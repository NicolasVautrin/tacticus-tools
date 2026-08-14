"""`BattleFocus` -- passif `TriggeredAbilityType` 0x494 = **1172** + son effet
`EffectType.BattleFocus` 0x4af = **1199** (#1080).

i2 : « After attacking or being attacked, moves 1 hex in a direction as far away from enemies as
possible. »

PORTEURS (gate de confrontabilite, ventiles -- meme forme que case-1052) :
  * `eldarNpc1Guardian` -- **npc**, `units.npc[].stats[]` present (45 paliers) -> confrontable par
    le CHEMIN DE STATS EXPLICITE (`rl_duel build --explicit-stats eldarNpc1Guardian:45`, case-92
    Sec.5bis recours 4). Le porteur arrive avec SES stats, SES traits, SES armes ;
  * `eldarSmnGuardian` -- **summon**, `visualId == eldarNpc1Guardian` (le jumeau npc ci-dessus).
    **AUCUN invocateur n'existe** : un balayage EXHAUSTIF du gameconfig (tout `str` de l'arbre, pas
    seulement `constants.unitId*`) ne trouve cet `unitId` NULLE PART hors de sa propre definition
    (0 occurrence). C'est le cas 3 de case-1052 (« aucun invocateur du tout »), et c'est pourquoi
    l'audit rendait `S?` ; le jumeau NPC le rend confrontable quand meme.

================================================================================================
RE (decompile ghidra, build `rnca9r7q6c`) -- decompile = verite
================================================================================================
Le passif se joue en TROIS temps, et AUCUN des trois n'est un `CreateTrigger` de l'ability :

## 1. POSE -- `IdunBattleLogic.Entities.Abilities.Triggered.Loki.BattleFocusAbility`
       : `IdunBattle.Entities.Abilities.AOwnerEffectTriggeredAbility`

    AOwnerEffectTriggeredAbility$$CreateTrigger   = OnOwnerSpecificAbilityInit(<this+0x10> = 1172)
    AOwnerEffectTriggeredAbility$$CreateBehaviour = If( <slot 0x368 = la condition de la classe>,
        AddEffect( <slot 0x378 = GetEffectType()> = 0x4af,
                   AbilityState(Owner@<DSLSelectors+0x30>, AbilityType(abilityState)),
                   source  = Owner@<+0x30>,
                   targets = Owner@<+0x30>,
                   turns   = <struct ZEROEE> ) )
    ...BattleFocusAbility$$GetEffectType          = return 0x4af;                    # 1199

L'ability POSE donc l'effet 1199 sur son PROPRE porteur des l'init -- canal `O` de l'audit, porte
par `ABILITY_INIT_OWNER_EFFECTS`, pas par un trigger d'event. CONFIRME LIVE (2026-08-14) :
`decisionView` rend `u81 [eldarNpc1Guardian] <MOI>: BattleFocus` des le deploiement du runner.

## 2. DETECTION -- `IdunBattle.Entities.Effects.Loki.BattleFocusEffect$$CreateTargetTrigger`

      NOT IsMoving(Owner@<DSLSelectors+0x30>)
    & CanMove(Owner@<+0x30>)
    & (   On(0xb = UnitAbility, ownerNeedsToBeAlive: 1)
        & AbilityHasAttackType(CurrentAbility@<DSLSelectors+0x88>,
                               AbilityAttackType.DirectTargetAttack = 0)
        & ( get_OwnerIsTarget | get_OwnerIsCaster ) )

⚠ **L'ORDRE des `op_BitwiseAnd` est celui ci-dessus** (le decompile termine par
`op_BitwiseAnd(<NOT IsMoving & CanMove>, <le reste>)`), et il est sans effet numerique -- il est
ecrit ainsi pour rester relisible contre le decompile.

⚠ **`AbilityHasAttackType(..., 0)` SEUL, pas la disjonction `0 | 1`** de `SwornProtector` : le
`SummonAndAttackTarget` (1) est EXCLU. Le port passe donc par `ability_has_attack_type(t, 0)`, pas
par `ability_is_attack`.

⚠ **`get_OwnerIsTarget | get_OwnerIsCaster`** = le << after attacking OR being attacked >> de l'i2,
en UN seul vecteur. `On(0xb)` est publie INCONDITIONNELLEMENT par
`IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal` apres l'execution de la behaviour,
donc il couvre l'attaque NORMALE comme un cast (#928).

## 3. DEPLACEMENT -- `...BattleFocusEffect$$CreateTargetTriggerBehaviour` puis la branche `Custom`

    CreateTargetTriggerBehaviour = TriggerAbilityDelayed(
        entity: Owner@<DSLSelectors+0x30>,
        triggeredAbilityType: 0x494 = 1172 BattleFocus,
        unitSelectionType: UnitSelectionType.OnlyAliveAndTargetable = 3 )

    ...BattleFocusAbility$$CreateBehaviour(abilityState, triggerType) :
        if (triggerType != 0x20 = EventTriggerType.Custom)
            return AOwnerEffectTriggeredAbility.CreateBehaviour(abilityState, triggerType);
        return CreateMoveBehaviour();

    ...BattleFocusAbility$$CreateMoveBehaviour() :
        base    = CanAddUnit( AdjacentTiles(Owner@<+0x30>) )
        tiles   = TilesWithoutPowerUps(base).Otherwise(base)
        avoid   = NonSteppableOrObjectUnits( Enemies(Owner@<+0x30>,
                                                     _allAliveUnits@<DSLSelectors+0x20>,
                                                     UnitSelectionType 3),
                                             UnitSelectionType 3 )
        tiles   = SafestTiles(tiles, Owner@<+0x30>, avoid)
        tiles   = PickRandomly(tiles, amount: 1, allowDuplicates: 0,
                               maxDuplicatesAllowed: 0x7fffffff, ignoreForcedTargets: 0)
        return IfAlive( Owner@<+0x30>,
                        MoveUnit(Owner@<+0x30>, tiles, <MoveUnitBehaviourOptions ZEROEES>),
                        null )

**L'EFFET NE DEPLACE RIEN** : il ENFILE un re-declenchement de l'ability, et c'est le SECOND
passage (`triggerType == Custom`) qui bouge le porteur. Cabler le `MoveUnit` directement sur
`On(0xb)` donnerait le bon observable et le mauvais ORDRE -- le deplacement tomberait AU MILIEU de
la resolution de l'attaque au lieu d'apres (meme argument que `ShieldOfFaith`/`UnwaveringSentinel`).

Table des selecteurs partages (`IdunBattleLogic.Entities.DSLSelectors$$InitializeShared`, noms de
CHAMP mesures par #1064) : `+0x20 _allAliveUnits · +0x30 Owner · +0x88 CurrentAbility`.

================================================================================================
CE QUE `ABILITY_CLASSES` N'EXIGE PAS
================================================================================================
1172 est une `TriggeredAbilityType`, donc elle n'entre NI dans `ABILITY_CLASSES`, NI dans
`TARGETING_OPTIONS`, NI dans `ABILITY_ATTACK_TYPE` -- ces trois registres sont ceux des abilities
ACTIVES (meme constat que `Pyreblaster`, case-1052).

RESIDUS NOMMES
  * **`NOT IsMoving(Owner)` n'est PAS porte, et c'est une degradation PERMISSIVE assumee.**
    `IdunBattle.Entities.Triggers.IsMovingTrigger$$ShouldTrigger` lit un flag booleen du composant
    de mouvement de CHAQUE entite selectionnee (`<composant>+0xa8+<offset>`), qu'aucun canal du
    runner ne publie. Cote port le deplacement est ATOMIQUE (`MoveUnitOperation` termine avant que
    le vecteur `On(0xb)` ne parte), donc le flag natif serait FAUX a cet instant et le conjoint
    VRAI : le collapse est correct sur ce vecteur, et il ne le serait PAS sur un vecteur emis
    pendant une animation de deplacement. Residu `#1080-r1`.
  * **`CanMove(Owner)` ne tient que TROIS de ses quatre etages.**
    `IdunBattle.Entities.UnitExtensions$$CanMove` finit par
    `MovementComponent$$IsAllowedToMove`, qu'aucun canal ne publie -- residu PRE-EXISTANT du noeud
    `entities/triggers.py::CanMove`, herite tel quel (le trait `Stationary` = 0x418, lui, est
    porte).
  * `unitSelectionType = OnlyAliveAndTargetable` du `TriggerAbilityDelayed` : transporte, jamais
    LU -- MEME residu que les cinq call-sites deja portes.
  * `MoveUnitBehaviourOptions` ZEROEES (les 0x20 octets `local_58..uStack_20` du decompile) : le
    port n'a pas de structure d'options de deplacement a ce call-site, comme aux autres.
  * `PickRandomly(..., maxDuplicatesAllowed: 0x7fffffff, ignoreForcedTargets: 0)` : les deux
    derniers arguments sont transportes par le noeud et non lus.
"""
from __future__ import annotations

