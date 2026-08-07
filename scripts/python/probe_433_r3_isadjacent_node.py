"""#433-r3 -- le noeud DSL `IsAdjacent` : UNIVERSEL + porte d'ELEVATION.

RE (decompile = verite). `IdunBattle.Entities.Triggers.IsAdjacentAbilityTrigger$$ShouldTrigger`,
lu instruction par instruction :

    A = <sel a>.Select(entities, selectionType)     // slot 3 ; ctor : a@+0x20, b@+0x28,
    B = <sel b>.Select(entities, selectionType)     //          selectionType@+0x18, query@+0x10
    if (A == null || B == null) throw;
    if (!A.Any() || !B.Any()) return false;
    foreach (x in A) foreach (y in B)
        if (!query.AreEntitiesAdjacent(x, y)) return false;      // slot 0x60
    return true;

TROIS ecarts du port d'AVANT, mesures SEPAREMENT ici :

  (Q) QUANTIFICATEUR -- le natif rend FAUX des qu'UNE paire ne l'est pas et VRAI quand
      l'enumeration s'epuise : un `forall`. Le port faisait `any(...)` -> divergence PERMISSIVE.
      La classe SOEUR `IdunBattle.Entities.Triggers.IsAdjacentTilesTrigger$$ShouldTrigger` est,
      elle, un `exists` (rend 1 des la premiere paire adjacente) : les deux ne se deduisent pas
      l'une de l'autre.
  (E) ELEVATION -- la comparaison par paire est
      `IdunBattle.Core.Services.BattleQuery$$AreEntitiesAdjacent` (surcharge `(entity1, entity2)`,
      slot 0x60) -> `IdunBattle.Core.Services.MovementUtil$$AreTilesAdjacent` =
      `(|dElev| < 2) & (t1 == t2 || ConnectivityComponent$$IsNeighbour(t1, t2))`. Deux voisines
      separees de 2 crans NE SONT PAS adjacentes.
  (I) IDENTITE -- le meme foyer porte le court-circuit `t1 == t2` (#433-r1).

Et le PIEGE que la fiche #433-r1 anticipait : le 3e argument de
`IdunBattleLogic.Entities.DSLTriggers$$IsAdjacent(a, b, selectionType)` part au SELECTEUR
(2e argument de son `Select`, slot 3), il n'entre PAS dans la comparaison par paire.

CE QUE LE PROBE MESURE
----------------------
  etape A (OFFLINE) -- (Q) sur un montage a DEUX paires dont une seule adjacente.
  etape B (OFFLINE) -- (E) : voisine a |dElev| >= 2 -> FAUX ; voisine PLATE -> VRAI.
  etape C (OFFLINE) -- (I) + les DEUX bornes de listes vides (le natif teste `Any()` AVANT la
      boucle : un `All` nu rendrait VRAI sur le vide, le natif rend FAUX).
  etape D (OFFLINE) -- le 3e argument est INERTE pour le predicat (balayage des valeurs).
  etape E (OFFLINE) -- degradation SANS board = adjacence hex pure, et les sites qui y retombent.
  etape F (LIVE)    -- confrontation port/natif du terme (E) a travers un CONSOMMATEUR porte :
      `IdunBattleLogic.Entities.Abilities.Active.Loki.SkyStrikeAbility$$ExecuteBehaviour` (1025),
      dont l'etage MOVE est `If(Not(IsAdjacent(caster, target)), MoveUnit(caster, dest))`.
      Celestine VOLE -> la destination (une tuile libre ring-1 de la cible) est toujours
      atteignable, donc le regime n'est jamais rabattu par le pathfinding. Montage repris de
      `probe_165b_sky_strike_border.py` (importe comme HARNAIS, jamais recopie).
      CRAN : caster et cible voisines HEX a |dElev| >= 2. Le natif ne les voit PAS adjacentes ->
      il CHARGE. Le port d'avant les voyait adjacentes -> il ne bougeait pas.
      TEMOIN : voisines PLATES -> adjacentes des deux cotes, aucun deplacement.

REGIME (Q) NON CONFRONTE LIVE, ET DIT COMME TEL : les call-sites natifs de
`DSLTriggers$$IsAdjacent` passent tous DEUX selecteurs MONO (champs du bundle Owner@+0x30 /
Actor@+0x40 / Caster@+0x48 / Target@+0x60 / Subject@+0x68, ou Self@0x148 / Caster@0x160 /
Target@0x178) -- lus sur `MedicusMinistorumAbility$$CreateTrigger`,
`SynapticImperativeAbility$$CreateTrigger`, `LifewardsAbility$$CreateTrigger`,
`TerrorsLament_HitReductionEffect$$CreateEffectHitsBonusForAttack`,
`LegendaryCommander_ExtraHitsEffect$$CreateTargetSelector` (sous un `Filter`, donc sujet unitaire),
`DSLFormulas$$AttackHits` (son UNIQUE appelant, `ExemplarOfHateAbility$$GetAttacker`, passe deux
champs de bundle), plus les quinze arbres deja transcrits cote port. Sur des singletons
`exists == forall` : la correction est portee par FIDELITE, son regime divergent n'est atteint par
aucun call-site lu. L'etape A le discrimine hors-natif, ce qui est le maximum disponible.

Usage (depuis scripts/python) :
    python probe_433_r3_isadjacent_node.py                 # A..E + F
    python probe_433_r3_isadjacent_node.py --offline       # A..E seules (aucun runner)
    python probe_433_r3_isadjacent_node.py --mutate        # CONTRE-EPREUVE A/B/C/F (doit rougir)
    python probe_433_r3_isadjacent_node.py --offline --mutate-seltype   # CONTRE-EPREUVE D

ASCII only. Aucune VA en dur.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

import hexgeo                                              # noqa: E402

COLS, ROWS = 7, 7

# Couples (board, seed) de l'etape F. DEUX geometries distinctes : un resultat obtenu sur UN seul
# board n'est pas un resultat des que la mecanique touche a la geometrie.
COUPLES = [("MC1_67", "433433"), ("C2_02", "31337")]
A_UNIT = "necroWarden"                                     # cible adverse (roster de #165b)


# --------------------------------------------------------------------------- board jouet

def _tid(col: int, row: int) -> int:
    return col * ROWS + row + 1


def _toy_board(elev_by_pos=None):
    """Board PLAT (ou a elevation choisie) au format `boardGraph`, adjacence GEOMETRIQUE : c'est
    le mode `evenq` qui laisse la porte d'elevation OBSERVABLE (en `native_sym` elle est deja
    bakee dans le champ `neighbours` capte -- cf. `runner/abilities/ultramarines.py`)."""
    from engine.entities.pathfinding.board import Board
    elev_by_pos = elev_by_pos or {}
    tiles = []
    for col in range(COLS):
        for row in range(ROWS):
            nb = [_tid(c, r) for (c, r) in hexgeo.neighbors(col, row)
                  if 0 <= c < COLS and 0 <= r < ROWS]
            tiles.append({"id": _tid(col, row), "col": col, "row": row,
                          "elevation": int(elev_by_pos.get((col, row), 0)),
                          "walkable": True, "isWall": False, "neighbours": nb})
    return Board(tiles, adjacency="evenq")


def _unit(uid: int, pos, team: int = 1) -> dict:
    return {"id": uid, "team": team, "player": team, "alive": True, "hp": 1000,
            "pos": ({"col": pos[0], "row": pos[1]} if pos else None), "visualId": "u%d" % uid}


def _ctx(units, caster=None, target=None, board=None):
    from engine.dsl.base import DslContext
    return DslContext(units=list(units), caster=caster, target=target, board=board)


# --------------------------------------------------------------------------- etape A

def etape_a(fails: list) -> None:
    """(Q) : DEUX paires, une seule adjacente. `exists` -> VRAI, `forall` -> FAUX."""
    from engine.entities.selectors.accessors import Target
    from engine.entities.selectors.tiles import AllAliveUnits
    from engine.entities.triggers import IsAdjacent

    board = _toy_board()
    near = _unit(1, (3, 3))
    far = _unit(2, (0, 0))
    tgt = _unit(3, (3, 4), team=2)
    print("=== etape A -- (Q) quantificateur : le natif est un FORALL ===")

    ctx = _ctx([near, far, tgt], caster=near, target=tgt, board=board)
    got = IsAdjacent(AllAliveUnits(), Target()).evaluate(ctx)
    print("  A = {u1 @(3,3) ADJACENTE, u2 @(0,0) LOIN}, B = {u3 @(3,4)}  -> %r" % got)
    if got is not False:
        fails.append("A(Q) : deux paires dont UNE SEULE adjacente -> %r. Le natif rend FAUX des "
                     "qu'une paire ne l'est pas (`foreach ... if (!adj) return false`)" % got)

    ctx2 = _ctx([near, tgt], caster=near, target=tgt, board=board)
    got2 = IsAdjacent(AllAliveUnits(), Target()).evaluate(ctx2)
    print("  TEMOIN : A = {u1 @(3,3)} seule (toutes les paires adjacentes)      -> %r" % got2)
    if got2 is not True:
        fails.append("A(Q) temoin : toutes les paires adjacentes -> %r (doit etre VRAI : "
                     "l'enumeration s'epuise sans echec)" % got2)


# --------------------------------------------------------------------------- etape B

def etape_b(fails: list) -> None:
    """(E) : la porte d'elevation de la primitive, vue DEPUIS le noeud."""
    from engine.entities.selectors.accessors import Target
    from engine.entities.selectors.tiles import Caster
    from engine.entities.triggers import IsAdjacent

    print("=== etape B -- (E) porte d'elevation |dElev| < 2 ===")
    board = _toy_board(elev_by_pos={(3, 4): 2})          # (3,3) reste a 0 -> |dElev| = 2
    assert board.id_at(3, 4) in set(board.neighbours(board.id_at(3, 3))), \
        "MONTAGE : (3,4) n'est pas voisine de (3,3) dans cette geometrie"
    cst = _unit(1, (3, 3))
    hi = _unit(2, (3, 4), team=2)
    got_hi = IsAdjacent(Caster(), Target()).evaluate(_ctx([cst, hi], cst, hi, board))
    print("  voisine a |dElev| = 2  -> %r" % got_hi)
    if got_hi is not False:
        fails.append("B(E) : voisine a |dElev| = 2 -> %r. `AreTilesAdjacent` rend "
                     "`(dElev < 2) & b` : 2 crans FERMENT l'adjacence" % got_hi)

    flat_board = _toy_board()
    got_flat = IsAdjacent(Caster(), Target()).evaluate(_ctx([cst, hi], cst, hi, flat_board))
    print("  TEMOIN meme paire, board PLAT                      -> %r" % got_flat)
    if got_flat is not True:
        fails.append("B(E) temoin : voisine PLATE -> %r (doit etre VRAI)" % got_flat)

    board1 = _toy_board(elev_by_pos={(3, 4): 1})          # |dElev| = 1 < 2 : la porte ne mord pas
    got_1 = IsAdjacent(Caster(), Target()).evaluate(_ctx([cst, hi], cst, hi, board1))
    print("  BORNE |dElev| = 1 (< 2, la porte ne mord pas)      -> %r" % got_1)
    if got_1 is not True:
        fails.append("B(E) borne : |dElev| = 1 -> %r (le natif compare `< 2`, pas `< 1`)" % got_1)


