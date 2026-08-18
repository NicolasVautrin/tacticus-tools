"""GARDE OFFLINE #448-r1-r1-r1-r1 -- `_num_tiles_moved` pour une unite VOLANTE.

CE QUI REGRESSERAIT SANS CE FICHIER. Le port prenait le **WalkPathfinder
INCONDITIONNELLEMENT**, alors que `IdunBattle.Core.Services.MovementQuery$$GetConnectedPathTo`
resout `IdunBattle.Core.Services.MovementQuery$$GetPathfinderTypeForUnit(unit)` =
`IsLikeFlying(unit) ? 3 : 0`. `IdunBattle.Entities.UnitExtensions$$RecordTilesMoved` enregistrait
donc des pas de MARCHE pour un volant -- dans `ActorStatisticsComponent+0xf0`, que lit
`IdunBattle.Entities.Formulas.TilesMovedThisTurnFormula$$Calculate`. Degradation SILENCIEUSE : ni
erreur ni crash, un simple compteur faux.

LA ROUTE DU VOL A TROIS ETAGES, pas un :

  1. `IdunBattle.Entities.Pathfinding.FlyPathfinder$$FindPath` **OVERRIDE**
     `BasePathfinder$$FindPath` et ne rend PAS le chemin : il le reduit a ses WAYPOINTS
     (extremites, tuiles de teleportation, et virages ayant un MUR dans leur couronne --
     `FlyPathfinder$$IsAnyAdjacentTileWall`) ;
  2. `GetConnectedPathTo` RE-DENSIFIE chaque saut restant par un `PathfinderType.Beeline`
     (`IdunBattle.Entities.Pathfinding.IgnoreEverythingPathfinder`), qui **traverse tout, murs
     compris** ;
  3. `IdunBattle.Core.Services.BattleQuery$$GetNumTilesMoved` = `Count - 1`.

RE-DERIVE AU RUNTIME (`resolveVtableSlot`, build `rnca9r7q6c`, vtable propre depuis `+0x138` par
pas de `0x10`) -- l'absence de ces methodes des tables de symboles ne prouvait rien, IL2CPP
DEDUPLIQUE les corps triviaux :

    FlyPathfinder              idx 0x0c WeightCost              -> corps TRIVIAL `return 10`
    FlyPathfinder              idx 0x09 IsValidFinalTile        -> WalkPathfinder$$IsValidFinalTile
    FlyPathfinder              idx 0x0a IsValidContinuePathTile -> corps TRIVIAL `return true`
    IgnoreEverythingPathfinder idx 0x0b IsValidPathNode         -> corps TRIVIAL `return true`
    IgnoreEverythingPathfinder idx 0x09 IsValidFinalTile        -> corps TRIVIAL `return true`

Le `WeightCost` UNIFORME est ce qui rend le port NON AMBIGU : a cout constant, le chemin de cout
minimal EST le chemin de longueur minimale, donc le residu de departage de `base_pathfinder` ne
mord pas sur cette branche.

REFUTE en chemin : le 5e parametre de `FindPath` n'est PAS un `maxRange`. Sa signature, lue dans
`data/symbols/<build>/frida/methods.tsv`, est `useTeleporter:System.Nullable<UseTeleporter>`, et
ni `BasePathfinder$$FindPath` ni `FlyPathfinder$$FindPath` ne le LISENT.

Detail : `docs/rl/case-448-r1-r1-r1-flying-movement-steps.md` §6. ASCII only.
"""
from __future__ import annotations

import pytest

import hexgeo
import probe_448_r1_r1_r1_flying_movement_steps as P
from engine.entities.pathfinding import base_pathfinder as BP
from engine.entities.pathfinding import beeline_pathfinder as BL
from engine.entities.pathfinding import fly_pathfinder as FLY
from engine.entities.pathfinding.board import Board
from engine.runner.operations.movement import _num_tiles_moved
from engine.services.movement_query import get_connected_path_to, get_num_tiles_moved

SRC = (4, 4)


