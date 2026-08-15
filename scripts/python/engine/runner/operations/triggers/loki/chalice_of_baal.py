"""`ChaliceOfBaal` -- relique `TriggeredAbilityType` 0x60e = **1550**, porteur `bloodSanguinary`
(Blood Angels, HERO du pool). DEUX classes natives pour UNE cle, et c'est LU, pas suppose :
`IdunBattle.Core.Services.AbilitiesDatabase.u003Cu003Ec$$u003CInitializeTriggeredAbilitiesu003Eb__28_426`
construit successivement `ChaliceOfBaalAbility` puis `ChaliceOfBaal_ResetAbility` et les range dans
LA MEME liste -- meme patron que `LetTheGalaxyBurn` / `HaywireMine` / `DaemonfleshPlate`.

================================================================================================
RE (decompile ghidra, build `rnca9r7q6c`)
================================================================================================
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.ChaliceOfBaalAbility$$CreateTrigger` :

      On(EventTriggerType.UnitDeath = 0, ownerNeedsToBeAlive = true)
    & NOT HasTrait(Target@DSLSelectors+0x60, UnitTrait.Steppable = 0x1b)
    & IdunBattleLogic.Entities.DSLTriggers$$IsAdjacent(Owner@DSLSelectors+0x30, Target@+0x60,
                                                       UnitSelectionType.Any = 0)
    & NOT IdunBattleLogic.Entities.Abilities.Triggered.Loki.AChaliceOfBaalAbility$$HasTriggeredThisTurn()

⚠ **AUCUN `get_OwnerIsActor`** -- le porteur n'a pas a etre le TUEUR. N'IMPORTE QUELLE unite non
`Steppable` qui meurt a son contact declenche la relique, alliee comme ennemie. Le lire autrement
(par analogie avec `DawnBlade`, qui lui porte bien `get_OwnerIsActor`) donnerait un port
RESTRICTIF et muet. Les deux `On(0, ownerNeedsToBeAlive)` sont l'inlining de
`IdunBattleLogic.Entities.DSLTriggers$$On`, dont le corps est
`new EventTrigger(type, false) & (alive ? <DSLTriggers+0x20> : <+0x70>)`.

`...AChaliceOfBaalAbility$$HasTriggeredThisTurn` :

      AmountIsGreaterThanZero(
          IdunBattleLogic.Entities.DSLFormulas$$GetPersistentData(
              AbilityOrEffect(TriggeredAbilityType.ChaliceOfBaal = 0x60e),
              Owner@DSLSelectors+0x30,
              key = DSLFormulas$$Get(<AChaliceOfBaalAbility statics[0]>) ) )

La cle est le litteral **`"ChaliceOfBaalTriggered"`** : `...AChaliceOfBaalAbility$$.cctor` a pour
corps ENTIER `statics[0] = <literal cache 0x33af708>`, et `metadata/string_literals.tsv` donne ce
slot pour cette chaine.

`...ChaliceOfBaalAbility$$CreateBehaviour` (les trois volets, dans CET ordre) :

    adj     = IdunBattleLogic.Entities.DSLSelectors$$AdjacentFriends(
                  unit = Owner@+0x30, unique = true, selectionType = 3 = OnlyAliveAndTargetable)
    all     = TargetsSelector.op_Addition(Owner@+0x30, adj)          # le porteur EST dans le set
    targets = IdunBattleLogic.Entities.DSLSelectors$$UnitsAffectedByHealType(all,
                  HealType.NonMechanical = 0)
    v       = IdunBattle.Configuration.AbilityConfiguration$$GetVariableForLevel(
                  cfg@this+0x20, AbilityVariableType.hp = 0x1d, abilityState, 0)
    heal    = IdunBattleLogic.Entities.DSLBehaviors$$Heal(
                  healer = Owner@+0x30, selector = targets, amount = DSLFormulas$$Get(v),
                  options = IdunBattle.Entities.Behaviours.HealBehaviourOptions$$ForHeal(
                                AbilityOrEffect(ChaliceOfBaal)) )
    buff    = IdunBattleLogic.Entities.DSLBehaviors$$AddEffect(
                  effectType   = EffectType.ChaliceOfBaal_ExtraDmg = 0x621 = 1569,
                  abilityState = BaseTriggeredAbility$$get_AbilityStateReference,
                  source       = Owner@+0x30,
                  targets      = targets,
                  turns        = <DSLFormulas+0x20> = Direct(1) )
    mark    = IdunBattleLogic.Entities.DSLBehaviors$$SetPersistentData(
                  AbilityOrEffect(ChaliceOfBaal), Owner@+0x30,
                  key = Get("ChaliceOfBaalTriggered"), value = <DSLTriggers+0x40> )
    return (heal & buff) & mark

`...ChaliceOfBaal_ResetAbility$$CreateTrigger` :

      On(EventTriggerType.TurnEnd = 0x17, ownerNeedsToBeAlive = true) & HasTriggeredThisTurn()

`...ChaliceOfBaal_ResetAbility$$CreateBehaviour` -- **le corps est FONDU par l'ICF** et n'a donc
pas de symbole propre : il est PARTAGE avec
`...NoHidingFromTheWatchers_EndPhaseAbility$$CreateBehaviour`, place dans le bloc d'adresses de
`ChaliceOfBaal_ResetAbility` (entre `ChaliceOfBaalAbility$$.ctor` et
`ChaliceOfBaal_ResetAbility$$CreateTrigger`, dans une zone dont l'ordre est alphabetique par
classe). Corps :

      IdunBattleLogic.Entities.DSLBehaviors$$ClearAllPersistentData(
          AbilityOrEffect(<this.abilityType>), Owner@DSLSelectors+0x30 )

Il ne PEUT PAS s'agir d'un corps propre a `ChaliceOfBaal_Reset` reference par les statics de la
famille : les SEULES cinq fonctions du binaire qui touchent le `Il2CppClass*` d'
`AChaliceOfBaalAbility` sont son `.cctor`, son `HasTriggeredThisTurn`, les deux `.ctor` derives et
`ChaliceOfBaalAbility$$CreateBehaviour` -- aucune sixieme. Le corps partage, lui, ne lit AUCUN
static de classe (il derive son `AbilityOrEffect` de `this`), ce qui est exactement ce qui le rend
ICF-fusionnable entre classes.

================================================================================================
CE QUE CA FAIT, EN CLAIR
================================================================================================
Une fois par tour, a la mort de n'importe quelle unite non-`Steppable` au contact du porteur :
le porteur ET ses allies adjacents NON MECANIQUES sont soignes de `hp[niveau]` PV et gagnent, pour
UN TOUR, `+extraDmg[niveau]` de degat sur leurs attaques NORMALES de MELEE (effet 1569, cf.
`entities/effects/loki/extra_damage.py::ChaliceOfBaalExtraDmgEffect`). Le drapeau
« deja declenche ce tour » est efface a la fin de CHAQUE tour (relique ET adversaire confondus --
le disjoint `On(0x17)` ne porte aucun predicat de camp autre que `HasTriggeredThisTurn`).

RESIDUS NOMMES
  * `HealBehaviourOptions$$ForHeal(AbilityOrEffect(ChaliceOfBaal))` -- l'ATTRIBUTION du soin n'est
    pas modelisee cote port (la feuille `Heal` ne porte que `scope`/`remove_effects`, et `ForHeal`
    vaut precisement le couple par defaut `(0, True)`). Meme choix que `DawnBlade` pour `Repair`.
  * NIVEAU de la variable -- `hp`/`extraDmg` ont 10 entrees (niveaux de RELIQUE), indexees
    nativement par `BC.Units[].TertiaryAbilityLevel`. `triggered_ability_state` rend le couple
    TERTIAIRE quand l'ability arrive par l'item equipe (mirror d'`UnitFactory$$Build`), comme pour
    `DawnBlade` ; sur un runner normalise ce niveau vaut 50 et `ability_var` clampe au dernier
    palier.
"""
from __future__ import annotations

