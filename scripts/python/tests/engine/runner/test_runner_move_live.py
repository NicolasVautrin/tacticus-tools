"""Tranche 1 (MOVE) — replay-diff CONFRONTÉ au LIVE.

On rejoue LE MÊME move sur le runner live (applyAction) ET sur le runner Python
(load_state(before) → apply(MoveUnitMessage)), puis on diffe l'état.

Le move choisi rapproche au max une unité de l'ennemi → déclenche un OVERWATCH
(vérité-terrain : Maugan Ra tire ~1174 sur le mover, cf. _probe_overwatch.py).

INCRÉMENT 1a (porté ici) : la POSITION finale du mover. On VALIDE qu'elle est exacte
ET qu'aucun changement STRUCTUREL parasite (team/alive/currentPlayer/autres positions)
n'apparaît. Le résidu hp/effets (cascade OVERWATCH + effets de téléport du mover) =
INCRÉMENT 1b, documenté ici (gap attendu), pas encore reproduit.

Property-based, indépendant version/seed. Skip si pas de session.
"""
from __future__ import annotations

import pytest

from engine.runner.snapshot import load_state, snapshot, snapshot_live, diff
from engine.runner.messages import MoveUnitMessage
from engine.runner.runner import Runner


def _cheby(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


@pytest.fixture(scope="session")
def move_replay(rpc, build_runner):
    """Rejoue un move (rapprochement max → overwatch) sur live + Python."""
    rid = build_runner("777")["rid"]

    def views():
        dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        ob = rpc("observeBattle", {"runnerId": rid}, 40)
        return dv, ob

    dv0, ob0 = views()
    if not (dv0.get("units")):
        pytest.skip("decisionView vide")
    cur = dv0.get("currentPlayer")
    my_team = next((u.get("team") for u in dv0["units"] if u.get("owner") == cur), None)
    enemies = [(u["pos"]["col"], u["pos"]["row"]) for u in dv0["units"]
               if u.get("team") != my_team and u.get("alive") and u.get("pos")]
    mov = rpc("aiMovableTiles", {"runnerId": rid}, 60)
    best = None  # (dist, mover, tile)
    for mu in (mov.get("units") or []):
        uid = mu.get("unitId")
        u0 = next((u for u in dv0["units"] if u.get("id") == uid), None)
        if not u0 or u0.get("team") != my_team:
            continue
        for t in (mu.get("tiles") or []):
            if t.get("col") is None:
                continue
            tile = (t["col"], t["row"])
            d = min((_cheby(tile, e) for e in enemies), default=99)
            if best is None or d < best[0]:
                best = (d, uid, tile)
    if best is None:
        pytest.skip("aucun move dispo pour la team courante")
    _, mover, tile = best

    # APPLY live
    rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": mover, "to": {"col": tile[0], "row": tile[1]}}}, 40)
    dv1, ob1 = views()

    # APPLY Python (depuis l'état d'avant)
    runner = Runner(load_state(dv0, ob0)).install_default_handlers()
    runner.apply(MoveUnitMessage(mover, tile))

    return {
        "mover": mover, "tile": list(tile),
        "before": snapshot_live(dv0, ob0),
        "live_after": snapshot_live(dv1, ob1),
        "py_after": snapshot(runner.state),
    }


def test_move_reproduces_mover_position(move_replay):
    """1a : la position finale du mover (Python) == live == tile cible."""
    m = move_replay
    py = m["py_after"]["units"][m["mover"]]
    live = m["live_after"]["units"][m["mover"]]
    assert py["pos"] == m["tile"], f"Python mover pos {py['pos']} != tile {m['tile']}"
    assert live["pos"] == m["tile"], f"live mover pos {live['pos']} != tile {m['tile']}"


def test_move_no_spurious_structural_change(move_replay):
    """1a : aucun changement structurel parasite — toutes les positions, teams, alive
    et currentPlayer concordent live vs Python. Le seul résidu autorisé = hp/effets
    (cascade overwatch + effets de téléport, incrément 1b)."""
    m = move_replay
    d = diff(m["live_after"], m["py_after"])
    structural = [x for x in d if not (".hp:" in x or ".effects:" in x)]
    assert not structural, "changements structurels inattendus:\n  " + "\n  ".join(structural)


def test_overwatch_fired_live_is_the_pending_increment(move_replay):
    """1b (documenté) : le move a bien déclenché un OVERWATCH côté LIVE (le mover a
    perdu des PV), que le runner Python NE reproduit PAS encore → gap attendu de la
    cascade after-move. Garantit que le scénario reste valide (overwatch déclenché)."""
    m = move_replay
    mv = m["mover"]
    hp_before = m["before"]["units"][mv]["hp"]
    hp_live = m["live_after"]["units"][mv]["hp"]
    hp_py = m["py_after"]["units"][mv]["hp"]
    if hp_before is None or hp_live is None or hp_live >= hp_before:
        pytest.skip("pas d'overwatch déclenché sur ce move (géométrie) — scénario non couvert")
    # L'overwatch (vecteur after-move) EST porté + validé bit-exact dans `test_overwatch_live.py`. Ce
    # fixture-ci seed l'état SANS combatSnapshot/dumpRng/board (load_state(dv,ob) seul) → pas de stats,
    # pas de RNG, pas d'adjacence hex → le vecteur after-move reste no-op ICI (dégradation fidèle). D'où
    # le gap attendu sur CE chemin ; la repro bit-exact est couverte par le test dédié.
    assert hp_py == hp_before, "sans snapshot/rng/board, le move-replay ne reproduit pas l'overwatch"
    pytest.xfail(f"overwatch porté+validé ailleurs (test_overwatch_live) ; ce fixture ne seed pas "
                 f"stats/rng/board → no-op. live Δhp={hp_live - hp_before} ({hp_before}->{hp_live})")
