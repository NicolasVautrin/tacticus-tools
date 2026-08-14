"""`PhasalSubjugator` -- RELIQUE de `necroOverlord` (`TriggeredAbilityType` 0x615 = 1557).
Tache #1011-r1, face COMBAT. RE : decompile ghidra, build `rnca9r7q6c`.

================================================================================================
1. UNE CLE, **DEUX** CLASSES NATIVES -- et c'est LU, pas suppose
================================================================================================

`IdunBattle.Core.Services.AbilitiesDatabase.u003Cu003Ec$$u003CInitializeTriggeredAbilitiesu003Eb__28_433`
(le lambda que `$$InitializeTriggeredAbilities` cache pour la cle `0x615`) construit **UNE `List` et
y `Add` DEUX elements** -- controle : `b__28_432` (0x614 `MyWillBeDoneOverlord`) n'en construit
qu'UN, ce qui concorde avec sa classe unique connue. Les deux classes sont
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.PhasalSubjugator_SummonAbility` et
`...PhasalSubjugator_TriggerPassiveAbility` (parent LU dans `data/symbols/<build>/frida/classes.tsv` :
`IdunBattle.Entities.Abilities.BaseTriggeredAbility` pour les deux, malgre le namespace `Triggered`).

L'ORDRE des deux `Add` est sans effet observable ici : les deux classes ecoutent des EVENEMENTS
DIFFERENTS (`0x1c` et `0x29`), donc aucune ne peut preceder l'autre sur un meme vecteur.

================================================================================================
2. `...PhasalSubjugator_SummonAbility` -- le summon a la fin d'un DEPLACEMENT
================================================================================================

`$$CreateTrigger` (verbatim) :

    On(0x1c = ArrivedAtFinalTile, ownerNeedsToBeAlive: 1)
      & get_OwnerIsActor
      & op_LogicalNot( AmountIsGreaterThanZero(
            Friends( of = Owner@<DSLSelectors+0x30>,
                     entities = UnitsWithVisualId( VisualUnitIdFromUnitId(
                                    GetStringConstant(config, 0 = unitId) ),
                                 selectionType = 1 ),
                     selectionType = 1 ) ) )

`$$CreateBehaviour` (verbatim) :

    unitId = GetStringConstant(config, 0 = AbilityConstantType.unitId)
    tiles  = First( SortTilesByUtilityForSummon( CanAddUnit(AdjacentTiles(Owner@+0x30)),
                                                 utilityType = 7, parent = Owner@+0x30 ),
                    amount = 1, ignoreForcedTargets = 0 )
    opts   = SpawnUnitOptions.WithStatsFromConfig(config, abilityState, 0, 0)
    return Spawn( parentSelector = Owner@+0x30, tiles, spawnUnitId = unitId, options = opts )

QUALIFICATION DES DEUX LITTERAUX `1` -- ils sont dans le MEME enum, et ce n'est pas un hasard : les
DEUX parametres se nomment `selectionType` et sont declares `IdunBattle.Entities.Enum.UnitSelectionType`
dans `data/symbols/<build>/frida/methods.tsv` (`DSLSelectors.UnitsWithVisualId(unitId:IStringFormula,
selectionType:UnitSelectionType)` et `DSLSelectors.Friends(of:ITargetsSelector,
entities:ITargetsSelector, selectionType:UnitSelectionType)`). `1` = `UnitSelectionType.OnlyAlive` --
surtout PAS un `UnitTeamSelectionType`, ou 1 nommerait `ByOriginalTeam`. Le gate est donc
« aucun Guerrier ami VIVANT sur le plateau », pas « aucun Guerrier ami quelconque » : un Warrior MORT
ne bloque pas le re-summon.

`utilityType = 7` = `IdunBattle.Configuration.UtilityType.Tile` (parametre declare
`utilityType:IdunBattle.Configuration.UtilityType` dans la meme table).

================================================================================================
3. `...PhasalSubjugator_TriggerPassiveAbility` -- l'ETAGE QUI BLOQUAIT, LEVE HORS LIGNE
================================================================================================

Son `$$CreateTrigger` est **ABSENT des deux tables de symboles** (corps DEDUPLIQUE par l'ICF). Il a
ete identifie SANS capteur, par la seule STRUCTURE de `frida/methods.tsv`, qui est ecrite dans
l'ordre `methodPointers` **par classe visitee** :

    [51013] 12a7cb0  ...PhasalSubjugator_TriggerPassiveAbility.HasFriendlyWarrior
    [51014] efad70   ...Abilities.Active.Loki.CallInReinforcementsAbility.CreateTrigger   <-- INTRUS
    [51015] 12a7d80  ...PhasalSubjugator_TriggerPassiveAbility.CreateBehaviour

L'adresse `efad70` est ETRANGERE au voisinage (tout le bloc est en `12a7xxx`), et le CONTROLE est
decisif : dans le groupe NATUREL de `CallInReinforcementsAbility` (`CreateBehaviour` +
`GetPossibleSpawnTiles`, lignes 52429-52430) son `CreateTrigger` **MANQUE**. La ligne a donc ete
emise a la visite de l'AUTRE classe -- c'est le corps partage.

Et ce corps, decompile, est GENERIQUE (aucun litteral propre a `CallInReinforcements`) :

    ...CallInReinforcementsAbility$$CreateTrigger
        = On(0x29, ownerNeedsToBeAlive: 1) op_BitwiseAnd get_OwnerIsActor

=> le partage est LEGITIME et la semantique determinee : **`EventTriggerType` 0x29 = 41 =
`UnitFinishedTurnNormally`** (mirror `engine/dsl/event_trigger_type.py`).

`$$CreateBehaviour` (verbatim) :

    spawn = <le MEME sous-arbre Spawn que la section 2>
    trig  = TriggerAbility( entity = Owner@+0x30, triggeredAbilityType = 0x614 = MyWillBeDoneOverlord,
                            actor = null, caster = null, target = null, unitFeetTiles = null,
                            selectionType = 3, ignoreUnitHavingAbility = false )
    cond  = op_LogicalNot( HasFriendlyWarrior() )        # inline, le MEME sous-arbre qu'en section 2
    return If( cond, spawn, else = null ) op_BitwiseAnd IfAlive( Owner@+0x30, trig, else = null )

`...PhasalSubjugator_TriggerPassiveAbility$$HasFriendlyWarrior` (methode NOMMEE, dont le corps est
recopie inline dans `CreateBehaviour`) =
`AmountIsGreaterThanZero(Friends(Owner, UnitsWithVisualId(VisualUnitIdFromUnitId(unitId), 1), 1))`.

`IdunBattleLogic.Entities.DSLBehaviors$$IfAlive(selector, ifBehaviour, elseBehaviour)` ne construit
aucune classe dediee : il COMPOSE `If(IsAlive(selector), ifB, elseB)` (meme lecture que celle deja
transcrite dans `runner/abilities/loki/leading_the_charge.py`).

=> **A la fin d'un tour NORMAL de l'Overlord** : s'il n'a plus de Guerrier ami vivant, il en
re-summone un ; puis, s'il est vivant, il RE-DECLENCHE son propre passif `MyWillBeDoneOverlord`.

================================================================================================
4. LE RE-DECLENCHEMENT DE 1556, ET CE QU'IL N'ARME **PAS**
================================================================================================

`TriggerAbility` passe par `IdunBattle.Operations.TriggerTriggeredAbilityOperation$$TriggerAbility`,
qui appelle `ITriggeredAbility.ExecuteBy(ability, &abilityState, entities, 0x20)` -- le
`0x20 = EventTriggerType.Custom` est EN DUR dans l'Operation. C'est donc la branche `else` de
`...MyWillBeDoneOverlordAbility$$CreateBehaviour` (son `if (triggerType == 0x12)` ne mord pas) : le
tour d'attaque offert a un allie. Ce module EST l'appelant qui manquait -- d'ou l'entree
`TRIGGERED_ABILITY_BEHAVIOURS[MyWillBeDoneOverlord]`, posee dans `my_will_be_done_overlord.py`
(patron `AdaptiveStrategy` -> `RelentlessMarch`, `runner/abilities/necrons.py`).

⚠ **LA PREMISSE DU RESIDU QUE CE PORT DEVAIT ROUVRIR EST REFUTEE.** `my_will_be_done_overlord.py`
sec.5 annoncait : « le jour ou la branche `Custom` a un appelant, le terme
`!TriggeringAbilityIs(1557) | IsUnitWithVisualId(...)` de `GetTargetFriend` doit etre pose ». Il ne
doit PAS l'etre, et c'est LU dans `IdunBattle.Entities.Abilities.BaseTriggeredAbility$$Execute` :

    <entities+0x60 CurrentAbility>    = Nullable(this.Id)     # AVANT le behaviour
    <execution du behaviour>
    <entities+0x98 TriggeringAbility> = Nullable(this.Id)     # APRES le behaviour, avant On(0xd)

`TriggeringAbilityIs` lit `<DSLSelectors+0x90>` -> `AbilityEntities+0x98` (case-292). Pendant le
behaviour de 1557, ce champ vaut donc encore la valeur ENTRANTE, et la chaine la PRESERVE :
`IdunBattle.Entities.Behaviours.TriggerAbilityBehaviour$$Execute` reconstruit son `AbilityEntities`
par `AbilityEntities$$.ctor(<copie de l'entrant>, null)` puis n'ecrase QUE `actor`/`caster`/`target`/
`unitFeetTiles`, et `TriggerTriggeredAbilityOperation` comme `ExecuteBy` ne font que RECOPIER les
0x148 octets. Or le vecteur porteur est `On(0x29)`, que `FinishUnitTurnOperation$$Execute` publie
avec un `Nullable<AbilityOrEffect>` ENTIEREMENT NUL (mesure de #354-r1). `TriggeringAbilityIs(1557)`
y est donc FAUX, `NOT(...)` VRAI, et la disjonction reste TAUTOLOGIQUE -- exactement comme sur le
vecteur direct. Omettre le terme reste EXACT.

================================================================================================
5. RESIDUS NOMMES
================================================================================================

  * `selectionType = 3` (`OnlyAliveAndTargetable`) et `ignoreUnitHavingAbility = false` du
    `TriggerAbility` : la feuille portee n'expose ni l'un ni l'autre (residu PARTAGE par tous ses
    call-sites, deja nomme par `geminae_superia.py`). Le volet « l'unite porte-t-elle l'ability »
    est, lui, applique -- `TriggerAbility.execute` gate sur `_unit_has_triggered_ability`, mirror du
    `GetAbilityState` de l'Operation.
  * Le tri `SortTilesByUtilityForSummon` est le noeud DSL `SortTilesByUtility` (#448-r1) avec
    `unit_sel = None` et `parent_sel = Owner` : mirror VALEUR-EQUIVALENT du call-site `ForSummon`,
    dont le corps natif est `unit = new <selecteur rendant null>(state, null, null)` +
    `def = new UtilityDefinition(7)`. Le port court-circuite l'appel du selecteur nul ; l'HYPOTHESE
    (le `SelectUnit` de cette classe rend `null` au lieu de lever) est celle deja nommee par
    `case-1013r2` sec.3.
  * La constante `unitId` (`necroSmnWarrior`) est LUE dans le gameconfig au runtime
    (`GC.ability("PhasalSubjugator").constants.unitId`), jamais ecrite en dur : c'est la MEME
    resolution que celle du `GetStringConstant(config, 0)` natif.
"""
from __future__ import annotations

