"""#448-r1-r1-r3 -- LES PARCOURS DE PATHFINDING D'UN MOUVEMENT : combien, et A QUEL RANG.

LE RESIDU DISAIT DEUX CHOSES, ET LES DEUX SONT FAUSSES
------------------------------------------------------
Enonce d'origine : « `_movement_steps` appelle `_num_tiles_moved` [...] puis `record_tiles_moved`
recalcule le MEME chemin quelques lignes plus bas. Correct -- la fonction est pure et ne tire aucun
aleatoire, aucun risque de divergence -- mais le cout est double ».

1. **Ce n'est pas DOUBLE, c'est TRIPLE.** `_calculate_path` (arrive avec #448-r1-r1-r2-r2, APRES
   la redaction du residu) ajoute un troisieme `_dijkstra_by_pos` complet. Le residu comptait un
   arbre qui avait grandi depuis.

2. **« Aucun risque de divergence » est FAUX, et c'est un ecart de RANG, pas de cout.** La fonction
   est pure EN SES ARGUMENTS, mais elle LIT `state` : `_blocking_positions(state, mover_id)` derive
   du plateau VIVANT. Or les deux appels du port n'ont pas lieu au meme moment :

       _movement_steps(...)          <- AVANT la mutation
       [ pc.col,pc.row = to ; apply_tile_defense_on_move ; _kill_steppable_units (et TOUTE la
         cascade de mort : On(1)/garde revive/On(2)/RemoveEffects x3/On(0)/On(0x36)/On(0x35)) ;
         update_charging ; set_moved_flag ; _remove_reservation ]
       record_tiles_moved(..., _num_tiles_moved(...))     <- APRES

   LE NATIF, LUI, N'A QU'UN SEUL POINT DE CALCUL, ET IL EST AMONT DE TOUT.
   `IdunBattle.Operations.MoveUnitOperation$$CalculatePaths` est appele UNE FOIS, et rend ses DEUX
   listes par out-param :

       path          = Pathfinders.<slot 4>(pathfinderType, unit, startTile, endTile, useTeleporter)
       connectedPath = BattleQuery.<slot 0x15>(unit, startTile, endTile)

   puis `IdunBattle.Operations.MoveUnitOperation$$Execute` les CONSOMME bien plus bas, apres
   `SetUnitPosition` / `KillSteppableUnits` / `SetMovedFlag` / `RemoveReservation` :

       movementSteps = isLikeFlying ? BattleQuery.<0x6c>(path.First(), path.Last()) : path.Count
       if (options+0x16 == 0) RecordTilesMoved(unit, BattleQuery.<0x17>(connectedPath), state)

   Les deux lectures portent donc sur des listes FIGEES AVANT la premiere mutation. Le port, lui,
   RE-DERIVE la seconde sur un plateau deja mute -- si la cascade de mort du crush a tue, ressuscite
   ou deplace une unite BLOQUANTE (le blast radius de `#462-...-c-r3-r1-r6`), `_blocking_positions`
   n'est plus le meme et `RecordTilesMoved` enregistre un compte que le natif n'aurait pas ecrit.

LE PLANCHER FIDELE EST **2**, PAS 1 -- et c'est LU
--------------------------------------------------
`CalculatePaths` fait DEUX parcours natifs distincts, et ils ne sont PAS interchangeables : `path`
voit l'override `MoveUnitOptions+0x8`, `connectedPath` re-resout `GetPathfinderTypeForUnit(unit)`
tout seul (appel a TROIS arguments, ni options ni pathfinderType). Fusionner les deux cote port
serait INFIDELE -- c'est deja ecrit dans `_movement_steps`. La reparation vise donc **3 -> 2**, et
pas davantage.

    python probe_448r1r1r3_double_parcours.py                 # mesure + rang
    python probe_448r1r1r3_double_parcours.py --board MC1_67
"""
from __future__ import annotations

import argparse
import pathlib
import sys
import time

PYDIR = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

