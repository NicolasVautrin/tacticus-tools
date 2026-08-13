"""`RelicOfLostCadia` (0x5b3 = 1459) -- relique ASTRA MILITARUM, TROIS porteurs `lineup`
(`astraBullgryn`, `astraOrdnance`, `astraPrimarisPsy`), tous DANS le pool rank 17.

i2 : « Friendly surrounding Imperial Summons have Final Vengeance. When the relic bearer is
defeated, summons a Cadian Guardsman in its hex with 5817 Health, 3492 Damage and 1166 Armour. »

VOIE D'ATTRIBUTION : item RELIQUE (`UnitConfiguration.TertiaryAbility`) -> `RELIC_ABILITY_TRIGGERS`,
`AbilityState` TERTIAIRE, montage `--equip-relic` (etat 2 de la gate relique). Pas une active.

DEUX classes natives pour UNE cle (patron `LetTheGalaxyBurn` / `DaemonfleshPlate`).

================================ 1. `RelicOfLostCadiaAbility` ================================

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.RelicOfLostCadiaAbility$$CreateTrigger` :

      On(0x4  = UnitAfterMove,        ownerNeedsToBeAlive: 1)
    | ( On(0x32 = UnitAdded,          ownerNeedsToBeAlive: 1) & IsAlive(Actor@DSLSelectors+0x40) )
    | On(0x3b = UnitBecameTargetable, ownerNeedsToBeAlive: 1)
    | On(0x2d = UnitRevived,          ownerNeedsToBeAlive: 1)
    | OnOwnerSpecificAbilityInit(this.AbilityType = 0x5b3 = 1459)

⚠ CINQ disjonctions, dont QUATRE `On()` -> `event_ids` (le dispatch teste `event_id` PUIS
`event_ids`, `dispatch/core.py`). C'est le patron `SavageKiller`, pas celui de `FuryFromTheDelve`
(qui ventile en deux CLASSES parce que ses deux bras ont des BEHAVIOURS differents ; ici les quatre
bras partagent le meme `CreateBehaviour`).

⚠ LE 5e VECTEUR, `OnOwnerSpecificAbilityInit`, N'EST PAS UN TRIGGER, et il ne peut PAS passer par
`ABILITY_INIT_OWNER_EFFECTS` : cette table pose l'effet sur l'OWNER, or l'effet vise ici le
VOISINAGE de l'owner (les summons imperiaux allies adjacents), jamais l'owner lui-meme. La couverture
vient du vecteur `On(0x32 = UnitAdded)`, qui refait EXACTEMENT le meme balayage a l'apparition de
toute unite -- y compris celle du porteur au spawn. RESIDU NOMME : un porteur DEJA sur le plateau a
t=0 d'un etat hydrate (pas d'`On(UnitAdded)` rejoue) ne re-pose pas l'effet tant qu'aucun des quatre
vecteurs ne survient ; en pratique le premier deplacement d'une unite du plateau le declenche.

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.RelicOfLostCadiaAbility$$CreateBehaviour` :

    If( get_OwnerIsCaster,
        AddEffect( 0x5ae = 1454 EffectType.FinalVengeance_UnitEffect,
                   AbilityStateReference,
                   source  = Owner@DSLSelectors+0x30,
                   targets = IsImperialAndSummon( SurroundingFriends(
                                 unit  = Owner@+0x30,
                                 range = <DSLFormulas+0x20> = Direct(1),
                                 unique: 1, unitSelectionType: 3 = OnlyAliveAndTargetable) ),
                   options = default(Nullable<AddEffectBehaviourOptions>) ),
        If( AreFriends(Owner@+0x30, Caster@+0x48, comparisonType: 0, anyEntity: 0)
            op_BitwiseAnd IsInRange(Owner@+0x30, Caster@+0x48,
                                    range = <DSLFormulas+0x20> = Direct(1)),
            AddEffect( 0x5ae, AbilityStateReference, source = Owner@+0x30,
                       targets = IsImperialAndSummon(Caster@+0x48), options = default ),
            null ) )

`...RelicOfLostCadiaAbility$$IsImperialAndSummon(targets)` =
`UnitsWithTraits(targets, [0x1a = 26 Imperial, 0x2 = 2 Summon], selectionType: 3)`.
`DSLSelectors$$UnitsWithTraits` est une INTERSECTION (decompile : `result = entities` puis, par
trait, `result = result op_BitwiseAnd UnitsWithTrait(entities, trait, sel)`) -- le nom « And » du
helper est donc exact.

⚠ `UnitTrait.Imperial` (26) n'est JAMAIS dans `gameconfig.unit().traits` : c'est un pseudo-trait
DERIVE de `GrandAllianceId` (`idun.Idun.Source.Shared.GrandAlliance$$GetTrait`). Le port le derive
dans `entities/traits/unit_trait.entity_trait_names`. MESURE LIVE (runner 585, RPC `combatSnapshot`,
2026-08-13) : les quatre unites Astra du plateau rendent bien `26` dans leurs traits -- p.ex.
`astraDreir` = `[16 Hero, 26 Imperial, 1009 Resilient, 1042 Unstoppable, 9000 DeathKorpsKrieg]`.

⚠ La RANGE est `<DSLFormulas+0x20>`, et ce slot est `One` -- LU au `.ctor` de `DSLFormulas`
(`+0x18 Zero, +0x20 One, +0x28 Two, +0x30 OneHundred, +0x38 MinusOne, ...`, chaque champ recevant
son litteral dans le ctor). Ce n'est PAS une variable du gameconfig : la config de la relique ne
porte que `summonHp`/`summonDmg`/`summonArmor`. Corroboration croisee :
`...RelicOfLostCadiaAbility$$TargetUnitsInRange` reconstruit le MEME `SurroundingFriends` avec le
MEME slot.

========================== 2. `RelicOfLostCadiaAbility_SummonUnit` ==========================

    CreateTrigger   = On(0x0 = UnitDeath, ownerNeedsToBeAlive: 0) op_BitwiseAnd get_OwnerIsTarget
    CreateBehaviour = Spawn( parentSelector = Owner@DSLSelectors+0x30,
                             tiles = PickRandomly( FreeTilesOrAdjacentFreeTiles( Tiles(Target@+0x60) ),
                                                   amount: 1, allowDuplicates: 0,
                                                   maxDuplicatesAllowed: 0x7fffffff,
                                                   ignoreForcedTargets: 0 ),
                             spawnUnitId = Config.GetStringConstant(0x0 = unitId),
                             options = SpawnUnitOptions.WithStatsFromConfig(Config, abilityState,
                                                                            null, null) )

`ownerNeedsToBeAlive: 0` -> `fire_on_death = True` (l'owner est deja `alive=False` au dispatch).
`get_OwnerIsTarget` sur `On(UnitDeath)` : le port construit l'evenement avec `actor = killer` et
`target = dying` (`unit_death_triggers`), donc l'owner doit etre le MOURANT.

`FreeTilesOrAdjacentFreeTiles` n'a pas de noeud homonyme cote port : son corps se DEPLIE en
`Otherwise(CanAddUnit(tiles), CanAddUnit(AdjacentTiles(tiles)))`. ⚠ L'ARITE tranche le litteral
`isSteppable` (#955-r2) : la surcharge **1 argument** (celle du site, `FreeTilesOrAdjacentFreeTiles(tiles)`)
lit `<DSLTriggers>+0x48` -> `allow_steppable=True`.

`WithStatsFromConfig(Config, abilityState, null, null)` -> `ability_state=` EXPLICITE : l'unite posee
monte ses stats sous l'`AbilityState` de la RELIQUE (tertiaire), pas sous l'`active_ability_level` du
porteur (le defaut de la feuille `Spawn`). Les trois variables lues sont `summonHp`/`summonDmg`/
`summonArmor` (`ordinal = 1` -> `stat_key_suffix=""`), niveau 10 = 5817 / 3492 / 1166, ce que l'i2
corrobore.

FORME DU PORT (doctrine #149) : les deux `CreateTrigger` COLLAPSENT imperativement dans `matches` ;
les deux `CreateBehaviour` sont des ARBRES DSL.
"""
from __future__ import annotations

