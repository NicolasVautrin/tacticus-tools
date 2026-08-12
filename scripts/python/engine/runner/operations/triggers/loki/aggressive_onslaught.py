"""`AggressiveOnslaught` (`TriggeredAbilityType.AggressiveOnslaught` = 1248 = 0x4e0) -- passif de kit
de `bloodIntercessor` << Mataneo >> (HERO Blood Angels, Uncommon). RE : decompile ghidra, build
`rnca9r7q6c`.

## RECENSEMENT -- TROIS classes natives pour UN seul id de kit

Etabli par la COLONNE << classe declarante >> de `data/symbols/<build>/frida/methods.tsv` (le bloc
`methodPointers`), jamais par grep de nom. Le build ne porte **qu'un seul** membre
`TriggeredAbilityType` de ce nom (`1248=AggressiveOnslaught`, verifie dans
`data/symbols/<build>/frida/enums.tsv`) : les trois classes ci-dessous partagent donc cet id, forme
deja rencontree (`LetTheGalaxyBurn`, `SpecialIssueCombiMelta`).

| classe (toutes base `IdunBattle.Entities.Abilities.BaseTriggeredAbility`, lue dans `classes.tsv`) | corps propres |
|--------------------------------------------------------------------------------------------------|---------------|
| `IdunBattleLogic.Entities.Abilities.Triggered.Loki.AggressiveOnslaught_PrepareAbility`             | 3 (`.cctor`, `CreateTrigger`, `CreateBehaviour`) |
| `IdunBattleLogic.Entities.Abilities.Triggered.Loki.AggressiveOnslaught_SummonAbility`              | 4 (`CreateTrigger`, `CreateBehaviour`, `GetMaxSummon`, `GetPossibleSpawnTiles`) |
| `IdunBattleLogic.Entities.Abilities.Triggered.Loki.AggressiveOnslaught_UnsummonAbility`            | 2 (`CreateTrigger`, `CreateBehaviour`) |

`BaseTriggeredAbility` expose 23 corps : aucune des trois ne surcharge autre chose.
`IdunBattle.View.AbilityConfigs.Loki.AggressiveOnslaughtVisuals` (+ ses 6 classes generees) est de
la couche VUE -- hors perimetre. `IdunBattle.AI.Playbook.Loki.AggressiveOnslaughtPlaybook` est la
face DECISION, **deja portee** (`engine/playbook/aggressive_onslaught.py`, #58) ; `GetMaxSummon` et
`GetPossibleSpawnTiles` sont ses deux helpers (non virtuels), et `GetMaxSummon` y est deja mirroré.

## Les arbres natifs, lus verbatim

`AggressiveOnslaught_PrepareAbility$$CreateTrigger` :

    On(0x5 = PreAttack) & <DSLTriggers+0x20 = OwnerIsAlive> & get_OwnerIsCaster

`AggressiveOnslaught_PrepareAbility$$CreateBehaviour` :

    SetPersistentData( abilityType = AbilityOrEffect(this.Id),
                       unit        = Owner@<DSLSelectors+0x30>,
                       key         = DSLFormulas.Get("IsCharging"),
                       value       = IsCharging(Caster@<+0x48>, Target@<+0x60>) )

`AggressiveOnslaught_SummonAbility$$CreateTrigger` :

    persist = DSLFormulas.GetPersistentData(AbilityOrEffect(this.Id), Owner@<+0x30>, Get("IsCharging"))
    return ( On(0xb = UnitAbility) & <DSLTriggers+0x20 = OwnerIsAlive> & get_OwnerIsCaster )
           op_BitwiseAnd
           ( AmountIsGreaterThanZero(persist) op_BitwiseOr IsCharging(Caster@<+0x48>, Target@<+0x60>) )

`AggressiveOnslaught_SummonAbility$$CreateBehaviour` :

    unitId  = AbilityConfiguration.GetStringConstant(cfg, 0 = unitId)          # "bloodSmnIntercessor"
    options = SpawnUnitOptions.WithStatsFromConfig(cfg, abilityState, null, null)
    options.<+0x18> = DSLBehaviors.UseNormalAttackIfAble(caster = ActiveTarget@<+0x68>,
                                                        target = Target@<+0x60>,
                                                        parentAbility = AbilityOrEffect(this.Id),
                                                        triggerAbilityOrEffect = <vide>, options)
    tiles   = DSLSelectors.AdjacentTiles(TargetTiles@<DSLSelectors+0x78>)
    tiles   = DSLSelectors.CanAddUnit(tiles)
    tiles   = DSLSelectors.SortByDistance(tiles, originSelector = Caster@<+0x48>)
    tiles   = DSLSelectors.First(tiles, amount = Get(GetNumberConstant(cfg, 0x10 = nrOfSummons)),
                                 ignoreForcedTargets = false)
    tiles   = DSLSelectors.Cache(tiles, matchAbilityEntities = true)
    return DSLBehaviors.Spawn(parentSelector = Caster@<+0x48>, tiles = tiles,
                              spawnUnitId = unitId, options = options)

`AggressiveOnslaught_UnsummonAbility$$CreateTrigger` :

    On(0x12 = TurnStart_EffectActivation) & <DSLTriggers+0x20 = OwnerIsAlive>
      & <DSLTriggers+0x28 = IsTurnOf(Owner)>
      & AmountIsGreaterThanZero( DSLSelectors.Children(Owner@<+0x30>) )

`AggressiveOnslaught_UnsummonAbility$$CreateBehaviour` :

    RemoveUnit( DSLSelectors.Children(Owner@<+0x30>) )

i2 : « When charging, Mataneo summons {nrOfSummons} Jump Pack Intercessors adjacent to and
immediately attacking his target. At the beginning of each of Mataneo's turns, if he is still on the
battlefield, all Jump Pack Intercessors summoned this way leave the battlefield. »

## Les SURCHARGES, tranchees par `probe_951_call_targets.py` (jamais par le pseudo-C)

Le probe rend la SIGNATURE de la cible reelle de chaque `call rel32`, et deux d'entre elles
contredisent le voisin de forme qu'on aurait recopie :

  * **`DSLSelectors$$First(entities, amount: IAmountFormula, ignoreForcedTargets: bool)`** -- c'est
    la surcharge « les N PREMIERS » (`PickFirstNSelector`), PAS `First(source, index)`
    (`PickAtIndexSelector`, une classe DISTINCTE construite par une AUTRE factory). Porter l'index
    aurait spawn **1** intercessor au lieu de `nrOfSummons` = 2.
  * **`DSLBehaviors$$UseNormalAttackIfAble(caster, target, parentAbility, triggerAbilityOrEffect,
    options)`** -- le `caster` est `ActiveTarget@<+0x68>` (le summon FRAICHEMENT pose), pas le
    porteur : c'est le motif deja porte de `SendInTheNextWaveAbility$$ExecuteBehaviour`.
  * `SpawnUnitOptions$$WithStatsFromConfig(config, abilityState, abilitiesLevel, variableMultiplier)`
    -- les DEUX derniers sont `null` ici ; le couple `abilityState` est celui du PASSIF du summoner.

## Les SLOTS de contexte, ancres sur des fonctions NOMMEES

`<DSLSelectors+0x30>` = Owner, `<+0x48>` = Caster (`DSLTriggers$$get_OwnerIsCaster` =
`AreEqual(+0x30, +0x48)`), `<+0x60>` = Target (`$$get_OwnerIsTarget`), `<+0x68>` = ActiveTarget
(`DSLSelectors+0x68 == DSLFactory+0x180`, cf. `entities/selectors/accessors.py`), `<+0x78>` =
TargetTiles (`TargetTilesSelector$$Select` ; recoupe par
`LetTheGalaxyBurnAbility$$TargetHasTileEffect` = `HasTileStatusEffect(<+0x78>)`, deja porte).
`<DSLTriggers+0x20>` = `OwnerIsAlive` et `<+0x28>` = `IsTurnOf(Owner)` -- deja nommes par
`entities/triggers.py`.

⚠ **Le spawn est adjacent a la CIBLE, pas au porteur** : `AdjacentTiles(TargetTiles@<+0x78>)`. Le
tri, lui, est `SortByDistance(., Caster@<+0x48>)` -- les tuiles retenues sont donc les plus proches
de MATANEO parmi celles adjacentes a sa cible. Les deux selecteurs sont DIFFERENTS et se lisent ;
recopier l'un sur l'autre change les tuiles choisies des que la cible a plus de 2 voisines libres.

⚠ `GetPossibleSpawnTiles(target)` (le helper du PLAYBOOK) s'arrete a
`CanAddUnit(AdjacentTiles(target))` : il ne porte NI le tri NI le `First`. Ce n'est pas la meme
chaine que le behaviour -- ne pas en deduire l'autre.

## La cle de persistance est un LITTERAL, lu dans la table

`AggressiveOnslaught_PrepareAbility$$.cctor` ecrit `<statics>+0xb8 <- DAT_183383b20`, et
`metadata/string_literals.tsv` donne pour ce slot (`0x3383b20`) la chaine **`"IsCharging"`**. Le
`CreateTrigger` du SUMMON relit ce MEME champ statique -- les deux cotes partagent donc la cle par
construction, et non par convention de nommage.

## Pourquoi le `Prepare` existe -- l'ordre des evenements

`On(0xb = UnitAbility)` est emis par
`IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal` **APRES** l'execution du behaviour,
donc APRES que l'attaque a resolu. Or `IsCharging` est vide par
`IdunBattle.Operations.FinishUnitTurnOperation$$Execute` et, surtout, l'attaque elle-meme peut
avoir change l'etat. Le `Prepare` capture donc le fait « Mataneo CHARGEAIT » au moment
`On(0x5 = PreAttack)` -- AVANT l'attaque -- et le SUMMON accepte `persist > 0` **OU** un
`IsCharging` encore vrai a l'instant du declenchement (`op_BitwiseOr`). Le disjonct est ce qui rend
le passif robuste aux deux ordonnancements ; ne porter qu'une branche le rendrait intermittent.

## L'EMETTEUR de chaque evenement existe deja cote port -- verifie, pas suppose

`PreAttack` (5) -> `dispatch/attack.py::pre_attack_triggers` ; `UnitAbility` (0xb) ->
`dispatch/ability.py` ; `TurnStart_EffectActivation` (0x12) -> `dispatch/turn.py`. Aucun etage amont
a construire (contraste avec `On(PreUnitFled)`, qui n'existait que dans le mirror d'enum).

## Doctrine #149

Les trois `CreateTrigger` sont des gates d'EVENEMENT -> COLLAPSE imperatif dans `matches()`. Les
trois `CreateBehaviour` sont de VRAIS ARBRES DSL (feuilles `SetPersistentData` / `Spawn` /
`RemoveUnit` portees, sur des selecteurs portes).

ASCII only (console cp1252).
"""
from __future__ import annotations

