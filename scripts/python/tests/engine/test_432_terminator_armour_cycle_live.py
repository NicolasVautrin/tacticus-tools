"""#432 -- le CYCLE d'armement de `1147 TerminatorArmour_ReduceDmg` (44 porteurs), CONFRONTE au NATIF.

Le port appliquait la reduction de -75 % a TOUTE attaque recue. Le natif ne la donne qu'a la
PREMIERE attaque QUALIFIANTE de chaque tour : `IdunBattle.Entities.Effects.Loki.
TerminatorArmour_ReduceDmg_Effect$$CreateTargetTrigger` (`On(9 = Attack)`, emis UNE fois par
attaque par `IdunBattle.Operations.FinishAttackOperation$$Execute`) -> `DeactivateEffect`, et la
branche `ActivationFrequency == 1 (PerTurn)` de
`IdunBattle.Entities.Effects.PlayerTurnEffect$$CreateHandleTriggerAbilitiesInternal` la re-arme au
`On(0x12 = TurnStart_EffectActivation)`.

CE QUE CE TEST GARDE :

  1. **LE NATIF DIT BIEN CA** -- trajectoire du flag `EffectComponent.IsActive @+0x5c` (lu par
     `decisionView({includeInactive:true})`) et **LEDGER PAR COUP** : dans l'attaque consommatrice,
     TOUS les coups sont reduits, pas seulement le premier. « premier COUP » predirait 1/5 ; la
     mesure donne 5/5, bandes DISJOINTES.
  2. **LE PORT REPRODUIT** -- les deux attaques du tour 1 rejouees OFFLINE, ENCHAINEES sur le meme
     `State` et le meme flux RNG, egalent le natif A L'UNITE.
  3. **LE CYCLE PORTE LE RESULTAT** -- cycle NEUTRALISE, la 2e attaque s'effondre : la garde ROUGIT.
     La mutation est verifiee avoir MORDU avant qu'on lise ce verdict (VERT serait le resultat
     suspect).
  4. **LE GATE DE PROFIL SEPARE LES DEUX LECTURES** -- une 1re attaque PSYCHIQUE (profil de
     `terminatorArmourExcludedDmgProfiles`) ne consomme PAS l'armure, donc la 2e attaque du MEME
     tour est REDUITE. C'est le seul regime ou « 2e attaque du tour » et « attaque non reduite » ne
     coincident pas -- un port qui aurait code « on saute la reduction a partir de la 2e attaque »
     y echouerait.

Montage, mesure et verdicts : `scripts/python/probe_432_terminator_armour_cycle.py`. ASCII only.
"""
from __future__ import annotations

import pytest

import probe_432_terminator_armour_cycle as P


@pytest.fixture(scope="module")
def terminator_case(live_session):
    """Les DEUX bras du discriminant central (normal / cycle NEUTRALISE). Chaque bras monte SON
    runner et le DISPOSE en sortie de `run()`. Portee MODULE : les trois tests partagent la mesure."""
    base = P.run(verbose=True)
    if "error" in base:
        pytest.fail("montage #432 NON INSTALLE (bras normal) : %s" % base["error"], pytrace=False)
    mut = P.run(mutate=True, verbose=True)
    if "error" in mut:
        pytest.fail("montage #432 NON INSTALLE (bras mutate) : %s" % mut["error"], pytrace=False)
    if [a["total"] for a in base["native"]] != [a["total"] for a in mut["native"]]:
        pytest.fail("les deux bras n'ont pas la MEME mesure NATIVE (%s vs %s) -- l'A/B ne serait "
                    "plus attribuable au seul cycle"
                    % ([a["total"] for a in base["native"]], [a["total"] for a in mut["native"]]),
                    pytrace=False)
    return base, mut


@pytest.fixture(scope="module")
def terminator_psychic_case(live_session):
    """Le bras `psychic` : 1re attaque de profil EXCLU -> l'armure survit, la 2e attaque est
    reduite."""
    r = P.run(arm="psychic", verbose=True)
    if "error" in r:
        pytest.fail("montage #432 NON INSTALLE (bras psychic) : %s" % r["error"], pytrace=False)
    return r


def test_native_cycle_and_per_hit_ledger(terminator_case):
    """(1) Le NATIF : le flag tombe a la 1re attaque, revient au boundary de tour, et le ledger par
    coup dit « premiere ATTAQUE », pas « premier COUP »."""
    fails = [x for x in P.verdict(*terminator_case) if x.startswith("[natif]")]
    assert not fails, "cycle NATIF #432 :\n  - " + "\n  - ".join(fails)


def test_port_matches_native(terminator_case):
    """(2) Le PORT : rejeu ENCHAINE des deux attaques du tour 1, egalite A L'UNITE avec le natif."""
    fails = [x for x in P.verdict(*terminator_case) if x.startswith("[port]")]
    assert not fails, "port vs natif #432 :\n  - " + "\n  - ".join(fails)


def test_cycle_is_load_bearing(terminator_case):
    """(3) CONTRE-EPREUVE : cycle neutralise -> la 2e attaque s'effondre. Le premier verdict de la
    liste verifie que la MUTATION A MORDU : sans lui, un bras vert ne prouverait rien."""
    fails = [x for x in P.verdict(*terminator_case) if x.startswith("[mutation]")]
    assert not fails, "discriminance #432 :\n  - " + "\n  - ".join(fails)


def test_excluded_damage_profile_does_not_consume(terminator_psychic_case):
    """(4) GENERALISATION : le gate `CurrentAttackDamageProfilesContainOtherThan` -- une attaque
    PSYCHIQUE ne consomme pas l'armure, donc la 2e attaque du tour est REDUITE."""
    fails = P.verdict_psychic(terminator_psychic_case)
    assert not fails, "gate de profil #432 :\n  - " + "\n  - ".join(fails)
