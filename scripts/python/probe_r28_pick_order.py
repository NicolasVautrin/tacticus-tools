"""PROBE R28-1 -- le `PickRandomly` natif tire-t-il dans l'ORDRE SOURCE ou dans l'ordre des ids ?

CRITERE (decompile = verite). `IdunBattle.Entities.Selectors.PickRandomAmountSelector$$Select` fait
`candidates = source.Select(entities).ToList()` puis tire par `ElementAt(idx)` : AUCUN tri n'intervient
entre la resolution du selecteur et la boucle de tirage. L'`OrderBy` que le port mirrorait
(`IdunBattle.Entities.Behaviours.AttackBehaviour$$Execute` : `if (Count > 1) targets.OrderBy(b__5_0)`)
s'applique APRES. Le port id-triait le pool AVANT le tirage -> a index de tirage EGAL il piquait une
AUTRE unite des que `|pool| > amount`.

PORTEUR = BringerOfDespair (1022, `blackTerminator` Angrax -- hero present au `--list-pool`) :
    bonus = PickRandomly( Damageable(Enemies(AdjacentUnits(casterTile, 1))) - Target(), 1 )
`AdjacentUnits(x)` = `Units(AdjacentTiles(x)) - x` : le natif ITERE les TUILES de
`BattleQuery$$GetAdjacentTiles` (= le champ BRUT `boardGraph.neighbours`, ordre STOCKE) et resout
l'occupant de chacune -> l'ordre source est celui des TUILES, pas celui des ids d'unite.

SCENARIO DISCRIMINANT : 3 ennemis adjacents au caster (1 cible + 2 candidats bonus), places EXPRES
pour que l'ordre `neighbours` brut et l'ordre des ids soient INVERSES sur les deux candidats. Un seul
tirage `NextInternal(0, 2)` decide -- et les deux modeles predisent alors des VICTIMES DIFFERENTES :
    M_SRC (decompile, porte)  : pool = [tuile_i, tuile_j] dans l'ordre brut
    M_ID  (port d'avant)      : pool = [id_min, id_max]
La victime LIVE tranche. Anti-tautologie : le probe ECHOUE s'il n'a pas pu crafter une geometrie ou
les deux modeles divergent (sinon il ne prouve rien et le dit).

Usage :  python probe_r28_pick_order.py [--seed 777] [--board MC1_67]
Depuis scripts/python. ASCII only. Dispose SES runners (jamais ceux des autres).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
sys.path.insert(0, str(PYDIR))

import probe_215_pick_randomly_rng as P215      # Rpc / count_genrand / CountingRng (voie deja validee)

CASTER_VIS = "blackTerminator"
ABILITY = 1022                                   # BringerOfDespair
A_UNITS = "necroWarden,necroWarden,necroWarden,necroOverlord"


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def build(seed, board, state_file):
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--state-file", str(state_file),
         "--board", board, "--roster", "1", "--p-units", CASTER_VIS, "--a-units", A_UNITS,
         "--hp-target", "90000", "--hp-player", "90000"],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not state_file.exists():
        print("BUILD KO:", (proc.stderr or proc.stdout or "")[-500:])
        return None
    return json.loads(state_file.read_text())["runnerId"]


def setup(rpc, seed, board_id):
    """Monte la geometrie : caster + 3 ennemis adjacents (cible + 2 candidats bonus) tels que
    l'ordre `neighbours` BRUT et l'ordre des ids DIVERGENT sur les deux candidats."""
    import hexgeo
    from engine.entities.pathfinding.board import Board

    state_file = ROOT / "logs" / "runners" / f"r28-{uuid.uuid4().hex[:8]}.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    rid = build(seed, board_id, state_file)
    if rid is None:
        return None
    out = {"rid": rid, "state_file": state_file}
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        print("boardGraph indispo")
        return out
    tiles = bg["tiles"]
    board = Board(tiles, adjacency="native_sym")
    raw_neigh = {t["id"]: [n for n in (t.get("neighbours") or []) if n in board.by_id] for t in tiles}

    def mv(uid, tid):
        c = board.coord(tid)
        return rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": uid, "to": {"col": c[0], "row": c[1]}}}, 60)

    def caster_of(dv):
        return next((u for u in (dv.get("units") or [])
                     if u.get("visualId") == CASTER_VIS and u.get("alive")), None)

    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
    if not _ok(dv) or caster_of(dv) is None:
        print("caster absent")
        return out
    myplayer = caster_of(dv).get("owner")
    landed = False
    for _ in range(6):                                # deep-strike : attendre l'atterrissage
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        c = caster_of(dv)
        if c is None:
            break
        tin = any("TeleportingIn" in (e.get("name") or "") for e in (c.get("effects") or []))
        if not tin and dv.get("currentPlayer") == myplayer:
            landed = True
            break
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    if not landed:
        print("terminator non atterri")
        return out

    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
    caster = caster_of(dv)
    cid = caster["id"]
    cpos = (caster["pos"]["col"], caster["pos"]["row"])
    ctile = board.id_at(*cpos)
    enemies = [u for u in (dv.get("units") or []) if u.get("owner") != myplayer and u.get("alive")]
    if len(enemies) < 3:
        print("pas assez d'ennemis")
        return out
    far = [t for t in sorted(board.by_id) if board.walkable(t)
           and hexgeo.distance(board.coord(t), cpos) > 6]
    for e, ft in zip(enemies, far):                   # parking
        mv(e["id"], ft)

    # ring EXPLOITABLE = voisin BRUT, marchable, ET a distance hex 1 (le `_within` du port filtre par
    # distance : une arete brute qui n'est pas a distance 1 ne produirait aucun candidat).
    ring_all = raw_neigh.get(ctile, [])
    ring = [t for t in ring_all if board.walkable(t)
            and hexgeo.distance(board.coord(t), cpos) == 1]
    print(f"[setup] caster tile={ctile}@{cpos} ring_brut_complet={ring_all} "
          f"ring_exploitable={ring} coords={[board.coord(t) for t in ring]}")
    if len(ring) < 3:
        print(f"ring-1 du caster trop petit ({len(ring)})")
        return out
    # cible = 1er voisin ; candidats bonus = deux voisins dont l'ORDRE BRUT est l'INVERSE de
    # l'ordre des ids d'unite -> l'unite d'id le PLUS GRAND va sur la tuile qui vient EN PREMIER.
    ids = sorted(e["id"] for e in enemies[:3])
    tgt_id = ids[0]
    lo_id, hi_id = ids[1], ids[2]
    tile_target, tile_first, tile_second = ring[0], ring[1], ring[2]
    mv(tgt_id, tile_target)
    mv(hi_id, tile_first)                             # id GRAND sur la tuile PRECOCE
    mv(lo_id, tile_second)                            # id PETIT sur la tuile TARDIVE

    dvp = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
    for u in (dvp.get("units") or []):
        if u.get("id") in (tgt_id, lo_id, hi_id) and u.get("pos"):
            p = (u["pos"]["col"], u["pos"]["row"])
            print(f"[setup] u{u['id']} pos={p} tile={board.id_at(*p)} "
                  f"dist_caster={hexgeo.distance(p, cpos)} alive={u.get('alive')}")

    at = rpc("abilityTargets", {"runnerId": rid, "unitId": cid, "abilityType": ABILITY}, 90)
    fh = [x.get("targetId") for x in
          next((a for a in ((at.get("units") or [{}])[0].get("abilities") or [])
                if a.get("abilityId") == ABILITY), {}).get("fromHere") or []]
    if tgt_id not in fh:
        print(f"cast illegal sur {tgt_id} (legaux={fh})")
        return out

    dv2 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
    ob2 = rpc("observeBattle", {"runnerId": rid}, 60)
    snap2 = rpc("combatSnapshot", {"runnerId": rid}, 90)
    rng_before = rpc("dumpRng", {"runnerId": rid}, 30)
    if not _ok(rng_before):
        print("dumpRng KO")
        return out

    cast = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": cid, "targetId": tgt_id, "abilityType": ABILITY},
        "captureEvents": True}, 120)
    if not _ok(cast):
        print("cast KO", str(cast)[:200])
        return out
    rng_after = rpc("dumpRng", {"runnerId": rid}, 30)

    live = {}
    for act in (cast.get("actions") or []):
        for e in (act.get("events") or []):
            td = e.get("tags")
            if not td:
                continue
            td = json.loads(td) if isinstance(td, str) else td
            if "Amount" in td and td.get("Active_Ability_Type") == ABILITY:
                live.setdefault(td.get("Target_Id"), []).append(td.get("Amount"))

    out.update({"board": board, "raw_neigh": raw_neigh, "dv": dv2, "ob": ob2, "snap": snap2,
                "cid": cid, "ctile": ctile, "target": tgt_id, "lo": lo_id, "hi": hi_id,
                "tile_first": tile_first, "tile_second": tile_second, "ring": ring,
                "live": live, "rng_before": rng_before, "rng_after": rng_after})
    return out


def port_victim(reg, id_sorted: bool):
    """Rejoue le cast par le PORT REEL. `id_sorted=True` = MODELE D'AVANT (pool id-trie avant le
    tirage) -- monkeypatch LOCAL du helper, pour disposer de l'arm anti-tautologie sur le MEME etat."""
    from engine.runner.snapshot import load_state
    from engine.runner.abilities.blacklegion import BringerOfDespairAbility
    import engine.runner.abilities.loki.splash as SP
    import engine.runner.abilities.loki as LK

    st = load_state(reg["dv"], reg["ob"], reg["snap"], board=reg["board"])
    rng = P215.CountingRng(reg["rng_before"]["mt"], reg["rng_before"]["mti"])
    st.rng = rng
    orig = SP._pick_randomly_n
    # le module `loki` RE-EXPORTE le helper (`from ..loki import _pick_randomly_n` dans la feuille) ->
    # patcher les DEUX liaisons, sinon l'arm M_ID est un no-op silencieux.
    if id_sorted:
        def patched(state, items, n, _o=orig):
            def key(x):
                return x.get("id") if isinstance(x, dict) else x
            return _o(state, sorted(items, key=key), n)
        SP._pick_randomly_n = patched
        LK._pick_randomly_n = patched
    try:
        res = BringerOfDespairAbility().execute_behaviour(st, reg["cid"], reg["target"])
    finally:
        SP._pick_randomly_n = orig
        LK._pick_randomly_n = orig
    bonus = [b["target"] for b in ((res or {}).get("bonus") or []) if b.get("target") is not None]
    per = {reg["target"]: ((res or {}).get("main_attack") or {}).get("per_hit")}
    for b in ((res or {}).get("bonus") or []):
        per[b["target"]] = (b.get("attack") or {}).get("per_hit")
    return {"victims": bonus, "n": rng.n, "per": per, "res": res}


