"""#381-r4 -- les collapses IMPERATIFS de `MovableTilesInRange` portent le gate d'expansion #131.

CE QUE CES GARDES VERROUILLENT
-----------------------------
Trois call-sites collapsent le noeud `IdunBattleLogic.Entities.DSLSelectors$$MovableTilesInRange`
en appel direct au pathfinder. Le noeud DSL homonyme porte, depuis `#381-r1`, le gate d'expansion
`IdunBattle.Entities.Pathfinding.BasePathfinder$$NodesInNextLevel` ->
`WalkPathfinder$$IsValidContinuePathTile` (#131) et le dispatch
`IdunBattle.Core.Services.MovementQuery$$GetPathfinderTypeForUnit` ->
`UnitExtensions$$IsLikeFlying` ; les collapses, eux, ne les portaient PAS.

Les deux qui les portent desormais passent par le FOYER `services/movement_query
.get_movable_tiles_for` (mirror `MovementQuery$$GetMovableTilesFor`) :

  * `abilities/genestealer._charge_candidate_tiles` (`HeroicFusilladeAbility$$ExecuteBehaviour`,
    `VigilanceEternalAbility$$GetPossibleMovementTiles`) ;
  * `operations/triggers/loki/betrayer._betrayer_stop_tile`
    (`TheBetrayer_TakeTurnAbility$$CreateBehaviour`).

Le TROISIEME, `operations/triggers/genestealer._hypersensory_move_dest`, ne l'appelle PAS : sa
portee est 1, et a portee 1 le gate n'est JAMAIS consulte (`NodesInNextLevel` teste
`currentTile != startTile` avant `IsValidContinuePathTile`, or la seule tuile qui s'etend au seul
niveau parcouru EST le start). Le dernier test verrouille cette PREMISSE, pas un comportement :
si la portee cessait de valoir 1, l'inertie tomberait et le collapse devrait rejoindre le foyer.

Chaque garde est AUTO-DISCRIMINANTE : elle exige que la variante NON gatee DIFFERE, sinon la
geometrie ne prouve rien et le test ECHOUE (jamais un vert vide).

100 % OFFLINE : board hex synthetique, aucun runner, aucune session. ASCII only.
"""
from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[3]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import hexgeo  # noqa: E402

COLS, ROWS = 7, 7
SWAMP_COL = 1                       # le COULOIR : toute la colonne 1 est block-entering
CASTER_POS = (0, 3)
CASTER_ID, TARGET_ID = 10, 20
CHARGE_RANGE = 2                    # `HeroicFusillade`/`VigilanceEternal` : GetNumberConstant = 2


def _tid(col: int, row: int) -> int:
    return col * ROWS + row + 1


def _tiles() -> list:
    """Board 7x7 PLAT, tout marchable ; la colonne `SWAMP_COL` est en `Swamp`.

    `Swamp` est le tile-def qui heberge `IdunBattleLogic.Entities.Abilities.Tiles
    .ThornsBlockMovementAbility` (elle pose `BlockEnteringUnitsTileEffect` AU SETUP) -- c'est la
    source du repli TERRAIN de `pathfinding/tile_blocking.terrain_blocks_entering`, seul canal
    disponible sur un etat monte sans `tiles=tileMeta`."""
    out = []
    for col in range(COLS):
        for row in range(ROWS):
            nb = [_tid(c, r) for (c, r) in hexgeo.neighbors(col, row)
                  if 0 <= c < COLS and 0 <= r < ROWS]
            out.append({"id": _tid(col, row), "col": col, "row": row, "elevation": 0,
                        "walkable": True, "isWall": False, "neighbours": nb,
                        "tileDefId": "Swamp" if col == SWAMP_COL else "Grass"})
    return out


