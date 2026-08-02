"""GARDE #447 -- `AddCasterIfMatchesDynamicRule` (bit 3) et le DEEP STRIKE, confronte au NATIF.

CE QUE CE FICHIER PROTEGE
-------------------------
`IdunBattle.Core.Services.TargetingQuery$$GetCasterNotAddedReason` etait un `return 0` (permissif
integral). Le port ACCEPTAIT donc le cast de 1115 `FearOfTheUnseen` pendant que le Deathleaper est
en DEEP STRIKE -- ce que le natif REFUSE, par sa regle-delegue CASTER
`FearOfTheUnseenAbility$$GetDynamicInvalidCasterReason` = `IsTeleporting(caster) ? 4 : 0`. C'est
exactement le « and is not in Deep Strike » du texte i2 de l'ability.

DEUX PIEGES QUE CETTE GARDE ENCODE, parce que les deux ont ete rencontres en la construisant :

  1. **LE CANAL `abilityReason` EST MUET ICI.** Il passe par
     `IdunBattle.Core.Services.AttackQuery$$GetInvalidTargetReason`, qui court-circuite sur
     `ActiveAbility$$get_CanCurrentlyBeUsed` AVANT toute cascade et rend le litteral `1`
     (`ValidRequest`). 1115 porte `initialCooldownTurns = 1` : au SEUL tour ou le Deep Strike est
     actif, ce canal publie `0x1` quoi qu'il arrive. Le canal juste est `abilityTargets.fromHere`
     (`AttackQuery$$GetValidTargets` ne gate que sur `IsAlreadyUsedThisTurn`).
     `test_le_canal_abilityreason_ne_tranche_pas` fige ce constat : s'il devenait faux (correctif
     de hook, cooldown initial modifie), on veut le savoir plutot que continuer a lire un canal
     dont on a suppose le comportement.
  2. **L'ATTRIBUTION.** `abilityTargets` mesure `TargetingQuery$$GetValidTargets`, qui n'appelle
     PAS `GetCasterNotAddedReason` mais RE-IMPLEMENTE l'ajout du caster dans le meme ordre. Un
     etage ANTERIEUR (`isSelfCasting` quand la liste est deja non vide) pourrait ajouter le caster
     et masquer la regle. `test_attribution_aucune_autre_cible_n_ajoute_le_caster` verifie que
     `targets == 0` dans le regime discriminant -- sans quoi la mesure ne serait plus attribuable.

MESURE : `python scripts/python/probe_447_add_caster_dynamic_rule.py [--generalize]`.
RE : `docs/rl/case-447-add-caster-dynamic-rule.md`.
ASCII only (console Windows cp1252). Aucune VA en dur.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))

import probe_447_add_caster_dynamic_rule as P                            # noqa: E402
from engine.runner.abilities.targeting_rule import TargetingRule as TR   # noqa: E402

DYNAMIC = int(TR.CasterMatchesDynamicRule)
NOT_MOVED = int(TR.CasterHasNotMoved)


@pytest.fixture(scope="module")
def mesure():
    """Rejoue le probe COMPLET (regimes R1/R2/R3 + contre-epreuves + rayon) et rend son bloc
    `[RAW]`. Le probe dispose SON runner, jamais ceux des autres."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = P.main([])
    txt = buf.getvalue()
    print(txt[-4000:])
    raw = [ln for ln in txt.splitlines() if ln.startswith("[RAW] ")]
    assert raw, "le probe n'a pas rendu sa ligne [RAW] -- montage rate :\n" + txt[-3000:]
    data = json.loads(raw[-1][len("[RAW] "):])
    data["rc"] = rc
    return data


# --------------------------------------------------------------------------- le montage tient

def test_le_montage_realise_le_deep_strike(mesure):
    """Sans Deep Strike au deploiement, la regle est MUETTE et l'accord ne prouverait rien. Le
    regime n'est pas un accident de spawn : `tyranDeathleaper` porte le trait `TeleportStrike`."""
    assert mesure["R1"]["teleporting"] is True, (
        "le caster n'est pas en Deep Strike au deploiement -- la mesure serait vide")


def test_le_canal_abilityreason_ne_tranche_pas(mesure):
    """Piege 1 : le canal naif publie `ValidRequest` (0x1) dans le regime discriminant. On le FIGE
    pour que le jour ou il changerait ne passe pas inapercu."""
    canal = mesure["canal_abilityreason"]
    assert canal["muet"] is True, (
        "abilityReason rend %s (cooldown=%s) : le canal a change -- re-lire quelle cascade il "
        "traverse avant de s'en servir" % (canal["hex"], canal["cooldown"]))


def test_attribution_aucune_autre_cible_n_ajoute_le_caster(mesure):
    """Piege 2 : `GetValidTargets` ajoute le caster par un etage ANTERIEUR des que la liste des
    cibles ordinaires est non vide. `targets == 0` est ce qui rend le verdict attribuable au
    bit 3."""
    assert mesure["R1"]["nat_targets"] == 0, (
        "targets=%s en R1 : l'ajout du caster pourrait venir de l'etage `isSelfCasting`"
        % mesure["R1"]["nat_targets"])
    assert mesure["R2"]["nat_targets"] in (0, 1), "R2 : liste de cibles inattendue"
    assert mesure["R2"]["fromHere_ids"] == [mesure["R2"]["caster"]], (
        "R2 : fromHere=%s, attendu [le caster] -- l'ajout ne vient pas de la branche mesuree"
        % mesure["R2"]["fromHere_ids"])


# --------------------------------------------------------------------------- l'accord natif/port

