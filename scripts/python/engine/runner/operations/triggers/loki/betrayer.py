"""`Abilities.Triggered.Loki.TheBetrayer_AddEffectAbility` (IdunBattleLogic.Entities.Abilities.Triggered.Loki.TheBetrayer_AddEffectAbility$$CreateTrigger) + `TheBetrayer_TakeTurnAbility`
(IdunBattleLogic.Entities.Abilities.Triggered.Loki.TheBetrayer_TakeTurnAbility$$CreateTrigger) — rage de TheBetrayer (worldKharn) : GAIN au kill (0x4f3) et AUTO-TOUR force au debut de tour
tant que la rage est active. Cf. `loki/__init__.py` pour le regroupement « Loki »."""
from __future__ import annotations

from typing import Optional

from ....state import State
from ....components import OwnerComponent, UnitComponent
from ....abilities.behaviours import AttackWithAttackDamage, MoveUnit, AddEffect, entities_from_state
from .....entities.effect_type import EffectType
from .....entities.selectors import Caster, Target, FixedTiles
from .....entities.behaviours import Seq, If, Inform, Emit
from .....entities.triggers import IsAdjacent, Not
from .....entities.pathfinding.walk_pathfinder import get_movable_positions
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from ..base import TriggeredAbility, TriggerEvent, _unit_tile, _hex_dist

THEBETRAYER_EFFECT = int(EffectType.TheBetrayer)  # 1267 — effet « rage » de TheBetrayer (gate de TakeTurn ; gagné au kill).
THEBETRAYER_RANGE = 2           # `TheBetrayer.variables.range` = 2 (GetVariableForLevel(0x53)) — move max.
THEBETRAYER_PROFILE = "Eviscerate"  # `TheBetrayer.constants.damageProfile` (attaque 4 coups Eviscerate).


def betrayer_add_effect_tree(effect_type: int):
    """Arbre de `IdunBattleLogic.Entities.Abilities.Triggered.Loki.TheBetrayer_AddEffectAbility$$CreateBehaviour` (MIRROR 1:1 du DECOMPILE) :
        AddEffect( effectType = 0x4f3, source = AbilityStateReference, target = Self@0x148 )
    Port : `AddEffect(THEBETRAYER_EFFECT, "TheBetrayer_Effect", Caster())` (Owner==Caster pour un triggered).
    La feuille route vers `AddEffectOperation.execute(target=caster, 0x4f3, "TheBetrayer_Effect")`.

    ⚠ DUREE : le port pose 1 TOUR, **valeur historique GELEE, pas un mirror** (cf. le commentaire du
    `return` ci-dessous). L'ancienne justification (« `local_588[0] = 1` est la duree quand l'override
    Nullable est null ») est REFUTEE : `local_588[0]` est le **NIVEAU** (`EffectComponent.Level @+0x68`,
    prouve par `IdunBattle.Operations.IncreaseEffectLevelOperation$$Execute`) ; la duree, elle, vaut 0 = PERMANENT
    quand ni override ni `DefaultAmountOfRounds` n'existent. `effect_type` passe par l'appelant
    (constante `THEBETRAYER_EFFECT`)."""
    # #98 -- RESIDU EXPLICITE (comportement HISTORIQUE GELE, pas un mirror). Le decompile IdunBattleLogic.Entities.Abilities.Triggered.Loki.TheBetrayer_AddEffectAbility$$CreateBehaviour
    # passe `AddEffect(factory, 0x4f3, stateRef, self@0x148, self@0x148, &optionsZEROEES, 0)` : le slot
    # duree est une struct ZERO -> duree PAR DEFAUT, et `DefaultAmountOfRounds(0x4f3=1267)` est ABSENT
    # du switch idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Effect$$DefaultAmountOfRounds -> le natif pose donc un effet **PERMANENT**. Le port garde 1 TOUR
    # (`duration_turns=1`, valeur historique) parce qu'AUCUN vecteur de RETRAIT de 0x4f3 n'est identifie
    # (ni `IdunBattleLogic.Entities.Abilities.Triggered.Loki.TheBetrayer_TakeTurnAbility$$CreateBehaviour`, ni les autres membres du kit) : passer
    # en permanent ferait rejouer Kharn a CHAQUE tour indefiniment -- regression fonctionnelle non mesuree.
    # A instruire separement (trouver le RemoveEffect(0x4f3) natif ou mesurer live le cycle de la rage).
    return AddEffect(effect_type, "TheBetrayer_Effect", Caster(), duration_turns=1)


