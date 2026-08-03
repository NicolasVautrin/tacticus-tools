"""#448-r1-r1-r1 -- la branche VOLANTE de `_movement_steps`, CONFRONTEE.

`IdunBattle.Operations.MoveUnitOperation$$Execute`, au site de fin de mouvement :

    movementSteps = IsLikeFlying(unit, options)
                      ? battleQuery.<slot itf 0x6c = GetDistance>(path.First(), path.Last())
                      : path.Count

Les deux branches sont ASYMETRIQUES : la marcheuse rend `path.Count` = `pas + 1`
(`path[0]` = tuile de DEPART), la volante rend une DISTANCE, qui n'a pas ce `+1` et qui
**ne depend pas du chemin**. #448-r1-r1 a mesure ses trois bras sur des MARCHEURS
uniquement : la branche volante etait portee et jamais exercee.

CE QUE LE SLOT 0x6c EST, re-derive au RUNTIME (`probe_27_4g_battlequery_slots.py`,
build `rnca9r7q6c`, ancres `+4` confirmees) :

    slot itf 0x6c -> index de vtable 0x70 -> `BattleQuery$$GetDistance(tileA, tileB)`
      -> `MovementQuery$$GetDistance(origin: IEntity, destination: IEntity)`
      -> min sur (a in GetTiles(origin), b in GetTiles(destination))
             `IdunBattle.Utils.Hex.CubeCoordinate$$Distance(a, b)` = max(|dx|,|dy|,|dz|)

Corroboration STRUCTURELLE independante : `IdunBattle.Operations.MoveUnitOperation$$
CalculatePaths` appelle **le meme slot 0x6c** avec `(startTile, endTile)` et compare son
retour au **stat Movement** (`GetStat(unit, 1)`) -- ce qui n'a de sens que pour une
distance en hexes. Les slots voisins recoupent : `0x15 = GetConnectedPathTo` et
`0x17 = GetNumTilesMoved` sont exactement ceux que le decompile utilise par ailleurs.

LE COUPLE DISCRIMINANT. Le gate de `1134 FullThrottle`
(`AmountIsEqualOrGreater(MovementSteps(), 'movement' = 3)`, `chance` = 30 %) rend
`movementSteps` OBSERVABLE par la mort du caster :

    | bras | trajet                        | movementSteps | gate >= 3 | MESURE NATIF   |
    | M2   | MARCHEUR, 2 pas (d = 2)       | path.Count = 3| VRAI      | 3 / 8  (37,5 %)|
    | V2   | VOLANT,   d = 2, vol direct   | distance   = 2| FAUX      | 0 / 20 ( 0,0 %)|
    | V3   | VOLANT,   d = 3, vol direct   | distance   = 3| VRAI      | 4 / 13 (30,8 %)|
    | VD   | VOLANT,   d = 2, vol DETOURNE | distance   = 2| FAUX      | 0 / 14 ( 0,0 %)|

* `M2` + `V2` = le couple demande : MEME distance parcourue, `movementSteps` DIFFERENT
  selon que l'unite vole ou marche. C'est ce couple, et lui seul, qui prouve l'asymetrie.
* `V3` est le controle POSITIF sans lequel « 0 mort chez le volant » serait indistinguable
  d'une greffe inerte.
* `VD` leve l'ambiguite restante : sur un vol DIRECT, `distance` et `path.Count - 1`
  coincident, donc `V2` seul ne distingue pas « distance » de « nombre de pas de vol ».
  `VD` choisit un trajet ou un mur (`HulkWall`, `FlyPathfinder$$IsValidPathNode` teste
  `TileComponent+0x41`) force le vol a contourner : `d = 2` mais tout chemin de vol fait
  >= 3 pas. Les trois lectures y divergent (2 / 3 / 4) et une seule ne tue pas.

Usage :
    python probe_448_r1_r1_r1_flying_movement_steps.py --offline    # etape 0 SEULE (0 runner)
    python probe_448_r1_r1_r1_flying_movement_steps.py              # etape 0 + M2/V2/V3
    python probe_448_r1_r1_r1_flying_movement_steps.py --only VD --turns 16   # le bras VD
    python probe_448_r1_r1_r1_flying_movement_steps.py --port       # chaine PORT (200 graines)
    python probe_448_r1_r1_r1_flying_movement_steps.py --port --mutate-fly    # CONTRE-EPREUVE
    python probe_448_r1_r1_r1_flying_movement_steps.py --scan C6_09,C6_25     # diag de board
"""
from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys

