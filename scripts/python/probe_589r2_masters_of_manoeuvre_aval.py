"""#589-r2 -- l'aval de `tilesMovedThisTurn` RECONFRONTE pour `MastersOfManoeuvre`, dont le seuil
est desormais EXERCE.

POURQUOI CETTE TRANCHE EXISTE
------------------------------
`#589-r1` avait classe `MastersOfManoeuvre` SATURE (seuil `tilesTraversed` sous la borne) en
notant que son trigger n'etait PAS porte : le seuil n'etait exerce nulle part, donc l'inertie
suffisait. Le trigger EST porte depuis `#999-r1`
(`engine/runner/operations/triggers/loki/masters_of_manoeuvre.py`,
`MastersOfManoeuvrePlaceOnMove`), et les deux crans qui gardaient ce fait sont passes au ROUGE :

  * `tests/engine/entities/pathfinding/test_589r1_tiles_moved_consumers_offline.py`
    ::test_aucun_trigger_a_SEUIL_n_est_porte_sinon_l_aval_est_a_RECONFRONTER
  * `probe_589r1_tiles_moved_consumers_live.py --only INV` (meme cause, plus `EmpyricAmbush`,
    dont le rouge est PERIME depuis `#589-r1-r1`)

Ils font exactement leur travail. Ce probe est la RECONFRONTATION qu'ils reclament.

LE DECOMPILE, RELU VERBATIM SUR LE BUILD COURANT `t6dpr4k06g`
-------------------------------------------------------------
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.MastersOfManoeuvreAbility$$CreateTrigger`,
branche `<A>` (celle qui lit le compteur) :

    DSLTriggers.AmountIsEqualOrGreater(
        DSLFormulas.TilesMovedThisTurn( Actor@<DSLSelectors+0x40> ),
        DSLFormulas.Get( AbilityConfiguration.GetNumberConstant(
            config@<this+0x20>, AbilityConstantType.tilesTraversed = 0x88 ) ) )

`IdunBattle.Entities.Formulas.TilesMovedThisTurnFormula$$Calculate` rend
`<ActorStatisticsComponent>+0xf0` (et **0** quand l'entite n'a pas le composant).

LA BORNE, ET LE TROU QU'ELLE AVAIT
-----------------------------------
`IdunBattle.Core.Services.MovementQuery$$GetConnectedPathTo` ne recoud par une beeline QUE
`if (GetDistance(last, next) > 1)`. Le sous-chemin recousu compte alors au moins `d >= 2` aretes
dans les DEUX substrats (`C` inclus dans `G` ne peut qu'ALLONGER), donc tout seuil `K <= 2` est
franchi AVANT comme APRES le rebranchement de `#589` : il ne peut pas basculer.

⚠ **CETTE DERIVATION A UNE HYPOTHESE CACHEE : que la beeline TROUVE un chemin.** Relu verbatim,
le natif ne dégrade pas -- il LEVE :

    lVar4 = <pathfinders>.GetPath(2 = Beeline, unit, last, next, null);
    if (lVar4 == 0) goto LAB_1811aae04;      // -> FUN_1801f5460() = FUN_180201bc0(); swi(3)

et `IdunBattle.Entities.Pathfinding.BasePathfinder$$FindPath` rend bien `null` quand la
destination est INATTEIGNABLE dans le voisinage du pathfinder (l'echec du `TryGetValue` de la
remontee d'arbre BFS). Le port, lui, ecrit `for mid in (sub or [])[1:-1]` -- il AVALE l'absence
de chemin et compte le saut pour **1** arete. Dans ce regime, et dans lui seul, on aurait
`n_C < n_G`, donc un `n_C = 1 < 2 <= n_G` : **le seuil `K = 2` de `MastersOfManoeuvre`
BASCULERAIT**, dans le sens permissif-vers-restrictif.

Le cran `S1` de `probe_589r1 --only SCAN` ne pouvait pas le voir : il ECARTE ces couples en
silence (`if lg is None or lc is None: continue`) -- un compte filtre qui ne dit pas ce qu'il
filtre, exactement sur le seul regime qui casserait la borne. Le cran `BORNE` ci-dessous les
COMPTE au lieu de les jeter.

LES TROIS CRANS
---------------
  INV    (offline, aucun runner) -- K relu du gameconfig, le trigger porte et son SUJET
         RE-DERIVES du code, et le gate porte bascule a K exactement.
  BORNE  (live, 1 build) -- le trou de S1 : sur combien de couples la beeline ECHOUE-t-elle dans
         un substrat et pas dans l'autre ? c'est la mesure qui rend la borne vraie ou fausse.
  GATE   (live, meme boardGraph) -- le gate PORTE de `MastersOfManoeuvre` bascule-t-il entre les
         deux substrats ? avec TEMOIN NON-NUL obligatoire : `EmpyricAmbush` (K = 4, au-dessus de
         la borne) DOIT basculer sur le meme board, sinon la mesure ne sait rien voir et son
         « aucune bascule » ne vaut rien.

Usage (session warmee) :
    python probe_589r2_masters_of_manoeuvre_aval.py --only INV
    python probe_589r2_masters_of_manoeuvre_aval.py --only BORNE --board C1_74
    python probe_589r2_masters_of_manoeuvre_aval.py --only GATE  --board C1_74
ASCII only.
"""
from __future__ import annotations

