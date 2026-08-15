"""#462-r4b-r1-r1-r1-r1-c-r3-r1-r5-r5 -- la POSE de la mine sur un deplacement MULTI-HEX.

CE QUE LE RESIDU CRAIGNAIT, ET CE QUE LE DECOMPILE REPOND
---------------------------------------------------------
Enonce : « Tous les bras joues ne bougent que d'UN hex, donc "PreviousTile = la tuile de DEPART" et
"= la derniere tuile INTERMEDIAIRE" sont indistinguables. [...] si le natif appelait
`SetUnitPosition` par PAS, la mine atterrirait sur l'avant-derniere tuile du chemin. »

**LE NATIF N'APPELLE PAS `SetUnitPosition` PAR PAS.** Lu verbatim dans
`IdunBattle.Operations.MoveUnitOperation$$Execute`, branche REELLE, DANS CET ORDRE :

    steppableUnits = BattleQuery.<slot 0x8f>(position)
    processor.<slot 0x7e>(unit, position, false)      <- L'ECRITURE DE POSITION, **UNE SEULE FOIS**,
                                                        avec la `position` de DESTINATION COMPLETE
    <log du mouvement>
    if (path.Count == 1) AddMoveEvent(..., startTile, isLast: 1, startTile, startTile, feet)
    else for (i = 1; i < path.Count; i++)                      <- LA BOUCLE PAR PAS EST **ICI**
             AddMoveEvent(..., path[i], isLast: i == connectedPath.Count - 1, <precedente>,
                          startTile, feet)
    KillSteppableUnits(this, unit, steppableUnits)

et `IdunBattle.Operations.MoveUnitOperation$$AddMoveEvent` **ne touche AUCUN composant ECS** : il
construit un `Dictionary<int,int>` (`0x79` pathTile, `0x80` isLastTile, `0x7a..0x7f` les pieds) et le
pousse dans `AOperation.get_Events()` par `AddStep(3, unit.Id, dict)`. Ses seules autres operations
sont des LECTURES (`HasTrait(unit, 0x13 = Burrow)`, `IsTeleportationTile`). C'est un canal de VUE.

Or `PreviousTile` lit `PositionComponent+0x88`, et le SEUL ecrivain de ce slot est
`IdunBattle.Operations.SetUnitPositionOperation$$SavePreviousPosition`, appele depuis
`SetUnitPositionOperation$$Execute` -- lui-meme le slot `0x7e` ci-dessus. Son entree est
`previousPosition = GetUnitPosition(unit, state)`, **capturee AVANT la boucle d'ecriture des pieds** :

    feet = GetUnitFeet(unit, state);
    if (feet.Count != position.Count)  { log; return; }           // S1
    if (HasFlag(unit, 6 = Dead))       { log; return; }           // S2
    previousPosition = GetUnitPosition(unit, state);              <- l'empreinte AVANT
    for (i = 0; i < feet.Count; i++) { ... ResetPreviousTile ... foot.<+0x14> = position[i].Id ... }
    if (!IsSimulation()) { if (previousPosition.Count >= 1) { comp.<+0x88> = comp.<+0x98>
                                              = Nullable(UnitPositionId(previousPosition)); } }
    VerifyTerritoryCapture(this, position);

⇒ `PreviousTile` vaut **la tuile de DEPART du mouvement ENTIER**, quelle que soit la longueur du
chemin. Les deux lectures que le residu declarait indistinguables ne le sont pas : la seconde
n'existe pas. **Le port est FIDELE** -- il fait UN `save_previous_position` avec l'empreinte de
depart, exactement au meme rang.

CE PROBE NE FAIT PAS QUE LE REDIRE -- IL LE MET EN REGIME
---------------------------------------------------------
`--volet offline` (0 runner) : force un chemin de **3 noeuds ou plus** sur un board reel, et
verifie (a) que `previous` vaut la tuile de DEPART, (b) que l'AVANT-DERNIERE tuile du chemin en est
DIFFERENTE -- sans quoi le regime serait degenere et ne prouverait rien --, (c) que
`save_previous_position` n'est appele **qu'une fois**, avec l'empreinte de depart.

`--volet live` : monte le runner `astarCyrus` (`Movement` releve), le fait bouger de **2+ hex**, et
confronte la tuile de la mine natif vs port sur le MEME etat et le MEME geste.

    python probe_462r4br5r5_pose_multihex.py --volet offline
    python probe_462r4br5r5_pose_multihex.py --volet live --board MC1_67
"""
from __future__ import annotations

import argparse
import pathlib
import sys

PYDIR = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

