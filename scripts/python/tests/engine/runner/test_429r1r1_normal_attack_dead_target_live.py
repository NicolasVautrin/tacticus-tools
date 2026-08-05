"""#429-r1-r1 -- L'ATTAQUE NORMALE sur un CADAVRE est un no-op, aux TROIS portes du port.

CE QUI EST GARDE ICI
--------------------
#429-r1 a pose `IdunBattle.Operations.ActiveAbilityOperation$$IsDeadUnitAndNotAllowedByAbility`
sur la seule voie d'ABILITY, et a nomme le residu : l'attaque NORMALE n'etait gatee NULLE PART.
Or elle EST une active ability cote natif (#139), donc elle traverse le MEME `ExecuteInternal`.

LA QUESTION PREALABLE, ET SA REPONSE MESUREE (le dernier test de ce fichier la GARDE) :
`engine/**` ne CONSTRUIT jamais d'`AttackUnitMessage` -- les attaques DECLENCHEES (overwatch,
riposte, drone commande, summon) appellent `AttackDamageOperation.execute` DIRECTEMENT. Les deux
ensembles sont DISJOINTS : un gate pose au rang du message n'aurait ni gate ni sur-refuse ces
chemins, il n'aurait ferme qu'UNE porte sur 10. Le foyer est donc l'OPERATION -- ce qui est aussi
le mirror exact du natif, qui n'a qu'UN site : `IdunBattle.Entities.Behaviours.
UseActiveAbilityBehaviour$$Execute` -> `Core.Services.OperationProcessor$$ActiveAbility` ->
`ActiveAbilityOperation$$Execute` -> `ExecuteInternal`.

MONTAGE ECRIT (positions FORCEES, board MC1_67, `probe_429r1r1_normal_attack_dead_target`) :
`spaceWulfen` (3,3), `ultraInceptorSgt` (1,3), `tyranWingedPrime` (2,3) a 1 PV, plus un SECOND
ennemi loin -- sans lui, tuer l'unique adversaire TERMINE la bataille et le cadavre disparait des
vues. `spaceWulfen` tue, puis `ultraInceptorSgt` porte son ATTAQUE NORMALE (ability `kind=normal`,
id 69 `Loki_NormalAttack`) sur le CADAVRE, depuis une tuile ADJACENTE.

CHIFFRES MESURES (build rnca9r7q6c, seed 777) :
  * NATIF          : 0 tirage RNG, action NON consommee (`hasAction` reste True).
  * PORT pre-fix   : 6 tirages, **6049 degats sur un cadavre**, ET les flags de tour poses
                     (`ability_used_flag`, `turn_finished`) -- l'action etait consommee.
  * PORT post-fix  : 0 tirage, `last is None` -- accord avec le natif.
  * CIBLE VIVANTE  : 3 tirages, 10192 degats -- le gate ne refuse pas TOUT.

LIVE-agreement, ASCII only. Cf. docs/rl/case-429r1r1-attaque-normale-cadavre.md.
"""
from __future__ import annotations

import pytest

import probe_429r1r1_normal_attack_dead_target as P


@pytest.fixture(scope="module")
def scenario(live_session, tmp_path_factory):
    """Le montage, une fois pour le module. `pytest.fail` (jamais skip) si non installe : un
    montage casse qui passe en skip est un vert qui ment (#455)."""
    sf = tmp_path_factory.mktemp("t429r1r1") / "state.json"
    r = P.scenario_live(str(sf), seed="777", board="MC1_67", verbose=False)
    if r.get("why"):
        pytest.fail("montage #429-r1-r1 NON INSTALLE : %s" % r["why"], pytrace=False)
    return r


def test_le_montage_pose_bien_un_cadavre_visible_et_positionne(scenario):
    """Prealable : sans cadavre VISIBLE et POSITIONNE cote port, tout le reste mesurerait le vide."""
    assert scenario["cible_dv_alive"] is False, "la cible doit etre MORTE"
    assert scenario["cible_dv_hp"] == 0, "hp du cadavre attendu a 0"
    assert scenario["port_cible_presente"] is True, "le port doit VOIR le cadavre"
    assert scenario["port_cible_alive"] is False
    assert scenario["port_cible_pos"] is not None, (
        "le cadavre doit garder une position -- sans elle l'attaque echouerait pour une raison de "
        "PORTEE et la mesure ne discriminerait plus rien")
    assert scenario["normal_ability_id"] is not None, (
        "l'ability `kind=normal` du DV doit etre resolue -- c'est ce qui est joue cote natif")


