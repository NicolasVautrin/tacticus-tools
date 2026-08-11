"""Abilities actives des **Black Templars** (prefixe `templ*`) — face EXECUTION (runner/ECS).

- `FragstormGrenadeLauncher` (1048, `templAggressor` « Brother Burchard ») — #489.
- `CrusadeOfWrath` (1049, `templHelbrecht` « High Marshal Helbrecht ») — bloc dedie ci-dessous (#893).
- `HolyDuel` (1050, `templChampion` « Brother Jaeger ») — cf. le bloc dedie en bas de module.
- `UnbreakableDuty` (1061, `templAncient` « Ancient Thoread ») — bloc dedie en bas de module (#572).

Les autres actives BT restent hors registre (cf. `docs/rl/case-220/black-templars.md`) ;
`ThunderousAssault` (1043) vit dans `loki/strike.py` (patron partage), pas ici.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from ...dsl.base import Const
from ...dsl.effects import ExecutionContext
from ...entities.active_ability_type import ActiveAbilityType
from ...entities.ability_constant_type import AbilityConstantType
from ...entities.ability_variable_type import AbilityVariableType
from ...entities.effect_type import EffectType
from ...entities.effects.magnitude import ability_var
from ...entities.formulas import Count, StatAmount
from ...entities.behaviours import If as IfBehaviour, op_add, op_and
from ...entities.selectors.accessors import ActiveTarget, CasterTile, Owner, Target
from ...entities.selectors.geometry import PickRandomly
from ...entities.selectors.tiles import Caster
from ...entities.selectors.units import (AdjacentEnemies, AllDeadOrResurrectedUnits, And, Damageable,
                                         Friends, SortByFormula, Sub, SurroundingEnemies,
                                         SurroundingUnits, ValidNormalAttackTargets,
                                         units_with_traits)
from ...entities.stats import StatType
from ...entities.traits.unit_trait import UnitTrait
from ...entities.triggers import AmountIsEqualOrGreater, AmountIsGreaterThanZero
from ..components import StatsComponent
from ..operations.damage_prediction_sort import SortTargetsByDamagePrediction
from .base import ActiveAbility, ability_attack_params
from .behaviours.combat import ChainLeftOverHitsAttackDamage, UseActiveAbility
from .behaviours.context import entities_from_state
from .behaviours.effects import AddBondEffect, AddEffect, AddStaticStatModifierEffect
from .behaviours.stats import ChangeStat
from .targeting import (RANGE_ADJACENT, RANGE_FROM_CONFIG, RANGED_BOOL_FALSE, TargetingOptions)
from .targeting_rule import TargetingRule as TR
from ...entities.unit_selection_type import UnitSelectionType

#: `UnitSelectionType` LU au dernier argument des `DSLSelectors$$*` de ce fichier -- releve
#: #585-r1, build `rnca9r7q6c`, littéral par littéral (JAMAIS par symetrie : deux call-sites
#: du releve passent `Any` parce que leur source est un ensemble de MORTS).
SELECTION = int(UnitSelectionType.OnlyAliveAndTargetable)     # 3


if TYPE_CHECKING:                       # pragma: no cover
    from ..state import State


# ================== FragstormGrenadeLauncher (templAggressor, actif 1048) -- #489 =================

FRAGSTORM_GRENADE_LAUNCHER_ID = "FragstormGrenadeLauncher"
FRAGSTORM_GRENADE_LAUNCHER_PROFILE = "Blast"      # `AbilityConfiguration$$GetDamageProfile` (gameconfig)


def fragstorm_grenade_launcher_other_targets(range_val: int):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.FragstormGrenadeLauncherAbility$$GetOtherTargets`
    — MIRROR 1:1 :

        Damageable( SurroundingEnemies(unit = Owner@DSLSelectors+0x30,
                                       range = GetNumberConstant(0x16 = range),
                                       unique = 1, unitSelectionType = 3)
                    op_Subtraction Target@DSLSelectors+0x60 )

    La surcharge appelee est celle a **4 arguments** (`SurroundingEnemies(unit, range: Int32, unique,
    unitSelectionType)`, `frida/methods.tsv`) : le MEME selecteur sert de centre ET de REFERENCE
    d'equipe -> `reference=Owner()` explicite, jamais le collapse `ctx.caster` par defaut (qui serait
    observationnellement egal ici, Owner == Caster pour une active, mais qui n'est pas ce qu'ecrit le
    natif).

    ⚠ Le meme ensemble est relu, inline, par `$$ExecuteBehaviour` — le natif ne rappelle pas
    `$$GetOtherTargets` mais recopie l'expression ; il n'y a donc qu'UN foyer cote port."""
    return Damageable(Sub(SurroundingEnemies(Owner(), Const(range_val), reference=Owner()),
                          Target()))