PYDIR = pathlib.Path(__file__).resolve().parent
ROOT = PYDIR.parent.parent
LOGSDIR = ROOT / "logs"
sys.path.insert(0, str(PYDIR))

ABILITY = "FullThrottle"
# Greffons VOLANTS : `Flying` + `Movement >= 4` (il faut pouvoir viser d = 2 ET d = 3), tous
# DANS `rl_duel build --list-pool` -- gate de confrontabilite passee au premier etage (HERO).
FLY_GRAFTS = ["blackHaarken", "bloodDante", "bloodIntercessor", "eldarAutarch",
              "tyranWingedPrime"]
# Greffons MARCHEURS : ceux de #448-r1-r1, pour que le bras M2 soit comparable a sa mesure.
WALK_GRAFTS = ["orksNob", "orksWarboss", "orksRuntherd", "orksBigMek", "orksKillaKan"]


# ------------------------------------------------------------------ ETAPE 0 (offline)
def _synth_board(walls=()):
    """Board hex plat 9x9, adjacence GEOMETRIQUE, avec des murs optionnels.

    `evenq` : c'est le mode qui laisse la geometrie observable (en `native_sym` l'adjacence
    est bakee dans le champ capte). Un mur = `isWall` ET `walkable = False` : c'est ce que
    le `boardGraph` publie pour un `HulkWall`, et les deux volets comptent -- `walkable`
    ferme l'ARRIVEE, `isWall` ferme la TRAVERSEE du vol."""
    import hexgeo
    from engine.entities.pathfinding.board import Board
    cols = rows = 9
    walls = {(int(c), int(r)) for c, r in walls}

    def tid(c, r):
        return c * rows + r + 1
    tiles = []
    for c in range(cols):
        for r in range(rows):
            nb = [tid(cc, rr) for (cc, rr) in hexgeo.neighbors(c, r)
                  if 0 <= cc < cols and 0 <= rr < rows]
            w = (c, r) in walls
            tiles.append({"id": tid(c, r), "col": c, "row": r, "elevation": 0,
                          "walkable": not w, "isWall": w, "neighbours": nb})
    return Board(tiles, adjacency="evenq")


def _synth_state(board, traits, pos=(4, 4)):
    """Un `State` minimal portant UNE unite a `pos` avec `traits`. Assez pour `_movement_steps` :
    il lit `StatsComponent.ctx.traits` (branche), `PositionComponent`/`OwnerComponent`/
    `UnitComponent` des AUTRES entites (blocage de marche) et `state.board`."""
    from engine.runner.state import State
    from engine.runner.components import (PositionComponent, UnitComponent, StatsComponent,
                                          OwnerComponent)
    from engine.entities.unit_context import UnitContext
    st = State()
    st.board = board
    e = st.add_entity(1)
    e.add_component(PositionComponent(col=pos[0], row=pos[1]))
    e.add_component(UnitComponent(visual_id="probe", alive=True))
    e.add_component(OwnerComponent(team=1, player=1))
    ctx = UnitContext(entity_id=1, visual_id="probe")
    ctx.traits = list(traits)          # noms gameconfig (str), comme `_load_traits` les pose
    e.add_component(StatsComponent(ctx=ctx))
    return st


def _fly_path_steps(board, src, dst) -> int:
    """Nombre MINIMAL de pas d'un chemin de vol de `src` a `dst` -- BFS non pondere sur le
    voisinage GEOMETRIQUE avec l'arete `FlyPathfinder$$IsValidPathNode` (= `!IsWall`, cf.
    `engine/entities/pathfinding/fly_pathfinder.py`). `-1` = injoignable.

    Sert UNIQUEMENT a qualifier un trajet (direct / detourne) : c'est la grandeur que la
    branche volante n'utilise PAS, et c'est pour cela qu'on la mesure a cote."""
    from collections import deque
    from engine.entities.pathfinding.fly_pathfinder import is_valid_path_node
    sid = board.id_at(int(src[0]), int(src[1]))
    did = board.id_at(int(dst[0]), int(dst[1]))
    if sid is None or did is None:
        return -1
    seen = {sid: 0}
    q = deque([sid])
    while q:
        cur = q.popleft()
        if cur == did:
            return seen[cur]
        for n in board.neighbours_geometric(cur):
            if n in seen or not is_valid_path_node(board, cur, n, {}, 1):
                continue
            seen[n] = seen[cur] + 1
            q.append(n)
    return -1


