"""GARDE OFFLINE #448-r1-r1-r1 -- la branche VOLANTE de `_movement_steps`.

`IdunBattle.Operations.MoveUnitOperation$$Execute`, au site de fin de mouvement :

    movementSteps = IsLikeFlying(unit, options)
                      ? battleQuery.<slot itf 0x6c = GetDistance>(path.First(), path.Last())
                      : path.Count

CE QUI REGRESSERAIT SANS CE FICHIER. Deux fautes, toutes deux silencieuses :

  * **supprimer la branche volante** (un seul `path.Count` pour tout le monde). Le `+1` de la
    branche marcheuse s'appliquerait aux volants et le gate de `1134 FullThrottle` mordrait
    des 2 hexes au lieu de 3. MESURE LIVE (greffe sur 5 volants du pool, board MC1_67,
    seed 777, `probe_448_r1_r1_r1_flying_movement_steps.py`) :

        bras                                   NATIF          PORT     PORT sans la branche
        M2  MARCHEUR d=2 (2 pas)             3 / 8  (37.5 %)    --              --
        V2  VOLANT   d=2 (vol direct)        0 / 20 ( 0.0 %)   0.0 %       **33.5 %**
        V3  VOLANT   d=3 (vol direct)        4 / 13 (30.8 %)  26.0 %          26.0 %
        VD  VOLANT   d=2 (vol DETOURNE)      0 / 14 ( 0.0 %)    --              --

    `P(0 mort sur 20 | gate vrai) = 0.7^20 = 0.08 %` -> le gate est bien FAUX a d=2 pour un
    volant, alors qu'il est VRAI a la MEME distance pour un marcheur (M2). C'est le couple
    qui prouve l'asymetrie ; V3 est le controle positif qui exclut « la greffe est inerte ».

  * **lire le CHEMIN au lieu de la DISTANCE** (`path.Count - 1`, la lecture qui coincide avec
    `GetDistance` sur tout vol DIRECT). Le bras VD la refute : 14 mouvements a `d = 2` dont le
    chemin de vol fait 3 ou 4 pas (murs `HulkWall` de `C6_25`), 0 mort -- alors qu'un
    `path.Count - 1 >= 3` aurait arme le gate. `P = 0.7^14 = 0.68 %`.

RE : le slot d'interface `0x6c` est RE-DERIVE au runtime (`probe_27_4g_battlequery_slots.py`,
build `rnca9r7q6c`) -> index de vtable `0x70` -> `IdunBattle.Core.Services.BattleQuery$$
GetDistance(tileA, tileB)` -> `IdunBattle.Core.Services.MovementQuery$$GetDistance(origin,
destination)` = min pairwise de `IdunBattle.Utils.Hex.CubeCoordinate$$Distance` = distance HEX.
Corroboration structurelle : `IdunBattle.Operations.MoveUnitOperation$$CalculatePaths` appelle
le MEME slot avec `(startTile, endTile)` et compare son retour au stat `Movement`.
Detail : `docs/rl/case-448-r1-r1-r1-flying-movement-steps.md`. ASCII only.
"""
from __future__ import annotations

import pytest

import hexgeo
import probe_448_r1_r1_r1_flying_movement_steps as P
from engine.entities.pathfinding.fly_pathfinder import is_like_flying
from engine.runner.operations.movement import _movement_steps, _num_tiles_moved

SRC = (4, 4)


@pytest.fixture(scope="module")
def flat():
    return P._synth_board()


@pytest.mark.parametrize("traits,expect", [(["Flying"], True), (["Burrow"], True),
                                           (["Flying", "Hulking"], True),
                                           (["Hulking"], False), ([], False), (None, False)])
def test_is_like_flying_est_flying_ou_burrow(traits, expect):
    """`IdunBattle.Entities.UnitExtensions$$IsLikeFlying(unit)` =
    `HasTrait(0x4 = Flying) || HasTrait(0x13 = Burrow)` -- les DEUX bras, lus au decompile.
    `Burrow` est le bras qu'on oublie : il vole aussi, au sens de ce predicat."""
    assert is_like_flying(traits) is expect


@pytest.mark.parametrize("d", [1, 2, 3, 4])
def test_branche_volante_rend_la_distance(flat, d):
    """La branche volante rend `GetDistance(path.First(), path.Last())`, PAS `path.Count`."""
    dst = P._dest_at_distance(flat, SRC, d)
    assert dst is not None, "montage : aucune tuile a d=%d" % d
    st = P._synth_state(flat, ["Flying"], SRC)
    assert _movement_steps(st, 1, SRC, dst) == d


@pytest.mark.parametrize("d", [1, 2, 3, 4])
def test_asymetrie_a_distance_egale(flat, d):
    """LE POINT MESURE. Meme depart, meme arrivee, meme distance : le volant rend UN DE MOINS
    que le marcheur. C'est cet ecart d'un cran qui deplace le seuil de `FullThrottle` de 2 a
    3 hexes selon le regime, et un port qui l'aplatirait tuerait la ou le natif ne tue pas."""
    dst = P._dest_at_distance(flat, SRC, d)
    fly = _movement_steps(P._synth_state(flat, ["Flying"], SRC), 1, SRC, dst)
    walk = _movement_steps(P._synth_state(flat, [], SRC), 1, SRC, dst)
    pas = _num_tiles_moved(P._synth_state(flat, [], SRC), 1, SRC, dst)
    assert (fly, walk) == (d, pas + 1)
    assert walk - fly == 1, "l'asymetrie du ternaire natif a disparu (fly=%d walk=%d)" % (fly, walk)


def test_branche_volante_ne_lit_pas_le_chemin():
    """Le DISCRIMINANT FIN. Un mur en arc laisse `d = 2` mais force le vol a contourner : la
    branche volante doit rendre **2**, jamais la longueur du detour.

    Sur un vol DIRECT, `GetDistance` et `path.Count - 1` coincident -- un accord obtenu la ne
    confirmerait rien. Ici les trois lectures divergent, et c'est ce qui rend la garde utile."""
    walls = [(3, 5), (4, 5), (5, 5), (3, 6), (5, 6)]
    board = P._synth_board(walls)
    src, dst = (4, 4), (4, 6)
    d = hexgeo.distance(src, dst)
    steps = P._fly_path_steps(board, src, dst)
    assert d == 2 and steps > d, ("montage : le mur ne detourne pas le vol (d=%d steps=%d)"
                                  % (d, steps))
    got = _movement_steps(P._synth_state(board, ["Flying"], src), 1, src, dst)
    assert got == d, ("branche volante = %d : elle a lu le CHEMIN (%d pas -> path.Count %d), "
                      "pas la distance" % (got, steps, steps + 1))


def test_mouvement_nul_et_absence_de_position(flat):
    """Les deux bords que le port traite a part, tous deux INOBSERVABLES par le seul lecteur
    (`FullThrottle` exige `>= 3`), mais qui doivent rester STABLES :
      * `from == to` -> 0 (le natif aurait `path.Count == 1` cote marcheur et `GetDistance` = 0
        cote volant -- l'ecart est un RESIDU NOMME, cf. la case-doc) ;
      * `from`/`to` absents -> 0 (le natif rendrait `int.MaxValue` sur un `GetDistance` a
        argument nul, autre RESIDU NOMME : aucun call-site du port ne le produit)."""
    st = P._synth_state(flat, ["Flying"], SRC)
    assert _movement_steps(st, 1, SRC, SRC) == 0
    assert _movement_steps(st, 1, None, SRC) == 0
    assert _movement_steps(st, 1, SRC, None) == 0
