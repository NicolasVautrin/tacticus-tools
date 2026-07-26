"""#129 -- face DECISION de `ThriceBlessedConflagration` (1187) : le natif CASTE-t-il, et le moteur
offline rend-il la MEME ability sur la MEME cible ?

`IdunBattle.AI.Playbook.Loki.ThriceBlessedConflagrationPlaybook$$EvaluateNonComparable` existe cote
natif ; jusqu'a #129 le moteur n'avait AUCUNE feuille NonComparable pour 1187 -> l'ability ne
pouvait JAMAIS etre proposee. Ce probe monte un etat ou le natif la caste REELLEMENT (sinon la
mesure ne prouve rien : feuille absente et feuille presente donneraient le meme verdict).

Porteur : `adeptExorcist` (MoW Sisterhood). LEVIER MUNITIONS : le seed BC part a
`BC.Player.Players[*].MachineOfWarAmmo = 0` -> aucune MoW ne caste (cf. `test_storm_speeder_live`).

Oracle = `aiDryRunAllUnits` (-> `CalculateNextActionForUnit`), JAMAIS `aiPredict`.
Usage :  python probe_129_thrice_blessed_decision.py [--board C1_02] [--seed 4242] [--elev]
ASCII only.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from collections import deque
from pathlib import Path

import hexgeo
from engine import battle_query as bq
from rl_collect_batch import _rpc, _resolve_session

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
ABILITY = 1187
MOW = "adeptExorcist"


def _sid() -> int:
    return _resolve_session()


def rpc(sid, method, args, timeout=90):
    r = _rpc(sid, method, [args], timeout=timeout)
    return r.get("result", r) if isinstance(r, dict) else r


def make_bc(ammo: int = 5) -> Path:
    """Seed BC + munitions de MoW (meme levier que `test_storm_speeder_live` / #117)."""
    src = ROOT / "data" / "seed-bc.json"
    bc = json.loads(src.read_text(encoding="utf-8"))
    for _pid, p in ((bc.get("Player") or {}).get("Players") or {}).items():
        if isinstance(p, dict) and p.get("PlayerType") != 2:      # Environment exclu
            p["MachineOfWarAmmo"] = ammo
    out = ROOT / "logs" / "runners" / f"bc-129-{uuid.uuid4().hex[:8]}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(bc), encoding="utf-8")
    return out


def build(seed: str, board: str, bc: Path, p_units: str, a_units: str) -> tuple:
    state = ROOT / "logs" / "runners" / f"st-129-{uuid.uuid4().hex[:8]}.json"
    state.parent.mkdir(parents=True, exist_ok=True)
    p = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", seed, "--board", board,
         "--seed-bc", str(bc), "--state-file", str(state), "--p-units", p_units,
         "--a-units", a_units, "--p-mow", MOW, "--hp-target", "90000", "--hp-player", "90000"],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not state.exists():
        print("BUILD KO:", (p.stderr or p.stdout or "")[-600:])
        return None, state
    return json.loads(state.read_text())["runnerId"], state


# ------------------------------------------------------------------ geometrie / placement

def move_ring(p, walk, elev):
    if elev.get(p) is None:
        return []
    return [n for n in hexgeo.neighbors(p[0], p[1])
            if walk.get(n) and elev.get(n) is not None and abs(elev[n] - elev[p]) < 2]


def gated_path(src, dst, walk, elev):
    if src == dst:
        return [src]
    prev, q = {src: None}, deque([src])
    while q:
        cur = q.popleft()
        for n in move_ring(cur, walk, elev):
            if n in prev:
                continue
            prev[n] = cur
            if n == dst:
                path, x = [], n
                while x is not None:
                    path.append(x)
                    x = prev[x]
                return list(reversed(path))
            q.append(n)
    return []


def positions(sid, rid):
    dv = rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    return dv, {u["id"]: (u["pos"]["col"], u["pos"]["row"])
                for u in (dv.get("units") or []) if u.get("alive") and u.get("pos")}


def drive_to(sid, rid, walk, elev, wanted: dict, rounds: int = 14) -> bool:
    for _ in range(rounds):
        _dv, pos = positions(sid, rid)
        if all(pos.get(u) == d for u, d in wanted.items()):
            return True
        occupied = set(pos.values())
        for uid, dest in wanted.items():
            cur = pos.get(uid)
            if cur is None or cur == dest:
                continue
            for p in reversed(gated_path(cur, dest, walk, elev)[1:]):
                if not walk.get(p) or (p in occupied and p != dest):
                    continue
                r = rpc(sid, "applyAction", {"runnerId": rid, "action": {
                    "kind": "move", "unitId": uid, "to": {"col": p[0], "row": p[1]}}}, 60)
                if isinstance(r, dict) and r.get("ok") \
                        and (r.get("actions") or [{}])[0].get("mutated"):
                    occupied.discard(cur)
                    occupied.add(p)
                    break
        rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
        rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    _dv, pos = positions(sid, rid)
    return all(pos.get(u) == d for u, d in wanted.items())


