"""Effets `Effects.Loki` — famille COUPS / BLOCS / PÉNÉTRATION-ARMURE : coups additionnels
(`additional_hit_groups` / `create_effect_hits_bonus_for_attack`), réduction de coups
(`create_effect_hits_malus_for_defense`), block (`create_effect_block_source_for_defense` /
stat-mod BLOCK_DAMAGE), pénétration d'armure (`get_armor_penetration`). 1 classe par effet natif (VA
citée). Cf. `loki/__init__.py`."""
from __future__ import annotations

from collections.abc import Mapping

import hexgeo

from ....services.effect_bonus import (EffectBonus, for_addition, for_subtraction,
                                       for_percent_decrease, for_percent_increase,
                                       for_percent_subtraction_capped)
from ....services.damage_combat import BlockSource
from ....services.static_battle_rules import TILE_STATUS_EFFECT_NAMES
from ..base import BaseEffect, is_charging_attack
from ..magnitude import ability_var, global_value, trait_var


class SquigHoundAdditionalHitsEffect(BaseEffect):
    """`SquigHound_AdditionalHitsEffect` (effet 0x50c=1292, orksRuntherd) — ajoute des coups HETEROGENES
    a l'attaque du porteur : `nrOfHits` coups a degat PROPRE [minDmg,maxDmg] (vars 0xc/0xd de l'ability
    SquigHound, ctor AbilityOrEffect 0x43a=1082) et profil PROPRE (`damageProfile`). Gate = OwnerIsCaster.

    Natif : `IdunBattle.Entities.Effects.Loki.SquigHound_AdditionalHitsEffect$$CreateAdditionalHits` -> `IdunBattle.Entities.Effects.EffectAdditionalHits$$Create` {condition=OwnerIsCaster, minDmg=GetMinMaxDamage(effect,idx0)=RandomAmount(ConfigVar(0xc),
    ConfigVar(0xd)), count=GetNumberConstant(0x2f=nrOfHits), damageProfile=GetDamageProfile(config).Value,
    maxDmg=GetMinMaxDamage(effect,idx1)}. `IdunBattle.Entities.Effects.BaseEffect$$GetMinMaxDamage` (overload 2-arg IdunBattle.Entities.Effects.BaseEffect$$GetMinMaxDamage) indexe
    les vars sur l'`AbilityStateFromEffect` (= le niveau de l'ability source sur l'unite, `ability_level`).
    minDmg/maxDmg in `variablesAffectedByRarityBonus` -> x multiplier. Les coups squig ont leur perce/profil
    propres et sont prev-threades APRES les coups d'arme (overkill continu) -> chemin `extra_groups` de
    `get_multi_hit_attack_prediction`. VALIDE live seed 500 (u87 orksRuntherd L50 mult200 :
    [minDmg50,maxDmg50]=[1330,1994]x2 = [2660,3988] par coup squig, count=2, profil Physical pierce 1)."""

    def additional_hit_groups(self, ctx: "Mapping | None" = None) -> "list[dict] | None":
        lvl = self.ability_level if self.ability_level is not None else self.level
        mn = ability_var("SquigHound", "minDmg", lvl, multiplier_pct=self.ability_variables_multiplier)
        mx = ability_var("SquigHound", "maxDmg", lvl, multiplier_pct=self.ability_variables_multiplier)
        count = ability_var("SquigHound", "nrOfHits", is_constant=True)  # numberConstant 0x2f
        if mn is None or mx is None or not count or count <= 0:
            return None
        try:
            import gameconfig as _GC
            profile = ((_GC.ability("SquigHound") or {}).get("constants") or {}).get("damageProfile") \
                or "Physical"
        except Exception:
            profile = "Physical"
        return [{"count": int(count), "min": int(mn), "max": int(mx), "profile": profile}]


class CordClawAdditionalHitsEffect(BaseEffect):
    """`CordClaw_AdditionalHitsEffect` (effet 0x4e2=1250, nom capté "CordClaw_AdditionHits",
    admecRuststalker Exitor-Rho) — après un cast CordClaw (0x462=1122), TOUTES les attaques du porteur
    jusqu'à la fin de son prochain tour gagnent des coups additionnels à dégât PROPRE (i2 : « All of
    Exitor-Rho's further attacks ... deal an additional 2x 582-873 Direct Damage »).

    Natif : `IdunBattle.Entities.Effects.Loki.CordClaw_AdditionalHitsEffect$$CreateAdditionalHits` -> EffectAdditionalHits
    {condition=OwnerIsActor, minmax=GetMinMaxDamage2(effect, idx0/idx1) = vars `minDmg_2`/`maxDmg_2`
    de l'ability CordClaw (indexées AbilityStateFromEffect = ablvl du cast, rarity-scalées ×mult),
    count=GetNumberConstant(0x32)=`nrOfHits_2` (=2), profile=GetDamageProfile(config)=DirectDamage
    (fallback natif 0xf si absent)}. Même canal #179 que SquigHound (prev-threadés après les coups
    d'arme, overkill continu).

    VALIDÉ arithmétique live (probe_57c_flathits.py D, 2468 s15 u83 lvl50 mult200, ability 1123 vs
    t162 deathPoxwalker) : per-hit [886,1330] = [minDmg_2,maxDmg_2][50]=[443,665]×2.0, ×2 coups ->
    rawMin +1772 / rawMax +2660 EXACT (nat 6590/9886 vs off-sans 4818/7226)."""

    def additional_hit_groups(self, ctx: "Mapping | None" = None) -> "list[dict] | None":
        lvl = self.ability_level if self.ability_level is not None else self.level
        mn = ability_var("CordClaw", "minDmg_2", lvl, multiplier_pct=self.ability_variables_multiplier)
        mx = ability_var("CordClaw", "maxDmg_2", lvl, multiplier_pct=self.ability_variables_multiplier)
        count = ability_var("CordClaw", "nrOfHits_2", is_constant=True)  # numberConstant 0x32
        if mn is None or mx is None or not count or count <= 0:
            return None
        try:
            import gameconfig as _GC
            profile = ((_GC.ability("CordClaw") or {}).get("constants") or {}).get("damageProfile") \
                or "Physical"
        except Exception:
            profile = "Physical"
        return [{"count": int(count), "min": int(mn), "max": int(mx), "profile": profile}]


class FearOfTheUnseenExtraDamageEffect(BaseEffect):
    """`FearOfTheUnseen_ExtraDamageEffect` (effet 0x4d7=1239, `tyranDeathleaper` « Deathleaper ») — pose
    sur LUI-MEME par le cast de `FearOfTheUnseen` (0x45b=1115) : jusqu'a l'expiration, ses attaques
    MELEE infligent `nrOfHits` coups additionnels HETEROGENES [minDmg,maxDmg] au profil
    `damageProfile` (= DirectDamage, pierce 100). i2 : « In its next turn, its attacks deal an additional
    3x 873-1091 Direct Damage ».

    Natif : `IdunBattle.Entities.Effects.Loki.FearOfTheUnseen_ExtraDamageEffect$$CreateAdditionalHits`
    -> `IdunBattle.Entities.Effects.EffectAdditionalHits$$Create` {
        trigger  = `get_OwnerIsCaster` op_BitwiseAnd `IsMeleeAttack`,
        damage   = `IdunBattle.Entities.Effects.BaseEffect$$GetMinMaxDamage(this, 0)`
                   = `RandomAmount(ConfigVar(0xc=minDmg, AbilityStateFromEffect),
                                   ConfigVar(0xd=maxDmg, AbilityStateFromEffect))`,
        additionalHitsType = 1,
        profile  = `GetDamageProfile(config, 0).Value` = `constants.damageProfile` = DirectDamage,
        hits     = `Get(GetNumberConstant(config, 0x2f = nrOfHits))`,
        forceOverkill = true,
        predictionDamage = `GetMinMaxDamage(this, 1)` = `Average(minDmg, maxDmg)` (canal display) }
    `.ctor` = `BaseEffect(AbilityOrEffect(0x45b = 1115 FearOfTheUnseen), 1)` -> les `ConfigVar` sont lues
    sur la config de l'ABILITY 1115, indexees par l'`AbilityStateFromEffect` (= le niveau d'ability de la
    SOURCE, donc `ability_level` cote port, propage par `scale_from_source` a la pose).

    Canal #179 STANDARD du PORTEUR, forme PREDEFINED [min,max] (== SquigHound/CordClaw : la face COMBAT
    resout le noeud `RandomAmount`). `minDmg`/`maxDmg` sont dans `variablesAffectedByRarityBonus` ->
    x multiplier de rarete. Gate `ctx["is_melee"]` requis (noeud `IsMeleeAttack` du trigger) ;
    `OwnerIsCaster` = le porteur EST l'attaquant, ce que le canal porteur garantit deja.

    RESIDU NOMME : `forceOverkill = true` (6e argument d'`EffectAdditionalHits.Create`) n'est PAS
    transporte par le canal `additional_hit_groups` (aucun consommateur ne le lit) -> les coups bonus ne
    bypassent PAS le cap Resilient (`ApplyResilientTraitDamageLimit`). NO-OP sur toute cible
    non-Resilient (le cas courant) ; a plomber le jour ou un scenario Resilient l'exerce."""

    def additional_hit_groups(self, ctx: "Mapping | None" = None) -> "list[dict] | None":
        if not ctx or ctx.get("is_melee") is not True:      # noeud IsMeleeAttack du trigger
            return None
        lvl = self.ability_level if self.ability_level is not None else self.level
        mn = ability_var("FearOfTheUnseen", "minDmg", lvl,
                         multiplier_pct=self.ability_variables_multiplier)
        mx = ability_var("FearOfTheUnseen", "maxDmg", lvl,
                         multiplier_pct=self.ability_variables_multiplier)
        count = ability_var("FearOfTheUnseen", "nrOfHits", is_constant=True)   # numberConstant 0x2f
        if mn is None or mx is None or not count or count <= 0:
            return None
        try:
            import gameconfig as _GC
            profile = ((_GC.ability("FearOfTheUnseen") or {}).get("constants") or {}) \
                .get("damageProfile") or "DirectDamage"
        except Exception:
            profile = "DirectDamage"
        return [{"count": int(count), "min": int(mn), "max": int(mx), "profile": profile}]


class FoulInfusionExtraHitsEffect(BaseEffect):
    """`FoulInfusion_ExtraHitsEffect` (effet 0x432=1074, deathPutrifier Pestillian) — au cast de
    FoulInfusion (1038), Pestillian ET les unites Chaos dans son aura de Contagion recoivent CET
    effet : leurs attaques normales MELEE infligent +1 coup Toxic « this round and the next » (i2).

    Natif : `IdunBattle.Entities.Effects.Loki.FoulInfusion_ExtraHitsEffect$$CreateAdditionalHits` -> `EffectAdditionalHits
    .Create` {trigger = IsMeleeAttack & OwnerIsCaster, amount = ConfigVar(dmg, GetAbilityState(effet)),
    count = GetNumberConstant(0x2f)=nrOfHits (=1), profile = GetDamageProfile(config) = Toxic (p70)}.
    Le trigger est EVALUE en prediction (mesure 2468 s14 : les 3 effets u91/u162/u166 ne contribuent
    PAS a la prediction RANGED de u89 — le +2992 venait d'ExplosiveMaladies) : canal #179 standard
    du PORTEUR, gate `ctx["is_melee"]` requis (IsMeleeAttack). `amount` seul -> spread ±20% pipeline.
    NON exerce bit-exact live (porte 1:1 du decompile ; s'active quand u91/poxwalkers attaquent MELEE)."""

    def additional_hit_groups(self, ctx: "Mapping | None" = None) -> "list[dict] | None":
        if not ctx or ctx.get("is_melee") is not True:      # trigger IsMeleeAttack (evalue)
            return None
        lvl = self.ability_level if self.ability_level is not None else self.level
        amt = ability_var("FoulInfusion", "dmg", lvl, multiplier_pct=self.ability_variables_multiplier)
        count = ability_var("FoulInfusion", "nrOfHits", is_constant=True)   # numberConstant 0x2f
        if amt is None or amt <= 0 or not count or count <= 0:
            return None
        try:
            import gameconfig as _GC
            profile = ((_GC.ability("FoulInfusion") or {}).get("constants") or {}).get("damageProfile") \
                or "Toxic"
        except Exception:
            profile = "Toxic"
        return [{"count": int(count), "amount": int(amt), "profile": profile}]