import hexgeo                                                                  # noqa: E402
import probe_448r1r1r2r2_gates_abandon as GA                                   # noqa: E402
import probe_448r1r1r3_double_parcours as DP                                   # noqa: E402
from engine.entities.pathfinding import walk_pathfinder as WP                  # noqa: E402
from engine.runner.components import PositionComponent                         # noqa: E402
from engine.runner.events import EventBus                                      # noqa: E402
from engine.runner.operations.movement import MoveUnitOperation                # noqa: E402
import engine.runner.operations.movement as MV                                 # noqa: E402


# --------------------------------------------------------------------------- VOLET OFFLINE
def volet_offline(board_id: str) -> int:
    bad = 0
    board = GA._load_board(board_id)
    neigh, walk, elev = board.walk_maps_by_pos()

    # --- LA GEOMETRIE : un chemin d'AU MOINS 4 noeuds, donc au moins TROIS pas parcourus.
    # C'est la condition SANS LAQUELLE le residu ne peut pas etre tranche : a un seul pas, la tuile
    # de depart EST l'avant-derniere du chemin, et les deux lectures coincident.
    src = dst = chemin = None
    for p in sorted(q for q, w in walk.items() if w):
        counts = WP.get_path_node_counts_by_pos(p, neigh_by_pos=neigh, walkable_by_pos=walk,
                                                elev_by_pos=elev)
        cands = sorted(q for q, n in counts.items() if n >= 4)
        if cands:
            src, dst = p, cands[0]
            chemin = WP.get_path_by_pos(src, dst, neigh_by_pos=neigh, walkable_by_pos=walk,
                                        elev_by_pos=elev)
            break
    if not chemin or len(chemin) < 3:
        print("[OFF] SANS OBJET : aucun chemin de 3+ noeuds sur %s -- le regime n'est pas monte"
              % board_id)
        return 1
    print("[OFF] board %s : %s -> %s, chemin de %d noeuds %s"
          % (board_id, src, dst, len(chemin), chemin))

    # --- NON-DEGENERESCENCE : l'avant-derniere tuile du chemin DIFFERE de la tuile de depart.
    # Sans ce controle, un accord « previous == depart » serait vrai pour la mauvaise raison.
    avant_derniere = chemin[-2]
    ok = (avant_derniere != src)
    bad += 0 if ok else 1
    print("[OFF] depart=%s  avant-derniere du chemin=%s  DISTINCTES=%s  => %s"
          % (src, avant_derniere, avant_derniere != src,
             "OK (le regime DISCRIMINE)" if ok else "REGIME DEGENERE, aucun verdict"))

    # --- LE MOUVEMENT, et le COMPTE d'ecritures de la position precedente.
    # Forme MODULE : `execute` resout `save_previous_position` par le global de `movement`, donc le
    # `setattr` mord (une liaison `from ... import` hissee, elle, serait INERTE -- #485-r1-r1).
    appels = []
    vrai = MV.save_previous_position

    def espion(state, unit_id, previous_tiles):
        appels.append([tuple(t) for t in (previous_tiles or ())])
        return vrai(state, unit_id, previous_tiles)

    MV.save_previous_position = espion
    try:
        st = DP._state(board, [(1, src, 1, [])])
        op = MoveUnitOperation(1, dst)
        op.execute(st, EventBus())
    finally:
        MV.save_previous_position = vrai

    e = st.get_entity(1)
    pc = e.get_component(PositionComponent)
    prev = [tuple(t) for t in (getattr(pc, "previous", None) or ())]
    pos = (pc.col, pc.row)
    print("[OFF] apres le move : pos=%s  previous=%s  last_path=%d noeuds  abandon=%r"
          % (pos, prev, len(op.last_path or ()), op.last_abandoned))
    print("[OFF] `save_previous_position` appele %d fois, avec %s" % (len(appels), appels))

    for libelle, cond in (
            ("le mover est ARRIVE a destination", pos == dst),
            ("`previous` vaut la tuile de DEPART", prev == [src]),
            ("`previous` n'est PAS l'avant-derniere du chemin", prev != [avant_derniere]),
            ("UNE SEULE ecriture de la position precedente", len(appels) == 1),
            ("cette ecriture porte l'empreinte de DEPART", appels == [[src]]),
            ("le chemin materialise fait bien 3+ noeuds", len(op.last_path or ()) >= 3)):
        bad += 0 if cond else 1
        print("[OFF] %-52s => %s" % (libelle, "OK" if cond else "ROUGE"))
    return bad