from typing import Optional

from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.behaviours import If
from .....entities.effect_type import EffectType
from .....entities.selectors.accessors import Owner
from .....entities.selectors.geometry import Otherwise, PickRandomly
from .....entities.selectors.tiles import (AdjacentTiles, AllAliveUnits, CanAddUnit, SafestTiles,
                                           TilesWithoutPowerUps)
from .....entities.selectors.units import Enemies, UnitsWithoutTrait
from .....entities.traits.unit_trait import UnitTrait
from .....entities.triggered_ability_type import TriggeredAbilityType
from .....entities.triggers import IsAlive
from .....entities.unit_selection_type import UnitSelectionType
from ....abilities.attack_type import ability_has_attack_type
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.lifecycle import TriggerAbilityDelayed
from ....abilities.behaviours.movement import MoveUnit
from ....components import UnitComponent
from ....state import State
from ..base import EffectTrigger, TriggeredAbility, TriggerEvent

#: `...BattleFocusAbility$$GetEffectType()` = `return 0x4af;` -- l'effet POSE, pas l'ability.
BATTLE_FOCUS_EFFECT = int(EffectType.BattleFocus)                    # 0x4af = 1199
#: `TriggerAbilityDelayed(..., 0x494, ...)` et `<this+0x10>` de l'ability -- l'ability RE-DECLENCHEE.
BATTLE_FOCUS_ABILITY = int(TriggeredAbilityType.BattleFocus)         # 0x494 = 1172
#: Cle du registre `ABILITY_INIT_OWNER_EFFECTS` / `EFFECT_CLASSES` = le NOM gameconfig, DERIVE du
#: mirror d'enum. Les deux enums portent le meme NOM a des ordinaux DIFFERENTS (cf. l'en-tete de
#: `entities/effects/loki/battle_focus.py`), donc le nom est le SEUL canal ou la faute serait visible.
BATTLE_FOCUS_KEY = TriggeredAbilityType.BattleFocus.name             # "BattleFocus"
#: `unitSelectionType` du `TriggerAbilityDelayed`, du `Enemies` et du `NonSteppableOrObjectUnits`.
_SEL = int(UnitSelectionType.OnlyAliveAndTargetable)                 # 3
#: `AbilityHasAttackType(CurrentAbility@<+0x88>, 0)` -- le litteral `0`, ecrit par son membre.
_DIRECT_TARGET_ATTACK = 0                                            # AbilityAttackType.DirectTargetAttack


