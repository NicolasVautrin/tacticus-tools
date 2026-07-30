"""PlasmaGrenade (1098) -- face DECISION, confrontee au LIVE (#27-4g).

CE QUE CE TEST GARDE, et pourquoi il ne peut pas passer par accident :

A. **L'EXERCICE** : le natif doit REELLEMENT emettre `ActiveAbilityMessage(1098)` dans au moins un
   bras. Sans ce garde-fou le montage degenere en « le natif finit son tour partout », et les trois
   bras seraient « d'accord » sans rien mesurer.
B. **Le VETO** : quand aucun ennemi n'est adjacent a la cible, la somme du custom vaut `Fix64(0)` et
   le natif la remplace par `IdunBattle.AI.Utilities.BaseUtility.<statics+0x18>`, l'une des deux
   valeurs que `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateActionUtility`
   traduit en `Nullable` VIDE. Le bras C0 le prouve dans le regime le plus exigeant : la cible EST
   legale (`abilityTargets` la rend) et `pairUtility(1098)` y vaut ~13.55 -- une utilite qui aurait
   largement gagne. Le natif ne propose pourtant JAMAIS 1098.
C. **La forme est LINEAIRE, pas booleenne** : au bras C2 le natif prefere la cible dont la
   `pairUtility` est la PLUS FAIBLE parce qu'elle a DEUX voisins ennemis au lieu d'un. Un terme
   booleen (« au moins un voisin ») garderait l'autre cible -- c'est la mutation adversariale que
   le probe joue et dont ce test verifie qu'elle DIVERGE.
D. **Le terme est NECESSAIRE** : veto desarme (custom = 0.0, c'est-a-dire l'etat du port AVANT ce
   commit) -> le moteur propose 1098 en C0, la ou le natif ne le fait jamais.

BRUIT ASSUME : `IdunBattle.AI.Playbook.Loki.PlasmaGrenadePlaybook$$GetUseProbability` rend
`Fix64(1)/Fix64(3)` et `IdunBattle.AI.Playbook.BasePlaybook$$ShouldEvaluate` en fait un TIRAGE. Le
natif ne propose donc 1098 qu'environ un dry-run sur trois ; le probe repete les dry-runs et
l'accord se lit sur l'ENSEMBLE des cibles proposees au moins une fois (jamais sur un tirage isole).

PORTEUR : les deux seuls porteurs de 1098 sont un SUMMON SANS invocateur (`eldarSmnGuardian`) et un
npc, tous deux refuses par `buildNormalizedBC` -> GREFFE de l'ability sur `eldarAutarch`
(`case-92` §5bis). Ce que la greffe ne couvre pas est nomme dans `case-27` §Non couvert.

ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[2]                 # scripts/python
sys.path.insert(0, str(PYDIR))

import probe_27_4g_plasma_grenade_ab as AB                  # noqa: E402

PLASMA_GRENADE = AB.PLASMA_GRENADE
TIRAGES = 18


@pytest.fixture(scope="module")
def rows():
    rid = AB.build()
    try:
        yield AB.run_ab(rid, engine=True, tirages=TIRAGES)
    finally:
        try:
            AB.L._rpc("disposeRunner", [{"runnerId": rid}])
        except Exception:                                   # noqa: BLE001
            pass


def test_native_actually_casts_plasma_grenade(rows):
    """EXERCICE : sans un bras ou le natif joue REELLEMENT 1098, ce test ne mesure rien."""
    assert any(AB._native_1098_targets(r) for r in rows.values()), (
        "le natif n'a jamais propose 1098 -- montage non exerce, l'accord des bras ne prouve rien")


def test_setup_moves_were_applied(rows):
    """Le compte d'ennemis adjacents suit bien le montage (0, 1, 2). Un `act move` REFUSE aurait
    laisse les trois bras identiques et l'accord serait vide (piege mesure le 2026-07-30)."""
    assert rows["C0"]["n_live"][AB.A_VID] == 0
    assert rows["C1"]["n_live"][AB.A_VID] == 1
    assert rows["C2"]["n_live"][AB.A_VID] == 2