from typing import Optional

from .....dsl.base import Const
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.formulas import GetPersistentData
from .....entities.selectors.accessors import ActiveTarget, Owner, Target, TargetTile
from .....entities.selectors.geometry import Cache, PickFirstN
from .....entities.selectors.tiles import AdjacentTiles, Caster, CanAddUnit, ChildrenOf
from .....entities.selectors.units import SortByDistance
from .....entities.triggered_ability_type import TriggeredAbilityType
from .....entities.triggers import IsCharging
from ....abilities.behaviours.combat import UseNormalAttackIfAble
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.lifecycle import RemoveUnit
from ....abilities.behaviours.persistent_data import SetPersistentData
from ....abilities.behaviours.summon import Spawn
from ....components import OwnerComponent, StatsComponent, UnitComponent
from ....state import State
from ..base import TriggeredAbility, TriggerEvent

ABILITY_ID = "AggressiveOnslaught"
ABILITY_TYPE = int(TriggeredAbilityType.AggressiveOnslaught)           # 0x4e0 = 1248

#: `AggressiveOnslaught_PrepareAbility$$.cctor` : `<statics>+0xb8 <- literal 0x3383b20`.
#: LU dans `data/symbols/<build>/metadata/string_literals.tsv`, jamais reconstruit du nom.
PERSIST_KEY = "IsCharging"