PC_VIS = "darkaTerminator"
PC_ABILITY = 1150                                # PlasmaCannon : PickRandomly(UnitsDirectlyBehind, 2)


def setup_plasma(rpc, seed, board_id):
    """2e ITERATEUR NATIF : `UnitsDirectlyBehind` part de `SurroundingTiles(target, 1, 1)`, donc son
    ordre source est la TRIPLE BOUCLE CUBE d'`IterateSurroundingTiles` (et non la liste d'adjacence
    stockee). On place **3** unites derriere la cible (amount=2 -> |pool| > amount, le tirage tranche)
    en assignant les ids a CONTRE-SENS du rang cube, pour que les deux modeles divergent."""
    import hexgeo
    from engine.entities.pathfinding.board import Board
    from engine.dsl.base import _tile_enum_rank

    state_file = ROOT / "logs" / "runners" / f"r28pc-{uuid.uuid4().hex[:8]}.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--state-file", str(state_file),
         "--board", board_id, "--roster", "1", "--p-units", PC_VIS, "--a-units", A_UNITS,
         "--hp-target", "90000", "--hp-player", "90000"],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not state_file.exists():
        print("BUILD KO:", (proc.stderr or proc.stdout or "")[-400:])
        return None
    rid = json.loads(state_file.read_text())["runnerId"]
    out = {"rid": rid, "state_file": state_file}
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        print("boardGraph indispo"); return out
    tiles = bg["tiles"]
    elev = {(t["col"], t["row"]): t.get("elevation") for t in tiles}
    board = Board(tiles, adjacency="native_sym")

    def mv(uid, tid):
        c = board.coord(tid)
        return rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": uid, "to": {"col": c[0], "row": c[1]}}}, 60)

    def caster_of(dv):
        return next((u for u in (dv.get("units") or [])
                     if u.get("visualId") == PC_VIS and u.get("alive")), None)

    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
    if not _ok(dv) or caster_of(dv) is None:
        print("caster absent"); return out
    myplayer = caster_of(dv).get("owner")
    landed = False
    for _ in range(6):
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        c = caster_of(dv)
        if c is None:
            break
        tin = any("TeleportingIn" in (e.get("name") or "") for e in (c.get("effects") or []))
        if not tin and dv.get("currentPlayer") == myplayer:
            landed = True
            break
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    if not landed:
        print("terminator non atterri"); return out

    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
    caster = caster_of(dv)
    cid = caster["id"]
    cpos = (caster["pos"]["col"], caster["pos"]["row"])
    ctile = board.id_at(*cpos)
    eC = elev.get(cpos)
    enemies = [u for u in (dv.get("units") or []) if u.get("owner") != myplayer and u.get("alive")]
    if len(enemies) < 4:
        print("pas assez d'ennemis"); return out
    far = [t for t in sorted(board.by_id) if board.walkable(t)
           and hexgeo.distance(board.coord(t), cpos) > 6]
    for e, ft in zip(enemies, far):
        mv(e["id"], ft)

    cand = None
    for T in sorted(board.by_id):
        ct = board.coord(T)
        if not board.walkable(T) or T == ctile or hexgeo.distance(ct, cpos) != 2:
            continue
        if elev.get(ct) is None or eC is None or abs(elev.get(ct) - eC) > 1:
            continue
        nbrs = [n for n in board.neighbours(T) if board.walkable(n) and n != ctile]
        behind = [n for n in nbrs if hexgeo.distance(board.coord(n), cpos) == 3
                  and elev.get(board.coord(n)) is not None
                  and abs(elev.get(board.coord(n)) - elev.get(ct)) <= 1]
        if len(behind) >= 3:
            mv(enemies[0]["id"], T)
            at = rpc("abilityTargets", {"runnerId": rid, "unitId": cid, "abilityType": PC_ABILITY}, 90)
            fh = [x.get("targetId") for x in
                  next((a for a in ((at.get("units") or [{}])[0].get("abilities") or [])
                        if a.get("abilityId") == PC_ABILITY), {}).get("fromHere") or []]
            if enemies[0]["id"] in fh:
                cand = (T, behind[:3])
                break
            mv(enemies[0]["id"], far[0])
    if cand is None:
        print("geometrie 3-directly-behind introuvable"); return out
    T, behind = cand
    tpos = board.coord(T)
    # rang CUBE des 3 tuiles -> ids assignes a CONTRE-SENS (id croissant sur rang decroissant)
    rank = _tile_enum_rank(board, tpos, 1, "surrounding")
    behind_sorted = sorted(behind, key=lambda t: rank.get(board.coord(t), 10 ** 9))
    ids = sorted(e["id"] for e in enemies[1:4])
    placed = []
    for tile, uid in zip(behind_sorted, reversed(ids)):
        mv(uid, tile)
        placed.append(uid)

    at2 = rpc("abilityTargets", {"runnerId": rid, "unitId": cid, "abilityType": PC_ABILITY}, 90)
    fh2 = [x.get("targetId") for x in
           next((a for a in ((at2.get("units") or [{}])[0].get("abilities") or [])
                 if a.get("abilityId") == PC_ABILITY), {}).get("fromHere") or []]
    if enemies[0]["id"] not in fh2:
        print("cast illegal apres placement"); return out

    dv2 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
    ob2 = rpc("observeBattle", {"runnerId": rid}, 60)
    snap2 = rpc("combatSnapshot", {"runnerId": rid}, 90)
    rng_before = rpc("dumpRng", {"runnerId": rid}, 30)
    if not _ok(rng_before):
        print("dumpRng KO"); return out
    cast = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": cid, "targetId": enemies[0]["id"],
        "abilityType": PC_ABILITY}, "captureEvents": True}, 120)
    if not _ok(cast):
        print("cast KO", str(cast)[:200]); return out
    rng_after = rpc("dumpRng", {"runnerId": rid}, 30)
    live = {}
    for act in (cast.get("actions") or []):
        for e in (act.get("events") or []):
            td = e.get("tags")
            if not td:
                continue
            td = json.loads(td) if isinstance(td, str) else td
            if "Amount" in td and td.get("Active_Ability_Type") == PC_ABILITY:
                live.setdefault(td.get("Target_Id"), []).append(td.get("Amount"))
    out.update({"board": board, "dv": dv2, "ob": ob2, "snap": snap2, "cid": cid,
                "target": enemies[0]["id"], "behind": placed, "behind_tiles": behind_sorted,
                "live": live, "rng_before": rng_before, "rng_after": rng_after})
    return out


