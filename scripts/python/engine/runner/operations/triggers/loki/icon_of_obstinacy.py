"""`IdunBattleLogic.Entities.Abilities.Triggered.Loki.IconOfObstinacy_AddArmourBuffAbility` -- le
volet ARMURE du passif `IconOfObstinacy` (`TriggeredAbilityType` 0x610 = 1552) d'`astarLysander`
(HERO, HORS du pool par defaut -> injection catalogue, cf. `docs/rl/case-270d-trait-hors-enum.md`).

Tache #919, face COMBAT. Le volet DEGAT (`IconOfObstinacy_AddDamageBuffAbility`) n'est PAS un
trigger : c'est un owner-effect pose a l'init de l'ability -- il vit dans
`effects.factory.ABILITY_INIT_OWNER_EFFECTS`, et sa RE est en tete de
`engine/entities/effects/loki/icon_of_obstinacy.py`. Les DEUX faces DECISION (owner et non-owner)
vivent dans `playbook/adjacent_unit_preference.py` et `playbook/non_owner.py`.

================================================================================================
RE (decompile ghidra, build `rnca9r7q6c`)
================================================================================================

## 1. `...IconOfObstinacy_AddArmourBuffAbility$$CreateTrigger` -- conjonction de TROIS termes

    affected = Owner@DSLSelectors+0x30
             + UnitsWithTrait( AdjacentFriends(Owner@0x30, unique = 1, selType = 3),
                               0x40f = UnitTrait.TerminatorArmour, selType = 3 )
                                                   # == `AIconOfObstinacyAbility$$GetAffectedUnits`

    return   On( 0x28 = EventTriggerType.UnitFinishedTurn, ownerNeedsToBeAlive = 1 )
           & DSLTriggers.Contains( list = affected, elements = Actor@DSLSelectors+0x40 )
           & DSLTriggers.AmountIsZero( DSLFormulas.TimesAttackMadeThisTurn( attacker = Actor@0x40,
                                                                           rangeType = null ) )

TROIS lectures qui ne se devinent pas :

  * **AUCUN `get_OwnerIsActor`.** Le gate d'appartenance est le `Contains` : l'ability fire quand
    N'IMPORTE QUELLE unite clot son tour, et ne retient que celles du set `affected`. Le porteur y
    est (par `op_Addition`, SANS condition de trait) et ses amis Terminator adjacents aussi.
  * **`On(0x28 = UnitFinishedTurn)`, PAS `On(0x29 = UnitFinishedTurnNormally)`** -- l'evenement SANS
    le gate `!isTerminated` (`FinishUnitTurnOperation$$Execute` publie les deux, cf.
    `dispatch/turn.py`). Une terminaison FORCEE declenche donc le buff, elle aussi.
  * **`rangeType = null`** sur `TimesAttackMadeThisTurn` -> c'est le compteur TOTAL
    (`ActorStatisticsComponent+0x24`), que
    `IdunBattle.Entities.Formulas.AmountOfAttacksMadeThisTurnFormula$$Calculate` lit quand son
    `Nullable<AttackRangeType>` n'a pas de valeur. Ce champ EST porte (#508-r1,
    `components.unit_attacks_made_this_turn`) -- les variantes Melee/Ranged (+0x2c/+0x28) ne le sont
    pas, et ce call-site n'en a pas besoin.

## 2. `...IconOfObstinacy_AddArmourBuffAbility$$CreateBehaviour(abilityState, triggerType)`

    return DSLBehaviors.AddDynamicStatModifierEffect(
               targets = Actor@DSLSelectors+0x40,
               source  = Owner@DSLSelectors+0x30,
               effectType = 0x628 = EffectType.IconOfObstinacy_ExtraArmor,
               statType   = 0x10 = StatType.FixedArmor,
               abilityStateSelector = BaseTriggeredAbility$$get_AbilityStateReference(this),
               turns = DSLFormulas.TurnsFromRounds(1),
               isHidden = <non lu : registre non initialise au decompile> )

Le couple (`targets`, `source`) tranche « self-buff vs buff d'autrui » -- ici la SOURCE est le
porteur et la CIBLE l'unite qui vient de clore son tour ; c'est ce qui fait indexer la magnitude sur
l'`AbilityState` de Lysander (cf. `IconOfObstinacyExtraArmorEffect`). `+0x30 = Owner` /
`+0x40 = Actor` sont LUS (`entities/selectors/accessors.py` : `AreEqual(+0x30, +0x40)` EST
`get_OwnerIsActor`), pas devines.

⚠ `isHidden` : le dernier argument sort d'un registre que ghidra n'initialise pas (`in_stack_...`).
Il n'a AUCUN observable cote port (le flag ne pilote que l'affichage) -- non modelise plutot que
devine.

## 3. CE QUE LE PORT NE COUVRE PAS -- residus NOMMES

  * `CreateRefreshValueTrigger` de l'effet (`On(0x38 = BlockDamageChanged) & get_OwnerIsActor`) :
    le vecteur `On(0x38)` n'est emis par aucun site du port -> la magnitude est FIGEE a la pose. Le
    natif, lui, la recalcule quand le `BlockDamage` de la cible bouge.
  * `selectionType = 3` (`OnlyAliveAndTargetable`) du selecteur : le port n'honore que le volet
    ALIVE, comme partout ailleurs dans cette famille.
  * ~~L'adjacence est `hexgeo.distance == 1` ... PERMISSIF au bord d'une marche >= 2.~~ **CABLE
    (#943-r7)** : `icon_of_obstinacy_affected_units` passe desormais par le foyer
    `engine.battle_query.is_adjacent`, donc par la liste STOCKEE du `ConnectivityComponent` PUIS la
    porte `|dElev| < 2`. Le couple est ferme DANS LE MEME COMMIT avec l'autre expression du meme
    `AIconOfObstinacyAbility$$GetAffectedUnits`
    (`entities/effects/loki/icon_of_obstinacy.py::create_aura_attack_damage_bonus_for_ally`) : les
    cabler separement aurait fait diverger le buff d'ARMURE du bonus de DEGAT.

DOCTRINE #149 : le trigger (predicats + selecteur) est COLLAPSE imperativement -- lecture d'etat --
et la feuille `AddDynamicStatModifierEffect` est le noeud DSL deja porte, qui delegue a
`AddEffectOperation`.
"""
from __future__ import annotations

