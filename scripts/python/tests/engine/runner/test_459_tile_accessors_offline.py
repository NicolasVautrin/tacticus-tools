"""#459 -- GARDE offline des DEUX residus geometriques laisses par #433-r3-r1a.

ITEM 1 (`#433-r3-r1a-r2`) -- les accesseurs de tuile rendent l'EMPREINTE, pas une position.
Lu au decompile `rnca9r7q6c` :

  * `IdunBattle.Entities.Selectors.CasterTileSelector$$Select` :
        tiles = entities.CasterPosition.Tiles  (+0x48)
             ?? entities.CasterTile.ToList()   (+0x40)
             ?? EntityExtensions.GetTiles(entities.Caster, state);   (+0x08)
        return new List(tiles);
    -- AUCUNE branche `GetMainTile`. Idem `TargetTilesSelector$$Select` sur `TargetPosition` (+0x38)
    / `TargetTile` (+0x30) / `GetTiles(Target)` (+0x10). Les slots sont identifies sans ambiguite
    par `IdunBattleLogic.Entities.DSLTriggers$$get_CasterIsCasterTile` = `AreEqual(+0x48, +0x50)`
    et `$$get_OwnerIsTargetTile` = `AreEqual(+0x78, +0x30)`.
  * `OwnerTile` n'est PAS un slot : quand le natif veut la main tile de l'owner il ecrit
    `IdunBattleLogic.Entities.DSLSelectors$$MainTileOfUnits(Owner@0x148)`
    (`$$get_OwnerTileIsTarget`). Aux call-sites portes il passe l'ENTITE `Owner@0x148` a
    `Adjacent*`, que `IdunBattle.DSL.TargetsSelector$$SelectTiles` deplie en son empreinte.
  * Le contrat de consommation a DEUX faces :
        SelectTiles (PLURIEL)  -> l'empreinte  (voisinage)
        SelectTile  (SINGULIER)-> la PREMIERE tuile, `GetMainTile` pour une unite/un pied
    -- `IdunBattle.DSL.TargetsSelector$$SelectTile`, que lisent `MovableTilesInRangeSelector`,
    `TilesBehindInLineSelector` (origin ET direction) et le referent de `SortByDistanceSelector`.

ITEM 1bis -- L'EXCLUSION DU CENTRE N'EST PAS LA MEME DES DEUX COTES, et c'est le SELECTEUR qui
tranche, pas le rayon :

  * `AdjacentTilesSelector$$Select` : `tiles = source.SelectTiles(entities)` puis
    `if (!tiles.Contains(a))` -> l'EMPREINTE ENTIERE est retranchee ;
  * `DSLSelectors$$SurroundingTiles(origin, includeCenter: 0, ...)` =
    `SurroundingTiles(origin, 1, ...) op_Subtraction Tiles(origin)`, et `Tiles` =
    `UnitsMainTilesSelector$$Select` = `GetMainTile` par ENTITE.

⚠ **CE FICHIER A TESTE LA RECIPROQUE SUR LA MAUVAISE ORIGINE, ET IL SE CONTREDISAIT LUI-MEME**
(corrige par #10023-r3). « `GetMainTile` par ENTITE -> UNE SEULE tuile » n'est vrai que si
l'origine n'ENUMERE QU'UNE entite. Or `test_target_tile_returns_the_whole_footprint`, deux tests
plus haut, etablit que `TargetTile()` en rend **TROIS** -- et `TargetsSelector$$SelectAllUnits`
ouvre par `if (this.<klass+0x278 = get_ReturnsOnlyUnits>()) return list;`, donc sous ce regime les
trois entites-TUILE traversent SANS resolution et `EntityExtensions$$GetMainTileId` fait de chacune
SA PROPRE main tile (3e branche). Trois tuiles retranchees, pas une.

DEUX mesures INDEPENDANTES l'etablissent, et la seconde est ce qui autorise a transporter la
premiere :

  1. **LIVE** -- `1094 TheLantern` sur `deathBossMortarion` (SEPT hex, `GB_Mortarion_05`) :
     `Tiles(CasterTiles)` retranche les SEPT tuiles, pas la seule main tile (9 tuiles marquees
     contre 10 ; `probe_10023r3_caster_tiles_regime_live.py`). Donc
     `CasterTileSelector.ReturnsOnlyUnits == VRAI`.
  2. **METADATA** -- `global-metadata.dat`, indexee par TYPE (donc immunisee a la deduplication de
     CODE qui aveugle `frida/methods.tsv`) : `CasterTileSelector` et `TargetTilesSelector` derivent
     TOUTES DEUX de `IdunBattle.DSL.TargetsSelector` et ne declarent QUE `.ctor` et `Select` --
     **aucun override de `get_ReturnsOnly*`**. Elles heritent donc de la MEME valeur, et la mesure
     faite sur l'une vaut pour l'autre. Cran executable : `probe_10023r1...` etage 7.

⇒ **LA RECIPROQUE EXISTE, MAIS SUR L'ORIGINE EN DOMAINE UNITE.** `Adjacent`/`Surrounding` rendent
des verdicts OPPOSES quand l'origine est `Target()` (UNE entite-unite : `SelectTiles` la deplie en
son empreinte -> tout retranche, tandis que `Tiles` rend `GetMainTile(unite)` -> une seule), et ils
COINCIDENT quand elle est `TargetTile()` (N entites-tuile). Les deux faits sont gardes ci-dessous.

ITEM 2 (`#457-r1`) -- `MovementQuery$$IsAdjacent` et la branche `feetCount == 7` de
`MovementQuery$$GetPossibleTileListsFromMovableTiles` sont le MEME appel a l'octet pres (meme slot
d'interface `0x4f`, meme receveur `MovementQuery+0x30`, memes flags `(0, 1, 1)`), donc la MEME vue :
`TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext` enumere la liste d'adjacence STOCKEE
(`ConnectivityComponent`) -> `Board.neighbours_native`, jamais `Board.neighbours()` (trie ET
symetrise). Le foyer unique est `movement_query.adjacent_tile_ids`.

Chaque axe porte sa CONTRE-EPREUVE, et chaque mutant doit mordre a SON cran et etre INERTE ailleurs.
ASCII only.
"""
from __future__ import annotations

