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

Ce qu'elle NE tenait PAS -- que le natif rende bien `LightImUpPlaybook` pour `1103` -- a ete
CONFRONTE le 2026-07-31 apres reinject (etape 3 du probe, verte pour les trois abilities).

#375 y ajoute deux verrous, tous deux nes d'un ECHEC MESURE :
  * la FIXTURE doit survivre au CHEMIN DU BUILD. Elle ne survivait pas : `_load_seed_bc` re-
    synthetisait `LightImUp` depuis le gameconfig vivant et revertait le patch, EN SILENCE.
  * l'echelle 971/972 doit VERIFIER SON OBSERVABILITE avant de conclure. A l'armure nominale les
    deux references sont EGALES (l'etage aval ecrase l'ecart de 1) : un verdict lu la serait vide.

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
    """VU ROUGE par DEUX mutations adversariales (mesure du 2026-07-31) :
      (a) `triggered: "TriggeredAbilityType"` -> `"ActiveAbilityType"` dans `triggered-predict.ts`
          (= le bug de #369, reintroduit) -> 1 failed, 9 passed ;
      (b) suppression de l'echo `abilityKind: keySpace` du litteral `out` de `rpc-nc-predict.ts`
          -> 1 failed, 9 passed."""
    r = P369.step1_harness(verbose=False)
    rouges = [c["name"] for c in r["checks"] if not c["ok"]]
    assert r["ok"], "garde structurelle ROUGE sur : %s" % ", ".join(rouges)


def test_la_garde_de_l_echo_vise_le_chemin_SUCCES_pas_le_fichier_entier():
    """VERROU DU TROU TROUVE PAR LA MUTATION (b). La premiere version cherchait
    `"abilityKind: keySpace"` dans TOUT le fichier ; comme la meme chaine apparait dans les retours
    d'ERREUR (`return { ok: false, abilityKind: keySpace, ... }`), supprimer l'echo du chemin
    SUCCES laissait la garde VERTE. Ce test fige l'extraction ciblee sur des sources synthetiques :
    il ne depend d'aucun fichier, donc il ne peut pas re-verdir par accident."""
    avec_echo = (
        '        if (x) return { ok: false, abilityKind: keySpace, via, error: "boom" };\n'
        '        const out: Record<string, unknown> = {\n'
        '            ok: true, via, abilityKind: keySpace, playbookSource: load.source,\n'
        '        };\n')
    sans_echo = (
        '        if (x) return { ok: false, abilityKind: keySpace, via, error: "boom" };\n'
        '        const out: Record<string, unknown> = {\n'
        '            ok: true, via, playbookSource: load.source,\n'
        '        };\n')
    assert "abilityKind: keySpace" in P369._success_payload(avec_echo)
    # Le fichier CONTIENT toujours la chaine (dans le retour d'erreur) -- c'est exactement le piege.
    assert "abilityKind: keySpace" in sans_echo
    assert "abilityKind: keySpace" not in P369._success_payload(sans_echo)


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


# --- #375 : la fixture doit SURVIVRE au chemin du build -----------------------------------------

def test_la_fixture_SURVIT_au_chemin_du_build(tmp_path):
    """Le seul test qui prouve quelque chose : relire par `_load_seed_bc`, pas depuis le disque.

    Ecrire dans un fichier ne dit RIEN de ce que le build lira -- c'est exactement l'ecart qui a
    rendu la fixture de #369 inerte pendant toute sa duree de vie."""
    fx = P369.build_regime_seed_bc(tmp_path / "seed-bc-regime.json")
    assert fx["pins"] == ["PassiveAbilities/LightImUp"], fx["pins"]
    rt = fx["roundtrip"]
    assert rt["min_dmg"] == fx["min_dmg"], rt
    assert rt["max_dmg"] == fx["max_dmg"], rt
    # ... et le multiplicateur de rarete reste neutralise DE L'AUTRE COTE du rattrapage.
    assert rt["rarity_affected"] == [], rt


def test_sans_epingle_le_patch_est_ECRASE_EN_SILENCE(tmp_path):
    """REPRODUCTION du bug de #375, et preuve que c'est bien l'epingle qui le ferme.

    On retire le sidecar : `refresh_ability_configs` re-synthetise alors `LightImUp` depuis le
    gameconfig vivant et REVERTE `minDmg`/`maxDmg` aux valeurs nominales -- sans erreur, sans
    warning. Le regime discriminant n'est jamais joue, et le run a l'air vert."""
    import catalog_inject as CI
    from rl_collect_batch import _load_seed_bc
    fx = P369.build_regime_seed_bc(tmp_path / "seed-bc-regime.json")
    CI.pins_path(fx["path"]).unlink()                  # <- la mutation adversariale
    bc = _load_seed_bc(str(fx["path"]))
    variables = bc["Abilities"]["PassiveAbilities"]["LightImUp"]["Variables"]
    idx = P369._FIXTURE_REGIME["level"] - 1
    assert int(variables["maxDmg"][idx]) != fx["max_dmg"], (
        "sans epingle le patch a survecu -- soit le rattrapage #254 a change, soit la valeur "
        "patchee coincide avec le gameconfig (choisir un autre couple)")
    # ... et la parite visee, seul axe discriminant, est perdue avec lui.
    somme = int(variables["minDmg"][idx]) + int(variables["maxDmg"][idx])
    assert somme % 4 != 3, somme


