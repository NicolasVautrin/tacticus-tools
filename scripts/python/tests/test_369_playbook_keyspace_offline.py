"""#369 -- GARDE du key-space d'enum de `ncPlaybookPredict`. OFFLINE, aucune plateforme requise.

CE QUE CETTE GARDE TIENT, ET POURQUOI ELLE EST OFFLINE
------------------------------------------------------
`ncPlaybookPredict` chargeait toujours par `ActiveAbilityType`. A id egal, `ActiveAbilityType` et
`TriggeredAbilityType` designent des abilities DIFFERENTES -- **233 ids** collisionnent sur
`rnca9r7q6c`, dont **231** avec un membre de nom different. L'oracle rendait donc une valeur
plausible pour la MAUVAISE ability, sans jamais signaler d'erreur : la degradation etait SILENCIEUSE,
donc invisible d'un accord.

La confrontation LIVE du correctif exige une fenetre de reinject (le lot touche `frida/hooks/*`), et
un agent ne reinjecte pas. Cette garde est donc ce qui tient le correctif entre-temps -- et elle
n'est pas un pis-aller : ce qu'elle verrouille (la COLLISION des enums, la DESAMBIGUISATION par type
de parametre dans le harnais, l'existence d'un REGIME discriminant) est entierement determine par la
table de symboles versionnee et par les sources du hook. Rien de tout cela ne depend de l'etat de
bataille.

Ce qu'elle NE tient PAS, et c'est ecrit tel quel dans le case-doc : que le natif, une fois reinjecte,
rende bien `LightImUpPlaybook` pour `1103`. C'est l'etape 3 du probe, NON CONFRONTEE.

ASCII only (cp1252).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[1]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import probe_369_playbook_keyspace as P369                              # noqa: E402


# --- la collision des key-spaces est REELLE ------------------------------------------------------

def test_les_deux_enums_collisionnent_massivement():
    """Sans collision, indexer sur le mauvais key-space serait inoffensif. Elle est massive."""
    r = P369.step0_collision(verbose=False)
    assert r["ok"], r
    # Borne PLANCHER, pas egalite : le compte exact bouge d'un build a l'autre, le fait non.
    assert r["n_divergent"] >= 100, (
        "seulement %d ids designent des abilities differentes selon l'enum -- la collision "
        "mesuree etait de 231 sur rnca9r7q6c ; verifier la table de symboles" % r["n_divergent"])


def test_les_trois_cas_mesures_sont_bien_des_collisions():
    """Les trois ids du rapport #384, verifies contre `enums.tsv` -- pas herites."""
    r = P369.step0_collision(verbose=False)
    par_id = {c["id"]: c for c in r["cases"]}
    assert par_id[1103]["triggered"] == "LightImUp"
    assert par_id[1103]["active"] == "Supercharge"
    assert par_id[1054]["triggered"] == "MassiveScythingTalons"
    assert par_id[1054]["active"] == "CallRipperSwarms2"
    # 1247 n'existe PAS cote actif : c'est ce qui faisait retomber le RPC sur le fallback.
    assert par_id[1247]["triggered"] == "FuryOfTheAncients"
    assert par_id[1247]["active"] is None


# --- le harnais desambiguise (et cette garde ROUGIT sur mutation) --------------------------------

def test_le_harnais_route_par_key_space():
    """VU ROUGE par mutation adversariale : remplacer `triggered: "TriggeredAbilityType"` par
    `"ActiveAbilityType"` dans `frida/hooks/features/ai-step/triggered-predict.ts` fait echouer
    exactement ce test (mesure du 2026-07-31, ligne `key-space triggered = ... ROUGE`)."""
    r = P369.step1_harness(verbose=False)
    rouges = [c["name"] for c in r["checks"] if not c["ok"]]
    assert r["ok"], "garde structurelle ROUGE sur : %s" % ", ".join(rouges)


# --- le regime discriminant existe, et le montage l'atteint --------------------------------------

def test_le_couple_nominal_ne_discrimine_PAS():
    """Verrou de NON-VACUITE : au niveau 50 nominal (`831 + 1109`), les deux formes rendent la MEME
    valeur. Un run live a ce regime ne conclurait RIEN -- c'est precisement pourquoi le montage
    existe. Si ce test devenait vert par accident, le montage n'aurait plus de sens et il faudrait
    le redemontrer."""
    f = P369.discriminating_forms(831, 1109)
    assert f["sum_mod_4"] == 0
    assert not f["discriminating"], f
    assert f["trunc"] == f["half_even"]


