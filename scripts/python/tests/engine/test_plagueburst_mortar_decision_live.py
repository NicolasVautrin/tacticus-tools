"""PlagueburstMortar (1169) -- face DECISION a cible TUILE, confrontee au LIVE (case-302, tranche 1).

CE QUE CE TEST GARDE, et pourquoi il ne peut pas passer par accident :

A. **La ROUTE a cibles TUILE existe et sert.** Le bras `noroute` (registre `NONATTACK_PLAYBOOKS`
   vide) rejoue la decision dans l'etat d'AVANT le port : s'il rendait la meme chose, l'accord
   viendrait d'ailleurs. Le bras `best_attack` verifie l'autre porte : `_best_attack` consomme
   `ranked`, or les evals natives de 1169 ont `rankCount = 0` sur toute cible UNITE.
B. **Le terme custom est NECESSAIRE** : force a 0, le moteur DIVERGE (il retombe sur l'attaque
   normale, que le natif ne choisit pas).
C. **La cible emise est bien une ENTITE-TUILE** : l'id retenu appartient au `boardGraph`, pas a
   `decisionView.units` -- c'est le meme id que celui de l'`ActiveAbilityMessage` natif.
D. **La forme est LINEAIRE en n**, pas booleenne ni constante : le custom releve cible par cible
   prend PLUSIEURS valeurs distinctes (`10 x |ennemis adjacents a la tuile visee|`).
E. **Le montage n'est pas complaisant** : le bras TEMOIN (sans `--hp-target` gonfle) verifie que le
   natif NE caste PAS 1169 quand l'attaque normale vaut mieux -- et que le moteur le suit. Sans ce
   bras, un port qui casterait 1169 *toujours* passerait le test A/B/D.
F. **Le COOLDOWN est purge avant de conclure.** 1169 arrive avec `RemainingCooldownTurns = 1` : au
   tour du build elle est INDISPONIBLE, et c'est ce qui avait fait lire « le natif ne genere pas
   l'action pour une cible tuile » (`probe_27_4g_plagueburst_route.py`). Le test assert le cooldown
   purge AVANT de comparer -- un montage qui mesurerait a nouveau une ability indisponible ECHOUE
   au lieu de rendre un faux verrou.

PORTEUR : 1169 est portee par `deathCrawler` (MACHINE OF WAR, hors `decisionView.units`). Le montage
la GREFFE sur `deathTyphus` (Death Guard, DANS le pool rank 17) -- le natif charge le playbook PAR
ABILITY, jamais par unite (`case-92` §5bis).

ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[2]                 # scripts/python
sys.path.insert(0, str(PYDIR))

import probe_302_tile_target_route as AB                    # noqa: E402

PB = AB.PLAGUEBURST                                          # 1169
NORMAL = 69


@pytest.fixture(scope="module")
def arms():
    rids = []
    try:
        a = AB.measure(400000, "rs_302_a.json")             # regime ou 1169 domine
        rids.append(a["rid"])
        b = AB.measure(0, "rs_302_b.json")                  # TEMOIN : l'attaque normale domine
        rids.append(b["rid"])
        yield {"pb": a, "temoin": b}
    finally:
        for rid in rids:
            AB.dispose(rid)


def test_cooldown_is_purged_before_measuring(arms):
    """F : sans cette purge, « le natif ne propose pas 1169 » ne mesure que l'indisponibilite."""
    for k, r in arms.items():
        assert r["cooldown"] in (None, 0), (
            "bras %s : 1169 encore en cooldown (%s) -- la mesure ne dit rien du ciblage"
            % (k, r["cooldown"]))


def test_engine_matches_native_on_both_arms(arms):
    """Le moteur reproduit le choix NATIF (ability ET cible) dans les deux bras."""
    for k, r in arms.items():
        assert r["engine"]["on"] == r["native"], (
            "bras %s : moteur %s != natif %s" % (k, r["engine"]["on"], r["native"]))


