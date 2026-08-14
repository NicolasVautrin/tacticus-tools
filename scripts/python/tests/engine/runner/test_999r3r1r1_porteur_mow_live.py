"""#999-r3-r1-r1 -- une MACHINE OF WAR porteuse d'un effet-AURA, CONFRONTEE LIVE de bout en bout.

CE QUI EST CONFRONTE ICI, ET CE QUI NE L'EST PAS. La reparation de `#999-r3-r1-r1` retire un
FILTRE du port (les deux agregateurs d'aura exigeaient un `PositionComponent` du porteur ; la face
DECISION ne seedait meme pas les effets des MoW). Un test offline montre qu'un etat SYNTHETIQUE
traverse ; il ne peut pas montrer que le JEU publie la matiere. C'est cette moitie-la que ce
fichier garde -- la chaine `jeu -> decisionView/combatSnapshot -> EffectsState -> univers de
porteurs`.

⚠ AUCUNE MAGNITUDE N'EST CONFRONTEE ICI, et ce n'est pas un oubli : ce fichier garde la CHAINE
(le jeu publie la matiere, le port la voit), pas les nombres. La phrase qui vivait ici -- << aucun
des six effets d'aura de MoW n'est porte cote Python, donc il n'existe aucun nombre a comparer >>
-- est PERIMEE : `1442 BlightedLand` (#1035-r2) et `1449 MoreGitzOverEre` (#1025-r1) SONT portes
et confrontes, chacun dans SON fichier, en regime SEPARANT -- `test_1035r2_blighted_land_bonus_
live.py` et `test_1025r1_more_gitz_bonus_live.py`. Restent NON PORTES : `1443
ContemptuousDisregard`, `1445 WisdomOfTheAncients`, `1494 CabalOfSorcerers`, `1548
GuardianConstruct`. La consigne, elle, reste ENTIEREMENT valable pour eux : le regime par defaut du
harnais impose `targetRarity = 5` a toute unite normalisee, donc tout gate de rarete y est
uniformement VRAI et un vert obtenu la serait VIDE.

MONTAGE : `deathCrawler` / `BlightedLand` (1447 -> effet 1442), le seul couple qui tienne les trois
contraintes -- porteur MoW **au seed**, aura posee A L'INIT (donc presente au tour 0 sans jouer
quoi que ce soit), et `$$CreateTargetSelector` qui ne lit AUCUNE position (la classe exacte
d'effets que la reparation rend atteignable).

Probe : `scripts/python/probe_999r3r1r1_porteur_mow_live.py`. Un montage qui ne s'installe pas
LEVE (`RuntimeError`) et fait ROUGIR ce fichier -- il ne skippe pas (#268/#455).
"""
from __future__ import annotations

import pytest

import probe_999r3r1r1_porteur_mow_live as P

#: #486-r15 -- ce qui doit changer pour que ce fichier puisse changer de verdict.
DECLENCHEUR = {
    "chemins": (
        "scripts/python/probe_999r3r1r1_porteur_mow_live.py",
        # Les QUATRE sites de la reparation : deux agregateurs COMBAT, le seed DECISION, le foyer
        # de l'univers de porteurs, et les trois boucles qui le consomment.
        "scripts/python/engine/runner/damage_model.py",
        "scripts/python/engine/playbook/scene.py",
        "scripts/python/engine/playbook/prediction/_shared.py",
        "scripts/python/engine/playbook/prediction/normal_attack.py",
        # L'ENTREE : ce qui materialise une MoW cote port, et ce qui la publie cote hooks.
        "scripts/python/engine/runner/snapshot.py",
        "scripts/python/engine/entities/effects_state.py",
        "scripts/python/rl_duel.py",
        "scripts/python/catalog_inject.py",
        "frida/hooks/features/ai-step/rpc-decision.ts",
        "frida/hooks/features/ai-step/projection.ts",
    ),
    "build": True,
    "toujours": False,
    "raison": "Confrontation LIVE : le canal `decisionView.mows[].effects` est assemble cote HOOKS "
              "(rpc-decision.ts), et le montage passe par `--equip-mythic`, dont le gameconfig se "
              "perime SEPAREMENT du build. Un changement de build change ce que le jeu publie.",
}


@pytest.fixture(scope="module")
def mesure(live_session):
    """UN runner pour tout le fichier (le montage est identique pour chaque etage), DISPOSE en
    sortie de `run()`. Un montage non installe fait `pytest.fail`, jamais `skip` : un skip
    laisserait ce fichier VERT sans avoir evalue une seule assertion (#455)."""
    try:
        return P.run(verbose=True)
    except RuntimeError as exc:
        pytest.fail("montage porteur-MoW NON INSTALLE : %s" % exc, pytrace=False)