# --------------------------------------------------------------------------- VOLET LIVE
def volet_live(board_id: str, seed: str, units: str) -> int:
    """CONFRONTATION natif vs port sur un pas de 2+ hex, avec `HaywireMineAbility` comme LECTEUR.

    Le montage reprend celui de `probe_462_r4b_r1_r1_r1_r1_c_r3_r1_r5_haywire_pose.py` (dont on
    IMPORTE les helpers -- pas de fork), avec une seule difference, qui est tout le residu : la
    destination est prise a distance >= 2, et on exige que le CHEMIN fasse 3 noeuds ou plus."""
    import probe_462_r4b_r1_r1_r1_r1_c_r3_r1_r5_haywire_pose as H
    from engine.entities.pathfinding.board import Board
    from engine.runner.messages import MoveUnitMessage
    from engine.runner.runner import Runner

    R = H._host()
    sid = R._resolve_session()
    rpc = H._mk_rpc(R, sid)
    # `Movement` releve : sans ca le pas de 2+ hex n'est pas dans `aiMovableTiles` et le montage
    # serait « bloque par la geometrie de spawn » au lieu d'etre CRAFTE.
    rid, state_f = H._build(board_id, seed, units,
                            extra=["--unit-stat", "%s:Movement=25" % H.SUMMONER])
    print("[LIVE] runner=%d board=%s seed=%s" % (rid, board_id, seed))
    bad = 0
    try:
        dv = H._vue(rpc, rid)
        cyrus = H._by_vis(dv, H.SUMMONER)
        if cyrus is None:
            print("[LIVE] KO : %s absent du plateau -- NON CONFRONTE" % H.SUMMONER)
            return 2
        cid, avant = H._uid(cyrus), H._pos(cyrus)
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        board = Board(bg["tiles"], adjacency="evenq")
        neigh, walk, elev = board.walk_maps_by_pos()
        counts = WP.get_path_node_counts_by_pos(avant, neigh_by_pos=neigh, walkable_by_pos=walk,
                                                elev_by_pos=elev)
        # DESTINATION : distance hex >= 2 ET chemin de 3+ noeuds ET atteignable selon le NATIF.
        mov = H._movable(rpc, rid, cid)
        cands = sorted(t for t in mov
                       if hexgeo.distance(t, avant) >= 2 and (counts.get(t) or 0) >= 3)
        if not cands:
            print("[LIVE] aucune destination a 2+ hex dans `aiMovableTiles` (mov=%d) "
                  "-- NON CONFRONTE" % len(mov))
            return 2
        dest = cands[0]
        chemin = WP.get_path_by_pos(avant, dest, neigh_by_pos=neigh, walkable_by_pos=walk,
                                    elev_by_pos=elev)
        print("[LIVE] cyrus=%s  %s -> %s  distance=%d  chemin=%s"
              % (cid, avant, dest, hexgeo.distance(dest, avant), chemin))
        if not chemin or len(chemin) < 3 or chemin[-2] == avant:
            print("[LIVE] REGIME DEGENERE (chemin trop court, ou avant-derniere == depart) "
                  "-- aucun verdict")
            return 2

        cap = H._capture(rpc, rid)
        st = H._state(cap, int(seed))
        H._act(rpc, rid, {"kind": "move", "unitId": cid,
                          "to": {"col": dest[0], "row": dest[1]}})
        nat = sorted(H._mines(H._vue(rpc, rid)))
        r = Runner(st).install_default_handlers()
        r.apply(MoveUnitMessage(int(cid), (int(dest[0]), int(dest[1]))))
        port = sorted(H._mines_offline(st))
        print("[LIVE] mines natif=%s   port=%s" % (nat, port))
        for libelle, cond in (
                ("natif et port POSENT AU MEME ENDROIT", nat == port),
                ("la mine natif est sur la tuile de DEPART", avant in nat),
                ("elle n'est PAS sur l'avant-derniere du chemin",
                 tuple(chemin[-2]) not in [tuple(t) for t in nat])):
            bad += 0 if cond else 1
            print("[LIVE] %-48s => %s" % (libelle, "OK" if cond else "ROUGE"))
        return bad
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 20)
        try:
            state_f.unlink(missing_ok=True)
        except Exception:                                                   # noqa: BLE001
            pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--volet", default="offline", choices=("offline", "live"))
    ap.add_argument("--board", default="C4_09")
    ap.add_argument("--seed", default="777")
    ap.add_argument("--units", default="ultraTitus,orksNob")
    a = ap.parse_args()
    bad = volet_offline(a.board) if a.volet == "offline" else volet_live(a.board, a.seed, a.units)
    print("\n[462-...-r5-r5] %s (%d rouge(s))" % ("OK" if bad == 0 else "ROUGE", bad))
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
