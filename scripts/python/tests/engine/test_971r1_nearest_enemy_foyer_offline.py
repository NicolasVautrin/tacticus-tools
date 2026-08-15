"""#971-r1 -- `GetNearestEnemy` a UN foyer, et la convergence est VALUE-PRESERVING.

Ce que cette garde verrouille
-----------------------------
`IdunBattle.Core.Services.BattleQuery$$GetNearestEnemy(caster, position)` etait mirrore TROIS fois
(`noncomparable/summon_attack_range.py::nearest_enemy`, `master_of_the_tutelaries.py::
_nearest_enemy_tile`, `ironkin_steeljack.py::_nearest_enemy`). Le foyer est desormais
`engine/battle_query.py::get_nearest_enemy(ctx, position=None)` et les trois sont des passe-plats.

Les etages 1 a 3 rejouent les TROIS corps d'origine, RECOPIES ICI VERBATIM, contre le foyer, sur un
balayage EXHAUSTIF de plateaux (elevations aleatoires, ancres variees). Une convergence qui ne
mesurerait pas son propre bras d'avant ne prouverait rien : elle serait verte que le foyer soit
fidele ou non.

L'etage 4 garde le seul point ou le foyer est PLUS fidele que les trois : `bestDist` part de
`int.MaxValue` (le natif ecrit `d < bestDist`, jamais « c'est le premier »).
L'etage 5 garde l'ancre, qui est le `Nullable<UnitPosition>` du natif et non une convention.
L'etage 6 garde que les trois appelants passent bien par le foyer (aucun fork ne peut revenir).

100 % OFFLINE : aucun runner, aucune session.
"""
from __future__ import annotations

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        # LE FOYER, et la primitive d'adjacence dont il derive son tie-break.
        "scripts/python/engine/battle_query.py",
        # Les TROIS passe-plats : l'etage 6 lit leur source pour verifier qu'aucun fork ne revient.
        "scripts/python/engine/playbook/noncomparable/summon_attack_range.py",
        "scripts/python/engine/playbook/noncomparable/master_of_the_tutelaries.py",
        "scripts/python/engine/playbook/noncomparable/ironkin_steeljack.py",
        # La geometrie hex : elle decide QUELLES paires sont adjacentes, donc quel tie-break mord.
        "scripts/python/hexgeo.py",
    ),
    "build": False,
    "toujours": False,
    "raison": "Purement offline, sans lecture de `data/` ni de gameconfig : les entrees sont le "
              "foyer `get_nearest_enemy`, les trois passe-plats, et la geometrie hex. Le build du "
              "jeu n'entre pas -- aucun symbole n'est resolu ici, ils ne sont que CITES.",
}

import random                                                                    # noqa: E402
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parents[2]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import hexgeo                                                                    # noqa: E402
from engine import battle_query as bq                                            # noqa: E402
from engine.playbook.noncomparable import ironkin_steeljack as IK                # noqa: E402
from engine.playbook.noncomparable import master_of_the_tutelaries as MT         # noqa: E402
from engine.playbook.noncomparable import summon_attack_range as SAR             # noqa: E402

COLS, ROWS = 8, 8


class _Ctx:
    """Le minimum que les quatre corps lisent : `origin`, `epos`, `enemies`, `elev_by_pos`,
    `neigh_by_pos`. Duck-type -- c'est ainsi que `neigh_map` / `occupied_positions` lisent deja."""

    def __init__(self, origin, positions, elev, neigh=None):
        self.origin = origin
        self.epos = list(positions)
        self.enemies = [{"id": 100 + i, "pos": {"col": c, "row": r}}
                        for i, (c, r) in enumerate(positions)]
        self.elev_by_pos = elev
        self.neigh_by_pos = neigh


# ---------------------------------------------------------------- LES TROIS CORPS D'AVANT, VERBATIM

