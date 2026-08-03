"""#462-r4b-r1-r1 -- les DEUX producteurs d'additif DEFENSEUR que #462-r4b-r1 avait laisses SANS
AUCUNE MESURE, confrontes en COMBAT.

#462-r4b-r1 (PR #548) a deplace l'additif DEFENSEUR dans le slot PRE-PERCAGE de l'attaquant
(`IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw` somme `base + Addition(0xd) +
Addition(0xe)` avant `CalculateBaseDamageWithAllModifiers`, qui ne re-consomme pas `+0x10`). TROIS
producteurs alimentent ce champ ; un SEUL avait ete confronte. Le comportement des deux autres avait
donc change sans qu'aucune mesure ne le voie -- le profil exact d'une regression silencieuse.

DEUX BRAS DISCRIMINANTS, ET CHACUN PAR UN ETAGE DIFFERENT :

  * `chrono`  -- `Chronometron_ExtraDamage` (1550), pose par l'active 1226 de `necroChronomancer`
                 (HORS POOL -> injection catalogue). Profil `Physical` (`PiercingRatio = 1`) et
                 armure forcee a 50000 : c'est la branche PERCAGE du plancher qui separe, SANS
                 aucune `%-list` -- un etage que le bras de #462-r4b-r1 (qui reposait sur la
                 `%-list` `TerminatorArmour` x0.25) ne pouvait pas exercer.
  * `neuro`   -- `Neuroparasite` (1218), passif de `tyranNeurothrope` (AU POOL). Profil `Psychic`
                 (`PiercingRatio = 100`) : l'axe PERCAGE y est STRUCTURELLEMENT degenere, et c'est
                 la `%-list` ATTAQUANT (`RangedSpecialist` x1.33) que l'additif pre-percage traverse
                 qui separe. Ce bras a trouve un SECOND defaut : l'effet etait MATERIALISE et
                 pourtant INERTE en combat, faute des cles `ability_level`/`multiplier` dans
                 l'`attacker_ctx` -- le meme fork prediction/combat que #462-r4b-r1 a ferme sur
                 l'axe PLACEMENT, reste ouvert sur l'axe MAGNITUDE.

UN BRAS TEMOIN, ASSERTIONNE COMME NON PROBANT :

  * `chrono-flat` -- meme montage, armure 0. Le plancher `max(d x pierce%, d - armure)` est alors
                 AFFINE DE PENTE 1, donc `P(v + A) = P(v) + A` : les deux placements COINCIDENT.
                 `port == contre-modele == natif` y est une BORNE, jamais une confirmation -- et le
                 test l'assertionne pour qu'aucune lecture future ne s'y trompe.

Montage : `probe_462_r4b_r1_r1_defender_additive_carriers.py` (ce fichier n'en est que la porte
pytest). ASCII only. Dispose SES runners.
"""
from __future__ import annotations

import json

import pytest

import probe_462_r4b_r1_r1_defender_additive_carriers as PB

CHRONO_EXTRA_DAMAGE = 1550         # `Chronometron_ExtraDamage`
NEUROPARASITE = 1218               # `Neuroparasite` (l'EFFET ; 1183 est le TriggeredAbilityType)
CHRONO_ADD = 898                   # `extraDmg[50] x mult 180`
NEURO_ADD = 1696                   # `extraDmg[50] x mult 180` x niveau 1


@pytest.fixture(scope="module")
def chrono_case(live_session):
    m = PB.measure_chronometron(live_session, PB.ARMOR_PIERCE)
    if m.get("skip"):
        pytest.skip(m["skip"])
    return m


@pytest.fixture(scope="module")
def chrono_flat_case(live_session):
    m = PB.measure_chronometron(live_session, PB.ARMOR_FLAT)
    if m.get("skip"):
        pytest.skip(m["skip"])
    return m


@pytest.fixture(scope="module")
def neuro_case(live_session):
    m = PB.measure_neuroparasite(live_session)
    if m.get("skip"):
        pytest.skip(m["skip"])
    return m