def test_le_jeu_publie_l_aura_sur_la_mow(mesure):
    """Etage 1 -- le CAPTEUR. `decisionView.mows[].effects` est assemble au site du RPC
    (`rpc-decision.ts` : `effectsByUnit.get(m.casterId)`), PAS dans `projectMowsFull`, qui ne porte
    aucun champ `effects`. Conclure du projecteur que le canal n'existe pas serait un faux negatif
    -- c'est pourquoi cet etage LIT la sortie plutot que le code."""
    assert mesure["mow_id"] is not None, "aucune MoW dans decisionView.mows"
    assert mesure["aura_publiee"], (
        "la MoW ne porte pas %r (publie : %r) : le montage n'a pas installe la mythique, ou le "
        "canal `mows[].effects` a disparu" % (mesure["effet"], mesure["mow_effets_publies"]))


def test_la_face_combat_materialise_la_mow_SANS_position(mesure):
    """Etage 2 -- l'ENTREE de la face COMBAT. Les deux faits comptent ENSEMBLE : la MoW existe
    comme entite ET n'a pas de position. Le second est ce qui faisait echouer l'ancien filtre, et
    il doit RESTER vrai : le natif n'a pas de position pour elle non plus."""
    assert mesure["mow_entite_combat"], "la MoW n'est pas materialisee par `load_state`"
    assert mesure["mow_sans_position_combat"], (
        "la MoW a recu un `PositionComponent` : `snapshot._load_machines` fabrique une tuile pour "
        "une entite hors-plateau -- une aura POSITIONNELLE deviendrait evaluable a tort.")
    assert mesure["mow_aura_active_combat"], "l'aura n'est pas ACTIVE dans `state.effects`"


def test_les_deux_agregateurs_combat_retiennent_la_mow(mesure):
    """Etage 3 -- la SORTIE de la face COMBAT, mesuree par INTERCEPTION du foyer REEL (jamais par
    un mirror de sa boucle : un mirror mesurerait le code du probe).

    TEMOIN DE NON-DEGENERESCENCE : les deux listes doivent etre NON VIDES et contenir d'AUTRES
    porteurs que la MoW. Sans lui, << la MoW est retenue >> pourrait etre vrai dans un montage ou
    plus rien ne tourne."""
    for face in ("attaque", "defense"):
        porteurs = mesure["porteurs_aura_%s" % face]
        assert porteurs is not None, (
            "l'agregateur d'aura %s n'a PAS ete appele : le montage ne mesure rien" % face)
        assert len(porteurs) >= 2, (
            "un seul porteur (%r) sur la face %s : temoin degenere" % (porteurs, face))
        assert mesure["mow_id"] in porteurs, (
            "la MoW %r est ECARTEE de l'aura %s (porteurs : %r) -- le filtre positionnel de "
            "`damage_model` est revenu" % (mesure["mow_id"], face, porteurs))


def test_la_face_decision_seede_l_aura_et_voit_le_porteur(mesure):
    """Etage 4 -- la face DECISION, DEUX faits distincts.

    << l'effet est SEEDE >> et << la boucle de porteurs le VOIT >> ne sont pas la meme chose :
    c'est exactement l'ecart qui rendait une reparation partielle invisible. Le foyer qui les relie
    est `Scene.effect_carrier_ids`."""
    assert mesure["mow_seedee_decision"], (
        "`step_context` ne seede plus les effets de `dv['mows']` : la face DECISION redevient "
        "aveugle a l'aura, alors que la face COMBAT la voit -- FORK prediction/combat.")
    assert mesure["mow_dans_univers_porteurs"], (
        "la MoW n'entre pas dans `Scene.effect_carrier_ids` : les trois boucles d'aura de la face "
        "DECISION la rateront.")


def test_aucune_position_n_est_fabriquee_pour_la_mow(mesure):
    """Etage 5 -- la CONTRE-EPREUVE, et c'est elle qui distingue une reparation d'une triche.

    Elargir `pos_by_id` aurait fait passer tous les etages ci-dessus. Ce serait pourtant FAUX : une
    MoW est hors-plateau cote natif aussi, et lui inventer une tuile rendrait evaluable une aura
    POSITIONNELLE qui doit se taire -- pire qu'un gate muet. Ce qu'il fallait elargir est l'UNIVERS
    DES PORTEURS, jamais la geometrie."""
    assert mesure["mow_pos_publiee"] is None, (
        "le jeu publie une position pour la MoW : la premisse du port a change, tout relire.")
    assert mesure["mow_sans_position_decision"], (
        "la MoW est entree dans `pos_by_id` : une tuile a ete FABRIQUEE pour une entite "
        "hors-plateau.")