class CyclicIonBlasterAdditionalHitsEffect(BaseEffect):
    """`CyclicIonBlaster_AdditionalHitsEffect` (effet 0x47c=1148, classe native
    `IdunBattleLogic.Entities.Abilities.Triggered.Loki`, Tau) — i2 : « All attacks deal an additional
    3x minDmg-maxDmg Particle Damage. If the target has a Markerlight or the Mechanical trait these
    hits deal +extraDmg Damage ».

    Natif : `IdunBattleLogic.Entities.Abilities.Triggered.Loki.CyclicIonBlaster_AdditionalHitsEffect$$CreateAdditionalHits` -> `EffectAdditionalHits.Create` {trigger = OwnerIsCaster
    (TOUTES les attaques, pas de gate melee/normal), amount = ConditionalAmount(HasEffect(target,
    0x462=1122 Markerlight) | HasTrait(target, 5=Mechanical), RandomAmount(Sum(minDmg 0xc, extraDmg 8),
    Sum(maxDmg 0xd, extraDmg 8)), RandomAmount(minDmg, maxDmg)), count = GetNumberConstant(0x2f=
    nrOfHits=3), profile = GetDamageProfile = Particle (p35), minNode = ConditionalAmount(cond,
    Sum(minDmg, extraDmg), minDmg)}.

    PREDICTION (#57e, 54321 s19 u77->t93 + varTrace) : le display n'evalue QUE le noeud MIN (2
    resolutions var 0xc minDmg etat {50,180} -> 599 ; JAMAIS 0xd ni 8) et laisse le pipeline etaler :
    amount 599 x ±20% x %-mods attaquant (1.33 RangedSpecialist x 0.7 Pinned) x pierce Particle 35
    (armure haute) = [156,234]/coup x3 = nat [1098,1644] - arme [630,942] EXACT -> forme « amount »
    (spread pipeline, comme FoulInfusion), PAS predefined [min,max]. Multiplier = GLOBAL de l'unite
    (varTrace mult=180 ; pas le per-ability #68). Gate +extraDmg = cible Markerlight (effet 1122) OU
    trait Mechanical, via ctx tgt_effect_names/tgt_traits (branche non exercee : t93 ni l'un ni
    l'autre -> flag validator). Face COMBAT (RandomAmount reel) non confrontee -> flag validator."""

    def additional_hit_groups(self, ctx: "Mapping | None" = None) -> "list[dict] | None":
        lvl = self.ability_level if self.ability_level is not None else self.level
        mn = ability_var("CyclicIonBlaster", "minDmg", lvl,
                         multiplier_pct=self.ability_variables_multiplier)
        count = ability_var("CyclicIonBlaster", "nrOfHits", is_constant=True)  # numberConstant 0x2f
        if mn is None or mn <= 0 or not count or count <= 0:
            return None
        c = ctx or {}
        if ("Markerlight" in (c.get("tgt_effect_names") or ()) or
                "Mechanical" in (c.get("tgt_traits") or ())):
            extra = ability_var("CyclicIonBlaster", "extraDmg", lvl,
                                multiplier_pct=self.ability_variables_multiplier)
            mn = int(mn) + int(extra or 0)      # noeud min du Conditional = Sum(minDmg, extraDmg)
        try:
            import gameconfig as _GC
            profile = ((_GC.ability("CyclicIonBlaster") or {}).get("constants") or {}).get("damageProfile") \
                or "Particle"
        except Exception:
            profile = "Particle"
        return [{"count": int(count), "amount": int(mn), "profile": profile}]


class _BaseFleshmetalGunsEffect(BaseEffect):
    """`BaseFleshmetalGunsEffect` (IdunBattle.Entities.Effects.Loki.BaseFleshmetalGunsEffect$$.ctor, EffectSource = AbilityOrEffect 0x429=1065
    FleshmetalGuns, blackObliterator Volk) — mold commun des 3 effets CYCLIQUES du passif : au debut
    du tour de Volk, `IdunBattleLogic.Entities.Abilities.Active.Loki.FleshMetalGunsAbility$$CreateBehaviour` retire les 3 effets puis pose
    `If(UnitTurnsStarted % 3 == 1 -> AddEffect(0x42b FocusedMalice), == 2 -> AddEffect(0x4bc
    RuinousSalvo), == 0 -> AddEffect(0x4c5 WarpHail))` — le CYCLE est natif (l'etat runner porte
    l'effet courant), seul le canal #179 est porte ici.

    Natif : `IdunBattle.Entities.Effects.Loki.BaseFleshmetalGunsEffect$$CreateAdditionalHits` -> `EffectAdditionalHits.Create`
    {condition = OwnerIsCaster & IsRangedAttack, noeud roll = GetMinMaxDamage(effect, 0, keyMin, keyMax)
    = RandomAmount(ConfigVar(keyMin, AbilityStateFromEffect), ConfigVar(keyMax, ...)), noeud display =
    GetMinMaxDamage(effect, 1, ...) = **Average** des memes ConfigVars, count = GetNumberConstant(
    keyCount), profile = virtuel 0x728}. Les cles min/max/count/profil sont des VIRTUELS par variante
    (suffixe _2/_3) : base = minDmg/maxDmg/nrOfHits/GetDamageProfile (Melta) ; RuinousSalvo override
    IdunBattle.Entities.Effects.Loki.FleshmetalGunsRuinousSalvoEffect$$GetDamageProfileType -> GetDamageProfile2 (Flame, jeu _2) ; WarpHail IdunBattle.Entities.Effects.Loki.FleshmetalGunsWarpHailEffect$$GetDamageProfileType ->
    GetDamageProfile3 (HeavyRound, jeu _3). min/max in `variablesAffectedByRarityBonus` -> x multiplier ;
    niveau = AbilityStateFromEffect (ability_level).

    ⚠ FORME DISPLAY = AMOUNT (midpoint), PAS predefined [min,max] — GROUND TRUTH AllMods (probe_65_
    allmods, round WarpHail, mult 180) : inputs per-coup du groupe = 718/1076 = round((698+1096)/2
    x 0.8/1.2) ou 698/1096 = minDmg_3/maxDmg_3 int-resolus (varTrace 56/57), outs x0.55 (pierce
    HeavyRound) = [395,592]/coup -> oracle ranked (3184,4772) reconstruit EXACT. La prediction native
    evalue le noeud Average (midpoint des vars INT-resolues) puis applique le spread pipeline ±20%
    (IdunBattle.Core.Services.DamageCalculations$$CalculateDamageSpread). Les paires Melta [554,831] et Flame [443,665] (comme SquigHound
    [1330,1994] / CordClaw [886,1330]) sont des paires ±20% EXACTES autour de leur moyenne -> predefined
    et amount-midpoint coincident au round pres ; seule la paire WarpHail [388,609] est ASYMETRIQUE
    (±22.2%) et discrimine les formes (miss +-22 du 1er run probe_65). Face COMBAT (roll reel) =
    RandomAmount(min,max) — bornes DIFFERENTES du display (incoherence native mirroree telle quelle ;
    aucun consommateur combat du canal #179 a ce jour).

    DECOUVERT par probe #62 (seed 62001 MC1_67) : u79 blackObliterator (4,4) vs u81 natif (2321,3479)
    vs offline (725,1087). i2 : << Ranged attacks deal an additional {nrOfHits}x {minDmg}-{maxDmg} ...
    >>. Le volet << Despoiled Ground >> de WarpHail = `FleshMetalGuns_TileEffectAbility IdunBattleLogic.Entities.Abilities.Active.Loki.FleshMetalGuns_TileEffectAbility$$CreateBehaviour`
    (effet de TUILE, hors canal #179, non porte). #65."""

    _SUFFIX = ""                       # cles gameconfig de la variante : ""|"_2"|"_3"
    _FALLBACK_PROFILE = "Melta"

    def additional_hit_groups(self, ctx: "Mapping | None" = None) -> "list[dict] | None":
        if not ctx or ctx.get("is_melee") is not False:   # trigger IsRangedAttack (evalue)
            return None
        lvl = self.ability_level if self.ability_level is not None else self.level
        sfx = self._SUFFIX
        mn = ability_var("FleshmetalGuns", "minDmg" + sfx, lvl,
                         multiplier_pct=self.ability_variables_multiplier)
        mx = ability_var("FleshmetalGuns", "maxDmg" + sfx, lvl,
                         multiplier_pct=self.ability_variables_multiplier)
        count = ability_var("FleshmetalGuns", "nrOfHits" + sfx, is_constant=True)
        if mn is None or mx is None or not count or count <= 0:
            return None
        try:
            import gameconfig as _GC
            profile = ((_GC.ability("FleshmetalGuns") or {}).get("constants") or {}) \
                .get("damageProfile" + sfx) or self._FALLBACK_PROFILE
        except Exception:
            profile = self._FALLBACK_PROFILE
        # display natif = noeud Average (midpoint des vars INT-resolues) + spread pipeline ±20%
        # (cf. docstring de la base) -> forme "amount" du canal #179, midpoint possiblement x.5.
        return [{"count": int(count), "amount": (int(mn) + int(mx)) / 2, "profile": profile}]


class FleshmetalGunsFocusedMaliceEffect(_BaseFleshmetalGunsEffect):
    """`FleshmetalGunsFocusedMaliceEffect` (effet 0x42b=1067, tour 1 du cycle) — defauts de la BASE :
    vars minDmg/maxDmg, nrOfHits (=2), GetDamageProfile = Melta (pas d'override nomme)."""

    _SUFFIX = ""
    _FALLBACK_PROFILE = "Melta"


class FleshmetalGunsRuinousSalvoEffect(_BaseFleshmetalGunsEffect):
    """`FleshmetalGunsRuinousSalvoEffect` (effet 0x4bc=1212, tour 2 du cycle) — jeu _2 :
    minDmg_2/maxDmg_2, nrOfHits_2 (=2), `IdunBattle.Entities.Effects.Loki.FleshmetalGunsRuinousSalvoEffect$$GetDamageProfileType` -> GetDamageProfile2 = Flame."""

    _SUFFIX = "_2"
    _FALLBACK_PROFILE = "Flame"


class FleshmetalGunsWarpHailEffect(_BaseFleshmetalGunsEffect):
    """`FleshmetalGunsWarpHailEffect` (effet 0x4c5=1221, tour 3 du cycle) — jeu _3 :
    minDmg_3/maxDmg_3, nrOfHits_3 (=2), `IdunBattle.Entities.Effects.Loki.FleshmetalGunsWarpHailEffect$$GetDamageProfileType` -> GetDamageProfile3 =
    HeavyRound. Le volet Despoiled Ground (tuile) est un artefact separe non porte (IdunBattleLogic.Entities.Abilities.Active.Loki.FleshMetalGuns_TileEffectAbility$$CreateBehaviour)."""

    _SUFFIX = "_3"
    _FALLBACK_PROFILE = "HeavyRound"