def etape0() -> int:
    """Le cablage OFFLINE des deux branches, et le COUPLE, sur un board synthetique."""
    from engine.entities.pathfinding.fly_pathfinder import is_like_flying
    from engine.runner.operations.movement import _movement_steps, _num_tiles_moved
    import hexgeo

    bad = 0
    print("== ETAPE 0 (offline) -- les deux branches de `_movement_steps`")

    for traits, expect in ((["Flying"], True), (["Burrow"], True), (["Hulking"], False),
                           ([], False), (["Flying", "Hulking"], True)):
        got = bool(is_like_flying(traits))
        ok = got == expect
        bad += 0 if ok else 1
        print("   is_like_flying(%-22s) = %-5s attendu %-5s %s"
              % (traits, got, expect, "OK" if ok else "FAUX"))

    # --- Le couple, sur un board PLAT : trajet direct, distance == pas de marche.
    board = _synth_board()
    src = (4, 4)
    print("   -- board plat 9x9, depart %s" % (src,))
    for d in (1, 2, 3, 4):
        dst = _dest_at_distance(board, src, d)
        if dst is None:
            print("     d=%d : aucune tuile a cette distance -- SKIP" % d)
            continue
        fly = _movement_steps(_synth_state(board, ["Flying"], src), 1, src, dst)
        walk = _movement_steps(_synth_state(board, [], src), 1, src, dst)
        pas = _num_tiles_moved(_synth_state(board, [], src), 1, src, dst)
        okf, okw = fly == d, walk == pas + 1
        bad += 0 if (okf and okw) else 1
        # Le couple ne prouve quelque chose que s'il DIFFERE.
        okc = fly != walk
        bad += 0 if okc else 1
        print("     d=%d dst=%-7s : VOLANT=%d (attendu %d %s) MARCHEUR=%d (pas=%d -> %d %s) "
              "ecart=%d %s" % (d, dst, fly, d, "OK" if okf else "FAUX", walk, pas, pas + 1,
                               "OK" if okw else "FAUX", walk - fly, "OK" if okc else "IDENTIQUES"))

    # --- Le DETOUR : la branche volante ne lit PAS le chemin.
    # Mur en arc autour de (4,4) laissant une seule breche : d((4,4),(4,6)) = 2 mais le vol
    # doit contourner.
    walls = [(3, 5), (4, 5), (5, 5), (3, 6), (5, 6)]
    bd = _synth_board(walls)
    src, dst = (4, 4), (4, 6)
    d = hexgeo.distance(src, dst)
    steps = _fly_path_steps(bd, src, dst)
    fly = _movement_steps(_synth_state(bd, ["Flying"], src), 1, src, dst)
    ok = (d == 2) and (steps > d) and (fly == d)
    bad += 0 if ok else 1
    print("   -- DETOUR (murs %s) : d=%d, pas de vol MINIMAUX=%d, `_movement_steps`=%d "
          "-> %s" % (walls, d, steps, fly, "OK (lit la DISTANCE)" if ok else "FAUX"))
    print("      (une lecture `path.Count-1` rendrait %d, une lecture `path.Count` %d -- "
          "les trois divergent)" % (steps, steps + 1))
    return bad


def _dest_at_distance(board, src, d):
    """Une tuile du board a distance hex EXACTEMENT `d` de `src`, joignable en vol."""
    import hexgeo
    for c, r in sorted(board.by_coord):
        if hexgeo.distance(src, (c, r)) != d:
            continue
        if _fly_path_steps(board, src, (c, r)) < 0:
            continue
        return (c, r)
    return None


# ------------------------------------------------------------------ VOLET LIVE
def _rpc_factory():
    from rl_collect_batch import _resolve_session, _rpc

    def rpc(sid, m, args, t=120):
        r = _rpc(sid, m, [args], timeout=t)
        return (r.get("result") if isinstance(r, dict) and "result" in r else r) or {}
    return _resolve_session(), rpc


