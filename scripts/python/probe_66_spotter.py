#!/usr/bin/env python
"""Probe #66 — agreement PREDICTION per-tuile : aura alliee SpotterReworked (Thaddeus).

Design CARRIERS COTE JOUEUR (drive-positions) : p-units = admecDestroyer (Sy-gex, HeavyWeapon
+ arme ranged 4h Physical R3) + darkaTerminator (Baraqiel, HeavyWeapon SANS arme ranged, melee
3h Power) + astraOrdnance (Thaddeus, porteur SpotterReworked). a-unit cible = bloodSanguinary
(traits Hero/Healer/RapidAssault : HeavyGravCannon de Sy-gex INERTE — gate Mechanical/Terminator/
Gravis faux). A CHAQUE debut de MON tour (unites non bougees), decisionView maxRank 99 emet les
plans multi-tuiles de MES unites vs la cible -> oracle natif ranked[] per-tuile, confronte a
make_normal_attack_predictions (TOL 3). Puis parking greedy (Thaddeus ~2 hexes de la cible,
Sy-gex ~3, Baraqiel au contact) + aiturn.

Couverture visee (variante HW extraDmg_2 + gates — la variante extraDmg non-HW est deja validee
par probe_62_campred 24/24, ligne u77 (4,3) +748) :
  - sygex_in  : tuile candidate a <=2 hexes de Thaddeus -> natif +extraDmg_2 (trigger SANS
                IsRangedAttack IdunBattle.Entities.Effects.Loki.SpotterReworked_HeavyWeaponEffect$$CreateEffectDamageBonusForAttack : tuiles melee INCLUSES) ;
  - sygex_out : tuile a >2 hexes -> pas de bonus (rayon ConfigConst 0x16=2) ;
  - barq_in   : Baraqiel (HW melee-only, AUCUNE arme ranged) a <=2 hexes -> +extraDmg_2 AUSSI :
                MESURE (run 1, 2 lignes +1194/1197 = 3x ~399) puis RE — `IdunBattleLogic.Entities.DSLSelectors$$UnitsWithRangedAttacks` = UNION UnitsWithWeaponsSelector(2) + TilesOnSameElevationSelector
                (ref porteur, |delta elev|<=2 via IdunBattle.Entities.TileExtensions$$GetElevationDifference) -> sur
                MC1_67 (elev 3-4) le noeud est un pass-through. Le port mirrore l'union ;
  - thad self : Thaddeus lui-meme -> pas d'aura (SurroundingFriends exclut le porteur).
Counterfactuel : create_aura des DEUX classes patche -> None ; les lignes qui divergent doivent
etre EXACTEMENT les {sygex,barq} a d_thad<=2 (aura load-bearing, rayon respecte).

Known-flags : Deathwing (Baraqiel, on-block +146 melee, non porte) — si l'effet apparait dans
ses decisionView.effects apres un block, ses lignes du round sont EXCLUES (loggees). IndirectFire
(Thaddeus) : residuel #182 = Trench only, absent de MC1_67.

ASCII only (cp1252). Usage: python probe_66_spotter.py [--seed 66001] [--max-rounds 8]
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
from engine.entities.effects.loki.extra_damage_aura import (  # noqa: E402
    SpotterReworkedExtraDamageEffect, SpotterReworkedHeavyWeaponEffect)

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
STATE = ROOT / "logs" / "runners" / "_66_spotter_state.json"
TOL = 3
P_UNITS = "admecDestroyer,darkaTerminator,astraOrdnance"
A_UNITS = "bloodSanguinary"
W, H = 7, 9                     # bornes MC1_67 (les moves illegaux sont rejetes par le RPC)
MV = {"admecDestroyer": 2, "darkaTerminator": 2, "astraOrdnance": 3}


def _r(sid: int, method: str, body: dict, t: float = 90) -> dict:
    return (_rpc(sid, method, [body], timeout=t).get("result") or {})


def build(seed: int) -> int:
    STATE.unlink(missing_ok=True)
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
         "--state-file", str(STATE), "--board", "MC1_67",
         "--p-units", P_UNITS, "--a-units", A_UNITS,
         "--hp-player", "30000"],   # mes carriers encaissent les tours d'approche de la cible
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not STATE.exists():
        print(f"[66] build KO: {(proc.stderr or proc.stdout or '')[-400:]}", file=sys.stderr)
        sys.exit(2)
    return json.loads(STATE.read_text())["runnerId"]


def _units_by_vis(dv: dict) -> dict:
    return {u.get("visualId"): u for u in (dv.get("units") or []) if u.get("alive")}


def _pos(u: dict) -> tuple:
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row"))


def _collect_rows(dec: dict, predictor: dict, scene, att_ids: set, tgt_id: int,
                  thad_pos: tuple) -> list[dict]:
    """Lignes (att, tile, oracle, offline, d_thad) des attaques NORMALES rankees vs la cible."""
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
                if rk.get("dmgMax") is None:
                    continue
                tile = ((rk["col"], rk["row"]) if rk.get("col") is not None else None)
                if tile is None:
                    continue
                ev_off = prediction.make_normal_attack_predictions(scene, a_id, tgt_id, tile)
                res = ev_off.prediction.accurate_health_damage
                rows.append({"att": a_id, "tile": tile, "ab": ev.get("abilityId"),
                             "d_thad": hexgeo.distance(tile, thad_pos),
                             "opt": bool(rk.get("predOptimistic")),
                             "oracle": (rk.get("dmgMin"), rk.get("dmgMax")),
                             "offline": (res.min, res.max)})
    return rows


def _agree(r: dict) -> bool:
    return max(abs(r["oracle"][0] - r["offline"][0]),
               abs(r["oracle"][1] - r["offline"][1])) <= TOL


def _park(rpc, rid, uid, vis, cur, goal, occupied) -> tuple:
    """Move greedy vers goal (trial des tuiles de la portee mv triees par dist au goal) + finish.
    Un move rejete par le runner n'est pas consomme -> on essaie la candidate suivante."""
    cands = [t for t in hexgeo.disk(cur[0], cur[1], MV.get(vis, 2))
             if 0 <= t[0] < W and 0 <= t[1] < H and t not in occupied and t != cur]
    cands.sort(key=lambda t: (hexgeo.distance(t, goal), hexgeo.distance(t, cur)))
    newpos = cur
    for t in cands[:12]:
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


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=66001)
    ap.add_argument("--max-rounds", type=int, default=8)
    args = ap.parse_args(argv)
    sid = _resolve_session()
    rid = build(args.seed)
    rpc = lambda m, b, t=90: _r(sid, m, b, t)   # noqa: E731
    print(f"[66] seed={args.seed} runner={rid}")
    try:
        dv0 = rpc("decisionView", {"runnerId": rid, "maxRank": 1}, 60)
        byvis = _units_by_vis(dv0)
        need = ("admecDestroyer", "darkaTerminator", "astraOrdnance", "bloodSanguinary")
        if any(v not in byvis for v in need):
            print(f"[66] roster KO (vis presents: {sorted(byvis)})"); return 2
        ids = {v: byvis[v]["id"] for v in need}
        sygex, barq, thad, sang = (ids["admecDestroyer"], ids["darkaTerminator"],
                                   ids["astraOrdnance"], ids["bloodSanguinary"])
        thad_eff0 = [e.get("name") for e in (byvis["astraOrdnance"].get("effects") or [])]
        print(f"[66] sygex=u{sygex} barq=u{barq} thad=u{thad} sang=u{sang} "
              f"cp={dv0.get('currentPlayer')} thadEff={thad_eff0}")

        all_rows, cf_pairs, barq_excl = [], [], 0
        for rnd in range(args.max_rounds):
            dec = rpc("decisionView", {"runnerId": rid, "maxRank": 99,
                                       "allAbilities": True}, 120)
            byvis = _units_by_vis(dec)
            if any(v not in byvis for v in need):
                print(f"[66] unite perdue round {rnd} (vis: {sorted(byvis)}) -> stop"); break
            tp = _pos(byvis["astraOrdnance"])
            barq_eff = [e.get("name") for e in (byvis["darkaTerminator"].get("effects") or [])]
            deathwing = any("Deathwing" in (n or "") for n in barq_eff)
            predictor = SC.build_predictor(rpc, rid)
            if predictor is None:
                print("[66] combatSnapshot KO"); return 2
            sctx = SC.step_context(predictor, dec)
            scene = Scene.from_predictor_sctx(predictor, sctx, None)
            att_ids = {sygex, thad} | (set() if deathwing else {barq})
            if deathwing:
                barq_excl += 1
            rows = _collect_rows(dec, predictor, scene, att_ids, sang, tp)
            for x in rows:
                x["rnd"] = rnd
            all_rows += rows
            if rows:
                cf_pairs.append((dec, predictor, scene, tp, att_ids))
            cov = {
                "sygex_in": sum(1 for x in all_rows if x["att"] == sygex and x["d_thad"] <= 2),
                "sygex_out": sum(1 for x in all_rows if x["att"] == sygex and x["d_thad"] > 2),
                "barq_in": sum(1 for x in all_rows if x["att"] == barq and x["d_thad"] <= 2),
                "thad": sum(1 for x in all_rows if x["att"] == thad),
            }
            print(f"[66] round {rnd}: thad@{tp} rows=+{len(rows)} cov={cov}"
                  + (" [barq EXCLU: Deathwing]" if deathwing else ""))
            if cov["sygex_in"] and cov["sygex_out"] and cov["barq_in"] and cov["thad"]:
                break
            # parking : Thaddeus a 2 hexes de la cible, Sy-gex a 3, Baraqiel au contact
            sp = _pos(byvis["bloodSanguinary"])
            occ = {_pos(byvis[v]) for v in need}
            for vis, uid, rad in (("astraOrdnance", thad, 2),
                                  ("admecDestroyer", sygex, 3),
                                  ("darkaTerminator", barq, 1)):
                cur = _pos(byvis[vis])
                ring = [t for t in hexgeo.ring(sp[0], sp[1], rad)
                        if 0 <= t[0] < W and 0 <= t[1] < H]
                goal = min(ring, key=lambda t: hexgeo.distance(t, cur)) if ring else sp
                occ.discard(cur)
                np_ = _park(rpc, rid, uid, vis, cur, goal, occ)
                occ.add(np_)
            subprocess.run([sys.executable, "rl_duel.py", "aiturn",
                            "--state-file", str(STATE)], cwd=str(PYDIR),
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        if not all_rows:
            print("[66] AUCUNE ligne rankee -> scenario KO"); return 3

        # (1) agrement offline == oracle natif
        bad = []
        for x in all_rows:
            who = ("sygex" if x["att"] == sygex else "barq" if x["att"] == barq else "thad")
            ok = _agree(x)
            if not ok:
                bad.append(x)
            print(f"  [{who}] r{x['rnd']} tile={x['tile']} d_thad={x['d_thad']} "
                  f"ab={x['ab']} oracle={x['oracle']} offline={x['offline']} "
                  f"opt={int(x['opt'])} {'OK' if ok else '** MISS **'}")

        # (2) counterfactuel : auras Spotter OFF -> divergent EXACTEMENT les lignes ou
        # l'offline appliquait le bonus (attendu : {sygex,barq} a d_thad<=2 ; thad/out stables).
        cf_diverg = []
        with mock.patch.object(SpotterReworkedExtraDamageEffect,
                               "create_aura_attack_damage_bonus_for_ally",
                               lambda self, ctx=None: None), \
             mock.patch.object(SpotterReworkedHeavyWeaponEffect,
                               "create_aura_attack_damage_bonus_for_ally",
                               lambda self, ctx=None: None):
            for _dec, _pred, _scene, _tp, _atts in cf_pairs:
                for x in _collect_rows(_dec, _pred, _scene, _atts, sang, _tp):
                    if not _agree(x):
                        cf_diverg.append(x)
        n_in = sum(1 for x in all_rows if x["att"] != thad and x["d_thad"] <= 2)
        cf_in = sum(1 for x in cf_diverg if x["att"] != thad and x["d_thad"] <= 2)
        cf_autres = len(cf_diverg) - cf_in
        print(f"[66] counterfactuel aura-OFF : {len(cf_diverg)} lignes divergent "
              f"(in-rayon={cf_in}/{n_in} attendues, autres={cf_autres} attendu 0)")
        if barq_excl:
            print(f"[66] note : lignes Baraqiel EXCLUES sur {barq_excl} round(s) (Deathwing)")

        if bad:
            print(f"[66] ECHEC : {len(bad)}/{len(all_rows)} lignes en miss"); return 1
        if n_in and not cf_in:
            print("[66] /!\\ counterfactuel NON discriminant (aura jamais load-bearing)")
            return 4
        if cf_autres:
            print("[66] /!\\ counterfactuel : divergences HORS rayon (aura appliquee a tort)")
            return 4
        print(f"[66] OK : {len(all_rows)} lignes = agreement 100% (TOL {TOL}), "
              f"counterfactuel discriminant ({cf_in} lignes portees par l'aura)")
        return 0
    finally:
        try:
            _r(sid, "disposeRunner", {"runnerId": rid}, 15)
            print(f"[66] runner {rid} dispose")
        except Exception as e:
            print(f"[66] dispose KO: {e}")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
