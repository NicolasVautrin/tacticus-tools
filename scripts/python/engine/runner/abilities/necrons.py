"""Abilities Necrons (namespace natif `Abilities.Active.Loki.*`) — case-220 §6.7.

Module DEDIE a la faction Necrons (comme `blacklegion.py`/`genestealer.py`/`deathguard.py` : une classe
par ability, l'arbre SPECIFIQUE vit avec sa classe). RE ghidra gqfc5mff6c (VA citees). Doc :
docs/rl/case-220/necrons.md.

Contenu :
- `HarbingerOfDestruction` (1008, `necroPlasmancer`) — attaque la cible + N-1 ennemis ALEATOIRES dans un
  DISQUE rayon-2 du CASTER (non obscurcis, damageable, hors cible), 1 coup MinMaxDamage profil DirectDamage
  (pierce 100) chacun. Selecteur rayon-2 SurroundingEnemies (template splash `loki/splash.py`, adapte du
  BringerOfDespair caster-ancre `blacklegion.py`).
- `ResurrectionOrb` (1009, `necroOverlord`) — `Spawn(CanAddUnit(AdjacentTiles(casterTile)), N,
  'necroSmnWarrior', WithStatsFromConfig)` avec N = `Min(Count(amis MORTS mecaniques) +
  TURNS_STARTED(caster), maxSummons)`. ⚠ Sur `rnca9r7q6c` l'ability n'est PLUS un summon pur : elle a
  gagne `$$GetPossibleResurrectTargets` / `$$GetResurrectBehaviour` / `$$GetNumSummonsFormula` /
  `$$GetPossibleSpawnOrResurrectTiles` (absents de `gqfc5mff6c`). #289 porte les SELECTEURS et
  FORMULES (partages avec la face DECISION) ; le volet RESURRECTION d'`$$ExecuteBehaviour` reste un
  residu nomme, cf. `resurrection_orb_tree`.
- `Chronometron` (1226, `necroChronomancer`) — `Foreach(SurroundingEnemies(caster, range), (If(HasTrait(It,
  Summon), AddEffect(Stunned), AddEffect(Pinned)) & AddEffect(Chronometron_ExtraDamage)))`.
- `MultiThreatEliminator` (1006, `necroDestroyer`) — `ChainLeftOverHitsAttackDamage` : 6 coups Gauss sur la
  cible, report des coups NON consommes (kills) sur l'ennemi suivant, +1 coup par kill.
- `TunnelingHorror` (1011, `necroSmnDestroyer`) — cast TILE-TARGET : `RemoveUnitFromItsTiles(Caster, true)`
  (le caster QUITTE le plateau sans mourir) & `RemoveAllForcedAttackTargets(Caster)` &
  `AddBondEffect(0x459 -> la tuile visee, bondedEntity = Caster, PERMANENT)`. Vecteur de pose du
  marqueur `TunnelingHorror_PendingSummon` ; #366-r1.
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from ...dsl.base import AAmountFormula, Const, TargetsSelector
from ...dsl.effects import ExecutionContext
from ...dsl.event_trigger_type import EventTriggerType
from ...entities.behaviours import AtomicGroup, Foreach, If as IfBehaviour, Seq, op_add, op_and
from ...entities.formulas import Count, Min, RandomAmount, StatAmount, Sum
from ...entities.selectors.accessors import ActiveTarget, CasterTile, FixedTileIds, Target
from ...entities.selectors.tiles import AdjacentTiles, AllAliveUnits, CanAddUnit, Caster
from ...entities.selectors.units import (
    AdjacentUnits, AllDeadOrResurrectedUnits, And, Damageable, Enemies, Friends, Sub,
    SurroundingEnemies, SurroundingUnits, Union, UnitSet, UnitsWithTrait, Unobscured, hero_units
)
from ...entities.stats import StatType
from ...entities.traits.unit_trait import UnitTrait
from ...entities.unit_selection_type import UnitSelectionType

#: `UnitSelectionType` LU au dernier argument des `DSLSelectors$$*` de ce fichier -- releve #585-r1,
#: build `rnca9r7q6c`, littéral par littéral. ⚠ CE FICHIER PORTE LE CONTRE-EXEMPLE : le `Friends`
#: de `...ResurrectionOrbAbility$$GetPossibleResurrectTargets` recoit **0** (`Any`), pas 3 -- il
#: selectionne des unites MORTES, qu'`OnlyAlive*` ecarterait TOUTES. Ne jamais recopier `SELECTION`
#: sans avoir relu le littéral du call-site.
SELECTION = int(UnitSelectionType.OnlyAliveAndTargetable)     # 3
from ...entities.triggers import ActorHasTriggeredAbility, HasTrait
from ...entities.active_ability_type import ActiveAbilityType
from ...entities.ability_variable_type import AbilityVariableType
from ...entities.effect_type import EffectType
from ...entities.triggered_ability_type import TriggeredAbilityType
from ...entities.effects.magnitude import ability_var
from .base import ActiveAbility
from .targeting import (RANGE_ADJACENT, RANGE_FROM_CONFIG, RANGE_SELF, RANGE_WHOLE_BOARD,
                        RANGED_BOOL_FALSE, RANGED_BOOL_TRUE, TargetingOptions,
                        _dynamic_rule_adaptive_strategy)
from .targeting_rule import TargetingRule as TR
from .behaviours.ability_state import SetActiveAbilityUsed        # #996-r1-r3 (1012, slot 0x74)
from .behaviours.ai_control import PerformAIAction
from .behaviours.combat import (AttackWithAttackDamage, ChainLeftOverHitsAttackDamage,
                                UseActiveAbility)
from .behaviours.context import entities_from_state
from .behaviours.effects import AddBondEffect, AddEffect, RemoveEffect
from .behaviours.lifecycle import (RemoveAllForcedAttackTargets, RemoveUnitFromItsTiles,
                                   TriggerAbility, TRIGGERED_ABILITY_BEHAVIOURS)
from .behaviours.stats import AddStatOverrideEffect
from .behaviours.summon import Spawn
# #577 : le noeud (1) d'`AdaptiveStrategy` est l'APPELANT que la branche `Custom` de
# `RelentlessMarch` attendait depuis #328 (cf. `_relentless_march_custom`). On importe le MIRROR
# deja porte -- surtout pas un 2e port de `...RelentlessMarchAbility$$CreateBehaviour`.
from ..operations.triggers.loki.relentless_march import (
    hp_to_repair as rm_hp_to_repair, relentless_march_behaviour_tree as rm_behaviour_tree)
from .loki import _pick_randomly_n
from ...entities.ability_constant_type import AbilityConstantType   # #270-r1-r1-r3
from ...entities.formulas import Difference, If as IfAmount
from ...entities.selectors.accessors import Subject
from ...entities.selectors.units import AllDeadUnits, Filter
from ...entities.triggers import AmountIsGreaterThanZero
from ...entities.triggers import TriggerAnd, is_mechanical
from ...entities.triggers import is_mechanical
from ..components import StatsComponent
# --- #902 : `necroReanimator` (1223 ReanimationBeam / 1224 NanoscarabRepairProtocols) -------------
from ...entities.formulas import percentage_of_attack_capped_at_max
from ...entities.selectors.accessors import Actor, Owner
from ...entities.selectors.geometry import EntitiesWithAnyEffect
from ...entities.selectors.units import MechanicalUnits, Repairable
from ...entities.stats import StatPart
from ..components import has_effect_of_type
from .base import active_ability_state
from .behaviours.effects import AddDynamicStatModifierEffect
# `is_mechanical` est ALIASE : ce module importe deja l'HOMONYME `entities.triggers.is_mechanical`
# (le NOEUD DSL `DSLTriggers$$IsMechanical`, un predicat d'arbre). Celui-ci est le PREDICAT PYTHON
# `IdunBattle.Entities.UnitExtensions$$IsMechanical` (Mechanical | LivingMetal | Vehicle), qu'on
# evalue hors arbre dans les deux `GetDynamicInvalidTargetReason`. Sans alias, le second import
# masquerait le premier EN SILENCE -- exactement le vice qu'a corrige la fusion d'#112/#114.
from .behaviours.stats import ChangeStat, Repair, is_mechanical as unit_is_mechanical

if TYPE_CHECKING:
    from ..state import State


# ============ AdaptiveStrategy (necroWarden « Makhotep », actif 1005) -- #577 =====================
#
# i2 : « Triggers <Relentless March> again for all adjacent Non-Character friendly units and makes
#        them immediately take an action, dealing {minDmg}-{maxDmg} Damage per hit if they attack. »
#
# CATEGORIE REELLE : ce n'est PAS un « EFFECT/BUFF » -- c'est un ORDONNANCEUR. Le cast ne frappe
# personne : il OVERRIDE l'Attack d'un set d'allies, les fait AGIR, puis retire l'override. QUATRE
# mecaniques, comptees sur les quatre noeuds de l'`op_Addition` final (l'audit n'en voyait qu'une) :
#   (1) re-declenchement CONDITIONNEL du passif `RelentlessMarch` du caster ;
#   (2) override de stat ATTACK sur les allies adjacents NON-Character ;
#   (3) action IA FORCEE, une par unite, sans consommer leur tour ;
#   (4) retrait de l'override -- sur TOUS les allies non-Character du plateau, pas sur les seuls
#       adjacents (le selecteur du (4) N'EST PAS celui du (2) : lu, pas suppose).
#
# `IdunBattleLogic.Entities.Abilities.Active.Loki.AdaptiveStrategyAbility$$ExecuteBehaviour` --
# transcription du decompile (build `rnca9r7q6c`), dans l'ORDRE de la chaine `op_Addition` :
#
#     amount   = AActiveAbility.MinMaxDamage(this, abilityState, isPrediction: FALSE)
#     targets  = GetNonCharacterFriendsSelector( DSLSelectors.AdjacentUnits(Caster@DSLSelectors+0x48,
#                                                                          unique: 1, selType: 3) )
#     everyone = GetNonCharacterFriendsSelector( AllAliveUnits@DSLSelectors+0x20 )
#
#     Execute(   DSLBehaviors.If( DSLTriggers.ActorHasTriggeredAbility(Caster@0x48, 0x3ec),
#                                 DSLBehaviors.TriggerAbility(Caster@0x48, 0x3ec, actor: null,
#                                     caster: null, target: null, unitFeetTiles: null,
#                                     selectionType: 3, ignoreUnitHavingAbility: 0),
#                                 else: null )
#              + DSLBehaviors.AddStatOverrideEffect(targets, 0x3f4, statType: 0, amount,
#                                                   turns: Nullable<int> VIDE, flag: 1)
#              + DSLBehaviors.PerformAIAction(targets, asGroup: 0, resetTurnFlags: 1)
#              + DSLBehaviors.RemoveEffect(everyone, Nullable<EffectType>(0x3f4),
#                                          replaceableEffectType: null) )
#
# `...$$GetNonCharacterFriendsSelector(units)` (mirror 1:1, DEUX appels avec des sources DIFFERENTES) :
#
#     DSLSelectors.Friends(of: Caster@DSLSelectors+0x30, entities: units, selType: 3)
#       op_Subtraction DSLSelectors.HeroUnits(units, selType: 3)
#
# QUALIFICATION D'ENUM -- les deux litteraux de ce corps vivent dans des enums DIFFERENTS, et leurs
# ordinaux se ressemblent :
#   * `0x3ec` = 1004 = `TriggeredAbilityType.RelentlessMarch` (le passif du MEME porteur, deja porte
#     dans `operations/triggers/loki/relentless_march.py`). Dans `ActiveAbilityType`, 1004 nomme
#     `MortisRound` -- une ability d'`ultraEliminatorSgt`, sans aucun rapport.
#   * `0x3f4` = 1012 = `EffectType.AdaptiveStrategy_DmgOverride`. Dans `ActiveAbilityType`, 1012
#     nomme `PrecisionShot_Aim` ; dans `TriggeredAbilityType`, `HeavyWeaponExtraDamage`.
#   * `statType: 0` = `StatType.ATTACK` (LU : c'est le 4e parametre de la factory, transcrit dans
#     `AddStatOverrideEffectBehaviour+0x64`).
#
# CE QUE CE PORT FERME. `relentless_march.py` section 3 nommait un residu : sa branche
# `triggerType == EventTriggerType.Custom` (0x20) etait PORTEE mais SANS APPELANT cote port, parce
# que 1005 n'etait pas dans `ABILITY_CLASSES`. Le noeud (1) ci-dessus EST cet appelant --
# `IdunBattle.Operations.TriggerTriggeredAbilityOperation$$TriggerAbility` appelle
# `ITriggeredAbility.ExecuteBy(ability, &abilityState, entities, 0x20)` avec le `0x20` EN DUR. D'ou
# l'entree `TRIGGERED_ABILITY_BEHAVIOURS[RelentlessMarch]` plus bas.


ADAPTIVE_STRATEGY_ID = "AdaptiveStrategy"
#: `AddStatOverrideEffect(targets, 0x3f4, ...)` -- `EffectType`, PAS `TriggeredAbilityType`.
ADAPTIVE_STRATEGY_OVERRIDE = int(EffectType.AdaptiveStrategy_DmgOverride)       # 0x3f4 = 1012
#: `ActorHasTriggeredAbility(Caster, 0x3ec)` / `TriggerAbility(Caster, 0x3ec, ...)` --
#: `TriggeredAbilityType`, PAS `ActiveAbilityType` (ou 1004 nomme `MortisRound`).
ADAPTIVE_STRATEGY_RETRIGGER = int(TriggeredAbilityType.RelentlessMarch)         # 0x3ec = 1004
#: `AActiveAbility$$MinMaxDamage` : `GetVariableForLevel(cfg@+0x60, 0xc)` / `(..., 0xd)`.
ADAPTIVE_STRATEGY_MIN = AbilityVariableType.minDmg.name                        # 0xc = 12
ADAPTIVE_STRATEGY_MAX = AbilityVariableType.maxDmg.name                        # 0xd = 13
#: le 7e argument de la factory (`AddStatOverrideEffectBehaviour+0x78`), LITTERAL `1`. Le decompile
#: nomme ce parametre `isHidden` ; le port a trace son usage jusqu'a `SetOverride(value, modifiable)`
#: (cf. `behaviours/stats.py::AddStatOverrideEffect`) -- on transcrit le littéral, pas le nom.
ADAPTIVE_STRATEGY_OVERRIDE_FLAG = True
#: `PerformAIAction(targets, asGroup: 0, resetTurnFlags: 1)` -- les DEUX booleens sont LUS.
ADAPTIVE_STRATEGY_AS_GROUP = False
ADAPTIVE_STRATEGY_RESET_TURN_FLAGS = True


def non_character_friends_selector(units: TargetsSelector) -> TargetsSelector:
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.AdaptiveStrategyAbility$$
    GetNonCharacterFriendsSelector(units)` -- MIRROR 1:1, et c'est une FACTORY de composition (le
    natif n'alloue aucun selecteur dedie) :

        Friends(of: Owner@DSLSelectors+0x30, entities: units, selType: 3)
          op_Subtraction HeroUnits(units, selType: 3)

    « Non-Character » du tooltip == « pas le trait `Hero` » : `DSLSelectors$$HeroUnits(src, selType)`
    DELEGUE litteralement a `UnitsWithTrait(src, 0x10 = UnitTrait.Hero, selType)` (d'ou le helper
    `hero_units` deja porte, et sa docstring, qui cite CE call-site).

    ⚠ LE MEME arbre `units` est repris DES DEUX COTES de la soustraction, comme le natif reprend le
    meme argument -- il est donc evalue deux fois, exactement comme lui. C'est la MEME forme que la
    branche `Custom` de `relentless_march_targets`, ce qui en dit le sens : rejoue par
    `AdaptiveStrategy`, `RelentlessMarch` ne beneficie qu'aux allies NON-Character.

    Le referent du `Friends` est LU (`DSLSelectors+0x30` = Owner) et non suppose : pour une ACTIVE,
    `entities_from_state(state, caster_id, ...)` pose `owner == caster`, d'ou `Caster()`.

    `selType = 3` (`UnitSelectionType.OnlyAliveAndTargetable`) : le port n'honore que le volet ALIVE
    (meme residu nomme que `relentless_march.py`)."""
    return Sub(Friends(units, Caster()), hero_units(units))


def adaptive_strategy_targets() -> TargetsSelector:
    """Le selecteur du (2) et du (3) : `GetNonCharacterFriendsSelector(AdjacentUnits(Caster@0x48))`.

    `DSLSelectors$$AdjacentUnits(origin, unique, selType)` = `Units(AdjacentTiles(origin), unique,
    selType) op_Subtraction origin` -- l'origine est EXCLUE de sa propre selection, et ce selecteur
    ne filtre AUCUNE equipe (c'est le `Friends` au-dessus qui le fait). `unique = 1` est sans effet
    observable (une unite = une position)."""
    return non_character_friends_selector(AdjacentUnits(Caster()))


def adaptive_strategy_cleanup_targets() -> TargetsSelector:
    """Le selecteur du (4) : `GetNonCharacterFriendsSelector(AllAliveUnits@DSLSelectors+0x20)`.

    ⚠ CE N'EST PAS LE SELECTEUR DU (2), et l'ecart est OBSERVABLE : le `RemoveEffect` balaie TOUS les
    allies non-Character VIVANTS du plateau, pas les seuls adjacents. Un allie non-Character qui
    porterait encore un `AdaptiveStrategy_DmgOverride` d'un cast anterieur -- ou qui a quitte
    l'adjacence entre la pose et le retrait, l'action IA du (3) pouvant le DEPLACER -- est nettoye
    par ce noeud et ne l'aurait pas ete par celui du (2). Recopier le selecteur du (2) ici aurait
    laisse un override colle, c'est-a-dire une unite dont l'Attack reste ecrasee pour le reste de la
    bataille.

    `AllAliveUnits` = le champ PARTAGE `DSLSelectors+0x20` (`EntityPool.AliveUnits`), surtout pas
    `AllUnits` (`EntityPool.AllUnits`, morts inclus) : les deux corps natifs ne different que par le
    litteral d'`EntityPool`, et le port distingue les deux primitives depuis #514."""
    return non_character_friends_selector(AllAliveUnits())


