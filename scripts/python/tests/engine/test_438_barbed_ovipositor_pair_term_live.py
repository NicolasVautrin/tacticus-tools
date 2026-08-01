"""#438 -- les DEUX poids de `BarbedOvipositor` (1204) dans le `pairUtility`, confrontes au NATIF.

`IdunBattle.AI.Playbook.Loki.BarbedOvipositorPlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__4$$MoveNext`
a QUATRE sorties : 0 si le case n'a pas de prediction, 0 si le kill n'est meme pas POSSIBLE
(`get_MightBeKill`), 0 si la CIBLE porte le trait `Mechanical` (5), et sinon
`BARBEDOVIPOSITOR_DefinitelyKill` quand le kill est GARANTI (`get_WillBeKill`),
`BARBEDOVIPOSITOR_PossibleKill` sinon. Il entre dans la face ATTACK du dispatcher
`TriggeredAbilitiesUtility(2)`, donc DANS le terme de paire -- directement confrontable a l'oracle.

CE QUE CE TEST GARDE -- quatre choses, parce que le corps a quatre sorties et que trois d'entre
elles rendent 0 pour des RAISONS DIFFERENTES :

  1. **CONFORMITE** -- pour CHAQUE regime, l'utilite de paire du port
     (`ComparablePlaybook.calculate_action_utility(...)["u"]`) egale celle du NATIF (RPC
     `pairUtility`), depuis la MEME tuile.
  2. **DISCRIMINANCE PAR REGIME** -- playbook 1204 RETIRE du registre, le port DOIT perdre
     EXACTEMENT le poids attendu de chaque regime : le poids `DefinitelyKill` sur le kill garanti,
     `PossibleKill` sur le kill seulement possible, et RIEN sur les deux regimes nuls. Un port qui
     verserait un poids unique passerait la premiere assertion sur un seul regime et tomberait ici.
  3. **NON-DEGENERESCENCE** -- les deux poids servis sont non nuls ET DIFFERENTS. S'ils etaient
     egaux, la branche `WillBeKill` ne serait plus discriminee et l'accord ne vaudrait rien.
  4. **CABLAGE DE LA PREDICTION** (`test_barbed_ovipositor_requires_case_prediction`) -- 1204 est le
     premier playbook attack porte qui lit `case.DamagePrediction` (`UtilityAttackCase@+0x28`). Si
     un call-site ne la transmet pas, la face ATTACK voit `HasValue == false` et rend 0 EN SILENCE
     -- exactement le patron « porte + non cable » de #419, mais sur l'autre axe. La garde exige
     donc que la feuille rende 0 SANS prediction et le poids AVEC.

Le montage EXIGE les quatre regimes ; s'il ne les obtient pas, il ECHOUE, il ne skippe pas (#268).
Les PV sont CALIBRES sur les bornes RAW natives (`aiPlaybookPredict`) en une passe prealable : au
rank 17 aucun kill n'est possible naturellement, donc un montage nu tomberait entier dans le regime
« aucun kill » -- degenere, et d'accord pour rien.

Porteur : `tyranParasite` (HERO au pool ; 6 npc `tyranBossParasite*` portent 1204 aussi).
Cibles : `astraBullgryn` / `astraCreed` / `astraDreir` (non `Mechanical`), `admecDestroyer`.
ASCII only. Probe jumeau : `scripts/python/probe_438_barbed_ovipositor_pair_term.py`.
"""
from __future__ import annotations

import pytest

import probe_438_barbed_ovipositor_pair_term as P438

EPS = P438.EPS


@pytest.fixture(scope="module")
def bo_case(live_session, rpc, build_runner):
    """Deux runners : le premier CALIBRE les PV sur les bornes natives, le second MESURE.

    Le montage entier (drive, verification de l'AbilitiesComponent, attestation des quatre regimes
    par le natif ET par les mirrors de kill, controle des deux poids BC) vit dans
    `probe_438_barbed_ovipositor_pair_term` -- cette fixture n'en est que la porte pytest. Un
    `MontageError` devient un ECHEC, jamais un skip."""
    try:
        rid_calib = build_runner(P438.SEED, P438.BUILD_ARGS_CALIB)["rid"]
        calib = P438.calibrate(live_session, rpc, rid_calib)
        rid = build_runner(P438.SEED, P438.build_args_measure(calib))["rid"]
        return P438.build_case(live_session, rpc, rid)
    except P438.MontageError as e:
        pytest.fail(str(e), pytrace=False)