def _add_betrayer_effect(state: State, owner_id: int) -> Optional[dict]:
    """`TheBetrayer_AddEffectAbility` behaviour = arbre DSL `betrayer_add_effect_tree()` (mirror
    `AddEffect(0x4f3, Self)` IdunBattleLogic.Entities.Abilities.Triggered.Loki.TheBetrayer_AddEffectAbility$$CreateBehaviour) : le porteur (Kharn) gagne le marqueur de rage 0x4f3 (aucune
    StatModification, juste la presence qui gate TakeTurn), DUREE 1 tour (RE IdunBattle.Operations.AddEffectOperation$$Execute, cf. tree ; re-accorde
    a chaque kill). No-op si `state.effects` absent. Le gate `matches` (OnDeath & killer==owner & NOT
    HasEffect(0x4f3)) reste upstream (hors CreateBehaviour)."""
    if state.effects is None:
        return None
    ectx = ExecutionContext(state=state)
    betrayer_add_effect_tree(THEBETRAYER_EFFECT).execute(
        entities_from_state(state, owner_id, None), ectx)
    placed = any(p.get("placed") for n, p in ectx.emitted if n == "AddEffect")
    return {"ability": "TheBetrayer", "owner": owner_id,
            "effect": "added 0x4f3" if placed else "already present"}


def _betrayer_target(state: State, owner_id: int) -> Optional[int]:
    """`IdunBattleLogic.Entities.Abilities.Triggered.Loki.TheBetrayer_TakeTurnAbility$$GetAttackTarget : priorité `ForcedAttackTargets > ennemi-le-plus-proche-en-portée >
    allié-en-portée > ennemi-le-plus-proche > allié`. (ForcedAttackTargets + filtre `NOT HasTrait(0xd)`
    non portés : aucun candidat concret dans le roster validé — approximation documentée.) « En portée »
    = atteignable+frappable ce tour (hex <= `range`=2 + portée mêlée 1). « Le plus proche » = min distance
    hex (tie-break id croissant)."""
    board = state.board
    owner = state.get_entity(owner_id)
    if board is None or owner is None:
        return None
    ot = _unit_tile(state, board, owner_id)
    oc = owner.get_component(OwnerComponent)
    if ot is None or oc is None:
        return None
    reach = THEBETRAYER_RANGE + 1
    enemies: list[tuple[int, int]] = []
    friends: list[tuple[int, int]] = []
    for eid, e in state.entities.items():
        if eid == owner_id:
            continue
        c = e.get_component(OwnerComponent)
        u = e.get_component(UnitComponent)
        if c is None or (u is not None and not u.alive):
            continue
        t = _unit_tile(state, board, eid)
        if t is None:
            continue
        d = _hex_dist(board, ot, t, 99)
        if d is None:
            continue
        (friends if c.team == oc.team else enemies).append((d, eid))

    def nearest(cands: list[tuple[int, int]], within: Optional[int] = None) -> Optional[int]:
        pool = [(d, i) for (d, i) in cands if within is None or d <= within]
        if not pool:
            return None
        pool.sort()                                   # min distance, puis min id (déterministe)
        return pool[0][1]

    return (nearest(enemies, reach) or nearest(friends, reach)
            or nearest(enemies) or nearest(friends))


