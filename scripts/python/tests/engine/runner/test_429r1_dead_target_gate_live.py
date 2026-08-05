"""#429-r1 -- GATE CIBLE-MORTE : un cast sur un CADAVRE est un no-op, sauf `AllowDeadTarget`.

CE QUI EST GARDE ICI
--------------------
`IdunBattle.Operations.ActiveAbilityOperation$$IsDeadUnitAndNotAllowedByAbility` est le PREMIER
gate d'`ExecuteInternal`. Son verdict est le virtuel slot 0x11 `IActiveAbility.CanContinueOnDeadTarget`
-- LE lecteur du bit 38 `AllowDeadTarget`, que la tranche #429 avait laisse en `READER_UNKNOWN`
parce qu'il ne vit dans AUCUNE cascade de ciblage : il lit le masque de CONTINUE
(`AActiveAbility._targetingOptionsForContinue`, +0xb0, donc `Rules` a +0xd8), pas le masque
principal a +0x70.

MONTAGE ECRIT (positions FORCEES, board MC1_67, `probe_429r1_dead_target_gate.scenario_live`) :
`spaceWulfen` (2,2), `ultraInceptorSgt` (1,3), `tyranWingedPrime` (2,3) a 1 PV, plus un SECOND
ennemi loin -- sans lui, tuer l'unique adversaire TERMINE la bataille et le cadavre disparait des
vues (mesure faite : toutes les sondes a `None`). `spaceWulfen` tue, puis `ultraInceptorSgt` caste
`DeathFromAbove` (1003) sur le CADAVRE, depuis une tuile ADJACENTE.

CHIFFRES MESURES (build rnca9r7q6c, seed 777) :
  * NATIF        : 0 tirage RNG, action NON consommee (`hasAction` reste True) -- refus complet.
  * PORT pre-fix : le gate suivant (`is_invalid_target`, deja porte) rendait **0** -- il ACCEPTAIT.
                   Le cast s'executait : 6 tirages, un summon spawne, 5702 degats sur un cadavre.
  * PORT post-fix: 0 tirage, `dead_target_not_allowed` -- identique au natif.
Le nouveau gate n'est donc PAS redondant avec `IsInvalidTarget` : sur un etat reel, ce dernier
laissait passer 43 des 104 abilities du registre sur une cible morte (`--volet trou`).

⚠ #429-r1-r3 -- DEPUIS, UN GATE DE PLUS A ETE LU, ET IL EST AU-DESSUS DE CELUI-CI :
`IdunBattle.Messages.InputMessageProcessor$$Visit(ActiveAbilityMessage)` teste
`IdunBattle.Entities.UnitExtensions$$IsAliveAndNotFled` sur le caster puis la cible AVANT toute
operation, sans lire l'ability -- donc sans derogation. Sur la voie MESSAGE, `port_last` sort
desormais par `not_alive_and_not_fled`. Le gate d'OPERATION garde ci-dessous n'a pas bouge : il est
mesure en le laissant SEUL (bras `port_sans_message_gate_*`), et c'est ce bras qui rend la
derogation du bit 38 OBSERVABLE au lieu d'assertee sur un predicat.

LIVE-agreement, ASCII only. Cf. docs/rl/case-429r1-lecteurs-bits-ciblage.md.
"""
from __future__ import annotations

import pytest

import probe_429r1_dead_target_gate as P


@pytest.fixture(scope="module")
def scenario(live_session, tmp_path_factory):
    """Le montage, une fois pour le module. `pytest.fail` (jamais skip) si non installe : un
    montage casse qui passe en skip est un vert qui ment (#455)."""
    sf = tmp_path_factory.mktemp("t429r1") / "state.json"
    r = P.scenario_live(str(sf), seed="777", board="MC1_67", verbose=False)
    if r.get("why"):
        pytest.fail("montage #429-r1 NON INSTALLE : %s" % r["why"], pytrace=False)
    return r


def test_le_montage_pose_bien_un_cadavre_visible_et_positionne(scenario):
    """Prealable : sans cadavre VISIBLE et POSITIONNE cote port, tout le reste mesurerait le vide.
    C'est exactement ce qui s'est produit au premier jet (un seul ennemi -> bataille terminee)."""
    assert scenario["cible_dv_alive"] is False, "la cible doit etre MORTE"
    assert scenario["cible_dv_hp"] == 0, "hp du cadavre attendu a 0"
    assert scenario["port_cible_presente"] is True, "le port doit VOIR le cadavre"
    assert scenario["port_cible_alive"] is False
    assert scenario["port_cible_pos"] is not None, (
        "le cadavre doit garder une position -- sans elle le gate de PORTEE refuserait pour une "
        "autre raison et la mesure ne discriminerait plus rien")