#: `AbilityConstantType` LUS au decompile (`GetStringConstant(cfg, 0)` / `GetNumberConstant(cfg, 0x10)`).
UNIT_ID_CONSTANT = "unitId"                    # `AbilityConstantType` 0
NR_OF_SUMMONS_KEY = "nrOfSummons"              # `AbilityConstantType` 0x10 = 16

_ON_PRE_ATTACK = int(EventTriggerType.PreAttack)                       # 0x5
_ON_UNIT_ABILITY = int(EventTriggerType.UnitAbility)                   # 0xb
_ON_TURN_START_EFFECTS = int(EventTriggerType.TurnStart_EffectActivation)   # 0x12


def _owner_alive(state: State, owner_id) -> bool:
    """`<DSLTriggers+0x20>` = `OwnerIsAliveAbilityTrigger$$ShouldTrigger` -- MIRROR :
    `!IsUnit(Owner) ? true : IsAlive(Owner)`. Owner introuvable -> True (le natif ne refuse pas)."""
    e = state.get_entity(owner_id) if owner_id is not None else None
    if e is None:
        return True                                   # branche `!EntityExtensions.IsUnit(Owner)`
    uc = e.get_component(UnitComponent)
    return True if uc is None else bool(uc.alive)


def _is_turn_of_owner(state: State, owner_id) -> bool:
    """`<DSLTriggers+0x28>` = `IsTurnOf(Owner@<DSLSelectors+0x30>)`. TRI-ETAT : proprietaire ou
    joueur courant NON MESURE -> la clause degrade en VRAI, jamais en FAUX invente (meme regle que
    le foyer `runner/components.py::is_turn_of_owner` et que `SanguinaryPriestAbility.matches`)."""
    e = state.get_entity(owner_id) if owner_id is not None else None
    oc = e.get_component(OwnerComponent) if e is not None else None
    cur = getattr(state, "current_player_id", None)
    owner_player = getattr(oc, "player", None) if oc is not None else None
    if owner_player is None or cur is None:
        return True
    return int(owner_player) == int(cur)