def _build(board: str, seed: int, tag: str, grafts: list, foes: list) -> tuple[int, pathlib.Path]:
    import catalog_inject as CI
    LOGSDIR.mkdir(parents=True, exist_ok=True)
    state_file = LOGSDIR / ("p448r1r1r1_state_%s.json" % tag)
    bc_path = LOGSDIR / ("p448r1r1r1_bc_%s.json" % tag)

    bc = json.loads((ROOT / "data" / "seed-bc.json").read_text(encoding="utf-8"))
    for uid in grafts:
        CI.graft_passive_ability(bc, uid, ABILITY)
    bc_path.write_text(json.dumps(bc), encoding="utf-8")

    # Le nombre de SPAWNS JOUEUR varie par board (les C6_* en ont 3 a 5) et le build refuse
    # `N spawns joueur < M units`. On DEGRADE l'equipe plutot que d'echouer : moins de porteurs,
    # donc moins d'essais par tour, mais le bras reste joue. Le compte reel est publie.
    used = list(grafts)
    while used:
        state_file.unlink(missing_ok=True)
        cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--rank", "17",
               "--board", board, "--p-units", ",".join(used),
               "--a-units", ",".join(foes), "--no-ai",
               "--seed-bc", str(bc_path), "--state-file", str(state_file)]
        p = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if state_file.exists():
            rid = int(json.loads(state_file.read_text(encoding="utf-8"))["runnerId"])
            if len(used) != len(grafts):
                print("     [build] %s : %d spawns joueur -> equipe reduite a %s"
                      % (board, len(used), used))
            return rid, state_file, used
        if "spawns joueur <" not in (p.stdout or "") + (p.stderr or ""):
            break
        used = used[:-1]
    sys.stdout.write((p.stdout or "")[-1500:])
    sys.stdout.write((p.stderr or "")[-1500:])
    raise SystemExit("build KO (%s)" % tag)


def _port_state(sid, rpc, rid, board):
    """Cf. `probe_448_r1_r1_full_throttle._port_state` : `board=` et `ability_states=` sont
    tous deux OBLIGATOIRES depuis un probe autonome (sans eux le compte de pas court-circuite
    a 0, et la greffe reste INERTE sans erreur)."""
    from engine.runner.snapshot import load_state
    dv = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 150)
    ob = rpc(sid, "observeBattle", {"runnerId": rid}, 60)
    snap = rpc(sid, "combatSnapshot", {"runnerId": rid}, 90)
    ast = rpc(sid, "unitAbilityStates", {"runnerId": rid}, 90)
    return load_state(dv, ob, snap, board=board, ability_states=ast), dv, ob


def _alive_map(dv) -> dict:
    """`decisionView.units[].alive` indexe par `id` -- la MEME numerotation que `toActivate`
    (jamais `observeBattle.entityId`, qui est une autre cle)."""
    out = {}
    for u in (dv.get("units") or []):
        uid = u.get("id")
        if uid is not None:
            out[int(uid)] = bool(u.get("alive"))
    return out


def _carriers(dv, grafts) -> set:
    return {int(u.get("id")) for u in (dv.get("units") or [])
            if u.get("id") is not None and (u.get("visualId") in grafts)}


def _legal_moves(sid, rpc, rid, uid: int) -> set:
    """Les tuiles ou le NATIF accepte de deplacer `uid` -- `aiMovableTiles`."""
    mov = rpc(sid, "aiMovableTiles", {"runnerId": rid}, 60)
    out = set()
    for mu in (mov.get("units") or []):
        if int(mu.get("unitId", -1)) != int(uid):
            continue
        for t in (mu.get("tiles") or []):
            c, r = t.get("col"), t.get("row")
            if c is not None and r is not None:
                out.add((int(c), int(r)))
    return out


