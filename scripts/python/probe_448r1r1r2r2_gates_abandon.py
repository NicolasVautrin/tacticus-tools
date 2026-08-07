"""#448-r1-r1-r2-r2 / #448-r1-r2 / #462-r4b-r1-r1-r1-r1-c-r3-r1-r4-r3 -- LES DEUX GATES D'ABANDON
de `IdunBattle.Operations.MoveUnitOperation$$Execute`, et la trace du crush.

LE CONSTAT COMMUN. `Execute` est une operation A ETAPES, et le port en sautait deux qui peuvent
REFUSER le mouvement. Les etages de sa branche REELLE, lus VERBATIM (build `rnca9r7q6c`) :

    G1..G7  IsAllowedToMove / UnitIsOnTiles / TilesAreWalkable / TilesMatchUnitFeetCount /
            IsDisallowedEmptyPosition / IsPositionReservedForOtherUnit /
            IsPositionReservedForDrafting          <- AUCUN ne teste l'OCCUPATION
    E0      isLikeFlying = IsLikeFlying(unit, options)
    E1      currentPosition = GetUnitPosition(unit)
            movementStartPosition = currentPosition, ou GetPreviousPositionThisTurn si vide
    E2      endTile = position.MainTile ; feet = GetUnitFeet(unit) ; startTile = start[0]
    E3      comp.<+0xa8> = Nullable(UnitPositionId(position))        (a) destination DEMANDEE
    E4      SetReservation(unit, position)
    E5      if (!options.skipPreMoveTriggers) {
                On(0x1f = PreUnitMove)                               (b)
                if (!TilesAreEmpty(unit, position)) { RemoveReservation ; return }   <<< GATE 1
            }
    E6      ovr = comp.<+0xa8> ; comp.<+0xa8> = null                 (c)
            if (!ovr.HasValue || IsDead(unit)) { RemoveReservation ; return }
    E7      if (ToUnitPosition(ovr) != position) { RemoveReservation ; options.<+0x12> = 1 ;
                                                   return Execute(<nouvelle position>) }
    E8      if (position.Count == 0) { ... allowNullTargetPosition ... }
    E9      CalculatePaths(...) -> path, connectedPath
    E10     if (path == null || path.Count == 0) { log ; RemoveReservation ; return }   <<< GATE 2
    E11     steppableUnits = BattleQuery.<0x8f>(position)
    E12     processor.<0x7e>(unit, position, false)     <- L'ECRITURE DE POSITION EST *ICI*
    E13     log du mouvement
    E14     AddMoveEvent x N (un par pas de `path`)
    E15     KillSteppableUnits(this, unit, steppableUnits)
    E16..26 UpdateCharging / SetMovedFlag / ArrivedAtFinalTile / RemoveReservation /
            movementSteps / RecordTilesMoved / RefreshEffects#1 / EvaluateAfterMoveTriggers /
            On(0x1c) / RefreshEffects#2

⇒ les deux gates sont AVANT E12. Le port ecrivait la position sans les jouer : degradation
PERMISSIVE des deux cotes (le port bouge TOUJOURS), donc ni erreur ni crash -- invisible.

CE QUE `AddMoveEvent` N'EST PAS. Le decompile de
`IdunBattle.Operations.MoveUnitOperation$$AddMoveEvent` ne touche AUCUN composant ECS : il
construit un `Dictionary<int,int>` (cles `0x79` pathTile, `0x80` isLastTile, `0x7a..0x7f` les pieds)
et le pousse dans `AOperation.get_Events()` par `AddStep(3, unit.Id, dict)`. Ses seules autres
operations sont des LECTURES (`HasTrait(unit, 0x13 = Burrow)`, `IsTeleportationTile`). C'est un pur
canal de VUE -- non porte, comme le step `0x25` d'`OverrideMovementTargetOperation` et le
`Inform{0x79}` du Miss. La moitie « emettre un AddMoveEvent par pas » du residu est donc SANS effet
d'etat ; ce qui mordait est la GARDE `path` vide, et elle exige de materialiser `path`.

VOLET A (offline) -- le port, sur board REEL, avec les gates ON puis OFF (le port d'AVANT).
VOLET B (live)    -- le NATIF, meme geometrie, avec un CONTROLE POSITIF a chaque bras : sans lui,
                     « le natif n'a pas bouge » se lirait comme un verdict alors que ce pourrait
                     etre un montage inerte (RPC refuse, unite deja jouee, portee...).

    python probe_448r1r1r2r2_gates_abandon.py --offline
    python probe_448r1r1r2r2_gates_abandon.py --live --board C4_09
"""
from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys

