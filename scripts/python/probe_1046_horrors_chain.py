"""#1046 -- PROBE de mesure de la chaine des Horreurs Thousand Sons (`Split` 1156 ->
`FlamesOfMutation` 1160), OFFLINE INTEGRAL (State synthetique, aucun runner, aucun RPC).

Ce n'est PAS un test : il MESURE et IMPRIME (le cliquet, lui, est
`tests/engine/test_1046_horrors_chain_offline.py`). Sortie ASCII only (cp1252).

Usage :
    python probe_1046_horrors_chain.py            # les cinq mesures
"""
from __future__ import annotations

import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import hexgeo                                                                    # noqa: E402
from engine.entities.effects_state import EffectsState                           # noqa: E402
from engine.entities.pathfinding.board import Board                              # noqa: E402
from engine.entities.unit_context import UnitContext                             # noqa: E402
from engine.runner.components import (HealthComponent, OwnerComponent,           # noqa: E402
                                      PositionComponent, StatsComponent, UnitComponent)
from engine.runner.operations.triggers.dispatch.move_death import (              # noqa: E402
    pre_unit_death_2_triggers)
from engine.runner.prng import IntBasedMersenneTwister                           # noqa: E402
from engine.runner.state import State                                            # noqa: E402

COLS, ROWS = 5, 5
LEVEL, MULT = 50, 100
HP_MAX = 20000
PORTEUR, ENNEMI = 101, 102


def tid(col: int, row: int) -> int:
    return col * ROWS + row + 1


def dans_board(p) -> bool:
    return 0 <= p[0] < COLS and 0 <= p[1] < ROWS


def board(bloquees=()) -> Board:
    """Board plein `COLS x ROWS`. `bloquees` = positions rendues NON walkable (pour reduire le
    nombre de tuiles posables et mesurer le compte du `PickRandomly(..., 2)`)."""
    bloquees = set(bloquees)
    tiles = []
    for col in range(COLS):
        for row in range(ROWS):
            tiles.append({"id": tid(col, row), "col": col, "row": row,
                          "walkable": (col, row) not in bloquees,
                          "isWall": False, "isInFog": False, "elevation": 0,
                          "neighbours": [tid(c, r) for (c, r) in hexgeo.neighbors(col, row)
                                         if dans_board((c, r))]})
    return Board(tiles)


def Ctx(uid: int, visual_id, traits=(), passives=None, mult: int = MULT) -> UnitContext:
    """Le VRAI `UnitContext` (dataclass a defauts), pas un sosie : la chaine `Spawn` ->
    on-appearance -> `Scene.from_state` lit une dizaine de champs (`fixed_armor`, `stats`, ...) que
    la moindre classe ad hoc oublierait -- et un `AttributeError` la ferait passer pour un no-op."""
    return UnitContext(entity_id=int(uid), visual_id=visual_id, traits=list(traits),
                       passive_abilities=(list(passives) if passives is not None else None),
                       active_ability_level=LEVEL, passive_ability_level=LEVEL,
                       ability_variables_multiplier=int(mult), config_active_abilities=[])


def unite(st: State, uid: int, visual_id: str, *, team: int, pos, traits=(), passives=None,
          hp=HP_MAX, alive=True, mult: int = MULT) -> int:
    e = st.add_entity(uid)
    e.add_component(UnitComponent(visual_id, alive))
    e.add_component(OwnerComponent(team, team))
    e.add_component(HealthComponent(hp, HP_MAX))
    e.add_component(StatsComponent(ctx=Ctx(uid, visual_id, traits, passives, mult)))
    e.add_component(PositionComponent(int(pos[0]), int(pos[1])))
    return uid


def monter(visual_id: str, passif: str, *, traits=(), bloquees=(), owner_turn: bool = True,
           ennemi_adjacent: bool = False, seed: int = 777, pos=(2, 2), mult: int = MULT) -> State:
    """Un porteur du passif en `pos`, mort (`alive=False`, comme au dispatch de `On(2)`), sur un
    board plein. `owner_turn` pilote `IsTurnOf(Owner)` par `state.current_player_id`."""
    st = State()
    st.effects = EffectsState()
    st.rng = IntBasedMersenneTwister(seed)
    st.board = board(bloquees)
    unite(st, PORTEUR, visual_id, team=0, pos=pos, traits=traits, passives=[passif],
          alive=False, hp=0, mult=mult)
    if ennemi_adjacent:
        adj = [p for p in hexgeo.neighbors(pos[0], pos[1]) if dans_board(p)]
        unite(st, ENNEMI, "thousRubricMarine", team=1, pos=adj[-1])
    # `State.add_entity(<id explicite>)` ne fait PAS avancer `_next_entity_id` : sans ce recalage,
    # le `add_entity()` du spawn re-attribuerait 1 puis 2 et ECRASERAIT les deux unites du montage.
    # Artefact du montage synthetique, pas du port.
    st._next_entity_id = max(int(e) for e in st.entities) + 1
    st.current_player_id = 0 if owner_turn else 1
    # DEUX joueurs, comme un duel -- c'est le FACTEUR de `convert_rounds_to_turns`
    # (`IdunBattle.Core.Services.BattleQuery$$ConvertRoundsToTurns` = `nb joueurs x rounds`). Sans
    # lui le facteur retombe a 1 et la duree du Fire se lit `2` la ou le live rend `4` : l'ecart
    # serait un artefact du montage, pas du port (etage MESURE, pas devine).
    st.turn_order_player_count = 2
    return st


def nouvelles_unites(st: State, connues) -> list:
    return sorted(int(eid) for eid in st.entities if int(eid) not in connues)


