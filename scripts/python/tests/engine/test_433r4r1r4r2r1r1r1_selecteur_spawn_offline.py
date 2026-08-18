"""#433-r4-r1-r4-r2-r1-r1-r1 -- les DEUX selecteurs de spawn NC lisent la LISTE STOCKEE.

`AberrantHypermorphPlaybook` (1166) et `MasterOfTheTutelariesPlaybook` (1096) re-projetaient
l'union `abilityTargets` sur la position candidate T par `hexgeo.distance(T, ST) == 1` NU. Le
constat de #614 (« le playbook ne filtre pas par distance, la contrainte vient du selecteur »)
est CONFIRME -- et le selecteur, lui, n'est PAS geometrique :

    <X>Playbook$$EvaluateNonComparable
      -> BasePlaybook$$GetEligibleTargetsSelectable(caster, MainTile(casterPosition))
         -> IBattleQuery slot 0x42 = BattleQuery$$GetValidTargets(unit, UnitPosition(T), abilityType)
            -> TargetingQuery$$GetValidTargets
               -> TargetingQuery$$GetRange : TargetingRange statique +0x30 (TargetingRange$$.cctor),
                  recopie par les DEUX .ctor d'ability -- onlyAdjacent = 0 = RangedBool.True,
                  overrideRange = Nullable(1). RangedBoolExtensions$$IsTrue(0) = VRAI -> octet +4 POSE
               -> TargetingQuery$$GetPossibleTargetsForOptions : rules 0x1040, bit 6 TargetIsTile
                  -> TargetingQuery$$GetTilesInRange : octet +4 POSE
                     -> slot 0x51 = BattleQuery$$GetAdjacentTiles(casterTiles, 0, onlyWalkable, 1)
                        -> BattleQuery$$IterateAdjacentTiles -> TileQuery$$IterateAdjacentTiles
                           -> TileQuery.<IterateAdjacentTiles>d__8$$MoveNext
                              = foreach (nid in tile.ConnectivityComponent.Neighbours)  <- STOCKEE
                                ... if (abs(elev0 - t.Elevation) < 2) yield             <- PORTE

La branche GEOMETRIQUE existe bien -- `GetSurroundingTiles` (slot 0x67) ->
`TileQuery.<IterateSurroundingTiles>d__6$$MoveNext`, triple boucle x/y/z sous `x+y+z == 0` -- mais
c'est celle du range NUMERIQUE, prise quand `onlyAdjacent` n'est PAS pose. C'est elle qui rend
`in_arc` geometrique par construction (#614 §1) ; ici `onlyAdjacent` la court-circuite. Les deux
sites ne partagent donc PAS le verdict d'`in_arc`, malgre l'air de famille.

CONVENTION DE CE FICHIER : « AVANT » se rejoue en passant le contexte SANS canal
(`elev_by_pos=None`, `neigh_by_pos={}`) -- `is_adjacent` y retombe alors sur son repli geometrique
documente, qui EST l'ancien code, a l'identique. Aucune assertion ne depend d'un code supprime.

100 % OFFLINE.
"""
from __future__ import annotations

import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parents[2]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import hexgeo                                                                    # noqa: E402
from engine.entities.pathfinding.board import (Board,                            # noqa: E402
                                               adjacent_neigh_by_pos)
from engine.playbook.noncomparable._base import NCContext                        # noqa: E402
from engine.playbook.noncomparable.aberrant_hypermorph import (                  # noqa: E402
    AberrantHypermorphPlaybook)
from engine.playbook.noncomparable.master_of_the_tutelaries import (             # noqa: E402
    MasterOfTheTutelariesPlaybook)

COLS, ROWS = 5, 5

T = (2, 2)                                  # position candidate du caster (= son origine ici)
FANTOME = hexgeo.neighbors(2, 2)[0]         # couronne hex de T, ABSENT de sa liste stockee
TEMOIN = hexgeo.neighbors(2, 2)[1]          # couronne hex de T, PRESENT des deux cotes


def _tid(col: int, row: int) -> int:
    return col * ROWS + row + 1


def _dans_board(p) -> bool:
    return 0 <= p[0] < COLS and 0 <= p[1] < ROWS


