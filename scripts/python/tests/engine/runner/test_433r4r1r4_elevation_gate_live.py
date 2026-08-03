"""#433-r4-r1-r4 -- la porte d'elevation `|dElev| < 2`, CONFRONTEE AU NATIF sur un board a relief.

Deux oracles INDEPENDANTS, sur `MC1_67` (5 niveaux d'elevation) :

(A) **La porte elle-meme, lue sur la liste d'adjacence NATIVE.** Le `boardGraph` est capte par
    `IdunBattle.Core.Services.BattleQuery$$GetAdjacentTiles` ->
    `IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext`, donc la
    liste rendue a DEJA traverse la porte. Les aretes de la couronne hex ABSENTES de cette liste
    doivent donc etre EXACTEMENT celles a `|dElev| >= 2`. C'est le SENS PERMISSIF du gate : ces
    voisins-la, le natif ne les ITERE PAS, donc `GetAdjacentUnits(tile, ..., enemyOf, false).Count`
    ne les compte pas -- exactement ce dont depend le PREMIER bras de
    `FilterTilesIfCanAttackTargetTileFromSelector$$Select`, dont les deux seuls consommateurs sont
    hors d'atteinte d'un roster (cf. `docs/rl/case-433r4r1r4-porte-elevation-substrat-dsl.md`).

(B) **Le SENS RESTRICTIF, sur une cascade de degat.** `PlasmaCannonAbility$$ExecuteBehaviour`
    (1150, `darkaTerminator`) splashe `PickRandomly(UnitsDirectlyBehind(caster, target), 2)`, et
    `UnitsDirectlyBehind` passe par `IdunBattle.Entities.Selectors.TilesOnSameElevationSelector$$Select`
    (`GetElevationDifference(cand, targetTile) <= maxDiff`, maxDiff = 1 a ce call-site). On drive
    DEUX ennemis derriere la cible -- l'un dans la tolerance, l'autre a `|dElev| >= 2` -- et le
    splash natif ne doit frapper QUE le premier. Oracle a 1 bit.

    Le test compare TROIS lectures sur le MEME etat : le LIVE, le port AVEC le canal (l'etat
    livre), et le port AVEC LE CANAL NEUTRALISE (`elev_by_pos = {}`, l'etat d'AVANT #433-r4-r1-r4).
    C'est le couple divergence -> convergence : sans la troisieme lecture, un accord live/port ne
    prouverait pas que la porte MORD.

Lit l'etat LIVE, aucune tuile/RVA hardcodee (le quadruplet est DERIVE du `boardGraph`). ASCII only.
"""
from __future__ import annotations

import json
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

import hexgeo
from engine.entities.pathfinding.board import Board
from engine.entities.selectors import UnitsDirectlyBehind
from engine.runner.abilities.behaviours import entities_from_state
from engine.runner.snapshot import load_state

PYDIR = Path(__file__).resolve().parents[3]                 # scripts/python
ROOT = PYDIR.parents[1]
CASTER_VIS = "darkaTerminator"
ABILITY = 1150
BOARD = "MC1_67"
A_UNITS = "necroWarden,necroWarden,necroWarden,necroOverlord"


def _caster(dv):
    return next((u for u in (dv.get("units") or [])
                 if u.get("visualId") == CASTER_VIS and u.get("alive")), None)


def _dmg_by_target(res: dict) -> dict:
    """`Amount` par cible dans la cascade d'un `applyAction` (les events vivent sous `actions[]`)."""
    out: dict = {}
    for act in (res.get("actions") or []):
        for e in (act.get("events") or []):
            td = e.get("tags")
            if not td:
                continue
            td = json.loads(td) if isinstance(td, str) else td
            if "Amount" in td:
                out.setdefault(td.get("Target_Id"), []).append(td.get("Amount"))
    return out