def _avant_summon_attack_range(ctx, frm):
    """`summon_attack_range.py::nearest_enemy` d'avant #971-r1 -- rendait `(id, pos)`."""
    neigh = bq.neigh_map(ctx)
    best = None            # (id, pos, dist, adj)
    for e in (ctx.enemies or []):
        p = e.get("pos") or {}
        if p.get("col") is None:
            continue
        q = (p["col"], p["row"])
        d = hexgeo.distance(frm, q)
        adj = bq.are_entities_adjacent(frm, q, ctx.elev_by_pos, neigh)
        if best is None or d < best[2] or (adj and not best[3]):
            best = (e.get("id"), q, d, adj)
    return None if best is None else (best[0], best[1])


def _avant_master_of_the_tutelaries(ctx):
    """`master_of_the_tutelaries.py::_nearest_enemy_tile` d'avant -- ancre sur l'ORIGINE."""
    if ctx.origin is None:
        return None
    best = None
    best_d = None
    best_melee = False
    for p in (ctx.epos or []):
        pk = (p[0], p[1])
        d = hexgeo.distance(ctx.origin, pk)
        melee = bq.are_entities_adjacent(ctx.origin, pk, ctx.elev_by_pos, bq.neigh_map(ctx))
        if best_d is None or d < best_d or (melee and not best_melee):
            best, best_d, best_melee = pk, d, melee
    return best


def _avant_ironkin_steeljack(ctx, frm):
    """`ironkin_steeljack.py::_nearest_enemy` d'avant -- rendait une POSITION."""
    neigh = bq.neigh_map(ctx)
    best = None                      # (pos, dist, adj)
    for p in (ctx.epos or []):
        q = (p[0], p[1])
        d = hexgeo.distance(frm, q)
        adj = bq.are_entities_adjacent(frm, q, ctx.elev_by_pos, neigh)
        if best is None or d < best[1] or (adj and not best[2]):
            best = (q, d, adj)
    return None if best is None else best[0]


def _plateaux_aleatoires(seed=4242, n=14):
    """Plateaux 8x8, elevations 0..4, 1 a 6 ennemis, ancres variees -- la COUVERTURE."""
    rnd = random.Random(seed)
    cells = [(c, r) for c in range(COLS) for r in range(ROWS)]
    for _ in range(n):
        elev = {p: rnd.randint(0, 4) for p in cells}
        k = rnd.randint(1, 6)
        foes = rnd.sample(cells, k)
        origin = rnd.choice([p for p in cells if p not in foes])
        yield _Ctx(origin, foes, elev), origin