from typing import Optional

from ....state import State
# #943-r7 -- les deux canaux du substrat d'adjacence NATIF, en FORME B (#485-r1-r1). Aucun seeding :
# `State.board` est deja la, et c'est le MEME board que celui d'ou la face jumelle (le ctx d'aura)
# tire les siens.
from .....entities.pathfinding import board as _board
from ..... import battle_query as _bq
from ....components import (OwnerComponent, PositionComponent, UnitComponent,
                            unit_attacks_made_this_turn)
from ....abilities.base import convert_rounds_to_turns
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.effects import AddDynamicStatModifierEffect
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.effect_type import EffectType
from .....entities.selectors.accessors import Actor
from .....entities.selectors.tiles import Caster
from .....entities.stats import StatType
from .....entities.traits.unit_trait import UnitTrait
from .....entities.triggered_ability_type import TriggeredAbilityType
from ..base import TriggeredAbility, TriggerEvent
from ....damage_model import target_trait_names

ABILITY_ID = "IconOfObstinacy"
ICON_OF_OBSTINACY = int(TriggeredAbilityType.IconOfObstinacy)          # 0x610 = 1552
EXTRA_ARMOR_EFFECT = int(EffectType.IconOfObstinacy_ExtraArmor)        # 0x628 = 1576
EXTRA_ARMOR_EFFECT_NAME = "IconOfObstinacy_ExtraArmor"
TERMINATOR_ARMOUR = int(UnitTrait.TerminatorArmour)                    # 0x40f = 1039

#: `On(0x28)` -- l'evenement SANS le gate `!isTerminated` (cf. §1).
_ON_UNIT_FINISHED_TURN = int(EventTriggerType.UnitFinishedTurn)        # 0x28 = 40
#: `TurnsFromRounds(1)` du behaviour.
_BUFF_ROUNDS = 1


def _has_terminator_armour(state: State, unit_id: int) -> bool:
    """`IdunBattle.Entities.UnitExtensions$$HasTrait(u, 0x40f)` -> `BaseUnitComponent$$HasTrait`.

    Substrat d'ENTITE (`StatsComponent.ctx.traits`), le MEME que lit `damage_model
    .target_trait_names` (#267-r1) -- et non le kit gameconfig cache par `visualId`. Le foyer est
    ce lecteur-la : les traits y sont des NOMS, l'enum sert a NOMMER le membre au site, pas a
    convertir. Composant absent -> faux (une unite sans stats n'a aucun trait porte)."""
    return UnitTrait.TerminatorArmour.name in (target_trait_names(state, int(unit_id)) or ())


