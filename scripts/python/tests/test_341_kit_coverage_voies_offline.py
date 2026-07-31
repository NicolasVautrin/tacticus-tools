"""#341 -- garde OFFLINE de `audit_kit_coverage.py` : les voies d'attribution CONDITIONNELLES
restent lues, et le total ne les avale pas.

Pourquoi une garde : l'audit lisait 2 des 5 voies derivables du gameconfig (`activeAbilities`,
`passiveAbilities`) et taisait `mythicAbilities` + la relique EQUIPABLE `items[*].abilityId`,
soit 43 abilities dont AUCUNE n'est portee. C'est la meme cecite qui a fait rendre un faux
« 0 unite, DEAD » a `unit_map find --ability` (#323, `case-323-unit-map-attribution-voies.md`).
Une cecite de recensement ne se trompe pas : elle ATTESTE -- rien en aval ne la contredit.

Cas NOMME = `NetherRealmCasket` / `necroSpyder`, le cas canonique de #323.

Usage : depuis `scripts/python/`  ->  python -m pytest tests/test_341_kit_coverage_voies_offline.py -q
"""
from __future__ import annotations

import os
import sys

import pytest

_PYROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PYROOT not in sys.path:
    sys.path.insert(0, _PYROOT)

import audit_kit_coverage as AKC          # noqa: E402
import enum_maps as EM                    # noqa: E402
import unit_map as UM                     # noqa: E402


@pytest.fixture(scope="module")
def cond():
    return AKC.collect_conditionnelles({v: k for k, v in EM.ACTIVE_ABILITY_TYPE.items()})


def test_cas_nomme_netherrealmcasket_est_vu_par_la_voie_item(cond):
    """#323 : `necroSpyder` porte `NetherRealmCasket` par la RELIQUE equipable -- l'ability
    n'apparait sur AUCUN champ de sa fiche d'unite. C'est exactement l'etat qui a fait classer
    l'`EffectType` 1456 `NetherRealmCasket_LivingMetalBonus` en DEAD."""
    hit = [c for c in cond if c["name"] == "NetherRealmCasket"]
    assert hit, (
        "REGRESSION #341 : `NetherRealmCasket` n'est plus vue par l'audit de kit. C'est l'etat "
        "de cecite qui a fait classer l'effet 1456 en DEAD (#310) : la voie RELIQUE n'etait pas "
        "lue. Attendu : voie `item` (items/R_Booster_Crit_NetherRealmCasket.allowedUnits "
        "contient necroSpyder)."
    )
    c = hit[0]
    assert c["voie"] == "item", "voie attendue `item`, lue: %s" % c["voie"]
    assert "necroSpyder" in c["carriers"], (
        "porteur `necroSpyder` absent ; porteurs lus: %s" % c["carriers"])


def test_les_deux_voies_conditionnelles_sont_non_vides(cond):
    """Un audit qui rend zero sur une voie a plus de chances d'etre casse que d'avoir raison :
    la mesure #341 vaut 11 mythiques + 32 reliques. On garde le PLANCHER, pas le chiffre exact
    (il bouge a chaque build), pour que la garde survive a une mise a jour du jeu."""
    for voie in AKC.VOIES_CONDITIONNELLES:
        n = len({c["name"] for c in cond if c["voie"] == voie})
        assert n > 0, (
            "REGRESSION #341 : la voie conditionnelle `%s` ne rend plus AUCUNE ability sur les "
            "unites lineup. Soit `unit_map` a cesse de l'indexer, soit l'audit a cesse de la "
            "lire -- dans les deux cas le doc sous-estime SILENCIEUSEMENT le travail restant."
            % voie)


def test_le_total_ne_compte_PAS_les_voies_conditionnelles():
    """Symetrique de la garde precedente : les fondre dans le total ferait remonter en tete du
    classement un heros riche en reliques EQUIPABLES dont le kit, lui, est porte. Une mythique
    se DEBLOQUE et une relique s'EQUIPE : ce n'est pas du kit intrinseque."""
    rows = AKC.collect()
    noms_cond = {c["name"] for c in
                 AKC.collect_conditionnelles({v: k for k, v in EM.ACTIVE_ABILITY_TYPE.items()})}
    comptes = {a["name"] for r in rows for a in r["actives"]}
    comptes |= {p["name"] for r in rows for p in r["passives"]}
    fuite = noms_cond & comptes
    assert not fuite, (
        "REGRESSION #341 : %d ability(s) conditionnelle(s) ont fui dans le compte du kit "
        "intrinseque (%s). Le total de `kit-coverage.md` cesserait d'etre comparable a ses "
        "valeurs historiques." % (len(fuite), sorted(fuite)[:5]))


def test_les_voies_lues_couvrent_celles_que_unit_map_indexe_sur_lineup():
    """Contre-garde d'INVENTAIRE : si `unit_map` gagne une 6e voie qui touche une unite lineup,
    ce test tombe -- et c'est voulu. Sans lui, l'audit resterait aveugle a la voie NEUVE sans
    que rien ne le signale, ce qui est precisement le mode de defaillance de #323."""
    lues = {"active", "passive"} | set(AKC.VOIES_CONDITIONNELLES)
    touchent_lineup = {v for k in UM.all_kits() if k.get("kind") == "lineup"
                       for v, a in (k.get("voies") or {}).items() if a}
    oubliees = touchent_lineup - lues
    assert not oubliees, (
        "REGRESSION #341 : la/les voie(s) %s touchent une unite lineup et ne sont lues NI par le "
        "corps de l'audit NI par sa section conditionnelle. Les ajouter a "
        "`VOIES_CONDITIONNELLES` (ou au corps si elles relevent du kit intrinseque)."
        % sorted(oubliees))


def test_controle_negatif_un_passif_PORTE_est_bien_vu_comme_couvert():
    """Sans ce controle, un predicat de couverture devenu permissif ferait passer toute la garde
    au vert en rendant l'audit inutile dans l'autre sens (tout compte comme porte)."""
    assert AKC._passive_covered("RelentlessMarch"), (
        "`RelentlessMarch` est portee (#328 : ABILITY_TRIGGERS + RelentlessMarch_Effect) et le "
        "predicat ne la voit plus couverte -- l'audit va la re-compter comme travail restant.")
    assert not AKC._passive_covered("ZzzAbilityQuiNExistePas"), (
        "le predicat de couverture est devenu PERMISSIF : il declare porte un nom inexistant.")