def adaptive_strategy_tree(amount: AAmountFormula) -> Seq:
    """`...AdaptiveStrategyAbility$$ExecuteBehaviour` -- MIRROR 1:1 de la chaine `op_Addition`, dans
    l'ordre du decompile (`ifB + statB + aiB + remB`) :

        If( ActorHasTriggeredAbility(Caster, 0x3ec), TriggerAbility(Caster, 0x3ec) )
      + AddStatOverrideEffect(targets, 0x3f4, ATTACK, amount, turns: VIDE, flag: 1)
      + PerformAIAction(targets, asGroup: 0, resetTurnFlags: 1)
      + RemoveEffect(everyone, 0x3f4)

    ⚠ L'ORDRE EST LOAD-BEARING, et il ne se devine pas : le (4) retire l'override que le (2) vient de
    poser, APRES que le (3) a fait agir les unites. C'est un buff STRICTEMENT TRANSITOIRE -- le meme
    patron net-zero que `TheQuickening` (0x510) et `GalvanicField` (1242), sauf que l'action
    intercalee n'est pas une attaque libre mais un TOUR D'IA COMPLET.

    ⚠ `turns` = un `Nullable<int>` VIDE (le decompile passe 8 octets a zero, pas un `Direct(n)`) ->
    `duration_rounds=None, duration_turns=None` : aucun override de duree, la duree vient de
    `DefaultAmountOfRounds` -- ce que fait deja `_resolve_duration`. Ne PAS ecrire `duration_turns=1`
    ici : le (4) est le retrait REEL, une duree inventee le doublerait.

    `amount` est le noeud MONTANT, PARESSEUX -- pas une constante : la feuille le `Calculate` UNE FOIS
    PAR UNITE, avec le sujet lie (`param_3[4] = current` du natif). Un `RandomAmount` y consomme donc
    UN tirage PAR CIBLE, exactement comme le natif. C'est pourquoi ce port ne resout pas le montant
    en amont (contraste `relentless_march`, dont le natif appelle `GetVariableForLevel` puis
    `DSLFormulas$$Direct` AVANT de batir l'arbre).

    ⚠ La feuille du (3) est `PerformAIAction`, PAS `PerformAIAttack` : le natif fait agir chaque
    unite par une passe de DECISION complete (`AiControl$$ExecuteFor(unit)`), qui peut la faire se
    DEPLACER, caster une ability, ou ne rien faire -- « if they attack » du tooltip est une
    CONDITION, pas une garantie. `resetTurnFlags = 1` : les flags de tour sont sauvegardes, effaces,
    puis restaures -> l'unite agit meme si elle avait deja fini son tour, et cette action
    supplementaire ne le consomme pas."""
    targets = adaptive_strategy_targets()
    # `op_add` chaine A GAUCHE, comme le decompile : `((ifB + statB) + aiB) + remB`. `Seq` est
    # binaire cote port, exactement comme `CombinedBehaviour` (left@0x50, right@0x58) cote natif.
    tree = op_add(IfBehaviour(ActorHasTriggeredAbility(Caster(), ADAPTIVE_STRATEGY_RETRIGGER),
                              TriggerAbility(Caster(), ADAPTIVE_STRATEGY_RETRIGGER)),
                  AddStatOverrideEffect(targets, ADAPTIVE_STRATEGY_OVERRIDE, int(StatType.ATTACK),
                                        amount,
                                        name=EffectType.AdaptiveStrategy_DmgOverride.name,
                                        duration_rounds=None, duration_turns=None,
                                        is_modifiable=ADAPTIVE_STRATEGY_OVERRIDE_FLAG))
    tree = op_add(tree, PerformAIAction(targets, as_group=ADAPTIVE_STRATEGY_AS_GROUP,
                                        reset_turn_flags=ADAPTIVE_STRATEGY_RESET_TURN_FLAGS))
    return op_add(tree, RemoveEffect(ADAPTIVE_STRATEGY_OVERRIDE,
                                     adaptive_strategy_cleanup_targets()))


def _relentless_march_custom(state: "State", unit_id: int, entities, ectx):
    """Entree de `TRIGGERED_ABILITY_BEHAVIOURS[RelentlessMarch]` -- le bout de chaine du noeud (1).

    Le natif : `TriggerAbilityBehaviour$$Execute` resout ses cibles puis appelle, par unite,
    `IdunBattle.Operations.TriggerTriggeredAbilityOperation$$TriggerAbility`, dont le corps fait
    `ITriggeredAbility.ExecuteBy(ability, &abilityState, entities, 0x20)` -- le `0x20` =
    `EventTriggerType.Custom` est EN DUR dans l'Operation, ce n'est pas un parametre du DSL. C'est
    donc la branche `Custom` de `...RelentlessMarchAbility$$CreateBehaviour` qui s'execute, celle qui
    SOUSTRAIT les `HeroUnits` -- et c'est ce que `relentless_march.py` section 3 annonce depuis #328
    comme « portee, sans appelant cote port ». Ce module EST l'appelant.

    `unit_id` = l'unite DECLENCHEE (ici le caster de 1005, seule cible du `TriggerAbility`) : c'est
    elle qui devient l'OWNER de la triggered, exactement comme `ExecuteBy` prend l'`abilityState` de
    l'entite iteree. On re-materialise donc `entities_from_state(state, unit_id, None)` plutot que de
    reutiliser l'`entities` du cast -- le natif reconstruit lui aussi son `AbilityEntities` depuis
    les quatre selecteurs du `TriggerAbilityBehaviour`, qui sont tous NULS ici (`actor`, `caster`,
    `target`, `unitFeetTiles` = 0 au call-site).

    Le gate « l'unite porte-t-elle 1004 » est deja applique EN AMONT, deux fois et par deux artefacts
    natifs distincts : le predicat `ActorHasTriggeredAbility` du `If` (noeud (1)) et le
    `GetAbilityState` de l'Operation (`_unit_has_triggered_ability`, feuille `TriggerAbility`)."""
    amount = rm_hp_to_repair(state, int(unit_id))
    ents = entities_from_state(state, int(unit_id), None)
    rm_behaviour_tree(amount, int(EventTriggerType.Custom)).execute(ents, ectx)
    return {"passive": "RelentlessMarch", "owner": int(unit_id), "amount": int(amount),
            "trigger_type": int(EventTriggerType.Custom)}


TRIGGERED_ABILITY_BEHAVIOURS[ADAPTIVE_STRATEGY_RETRIGGER] = _relentless_march_custom


class AdaptiveStrategyAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.AdaptiveStrategyAbility$$ExecuteBehaviour`
    (id 1005, `necroWarden` « Makhotep », Necrons, HERO, dans le pool rank 17) -- cf. le bloc
    d'en-tete de section pour la transcription du decompile et les QUATRE mecaniques.

    Cast UNIT-TARGET sur un ALLIE ADJACENT NON-HERO. L'arbre, lui, ne lit PAS la cible : il part du
    CASTER (`AdjacentUnits(Caster@DSLSelectors+0x48)`). La cible ne sert qu'au GATE -- ce qui est
    coherent avec `isSelfCasting = 1` (cf. `TARGETING_OPTIONS` ci-dessous), puisque
    `IdunBattle.Core.Services.TargetingQuery$$GetActualTarget` rabat alors le role `target` sur le
    CASTER avant de construire l'`AbilityEntities`.

    ⚠ CONFRONTABILITE, et c'est une CONSEQUENCE DU GATE, pas un defaut de montage : le refus
    dynamique est `HasTrait(target, Hero) -> TargetMatchesDynamicRule`, et en bataille de lineup
    TOUTE unite deployee porte `Hero`. Le cast n'a donc AUCUNE cible legale tant qu'il n'y a pas un
    allie NON-Hero adjacent -- un SUMMON, un `Object`, une unite greffee sans le trait. C'est
    exactement la divergence que `_dynamic_rule_adaptive_strategy` (`abilities/targeting.py`)
    documente et mesure (`C1_02`/seed 28704 : natif `targetReason = TargetMatchesDynamicRule` +
    `UnitFlag.NoActionAvailable` POSE). La regle vit desormais SUR CETTE CLASSE (contrat de
    disjonction), et `DYNAMIC_TARGET_RULE_UNPORTED` ne la porte plus.

    Renvoie {ability, caster, target, retriggered, overrides, actions, cleaned, dsl}."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.AdaptiveStrategy)        # 0x3ed = 1005
    ABILITY_ID = ADAPTIVE_STRATEGY_ID

    # GATE DE CIBLE (#115). `IdunBattleLogic.Entities.Abilities.Active.Loki.AdaptiveStrategyAbility$$.ctor` :
    #     range = <TargetingRange statics+0x30> = RANGE_ADJACENT        (copie de 0x18 octets)
    #     TargetingOptions..ctor(&opts, isSelfCasting=1, &range, forceMeleeTarget=1,
    #                            rules=0x402, getDynamicInvalidCasterReason=0,
    #                            getDynamicInvalidTargetReason=0)
    #     AActiveAbility..ctor(this, &opts, 2)                          # AbilityAttackType.Others
    # FORME DIRECTE a 7 arguments (surcharge `(this, isSelfCasting, range, forceMeleeTarget, rules,
    # getDynamicInvalidCasterReason, getDynamicInvalidTargetReason)`, tranchee par l'ADRESSE du call)
    # -> le litteral EST le masque effectif, aucun preset, aucun `|` de flags additionnels.
    #   0x402 = TargetMatchesDynamicRule (1<<1) | TargetIsFriendly (1<<10)  -- somme EXACTE, 0 residu
    #   forceMeleeTarget = 1 = RangedBool.False (l'enum natif est INVERSE)
    # ⚠ Les DEUX derniers arguments du ctor sont NULS : le delegue de regle dynamique n'est PAS pose
    # a `options+0x38` par le ctor. C'est le slot VIRTUEL `GetDynamicInvalidTargetReason` de la
    # sous-classe qui porte la regle -- d'ou la surcharge de methode ci-dessous, et non une entree de
    # table. Le masque etait DEJA lu et vivait dans `TARGETING_OPTIONS_UNPORTED` ; il a ete RE-LU au
    # decompile avant migration et est bit-identique (contrat de disjonction, #577).
    TARGETING_OPTIONS = TargetingOptions(rules=(
          TR.TargetMatchesDynamicRule
        | TR.TargetIsFriendly
    ), self_cast=True, range=RANGE_ADJACENT, force_melee_target=RANGED_BOOL_FALSE)

    def get_dynamic_invalid_target_reason(self, state: "State", caster_id: int,
                                          target_id: Optional[int]) -> int:
        """`...AdaptiveStrategyAbility$$GetDynamicInvalidTargetReason` -- le corps natif tient en une
        ligne (`return HasTrait(target, 0x10 = UnitTrait.Hero) ? 2 : 0`). Il n'a QU'UN mirror, celui
        d'`abilities/targeting.py`, que cette surcharge APPELLE : #577 deplace la SOURCE (table ->
        classe, contrat de disjonction), jamais la valeur, et surtout ne la duplique pas."""
        return _dynamic_rule_adaptive_strategy(state, caster_id, target_id)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        e = state.get_entity(caster_id)
        sc = e.get_component(StatsComponent) if e is not None else None
        ctx = getattr(sc, "ctx", None) if sc is not None else None
        lvl = getattr(ctx, "active_ability_level", None) if ctx is not None else None
        mult = int(getattr(ctx, "ability_variables_multiplier", 100) or 100) if ctx is not None else 100
        # `AActiveAbility$$MinMaxDamage(this, abilityState, isPrediction: FALSE)` =
        # `DSLFormulas.RandomAmount( GetVariableForLevel(cfg@+0x60, 0xc = minDmg),
        #                            GetVariableForLevel(cfg@+0x60, 0xd = maxDmg) )`.
        # Les DEUX bornes sont rarity-scale (`variablesAffectedByRarityBonus` = [minDmg, maxDmg]),
        # ce que `ability_var` gate sur cette meme liste. Le RNG est un CHAMP du noeud cote natif
        # (`RandomAmount+0x20`, pose par la factory depuis `DSLFactory+0x18`) -> il se passe au
        # CONSTRUCTEUR, jamais par le contexte. `state.rng` absent -> le noeud rend sa borne MIN
        # (degradation deterministe deja documentee sur `RandomAmount`, aucun tirage consomme).
        mn = int(ability_var(ADAPTIVE_STRATEGY_ID, ADAPTIVE_STRATEGY_MIN, lvl,
                             multiplier_pct=mult) or 0)
        mx = int(ability_var(ADAPTIVE_STRATEGY_ID, ADAPTIVE_STRATEGY_MAX, lvl,
                             multiplier_pct=mult) or 0)
        amount = RandomAmount(Const(mn), Const(mx), rng=state.rng)
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, caster_id, target_id)
        adaptive_strategy_tree(amount).execute(entities, ectx)
        retriggered = next((p for n, p in ectx.emitted if n == "TriggerAbility"), None)
        overrides = [{"unit": p["unit"], "amount": p["amount"]}
                     for n, p in ectx.emitted if n == "AddStatOverrideEffect"]
        actions = next((p for n, p in ectx.emitted if n == "PerformAIAction"), None)
        cleaned = [{"unit": p.get("target"), "removed": p.get("removed")}
                   for n, p in ectx.emitted if n == "RemoveEffect"]
        return {"ability": ADAPTIVE_STRATEGY_ID, "caster": caster_id, "target": target_id,
                "min": mn, "max": mx, "retriggered": retriggered, "overrides": overrides,
                "actions": actions, "cleaned": cleaned, "dsl": True}


def harbinger_pool_selector(range_val: int):
    """Pool des cibles ADDITIONNELLES (mirror `HarbingerOfDestructionAbility$$IdunBattleLogic.Entities.Abilities.Active.Loki.HarbingerOfDestructionAbility$$GetEnemiesInRange`) :

        SurroundingTiles(casterTile@0x168, includeCenter=0, range)   # DISQUE dist<=range du caster, centre exclu
        |> Units(., 1, 3)                                            # unites DEBOUT dessus
        |> Enemies(caster@0x160, ., 3)                              # ennemis du caster
        |> op_Subtraction(., target@arg)                           # MOINS la cible principale
        |> Unobscured(caster@0x160, .)                             # ligne de vue depuis le caster (terrain)
        |> Damageable(.)                                           # vivants ciblables (PV>0)

    Le triplet `Enemies(Units(SurroundingTiles(tile, incl=0, range)))` == `IdunBattleLogic.Entities.DSLSelectors$$SurroundingEnemies(tile,
    range)` (DECOMPILE : `SurroundingEnemies` = `Enemies(Units(SurroundingTiles(tile, incl=1,
    range) - Tiles(tile)))`, et `SurroundingTiles(incl=0)` == `SurroundingTiles(incl=1) - Tiles(tile)` par
    definition -> IDENTITE prouvee). D'ou le port `SurroundingEnemies(CasterTile(), Const(range))` (disque
    dist<=range, centre=caster exclu, team!=caster ; memes flags Units 1,3 inertes offline). Puis `Sub(.,
    Target())`, `Unobscured(., Caster())`, `Damageable(.)` — mirror 1:1 de l'ordre natif."""
    # #585-r1 : `...HarbingerOfDestructionAbility$$GetEnemiesInRange` n'appelle PAS `SurroundingEnemies` --
    # il ecrit `Units(gs, SurroundingTiles(gs@0x50, incl: 0, range), unique: 1, 3)` puis
    # `Enemies(gs, gs@0x48, ., 3)`. Les DEUX etages portent `3` ; le collapse du port en un seul
    # `SurroundingEnemies` applique le meme predicat une fois (il est PUR, donc idempotent).
    return Damageable(
        Unobscured(
            Sub(SurroundingEnemies(CasterTile(), Const(range_val), selection_type=SELECTION),
                Target()),
            Caster()))


def harbinger_of_destruction_tree(additional_units: list,
                                  include_main: bool = True) -> AttackWithAttackDamage:
    """UNE feuille `AttackWithAttackDamage` sur le selecteur COMBINE `op_Addition(Target(), <additional>)`
    (mirror `HarbingerOfDestructionAbility$$IdunBattleLogic.Entities.Abilities.Active.Loki.HarbingerOfDestructionAbility$$ExecuteBehaviour` : UN SEUL `AttackWithAttackDamage`,
    PAS deux volets separes -- CONTRASTE BringerOfDespair). Le natif construit :

        targets = If( AreEqual(caster@0x160, target@0x178),
                      GetAdditionalTargets,                             # then : caster==target (degenere)
                      op_Addition(target@0x178, GetAdditionalTargets) ) # else : cible + additionnels
        AttackWithAttackDamage(caster@0x160, targets, MinMaxDamage, Direct(GetDamageProfile(0)),
                               Direct(GetNumberConstant(0x2f)=nrOfHits))               # Execute (PAS ExecuteAtomic)

    `additional_units` = les cibles additionnelles DEJA pickees (collapse du `PickRandomly` natif, cf.
    `execute_behaviour`). `include_main` = la branche `If(AreEqual)` : True (else, target != caster =
    reachable) -> `Union(Target(), UnitSet(additional))` ; False (then, target == caster degenere) ->
    `UnitSet(additional)` seul (le natif n'ajoute pas la cible). La feuille `multi=True` resout le selecteur,
    `OrderBy` par id (== l'`OrderBy` de `IdunBattle.Entities.Behaviours.AttackBehaviour$$Execute`) puis attaque CHAQUE cible 1 coup
    dans l'ordre id -> main et additionnels sont attaques dans UNE passe id-triee UNIQUE (mirror du leaf natif
    unique).

    - **MinMaxDamage(minDmg/maxDmg)** = bornes config brutes (aucun override `GetAttackDamage`), profil
      `GetDamageProfile(config, 0)` = "DirectDamage" (PiercingRatio 100 -> pierce 100), `GetNumberConstant(
      0x2f)` = nrOfHits = 1. `attackRangeType=Ranged` -> `is_melee=False`.
    - **native_factory = "attack"** (defaut, 2 tirages/coup a cc=0) : l'ExecuteBehaviour appelle
      `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage` (VERIFIE par les CALLEES de IdunBattleLogic.Entities.Abilities.Active.Loki.HarbingerOfDestructionAbility$$ExecuteBehaviour, PAS
      `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAbilityDamage` -- cf. rngcrit-1202/tip #2). "DirectDamage" est le NOM DU PROFIL,
      PAS l'effet direct-damage (montant fixe) -> la feuille route par `execute_ability_attack` (crit/block)."""
    add_sel = UnitSet(additional_units)
    target_sel = Union(Target(), add_sel) if include_main else add_sel
    return AttackWithAttackDamage(target_sel, "HarbingerOfDestruction", "DirectDamage",
                                  is_melee=False, multi=True)                # MinMaxDamage/DirectDamage/0x2f=1