def test_native_casts_the_mortar_only_in_the_favourable_arm(arms):
    """E : le montage SEPARE bien les deux regimes -- sinon il ne mesure rien."""
    assert arms["pb"]["native"][0] == PB, (
        "le natif ne caste pas 1169 dans le regime favorable -- le montage ne mord plus")
    assert arms["temoin"]["native"][0] != PB, (
        "le natif caste 1169 MEME dans le regime temoin -- l'accord du bras favorable ne prouve rien")


def test_tile_route_is_necessary(arms):
    """A : sans la route non-attaque, le moteur ne PEUT PAS proposer 1169."""
    e = arms["pb"]["engine"]
    assert e["on"][0] == PB
    assert e["noroute"][0] != PB, (
        "le moteur propose 1169 SANS la route -- une autre voie la fait passer, la mesure ne prouve "
        "rien sur le deblocage")


def test_best_attack_can_never_yield_the_mortar(arms):
    """A (2e porte) : `_best_attack` rend l'attaque normale, jamais 1169 (`rankCount = 0` partout)."""
    for k, r in arms.items():
        assert r["engine"]["best_attack_ability"] != PB, (
            "bras %s : `_best_attack` a rendu 1169" % k)


def test_custom_term_is_necessary(arms):
    """B : force a 0, le custom fait DIVERGER le moteur du natif au bras favorable."""
    e = arms["pb"]["engine"]
    assert e["zero"] != e["on"], "custom force a 0 ne change rien -> le terme est inerte"


def test_target_is_a_tile_entity(arms):
    """C : la cible retenue est un id de TUILE (boardGraph), pas un id d'unite."""
    r = arms["pb"]
    tid = r["engine"]["on"][1]
    assert tid in r["engine"]["targets"], (
        "la cible %s n'est pas dans l'ensemble eligible TUILE %s" % (tid, r["engine"]["targets"][:8]))
    assert tid != r["caster"]


def test_eligible_set_is_the_native_tile_domain(arms):
    """L'ensemble eligible est NON VIDE et large (domaine `GetTilesInRange`), pas un singleton
    bricole : avant la tranche, `eligible_targets` filtrait `kind == "unit"` et rendait []."""
    assert len(arms["pb"]["engine"]["targets"]) > 10


def test_unit_domain_is_empty_which_is_exactly_the_state_before_the_fix(arms):
    """VUE ROUGE, MESUREE et non supposee : avec le domaine force a UNITE (le code d'avant la
    tranche), `eligible_targets` rend un ensemble VIDE -> `nonattack_candidates` sort au `continue`
    et l'action 1169 n'existe simplement pas cote moteur.

    Ce test est le pendant exact de `test_tile_route_is_necessary` : l'un coupe la ROUTE, l'autre
    coupe le DOMAINE. Les deux doivent mordre, sinon le port passerait par une porte non identifiee."""
    for k, r in arms.items():
        assert r["engine"]["targets_unit_domain"] == [], (
            "bras %s : le domaine UNITE rend %s -- 1169 aurait donc eu une route AVANT la tranche, "
            "et le verrou mesure par case-27 n'etait pas celui-la"
            % (k, r["engine"]["targets_unit_domain"][:8]))


def test_custom_is_linear_not_boolean(arms):
    """D : le custom prend plusieurs valeurs distinctes sur le domaine (0, W, 2W...)."""
    vals = sorted({c for _t, c in arms["pb"]["engine"]["per_target"]})
    assert len(vals) > 2, (
        "le custom ne prend que %s valeur(s) sur les %d tuiles -- soit le selecteur est mort, soit "
        "le montage n'offre aucun contraste d'adjacence"
        % (vals, len(arms["pb"]["engine"]["targets"])))
    step = min(v for v in vals if v > 0)
    assert all(abs(v % step) < 1e-9 for v in vals), (
        "les valeurs %s ne sont pas des multiples de %s -- la forme n'est pas `n x W`" % (vals, step))
