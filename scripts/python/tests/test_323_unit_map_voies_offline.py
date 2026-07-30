"""CLIQUET #323 -- `unit_map find --ability` voit-il TOUTES les voies d'attribution ?

Le cas NOMME que ce fichier garde : **`NetherRealmCasket` / `necroSpyder` / TriggeredAbilityType
1462**. Il est nomme parce qu'il a COUTE : #310 a classe l'effet `NetherRealmCasket_LivingMetalBonus`
(EffectType 1456) DEAD sur la foi d'un `unit_map.py find --ability NetherRealmCasket` qui rendait
« 0 unite ». L'outil ne lisait que `activeAbilities` + `passiveAbilities` -- il etait aveugle a la
RELIQUE. Trois heros du pool figurent dans `items/R_Booster_Crit_NetherRealmCasket.allowedUnits`,
et `necroSpyder` la porte EQUIPEE dans le seed BC (`Units[].TertiaryAbility = 1462`). Un residu
avait donc ete ferme sur un faux negatif -- de l'OUTIL DE RECENSEMENT lui-meme.

Ce que le cliquet mord (mutations verifiees ROUGE avant vert) :
  * retirer `item` de `unit_map.VOIE_KEYS`         -> test_1462, test_les_trois_heros
  * faire rendre `{}` a `unit_map._relic_items()`  -> test_1462, test_les_trois_heros, test_table
  * retirer `relic`/`mythic` de `UNIT_ABILITY_FIELDS` -> test_table, test_voies_npc_relique
  * supprimer le pied de page de `_zero_carrier_footer` -> test_zero_ne_prouve_rien

Re-derivation des chiffres : `python scripts/python/probe_323_ability_carrier_voies.py`.
100 % OFFLINE (gameconfig + `data/seed-bc.json`) -- aucune session Frida.
ASCII only (cp1252).
"""
from __future__ import annotations

import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path

PYDIR = Path(__file__).resolve().parents[1]          # scripts/python
ROOT = Path(__file__).resolve().parents[3]           # racine du checkout
sys.path.insert(0, str(PYDIR))

import unit_map as UM                                            # noqa: E402
from engine.entities.triggered_ability_type import TriggeredAbilityType  # noqa: E402

CASKET = "NetherRealmCasket"
CASKET_ITEM = "R_Booster_Crit_NetherRealmCasket"
CASKET_HEROES = ("necroWarden", "necroSpyder", "necroDestroyer")
CASKET_TRIGGERED_ID = 1462          # `TriggeredAbilityType.NetherRealmCasket`


def _kit(uid: str) -> dict:
    k = UM.kit(uid)
    assert k is not None, f"unite absente du gameconfig : {uid}"
    return k


def test_1462_necro_spyder_porte_le_casket_par_la_voie_relique():
    """LE CAS NOMME. `necroSpyder` porte `NetherRealmCasket` -- par la voie ITEM, pas par son kit."""
    k = _kit("necroSpyder")
    voies = UM.carrier_voies(k, CASKET)
    assert voies, (
        "REGRESSION #323 : `necroSpyder` ne porte plus `NetherRealmCasket` par AUCUNE voie. "
        "C'est exactement l'etat qui a fait classer l'effet 1456 "
        "`NetherRealmCasket_LivingMetalBonus` en DEAD (#310) : l'outil de recensement etait "
        "aveugle a la RELIQUE. La voie attendue est `item` "
        "(items/" + CASKET_ITEM + ".allowedUnits contient necroSpyder)."
    )
    assert "item" in voies, (
        "REGRESSION #323 : `necroSpyder` porte `NetherRealmCasket` par " + str(voies) + " mais PAS "
        "par la voie `item`. La relique EQUIPABLE (`items[*].abilityId` + `allowedUnits`) est LA "
        "voie que `unit_map` ne lisait pas avant #323."
    )
    assert any(r["ability"] == CASKET and r["item"] == CASKET_ITEM
               for r in k["relic_items"]), (
        "REGRESSION #323 : le kit de `necroSpyder` n'expose plus l'item relique "
        + CASKET_ITEM + " -> impossible de savoir PAR QUOI l'ability lui arrive."
    )


def test_les_trois_heros_allowedUnits_du_casket_sont_remontes():
    """Les 3 heros de `allowedUnits` -- ceux dont #310 disait qu'il n'en existait AUCUN."""
    got = [uid for uid in CASKET_HEROES if UM.carrier_voies(_kit(uid), CASKET)]
    assert sorted(got) == sorted(CASKET_HEROES), (
        "REGRESSION #323 : `find --ability " + CASKET + "` ne remonte que " + str(sorted(got))
        + " au lieu des 3 heros de allowedUnits " + str(sorted(CASKET_HEROES)) + ". Un « 0 "
        "porteur » rendu par cet outil a DEJA FERME UN RESIDU A TORT (#310 -> #317)."
    )


