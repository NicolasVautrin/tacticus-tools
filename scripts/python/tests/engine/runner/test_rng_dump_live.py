"""RNG — DUMP natif (`dumpRng`) CONFRONTÉ au MT Python, bit-exact.

`dumpRng` lit l'état MT19937 du runner natif (runner@0x38, RE IdunRunner.Initialize).
Validation : on dump l'état AVANT un coup consommant du RNG (move au contact →
overwatch), on applique le coup, on re-dump APRÈS ; puis on fait AVANCER le MT Python
(engine/runner/prng) depuis l'état-AVANT jusqu'à retrouver EXACTEMENT (mt[]+mti)
l'état-APRÈS. S'il y parvient en k tirages, le dump ET le port MT reproduisent le RNG
du binaire LIVE, bit-pour-bit — base de la reproduction exacte de l'overwatch (1b).

Skip si pas de session / dumpRng indispo. cf. conftest.
"""
from __future__ import annotations

import pytest

from engine.runner.prng import IntBasedMersenneTwister


def _cheby(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


@pytest.fixture(scope="session")
def rng_replay(rpc, build_runner):
    rid = build_runner("777")["rid"]
    s1 = rpc("dumpRng", {"runnerId": rid}, 30)
    if not (isinstance(s1, dict) and s1.get("ok")):
        pytest.skip(f"dumpRng indispo (rebuild+reinject hooks ?): {str(s1)[:200]}")

    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1}, 90)
    cur = dv.get("currentPlayer")
    my_team = next((u.get("team") for u in (dv.get("units") or []) if u.get("owner") == cur), None)
    enemies = [(u["pos"]["col"], u["pos"]["row"]) for u in (dv.get("units") or [])
               if u.get("team") != my_team and u.get("alive") and u.get("pos")]
    mov = rpc("aiMovableTiles", {"runnerId": rid}, 60)
    best = None
    for mu in (mov.get("units") or []):
        uid = mu.get("unitId")
        u0 = next((u for u in (dv.get("units") or []) if u.get("id") == uid), None)
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
        pytest.skip("aucun move pour consommer du RNG")
    _, mover, tile = best
    rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": mover, "to": {"col": tile[0], "row": tile[1]}}}, 40)
    s2 = rpc("dumpRng", {"runnerId": rid}, 30)
    if not (isinstance(s2, dict) and s2.get("ok")):
        pytest.skip(f"dumpRng #2 KO: {str(s2)[:200]}")
    return s1, s2


def test_dump_is_a_valid_mt_state(rng_replay):
    """Garde-fou : l'état dumpé ressemble à un MT19937 (624 mots, mti plausible,
    pas tout-zéro)."""
    s1, _ = rng_replay
    assert len(s1["mt"]) == 624
    assert 0 <= s1["mti"] <= 624
    assert any(x != 0 for x in s1["mt"]), "mt tout-zéro = état non initialisé"


def test_python_mt_reproduces_live_consumption(rng_replay):
    """Cœur : le MT Python, parti de l'état-AVANT, retrouve EXACTEMENT l'état-APRÈS
    en avançant de k tirages → bit-exact vs RNG live."""
    s1, s2 = rng_replay
    mt = IntBasedMersenneTwister()
    mt.mt = list(s1["mt"])
    mt.mti = s1["mti"]
    target_mt = list(s2["mt"])
    target_mti = s2["mti"]
    if mt.mti == target_mti and mt.mt == target_mt:
        return                                   # 0 consommation (dump stable)
    for k in range(1, 5000):
        mt.genrand_int32()
        if mt.mti == target_mti and mt.mt == target_mt:
            return                               # reproduit l'état live après k tirages
    pytest.fail(
        f"MT Python n'a pas rejoint l'état live en <5000 tirages "
        f"(mti {s1['mti']}->{s2['mti']}, callCount {s1['callCount']}->{s2['callCount']})")