def test_le_montage_atteint_le_regime_discriminant(tmp_path):
    """Le seed BC patche porte le couple `3 mod 4`, et les deux formes divergent d'exactement 1,
    le demi-vers-le-pair MONTANT (mirror de `Fix64.Round`)."""
    fx = P369.build_regime_seed_bc(tmp_path / "seed-bc-regime.json")
    assert fx["sum_mod_4"] == 3, fx
    assert fx["discriminating"]
    assert fx["half_even"] - fx["trunc"] == 1, fx
    # Le montage a bien ECRIT (une des trois fautes de #237 etait d'echouer en silence).
    rep = fx["report"]
    assert rep["written"]["minDmg"]["value"] == fx["min_dmg"]
    assert rep["written"]["maxDmg"]["value"] == fx["max_dmg"]
    # ... et il a neutralise le multiplicateur de rarete, sans quoi la valeur ECRITE ne serait pas
    # la valeur LUE et la parite visee serait perdue en silence.
    assert rep["rarity_neutralized"], rep


def test_le_montage_ROUGIT_si_l_ability_ou_la_variable_manque(tmp_path):
    """Un patch qui ne s'applique pas doit LEVER, jamais rendre un BC inchange qu'on croirait
    patche. C'est la lecon de #237 (deux des trois ecritures echouaient en silence)."""
    import copy
    import json as _json
    import catalog_inject as CI
    bc = copy.deepcopy(_json.loads(CI.SEED_BC.read_text(encoding="utf-8")))
    with pytest.raises(KeyError):
        CI.patch_ability_variables(bc, "AbilityQuiNExistePas", 50, {"minDmg": 1})
    with pytest.raises(KeyError):
        CI.patch_ability_variables(bc, "LightImUp", 50, {"variableQuiNExistePas": 1})


# --- le verdict live : le mode de panne ACTUEL doit rougir, message VERBATIM ---------------------

def test_un_id_triggered_qui_resout_sur_un_playbook_d_active_ROUGIT():
    """LE mode de panne mesure par #384 : `1103` (triggered `LightImUp`) resolvant sur
    `SuperchargePlaybook`. Le verdict est une fonction PURE de la reponse RPC, donc verrouillable
    sans plateforme -- et le message est celui que la garde live publiera."""
    resp = {"abilityKind": "triggered", "playbookClass": "SuperchargePlaybook",
            "ability": 1103, "capturedCount": 2}
    v = P369.check_keyspace_response(resp, 1103, "LightImUp", "LightImUpPlaybook")
    assert v["status"] == "mismatch"
    assert v["message"] == (
        "#369 KEY-SPACE : ability TRIGGERED 1103 (LightImUp) a resolu sur le playbook"
        " 'SuperchargePlaybook' -- attendu 'LightImUpPlaybook'."
        " ncPlaybookPredict interroge le key-space ActiveAbilityType.")


def test_le_fallback_par_defaut_ROUGIT_aussi():
    """L'autre face du mode de panne : `1247` n'existe pas cote actif, le RPC retombait sur
    `DefaultActiveAbilityPlaybook` -- une reponse plausible a une question sans reponse."""
    resp = {"abilityKind": "triggered", "playbookClass": "DefaultActiveAbilityPlaybook"}
    v = P369.check_keyspace_response(resp, 1247, "FuryOfTheAncients", "FuryOfTheAncientsPlaybook")
    assert v["status"] == "mismatch"
    assert "DefaultActiveAbilityPlaybook" in v["message"]


def test_un_hook_anterieur_est_DETECTE_et_pas_lu():
    """Un hook d'avant #369 ne connait pas `abilityKind` : sa reponse ne le porte pas. On rend
    NON CONFRONTE et on ne lit AUCUN chiffre -- lire `captured` reviendrait a valider la mauvaise
    ability, exactement l'accord qu'il ne faut pas maquiller."""
    resp = {"playbookClass": "SuperchargePlaybook", "capturedCount": 3,
            "captured": [{"minDamage": 999}]}
    v = P369.check_keyspace_response(resp, 1103, "LightImUp", "LightImUpPlaybook")
    assert v["status"] == "not_reinjected"
    assert v["message"] == P369.HOOK_NOT_REINJECTED
    assert "fenetre de reinject" in v["message"]


def test_le_bon_playbook_passe():
    """Contre-epreuve : sans elle, un verdict qui rougirait TOUJOURS passerait pour une garde."""
    resp = {"abilityKind": "triggered", "playbookClass": "LightImUpPlaybook"}
    v = P369.check_keyspace_response(resp, 1103, "LightImUp", "LightImUpPlaybook")
    assert v["status"] == "ok"
    assert v["message"] is None