from typing import Optional

from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.ability_constant_type import AbilityConstantType
from .....entities.behaviours import If, Seq
from .....entities.formulas import Count, VisualUnitIdFromUnitId
from .....entities.selectors.geometry import UnitsWithVisualId
from .....entities.selectors.tiles import (AdjacentTiles, CanAddUnit, Caster,
                                           SortTilesByUtility)
from .....entities.selectors.units import First, Friends
from .....entities.triggered_ability_type import TriggeredAbilityType
from .....entities.triggers import AmountIsGreaterThanZero, IsAlive, Not, OwnerIsActor, TriggerAnd
from .....entities.unit_selection_type import UnitSelectionType
from .....utilities.utility_type import UtilityType
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.lifecycle import TriggerAbility
from ....abilities.behaviours.summon import Spawn
from ....state import State
from ..base import TriggeredAbility, TriggerEvent, triggered_ability_state

ABILITY_ID = "PhasalSubjugator"
PHASAL_SUBJUGATOR = int(TriggeredAbilityType.PhasalSubjugator)          # 0x615 = 1557
#: `TriggerAbility(Owner@+0x30, 0x614, ...)` -- `TriggeredAbilityType`, PAS `ActiveAbilityType`
#: (ou 1556 nommerait autre chose). C'est le passif de kit du MEME porteur.
MY_WILL_BE_DONE_OVERLORD = int(TriggeredAbilityType.MyWillBeDoneOverlord)   # 0x614 = 1556
#: `GetStringConstant(config, 0)` -- `AbilityConstantType.unitId` (= `necroSmnWarrior` au gameconfig).
SUMMON_UNIT_ID_CONSTANT = AbilityConstantType.unitId                    # 0
#: Les DEUX `1` du gate sont des `UnitSelectionType` (type DECLARE lu dans `frida/methods.tsv`).
WARRIOR_SELECTION = UnitSelectionType.OnlyAlive                         # = 1
#: `SortTilesByUtilityForSummon(tiles, 7, parent)` -- `IdunBattle.Configuration.UtilityType.Tile`.
SPAWN_TILE_UTILITY = UtilityType.Tile                                   # = 7