def battle_focus_avoid_tree():
    """`NonSteppableOrObjectUnits( Enemies(Owner@<+0x30>, _allAliveUnits@<+0x20>, 3), 3 )`.

    `IdunBattleLogic.Entities.DSLSelectors$$NonSteppableOrObjectUnits(entities, selectionType)` =
    `entities & UnitsWithoutTrait(entities, UnitTrait.Steppable = 0x1b, sel)
              & UnitsWithoutTrait(entities, UnitTrait.Object = 0xd, sel)` (decompile deja lu par
    `entities/effects/loki/enmity_for_the_unworthy.py`). Le port l'exprime par la COMPOSITION des
    deux `UnitsWithoutTrait` -- l'intersection avec `entities` est structurelle (chaque filtre part
    du meme ensemble).

    ⚠ Ce filtre est LOAD-BEARING pour `SafestTiles` : sans lui, une mine `Steppable` ou un objet de
    decor compterait comme une unite a fuir, et le Guardian se rangerait du mauvais cote."""
    enemies = Enemies(AllAliveUnits(), reference=Owner(), selection_type=_SEL)
    return UnitsWithoutTrait(
        UnitsWithoutTrait(enemies, UnitTrait.Steppable, selection_type=_SEL),
        UnitTrait.Object, selection_type=_SEL)