def test_le_natif_no_oppe_le_cast_sur_cadavre(scenario):
    """NATIF : 0 tirage RNG et action NON consommee = la signature d'un refus en tete d'operation
    (`ExecuteInternal` sort avant `On(0x2a)`, avant tout degat, avant les flags de tour)."""
    assert scenario["live_draws"] == 0, (
        "natif : 0 tirage attendu sur un cast vers un cadavre, obtenu %s" % scenario["live_draws"])
    assert scenario["live_sgt_has_action"] is True, (
        "natif : le caster doit GARDER son action (actionConsumed=false) -- un cast execute la "
        "consommerait")


def test_le_port_refuse_par_un_gate_CIBLE_MORTE_et_pas_par_un_autre(scenario):
    """PORT : le refus vient bien d'un gate CIBLE-MORTE, et il n'est pas redondant --
    `is_invalid_target` SEUL rendait 0 (il acceptait) sur ce meme etat.

    ⚠ #429-r1-r3 : sur la voie MESSAGE, c'est le gate du MESSAGE
    (`InputMessageProcessor$$Visit` -> `UnitExtensions$$IsAliveAndNotFled`) qui mord en PREMIER, le
    gate d'OPERATION etant un cran plus bas. `port_gate_refuse` reste la mesure du SECOND (predicat
    pur, evalue hors du chemin) -- et le test suivant le laisse SEUL pour montrer qu'il est arme."""
    assert scenario["port_is_invalid_target_seul"] == 0, (
        "le montage n'est plus DISCRIMINANT : `is_invalid_target` refuse deja (code %s), donc ce "
        "test ne prouverait plus rien du gate cible-morte"
        % scenario["port_is_invalid_target_seul"])
    assert scenario["port_gate_refuse"] is True, (
        "le gate d'OPERATION doit rester ARME pour cette ability (predicat pur)")
    assert (scenario["port_last"] or {}).get("not_alive_and_not_fled") == "target", (
        "le port doit sortir par le gate de MESSAGE sur la cible, obtenu %s"
        % scenario["port_last"])
    assert scenario["port_draws"] == 0, (
        "port : 0 tirage attendu, obtenu %s" % scenario["port_draws"])
    assert scenario["port_draws"] == scenario["live_draws"], "port et natif doivent s'accorder"


def test_le_gate_d_OPERATION_refuse_quand_on_le_laisse_SEUL(scenario):
    """DECOMPOSITION PAR ETAGE (#429-r1-r3). Gate de MESSAGE neutralise, c'est le gate d'OPERATION
    qui prend le refus -- et il rend bien `dead_target_not_allowed`, sans consommer de RNG. C'est
    ce bras qui garde le port de #429-r1 maintenant qu'un gate plus haut le precede."""
    seul = scenario["port_sans_message_gate_last"] or {}
    assert seul.get("dead_target_not_allowed") is True, (
        "gate de message debranche : c'est au gate d'OPERATION de refuser, obtenu %s" % seul)
    assert scenario["port_sans_message_gate_draws"] == 0, (
        "le gate d'operation sort AVANT tout tirage, obtenu %s"
        % scenario["port_sans_message_gate_draws"])


def test_contre_epreuve_sans_AUCUN_gate_le_port_executait(scenario):
    """LA MORSURE. Les DEUX gates neutralises, le meme cast s'EXECUTE : tirages RNG > 0 et une
    behaviour complete. Sans cette mesure, les verts precedents pourraient venir d'un montage
    inerte."""
    assert scenario["port_sans_gate_draws"] and scenario["port_sans_gate_draws"] > 0, (
        "la mutation n'a pas mordu : sans les gates le port doit consommer du RNG, obtenu %s"
        % scenario["port_sans_gate_draws"])
    sans = scenario["port_sans_gate_last"] or {}
    assert sans.get("dead_target_not_allowed") is None, "gates censes etre neutralises"
    assert sans.get("not_alive_and_not_fled") is None, "gates censes etre neutralises"
    assert sans.get("attacks") or sans.get("dsl"), (
        "sans les gates, la behaviour doit s'executer sur le cadavre -- obtenu %s" % sans)