def test_le_seed_bc_porte_la_relique_EQUIPEE_1462_sur_necro_spyder():
    """La seconde source : la relique n'est pas qu'eligible, elle est EQUIPEE dans le seed BC."""
    seed_p = ROOT / "data" / "seed-bc.json"
    assert seed_p.exists(), "data/seed-bc.json absent -- entree VERSIONNEE, elle doit etre la"
    seed = json.loads(seed_p.read_text(encoding="utf-8"))
    equipped = {u.get("Id"): u.get("TertiaryAbility") for u in (seed.get("Units") or [])
                if u.get("TertiaryAbility")}
    assert equipped.get("necroSpyder") == CASKET_TRIGGERED_ID, (
        "REGRESSION #323 : `necroSpyder` ne porte plus TertiaryAbility="
        + str(CASKET_TRIGGERED_ID) + " dans data/seed-bc.json (mesure : "
        + str(equipped.get("necroSpyder")) + "). C'est la SECONDE source qui prouve que la voie "
        "relique n'est pas theorique : le porteur l'a EQUIPEE en bataille."
    )
    assert TriggeredAbilityType(CASKET_TRIGGERED_ID).name == CASKET, (
        "REGRESSION #323 : TriggeredAbilityType(" + str(CASKET_TRIGGERED_ID) + ") ne vaut plus "
        "`" + CASKET + "`. Qualifier l'enum est OBLIGATOIRE ici : l'EffectType 1462 est "
        "`TheArdentBlade`, et l'effet mort-a-tort de #310 est l'EffectType 1456 "
        "`NetherRealmCasket_LivingMetalBonus` -- trois ids voisins, trois enums differents."
    )


def test_la_table_des_voies_couvertes_reste_complete():
    """Cliquet de COUVERTURE : chacune des 5 voies derivables doit avoir des porteurs REELS."""
    kits = UM.all_kits()
    vides = [v for v in UM.VOIE_KEYS
             if not any((k.get("voies") or {}).get(v) for k in kits)]
    assert not vides, (
        "REGRESSION #323 : la/les voie(s) " + str(vides) + " ne remonte(nt) plus AUCUN porteur. "
        "Une voie qui disparait silencieusement rend a nouveau des « 0 unite » qui se lisent "
        "comme des preuves de mort. Voies attendues : " + str(list(UM.VOIE_KEYS)) + "."
    )
    assert len(UM.VOIES_NON_COUVERTES) >= 4, (
        "REGRESSION #323 : la liste des voies NON couvertes a maigri. Une couverture partielle "
        "ASSUMEE et documentee (trait / liveevent / summon / tile) vaut mille fois mieux qu'une "
        "couverture partielle SILENCIEUSE -- c'est tout l'objet du cas."
    )


def test_voies_npc_relique_et_mythique_restent_lisibles():
    """`relicAbilities` (npc boss) et `mythicAbilities` (MoW) : les deux autres voies muettes."""
    assert "relic" in UM.carrier_voies(_kit("tauNpcFarsight"), "DawnBlade"), (
        "REGRESSION #323 : `tauNpcFarsight` ne porte plus `DawnBlade` par `relicAbilities`. "
        "C'est la voie EN DUR (5 npc Farsight), distincte de la relique EQUIPABLE du hero."
    )
    assert "mythic" in UM.carrier_voies(_kit("necroReanimator"), "GuardianConstruct"), (
        "REGRESSION #323 : `necroReanimator` ne porte plus `GuardianConstruct` par "
        "`mythicAbilities`. Les 11 abilities mythiques de Machine of War n'apparaissent dans "
        "AUCUN autre champ -- les rater rend « 0 porteur » sur 11 abilities de MoW."
    )


def test_zero_ne_prouve_rien_le_pied_de_page_nomme_les_voies_non_couvertes():
    """Un « 0 unite » DOIT dire pourquoi il ne prouve pas la mort -- sinon il se lit comme DEAD."""
    class _A:
        melee_hits = ranged_hits = None
        trait = faction = None
        ability = "NoSuchAbilityWhatsoever"
        ability_voie = "all"
        no_dmg_mods = False
    buf = io.StringIO()
    with redirect_stdout(buf):
        UM.cmd_find(_A())
    out = buf.getvalue()
    assert "=== 0 unit" in out, "le montage n'a pas produit le zero attendu :\n" + out
    assert "CE ZERO NE PROUVE PAS QUE L'ABILITY EST MORTE" in out, (
        "REGRESSION #323 : `find --ability` rend un « 0 unite » NU. C'est litteralement la "
        "sortie que #310 a lue comme une preuve de mort. Le zero doit porter le pied de page "
        "qui nomme les voies NON couvertes.\nSortie mesuree :\n" + out
    )
    for name, _ in UM.VOIES_NON_COUVERTES:
        assert name in out, (
            "REGRESSION #323 : le pied de page du zero ne cite plus la voie non couverte `"
            + name + "`. Une voie tue est une voie qu'on re-oubliera.\nSortie mesuree :\n" + out
        )


def test_control_une_ability_sans_aucun_porteur_reste_a_zero():
    """CONTROLE NEGATIF : le correctif n'invente pas de porteurs -- `ObeisanceGenerators` en a 0.

    Sans ce controle, un `carrier_voies` devenu permissif (ex. match vide -> True) ferait passer
    tous les tests ci-dessus au vert en rendant l'outil INUTILE dans l'autre sens."""
    kits = UM.all_kits()
    porteurs = [k["id"] for k in kits if UM.carrier_voies(k, "ObeisanceGenerators")]
    assert porteurs == [], (
        "REGRESSION #323 : `ObeisanceGenerators` remonte des porteurs " + str(porteurs) + " alors "
        "que le balayage des 5 voies en donne ZERO (verdict de `case-ischarging-hits-channel` "
        "par. 4, qui TIENT). Un recensement qui trouve des porteurs partout ne vaut pas mieux "
        "qu'un recensement aveugle."
    )
