"""GARDE #120bis-spawn (OFFLINE PURE) -- `SwornProtectorAbility$$GetSpawnTile` : le TRI de la
tuile de spawn de Kell, et l'ORDINAL qui a failli etre recopie faux.

CE QU'ELLE PROTEGE. Le port collapsait `First(SortTilesByUtilityForSummon(...), 1)` en
`First(CanAddUnit(AdjacentTiles(Caster())))` -- la premiere tuile libre dans l'ordre
`board.neighbours`. Quatre choses peuvent regresser, dont deux sont des PIEGES qu'on a
effectivement failli prendre :

  1. **LA DEFINITION EST UN BUCKET A DEUX TERMES**, batie a la main :
     `UtilityDefinition( UtilityBucket([ WeightedUtility(7 = Tile), WeightedUtility(52 =
     SwornProtector_AvoidAdjacentEnemies) ]) )`. La surcharge SCALAIRE `UtilityDefinition(7)` ne
     peut pas l'exprimer, et un retour a elle re-collapserait le tri sans rien casser d'autre.
  2. ⚠ **L'ORDINAL EST 52, ET 51 EST UN HOMONYME QUASI PARFAIT.** `docs/rl/case-120bis-...` cite
     `WeightedUtility(0x33)` -- ecrit sur `gqfc5mff6c`, ou `AttackTile` n'existait pas encore en 8 ;
     son insertion a decale de +1 les 73 membres suivants d'`IdunBattle.Configuration.UtilityType`.
     `0x33 = 51` designe aujourd'hui **`RoyalGuard_AvoidAdjacentEnemies`**, qui porte la MEME cle
     BC (`AdjacentEnemy`) et la MEME valeur (**-20**) : une recopie de l'ordinal aurait produit un
     tri d'apparence juste, avec la mauvaise feuille. Ce fichier fige l'ordinal MESURE a la
     conversion -- `probe_313` ne le verrait pas (il compare le mirror au build, et redevient vert
     des qu'on regenere le mirror apres un renumerotage).
  3. **LA FEUILLE NE DEGRADE PAS EN REGIME SPAWN.** Elle lit `UtilityMovementCase.get_UnitOrParent`
     (= `unit ?? parent`), donc le PARENT quand `case.unit` est nul. Son jumeau
     `RammingSpeed_MostAdjacentEnemies` lit `case.unit` et rend 0 sous `is_spawning` : recopier sa
     garde ici rendrait la feuille INERTE sur son UNIQUE call-site, c'est-a-dire restaurerait
     exactement le collapse qu'elle repare -- et aucun test de presence ne le verrait.
  4. **LE SIGNE DU POIDS.** `Utilities.Default.SwornProtector_AvoidAdjacentEnemies.AdjacentEnemy`
     vaut **-20**. Positif, le tri poserait Kell **du cote de l'attaquant**, soit l'inverse exact
     du natif.

Confront LIVE (accord `d(att, creed)` 3/3 contre 0/3 pour l'arbre temoin `origin/master`) :
`python scripts/python/probe_120bis_spawn_tile.py`.
RE : `docs/rl/case-120bis-flailswing-haze-confound.md` Sec.8. ASCII only. Aucune VA en dur.
"""
from __future__ import annotations

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        # SOCLE COMMUN a TOUT fichier de test : la cascade des `conftest.py` et sa fermeture.
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/tests/engine/runner/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        "scripts/python/catalog_inject.py",
        "scripts/python/gameconfig.py", "scripts/python/enum_maps.py",
        "scripts/python/host_inputs.py", "scripts/python/rl_collect_batch.py",
        "scripts/python/stream_events.py", "scripts/python/symbols_layout.py",
        "scripts/python/engine/runner/snapshot.py",
        # PROPRE A CE FICHIER, perimetre pris LARGE : le foyer de tri tire toutes les feuilles
        # d'utilite, et le trigger tire le registre complet. Foyers load-bearing pour la
        # relecture : `engine/utilities/sworn_protector.py` (la feuille + son inscription),
        # `engine/utilities/tile.py` (le foyer de tri et `UTILITY_BY_TYPE`),
        # `engine/utilities/utility_type.py` (le mirror d'enum),
        # `operations/triggers/loki/sworn_protector.py` (la definition et l'arbre),
        # `entities/selectors/tiles.py` (le noeud `SortTilesByUtility`).
        # ⚠ Les DEUX formes de glob sont necessaires : dans ce matcher `**/` exige un segment.
        "scripts/python/engine/*.py",
        "scripts/python/engine/**/*.py",
        # Le poids `AdjacentEnemy` est une DONNEE de BC, et les ordinaux d'`UtilityType` viennent
        # du dump du build.
        "data/seed-bc.json",
        "data/symbols/**",
    ),
    "build": True,
    "toujours": False,
    "raison": "Verdicts figes : la definition BATIE A LA MAIN (bucket a deux termes, pas la "
              "surcharge scalaire), l'ORDINAL 52 mesure a la conversion et la DISTINCTION d'avec "
              "l'homonyme 51 `RoyalGuard_AvoidAdjacentEnemies` (meme cle BC, meme valeur), "
              "l'inscription au registre `UTILITY_BY_TYPE`, le SIGNE negatif du poids, la "
              "NON-degradation de la feuille en regime spawn, et l'ordre que le tri produit sur "
              "un board synthetique. Aucun runner, aucune session Frida.",
}