def test_barbed_ovipositor_covers_all_four_regimes(bo_case):
    """(3) NON-DEGENERESCENCE : les quatre sorties natives sont bien installees, et les deux poids
    servis sont non nuls et DIFFERENTS."""
    seen = {(r["mechanical"], r["might"], r["will"]) for r in bo_case["regimes"].values()}
    assert seen == {(False, True, True), (False, True, False),
                    (False, False, False), (True, True, True)}, (
        f"les quatre regimes du corps natif ne sont pas tous couverts : {seen}")
    assert bo_case["w_def"] != 0 and bo_case["w_pos"] != 0, (
        f"poids nul dans le BC servi : DefinitelyKill={bo_case['w_def']} "
        f"PossibleKill={bo_case['w_pos']} -- rien ne discriminerait")
    assert bo_case["w_def"] != bo_case["w_pos"], (
        f"les deux poids sont EGAUX ({bo_case['w_def']}) : la branche `WillBeKill` ne serait plus "
        f"discriminee, et un accord ne prouverait rien")


def test_barbed_ovipositor_pair_term_matches_native(bo_case, rpc):
    """(1) CONFORMITE : port == natif sur les quatre regimes, tuile par tuile."""
    rows = P438.measure(rpc, bo_case)
    assert rows, "aucune mesure produite -- le montage n'a rien confronte"
    for r in rows:
        assert abs(r["native"] - r["port"]) < EPS, (
            f"pairUtility != natif sur {r['target']} (regime={r['regime']}) depuis {r['tile']} : "
            f"natif={r['native']} port={r['port']} ecart={r['port'] - r['native']}")


def test_barbed_ovipositor_term_is_load_bearing(bo_case, rpc):
    """(2) DISCRIMINANCE PAR REGIME : playbook 1204 RETIRE -> le port perd EXACTEMENT le poids du
    regime -- `DefinitelyKill` sur le kill garanti, `PossibleKill` sur le kill possible, rien sur
    les deux regimes nuls."""
    rows = P438.measure(rpc, bo_case)
    assert {r["expected"] for r in rows} == {0.0, bo_case["w_pos"], bo_case["w_def"]}, (
        f"les trois niveaux de terme (0 / {bo_case['w_pos']} / {bo_case['w_def']}) ne sont pas "
        f"tous attendus par la mesure : {[(r['target'], r['expected']) for r in rows]}")
    for r in rows:
        got = r["native"] - r["port_muted"]
        assert abs(got - r["expected"]) < EPS, (
            f"sans le playbook 1204, l'ecart au natif sur {r['target']} (regime={r['regime']}) "
            f"depuis {r['tile']} devrait valoir exactement {r['expected']} : natif={r['native']} "
            f"port_mute={r['port_muted']} ecart={got}")


def test_barbed_ovipositor_requires_case_prediction(bo_case):
    """(4) CABLAGE : la face ATTACK ne verse le poids que si le call-site lui passe la
    `DamagePrediction` du case. Sans elle -> 0 partout (le chemin `HasValue == false` du natif).

    La garde VISE LE FOYER exact (`engine.utilities.tile.triggered_abilities_attack_utility`) : un
    call-site qui oublierait de transmettre `ev.prediction` rendrait le playbook INERTE sans erreur
    ni test rouge, et c'est precisement la forme de bug que #419 a recensee."""
    from engine.utilities.tile import triggered_abilities_attack_utility

    ctx, cid, tile, ab = bo_case["ctx"], bo_case["cid"], bo_case["tiles"][0], bo_case["ab"]
    for vis, uid in bo_case["tgt"].items():
        blind = triggered_abilities_attack_utility(ctx, cid, ab, uid, tile)
        assert abs(blind) < EPS, (
            f"la face ATTACK rend {blind} sur {vis} SANS prediction de case : le natif y lit "
            f"`HasValue == false` et rend 0")
        got = triggered_abilities_attack_utility(ctx, cid, ab, uid, tile,
                                                 prediction=P438.prediction_of(bo_case, vis))
        expected = P438.expected_term(bo_case, vis)
        assert abs(got - expected) < EPS, (
            f"la feuille TriggeredAbilities(2) FACE ATTACK rend {got} sur {vis} "
            f"(regime={bo_case['regimes'][vis]}) alors qu'elle doit rendre {expected}")