_ON_ARRIVED_AT_FINAL_TILE = int(EventTriggerType.ArrivedAtFinalTile)    # 0x1c = 28
_ON_UNIT_FINISHED_TURN_NORMALLY = int(EventTriggerType.UnitFinishedTurnNormally)   # 0x29 = 41


def _summon_unit_id():
    """`IdunBattle.Configuration.AbilityConfiguration$$GetStringConstant(config, 0 = unitId)`.

    MEME lecture que `geminae_superia._summon_unit_id`. `None` = cle absente -> le selecteur
    `UnitsWithVisualId` ne matche rien (le gate passe alors), et le `Spawn` est de toute facon un
    no-op (`Spawn.execute` sort quand la constante rend None)."""
    import gameconfig as GC
    return ((GC.ability(ABILITY_ID) or {}).get("constants") or {}).get(SUMMON_UNIT_ID_CONSTANT.name)


def phasal_friendly_warriors():
    """Le sous-arbre PARTAGE par les deux classes -- `$$HasFriendlyWarrior` moins son
    `AmountIsGreaterThanZero` :

        Friends( of = Owner@+0x30,
                 entities = UnitsWithVisualId(VisualUnitIdFromUnitId(GetStringConstant(0)), 1),
                 selectionType = 1 )

    Une NOUVELLE instance a chaque appel, EXPRES : le natif rebatit le sous-arbre a chaque site
    (`CreateTrigger` de la classe 1, `CreateBehaviour` de la classe 2), sans aucun `Cache`.

    `Caster()` = `Owner@+0x30` (pour une `BaseTriggeredAbility`, owner == caster).
    ⚠ `UnitsWithVisualId` est **BOARD-WIDE** (source = le slot partage `factory+0x80`) : le gate ne
    regarde AUCUN rayon autour de l'Overlord -- un Guerrier ami vivant a l'autre bout du plateau le
    ferme."""
    return Friends(UnitsWithVisualId(VisualUnitIdFromUnitId(_summon_unit_id()),
                                     int(WARRIOR_SELECTION)),
                   Caster(), selection_type=int(WARRIOR_SELECTION))


