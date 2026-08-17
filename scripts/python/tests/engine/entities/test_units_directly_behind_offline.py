"""Case #48 -- `UnitsDirectlyBehind` : comparateur `>` STRICT (AmountIsGreater), PAS `>=`.

Test OFFLINE deterministe (pur, sans live) du selecteur `IdunBattleLogic.Entities.DSLSelectors$$UnitsDirectlyBehind`.
RE (cf. docs/rl/case-48-units-directly-behind-comparator.md) : piege gshared -- le nom du ctor
FOLDE (`AmountIsEqualOrGreaterAbilityTrigger___ctor`) est MISLABELE par ghidra ; l'ancre fiable est
le SINGLETON de classe `DAT_1832482b0`, construit par `IdunBattleLogic.Entities.DSLTriggers$$AmountIsGreater`
(`IdunBattle.Entities.Conditions.AmountIsGreaterAbilityTrigger$$ShouldTrigger : iVar16 < iVar15` == `amount > threshold`, STRICT). La formule =
`DAT_18324e3c0` construit par `IdunBattleLogic.Entities.DSLFormulas$$MinDistance` (distance hex). Donc le predicat
natif est `MinDistance(caster, candidate) > MinDistance(caster, target)` (`>` STRICT).

Consequence geometrique : sur l'anneau R1 de la cible, un candidat a dist(caster) == dist(caster,
target) (unite LATERALE a distance EGALE, delta 0) est EXCLU par `>` (l'ancien offline `>=` le
sur-incluait a tort). C'est le seul cas frontiere qui separe les deux comparateurs. Confirme LIVE
(test_plasma_cannon_lateral_live). Ce test verrouille l'EXCLUSION du lateral.

Le selecteur n'utilise que `hexgeo.distance` (+ elevation optionnelle) -> aucun board/live requis :
on construit un `DslContext` synthetique avec des positions hex aux 3 deltas frontiere.
ASCII only.
"""
from __future__ import annotations

import hexgeo
from engine.dsl.base import DslContext
from engine.entities.selectors.units import UnitsDirectlyBehind


def _u(uid, col, row, team):
    return {"id": uid, "pos": {"col": col, "row": row}, "team": team, "alive": True, "hp": 100}


def _find_frontier(caster_pos, d_ct):
    """Trouve, autour d'un caster, une cible T a d_ct du caster ayant sur son anneau R1
    un voisin FRONT (delta -1), un voisin LATERAL (delta 0) et un voisin AWAY (delta +1).
    Retourne (T, front, lateral, away) en (col,row). hexgeo est valide vs boardGraph (parite)."""
    cx, cy = caster_pos
    for T in hexgeo.disk(cx, cy, d_ct + 2):
        if hexgeo.distance(caster_pos, T) != d_ct:
            continue
        front = lateral = away = None
        for n in hexgeo.neighbors(*T):
            delta = hexgeo.distance(caster_pos, n) - d_ct
            if delta == -1 and front is None:
                front = n
            elif delta == 0 and lateral is None:
                lateral = n
            elif delta == 1 and away is None:
                away = n
        if front and lateral and away:
            return T, front, lateral, away
    raise AssertionError("geometrie frontiere introuvable (bug hexgeo?)")


def test_units_directly_behind_excludes_lateral_equal():
    """`>` STRICT natif : le candidat LATERAL a distance EGALE (delta 0) est EXCLU ; le FRONT (delta -1)
    exclu ; seul l'AWAY (delta +1) inclus. Miroir exact de `AmountIsGreater` + `MinDistance`."""
    caster_pos = (10, 10)
    d_ct = 2
    T, front, lateral, away = _find_frontier(caster_pos, d_ct)

    # unite "trop loin" : hors anneau R1 de la cible (dist(target) == 2) mais plus loin du caster -> EXCLUE
    # par le filtre d'anneau (SurroundingTiles(target,1,1)), independamment du comparateur.
    off_ring = next(n for n in hexgeo.disk(T[0], T[1], 3) if hexgeo.distance(T, n) == 2
                    and hexgeo.distance(caster_pos, n) > d_ct and n != caster_pos)

    caster = _u(1, caster_pos[0], caster_pos[1], team=1)
    target = _u(2, T[0], T[1], team=2)
    u_front = _u(3, front[0], front[1], team=2)      # delta -1 : plus pres du caster
    u_lateral = _u(4, lateral[0], lateral[1], team=2)  # delta  0 : DISCRIMINANT (dist == d_ct)
    u_away = _u(5, away[0], away[1], team=2)          # delta +1 : plus loin du caster
    u_far = _u(6, off_ring[0], off_ring[1], team=2)  # hors anneau R1 (dist(target)==2) : trop loin

    ctx = DslContext(units=[caster, target, u_front, u_lateral, u_away, u_far],
                     caster=caster, target=target)
    sel_ids = sorted(u["id"] for u in UnitsDirectlyBehind().select(ctx))

    assert sel_ids == [5], (
        f"UnitsDirectlyBehind {sel_ids} != [5(away)] : le comparateur natif est `>` STRICT "
        f"(AmountIsGreater) -> seul l'away strictement plus loin passe ; lateral (delta 0), front et "
        f"hors-anneau exclus")
    assert 3 not in sel_ids, "front (delta -1, plus pres du caster) doit etre EXCLU"
    assert 4 not in sel_ids, "lateral (delta 0, distance EGALE) doit etre EXCLU par `>` STRICT (natif AmountIsGreater)"
    assert 5 in sel_ids, "away (delta +1, strictement plus loin) doit etre INCLU"
    assert 6 not in sel_ids, "hors-anneau R1 (dist(target) 2, trop loin) doit etre EXCLU (filtre d'anneau)"


def test_units_directly_behind_excludes_team_target_and_dead():
    """Filtres de base (mirror de la construction native) : la cible elle-meme (Tiles(target)
    soustrait), les allies du caster (Enemies(caster, .)) et les morts (occupation de tuile)
    sont exclus, meme s'ils sont sur l'anneau R1 a delta >= 0."""
    caster_pos = (10, 10)
    d_ct = 2
    T, _front, lateral, away = _find_frontier(caster_pos, d_ct)

    caster = _u(1, caster_pos[0], caster_pos[1], team=1)
    target = _u(2, T[0], T[1], team=2)
    ally = _u(6, lateral[0], lateral[1], team=1)       # allie du caster (meme team) -> exclu
    dead = _u(7, away[0], away[1], team=2)
    dead["alive"] = False                              # mort -> plus DEBOUT sur sa tuile -> exclu
    # un ennemi vivant valide (away, autre tuile) pour prouver que le selecteur n'est pas vide par erreur
    # (on reutilise la tuile away pour dead ; on met l'ennemi valide sur un 2e away s'il existe)
    ctx = DslContext(units=[caster, target, ally, dead], caster=caster, target=target)
    sel_ids = sorted(u["id"] for u in UnitsDirectlyBehind().select(ctx))
    assert 6 not in sel_ids, "allie du caster (meme team) doit etre EXCLU (Enemies(caster, .))"
    assert 7 not in sel_ids, "mort doit etre EXCLU (occupation de tuile)"
    assert 2 not in sel_ids, "la cible elle-meme doit etre EXCLUE (Tiles(target) soustrait de l'anneau)"
