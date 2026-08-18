"""Effets `Effects.Loki` — famille COUPS / BLOCS / PÉNÉTRATION-ARMURE : coups additionnels
(`additional_hit_groups` / `create_effect_hits_bonus_for_attack`), réduction de coups
(`create_effect_hits_malus_for_defense`), block (`create_effect_block_source_for_defense` /
stat-mod BLOCK_DAMAGE), pénétration d'armure (`get_armor_penetration`). 1 classe par effet natif (VA
citée). Cf. `loki/__init__.py`."""
from __future__ import annotations

from collections.abc import Mapping
from fractions import Fraction as _Fraction

import hexgeo

# `IdunBattle.DSL.AAmountFormula$$RoundFix64Result` -- foyer PARTAGE de l'arrondi Fix64 (#344).
# Consomme ici par le canal DISPLAY de `SpecialIssueCombiMelta_AdditionalHits` (#419-r1-tr11-r5) :
# `DSLFormulas$$Average` -> `DivideAmount$$Calculate` -> `RoundFix64Result(., 0)` demi-vers-le-PAIR.
from ....dsl.base import _round_fix64
from ....services.effect_bonus import (EffectBonus, for_addition, for_subtraction,
                                       for_percent_decrease, for_percent_increase,
                                       for_percent_subtraction_capped)
from ....services.damage_combat import BlockSource
from ....services.static_battle_rules import TILE_STATUS_EFFECT_NAMES
# FORME B (liaison de MODULE, pas de nom) -- la seule des trois qui laisse un
# `monkeypatch.setattr("engine.services.static_battle_rules.<f>", ...)` MORDRE. Differe GRATUIT
# hisse : `import engine.services.static_battle_rules` en process frais charge 9 modules `engine.*`
# et n'y met PAS `engine.entities.effects.loki.hits` -- aucun cycle a fermer (mesure #419-r1-tr9-
# r4-r1-r2-r1a). Le module est de toute facon deja importe par la ligne au-dessus.
from ....services import static_battle_rules as _static_battle_rules
from ..base import BaseEffect, is_at_range as _is_at_range, is_charging_attack, owner_is_caster
from ..magnitude import ability_var, global_value, trait_var
# #270-r1-r1 : les cles composites `LET_THE_GALAXY_BURN_PERSISTENT_KEY` / `SWARM_HIT_REDUCTION_SOURCE`
# portent des membres d'enum, et le meme ordinal 1482 nomme AUTRE CHOSE dans l'autre.
from ...effect_type import EffectType
from ...triggered_ability_type import TriggeredAbilityType
# Meme cause que dans `status.py` : `630fb33e` (#270-r1-r1-r3) a converti des litteraux en
# `StatType.<MEMBRE>` dans quatre `get_stat_modification_stat` qui n'avaient aucun import local ->
# `NameError` au chargement d'etat. Import module-level (#448-r3-r1).
from ...stats import StatPart, StatType
from ....services.trait_damage_limits import group_unit_stat_part
import engine.entities.effects.ctx_keys as _ctx_keys      # #1042-r5 : foyer UNIQUE des chaines de cle de ctx
# #943-r7 -- les deux canaux du substrat d'adjacence NATIF, en FORME B (#485-r1-r1).
# `pathfinding.board` n'importe RIEN de `engine`, et `engine.battle_query` n'importe que `hexgeo` +
# `.hex_corner` : aucune de ces deux aretes ne peut refermer le SCC `effects`.
from ...pathfinding import board as _board
from .... import battle_query as _bq


def _adjacency_channels(ctx):
    """Les DEUX canaux de l'adjacence NATIVE derives du `board` porte par le ctx, en TRI-ETAT
    (#943-r7). Les trois canaux qui traversent ce module le publient depuis le meme commit :
    `aura_hits_malus_for_defense` / `aura_hits_bonus_for_attack` (le board de coups, monte par
    `runner/damage_model.py::build_hits_board` cote COMBAT et par
    `playbook/prediction/normal_attack.py` cote PREDICTION -- PENDANTS EXACTS) et
    `aura_additional_hits_from_allies` (`runner/operations/additional_hits.py` / les deux ctx de la
    meme face PREDICTION).

    Substrat : `IdunBattleLogic.Entities.DSLSelectors$$AdjacentTiles` ->
    `IdunBattle.Entities.Selectors.AdjacentTilesSelector$$Select` -> la liste STOCKEE du
    `ConnectivityComponent`, puis la porte `|dElev| < 2` de `IdunBattle.Core.Services.TileQuery
    .u003CIterateAdjacentTilesu003Ed__8$$MoveNext`. Board absent -> `(None, None)` -> repli
    geometrique NOMME du foyer d'adjacence, jamais un voisinage vide (#381-r3)."""
    return _board.adjacency_channels((ctx or {}).get("board"))