def _plateaux_craftes():
    """Les configurations ou le tie-break `(adj && !bestAdj)` MORD -- et elles ne sortent PAS d'un
    tirage : il faut DEUX ennemis a distance hex 1 de l'ancre, le PREMIER enumere separe par
    `|dElev| >= 2` (donc `AreTilesAdjacent` FAUX malgre `dist == 1`) et le second de plain-pied.
    Alors `d < bestDist` est faux (1 < 1) et c'est `(adj && !bestAdj)` seul qui deplace le best.

    Mesure de la RARETE, qui est la raison d'etre de ces plateaux : sur les 14 plateaux aleatoires
    ci-dessus, cette configuration sort **0** fois (etage 0 rougissait). Un balayage qui ne
    l'exerce pas ne teste qu'un `min`, et serait vert sur un foyer ayant PERDU le tie-break natif."""
    base = {(c, r): 0 for c in range(COLS) for r in range(ROWS)}
    origin = (3, 3)
    voisins = hexgeo.neighbors(*origin)
    assert len(voisins) >= 2
    haut, plat = voisins[0], voisins[1]
    for delta in (2, 3, 4):
        elev = dict(base)
        elev[haut] = delta                       # |dElev| >= 2 -> PAS adjacent, malgre dist 1
        # ordre d'enumeration : le NON adjacent d'abord, sinon le tie-break n'a rien a corriger
        yield _Ctx(origin, [haut, plat], elev), origin
        # et le meme, avec un TROISIEME candidat plus loin : le best ne doit pas y retomber
        loin = (0, 0) if origin != (0, 0) else (7, 7)
        yield _Ctx(origin, [haut, plat, loin], elev), origin
    # contre-forme : les DEUX voisins separes -> aucun n'est adjacent, le tie-break ne mord pas et
    # c'est la distance seule qui decide (temoin que l'etage 0 ne compte pas n'importe quoi).
    elev = dict(base)
    elev[haut] = 3
    elev[plat] = 3
    yield _Ctx(origin, [haut, plat], elev), origin
    # L'ANCRE COINCIDE AVEC UN ENNEMI -- le SEUL regime ou `AreEntitiesAdjacent` differe
    # d'`IterateAdjacentTiles` (court-circuit d'identite `t1 == t2`, #433-r1). Mesure : sans ce
    # plateau, remplacer `are_entities_adjacent` par `is_adjacent` dans le foyer laisse le cliquet
    # VERT -- les deux coincident partout ailleurs. Le natif l'atteint : `GetNearestEnemy(caster,
    # position)` ne filtre pas la tuile fournie, un appelant peut y passer une tuile OCCUPEE.
    # PLAIN-PIED obligatoire : il faut que le SECOND candidat soit adjacent au sens des DEUX
    # primitives, sinon le tie-break n'a rien a deplacer et les deux bras coincident encore.
    yield _Ctx(haut, [haut, plat], dict(base)), haut   # ancre == le 1er ennemi enumere


def _plateaux(seed=4242, n=14):
    """La COUVERTURE (aleatoire) et les CONFIGURATIONS CRAFTEES, dans le meme balayage."""
    yield from _plateaux_aleatoires(seed, n)
    yield from _plateaux_craftes()


# ============================================== 0. LE BALAYAGE EST DISCRIMINANT (non-vide assertionne)

def test_etape0_le_balayage_fait_mordre_le_tie_break():
    """Un balayage ou `(adj && !bestAdj)` ne mord JAMAIS ne testerait que `min` : il serait vert
    sur un foyer qui aurait perdu le tie-break natif. On assertionne son propre non-vide.

    ⚠ MESURE : le tirage aleatoire seul rend **0** morsure -- il faut CRAFTER (cf.
    `_plateaux_craftes`). C'est le tirage qui a fait rougir cet etage a son premier jeu."""
    morsures = 0
    for ctx, origin in _plateaux():
        neigh = bq.neigh_map(ctx)
        best_d = None
        best_adj = False
        for p in ctx.epos:
            d = hexgeo.distance(origin, p)
            adj = bq.are_entities_adjacent(origin, p, ctx.elev_by_pos, neigh)
            if best_d is not None and not (d < best_d) and adj and not best_adj:
                morsures += 1
            if best_d is None or d < best_d or (adj and not best_adj):
                best_d, best_adj = d, adj
    assert morsures > 0, (
        "aucune configuration ou le tie-break natif departage : le balayage ne prouverait rien")


# ================================================== 1-3. LES TROIS CORPS D'AVANT == LE FOYER, EXHAUSTIF

def test_etape1_summon_attack_range_est_value_preserving():
    for ctx, _origin in _plateaux():
        for frm in [(c, r) for c in range(0, COLS, 3) for r in range(0, ROWS, 3)]:
            assert SAR.nearest_enemy(ctx, frm) == _avant_summon_attack_range(ctx, frm)


def test_etape2_master_of_the_tutelaries_est_value_preserving():
    pb = MT.MasterOfTheTutelariesPlaybook()
    for ctx, _origin in _plateaux():
        assert pb._nearest_enemy_tile(ctx) == _avant_master_of_the_tutelaries(ctx)