import argparse
import pathlib
import sys
import types

PYDIR = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

#: Le board a `Bridge` de `#589-r1` : `G \ C != 0`, donc le rebranchement peut y mordre. Un board
#: ou les deux vues coincident est un TEMOIN DEGENERE -- le jouer seul ne prouverait rien.
BOARD_DEFAUT = "C1_74"

#: Les quatre regimes de `MovementQuery$$GetPathfinderTypeForUnit` qui comptent ici.
REGIMES = {0: "Walk", 3: "Fly", 6: "TeleportStrike(Walk)", 7: "TeleportStrike(+Fly)"}


# --------------------------------------------------------------------------- cran INV (offline)
def _k_du_gameconfig() -> int:
    """`AbilityConfiguration$$GetNumberConstant(config, AbilityConstantType.tilesTraversed = 0x88)`
    -- RELU du gameconfig courant, jamais recopie du decompile.

    Passe par le foyer du port (`masters_of_manoeuvre_constant`) pour que le probe et le moteur
    lisent la MEME chose : une divergence entre les deux serait invisible sinon."""
    from engine.runner.operations.triggers.loki.masters_of_manoeuvre import (
        CONST_TILES_TRAVERSED, masters_of_manoeuvre_constant)
    return int(masters_of_manoeuvre_constant(CONST_TILES_TRAVERSED))


def _gate_porte():
    """Le gate REEL du port -- pas une re-ecriture. C'est lui que le trigger evalue."""
    from engine.runner.operations.triggers.loki.masters_of_manoeuvre import (
        masters_of_manoeuvre_tiles_gate)
    return masters_of_manoeuvre_tiles_gate()


def _eval_gate(gate, n) -> bool:
    """Evalue le gate sur un `AbilityEntities` MINIMAL dont l'ACTEUR porte `n`.

    `Actor().select(ctx)` rend `ctx.actor` : un namespace suffit, et c'est VOULU -- on veut
    exercer le NOEUD, pas le montage d'un `State`. `n = None` modelise le compteur NON MESURE."""
    actor = {} if n is None else {"tilesMovedThisTurn": int(n)}
    return bool(gate.should_trigger(types.SimpleNamespace(actor=actor, subject=None,
                                                          owner=None, caster=None, target=None)))


def _sujet_du_gate_porte() -> str:
    """Le SUJET que le port passe a `TilesMovedThisTurn`, DERIVE de l'objet construit (jamais lu
    dans une docstring) : le natif cite `Actor@<DSLSelectors+0x40>`."""
    g = _gate_porte()
    for attr in ("amount", "left", "value", "a", "formula"):
        node = getattr(g, attr, None)
        unit = getattr(node, "unit", None)
        if unit is not None:
            return type(unit).__name__
    return "?"