def test_le_natif_refuse_en_deep_strike(mesure):
    """La ligne qui porte toute la tranche : le natif ne propose AUCUNE cible pour 1115 tant que le
    caster teleporte."""
    assert mesure["R1"]["nat_fromHere"] == 0, (
        "le natif accepte le self-cast en Deep Strike (fromHere=%s) -- le regime discriminant a "
        "disparu" % mesure["R1"]["nat_fromHere"])


def test_le_port_rend_caster_matches_dynamic_rule(mesure):
    """Le code EXACT, pas seulement « un refus » : le natif rend le code de la DELEGUE
    (`GenericBrokenTargetingRule(4)`), pas le bit 3."""
    assert mesure["R1"]["port"] == DYNAMIC, (
        "port=%s, attendu %s (CasterMatchesDynamicRule)"
        % (hex(mesure["R1"]["port"]), hex(DYNAMIC)))


def test_hors_deep_strike_les_deux_acceptent(mesure):
    """La face RESTRICTIVE : un port trop strict casserait le cast legitime du tour suivant."""
    assert mesure["R2"]["teleporting"] is False, "R2 : l'effet n'a pas expire"
    assert mesure["R2"]["nat_fromHere"] == 1 and mesure["R2"]["port"] == 0, (
        "R2 natif fromHere=%s port=%s -- attendu 1 / 0x0"
        % (mesure["R2"]["nat_fromHere"], hex(mesure["R2"]["port"])))


# --------------------------------------------------------------------------- l'ORDRE

def test_ordre_une_regle_anterieure_gagne_live(mesure):
    """PREUVE D'ORDRE confrontee au natif : apres un move, le natif refuse AUSSI (fromHere=0) et le
    port doit rendre `CasterHasNotMoved` -- la regle de la cascade CASTER, qui tourne AVANT
    `GetCasterNotAddedReason` dans l'overload 5 arguments. Rendre `0x4` ici serait un ordre
    inverse, invisible de tout test qui ne regarderait que « refuse / accepte »."""
    r3 = mesure["R3"]
    if r3 is None:
        pytest.skip("aucune tuile de deplacement -- regime NON CONFRONTE (dit, pas masque)")
    assert r3["nat_fromHere"] == 0, "R3 : le natif accepte alors que le caster a bouge"
    assert r3["port"] == NOT_MOVED, (
        "R3 port=%s, attendu %s -- l'ordre des deux cascades est inverse"
        % (hex(r3["port"]), hex(NOT_MOVED)))


def test_ordre_offline_le_court_circuit_addcaster_precede(mesure):
    """Meme preuve d'ordre a l'INTERIEUR de `GetCasterNotAddedReason` : `AddCaster` (bit 7) est
    teste AVANT le bit 3, donc l'ajouter au masque doit faire ACCEPTER malgre le Deep Strike."""
    assert mesure["CE"]["ce2_addcaster"] == 0, (
        "CE2 = %s : le court-circuit `AddCaster` ne precede plus la branche de la regle-delegue"
        % hex(mesure["CE"]["ce2_addcaster"]))
    assert mesure["CE"]["ce4_ordre_moved"] == NOT_MOVED, (
        "CE4 = %s, attendu %s" % (hex(mesure["CE"]["ce4_ordre_moved"]), hex(NOT_MOVED)))


# --------------------------------------------------------------------------- la degradation fermee

def test_la_degradation_fermee_etait_permissive(mesure):
    """L'etat de `master` avant #447, joue comme contrefactuel de CHAMP (masque prive du bit 3) :
    le port ACCEPTAIT (`0x0`) la ligne que le natif refuse. C'est la seule forme de preuve qui
    vaille pour une regle dont la degradation est permissive -- elle ne produit aucun desaccord
    mesurable tant qu'on ne va pas la chercher."""
    assert mesure["CE"]["ce1_sans_bit3"] == 0, (
        "CE1 = %s : le contrefactuel refuse deja, la mutation ne mord pas"
        % hex(mesure["CE"]["ce1_sans_bit3"]))
    assert mesure["R1"]["port"] != mesure["CE"]["ce1_sans_bit3"], (
        "le port rend la meme chose avec et sans le bit 3 -- rien n'a ete ferme")


def test_c_est_la_delegue_qui_decide_pas_le_bit(mesure):
    """Le bit 3 n'est qu'un AIGUILLAGE : la meme classe dont la delegue rend 0 doit ACCEPTER,
    masque inchange."""
    assert mesure["CE"]["ce3_delegue_neutre"] == 0, (
        "CE3 = %s : le refus ne vient pas de la delegue"
        % hex(mesure["CE"]["ce3_delegue_neutre"]))


# --------------------------------------------------------------------------- le rayon de souffle

def test_le_rayon_de_souffle_est_borne(mesure):
    """DERIVE du registre : seules les abilities qui posent le bit 3 ET portent leur delegue
    peuvent desormais se voir refuser. Si ce compte enflait sans qu'on l'ait voulu, des casts
    legitimes se mettraient a etre refuses en silence."""
    blast = mesure["blast"]
    assert blast["armes"] == blast["rayon"], (
        "masques armes %s != rayon %s -- un masque arme dont la delegue n'est pas portee reste "
        "permissif, il faut le dire" % (blast["armes"], blast["rayon"]))
    assert blast["rayon"], "rayon VIDE : le fix ne peut mordre nulle part"


def test_le_probe_rend_pass(mesure):
    assert mesure["rc"] == 0, "le probe rend FAIL -- lire sa sortie ci-dessus"
