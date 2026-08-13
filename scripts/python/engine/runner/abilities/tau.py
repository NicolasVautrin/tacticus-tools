"""Abilities actives TAU (namespace natif `IdunBattleLogic.Entities.Abilities.Active.Loki.*`).

Contenu :
- `HeavyRailRifle` (1160, `tauBroadside` -- Tson'ji, MachineOfWar) : ability MoW **2-PHASES** dont le
  behaviour de CAST est une PURE POSE D'EFFETS (aucune attaque, aucun spawn, aucune stat touchee) --
  patron « pose d'effet(s) seule » du lot #90-B (cf. `docs/rl/case-90-mow-effect-posers.md`). Le cast
  ARME la phase 1 ; le degat vient de la phase 2 (`Abilities.Triggered.Loki.HeavyRailRifle_AttackAbility`,
  porte par l'effet `HeavyRailRifle_PendingAttack`) -- HORS de ce port (cf. residus du case doc).
- `TwinSmartMissileSystem` (1161, MEME porteur `tauBroadside`) : patron « ATTAQUE DSL filtree par un
  ETAT + entretien de cet etat » (groupe B du case doc) -- l'attaque ne porte QUE sur les ennemis deja
  MARQUES (`Markerlight` 1122), et le cast (re)pose/rafraichit ce marquage sur sa cible.
- `FightingRetreat` (1081, `tauDarkstrider` -- HERO) : DEBUFF DE ZONE + entretien d'un ETAT de trait +
  pilotage du TURN-FLOW (lot #114 -- cf. `docs/rl/case-114-tau-lot1.md`).
- `EarlyWarningOverride` (1077, `tauCrisis` -- Re'vas, HERO) : SUMMON (2 drones) + auto-armement
  OVERWATCH par pose de 4 effets sur soi (lot #114).
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from .base import (ActiveAbility, convert_rounds_to_turns,
                   turns_until_end_of_current_players_next_turn)
from .behaviours.ability_state import ResetActiveAbility
from .behaviours.combat import AttackWithAttackDamage
from .behaviours.context import entities_from_state
from .behaviours.effects import (ActivateEffect, AddBondEffect, AddEffect,
                                 AddStaticStatModifierEffect, ChangeEffectTurns, CreateShield,
                                 RemoveEffect)
from .behaviours.grants import AddTrait
from .behaviours.movement import Teleport
from .behaviours.stats import (
    AddStatOverrideEffect, Heal, Repair, healable_heal_type_0, repairable_heal_type_1
)
from .behaviours.summon import PerformAIAttack, Spawn
from .behaviours.turnflow import FinishTurn, ResetTurn
from .targeting import (RANGE_ADJACENT, RANGE_FROM_CONFIG, RANGE_SELF, RANGE_WHOLE_BOARD,
                        RANGED_BOOL_FALSE, RANGED_BOOL_TRUE, TargetingOptions,
                        _dynamic_rule_exemplar_of_the_kauyon, _dynamic_rule_forward_observers)
from .targeting_rule import TargetingRule as TR
from ...dsl.base import Const
from ...dsl.effects import ExecutionContext
from ...entities.ability_constant_type import AbilityConstantType
from ...entities.active_ability_type import ActiveAbilityType
from ...entities.behaviours import Foreach, op_add, op_and, If as IfBehaviour
from ...entities.effect_type import EffectType
from ...entities.selectors.accessors import (ActiveTarget, CasterTile, FixedTileIds, Owner,
                                             OwnerTile, Subject, Target)
from ...entities.selectors.geometry import EntitiesWithAnyEffect, Randomize
from ...entities.selectors.tiles import AllAliveUnits, AllTiles, Caster
from ...entities.selectors.units import (
    AdjacentEnemies, AdjacentFriends, Enemies, Filter, Friends, SortByDistance, Sub, Union,
    UnitsThatCanHaveActiveAbilityReset, UnitsWithRangedWeapons, UnitsWithTrait,
    non_steppable_or_object_units
)
from ...entities.unit_selection_type import UnitSelectionType
from ...entities.stats import StatType
from ...entities.traits.unit_trait import UnitTrait
from ...entities.triggers import (AmountIsGreater, HasEffect, HasTrait, IsRepairable, IsTrenchTile,
                                  Not, OwnerIsAlive)
from ...entities.effects.magnitude import ability_var
from ...entities.selectors.geometry import PickFirstN
from ...entities.selectors.tiles import AdjacentTiles, CanAddUnit
from ..components import ActiveAbilitiesComponent, StatsComponent
from ..components import StatsComponent
from ..operations.ability_reset import entity_can_have_active_ability_reset
from .targeting import entity_tiles, get_adjacent_enemies, get_adjacent_friends
from .attack_query import (_has_trait, entity_can_be_healed, entity_can_be_repaired,
                                   health_is_readable)
from .attack_query import get_owned_effect_is_active

if TYPE_CHECKING:
    from ..state import State

HEAVY_RAIL_RIFLE_PENDING_ATTACK = int(EffectType.HeavyRailRifle_PendingAttack)   # 0x535 = 1333
HEAVY_RAIL_RIFLE_PENDING_TARGET = int(EffectType.HeavyRailRifle_PendingTarget)   # 0x536 = 1334
MARKERLIGHT = int(EffectType.Markerlight)                                        # 0x462 = 1122


def heavy_rail_rifle_tree():
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.HeavyRailRifleAbility$$ExecuteBehaviour` -- MIRROR 1:1 du DECOMPILE :

        Execute(   AddEffect(0x536=1334 HeavyRailRifle_PendingTarget, AbilityStateReference,
                             source=caster@0x160, targets=target@0x178, options=ZERO)
                 & AddEffect(0x535=1333 HeavyRailRifle_PendingAttack, AbilityStateReference,
                             source=caster@0x160, targets=caster@0x160,  options=ZERO) )

    DEUX `DSLFactory.AddEffect` combines par `AbilityBehaviour.op_BitwiseAnd`, passes a
    `AActiveAbility.Execute` (PAS `ExecuteAtomic`). AUCUN autre noeud : ni attaque, ni `ChangeStat`,
    ni `Spawn` -- le cast ne fait que MARQUER (la cible) et ARMER (la MoW).

    Les DEUX options-structs sont ZERO-initialisees (`local_178..uStack_160 = 0`) : pas de
    `TurnsFromRounds` -> duree = `DefaultAmountOfRounds` de l'effet. 1333/1334 sont ABSENTS de la table
    `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Effect$$DefaultAmountOfRounds` -> Nullable null -> `remaining = 0` = PERMANENT (l'effet est consomme par la phase 2,
    pas expire par un timer). CONFIRME LIVE : les deux effets sortent a `remaining 0, level 1`."""
    return op_and(
        AddEffect(HEAVY_RAIL_RIFLE_PENDING_TARGET, EffectType.HeavyRailRifle_PendingTarget.name,
                  Target(), duration_rounds=None),
        AddEffect(HEAVY_RAIL_RIFLE_PENDING_ATTACK, EffectType.HeavyRailRifle_PendingAttack.name,
                  Caster(), duration_rounds=None))


class HeavyRailRifleAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.HeavyRailRifleAbility$$ExecuteBehaviour` (id 1160, `tauBroadside` Broadside -- Tau,
    MachineOfWar). Cast UNIT-TARGET (`abilityTargets` kind="unit").

    RE (ghidra gqfc5mff6c) :
    - `IdunBattleLogic.Entities.Abilities.Active.Loki.HeavyRailRifleAbility$$ExecuteBehaviour` : `Execute( AddEffect(0x536, absRef, caster@0x160, target@0x178,
      opts=0) & AddEffect(0x535, absRef, caster@0x160, caster@0x160, opts=0) )` -- cf.
      `heavy_rail_rifle_tree`.
    - `.IdunBattleLogic.Entities.Abilities.Active.Loki.HeavyRailRifleAbility$$.ctor` : `AActiveAbility.ctor(..., TargetingOptions unit-target)`.
    - PHASE 2 (NON PORTEE) : `IdunBattleLogic.Entities.Abilities.Triggered.Loki.HeavyRailRifle_AttackAbility`
      (`IdunBattleLogic.Entities.Abilities.Triggered.Loki.HeavyRailRifle_AttackAbility$$GetFinalUnitDamageAmount`) -- l'attaque differee portee par `HeavyRailRifle_PendingAttack`
      sur la MoW, qui frappe l'unite marquee `HeavyRailRifle_PendingTarget`. Le degat (minDmg/maxDmg,
      profil Piercing, nrOfHits=2, `dmgPctReduction`/`extraDmgPct`) appartient a CETTE phase, pas au cast.

    OBSERVABLE DU CAST (mesure live, runner MoW C1_02, caster 53, cible 49) :
        49    : + HeavyRailRifle_PendingTarget (1334, remaining 0, level 1)
        mow53 : + HeavyRailRifle_PendingAttack (1333, remaining 0, level 1)

    Flags de tour : defauts base (1160 absent des tables d'override `NO_END_TURN_ABILITY_TYPES` /
    `NO_ABILITY_USED_FLAG_ABILITY_TYPES`) -> l'ability termine le tour + pose ActiveAbilityUsed."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.HeavyRailRifle)   # 1160
    ABILITY_ID = "HeavyRailRifle"

    # GATE DE CIBLE (#115) + PORTEE (#241) -- forme de ctor = **FLAGS DIRECTS** (la 1re des trois).
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.HeavyRailRifleAbility$$.ctor` recopie le champ
    # STATIQUE `TargetingRange statics+0x48` dans un local, puis appelle la surcharge « flags
    # directs » de `IdunBattle.Core.Services.TargetingOptions$$.ctor` :
    #     TargetingOptions..ctor(&opts, isSelfCasting=0, range=<TargetingRange statics+0x48>,
    #                            forceMeleeTarget=1, rules=0x10400040004000, 0, 0, 0)
    #     AActiveAbility..ctor(this, &opts, 0, 0)   # 3e arg = 0 = AbilityAttackType.DirectTargetAttack
    # Le litteral EST le masque : ni preset a OR-er (surcharge 2), ni copie de bloc statique
    # (surcharge 3). Layout confirme sur le corps de `TargetingOptions$$.ctor` (`+0x00` isSelfCasting,
    # `+0x08..0x1f` range, `+0x20` forceMeleeTarget, `+0x28` rules, `+0x30/+0x38` les 2 delegues).
    #
    # Decomposition EXHAUSTIVE (`IdunBattle.Core.Services.TargetingRule`, noms VERBATIM du mirror
    # genere) -- 0x4000 + 0x40000000 + 0x400000000000 + 0x10000000000000 = 0x10400040004000, aucun
    # bit residuel :
    #     0x4000            (bit 14) TargetIsEnemy         -> PORTE (refus sur un allie / sur soi ;
    #                       `TargetingQuery$$UnitsCanAttackEachOther`).
    #     0x40000000        (bit 30) AllowNullCasterTile   -> volet CASTER, et c'est un
    #                       ASSOUPLISSEMENT, pas un refus : `TargetingQuery$$GetInvalidCasterReason`
    #                       fait `if (!(rules & bit30) && !(rules & CasterHasNoTile)
    #                       && IsNullOrEmpty(casterTiles)) -> broken(0x40000000)`. Le port ne porte
    #                       PAS cette clause (cf. `get_invalid_caster_reason`), donc le bit est sans
    #                       effet offline -- et il ne peut de toute facon que rendre le natif PLUS
    #                       permissif.
    #     0x400000000000    (bit 46) TargetIsActor         -> regle de DOMAINE, en TETE de la cascade
    #                       (`GetInvalidTargetReason` 7-args) : sans ce bit, `GetUnit(target) == null`
    #                       rompt sur `TargetIsUnit` (bit 45) ; AVEC lui le natif RETOMBE sur
    #                       `GetMachine(target)` et ne rompt (`TargetIsMachine`, bit 44) que si les
    #                       DEUX sont nuls. Autrement dit 1160 peut viser une MACHINE OF WAR ennemie.
    #                       NON PORTE (cf. l'inventaire en tete de `targeting.py`) : le port resout la
    #                       cible par `_unit_of` (UnitComponent) et rend 0 quand elle n'est pas une
    #                       unite -- degradation PERMISSIVE, jamais un refus invente. Residu : sur une
    #                       cible MACHINE le port ne rejoue pas `TargetIsEnemy`.
    #     0x10000000000000  (bit 52) CasterHas2TurnsLeft   -> volet CASTER :
    #                       `if ((rules >> 0x34) & 1 && !<IBattleQuery slot 0x1b>(caster, 2))
    #                        -> broken(0x10000000000000)`.
    #                       `IdunBattle.Core.Services.BattleQuery$$HasMinimumRemainingTurns(unit, n)` =
    #                       `maxRounds = <victoryConfig @+0xb0>.<+0x18>[MainPlayerRoundLimitation]`
    #                       (Nullable) ; **si le match n'a PAS de plafond de rounds -> `true`, donc
    #                       AUCUN refus** ; sinon `n <= maxRounds -
    #                       TurnComponent.GetAmountOfTurnsEndedByPlayer(matchTurn,
    #                       GetPlayerTurnOrder()[0])`.
    #                       **PORTE depuis #287-r11-r1-r1** : le dictionnaire est `BC.Victory.
    #                       VictoryConditions`, que le port lit (`engine.services.victory_config`),
    #                       et le premier bras est donc une LECTURE. Le second bras APPLIQUE la
    #                       formule depuis `#287-r11-r1-r1-r1` : `TurnComponent+0x40` a un substrat
    #                       porte (`State.turns_ended`, ecrit par `turnflow.set_current_player`,
    #                       l'ecrivain natif UNIQUE des deux dictionnaires de tours). Il LEVAIT.
    #                       Coherent avec la mecanique 2-PHASES de l'ability (le degat arrive au tour
    #                       SUIVANT : sans 2 tours restants, armer la phase 1 ne sert a rien).
    # PORTEE : `TargetingRange statics+0x48` = `RANGE_WHOLE_BOARD`
    # (`IdunBattle.Core.Services.TargetingRange$$.cctor` : `+0x48` onlyAdjacent = 1 = `RangedBool.False`,
    # `+0x4c` = 0x100 -> `useRangeFromConfig = false` / **`useWholeBoard = true`**, `+0x50..0x54`
    # overrideRange VIDE, `+0x58` overrideRangeFunc null) -> le filtre statique NE TESTE AUCUNE
    # portee. `forceMeleeTarget` = 1 = `RangedBool.False` (aucun clamp melee).
    TARGETING_OPTIONS = TargetingOptions(
        rules=TR.TargetIsEnemy | TR.AllowNullCasterTile | TR.TargetIsActor | TR.CasterHas2TurnsLeft,
        self_cast=False, range=RANGE_WHOLE_BOARD, force_melee_target=RANGED_BOOL_FALSE)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        entities = entities_from_state(state, caster_id, target_id)
        ectx = ExecutionContext(state=state, rng=state.rng)
        heavy_rail_rifle_tree().execute(entities, ectx)
        posed = [{"target": p["target"], "effect": p["effect_type"]}
                 for n, p in ectx.emitted if n == "AddEffect"]
        return {"posed": posed, "dsl": True}


# ============ TwinSmartMissileSystem (tauBroadside, MACHINE OF WAR, actif 1161) ============
#
# `IdunBattleLogic.Entities.Abilities.Active.Loki.TwinSmartMissileSystemAbility$$ExecuteBehaviour`
# (MIRROR du DECOMPILE) :
#
#   targets = EntitiesWithAnyEffect( Enemies(<dsl>+0x48 = Caster, <dsl>+0x20 = AllAliveUnits, 3),
#                                    0x462 = Markerlight )
#             (== `IdunBattleLogic.Entities.Abilities.Active.Loki.TwinSmartMissileSystemAbility$$GetAttackTargets`,
#              fonction NOMMEE dont le corps est REPRIS INLINE par ExecuteBehaviour)
#   attack  = AttackWithAbilityDamage( caster@0x160, targets,
#                                      MinMaxDamage(this, entities),           # minDmg/maxDmg[level]
#                                      Direct(Nullable(GetDamageProfile()))=Blast,
#                                      ConfigConst(0x2f)=nrOfHits=3,
#                                      AbilityOrEffect(this+0x10 = 0x489 = 1161) )
#   turns   = TurnsFromRounds(2)
#   refresh = If( HasEffect(target@0x178, 0x462, minLevel 0, source-flag 6),
#                 ChangeEffectTurns(target@0x178, 0x462, turns, ChangeType 0 = Add),
#                 AddEffect(0x462, AbilityStateReference, source=caster@0x160, target@0x178, turns) )
#   AActiveAbility.ExecuteAtomic( attack op_BitwiseAnd refresh, entities, 0x2a )
#
# NOTES DE FIDELITE :
#  - `ChangeType` = `IdunBattle.Entities.Enum.ChangeType` : **0 = Add**, 1 = Set (`IdunBattle.Core.Services.BattleQuery$$GetAmount`
#    lu au decompile). Le call-site passe 0 -> la duree est AJOUTEE a la duree restante (pas un SET).
#  - `TurnsFromRounds(2)` est evalue UNE fois et sert AUX DEUX branches (meme noeud `uVar12`).
#  - l'attaque route la factory `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAbilityDamage`
#    -> `AbilityDamageOperation.ExecuteHits` (1 tirage/coup, pas de crit) == Stormcaller/EntropyCannons
#    -> `native_factory="ability"` cote port (classification par XREF, jamais au juge).
#  - `ExecuteAtomic(..., 0x2a)` = groupe atomique de presentation (meme flag que JakhalStimms) : aucun
#    effet sur l'etat porte (les Operations sont deja appliquees en sequence).

TWIN_SMART_MISSILE_SYSTEM_ID = "TwinSmartMissileSystem"


def twin_smart_missile_system_attack_targets() -> EntitiesWithAnyEffect:
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.TwinSmartMissileSystemAbility$$GetAttackTargets`
    (MIRROR) = `EntitiesWithAnyEffect(Enemies(<dsl>+0x48, <dsl>+0x20, 3), 0x462 Markerlight)`.

    `<dsl>+0x20` = le selecteur PARTAGE `IdunBattle.Entities.Selectors.AllAliveUnitsSelector` pose par
    `IdunBattleLogic.Entities.DSLSelectors$$InitializeShared` (slot `IBattleQuery` 137
    `GetAllAliveUnits`, pool `EntityPool.AliveUnits`) -> `AllAliveUnits()` cote port -- meme source que
    Waaagh/Stormcaller/RadBombardment. Ce N'EST PAS `DSLSelectors$$AllUnits` (pool 8, morts inclus),
    et ce n'est pas non plus `AllAliveMachines` (pool 6) : #514. AUCUN rayon : l'ability frappe TOUT
    ennemi marque du plateau."""
    return EntitiesWithAnyEffect(Enemies(AllAliveUnits()), [MARKERLIGHT])


def twin_smart_missile_system_tree(state: "State"):
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.TwinSmartMissileSystemAbility$$ExecuteBehaviour`
    (MIRROR 1:1, cf. le bloc de commentaire ci-dessus) :

        op_BitwiseAnd( AttackWithAbilityDamage(<ennemis marques>),
                       If(HasEffect(cible, Markerlight), ChangeEffectTurns(+2 rounds),
                                                         AddEffect(Markerlight, 2 rounds)) )

    `TurnsFromRounds(2)` est CALCULE ICI (`convert_rounds_to_turns`, mirror
    `IdunBattle.Core.Services.BattleQuery$$ConvertRoundsToTurns`) parce que les deux consommateurs en ont
    besoin sous des formes differentes : `AddEffect` prend une duree DEJA en tours (`duration_turns`),
    `ChangeEffectTurns` prend le MONTANT a ajouter -- c'est le MEME scalaire natif."""
    turns = convert_rounds_to_turns(state, 2)             # noeud `TurnsFromRounds(2)`, evalue une fois
    attack = AttackWithAttackDamage(twin_smart_missile_system_attack_targets(),
                                    TWIN_SMART_MISSILE_SYSTEM_ID, "Blast", is_melee=False, multi=True,
                                    native_factory="ability",
                                    ability_type=int(ActiveAbilityType.TwinSmartMissileSystem))
    refresh = IfBehaviour(
        HasEffect(Target(), MARKERLIGHT),
        ChangeEffectTurns(Target(), MARKERLIGHT, turns, change_type=0),     # ChangeType.Add
        AddEffect(MARKERLIGHT, EffectType.Markerlight.name, Target(), duration_turns=turns))
    return op_and(attack, refresh)


class TwinSmartMissileSystemAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.TwinSmartMissileSystemAbility$$ExecuteBehaviour`
    (id 1161, `tauBroadside` Broadside -- Tau, MachineOfWar). Cast UNIT-TARGET.

    Kit gameconfig 1161 : `damageProfile=Blast`, `nrOfHits=3`, `minDmg`/`maxDmg`[level] (rarity-affected),
    `attackRangeType=Ranged`, `initialCooldownTurns=0`.

    OBSERVABLE : (1) 3 coups Blast famille ABILITY sur CHAQUE ennemi porteur de `Markerlight` (1122) --
    ensemble VIDE tant que personne n'est marque, donc le 1er cast d'un runner frais ne fait AUCUN degat ;
    (2) marquage de la cible : pose `Markerlight` (duree = `ConvertRoundsToTurns(2)`) si absente, sinon
    AJOUT de cette meme duree a la duree restante.

    Flags de tour : defauts base (1161 absent des tables d'override) -> termine le tour + ActiveAbilityUsed."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.TwinSmartMissileSystem)   # 1161
    ABILITY_ID = TWIN_SMART_MISSILE_SYSTEM_ID

    # GATE DE CIBLE (#115) + PORTEE (#241) -- forme de ctor = **FLAGS DIRECTS**.
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.TwinSmartMissileSystemAbility$$.ctor` :
    #     TargetingOptions..ctor(&opts, isSelfCasting=0, range=<TargetingRange statics+0x48>,
    #                            forceMeleeTarget=1, rules=0x40004000, 0, 0, 0)
    #     AActiveAbility..ctor(this, &opts, 0, 0)   # 0 = AbilityAttackType.DirectTargetAttack
    #
    # MEME PORTEUR, MEME FORME DE CTOR QUE 1160 -- ET UN MASQUE DIFFERENT : les DEUX bits que 1160
    # porte en plus (46 `TargetIsActor`, 52 `CasterHas2TurnsLeft`) sont ABSENTS ici. Deux abilities
    # de la MEME machine, lues separement : recopier la voisine aurait donne un masque FAUX dans les
    # deux sens (une cible MACHINE serait acceptee a tort, un plafond de tours refuserait a tort).
    #
    # Decomposition EXHAUSTIVE -- 0x4000 + 0x40000000 = 0x40004000, aucun bit residuel :
    #     0x4000      (bit 14) TargetIsEnemy       -> PORTE (refus sur un allie / sur soi).
    #     0x40000000  (bit 30) AllowNullCasterTile -> volet CASTER, ASSOUPLISSEMENT (cf. 1160) ;
    #                 la clause qu'il desarme n'est pas portee -> sans effet offline.
    # Sans le bit 46, le natif exige que la cible resolve en UNITE : `GetUnit(target) == null` rompt
    # sur `TargetIsUnit` (bit 45, non gate par un flag, non porte -> permissif cote port).
    # PORTEE : `TargetingRange statics+0x48` = `RANGE_WHOLE_BOARD` -> aucun test de portee, ce qui
    # est coherent avec `GetAttackTargets` (l'attaque frappe TOUT ennemi marque du plateau, sans
    # rayon). `forceMeleeTarget` = 1 = `RangedBool.False`.
    TARGETING_OPTIONS = TargetingOptions(rules=TR.TargetIsEnemy | TR.AllowNullCasterTile,
                                         self_cast=False, range=RANGE_WHOLE_BOARD,
                                         force_melee_target=RANGED_BOOL_FALSE)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        twin_smart_missile_system_tree(state).execute(
            entities_from_state(state, caster_id, target_id), ectx)
        attacks = [{"target": p.get("target"), "total": p.get("total")}
                   for n, p in ectx.emitted if n == "AttackWithAttackDamage"]
        marked = [{"target": p.get("target"), "effect": p.get("effect_type")}
                  for n, p in ectx.emitted if n == "AddEffect"]
        refreshed = [{"owner": p.get("owner"), "remaining": p.get("remaining")}
                     for n, p in ectx.emitted if n == "ChangeEffectTurns"]
        return {"ability": TWIN_SMART_MISSILE_SYSTEM_ID, "caster": caster_id, "target": target_id,
                "attacks": attacks, "marked": marked, "refreshed": refreshed, "dsl": True}


# ==================== FightingRetreat (tauDarkstrider, HERO, actif 1081) -- lot #114 ====================
#
# `IdunBattleLogic.Entities.Abilities.Active.Loki.FightingRetreatAbility$$ExecuteBehaviour`
# (MIRROR 1:1 du DECOMPILE, 5 volets joints par `AbilityBehaviour.op_Addition`) :
#
#   adjEnemies = NonSteppableOrObjectUnits( AdjacentEnemies(Owner@0x148, 1, 3), 3 )
#   adjFriends = NonSteppableOrObjectUnits( AdjacentFriends(Owner@0x148, 1, 3), 3 )
#   turns      = TurnsUntilEndOfCurrentPlayersNextTurn()
#   n          = adjEnemies.Count(entities)          # virtuel slot 0x18, EVALUE A LA CONSTRUCTION
#
#   AActiveAbility.Execute(
#         AddEffect(0x485 = 1157 FightingRetreatDmgReduction, absRef, source=Owner@0x148,
#                   targets=adjEnemies, turns)
#       + AddEffect(0x486 = 1158 FightingRetreatHitReduction, absRef, source=Owner@0x148,
#                   targets=adjEnemies, turns)
#       + Foreach( adjEnemies,
#                  AddEffect(0x462 = 1122 Markerlight, absRef, source=caster@0x160,
#                            targets=subject@0x180, turns) )
#       + Foreach( adjFriends op_Addition caster@0x160,
#                  If( HasTrait(subject@0x180, 0x424 = 1060 RangedSpecialist),
#                      ActivateEffect( EffectFromOwner(subject@0x180, 0x5eb = 1515 RangedSpecialist) ) ) )
#       + If( AmountIsGreater(Direct(n), Direct(0)),
#             ResetTurn(Owner@0x148, 1),
#             FinishTurn(Owner@0x148) ),
#       entities )
#
# NOTES DE FIDELITE :
#  - `NonSteppableOrObjectUnits(sel, 3)` = `(sel & UnitsWithoutTrait(sel, 0x1b=Steppable)) &
#    UnitsWithoutTrait(sel, 0xd=Object)` (`IdunBattleLogic.Entities.DSLSelectors$$NonSteppableOrObjectUnits`,
#    decompile) -> un decoy/objet adjacent n'est NI debuffe NI marque. Helper deja porte (partage avec
#    les predicats de ciblage de SquigLaunchas).
#  - `TurnsUntilEndOfCurrentPlayersNextTurn` = `Sum(TurnsFromRounds(1), Direct(1))` (cf.
#    `abilities/base.py`, ground truth live anvil_shield `remaining 3`). i2 : « for one round ».
#  - Le COMPTE d'ennemis adjacents est fige a la CONSTRUCTION de l'arbre (`Direct(n)`), pas relu a
#    l'execution -- aucun observable different (la pose d'effets ne change pas l'adjacence), mais le port
#    respecte la structure (compte calcule dans le builder, injecte en `Const`).
#  - Les DEUX faces turn-flag (`SetsEndTurnFlags`/`SetsActiveAbilityUsedFlag`) sont DEJA portees (#139,
#    `_fighting_retreat_sets_flags` : les flags ne sont poses QUE si AUCUN ennemi adjacent) -- c'est le
#    MEME predicat que le `If` du 5e volet, mais un canal DISTINCT (queue `AddFlagsAfterAbilityExecution`
#    de `ActiveAbilityOperation`, hors behaviour). Les deux convergent : ennemi adjacent -> ResetTurn +
#    aucun flag ; aucun ennemi adjacent -> FinishTurn + flags poses.
#  - CAST LEGAL (`IdunBattleLogic.Entities.Abilities.Active.Loki.FightingRetreatAbility$$GetDynamicInvalidTargetReason`,
#    PORTE depuis #247 -- gate AMONT) : le cast est REFUSE (reason 2) sauf si le caster a >=1 ennemi
#    adjacent OU si un allie adjacent a un `RangedSpecialist` DESACTIVE
#    (`FightingRetreatAbility$$HasDeactivatedRangedSpecialist`). Le predicat du 1er disjunct compte les
#    `Steppable` (`ignoreSteppables = false`), la ou l'ExecuteBehaviour ci-dessus les EXCLUT
#    (`NonSteppableOrObjectUnits`) : les deux volets ne comptent pas le meme ensemble.

FIGHTING_RETREAT_ID = "FightingRetreat"
FIGHTING_RETREAT_DMG_REDUCTION = int(EffectType.FightingRetreatDmgReduction)   # 0x485 = 1157
FIGHTING_RETREAT_HIT_REDUCTION = int(EffectType.FightingRetreatHitReduction)   # 0x486 = 1158
RANGED_SPECIALIST_EFFECT = int(EffectType.RangedSpecialist)                    # 0x5eb = 1515
RANGED_SPECIALIST_TRAIT = int(UnitTrait.RangedSpecialist)                      # 0x424 = 1060


def fighting_retreat_adjacent_enemies():
    """`NonSteppableOrObjectUnits(AdjacentEnemies(Owner@0x148, 1, 3), 3)` (MIRROR) -- les ennemis
    STRICTEMENT adjacents au caster, decoys (`Steppable` 27) et objets (`Object` 13) EXCLUS.
    L'ancre est `OwnerTile()` = la position LIVE de l'owner (le port ancre `AdjacentEnemies` sur une
    POSITION ; `OwnerTile` mirror `Owner@0x148`, PAS la tuile d'attaque balayee `CasterTile`)."""
    return non_steppable_or_object_units(AdjacentEnemies(OwnerTile()))


def fighting_retreat_adjacent_friends():
    """`NonSteppableOrObjectUnits(AdjacentFriends(Owner@0x148, 1, 3), 3)` (MIRROR) -- symetrique allie.
    `AdjacentFriends` natif EXCLUT deja le caster (anneau `d>0`) ; le 4e volet le re-AJOUTE explicitement
    par `op_Addition(adjFriends, caster@0x160)`."""
    return non_steppable_or_object_units(AdjacentFriends(OwnerTile()))


def _has_deactivated_ranged_specialist(state: "State", unit_id) -> bool:
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.FightingRetreatAbility$$HasDeactivatedRangedSpecialist`
    -- MIRROR du decompile (le predicat du `Enumerable.Any(adjFriends, ...)` de la regle dynamique) :

        effect = EntityExtensions.GetOwnedEffect(unit, state, 0x5eb RangedSpecialist);
        if (effect == null) return false;
        return effect.EffectComponent.IsActive@+0x5c == 0;

    Nativement l'entite-effet 1515 EXISTE en permanence sur tout porteur du trait
    `RangedSpecialist` (1060) -- `StaticBattleRules.Trait$$GetEffectToBeAddedToOwnerForTrait`, pose
    par `InitializeActorAbilitiesOperation$$Execute` a la creation de l'unite. Seul son FLAG bascule
    (`RangedSpecialistEffect$$CreateHandleTriggerAbilitiesInternal` : `If(HasAdjacentEnemies,
    DeactivateEffect, ActivateEffect)` sur `On(0x12)` = turn-start). « Effet absent » et « effet
    desactive » sont donc DEUX etats natifs distincts, et seul le second rend `true`.

    Cote port, le canal de seed DROPPE les instances `IsActive == 0` (case-160, prouve live :
    `readEffectsByUnit` fait `if (!info.active || info.removed) continue`) -- la distinction est
    reconstruite par `attack_query.get_owned_effect_is_active(..., has_trait_effect_source=1060)`,
    qui rend le TERNAIRE natif : `None` = pas porteur du trait (pas d'entite-effet), `True` = effet
    present et actif, `False` = trait porte mais instance absente du seed = DESACTIVEE."""
    return get_owned_effect_is_active(state, unit_id, RANGED_SPECIALIST_EFFECT,
                                      has_trait_effect_source=RANGED_SPECIALIST_TRAIT) is False


def fighting_retreat_tree(state: "State", n_adjacent_enemies: int):
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.FightingRetreatAbility$$ExecuteBehaviour`
    (MIRROR 1:1, cf. le bloc de commentaire ci-dessus). `n_adjacent_enemies` = le `Direct(n)` natif
    (`adjEnemies.Count(entities)` evalue A LA CONSTRUCTION)."""
    adj_enemies = fighting_retreat_adjacent_enemies()
    adj_friends = fighting_retreat_adjacent_friends()
    turns = turns_until_end_of_current_players_next_turn(state)      # Sum(TurnsFromRounds(1), Direct(1))
    debuffs = op_add(
        AddEffect(FIGHTING_RETREAT_DMG_REDUCTION, EffectType.FightingRetreatDmgReduction.name,
                  adj_enemies, duration_turns=turns),
        AddEffect(FIGHTING_RETREAT_HIT_REDUCTION, EffectType.FightingRetreatHitReduction.name,
                  adj_enemies, duration_turns=turns))
    marking = Foreach(adj_enemies,
                      AddEffect(MARKERLIGHT, EffectType.Markerlight.name, Subject(),
                                duration_turns=turns))
    # 4e volet : re-ACTIVE le RangedSpecialist du caster ET de ses allies adjacents qui portent le trait
    # (i2 : « gain the effect of the trait even if they started their turn adjacent to an enemy unit »).
    reactivate = Foreach(
        Union(adj_friends, Caster()),
        IfBehaviour(HasTrait(Subject(), RANGED_SPECIALIST_TRAIT),
                    ActivateEffect(Subject(), RANGED_SPECIALIST_EFFECT,
                                   EffectType.RangedSpecialist.name)))
    # 5e volet : TURN-FLOW. Ennemi adjacent -> le tour de Darkstrider est ROUVERT (il peut re-bouger) ;
    # sinon son tour est CLOS.
    turn_flow = IfBehaviour(AmountIsGreater(Const(int(n_adjacent_enemies)), Const(0)),
                            ResetTurn(Caster(), True),
                            FinishTurn(Caster()))
    return op_add(op_add(op_add(debuffs, marking), reactivate), turn_flow)


class FightingRetreatAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.FightingRetreatAbility$$ExecuteBehaviour`
    (id 1081, `tauDarkstrider` Darkstrider -- Tau, HERO). Cast SELF (targeting `TargetingOptions(1, ...,
    1, 0x802)` -- `abilityTargets` rend le caster lui-meme).

    Kit gameconfig 1081 : `hitsReduction=1` (constante consommee par
    `FightingRetreat_HitReductionEffect$$CreateEffectHitsBonusForAttack`), `dmgReduction`[level]
    (rarity-affected, lvl65=582 -- consomme par `FightingRetreat_DamageReductionEffect$$
    CreateEffectDamageBonusForAttack`). AUCUN volet degat, AUCUN spawn.

    OBSERVABLE du cast : (1) chaque ennemi adjacent (hors Steppable/Object) recoit TROIS effets --
    1157 FightingRetreatDmgReduction, 1158 FightingRetreatHitReduction, 1122 Markerlight -- de duree
    `TurnsUntilEndOfCurrentPlayersNextTurn` ; (2) Darkstrider et ses allies adjacents porteurs du trait
    `RangedSpecialist` voient leur effet 1515 (RE)ACTIVE ; (3) si >=1 ennemi adjacent, le tour de
    Darkstrider est ROUVERT (`ResetTurn` : flags Moved/ActiveAbilityUsed/TurnFinished retires), sinon il
    est CLOS (`FinishTurn`).

    Flags de tour : override CONDITIONNEL (#139) -- `SetsActiveAbilityUsedFlag = Direct(!Any(<ennemis
    adjacents>))` (decompile) ; le handler l'applique deja via `_fighting_retreat_sets_flags`.

    Retour : {posed, activated, turn_flow, adjacent_enemies, turns, dsl}."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.FightingRetreat)   # 1081
    ABILITY_ID = FIGHTING_RETREAT_ID

    # GATE DE CIBLE (#115) + PORTEE (#241) -- forme de ctor = **FLAGS DIRECTS**.
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.FightingRetreatAbility$$.ctor` :
    #     TargetingOptions..ctor(&opts, isSelfCasting=1, range=<TargetingRange statics+0x30>,
    #                            forceMeleeTarget=1, rules=0x802, 0, 0, 0)
    #     AActiveAbility..ctor(this, &opts, 2, 0)   # 2 = AbilityAttackType.Others
    #
    # Decomposition EXHAUSTIVE -- 0x2 + 0x800 = 0x802, aucun bit residuel :
    #     0x2    (bit  1) TargetMatchesDynamicRule    -> POINT D'EXTENSION : le filtre statique
    #            invoque le delegue `options+0x38` (= le slot vtable `+0x480`, ici
    #            `...FightingRetreatAbility$$GetDynamicInvalidTargetReason`). Son corps ne lit QUE le
    #            CASTER (`param_2`) : il rend `2` si le caster n'a NI ennemi adjacent
    #            (`battleQuery.<slot 0x7d> GetAdjacentEnemies`) NI allie adjacent porteur d'un
    #            `RangedSpecialist` DESACTIVE (`<slot 0x80> GetAdjacentFriends` + le predicat
    #            `FightingRetreatAbility$$HasDeactivatedRangedSpecialist`), sinon `0`.
    #            PORTE depuis #247 -- cf. `get_dynamic_invalid_target_reason` ci-dessous.
    #     0x800  (bit 11) AddCasterIfAtLeastOneTarget -> N'EST PAS une regle du filtre statique : il
    #            n'est lu que par `IdunBattle.Core.Services.TargetingQuery$$GetCasterNotAddedReason`,
    #            la branche que prend le natif quand une ability `isSelfCasting != 0` est castee SUR
    #            SON PROPRE CASTER. Pour 0x802 le decompile y prend le dernier `else` :
    #            `GetValidTargets(caster, tiles, options, 1, 1).AllTargets.Count == 0 -> broken(0x800)`.
    #            `GetValidTargets` (enumeration complete du plateau) n'est PAS portee -> le port rend
    #            0 (`get_caster_not_added_reason`), degradation PERMISSIVE deja documentee.
    # C'est donc le VOLET PORTEE qui mord offline : `TargetingRange statics+0x30` = `RANGE_ADJACENT`
    # (`TargetingRange$$.cctor` : `+0x30` onlyAdjacent = 0 = `RangedBool.True`, `+0x38` overrideRange
    # = `Nullable(1)`, `+0x40` func null) -> branche `battleQuery.AreEntitiesAdjacent(casterTiles,
    # target)`, toute cible hors contact rompt sur `TargetIsInRange`. `forceMeleeTarget` = 1 =
    # `RangedBool.False` (la portee EST deja l'adjacence).
    # AUCUNE regle de CAMP (ni `TargetIsFriendly` ni `TargetIsCaster`) -> `refuses_all_enemy_targets`
    # reste `False` : poser ce masque ne deplace AUCUN routage d'action cote IA.
    TARGETING_OPTIONS = TargetingOptions(
        rules=TR.TargetMatchesDynamicRule | TR.AddCasterIfAtLeastOneTarget,
        self_cast=True, range=RANGE_ADJACENT, force_melee_target=RANGED_BOOL_FALSE)

    def get_dynamic_invalid_target_reason(self, state: "State", caster_id: int,
                                          target_id: Optional[int]) -> int:
        """`IdunBattleLogic.Entities.Abilities.Active.Loki.FightingRetreatAbility$$GetDynamicInvalidTargetReason`
        -- MIRROR 1:1 du decompile. La signature native est celle du delegue
        `TargetingOptions.DynamicTargetingTargetRule` (`caster, casterTiles, target, targetTiles`) ;
        ce corps-ci **n'en lit QUE `caster` (`param_2` = RDX)** -- il ne touche jamais la cible :

            owner      = OwnerComponent.GetCurrentPlayerEntityId(caster.OwnerComponent);
            adjEnemies = battleQuery.<slot 0x7d> GetAdjacentEnemies(caster, owner, false);
            adjFriends = battleQuery.<slot 0x81> GetAdjacentFriends(caster, owner);
            if (Enumerable.Any(adjEnemies))                                   return 0;
            if (Enumerable.Any(adjFriends, this.HasDeactivatedRangedSpecialist)) return 0;
            return 2;                       // == TargetingRule.TargetMatchesDynamicRule

        CONSEQUENCE DE STRUCTURE : la regle est INDEPENDANTE de la cible, donc pour un caster donne
        elle refuse TOUTES les cibles ou AUCUNE. Elle n'est atteinte que par les lignes qui ont deja
        passe le volet PORTEE (`RANGE_ADJACENT`), et jamais par la ligne « cible == caster » (1081
        est `isSelfCasting`, l'overload 5 arguments l'aiguille sur `GetCasterNotAddedReason`). C'est
        pourquoi elle etait restee INERTE sur les montages de #250 : Darkstrider y avait un ennemi
        adjacent, donc le 1er `Any` court-circuitait.

        `ignoreSteppables = false` (3e argument du slot 0x7c, LU) : un decoy `Steppable` ennemi au
        contact SUFFIT a autoriser le cast -- contraste voulu avec l'`ExecuteBehaviour`, qui lui
        filtre par `NonSteppableOrObjectUnits`. Les deux volets ne comptent PAS la meme chose.

        ⚠ GARDE-FOU (sans lequel ce port INVENTE des refus) : cette regle refuse sur une LISTE VIDE.
        Or `get_adjacent_enemies` / `get_adjacent_friends` rendent aussi la liste vide quand le port
        ne SAIT PAS enumerer l'adjacence (pas de `state.board`, caster sans tuile). « Vide » y
        signifie alors « inconnu », pas « aucun ennemi » -- on rend donc 0 dans ce cas, comme partout
        ailleurs dans le gate. MESURE offline (`State()` nu) : sans cette garde le port rendait
        `0x2` sur un etat ou il n'avait rien lu."""
        tiles = entity_tiles(state, caster_id)
        if state.board is None or not tiles:
            return 0                     # adjacence NON ENUMERABLE -> aucun refus invente
        if get_adjacent_enemies(state, tiles, caster_id):        # `Any(adjEnemies)`
            return 0
        for ally in get_adjacent_friends(state, tiles, caster_id):
            if _has_deactivated_ranged_specialist(state, ally.id):
                return 0
        return int(TR.TargetMatchesDynamicRule)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        entities = entities_from_state(state, caster_id, target_id)
        # `adjEnemies.Count(entities)` (virtuel slot 0x18) -> `Direct(n)`, evalue A LA CONSTRUCTION de
        # l'arbre par le natif (avant tout Execute) : on le calcule donc ICI, pas dans une feuille.
        n_adj = len(fighting_retreat_adjacent_enemies().evaluate(entities) or [])
        ectx = ExecutionContext(state=state, rng=state.rng)
        fighting_retreat_tree(state, n_adj).execute(entities, ectx)
        posed = [{"target": p.get("target"), "effect": p.get("effect_type"),
                  "placed": p.get("placed")} for n, p in ectx.emitted if n == "AddEffect"]
        activated = [{"owner": p.get("owner"), "created": p.get("created")}
                     for n, p in ectx.emitted if n == "ActivateEffect"]
        flow = [{"op": n, **p} for n, p in ectx.emitted if n in ("ResetTurn", "FinishTurn")]
        return {"ability": FIGHTING_RETREAT_ID, "posed": posed, "activated": activated,
                "turn_flow": flow, "adjacent_enemies": n_adj,
                "turns": turns_until_end_of_current_players_next_turn(state), "dsl": True}


