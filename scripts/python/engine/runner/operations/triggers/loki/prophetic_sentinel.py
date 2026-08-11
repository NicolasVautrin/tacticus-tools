"""`IdunBattleLogic.Entities.Abilities.Triggered.Loki.PropheticSentinel_OverwatchAbility` -- la
SECONDE des deux abilities natives du passif de kit `PropheticSentinel` (`TriggeredAbilityType`
0x607 = 1543, `thousSekhetar` << Sekhetar Robot >>). Elle RE-ARME l'overwatch du porteur en fin de
son tour quand au moins UN ami ADJACENT porte le trait `Psyker`.

La PREMIERE (`PropheticSentinel_AddBuffAbility`) pose les trois owner-effects PERMANENTS a l'init
et vit dans `entities/effects/loki/prophetic_sentinel.py` (canal `ABILITY_INIT_OWNER_EFFECTS`).
Les deux classes sont DISTINCTES et n'ont NI le meme trigger NI le meme behaviour.

RE (decompile ghidra, build `rnca9r7q6c`)
-----------------------------------------
`...PropheticSentinel_OverwatchAbility$$CreateTrigger` (MIRROR 1:1) :

      On( 0x17 = EventTriggerType.TurnEnd, ownerNeedsToBeAlive = 1 )
    & <DSLTriggers+0x28>                                    # IsTurnOf(Owner)
    & AmountIsEqualOrGreater(
          Count( UnitsWithTrait(
                     AdjacentFriends( unit     = Caster@DSLSelectors+0x48,
                                      unitTile = CasterTile@DSLSelectors+0x50,
                                      unique   = 1 ),       # surcharge B -> selectionType 3 EN DUR
                     0x3ea = UnitTrait.Psyker, 3 ) ),
          <DSLFormulas+0x20> = Direct(1) )                  # SEUIL = 1

⚠ L'ORDRE des `op_BitwiseAnd` est `(On & <+0x28>) & AmountIsEqualOrGreater` ; le noeud de compte est
CONSTRUIT en premier dans le corps mais COMBINE en dernier. Aucun effet observable (conjonction
pure, tous les noeuds sont purs), cite pour la fidelite de lecture.

`...PropheticSentinel_OverwatchAbility$$CreateBehaviour` (MIRROR 1:1) :

      ActivateEffect( Owner@DSLSelectors+0x30, 0x3f1 = EffectType.Overwatch_AutoAttack )

Ce corps n'apparait PAS sous ce nom dans `frida/methods.tsv` : il est DEDUPLIQUE (identical code
folding) avec `...PurgeResponse_ActiveOverwatchAbility$$CreateBehaviour`, dont c'est exactement le
corps. Le depart a ete LU dans la table des pointeurs de methodes (le metadata declare
`CreateTrigger` slot 26 ET `CreateBehaviour` slot 28 pour la classe ; les deux entrees consecutives
de la table donnent les deux corps -- celui du `CreateTrigger` etant le corps propre lu ci-dessus,
celui du `CreateBehaviour` etant le corps partage avec PurgeResponse). Ne PAS conclure de l'absence
dans la table : elle ne prouve rien (cf. CLAUDE.md).

Le JUMEAU STRUCTUREL est `PurgeResponse` (`votanSmnSteeljack`), qui differe sur le seul noeud de
comptage : `AmountIsGreaterThanZero(Count(HeroUnits(UnitsFromFaction(AdjacentFriends(Owner, 1, 3),
0x14))))` la ou PropheticSentinel exige `>= 1` unite a trait `Psyker`. Le `>= Direct(1)` et le
`> 0` sont equivalents sur un cardinal, mais le noeud natif est bien `AmountIsEqualOrGreater` --
on mirrore ce qui est ecrit.

`Owner` vs `Caster` : le trigger lit `Caster@+0x48` / `CasterTile@+0x50`, le behaviour lit
`Owner@+0x30`. Pour une TRIGGERED-ability les trois designent le porteur (le behaviour est execute
par `IdunBattle.Entities.Abilities.BaseTriggeredAbility$$Execute` sur son propre porteur, et
`entities_from_state(state, owner_id)` pose `caster == owner`), mais les noeuds portes CITENT le
slot que le natif cite.

CE QUE LE PORT REND OBSERVABLE
------------------------------
`ActivateEffect` (feuille deja portee, `abilities/behaviours/effects.py`) : si l'instance
`Overwatch_AutoAttack` du porteur a ete CONSOMMEE (`RangedAutoAttackDeactivateOnAttack`, le
<< un seul tir par activation >> de #127), elle repasse `active = True` ; si elle est absente, elle
est MATERIALISEE. `thousSekhetar` porte le trait `Overwatch` au gameconfig, donc l'instance existe
des le spawn -- le volet utile ici est la REACTIVATION.

⚠ Le natif ne pose AUCUN gate << l'overwatch a-t-il ete consomme ? >> : le trigger fire a chaque fin
de tour du porteur des qu'un ami Psyker est adjacent, et `ActivateEffect` est un no-op quand le flag
est deja pose (mirror exact du `RefreshEffectsOperation$$ActivateEffect`, `+0x5c = 1`).

Qualification des enums
-----------------------
    EventTriggerType 0x17 = 23 TurnEnd
    UnitTrait        0x3ea = 1002 Psyker      (!= EffectType 1002 CombatRestoratives)
    EffectType       0x3f1 = 1009 Overwatch_AutoAttack
                     (!= ActiveAbilityType 1009 ResurrectionOrb, != TriggeredAbilityType 1009
                      WhipcoilBody, != UnitTrait 1009 Resilient)
    TriggeredAbilityType 0x607 = 1543 PropheticSentinel
                     (!= EffectType 1543 ModifiedExoarmour_PierceReduction)
"""
from __future__ import annotations

