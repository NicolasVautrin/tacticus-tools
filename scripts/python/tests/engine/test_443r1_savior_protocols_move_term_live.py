"""#443-r1 -- la face MOVE de `SaviorProtocols` (1120), sur son porteur NATUREL.

`IdunBattle.AI.Playbook.Loki.SaviorProtocolsPlaybook.u003CCalculateMovementUtilityInStepsInternalu003Ed__4$$MoveNext`
verse `SAVIORPROTOCOLS_AdjacentTauFriend` (20) par unite ADJACENTE a la tuile candidate qui passe
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.SaviorProtocolsAbility$$TargetIsValidTrigger`,
puis `SAVIORPROTOCOLS_AdjacentTauParent` (30) de PLUS si cette unite est le SUMMONER du mover.

MONTAGE : le drone `tauSmnDroneSniper`, invoque par l'attaque RANGED 1076 de `tauMarksman` (montage
#443 repris tel quel). C'est le SEUL etat ou `GetParent(case.Unit)` est non nul -- donc le seul qui
exerce le terme PARENT -- et c'est un porteur NATUREL, pas une greffe. Trois voisins sont amenes
apres le tir pour exercer un noeud du predicat chacun.

CE QUE CE TEST GARDE -- cinq choses :

  1. **NON-DEGENERESCENCE** -- le terme prend TROIS valeurs distinctes sur le balayage (0 / 20 /
     20+30), et les deux poids servis par le BC sont non nuls (piege #271). Le regime a 20 est ce
     qui SEPARE les deux poids : 50 tout seul ne distingue pas `20 + 30` d'un forfait.
  2. **LE CANAL PARENT EST REEL** -- `unit_parent_id` du `ctx` tile-leaf vaut l'id du summoner sur
     un VRAI summon (le montage LEVE sinon). Sans lui le terme PARENT serait muet en silence.
  3. **CONFORMITE** -- le terme egale `20 x n + 30 si le parent est parmi les n`, ou `n` est
     calcule depuis le `decisionView` + `faction_value` + le kit LIVE (`unitAbilityStates`), donc
     SANS passer par le playbook teste.
  4. **LES CONTRE-REGIMES SONT EXPOSES** -- chacun des trois voisins-temoins est adjacent a au
     moins une tuile balayee. Un contre-regime qu'aucune tuile ne voit rendrait « 0 » sans rien
     prouver.
  5. **CINQ CONTRE-EPREUVES MORDENT** -- les quatre noeuds du predicat, la cle du poids FRIEND et
     l'entree au registre, mutes un a un, changent la mesure ; et l'etat est verifie RESTAURE apres
     chacune. Sur une contre-epreuve, VERT est le resultat SUSPECT.

⚠ CE QUE CE TEST NE FAIT PAS : il ne CONFRONTE PAS au natif. Un summon n'entre jamais dans
`toActivate` (#291), et le hook `scorerTileTermTrace` n'attribue aucune evaluation au porteur (trois
faits de harnais mesures, cf. la docstring du probe). Le terme MOVE reste **NON CONFRONTE** ; le
point d'ancrage a hooker est
`IdunBattle.AI.Utilities.TriggeredAbilitiesUtility.u003CEvaluateMovementInStepsu003Ed__2$$MoveNext`.

Le montage EXIGE ses regimes ; s'il ne les obtient pas, il ECHOUE, il ne skippe pas (#268).

ASCII only. Probe jumeau : `scripts/python/probe_443r1_savior_protocols_move_term.py`.
"""
from __future__ import annotations

import pytest

import catalog_inject as CI
import probe_443r1_savior_protocols_move_term as P443R1
import probe_443_savior_protocols_pair_term as P443

EPS = P443R1.EPS
SEED = "41504"