PYDIR = pathlib.Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
LOGSDIR = ROOT / "logs"
sys.path.insert(0, str(PYDIR))

import board as BOARDMOD                                                       # noqa: E402
from engine.entities.pathfinding.board import Board as EngineBoard             # noqa: E402
from engine.entities.pathfinding.walk_pathfinder import (                      # noqa: E402
    get_path_node_counts_by_pos, get_path_by_pos)
from engine.runner.state import State                                          # noqa: E402
from engine.runner.events import EventBus                                      # noqa: E402
from engine.runner.components import (PositionComponent, UnitComponent,        # noqa: E402
                                      OwnerComponent, HealthComponent,
                                      StatsComponent, UnitFlagsComponent)
from engine.runner.operations.movement import MoveUnitOperation                # noqa: E402
import engine.runner.operations.movement as MV                                 # noqa: E402
from engine.entities.traits.unit_trait import UnitTrait, trait_name            # noqa: E402

BOARDS = ROOT / "data" / "boards"


# --------------------------------------------------------------------------- helpers de board
def _engine_board_from_dump(dump) -> EngineBoard:
    """`EngineBoard` depuis un dump `data/boards/` -- meme construction que
    `probe_381r4_imperative_collapses._engine_board`. Le champ `neighbours` est volontairement
    ABSENT : `Board.neighbours_native` retombe alors sur l'adjacence geometrique `evenq`, ce qui
    est le meilleur proxy offline du `ConnectivityComponent` (cf. `board.base_add_neighbours`)."""
    cols = dump["board"].get("Tiles") or []
    height = dump["board"].get("Height") or max(
        (len((c or {}).get("Tile") or []) for c in cols), default=0)
    tiles = []
    for c, col in enumerate(cols):
        for r, t in enumerate((col or {}).get("Tile") or []):
            if t is None:
                continue
            tiles.append({"id": c * height + r, "col": c, "row": r,
                          "elevation": BOARDMOD._effective_elevation(t.get("TileId"),
                                                                     t.get("Elevation", 0)),
                          "walkable": not bool(t.get("ForceUnplayable", False)),
                          "tileDefId": t.get("TileId")})
    return EngineBoard(tiles, adjacency="evenq")


def _load_board(board_id: str) -> EngineBoard:
    for kind in ("pvp", "global", "syncPvp"):
        p = BOARDS / kind / ("%s.json" % board_id)
        if p.exists():
            return _engine_board_from_dump(json.loads(p.read_text(encoding="utf-8")))
    raise SystemExit("board introuvable dans data/boards/ : %s" % board_id)