class HarbingerOfDestructionAbility(ActiveAbility):
    """`HarbingerOfDestructionAbility$$IdunBattleLogic.Entities.Abilities.Active.Loki.HarbingerOfDestructionAbility$$ExecuteBehaviour` (id 1008, `necroPlasmancer`, namespace
    natif `Abilities.Active.Loki`).

    Attaque la CIBLE + N-1 ennemis ALEATOIRES dans un DISQUE rayon-2 du CASTER (non obscurcis, damageable,
    hors cible), 1 coup MinMaxDamage profil DirectDamage (pierce 100) chacun, dans UNE passe id-triee unique.
    Mirror 1:1 des 4 fonctions natives (VA gqfc5mff6c) :

      - `IdunBattleLogic.Entities.Abilities.Active.Loki.HarbingerOfDestructionAbility$$ExecuteBehaviour` : UN `AttackWithAttackDamage(caster, If(AreEqual(caster,target),
        additional, Target()+additional), MinMaxDamage, Direct(profile 0), Direct(nrOfHits 0x2f))`.
      - `IdunBattleLogic.Entities.Abilities.Active.Loki.HarbingerOfDestructionAbility$$GetAdditionalTargets` : count = `If(AreEqual(caster,target), Get(N), Get(N-1))` avec
        N = `GetVariableForLevel(config, 0x9a)` = `nrOfUnits`[level] ; range = `GetNumberConstant(0x16)` =
        `range` = 2 ; -> `GetEnemiesInRange(count, range, target, pickRandom=1)`.
      - `IdunBattleLogic.Entities.Abilities.Active.Loki.HarbingerOfDestructionAbility$$GetEnemiesInRange` : `PickRandomly(Damageable(Unobscured(caster, SurroundingEnemies(
        casterTile, range) - target)), count)` (pickRandom=1 -> PickRandomly ; =0 -> First, chemin preview).
      - `IdunBattleLogic.Entities.Abilities.Active.Loki.HarbingerOfDestructionAbility$$GetTargetAmount` : accessoire preview (meme `If(AreEqual, Get(N), Get(N-1))`).

    STRUCTURE = template splash `loki/splash.py`, adaptee de BringerOfDespair (`blacklegion.py`, caster-ancre
    + Sub(Target) + PickRandomly) SAUF que : (1) rayon-2 DISQUE (`SurroundingEnemies`, PAS `AdjacentUnits`
    ring-1) ; (2) filtre `Unobscured` ; (3) N-1 picks (up to 2, `nrOfUnits`-1) et non 1 ; (4) UN SEUL leaf
    combine (main+additionnels attaques ENSEMBLE id-triees), PAS deux volets.

    COLLAPSE du `PickRandomly` (doctrine slice-18/19 + Fragstorm/BringerOfDespair `pick_n`) : le `DslContext`
    des selecteurs ne porte PAS `state.rng` -> on resout le pool (selecteur DSL PUR `harbinger_pool_selector`),
    on id-trie, puis on FOLDE le `PickRandomly(pool, N-1)` via `_pick_randomly_n(state.rng)` (== BringerOfDespair)
    AVANT d'attaquer -> l'ordre de conso `state.rng` (pick D'ABORD, puis 1 coup/cible id-triee = 2 tirages/coup)
    mirror le natif (PickRandomly evalue a la RESOLUTION du selecteur, avant tout coup). Les cibles pickees
    alimentent `harbinger_of_destruction_tree` via `UnitSet` (vehicule de collapse).

    #130 (GAP #215 CLOS sur la CONSO) : `_pick_randomly_n` consomme `min(len(pool), N-1)` tirages -- MEME
    quand le pool tient dans `N-1` (le natif n'a aucun court-circuit ; cf. `_pick_randomly_n`). Le pick
    precede les coups -> sans lui TOUT le flux rng aval etait decale. Le SET, lui, reste le pool entier
    quand `len(pool) <= N-1` (== natif).
    R28-1 (2026-07-27) : l'ORDRE du pool est desormais celui du natif -- `SurroundingEnemies` enumere par
    TUILE dans l'ordre de `TileQuery$$IterateSurroundingTiles` (triple boucle CUBE), et le pick consomme
    cet ordre TEL QUEL (le `sorted(key=id)` pre-tirage qui vivait ici n'avait aucun homologue natif :
    `PickRandomAmountSelector$$Select` ne trie jamais son `candidates`). Observable des que
    `len(pool) > N-1` : l'ENSEMBLE pique change.

    Renvoie {ability, caster, target, main_attack, splash, dsl}. Termine le tour (1008 hors des frozensets
    base.py -> flags par defaut). `native_factory="attack"` (defaut) = 2 tirages/coup a cc=0 -> bit-exact BY
    CONSTRUCTION vs une sequence directe `execute_ability_attack` (memes bornes/hits/profil, cibles id-triees,
    meme `state.rng`)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.HarbingerOfDestruction)  # 1008
    ABILITY_ID = "HarbingerOfDestruction"

    # GATE DE CIBLE (#115). `IdunBattleLogic.Entities.Abilities.Active.Loki.HarbingerOfDestructionAbility$$.ctor`
    # n'appelle AUCUN `TargetingOptions..ctor` : il COPIE les 0x40 octets d'un PRESET STATIQUE de
    # `IdunBattle.Core.Services.TargetingOptions` (statics `+0x3c0`, pose par
    # `IdunBattle.Core.Services.TargetingOptions$$.cctor`), puis
    # `AActiveAbility..ctor(this, &opts, 0, 0)`. Le masque effectif est donc le champ `Rules` du preset,
    # a `preset+0x28` = statics `+0x3e8` -> `0x200000000000004` (litteral LU dans le `.cctor`).
    # Decomposition (`IdunBattle.Core.Services.TargetingRule`) :
    #     0x4                 CasterMatchesDynamicRule  -> volet CASTER (regle-delegue), NON PORTE
    #     0x200000000000000   TargetIsCasterOrEnemy (`TargetingOptions$$get_IsCasterOrEnemyTargeting`
    #                         = `(rules >> 0x39) & 1`) -> PORTE : la cible doit etre le CASTER LUI-MEME
    #                         ou un ennemi attaquable. C'est ce bit qui explique la branche
    #                         `If(AreEqual(caster, target), ...)` de l'ExecuteBehaviour : le natif ACCEPTE
    #                         `target == caster` pour cette ability (d'ou `include_main=False`).
    # PORTEE (#241) : preset `TargetingOptions` statique `+0x3c0` -> `TargetingRange`
    # statique `+0x18` (`useRangeFromConfig` -> `HarbingerOfDestruction.constants.range` = 2)
    # + `forceMeleeTarget = False`.
    TARGETING_OPTIONS = TargetingOptions(rules=(
          TR.CasterMatchesDynamicRule
        | TR.TargetIsCasterOrEnemy
    ), range=RANGE_FROM_CONFIG, force_melee_target=RANGED_BOOL_FALSE)

    def _params(self, state: "State", caster_id: int) -> tuple:
        """`(N, range)` lus du gameconfig au niveau du caster (mirror `GetVariableForLevel(config, 0x9a)` =
        `nrOfUnits`[level] et `GetNumberConstant(config, 0x16)` = `range`). N NON scale rarete (`nrOfUnits`
        hors `variablesAffectedByRarityBonus`). Cle config `nrOfUnits ` (espace final = quirk gameconfig)
        avec fallback sans espace. Defauts surs si absent (N>=1, range>=1)."""
        e = state.get_entity(caster_id)
        sc = e.get_component(StatsComponent) if e is not None else None
        level = getattr(sc.ctx, "active_ability_level", 0) if sc is not None else 0
        n = (ability_var(self.ABILITY_ID, "nrOfUnits ", level)
             or ability_var(self.ABILITY_ID, "nrOfUnits", level) or 1)
        rng_range = ability_var(self.ABILITY_ID, "range", is_constant=True) or 1
        return int(n), int(rng_range)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        entities = entities_from_state(state, caster_id, target_id)
        n_total, range_val = self._params(state, caster_id)
        # count = If(AreEqual(caster,target), Get(N), Get(N-1)) : la cible occupe 1 des N slots quand
        # target != caster (cas reachable d'une ability ennemi-ciblee) -> N-1 picks + la cible ; sinon N.
        same = (int(target_id) == int(caster_id))
        n_pick = max(0, n_total if same else n_total - 1)
        # pool (selecteur DSL PUR) dans l'ORDRE SOURCE -> PickRandomly(N-1) folde. R28-1 : le natif
        # `PickRandomAmountSelector$$Select` fait `source.Select(entities).ToList()` et tire par
        # `ElementAt(idx)` SANS aucun tri prealable -- l'id-tri qui etait ici n'avait pas d'homologue
        # natif et decidait QUI etait pique des que |pool| > N-1. L'ordre source vient desormais de
        # `SurroundingEnemies` = enumeration CUBE d'`IterateSurroundingTiles` (cf. `_tile_enum_rank`).
        pool = [u for u in harbinger_pool_selector(range_val).evaluate(entities)
                if isinstance(u, dict) and u.get("id") is not None]
        picked = _pick_randomly_n(state, pool, n_pick)          # ordre source == natif ; conso exacte (#130)
        # additionnels != cible (le pool a deja soustrait Target() ; garde-fou par securite)
        additional = [u for u in picked if u.get("id") != target_id]
        ectx = ExecutionContext(state=state, rng=state.rng)
        # branche If(AreEqual) : include_main=False si target==caster (degenere, non reachable pour une
        # ability ennemi-ciblee), sinon Union(Target(), additionnels).
        harbinger_of_destruction_tree(additional, include_main=not same).execute(entities, ectx)
        atks = [p for n, p in ectx.emitted if n == "AttackWithAttackDamage"]
        main = next((p["attack"] for p in atks if p.get("target") == target_id), None)
        splash = [{"target": p["target"], "attack": p["attack"]}
                  for p in atks if p.get("target") != target_id]  # cibles additionnelles != cible principale
        return {"ability": "HarbingerOfDestruction", "caster": caster_id, "target": target_id,
                "main_attack": main, "splash": splash, "dsl": True}


# =================== ResurrectionOrb (Anuphet `necroOverlord`, actif 1009) — #116 ===================
#
# Indices de config (`AbilityConfiguration.Get*`) lus au decompile de
# `IdunBattleLogic.Entities.Abilities.Active.Loki.ResurrectionOrbAbility$$ExecuteBehaviour` :
RESURRECTION_ORB_CONST_UNIT_ID = 0x00     # GetStringConstant(0)  -> "unitId"     = necroSmnWarrior
RESURRECTION_ORB_CONST_MAX_SUMMONS = AbilityConstantType.maxSummons  # GetNumberConstant(0x3c) -> "maxSummons" (== behaviours.py)
RESURRECTION_ORB_CONFIG_ID = "ResurrectionOrb"


def resurrection_orb_max_summons_const() -> int:
    """`IdunBattle.Configuration.AbilityConfiguration$$GetNumberConstant(config, 0x3c)` =
    `constants.maxSummons` du gameconfig (= 5). Lu de la CONFIG, jamais recopie : c'est la seule voie
    qui reste juste quand l'equilibrage bouge.

    ⚠ DRIFT DE BUILD, mesure le 2026-07-30 : sur `gqfc5mff6c` le cap etait un `Direct(6)` LITTERAL, et
    le port l'avait fige a 6 (`RESURRECTION_ORB_MAX_SUMMONS = 6`). Sur `rnca9r7q6c`,
    `$$GetMaxSummonsFormula` appelle `GetNumberConstant(this+0x60, 0x3c)` puis `Direct(<valeur lue>)`
    — le cap est passe LITTERAL -> CONFIG, et vaut 5. La constante figee etait donc devenue fausse."""
    import gameconfig as _GC                       # lazy : pas de lecture gameconfig a l'import
    c = (_GC.ability(RESURRECTION_ORB_CONFIG_ID) or {}).get("constants") or {}
    return int(c.get("maxSummons") or 0)


def resurrection_orb_possible_resurrect_targets():
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.ResurrectionOrbAbility$$GetPossibleResurrectTargets`
    — MIRROR 1:1 du decompile `rnca9r7q6c` :

        Filter( Friends(AllDeadUnits, caster@0x48),
                HasTrait(It@0x68, 0x10) & IsMechanical(It@0x68) )

    = les allies MORTS qui sont a la fois **Hero** et **mecaniques**. Le `&` est
    `IdunBattle.DSL.AbilityTrigger$$op_BitwiseAnd` (-> `TriggerAnd`).

    ⚠ NOMS D'ENUM QUALIFIES : `0x10` = 16 = **UnitTrait.Hero** (surtout pas un EffectType ; et
    `UnitTrait.Resilient` vaut 1009, homonyme de l'ability elle-meme -- piege a ecarter).
    ⚠ `IsMechanical` n'est PAS `HasTrait(LivingMetal)` : c'est
    `HasTrait(5) | HasTrait(1000) | HasTrait(1029)` (cf. `UnitExtensions$$IsMechanical`).

    L'ensemble alimente DEUX consommateurs (xrefs relues) : `$$GetResurrectBehaviour` (la resurrection
    proprement dite, cote COMBAT) et `$$GetNumSummonsFormula` (cote DECISION). Un seul artefact natif,
    un seul port."""
    # #585-r1 -- LE LITTERAL EST `0`, ET C'EST LE CONTRE-EXEMPLE DU RELEVE.
    # `Friends(gs, gs@0x48, AllDeadUnits(gs), 0)` : `UnitSelectionType.Any`. Le reste du corpus
    # releve vaut 3 (`OnlyAliveAndTargetable`) ; ici un 3 recopie aurait vide l'ensemble -- les
    # cibles SONT mortes, et `MatchesUnitSelectionType` teste `IsAlive` pour 1 comme pour 3.
    # C'est un masque FAUX qui a l'air renseigne : la faute exacte que la fiche annoncait.
    return Filter(Friends(AllDeadUnits(), Caster(),
                          selection_type=int(UnitSelectionType.Any)),
                  TriggerAnd(HasTrait(Subject(), int(UnitTrait.Hero)), is_mechanical(Subject())))


def resurrection_orb_possible_spawn_or_resurrect_tiles():
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.ResurrectionOrbAbility$$GetPossibleSpawnOrResurrectTiles`
    — MIRROR 1:1 : `CanAddUnit( AdjacentTiles(casterTile@0x58) )` = les hex adjacents a la tuile du
    caster ou une unite peut etre posee.

    L'ancre est `DSLSelectors+0x58` = **CasterTile**, PAS `+0x48` = Caster (deux slots distincts de
    `DSLSelectors$$InitializeShared`, et le natif choisit +0x58 ici). La difference est INERTE cote
    runner (`ctx.caster_pos` None -> position courante) mais DECISIVE cote decision balayee : c'est
    `ctx.caster_pos` = la tuile candidate qui doit ancrer l'anneau, sinon les six voisins evalues sont
    ceux de la position de DEPART pour toutes les tuiles du sweep."""
    return CanAddUnit(AdjacentTiles(CasterTile()))


def resurrection_orb_max_summons_formula():
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.ResurrectionOrbAbility$$GetMaxSummonsFormula` —
    MIRROR 1:1 du decompile `rnca9r7q6c` (formule V pure, aucun collapse) :

        Min( Sum( Count( Filter(Friends(AllDeadUnits, caster@0x48), IsMechanical(It@0x68)) ),
                  StatAmount(caster@0x48, 0xc = TURNS_STARTED) ),
             Direct(GetNumberConstant(0x3c) = maxSummons) )

    = i2 mot a mot : « summons 1 Necron Warrior **for each round that has started** » (le compteur
    per-unite `UnitComponent.turnsStarted@+0x58` du caster) « + 1 more for each friendly unit with the
    trait Living Metal **that was defeated** in this battle ». L'ordre des operandes du `Sum` est celui
    du natif (`Sum(Count, StatAmount)`).

    ⚠ TROIS ecarts par rapport au port ecrit sur `gqfc5mff6c`, tous relus au decompile du build
    COURANT (le natif a change, pas la lecture) :
      1. `AllDeadUnits` (`AllDefeatedUnitsSelector`) et **pas** `AllDeadOrResurrectedUnits` — deux
         factories natives distinctes ; la seconde ajoute les ressuscites (flag 0xe), qui sont VIVANTS.
      2. `Filter(..., IsMechanical)` et **pas** `UnitsWithTrait(LivingMetal)` — `IsMechanical` couvre
         AUSSI `Mechanical`(5) et `Vehicle`(1029) ; un allie mort `Mechanical` non-`LivingMetal`
         comptait a tort pour zero.
      3. cap = `ConfigConst(maxSummons)` = 5 et **pas** `Direct(6)` (cf.
         `resurrection_orb_max_summons_const`).

    ⚠ NOMS D'ENUM QUALIFIES : `0xc` est un **StatType** (TURNS_STARTED), pas un EffectType."""
    return Min(Sum(Count(Filter(Friends(AllDeadUnits(), Caster()), is_mechanical(Subject()))),
                   StatAmount(Caster(), int(StatType.TURNS_STARTED))),
               Const(resurrection_orb_max_summons_const()))