class _ExplosiveMaladiesAuraHitsBase(BaseEffect):
    """Mold commun des deux effets-AURA d'ExplosiveMaladies (passif deathPutrifier Pestillian, effets
    HOSTES SUR LE PORTEUR — rien n'est poste sur le beneficiaire, modele #49) : +nrOfHits=1 coup de
    ConfigVar(8=extraDmg, GetAbilityState(effet)) au profil `GetAffectedDamageProfile` (= Blast p15)
    aux attaques NORMALES des amis ADJACENTS au porteur (`AdjacentFriends(owner, 1)` IdunBattle.Entities.Effects.Loki.ExplosiveMaladies_ExtraRangedAttackEffect$$CreateTargetSelector),
    adjacence re-evaluee a la TUILE CANDIDATE.

    VALIDE bit-exact live (probe #57c-C, 2468 s14) : u89 (Ork, ranged, NON porteur) a (2,3) adjacent
    de u91 -> +1 coup de extraDmg[50]x1.8=2992, roll ±20% PUIS x1.5 CrushingStrike (les %-mods
    attaquant S'APPLIQUENT au coup folde) = delta [3591, 5385] ; a (0,3) non adjacent -> rien.
    i2 : « Enemies defeated by affected attacks are always overkilled » (flag overkill non porte)."""

    _VARIANT_IS_MELEE = False        # ExtraRanged : IsRangedAttack ; ExtraMelee : IsMeleeAttack

    def _gates_ok(self, ctx: "Mapping") -> bool:
        return True                  # gates additionnels de la variante (Chaos pour la melee)

    def create_aura_additional_hits_for_ally(self, ctx: "Mapping") -> "dict | None":
        att_pos, owner_pos = ctx.get("att_pos"), ctx.get("owner_pos")
        if att_pos is None or owner_pos is None:
            return None
        if ctx.get("att_team") != ctx.get("owner_team"):     # AdjacentFriends (allies seulement)
            return None
        if bool(ctx.get("is_melee")) != self._VARIANT_IS_MELEE:   # trigger Is(Ranged|Melee)Attack
            return None
        if not self._gates_ok(ctx):
            return None
        if hexgeo.distance(tuple(att_pos), tuple(owner_pos)) != 1:   # AdjacentFriends(owner, 1)
            return None
        lvl = self.ability_level if self.ability_level is not None else self.level
        amt = ability_var("ExplosiveMaladies", "extraDmg", lvl,
                          multiplier_pct=self.ability_variables_multiplier)
        count = ability_var("ExplosiveMaladies", "nrOfHits", is_constant=True)   # numberConstant 0x2f
        if amt is None or amt <= 0 or not count or count <= 0:
            return None
        try:
            import gameconfig as _GC
            profile = ((_GC.ability("ExplosiveMaladies") or {}).get("constants") or {}) \
                .get("affectedDamageProfile") or "Blast"     # GetAffectedDamageProfile
        except Exception:
            profile = "Blast"
        return {"count": int(count), "amount": int(amt), "profile": profile}


class ExplosiveMaladiesExtraRangedAttackEffect(_ExplosiveMaladiesAuraHitsBase):
    """`IdunBattle.Entities.Effects.Loki.ExplosiveMaladies_ExtraRangedAttackEffect$$CreateAdditionalHits` — trigger
    `OwnerIsCaster & IsRangedAttack`, selecteur `UnitsWithRangedWeapons(AdjacentFriends(owner,1))`
    IdunBattle.Entities.Effects.Loki.ExplosiveMaladies_ExtraRangedAttackEffect$$CreateTargetSelector : TOUT ami adjacent (arme ranged requise — implicite : l'attaque predite EST ranged)."""

    _VARIANT_IS_MELEE = False


class ExplosiveMaladiesExtraMeleeAttackEffect(_ExplosiveMaladiesAuraHitsBase):
    """`IdunBattle.Entities.Effects.Loki.ExplosiveMaladies_ExtraMeleeAttackEffect$$CreateAdditionalHits` — trigger
    `OwnerIsCaster & IsMeleeAttack` ; i2 : seuls les amis CHAOS adjacents beneficient du coup en
    MELEE (selecteur melee non decompile — gate GrandAlliance Chaos mirror i2, flag validator)."""

    _VARIANT_IS_MELEE = True

    def _gates_ok(self, ctx: "Mapping") -> bool:
        return (ctx.get("att_grand_alliance") == "Chaos")


class InfernalPactsAdditionalHitsEffect(BaseEffect):
    """`InfernalPacts_AdditionalHitsEffect` (effet 0x4ae=1198, AURA HOSTEE SUR LE PORTEUR — Abraxas
    thousInfernalMaster, passif `InfernalPacts` 0x492=1170 ; #202-B) : +nrOfHits=1 coup PREDEFINED
    [minDmg,maxDmg] (courbe InfernalPacts 10-20 L1 -> 728-1455 L65, RandomAmount natif — PAS de spread
    ±20%) au profil `affectedDamageProfile` (=Psychic) aux attaques des amis CHAOS adjacents ring-1 :
    ranged pour tous, melee AUSSI pour les Daemons.

    Natif (case-202 §7) : IdunBattle.Entities.Effects.Loki.InfernalPacts_AdditionalHitsEffect$$.ctor = `BaseEffect(AbilityOrEffect(0x492), 1, 0)` (effet
    auto-porteur EffectsDatabase b__14_225, AUCUNE classe Ability dediee) ; `IdunBattle.Entities.Effects.Loki.InfernalPacts_AdditionalHitsEffect$$CreateAdditionalHits` -> `IdunBattle.Entities.Effects.EffectAdditionalHits$$Create` {trigger = `OwnerIsCaster &
    (IsRangedAttack | HasTrait(Caster, 0x3fb=1019 Daemon))`, dmg = `IdunBattle.Entities.Effects.BaseEffect$$GetMinMaxDamage(this,0) = `RandomAmount(ConfigVar(0xc=minDmg), ConfigVar(0xd=maxDmg))`, count =
    `GetNumberConstant(0x2f=nrOfHits)`, profil = `GetAffectedDamageProfile`, avg =
    `GetMinMaxDamage(this,1)` = `Average(min,max)` (canal display)} ; `IdunBattle.Entities.Effects.Loki.InfernalPacts_AdditionalHitsEffect$$CreateTargetSelector` = `Unique( UnitsWithRangedWeapons(UnitsWithTrait(AdjacentFriends(Caster,1),
    0x7ea=2026 Chaos)) + UnitsWithTrait(AdjacentFriends(Caster,1) avec Chaos, 0x3fb Daemon) )` ;
    `IdunBattle.Entities.Effects.Loki.InfernalPacts_AdditionalHitsEffect$$GetRefreshTriggers` = [PreAttack(5), PreAttackDamageHit(7)] -> l'aura est reevaluee
    AU MOMENT de l'attaque = modele tuile-candidate (#49/#153), rien n'est pose sur le beneficiaire.

    Gates offline : allie meme team + ring-1 + CHAOS (grande alliance — les traits gameconfig ne
    portent pas Chaos/Imperial, mirror UnitsWithTrait(0x7ea) via grand_alliance, precedent
    ExplosiveMaladies melee) + (attaque ranged OU attaquant Daemon). La branche selecteur
    `UnitsWithRangedWeapons` est implicite cote ranged (l'attaque consideree EST ranged, precedent
    ExplosiveMaladiesExtraRanged).

    DEGAT BI-CANAL (mesure live probe_202b, seed 20202 round-2 propre) : le descripteur natif
    porte LES DEUX noeuds — field[1] = RandomAmount(min,max) (resolution COMBAT) et field[2] =
    Average(min,max) (canal PREDICTION/display, param_8 de Create). La prediction native de
    l'attaque bonus = Average ± 20% (paire sum-preserving (3248,4871) vs plage brute (2948,5172) —
    la courbe InfernalPacts max=2x min DISCRIMINE, contrairement a SquigHound max=1.5x min ou les
    deux modeles coincident). Le groupe expose donc `amount` (Average EXACT, .5 possible —
    precedent FleshmetalGuns #65) consomme par la PREDICTION, ET `min`/`max` (plage RandomAmount)
    consommes par la face COMBAT (`_execute_additional_hits`, qui prefere min/max)."""

    def create_aura_additional_hits_for_ally(self, ctx: "Mapping") -> "dict | None":
        att_pos, owner_pos = ctx.get("att_pos"), ctx.get("owner_pos")
        if att_pos is None or owner_pos is None:
            return None
        if ctx.get("att_team") != ctx.get("owner_team"):        # AdjacentFriends (allies seulement)
            return None
        if ctx.get("att_grand_alliance") != "Chaos":            # UnitsWithTrait(0x7ea=2026) — les 2 branches
            return None
        is_daemon = "Daemon" in (ctx.get("att_traits") or ())   # UnitTrait 0x3fb=1019
        if bool(ctx.get("is_melee")) and not is_daemon:         # trigger IsRangedAttack | HasTrait(Daemon)
            return None
        if hexgeo.distance(tuple(att_pos), tuple(owner_pos)) != 1:   # AdjacentFriends(caster, 1)
            return None
        lvl = self.ability_level if self.ability_level is not None else self.level
        mn = ability_var("InfernalPacts", "minDmg", lvl, multiplier_pct=self.ability_variables_multiplier)
        mx = ability_var("InfernalPacts", "maxDmg", lvl, multiplier_pct=self.ability_variables_multiplier)
        count = ability_var("InfernalPacts", "nrOfHits", is_constant=True)    # numberConstant 0x2f
        if mn is None or mx is None or not count or count <= 0:
            return None
        try:
            import gameconfig as _GC
            profile = ((_GC.ability("InfernalPacts") or {}).get("constants") or {}) \
                .get("affectedDamageProfile") or "Psychic"      # GetAffectedDamageProfile
        except Exception:
            profile = "Psychic"
        # bi-canal : `amount` = noeud Average (PREDICTION, exact — pas de troncature du .5) ;
        # `min`/`max` = noeud RandomAmount (COMBAT). Cf. docstring (mesure 202b).
        return {"count": int(count), "amount": (int(mn) + int(mx)) / 2,
                "min": int(mn), "max": int(mx), "profile": profile}


class AnvilShieldAdditionalBlockEffect(BaseEffect):
    """`AnvilShield_AdditionalBlock` (effet 0x4b2=1202, StaticStatModifierEffect) — buff BLOCK_DAMAGE
    self de Arjac (spaceRockfist), OWNER-EFFECT pose A L'INIT DE L'ABILITY. Pose par
    `IdunBattleLogic.Entities.Abilities.Triggered.Loki.AnvilShieldAbility_ApplyAdditionalBlockAndBlockChance$$CreateBehaviour` :
    `AddStaticStatModifierEffect(0x4b2, statType 8=BLOCK_DAMAGE, GetVariableForLevel(0x14))` (2e effet de
    la meme behaviour = 0x4b0=1200 BlockChanceBelowHealthCap, stat 7=BLOCK_CHANCE / var blockChance, gate
    sante -> NON porte ici, ambiguite abs-vs-% du cap).

    Magnitude = ability_var AnvilShield `blockDmg` (idx enum 0x14 <-> stat 8 BLOCK_DAMAGE ; blockDmg in
    variablesAffectedByRarityBonus -> scale x multiplier de l'unite). blockDmg[L1..65]=[10..728]. Effet
    INCONDITIONNEL (pas d'ActiveCondition). AnvilShield = ability ACTIVE -> index activeAbilityLevel
    (fallback passif/stack). EffectSource = AbilityOrEffect 0x493 (=AnvilShield, ability enum).

    ⚠ MIS-ATTRIBUTION CORRIGEE (#222) : l'ancienne note « pose par le vecteur ON-BLOCK » etait FAUSSE.
    Le `CreateTrigger` de cette ability est le corps DEDUPLIQUE `IdunBattleLogic.Entities.Abilities.Triggered.LifewardsAddEffectAbility$$CreateTrigger` (`return df@0xa8`), et
    `df@0xa8` est construit par `IdunBattleLogic.Entities.DSLFactory$$InitializeShared` = `On(0x21 = AbilityInit) &
    OwnerIsActor` -> 1202 (et 1200) sont poses A LA CREATION de l'unite, PAS au block. GROUND TRUTH live :
    Arjac porte `AnvilShield_AdditionalBlock` (level 1, remaining 0) des le PREMIER `decisionView` d'un
    runner frais -> l'effet est deja materialise par le seed, RIEN a caber. Le vrai volet ON-BLOCK
    (`On(UnitBlocked=0x3d)`) est `ApplyIce`/`ApplyStun` (cf. triggers/loki/anvil_shield.py)."""

    def get_stat_modification_stat(self) -> int | None:
        return 8                                     # StatType.BLOCK_DAMAGE

    def get_stat_modification_amount(self) -> int | None:
        lvl = (self.active_ability_level if self.active_ability_level is not None
               else (self.ability_level if self.ability_level is not None else self.level))
        return ability_var("AnvilShield", "blockDmg", lvl,
                           multiplier_pct=self.ability_variables_multiplier)


def _anvil_shield_level(eff: BaseEffect) -> "int | None":
    """Niveau qui indexe `variables[level]` d'AnvilShield — MEME resolution que
    `AnvilShieldAdditionalBlockEffect` (AnvilShield est une ability ACTIVE : index `activeAbilityLevel`,
    fallback passif/stack)."""
    return (eff.active_ability_level if eff.active_ability_level is not None
            else (eff.ability_level if eff.ability_level is not None else eff.level))


