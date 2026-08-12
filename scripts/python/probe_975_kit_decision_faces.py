"""#975 -- confrontation LIVE des CINQ faces DECISION du lot AdeptusMechanicus / Votann / T'au.

Oppose, ability par ability, l'ORACLE NATIF (`ncEvaluate` -- invoque le wrapper `Evaluate(unit,
UnitPosition)` du playbook NATIF et rend, PAR POSITION candidate, l'utilite `best` du Bucket) au
PORT (`engine.playbook.noncomparable.PLAYBOOKS[<id>].generate_candidates`, monte sur un `NCContext`
bati par le chemin de PRODUCTION `engine.ai.context.build`).

L'etat est CONSTRUIT, pas subi : `--place` / `--a-place` posent les dix unites sur des tuiles
exactes (le natif `AddUnitOperation$$Execute` n'exige pas qu'elles appartiennent au SpawnPointSet).

Deux montages :
  * `--montage A` -- le regime NOMINAL : deux ennemis alignes devant le Dominus, deux ennemis
    ADJACENTS au Beserk (le gate `1 < targets.Count` de 1221 PASSE), une cible a portee du
    Destroyer et de l'Ironmaster.
  * `--montage B` -- la CONTRE-EPREUVE du gate de 1221 : UN SEUL ennemi adjacent au Beserk. Le
    natif doit rendre un bucket VIDE la ou le montage A rend une utilite.

Usage (depuis `scripts/python`, session Frida deja warmee) :

    python probe_975_kit_decision_faces.py --state-file <ABSOLU sous logs/>.json [--montage A|B]
                                           [--only <abilityId>] [--keep]

PROBE (mesure), pas test : il imprime, il n'assertionne pas. ASCII only (cp1252).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

from rl_collect_batch import _resolve_session, _rpc, _http   # noqa: E402

BOARD = "MC1_67"
CARRIERS = {
    1139: ("SentinelDirectives", "admecDestroyer"),
    1116: ("RadBombardment", "admecDominus"),
    1206: ("GravitonRifle", "votanIronmaster"),
    1221: ("AugmentedAssault", "votanBeserk"),
    1087: ("ExemplarOfTheKauyon", "tauShadowsun"),
}
P_UNITS = "admecDominus,admecDestroyer,votanIronmaster,votanBeserk,tauShadowsun"
A_UNITS = "necroWarden,orksNob,tauCrisis,necroDestroyer,necroSpyder"

#: Placements EXACTS. Ligne du Dominus : (1,3) -> aim (2,3) -> (3,3) = DEUX ennemis alignes.
#: Beserk (4,5) : voisins (3,5),(3,6),(4,4),(4,6),(5,5),(5,6) -- montage A y met DEUX ennemis.
PLACES = {
    "A": {
        "p": {"admecDominus": (1, 3), "admecDestroyer": (1, 6), "votanIronmaster": (5, 2),
              "votanBeserk": (4, 5), "tauShadowsun": (0, 1)},
        "a": {"necroWarden": (2, 3), "orksNob": (3, 3), "tauCrisis": (3, 6),
              "necroDestroyer": (4, 4), "necroSpyder": (5, 5)},
    },
    "B": {   # contre-epreuve du gate `1 < targets.Count` de 1221 : UN SEUL adjacent au Beserk
        "p": {"admecDominus": (1, 3), "admecDestroyer": (1, 6), "votanIronmaster": (5, 2),
              "votanBeserk": (4, 5), "tauShadowsun": (0, 1)},
        "a": {"necroWarden": (2, 3), "orksNob": (3, 3), "tauCrisis": (3, 6),
              "necroDestroyer": (4, 4), "necroSpyder": (6, 1)},
    },
}


def _r(sid, rid, method, body=None, timeout=120):
    b = {"runnerId": rid}
    b.update(body or {})
    return (_rpc(sid, method, [b], timeout=timeout) or {}).get("result") or {}


def _uid(u: dict):
    for k in ("squadId", "id", "unitId", "entityId"):
        if u.get(k) is not None:
            return u[k]
    return None


def build(state_file: Path, seed: int, montage: str, seed_bc: Path) -> int:
    state_file.unlink(missing_ok=True)
    spec = PLACES[montage]
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
           "--board", BOARD, "--rank", "17", "--seed-bc", str(seed_bc),
           "--state-file", str(state_file),
           "--p-units", P_UNITS, "--a-units", A_UNITS, "--no-ai"]
    for uid, (c, r) in spec["p"].items():
        cmd += ["--place", "%s:%d,%d" % (uid, c, r)]
    for uid, (c, r) in spec["a"].items():
        cmd += ["--a-place", "%s:%d,%d" % (uid, c, r)]
    proc = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not state_file.exists():
        raise RuntimeError("build KO : %s" % ((proc.stderr or proc.stdout or "")[-1200:]))
    return int(json.loads(state_file.read_text(encoding="utf-8"))["runnerId"])


def port_context(sid: int, rid: int, cid: int, dv: dict):
    """`NCContext` par le chemin de PRODUCTION (`engine.ai.context.build`), avec les MEMES champs
    que le foyer `engine.ai.action_generators.NonComparableGenerator.generate` -- y compris
    `is_wall_by_pos`, `is_in_fog_by_pos` et `current_player`, que les probes anterieurs oubliaient."""
    from engine import weights as W
    from engine.ai import context as AICTX
    from engine.playbook import scene as _scene
    from engine.playbook import noncomparable as NC

    rpc2 = lambda m, b, t=60: _r(sid, rid, m, b, t)                     # noqa: E731
    mov = _r(sid, rid, "aiMovableTiles", {}, 60)
    mov_by_unit = {u.get("unitId"): u for u in ((mov or {}).get("units") or [])}
    ctx = AICTX.build(rpc2, rid, dv, mov_by_unit, int(cid), W.load(),
                      _scene.build_predictor(rpc2, rid))
    return NC.NCContext(
        uid=ctx.uid, origin=ctx.origin, reach_nc=ctx.reach_nc, epos=ctx.epos, fpos=ctx.fpos,
        enemies=ctx.enemies, neigh_by_pos=ctx.neigh_by_pos, walkable_by_pos=ctx.walkable_by_pos,
        plan=ctx.plans.get(ctx.uid) or {}, plans=ctx.plans, hp_cur_by_id=ctx.hp_cur_by_id,
        elev_by_pos=ctx.elev_by_pos, ability_targets=ctx.ability_targets, wt=ctx.wt,
        is_temporary_by_pos=ctx.is_temporary_by_pos, effects_by_pos=ctx.effects_by_pos,
        obs_units=ctx.obs_units, tile_id_by_pos=ctx.tile_id_by_pos,
        active_levels=ctx.active_ability_levels, ability_config=ctx.heal_config,
        units=ctx.units, cast_from_tiles=ctx.cast_from_tiles, scene=ctx.scene,
        is_wall_by_pos=getattr(ctx, "is_wall_by_pos", {}) or {},
        is_in_fog_by_pos=getattr(ctx, "is_in_fog_by_pos", {}) or {},
        current_player=getattr(ctx, "cur", None), debug=False)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True)
    ap.add_argument("--seed-bc", required=True)
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--montage", default="A", choices=sorted(PLACES))
    ap.add_argument("--only", type=int, default=None)
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()

    sid = _resolve_session()
    sf = Path(a.state_file)
    rid = build(sf, a.seed, a.montage, Path(a.seed_bc))
    print("[975] montage=%s runner=%d session=%d board=%s seed=%d"
          % (a.montage, rid, sid, BOARD, a.seed))
    try:
        obs = _r(sid, rid, "observeBattle", {}, 60)
        units = obs.get("units") or []
        by_vis = {}
        for u in units:
            by_vis.setdefault(u.get("visualId"), []).append(u)
        for u in units:
            print("   u%-5s %-18s team=%s pos=(%s,%s) hp=%s"
                  % (_uid(u), u.get("visualId"), u.get("teamId"), u.get("col"), u.get("row"),
                     u.get("hp")))
        dv = _r(sid, rid, "decisionView", {"allAbilities": True, "maxRank": 32}, 240)

        for aid in (1139, 1116, 1206, 1221, 1087):
            if a.only is not None and aid != a.only:
                continue
            name, carrier = CARRIERS[aid]
            rows = by_vis.get(carrier) or []
            if not rows:
                print("[975] %-20s (%d) : porteur ABSENT" % (name, aid))
                continue
            cid = int(_uid(rows[0]))
            print("\n=== %s (%d) -- u%d [%s] ===" % (name, aid, cid, carrier))

            nat = _r(sid, rid, "ncEvaluate",
                     {"unitId": cid, "abilityType": aid, "sweep": True}, 240)
            pos = nat.get("positions") or []
            nz = [p for p in pos if p.get("util") is not None]
            print("  NATIF  playbook=%s eval=%s positions=%d non-vides=%d"
                  % (nat.get("playbookClass"), nat.get("evalName"), len(pos), len(nz)))
            for p in pos[:8]:
                print("     nat pos=%s cur=%s bucket=%s util=%s"
                      % (p.get("pos"), p.get("cur"), p.get("bucket"), p.get("util")))
            if nz:
                best = max(nz, key=lambda p: p["util"])
                print("  NATIF  best = pos %s util %.6f" % (best["pos"], best["util"]))

            try:
                nc = port_context(sid, rid, cid, dv)
                from engine.playbook import noncomparable as NC
                pb = NC.PLAYBOOKS.get(aid)
                ge = pb.should_evaluate(nc)
                cands = pb.generate_candidates(nc) if ge else []
                print("  PORT   should_evaluate=%s candidats=%s" % (ge, cands))
                print("  PORT   origin=%s reach=%d epos=%s"
                      % (nc.origin, len(nc.reach_nc or []), nc.epos))
            except Exception as e:                                   # noqa: BLE001
                import traceback
                print("  PORT   EXCEPTION %s" % e)
                traceback.print_exc()
        return 0
    finally:
        if not a.keep:
            try:
                _r(sid, rid, "disposeRunner", {}, 30)
                print("\n[975] runner %d dispose" % rid)
            except Exception:                                        # noqa: BLE001
                print("\n[975] dispose KO (runner %d)" % rid)


if __name__ == "__main__":
    raise SystemExit(main())