import hexgeo
from engine.dsl.base import Const, DslContext, _select_tile, _within
from engine.entities.pathfinding.board import Board
from engine.entities.selectors.accessors import (CasterTile, OwnerTile, SelectTile, Target,
                                                 TargetTile)
from engine.entities.selectors.tiles import AdjacentTiles
from engine.entities.selectors.units import AdjacentUnits, SurroundingUnits
from engine.services import movement_query as MQ

COLS, ROWS = 9, 9

# Empreinte 3 tuiles ; `feet[0]` EST la main tile (mirror `GetMainTile` = 1er pied).
FEET = [(2, 1), (2, 2), (3, 2)]
# d=1 du pied (3,2), d=2 de la main tile (2,1) -> STRICTEMENT discriminant.
OBSERVER = (4, 2)


def _flat_board() -> Board:
    """Plateau plat, `neighbours` REMPLI (even-q clippe aux bords) : `Board.neighbours_native`
    distingue le champ ABSENT du champ PRESENT-ET-VIDE (#381-r3 / #457), et un `[]` litteral
    declarerait « aucun voisin natif » sur un plateau annonce sans trou."""
    idof, tid = {}, 1
    for c in range(COLS):
        for r in range(ROWS):
            idof[(c, r)] = tid
            tid += 1
    tiles = [{"id": i, "col": c, "row": r, "elevation": 0, "tileDefId": "Grass",
              "isTemporary": False, "isWall": False, "walkable": True, "occupantUnitId": None,
              "neighbours": [idof[n] for n in hexgeo.neighbors(c, r) if n in idof]}
             for (c, r), i in idof.items()]
    return Board(tiles, adjacency="evenq")