def icon_of_obstinacy_affected_units(state: State, owner_id: int) -> list:
    """`AIconOfObstinacyAbility$$GetAffectedUnits` -- MIRROR du selecteur partage :

        Owner + UnitsWithTrait( AdjacentFriends(Owner, unique, OnlyAliveAndTargetable),
                                0x40f = TerminatorArmour, OnlyAliveAndTargetable )

    ⚠ `Owner` entre par `TargetsSelector$$op_Addition`, donc SANS passer par le filtre de trait :
    le porteur est dans le set meme s'il perdait `TerminatorArmour`.

    Rend les entity-ids. Foyer UNIQUE de ce noeud cote port -- le trigger ci-dessous ET
    `IconOfObstinacyExtraDmgEffect` decrivent le MEME selecteur natif, mais le second est evalue
    contre le ctx d'aura (pas contre l'ECS), d'ou deux expressions du meme fait ; elles sont tenues
    d'accord par `test_919_icon_of_obstinacy_offline.py`."""
    owner = state.get_entity(owner_id)
    if owner is None:
        return []
    opc = owner.get_component(PositionComponent)
    ooc = owner.get_component(OwnerComponent)
    if opc is None or ooc is None:
        return []
    # #943-r7 -- `AdjacentFriends(Owner)` = `Friends(Owner, Units(AdjacentTiles(Owner)) - Owner, 3)`
    # : l'ENUMERATION part du PORTEUR, sur la liste STOCKEE du `ConnectivityComponent`, puis la
    # porte `|dElev| < 2` de `TileQuery$$IterateAdjacentTiles`. Board absent (`State.board is None`)
    # -> `(None, None)` -> repli geometrique NOMME, le comportement d'avant.
    elev_by_pos, neigh_by_pos = _board.adjacency_channels(getattr(state, "board", None))
    out = [int(owner_id)]                        # `op_Addition` : le porteur, INCONDITIONNEL
    for uid, ent in state.entities.items():
        if int(uid) == int(owner_id):
            continue                             # `AdjacentFriends` retire la source (`- unit`)
        uc = ent.get_component(UnitComponent)
        if uc is not None and not uc.alive:
            continue                             # volet ALIVE de `selectionType = 3`
        oc = ent.get_component(OwnerComponent)
        pc = ent.get_component(PositionComponent)
        if oc is None or pc is None or oc.team != ooc.team:
            continue                             # `Friends` = meme equipe que le porteur
        if not _bq.is_adjacent((opc.col, opc.row), (pc.col, pc.row),
                               elev_by_pos, neigh_by_pos):
            continue                             # `AdjacentTiles(Owner)` : la liste STOCKEE (#943-r7)
        if not _has_terminator_armour(state, uid):
            continue                             # `UnitsWithTrait(0x40f = TerminatorArmour)`
        out.append(int(uid))
    return out


class IconOfObstinacyAddArmourBuffAbility(TriggeredAbility):
    """`On(0x28 = UnitFinishedTurn) & Contains(GetAffectedUnits(), Actor)
    & AmountIsZero(TimesAttackMadeThisTurn(Actor, null))`
    -> `AddDynamicStatModifierEffect(targets = Actor, source = Owner, 0x628, FixedArmor,
    AbilityStateReference, TurnsFromRounds(1))`.

    Lisible : quand `astarLysander` -- ou un ami portant `TerminatorArmour` et adjacent a lui --
    termine son tour SANS avoir attaque, il gagne `extraArmor + chance% de son BlockDamage` en
    `FixedArmor` pour un round. Cf. l'en-tete du module."""

    event_id = _ON_UNIT_FINISHED_TURN
    TRIGGERED_ABILITY_ID = ICON_OF_OBSTINACY

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        """Les DEUX termes non-`On` de la conjonction (§1). L'ordre est celui du decompile ; le gate
        « owner vivant » (`ownerNeedsToBeAlive = 1`) est deja porte par le dispatch."""
        actor = ev.actor_id
        if actor is None:
            return False
        # `Contains(affected, Actor@0x40)`
        if int(actor) not in icon_of_obstinacy_affected_units(state, self.owner_id):
            return False
        # `AmountIsZero(TimesAttackMadeThisTurn(Actor@0x40, rangeType = null))` -- compteur TOTAL
        # `ActorStatisticsComponent+0x24` (#508-r1), remis a zero au turn-start du proprietaire.
        return int(unit_attacks_made_this_turn(state, int(actor)) or 0) == 0

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        turns = int(convert_rounds_to_turns(state, _BUFF_ROUNDS))     # `TurnsFromRounds(1)`
        entities = entities_from_state(state, self.owner_id, None, actor_id=ev.actor_id)
        ectx = ExecutionContext(state=state, rng=state.rng)
        AddDynamicStatModifierEffect(Actor(), Caster(), EXTRA_ARMOR_EFFECT,
                                     int(StatType.FIXED_ARMOR), name=EXTRA_ARMOR_EFFECT_NAME,
                                     duration_turns=turns).execute(entities, ectx)
        placed = [p for (n, p) in ectx.emitted if n == "AddDynamicStatModifierEffect"]
        if not placed:
            return None
        return {"passive": ABILITY_ID, "owner": int(self.owner_id),
                "target": int(ev.actor_id), "effect": EXTRA_ARMOR_EFFECT,
                "turns": turns, "dsl": True}