@pytest.fixture(scope="module")
def scenario_porteur(live_session, tmp_path_factory):
    """GENERALISATION -- roles INVERSES : `ultraInceptorSgt` tue, puis `spaceWulfen` caste
    `GreatFrostAxe` (1089) sur le cadavre. C'est le cas ou le BIT 38 doit MORDRE dans l'autre sens :
    le gate ne doit PAS refuser le porteur."""
    sf = tmp_path_factory.mktemp("t429r1p") / "state.json"
    r = P.scenario_live(str(sf), seed="777", board="MC1_67", verbose=False,
                        ability=1089, killer="ultraInceptorSgt", caster="spaceWulfen")
    if r.get("why"):
        pytest.fail("montage porteur NON INSTALLE : %s" % r["why"], pytrace=False)
    return r


def test_le_gate_d_OPERATION_laisse_passer_le_porteur_du_bit_38(scenario_porteur):
    """Le gate d'OPERATION est un MIRROR, pas un refus generalise : `GreatFrostAxe` (1089) arme
    `AllowDeadTarget` dans son masque de CONTINUE, donc `CanContinueOnDeadTarget()` rend vrai et
    `IsDeadUnitAndNotAllowedByAbility` rend FAUX. Sans cette assertion, un gate qui refuserait TOUT
    passerait les tests precedents.

    ⚠ #429-r1-r3 -- LA DEROGATION EST DESORMAIS OBSERVABLE, et pas seulement assertee sur un
    predicat : gate de MESSAGE debranche, 1089 EXECUTE sa behaviour sur le cadavre (la glace se
    pose) la ou 1003 sortait par `dead_target_not_allowed`. C'est le MEME bras, deux abilities, deux
    verdicts -- le bit 38 est ce qui les separe.

    ⚠ Ce que le port fait EN VRAI pour 1089 sur la voie MESSAGE est un refus par le gate du MESSAGE
    (cf. `test_429r1r3_dead_target_message_gate_live.py`) : le residu `#429-r1-r3` que cette
    docstring nommait -- « le natif refuse, le port pose la glace » -- est RESOLU, et sa cause
    n'etait pas la portee mais un gate d'un RANG PLUS HAUT."""
    assert scenario_porteur["port_gate_refuse"] is False, (
        "le porteur du bit 38 ne doit PAS etre refuse par le gate cible-morte d'OPERATION")
    assert (scenario_porteur["port_last"] or {}).get("dead_target_not_allowed") is None, (
        "1089 ne doit pas sortir par le gate d'operation, obtenu %s" % scenario_porteur["port_last"])
    assert scenario_porteur["port_cible_alive"] is False, "la cible doit bien etre MORTE"
    seul = scenario_porteur["port_sans_message_gate_last"] or {}
    assert seul.get("dead_target_not_allowed") is None, (
        "gate de message debranche, 1089 ne doit PAS etre refuse par le gate d'operation")
    assert seul.get("dsl") or seul.get("attacks"), (
        "gate de message debranche, 1089 doit EXECUTER sa behaviour sur le cadavre -- obtenu %s"
        % seul)


def test_seul_le_porteur_du_bit_38_echappe_au_gate():
    """OFFLINE : `can_continue_on_dead_target()` ne vaut True que pour `GreatFrostAxe` (1089).

    Le compte n'est pas saisi : le scan d'instructions du binaire du build courant
    (`probe_429r1_bit_readers_scan.py`) ne trouve qu'UN site posant le bit 38 dans tout
    `GameAssembly.dll`, `GreatFrostAxeAbility$$GetTargetingOptionsForContinue`. Si une tranche
    future porte une seconde ability qui l'arme, ce test rougit et demande de le RE-verifier au
    binaire plutot que de gonfler une liste."""
    from engine.runner.abilities.handler import ABILITY_CLASSES
    vrais = sorted(aid for aid, k in ABILITY_CLASSES.items() if k.can_continue_on_dead_target())
    assert vrais == [1089], (
        "porteurs attendus [1089 GreatFrostAxe], obtenus %s -- re-lire le binaire "
        "(`probe_429r1_bit_readers_scan.py --bit 38`) avant d'ajuster" % vrais)