def _build(caster_vis: str, caster_pos, target_pos):
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    board = Board(_tiles(), adjacency="evenq")
    units = [{"id": CASTER_ID, "visualId": caster_vis, "alive": True, "team": 1, "owner": 1,
              "pos": {"col": caster_pos[0], "row": caster_pos[1]}, "effects": []},
             {"id": TARGET_ID, "visualId": "necroWarden", "alive": True, "team": 2, "owner": 2,
              "pos": {"col": target_pos[0], "row": target_pos[1]}, "effects": []}]
    dv = {"currentPlayer": 1, "units": units}
    ob = {"units": [{"squadId": u["id"], "hp": 100000, "hpMax": 100000} for u in units]}
    return load_state(dv, ob, board=board), board


@contextmanager
def _no_gate():
    """L'etat d'AVANT `#381-r4` : le gate d'expansion #131 desarme.

    ⚠ HISTORIQUE DU SITE D'INJECTION, PARCE QU'IL A CHANGE DEUX FOIS (#484, puis #10031).
    A l'origine de `#381-r4` le foyer `engine/services/movement_query.py` resolvait
    `make_can_continue` a CHAQUE appel (import fonction-local, forme C) : patcher la SOURCE
    suffisait. `492c722f` (« hisser 624 imports differes d'engine/ au niveau module ») l'a passe en
    FORME A -- le nom y devenait lie AU CHARGEMENT, le patch sur `tile_blocking` ne l'atteignait
    plus, et les assertions AUTO-DISCRIMINANTES de ce fichier ont mordu, comme prevu. La reponse
    d'alors fut de patcher AUSSI le consommateur (`MQ.make_can_continue`) : un contournement AU SITE
    DE MESURE, qui a reverdi CE fichier et laisse DEUX instruments muets -- le pendant LIVE
    (`test_381r4_imperative_collapses_live.py`, rouge sur `aucune geometrie [...] le test ne
    prouverait rien`) et `probe_381r4_imperative_collapses.py` (`rc 1`, `0 sortie changee`), aucun
    des deux n'etant joue par un cliquet.

    `#10031` repare le FOYER au lieu du site de mesure : `movement_query` est repasse en FORME B
    (liaison de MODULE, resolue a l'appel), donc patcher la SOURCE suffit de nouveau -- et
    `MQ.make_can_continue` n'existe plus, ce qui a fait rougir ce fichier au moment de la
    reparation. Mesure : `no-gate` 0 -> 483 sorties changees sur C2_26.

    La contre-epreuve de morsure reste EXPLICITE, mais elle ne nomme plus l'alias prive du foyer :
    elle passe par `morsure_substitution.liaisons_figees`, qui DERIVE des modules CHARGES ceux qui
    ont fige ce symbole.

    ⚠ Elle est BORNEE AU FOYER QUE CE FICHIER EXERCE (`engine.services.movement_query`), et c'est
    une correction MESUREE : sans la borne, elle rougit sur `engine.ai.state_bridge`, qui fige bien
    `make_can_continue` en forme A mais que les trois tests d'ici ne traversent PAS -- une garde
    locale qui accuse un chemin non exerce est un faux rouge, et un faux rouge se fait desarmer. La
    vue LARGE (tout `engine/**`, y compris ce que rien ne charge) est le role du cliquet
    `tests/engine/services/test_10031_morsure_des_mutations_offline.py`, ou les deux liaisons
    figees hors chemin sont ATTESTEES et nommees."""
    from engine.entities.pathfinding import tile_blocking as TB
    from morsure_substitution import liaisons_figees
    saved = TB.make_can_continue
    TB.make_can_continue = lambda *a, **k: None
    try:
        figees = liaisons_figees("engine.entities.pathfinding.tile_blocking", "make_can_continue",
                                 saved, consommateurs_seuls=True,
                                 prefixe="engine.services.movement_query")
        assert not figees, ("le desarmement du gate ne mord pas : %s a(ont) fige `make_can_continue` "
                            "en forme A (cf. #484, #10031)" % sorted(figees))
        yield
    finally:
        TB.make_can_continue = saved