def resurrection_orb_num_summons_formula():
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.ResurrectionOrbAbility$$GetNumSummonsFormula` —
    MIRROR 1:1 du decompile `rnca9r7q6c` :

        tiles = CanAddUnit(AdjacentTiles(casterTile@0x58))
        amount = If( AmountIsGreaterThanZero(GetPossibleResurrectTargets()),
                     Difference(Count(tiles), formulas+0x20 = Direct(1)),      # une tuile RESERVEE
                     Count(tiles) )
        return Min( GetMaxSummonsFormula(), amount )

    = « autant de Warriors que de hex libres adjacents, MOINS un si un heros mecanique allie mort peut
    etre ressuscite (sa tuile est reservee), le tout plafonne par maxSummons ». `formulas+0x20` est la
    constante partagee `Direct(1)` allouee par `DSLFormulas$$.ctor` (`+0x18`=0, `+0x20`=1, `+0x28`=2,
    `+0x30`=100, `+0x38`=-1) -- d'ou le `-1`, lu et non devine.

    ⚠ Cette formule est PUREMENT AI : son unique xref native est
    `IdunBattle.AI.Playbook.Loki.ResurrectionOrbPlaybook$$CalculateCustomUtility`. `ExecuteBehaviour`,
    lui, cape par `GetMaxSummonsFormula` DIRECTEMENT (`First(tiles, GetMaxSummonsFormula(), 0)`) — les
    deux faces n'utilisent donc PAS le meme compte, et c'est le natif qui le veut."""
    tiles = resurrection_orb_possible_spawn_or_resurrect_tiles()
    amount = IfAmount(AmountIsGreaterThanZero(Count(resurrection_orb_possible_resurrect_targets())),
                      Difference(Count(tiles), Const(1)),
                      Count(tiles))
    return Min(resurrection_orb_max_summons_formula(), amount)


def resurrection_orb_tree(count: int) -> Spawn:
    """UNIQUE noeud natif de
    `IdunBattleLogic.Entities.Abilities.Active.Loki.ResurrectionOrbAbility$$ExecuteBehaviour` :

        Execute( Spawn(caster@0x160,
                       PickRandomly(CanAddUnit(AdjacentTiles(caster@0x160)), <count>, 0, 0x7fffffff, false),
                       unitId = GetStringConstant(0) = 'necroSmnWarrior',
                       SpawnUnitOptions.WithStatsFromConfig(config, entities)),
                 entities )

    `Execute` PLAIN (PAS `ExecuteAtomic`, PAS de `Group`) -> aucun `AtomicGroup` (contraste
    SupremeCommander `ExecuteAtomic(0x48)`). AUCUN sous-behaviour on-appearance dans les options (le natif
    passe `WithStatsFromConfig(config, execCtx, 0, 0)` : pas de `+0x10` AddEffect ni `+0x18` attaque) -> le
    Warrior n'agit PAS a l'apparition.

    Le `count` natif est evalue EAGERLY (la formule `GetMaxSummonsFormula` est `Calculate`e AVANT la
    construction du `PickRandomly`, cf. le decompile : le resultat int est passe au factory) -> le port
    l'evalue de meme dans `execute_behaviour` puis le passe en `pick_n` (FOLD du PickRandomly dans la
    feuille `Spawn`, qui seule voit `ectx.state.rng` -- MEME convention que SupremeCommander).

    ⚠ RESIDU DE BUILD (`rnca9r7q6c`, non porte -- hors perimetre #289, qui ne traite que la face
    DECISION) : `$$ExecuteBehaviour` a ete REECRIT entre `gqfc5mff6c` et le build courant. Il fait
    desormais `SortByFormula(tiles, MinDistance(It, NormalUnits(Enemies(caster))), asc)` puis
    `SortTilesByUtilityForSummon(., 7, caster)` puis `First(., GetMaxSummonsFormula(), 0)` -- un TRI
    deterministe la ou le port a garde le `PickRandomly` de l'ancien build ; et il PRECEDE le spawn
    d'un `GetResurrectBehaviour(...)` (resurrection d'un heros mecanique allie mort, `PickRandomly(1)`,
    PV = `PercentageOf(StatAmount(cible, Health, max), variable 0x26)`), entierement absent du port.
    L'ancre reste `casterTile@0x58` (cf. `resurrection_orb_possible_spawn_or_resurrect_tiles`)."""
    return Spawn(resurrection_orb_possible_spawn_or_resurrect_tiles(), "ResurrectionOrb",
                 pick_n=count)


class ResurrectionOrbAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.ResurrectionOrbAbility$$ExecuteBehaviour` (id 1009,
    `necroOverlord` « Anuphet »).

    ⚠ **VERDICT « SUMMON PUR » PERIME — relu le 2026-07-30 sur `rnca9r7q6c` (#289).** Il etait juste
    sur `gqfc5mff6c` : l'arbre n'y contenait NI `Revive` NI `Resurrect`. Le build COURANT a ajoute
    `$$GetResurrectBehaviour`, qui appelle bien `IdunBattleLogic.Entities.DSLBehaviors$$Resurrect` —
    `ExecuteBehaviour` y fait `op_Addition(GetResurrectBehaviour(...), Spawn(...))`. Le volet
    resurrection n'est PAS porte (residu nomme sur `resurrection_orb_tree`) ; ce qui EST porte ici,
    ce sont les selecteurs/formules que la face DECISION partage avec lui.

    Corps natif (ordre de lecture) :
        unitId  = GetStringConstant(config, 0)                       # necroSmnWarrior
        formula = GetMaxSummonsFormula(this)                         # cf. resurrection_orb_max_summons_formula
        tiles   = CanAddUnit(AdjacentTiles(caster@0x160))
        count   = formula.Calculate(entities)                        # EAGER (int), pas un noeud
        picked  = PickRandomly(tiles, count, 0, 0x7fffffff, false)
        opts    = SpawnUnitOptions.WithStatsFromConfig(config, entities)
        AActiveAbility.Execute(this, Spawn(caster@0x160, picked, unitId, opts), entities)

    Stats du summon = `WithStatsFromConfig` -> `summonHp`/`summonDmg`/`summonArmor`[level] x multiplier de
    rarete (les 3 sont dans `variablesAffectedByRarityBonus`) — c'est exactement ce que
    `Spawn`/`_spawn_config_grot` lit via `build_summon_context(summon_ability='ResurrectionOrb')`.

    Renvoie {ability, caster, count, spawned, dsl}. Termine le tour (1009 hors des frozensets de base.py)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.ResurrectionOrb)   # 1009
    ABILITY_ID = "ResurrectionOrb"

    # GATE DE CIBLE (#115). `IdunBattleLogic.Entities.Abilities.Active.Loki.ResurrectionOrbAbility$$.ctor` :
    #     TargetingOptions..ctor(&opts, 1, &statsFromClass, 1, 0x8000000020, 0, 0, 0)
    #     AActiveAbility..ctor(this, &opts, 2, 0)
    # Overload « flags DIRECTS » (`IdunBattle.Core.Services.TargetingOptions$$.ctor` 7 params : le 5e
    # argument atterrit tel quel a `options+0x28` = Rules) -> le litteral EST le masque effectif ; ce
    # n'est PAS l'overload preset+flags (qui, lui, a 3 params et fait `param_3 | preset.Rules`).
    # Decomposition (`IdunBattle.Core.Services.TargetingRule`) :
    #     0x20          TargetHasFreeAdjacentTile  -> il faut un hex libre adjacent (ou spawner), NON PORTE
    #     0x8000000000  TargetIsCaster « la cible DOIT etre le caster » -> PORTE : ResurrectionOrb est un
    #                   SELF-CAST STRICT (le natif refuse tout target != caster).
    # `self_cast` = le BYTE `options+0x00`, ici le 2e argument du ctor (= 1) : il aiguille le cast
    # SUR SOI-MEME vers `TargetingQuery$$GetCasterNotAddedReason` au lieu du filtre statique.
    # PORTEE (#241) : `range = TargetingRange` statique `+0x60` = `overrideRange = 0`,
    # `forceMeleeTarget = False` -- portee NULLE, coherent avec un cast SELF.
    TARGETING_OPTIONS = TargetingOptions(rules=(
          TR.TargetHasFreeAdjacentTile
        | TR.TargetIsCaster
    ), self_cast=True, range=RANGE_SELF, force_melee_target=RANGED_BOOL_FALSE)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        entities = entities_from_state(state, caster_id, target_id)
        # `GetMaxSummonsFormula(...).Calculate(entities)` — EAGER cote natif (le int alimente PickRandomly).
        count = int(resurrection_orb_max_summons_formula().evaluate(entities) or 0)
        ectx = ExecutionContext(state=state, rng=state.rng)
        resurrection_orb_tree(count).execute(entities, ectx)
        spawned = [p["unit"] for n, p in ectx.emitted if n == "SpawnUnit"]
        return {"ability": "ResurrectionOrb", "caster": caster_id, "target": target_id,
                "count": count, "spawned": spawned, "dsl": True}


# =================== Chronometron (Thothmek `necroChronomancer`, actif 1226) — #116 ===================
#
# Indices de config lus au decompile de
# `IdunBattleLogic.Entities.Abilities.Active.Loki.ChronometronAbility$$ExecuteBehaviour` :
CHRONOMETRON_CONST_RANGE = AbilityConstantType.range          # GetNumberConstant(0x16)  -> "range"      = 2
CHRONOMETRON_CONST_NR_OF_ROUNDS = AbilityConstantType.nrOfRounds   # GetNumberConstant(0x45)  -> "nrOfRounds" = 1 (== SquigMine)
CHRONOMETRON_TRAIT_SUMMON = int(UnitTrait.Summon)   # 2 — `HasTrait(It@0x180, 2)` du If natif


def chronometron_affected_enemies(range_val: int):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.ChronometronAbility$$GetAffectedEnemies` — MIRROR :

        SurroundingEnemies(caster@0x160, GetNumberConstant(0x16)=range, 1, 3)

    surcharge 5-args de `IdunBattleLogic.Entities.DSLSelectors$$SurroundingEnemies` : le MEME noeud sert de
    CENTRE **et** de reference d'equipe (`Enemies(param_2, Units(SurroundingTiles(param_2, incl=1, range) -
    Tiles(param_2)))`) -> ennemis DU CASTER dans le DISQUE rayon `range` autour de SA tuile, caster exclu.
    Le port l'exprime avec le centre `CasterTile()` (le noeud porte prend une POSITION en centre) et la
    reference d'equipe implicite = le caster — identique par construction (`Caster` et `CasterTile`
    designent la meme tuile), meme forme que `harbinger_pool_selector`."""
    # #585-r1 : `SurroundingEnemies(gs, gs@0x48, range, unique: 1, 3)` -- littéral LU dans
    # `...ChronometronAbility$$GetAffectedEnemies`. Les QUATRE surcharges natives portent le
    # `unitSelectionType` en DERNIERE position : aucune ambiguite de lecture ici.
    return SurroundingEnemies(CasterTile(), Const(range_val), selection_type=SELECTION)


def chronometron_tree(range_val: int, rounds: int):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.ChronometronAbility$$ExecuteBehaviour` — MIRROR 1:1 :

        Execute( Foreach( GetAffectedEnemies,
                          op_BitwiseAnd( GetApplyStunOrPinToActiveTarget,
                                         GetAddExtraDamageEffectToActiveTarget ) ),
                 entities )

    avec (les DEUX sous-arbres sont des methodes natives NOMMEES, re-inlinees dans ExecuteBehaviour) :

      `$$GetApplyStunOrPinToActiveTarget` =
          If( HasTrait(It@0x180, 2 = UnitTrait.Summon),
              AddEffect(0x48a = EffectType.Stunned, stateRef, caster@0x160, It@0x180, TurnsFromRounds(nrOfRounds)),
              AddEffect(0x429 = EffectType.Pinned,  stateRef, caster@0x160, It@0x180, TurnsFromRounds(nrOfRounds)) )

      `$$GetAddExtraDamageEffectToActiveTarget` =
          AddEffect(0x60e = EffectType.Chronometron_ExtraDamage, stateRef, Owner@0x148, It@0x180, <duree ZERO>)

    Points LUS (jamais devines) :
      * `It@0x180` = le slot **ActiveTarget** : le `ForeachBehaviour` a corps STATIQUE ecrit
        `entities[slot 4] = element` avant d'executer (cf. `Foreach` cote port, qui lie desormais
        `active_target`). D'ou `ActiveTarget()` — PAS `Target()` (l'ability est SELF-castee : le `target`
        du message n'intervient nulle part dans l'arbre).
      * la SOURCE des 2 premiers AddEffect est `caster@0x160`, celle du 3e est `Owner@0x148` — dans un cast
        d'active Owner == Caster (le port pose la source = caster dans les deux cas, comportement par defaut
        d'`AddEffect`).
      * la duree du 3e AddEffect est la struct ZERO-INITIALISEE (`local_198..uStack_180 = 0`), PAS un
        `TurnsFromRounds` -> `duration_rounds=None` = duree DEFAUT de l'effet (`DefaultAmountOfRounds`),
        exactement la convention deja en place pour le `Pinned` de CrushingClaws.
      * ENUMS QUALIFIES : `0x48a`/`0x429`/`0x60e` sont des **EffectType** (Stunned / Pinned /
        Chronometron_ExtraDamage) et `2` un **UnitTrait** (Summon).

    L'ordre du `op_BitwiseAnd` est stun-ou-pin D'ABORD, extra-damage ENSUITE (mirror `op_and`)."""
    stun_or_pin = IfBehaviour(
        HasTrait(ActiveTarget(), CHRONOMETRON_TRAIT_SUMMON),
        AddEffect(int(EffectType.Stunned), "Stunned", ActiveTarget(), duration_rounds=rounds),
        AddEffect(int(EffectType.Pinned), "Pinned", ActiveTarget(), duration_rounds=rounds))
    extra_damage = AddEffect(int(EffectType.Chronometron_ExtraDamage), "Chronometron_ExtraDamage",
                             ActiveTarget(), duration_rounds=None, scale_from_source=True)
    return Foreach(chronometron_affected_enemies(range_val), op_and(stun_or_pin, extra_damage))


class ChronometronAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.ChronometronAbility$$ExecuteBehaviour` (id 1226,
    `necroChronomancer` « Thothmek »).

    Pose sur CHAQUE ennemi du disque rayon `range`(=2) autour du caster : `Stunned` (1162) si l'ennemi a le
    trait `Summon`, sinon `Pinned` (1065), pour `TurnsFromRounds(nrOfRounds=1)` ; ET l'effet
    `Chronometron_ExtraDamage` (1550) a duree DEFAUT. Aucune attaque, aucun degat, aucun spawn — c'est un
    pur poseur d'effets (patron « MoW effect-poser » de case-90, ici sur une ACTIVE de hero).

    Structure = `Foreach(selecteur, If(...) & AddEffect(...))` (cf. `chronometron_tree`).

    GROUND TRUTH LIVE deja au dossier (case-92 §4, session 78, porteur INJECTE par `catalog_inject.py` car
    `necroChronomancer` est hors du seed BC capture) : « necroChronomancer 1226 Chronometron -> effets 1065
    Pinned + 1550 Chronometron_ExtraDamage ».

    CONTRIBUTION AU DEGAT de l'effet 1550 : PORTEE (residu transverse R9 ferme).
    `IdunBattle.Entities.Effects.Loki.Chronometron_ExtraDamageEffect$$CreateEffectDamageBonusForAttack` =
        EffectBonus.ForAddition( OwnerIsTarget & IsUnit(caster@0x160)
                                   & AreFriends(caster@0x160, EffectSource(Effect@0x150)),
                                 Multiply( If(IsMechanical(caster@0x160), ConfigVar(9 = extraDmg_2),
                                                                          ConfigVar(8 = extraDmg)),
                                           TimesEffectApplied(Effect@0x150) ),
                                 AbilityOrEffect(0x4ca = 1226) )
    et `$$CreateRemoveEffectTrigger` = `On(9) & OwnerIsTarget & IsUnit(caster) & AreFriends(caster,
    EffectSource)` (l'effet est CONSOMME au 1er coup d'un allie du Chronomancer). Les TROIS entrees dont
    depend la magnitude sont desormais dans l'`attacker_ctx` PARTAGE des deux faces (combat
    `damage_model.defender_modifiers` + prediction `playbook/prediction/_shared.py`) : `team` +
    `team_by_id` (`AreFriends(caster, EffectSource)`), `traits` (`IsMechanical(caster)`), et le compteur
    `EffectComponent.TimesApplied @+0x6c` porte par l'instance (`BaseEffect.times_applied`).
    Classe d'effet : `entities/effects/loki/damage_reduction.py::ChronometronExtraDamageEffect` (canal
    `create_effect_damage_malus_for_defense`, mold `OwnerIsTarget` d'ExemplarOfHate) ; trigger de
    retrait : `runner/operations/triggers/loki/chronometron.py` (`EFFECT_TRIGGERS[1550]`)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.Chronometron)   # 1226
    ABILITY_ID = "Chronometron"

    # GATE DE CIBLE (#115). `IdunBattleLogic.Entities.Abilities.Active.Loki.ChronometronAbility$$.ctor`
    # n'appelle pas `TargetingOptions..ctor` : IL2CPP a INLINE la construction et ecrit les champs
    # directement sur la pile avant `AActiveAbility..ctor(this, &opts, 2, 0)`. Le champ Rules
    # (`options+0x28`, ecrit en deux dwords `0x6004000` / `0`) donne le masque effectif.
    # Le BYTE `options+0x00` vaut **1** (`local_48 = 1` avant l'appel a `AActiveAbility..ctor`) ->
    # `self_cast=True`. Combinaison LUE TELLE QUELLE dans la factory native
    # `IdunBattle.Core.Services.TargetingOptions$$SelfCastIfEnemyInCustomRangeOptions`, qui pose
    # exactement `byte0 = 1` + `Rules = TargetIsEnemy` + un `Range` : l'ability est **SELF-CASTEE**,
    # et `TargetIsEnemy`/`Range` servent au PREDICAT « existe-t-il au moins un ennemi a portee ? »
    # (evalue par `GetCasterNotAddedReason` -> `GetValidTargets`, qui rend `0x800`
    # `AddCasterIfAtLeastOneTarget` si l'ensemble est vide -- MESURE live).
    # Decomposition (`IdunBattle.Core.Services.TargetingRule`) :
    #     0x4000      TargetIsEnemy        -> PORTE, mais SEULEMENT sur le chemin « cible = un TIERS »
    #                                         (un allie est refuse) ; le self-cast ne passe PAS par la.
    #     0x6000000   AllowObscuredTarget  -> permissif (aucune contrainte de ligne de vue)
    # => l'ability accepte DEUX formes de cast : sur SOI (self-cast, forme naturelle -- l'arbre est
    # caster-ancre `Foreach(SurroundingEnemies(caster, range))`), ou sur un ENNEMI a portee.
    # PORTEE (#241) : le ctor construit les `TargetingOptions` INLINE (aucun appel a
    # `TargetingOptions..ctor`) mais recopie le `TargetingRange` statique `+0x18`
    # (`useRangeFromConfig` -> `Chronometron.constants.range` = 2) ; `forceMeleeTarget =
    # False`, `isSelfCasting = 1`.
    TARGETING_OPTIONS = TargetingOptions(rules=(
          TR.TargetIsEnemy
        | TR.AllowObscuredTargetByElevation
        | TR.AllowObscuredTargetByWalls
    ), self_cast=True, range=RANGE_FROM_CONFIG, force_melee_target=RANGED_BOOL_FALSE)

    def _params(self) -> tuple:
        """`(range, nrOfRounds)` = `GetNumberConstant(config, 0x16 / 0x45)` — DEUX constantes de config
        (jamais des scalaires figes). Defauts surs si absentes (range>=1, rounds>=1)."""
        rng_range = ability_var(self.ABILITY_ID, "range", is_constant=True) or 1
        rounds = ability_var(self.ABILITY_ID, "nrOfRounds", is_constant=True) or 1
        return int(rng_range), int(rounds)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        entities = entities_from_state(state, caster_id, target_id)
        range_val, rounds = self._params()
        ectx = ExecutionContext(state=state, rng=state.rng)
        chronometron_tree(range_val, rounds).execute(entities, ectx)
        posed = [{"target": p["target"], "effect_type": p["effect_type"], "placed": p["placed"]}
                 for n, p in ectx.emitted if n == "AddEffect"]
        return {"ability": "Chronometron", "caster": caster_id, "target": target_id,
                "range": range_val, "rounds": rounds, "effects": posed, "dsl": True}


# ============ MultiThreatEliminator (Imospekh `necroDestroyer`, actif 1006) — #116 ============
#
MTE_CONST_RANGE = AbilityConstantType.range        # GetNumberConstant(0x16) -> "range"    = 2
MTE_CONST_EXTRA_HIT = AbilityConstantType.extraHit    # GetNumberConstant(0x2b) -> "extraHit" = 1  (== ConfigConst 43, formulas.py)
# `nrOfHits` N'EST PAS dans la config de 1006 : le nombre de coups est un CHAMP STATIQUE de la classe
# native, pose par `IdunBattleLogic.Entities.Abilities.Active.Loki.MultiThreatEliminatorAbility$$.cctor`
# (`**(class+0xb8) = 6`) et lu par `$$ExecuteBehaviour` (`Direct(<static>)`). Deja etabli cote DECISION
# (case-166-168 : `MultiThreatEliminatorAbility.get_special_hits -> 6`). C'est une constante NATIVE, pas
# un scalaire invente ni une valeur de gameconfig.
MTE_NR_OF_HITS = 6


def multi_threat_next_target_selector(range_val: int):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.MultiThreatEliminatorAbility$$GetNextHitTargetSelector`
    — MIRROR 1:1 :

        op_BitwiseAnd(
            Unobscured( caster@0x160,
                        Enemies(caster@0x160,
                                SurroundingUnits(casterTile@0x168, range, 1, includeCenter=false, 3)) ),
            AdjacentUnits( Last(It@0x180, 1), 1, 3 ) )

    = « ennemi du caster, dans le DISQUE `range` autour de la tuile du caster (caster exclu), non obscurci
    depuis le caster, ET adjacent (hex 1) a la DERNIERE cible frappee ». `Last(It@0x180, 1)` sur un
    selecteur MONO-ENTITE (`ActiveTarget`, que la boucle vient de lier) rend cette entite -> porte comme
    `ActiveTarget()` (le noeud `Last` n'a pas d'autre effet sur un singleton).

    ⚠ GAP d'ORDRE (documente, non root-cause) : le natif prend `SelectSingle` = le PREMIER element dans
    SON ordre d'enumeration (tuiles via `UnitsOnTilesSelector`) ; le port prend le premier dans l'ordre de
    `ctx.units` (ordre d'entite ECS). Quand PLUSIEURS candidats satisfont l'intersection, la cible suivante
    peut differer. Deterministe et identique des que l'intersection a <= 1 element."""
    # #585-r1 : `Enemies(gs@0x48, SurroundingUnits(gs@0x50, n, unique: 1, includeCenter: 0, 3), 3)`
    # puis `AdjacentUnits(gs, Last(...), unique: 1, 3)` -- littéraux LUS.
    # L'ETAGE EXISTE depuis #585-r3 : `SurroundingUnits` et `AdjacentUnits` portent le parametre, et
    # les deux litteraux ci-dessus sont desormais poses la ou le natif les ecrit.
    return And(Unobscured(Enemies(SurroundingUnits(CasterTile(), Const(range_val),
                                                   selection_type=SELECTION),
                                  selection_type=SELECTION), Caster()),
               AdjacentUnits(ActiveTarget(), Const(1), selection_type=SELECTION))


