"""#433-r4-r1-r1 -- `WallOfMirrorsAbility` (1186), face DECISION portee OFFLINE.

Ce que ces gardes verrouillent, etage par etage de
`IdunBattleLogic.Entities.Abilities.Active.Loki.WallOfMirrorsAbility$$GetPossibleTiles` :

  1. l'ANNEAU est a distance EXACTEMENT `range` (= 2) -- la soustraction des deux `SurroundingTiles`
     n'est pas cosmetique : sans elle le disque entier passerait, et le ring-1 avec ;
  2. `CanAddUnit` retire les tuiles OCCUPEES (par n'importe quel pied) et non marchables ;
  3. `FromTrigger(!IsObscured(ActiveTarget, Target))` evalue la ligne de vue DEPUIS LA TUILE
     CANDIDATE -- c'est le liant `Filter` qui pose le slot `ability+0x180` ; sans lui le predicat
     lirait le liant ENGLOBANT et le filtre serait inerte ;
  4. `FilterTilesIfCanAttackTargetTileFrom(Caster, Target, ...)` est le DERNIER etage (deja garde par
     `test_433_r4_r1_filter_tiles_can_attack_offline.py` ; ici on verifie seulement qu'il est CABLE).

Plus les deux donnees de REGISTRE que la regle de non-regression exige dans le meme commit : le
masque `TARGETING_OPTIONS` (littéral `0x6004012` de la surcharge PRIMITIVE a 7 parametres) et
`ABILITY_ATTACK_TYPE[1186] = 2 = Others` (3e argument d'`AActiveAbility..ctor`).

100 % OFFLINE : aucun runner, aucune session.
"""
from __future__ import annotations

import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parents[2]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import hexgeo                                                              # noqa: E402
from engine.dsl.base import DslContext                                     # noqa: E402
from engine.runner.abilities.attack_type import ABILITY_ATTACK_TYPE        # noqa: E402
from engine.runner.abilities.handler import ABILITY_CLASSES                # noqa: E402
from engine.runner.abilities.loki import (wall_of_mirrors_possible_tiles,  # noqa: E402
                                          wall_of_mirrors_range)
from engine.runner.abilities.targeting_rule import TargetingRule as TR     # noqa: E402


class _Board:
    """Board hex minimal : grille 9x9 complete, toutes les tuiles marchables, elevation 0 par
    defaut. `by_coord` porte l'elevation (canal lu par `IsObscured`, comme par `Unobscured`)."""

    def __init__(self, cols=9, rows=9, elev=None):
        self._ids, n = {}, 1
        for col in range(cols):
            for row in range(rows):
                self._ids[(col, row)] = n
                n += 1
        self._pos = {v: k for k, v in self._ids.items()}
        self.by_id = {t: {"col": p[0], "row": p[1]} for t, p in self._pos.items()}
        self.by_coord = {p: {"col": p[0], "row": p[1], "elevation": (elev or {}).get(p, 0)}
                         for p in self._ids}

    def id_at(self, col, row):
        return self._ids.get((int(col), int(row)))

    def coord(self, tid):
        return self._pos.get(tid)

    def neighbours(self, tid):
        return [self._ids[p] for p in hexgeo.neighbors(*self._pos[tid]) if p in self._ids]

    def walkable(self, tid):
        return tid in self._pos


CASTER = {"id": 1, "team": 1, "alive": True, "hp": 100, "pos": {"col": 1, "row": 4}}
TARGET = {"id": 2, "team": 2, "alive": True, "hp": 100, "pos": {"col": 5, "row": 4}}


def _unit(uid, team, pos, alive=True, hp=100, feet=None):
    d = {"id": uid, "team": team, "alive": alive, "hp": hp,
         "pos": {"col": pos[0], "row": pos[1]}}
    if feet is not None:
        d["feet"] = [tuple(f) for f in feet]
    return d


def _ctx(units, board, caster=CASTER, target=TARGET):
    return DslContext(units=units, caster=caster, target=target, board=board)


def _tiles(ctx, board, rng=None):
    """Positions rendues par l'arbre `GetPossibleTiles`, triees pour comparaison stable."""
    sel = wall_of_mirrors_possible_tiles(wall_of_mirrors_range() if rng is None else rng)
    return sorted(board.coord(t) for t in sel.select(ctx))