def _detour_pairs(board, want: int = 2) -> dict:
    """`{src -> [dst, ...]}` des couples a distance hex `want` dont TOUT chemin de vol fait
    STRICTEMENT plus de `want` pas -- c'est-a-dire ou un mur force le vol a contourner.

    C'est le seul trajet qui distingue la branche volante (`GetDistance`, insensible au
    chemin) d'une lecture `path.Count - 1` : sur un vol DIRECT les deux coincident, donc un
    accord obtenu la ne confirme rien."""
    import hexgeo
    out = {}
    coords = sorted(board.by_coord)
    for src in coords:
        if not board.walkable(board.id_at(*src)):
            continue
        ds = []
        for dst in coords:
            if hexgeo.distance(src, dst) != want:
                continue
            if not board.walkable(board.id_at(*dst)):
                continue
            fs = _fly_path_steps(board, src, dst)
            if fs > want:
                ds.append(dst)
        if ds:
            out[src] = ds
    return out


def _approach(board, src, legal: set, targets) -> "tuple | None":
    """Un pas d'APPROCHE d'UN hexe vers la zone `targets`, choisi dans `legal`.

    Un pas de 1 ne peut PAS declencher le gate, quelle que soit la branche : `movementSteps`
    y vaut 1 (volant) ou 2 (marcheur), tous deux `< 3`. L'approche ne peut donc ni tuer le
    porteur ni polluer la mesure -- elle ne fait que l'amener ou la configuration existe.
    C'est la parade au « bloque par la geometrie de spawn »."""
    import hexgeo
    if not targets:
        return None
    best, bestd = None, None
    for dest in sorted(legal):
        if hexgeo.distance(src, dest) != 1:
            continue
        d = min(hexgeo.distance(dest, t) for t in targets)
        if bestd is None or d < bestd:
            best, bestd = dest, d
    cur = min(hexgeo.distance(src, t) for t in targets)
    return best if (best is not None and bestd < cur) else None


def _pick(state, board, uid: int, legal: set, mode: str, want: int):
    """Une destination LEGALE realisant le trajet demande. Rend `(dest, info)` ou `None`.

    `mode` :
      * `walk`  -- chemin de MARCHE de `want` pas ET distance hex `want` (trajet DIRECT :
        c'est ce qui rend le bras comparable au bras volant « a distance egale ») ;
      * `fly`   -- distance hex `want` ET vol DIRECT (pas de vol minimaux == `want`) ;
      * `flyd`  -- distance hex `want` ET vol DETOURNE (pas de vol minimaux > `want`).
    """
    import hexgeo
    from engine.runner.operations.movement import _num_tiles_moved
    from engine.runner.components import PositionComponent
    e = state.get_entity(int(uid))
    pc = e.get_component(PositionComponent) if e is not None else None
    if pc is None:
        return None
    src = (pc.col, pc.row)
    for dest in sorted(legal):
        d = hexgeo.distance(src, dest)
        if mode == "walk":
            if d == want and _num_tiles_moved(state, int(uid), src, dest) == want:
                return dest, {"src": src, "d": d, "walk_steps": want}
        else:
            if d != want:
                continue
            fs = _fly_path_steps(board, src, dest)
            if mode == "fly" and fs == want:
                return dest, {"src": src, "d": d, "fly_steps": fs}
            if mode == "flyd" and fs > want:
                return dest, {"src": src, "d": d, "fly_steps": fs}
    return None