from typing import Optional

from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.ability_variable_type import AbilityVariableType
from .....entities.effect_type import EffectType
from .....entities.effects.magnitude import ability_var
from .....entities.formulas import GetPersistentData
from .....entities.heal_type import HealType
from .....entities.selectors.accessors import Owner
from .....entities.selectors.units import AdjacentFriends, UnitsAffectedByHealType, Union
from .....entities.traits.unit_trait import UnitTrait, has_any_trait
from .....entities.triggered_ability_type import TriggeredAbilityType
from .....entities.triggers import AmountIsGreaterThanZero
from .....entities.unit_selection_type import UnitSelectionType
from .....entities.behaviours import op_and
# #943-r7 -- les DEUX canaux du substrat d'adjacence NATIF, en FORME B (#485-r1-r1).
# `entities.pathfinding.board` n'importe RIEN d'`engine`, et `engine.battle_query` n'importe que
# `hexgeo` + `.hex_corner` : aucune de ces deux aretes ne peut fermer un cycle.
from .....entities.pathfinding import board as _board
from ..... import battle_query as _bq
from ....components import StatsComponent, UnitComponent
from ....state import State
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.effects import AddEffect
from ....abilities.behaviours.persistent_data import (ClearAllPersistentData,
                                                      SetPersistentData)