def _multi(uid=1, team=1, feet=None):
    fs = list(feet or FEET)
    return {"id": uid, "team": team, "hp": 100, "alive": True,
            "pos": {"col": fs[0][0], "row": fs[0][1]}, "feet": fs}


def _mono(uid=2, team=2, pos=OBSERVER):
    return {"id": uid, "team": team, "hp": 100, "alive": True,
            "pos": {"col": pos[0], "row": pos[1]}}


def _ctx(board, units, caster=None, target=None, caster_pos=None):
    return DslContext(caster=caster, target=target, units=list(units), board=board,
                      caster_pos=caster_pos)


def test_the_montage_is_discriminant():
    """Sans ce cran, tout le fichier passerait sur un montage DEGENERE."""
    assert hexgeo.distance(OBSERVER, FEET[0]) == 2, "l'observateur touche la MAIN TILE"
    assert min(hexgeo.distance(OBSERVER, f) for f in FEET) == 1, "aucun pied n'est adjacent"
    b = _flat_board()
    assert b.id_at(*OBSERVER) is not None and all(b.id_at(*f) is not None for f in FEET)
    # les pieds sont voisins entre eux -> l'exclusion d'empreinte est OBSERVABLE
    assert b.id_at(*FEET[1]) in b.neighbours_native(b.id_at(*FEET[0]))


# --------------------------------------------------- ITEM 1 : ce que rendent les trois accesseurs

def test_caster_tile_returns_the_whole_footprint():
    """`CasterTileSelector$$Select` -> `GetTiles(Caster)` : une LISTE, pas une position."""
    u = _multi()
    got = CasterTile().evaluate(_ctx(_flat_board(), [u], caster=u))
    assert got == FEET


def test_target_tile_returns_the_whole_footprint():
    """`TargetTilesSelector$$Select` -> `GetTiles(Target)`."""
    u = _multi()
    got = TargetTile().evaluate(_ctx(_flat_board(), [u], target=u))
    assert got == FEET


def test_owner_tile_returns_the_whole_footprint():
    """Les call-sites portes passent `Owner@0x148` (l'ENTITE) a `Adjacent*` ; `SelectTiles` la
    deplie. Ce n'est donc PAS `MainTileOfUnits(Owner)`, qui rendrait une tuile."""
    u = _multi()
    got = OwnerTile().evaluate(_ctx(_flat_board(), [u], caster=u))
    assert got == FEET


def test_caster_tile_prefers_the_candidate_position():
    """Branche 1 de la cascade : `CasterPosition.Tiles` prime sur `GetTiles(Caster)`.
    ⚠ RESIDU `#459-r1` : le port ne porte de la position candidate que sa MAIN TILE, d'ou UNE
    tuile la ou le natif rendrait l'empreinte candidate."""
    u = _multi()
    cand = (7, 7)
    got = CasterTile().evaluate(_ctx(_flat_board(), [u], caster=u, caster_pos=cand))
    assert got == [cand]


def test_absent_entity_yields_the_empty_footprint():
    """`GetTiles(null)` -> liste vide ; aucun voisinage invente."""
    assert TargetTile().evaluate(_ctx(_flat_board(), [])) == []
    assert CasterTile().evaluate(_ctx(_flat_board(), [])) == []


def test_select_tile_mirrors_the_singular_overload():
    """`TargetsSelector$$SelectTile` : la PREMIERE tuile = `GetMainTile` = `feet[0]`. C'est ce qui
    rend l'elargissement INERTE chez les consommateurs scalaires."""
    u = _multi()
    ctx = _ctx(_flat_board(), [u], caster=u, target=u)
    assert SelectTile(CasterTile()).evaluate(ctx) == FEET[0]
    assert SelectTile(TargetTile()).evaluate(ctx) == FEET[0]
    assert _select_tile(FEET) == FEET[0]
    assert _select_tile([]) is None and _select_tile(None) is None


