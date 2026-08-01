"""#437 -- un TIR D'OVERWATCH consomme l'armure Terminator, CONFRONTE au NATIF.

Residu structurel laisse par #432 : le natif emet `On(9 = Attack)` depuis le noeud DSL `Attack(...)`
(`IdunBattle.Entities.Behaviours.AttackBehaviour$$Execute` -> `processor.FinishAttack` slot 0x3b ->
`IdunBattle.Operations.FinishAttackOperation$$Execute`), que TOUTE attaque traverse -- y compris
celle qu'un TRIGGER declenche, le tir d'overwatch etant
`Overwatch_AutoAttackEffect$$GetAttackBehaviour = UseActiveAbility(NormalAttack)`. Le port, lui,
emettait `On(9)` au niveau MESSAGE (`DamageHandler.visit_AttackUnitMessage`), que le tir d'overwatch
ne traverse pas : l'armure restait ARMEE apres un tir d'overwatch, et l'attaque suivante etait
reduite a tort.

CE QUE CE TEST GARDE :

  1. **LE NATIF DIT BIEN CA** -- le flag `EffectComponent.IsActive @+0x5c` du porteur (lu par
     `decisionView({includeInactive:true})`) vaut `True` avant le move et `False` apres le tir
     d'overwatch. Observable BINAIRE, sans arithmetique.
  2. **LE PORT REPRODUIT** -- le meme move rejoue OFFLINE sur le meme `State` et le meme flux RNG
     rend la meme trajectoire de flag ET le meme degat, a l'unite.
  3. **LE FOYER PORTE LE RESULTAT** -- `finish_attack_triggers` neutralise a la sortie de
     `AttackDamageOperation.execute` (= l'etat d'`origin/master` pour une attaque declenchee par un
     trigger), le flag ne tombe PLUS : la garde ROUGIT. La mutation est VERIFIEE avoir MORDU avant
     qu'on lise ce verdict (VERT serait le resultat suspect), et son degat est INCHANGE -- elle ne
     deborde pas du seul vecteur d'evenement qu'elle vise.
  4. **LE REGIME A DEUX TIRS REND LE DEGAT OBSERVABLE** -- un flag n'est pas un degat. Avec DEUX
     overwatchers ennemis couvrant la tuile d'arrivee, le MEME move declenche deux tirs : le 1er est
     REDUIT (armure armee), le 2e est PLEIN (armure consommee par le 1er). Mesure `MC1_67`/seed 4321
     (`eldarRanger` + `admecDestroyer`) : natif **15 280**, port **15 280**, port sans le foyer
     **4 828** -- soit **10 452 points de degat escamotes** sur un seul move. Le nombre de tirs est
     COMPTE (desarmement 1009 de chaque overwatcher, `On(10) & OwnerIsActor -> DeactivateEffect`),
     jamais suppose : la geometrie n'en amene pas toujours deux.

Montage, mesure et verdicts : `scripts/python/probe_437_overwatch_consumes_armour.py`. ASCII only.
"""
from __future__ import annotations

import pytest

import probe_437_overwatch_consumes_armour as P


@pytest.fixture(scope="module")
def overwatch_armour_case(live_session):
    """Les DEUX bras (foyer normal / foyer NEUTRALISE). Chaque bras monte SON runner et le DISPOSE
    en sortie de `run()`. Portee MODULE : les trois tests partagent la mesure."""
    base = P.run(verbose=True)
    if "error" in base:
        pytest.fail("montage #437 NON INSTALLE (bras normal) : %s" % base["error"], pytrace=False)
    mut = P.run(mutate=True, verbose=True)
    if "error" in mut:
        pytest.fail("montage #437 NON INSTALLE (bras mutate) : %s" % mut["error"], pytrace=False)
    if base["native"] != mut["native"]:
        pytest.fail("les deux bras n'ont pas la MEME mesure NATIVE (%s vs %s) -- l'A/B ne serait "
                    "plus attribuable au seul foyer d'emission"
                    % (base["native"], mut["native"]), pytrace=False)
    return base, mut


def test_native_overwatch_consumes_armour(overwatch_armour_case):
    """(1) Le NATIF : l'armure est ARMEE avant le move et DESARMEE apres le tir d'overwatch."""
    base, _ = overwatch_armour_case
    fails = [x for x in P.verdict(base) if x.startswith(("[natif]", "[montage]"))]
    assert not fails, "cycle NATIF #437 :\n  - " + "\n  - ".join(fails)


def test_port_matches_native(overwatch_armour_case):
    """(2) Le PORT : meme trajectoire de flag et meme degat, a l'unite."""
    base, _ = overwatch_armour_case
    fails = [x for x in P.verdict(base) if x.startswith("[port]")]
    assert not fails, "port vs natif #437 :\n  - " + "\n  - ".join(fails)


def test_emission_site_is_load_bearing(overwatch_armour_case):
    """(3) CONTRE-EPREUVE : foyer `On(9)` neutralise -> le flag ne tombe plus. Le premier verdict
    de la liste verifie que la MUTATION A MORDU ; sans lui, un bras vert ne prouverait rien."""
    base, mut = overwatch_armour_case
    fails = [x for x in P.verdict(base, mut) if x.startswith("[mutation]")]
    assert not fails, "discriminance #437 :\n  - " + "\n  - ".join(fails)


@pytest.fixture(scope="module")
def two_shot_case(live_session):
    """Le regime a DEUX TIRS : deux overwatchers ennemis couvrent la tuile d'arrivee, donc le MEME
    move part en deux tirs -- 1er REDUIT, 2e PLEIN. C'est ce qui fait du DEGAT un observable."""
    ows = [P.OVERWATCHER, "admecDestroyer"]
    base = P.run(verbose=True, overwatchers=ows)
    if "error" in base:
        pytest.fail("montage #437 deux-tirs NON INSTALLE : %s" % base["error"], pytrace=False)
    if int(base["native"].get("n_shots") or 0) < 2:
        pytest.skip("la geometrie n'a amene qu'%d tir(s) : le regime discriminant n'est pas realise"
                    % int(base["native"].get("n_shots") or 0))
    mut = P.run(mutate=True, verbose=True, overwatchers=ows)
    if "error" in mut:
        pytest.fail("montage #437 deux-tirs NON INSTALLE (mutate) : %s" % mut["error"],
                    pytrace=False)
    return base, mut


def test_two_shots_damage_is_observable(two_shot_case):
    """(4) GENERALISATION : sous DOUBLE overwatch, le degat total du move separe les deux lectures --
    le port doit egaler le natif A L'UNITE, et le bras sans foyer doit s'effondrer."""
    base, mut = two_shot_case
    fails = P.verdict(base, mut)
    assert not fails, "regime deux-tirs #437 :\n  - " + "\n  - ".join(fails)