def battle_focus_move_tree():
    """`...BattleFocusAbility$$CreateMoveBehaviour()` -- MIRROR, noeud par noeud (cf. l'en-tete Sec.3).

    `TilesWithoutPowerUps(base).Otherwise(base)` : `IdunBattle.DSL.TargetsSelector$$Otherwise(this,
    other)` rend `this` s'il est NON VIDE, `other` sinon -- donc « les tuiles libres SANS power-up,
    ou, s'il n'y en a aucune, toutes les tuiles libres ». Le port ecrit `Otherwise(primary=<sans
    power-up>, fallback=base)`, l'ORDRE du natif.

    `IfAlive(x, b, null)` est LITTERALEMENT `If(IsAlive(x), b)` (`DSLBehaviors$$IfAlive` appelle
    `DSLTriggers$$IsAlive` puis `DSLBehaviors$$If`) -> pas de noeud dedie, meme convention que les
    sept call-sites deja portes.

    `MoveUnit(Owner, tiles, <options ZEROEES>)` : le porteur se deplace d'UN hex (la source est
    `AdjacentTiles(Owner)`), donc `set_moved` reste au defaut du noeud."""
    base = CanAddUnit(AdjacentTiles(Owner()))
    tiles = Otherwise(TilesWithoutPowerUps(base), base)
    safest = SafestTiles(tiles, Owner(), battle_focus_avoid_tree())
    dest = PickRandomly(safest, amount=1)
    return If(IsAlive(Owner()), MoveUnit(Owner(), dest))