from typing import Optional

from .....dsl.base import Const
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.ability_constant_type import AbilityConstantType
from .....entities.behaviours import If
from .....entities.effect_type import EffectType
from .....entities.selectors.accessors import Actor, Owner, OwnerTile, Target
from .....entities.selectors.geometry import Otherwise, PickRandomly
from .....entities.selectors.tiles import AdjacentTiles, CanAddUnit, Caster
from .....entities.selectors.units import SurroundingFriends, Tiles, units_with_traits
from .....entities.traits.unit_trait import UnitTrait
from .....entities.triggered_ability_type import TriggeredAbilityType
from .....entities.triggers import AreFriends, IsAlive, IsInRange, OwnerIsCaster, TriggerAnd
from .....entities.unit_selection_type import UnitSelectionType
from .....entities.unit_team_selection_type import UnitTeamSelectionType
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.effects import AddEffect
from ....abilities.behaviours.summon import Spawn
from ....state import State
from ..base import TriggeredAbility, TriggerEvent, triggered_ability_state

ABILITY_ID = "RelicOfLostCadia"
RELIC_OF_LOST_CADIA = int(TriggeredAbilityType.RelicOfLostCadia)         # 0x5b3 = 1459
FINAL_VENGEANCE_EFFECT = int(EffectType.FinalVengeance_UnitEffect)      # 0x5ae = 1454
UNIT_ID_KEY = AbilityConstantType.unitId.name                           # `GetStringConstant(0x0)`