def test_c0_target_is_legal_so_the_absence_is_the_veto(rows):
    """En C0 la cible principale EST une cible legale du natif et sa `pairUtility` est largement
    positive : l'absence de 1098 ne peut donc pas venir du CIBLAGE, seulement du veto du custom."""
    a_id = rows["C0"]["ids"][AB.A_VID]
    assert a_id in rows["C0"]["legal"], (
        "la cible n'est pas legale en C0 -- l'absence de 1098 serait un fait de ciblage, pas le veto")
    assert (rows["C0"]["pairs"][(PLASMA_GRENADE, a_id)] or 0) > 0, (
        "pairUtility(1098) nulle en C0 : le veto ne serait pas discriminant")


def test_veto_native_never_proposes_without_adjacent_enemy(rows):
    """B : n = 0 -> AUCUNE action 1098 sur les %d tirages natifs.""" % TIRAGES
    assert not AB._native_1098_targets(rows["C0"]), (
        "le natif a propose 1098 sans ennemi adjacent -- la sentinelle n'est pas un veto")


def test_engine_matches_native_on_all_arms(rows):
    """Le moteur propose 1098 exactement dans les bras ou le natif l'a proposee au moins une fois,
    et sur la MEME cible."""
    for k, row in rows.items():
        tg = AB._native_1098_targets(row)
        eng_ab, eng_tgt = row["engine"]["on"]
        if tg:
            assert eng_ab == PLASMA_GRENADE and eng_tgt in tg, (
                "bras %s : natif propose 1098 sur %s, moteur %s" % (k, sorted(tg), (eng_ab, eng_tgt)))
        else:
            assert eng_ab != PLASMA_GRENADE, (
                "bras %s : moteur propose 1098 la ou le natif ne le fait JAMAIS" % k)


def test_term_is_linear_not_boolean(rows):
    """C : en C2 le natif prend la cible a `pairUtility` la PLUS FAIBLE parce qu'elle a 2 voisins."""
    a_id, b_id = rows["C2"]["ids"][AB.A_VID], rows["C2"]["ids"][AB.B_VID]
    pa = rows["C2"]["pairs"][(PLASMA_GRENADE, a_id)]
    pb = rows["C2"]["pairs"][(PLASMA_GRENADE, b_id)]
    assert pa < pb, ("montage non discriminant : pair(A)=%s n'est pas < pair(B)=%s -- le "
                     "renversement ne prouverait rien" % (pa, pb))
    assert a_id in AB._native_1098_targets(rows["C2"]), (
        "le natif n'a pas renverse l'argmax par cible -- terme non lineaire, ou montage inerte")
    assert rows["C2"]["engine"]["boolean"] != rows["C2"]["engine"]["on"], (
        "la mutation 'terme BOOLEEN' ne change rien : ce montage ne separe pas lineaire de booleen")


def test_veto_is_necessary(rows):
    """D : veto desarme (custom = 0.0, l'etat du port AVANT ce commit) -> le moteur propose 1098 en
    C0, la ou le natif ne le fait JAMAIS."""
    assert rows["C0"]["engine"]["noveto"][0] == PLASMA_GRENADE, (
        "veto desarme : le moteur ne propose toujours pas 1098 -> la garde ne mord pas, et le port "
        "n'est pas ce qui decide en C0")


def test_pair_utilities_of_the_two_switching_targets_are_bit_identical(rows):
    """Confond de PREDICTION MESURE et NUL sur les DEUX cibles entre lesquelles le natif arbitre.

    Le renversement de C2 se joue entre A et B. Leurs `pairUtility` natives doivent etre
    BIT-IDENTIQUES dans les trois bras -- sinon le basculement pourrait venir d'un ecart de
    prediction et non du terme custom. Mesure : elles le sont (1098 est mono-cible cote prediction
    de paire, et ni A ni B ne bougent apres leur placement).

    ⚠ L'enonce ne s'etend PAS a la 3e cible : C est DEPLACEE entre C1 et C2 (elle passe de sa tuile
    d'ecart a un voisin de A), donc sa propre paire bouge -- MESURE, 15.056975 -> 10.045359. Exiger
    son invariance ferait echouer le test pour une raison qui n'a rien a voir avec le custom."""
    a_id, b_id = rows["C0"]["ids"][AB.A_VID], rows["C0"]["ids"][AB.B_VID]
    for k in ("C1", "C2"):
        for tgt, who in ((a_id, "A"), (b_id, "B")):
            assert rows[k]["pairs"][(PLASMA_GRENADE, tgt)] == \
                rows["C0"]["pairs"][(PLASMA_GRENADE, tgt)], (
                    "bras %s : pairUtility(1098, %s=u%d) a bouge -- l'A/B ne mesure plus le seul "
                    "custom" % (k, who, tgt))
