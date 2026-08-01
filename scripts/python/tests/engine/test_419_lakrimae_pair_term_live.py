"""#419 -- le terme `Lakrimae_LikesNonMechanicalEnemies` (+5) du `pairUtility`, confronte au NATIF.

`IdunBattle.AI.Playbook.Loki.LakrimaePlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__3$$MoveNext`
verse le poids `Utilities.Default.TriggeredAbilities.Lakrimae_LikesNonMechanicalEnemies` quand la
CIBLE n'a PAS le trait `Mechanical` (`UnitExtensions.HasTrait(target, (UnitTrait)5)`), et 0 sinon.
Il entre dans la face ATTACK du dispatcher `TriggeredAbilitiesUtility(2)`, donc DANS le terme de
paire -- directement confrontable a l'oracle natif.

CE QUE CE TEST GARDE, et c'est DOUBLE parce que le bug de #419 l'est :

  1. **CONFORMITE** -- pour CHAQUE cible, l'utilite de paire du port
     (`ComparablePlaybook.calculate_action_utility(...)["u"]`) egale celle du NATIF
     (RPC `pairUtility` = `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateUtilityFromPredictions`,
     invoque DEPUIS LA MEME tuile). Les deux regimes du predicat sont couverts : une cible
     `Mechanical` (terme = 0) et une non `Mechanical` (terme = le poids).
  2. **DISCRIMINANCE** -- le meme moteur, playbook 1541 RETIRE du registre
     (`engine.playbook.psyker.TRIGGERED_ATTACK_PLAYBOOKS`), DOIT diverger du natif d'EXACTEMENT le
     poids BC sur la cible NON mecanique, et rester d'accord sur la cible mecanique. Sans cette
     seconde assertion, un port qui ignore le terme passerait -- l'etat d'avant #419.

  3. **CABLAGE** (`test_lakrimae_requires_live_kit_channel`) -- l'ability 1541 arrive par une
     RELIQUE (`UnitConfiguration.TertiaryAbility`), que le kit gameconfig ne contient PAS. La garde
     verifie que le canal live est bien ce qui alimente le dispatcher : le kit gameconfig SEUL ne
     porte pas 1541, le kit live OUI. C'est la moitie du patron #419 -- un playbook porte mais non
     cable est INERTE, sans erreur ni test rouge.

Le montage EXIGE les deux regimes de cible ET la relique effectivement montee ; s'il ne les obtient
pas, il ECHOUE, il ne skippe pas (#268 -- un skip sur un regime non atteint est un vert qui ment).

Porteur : `deathTyphus`, HERO au pool, SEUL `allowedUnits` de l'item relique `R_Crit_Lakrimae`.
Cibles : `admecDestroyer` (trait `Mechanical`) et `astraBullgryn` (sans).
ASCII only. Probe jumeau : `scripts/python/probe_419_lakrimae_pair_term.py` (montage + mesure).
"""
from __future__ import annotations

import pytest

import probe_419_lakrimae_pair_term as P419
from engine.entities.triggered_ability_type import (TriggeredAbilityType,
                                                    kit_triggered_ability_ids)

EPS = P419.EPS


@pytest.fixture(scope="module")
def lak_case(live_session, rpc, build_runner):
    """Monte UN runner avec la relique EQUIPEE, place le caster au contact des deux cibles.

    Le montage entier (drive, verification de l'AbilitiesComponent, choix des tuiles, controle du
    poids BC non nul) vit dans `probe_419_lakrimae_pair_term.build_case` -- cette fixture n'en est
    que la porte pytest. Un `MontageError` devient un ECHEC, jamais un skip."""
    rid = build_runner(P419.SEED, P419.BUILD_ARGS)["rid"]
    try:
        return P419.build_case(live_session, rpc, rid)
    except P419.MontageError as e:
        pytest.fail(str(e), pytrace=False)