import pytest

from engine.utilities.utility_type import UtilityType

#: L'ordinal MESURE a la conversion (build `rnca9r7q6c`). Il est ECRIT ICI, en clair, parce que
#: c'est la seule chose qu'un mirror regenere ne peut pas rattraper toute seule.
ORDINAL_MESURE_SWORN_PROTECTOR = 52
ORDINAL_MESURE_ROYAL_GUARD = 51        # l'HOMONYME, ce que la fiche citait par erreur (`0x33`)
POIDS_ATTENDU = -20


# --------------------------------------------------------------------------------------------
# 1. L'ORDINAL, ET SON HOMONYME
# --------------------------------------------------------------------------------------------

def test_lordinal_de_la_feuille_est_celui_MESURE_a_la_conversion():
    """Si le build renumerote, ce test rougit et la conversion doit etre RE-MESUREE -- on ne
    regenere pas le mirror en silence."""
    assert int(UtilityType.SwornProtector_AvoidAdjacentEnemies) == ORDINAL_MESURE_SWORN_PROTECTOR


def test_lhomonyme_51_existe_et_nest_PAS_la_meme_feuille():
    """⚠ LE PIEGE. `0x33 = 51` = `RoyalGuard_AvoidAdjacentEnemies` : meme suffixe de nom, meme cle
    BC `AdjacentEnemy`, meme valeur -20. Recopier l'ordinal de la fiche aurait donne un tri
    d'apparence juste avec la MAUVAISE feuille. Les deux membres doivent exister et differer."""
    assert int(UtilityType.RoyalGuard_AvoidAdjacentEnemies) == ORDINAL_MESURE_ROYAL_GUARD
    assert UtilityType.RoyalGuard_AvoidAdjacentEnemies != \
        UtilityType.SwornProtector_AvoidAdjacentEnemies


def test_le_port_ecrit_le_MEMBRE_jamais_lordinal():
    """La regle << un entier qui DESIGNE passe par un ENUM >> : le module de la feuille et celui
    de la definition ne doivent contenir AUCUN littéral 52/0x34 en position d'utility-type."""
    import inspect
    import engine.utilities.sworn_protector as F
    import engine.runner.operations.triggers.loki.sworn_protector as SP
    for mod in (F, SP):
        src = inspect.getsource(mod)
        for ligne in src.splitlines():
            nu = ligne.split("#")[0]
            assert "utility_type=52" not in nu and "utility_type=0x34" not in nu, ligne
            assert "UTILITY_BY_TYPE[52]" not in nu, ligne


# --------------------------------------------------------------------------------------------
# 2. LA DEFINITION -- un bucket a DEUX termes, pas la surcharge scalaire
# --------------------------------------------------------------------------------------------

def test_la_definition_porte_les_DEUX_termes_dans_UN_bucket():
    from engine.runner.operations.triggers.loki.sworn_protector import (
        SWORN_PROTECTOR_SPAWN_TILE_UTILITY as D)
    types = [int(w.utility_type) for w in D.bucket.utilities]
    assert types == [int(UtilityType.Tile),
                     int(UtilityType.SwornProtector_AvoidAdjacentEnemies)], \
        "l'ORDRE des deux termes est celui des deux `WeightedUtility$$.ctor` successifs"
    assert all(getattr(w, "weight", None) in (None, 1) for w in D.bucket.utilities), \
        "les deux ctors passent un `Nullable<Fix64>` VIDE -> poids 1"