def phasal_has_friendly_warrior():
    """`...PhasalSubjugator_TriggerPassiveAbility$$HasFriendlyWarrior` = `AmountIsGreaterThanZero(
    <phasal_friendly_warriors>)`. `Count(...)` est la conversion selecteur -> CARDINAL que le noeud
    natif `AmountIsGreaterAbilityTrigger(selector, Direct(0))` fait en interne."""
    return AmountIsGreaterThanZero(Count(phasal_friendly_warriors()))


def phasal_spawn_tiles():
    """`First( SortTilesByUtilityForSummon( CanAddUnit(AdjacentTiles(Owner@+0x30)), 7, Owner@+0x30 ),
    1, 0 )` -- le MEME sous-arbre dans les DEUX `CreateBehaviour`.

    `First(sel)` (index 0) est le mirror de `First(sel, amount = 1, ignoreForcedTargets = 0)` : la
    surcharge native prend les `amount` PREMIERS elements, et pour `amount == 1` c'est l'element 0.
    `unit_sel = None` + `parent_sel = Owner` = la signature EXACTE du call-site `ForSummon`
    (cf. le residu en en-tete)."""
    return First(SortTilesByUtility(CanAddUnit(AdjacentTiles(Caster())),
                                    unit_sel=None, utility_type=int(SPAWN_TILE_UTILITY),
                                    parent_sel=Caster()))