def test_lakrimae_pair_term_matches_native(lak_case, rpc):
    """(1) CONFORMITE : port == natif sur les DEUX regimes de cible, tuile par tuile."""
    rows = P419.measure(rpc, lak_case)
    assert rows, "aucune mesure produite -- le montage n'a rien confronte"
    seen = {r["mechanical"] for r in rows}
    assert seen == {True, False}, (
        f"les deux regimes de cible ne sont pas mesures (mechanical vus : {seen})")
    for r in rows:
        assert abs(r["native"] - r["port"]) < EPS, (
            f"pairUtility != natif sur {r['target']} (Mechanical={r['mechanical']}) depuis "
            f"{r['tile']} : natif={r['native']} port={r['port']} ecart={r['port'] - r['native']}")


def test_lakrimae_term_is_load_bearing(lak_case, rpc):
    """(2) DISCRIMINANCE : playbook 1541 RETIRE -> le port perd EXACTEMENT le poids BC sur la cible
    NON mecanique, et rien du tout sur la mecanique (le predicat coupe)."""
    weight = lak_case["weight"]
    assert weight != 0, ("le BC servi porte Lakrimae_LikesNonMechanicalEnemies = 0 : le regime ne "
                         "discrimine rien")
    for r in P419.measure(rpc, lak_case):
        expected = 0.0 if r["mechanical"] else weight
        got = r["native"] - r["port_muted"]
        assert abs(got - expected) < EPS, (
            f"sans le playbook 1541, l'ecart au natif sur {r['target']} "
            f"(Mechanical={r['mechanical']}) depuis {r['tile']} devrait valoir exactement "
            f"{expected} : natif={r['native']} port_mute={r['port_muted']} ecart={got}")


def test_lakrimae_requires_live_kit_channel(lak_case):
    """(3) CABLAGE : 1541 arrive par la RELIQUE, invisible du kit gameconfig. Le dispatcher DOIT
    donc lire le canal live -- sinon le playbook est porte et INERTE (le patron #419).

    La garde VISE LE DISPATCHER, pas le canal : elle etablit d'abord que le kit gameconfig ne
    contient PAS 1541 (sinon elle ne prouverait rien), puis appelle
    `engine.utilities.tile.triggered_abilities_attack_utility` -- le foyer exact ou le cablage a ete
    pose -- et exige qu'il rende le poids sur la cible NON mecanique et 0 sur la mecanique. Retirer
    la lecture live de `TriggeredAbilitiesUtility.evaluate_attack_in_steps` fait tomber les deux
    valeurs a 0 : la garde rougit, meme si le playbook reste au registre.
    (Contre-epreuve JOUEE : `_live_fn = None` -> ecart mesure de 5.000000 sur la non mecanique.)"""
    from engine.utilities.tile import triggered_abilities_attack_utility

    ab = int(TriggeredAbilityType.Lakrimae)
    ctx, cid, tile = lak_case["ctx"], lak_case["cid"], lak_case["tiles"][0]
    vis = (getattr(ctx.scene, "vis_by_id", None) or {}).get(cid)
    kit = list(kit_triggered_ability_ids(vis))
    assert ab not in kit, (
        f"le kit gameconfig de {vis} contient deja {ab} : la garde de cablage ne prouve plus rien "
        f"(kit={sorted(kit)})")
    for name, uid in lak_case["tgt"].items():
        got = triggered_abilities_attack_utility(ctx, cid, lak_case["ab"], uid, tile)
        expected = 0.0 if lak_case["regimes"][name] else lak_case["weight"]
        assert abs(got - expected) < EPS, (
            f"la feuille TriggeredAbilities(2) FACE ATTACK rend {got} sur {name} "
            f"(Mechanical={lak_case['regimes'][name]}) alors qu'elle doit rendre {expected} -- "
            f"1541 vient de la RELIQUE, donc le dispatcher doit lire le canal live, pas le kit "
            f"gameconfig (kit={sorted(kit)})")
