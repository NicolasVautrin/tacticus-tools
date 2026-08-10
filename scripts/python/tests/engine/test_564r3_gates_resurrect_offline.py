"""#564-r3 (offline) -- les etages de `IdunBattle.Operations.ResurrectUnitOperation$$Execute` qui
vivaient EN AVAL DU GATE et n'etaient pas portes.

POURQUOI CE FICHIER EXISTE : LES POLARITES NE SONT PAS HOMOGENES

Les quatre gates de tuile se suivent dans `Execute`, et **deux d'entre eux refusent quand ils
rendent VRAI** -- recopier la polarite au juge en aurait inverse la moitie :

    if ( TilesAreOccupied(tiles))                          return;   <- VRAI  = refus
    if (!TilesAreWalkable(unit, tiles))                    return;   <- FAUX  = refus
    if ( GetFeetCount(unit) != unitFeetTiles.Count)        return;
    if ( IsTileReservedForAnotherUnit(tiles, unit))        return;   <- VRAI  = refus

C'est la meme famille de piege que les sept gates amont de `MoveUnitOperation`
(#448-r1-r1-r2-r2-r1), et les DEUX gates de tuile sont litteralement les MEMES slots
d'`IBattleQuery` (0xa1 `IsWalkableTile`, 0xa5 `IsTileReservedForAnotherUnit`) -- d'ou la
reutilisation de leur foyer porte plutot qu'un second mirror.

CE QUI RESTE NON PORTE, ET C'EST DIT : l'empreinte MULTI-HEX. Le port n'ecrit qu'une
`PositionComponent`, la ou le natif joue `ResetPreviousTileIfStillOwned` + `ResetFeet` +
`processor.<slot 0x7e>(unit, unitFeetTiles)`. Le fermer exige que la feuille DSL `Resurrect`
transmette la LISTE de tuiles ; foyer `runner/abilities/behaviours/lifecycle.py`.

ASCII only.
"""
from __future__ import annotations

# `DECLENCHEUR` (#486-r15) -- ce qui doit changer pour que ce fichier puisse changer de verdict.
DECLENCHEUR = {
    "chemins": (
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        # L'OPERATION et les DEUX foyers de gate qu'elle REUTILISE -- si l'un des deux change de
        # polarite, c'est ici que ca doit se voir.
        "scripts/python/engine/runner/operations/resurrect.py",
        "scripts/python/engine/runner/operations/movement.py",
        "scripts/python/engine/runner/operations/tile_reservation.py",
        "scripts/python/engine/runner/operations/turnflow.py",
        "scripts/python/engine/runner/components.py",
        "scripts/python/engine/runner/abilities/attack_query.py",
        # ⚠ ELARGI : la liste ci-dessus dit OU regarder ; les deux globs disent ce qui fait
        # vraiment changer d'avis (l'Operation tire tout le paquet `runner`). Les DEUX formes
        # sont necessaires : `**/` exige un SEGMENT.
        "scripts/python/*.py", "scripts/python/**/*.py",
    ),
    "build": False,
    "toujours": False,
    "raison": "Les quatre gates de tuile de `ResurrectUnitOperation$$Execute`, leurs polarites, et "
              "`ResetPersistentData`. Aucun runner, aucun canal live -> `build: False`.",
}

import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

from engine.entities.unit_context import UnitContext                          # noqa: E402
from engine.runner.components import (HealthComponent, PersistentDataComponent,  # noqa: E402
                                      PositionComponent, StatsComponent,
                                      TriggeredAbilityComponent, UnitComponent,
                                      UnitFlagsComponent)
from engine.runner.operations.resurrect import (ResurrectUnitOperation,        # noqa: E402
                                                feet_count_matches_tiles,
                                                reset_persistent_data,
                                                tiles_are_occupied)
from engine.runner.operations.tile_reservation import reserve_for_unit         # noqa: E402
from engine.runner.state import State                                          # noqa: E402


class _Board:
    """Board minimal : une grille 4x4, toutes les tuiles marchables sauf celles d'`unwalkable`."""
    def __init__(self, unwalkable=()):
        self._u = {(int(c), int(r)) for c, r in unwalkable}
        self._ids = {}
        n = 100
        for c in range(4):
            for r in range(4):
                self._ids[(c, r)] = n
                n += 1
        self._rev = {v: k for k, v in self._ids.items()}

    def id_at(self, col, row):
        return self._ids.get((int(col), int(row)))

    def walkable(self, tid):
        p = self._rev.get(int(tid))
        return p is not None and p not in self._u

    def coord(self, tid):
        return self._rev[int(tid)]