def _board(walls=(), blocks=(), elev=None):
    """Board hex plat 9x9, adjacence GEOMETRIQUE, avec trois leviers SEPARES -- c'est cette
    separation qui fait les cas discriminants :

      * `walls`  : `isWall = True` ET `walkable = False`  -> ni le vol ni la marche ne passent ;
      * `blocks` : `isWall = False` ET `walkable = False` -> le vol SURVOLE (son arete ne teste
        que `IsWall`, cf. `#403`), la marche NON. C'est un `Block`/`Water` du jeu ;
      * `elev`   : `{(col,row) -> elevation}` -> la marche exige `|delta| <= 1`
        (`WalkPathfinder$$IsReachableElevationDifference`), le vol l'ignore totalement."""
    cols = rows = 9
    walls = {(int(c), int(r)) for c, r in walls}
    blocks = {(int(c), int(r)) for c, r in blocks}
    elev = dict(elev or {})

    def tid(c, r):
        return c * rows + r + 1
    tiles = []
    for c in range(cols):
        for r in range(rows):
            nb = [tid(cc, rr) for (cc, rr) in hexgeo.neighbors(c, r)
                  if 0 <= cc < cols and 0 <= rr < rows]
            w = (c, r) in walls
            tiles.append({"id": tid(c, r), "col": c, "row": r,
                          "elevation": int(elev.get((c, r), 0)),
                          "walkable": not (w or (c, r) in blocks), "isWall": w,
                          "neighbours": nb})
    return Board(tiles, adjacency="evenq")


@pytest.fixture(scope="module")
def flat():
    return _board()


# ─────────────────────────────────────────────────────────────────────────────────────────────
# ETAGE 1 -- `FlyPathfinder$$FindPath` rend des WAYPOINTS, pas le chemin
# ─────────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("d", [1, 2, 3, 4])
def test_vol_direct_se_reduit_aux_deux_extremites(flat, d):
    """Sans mur, `IsAnyAdjacentTileWall` est faux partout : AUCUN waypoint intermediaire n'est
    retenu, quel que soit le nombre de virages du chemin A*. C'est la propriete qui rend le
    compte volant INDEPENDANT du chemin choisi -- donc immunise contre le residu de departage."""
    dst = P._dest_at_distance(flat, SRC, d)
    assert dst is not None, "montage : aucune tuile a d=%d" % d
    wp = FLY.find_path(flat, flat.id_at(*SRC), flat.id_at(*dst))
    assert [flat.coord(t) for t in wp] == [SRC, dst]


def test_vol_detourne_retient_les_virages_pres_du_mur():
    """Avec des murs, le natif retient les points de virage dont la couronne porte un mur. Le
    chemin RECOUSU doit alors etre PLUS LONG que la simple distance -- sinon la simplification
    aurait tout aplati et le compte serait faux."""
    walls = [(3, 5), (4, 5), (5, 5), (3, 6), (5, 6)]
    b = _board(walls)
    src, dst = (4, 4), (4, 6)
    s, t = b.id_at(*src), b.id_at(*dst)
    steps = P._fly_path_steps(b, src, dst)
    assert hexgeo.distance(src, dst) == 2 and steps > 2, "montage : le mur ne detourne pas"
    wp = FLY.find_path(b, s, t)
    conn = get_connected_path_to(b, s, t, wp)
    assert len(wp) > 2, "aucun waypoint retenu : la simplification a aplati le detour"
    assert len(conn) >= len(wp), "la densification a RACCOURCI la liste de noeuds"
    assert get_num_tiles_moved(conn) > hexgeo.distance(src, dst)


def test_direction_to_est_le_delta_cube_sur_un_pas_unitaire(flat):
    """`IdunBattle.Utils.Hex.AxialCoordinate$$DirectionTo` -- le seul regime ou
    `FlyPathfinder$$FindPath` l'appelle. Deux tuiles NON adjacentes sortent du regime porte."""
    a = flat.id_at(4, 4)
    for nb in flat.neighbours_geometric(a):
        d = FLY.direction_to(flat, a, nb)
        assert d is not None and sorted(abs(v) for v in d) == [0, 1, 1]
        assert sum(d) == 0, "un delta cube a toujours x + y + z == 0"
    far = flat.id_at(4, 7)
    assert FLY.direction_to(flat, a, far) is None