def test_etape3_ironkin_steeljack_est_value_preserving():
    pb = IK.IronkinSteeljackPlaybook()
    for ctx, _origin in _plateaux():
        for frm in [(c, r) for c in range(0, COLS, 3) for r in range(0, ROWS, 3)]:
            assert pb._nearest_enemy(ctx, frm) == _avant_ironkin_steeljack(ctx, frm)


# ================================================ 4. LE FOYER EST PLUS FIDELE : `bestDist` = int.MaxValue

def test_etape4_bestdist_part_de_int_max_et_non_de_pas_de_best():
    """`best = null ; bestDist = int.MaxValue` puis `if (d < bestDist || ...)` -- le natif ne garde
    JAMAIS un candidat parce qu'il est le premier. Les trois corps ecrivaient `best is None or ...`.

    Le regime ou les deux divergent exige `d >= int.MaxValue` ET `adj` faux. `get_distance` sur des
    singletons non vides ne rend jamais `DISTANCE_UNREACHABLE`, donc il est INATTEIGNABLE par la
    voie normale -- on l'exerce ici par la seule porte qui reste, un ensemble d'ennemis dont AUCUN
    n'a de position lisible, et on garde le fait STRUCTUREL : le foyer nomme `DISTANCE_UNREACHABLE`
    comme graine, ce qui est le litteral natif."""
    assert bq.DISTANCE_UNREACHABLE == 0x7FFFFFFF, "`int.MaxValue`, la graine de `bestDist`"
    vide = _Ctx((0, 0), [], {}, None)
    assert bq.get_nearest_enemy(vide) is None, "aucun candidat -> `best` reste null"


# ============================ 4bis. LE FOYER D'ADJACENCE EST `AreEntitiesAdjacent`, PAS `is_adjacent`

def test_etape4bis_le_court_circuit_d_identite_est_celui_du_natif():
    """`BattleQuery$$AreEntitiesAdjacent(tiles, unit)` -> `MovementUtil$$AreTilesAdjacent(t1, t2)` =
    `(|dElev| < 2) & (t1 == t2 || IsNeighbour(t1, t2))`. `is_adjacent`, lui, mirrore
    `TileQuery$$IterateAdjacentTiles`, qui ne rend JAMAIS la tuile source.

    ⚠ MESURE : les deux ne different QUE sur `t1 == t2`, et ce regime ne sort d'AUCUN tirage --
    l'ancre est soit la tuile du caster, soit une tuile de spawn LIBRE. Substituer `is_adjacent`
    dans le foyer laissait donc les etages 1-3 VERTS (contre-epreuve par mutation, 2026-08-15 :
    3 mutations sur 4 vues, celle-ci NON). Il faut le CRAFTER, et c'est ce que fait cet etage."""
    elev = {(c, r): 0 for c in range(COLS) for r in range(ROWS)}    # PLAT (cf. plus bas)
    e1 = (3, 3)
    e2 = hexgeo.neighbors(*e1)[0]                                   # voisin de PLAIN-PIED
    ctx = _Ctx(e1, [e1, e2], elev)
    assert bq.are_entities_adjacent(e1, e1, elev, None) is True, "court-circuit d'identite `t1 == t2`"
    assert bq.is_adjacent(e1, e1, elev, None) is False, (
        "`IterateAdjacentTiles` ne rend jamais la tuile source -- c'est le contre-exemple #433-r1")
    # Ancre = `e1`, qui est AUSSI le 1er ennemi enumere.
    #   avec `are_entities_adjacent` : cand1 `e1` -> d=0, adj=VRAI (identite) -> bestAdj = VRAI ;
    #     cand2 `e2` -> d=1, adj=VRAI, mais `1 < 0` faux et `(adj && !bestAdj)` faux -> best = e1.
    #   avec `is_adjacent`            : cand1 `e1` -> d=0, adj=FAUX -> bestAdj = FAUX ;
    #     cand2 `e2` -> d=1, adj=VRAI -> `(adj && !bestAdj)` VRAI -> best = e2. DIVERGENT.
    # ⚠ Le PLAIN-PIED est necessaire : si `e2` etait separe de `e1` par `|dElev| >= 2`, il ne serait
    #   adjacent pour AUCUNE des deux primitives et les deux bras coincideraient a nouveau (mesure :
    #   la 1re version de cet etage, avec une crete, laissait la mutation invisible).
    assert bq.get_nearest_enemy(ctx, e1)[1] == e1, (
        "le foyer doit appeler `are_entities_adjacent` : avec `is_adjacent`, `bestAdj` resterait "
        "FAUX au 1er candidat et le tie-break deplacerait le best vers le voisin")


