"""#448 -- la face MOVE de `SaviorProtocols` (1120) dans le composite `Tile(7)`, confrontee au NATIF.

`IdunBattle.AI.Playbook.Loki.SaviorProtocolsPlaybook.u003CCalculateMovementUtilityInStepsInternalu003Ed__4$$MoveNext`
verse `SAVIORPROTOCOLS_AdjacentTauFriend` (20) par unite ADJACENTE a la tuile candidate qui passe
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.SaviorProtocolsAbility$$TargetIsValidTrigger`,
puis `SAVIORPROTOCOLS_AdjacentTauParent` (30) de PLUS si cette unite est le SUMMONER du mover.

CE QUE CE TEST GARDE -- cinq choses :

  1. **NON-DEGENERESCENCE** -- le terme prend AU MOINS DEUX valeurs distinctes sur les tuiles que
     le natif evalue, et les deux poids servis par le BC sont non nuls. Sans cela, natif et port
     seraient d'accord sur une constante et l'accord ne prouverait rien (piege #271).
  2. **CONFORMITE PAR ETAGE** -- `X_nat = Tile(7) - Elevation - TileEffects` (hooks
     `scorer-damage-trace`) egale le meme `X` calcule sur le composite du PORT, TUILE PAR TUILE.
     C'est une decomposition, jamais un scalaire fitte.
  3. **LES QUATRE NOEUDS DU PREDICAT** -- le terme vaut EXACTEMENT `20 x n`, ou `n` est calcule
     depuis le `decisionView` (ami + faction T'au + sans 1120 + != mover + adjacent au sens natif),
     donc INDEPENDAMMENT du port teste. Le montage place un voisin dedie a chaque noeud : un ami
     T'au sans 1120 (compte), un ami T'au AVEC 1120 greffe (ne compte pas), un ami NON-T'au (ne
     compte pas), un ennemi T'au (ne compte pas).
  4. **DISCRIMINANCE** -- playbook 1120 RETIRE du registre, le `X` du port CHANGE sur au moins une
     tuile. Un port inerte passerait (2) sans rien prouver.
  5. **LE TERME PARENT EST EXERCE** -- second runner, porteur NATUREL (`tauSmnDroneSniper` invoque
     par l'attaque RANGED 1076 de `tauMarksman`, montage #443) : c'est le SEUL etat ou
     `GetParent(case.Unit)` est non nul. Depuis une tuile adjacente au summoner, le terme doit
     valoir `20 + 30`. ⚠ L'oracle NATIF est indisponible sur ce bras (un summon n'entre jamais
     dans `toActivate`, #291) : ce test garde le PORT et l'exercice du noeud, il ne CONFRONTE pas.

PORTEUR : 1120 n'a AUCUN porteur `lineup` (3 npc, 3 summons). Le bras (1)-(4) le GREFFE sur
`tauCrisis` (HERO du pool) -- legitime par `case-92` §5bis : le corps ne lit du mover que son
EQUIPE et son PARENT, jamais une stat ni un trait. Le bras (5) utilise le porteur NATUREL.

Le montage EXIGE ses regimes ; s'il ne les obtient pas, il ECHOUE, il ne skippe pas (#268).

ASCII only. Probe jumeau : `scripts/python/probe_448_savior_protocols_move_term.py`.
"""
from __future__ import annotations

import pytest

import probe_448_savior_protocols_move_term as P448
import probe_443_savior_protocols_pair_term as P443

EPS = P448.EPS


@pytest.fixture(scope="module")
def sp_move_case(live_session, rpc, build_runner):
    """Runner GREFFE : build sur le seed BC greffe, placement dirige, etat frais, tour des autres
    unites termine. Le montage entier vit dans le probe -- cette fixture n'en est que la porte
    pytest. Un `MontageError` devient un ECHEC, jamais un skip."""
    try:
        P448._exiger_build_des_rva()
        seed_bc, _reports = P448.grafted_seed_bc(tag="pytest")
        rid = build_runner(P448.SEED, P448.build_extra(seed_bc))["rid"]
        return P448._place(live_session, rpc, rid)
    except Exception as e:                     # MontageError / BuildPinRefused
        pytest.fail(str(e), pytrace=False)


@pytest.fixture(scope="module")
def sp_move_res(live_session, rpc, sp_move_case):
    """La mesure, faite UNE SEULE FOIS : l'armement des hooks ne capte que sur un etat non encore
    score (mesure -- un second passage sur le meme etat rend 0 event). Tous les tests lisent ce
    meme resultat plutot que de re-mesurer."""
    try:
        return P448.measure(live_session, rpc, sp_move_case)
    except P448.MontageError as e:
        pytest.fail(str(e), pytrace=False)


