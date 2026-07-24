#!/usr/bin/env python
"""Probe #220 -- agreement PREDICTION per-tuile : aura alliee DefenderOfTheGreaterGood_ExtraDmg (1182,
tauShadowsun). L'effet vit sur le PORTEUR (Shadowsun) et bonifie +extraDmg les attaques RANGED non-Psychic
des amis SOIT adjacents (range 1, TOUTE faction) SOIT T'au dans range 2 (@180f3e4f0 gate OwnerIsCaster &
IsRangedAttack & !DamageProfileIs(Psychic) ; selector @180e20590 = (AdjacentFriends(1)-owner) +
UnitsFromFaction(SurroundingFriends(2), Tau=9)).

Design DRIVE-POSITIONS (carriers cote joueur) : p-units = tauShadowsun (porteur) + tauCrisis (Tau, ranged
R2 Pulse, normal-attack STANDARD -> base bit-exact, tier T'au range-2) + admecDestroyer (AdMech NON-Tau,
ranged R3 Physical, tier ADJACENT range-1 seul). NB : tauMarksman ECARTE -- son "normal attack" = ability
1076 (MV71 sniper range-dependent) dont la prediction de BASE diverge offline, polluant l'agreement (pas
un miss DotGG). L'admec + tauCrisis ont des normal-attacks propres (base bit-exact confirmee).
a-unit cible = bloodSanguinary. A chaque debut de MON tour, decisionView maxRank 99 emet les plans multi-
tuiles rankes de MES 2 beneficiaires vs la cible -> oracle natif per-tuile, confronte a
make_normal_attack_predictions (TOL 3), AVEC aura et SANS (mock.patch aura -> None).

Discriminateurs (adversariaux) :
  (A) offline_avec_aura == oracle (TOL 3) pour TOUTES les tuiles.
  (B) aucune tuile ou l'aura est load-bearing (offline_avec != offline_sans) HORS portee :
      toute divergence satisfait (d_shadowsun==1) OU (d_shadowsun==2 ET faction==Tau). Pas de sur-application.
  (C) load-bearing EXISTE dans chaque categorie :
      - EXISTS divergence a d_shadowsun==1 (tier ADJACENT, toute faction) ;
      - EXISTS divergence faction==Tau a d_shadowsun==2 (tier T'au range-2) ;
      - admecDestroyer (NON-Tau) : AUCUNE divergence a d_shadowsun>=2 (le non-Tau est EXCLU au ring-2).

ASCII only (cp1252). Usage: python probe_220_dotgg.py [--seed 220] [--max-rounds 10]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hexgeo  # noqa: E402
from rl_collect_batch import _resolve_session, _rpc  # noqa: E402
from engine.playbook import scene as SC  # noqa: E402
from engine.playbook.scene import Scene  # noqa: E402
from engine.playbook import prediction  # noqa: E402
from engine.entities.effects.loki.extra_damage import (  # noqa: E402
    DefenderOfTheGreaterGoodExtraDmgEffect)

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
STATE = ROOT / "data" / "_220_dotgg_a5897909_state.json"
TOL = 3
P_UNITS = "tauShadowsun,tauCrisis,admecDestroyer"
A_UNITS = "bloodSanguinary"
CARRIER = "tauShadowsun"
BENEF = {"tauCrisis": "Tau", "admecDestroyer": "AdMech"}   # faction (Tau -> tier range-2 ; autre -> adj seul)
TAU_BENEF = "tauCrisis"        # Tau ranged-R2 propre (tier range-2) ; ECARTE tauMarksman (sniper 1076 noisy)
W, H = 7, 9                     # bornes MC1_67
MV = {"tauShadowsun": 4, "tauCrisis": 4, "admecDestroyer": 2}


def _r(sid: int, method: str, body: dict, t: float = 90) -> dict:
    return (_rpc(sid, method, [body], timeout=t).get("result") or {})


def build(seed: int) -> int:
    STATE.unlink(missing_ok=True)
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
         "--state-file", str(STATE), "--board", "MC1_67",
         "--p-units", P_UNITS, "--a-units", A_UNITS, "--hp-player", "40000"],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not STATE.exists():
        print(f"[220] build KO: {(proc.stderr or proc.stdout or '')[-400:]}", file=sys.stderr)
        sys.exit(2)
    return json.loads(STATE.read_text())["runnerId"]


def _units_by_vis(dv: dict) -> dict:
    return {u.get("visualId"): u for u in (dv.get("units") or []) if u.get("alive")}


def _pos(u: dict) -> tuple:
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row"))


def _collect_rows(dec, predictor, scene, att_ids, tgt_id, shad_pos):
    """Lignes (att, tile, oracle, offline_avec, offline_sans, d_shad) des attaques NORMALES rankees vs cible."""
    rows = []
    for ap in (dec.get("attackPlans") or []):
        a_id = ap.get("unitId")
        if a_id not in att_ids or a_id not in predictor["ctx_by_id"]:
            continue
        norm_ids = {ab.get("id") for u in (dec.get("units") or []) if u.get("id") == a_id
                    for ab in (u.get("abilities") or []) if ab.get("kind") == "normal"}
        for ev in (ap.get("evals") or []):
            if ev.get("targetId") != tgt_id:
                continue
            if norm_ids and ev.get("abilityId") not in norm_ids:
                continue
            for rk in (ev.get("ranked") or []):
                if rk.get("dmgMax") is None or rk.get("col") is None:
                    continue
                tile = (rk["col"], rk["row"])
                ev_off = prediction.make_normal_attack_predictions(scene, a_id, tgt_id, tile)
                res = ev_off.prediction.accurate_health_damage
                rows.append({"att": a_id, "tile": tile, "ab": ev.get("abilityId"),
                             "d_shad": hexgeo.distance(tile, shad_pos),
                             "oracle": (rk.get("dmgMin"), rk.get("dmgMax")),
                             "offline": (res.min, res.max)})
    return rows


def _agree(oracle, offline) -> bool:
    return max(abs(oracle[0] - offline[0]), abs(oracle[1] - offline[1])) <= TOL


def _park(rpc, rid, uid, vis, cur, goal, occupied):
    cands = [t for t in hexgeo.disk(cur[0], cur[1], MV.get(vis, 2))
             if 0 <= t[0] < W and 0 <= t[1] < H and t not in occupied and t != cur]
    cands.sort(key=lambda t: (hexgeo.distance(t, goal), hexgeo.distance(t, cur)))
    newpos = cur
    for t in cands[:14]:
        try:
            r = rpc("applyAction", {"runnerId": rid, "actions": [
                {"kind": "move", "unitId": uid, "to": {"col": t[0], "row": t[1]}}]}, 60)
        except Exception:
            continue
        if isinstance(r, dict) and r.get("ok", True) and not r.get("error"):
            newpos = t
            break
    try:
        rpc("applyAction", {"runnerId": rid, "actions": [{"kind": "finish", "unitId": uid}]}, 60)
    except Exception:
        pass
    return newpos


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=220)
    ap.add_argument("--max-rounds", type=int, default=10)
    args = ap.parse_args(argv)
    sid = _resolve_session()
    rid = build(args.seed)
    rpc = lambda m, b, t=90: _r(sid, m, b, t)   # noqa: E731
    print(f"[220] seed={args.seed} runner={rid}")
    try:
        dv0 = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 60)
        byvis = _units_by_vis(dv0)
        need = (CARRIER, TAU_BENEF, "admecDestroyer", A_UNITS)
        if any(v not in byvis for v in need):
            print(f"[220] roster KO (vis: {sorted(byvis)})"); return 2
        ids = {v: byvis[v]["id"] for v in need}
        shad, mark, sygex, sang = (ids[CARRIER], ids[TAU_BENEF],
                                   ids["admecDestroyer"], ids[A_UNITS])
        fac_by_id = {mark: "Tau", sygex: "AdMech"}
        shad_eff0 = [e.get("name") for e in (byvis[CARRIER].get("effects") or [])]
        print(f"[220] shad=u{shad} mark=u{mark}(Tau) sygex=u{sygex}(AdMech) sang=u{sang} "
              f"shadEff={shad_eff0}")
        if "DefenderOfTheGreaterGood_ExtraDmg" not in shad_eff0:
            print("[220] Shadowsun ne porte PAS DefenderOfTheGreaterGood_ExtraDmg -> abort"); return 2

        all_rows, cf_pairs = [], []
        for rnd in range(args.max_rounds):
            dec = rpc("decisionView", {"runnerId": rid, "maxRank": 99, "allAbilities": True}, 120)
            byvis = _units_by_vis(dec)
            if any(v not in byvis for v in need):
                print(f"[220] unite perdue round {rnd} (vis: {sorted(byvis)}) -> stop"); break
            sp = _pos(byvis[CARRIER])
            predictor = SC.build_predictor(rpc, rid)
            if predictor is None:
                print("[220] combatSnapshot KO"); return 2
            sctx = SC.step_context(predictor, dec)
            scene = Scene.from_predictor_sctx(predictor, sctx, None)
            att_ids = {mark, sygex}
            rows = _collect_rows(dec, predictor, scene, att_ids, sang, sp)
            for x in rows:
                x["rnd"] = rnd
                x["fac"] = fac_by_id[x["att"]]
            all_rows += rows
            if rows:
                cf_pairs.append((dec, predictor, scene, sp, att_ids, dict(fac_by_id)))
            cov = {
                "mark_d1": sum(1 for x in all_rows if x["att"] == mark and x["d_shad"] == 1),
                "mark_d2": sum(1 for x in all_rows if x["att"] == mark and x["d_shad"] == 2),
                "sygex_d1": sum(1 for x in all_rows if x["att"] == sygex and x["d_shad"] == 1),
                "sygex_d2": sum(1 for x in all_rows if x["att"] == sygex and x["d_shad"] == 2),
            }
            tp = _pos(byvis[A_UNITS])
            print(f"[220] round {rnd}: shad@{sp} sang@{tp} rows=+{len(rows)} cov={cov}")
            if cov["mark_d2"] and cov["sygex_d1"] and cov["sygex_d2"]:
                break
            # parking : Shadowsun a 2 hexes de la cible ; marksman a 2-3 (tier Tau range-2) ;
            # sygex tout pres de Shadowsun (pour des tuiles a d_shad 1 ET 2).
            occ = {_pos(byvis[v]) for v in need}
            for vis, uid, anchor, rad in (
                    (CARRIER, shad, A_UNITS, 2),
                    (TAU_BENEF, mark, A_UNITS, 2),         # R2 ranged -> anchor a dist-2 de la cible
                    ("admecDestroyer", sygex, CARRIER, 1)):
                cur = _pos(byvis[vis])
                a_pos = _pos(byvis[anchor])
                ring = [t for t in hexgeo.ring(a_pos[0], a_pos[1], rad)
                        if 0 <= t[0] < W and 0 <= t[1] < H]
                goal = min(ring, key=lambda t: hexgeo.distance(t, cur)) if ring else a_pos
                occ.discard(cur)
                np_ = _park(rpc, rid, uid, vis, cur, goal, occ)
                occ.add(np_)
            subprocess.run([sys.executable, "rl_duel.py", "aiturn", "--state-file", str(STATE)],
                           cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8",
                           errors="replace")
        if not all_rows:
            print("[220] AUCUNE ligne rankee -> scenario KO"); return 3

        # (A) agrement offline (avec aura) == oracle natif
        bad = []
        for x in all_rows:
            who = "mark" if x["att"] == mark else "sygex"
            ok = _agree(x["oracle"], x["offline"])
            if not ok:
                bad.append(x)
            print(f"  [{who} {x['fac']}] r{x['rnd']} tile={x['tile']} d_shad={x['d_shad']} "
                  f"ab={x['ab']} oracle={x['oracle']} offline={x['offline']} {'OK' if ok else '** MISS **'}")

        # (B/C) counterfactuel : DotGG aura OFF -> tuiles load-bearing
        diverging = []
        with mock.patch.object(DefenderOfTheGreaterGoodExtraDmgEffect,
                               "create_aura_attack_damage_bonus_for_ally",
                               lambda self, ctx=None: None):
            for _dec, _pred, _scene, _sp, _atts, _fac in cf_pairs:
                for x in _collect_rows(_dec, _pred, _scene, _atts, sang, _sp):
                    row_avec = next((r for r in all_rows if r["att"] == x["att"]
                                     and r["tile"] == x["tile"] and r["d_shad"] == x["d_shad"]), None)
                    if row_avec is None:
                        continue
                    if row_avec["offline"] != x["offline"]:      # aura load-bearing sur cette tuile
                        diverging.append({"att": x["att"], "fac": _fac[x["att"]], "tile": x["tile"],
                                          "d_shad": x["d_shad"], "avec": row_avec["offline"],
                                          "sans": x["offline"]})
        for d in diverging:
            who = "mark" if d["att"] == mark else "sygex"
            print(f"  [LB {who} {d['fac']}] tile={d['tile']} d_shad={d['d_shad']} "
                  f"avec={d['avec']} sans={d['sans']}")

        # verdicts
        errs = []
        if bad:
            errs.append(f"(A) {len(bad)}/{len(all_rows)} lignes offline != oracle")
        # (B) pas de sur-application : toute divergence in-range
        over = [d for d in diverging
                if not (d["d_shad"] == 1 or (d["d_shad"] == 2 and d["fac"] == "Tau"))]
        if over:
            errs.append(f"(B) {len(over)} divergences HORS portee (aura sur-appliquee): "
                        + ", ".join(f"u{d['att']}{d['fac']}@d{d['d_shad']}" for d in over[:6]))
        # (C) load-bearing existe dans chaque categorie
        has_adj = any(d["d_shad"] == 1 for d in diverging)
        has_tau2 = any(d["d_shad"] == 2 and d["fac"] == "Tau" for d in diverging)
        sygex_ring2 = [d for d in diverging if d["att"] == sygex and d["d_shad"] >= 2]
        if not has_adj:
            errs.append("(C) tier ADJACENT non demontre (aucune divergence a d_shad==1)")
        if not has_tau2:
            errs.append("(C) tier T'au range-2 non demontre (aucune divergence Tau a d_shad==2)")
        if sygex_ring2:
            errs.append(f"(C) NON-Tau BOOSTE au ring-2 (gate faction KO): "
                        + ", ".join(f"@d{d['d_shad']}" for d in sygex_ring2[:6]))

        print(f"[220] resume: rows={len(all_rows)} miss={len(bad)} lb={len(diverging)} "
              f"adj={has_adj} tau2={has_tau2} sygex_ring2={len(sygex_ring2)}")
        if errs:
            print("[220] ECHEC:\n  - " + "\n  - ".join(errs)); return 1
        print(f"[220] OK : {len(all_rows)} lignes agreement 100% (TOL {TOL}) ; aura load-bearing "
              f"discriminante (adjacent + T'au range-2 ; non-Tau exclu au ring-2)")
        return 0
    finally:
        try:
            _r(sid, "disposeRunner", {"runnerId": rid}, 15)
            print(f"[220] runner {rid} dispose")
        except Exception as e:
            print(f"[220] dispose KO: {e}")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
