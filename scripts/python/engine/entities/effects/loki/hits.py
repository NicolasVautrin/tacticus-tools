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


class SorcerousFacadeAdditionalHitsEffect(BaseEffect):
    """`SorcerousFacade_AdditionalHitsEffect` (effet 0x4b4=1204) — pose par le cast de `SorcerousFacade`
    (1100, Yazaghor `thousTzaangor`) sur le CASTER **et** sur l'allie Psyker vise, pour
    `TurnsFromRounds(1)` : leurs attaques gagnent `nrOfHits` coup(s) additionnel(s) HETEROGENE(s)
    [minDmg,maxDmg] au profil `damageProfile` (= Psychic). i2 : le +728-1455 Psychic n'est PAS le degat
    du cast (celui-la est l'attaque NORMALE, cf. docs/rl/case-171-sorcerousfacade-normal-attack.md) —
    c'est ce BUFF sur les attaques suivantes.

    Natif : `IdunBattle.Entities.Effects.Loki.SorcerousFacade_AdditionalHitsEffect$$CreateAdditionalHits`
    -> `IdunBattle.Entities.Effects.EffectAdditionalHits$$Create` {
        trigger  = `IdunBattleLogic.Entities.DSLTriggers$$get_OwnerIsCaster` (SEUL conjoint — ni
                   `IsMeleeAttack` ni `IsRangedAttack` : le buff vaut pour TOUTE attaque du porteur),
        damage   = `IdunBattle.Entities.Effects.BaseEffect$$GetMinMaxDamage(this, 0)`
                   = `RandomAmount(ConfigVar(0xc=minDmg), ConfigVar(0xd=maxDmg))`,
        additionalHitsType = 1,
        profile  = `GetDamageProfile(config).Value` = `constants.damageProfile` = Psychic,
        hits     = `Get(GetNumberConstant(config, 0x2f = nrOfHits))` (= 1),
        predictionDamage = `GetMinMaxDamage(this, 1)` }

    ⚠ Le corps natif est **IDENTIQUE INSTRUCTION POUR INSTRUCTION** a
    `IdunBattle.Entities.Effects.Loki.SquigHound_AdditionalHitsEffect$$CreateAdditionalHits` (memes
    appels, memes constantes `0x2f`/`0`/`1` ; seules les gardes de cctor different) — ce port en est
    donc le CLONE parametre par la config de l'ability, pas une lecture approchee. `.ctor` =
    `BaseEffect(AbilityOrEffect(<SorcerousFacade>), hasAutomaticActivation = 1)` : les `ConfigVar` sont
    lues sur la config de l'ability 1100, indexees par l'`AbilityStateFromEffect` (= `ability_level`
    cote port, propage a la pose par `scale_from_source`). `minDmg`/`maxDmg` sont dans
    `variablesAffectedByRarityBonus` -> x multiplier de rarete ; `nrOfHits` est un numberConstant."""

    def additional_hit_groups(self, ctx: "Mapping | None" = None) -> "list[dict] | None":
        lvl = self.ability_level if self.ability_level is not None else self.level
        mn = ability_var("SorcerousFacade", "minDmg", lvl,
                         multiplier_pct=self.ability_variables_multiplier)
        mx = ability_var("SorcerousFacade", "maxDmg", lvl,
                         multiplier_pct=self.ability_variables_multiplier)
        count = ability_var("SorcerousFacade", "nrOfHits", is_constant=True)   # numberConstant 0x2f
        if mn is None or mx is None or not count or count <= 0:
            return None
        try:
            import gameconfig as _GC
            profile = ((_GC.ability("SorcerousFacade") or {}).get("constants") or {}) \
                .get("damageProfile") or "Psychic"
        except Exception:
            profile = "Psychic"
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
    du PORTEUR, gate `ctx["is_melee"]` requis (IsMeleeAttack).

    R6-c — CELLULE COMBAT **DEGENEREE**, PAS un spread ±20%. L'appel natif est lu verbatim :
    `EffectAdditionalHits$$Create(&out, cond, ConfigVar(0xb), 1, profile, Direct(nrOfHits), 0,
    **0**, 0)` — le 8e argument (`param_8` = noeud DISPLAY) est **ZERO**, donc
    `IdunBattle.Entities.Effects.EffectAdditionalHits$$Create` execute son repli
    `if (param_8 != 0) param_3 = param_8; param_1[2] = param_3` : `minNode` (+0x10, DISPLAY)
    retombe sur `amountNode` (+0x08, ROLL), et ce noeud unique est un **SCALAIRE**
    (`IdunBattleLogic.Entities.DSLFactory$$ConfigVar` -> `IdunBattle.Entities.Formulas.ConfigAmount`,
    qui n'a pas de `CalculateMin`/`CalculateMax` propres). La face COMBAT
    (`BaseEffect$$AdditionalHits`, `useDisplay = false`) lit donc slot 2 ET slot 3 du MEME noeud
    scalaire => `MinMaxDamage(v, v)`. Consequence sur la CONSOMMATION, et pas seulement sur la
    valeur : `IdunBattle.Core.HitDamage$$GetDamage` ouvre sur
    `if (*param_1 == param_1[1]) return *param_1;` -> **0 tirage** au lieu de 1.
    La face PREDICTION est INCHANGEE (`amount` reste la cle lue en premier par
    `playbook/prediction/normal_attack.py`, et le natif y etale `(amount, amount)` a ±20 % via
    `DamageCalculations$$CalculateDamageSpread`)."""

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
        # R6-c : `amount` = face PREDICTION (noeud DISPLAY) ; `min`/`max` = face COMBAT (noeud ROLL,
        # ICI LE MEME noeud scalaire) -> cellule DEGENEREE, 0 tirage `GetDamage`. Cf. docstring.
        return [{"count": int(count), "amount": int(amt),
                 "min": int(amt), "max": int(amt), "profile": profile}]


class ExemplarOfTheKauyonAdditionalHitsEffect(BaseEffect):
    """`ExemplarOfTheKauyon_AdditionalHits` (effet 0x49d=1181, `tauShadowsun`) — classe native
    `IdunBattle.Entities.Effects.Loki.ExemplarOfTheKauyon_AdditionalHitsEffectEffect` (le suffixe
    `EffectEffect` est celui du BINAIRE, pas une coquille). i2 : « ... reappears on a target hex
    adjacent to an allied unit and immediately performs a normal attack against the closest enemy
    target. **This attack deals an additional {nrOfHits}x {dmg} Blast Damage.** »

    ⚠ CANAL — ce n'est PAS celui de `1183 DefenderOfTheGreaterGood_ExtraHits` (#372), qui partage
    pourtant le porteur. Le marqueur natif est ici
    `...ExemplarOfTheKauyon_AdditionalHitsEffectEffect$$CreateAdditionalHits` ->
    `IdunBattle.Entities.Effects.EffectAdditionalHits$$Create` = canal #179, un GROUPE de coups a
    degat et profil PROPRES ; `1183` passe par `CreateEffectHitsBonusForAttack`, terme de
    `IdunBattle.Entities.Formulas.AttackHitsWithModifiersFormula$$Calculate`, donc des coups d'ARME
    en plus. La colonne « COUPS » de l'inventaire #366 confond les deux ; le decompile les separe.

    Appel natif lu VERBATIM (ordre des `DSLFactory` du corps) :

        amount  = DSLFormulas.ConfigVar( 0xb = dmg, GetAbilityState(effet), config@0x60 )
        nrOfHits= AbilityConfiguration.GetNumberConstant( config, 0x2f = nrOfHits )   # = 2
        profile = AbilityConfiguration.GetDamageProfile( config ).Value               # = Blast
        trigger = DSLTriggers.get_OwnerIsCaster                                       # SEUL conjoint
        hits    = DSLFormulas.Get( nrOfHits )
        EffectAdditionalHits.Create( &out, trigger, amount, 1, profile, hits,
                                     forceOverkill = false, param_8 = **0** )

    `.ctor` = `BaseEffect(AbilityOrEffect(0x43f = 1087 ExemplarOfTheKauyon),
    hasAutomaticActivation = 1)` (immediat `mov edx, 0x43f` lu a l'octet) -> les `ConfigVar` sont
    lues sur la config de l'ABILITY 1087, indexees par l'`AbilityStateFromEffect` (= `ability_level`
    cote port). `dmg` est dans `variablesAffectedByRarityBonus` -> x multiplier ; `nrOfHits` est un
    numberConstant, donc NI leveled NI rarity-scale.

    Pas de gate melee/ranged (contrairement a `FoulInfusion`/`FearOfTheUnseen`) : `OwnerIsCaster` est
    le SEUL noeud du trigger, et il est rendu par le canal PORTEUR lui-meme.

    R6-c — CELLULE COMBAT **DEGENEREE**, exactement comme `FoulInfusion_ExtraHits` : le 8e argument
    (noeud DISPLAY) vaut **0**, donc `EffectAdditionalHits$$Create` execute son repli
    `if (param_8 != 0) param_3 = param_8; param_1[2] = param_3` -> `minNode` (+0x10) retombe sur
    l'`amountNode` (+0x08), et ce noeud unique est un SCALAIRE
    (`IdunBattleLogic.Entities.DSLFactory$$ConfigVar` -> `IdunBattle.Entities.Formulas.ConfigAmount`,
    sans `CalculateMin`/`CalculateMax` propres). La face COMBAT (`BaseEffect$$AdditionalHits`,
    `useDisplay = false`) lit donc slot 2 ET slot 3 du MEME noeud => `MinMaxDamage(v, v)`, et
    `IdunBattle.Core.HitDamage$$GetDamage` ouvre sur `if (*param_1 == param_1[1]) return *param_1;`
    -> **0 tirage**. La face PREDICTION lit `amount` et laisse le pipeline etaler a +/-20 %.

    ⚠ POSEUR NON PORTE : le seul site de pose est
    `IdunBattleLogic.Entities.Abilities.Active.Loki.ExemplarOfTheKauyonAbility$$ExecuteBehaviour`
    (`AddEffect(0x49d, AbilityStateReference, Caster, Caster)` -> `PerformAIAttackFromCurrentPosition`
    -> `RemoveEffect(0x49d)`), et l'ability 1087 est encore un NO-OP combat cote port
    (`docs/rl/combat-ability-coverage.md`). L'inscription est donc DORMANTE dans le pipeline tant que
    1087 n'est pas porte -- elle est confrontee live par decomposition d'etage
    (`tests/engine/runner/test_exemplar_of_the_kauyon_hits_live.py`)."""

    def additional_hit_groups(self, ctx: "Mapping | None" = None) -> "list[dict] | None":
        lvl = self.ability_level if self.ability_level is not None else self.level
        amt = ability_var("ExemplarOfTheKauyon", "dmg", lvl,
                          multiplier_pct=self.ability_variables_multiplier)
        count = ability_var("ExemplarOfTheKauyon", "nrOfHits", is_constant=True)  # numberConstant 0x2f
        if amt is None or amt <= 0 or not count or count <= 0:
            return None
        try:
            import gameconfig as _GC
            profile = ((_GC.ability("ExemplarOfTheKauyon") or {}).get("constants") or {}) \
                .get("damageProfile") or "Blast"
        except Exception:
            profile = "Blast"
        # param_8 = 0 -> cellule DEGENEREE : `amount` (face PREDICTION) et `min`/`max` (face COMBAT)
        # sont le MEME noeud scalaire `ConfigVar(0xb = dmg)`. Cf. docstring (R6-c).
        return [{"count": int(count), "amount": int(amt),
                 "min": int(amt), "max": int(amt), "profile": profile}]


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
    (armure haute) = [156,234]/coup x3 = nat [1098,1644] - arme [630,942] EXACT -> le noeud DISPLAY
    n'evalue QUE le MIN, puis le pipeline etale. Multiplier = GLOBAL de l'unite (varTrace mult=180 ;
    pas le per-ability #68).

    R6-c — LES DEUX NOEUDS SONT DISTINCTS ; la face COMBAT tire dans [minDmg, maxDmg], PAS
    `minDmg ±20%`. `CyclicIonBlaster_AdditionalHitsEffect$$CreateAdditionalHits` lu verbatim
    (l'ordre des `DSLFactory` du corps natif) :

        cond    = HasEffect(target@0x178, 0x462 Markerlight, 1, 6) | HasTrait(target@0x178, 5 Mechanical)
        ROLL    = ConditionalAmount(cond, RandomAmount(Sum(minDmg, extraDmg), Sum(maxDmg, extraDmg)),
                                          RandomAmount(minDmg, maxDmg))          # -> param_3, +0x08
        DISPLAY = ConditionalAmount(cond, Sum(minDmg, extraDmg), minDmg)         # -> param_8, +0x10

    `IdunBattle.Entities.Formulas.ConditionalAmount$$CalculateMin` evalue la condition puis DELEGUE
    `CalculateMin` a la branche retenue (`this+0x18` si vraie, `this+0x20` sinon), et
    `IdunBattle.Entities.Formulas.RandomAmount$$CalculateMin`/`CalculateMax` rendent `Calculate` de
    leur sous-noeud `+0x10`/`+0x18`. La face COMBAT (`BaseEffect$$AdditionalHits`, `useDisplay =
    false`, slots 2/3 du noeud ROLL) obtient donc **[minDmg, maxDmg]**, ou **[minDmg + extraDmg,
    maxDmg + extraDmg]** quand `cond` tient.

    Le port ne rendait que `amount` (= la valeur du noeud DISPLAY, donc le MIN) : la face COMBAT
    etalait ce MIN a ±20 %, soit `[479, 719]` la ou le natif tire dans `[599, 898]` a mult 180 —
    d'ou la signature R6-c « groupe live AU-DESSUS de la borne haute du port » (`tauCrisis`, profil
    Particle p35, armure 6000 : live `[267, 277, 243]` contre `[235, 235, 208]` porte, cellule
    reduite plafonnee a 252). Que `amount == min` du groupe ici est une PROPRIETE DU DESCRIPTEUR
    (branche fausse du DISPLAY = `minDmg` nu), pas une regle du canal.
    La face PREDICTION est INCHANGEE : `playbook/prediction/normal_attack.py` lit `amount` EN
    PREMIER."""

    def additional_hit_groups(self, ctx: "Mapping | None" = None) -> "list[dict] | None":
        lvl = self.ability_level if self.ability_level is not None else self.level
        mn = ability_var("CyclicIonBlaster", "minDmg", lvl,
                         multiplier_pct=self.ability_variables_multiplier)
        mx = ability_var("CyclicIonBlaster", "maxDmg", lvl,
                         multiplier_pct=self.ability_variables_multiplier)
        count = ability_var("CyclicIonBlaster", "nrOfHits", is_constant=True)  # numberConstant 0x2f
        if mn is None or mn <= 0 or mx is None or mx <= 0 or not count or count <= 0:
            return None
        c = ctx or {}
        extra = 0
        if ("Markerlight" in (c.get("tgt_effect_names") or ()) or
                "Mechanical" in (c.get("tgt_traits") or ())):
            # branche VRAIE du ConditionalAmount : `Sum(minDmg, extraDmg)` / `Sum(maxDmg, extraDmg)`
            # — le meme `extraDmg` (ConfigVar 8) alimente les DEUX bornes du `RandomAmount`.
            extra = int(ability_var("CyclicIonBlaster", "extraDmg", lvl,
                                    multiplier_pct=self.ability_variables_multiplier) or 0)
        try:
            import gameconfig as _GC
            profile = ((_GC.ability("CyclicIonBlaster") or {}).get("constants") or {}).get("damageProfile") \
                or "Particle"
        except Exception:
            profile = "Particle"
        # R6-c : `min`/`max` = noeud ROLL (face COMBAT) ; `amount` = noeud DISPLAY (face
        # PREDICTION) = la borne MIN de la meme branche. Cf. docstring.
        return [{"count": int(count), "min": int(mn) + extra, "max": int(mx) + extra,
                 "amount": int(mn) + extra, "profile": profile}]


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
        # #159 (a) — LES DEUX NOEUDS (cf. `BaseEffect.additional_hit_groups`, contrat du dict) :
        #   `amount` = noeud DISPLAY `Average(ConfigVar(keyMin), ConfigVar(keyMax))` (face
        #              PREDICTION ; le pipeline etale ensuite a +-20 %) ;
        #   `min`/`max` = noeud ROLL `RandomAmount(ConfigVar(keyMin), ConfigVar(keyMax))` (face
        #              COMBAT, `useDisplay = false`).
        # Les deux sortent du MEME helper natif `IdunBattle.Entities.Effects.BaseEffect$$
        # GetMinMaxDamage(this, useAverage, keyMin, keyMax)`, lu verbatim :
        #     a = ConfigVar(keyMin, AbilityStateFromEffect(...)) ; b = ConfigVar(keyMax, ...)
        #     return useAverage ? DSLFactory.Average(a, b) : DSLFactory.RandomAmount(a, b)
        # et `IdunBattle.Entities.Effects.Loki.BaseFleshmetalGunsEffect$$CreateAdditionalHits`
        # l'appelle DEUX FOIS (`..., 0, ...` = roll -> param_3 ; `..., 1, ...` = display -> param_8).
        # Le port ne rendait que `amount` : la face COMBAT etalait donc la MOYENNE a +-20 % au lieu
        # de tirer dans [minDmg, maxDmg]. NON DISCRIMINANT sur Melta/Flame (paires +-20 % exactes
        # autour de leur moyenne) mais FAUX sur WarpHail, dont la paire est ASYMETRIQUE :
        # natif [698, 1096] (largeur 399) vs port [718, 1076] (largeur 359) a mult 180.
        # MESURE LIVE (`probe_159_ah_bounds.py`, blackObliterator vs necroWarden, board MC1_67,
        # flux RNG cale par `dumpRng`) : le groupe live est reproduit **8/8** par les bornes ROLL
        # et **0/8** par `amount +-20 %`, 8/8 montages discriminants -- 6 seeds sur WarpHail
        # (largeur 399 vs 359) et 2 sur Melta (500 vs 499 : un ecart d'UNE cellule suffit a
        # decorreler les tirages, donc un fix ajuste au scalaire s'y serait trahi).
        # Cf. `docs/rl/case-159-rng-canal179-et-maybe-ltgb.md`.
        return [{"count": int(count), "min": int(mn), "max": int(mx),
                 "amount": (int(mn) + int(mx)) / 2, "profile": profile}]


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
    de u91 -> +1 coup de extraDmg[50]x1.8=2992 ; a (0,3) non adjacent -> rien.
    i2 : « Enemies defeated by affected attacks are always overkilled » (flag overkill non porte).

    R6-c — CELLULE COMBAT **DEGENEREE**, PAS un spread ±20%. Ici `EffectAdditionalHits$$Create` est
    INLINE par le compilateur dans `ExplosiveMaladies_ExtraRangedAttackEffect$$CreateAdditionalHits`,
    et le repli `param_8 == 0` y est deja resolu — les deux champs recoivent LE MEME noeud :
        param_1[0] = OwnerIsCaster & IsRangedAttack   (condition)
        param_1[1] = ConfigVar(8 = extraDmg)          (+0x08 ROLL)
        param_1[2] = ConfigVar(8 = extraDmg)          (+0x10 DISPLAY, meme objet)
        param_1[3] = Get(GetNumberConstant(0x2f))     (count)
        +0x30 = 1 (forceOverkill)                     +0x34 = 1 (additionalHitsType)
    Ce noeud unique est un SCALAIRE (`IdunBattle.Entities.Formulas.ConfigAmount`), donc les slots
    2 et 3 lus par la face COMBAT rendent la MEME valeur -> `MinMaxDamage(v, v)`, et
    `IdunBattle.Core.HitDamage$$GetDamage` court-circuite sur `min == max` : **0 tirage** au lieu
    de 1. La face PREDICTION est INCHANGEE (`amount` reste lu en premier, spread ±20 % pipeline —
    c'est bien lui qui a produit le delta [3591, 5385] mesure en #57c-C)."""

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
        # R6-c : `amount` = face PREDICTION (noeud DISPLAY) ; `min`/`max` = face COMBAT (noeud ROLL,
        # ICI LE MEME noeud scalaire) -> cellule DEGENEREE, 0 tirage `GetDamage`. Cf. docstring.
        return {"count": int(count), "amount": int(amt),
                "min": int(amt), "max": int(amt), "profile": profile}


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
    (`On(UnitBlocked=0x3c)`) est `ApplyIce`/`ApplyStun` (cf. triggers/loki/anvil_shield.py)."""

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
    """`MasterAnnihilator_AdditionalHitEffect` (effet `MasterAnnihilator_extraHit` 0x4e1=1249 — DEBUFF
    pose par `admecDominus` << Vitruvius >> sur SA cible d'attaque normale, cf.
    `runner/operations/triggers/loki/master_annihilator.py` ; i2 : « Attacks by any friendly unit
    against the affected enemy score an additional hit, except attacks that deal Psychic Damage »).
    Les attaquants qui en beneficient = les ENNEMIS du porteur = les allies du poseur (le gate
    « friendly unit » de l'i2 est structurel, pas dans le trigger).

    ## Canal — GROUPE du canal #179, PAS un terme de la formule de coups (#204, fork ferme)
    `IdunBattle.Entities.Effects.Loki.MasterAnnihilator_AdditionalHitEffect$$CreateAdditionalHits`
    -> `IdunBattle.Entities.Effects.EffectAdditionalHits$$Create` avec :
      - condition = `get_OwnerIsTarget & !AreEqual(CurrentAttackDamageProfile, 0xd = Psychic)` ;
      - roll (param_3) et display (param_8) = `FirstHitInCurrentAttackDamageRange` (le MEME noeud,
        deux instances) ;
      - profil (param_5) = `CONCAT44(0, 0xffffffff)` -> **NULL**, a l'octet pres le meme littéral que
        `IdunBattle.Entities.Effects.Loki.LetTheGalaxyBurnEffect$$CreateAdditionalHits` -> le groupe
        est execute par `IdunBattle.Operations.AttackDamageOperation$$ExecuteAdditionalHitsWithout
        DamageProfileType` (INLINE, donc AVANT les groupes a profil) et emprunte le profil de l'ARME ;
      - count (param_6) = `ConfigConst(0x2f = nrOfHits)` = 1 ;
      - cap (param_9) = `ConfigVar(0xd = maxDmg)` (cf. « CAP » plus bas).

    `FirstHitInCurrentAttackDamageRange` rend le `IdunBattle.Core.HitDamage` de l'AttackData de
    l'attaque COURANTE, pris BRUT ; `IdunBattle.Core.HitDamage$$GetDamage` court-circuite quand
    `min == max` -> sur une attaque NORMALE la valeur du coup est une CONSTANTE = base d'attaque
    reduite. Chaine complete et consequences par vecteur : `docs/rl/case-227-let-the-galaxy-burn-
    canal179.md` §2 (le port ci-dessous en est le mirror exact).

    GROUND TRUTH LIVE #204 (`probe_204_ah_channel.py --case master` ; `admecDominus` pose sur
    `bloodSanguinary`, l'attaquant temoin `ultraApothecary` frappe en melee, MC1_67, armure cible 0) :
    l'evenement supplementaire vaut **4617 sur 5/5 attaques armees** = la stat ATTACK de
    l'attaquant A L'UNITE, quand les coups d'ARME de la meme campagne prennent **8 valeurs distinctes
    sur 8 coups** (3832 .. 5503). Le contrefactuel « +1 coup d'ARME » (l'ancien port) devrait tirer
    4617 pile dans `[0.8A, 1.2A] = [3694, 5540]` : 0/5.

    ## CAP `ConfigVar(0xd = maxDmg)` — transporte, INERTE dans tout regime spawnable
    `IdunBattle.Entities.Effects.BaseEffect$$AdditionalHits` evalue le noeud cap (slot 1) et le range
    en `Nullable<int>` dans l'`AdditionalHits` (+0x20) ; `IdunBattle.Operations.AdditionalHitsFrom
    Effects$$GetAdditionalHitsData` le recopie tel quel dans l'`AdditionalHitsData`. Le seul
    consommateur LU est la face PREDICTION (`IdunBattle.Entities.Abilities.AActiveAbility$$
    GetEffectAdditionalHitPrediction`, qui le passe au slot 0x26 de `DamagePrediction`) ; la voie
    COMBAT sans profil ne lit de cet enregistrement que le COUNT et le profil. MESURE #204
    (`probe_204_cap_and_stat.py`) : `maxDmg` a le niveau d'ability 50 du roster spawnable, multiplier
    de rarete 180 %, vaut **7477**, au-dessus de toute stat ATTACK atteignable (max observe 5022) ->
    **strictement no-op**. Non porte, pour ne pas figer une semantique non lue ; a rouvrir si un
    regime ou `reduce(base) > cap` devient atteignable."""

    def create_aura_additional_hits_for_ally(self, ctx: Mapping) -> "dict | None":
        c = ctx or {}
        # `get_OwnerIsTarget` : le porteur du marqueur EST la cible de l'attaque courante.
        if c.get("owner_id") is None or c.get("owner_id") != c.get("tgt_id"):
            return None
        # `!AreEqual(CurrentAttackDamageProfile, 0xd = Psychic)`. Profil INCONNU (None) -> le noeud
        # `AreEqual` ne peut pas etre VRAI hors d'une attaque -> pas d'exclusion (degradation fidele).
        if c.get("damage_profile") == "Psychic":
            return None
        n = ability_var("MasterAnnihilator", "nrOfHits", is_constant=True)   # ConfigConst 0x2f (=1)
        if not n:
            return None
        # `FirstHitInCurrentAttackDamageRange` = le `HitDamage` BRUT de l'attaque courante. Absent =
        # aucune attaque en cours (face PREDICTION) -> le noeud rend 0 -> coup a 0 degat = no-op
        # numerique -> on n'emet PAS de groupe (mirror #227).
        hd = c.get("attack_hit_damage")
        if hd is None:
            return None
        mn, mx = int(hd[0]), int(hd[1])
        if mn <= 0 and mx <= 0:
            return None
        return {"count": int(n), "min": mn, "max": mx, "profile": None}


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
    => c'est un **GROUPE DU CANAL #179** (coups additionnels), PAS un `+1` de la formule de coups :
    l'artefact natif est un descripteur `EffectAdditionalHits`, comme SquigHound/CordClaw. MEME canal
    que MasterAnnihilator, cote ATTAQUANT (`OwnerIsCaster`) au lieu de defenseur (`OwnerIsTarget`).

    ## `FirstHitInCurrentAttackDamageRange` — ce que le noeud rend VRAIMENT (#227, chaine LUE)
    `IdunBattle.Operations.AttackDamageOperation$$ExecuteHits` fait, APRES chaque coup,
    `List.Add(currentAttack@+0x50, <les 16 premiers octets de l'AttackData>)`, et le champ 0 de
    l'AttackData est son `IdunBattle.Core.HitDamage` (c'est LUI que
    `IdunBattle.Operations.AttackDamageOperation$$ExecuteHit` passe a
    `IdunBattle.Core.HitDamage$$GetDamage` en TETE de coup). Les trois accesseurs du noeud lisent
    `FirstOrDefault` de cette liste :
      - `IdunBattle.Entities.Formulas.FirstHitInCurrentAttackDamageRange$$CalculateMin` -> `.min` ;
      - `...$$CalculateMax` -> `.max` ;
      - `...$$Calculate` (slot 4, canal DISPLAY) -> `HitDamage$$GetDamage(., rng, useAverage=0)`.
    Liste VIDE / pas d'attaque en cours -> les trois rendent **0**.
    => le degat du groupe est le `HitDamage` **de l'ATTAQUE COURANTE** (constant d'un coup a
    l'autre : c'est un champ de l'AttackData, pas une valeur par coup), pris **BRUT**, avant
    spread/percage. `IdunBattle.Core.HitDamage$$GetDamage` (lu verbatim) :
        `if (min == max) return min ; if (useAverage) return (min+max)/2 ; return rng.Range(min, max+1)`

    ## LA CONSEQUENCE, ET POURQUOI ELLE DIFFERE PAR VECTEUR (la tension case-159 §3.3, LEVEE)
      - **attaque NORMALE** : l'AttackData porte un `HitDamage` **DEGENERE** (min == max = la base
        d'attaque ; c'est ce qui donne 1 tirage/coup et non 2). Le groupe herite donc d'une cellule
        degeneree -> `GetDamage` court-circuite (0 tirage) et la valeur du coup est
        `reduce(base)` : **DETERMINISTE**, un seul tirage consomme (le resolve slot-8 gaspille).
      - **ability bounds-mode famille ATTACK** : l'AttackData porte `[minDmg, maxDmg]` NON degenere
        -> `GetDamage` TIRE (1) puis reduce puis resolve (1) = 2 tirages, valeur ALEATOIRE.
    Les deux constats herites etaient donc VRAIS ET COMPATIBLES : `case-bl-1029-1020` §5.4 mesurait
    le vecteur ABILITY, ou l'ancien modele « +1 coup d'ARME » produit EXACTEMENT la meme valeur et la
    meme consommation que le groupe (roll dans les memes bornes brutes, meme reduce, meme resolve) ;
    `case-159` §3.2 mesurait le vecteur NORMAL, ou le port TIRAIT dans la cellule d'arme la ou le
    natif rend une constante. Mesure case-159 : 7e event live = **1133** sur 4 seeds (cellule d'arme
    reduite `(906, 1359)`) et **906** sur la cellule `(725, 1087)` — soit exactement `reduce(base)`,
    la cellule reduite valant `(reduce(0.8 base), reduce(1.2 base))`.

    ## Face PREDICTION
    `IdunBattle.Entities.Abilities.AActiveAbility$$GetAdditionalHitsFromEffectsForPrediction` tourne
    HORS de toute `OngoingAttack` -> `currentAttack@+0x50` est vide -> le noeud rend **0** sur ses
    trois accesseurs -> le groupe predit est un coup a **0 degat** (no-op numerique), et le nb de
    coups de `IdunBattle.Core.Services.DamagePrediction$$GetAttackHits` n'est PAS augmente (ce n'est
    pas un `EffectHitsBonusForAttack`). Cote port : `attack_hit_damage` absent -> aucun groupe.

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

    ## Contexte requis (`ctx` du canal #179, monte par `collect_additional_hit_groups`)
    Le gate a besoin de la CIBLE et de l'etat de l'attaquant : `t_pos` + `tile_effects_by_pos`
    (tileMeta -> `HasTileStatusEffect`) et `persistent_data` (les cles posees sur l'ATTAQUANT ->
    `IsPersistentData`). Le degat a besoin d'`attack_hit_damage` = le `HitDamage` BRUT de l'attaque
    courante. Contexte ABSENT (None) -> aucune contribution (degradation fidele « present !=
    applique », = l'etat PREDICTION mesure #62/#65 : contribution native 0)."""

    def additional_hit_groups(self, ctx: "Mapping | None" = None) -> "list[dict] | None":
        c = ctx or {}
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
        # `FirstHitInCurrentAttackDamageRange` = le `HitDamage` BRUT de l'attaque courante (cf.
        # docstring). Absent = aucune attaque en cours (face PREDICTION) -> le noeud rend 0 ->
        # coup a 0 degat = no-op numerique -> on n'emet PAS de groupe.
        hd = c.get("attack_hit_damage")
        if hd is None:
            return None
        mn, mx = int(hd[0]), int(hd[1])
        if mn <= 0 and mx <= 0:
            return None
        # count  = noeud NULL IdunBattle.Entities.Effects.Loki.LetTheGalaxyBurnEffect$$CreateAdditionalHits -> 1 coup (defaut natif ; GROUND TRUTH live 4 -> 5).
        # profil = Nullable NULL -> le groupe est execute par `IdunBattle.Operations.
        #          AttackDamageOperation$$ExecuteAdditionalHitsWithoutDamageProfileType` au profil
        #          de l'ATTAQUE (percage/block/RegisterDamage de l'arme), cf. `execute_additional_hits`.
        # min/max = noeud ROLL **et** noeud DISPLAY (le natif passe le MEME noeud en param_3 et
        #          param_8) : pas de cle `amount` a fournir, les deux faces lisent la meme chose.
        return [{"count": 1, "min": mn, "max": mx, "profile": None}]


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
    - hits `IdunBattle.Entities.Effects.Loki.AstartesBanner_AdditionalHitsEffect$$CreateAdditionalHits` :
      `EffectAdditionalHits.Create(OwnerIsCaster & IsMeleeAttack, roll = FirstHitInCurrentAttack
      DamageRange, profil = -1 (NULL), count = ConfigConst(0x64 = extraHits), display =
      FirstHitInCurrentAttackDamageRange, cap = ConfigVar(0xd = maxDmg))`.
      ⚠ IDs RE-LUS (#204) : `ConfigConst(0x64)` = **extraHits** et `ConfigVar(0xd)` = **maxDmg**
      (`IdunBattle.Configuration.AbilityConstantType` / `...AbilityVariableType`) — l'ancienne
      docstring lisait `ConfigVar(0xd = extraHits)`, ce qui confondait le COUNT et le CAP.
      GROUND TRUTH ultraApothecary 1->2 @seed999 via AstartesBanner de templAncient.
    - cible `IdunBattle.Entities.Effects.Loki.AstartesBanner_AdditionalHitsEffect$$CreateTargetSelector` : `SurroundingFriends(Self@0x148, ConfigConst 0x16 = range = 2, exclut self)`.

    ## Canal — GROUPE du canal #179, PAS un terme de la formule de coups (#204, fork ferme)
    Le natif appelle `CreateAdditionalHits` (marqueur du canal #179), pas
    `CreateEffectHitsBonusForAttack` (marqueur de la formule de coups). Le corps INLINE de
    `IdunBattle.Entities.Effects.EffectAdditionalHits$$Create` y ecrit le MEME layout que chez
    `LetTheGalaxyBurnEffect` / `MasterAnnihilator_AdditionalHitEffect`, avec le MEME littéral de
    profil (`0xffffffff` -> NULL) : groupe execute par `IdunBattle.Operations.AttackDamage
    Operation$$ExecuteAdditionalHitsWithoutDamageProfileType` (INLINE, donc avant les groupes a
    profil), au profil de l'ARME. `FirstHitInCurrentAttackDamageRange` rend le
    `IdunBattle.Core.HitDamage` de l'AttackData COURANTE, degenere sur une attaque normale -> valeur
    CONSTANTE (`IdunBattle.Core.HitDamage$$GetDamage` court-circuite sur `min == max`). Detail de la
    chaine : `docs/rl/case-227-let-the-galaxy-burn-canal179.md` §2.

    GROUND TRUTH LIVE #204 (`probe_204_ah_channel.py --case astartes` ; `templAncient` a <= 2 hex de
    `ultraApothecary`, qui frappe `bloodSanguinary` en melee, MC1_67, armure cible 0) : l'evenement
    supplementaire vaut **4617 sur 5/5 attaques armees** = la stat ATTACK de l'attaquant A L'UNITE,
    quand les coups d'ARME de la meme campagne prennent **8 valeurs distinctes sur 8 coups**
    (3832 .. 5027). Contrefactuel « +1 coup d'ARME » (l'ancien port) : 0/5.

    ## CAP `ConfigVar(0xd = maxDmg)` — meme statut que chez `MasterAnnihilatorAdditionalHitEffect`
    Transporte par `IdunBattle.Entities.Effects.BaseEffect$$AdditionalHits` (+0x20 de l'`AdditionalHits`),
    lu par la seule face PREDICTION ; MESURE #204 : 7477 au niveau d'ability 50 du roster spawnable
    (multiplier 180 %), au-dessus de toute stat ATTACK atteignable -> strictement no-op. Non porte.

    Ctx du canal (monte par `collect_additional_hit_groups` puis `aura_additional_hits_from_allies`) :
    {owner_id/pos/team, att_id/att_pos/att_team, is_melee, attack_hit_damage, tgt_id, damage_profile}."""

    def create_aura_additional_hits_for_ally(self, ctx: Mapping) -> "dict | None":
        c = ctx or {}
        if not c.get("is_melee"):                          # IsMeleeAttack
            return None
        # `get_OwnerIsCaster` : le BENEFICIAIRE (une cible du `SurroundingFriends`) est l'attaquant.
        if c.get("att_id") == c.get("owner_id"):           # SurroundingFriends exclut le porteur (self)
            return None
        if c.get("owner_team") is None or c.get("owner_team") != c.get("att_team"):
            return None                                    # beneficiaires = ALLIES du porteur
        op, ap = c.get("owner_pos"), c.get("att_pos")
        if not op or not ap:
            return None
        import hexgeo
        rng = ability_var("AstartesBanner", "range", is_constant=True)   # ConfigConst 0x16 (=2)
        if hexgeo.distance(op, ap) > int(rng if rng else 2):             # SurroundingFriends(range)
            return None
        n = ability_var("AstartesBanner", "extraHits", is_constant=True)  # ConfigConst 0x64 (=1)
        if not n:
            return None
        # `FirstHitInCurrentAttackDamageRange` — absent = hors `OngoingAttack` (face PREDICTION) ->
        # le noeud rend 0 -> coup a 0 degat = no-op numerique -> aucun groupe (mirror #227).
        hd = c.get("attack_hit_damage")
        if hd is None:
            return None
        mn, mx = int(hd[0]), int(hd[1])
        if mn <= 0 and mx <= 0:
            return None
        return {"count": int(n), "min": mn, "max": mx, "profile": None}


class SagaOfTheWarriorBornOwnerEffect(BaseEffect):
    """`SagaOfTheWarriorBorn_Owner` (0x4c7=1223) ET `SagaOfTheWarriorBorn_OtherSpaceWolves`
    (0x4c8=1224) — UNE SEULE classe, comme le natif. Axe COUPS + axe CRIT, gate `IsCharging`.

    UNE CLASSE POUR DEUX `EffectType` — mesure, pas supposition. Les deux fabriques
    `IdunBattle.Core.Services.EffectsDatabase.u003Cu003Ec$$u003CInitializeEffectsu003Eb__14_241`
    (1223) et `…b__14_242` (1224) sont **bit-identiques** : meme slot `Il2CppClass*`, meme
    `IdunBattle.Entities.Effects.Loki.SagaOfTheWarriorBorn_OwnerEffect$$.ctor`, **aucun argument
    variable**. Sur les **607** enregistrements d'`InitializeEffects` (formes A + B), ce slot ne
    couvre QUE ces deux ids — aucun autre jumeau. L'identite vient du SLOT, jamais du nom du ctor
    (51 noms de ctor couvrent plusieurs classes sur ce binaire). Le port pointe donc la MEME classe
    depuis les deux entrees d'`EFFECT_CLASSES` : ecrire une seconde classe aurait duplique une
    distinction que le natif n'a pas.

    Le ctor porte une CONSTANTE partagee — `mov edx, 0x49e` puis
    `IdunBattle.Core.AbilityOrEffect$$op_Implicit` puis
    `IdunBattle.Entities.Effects.BaseEffect$$.ctor(this, abilityOrEffect, hasAutomaticActivation: 1)` :
    `0x49e = 1182 = TriggeredAbilityType.SagaOfTheWarriorBorn`. Les DEUX effets lisent donc la MEME
    config d'ability, donc les MEMES variables `extraHits` (0x13) et `extraCritDmg` (0x42). Seul le
    PORTEUR change — d'ou deux `EffectType`, un seul comportement.

    QUI PORTE QUOI :
      * **1223** — `spaceBlackmane` <<Ragnar>> lui-meme, pose des le depart par
        `IdunBattleLogic.Entities.Abilities.Triggered.Loki.SagaOfTheWarriorBorn_InitAbility$$GetEffectType`
        (= `0x4c7`, corps litteral).
      * **1224** — les AUTRES Space Wolves AMIS, poses par
        `IdunBattleLogic.Entities.Abilities.Triggered.Loki.SagaOfTheWarriorBorn_KillAbility` :

            CreateTrigger   = OnDeath(triggerOnOverkill: 1, triggerOnSteppable: 0)
                            & get_OwnerIsActor
                            & HasTrait(Target, 0x10 = UnitTrait.Hero)

            CreateBehaviour = AddEffect( 0x4c8 = 1224,
                                         get_AbilityStateReference(owner),
                                         source  = Owner,
                                         targets = UnitsFromFaction(
                                                       Friends(Owner, <pool partage>,
                                                               UnitSelectionType.OnlyAlive)
                                                       - Owner,
                                                       faction = 0xd = UnitFaction.SpaceWolves,
                                                       UnitSelectionType.OnlyAlive ),
                                         <Nullable vide = aucune duree> )

        ⚠ **AUCUN RAYON.** `IdunBattleLogic.Entities.DSLSelectors$$Friends(of, entities,
        selectionType)` n'a pas de parametre de distance : son 2e argument est le POOL D'ENTITES a
        filtrer (un selecteur partage pre-construit par
        `IdunBattleLogic.Entities.DSLSelectors$$InitializeShared`), pas une portee. La fiche
        `case-ischarging-hits` §7 le lisait « `<radius @+0x80>` » — mé-lecture, corrigee ici et
        recoupee par l'i2 (« friendly Space Wolves », sans mention de portee). L'effet est donc
        POSE A TOUTE L'EQUIPE Space Wolves vivante, ou qu'elle soit sur le plateau, et il est
        PERMANENT (le dernier argument d'`AddEffect` est un `Nullable` vide) — ce que dit l'i2 :
        « If Ragnar has defeated one or more enemy Characters **this battle**, friendly Space Wolves
        also gain this ability. » (« Characters » = le libelle UI du trait `Hero`.)

    FACE POSE NON PORTEE (residu nomme) : le trigger ci-dessus n'existe pas cote port — un moteur
    100 % offline ne posera donc jamais 1224 de lui-meme. Ce que ce port ferme, c'est la LECTURE :
    quand le natif l'a pose, `load_state` le materialise et le port en compte desormais la
    contribution (avant, il retombait sur `BaseEffect`, no-op silencieux).

    MIRROR de
    `IdunBattle.Entities.Effects.Loki.SagaOfTheWarriorBorn_OwnerEffect$$CreateEffectHitsBonusForAttack` :
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
    a `Moved` VRAI et `IsCharging` FAUX. MESURE live (`test_ischarging_saga_hits_live.py`, Ragnar
    rank 17) : regime CHARGE = **10 coups** natifs (7 arme + 3), regime STEP_ADJACENT = **7**. Un
    port gate par `has_moved` rendrait 10 dans les DEUX.

    MAGNITUDE = `ConfigVar(0x13)` = la variable `extraHits` de l'ability `SagaOfTheWarriorBorn`,
    indexee par l'`AbilityState` de l'effet (`IdunBattle.Entities.Effects.BaseEffect$$GetAbilityState`)
    = le niveau de l'ability SOURCE sur le porteur. `SagaOfTheWarriorBorn` est le PASSIF de Ragnar ->
    `ability_level` (fallback `level`, comme `PowerTrip_IgnoreArmor`). `extraHits` n'est PAS dans
    `variablesAffectedByRarityBonus` (seule `extraCritDmg` l'est) -> le multiplier ne la scale pas ;
    il est passe quand meme pour rester le calque strict de `ConfigVar`. Table : `[1]x17, [2]x18,
    [3]x30` -> niveau 50 (rank 17) = **3**, ce que dit l'i2 (« scores 3 additional hits »).

    FACE CRIT (`N14`, FERME par case-ischarging-crit-channel) : le MEME effet porte
    `IdunBattle.Entities.Effects.Loki.SagaOfTheWarriorBorn_OwnerEffect$$CreateCritDamageBonus`, dont
    le decompile est le CALQUE EXACT de la face COUPS ci-dessus -- meme `get_OwnerIsCaster &
    IsCharging(owner@0x148, target@0x178)`, meme `GetAbilityState(effect)`, meme `config@+0x60`, meme
    `EffectBonus.ForAddition`, meme `AbilityOrEffect` recopie de `effect+0x14..+0x2c`. **Une seule
    difference : la cle du `ConfigVar`, 0x42 (`extraCritDmg`) au lieu de 0x13 (`extraHits`).**
    Contrairement a `extraHits`, `extraCritDmg` EST dans `variablesAffectedByRarityBonus` -> le
    multiplier la scale.
    Le canal offline etait le blocage, pas le natif : `create_effect_crit_damage_bonus_for_attack()`
    n'avait aucun parametre de contexte, alors que
    `IdunBattle.Core.Services.DamagePrediction$$CalculateCriticalDamage` passe l'attaquant ET la cible
    a `GetCritDamageBonusFromEffects`, qui batit son `AbilityEntities` avec les deux. Le contexte est
    desormais threade en UN point (`runner/operations/damage.py::AttackDamageOperation._crit_params`).

    NIVEAU D'ABILITY — le seul point ou 1224 SOLLICITE le port autrement que 1223, et un ECART REEL
    (mesure, pas suppose). Le natif lit
    `IdunBattle.Entities.Effects.BaseEffect$$GetAbilityState` =
    `IdunBattleLogic.Entities.DSLSelectors$$AbilityStateFromEffect(<noeud EFFET>)`, c.-a-d.
    l'`AbilityStateReference` BAKEE DANS L'EFFET a la pose, donc celle de la SOURCE (Ragnar). Le
    port, lui, seede `ability_level` depuis le `unitConfig` du PORTEUR (`EffectsState.seed`, cle par
    porteur) — approximation deja nommee dans `runner/snapshot.py::_source_ability_state`. Pour 1223
    les deux coincident (porteur == source) : l'ecart y est INOBSERVABLE. Pour **1224 ils different
    par construction** — le porteur est un Space Wolf qui n'a PAS l'ability.

    Sous `buildNormalizedBC` les deux valent 50, donc l'ecart est numeriquement nul sur tout montage
    normalise. DISSOCIES, il apparait (MC1_67 / 777, Ragnar `PassiveAbilityLevel=1`, Ulf 50) :

        natif   n=4  [2679, 3724, 2879, 3771]                      # extraHits[1] = 1, niveau SOURCE
        port    n=6  [2679, 3724, 2879, 3771, 3273, 3750]          # extraHits[50] = 3, niveau PORTEUR

    Repro : `probe_366_r1_saga_other_space_wolves.py --arms KILL --regimes CHARGE
    --extra="--unit-stat" --extra="spaceBlackmane:PassiveAbilityLevel=1"`.
    Le meme ecart porte sur le MULTIPLIER de rarete (mesure : source 200, porteur 180), donc il
    touche AUSSI la face CRIT (`extraCritDmg` est la seule variable scalee par le multiplier).

    NON CORRIGE ICI, et actionnable : le capteur publie deja la source sur l'effet
    (`{"effectType": 1224, …, "source": 81}`) et `_source_ability_state(state, source_id)` fait deja
    exactement ce calcul pour les effets de TUILE. Ce qui manque est le CABLAGE de cette voie sur les
    effets d'UNITE — un changement du canal de seed partage par les 135 entrees d'`EFFECT_CLASSES`,
    donc une tranche a part entiere avec sa propre validation, pas un ajout a ce port."""

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

    def create_effect_crit_damage_bonus_for_attack(self, att_ctx: "Mapping | None" = None) -> int | None:
        """MIRROR de `IdunBattle.Entities.Effects.Loki.SagaOfTheWarriorBorn_OwnerEffect$$CreateCritDamageBonus` :

            EffectBonus.ForAddition( get_OwnerIsCaster & IsCharging(owner@0x148, target@0x178),
                                     ConfigVar(0x42 = extraCritDmg, GetAbilityState(effect), config@+0x60),
                                     <AbilityOrEffect recopie de effect+0x14..+0x2c> )

        Calque strict de la face COUPS -- MEME arbre a deux noeuds, MEME gate partage
        `is_charging_attack(att_ctx)` (aucun predicat re-derive), seule la cle du `ConfigVar` change.
        Ni `IsNormalAttack` ni `IsMeleeAttack` : le bonus vaut pour tout coup du porteur en charge.

        MAGNITUDE : `extraCritDmg[ability_level]`, **scalee par le multiplier** (elle est la SEULE
        variable de `SagaOfTheWarriorBorn` listee dans `variablesAffectedByRarityBonus`) -> a l'inverse
        de `extraHits`, ou le multiplier est passe mais inerte.

        Le retour est un ENTIER (pas un `EffectBonus`) : le canal natif somme des scalaires
        (`GetCritDamageBonusFromEffects` accumule `addition - subtraction` de chaque `EffectBonus`
        evalue), et son consommateur est `max(0, GetStat(10) + somme)`."""
        if not is_charging_attack(att_ctx):
            return None
        lvl = self.ability_level if self.ability_level is not None else self.level
        n = ability_var("SagaOfTheWarriorBorn", "extraCritDmg", lvl,
                        multiplier_pct=self.ability_variables_multiplier)   # ConfigVar 0x42
        return int(n) if n else None


class UnstoppableFerocityOwnerEffect(BaseEffect):
    """`UnstoppableFerocity_OwnerEffect` (effet 0x408=1032, `blackSmnBloodletter` <<Bloodletter>>,
    summon d'Archimatos `blackPossession`) — axe COUPS, gate `IsCharging`. MIRROR de
    `IdunBattle.Entities.Effects.Loki.UnstoppableFerocityOwnerEffect$$CreateEffectHitsBonusForAttack` :

        EffectBonus.ForAddition( get_OwnerIsCaster & IsCharging(caster@0x160, target@0x178),
                                 Direct( AbilityConfiguration.GetNumberConstant(config@+0x60,
                                                                               0x2b = extraHit) ),
                                 <AbilityOrEffect recopie de effect+0x14..+0x2c> )

    DEUX noeuds trigger, pas trois — **aucun** `IsNormalAttack`, **aucun** `IsMeleeAttack` : meme
    forme exacte que `SagaOfTheWarriorBornOwnerEffect` (1223), dont ce port est le calque. Le bonus
    vaut donc pour TOUTE attaque du porteur en charge. `get_OwnerIsCaster` est deja porte par le
    canal : ces effets ne sont interroges que sur l'ATTAQUANT
    (`hits_bonus_from_effects(attacker_effects, ...)`).

    ⚠ L'`IsCharging` de CET effet prend `caster@0x160` (pas `owner@0x148` comme 1223) en 1er argument.
    Sous `OwnerIsCaster` les deux designent la meme entite -> semantique identique ; la difference est
    notee parce qu'elle est REELLE au decompile, pas parce qu'elle change quoi que ce soit.

    GATE — foyer PARTAGE, aucun predicat re-derive ici : `effects/base.py::is_charging_attack` lit la
    cle `att_ctx["is_charging"]`, calculee par `engine/battle_query.py::is_charging`
    (`AreEntitiesAdjacent(caster,target) && UnitComponent.ChargedUnitIds@+0x190.Contains(target.Id)`) --
    cote COMBAT dans `runner/damage_model.py::build_hits_board`, cote PREDICTION dans
    `playbook/prediction/normal_attack.py`. Ce n'est PAS `HasFlag(UnitFlag.Moved)` :
    `MoveUnitOperation$$UpdateCharging` n'inscrit que les unites devenues NOUVELLEMENT adjacentes,
    donc un caster qui se decale vers une cible DEJA adjacente a `Moved` VRAI et `IsCharging` FAUX.

    MAGNITUDE = `GetNumberConstant(config, 0x2b)` = la CONSTANTE `extraHit` de l'ability source
    (`ABondEffect..ctor(this, 1, 0, AbilityOrEffect(0x40b = TriggeredAbilityType.UnstoppableFerocity))`,
    recopiee en `effect+0x14..+0x2c`), = **1**. Une constante, donc : ni indexee par niveau, ni dans
    `variablesAffectedByRarityBonus` -> jamais scalee par le multiplier de rarete (meme forme que
    `PowerTrip_FullHealth`, `extraHit` cle 0x2b elle aussi). i2 : « Scores one additional hit when
    <charging> ».

    HORS PERIMETRE, nomme : la SECONDE clause de l'i2 (« Scores one additional hit when attacking an
    enemy Psyker ») est un effet SEPARE, `UnstoppableFerocity_ExtraHit` (0x4a8=1192) =
    `ForAddition(HasTrait(target@0x178, 0x3ea) & get_OwnerIsCaster, Direct(1))` — meme ability source
    0x40b, aucun noeud `IsCharging`. Non porte ici (l'inventaire le classe NON CONFRONTABLE) ; il faut
    donc mesurer 1032 sur une cible **NON Psyker**, sinon les deux +1 se confondent."""

    def create_effect_hits_bonus_for_attack(self, is_normal_attack: bool = True,
                                            att_ctx: "Mapping | None" = None) -> EffectBonus | None:
        # IsCharging (IdunBattleLogic.Entities.DSLFactory$$IsCharging -> BattleQuery$$IsCharging).
        # PAS de gate is_normal_attack / is_melee : le decompile n'a QUE ces deux noeuds.
        if not is_charging_attack(att_ctx):
            return None
        n = ability_var("UnstoppableFerocity", "extraHit",
                        is_constant=True)          # GetNumberConstant(config, 0x2b)
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


class DefenderOfTheGreaterGoodExtraHitsEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.DefenderOfTheGreaterGood_ExtraHitsEffect` (effet 0x49f=1183 sur
    `tauShadowsun`, 0x51b=1307 sur son summon `tauSmnDroneCommandLink`) -- AURA source-side sur l'axe
    COUPS. i2 : « Affected attacks also have a chance to score an additional hit. This chance is
    {[chance]}% for each round in which Shadowsun has been on the battlefield. »

    UNE SEULE CLASSE NATIVE pour les DEUX EffectType : `..._ExtraHitsEffect$$.ctor(this, isDrone)` ecrit
    `isDrone` a `this+0x480` apres `BaseEffect(AbilityOrEffect(...), hasAutomaticActivation = 1)`. Le
    port suit -- `DefenderOfTheGreaterGoodExtraHitsDroneEffect` n'est qu'une sous-classe a `_IS_DRONE`.

    POSE : `IdunBattleLogic.Entities.Abilities.Triggered.Loki.DefenderOfTheGreaterGoodAbility$$CreateBehaviour`
    = `If(HasTrait(Owner, 0x2 = Summon), AddEffect(0x51a)+AddEffect(0x51b),
                                         AddEffect(0x49e)+AddEffect(0x49f))`, toujours sur
    `selectors.Owner` -> l'effet vit sur le PORTEUR (mesure live : `decisionView` porte
    `DefenderOfTheGreaterGood_ExtraHits` sur `tauShadowsun`, jamais sur ses allies).

    CONTRIBUTION -- `IdunBattle.Entities.Effects.Loki.DefenderOfTheGreaterGood_ExtraHitsEffect$$CreateEffectHitsBonusForAttack`,
    lu verbatim (ordre des `DSLFactory` du corps natif) :

        srcSel  = EffectSource(<selectors+0x38 = le selecteur Effect>)
        turnSel = If( AmountIsGreaterThanZero(Parent(srcSel)), Parent(srcSel), srcSel )
        chance  = Min( Direct(100), Multiply( ConfigConst(0x2a = chance), UnitTurnsStarted(turnSel) ) )
        trigger = get_OwnerIsCaster & IsRangedAttack & !DamageProfileIs(0xd = Psychic) & Maybe(chance)
        return EffectBonus.ForAddition( trigger, ConfigConst(0x2b = extraHit), <AbilityOrEffect> )

    `Direct(100)` = le champ `DSLFormulas+0x30`, construit `DirectAmount(100)` par
    `IdunBattleLogic.Entities.DSLFormulas$$.ctor` (voisins : +0x18=0, +0x20=1, +0x28=2, +0x38=-1).
    `IdunBattle.Entities.Effects.Loki.DefenderOfTheGreaterGood_ExtraHitsEffect$$GetCurrentExtraHitChance`
    reconstruit EXACTEMENT le meme noeud `chance` (c'est la donnee `{[chanceCurrent]}` de l'i2).

    ## MARQUEUR DE CANAL : `CreateEffectHitsBonusForAttack`, PAS `CreateAdditionalHits`
    Le coup gagne est un coup d'ARME de plus (terme de
    `IdunBattle.Entities.Formulas.AttackHitsWithModifiersFormula$$Calculate`), pas un groupe #179 a
    degat propre. C'est la distinction tranchee en #204/#227, ici dans l'autre sens : cet effet est
    l'alimenteur natif qui manquait au canal AURA de la formule de coups, supprime faute d'implementeur.

    ## `Owner` = LE BENEFICIAIRE, jamais le porteur
    `IdunBattle.Core.Services.DamagePrediction$$GetAttackHits` n'itere PAS `attacker.Effects` : il
    prend TOUS les effets actifs du board (`IdunBattle.Core.Services.EffectsQuery$$GetActiveEffectsWithBonuses`,
    entrees baties par `IdunBattle.Core.Services.EffectsQuery$$GetEffectWithTargetEntry` qui embarquent
    la liste des CIBLES) puis boucle effets x cibles en ecrivant `AbilityEntities+0x18 (Owner) <- la
    CIBLE de l'effet` et `+0x08/+0x00 (Caster/Actor) <- l'ATTAQUANT`. Donc `get_OwnerIsCaster` signifie
    « la cible de l'effet EST l'attaquant » -- le porteur n'est atteint que par `EffectSource(Effect)`,
    ce que fait justement la formule de chance. Cote port, ce gate est PORTE PAR LE CANAL
    (`aura_hits_bonus_for_attack` n'interroge que des porteurs != attaquant et evalue le selecteur sur
    l'attaquant), exactement comme pour les autres auras source-side (#49/#153).

    ## SELECTEUR -- partage avec l'axe DEGAT
    `..._ExtraHitsEffect$$CreateTargetSelector` = `DefenderOfTheGreaterGoodAbility.GetBaseBuffTargetSelector(
    dsl, Tiles(Owner), isDrone@+0x480, 0x49f)`, dont le corps est :

        sel = AdjacentFriends(Owner, ownerTiles, includeSelf = 1) - Owner
        sel = Unique( sel + UnitsFromFaction(SurroundingFriends(Owner, ownerTiles, range = 2), 9 = Tau) )
        sel = UnitsWithRangedWeaponsExcludingDamageProfile( sel, 0xd = Psychic )
        if (isDrone == 0) return sel
        return EntitiesIsNotTargetOfEffect( sel, Nullable<EffectType>(effectType) )

    Le tronc est celui deja porte pour `1182` (`loki/extra_damage_aura.py`). La branche `isDrone` retire
    du selecteur du DRONE toute unite DEJA ciblee par l'effet NON-drone de Shadowsun (`0x49f` ici) :
    anti-double-comptage natif quand les deux auras se recouvrent -> `_IS_DRONE` + `aura_peers`.

    ⚠ `!DamageProfileIs(0xd)` du trigger est **INERTE SUR CE CANAL** : `GetAttackHits` construit son
    `AbilityEntities` avec `damageProfile (+0xbc) = null`, et
    `IdunBattle.Entities.Triggers.DamageProfileIsTrigger$$IsMatchingDamageProfileInEntities` ouvre sur
    `Nullable.get_HasValue(entities+0xbc)` -> rend 0. Le gate Psychic PORTE ici vient donc du
    SELECTEUR (`UnitsWithRangedWeaponsExcludingDamageProfile` = eligibilite de l'ARME du beneficiaire),
    pas du trigger -- meme approximation que sur l'axe degat : l'attaque evaluee etant RANGED, son
    profil EST celui de l'arme ranged du beneficiaire.

    ## MAGNITUDE / CHANCE
    `extraHit` et `chance` sont les DEUX seules constantes de l'ability au gameconfig
    (`{chance: 25, extraHit: 1}`) et AUCUNE n'est dans `variablesAffectedByRarityBonus` -> le multiplier
    est inerte. `chance = min(100, 25 x UnitTurnsStarted(src))` avec
    `IdunBattle.Entities.Formulas.UnitTurnsStartedFormula$$Calculate` = `GetStat(unit, 0xc)` =
    `StatType.TURNS_STARTED` ; `src` = le PARENT du porteur s'il existe (drone -> Shadowsun), sinon le
    porteur -> dans les deux cas les tours de SHADOWSUN, ce que dit l'i2.

    ## `Maybe(chance)` -- foyer PARTAGE, aucun predicat re-derive
    `entities.triggers.MaybeTrigger` (mirror 1:1 de
    `IdunBattle.Entities.Triggers.MaybeTrigger$$ShouldTrigger`) : sans PRNG (`!CanUseRandom`, c.-a-d.
    la face DECISION/PREDICTION) il rend `99 < chance`, donc VRAI seulement a 100 % ; avec PRNG (face
    COMBAT) il tire `NextBool(chance)` -- **et ce tirage CONSOMME un genrand**, il ne peut donc pas
    etre saute sans decaler tout le flux. Le noeud est evalue EN DERNIER (apres selecteur et gates),
    comme dans l'arbre natif.

    GROUND TRUTH LIVE (`MC1_67`/777, `tauShadowsun` rank 17, `turnsStarted >= 4` donc chance = 100) :
    `darkaHellblaster` (non-T'au) a d=1 de Shadowsun -> **2** coups ; a d=2 -> **1** ; a d=4 -> **1**.
    `tauCrisis` (T'au) a d=2 -> **10** coups ; a d=4 -> **9**. Le selecteur MORD sur la distance ET la
    faction."""

    _IS_DRONE = False
    _TAU_FACTION = "Tau"           # UnitFaction.Tau=9 (`UnitsFromFaction(..., 9)`)
    _SOURCE_EFFECT_TYPE = 1183     # 0x49f -- l'effet NON-drone vise par `EntitiesIsNotTargetOfEffect`

    # ------------------------------------------------------------------ selecteur (geometrie)

    def aura_selector_covers(self, ctx: "Mapping | None" = None) -> bool:
        """Tronc commun de `GetBaseBuffTargetSelector` (SANS la branche `isDrone`) : l'attaquant
        est-il dans le selecteur de CE porteur ? Extrait en methode parce que la branche drone
        (`EntitiesIsNotTargetOfEffect`) doit l'evaluer sur un AUTRE porteur."""
        c = ctx or {}
        if c.get("att_id") == c.get("owner_id"):              # `sel - Owner`
            return False
        if c.get("owner_team") is None or c.get("owner_team") != c.get("att_team"):
            return False                                      # Adjacent/SurroundingFRIENDS
        op, ap = c.get("owner_pos"), c.get("att_pos")
        if not op or not ap:
            return False
        d = hexgeo.distance(tuple(op), tuple(ap))
        adjacent = (d == 1)                                   # AdjacentFriends(range 1, TOUTE faction)
        tau_ring = (d <= 2 and c.get("att_faction") == self._TAU_FACTION)   # UnitsFromFaction(2, Tau)
        return bool(adjacent or tau_ring)

    def _covered_by_source_aura(self, c: Mapping) -> bool:
        """`EntitiesIsNotTargetOfEffect(sel, <effectType non-drone>)` -- branche `isDrone` du selecteur.
        `aura_peers` = les MEMES porteurs que ceux passes a l'agregateur (tuple [0]=id, [1]=pos,
        [2]=team, [-1]=effets) : on cherche un porteur du type NON-drone dont le selecteur couvre
        DEJA l'attaquant."""
        for p in (c.get("aura_peers") or []):
            for e in (p[-1] or []):
                if getattr(e, "effect_type", None) != self._SOURCE_EFFECT_TYPE:
                    continue
                if e.aura_selector_covers({**c, "owner_id": p[0], "owner_pos": p[1],
                                           "owner_team": p[2]}):
                    return True
        return False

    # ------------------------------------------------------------------ chance (noeud V)

    def current_extra_hit_chance(self, ctx: "Mapping | None" = None) -> "int | None":
        """MIRROR de `..._ExtraHitsEffect$$GetCurrentExtraHitChance` :
        `Min(Direct(100), Multiply(ConfigConst(0x2a = chance), UnitTurnsStarted(turnSel)))`.
        None = substrat absent (pas de `turns_started_by_id`) -> aucune contribution, jamais un 0
        deguise en mesure."""
        c = ctx or {}
        ts = c.get("turns_started_by_id") or {}
        oid = c.get("owner_id")
        # `If( AmountIsGreaterThanZero(Parent(EffectSource)), Parent(EffectSource), EffectSource )` :
        # le PARENT s'il existe (drone -> son summoner Shadowsun), sinon la source elle-meme.
        pid = (c.get("parent_by_id") or {}).get(oid)
        src = pid if (pid is not None and pid in ts) else oid
        turns = ts.get(src)
        if turns is None:
            return None
        per = ability_var("DefenderOfTheGreaterGood", "chance", is_constant=True)   # ConfigConst 0x2a
        if not per:
            return None
        return min(100, int(per) * int(turns))                # Min(Direct(100), Multiply(...))

    # ------------------------------------------------------------------ contribution

    def create_aura_hits_bonus_for_attack(self, ctx: "Mapping | None" = None) -> "EffectBonus | None":
        from ...triggers import MaybeTrigger        # foyer PARTAGE du noeud `Maybe` (mirror 1:1)
        c = ctx or {}
        if c.get("is_melee") is not False:                    # IsRangedAttack (TRI-ETAT : None se tait)
            return None
        if (c.get("damage_profile") or None) == "Psychic":    # selecteur ...ExcludingDamageProfile(0xd)
            return None
        if not self.aura_selector_covers(c):
            return None
        if self._IS_DRONE and self._covered_by_source_aura(c):
            return None                                       # EntitiesIsNotTargetOfEffect
        chance = self.current_extra_hit_chance(c)
        if chance is None:
            return None
        # `Maybe(chance)` EN DERNIER (ordre de l'arbre natif) : le tirage COMBAT consomme un genrand,
        # il ne doit avoir lieu que si les noeuds precedents ont tenu.
        if not MaybeTrigger(c.get("rng"), int(chance)).should_trigger(None):
            return None
        n = ability_var("DefenderOfTheGreaterGood", "extraHit", is_constant=True)   # ConfigConst 0x2b
        return for_addition(True, int(n)) if n else None


class DefenderOfTheGreaterGoodExtraHitsDroneEffect(DefenderOfTheGreaterGoodExtraHitsEffect):
    """Jumeau DRONE (effet 0x51b=1307, porte par `tauSmnDroneCommandLink`, le summon d'
    `ExemplarOfTheKauyon`). MEME classe native, `isDrone = 1` a `this+0x480` -- donc MEME magnitude,
    MEME chance (lue sur le PARENT = Shadowsun), et une seule difference de comportement : la branche
    `EntitiesIsNotTargetOfEffect` du selecteur (cf. `_covered_by_source_aura`).

    `..._ExtraHitsEffect$$get_Priority` rend `0` quand `isDrone`, `100` sinon -- ordre de resolution
    des effets, sans effet sur la magnitude ; non porte (le canal somme, il ne trie pas)."""

    _IS_DRONE = True


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
    Triggers `IdunBattleLogic.Entities.Abilities.Active.Loki.SwarmAbility$$CreateTrigger` : (On(UnitRepaired=48)|On(UnitHealed=43)|On(UnitMemberDeath=47)|
    On(UnitRevived=45)) & OwnerIsTarget | OnOwnerSpecificAbilityInit(1023) — tous les événements qui
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