def test_select_tile_is_identity_on_a_mono_hex_carrier():
    """Reciproque : sur une unite mono-hex, `SelectTile(CasterTile())` rend exactement ce que
    rendait l'accesseur scalaire d'avant #459."""
    u = _mono(uid=3, team=1, pos=(5, 5))
    ctx = _ctx(_flat_board(), [u], caster=u)
    assert SelectTile(CasterTile()).evaluate(ctx) == (5, 5)
    assert CasterTile().evaluate(ctx) == [(5, 5)]


# ------------------------------------------- ITEM 1 : le voisinage voit desormais TOUTE l'empreinte

def test_adjacent_units_sees_a_neighbour_of_a_secondary_foot():
    """Le correctif d'ORIGINE mord enfin sur un centre venu de `TargetTile()` : l'observateur
    touche `feet[2]`, PAS la main tile."""
    tgt, obs = _multi(), _mono()
    ring = AdjacentUnits(TargetTile()).evaluate(_ctx(_flat_board(), [tgt, obs], target=tgt))
    assert [u["id"] for u in ring] == [obs["id"]]


def test_adjacent_units_collapsed_accessor_would_miss_it():
    """CONTRE-EPREUVE : l'accesseur SCALAIRE d'avant #459 (la seule main tile comme centre) rate
    l'observateur -- ET ramene la cible elle-meme, puisque son pied (2,2) touche sa main tile
    (2,1) que l'exclusion scalaire est seule a retirer. Les DEUX symptomes du collapse, sur le
    meme appel."""
    tgt, obs = _multi(), _mono()
    ids = [u["id"] for u in _within([tgt, obs], FEET[0], 1,
                                    board=_flat_board(), order="adjacent")]
    assert obs["id"] not in ids
    assert ids == [tgt["id"]]


# ------------------------- ITEM 1bis : les deux exclusions, et leur RECIPROQUE sur le meme montage

def test_adjacent_excludes_the_whole_footprint():
    """`AdjacentTilesSelector` retranche `SelectTiles(origin)` : la cible multi-hex NE PEUT PAS
    ressortir de son propre `AdjacentUnits`, alors que ses pieds sont voisins les uns des autres."""
    tgt = _multi()
    ring = AdjacentUnits(TargetTile()).evaluate(_ctx(_flat_board(), [tgt], target=tgt))
    assert ring == []


def test_surrounding_also_excludes_the_footprint_on_a_TILE_domain_origin():
    """MEME montage, MEME rayon que le precedent -- et MEME verdict, parce que l'origine ENUMERE
    ici TROIS entites-TUILE.

    ⚠ CE TEST ASSERTIONNAIT `[tgt]`, ET IL ETAIT VERT parce que `_main_tiles` prenait
    `_origin_tiles(origin, board)[:1]`. Oracle et port portaient la MEME lecture : aucun cliquet ne
    pouvait la voir. Ce qui l'a retournee est une mesure EXTERIEURE (#10023-r3, en-tete de module),
    doublee de la metadata qui autorise a la transporter d'un selecteur a l'autre.

    Sous `ReturnsOnlyUnits == VRAI`, `Tiles(TargetTile())` = `GetMainTileId` de chacune des trois
    entites-tuile = elles-memes. L'origine ne peut donc PAS se selectionner elle-meme."""
    tgt = _multi()
    ring = SurroundingUnits(TargetTile(), Const(1)).evaluate(_ctx(_flat_board(), [tgt], target=tgt))
    assert [u["id"] for u in ring] == []


def test_the_two_exclusions_DIVERGE_on_a_UNIT_domain_origin():
    """LE GARDE QUI REMPLACE l'ancienne reciproque -- deplace sur l'origine qui la PORTE.

    `Target()` n'enumere qu'UNE entite-unite, et c'est la que les deux formes se separent :

      * `AdjacentTilesSelector` resout son origine par `SelectTiles` -> l'EMPREINTE -> tout
        retranche, donc l'unite ne ressort pas ;
      * `- Tiles(origin)` applique `GetMainTile` a l'unique entite -> `GetMainTile(unite)` = UNE
        tuile, donc l'unite SE SELECTIONNE elle-meme par un pied secondaire.

    C'est exactement ce que l'ancien test voulait garder ; il le cherchait sur `TargetTile()`, qui
    enumere l'empreinte et ou les deux formes coincident."""
    tgt = _multi()
    ctx = _ctx(_flat_board(), [tgt], target=tgt)
    adj = [u["id"] for u in AdjacentUnits(Target()).evaluate(ctx)]
    sur = [u["id"] for u in SurroundingUnits(Target(), Const(1)).evaluate(ctx)]
    assert adj == [], "l'empreinte entiere doit etre retranchee du cote ADJACENT"
    assert sur == [tgt["id"]], "une SEULE main tile doit etre retranchee du cote SURROUNDING"
    assert adj != sur, "le montage ne discrimine plus les deux formes -- il ne garde plus rien"