def unreachable_pair(board: EngineBoard) -> "tuple | None":
    """Une paire `(src, dst)` toutes deux WALKABLE dont `dst` est INJOIGNABLE a la marche depuis
    `src` -- la geometrie SEULE (relief / murs), aucune unite. `src` est pris dans la PLUS GRANDE
    composante pour qu'un spawn puisse l'atteindre."""
    neigh, walk, elev = board.walk_maps_by_pos()
    walkables = [p for p, w in walk.items() if w]
    seen, comps = set(), []
    for start in walkables:
        if start in seen:
            continue
        counts = get_path_node_counts_by_pos(start, neigh_by_pos=neigh, walkable_by_pos=walk,
                                             elev_by_pos=elev)
        comp = {q for q in counts if walk.get(q)}
        seen |= comp
        comps.append(comp)
    if len(comps) < 2:
        return None
    comps.sort(key=len, reverse=True)
    big, small = comps[0], comps[-1]
    return sorted(big)[len(big) // 2], sorted(small)[0]


# --------------------------------------------------------------------------- state synthetique
def _state(board, units) -> State:
    """`units` = [(id, (col,row) | None, team, [traits])]."""
    st = State()
    st.board = board
    for uid, pos, team, traits in units:
        e = st.add_entity(uid)
        e.add_component(UnitComponent(visual_id="u%d" % uid, alive=True))
        e.add_component(OwnerComponent(team=team, player=2 + team))
        e.add_component(HealthComponent(hp=1000, hp_max=1000))
        from engine.entities.unit_context import UnitContext
        ctx = UnitContext.__new__(UnitContext)                   # ctx NU : seuls `traits` comptent
        # `ctx.traits` porte des NOMS (le champ gameconfig), jamais des ordinaux : `has_trait` fait
        # `trait_name(trait) in trait_names`. Passer l'enum brut donnerait un substrat SILENCIEUSEMENT
        # inerte -- et le bras `Steppable` du gate serait vert pour la mauvaise raison.
        ctx.traits = [trait_name(t) for t in (traits or [])]
        e.add_component(StatsComponent(ctx))
        if pos is not None:
            e.add_component(PositionComponent(pos[0], pos[1]))
        e.add_component(UnitFlagsComponent())
    return st


def _pos(st, uid):
    e = st.get_entity(uid)
    pc = e.get_component(PositionComponent) if e is not None else None
    return None if pc is None else (pc.col, pc.row)


# --------------------------------------------------------------------------- VOLET A (offline)
def volet_a(board_id: str) -> int:
    bad = 0
    board = _load_board(board_id)
    print("[A] board %s -- %d tuiles" % (board_id, len(board.by_id)))

    # ---- A1 : GATE 2 (`path` vide). Temoin NON NUL : les deux modeles divergent.
    pair = unreachable_pair(board)
    if pair is None:
        print("[A1] SANS OBJET : %s n'a qu'UNE composante de marche" % board_id)
        bad += 1
    else:
        src, dst = pair
        neigh, walk, elev = board.walk_maps_by_pos()
        path = get_path_by_pos(src, dst, neigh_by_pos=neigh, walkable_by_pos=walk, elev_by_pos=elev)
        print("[A1] src=%s dst=%s  walkable(dst)=%s  path=%s"
              % (src, dst, walk.get(dst), "None (INJOIGNABLE)" if path is None else len(path)))
        bad += 0 if (walk.get(dst) and path is None) else 1

        st = _state(board, [(1, src, 1, [])])
        op = MoveUnitOperation(1, dst)
        op.execute(st, EventBus())
        apres_on = _pos(st, 1)
        st2 = _state(board, [(1, src, 1, [])])
        op2 = MoveUnitOperation(1, dst, enforce_native_gates=False)      # le port d'AVANT
        op2.execute(st2, EventBus())
        apres_off = _pos(st2, 1)
        ok = (apres_on == src and apres_off == dst and op.last_abandoned == "path-empty")
        bad += 0 if ok else 1
        print("[A1] gates ON  -> pos %s (abandon=%r)   gates OFF -> pos %s   => %s"
              % (apres_on, op.last_abandoned, apres_off, "OK" if ok else "ROUGE"))

    # ---- A2 : GATE 1 (`TilesAreEmpty`). Deux unites, l'une bouge SUR l'autre.
    neigh, walk, elev = board.walk_maps_by_pos()
    a = next(p for p, w in sorted(walk.items()) if w and neigh.get(p))
    b = next(q for q in neigh[a] if walk.get(q))
    st = _state(board, [(1, a, 1, []), (2, b, 2, [])])
    op = MoveUnitOperation(1, b)
    op.execute(st, EventBus())
    apres_on = _pos(st, 1)
    st2 = _state(board, [(1, a, 1, []), (2, b, 2, [])])
    MoveUnitOperation(1, b, enforce_native_gates=False).execute(st2, EventBus())
    apres_off = _pos(st2, 1)
    ok = (apres_on == a and apres_off == b and op.last_abandoned == "tiles-not-empty")
    bad += 0 if ok else 1
    print("[A2] a=%s occupee par u2 ; gates ON -> pos %s (abandon=%r) ; OFF -> %s  => %s"
          % (b, apres_on, op.last_abandoned, apres_off, "OK" if ok else "ROUGE"))

    # ---- A3 : les TROIS exemptions natives du gate 1.
    #   (i) occupant STEPPABLE -> le mouvement PASSE (et le crush a lieu) ;
    #   (ii) occupant MORT -> passe (`IsFilled` suit le retrait du plateau) ;
    #   (iii) tuile vide -> passe.
    st = _state(board, [(1, a, 1, []), (2, b, 2, [UnitTrait.Steppable])])
    op = MoveUnitOperation(1, b)
    op.execute(st, EventBus())
    ok_i = _pos(st, 1) == b
    st = _state(board, [(1, a, 1, []), (2, b, 2, [])])
    st.get_entity(2).get_component(UnitComponent).alive = False
    MoveUnitOperation(1, b).execute(st, EventBus())
    ok_ii = _pos(st, 1) == b
    st = _state(board, [(1, a, 1, [])])
    MoveUnitOperation(1, b).execute(st, EventBus())
    ok_iii = _pos(st, 1) == b
    bad += 0 if (ok_i and ok_ii and ok_iii) else 1
    print("[A3] exemptions : Steppable=%s  mort=%s  vide=%s  => %s"
          % (ok_i, ok_ii, ok_iii, "OK" if (ok_i and ok_ii and ok_iii) else "ROUGE"))

    # ---- A4 : la TRACE du crush est publiee (#462-...-r4-r3). Ecart d'OBSERVABILITE, pas d'etat.
    st = _state(board, [(1, a, 1, []), (2, b, 2, [UnitTrait.Steppable])])
    op = MoveUnitOperation(1, b)
    op.execute(st, EventBus())
    tr = op.last_crushed
    ok = (len(tr) == 1 and tr[0]["unit"] == 2 and tr[0]["killer"] == 1
          and isinstance(tr[0].get("vectors"), list))
    bad += 0 if ok else 1
    print("[A4] last_crushed = %s  => %s"
          % (json.dumps([{k: v for k, v in t.items() if k != "vectors"} for t in tr]),
             "OK" if ok else "ROUGE"))
    ok = _pos(st, 1) == b and not st.get_entity(2).get_component(UnitComponent).alive
    bad += 0 if ok else 1
    print("[A4] l'ETAT est inchange (mover arrive, steppable mort) => %s"
          % ("OK" if ok else "ROUGE"))

    # ---- A5 : `last_path` materialise, et sa longueur == le compte du meme moteur.
    dst2 = next(q for q in neigh[a] if walk.get(q))
    st = _state(board, [(1, a, 1, [])])
    op = MoveUnitOperation(1, dst2)
    op.execute(st, EventBus())
    counts = get_path_node_counts_by_pos(a, neigh_by_pos=neigh, walkable_by_pos=walk,
                                         elev_by_pos=elev)
    ok = (op.last_path is not None and len(op.last_path) == counts.get(dst2)
          and op.last_path[0] == a and op.last_path[-1] == dst2)
    bad += 0 if ok else 1
    print("[A5] last_path=%s len=%s counts[dst]=%s => %s"
          % (op.last_path, None if op.last_path is None else len(op.last_path),
             counts.get(dst2), "OK" if ok else "ROUGE"))

    # ---- A6 : unite HORS PLATEAU -> branche degeneree `[to, to]`, JAMAIS d'abandon.
    st = _state(board, [(1, None, 1, [])])
    op = MoveUnitOperation(1, dst2)
    op.execute(st, EventBus())
    ok = (_pos(st, 1) == dst2 and op.last_path == [dst2, dst2] and op.last_abandoned == "")
    bad += 0 if ok else 1
    print("[A6] hors plateau -> pos %s path %s abandon %r => %s"
          % (_pos(st, 1), op.last_path, op.last_abandoned, "OK" if ok else "ROUGE"))
    return bad


# --------------------------------------------------------------------------- VOLET B (live)
def _rpc_factory():
    from rl_collect_batch import _resolve_session, _rpc

    def rpc(sid, m, args, t=120):
        r = _rpc(sid, m, [args], timeout=t)
        return (r.get("result") if isinstance(r, dict) and "result" in r else r) or {}
    return _resolve_session(), rpc


def _build(board: str, seed: int, tag: str) -> int:
    LOGSDIR.mkdir(parents=True, exist_ok=True)
    state_file = LOGSDIR / ("p448r1r1r2r2_state_%s.json" % tag)
    state_file.unlink(missing_ok=True)
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--rank", "17",
           "--board", board, "--no-ai", "--state-file", str(state_file)]
    p = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state_file.exists():
        sys.stdout.write((p.stdout or "")[-2000:])
        sys.stdout.write((p.stderr or "")[-2000:])
        raise SystemExit("build KO (%s)" % tag)
    return int(json.loads(state_file.read_text(encoding="utf-8"))["runnerId"]), state_file