def multi_threat_eliminator_tree(range_val: int, extra_hit: int) -> ChainLeftOverHitsAttackDamage:
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.MultiThreatEliminatorAbility$$ExecuteBehaviour` —
    MIRROR 1:1 (UN SEUL noeud, `ExecuteAtomic(this, tree, entities, 0x41)`) :

        ChainLeftOverHitsAttackDamage(
            caster@0x160, target@0x178,
            MinMaxDamage(minDmg/maxDmg[level]),                   # +0x68
            Direct(Nullable(GetDamageProfile(this)))              # +0xa0  -> config "damageProfile"=Gauss
            Direct(<champ statique de la classe> = 6),            # +0x98  hits
            AbilityOrEffect(this+0x10),                           # +0x70  source du coup
            GetNextHitTargetSelector(this),                       # +0x88
            Get(GetNumberConstant(0x2b) = extraHit))              # +0x90  extraHits

    ⚠ `DSLFormulas$$Get(int)` **EST** `DSLFormulas$$Direct(int)`, et ce n'est PAS une analogie de nom
    (#512-r5, MESURE sur `t6dpr4k06g`). Les deux corps chargent le MEME `Il2CppClass*`, appellent le
    MEME allocateur et le MEME ctor avec le MEME argument -- leurs empreintes structurelles
    (`data/symbols/<build>/fingerprints/functions.tsv`) sont identiques sur les CINQ couches, et le
    desassemblage rend les MEMES 5 adresses decisives ; seuls les booleens
    `s_Il2CppMethodInitialized` different, un octet d'amorcage qui ne designe ni classe ni valeur.
    Donc `Get(extraHit)` vaut bien la valeur `extraHit`, et le `extra_hit` scalaire passe ci-dessous
    est fidele. ⚠ ET IL FALLAIT RESOUDRE LA BONNE SURCHARGE : `$$Get` en a TROIS
    (`Get(s:System.String) -> IStringFormula`, `Get(vector:IdunBattle.Utils.Hex.Edge) ->
    IVectorFormula`, `Get(amount:System.Int32) -> IAmountFormula`), que `ghidra/functions.tsv` nomme
    identiquement -- et les deux premieres allouent bel et bien d'AUTRES classes. Confronter
    `$$Direct` a la surcharge `string` est ce qui avait fait ecrire que les deux factories
    divergeaient. Mesure re-jouable : `probe_512r5_get_vs_direct.py` ; cliquet
    `tests/engine/test_512r5_get_est_direct_offline.py`.

    `attackRangeType = Ranged` (gameconfig) -> `is_melee=False`. Famille de factory = **ATTACK** (le nom
    natif est `...AttackDamage`, et le behaviour construit par iteration porte le meme mold de champs que
    `AttackDamageBehaviour`) -> `native_factory="attack"` (2 tirages/coup a cc=0)."""
    return ChainLeftOverHitsAttackDamage(
        Caster(), Target(), multi_threat_next_target_selector(range_val),
        "MultiThreatEliminator", "Gauss", MTE_NR_OF_HITS, extra_hit, is_melee=False,
        # `AbilityOrEffect(this+0x10)` = le `+0x70` du mold, LU au call-site ci-dessus
        # (#512-r2 volet 2). Sans lui, l'`On(PreAttack = 5)` de chaque maillon partait sans id.
        ability_type=int(ActiveAbilityType.MultiThreatEliminator))


class MultiThreatEliminatorAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.MultiThreatEliminatorAbility$$ExecuteBehaviour`
    (id 1006, `necroDestroyer` « Imospekh »).

    6 coups Gauss (`minDmg`/`maxDmg`[level]) sur la cible ; les coups qui tombent sur le CADAVRE sont
    REPORTES (+1 par ennemi tue) sur l'ennemi suivant — adjacent a la derniere cible ET dans le disque
    rayon `range`(=2) du caster, non obscurci — et ainsi de suite. i2 mot a mot : « Deals 6x ... Molecular
    Damage to an enemy within range 2. Any leftover hits are allocated to another enemy adjacent to the
    target and in range 2. Each enemy killed adds +1 hit and the ability keeps targeting new enemies until
    there are no more enemies or hits left. »

    Le report vit dans la feuille `ChainLeftOverHitsAttackDamage` (`behaviours/combat.py`) — mirror du
    `ChainLeftOverHitsAttackDamageBehaviour` natif, y compris son `GetLeftOverHits` (coups gaspilles sur le
    cadavre + `extraHit` si la cible est morte) et sa garde de 100 iterations. Ici, seule la CONSTRUCTION
    de l'arbre (`multi_threat_eliminator_tree`).

    Renvoie {ability, caster, target, chain, dsl}. Termine le tour (1006 hors des frozensets base.py)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.MultiThreatEliminator)   # 1006
    ABILITY_ID = "MultiThreatEliminator"

    # GATE DE CIBLE (#115). `IdunBattleLogic.Entities.Abilities.Active.Loki.MultiThreatEliminatorAbility$$.ctor`
    # COPIE le PRESET STATIQUE `IdunBattle.Core.Services.TargetingOptions` statics `+0x140` (pose par
    # `IdunBattle.Core.Services.TargetingOptions$$.cctor`), puis `AActiveAbility..ctor(this, &opts, 0, 0)`.
    # Masque effectif = `preset+0x28` = statics `+0x168` -> `0x4002`. Le MEME preset alimente
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.GravitonRifleAbility$$.ctor` (cf. votann.py).
    # Decomposition (`IdunBattle.Core.Services.TargetingRule`) :
    #     0x2      TargetMatchesDynamicRule -> consulte `GetDynamicInvalidTargetReason` (non surcharge
    #              ici -> defaut 0 = pas de refus dynamique, degradation PERMISSIVE assumee)
    #     0x4000   TargetIsEnemy            -> PORTE (refus sur soi-meme / un allie)
    # PORTEE (#241) : preset `TargetingOptions` statique `+0x140` -> `TargetingRange`
    # statique `+0x18` (`useRangeFromConfig` -> `MultiThreatEliminator.constants.range` = 2)
    # + `forceMeleeTarget = True`.
    TARGETING_OPTIONS = TargetingOptions(rules=TR.TargetMatchesDynamicRule | TR.TargetIsEnemy,
                                         range=RANGE_FROM_CONFIG,
                                         force_melee_target=RANGED_BOOL_TRUE)

    def _params(self) -> tuple:
        """`(range, extraHit)` = `GetNumberConstant(config, 0x16 / 0x2b)`."""
        rng_range = ability_var(self.ABILITY_ID, "range", is_constant=True) or 1
        extra_hit = ability_var(self.ABILITY_ID, "extraHit", is_constant=True) or 0
        return int(rng_range), int(extra_hit)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        entities = entities_from_state(state, caster_id, target_id)
        range_val, extra_hit = self._params()
        ectx = ExecutionContext(state=state, rng=state.rng)
        multi_threat_eliminator_tree(range_val, extra_hit).execute(entities, ectx)
        chain = next((p["chain"] for n, p in ectx.emitted if n == "ChainLeftOverHits"), [])
        return {"ability": "MultiThreatEliminator", "caster": caster_id, "target": target_id,
                "range": range_val, "extra_hit": extra_hit, "chain": chain, "dsl": True}


# ================== TunnelingHorror (necroSmnDestroyer, actif 1011) -- #366-r1 ====================
#
# Le VECTEUR DE POSE du marqueur `TunnelingHorror_PendingSummon` (EffectType 0x459 = 1113). Le porteur
# `necroSmnDestroyer` (« Ophydian Destroyer ») est un SUMMON **sans invocateur d'unite** : la seule
# reference du gameconfig hors de sa propre entree est `abilities["EnvFactionSummons:Necrons"]
# .constants.unitId`, une ability d'ENVIRONNEMENT que AUCUNE unite ne porte. La voie confrontee est
# donc la GREFFE de 1011 sur un heros DU POOL (recours 3 de `docs/rl/case-92-catalog-injection.md`
# §5bis) -- legitime : `gameconfig.ability("TunnelingHorror")` n'a AUCUNE variable ni constante, et
# le behaviour ne lit ni stat, ni trait, ni arme du caster.
#
# i2 : « This unit may use tunnelling to move. It is then removed from the battlefield and emerges in
# its chosen hex at the start of its next turn, pushing any unit in that hex aside. »
#
# RE complete + les cinq mesures live : `docs/rl/case-366-r1-tunneling-horror-pending-summon.md`.

TUNNELING_HORROR_ID = "TunnelingHorror"
TUNNELING_HORROR_PENDING = int(EffectType.TunnelingHorror_PendingSummon)   # 0x459 = 1113


def tunneling_horror_remove_tree() -> RemoveUnitFromItsTiles:
    """1er des TROIS `AActiveAbility$$Execute` de
    `IdunBattleLogic.Entities.Abilities.Active.Loki.TunnelingHorrorAbility$$ExecuteBehaviour` :

        RemoveUnitFromItsTiles( <selecteur pre-construit du contexte DSL>, removeTileFromUnit: true )

    Le selecteur est un champ PRE-CONSTRUIT du contexte (`<ctx>+0x90` -> `+0x30`), pas une chaine
    lisible dans ce corps ; la MESURE live le tranche sans ambiguite -- l'event est
    `RemoveUnitFromTiles e=<caster> Clear_Unit_Tiles=1`, et le caster passe a `pos = null`,
    `alive = true`. D'ou `Caster()`."""
    return RemoveUnitFromItsTiles(Caster(), remove_tile_from_unit=True)


def tunneling_horror_forced_targets_tree() -> RemoveAllForcedAttackTargets:
    """2e `Execute` : `RemoveAllForcedAttackTargets(<meme selecteur +0x30>)` = le caster. N'a emis
    AUCUN event dans les cinq mesures (la liste de cibles forcees du caster etait VIDE) : porte pour
    la STRUCTURE de l'arbre ; observable seulement si le caster est sous Taunt /
    `InstinctiveBehaviour` au moment du cast."""
    return RemoveAllForcedAttackTargets(Caster())


def tunneling_horror_bond_tree(target_tile_id: int) -> AddBondEffect:
    """3e `Execute`, lu sur la surcharge `options` d'`IdunBattleLogic.Entities.DSLBehaviors$$
    AddBondEffect` (`effectType, abilityState, source, targets, bondedEntity, options`) :

        AddBondEffect( 0x459, AbilityStateReference,
                       source: <ctx+0x90 +0x48>, targets: <ctx+0x90 +0x78>,
                       bondedEntity: <ctx+0x90 +0x48>, options: <struct ZERO> )

    `source` et `bondedEntity` sont LE MEME champ -- la mesure live les donne tous deux egaux au
    caster (`Effect_SourceId = BondEffect_BondedId = <caster>`), et `targets` = la TUILE ciblee (le
    cast est TILE-TARGET).

    ⚠ La struct d'options est ZERO-initialisee : **aucun `TurnsFromRounds`**, donc pas d'override de
    duree -> `DefaultAmountOfRounds` -> `remaining = 0` = PERMANENT (mesure : l'effet survit a un
    tour complet, et n'est retire que par le cast de 1060). `docs/rl/summon-abilities-port-spec.md`
    annoncait « default -> 1 round » : REFUTE. D'ou `duration_rounds=None`.

    LIMITE DE CANAL cote CHARGEMENT (pas cote pose) : une instance SEEDEE depuis `tileMeta` a
    `bonded = None` (le canal ne publie pas le `BondEffect_BondedId`). La POSE offline, elle, le
    renseigne -- c'est precisement ce que ce vecteur ajoute."""
    return AddBondEffect(TUNNELING_HORROR_PENDING,
                         EffectType.TunnelingHorror_PendingSummon.name,
                         Caster(), FixedTileIds([int(target_tile_id)]),
                         duration_rounds=None, bonded_ref=Caster())


class TunnelingHorrorAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.TunnelingHorrorAbility$$ExecuteBehaviour`
    (id 1011, `necroSmnDestroyer`, namespace natif `Abilities.Active.Loki`). Cast TILE-TARGET.

    TROIS `AActiveAbility$$Execute` SUCCESSIFS (pas un `op_Addition` : le decompile re-copie les
    0x148 octets du contexte `entities` AVANT chacun -- meme forme que `WaaaghAbility`), dans cet
    ordre LOAD-BEARING : le caster quitte le plateau AVANT que le bond ne soit pose, donc au moment
    du bond `source`/`bondedEntity` designent une unite SANS position. Le port re-materialise
    `entities_from_state` avant chaque etage, comme le natif re-copie son contexte.

      1. `RemoveUnitFromItsTiles(Caster, removeTileFromUnit: true)`
      2. `RemoveAllForcedAttackTargets(Caster)`
      3. `AddBondEffect(0x459, ..., source: Caster, targets: TargetTiles, bondedEntity: Caster,
                        <options SANS TurnsFromRounds>)`

    OBSERVABLE DU CAST (mesure live #366-r1, greffe sur `necroDestroyer`, board MC1_67, seed 777) :

        [User_UseAbility e=<caster> «TunnelingHorror»]
          [Ability_Power e=<caster> «TunnelingHorror»]
            RemoveUnitFromTiles e=<caster>  Clear_Unit_Tiles=1
            [Effect_Refresh e=<effet> «TunnelingHorror_PendingSummon»]
              ReceiveEffect e=<tuile>  BondEffect_BondedId=<caster> Effect_SourceId=<caster>
                                       Effect_SourceActiveAbility=1011
          ChangeStats e=<caster>  UnitStats_TurnFinished=1

    et `tileMeta` ne marque QUE la tuile ciblee. Le caster passe a `pos = null` / `alive = true` :
    il est HORS PLATEAU, **pas mort**. (⚠ `rl_duel` l'affiche « TUE » -- son heuristique lit
    `hp = null` comme 0 ; faux positif d'AFFICHAGE, cf. la fiche.)

    L'ability 1060 `TunnelingHorror_Appear` (le retour sur la tuile marquee) est un arbre nettement
    plus gros, SANS aucune config au gameconfig : hors perimetre, residu nomme dans la fiche.

    Renvoie {ability, caster, tile, removed_from_tiles, posed, dsl}."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.TunnelingHorror)         # 1011
    ABILITY_ID = TUNNELING_HORROR_ID

    # GATE DE CIBLE (#115). `IdunBattleLogic.Entities.Abilities.Active.Loki.TunnelingHorrorAbility$$.ctor` :
    #     range = <TargetingRange statics+0x48> = `useWholeBoard = true`   (copie de 0x18 octets)
    #     TargetingOptions..ctor(&opts, isSelfCasting=0, &range, forceMeleeTarget=1,
    #                            rules=0x8000000001042, 0, 0)
    #     AActiveAbility..ctor(this, &opts, 2)                              # AbilityAttackType.Others
    # FORME DIRECTE a 6 arguments -> le litteral EST le masque effectif (aucun preset).
    #   0x8000000001042 = TargetMatchesDynamicRule (1<<1)  | TargetIsTile         (1<<6)
    #                   | TargetTileIsFree         (1<<12) | TargetIsNotSteppable (1<<51)
    #                                                              -> somme EXACTE, 0 bit residuel
    #   forceMeleeTarget = 1 = RangedBool.False
    TARGETING_OPTIONS = TargetingOptions(rules=(
          TR.TargetMatchesDynamicRule
        | TR.TargetIsTile
        | TR.TargetTileIsFree
        | TR.TargetIsNotSteppable
    ), range=RANGE_WHOLE_BOARD, force_melee_target=RANGED_BOOL_FALSE)

    def get_dynamic_invalid_target_reason(self, state: "State", caster_id: int,
                                          target_id: Optional[int]) -> int:
        """`...TunnelingHorrorAbility$$GetDynamicInvalidTargetReason` -- MIRROR du decompile, qui
        porte **DEUX** refus (et non un seul) :

            if ( HasEffect(Get(target), 0x459, onlyActive: false, targetType: 6) )
                return 2;                                   // (a) tuile DEJA marquee
            foreach (t in casterTiles)
                if (IdunBattle.Entities.TileExtensions$$IsTemporary(t)) return 2;   // (b)
            return 0;

        (a) est PORTE : c'est le refus DISCRIMINANT mesure live (E3 -- sur 58 cibles legales du
        second porteur, la tuile marquee est la seule exclue, le temoin adjacent reste legal).

        (b) est un RESIDU NOMME : `IsTemporary` lit le champ booleen `@+0x2c` du `TileComponent`, que
        le port ne materialise PAS cote RUNNER (`state.board` ne porte que la geometrie et
        `walkable` ; le canal `tileMeta.isTemporary` n'est seede que du cote DECISION, cf.
        `engine/ai/context.py::is_temporary_by_pos`). Degradation PERMISSIVE, jamais un refus
        invente. Pour le fermer il faudrait seeder `isTemporary` dans le board du runner.

        Le port cherche l'effet 1113 sur l'ENTITE-TUILE (`state.effects.by_unit[tile_id]`), la meme
        cle que `snapshot._load_tile_effects` et `AddEffectOperation` -- il n'y a qu'un modele
        d'effet de tuile, alimente par la pose et par le chargement."""
        if target_id is None or state is None or state.effects is None:
            return 0
        for eff in state.effects.by_unit.get(int(target_id), []):
            if int(getattr(eff, "effect_type", -1)) == TUNNELING_HORROR_PENDING and not eff.consumed:
                return int(TR.TargetMatchesDynamicRule)
        return 0

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        # #287-r14 RESOLUTION DE CIBLE -- `IdunBattle.Core.Services.TargetingQuery$$GetActualTarget`
        # via le slot 16 d'`IActiveAbility` : pour un masque `TargetIsTile`, le role `target` du
        # natif est TOUJOURS l'entite-TUILE, que l'appelant ait passe la tuile ou son occupant.
        # IDEMPOTENT (`GetMainTile(<tuile>)` rend la tuile) -> inerte quand `AbilityHandler` a
        # deja resolu, mordant sur tout appel DIRECT (tests de migration, probes).
        target_id = self.get_actual_target(state, caster_id, target_id)
        board = state.board
        tile_id = target_id if (board is not None and target_id in board.by_id) else None
        if tile_id is None:
            # Cast TILE-TARGET : sans tuile resolue il n'y a AUCUN `targets` pour l'`AddBondEffect`.
            # On ne joue alors NI le retrait de tuiles NI le bond (le natif, lui, n'arrive pas la :
            # `TargetIsTile` est dans son masque, donc le gate statique a deja refuse).
            return {"ability": TUNNELING_HORROR_ID, "caster": caster_id, "tile": None,
                    "removed_from_tiles": None, "posed": [], "dsl": True}
        ectx = ExecutionContext(state=state, rng=state.rng)
        # 1) Execute(RemoveUnitFromItsTiles(Caster, true))
        tunneling_horror_remove_tree().execute(entities_from_state(state, caster_id), ectx)
        # 2) Execute(RemoveAllForcedAttackTargets(Caster))
        tunneling_horror_forced_targets_tree().execute(entities_from_state(state, caster_id), ectx)
        # 3) Execute(AddBondEffect(...)) -- `entities` RE-MATERIALISE : le caster n'a plus de tuile.
        tunneling_horror_bond_tree(tile_id).execute(entities_from_state(state, caster_id), ectx)
        removed = next((p for n, p in ectx.emitted if n == "RemoveUnitFromItsTiles"), None)
        posed = [{"target": p["target"], "effect": p["effect_type"], "bonded": p.get("bonded")}
                 for n, p in ectx.emitted if n == "AddBondEffect"]
        return {"ability": TUNNELING_HORROR_ID, "caster": caster_id, "tile": tile_id,
                "removed_from_tiles": removed, "posed": posed, "dsl": True}


# ===================================================================================================
# necroReanimator (MACHINE OF WAR Necrons) -- 1223 `ReanimationBeam` / 1224 `NanoscarabRepairProtocols`
#                                                                                              #902 #
# ===================================================================================================
#
# ⚠ L'AUDIT LES CLASSE TOUTES DEUX EN « REPAIR », ET C'EST VRAI DE **1223 SEULEMENT** -- la lecture
# de `$$ExecuteBehaviour` (jamais de la colonne derivee) rend TROIS volets pour 1223 et TROIS pour
# 1224, dont **UN SEUL** est une reparation :
#
#   1223 = reparation de MASSE  +  les SUMMONS marques agissent avec un Attack OVERRIDE  +  pose d'un
#          effet de RESURRECTION sur l'acteur ;
#   1224 = pose de l'effet-MARQUEUR 1545 sur UN allie mecanique  +  stat-mod +max HP  +  soin des PV
#          COURANTS du meme montant. **Aucun `Repair`** : `hpToRepair` de 1224 n'est PAS lu par
#          l'ability -- il est lu par l'EFFET 1545 (`NanoscarabRepairProtocolsEffect$$CreateEffectRepairBonus`
#          = `EffectBonus.ForAddition(OwnerIsTarget, ConfigVar(0x24 = hpToRepair))`), qui BONIFIE
#          toute reparation recue par le porteur. C'est cette variable-la que la colonne derivee de
#          l'audit a vue, et elle appartient a l'effet, pas au cast.
#
# Le couple forme une BOUCLE : 1224 marque, 1223 moissonne (son selecteur ET son gate de cible
# exigent l'effet 1545). Confirme par `IdunBattleLogic.Entities.Abilities.Active.Loki.ReanimationBeamAbility$$GetDynamicInvalidTargetReason`.
#
# ---------------------------------------------------------------------------------------------------
# `IdunBattleLogic.Entities.Abilities.Active.Loki.NanoscarabRepairProtocolsAbility$$ExecuteBehaviour`
# (MIRROR du decompile ; les 9 arguments de `ChangeStat` et les 8 d'`AddDynamicStatModifierEffect`
#  ont ete RELUS AU DESASSEMBLAGE -- le decompilateur rendait leurs 4 derniers slots en registres
#  non initialises) :
#
#   [A] addNrp = DSLBehaviors.AddEffect(0x609 = 1545 NanoscarabRepairProtocols,
#                    abilityState = AActiveAbility.AbilityStateReference,
#                    source  = Owner@DSLSelectors+0x30,
#                    targets = Target@DSLSelectors+0x60,
#                    options = default(0)          -> AUCUN override de duree = PERMANENT)
#   hp        = AbilityConfiguration.GetVariableForLevel(config@this+0x60, 0x1d = hp, abilityState)
#   [B] statMod = DSLBehaviors.AddDynamicStatModifierEffect(
#                    targets = Target@+0x60, source = Owner@+0x30,
#                    effectType = 0x60a = 1546 NanoscarabRepairProtocols_ExtraHp,
#                    statType = 5 = Health, abilityStateSelector = AbilityStateReference,
#                    turns = null, isHidden = false)
#   [C] hpFill  = DSLBehaviors.ChangeStat(targets = Target@+0x60,
#                    stat = Stat(5 = Health, part 0 = Current), mode = 2 = Add,
#                    amount = DSLFormulas.Get(hp), modificationEntity = null,
#                    selectionType = 3 = OnlyAliveAndTargetable,
#                    isModifiable = false, isHiddenModification = false)
#   Execute( ([B] op_Addition [C]) op_Addition [A] )
#
# `$$GetExtraMaxHealthBehavior` est le MEME couple `[B] + [C]`, sans appelant direct au binaire
# (IL2CPP l'a INLINE dans `$$ExecuteBehaviour`) -> UN seul foyer cote port.
#
# `$$GetDynamicInvalidTargetReason` :
#     if (target != null && UnitExtensions.IsMechanical(target))
#         return EntityExtensions.IsOwnerOfEffect(target, entities, 0x609, onlyActive: null) ? 2 : 0;
#     return 2;
#   -> une machine QUI PORTE DEJA le marqueur est REFUSEE (pas de re-pose ; le `2` est
#      `TargetingRule.TargetMatchesDynamicRule`).
#
# ---------------------------------------------------------------------------------------------------
# `IdunBattleLogic.Entities.Abilities.Active.Loki.ReanimationBeamAbility$$ExecuteBehaviour` :
#
#   carriers = DSLSelectors.EntitiesWithAnyEffect(
#                  DSLSelectors.MechanicalUnits(
#                      DSLSelectors.Friends(of = Owner@+0x30, entities = AllAliveUnits@+0x20, 3), 3),
#                  effectTypes = [0x609 = 1545], effectTarget = 6 = Both)
#   [A] repair = DSLBehaviors.Repair(
#                    mechanic = Caster@DSLSelectors+0x48,
#                    selector = DSLSelectors.Repairable(carriers, scope = 0, removeEffects = true,
#                                                       unitsToTarget = 3),
#                    amount   = DSLFormulas.ConfigVar(0x24 = hpToRepair, abilityState, config@+0x60),
#                    source   = AbilityOrEffect(0x4c7 = 1223),
#                    options  = RepairBehaviourOptions.ForRepair()   -> scope 0, removeEffects true)
#   [B] summons = $$GetSummonsTakeActionBehaviour(carriers, abilityState, entities) :
#           sel  = DSLSelectors.UnitsWithTrait(carriers, 2 = Summon, 3)
#           node = DSLFormulas.PercentageOfAttackCappedAtMax(
#                      unit = ActiveTarget@+0x68, statPart = **0 = Current**,
#                      maxAmount = ConfigVar(0xd = maxDmg), percentage = ConfigVar(0x4a = dmgPct),
#                      roundingRule = 0)
#           return ( DSLBehaviors.AddTemporaryAttackOverrideEffect(sel, node)
#                    op_BitwiseAnd DSLBehaviors.PerformAIAction(sel, actAsAGroup: 1, forced: 1) )
#                  op_BitwiseAnd DSLBehaviors.ResetTemporaryAttackOverrideEffect(sel)
#   [C] revive = DSLBehaviors.AddEffect(0x60b = 1547 ReanimationBeam_Revive,
#                    abilityState = AbilityStateReference, targets = Actor@DSLSelectors+0x40,
#                    turns = DSLFormulas.TurnsFromRounds(1))
#   Execute( ([A] op_Addition [B]) op_Addition [C] )
#
# `$$GetRepairBehaviour` et `$$GetAttackDamage` sont les MEMES sous-arbres, inlines par IL2CPP dans
# `$$ExecuteBehaviour` / `$$GetSummonsTakeActionBehaviour` : ZERO appelant direct pour le premier ;
# le second n'a que des call-sites d'`ExemplarOfHateAbility`, c'est-a-dire un CORPS PARTAGE par
# deduplication IL2CPP (meme sous-arbre a l'octet pres), pas un appel de 1223. Un seul foyer ici.
#
# `$$GetDynamicInvalidTargetReason` :
#     if (target != null && EntityExtensions.HasEffect(target, entities, 0x609, onlyActive: null)
#                        && UnitExtensions.IsMechanical(target))       return 0;
#     return 2;
#   `HasEffect = IsOwnerOfEffect || IsTargetOfEffect` (relu) ; le port n'a qu'un canal
#   (`EffectsState.by_unit`, indexe par l'entite PORTEUSE) et les deux branches y coincident --
#   1545 est pose par un `AddEffect` dont les `targets` sont la cible, qui en devient proprietaire.
#
# ---------------------------------------------------------------------------------------------------
# `AddTemporaryAttackOverrideEffect(targets, amount)` = `AddStatOverrideEffectBehaviour(targets,
# **0x510 = 1296 TemporaryStatOverride**, statType 0 = Attack, amount, duree 0, isModifiable 1)` ;
# `ResetTemporaryAttackOverrideEffect(targets)` = `RemoveEffect(targets, Nullable(0x510), 0)`.
# Les deux litteraux sont ECRITS PAR LES FABRIQUES elles-memes, pas par l'ability -> meme couple
# net-zero que `Repair_GalvanicField`/`TheQuickening`, a l'`EffectType` pres (1296 au lieu de 1242).
#
# ⚠ DEUX DIFFERENCES avec `Repair_GalvanicField`, lues et NON recopiees : `statPart` vaut **0 =
# Current** (GalvanicField : 3 = Initial), et l'action libre passe par `PerformAIAction(asGroup=1,
# forced=1)` -- le GROUP OPERATOR, qui boucle `PickNextUnit` -- la ou GalvanicField appelle
# `PerformAIAttackFromCurrentPosition` (une attaque, sans deplacement). Un summon reanime PEUT donc
# se DEPLACER puis agir.
#
# RESIDUS NOMMES (aucune invention, degradation FIDELE par absence de classe d'effet) :
#   * 1546 `NanoscarabRepairProtocols_ExtraHp` n'est pas dans `EFFECT_CLASSES` -> `AddEffectOperation`
#     pose un `BaseEffect` nu : l'effet EXISTE (visible de `decisionView.effects`, du gate de re-pose
#     et de `has_effect`) mais n'ajoute AUCUN max-HP. Le porter serait INOBSERVABLE en l'etat : les
#     stat-mods HEALTH vivent dans `ctx.stats[5]`, que RIEN ne relit pour les PV -- c'est le residu
#     deja nomme #572-r1 (`ChangeStat`/`SetHealth` mutent `HealthComponent` directement). Le volet
#     [C] (PV COURANTS), lui, MORD.
#   * 1547 `ReanimationBeam_Revive` idem : l'effet est POSE sur l'acteur pour 1 round, mais son
#     `ReviveEffect` n'est pas porte -> aucune resurrection. Son filtre natif, LU pour la fiche :
#     `$$CreateTargetFilter` = `AreFriends(Owner@+0x30, Target@+0x60) & HasTrait(Target, 5 =
#     Mechanical) & HasEffect(Target, 0x609, effectTarget 6)`, et `$$.ctor` =
#     `ReviveEffect..ctor(this, 2, null, Nullable(AbilityOrEffect(this)), true)`.
#   * 1545 `NanoscarabRepairProtocols` : sa PRESENCE suffit a tout ce que 1223 en attend (selecteur
#     `EntitiesWithAnyEffect` + les deux gates) et elle est portee. Son `EffectBonus.ForAddition`
#     (+hpToRepair a chaque reparation recue) ne l'est pas.

#: `EffectType.NanoscarabRepairProtocols` -- le MARQUEUR que 1224 pose et que 1223 moissonne.
NANOSCARAB_MARKER = int(EffectType.NanoscarabRepairProtocols)             # 0x609 = 1545
#: `EffectType.NanoscarabRepairProtocols_ExtraHp` -- le stat-mod HEALTH du volet [B] de 1224.
NANOSCARAB_EXTRA_HP = int(EffectType.NanoscarabRepairProtocols_ExtraHp)   # 0x60a = 1546
#: `EffectType.ReanimationBeam_Revive` -- l'effet de resurrection pose par le volet [C] de 1223.
REANIMATION_BEAM_REVIVE = int(EffectType.ReanimationBeam_Revive)          # 0x60b = 1547
#: Litteral ECRIT PAR LA FABRIQUE `DSLBehaviors$$AddTemporaryAttackOverrideEffect` (et repris tel
#: quel par `$$ResetTemporaryAttackOverrideEffect`), jamais par l'ability.
TEMPORARY_STAT_OVERRIDE = int(EffectType.TemporaryStatOverride)           # 0x510 = 1296
#: Cle de source du `ChangeStat` [C] de 1224. La branche HEALTH de la feuille mute
#: `HealthComponent.hp` directement (stat FILL-UP) et ne la relit pas ; elle reste NOMMEE pour la
#: tracabilite -- meme convention que `_UD_HEAL_SOURCE` (1061 `UnbreakableDuty`, MEME patron [B]+[C]).
_NRP_HEAL_SOURCE = "NanoscarabRepairProtocols:hpFill"

REANIMATION_BEAM_ID = "ReanimationBeam"
NANOSCARAB_REPAIR_PROTOCOLS_ID = "NanoscarabRepairProtocols"


def nanoscarab_carriers_selector() -> TargetsSelector:
    """`carriers` de `...ReanimationBeamAbility$$ExecuteBehaviour` -- MIRROR feuille par feuille :

        EntitiesWithAnyEffect( MechanicalUnits( Friends(of = Owner@+0x30,
                                                        entities = AllAliveUnits@+0x20, 3), 3),
                               [0x609 = 1545], effectTarget = 6 = Both )

    Les alliees MECANIQUES du porteur qui portent le marqueur `NanoscarabRepairProtocols`. Le
    `<DSLSelectors>+0x20` est `AllAliveUnits` (pool `EntityPool.AliveUnits`), PAS `AllUnits` -- le
    filtre alive est DANS la source, pas dans un noeud aval (#514).

    `effectTarget = 6 = Both` : cote port `EntitiesWithAnyEffect` interroge `ctx.has_effect`, dont le
    `source_flag` vaut deja 6 -- les branches owned/targeted coincident sur `EffectsState.by_unit`."""
    friends = Friends(AllAliveUnits(), Owner(), SELECTION)
    return EntitiesWithAnyEffect(MechanicalUnits(friends, SELECTION), [NANOSCARAB_MARKER])


def reanimation_beam_summons_selector(carriers: TargetsSelector) -> TargetsSelector:
    """`sel` de `...ReanimationBeamAbility$$GetSummonsTakeActionBehaviour` =
    `DSLSelectors.UnitsWithTrait(carriers, 2 = Summon, 3)`.

    Le natif RE-UTILISE l'instance `carriers` deja construite par `$$ExecuteBehaviour` (elle lui est
    passee en argument) -- d'ou le parametre plutot qu'une reconstruction, qui serait equivalente
    (les selecteurs sont purs) mais masquerait le partage."""
    return UnitsWithTrait(carriers, int(UnitTrait.Summon), SELECTION)


def reanimation_beam_override_amount(max_dmg: int, dmg_pct: int) -> AAmountFormula:
    """Le noeud MONTANT du volet SUMMONS de 1223 :
    `PercentageOfAttackCappedAtMax(ActiveTarget@+0x68, statPart = 0 = Current, ConfigVar(maxDmg),
    ConfigVar(dmgPct), roundingRule = 0)` = `Min(maxDmg, PercentageOf(Attack(sujet, Current), dmgPct))`.

    Le SUJET est l'unite qui RECOIT l'override (le summon), pas le caster : c'est
    `AddStatOverrideEffectBehaviour$$Execute` qui lie le slot sujet (`param_3[4] = current`) AVANT
    d'evaluer le noeud -- d'ou `Subject()`, exactement comme `galvanic_override_amount`
    (`abilities/repair.py`), dont le natif passe le MEME `<DSLSelectors>+0x68`.

    ⚠ `stat_part = 0 = Current` et non `3 = Initial` : LU au call-site (`mov r8d, 0` avant l'appel a
    `DSLFormulas$$PercentageOfAttackCappedAtMax`), et c'est la difference avec `GalvanicField`, qui
    passe `3`. Sur un summon deja buffe/debuffe les deux ne donnent PAS le meme plafond."""
    return percentage_of_attack_capped_at_max(Subject(), int(max_dmg), int(dmg_pct),
                                              stat_part=int(StatPart.CURRENT))


def _target_is_mechanical(state: "State", caster_id, target_id) -> bool:
    """`IdunBattle.Entities.UnitExtensions$$IsMechanical(target)` evalue HORS arbre, pour les deux
    `GetDynamicInvalidTargetReason`. Delegue au helper PARTAGE `behaviours.stats.is_mechanical`
    (`Mechanical | LivingMetal | Vehicle`, deja confronte live case-220) via le `has_trait` du
    contexte DSL. Accesseur ou unite absente -> False (degradation fidele : le natif rendrait alors
    `2`, un REFUS -- jamais un « tout passe »)."""
    if target_id is None:
        return False
    ents = entities_from_state(state, caster_id, int(target_id))
    ht = ents.has_trait
    if ht is None:
        return False
    u = next((x for x in (ents.units or ())
              if isinstance(x, dict) and x.get("id") == int(target_id)), None)
    return bool(u is not None and unit_is_mechanical(ht, u))


class NanoscarabRepairProtocolsAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.NanoscarabRepairProtocolsAbility` (id 1224,
    `necroReanimator` -- MACHINE OF WAR Necrons).

    Cast sur UN allie MECANIQUE qui ne porte pas encore le marqueur : pose l'effet PERMANENT 1545,
    ajoute `hp[level]` de PV MAX (stat-mod dynamique 1546) et le MEME montant de PV COURANTS.
    Aucune reparation, aucun degat -- cf. le bloc de commentaire ci-dessus pour pourquoi la colonne
    « REPAIR » de l'audit est trompeuse ici."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.NanoscarabRepairProtocols)   # 0x4c8 = 1224
    ABILITY_ID = NANOSCARAB_REPAIR_PROTOCOLS_ID

    # `...NanoscarabRepairProtocolsAbility$$.ctor` -- FORME 1 « FLAGS DIRECTS ». La surcharge appelee
    # est TRANCHEE PAR SES XREFS ENTRANTES : le `call` cible la surcharge SEPT arguments de
    # `IdunBattle.Core.Services.TargetingOptions$$.ctor` (`(this, isSelfCasting, range,
    # forceMeleeTarget, rules, getDynamicInvalidCasterReason, getDynamicInvalidTargetReason)`),
    # celle dont le corps ECRIT `rules` TEL QUEL a `options+0x28` -- ni preset combine (surcharge
    # `(this, template, additionalRules)`, qui fait `template.Rules | additionalRules`), ni copie
    # statique (surcharge `(this, template)`).
    #
    #   TargetingOptions..ctor(&opts, 0, &<TargetingRange statics>+0x48, 1, 0x40000402, 0, 0)
    #     isSelfCasting    = 0
    #     range            = `TargetingRange` statics+0x48 = RANGE_WHOLE_BOARD (`onlyAdjacent =
    #                        RangedBool.False`, `useWholeBoard = true`) -- LU dans
    #                        `IdunBattle.Core.Services.TargetingRange$$.cctor`
    #     forceMeleeTarget = 1 = RangedBool.False
    #     rules            = 0x40000402
    #   puis `AActiveAbility..ctor(this, &opts, 2)`.
    #
    # Decomposition du masque (`IdunBattle.Core.Services.TargetingRule`, bit a bit, RESTE = 0) :
    #     0x00000002  TargetMatchesDynamicRule -> tout le refus reel vit dans la regle DYNAMIQUE
    #     0x00000400  TargetIsFriendly         -> une cible ENNEMIE est refusee
    #     0x40000000  AllowNullCasterTile      -> permissif (une MoW n'occupe pas de tuile « caster »)
    # Le bit `CasterIsPossibleTarget` est ABSENT (contraste `RepairAbility`, qui l'a) : le Reanimator
    # ne peut pas se marquer lui-meme.
    TARGETING_OPTIONS = TargetingOptions(
        rules=(TR.TargetMatchesDynamicRule | TR.TargetIsFriendly | TR.AllowNullCasterTile),
        self_cast=False, range=RANGE_WHOLE_BOARD, force_melee_target=RANGED_BOOL_FALSE)

    def _extra_hp(self, state: "State", caster_id: int) -> int:
        """`AbilityConfiguration.GetVariableForLevel(config@this+0x60, 0x1d = hp, abilityState)`.

        COLLAPSE V : le natif garde un noeud `DSLFormulas.Get(<valeur>)`, dont l'argument est DEJA
        le scalaire resolu (`GetVariableForLevel` est appele AVANT la construction du noeud, pas
        dedans) -- on resout donc au meme endroit que lui. `(level, mult)` vient de l'`AbilityState`
        de CETTE active sur CE caster (#890), jamais d'un niveau global d'unite."""
        level, mult = active_ability_state(state, caster_id, self.ABILITY_TYPE)
        return int(ability_var(self.ABILITY_ID, AbilityVariableType.hp.name, level,
                               multiplier_pct=mult) or 0)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        extra_hp = self._extra_hp(state, caster_id)
        ents = entities_from_state(state, caster_id, int(target_id))
        ectx = ExecutionContext(state=state, rng=state.rng)
        # `turns = null` -> `duration_rounds=None` = pas d'override -> `DefaultAmountOfRounds`.
        stat_mod = AddDynamicStatModifierEffect(Target(), Owner(), NANOSCARAB_EXTRA_HP,
                                                int(StatType.HEALTH),
                                                name=EffectType.NanoscarabRepairProtocols_ExtraHp.name,
                                                duration_rounds=None)
        hp_fill = ChangeStat(Target(), int(StatType.HEALTH), "add", _NRP_HEAL_SOURCE, extra_hp)
        # `options = default(0)` -> aucun override de duree : le marqueur est PERMANENT.
        add_marker = AddEffect(NANOSCARAB_MARKER, EffectType.NanoscarabRepairProtocols.name,
                               Target(), duration_rounds=None, scale_from_source=True)
        op_add(op_add(stat_mod, hp_fill), add_marker).execute(ents, ectx)
        posed = [{"target": p["target"], "effect_type": p["effect_type"], "placed": p["placed"]}
                 for n, p in ectx.emitted if n in ("AddEffect", "AddDynamicStatModifierEffect")]
        filled = next((p for n, p in ectx.emitted if n == "ChangeStat"), None)
        return {"ability": NANOSCARAB_REPAIR_PROTOCOLS_ID, "caster": caster_id, "target": target_id,
                "extra_hp": extra_hp, "effects": posed, "hp_fill": filled, "dsl": True}

    def get_dynamic_invalid_target_reason(self, state: "State", caster_id: int,
                                          target_id: Optional[int]) -> int:
        """`...NanoscarabRepairProtocolsAbility$$GetDynamicInvalidTargetReason` -- MIRROR verbatim :

            if (target != null && UnitExtensions.IsMechanical(target))
                return EntityExtensions.IsOwnerOfEffect(target, entities, 0x609, null) ? 2 : 0;
            return 2;

        (`-(uint)(IsOwnerOfEffect != 0) & 2` au decompile : 2 si l'effet est deja la, 0 sinon.)

        `onlyActive = null` -> le natif NE consulte PAS `EffectComponent.IsActive @+0x5c` : le mirror
        est `components.has_effect_of_type` (qui ne filtre que `consumed`), et surtout PAS
        `ctx.has_effect`, dont le defaut `active_only=True` appellerait `BaseEffect.is_active`."""
        if not _target_is_mechanical(state, caster_id, target_id):
            return int(TR.TargetMatchesDynamicRule)
        return (int(TR.TargetMatchesDynamicRule)
                if has_effect_of_type(state, int(target_id), NANOSCARAB_MARKER) else 0)


class ReanimationBeamAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.ReanimationBeamAbility` (id 1223,
    `necroReanimator` -- MACHINE OF WAR Necrons).

    Cast sur un allie mecanique DEJA marque par `NanoscarabRepairProtocols` : repare
    `hpToRepair[level]` a TOUTES les machines alliees marquees (pas seulement la cible), fait agir
    immediatement celles qui ont le trait `Summon` avec un Attack OVERRIDE
    `Min(maxDmg, Attack_Current x dmgPct%)`, puis rend l'override (net-zero), et pose sur l'ACTEUR
    l'effet `ReanimationBeam_Revive` pour 1 round."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.ReanimationBeam)   # 0x4c7 = 1223
    ABILITY_ID = REANIMATION_BEAM_ID

    # `...ReanimationBeamAbility$$.ctor` -- MEME surcharge SEPT arguments que 1224 (tranchee par les
    # memes XREFS entrantes), MEME `TargetingRange` statique, MEME `forceMeleeTarget` ; DEUX ecarts,
    # tous deux LUS :
    #
    #   TargetingOptions..ctor(&opts, **1**, &<TargetingRange statics>+0x48, 1, **0x200040000402**, 0, 0)
    #     isSelfCasting    = 1        <- 1224 vaut 0
    #     range            = statics+0x48 = RANGE_WHOLE_BOARD
    #     forceMeleeTarget = 1 = RangedBool.False
    #     rules            = 0x200040000402
    #   puis `AActiveAbility..ctor(this, &opts, 2)`.
    #
    # Decomposition (RESTE = 0) :
    #     0x000000000002  TargetMatchesDynamicRule
    #     0x000000000400  TargetIsFriendly
    #     0x000040000000  AllowNullCasterTile
    #     0x200000000000  TargetIsUnit             <- ABSENT du masque de 1224
    TARGETING_OPTIONS = TargetingOptions(
        rules=(TR.TargetMatchesDynamicRule | TR.TargetIsFriendly | TR.AllowNullCasterTile
               | TR.TargetIsUnit),
        self_cast=True, range=RANGE_WHOLE_BOARD, force_melee_target=RANGED_BOOL_FALSE)

    def _params(self, state: "State", caster_id: int) -> tuple:
        """Les TROIS `ConfigVar` de l'ability, COLLAPSES a la valeur qu'ils rendent pour ce caster :
        `hpToRepair` (0x24), `maxDmg` (0xd), `dmgPct` (0x4a). Les trois s'indexent sur l'`AbilityState`
        de CETTE active (#890) ; `hpToRepair` et `maxDmg` sont dans `variablesAffectedByRarityBonus`
        (lu au gameconfig), `dmgPct` non -- `ability_var` applique le multiplicateur au bon endroit."""
        level, mult = active_ability_state(state, caster_id, self.ABILITY_TYPE)
        hp_to_repair = ability_var(self.ABILITY_ID, AbilityVariableType.hpToRepair.name, level,
                                   multiplier_pct=mult) or 0
        max_dmg = ability_var(self.ABILITY_ID, AbilityVariableType.maxDmg.name, level,
                              multiplier_pct=mult) or 0
        dmg_pct = ability_var(self.ABILITY_ID, AbilityVariableType.dmgPct.name, level,
                              multiplier_pct=mult) or 0
        return int(hp_to_repair), int(max_dmg), int(dmg_pct)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        hp_to_repair, max_dmg, dmg_pct = self._params(state, caster_id)
        carriers = nanoscarab_carriers_selector()
        summons = reanimation_beam_summons_selector(carriers)
        # `actor_id = caster_id` : le volet [C] pose 1547 sur `Actor@DSLSelectors+0x40`, et
        # `IdunBattle.Entities.Selectors.ActorSelector$$Select` rend une liste VIDE quand le slot
        # `AbilityEntities+0x00` est nul (les trois selecteurs Actor/Caster/Owner ont le MEME corps a
        # l'offset lu pres : `+0x00` / `+0x08` / `+0x18`). Sur un cast d'ACTIVE ce slot est renseigne,
        # et il vaut le CASTER -- MESURE, pas deduite : `probe_902 --phase beam` voit l'effet 1547
        # arriver sur la MoW casteuse (`Effect_Refresh e=79 -> ReceiveEffect e=53`). Sans ce fil, le
        # port n'aurait POSE AUCUN effet, et le temoin qui le montre a lui-meme du etre repare (le
        # mutant `Actor() -> Target()` passait AVEUGLE tant qu'on ne lisait que le cote live).
        ents = entities_from_state(state, caster_id, target_id, actor_id=caster_id)
        ectx = ExecutionContext(state=state, rng=state.rng)
        # [A] `Repair(Caster, Repairable(carriers, 0, true, 3), ConfigVar(hpToRepair), ForRepair())`.
        # `guard=None` : le natif ne pre-filtre PAS au-dela de `Repairable` -- c'est le gate
        # `AttackQuery$$EntityCanBeRepaired` DE L'OPERATION qui tranche, exactement comme 28/1119.
        repair = Repair(Repairable(carriers, scope=0, remove_effects=True,
                                   unit_selection_type=SELECTION),
                        hp_to_repair, guard=None, scope=0, remove_effects=True)
        # [B] `(AddTemporaryAttackOverrideEffect & PerformAIAction) & ResetTemporaryAttackOverrideEffect`
        override = AddStatOverrideEffect(summons, TEMPORARY_STAT_OVERRIDE, int(StatType.ATTACK),
                                         reanimation_beam_override_amount(max_dmg, dmg_pct),
                                         name=EffectType.TemporaryStatOverride.name,
                                         is_modifiable=True)
        act = PerformAIAction(summons, as_group=True, reset_turn_flags=True)
        reset = RemoveEffect(TEMPORARY_STAT_OVERRIDE, summons)
        # [C] `AddEffect(1547, AbilityStateReference, Actor@+0x40, TurnsFromRounds(1))`.
        revive = AddEffect(REANIMATION_BEAM_REVIVE, EffectType.ReanimationBeam_Revive.name,
                           Actor(), duration_rounds=1, scale_from_source=True)
        op_add(op_add(repair, op_and(op_and(override, act), reset)), revive).execute(ents, ectx)
        rep = next((p for n, p in ectx.emitted if n == "Repair"), None) or {}
        acted = next((p for n, p in ectx.emitted if n == "PerformAIAction"), None)
        posed = [{"target": p["target"], "effect_type": p["effect_type"], "placed": p["placed"]}
                 for n, p in ectx.emitted if n == "AddEffect"]
        return {"ability": REANIMATION_BEAM_ID, "caster": caster_id, "target": target_id,
                "amount": rep.get("amount"), "repairs": rep.get("repairs"),
                "summons": acted, "effects": posed, "dsl": True}

    def get_dynamic_invalid_target_reason(self, state: "State", caster_id: int,
                                          target_id: Optional[int]) -> int:
        """`...ReanimationBeamAbility$$GetDynamicInvalidTargetReason` -- MIRROR verbatim :

            if (target != null && EntityExtensions.HasEffect(target, entities, 0x609, null)
                               && UnitExtensions.IsMechanical(target))   return 0;
            return 2;

        MEME canal `onlyActive = null` que 1224 (cf. sa docstring). `HasEffect` = `IsOwnerOfEffect ||
        IsTargetOfEffect` : le port n'a qu'un canal (`EffectsState.by_unit`), ou les deux branches
        coincident pour 1545 -- l'effet est pose AVEC la cible en `targets`, donc elle en est
        proprietaire. Un effet 1545 qui serait un jour pose en AURA (porteur != cible) ferait diverger
        cette branche ; aucun call-site natif ne le fait aujourd'hui."""
        if target_id is None:
            return int(TR.TargetMatchesDynamicRule)
        if (has_effect_of_type(state, int(target_id), NANOSCARAB_MARKER)
                and _target_is_mechanical(state, caster_id, target_id)):
            return 0
        return int(TR.TargetMatchesDynamicRule)



# ===== StormOfFlensingBlades (1010, `necroNpc2FlayedOne` + les deux Flayed One de tutoriel) ========
# Lot #996 -- « six no-op silencieuses » (docs/rl/case-996-six-no-op-silencieuses-reconnaissance.md).
#
# `IdunBattleLogic.Entities.Abilities.Active.Loki.StormOfFlensingBladesAbility$$ExecuteBehaviour`
# ne construit AUCUN arbre : il appelle la surcharge 4-arguments
#
#   DSLBehaviors$$AtomicGroup( groupType = 0x3e = GroupType.StormOfFlensingBlades_Attacks,
#                              behaviour = <delegue>, initialTarget = null )
#
# qui passe par le PROCESSOR (slot virtuel) -- donc EXECUTION, pas construction de noeud. Le corps
# reel est le delegue
# `...StormOfFlensingBladesAbility.u003Cu003Ec__DisplayClass1_0$$u003CExecuteBehaviouru003Eb__0`,
# une BOUCLE IMPERATIVE de DEUX tours (`i = 0, 1`) qui, a chaque tour, fait :
#
#   AActiveAbility$$Execute( ability@this+0x10,
#       DSLBehaviors$$UseActiveAbility( subject     = Caster@+0x48,
#                                       targets     = Target@+0x60,
#                                       abilityType = DSLSelectors$$UnitNormalAttackType(Caster@+0x48),
#                                       parentAbility = Nullable<AbilityOrEffect>(op_Implicit(this)),
#                                       triggerAbilityOrEffect = <ZERO>,
#                                       options = { SkipEndTurnFlag = (i == 0), SkipAbilityFlag = 0,
#                                                   SkipAtomicCheck = 1, SkipAliveCheck = 0 } ) )
#
# CATEGORIE ANNONCEE PAR L'AUDIT = EFFECT/BUFF -> **FAUSSE**. Il n'y a NI effet NI buff dans ce
# cast : c'est une DOUBLE ATTAQUE NORMALE. L'audit derive sa colonne du `damageProfile` de l'ARME du
# porteur et le declare lui-meme (residu #491-r2) -- pour une ability non portee, personne ne
# connait son `ExecuteBehaviour`, donc la colonne ne peut pas etre derivee.
#
# L'ATTAQUE EST L'ATTAQUE **NORMALE** DE L'UNITE, pas une attaque d'ability : le type est
# `UnitNormalAttackType(Caster)`, resolu par distance, et le kit gameconfig 1010 ne porte NI
# `minDmg`/`maxDmg` NI `nrOfHits` NI `damageProfile` -- seulement `attackRangeType = Melee`. Fabriquer
# un profil de degats ici serait une invention pure.
#
# LES OPTIONS SONT LUES, ET ELLES NE SONT PAS PORTEES -- residu NOMME. La struct est
# `IdunBattle.Entities.Behaviours.UseActiveAbilityBehaviourOptions` (`InvalidTargetPolicy@+0x00`,
# `SkipEndTurnFlag@+0x08`, `SkipAbilityFlag@+0x09`, `SkipAtomicCheck@+0x0a`, `SkipAliveCheck@+0x0b`,
# `TempData@+0x0c`) ; le decompile ecrit `CONCAT12(1, (ushort)(i == 0))` a `+0x08`, soit
# `SkipEndTurnFlag = (i == 0)` et `SkipAtomicCheck = true`. Le port de `UseActiveAbility` ne
# modelise AUCUN de ces champs (14 call-sites, tous a options ZERO avant celui-ci) et l'ecart est
# INERTE ici : la feuille ne pose aucun flag de fin de tour -- ce sont les tables d'override du
# handler qui le font, pour l'ability PARENTE. La premiere attaque ne doit pas clore le tour, la
# seconde si : c'est exactement ce que le port obtient en ne posant rien depuis la feuille.

STORM_OF_FLENSING_BLADES_ID = "StormOfFlensingBlades"
STORM_OF_FLENSING_BLADES_ATTACKS = 2      # les DEUX tours de la boucle du delegue (i = 0, 1)


def storm_of_flensing_blades_tree():
    """Arbre de `...StormOfFlensingBladesAbility$$ExecuteBehaviour` (MIRROR, cf. le bloc ci-dessus) :

        AtomicGroup( GroupType.StormOfFlensingBlades_Attacks,
                     UseActiveAbility(Caster, Target, UnitNormalAttackType(Caster))
                     PUIS le MEME, une seconde fois )

    DEUX NOEUDS DISTINCTS, PAS UN `Repeat` : le natif n'utilise pas
    `IdunBattleLogic.Entities.DSLBehaviors$$Repeat` -- c'est une boucle C# dans un lambda, et les
    OPTIONS different entre les deux tours (`SkipEndTurnFlag = (i == 0)`). Un `Repeat` reutiliserait
    le MEME noeud et effacerait cette difference du mirror.

    `op_add` (= `Seq`) COURT-CIRCUITE sur `stop`, la boucle native NON. L'ecart est inerte :
    `UseActiveAbility.execute` rend `OperationResult.ok()` sur ses TROIS chemins de sortie, donc
    aucun `stop` ne peut naitre du premier coup.

    `UseActiveAbility(Caster(), Target())` = la feuille deja portee, specialisee au dispatch
    d'ATTAQUE NORMALE (`UnitNormalAttackType(Caster)` -> `AttackDamageOperation.execute`, resolveur
    d'arme par distance)."""
    first = UseActiveAbility(Caster(), Target())        # i = 0, SkipEndTurnFlag = true
    second = UseActiveAbility(Caster(), Target())       # i = 1, SkipEndTurnFlag = false
    return AtomicGroup(op_add(first, second))           # GroupType.StormOfFlensingBlades_Attacks


class StormOfFlensingBladesAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.StormOfFlensingBladesAbility$$ExecuteBehaviour`
    (id 1010, `necroNpc2FlayedOne` « Flayed One » + `necroNpc2TutFlayedOne` /
    `necroNpc2TutFlayedOneFTUEtest`, npc Necrons). Cast UNIT-TARGET.

    Kit gameconfig 1010 : `attackRangeType = Melee` et RIEN d'autre -- aucune variable de niveau,
    aucune constante, aucun profil de degats. Cette absence CONFIRME que le cast n'a pas de degat
    propre : il rejoue deux fois l'attaque NORMALE du porteur.

    OBSERVABLE porte : DEUX attaques normales du caster sur la cible, dans cet ordre, dans un
    groupe atomique. Aucun effet, aucun buff (l'audit annoncait EFFECT/BUFF -- categorie FAUSSE).

    Flags de tour : defauts base (1010 absent des tables d'override)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.StormOfFlensingBlades)   # 1010
    ABILITY_ID = STORM_OF_FLENSING_BLADES_ID

    # GATE DE CIBLE + PORTEE -- forme de ctor = **FLAGS DIRECTS** (le litteral du ctor EST le
    # masque ; aucun preset recopie, aucun OR de flags).
    # `...StormOfFlensingBladesAbility$$.ctor` :
    #     TargetingOptions..ctor(&opts, isSelfCasting=0, range=<TargetingRange statics+0x30>,
    #                            forceMeleeTarget=1, rules=0x4010, 0, 0)
    #     AActiveAbility..ctor(this, &opts, 0)   # 3e arg = 0 = AbilityAttackType.DirectTargetAttack
    #
    # Decomposition EXHAUSTIVE -- 0x10 + 0x4000 = 0x4010, aucun bit residuel :
    #     0x10    (bit  4) CasterHasNotMoved -> volet CASTER, PORTE (`get_invalid_caster_reason`) :
    #             le cast est REFUSE si le caster a deja bouge ce tour.
    #     0x4000  (bit 14) TargetIsEnemy     -> PORTE (refus sur un allie / sur soi).
    # PORTEE : `TargetingRange statics+0x30` = `RANGE_ADJACENT` (`onlyAdjacent = RangedBool.True`
    # + `overrideRange = 1`) -> cible ADJACENTE obligatoire, coherent avec `attackRangeType=Melee`.
    # `forceMeleeTarget` = 1 = `RangedBool.False`.
    TARGETING_OPTIONS = TargetingOptions(rules=TR.CasterHasNotMoved | TR.TargetIsEnemy,
                                         self_cast=False, range=RANGE_ADJACENT,
                                         force_melee_target=RANGED_BOOL_FALSE)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        storm_of_flensing_blades_tree().execute(
            entities_from_state(state, caster_id, target_id), ectx)
        attacks = [p for n, p in ectx.emitted if n == "UseActiveAbility"]
        return {"ability": STORM_OF_FLENSING_BLADES_ID, "caster": caster_id, "target": target_id,
                "attacks": attacks, "dsl": True}

# ============================================================================================== #
# PrecisionShot (1015) + PrecisionShot_Aim (1012) -- `necroNpc3Deathmark` (npc Necrons)  #996-r1-r3
# ============================================================================================== #
#
# UN TRIPTYQUE, ET LE GAMECONFIG N'EN DECLARE QU'UN TIERS. Le kit ne porte que
# `activeAbilities: ["PrecisionShot"]` -- pourtant la bataille MONTE les trois soeurs sur le
# porteur (`[69 Loki_NormalAttack, 1015 PrecisionShot, 1012 PrecisionShot_Aim,
# 1013 PrecisionShot_Attack]`, mesure live `probe_996r1_precision_shot.py`). Le seed BC ne porte,
# lui aussi, qu'une seule entree `BC.Abilities.ActiveAbilities["PrecisionShot"]`
# (`variables: {dmg}`, `constants: {nrOfHits: 1, damageProfile: Energy}`).
#
# LES TROIS REGLES DYNAMIQUES DE CASTER, relues au decompile de ce build -- c'est ce qui articule
# le triptyque, et elles s'excluent deux a deux :
#
#   `PrecisionShotAbility$$GetDynamicInvalidCasterReason`
#       HasEffect(caster, 0x3f7 EffectType.PrecisionShot_Aim) ? 0 : 2      # valide EN visee
#   `PrecisionShot_AimAbility$$GetDynamicInvalidCasterReason`
#       HasEffect(caster, 0x3f7)                              ? 2 : 0      # valide HORS visee
#   `PrecisionShot_AttackAbility$$GetDynamicInvalidCasterReason`
#       HasEffect(caster, 0x3f7)                              ? 0 : 4      # valide EN visee
#
# `2` = `TargetingRule.TargetMatchesDynamicRule`, `4` = `TargetingRule.CasterMatchesDynamicRule`.
# ⚠ Le litteral de 1015/1012 est bien `2` -- un code de regle CIBLE rendu par une regle CASTER.
# C'est le natif qui l'ecrit ainsi ; le port le TRANSCRIT au lieu de le << corriger >> en 4.
# Confirmes live (meme probe, avant toute visee) : `abilityReason` 1015 -> `casterReason 0x2`,
# 1012 -> `0x0`, 1013 -> `0x4`.
#
# CE QUE 1015 FAIT -- `...PrecisionShotAbility$$ExecuteBehaviour`, MIRROR :
#
#     AActiveAbility.Execute( entities, this,
#         DSLBehaviors.UseActiveAbility( caster = Caster@DSLSelectors+0x48,
#                                        target = Caster@+0x48,          # <- le CASTER, pas la cible
#                                        activeAbilityType = 0x3f4 = 1012 PrecisionShot_Aim,
#                                        parentAbility = Nullable(AbilityOrEffect(this+0x10)),
#                                        <opts ZERO>, <opts ZERO> ) )
#
# UN SEUL NOEUD, et il ne frappe pas : 1015 DISPATCHE 1012 sur son propre caster. La surcharge est
# celle a `ActiveAbilityType` ENTIER (`180ea6b30`), qui emballe le litteral dans un
# `AbilityTypeSelector.DirectAbilitySelector(AbilityOrEffect(1012))` -- TRANCHEE AUX XREFS
# ENTRANTES, jamais au pseudo-C : les deux surcharges ont sept parametres et le meme nom affiche
# (l'autre, `180ea6a20`, prend un SELECTEUR et sert les 17 call-sites d'attaque normale).
#
# CE QUE 1012 FAIT -- `...PrecisionShot_AimAbility$$ExecuteBehaviour`, MIRROR :
#
#     AActiveAbility.Execute( entities, this,
#         DSLBehaviors.AddEffect( 0x3f7 = 1015 EffectType.PrecisionShot_Aim,
#                                 AActiveAbility.get_AbilityStateReference(this),
#                                 targets = Owner@DSLSelectors+0x30,
#                                 turns   = Nullable(3) )                 # TOURS, pas des rounds
#         op_BitwiseAnd
#         DSLBehaviors.SetActiveAbilityUsed( Owner@+0x30, 0x3f7 = 1015 ActiveAbilityType.PrecisionShot ) )
#
# ⚠ LE MEME ORDINAL `0x3f7` DESIGNE DEUX CHOSES DANS LE MEME ARBRE : l'EFFET `1015
# EffectType.PrecisionShot_Aim` (1er terme) et l'ABILITY `1015 ActiveAbilityType.PrecisionShot`
# (2e terme). Le port les NOMME tous les deux -- ecrire l'entier une fois pour deux roles serait
# exactement la confusion d'enums silencieuse en ordinal que le CLAUDE.md decrit.
#
# La surcharge d'`AddEffect` est celle a QUATRE arguments (`180e9eca0`, xref entrante confirmee),
# dont le corps passe litteralement `source = 0` au `AddEffectBehaviour..ctor` -> la SOURCE de
# l'effet est la CIBLE, pas le caster (`source_from_target=True` cote port). Ici les deux
# coincident (la cible est `Owner`, donc le caster lui-meme) : l'ecart est inerte, on transcrit
# quand meme la forme native.
#
# CE QUE LE PORT NE FAIT PAS ENCORE (residus nommes, cf. `docs/rl/case-996-r1-r3-precisionshot.md`) :
#   * l'ETAGE EFFET de `1015 PrecisionShot_Aim` -- `IdunBattle.Entities.Effects.Loki.
#     PrecisionShot_AimEffect$$BlockMovement` (sous-effet `0x3f8 = 1016
#     EffectType.PrecisionShot_BlockMovement` via `BaseEffect$$AddSubEffectWithSameTurns`) et ses
#     trois `Triggered(<cond>, RemoveEffect)` de `$$CreateHandleTriggerAbilitiesInternal`. La POSE
#     est portee (l'effet se materialise en `BaseEffect`, degradation fidele et VISIBLE) ; sa
#     MECANIQUE ne l'est pas ;
#   * `1013 PrecisionShot_Attack`, dont la config d'ability n'est ni au gameconfig ni au seed BC.

PRECISION_SHOT_ID = "PrecisionShot"

#: Le `Nullable(3)` du 4e argument d'`AddEffect` -- deja en TOURS (le natif ne passe PAS de
#: `TurnsFromRounds` ici, cf. la surcharge 4-args relue ci-dessus).
PRECISION_SHOT_AIM_TURNS = 3


def precision_shot_tree():
    """Arbre de `...PrecisionShotAbility$$ExecuteBehaviour` (MIRROR) : UN noeud, un dispatch.

        UseActiveAbility(Caster@+0x48, Caster@+0x48, 1012 PrecisionShot_Aim)

    `ability_type` NON-NORMAL -> la feuille entre par `AbilityHandler.active_ability_operation`
    (`Core.Services.OperationProcessor$$ActiveAbility`, slot 2), donc le sous-cast rejoue TOUTE la
    chaine d'`ActiveAbilityOperation$$ExecuteInternal` -- gates compris. Cf. la docstring de
    `behaviours/combat.py::UseActiveAbility`."""
    return UseActiveAbility(Caster(), Caster(),
                            ability_type=int(ActiveAbilityType.PrecisionShot_Aim))


def precision_shot_aim_tree():
    """Arbre de `...PrecisionShot_AimAbility$$ExecuteBehaviour` (MIRROR) :

        AddEffect(1015 EffectType.PrecisionShot_Aim, stateRef, Owner@+0x30, Nullable(3) TOURS)
        & SetActiveAbilityUsed(Owner@+0x30, 1015 ActiveAbilityType.PrecisionShot)

    `op_and` = `IdunBattle.DSL.AbilityBehaviour$$op_BitwiseAnd`, le combinateur du natif."""
    return op_and(
        AddEffect(int(EffectType.PrecisionShot_Aim), "PrecisionShot_Aim", Owner(),
                  duration_rounds=None, duration_turns=PRECISION_SHOT_AIM_TURNS,
                  source_from_target=True),
        SetActiveAbilityUsed(Owner(), int(ActiveAbilityType.PrecisionShot)))


class PrecisionShotAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.PrecisionShotAbility$$ExecuteBehaviour`
    (id 1015, `necroNpc3Deathmark` « Deathmark », npc Necrons). Cast SELF-TARGET.

    OBSERVABLE porte : le dispatch de `1012 PrecisionShot_Aim` sur le caster -- donc, quand ce
    sous-cast passe ses propres gates, la pose de l'effet de visee et la consommation de la charge
    de 1015. AUCUNE attaque : ce cast ne frappe pas.

    ⚠ SES DEUX FACES SE REFUSENT MUTUELLEMENT, ET C'EST LE NATIF QUI LE VEUT : 1015 exige l'effet
    de visee (`GetDynamicInvalidCasterReason` -> 0 seulement si `HasEffect`), et 1012 exige son
    ABSENCE. Le port ne tranche RIEN de cette articulation : il pose la regle de chaque classe et
    laisse le sous-cast traverser les memes gates que le natif.

    Flags de tour : defauts base (1015 absent des tables d'override)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.PrecisionShot)            # 0x3f7 = 1015
    ABILITY_ID = PRECISION_SHOT_ID

    # GATE DE CIBLE + PORTEE -- forme de ctor = **PRESET + FLAGS** (le litteral visible n'est PAS le
    # masque). `...PrecisionShotAbility$$.ctor` recopie les 0x40 octets du preset
    # `<TargetingOptions statics>+0x280` puis appelle `TargetingOptions..ctor(&opts, &preset, 0x10)`,
    # dont le corps fait `this+0x28 <- additionalRules | template+0x28`. Le `.cctor` a ete RELU par
    # cette tranche, champ par champ :
    #     +0x280 isSelfCasting    = 1
    #     +0x288 range           <- `TargetingRange statics+0x60` = RANGE_SELF
    #                               (`.cctor` : `+0x60 = 1` onlyAdjacent, `+0x68 = Nullable(0)`)
    #     +0x2a0 forceMeleeTarget = 1 = RangedBool.False
    #     +0x2a8 rules            = 0x8004
    # -> masque effectif = 0x10 | 0x8004 = **0x8014**, decompose EXHAUSTIVEMENT :
    #     0x0004 (bit  2) CasterMatchesDynamicRule -> arme `get_dynamic_invalid_caster_reason`
    #     0x0010 (bit  4) CasterHasNotMoved        -> refus si le caster a deja bouge ce tour
    #     0x8000 (bit 15) CasterIsPossibleTarget   -> le caster entre dans ses propres cibles
    # AUCUN bit de cible : c'est un self-cast. `1012` porte le MEME ctor, au litteral pres -- aucun :
    # les deux corps sont identiques (meme preset, meme `0x10`, meme `AActiveAbility..ctor(.., 2)`).
    TARGETING_OPTIONS = TargetingOptions(rules=(TR.CasterHasNotMoved | TR.CasterMatchesDynamicRule
                                                | TR.CasterIsPossibleTarget),
                                         self_cast=True, range=RANGE_SELF,
                                         force_melee_target=RANGED_BOOL_FALSE)

    def get_dynamic_invalid_caster_reason(self, state: "State", caster_id: int) -> int:
        """`...PrecisionShotAbility$$GetDynamicInvalidCasterReason` -- MIRROR du DECOMPILE :

            r = EntityExtensions.HasEffect(caster, this+0x18, 0x3f7, 0)
            return (char)r != 0 ? 0 : 2

        Soit : le cast n'est LEGAL que si le caster porte DEJA l'effet de visee. `onlyActive = 0`
        au call-site -> `has_effect_of_type` (qui ne filtre que `consumed`), jamais `active_effects`.

        C'est un trou PERMISSIF que ce port ferme : sans cette regle, le port acceptait un cast que
        le natif REFUSE (mesure live : `casterReason 0x2`, `actionConsumed = False`)."""
        if has_effect_of_type(state, int(caster_id), int(EffectType.PrecisionShot_Aim)):
            return 0
        return int(TR.TargetMatchesDynamicRule)                   # le litteral `2` du natif

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        ectx = ExecutionContext(state=state, rng=state.rng)
        precision_shot_tree().execute(entities_from_state(state, caster_id, target_id), ectx)
        casts = [p for n, p in ectx.emitted if n == "UseActiveAbility"]
        return {"ability": PRECISION_SHOT_ID, "caster": caster_id, "target": target_id,
                "dispatched": casts, "dsl": True}


class PrecisionShot_AimAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.PrecisionShot_AimAbility$$ExecuteBehaviour`
    (id 1012). Cast SELF-TARGET, monte sur le porteur de 1015 SANS etre declaree au gameconfig.

    OBSERVABLE porte : l'effet `1015 PrecisionShot_Aim` pose sur le caster pour **3 TOURS**, et la
    charge de `1015 PrecisionShot` consommee (`CanStillBeUsed = false`).

    Flags de tour : defauts base (1012 absent des tables d'override)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.PrecisionShot_Aim)        # 0x3f4 = 1012
    ABILITY_ID = PRECISION_SHOT_ID          # la config d'ability du triptyque est celle du PARENT

    # MEME ctor que 1015, relu independamment : preset `<TargetingOptions statics>+0x280` recopie,
    # puis `TargetingOptions..ctor(&opts, &preset, 0x10)`, puis `AActiveAbility..ctor(this, &opts, 2)`.
    # Les deux corps sont identiques instruction pour instruction -> meme masque effectif 0x8014.
    TARGETING_OPTIONS = TargetingOptions(rules=(TR.CasterHasNotMoved | TR.CasterMatchesDynamicRule
                                                | TR.CasterIsPossibleTarget),
                                         self_cast=True, range=RANGE_SELF,
                                         force_melee_target=RANGED_BOOL_FALSE)

    def get_dynamic_invalid_caster_reason(self, state: "State", caster_id: int) -> int:
        """`...PrecisionShot_AimAbility$$GetDynamicInvalidCasterReason` -- MIRROR du DECOMPILE :

            r = EntityExtensions.HasEffect(caster, this+0x18, 0x3f7, 0)
            return -(uint)((char)r != 0) & 2

        C'est l'INVERSE EXACT de 1015 : viser n'est legal que si l'on ne vise PAS deja. La forme du
        pseudo-C differe (`neg/sbb/and` contre `cmovne`) mais les deux corps rendent le meme jeu de
        valeurs {0, 2} -- seule la CONDITION est inversee, et c'est elle qu'on transcrit."""
        if has_effect_of_type(state, int(caster_id), int(EffectType.PrecisionShot_Aim)):
            return int(TR.TargetMatchesDynamicRule)               # le litteral `2` du natif
        return 0

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        ectx = ExecutionContext(state=state, rng=state.rng)
        precision_shot_aim_tree().execute(entities_from_state(state, caster_id, target_id), ectx)
        posed = [p for n, p in ectx.emitted if n == "AddEffect"]
        used = [p for n, p in ectx.emitted if n == "SetActiveAbilityUsed"]
        return {"ability": PRECISION_SHOT_ID, "caster": caster_id, "target": target_id,
                "aim": posed, "ability_used": used, "dsl": True}
