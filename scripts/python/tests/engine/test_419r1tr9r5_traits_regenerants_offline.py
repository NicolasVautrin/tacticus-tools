"""#419-r1-tr9-r5 OFFLINE -- forcer les PV d'un porteur REGENERANT ne tient pas, et l'outil le dit.

LA PREMISSE DE LA FICHE ETAIT FAUSSE, DEUX FOIS. Elle disait « `--unit-stat
necroWarden:RemainingHealth=N` ne mord pas -- 300 ressort a 2008 », puis se RE-QUALIFIAIT en
« 2008 est l'ARMURE de necroWarden, relue par trois runners independants ». Les deux sont
refutees par la mesure du 2026-08-15 (session 93, build `t6dpr4k06g`, board MC1_67) :

  * le patch MORD -- le BC envoye a `initAndStart` porte bien `RemainingHealth = 300` pour
    `necroWarden` comme pour ses deux temoins (lu dans le state-file) ;
  * l'armure de `necroWarden` vaut `armor=0 / armorMax=0` (`observeBattle`), donc `2008` n'est
    PAS son armure ;
  * `necroWarden` sort a `hp=1154/8536` quand `astraBullgryn` et `tauAunShi`, MEME montage, MEME
    patch, sortent a `300`. Et apres UN tour complet, il passe a `hp=2008` -- le nombre exact de
    la fiche.

La cause est le trait `LivingMetal` (« Regenerates {[hpPct]}% of its max Health at the start of
the players' turn », `globalValues.traitVariables.livingMetalHp = 10`) :
`1154 = 300 + round(8536 x 10%)` et `2008 = 300 + 2 x 854`. Ce n'est pas un defaut de l'outil,
c'est un PIEGE DE MESURE -- que `rl_duel` avertit desormais, comme il le fait deja pour un champ
jamais lu (#342 `Shield`) et pour un champ recalcule (#914-r1).

Ce fichier garde la DERIVATION (jamais une liste en dur) et l'arithmetique qui a ferme le residu.
"""
from __future__ import annotations

#: Perimetre : le detecteur et ses DEUX entrees -- la description i2 (qui dit « regenerate ») et
#: le gameconfig (qui porte le montant). Le seed BC y entre parce que le gisement (13 porteurs)
#: s'en derive.
DECLENCHEUR = {
    "chemins": (
        "scripts/python/rl_duel.py",
        "scripts/python/gameconfig.py",
        "data/i2_en.json",
        "data/seed-bc.json",
        "data/symbols/*/gameconfig.json",
    ),
    "build": False,
    "toujours": False,
    "raison": "Offline : garde que `--unit-stat RemainingHealth/Health` avertit sur un porteur "
              "REGENERANT (#419-r1-tr9-r5), que la liste des traits concernes est DERIVEE de i2 "
              "et du gameconfig (jamais ecrite en dur), et fige l'arithmetique mesuree qui a "
              "refute les DEUX lectures de la fiche (ni « le patch ne mord pas », ni « 2008 est "
              "l'armure » : c'est 300 + k x 10% des PV max).",
}

import json          # noqa: E402  (le DECLENCHEUR doit rester en tete, cf. `probe_486r15`)
import re            # noqa: E402
import sys           # noqa: E402
from pathlib import Path                                                      # noqa: E402

import pytest        # noqa: E402

_SP = Path(__file__).resolve().parents[2]
if str(_SP) not in sys.path:
    sys.path.insert(0, str(_SP))

import gameconfig as G                                                        # noqa: E402
import rl_duel as D                                                           # noqa: E402

_SEED = _SP.parents[1] / "data" / "seed-bc.json"


def _traits_regenerants_du_corpus() -> list:
    """Traits dont la description i2 parle de regeneration -- DERIVE de `data/i2_en.json`."""
    i2 = json.loads((_SP.parents[1] / "data" / "i2_en.json").read_text(encoding="utf-8"))
    out = []
    for cle, texte in i2.items():
        m = re.match(r"^Traits/(\w+)_Description$", cle)
        if m and isinstance(texte, str) and re.search(r"regenerat", texte, re.I):
            out.append(m.group(1))
    return sorted(out)