@pytest.fixture(scope="module")
def sp_parent_res(live_session, rpc, build_runner):
    """Bras (5) : porteur NATUREL, seul etat ou le noeud PARENT est exerce."""
    try:
        rid = build_runner(P448.SEED, ["--board", P448.BOARD,
                                       "--p-units", P448.SUMMONER,
                                       "--a-units", ",".join(P443.FOES),
                                       "--hp-target", P443.HP_TARGET])["rid"]
        return P448.parent_arm(live_session, rpc, rid)
    except P448.MontageError as e:
        pytest.fail(str(e), pytrace=False)


def test_move_montage_is_not_degenerate(sp_move_res):
    """(1) NON-DEGENERESCENCE : deux valeurs distinctes du terme, deux poids BC non nuls."""
    v = P448.verdicts(sp_move_res)
    assert sp_move_res["w_friend"] != 0 and sp_move_res["w_parent"] != 0, (
        f"poids nuls dans le BC servi : {P448.KEY_FRIEND}={sp_move_res['w_friend']} "
        f"{P448.KEY_PARENT}={sp_move_res['w_parent']} -- rien ne discriminerait")
    assert v["V1_terme_variable"], (
        f"TERME CONSTANT sur les {len(sp_move_res['rows'])} tuiles evaluees par le natif "
        f"(valeurs={v['V1_valeurs']}) -- la mesure ne peut pas contredire le port")


def test_move_term_matches_native_per_tile(sp_move_res):
    """(2) CONFORMITE PAR ETAGE : `Tile(7) - Elevation - TileEffects` natif == le meme `X` du port,
    tuile par tuile."""
    v = P448.verdicts(sp_move_res)
    assert not v["V2_desaccords"], (
        "X_nat != X_port sur %d tuile(s) : %s" % (
            len(v["V2_desaccords"]),
            [(r["tile"], r["x_nat"], r["x_port"], r["term"], r["qualified"])
             for r in v["V2_desaccords"]]))


def test_move_term_equals_weight_times_qualified_neighbours(sp_move_res):
    """(3) LES QUATRE NOEUDS : le terme vaut `20 x n`, `n` calcule depuis le `decisionView`.

    C'est la garde qui attrape un port qui compterait un ami NON-T'au, un porteur de 1120, un
    ENNEMI T'au, ou qui oublierait la porte d'elevation de l'adjacence native."""
    v = P448.verdicts(sp_move_res)
    assert not v["V3_non_conformes"], (
        "terme != %s x |voisins qualifies| sur %d tuile(s) : %s" % (
            sp_move_res["w_friend"], len(v["V3_non_conformes"]),
            [(r["tile"], r["term"], r["expected"], r["qualified"])
             for r in v["V3_non_conformes"]]))


def test_move_term_is_load_bearing(sp_move_res):
    """(4) DISCRIMINANCE : 1120 retire du registre, le `X` du port change sur au moins une tuile."""
    v = P448.verdicts(sp_move_res)
    assert v["V4_sensible"], (
        "retirer 1120 de TRIGGERED_MOVE_PLAYBOOKS ne change RIEN sur les %d tuiles mesurees : "
        "%s -- le terme porte est INERTE sur ce montage" % (
            len(sp_move_res["rows"]),
            [(r["tile"], r["x_port"], r["x_port_muted"]) for r in sp_move_res["rows"]]))


def test_move_parent_term_is_exercised(sp_parent_res):
    """(5) LE NOEUD PARENT : depuis une tuile adjacente au SUMMONER, le terme vaut `20 + 30`.

    Le summoner `tauMarksman` est T'au, allie, et ne porte PAS 1120 (son passif est
    `MV71SniperDroneSquad` 1119) : il passe donc `TargetIsValidTrigger`, ce qui est la condition
    pour que le bonus PARENT -- IMBRIQUE dans le predicat au decompile -- soit verse."""
    hit = [r for r in sp_parent_res["rows"] if r["adj_summoner"]]
    assert hit, ("aucune tuile candidate du drone n'est adjacente a son summoner -- le noeud "
                 "PARENT n'est PAS exerce par ce montage")
    exp = sp_parent_res["w_friend"] + sp_parent_res["w_parent"]
    bad = [r for r in hit if abs(r["term"] - exp) > EPS]
    assert not bad, (
        "depuis une tuile adjacente au summoner le terme doit valoir %s (= %s + %s) : %s" % (
            exp, sp_parent_res["w_friend"], sp_parent_res["w_parent"],
            [(r["tile"], r["term"]) for r in bad]))
