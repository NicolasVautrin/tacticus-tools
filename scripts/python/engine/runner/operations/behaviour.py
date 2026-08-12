"""Mecaniques de COMPORTEMENT — **Battle Fatigue** (trait `BattleFatigue`).

RE ghidra (gqfc5mff6c, re-lu sur rnca9r7q6c) :
  `IdunBattleLogic.Entities.Abilities.Active.Loki.BattleFatigueAbility$$CreateTrigger = `OnDeath(1) & IsAdjacent(self,dying,2) &
   AreFriends(dying,self) & NOT HasEffect(self, 0x437=1079 IgnoreBattleFatigue) & NOT IsObjectOrSteppable(dying)
   & OwnerActive` -> quand une VRAIE UNITE ALLIEE **ADJACENTE** meurt et que self n'est pas immunise.
  L'ordre ci-dessus est celui du decompile, conjoint par conjoint (`op_BitwiseAnd` de gauche a droite) ;
  les selecteurs sont `+0x30 = self` et `+0x60 = dying`, et le conjoint terminal est le `OwnerActive`
  pre-alloue (`<factory+0x88>+0x20`).

⚠ `NOT IsObjectOrSteppable(dying)` A ETE ABSENT DU CODE jusqu'au 2026-08-05, alors que CETTE MEME
LIGNE d'en-tete le citait (#462-r4b-r1-r1-r1-r1-b-r1-r1). Ecart PERMISSIF : le port faisait fuir sur
la mort d'un allie OBJET/STEPPABLE (mur, tourelle, decoy, token) que le natif ignore. Il est
desormais porte par le foyer `entities/triggers.py::is_object_or_steppable` -- mirror de
`IdunBattleLogic.Entities.DSLTriggers$$IsObjectOrSteppable` = `HasTrait(x, 0x1b=27 Steppable) |
HasTrait(x, 0xd=13 Object)`, qui a HUIT call-sites natifs. Detail :
`docs/rl/case-462-r4b-r1-r1-r1-r1-b-r1-r1-object-or-steppable.md`.

⚠ LE `2` D'`IsAdjacent` N'EST PAS UN RAYON -- c'est un `UnitSelectionType` (#462-r4b-r1-r1-r1-r1-b-r1).
`IdunBattleLogic.Entities.DSLTriggers$$IsAdjacent(this, sel@+0x30 = self, sel@+0x60 = dying, 0x2)` ->
`IdunBattle.Entities.Triggers.IsAdjacentAbilityTrigger$$.ctor(this, selector1@+0x20, selector2@+0x28,
(int)selectionType@+0x18, query@+0x10)`. Dans `$$ShouldTrigger`, `+0x18` n'est lu QUE comme 2e argument
du `Select` des deux selecteurs ; la comparaison par paire est `query.AreEntitiesAdjacent(x, y)`
(slot 0x60), qui ne prend AUCUN rayon. Enum `IdunBattle.Entities.Enum.UnitSelectionType` :
`0=Any, 1=OnlyAlive, 2=OnlyTargetable, 3=OnlyAliveAndTargetable`. Le port lisait `dist <= 2` : il
declenchait la fuite pour un allie mort a 2 hex, que le natif IGNORE. Corrige -- le terme passe par le
mirror `entities/triggers.py::IsAdjacent`, comme les deux revives Narthecium/TaintedNarthecium qui
portent le MEME litteral. Detail : `docs/rl/case-462-r4b-r1-r1-r1-r1-b-r1-isadjacent-selection-type.md`.
  `IdunBattleLogic.Entities.Abilities.Active.Loki.BattleFatigueAbility$$CreateBehaviour = `Repeat(numTriggers, If(NOT HasFlag(self,9),
   Maybe(GetFleeChance, self) -> Flee(self,...)))`. `IdunBattleLogic.Entities.Abilities.Active.Loki.BattleFatigueAbility$$GetFleeChance = `ConditionalAmount(
   TargetIsOverkilled ? const 0x33 : const 0x2a)` — chances NON sourcables offline (config interne BC).
  `IdunBattle.Operations.FleeOperation$$Execute = deplace vers une tuile de fuite -> RecordFlee (stats/timelines) ->
   RemoveEffects (3 phases) -> **pose UnitFlag 9** (« a fui » : bloque la ré-action ; re-teste par le trigger)
   -> events.

GROUND TRUTH live (cf. project_instinctive_fatigue_carriers) : `BattleFatigue` est un **TRAIT** (gameconfig)
porte par les gaunts/grots/summons ; les grots invoques par SquigHound (Snotflogga) recoivent
`IgnoreBattleFatigue` (1079) -> immunises (confirme live). Sujets non-immunises spawnables :
genesSmnNeophyte / astraSmnGuardsman / orksOrkBoys / tyranSmnRipperSwarm.

PORTAGE : la CONDITION de trigger (deterministe) est portee+validable. Le `Maybe(fleeChance)` (RNG, chance
un-sourcable offline) est un GATE documente ; par defaut on FUIT quand eligible (pour exercer/valider
FleeOperation), et on ne tire la chance que si `state.battle_fatigue_flee_chance` est fournie (live-mesuree).
La DESTINATION de fuite (pathfinding natif) = approximee par la tuile atteignable maximisant la distance min
aux ennemis. Stats/timelines/remove-effects (non observables) = non portes.
"""
from __future__ import annotations

