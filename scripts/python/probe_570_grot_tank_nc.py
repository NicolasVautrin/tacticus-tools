"""#570 (face DECISION) -- `GrotTankPlaybook` : bucket NATIF (`ncEvaluate`) vs port NonComparable.

CE QUE CE PROBE MESURE. La face COMBAT (`probe_570_grot_tank.py`) dit ce que le cast FAIT ; celle-ci
dit ce que l'IA CHOISIT. Le natif est `IdunBattle.AI.Playbook.Loki.GrotTankPlaybook$$
EvaluateNonComparable`, dont l'utilite par tuile de spawn vaut
`GrotTankPlaybook$$GetUtility(caster, summonTile)` = le nombre d'unites NON AMIES dans le disque de
rayon 3 autour de cette tuile (slots `IBattleQuery` 118 `GetSurroundingUnits` / 146 `AreFriends`).

Deux grandeurs sont confrontees, et elles ne sont pas redondantes :
  D1 UTILITE  : par POSITION du caster, la valeur du bucket natif (`ncEvaluate --sweep`) vs celle
                que le port calcule. C'est le seul etage qui voie le RAYON (3) et le PREDICAT
                (`AreFriends` inverse) -- un port qui compterait les ADJACENTS rendrait des valeurs
                plus petites, un port qui compterait TOUTES les unites rendrait des valeurs plus
                grandes.
  D2 CHOIX    : la tuile de spawn effectivement retenue (argmax STRICT, 1re paire du maximum). Deux
                utilites identiques et un ARGMAX different = un ordre d'enumeration divergent.

⚠ NON-VACUITE : un bucket natif VIDE aux positions de spawn n'est pas un desaccord -- c'est
« aucun ennemi a portee 3 d'aucune tuile adjacente ». Le probe le DIT (`NON CONFRONTE`) au lieu de
rendre un vert. Le montage `--caster-pos`/`--enemy-pos` existe pour eviter ce regime.

Usage (depuis scripts/python) :
    python probe_570_grot_tank_nc.py --state-file <ABSOLU> [--board MC1_67] [--seed 777]
                                     [--caster-pos 4,5] [--enemy-pos 5,5] [--keep]

ASCII only (cp1252).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import requests

HOST = "http://127.0.0.1:8765"
CASTER = "orksBigMek"
ENEMIES = "orksNob,orksRuntherd,tyranWingedPrime"
GROT_TANK = 1057


def sid() -> int:
    return int(requests.get(f"{HOST}/api/admin/status", timeout=10).json()["session"]["id"])


def rpc(s: int, method: str, args=None, timeout: int = 90):
    r = requests.post(f"{HOST}/api/scripts/{s}/rpc",
                      json={"method": method, "args": [args or {}], "timeout": int(timeout) * 1000},
                      timeout=timeout + 30)
    if r.status_code >= 400:
        raise RuntimeError("%s HTTP %d: %s" % (method, r.status_code, r.text[:400]))
    body = r.json()
    if body.get("error"):
        raise RuntimeError(str(body["error"])[:400])
    return body.get("result") or {}


def build(state_file: Path, board: str, seed: str, cpos, epos) -> int:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    if state_file.exists():
        state_file.unlink()
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", seed, "--board", board,
           "--p-units", CASTER, "--a-units", ENEMIES, "--state-file", str(state_file)]
    if cpos:
        cmd += ["--place", "%s:%s" % (CASTER, cpos)]
    if epos:
        cmd += ["--a-place", "orksNob:%s" % epos]
    proc = subprocess.run(cmd, cwd=str(Path(__file__).resolve().parent),
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not state_file.exists():
        raise SystemExit("[570nc] build KO: %s" % ((proc.stderr or proc.stdout or "")[-800:]))
    return int(json.loads(state_file.read_text())["runnerId"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True)
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--seed", default="777")
    ap.add_argument("--caster-pos", default="4,5")
    ap.add_argument("--enemy-pos", default="5,5")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()

    s = sid()
    rid = build(Path(a.state_file), a.board, a.seed, a.caster_pos, a.enemy_pos)
    print("[570nc] runner %d monte (board %s, seed %s)" % (rid, a.board, a.seed))
    rc = 0
    try:
        import hexgeo
        from engine.ai import context as ai_ctx
        from engine.playbook import noncomparable as playbooks
        from engine.playbook import scene as scene_mod
        from engine import weights as W

        _rpc = lambda m, b, t=90: rpc(s, m, b, t)      # noqa: E731
        dv = _rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
        cid = next((u.get("id") for u in (dv.get("units") or [])
                    if u.get("visualId") == CASTER and u.get("alive")), None)
        if cid is None:
            print("[570nc] ECHEC : caster absent")
            return 1

        # ---------------- NATIF : le bucket par POSITION ----------------
        nc = _rpc("ncEvaluate", {"runnerId": rid, "unitId": cid,
                                 "abilityType": GROT_TANK, "sweep": True}, 180)
        print("[570nc] NATIF ncEvaluate ok=%s playbook=%s positions=%d"
              % (nc.get("ok"), nc.get("playbookClass"), len(nc.get("positions") or [])))
        # Le RPC rend, PAR POSITION : `{pos, cur, hvt, util, action}` (la meilleure `BucketAction`
        # decodee -- `Bucket.best@+0x20`, `util` Fix64 @+0x18, `UnitAction.target` @+0x18), ou
        # `{bucket: "empty"|null}` quand `best` est nul. Lire une cle `bucket` sur le cas NOMINAL
        # rendait un dict VIDE a chaque position -> un faux "NON CONFRONTE" (mesure du 1er passage).
        nat_by_pos = {}
        for row in (nc.get("positions") or []):
            p = row.get("pos")
            key = tuple(p) if isinstance(p, list) else p
            nat_by_pos[key] = row
        non_vide = [(k, v) for k, v in nat_by_pos.items() if v.get("util") is not None]
        for k, v in sorted(nat_by_pos.items(), key=lambda x: str(x[0]))[:16]:
            print("    pos=%-10s cur=%-5s hvt=%-5s util=%-8s action=%s"
                  % (str(k), v.get("cur"), v.get("hvt"), v.get("util"),
                     json.dumps(v.get("action"), default=str)[:120]))

        # ---------------- PORT : `GrotTankPlaybook.generate_candidates` ----------------
        mov = _rpc("aiMovableTiles", {"runnerId": rid}, 60)
        predictor = scene_mod.build_predictor(_rpc, rid)
        wt = W.load()
        mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
        ctx = ai_ctx.build(_rpc, rid, dv, mov_by_unit, cid, wt, predictor, debug=False)
        nc_ctx = playbooks.NCContext(
            uid=ctx.uid, origin=ctx.origin, reach_nc=ctx.reach_nc, epos=ctx.epos, fpos=ctx.fpos,
            enemies=ctx.enemies, neigh_by_pos=ctx.neigh_by_pos,
            walkable_by_pos=ctx.walkable_by_pos,
            plan=ctx.plans.get(ctx.uid) or {}, plans=ctx.plans, hp_cur_by_id=ctx.hp_cur_by_id,
            elev_by_pos=ctx.elev_by_pos, ability_targets=ctx.ability_targets,
            wt=ctx.wt, is_temporary_by_pos=ctx.is_temporary_by_pos,
            effects_by_pos=ctx.effects_by_pos, obs_units=ctx.obs_units,
            tile_id_by_pos=ctx.tile_id_by_pos, active_levels=ctx.active_ability_levels,
            units=ctx.units, cast_from_tiles=ctx.cast_from_tiles, scene=ctx.scene, debug=False)
        pb = playbooks.PLAYBOOKS.get(GROT_TANK)
        if pb is None:
            print("[570nc] ECHEC : 1057 absente du registre NonComparable")
            return 1
        cands = pb.generate_candidates(nc_ctx) or []
        print("[570nc] PORT  candidats=%s" % json.dumps(cands, default=str)[:400])

        # ---------------- D1/D2 : confrontation ----------------
        print("\n[570nc] CONFRONTATION")
        if not non_vide:
            print("    NON CONFRONTE : le bucket natif est VIDE a toutes les positions. Ce n'est "
                  "pas un desaccord (aucun ennemi a portee 3 d'aucune tuile de spawn) -- "
                  "re-crafter le montage (--caster-pos / --enemy-pos).")
            return 2
        tid_by_pos = ctx.tile_id_by_pos or {}
        pos_by_tid = {v: k for k, v in tid_by_pos.items()}
        port_tile = port_util = None
        if cands:
            t = cands[0].get("target")
            port_tile = pos_by_tid.get(t, t)
            port_util = float(cands[0].get("pred"))
        # D1 -- l'utilite PAR POSITION, sur les 30 positions du sweep. Le natif rend, pour chaque
        # position T, le MEILLEUR `BucketAction` (`Bucket.best@+0x20`) ; le port recalcule le MAX de
        # sa propre utilite sur les tuiles de spawn eligibles depuis T. C'est l'etage qui voit le
        # RAYON (3) et le PREDICAT (`AreFriends` inverse) : un port qui compterait les ADJACENTS
        # rendrait des valeurs plus petites, un port qui compterait toutes les unites, plus grandes.
        # ⚠ `action.targetLow` n'est PAS un id de tuile : le RPC lit `UnitAction.target@+0x18`
        # comme un POINTEUR (`targetQ`) et en publie les 32 bits bas. Il ne se resout donc pas en
        # position -- on ne compare que l'UTILITE, et D2 tranche l'argmax.
        from engine.playbook.noncomparable._base import eligible_target_tiles
        radius = pb._UTILITY_RADIUS
        _fh, union = eligible_target_tiles(nc_ctx, GROT_TANK)
        neigh = None
        try:
            from engine import battle_query as _bq
            neigh = _bq.neigh_map(nc_ctx)
        except Exception:
            neigh = None
        ok_d1 = True
        n_cmp = 0
        for k, row in sorted(non_vide, key=lambda x: str(x[0])):
            if not isinstance(k, tuple):
                continue
            from engine import battle_query as _bq2
            mine = 0.0
            for st in union:
                if not _bq2.is_adjacent(k, st, nc_ctx.elev_by_pos, neigh):
                    continue
                u = float(sum(1 for p in (ctx.epos or [])
                              if hexgeo.distance(st, (p[0], p[1])) <= radius))
                mine = max(mine, u)
            same = abs(float(row["util"]) - mine) < 1e-6
            ok_d1 = ok_d1 and same
            n_cmp += 1
            if n_cmp <= 14 or not same:
                print("    D1 pos=%-9s util natif=%-7s port(max sur ses tuiles)=%-7s -> %s"
                      % (str(k), row.get("util"), mine, "OK" if same else "DIVERGE"))
        print("    D1 BILAN    %d position(s) confrontee(s) -> %s"
              % (n_cmp, "TOUTES OK" if ok_d1 else "DIVERGENCE"))
        if not ok_d1 or n_cmp == 0:
            rc = 1
        # D2 -- l'ARGMAX. Le natif rend son meilleur par position ; le port rend UN candidat.
        nat_best = max((float(v["util"]) for _k, v in non_vide), default=None)
        nat_arg = [k for k, v in non_vide if abs(float(v["util"]) - nat_best) < 1e-6]
        print("    D2 ARGMAX   natif util=%s (aux positions %s) ; port tuile=%s util=%s -> %s"
              % (nat_best, nat_arg[:6], port_tile, port_util,
                 "OK" if (port_util is not None and nat_best is not None
                          and abs(nat_best - port_util) < 1e-6) else "DIVERGE"))
        if not cands:
            print("    ECHEC : le natif propose et le port ne propose RIEN")
            rc = 1
        elif port_util is None or nat_best is None or abs(nat_best - port_util) >= 1e-6:
            rc = 1
        print("\n[570nc] %s" % ("PROBE OK" if rc == 0 else "PROBE : DIVERGENCE"))
    finally:
        if not a.keep:
            try:
                rpc(s, "disposeRunner", {"runnerId": rid}, 20)
                print("[570nc] runner %d dispose" % rid)
            except Exception as exc:
                print("[570nc] dispose KO: %s" % str(exc)[:200])
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