# --------------------------------------------------------------------------- etape C

def etape_c(fails: list) -> None:
    """(I) identite + les DEUX bornes de listes vides."""
    from engine.entities.selectors.accessors import Target
    from engine.entities.selectors.tiles import Caster
    from engine.entities.triggers import IsAdjacent

    print("=== etape C -- (I) identite, et le vide ===")
    board = _toy_board()
    cst = _unit(1, (3, 3))
    got_self = IsAdjacent(Caster(), Caster()).evaluate(_ctx([cst], cst, None, board))
    print("  meme entite des deux cotes (t1 == t2)              -> %r" % got_self)
    if got_self is not True:
        fails.append("C(I) : `IsAdjacent(x, x)` -> %r. `AreTilesAdjacent` court-circuite "
                     "`IsNeighbour` sur `tile1 == tile2` et `|dElev| = 0 < 2` ne peut pas "
                     "le contredire" % got_self)

    got_empty = IsAdjacent(Caster(), Target()).evaluate(_ctx([cst], cst, None, board))
    print("  B VIDE (cible absente)                             -> %r" % got_empty)
    if got_empty is not False:
        fails.append("C(vide) : B vide -> %r. Le natif teste `Any()` AVANT la boucle et rend "
                     "FAUX -- un `All` nu rendrait VRAI sur le vide" % got_empty)

    orphan = _unit(4, None, team=2)                      # entite SANS position -> GetTiles = []
    got_nopos = IsAdjacent(Caster(), Target()).evaluate(_ctx([cst, orphan], cst, orphan, board))
    print("  cible SANS position (GetTiles vide)                -> %r" % got_nopos)
    if got_nopos is not False:
        fails.append("C(sans pos) : cible sans tuile -> %r (la double boucle native ne tourne "
                     "pas -> paire NON adjacente -> le forall rend FAUX)" % got_nopos)