def _board(elev=None, coupe=()) -> Board:
    """Board 5x5 plein. `coupe` = aretes NON DIRIGEES retirees du champ `neighbours` des DEUX
    cotes -- le patron `Bridge` mesure live (#433-r4-r1-r4-r2)."""
    elev = elev or {}
    coupees = set()
    for (a, b) in coupe:
        coupees.add((a, b))
        coupees.add((b, a))
    tiles = []
    for col in range(COLS):
        for row in range(ROWS):
            tiles.append({"id": _tid(col, row), "col": col, "row": row, "walkable": True,
                          "isWall": False, "elevation": int(elev.get((col, row), 0)),
                          "neighbours": [_tid(c, r) for (c, r) in hexgeo.neighbors(col, row)
                                         if _dans_board((c, r))
                                         and ((col, row), (c, r)) not in coupees]})
    return Board(tiles)


def _rpc_tuiles(ability_id: int, from_here: list, union: list | None = None):
    """Le callable `ctx.ability_targets` : la forme EXACTE que lisent `eligible_target_tiles`
    (`fromHere` + `targets`). ⚠ `MasterOfTheTutelariesPlaybook._eligible_spawn_tiles`, qui ne
    lisait que `targets`, a ete SUPPRIME par `#971-r4` : les trois playbooks ring-1 passent
    desormais par le MEME foyer, donc par les DEUX vues."""
    def _entrees(ps):
        return [{"kind": "tile", "tile": {"col": c, "row": r}} for (c, r) in ps]

    def _f(uid, aid):
        if aid != ability_id:
            return {}
        return {"units": [{"abilities": [{"abilityId": aid,
                                          "fromHere": _entrees(from_here),
                                          "targets": _entrees(union if union is not None
                                                              else from_here)}]}]}
    return _f


def _ctx(ability_id: int, spawn: list, board: Board, epos: list, *, canal: bool,
         union: list | None = None) -> NCContext:
    """`canal=False` = le contexte d'AVANT le branchement (aucun des deux etages publie)."""
    neigh = adjacent_neigh_by_pos(board) if canal else {}
    elev = board.elev_by_pos() if canal else None
    walk = {(c, r): True for c in range(COLS) for r in range(ROWS)}
    return NCContext(uid=1, origin=T, reach_nc=[T], epos=list(epos), fpos=[], plan={},
                     hp_cur_by_id={}, ability_targets=_rpc_tuiles(ability_id, spawn, union),
                     neigh_by_pos=neigh, walkable_by_pos=walk, elev_by_pos=elev,
                     tile_id_by_pos={(c, r): _tid(c, r)
                                     for c in range(COLS) for r in range(ROWS)})


def _cible(sorties: list):
    """L'id de tuile emis, ou `None` si le playbook n'a rien emis."""
    return sorties[0]["target"] if sorties else None


# ------------------------------------------------------------------ le montage est-il discriminant
def test_le_montage_est_discriminant():
    """Sans ce cran, tous les autres pourraient etre verts pour la mauvaise raison."""
    assert hexgeo.distance(T, FANTOME) == 1 and hexgeo.distance(T, TEMOIN) == 1
    assert FANTOME != TEMOIN and _dans_board(FANTOME) and _dans_board(TEMOIN)
    neigh = adjacent_neigh_by_pos(_board(coupe=[(T, FANTOME)]))
    assert FANTOME not in neigh[T] and TEMOIN in neigh[T]
    # ... et le canal reste MUET quand on ne le publie pas : c'est ce qui rejoue l'AVANT.
    assert _ctx(1166, [FANTOME], _board(coupe=[(T, FANTOME)]), [], canal=False).neigh_by_pos == {}


def _voisins_reels(p) -> list:
    return [q for q in hexgeo.neighbors(p[0], p[1]) if _dans_board(q)]


# ============================================================ 1166 -- AberrantHypermorphPlaybook
# Utilite = `GetAdjacentEnemies(ST, caster).Count`, MIN_UTILITY = 1 : il faut un ennemi au contact
# de la tuile de spawn pour que la moindre action soit emise.
def _ennemi_de(st) -> tuple:
    """Un voisin de `st` qui n'est ni T, ni l'autre tuile de spawn -- pour ne pas croiser."""
    autre = TEMOIN if st == FANTOME else FANTOME
    for q in _voisins_reels(st):
        if q not in (T, autre) and q not in _voisins_reels(autre):
            return q
    raise AssertionError("montage impossible : aucun ennemi isolable autour de %r" % (st,))