def _betrayer_stop_tile(state: State, owner_id: int, target_id: int) -> Optional[tuple]:
    """COLLAPSE (kind S) du sélecteur de destination du move natif IdunBattleLogic.Entities.Abilities.Triggered.Loki.TheBetrayer_TakeTurnAbility$$CreateBehaviour `First(SortByFormula(
    SortTilesByUtility((AdjacentTiles(target) & movable).Otherwise(movable)), MinPathLength))` : la tuile
    d'arrêt (atteignable ≤ `range`=2) ADJACENTE à la cible et la plus proche d'elle, sinon (`Otherwise`) la
    movable la plus proche. Renvoie (col,row) ou None si rien d'atteignable. Pathfinding LOURD calculé
    IMPÉRATIVEMENT hors DSL (doctrine slice-18/19) -> injecté ensuite dans la feuille `MoveUnit` via
    `FixedTiles`. (`SortTilesByUtility` = pré-tri d'utilité de tuile non porté -> `MinPathLength` départagé
    par id.)

    RÉSIDU `#381-r4`, PARTAGÉ par tous les collapses impératifs de `MovableTilesInRange` (celui-ci,
    `abilities/genestealer._charge_candidate_tiles`, `triggers/genestealer._hypersensory_move_dest`) :
    ce `get_movable_positions` n'applique NI le gate d'expansion #131
    (`BasePathfinder$$NodesInNextLevel` -> `IsValidContinuePathTile`) NI le dispatch
    `MovementQuery$$GetPathfinderTypeForUnit` (`IsLikeFlying`). Il SUR-ATTEINT donc sur un board à
    tuiles block-entering. Le nœud DSL homonyme, lui, les porte depuis `#381-r1` — c'est le même
    correctif à recopier ici, avec le re-jeu des tests live de chaque ability concernée."""
    board = state.board
    owner = state.get_entity(owner_id)
    if board is None or owner is None:
        return None
    oc = owner.get_component(OwnerComponent)
    ot = _unit_tile(state, board, owner_id)
    tt = _unit_tile(state, board, target_id)
    if oc is None or ot is None or tt is None:
        return None
    occupants: dict = {}
    for eid, e in state.entities.items():
        u = e.get_component(UnitComponent)
        if u is not None and not u.alive:
            continue
        t = _unit_tile(state, board, eid)
        if t is not None:
            occupants[t] = eid
    _, stop = get_movable_positions(board, ot, THEBETRAYER_RANGE, occupants, oc.team)
    t_neigh = set(board.neighbours(tt))
    cands = [t for t in stop if t in t_neigh] or list(stop)
    if not cands:
        return None
    cands.sort(key=lambda t: (_hex_dist(board, t, tt, 99) or 99, t))   # MinPathLength, puis id (tie-break)
    return board.coord(cands[0])                                       # (col, row)