class dark_talon_like:
    """MUTATION : la feuille 1187 remise a la geometrie de DarkTalonStrike (1092) -- ring
    `AdjacentTiles` (porte `|Delta elev| < 2`) + settings de ligne `1/1` (walkable + elevation).
    C'est EXACTEMENT ce qu'un copier-coller de la feuille 1092 produirait. Sur une marche
    d'elevation, ce port SOUS-compte (voire annule) le beam la ou le natif compte."""

    def __enter__(self):
        import engine.playbook.noncomparable.thrice_blessed_conflagration as TBC
        from engine import battle_query as _bq
        self.TBC, self.orig = TBC, (bq.get_surrounding_tiles, TBC._line_enemy_count)

        def ring(p, radius=1, include_center=False, check_walkable=True,
                 walkable_at=None, elevation_at=None, tile_exists=None):
            return _bq.get_adjacent_tiles(p, walkable_at=walkable_at, elevation_at=elevation_at,
                                          tile_exists=tile_exists)

        def line(aim, direction, enemy_set, walkable_at, elevation_at, tile_exists):
            tiles = _bq.get_tiles_behind(aim, direction, max_count=None, check_walkable=True,
                                         update_reference=True, walkable_at=walkable_at,
                                         elevation_at=elevation_at, tile_exists=tile_exists)
            n = 0
            for t in tiles:
                if t not in enemy_set:
                    break
                n += 1
            return n

        bq.get_surrounding_tiles, TBC._line_enemy_count = ring, line
        return self

    def __exit__(self, *exc):
        bq.get_surrounding_tiles, self.TBC._line_enemy_count = self.orig
        return False


def engine_leaf(sid, rid, cid, myplayer, elev, walk):
    """Execute la FEUILLE NonComparable portee sur l'etat LIVE (NCContext bati depuis les RPC).

    Pourquoi la feuille et pas `engine_decide` : le driver de decision offline exclut les MACHINES
    OF WAR (`engine.ai.state_bridge._dv_units` : « MoW EXCLUES -- le natif ne met que
    `EntityType.Unit` dans `decisionView.units` »), donc `engine_decide` n'a PAS d'entree pour le
    SEUL porteur de 1187. Le cablage MoW du driver est un chantier distinct ; ce qui est confronte
    ici est exactement ce que `EvaluateNonComparable` calcule : ability + cible + utilite."""
    from engine.playbook import noncomparable as NC
    dv = rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 180)
    units = [u for u in (dv.get("units") or []) if u.get("alive")]
    epos = [(u["pos"]["col"], u["pos"]["row"]) for u in units
            if u.get("owner") != myplayer and u.get("pos")]
    ctx = NC.NCContext(
        uid=cid, origin=None, reach_nc=[], epos=epos, fpos=[], plan={}, hp_cur_by_id={},
        ability_targets=lambda u, a: rpc(sid, "abilityTargets",
                                         {"runnerId": rid, "unitId": u, "abilityType": a}, 120),
        units=units, walkable_by_pos=walk, elev_by_pos=elev)
    return NC.PLAYBOOKS[ABILITY].generate_candidates(ctx)


def native(sid, rid, cid):
    dry = rpc(sid, "aiDryRunAllUnits", {"runnerId": rid}, 180)
    nat = next((u for u in (dry.get("units") or []) if u.get("unitId") == cid), None)
    out = []
    for m in ((nat or {}).get("proposed") or []):
        out.append((m.get("cls"), m.get("abilityType"), m.get("targetId")))
    return out