def test_une_epingle_qui_ne_designe_RIEN_leve(tmp_path):
    """Une epingle orpheline doit ROUGIR, pas se taire : c'est la meme discipline que le patch."""
    import catalog_inject as CI
    from rl_collect_batch import _load_seed_bc
    fx = P369.build_regime_seed_bc(tmp_path / "seed-bc-regime.json")
    CI.write_pins(fx["path"], ["PassiveAbilities/AbilityQuiNExistePas"])
    with pytest.raises(RuntimeError, match="epingles introuvables"):
        _load_seed_bc(str(fx["path"]))


# --- #375 : l'echelle 971/972 verifie SON OBSERVABILITE avant de conclure ------------------------

_LOW = (1166, 1748, 0, 0, 1166, 1748, 1166, 1748)
_HIGH = (1167, 1749, 0, 0, 1167, 1749, 1167, 1749)


def test_le_regime_discriminant_tombe_sur_la_reference_HAUTE():
    """Le verdict vert : la prediction du regime `3 mod 4` egale celle de la reference 972."""
    v = P369.check_half_even(_LOW, _HIGH, _HIGH, 971, 972)
    assert v["status"] == "ok" and v["value"] == 972


def test_la_TRONCATURE_ROUGIT_avec_un_message_VERBATIM():
    """Contre-epreuve : si le natif tronquait, la garde doit le DIRE, pas s'accommoder."""
    v = P369.check_half_even(_LOW, _LOW, _HIGH, 971, 972)
    assert v["status"] == "truncated" and v["value"] == 971
    assert "TRONCATURE (971)" in v["message"]


def test_deux_references_EGALES_rendent_NON_CONFRONTE_jamais_vert():
    """LE verrou de #375. Mesure du 2026-07-31 : a l'armure NOMINALE de la cible, `damage = 971` et
    `damage = 972` rendent tous deux `healthDmgMin = 175`. Les trois montages coincidaient donc, et
    la comparaison `test == high` etait VRAIE -- un vert qui ne mesurait rien. Une reference basse
    egale a la haute doit rendre NON CONFRONTE, jamais OK."""
    plat = (175, 262, 0, 0, 175, 262, 175, 262)
    v = P369.check_half_even(plat, plat, plat, 971, 972)
    assert v["status"] == "not-observable"
    assert "ecrase l'ecart de 1" in v["message"]


def test_une_signature_TIERCE_ROUGIT():
    """Ni la basse ni la haute : le montage a bouge entre les builds -- ECHEC, pas silence."""
    v = P369.check_half_even(_LOW, (1, 2, 3, 4, 5, 6, 7, 8), _HIGH, 971, 972)
    assert v["status"] == "unknown"


def test_aucune_capture_rend_NON_CONFRONTE():
    v = P369.check_half_even(None, _HIGH, _HIGH, 971, 972)
    assert v["status"] == "no-capture"


# --- #375 : la FORME de la reponse muette de `attackUtilityInSteps` ------------------------------

def test_la_reponse_muette_est_la_reponse_ATTENDUE_du_natif():
    """`capturedCount: 0` n'est pas un trou : les deux machines a etats yieldent UN `Fix64(0)` quand
    la gate `IsRegularAttack` refuse (le case ne nomme aucune ability). On asserte cette FORME."""
    resp = {"abilityKind": "triggered", "capturedCount": 0, "triggeredUtilities": [0]}
    for aid in (1103, 1054, 1247):
        v = P369.check_insteps_shape(resp, aid)
        assert v["status"] == "mute-expected", (aid, v)
        assert v["reason"]


def test_une_capture_INATTENDUE_sans_ability_nommee_ROUGIT():
    """Si le natif capturait SANS que le case nomme d'ability, la RE serait fausse -- il faut le
    savoir, pas l'encaisser."""
    resp = {"abilityKind": "triggered", "capturedCount": 1, "triggeredUtilities": [0]}
    v = P369.check_insteps_shape(resp, 1103)
    assert v["status"] == "anomaly"
    assert "attendu 0 / [0]" in v["message"]


def test_le_correctif_du_case_NOMME_inverse_l_attente():
    """Des que le hook echoe `attackAbility` (correctif #375 deploye), la gate doit passer et la
    voie inSteps DOIT capturer. La garde s'inverse toute seule : la prochaine fenetre de reinject
    est auto-verifiante."""
    ok = {"abilityKind": "triggered", "attackAbility": {"resolved": 69},
          "capturedCount": 1, "triggeredUtilities": [3.5]}
    assert P369.check_insteps_shape(ok, 1103)["status"] == "captured"
    ko = {"abilityKind": "triggered", "attackAbility": {"resolved": 69},
          "capturedCount": 0, "triggeredUtilities": [0]}
    v = P369.check_insteps_shape(ko, 1103)
    assert v["status"] == "anomaly" and "REGRESSION" in v["message"]
    # 1247 reste muet MEME avec une ability nommee : son playbook ne surcharge pas la voie attaque.
    assert P369.check_insteps_shape(ko, 1247)["status"] == "mute-expected"


def test_une_erreur_RPC_ne_passe_pas_pour_un_silence_normal():
    resp = {"abilityKind": "triggered", "capturedCount": 0, "triggeredUtilities": [],
            "error": "CalculateAttackUtilityInSteps a leve: boom"}
    v = P369.check_insteps_shape(resp, 1103)
    assert v["status"] == "rpc-error" and "boom" in v["message"]