def _unite(st, pos, alive=True, hp=0, hp_max=500, traits=()):
    e = st.add_entity()
    e.add_component(UnitComponent(visual_id="x", alive=alive))
    e.add_component(PositionComponent(col=pos[0], row=pos[1]))
    e.add_component(HealthComponent(hp=hp, hp_max=hp_max))
    e.add_component(UnitFlagsComponent())
    ctx = UnitContext(entity_id=e.id, visual_id="x")
    ctx.traits = list(traits)
    e.add_component(StatsComponent(ctx=ctx))
    return e.id


def _mort(st, pos, **kw):
    return _unite(st, pos, alive=False, hp=0, **kw)


# ---------------------------------------------------------------------------------------------
# `TilesAreOccupied` -- VRAI = REFUS
# ---------------------------------------------------------------------------------------------

def test_TilesAreOccupied_rend_VRAI_quand_une_tuile_est_prise():
    """Polarite : le natif REFUSE quand cette fonction rend VRAI. L'inverser laisserait
    ressusciter SOUS une unite vivante, et ne refuserait plus jamais rien."""
    st = State()
    st.board = _Board()
    _unite(st, (1, 1))                                   # un vivant occupe (1,1)
    assert tiles_are_occupied(st, [(1, 1)]) is True
    assert tiles_are_occupied(st, [(2, 2)]) is False


def test_un_occupant_STEPPABLE_ne_rend_PAS_la_tuile_occupee():
    """`allowSteppable: 1` est LU aux octets du call-site, et il est LOAD-BEARING : c'est ce qui
    laisse la resurrection reapparaitre SUR un decoy, que `KillSteppableUnits` ecrase juste apres.
    Avec `allowSteppable: 0`, le cas nominal de `1039`/de l'Ambush serait refuse."""
    st = State()
    st.board = _Board()
    _unite(st, (1, 1), traits=("Steppable",))
    assert tiles_are_occupied(st, [(1, 1)]) is False


def test_un_CADAVRE_n_occupe_rien():
    """`KillUnitOperation` -> `RemoveUnitFromTiles` vide le `TileContentComponent` : l'occupation
    est celle de la TUILE, jamais la vitalite de son occupant. Sans ce bras, une unite ne pourrait
    jamais ressusciter SUR SA PROPRE tuile."""
    st = State()
    st.board = _Board()
    _mort(st, (1, 1))
    assert tiles_are_occupied(st, [(1, 1)]) is False


def test_sans_board_le_gate_est_PERMISSIF():
    """Meme parti que `_tiles_are_walkable` : on ne refuse pas une resurrection faute de substrat."""
    st = State()
    _unite(st, (1, 1))
    assert tiles_are_occupied(st, [(1, 1)]) is False


# ---------------------------------------------------------------------------------------------
# `GetFeetCount(unit) != tiles.Count`
# ---------------------------------------------------------------------------------------------

def test_le_compte_de_pieds_PASSE_sur_un_mono_hex_mort():
    """Le gate le plus dangereux a porter : un cadavre GARDE ses pieds (c'est `ResetFeet`, APRES ce
    gate, qui detache leur `TileId`), donc `1 != 1` est faux et la resurrection continue. S'il
    refusait ici, AUCUNE resurrection ne passerait plus."""
    st = State()
    st.board = _Board()
    uid = _mort(st, (0, 0))
    assert feet_count_matches_tiles(st, uid, [(1, 1)]) is True
    assert feet_count_matches_tiles(st, uid, [(1, 1), (2, 2)]) is False


# ---------------------------------------------------------------------------------------------
# Le pipeline complet : chaque gate REFUSE, et le cas nominal PASSE
# ---------------------------------------------------------------------------------------------

def _banc(unwalkable=()):
    st = State()
    st.board = _Board(unwalkable)
    mort = _mort(st, (0, 0))
    return st, mort


def test_le_cas_NOMINAL_passe_les_quatre_gates():
    """Le contre-modele de tous les crans de refus ci-dessous : sans lui, un port qui refuserait
    TOUT serait vert sur eux."""
    st, mort = _banc()
    r = ResurrectUnitOperation.execute(st, mort, (1, 1), 400, immediate_turn=False)
    assert r is not None, "le cas nominal est refuse -- un gate mord a tort"
    assert r["tile_gates"] == {"tiles_occupied": False, "tiles_walkable": True,
                               "feet_count_ok": True, "reserved_for_another": False}, r["tile_gates"]
    assert st.get_entity(mort).get_component(UnitComponent).alive is True