from ....abilities.behaviours.stats import Heal
from ..base import TriggeredAbility, TriggerEvent, triggered_ability_state, _unit_trait_names

ABILITY_ID = "ChaliceOfBaal"
CHALICE = int(TriggeredAbilityType.ChaliceOfBaal)                 # 0x60e = 1550
EXTRA_DMG_EFFECT = int(EffectType.ChaliceOfBaal_ExtraDmg)         # 0x621 = 1569
EXTRA_DMG_EFFECT_NAME = EffectType.ChaliceOfBaal_ExtraDmg.name
#: Le litteral que `AChaliceOfBaalAbility$$.cctor` range dans `statics[0]` (slot de cache
#: `0x33af708`, `metadata/string_literals.tsv` ligne 5965).
TRIGGERED_KEY = "ChaliceOfBaalTriggered"
HP_KEY = AbilityVariableType.hp.name                              # `GetVariableForLevel(0x1d)`
#: `turns = <DSLFormulas+0x20>` -- le `.ctor` de `DSLFormulas` alloue `0/1/2/100/-1` aux slots
#: `+0x18/+0x20/+0x28/+0x30/+0x38`, donc `Direct(1)`. C'est un `IAmountFormula` deja en TOURS
#: (pas un `TurnsFromRounds`) -> `duration_turns`, jamais `duration_rounds`.
BUFF_TURNS = 1
#: `value = <DSLTriggers+0x40>` -- la constante VRAIE de `DSLTriggers` (meme famille que le
#: `YesTrigger` de `+0x70`, cf. `ABILITY_INIT_OWNER_EFFECTS["TerrorsLament"]`). Le seul LECTEUR de
#: la donnee persistante est `AmountIsGreaterThanZero`, donc ce qui compte est `>= 1`.
TRIGGERED_VALUE = 1

_ON_UNIT_DEATH = int(EventTriggerType.UnitDeath)                  # `On(0, alive = true)`
_ON_TURN_END = int(EventTriggerType.TurnEnd)                      # `On(0x17, alive = true)`


def chalice_targets() -> UnitsAffectedByHealType:
    """`UnitsAffectedByHealType( Owner + AdjacentFriends(Owner, unique, OnlyAliveAndTargetable),
    HealType.NonMechanical )` -- le selecteur PARTAGE par le `Heal` et par l'`AddEffect` du
    `CreateBehaviour` natif (une seule variable locale y sert aux deux feuilles).

    La surcharge d'`AdjacentFriends` est la variante **A** `(unit, unique, selectionType)` : le 3e
    argument du call-site est le litteral booleen `1` et le 4e l'entier `3`, ce qui exclut la
    variante `(unit, unitTile, unique)` (dont le 3e argument est un `TargetsSelector*`).
    `reference = Owner` parce que c'est le CENTRE qui sert de reference d'equipe dans le corps natif
    (`Friends(unit, Units(AdjacentTiles(unit), ...) - unit, ...)`) -- ici centre == porteur, donc le
    defaut aurait suffi ; on l'ecrit pour ne pas dependre du collapse."""
    adj = AdjacentFriends(Owner(), reference=Owner(),
                          selection_type=int(UnitSelectionType.OnlyAliveAndTargetable))
    return UnitsAffectedByHealType(Union(Owner(), adj), int(HealType.NonMechanical))


def chalice_behaviour_tree(hp_amount: int):
    """`(Heal & AddEffect) & SetPersistentData` -- ARBRE 1:1, ordre gauche->droite du decompile.

    `hp_amount` est resolu par l'APPELANT parce que le natif le resout lui aussi AVANT de batir
    l'arbre (`GetVariableForLevel` puis `DSLFormulas$$Get`) : c'est une CONSTANTE de l'arbre, pas un
    noeud paresseux -- meme forme que `DawnBlade` et `FabricatorClawArray`.

    `scale_from_source=True` sur l'`AddEffect` porte l'`abilityState` natif : l'effet materialise
    resout son `ConfigVar(extraDmg)` contre l'etat d'ability de sa SOURCE (le porteur de la
    relique), pas contre celui de l'allie buffe."""
    targets = chalice_targets()
    heal = Heal(targets, hp_amount)                      # `ForHeal` == (scope 0, removeEffects True)
    buff = AddEffect(EXTRA_DMG_EFFECT, EXTRA_DMG_EFFECT_NAME, chalice_targets(),
                     duration_rounds=None, duration_turns=BUFF_TURNS,
                     source_ref=Owner(), scale_from_source=True)
    mark = SetPersistentData(CHALICE, Owner(), TRIGGERED_KEY, TRIGGERED_VALUE)
    return op_and(op_and(heal, buff), mark)


