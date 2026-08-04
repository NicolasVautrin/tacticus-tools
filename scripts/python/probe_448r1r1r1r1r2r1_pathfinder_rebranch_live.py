"""#448-r1-r1-r1-r1-r2-r1 -- CE QUE LE REBRANCHEMENT DES PATHFINDERS SUR `ConnectivityComponent`
DEPLACE, chiffre par SITE, et sa CONFRONTATION au natif.

LE CRITERE, pose AVANT la methode
---------------------------------
#584 a prouve que le canal TRANSPORTE (`C \\ N` = 18 aretes sur `MC1_67`, `G \\ C` = 16 sur
`C1_74`). Ca ne dit RIEN de ce qu'un rebranchement change : un substrat plus juste peut etre
INERTE si le predicat d'arete du pathfinder re-filtre deja ce qui differe. La question binaire
est donc **par site**, pas globale :

    pour CHAQUE route qui herite `BasePathfinder$$AddNeighbours`, changer son voisinage
    de son substrat actuel vers le canal brut change-t-il un RESULTAT observable ?

Les trois vues, comme dans #584 :

    G = `neighbours_geometric`  (couronne hex, aucune porte)
    N = `neighbours`            (`BattleQuery$$GetAdjacentTiles` -> porte `|delev| < 2`)
    C = `connectivity`          (`ConnectivityComponent`, critere `TileComponent$$HasEdge`)

et la relation d'inclusion mesuree : `N <= C <= G`.

LA PREDICTION, ecrite avant de mesurer, et ce qui la REFUTERAIT
--------------------------------------------------------------
Elle se DERIVE du decompile, elle n'est pas un pari :
`IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext` itere la MEME
liste stockee que `BasePathfinder.u003CAddNeighboursu003Ed__19$$MoveNext`, puis applique
`IsTemporary` / `IsWalkable` / `IsEmptyOrSteppable` (les trois OFF pour le capteur, qui appelle
`GetAdjacentTiles(tile, false, false, true)`) et une porte `|delev| < 2` INCONDITIONNELLE. Donc

    N == C INTERSECTE {aretes de |delev| < 2}                       (cran D2)

  * routes a PORTE D'ELEVATION (`Walk` : `IsReachableElevationDifference` ; `IgnoreTerrain` :
    `|delev| <= 1`) -> le canal n'ajoute QUE des aretes que leur propre predicat refuse
    -> **NO-OP EXACT, sur tout board** (crans D3, D4 : attendu 0).
    REFUTATION : une seule arete de `C \\ N` avec `|delev| < 2` (cran D2) fait tomber le no-op.
  * route `Beeline` (`IgnoreEverythingPathfinder`) : son `IsValidPathNode` est le corps TRIVIAL
    `return true`, il ne re-filtre RIEN. Elle lisait `G`, sur-ensemble strict de `C`
    -> **elle MORD, et exactement la ou `G \\ C != 0`** (cran D5 : attendu > 0 sur `C1_74`).
    REFUTATION : `D5 == 0` sur un board a `G \\ C != 0` voudrait dire que les aretes en trop sont
    toutes contournables a longueur egale -- le rebranchement serait alors cosmetique.

⚠ REGIME DEGENERE, deja paye sur ce sujet : sur `C6_25` les TROIS vues coincident (316/316/316).
Un rebranchement valide sur ce seul board rendrait un accord parfait sans rien etablir. Il est
garde ici comme TEMOIN (D5 doit y valoir 0), jamais comme preuve.

LE CRAN QUI CONFRONTE LE NATIF (`--only NATIVE`)
------------------------------------------------
Les crans D1-D6 comparent le port a lui-meme : ils disent ce qui BOUGE, pas qui a RAISON. Le
natif tranche par un scalaire deja etabli (#448-r1-r1-r1-r1) :
`IdunBattle.Core.Services.MovementQuery$$GetConnectedPathTo` recoit `[from, to]` pour un porteur
`TeleportStrike` (`ATeleportPathfinder$$FindPath` rend litteralement les deux extremites) puis
recoud le saut par une BEELINE. Donc

    tilesMovedThisTurn == nombre d'ARETES du chemin BEELINE de `from` a `to`

et c'est un oracle DIRECT du substrat de la beeline. Sur `C1_74`, on cherche une destination ou
`beeline(G)` et `beeline(C)` n'ont PAS la meme longueur, et le natif departage.

Usage (session warmee) :
    python probe_448r1r1r1r1r2r1_pathfinder_rebranch_live.py                    # STRUCT, 3 boards
    python probe_448r1r1r1r1r2r1_pathfinder_rebranch_live.py --only NATIVE
    python probe_448r1r1r1r1r2r1_pathfinder_rebranch_live.py --only NATIVE --mutate-geometric
ASCII only.
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

# `C1_74` porte les deux `Bridge` -> c'est le SEUL des trois ou `G \ C != 0`, donc le seul qui
# puisse faire mordre la beeline. `MC1_67` a `C \ N = 18` et `G \ C = 0` : il discrimine le no-op
# des routes a porte d'elevation. `C6_25` est le TEMOIN degenere (les trois vues coincident).
BOARDS = ("C1_74", "MC1_67", "C6_25")

# Porteur de la confrontation native : `bloodIntercessor` sort en `PathfinderType 7`
# (`TeleportStrike` + `Flying`), donc son `FindPath` rend `[from, to]` et TOUT le trajet est
# recousu par la beeline -- le regime ou le compteur natif EST la longueur beeline.
#
# ⚠ LES DEUX FIGURANTS NE SONT PAS UN DETAIL DE ROSTER. Le move de la DERNIERE unite activable
# fait basculer le tour, donc `ActorStatisticsComponent$$ResetThisTurn` remet `+0xf0` a ZERO pour
# TOUT LE MONDE -- y compris celle qu'on vient de bouger. Avec le porteur SEUL cote joueur, la
# lecture `after` vaut 0 a CHAQUE mesure et se lit comme « le natif n'a rien enregistre » : mesure
# vecue ici, 7 pseudo-desaccords d'affilee. Les figurants gardent une unite activable APRES le
# move, donc le tour ne bascule pas pendant la mesure.
NATIVE_UNIT = "bloodIntercessor"
NATIVE_FILLERS = ["blackHaarken", "necroWarden"]
NATIVE_FOES = ["necroWarden"]


def _rpc_factory():
    from rl_collect_batch import _resolve_session, _rpc

    def rpc(sid, m, args, t=180):
        r = _rpc(sid, m, [args], timeout=t)
        return (r.get("result") if isinstance(r, dict) and "result" in r else r) or {}
    return _resolve_session(), rpc


def _build(board: str, seed: int, tag: str, units=None, foes=None):
    """Build tolerant au nombre de spawns joueur (les `C6_*` en ont 3 a 5)."""
    LOGSDIR.mkdir(parents=True, exist_ok=True)
    state_file = LOGSDIR / ("p448r1r1r1r1r2r1_state_%s.json" % tag)
    p = None
    if units:
        state_file.unlink(missing_ok=True)
        cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--rank", "17",
               "--board", board, "--p-units", ",".join(units), "--a-units", ",".join(foes or []),
               "--no-ai", "--state-file", str(state_file)]
        p = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if state_file.exists():
            return int(json.loads(state_file.read_text(encoding="utf-8"))["runnerId"]), state_file
    else:
        for roster in (5, 4, 3, 2, 1):
            state_file.unlink(missing_ok=True)
            cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--rank", "17",
                   "--board", board, "--no-ai", "--roster", str(roster),
                   "--state-file", str(state_file)]
            p = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                               encoding="utf-8", errors="replace")
            if state_file.exists():
                return (int(json.loads(state_file.read_text(encoding="utf-8"))["runnerId"]),
                        state_file)
            if "spawns joueur <" not in ((p.stdout or "") + (p.stderr or "")):
                break
    sys.stdout.write(((p.stdout if p else "") or "")[-1500:])
    sys.stdout.write(((p.stderr if p else "") or "")[-1500:])
    raise SystemExit("build KO (%s)" % tag)


# --------------------------------------------------------------------------- VOLET STRUCT
def _views(board):
    """Les trois vues, en dict `{tile_id -> set(tile_id)}` -- `C` vaut `None` si le canal n'est
    pas capte (TRI-ETAT : on ne fabrique jamais un graphe vide qui se lirait comme une mesure)."""
    G = {t: set(board.neighbours_geometric(t)) for t in board.by_id}
    N = {t: set(board.neighbours_native(t)) for t in board.by_id}
    if not board.has_connectivity_channel():
        return G, N, None
    C = {}
    for t in board.by_id:
        c = board.neighbours_connectivity(t)
        C[t] = set(c if c is not None else N[t])
    return G, N, C


def _walk_stop_sets(board, neighbours, depths):
    """`{(start, depth) -> frozenset(stop)}` du `WalkPathfinder`, sur un board VIDE d'occupants
    (le voisinage est la SEULE variable de la comparaison)."""
    from engine.entities.pathfinding.walk_pathfinder import get_movable_positions
    out = {}
    for start in board.by_id:
        for d in depths:
            _v, stop = get_movable_positions(board, start, d, {}, 1, neighbours=neighbours)
            out[(start, d)] = frozenset(stop)
    return out


def _ignore_terrain_counts(board, use_channel: bool):
    """`{(target, tile) -> Count}` de `IgnoreTerrainPathfinder`. Le substrat se pilote en
    substituant `Board.base_add_neighbours` -- c'est le foyer que la route consomme."""
    from engine.entities.pathfinding import ignore_terrain_pathfinder as IT
    from engine.entities.pathfinding.board import Board
    orig = Board.base_add_neighbours
    if not use_channel:
        Board.base_add_neighbours = lambda self, tid, fallback=None: self.neighbours_native(tid)
    try:
        out = {}
        for target in board.by_id:
            for tile, n in IT.get_path_node_counts(board, target, {}).items():
                out[(target, tile)] = n
        return out
    finally:
        Board.base_add_neighbours = orig