from typing import Optional

from ....state import State
from ....components import OwnerComponent, PositionComponent
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.effects import ActivateEffect
from .....entities.selectors.accessors import Owner
from .....entities.selectors.tiles import Caster
from .....entities.selectors.units import AdjacentFriends, UnitsWithTrait
from .....dsl.base import Const
from .....entities.effect_type import EffectType
from .....entities.traits.unit_trait import UnitTrait
from .....entities.unit_selection_type import UnitSelectionType
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from ..base import TriggeredAbility, TriggerEvent
from .....entities.formulas import Count

_TURN_END = int(EventTriggerType.TurnEnd)                  # `On(0x17)`
OVERWATCH_AUTO_ATTACK = int(EffectType.Overwatch_AutoAttack)   # 0x3f1 = 1009
#: `UnitSelectionType` LU au dernier argument du `UnitsWithTrait` natif (et EN DUR dans la surcharge
#: B d'`AdjacentFriends`) : `3` = `OnlyAliveAndTargetable`.
SELECTION = int(UnitSelectionType.OnlyAliveAndTargetable)  # 3
#: `<DSLFormulas+0x20>` = `Direct(1)`, la constante pre-cachee du `.ctor` de `DSLFormulas`.
MIN_ADJACENT_PSYKER_FRIENDS = 1


def adjacent_psyker_friends_selector():
    """L'ARBRE du noeud de comptage de `...PropheticSentinel_OverwatchAbility$$CreateTrigger`
    (doctrine #149 : l'artefact natif est un SELECTEUR, donc le port est un arbre) :

        UnitsWithTrait( AdjacentFriends(Caster@+0x48, CasterTile@+0x50, unique = 1),
                        UnitTrait.Psyker, 3 )

    La surcharge B d'`AdjacentFriends` (`(this, unit, unitTile, unique)`) developpe en
    `Friends(unit, Units(AdjacentTiles(unitTile), unique, 3) - unitTile, 3)` : `3` EN DUR aux deux
    etages, ancre geometrique = `unitTile`, reference d'equipe = `unit`. Cote port les deux
    designent le CASTER (une unite mono-tuile a sa tuile pour position), d'ou `center=Caster()` et
    `reference=Caster()`.

    Import PARESSEUX de `Count` : `entities/formulas` est assemble APRES le paquet
    `entities/selectors` -- meme convention anti-cycle que
    `effects/loki/amulet_of_the_voidwyrm.py::adjacent_friendly_summons_and_decoys_selector`."""
    return UnitsWithTrait(
        AdjacentFriends(Caster(), Const(1), Caster(), selection_type=SELECTION),
        int(UnitTrait.Psyker), selection_type=SELECTION)