def chalice_reset_tree() -> ClearAllPersistentData:
    """`ClearAllPersistentData(AbilityOrEffect(ChaliceOfBaal), Owner@+0x30)` -- le corps ICF-partage
    avec `NoHidingFromTheWatchers_EndPhaseAbility$$CreateBehaviour` (cf. l'en-tete du module)."""
    return ClearAllPersistentData(CHALICE, Owner())


def _has_triggered_this_turn(state: State, owner_id: int) -> bool:
    """`AChaliceOfBaalAbility$$HasTriggeredThisTurn` -- le noeud, evalue contre l'ECS."""
    entities = entities_from_state(state, int(owner_id), int(owner_id))
    return bool(AmountIsGreaterThanZero(
        GetPersistentData(CHALICE, Owner(), TRIGGERED_KEY)).evaluate(entities))


def chalice_hp(state: State, owner_id: int) -> int:
    """`GetVariableForLevel(cfg, AbilityVariableType.hp = 0x1d, abilityState, 0)`.

    `triggered_ability_state` mirrore le choix d'`UnitFactory$$Build` : couple TERTIAIRE
    (`TertiaryAbilityLevel` / `TertiaryAbilityVariablesMultiplierPercentage`) quand `ChaliceOfBaal`
    arrive par l'item relique EQUIPE, couple PASSIF sinon. `hp` n'est PAS dans
    `variablesAffectedByRarityBonus` du gameconfig de `ChaliceOfBaal` (la liste est absente) -> le
    multiplicateur est un no-op, `ability_var` le gate sur cette liste ; on le passe quand meme,
    c'est le natif qui decide. 0 -> la feuille `Heal` no-ope (`amount > 0` est sa garde)."""
    e = state.get_entity(int(owner_id))
    sc = e.get_component(StatsComponent) if e is not None else None
    if sc is None or getattr(sc, "ctx", None) is None:
        return 0
    lvl, mult = triggered_ability_state(state, int(owner_id), ABILITY_ID)
    return int(ability_var(ABILITY_ID, HP_KEY, lvl, multiplier_pct=mult) or 0)


class ChaliceOfBaalAbility(TriggeredAbility):
    """1re classe de la cle 1550 -- le VOLET ACTIF de la relique (soin + buff + marquage)."""
    event_id = _ON_UNIT_DEATH
    TRIGGERED_ABILITY_ID = CHALICE                        # 0x60e = 1550

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        dying = ev.dying_id if ev.dying_id is not None else ev.target_id
        if dying is None or int(dying) == int(self.owner_id):
            return False
        owner = state.get_entity(int(self.owner_id))
        victim = state.get_entity(int(dying))
        if owner is None or victim is None:
            return False
        # `On(0, ownerNeedsToBeAlive = true)` -- `<DSLTriggers+0x20>`.
        ouc = owner.get_component(UnitComponent)
        if ouc is not None and not ouc.alive:
            return False
        # `NOT HasTrait(Target@+0x60, UnitTrait.Steppable = 0x1b)`.
        if has_any_trait(_unit_trait_names(state, int(dying)), (UnitTrait.Steppable,)):
            return False
        # `IsAdjacent(Owner@+0x30, Target@+0x60, UnitSelectionType.Any = 0)` -- le `0` ne filtre
        # RIEN (la victime est morte, un `OnlyAlive` l'aurait ecartee et la relique n'aurait
        # jamais rien fait).
        if not _adjacent(state, int(self.owner_id), int(dying)):
            return False
        # `NOT HasTriggeredThisTurn()`.
        return not _has_triggered_this_turn(state, int(self.owner_id))

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        amount = chalice_hp(state, int(self.owner_id))
        ectx = ExecutionContext(state=state, rng=state.rng)
        # `BaseTriggeredAbility$$Execute` monte l'`AbilityEntities` sur SON porteur : `Owner@+0x30`
        # == caster == le porteur ; `actor` = l'acteur du vecteur de mort (le TUEUR).
        entities = entities_from_state(state, int(self.owner_id), int(self.owner_id),
                                       actor_id=ev.actor_id)
        chalice_behaviour_tree(amount).execute(entities, ectx)
        heals = [h for n, p in ectx.emitted if n == "Heal" for h in (p.get("heals") or ())]
        placed = [p["target"] for n, p in ectx.emitted if n == "AddEffect" and p.get("placed")]
        return {"relic": ABILITY_ID, "owner": int(self.owner_id),
                "victim": int(ev.dying_id) if ev.dying_id is not None else None,
                "amount": int(amount), "heals": heals, "buffed": placed,
                "key": TRIGGERED_KEY, "dsl": True}