def _beeline_lengths(board, neighbours):
    """`{(from, to) -> aretes}` de la `Beeline` sur TOUS les couples ordonnes. `None` = pas de
    chemin (impossible ici : le predicat est trivial, mais on ne le suppose pas)."""
    from engine.entities.pathfinding import base_pathfinder as BP
    from engine.entities.pathfinding import beeline_pathfinder as BL
    out = {}
    ids = sorted(board.by_id)
    for a in ids:
        for b in ids:
            if a == b:
                continue
            p = BP.find_path(board, a, b, edge=BL.is_valid_path_node, neighbours=neighbours,
                             weight_cost=lambda tid: BL.WEIGHT_BASE,
                             is_valid_final_tile=lambda tid: True)
            out[(a, b)] = None if p is None else len(p) - 1
    return out


def run_struct(sid, rpc, board_id: str, seed: int, verbose: bool):
    from engine.entities.pathfinding.board import Board
    rid, state_file = _build(board_id, seed, "struct_%s" % board_id)
    bad = 0
    resume = {}
    try:
        res = rpc(sid, "boardGraph", {"runnerId": rid}, 180)
        if not res.get("ok"):
            print("  boardGraph KO: %s" % res.get("error"))
            return 1, {}
        (LOGSDIR / ("p448r1r1r1r1r2r1_bg_%s.json" % board_id)).write_text(
            json.dumps(res), encoding="utf-8")
        bd = Board(res["tiles"], adjacency="native_sym")
        G, N, C = _views(bd)
        if C is None:
            print("  CANAL ABSENT du boardGraph -- rien n'est interpretable (NON MESURE)")
            return 1, {}
        elev = {t["id"]: int(t.get("elevation") or 0) for t in res["tiles"]}

        # --- D1 : les inclusions. Elles fondent tout le reste.
        n_nc = sum(len(N[t] - C[t]) for t in bd.by_id)      # N \ C  : doit etre 0
        n_cg = sum(len(C[t] - G[t]) for t in bd.by_id)      # C \ G  : doit etre 0
        n_cn = sum(len(C[t] - N[t]) for t in bd.by_id)
        n_gc = sum(len(G[t] - C[t]) for t in bd.by_id)
        print("  [D1] N\\C=%d (attendu 0)  C\\G=%d (attendu 0)  |  C\\N=%d  G\\C=%d"
              % (n_nc, n_cg, n_cn, n_gc))
        bad += (0 if n_nc == 0 else 1) + (0 if n_cg == 0 else 1)

        # --- D2 : LE cran du no-op. `C \ N` ne doit contenir QUE des |delev| >= 2, sinon la
        #     porte du capteur n'est pas la seule difference et les routes a porte d'elevation
        #     ne sont plus inertes.
        mauvaises = [(a, b) for a in bd.by_id for b in sorted(C[a] - N[a])
                     if abs(elev[a] - elev[b]) < 2]
        print("  [D2] aretes C\\N avec |delev| < 2 : %d (attendu 0)" % len(mauvaises))
        bad += 0 if not mauvaises else 1
        for (a, b) in mauvaises[:12]:
            print("        %s -> %s  |delev|=%d" % (bd.coord(a), bd.coord(b),
                                                    abs(elev[a] - elev[b])))

        # --- D3 : MARCHE. Substrat N vs C, sur toutes les tuiles de depart x 3 portees.
        depths = (3, 5, 8)
        w_n = _walk_stop_sets(bd, bd.neighbours_native, depths)
        w_c = _walk_stop_sets(bd, lambda t: bd.base_add_neighbours(t), depths)
        d3 = sorted(k for k in w_n if w_n[k] != w_c[k])
        delta3 = sum(len(w_c[k] ^ w_n[k]) for k in d3)
        print("  [D3] MARCHE : %d couple(s) (start,depth) sur %d changent ; %d tuile(s) en ecart "
              "(attendu 0 -- no-op prouve par D2)" % (len(d3), len(w_n), delta3))
        resume["walk_changed"] = len(d3)
        if d3 and not mauvaises:
            print("        ECART: D2 vert mais la marche bouge -> la derivation du no-op est FAUSSE")
            bad += 1
        for k in d3[:6]:
            print("        start=%s depth=%d : %d tuile(s)" % (bd.coord(k[0]), k[1],
                                                               len(w_c[k] ^ w_n[k])))

        # --- D4 : IGNORE_TERRAIN (l'utilite IA `MinDistanceToClosestEnemyUtility`).
        it_n = _ignore_terrain_counts(bd, use_channel=False)
        it_c = _ignore_terrain_counts(bd, use_channel=True)
        d4 = sorted(set(it_n) ^ set(it_c)) + sorted(k for k in set(it_n) & set(it_c)
                                                    if it_n[k] != it_c[k])
        print("  [D4] IGNORE_TERRAIN : %d distance(s) sur %d changent (attendu 0)"
              % (len(d4), len(it_n)))
        resume["ignore_terrain_changed"] = len(d4)
        if d4 and not mauvaises:
            print("        ECART: D2 vert mais les distances bougent -> derivation du no-op FAUSSE")
            bad += 1
        for k in d4[:6]:
            print("        target=%s tile=%s : %s -> %s" % (bd.coord(k[0]), bd.coord(k[1]),
                                                            it_n.get(k), it_c.get(k)))

        # --- D5 : BEELINE. C'est le site qui MORD, et il mord la ou `G \ C != 0`.
        bl_g = _beeline_lengths(bd, bd.neighbours_geometric)
        bl_c = _beeline_lengths(bd, lambda t: bd.base_add_neighbours(t, bd.neighbours_geometric))
        d5 = sorted(k for k in bl_g if bl_g[k] != bl_c[k])
        print("  [D5] BEELINE : %d couple(s) (from,to) sur %d changent de longueur ; "
              "G\\C=%d %s" % (len(d5), len(bl_g), n_gc,
                              "(attendu > 0)" if n_gc else "(attendu 0 -- pas d'arete en trop)"))
        resume["beeline_changed"] = len(d5)
        resume["G_moins_C"] = n_gc
        resume["C_moins_N"] = n_cn
        if n_gc == 0 and d5:
            print("        ECART: aucune arete en trop mais la beeline bouge -- incoherent")
            bad += 1
        if n_gc > 0 and not d5:
            print("        ECART: %d arete(s) en trop et AUCUN couple ne change -- le "
                  "rebranchement serait cosmetique, a expliquer" % n_gc)
            bad += 1
        deltas = {}
        for k in d5:
            deltas[(bl_c[k] or -1) - (bl_g[k] or -1)] = deltas.get(
                (bl_c[k] or -1) - (bl_g[k] or -1), 0) + 1
        if d5:
            print("        distribution des ecarts (C - G) : %s"
                  % ", ".join("%+d : %d couple(s)" % kv for kv in sorted(deltas.items())))
            for k in (d5 if verbose else d5[:8]):
                print("        %s -> %s : G=%s  C=%s" % (bd.coord(k[0]), bd.coord(k[1]),
                                                          bl_g[k], bl_c[k]))
        return bad, resume
    finally:
        try:
            rpc(sid, "disposeRunner", {"runnerId": rid}, 60)
        except Exception:
            pass
        state_file.unlink(missing_ok=True)