@pytest.fixture(scope="module")
def sp_move_res(live_session, rpc, build_runner, tmp_path_factory):
    """Le montage complet, mesure UNE SEULE FOIS (les contre-epreuves re-jouent la mesure sur le
    resultat deja capture, sans retoucher au runner). Un `MontageError` devient un ECHEC."""
    try:
        gseed, _ = CI.write_grafted_seed_bc(
            tmp_path_factory.mktemp("bc443r1") / "seed.json",
            [f"{P443R1.EXTRA_1120}:{P443R1.ABILITY_NAME}"], replace=True)
        extra = list(P443.build_args(P443R1.BOARD))
        extra[extra.index("--p-units") + 1] = ",".join(
            [P443R1.SUMMONER, P443R1.EXTRA_TAU, P443R1.EXTRA_OTHER, P443R1.EXTRA_1120])
        extra[extra.index("--a-units") + 1] = ",".join(list(P443.FOES) + [P443R1.ENE_TAU])
        rid = build_runner(SEED, extra + ["--seed-bc", str(gseed)])["rid"]
        return P443R1.parent_arm(live_session, rpc, rid)
    except P443R1.MontageError as e:
        pytest.fail(str(e), pytrace=False)


@pytest.fixture(scope="module")
def sp_counter_proofs(sp_move_res):
    return P443R1.counter_proofs(sp_move_res)


def test_move_montage_reaches_three_regimes(sp_move_res):
    """(1) NON-DEGENERESCENCE : 0 / 20 / 20+30 tous atteints, deux poids BC non nuls."""
    assert sp_move_res["w_friend"] != 0 and sp_move_res["w_parent"] != 0, (
        f"poids nuls dans le BC servi : {P443R1.KEY_FRIEND}={sp_move_res['w_friend']} "
        f"{P443R1.KEY_PARENT}={sp_move_res['w_parent']} -- rien ne discriminerait")
    vals = sorted({round(r["term"], 4) for r in sp_move_res["rows"]})
    want = sorted({0.0, sp_move_res["w_friend"],
                   sp_move_res["w_friend"] + sp_move_res["w_parent"]})
    assert vals == want, (
        f"les trois regimes du corps natif ne sont pas tous atteints : vu {vals}, attendu {want} "
        f"-- sans le regime a {sp_move_res['w_friend']}, le poids PARENT n'est pas SEPARE du "
        f"poids FRIEND")


def test_move_parent_channel_is_live(sp_move_res):
    """(2) LE CANAL PARENT EST REEL : le montage a leve si `unit_parent_id` n'etait pas le summoner
    -- ce test atteste en plus qu'au moins une tuile l'exerce."""
    hit = [r for r in sp_move_res["rows"] if r["adj_summoner"]]
    assert hit, ("aucune tuile balayee n'est adjacente au SUMMONER -- le noeud PARENT n'est PAS "
                 "exerce par ce montage")


def test_move_term_matches_independent_expectation(sp_move_res):
    """(3) CONFORMITE : terme == `20 x n (+30 si le parent est parmi les n)`, `n` calcule hors du
    playbook teste."""
    bad = [r for r in sp_move_res["rows"] if abs(r["term"] - r["expected"]) > EPS]
    assert not bad, (
        "terme != attendu sur %d tuile(s) : %s" % (
            len(bad), [(r["tile"], r["term"], r["expected"], r["qualified"], r["adj_summoner"])
                       for r in bad]))


def test_move_counter_regimes_are_exposed(sp_move_res):
    """(4) LES CONTRE-REGIMES SONT EXPOSES : chaque voisin-temoin est adjacent a >= 1 tuile
    balayee. Sans cela son « 0 » ne prouverait rien."""
    zero = [v for v, n in (sp_move_res["exposure"] or {}).items() if not n]
    assert not zero, (
        f"ces voisins-temoins ne sont adjacents a AUCUNE tuile balayee : {zero} -- leur 0 ne "
        f"prouve rien (exposition mesuree : {sp_move_res['exposure']})")


def test_move_counter_proofs_bite(sp_counter_proofs):
    """(5) LES CONTRE-EPREUVES MORDENT, et l'etat est RESTAURE apres chacune."""
    assert sp_counter_proofs, "aucune contre-epreuve jouee"
    inertes = [c["name"] for c in sp_counter_proofs if not c["mord"]]
    assert not inertes, (
        "ces contre-epreuves NE MORDENT PAS -- la mesure ne peut pas les distinguer du port juste :"
        " %s" % [(c["name"], c["why"]) for c in sp_counter_proofs if not c["mord"]])
    derive = [c["name"] for c in sp_counter_proofs if not c["restored"]]
    assert not derive, (
        f"ces contre-epreuves n'ont PAS restaure l'etat : {derive} -- elles contamineraient les "
        f"suivantes")