def test_le_natif_no_oppe_l_attaque_normale_sur_cadavre(scenario):
    """NATIF : 0 tirage RNG et action NON consommee = la signature d'un refus en tete d'operation
    (`ExecuteInternal` sort avant `On(0x2a)`, avant tout degat, avant les flags de tour)."""
    assert scenario["live_draws"] == 0, (
        "natif : 0 tirage attendu sur une attaque normale vers un cadavre, obtenu %s"
        % scenario["live_draws"])
    assert scenario["live_att_has_action"] is True, (
        "natif : l'attaquant doit GARDER son action -- une attaque executee la consommerait")


def test_le_port_no_oppe_aussi(scenario):
    """PORT : accord avec le natif, tirage pour tirage."""
    assert scenario["port_draws"] == 0, (
        "port : 0 tirage attendu, obtenu %s" % scenario["port_draws"])
    assert scenario["port_last"] is None, (
        "port : aucun resultat de coup attendu, obtenu %s" % scenario["port_last"])
    assert scenario["port_draws"] == scenario["live_draws"], "port et natif doivent s'accorder"


def test_contre_epreuve_sans_le_gate_le_port_frappait_le_cadavre(scenario):
    """LA MORSURE. Gate neutralise, la MEME attaque s'execute sur le cadavre : tirages RNG > 0,
    degats > 0, et les flags de tour poses. Sans cette mesure, le vert du test precedent pourrait
    venir d'un montage inerte (une attaque qui ne partait de toute facon pas)."""
    assert scenario["port_sans_gate_draws"] and scenario["port_sans_gate_draws"] > 0, (
        "la mutation n'a pas mordu : sans le gate le port doit consommer du RNG, obtenu %s"
        % scenario["port_sans_gate_draws"])
    assert scenario["port_sans_gate_total"] and scenario["port_sans_gate_total"] > 0, (
        "sans le gate, le port doit infliger des degats AU CADAVRE -- obtenu %s"
        % scenario["port_sans_gate_total"])
    sans = scenario["port_sans_gate_last"] or {}
    assert (sans.get("flags") or {}).get("ability_used_flag") is True, (
        "sans le gate, le port consommait AUSSI l'action de l'attaquant (flags de tour poses), "
        "alors que le natif la laisse -- obtenu %s" % sans.get("flags"))


def test_le_gate_ne_refuse_pas_TOUT_cible_vivante(scenario):
    """GENERALISATION, sur le MEME porteur et la MEME attaque normale : cible VIVANTE, le port
    execute. Sans cette ligne, un gate qui refuserait toute attaque passerait les tests ci-dessus."""
    assert scenario["vivante_cible_alive"] is True, "prealable : la cible doit etre VIVANTE ici"
    assert scenario["vivante_port_draws"] and scenario["vivante_port_draws"] > 0, (
        "cible vivante : le port doit tirer, obtenu %s" % scenario["vivante_port_draws"])
    assert scenario["vivante_port_total"] and scenario["vivante_port_total"] > 0, (
        "cible vivante : le port doit infliger des degats, obtenu %s"
        % scenario["vivante_port_total"])


def test_les_deux_ensembles_de_portes_restent_disjoints():
    """OFFLINE -- GARDE DE LA QUESTION PREALABLE. Le foyer choisi (l'OPERATION) n'est correct que
    tant qu'`engine/**` ne construit AUCUN `AttackUnitMessage` : le jour ou un chemin declenche
    passerait par le visiteur, le gate y serait applique DEUX fois et il faudrait re-repondre a la
    question avant de conclure quoi que ce soit. Ce test force cette re-lecture.

    La contre-epreuve est INTEGREE au scan (`--check`) : il doit retrouver les sites CONNUS, sinon
    son silence sur les constructeurs ne vaudrait rien."""
    r = P._scan()
    assert r["constructeurs"] == [], (
        "un module d'engine/ construit desormais un AttackUnitMessage (%s) -- re-lire la question "
        "prealable de #429-r1-r1 avant d'ajuster le gate" % r["constructeurs"])
    fichiers = sorted({f for f, _ in r["appels_execute"]})
    manquants = [a for a in P.ATTENDUS_EXECUTE if a not in fichiers]
    assert not manquants, (
        "le scan ne retrouve plus les sites CONNUS %s -- son silence ci-dessus ne prouve donc rien"
        % manquants)
    assert len(fichiers) >= 3, (
        "le foyer OPERATION doit couvrir plusieurs portes, obtenu %s" % fichiers)