def adjacent_psyker_friends_count(state: State, unit_id: int) -> Optional[int]:
    """`Count(<le selecteur ci-dessus>)` pour le porteur. `None` si le porteur n'a ni equipe ni
    tuile -- jamais un `0` invente (un 0 fabrique fermerait le trigger a tort)."""
    ent = state.get_entity(int(unit_id))
    oc = ent.get_component(OwnerComponent) if ent is not None else None
    pc = ent.get_component(PositionComponent) if ent is not None else None
    if oc is None or oc.team is None or pc is None:
        return None
    return int(Count(adjacent_psyker_friends_selector())
               .calculate(entities_from_state(state, int(unit_id))))


def prophetic_sentinel_overwatch_tree():
    """Feuille de `...PropheticSentinel_OverwatchAbility$$CreateBehaviour` (MIRROR 1:1) :
    `ActivateEffect(Owner@DSLSelectors+0x30, 0x3f1 = Overwatch_AutoAttack)`. Corps DEDUPLIQUE avec
    `PurgeResponse_ActiveOverwatchAbility$$CreateBehaviour`. RNG-free."""
    return ActivateEffect(Owner(), OVERWATCH_AUTO_ATTACK, "Overwatch_AutoAttack")


class PropheticSentinelOverwatchAbility(TriggeredAbility):
    """`PropheticSentinel_OverwatchAbility` -- re-arme l'overwatch du Sekhetar Robot en fin de SON
    tour s'il a au moins un ami ADJACENT a trait `Psyker`.

    `matches` COLLAPSE les deux predicats du `CreateTrigger` (doctrine #149 : les predicats d'un
    trigger sont des lectures d'etat, la feuille en dessous reste declarative) :
      * `<DSLTriggers+0x28>` = `IsTurnOf(Owner)` -> `OwnerComponent.player == ev.player_id`
        (mirror `IdunBattle.Entities.UnitExtensions$$IsControlledByCurrentPlayer` ; meme lecture que
        `components.py::unit_state['is_turn_of_owner']`) ;
      * `AmountIsEqualOrGreater(Count(...), Direct(1))` -> l'arbre `adjacent_psyker_friends_count`.
    `On(..., ownerNeedsToBeAlive = 1)` est deja porte par le gate `CanGetAbilityTrigger` du
    dispatcher (owner vivant), pas re-teste ici."""

    event_id = _TURN_END
    TRIGGERED_ABILITY_ID = 1543             # `TriggeredAbilityType.PropheticSentinel` (0x607)

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        owner = state.get_entity(self.owner_id)
        oc = owner.get_component(OwnerComponent) if owner is not None else None
        if oc is None:
            return False
        # `IsTurnOf(Owner)` : le tour qui se termine est celui du camp du porteur.
        if ev.player_id is not None and oc.player != ev.player_id:
            return False
        n = adjacent_psyker_friends_count(state, self.owner_id)
        # `None` = porteur sans equipe/tuile : le selecteur natif ne rend rien -> 0 -> pas de fire.
        return n is not None and n >= MIN_ADJACENT_PSYKER_FRIENDS

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        if state.effects is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        prophetic_sentinel_overwatch_tree().execute(
            entities_from_state(state, self.owner_id), ectx)
        acts = [p for n, p in ectx.emitted if n == "ActivateEffect"]
        if not acts:
            return None
        p = acts[0]
        return {"passive": "PropheticSentinel", "unit": self.owner_id,
                "effect_type": OVERWATCH_AUTO_ATTACK,
                "created": bool(p.get("created")), "activated": bool(p.get("activated"))}