def _passive_scaling(state: State, owner_id: int) -> tuple:
    """`(passive_ability_level, ability_variables_multiplier)` du porteur -- le 2e argument
    `abilityState` de `SpawnUnitOptions$$WithStatsFromConfig`, sous lequel le summon monte SES
    PROPRES abilities. `AggressiveOnslaught` est un PASSIF -> `passive_ability_level`."""
    e = state.get_entity(owner_id)
    sc = e.get_component(StatsComponent) if e is not None else None
    ctx = getattr(sc, "ctx", None)
    if ctx is None:
        return 0, 100
    return (int(getattr(ctx, "passive_ability_level", 0) or 0),
            int(getattr(ctx, "ability_variables_multiplier", 100) or 100))


def aggressive_onslaught_max_summon(state: State, owner_id: int) -> int:
    """`AggressiveOnslaught_SummonAbility$$GetMaxSummon` = `GetNumberConstant(cfg, 0x10)` =
    `constants.nrOfSummons` (gameconfig 1248 : 2). MEME lecture que le mirror deja porte
    `engine/playbook/aggressive_onslaught.py::_max_summon` -- une CONSTANTE (`constants` du
    gameconfig), donc AUCUN niveau ni multiplicateur n'intervient (contraste avec
    `GetVariableForLevel`, qui indexe par niveau et subit le multiplicateur de rarete)."""
    import gameconfig as GC
    a = GC.ability(ABILITY_ID) or {}
    try:
        return int((a.get("constants") or {}).get(NR_OF_SUMMONS_KEY) or 0)
    except (TypeError, ValueError):
        return 0


# --------------------------------------------------------------------------------------------------
# 1/3 -- PREPARE : memorise « Mataneo chargeait » AVANT que l'attaque ne resolve.
# --------------------------------------------------------------------------------------------------

def prepare_behaviour_tree():
    """`AggressiveOnslaught_PrepareAbility$$CreateBehaviour` -- MIRROR 1:1 :

        SetPersistentData( AbilityOrEffect(this.Id), Owner@<+0x30>, Get("IsCharging"),
                           IsCharging(Caster@<+0x48>, Target@<+0x60>) )

    La VALEUR est un `IAbilityTrigger` (signature lue par `probe_951_call_targets.py`), pas un
    entier : le natif stocke le VERDICT du predicat `IsCharging`, evalue au moment du PreAttack."""
    return SetPersistentData(ABILITY_TYPE, Owner(), PERSIST_KEY,
                             IsCharging(Caster(), Target()))