def fragstorm_grenade_launcher_tree(state, range_val: int, base_min: int, base_max: int,
                                    hits: int, pierce: int) -> ChainLeftOverHitsAttackDamage:
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.FragstormGrenadeLauncherAbility$$ExecuteBehaviour`
    — MIRROR 1:1 (UN SEUL noeud terminal, passe a `AActiveAbility$$Execute`) :

        dmg   = DSLFormulas$$Cache( AActiveAbility$$MinMaxDamage(this, abilityState) )
        other = <GetOtherTargets ci-dessus>
        chain = DSLSelectors$$SortTargetsByDamagePredictionSelector(
                    attacker           = Owner@+0x30,
                    units              = DSLSelectors$$SortByFormula(
                                             other,
                                             DSLFormulas$$StatAmount(ActiveTarget@+0x68,
                                                                     StatType.Health, StatPart.Current),
                                             ascending: 1),
                    ability            = DSLSelectors$$Direct(AbilityOrEffect(this+0x10)),
                    damage             = dmg,
                    hits               = DSLFormulas$$Direct(GetNumberConstant(0x2f = nrOfHits)),
                    damageProfileType  = DSLSelectors$$Direct(Nullable(GetDamageProfile(config))),
                    attackerSelectionType = 3)
        DSLBehaviors$$ChainLeftOverHitsAttackDamage(
            caster                     = Owner@+0x30,
            firstTarget                = Target@+0x60,
            dmgAmount                  = dmg,
            damageProfileType          = Direct(Nullable(GetDamageProfile(config))),
            hits                       = Direct(nrOfHits),
            abilityType                = this+0x10,
            otherTargetSelector        = chain,
            extraHitsAfterTargetKilled = **null**)

    TROIS ecarts LUS avec `1006 MultiThreatEliminator`, qui monte la MEME feuille (`necrons.py`) —
    aucun n'est copie du voisin :
      * `extraHitsAfterTargetKilled` est **null** ici (MTE : `DSLFormulas$$Get(GetNumberConstant(0x2b
        = extraHit))`) -> **aucun coup bonus par ennemi tue** ;
      * le caster est pris au slot `Owner@+0x30` (MTE : `Caster@+0x48`) ;
      * le selecteur de cible suivante est un `SortTargetsByDamagePredictionSelector` (MTE :
        `And(Unobscured(Enemies(SurroundingUnits(CasterTile, range))), AdjacentUnits(ActiveTarget))`).
    Et l'execution passe par `AActiveAbility$$Execute` (MTE : `$$ExecuteAtomic(..., 0x41)`).

    Le tri par PV est **ASCENDANT** (`ascending: 1` LU au call-site ; le flag natif `0` vaudrait
    DESCENDANT) : les cibles les plus faibles d'abord. Il ne survit toutefois que comme TIE-BREAK — le
    `OrderByDescending` du selecteur de prediction, stable, le reordonne ensuite par priorite de kill.

    ⚠ **LE NOEUD DE LA FORMULE DE TRI EST `ActiveTarget`, PAS `Subject` — et ca CHANGE le resultat.**
    Le natif passe `DSLSelectors+0x68`, et le mapping des slots de `DSLSelectors` est LU dans
    `IdunBattleLogic.Entities.DSLSelectors$$InitializeShared` (onze champs `+0x30..+0x80`), aligne sur
    la carte `DSLFactory` (`+0x148 Owner … +0x180 ActiveTarget`) par l'ecart constant `0x118` :
    `+0x30 Owner · +0x38 Effect · +0x40 Actor · +0x48 Caster · +0x50 CasterTile · +0x58 CasterTiles ·
    +0x60 Target · +0x68 ActiveTarget · +0x70 PreviousActiveTarget · +0x78 TargetTiles ·
    +0x80 UnitFeetTiles`. Le port expose ce slot par `ActiveTarget()` (`ctx.active_target`), que
    `SortByFormula.select` ne re-lie PAS (il re-lie `subject`) : la formule est donc CONSTANTE sur la
    source — le tri par PV est un **NO-OP**, et l'ordre SOURCE (geometrique, `SurroundingEnemies`)
    survit jusqu'au selecteur de prediction. Ecrire `Subject()` a la place rendait le tri ACTIF et
    changeait la cible du report (MESURE #489 : port -> `u81`, natif -> `u107` ; cf. la case-doc).

    `attackRangeType = Ranged` (gameconfig) -> `is_melee=False`. Famille de factory = **ATTACK** (le
    nom natif est `...AttackDamage` et la feuille construit le mold `AttackDamageBehaviour`) ->
    `native_factory="attack"`, le defaut de la feuille."""
    other = fragstorm_grenade_launcher_other_targets(range_val)
    by_health = SortByFormula(other,
                              StatAmount(ActiveTarget(), int(StatType.HEALTH)),  # StatPart.Current = 0
                              ascending=True)   # flag natif `1` -> `OrderBy` (LU dans `$$Select`)
    chain = SortTargetsByDamagePrediction(
        state=state, attacker=Owner(), targets=by_health,
        ability_type=int(ActiveAbilityType.FragstormGrenadeLauncher),
        damage_min=base_min, damage_max=base_max, hits=hits,
        damage_profile=FRAGSTORM_GRENADE_LAUNCHER_PROFILE, pierce=pierce, is_melee=False)
    return ChainLeftOverHitsAttackDamage(
        Owner(), Target(), chain, FRAGSTORM_GRENADE_LAUNCHER_ID,
        FRAGSTORM_GRENADE_LAUNCHER_PROFILE, hits, 0, is_melee=False,
        # `abilityType = this+0x10` (#512-r2 volet 2) -- LU au call-site ci-dessus.
        ability_type=int(ActiveAbilityType.FragstormGrenadeLauncher))


class FragstormGrenadeLauncherAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.FragstormGrenadeLauncherAbility$$ExecuteBehaviour`
    (id 1048, `templAggressor` « Brother Burchard », Black Templars).

    i2 mot a mot : « Deals up to 6x 1746-2183 Blast Damage to a target within 2 hexes. Any leftover
    hits are allocated to enemy units within 2 hexes, prioritising kills. »

    6 coups Blast sur la cible ; les coups qui tombent sur le CADAVRE sont REPORTES sur l'ennemi
    suivant — parmi les ennemis du caster a distance <= `range`(2) de LUI, cible principale exclue,
    tries PV croissants puis par priorite de kill (prediction de degat). Le report lui-meme vit dans
    la feuille partagee `ChainLeftOverHitsAttackDamage` (`behaviours/combat.py`, avec son
    `GetLeftOverHits` et sa garde de 100 iterations) ; ici, seulement la CONSTRUCTION de l'arbre.

    ⚠ Sans `extraHits`, un maillon ne peut REPORTER que si la cible meurt AVANT le dernier coup :
    `GetLeftOverHits` rend `max(0, H - k - 1) + 0`. Une cible tuee au dernier ou a l'avant-dernier
    coup ne reporte RIEN.

    Face DECISION deja portee (#352, `playbook/prediction/abilities.py::
    _fragstorm_grenade_launcher_inputs`) : base = `nrOfHits x maxDmg` en UN coup. Ce port-ci est la
    face EXECUTION, qui etait un NO-OP SILENCIEUX (absente d'`ABILITY_CLASSES`).

    Renvoie {ability, caster, target, chain, dsl}. Termine le tour (1048 hors des frozensets
    de `base.py`)."""

    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.FragstormGrenadeLauncher)   # 1048
    ABILITY_ID = FRAGSTORM_GRENADE_LAUNCHER_ID

    # GATE DE CIBLE (#489). `…FragstormGrenadeLauncherAbility$$.ctor` COPIE les 0x40 octets du PRESET
    # STATIQUE `IdunBattle.Core.Services.TargetingOptions` statics `+0x180` puis appelle la surcharge
    # PRESET+FLAGS `TargetingOptions$$.ctor(&opts, &preset, 0x2000000)`, dont la seule difference avec
    # une copie pure est `opts.Rules = flags | preset.Rules`. Enfin `AActiveAbility$$.ctor(this,
    # &opts, 0)`.
    # Le preset `+0x180` est LU dans `IdunBattle.Core.Services.TargetingOptions$$.cctor` :
    #     +0x180 isSelfCasting = 0
    #     +0x188 range         = `TargetingRange` statics `+0x18` = useRangeFromConfig -> range = 2
    #     +0x1a0 forceMeleeTarget = 1 = `RangedBool.False`
    #     +0x1a8 rules         = 0x4002
    # => masque EFFECTIF = `0x2000000 | 0x4002` = **0x2004002**, concordant avec la mesure
    # independante de `docs/rl/case-302-4/tile-target-population.tsv` (ligne 1048, `state=measured`,
    # `form=preset+flags`).
    # Decomposition (`IdunBattle.Core.Services.TargetingRule`), exhaustive :
    #     0x2        TargetMatchesDynamicRule       -> `GetDynamicInvalidTargetReason` non surchargee
    #                                                  ici -> defaut 0 (degradation PERMISSIVE assumee)
    #     0x4000     TargetIsEnemy                  -> PORTE
    #     0x2000000  AllowObscuredTargetByElevation -> DESARME une regle de ligne de vue elle-meme non
    #                                                  portee -> sans effet, dans le bon sens
    # ⚠ Le preset voisin `+0x140` (Stikkbomb 1051, PlasmaGrenade 1098) ne differe QUE par
    # `forceMeleeTarget` (`RangedBool.True`) : recopier le masque d'une voisine aurait donne le bon
    # `rules` et la mauvaise PORTEE (`TargetingQuery$$GetRange` rabat a 1 au contact quand
    # `ForceMeleeTarget` est vrai). Fragstorm, lui, GARDE sa portee 2 au contact.
    TARGETING_OPTIONS = TargetingOptions(rules=TR.TargetMatchesDynamicRule | TR.TargetIsEnemy
                                               | TR.AllowObscuredTargetByElevation,
                                         range=RANGE_FROM_CONFIG,
                                         force_melee_target=RANGED_BOOL_FALSE)

    # `AbilityAttackType` = 3e argument d'`IdunBattle.Entities.Abilities.AActiveAbility$$.ctor` = `0`
    # (`DirectTargetAttack`), LU au ctor -> transcrit dans la table `ABILITY_ATTACK_TYPE`
    # (`abilities/attack_type.py`), qui est le registre de cette donnee (pas un attribut de classe).

    def _params(self, state: "State", caster_id: int) -> tuple:
        """`(range, base_min, base_max, hits, pierce)`.

        `range` = `AbilityConfiguration$$GetNumberConstant(config, 0x16)` ; les bornes, le nombre de
        coups (`0x2f`) et le percage du profil viennent du foyer partage `ability_attack_params`
        (mirror `AActiveAbility$$MinMaxDamage` / `GetHits` / `GetDamageProfile`)."""
        rng_range = ability_var(self.ABILITY_ID, "range", is_constant=True) or 1
        base_min, base_max, pierce, hits = ability_attack_params(
            state, caster_id, self.ABILITY_ID, FRAGSTORM_GRENADE_LAUNCHER_PROFILE, ranged=True)
        return int(rng_range), int(base_min), int(base_max), int(hits), int(pierce)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        entities = entities_from_state(state, caster_id, target_id)
        range_val, base_min, base_max, hits, pierce = self._params(state, caster_id)
        ectx = ExecutionContext(state=state, rng=state.rng)
        fragstorm_grenade_launcher_tree(state, range_val, base_min, base_max,
                                        hits, pierce).execute(entities, ectx)
        chain = next((p["chain"] for n, p in ectx.emitted if n == "ChainLeftOverHits"), [])
        return {"ability": FRAGSTORM_GRENADE_LAUNCHER_ID, "caster": caster_id, "target": target_id,
                "range": range_val, "hits": hits, "chain": chain, "dsl": True}


# Les deux constantes de config LUES au decompile, nommees (regle « un entier qui DESIGNE passe par
# un ENUM ») : `GetNumberConstant(0x16)` et `GetNumberConstant(0x2f)`.
assert int(AbilityConstantType.range) == 0x16 and int(AbilityConstantType.nrOfHits) == 0x2F


# =================================================================================================== #
# CrusadeOfWrath (1049, `templHelbrecht` -- High Marshal Helbrecht, HERO Black Templars)        #893 #
#
# `IdunBattleLogic.Entities.Abilities.Active.Loki.CrusadeOfWrathAbility$$ExecuteBehaviour` (MIRROR du
# DECOMPILE, build `rnca9r7q6c`) -- UN SEUL noeud terminal passe a `AActiveAbility$$Execute` :
#
#   range  = AbilityConfiguration.GetNumberConstant(config@this+0x60, 0x16 = range)      -> 2
#   buffed = DSLSelectors.Friends(
#                of       = Owner@DSLSelectors+0x30,
#                entities = DSLSelectors.SurroundingUnits(origin = CasterTile@+0x50, range = range,
#                                                         unique = 1, includeCenter = **0**,
#                                                         unitSelectionType = 3)
#                           op_Subtraction Caster@+0x48,
#                selectionType = 3)
#   turns  = DSLFormulas.TurnsFromRounds(**2**)
#
#   [A] dmg    = DSLBehaviors.AddStaticStatModifierEffect(
#                    targets   = buffed,
#                    effectType = 0x43e = 1086 CrusadeOfWrath_ExtraDamage,
#                    statType  = **0** = Attack,
#                    amount    = DSLFormulas.Direct(AbilityConfiguration.GetVariableForLevel(
#                                    config, **8** = extraDmg, AbilityState, 0)),
#                    turns = turns, isHidden = false)
#   [B] pierce = DSLBehaviors.AddStaticStatModifierEffect(
#                    targets   = buffed,
#                    effectType = 0x43f = 1087 CrusadeOfWrath_ExtraPierce,
#                    statType  = **0x15** = 21 ExtraPierceMelee,
#                    amount    = DSLFormulas.Direct(AbilityConfiguration.GetVariableForLevel(
#                                    config, **0x3f** = extraPierceRatio, AbilityState, 0)),
#                    turns = turns, isHidden = false)
#   [C] sel    = DSLSelectors.ValidNormalAttackTargets(CasterTile@+0x50, CasterTile@+0x50,
#                                                      range = null, ignoreRule/additionalRule = null)
#                op_BitwiseAnd DSLSelectors.AdjacentEnemies(Caster@+0x48, unique = 1,
#                                                           selectionType = 3)
#       attack = DSLBehaviors.UseActiveAbility(
#                    caster            = Owner@+0x30,
#                    target            = DSLSelectors.PickRandomly(sel, amount = 1,
#                                            allowDuplicates = 0, maxDuplicatesAllowed = 0x7fffffff,
#                                            ignoreForcedTargets = 0),
#                    activeAbilityType = **DSLSelectors.UnitNormalAttackType(Owner@+0x30)**,
#                    parentAbility     = Nullable(AbilityOrEffect(this+0x10)),
#                    triggerAbilityOrEffect / options ZEROES)
#       free   = DSLBehaviors.If(DSLTriggers.AmountIsGreaterThanZero(DSLFormulas.Count(sel)),
#                                attack, null)
#
#   AActiveAbility.Execute(entities, this, [A] op_BitwiseAnd ([B] op_Addition [C]))
#
# i2 mot a mot (`Abilities/CrusadeOfWrath_CurrentLevelDescription`) : « All other friendly units
# within {[range]} hexes gain +{[extraDmg]} Damage and +{[extraPierceRatio]}% pierce ratio in melee
# - regardless of Damage type - for this round and the next. High Marshal Helbrecht immediately
# performs a normal melee attack against a random adjacent enemy. » -- appariement UN A UN avec
# [A] / [B] / [C], et « for this round and the next » = le `TurnsFromRounds(2)`.
#
# LA CATEGORIE ANNONCEE EST INCOMPLETE, et c'est un RESULTAT : `docs/rl/combat-ability-coverage.md`
# classe 1049 en EFFECT/BUFF (colonne derivee du `damageProfile` de l'ARME du porteur, pas du
# behaviour). C'est vrai de DEUX mecaniques sur TROIS. La troisieme, [C], FRAPPE -- par l'attaque
# NORMALE de l'unite, pas par une `AttackWithAbilityDamage` : `abilities.CrusadeOfWrath` n'a NI
# `minDmg`/`maxDmg`, NI `nrOfHits`, NI `damageProfile` (gameconfig : DEUX variables `extraDmg` /
# `extraPierceRatio` et UNE constante `range` = 2). MEME configuration que `HolyDuel` 1050,
# `UnbreakableDuty` 1061 et `Drachnyen` 1029.
#
# LE CASTER NE SE BUFFE PAS -- et c'est ecrit DEUX FOIS par le natif : `includeCenter = 0` exclut
# deja la tuile du caster de `SurroundingUnits`, puis `op_Subtraction Caster@+0x48` l'ote une seconde
# fois. Redondant sur une unite mono-tuile, load-bearing si le porteur en occupe plusieurs (le
# `SurroundingTiles` d'un des pieds ramenerait les AUTRES pieds). C'est le « All OTHER friendly
# units » de l'i2. Consequence observable : l'attaque libre [C] part SANS le `+extraDmg` du cast --
# contraste avec `UnbreakableDuty` 1061, dont l'ordre `[C] dmgBuff` PUIS `[D] attaque` fait
# beneficier le caster de son propre buff.
#
# ORDRE (`op_BitwiseAnd` comme `op_Addition` -> `CombinedBehaviour`, evalue a GAUCHE d'abord) :
# [A] +Attack, [B] +ExtraPierceMelee, PUIS [C] l'attaque libre. [A] et [B] sont DETERMINISTES (aucun
# tirage) : le flux `state.rng` de l'attaque est celui d'une attaque normale nue, precede du seul
# tirage de `PickRandomly` (qui consomme MEME sur un pool de 1, cf. `_pick_randomly_n`).
# =================================================================================================== #

CRUSADE_OF_WRATH_ID = "CrusadeOfWrath"
CRUSADE_OF_WRATH_EXTRA_DAMAGE = int(EffectType.CrusadeOfWrath_ExtraDamage)   # 0x43e = 1086
CRUSADE_OF_WRATH_EXTRA_PIERCE = int(EffectType.CrusadeOfWrath_ExtraPierce)   # 0x43f = 1087
#: `DSLFormulas$$TurnsFromRounds(2)` -- le litteral `2` du call-site, converti en TOURS par
#: `ConvertRoundsToTurns`. C'est le « for this round and the next » de l'i2.
CRUSADE_OF_WRATH_BUFF_ROUNDS = 2


def crusade_of_wrath_buff_targets(range_val: int):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.CrusadeOfWrathAbility$$GetBuffTargets`
    -- MIRROR 1:1 :

        Friends( of       = Owner@DSLSelectors+0x30,
                 entities = SurroundingUnits(CasterTile@+0x50, GetNumberConstant(0x16 = range),
                                             unique = 1, includeCenter = 0, selectionType = 3)
                            op_Subtraction Caster@+0x48,
                 selectionType = 3 )

    ⚠ Le meme ensemble est relu, INLINE, par `$$ExecuteBehaviour` (le natif ne rappelle pas
    `$$GetBuffTargets` mais recopie l'expression) -- il n'y a donc qu'UN foyer cote port, exactement
    comme `fragstorm_grenade_launcher_other_targets` plus haut. Le natif, LUI, appelle bien
    `$$GetBuffTargets` depuis un SEUL autre site : `IdunBattle.AI.Playbook.Loki.CrusadeOfWrathPlaybook$$GetMaxFriendlyUnitsBuffed`,
    la face DECISION (non portee, residu `#893-r1`).

    La surcharge de `SurroundingUnits` est celle a `range: System.Int32` (le call-site passe le
    retour d'un `GetNumberConstant`, un int32 nu, PAS un `IAmountFormula`). Celle de `Friends` est
    l'unique `(of, entities, selectionType)`.

    `reference=Owner()` est EXPLICITE (jamais le collapse `ctx.caster` par defaut) : le natif ecrit
    le slot `+0x30`, et le fait qu'Owner == Caster pour une active ne rend pas le defaut plus juste."""
    # #585-r1 -- les DEUX litteraux `selectionType` LUS au call-site valent **3**
    # (`OnlyAliveAndTargetable`), l'un dans le `SurroundingUnits`, l'autre dans le `Friends`.
    autour = SurroundingUnits(CasterTile(), Const(int(range_val)), selection_type=SELECTION)
    return Friends(Sub(autour, Caster()), reference=Owner(), selection_type=SELECTION)


def crusade_of_wrath_free_attack_targets():
    """Le selecteur `sel` de [C] -- MIRROR 1:1 :

        ValidNormalAttackTargets(CasterTile@+0x50, CasterTile@+0x50, null, null, null)
          op_BitwiseAnd
        AdjacentEnemies(Caster@+0x48, unique = 1, selectionType = 3)

    ⚠ EXPRESSION NATIVE IDENTIQUE, LITTERAL POUR LITTERAL, a celle de
    `...UnbreakableDutyAbility$$ExecuteBehaviour` [D] (`unbreakable_duty_free_attack_targets`
    ci-dessous) -- les deux ont ete relues cote a cote sur `rnca9r7q6c`. Les deux helpers restent
    SEPARES a dessein : ce sont DEUX inlines natifs distincts, dans deux `ExecuteBehaviour`
    differents, et une correction faite sur l'un ne doit pas deplacer l'autre en silence.

    `AdjacentEnemies` est la VARIANTE A (`unit, unique, selectionType`), tranchee au call-site et non
    par symetrie : le 2e argument est un booleen construit par `CONCAT71(..., 1)`, pas un selecteur,
    ce qui exclut la variante B (`unit, unitTile, unique`) de meme arite apparente. Aucun rayon ->
    ring-1 = « a random adjacent enemy » de l'i2.

    Le `selectionType = 3` est pose parce qu'il est LU, pas parce qu'il mord : l'intersection avec
    `ValidNormalAttackTargets` applique deja la cascade de ciblage complete
    (`runner/abilities/targeting.py`, masque `NORMAL_ATTACK_TARGETING_OPTIONS`). Il est donc INERTE
    a ce call-site -- ce qui est aussi pourquoi son absence chez le voisin 1061 ne se voit pas."""
    return And(ValidNormalAttackTargets(CasterTile(), CasterTile()),
               AdjacentEnemies(Caster(), selection_type=SELECTION))


def crusade_of_wrath_tree(range_val: int, extra_dmg: int, extra_pierce: int):
    """Arbre COMPLET de `...CrusadeOfWrathAbility$$ExecuteBehaviour` (cf. le bloc de commentaire).

    `extra_dmg` / `extra_pierce` = les DEUX `GetVariableForLevel` COLLAPSES a la valeur qu'ils
    rendent pour le caster (`variables.extraDmg` / `variables.extraPierceRatio` indexes par
    l'`active_ability_level`). SEUL `extraDmg` est dans `variablesAffectedByRarityBonus` -> seul lui
    est scale par l'`AbilityVariablesMultiplierPercentage` ; `ability_var` porte cette regle et
    laisse `extraPierceRatio` brut (meme configuration que `BloodChalice` 1175, `bloodangels.py`).

    `duration_rounds = 2` sur les DEUX effets = le `TurnsFromRounds(2)` natif, PARTAGE par les deux
    `AddStaticStatModifierEffect` (le natif construit UN seul noeud `turns` et le passe deux fois).

    Le terminal est `[A] op_BitwiseAnd ([B] op_Addition [C])` -- transcrit tel que lu ; les deux
    operateurs rendent le meme `CombinedBehaviour` cote natif comme cote port (`Seq`), donc
    l'ASSOCIATIVITE ecrite ici ne change pas l'ordre d'evaluation (A, B, C)."""
    buffed = crusade_of_wrath_buff_targets(range_val)
    dmg = AddStaticStatModifierEffect(buffed, CRUSADE_OF_WRATH_EXTRA_DAMAGE, int(StatType.ATTACK),
                                      Const(int(extra_dmg)),
                                      name=EffectType.CrusadeOfWrath_ExtraDamage.name,
                                      duration_rounds=CRUSADE_OF_WRATH_BUFF_ROUNDS)
    pierce = AddStaticStatModifierEffect(buffed, CRUSADE_OF_WRATH_EXTRA_PIERCE,
                                         int(StatType.EXTRA_PIERCE_MELEE), Const(int(extra_pierce)),
                                         name=EffectType.CrusadeOfWrath_ExtraPierce.name,
                                         duration_rounds=CRUSADE_OF_WRATH_BUFF_ROUNDS)
    sel = crusade_of_wrath_free_attack_targets()
    attack = UseActiveAbility(Owner(), PickRandomly(sel, 1))      # UnitNormalAttackType(Owner@+0x30)
    free = IfBehaviour(AmountIsGreaterThanZero(Count(sel)), attack)
    return op_and(dmg, op_add(pierce, free))


class CrusadeOfWrathAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.CrusadeOfWrathAbility$$ExecuteBehaviour`
    (id 1049, `templHelbrecht` « High Marshal Helbrecht », HERO Black Templars) -- cf. le bloc de
    commentaire.

    PORTEURS, ventiles (`unit_map.py find --ability CrusadeOfWrath`) : `templHelbrecht` (HERO, DEJA
    au pool `rl_duel build --list-pool`) + `templBossHelbrecht` / `templBossHelbrecht_LHE` (npc).
    Aucun montage necessaire.

    TROIS mecaniques (l'audit n'en annonce qu'UNE, « EFFECT/BUFF ») :
      1. +`extraDmg` d'ATTACK sur les AUTRES allies a <= `range`(2) hexes, 2 rounds (effet 1086) ;
      2. +`extraPierceRatio` d'`ExtraPierceMelee` sur les MEMES cibles, 2 rounds (effet 1087) ;
      3. une attaque NORMALE gratuite sur UN ennemi adjacent tire au sort parmi les cibles valides.

    Face DECISION **NON PORTEE** -- residu NOMME `#893-r1` : le natif a un playbook dedie
    (`IdunBattle.AI.Playbook.Loki.CrusadeOfWrathPlaybook`, `ComparablePlaybook<CrusadeOfWrathAbility>`
    ctor `0x419 = 1049`), dont `$$GetUseProbability` vaut `<Fix64 statique @ statics+0x08> x
    $$GetMaxFriendlyUnitsBuffed(unit)`, ce dernier balayant les tuiles rendues par le slot de query
    `this+0x28` et prenant le MAX du cardinal de `$$GetBuffTargets(Entity(unit), Entity(tuile))`.
    C'est le sous-arbre `crusade_of_wrath_buff_targets` ci-dessus, evalue depuis CHAQUE tuile
    atteignable -- donc un scorer de POSITIONNEMENT, pas un simple gate.

    Renvoie {ability, caster, target, buffs, attack, dsl}. Termine le tour (1049 hors des frozensets
    de `base.py`)."""

    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.CrusadeOfWrath)   # 1049
    ABILITY_ID = CRUSADE_OF_WRATH_ID

    # GATE DE CIBLE. `...Active.Loki.CrusadeOfWrathAbility$$.ctor` est la forme **FLAGS DIRECTS**
    # (le litteral EST le masque) : il recopie les 3 qwords du champ statique
    # `<TargetingRange statics>+0x18` dans un local puis appelle
    #     `TargetingOptions$$.ctor(&opts, 1, &range, 1, 0x400, 0, 0)`
    # et enfin `AActiveAbility$$.ctor(this, &opts, 2)`.
    #   selfCast          = 1
    #   range             = `TargetingRange` statics `+0x18` = useRangeFromConfig -> `constants.range` = 2
    #   forceMeleeTarget  = 1 = `RangedBool.False` (l'enum natif est INVERSE)
    #   rules             = 0x400 = `TargetIsFriendly`, SEUL
    # SURCHARGE TRANCHEE PAR SES XREFS ENTRANTES, jamais par l'arite du pseudo-C :
    # `IdunBattle.Core.Services.TargetingOptions$$.ctor` a TROIS surcharges, et
    # `list_xrefs` place `CrusadeOfWrathAbility$$.ctor` sur celle a SIX parametres
    # (`isSelfCasting, range, forceMeleeTarget, rules, getDynamicInvalidCasterReason,
    # getDynamicInvalidTargetReason`, `frida/methods.tsv`) -- ni l'overload PRESET+FLAGS
    # (`template, additionalRules`), ni la copie pure (`template`). Le `0x400` visible est donc bien
    # le masque EFFECTIF, sans OU avec un preset.
    # ⚠ CONTRASTE AVEC LE VOISIN 1061 `UnbreakableDuty`, MEME forme de ctor et MEME `TargetingRange` :
    # lui porte `0x8400` = `TargetIsFriendly | CasterIsPossibleTarget`. Ici le bit
    # `CasterIsPossibleTarget` est ABSENT -- concordant avec l'i2 (« all OTHER friendly units ») et
    # avec le `op_Subtraction Caster` de l'arbre. Recopier le masque du voisin aurait ouvert le cast
    # sur le caster lui-meme.
    # Valeur RELUE au decompile a la migration : elle est bit-identique a celle qui vivait dans
    # `TARGETING_OPTIONS_UNPORTED` (`targeting.py`), d'ou elle est RETIREE par le contrat de
    # disjonction (une ability portee tient son masque sur SA classe).
    TARGETING_OPTIONS = TargetingOptions(rules=TR.TargetIsFriendly, self_cast=True,
                                         range=RANGE_FROM_CONFIG,
                                         force_melee_target=RANGED_BOOL_FALSE)

    # `AbilityAttackType` = 3e argument d'`IdunBattle.Entities.Abilities.AActiveAbility$$.ctor` = le
    # litteral **`2`** (`Others`), LU au ctor -> transcrit dans la table `ABILITY_ATTACK_TYPE`
    # (`abilities/attack_type.py`), qui est le registre de cette donnee. TRANSCRIT, jamais deduit :
    # l'arbre FRAPPE (attaque NORMALE gratuite via `UseActiveAbility`), ce qui ferait ecrire
    # `DirectTargetAttack` a l'oeil -- et c'est justement la lecture INVERSE qu'ont donnee `HolyDuel`
    # 1050 et `Drachnyen` 1029, MEME forme d'arbre, litteral `0`. Meme valeur que `UnbreakableDuty`
    # 1061, du meme module.

    def _params(self, state: "State", caster_id: int) -> tuple:
        """`(range, extra_dmg, extra_pierce)`.

        `range` = `AbilityConfiguration$$GetNumberConstant(config, 0x16)` = `constants.range` = 2
        (CONSTANTE, jamais scalee). Niveau = `active_ability_level` (1049 est l'ability ACTIVE de
        `templHelbrecht`), multiplier = `AbilityVariablesMultiplierPercentage` de l'unite --
        `ability_var` ne l'applique qu'aux variables listees dans `variablesAffectedByRarityBonus`,
        ici `['extraDmg']` SEUL : `extraPierceRatio` sort brut, par la regle de config, pas par une
        exception ecrite ici."""
        e = state.get_entity(caster_id)
        sc = e.get_component(StatsComponent) if e is not None else None
        ctx = sc.ctx if sc is not None else None
        level = ctx.active_ability_level if ctx is not None else 0
        mult = ctx.ability_variables_multiplier if ctx is not None else 100
        rng_range = ability_var(self.ABILITY_ID, "range", is_constant=True) or 1
        extra_dmg = ability_var(self.ABILITY_ID, "extraDmg", level, multiplier_pct=mult) or 0
        extra_pierce = ability_var(self.ABILITY_ID, "extraPierceRatio", level,
                                   multiplier_pct=mult) or 0
        return int(rng_range), int(extra_dmg), int(extra_pierce)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if state.get_entity(caster_id) is None:
            return None
        range_val, extra_dmg, extra_pierce = self._params(state, caster_id)
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, caster_id, target_id)
        crusade_of_wrath_tree(range_val, extra_dmg, extra_pierce).execute(entities, ectx)
        buffs = [p for n, p in ectx.emitted if n == "AddStaticStatModifierEffect"]
        atk = next((p for n, p in ectx.emitted if n == "UseActiveAbility"), None)
        return {"ability": CRUSADE_OF_WRATH_ID, "caster": caster_id, "target": target_id,
                "range": range_val, "buffs": buffs, "attack": atk, "dsl": True}


# Les trois cles de config LUES au decompile de 1049, nommees (regle « un entier qui DESIGNE passe
# par un ENUM »). ⚠ QUALIFICATION : `8`/`0x3f` sont des `AbilityVariableType` -- type DECLARE du 1er
# parametre de `AbilityConfiguration$$GetVariableForLevel` -- et `0x16` un `AbilityConstantType`
# (`GetNumberConstant`). Les ordinaux se croisent, et la confusion serait SILENCIEUSE (aucune erreur,
# juste la mauvaise cle du gameconfig) : `AbilityConstantType(8)` nomme `unitToSpawn`, `(63)` nomme
# `damageProfile_2`, et `AbilityVariableType(22)` nomme `blockDmg_2` -- trois cles sans aucun rapport
# avec `extraDmg` / `extraPierceRatio` / `range`.
assert int(AbilityVariableType.extraDmg) == 8 and int(AbilityVariableType.extraPierceRatio) == 0x3F


# =================================================================================================== #
# HolyDuel (1050, `templChampion` -- Brother Jaeger, HERO Black Templars)
#
# `IdunBattleLogic.Entities.Abilities.Active.Loki.HolyDuelAbility$$ExecuteBehaviour` (MIRROR du
# DECOMPILE, build `rnca9r7q6c`) :
#
#   [1] bond   = DSLBehaviors.AddBondEffect( 0x443 = 1091 HolyDuel_Taunt,
#                                            AbilityStateReference,
#                                            source       = Caster@DSLSelectors+0x48,
#                                            targets      = Target@DSLSelectors+0x60,
#                                            bondedEntity = Caster@DSLSelectors+0x48,
#                                            options ZEROEES )
#   [2] attack = DSLBehaviors.UseActiveAbility( subject     = Caster@0x48,
#                                               targets     = Target@0x60,
#                                               abilityType = DSLSelectors.UnitNormalAttackType(
#                                                                 Caster@0x48),
#                                               source      = Nullable(AbilityOrEffect(...)),
#                                               <opts>, <opts> )
#   AActiveAbility.Execute( entities, this, op_BitwiseAnd([1], [2]) )
#
# i2 : « Brother Jaeger Taunts an adjacent enemy unit and immediately performs a normal attack
# against it. Brother Jaeger deals +582 Damage and takes -364 Damage from the target while it's
# Taunted by him. Brother Jaeger is also Taunted by the target and the taunt does not expire with
# rounds passed. »
#
# LA CATEGORIE ANNONCEE ETAIT FAUSSE, et c'est un RESULTAT : `docs/rl/combat-ability-coverage.md`
# classait 1050 en EFFECT/BUFF (colonne derivee du `damageProfile` de l'ARME du porteur, pas du
# behaviour). Le cast FRAPPE bel et bien -- mais par l'attaque NORMALE de l'unite ([2]), pas par une
# `AttackWithAbilityDamage` : `abilities.HolyDuel` n'a NI `minDmg`/`maxDmg`, NI `nrOfHits`, NI
# `damageProfile` (gameconfig : deux variables seulement, `extraDmg` et `dmgReduction`). Le +582 de
# l'i2 n'est PAS le degat du cast : c'est le bonus additif que l'EFFET 1092 verse a chaque attaque du
# champion contre son duelliste. Meme configuration que `Drachnyen` (1029).
#
# TOUT le reste du kit vit dans les EFFETS (`entities/effects/loki/holy_duel.py`) : 1091 est un
# composite qui pose les quatre sous-effets du duel, dont les DEUX `Taunted` symetriques.
# =================================================================================================== #

HOLY_DUEL_ID = "HolyDuel"
HOLY_DUEL_TAUNT = int(EffectType.HolyDuel_Taunt)        # 0x443 = 1091


def holy_duel_tree():
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.HolyDuelAbility$$ExecuteBehaviour`
    (MIRROR 1:1, cf. le bloc de commentaire ci-dessus) :

        op_BitwiseAnd( AddBondEffect(1091, source=Caster, targets=Target, bondedEntity=Caster),
                       UseActiveAbility(Caster, Target, UnitNormalAttackType(Caster)) )

    - `AddBondEffect(..., duration_rounds=None)` = les options natives ZEROEES (aucun
      `TurnsFromRounds`) -> `DefaultAmountOfRounds(0x443)`, que
      `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Effect$$
      DefaultAmountOfRounds` rend NULL (relu : `0x443` sort par la branche `return 0` du switch)
      -> effet PERMANENT. C'est litteralement l'i2 « the taunt does not expire with rounds passed ».
    - `bonded_ref=Caster()` = le 5e argument natif (`bondedEntity` = `Caster@0x48`), celui que
      `AddEffectBehaviour$$GetEffectBuilder` resout puis ecrit dans le composant de bond de
      l'entite-effet. C'est LUI qui fait tout le duel : `HolyDuel_TauntEffect$$ApplyInternal` le
      relit pour savoir sur QUI poser les trois sous-effets du champion.
    - `scale_from_source=True` = le 3e argument natif `abilityState` (`AbilityStateReference` du
      caster), que l'entite-effet BAKE et que relit `BaseEffect$$GetAbilityState` quand les
      `ConfigVar` de 1092/1093 s'indexent (`extraDmg`/`dmgReduction` sont tous deux
      `variablesAffectedByRarityBonus`).
    - `UseActiveAbility(Caster(), Target())` = la feuille deja portee, specialisee au dispatch
      d'ATTAQUE NORMALE (`UnitNormalAttackType(Caster)` -> `AttackDamageOperation.execute`,
      resolveur d'arme par distance).

    ORDRE LOAD-BEARING : le bond est pose AVANT l'attaque (`op_BitwiseAnd` evalue a gauche
    d'abord), donc le `+extraDmg` de 1092 mord DES le coup de ce cast -- exactement comme
    `Drachnyen` arme sa triggered avant son attaque. Aucun tirage RNG avant [2] ([1] est
    deterministe) -> le flux `state.rng` de l'attaque est celui d'une attaque normale nue."""
    bond = AddBondEffect(HOLY_DUEL_TAUNT, EffectType.HolyDuel_Taunt.name,
                         source_ref=Caster(), target_ref=Target(),
                         duration_rounds=None,          # options ZEROEES -> DefaultAmountOfRounds
                         bonded_ref=Caster(),           # 5e argument natif : `bondedEntity`
                         scale_from_source=True)        # 3e argument natif : `abilityState`
    attack = UseActiveAbility(Caster(), Target())       # UnitNormalAttackType(Caster)
    return op_and(bond, attack)


class HolyDuelAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.HolyDuelAbility$$ExecuteBehaviour` (id 1050,
    `templChampion` « Brother Jaeger », HERO Black Templars) -- cf. le bloc de commentaire.

    Kit gameconfig 1050 : `attackRangeType=Normal`, variables `extraDmg` / `dmgReduction` (les DEUX
    `variablesAffectedByRarityBonus`). AUCUNE variable de degat propre -> le cast n'a pas d'attaque
    d'ability, il DISPATCHE l'attaque NORMALE de l'unite.

    OBSERVABLE porte : (1) effet 1091 `HolyDuel_Taunt` pose sur la CIBLE, PERMANENT, bonde au
    champion ; par cascade de son `ApplyInternal`, (2) `Taunted` (27) sur la cible bonde au champion
    -- donc `ForcedAttackTargetsComponent(cible) = [champion]` -- et (3) `Taunted` (27) +
    `HolyDuel_ExtraDmg` (1092) + `HolyDuel_DmgReduction` (1093) sur le CHAMPION, bondes a la cible ;
    (4) une attaque NORMALE dirigee sur la cible, qui beneficie DEJA du `+extraDmg`.

    Face DECISION deja portee (`playbook/noncomparable/holy_duel.py`, gate `ShouldEvaluate` =
    `!EnemyMightBeKilledWithNormalAttack`) ; CE port est la face EXECUTION, qui etait un NO-OP
    SILENCIEUX (1050 absente d'`ABILITY_CLASSES` : `AbilityHandler.visit_ActiveAbilityMessage`
    l'ignorait -- 0 degat, 0 effet, aucune erreur).

    Renvoie {ability, caster, target, bond, attack, dsl}. Termine le tour (1050 hors des frozensets
    de `base.py`)."""

    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.HolyDuel)      # 1050
    ABILITY_ID = HOLY_DUEL_ID

    # GATE DE CIBLE. `IdunBattleLogic.Entities.Abilities.Active.Loki.HolyDuelAbility$$.ctor` :
    #   1. il recopie les 0x40 octets du PRESET STATIQUE `TargetingOptions` `statics+0x40` ;
    #   2. il passe ce preset a la surcharge **PRESET + FLAGS**
    #      `TargetingOptions$$.ctor(&opts, &preset, 0x200000000)`, dont la seule difference avec une
    #      copie pure est `opts.Rules = flags | preset.Rules` ;
    #   3. puis `AActiveAbility$$.ctor(this, &opts, 0)`.
    # `IdunBattle.Core.Services.TargetingOptions$$.cctor` ecrit pour le preset `+0x40` :
    # `+0x68` (= +0x28 relatif) `Rules = 0x4000`, `+0x60` (= +0x20) `forceMeleeTarget = 1`
    # (`RangedBool.False`) et le `TargetingRange` statique a `onlyAdjacent` (MEME preset que
    # `Drachnyen` 1029 / `JakhalStimms` 1131 / `KillMaimBurn` 1132 : cible ADJACENTE obligatoire, la
    # constante de config `range` n'est PAS consultee).
    # MASQUE EFFECTIF = `0x200000000 | 0x4000` = **0x200004000** =
    # `TargetIsNotAnObject | TargetIsEnemy`.
    # ⚠ Le `0x4000` vient du PRESET, pas du litteral visible -- c'est le OU qui le dit. Meme couple
    # preset/flags que `VexillaMagnifica` (1183) ; `AttemptedPossession` (1101) porte le MEME flag
    # `0x200000000` sur un AUTRE preset (`+0x180`, rules `0x4002`) et ne vaut donc pas la meme chose.
    # Coherent avec l'i2 (« an adjacent enemy unit »).
    TARGETING_OPTIONS = TargetingOptions(rules=TR.TargetIsEnemy | TR.TargetIsNotAnObject,
                                         self_cast=False,
                                         range=RANGE_ADJACENT,
                                         force_melee_target=RANGED_BOOL_FALSE)

    # `AbilityAttackType` = 3e argument d'`IdunBattle.Entities.Abilities.AActiveAbility$$.ctor` = le
    # litteral `0` (`DirectTargetAttack`), LU au ctor -> transcrit dans la table
    # `ABILITY_ATTACK_TYPE` (`abilities/attack_type.py`), qui est le registre de cette donnee.
    # TRANSCRIT, jamais deduit : l'arbre n'attaque PAS « en direct » (il dispatche l'attaque NORMALE
    # via `UseActiveAbility`), exactement comme `Drachnyen` 1029 -- et le litteral vaut quand meme 0.

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None or state.get_entity(caster_id) is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        holy_duel_tree().execute(entities_from_state(state, caster_id, target_id), ectx)
        bond = next((p for n, p in ectx.emitted if n == "AddBondEffect"), None)
        atk = next((p for n, p in ectx.emitted if n == "UseActiveAbility"), None)
        return {"ability": HOLY_DUEL_ID, "caster": caster_id, "target": target_id,
                "bond": bond, "attack": atk, "dsl": True}


# =================================================================================================== #
# UnbreakableDuty (1061, `templAncient` -- Ancient Thoread, HERO Black Templars)                #572 #
#
# `IdunBattleLogic.Entities.Abilities.Active.Loki.UnbreakableDutyAbility$$ExecuteBehaviour` (MIRROR du
# DECOMPILE, build `rnca9r7q6c`) -- UN SEUL noeud terminal passe a `AActiveAbility$$Execute` :
#
#   extraHp  = DSLFormulas.ConfigVar(0x1e = extraHp,  AbilityState, config@this+0x60)
#   extraDmg = DSLFormulas.ConfigVar(8    = extraDmg, AbilityState, config@this+0x60)
#
#   [A] hpBuff  = DSLBehaviors.AddStaticStatModifierEffectToOwner(
#                     0x4e3 = 1251 UnbreakableDuty_Health, statType = 5 Health,
#                     amount = extraHp, turns = **null**, isHidden = false)
#   [B] hpFill  = DSLBehaviors.ChangeStat(targets = Owner@DSLSelectors+0x30,
#                     stat = Stat(5 = Health, part 0 = Current), mode = 2 = Add, amount = extraHp,
#                     modificationEntity = null, selectionType = 3 = OnlyAliveAndTargetable,
#                     isModifiable = false, isHiddenModification = false)
#   [C] dmgBuff = DSLBehaviors.AddStaticStatModifierEffectToOwner(
#                     0x4e8 = 1256 UnbreakableDuty_Damage, statType = 0 Attack,
#                     amount = extraDmg, turns = **null**, isHidden = false)
#   [D] sel     = DSLSelectors.ValidNormalAttackTargets(CasterTile@+0x50, CasterTile@+0x50,
#                                                       range = null, ignoreRule/additionalRule = null)
#                 op_BitwiseAnd DSLSelectors.AdjacentEnemies(Caster@+0x48, unique = 1,
#                                                            selectionType = 3)
#       attack  = DSLBehaviors.UseActiveAbility(caster = Owner@+0x30,
#                                               target = DSLSelectors.PickRandomly(sel, amount = 1,
#                                                            allowDuplicates = 0,
#                                                            maxDuplicatesAllowed = 0x7fffffff,
#                                                            ignoreForcedTargets = 0),
#                                               activeAbilityType = **0x45 = Loki_NormalAttack**,
#                                               parentAbility = Nullable(AbilityOrEffect(this+0x10)),
#                                               trigger/options ZEROES)
#       free    = DSLBehaviors.If(DSLTriggers.AmountIsGreaterThanZero(DSLFormulas.Count(sel)),
#                                 attack, null)
#   [E] dead    = DSLSelectors.UnitsWithTraits(
#                     DSLSelectors.Friends(of = Owner@+0x30,
#                                          entities = DSLSelectors.AllDeadOrResurrectedUnits(),
#                                          selectionType = 0),
#                     [0x1a = Imperial, 0x10 = Hero], selectionType = 0)
#       gate    = DSLTriggers.AmountIsEqualOrGreater(DSLFormulas.Count(dead), DSLFormulas.Direct(2))
#       body    = ((A op_Addition B) op_Addition C) op_Addition free
#       gated   = DSLBehaviors.If(gate, body, null)
#   [F] aura    = DSLBehaviors.AddEffect(0x449 = 1097 UnbreakableDuty_DamageReduction,
#                                        abilityState = AActiveAbility.AbilityStateReference,
#                                        targets = Owner@+0x30,
#                                        turns = DSLFormulas.TurnsFromRounds(1))
#
#   AActiveAbility.Execute(entities, this, aura op_Addition gated)
#
# i2 mot a mot : « Ancient Thoread and all friendly units within 2 hexes receive -33% Damage until the
# start of their next turn. If 2 or more friendly Imperial Characters are dead upon activation of this
# ability, Ancient Thoread gains 7275 extra Health and +1455 Damage until the end of the battle and
# immediately performs a normal attack against an adjacent enemy. »
#
# LA CATEGORIE ANNONCEE EST INCOMPLETE, et c'est un RESULTAT : `docs/rl/combat-ability-coverage.md`
# classe 1061 en EFFECT/BUFF (colonne derivee du `damageProfile` de l'ARME du porteur, pas du
# behaviour). C'est vrai d'UNE mecanique sur CINQ. Les quatre autres sont : une AURA de reduction de
# degat PROJETEE sur les allies (l'effet 1097 vit sur le caster et se projette via son
# `CreateTargetSelector`) ; un SOIN direct (`ChangeStat` mode Add sur la stat FILL-UP Health, un
# canal que le mot « buff » ne couvre pas -- il monte les PV COURANTS, pas un modificateur) ; et un
# CAST QUI FRAPPE, par l'attaque NORMALE (`UseActiveAbility(Loki_NormalAttack)`, MEME configuration
# que `HolyDuel` 1050 et `Drachnyen` 1029 : `abilities.UnbreakableDuty` n'a NI `minDmg`/`maxDmg`, NI
# `nrOfHits`, NI `damageProfile` -- gameconfig : trois variables `dmgReductionPct`/`extraDmg`/
# `extraHp` et UNE constante `range`). Les 5 mecaniques s'apparient UNE A UNE aux 5 propositions de
# l'i2 (le +extraHp couvrant les DEUX noeuds [A] et [B], MAX et COURANT).
#
# ORDRE LOAD-BEARING (`op_Addition` evalue a GAUCHE d'abord) : [F] l'aura de reduction est posee
# AVANT tout, puis dans la branche gatee [A] +maxHP, [B] +PV courants, [C] +Attack, et SEULEMENT
# ENSUITE [D] l'attaque libre -- qui beneficie donc DEJA du `+extraDmg`. Une permutation ne changerait
# ni le flux RNG (A/B/C sont deterministes) ni le degat de l'attaque... sauf justement si [C] passait
# APRES [D]. C'est le seul ordre observable, et il est garde (`test_572_unbreakable_duty_offline.py`).
# =================================================================================================== #

UNBREAKABLE_DUTY_ID = "UnbreakableDuty"
UNBREAKABLE_DUTY_DAMAGE_REDUCTION = int(EffectType.UnbreakableDuty_DamageReduction)   # 0x449 = 1097
UNBREAKABLE_DUTY_HEALTH = int(EffectType.UnbreakableDuty_Health)                      # 0x4e3 = 1251
UNBREAKABLE_DUTY_DAMAGE = int(EffectType.UnbreakableDuty_Damage)                      # 0x4e8 = 1256
#: `DSLFormulas$$Direct(2)` du `AmountIsEqualOrGreater` -- le seuil de l'i2 (« 2 or more »).
UNBREAKABLE_DUTY_MIN_DEAD_IMPERIAL_HEROES = 2
#: Cle de source du `ChangeStat` [B]. La branche HEALTH de la feuille mute `HealthComponent.hp`
#: directement (stat FILL-UP) et ne la lit pas ; elle reste NOMMEE pour la tracabilite.
_UD_HEAL_SOURCE = "UnbreakableDuty:hpFill"


def unbreakable_duty_dead_imperial_heroes():
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.UnbreakableDutyAbility$$GetAmountOfDeadImperialUnits`
    -- MIRROR 1:1 de son sous-arbre (le natif RECOPIE la meme expression, inline, dans
    `$$ExecuteBehaviour` : un seul foyer cote port) :

        UnitsWithTraits( Friends(of = Owner@DSLSelectors+0x30,
                                 entities = AllDeadOrResurrectedUnits(),
                                 selectionType = 0),
                         [0x1a = Imperial, 0x10 = Hero], selectionType = 0 )

    `UnitsWithTraits` est une CONJONCTION (`units_with_traits`, foyer `selectors/units.py`) : il faut
    les DEUX traits -- « Imperial Characters » de l'i2, `Character` etant le trait `Hero` (0x10).
    `AllDeadOrResurrectedUnits` = les morts du state PLUS les ressuscites, pas seulement les morts.
    `Friends(of = Owner)` = de l'equipe du porteur."""
    # #585-r1 -- ⚠ CONTRE-EXEMPLE : les DEUX litteraux LUS ici valent **0** (`Any`), pas 3, et la
    # cause est mecanique : la source est `AllDeadOrResurrectedUnits`. `MatchesUnitSelectionType`
    # teste `IsAlive` pour `OnlyAlive` COMME pour `OnlyAliveAndTargetable` -> un `3` recopie par
    # symetrie aurait VIDE l'ensemble, donc rendu le compte toujours nul, sans erreur ni crash.
    # `Any` est pose EXPLICITEMENT (et non laisse a `None`) pour que le littéral soit LU au site.
    dead = Friends(AllDeadOrResurrectedUnits(), reference=Owner(),
                   selection_type=int(UnitSelectionType.Any))
    return units_with_traits(dead, (UnitTrait.Imperial, UnitTrait.Hero),
                             selection_type=int(UnitSelectionType.Any))   # 0x1a, 0x10


def unbreakable_duty_free_attack_targets():
    """Le selecteur `sel` de [D] -- MIRROR 1:1 :

        ValidNormalAttackTargets(CasterTile@+0x50, CasterTile@+0x50, null, null, null)
          op_BitwiseAnd
        AdjacentEnemies(Caster@+0x48, unique = 1, selectionType = 3)

    Les DEUX slots de `ValidNormalAttackTargets` recoivent `CasterTile` -- lu aux octets du call-site
    (un seul `mov r8,[r10+0x50]`, recopie dans `rdx`), la ou `SorcerousFacadeAbility$$GetTarget` passe
    `(Caster@+0x48, CasterTile@+0x50)`. Sans consequence : le slot `unit` est consomme par
    `SelectSingle` -> `TargetsSelector$$SelectUnit`, qui resout une TUILE en son OCCUPANT (cf. la
    docstring du noeud). On mirror le slot LU, pas le slot attendu.

    `AdjacentEnemies` est la surcharge a 3 arguments (`unit, unique, selectionType`) -- **aucun rayon**,
    donc ring-1 : « an adjacent enemy » de l'i2. L'intersection avec les cibles d'attaque normale
    valides est ce qui fait respecter le masque de ciblage de l'attaque normale (portee, obstruction,
    cibles interdites)."""
    return And(ValidNormalAttackTargets(CasterTile(), CasterTile()),
               AdjacentEnemies(Caster()))


def unbreakable_duty_tree(extra_hp: int, extra_dmg: int):
    """Arbre COMPLET de `...UnbreakableDutyAbility$$ExecuteBehaviour` (cf. le bloc de commentaire).

    `extra_hp` / `extra_dmg` = les DEUX `ConfigVar` COLLAPSES a la valeur qu'ils rendent pour le
    caster (`variables.extraHp` / `variables.extraDmg` indexes par l'`active_ability_level` et scales
    par l'`AbilityVariablesMultiplierPercentage` -- les DEUX sont dans
    `variablesAffectedByRarityBonus`). Le collapse est celui qu'on fait partout ailleurs pour un
    `ConfigVar` d'ability ACTIVE (cf. `ability_attack_params`) : le natif resout la meme chose contre
    l'`AbilityState` du caster, fige a la construction du behaviour.

    `duration_rounds = 1` de l'`AddEffect` = le `TurnsFromRounds(1)` natif ; `duration_rounds = None`
    des deux `AddStaticStatModifierEffect` = le `turns = null` natif -> `DefaultAmountOfRounds` ->
    PERMANENT (« until the end of the battle » de l'i2).

    `scale_from_source = True` = l'`AbilityStateReference` que l'`AddEffect` natif passe en 2e
    argument : l'entite-effet 1097 BAKE le niveau/multiplier du CASTER, et c'est contre lui que son
    `ConfigVar(0x46 = dmgReductionPct)` s'indexe."""
    hp_buff = AddStaticStatModifierEffect(Owner(), UNBREAKABLE_DUTY_HEALTH, int(StatType.HEALTH),
                                          Const(int(extra_hp)),
                                          name=EffectType.UnbreakableDuty_Health.name,
                                          duration_rounds=None)          # turns = null -> PERMANENT
    hp_fill = ChangeStat(Owner(), int(StatType.HEALTH), "add", _UD_HEAL_SOURCE, int(extra_hp))
    dmg_buff = AddStaticStatModifierEffect(Owner(), UNBREAKABLE_DUTY_DAMAGE, int(StatType.ATTACK),
                                           Const(int(extra_dmg)),
                                           name=EffectType.UnbreakableDuty_Damage.name,
                                           duration_rounds=None)         # turns = null -> PERMANENT
    sel = unbreakable_duty_free_attack_targets()
    attack = UseActiveAbility(Owner(), PickRandomly(sel, 1))             # 0x45 = Loki_NormalAttack
    free = IfBehaviour(AmountIsGreaterThanZero(Count(sel)), attack)
    body = op_add(op_add(op_add(hp_buff, hp_fill), dmg_buff), free)
    gate = AmountIsEqualOrGreater(Count(unbreakable_duty_dead_imperial_heroes()),
                                  Const(UNBREAKABLE_DUTY_MIN_DEAD_IMPERIAL_HEROES))
    gated = IfBehaviour(gate, body)
    aura = AddEffect(UNBREAKABLE_DUTY_DAMAGE_REDUCTION,
                     EffectType.UnbreakableDuty_DamageReduction.name, Owner(),
                     duration_rounds=1, scale_from_source=True)          # TurnsFromRounds(1)
    return op_add(aura, gated)


class UnbreakableDutyAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.UnbreakableDutyAbility$$ExecuteBehaviour`
    (id 1061, `templAncient` « Ancient Thoread », HERO Black Templars) -- cf. le bloc de commentaire.

    CINQ mecaniques (l'audit n'en annonce qu'UNE, « EFFECT/BUFF ») :
      1. AURA -33% de degat RECU sur le caster ET ses allies a <= `range`(2) hexes, `TurnsFromRounds(1)`
         (effet 1097, materialise sur le CASTER et PROJETE par son `CreateTargetSelector`) ;
      puis, SI >= 2 allies morts portant a la fois `Imperial` et `Hero` :
      2. +`extraHp` (7275 @L65) de PV MAX, PERMANENT (effet 1251) ;
      3. +`extraHp` de PV COURANTS (`ChangeStat` mode Add sur la stat FILL-UP Health) ;
      4. +`extraDmg` (1455 @L65) d'ATTACK, PERMANENT (effet 1256) ;
      5. une attaque NORMALE gratuite sur UN ennemi adjacent tire au sort parmi les cibles valides.

    Face DECISION **NON PORTEE** -- residu NOMME `#572-r2` : le natif a un playbook dedie
    (`IdunBattle.AI.Playbook.Loki.UnbreakableDutyPlaybook`, `NonComparablePlaybook<UnbreakableDuty
    Ability>` ctor `0x425 = 1061`), dont `$$GetUseProbability` vaut `10 x <cardinal du slot de query
    0x75(tile, range)>` puis `+40` si le gate des deux morts passe et `+70` (au lieu de `+40`) s'il
    existe en plus une cible au slot `0x7d`. Les deux slots d'interface ne sont pas resolus -- c'est
    ce qui manque, pas l'arbre.

    Renvoie {ability, caster, target, aura, gate_passed, buffs, attack, dsl}. Termine le tour (1061
    hors des frozensets de `base.py`)."""

    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.UnbreakableDuty)   # 1061
    ABILITY_ID = UNBREAKABLE_DUTY_ID

    # GATE DE CIBLE. `...Active.Loki.UnbreakableDutyAbility$$.ctor` est la forme **FLAGS DIRECTS**
    # (surcharge a 7 arguments, le litteral EST le masque) : il recopie les 3 qwords du champ statique
    # `<TargetingRange statics>+0x18` dans un local puis appelle
    #     `TargetingOptions$$.ctor(&opts, 1, &range, 1, 0x8400, 0, 0)`
    # et enfin `AActiveAbility$$.ctor(this, &opts, 2)`.
    #   selfCast          = 1
    #   range             = `TargetingRange` statics `+0x18` = useRangeFromConfig -> `constants.range` = 2
    #   forceMeleeTarget  = 1 = `RangedBool.False` (l'enum natif est INVERSE)
    #   rules             = 0x8400 = `TargetIsFriendly (0x400) | CasterIsPossibleTarget (0x8000)`
    # Coherent avec l'i2 (« Ancient Thoread AND all friendly units within 2 hexes ») : la cible est un
    # ALLIE, et le caster est lui-meme une cible possible.
    # Valeur RELUE au decompile a la migration : elle est bit-identique a celle qui vivait dans
    # `TARGETING_OPTIONS_UNPORTED` (`targeting.py`), d'ou elle est RETIREE par le contrat de
    # disjonction (une ability portee tient son masque sur SA classe).
    TARGETING_OPTIONS = TargetingOptions(rules=TR.TargetIsFriendly | TR.CasterIsPossibleTarget,
                                         self_cast=True, range=RANGE_FROM_CONFIG,
                                         force_melee_target=RANGED_BOOL_FALSE)

    # `AbilityAttackType` = 3e argument d'`IdunBattle.Entities.Abilities.AActiveAbility$$.ctor` = le
    # litteral **`2`** (`Others`), LU au ctor -> transcrit dans la table `ABILITY_ATTACK_TYPE`
    # (`abilities/attack_type.py`), qui est le registre de cette donnee. TRANSCRIT, jamais deduit :
    # l'arbre FRAPPE (via `UseActiveAbility`), exactement comme `HolyDuel` 1050 et `Drachnyen` 1029 --
    # qui, eux, portent `0`. Le litteral ne se derive pas du profil de l'arbre.

    def _params(self, state: "State", caster_id: int) -> tuple:
        """`(extra_hp, extra_dmg)` = les deux `ConfigVar` collapses.

        Niveau = `active_ability_level` (1061 est l'ability ACTIVE de `templAncient`), multiplier =
        `AbilityVariablesMultiplierPercentage` de l'unite -- les DEUX variables sont dans
        `variablesAffectedByRarityBonus` (`['extraDmg', 'extraHp']`), donc les DEUX sont scalees."""
        e = state.get_entity(caster_id)
        sc = e.get_component(StatsComponent) if e is not None else None
        ctx = sc.ctx if sc is not None else None
        level = ctx.active_ability_level if ctx is not None else 0
        mult = ctx.ability_variables_multiplier if ctx is not None else 100
        extra_hp = ability_var(self.ABILITY_ID, "extraHp", level, multiplier_pct=mult) or 0
        extra_dmg = ability_var(self.ABILITY_ID, "extraDmg", level, multiplier_pct=mult) or 0
        return int(extra_hp), int(extra_dmg)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if state.get_entity(caster_id) is None:
            return None
        extra_hp, extra_dmg = self._params(state, caster_id)
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, caster_id, target_id)
        unbreakable_duty_tree(extra_hp, extra_dmg).execute(entities, ectx)
        aura = next((p for n, p in ectx.emitted if n == "AddEffect"), None)
        buffs = [p for n, p in ectx.emitted if n == "AddStaticStatModifierEffect"]
        heal = next((p for n, p in ectx.emitted if n == "ChangeStat"), None)
        atk = next((p for n, p in ectx.emitted if n == "UseActiveAbility"), None)
        return {"ability": UNBREAKABLE_DUTY_ID, "caster": caster_id, "target": target_id,
                "aura": aura, "gate_passed": bool(buffs), "buffs": buffs, "heal": heal,
                "attack": atk, "dsl": True}


# Les cles de config LUES au decompile de 1061, nommees (regle « un entier qui DESIGNE passe par un
# ENUM »). ⚠ QUALIFICATION : `0x1e`/`8`/`0x46` sont des `AbilityVariableType` -- type DECLARE du 1er
# parametre de `AbilityConfiguration$$GetVariableForLevel`, l'accesseur derriere `DSLFormulas$$
# ConfigVar` -- et `0x16` un `AbilityConstantType` (`DSLFormulas$$ConfigConst`). Les ordinaux se
# croisent : `AbilityConstantType(30)` nomme `nrOfProjectilesMax`, `(8)` nomme `unitToSpawn` et
# `(70)` nomme `summonId` -- trois cles sans aucun rapport.
assert int(AbilityVariableType.extraHp) == 0x1E and int(AbilityVariableType.extraDmg) == 0x08
assert int(AbilityVariableType.dmgReductionPct) == 0x46   # relu par l'entite-effet 1097