def bras(name: str, board_id: str, seed: int, grafts: list, foes: list,
         mode: str, want: int, max_turns: int) -> dict:
    """Un bras : chaque porteur vivant joue le trajet demande, tour apres tour ; on relit sa
    mort IMMEDIATEMENT apres le move (avant toute action adverse)."""
    rid, _sf, grafts = _build(board_id, seed, "%s_%s_%d" % (name, board_id, seed),
                              grafts, foes)
    sid, rpc = _rpc_factory()
    print("== BRAS %s  mode=%s want=%d  board=%s seed=%d  runner=%s"
          % (name, mode, want, board_id, seed, rid))
    from engine.entities.pathfinding.board import Board
    bg = rpc(sid, "boardGraph", {"runnerId": rid}, 90)
    brd = Board(bg["tiles"], adjacency="native_sym")
    # La QUALIFICATION de trajet (direct / detourne) se fait sur la geometrie du vol, donc sur
    # un board `neighbours_geometric` -- `Board` l'expose quel que soit son mode d'adjacence.
    dpairs, dsrcs = {}, []
    if mode == "flyd":
        dpairs = _detour_pairs(brd, want)
        dsrcs = sorted(dpairs)
        nwall = sum(1 for t in bg["tiles"] if t.get("isWall"))
        print("     [board] %d mur(s) ; %d tuile(s) de depart offrant un trajet DETOURNE a d=%d"
              % (nwall, len(dsrcs), want))
        if not dsrcs:
            print("     [board] AUCUN trajet detourne -- bras NON CONFRONTABLE sur ce board")
    essais, morts, details, skips = 0, 0, [], 0
    try:
        for turn in range(max_turns):
            state, dv, _ob = _port_state(sid, rpc, rid, brd)
            alive = _alive_map(dv)
            to_act = [int(u) for u in (dv.get("toActivate") or [])]
            if not to_act:
                print("     t%d : toActivate vide -> fin" % turn)
                break
            carriers = _carriers(dv, grafts)
            for uid in to_act:
                if not alive.get(uid, False) or uid not in carriers:
                    continue
                legal = _legal_moves(sid, rpc, rid, uid)
                state, _, _ = _port_state(sid, rpc, rid, brd)
                got = _pick(state, brd, uid, legal, mode, want)
                if got is None:
                    # Pas de configuration ICI -> on DEPLACE le porteur vers la zone qui
                    # l'offre, d'un pas de 1 (qui ne peut pas declencher le gate). Ce n'est
                    # jamais compte comme un essai.
                    from engine.runner.components import PositionComponent
                    e = state.get_entity(int(uid))
                    pc = e.get_component(PositionComponent) if e is not None else None
                    step = (_approach(brd, (pc.col, pc.row), legal, dsrcs)
                            if (mode == "flyd" and pc is not None) else None)
                    if step is not None:
                        rpc(sid, "applyAction", {"runnerId": rid, "action": {
                            "kind": "move", "unitId": int(uid),
                            "to": {"col": int(step[0]), "row": int(step[1])}}}, 120)
                        print("     t%d u%s (%d,%d) -> %s : APPROCHE (1 pas, gate hors "
                              "portee)" % (turn, uid, pc.col, pc.row, step))
                        continue
                    skips += 1
                    print("     t%d u%s : SKIP -- aucune des %d tuiles legales ne realise "
                          "%s/%d" % (turn, uid, len(legal), mode, want))
                    continue
                dest, info = got
                rpc(sid, "applyAction", {"runnerId": rid, "action": {
                    "kind": "move", "unitId": int(uid),
                    "to": {"col": int(dest[0]), "row": int(dest[1])}}}, 120)
                dv2 = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1,
                                                "allAbilities": True}, 150)
                dead = not _alive_map(dv2).get(uid, False)
                essais += 1
                morts += 1 if dead else 0
                details.append(dict(info, turn=turn, unit=uid, dest=list(dest), dead=dead))
                print("     t%d u%s %s -> %s (%s) : %s"
                      % (turn, uid, info["src"], dest,
                         " ".join("%s=%s" % kv for kv in sorted(info.items()) if kv[0] != "src"),
                         "MORT" if dead else "vivant"))
            rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 120)
    finally:
        try:
            rpc(sid, "disposeRunner", {"runnerId": rid}, 60)
        except Exception:
            pass
    pct = (100.0 * morts / essais) if essais else 0.0
    print("   -> BRAS %s : %d mort(s) / %d essai(s) = %.1f %%  (%d skip)"
          % (name, morts, essais, pct, skips))
    return {"name": name, "mode": mode, "want": want, "essais": essais, "morts": morts,
            "pct": pct, "skips": skips, "details": details, "board": board_id, "seed": seed}


