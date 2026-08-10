"""CONFRONT LIVE de la NATURE du coup differe `1237` -- #503-r5 (residu de #503-r1).

CE QUE CE FICHIER GARDE. `overwhelming_wrath_attack_tree()` porte `is_melee=True`, et c'est une
MESURE, pas une lecture du noeud : les cinq surcharges de
`IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage` ne portent AUCUN bit melee/ranged,
et c'est precisement pour ca que la question ne se tranche qu'au comportement. Le mirror a porte
`None` jusqu'a cette tranche -- un choix PERMISSIF, qui faisait taire les gates defensifs de melee
des cibles.

LE MONTAGE EST LE DISCRIMINANT, et il tient en une greffe : le trait `Terrifying` pose sur
`orksNob` (1re cible frappee) derive `TerrifyingAbility`, qui pose `78 Terrifying_ExtraDefense`,
dont l'UNIQUE gate est `IsMeleeAttack`. Mesure du 2026-08-10 :

    u81 GREFFEE, port a `is_melee=None`  : port 8761 vs natif **6132**  (ecart 2629)
    u81 GREFFEE, port a `is_melee=True`  : port 6132 == natif 6132      BIT-EXACT
    u83 TEMOIN (non greffe)              : 10957 == 10957 des DEUX cotes

`8761 x 0,7 = 6132,7` -- exactement `globalValues.terrifyingBonus` = 30 %. Le natif applique donc
un reducteur gate `IsMeleeAttack` sur ce coup.

LE TEMOIN NON GREFFE EST AUSSI IMPORTANT QUE LE POSITIF : sans lui, un ecart sur `u81` ne se
distinguerait pas d'une greffe qui aurait deplace autre chose (elle change le seed BC, donc
potentiellement l'ordre d'unites, les stats, la RNG).

Le montage et TOUTES les lectures vivent dans `scripts/python/probe_503r5_is_melee.py` : une seule
implementation, aucune divergence possible entre ce qui est mesure et ce qui est garde.

ASCII only.
"""
from __future__ import annotations

import pytest

import probe_503r1_overwhelming_wrath_phase2 as P
import probe_503r5_is_melee as R5

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    # PERIMETRE LARGE, pour la meme raison MESUREE que `test_503r1_overwhelming_wrath_phase2_live`
    # : ce fichier importe DEUX probes, dont la fermeture d'import atteint la quasi-totalite de
    # `scripts/python` (dont `catalog_inject`, qui monte le seed BC greffe). Declarer etroit
    # produirait un FAUX VERT.
    # ⚠ Les DEUX formes sont necessaires : `**/` exige un SEGMENT, donc `scripts/python/**/*.py`
    # ne voit PAS `scripts/python/board.py`.
    "chemins": ("scripts/python/*.py", "scripts/python/**/*.py",
                "data/seed-bc.json", "data/boards/**", "data/symbols/**"),
    "build": True,
    "toujours": False,
    "raison": "Confrontation LIVE de la NATURE (melee/ranged) du coup differe 1237, par un gate "
              "defensif natif (`Terrifying_ExtraDefense`, unique gate `IsMeleeAttack`). L'oracle "
              "est le jeu lui-meme, donc un changement de build ou de gameconfig "
              "(`terrifyingBonus`) peut faire changer d'avis sans qu'une ligne du port bouge.",
}


@pytest.fixture(scope="module")
def mesure(live_session):
    """UN SEUL runner pour tout le fichier : le cast et les passages de tour ne sont pas
    rejouables (ils consomment l'actif et l'effet)."""
    return R5.mesurer(live_session, "test_503r5_is_melee", R5.TRAIT)


def _degats(m):
    off = {k: v[0] - v[1] for k, v in P._hp_delta(*m["off_hp"]).items()}
    live = {k: v[0] - v[1] for k, v in P._hp_delta(*m["live_hp"]).items()}
    return off, live


def test_la_greffe_a_pris(mesure):
    """SANS CE GARDE, TOUT LE FICHIER EST UN FAUX VERT : si le trait n'est pas pose, aucun gate
    `IsMeleeAttack` n'est arme et l'egalite port==natif ne prouve plus rien."""
    porteurs = [u for u, e in (mesure["live_foot"][0] or {}).items()
                if R5.TERRIFYING_EXTRA_DEFENSE in e]
    _off, live = _degats(mesure)
    assert live, "regime DEGENERE : aucun degat natif"
    frappees_greffees = [u for u in live if u in porteurs and u != mesure["caster"]]
    assert frappees_greffees, (
        "aucune CIBLE frappee ne porte `Terrifying_ExtraDefense` (78) -- la greffe n'a pas pris, "
        "porteurs mesures = %s, cibles frappees = %s" % (porteurs, sorted(live)))


def test_la_cible_greffee_est_bit_exacte(mesure):
    """LE GARDE DE #503-r5. A `is_melee=None` il rougit de 2629 PV (mesure) ; a `is_melee=True` il
    est bit-exact. C'est ce qui interdit de revenir au `None` permissif."""
    porteurs = [u for u, e in (mesure["live_foot"][0] or {}).items()
                if R5.TERRIFYING_EXTRA_DEFENSE in e]
    off, live = _degats(mesure)
    greffees = [u for u in live if u in porteurs and u != mesure["caster"]]
    for u in greffees:
        assert off.get(u) == live[u], (
            "u%d porte le gate `IsMeleeAttack` et diverge : port %s vs natif %s -- la nature "
            "ecrite dans l'arbre n'est pas celle que le natif applique" % (u, off.get(u), live[u]))


def test_le_temoin_non_greffe_na_pas_bouge(mesure):
    """Le TEMOIN attribue le verdict ci-dessus au SEUL gate : la greffe change le seed BC, donc
    tout le reste doit rester ce qu'il etait."""
    porteurs = [u for u, e in (mesure["live_foot"][0] or {}).items()
                if R5.TERRIFYING_EXTRA_DEFENSE in e]
    off, live = _degats(mesure)
    temoins = [u for u in live if u not in porteurs]
    assert temoins, ("aucune cible TEMOIN : le montage ne peut pas attribuer son verdict au seul "
                     "gate, ce n'est pas un resultat")
    for u in temoins:
        assert off.get(u) == live[u], (
            "le TEMOIN u%d a bouge (port %s vs natif %s) : la greffe a deplace autre chose"
            % (u, off.get(u), live[u]))