def test_the_unit_domain_montage_is_not_vacuous():
    """LE CRAN ANTI-VIDAGE du retournement ci-dessus : sans lui, un `Target()` qui rendrait `None`
    (ou une empreinte) ferait passer les DEUX assertions precedentes sur un montage DEGENERE.

    On assertionne donc ce qui les rend discriminantes : `Target()` enumere UNE entite quand
    `TargetTile()` en enumere TROIS, et les pieds sont voisins entre eux (sans quoi l'origine ne
    pourrait de toute facon pas se selectionner elle-meme)."""
    tgt = _multi()
    board = _flat_board()
    ctx = _ctx(board, [tgt], target=tgt)
    assert TargetTile().evaluate(ctx) == FEET and len(FEET) == 3
    cible = Target().evaluate(ctx)
    assert isinstance(cible, dict) and cible["id"] == tgt["id"], (
        "`Target()` doit rendre UNE entite-unite -- sinon les deux formes ne peuvent pas diverger")
    assert board.id_at(*FEET[1]) in board.neighbours_native(board.id_at(*FEET[0]))


def test_both_exclusions_coincide_on_a_mono_hex_origin():
    """Reciproque de la reciproque : hors multi-hex les deux formes rendent le MEME ensemble --
    c'est ce qui rendait l'ecart invisible."""
    origin = _mono(uid=4, team=1, pos=(5, 5))
    others = [_mono(uid=5, team=2, pos=(5, 6)), _mono(uid=6, team=2, pos=(6, 5))]
    board, units = _flat_board(), [origin] + others
    adj = _within(units, origin, 1, board=board, order="adjacent")
    sur = _within(units, origin, 1, board=board, order="surrounding")
    assert {u["id"] for u in adj} == {u["id"] for u in sur} == {5, 6}


def test_adjacent_tiles_node_drops_the_origin_footprint():
    """`AdjacentTilesSelector$$Select` : `if (!tiles.Contains(a))`. Sur une origine multi-hex les
    pieds sont voisins entre eux -> ils sortent de l'anneau."""
    tgt = _multi()
    board = _flat_board()
    ids = AdjacentTiles(TargetTile()).evaluate(_ctx(board, [tgt], target=tgt))
    foot_ids = {board.id_at(*f) for f in FEET}
    assert foot_ids and not (set(ids) & foot_ids)
    # ... et l'anneau EST bien l'union des voisinages des trois pieds
    union = set()
    for f in FEET:
        union |= set(board.neighbours_native(board.id_at(*f)))
    assert set(ids) == union - foot_ids


def test_adjacent_tiles_exclusion_is_inert_on_a_mono_hex_origin():
    """Reciproque : une tuile n'est jamais dans son propre voisinage -> l'exclusion ne retire rien."""
    u = _mono(uid=7, team=1, pos=(5, 5))
    board = _flat_board()
    ids = AdjacentTiles(CasterTile()).evaluate(_ctx(board, [u], caster=u))
    assert set(ids) == set(board.neighbours_native(board.id_at(5, 5)))


# ------------------------------------------------------------- ITEM 2 : UNE seule vue du voisinage