def test_une_tuile_OCCUPEE_refuse_la_resurrection():
    st, mort = _banc()
    _unite(st, (1, 1))                                   # un vivant y est deja
    assert ResurrectUnitOperation.execute(st, mort, (1, 1), 400, immediate_turn=False) is None
    assert st.get_entity(mort).get_component(UnitComponent).alive is False, (
        "l'unite est revenue a la vie malgre le refus -- la mutation a eu lieu avant le gate")


def test_une_tuile_NON_WALKABLE_refuse_la_resurrection():
    st, mort = _banc(unwalkable=[(1, 1)])
    assert ResurrectUnitOperation.execute(st, mort, (1, 1), 400, immediate_turn=False) is None
    assert st.get_entity(mort).get_component(UnitComponent).alive is False


def test_une_tuile_RESERVEE_PAR_UN_AUTRE_refuse_la_resurrection():
    """`BattleQuery$$IsTileReservedForAnotherUnit` = `IsTileReserved && !IsTileReservedForUnit`.
    ⚠ Il ne faut PAS le confondre avec son homonyme `TileExtensions$$IsTileReservedForOtherUnit`,
    de polarite OPPOSEE sur une tuile NON reservee (#448-r1-r1-r2-r2-r1 SS3.1)."""
    st, mort = _banc()
    autre = _unite(st, (3, 3))
    reserve_for_unit(st, (1, 1), autre)
    assert ResurrectUnitOperation.execute(st, mort, (1, 1), 400, immediate_turn=False) is None
    assert st.get_entity(mort).get_component(UnitComponent).alive is False


def test_une_tuile_reservee_par_SOI_MEME_ne_refuse_PAS():
    """Le bras `!IsTileReservedForUnit(tile, unit)` : une reservation POSEE POUR l'unite qui
    ressuscite ne la bloque pas. Sans ce bras, l'agregateur refuserait toute tuile reservee, y
    compris celles reservees a son intention."""
    st, mort = _banc()
    reserve_for_unit(st, (1, 1), mort)
    r = ResurrectUnitOperation.execute(st, mort, (1, 1), 400, immediate_turn=False)
    assert r is not None and r["tile_gates"]["reserved_for_another"] is False


def test_dest_coord_None_rend_les_gates_NON_APPLICABLES():
    """`None` n'est PAS une empreinte VIDE (meme distinction que le `()` vs `None` du lift-off de
    `MoveUnitOperation`). Aucun call-site NATIF ne passe une empreinte vide ; `None` est un regime
    propre au port, ou il n'y a aucune tuile a valider. Armer les gates y ferait refuser TOUTE
    resurrection par `GetFeetCount(unit) != 0` -- ce qui inventerait un refus que le natif n'a
    pas, et casserait les bancs qui ne mesurent que les PV."""
    st, mort = _banc()
    r = ResurrectUnitOperation.execute(st, mort, None, 400, immediate_turn=False)
    assert r is not None, "une resurrection SANS tuile a ete refusee par les gates de tuile"
    assert r["tile_gates"] is None, r["tile_gates"]


# ---------------------------------------------------------------------------------------------
# `ResetPersistentData` -- les DEUX composants
# ---------------------------------------------------------------------------------------------

def test_la_resurrection_PURGE_les_deux_sacs_persistants():
    """`ResurrectUnitOperation$$ResetPersistentData` appelle `ClearAllPersistentData` sur DEUX
    composants distincts : le `PersistentDataComponent` (le sac de donnees) ET le
    `TriggeredAbilityComponent` (les compteurs de phase-triggers). N'en purger qu'un laisserait
    l'unite revenir avec un compteur de declenchements a son plafond, ou un flag intra-attaque
    encore arme."""
    st, mort = _banc()
    e = st.get_entity(mort)
    pdc = e.add_component(PersistentDataComponent())
    pdc.data[("LetTheGalaxyBurn", "fired")] = 1
    tac = e.add_component(TriggeredAbilityComponent())
    tac.try_add("une-cle")
    assert pdc.data and tac.entries

    r = ResurrectUnitOperation.execute(st, mort, (1, 1), 400, immediate_turn=False)
    assert r is not None
    assert not pdc.data, "le sac de donnees persistantes a survecu a la resurrection"
    assert not tac.entries, "les compteurs de phase-triggers ont survecu a la resurrection"
    assert r["persistent_cleared"] == 2, r["persistent_cleared"]


def test_reset_persistent_data_est_un_no_op_sans_composant():
    """0 = « rien a effacer », pas une erreur : la plupart des unites n'ont ni sac ni compteur."""
    st, mort = _banc()
    assert reset_persistent_data(st, mort) == 0
    assert reset_persistent_data(st, 999999) == 0