class BattleFocusEffectTrigger(EffectTrigger):
    """`...BattleFocusEffect$$CreateTargetTrigger` + `$$CreateTargetTriggerBehaviour` (Sec.2/Sec.3).

    Les conjoints du trigger sont COLLAPSES imperativement dans `matches` (doctrine #149 : la maison
    porte les `CreateTrigger` conjoint-par-conjoint et reserve les arbres DSL aux `CreateBehaviour`)
    -- sauf `CanMove`, qui passe par le noeud homonyme du depot pour ne pas dupliquer sa
    degradation NOMMEE.

    AUCUN deplacement ne tombe ici : le behaviour ENFILE, et le mouvement tombe au drain, dans
    `BattleFocusMoveAbility`."""
    event_id = int(EventTriggerType.UnitAbility)          # `On(0xb, ownerNeedsToBeAlive: 1)`
    effect_type = BATTLE_FOCUS_EFFECT                     # 1199

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        owner = state.get_entity(self.owner_id)
        if owner is None:
            return False
        # `ownerNeedsToBeAlive: true` du `On(...)`.
        uc = owner.get_component(UnitComponent)
        if uc is not None and not uc.alive:
            return False
        # `get_OwnerIsTarget | get_OwnerIsCaster` -- sur ce vecteur l'`actor_id` porte le CASTER
        # (`unit_ability_triggers(state, caster_id, target_id, ...)`), donc la disjonction est
        # « le porteur a attaque OU a ete attaque ».
        is_caster = ev.actor_id is not None and int(ev.actor_id) == int(self.owner_id)
        is_target = ev.target_id is not None and int(ev.target_id) == int(self.owner_id)
        if not (is_caster or is_target):
            return False
        # `AbilityHasAttackType(CurrentAbility@<+0x88>, DirectTargetAttack = 0)` -- SEUL, pas la
        # disjonction `0 | 1` de SwornProtector. `ability_type` est le `AbilityEntities.CurrentAbility`
        # threade par l'emetteur (`0x3f5` sur l'attaque normale, l'`ActiveAbilityType` sur un cast).
        if not ability_has_attack_type(ev.ability_type, _DIRECT_TARGET_ATTACK):
            return False
        # `CanMove(Owner@<+0x30>)` -- le noeud du depot (trait `Stationary` porte, `IsAllowedToMove`
        # residu NOMME). `NOT IsMoving(Owner)` : non porte, collapse a VRAI (residu `#1080-r1`).
        from .....entities.triggers import CanMove       # differe PORTEUR : triggers <- selectors
        ents = entities_from_state(state, int(self.owner_id))
        return bool(CanMove(Owner()).should_trigger(ents))

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        """`TriggerAbilityDelayed(Owner@<+0x30>, 0x494, OnlyAliveAndTargetable)` -- le porteur
        RE-DECLENCHE sa propre ability. Le noeud partage ENFILE (chemin « file ») des lors que 1172
        est inscrite dans `CUSTOM_TRIGGERED_ABILITIES` -- ce qu'elle est."""
        entities = entities_from_state(state, int(self.owner_id))
        ectx = ExecutionContext(state=state, rng=state.rng)
        TriggerAbilityDelayed(Owner(), BATTLE_FOCUS_ABILITY,
                              unit_selection_type=_SEL).execute(entities, ectx)
        delayed = [p for n, p in ectx.emitted if n == "TriggerAbilityDelayed"]
        return {"effect": BATTLE_FOCUS_KEY, "owner": int(self.owner_id),
                "vector": int(ev.event_id),
                "queued": bool(delayed and delayed[0].get("queued")), "dsl": True}


class BattleFocusMoveAbility(TriggeredAbility):
    """`...BattleFocusAbility$$CreateBehaviour`, branche **`triggerType == 0x20 = Custom`** -- LE
    DEPLACEMENT (Sec.3 de l'en-tete). Jamais atteinte par le bus d'events : l'ability n'ecrit pas
    de `CreateTrigger` propre a ce vecteur (le sien est `OnOwnerSpecificAbilityInit`), elle est
    inscrite dans `CUSTOM_TRIGGERED_ABILITIES[1172]` et n'est joignable que par le drain de
    `state.pending_triggered_abilities`.

    `matches` rend `True` : sur ce chemin le natif ne RE-EVALUE aucun trigger
    (`TriggerTriggeredAbilityOperation$$TriggerAbility` n'appelle que `ExecuteBehaviour`). La seule
    condition restante, `IfAlive(Owner)`, est DANS l'arbre -- donc evaluee a l'etat COURANT au
    moment du drain, exactement comme le natif : un porteur mort entre l'enfilement et le drain ne
    bouge pas."""
    event_id = int(EventTriggerType.Custom)               # 0x20 -- jamais emis par le bus du port
    TRIGGERED_ABILITY_ID = BATTLE_FOCUS_ABILITY           # 0x494 = 1172

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        return True

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        if state.rng is None:                             # `PickRandomly` consomme le PRNG
            return None
        entities = entities_from_state(state, int(self.owner_id))
        ectx = ExecutionContext(state=state, rng=state.rng)
        battle_focus_move_tree().execute(entities, ectx)
        moves = [p for n, p in ectx.emitted if n == "MoveUnit"]
        mv = moves[0] if moves else None
        return {"ability": BATTLE_FOCUS_KEY, "owner": int(self.owner_id),
                "moved": bool(mv), "to": (mv.get("tile") if mv else None), "dsl": True}