def _asymmetric_board() -> Board:
    """Board a UNE arete dirigee : (1,1) -> (1,2) est stockee, la reciproque ne l'est PAS.
    C'est la forme reelle du `ConnectivityComponent` d'un board capte (~18 aretes one-way
    observees) -- et exactement ce que le mode `native_sym` de `Board.neighbours()` masque."""
    idof, tid = {}, 1
    for c in range(4):
        for r in range(4):
            idof[(c, r)] = tid
            tid += 1
    tiles = []
    for (c, r), i in idof.items():
        nb = [idof[n] for n in hexgeo.neighbors(c, r) if n in idof]
        if (c, r) == (1, 2):
            nb = [x for x in nb if x != idof[(1, 1)]]        # arete inverse ABSENTE du stockage
        tiles.append({"id": i, "col": c, "row": r, "elevation": 0, "tileDefId": "Grass",
                      "isTemporary": False, "isWall": False, "walkable": True,
                      "occupantUnitId": None, "neighbours": nb})
    return Board(tiles, adjacency="native_sym")


def test_the_asymmetric_montage_is_discriminant():
    b = _asymmetric_board()
    a, c = b.id_at(1, 1), b.id_at(1, 2)
    assert c in b.neighbours_native(a) and a not in b.neighbours_native(c)
    assert c in b.neighbours(a) and a in b.neighbours(c), "la vue symetrisee gomme l'ecart"


def test_is_adjacent_reads_the_stored_view():
    """`MovementQuery$$IsAdjacent` = `GetAdjacentTiles(a, 0, 1, 1).Contains(b)`, et
    `TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext` enumere le `ConnectivityComponent`.
    Le port lisait `board.neighbours()` (symetrise) -> il rendait VRAI dans les deux sens."""
    b = _asymmetric_board()
    assert MQ.is_adjacent(b, (1, 1), (1, 2)) is True
    assert MQ.is_adjacent(b, (1, 2), (1, 1)) is False


def test_is_adjacent_and_the_seven_feet_branch_share_one_focus():
    """Les deux mirrorent le MEME appel : ils doivent passer par `adjacent_tile_ids`. On le prouve
    en MUTANT le foyer -- les deux verdicts bougent ensemble."""
    b = _asymmetric_board()
    orig = MQ.adjacent_tile_ids
    try:
        MQ.adjacent_tile_ids = lambda board, tile: []       # noqa: E731
        assert MQ.is_adjacent(b, (1, 1), (1, 2)) is False
        assert MQ.get_possible_tile_lists_from_movable_tiles(
            b, [(c, r) for c in range(4) for r in range(4)], 7) == []
    finally:
        MQ.adjacent_tile_ids = orig
    assert MQ.is_adjacent(b, (1, 1), (1, 2)) is True         # le revert a bien mordu


def test_seven_feet_branch_uses_the_stored_view():
    """La branche 7 batit `{centre} + GetAdjacentTiles(centre)` : sur la tuile dont une arete
    inverse manque, l'anneau est PLUS PETIT que la couronne symetrisee."""
    b = _asymmetric_board()
    pool = [(c, r) for c in range(4) for r in range(4)]
    combos = MQ.get_possible_tile_lists_from_movable_tiles(b, pool, 7)
    by_center = {c[0]: c[1:] for c in combos}
    assert (1, 2) in by_center[(1, 1)], "l'arete stockee (1,1)->(1,2) doit etre dans l'anneau"
    assert (1, 1) not in by_center[(1, 2)], "l'arete inverse n'est PAS stockee"
    assert len(by_center[(1, 2)]) == len(by_center[(1, 1)]) - 1


def test_adjacent_tile_ids_is_ordered_like_the_stored_list():
    """L'ORDRE compte (`OrderedSet` d'insertion, consomme par `PickRandomly`/`First`/tris stables) :
    le foyer rend la liste BRUTE, pas les ids tries de `neighbours()`."""
    b = _asymmetric_board()
    assert MQ.adjacent_tile_ids(b, (1, 1)) == b.neighbours_native(b.id_at(1, 1))
    assert MQ.adjacent_tile_ids(b, None) == [] and MQ.adjacent_tile_ids(None, (1, 1)) == []