# --------------------------------------------------------------------------- etape D

def etape_d(fails: list) -> None:
    """Le 3e argument de la factory est INERTE pour le predicat -- c'est la faute que la fiche
    #433-r1 anticipait ("ne le cable pas dans la comparaison")."""
    from engine.entities.selectors.accessors import Target
    from engine.entities.selectors.tiles import Caster
    from engine.entities.triggers import IsAdjacent

    print("=== etape D -- le 3e argument (`UnitSelectionType`) ne touche PAS le predicat ===")
    board = _toy_board(elev_by_pos={(3, 4): 2})
    cst, hi = _unit(1, (3, 3)), _unit(2, (3, 4), team=2)
    near = _unit(3, (3, 2), team=2)
    for tgt in (hi, near):
        vals = {}
        for sel in (None, 0, 2, 3):
            vals[sel] = IsAdjacent(Caster(), Target(), sel).evaluate(_ctx([cst, tgt], cst, tgt,
                                                                          board))
        print("  cible %s : verdicts par selectionType %r" % (_pospair(tgt), vals))
        # INERTNESS seule : le verdict ne doit pas VARIER avec le 3e argument. La valeur, elle,
        # est mesuree par les etapes B/C -- ici on garde uniquement contre le cablage fautif.
        if len(set(vals.values())) != 1:
            fails.append("D : le verdict DEPEND du 3e argument (%r) -- il part au SELECTEUR "
                         "(slot 3), jamais dans la comparaison par paire" % vals)