def _additive(m):
    """L'additif DEFENSEUR effectivement fusionne, LU du foyer instrumente (`defender_modifiers`)
    -- jamais recalcule ici : c'est la mesure, pas une reconstruction."""
    for c in m.get("def_mods_calls") or []:
        v = json.loads(c["mods"]).get("additive")
        if v:
            return int(v)
    return 0


# -------------------------------------------------- (1) `Chronometron_ExtraDamage` -- branche PERCAGE

def test_chronometron_additif_defenseur_bit_exact(chrono_case):
    """Le ledger PAR COUP, a l'unite (l'etat port est cale sur le RNG du runner : meme flux des deux
    cotes). C'est le premier datapoint COMBAT de ce producteur, tous cas confondus."""
    m = chrono_case
    assert CHRONO_EXTRA_DAMAGE in m["pre_active"], (
        "l'effet 1550 n'est pas ACTIF au chargement -> le bras ne mesure rien (%s)"
        % (m["pre_active"],))
    assert _additive(m) == CHRONO_ADD, (
        "additif defenseur attendu %s, mesure %s" % (CHRONO_ADD, _additive(m)))
    assert m["port_per_hit"] == m["live_per_hit"], (
        "ledger PAR COUP divergent\n  port=%s\n  live=%s" % (m["port_per_hit"], m["live_per_hit"]))
    assert m["port_total"] == m["live_delta"], (
        "degat total port=%s live=%s" % (m["port_total"], m["live_delta"]))
    assert m["live_delta"] > 0, "aucun degat -> l'attaque n'a pas porte"


def test_chronometron_le_contre_modele_POST_pct_list_MORD(chrono_case):
    """Le rejeu du MEME etat avec le corps d'AVANT #462-r4b-r1 doit DIVERGER largement. Sans ce
    test, `port == live` pourrait tenir d'un port qui n'exerce plus l'axe du tout.

    Ce bras separe par la branche PERCAGE SEULE (`Physical`, `PiercingRatio = 1`, armure 50000) :
    l'ecart theorique est `A x (1 - pierce/100)`, soit ~890 sur 898 -- d'ou un contre-modele plus
    de DIX fois le natif, la ou le bras de #462-r4b-r1 separait par une `%-list`."""
    m = chrono_case
    assert m["variant_per_hit"], "contre-modele non joue"
    assert m["variant_per_hit"] != m["live_per_hit"], (
        "le contre-modele rend le MEME ledger -> regime NON discriminant (%s)"
        % (m["variant_per_hit"],))
    assert sum(m["variant_per_hit"]) > 5 * sum(m["live_per_hit"]), (
        "sur la branche PERCAGE le contre-modele devait sur-infliger massivement : variant=%s "
        "live=%s" % (sum(m["variant_per_hit"]), sum(m["live_per_hit"])))


def test_chronometron_regime_ARMURE_est_une_BORNE_pas_une_confirmation(chrono_flat_case):
    """BRAS TEMOIN, NON PROBANT PAR CONSTRUCTION -- et c'est la mesure qui le dit. Armure 0 => la
    branche ARMURE du plancher gagne, il est affine de pente 1, donc `P(v + A) = P(v) + A` et les
    deux placements rendent le MEME nombre. L'assertion est une garde de LECTURE : si ce bras
    devenait discriminant, on le prendrait a tort pour une confirmation du correctif."""
    m = chrono_flat_case
    assert _additive(m) == CHRONO_ADD, "l'additif n'est pas en jeu -> le temoin ne temoigne de rien"
    assert m["port_per_hit"] == m["live_per_hit"], (
        "port=%s live=%s" % (m["port_per_hit"], m["live_per_hit"]))
    assert m["variant_per_hit"] == m["port_per_hit"], (
        "ce bras est devenu DISCRIMINANT (variant=%s port=%s) -- la borne algebrique `branche "
        "ARMURE` est a revoir, et ce bras ne doit plus se lire comme un simple accord"
        % (m["variant_per_hit"], m["port_per_hit"]))