def phasal_spawn_tree(ability_state):
    """`Spawn( parentSelector = Owner@+0x30, <phasal_spawn_tiles>, unitId,
    SpawnUnitOptions.WithStatsFromConfig(config, abilityState, 0, 0) )`.

    `ability_state` = le couple `(niveau, multiplicateur)` de l'`AbilityState` TERTIAIRE du porteur
    (`triggered_ability_state`) : une RELIQUE ne monte PAS ses variables au niveau des passifs.
    Sans lui, `summonHp`/`summonDmg`/`summonArmor` seraient lus au dernier palier dans tout runner
    normalise -- l'ecart #174, silencieux.

    Le `parentSelector` natif est porte par la feuille elle-meme (`Spawn.execute` pose
    `parent_id = <caster>`)."""
    return Spawn(phasal_spawn_tiles(), ABILITY_ID,
                 unit_id_constant=SUMMON_UNIT_ID_CONSTANT.name,
                 ability_state=ability_state)


def phasal_trigger_passive_tree(ability_state):
    """`...PhasalSubjugator_TriggerPassiveAbility$$CreateBehaviour` =

        If( NOT HasFriendlyWarrior(), <spawn> )   op_BitwiseAnd   IfAlive( Owner@+0x30, <trigger> )

    `op_BitwiseAnd` alloue la MEME `CombinedBehaviour` que `op_Addition` -> noeud `Seq`.
    `IfAlive(sel, ifB, elseB)` = `If(IsAlive(sel), ifB, elseB)` (le natif ne fait que composer).

    ⚠ L'ORDRE est celui du decompile et il compte : le Guerrier est pose AVANT le re-declenchement,
    donc `MyWillBeDoneOverlord` peut elire le Guerrier fraichement spawne (la feuille `Spawn` pousse
    chaque enfant dans `entities.units`, mirror de la ref d'etat native)."""
    return Seq(If(Not(phasal_has_friendly_warrior()), phasal_spawn_tree(ability_state)),
               If(IsAlive(Caster()), TriggerAbility(Caster(), MY_WILL_BE_DONE_OVERLORD)))


