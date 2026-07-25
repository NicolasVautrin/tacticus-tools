#!/usr/bin/env python
"""Probe #61bis tranche 3 — arbitrage LIVE de la prediction MV71 (1076, drone a distance).

Le natif (`IdunBattleLogic.Entities.Abilities.Triggered.Loki.MV71SniperDroneSquadAttackAbility$$PredictAttack`, branche distance) passe au
service slot 0x24 un widget modifiers ZEROE (memset &local_3f8) au lieu du param_4 du playbook.
Question ouverte : les mods DEFENSEUR (Markerlight +15%, stat-mods DEFENSE) et/ou POSITIONNELS
(elevation) sont-ils calcules EN AVAL dans le service (=> ils s'appliquent malgre le widget zeroe),
ou le widget est-il la SEULE source de mods (=> prediction nue) ?

Harnais : confrontation PER-TUILE (canal `ranked` de decisionView = oracle natif par position
candidate) offline vs natif, offline = make_normal_attack_predictions (dispatch MV71 v1 = widget
zeroe, AUCUN mod). Datapoints :
  A. rows PRE-cast (cible sans Markerlight) : v1 colle ? ratio oracle/offline par row
     (~1.0 = v1 exact ; ~1.5 sur tuile sur-elevee = elevation DANS le service ; autre = a creuser).
  B. cast 1076 (pose Markerlight sur la cible) -> rows du tour SUIVANT : ratio ~1.15 = mods
     DEFENSEUR dans le service ; 1.0 = widget zeroe litteral. CONTROLE : les rows de templAncient
     (Imperial, pas T'au) doivent rester a 1.0 quel que soit le verdict (gate HasFaction(9)).
  C. aiPlaybookPredict depuis la tuile courante : appliedHits attendu = 1 + ExtraHits(caster)=0
     (delegue m860) — les 2 armes (drone et Sho'syl) font 1 hit, la magnitude ne discrimine pas,
     mais un appliedHits != 1 refuterait le modele.

ASCII only (cp1252). Usage: python probe_61bis_pred.py [--seed 61010] [--max-rounds 8]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hexgeo  # noqa: E402
from rl_collect_batch import _resolve_session, _rpc  # noqa: E402
from engine.playbook import scene as SC  # noqa: E402
from engine.playbook.scene import Scene  # noqa: E402
from engine.playbook import prediction  # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
STATE = ROOT / "data" / "_61bis_pred_state.json"
CASTER_VIS = "tauMarksman"          # Sho'syl (attaque normale = 1076)
CONTROL_VIS = "templAncient"        # controle non-T'au (gate HasFaction(9) doit l'exclure)
TARGET_VIS = "astraYarrick"
ABILITY = 1076
MV_SHO = 2
W, H = 7, 9                          # bornes MC1_67


def _r(sid: int, method: str, body: dict, t: float = 90) -> dict:
    return (_rpc(sid, method, [body], timeout=t).get("result") or {})


def build(seed: int) -> int:
    STATE.unlink(missing_ok=True)
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
         "--state-file", str(STATE), "--board", "MC1_67",
         "--p-units", f"{CASTER_VIS},{CONTROL_VIS}", "--a-units", TARGET_VIS,
         "--hp-target", "200000", "--hp-player", "60000"],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not STATE.exists():
        print(f"[61p] build KO: {(proc.stderr or proc.stdout or '')[-400:]}", file=sys.stderr)
        sys.exit(2)
    return json.loads(STATE.read_text())["runnerId"]


def _units_by_vis(dv: dict) -> dict:
    return {u.get("visualId"): u for u in (dv.get("units") or []) if u.get("alive")}


def _pos(u: dict) -> tuple:
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row"))


def _elev(board, pos) -> int:
    if board is None or pos is None:
        return 0
    for t in board.by_id.values():
        if (t["col"], t["row"]) == tuple(pos):
            return int(t.get("elevation") or 0)
    return 0


def _rows_for(dec, scene, att_id: int, tgt_id: int, board, tgt_pos, marklit: bool) -> list:
    """Rows (tile candidate, oracle natif, offline v1) des attaques NORMALES rankees vs la cible."""
    rows = []
    norm_ids = {ab.get("id") for u in (dec.get("units") or []) if u.get("id") == att_id
                for ab in (u.get("abilities") or []) if ab.get("kind") == "normal"}
    for ap in (dec.get("attackPlans") or []):
        if ap.get("unitId") != att_id:
            continue
        for ev in (ap.get("evals") or []):
            if ev.get("targetId") != tgt_id:
                continue
            if norm_ids and ev.get("abilityId") not in norm_ids:
                continue
            for rk in (ev.get("ranked") or []):
                if rk.get("dmgMax") is None or rk.get("col") is None:
                    continue
                tile = (rk["col"], rk["row"])
                out = prediction.make_normal_attack_predictions(scene, att_id, tgt_id, tile,
                                                                meta=True)
                if out is None:
                    continue
                ev_off, meta = out
                res = ev_off.prediction.accurate_health_damage
                omin, omax = rk.get("dmgMin"), rk.get("dmgMax")
                fmin = (omin / res.min) if res.min else None
                fmax = (omax / res.max) if res.max else None
                rows.append({"tile": tile, "ab": ev.get("abilityId"),
                             "d_tgt": hexgeo.distance(tile, tgt_pos),
                             "elev_cand": _elev(board, tile),
                             "opt": bool(rk.get("predOptimistic")),
                             "marklit": marklit,
                             "oracle": (omin, omax), "offline": (res.min, res.max),
                             "ratio": (round(fmin, 3) if fmin else None,
                                       round(fmax, 3) if fmax else None),
                             "meta": {k: meta.get(k) for k in ("mv71", "tile", "hits",
                                                               "base", "pierce", "profile")}})
    return rows


def _advance_to_my_turn(rpc, rid, vis, max_iter=12):
    """Avance au tour du proprietaire de `vis` (mirror test_mv71 : decisionView LEGER dans la
    boucle ; tour adverse -> aiPlayTurn, endturn de secours) puis re-fetch riche (maxRank 99)."""
    for _ in range(max_iter):
        dec = rpc("decisionView", {"runnerId": rid}, 150)
        if not isinstance(dec, dict) or not dec.get("ok"):
            return None, None
        u = next((x for x in (dec.get("units") or [])
                  if x.get("visualId") == vis and x.get("alive")), None)
        if u is None:
            return dec, None
        if dec.get("currentPlayer") == u.get("owner"):
            rich = rpc("decisionView", {"runnerId": rid, "maxRank": 99,
                                        "allAbilities": True}, 150)
            if isinstance(rich, dict) and rich.get("ok"):
                u2 = next((x for x in (rich.get("units") or [])
                           if x.get("visualId") == vis and x.get("alive")), None)
                return rich, u2
            return None, None
        rpc("aiPlayTurn", {"runnerId": rid}, 180)
        dec2 = rpc("decisionView", {"runnerId": rid}, 150)
        if isinstance(dec2, dict) and dec2.get("ok") \
                and dec2.get("currentPlayer") != u.get("owner"):
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    return None, None


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=61010)
    ap.add_argument("--max-rounds", type=int, default=8)
    args = ap.parse_args(argv)
    sid = _resolve_session()
    rid = build(args.seed)
    rpc = lambda m, b, t=90: _r(sid, m, b, t)   # noqa: E731
    print(f"[61p] seed={args.seed} runner={rid}")
    all_rows, casted = [], False
    try:
        board = SC.build_board(rpc, rid)
        for rnd in range(args.max_rounds):
            dec, sho = _advance_to_my_turn(rpc, rid, CASTER_VIS)
            if sho is None:
                print(f"[61p] round {rnd}: Sho'syl introuvable / dec KO -> stop")
                break
            byvis = _units_by_vis(dec)
            tgt = byvis.get(TARGET_VIS)
            ctl = byvis.get(CONTROL_VIS)
            if tgt is None:
                print(f"[61p] round {rnd}: cible perdue -> stop")
                break
            tpos = _pos(tgt)
            spos = _pos(sho)
            tgt_eff = [e.get("name") for e in (tgt.get("effects") or [])]
            marklit = "Markerlight" in tgt_eff
            predictor = SC.build_predictor(rpc, rid)
            if predictor is None:
                print("[61p] combatSnapshot KO")
                return 2
            sctx = SC.step_context(predictor, dec)
            scene = Scene.from_predictor_sctx(predictor, sctx, None)
            rows = _rows_for(dec, scene, sho["id"], tgt["id"], board, tpos, marklit)
            crows = (_rows_for(dec, scene, ctl["id"], tgt["id"], board, tpos, marklit)
                     if ctl is not None else [])
            d = hexgeo.distance(spos, tpos)
            print(f"[61p] round {rnd}: sho={spos} tgt={tpos} d={d} elev_sho={_elev(board, spos)}"
                  f" elev_tgt={_elev(board, tpos)} marklit={marklit}"
                  f" rows={len(rows)} ctl_rows={len(crows)}")
            for x in rows:
                print(f"  [sho] tile={x['tile']} d_tgt={x['d_tgt']} elev={x['elev_cand']}"
                      f" opt={x['opt']} oracle={x['oracle']} off={x['offline']}"
                      f" ratio={x['ratio']} meta={x['meta']}")
            for x in crows[:4]:
                print(f"  [ctl] tile={x['tile']} d_tgt={x['d_tgt']} oracle={x['oracle']}"
                      f" off={x['offline']} ratio={x['ratio']}")
            # datapoint C : oracle per-tile (col/row = UnitPositionAtTile) — healthDmg + appliedHits.
            # Tuiles sondees : la courante + les 3 premieres rankees (si presentes).
            pb_tiles = [tuple(spos)] + [x["tile"] for x in rows[:3]]
            for pt in dict.fromkeys(pb_tiles):
                body = {"runnerId": rid, "unitId": sho["id"], "targetId": tgt["id"],
                        "abilityType": ABILITY, "col": int(pt[0]), "row": int(pt[1])}
                pb = rpc("aiPlaybookPredict", body, 60)
                if isinstance(pb, dict) and pb.get("ok"):
                    out = prediction.make_normal_attack_predictions(
                        scene, sho["id"], tgt["id"], pt, meta=True)
                    om = out[0].prediction.accurate_health_damage if out else None
                    for e in (pb.get("events") or []):
                        print(f"  [pb] tile={pt} elev={_elev(board, pt)} tgt_ev={e.get('targetId')}"
                              f" nat=({e.get('healthDmgMin')},{e.get('healthDmgMax')})"
                              f" raw=({e.get('willKillDmg')},{e.get('mightKillDmg')})"
                              f" hits={e.get('appliedHits')}"
                              f" off=({om.min if om else None},{om.max if om else None})")
                else:
                    print(f"  [pb] tile={pt} KO: {str(pb)[:160]}")
            all_rows += rows + crows
            # B : caster 1076 une fois a portee (marque la cible pour les rounds suivants)
            if not casted and 2 <= d <= 3:
                res = rpc("applyAction", {"runnerId": rid, "action": {
                    "kind": "ability", "casterId": sho["id"], "targetId": tgt["id"],
                    "abilityType": ABILITY}}, 120)
                a0 = ((res or {}).get("actions") or [{}])[0]
                casted = bool(a0.get("ok")) and bool(a0.get("mutated"))
                print(f"  [cast] ok={casted}")
            elif not casted:
                # drive greedy vers dist 2-3 de la cible
                cands = [t for t in hexgeo.disk(spos[0], spos[1], MV_SHO)
                         if 0 <= t[0] < W and 0 <= t[1] < H and t != tuple(spos)]
                occ = {tuple(_pos(u)) for u in (dec.get("units") or []) if u.get("alive")}
                cands = [t for t in cands if t not in occ]
                cands.sort(key=lambda t: abs(hexgeo.distance(t, tpos) - 3))
                for t in cands[:10]:
                    r2 = rpc("applyAction", {"runnerId": rid, "action": {
                        "kind": "move", "unitId": sho["id"],
                        "to": {"col": t[0], "row": t[1]}}}, 60)
                    a0 = ((r2 or {}).get("actions") or [{}])[0]
                    if a0.get("ok") and a0.get("mutated"):
                        break
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            post = sum(1 for x in all_rows if x["marklit"] and x["ab"] == ABILITY)
            if casted and post >= 3:
                break
        pre = [x for x in all_rows if not x["marklit"] and x["ab"] == ABILITY]
        post = [x for x in all_rows if x["marklit"] and x["ab"] == ABILITY]
        print(f"[61p] TOTAL rows sho: pre={len(pre)} post-marklight={len(post)}")
        exact_pre = sum(1 for x in pre if x["oracle"] == x["offline"])
        exact_post = sum(1 for x in post if x["oracle"] == x["offline"])
        print(f"[61p] EXACT v1: pre {exact_pre}/{len(pre)} ; post {exact_post}/{len(post)}")
        return 0
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 30)
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
