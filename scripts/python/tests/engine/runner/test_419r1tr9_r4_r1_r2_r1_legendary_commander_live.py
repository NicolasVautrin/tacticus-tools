"""GARDE de `LegendaryCommander_ExtraHits` (1395) -- #419-r1-tr9-r4-r1-r2-r1.

Le PROBE (`probe_419r1tr9_r4_r1_r2_r1_legendary_commander.py`) MESURE ; ce fichier GARDE. Il monte
les deux bras UNE fois (fixture `scope="module"`) et asserte, cran par cran :

  1. MONTAGE, mesure 100 % NATIVE : l'effet 1395 est sur `custoTrajann`, et le nb de coups d'une
     attaque d'ABILITY (famille ATTACK) sur un ennemi adjacent a Trajann passe de `base` a
     `base + ConfigVar(0x2f = nrOfHits)` DES LORS QUE Trajann a caste une active ce tour. Le bras
     `idle` (Trajann inactif) est le TEMOIN : meme board, meme seed, meme geometrie, meme cast.
  2. ACCORD port/natif sur les QUATRE mesures (2 bras x 2 attaques).
  3. CONTRE-EPREUVES, une PAR AXE du trigger natif : chacune doit MORDRE de `-nrOfHits` dans le bras
     `armed` et etre INERTE dans `idle`. Le mutant patche la METHODE de la classe d'effet, jamais le
     registre `EFFECT_CLASSES` (la scene est deja hydratee -> le mutant-registre rend un vert
     menteur, mesure #419-r1-tr9-r4-r1-r2).
  4. << FIRST ATTACK >> : deux attaques CONSECUTIVES dans la MEME fenetre de couverture (regime non
     jouable cote natif -- une unite n'a qu'une action par tour) tombent a `[base+bonus, base]`, et
     le mutant qui neutralise `!IsInPersistentDataList` les remonte a `[base+bonus, base+bonus]`.
  5. RECIPROQUE MESUREE : au TOUR SUIVANT, si Trajann RE-caste, le natif RE-DONNE le bonus. Le
     << first attack >> est donc PAR FENETRE DE COUVERTURE (`$$RevertInternal` purge la marque quand
     la cible sort des targets), pas par bataille.
"""
from __future__ import annotations

import pytest

import probe_419r1tr9_r4_r1_r2_r1_legendary_commander as LC


@pytest.fixture(scope="module")
def lc(live_session):
    """Les DEUX bras, un runner a la fois, dispose par le probe lui-meme."""
    res = LC.run(verbose=False)
    for arm in ("armed", "idle"):
        if (res.get(arm) or {}).get("error"):
            pytest.fail(f"[{arm}] montage NON INSTALLE : {res[arm]['error']}", pytrace=False)
    return res


def test_montage_installed(lc):
    """Cran 1a : l'effet 1395 EXISTE sur Trajann. Sans lui, rien d'autre n'est lisible."""
    for arm in ("armed", "idle"):
        assert "LegendaryCommander_ExtraHits" in (lc[arm]["trajann_effects"] or []), (
            f"[{arm}] 1395 absent de decisionView : {lc[arm]['trajann_effects']}")


def test_native_bonus_mordu(lc):
    """Cran 1b : mesure NATIVE seule -- `armed` == `idle` + `ConfigVar(0x2f = nrOfHits)`.
    L'oracle de la magnitude est `ability_var`, jamais un litteral."""
    bonus = lc["oracle"]["legendary_nrOfHits"]
    base = lc["oracle"]["flail_nrOfHits"]
    assert bonus > 0, f"nrOfHits lu au gameconfig = {bonus} (setup non discriminant)"
    assert lc["idle"]["hits_1"] == base, (
        f"temoin : le natif rend {lc['idle']['hits_1']} coups sans cast de Trajann, "
        f"oracle gameconfig FlailSwing.nrOfHits={base}")
    assert lc["armed"]["hits_1"] == base + bonus, (
        f"natif armed={lc['armed']['hits_1']} != base({base}) + nrOfHits({bonus})")


def test_port_agrees_with_native(lc):
    """Cran 2 : accord port/natif sur les 4 mesures."""
    for key, (port, native) in (lc["verdict"]["agreement"] or {}).items():
        assert port == native, f"{key} : port={port} != natif={native}"


def test_mutants_bite_where_they_should(lc):
    """Cran 3 : chaque axe du trigger MORD dans `armed`, et est INERTE dans `idle`."""
    bonus = lc["oracle"]["legendary_nrOfHits"]
    armed = lc["verdict"]["mutants"]["armed"]
    for name, d in armed.items():
        if name == "no_persistent_gate":
            # Structurellement inerte sur la PREMIERE attaque : le sac est encore vide (le marquage
            # a lieu APRES, sur `On(0xa = AttackDamageAttack)`). Son cran est `test_first_attack`.
            assert d == 0, f"mutant {name} : deplacement {d} attendu 0 sur la 1re attaque"
            continue
        assert d == -bonus, f"mutant {name} : deplacement {d} != -{bonus} (il ne mord pas)"
    for name, d in (lc["verdict"]["mutants"]["idle"] or {}).items():
        assert d == 0, f"mutant {name} : deplacement {d} != 0 dans le bras temoin (il deborde)"


def test_first_attack_within_window(lc):
    """Cran 4 : `!IsInPersistentDataList` -- deux attaques CONSECUTIVES, meme fenetre."""
    base, bonus = lc["oracle"]["flail_nrOfHits"], lc["oracle"]["legendary_nrOfHits"]
    assert lc["verdict"]["pair"] == [base + bonus, base], (
        f"port pair={lc['verdict']['pair']} != [{base + bonus}, {base}] (le marquage ne ferme pas)")
    assert lc["verdict"]["pair_no_persist"] == [base + bonus, base + bonus], (
        f"contre-epreuve : pair_no_persist={lc['verdict']['pair_no_persist']} "
        f"!= [{base + bonus}, {base + bonus}] (le mutant du gate persistant ne mord pas)")
    assert (lc["idle"]["port_pair"] or []) == [base, base], (
        f"temoin : idle pair={lc['idle']['port_pair']} != [{base}, {base}]")


def test_marker_dies_with_the_coverage_window(lc):
    """Cran 5 : au TOUR SUIVANT, Trajann RE-caste -> le natif RE-DONNE le bonus, et le port le suit.
    C'est ce qui a impose le port de `$$RevertInternal` (la marque part avec la sortie de target)."""
    base, bonus = lc["oracle"]["flail_nrOfHits"], lc["oracle"]["legendary_nrOfHits"]
    assert lc["armed"]["hits_2"] == base + bonus, (
        f"natif 2e attaque (apres re-cast) = {lc['armed']['hits_2']} != {base + bonus} : "
        f"le << first attack >> ne serait alors PAS par fenetre de couverture")
    assert lc["armed"]["port_hits_2"] == lc["armed"]["hits_2"], (
        f"port {lc['armed']['port_hits_2']} != natif {lc['armed']['hits_2']} sur la 2e attaque")
    assert lc["idle"]["hits_2"] == base, f"temoin idle 2e attaque = {lc['idle']['hits_2']} != {base}"