def test_1166_le_FANTOME_est_ECARTE_par_la_liste_stockee():
    """Le discriminant : meme tuile, meme ennemi -- seul le substrat d'adjacence change."""
    bd = _board(coupe=[(T, FANTOME)])
    ennemi = _ennemi_de(FANTOME)
    pb = AberrantHypermorphPlaybook()
    assert _cible(pb.generate_candidates(
        _ctx(1166, [FANTOME], bd, [ennemi], canal=False))) == _tid(*FANTOME)   # AVANT : la couronne
    assert pb.generate_candidates(
        _ctx(1166, [FANTOME], bd, [ennemi], canal=True)) == []                 # APRES : la liste


def test_1166_le_TEMOIN_reste_ACCORDE():
    """Anti-inertie : le refus ci-dessus n'est pas un blocage general du montage."""
    bd = _board(coupe=[(T, FANTOME)])
    ennemi = _ennemi_de(TEMOIN)
    pb = AberrantHypermorphPlaybook()
    for canal in (False, True):
        assert _cible(pb.generate_candidates(
            _ctx(1166, [TEMOIN], bd, [ennemi], canal=canal))) == _tid(*TEMOIN)


def test_1166_le_FANTOME_MEILLEUR_perd_quand_meme():
    """Le cas qui CHANGE la decision : le fantome maximise l'utilite et gagnait l'argmax."""
    bd = _board(coupe=[(T, FANTOME)])
    deux = [q for q in _voisins_reels(FANTOME)
            if q not in (T, TEMOIN) and q not in _voisins_reels(TEMOIN)][:2]
    assert len(deux) == 2, "montage : il faut deux ennemis propres au fantome"
    epos = deux + [_ennemi_de(TEMOIN)]
    pb = AberrantHypermorphPlaybook()
    # fromHere donne le FANTOME en premier : a utilite egale il gagnerait aussi par l'ordre.
    avant = pb.generate_candidates(_ctx(1166, [FANTOME, TEMOIN], bd, epos, canal=False))
    apres = pb.generate_candidates(_ctx(1166, [FANTOME, TEMOIN], bd, epos, canal=True))
    assert _cible(avant) == _tid(*FANTOME) and avant[0]["pred"] == 2.0
    assert _cible(apres) == _tid(*TEMOIN) and apres[0]["pred"] == 1.0


def test_1166_la_PORTE_D_ELEVATION_ecarte_aussi():
    """Le SECOND etage de l'iterateur, que le port ne portait pas davantage. Aucune arete coupee
    ici : c'est bien la porte, et elle seule, qui tranche.

    ⚠ L'ELEVATION EST POSEE SUR `T`, JAMAIS SUR LA TUILE DE SPAWN, et c'est ce qui rend le test
    conclusif. La posee sur `TEMOIN` rendait aussi VERTE la mutation qui retire `ctx.elev_by_pos`
    du FILTRE (contre-epreuve du 2026-08-05) : elle isolait `TEMOIN` de son propre ennemi, donc
    l'utilite tombait a 0 et le playbook rendait `[]` pour une raison qui n'etait pas la porte.
    Sur `T`, l'utilite de `TEMOIN` reste 1 -- seul le filtre peut expliquer le refus."""
    bd = _board(elev={T: 2})
    ennemi = _ennemi_de(TEMOIN)
    pb = AberrantHypermorphPlaybook()
    avant = pb.generate_candidates(_ctx(1166, [TEMOIN], bd, [ennemi], canal=False))
    assert _cible(avant) == _tid(*TEMOIN) and avant[0]["pred"] == 1.0   # l'utilite EST atteignable
    assert pb.generate_candidates(_ctx(1166, [TEMOIN], bd, [ennemi], canal=True)) == []


def test_1166_le_REPLI_geometrique_est_preserve():
    """Canal muet POUR CETTE TUILE -> couronne hex, degradation permissive DOCUMENTEE. Un canal
    absent ne doit jamais se lire comme « aucun voisin » (le vice #381-r3)."""
    bd = _board(coupe=[(T, FANTOME)])
    ennemi = _ennemi_de(FANTOME)
    ctx = _ctx(1166, [FANTOME], bd, [ennemi], canal=True)
    ctx.neigh_by_pos = {}                       # dict VIDE : mesure faite, aucune tuile captee
    pb = AberrantHypermorphPlaybook()
    assert _cible(pb.generate_candidates(ctx)) == _tid(*FANTOME)