def run_inv() -> int:
    print("== INV -- le consommateur PORTE, re-derive du code (offline)")
    bad = 0
    k = _k_du_gameconfig()
    print("  K = `tilesTraversed` relu du gameconfig courant : %s" % k)
    if k <= 0:
        print("     ECART: constante absente ou nulle -- le seuil n'est pas mesure")
        bad += 1

    # Le FAIT qui motive la tranche, re-derive : le trigger est PORTE. S'il disparaissait, ce
    # probe deviendrait un temoin vide et doit le DIRE.
    try:
        from engine.runner.operations.triggers.loki.masters_of_manoeuvre import (
            MastersOfManoeuvrePlaceOnMove)
        porte = True
    except ImportError:
        MastersOfManoeuvrePlaceOnMove = None
        porte = False
    print("  trigger porte (`MastersOfManoeuvrePlaceOnMove`) : %s" % porte)
    if not porte:
        print("     ECART: le trigger n'est plus porte -- cette tranche n'a plus d'objet, et les "
              "crans ci-dessous ne mesurent RIEN")
        return bad + 1

    from engine.dsl.event_trigger_type import EventTriggerType
    ev = int(MastersOfManoeuvrePlaceOnMove.event_id)
    print("  branche <A> : `On(%d = %s)`" % (ev, EventTriggerType(ev).name))
    if ev != int(EventTriggerType.UnitAfterMove):
        print("     ECART: la branche qui porte le seuil n'est plus `On(UnitAfterMove)`")
        bad += 1

    sujet = _sujet_du_gate_porte()
    print("  sujet du `TilesMovedThisTurn` porte : %s   (natif : Actor@<DSLSelectors+0x40>)" % sujet)
    if sujet != "Actor":
        print("     ECART: le sujet n'est pas l'ACTEUR -- le natif lit `+0x40`")
        bad += 1

    # LE GATE BASCULE A K EXACTEMENT -- `AmountIsEqualOrGreater`, donc `>=`, pas `>`.
    gate = _gate_porte()
    sous = [n for n in range(0, k) if _eval_gate(gate, n)]
    au_dessus = [n for n in (k, k + 1, k + 7) if not _eval_gate(gate, n)]
    print("  bascule : ouvert sous K -> %s ; ferme a K et au-dessus -> %s"
          % (sous or "(aucun)", au_dessus or "(aucun)"))
    if sous or au_dessus:
        print("     ECART: le gate ne bascule pas a K = %d" % k)
        bad += 1
    # TRI-ETAT : compteur NON MESURE. Le natif rend 0 quand l'entite n'a pas le composant, donc
    # le gate est FERME -- degradation RESTRICTIVE, et c'est ce que le port doit faire.
    if _eval_gate(gate, None):
        print("     ECART: compteur NON MESURE -> le gate s'ouvre (le natif rend 0, donc ferme)")
        bad += 1
    else:
        print("  compteur NON MESURE -> gate ferme (mirror du `return 0` de `$$Calculate`)")

    print("\n  VERDICT INV: %s (%d ecart(s))" % ("PASS" if bad == 0 else "FAIL", bad))
    return bad


# --------------------------------------------------------------------------- infra live
def _board_graph(board_id: str, seed: int, reuse: bool):
    """Le `boardGraph`, capte par le montage DEJA ECRIT de `#589-r1` (cache dans `logs/`)."""
    from probe_589r1_tiles_moved_consumers_live import _get_board_graph, _rpc_factory
    sid, rpc = _rpc_factory()
    return _get_board_graph(sid, rpc, board_id, seed, reuse)


def _charge_board(board_id: str, seed: int, reuse: bool):
    from engine.entities.pathfinding.board import Board
    bg = _board_graph(board_id, seed, reuse)
    bd = Board(bg["tiles"], adjacency="native_sym")
    if not bd.has_connectivity_channel():
        print("   CANAL ABSENT du boardGraph -- NON MESURE (jamais rendu comme un zero)")
        return None, None
    return bd, Board