class SquigHoundAdditionalHitsEffect(BaseEffect):
    """`SquigHound_AdditionalHitsEffect` (effet 0x50c=1292, orksRuntherd) — ajoute des coups HETEROGENES
    a l'attaque du porteur : `nrOfHits` coups a degat PROPRE [minDmg,maxDmg] (vars 0xc/0xd de l'ability
    SquigHound, ctor AbilityOrEffect 0x43a=1082) et profil PROPRE (`damageProfile`). Gate = OwnerIsCaster.

    Natif : `IdunBattle.Entities.Effects.Loki.SquigHound_AdditionalHitsEffect$$CreateAdditionalHits` -> `IdunBattle.Entities.Effects.EffectAdditionalHits$$Create` {condition=OwnerIsCaster,
    param_3 = `GetMinMaxDamage(this, 0)` (noeud ROLL), count=GetNumberConstant(0x2f=nrOfHits),
    damageProfile=GetDamageProfile(config).Value, param_8 = `GetMinMaxDamage(this, 1)` (noeud DISPLAY)}.
    ⚠ La ligne qui vivait ici disait « minDmg=...(idx0) / maxDmg=...(idx1) » : c'etait FAUX (#884). Le
    2e argument d'`IdunBattle.Entities.Effects.BaseEffect$$GetMinMaxDamage` n'est pas un INDICE de
    variable, c'est le drapeau `isPrediction` -- corps LU (overload 4-arg, `0xc`/`0xd`) :
    `isPrediction == 0` -> `DSLFormulas.RandomAmount(minNode, maxNode)` ; `!= 0` -> `DSLFormulas.Average
    (minNode, maxNode)`. Cf. la note de mecanique sur `SpecialIssueCombiMeltaAdditionalHitsEffect`.
    `GetMinMaxDamage` (overload 2-arg) indexe
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
        # BI-CANAL ROLL / DISPLAY (#884) : `param_8` du `Create` natif vaut `GetMinMaxDamage(this, 1)`
        # = `Average(minNode, maxNode)`, PAS 0 -> la cellule de PREDICTION est DEGENEREE a la moyenne
        # (etalee +/-20 % par le pipeline), alors que la face COMBAT lit `min`/`max` du noeud ROLL.
        # Mecanique complete : `SpecialIssueCombiMeltaAdditionalHitsEffect.additional_hit_groups`.
        return [{"count": int(count),
                 "amount": _round_fix64(_Fraction(int(mn) + int(mx), 2), 0),
                 "min": int(mn), "max": int(mx), "profile": profile}]


class CordClawAdditionalHitsEffect(BaseEffect):
    """`CordClaw_AdditionalHitsEffect` (effet 0x4e2=1250, nom capté "CordClaw_AdditionHits",
    admecRuststalker Exitor-Rho) — après un cast CordClaw (0x462=1122), TOUTES les attaques du porteur
    jusqu'à la fin de son prochain tour gagnent des coups additionnels à dégât PROPRE (i2 : « All of
    Exitor-Rho's further attacks ... deal an additional 2x 582-873 Direct Damage »).

    Natif : `IdunBattle.Entities.Effects.Loki.CordClaw_AdditionalHitsEffect$$CreateAdditionalHits` -> EffectAdditionalHits
    (INLINÉ dans ce corps-ci — le repli `if (param_8 == 0) param_8 = param_3` s'y lit verbatim)
    {condition=OwnerIsActor, param_3 = `GetMinMaxDamage2(this, 0)` (noeud ROLL),
    param_8 = `GetMinMaxDamage2(this, 1)` (noeud DISPLAY),
    count=GetNumberConstant(0x32)=`nrOfHits_2` (=2), profile=GetDamageProfile(config)=DirectDamage
    (fallback natif 0xf si absent)}. Même canal #179 que SquigHound (prev-threadés après les coups
    d'arme, overkill continu).

    ⚠ La ligne qui vivait ici disait « minmax=GetMinMaxDamage2(effect, idx0/idx1) » : c'était FAUX
    (#884). `IdunBattle.Entities.Effects.BaseEffect$$GetMinMaxDamage2(this, isPrediction)` =
    `GetMinMaxDamage(this, isPrediction, 0x36 = minDmg_2, 0x37 = maxDmg_2)` — le 2ᵉ argument est le
    drapeau `isPrediction`, PAS un indice de variable : `0` -> `RandomAmount(min, max)` (ROLL),
    `1` -> `Average(min, max)` (DISPLAY). Cf. `SpecialIssueCombiMeltaAdditionalHitsEffect`.

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
        # BI-CANAL ROLL / DISPLAY (#884) : `param_8` = `GetMinMaxDamage2(this, 1)` = `Average(...)`.
        # Cf. `SpecialIssueCombiMeltaAdditionalHitsEffect.additional_hit_groups` pour la mecanique.
        return [{"count": int(count),
                 "amount": _round_fix64(_Fraction(int(mn) + int(mx), 2), 0),
                 "min": int(mn), "max": int(mx), "profile": profile}]


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
        forceOverkill = 0,
        param_8  = `GetMinMaxDamage(this, 1)` = `Average(ConfigVar(0xc), ConfigVar(0xd))` (noeud
                   DISPLAY -- #884 : ce n'est PAS un second `RandomAmount`) }

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
        # BI-CANAL ROLL / DISPLAY (#884) : `param_8` = `GetMinMaxDamage(this, 1)` = `Average(...)`.
        # Cf. `SpecialIssueCombiMeltaAdditionalHitsEffect.additional_hit_groups` pour la mecanique.
        return [{"count": int(count),
                 "amount": _round_fix64(_Fraction(int(mn) + int(mx), 2), 0),
                 "min": int(mn), "max": int(mx), "profile": profile}]


class FragLanceEffect(BaseEffect):
    """`FragLanceEffect` (`EffectType` 0x5c3 = 1475 `FragLance`) — effet PERMANENT du passif de relance
    `astraSmnDeathRider` (summon d'`astraDreir` via `LeadingTheCharge`) et de son jumeau npc
    `astraNpc5DeathRider` : quand le porteur CHARGE, ses attaques NORMALES gagnent `nrOfHits` coups
    additionnels HETEROGENES [minDmg,maxDmg] au profil `damageProfile` (= Blast). i2
    `Abilities/FragLance_CurrentLevelDescription` : « When charging, normal melee attacks deal an
    additional {nrOfHits}x {minDmg}-{maxDmg} Blast Damage ».

    ## L'ARTEFACT NATIF (decompile = verite, build `rnca9r7q6c`)

    Deux etages, et ils sont SEPARES cote port comme cote natif :

    1. LA POSE — `IdunBattleLogic.Entities.Abilities.Triggered.Loki.FragLanceAbility`, dont la classe
       de base est `IdunBattle.Entities.Abilities.AOwnerEffectTriggeredAbility` et dont le SEUL corps
       propre est `...FragLanceAbility$$GetEffectType` (corps ENTIER : `return 0x5c3`). Le patron du
       parent est invariant :
           `AOwnerEffectTriggeredAbility$$CreateTrigger`   = `OnOwnerSpecificAbilityInit(this.AbilityType)`
           `AOwnerEffectTriggeredAbility$$CreateCondition` = <trigger constant `DSLTriggers+0x70`>
           `AOwnerEffectTriggeredAbility$$CreateBehaviour` =
               `If(CreateCondition(state),
                   AddEffect(GetEffectType(), AbilityState(Owner, AbilityType), Owner, Owner, default))`
       -> a l'init du porteur, l'effet 1475 est pose SUR LUI-MEME, sans duree. Cote port c'est la table
       `ABILITY_INIT_OWNER_EFFECTS["FragLance"] = ["FragLance"]` (aplatissement du patron, cf. sa
       docstring). ⚠ HOMONYMIE A DEUX FACES : la CLE est le nom d'un `TriggeredAbilityType`
       (`FragLance` = 1481), la VALEUR le nom d'un `EffectType` (`FragLance` = 1475) — meme chaine,
       deux enums, deux ordinaux.

    2. LE CANAL — `IdunBattle.Entities.Effects.Loki.FragLanceEffect$$CreateAdditionalHits`
       -> `IdunBattle.Entities.Effects.EffectAdditionalHits$$Create` {
           trigger  = `get_OwnerIsCaster` op_BitwiseAnd `IsNormalAttack`
                      op_BitwiseAnd `IsCharging(Caster@DSLSelectors+0x60, Target@DSLSelectors+0x78)`,
           damage   = `IdunBattle.Entities.Effects.BaseEffect$$GetMinMaxDamage(this, 0)`
                      = `RandomAmount(ConfigVar(0xc=minDmg), ConfigVar(0xd=maxDmg))`  (noeud ROLL),
           additionalHitsType = 1,
           profile  = `IdunBattle.Configuration.AbilityConfiguration$$GetDamageProfile(config).Value`
                      = `constants.damageProfile` = Blast,
           hits     = `IdunBattleLogic.Entities.DSLFormulas$$ConfigConst(0x2f = nrOfHits, config)`,
           forceOverkill = 0,
           predictionDamage = `GetMinMaxDamage(this, 1)` = `Average(minDmg, maxDmg)`  (noeud DISPLAY) }
       `.ctor` = `IdunBattle.Entities.Effects.BaseEffect(AbilityOrEffect(<FragLance>), 1)` -> les
       `ConfigVar` sont lues sur la config de l'ability, indexees par l'`AbilityStateFromEffect`
       (= `ability_level` cote port). `minDmg`/`maxDmg` sont dans `variablesAffectedByRarityBonus`
       -> x multiplier de rarete ; `nrOfHits` est un numberConstant.

    ## Le TRIGGER a TROIS conjoints, et le troisieme est le seul NEUF sur ce canal

    - `get_OwnerIsCaster` -> foyer partage `owner_is_caster(ctx)` (cles `owner_id`/`att_id`) ;
    - `IsNormalAttack`    -> cle `ctx["is_normal_attack"]`, MEME donnee que le parametre homonyme des
      canaux COUPS-D'ARME et PENETRATION (`create_effect_hits_bonus_for_attack`,
      `get_armor_penetration`) : nature du VECTEUR, pas du coup. Tri-etat, `True` requis ;
    - `IsCharging(caster, target)` -> foyer partage `is_charging_attack(ctx)`, forme POSITIVE
      (`case-ischarging-hits-channel` : VRAI seulement si la charge est PROUVEE — le natif commence
      par `AreEntitiesAdjacent`, donc sans positions il rend FAUX, jamais VRAI).

    BI-CANAL ROLL / DISPLAY (#884) : ce descripteur etait l'un des trois `Average` NON portes du
    recensement des 19 `$$CreateAdditionalHits` (residu `#884-r2`) ; il publie donc `min`/`max`
    (face COMBAT, `useDisplay = 0`) ET `amount` (face PREDICTION, `Average` arrondi Fix64
    demi-vers-le-PAIR) DES son premier commit, comme cette fiche l'exigeait."""

    def additional_hit_groups(self, ctx: "Mapping | None" = None) -> "list[dict] | None":
        c = ctx or {}
        if not owner_is_caster(c):                          # get_OwnerIsCaster
            return None
        if c.get("is_normal_attack") is not True:           # IsNormalAttack (tri-etat : True requis)
            return None
        if not is_charging_attack(c):                       # IsCharging(Caster@+0x60, Target@+0x78)
            return None
        lvl = self.ability_level if self.ability_level is not None else self.level
        mn = ability_var("FragLance", "minDmg", lvl, multiplier_pct=self.ability_variables_multiplier)
        mx = ability_var("FragLance", "maxDmg", lvl, multiplier_pct=self.ability_variables_multiplier)
        count = ability_var("FragLance", "nrOfHits", is_constant=True)   # numberConstant 0x2f
        if mn is None or mx is None or not count or count <= 0:
            return None
        try:
            import gameconfig as _GC
            profile = ((_GC.ability("FragLance") or {}).get("constants") or {}) \
                .get("damageProfile") or "Blast"
        except Exception:
            profile = "Blast"
        # BI-CANAL ROLL / DISPLAY (#884) : `predictionDamage` = `GetMinMaxDamage(this, 1)` =
        # `Average(minNode, maxNode)` -> cellule de PREDICTION DEGENEREE a la moyenne ARRONDIE
        # (`DivideAmount$$Calculate` -> `AAmountFormula$$RoundFix64Result(., 0)`, demi-vers-le-PAIR),
        # etalee +/-20 % par le pipeline ; la face COMBAT lit `min`/`max` du noeud ROLL.
        return [{"count": int(count),
                 "amount": _round_fix64(_Fraction(int(mn) + int(mx), 2), 0),
                 "min": int(mn), "max": int(mx), "profile": profile}]


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

    Canal #179 STANDARD du PORTEUR, BI-CANAL (== SquigHound/CordClaw/SorcerousFacade) : la face COMBAT
    resout le noeud `RandomAmount` (`min`/`max`), la face PREDICTION la cellule DEGENEREE `Average`
    (`amount`) -- #884. `minDmg`/`maxDmg` sont dans `variablesAffectedByRarityBonus` ->
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
        # BI-CANAL ROLL / DISPLAY (#884) : `param_8` = `GetMinMaxDamage(this, 1)` = `Average(...)`.
        # Cf. `SpecialIssueCombiMeltaAdditionalHitsEffect.additional_hit_groups` pour la mecanique.
        return [{"count": int(count),
                 "amount": _round_fix64(_Fraction(int(mn) + int(mx), 2), 0),
                 "min": int(mn), "max": int(mx), "profile": profile}]


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
    (`IdunBattleLogic.Entities.DSLFormulas$$ConfigVar` -> `IdunBattle.Entities.Formulas.ConfigAmount`,
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
    (`IdunBattleLogic.Entities.DSLFormulas$$ConfigVar` -> `IdunBattle.Entities.Formulas.ConfigAmount`,
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


class SpecialIssueCombiMeltaAdditionalHitsEffect(BaseEffect):
    """`SpecialIssueCombiMelta_AdditionalHits` (`EffectType` 0x61b = **1563**) -- classe native
    `Idun.Source.IdunBattle.Logic.Entities.Effects.Loki.SpecialIssueCombiMelta_AdditionalHitsEffect`.
    Porteurs de l'ability 1545 (`TriggeredAbilityType`) : `darkaSternguard` (HERO « Ramus ») et le npc
    `darkaBossSternguardLHE`. C'est la face COMBAT du terme de PORTEE EXACTE dont
    `docs/rl/case-419-r1-tr11-special-issue-combi-melta.md` porte la face DECISION.

    ## Appel natif, lu VERBATIM (`...$$CreateAdditionalHits`)
    ```
    trigger = get_OwnerIsCaster
            & IsAtRange( Caster@DSLSelectors+0x48, Target@DSLSelectors+0x60, DSLFormulas+0x28 )
    EffectAdditionalHits.Create( trigger,
                                 GetMinMaxDamage(this, 0),                     # noeud ROLL
                                 additionalHitsType = 1,
                                 profile = AbilityConfiguration.GetDamageProfile(config@+0x60),
                                 hits    = Get( GetNumberConstant(config, 0x2f = nrOfHits) ),
                                 forceOverkill = 0,
                                 GetMinMaxDamage(this, 1) )                    # noeud DISPLAY
    ```

    ## LE POINT QUI NE SE DEVINE PAS -- `IsAtRange` compare par EGALITE, et la formule est un CHAMP
    `IdunBattle.Entities.Triggers.IsAtRangeAbilityTrigger$$ShouldTrigger` (corps LU) :
    ```
    attendu = <formule this+0x28>.Calculate(entities)
    d       = query.<slot 0x6f = GetDistance>( <this+0x18>.Select(entities), <this+0x20>.Select(...) )
    return d == attendu                       # EGALITE EXACTE -- ce n'est PAS un `<=`
    ```
    et la formule n'est PAS un `Get(n)` au call-site : c'est un champ PRE-CONSTRUIT de l'instance
    `DSLFormulas`, pose par `IdunBattleLogic.Entities.DSLFormulas$$.ctor` (lu a l'octet) :
    ```
    +0x18 = Const(0)   +0x20 = Const(1)   +0x28 = Const(2)   +0x30 = Const(100)   +0x38 = Const(-1)
    ```
    => ce groupe mord **a la distance 2 EXACTEMENT**. Son jumeau `SpecialIssueCombiMelta_ExtraDmg`
    (1564, `+0x20`) mord a **1**, et le `Pinned` de `SpecialIssueCombiMelta_AddEffectAbility`
    (`DSLFormulas.Get(3)`) a **3**. Les trois valeurs CORROBORENT l'empreinte de prediction native
    deja mesuree au §3 de la case-doc (d=1 montant plat, d=2 coup ENTIER, d=3 rien) au lieu de la
    fitter : elles sont lues, l'empreinte les confirme.

    ## `.ctor` et magnitude
    `...AdditionalHitsEffect$$.ctor` = `BaseEffect(AbilityOrEffect(<1545>), hasAutomaticActivation = 1)`
    -- meme patron auto-porteur qu'`InfernalPacts_AdditionalHitsEffect` : aucune classe `Ability` ne le
    pose en jeu, `SpecialIssueCombiMelta_InitAbility$$CreateBehaviour` le materialise a l'init
    (`AddEffect(0x61b, stateRef, Owner@+0x30) & AddEffect(0x61c, ...)`). Les `ConfigVar` sont donc lues
    sur la config de l'ability 1545, indexees par l'`AbilityStateFromEffect` (= `ability_level`).
    Kit LU : `{damageProfile: Bolter, nrOfHits: 1}`, `variablesAffectedByRarityBonus =
    [minDmg, maxDmg, extraDmg]` -> min/max x multiplier, `nrOfHits` NI leveled NI rarity-scale.

    ## CONTEXTE REQUIS -- et c'est ce qui bloquait le port (#419-r1-tr11-r3)
    Le gate a besoin des DEUX positions. Le `ctx` du canal #179 portait deja `t_pos` cote COMBAT mais
    PAS `att_pos` ; cote PREDICTION il ne portait NI l'un NI l'autre. Les deux `ctx` sont enrichis
    dans le meme commit (`runner/operations/additional_hits.py::collect_additional_hit_groups` et
    `playbook/prediction/normal_attack.py`). Contexte ABSENT -> aucune contribution : un gate de
    DISTANCE inevaluable ne peut pas etre suppose VRAI (degradation fidele, meme convention que
    `LetTheGalaxyBurnEffect`).

    ⚠ `att_pos` est la tuile d'ATTAQUE (candidate en prediction, reelle en combat), pas la position
    courante du caster -- c'est le meme substrat que `LordOfTempests_ExtraDamageEffect`, et c'est ce
    que le natif lit : le `Caster@DSLSelectors+0x48` d'une prediction est resolu contre la
    `UnitPosition` CANDIDATE threadee par la chaine display."""

    def additional_hit_groups(self, ctx: "Mapping | None" = None) -> "list[dict] | None":
        c = ctx or {}
        if not _is_at_range(c.get("att_pos"), c.get("t_pos"), 2):   # DSLFormulas+0x28 = Const(2)
            return None
        lvl = self.ability_level if self.ability_level is not None else self.level
        mn = ability_var("SpecialIssueCombiMelta", "minDmg", lvl,
                         multiplier_pct=self.ability_variables_multiplier)
        mx = ability_var("SpecialIssueCombiMelta", "maxDmg", lvl,
                         multiplier_pct=self.ability_variables_multiplier)
        count = ability_var("SpecialIssueCombiMelta", "nrOfHits", is_constant=True)   # 0x2f
        if mn is None or mx is None or not count or count <= 0:
            return None
        import gameconfig as _GC
        profile = ((_GC.ability("SpecialIssueCombiMelta") or {}).get("constants") or {}) \
            .get("damageProfile") or "Bolter"
        # BI-CANAL ROLL / DISPLAY (#419-r1-tr11-r5) -- et la ligne qui vivait ici etait FAUSSE :
        # elle disait << les DEUX noeuds sont des RandomAmount >>. Corps LU de
        # `IdunBattle.Entities.Effects.BaseEffect$$GetMinMaxDamage(this, isPrediction, 0xc, 0xd)` :
        #     minNode = ConfigVar(0xc = minDmg, AbilityStateFromEffect, config)
        #     maxNode = ConfigVar(0xd = maxDmg, AbilityStateFromEffect, config)
        #     isPrediction == 0 -> DSLFormulas.RandomAmount(minNode, maxNode)      # noeud ROLL
        #     isPrediction != 0 -> DSLFormulas.Average(minNode, maxNode)           # noeud DISPLAY
        # Le noeud DISPLAY est donc une MOYENNE, pas un tirage -- et c'est ce qui rend la cellule de
        # PREDICTION degeneree : `IdunBattle.Entities.Effects.BaseEffect$$AdditionalHits(this,
        # entities, useDisplay)` pose `min = max = <+0x10 = noeud DISPLAY>.Calculate()` quand
        # `useDisplay`, et `min = <+0x08 = noeud ROLL>.CalculateMin()` / `max = ...CalculateMax()`
        # sinon (face COMBAT, ou `ExecuteAdditionalHitsWithoutDamageProfileType` passe l'octet a 0).
        # `DSLFormulas$$Average(a, b)` = `DivideAmount(SumAmount(a, b), Direct(2), rule = null)` ->
        # `IdunBattle.Entities.Formulas.DivideAmount$$Calculate` ->
        # `IdunBattle.DSL.AAmountFormula$$RoundFix64Result(., 0)` = `Fix64.Round` demi-vers-le-PAIR
        # (MEME foyer et MEME arrondi que la famille (a) de #344) -- donc un ENTIER, jamais un `.5`.
        # D'ou la cle `amount` : le consommateur PREDICTION la prefere et etale +/- 20 %
        # (`GetBaseDamageFix64`), ce qui EST l'etalement natif de la cellule degeneree ; le
        # consommateur COMBAT (`operations/additional_hits.py`) prefere `min`/`max` des qu'ils
        # existent -- ajouter `amount` ne peut donc PAS toucher la face COMBAT.
        # Patron identique a `InfernalPactsAdditionalHitsEffect` / `_BaseFleshmetalGunsEffect`.
        return [{"count": int(count),
                 "amount": _round_fix64(_Fraction(int(mn) + int(mx), 2), 0),
                 "min": int(mn), "max": int(mx), "profile": profile}]


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
        # #884 -- `Average` rend un ENTIER, jamais un `.5`. La ligne qui vivait ici ecrivait
        # `(mn + mx) / 2` (division FLOTTANTE Python) et sa docstring revendiquait le `.5` :
        # c'etait un SECOND modele du MEME noeud natif, contradictoire avec celui de
        # `SpecialIssueCombiMeltaAdditionalHitsEffect`. `DSLFormulas$$Average` ->
        # `DivideAmount$$Calculate` -> `AAmountFormula$$RoundFix64Result(., 0)` = `Fix64.Round`
        # demi-vers-le-PAIR, puis `Fix64.op_Explicit` vers un int.
        # VALUE-PRESERVING au regime SERVI (lvl 50, mult 180 de `blackObliterator`) : Melta
        # 1246 = round(1246.5) et floor(1246.5) ; Flame et WarpHail sont a somme PAIRE. Le
        # correctif MORD ailleurs -- 14/50, 14/50 et 15/50 niveaux du gameconfig, et au lvl 50
        # des mult 140 (Melta 970 contre 969.5 ; Flame 776 contre 775.5) et 160 (WarpHail 798
        # contre 797.5). Un `.5` publie ici se comporte en aval comme un `floor` :
        # `get_base_damage_fix64(2991.5)` rend `[2393, 3589]`, soit exactement `(2991)`.
        return [{"count": int(count), "min": int(mn), "max": int(mx),
                 "amount": _round_fix64(_Fraction(int(mn) + int(mx), 2), 0), "profile": profile}]


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
        # `AdjacentFriends(owner, 1)` -> `AdjacentTiles(owner)` -> la liste STOCKEE (#943-r7). La
        # SOURCE de l'enumeration est le PORTEUR : `is_adjacent(owner, att)`, pas l'inverse -- le
        # champ `neighbours` du `boardGraph` est le champ BRUT, ni trie ni symetrise, donc la
        # couronne hex ne pouvait PAS exprimer cet axe.
        elev_by_pos, neigh_by_pos = _adjacency_channels(ctx)
        if not _bq.is_adjacent(tuple(owner_pos), tuple(att_pos), elev_by_pos, neigh_by_pos):
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
    deux modeles coincident PRESQUE — #884 les a separes live, ecart 4 points). Le groupe expose
    donc `amount` (le noeud `Average`, ENTIER : `Fix64.Round` demi-vers-le-PAIR — la mention
    « .5 possible » qui vivait ici etait FAUSSE, cf. #884) consomme par la PREDICTION, ET
    `min`/`max` (plage RandomAmount) consommes par la face COMBAT (`_execute_additional_hits`,
    qui prefere min/max)."""

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
        # `AdjacentFriends(Caster, 1)` -> la liste STOCKEE (#943-r7), enumeree depuis le PORTEUR
        # (le `Caster` du selecteur EST le porteur de l'effet, cf. la docstring de la classe).
        elev_by_pos, neigh_by_pos = _adjacency_channels(ctx)
        if not _bq.is_adjacent(tuple(owner_pos), tuple(att_pos), elev_by_pos, neigh_by_pos):
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
        # bi-canal : `amount` = noeud `Average` (PREDICTION) ; `min`/`max` = noeud `RandomAmount`
        # (COMBAT). Cf. docstring (mesure 202b).
        # #884 -- la ligne qui vivait ici ecrivait `(mn + mx) / 2` (division FLOTTANTE) et son
        # commentaire revendiquait « pas de troncature du .5 ». C'est FAUX : `DSLFormulas$$Average`
        # -> `DivideAmount$$Calculate` -> `AAmountFormula$$RoundFix64Result(., 0)` = `Fix64.Round`
        # demi-vers-le-PAIR puis `Fix64.op_Explicit` -> un ENTIER. VALUE-PRESERVING au regime SERVI
        # (lvl 50, mult 180 de `thousInfernalMaster` : 1496 des deux facons), MORDANT ailleurs --
        # 12/50 niveaux, et au lvl 50 du mult 100 (832 contre 831.5).
        return {"count": int(count), "amount": _round_fix64(_Fraction(int(mn) + int(mx), 2), 0),
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
    `df@0xa8` est construit par `IdunBattleLogic.Entities.DSLTriggers$$InitializeShared` = `On(0x21 = AbilityInit) &
    OwnerIsActor` -> 1202 (et 1200) sont poses A LA CREATION de l'unite, PAS au block. GROUND TRUTH live :
    Arjac porte `AnvilShield_AdditionalBlock` (level 1, remaining 0) des le PREMIER `decisionView` d'un
    runner frais -> l'effet est deja materialise par le seed, RIEN a caber. Le vrai volet ON-BLOCK
    (`On(UnitBlocked=0x3c)`) est `ApplyIce`/`ApplyStun` (cf. triggers/loki/anvil_shield.py)."""

    def get_stat_modification_stat(self) -> int | None:
        return StatType.BLOCK_DAMAGE                                     # StatType.BLOCK_DAMAGE

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
        return StatType.BLOCK_CHANCE                                     # StatType.BLOCK_CHANCE

    def get_stat_modification_amount(self) -> int | None:
        return ability_var("AnvilShield", "blockChance", _anvil_shield_level(self),
                           multiplier_pct=self.ability_variables_multiplier)

    def reverted_stats(self) -> "list":
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
        return StatType.BLOCK_CHANCE                                     # StatType.BLOCK_CHANCE

    def get_stat_modification_amount(self) -> int | None:
        return ability_var("AnvilShield", "blockChance", _anvil_shield_level(self),
                           multiplier_pct=self.ability_variables_multiplier)

    def applied_stat_mods(self, stats_ctx) -> "list":
        """DATA du `ChangeStat` (part 5) pose a l'application : BLOCK_CHANCE += blockChance[level]."""
        amt = self.get_stat_modification_amount()
        return [(StatType.BLOCK_CHANCE, int(amt))] if amt else []   # 7 (#270-r1-r1)

    def reverted_stats(self) -> "list":
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
                                               defender_attack: int = 0,
                                               defender_max_health: int = 0):
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


class BeastSnaggaExtraBlockEffect(BaseEffect):
    """`EffectType.BeastSnagga_ExtraBlock` (0x439 = 1081) -- l'entree `GetMultiValueStat(7)` posee
    par `IdunBattleLogic.Entities.Abilities.Triggered.Loki.BeastSnaggaAbility$$CreateBehaviour`.
    #1015-r1.

    ARBRE NATIF, LU (le SEUL `AddExtraBlockEffectToOwner` du build dont l'amount vient des PV) :

        blockChance = GetNumberConstant( AbilityConstantType.blockChance = 0x2d )
        blockDmgPct = GetNumberConstant( AbilityConstantType.blockDmgPct = 0x36 )
        AddExtraBlockEffectToOwner(
            0x439,
            blockChance : Direct( blockChance ),
            blockDamage : PercentageOf( StatAmount(Owner@<DSLSelectors+0x30>,
                                                   statType 0x5 = Health, statPart 0x2 = Maximum),
                                        Direct( blockDmgPct ) ),
            turns       : null )

    ⚠ **LA STAT N'EST PAS CELLE DU JUMEAU.** `BeastSlayerAbility$$GetBlockDamage` calcule
    `PercentageOf(StatAmount(0x10 = FixedArmor), ...)` ; ici c'est `StatAmount(0x5 = Health,
    part 0x2 = Maximum)`. Les deux abilities partagent le MEME `CreateDamageModifier` (cf.
    `BeastSnaggaExtraDmgEffect`), donc supposer que le block suit aussi etait tentant -- il ne le
    suit pas, et le nom de la variable de trait le CONFIRME : `beastSnaggaDmgAsMaxHpPct` (contre
    `beastSlayerBlockAsMaxArmorPct`). Substrat = `GetStat(defenseur, Health, Maximum)`, c.-a-d. le
    maximum COURANT (`HealthComponent.hp_max` cote runner, `combatSnapshot.healthMax` cote scene) --
    PAS la stat `Health` de la BC.

    ⚠ **AUCUNE CLASSE D'EFFET DEDIEE COTE NATIF** pour 1081 (`search_symbols_by_name BeastSnagga`
    rend 4 symboles : `BeastSnaggaAbility$$CreateTrigger/$$CreateBehaviour` et
    `BeastSnagga_ExtraDmgEffect$$.ctor/$$CreateDamageModifier`). C'est le regime NORMAL
    d'`AddExtraBlockEffectToOwner`, qui pose un `MultiValueStatEntryEffect` generique portant les
    deux entrees `{BLOCK_CHANCE, BLOCK_DAMAGE}` -- meme patron de port que
    `BeastSlayerExtraBlockEffect` / `PsychicFortressExtraBlockEffect` /
    `MonsterSlayerOfCalibanExtraBlockEffect` : une classe qui RELIT la config.

    `defender_max_health` non threade (0) -> `None` : une source dont l'amount serait devine
    ferait rouler au port un tirage de block que le natif ne roule pas de la meme facon."""

    def create_effect_block_source_for_defense(self, defender_fixed_armor: int = 0,
                                               defender_attack: int = 0,
                                               defender_max_health: int = 0):
        chance = trait_var("BeastSnagga", "beastSnaggaBlockChance")
        pct = trait_var("BeastSnagga", "beastSnaggaDmgAsMaxHpPct")
        if not chance or pct is None:
            return None
        # `PercentageOf(StatAmount(Owner, Health, Maximum), Direct(pct))` -- meme troncature entiere
        # que les deux autres `PercentageOf` de la famille (`BeastSlayer`, `Daemon`).
        amount = int(int(defender_max_health) * int(pct) / 100)
        if amount <= 0:
            return None
        # block_id = l'ENTITE-EFFET (cf. `BeastSlayerExtraBlockEffect`) ; offline = l'`effect_type`,
        # jamais la chance : `BeastSnagga` et `BeastSlayer` ont TOUS DEUX chance 10, et les
        # confondre perdrait un tirage dans l'exclusion inter-coups de `_run_hits`.
        return BlockSource(chance=int(chance), amount=amount,
                           block_id=self.block_source_id(int(EffectType.BeastSnagga_ExtraBlock)))


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
                                               defender_attack: int = 0,
                                               defender_max_health: int = 0):
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
      `IdunBattleLogic.Entities.DSLBehaviors$$AddExtraBlockEffectToOwner(0x3ef, Direct(GetNumberConstant(0x2d=blockChance)),
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
                                               defender_attack: int = 0,
                                               defender_max_health: int = 0):
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
                                             dist: int | None = None,
                                             is_normal_attack: bool = True,
                                             att_ctx: Mapping | None = None) -> EffectBonus | None:
        # PAS de gate `IsNormalAttack` : le trigger natif n'a QUE `OwnerIsTarget(tuiles egales) &
        # !IsMeleeAttack` -- la reduction porte aussi sur les attaques d'ABILITY.
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
                                             dist: int | None = None,
                                             is_normal_attack: bool = True,
                                             att_ctx: Mapping | None = None) -> EffectBonus | None:
        # PAS de gate `IsNormalAttack` : le trigger natif n'a QUE `OwnerIsTarget & IsMeleeAttack`.
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
                                             dist: int | None = None,
                                             is_normal_attack: bool = True,
                                             att_ctx: Mapping | None = None) -> EffectBonus | None:
        # trigger natif = OwnerIsTarget SEUL (IdunBattle.Entities.Effects.Loki.Diminutive_HitReductionEffect$$CreateEffectHitsBonusForAttack) : AUCUN gate melee/ranged, aucun gate profil, aucun gate IsNormalAttack.
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
                                             dist: int | None = None,
                                             is_normal_attack: bool = True,
                                             att_ctx: Mapping | None = None) -> EffectBonus | None:
        # PAS de gate `IsNormalAttack` : le trigger natif n'a QUE `OwnerIsTarget & IsRangedAttack`.
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

    def create_effect_hits_malus_for_defense(self, is_melee: bool | None = None,
                                             damage_profile: str | None = None,
                                             defender_on_cover: bool | None = None,
                                             dist: int | None = None,
                                             is_normal_attack: bool = True,
                                             att_ctx: Mapping | None = None) -> "EffectBonus | None":
        """FACE PREDICTION SEULEMENT (#10019) -- un coup d'ARME de plus, MESURE.

        Ce canal a ete RETIRE par #204 parce que la mesure du COMBAT l'exigeait, et ce retrait
        reste juste POUR LE COMBAT : l'evenement supplementaire y vaut la constante `reduce(base)`
        (stat ATTACK a l'unite, 4617 sur 5/5 attaques armees), donc un GROUPE du canal #179, pas un
        coup d'arme. Ce que #204 n'a pas mesure, c'est la face PREDICTION -- son verdict s'appuyait
        sur la deduction de `case-227` Sect. 2.5 (`GetAdditionalHitsFromEffectsForPrediction` tourne
        hors `OngoingAttack` -> `FirstHitInCurrentAttackDamageRange` rend 0 -> coup a 0 degat).

        MESURE #10019 (`engine_agreement_stages --build --seeds 777 --steps 20`, board `MC1_67`) --
        la deduction est REFUTEE pour ce porteur. Trois paires independantes vers la MEME cible 93
        (`templChampion`), toutes en `ability 69` = attaque normale, six nombres, tous en rapports
        ENTIERS `(h+1)/h` sur les DEUX bornes :

            u85 `orksKillaKan`   1108 -> 1385  |  3052 -> 3815   (5/4)
            u79 `tauDarkstrider`   60 ->   90  |  3004 -> 4506   (3/2, `kill` BASCULE)
            u77 `eldarMauganRa`  2394 -> 2793  |  3588 -> 4186   (7/6)

        Le degat PAR COUP est IDENTIQUE des deux cotes (277, 30, 399) : seul le COMPTE differe,
        d'exactement un. Un groupe a degat CONSTANT est ARITHMETIQUEMENT exclu -- il ajouterait le
        MEME entier aux deux bornes, or u77 exigerait +399 et +598 a la fois.

        TEMOIN NEGATIF : `u83` = `admecDominus`, le POSEUR de la marque, attaque la MEME cible avec
        la MEME ability au pas 5 et CONCORDE -- la marque n'y est pas encore posee, elle est le
        fruit de son attaque. C'est le seul effet present chez les trois divergents et absent chez
        lui, ce qui rend l'attribution falsifiable.

        VOIE NON TRANCHEE (residu `#10019-r1`) -- on porte l'EFFET mesure, pas la voie, et le site
        le dit : cette classe ne declare AUCUN `CreateEffectHitsBonusForAttack` natif (absent de
        `ghidra/functions.tsv` ET de `frida/methods.tsv` ; un corps NON trivial n'aurait pas ete
        deduplique), donc `IdunBattle.Core.Services.DamagePrediction$$GetAttackHits` ne le compte
        pas -- le coup vient de `IdunBattle.Entities.Abilities.AActiveAbility$$
        AddAdditionalHitsToPrediction`, qui appelle le MEME slot `PredictAttack` (0x27) que les
        coups d'arme et somme par `IdunBattle.Core.Services.DamagePredictionResult$$Add`. Le port
        n'a pas d'etage ou loger cette somme cote prediction ; l'ecrire comme un coup d'arme y est
        NUMERIQUEMENT EXACT, et c'est exactement la forme deja retenue pour `GetStuckIn` (fold
        deterministe dans la formule cote prediction, behaviour chance-gate cote combat).

        Gates portes, tous deux LUS dans `MasterAnnihilator_AdditionalHitEffect$$CreateAdditionalHits` :
          * `get_OwnerIsTarget` -- STRUCTUREL ici : ce canal n'agrege que les effets de la CIBLE
            (`hits_malus_from_defender_effects`), donc le porteur EST la cible ;
          * `!AreEqual(CurrentAttackDamageProfile, 0xd = Psychic)`.
        Le SIGNE est POSITIF, donc `block_hits_reduction` ne l'eteint pas (`_hits_contribution` ne
        neutralise que les contributions negatives) -- fidele au tri natif, qui porte sur le signe.
        """
        # FACE : hors prediction, ce canal n'existe pas -- le combat garde le groupe #179 de #204.
        # `att_ctx` absent (appelant anterieur a #10019) -> False -> no-op strict.
        if not (att_ctx or {}).get("is_prediction"):
            return None
        # `!AreEqual(CurrentAttackDamageProfile, 0xd = Psychic)`. Profil INCONNU (None) -> le noeud
        # `AreEqual` ne peut pas etre VRAI -> pas d'exclusion (meme degradation que la face #179).
        if damage_profile == "Psychic":
            return None
        n = ability_var("MasterAnnihilator", "nrOfHits", is_constant=True)   # ConfigConst 0x2f (=1)
        return for_addition(True, int(n)) if n else None

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
# Direct(1)@0xc0)`) et lue par `IdunBattleLogic.Entities.DSLTriggers$$IsPersistentData` dans le gate de
# `IdunBattle.Entities.Effects.Loki.LetTheGalaxyBurnEffect$$CreateAdditionalHits`. Le tuple = la cle composite native
# (AbilityOrEffect, nom de la donnee) ; PARTAGEE entre le poseur (runner/.../let_the_galaxy_burn.py),
# le nettoyeur (Reset) et ce lecteur -> une seule source de verite.
# #270-r1-r1 : `TriggeredAbilityType`, PAS `EffectType` -- le meme ordinal 1482 nomme
# `PrioritisedEfficiency_ExtraMovement` en `EffectType`. Le discriminant est le symbole natif deja
# cite ci-dessus (`LetTheGalaxyBurnAbility$$.cctor`, une ability TRIGGERED).
LET_THE_GALAXY_BURN_PERSISTENT_KEY = (TriggeredAbilityType.LetTheGalaxyBurn,   # 0x5ca = 1482
                                      "LetTheGalaxyBurn")


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
        (IdunBattleLogic.Entities.DSLTriggers$$HasTileStatusEffect) — **GENERIQUE** : n'importe quel status-effect de tuile, pas un type precis ;
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
        # `IdunBattleLogic.Entities.DSLTriggers$$IsPersistentData(0x5ca, Self@0x148, Get(<statique>)) — flag intra-attaque arme par
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
        # `CreateTargetSelector` = `Friends(Owner@+0x30, AdjacentUnits(Owner@+0x30, unique, 3), 3)`
        # -- LU (#943-r7). `AdjacentUnits(o)` = `Units(AdjacentTiles(o)) - o`, donc l'ENUMERATION
        # part du PORTEUR, sur la liste STOCKEE : `is_adjacent(owner, cible)`, pas l'inverse.
        elev_by_pos, neigh_by_pos = _adjacency_channels(c)
        if not _bq.is_adjacent(op, tp, elev_by_pos, neigh_by_pos):
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

    NIVEAU D'ABILITY — le seul point ou 1224 SOLLICITE le port autrement que 1223. Le natif lit
    `IdunBattle.Entities.Effects.BaseEffect$$GetAbilityState` =
    `IdunBattleLogic.Entities.DSLSelectors$$AbilityStateFromEffect(<noeud EFFET>)`, c.-a-d.
    l'`AbilityStateReference` BAKEE DANS L'EFFET a la pose, donc celle de la SOURCE (Ragnar). Pour
    1223 porteur == source, l'ecart y serait INOBSERVABLE ; pour **1224 ils different par
    construction** — le porteur est un Space Wolf qui n'a PAS l'ability.

    FERME PAR #382 : `engine.entities.effects_state.baked_ability_state` lit desormais l'etat de la
    SOURCE (`EffectComponent.SourceUnitId`, publie par le capteur) pour les DEUX seams. `self.
    ability_level` / `self.ability_variables_multiplier` valent donc ici ceux de Ragnar, pas ceux du
    porteur. MESURE, MC1_67 / 777, Ragnar `PassiveAbilityLevel=1` / Ulf 50 (regime DISSOCIE, le seul
    ou les deux modeles se separent — `buildNormalizedBC` pose 50 partout) :

        natif    n=4  [2679, 3724, 2879, 3771]                     # extraHits[1] = 1, niveau SOURCE
        port     n=4  [2679, 3724, 2879, 3771]                     # apres #382
        (avant)  n=6  [2679, 3724, 2879, 3771, 3273, 3750]         # extraHits[50], niveau PORTEUR

    Le MULTIPLIER de rarete est DISSOCIE lui aussi (mesure : source 200, porteur 180), et il reste
    per-unite meme sous normalisation -> il touche AUSSI la face CRIT (`extraCritDmg` est la seule
    variable scalee par lui). Garde : `test_effect_source_ability_state_live.py` ; repro :
    `probe_382_effect_source_ability_state.py`."""

    def create_effect_hits_bonus_for_attack(self, is_normal_attack: bool = True,
                                            att_ctx: "Mapping | None" = None) -> EffectBonus | None:
        # IsCharging (IdunBattleLogic.Entities.DSLTriggers$$IsCharging -> BattleQuery$$IsCharging).
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
        evalue), et son consommateur est `max(0, GetStat(10) + somme)`.

        ⚠ `get_OwnerIsCaster` etait rendu par le CANAL jusqu'a #589-r1-r1 : le balayage ne voyait
        que les effets de l'ATTAQUANT. Il a MIGRE ICI, a sa place native, quand le balayage s'est
        aligne sur l'univers natif (`board_effect_carriers`) pour `EmpyricAmbush` (1578), porte par
        la CIBLE. Sans lui, un Ragnar SPECTATEUR EN CHARGE bufferait le crit d'un tiers.
        NB : la face COUPS (`create_effect_hits_bonus_for_attack`) n'a PAS besoin de ce geste --
        son agregateur (`hits_bonus_from_effects`) balaie toujours les seuls effets de
        l'attaquant."""
        if not owner_is_caster(att_ctx):                    # get_OwnerIsCaster
            return None
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
        # IsCharging (IdunBattleLogic.Entities.DSLTriggers$$IsCharging -> BattleQuery$$IsCharging).
        # PAS de gate is_normal_attack / is_melee : le decompile n'a QUE ces deux noeuds.
        if not is_charging_attack(att_ctx):
            return None
        n = ability_var("UnstoppableFerocity", "extraHit",
                        is_constant=True)          # GetNumberConstant(config, 0x2b)
        return for_addition(True, int(n)) if n else None


class RedThirstExtraDamageAndHitEffect(BaseEffect):
    """`RedThirst_ExtraDamageAndHit` (effet 0x52a = 1322) -- owner-effect PERMANENT du summon
    `bloodSmnIntercessor` << Jump Pack Intercessor >> (et du npc `bloodNpc1Intercessor`), qui porte
    le passif `RedThirst` (`TriggeredAbilityType` 0x4e1 = 1249). DEUX canaux distincts sous UNE
    active-condition de PV.

    i2 : « If this unit is at or below {healthPct}% Health, it gains +{extraDmg} Damage and scores
    +{extraHit} hit when charging. »

    POSE -- `IdunBattleLogic.Entities.Abilities.Triggered.Loki.RedThirstAbility` a pour parent
    `IdunBattle.Entities.Abilities.AOwnerEffectTriggeredAbility` (`frida/classes.tsv`) et n'override
    QUE `$$GetEffectType`, dont le corps ENTIER est `return 0x52a` : l'appariement ability -> effet
    est LU, pas devine. Le reste vient de la base (`CreateTrigger =
    OnOwnerSpecificAbilityInit(this.AbilityType)`, `CreateBehaviour = If(CreateCondition(...),
    AddEffect(GetEffectType(), AbilityState(Owner), source = Owner, targets = Owner,
    options = <Nullable ZERO>))`) -- owner-effect PERMANENT pose a l'init, exactement le patron
    `ToughToKill` / `Vitarus` / `HammerOfWrath`. Cote port : `factory.ABILITY_INIT_OWNER_EFFECTS
    ["RedThirst"]`.

    `IdunBattle.Entities.Effects.Loki.RedThirst_ExtraDamageAndHitEffect$$.ctor` =
    `BaseEffect(AbilityOrEffect(<0x4e1>), hasAutomaticActivation = 1)` -- les trois corps ci-dessous
    lisent donc TOUS la config de l'ability `RedThirst`.

    ## ACTIVE-CONDITION -- `..._ExtraDamageAndHitEffect$$CreateActiveCondition`

        HealthPctIsBelowOrEqual( Owner@<DSLSelectors+0x30>,
                                 ConfigConst(0x4e1 = RedThirst,
                                             Owner@<DSLSelectors+0x30>,
                                             AbilityConstantType.healthPct = 0x4f) )

    `IdunBattleLogic.Entities.DSLTriggers$$HealthPctIsBelowOrEqual(unit, percentage)` alloue un
    `IdunBattle.Entities.Conditions.StatPercentageIsBelowOrEqualAbilityTrigger` sur la stat
    **5 = HEALTH** -> `(current / max) <= (healthPct / 100)` en Fix64. `healthPct` =
    `gameconfig.ability("RedThirst").constants["healthPct"]` = **50**. MEME noeud, MEME cle et MEME
    comparaison entiere exacte que `HammerOfWrathConditionalDamageEffect` (`loki/status.py`) : pour
    des PV entiers la division Fix64 ne bascule jamais autrement, et l'egalite au bord
    (`2*current == max`) est rendue `0.5` exact -> `<=` VRAI.

    PAS d'`active_condition_ported`, et c'est le regime des **13** classes qui surchargent
    `is_active` : `refresh_effects.py::refresh_stat_modifier_effects` re-ecrit `e.active` depuis
    `is_active(...)` pour toute classe qui surcharge la methode, et `EffectsState.active_effects`
    lit la CONJONCTION `e.active and e.is_active(unit_state)`. L'instance seedee nait `active = True`
    (`BaseEffect.active`), donc c'est bien la condition portee qui tranche des le premier tour.

    ## CANAL DEGAT -- `..._ExtraDamageAndHitEffect$$CreateEffectDamageBonusForAttack`

        EffectBonus.ForAddition( get_OwnerIsCaster,
                                 ConfigVar(0x4e1 = RedThirst, Owner@<DSLSelectors+0x30>,
                                           AbilityVariableType.extraDmg = 8) )

    **UN SEUL noeud de trigger** : ni `IsCharging`, ni `IsMeleeAttack`, ni `IsNormalAttack` -- le
    bonus de degat vaut pour TOUTE attaque du porteur des que l'active-condition tient. La prose i2
    (« gains +extraDmg Damage and scores +extraHit hit **when charging** ») rattache la charge aux
    DEUX termes ; le decompile ne la met que sur le second, et c'est le decompile qui fait foi.
    `get_OwnerIsCaster` est RENDU PAR LE CANAL (`_attacker_effect_bonuses` n'itere que les effets de
    l'ATTAQUANT) -- l'appeler ici fermerait le gate a tort, les cles `owner_id`/`att_id` n'etant
    posees que par les agregateurs CRIT.

    ## CANAL COUPS -- `..._ExtraDamageAndHitEffect$$CreateEffectHitsBonusForAttack`

        EffectBonus.ForAddition( get_OwnerIsCaster & IsCharging(Owner@<DSLSelectors+0x30>,
                                                                Target@<DSLSelectors+0x60>),
                                 ConfigConst(0x4e1 = RedThirst, Owner@<DSLSelectors+0x30>,
                                             AbilityConstantType.extraHit = 0x2b) )

    Calque strict de `UnstoppableFerocityOwnerEffect` (1032) et de `SagaOfTheWarriorBornOwnerEffect`
    (1223) ci-dessus : DEUX noeuds, aucun `IsNormalAttack`, aucun `IsMeleeAttack`. Gate = le FOYER
    PARTAGE `effects/base.py::is_charging_attack`, alimente par `engine/battle_query.py::is_charging`
    (`AreEntitiesAdjacent(caster, target) && UnitComponent.ChargedUnitIds@+0x190.Contains(target.Id)`)
    -- cote COMBAT via `runner/damage_model.py::build_hits_board`, cote PREDICTION via
    `playbook/prediction/normal_attack.py`. Ce n'est PAS `HasFlag(UnitFlag.Moved)`.
    C'est l'entree #8 de l'inventaire d'`IsCharging` (`docs/rl/case-ischarging-hits-channel.md` SS2),
    la derniere du canal COUPS a etre restee « absente (canal absent) ».

    ## MAGNITUDES -- une VARIABLE et une CONSTANTE, et la difference est LUE
    * `extraDmg` = `ConfigVar` (`AbilityVariableType` 8) -> indexee par le niveau de l'ability
      SOURCE, et **listee dans `variablesAffectedByRarityBonus`** du gameconfig de `RedThirst` ->
      scalee par le multiplier de rarete (`ability_var(..., multiplier_pct=...)` applique la regle
      par-config, il ne la devine pas).
    * `extraHit` = `ConfigConst` (`AbilityConstantType` 0x2b) -> **1**, ni indexee par niveau ni
      scalable, exactement comme chez `UnstoppableFerocity` et `PowerTrip_FullHealth`.

    NIVEAU : `RedThirst` est un PASSIF -> cascade `ability_level` puis repli `level`, la meme que
    `SagaOfTheWarriorBornOwnerEffect`. `engine.entities.effects_state.baked_ability_state` fait que
    ces champs portent l'etat de la SOURCE de l'effet (#382) ; ici porteur == source (l'owner-effect
    est pose sur son propre porteur), donc l'ecart y est INOBSERVABLE.

    NON COUVERT, nomme : le `CreateTargetSelector` de la classe n'existe pas (elle ne declare que le
    `.ctor` et les trois corps ci-dessus dans les tables) -- l'effet est un SELF-effect strict, pas
    une aura."""

    def is_active(self, unit_state: "Mapping | None" = None) -> bool:
        """`CreateActiveCondition` : `HealthPct(Owner) <= GetNumberConstant(0x4f = healthPct)`.
        `unit_state` = `{hp, max_hp}` (convention `PowerTripFullHealthEffect` /
        `AnvilShieldBlockChanceBelowHealthCapEffect` / `HammerOfWrathConditionalDamageEffect`).
        PV non captes -> True (degradation fidele : on ne masque pas l'effet a tort)."""
        s = unit_state or {}
        hp, mx = s.get("hp"), s.get("max_hp")
        pct = ability_var("RedThirst", "healthPct", is_constant=True)   # GetNumberConstant(0x4f) = 50
        if hp is None or mx is None or not mx or pct is None:
            return True
        return 100 * int(hp) <= int(pct) * int(mx)

    def create_effect_damage_bonus_for_attack(self, is_ranged: "bool | None" = None,
                                              has_moved: "bool | None" = None,
                                              target_traits: "frozenset[str] | None" = None,
                                              is_prediction: bool = False,
                                              is_normal_attack: "bool | None" = True,
                                              target_armor_reduced: "bool | None" = None,
                                              att_ctx=None) -> EffectBonus | None:
        # `ForAddition(get_OwnerIsCaster, ConfigVar(8 = extraDmg))` -- UN SEUL noeud de trigger, et
        # il est rendu par le canal (balayage restreint aux effets de l'ATTAQUANT). AUCUN
        # `IsCharging` ici : la charge ne gate que le canal COUPS (cf. docstring de classe).
        lvl = self.ability_level if self.ability_level is not None else self.level
        v = ability_var("RedThirst", "extraDmg", lvl,
                        multiplier_pct=self.ability_variables_multiplier)   # ConfigVar 8
        return for_addition(True, int(v)) if v else None

    def create_effect_hits_bonus_for_attack(self, is_normal_attack: bool = True,
                                            att_ctx: "Mapping | None" = None) -> EffectBonus | None:
        # IsCharging (IdunBattleLogic.Entities.DSLTriggers$$IsCharging -> BattleQuery$$IsCharging).
        # PAS de gate is_normal_attack / is_melee : le decompile n'a QUE ces deux noeuds.
        if not is_charging_attack(att_ctx):
            return None
        n = ability_var("RedThirst", "extraHit",
                        is_constant=True)          # GetNumberConstant(config, 0x2b) = 1
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
    _SOURCE_EFFECT_TYPE = EffectType.DefenderOfTheGreaterGood_ExtraHits     # 0x49f -- l'effet NON-drone vise par `EntitiesIsNotTargetOfEffect`

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
        # ⚠ LES DEUX TIERS N'ONT PAS LE MEME SUBSTRAT NATIF (#433-r4-r1-r4-r2-r1-r1-r1-r1), et les
        # decider par la MEME distance melangeait une liste STOCKEE et un disque CUBE :
        #   * `AdjacentFriends` -> `DSLSelectors$$AdjacentTiles` -> liste stockee du
        #     `ConnectivityComponent` + porte `|dElev| < 2` -> canal `battle_query.is_adjacent` ;
        #   * `SurroundingFriends(2)` -> `SurroundingTiles` -> `BattleQuery.u003CIterateSurrounding
        #     Tilesu003Ed__6$$MoveNext` (cube, sans porte) -> la distance nue EST le mirror exact.
        # CABLE EN MEME TEMPS que sa JUMELLE `extra_damage_aura::DefenderOfTheGreaterGoodExtraDmg
        # Effect.aura_selector_covers` : c'est le MEME `GetBaseBuffTargetSelector`, les separer
        # ouvrirait une divergence entre l'axe DEGAT et l'axe COUPS du meme passif.
        elev_by_pos, neigh_by_pos = _adjacency_channels(c)
        adjacent = bool(_bq.is_adjacent(tuple(op), tuple(ap), elev_by_pos, neigh_by_pos))
        tau_ring = (hexgeo.distance(tuple(op), tuple(ap)) <= 2
                    and c.get("att_faction") == self._TAU_FACTION)          # UnitsFromFaction(2, Tau)
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
# #270-r1-r1 : `EffectType` -- la 4e composante du tuple porte litteralement le nom du membre.
SWARM_HIT_REDUCTION_SOURCE = ("statmod", EffectType.Swarm_HitReduction, None,   # 1021
                              "Swarm_HitReduction")


class Swarm_HitReductionEffect(BaseEffect):
    """`Swarm_HitReduction` (effet 0x3fd=1021, StaticStatModifierEffect) — malus EXTRA_HITS(17) self du
    trait **Swarm** : « For each member defeated, the swarm attacks with 1 fewer hit » (i2, #60).

    Natif : `IdunBattleLogic.Entities.Abilities.Active.Loki.SwarmAbility$$CreateBehaviour` (ability 0x3ff=1023 accordée par le trait) =
    `AddOrUpdateStaticStatModifierEffect(Self@+0x148, 0x3fd, statType 0x11=EXTRA_HITS,
        Negative(Min(Difference(StatAmount(Self, 20, part 3=INITIAL), Const1@+0xc0),
                     StatAmount(Self, 20, part 4=MISSING))))`
    = **−min(nrOfMembers − 1, membres MORTS)** (plancher structurel 1 hit). Stat 20 = NUMBER_OF_MEMBERS,
    résolue par le handler jumptable 0x14 de `IdunBattle.Entities.UnitExtensions$$GetStat` (IdunBattle.Entities.UnitExtensions$$GetStat+0x859) → NumberOfMembersComponent
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
        n = int(member_count)
        if n < 2:
            self._bound_amount = None
            return
        missing = group_unit_stat_part(int(StatPart.MISSING),          # part 4
                                       int(member_total_hp), n, int(current_hp))
        self._bound_amount = -min(n - 1, missing)

    def get_stat_modification_stat(self) -> "int | None":
        return StatType.EXTRA_HITS if self._bound_amount else None    # StatType.EXTRA_HITS

    def get_stat_modification_amount(self) -> "int | None":
        return self._bound_amount


class ShroudPsalmEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.ShroudPsalmEffect` (EffectType 0x556 = 1366 `ShroudPsalm`) --
    MALUS DEFENSEUR de coups, gate ATTAQUE NORMALE. #419-r1-tr9-r4-r1-r2.

    Natif, relu au decompile (2026-08-02, `rnca9r7q6c`) --
    `IdunBattle.Entities.Effects.Loki.ShroudPsalmEffect$$CreateEffectHitsBonusForAttack` :

        EffectBonus.ForAdditionWithMinimum(
            trigger  = get_OwnerIsTarget & IsNormalAttack,
            addition = Negative(Get(GetNumberConstant(config, 0x2c = hitsReduction))),
            minimum  = Get(1))

    Les DEUX noeuds du trigger sont lus dans cet ordre exact
    (`IdunBattleLogic.Entities.DSLTriggers$$get_OwnerIsTarget` puis
    `IdunBattleLogic.Entities.DSLTriggers$$IsNormalAttack`, joints par
    `IdunBattle.DSL.AbilityTrigger$$op_BitwiseAnd`). AUCUN noeud melee/ranged, AUCUN gate de profil,
    AUCUN gate de distance : la reduction porte sur TOUTE attaque NORMALE recue par le porteur.
    `IdunBattleLogic.Entities.DSLFormulas$$Get(int)` a le MEME corps que `$$Direct(int)` (meme classe
    de formule `DAT_183395500`, meme ctor) -- c'est une constante directe, pas un acces indexe.

    MAGNITUDE : `GetNumberConstant(0x2c)` = la CONSTANTE `hitsReduction` de l'ability `ShroudPsalm`
    (= **2**, meme slot 0x2c que `parryHitReduction` / `camouflageHitReduction_1` /
    `diminutiveHitReduction` / `FightingRetreat.hitsReduction`). Constante, donc jamais indexee par
    niveau ni scalee par le multiplier de rarete.
    i2 : << Up to 2 other friendly units gain 2 levels of Machine Vengeance and are affected by
    Shroud Psalm until the start of their next turn. Affected units have +728 Armour and normal
    attacks against them score -2 hits, to a minimum of 1. >>

    QUI POSE L'EFFET (#436 -- un effet au registre sans poseur reste inerte en silence) :
    `IdunBattleLogic.Entities.Abilities.Active.Loki.ShroudPsalmAbility$$ExecuteBehaviour`, sur le
    selecteur `First(SortByFormula(Randomize(Friends(Caster, AllUnits - Caster, 3))), <formule>,
    ConfigConst(0x11 = nrOfTargets = 2))` -- donc **jusqu'a 2 ALLIES du caster, caster EXCLU**, pour
    `TurnsFromRounds(1)`. Le meme `ExecuteBehaviour` pose deux AUTRES effets sur les memes cibles :
    `AddStaticStatModifierEffect(., 0x55a = 1370 ShroudPsalm_Armor, stat 0x10, ConfigVar(0x1b =
    extraArmor[L]))` et `AddEffect(0x555 = 1365 MachineVengeance, ., Get(ConfigConst 0x73))`. Seul
    0x556 porte le canal COUPS.

    PLANCHER `minimum = Get(1)` : le natif l'applique DANS
    `IdunBattle.Core.Services.DamagePrediction$$GetAttackHits`, juste apres l'addition du bonus
    concerne -- `hits = Math.Max(hits, Math.Min(base, minimum))`. Le port l'approxime par le plancher
    GLOBAL `max(min(1, base), .)` de `services.attack_hits_formula` : identique tant que tous les
    minimums valent 1 (c'est le cas de TOUS les porteurs du canal : Parry, LightCover, Camouflage,
    Diminutive, BigTarget, FightingRetreat, ShroudPsalm). Le port INTEGRAL du clamp par-effet reste
    le chantier separe deja nomme dans l'entete de `attack_hits_formula`."""

    def create_effect_hits_malus_for_defense(self, is_melee: bool | None = None,
                                             damage_profile: str | None = None,
                                             defender_on_cover: bool | None = None,
                                             dist: int | None = None,
                                             is_normal_attack: bool = True,
                                             att_ctx: Mapping | None = None) -> EffectBonus | None:
        # trigger natif = `get_OwnerIsTarget & IsNormalAttack` : le SEUL gate est la nature du
        # VECTEUR (attaque normale vs attaque d'ABILITY). Aucun gate melee/ranged.
        if not is_normal_attack:
            return None
        n = ability_var("ShroudPsalm", "hitsReduction", is_constant=True)   # ConfigConst 0x2c (=2)
        return for_addition(True, -int(n)) if n else None


class VoltagheistFieldExtraHitEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.VoltagheistField_ExtraHitEffect` (EffectType 0x565 = 1381
    `VoltagheistField_ExtraHit`) -- +coups de l'ATTAQUANT, gate ATTAQUE NORMALE.
    #419-r1-tr9-r4-r1-r2 ; jumeau STRUCTUREL exact de `PowerTrip_FullHealthEffect` (memes deux noeuds,
    ordre inverse, meme cle de constante).

    Natif, relu au decompile (2026-08-02, `rnca9r7q6c`) --
    `IdunBattle.Entities.Effects.Loki.VoltagheistField_ExtraHitEffect$$CreateEffectHitsBonusForAttack` :

        EffectBonus.ForAddition(
            trigger  = get_OwnerIsCaster & IsNormalAttack,
            addition = Get(GetNumberConstant(config, 0x2b = extraHit)))

    PAS de `minimum` (`ForAddition`, pas `ForAdditionWithMinimum`) -- coherent : c'est une addition.
    MAGNITUDE : constante `extraHit` de l'ability `VoltagheistField` = **1** (meme cle 0x2b que
    `PowerTrip.extraHit` / `Waaagh.extraHit` / `UnstoppableFerocity.extraHit`).
    i2 : << If Health is restored to this unit, the amount restored is reduced by 50% and it then
    scores +1 hit with normal attacks until the end of its turn. >>

    QUI POSE L'EFFET (#436) :
    `IdunBattleLogic.Entities.Abilities.Triggered.Loki.VoltagheistField_OnRepairAbility` --
    `CreateTrigger` = `On(0x30 = 48 UnitRepaired) & get_OwnerIsTarget` (le porteur du passif est la
    CIBLE du soin), `CreateBehaviour` = `AddEffect(0x565, <abilityStateRef>, Target, Owner,
    <duree UntilEndOfTurn>)`. L'effet n'existe donc QUE dans la fenetre qui suit un soin recu.
    La seconde moitie du passif (`-50%` sur le montant soigne) est l'effet SEPARE 0x566 = 1382
    `VoltagheistField_RepairReduction`
    (`IdunBattle.Entities.Effects.Loki.VoltagheistField_RepairReductionEffect$$CreateEffectRepairBonus`),
    canal REPAIR -- hors du canal COUPS, non porte ici.

    PORTEURS : `admecNpc3Electropriest` / `admecNpc3ElectropriestSurv` (npc) et
    `admecSmnElectropriest` (summon d'ENVIRONNEMENT -- son unique invocateur est l'ability
    `EnvFactionSummons:AdeptusMechanicus`, portee par aucune unite). Confrontation = greffe du PASSIF
    sur une unite du pool (`catalog_inject.graft_passive_ability`) + un soin recu."""

    def create_effect_hits_bonus_for_attack(self, is_normal_attack: bool = True,
                                            att_ctx: "Mapping | None" = None) -> EffectBonus | None:
        # trigger natif = `get_OwnerIsCaster & IsNormalAttack` : ce canal n'est evalue QUE pour
        # l'attaque du PORTEUR (get_OwnerIsCaster implicitement vrai, meme traitement que
        # `PowerTripFullHealthEffect`), le seul gate restant est la nature du vecteur.
        if not is_normal_attack:
            return None
        n = ability_var("VoltagheistField", "extraHit", is_constant=True)   # ConfigConst 0x2b (=1)
        return for_addition(True, int(n)) if n else None


#: Cle de la LISTE persistante d'attaquants deja servis (`AddToPersistentDataList` /
#: `IsInPersistentDataList` de `LegendaryCommander_ExtraHitsEffect`). Le sac natif est porte par
#: l'`EffectSource` (custoTrajann) et indexe par `GetPersistentDataId(<AbilityOrEffect de l'effet>)`
#: puis par la `dataKey` = `EntityId(Owner@0x30)` = l'id de l'ENNEMI marque ; la valeur empilee est
#: `EntityId(Caster@0x48)` = l'id de l'ATTAQUANT. Le port aplatit en cle composite
#: `(ability_or_effect, data_key)` (cf. `runner/components.py::PersistentDataComponent`), d'ou ce
#: helper partage entre le LECTEUR (`LegendaryCommanderExtraHitsEffect`) et l'ECRIVAIN
#: (`runner/operations/triggers/loki/legendary_commander.py`) -- un seul foyer, jamais deux formes.
LEGENDARY_COMMANDER_EXTRA_HITS = EffectType.LegendaryCommander_ExtraHits            # 0x573 `EffectType.LegendaryCommander_ExtraHits`


def legendary_commander_marked_key(marked_unit_id: int) -> tuple:
    """Cle composite du port pour la liste des attaquants deja servis CONTRE `marked_unit_id`."""
    return (LEGENDARY_COMMANDER_EXTRA_HITS, int(marked_unit_id))


class LegendaryCommanderExtraHitsEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.LegendaryCommander_ExtraHitsEffect` (effet 0x573 = 1395,
    passif `LegendaryCommander` de `custoTrajann`) -- AURA source-side sur l'axe COUPS, et le SEUL
    consommateur du canal gate en NEGATION (`!IsNormalAttack`). #419-r1-tr9-r4-r1-r2-r1.

    i2 : << Whenever a friendly unit uses an Active ability, enemies adjacent to it take
    +[extraDmg] damage from friendly Characters. If the affected enemies are also adjacent to
    Trajann, friendly Characters score [nrOfHits] additional hits against them with their first
    attack that is not a normal attack. >>

    POSE -- `IdunBattleLogic.Entities.Abilities.Triggered.Loki.LegendaryCommanderAbility$$CreateBehaviour`
    = `AddEffect(0x572 = 1394, <abilityStateRef>, Owner@0x30, Owner@0x30, <turns VIDE>)
       & AddEffect(0x573 = 1395, <abilityStateRef>, Owner@0x30, Owner@0x30, <turns VIDE>)`.
    Les DEUX effets vivent donc sur TRAJANN (le porteur du passif), jamais sur les ennemis : ce sont
    les `EffectComponent.Targets @+0x48` -- re-derives par le `CreateTargetSelector` ci-dessous --
    qui designent les ennemis affectes (modele `effect_targets.py` : << le PORTEUR n'est pas la
    CIBLE >>). D'ou le canal AURA, et non le canal DEFENSEUR.

    ⚠ `LegendaryCommander_ExtraHitsEffect$$.ctor` est le corps DEDUPLIQUE de deux classes : les
    lambdas `EffectsDatabase.<InitializeEffects>b__14_403` / `b__14_404` l'appellent toutes deux sur
    des `Il2CppClass*` DISTINCTS (0x572 = `ExtraDamage`, 0x573 = `ExtraHits`). Le nom du ctor ne dit
    donc PAS l'identite de classe (piege `reference_ctor_name_is_not_class_identity`) -- les deux
    effets ont bien chacun leur canal (`CreateEffectDamageBonusForAttack` pour 1394,
    `CreateEffectHitsBonusForAttack` pour 1395).

    ## SELECTEUR -- `LegendaryCommander_ExtraHitsEffect$$CreateTargetSelector`, lu verbatim

        sel = Friends( of = Owner@0x30, entities = AllUnits@0x20, selectionType = 3 )
        sel = Filter( sel, HasUsedActiveAbilityThisTurn(Subject@0x68) )
        sel = AdjacentEnemies( unit = sel, unique = 1, selectionType = 3 )
        sel = Filter( sel, IsAdjacent(Owner@0x30, Subject@0x68, 3) )

    Le tronc des TROIS premiers noeuds est celui de la base
    `ALegendaryCommander_BaseEffect$$CreateTargetSelector` (partage avec 1394) ; le QUATRIEME
    (`IsAdjacent(Owner, Subject)`) n'existe QUE sur 1395 -- c'est exactement le << If the affected
    enemies are ALSO adjacent to Trajann >> de l'i2. `Friends(Owner, AllUnits)` n'a AUCUNE
    soustraction `- Owner` : Trajann est ami de lui-meme, donc SON propre cast d'active arme l'aura.

    ## TRIGGER -- `$$IsValidAttack(<selecteur>)`, lu verbatim (ordre des `op_BitwiseAnd` du corps)

        get_OwnerIsTarget
      & AreFriends( Caster@0x48, EffectSource(<selecteur passe>) )
      & !IsNormalAttack( CurrentAbility@0x88 )
      & !( TriggeringAbilityIsNormalAttack & IsPartialAttackAbility(CurrentAbility@0x88) )

    et `$$CreateEffectHitsBonusForAttack` l'enveloppe :

        EffectBonus.ForAddition(
            trigger  = ( IsValidAttack(Effect@0x38)
                         & !IsInPersistentDataList(<AbilityOrEffect>, EffectSource(Effect@0x38),
                                                   EntityId(Owner@0x30), EntityId(Caster@0x48)) )
                       & IsFirstHitGroupInAttack(),
            addition = ConfigVar(0x2f = nrOfHits, <abilityState>, config@+0x60) )

    `get_OwnerIsTarget` = << la CIBLE DE L'EFFET est la cible de l'attaque >> (la boucle native
    ecrit `AbilityEntities+0x18 (Owner) <- la cible de l'effet`, cf.
    `create_aura_hits_bonus_for_attack` de la base) -> cote port c'est `aura_selector_covers(tgt_id)`.

    ## `IsFirstHitGroupInAttack` -- UNIQUE consommateur du canal `hitGroupIndex`
    `IdunBattleLogic.Entities.DSLTriggers$$IsFirstHitGroupInAttack` ->
    `Idun.Source.IdunBattle.Logic.Entities.Triggers.IsFirstHitGroupInAttackTrigger$$ShouldTrigger` ->
    `IdunBattle.Entities.Abilities.AbilityEntities$$get_IsFirstHitGroup`, qui rend
    `Nullable<bool>( (hitGroupIndex.GetValueOrDefault() == 0) && hitGroupIndex.HasValue )` sur le
    `Nullable<int>` @`AbilityEntities+0x110`. Ce champ n'a qu'UN peupleur sur la face PREDICTION
    (`IdunBattle.Core.Services.DamagePrediction$$GetAttackHits` le construit depuis son 3e parametre)
    et le COMBAT le lui passe depuis `OngoingAttack+0x34`
    (`IdunBattle.Operations.AttackDamageOperation$$Execute` -> `$$GetAttackHits`, slot 0xb6).
    `IdunBattle.Core.OngoingAttack$$.ctor` initialise ce bloc a **0** -> la phase d'ARME (le seul
    etage que le port fait traverser la formule) est bien le groupe **0**. Cf.
    `services/attack_hits_formula.py::attack_hits_with_modifiers(hit_group_index=...)`.

    ## `!IsInPersistentDataList` -- le << FIRST attack >>
    L'ECRIVAIN est le TARGET-TRIGGER de l'effet, porte a part
    (`runner/operations/triggers/loki/legendary_commander.py`) :
    `$$CreateTargetTrigger` = `On(0xa = AttackDamageAttack) & IsValidAttack(Effect@0x38)` ->
    `$$CreateTargetTriggerBehaviour` = `AddToPersistentDataList(<AbilityOrEffect>,
    EffectSource(Get(effect)), EntityId(Owner@0x30), EntityId(Caster@0x48))`. La cle est donc
    (ennemi marque -> liste des attaquants deja servis), le sac vivant sur TRAJANN.
    `$$GetMarkCasterBehaviour` a le corps IDENTIQUE et `$$IsCasterMarked` le pendant lecteur, mais
    AUCUN des deux n'a d'appelant (xrefs = metadata IL2CPP seule) : ce sont des doublons morts, le
    couple VIVANT est `CreateTargetTrigger`/`CreateTargetTriggerBehaviour`.
    `$$RevertInternal` = `ExecuteBehaviour(ClearPersistentData(<AbilityOrEffect>,
    EffectSource(Get(effect)), EntityId(Target@0x60)))` -- purge la cle d'UNE cible au retrait de
    l'effet ; `AddEffect` posant 1395 SANS duree, le retrait n'a aucun vecteur porte (residu nomme).

    ## `IsPartialAttackAbility` -- PORTE (#419-r1-tr9-r4-r1-r2-r1a), et l'inertie du 1er conjoint
    `Idun.Source.IdunBattle.Logic.Entities.Triggers.AbilityIsPartialAttackAbilityTrigger$$IsPartialAttack`
    teste l'appartenance du `CurrentAbility` a l'un de DEUX `HashSet` statiques
    (`StaticBattleRules.TriggeredAbility$$IsPartialAttackAbility` pour un `TriggeredAbilityType`,
    `StaticBattleRules.Effect$$IsPartialAttack` pour un `EffectType`) et rend FAUX pour toute
    ACTIVE. Les deux ensembles sont desormais LUS -- pas au decompile (le `.cctor` de
    `StaticBattleRules.Effect` fait 0xd120 octets et depasse le budget de decompilation, ce sur quoi
    #1103 et #1107 ont bute) mais par les OCTETS du PE :
    `probe_419r1tr9r4r1r2r1a_partial_attack_sets.py`. Ils valent
    `{DeathToTheFalseEmperor 1032, HazeOfCorruption 1076}` et
    `{HazeOfCorruption_DamageTransfer 1077}` -- foyer `services/static_battle_rules.py`, ou le
    discriminant de type PERDU par le canal (le port thread un entier nu) est nomme et son sens
    mesure (SUR-approximation, donc RESTRICTIVE sous cette negation).

    ⚠ RESIDU DEPLACE D'UN CRAN, ET IL EST MESURE : c'est le PREMIER conjoint qui est inerte.
    `TriggeringAbilityIsNormalAttack` = `IsNormalAttack(TriggeringAbility@DSLSelectors+0x90)` = le
    canal `trigger_ability_type` du board de coups -- et ce canal n'est alimente QUE par la face
    NORMALE (`damage_ops/normal.py` passe `trigger_ability_type=triggering_ability` a
    `build_hits_board`) ; la face ABILITY (`damage_ops/ability.py`) ne le passe PAS, il y reste a
    `None`. Or le gate `!IsNormalAttack(CurrentAbility)` juste au-dessus FERME la face normale. La
    conjonction complete ne peut donc mordre sur AUCUNE face portee tant que la face ABILITY
    n'alimente pas ce canal -- ce qui n'est pas fait ici parce que le canal a un AUTRE consommateur
    (`PurgeResponse` 1538, `TriggeringAbilityIs(EffectType 1009 Overwatch_AutoAttack)`) qu'un
    alignement sur `ability_type` ferait firer a tort des que l'ordinal coincide.
    Residu #419-r1-tr9-r4-r1-r2-r1a-r1.

    ## FACE PREDICTION -- structurellement INERTE, et c'est le natif
    Les deux facades de prediction qui traversent `attack_hits_with_modifiers`
    (`make_normal_attack_predictions` et le fold `GetAdditionalDamagePrediction`) portent
    `is_normal_attack = True` : le gate `!IsNormalAttack` les ferme toutes deux. La prediction d'une
    attaque d'ABILITY, elle, n'interpose PAS la formule (cf. l'entete de `attack_hits_formula`,
    point 4). Le seul vecteur ou cet effet mord est donc le COMBAT, famille ATTACK
    (`runner/operations/damage_ops/ability.py`).

    ## MAGNITUDE
    `ConfigVar(0x2f = nrOfHits)` = une VARIABLE par niveau de l'ability `LegendaryCommander`
    (contraste avec les `ConfigConst` de `PowerTrip`/`Waaagh`/`VoltagheistField`) -> lue au niveau
    d'ability de l'instance, avec le multiplier de rarete que `ability_var` applique SSI la cle est
    dans `variablesAffectedByRarityBonus`."""

    def aura_selector_covers(self, ctx: "Mapping | None" = None) -> bool:
        """`LegendaryCommander_ExtraHitsEffect$$CreateTargetSelector` evalue sur la CIBLE de
        l'attaque (`get_OwnerIsTarget` : `Owner` = la cible de l'EFFET).

        Substrat manquant (positions/equipes/`used_active_by_id` absents du contexte) -> `False` :
        << present != applique >>, jamais un booleen invente."""
        c = ctx or {}
        tgt = c.get("tgt_id")
        oid, opos, oteam = c.get("owner_id"), c.get("owner_pos"), c.get("owner_team")
        pos = c.get("pos_by_id") or {}
        team = c.get("team_by_id") or {}
        used = c.get("used_active_by_id")
        if tgt is None or oid is None or opos is None or oteam is None or used is None:
            return False
        tpos = c.get("t_pos") or pos.get(tgt)
        if tpos is None:
            return False
        if team.get(tgt) is None or team.get(tgt) == oteam:
            return False                                  # `AdjacentEnemies` : ennemi de l'owner
        # 4e noeud, PROPRE a 1395 : `Filter(., IsAdjacent(Owner@0x30, Subject@0x68, 3))`.
        # `IdunBattleLogic.Entities.DSLTriggers$$IsAdjacent` -> `IsAdjacentAbilityTrigger$$
        # ShouldTrigger` -> slot 0x60 = `BattleQuery$$AreEntitiesAdjacent` -> `MovementUtil$$
        # AreTilesAdjacent` = `(|dElev| < 2) & (t1 == t2 || ConnectivityComponent$$IsNeighbour)`
        # -- donc le court-circuit d'identite EN PLUS de la liste stockee (#433-r1, #943-r7).
        elev_by_pos, neigh_by_pos = _adjacency_channels(c)
        if not _bq.are_entities_adjacent(tuple(opos), tuple(tpos), elev_by_pos, neigh_by_pos):
            return False
        # `AdjacentEnemies( Filter(Friends(Owner, AllUnits, 3), HasUsedActiveAbilityThisTurn) , 1, 3)`
        # -- au moins UN allie de l'owner (Trajann INCLUS : aucun `- Owner` dans le `Friends`) ayant
        # utilise une active ce tour est adjacent a la cible. `AdjacentEnemies(X, unique, selType)` =
        # `Enemies(X, Units(AdjacentTiles(X), unique, selType) - X, selType)` : l'ENUMERATION part de
        # CHAQUE ALLIE retenu, donc `is_adjacent(allie, cible)` -- pas l'inverse.
        for uid, p in pos.items():
            if team.get(uid) != oteam or p is None:
                continue
            if not used.get(uid):                         # `HasUsedActiveAbilityThisTurn(Subject)`
                continue
            if _bq.is_adjacent(tuple(p), tuple(tpos), elev_by_pos, neigh_by_pos):
                return True
        return False

    def targets_to_revert_on_exit(self, state, owner_id: int) -> tuple:
        """`LegendaryCommander_ExtraHitsEffect$$RevertInternal` = `ExecuteBehaviour(
        ClearPersistentData(<AbilityOrEffect>, EffectSource(Get(effect)),
        EntityId(Target@<DSLSelectors+0x60>)))` -- la part DATA, lue par le driver
        `runner/operations/refresh_effects.revert_effects_for_exited_targets`.
        #419-r1-tr9-r4-r1-r2-r1b.

        Rend les cles `(source, (1395, uid))` des cibles MARQUEES que le selecteur ne couvre PLUS.
        L'ensemble des marquees est un sur-ensemble suffisant de `targetsToRemove` : sur une cible
        sortie mais NON marquee, `ClearPersistentData` est un no-op (cf. la docstring du driver).

        ⚠ LE CTX PASSE PAR `build_hits_board`, LE FOYER, et pas par une seconde construction.
        `aura_selector_covers` ne lit QUE des donnees d'ETAT (`owner_*`, `pos_by_id`, `team_by_id`,
        `used_active_by_id`, le board) : aucune n'a besoin d'une attaque en cours. L'`att_id` passe
        au foyer est donc le PORTEUR lui-meme -- il n'entre dans aucun des noeuds evalues ici, et
        le prendre ailleurs n'aurait fait qu'inventer un acteur.

        Import DIFFERE et PORTEUR (classe MESUREE) : `runner.damage_model` importe ce module-ci
        (`from ..entities.effects.loki.hits import ...`), donc hisser cet import fermerait le cycle."""
        from ....runner.damage_model import build_hits_board          # differe PORTEUR (cf. supra)
        from ....runner.components import PersistentDataComponent, PositionComponent
        src = self.source if self.source is not None else int(owner_id)
        ent = state.get_entity(int(src))
        comp = ent.get_component(PersistentDataComponent) if ent is not None else None
        if comp is None:
            return ()
        marquees = [k[1] for k in comp.data
                    if isinstance(k, tuple) and len(k) == 2
                    and k[0] == LEGENDARY_COMMANDER_EXTRA_HITS]
        if not marquees:
            return ()                              # aucun sac a balayer -> cout nul hors regime
        oe = state.get_entity(int(owner_id))
        opc = oe.get_component(PositionComponent) if oe is not None else None
        if opc is None:
            return ()                              # porteur hors plateau -> rien de mesurable
        out = []
        for uid in marquees:
            te = state.get_entity(int(uid))
            tpc = te.get_component(PositionComponent) if te is not None else None
            if tpc is None:
                # La cible n'a plus de tuile (morte / retiree) : le natif l'a fait sortir de
                # `Targets` au meme titre, donc la marque part.
                out.append((int(src), legendary_commander_marked_key(int(uid))))
                continue
            board, _auras, _tgt_eff = build_hits_board(
                state, int(owner_id), int(uid), (opc.col, opc.row), (tpc.col, tpc.row),
                is_melee=None)
            # `owner_team` vient du MEME `team_by_id` que le reste du selecteur -- une seconde
            # lecture de l'`OwnerComponent` ici serait un fork silencieux.
            ctx = {**board, "owner_id": int(owner_id),
                   "owner_pos": (opc.col, opc.row),
                   "owner_team": (board.get("team_by_id") or {}).get(int(owner_id))}
            if not self.aura_selector_covers(ctx):
                out.append((int(src), legendary_commander_marked_key(int(uid))))
        return tuple(out)

    def is_valid_attack(self, ctx: "Mapping | None" = None) -> bool:
        """`LegendaryCommander_ExtraHitsEffect$$IsValidAttack(<selecteur>)` -- les QUATRE noeuds, dans
        l'ordre du corps natif."""
        c = ctx or {}
        if not self.aura_selector_covers(c):              # get_OwnerIsTarget
            return False
        # `AreFriends(Caster@0x48, EffectSource(<sel>))` -- `EffectSource` = `EffectComponent.
        # SourceUnit @+0x10` de l'instance (= `BaseEffect.source`), et `AddEffect` la pose sur
        # `Owner@0x30` : source == porteur == Trajann. On lit la source REELLE, pas le porteur.
        src = self.source if self.source is not None else c.get("owner_id")
        team = c.get("team_by_id") or {}
        att = c.get("att_id")
        if att is None or src is None:
            return False
        if team.get(att) is None or team.get(att) != team.get(src):
            return False
        # `!IsNormalAttack(CurrentAbility@0x88)` -- le SEUL gate du canal COUPS pose en NEGATION.
        if c.get("is_normal_attack", True):
            return False
        # `!( TriggeringAbilityIsNormalAttack & IsPartialAttackAbility(CurrentAbility@0x88) )`
        # -- LES DEUX CONJOINTS, depuis #419-r1-tr9-r4-r1-r2-r1a. Le second etait absent parce que
        # ses deux `HashSet` statiques n'etaient pas lisibles (le `.cctor` de
        # `StaticBattleRules.Effect` depasse le budget de decompilation) ; ils le sont maintenant,
        # par les OCTETS du PE (`probe_419r1tr9r4r1r2r1a_partial_attack_sets.py`).
        from ....runner.abilities.attack_type import is_regular_attack   # differe PORTEUR (runner)
        if (is_regular_attack(c.get("trigger_ability_type"))
                and _static_battle_rules.ability_is_partial_attack(c.get("ability_type"))):
            return False
        return True

    def create_aura_hits_bonus_for_attack(self, ctx: "Mapping | None" = None) -> "EffectBonus | None":
        c = ctx or {}
        if not self.is_valid_attack(c):
            return None
        # `!IsInPersistentDataList(<AbilityOrEffect>, EffectSource(Effect), EntityId(Owner),
        # EntityId(Caster))` : l'attaquant a-t-il DEJA ete servi contre CETTE cible ? Le sac est
        # celui de l'`EffectSource` (Trajann). Substrat absent -> liste VIDE -> le natif rend FAUX
        # (`TryGetPersistDataList` sur une cle absente), donc le `!` laisse passer : c'est bien le
        # comportement du natif hors runner, pas une degradation choisie.
        fn = c.get("persistent_data_list")
        if fn is not None:
            src = self.source if self.source is not None else c.get("owner_id")
            served = fn(src, legendary_commander_marked_key(c.get("tgt_id"))) or ()
            if c.get("att_id") in served:
                return None
        # `IsFirstHitGroupInAttack()` -- `get_IsFirstHitGroup` = `HasValue && Value == 0`.
        # Cle ABSENTE = `Nullable` vide cote natif -> le trigger rend FAUX.
        if c.get("hit_group_index") != 0:
            return None
        n = ability_var("LegendaryCommander", "nrOfHits", self.ability_level,
                        multiplier_pct=self.ability_variables_multiplier)   # ConfigVar 0x2f
        return for_addition(True, int(n)) if n else None