import probe_448r1r1r2r2_gates_abandon as GA                                   # noqa: E402
from engine.entities.pathfinding import walk_pathfinder as WP                  # noqa: E402
from engine.entities.traits.unit_trait import UnitTrait                        # noqa: E402
from engine.runner.components import PositionComponent, UnitComponent          # noqa: E402
from engine.runner.events import EventBus                                      # noqa: E402
from engine.runner.operations.movement import MoveUnitOperation                # noqa: E402
import engine.runner.operations.movement as MV                                 # noqa: E402


class _StatsVides:
    """Le `ctx.stats` que `GA._state` ne pose pas -- son `UnitContext` est cree par `__new__`, donc
    NU. `triggers/tiles.py::apply_tile_defense_on_move` lit `sc.ctx.stats.components` des que la
    transition change le stat-mod DEFENSE de la tuile : sur `GA`, aucun bras ne tombe sur une telle
    tuile ; ici on en balaie 70, donc il faut le substrat. Un dict VIDE rend le bras no-op
    (`comp is None -> return None`), ce qui est exactement le regime « unite sans composant
    DEFENSE » que la fonction gate deja."""
    __slots__ = ("components",)

    def __init__(self):
        self.components = {}


def _state(board, units):
    """`GA._state`, plus le `ctx.stats` manquant."""
    st = GA._state(board, units)
    from engine.runner.components import StatsComponent
    for _uid, e in st.entities.items():
        sc = e.get_component(StatsComponent)
        if sc is not None and getattr(sc, "ctx", None) is not None:
            sc.ctx.stats = _StatsVides()
    return st


class _Compteur:
    """Espion sur `_dijkstra_by_pos` -- le moteur PARTAGE de `get_path_by_pos` et de
    `get_path_node_counts_by_pos`. Les deux le resolvent par le GLOBAL de leur propre module, donc
    un `setattr` sur le module MORD (ce n'est pas une liaison `from ... import` gelee)."""

    def __init__(self):
        self.n = 0
        self.origines: list = []
        self._vrai = WP._dijkstra_by_pos

    def __enter__(self):
        def espion(origin, *a, **kw):
            self.n += 1
            self.origines.append((origin[0], origin[1]))
            return self._vrai(origin, *a, **kw)
        WP._dijkstra_by_pos = espion
        return self

    def __exit__(self, *exc):
        WP._dijkstra_by_pos = self._vrai
        return False


def _paires_adjacentes(board, combien: int) -> list:
    """`combien` paires `(src, dst)` adjacentes et walkable -- des mouvements d'UN pas, le regime
    le plus courant d'un walk RL."""
    neigh, walk, _elev = board.walk_maps_by_pos()
    out = []
    for p in sorted(q for q, w in walk.items() if w):
        for q in (neigh.get(p) or ()):
            if walk.get(q):
                out.append((p, q))
                break
        if len(out) >= combien:
            break
    return out


def mesure_parcours(board, paires, regime_avant: bool = False, repets: int = 3) -> tuple:
    """(nb de dijkstras par mouvement, secondes du MEILLEUR tour, nb de mouvements).

    `regime_avant` RECONSTITUE le port d'avant #448-r1-r1-r3 sans y revenir : il rejoue, APRES le
    mouvement, le `_num_tiles_moved(state, unit, old_pos, to)` que `record_tiles_moved` faisait a
    ce rang-la. Meme appel, meme arguments, meme moment -- donc meme cout ET meme lecture d'un
    plateau deja mute. C'est ce qui rend le AVANT/APRES mesurable dans un seul arbre, au lieu de
    citer un chiffre pris sur un checkout disparu.

    Le CHRONO est bruite (la machine est partagee avec les autres agents) : on garde le MEILLEUR de
    `repets` tours. Le COMPTE de dijkstras, lui, est deterministe -- c'est le chiffre load-bearing."""
    best = None
    n = m = 0
    for _ in range(max(1, repets)):
        t0 = time.perf_counter()
        with _Compteur() as c:
            for src, dst in paires:
                st = _state(board, [(1, src, 1, [])])
                op = MoveUnitOperation(1, dst)
                op.execute(st, EventBus())
                if regime_avant and op.last_abandoned == "":
                    MV._num_tiles_moved(st, 1, src, dst)     # le 2e appel, au rang d'AVANT
        dt = time.perf_counter() - t0
        best = dt if best is None else min(best, dt)
        n, m = c.n, len(paires)
    return n, best, m