#: CHARGE -- cible de colonne 2 : son ring-1 porte des tuiles de colonne >= 2, que le port
#: n'atteignait qu'en TRAVERSANT un Swamp. C'est l'intersection `CanAddUnit(SurroundingTiles)`
#: qui rend l'ecart observable sur le pool.
TARGET_CHARGE = (2, 3)
#: BETRAYER -- cible HORS de toute portee : la branche `Otherwise(movable)` s'applique, et le tri
#: `MinPathLength` designe la tuile la plus proche de la cible. Avec une cible adjacente au
#: couloir, les deux bras choisiraient le MEME Swamp (qui reste un STOP legal) et le test ne
#: verrouillerait rien -- c'est mesure, cf. l'assertion auto-discriminante.
TARGET_BETRAYER = (4, 3)


# --------------------------------------------------------------------------------------------- #
# 1. `_charge_candidate_tiles` (HeroicFusillade + VigilanceEternal)
# --------------------------------------------------------------------------------------------- #
def test_le_pool_de_charge_ne_traverse_plus_le_couloir_de_swamp():
    """`HeroicFusilladeAbility$$ExecuteBehaviour` / `VigilanceEternalAbility$$
    GetPossibleMovementTiles` : le pool est `CanAddUnit(SurroundingTiles(target)) op_And
    MovableTilesInRange(caster, ...)`. Une tuile qui ne pend que d'un Swamp n'est PAS atteignable
    (le Swamp est un CUL-DE-SAC), donc elle sort du pool."""
    from engine.runner.abilities.genestealer import SURROUND_RADIUS, _charge_candidate_tiles
    tpos = TARGET_CHARGE
    state, board = _build("genesKelermorph", CASTER_POS, tpos)

    gated = {board.coord(t) for t in _charge_candidate_tiles(
        state, CASTER_ID, TARGET_ID, SURROUND_RADIUS, CHARGE_RANGE)}
    with _no_gate():
        raw = {board.coord(t) for t in _charge_candidate_tiles(
            state, CASTER_ID, TARGET_ID, SURROUND_RADIUS, CHARGE_RANGE)}

    # AUTO-DISCRIMINANT : sans le gate, le port atteignait bien au-dela du couloir.
    assert any(c >= 2 for (c, _r) in raw), sorted(raw)
    assert gated < raw, ("le gate #131 ne retire RIEN de ce pool -- la geometrie ne prouve rien "
                         "(gated=%s raw=%s)" % (sorted(gated), sorted(raw)))
    assert not any(c >= 2 for (c, _r) in gated), sorted(gated)


def test_la_destination_de_charge_change_quand_le_gate_mord():
    """Le pool n'est pas la sortie observable : c'est la TUILE d'atterrissage
    (`First(SortTilesByUtility(...))`). Les deux tris -- `Tile(7)` pour HeroicFusillade,
    `MovementSuggestion(0x20)` pour VigilanceEternal -- doivent changer avec le pool."""
    from engine.runner.abilities.genestealer import (SURROUND_RADIUS, _hf_move_dest_tile,
                                                     _vigilance_move_dest_tile)
    tpos = TARGET_CHARGE
    state, _board = _build("genesKelermorph", CASTER_POS, tpos)

    hf = _hf_move_dest_tile(state, CASTER_ID, TARGET_ID, SURROUND_RADIUS, CHARGE_RANGE)
    vig = _vigilance_move_dest_tile(state, CASTER_ID, TARGET_ID, CHARGE_RANGE)
    with _no_gate():
        hf_raw = _hf_move_dest_tile(state, CASTER_ID, TARGET_ID, SURROUND_RADIUS, CHARGE_RANGE)
        vig_raw = _vigilance_move_dest_tile(state, CASTER_ID, TARGET_ID, CHARGE_RANGE)

    assert hf != hf_raw, ("la destination HeroicFusillade est la MEME avec et sans gate -- ce test "
                          "ne verrouille rien (%s)" % (hf,))
    assert vig != vig_raw, ("la destination VigilanceEternal est la MEME avec et sans gate (%s)"
                            % (vig,))
    for name, dest in (("HeroicFusillade", hf), ("VigilanceEternal", vig)):
        assert dest is None or dest[0] <= SWAMP_COL, \
            "%s atterrit au-dela du couloir de Swamp : %s" % (name, dest)