def jouer(st: State, *, overkill: bool = False):
    """Emet `On(PreUnitDeath_2)` sur le porteur et rend `(payload, ids des unites neuves)`."""
    connues = set(int(e) for e in st.entities)
    out = pre_unit_death_2_triggers(st, PORTEUR, ENNEMI, overkill=overkill)
    return out, nouvelles_unites(st, connues)


def decrire(st: State, ids) -> None:
    for nid in ids:
        e = st.get_entity(nid)
        uc, pc = e.get_component(UnitComponent), e.get_component(PositionComponent)
        hc, oc = e.get_component(HealthComponent), e.get_component(OwnerComponent)
        print("      id=%s visual=%s pos=(%s,%s) hp=%s/%s team=%s parent=%s"
              % (nid, uc.visual_id, pc.col, pc.row, hc.hp, hc.hp_max, oc.team, uc.parent_id))


def effets(st: State) -> dict:
    """`{porteur: [(effect_type, remaining_turns, source), ...]}` -- les TROIS champs que le stream
    live donne (`ReceiveEffect e=<tuile> Effect_SourceId=<tuile> Effect_RemainingTurns=4`), donc les
    trois qui se confrontent. Un seul `effect_type` ne montrerait ni la duree ni la source."""
    return {int(k): sorted((int(e.effect_type), e.remaining_turns, e.source)
                           for e in v if not e.consumed)
            for k, v in st.effects.by_unit.items() if v}


def main() -> int:
    print("=== 1. Split MORD (tour de l'owner) ===")
    st = monter("thousSmnPinkHorror", "Split", ennemi_adjacent=True, owner_turn=True)
    out, neuves = jouer(st)
    print("    payload : %r" % (out,))
    print("    unites neuves : %r" % (neuves,))
    decrire(st, neuves)

    print("=== 2. Split -- gate OVERKILL (a=0 -> NOT TargetIsOverkilled) ===")
    st = monter("thousSmnPinkHorror", "Split", owner_turn=True)
    out, neuves = jouer(st, overkill=True)
    print("    payload : %r ; unites neuves : %r" % (out, neuves))

    print("=== 3. Split -- gate STEPPABLE (b=0 -> NOT HasTrait(Steppable)) ===")
    st = monter("thousSmnPinkHorror", "Split", traits=("Steppable",), owner_turn=True)
    out, neuves = jouer(st)
    print("    payload : %r ; unites neuves : %r" % (out, neuves))

    print("=== 4. Split -- HORS tour de l'owner (branche ELSE du If) ===")
    st = monter("thousSmnPinkHorror", "Split", ennemi_adjacent=True, owner_turn=False)
    out, neuves = jouer(st)
    print("    payload : %r ; unites neuves : %r" % (out, neuves))

    print("=== 5. Split -- UNE SEULE tuile posable (compte = min(2, libres)) ===")
    voisines = [p for p in hexgeo.neighbors(2, 2) if dans_board(p)]
    st = monter("thousSmnPinkHorror", "Split", owner_turn=True, bloquees=voisines[1:])
    out, neuves = jouer(st)
    print("    voisines bloquees : %r" % (voisines[1:],))
    print("    payload : %r ; unites neuves : %r" % (out, neuves))

    print("=== 6. FlamesOfMutation MORD (Fire sur SA main tile) ===")
    st = monter("thousSmnBlueHorror", "FlamesOfMutation", owner_turn=True)
    out, neuves = jouer(st)
    print("    payload : %r" % (out,))
    print("    main tile du porteur = %s" % (tid(2, 2),))
    print("    effets non consommes par entite : %r" % (effets(st),))

    print("=== 7. FlamesOfMutation -- gate OVERKILL ===")
    st = monter("thousSmnBlueHorror", "FlamesOfMutation", owner_turn=True)
    out, neuves = jouer(st, overkill=True)
    print("    payload : %r ; effets : %r" % (out, effets(st)))

    print("=== 8. LA CHAINE -- Pink meurt -> 2 Blue -> une Blue meurt -> sa tuile brule ===")
    st = monter("thousSmnPinkHorror", "Split", owner_turn=True)
    out, neuves = jouer(st)
    print("    etape 1 (Split) : neuves = %r" % (neuves,))
    for nid in neuves:
        ctx = st.get_entity(nid).get_component(StatsComponent).ctx
        print("      id=%s passives montees = %r" % (nid, list(getattr(ctx, "passive_abilities", None)
                                                               or [])))
    cible = neuves[0]
    uc = st.get_entity(cible).get_component(UnitComponent)
    uc.alive = False
    st.get_entity(cible).get_component(HealthComponent).hp = 0
    out2 = pre_unit_death_2_triggers(st, cible, ENNEMI, overkill=False)
    pc = st.get_entity(cible).get_component(PositionComponent)
    print("    etape 2 (FlamesOfMutation sur %s en (%s,%s), main tile %s) : %r"
          % (cible, pc.col, pc.row, tid(pc.col, pc.row), out2))
    print("    effets non consommes : %r" % (effets(st),))

    print("=== 9. STATS des Blue Horrors sous mult 180 (le regime du runner normalise) ===")
    st = monter("thousSmnPinkHorror", "Split", owner_turn=True, mult=180)
    out, neuves = jouer(st)
    decrire(st, neuves)
    print("    attendu live : hp 2093 / attack 1795  (summonHp[49]=1163 x180%%, summonDmg[49]=997 x180%%)")
    for nid in neuves:
        ctx = st.get_entity(nid).get_component(StatsComponent).ctx
        print("      id=%s attack=%s health=%s" % (nid, ctx.attack, ctx.health))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