_ON_AFTER_MOVE = int(EventTriggerType.UnitAfterMove)                    # 0x04 = 4
_ON_UNIT_ADDED = int(EventTriggerType.UnitAdded)                        # 0x32 = 50
_ON_BECAME_TARGETABLE = int(EventTriggerType.UnitBecameTargetable)      # 0x3b = 59
_ON_UNIT_REVIVED = int(EventTriggerType.UnitRevived)                    # 0x2d = 45
_ON_UNIT_DEATH = int(EventTriggerType.UnitDeath)                        # 0x00 = 0

#: `unitSelectionType` de `SurroundingFriends` et de `UnitsWithTraits` (le litteral `3` des deux
#: sites). Type DECLARE lu dans `frida/methods.tsv`.
_SELECTION = int(UnitSelectionType.OnlyAliveAndTargetable)              # 3
#: `comparisonType` d'`IdunBattleLogic.Entities.DSLTriggers$$AreFriends` (litteral `0` du site).
_FRIENDS_COMPARISON = int(UnitTeamSelectionType.ByCurrentTeam)          # 0
#: `<DSLFormulas+0x20>` = `Direct(1)` -- cf. l'en-tete (slot LU au `.ctor` de `DSLFormulas`).
_RANGE_ONE = 1
#: `PickRandomly(entities, amount, allowDuplicates, maxDuplicatesAllowed, ignoreForcedTargets)`
#: -- les quatre litteraux du site, transcrits tels quels.
_PICK_MAX_DUPLICATES = 0x7FFFFFFF


def is_imperial_and_summon(targets):
    """`...RelicOfLostCadiaAbility$$IsImperialAndSummon(targets)` =
    `UnitsWithTraits(targets, [0x1a Imperial, 0x2 Summon], selectionType: 3)`.

    L'ORDRE des deux traits est celui des `List.Add` du decompile ; l'operation etant une
    INTERSECTION il n'est pas observable, mais on le transcrit."""
    return units_with_traits(targets, (UnitTrait.Imperial, UnitTrait.Summon),
                             selection_type=_SELECTION)