# ------------------------------------------------------------------- etage 1 : l'anneau

def test_la_constante_range_vient_du_gameconfig():
    """`GetNumberConstant(config, 0x16 = range)` -- gameconfig LU, pas un litteral en dur."""
    assert wall_of_mirrors_range() == 2


def test_l_anneau_est_a_distance_exactement_range():
    """Toutes les tuiles rendues sont a distance EXACTEMENT 2 de la cible, et l'ensemble EST
    l'anneau complet (aucune tuile du disque 2 ne manque sur un board vide et plat)."""
    board = _Board()
    ctx = _ctx([CASTER, TARGET], board)
    got = _tiles(ctx, board)
    tpos = (TARGET["pos"]["col"], TARGET["pos"]["row"])
    assert got, "l'anneau ne doit pas etre vide sur un board degage"
    assert all(hexgeo.distance(p, tpos) == 2 for p in got)
    attendu = sorted(p for p in board.by_coord if hexgeo.distance(p, tpos) == 2)
    assert got == attendu


def test_le_ring_1_est_retranche():
    """La soustraction `SurroundingTiles(r) - SurroundingTiles(r-1)` est ce qui exclut le ring-1 :
    sans elle, les 6 voisins immediats de la cible passeraient."""
    board = _Board()
    got = _tiles(_ctx([CASTER, TARGET], board), board)
    tpos = (TARGET["pos"]["col"], TARGET["pos"]["row"])
    ring1 = [p for p in hexgeo.neighbors(*tpos) if p in board.by_coord]
    assert ring1, "montage invalide : la cible doit avoir des voisins"
    assert not (set(got) & set(ring1))


# ------------------------------------------------------------------- etage 2 : CanAddUnit

def test_can_add_unit_retire_les_tuiles_occupees():
    """Une unite VIVANTE posee sur une tuile de l'anneau la retire (`CanAddUnit`). L'occupation se
    lit par PIED : une multi-hex bloque aussi ses pieds secondaires."""
    board = _Board()
    tpos = (TARGET["pos"]["col"], TARGET["pos"]["row"])
    anneau = sorted(p for p in board.by_coord if hexgeo.distance(p, tpos) == 2)
    squatte, second = anneau[0], anneau[1]
    # AMI du caster (team 1) : `CanAddUnit` l'exclut par OCCUPATION seule -- un ennemi retirerait
    # AUSSI, par le dernier etage, les candidates auxquelles il serait adjacent (cf. le test dedie).
    bloqueur = _unit(9, 1, squatte, feet=[squatte, second])
    got = _tiles(_ctx([CASTER, TARGET, bloqueur], board), board)
    assert squatte not in got and second not in got
    assert set(got) == set(anneau) - {squatte, second}


def test_can_add_unit_ignore_les_morts():
    """Un cadavre n'occupe pas : `CanAddUnit` filtre sur les unites VIVANTES."""
    board = _Board()
    tpos = (TARGET["pos"]["col"], TARGET["pos"]["row"])
    anneau = sorted(p for p in board.by_coord if hexgeo.distance(p, tpos) == 2)
    mort = _unit(9, 2, anneau[0], alive=False, hp=0)
    assert anneau[0] in _tiles(_ctx([CASTER, TARGET, mort], board), board)


# ------------------------------------------------------------------- etage 3 : la ligne de vue

def test_la_ligne_de_vue_part_de_la_tuile_candidate():
    """`FromTrigger(tiles, Not(IsObscured(ActiveTarget, Target)))` : le liant pose la TUILE COURANTE
    au slot `ability+0x180`, donc la LoS est evaluee DEPUIS elle. Une crete d'elevation posee entre
    UNE candidate et la cible retire CETTE candidate, et elle seule.

    `battle_query.is_target_tile_obscured` ne modelise que la distance EXACTEMENT 2 (borne v1 heritee
    de `Unobscured`) -- c'est precisement le regime de cet anneau, donc le filtre y est ACTIF."""
    board_plat = _Board()
    tpos = (TARGET["pos"]["col"], TARGET["pos"]["row"])
    base = _tiles(_ctx([CASTER, TARGET], board_plat), board_plat)
    # une crete de hauteur 4 sur CHAQUE tuile intermediaire entre `cand` et la cible
    cand = base[0]
    entre = [p for p in board_plat.by_coord
             if hexgeo.distance(p, cand) == 1 and hexgeo.distance(p, tpos) == 1]
    assert entre, "montage invalide : il faut au moins une tuile intermediaire"
    board_crete = _Board(elev={p: 4 for p in entre})
    got = _tiles(_ctx([CASTER, TARGET], board_crete), board_crete)
    assert cand not in got, "la candidate derriere la crete doit etre retiree"
    assert set(got) == set(base) - {cand}, "aucune AUTRE candidate ne doit bouger"


