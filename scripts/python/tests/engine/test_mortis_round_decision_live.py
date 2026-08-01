"""MortisRound (1004, `ultraEliminatorSgt` "Certus") -- terme `CalculateCustomUtility`, LIVE.

CE QUE CE TEST GARDE, et pourquoi il ne peut pas passer par accident :

A. **Le terme natif est le GAIN d'utilite de TUILE que le PUSH inflige a la cible**, tronque vers
   `int` -- `IdunBattle.AI.Playbook.Loki.MortisRoundPlaybook$$CalculateCustomUtility` =
   `(Fix64)(int) Playbook<T>$$GetTargetUtilityDiffOnDisplace(...).value`. Sur MC1_67 le montage
   pose DEUX geometries dont seule l'ELEVATION de la tuile d'arrivee change :
     geom A : cible sur elev 4 (le MAX du board) poussee vers elev 3 -> 50 - 30 = **20**
     geom B : cible sur elev 3 poussee vers elev 2                   -> 30 - 20 = **10**
   Les deux casters sont a elevation 3 et a distance 2 de leur cible : le terme `Tile(7)` de la
   tuile de tir ET les predictions sont IDENTIQUES entre A et B.

B. **Le montage est A L'EQUILIBRE, et l'ecart est MESURE, pas suppose.** `--hp-target 1800` place
   `ecart = pair69 + 1 - pair1004` a ~11.93, DANS (10, 20) : la geom A (20) fait basculer le natif
   sur 1004, la geom B (10) ne le fait PAS. C'est ce qui distingue une magnitude de 20 d'une
   magnitude de 10 -- un terme CONSTANT, quelle que soit sa valeur, ne peut pas produire ces deux
   resultats opposes a paires identiques.

C. **Deux leviers d'annulation, chacun teste separement** :
   * OCCUPATION -- un appat ALLIE (jamais ciblable, sans trait `Steppable`) occupe la tuile
     d'arrivee : `DSLSelectors.EmptyOrHasSteppableUnit` vide l'arc -> custom 0, le natif revient
     sur 69 ;
   * `IsDisplaceable` -- une unite `BigTarget` prend EXACTEMENT la tuile de la geom A, arc libre :
     `IdunBattle.Entities.UnitExtensions$$IsDisplaceable` refuse -> custom 0.

D. **TROIS mutations adversariales** rejouent la decision moteur avec une piece du port RETIREE.
   Chacune doit DIVERGER du natif quelque part, sinon le montage ne teste pas cette piece :
   `zero` (terme absent), `no_occupancy` (filtre d'occupation retire), `no_displaceable` (gate de
   trait retire).

CONFONDS NEUTRALISES, tous MESURES par le probe :
  * les `pairUtility` natives (69 et 1004) sont BIT-IDENTIQUES sur les quatre bras a cible
    deplacable -- le confond de prediction est mesure et nul ;
  * l'appat est un ALLIE : il ne peut pas devenir une cible, donc il ne deplace aucun autre terme ;
  * les placements STRUCTURANTS (caster, cible, appat sur la tuile d'arc) sont verifies a
    l'EGALITE, les relegations par une distance minimale -- un `act move` refuse ne degrade donc
    pas le montage en silence.

Porteur `ultraEliminatorSgt` : HERO present dans `rl_duel build --list-pool`, aucun
`catalog_inject` ni greffe.

ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[2]                 # scripts/python
sys.path.insert(0, str(PYDIR))

import probe_27_r3_mortis_round_ab as AB                    # noqa: E402

# Action attendue par bras : 1004 quand le custom (20) domine l'ecart, 69 sinon.
WANT = {"a-libre": 1004, "a-bloque": 69, "b-libre": 69, "b-bloque": 69, "bigtarget": 69}
CUSTOM = {"a-libre": 20.0, "a-bloque": 0.0, "b-libre": 10.0, "b-bloque": 0.0, "bigtarget": 0.0}


@pytest.fixture(scope="module")
def rows():
    data, rid = AB.scenario()
    try:
        yield data
    finally:
        if rid is not None:
            try:
                AB.L._rpc("disposeRunner", [{"runnerId": rid}])
            except Exception:                               # noqa: BLE001
                pass


def test_montage_has_no_prediction_confound(rows):
    """Les `pairUtility` natives sont BIT-IDENTIQUES sur les quatre bras a cible deplacable. Sans
    cela l'A/B melangerait le custom a une derive de prediction et ne conclurait rien."""
    ref = rows["a-libre"]["pairs"]
    bad = [k for k in ("a-bloque", "b-libre", "b-bloque") if rows[k]["pairs"] != ref]
    assert not bad, (
        "les paires natives BOUGENT entre les bras %s (ref=%r) -- confond de prediction present, "
        "l'ecart mesure n'est plus attribuable au seul terme custom" % (bad, ref))


def test_montage_sits_in_the_flip_window(rows):
    """`ecart = pair69 + 1 - pair1004` doit tomber DANS (10, 20) : c'est la seule fenetre ou une
    magnitude de 20 bascule le natif et une magnitude de 10 ne le bascule pas. Hors de cette
    fenetre, tous les bras rendraient la meme action et le test serait vide."""
    gap = rows["a-libre"]["gap"]
    assert 10.0 < gap < 20.0, (
        "ecart natif = %.6f, hors de la fenetre (10, 20) -- le montage ne peut plus discriminer "
        "une magnitude de 20 d'une magnitude de 10 ; re-calibrer --hp-target" % gap)


def test_native_flips_exactly_where_the_formula_predicts(rows):
    """LE VERDICT : le natif prend 1004 dans le SEUL bras ou le gain d'elevation vaut 20, et
    l'attaque normale dans les quatre autres."""
    got = {k: rows[k]["native"][0] for k in AB.ARMS}
    assert got == WANT, (
        "choix natif %s != attendu %s -- la formule `max(0, u0 - uN) tronque` ne decrit plus le "
        "comportement natif" % (got, WANT))


def test_ported_term_matches_the_elevation_arithmetic(rows):
    """Le terme porte vaut EXACTEMENT ce que l'arithmetique d'elevation impose, bras par bras.
    (20 = 10*4 + HighestElevation(10) - 10*3 ; 10 = 10*3 - 10*2 ; 0 quand l'arc est vide.)"""
    bad = {k: rows[k]["custom"] for k in AB.ARMS if rows[k]["custom"] != CUSTOM[k]}
    assert not bad, "termes portes hors attendu %s (attendu %s)" % (bad, CUSTOM)


def test_engine_matches_native_on_all_arms(rows):
    """Accord moteur <-> natif dans les CINQ bras."""
    bad = [(k, rows[k]["engine"], rows[k]["native"]) for k in AB.ARMS
           if tuple(rows[k]["engine"]) != tuple(rows[k]["native"])]
    assert not bad, "bras divergents (bras, moteur, natif) : %s" % bad


@pytest.mark.parametrize("mutant", sorted(AB.MUTANTS))
def test_each_mutation_is_visible(rows, mutant):
    """MUTATIONS ADVERSARIALES : chaque piece du port RETIREE doit faire diverger le moteur du
    natif dans au moins un bras. Un mutant invisible signifie que le montage ne teste pas cette
    piece -- l'accord mesure ne prouverait alors rien SUR ELLE."""
    hit = [k for k in AB.ARMS if rows[k]["mutants"][mutant] != tuple(rows[k]["native"])]
    assert hit, (
        "la mutation `%s` rend EXACTEMENT le meme choix que le natif dans les cinq bras : le "
        "montage ne discrimine pas cette piece du port, re-calibrer avant de conclure" % mutant)