def relic_of_lost_cadia_behaviour_tree():
    """`...RelicOfLostCadiaAbility$$CreateBehaviour` -- MIRROR 1:1 (cf. l'en-tete du module).

    `duration_rounds=None` : le `Nullable<AddEffectBehaviourOptions>` du site est a ZERO, donc le
    champ `+0x78` (turnsNode) est NUL -> duree PAR DEFAUT de l'effet, jamais un litteral.

    ⚠ Le centre de `SurroundingFriends` est `OwnerTile()` et non `Owner()` : le port de ce noeud
    prend une POSITION (il la passe a `_within`), la ou le natif prend l'ENTITE. `OwnerTile` EST
    l'empreinte courante de l'owner, donc le meme centre. La reference d'EQUIPE du noeud porte est
    `ctx.caster` en dur -- exact ici, cette branche etant precisement gardee par `OwnerIsCaster`."""
    surrounding = is_imperial_and_summon(
        SurroundingFriends(OwnerTile(), Const(_RANGE_ONE), selection_type=_SELECTION))
    pose_zone = AddEffect(FINAL_VENGEANCE_EFFECT, EffectType.FinalVengeance_UnitEffect.name,
                          surrounding, duration_rounds=None, source_ref=Owner())
    voisin = TriggerAnd(AreFriends(Owner(), Caster(), selection_type=_FRIENDS_COMPARISON),
                        IsInRange(Owner(), Caster(), Const(_RANGE_ONE)))
    pose_un = AddEffect(FINAL_VENGEANCE_EFFECT, EffectType.FinalVengeance_UnitEffect.name,
                        is_imperial_and_summon(Caster()),
                        duration_rounds=None, source_ref=Owner())
    return If(OwnerIsCaster(), pose_zone, If(voisin, pose_un, None))


def relic_of_lost_cadia_spawn_tree(ability_state: tuple):
    """`...RelicOfLostCadiaAbility_SummonUnit$$CreateBehaviour` -- MIRROR 1:1.

    `FreeTilesOrAdjacentFreeTiles(tiles)` (surcharge 1 argument) est DEPLIE en
    `Otherwise(CanAddUnit(tiles, True), CanAddUnit(AdjacentTiles(tiles), True))` -- `allow_steppable`
    vaut `True` parce que cette surcharge lit `<DSLTriggers>+0x48` (#955-r2 : c'est l'ARITE qui
    tranche le litteral, pas une preference).

    `pick_n=1` folde le `PickRandomly(..., amount: 1, ...)` du site."""
    tuiles = Tiles(Target(), as_ids=True)
    libres = Otherwise(CanAddUnit(tuiles, allow_steppable=True),
                       CanAddUnit(AdjacentTiles(tuiles), allow_steppable=True))
    return Spawn(PickRandomly(libres, 1, False, _PICK_MAX_DUPLICATES, False), ABILITY_ID,
                 unit_id_constant=UNIT_ID_KEY, ability_state=ability_state)