#: `TriggeredAbilityType` 0x5da = 1498 -- la CONFIG que lit l'effet 1497 (relique `R_Crit_Maugetar`,
#: `allowedUnits = ['eldarMauganRa']`). Le nom est le SEUL discriminant : l'ordinal 1498 nomme
#: `ExemplarOfTheMontka` dans `EffectType`, et `Maugetar` apparait en `activeAbilities` d'un npc --
#: c'est une INVERSION DE VOIE, pas une active (#270-c).
_MAUGETAR_ABILITY = "Maugetar"
#: callable `(owner_id, ability_name) -> (level, multiplier)` -- mirror de
#: `IdunBattle.Entities.Effects.BaseEffect$$GetAbilityState`, pose par `collect_additional_hit_groups`.
MAUGETAR_CTX_ABILITY_STATE_OF = _ctx_keys.CTX_TERTIARY_ABILITY_STATE_OF
#: cle du ctx du canal #179 : « le groupe de coups d'ARME de cette attaque contient-il un CRIT ? »
#: -- mirror de `hitGroup+0x3d`, que
#: `IdunBattle.Operations.AttackDamageOperation$$ExecuteAdditionalHitsWithoutDamageProfileType`
#: recopie dans l'`AbilityEntities` qu'il passe a `GetAdditionalHitsFromEffectsInternal`.
MAUGETAR_CTX_ATTACK_HAD_CRITICAL = "attack_had_critical"