# ─────────────────────────────────────────────────────────────────────────────────────────────
# ETAGE 2 -- la beeline TRAVERSE TOUT
# ─────────────────────────────────────────────────────────────────────────────────────────────
def test_beeline_traverse_les_murs():
    """Les trois predicats de l'`IgnoreEverythingPathfinder` sont des corps TRIVIAUX
    `return true` (RE-DERIVES AU RUNTIME). C'est ce qui autorise le chemin recousu a COUPER a
    travers un obstacle au lieu de le longer -- et donc a etre plus court que le chemin de vol."""
    b = _board(walls=[(4, 5)])
    a, z = b.id_at(4, 4), b.id_at(4, 6)
    path = BL.find_path(b, a, z)
    assert path is not None
    assert len(path) - 1 == hexgeo.distance((4, 4), (4, 6))
    assert any(b.is_wall(t) for t in path), "la beeline a CONTOURNE : elle doit traverser"


def test_beeline_weight_cost_est_dix_plus_is_filled():
    """`IgnoreEverythingPathfinder$$WeightCost` = `10 + IsFilled(tile)`, et
    `TileContentComponent$$IsFilled` = `comp[+0x10] != 0`. Le `+1` ne peut pas rallonger le
    chemin (une arete de plus coute 10) : il ne fait que departager a longueur egale."""
    assert (BL.weight_cost(False), BL.weight_cost(True)) == (10, 11)


# ─────────────────────────────────────────────────────────────────────────────────────────────
# ETAGE 3 -- `GetNumTilesMoved` et le compte final
# ─────────────────────────────────────────────────────────────────────────────────────────────
def test_get_num_tiles_moved_est_count_moins_un():
    """`IsNullOrEmpty(path) ? 0 : path.Count - 1` -- verbatim, y compris les deux bords."""
    assert get_num_tiles_moved(None) == 0
    assert get_num_tiles_moved([]) == 0
    assert get_num_tiles_moved([7]) == 0
    assert get_num_tiles_moved([7, 8, 9]) == 2


@pytest.mark.parametrize("d", [1, 2, 3, 4])
def test_compte_volant_vaut_la_distance_sur_board_plat(flat, d):
    dst = P._dest_at_distance(flat, SRC, d)
    assert _num_tiles_moved(P._synth_state(flat, ["Flying"], SRC), 1, SRC, dst) == d


@pytest.mark.parametrize("traits", [["Flying"], ["Burrow"], ["Flying", "Hulking"]])
def test_les_deux_traits_dIsLikeFlying_prennent_la_branche_volante(traits):
    """`IsLikeFlying` = `HasTrait(0x4 = Flying) || HasTrait(0x13 = Burrow)`. `Burrow` est le bras
    qu'on oublie -- il prend le MEME pathfinder, donc le meme compteur."""
    b = _board(blocks=[(4, 5), (3, 5), (5, 5), (3, 6), (5, 6)])
    src, dst = (4, 4), (4, 6)
    assert _num_tiles_moved(P._synth_state(b, traits, src), 1, src, dst) == 2


# ─────────────────────────────────────────────────────────────────────────────────────────────
# LE FIX MORD -- contre-epreuves, chacune avec son mecanisme NATIF distinct
# ─────────────────────────────────────────────────────────────────────────────────────────────
def test_block_survole_le_volant_compte_moins_que_le_marcheur():
    """DISCRIMINANT #1 -- `Block`/`Water` (`walkable = False`, `isWall = False`). L'arete du vol
    ne teste que `IsWall` (`#403`) : le volant SURVOLE et compte la distance, le marcheur
    contourne et compte son detour. C'est exactement ce que le port d'AVANT rendait pour LES
    DEUX."""
    b = _board(blocks=[(3, 5), (4, 5), (5, 5), (3, 6), (5, 6)])
    src, dst = (4, 4), (4, 6)
    fly = _num_tiles_moved(P._synth_state(b, ["Flying"], src), 1, src, dst)
    walk = _num_tiles_moved(P._synth_state(b, [], src), 1, src, dst)
    assert fly == hexgeo.distance(src, dst) == 2
    assert walk > fly, ("le marcheur devrait CONTOURNER le Block (walk=%d fly=%d) -- montage"
                        % (walk, fly))