def test_sans_elevation_le_filtre_de_vue_est_passe_tout():
    """Degradation NOMMEE et PERMISSIVE : sans canal d'elevation, `is_target_tile_obscured` rend
    faux partout -> `IsObscured` faux -> `Not(...)` vrai -> aucune tuile retiree."""
    board = _Board()
    tpos = (TARGET["pos"]["col"], TARGET["pos"]["row"])
    got = _tiles(_ctx([CASTER, TARGET], board), board)
    assert set(got) == {p for p in board.by_coord if hexgeo.distance(p, tpos) == 2}


# ------------------------------------------------------ etage 4 : le filtre de tir est CABLE

def test_le_dernier_etage_filtre_les_tuiles_engagees():
    """`FilterTilesIfCanAttackTargetTileFrom(Caster, Target, ...)` : une candidate qui a un ennemi
    du CASTER adjacent ET qui n'est pas adjacente a la tuile cible est REFUSEE. Sur cet anneau
    (distance 2), aucune candidate n'est adjacente a la cible -> le bras de rattrapage ne mord pas et
    le premier bras tranche seul."""
    board = _Board()
    tpos = (TARGET["pos"]["col"], TARGET["pos"]["row"])
    anneau = sorted(p for p in board.by_coord if hexgeo.distance(p, tpos) == 2)
    cand = anneau[0]
    # un ennemi du caster (team 2) adjacent a `cand`, hors de l'anneau pour ne pas l'occuper
    voisins = [p for p in hexgeo.neighbors(*cand)
               if p in board.by_coord and hexgeo.distance(p, tpos) != 2]
    assert voisins, "montage invalide"
    garde = _unit(9, 2, voisins[0])
    got = _tiles(_ctx([CASTER, TARGET, garde], board), board)
    assert cand not in got
    # contre-epreuve : le MEME montage avec un AMI du caster laisse la tuile passer
    ami = _unit(9, 1, voisins[0])
    assert cand in _tiles(_ctx([CASTER, TARGET, ami], board), board)


def test_selection_vide_quand_l_anneau_est_entierement_occupe():
    """Aucune tuile -> le gate dynamique refusera la cible (`Count == 0`)."""
    board = _Board()
    tpos = (TARGET["pos"]["col"], TARGET["pos"]["row"])
    anneau = sorted(p for p in board.by_coord if hexgeo.distance(p, tpos) == 2)
    squatteurs = [_unit(100 + i, 1, p) for i, p in enumerate(anneau)]
    assert _tiles(_ctx([CASTER, TARGET] + squatteurs, board), board) == []


# ------------------------------------------------------------------- le REGISTRE

def test_le_registre_porte_le_masque_et_le_type_d_attaque():
    """Regle de non-regression : `TARGETING_OPTIONS` **et** `ABILITY_ATTACK_TYPE` dans le meme
    commit. Le masque est le litteral `0x6004012` de la surcharge PRIMITIVE (7 parametres, celle qui
    ECRIT `rules` sans OU avec un preset -- tranchee par les xrefs entrantes du call-site)."""
    assert 1186 in ABILITY_CLASSES
    opts = ABILITY_CLASSES[1186].TARGETING_OPTIONS
    assert int(opts.rules) == 0x6004012
    assert int(opts.rules) == int(TR.TargetMatchesDynamicRule | TR.CasterHasNotMoved
                                  | TR.TargetIsEnemy | TR.AllowObscuredTarget)
    assert opts.self_cast is False
    assert opts.range is not None and opts.range.use_whole_board is True
    assert ABILITY_ATTACK_TYPE.get(1186) == 2                      # AbilityAttackType.Others