class MaugetarHasNotMovedEffect(BaseEffect):
    """`Maugetar_HasNotMovedEffect` (effet 0x5d9 = 1497 `Maugetar_HasNotMoved`, relique unique de
    `eldarMauganRa`) -- tant que Maugan Ra n'a pas bouge, ses attaques qui CONTIENNENT un crit
    portent `nrOfHits` coup(s) additionnel(s) [minDmg, maxDmg] au profil `damageProfile`.

    i2 : « During his turn, if Maugan Ra has not moved, he can move after attacking and his attacks
    that contain a Crit deal an additional 1x 2622-3492 Direct Damage. When Overwatching, Crits deal
    this additional hit if he has not moved in his last turn. »

    Natif : `IdunBattle.Entities.Effects.Loki.Maugetar_HasNotMovedEffect$$CreateAdditionalHits` ->
    `IdunBattle.Entities.Effects.EffectAdditionalHits$$Create` {
        trigger        = `IdunBattleLogic.Entities.DSLTriggers$$get_OwnerIsCaster`
                       & `IdunBattleLogic.Entities.DSLTriggers$$AttackDamageIsCritical`,
        damageFormula  = `IdunBattle.Entities.Effects.BaseEffect$$GetMinMaxDamage(this, 0)` (ROLL),
        additionalHitsType = null,
        damageProfileType  = `IdunBattle.Configuration.AbilityConfiguration$$GetDamageProfile(cfg)`
                             (defaut 0xf quand le `Nullable` est vide),
        hitsFormula    = `IdunBattleLogic.Entities.DSLFormulas$$ConfigConst(0x2f =
                          AbilityConstantType.nrOfHits)`,
        forceOverkill  = false,
        maxDamage      = `BaseEffect$$GetMinMaxDamage(this, 1)` = noeud DISPLAY (`Average`) }

    Le descripteur etait l'un des TROIS `Average` recenses NON PORTES par #884 SS2 (residu `#884-r2`,
    annonce `BLOCAGE: porteur`) -- ce blocage est LEVE : `eldarMauganRa` est au pool rank 17 et la
    relique se monte par `rl_duel build --equip-relic "eldarMauganRa:Maugetar[:lvl]"` (#237). Mesure :
    l'effet 1497 est bien POSE par le natif et capte par `decisionView.effects`.

    ⚠ LE NIVEAU NE SE LIT PAS SUR L'INSTANCE. Mesure (probe_959, deux runners `--equip-relic` a
    niveau 1 puis 10) : l'instance publie `ability_level = 50` (l'etat PASSIF du porteur) dans LES
    DEUX cas. `minDmg`/`maxDmg` ont **10 paliers** (1765-2350 au niveau 1, 2622-3492 au niveau 10,
    soit x1,49) : lire l'instance clamperait TOUJOURS au dernier palier. On passe donc par le foyer
    UNIQUE `triggered_ability_state` (#357), expose au ctx sous
    `MAUGETAR_CTX_ABILITY_STATE_OF` -- exactement le motif de `RelicBoltPistol*Effect`.

    ⚠ `variablesAffectedByRarityBonus` est ABSENT de la config de `Maugetar` -> le multiplicateur de
    rarete ne s'applique pas (`ability_var` gate dessus). On le passe quand meme : c'est le natif qui
    decide, pas nous."""

    def _ability_state(self, ctx: "Mapping | None") -> tuple:
        """`BaseEffect$$GetAbilityState` -> `(level, multiplier)` de l'`AbilityState` bake a la pose.

        `Maugetar_AddEffectAbility$$CreateBehaviour` bake `AbilityStateReference` et pose l'effet sur
        `Owner@DSLSelectors+0x30` : source == porteur, donc le couple se relit sur le porteur.
        Callable absent (ctx de probe / test offline) -> repli sur ce que l'instance porte, comme
        toutes les autres classes d'effet."""
        c = ctx or {}
        fn, oid = c.get(MAUGETAR_CTX_ABILITY_STATE_OF), c.get("owner_id")
        if fn is not None and oid is not None:
            lvl, mult = fn(oid, _MAUGETAR_ABILITY)
            if lvl is not None:
                return int(lvl), int(mult if mult is not None else 100)
        lvl = self.ability_level if self.ability_level is not None else self.level
        return lvl, int(self.ability_variables_multiplier or 100)

    def additional_hit_groups(self, ctx: "Mapping | None" = None) -> "list[dict] | None":
        c = ctx or {}
        # `AttackDamageIsCritical` : le natif l'evalue sur `AbilityEntities+0xf8`, que
        # `ExecuteAdditionalHitsWithoutDamageProfileType` recopie depuis `hitGroup+0x3d` -- l'etat du
        # groupe de coups d'ARME qui vient d'etre resolu, pas un tirage per-coup. Cle ABSENTE = NON
        # MESUREE -> le noeud rend FAUX (jamais permissif) : hors face COMBAT, aucun groupe.
        if not c.get(MAUGETAR_CTX_ATTACK_HAD_CRITICAL):
            return None
        # `get_OwnerIsCaster` : cet agregateur n'est appele QUE sur les effets de l'ATTAQUANT (branche
        # PORTEUR de `collect_additional_hit_groups`), donc l'identite est structurelle. On la
        # re-verifie quand le ctx la porte, jamais on ne la suppose absente-donc-vraie.
        oid, aid = c.get("owner_id"), c.get("att_id")
        if oid is not None and aid is not None and oid != aid:
            return None
        lvl, mult = self._ability_state(c)
        mn = ability_var(_MAUGETAR_ABILITY, "minDmg", lvl, multiplier_pct=mult)      # ConfigVar 0xc
        mx = ability_var(_MAUGETAR_ABILITY, "maxDmg", lvl, multiplier_pct=mult)      # ConfigVar 0xd
        count = ability_var(_MAUGETAR_ABILITY, "nrOfHits", is_constant=True)         # ConfigConst 0x2f
        if mn is None or mx is None or not count or count <= 0:
            return None
        try:
            import gameconfig as _GC
            profile = ((_GC.ability(_MAUGETAR_ABILITY) or {}).get("constants") or {}) \
                .get("damageProfile") or "DirectDamage"
        except Exception:                                    # noqa: BLE001 -- gameconfig absent
            profile = "DirectDamage"
        # BI-CANAL ROLL / DISPLAY (#884) : le 8e argument du `Create` natif vaut
        # `GetMinMaxDamage(this, 1)` = `DSLFormulas$$Average(minNode, maxNode)`, donc la cellule de
        # PREDICTION est DEGENEREE a la moyenne ARRONDIE (`RoundFix64Result(., 0)`, demi-vers-le-PAIR),
        # alors que la face COMBAT lit `min`/`max` du noeud ROLL. Publier les deux DES le premier
        # commit : c'est le gisement que notre propre cadence de portage rouvre.
        return [{"count": int(count),
                 "amount": _round_fix64(_Fraction(int(mn) + int(mx), 2), 0),
                 "min": int(mn), "max": int(mx), "profile": profile}]