# --------------------------------------------------------------------------- cran BORNE (live)
def run_borne(board_id: str, seed: int, reuse: bool) -> int:
    """LE TROU DE `S1` : les couples ou la beeline ECHOUE, comptes au lieu d'etre jetes.

    Deux gisements, et le second est le seul qui compte vraiment :
      B1  TOUS les couples a `d_hex > 1` -- borne SUPERIEURE du gisement ;
      B2  les sauts REELLEMENT recousus par `GetConnectedPathTo` sur de vrais chemins volants --
          c'est ce que `MoveUnitOperation$$Execute` fait jouer.
    """
    import hexgeo
    from probe_589r1_tiles_moved_consumers_live import _beeline_len

    bd, Board = _charge_board(board_id, seed, reuse)
    if bd is None:
        return 1
    ids = sorted(bd.by_id)
    print("== BORNE  board=%s  %d tuiles" % (board_id, len(ids)))
    bad = 0

    # --- B1 : le gisement brut.
    n_couples = echec_c = echec_g = echec_2 = 0
    sous_borne = []
    mini_g = mini_c = None
    for a in ids:
        for b in ids:
            if a == b or hexgeo.distance(bd.coord(a), bd.coord(b)) <= 1:
                continue
            n_couples += 1
            lg = _beeline_len(bd, bd.neighbours_geometric, a, b)
            lc = _beeline_len(bd, lambda t: bd.neighbours_connectivity(t) or [], a, b)
            if lg is None and lc is None:
                echec_2 += 1
                continue
            if lg is None:
                echec_g += 1
                continue
            if lc is None:
                # LE REGIME CRITIQUE : le natif LEVE (`swi(3)`), le port compte le saut pour 1.
                echec_c += 1
                continue
            mini_g = lg if mini_g is None else min(mini_g, lg)
            mini_c = lc if mini_c is None else min(mini_c, lc)
            if min(lg, lc) < 2:
                sous_borne.append((bd.coord(a), bd.coord(b), lg, lc))
    print("  [B1] %d couple(s) a d_hex > 1" % n_couples)
    print("       min(beeline) : G=%s  C=%s   (la borne exige >= 2)" % (mini_g, mini_c))
    print("       ECARTES PAR CE FILTRE -- beeline SANS chemin : canal seul=%d, geometrie seule=%d,"
          " les deux=%d" % (echec_c, echec_g, echec_2))
    if mini_g is None or mini_c is None:
        print("       ECART: aucun couple mesurable -- le board ne garde rien")
        bad += 1
    if sous_borne:
        print("       ECART: %d couple(s) SOUS la borne -- la saturation des seuils <= 2 TOMBE"
              % len(sous_borne))
        for v in sous_borne[:6]:
            print("         %s -> %s  G=%d C=%d" % v)
        bad += 1
    if echec_c:
        print("       ECART: %d couple(s) ou la beeline CANAL n'a pas de chemin et la GEOMETRIE en"
              " a un. Le natif y LEVE (`BasePathfinder$$FindPath` -> null -> `swi(3)`), le port"
              " compte le saut pour 1 arete : c'est le SEUL regime ou `n_C < n_G`, donc le seul"
              " ou le seuil K = 2 pourrait basculer." % echec_c)
        bad += 1

    # --- B2 : les sauts REELLEMENT demandes. Un couple de B1 n'est recousu que s'il apparait
    #     comme deux noeuds CONSECUTIFS d'un chemin rendu par un pathfinder.
    from engine.entities.pathfinding import pathfinders as _pf
    sauts, sauts_ko = set(), set()
    for pt in (3, 6, 7):
        for a in ids:
            for b in ids:
                if a == b:
                    continue
                path = _pf.find_path(bd, pt, a, b)
                if not path:
                    continue
                for x, y in zip(path, path[1:]):
                    if hexgeo.distance(bd.coord(x), bd.coord(y)) <= 1:
                        continue
                    sauts.add((x, y))
                    if _beeline_len(bd, lambda t: bd.neighbours_connectivity(t) or [], x, y) is None:
                        sauts_ko.add((x, y))
    print("  [B2] sauts REELLEMENT recousus par `GetConnectedPathTo` (regimes 3/6/7) : %d"
          % len(sauts))
    print("       ... dont SANS chemin canal : %d" % len(sauts_ko))
    if not sauts:
        print("       ECART: aucun saut recousu -- ce board ne fait pas jouer la beeline, la"
              " mesure est DEGENEREE")
        bad += 1
    if sauts_ko:
        print("       ECART: la borne TOMBE sur les sauts reellement joues")
        for s in sorted(sauts_ko)[:6]:
            print("         %s -> %s" % (bd.coord(s[0]), bd.coord(s[1])))
        bad += 1
    print("\n  VERDICT BORNE: %s (%d ecart(s))" % ("PASS" if bad == 0 else "FAIL", bad))
    return bad