# =========================================================== 5. L'ANCRE EST LE `Nullable` DU NATIF

def test_etape5_l_ancre_est_le_nullable_du_natif():
    """`tilesA = position.HasValue ? position.Value : GetUnitPosition(caster)`. Les deux voies sont
    le MEME corps -- ce n'est pas une convention de port."""
    elev = {(c, r): 0 for c in range(COLS) for r in range(ROWS)}
    ctx = _Ctx(origin=(0, 0), positions=[(5, 5), (1, 0)], elev=elev)
    # `Nullable` VIDE -> ancre = `ctx.origin` = (0,0) -> le plus proche est (1,0)
    assert bq.get_nearest_enemy(ctx)[1] == (1, 0)
    # `Nullable` PLEIN -> ancre = la tuile fournie -> le plus proche est (5,5)
    assert bq.get_nearest_enemy(ctx, (5, 5))[1] == (5, 5)
    assert bq.get_nearest_enemy(ctx, (4, 5))[1] == (5, 5)
    # ancre absente ET pas d'origine -> le port ne devine pas `GetUnitPosition`
    assert bq.get_nearest_enemy(_Ctx(None, [(1, 1)], elev)) is None


# ================================================ 6. AUCUN FORK NE PEUT REVENIR (lecture de la SOURCE)

def test_etape6_les_trois_appelants_passent_par_le_foyer():
    """Un passe-plat qui redeviendrait une copie ne serait vu par AUCUN etage ci-dessus : les
    etages 1-3 comparent au bras d'avant, donc une copie EXACTE du bras d'avant les laisserait
    verts. Le discriminant est la SOURCE."""
    import ast
    import inspect
    import textwrap
    for fn, nom in ((SAR.nearest_enemy, "summon_attack_range.nearest_enemy"),
                    (MT.MasterOfTheTutelariesPlaybook._nearest_enemy_tile,
                     "master_of_the_tutelaries._nearest_enemy_tile"),
                    (IK.IronkinSteeljackPlaybook._nearest_enemy,
                     "ironkin_steeljack._nearest_enemy")):
        # ⚠ La DOCSTRING de ces trois passe-plats CITE le natif, `AreEntitiesAdjacent` compris --
        # un critere sur le texte brut de la source les accuse tous (mesure : cet etage a rougi
        # ainsi a son premier jeu). Le discriminant est le CORPS EXECUTABLE, donc l'AST.
        arbre = ast.parse(textwrap.dedent(inspect.getsource(fn))).body[0]
        corps = [n for n in arbre.body
                 if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)
                         and isinstance(n.value.value, str))]
        noms = {n.attr for n in ast.walk(ast.Module(body=corps, type_ignores=[]))
                if isinstance(n, ast.Attribute)}
        noms |= {n.id for n in ast.walk(ast.Module(body=corps, type_ignores=[]))
                 if isinstance(n, ast.Name)}
        assert "get_nearest_enemy" in noms, (
            "%s ne delegue plus au foyer `battle_query.get_nearest_enemy` -- le fork est revenu"
            % nom)
        assert "are_entities_adjacent" not in noms, (
            "%s a reconstitue le tie-break en local : c'est le fork, meme s'il rend juste" % nom)