def find_line(elev, walk, n=3, want_step=None):
    """(P, [P+d, ..., P+(n-1)d]) : `n` tuiles alignees walkables. `want_step` (ex. 2) exige une
    MARCHE d'elevation `|elev(P+d) - elev(P)| >= want_step` -- le scenario qui SEPARE le ring
    `SurroundingTiles` (sans porte d'elevation) du ring-1 `AdjacentTiles` (porte |Delta| < 2)."""
    cube = {p: hexgeo.to_cube(p[0], p[1]) for p in elev}
    dirs = [(0, -1, 1), (1, -1, 0), (1, 0, -1), (0, 1, -1), (-1, 1, 0), (-1, 0, 1)]
    for P in sorted(elev):
        if not walk.get(P) or elev.get(P) is None:
            continue
        px, _py, pz = cube[P]
        for d in dirs:
            chain = [hexgeo.from_cube(px + d[0] * k, pz + d[2] * k) for k in range(1, n)]
            if any(t not in cube or not walk.get(t) or elev.get(t) is None for t in chain):
                continue
            if want_step is None:
                if len({elev[t] for t in [P] + chain}) != 1:
                    continue                       # palier UNIQUE -> aucun gate d'elevation exerce
            else:
                if abs(elev[chain[0]] - elev[P]) < want_step:
                    continue                       # pas de marche entre la cible et le 1er ennemi
                if len({elev[t] for t in chain}) != 1:
                    continue                       # la ligne elle-meme reste plate
            return P, chain
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", default="C1_02")
    ap.add_argument("--seed", default="4242")
    ap.add_argument("--p-units", default="adeptCanoness,adeptRetributor")
    ap.add_argument("--a-units", default="necroDestroyer,necroWarden,necroDestroyer")
    ap.add_argument("--endturns", type=int, default=2)
    ap.add_argument("--elev", action="store_true",
                    help="exiger une MARCHE d'elevation >= 2 entre la cible et le 1er ennemi")
    ap.add_argument("--keep", action="store_true",
                    help="ne PAS disposer le runner en sortie (inspection manuelle)")
    args = ap.parse_args()

    sid = _sid()
    bc = make_bc()
    rid, state = build(args.seed, args.board, bc, args.p_units, args.a_units)
    if rid is None:
        return 1
    print(f"runner={rid} board={args.board} seed={args.seed}")
    try:
        bg = rpc(sid, "boardGraph", {"runnerId": rid}, 60)
        tiles = bg.get("tiles") or []
        elev = {(t["col"], t["row"]): t.get("elevation") for t in tiles}
        walk = {(t["col"], t["row"]): bool(t.get("walkable")) for t in tiles}
        for _ in range(args.endturns):
            rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
        dv, pos = positions(sid, rid)
        mows = dv.get("mows") or []
        print("mows:", [(m.get("visualId"), m.get("casterId"), m.get("owner")) for m in mows])
        m = next((x for x in mows if x.get("visualId") == MOW), None)
        if m is None:
            print("MoW non deployee")
            return 2
        cid = m["casterId"]
        myplayer = m.get("owner")
        print("caster", cid, "owner", myplayer, "abilities",
              [(a.get("id"), a.get("usable"), a.get("hasAmmo"), a.get("cooldown"))
               for a in (m.get("abilities") or [])])
        mine = [(u["id"], pos.get(u["id"]), u.get("visualId"))
                for u in (dv.get("units") or []) if u.get("owner") == myplayer and u.get("alive")]
        foes = [(u["id"], pos.get(u["id"]), u.get("visualId"))
                for u in (dv.get("units") or []) if u.get("owner") != myplayer and u.get("alive")]
        print("mine:", mine)
        print("foes:", foes)
        print("mow pos:", [(x.get("casterId"), x.get("pos")) for x in mows])
        win = find_line(elev, walk, n=3, want_step=(2 if args.elev else None))
        if win is None:
            print("aucune ligne de 3 tuiles trouvee sur ce board")
            return 3
        P, chain = win
        print("scenario: ally P=%s (elev %s) enemies=%s (elev %s)"
              % (P, elev[P], chain, [elev[c] for c in chain]))
        ally = mine[-1][0]
        eids = [f[0] for f in foes]
        wanted = {ally: P}
        for i, c in enumerate(chain):
            if i < len(eids):
                wanted[eids[i]] = c
        far = [u for u, _p, _v in mine if u != ally]
        ok = drive_to(sid, rid, walk, elev, wanted)
        _dv, pos = positions(sid, rid)
        print("placement ok=%s -> %s (want %s)" % (ok, {u: pos.get(u) for u in wanted}, wanted))
        print("spare allies:", {u: pos.get(u) for u in far})
        at = rpc(sid, "abilityTargets",
                 {"runnerId": rid, "unitId": cid, "abilityType": ABILITY}, 120)
        row = next((u for u in (at.get("units") or []) if u.get("unitId") == cid), {})
        ab = next((a for a in (row.get("abilities") or []) if a.get("abilityId") == ABILITY), {})
        print("fromHere:", json.dumps(ab.get("fromHere") or [])[:500])
        step = rpc(sid, "aiStepDryRun", {"runnerId": rid}, 180)
        msgs = ((step.get("action") or {}).get("messages") or [])
        print("NATIF  :", [(m.get("cls"), m.get("casterId"), m.get("abilityType"), m.get("targetId"))
                           for m in msgs])
        print("MOTEUR :", engine_leaf(sid, rid, cid, myplayer, elev, walk))
        with dark_talon_like():
            print("MUTE(DarkTalon-like):", engine_leaf(sid, rid, cid, myplayer, elev, walk))
        if args.keep:
            print(f"KEEP runner={rid} state={state}")
    finally:
        if not args.keep:                          # discipline runner : on dispose LES SIENS
            rpc(sid, "disposeRunner", {"runnerId": rid}, 20)
            state.unlink(missing_ok=True)
            bc.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