def test_433r4r1r4_elevation_gate_live(live_session, rpc):
    state_file = ROOT / "logs" / "runners" / f"r4r1r4-{uuid.uuid4().hex[:8]}.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", "31337", "--state-file", str(state_file),
         "--board", BOARD, "--roster", "1", "--p-units", CASTER_VIS, "--a-units", A_UNITS,
         "--hp-target", "90000"],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not state_file.exists():
        pytest.skip(f"build runner KO: {(proc.stderr or proc.stdout or '')[-300:]}")
    rid = json.loads(state_file.read_text())["runnerId"]
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            pytest.skip("boardGraph indispo")
        tiles = bg["tiles"]
        pos_of = {t["id"]: (t["col"], t["row"]) for t in tiles}
        id_of = {v: k for k, v in pos_of.items()}
        elev = {pos_of[t["id"]]: t.get("elevation") for t in tiles}
        assert len({v for v in elev.values() if v is not None}) >= 2, \
            f"{BOARD} sans relief : le gate ne peut pas mordre, le test serait vert a tort"

        # ---------- (A) la porte, lue sur la liste d'adjacence NATIVE ----------
        manquantes, gatees, en_trop = 0, 0, 0
        for t in tiles:
            p = pos_of[t["id"]]
            stored = set(t.get("neighbours") or [])
            geo = {id_of[q] for q in hexgeo.neighbors(p[0], p[1]) if q in id_of}
            for n in geo - stored:
                manquantes += 1
                if abs(int(elev[p]) - int(elev[pos_of[n]])) >= 2:
                    gatees += 1
            en_trop += len(stored - geo)
        assert manquantes > 0, (
            "aucune arete geometrique absente de la liste native : la porte ne mord nulle part sur "
            f"{BOARD}, l'oracle (A) serait vide")
        assert gatees == manquantes, (
            f"{manquantes - gatees} arete(s) absente(s) de la liste native SANS |dElev| >= 2 : "
            "la porte n'explique pas l'ecart (cf. residu #433-r4-r1-r4-r2, quirks de connectivite)")
        assert en_trop == 0, f"{en_trop} arete(s) stockee(s) hors couronne hex"

        # ---------- (B) le splash de PlasmaCannon ----------
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        if _caster(dv) is None:
            pytest.skip("darkaTerminator absent (pool/spawn)")
        myplayer = _caster(dv).get("owner")
        landed = False
        for _ in range(6):                                  # DEEP-STRIKE : le faire ATTERRIR
            dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
            c = _caster(dv)
            if c is None:
                break
            tin = any("TeleportingIn" in (e.get("name") or "") for e in (c.get("effects") or []))
            if not tin and dv.get("currentPlayer") == myplayer:
                landed = True
                break
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
        if not landed:
            pytest.skip("terminator non atterri / tour non atteint")

        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        c = _caster(dv)
        cpos = (c["pos"]["col"], c["pos"]["row"])
        enemies = [u for u in (dv.get("units") or [])
                   if u.get("owner") != myplayer and u.get("alive")]
        if len(enemies) < 3:
            pytest.skip("moins de 3 ennemis vivants")

        # QUADRUPLET derive du board : cible a portee, DEUX voisins de la cible STRICTEMENT plus
        # loin du caster (`MinDistance(caster, cand) > MinDistance(caster, target)`, #48), l'un
        # hors tolerance d'elevation, l'autre dedans.
        pick = None
        for T in sorted(elev):
            dT = hexgeo.distance(cpos, T)
            if dT < 1 or dT > 3 or T == cpos:
                continue
            ring = [q for q in hexgeo.neighbors(T[0], T[1]) if q in elev and q != cpos]
            hi = [q for q in ring if abs(elev[q] - elev[T]) >= 2
                  and hexgeo.distance(cpos, q) > dT]
            fl = [q for q in ring if abs(elev[q] - elev[T]) <= 1
                  and hexgeo.distance(cpos, q) > dT]
            if hi and fl:
                pick = (T, hi[0], fl[0])
                break
        if pick is None:
            pytest.skip(f"aucun quadruplet (cible, derriere-haut, derriere-plat) sur {BOARD}")
        T, HI, FL = pick

        far = [p for p in sorted(elev) if hexgeo.distance(p, cpos) > 6 and p not in pick]
        plan = [(enemies[0]["id"], T), (enemies[1]["id"], HI), (enemies[2]["id"], FL)]
        plan += [(u["id"], far[i]) for i, u in enumerate(enemies[3:]) if i < len(far)]
        for uid, p in plan:                                 # `applyAction move` ignore portee/propriete
            rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": uid, "to": {"col": p[0], "row": p[1]}}}, 60)
        tgt, u_hi, u_fl = plan[0][0], plan[1][0], plan[2][0]

        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        posn = {u["id"]: (u["pos"]["col"], u["pos"]["row"])
                for u in (dv.get("units") or []) if u.get("pos")}
        if (posn.get(tgt), posn.get(u_hi), posn.get(u_fl)) != (T, HI, FL):
            pytest.skip(f"montage non atteint : {posn.get(tgt)}/{posn.get(u_hi)}/{posn.get(u_fl)}")

        ob = rpc("observeBattle", {"runnerId": rid}, 40)
        cs = rpc("combatSnapshot", {"runnerId": rid}, 60)
        board = Board(tiles, adjacency="native_sym")
        st = load_state(dv, ob, cs, board=board)

        ent = entities_from_state(st, c["id"], tgt)
        assert ent.elev_by_pos, "le canal d'elevation n'est pas pose sur le contexte runner"
        udb = sorted(x.get("id") for x in UnitsDirectlyBehind().select(ent))

        ent_avant = entities_from_state(st, c["id"], tgt)
        ent_avant.elev_by_pos = {}                          # l'etat d'AVANT #433-r4-r1-r4
        udb_avant = sorted(x.get("id") for x in UnitsDirectlyBehind().select(ent_avant))

        res = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": c["id"], "targetId": tgt, "abilityType": ABILITY}}, 120)
        assert res.get("ok"), f"cast live KO: {str(res)[:200]}"
        live = set(_dmg_by_target(res))

        print(f"\n[r4r1r4] caster u{c['id']}@{cpos} target u{tgt}@{T}(elev {elev[T]}) "
              f"high u{u_hi}@{HI}(elev {elev[HI]}) flat u{u_fl}@{FL}(elev {elev[FL]})"
              f"\n         live={sorted(live)} port={udb} port_sans_canal={udb_avant}")

        # le NATIF exclut l'unite hors tolerance : ni la cible principale, ni le splash ne l'atteint
        assert live == {tgt, u_fl}, (
            f"live frappe {sorted(live)} != cible+derriere-plat {sorted([tgt, u_fl])} -- "
            f"u{u_hi} est a |dElev| = {abs(elev[HI] - elev[T])} de la cible")
        assert udb == [u_fl], f"port {udb} != [{u_fl}] (le gate d'elevation ne mord pas)"
        # CONTRE-EPREUVE : sans le canal, le port DIVERGE du natif sur ce meme etat
        assert udb_avant == sorted([u_hi, u_fl]), (
            f"port sans canal {udb_avant} != {sorted([u_hi, u_fl])} -- le montage ne discrimine "
            "plus rien, l'accord ci-dessus serait tautologique")
        assert set(udb) != set(udb_avant)
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 30)