# ======================================================= 1096 -- MasterOfTheTutelariesPlaybook
# Gates propres a ce playbook : nE2 > 0 (un ennemi a distance hex EXACTEMENT 2 de la tuile REELLE
# du caster) et nFree > 2 (tuiles ou l'on peut ajouter une unite, autour de la tuile de spawn).
def _ennemi_ring2() -> tuple:
    for c in range(COLS):
        for r in range(ROWS):
            if hexgeo.distance(T, (c, r)) == 2:
                return (c, r)
    raise AssertionError("montage impossible : aucune tuile a distance 2")


def test_1096_les_gates_du_playbook_sont_franchis():
    """Cran de montage : sans nE2 > 0 le playbook rend `[]` pour une raison qui n'est PAS l'objet
    du test, et les deux verdicts se confondraient."""
    bd = _board(coupe=[(T, FANTOME)])
    e2 = _ennemi_ring2()
    assert hexgeo.distance(T, e2) == 2
    pb = MasterOfTheTutelariesPlaybook()
    assert pb.generate_candidates(_ctx(1096, [TEMOIN], bd, [e2], canal=True)) != []


def test_1096_le_FANTOME_est_ECARTE_par_la_liste_stockee():
    bd = _board(coupe=[(T, FANTOME)])
    e2 = _ennemi_ring2()
    pb = MasterOfTheTutelariesPlaybook()
    assert _cible(pb.generate_candidates(
        _ctx(1096, [FANTOME], bd, [e2], canal=False))) == _tid(*FANTOME)   # AVANT
    assert pb.generate_candidates(_ctx(1096, [FANTOME], bd, [e2], canal=True)) == []   # APRES


def test_1096_le_TEMOIN_reste_ACCORDE():
    bd = _board(coupe=[(T, FANTOME)])
    e2 = _ennemi_ring2()
    pb = MasterOfTheTutelariesPlaybook()
    for canal in (False, True):
        assert _cible(pb.generate_candidates(
            _ctx(1096, [TEMOIN], bd, [e2], canal=canal))) == _tid(*TEMOIN)


def test_1096_la_PORTE_D_ELEVATION_ecarte_aussi():
    """Meme precaution qu'en 1166 : l'elevation va sur `T`, pas sur la tuile de spawn -- sinon
    `adjacent_addable_count(TEMOIN, ...)` chuterait et le `[]` serait imputable au gate nFree."""
    bd = _board(elev={T: 2})
    e2 = _ennemi_ring2()
    pb = MasterOfTheTutelariesPlaybook()
    assert _cible(pb.generate_candidates(
        _ctx(1096, [TEMOIN], bd, [e2], canal=False))) == _tid(*TEMOIN)
    assert pb.generate_candidates(_ctx(1096, [TEMOIN], bd, [e2], canal=True)) == []


def test_1096_le_REPLI_geometrique_est_preserve():
    bd = _board(coupe=[(T, FANTOME)])
    ctx = _ctx(1096, [FANTOME], bd, [_ennemi_ring2()], canal=True)
    ctx.neigh_by_pos = {}
    pb = MasterOfTheTutelariesPlaybook()
    assert _cible(pb.generate_candidates(ctx)) == _tid(*FANTOME)


def test_1096_les_RING_2_ne_se_branchent_PAS():
    """Les deux autres distances de ce corps (`nE2`, le bonus de 100) mirrorent
    `GetUnitsAtDistance`/`GetDistance` -> `GetTilesAtDistance`, GEOMETRIQUES par construction
    (#614 §1). Couper l'arete (T, FANTOME) ne doit RIEN leur faire : ici l'ennemi ring-2 est
    atteint par un chemin qui passe par le fantome, et il compte quand meme."""
    e2 = _ennemi_ring2()
    coupe = [(T, q) for q in _voisins_reels(T)]          # T totalement isole de sa liste stockee
    bd = _board(coupe=coupe)
    pb = MasterOfTheTutelariesPlaybook()
    ctx = _ctx(1096, [TEMOIN], bd, [e2], canal=True)
    assert adjacent_neigh_by_pos(bd)[T] == []            # la liste stockee de T est VIDE
    assert pb.generate_candidates(ctx) == []             # ... donc aucune tuile de spawn
    # mais le gate nE2, lui, tient toujours : le remettre adjacent suffit a re-emettre.
    assert _cible(pb.generate_candidates(
        _ctx(1096, [TEMOIN], _board(), [e2], canal=True))) == _tid(*TEMOIN)