def _betrayer_take_turn(state: State, owner_id: int) -> Optional[dict]:
    """Behaviour TheBetrayer (`IdunBattleLogic.Entities.Abilities.Triggered.Loki.TheBetrayer_TakeTurnAbility$$CreateBehaviour`) — replié en UN ARBRE DSL UNIFIÉ (S-chantier
    Voie A). La composition STRUCTURELLE est désormais des NŒUDS DSL, plus du contrôle impératif :

        If( AmountIsGreaterThanZero(target),                        # <- gate S collapse (voir plus bas)
            Inform(0xbf)
            & If( NOT IsAdjacent(Caster, Target), MoveUnit(Caster, bestTile, options=NULL) )
            & If(     IsAdjacent(Caster, Target), GetDamageBehaviour(Target) ) )

    L'arbre partage UN SEUL contexte `entities_from_state` dont les unités sont des `LiveUnit` (Slice A1) :
    caster/target relisent leur position du `state` À CHAQUE éval. Donc le MÊME nœud `is_adj =
    IsAdjacent(Caster(), Target())` (réutilisé sous `Not` pour le move-gate ET en direct pour l'attack-gate,
    == le natif `uVar4`) rend deux verdicts DIVERGENTS à travers le move : `Seq`/`&` exécute le move
    (mutation) AVANT que l'attack-gate re-teste l'adjacence POST-move. C'est la re-éval LIVE native, sans
    plus aucun `_is_adjacent_units` impératif (cf. docs/rl/dsl-live-context-substrate.md).

    Frontière déclaratif/impératif (doctrine slice-18/19) — les SÉLECTEURS S lourds restent COLLAPSÉS,
    fournis à l'arbre comme valeurs concrètes ; SEULE la composition E + les prédicats d'adjacence sont en
    nœuds :
    - `target` = `Cache(GetAttackTarget(AdjacentTiles(MovableTilesInRange(caster, range))))` -> COLLAPSE
      `_betrayer_target` (S), fourni comme `Target()` via `entities_from_state(..., target)`.
    - `AmountIsGreaterThanZero(target)` = cardinalité de la cible-sélection = PARTIE de la sélection S
      collapsée (`_betrayer_target` -> None = liste vide) -> reste le gate impératif `if target is None`
      (la folder en `Count(Target())` exigerait d'un-collapser la cible en LISTE, contre la doctrine).
    - `bestTile` = `First(SortByFormula(SortTilesByUtility(...), MinPathLength))` -> COLLAPSE
      `_betrayer_stop_tile` (S pathfinding), injecté via `FixedTiles([bestTile])` (calculé une fois au cast,
      == le bestTile natif). Non utilisé si déjà adjacent (move gated off).
    - `NOT IsAdjacent` / `IsAdjacent` (seuil dist-1) = nœuds `Not(is_adj)` / `is_adj` (LIVE via LiveUnit).
    - `MoveUnit` options NULLES (`local_a8..local_78` zéro IdunBattleLogic.Entities.Abilities.Triggered.Loki.TheBetrayer_TakeTurnAbility$$CreateBehaviour, == ThunderousAssault) -> feuille
      `MoveUnit` plaine (fidèle) ; `ExecutionContext` sans bus = `EventBus()` jetable (== l'impératif).
    - `IdunBattleLogic.Entities.Abilities.Triggered.Loki.ATheBetrayerAbility$$GetDamageBehaviour` = `AttackWithAttackDamage(Self, target, MinMaxDamage,
      GetDamageProfileOrDefault(0x19)=Eviscerate, GetHits)` -> feuille `AttackWithAttackDamage(Target(),
      "TheBetrayer", "Eviscerate", melee)` (BIT-EXACT : mêmes `ability_attack_params` + `execute_ability_attack`).
    - `Inform(0xbf)` = notif AI/UI = NO-OP observable (feuille `Inform`).

    FIDÉLITÉ after-move overwatch (#149, task #4 RÉSOLU par RE IdunBattle.Operations.MoveUnitOperation$$EvaluateAfterMoveTriggers) : l'`Emit("BetrayerAfterMove")`
    appelle `after_move_triggers` (overwatch sur le move forcé, ssi le move est effectif) — c'est FIDÈLE au
    natif, PAS un over-trigger. `IdunBattle.Operations.MoveUnitOperation$$EvaluateAfterMoveTriggers` émet `On(4)`
    (after-move / overwatch) gaté par `if (param_6 != 0) return`, où `param_6` = options[4] du nœud `MoveUnit`
    (behaviour +0x80) = flag SUPPRESS (défaut 0 = overwatch ACTIF). Options NULLES (Kharn == ThunderousAssault)
    => param_6=0 => `On(4)` ÉMIS. Émission UNIQUE : la feuille `MoveUnit` appelle `MoveUnitOperation.execute`
    (position seule ; INCRÉMENT 1b `EvaluateAfterMoveTriggers` NON replié dans l'Operation) -> l'`Emit` explicite
    est le SEUL vecteur after-move de ce move DSL (pas de double). ⚠ Si INCRÉMENT 1b replie un jour
    `EvaluateAfterMoveTriggers` DANS `MoveUnitOperation.execute`, RETIRER cet `Emit` (sinon double-émission).
    No-op si pas de cible / board."""
    from ..dispatch import after_move_triggers            # lazy : évite le cycle loki<->dispatch

    target = _betrayer_target(state, owner_id)                      # collapse GetAttackTarget (S)
    if target is None:                                             # AmountIsGreaterThanZero(target) = gate S
        return {"ability": "TheBetrayer", "owner": owner_id, "target": None}
    stop = _betrayer_stop_tile(state, owner_id, target)            # collapse bestTile (S pathfinding), une fois

    is_adj = IsAdjacent(Caster(), Target())                        # UN nœud réutilisé (== natif uVar4)

    def _after_move_fn(entities, ectx):
        mv = next((p for (n, p) in ectx.emitted if n == "MoveUnit"), None)
        if mv is not None and mv.get("moved"):                     # after-move SSI move effectif (== impératif)
            return {"result": after_move_triggers(ectx.state, owner_id)}
        return {}

    # FIDÈLE au natif (task #4 RÉSOLU, RE IdunBattle.Operations.MoveUnitOperation$$EvaluateAfterMoveTriggers) : `Emit` AfterMove = l'after-move overwatch du move
    # forcé, émis par `EvaluateAfterMoveTriggers` pour TOUT move (options nulles = flag SUPPRESS param_6=0 =
    # overwatch actif ; Kharn == ThunderousAssault). Émission UNIQUE (feuille `MoveUnit` -> Operation
    # position-seule) ; encapsulé DANS la branche move, ordonné move -> after_move -> attaque.
    move_branch = Seq(MoveUnit(Caster(), FixedTiles([stop] if stop is not None else [])),
                      Emit("BetrayerAfterMove", _after_move_fn))

    # ARBRE UNIFIÉ (mirror IdunBattleLogic.Entities.Abilities.Triggered.Loki.TheBetrayer_TakeTurnAbility$$CreateBehaviour) : Inform & If(NOT is_adj, Move) & If(is_adj, Attack). Contexte LIVE
    # partagé -> re-éval de `is_adj` post-move (Voie A). `Seq` = `CombinedBehaviour` court-circuit gauche->droite.
    tree = Seq(Inform(0xbf),
               Seq(If(Not(is_adj), move_branch),
                   If(is_adj, AttackWithAttackDamage(Target(), "TheBetrayer", THEBETRAYER_PROFILE,
                                                     is_melee=True))))

    ectx = ExecutionContext(state=state, rng=state.rng)            # bus = EventBus() jetable (== impératif)
    tree.execute(entities_from_state(state, owner_id, target), ectx)

    mv = next((p for (n, p) in ectx.emitted if n == "MoveUnit"), None)
    moved = None
    if mv is not None and mv.get("moved"):
        am = next((p for (n, p) in ectx.emitted if n == "BetrayerAfterMove"), {})
        moved = {"to": mv.get("to"), "after_move": am.get("result")}
    atk = next((p for (n, p) in ectx.emitted if n == "AttackWithAttackDamage"), {}).get("attack")

    return {"ability": "TheBetrayer", "owner": owner_id, "target": target,
            "moved": moved, "attack": atk}