# ================ EarlyWarningOverride (tauCrisis Re'vas, HERO, actif 1077) -- lot #114 ================
#
# `IdunBattleLogic.Entities.Abilities.Active.Loki.EarlyWarningOverrideAbility$$ExecuteBehaviour`
# (MIRROR 1:1 du DECOMPILE) :
#
#   unitId      = GetStringConstant(config@0x60, 0)                  # = tauSmnDroneShield
#   nrOfSummons = GetNumberConstant(config@0x60, 0x10)               # = 2
#   opts        = SpawnUnitOptions.WithStatsFromConfig(config@0x60, entities)
#   opts+0x18   = PerformAIAttackFromCurrentPosition(ActiveTarget@0x180, 0, 0, false)   # on-appearance
#   tiles       = First( SortTilesByUtilityForSummon( CanAddUnit(AdjacentTiles(Owner@0x148)),
#                                                     TestUnitProvider(UtilityBucket(WeightedUtility 7,
#                                                                                    WeightedUtility 0x38)),
#                                                     Owner@0x148 ),
#                        Direct(nrOfSummons) )
#   turns       = TurnsFromRounds(1)
#   snapshot    = CreateSnapshot(entities)                           # AbilityStateReference fige
#
#   AActiveAbility.Execute(
#         Nothing()
#       + AddEffect(0x3f1 = 1009 Overwatch_AutoAttack,                     snapshot, Owner@0x148, turns)
#       + AddEffect(0x478 = 1144 SuppressCloseCombatWeakness,              snapshot, Owner@0x148, turns)
#       + AddEffect(0x479 = 1145 EarlyWarningOverride_ReactivateOverwatch, snapshot, Owner@0x148, turns)
#       + AddEffect(0x47d = 1149 EarlyWarningOverride_Visual,              snapshot, Owner@0x148, turns)
#       + Spawn(Owner@0x148, tiles, unitId, opts),
#       entities )
#
# NOTES DE FIDELITE :
#  - `Nothing()` (`IdunBattleLogic.Entities.DSLBehaviors$$Nothing`) = feuille NEUTRE en tete du `op_Addition` :
#    aucun etat, aucun tirage -> NON materialisee (l'arbre porte demarre au 1er `AddEffect`).
#  - ORDRE natif : les 4 effets AVANT le spawn. Le spawn ne consomme aucun rng ; l'attaque on-appearance
#    des drones, SI. Conserver l'ordre garde la sequence rng fidele.
#  - `SortTilesByUtilityForSummon` (moteur d'utilite IA COMPLET, kind S lourd) est COLLAPSE (doctrine
#    slice-18/19, meme classe que ForwardSpotter/SendInTheNextWave) : on conserve l'ORDRE DU SELECTEUR
#    (`CanAddUnit(AdjacentTiles(caster))`, voisinage natif `board.neighbours`). RESIDU EXPLICITE : quand
#    il y a plus de tuiles libres que `nrOfSummons`, la TUILE choisie peut differer du live ; le POOL et
#    le CARDINAL sont exacts.
#  - `Overwatch_AutoAttack` (1009) est un EFFET-TRIGGER DEJA PORTE (`OverwatchAutoAttack`,
#    `operations/triggers/effect_triggers.py`) : le poser rend Re'vas REELLEMENT overwatchante offline
#    (auto-attaque `On(4)` = after-move d'un ennemi en portee).
#  - 1144/1145/1149 n'ont PAS de classe d'effet portee -> `BaseEffect` inerte (presence fidele, semantique
#    non modelisee) : 1145 = re-entree en overwatch apres un kill avec `hitsReduction=1` (phase 2, effet
#    `EarlyWarningOverride_ReactivateOverwatchEffect`, HORS de ce port) ; 1149 = VISUEL pur.
#  - `SetsActiveAbilityUsedFlag` overridee (#139, 1077 dans `NO_ABILITY_USED_FLAG_ABILITY_TYPES`) ;
#    `SetsEndTurnFlags` = defaut -> l'ability TERMINE le tour de Re'vas.

EARLY_WARNING_OVERRIDE_ID = "EarlyWarningOverride"
EWO_EFFECTS = (
    (int(EffectType.Overwatch_AutoAttack), EffectType.Overwatch_AutoAttack.name),                    # 0x3f1
    (int(EffectType.SuppressCloseCombatWeakness), EffectType.SuppressCloseCombatWeakness.name),      # 0x478
    (int(EffectType.EarlyWarningOverride_ReactivateOverwatch),
     EffectType.EarlyWarningOverride_ReactivateOverwatch.name),                                      # 0x479
    (int(EffectType.EarlyWarningOverride_Visual), EffectType.EarlyWarningOverride_Visual.name),      # 0x47d
)


def early_warning_override_num_summons() -> int:
    """`GetNumberConstant(config, 0x10)` = `nrOfSummons` (CONSTANTE, hors niveau) de 1077 -- = 2."""
    import gameconfig as GC
    consts = (GC.ability(EARLY_WARNING_OVERRIDE_ID) or {}).get("constants") or {}
    return int(consts.get("nrOfSummons") or 0)


def early_warning_override_tree(state: "State", tiles: list):
    """Arbre de
    `IdunBattleLogic.Entities.Abilities.Active.Loki.EarlyWarningOverrideAbility$$ExecuteBehaviour`
    (MIRROR 1:1, cf. le bloc ci-dessus) : les 4 `AddEffect(Owner, TurnsFromRounds(1))` puis le `Spawn`
    dont les options portent le sous-behaviour on-appearance `PerformAIAttackFromCurrentPosition
    (ActiveTarget@0x180)`. `tiles` = le COLLAPSE du tile-selecteur (ids deja resolus)."""
    turns = convert_rounds_to_turns(state, 1)                  # noeud `TurnsFromRounds(1)`
    node = None
    for etype, name in EWO_EFFECTS:
        leaf = AddEffect(etype, name, Caster(), duration_turns=turns)
        node = leaf if node is None else op_add(node, leaf)
    return op_add(node, Spawn(FixedTileIds(tiles), EARLY_WARNING_OVERRIDE_ID,
                              on_appearance=PerformAIAttack(ActiveTarget())))


class EarlyWarningOverrideAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.EarlyWarningOverrideAbility$$ExecuteBehaviour`
    (id 1077, `tauCrisis` Re'vas -- Tau, HERO). Cast SELF (ctor `AActiveAbility(<targeting statique de la
    classe>, 2)` ; `abilityTargets` rend le caster).

    Kit gameconfig 1077 : `unitId=tauSmnDroneShield`, `nrOfSummons=2`, `hitsReduction=1`,
    `summonHp`/`summonDmg`/`summonArmor`[level]. AUCUN volet degat propre.

    OBSERVABLE : (1) QUATRE effets sur Re'vas -- 1009 Overwatch_AutoAttack, 1144
    SuppressCloseCombatWeakness, 1145 EarlyWarningOverride_ReactivateOverwatch, 1149
    EarlyWarningOverride_Visual -- de duree `TurnsFromRounds(1)` ; (2) `nrOfSummons` Shield Drones sur
    des tuiles LIBRES adjacentes a Re'vas, chacun executant une attaque IA a l'apparition (i2 : « can
    immediately attack an enemy in melee, but cannot move this turn »).

    Flags de tour : `SetsActiveAbilityUsedFlag` overridee (pas de flag 2), `SetsEndTurnFlags` par defaut
    -> l'ability TERMINE le tour.

    Retour : {posed, spawned, attacks, tiles, count, dsl}."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.EarlyWarningOverride)   # 1077
    ABILITY_ID = EARLY_WARNING_OVERRIDE_ID

    # GATE DE CIBLE (#115) + PORTEE (#241) -- forme de ctor = **PRESET STATIQUE COPIE** (la 3e des
    # trois, et la SEULE de ce module) : `...EarlyWarningOverrideAbility$$.ctor` n'appelle AUCUN
    # `IdunBattle.Core.Services.TargetingOptions$$.ctor`. Il recopie les 0x40 octets du champ
    # STATIQUE de `TargetingOptions` a l'offset **`+0x280`** du bloc `<class>+0xb8`, puis :
    #     AActiveAbility..ctor(this, &opts, 2, 0)   # 3e arg = 2 = AbilityAttackType.Others
    # Aucun litteral de masque n'est visible dans le ctor. Le masque EFFECTIF est la constante ecrite
    # par `IdunBattle.Core.Services.TargetingOptions$$.cctor` a `<preset>+0x28` = `*(statics+0x2a8)`.
    #
    # Le preset lu EN ENTIER (bloc `statics+0x280` du `cctor`), pas seulement son champ `Rules` :
    #     <preset>+0x00 = *(statics+0x280) = 1                -> **isSelfCasting = true**
    #     <preset>+0x08 = copie de `TargetingRange statics+0x60` -> **RANGE_SELF** (`+0x60`
    #                     onlyAdjacent = 1 = `RangedBool.False`, `+0x68` overrideRange = `Nullable(0)`,
    #                     `+0x70` func null) : portee NULLE.
    #     <preset>+0x20 = *(statics+0x2a0) = 1                -> forceMeleeTarget = `RangedBool.False`
    #     <preset>+0x28 = *(statics+0x2a8) = **0x8004**       -> le masque
    #     <preset>+0x30/+0x38 = 0                             -> ecrases par `AActiveAbility$$.ctor`
    #
    # Decomposition EXHAUSTIVE -- 0x4 + 0x8000 = 0x8004, aucun bit residuel. Et AUCUN des deux n'est
    # une regle du filtre statique de CIBLE :
    #     0x4     (bit  2) CasterMatchesDynamicRule -> volet CASTER : `GetInvalidCasterReason` fait
    #             `if (rules & 4) { r = options[+0x30].Invoke(caster, casterTiles); if (r) broken(r); }`
    #             (delegue liee au slot vtable `+0x470`). NON PORTEE -- `get_invalid_caster_reason` ne
    #             porte que `CasterHasNotMoved`.
    #     0x8000  (bit 15) CasterIsPossibleTarget   -> flag DECLARATIF, PAS une regle de refus : il
    #             n'apparait ni dans la cascade cible ni dans `GetInvalidCasterReason` ; il est lu par
    #             `TargetingOptions$$get_CanTargetCaster` (preview / IA) et par la branche
    #             `AddCasterIfAtLeastOneTarget` de `GetCasterNotAddedReason`. Deja mirrore cote port
    #             (`TargetingOptions.can_target_caster`).
    # AUCUNE regle de DOMAINE ni de CAMP -> `refuses_all_enemy_targets` = `False`, routage IA inchange.
    # Le cast reel etant SELF (`abilityTargets` rend le caster), le port prend l'aiguillage self-cast
    # de `get_invalid_target_reason` -> `get_caster_not_added_reason` = 0, et le natif prend le meme
    # embranchement ; pour ce preset (`isSelfCasting != 0`, ni `AddCaster` ni
    # `AddCasterIfMatchesDynamicRule` ni `AddCasterIfAtLeastOneFreeTileInRange`) il tombe sur
    # `GetValidTargets(...).AllTargets.Count == 0 -> broken(0x800)`, non porte (permissif).
    TARGETING_OPTIONS = TargetingOptions(
        rules=TR.CasterMatchesDynamicRule | TR.CasterIsPossibleTarget,
        self_cast=True, range=RANGE_SELF, force_melee_target=RANGED_BOOL_FALSE)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        entities = entities_from_state(state, caster_id, target_id)
        n = early_warning_override_num_summons()
        # COLLAPSE de `First(SortTilesByUtilityForSummon(CanAddUnit(AdjacentTiles(Owner))), nrOfSummons)` :
        # la chaine sans le tri IA est EXPRIMABLE en selecteurs DSL portes -> on l'evalue telle quelle et
        # on injecte les ids resolus (le tri IA reste le seul maillon non porte, cf. bloc ci-dessus).
        tiles = PickFirstN(CanAddUnit(AdjacentTiles(Caster())), Const(n)).evaluate(entities) or []
        ectx = ExecutionContext(state=state, rng=state.rng)
        early_warning_override_tree(state, list(tiles)).execute(entities, ectx)
        posed = [{"target": p.get("target"), "effect": p.get("effect_type")}
                 for nm, p in ectx.emitted if nm == "AddEffect"]
        spawned = [p["unit"] for nm, p in ectx.emitted if nm == "SpawnUnit"]
        attacks = [p for nm, p in ectx.emitted if nm == "PerformAIAttack"]
        return {"ability": EARLY_WARNING_OVERRIDE_ID, "posed": posed, "spawned": spawned,
                "attacks": attacks, "tiles": list(tiles), "count": n, "dsl": True}


# =============== InspiredToGreatness (tauAunShi, HERO, actif 1082) -- lot #114 ===============
#
# `IdunBattleLogic.Entities.Abilities.Active.Loki.InspiredToGreatnessAbility$$ExecuteBehaviour`
# (MIRROR 1:1 du DECOMPILE) :
#
#   hpUsed    = GetVariableForLevel(config@0x60, 0x20, level)     # = hpToHeal   [lvl65 = 1091]
#   hpUnused  = GetVariableForLevel(config@0x60, 0x22, level)     # = hpToHeal_2 [lvl65 = 4365]
#   canReset  = UnitsThatCanHaveActiveAbilityReset( target@0x178 )
#   cantReset = TargetsSelector.op_Subtraction( target@0x178, canReset )
#   lvl       = Min( AbilityLevelAmount(Owner@0x148, AbilityType(0x43a = 1082)),
#                    PrimaryActiveAbilityLevelAmount(canReset) )
#
#   AActiveAbility.Execute(
#         ( RepairOrHeal(canReset,  hpUsed,   canReset)
#         & RepairOrHeal(cantReset, hpUnused, cantReset) )
#       & AddStatOverrideEffect(canReset, 0x49c = 1180 InspiredToGreatness_OverrideLevel,
#                               0x12 = 18 ACTIVE_ABILITY_LEVEL, lvl, 0, 0, 0)
#       & ResetActiveAbility(canReset, 0),
#       entities )
#
#   IdunBattleLogic.Entities.Abilities.Active.Loki.InspiredToGreatnessAbility$$RepairOrHeal(sel, amt, sel2) =
#       If( IsRepairable(sel, 0),
#           Repair(caster@0x160, sel,  Direct(amt), AbilityOrEffect(0x43a)),
#           Heal  (caster@0x160, sel2, Direct(amt)) )
#
# NOTES DE FIDELITE :
#  - Le SPLIT canReset/cantReset EST la mecanique de l'i2 : « heals or repairs it for 1091 Health.
#    [...] If that unit has NOT USED their active ability yet, then 4365 Health is restored instead. »
#    -> `canReset` = l'allie qui A consomme son actif (`BattleQuery.EntityCanHaveActiveAbilityReset`
#    branche `!IsInCooldown && !CanStillBeUsed`) = le PETIT montant `hpToHeal` ; son complementaire
#    prend le GROS `hpToHeal_2`. Les deux vars sont dans `variablesAffectedByRarityBonus` (scaling
#    rarete via `ability_var(multiplier_pct=...)`), lues+arrondies SEPAREMENT (jamais sommees --
#    meme discipline que le jumeau 1002 CombatRestoratives).
#  - `Min(AbilityLevelAmount(owner, 1082), PrimaryActiveAbilityLevelAmount(canReset))` = formules V
#    COLLAPSEES en scalaire (doctrine slice-18/19) : les deux niveaux sont lus sur l'
#    `ActiveAbilitiesComponent` (`AbilityState.Level` PER-ABILITY, canal `readAbilityState` #100),
#    avec repli sur `UnitContext.active_ability_level`.
#  - CAST LEGAL (`InspiredToGreatnessAbility$$GetDynamicInvalidTargetReason`, gate AMONT PORTE
#    depuis #247) : cible != caster, PAS de trait `0x7e7 = UnitTrait.Boss`, ET (soignable | reparable
#    | `EntityCanHaveActiveAbilityReset`). C'est pourquoi un allie a PLEINS PV dont l'actif est PRET
#    rend `fromHere = []` -- le cast est REFUSE (`ValidRequest`, mesure #247 : 2 lignes / 8).

INSPIRED_TO_GREATNESS_ID = "InspiredToGreatness"
ITG_OVERRIDE_LEVEL = int(EffectType.InspiredToGreatness_OverrideLevel)   # 0x49c = 1180


def _itg_heal_amounts(state: "State", caster_id: int) -> tuple[int, int]:
    """`(hpUsed, hpUnused)` -- mirror des DEUX `GetVariableForLevel` d'
    `InspiredToGreatnessAbility$$ExecuteBehaviour` :
        0x20 -> `hpToHeal`   : l'allie qui A utilise son actif  (canReset)
        0x22 -> `hpToHeal_2` : l'allie qui ne l'a PAS utilise   (cantReset)
    Lues SEPAREMENT via `ability_var` (scaling rarete `AbilityVariablesMultiplier`). MEME convention
    d'index que le jumeau 1002 (`CombatRestoratives`), lue independamment au decompile."""
    e = state.get_entity(caster_id)
    sc = e.get_component(StatsComponent) if e is not None else None
    ctx = sc.ctx if sc is not None else None
    level = getattr(ctx, "active_ability_level", 0) if ctx is not None else 0
    mult = int(getattr(ctx, "ability_variables_multiplier", 100) or 100) if ctx is not None else 100
    return (int(ability_var(INSPIRED_TO_GREATNESS_ID, "hpToHeal", level, multiplier_pct=mult) or 0),
            int(ability_var(INSPIRED_TO_GREATNESS_ID, "hpToHeal_2", level, multiplier_pct=mult) or 0))


def _ability_level_amount(state: "State", unit_id, ability_type: int):
    """`IdunBattleLogic.Entities.DSLFormulas$$AbilityLevelAmount(unit, abilityType)` (formule V,
    COLLAPSEE) : le niveau de CETTE ability sur CETTE unite = `ActiveAbility.AbilityState.Level`
    (canal `readAbilityState` #100). Repli sur `UnitContext.active_ability_level` (canal global) si
    l'entree n'est pas seedee. None si rien de lisible."""
    e = state.get_entity(int(unit_id)) if unit_id is not None else None
    if e is None:
        return None
    comp = e.get_component(ActiveAbilitiesComponent)
    ab = comp.get(int(ability_type)) if comp is not None else None
    if ab is not None and ab.level is not None:
        return int(ab.level)
    sc = e.get_component(StatsComponent)
    return getattr(sc.ctx, "active_ability_level", None) if sc is not None else None


def _primary_active_ability_level_amount(state: "State", unit_id):
    """`IdunBattleLogic.Entities.DSLFormulas$$PrimaryActiveAbilityLevelAmount(unit)` (formule V,
    COLLAPSEE) : le niveau de l'ability active PRIMAIRE de l'unite (`ActiveAbilityComponent.GetActive`
    = la 1re entree active/granted, cf. le meme accesseur cote playbook `InspiredToGreatnessPlaybook.
    _active_ability`). Repli `UnitContext.active_ability_level`."""
    e = state.get_entity(int(unit_id)) if unit_id is not None else None
    if e is None:
        return None
    comp = e.get_component(ActiveAbilitiesComponent)
    ab = next((a for a in comp.abilities if a.level is not None), None) if comp is not None else None
    if ab is not None:
        return int(ab.level)
    sc = e.get_component(StatsComponent)
    return getattr(sc.ctx, "active_ability_level", None) if sc is not None else None


def _repair_or_heal(sel, amount: int):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.InspiredToGreatnessAbility$$RepairOrHeal`
    (MIRROR) = `If(IsRepairable(sel), Repair(caster, sel, Direct(amt)), Heal(caster, sel, Direct(amt)))`.
    Les gardes d'eligibilite (`HealableUnitsSelector` cote natif) vivent COTE MUTATION, une par
    branche : `repairable_heal_type_1` (mecanique) / `healable_heal_type_0` (non-mecanique)."""
    return IfBehaviour(IsRepairable(sel),
                       Repair(sel, amount, guard=repairable_heal_type_1),
                       Heal(sel, amount, guard=healable_heal_type_0))


def inspired_to_greatness_tree(state: "State", caster_id: int, target_id: Optional[int]):
    """Arbre d'`IdunBattleLogic.Entities.Abilities.Active.Loki.InspiredToGreatnessAbility$$
    ExecuteBehaviour` (MIRROR 1:1, cf. le bloc de commentaire ci-dessus)."""
    hp_used, hp_unused = _itg_heal_amounts(state, caster_id)
    can_reset = UnitsThatCanHaveActiveAbilityReset(Target())
    cant_reset = Sub(Target(), can_reset)
    # `Min(AbilityLevelAmount(owner, 1082), PrimaryActiveAbilityLevelAmount(canReset))` -- COLLAPSE V.
    own_lvl = _ability_level_amount(state, caster_id, int(ActiveAbilityType.InspiredToGreatness))
    tgt_lvl = _primary_active_ability_level_amount(state, target_id)
    lvls = [v for v in (own_lvl, tgt_lvl) if v is not None]
    override_lvl = min(lvls) if lvls else 0
    heals = op_and(_repair_or_heal(can_reset, hp_used),
                   _repair_or_heal(cant_reset, hp_unused))
    return op_and(op_and(heals,
                         AddStatOverrideEffect(can_reset, ITG_OVERRIDE_LEVEL,
                                               int(StatType.ACTIVE_ABILITY_LEVEL), override_lvl,
                                               name=EffectType.InspiredToGreatness_OverrideLevel.name)),
                  ResetActiveAbility(can_reset, False))


class InspiredToGreatnessAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.InspiredToGreatnessAbility$$ExecuteBehaviour`
    (id 1082, `tauAunShi` Aun'Shi -- Tau, HERO). Cast UNIT-TARGET (ALLIE adjacent ; ctor
    `TargetingOptions(0, ..., 1, 0x402)`).

    Kit gameconfig 1082 : `hpToHeal`[level] et `hpToHeal_2`[level] (les DEUX rarity-affected). AUCUN
    volet degat, AUCUN spawn.

    OBSERVABLE : (1) l'allie cible est SOIGNE ou REPARE (selon `IsRepairable`) de `hpToHeal` s'il a
    deja utilise son actif, de `hpToHeal_2` sinon ; (2) s'il l'a utilise, il recoit l'effet 1180
    `InspiredToGreatness_OverrideLevel` (niveau d'ability plafonne au min des deux) et son actif est
    RE-ARME (`CanStillBeUsed = true`, cooldown remis a zero).

    Flags de tour : defauts base (1082 absent des tables d'override) -> termine le tour +
    ActiveAbilityUsed.

    Retour : {healed, repaired, override, reset, can_reset, amounts, dsl}."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.InspiredToGreatness)   # 1082
    ABILITY_ID = INSPIRED_TO_GREATNESS_ID

    # GATE DE CIBLE (#115) + PORTEE (#241) -- forme de ctor = **FLAGS DIRECTS**.
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.InspiredToGreatnessAbility$$.ctor` :
    #     TargetingOptions..ctor(&opts, isSelfCasting=0, range=<TargetingRange statics+0x30>,
    #                            forceMeleeTarget=1, rules=0x402, 0, 0, 0)
    #     AActiveAbility..ctor(this, &opts, 2, 0)   # 2 = AbilityAttackType.Others
    # MEME `TargetingRange` que 1081 (`statics+0x30`) mais `isSelfCasting = 0` et un masque de CAMP
    # oppose : la voisine de module ne dit rien de celle-ci.
    #
    # Decomposition EXHAUSTIVE -- 0x2 + 0x400 = 0x402, aucun bit residuel :
    #     0x2    (bit 1)  TargetMatchesDynamicRule -> delegue `options+0x38` =
    #            `...InspiredToGreatnessAbility$$GetDynamicInvalidTargetReason`, qui rend `1`
    #            (`ValidRequest`, que le natif REUTILISE comme code de refus) si
    #            `target == caster` OU `UnitExtensions.HasTrait(target, 0x7e7 = UnitTrait.Boss)`
    #            OU si les TROIS predicats `<slot 0x11>(caster, target, 0, 1)` (SOIGNABLE,
    #            `AttackQuery$$EntityCanBeHealed`), `<slot 0x12>(caster, target, 0, 0)` (REPARABLE,
    #            `AttackQuery$$EntityCanBeRepaired`) et `<slot 0x31>(target, 0)`
    #            (`BattleQuery$$EntityCanHaveActiveAbilityReset`) sont faux ; sinon `0`.
    #            PORTE depuis #247 -- cf. `get_dynamic_invalid_target_reason` ci-dessous.
    #     0x400  (bit 10) TargetIsFriendly         -> PORTE. Le seul bit qui mord sur le CAMP :
    #            `if (!UnitsAreFriendly(caster, target)) -> broken(0x400)` (et une cible portant
    #            l'effet `FriendlyFire` 0x67 n'est « amie » de personne). Consequence de ROUTAGE :
    #            `refuses_all_enemy_targets` passe a **True** pour 1082 -- c'est le verdict natif
    #            (l'ability soigne un ALLIE), et c'est justement ce que le masque manquant cachait.
    # PORTEE : `TargetingRange statics+0x30` = `RANGE_ADJACENT` -> branche
    # `AreEntitiesAdjacent(casterTiles, target)` : Aun'Shi ne peut inspirer qu'un allie AU CONTACT.
    # `forceMeleeTarget` = 1 = `RangedBool.False`.
    TARGETING_OPTIONS = TargetingOptions(
        rules=TR.TargetMatchesDynamicRule | TR.TargetIsFriendly,
        self_cast=False, range=RANGE_ADJACENT, force_melee_target=RANGED_BOOL_FALSE)

    def get_dynamic_invalid_target_reason(self, state: "State", caster_id: int,
                                          target_id: Optional[int]) -> int:
        """`IdunBattleLogic.Entities.Abilities.Active.Loki.InspiredToGreatnessAbility$$GetDynamicInvalidTargetReason`
        -- MIRROR 1:1 du decompile (`param_2` = caster, `param_4` = target, la signature du delegue
        `TargetingOptions.DynamicTargetingTargetRule`) :

            if (caster == target || UnitExtensions.HasTrait(target, 0x7e7 Boss)) return 1;
            healable   = attackQuery.<slot 0x11> EntityCanBeHealed  (caster, target, 0, true);
            repairable = attackQuery.<slot 0x12> EntityCanBeRepaired(caster, target, 0, false);
            canReset   = battleQuery.<slot 0x32> EntityCanHaveActiveAbilityReset(target, false);
            return (!healable && !repairable && !canReset) ? 1 : 0;

        ⚠ LE CODE RENDU EST LE LITTERAL `1` = `TargetingRule.ValidRequest` : le natif REUTILISE
        cette valeur comme code de refus, exactement comme la branche `TargetIsTile` du filtre
        statique. Ne pas y lire « ability indisponible ».

        `0x7e7` = **2023**, et la QUALIFICATION compte : 2023 n'existe QUE dans
        `IdunBattle.Entities.Enum.UnitTrait` (= `Boss`) -- il est absent d'`EffectType`,
        d'`ActiveAbilityType` et de `TriggeredAbilityType`, dont les espaces d'ids se recouvrent
        numeriquement. L'argument est bien un `UnitTrait` (2e parametre d'`UnitExtensions$$HasTrait`).

        DEUX GARDES-FOUS, parce que ce refus-ci sort d'une CONJONCTION de disjuncts FAUX -- et que
        « faux » et « pas lu » n'y ont pas le meme statut :
          * `canReset` INCONNU (`None` : l'unite n'a pas d'`ActiveAbilitiesComponent`, c'est-a-dire
            `decisionView` interroge SANS `allAbilities`) -> on ne refuse pas ;
          * PV de la cible NON LISIBLES (`attack_query.health_is_readable`) -> on ne refuse pas non
            plus : `is_damaged_unit` rendrait `False` sans avoir rien lu, et ce `False`-la
            fabriquerait le refus a lui seul.
        Les mesures de #247 sont faites avec `allAbilities: True` et un `combatSnapshot` complet,
        donc sur des verdicts REELS -- les gardes ne masquent aucune de ces lignes."""
        if target_id is None:
            return 0                                    # cible non resolue -> le port ne decide pas
        if int(target_id) == int(caster_id):
            return int(TR.ValidRequest)
        if _has_trait(state, target_id, int(UnitTrait.Boss)):
            return int(TR.ValidRequest)
        if entity_can_be_healed(state, caster_id, target_id, scope=0, remove_effects=True):
            return 0
        if entity_can_be_repaired(state, caster_id, target_id, scope=0, remove_effects=False):
            return 0
        if entity_can_have_active_ability_reset(state, target_id) is not False:
            return 0                                    # True (resettable) ou None (verdict INCONNU)
        if not health_is_readable(state, target_id):
            return 0                                    # PV non lus -> les 2 1ers disjuncts sont INCONNUS
        return int(TR.ValidRequest)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        entities = entities_from_state(state, caster_id, target_id)
        can_reset = UnitsThatCanHaveActiveAbilityReset(Target()).evaluate(entities) or []
        # VERDICT INCONNU (canal `ActiveAbilitiesComponent` absent = `decisionView` sans
        # `allAbilities`) : le split de soin retomberait SILENCIEUSEMENT sur `cantReset` -> on le
        # REND VISIBLE dans le diagnostic plutot que de laisser une fausse certitude.
        unknown = entity_can_have_active_ability_reset(state, target_id) is None
        ectx = ExecutionContext(state=state, rng=state.rng)
        inspired_to_greatness_tree(state, caster_id, target_id).execute(entities, ectx)
        hp_used, hp_unused = _itg_heal_amounts(state, caster_id)
        return {"ability": INSPIRED_TO_GREATNESS_ID, "caster": caster_id, "target": target_id,
                "can_reset": [u.get("id") for u in can_reset],
                "unknown_reset_verdict": unknown,
                "amounts": {"hpToHeal": hp_used, "hpToHeal_2": hp_unused},
                "healed": [p for n, p in ectx.emitted if n == "Heal"],
                "repaired": [p for n, p in ectx.emitted if n == "Repair"],
                "override": [p for n, p in ectx.emitted if n == "AddStatOverrideEffect"],
                "reset": [p for n, p in ectx.emitted if n == "ResetActiveAbility"],
                "dsl": True}


# ============ SeekerMissileFrequencyLock (tauMarksman Sho'syl, HERO, actif 1069) -- #491 ============
#
# `IdunBattleLogic.Entities.Abilities.Active.Loki.SeekerMissileFrequencyLockAbility$$ExecuteBehaviour`
# (MIRROR 1:1 du DECOMPILE, build `rnca9r7q6c`) :
#
#   turns = Sum( TurnsFromRounds(1), Direct(1) )        # == DSLFormulas$$TurnsUntilEndOfCurrentPlayersNextTurn
#   AActiveAbility.Execute(
#         AddEffect(     0x462 = 1122 Markerlight,                        AbilityStateReference,
#                        source = Caster@DSLSelectors+0x48,
#                        targets = Target@DSLSelectors+0x60,  turns )
#       & AddBondEffect( 0x463 = 1123 SeekerMissileFrequencyLock_Target,  CreateSnapshot(abilityState),
#                        source = Caster@+0x48, targets = Target@+0x60, bonded = Caster@+0x48,
#                        options = ZERO )
#       & AddBondEffect( 0x470 = 1136 SeekerMissileFrequencyLock_Aiming,  CreateSnapshot(abilityState),
#                        source = Caster@+0x48, targets = Caster@+0x48, bonded = Target@+0x60,
#                        options = ZERO ),
#       entities )
#
# LE CAST NE FRAPPE PAS. L'audit `combat-ability-coverage` classe 1069 en `DAMAGE(HeavyRound)` --
# c'est le profil du KIT (`constants.damageProfile = HeavyRound`, `nrOfHits = 1`,
# `minDmg`/`maxDmg`[level]), pas celui du cast : l'`ExecuteBehaviour` ne porte AUCUN noeud
# `AttackWithAbilityDamage`, AUCUN spawn, AUCUNE stat. Meme patron 2-PHASES que `HeavyRailRifle`
# (1160) : le cast ARME, le degat vient de la PHASE 2 --
# `IdunBattleLogic.Entities.Abilities.Triggered.Loki.SeekerMissileFrequencyLock_AttackAbility$$CreateBehaviour`
# (`TriggeredAbilityType.SeekerMissileFrequencyLock_Attack` = 1127, rendu par
# `IdunBattle.Entities.Effects.Loki.SeekerMissileFrequencyLockTargetEffect$$GetTriggeredAbilityType`)
# -- HORS de ce port (residu #491-r1, cf. `docs/rl/case-491-seeker-missile-frequency-lock.md`).
#
# ⚠ L'ordinal `0x467 = 1127` rendu par `$$GetTriggeredAbilityType` est un **TriggeredAbilityType**,
# PAS un `EffectType` : `EffectType(1127)` existe et vaut `AnnihilatorBeam_PendingAttack` -- une
# ability ENTIEREMENT differente. Qualifie par NOM (`triggered_ability_type.py`), jamais par ordinal.
#
# LES DEUX BONDS SONT SYMETRIQUES ET INVERSES (lu, pas deduit -- le decompile passe les memes deux
# selecteurs dans l'ordre oppose) :
#   * 1123 `_Target` est pose SUR LA CIBLE,  bonde AU CASTER  -> `APendingAttackEffect` (le missile en
#     vol vise cette unite) ;
#   * 1136 `_Aiming` est pose SUR LE CASTER, bonde A LA CIBLE -> `BaseEffect` (Sho'syl est en train de
#     viser). Son `$$CreateHandleTriggerAbilitiesInternal` retire l'effet sur
#     `On(0xc = EventTriggerType.UnitActiveAbility) & TriggeringAbilityIs(<self>)
#      & AreEqual(Caster@+0x48, BondedEntityFromEffect(Effect@+0x38))` -- i.e. un NOUVEAU cast de
#     Sho'syl annule le verrouillage precedent.
# La classe de 1136 n'est pas portee -> `BaseEffect` inerte (presence FIDELE, retrait sur nouveau cast
# non modelise -- residu #513-r1). Celle de 1123, elle, l'est DEPUIS #513 : son foyer est
# `runner/operations/triggers/pending_attack.py`, qui porte le `Triggered()` d'`APendingAttackEffect`
# commun aux 20 derivees, et la PHASE 2 vit plus bas dans ce module.
#
# `Markerlight` (1122), lui, EST porte (`MarkerlightEffect`) : la cible prend `MarkerlightDmgBonusPct`
# (=15 %) de degats en plus des attaques RANGED d'un attaquant T'AU. C'est l'observable MESURABLE du
# cast, et le lien de kit avec `TwinSmartMissileSystem` (1161), dont l'attaque ne porte QUE sur les
# ennemis deja marques.
#
# `CreateSnapshot(abilityState)` (`IdunBattleLogic.Entities.DSLSelectors$$CreateSnapshot`) = l'
# `AbilityStateReference` FIGE, meme role que le `snapshot` d'`EarlyWarningOverride` et le
# `CreateSnapshot` de `WarHowlAbility`. Cote port il n'a d'effet OBSERVABLE que via
# `scale_from_source` (indexation des `ConfigVar` de l'effet materialise).
# ⚠ IL EN A UN DEPUIS #513, ET SUR 1123 SEULEMENT : la PHASE 2 relit cet etat fige par
# `AbilityStateFromEffect( EffectFromOwner(Target@0x60, 0x463) )` pour indexer `minDmg`/`maxDmg`.
# C'est le SNAPSHOT du cast, pas l'etat COURANT du caster -- ils coincident dans un runner normalise
# (tout a 50), et divergeraient des qu'un niveau bougerait entre le cast et le tir. 1122 et 1136
# gardent le defaut : aucune magnitude `ConfigVar` portee ne les lit.

# Les identifiants du kit vivent avec la PHASE 2 (`operations/triggers/loki/seeker_missile_attack.py`)
# depuis #503-r3 : c'est ce module-la que `dispatch/registry.py` doit pouvoir charger SEUL pour que
# `TRIGGERED_ABILITY_BEHAVIOURS[1127]` soit peuple des que la chaine trigger l'est. Le sens de
# l'arete est donc `abilities.tau -> triggers.loki.seeker_missile_attack`, jamais l'inverse : la
# reciproque est PORTEUSE (mesuree -- `tau` tire `registry` par `attack_query -> revive_effect`).
from ..operations.triggers.loki.seeker_missile_attack import (SEEKER_LOCK_AIMING,
                                                              SEEKER_LOCK_TARGET,
                                                              SEEKER_MISSILE_FREQUENCY_LOCK_ID)


def seeker_missile_frequency_lock_tree(state: "State"):
    """Arbre de
    `IdunBattleLogic.Entities.Abilities.Active.Loki.SeekerMissileFrequencyLockAbility$$ExecuteBehaviour`
    -- MIRROR 1:1 du decompile (cf. le bloc de commentaire ci-dessus).

    `turns` est CALCULE ici parce que le natif compose deux noeuds de formule dont un SEUL passe par
    `IdunBattle.Core.Services.BattleQuery$$ConvertRoundsToTurns` : `Sum(TurnsFromRounds(1),
    Direct(1))` == `IdunBattleLogic.Entities.DSLFormulas$$TurnsUntilEndOfCurrentPlayersNextTurn`, deja
    porte (`turns_until_end_of_current_players_next_turn`). Il s'applique au SEUL `Markerlight` : les
    deux `AddBondEffect` recoivent une struct d'options ZERO-INITIALISEE (`local_188..uStack_170 = 0`,
    surcharge `IdunBattleLogic.Entities.DSLBehaviors$$AddBondEffect(..., options)` et non
    `(..., turns)`) -> duree `DefaultAmountOfRounds` = `duration_rounds=None` cote port."""
    turns = turns_until_end_of_current_players_next_turn(state)
    mark = AddEffect(MARKERLIGHT, EffectType.Markerlight.name, Target(), duration_turns=turns)
    # `scale_from_source=True` = le 3e argument natif `CreateSnapshot(abilityState)` : l'entite-effet
    # BAKE l'etat d'ability du POSEUR, et c'est CET etat que la phase 2 relit par
    # `AbilityStateFromEffect(EffectFromOwner(Target, 0x463))` pour indexer `minDmg`/`maxDmg` (#513).
    on_target = AddBondEffect(SEEKER_LOCK_TARGET, EffectType.SeekerMissileFrequencyLock_Target.name,
                              Caster(), Target(), duration_rounds=None, bonded_ref=Caster(),
                              scale_from_source=True)
    on_caster = AddBondEffect(SEEKER_LOCK_AIMING, EffectType.SeekerMissileFrequencyLock_Aiming.name,
                              Caster(), Caster(), duration_rounds=None, bonded_ref=Target())
    return op_and(op_and(mark, on_target), on_caster)


class SeekerMissileFrequencyLockAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.SeekerMissileFrequencyLockAbility$$ExecuteBehaviour`
    (id 1069, `tauMarksman` Sho'syl -- Tau, HERO). Cast UNIT-TARGET.

    La classe native ne porte QUE deux corps -- `$$.ctor` et `$$ExecuteBehaviour` : aucun
    `GetDynamicInvalidTargetReason`, aucun `GetAdditionalTargets`, aucun `GetAttackDamage`.

    Kit gameconfig 1069 : `range=5`, `nrOfHits=1`, `damageProfile=HeavyRound`, `minDmg`/`maxDmg`[level]
    (rarity-affected) -- TOUS consommes par la PHASE 2, pas par le cast (cf. le bloc ci-dessus).

    OBSERVABLE DU CAST : (1) la cible recoit `Markerlight` (1122) pour
    `TurnsUntilEndOfCurrentPlayersNextTurn` tours -- effet PORTE, donc +15 % de degats subis des
    attaques ranged T'AU ; (2) la cible recoit `SeekerMissileFrequencyLock_Target` (1123, bonde au
    caster, duree DEFAUT) ; (3) Sho'syl recoit `SeekerMissileFrequencyLock_Aiming` (1136, bonde a la
    cible, duree DEFAUT). AUCUN degat, AUCUN spawn, AUCUNE stat touchee.

    Flags de tour : defauts base (1069 absent de `NO_END_TURN_ABILITY_TYPES` /
    `NO_ABILITY_USED_FLAG_ABILITY_TYPES`) -> l'ability termine le tour + pose ActiveAbilityUsed."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.SeekerMissileFrequencyLock)   # 1069
    ABILITY_ID = SEEKER_MISSILE_FREQUENCY_LOCK_ID

    # GATE DE CIBLE (#115) + PORTEE (#241) -- forme de ctor = **PRESET STATIQUE COPIE** (la 3e des
    # trois formes) : `...SeekerMissileFrequencyLockAbility$$.ctor` n'appelle AUCUN
    # `IdunBattle.Core.Services.TargetingOptions$$.ctor`. Il recopie les 0x40 octets du champ STATIQUE
    # de `TargetingOptions` a l'offset RELATIF **+0x180** du bloc `<class>+0xb8`, puis :
    #     AActiveAbility..ctor(this, &opts, 0)   # 3e arg = 0 = AbilityAttackType.DirectTargetAttack
    # Aucun litteral de masque n'est donc visible dans le ctor : le masque EFFECTIF est la constante
    # ecrite par `IdunBattle.Core.Services.TargetingOptions$$.cctor` a `<preset>+0x28`, soit
    # `*(statics+0x1a8)` = **0x4002** (LU dans le cctor, pas deduit). Ce n'est PAS la surcharge
    # « preset + flags » : la copie est integrale, il n'y a aucun flag a OR-er.
    #
    # Decomposition EXHAUSTIVE (`IdunBattle.Core.Services.TargetingRule`) -- 0x2 + 0x4000 = 0x4002,
    # aucun bit residuel :
    #     0x2     (bit 1)  TargetMatchesDynamicRule -> point d'extension : le filtre statique invoque
    #             la regle-delegue `options+0x38` (slot vtable +0x480). La classe native ne fournit
    #             AUCUN corps `...SeekerMissileFrequencyLockAbility$$GetDynamicInvalidTargetReason`
    #             (ses SEULS corps sont `$$.ctor` et `$$ExecuteBehaviour`) -> defaut `AActiveAbility`
    #             = 0 = aucun refus. Cote port : `ActiveAbility.get_dynamic_invalid_target_reason`.
    #     0x4000  (bit 14) TargetIsEnemy            -> PORTE
    #             (`TargetingQuery$$UnitsCanAttackEachOther`) : refus sur soi-meme et sur un allie.
    # PORTEE : le MEME preset `+0x180` porte `TargetingRange` <- `TargetingRange` statique **+0x18**
    # (`IdunBattle.Core.Services.TargetingRange$$.cctor` : `+0x18`=1 `onlyAdjacent = RangedBool.False`,
    # `+0x1c`=1 `useRangeFromConfig = true`, `+0x20/+0x24` overrideRange VIDE, `+0x28` null)
    # = `RANGE_FROM_CONFIG` -> `AActiveAbility$$SetConfigValuesInTargetingOptions` pose
    # `OverrideRange = GetNumberConstant(0x16 range)` = `SeekerMissileFrequencyLock.constants.range`
    # = **5** (l'arme de `tauMarksman` porte 3 : c'est bien l'ABILITY qui etend a 5, cf.
    # `engine/services/ability_range.py` et `probe_433_r4_r2_r1_ability_range.py`).
    # `forceMeleeTarget` (`<preset>+0x20` = `*(statics+0x1a0)`) = **1** = `RangedBool.False` -> AUCUN
    # clamp melee.
    # ⚠ LA VOISINE MENT : `HellfyreMissileRack` (1088) a le MEME masque 0x4002 et le MEME
    # `RANGE_FROM_CONFIG`, mais son preset est `+0x140`, qui ecrit `forceMeleeTarget = 0`
    # (`RangedBool.True`). Copier le masque d'a cote aurait produit un regime de portee FAUX.
    # ⚠ Cette valeur MIGRE depuis `TARGETING_OPTIONS_UNPORTED[1069]` (contrat de DISJONCTION :
    # une ability a UNE source de masque, jamais deux -- garde
    # `tests/engine/runner/test_targeting_options_sources.py`).
    TARGETING_OPTIONS = TargetingOptions(
        rules=TR.TargetMatchesDynamicRule | TR.TargetIsEnemy,
        self_cast=False, range=RANGE_FROM_CONFIG, force_melee_target=RANGED_BOOL_FALSE)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        entities = entities_from_state(state, caster_id, target_id)
        ectx = ExecutionContext(state=state, rng=state.rng)
        seeker_missile_frequency_lock_tree(state).execute(entities, ectx)
        posed = [{"target": p["target"], "effect": p["effect_type"], "bonded": p.get("bonded"),
                  "placed": p.get("placed"), "active": p.get("active")}
                 for n, p in ectx.emitted if n in ("AddEffect", "AddBondEffect")]
        return {"ability": SEEKER_MISSILE_FREQUENCY_LOCK_ID, "caster": caster_id,
                "target": target_id, "posed": posed,
                "turns": turns_until_end_of_current_players_next_turn(state), "dsl": True}


# ---- PHASE 2 : `SeekerMissileFrequencyLock_Attack` (TriggeredAbilityType 0x467 = 1127), #513 ------
#
# DEPLACEE vers `runner/operations/triggers/loki/seeker_missile_attack.py` par #503-r3 -- avec sa RE
# integrale (les trois points de fidelite, l'ordre du `op_BitwiseAnd`, le kit partage). Une ability
# TRIGGERED vit avec les triggers : c'est la SEULE facon pour que `dispatch/registry.py` puisse
# peupler `TRIGGERED_ABILITY_BEHAVIOURS[1127]` sans importer ce module-ci, dont l'arete retour est
# PORTEUSE (`tau -> attack_query -> revive_effect -> dispatch.ability -> dispatch.core ->
# dispatch.registry`, chaine MESUREE). Ce module garde la PHASE 1, l'active `1069` ci-dessus.

# ============ ExemplarOfTheKauyon (tauShadowsun, HERO, actif 1087) -- lot #488 ============
#
# `IdunBattleLogic.Entities.Abilities.Active.Loki.ExemplarOfTheKauyonAbility$$ExecuteBehaviour`
# (MIRROR 1:1 du DECOMPILE ; offsets de `IdunBattleLogic.Entities.DSLSelectors` -- convention deja
# etablie dans le port : `caster@0x48`, `target@0x60`, `ActiveTarget@0x68`, `AllTiles@0x18`) :
#
#   teleport = DSLBehaviors.Teleport( caster@0x48, target@0x60 )
#   aiAttack = DSLBehaviors.PerformAIAttackFromCurrentPosition( target@0x60, null, null, false )
#   exTile   = DSLSelectors.Entity( <AbilityEntities+0x40 = casterTile> )
#   unitId   = AbilityConfiguration.GetStringConstant( config@0x60, 0 )   # "unitId"
#   opts     = SpawnUnitOptions.WithStatsFromConfig( config@0x60, abilityState, null, null )
#   opts.<+0x18> = DSLBehaviors.AddTrait( ActiveTarget@0x68, 0x418, null )
#   tileSel  = First( CanAddUnit( exTile + SortByDistance( Randomize( AllTiles@0x18 ), exTile ) ),
#                     1, null )
#   spawn    = DSLBehaviors.Spawn( caster@0x48, tileSel, unitId, opts )
#   addEff   = DSLBehaviors.AddEffect( 0x49d, AbilityStateReference,
#                                      source = caster@0x48, targets = caster@0x48,
#                                      options = default )            # Nullable turns VIDE
#   remEff   = DSLBehaviors.RemoveEffect( caster@0x48, (int?)0x49d, null )
#
#   AActiveAbility.Execute( entities, this,
#       ( teleport & If( <DSLTriggers+0x20 = OwnerIsAlive>, (addEff & aiAttack) & remEff ) )
#       & spawn )
#
# NOTES DE FIDELITE :
#  - `AbilityEntities+0x40` EST `casterTile` -- lu sur les noms de parametres du
#    `IdunBattle.Entities.Abilities.AbilityEntities$$.ctor` (32 arguments nommes ; `+0x00` actor,
#    `+0x08` caster, `+0x10` target, `+0x18` owner, `+0x20` activeTarget, `+0x28`
#    previousActiveTarget, `+0x30` targetTile, `+0x38` targetTiles, **`+0x40` casterTile**, `+0x48`
#    casterTiles, `+0x50` activePlayer, `+0x58` effect). C'est une entite CAPTUREE a la construction
#    de l'`AbilityEntities`, donc AVANT le teleport : d'ou l'i2, « A stationary Command-Link Drone is
#    summoned in the hex she **previously occupied** ». Un `CasterTile()` DYNAMIQUE rendrait la
#    NOUVELLE tuile -- c'est exactement pourquoi le natif passe par `DSLSelectors.Entity(<entite>)` et
#    pas par le selecteur `CasterTile`. Le port COLLAPSE donc l'id AVANT d'executer l'arbre et le
#    presente en `FixedTileIds` (meme vehicule que `SendInTheNextWave` / `SpawnPoxwalkers`).
#  - L'ORDRE compte : le `Teleport` LIBERE la tuile d'origine avant que le `Spawn` ne l'evalue, ce
#    qui fait passer `CanAddUnit(exTile)` -- le drone atterrit sur l'ex-tuile de Shadowsun dans le cas
#    nominal, et le `SortByDistance(Randomize(AllTiles), exTile)` n'est le repli que si elle est prise.
#  - `Randomize(AllTiles)` CONSOMME DU RNG (permutation complete du pool, `len(pool)` tirages, cf. sa
#    docstring) et il est evalue MEME quand l'ex-tuile passe : le `+` (op_Addition) evalue ses DEUX
#    operandes avant que `First(1)` ne tranche, exactement comme le natif.
#  - `AddEffect` recoit un `options` ZERO-initialise (32 octets) -> `Nullable<turns>` VIDE, donc
#    AUCUN noeud de duree : convention deja posee par `add_effect_or_increase_level`
#    (`duration_rounds=0` = permanent cote port). Sans objet ici, l'effet etant retire trois noeuds
#    plus bas -- mais on n'invente pas une duree que le natif n'ecrit pas.
#  - `PerformAIAttack(Target())` : le natif passe `target@0x60`, un selecteur de TUILE (l'ability est
#    `TargetIsTile`). C'est la tuile ou Shadowsun VIENT d'arriver -- donc l'acteur de l'attaque IA est
#    bien elle. Defauts `...FromCurrentPosition` (`allow_move_action=False`, `move_amount=0`).
#  - Le gate `If(OwnerIsAlive)` couvre les DEUX etages qui suivent le deplacement (overwatch, piege,
#    DoT declenches par l'arrivee) : si Shadowsun meurt en se teleportant, ni l'effet ni l'attaque
#    n'ont lieu -- mais le `Spawn`, lui, est HORS du `If` et a lieu quand meme.
#  - `SetsEndTurnFlags` / `SetsActiveAbilityUsedFlag` : AUCUN override dans la classe native (les
#    seuls symboles `ExemplarOfTheKauyonAbility$$*` du build sont `.ctor`, `ExecuteBehaviour`,
#    `GetDynamicInvalidTargetReason`, `GetPossibleAdditionalTargetTilesForDangerZone` et le lambda de
#    la regle dynamique) -> defauts, l'ability TERMINE le tour et pose le flag.

EXEMPLAR_OF_THE_KAUYON_ID = "ExemplarOfTheKauyon"
EXEMPLAR_KAUYON_HITS = int(EffectType.ExemplarOfTheKauyon_AdditionalHits)     # 0x49d = 1181


def exemplar_of_the_kauyon_tree(dest_tile_id: int, ex_tile_id: Optional[int]):
    """Arbre de `...ExemplarOfTheKauyonAbility$$ExecuteBehaviour` (MIRROR 1:1, cf. le bloc ci-dessus).

    `dest_tile_id` = le COLLAPSE de `target@0x60`. Le port ne materialise AUCUNE entite-tuile dans
    `state.entities` (elles ne vivent que dans `state.board`), donc `entities_from_state` laisse
    `ctx.target` a `None` pour un cast TILE-TARGET et le selecteur `Target()` serait VIDE : on
    presente l'id deja resolu en `FixedTileIds`, meme vehicule de collapse que
    `DutyEternalAbility` / `SendInTheNextWaveAbility` / `SpawnPoxwalkersAbility`.

    `ex_tile_id` = le COLLAPSE de `DSLSelectors.Entity(<AbilityEntities+0x40 = casterTile>)`, resolu
    AVANT l'execution (donc AVANT le teleport). `None` -> le selecteur d'ex-tuile est VIDE et seul le
    repli `SortByDistance(Randomize(AllTiles), ...)` alimente le spawn."""
    dest = FixedTileIds([dest_tile_id])
    ex_tile = FixedTileIds([ex_tile_id] if ex_tile_id is not None else [])
    spawn_tiles = PickFirstN(
        CanAddUnit(Union(ex_tile, SortByDistance(Randomize(AllTiles()), ex_tile))), Const(1))
    corps = op_and(
        # `AddEffect(0x49d, abilityState = AbilityStateReference, source = caster@0x48,
        #            targets = caster@0x48, options = default)`.
        #  * `duration_rounds=None` : le natif passe une struct d'options ZERO-initialisee, donc AUCUN
        #    noeud `TurnsFromRounds` -> pas d'override, la duree vient de `DefaultAmountOfRounds`
        #    (branche « pas d'override » d'`AddEffectOperation`). Sans objet ici (l'effet est retire
        #    trois noeuds plus bas) mais on n'invente pas une duree que le natif n'ecrit pas.
        #  * `scale_from_source` : c'est le pendant PORT de l'`AbilityStateReference` -- le 2e argument
        #    natif. `...ExemplarOfTheKauyon_AdditionalHitsEffectEffect$$CreateAdditionalHits` lit son
        #    degat par `DSLFormulas.ConfigVar(0xb = dmg, GetAbilityState(effet), config)`, donc contre
        #    le NIVEAU d'ability + le multiplicateur de rarete de l'unite qui a pose l'effet. Sans lui
        #    l'effet retombe sur le niveau 1 : MESURE #488, les 2 coups additionnels valaient **40**
        #    au lieu de **3979** (la phase ARME, elle, etait deja bit-exacte : 3162 / 2678). Meme
        #    cablage que le jumeau `SorcerousFacade_AdditionalHits` (1204), meme canal #179.
        AddEffect(EXEMPLAR_KAUYON_HITS, EffectType.ExemplarOfTheKauyon_AdditionalHits.name,
                  Caster(), duration_rounds=None, scale_from_source=True, source_ref=Caster()),
        PerformAIAttack(dest))
    corps = op_and(corps, RemoveEffect(EXEMPLAR_KAUYON_HITS, Caster()))
    tete = op_and(Teleport(Caster(), dest), IfBehaviour(OwnerIsAlive(), corps))
    return op_and(tete, Spawn(spawn_tiles, EXEMPLAR_OF_THE_KAUYON_ID,
                              on_appearance=AddTrait(ActiveTarget(), UnitTrait.Stationary)))


class ExemplarOfTheKauyonAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.ExemplarOfTheKauyonAbility$$ExecuteBehaviour`
    (id 1087, `tauShadowsun` -- Commander Shadowsun, Tau, HERO). Cast TILE-TARGET.

    Kit gameconfig 1087 : `unitId=tauSmnDroneCommandLink`, `damageProfile=Blast`, `nrOfHits=2`,
    `initialCooldownTurns=1` ; variables `dmg` / `summonHp` / `summonDmg` / `summonArmor` (toutes
    dans `variablesAffectedByRarityBonus`).

    OBSERVABLE, dans l'ordre : (1) Shadowsun DISPARAIT de sa tuile et REAPPARAIT sur la tuile cible
    (libre, adjacente a un allie) ; (2) si elle a survecu au deplacement, l'effet 1181
    `ExemplarOfTheKauyon_AdditionalHits` est pose sur elle, elle execute une ATTAQUE NORMALE pilotee
    par l'IA depuis sa nouvelle position, puis l'effet est retire ; (3) un `tauSmnDroneCommandLink`
    `Stationary` apparait sur la tuile qu'elle occupait -- ce dernier volet a lieu MEME si elle est
    morte en chemin (il est hors du `If`). i2 : « Commander Shadowsun disappears, then reappears on a
    target hex adjacent to an allied unit and immediately performs a normal attack against the
    closest enemy target. This attack deals an additional {nrOfHits}x {dmg} Blast Damage. A
    stationary Command-Link Drone is summoned in the hex she previously occupied. »

    LE DEGAT SUPPLEMENTAIRE N'EST PAS ECRIT ICI : il vient de l'effet 1181, deja porte
    (`entities/effects/loki/hits.py::ExemplarOfTheKauyonAdditionalHitsEffect`, canal #179
    `EffectAdditionalHits`, mesure #366-r1). Cette classe est ce qui le POSE -- l'inscription etait
    DORMANTE tant que 1087 restait un no-op combat.

    Retour : {teleport, posed, attacks, removed, spawned, ex_tile, dsl}."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.ExemplarOfTheKauyon)     # 1087
    ABILITY_ID = EXEMPLAR_OF_THE_KAUYON_ID

    # GATE DE CIBLE (#115) + PORTEE (#241) -- forme de ctor = **7 ARGUMENTS EXPLICITES** (ni preset
    # copie, ni surcharge PRESET+FLAGS) : `...ExemplarOfTheKauyonAbility$$.ctor` fait
    #     TargetingOptions..ctor(&opts, isSelfCasting = 0,
    #                            range = &<TargetingRange statics+0x48>,
    #                            forceMeleeTarget = 1, rules = 0x6001042, null, null)
    #     AActiveAbility..ctor(this, &opts, 2)          # 3e arg = 2 = AbilityAttackType.Others
    # Le masque est donc le LITTERAL, sans template a fusionner. Decomposition EXHAUSTIVE de
    # 0x6001042 = 0x2 + 0x40 + 0x1000 + 0x2000000 + 0x4000000, aucun bit residuel :
    #     0x2        TargetMatchesDynamicRule      -> delegue `GetDynamicInvalidTargetReason`, porte
    #                                                 ci-dessous (tuile libre + allie adjacent).
    #     0x40       TargetIsTile                  -> domaine TUILE.
    #     0x1000     TargetTileIsFree              -> la tuile d'arrivee doit etre libre.
    #     0x2000000  AllowObscuredTargetByElevation
    #     0x4000000  AllowObscuredTargetByWalls    -> Shadowsun se teleporte : la ligne de vue ne
    #                                                 la contraint pas. SEULE du lot #241 a porter
    #                                                 les DEUX bits d'obscurcissement.
    # `range` = `<TargetingRange statics+0x48>` = RANGE_WHOLE_BOARD ; `forceMeleeTarget = 1` =
    # `RangedBool.False`. Ce masque etait dans `TARGETING_OPTIONS_UNPORTED` (pose par #241) ; il
    # MIGRE ici avec la face COMBAT, contrat de disjonction du module `targeting.py`.
    TARGETING_OPTIONS = TargetingOptions(
        rules=TR.TargetMatchesDynamicRule | TR.TargetIsTile | TR.TargetTileIsFree
              | TR.AllowObscuredTargetByElevation | TR.AllowObscuredTargetByWalls,
        self_cast=False, range=RANGE_WHOLE_BOARD, force_melee_target=RANGED_BOOL_FALSE)

    def get_dynamic_invalid_target_reason(self, state: "State", caster_id: int, target_id) -> int:
        """Le delegue `options+0x38` (slot vtable `+0x480`) =
        `...ExemplarOfTheKauyonAbility$$GetDynamicInvalidTargetReason`. Le CORPS vit dans
        `targeting.py::_dynamic_rule_exemplar_of_the_kauyon` (mirror complet, avec la RE du
        `Remove(caster)` trouve par la mesure live sur `MC1_67`) : il y a ete ecrit quand la face
        COMBAT n'etait pas portee, et il y RESTE -- un seul foyer, deux appelants successifs.
        Son entree de `DYNAMIC_TARGET_RULE_UNPORTED` est retiree par le meme commit que cette
        classe (les deux tables `*_UNPORTED` sont disjointes d'`ABILITY_CLASSES`)."""
        return _dynamic_rule_exemplar_of_the_kauyon(state, caster_id, target_id)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        # #287-r14 RESOLUTION DE CIBLE -- `IdunBattle.Core.Services.TargetingQuery$$GetActualTarget`
        # via le slot 16 d'`IActiveAbility` : pour un masque `TargetIsTile`, le role `target` du
        # natif est TOUJOURS l'entite-TUILE, que l'appelant ait passe la tuile ou son occupant.
        # IDEMPOTENT (`GetMainTile(<tuile>)` rend la tuile) -> inerte quand `AbilityHandler` a
        # deja resolu, mordant sur tout appel DIRECT (tests de migration, probes).
        target_id = self.get_actual_target(state, caster_id, target_id)
        board = getattr(state, "board", None)
        entities = entities_from_state(state, caster_id)
        # COLLAPSE de `DSLSelectors.Entity(<AbilityEntities+0x40 = casterTile>)` : l'id d'entite-tuile
        # du caster, LU MAINTENANT (avant le `Teleport` de l'arbre), comme le natif le capture a la
        # construction de l'`AbilityEntities`.
        ex_tiles = CasterTile(as_ids=True).evaluate(entities) or []
        ex_tile_id = int(ex_tiles[0]) if ex_tiles else None
        # COLLAPSE de `target@0x60` : le cast est TILE-TARGET, donc `target_id` est un id du
        # `board`, pas une entite de `state.entities` (meme lecture que `DutyEternalAbility`).
        dest_tile_id = (int(target_id) if (board is not None and target_id is not None
                                           and int(target_id) in board.by_id) else None)
        if dest_tile_id is None:
            return {"ability": EXEMPLAR_OF_THE_KAUYON_ID, "caster": caster_id,
                    "target": target_id, "ex_tile": ex_tile_id, "teleport": [], "posed": [],
                    "attacks": [], "removed": [], "spawned": [], "dsl": True}
        ectx = ExecutionContext(state=state, rng=state.rng)
        exemplar_of_the_kauyon_tree(dest_tile_id, ex_tile_id).execute(entities, ectx)
        return {"ability": EXEMPLAR_OF_THE_KAUYON_ID, "caster": caster_id, "target": target_id,
                "ex_tile": ex_tile_id, "dest_tile": dest_tile_id,
                "teleport": [p for n, p in ectx.emitted if n == "Teleport"],
                "posed": [p for n, p in ectx.emitted if n == "AddEffect"],
                "attacks": [p for n, p in ectx.emitted if n == "PerformAIAttack"],
                "removed": [p for n, p in ectx.emitted if n == "RemoveEffect"],
                "spawned": [p["unit"] for n, p in ectx.emitted if n == "SpawnUnit"],
                "dsl": True}


# =========== ExemplarOfTheMontka (`tauFarsight` « Commander Farsight », actif 1210) ===========

EXEMPLAR_OF_THE_MONTKA_ID = "ExemplarOfTheMontka"
EXEMPLAR_OF_THE_MONTKA_BUFF = int(EffectType.ExemplarOfTheMontka)     # 0x5da = 1498
#: `UnitSelectionType.OnlyAliveAndTargetable` -- le 4e argument natif de `Friends` ET le 4e
#: d'`UnitsWithTrait`, tous deux LUS a `0x3` dans le decompile de `...$$ExecuteBehaviour`.
_MONTKA_SELECTION = int(UnitSelectionType.OnlyAliveAndTargetable)     # 3
#: `UnitsWithTrait(<...>, 0x10, 3)` -- `0x10 = 16 = UnitTrait.Hero` (qualifie : 16 vaut
#: `EffectType.None` et `AbilityConstantType.nrOfSummons` dans d'AUTRES enums).
_MONTKA_TRAIT = int(UnitTrait.Hero)                                   # 0x10 = 16


def exemplar_of_the_montka_buff_targets():
    """Le selecteur-cible d'`IdunBattleLogic.Entities.Abilities.Active.Loki.
    ExemplarOfTheMontkaAbility$$ExecuteBehaviour` -- MIRROR 1:1 du DECOMPILE, trois noeuds,
    aucune logique en plus :

        UnitsWithRangedWeapons(
            UnitsWithTrait( Friends( of        = <DSLSelectors+0x48 = Caster>,
                                     entities  = <DSLSelectors+0x20 = AllAliveUnits>,
                                     selection = 3 ),
                            trait     = 0x10 = UnitTrait.Hero,
                            selection = 3 ) )

    ⚠ **LE CASTER ENTRE PAR LE FILTRE, PAS PAR UNE EXCEPTION** -- et c'est la difference de fond
    avec le jumeau de forme `WarHowlAbility$$ExecuteBehaviour` (1106), qui SOUSTRAIT l'Owner du
    pool (`op_Subtraction(<+0x20>, <+0x30>)`) puis le RE-AJOUTE par un `op_Addition`. Ici il n'y a
    NI soustraction NI addition : `entities` est le pool ENTIER, et `IdunBattle.Entities.
    UnitExtensions$$IsFriend` n'ecarte pas l'egalite, donc le caster est son propre ami. CONSEQUENCE
    OBSERVABLE : Farsight ne se buffe que s'il satisfait LUI AUSSI les deux filtres. Il les
    satisfait au kit (`traits: [Hero, BeastSlayer, BigTarget, Flying, Mechanical]`, arme `Plasma`
    `Range 2`), mais un porteur qui perdrait `Hero` ou son arme distante ne se bufferait PAS -- la
    ou WarHowl buffe son caster inconditionnellement.

    ⚠ Le REFERENT de `Friends` est `<+0x48 = Caster>`, pas `<+0x30 = Owner>` : deuxieme ecart
    d'ecriture avec 1106, sans effet observable sur une ability ACTIVE (les deux slots designent le
    porteur qui caste) mais on ecrit les slots que le natif ecrit.

    ⚠ Le `selectionType = 3` (`OnlyAliveAndTargetable` = `IsAlive && !HasFlag(0x11 Untargetable)`)
    est passe aux DEUX noeuds qui l'acceptent -- MEME filtre, MEME mesure que #585 : il ecarte un
    allie en DEEP STRIKE que tous les autres filtres retiennent. `UnitsWithRangedWeapons`, lui,
    n'en prend PAS (son `Select` code en dur `SelectUniqueUnits(..., 1 = OnlyAlive)`).

    NI FACTION, NI RAYON : aucune borne de distance, aucune contrainte de sous-faction. Tout ami
    `Hero` porteur d'une arme distante du PLATEAU recoit le buff."""
    friends = Friends(AllAliveUnits(), reference=Caster(),        # Friends(of = Caster@+0x48, ...)
                      selection_type=_MONTKA_SELECTION)           # 4e argument natif : 3
    return UnitsWithRangedWeapons(
        UnitsWithTrait(friends, _MONTKA_TRAIT,                    # 0x10 = Hero
                       selection_type=_MONTKA_SELECTION))         # 4e argument natif : 3


def exemplar_of_the_montka_tree():
    """Arbre d'`IdunBattleLogic.Entities.Abilities.Active.Loki.ExemplarOfTheMontkaAbility$$
    ExecuteBehaviour` -- MIRROR 1:1 du DECOMPILE, **un seul noeud** :

        Execute( AddEffect( 0x5da = 1498 ExemplarOfTheMontka,
                            abilityState = AActiveAbility$$get_AbilityStateReference,
                            source       = <DSLSelectors+0x48 = Caster>,
                            targets      = <exemplar_of_the_montka_buff_targets()>,
                            turns        = <DSLFormulas+0x20> ) )

    LA SURCHARGE D'`AddEffect` EST TRANCHEE PAR L'ADRESSE DE LA CIBLE DU `call`, pas a l'oeil : le
    binaire en porte QUATRE du meme nom, et le `e8` du site resout sur
    `IdunBattleLogic.Entities.DSLBehaviors.AddEffect(effectType, abilityState, source, targets,
    turns: IdunBattle.DSL.IAmountFormula)` -- la MEME que `WarHowlAbility$$ExecuteBehaviour`. Une
    source EXPLICITE est donc passee (pas de `source_from_target`).

    `turns` = `<DSLFormulas+0x20>`, un champ POSE PAR LE CTOR, pas un appel : `IdunBattleLogic.
    Entities.DSLFormulas$$.ctor` remplit un cache de constantes -- `+0x18 <- 0`, **`+0x20 <- 1`**,
    `+0x28 <- 2`, `+0x30 <- 100`, `+0x38 <- -1`. La duree est donc la constante **1**, et elle
    arrive telle quelle dans le `param_6` d'`IdunBattle.Operations.AddEffectOperation$$Execute`,
    qui ne la convertit PAS -> **1 TOUR**, d'ou `duration_turns=1` (et non `duration_rounds`).
    C'est le meme noeud, a la meme valeur, que le `DSLFormulas$$Get(1)` de 1106 -- ecrit ici par
    lecture du champ, la ou 1106 passe par la factory.

    `scale_from_source=True` = le PORT de l'`AbilityStateReference` (2e argument natif). Ce n'est
    PAS le `CreateSnapshot(abilityState)` de 1106 mais ca designe le MEME etat :
    `IdunBattle.Entities.Abilities.AActiveAbility$$get_AbilityStateReference` =
    `DSLSelectors$$AbilityState(<+0x48 = Caster>, AbilityType(<l'active courante>))`, donc l'etat
    d'ability du CASTER. Ce n'est pas cosmetique : `extraDmg` ET `extraDmg_2` sont TOUS DEUX dans
    `variablesAffectedByRarityBonus` du kit, et le multiplicateur de rarete differe d'une unite a
    l'autre (mesure #585 : 200 contre 180) -- lire le scaling sur le BUFFE donnerait un ecart
    NUMERIQUE et SILENCIEUX.

    `source_ref=Caster()` = le 4e argument NATIF (`<DSLSelectors+0x48>`).

    AUCUNE ATTAQUE, AUCUN DEGAT DIRECT : `ExecuteBehaviour` n'appelle ni `AttackWithAttackDamage`
    ni `AttackWithAbilityDamage`, et la classe native n'a que DEUX methodes en tout (`ExecuteBehaviour`
    et `.ctor` -- slots contigus du bloc `methodPointers`, entre `ExemplarOfTheKauyonAbility$$.ctor`
    et `ExplosivePresentsAbility$$ExecuteBehaviour`). Le `+Damage` de l'i2 appartient a l'EFFET
    1498 (`entities/effects/loki/exemplar_of_the_montka.py`), pas au cast."""
    return AddEffect(EXEMPLAR_OF_THE_MONTKA_BUFF, EffectType.ExemplarOfTheMontka.name,
                     exemplar_of_the_montka_buff_targets(),
                     duration_turns=1,               # `<DSLFormulas+0x20>` = 1 -> 1 TOUR, PAS 1 round
                     scale_from_source=True,         # `get_AbilityStateReference` = l'etat du CASTER
                     source_ref=Caster())            # 4e argument natif = `<DSLSelectors+0x48>`


class ExemplarOfTheMontkaAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.ExemplarOfTheMontkaAbility$$ExecuteBehaviour`
    (id 1210, `tauFarsight` « Commander Farsight », Tau/FarsightEnclaves, HERO). Cast SELF.

    i2 : « Until the end of this turn, Commander Farsight and all other friendly Characters with a
    normal ranged attack gain Unstoppable and all their normal attacks deal +{extraDmg} Damage.
    When attacking a Big Target, they deal +{extraDmg_2} Damage instead. Using Exemplar of the
    Mont'ka does not end Commander Farsight's turn. »

    QUATRE mecaniques, appariees une a une aux artefacts natifs :
      1. ciblage « Farsight and all other friendly Characters with a normal ranged attack »
         -> `exemplar_of_the_montka_buff_targets()` (les trois noeuds du selecteur) ;
      2. « gain Unstoppable » -> `ExemplarOfTheMontkaEffect.applied_traits` (AddTrait 0x412,
         temporaire), face DEJA portee par cette meme tranche ;
      3. « +{extraDmg} Damage / +{extraDmg_2} vs Big Target »
         -> `...ExemplarOfTheMontkaEffect$$CreateEffectDamageBonusForAttack` ;
      4. « does not end Farsight's turn » -> 1210 est DEJA dans `NO_END_TURN_ABILITY_TYPES` **et**
         dans `NO_ABILITY_USED_FLAG_ABILITY_TYPES` (`runner/abilities/base.py`, inventaire #139) --
         aucune ecriture necessaire ici, et c'est ce qui rend le cast REPETABLE dans le tour si
         aucun cooldown ne l'en empeche (le kit 1210 n'en declare aucun : ses `variables` sont
         `extraDmg` / `extraDmg_2`, et il n'a NI `constants` NI `cooldownTurns`).

    Kit gameconfig 1210 : `extraDmg[level]`, `extraDmg_2[level]`, les DEUX dans
    `variablesAffectedByRarityBonus`. Aucune constante -> aucun `GetNumberConstant` a lire.

    Retour : {posed, dsl}."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.ExemplarOfTheMontka)     # 0x4ba = 1210
    ABILITY_ID = EXEMPLAR_OF_THE_MONTKA_ID

    # GATE DE CIBLE (#115) + PORTEE (#241) -- forme **STATIC-COPY** : `...ExemplarOfTheMontkaAbility$$
    # .ctor` recopie les 0x40 octets de `<TargetingOptions statics>+0x280` dans une struct locale et
    # la passe TELLE QUELLE a `AActiveAbility$$.ctor(this, &opts, 2)` -- il n'appelle AUCUNE surcharge
    # de `TargetingOptions$$.ctor`, ni la forme « flags directs » ni la forme PRESET+FLAGS. Le masque
    # effectif est donc la constante ecrite par `IdunBattle.Core.Services.TargetingOptions$$.cctor`
    # en `<preset>+0x28`, RE-LUE au decompile de ce build :
    #     0x8004 = CasterIsPossibleTarget(0x8000) | CasterMatchesDynamicRule(0x4)
    # Decomposition EXHAUSTIVE, aucun bit residuel. C'est le MEME preset que `1215
    # InstrumentsOfVengeance` (STATIC-COPY nue, sans flags), et celui de `1216 MartialExemplar` /
    # `1192 NovaBoost` MOINS leur `additionalRules = 0x10` -> 1210 n'a PAS `CasterHasNotMoved` :
    # elle reste castable APRES deplacement.
    # ⚠ `CasterMatchesDynamicRule` (0x4) delegue a `GetDynamicInvalidCasterReason` (`options+0x30`).
    # La classe native NE LE SURCHARGE PAS -- le bloc `methodPointers` ne lui donne que deux slots
    # (`ExecuteBehaviour`, `.ctor`) -- donc le delegue reste le DEFAUT de `AActiveAbility`, qui ne
    # refuse rien. Aucun `get_dynamic_invalid_caster_reason` a poser ici.
    # `isSelfCasting` = `<preset>+0x00` = 1 ; `forceMeleeTarget` = `<preset>+0x20` = 1 = RangedBool.False.
    # PORTEE : le bloc `<preset>+0x08..0x1f` est la copie de `<TargetingRange statics>+0x60` faite par
    # `TargetingOptions$$.cctor`, soit **RANGE_SELF** (`overrideRange = Nullable(0)`) -- lecture DEJA
    # etablie et re-verifiee ici (cf. `darkangels.py::MartialExemplarAbility`, #923). Portee NULLE :
    # toute cible autre que le caster tombe sur `range.Value(0) < d`, le gate attendu d'un self-cast.
    TARGETING_OPTIONS = TargetingOptions(
        rules=TR.CasterIsPossibleTarget | TR.CasterMatchesDynamicRule,
        self_cast=True, range=RANGE_SELF, force_melee_target=RANGED_BOOL_FALSE)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        entities = entities_from_state(state, caster_id)
        ectx = ExecutionContext(state=state, rng=state.rng)
        exemplar_of_the_montka_tree().execute(entities, ectx)
        return {"ability": EXEMPLAR_OF_THE_MONTKA_ID, "caster": caster_id, "target": target_id,
                "posed": [p for n, p in ectx.emitted if n == "AddEffect"], "dsl": True}


# ============ LOT BOSS RIPTIDE (`tauBossRiptide`, NPC) -- NovaShield 1194 / NovaBoost 1192 ===========
#
# LES TROIS `Nova*` SONT DES ABILITIES **2-PHASES**, PAS DES ATTAQUES. L'audit
# `combat-ability-coverage.md` les classe `DAMAGE(Particle)` -- cette colonne derive du
# `damageProfile` du KIT (l'arme du porteur), pas du behaviour. Les trois `ExecuteBehaviour` LUS
# ne portent AUCUN noeud d'attaque (`AttackWith*`), AUCUN `Spawn`, AUCUN `ChangeStat` : ils POSENT
# des effets `*_PendingAttack` / `*_PendingTarget` -- exactement le patron de `HeavyRailRifle`
# (1160) en tete de ce module. `minDmg`/`maxDmg`/`nrOfHits`/`damageProfile` du gameconfig
# appartiennent aux TRIGGERED de phase 2 (`Abilities.Triggered.Loki.NovaShield_AttackAbility`,
# `NovaBoost_AttackAbility`, `NovaCharge_AttackAbility`), HORS de ce port.
#
# `IdunBattleLogic.Entities.Abilities.Active.Loki.NovaShieldAbility$$ExecuteBehaviour` -- MIRROR 1:1
# du DECOMPILE (les quatre feuilles, dans l'ordre des trois `AbilityBehaviour.op_BitwiseAnd`) :
#
#   turns   = DSLFormulas.TurnsFromRounds( GetNumberConstant(config@0x60, 0x45 = nrOfRounds) )
#   shield  = DSLBehaviors.CreateShield( unitSelector = Caster@DSLSelectors+0x48,
#                                        amount       = DSLFormulas.Direct(
#                                                         GetVariableForLevel(0x27 = shieldHp)),
#                                        source       = AbilityOrEffect.op_Implicit(this),
#                                        turns        = turns,
#                                        createdByEffect = null,  stackable = TRUE )
#   block   = DSLBehaviors.AddStaticStatModifierEffect( targets  = Owner@DSLSelectors+0x30,
#                                        effectType = 0x588 = 1416 NovaShield_ExtraBlockChance,
#                                        statType   = 0x7 = StatType.BLOCK_CHANCE,
#                                        amount     = Direct(GetVariableForLevel(0x15=blockChance)),
#                                        turns      = turns,   isHidden = false )
#   marked  = DSLSelectors.Filter( Target@+0x60 op_Addition AdjacentTiles(Target@+0x60),
#                                  op_LogicalNot( DSLTriggers.IsTrenchTile(ActiveTarget@+0x68) ) )
#             (== `NovaShieldAbility$$GetMarkedTiles`, fonction NOMMEE dont le corps est REPRIS
#              INLINE par `ExecuteBehaviour` -- meme motif que `TwinSmartMissileSystem`)
#   mark    = DSLBehaviors.AddEffect( 0x587 = 1415 NovaShield_PendingTarget, AbilityStateReference,
#                                     targets = marked, turns = NULL )        # surcharge **5-args**
#   pending = DSLBehaviors.AddBondEffect( 0x586 = 1414 NovaShield_PendingAttack,
#                                     AbilityStateReference, source = Owner@+0x30,
#                                     targets = Owner@+0x30, bondedEntity = Owner@+0x30,
#                                     options = <struct 0x20 octets ZERO> )
#   Execute( ((shield & block) & mark) & pending )
#
# ⚠ LA SURCHARGE D'`AddEffect` EST LA 5-ARGS (SANS selecteur SOURCE), et ca change la SOURCE de
# l'effet pose. Le build porte quatre corps : `(this, effectType, abilityState, source, targets,
# options)`, `(..., source, targets, turns)` et DEUX `(this, effectType, abilityState, targets,
# turns)`. Le site de 1194 passe CINQ arguments (`AddEffect(behaviors, 0x587, absRef, marked, 0)`)
# -> pas de selecteur source, donc `AddEffectBehaviour$$Execute` prend sa branche
# « `if (<selecteur source> != 0) src = <ce resultat>` sinon `src = <cible courante>` » : **chaque
# TUILE marquee est sa propre source** (`source_from_target=True` cote port). NovaBoost et
# NovaCharge, eux, passent SIX arguments avec `Caster@+0x48` en source -- la difference est
# INVISIBLE au nom de la fonction et se lit uniquement a l'arite.

NOVA_SHIELD_ID = "NovaShield"
NOVA_SHIELD_PENDING_ATTACK = int(EffectType.NovaShield_PendingAttack)          # 0x586 = 1414
NOVA_SHIELD_PENDING_TARGET = int(EffectType.NovaShield_PendingTarget)          # 0x587 = 1415
NOVA_SHIELD_EXTRA_BLOCK_CHANCE = int(EffectType.NovaShield_ExtraBlockChance)   # 0x588 = 1416


def _nova_ability_scaling(state: "State", caster_id: int, ability_type: int) -> tuple:
    """`(level, multiplier_pct)` a passer a `ability_var` = l'**`AbilityState` PER-ABILITY** du
    caster, mirror EXACT du 3e argument d'`IdunBattle.Configuration.AbilityConfiguration$$
    GetVariableForLevel(type, abilityState, fallback)`.

    Le decompile ne laisse aucun doute sur QUEL etat le natif indexe : `ExecuteBehaviour(this,
    abilityState, entities)` recopie `*(abilityState)` / `*(abilityState + 8)` dans un local et
    passe CE local -- c'est l'`AbilityState` de CETTE ability, celui que le canal `readAbilityState`
    (#100) publie dans `decisionView.units[].abilities[]` et que porte
    `ActiveAbility.level` / `.multiplier`.

    ⚠ CE N'EST PAS le canal GLOBAL `StatsComponent.ctx.active_ability_level` /
    `ability_variables_multiplier`, et les confondre est SILENCIEUX SUR UN HEROS et FAUX SUR UN
    BOSS. MESURE (#895, runner `GB_Riptide_01`, `tauBossRiptide:4`) : le canal global rend
    `level=0, mult=100` (`combatSnapshot.unitConfig` = `{"error": "config null"}` pour un npc),
    la ou `abilityStates[]` rend `level=55, multiplier=200` -- soit `shieldHp` **100** au lieu de
    **13686** (round(6843 x 200/100), le `Shields_InitialAmount` du cast natif). Un facteur 137.
    Le canal global reste le REPLI (unite dont le composant per-ability n'est pas seede : le
    canal exige `allAbilities: true`)."""
    e = state.get_entity(caster_id) if caster_id is not None else None
    if e is None:
        return (0, 100)
    comp = e.get_component(ActiveAbilitiesComponent)
    ab = comp.get(int(ability_type)) if comp is not None else None
    if ab is not None and ab.level is not None:
        return (int(ab.level), int(ab.multiplier if ab.multiplier is not None else 100) or 100)
    sc = e.get_component(StatsComponent)
    ctx = sc.ctx if sc is not None else None
    level = getattr(ctx, "active_ability_level", 0) if ctx is not None else 0
    mult = int(getattr(ctx, "ability_variables_multiplier", 100) or 100) if ctx is not None else 100
    return (level, mult)


def nova_shield_marked_tiles():
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.NovaShieldAbility$$GetMarkedTiles` (MIRROR) :

        Filter( Target@+0x60 op_Addition AdjacentTiles(Target@+0x60),
                NOT IsTrenchTile(ActiveTarget@+0x68) )

    Le cast est TILE-TARGET (`TargetIsTile`, cf. `TARGETING_OPTIONS`), donc `Target@+0x60` est
    l'ENTITE-TUILE visee (`entities_from_state` la materialise, #287-r12) -- la zone marquee est
    « la tuile ciblee + sa couronne », TRENCHES EXCLUES. `AdjacentTiles` exclut deja l'origine
    (`AdjacentTilesSelector$$Select` : `if (!tiles.Contains(a))`), donc l'`op_Addition` ne fait
    aucun doublon. Le predicat lit `ActiveTarget@+0x68`, le slot que `Filter`
    (`FromTriggerSelector$$Select`) ecrase a chaque element."""
    return Filter(Union(Target(), AdjacentTiles(Target())),
                  Not(IsTrenchTile(ActiveTarget())))


def nova_shield_tree(state: "State", caster_id: int):
    """Arbre de `...NovaShieldAbility$$ExecuteBehaviour` (MIRROR 1:1, cf. le bloc ci-dessus).

    `shieldHp` (0x27) et `blockChance` (0x15) sont des `GetVariableForLevel` -> COLLAPSE V en
    scalaire (doctrine slice-18/19), lus par `ability_var` avec le niveau + le multiplier de
    rarete du caster. `nrOfRounds` (0x45) est un `GetNumberConstant` -> `constants` du kit.
    `TurnsFromRounds` = `convert_rounds_to_turns` pour les DEUX consommateurs (le bouclier et
    l'effet de blockChance partagent le MEME noeud natif `pvVar6`)."""
    level, mult = _nova_ability_scaling(state, caster_id, int(ActiveAbilityType.NovaShield))
    shield_hp = int(ability_var(NOVA_SHIELD_ID, "shieldHp", level, multiplier_pct=mult) or 0)
    block_chance = int(ability_var(NOVA_SHIELD_ID, "blockChance", level, multiplier_pct=mult) or 0)
    rounds = int(ability_var(NOVA_SHIELD_ID, "nrOfRounds", is_constant=True) or 0)
    turns = convert_rounds_to_turns(state, rounds)             # noeud `TurnsFromRounds(nrOfRounds)`
    # `stackable = true` (7e arg natif) == le comportement de `ShieldComponent.add_or_update_shield`
    # (cumul meme-source/meme-duree) ; `source` = `AbilityOrEffect(this)` -> l'id d'ability sert
    # d'etiquette de source, c'est ce que le natif utilise pour decider du cumul.
    shield = CreateShield(Caster(), shield_hp, duration=turns, source=NOVA_SHIELD_ID)
    block = AddStaticStatModifierEffect(Owner(), NOVA_SHIELD_EXTRA_BLOCK_CHANCE,
                                        int(StatType.BLOCK_CHANCE), block_chance,
                                        name=EffectType.NovaShield_ExtraBlockChance.name,
                                        duration_turns=turns)
    mark = AddEffect(NOVA_SHIELD_PENDING_TARGET, EffectType.NovaShield_PendingTarget.name,
                     nova_shield_marked_tiles(), duration_rounds=None, source_from_target=True)
    pending = AddBondEffect(NOVA_SHIELD_PENDING_ATTACK, EffectType.NovaShield_PendingAttack.name,
                            Owner(), Owner(), duration_rounds=None, bonded_ref=Owner())
    return op_and(op_and(op_and(shield, block), mark), pending)


class NovaShieldAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.NovaShieldAbility$$ExecuteBehaviour` (id 1194,
    `tauBossRiptide` -- Tau, **NPC boss de guilde**). Cast TILE-TARGET.

    Kit gameconfig 1194 : `shieldHp[level]`, `blockChance[level]`, `nrOfRounds=1`,
    `damageProfile=Particle`, `nrOfHits=6`, `cooldownTurns=2` -- les trois dernieres constantes et
    `minDmg`/`maxDmg` appartiennent a la PHASE 2 (triggered), pas au cast.

    OBSERVABLE DU CAST : (1) un BOUCLIER `shieldHp` sur le caster, duree `TurnsFromRounds(1)` ;
    (2) l'effet 1416 `NovaShield_ExtraBlockChance` sur le caster, porteur d'un stat-mod STATIQUE
    `+blockChance` sur `StatType.BLOCK_CHANCE`, meme duree ; (3) l'effet 1415
    `NovaShield_PendingTarget` sur la tuile ciblee ET sa couronne (trenches exclues), duree
    DEFAUT ; (4) l'effet-BOND 1414 `NovaShield_PendingAttack` sur le caster, bonde a lui-meme,
    duree DEFAUT. Le degat vient de la phase 2, armee par (4) et dirigee par (3).

    Flags de tour : defauts base (1194 absent des tables d'override `NO_END_TURN_ABILITY_TYPES` /
    `NO_ABILITY_USED_FLAG_ABILITY_TYPES`) -> l'ability termine le tour + pose ActiveAbilityUsed."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.NovaShield)   # 1194
    ABILITY_ID = NOVA_SHIELD_ID

    # GATE DE CIBLE (#115) + PORTEE (#241) -- forme de ctor = **PRESET STATIQUE COPIE** (la 3e des
    # trois formes) : `...NovaShieldAbility$$.ctor` n'appelle AUCUN
    # `IdunBattle.Core.Services.TargetingOptions$$.ctor`. Il recopie les 0x40 octets du champ
    # STATIQUE de `TargetingOptions` a l'offset **`+0x1c0`** du bloc `<class>+0xb8`, puis :
    #     AActiveAbility..ctor(this, &opts, 2)   # 3e arg = 2 = AbilityAttackType.Others
    # Le masque EFFECTIF est la constante ecrite par
    # `IdunBattle.Core.Services.TargetingOptions$$.cctor` a `<preset>+0x28` = `*(statics+0x1e8)`.
    #
    # Le preset lu EN ENTIER (bloc `statics+0x1c0` du `cctor`) :
    #     <preset>+0x00 = *(statics+0x1c0) = 0                -> isSelfCasting = false
    #     <preset>+0x08 = copie de `TargetingRange statics+0x48` -> **RANGE_WHOLE_BOARD**
    #                     (`+0x48` onlyAdjacent = 1 = `RangedBool.False`, `+0x4c` = 0x100 ->
    #                     `useWholeBoard = true`, overrideRange VIDE, func null) -- MEME bloc que
    #                     `HeavyRailRifle` 1160 en tete de module.
    #     <preset>+0x20 = *(statics+0x1e0) = 1                -> forceMeleeTarget = RangedBool.False
    #     <preset>+0x28 = *(statics+0x1e8) = **0x6000040**    -> le masque
    #     <preset>+0x30/+0x38 = 0                             -> ecrases par `AActiveAbility$$.ctor`
    #
    # Decomposition EXHAUSTIVE -- 0x40 + 0x2000000 + 0x4000000 = 0x6000040, aucun bit residuel :
    #     0x40        (bit  6) TargetIsTile                  -> regle de DOMAINE : la cible EST une
    #                 tuile (branche `GetActualTarget` -> `GetMainTile`). PORTEE
    #                 (`TargetingOptions.is_tile_targeting`).
    #     0x2000000   (bit 25) AllowObscuredTargetByElevation -> ASSOUPLISSEMENT du gate d'obstruction.
    #     0x4000000   (bit 26) AllowObscuredTargetByWalls     -> idem, volet murs.
    # AUCUNE regle de CAMP (`TargetIsEnemy`/`TargetIsFriendly` absentes) : 1194 vise n'importe
    # quelle TUILE, amie ou ennemie -> `refuses_all_enemy_targets` = False.
    TARGETING_OPTIONS = TargetingOptions(
        rules=TR.TargetIsTile | TR.AllowObscuredTargetByElevation | TR.AllowObscuredTargetByWalls,
        self_cast=False, range=RANGE_WHOLE_BOARD, force_melee_target=RANGED_BOOL_FALSE)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        # #287-r14 RESOLUTION DE CIBLE -- `IdunBattle.Core.Services.TargetingQuery$$GetActualTarget`
        # via le slot 16 d'`IActiveAbility` : pour un masque `TargetIsTile`, le role `target` du
        # natif est TOUJOURS l'entite-TUILE, que l'appelant ait passe la tuile ou son occupant.
        # IDEMPOTENT (`GetMainTile(<tuile>)` rend la tuile) -> inerte quand `AbilityHandler` a
        # deja resolu, mordant sur tout appel DIRECT (tests de migration, probes).
        target_id = self.get_actual_target(state, caster_id, target_id)
        entities = entities_from_state(state, caster_id, target_id)
        ectx = ExecutionContext(state=state, rng=state.rng)
        nova_shield_tree(state, caster_id).execute(entities, ectx)
        return {"ability": NOVA_SHIELD_ID, "caster": caster_id, "target": target_id,
                "shield": [p for n, p in ectx.emitted if n == "CreateShield"],
                "stat_mods": [p for n, p in ectx.emitted if n == "AddStaticStatModifierEffect"],
                "posed": [{"target": p.get("target"), "effect": p.get("effect_type")}
                          for n, p in ectx.emitted if n in ("AddEffect", "AddBondEffect")],
                "dsl": True}


# ---------------- NovaBoost (`tauBossRiptide`, NPC, actif 1192) ----------------
#
# `IdunBattleLogic.Entities.Abilities.Active.Loki.NovaBoostAbility$$ExecuteBehaviour` -- MIRROR 1:1 :
#
#   marked  = NovaBoostAbility$$GetMarkedTilesSelector()
#           = DSLSelectors.Filter( AdjacentTiles(Caster@DSLSelectors+0x48),
#                                  op_LogicalNot( DSLTriggers.IsTrenchTile(ActiveTarget@+0x68) ) )
#   pending = DSLBehaviors.AddBondEffect( 0x581 = 1409 NovaBoost_PendingAttack,
#                                  AbilityStateReference, source = Caster@+0x48,
#                                  targets = Caster@+0x48, bondedEntity = Owner@+0x30,
#                                  options = <struct 0x20 octets ZERO> )
#   mark    = DSLBehaviors.AddEffect( 0x582 = 1410 NovaBoost_PendingTarget, AbilityStateReference,
#                                  source = Caster@+0x48, targets = marked,
#                                  options = <struct 0x20 octets ZERO> )      # surcharge **6-args**
#   Execute( pending & mark )
#
# La zone marquee est la COURONNE DU CASTER (pas d'une cible) -- l'ability est SELF-CAST
# (`isSelfCasting = 1` dans son preset). AUCUN degat, AUCUN deplacement dans le cast : le « boost »
# (le SAUT visible dans `NovaBoost_AttackVisuals$$Flight` / `NovaBoost_AttackAbility$$
# GetLandPosition`) appartient a la TRIGGERED de phase 2, hors de ce port.

NOVA_BOOST_ID = "NovaBoost"
NOVA_BOOST_PENDING_ATTACK = int(EffectType.NovaBoost_PendingAttack)      # 0x581 = 1409
NOVA_BOOST_PENDING_TARGET = int(EffectType.NovaBoost_PendingTarget)      # 0x582 = 1410


def nova_boost_marked_tiles():
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.NovaBoostAbility$$GetMarkedTilesSelector`
    (MIRROR) : `Filter( AdjacentTiles(Caster@+0x48), NOT IsTrenchTile(ActiveTarget@+0x68) )`.

    ⚠ CONTRASTE avec `nova_shield_marked_tiles` : PAS d'`op_Addition` avec l'origine -- la tuile du
    caster elle-meme n'est PAS marquee, seulement sa couronne."""
    return Filter(AdjacentTiles(Caster()), Not(IsTrenchTile(ActiveTarget())))


def nova_boost_tree():
    """Arbre de `...NovaBoostAbility$$ExecuteBehaviour` (MIRROR 1:1, cf. le bloc ci-dessus).
    Les DEUX options-structs sont ZERO-initialisees -> aucune duree d'override : les effets
    1409/1410 prennent leur `DefaultAmountOfRounds` (meme lecture que 1333/1334 de HeavyRailRifle,
    ou l'effet est CONSOMME par la phase 2, pas expire par un timer)."""
    pending = AddBondEffect(NOVA_BOOST_PENDING_ATTACK, EffectType.NovaBoost_PendingAttack.name,
                            Caster(), Caster(), duration_rounds=None, bonded_ref=Owner())
    mark = AddEffect(NOVA_BOOST_PENDING_TARGET, EffectType.NovaBoost_PendingTarget.name,
                     nova_boost_marked_tiles(), duration_rounds=None, source_ref=Caster())
    return op_and(pending, mark)


class NovaBoostAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.NovaBoostAbility$$ExecuteBehaviour` (id 1192,
    `tauBossRiptide` -- Tau, **NPC boss de guilde**). Cast SELF.

    Kit gameconfig 1192 : `minDmg`/`maxDmg` + `damageProfile=Particle`, `nrOfHits=6`,
    `cooldownTurns=2` -- TOUS de phase 2. Le cast n'a AUCUNE variable propre.

    OBSERVABLE DU CAST : l'effet-BOND 1409 `NovaBoost_PendingAttack` sur le caster (bonde a
    lui-meme) + l'effet 1410 `NovaBoost_PendingTarget` sur les tuiles ADJACENTES au caster
    (trenches exclues), les deux a duree DEFAUT.

    GATE DYNAMIQUE NON PORTE (residu, cf. le rapport de tranche) :
    `NovaBoostAbility$$GetDynamicInvalidCasterReason` construit un `AbilityEntities` local avec le
    caster candidat, evalue `Enemies(Caster@+0x48, GetMarkedTilesSelector(), 3)` et rend
    `broken(4)` si le compte est `<= 1` -- « il faut AU MOINS DEUX ennemis dans la couronne ».
    C'est une regle de CASTER, appelee via `CasterMatchesDynamicRule` (bit 2 du masque, non porte
    par `get_invalid_caster_reason`) : le port est donc PERMISSIF sur ce point, jamais restrictif."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.NovaBoost)   # 1192
    ABILITY_ID = NOVA_BOOST_ID

    # GATE DE CIBLE (#115) + PORTEE (#241) -- forme de ctor = **PRESET + FLAGS** (la 2e des trois,
    # celle ou le litteral visible n'est PAS le masque effectif). `...NovaBoostAbility$$.ctor`
    # recopie les 0x40 octets du preset `<TargetingOptions statics>+0x280` puis appelle
    #     TargetingOptions..ctor(&opts, &preset, 0x10)
    #     AActiveAbility..ctor(this, &opts, 2)   # 3e arg = 2 = AbilityAttackType.Others
    # Le masque EFFECTIF = `<preset>+0x28` OR le litteral de flags. MEME couple que
    # `PrecisionShot` 1015 / `MartialExemplar` 1216 plus bas dans `targeting.py`.
    #
    # Le preset lu EN ENTIER (bloc `statics+0x280` du `cctor`) :
    #     <preset>+0x00 = *(statics+0x280) = 1                -> **isSelfCasting = true**
    #     <preset>+0x08 = copie de `TargetingRange statics+0x60` -> **RANGE_SELF** (`+0x60`
    #                     onlyAdjacent = 1 = `RangedBool.False`, `+0x68` overrideRange =
    #                     `Nullable(0)`, `+0x70` func null) -- MEME bloc qu'`EarlyWarningOverride`.
    #     <preset>+0x20 = *(statics+0x2a0) = 1                -> forceMeleeTarget = RangedBool.False
    #     <preset>+0x28 = *(statics+0x2a8) = **0x8004**       -> le masque du preset
    #     flags OR-es par le ctor                             = **0x10**
    #  => masque EFFECTIF = 0x8014.
    #
    # Decomposition EXHAUSTIVE -- 0x4 + 0x10 + 0x8000 = 0x8014, aucun bit residuel :
    #     0x10    (bit  4) CasterHasNotMoved         -> volet CASTER, PORTE
    #             (`get_invalid_caster_reason`) : le cast est REFUSE si le caster a deja bouge.
    #             ⚠ Coherent avec le fait que la phase 2 fait SAUTER le caster.
    #     0x4     (bit  2) CasterMatchesDynamicRule  -> `GetInvalidCasterReason` invoque la delegue
    #             `options[+0x30]` = `NovaBoostAbility$$GetDynamicInvalidCasterReason` (>= 2 ennemis
    #             dans la couronne). NON PORTEE -> degradation PERMISSIVE (cf. la docstring).
    #     0x8000  (bit 15) CasterIsPossibleTarget    -> flag DECLARATIF (preview / IA), deja mirrore
    #             (`TargetingOptions.can_target_caster`).
    TARGETING_OPTIONS = TargetingOptions(
        rules=TR.CasterMatchesDynamicRule | TR.CasterHasNotMoved | TR.CasterIsPossibleTarget,
        self_cast=True, range=RANGE_SELF, force_melee_target=RANGED_BOOL_FALSE)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        entities = entities_from_state(state, caster_id, target_id)
        ectx = ExecutionContext(state=state, rng=state.rng)
        nova_boost_tree().execute(entities, ectx)
        return {"ability": NOVA_BOOST_ID, "caster": caster_id, "target": target_id,
                "posed": [{"target": p.get("target"), "effect": p.get("effect_type")}
                          for n, p in ectx.emitted if n in ("AddEffect", "AddBondEffect")],
                "dsl": True}


# ================ ForwardObservers (1185, `tauNpc5StealthSuit` / `tauSmnStealthSuit`) ================
# Lot #996 -- « six no-op silencieuses » (docs/rl/case-996-six-no-op-silencieuses-reconnaissance.md).
#
# `IdunBattleLogic.Entities.Abilities.Active.Loki.ForwardObserversAbility$$ExecuteBehaviour`
# (MIRROR 1:1 du DECOMPILE) :
#
#   [1] AddEffect( 0x462 = 1122 Markerlight, AbilityStateReference,
#                  source = Owner@+0x30, targets = Target@+0x60,
#                  DSLFormulas$$TurnsFromRounds( GetNumberConstant(config@0x60, 0x45 = nrOfRounds) ) )
#   [2] AddEffect( 0x575 = 1397 ForwardObservers_DamageReduction, AbilityStateReference,
#                  source = Owner@+0x30, targets = Owner@+0x30,
#                  DSLFormulas$$TurnsFromRounds( GetNumberConstant(config@0x60, 0x77 = nrOfRounds_2) ) )
#   AActiveAbility$$Execute( op_Addition([1], [2]) )
#
# CATEGORIE ANNONCEE PAR L'AUDIT = EFFECT/BUFF -> **CONFIRMEE**. Cette colonne derive du
# `damageProfile` de l'ARME du porteur, pas du behaviour : elle ne vaut rien tant que
# l'`ExecuteBehaviour` n'a pas ete lu. Ici elle tombe juste ; ce n'est PAS le cas general (4 des 6
# no-op du lot #996 la portaient FAUSSE).
#
# LE POINT DE FIDELITE = LES DEUX DUREES SONT DISTINCTES. `nrOfRounds` (0x45) = 2 rounds pour le
# `Markerlight` pose sur la CIBLE ; `nrOfRounds_2` (0x77) = 1 round pour la reduction de degats
# posee sur SOI. Le natif lit DEUX constantes differentes du meme kit -- les confondre serait le
# premier ecart, et rien dans le nom ne le signale.
#
# LES DEUX CIBLES SONT DIFFERENTES AUSSI : `Target@+0x60` pour [1], `Owner@+0x30` pour [2]
# (`DSLSelectors+0x30` = Owner = `factory+0x148`, `DSLSelectors+0x60` = Target = `factory+0x178` --
# ecart constant de 0x118 entre les deux bases, cf. la docstring de `Owner`). Le buff defensif ne
# part PAS sur la cible.

FORWARD_OBSERVERS_ID = "ForwardObservers"
CONST_FO_ROUNDS = AbilityConstantType.nrOfRounds        # GetNumberConstant(0x45) -> "nrOfRounds"   = 2
CONST_FO_ROUNDS_2 = AbilityConstantType.nrOfRounds_2    # GetNumberConstant(0x77) -> "nrOfRounds_2" = 1
FORWARD_OBSERVERS_DMG_REDUCTION = int(EffectType.ForwardObservers_DamageReduction)   # 0x575 = 1397


def forward_observers_tree(state: "State"):
    """Arbre de `...ForwardObserversAbility$$ExecuteBehaviour` (MIRROR 1:1, cf. le bloc ci-dessus) :

        op_Addition( AddEffect(1122 Markerlight -> Target, TurnsFromRounds(nrOfRounds)),
                     AddEffect(1397 ForwardObservers_DamageReduction -> Owner,
                               TurnsFromRounds(nrOfRounds_2)) )

    Les deux durees passent par `duration_rounds` = le mirror DIRECT du noeud `TurnsFromRounds(n)`
    (`_resolve_duration` applique `IdunBattle.Core.Services.BattleQuery$$ConvertRoundsToTurns`) --
    surtout pas `duration_turns`, qui court-circuiterait la conversion."""
    rounds = int(ability_var(FORWARD_OBSERVERS_ID, CONST_FO_ROUNDS.name, is_constant=True) or 0)
    rounds_2 = int(ability_var(FORWARD_OBSERVERS_ID, CONST_FO_ROUNDS_2.name, is_constant=True) or 0)
    mark = AddEffect(MARKERLIGHT, EffectType.Markerlight.name, Target(), duration_rounds=rounds)
    self_buff = AddEffect(FORWARD_OBSERVERS_DMG_REDUCTION,
                          EffectType.ForwardObservers_DamageReduction.name,
                          Owner(), duration_rounds=rounds_2)
    return op_add(mark, self_buff)


class ForwardObserversAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.ForwardObserversAbility$$ExecuteBehaviour`
    (id 1185, `tauNpc5StealthSuit` npc + `tauSmnStealthSuit` SUMMON -- Tau). Cast UNIT-TARGET.

    Kit gameconfig 1185 : `range=3`, `dmgPctReduction=50`, `nrOfRounds=2`, `nrOfRounds_2=1` -- que
    des CONSTANTES, aucune variable de niveau, aucun profil de degats. Le cast NE FRAPPE PAS.

    OBSERVABLE porte : (1) `Markerlight` (1122) pose sur la CIBLE pour `ConvertRoundsToTurns(2)` ;
    (2) `ForwardObservers_DamageReduction` (1397) pose sur le CASTER pour `ConvertRoundsToTurns(1)`.

    RESIDU NOMME -- la MAGNITUDE de (2) n'est pas portee : `dmgPctReduction=50` est lu par
    `IdunBattle.Entities.Effects.Loki.ForwardObservers_DamageReductionEffect$$CreateEffectDamageMalusForDefense`,
    c'est-a-dire par l'EFFET, pas par cet `ExecuteBehaviour`. L'effet est donc POSE (visible,
    duree juste) mais INERTE sur le calcul de degats tant que cet artefact-la n'est pas porte.
    `Markerlight`, lui, est deja CONSOMME cote port (`twin_smart_missile_system_attack_targets`).

    Flags de tour : defauts base (1185 absent des tables d'override)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.ForwardObservers)   # 1185
    ABILITY_ID = FORWARD_OBSERVERS_ID

    # GATE DE CIBLE + PORTEE -- forme de ctor = **FLAGS DIRECTS** (la 1re des trois : le litteral
    # du ctor EST le masque). `...ForwardObserversAbility$$.ctor` :
    #     TargetingOptions..ctor(&opts, isSelfCasting=0, range=<TargetingRange statics+0x18>,
    #                            forceMeleeTarget=0, rules=0x200004002, 0, 0)
    #     AActiveAbility..ctor(this, &opts, 2)   # 3e arg = 2 = AbilityAttackType.Others
    #
    # Decomposition EXHAUSTIVE -- 0x2 + 0x4000 + 0x200000000 = 0x200004002, aucun bit residuel :
    #     0x2          (bit  1) TargetMatchesDynamicRule -> PORTE : la delegue est le slot VIRTUEL
    #                  `...ForwardObserversAbility$$GetDynamicInvalidTargetReason` (les deux champs
    #                  delegues du ctor sont NULS), mirrore par `_dynamic_rule_forward_observers`
    #                  et surcharge ci-dessous : refus si la cible porte DEJA `Markerlight`.
    #     0x4000       (bit 14) TargetIsEnemy            -> PORTE (refus sur un allie / sur soi).
    #     0x200000000  (bit 33) TargetIsNotAnObject      -> regle NON portee -> PERMISSIF.
    # PORTEE : `TargetingRange statics+0x18` = `RANGE_FROM_CONFIG` -> `AActiveAbility$$SetConfig
    # ValuesInTargetingOptions` y injecte la constante `range` du kit (= 3).
    # `forceMeleeTarget` = 0 = `RangedBool.True`.
    TARGETING_OPTIONS = TargetingOptions(
        rules=TR.TargetMatchesDynamicRule | TR.TargetIsEnemy | TR.TargetIsNotAnObject,
        self_cast=False, range=RANGE_FROM_CONFIG, force_melee_target=RANGED_BOOL_TRUE)

    def get_dynamic_invalid_target_reason(self, state: "State", caster_id: int,
                                          target_id: Optional[int]) -> int:
        """`...ForwardObserversAbility$$GetDynamicInvalidTargetReason` -- le mirror UNIQUE vit dans
        `targeting.py` (`_dynamic_rule_forward_observers`, deja ecrit et deja enregistre du temps ou
        1185 n'etait pas portee) ; cette surcharge ne fait que le rebrancher sur la classe."""
        return _dynamic_rule_forward_observers(state, caster_id, target_id)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        forward_observers_tree(state).execute(
            entities_from_state(state, caster_id, target_id), ectx)
        posed = [{"target": p.get("target"), "effect": p.get("effect_type"),
                  "placed": p.get("placed")}
                 for n, p in ectx.emitted if n == "AddEffect"]
        return {"ability": FORWARD_OBSERVERS_ID, "caster": caster_id, "target": target_id,
                "posed": posed, "dsl": True}