from typing import Optional

from ..abilities.behaviours.context import entities_from_state
from ..components import OwnerComponent, PositionComponent, UnitComponent, UnitFlagsComponent
from .triggers.base import TriggeredAbility, _hex_dist
from ...dsl.event_trigger_type import EventTriggerType
from ...entities.effect_type import EffectType
from ...entities.selectors.accessors import Target
from ...entities.selectors.tiles import Caster
from ...entities.triggered_ability_type import TriggeredAbilityType   # #955 : `TriggeringAbilityIs`
from ...entities.triggers import IsAdjacent, is_object_or_steppable
from ...entities.unit_selection_type import UnitSelectionType   # #524 : 3e arg d'`IsAdjacent`
from ...entities.pathfinding.walk_pathfinder import get_movable_positions
from .remove_unit import RemoveUnitOperation
from ...services.damage_combat import roll_critical
from ..events import EventBus
from .movement import MoveUnitOperation
from .triggers.dispatch import move_death

IGNORE_BATTLE_FATIGUE = int(EffectType.IgnoreBattleFatigue)  # 1079 (immunite ; posee p.ex. par SquigHound 1078) #158
# 3e argument d'`DSLTriggers$$IsAdjacent` = `UnitSelectionType`, PAS un rayon (cf. en-tete du module).
# #524 : l'ordinal ecrit a la main est remplace par le MEMBRE du mirror `IdunBattle.Entities.Enum.
# UnitSelectionType` (value-preserving : `IntEnum` EST un `int`, et `OnlyTargetable` vaut 2).
ONLY_TARGETABLE = UnitSelectionType.OnlyTargetable
_IS_ADJACENT = IsAdjacent(Caster(), Target(), ONLY_TARGETABLE)   # IsAdjacent(self@+0x30, dying@+0x60, 2)
# 5e conjoint : `NOT IsObjectOrSteppable(dying@+0x60)`. Foyer partage `entities/triggers.py`
# (mirror de `IdunBattleLogic.Entities.DSLTriggers$$IsObjectOrSteppable`, 8 call-sites natifs).
_IS_OBJECT_OR_STEPPABLE = is_object_or_steppable(Target())       # IsObjectOrSteppable(dying@+0x60)