def port_victims_plasma(reg, id_sorted: bool):
    from engine.runner.snapshot import load_state
    from engine.runner.abilities.darkangels import PlasmaCannonAbility
    import engine.runner.abilities.loki.splash as SP
    import engine.runner.abilities.loki as LK

    st = load_state(reg["dv"], reg["ob"], reg["snap"], board=reg["board"])
    rng = P215.CountingRng(reg["rng_before"]["mt"], reg["rng_before"]["mti"])
    st.rng = rng
    orig = SP._pick_randomly_n
    if id_sorted:
        def patched(state, items, n, _o=orig):
            def key(x):
                return x.get("id") if isinstance(x, dict) else x
            return _o(state, sorted(items, key=key), n)
        SP._pick_randomly_n = patched
        LK._pick_randomly_n = patched
    try:
        res = PlasmaCannonAbility().execute_behaviour(st, reg["cid"], reg["target"])
    finally:
        SP._pick_randomly_n = orig
        LK._pick_randomly_n = orig
    per = {reg["target"]: ((res or {}).get("main_attack") or {}).get("per_hit")}
    vic = []
    for s in ((res or {}).get("splash") or []):
        vic.append(s["target"])
        per[s["target"]] = (s.get("attack") or {}).get("per_hit")
    return {"victims": sorted(vic), "n": rng.n, "per": per}