#: `TriggeredAbilityType` 0x5b9 = 1465 -- la CONFIG que lit l'effet 1463 (relique Death Guard
#: `R_*_OrbsOfDecay`). Le nom est le SEUL discriminant : l'ordinal 1465 nomme
#: `DaemonicPatrons_DmgReduction` dans `EffectType`.
_ORBS_OF_DECAY_ABILITY = "OrbsOfDecay"
#: callable `(owner_id, ability_name) -> (level, multiplier)` -- MEME foyer que `Maugetar`
#: ci-dessus (`BaseEffect$$GetAbilityState` -> `triggered_ability_state`, #357). Indispensable ici :
#: la relique arrive par la branche TERTIAIRE, dont le niveau n'est PAS celui des passifs.
ORBS_OF_DECAY_CTX_ABILITY_STATE_OF = _ctx_keys.CTX_TERTIARY_ABILITY_STATE_OF


class OrbsOfDecayAdditionalHitsEffect(BaseEffect):
    """`OrbsOfDecay_AdditionalHitsEffect` (effet 0x5b7 = 1463 `OrbsOfDecay_AdditionalHits`, relique
    Death Guard `OrbsOfDecay`) -- le volet << ON the target's hex >> de la relique.

    i2 `Abilities/OrbsOfDecay_CurrentLevelDescription` : << The relic bearer's normal attacks deal an
    additional {nrOfHits}x {minDmg}-{maxDmg} Toxic Damage to enemy units that have their Armour
    reduced by {armorReductionPct}% or more and are also **on or** adjacent to the target's hex.
    Additionally, the target's hex is Contaminated. >>

    ## DEUX ARTEFACTS, DEUX MOITIES DE LA MEME PHRASE
    Le << **adjacent to** >> est le volet ABILITY, deja porte (#1003,
    `runner/operations/triggers/loki/orbs_of_decay.py`) : `OrbsOfDecayAbility$$CreateBehaviour`
    attaque les ennemis ADJACENTS a la tuile de la cible, et
    `IdunBattle.Entities.Selectors.AdjacentTilesSelector$$Select` EXCLUT ses tuiles d'origine --
    donc la CIBLE elle-meme n'est PAS frappee par ce volet-la.
    Le << **on** >> est CE descripteur : il ajoute des coups a l'attaque PRIMAIRE, celle qui frappe
    la cible, sous le MEME predicat d'armure. C'est le residu `#884-r2` / `#1003-r1`.

    ## L'ARTEFACT NATIF -- `OrbsOfDecay_AdditionalHitsEffect$$CreateAdditionalHits`, lu VERBATIM
        `IdunBattle.Entities.Effects.EffectAdditionalHits$$Create` {
          trigger        = `IdunBattleLogic.Entities.DSLTriggers$$get_OwnerIsCaster`
                         & `OrbsOfDecayAbility$$GetTriggerForAttack(dsl, config@+0x60)`
                         & `IdunBattleLogic.Entities.DSLTriggers$$IsMeleeAttack`,
          damageFormula  = `IdunBattle.Entities.Effects.BaseEffect$$GetMinMaxDamage(this, 0)` (ROLL),
          additionalHitsType = 1,
          damageProfileType  = `IdunBattle.Configuration.AbilityConfiguration$$GetDamageProfile(config)`
                               = `Toxic`,
          hitsFormula    = `IdunBattleLogic.Entities.DSLFormulas$$ConfigConst(0x2f = nrOfHits, config)`,
          forceOverkill  = 0,
          maxDamage      = `BaseEffect$$GetMinMaxDamage(this, 1)`            (noeud DISPLAY) }
    `.ctor` = `BaseEffect(AbilityOrEffect(TriggeredAbilityType.OrbsOfDecay = 0x5b9), 1)` -- LU au
    desassemblage (`mov edx, 0x5b9` puis le `call` de la surcharge dont le parametre se nomme
    `triggeredAbility`), pas deduit : l'ordinal seul ne discriminerait pas l'enum.

    ## LE PREDICAT D'ARMURE EST LE **MEME ARTEFACT NATIF** que celui du volet ABILITY
    Le natif appelle litteralement `OrbsOfDecayAbility$$GetTriggerForAttack` ici -- une fonction
    STATIQUE partagee. Cote port, l'arbre DSL du volet ABILITY resout des ENTITES sous un `Filter`
    alors que ce canal-ci ne recoit qu'un DICT : les deux expressions vivent donc dans le MEME
    module (`triggers/loki/orbs_of_decay.py`), et un test balaie leur accord
    (`test_884r2_orbs_of_decay_offline.py` etage 2) pour qu'un fork soit VISIBLE.

    ⚠ LE SUJET EST LA CIBLE, ET C'EST CE QUI SEPARE LES DEUX VOLETS. Le natif evalue
    `GetTriggerForAttack` sur `Subject@DSLSelectors+0x68` ; sous le `Filter` du volet ABILITY c'est
    l'element courant (un VOISIN), hors `Filter` -- ici -- c'est la cible originale de l'attaque.
    C'est exactement la lecture que l'i2 impose (<< on OR adjacent >>) : sans elle, le << on >>
    n'aurait AUCUN artefact.

    ⚠ TRI-ETAT SUR LES DEUX SCALAIRES D'ARMURE : cles absentes = NON MESUREES -> le gate se FERME
    (`orbs_of_decay_armor_gate`). Un 0 rabattu ferait passer une cible SANS armure pour une cible
    non reduite -- et, pire, un `initial = 0` avec une reduction non nulle diviserait par zero la ou
    le natif court-circuite.

    BI-CANAL ROLL / DISPLAY (#884) : ce descripteur etait le DERNIER des trois `Average` non portes
    du recensement des 19 `$$CreateAdditionalHits` -- il publie donc `min`/`max` (face COMBAT,
    noeud ROLL) ET `amount` (face PREDICTION, `Average` arrondi Fix64 demi-vers-le-PAIR) DES son
    premier commit, comme la fiche `#884-r2` l'exigeait."""

    def _ability_state(self, ctx: "Mapping | None") -> tuple:
        """`BaseEffect$$GetAbilityState` -> `(level, multiplier)` -- MEME foyer et MEME repli que
        `MaugetarHasNotMovedEffect._ability_state` (les deux sont des reliques TERTIAIRES)."""
        c = ctx or {}
        fn, oid = c.get(ORBS_OF_DECAY_CTX_ABILITY_STATE_OF), c.get("owner_id")
        if fn is not None and oid is not None:
            lvl, mult = fn(oid, _ORBS_OF_DECAY_ABILITY)
            if lvl is not None:
                return int(lvl), int(mult if mult is not None else 100)
        lvl = self.ability_level if self.ability_level is not None else self.level
        return lvl, int(self.ability_variables_multiplier or 100)

    def additional_hit_groups(self, ctx: "Mapping | None" = None) -> "list[dict] | None":
        c = ctx or {}
        # `get_OwnerIsCaster` : cet agregateur n'est appele QUE sur les effets de l'ATTAQUANT
        # (branche PORTEUR de `collect_additional_hit_groups`), donc l'identite est structurelle.
        # On la RE-VERIFIE quand le ctx la porte -- jamais << absente donc vraie >>.
        oid, aid = c.get("owner_id"), c.get("att_id")
        if oid is not None and aid is not None and oid != aid:
            return None
        # `IsMeleeAttack` -- nature du coup, MEME cle et MEME tri-etat que les autres descripteurs
        # du canal. `None` (non threade) -> FAUX, jamais permissif.
        if c.get("is_melee") is not True:
            return None
        # `OrbsOfDecayAbility$$GetTriggerForAttack(dsl, config)` evalue sur la CIBLE. Differe
        # PORTEUR : le module cible importe `entities.formulas` / `entities.selectors` /
        # `entities.triggers`, donc le hisser fermerait un cycle -- meme classe que le differe
        # voisin vers `runner.abilities.attack_type`.
        from ....runner.operations.triggers.loki.orbs_of_decay import orbs_of_decay_armor_gate
        if not orbs_of_decay_armor_gate(c.get(_ctx_keys.CTX_TGT_FIXED_ARMOR_INITIAL),
                                        c.get(_ctx_keys.CTX_TGT_FIXED_ARMOR_NEGATIVE_MOD)):
            return None
        lvl, mult = self._ability_state(c)
        mn = ability_var(_ORBS_OF_DECAY_ABILITY, "minDmg", lvl, multiplier_pct=mult)   # ConfigVar 0xc
        mx = ability_var(_ORBS_OF_DECAY_ABILITY, "maxDmg", lvl, multiplier_pct=mult)   # ConfigVar 0xd
        count = ability_var(_ORBS_OF_DECAY_ABILITY, "nrOfHits", is_constant=True)      # ConfigConst 0x2f
        if mn is None or mx is None or not count or count <= 0:
            return None
        try:
            import gameconfig as _GC
            profile = ((_GC.ability(_ORBS_OF_DECAY_ABILITY) or {}).get("constants") or {}) \
                .get("damageProfile") or "Toxic"
        except Exception:                                    # noqa: BLE001 -- gameconfig absent
            profile = "Toxic"
        # BI-CANAL ROLL / DISPLAY (#884) -- cf. la docstring de classe.
        return [{"count": int(count),
                 "amount": _round_fix64(_Fraction(int(mn) + int(mx), 2), 0),
                 "min": int(mn), "max": int(mx), "profile": profile}]