# --------------------------------------------------------------------------- cran GATE (live)
def run_gate(board_id: str, seed: int, reuse: bool) -> int:
    """LE GATE PORTE, evalue sur les DEUX substrats, sur tous les couples et tous les regimes.

    TEMOIN NON-NUL OBLIGATOIRE : `EmpyricAmbush` (K = 4 > borne) DOIT basculer sur ce board.
    Sans lui, « `MastersOfManoeuvre` ne bascule jamais » serait indistinguable d'une mesure qui
    ne sait rien voir -- l'accord en regime degenere ne prouve rien."""
    from probe_589r1_tiles_moved_consumers_live import _connected_len

    bd, Board = _charge_board(board_id, seed, reuse)
    if bd is None:
        return 1
    ids = sorted(bd.by_id)
    k = _k_du_gameconfig()
    gate = _gate_porte()

    import gameconfig as GC
    k_temoin = int(((GC.ability("EmpyricAmbush") or {}).get("constants") or {}).get("movement"))
    print("== GATE  board=%s  %d tuiles   K(MastersOfManoeuvre)=%d   K(temoin EmpyricAmbush)=%d"
          % (board_id, len(ids), k, k_temoin))
    bad = 0
    bascule_mom = bascule_temoin = divergents = 0
    exemples = []

    for pt, nom in sorted(REGIMES.items()):
        b_mom = b_tem = div = 0
        for a in ids:
            for b in ids:
                if a == b:
                    continue
                ng = _connected_len(bd, Board, pt, a, b, "G")
                nc = _connected_len(bd, Board, pt, a, b, "C")
                if ng != nc:
                    div += 1
                # Le gate PORTE, evalue sur les deux substrats. C'est la question de #589 posee
                # au consommateur lui-meme, pas a un scalaire intermediaire.
                if _eval_gate(gate, ng) != _eval_gate(gate, nc):
                    b_mom += 1
                    if len(exemples) < 6:
                        exemples.append((nom, bd.coord(a), bd.coord(b), ng, nc))
                if (ng >= k_temoin) != (nc >= k_temoin):
                    b_tem += 1
        print("  ptype=%-2d %-22s : %4d couple(s) divergents   MoM bascule=%d   temoin bascule=%d"
              % (pt, nom, div, b_mom, b_tem))
        divergents += div
        bascule_mom += b_mom
        bascule_temoin += b_tem

    if divergents == 0:
        print("  ECART: AUCUN couple divergent -- ce board ne fait pas mordre le rebranchement,"
              " la mesure est DEGENEREE et son verdict ne vaut rien")
        bad += 1
    if bascule_temoin == 0:
        print("  ECART: le TEMOIN `EmpyricAmbush` (K=%d) ne bascule nulle part -- la mesure ne sait"
              " pas voir une bascule, donc le zero de `MastersOfManoeuvre` ne prouve RIEN"
              % k_temoin)
        bad += 1
    if bascule_mom:
        print("  ECART: le gate porte de `MastersOfManoeuvre` BASCULE sur %d couple(s) -- l'aval de"
              " #589 le touche, il n'est PAS sature" % bascule_mom)
        for e in exemples:
            print("         %-22s %s -> %s : n_G=%s n_C=%s" % e)
        bad += 1
    else:
        print("  `MastersOfManoeuvre` (K=%d) : AUCUNE bascule sur %d couple(s) divergents, %d"
              " regimes -- SATURE par la borne, et le temoin (%d bascules) prouve que la mesure"
              " sait en voir une." % (k, divergents, len(REGIMES), bascule_temoin))
    print("\n  VERDICT GATE: %s (%d ecart(s))" % ("PASS" if bad == 0 else "FAIL", bad))
    return bad


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--only", choices=("INV", "BORNE", "GATE"), default="INV")
    ap.add_argument("--board", default=BOARD_DEFAUT)
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--no-reuse", action="store_true",
                    help="re-capte le boardGraph au lieu de relire le cache de `logs/`")
    a = ap.parse_args()
    if a.only == "INV":
        return 1 if run_inv() else 0
    if a.only == "BORNE":
        return 1 if run_borne(a.board, a.seed, not a.no_reuse) else 0
    return 1 if run_gate(a.board, a.seed, not a.no_reuse) else 0


if __name__ == "__main__":
    raise SystemExit(main())