class AnvilShieldBlockChanceBelowHealthCapEffect(BaseEffect):
    """`AnvilShield_BlockChanceBelowHealthCap` (effet 0x4b0=1200, classe native
    `IdunBattle.Entities.Effects.Loki.AnvilShield_BlockChanceBelowHealthCapEffect` — base
    `IdunBattle.Entities.Effects.ADynamicStatModifierEffect`, source `AbilityOrEffect 0x493` = AnvilShield).

    POSE : owner-effect pose A L'INIT DE L'ABILITY, 2e volet de
    `IdunBattleLogic.Entities.Abilities.Triggered.Loki.AnvilShieldAbility_ApplyAdditionalBlockAndBlockChance$$CreateBehaviour` :
    `AddStaticStatModifierEffect(Self@0x148, 0x4b0, statType 7 = BLOCK_CHANCE,
     GetVariableForLevel(0x15 = blockChance))` (le 1er volet = 0x4b2=1202 stat 8 BLOCK_DAMAGE, var 0x14
    = blockDmg). Son `CreateTrigger` est le corps deduplique `LifewardsAddEffectAbility$$CreateTrigger`
    (`return df@0xa8` = `On(0x21 = AbilityInit) & OwnerIsActor`).

    ACTIVE-CONDITION (le point qui etait NON TRANCHE en #133, RESOLU ici) —
    `IdunBattle.Entities.Effects.Loki.AnvilShield_BlockChanceBelowHealthCapEffect$$CreateActiveCondition` :
        AmountIsEqualOrGreater( Direct(GetNumberConstant(0x4f)),
                                StatAmount(Self@0x148, 5 = HEALTH, 1 = CURRENT_PCT) )
    `StatPart 1 = CURRENT_PCT` => la comparaison est un **POURCENTAGE**, pas une valeur absolue :
    l'effet n'est ACTIF que si `healthPct >= PV courant en %`. `GetNumberConstant(0x4f)` =
    `gameconfig.ability('AnvilShield').constants['healthPct']` = **35**. i2 : « **If Arjac is below 35%
    Health**, ... he gains +20% Block chance ».

    GROUND TRUTH LIVE (#100, runner 11/28, `probe_anvil_shield_residues.py`) : a 100 % PV l'effet est
    ABSENT de `decisionView.effects` et `blockChance = 0` ; a 31.8 % (puis 8.2 %) il APPARAIT et
    `blockChance = 20`. `decisionView.effects` n'expose donc que les effets ACTIFS — c'est aussi ce que
    lit le gate `HasEffect(..., activeOnly=1)` d'`ApplyStun`.

    MAGNITUDE : `blockChance[activeAbilityLevel]` = 20 au rank courant. `blockChance` n'est **PAS** dans
    `variablesAffectedByRarityBonus` (contraste `blockDmg` : 728 -> 997 avec le multiplier) -> la valeur
    live est 20 EXACTEMENT, non scalee (`ability_var` applique la regle par-config).

    Le CHANGESTAT n'est PAS declare en `applied_stat_mods` : il est pilote par le driver
    `runner/operations/refresh_effects.py` (mirror `IdunBattle.Operations.RefreshEffectsOperation`
    ActivateEffect/DeactivateEffect -> `AStatModifierEffect.ApplyModification/RevertModification`), pour
    que la contribution SUIVE la condition (Arjac qui passe sous/au-dessus de 35 % en cours de bataille).
    `get_stat_modification_stat/amount` restent declares : c'est ce que lit l'ATTRIBUTION du seed
    (`stat_modifications_by_source`) quand l'effet est capte live (donc deja actif)."""

    def is_active(self, unit_state: Mapping | None = None) -> bool:
        """`CreateActiveCondition` : `healthPct >= GetStat(Self, HEALTH, CURRENT_PCT)`. `unit_state` =
        `{hp, max_hp}` (meme convention que `PowerTripFullHealthEffect`). PV non captes -> True
        (degradation fidele : on ne masque pas l'effet a tort)."""
        s = unit_state or {}
        hp, mx = s.get("hp"), s.get("max_hp")
        cap = ability_var("AnvilShield", "healthPct", is_constant=True)   # GetNumberConstant(0x4f) = 35
        if hp is None or mx is None or not mx or cap is None:
            return True
        return int(cap) >= (100.0 * float(hp) / float(mx))

    def get_stat_modification_stat(self) -> int | None:
        return 7                                     # StatType.BLOCK_CHANCE

    def get_stat_modification_amount(self) -> int | None:
        return ability_var("AnvilShield", "blockChance", _anvil_shield_level(self),
                           multiplier_pct=self.ability_variables_multiplier)

    def reverted_stats(self) -> "list":
        from ...stats import StatType
        return [StatType.BLOCK_CHANCE]


class AnvilShieldFrozenAttackerAdvantageEffect(BaseEffect):
    """`AnvilShield_FrozenAttackerAdvantage` (effet 0x4b1=1201, classe native
    `IdunBattle.Entities.Effects.Loki.AnvilShield_FrozenAttackerAdvantageEffect` — meme base
    `ADynamicStatModifierEffect`, meme source `AbilityOrEffect 0x493`).

    POSE : `IdunBattleLogic.Entities.Abilities.Triggered.Loki.AnvilShieldAbility_FrozenAttackerAdvantage$$CreateBehaviour` =
    `AddStaticStatModifierEffect(Self@0x148, 0x4b1, statType 7 = BLOCK_CHANCE,
     GetVariableForLevel(0x15 = blockChance))` — **MEME stat et MEME variable que 1200** : +20 % de
    chance de bloquer. i2 : « ... **or if his attacker is on a hex covered in Ice**, he gains +20 % Block
    chance ».

    DUREE : l'effet ne porte AUCUNE ActiveCondition ; son SEUL trigger propre est
    `IdunBattle.Entities.Effects.Loki.AnvilShield_FrozenAttackerAdvantageEffect$$CreateTargetTrigger` =
    `On(0xe = UnitPostAbility) & AreEqual(target@0x178, EffectSource(thisEffect@0x150))` -> il est donc
    consomme A LA FIN de l'ability qui a declenche sa pose (mirror : `AnvilShieldFrozenAdvantageExpire`,
    `runner/operations/triggers/loki/anvil_shield.py`). GROUND TRUTH LIVE (#100) : apres l'attaque,
    l'effet est ABSENT de `decisionView.effects` et `blockChance` est retombe a 0 — alors que le STUN
    a bien eu lieu PENDANT l'attaque (le gate `HasEffect(Arjac, 1201, activeOnly=1)` d'`ApplyStun` etait
    donc vrai a cet instant, Arjac etant a 100 % PV donc 1200 INACTIF).

    Contrairement a 1200, le ChangeStat est declare en `applied_stat_mods` : l'effet est pose a
    l'EXECUTION (jamais dans le seed) et n'a pas de condition -> `AddEffectOperation._apply_stat_mods`
    l'applique, la feuille `RemoveEffect` le reverte via `reverted_stats()`."""

    def get_stat_modification_stat(self) -> int | None:
        return 7                                     # StatType.BLOCK_CHANCE

    def get_stat_modification_amount(self) -> int | None:
        return ability_var("AnvilShield", "blockChance", _anvil_shield_level(self),
                           multiplier_pct=self.ability_variables_multiplier)

    def applied_stat_mods(self, stats_ctx) -> "list":
        """DATA du `ChangeStat` (part 5) pose a l'application : BLOCK_CHANCE += blockChance[level]."""
        amt = self.get_stat_modification_amount()
        return [(7, int(amt))] if amt else []

    def reverted_stats(self) -> "list":
        from ...stats import StatType
        return [StatType.BLOCK_CHANCE]


class BeastSlayerExtraBlockEffect(BaseEffect):
    """`IdunBattleLogic.Entities.Abilities.Triggered.Loki.BeastSlayerAbility$$CreateAddBlockEffectBehaviour` (trait BeastSlayer, effet
    `BeastSlayer_ExtraBlock`, cote DEFENSE) : `AddExtraBlockEffectToOwner(chance, amount)` avec
    chance=`IdunBattleLogic.Entities.Abilities.Triggered.Loki.BeastSlayerAbility$$GetBlockChance`=`GetNumberConstant(0x2d=beastSlayerBlockChance)` (=10) et
    amount=`IdunBattleLogic.Entities.Abilities.Triggered.Loki.BeastSlayerAbility$$GetBlockDamage`=`PercentageOf(StatAmount(0x10=FixedArmor),
    GetNumberConstant(0x36=beastSlayerBlockAsMaxArmorPct))` (=100% du FixedArmor COURANT).
    => source de BLOCK SUPPLEMENTAIRE (roll separe : +10% chance de bloquer 100% de l'armure courante
    en degat), ABSENTE du scalaire GetStat(7/8) (verifie LIVE 2026-07-09 : orksNob blockChance=0). Le
    natif la tient dans `GetMultiValueStat(7)`. Variables de TRAIT -> globales, NON scalees par le mult.
    Cf. docs/rl/case-68-orksnob-attacker-effects.md (#72)."""

    def create_effect_block_source_for_defense(self, defender_fixed_armor: int = 0,
                                               defender_attack: int = 0):
        chance = trait_var("BeastSlayer", "beastSlayerBlockChance")
        pct = trait_var("BeastSlayer", "beastSlayerBlockAsMaxArmorPct")
        if not chance or pct is None:
            return None
        amount = int(int(defender_fixed_armor) * int(pct) / 100)   # PercentageOf(FixedArmor, blockDmgPct)
        if amount <= 0:
            return None
        # block_id = l'ENTITE-EFFET (`BlockChanceInfo.entityId`, cle du `failedBlockIds:
        # List<BEntityId>` de IdunBattle.Core.Services.DamageCalculations$$CalculateBlockChances) :
        # une source EXCLUE apres son 1er echec sur un coup (exclusion inter-coups, cf.
        # AttackDamageOperation._run_hits #72). Offline = `effect_type` (cf. `block_source_id`).
        return BlockSource(chance=int(chance), amount=amount,
                           block_id=self.block_source_id(int(chance)))


class DaemonExtraBlockEffect(BaseEffect):
    """Trait Daemon, effet `Daemon_ExtraBlock` (1034) — source de BLOCK du defenseur daemon (#54A) :
    chance = `daemonBlockChance` (25), amount = `daemonBlockDamagePercentage`% (50) de la stat
    **Attack COURANTE du defenseur** (variables de TRAIT globales, non scalees par le mult). Entree
    `GetMultiValueStat(7)` (`IdunBattle.Core.Services.DamageCalculations$$CalculateBlockChances`), ABSENTE du scalaire GetStat(7/8),
    comme BeastSlayer. Cote PREDICTION elle pilote le scenario block `list[0]@0x50` du
    `DamagePredictionResult` (« tous les coups bloques », `IdunBattle.Core.Services.DamagePrediction$$CalculateDamagePredictionScenario` : dmg' = max(0, dmg − blockAmount)) consomme par `IdunBattle.Core.Services.DamagePredictionResult$$get_WillBeKill` /
    `IdunBattle.Core.Services.DamagePredictionResult$$WillBeOverkill`. Reconcilie 1357 s15 (u135 3 hits vs blackSmnBloodletter atk 2194,
    hp 3888) : blockAmount = 50%×2194 = 1097 ; list[0].rawMin = 5388 − 3×1097 = 2097 < 3888
    -> WillBeKill FALSE -> PossibleKill(50) ; pairUtility natif 164.94858612772077 = EXACT."""

    def create_effect_block_source_for_defense(self, defender_fixed_armor: int = 0,
                                               defender_attack: int = 0):
        chance = trait_var("Daemon", "daemonBlockChance")
        pct = trait_var("Daemon", "daemonBlockDamagePercentage")
        if not chance or pct is None:
            return None
        amount = int(int(defender_attack) * int(pct) / 100)   # PercentageOf(Attack courant, pct)
        if amount <= 0:
            return None
        return BlockSource(chance=int(chance), amount=amount,
                           block_id=self.block_source_id(int(chance)))