class AggressiveOnslaughtPrepareAbility(TriggeredAbility):
    """`AggressiveOnslaught_PrepareAbility` -- `On(0x5 = PreAttack) & OwnerIsAlive & OwnerIsCaster`
    -> `SetPersistentData(Owner, "IsCharging", IsCharging(Caster, Target))`."""
    event_id = _ON_PRE_ATTACK
    TRIGGERED_ABILITY_ID = ABILITY_TYPE

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        """COLLAPSE du `CreateTrigger` -- TROIS termes, dans l'ordre du decompile."""
        if not _owner_alive(state, self.owner_id):                  # `<DSLTriggers+0x20>`
            return False
        # `get_OwnerIsCaster` = `AreEqual(<+0x30>, <+0x48>)` : sur ce vecteur le caster est
        # l'ATTAQUANT (`ev.actor_id`), donc le passif ne s'arme que sur les attaques de son porteur.
        return ev.actor_id is not None and int(ev.actor_id) == int(self.owner_id)

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, self.owner_id, ev.target_id, actor_id=ev.actor_id)
        prepare_behaviour_tree().execute(entities, ectx)
        charging = bool(IsCharging(Caster(), Target()).should_trigger(entities))
        return {"type": "aggressive_onslaught_prepare", "unit": int(self.owner_id),
                "key": PERSIST_KEY, "value": charging}


# --------------------------------------------------------------------------------------------------
# 2/3 -- SUMMON : pose `nrOfSummons` intercessors adjacents a la CIBLE, chacun attaquant aussitot.
# --------------------------------------------------------------------------------------------------

def summon_spawn_tiles(n: int):
    """Le sous-arbre TUILES de `AggressiveOnslaught_SummonAbility$$CreateBehaviour` -- MIRROR 1:1 :

        Cache( First( SortByDistance( CanAddUnit( AdjacentTiles(TargetTiles@<+0x78>) ),
                                      originSelector = Caster@<+0x48> ),
                      amount = Get(nrOfSummons), ignoreForcedTargets = false ),
               matchAbilityEntities = true )

    ⚠ Le CENTRE est `TargetTiles` (la cible) et le REFERENT du tri est `Caster` (Mataneo) : deux
    selecteurs DIFFERENTS, lus tels quels. `First` est la surcharge `PickFirstN` (les N premiers),
    tranchee par la signature que rend `probe_951_call_targets.py` -- pas `PickAtIndex`."""
    tiles = AdjacentTiles(TargetTile())
    tiles = CanAddUnit(tiles)
    tiles = SortByDistance(tiles, Caster())
    tiles = PickFirstN(tiles, Const(int(n)))
    return Cache(tiles)


def summon_behaviour_tree(n: int, ability_state: tuple):
    """`AggressiveOnslaught_SummonAbility$$CreateBehaviour` -- MIRROR 1:1.

    `on_appearance` = le sous-behaviour accroche a `SpawnUnitOptions+0x18`, que
    `SpawnUnitBehaviour$$TriggerSpawnedUnitBehaviours` fire PAR SUMMON juste apres la pose : son
    `caster` est `ActiveTarget@<+0x68>` (le summon frais) et sa cible `Target@<+0x60>` (la cible de
    Mataneo). C'est le « immediately attacking his target » du tooltip, et c'est EXACTEMENT le motif
    deja porte de `SendInTheNextWaveAbility$$ExecuteBehaviour`."""
    return Spawn(summon_spawn_tiles(n), ABILITY_ID,
                 on_appearance=UseNormalAttackIfAble(ActiveTarget(), Target()),
                 unit_id_constant=UNIT_ID_CONSTANT,
                 ability_state=ability_state)