class TheBetrayerAddEffectAbility(TriggeredAbility):
    """`TheBetrayer_AddEffectAbility` (IdunBattleLogic.Entities.Abilities.Triggered.Loki.TheBetrayer_AddEffectAbility$$CreateTrigger CreateTrigger / IdunBattleLogic.Entities.Abilities.Triggered.Loki.TheBetrayer_AddEffectAbility$$CreateBehaviour CreateBehaviour) — GAIN de la
    rage TheBetrayer (0x4f3) quand le porteur TUE.

    CreateTrigger = `OnDeath(1) & OwnerIsActor & NOT HasEffect(owner,0x4f3)` — l'owner (Kharn) est l'ACTEUR
    de la mort (= le tueur, slot 0x158=killer) et n'a pas déjà la rage. Behaviour = `AddEffect(0x4f3)` sur
    lui-même. ⇒ après que Kharn tue une unité, il gagne la rage qui déclenche son auto-tour (cf. TakeTurn).
    Vérité-terrain : pas d'auto-action AVANT le 1er kill (0x4f3 absent), auto-action APRÈS (cf. recon)."""
    event_id = EventTriggerType.PreUnitDeath

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        if ev.killer_id != self.owner_id:                        # OwnerIsActor (= killer)
            return False
        if state.effects is not None and state.effects.has_effect(  # NOT HasEffect(owner, 0x4f3)
                self.owner_id, effect_type=THEBETRAYER_EFFECT):
            return False
        return True

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        return _add_betrayer_effect(state, self.owner_id)


class TheBetrayerTakeTurnAbility(TriggeredAbility):
    """`TheBetrayer_TakeTurnAbility` (IdunBattleLogic.Entities.Abilities.Triggered.Loki.TheBetrayer_TakeTurnAbility$$CreateTrigger CreateTrigger / IdunBattleLogic.Entities.Abilities.Triggered.Loki.TheBetrayer_TakeTurnAbility$$CreateBehaviour CreateBehaviour) — AUTO-TOUR
    forcé de TheBetrayer (worldKharn) au DÉBUT DE TOUR.

    CreateTrigger = `On(0x16 turn-start) & <OwnerActive @+0xa0> & HasEffect(owner,0x4f3)` — au début du
    tour du player de l'owner, si l'owner a la rage. Behaviour IdunBattleLogic.Entities.Abilities.Triggered.Loki.TheBetrayer_TakeTurnAbility$$CreateBehaviour = choisit la meilleure cible
    (`GetAttackTarget` : ennemi le plus proche atteignable préféré, sinon allié), se DÉPLACE vers elle
    (≤ `range`=2, meilleure tuile adjacente par MinPathLength), puis l'ATTAQUE si adjacent (4 coups
    Eviscerate, `GetDamageBehaviour`). ⇒ Kharn « charge et frappe » l'unité la plus proche, amie ou
    ennemie, à chaque début de tour tant qu'il a la rage."""
    event_id = EventTriggerType.TurnStart_Actions

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        owner = state.get_entity(self.owner_id)
        if owner is None:
            return False
        oc = owner.get_component(OwnerComponent)
        if oc is None or oc.player != ev.player_id:              # OwnerActive : tour du player de l'owner
            return False
        if state.effects is None or not state.effects.has_effect(  # HasEffect(owner, 0x4f3)
                self.owner_id, effect_type=THEBETRAYER_EFFECT):
            return False
        return True

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        return _betrayer_take_turn(state, self.owner_id)