# --------------------------------------------------------------------------------------------- #
# 2. `_betrayer_stop_tile` (TheBetrayer_TakeTurnAbility)
# --------------------------------------------------------------------------------------------- #
def test_la_tuile_d_arret_de_thebetrayer_ne_traverse_plus_le_couloir():
    """`TheBetrayer_TakeTurnAbility$$CreateBehaviour` : `First(SortByFormula(SortTilesByUtility(
    (AdjacentTiles(target) & movable).Otherwise(movable)), MinPathLength))`. Le `movable` est le
    meme pathfinding, donc le meme gate."""
    from engine.runner.operations.triggers.loki.betrayer import _betrayer_stop_tile
    tpos = TARGET_BETRAYER
    state, _board = _build("worldKharn", CASTER_POS, tpos)

    gated = _betrayer_stop_tile(state, CASTER_ID, TARGET_ID)
    with _no_gate():
        raw = _betrayer_stop_tile(state, CASTER_ID, TARGET_ID)

    assert gated != raw, ("la tuile d'arret est la MEME avec et sans gate -- ce test ne "
                          "verrouille rien (%s)" % (gated,))
    assert raw is not None and raw[0] >= 2, ("sans le gate, TheBetrayer s'arretait au-dela du "
                                             "couloir : c'est ce qu'on verrouille (%s)" % (raw,))
    assert gated is None or gated[0] <= SWAMP_COL, \
        "TheBetrayer s'arrete au-dela du couloir de Swamp : %s" % (gated,)


# --------------------------------------------------------------------------------------------- #
# 3. `_hypersensory_move_dest` -- NON corrige : la PREMISSE de son inertie
# --------------------------------------------------------------------------------------------- #
def test_hypersensory_reste_a_portee_1_donc_le_gate_y_est_inerte():
    """`HypersensoryAbilitiesAbility_MoveAndSpawnDecoy$$CreateBehaviour` passe a
    `MovableTilesInRange` l'`overrideRange` `DSLFormulas+0x20`, la formule partagee `Direct(1)`
    que son `.ctor` alloue (`+0x18`=0, `+0x20`=1, `+0x28`=2, `+0x30`=100, `+0x38`=-1).

    A portee 1, `BasePathfinder$$NodesInNextLevel` teste `currentTile != startTile` AVANT
    `IsValidContinuePathTile` : la seule tuile qui s'etend au seul niveau parcouru EST le start,
    donc le predicat n'est JAMAIS consulte. On le prouve par un `can_continue` SENTINELLE qui
    leve s'il est appele -- et on verifie qu'a portee 2 il l'EST (sinon la sentinelle ne prouve
    rien)."""
    from engine.entities.pathfinding.board import Board
    from engine.entities.pathfinding.walk_pathfinder import get_movable_positions
    from engine.runner.operations.triggers.genestealer import HYPERSENSORY_MOVE_RANGE

    assert HYPERSENSORY_MOVE_RANGE == 1, (
        "la portee du move Hypersensory n'est plus 1 : l'inertie du gate #131 tombe, et ce "
        "collapse doit rejoindre `services/movement_query.get_movable_tiles_for`")

    board = Board(_tiles(), adjacency="evenq")
    start = board.id_at(*CASTER_POS)
    calls: list = []

    def _sentinel(tid):
        calls.append(int(tid))
        return True

    get_movable_positions(board, start, HYPERSENSORY_MOVE_RANGE, {}, 1, can_continue=_sentinel)
    assert calls == [], ("le gate a ete consulte a portee 1 : la lecture de "
                         "`NodesInNextLevel` est fausse (%s)" % calls)
    get_movable_positions(board, start, 2, {}, 1, can_continue=_sentinel)
    assert calls, "le gate n'est pas consulte non plus a portee 2 -- la sentinelle ne prouve rien"


if __name__ == "__main__":                       # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