class FleeOperation:
    """`IdunBattle.Operations.FleeOperation$$Execute (port STRUCTUREL de l'observable).

    L'unite FUIT : elle est RETIREE du plateau, puis porte le **UnitFlag 9** (`UnitFlagsComponent`,
    « a fui » -> bloque la ré-action ce tour). Les volets non observables (RecordFlee
    stats/timelines, RemoveEffects 3 phases) ne sont pas portes.

    #429-r1-r3-r1-r2 -- LE RETRAIT DU PLATEAU MANQUAIT, et c'est LU puis MESURE. Le decompile de
    `IdunBattle.Operations.FleeOperation$$Execute` enchaine, DANS CET ORDRE :

        OperationProcessor.RemoveUnit(unit, removeEffects: 0, param4: 1)   // slot 6
        state.AddToPools(unit, [1 = EntityPool.DefeatedUnits])             // slot 0x31
        UnitFlagsComponent.Add(unit, 9 = UnitFlag.Fled)

    Le slot **6** de `Core.Services.OperationProcessor` est celui de
    `Core.Services.OperationProcessor$$RemoveUnit` -> `IdunBattle.Operations.RemoveUnitOperation$$
    Execute` (unique appelant de code de cette Operation) ; `removeEffects = 0` parce que
    `FleeOperation` fait ses PROPRES `RemoveEffects` en trois phases juste apres.

    MESURE LIVE (2026-08-05, boards MC1_67 **et** C1_74, seed 777) : l'unite enfuie porte
    `unitFlags = [9, 26]` -- `Fled` **et `Removed` (0x1a)**, ce dernier n'ayant qu'UN poseur dans
    tout le binaire, `RemoveUnitOperation$$Execute` -- et `UnitExtensions$$IsAlive` rend FAUX sur
    elle a `hp = 1000/1000`. Le port ne posait que le flag 9 : son enfuie restait `alive = True`,
    donc VIVANTE pour `unit_extensions_is_alive` -- le mirror de la liveness native aurait ete
    correct mais INERTE en rollout offline."""
    __slots__ = ()

    @staticmethod
    def execute(state, unit_id: int, movement: int = 3,
                triggering_ability=None) -> Optional[dict]:
        e = state.get_entity(unit_id)
        if e is None:
            return None
        # #955 -- LES DEUX PREMIERS GESTES DU NATIF, ET ILS MANQUAIENT.
        # `IdunBattle.Operations.FleeOperation$$Execute` ouvre sur
        #     IOperationProcessor.<slot 81 = EvaluateAbilities>(unit, unit, unit, 0x33 = PreUnitFled,
        #                                                       triggeringAbilityOrEffect)
        #     if (UnitExtensions.IsDead(unit)) return;
        # -- c'est-a-dire que TOUT ce qui suit (retrait du plateau, `UnitFlag 9`, `On(0x34)`,
        # `On(0x36)`) est ABANDONNE si un trigger a tue l'unite pendant l'evenement. Le port
        # n'emettait AUCUN `PreUnitFled` : le vecteur n'avait aucun emetteur dans tout `engine/**`,
        # donc `SummaryExecutionAbility` n'aurait jamais pu se poser.
        pre = move_death.pre_unit_fled_triggers(state, int(unit_id),
                                                triggering_ability=triggering_ability)
        uc = e.get_component(UnitComponent)
        if uc is not None and not uc.alive:                    # `UnitExtensions$$IsDead(unit)`
            return {"fled": None, "pre_unit_fled": pre, "cancelled_by_death": int(unit_id)}
        # ORDRE NATIF : le retrait du plateau PRECEDE la pose du flag 9. Il pose `Removed` (0x1a),
        # sort l'unite de l'occupation (le collapse porte du pool `AliveUnits`) et publie
        # `On(0x25 = UnitRemoved)`. `remove_effects=False` = le `removeEffects: 0` du call-site.
        retrait = RemoveUnitOperation.execute(state, int(unit_id), remove_effects=False)
        fl = e.get_component(UnitFlagsComponent)
        if fl is None:
            fl = e.add_component(UnitFlagsComponent())
        fl.add(UnitFlagsComponent.FLED)                       # UnitFlag 9 = a fui
        to = FleeOperation._safest_tile(state, unit_id, movement)
        if to is not None:
            # `emit_after_move=False` : `IdunBattle.Operations.FleeOperation$$Execute` n'appelle NI
            # le slot `MoveUnit` NI `SetUnitPosition` -- son deplacement n'est PAS porte (la
            # destination ci-dessus est une approximation best-effort, cf. docstring). Jouer le
            # vecteur after-move ici FABRIQUERAIT un overwatch sur un mouvement inexistant cote
            # natif (#448-r1-r1-r2-r1, face inverse).
            # `enforce_native_gates=False` pour la MEME raison : les deux gates d'abandon
            # (`TilesAreEmpty`, `path` vide) vivent dans `MoveUnitOperation$$Execute`, que ce
            # call-site ne mirroite PAS. Les jouer inventerait un refus que le natif n'a pas.
            MoveUnitOperation(unit_id, to, emit_after_move=False,
                              enforce_native_gates=False).execute(state, EventBus())
        return {"fled": unit_id, "to": to, "flag": UnitFlagsComponent.FLED, "retrait": retrait,
                "pre_unit_fled": pre}

    @staticmethod
    def _safest_tile(state, unit_id: int, movement: int):
        """Tuile atteignable (<= movement) maximisant la distance min a tout ennemi VIVANT. Requiert
        `state.board` (evenq). None si pas de board / pas d'ennemi / aucune tuile."""
        board = state.board
        e = state.get_entity(unit_id)
        if board is None or e is None:
            return None
        oc = e.get_component(OwnerComponent)
        pc = e.get_component(PositionComponent)
        if oc is None or pc is None:
            return None
        occ: dict = {}
        enemies: list = []
        for eid, o in state.entities.items():
            u = o.get_component(UnitComponent)
            p = o.get_component(PositionComponent)
            c = o.get_component(OwnerComponent)
            if p is None:
                continue
            t = board.id_at(p.col, p.row)
            if t is None or (u is not None and not u.alive):
                continue
            occ[t] = eid
            if c is not None and c.team != oc.team:
                enemies.append(t)
        ot = board.id_at(pc.col, pc.row)
        occ.pop(ot, None)
        _, stop = get_movable_positions(board, ot, movement, occ, oc.team)
        if not stop or not enemies:
            return None

        def mind(t):
            return min(_hex_dist(board, t, et, 99) or 99 for et in enemies)

        best = max(stop, key=lambda t: (mind(t), -t))         # plus loin des ennemis (tie-break id bas)
        return board.coord(best)