class ChaliceOfBaalResetAbility(TriggeredAbility):
    """2e classe de la MEME cle 1550 -- efface le drapeau « deja declenche ce tour ».

    Le disjoint natif est `On(0x17 = TurnEnd, ownerNeedsToBeAlive = true) & HasTriggeredThisTurn()`
    : PAS de `get_OwnerIsActor`, PAS d'`IsTurnOf(Owner)`. Le drapeau tombe donc a la fin de
    N'IMPORTE QUEL tour, celui de l'adversaire compris -- ce qu'on ecrit parce que c'est ce qui est
    LU, meme si l'observable coincide avec « une fois par tour du porteur » sur les regimes
    confrontes."""
    event_id = _ON_TURN_END
    TRIGGERED_ABILITY_ID = CHALICE                        # 0x60e = 1550

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        owner = state.get_entity(int(self.owner_id))
        if owner is None:
            return False
        ouc = owner.get_component(UnitComponent)
        if ouc is not None and not ouc.alive:             # `ownerNeedsToBeAlive = true`
            return False
        return _has_triggered_this_turn(state, int(self.owner_id))

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, int(self.owner_id), int(self.owner_id))
        chalice_reset_tree().execute(entities, ectx)
        cleared = [c for n, p in ectx.emitted if n == "ClearAllPersistentData"
                   for c in (p.get("cleared") or ())]
        return {"relic": ABILITY_ID, "owner": int(self.owner_id), "cleared": cleared, "dsl": True}


def _adjacent(state: State, a_id: int, b_id: int) -> bool:
    """`IdunBattleLogic.Entities.DSLTriggers$$IsAdjacent` -> `IdunBattle.Entities.Triggers.
    IsAdjacentAbilityTrigger$$ShouldTrigger` -> slot 0x60 d'`IBattleQuery` =
    `IdunBattle.Core.Services.BattleQuery$$AreEntitiesAdjacent`.

    LE SUBSTRAT, LU (#943-r7) -- ce n'est PAS une couronne hex :

        BattleQuery$$AreEntitiesAdjacent(e1, e2) = MovementUtil$$AreTilesAdjacent(GetTiles(e1),
                                                                                 GetTiles(e2))
        MovementUtil$$AreTilesAdjacent(t1, t2)   = (|elev(t1) - elev(t2)| < 2)
                                                 & (t1 == t2
                                                    || ConnectivityComponent$$IsNeighbour(t1, t2))

    -- l'appartenance a la liste STOCKEE `ConnectivityComponent+0x10`, ET la porte d'elevation en
    terme SEPARE (`iVar7 < 2 & bVar3` au decompile). Le foyer `engine.battle_query
    .are_entities_adjacent` porte exactement ces deux etages, court-circuit d'identite compris
    (#433-r1) ; le canal `adjacent_neigh_by_pos` est le champ `neighbours` du `boardGraph`, c.-a-d.
    `connectivity INTERSECTE {|dElev| < 2}` -- l'intersecter une seconde fois avec la meme porte est
    IDEMPOTENT, donc ce canal-la est le substrat EXACT de cette conjonction.

    Board absent (`State.board is None`, board de test) -> `(None, None)` -> le foyer retombe sur
    son repli geometrique NOMME, le comportement d'avant ce cablage."""
    from ....components import PositionComponent
    ea, eb = state.get_entity(int(a_id)), state.get_entity(int(b_id))
    pa = ea.get_component(PositionComponent) if ea is not None else None
    pb = eb.get_component(PositionComponent) if eb is not None else None
    if pa is None or pb is None:
        return False
    board = getattr(state, "board", None)
    return _bq.are_entities_adjacent((pa.col, pa.row), (pb.col, pb.row),
                                     _board.elevations_by_pos(board),
                                     _board.adjacent_neigh_by_pos(board))
