"""Case #48 -- DISCRIMINANT LIVE du comparateur `UnitsDirectlyBehind` : `>` STRICT (AmountIsGreater).

RE (docs/rl/case-48-units-directly-behind-comparator.md) : `IdunBattleLogic.Entities.DSLSelectors$$UnitsDirectlyBehind`
finit par le SINGLETON `DAT_1832482b0` = classe construite par `IdunBattleLogic.Entities.DSLTriggers$$AmountIsGreater`
(`IdunBattle.Entities.Conditions.AmountIsGreaterAbilityTrigger$$ShouldTrigger : iVar16 < iVar15` == `>` STRICT) -- PAS `AmountIsEqualOrGreater` (le nom du
ctor FOLDE, mislabele par ghidra, le faisait croire). Formule = `IdunBattleLogic.Entities.DSLFormulas$$MinDistance` (distance hex).
Donc `MinDistance(caster, candidate) > MinDistance(caster, target)` (`>` STRICT). Le seul cas frontiere qui
separe `>` de `>=` est le candidat LATERAL a distance EGALE (dist(caster, candidate) == dist(caster, target),
delta 0 sur l'anneau R1 de la cible) : `>` l'EXCLUT (l'ancien offline `>=` le sur-incluait a tort).

Le test existant `test_plasma_cannon_live.py` utilise une geometrie STRICTE (unites a d=3 > d_ct=2, delta +1)
qui NE discrimine PAS `>`/`>=` (les deux s'accordent). CE test comble ce trou : il place sur l'anneau R1 de
la cible EXACTEMENT 1 unite LATERALE (delta 0) + 1 unite AWAY (delta +1), tout le reste parque LOIN. Sous
`>` (natif confirme), UnitsDirectlyBehind = {away} seul -> le splash LIVE frappe {main, away}, la LATERALE
est ABSENTE. (Sous l'ancien `>=` bugue, ce serait {main, lateral, away}.) L'absence de la laterale du splash
LIVE == son exclusion offline confirme `>` STRICT.

Board plat (--board MC1_67, elevation uniforme -> gate elevation no-op). darkaTerminator DEEP-STRIKE
(TeleportStrike) -> on la fait ATTERRIR (endturn) avant de caster. Drive-positions : on DEPLACE les unites
pour fabriquer le cas frontiere. Lit l'etat LIVE, aucune tuile/RVA hardcodee. ASCII only. Skip propre si
build/geometrie/darkaTerminator indispo.
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
from engine.runner.snapshot import load_state
from engine.runner.abilities.behaviours.context import entities_from_state
from engine.entities.selectors.units import UnitsDirectlyBehind

PYDIR = Path(__file__).resolve().parents[3]                 # scripts/python
ROOT = PYDIR.parents[1]                                      # racine repo
CASTER_VIS = "darkaTerminator"
ABILITY = 1150
A_UNITS = "necroWarden,necroWarden,necroWarden,necroOverlord"


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _caster(dv):
    return next((u for u in (dv.get("units") or []) if u.get("visualId") == CASTER_VIS and u.get("alive")), None)


def test_plasma_cannon_lateral_directly_behind_live(live_session, rpc):
    """DISCRIMINANT : le natif EXCLUT l'unite LATERALE a distance EGALE du splash directly-behind
    (confirme `>` STRICT). offline `UnitsDirectlyBehind == {away}` (lateral exclu) == splash LIVE {main, away}."""
    state_file = ROOT / "logs" / "runners" / f"plasmacannon-lateral-{uuid.uuid4().hex[:8]}.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", "777", "--state-file", str(state_file),
         "--board", "MC1_67", "--roster", "1", "--p-units", CASTER_VIS, "--a-units", A_UNITS,
         "--hp-target", "90000"],                            # armure 0 + PV hauts (survivent) -> isole le targeting
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not state_file.exists():
        pytest.skip(f"build runner KO: {(proc.stderr or proc.stdout or '')[-300:]}")
    rid = json.loads(state_file.read_text())["runnerId"]
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            pytest.skip("boardGraph indispo")
        tiles = bg["tiles"]
        elev = {(t["col"], t["row"]): t.get("elevation") for t in tiles}
        board = Board(tiles, adjacency="native_sym")

        def mv(uid, tid):
            c = board.coord(tid)
            return rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": uid, "to": {"col": c[0], "row": c[1]}}}, 60)

        # --- faire ATTERRIR le terminator (deep-strike) et revenir a mon tour ---
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        if not _ok(dv) or _caster(dv) is None:
            pytest.skip("darkaTerminator absent (pool/spawn)")
        myplayer = _caster(dv).get("owner")
        landed = False
        for _ in range(6):
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
        caster = _caster(dv)
        cid = caster["id"]
        cpos = (caster["pos"]["col"], caster["pos"]["row"])
        ctile = board.id_at(*cpos)
        eC = elev.get(cpos)
        enemies = [u for u in (dv.get("units") or []) if u.get("owner") != myplayer and u.get("alive")]
        if len(enemies) < 3:
            pytest.skip("moins de 3 ennemis vivants (besoin cible + lateral + away)")

        # park TOUS les ennemis LOIN (isole la geometrie de l'anneau)
        far = [t for t in sorted(board.by_id) if board.walkable(t)
               and hexgeo.distance(board.coord(t), cpos) > 6]
        if len(far) < len(enemies):
            pytest.skip("pas assez de tuiles lointaines pour parquer")
        for e, ft in zip(enemies, far):
            mv(e["id"], ft)

        # --- geometrie DISCRIMINANTE : cible T a d_ct=2 du caster ; sur son anneau R1, un voisin LATERAL
        #     (delta 0 : dist(caster)==d_ct) et un voisin AWAY (delta +1 : dist(caster)==d_ct+1), tous deux
        #     walkable + meme elevation (+-1). Le cast doit etre LEGAL (fromHere). ---
        cand = None
        for T in sorted(board.by_id):
            ct = board.coord(T)
            if not board.walkable(T) or T == ctile or hexgeo.distance(ct, cpos) != 2:
                continue
            if elev.get(ct) is None or eC is None or abs(elev.get(ct) - eC) > 1:
                continue
            lateral = away = None
            for n in board.neighbours(T):
                if not board.walkable(n) or n == ctile:
                    continue
                cn = board.coord(n)
                if elev.get(cn) is None or abs(elev.get(cn) - elev.get(ct)) > 1:
                    continue
                delta = hexgeo.distance(cn, cpos) - 2                # d_ct == 2
                if delta == 0 and lateral is None:
                    lateral = n
                elif delta == 1 and away is None:
                    away = n
            if lateral is None or away is None:
                continue
            mv(enemies[0]["id"], T)
            at = rpc("abilityTargets", {"runnerId": rid, "unitId": cid, "abilityType": ABILITY}, 90)
            fh = [x.get("targetId") for x in
                  next((a for a in ((at.get("units") or [{}])[0].get("abilities") or [])
                        if a.get("abilityId") == ABILITY), {}).get("fromHere") or []]
            if enemies[0]["id"] in fh:
                cand = (T, lateral, away)
                break
            mv(enemies[0]["id"], far[0])
        if cand is None:
            pytest.skip("aucune geometrie lateral+away LEGALE (board/elevation)")
        T, ltile, atile = cand

        target, u_lat, u_away = enemies[0], enemies[1], enemies[2]
        mv(u_lat["id"], ltile)      # LATERAL (delta 0, distance EGALE) -- discriminant (doit etre EXCLU)
        mv(u_away["id"], atile)     # AWAY   (delta +1) -- controle positif (doit etre INCLU)

        # re-check legalite APRES placements (LOS caster->cible)
        at2 = rpc("abilityTargets", {"runnerId": rid, "unitId": cid, "abilityType": ABILITY}, 90)
        fh2 = [x.get("targetId") for x in
               next((a for a in ((at2.get("units") or [{}])[0].get("abilities") or [])
                     if a.get("abilityId") == ABILITY), {}).get("fromHere") or []]
        if target["id"] not in fh2:
            pytest.skip("cast devenu illegal apres placement (LOS)")

        # --- offline : UnitsDirectlyBehind DOIT contenir EXACTEMENT {away} (le lateral EXCLU par `>` STRICT) ---
        dv2 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        ob2 = rpc("observeBattle", {"runnerId": rid}, 60)
        snap2 = rpc("combatSnapshot", {"runnerId": rid}, 90)
        st = load_state(dv2, ob2, snap2)
        st.board = board
        ent = entities_from_state(st, cid, target["id"])
        udb = sorted(x.get("id") for x in UnitsDirectlyBehind().select(ent))
        assert set(udb) == {u_away["id"]}, (
            f"UnitsDirectlyBehind offline {udb} != {{away {u_away['id']}}} : le lateral a distance EGALE "
            f"({u_lat['id']}) doit etre EXCLU (natif `>` STRICT AmountIsGreater)")

        # ============ LIVE cast : le splash natif doit frapper {main, away} SANS la laterale ============
        cast = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": cid, "targetId": target["id"], "abilityType": ABILITY},
            "captureEvents": True}, 120)
        assert _ok(cast), f"cast PlasmaCannon non applique: {str(cast)[:200]}"
        live_targets = set()
        for act in (cast.get("actions") or []):
            for e in (act.get("events") or []):
                td = e.get("tags")
                if not td:
                    continue
                td = json.loads(td) if isinstance(td, str) else td
                if "Amount" in td and td.get("Active_Ability_Type") == ABILITY:
                    live_targets.add(td.get("Target_Id"))

        assert live_targets == {target["id"], u_away["id"]}, (
            f"cibles PlasmaCannon live {sorted(live_targets)} != {{main {target['id']}, away "
            f"{u_away['id']}}} : le natif doit EXCLURE l'unite LATERALE a distance EGALE (comparateur `>` "
            f"STRICT). Sa presence signifierait `>=` (l'ancien bug offline).")
        # DISCRIMINANT explicite : la laterale est ABSENTE (aurait ete presente sous l'ancien `>=`).
        assert u_lat["id"] not in live_targets, (
            f"unite LATERALE {u_lat['id']} presente dans le splash live -> le natif utiliserait `>=`, "
            f"contredisant le RE (DAT_1832482b0 = AmountIsGreater = `>` STRICT IdunBattle.Entities.Conditions.AmountIsGreaterAbilityTrigger$$ShouldTrigger)")
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 20)
        except Exception:
            pass
        try:
            state_file.unlink()
        except Exception:
            pass