def scan(board_ids: list, seed: int, foes: list, grafts=None, want: int = 2) -> dict:
    """Diagnostic de board SANS jouer : combien de trajets DETOURNES a `want` hexes ce board
    offre-t-il ? Le `isWall` n'est publie QUE par le `boardGraph` live (le JSON de
    `data/boards/` porte un `TileId`, pas le flag), donc le scan monte un runner par board --
    et le dispose aussitot."""
    sid, rpc = _rpc_factory()
    from engine.entities.pathfinding.board import Board
    out = {}
    for bid in board_ids:
        rid, _sf, _u = _build(bid, seed, "scan_%s" % bid, list(grafts or FLY_GRAFTS), foes)
        try:
            bg = rpc(sid, "boardGraph", {"runnerId": rid}, 90)
            brd = Board(bg["tiles"], adjacency="native_sym")
            pairs = _detour_pairs(brd, want)
            nwall = sum(1 for t in bg["tiles"] if t.get("isWall"))
            npairs = sum(len(v) for v in pairs.values())
            walls = sorted((t["col"], t["row"]) for t in bg["tiles"] if t.get("isWall"))
            out[bid] = {"walls": nwall, "srcs": len(pairs), "pairs": npairs,
                        "sample": sorted(pairs)[:6], "wallPos": walls,
                        "tiles": [(t["col"], t["row"], bool(t.get("walkable")),
                                   bool(t.get("isWall")), t.get("elevation"))
                                  for t in bg["tiles"]]}
            print("   %-14s murs=%-3d departs_detour=%-3d couples=%-4d ex=%s"
                  % (bid, nwall, len(pairs), npairs, sorted(pairs)[:6]))
            print("      murs @ %s" % (walls,))
        finally:
            try:
                rpc(sid, "disposeRunner", {"runnerId": rid}, 60)
            except Exception:
                pass
    return out