def test_larbre_de_spawn_passe_la_definition_et_le_PARENT():
    """`SortTilesByUtilityForSummon(tiles, definition, owner)` = `dc.unit == null` et
    `dc.parent == owner`. Un `unit_sel` non nul basculerait le foyer hors du regime SPAWN."""
    from engine.entities.selectors.tiles import SortTilesByUtility
    from engine.runner.operations.triggers.loki.sworn_protector import (
        sworn_protector_spawn_tree, SWORN_PROTECTOR_SPAWN_TILE_UTILITY)
    tri = sworn_protector_spawn_tree().tile_selector.source        # `First(<le tri>)`
    assert isinstance(tri, SortTilesByUtility)
    assert tri.utility_definition is SWORN_PROTECTOR_SPAWN_TILE_UTILITY
    assert tri.unit_sel is None, "`dc.unit` doit rester NUL (regime SPAWN)"
    assert tri.parent_sel is not None, "`dc.parent` doit etre l'owner"


def test_la_feuille_est_INSCRITE_au_registre_des_utilites():
    """`utilities_database(52)` doit rendre l'instance : `UtilityDecider.CalculateUtility` LEVE sur
    un type non porte plutot que de rendre 0 en silence -- donc l'absence casserait le tri, pas
    seulement sa qualite."""
    from engine.utilities.tile import utilities_database
    from engine.utilities.sworn_protector import SwornProtector_AvoidAdjacentEnemiesUtility
    u = utilities_database(int(UtilityType.SwornProtector_AvoidAdjacentEnemies))
    assert isinstance(u, SwornProtector_AvoidAdjacentEnemiesUtility)


# --------------------------------------------------------------------------------------------
# 3. LA FEUILLE -- signe, substrat, et NON-degradation en regime spawn
# --------------------------------------------------------------------------------------------

def _wt():
    from engine.weights import load
    return load()


def test_le_poids_BC_est_NEGATIF():
    """Positif, le tri poserait Kell DU COTE de l'attaquant -- l'inverse exact du natif."""
    p = _wt().sub("SwornProtector_AvoidAdjacentEnemies", "AdjacentEnemy")
    assert p == POIDS_ATTENDU, "la cle est `AdjacentEnemy`, SANS prefixe (contraste RammingSpeed)"


def _ctx_spawn(enemies):
    """Ce que `tile._spawn_leaf_ctx` publie : camp calcule par rapport au PARENT, cartes du board."""
    return {"is_spawning": True,
            "enemy_units": [{"pos": p} for p in enemies],
            "elev_by_pos": {}, "neigh_by_pos": {}}


def test_la_feuille_MORD_en_regime_spawn_contraste_avec_RammingSpeed():
    """⚠ LE SECOND PIEGE. `get_UnitOrParent` = `unit ?? parent` : en regime spawn le sujet est le
    PARENT, donc la feuille reste ACTIVE. Son jumeau, lui, rend 0. Recopier sa garde ici rendrait
    la feuille inerte sur son UNIQUE call-site."""
    from engine.utilities.sworn_protector import SWORN_PROTECTOR_AVOID_ADJACENT_ENEMIES as F
    from engine.utilities.ramming_speed import RAMMING_SPEED_MOST_ADJACENT_ENEMIES as R
    ctx = _ctx_spawn([(2, 3)])
    v = F.evaluate((2, 2), {}, ctx, _wt())
    assert v == POIDS_ATTENDU, "un ennemi adjacent -> exactement un `AdjacentEnemy`"
    assert R.evaluate((2, 2), {}, ctx, _wt()) == 0.0, \
        "temoin : le jumeau DEGRADE bien a 0 sous `is_spawning` -- les deux ne sont pas identiques"


@pytest.mark.parametrize("ennemis,attendu", [
    ([], 0.0),
    ([(2, 3)], float(POIDS_ATTENDU)),
    ([(2, 3), (3, 2)], 2.0 * POIDS_ATTENDU),
])
def test_la_feuille_compte_les_ennemis_ADJACENTS_A_LA_TUILE_CANDIDATE(ennemis, attendu):
    """L'ancre est `case.get_MovementTile`, pas la tuile du sujet -- c'est ce qui rend la feuille
    DISCRIMINANTE d'une candidate a l'autre."""
    from engine.utilities.sworn_protector import SWORN_PROTECTOR_AVOID_ADJACENT_ENEMIES as F
    assert F.evaluate((2, 2), {}, _ctx_spawn(ennemis), _wt()) == attendu