def _board_from_graph(rpc, sid, rid) -> EngineBoard:
    bg = rpc(sid, "boardGraph", {"runnerId": rid}, 60)
    tiles = bg.get("tiles") or bg.get("Tiles") or []
    return EngineBoard(list(tiles), adjacency="evenq")


def _pos_by_squad(rpc, sid, rid) -> dict:
    """Positions indexees par `squadId` -- la MEME cle que `decisionView.toActivate`.

    ⚠ `observeBattle.units[]` porte `col`/`row` A PLAT (pas un sous-objet `pos`), et son `id` est
    l'`entityId`, PAS le `squadId` : melanger les deux lirait la position d'une AUTRE unite."""
    ob = rpc(sid, "observeBattle", {"runnerId": rid}, 60)
    out = {}
    for u in (ob.get("units") or []):
        sq, c, r = u.get("squadId"), u.get("col"), u.get("row")
        if sq is None or c is None or r is None:
            continue
        out[int(sq)] = (int(c), int(r))
    return out


def volet_b(board_id: str, seed: int) -> int:
    bad = 0
    sid, rpc = _rpc_factory()
    rid, state_file = _build(board_id, seed, "b")
    print("[B] runner %d monte sur %s (seed %d)" % (rid, board_id, seed))
    try:
        board = _board_from_graph(rpc, sid, rid)
        neigh, walk, elev = board.walk_maps_by_pos()
        # ⚠ `decisionView` ne porte PAS `col`/`row` (mesure #448-r1-r1-r2) : les positions viennent
        # d'`observeBattle`, indexees par `squadId` -- la MEME cle que `toActivate`.
        dv = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1}, 90)
        to_act = [int(x) for x in (dv.get("toActivate") or [])]
        pos0 = _pos_by_squad(rpc, sid, rid)
        mine = [x for x in to_act if pos0.get(x) is not None]
        if not mine:
            print("[B] AUCUNE unite jouable (toActivate=%r, positions=%d) -- montage inerte"
                  % (to_act[:6], sum(1 for v in pos0.values() if v is not None)))
            return bad + 1
        uid = mine[0]
        p0 = pos0[uid]
        counts = get_path_node_counts_by_pos(p0, neigh_by_pos=neigh, walkable_by_pos=walk,
                                             elev_by_pos=elev)
        joignables = set(counts)
        isolees = sorted(p for p, w in walk.items() if w and p not in joignables)
        nwalk = sum(1 for w in walk.values() if w)
        print("[B] unite %d en %s ; tuiles=%d walkable=%d joignables=%d ; walkable ISOLEES=%d %s"
              % (uid, p0, len(board.by_id), nwalk, len(joignables), len(isolees), isolees[:6]))
        # DIAGNOSTIC de l'ecart offline/live : le boardGraph LIVE porte le champ `neighbours` du
        # capteur (`connectivity` INTERSECTE `|dElev| < 2`), la ou le dump `data/boards/` ne le porte
        # pas et retombe sur la geometrie `evenq`. Les composantes ne coincident donc pas -- c'est le
        # graphe LIVE qui fait foi pour un verdict live.
        print("[B] boardGraph : champ `neighbours` %s"
              % ("PRESENT" if any((t or {}).get("neighbours") is not None
                                  for t in board.by_id.values()) else "ABSENT (repli geometrique)"))

        # --- CONTROLE POSITIF : une destination JOIGNABLE et LIBRE, a distance 1.
        occ = {p for p in _pos_by_squad(rpc, sid, rid).values() if p is not None}
        libre = next((q for q in neigh.get(p0) or [] if walk.get(q) and q not in occ), None)
        if libre is None:
            print("[B] pas de voisine libre -- controle positif IMPOSSIBLE, aucun verdict")
            return bad + 1
        r = rpc(sid, "applyAction", {"runnerId": rid,
                                     "action": {"kind": "move", "unitId": uid,
                                                "to": {"col": libre[0], "row": libre[1]}}}, 60)
        p1 = _pos_by_squad(rpc, sid, rid).get(uid)
        ok_pos = (p1 == libre)
        bad += 0 if ok_pos else 1
        print("[B+] CONTROLE POSITIF  move %s -> %s : natif pos %s (mutated=%s) => %s"
              % (p0, libre, p1, r.get("mutated"), "MORD" if ok_pos else "MONTAGE INERTE"))
        if not ok_pos:
            print("[B] le controle positif ne mord pas : les bras negatifs ne prouveraient RIEN")
            return bad

        # --- BRAS 1bis : l'isolement par les UNITES ENNEMIES. Sur board reel, l'isolement
        # GEOMETRIQUE est rare en live (les tuiles d'ilot du dump BC ressortent non-walkable), mais
        # `WalkPathfinder$$UnitIsBlockedByEnemyUnit` en produit un DYNAMIQUE : une tuile joignable a
        # vide peut ne plus l'etre une fois les ennemis places. C'est le MEME `path` vide.
        pos_now = _pos_by_squad(rpc, sid, rid)
        dv_units = {int(u["id"]): u for u in (dv.get("units") or []) if u.get("id") is not None}
        moi = dv_units.get(uid) or {}
        ennemis = {p for k, p in pos_now.items()
                   if k != uid and p is not None
                   and (dv_units.get(k) or {}).get("team") not in (None, moi.get("team"))}
        cnt_bloque = get_path_node_counts_by_pos(p1, neigh_by_pos=neigh, walkable_by_pos=walk,
                                                 elev_by_pos=elev, blocking_positions=ennemis)
        coupees = sorted(q for q in joignables
                         if q not in cnt_bloque and q not in ennemis and walk.get(q))
        print("[B1b] ennemis=%d ; tuiles joignables A VIDE mais COUPEES par eux : %d %s"
              % (len(ennemis), len(coupees), coupees[:6]))
        if coupees:
            cible = coupees[0]
            r = rpc(sid, "applyAction", {"runnerId": rid,
                                         "action": {"kind": "move", "unitId": uid,
                                                    "to": {"col": cible[0],
                                                           "row": cible[1]}}}, 60)
            pB = _pos_by_squad(rpc, sid, rid).get(uid)
            ok = (pB == p1)
            bad += 0 if ok else 1
            print("[B1b] move %s -> %s (coupee par les ennemis) : natif pos %s => %s"
                  % (p1, cible, pB, "N'A PAS BOUGE (conforme)" if ok else "A BOUGE"))

        # --- BRAS 1 : destination WALKABLE mais INJOIGNABLE (gate `path` vide).
        if not isolees:
            print("[B1] SANS OBJET sur ce board : aucune tuile walkable isolee de %s" % (p1,))
        else:
            cible = isolees[0]
            r = rpc(sid, "applyAction", {"runnerId": rid,
                                         "action": {"kind": "move", "unitId": uid,
                                                    "to": {"col": cible[0],
                                                           "row": cible[1]}}}, 60)
            p2 = _pos_by_squad(rpc, sid, rid).get(uid)
            ok = (p2 == p1)
            bad += 0 if ok else 1
            print("[B1] move %s -> %s (INJOIGNABLE) : natif pos %s (mutated=%s) => %s"
                  % (p1, cible, p2, r.get("mutated"),
                     "N'A PAS BOUGE (conforme)" if ok else "A BOUGE (le gate n'existe pas ?)"))
            st = _state(board, [(1, p1, 1, [])])
            MoveUnitOperation(1, cible, enforce_native_gates=False).execute(st, EventBus())
            print("[B1] PORT SANS le gate -> pos %s   |   PORT AVEC -> %s"
                  % (_pos(st, 1), _pos(_apply_with_gate(board, p1, cible), 1)))

        # --- BRAS 2 : destination OCCUPEE par une autre unite (gate `TilesAreEmpty`).
        # Le montage ne se CONTENTE PAS d'une voisine deja occupee : il RAPPROCHE le mover d'une
        # autre unite (« DEPLACE les unites pour forcer la configuration, jamais bloque par la
        # geometrie de spawn »). On vise donc, parmi les tuiles JOIGNABLES, celle qui est adjacente
        # a une unite tierce, puis on demande le pas final SUR cette unite.
        occ2 = {k: v for k, v in _pos_by_squad(rpc, sid, rid).items() if k != uid and v is not None}
        approche = cible2 = None
        for autre_id, ap in sorted(occ2.items()):
            for q in (neigh.get(ap) or []):
                if walk.get(q) and q in joignables and q not in set(occ2.values()):
                    approche, cible2 = q, ap
                    break
            if approche is not None:
                break
        if approche is None:
            print("[B2] aucune tuile joignable ADJACENTE a une autre unite -- NON CONFRONTE")
        else:
            if approche != p1:
                rpc(sid, "applyAction", {"runnerId": rid,
                                         "action": {"kind": "move", "unitId": uid,
                                                    "to": {"col": approche[0],
                                                           "row": approche[1]}}}, 60)
            pA = _pos_by_squad(rpc, sid, rid).get(uid)
            if pA != approche:
                print("[B2] l'approche %s -> %s a ECHOUE (pos %s) : hors portee ? NON CONFRONTE"
                      % (p1, approche, pA))
            else:
                r = rpc(sid, "applyAction", {"runnerId": rid,
                                             "action": {"kind": "move", "unitId": uid,
                                                        "to": {"col": cible2[0],
                                                               "row": cible2[1]}}}, 60)
                p3 = _pos_by_squad(rpc, sid, rid).get(uid)
                ok = (p3 == pA)
                bad += 0 if ok else 1
                print("[B2] move %s -> %s (OCCUPEE, distance 1) : natif pos %s (mutated=%s) => %s"
                      % (pA, cible2, p3, r.get("mutated"),
                         "N'A PAS BOUGE (conforme)" if ok else "A BOUGE"))
                st = _state(board, [(1, pA, 1, []), (2, cible2, 2, [])])
                MoveUnitOperation(1, cible2, enforce_native_gates=False).execute(st, EventBus())
                st2 = _state(board, [(1, pA, 1, []), (2, cible2, 2, [])])
                op2 = MoveUnitOperation(1, cible2)
                op2.execute(st2, EventBus())
                print("[B2] PORT SANS le gate -> pos %s (SUPERPOSITION)  |  AVEC -> %s (%r)"
                      % (_pos(st, 1), _pos(st2, 1), op2.last_abandoned))
    finally:
        try:
            rpc(sid, "disposeRunner", {"runnerId": rid}, 30)
            print("[B] runner %d dispose" % rid)
        except Exception as exc:                                       # noqa: BLE001
            print("[B] dispose KO : %s" % exc)
    return bad


def _apply_with_gate(board, src, dst) -> State:
    st = _state(board, [(1, src, 1, [])])
    MoveUnitOperation(1, dst).execute(st, EventBus())
    return st


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--board", default="C4_09")
    ap.add_argument("--boards", default="", help="liste separee par des virgules pour le volet B")
    ap.add_argument("--seed", type=int, default=777)
    a = ap.parse_args()
    if not (a.offline or a.live):
        a.offline = True
    bad = 0
    if a.offline or a.live:
        bad += volet_a(a.board)
    if a.live:
        for b in ([x.strip() for x in a.boards.split(",") if x.strip()] or [a.board]):
            bad += volet_b(b, a.seed)
    print("\n[448-r1-r1-r2-r2] %s (%d rouge(s))" % ("OK" if bad == 0 else "ROUGE", bad))
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
