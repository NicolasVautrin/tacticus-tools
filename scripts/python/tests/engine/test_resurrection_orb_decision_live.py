"""ResurrectionOrb (1009, Anuphet `necroOverlord`) -- face DECISION, confrontee au LIVE.

CE QUE CE TEST GARDE (et pourquoi il ne peut pas passer par accident) :

A. **La ROUTE non-attaque existe et sert.** 1009 n'a pas de `damageProfile` -> `make_damage_predictions`
   rend `[]` et `calculate_action_utility` rend `None` : `_best_attack` ne peut PAS la produire. Le
   bras `noroute` (registre `NONATTACK_PLAYBOOKS` vide) rejoue la decision dans l'etat d'AVANT le
   port -- s'il rend la MEME chose, le port est inerte et l'accord vient d'ailleurs.
   ⚠ Contrairement a une formulation repandue, 1009 **EST** listee dans `ctx.plans` cote LIVE
   (`decisionView.attackPlans`), a `rankCount = 0` et sur des ENNEMIS -- alors que la cible retenue
   est le CASTER. Le critere garde ici est donc « `_best_attack` ne peut pas la rendre », pas
   « absente de `ctx.plans` » (mesure #289).
B. **Le terme custom est NECESSAIRE** : force a 0, le moteur DIVERGE du natif au bras MORT.
C. **Le forfait resurrection est CAUSAL** : les deux bras sont identiques (meme seed, meme board, meme
   tour adverse joue) a UNE chose pres -- l'allie `necroWarden` (Hero + LivingMetal => Mechanical) est
   mort ou non. Le natif ATTAQUE quand il est vivant et CASTE 1009 quand il est mort.
D. **La forme est LINEAIRE en `numSummons`, pas constante** : le custom releve tuile par tuile prend
   PLUSIEURS valeurs distinctes (il vaut `10 x min(maxSummons, libres - hasResurrectTarget)`).
E. **Les etages sont mesures separement** (`nResurrect`, `nTiles`, `maxSummons`, `numSummons`,
   `turnsStarted`) : une divergence se localise, au lieu de se compenser dans un total.

La `pairUtility(69)` native de l'appat est BIT-IDENTIQUE d'un bras a l'autre : le confond de
prediction est MESURE et NUL -- seul le terme custom peut expliquer la bascule.

Aucun scalaire de gameplay n'est fige : les poids viennent de la BC re-synthetisee, l'encadrement des
`pairUtility` natives du montage.

PORTEUR : `necroOverlord` est DANS le pool rank 17 (`rl_duel.py build --list-pool`) -- aucune
injection de catalogue n'est necessaire.

ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[2]                 # scripts/python
sys.path.insert(0, str(PYDIR))

import probe_289_resurrection_orb as AB                      # noqa: E402

ORB = AB.ORB


@pytest.fixture(scope="module")
def rows():
    rv = rm = None
    try:
        rv = AB.build_vivant()
        rm = AB.build_mort()
        yield AB.run_arms(rv, rm, engine=True)
    finally:
        for rid in (rv, rm):
            if rid is None:
                continue
            try:
                AB.L._rpc("disposeRunner", [{"runnerId": rid}])
            except Exception:                               # noqa: BLE001
                pass


def test_engine_matches_native_on_both_arms(rows):
    """Le moteur reproduit le choix NATIF (ability ET cible) dans les deux bras."""
    for k, row in rows.items():
        assert row["engine"]["on"] == row["native"], (
            "bras %s : moteur %s != natif %s" % (k, row["engine"]["on"], row["native"]))


def test_native_switches_on_resurrect_target(rows):
    """CAUSALITE : le natif attaque quand l'allie est VIVANT et caste 1009 quand il est MORT.

    C'est la seule difference entre les deux montages -- si le natif ne bascule pas, le montage ne
    mesure rien et on ne conclut pas (plutot que de lire l'accord comme une preuve)."""
    assert rows["vivant"]["native"][0] != ORB, (
        "le natif caste deja 1009 SANS cible resurrectable -- le montage ne separe pas les deux bras")
    assert rows["mort"]["native"][0] == ORB, (
        "le natif ne caste pas 1009 avec une cible resurrectable -- le forfait 90 ne mord pas ici")


def test_resurrect_stage_flips(rows):
    """ETAGE : `Count(GetPossibleResurrectTargets)` passe de 0 a 1 -- l'allie mort est bien reconnu
    Hero ET mecanique (`HasTrait(0x10) & IsMechanical`)."""
    assert rows["vivant"]["engine"]["stages"]["nResurrect"] == 0
    assert rows["mort"]["engine"]["stages"]["nResurrect"] == 1


def test_max_summons_counts_the_dead_mechanical_ally(rows):
    """ETAGE : `maxSummons` = `Count(amis MORTS mecaniques) + TURNS_STARTED` gagne EXACTEMENT un cran
    quand l'allie meurt (les deux bras ont joue le meme nombre de tours)."""
    sv, sm = rows["vivant"]["engine"]["stages"], rows["mort"]["engine"]["stages"]
    assert sv["turnsStarted"] == sm["turnsStarted"], (
        "les deux bras ne sont pas au meme round -- `maxSummons` differe pour une autre raison")
    assert sm["maxSummons"] == sv["maxSummons"] + 1


def test_one_tile_is_reserved_for_the_resurrection(rows):
    """`GetNumSummonsFormula` = `If(hasResurrectTarget, Count(tiles) - 1, Count(tiles))` : a nombre de
    tuiles EGAL, le bras MORT summon UN de moins -- la tuile de resurrection est reservee."""
    sv, sm = rows["vivant"]["engine"]["stages"], rows["mort"]["engine"]["stages"]
    assert sv["nTiles"] == sm["nTiles"], "le nombre de hex libres differe : la comparaison est faussee"
    assert sm["numSummons"] == min(sm["maxSummons"], sm["nTiles"] - 1)
    assert sv["numSummons"] == min(sv["maxSummons"], sv["nTiles"])


def test_custom_is_not_constant_across_tiles(rows):
    """LINEARITE : le custom depend du nombre de hex libres autour de la TUILE CANDIDATE, donc il
    prend plusieurs valeurs sur le balayage. Un terme constant (ou purement booleen) est exclu."""
    vals = {c for _T, c, _a in rows["mort"]["engine"]["per_tile"]}
    assert len(vals) > 1, (
        "le custom vaut %s sur TOUTES les tuiles -- soit l'ancrage `CasterTile` est mort, soit le "
        "montage n'offre aucune tuile de voisinage different" % vals)


def test_custom_term_is_necessary(rows):
    """Force a 0, le custom fait DIVERGER le moteur du natif au bras MORT."""
    e = rows["mort"]["engine"]
    assert e["zero"] != e["on"], "custom force a 0 ne change rien -> le terme est inerte"


def test_nonattack_route_is_necessary(rows):
    """Sans la route non-attaque, le moteur ne PEUT PAS proposer 1009."""
    e = rows["mort"]["engine"]
    assert e["on"][0] == ORB
    assert e["noroute"][0] != ORB, (
        "le moteur propose 1009 SANS la route non-attaque -- une autre voie la fait passer, "
        "la mesure ne prouve rien sur le deblocage")


def test_best_attack_can_never_yield_the_orb(rows):
    """VERROU : `calculate_action_utility` rend None (aucune prediction de degat) dans les deux bras,
    et `_best_attack` rend l'attaque normale -- jamais 1009."""
    for k, row in rows.items():
        v = row["engine"]["verrou"]
        assert v["action_utility_is_none"], "bras %s : 1009 produit une utilite d'ACTION d'attaque" % k
        assert v["best_attack_ability"] != ORB, "bras %s : `_best_attack` a rendu 1009" % k


def test_target_is_the_caster(rows):
    """SELF-CAST STRICT (`TargetIsCaster` du masque) : la seule cible eligible est le caster."""
    for k, row in rows.items():
        assert row["engine"]["targets"] == [row["caster"]], (
            "bras %s : cibles eligibles %s != [caster %s]"
            % (k, row["engine"]["targets"], row["caster"]))


def test_native_pair_utility_is_bit_identical_across_arms(rows):
    """Confond de PREDICTION mesure et NUL : la paire native de l'appat ne bouge pas d'un bras a
    l'autre -- la bascule ne peut donc pas venir de l'etage degat."""
    assert rows["vivant"]["pair"] == rows["mort"]["pair"], (
        "la pairUtility native a bouge (%r != %r) : les deux bras different par autre chose que la "
        "mort de l'allie" % (rows["vivant"]["pair"], rows["mort"]["pair"]))