class PhasalSubjugatorSummonAbility(TriggeredAbility):
    """`...PhasalSubjugator_SummonAbility` (1re des DEUX classes de la cle 0x615).

    `On(0x1c = ArrivedAtFinalTile, alive) & get_OwnerIsActor & NOT HasFriendlyWarrior()`
    -> `Spawn(<la meilleure tuile libre adjacente>, necroSmnWarrior, stats de la RELIQUE)`.

    Lisible : quand `necroOverlord` termine son deplacement et n'a plus aucun Guerrier ami VIVANT
    sur le plateau, un Guerrier apparait a cote de lui."""
    event_id = _ON_ARRIVED_AT_FINAL_TILE
    TRIGGERED_ABILITY_ID = PHASAL_SUBJUGATOR

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        """`CreateTrigger` moins le volet `On(0x1c)` + « owner vivant », deja porte par le dispatch."""
        entities = entities_from_state(state, self.owner_id, ev.target_id, actor_id=ev.actor_id)
        return bool(TriggerAnd(OwnerIsActor(),
                               Not(phasal_has_friendly_warrior())).evaluate(entities))

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        etat = triggered_ability_state(state, int(self.owner_id), ABILITY_ID)
        entities = entities_from_state(state, self.owner_id, ev.target_id, actor_id=ev.actor_id)
        ectx = ExecutionContext(state=state, rng=state.rng)
        phasal_spawn_tree(etat).execute(entities, ectx)
        spawned = [p.get("unit") for (n, p) in ectx.emitted if n == "SpawnUnit"]
        if not spawned:
            return None
        return {"passive": ABILITY_ID, "owner": int(self.owner_id),
                "spawned": spawned, "ability_state": etat, "dsl": True}


class PhasalSubjugatorTriggerPassiveAbility(TriggeredAbility):
    """`...PhasalSubjugator_TriggerPassiveAbility` (2e des DEUX classes de la cle 0x615).

    `On(0x29 = UnitFinishedTurnNormally, alive) & get_OwnerIsActor`
    -> `If(NOT HasFriendlyWarrior(), Spawn(...)) & IfAlive(Owner, TriggerAbility(Owner, 1556))`.

    Lisible : a la CLOTURE NORMALE de son activation, `necroOverlord` recomplete son Guerrier s'il
    n'en a plus, puis rejoue son passif `MyWillBeDoneOverlord` -- un allie adjacent eligible attaque
    une SECONDE fois dans le tour.

    ⚠ Le gate `HasFriendlyWarrior` vit ICI dans le BEHAVIOUR (le `If`), pas dans le trigger : le
    re-declenchement de 1556 se produit MEME quand un Guerrier est deja en vie. Le confondre avec la
    forme de la classe 1 (ou le meme sous-arbre est un conjoint du `CreateTrigger`) supprimerait la
    moitie du contenu de la relique, en silence."""
    event_id = _ON_UNIT_FINISHED_TURN_NORMALLY
    TRIGGERED_ABILITY_ID = PHASAL_SUBJUGATOR

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        """Le corps partage `On(0x29, alive) & get_OwnerIsActor` (cf. sec.3 de l'en-tete) : le volet
        `On` + « owner vivant » est porte par le dispatch, reste `get_OwnerIsActor`."""
        entities = entities_from_state(state, self.owner_id, ev.target_id, actor_id=ev.actor_id)
        return bool(OwnerIsActor().evaluate(entities))

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        etat = triggered_ability_state(state, int(self.owner_id), ABILITY_ID)
        entities = entities_from_state(state, self.owner_id, ev.target_id, actor_id=ev.actor_id)
        ectx = ExecutionContext(state=state, rng=state.rng)
        phasal_trigger_passive_tree(etat).execute(entities, ectx)
        spawned = [p.get("unit") for (n, p) in ectx.emitted if n == "SpawnUnit"]
        trig = next((p for (n, p) in ectx.emitted if n == "TriggerAbility"), None)
        if not spawned and trig is None:
            return None
        return {"passive": ABILITY_ID, "owner": int(self.owner_id),
                "spawned": spawned, "ability_state": etat,
                "retrigger_targets": (trig.get("targets") if trig else None),
                "retrigger_dispatched": (trig.get("dispatched") if trig else None),
                "retrigger_results": (trig.get("results") if trig else None),
                "dsl": True}