def mesure_rang(board, paires) -> dict:
    """LE RANG : a quel moment `_num_tiles_moved` est-il appele ?

    On substitue `MV._num_tiles_moved` (forme MODULE : `execute` le resout par le global de son
    propre module, donc le `setattr` mord) et on enregistre, A CHAQUE appel, la POSITION COURANTE du
    mover. Un appel POST-mutation se voit : le mover est deja arrive."""
    obs: list = []
    vrai = MV._num_tiles_moved

    def espion(state, mover_id, from_pos, to_pos):
        e = state.get_entity(int(mover_id))
        pc = e.get_component(PositionComponent) if e is not None else None
        obs.append(None if pc is None else (pc.col, pc.row))
        return vrai(state, mover_id, from_pos, to_pos)

    MV._num_tiles_moved = espion
    try:
        src, dst = paires[0]
        st = _state(board, [(1, src, 1, [])])
        MoveUnitOperation(1, dst).execute(st, EventBus())
    finally:
        MV._num_tiles_moved = vrai
    return {"src": src, "dst": dst, "positions_aux_appels": obs}


def mesure_divergence(board, paires) -> dict:
    """LE DISCRIMINANT : le port peut-il ECRIRE un compte que le natif n'ecrirait pas ?

    Regime monte : le mover ecrase un `Steppable`, et la CASCADE DE MORT de ce crush tue une unite
    ENNEMIE qui bloquait le chemin. C'est exactement le blast radius de
    `#462-r4b-r1-r1-r1-r1-c-r3-r1-r6` (les consommateurs des cinq evenements de mort), monte ici de
    facon SYNTHETIQUE -- on substitue `_kill_steppable_kill_unit` par un stub qui tue le bloqueur,
    parce qu'aucune ability du registre ne le fait OFFLINE. La question posee n'est pas « ce
    consommateur existe-t-il » (il existe, §6 de la fiche `-r1`) mais « le port lit-il un plateau
    MUTE quand il enregistre ». Rend les deux comptes."""
    neigh, walk, elev = board.walk_maps_by_pos()
    # LA GEOMETRIE EXIGEE, et les trois contraintes se tiennent :
    #   * `dest` doit etre la DESTINATION REELLE du mouvement (c'est la que le crush a lieu, donc la
    #     que la cascade de mort part) -- viser une AUTRE tuile ne prouve rien ;
    #   * son compte doit CHANGER selon que le bloqueur est vivant ou non (sinon les deux lectures
    #     coincident et le rang est indistinguable) ;
    #   * elle doit rester JOIGNABLE **avec** le bloqueur en place, sinon le gate `path` vide
    #     abandonne le mouvement avant toute mutation.
    trouve = None
    for src, _ in paires:
        counts_libre = WP.get_path_node_counts_by_pos(src, neigh_by_pos=neigh, walkable_by_pos=walk,
                                                      elev_by_pos=elev)
        for bloqueur in (neigh.get(src) or ()):
            if not walk.get(bloqueur):
                continue
            counts_bloq = WP.get_path_node_counts_by_pos(
                src, neigh_by_pos=neigh, walkable_by_pos=walk, elev_by_pos=elev,
                blocking_positions={bloqueur})
            dests = [q for q in counts_bloq                       # JOIGNABLE avec le bloqueur
                     if q != bloqueur and q != src and walk.get(q)
                     and counts_bloq[q] != counts_libre.get(q)]   # et le compte CHANGE sans lui
            if dests:
                dests.sort()
                trouve = (src, dests[0], bloqueur,
                          (counts_bloq[dests[0]], counts_libre.get(dests[0])))
                break
        if trouve:
            break
    if trouve is None:
        return {"regime": None}
    src, dest, bloqueur, temoin = trouve
    # Le mover va de `src` a `dest` en ECRASANT un Steppable pose sur `dest`. Le bloqueur ennemi est
    # sur `bloqueur`. Le stub tue le bloqueur PENDANT la cascade de mort du crush.
    out = {}
    for tuer_le_bloqueur in (False, True):
        st = _state(board, [(1, src, 1, []),
                               (2, dest, 2, [UnitTrait.Steppable]),
                               (3, bloqueur, 2, [])])
        vrai = MV._kill_steppable_kill_unit

        def stub(state, dead_id, killer_id, _t=tuer_le_bloqueur):
            r = vrai(state, dead_id, killer_id)
            if _t:                                   # la cascade tue une unite BLOQUANTE tierce
                state.get_entity(3).get_component(UnitComponent).alive = False
            return r
        MV._kill_steppable_kill_unit = stub
        try:
            op = MoveUnitOperation(1, dest)
            op.execute(st, EventBus())
        finally:
            MV._kill_steppable_kill_unit = vrai
        e = st.get_entity(1)
        uc = e.get_component(UnitComponent)
        out["mort_du_bloqueur" if tuer_le_bloqueur else "temoin"] = {
            "tiles_moved": int(getattr(uc, "tiles_moved_this_turn", 0) or 0),
            "movement_steps": op.last_movement_steps,
        }
    out["regime"] = {"src": src, "dest": dest, "bloqueur": bloqueur, "noeuds_avec_puis_sans_bloqueur": temoin}
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", default="C4_09")
    ap.add_argument("--moves", type=int, default=200)
    ap.add_argument("--repets", type=int, default=3)
    a = ap.parse_args()
    board = GA._load_board(a.board)
    paires = _paires_adjacentes(board, a.moves)
    print("[448-r1-r1-r3] board %s -- %d tuiles, %d mouvements d'UN pas"
          % (a.board, len(board.by_id), len(paires)))

    na, sa, m = mesure_parcours(board, paires, regime_avant=True, repets=a.repets)
    nb, sb, _ = mesure_parcours(board, paires, regime_avant=False, repets=a.repets)
    print("[PARCOURS] AVANT (2 appels a `_num_tiles_moved`) : %d dijkstra / %d moves = %.2f par "
          "move -- %.3f s (%.2f ms/move)" % (na, m, na / max(m, 1), sa, 1000.0 * sa / max(m, 1)))
    print("[PARCOURS] APRES (1 seul, au rang natif)         : %d dijkstra / %d moves = %.2f par "
          "move -- %.3f s (%.2f ms/move)" % (nb, m, nb / max(m, 1), sb, 1000.0 * sb / max(m, 1)))
    print("[PARCOURS] gain : %.1f %% des parcours, %.1f %% du temps"
          % (100.0 * (na - nb) / max(na, 1), 100.0 * (sa - sb) / max(sa, 1e-9)))
    print("[PARCOURS] plancher FIDELE = 2,00 par mouvement (`CalculatePaths` fait DEUX parcours "
          "natifs : `Pathfinders.GetPath` et `BattleQuery.GetConnectedPathTo`) ; on descend sous "
          "2,00 parce que les mouvements ABANDONNES par un gate n'en font aucun")

    r = mesure_rang(board, paires)
    print("[RANG] `_num_tiles_moved` appele %d fois ; position du mover a chaque appel : %s"
          % (len(r["positions_aux_appels"]), r["positions_aux_appels"]))
    print("[RANG] src=%s dst=%s -- un appel dont la position vaut DEJA dst est POST-MUTATION, "
          "donc hors rang natif" % (r["src"], r["dst"]))

    d = mesure_divergence(board, paires)
    if d.get("regime") is None:
        print("[DIVERGENCE] SANS OBJET sur ce board : aucune geometrie ou un voisin COUPE un chemin")
    else:
        print("[DIVERGENCE] regime %s" % (d["regime"],))
        print("[DIVERGENCE] temoin (rien ne meurt)      : %s" % (d["temoin"],))
        print("[DIVERGENCE] la cascade tue le bloqueur  : %s" % (d["mort_du_bloqueur"],))
        chg = d["temoin"] != d["mort_du_bloqueur"]
        print("[DIVERGENCE] le compte ENREGISTRE change avec l'etat POST-mutation : %s"
              % ("OUI -- le rang MORD" if chg else "non sur ce montage"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
