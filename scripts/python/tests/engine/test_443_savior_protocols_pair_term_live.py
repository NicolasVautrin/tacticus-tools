"""#443 -- le poids `SAVIORPROTOCOLS_MarkedTarget` (1120, face ATTACK) dans le `pairUtility`,
confronte au NATIF.

`IdunBattle.AI.Playbook.Loki.SaviorProtocolsPlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__5$$MoveNext`
n'a qu'UN `yield` : le poids si la CIBLE porte un `Markerlight` (1122) ACTIF, 0 sinon. Il entre dans
la face ATTACK du dispatcher `TriggeredAbilitiesUtility(2)`, donc DANS le terme de paire --
directement confrontable a l'oracle.

CE QUE CE TEST GARDE -- quatre choses :

  1. **NON-DEGENERESCENCE** -- les DEUX regimes sont installes SUR LE MEME ETAT (une cible marquee,
     une temoin) et le poids servi par le BC est non nul. Sans les deux, natif et port seraient
     d'accord sur 0 et l'accord ne prouverait rien.
  2. **CONFORMITE** -- pour CHAQUE regime, l'utilite de paire du port
     (`ComparablePlaybook.calculate_action_utility(...)["u"]`) egale celle du NATIF (RPC
     `pairUtility`), depuis la MEME tuile.
  3. **DISCRIMINANCE** -- playbook 1120 RETIRE du registre, le port DOIT perdre EXACTEMENT le poids
     sur la cible marquee et RIEN sur la temoin. Un port qui verserait le poids inconditionnellement
     passerait (2) sur un seul regime et tomberait ici.
  4. **LE TERME EST ATTACHE AU PORTEUR** (`test_savior_protocols_term_belongs_to_carrier`) -- le
     SUMMONER attaque LA MEME cible marquee depuis LA MEME tuile et ne porte PAS 1120 : la face
     ATTACK doit rendre 0 pour lui. C'est la garde qui attrape un port ayant mis la condition dans
     le composite, ou qui lirait l'etat de la cible sans consulter le kit de l'attaquant.

Le montage EXIGE les deux regimes ; s'il ne les obtient pas, il ECHOUE, il ne skippe pas (#268).

PORTEUR : `SaviorProtocols` n'a AUCUN porteur `lineup` -- 3 npc et 3 SUMMONS. C'est la voie SUMMON
de la gate de confrontabilite : l'attaque RANGED 1076 de `tauMarksman` invoque `tauSmnDroneSniper`
(porteur NATIF de 1120) et pose le `Markerlight` sur la cible visee -- une action monte les deux
moities. ⚠ Au CONTACT, 1076 bascule sur le chemin melee : ni drone ni Markerlight (mesure).

ASCII only. Probe jumeau : `scripts/python/probe_443_savior_protocols_pair_term.py`.
"""
from __future__ import annotations

import pytest

import probe_443_savior_protocols_pair_term as P443

EPS = P443.EPS


@pytest.fixture(scope="module")
def sp_case(live_session, rpc, build_runner):
    """Un runner : build, placement RANGED, tir 1076, attestation des deux regimes.

    Le montage entier (drive, verification de l'`AbilitiesComponent` du drone, attestation du
    `Markerlight` cote natif, controle de portee des deux cibles, controle du poids BC) vit dans
    `probe_443_savior_protocols_pair_term` -- cette fixture n'en est que la porte pytest. Un
    `MontageError` devient un ECHEC, jamais un skip."""
    try:
        rid = build_runner(P443.SEED, P443.BUILD_ARGS)["rid"]
        return P443._stage(live_session, rpc, rid)
    except P443.MontageError as e:
        pytest.fail(str(e), pytrace=False)


def test_savior_protocols_covers_both_regimes(sp_case):
    """(1) NON-DEGENERESCENCE : une cible marquee ET une temoin, poids BC non nul."""
    assert sp_case["marks"] == {P443.TGT_MARKED: True, P443.TGT_PLAIN: False}, (
        f"les deux regimes du corps natif ne sont pas installes : {sp_case['marks']}")
    assert sp_case["w"] != 0, (
        f"poids nul dans le BC servi : {P443.KEY_MARKED}={sp_case['w']} -- rien ne discriminerait")


def test_savior_protocols_pair_term_matches_native(sp_case, rpc):
    """(2) CONFORMITE : port == natif sur les deux regimes, depuis la tuile du drone."""
    rows = P443.measure(rpc, sp_case)
    assert rows, "aucune mesure produite -- le montage n'a rien confronte"
    for r in rows:
        assert abs(r["native"] - r["port"]) < EPS, (
            f"pairUtility != natif sur {r['target']} (marked={r['marked']}) depuis {r['tile']} : "
            f"natif={r['native']} port={r['port']} ecart={r['port'] - r['native']}")


def test_savior_protocols_term_is_load_bearing(sp_case, rpc):
    """(3) DISCRIMINANCE : playbook 1120 RETIRE -> le port perd EXACTEMENT le poids sur la cible
    marquee, et RIEN sur la temoin."""
    rows = P443.measure(rpc, sp_case)
    assert {r["expected"] for r in rows} == {0.0, sp_case["w"]}, (
        f"les deux niveaux de terme (0 / {sp_case['w']}) ne sont pas tous attendus par la "
        f"mesure : {[(r['target'], r['expected']) for r in rows]}")
    for r in rows:
        got = r["native"] - r["port_muted"]
        assert abs(got - r["expected"]) < EPS, (
            f"sans le playbook 1120, l'ecart au natif sur {r['target']} (marked={r['marked']}) "
            f"depuis {r['tile']} devrait valoir exactement {r['expected']} : natif={r['native']} "
            f"port_mute={r['port_muted']} ecart={got}")


def test_savior_protocols_term_belongs_to_carrier(sp_case):
    """(4) LE PORTEUR DECIDE : la face ATTACK ISOLEE ne verse le poids que pour l'attaquant qui
    porte 1120. Le SUMMONER vise LA MEME cible marquee depuis LA MEME tuile et doit rendre 0."""
    terms = P443.leaf_terms(sp_case)
    expected = {("drone", P443.TGT_MARKED): sp_case["w"],
                ("drone", P443.TGT_PLAIN): 0.0,
                ("summoner", P443.TGT_MARKED): 0.0,
                ("summoner", P443.TGT_PLAIN): 0.0}
    for key, want in expected.items():
        got = terms[key]
        assert abs(got - want) < EPS, (
            f"la face ATTACK isolee rend {got} pour {key[0]} -> {key[1]} alors qu'elle doit rendre "
            f"{want} (termes complets : {terms})")
