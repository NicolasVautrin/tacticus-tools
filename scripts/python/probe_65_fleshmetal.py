#!/usr/bin/env python
"""Probe #65 — agreement PREDICTION per-tuile : canal additional-hits FleshmetalGuns (Volk).

Design : p-unit = blackObliterator (Volk, melee 4h Power / ranged 6h HeavyRound R3, MV 2)
SEUL cote joueur (drive-positions), a-unit cible = bloodSanguinary (cible propre validee #66 :
non-Mechanical, pas d'hex-effect, pas de reduction defensive). --hp-player 30000 pour encaisser
>=3 rounds. Le CYCLE est natif (`IdunBattleLogic.Entities.Abilities.Active.Loki.FleshMetalGunsAbility$$CreateBehaviour` :
UnitTurnsStarted % 3 == 1/2/0 -> AddEffect FocusedMalice 0x42b / RuinousSalvo 0x4bc / WarpHail
0x4c5) — la branche offline attendue est cle sur l'effet OBSERVE dans decisionView.effects de
Volk, le cycle observe est logge pour confirmation.

A CHAQUE debut de MON tour : decisionView maxRank 99 -> rows normal-attack rankees de Volk vs
la cible, confrontees a make_normal_attack_predictions (TOL 3). Parking ring-3 de la cible ->
les tuiles candidates couvrent dist 1 (melee) a 5 (ranged).

Couverture visee (x3 branches Melta/Flame/HeavyRound) :
  - ranged (d_tgt>1)  : natif +nrOfHits{,_2,_3}=2 coups PREDEFINED [minDmg,maxDmg]{,_2,_3}
                        (IdunBattle.Entities.Effects.Loki.BaseFleshmetalGunsEffect$$CreateAdditionalHits, trigger OwnerIsCaster & IsRangedAttack) ;
  - melee  (d_tgt==1) : PAS de groupe (gate IsRangedAttack).
Counterfactuel : additional_hit_groups de la BASE patche -> None ; divergent EXACTEMENT les
rows ranged des rounds a effet present (groupes load-bearing), les rows melee restent stables.

Known-flags : LetTheGalaxyBurn (chance% extra hit) = contribution native 0 tant que la cible
n'est PAS sur un hex-effect (prouve #62 : delta Volk = exactement 2x Melta) — on n'attaque
jamais, aucun Despoiled Ground n'est pose. FrenziedFiring jamais caste (rows normal-attack
only). HeavyWeapon (not-moved +dmg%) deja gere offline (probe #66 45/45).

ASCII only (cp1252). Usage: python probe_65_fleshmetal.py [--seed 65001] [--max-rounds 9]
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
from engine.entities.effects.loki.hits import _BaseFleshmetalGunsEffect  # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
STATE = ROOT / "data" / "_65_fleshmetal_state.json"
TOL = 3
P_UNITS = "blackObliterator"
A_UNITS = "bloodSanguinary"
W, H = 7, 9                     # bornes MC1_67
MV_VOLK = 2
FMG_EFFECTS = ("FleshmetalGunsFocusedMalice", "FleshmetalGunsRuinousSalvo",
               "FleshmetalGunsWarpHail")


def _r(sid: int, method: str, body: dict, t: float = 90) -> dict:
    return (_rpc(sid, method, [body], timeout=t).get("result") or {})


def build(seed: int) -> int:
    STATE.unlink(missing_ok=True)
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
         "--state-file", str(STATE), "--board", "MC1_67",
         "--p-units", P_UNITS, "--a-units", A_UNITS,
         "--hp-player", "30000"],   # Volk encaisse les tours de la cible
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not STATE.exists():
        print(f"[65] build KO: {(proc.stderr or proc.stdout or '')[-400:]}", file=sys.stderr)
        sys.exit(2)
    return json.loads(STATE.read_text())["runnerId"]


def _units_by_vis(dv: dict) -> dict:
    return {u.get("visualId"): u for u in (dv.get("units") or []) if u.get("alive")}


def _pos(u: dict) -> tuple:
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row"))


def _collect_rows(dec: dict, predictor: dict, scene, att_id: int, tgt_id: int,
                  tgt_pos: tuple, branch: str) -> list[dict]:
    """Rows (tile, oracle, offline, d_tgt, branch) des attaques NORMALES rankees vs la cible."""
    rows = []
    for ap in (dec.get("attackPlans") or []):
        if ap.get("unitId") != att_id or att_id not in predictor["ctx_by_id"]:
            continue
        norm_ids = {ab.get("id") for u in (dec.get("units") or []) if u.get("id") == att_id
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
                ev_off = prediction.make_normal_attack_predictions(scene, att_id, tgt_id, tile)
                res = ev_off.prediction.accurate_health_damage
                rows.append({"tile": tile, "ab": ev.get("abilityId"),
                             "d_tgt": hexgeo.distance(tile, tgt_pos),
                             "branch": branch,
                             "opt": bool(rk.get("predOptimistic")),
                             "oracle": (rk.get("dmgMin"), rk.get("dmgMax")),
                             "offline": (res.min, res.max)})
    return rows


def _agree(r: dict) -> bool:
    return max(abs(r["oracle"][0] - r["offline"][0]),
               abs(r["oracle"][1] - r["offline"][1])) <= TOL


def _park(rpc, rid, uid, cur, goal, occupied) -> tuple:
    """Move greedy vers goal (trial des tuiles triees par dist au goal) + finish."""
    cands = [t for t in hexgeo.disk(cur[0], cur[1], MV_VOLK)
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
    ap.add_argument("--seed", type=int, default=65001)
    ap.add_argument("--max-rounds", type=int, default=9)
    args = ap.parse_args(argv)
    sid = _resolve_session()
    rid = build(args.seed)
    rpc = lambda m, b, t=90: _r(sid, m, b, t)   # noqa: E731
    print(f"[65] seed={args.seed} runner={rid}")
    try:
        dv0 = rpc("decisionView", {"runnerId": rid, "maxRank": 1}, 60)
        byvis = _units_by_vis(dv0)
        if any(v not in byvis for v in ("blackObliterator", "bloodSanguinary")):
            print(f"[65] roster KO (vis presents: {sorted(byvis)})"); return 2
        volk = byvis["blackObliterator"]["id"]
        sang = byvis["bloodSanguinary"]["id"]
        print(f"[65] volk=u{volk} sang=u{sang} cp={dv0.get('currentPlayer')}")

        all_rows, cf_pairs, cycle = [], [], []
        for rnd in range(args.max_rounds):
            dec = rpc("decisionView", {"runnerId": rid, "maxRank": 99,
                                       "allAbilities": True}, 120)
            byvis = _units_by_vis(dec)
            if any(v not in byvis for v in ("blackObliterator", "bloodSanguinary")):
                print(f"[65] unite perdue round {rnd} (vis: {sorted(byvis)}) -> stop"); break
            volk_eff = [e.get("name") for e in (byvis["blackObliterator"].get("effects") or [])]
            fmg = [n for n in volk_eff if n in FMG_EFFECTS]
            branch = fmg[0] if fmg else "<none>"
            cycle.append(branch)
            sp = _pos(byvis["bloodSanguinary"])
            predictor = SC.build_predictor(rpc, rid)
            if predictor is None:
                print("[65] combatSnapshot KO"); return 2
            sctx = SC.step_context(predictor, dec)
            scene = Scene.from_predictor_sctx(predictor, sctx, None)
            rows = _collect_rows(dec, predictor, scene, volk, sang, sp, branch)
            for x in rows:
                x["rnd"] = rnd
            all_rows += rows
            if rows:
                cf_pairs.append((dec, predictor, scene, sp, branch, rows))
            cov = {}
            for b in FMG_EFFECTS:
                cov[b[13:] + "_rng"] = sum(1 for x in all_rows
                                           if x["branch"] == b and x["d_tgt"] > 1)
                cov[b[13:] + "_mel"] = sum(1 for x in all_rows
                                           if x["branch"] == b and x["d_tgt"] == 1)
            print(f"[65] round {rnd}: branch={branch} volkEff={volk_eff} rows=+{len(rows)} "
                  f"cov={cov}")
            if all(cov[b[13:] + "_rng"] for b in FMG_EFFECTS) \
                    and any(cov[b[13:] + "_mel"] for b in FMG_EFFECTS):
                break
            # parking ring-3 de la cible -> candidates dist 1..5 au prochain round
            cur = _pos(byvis["blackObliterator"])
            ring = [t for t in hexgeo.ring(sp[0], sp[1], 3)
                    if 0 <= t[0] < W and 0 <= t[1] < H]
            goal = min(ring, key=lambda t: hexgeo.distance(t, cur)) if ring else sp
            _park(rpc, rid, volk, cur, goal, {sp})
            subprocess.run([sys.executable, "rl_duel.py", "aiturn",
                            "--state-file", str(STATE)], cwd=str(PYDIR),
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        if not all_rows:
            print("[65] AUCUNE ligne rankee -> scenario KO"); return 3
        print(f"[65] cycle observe: {cycle} (attendu FocusedMalice -> RuinousSalvo -> WarpHail"
              f" -> repete)")

        # (1) agrement offline == oracle natif
        bad = []
        for x in all_rows:
            ok = _agree(x)
            if not ok:
                bad.append(x)
            print(f"  r{x['rnd']} [{x['branch'][13:] or x['branch']}] tile={x['tile']} "
                  f"d_tgt={x['d_tgt']} ab={x['ab']} oracle={x['oracle']} "
                  f"offline={x['offline']} opt={int(x['opt'])} {'OK' if ok else '** MISS **'}")

        # (2) counterfactuel : groupes OFF. Classement par APPLICATION REELLE (offline change
        # entre orig et cf — l'arme choisie peut etre ranged meme a d_tgt=1, ex. melee bloquee
        # par l'elevation) : toute row APPLIQUEE doit diverger de l'oracle (load-bearing), toute
        # row NON appliquee doit rester stable.
        n_applied = n_applied_ok = n_stable_bad = 0
        with mock.patch.object(_BaseFleshmetalGunsEffect, "additional_hit_groups",
                               lambda self, ctx=None: None):
            for _dec, _pred, _scene, _sp, _branch, _orig in cf_pairs:
                cf_rows = _collect_rows(_dec, _pred, _scene, volk, sang, _sp, _branch)
                for o, c in zip(_orig, cf_rows):
                    applied = (c["offline"] != o["offline"])
                    if applied:
                        n_applied += 1
                        if not _agree(c):
                            n_applied_ok += 1
                    elif not _agree(c):
                        n_stable_bad += 1
        print(f"[65] counterfactuel groupes-OFF : appliquees={n_applied} "
              f"(divergent {n_applied_ok}/{n_applied} attendu tout), "
              f"non-appliquees divergentes={n_stable_bad} (attendu 0)")

        if bad:
            print(f"[65] ECHEC : {len(bad)}/{len(all_rows)} rows en miss"); return 1
        if not n_applied or n_applied_ok != n_applied:
            print("[65] /!\\ counterfactuel NON discriminant (groupes pas load-bearing partout)")
            return 4
        if n_stable_bad:
            print("[65] /!\\ counterfactuel : rows sans groupe destabilisees")
            return 4
        print(f"[65] OK : {len(all_rows)} rows = agreement 100% (TOL {TOL}), "
              f"counterfactuel discriminant ({n_applied} rows portees par les groupes)")
        return 0
    finally:
        try:
            _r(sid, "disposeRunner", {"runnerId": rid}, 15)
            print(f"[65] runner {rid} dispose")
        except Exception as e:
            print(f"[65] dispose KO: {e}")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