# ------------------------------------------- (2) `Neuroparasite` -- %-list ATTAQUANT, et l'INERTIE

def test_neuroparasite_additif_defenseur_bit_exact(neuro_case):
    """Le parasite est POSE par le natif a la cloture (`On(9)`) d'une attaque PSYCHIQUE et son
    additif ne joue qu'a la frappe SUIVANTE -- d'ou un montage MULTI-TOURS.

    AVANT #462-r4b-r1-r1 ce bras rendait port 2192 contre natif 4448 : l'effet etait bien dans
    l'etat charge, mais `create_effect_damage_malus_for_defense` rendait `None` faute de
    `ability_level` dans l'`attacker_ctx` du COMBAT. L'ecart valait 2256 = 1696 x 1.33, exactement
    le separateur #88 mesure cote PREDICTION le 2026-07-12."""
    m = neuro_case
    assert NEUROPARASITE in m["pre_active"], (
        "le parasite 1218 n'est pas ACTIF au chargement -> le bras ne mesure rien (%s)"
        % (m["pre_active"],))
    assert _additive(m) == NEURO_ADD, (
        "additif defenseur attendu %s, mesure %s -- 0 signifie que l'effet est MATERIALISE mais "
        "INERTE (cles `ability_level`/`multiplier` absentes de l'attacker_ctx COMBAT)"
        % (NEURO_ADD, _additive(m)))
    assert m["port_per_hit"] == m["live_per_hit"], (
        "ledger PAR COUP divergent\n  port=%s\n  live=%s" % (m["port_per_hit"], m["live_per_hit"]))
    assert m["port_total"] == m["live_delta"], (
        "degat total port=%s live=%s" % (m["port_total"], m["live_delta"]))


def test_neuroparasite_le_contre_modele_POST_pct_list_MORD(neuro_case):
    """Sur ce profil `Psychic` (`PiercingRatio = 100`) le plancher est l'IDENTITE : ce qui separe
    les deux placements est la `%-list` ATTAQUANT que l'additif PRE-percage traverse. Le contre-
    modele ajoute l'additif APRES -- il rend donc `d x M + A` au lieu de `(d + A) x M`, soit un
    manque de `A x (M - 1)`."""
    m = neuro_case
    assert m["variant_per_hit"], "contre-modele non joue"
    assert m["variant_per_hit"] != m["live_per_hit"], (
        "le contre-modele rend le MEME ledger -> regime NON discriminant (%s)"
        % (m["variant_per_hit"],))
    assert sum(m["variant_per_hit"]) < sum(m["live_per_hit"]), (
        "le placement POST doit SOUS-infliger ici (l'additif n'est plus scale par la %%-list "
        "attaquant) : variant=%s live=%s"
        % (sum(m["variant_per_hit"]), sum(m["live_per_hit"])))


def test_neuroparasite_le_profil_est_bien_PSYCHIQUE(neuro_case):
    """Non-degenerescence du montage : le Neurothrope porte DEUX armes (melee `Physical`, ranged
    `Psychic` portee 3) et l'attaque normale choisit selon la distance. Au CONTACT il frappe en
    `Physical`, le gate `CurrentAttackDamageProfilesContain(0xd)` ne s'ouvre pas et AUCUN parasite
    n'est pose -- mesure de la premiere passe du probe. Ce test fige la condition du montage."""
    m = neuro_case
    assert m["port_profile"] == "Psychic", (
        "profil %s -- le montage a bascule sur l'arme melee, le parasite ne peut pas jouer"
        % (m["port_profile"],))
    assert any(c["profile"] == "Psychic" and c["is_melee"] is False
               for c in (m["def_mods_calls"] or [])), (
        "le foyer defenseur n'a pas vu un coup RANGED Psychic (%s)"
        % ([(c["profile"], c["is_melee"]) for c in (m["def_mods_calls"] or [])],))