class PsychicFortressExtraBlockEffect(BaseEffect):
    """`PsychicFortress_ExtraBlockChanceEffect` (effet 0x3ef=1007, base `MultiValueStatEntryEffect` IdunBattle.Entities.Effects.Loki.PsychicFortress_ExtraBlockChanceEffect$$.ctor, passif PsychicFortress de Tigurius ultraTigurius) — source de BLOCK SUPPLEMENTAIRE posee
    par `IdunBattleLogic.Entities.Abilities.Active.Loki.PsychicFortressAbility$$CreateBehaviour` :
      `IdunBattleLogic.Entities.DSLFactory$$AddExtraBlockEffectToOwner(0x3ef, Direct(GetNumberConstant(0x2d=blockChance)),
                                  Direct(GetVariableForLevel(0x14=blockDmg)))
    = `AddMultiValueStatEntryEffectBehaviour(context@0x148, 0x3ef, [{statType 7=BLOCK_CHANCE: chance},
      {statType 8=BLOCK_DAMAGE: amount}])`. Entree separee de `GetMultiValueStat(7)`
    (`IdunBattle.Core.Services.DamageCalculations$$CalculateBlockChances`), ABSENTE du scalaire GetStat(7/8) -- meme canal ExtraBlock que
    BeastSlayer IdunBattleLogic.Entities.Abilities.Triggered.Loki.BeastSlayerAbility$$CreateAddBlockEffectBehaviour / AnvilShield (hors GetStat).
      - chance = `GetNumberConstant(0x2d)` = `blockChance` (CONSTANTE gameconfig = 50, NON scalee).
      - amount = `GetVariableForLevel(0x14)` = `blockDmg[ablvl]` (6->437, RARITY-SCALE :
        blockDmg in variablesAffectedByRarityBonus) x mult du porteur.
    => +50% chance de bloquer blockDmg[niveau] Damage. i2 : « ... an added Block with 50% chance to block
    437 Damage. » Pose ToOwner (context@0x148 = porteur, PAS de CreateTargetSelector custom sur
    l'ExtraBlockChanceEffect -> selecteur par defaut) -- INERTE tant que non materialise (fidelite-safe
    « present != applique », comme BeastSlayer) ; une fois present sur le defenseur, la source est
    consommee par `apply_random_block_damage`/le scenario block de la prediction. block_id = la chance
    (id natif dans failedList IdunBattle.Core.Services.DamageCalculations$$CalculateBlockChances, exclusion inter-coups apres 1er echec)."""

    def create_effect_block_source_for_defense(self, defender_fixed_armor: int = 0,
                                               defender_attack: int = 0):
        chance = ability_var("PsychicFortress", "blockChance", is_constant=True)   # GetNumberConstant 0x2d (=50)
        if not chance:
            return None
        lvl = self.ability_level if self.ability_level is not None else self.level
        amount = ability_var("PsychicFortress", "blockDmg", lvl,                   # GetVariableForLevel 0x14 (rarity-scale x mult)
                            multiplier_pct=self.ability_variables_multiplier)
        if not amount or int(amount) <= 0:
            return None
        return BlockSource(chance=int(chance), amount=int(amount),
                           block_id=self.block_source_id(int(chance)))


class FightingRetreatHitReductionEffect(BaseEffect):
    """`FightingRetreat_HitReductionEffect` (effet 1158 `FightingRetreatHitReduction`) — même debuff,
    axe COUPS (« They also have 1 fewer hits, to a minimum of one »).
    - hits IdunBattle.Entities.Effects.Loki.FightingRetreat_HitReductionEffect$$CreateEffectHitsBonusForAttack : `EffectBonus.ForAdditionWithMinimum(OwnerIsCaster, Multiply(MinusOne,
      ConfigConst(0x2c=hitsReduction=1)), min=Direct(1))` = **-1 coup, PLANCHER 1**. Le plancher est
      appliqué chez les consommateurs de hits (`max(1, …)`, cf. predict_validate)."""

    def create_effect_hits_bonus_for_attack(self, is_normal_attack: bool = True,
                                            att_ctx: "Mapping | None" = None) -> EffectBonus | None:
        # trigger natif = OwnerIsCaster SEUL (IdunBattle.Entities.Effects.Loki.FightingRetreat_HitReductionEffect$$CreateEffectHitsBonusForAttack, pas de IsNormalAttack) -> TOUTES les attaques.
        n = ability_var("FightingRetreat", "hitsReduction", is_constant=True)   # ConfigConst 0x2c (=1)
        return for_addition(True, -int(n)) if n else None


# TileId (terrain BC) qui HÉBERGE la LightCoverAbility (Abilities.Tiles.Loki IdunBattleLogic.Entities.Abilities.Tiles.Loki.LightCoverAbility$$CreateBehaviour) : les tuiles de
# couverture = DryBush. Source : empirique live (gqfc5mff6c) — une unité posée sur une tuile DryBush porte
# l'effet 'LightCover', absente ailleurs ; + `IdunBattleLogic.Entities.Abilities.Tiles.Loki.LightCoverAbility$$UnitsThatNeedEffect` = Units(coverPatch@0x148) =
# unités SUR la tuile porteuse de l'ability. Utilisé par le COMBAT pour le gate `AreEqual(coverPatch, target)`
# (IdunBattle.Entities.Effects.Loki.LightCoverEffect$$CreateEffectHitsBonusForAttack) = "la cible est sur SA tuile de cover". Pas un hardcode de debug : mapping terrain->ability.
LIGHT_COVER_TILE_ID = "DryBush"


class LightCoverEffect(BaseEffect):
    """`LightCoverEffect` — couverture légère (effet de TUILE posé par `LightCoverAbility`
    Abilities.Tiles.Loki, `IdunBattleLogic.Entities.Abilities.Tiles.Loki.LightCoverAbility$$UnitsThatNeedEffect = unités SUR les tuiles de couverture).
    - hits IdunBattle.Entities.Effects.Loki.LightCoverEffect$$CreateEffectHitsBonusForAttack : `EffectBonus.ForAdditionWithMinimum(OwnerIsTarget(tuiles égales) &
      !IsMeleeAttack, -ConfigConst(0x2c=hitsReduction), min=Direct(1))` = **-hitsReduction coups
      sur les attaques NON-mêlée reçues par le porteur, plancher 1**. Le trigger `OwnerIsTarget(tuiles
      égales)` = `AreEqual(Tiles(coverPatch@0x148), Tiles(target@0x178))` = **la cible se tient sur LA
      tuile de cover** à laquelle l'effet est lié (approx. fidèle du port : la cible est sur UNE tuile
      DryBush, cf. `defender_on_cover`).
    MAGNITUDE : `globalValues.lightCoverHitReduction` = 2 (LightCoverAbility = ability de TUILE,
    absente de `units.abilities` — sa config vit dans les valeurs globales).
    GROUND TRUTH step-13 seed777 (trace AllMods, u90→u84 porteur LightCover) : ranged 4→2 coups
    partout, mêlée dist 1 → 4 coups (gate !IsMeleeAttack) — natif dMin/dMax reproduits exacts.

    ⚠ GATE compute-time `defender_on_cover` (A3, #113) : le natif RE-vérifie `AreEqual(coverPatch, target)`
    À CHAQUE calcul d'attaque — l'effet ne réduit PAS si la cible a quitté la tuile de cover. En PRÉDICTION
    (single-step, cible immobile) la présence de l'effet (IsActive live) ⟺ sur-cover → gate no-op (on passe
    `defender_on_cover=None` = "inconnu" → applique sur présence). En RUNNER-SIM (multi-step) l'effet peut
    PERSISTER après un move hors-cover (tant que B1 ne le retire pas) → le COMBAT passe
    `defender_on_cover = (terrain de la cible == DryBush)` pour ne PAS sur-appliquer un effet périmé."""

    def create_effect_hits_malus_for_defense(self, is_melee: bool | None = None,
                                             damage_profile: str | None = None,
                                             defender_on_cover: bool | None = None,
                                             dist: int | None = None) -> EffectBonus | None:
        if is_melee:                        # trigger natif = !IsMeleeAttack (IdunBattle.Entities.Effects.Loki.LightCoverEffect$$CreateEffectHitsBonusForAttack)
            return None
        if defender_on_cover is False:      # AreEqual(coverPatch, target) FAUX : cible hors tuile de cover
            return None                     # (None = inconnu -> on applique sur présence, cas prédiction)
        n = global_value("lightCoverHitReduction")   # miroir du ConfigConst 0x2c (=2)
        return for_addition(True, -int(n)) if n else None


class ParryEffect(BaseEffect):
    """`ParryEffect` (effet `Parry_ReduceHits`, trait Parry — i2 : « reduces incoming melee multi-hit
    attacks by 1 hit, to a minimum of 1 »).
    - hits IdunBattle.Entities.Effects.Loki.ParryEffect$$CreateEffectHitsBonusForAttack : `EffectBonus.ForAdditionWithMinimum(OwnerIsTarget & IsMeleeAttack,
      -ConfigConst(0x2c=hitsReduction), min=Direct(1))` = **-1 coup MÊLÉE reçu, plancher 1**
      (jumeau mêlée de LightCover). MAGNITUDE : `traitVariables.parryHitReduction` = 1.
    GROUND TRUTH step-6 seed777 (trace AllMods, u86→u94 porteur Parry) : mêlée dist 1 = 4 coups
    vs ranged = 5 (base 3 + PowerTrip 1 + MasterAnnihilator 1) — natif reproduit exact."""

    def create_effect_hits_malus_for_defense(self, is_melee: bool | None = None,
                                             damage_profile: str | None = None,
                                             defender_on_cover: bool | None = None,
                                             dist: int | None = None) -> EffectBonus | None:
        if not is_melee:                    # trigger natif = IsMeleeAttack (IdunBattle.Entities.Effects.Loki.ParryEffect$$CreateEffectHitsBonusForAttack)
            return None
        n = trait_var("Parry", "parryHitReduction")  # miroir du ConfigConst 0x2c (=1)
        return for_addition(True, -int(n)) if n else None


class DiminutiveHitReductionEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.Diminutive_HitReductionEffect$$CreateEffectHitsBonusForAttack (trait `Diminutive`
    0x408=1032, x3 npc + summon `orksGrot`) — jumeau INCONDITIONNEL de Parry/Camouflage cote DEFENSE.
    i2 : << Due to its tiny stature, this unit reduces incoming multi-hit attacks by {hitsReduction}
    hit, to a minimum of 1. >>

    Natif IdunBattle.Entities.Effects.Loki.Diminutive_HitReductionEffect$$CreateEffectHitsBonusForAttack = `ForAdditionWithMinimum(OwnerIsTarget, Direct(-ConfigConst(0x2c=hitsReduction)),
    min=Direct(1))` — structure IDENTIQUE a `IdunBattle.Entities.Effects.Loki.BigTargetAdjacentEffect$$CreateEffectHitsBonusForAttack (memes slots inlines : valeur, minimum, trigger) **MOINS le noeud `IsRangedAttack`** :
    le trigger est `OwnerIsTarget` SEUL -> la reduction s'applique a TOUTE attaque recue (melee ET
    ranged), contrairement a Parry (melee-only IdunBattle.Entities.Effects.Loki.ParryEffect$$CreateEffectHitsBonusForAttack) et Camouflage (ranged-only IdunBattleLogic.Entities.Abilities.Triggered.Loki.Camouflage_HitReductionEffect$$CreateEffectHitsBonusForAttack).
    Le plancher `min=Direct(1)` est applique chez les consommateurs de coups (`max(1, ...)`), comme
    pour Parry/LightCover/Camouflage — d'ou l'absence de clamp ici.

    CHAINE trait -> effet (mirror #73 Terrifying) : `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Trait$$GetTriggeredAbility` mappe le
    trait `Diminutive` -> `TriggeredAbilityType.Diminutive` 0x43f=1087 ; `AddTraitOperation.
    IdunBattle.Operations.AddTraitOperation$$AddDerivedAbilities` ajoute `DiminutiveAbility` IdunBattleLogic.Entities.Abilities.Triggered.Loki.DiminutiveAbility$$.ctor (=
    `AOwnerEffectSpecificTriggeredAbility(0x43f)` IdunBattle.Entities.Abilities.AOwnerEffectSpecificTriggeredAbility$$.ctor, enregistree par `AbilitiesDatabase.
    <InitializeTriggeredAbilities>b__28_89` IdunBattle.Core.Services.AbilitiesDatabase.u003Cu003Ec$$u003CInitializeTriggeredAbilitiesu003Eb__28_89+0x42) ; son `IdunBattle.Entities.Abilities.AOwnerEffectSpecificTriggeredAbility$$CreateTrigger` =
    `OnOwnerSpecificAbilityInit(0x43f)` -> a l'init du porteur, la behaviour pose l'owner-effect
    `Diminutive_HitReduction` (`Diminutive_HitReductionEffect..IdunBattle.Entities.Effects.Loki.Diminutive_HitReductionEffect$$.ctor, enregistre par
    `EffectsDatabase.<InitializeEffects>b__14_108` IdunBattle.Core.Services.EffectsDatabase.u003Cu003Ec$$u003CInitializeEffectsu003Eb__14_108+0x36).

    MAGNITUDE : `ConfigConst 0x2c` = MEME slot que `parryHitReduction` / `camouflageHitReduction_1`
    (l'ability Diminutive n'existe pas dans `units.abilities` -> le slot numberConstant du config
    Loki-triggered est seede depuis les vars de trait) = `traitVariables.diminutiveHitReduction` = 1."""

    def create_effect_hits_malus_for_defense(self, is_melee: bool | None = None,
                                             damage_profile: str | None = None,
                                             defender_on_cover: bool | None = None,
                                             dist: int | None = None) -> EffectBonus | None:
        # trigger natif = OwnerIsTarget SEUL (IdunBattle.Entities.Effects.Loki.Diminutive_HitReductionEffect$$CreateEffectHitsBonusForAttack) : AUCUN gate melee/ranged, aucun gate profil.
        n = trait_var("Diminutive", "diminutiveHitReduction")   # ConfigConst 0x2c (=1)
        return for_addition(True, -int(n)) if n else None


class CamouflageHitReductionEffect(BaseEffect):
    """`IdunBattleLogic.Entities.Abilities.Triggered.Loki.Camouflage_HitReductionEffect$$CreateEffectHitsBonusForAttack (effet 0x46e=1134
    'Camouflage_HitReduction', trait Camouflage 1037, ex. admecRuststalker Exitor-Rho) - jumeau RANGED
    de LightCover/Parry cote DEFENSE : canal `CreateEffectHitsBonusForAttack` (slot 0x23, trigger
    `OwnerIsTarget & IsRangedAttack`), plancher min 1. Consomme par la MEME boucle native
    `IdunBattle.Operations.AdditionalHitsFromEffects$$GetAdditionalHitsFromEffectsInternal` (slot 0x23 sur chaque
    effet), partagee prediction/combat via `IdunBattle.Entities.Formulas.AttackHitsWithModifiersFormula$$Calculate` (PAS
    predOptimistic : la reduction de COUPS est foldee dans le nb de coups, cote prediction ET combat).
    i2 : << Ranged attacks against this character score -1 hit. This increases to -2 hits if this
    character is more than 2 hexes away from the attacker or to -3 hits when in Tall Grass. Attackers
    always score at least 1 hit. >>

    Natif = `ForAdditionWithMinimum(OwnerIsTarget & IsRangedAttack, amount, min=Direct(1))` avec
      amount = ConditionalAmount(
        HasTile(TilesWithTriggeredAbility(Tiles(Target), 0x39=57=DryBushFireSpread)),   # cible sur DryBush
        Direct(-const(0x4d)),                                                            # << Tall Grass >>
        ConditionalAmount(AmountIsGreater(AverageDistance(Caster,Target), Direct(2)),   # dist > 2
                          Direct(-const(0x4b)),
                          Direct(-const(0x2c))))                                         # dist <= 2 (melee)
    Constantes GetNumberConstant(config, key) = traitVariables (l'ability Camouflage n'existe PAS dans
    gameconfig.abilities -> les slots numberConstant 0x2c/0x4b/0x4d du config Loki-triggered sont seedes
    depuis les vars de trait) : 0x2c=camouflageHitReduction_1=1, 0x4b=camouflageHitReduction_2=2,
    0x4d=camouflageHitReduction_3=3 (coherent i2 -1/-2/-3).

    GATE tuile << Tall Grass >> = MEME tuile DryBush que LightCover : la triggered ability 57
    (DryBushFireSpread) coexiste avec LightCoverAbility sur la tuile DryBush (le jeu l'affiche << Tall
    Grass >>) -> on REUTILISE le flag `defender_on_cover` (True = cible sur DryBush, deja calcule cote
    combat depuis le terrain). En PREDICTION (defender_on_cover None, terrain non threade) la branche -3
    est inaccessible -> repli distance (FLAG validator : prediction sur DryBush sous-predit -3 en -2/-1 ;
    combler = threader le terrain au board de prediction, comme le combat). Distance = AverageDistance(
    Caster,Target) en hex, calculee dans la formule depuis le board (dist>2 -> -2, sinon -1 ; multi-tuile
    approxime par hexgeo.distance mono-tuile - FLAG)."""

    def create_effect_hits_malus_for_defense(self, is_melee: bool | None = None,
                                             damage_profile: str | None = None,
                                             defender_on_cover: bool | None = None,
                                             dist: int | None = None) -> EffectBonus | None:
        # #122 : trigger `OwnerIsTarget & IsRangedAttack` (LU au decompile) ->
        # `BattleQuery$$IsRangedAttack`, VRAI pour le SEUL `attackRangeType = Ranged` (et pour `Normal`
        # hors-melee). `is_melee = None` = nature NON DECLAREE (`rangeType 0`) : le natif y rend FAUX
        # pour les DEUX predicats -> aucune reduction. La truthiness (`if is_melee:`) traitait `None`
        # comme du ranged. No-op strict pour tout appelant qui passe un booleen.
        if is_melee is not False:             # trigger IsRangedAttack (melee OU nature inconnue -> rien)
            return None
        if defender_on_cover is True:         # HasTile(TilesWithTriggeredAbility(Target, 57)) = sur DryBush
            n = trait_var("Camouflage", "camouflageHitReduction_3")   # numberConstant 0x4d (=3)
        elif dist is not None and dist > 2:   # AverageDistance(Caster,Target) > 2
            n = trait_var("Camouflage", "camouflageHitReduction_2")   # numberConstant 0x4b (=2)
        else:                                 # dist <= 2 (portee melee) OU distance inconnue
            n = trait_var("Camouflage", "camouflageHitReduction_1")   # numberConstant 0x2c (=1)
        return for_addition(True, -int(n)) if n else None


class MasterAnnihilatorAdditionalHitEffect(BaseEffect):
    """`MasterAnnihilator_AdditionalHitEffect` (effet `MasterAnnihilator_extraHit` — DEBUFF posé par
    Vitruvius sur SA cible d'attaque normale ; i2 : « Attacks by any friendly unit against the
    affected enemy score an additional hit, except attacks that deal Psychic Damage »).
    - hits IdunBattle.Entities.Effects.Loki.MasterAnnihilator_AdditionalHitEffect$$CreateAdditionalHits : `EffectAdditionalHits.Create(OwnerIsTarget & !AreEqual(
      CurrentAttackDamageProfile, 0xd=Psychic), count=ConfigConst(0x2f nrOfHits=1),
      dmg=FirstHitInCurrentAttackDamageRange capé ConfigVar(0xd maxDmg))` = **+1 coup reçu par le
      porteur (attaques non-Psychic)**. Les attaquants = ennemis du porteur = alliés du poseur (le
      gate « friendly unit » de l'i2 est structurel, pas dans le trigger).
    ⚠ CAP du coup bonus (dmg <= maxDmg[lvl] ex. 5456) non modélisé (per-coup observé << cap) — TODO.
    GROUND TRUTH step-6 seed777 : u86→u94 ranged = 5 coups (3 arme + 1 PowerTrip + 1 MA) vs 4 sur
    les cibles non marquées (88/96)."""

    def create_effect_hits_malus_for_defense(self, is_melee: bool | None = None,
                                             damage_profile: str | None = None,
                                             defender_on_cover: bool | None = None,
                                             dist: int | None = None) -> EffectBonus | None:
        if damage_profile == "Psychic":     # !AreEqual(profil, 0xd=Psychic) (IdunBattle.Entities.Effects.Loki.MasterAnnihilator_AdditionalHitEffect$$CreateAdditionalHits)
            return None
        n = ability_var("MasterAnnihilator", "nrOfHits", is_constant=True)   # ConfigConst 0x2f (=1)
        return for_addition(True, int(n)) if n else None


# Cle du sac `PersistentDataComponent` armee par `IdunBattleLogic.Entities.Abilities.Triggered.Loki.LetTheGalaxyBurnAbility$$CreateBehaviour`
# (`SetPersistentData(AbilityOrEffect(0x5ca=1482), Self@0x148, Get(<champ statique IdunBattleLogic.Entities.Abilities.Triggered.Loki.LetTheGalaxyBurnAbility$$.cctor>),
# Direct(1)@0xc0)`) et lue par `IdunBattleLogic.Entities.DSLFactory$$IsPersistentData` dans le gate de
# `IdunBattle.Entities.Effects.Loki.LetTheGalaxyBurnEffect$$CreateAdditionalHits`. Le tuple = la cle composite native
# (AbilityOrEffect, nom de la donnee) ; PARTAGEE entre le poseur (runner/.../let_the_galaxy_burn.py),
# le nettoyeur (Reset) et ce lecteur -> une seule source de verite.
LET_THE_GALAXY_BURN_PERSISTENT_KEY = (1482, "LetTheGalaxyBurn")


class LetTheGalaxyBurnEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.LetTheGalaxyBurnEffect` (effet 0x5c5=1477, nom capte
    « LetTheGalaxyBurn ») — owner-effect AUTO-PORTE par les 5 heros Black Legion qui ont le TRAIT
    `LetTheGalaxyBurn` (0x422=1058 : blackAbaddon, blackHaarken, blackObliterator, blackPossession,
    blackTerminator). IdunBattle.Entities.Effects.Loki.LetTheGalaxyBurnEffect$$.ctor` = `BaseEffect(AbilityOrEffect(0x5ca=1482), 1, 0)` : l'EffectSource
    est l'ability DECLENCHEE 1482 (meme patron auto-porteur qu'`InfernalPacts_AdditionalHitsEffect`
    IdunBattle.Entities.Effects.Loki.InfernalPacts_AdditionalHitsEffect$$.ctor — aucune classe `Ability` ne le POSE, il est materialise a l'init de l'unite).

    ⚠ HOMONYMIE : `ActiveAbilityType.Waaagh` vaut AUSSI 1058 — les espaces d'enum (`UnitTrait`,
    `TriggeredAbilityType`, `ActiveAbilityType`, `EffectType`) sont INDEPENDANTS. Ici 1058 = **UnitTrait**.

    ## Canal (RE, decompile ghidra build gqfc5mff6c)
    `IdunBattle.Entities.Effects.Loki.LetTheGalaxyBurnEffect$$CreateAdditionalHits` -> `IdunBattle.Entities.Effects.EffectAdditionalHits$$Create` avec :
      - condition = `get_OwnerIsCaster & ( TargetHasTileEffect | IsPersistentData(0x5ca, Self@0x148,
        Get(<statique>)) )`, ou `IdunBattleLogic.Entities.Abilities.Triggered.Loki.LetTheGalaxyBurnAbility$$TargetHasTileEffect` = `HasTileStatusEffect(Targets@0x190)`
        (IdunBattleLogic.Entities.DSLFactory$$HasTileStatusEffect) — **GENERIQUE** : n'importe quel status-effect de tuile, pas un type precis ;
      - degat  = `FirstHitInCurrentAttackDamageRange` (param_3 ET param_8 : roll ET display) ;
      - profil = **-1** (`CONCAT44(0,0xffffffff)` -> `Nullable<DamageProfileType>` NULL) ;
      - count  = **noeud NULL** (param_6=0, la ou `MasterAnnihilator_AdditionalHitEffect
        .IdunBattle.Entities.Effects.Loki.MasterAnnihilator_AdditionalHitEffect$$CreateAdditionalHits` passe `ConfigConst(0x2f=nrOfHits)`) -> defaut **1** ;
      - cap    = NULL (param_9=0 ; MasterAnnihilator, lui, cape a `ConfigVar(0xd=maxDmg)`).
    => coup additionnel a degat/profil de l'ARME = **+1 coup ordinaire** : MEME canal que
    MasterAnnihilator, cote ATTAQUANT (`OwnerIsCaster`) au lieu de defenseur (`OwnerIsTarget`).

    ## Les DEUX branches du gate (exclusives par construction)
    Le trigger de POSE `IdunBattleLogic.Entities.Abilities.Triggered.Loki.LetTheGalaxyBurnAbility$$CreateTrigger` =
    `On(5=PreAttack) & OwnerIsCaster & Maybe(ConfigConst 0x2a) & !HasTileStatusEffect(Targets@0x190)` :
    il n'arme le flag QUE si la cible n'est PAS deja sur une tuile a effet. Donc :
      A. cible sur tuile SANS status-effect -> seul le roll `Maybe(LetTheGalaxyBurnChancePct=33)` arme ;
      B. cible sur tuile AVEC status-effect -> `TargetHasTileEffect` VRAI -> +1 **systematique**, et
         AUCUNE pose (le flag reste vide).

    GROUND TRUTH LIVE (probe_84_ltgb_chance.py, blackTerminator « Angrax » vs bloodSanguinary, MC1_67,
    8 runners) : branche A n=73 -> base 4 coups, 25 attaques a 5 coups = **34.2 %** (== 33 % config) ;
    branche B n=23 -> **23/23 a 5 coups** (100 %). Le +1 est parfaitement correle a l'apparition de
    `DespoiledGround` sur la tuile de la cible (= le volet 2 du meme kit, pose par
    `IdunBattleLogic.Entities.Abilities.Triggered.Loki.LetTheGalaxyBurn_ResetAbility$$CreateBehaviour`, `AddEffect(0x5c4=1476)`).
    Corrobore le confound deja documente sur `test_bringer_of_despair_live.py` (Angrax 5 = 4 + 1).

    ## Contexte requis (`att_ctx`)
    Le gate a besoin de la CIBLE, que le canal `hits` ne portait pas : `att_ctx` = le `board` de
    `AttackHitsWithModifiersFormula` (`services/attack_hits_formula.py`) enrichi de
    `tile_effects_by_pos` (tileMeta -> `HasTileStatusEffect`) et `persistent_data` (les cles posees sur
    l'ATTAQUANT -> `IsPersistentData`). Contexte ABSENT (None) -> les deux branches sont fausses ->
    aucune contribution (degradation fidele « present != applique », = l'etat PREDICTION mesure #62/#65 :
    contribution native 0 tant que la cible n'est pas sur un hex-effect)."""

    def create_effect_hits_bonus_for_attack(self, is_normal_attack: bool = True,
                                            att_ctx: "Mapping | None" = None) -> EffectBonus | None:
        c = att_ctx or {}
        # `IdunBattleLogic.Entities.Abilities.Triggered.Loki.LetTheGalaxyBurnAbility$$TargetHasTileEffect` = `HasTileStatusEffect(Targets@0x190)` — GENERIQUE au sens
        # « n'importe LEQUEL des status de tuile », PAS « n'importe quel effet porte par la tuile » :
        # `IdunBattle.Entities.Triggers.HasTileStatusEffectTrigger$$ShouldTrigger` appelle
        # `IdunBattle.Entities.TileExtensions$$HasTileStatusEffect`, qui ne retient que les EffectType
        # du set `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Effect$$IsTileStatusEffect
        # (Darkness/Fire/Ice/Contaminated/DespoiledGround). Une tuile porte AUSSI des effets non-status
        # (Swamp : `BlockEnteringUnits` + `Thorns_DefenseReduction` ; `Melta_ExtraDmg`) qui ne doivent
        # PAS armer ce +1 — invisible tant que le canal offline etait vide, reel depuis le seed des
        # effets de tuile (#102). `tile_effects_by_pos` = tileMeta (effets DYNAMIQUES de la tuile) ;
        # le terrain statique (DryBush -> LightCover, pose sur les UNITES) n'en fait PAS partie.
        tfx, tp = c.get("tile_effects_by_pos"), c.get("t_pos")
        on_tile_fx = bool(set((tfx or {}).get(tuple(tp)) or ()) & TILE_STATUS_EFFECT_NAMES) \
            if (tfx is not None and tp is not None) else False
        # `IdunBattleLogic.Entities.DSLFactory$$IsPersistentData(0x5ca, Self@0x148, Get(<statique>)) — flag intra-attaque arme par
        # le trigger de pose (33%) et efface en fin d'attaque par le Reset IdunBattleLogic.Entities.Abilities.Triggered.Loki.LetTheGalaxyBurn_ResetAbility$$CreateBehaviour.
        armed = LET_THE_GALAXY_BURN_PERSISTENT_KEY in (c.get("persistent_data") or ())
        if not (on_tile_fx or armed):
            return None
        # count = noeud NULL IdunBattle.Entities.Effects.Loki.LetTheGalaxyBurnEffect$$CreateAdditionalHits -> 1 coup (defaut natif ; GROUND TRUTH live 4 -> 5).
        return for_addition(True, 1)


class BigTargetAdjacentEffect(BaseEffect):
    """`BigTargetAdjacentEffect` — AURA du trait BigTarget (i2 : « Adjacent friendly units receive
    -1 hit from ranged attacks, to a minimum of 1 »). L'effet est POSSÉDÉ par le porteur BigTarget
    (capté dans SA liste d'effets) ; ses bénéficiaires = les ALLIÉS ring-1 HEX désignés dynamiquement
    (TargetSelector IdunBattle.Entities.Effects.Loki.BigTargetAdjacentEffect$$CreateTargetSelector, refresh IdunBattle.Entities.Effects.Loki.BigTargetAdjacentEffect$$GetRefreshTriggers) — PAS le porteur lui-même (GROUND TRUTH step-13
    seed777 : u86 porteur = 4 coups pleins ; u80 allié adjacent = 3 coups).
    - hits IdunBattle.Entities.Effects.Loki.BigTargetAdjacentEffect$$CreateEffectHitsBonusForAttack : `ForAdditionWithMinimum(OwnerIsTarget & IsRangedAttack, Direct(-1),
      min=Direct(1))` — valeur -1 codée dans le natif (pas de config).
    Canal AURA (le porteur n'est pas la cible de l'attaque) : ctx fourni par l'agrégateur
    `aura_hits_malus_for_defense` = {owner_id/pos/team, tgt_id, t_pos, tgt_team, is_melee}."""

    def create_aura_hits_malus_for_defense(self, ctx: Mapping | None = None) -> EffectBonus | None:
        c = ctx or {}
        # #122 : `OwnerIsTarget & IsRangedAttack` (LU) -> `BattleQuery$$IsRangedAttack` = VRAI pour le
        # seul `attackRangeType = Ranged`. `is_melee = None` (nature non declaree, `rangeType 0`) =
        # les DEUX predicats faux -> pas d'aura. No-op strict pour un appelant qui passe un booleen.
        if c.get("is_melee") is not False or c.get("owner_id") == c.get("tgt_id"):
            return None
        if c.get("owner_team") is None or c.get("owner_team") != c.get("tgt_team"):
            return None                     # bénéficiaires = alliés du porteur uniquement
        op, tp = c.get("owner_pos"), c.get("t_pos")
        if not op or not tp:
            return None
        import hexgeo                       # ring-1 HEX (parité validée vs boardGraph)
        if hexgeo.distance(op, tp) != 1:
            return None
        return for_addition(True, -1)       # Direct(-1) IdunBattle.Entities.Effects.Loki.BigTargetAdjacentEffect$$CreateEffectHitsBonusForAttack


class AstartesBannerExtraHitEffect(BaseEffect):
    """`AstartesBanner_AdditionalHitsEffect` (effet capté "AstartesBanner_ExtraHit", passif AstartesBanner
    ex. templAncient) — AURA +coups : les ALLIÉS dans le rayon 2 du porteur marquent +extraHits coups avec
    leurs attaques MÊLÉE (i2 : « Other friendly units within 2 hexes score an additional hit with their melee
    attacks. This additional hit can deal a maximum of 5456 Damage »). L'effet est POSSÉDÉ par le PORTEUR
    (capté dans SA liste d'effets, comme BigTarget) ; bénéficiaires = SurroundingFriends (exclut self).
    - hits `IdunBattle.Entities.Effects.Loki.AstartesBanner_AdditionalHitsEffect$$CreateAdditionalHits` : `ForAddition(OwnerIsCaster & IsMeleeAttack, ConfigVar(0xd=
      extraHits, sourceAbilityState))` + cap dégât 5456 sur le coup ajouté (FirstHitInCurrentAttackDamageRange
      + max). ⚠ CAP 5456 du coup ajouté NON porté (refine : ne mord que si dégât/coup > 5456 ; le +1 coup
      COUNT est l'effet principal, GROUND TRUTH ultraApothecary 1->2 @seed999 via AstartesBanner de templAncient).
    - cible `IdunBattle.Entities.Effects.Loki.AstartesBanner_AdditionalHitsEffect$$CreateTargetSelector` : `SurroundingFriends(range=ConfigConst 0x16=2, exclut self)`.
    Canal AURA côté SOURCE (`create_aura_hits_bonus_for_attack`, agrégé par `aura_hits_bonus_for_attack`),
    SYMÉTRIQUE de BigTarget (défenseur). Magnitude `extraHits` indexée sur le niveau d'ability du PORTEUR
    (`GetAbilityState` -> `self.ability_level`). Ctx aura = {owner_id/pos/team, att_id/att_pos/att_team, is_melee}."""

    def create_aura_hits_bonus_for_attack(self, ctx: Mapping | None = None) -> EffectBonus | None:
        c = ctx or {}
        if not c.get("is_melee"):                          # IsMeleeAttack
            return None
        if c.get("att_id") == c.get("owner_id"):           # SurroundingFriends exclut le porteur (self)
            return None
        if c.get("owner_team") is None or c.get("owner_team") != c.get("att_team"):
            return None                                    # bénéficiaires = ALLIÉS du porteur
        op, ap = c.get("owner_pos"), c.get("att_pos")
        if not op or not ap:
            return None
        import hexgeo
        rng = ability_var("AstartesBanner", "range", is_constant=True)   # ConfigConst 0x16 (=2)
        if hexgeo.distance(op, ap) > int(rng if rng else 2):             # SurroundingFriends(range)
            return None
        n = ability_var("AstartesBanner", "extraHits", is_constant=True)  # constante extraHits (=1)
        return for_addition(True, int(n)) if n else None


class SagaOfTheWarriorBornOwnerEffect(BaseEffect):
    """`SagaOfTheWarriorBorn_Owner` (effet 0x4c7=1223, `spaceBlackmane` <<Ragnar>>) — axe COUPS,
    gate `IsCharging`. MIRROR de
    `IdunBattle.Entities.Effects.Loki.SagaOfTheWarriorBorn_OwnerEffect$$CreateEffectHitsBonusForAttack` :

        EffectBonus.ForAddition( get_OwnerIsCaster & IsCharging(owner@0x148, target@0x178),
                                 ConfigVar(0x13 = extraHits, GetAbilityState(effect), config@+0x60),
                                 <AbilityOrEffect recopie de effect+0x14..+0x2c> )

    DEUX noeuds trigger, pas trois : **aucun** `IsNormalAttack`, **aucun** `IsMeleeAttack`. Le bonus
    vaut donc pour TOUTE attaque du porteur en charge (Ragnar n'a de fait qu'un vecteur d'attaque :
    son arme normale, 7 coups Chain — son active `WarHowl` 1106 est un buff).
    `get_OwnerIsCaster` est deja porte par le canal : ces effets ne sont interroges que sur
    l'ATTAQUANT (`hits_bonus_from_effects(attacker_effects, ...)`).

    GATE — foyer PARTAGE, aucun predicat re-derive ici : `effects/base.py::is_charging_attack`
    lit la cle `att_ctx["is_charging"]`, calculee par `engine/battle_query.py::is_charging`
    (`AreEntitiesAdjacent(caster, target) && UnitComponent.ChargedUnitIds@+0x190.Contains(target.Id)`) --
    cote COMBAT dans `runner/damage_model.py::build_hits_board` (liste REELLE du `UnitComponent`),
    cote PREDICTION dans `playbook/prediction/normal_attack.py` (charges acquises UNION ce que le pas
    CANDIDAT ajouterait). C'est le MEME foyer que le canal degat de `case-r32`.
    ⚠ Ce n'est PAS `HasFlag(UnitFlag.Moved)` : `MoveUnitOperation$$UpdateCharging` n'inscrit que les
    unites devenues NOUVELLEMENT adjacentes, donc un caster qui bouge vers une cible DEJA adjacente
    a `Moved` VRAI et `IsCharging` FAUX. MESURE live (`test_r33_saga_charge_hits_live.py`, Ragnar
    rank 17) : regime CHARGE = **10 coups** natifs (7 arme + 3), regime STEP_ADJACENT = **7**. Un
    port gate par `has_moved` rendrait 10 dans les DEUX.

    MAGNITUDE = `ConfigVar(0x13)` = la variable `extraHits` de l'ability `SagaOfTheWarriorBorn`,
    indexee par l'`AbilityState` de l'effet (`IdunBattle.Entities.Effects.BaseEffect$$GetAbilityState`)
    = le niveau de l'ability SOURCE sur le porteur. `SagaOfTheWarriorBorn` est le PASSIF de Ragnar ->
    `ability_level` (fallback `level`, comme `PowerTrip_IgnoreArmor`). `extraHits` n'est PAS dans
    `variablesAffectedByRarityBonus` (seule `extraCritDmg` l'est) -> le multiplier ne la scale pas ;
    il est passe quand meme pour rester le calque strict de `ConfigVar`. Table : `[1]x17, [2]x18,
    [3]x30` -> niveau 50 (rank 17) = **3**, ce que dit l'i2 (« scores 3 additional hits »).

    RESIDU NOMME (`N14`) : la face CRIT du MEME effet
    (`…SagaOfTheWarriorBorn_OwnerEffect$$CreateCritDamageBonus` = meme trigger, `ConfigVar(0x42 =
    extraCritDmg)`) n'est PAS portee — `BaseEffect.create_effect_crit_damage_bonus_for_attack()` n'a
    aucun parametre de contexte, donc elle ne pourrait pas LIRE ce gate et s'appliquerait
    inconditionnellement. Poser la face dans cet etat serait plus faux que de ne pas la poser.
    HORS PERIMETRE, nomme : `SagaOfTheWarriorBorn_OtherSpaceWolves` (1224) est un effet SEPARE, pose
    par `IdunBattleLogic.Entities.Abilities.Triggered.Loki.SagaOfTheWarriorBorn_KillAbility$$CreateBehaviour`
    sur les amis Space Wolves apres un kill de Character."""

    def create_effect_hits_bonus_for_attack(self, is_normal_attack: bool = True,
                                            att_ctx: "Mapping | None" = None) -> EffectBonus | None:
        # IsCharging (IdunBattleLogic.Entities.DSLFactory$$IsCharging -> BattleQuery$$IsCharging).
        # PAS de gate is_normal_attack / is_melee : le decompile n'a QUE ces deux noeuds.
        if not is_charging_attack(att_ctx):
            return None
        lvl = self.ability_level if self.ability_level is not None else self.level
        n = ability_var("SagaOfTheWarriorBorn", "extraHits", lvl,
                        multiplier_pct=self.ability_variables_multiplier)   # ConfigVar 0x13
        return for_addition(True, int(n)) if n else None


class PowerTripFullHealthEffect(BaseEffect):
    """`PowerTrip_FullHealthEffect` — axe COUPS (hits), actif SSI PV pleins.
    - hits IdunBattle.Entities.Effects.Loki.PowerTrip_FullHealthEffect$$CreateEffectHitsBonusForAttack : `ForAddition(ConfigConst key 0x2b)` = constante `extraHit` de l'ability PowerTrip (=1).
    - condition IdunBattle.Entities.Effects.Loki.PowerTrip_FullHealthEffect$$CreateActiveCondition : `!IsDamaged` (hp == max).
    MAGNITUDE résolue : `gameconfig.ability('PowerTrip').constants['extraHit']` = 1 → +1 coup quand PV pleins."""

    def create_effect_hits_bonus_for_attack(self, is_normal_attack: bool = True,
                                            att_ctx: "Mapping | None" = None) -> EffectBonus | None:
        # trigger natif IdunBattle.Entities.Effects.Loki.PowerTrip_FullHealthEffect$$CreateEffectHitsBonusForAttack = `IsNormalAttack & OwnerIsCaster` -> ATTAQUE NORMALE SEULEMENT
        # (l'appliquer aux spéciales sur-prédisait DakkaDakkaDakka -> régression steps 6/13).
        if not is_normal_attack:
            return None
        n = ability_var("PowerTrip", "extraHit", is_constant=True)   # key 0x2b → constante extraHit (=1)
        return for_addition(True, n) if n else None

    def is_active(self, unit_state: Mapping | None = None) -> bool:
        s = unit_state or {}
        hp, mx = s.get("hp"), s.get("max_hp")
        if hp is None or mx is None:        # max_hp non capté → ne pas masquer l'effet à tort
            return True
        return hp >= mx


class PowerTripIgnoreArmorEffect(BaseEffect):
    """`PowerTrip_IgnoreArmorEffect` — « Normal attacks ignore X Armour » = axe PÉNÉTRATION.
    ⚠ Le natif `IdunBattle.Entities.Effects.Loki.PowerTrip_IgnoreArmorEffect$$CreateEffectDamageBonusForAttack = NO-OP
    (EffectBonus condition-seule, valeur 0) ; la pénétration est en fait bâtie DIRECTEMENT dans
    `IdunBattle.Core.Services.DamageCalculations$$CalculateAttackerModifiersForPrediction (lit la config PowerTrip de l'attaquant), pas
    portée par l'effet — pattern d'exploitation directe (cf. §17.17). On l'attribue ICI (l'effet
    représente la présence de PowerTrip ⇒ sa présence GATE correctement la pénétration : normal attack,
    owner=caster). Magnitude = `armorIgnored[level] × AbilityVariablesMultiplierPercentage/100` arrondi
    (§17.21, var flaggée `variablesAffectedByRarityBonus`). VÉRIFIÉ live u90 : 277 × 1.8 = round(498.6)
    = 499 = pénétration @0x28 attaquant ⇒ per-bout u90→u86 [341,1265], ×6 = oracle [2048,7592].
    `armorReduction` (full-health) = axe SÉPARÉ (debuff stateful de la stat FixedArmor cible, hors
    prédiction — la prédiction lit l'armure courante) → non porté ici (cf. PowerTrip_OnAttackAbility)."""

    def get_armor_penetration(self, is_normal_attack: bool = True) -> int | None:
        # Gate ATTAQUE NORMALE (i2 : « Normal attacks ignore X Armour ») — GROUND TRUTH step-13 :
        # DakkaDakkaDakka (spéciale, même porteur u90) per-coup natif 404/728 vs 78 = armure PLEINE
        # (2208), la pénétration 499 ne s'applique qu'au normal (per-coup 416/1598).
        if not is_normal_attack:
            return None
        # armorIgnored indexé par le niveau de l'ABILITY (passive, =50), PAS le stack level (=1), scalé par
        # le multiplier de l'unité. `ability_level` seedé depuis l'unité ; fallback `level` si absent.
        lvl = self.ability_level if self.ability_level is not None else self.level
        return ability_var("PowerTrip", "armorIgnored", lvl,
                           multiplier_pct=self.ability_variables_multiplier)


class KanOpenerEffect(BaseEffect):
    """`KanOpenerEffect` (triggered) — `IdunBattleLogic.Entities.Abilities.Triggered.Loki.KanOpenerEffect$$IgnoreArmor = `ConfigVar(key 0x40)` = pénétration
    d'armure per-niveau (axe armure, contrairement à PowerTrip dont la réduction est stateful on-attack).
    ⚠ KillaKan n'a PAS KanOpener (kit = PowerTrip) ; clé 0x40 → nom var gameconfig non résolu pour les
    unités qui l'ont → pénétration None tant qu'inconnue (à mapper quand on porte une unité KanOpener)."""

    def get_armor_penetration(self, is_normal_attack: bool = True) -> int | None:
        # TODO: mapper la clé 0x40 → var gameconfig (per-niveau) puis return ability_var(..., self.level).
        return None


# Clé de source UNIQUE du stat-mod Swarm_HitReduction — partagée entre l'attribution d'hydratation
# (`UnitContext.from_snapshot`) et le refresh runner (`runner/abilities/loki/swarm.py`) : même clé =
# `IdunBattle.Entities.Components.ValueModification$$Modify` REMPLACE la contribution (sémantique AddOrUpdate native),
# jamais de double-compte. Forme = le tuple stable par défaut de `stat_modifications_by_source`.
SWARM_HIT_REDUCTION_SOURCE = ("statmod", 1021, None, "Swarm_HitReduction")


class Swarm_HitReductionEffect(BaseEffect):
    """`Swarm_HitReduction` (effet 0x3fd=1021, StaticStatModifierEffect) — malus EXTRA_HITS(17) self du
    trait **Swarm** : « For each member defeated, the swarm attacks with 1 fewer hit » (i2, #60).

    Natif : `IdunBattleLogic.Entities.Abilities.Active.Loki.SwarmAbility$$CreateBehaviour` (ability 0x3ff=1023 accordée par le trait) =
    `AddOrUpdateStaticStatModifierEffect(Self@+0x148, 0x3fd, statType 0x11=EXTRA_HITS,
        Negative(Min(Difference(StatAmount(Self, 20, part 3=INITIAL), Const1@+0xc0),
                     StatAmount(Self, 20, part 4=MISSING))))`
    = **−min(nrOfMembers − 1, membres MORTS)** (plancher structurel 1 hit). Stat 20 = NUMBER_OF_MEMBERS,
    résolue par le handler jumptable 0x14 de `IdunBattle.Entities.UnitExtensions$$GetStat` (IdunBattle.Entities.UnitExtensions$$GetStat+0x859) → GroupUnitComponent
    fill-up {+0x10=nrOfMembers, +0x18=membres restants} via `IdunBattle.Entities.Components.FillUpStatComponent$$GetStatPart`.
    Triggers `IdunBattleLogic.Entities.Abilities.Active.Loki.SwarmAbility$$CreateTrigger` : (On(UnitRepaired=49)|On(UnitHealed=44)|On(UnitMemberDeath=48)|
    On(UnitRevived=46)) & OwnerIsTarget | OnOwnerSpecificAbilityInit(1023) — tous les événements qui
    changent le compte de membres.

    Côté runner l'AddOrUpdate vit dans `runner/abilities/loki/swarm.py` (refresh aux points de mutation
    PV). Ici = la face HYDRATATION : l'amount dépend de l'état PV du porteur → il est LIÉ après
    matérialisation (`bind_group_state`) ; non lié → None = no-op (« présent ≠ appliqué », fidélité-safe).
    La clé de source partagée `SWARM_HIT_REDUCTION_SOURCE` (runner/abilities/loki/swarm.py) fait que le
    refresh runner REMPLACE la contribution hydratée (sémantique AddOrUpdate de
    `IdunBattle.Entities.Components.ValueModification$$Modify`)."""

    _bound_amount: "int | None" = None

    def bind_group_state(self, current_hp: int, member_total_hp: int, member_count: int) -> None:
        """Évalue la formule native avec l'état PV du porteur : amount = −min(n−1, membres morts)."""
        from ....services.trait_damage_limits import group_unit_stat_part
        n = int(member_count)
        if n < 2:
            self._bound_amount = None
            return
        missing = group_unit_stat_part(4, int(member_total_hp), n, int(current_hp))
        self._bound_amount = -min(n - 1, missing)

    def get_stat_modification_stat(self) -> "int | None":
        return 17 if self._bound_amount else None    # StatType.EXTRA_HITS

    def get_stat_modification_amount(self) -> "int | None":
        return self._bound_amount