class BattleFatigueAbility(TriggeredAbility):
    """Trait `BattleFatigue` (cf. en-tete module). Trigger MORT : une VRAIE UNITE ALLIEE **ADJACENTE**
    meurt et self n'est pas immunise (1079) -> eligible a la fuite. Behaviour = `FleeOperation` (gate
    `Maybe(fleeChance)` documente). Gate par le trait via `BEHAVIOUR_TRAIT_TRIGGERS` (mirror
    Psyker/FinalJustice/ActOfFaith).

    ⚠ « adjacent (<=2) » : cette docstring a porte ce `<=2` jusqu'au 2026-08-05, alors que l'en-tete
    du module le REFUTAIT deja (le `2` est un `UnitSelectionType`, #462-r4b-r1-r1-r1-r1-b-r1). Deux
    faces du meme accident : ici la docstring survivait au fix, plus bas c'est le CODE qui survivait
    a la docstring (`NOT IsObjectOrSteppable`, #462-r4b-r1-r1-r1-r1-b-r1-r1). Une docstring n'est pas
    une source -- l'en-tete cite les symboles, et c'est LUI qu'on relit.

    ORDRE DES CONJOINTS. Le natif enchaine `OnDeath` -> `IsAdjacent` -> `AreFriends` -> `NOT HasEffect`
    -> `NOT IsObjectOrSteppable` -> `OwnerActive`. `matches` evalue `AreFriends`/`HasEffect` AVANT
    l'adjacence (ils sont impératifs et bon marche) : l'ordre differe, le VERDICT non -- les six
    conjoints sont des predicats PURS, donc leur conjonction commute. Ce qui est preserve, c'est
    l'ordre RELATIF des deux noeuds DSL (`IsAdjacent` avant `IsObjectOrSteppable`)."""
    event_id = EventTriggerType.PreUnitDeath

    def matches(self, state, ev) -> bool:
        if ev.dying_id is None or ev.dying_id == self.owner_id:
            return False
        owner = state.get_entity(self.owner_id)
        dying = state.get_entity(ev.dying_id)
        if owner is None or dying is None:
            return False
        ouc = owner.get_component(UnitComponent)              # OwnerActive : self vivant
        if ouc is not None and not ouc.alive:
            return False
        oo = owner.get_component(OwnerComponent)
        do = dying.get_component(OwnerComponent)
        if oo is None or do is None or oo.team != do.team:    # AreFriends(dying, self)
            return False
        if (state.effects is not None and                    # NOT HasEffect(self, 1079)
                state.effects.has_effect(self.owner_id, effect_type=IGNORE_BATTLE_FATIGUE)):
            return False
        if state.board is None:
            return False
        # `IsAdjacent(self, dying, 2)` : ADJACENCE STRICTE (le `2` va au selecteur -- cf. en-tete du
        # module). Meme foyer que tout autre consommateur du noeud : empreintes completes, porte
        # d'elevation, court-circuit d'identite, quantificateur universel.
        entities = entities_from_state(state, self.owner_id, ev.dying_id)
        if not _IS_ADJACENT.should_trigger(entities):
            return False
        # `NOT IsObjectOrSteppable(dying@+0x60)` -- 5e conjoint, LU au decompile (cf. en-tete). Un
        # objet/decor/token qui meurt NE fatigue PERSONNE. Le meme `entities` sert les deux noeuds :
        # le construire est une boucle sur tout le state, et le natif n'evalue lui aussi qu'UN
        # `AbilityEntities` pour tout l'arbre.
        return not _IS_OBJECT_OR_STEPPABLE.should_trigger(entities)

    def execute_behaviour(self, state, ev) -> Optional[dict]:
        # Gate natif `Maybe(GetFleeChance)` (RNG, chance un-sourcable offline) : on ne tire que si une chance
        # ET un rng sont fournis ; sinon on FUIT (eligible) pour exercer/valider FleeOperation. `HasFlag(9)`
        # deja-fui : si l'unite a deja le flag, pas de re-fuite (NOT HasFlag(self,9) natif).
        owner = state.get_entity(self.owner_id)
        fl = owner.get_component(UnitFlagsComponent) if owner is not None else None
        if fl is not None and fl.has(UnitFlagsComponent.FLED):
            return {"trait": "BattleFatigue", "owner": self.owner_id, "dying": ev.dying_id,
                    "eligible": True, "flee": None, "note": "deja fui (flag 9)"}
        chance = getattr(state, "battle_fatigue_flee_chance", None)
        if chance is not None and state.rng is not None:
            if not roll_critical(state.rng, int(chance)):
                return {"trait": "BattleFatigue", "owner": self.owner_id, "dying": ev.dying_id,
                        "eligible": True, "flee": None, "note": "maybe-flee rate (no flee)"}
        # `triggering_ability` : le natif propage l'`AbilityOrEffect` COURANT du behaviour dans
        # `FleeOperation$$Execute`, et c'est celui-la que `SummaryExecutionAbility$$CreateTrigger`
        # compare (`TriggeringAbilityIs(0x401 = BattleFatigue)`). Ici l'ability courante EST
        # `BattleFatigue` -- ce foyer est le SEUL appelant porte de `FleeOperation.execute`.
        res = FleeOperation.execute(state, self.owner_id,
                                    triggering_ability=int(TriggeredAbilityType.BattleFatigue))
        return {"trait": "BattleFatigue", "owner": self.owner_id, "dying": ev.dying_id,
                "eligible": True, "flee": res}


# Registre trait -> trigger(s), fusionne LAZILY par `triggers.collect_triggered_abilities` (evite l'import
# circulaire behaviour<->triggers). Mirror de `TRAIT_TRIGGERS` pour les mecaniques de comportement.
BEHAVIOUR_TRAIT_TRIGGERS: dict[str, list[type[TriggeredAbility]]] = {
    "BattleFatigue": [BattleFatigueAbility],
}