# ---------------------------------------------------- 1. la DERIVATION, non degeneree et ancree
def test_le_corpus_porte_au_moins_un_trait_regenerant():
    """Sans ce cran, tous les etages suivants pourraient etre vacants sans qu'on le voie."""
    traits = _traits_regenerants_du_corpus()
    assert traits, ("aucun trait dont la description i2 parle de regeneration -- la derivation "
                    "ne mesure plus rien ; re-mesurer avant de toucher au warn")


def test_livingmetal_est_reconnu_avec_son_montant():
    """`LivingMetal` -> 10 %, MESURE au moment ou le residu a ete ferme.

    Le chiffre est fige AU SITE : s'il bouge, ce test ROUGIT et c'est voulu -- le message d'aide
    annonce un pourcentage a l'utilisateur, donc un glissement silencieux le rendrait faux.
    """
    porte = {"Traits": ["Xenos", "Hero", "LivingMetal", "Mechanical"]}
    assert D._traits_regenerants_de(porte) == [("LivingMetal", 10)], (
        "LivingMetal n'est plus reconnu, ou son montant a change "
        f"(traitVariables.livingMetalHp = {G.global_value('livingMetalHp')!r} ; "
        f"gameconfig.trait('LivingMetal') = {G.trait('LivingMetal')})")


def test_le_gisement_est_reel_au_seed_bc():
    """Des porteurs existent : un warn qui ne peut jamais se declencher ne garde rien."""
    traits = set(_traits_regenerants_du_corpus())
    bc = json.loads(_SEED.read_text(encoding="utf-8"))
    porteurs = [u.get("Id") for u in (bc.get("Units") or [])
                if traits & set(u.get("Traits") or [])]
    assert len(porteurs) >= 5, (
        f"seulement {len(porteurs)} porteur(s) regenerant(s) au seed BC : {porteurs}")
    assert "necroWarden" in porteurs, "le porteur MESURE n'est plus au seed BC"


# ------------------------------------------------ 2. le DETECTEUR ne parle que pour un regenerant
def test_silence_sur_un_porteur_non_regenerant():
    assert D._traits_regenerants_de({"Traits": ["Imperial", "Hero", "BigTarget"]}) == []
    assert D._traits_regenerants_de({"Traits": []}) == []
    assert D._traits_regenerants_de({}) == []


def test_trait_inconnu_ne_fabrique_aucun_verdict():
    """Un id de trait absent d'i2 n'a pas de description -> il n'est pas declare regenerant."""
    assert D._traits_regenerants_de({"Traits": ["TraitQuiNExistePas_ac8b"]}) == []


def test_i2_illisible_rend_une_liste_vide(monkeypatch):
    """Entree non mesurable -> SILENCE, jamais un verdict invente (meme regle qu'`host_inputs`)."""
    def _boom(_):
        raise RuntimeError("i2 illisible")
    monkeypatch.setattr(G, "trait_description", _boom)
    assert D._traits_regenerants_de({"Traits": ["LivingMetal"]}) == []


def test_regenerant_sans_montant_lisible_avertit_quand_meme(monkeypatch):
    """Montant introuvable -> `(trait, None)`, pour avertir SANS chiffre plutot qu'en inventer un."""
    monkeypatch.setattr(G, "trait_description", lambda t: "Regenerates some Health.")
    monkeypatch.setattr(G, "trait", lambda t: {"id": t, "variables": {"fooPct": 3}})
    assert D._traits_regenerants_de({"Traits": ["Bidon"]}) == [("Bidon", None)]


# ------------------------------------- 3. l'ARITHMETIQUE qui a refute les DEUX lectures de la fiche
def test_l_arithmetique_mesuree_explique_1154_et_2008():
    """`hpMax = 8536`, `pct = 10` -> tick de 854 ; `300 + 854 = 1154` ; `300 + 2 x 854 = 2008`.

    Ces trois nombres sont des MESURES live (`observeBattle`), pas un modele : `1154` au build,
    `2008` apres un tour complet. Le test fige la seule lecture qui les produit toutes les deux --
    et refute par la meme occasion « 2008 est l'armure », mesuree a `0`.
    """
    hp_max, pct, force = 8536, 10, 300
    tick = round(hp_max * pct / 100)
    assert tick == 854, tick
    assert force + tick == 1154
    assert force + 2 * tick == 2008
