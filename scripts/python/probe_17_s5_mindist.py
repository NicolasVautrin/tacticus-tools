#!/usr/bin/env python
"""#17 / case-52 -- residu `MinDist#76` du pas s5 (seed 12345) : mesure du TERME, pas de l'issue.

Le residu consigne (case-52 §#57k) disait : au pas 5 de la seed 12345, le natif rend
`MinDistanceToClosestEnemyUtility#76` = **-700** sur (0,4) ET (1,4) (tie parfait, departage
premier-gagne dans l'ordre du movable set), tandis que le port rendait **-600** sur (1,4)
(pathdist 6 au lieu de 7) -> le port bougeait en (1,4) au lieu de (0,4).

Ce probe MESURE le terme sur les DEUX faces du port, au meme etat de decision :

  * face LIVE  -- `engine.ai.context.build` : `ctx.pathdist_by_pos` vient du RPC natif
    `pathDistToEnemies` (mirror complet de `IdunBattle.AI.ActionGenerators.MovementActionGenerator.u003CFindClosestEnemyu003Ed__8$$MoveNext` :
    ClosestEnemy FIGE + filtres `!CurrentOwnerIsEnvironment` / `IsTargetable` / `!IsIrrelevantObject`
    / vivant / `GetOnlyTargets`), puis `IdunBattle.AI.Utilities.MinDistanceToClosestEnemyUtility$$GetMinDistanceToEnemy`.

  * face OFFLINE -- `engine.ai.state_bridge.build_from_state` : `_pathdist_to_enemies` calcule
    la distance par BFS, sans RPC. C'est la face que consomment les runs 100 % offline.

Sortie : par tuile candidate, `pathDist` natif (RPC) / offline (BFS) et le terme `wMin * d`
(`wMin = MinDistanceToClosestEnemy.PerTileDistance`, poids BC), plus l'ordre du movable set
(le departage du tie natif est PREMIER-GAGNE dans cet ordre).

Usage (depuis scripts/python, session Frida warmee) :
  python probe_17_s5_mindist.py --state-file <ABSOLU>.json [--seed 12345] [--board MC1_67]
                                [--steps 6] [--focus-step 5]
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rl_collect_batch import _resolve_session, _rpc  # noqa: E402
from engine import weights  # noqa: E402
from engine.ai import context as _ai_ctx  # noqa: E402
from engine.ai import state_bridge as _sb  # noqa: E402
from engine.runner.snapshot import load_state  # noqa: E402
from engine.runner.components import OwnerComponent as _OwnerComponent  # noqa: E402
from engine.entities.pathfinding.walk_pathfinder import get_reachable_levels as _levels  # noqa: E402
from engine.entities.pathfinding.board import Board as _Board  # noqa: E402
from engine.utilities.move import MIN_DIST_UTILITY  # noqa: E402
import engine_validate as EV  # noqa: E402

PYDIR = Path(__file__).resolve().parent


def _mk_rpc(sid: int):
    def rpc(method, body, timeout=60):
        r = _rpc(sid, method, [body], timeout=timeout)
        return (r.get("result") or {}) if isinstance(r, dict) else {}
    return rpc


class MinDistProbe:
    """Sonde `run_agreement` : dumpe la decomposition MinDist des pas de MOVE PUR."""

    def __init__(self, sid: int, rid: int, wt, focus_step: int | None):
        self.sid, self.rid, self.wt = sid, rid, wt
        self.focus_step = focus_step
        self.rpc = _mk_rpc(sid)
        self.rows: list = []

    def __call__(self, step, uid, dv, mov_by_unit, nat, eng, predictor):
        if not nat.get("move") or nat.get("ability"):
            return
        if self.focus_step is not None and step != self.focus_step:
            return
        nat_to = tuple(nat["move"]["to"])
        eng_to = tuple(eng["to"]) if eng.get("to") else None

        # --- NATIF : le RPC invoque Pathfinders.GetPath + les predicats de FindClosestEnemy ---
        pd = self.rpc("pathDistToEnemies", {"runnerId": self.rid, "unitId": uid}, 90)
        nat_pd = {(t["col"], t["row"]): t["pathDist"] for t in (pd.get("tiles") or [])}
        nat_enemies = pd.get("enemies") or []

        # --- face LIVE du port (ctx.build : consomme le RPC) ---
        ctx = _ai_ctx.build(self.rpc, self.rid, dv, mov_by_unit, uid, self.wt, predictor)

        # --- face OFFLINE du port (state_bridge : BFS, aucun RPC de board) ---
        obs = self.rpc("observeBattle", {"runnerId": self.rid}, 60)
        snap = self.rpc("combatSnapshot", {"runnerId": self.rid}, 60)
        off_ctx = None
        per_enemy: dict = {}
        try:
            # `board=` OBLIGATOIRE : sans lui `state.board is None` -> `_pathdist_to_enemies` rend
            # {} et la feuille retombe sur le fallback HEX (on ne mesurerait PAS la face offline).
            bg = self.rpc("boardGraph", {"runnerId": self.rid}, 90)
            tm = self.rpc("tileMeta", {"runnerId": self.rid}, 60)
            bd = _Board(bg["tiles"], adjacency="native_sym")
            state = load_state(dv, obs, snap, board=bd, tiles=tm)
            off_ctx = _sb.build_from_state(state, uid)
            # DECOMPOSITION PAR ETAGE : un BFS MONO-source par ennemi ciblable. Le natif
            # (`IdunBattle.AI.Utilities.MinDistanceToClosestEnemyUtility$$GetMinDistanceToEnemy`) ne
            # mesure QUE vers le ClosestEnemy FIGE, et rend `GetPath(...).Count` = un nombre de NOEUDS
            # (= aretes + 1). Le BFS offline rend des ARETES et prend le min sur TOUS les ennemis.
            m_oc = state.get_entity(uid).get_component(_OwnerComponent)
            my_team = m_oc.team if m_oc is not None else None
            board = state.board
            # Arete = walkable + porte d'elevation SEULE (pas d'occupance) : le natif ARRIVE sur la
            # tuile de l'ennemi (elle est la DESTINATION de `GetPath`), alors que le BFS INVERSE du
            # bridge part d'elle avec `is_valid_path_node`, qui bloque les tuiles occupees par un
            # ennemi -> les ennemis groupes se bloquent mutuellement (cf. bilan ci-dessous).
            def _free_edge(_b, a, b, _occ, _team):
                t = _b.by_id.get(b)
                if t is None or not t["walkable"]:
                    return False
                return abs(_b.elevation(b) - _b.elevation(a)) <= 1
            for e in nat_enemies:
                sid_t = board.id_at(e["col"], e["row"])
                if sid_t is None:
                    continue
                lv = _levels(board, sid_t, {}, my_team, edge=_free_edge)
                per_enemy[e["id"]] = {board.coord(t): d for t, d in lv.items()}
        except Exception as exc:                      # pragma: no cover - diagnostic
            print("  [offline] build_from_state KO: %s" % exc)

        wmin = self.wt.sub("MinDistanceToClosestEnemy", "PerTileDistance")
        order = [(t["col"], t["row"]) for t in ctx.move_tiles]
        tiles = [nat_to] + ([eng_to] if eng_to and eng_to != nat_to else [])
        for t in order:
            if t not in tiles:
                tiles.append(t)

        print("")
        print("=== step %d u%d : MOVE PUR  natif->%s  engine->%s  wMin=%s ==="
              % (step, uid, nat_to, eng_to, wmin))
        print("  RPC pathDistToEnemies: closestResolved=%s enemyCount=%s onlyTargets=%s/%s"
              % (pd.get("closestResolved"), pd.get("enemyCount"),
                 pd.get("onlyTargetsCount"), pd.get("onlyTargetsUnmatched")))
        print("  ennemis CIBLABLES retenus (post-filtres natifs): %s"
              % ([(e["id"], e["col"], e["row"]) for e in nat_enemies],))
        print("  ennemis TOUS (ctx.epos)=%s ; CIBLABLES (ctx.tgt_epos)=%s"
              % (sorted(ctx.epos), sorted(ctx.tgt_epos or [])))
        print("  ordre du movable set (departage du tie natif = PREMIER-GAGNE):")
        print("    %s" % (order,))
        print("  %-8s %-6s %-9s | %-9s %-9s | %-9s %-9s | %s"
              % ("tile", "idx", "d_natif", "d_liveport", "U_live", "d_offport", "U_off", "verdict"))
        for t in tiles:
            idx = order.index(t) if t in order else -1
            dn = nat_pd.get(t)
            # `case=` : les 4 gates d'entree de la feuille (#236) -- le terme AFFICHE doit etre
            # celui que le moteur produit, gates compris (0 quand l'un d'eux mord).
            u_live = MIN_DIST_UTILITY.evaluate_movement(
                t, ctx.tgt_epos or ctx.epos, self.wt, ctx.pathdist_by_pos,
                case=ctx.mindist_case)
            d_live = MIN_DIST_UTILITY.get_min_distance_to_enemy(
                t, ctx.tgt_epos or ctx.epos, ctx.pathdist_by_pos)
            if off_ctx is not None:
                d_off = MIN_DIST_UTILITY.get_min_distance_to_enemy(
                    t, off_ctx.tgt_epos or off_ctx.epos, off_ctx.pathdist_by_pos)
                u_off = MIN_DIST_UTILITY.evaluate_movement(
                    t, off_ctx.tgt_epos or off_ctx.epos, self.wt, off_ctx.pathdist_by_pos,
                    case=off_ctx.mindist_case)
            else:
                d_off, u_off = None, None
            ok_live = (dn is not None and dn >= 0 and d_live == dn)
            ok_off = (dn is not None and dn >= 0 and d_off == dn)
            verdict = "live=%s off=%s" % ("OK" if ok_live else "DIVERGE",
                                          "OK" if ok_off else "DIVERGE")
            print("  %-8s %-6s %-9s | %-9s %-9s | %-9s %-9s | %s"
                  % (str(t), idx, dn, d_live, u_live, d_off, u_off, verdict))
            self.rows.append({"step": step, "uid": uid, "tile": t, "idx": idx,
                              "d_nat": dn, "d_live": d_live, "u_live": u_live,
                              "d_off": d_off, "u_off": u_off,
                              "live_ok": ok_live, "off_ok": ok_off})

        if per_enemy:
            print("")
            print("  --- DECOMPOSITION de l'ecart OFFLINE : BFS MONO-source par ennemi, +1 ---")
            hdr = "  %-8s %-8s" % ("tile", "d_natif")
            for eid in per_enemy:
                hdr += " %-12s" % ("BFS(e%d)+1" % eid)
            hdr += " %-12s" % "minTous+1"
            print(hdr)
            for t in tiles:
                line = "  %-8s %-8s" % (str(t), nat_pd.get(t))
                vals = []
                for eid, m in per_enemy.items():
                    v = m.get(t)
                    v = (v + 1) if v is not None else None
                    vals.append(v)
                    line += " %-12s" % v
                ok = [v for v in vals if v is not None]
                line += " %-12s" % (min(ok) if ok else None)
                print(line)
            for eid, m in per_enemy.items():
                exact = all((m.get(t) is not None and m[t] + 1 == nat_pd.get(t)) for t in tiles
                            if nat_pd.get(t) is not None and nat_pd.get(t) >= 0)
                print("  ClosestEnemy candidat e%d : BFS+1 == d_natif sur TOUTES les tuiles ? %s"
                      % (eid, "OUI" if exact else "non"))


def main(argv: list) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="12345")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--steps", type=int, default=6)
    ap.add_argument("--focus-step", type=int, default=None)
    ap.add_argument("--state-file", required=True)
    ap.add_argument("--runner", type=int, default=None,
                    help="runner DEJA construit (pas de build ; --state-file ignore pour le build)")
    args, extra = ap.parse_known_args(argv)
    sid = _resolve_session()
    wt = weights.load()

    rid = args.runner
    if rid is None:
        state_file = Path(args.state_file)
        state_file.parent.mkdir(parents=True, exist_ok=True)
        proc = subprocess.run(
            [sys.executable, "rl_duel.py", "build", "--seed", str(args.seed),
             "--board", args.board, "--state-file", str(state_file), *extra],
            cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
        if not state_file.exists():
            print("[probe17] build KO: %s" % ((proc.stderr or proc.stdout or "")[-400:]))
            return 2
        import json
        rid = json.loads(state_file.read_text(encoding="utf-8")).get("runnerId")
    print("[probe17] session=%s runner=%s seed=%s board=%s steps=%d"
          % (sid, rid, args.seed, args.board, args.steps))

    probe = MinDistProbe(sid, rid, wt, args.focus_step)
    try:
        EV.run_agreement(sid, rid, args.steps, wt, probe=probe)
    finally:
        if args.runner is None:
            _rpc(sid, "disposeRunner", [{"runnerId": rid}], timeout=30)
            print("[probe17] runner %s dispose" % rid)

    bad_live = [r for r in probe.rows if not r["live_ok"]]
    bad_off = [r for r in probe.rows if not r["off_ok"]]
    print("")
    print("=== BILAN === tuiles mesurees=%d  face LIVE divergentes=%d  face OFFLINE divergentes=%d"
          % (len(probe.rows), len(bad_live), len(bad_off)))
    for r in bad_off:
        print("  OFFLINE %s step=%s d_nat=%s d_off=%s (U %s vs %s)"
              % (r["tile"], r["step"], r["d_nat"], r["d_off"], r["u_off"], r["u_live"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