def test_la_feuille_degrade_a_ZERO_sans_liste_dennemis():
    """Substrat non mesure -> 0.0, ce qui redonne l'ordre SOURCE : le port ne devine pas."""
    from engine.utilities.sworn_protector import SWORN_PROTECTOR_AVOID_ADJACENT_ENEMIES as F
    assert F.evaluate((2, 2), {}, {}, _wt()) == 0.0
    assert F.evaluate((2, 2), {}, None, _wt()) == 0.0
    assert F.evaluate(None, {}, _ctx_spawn([(2, 3)]), _wt()) == 0.0


# --------------------------------------------------------------------------------------------
# 4. LE TRI, DE BOUT EN BOUT
# --------------------------------------------------------------------------------------------

def test_le_tri_prefere_la_tuile_qui_MINIMISE_les_ennemis_adjacents():
    """Bout en bout par le FOYER (`sort_tiles_by_utility`), en regime SPAWN. Le board est PLAT
    (elevation constante) pour que le composite `Tile(7)` soit un facteur COMMUN : ce qui reste
    discriminant est exactement la feuille 52.

    Temoin de NON-DEGENERESCENCE : sans la feuille (definition scalaire `Tile(7)` seule), l'ordre
    doit etre celui de la SOURCE -- sinon l'accord ci-dessus ne separerait rien."""
    import hexgeo
    from engine.entities.pathfinding.board import Board
    from engine.utilities.decider import UtilityBucket, UtilityDefinition, WeightedUtility
    from engine.utilities.tile import sort_tiles_by_utility
    from engine.runner.operations.triggers.loki.sworn_protector import (
        SWORN_PROTECTOR_SPAWN_TILE_UTILITY)

    COLS = ROWS = 6
    tiles = []
    for c in range(COLS):
        for r in range(ROWS):
            tiles.append({"id": c * ROWS + r + 1, "col": c, "row": r, "walkable": True,
                          "isWall": False, "elevation": 0,
                          "neighbours": [cc * ROWS + rr + 1 for (cc, rr) in hexgeo.neighbors(c, r)
                                         if 0 <= cc < COLS and 0 <= rr < ROWS]})
    board = Board(tiles)

    class _St:
        pass

    st = _St()
    st.board = board
    st.effects = None

    creed = (2, 2)
    attaquant = (2, 3)                       # l'ennemi, au contact de Creed
    cands = [board.id_at(*p) for p in ((2, 3 - 1), (1, 2), (3, 2))]   # trois voisins libres
    # `_spawn_leaf_ctx` fourni A LA MAIN : le foyer accepte un `leaf_ctx` explicite, ce qui evite
    # de monter un `State` de runner complet pour un invariant d'ORDRE.
    leaf = {"is_spawning": True, "enemy_units": [{"pos": attaquant}],
            "elev_by_pos": {(t["col"], t["row"]): 0 for t in tiles},
            "neigh_by_pos": {(t["col"], t["row"]): [board.coord(n)
                                                    for n in board.neighbours(t["id"])]
                             for t in tiles}}
    classe = sort_tiles_by_utility(st, cands, unit_id=None, parent_id=None,
                                   utility_definition=SWORN_PROTECTOR_SPAWN_TILE_UTILITY,
                                   leaf_ctx=leaf)
    premiere = board.coord(classe[0])
    assert hexgeo.distance(premiere, attaquant) > 1, \
        "la tuile retenue doit EVITER le voisinage de l'attaquant"

    # TEMOIN : avec la seule utilite `Tile(7)`, plus rien ne departage -> ordre SOURCE intact.
    scalaire = UtilityDefinition(UtilityBucket([WeightedUtility(utility_type=int(UtilityType.Tile))]))
    plat = sort_tiles_by_utility(st, cands, unit_id=None, parent_id=None,
                                 utility_definition=scalaire, leaf_ctx=leaf)
    assert plat == cands, "board plat + Tile(7) seul -> aucun departage, l'ordre SOURCE tient"
    assert classe != plat, "la feuille 52 doit CHANGER le classement -- sinon rien n'est mesure"