def volet_port(board_id: str, seed: int, grafts: list, foes: list, modes: list,
               trials: int) -> dict:
    """VOLET PORT -- la CHAINE COMPLETE cote python (`MovementHandler.visit_MoveUnitMessage`,
    le chemin du runner), sur l'etat de depart d'une VRAIE bataille.

    C'est LUI que `--mutate-fly` fait diverger : les bras natifs ne dependent pas du port,
    donc une contre-epreuve qui ne s'appliquerait qu'a eux ne prouverait rien. Ici le mutant
    NIE l'asymetrie et le bras `fly/2` doit passer de 0 % a ~30 % -- soit exactement le
    desaccord avec le natif mesure a 0 / 20."""
    import copy
    from engine.entities.pathfinding.board import Board
    from engine.runner.events import EventBus
    from engine.runner.operations.movement import MovementHandler
    from engine.runner.components import UnitComponent
    from engine.runner.prng import IntBasedMersenneTwister

    rid, _sf, grafts = _build(board_id, seed, "port_%s_%d" % (board_id, seed), grafts, foes)
    sid, rpc = _rpc_factory()
    print("== VOLET PORT  board=%s seed=%d  runner=%s (%d graines/porteur)"
          % (board_id, seed, rid, trials))
    out = {}
    try:
        bg = rpc(sid, "boardGraph", {"runnerId": rid}, 90)
        brd = Board(bg["tiles"], adjacency="native_sym")
        base, dv, _ob = _port_state(sid, rpc, rid, brd)
        carriers = sorted(_carriers(dv, grafts))
        for mode, want in modes:
            morts, essais, skipped = 0, 0, 0
            for uid in carriers:
                legal = _legal_moves(sid, rpc, rid, uid)
                got = _pick(base, brd, uid, legal, mode, want)
                if got is None:
                    skipped += 1
                    continue
                dest, _info = got
                for t in range(trials):
                    st = copy.deepcopy(base)
                    st.rng = IntBasedMersenneTwister(seed=1000 * want + 7 * t + uid)
                    h = MovementHandler(st, EventBus())

                    class _Msg:                      # le message que le runner poste
                        unit_id = uid
                        to = dest
                    h.visit_MoveUnitMessage(_Msg())
                    e = st.get_entity(int(uid))
                    uc = e.get_component(UnitComponent) if e is not None else None
                    essais += 1
                    morts += 0 if (uc is None or uc.alive) else 1
            pct = (100.0 * morts / essais) if essais else 0.0
            out["%s/%d" % (mode, want)] = {"morts": morts, "essais": essais, "pct": pct,
                                           "skipped": skipped}
            print("     %-6s d=%d : %d mort(s) / %d essai(s) = %.1f %%  (%d porteur(s) sans "
                  "trajet)" % (mode, want, morts, essais, pct, skipped))
    finally:
        try:
            rpc(sid, "disposeRunner", {"runnerId": rid}, 60)
        except Exception:
            pass
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scan", default="",
                    help="diagnostic de board(s) (liste d'ids) : combien de trajets DETOURNES")
    ap.add_argument("--n-grafts", type=int, default=5,
                    help="nombre de greffons (certains boards n'ont que 4 spawns joueur)")
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--detour-board", default="C6_25",
                    help="board offrant des trajets DETOURNES a d=2. Les murs (`HulkWall` / "
                         "`HulkDoor`) sont le SEUL obstacle que le vol contourne, et ils ne "
                         "vivent que sur 17 boards `C6_*` -- dont UN SEUL, `C6_25` (7 departs, "
                         "14 couples), en produit reellement. C6_09 a pourtant 16 murs et ZERO "
                         "trajet detourne : sa barriere coupe le plateau, donc les paires « a "
                         "travers » sont DECONNECTEES et les autres directes. `--scan` le mesure.")
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--foes", default="tauCrisis")
    ap.add_argument("--turns", type=int, default=5)
    ap.add_argument("--detour", action="store_true", help="joue AUSSI le bras VD")
    ap.add_argument("--only", default="", help="sous-ensemble des bras (M2,V2,V3,VD)")
    ap.add_argument("--mutate-fly", action="store_true",
                    help="CONTRE-EPREUVE : la branche volante rend `path.Count` comme la "
                         "marcheuse (asymetrie NIEE). Avec --port, `fly/2` doit passer de "
                         "0 %% a ~30 %% -- c'est-a-dire DIVERGER du natif mesure a 0 / 20.")
    ap.add_argument("--port", action="store_true",
                    help="VOLET PORT : joue les mouvements cote python (chaine complete)")
    ap.add_argument("--trials", type=int, default=40)
    ap.add_argument("--json", default="")
    a = ap.parse_args()

    if a.mutate_fly:
        # On NIE l'asymetrie : le volant repasse par la branche marcheuse (`pas + 1`). C'est
        # exactement le port qu'on obtiendrait en ne lisant pas le ternaire d'`Execute`.
        from engine.runner.operations import movement as MV
        _orig_num = MV._num_tiles_moved

        def _no_fly(state, mover_id, from_pos, to_pos):
            n = _orig_num(state, mover_id, from_pos, to_pos)
            return n + 1 if n > 0 else 0
        MV._movement_steps = _no_fly
        print("!! CONTRE-EPREUVE --mutate-fly : branche volante NIEE (path.Count partout)")

    bad = etape0()
    print("   etape 0 : %d anomalie(s)" % bad)
    if a.offline:
        return 1 if bad else 0

    foes = [s for s in a.foes.split(",") if s]
    fly = FLY_GRAFTS[:a.n_grafts]
    walk = WALK_GRAFTS[:a.n_grafts]
    if a.scan:
        print("== SCAN de boards (trajets DETOURNES a d=2)")
        res = scan([s.strip() for s in a.scan.split(",") if s.strip()], a.seed, foes, grafts=fly)
        if a.json:
            pathlib.Path(a.json).write_text(json.dumps(res, indent=1), encoding="utf-8")
        return 1 if bad else 0
    if a.port:
        res = volet_port(a.board, a.seed, fly, foes, [("fly", 2), ("fly", 3)], a.trials)
        if a.json:
            pathlib.Path(a.json).write_text(json.dumps(res, indent=1), encoding="utf-8")
        return 1 if bad else 0
    want = {k: True for k in (a.only.split(",") if a.only else ["M2", "V2", "V3"])}
    if a.detour and not a.only:
        want["VD"] = True

    out = {}
    if want.get("M2"):
        out["M2"] = bras("M2", a.board, a.seed, walk, foes, "walk", 2, a.turns)
    if want.get("V2"):
        out["V2"] = bras("V2", a.board, a.seed, fly, foes, "fly", 2, a.turns)
    if want.get("V3"):
        out["V3"] = bras("V3", a.board, a.seed, fly, foes, "fly", 3, a.turns)
    if want.get("VD"):
        out["VD"] = bras("VD", a.detour_board, a.seed, fly, foes, "flyd", 2, a.turns)

    print("\n== SYNTHESE (natif)")
    for k in ("M2", "V2", "V3", "VD"):
        b = out.get(k)
        if b:
            print("   %-3s %-4s d=%d : %2d mort(s) / %2d essai(s) = %5.1f %%"
                  % (k, b["mode"], b["want"], b["morts"], b["essais"], b["pct"]))
    if a.json:
        pathlib.Path(a.json).write_text(json.dumps(out, indent=1), encoding="utf-8")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