def run_plasma(rpc, seed, board_id):
    reg = setup_plasma(rpc, seed, board_id)
    if reg is None:
        print("SETUP KO (build)")
        return
    try:
        if "live" not in reg:
            print("SETUP KO (scenario plasma non monte)")
            return
        live_v = sorted(t for t in reg["live"] if t != reg["target"])
        print(f"\n[PLASMA] caster={reg['cid']} cible={reg['target']} "
              f"behind(tuiles rang cube croissant)={reg['behind_tiles']} ids places={reg['behind']}")
        print(f"[PLASMA] LIVE degats 1150 = { {k: len(v) for k, v in reg['live'].items()} } "
              f"-> victimes splash = {live_v}")
        print(f"[PLASMA] LIVE genrand = {P215.count_genrand(reg['rng_before'], reg['rng_after'])}")
        src = port_victims_plasma(reg, id_sorted=False)
        idm = port_victims_plasma(reg, id_sorted=True)
        print(f"[PLASMA] PORT M_SRC (ordre cube) victimes={src['victims']} genrand={src['n']}")
        print(f"[PLASMA] PORT M_ID  (id-trie)    victimes={idm['victims']} genrand={idm['n']}")
        if src["victims"] == idm["victims"]:
            print("[PLASMA] !! NON DISCRIMINANT")
        else:
            print(f"[PLASMA] VERDICT : M_SRC {'CONFIRME' if set(live_v) == set(src['victims']) else 'refute'} "
                  f"| M_ID {'CONFIRME' if set(live_v) == set(idm['victims']) else 'refute'}")
        for name, m in (("M_SRC", src), ("M_ID", idm)):
            rs, missing = [], []
            for tid, ph in m["per"].items():
                lp = reg["live"].get(tid) or []
                if ph and len(lp) == len(ph):
                    rs += [a / b for a, b in zip(lp, ph)]
                else:
                    missing.append(tid)
            ex = bool(rs) and max(abs(x - 1.0) for x in rs) < 1e-9
            print(f"[PLASMA] {name} per-coup : {len(rs)} coups compares, bit-exact={'OUI' if ex else 'NON'}"
                  + (f", cibles SANS degat live = {missing}" if missing else ""))
    finally:
        try:
            rpc("disposeRunner", {"runnerId": reg["rid"]}, 20)
        except Exception:
            pass
        try:
            reg["state_file"].unlink()
        except Exception:
            pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--mode", default="bod", choices=["bod", "plasma"])
    args = ap.parse_args()
    rpc = P215.Rpc()
    print(f"session={rpc.sid} seed={args.seed} board={args.board} mode={args.mode}")
    if args.mode == "plasma":
        run_plasma(rpc, args.seed, args.board)
        return

    reg = setup(rpc, args.seed, args.board)
    if reg is None:
        print("SETUP KO (build)")
        return
    try:
        if "live" not in reg:
            print("SETUP KO (scenario non monte)")
            return
        print(f"\ncaster={reg['cid']} tile={reg['ctile']} ring_brut={reg['ring']}")
        print(f"cible={reg['target']}  candidats bonus: hi_id={reg['hi']}@tile{reg['tile_first']} "
              f"(ordre brut PRECOCE)  lo_id={reg['lo']}@tile{reg['tile_second']} (TARDIF)")
        live_victims = sorted(t for t in reg["live"] if t != reg["target"])
        print(f"LIVE : degats 1022 par cible = { {k: len(v) for k, v in reg['live'].items()} }")
        print(f"LIVE : victime(s) BONUS = {live_victims}")
        live_n = P215.count_genrand(reg["rng_before"], reg["rng_after"])
        print(f"LIVE : genrand consommes = {live_n}")

        # POOL resolu par le selecteur DSL, AVANT le tirage -- c'est LUI qui porte l'ordre source.
        from engine.runner.snapshot import load_state
        from engine.runner.abilities.behaviours.context import entities_from_state
        from engine.runner.abilities.blacklegion import bringer_of_despair_tree
        st0 = load_state(reg["dv"], reg["ob"], reg["snap"], board=reg["board"])
        ents0 = entities_from_state(st0, reg["cid"], reg["target"])
        leaf = bringer_of_despair_tree().child.right         # op_and(main, bonus) -> feuille bonus
        pool = [u.get("id") for u in leaf.target_sel.evaluate(ents0)]
        print(f"POOL resolu (ordre source) = {pool}   | id-trie = {sorted(pool)}")

        src = port_victim(reg, id_sorted=False)
        idm = port_victim(reg, id_sorted=True)
        print(f"PORT M_SRC (ordre source, decompile) : victime={src['victims']} genrand={src['n']}")
        print(f"PORT M_ID  (pool id-trie, ex-port)   : victime={idm['victims']} genrand={idm['n']}")

        if src["victims"] == idm["victims"]:
            print("\n!! NON DISCRIMINANT : les deux modeles predisent la MEME victime -> ce scenario "
                  "ne prouve rien (re-crafter la geometrie).")
        else:
            v = set(live_victims)
            print("\n=== VERDICT ===")
            print(f"  M_SRC {'CONFIRME' if v == set(src['victims']) else 'refute'} par le live")
            print(f"  M_ID  {'CONFIRME' if v == set(idm['victims']) else 'refute'} par le live")

        def ratios(per):
            rs = []
            for tid, ph in per.items():
                lp = reg["live"].get(tid) or []
                if ph and len(lp) == len(ph):
                    rs += [a / b for a, b in zip(lp, ph)]
            return rs
        for name, m in (("M_SRC", src), ("M_ID", idm)):
            rs = ratios(m["per"])
            ex = bool(rs) and max(abs(x - 1.0) for x in rs) < 1e-9
            print(f"  {name} per-coup bit-exact vs live : {'OUI' if ex else 'NON'} "
                  f"(ratios={[round(x, 4) for x in rs][:8]})")
    finally:
        try:
            rpc("disposeRunner", {"runnerId": reg["rid"]}, 20)
        except Exception:
            pass
        try:
            reg["state_file"].unlink()
        except Exception:
            pass


if __name__ == "__main__":
    main()