# --------------------------------------------------------------------------- VOLET NATIVE
def _actor_stats(sid, rpc, rid) -> dict:
    return rpc(sid, "actorStats", {"runnerId": rid}, 60)


def _turn_counter(ast: dict, uid: int):
    """`tilesMovedThisTurn`, ou `None` = NON MESURE (jamais 0 par defaut)."""
    for u in ((ast or {}).get("units") or []):
        if u.get("entityId") is not None and int(u["entityId"]) == int(uid):
            v = u.get("tilesMovedThisTurn")
            return None if v is None else int(v)
    return None


def run_native(sid, rpc, board_id: str, seed: int, mutate: str, max_turns: int):
    """Le natif departage G et C, par un scalaire.

    Montage : un porteur `TeleportStrike` (pool board-wide, donc AUCUNE destination n'est
    interdite par la geometrie de spawn) sur `C1_74`. Pour chaque destination legale on calcule
    les DEUX longueurs de beeline ; on ne joue QUE celles ou elles different, et on lit
    `tilesMovedThisTurn`.
    """
    import hexgeo
    from engine.entities.pathfinding import base_pathfinder as BP
    from engine.entities.pathfinding import beeline_pathfinder as BL
    from engine.entities.pathfinding.board import Board
    from engine.runner.components import PositionComponent
    from engine.runner.operations.movement import _num_tiles_moved
    # Le montage (etat porte + tuiles legales + porteurs) est celui de `#448-r1-r1-r1`, deja
    # valide : `_port_state` y exige `board=` ET `ability_states=`, faute de quoi le compte de
    # pas court-circuite a 0 SANS erreur.
    import probe_448_r1_r1_r1_flying_movement_steps as P

    rid, state_file = _build(board_id, seed, "native_%s" % board_id,
                             units=[NATIVE_UNIT] + NATIVE_FILLERS, foes=NATIVE_FOES)
    print("== NATIVE  board=%s seed=%d unit=%s runner=%s mutate=%s"
          % (board_id, seed, NATIVE_UNIT, rid, mutate or "-"))
    accord = desaccord = joues = 0
    # Sans cette memoire, le porteur fait l'aller-retour entre les deux MEMES tuiles et rend
    # N fois LA MEME mesure : un seul cas discriminant repete, qui ne generalise rien.
    vus: set = set()
    temoins = 0
    try:
        bg = rpc(sid, "boardGraph", {"runnerId": rid}, 120)
        bd = Board(bg["tiles"], adjacency="native_sym")
        if not bd.has_connectivity_channel():
            print("   CANAL ABSENT -- NON MESURE")
            return 1
        if mutate == "geometric":
            Board.base_add_neighbours = (
                lambda self, tid, fallback=None: self.neighbours_geometric(tid))
        elif mutate == "native":
            Board.base_add_neighbours = (
                lambda self, tid, fallback=None: self.neighbours_native(tid))

        def blen(nb, a, b):
            p = BP.find_path(bd, a, b, edge=BL.is_valid_path_node, neighbours=nb,
                             weight_cost=lambda tid: BL.WEIGHT_BASE,
                             is_valid_final_tile=lambda tid: True)
            return None if p is None else len(p) - 1

        for turn in range(max_turns):
            state, dv, _ob = P._port_state(sid, rpc, rid, bd)
            to_act = [int(u) for u in (dv.get("toActivate") or [])]
            carriers = P._carriers(dv, [NATIVE_UNIT])
            cand = [u for u in to_act if u in carriers]
            if not cand:
                # Le porteur a deja joue, ou c'est au camp adverse (`--no-ai` : son tour ne se
                # joue pas tout seul). On rend la main et on ATTEND son prochain tour -- ne pas
                # sortir ici, sinon un simple pas d'approche coute toute la mesure.
                if not to_act:
                    print("   t%d : toActivate vide -> fin" % turn)
                    break
                print("   t%d : porteur non activable (%d autre(s) a jouer) -> endturn"
                      % (turn, len(to_act)))
                rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 120)
                continue
            uid = cand[0]
            e = state.get_entity(int(uid))
            pc = e.get_component(PositionComponent)
            src = (pc.col, pc.row)
            stid = bd.id_at(*src)
            legal = P._legal_moves(sid, rpc, rid, uid)
            # Les destinations DISCRIMINANTES : celles ou les deux substrats ne donnent pas la
            # meme longueur de beeline. On les joue par ecart DECROISSANT (le plus lisible
            # d'abord) -- jamais une destination ou les deux modeles coincident, qui ne
            # trancherait rien (regime degenere).
            disc, plats = [], []
            for d in legal:
                tid = bd.id_at(int(d[0]), int(d[1]))
                if tid is None or tid == stid:
                    continue
                # ⚠ `GetConnectedPathTo` ne recoud QUE `if (GetDistance(last, next) > 1)`. A
                # distance 1 la beeline n'est JAMAIS appelee : le couple ne discrimine RIEN du
                # substrat, quoi qu'en disent les deux longueurs. Mesure vecue : `(6,5)->(5,5)`
                # rend NATIF=1 avec `beeline(G)=1` et `beeline(C)=2` -- lu sans ce filtre, il
                # s'etiquetait « GEOMETRIE » et accusait a tort le canal.
                if hexgeo.distance(src, (int(d[0]), int(d[1]))) <= 1:
                    continue
                lg = blen(bd.neighbours_geometric, stid, tid)
                lc = blen(lambda t: bd.neighbours_connectivity(t) or [], stid, tid)
                ln = blen(bd.neighbours_native, stid, tid)
                if lg is None or lc is None or ln is None:
                    continue
                # DISCRIMINANT = les TROIS vues ne s'accordent pas. Discriminer sur le seul couple
                # (G, C) rendrait le bras `--mutate-native` incapable de mordre sur `MC1_67`, ou
                # `G == C` mais `N != C` : chaque mutant a SON gisement, et un mutant qui ne mord
                # pas parce qu'on l'a joue sur le mauvais board ne prouve RIEN.
                # ORDRE DE PREFERENCE, et il n'est pas cosmetique : un couple ou `G != C`
                # departage les deux vues que LE REBRANCHEMENT oppose ; un couple ou seul `N`
                # differe ne tranche que le vieux champ ampute. Trier sur le seul ecart MAXIMAL
                # noie le premier cas sous le second des que `C \ N` > `G \ C` -- ce qui est le
                # regime de `C1_74` (58 contre 16) : mesure vecue, un run de 22 tours n'y a rendu
                # que des `AMBIGU (G+C)`. La cle met donc `lg != lc` en tete.
                (disc if len({lg, lc, ln}) > 1 else plats).append(
                    ((1 if lg != lc else 0, max(abs(lc - lg), abs(lc - ln))), d, lg, lc, ln))
            # Couples DEJA mesures ecartes, et ecart decroissant a egalite -- on veut des cas
            # DIFFERENTS, pas le meme aller-retour N fois.
            disc = [x for x in disc if (src, (int(x[1][0]), int(x[1][1]))) not in vus]
            disc.sort(reverse=True)
            plats = [x for x in plats if x[2] >= 2
                     and (src, (int(x[1][0]), int(x[1][1]))) not in vus]
            plats.sort(reverse=True)
            print("   t%d u%s src=%s : %d destination(s) legale(s), %d DISCRIMINANTE(s) inedite(s)"
                  % (turn, uid, src, len(legal), len(disc)))
            # Un TEMOIN sur deux mesures : une destination ou les deux substrats COINCIDENT.
            # Sans lui on ne mesurerait que le regime qui change, et un port casse hors de ce
            # regime passerait inapercu.
            if disc and plats and joues and joues % 2 == 0:
                disc = plats
                temoins += 1
            if not disc:
                # On DEPLACE pour construire la configuration au lieu de conclure « geometrie
                # defavorable » : un pas vers la tuile la plus proche d'un `Bridge`.
                br = [t["id"] for t in bg["tiles"] if t.get("tileDefId") == "Bridge"]
                if br and legal:
                    tgt = bd.coord(br[0])
                    step = min(legal, key=lambda d: hexgeo.distance((d[0], d[1]), tgt))
                    rpc(sid, "applyAction", {"runnerId": rid, "action": {
                        "kind": "move", "unitId": int(uid),
                        "to": {"col": int(step[0]), "row": int(step[1])}}}, 120)
                    print("      APPROCHE -> %s (Bridge en %s)" % (step, tgt))
                rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 120)
                continue
            _gap, dest, lg, lc, ln = disc[0]
            vus.add((src, (int(dest[0]), int(dest[1]))))
            port_n = _num_tiles_moved(state, int(uid), src, (int(dest[0]), int(dest[1])))
            before_all = _actor_stats(sid, rpc, rid)
            before = _turn_counter(before_all, uid)
            rpc(sid, "applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": int(uid),
                "to": {"col": int(dest[0]), "row": int(dest[1])}}}, 120)
            after_all = _actor_stats(sid, rpc, rid)
            after = _turn_counter(after_all, uid)
            b_all = {int(u["entityId"]): u.get("tilesMovedThisTurn")
                     for u in ((before_all or {}).get("units") or [])
                     if u.get("entityId") is not None}
            a_all = {int(u["entityId"]): u.get("tilesMovedThisTurn")
                     for u in ((after_all or {}).get("units") or [])
                     if u.get("entityId") is not None}
            reset = any(k != int(uid) and a_all.get(k) is not None and b_all.get(k) is not None
                        and a_all[k] < b_all[k] for k in b_all)
            nat = None if (before is None or after is None) else after - before
            # DEUXIEME discriminant du `ResetThisTurn`, et le seul qui marche quand le porteur
            # est la seule unite a avoir bouge (aucune AUTRE ne peut alors « diminuer ») : un
            # move REEL vers une tuile differente enregistre au moins 1 pas -- `RecordTilesMoved`
            # ne fait que `+=` et sort sur `if (tiles < 1) return`. Un delta NUL n'est donc pas
            # une mesure, c'est le compteur remis a zero sous nos pieds.
            if nat == 0 and (int(dest[0]), int(dest[1])) != src:
                reset = True
            if reset or nat is None:
                print("      %s -> %s : NON MESURE (ResetThisTurn=%s, capteur=%s/%s)"
                      % (src, dest, reset, before, after))
                rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 120)
                continue
            joues += 1
            # Le verdict nomme la vue que le NATIF suit. `CANAL` seul quand elle est la seule a
            # coller ; si plusieurs coincident, on le DIT plutot que d'attribuer au hasard.
            colle = [nom for nom, v in (("G", lg), ("C", lc), ("N", ln)) if nat == v]
            verdict = ("TEMOIN (G==C==N)" if len({lg, lc, ln}) == 1 else
                       "NI L'UNE NI L'AUTRE" if not colle else
                       {"G": "GEOMETRIE", "C": "CANAL", "N": "CHAMP AMPUTE"}[colle[0]]
                       if len(colle) == 1 else "AMBIGU (%s)" % "+".join(colle))
            ok = (nat == port_n)
            accord += 1 if ok else 0
            desaccord += 0 if ok else 1
            print("      %s -> %s : NATIF=%d  beeline G=%d C=%d N=%d  PORT=%d  -> %s  %s"
                  % (src, dest, nat, lg, lc, ln, port_n, verdict, "OK" if ok else "DESACCORD"))
            rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 120)
    finally:
        try:
            rpc(sid, "disposeRunner", {"runnerId": rid}, 60)
        except Exception:
            pass
        state_file.unlink(missing_ok=True)
    print("   -> NATIVE : %d accord(s) / %d mesure(s), dont %d temoin(s) non discriminant(s)"
          % (accord, joues, temoins))
    if joues - temoins == 0:
        print("   AUCUNE mesure DISCRIMINANTE -- NON CONFRONTE (ne rien conclure)")
        return 1
    return 0 if desaccord == 0 else desaccord


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=("STRUCT", "NATIVE"), default="STRUCT")
    ap.add_argument("--board", action="append", default=None)
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--turns", type=int, default=6)
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--mutate-geometric", action="store_true",
                    help="CONTRE-EPREUVE : rebranche tout sur la GEOMETRIE (l'etat d'avant).")
    ap.add_argument("--mutate-native", action="store_true",
                    help="CONTRE-EPREUVE : rebranche tout sur le champ AMPUTE `neighbours`.")
    a = ap.parse_args()
    mutate = "geometric" if a.mutate_geometric else ("native" if a.mutate_native else "")
    sid, rpc = _rpc_factory()
    print("== #448-r1-r1-r1-r1-r2-r1 -- ce que le rebranchement DEPLACE   session=%s" % sid)
    if a.only == "NATIVE":
        return run_native(sid, rpc, (a.board or ["C1_74"])[0], a.seed, mutate, a.turns)
    boards = a.board or list(BOARDS)
    bad = 0
    resume = {}
    for b in boards:
        print("\n-- board %s" % b)
        n, r = run_struct(sid, rpc, b, a.seed, a.verbose)
        bad += n
        resume[b] = r
    print("\n== RESUME  (ce que le rebranchement DEPLACE, par site)")
    for b, r in resume.items():
        print("   %-8s C\\N=%s G\\C=%s | marche=%s  ignore_terrain=%s  BEELINE=%s"
              % (b, r.get("C_moins_N"), r.get("G_moins_C"), r.get("walk_changed"),
                 r.get("ignore_terrain_changed"), r.get("beeline_changed")))
    # DEUX causes distinctes derriere un « rien ne bouge », et les confondre est le piege :
    #   * aucun board du RUN n'a `G \ C != 0` -> le run est DEGENERE, il ne pouvait rien montrer
    #     (c'est le cas de `MC1_67` et `C6_25` joues seuls) ;
    #   * un board a `G \ C != 0` et la beeline ne bouge quand meme pas -> la, c'est le
    #     REBRANCHEMENT qui serait cosmetique, et il faudrait l'expliquer.
    # Les deux font rougir, mais ils n'accusent pas la meme chose.
    porteurs = [b for b, r in resume.items() if (r.get("G_moins_C") or 0) > 0]
    mord = any((r.get("beeline_changed") or 0) > 0 for r in resume.values())
    if not porteurs:
        print("   run DEGENERE : aucun board joue n'a `G \\ C != 0` -- rien ne POUVAIT bouger. "
              "Rejouer avec un board a `Bridge` (ex. C1_74) avant toute conclusion.")
        bad += 1
    elif not mord:
        print("   ECART: %s porte(nt) des aretes `G \\ C` et AUCUN couple ne change -- le "
              "rebranchement serait cosmetique, a EXPLIQUER" % ",".join(porteurs))
        bad += 1
    else:
        print("   regime NON degenere : la beeline bouge sur %s"
              % ",".join(b for b, r in resume.items() if (r.get("beeline_changed") or 0) > 0))
    print("VERDICT: %s (%d ecart(s))" % ("PASS" if bad == 0 else "FAIL", bad))
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