def test_elevation_le_volant_lignore():
    """DISCRIMINANT #2 -- `WalkPathfinder$$IsReachableElevationDifference` (`|delta| <= 1`)
    n'existe pas dans l'arete du vol. Une crete a 3 fait contourner la marche, pas le vol.

    ⚠ La crete est PARTIELLE (3 colonnes) et pas une bande complete : une bande DECONNECTE la
    destination, et le port rend alors `0` -- le residu marche « injoignable -> 0 », qui n'est
    PAS ce qu'on veut mesurer ici. Mesure du montage : marche 5, vol 2."""
    crest = {(c, 5): 3 for c in (3, 4, 5)}
    b = _board(elev=crest)
    src, dst = (4, 4), (4, 6)
    fly = _num_tiles_moved(P._synth_state(b, ["Flying"], src), 1, src, dst)
    walk = _num_tiles_moved(P._synth_state(b, [], src), 1, src, dst)
    assert fly == 2
    assert walk > fly, "montage : la crete ne detourne pas la marche (walk=%d)" % walk
    assert walk == 5, "le detour de marche a change (walk=%d) : montage a re-calibrer" % walk


def test_contre_epreuve_le_port_davant_diverge(monkeypatch):
    """LA CONTRE-EPREUVE. On NIE la branche volante (`is_like_flying` -> False), c'est-a-dire le
    port d'AVANT #448-r1-r1-r1-r1, et le compte doit CHANGER. Sans elle, tous les verts
    ci-dessus seraient compatibles avec « le fix ne sert a rien »."""
    from engine.runner.operations import movement as MV
    b = _board(blocks=[(3, 5), (4, 5), (5, 5), (3, 6), (5, 6)])
    src, dst = (4, 4), (4, 6)
    fixed = _num_tiles_moved(P._synth_state(b, ["Flying"], src), 1, src, dst)
    monkeypatch.setattr(MV, "is_like_flying", lambda traits: False, raising=False)
    import engine.entities.pathfinding.fly_pathfinder as _F
    monkeypatch.setattr(_F, "is_like_flying", lambda traits: False)
    # ⚠ LE BINDING QUI DECIDE (#484, puis #10031). `_num_tiles_moved` ne lit pas `is_like_flying` :
    # il passe par `movement_query.get_pathfinder_type_for_unit`, qui l'importait DANS sa fonction
    # jusqu'a `492c722f` (« hisser 624 imports differes »). Hisse en FORME A, le nom etait copie
    # dans le namespace de `movement_query` et NI `MV` NI `_F` ne l'atteignaient : le mutant rendait
    # la MEME valeur, donc la contre-epreuve ne prouvait plus rien. La reponse d'alors fut de
    # patcher AUSSI `_MQ.is_like_flying` -- un contournement AU SITE DE MESURE, qui a reverdi CE
    # fichier en laissant la cause en place ; le meme desarmement a garde MUETS 13 jours le pendant
    # LIVE de `#381-r4` et son probe, qu'aucun cliquet ne joue.
    # `#10031` a repare le FOYER : `movement_query` est en FORME B, il resout `is_like_flying` A
    # L'APPEL, donc patcher la SOURCE (`_F`, deux lignes plus haut) SUFFIT de nouveau -- et le patch
    # `_MQ` est devenu impossible (`AttributeError`, le nom n'existe plus la-bas). La contre-epreuve
    # de morsure ci-dessous remplace ce patch : elle DIT si un futur re-hissage la rend muette, au
    # lieu de la laisser rendre silencieusement la meme valeur.
    from morsure_substitution import liaisons_figees_statiques
    figees = {m for m in liaisons_figees_statiques(
        "engine.entities.pathfinding.fly_pathfinder", "is_like_flying")
        if m.startswith("services/")}
    assert not figees, ("la negation de la branche volante ne mord pas : %s a(ont) fige "
                        "`is_like_flying` en forme A -- le mutant rendrait la MEME valeur "
                        "(#484, #10031)" % sorted(figees))
    avant = _num_tiles_moved(P._synth_state(b, ["Flying"], src), 1, src, dst)
    assert fixed == 2
    assert avant != fixed, "le mutant rend la MEME valeur : le test ne mesure rien"