def _pospair(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row"))


# --------------------------------------------------------------------------- etape E

def etape_e(fails: list) -> None:
    """Degradation SANS board : adjacence hex pure. On NOMME les sites qui y retombent."""
    from engine.entities.selectors.accessors import Target
    from engine.entities.selectors.tiles import Caster
    from engine.entities.triggers import IsAdjacent

    print("=== etape E -- degradation SANS board (adjacence hex pure) ===")
    cst, hi = _unit(1, (3, 3)), _unit(2, (3, 4), team=2)
    got = IsAdjacent(Caster(), Target()).evaluate(_ctx([cst, hi], cst, hi, None))
    print("  ctx.board = None, voisines hex                     -> %r" % got)
    if got is not True:
        fails.append("E : sans board -> %r. La convention du depot est l'adjacence hex pure "
                     "(sure sur un board PLAT, ou |dElev| = 0 < 2 partout)" % got)
    got_far = IsAdjacent(Caster(), Target()).evaluate(
        _ctx([cst, _unit(2, (0, 0), team=2)], cst, _unit(2, (0, 0), team=2), None))
    print("  ctx.board = None, NON voisines                     -> %r" % got_far)
    if got_far is not False:
        fails.append("E : sans board, paire non voisine -> %r" % got_far)
    print("  sites qui retombent sur cette branche (ctx.board absent) :")
    print("    - `entities/abilities/triggered_ability.py` : `DslContext()` nu (arbres de DEGAT,")
    print("      aucun `IsAdjacent` -- branche INERTE)")
    print("    - `entities/abilities/active_ability.py::_hits_ctx` : contexte de COUPS (idem)")
    print("    - tout appelant de test qui construit un `DslContext` sans `board=`")
    print("  les SIX consommateurs portes du noeud passent tous par un contexte AVEC board :")
    print("    runner/abilities/{orks(Waaagh, RammingSpeed), sisterhood(SkyStrike),")
    print("    genestealer(VigilanceEternal)}, runner/operations/triggers/loki/{betrayer,")
    print("    harlequins_panoply} -> `entities_from_state(..., board=state.board)`,")
    print("    et cote DECISION `playbook/prediction/*` -> `board=scene.board`.")


# --------------------------------------------------------------------------- etape F (LIVE)

def _pick_pair(board, want_gap: bool, occupied):
    """Une paire (a, b) de tuiles MARCHABLES et LIBRES, voisines HEX, avec |dElev| >= 2
    (`want_gap`) ou |dElev| < 2. Rend `(a, b, dElev)` ou None. On BALAYE le plateau : jamais
    << bloque par la geometrie de spawn >>."""
    best = None
    for tid, t in sorted(board.by_id.items()):
        pa = (t["col"], t["row"])
        if not board.walkable(tid) or pa in occupied:
            continue
        ea = int(board.elevation(tid))
        for pb in hexgeo.neighbors(pa[0], pa[1]):
            pb = (pb[0], pb[1])
            nid = board.id_at(pb[0], pb[1])
            if nid is None or not board.walkable(nid) or pb in occupied:
                continue
            d = abs(ea - int(board.elevation(nid)))
            if (d >= 2) != bool(want_gap):
                continue
            # la cible doit garder au moins une tuile ring-1 LIBRE : c'est le pool
            # `CanAddUnit(AdjacentTiles(target))` de la charge, sinon rien n'est observable.
            free = [n for n in board.neighbours_native(nid)
                    if board.walkable(n) and board.coord(n) not in occupied
                    and board.coord(n) != pa]
            if not free:
                continue
            cand = (pa, pb, d)
            if best is None:
                best = cand
    return best


def _walk_path(board, start, goal, blocked):
    """Chemin de MARCHE start -> goal (BFS), avec la porte d'elevation du pathfinder natif
    (`IdunBattle.Entities.Pathfinding.WalkPathfinder$$IsValidPathNode` : voisin STOCKE et
    `|dElev| < 2`). Rend la liste des `(col,row)`, ou None.

    Pourquoi pas le pas glouton << la tuile la plus proche EN DISTANCE HEX >> : sur un board a
    plateaux il tombe dans un minimum LOCAL au bord de la falaise et n'atteint jamais la tuile
    d'en bas (mesure : `C2_02`, la cible s'immobilise a (3,5) au lieu de (5,4))."""
    from collections import deque
    sid_, gid = board.id_at(start[0], start[1]), board.id_at(goal[0], goal[1])
    if sid_ is None or gid is None:
        return None
    prev = {sid_: None}
    q = deque([sid_])
    while q:
        cur = q.popleft()
        if cur == gid:
            break
        e = int(board.elevation(cur))
        for n in board.neighbours(cur):
            if n in prev or not board.walkable(n):
                continue
            if abs(e - int(board.elevation(n))) >= 2:
                continue
            if board.coord(n) in blocked and n != gid:
                continue
            prev[n] = cur
            q.append(n)
    if gid not in prev:
        return None
    out, cur = [], gid
    while cur is not None:
        out.append(board.coord(cur))
        cur = prev[cur]
    return list(reversed(out))


def _drive(H, rid, board, wanted, max_turns: int = 20) -> bool:
    """Amene chaque `uid -> (col,row)` a destination en suivant le CHEMIN DE MARCHE (pas le
    gradient hex), un saut par tour, jusqu'a la tuile la plus avancee du chemin qui soit dans
    `aiMovableTiles`."""
    for _ in range(max_turns):
        if all(H.live_pos(rid, u) == tuple(p) for u, p in wanted.items()):
            return True
        mov = H.rpc("aiMovableTiles", {"runnerId": rid}, 60) or {}
        for mu in (mov.get("units") or []):
            uid = int(mu.get("unitId") or -1)
            if uid not in wanted:
                continue
            cur, dest = H.live_pos(rid, uid), tuple(wanted[uid])
            if cur == dest:
                continue
            blocked = {H.live_pos(rid, o) for o in wanted if o != uid}
            path = _walk_path(board, cur, dest, blocked)
            if not path:
                continue
            reach = {(t.get("col"), t.get("row")) for t in (mu.get("tiles") or [])}
            step = next((p for p in reversed(path[1:]) if p in reach), None)
            if step is not None and step != cur:
                H.move(rid, uid, step[0], step[1])
        H.endturn(rid)
    return all(H.live_pos(rid, u) == tuple(p) for u, p in wanted.items())


def etape_f(board_id: str, seed_value: str, fails: list, want_gap: bool = True) -> bool:
    """LIVE. `want_gap=True` = le CRAN (voisines a |dElev| >= 2, le natif doit CHARGER) ;
    `want_gap=False` = le TEMOIN (voisines PLATES, le natif ne doit PAS bouger). Le temoin n'est
    pas decoratif : sans lui, un port qui rendrait TOUJOURS `False` passerait le cran.
    Rend True si le regime a ete CONFRONTE."""
    import probe_165b_sky_strike_border as H              # harnais #165b (jamais recopie)
    from engine.entities.selectors.accessors import Target
    from engine.entities.selectors.tiles import Caster
    from engine.entities.triggers import IsAdjacent
    from engine.runner.abilities.behaviours.context import entities_from_state
    from engine.runner.abilities.sisterhood import _sky_strike_dest_tile

    kind = "CRAN (|dElev| >= 2)" if want_gap else "TEMOIN (voisines PLATES)"
    print("=== etape F (LIVE) -- %s -- board=%s seed=%s ===" % (kind, board_id, seed_value))
    bc = H.inject_bc(H.SKY_VIS)
    try:
        rid, _sf = H.build(seed_value, board_id,
                           ["--seed-bc", str(bc), "--p-units", H.SKY_VIS,
                            "--a-units", A_UNIT, "--no-ai"])
    finally:
        bc.unlink(missing_ok=True)
    confronted = False
    try:
        st, board, dv = H.load(rid)
        caster = H.uid_by_vis(dv, H.SKY_VIS)
        target = H.uid_by_vis(dv, A_UNIT)
        if caster is None or target is None:
            raise SystemExit("MONTAGE : roster absent (caster=%r target=%r)" % (caster, target))
        occupied = {H.live_pos(rid, u) for u in
                    (int(x["id"]) for x in (dv.get("units") or []) if x.get("pos"))}
        occupied -= {H.live_pos(rid, caster), H.live_pos(rid, target)}
        pair = _pick_pair(board, want_gap=want_gap, occupied=occupied)
        if pair is None:
            print("[MONTAGE] aucune paire voisine LIBRE %s sur %s -- regime inexistant sur ce "
                  "board" % ("a |dElev| >= 2" if want_gap else "PLATE", board_id))
            return False
        cpos, tpos, d = pair
        print("[MONTAGE] caster -> %r (elev %d), cible -> %r (elev %d), |dElev| = %d, "
              "dist hex = %d" % (cpos, board.elevation(board.id_at(*cpos)), tpos,
                                 board.elevation(board.id_at(*tpos)), d,
                                 hexgeo.distance(cpos, tpos)))
        ok = _drive(H, rid, board, {caster: cpos, target: tpos})
        print("[MONTAGE] drive ok=%s  caster=%s cible=%s"
              % (ok, H.live_pos(rid, caster), H.live_pos(rid, target)))
        if not ok:
            print("[NON CONFRONTE] le drive n'a pas place les deux unites -- ecrit tel quel.")
            return False

        st2, board2, _dv2 = H.load(rid)
        ctx = entities_from_state(st2, caster, target)
        node = IsAdjacent(Caster(), Target())
        adj_port = bool(node.evaluate(ctx))
        dest = _sky_strike_dest_tile(st2, caster, target)
        pred = cpos if adj_port else (dest if dest is not None else cpos)
        print("[PORT] IsAdjacent(caster, cible) = %r ; dest de charge = %r ; tuile finale "
              "PREDITE = %r" % (adj_port, dest, pred))

        act0 = H.cast_sky(rid, caster, target)
        if act0.get("error") or not act0.get("mutated"):
            print("[MONTAGE] cast 1025 KO : err=%r mutated=%r"
                  % (act0.get("error"), act0.get("mutated")))
            return False
        after = H.live_pos(rid, caster)
        moved = (after != cpos)
        print("[NATIF] tuile finale = %r  (deplacement = %s)" % (after, moved))
        confronted = True
        if want_gap and not moved:
            fails.append("F(cran) : le NATIF n'a PAS charge alors que caster %r et cible %r sont "
                         "voisines a |dElev| = %d -- si le natif les voyait adjacentes, la porte "
                         "d'elevation ne serait pas dans `AreTilesAdjacent`" % (cpos, tpos, d))
        if not want_gap and moved:
            fails.append("F(temoin) : le NATIF a CHARGE alors que caster %r et cible %r sont "
                         "voisines PLATES (|dElev| = %d) -- il devrait les voir adjacentes et "
                         "gater le move" % (cpos, tpos, d))
        if pred != after:
            fails.append("F(%s) : DESACCORD port/natif sur la tuile finale -- port=%r natif=%r "
                         "(IsAdjacent port = %r)"
                         % ("cran" if want_gap else "temoin", pred, after, adj_port))
        else:
            print("[VERDICT] ACCORD port/natif sur la tuile finale %r" % (after,))
        return confronted
    finally:
        try:
            H.rpc("disposeRunner", {"runnerId": rid}, 20)
        except Exception:
            pass


# --------------------------------------------------------------------------- mutation

def _mutate() -> None:
    """CONTRE-EPREUVE : on REMET le noeud dans son etat d'AVANT #433-r3 -- `any` + `hexgeo` pur,
    ni identite ni elevation. Les etapes A, B, C et F DOIVENT alors rougir. Le critere est le
    DEPLACEMENT par rapport au port NON MUTE."""
    from engine.dsl.base import _pos, _units_of
    from engine.entities import triggers as T

    def old(self, ctx):
        pa = [_pos(u) for u in _units_of(self.a, ctx)]
        pb = [_pos(u) for u in _units_of(self.b, ctx)]
        return any(x is not None and y is not None and hexgeo.distance(x, y) == 1
                   for x in pa for y in pb)

    T.IsAdjacent.should_trigger = old
    print("[MUTATE] noeud `IsAdjacent` REMIS a `any(hexgeo.distance == 1)` -- les etapes A, B, C "
          "et F DOIVENT rougir\n")


def _mutate_seltype() -> None:
    """CONTRE-EPREUVE de l'etape D, et de rien d'autre : on CABLE le 3e argument dans la
    comparaison par paire (`dist <= selectionType`) -- exactement la faute que la fiche #433-r1
    anticipait. Seule l'etape D doit rougir."""
    from engine.dsl.base import _pos, _units_of
    from engine.entities import triggers as T

    def wired(self, ctx):
        pa = [_pos(u) for u in _units_of(self.a, ctx)]
        pb = [_pos(u) for u in _units_of(self.b, ctx)]
        if not pa or not pb:
            return False
        r = 1 if self.selection_type is None else int(self.selection_type)
        return all(x is not None and y is not None and hexgeo.distance(x, y) <= r
                   for x in pa for y in pb)

    T.IsAdjacent.should_trigger = wired
    print("[MUTATE-SELTYPE] 3e argument CABLE dans la comparaison -- seule l'etape D doit "
          "rougir\n")


# --------------------------------------------------------------------------- main

def main() -> int:
    mutated = "--mutate" in sys.argv or "--mutate-seltype" in sys.argv
    if "--mutate-seltype" in sys.argv:
        _mutate_seltype()
    elif "--mutate" in sys.argv:
        _mutate()
    fails: list = []
    for step in (etape_a, etape_b, etape_c, etape_d, etape_e):
        step(fails)
        print()
    if "--offline" not in sys.argv:
        confronted = False
        # (board, seed, want_gap) : les DEUX couples pour le cran (geometries distinctes -- un
        # resultat sur UN seul board n'en est pas un des que la mecanique est geometrique), et le
        # TEMOIN plat sur le premier.
        runs = [(b, s, True) for b, s in COUPLES] + [(COUPLES[0][0], COUPLES[0][1], False)]
        for board_id, seed_value, want_gap in runs:
            try:
                confronted = etape_f(board_id, seed_value, fails, want_gap) or confronted
            except SystemExit as e:
                if not mutated:
                    raise
                fails.append("MUTATE : %s" % e)
            if mutated and confronted:
                break
        if not confronted:
            print("[ETAPE F] NON CONFRONTE sur les %d montages essayes -- ecrit tel quel, jamais "
                  "rabattu en << non pertinent >>." % len(runs))
        print()
    if fails:
        print("=== %d ECHEC(S) ===" % len(fails))
        for f in fails:
            print("  - " + f)
        return 0 if mutated else 1
    if mutated:
        print("=== CONTRE-EPREUVE VERTE = LE PROBE NE MESURE RIEN ===")
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    os.chdir(str(PYDIR))
    raise SystemExit(main())