class RelicOfLostCadiaAbility(TriggeredAbility):
    """`RelicOfLostCadiaAbility` -- confere `FinalVengeance_UnitEffect` (1454) aux summons IMPERIAUX
    allies adjacents, et re-evalue a chaque evenement qui peut changer le voisinage.

    QUATRE vecteurs, UN behaviour. `matches` = collapse du `CreateTrigger` : les quatre `On()` ne
    portent AUCUN predicat commun -- le seul conjoint est `IsAlive(Actor@+0x40)`, et il ne vaut QUE
    pour `On(UnitAdded)`. Tout le reste (qui recoit l'effet) est dans le `CreateBehaviour`, ou il
    DOIT rester : c'est un `If`, pas une gate de trigger."""
    #: `event_id` porte le vecteur le plus frequent ; les quatre sont dans `event_ids` (le dispatch
    #: teste les deux, cf. `dispatch/core.py`). Meme plomberie que `SavageKiller`.
    event_id = _ON_AFTER_MOVE
    event_ids = (_ON_AFTER_MOVE, _ON_UNIT_ADDED, _ON_BECAME_TARGETABLE, _ON_UNIT_REVIVED)
    TRIGGERED_ABILITY_ID = RELIC_OF_LOST_CADIA

    @staticmethod
    def _subject_id(ev: TriggerEvent):
        """L'entite du vecteur -- `Caster@+0x48` du `CreateBehaviour`, `Actor@+0x40` du
        `CreateTrigger`. Les quatre emetteurs portes posent la MEME unite dans les deux slots
        (`after_move_triggers` : `(mover, mover)` ; `on_unit_added` : `(added, added)` ;
        `unit_became_targetable_triggers` / `unit_revived_triggers` : idem) -- c'est aussi ce que
        fait le natif, dont l'`AbilityEntities` de ces evenements est unit-centric."""
        return ev.actor_id if ev.actor_id is not None else ev.target_id

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        sujet = self._subject_id(ev)
        if sujet is None or state.get_entity(self.owner_id) is None:
            return False
        if int(ev.event_id) != _ON_UNIT_ADDED:
            return True
        # `On(0x32 = UnitAdded) & IsAlive(Actor@+0x40)` -- le SEUL conjoint, et il ne vaut que sur
        # ce bras. Le recopier sur les trois autres eteindrait le rail sur toute unite morte
        # devenue ciblable / ressuscitee, que le natif, lui, laisse passer.
        ctx = entities_from_state(state, int(sujet), int(sujet), actor_id=int(sujet),
                                  owner_id=self.owner_id)
        return bool(IsAlive(Actor()).evaluate(ctx))

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        sujet = self._subject_id(ev)
        if sujet is None:
            return None
        # `Caster@+0x48` = l'entite du vecteur ; `Owner@+0x30` = le PORTEUR de la relique. Les deux
        # divergent des que ce n'est pas le porteur qui bouge -- c'est exactement ce que la
        # disjonction `If(OwnerIsCaster, ..., ...)` du natif distingue.
        entities = entities_from_state(state, int(sujet), int(sujet), actor_id=int(sujet),
                                       owner_id=self.owner_id)
        ectx = ExecutionContext(state=state, rng=state.rng)
        relic_of_lost_cadia_behaviour_tree().execute(entities, ectx)
        poses = [p for (n, p) in ectx.emitted if n == "AddEffect" and p.get("placed")]
        if not poses:
            return None
        return {"relic": ABILITY_ID, "owner": int(self.owner_id), "subject": int(sujet),
                "event": int(ev.event_id), "placed": poses}


class RelicOfLostCadiaSummonUnitAbility(TriggeredAbility):
    """`RelicOfLostCadiaAbility_SummonUnit` -- a la MORT du porteur, un `astraSmnGuardsman` apparait
    dans son hex (ou, a defaut, sur une tuile libre adjacente).

    `fire_on_death` : `On(UnitDeath, ownerNeedsToBeAlive: 0)` -- l'owner est deja `alive=False` au
    moment du dispatch, donc le gate << owner vivant >> de `CanGetAbilityTrigger` doit etre
    court-circuite, exactement comme `FinalJustice`."""
    event_id = _ON_UNIT_DEATH
    TRIGGERED_ABILITY_ID = RELIC_OF_LOST_CADIA
    fire_on_death = True

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        # `get_OwnerIsTarget` : sur `On(UnitDeath)` l'evenement porte `actor = killer` et
        # `target = dying` -- l'owner doit donc etre le MOURANT (meme lecture que `DawnBlade`,
        # qui teste l'autre slot parce que son trigger est `get_OwnerIsActor`).
        mourant = ev.dying_id if ev.dying_id is not None else ev.target_id
        return mourant is not None and int(mourant) == int(self.owner_id)

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        # `parentSelector = Owner@+0x30` : la feuille `Spawn` prend le PARENT dans `entities.caster`,
        # donc on pose le porteur en caster. `Tiles(Target@+0x60)` = l'hex du mort, et le mort EST
        # l'owner (`get_OwnerIsTarget`) -> meme entite dans les deux slots.
        entities = entities_from_state(state, int(self.owner_id), int(self.owner_id),
                                       owner_id=self.owner_id)
        ectx = ExecutionContext(state=state, rng=state.rng)
        etat = triggered_ability_state(state, self.owner_id, ABILITY_ID)
        relic_of_lost_cadia_spawn_tree(etat).execute(entities, ectx)
        spawned = [p for (n, p) in ectx.emitted if n == "Spawn"]
        if not spawned:
            return None
        return {"relic": ABILITY_ID, "owner": int(self.owner_id),
                "ability_state": etat, "spawned": spawned}