# ─────────────────────────────────────────────────────────────────────────────────────────────
# NON-REGRESSION -- la branche MARCHE n'a pas bouge
# ─────────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("d", [1, 2, 3, 4])
def test_marche_inchangee_sur_board_plat(flat, d):
    """La marche garde son moteur en domaine POSITION (foyer partage avec la face DECISION,
    #304). Sur un board plat sans obstacle, elle vaut la distance."""
    dst = P._dest_at_distance(flat, SRC, d)
    assert _num_tiles_moved(P._synth_state(flat, [], SRC), 1, SRC, dst) == d


def test_bords_du_port(flat):
    """`from == to` -> 0 (le natif : `path = [to]`, `Count == 1`, donc `Count - 1 == 0`) ;
    extremite absente -> 0 ; pas de board -> 0."""
    st = P._synth_state(flat, ["Flying"], SRC)
    assert _num_tiles_moved(st, 1, SRC, SRC) == 0
    assert _num_tiles_moved(st, 1, None, SRC) == 0
    assert _num_tiles_moved(st, 1, SRC, None) == 0
    st.board = None
    assert _num_tiles_moved(st, 1, SRC, (4, 6)) == 0


# ─────────────────────────────────────────────────────────────────────────────────────────────
# `BasePathfinder$$FindPath` -- ses trois sorties nulles, lues au decompile
# ─────────────────────────────────────────────────────────────────────────────────────────────
def test_base_find_path_sorties_nulles(flat):
    """    if (fromTile == null || toTile == null)   return null;
        if (!IsValidFinalTile(unit, toTile))     return null;
        ... if (!cameFrom.TryGetValue(cur, out cur)) return null;   // injoignable

    Le troisieme bras se montre avec une destination ENCERCLEE de murs."""
    a = flat.id_at(*SRC)
    assert FLY.find_path(flat, None, a) is None
    assert FLY.find_path(flat, a, None) is None
    # `IsValidFinalTile` = `!IsTemporary && IsWalkable` -> une tuile non walkable est refusee.
    b = _board(blocks=[(4, 6)])
    assert FLY.find_path(b, b.id_at(*SRC), b.id_at(4, 6)) is None
    # Destination joignable par AUCUNE arete : couronne complete de murs.
    ring = [(c, r) for (c, r) in hexgeo.neighbors(0, 0)]
    c = _board(walls=ring)
    assert FLY.find_path(c, c.id_at(*SRC), c.id_at(0, 0)) is None


def test_base_find_path_from_egal_to(flat):
    """`from == to` : la boucle de remontee ne s'execute pas -> `[to]`, `Count == 1`."""
    a = flat.id_at(*SRC)
    assert FLY.find_path(flat, a, a) == [a]
    assert get_num_tiles_moved(FLY.find_path(flat, a, a)) == 0


def test_heuristic_est_la_somme_des_ecarts_offset(flat):
    """`BasePathfinder$$Heuristic` = `|dcol| + |drow|`, sur les DEUX composantes de la position."""
    assert BP.heuristic(flat, flat.id_at(4, 4), flat.id_at(4, 4)) == 0
    assert BP.heuristic(flat, flat.id_at(4, 4), flat.id_at(6, 1)) == 2 + 3


def test_get_connected_path_to_branche_degeneree(flat):
    """`if (path == null) return new List { from, to };` -- la branche que le natif prend quand
    le pathfinder ne rend rien. Elle vaut `Count == 2`, donc `GetNumTilesMoved == 1`."""
    a, z = flat.id_at(4, 4), flat.id_at(4, 6)
    assert get_connected_path_to(flat, a, z, None) == [a, z]
    assert get_num_tiles_moved(get_connected_path_to(flat, a, z, None)) == 1