class AggressiveOnslaughtSummonAbility(TriggeredAbility):
    """`AggressiveOnslaught_SummonAbility` --
    `( On(0xb = UnitAbility) & OwnerIsAlive & OwnerIsCaster )
     & ( AmountIsGreaterThanZero(GetPersistentData(Owner, "IsCharging")) | IsCharging(Caster, Target) )`
    -> `Spawn(Caster, <tuiles>, unitId, options{OnSpawn = UseNormalAttackIfAble(summon, Target)})`."""
    event_id = _ON_UNIT_ABILITY
    TRIGGERED_ABILITY_ID = ABILITY_TYPE

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        """COLLAPSE du `CreateTrigger`. Le DISJONCT est load-bearing : `On(0xb)` est emis APRES le
        behaviour de l'attaque, donc le drapeau pose au `PreAttack` par le `Prepare` est la voie
        NOMINALE ; `IsCharging` re-evalue en direct est le second bras."""
        if not _owner_alive(state, self.owner_id):                  # `<DSLTriggers+0x20>`
            return False
        if ev.actor_id is None or int(ev.actor_id) != int(self.owner_id):   # `get_OwnerIsCaster`
            return False
        entities = entities_from_state(state, self.owner_id, ev.target_id, actor_id=ev.actor_id)
        # `AmountIsGreaterThanZero( GetPersistentData(AbilityOrEffect(1248), Owner, Get("IsCharging")) )`
        persisted = GetPersistentData(ABILITY_TYPE, Owner(), PERSIST_KEY).evaluate(entities)
        if int(persisted or 0) > 0:
            return True
        # `op_BitwiseOr IsCharging(Caster@<+0x48>, Target@<+0x60>)` -- le NOEUD DSL porte, qui
        # delegue au foyer PARTAGE `battle_query.is_charging` (empreintes + porte d'elevation +
        # `ChargedUnitIds@+0x190`). On ne recable pas le predicat a la main.
        if ev.target_id is None:
            return False
        return bool(IsCharging(Caster(), Target()).should_trigger(entities))

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        n = aggressive_onslaught_max_summon(state, self.owner_id)
        if n <= 0:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, self.owner_id, ev.target_id, actor_id=ev.actor_id)
        summon_behaviour_tree(n, _passive_scaling(state, self.owner_id)).execute(entities, ectx)
        spawned = [p for name, p in ectx.emitted if name == "Spawn"]
        if not spawned:
            return None
        return {"type": "aggressive_onslaught_summon", "unit": int(self.owner_id),
                "nr_of_summons": n, "target": (int(ev.target_id) if ev.target_id is not None else None),
                "spawned": spawned}


# --------------------------------------------------------------------------------------------------
# 3/3 -- UNSUMMON : au debut de chaque tour de Mataneo, ses intercessors quittent le champ.
# --------------------------------------------------------------------------------------------------

def unsummon_behaviour_tree():
    """`AggressiveOnslaught_UnsummonAbility$$CreateBehaviour` -- MIRROR 1:1 :
    `RemoveUnit( DSLSelectors.Children(Owner@<DSLSelectors+0x30>) )`.

    `Children` = l'accumulateur `factory+0x148` que la feuille `Spawn` alimente -- donc les summons
    de CE porteur, et eux seuls. Le natif ne filtre PAS par `unitId` : le selecteur est `Children`
    NU (un second summon d'une autre source du meme porteur partirait aussi ; aucun kit du build ne
    met Mataneo dans ce cas)."""
    return RemoveUnit(ChildrenOf(Owner()))


class AggressiveOnslaughtUnsummonAbility(TriggeredAbility):
    """`AggressiveOnslaught_UnsummonAbility` -- `On(0x12 = TurnStart_EffectActivation) & OwnerIsAlive
    & IsTurnOf(Owner) & AmountIsGreaterThanZero(Children(Owner))` -> `RemoveUnit(Children(Owner))`.

    ⚠ Le terme `OwnerIsAlive` EST le « if he is still on the battlefield » du tooltip : Mataneo mort,
    ses intercessors RESTENT."""
    event_id = _ON_TURN_START_EFFECTS
    TRIGGERED_ABILITY_ID = ABILITY_TYPE

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        """COLLAPSE du `CreateTrigger` -- QUATRE termes, dans l'ordre du decompile."""
        if not _owner_alive(state, self.owner_id):                  # `<DSLTriggers+0x20>`
            return False
        if not _is_turn_of_owner(state, self.owner_id):             # `<DSLTriggers+0x28>`
            return False
        # `AmountIsGreaterThanZero( Children(Owner) )` -- le natif compte les enfants AVANT de
        # construire le behaviour ; sans ce gate le passif s'executerait a vide chaque tour.
        entities = entities_from_state(state, self.owner_id, None, actor_id=ev.actor_id)
        return len(ChildrenOf(Owner()).evaluate(entities) or []) > 0

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, self.owner_id, None, actor_id=ev.actor_id)
        removed = [u.get("id") for u in (ChildrenOf(Owner()).evaluate(entities) or [])
                   if isinstance(u, dict)]
        unsummon_behaviour_tree().execute(entities, ectx)
        if not removed:
            return None
        return {"type": "aggressive_onslaught_unsummon", "unit": int(self.owner_id),
                "removed": [int(x) for x in removed if x is not None]}
