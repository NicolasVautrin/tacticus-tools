"""#419-r1-tr14-r5-r2-r1-r2-r1 -- la REGLE DYNAMIQUE de l'attaque normale, CONFRONTEE.

Ce que ces crans gardent, et pourquoi chacun est necessaire :

  1. **LA CHAINE, RELUE HORS LIGNE.** Les trois etages du port
     (`weapon_is_melee` -> `find_*_weapon` -> `get_attack_weapon_for_default_normal_attack_from_tiles`)
     rendent bien `null` sur le SEUL regime de refus natif : l'ensemble d'armes filtre est VIDE.
  2. **LE MONTAGE A MORDU.** Les deux summons portent l'attaque normale generique `69` (masque
     `0x4002`, bit `TargetMatchesDynamicRule` ARME) et l'un d'eux a un ennemi ADJACENT. Un montage
     qui n'a pas mordu est un ECHEC, jamais un skip vert.
  3. **LE PORT CONTRE LE NATIF, SUR LE VERDICT.** Accord TOTAL sur « refuse / accepte » -- l'axe qui
     gouverne `is_invalid_target` et `valid_normal_attack_targets`.
  4. **LA CONTRE-EPREUVE MORD.** La baseline (le corps d'avant, `return 0`) doit DIVERGER du natif
     sur au moins un verdict. Sans ce cran, un vert de (3) ne prouverait rien : le port et le natif
     s'accordent PAR CONSTRUCTION partout ou le caster possede l'arme demandee.
  5. **AUCUNE CIBLE LEGITIME PERDUE.** Le sens inverse, et c'est le vrai risque de cette tranche :
     un ecart permissif ferme au prix d'un ecart RESTRICTIF est un echec. Le temoin est un summon
     ARME de la MEME equipe, avec la MEME attaque normale et la MEME geometrie -- seules ses armes
     different.
  6. **LE REFUS EST NOMME.** Sur la ligne discriminante (cible ADJACENTE, caster SANS ARME), le
     natif rompt bien `TargetMatchesDynamicRule` et la baseline l'ACCEPTAIT (`0x0`) : c'est la
     signature exacte de l'ecart PERMISSIF que la tranche ferme.

⚠ Le montage est OBLIGATOIRE et c'est une MESURE : `genesSmnDecoy` a `weapons = []` AU KIT **et**
`Weapons = []` dans `BC.Units`. Les deux substrats CONCORDENT -- indispensable, puisque le port lit
le kit gameconfig la ou le natif lit le `WeaponsComponent`.

RE et mesures : `docs/rl/case-419-r1-tr14-r5-r2-r1-r2-r1-regle-dynamique-attaque-normale.md`.
ASCII only. Probe jumeau : `scripts/python/probe_419r1tr14r5r2r1r2r1_normal_attack_dynamic_rule.py`.
"""
from __future__ import annotations

import pytest

import probe_419r1tr14r5r2r1r2r1_normal_attack_dynamic_rule as P
from engine.runner.abilities.targeting_rule import TargetingRule as TR
from engine.services.battle_query import (
    find_melee_weapon, find_ranged_weapon, weapon_is_melee,
    get_attack_weapon_for_default_normal_attack_from_tiles as GET_WEAPON)

DYNAMIC = int(TR.TargetMatchesDynamicRule)


@pytest.fixture(scope="module")
def mesure(rpc):
    """Le montage complet, natif ET port. Un montage qui n'a pas mordu est un ECHEC
    (`MontageError`), jamais un skip vert."""
    from rl_collect_batch import _resolve_session
    try:
        return P.run(_resolve_session())
    except P.MontageError as e:
        pytest.fail(str(e), pytrace=False)


# ------------------------------------------------------------------------------- crans OFFLINE

def test_get_is_melee_est_le_seuil_lu_pas_labsence_de_portee():
    """(1) `IdunShared.Battle.WeaponProfile$$get_IsMelee` = `!Range.HasValue || Range.Value < 2`.
    Le seuil `< 2` est LU, pas deduit : une arme a `Range == 1` est encore de la MELEE."""
    assert weapon_is_melee({"hits": 1}) is True                 # `!Range.HasValue`
    assert weapon_is_melee({"hits": 1, "Range": 1}) is True      # `Range.Value < 2`
    assert weapon_is_melee({"hits": 1, "Range": 2}) is False


def test_la_selection_rend_null_sur_un_ensemble_vide():
    """(1) `SelectMaxRangeWeapon` rend `null` sur un ensemble VIDE -- l'UNIQUE porte de sortie
    `null`, donc le seul regime de refus de la regle dynamique. `genesSmnDecoy` (`weapons = []`)
    n'a NI melee NI distance ; `genesSmnNeophyte` a les deux."""
    assert find_melee_weapon("genesSmnDecoy") is None
    assert find_ranged_weapon("genesSmnDecoy") is None
    assert find_melee_weapon("genesSmnNeophyte") is not None
    assert find_ranged_weapon("genesSmnNeophyte") is not None


def test_la_surcharge_slot_0xb0_aiguille_sur_ladjacence():
    """(1) `GetAttackWeaponForDefaultNormalAttack(attacker, attackerTiles, targetTiles)` :
    `AreTilesAdjacent` -> `FindMeleeWeapon`, sinon `FindRangedWeapon`. Sur un caster SANS ARME les
    deux branches rendent `null` -- c'est ce qui fait REFUSER toute cible."""
    for adjacent in (True, False):
        assert GET_WEAPON("genesSmnDecoy", adjacent) is None
        assert GET_WEAPON("genesSmnNeophyte", adjacent) is not None
    # Un caster MELEE-ONLY : arme en contact, rien a distance (le refus y est deja rendu EN AMONT
    # par le volet portee, cf. la ventilation en tete du probe -- ce cran fixe l'aiguillage).
    assert GET_WEAPON("necroSpyder", True) is not None
    assert GET_WEAPON("necroSpyder", False) is None


# --------------------------------------------------------------------------------- crans LIVE

def test_le_montage_a_mordu(mesure):
    """(2) Les deux casters existent, portent `69`, et le discriminant a bien une cible ADJACENTE."""
    assert mesure["decoy"], "aucune ligne pour le caster SANS ARME"
    assert mesure["anchor"], "aucune ligne pour le caster ARME (temoin)"
    assert any(r["d"] == 1 for r in mesure["decoy"]), (
        "aucune cible ADJACENTE au caster sans arme : le discriminant n'est pas monte")
    assert any(r["d"] == 1 for r in mesure["anchor"]), (
        "aucune cible ADJACENTE au temoin : les deux bras ne sont pas comparables")


def test_le_port_est_daccord_avec_le_natif_sur_le_verdict(mesure):
    """(3) Accord TOTAL sur « refuse / accepte » -- l'axe que consomment `is_invalid_target` et
    `valid_normal_attack_targets`."""
    t = P.tally(mesure)
    assert t["v_after"] == t["tot"], (
        f"{t['tot'] - t['v_after']} ligne(s) ou le port et le natif divergent SUR LE VERDICT")


def test_la_baseline_diverge_du_natif(mesure):
    """(4) LA CONTRE-EPREUVE. Sans elle, le vert precedent serait un accord DEGENERE : partout ou le
    caster possede l'arme demandee, la regle ne refuse rien et les deux modeles coincident."""
    t = P.tally(mesure)
    assert t["v_gain"] >= 1, (
        "REGIME DEGENERE : la baseline (regle non portee) est d'accord partout -- cette geometrie "
        "ne separe pas les deux modeles (il faut un caster SANS ARME et une cible ADJACENTE)")


def test_aucune_cible_legitime_perdue(mesure):
    """(5) Le sens INVERSE : aucune cible que le natif ACCEPTE et que le port refuse. Un ecart
    permissif ferme au prix d'un ecart restrictif serait un echec."""
    t = P.tally(mesure)
    assert t["v_perte"] == 0, (
        f"{t['v_perte']} cible(s) que le natif accepte et que le port REFUSE : refus trop large")


def test_le_temoin_arme_est_inchange(mesure):
    """(5) RECIPROQUE, sur le bras temoin : un summon ARME de la meme equipe, meme attaque normale,
    meme geometrie. Le port APRES doit y rendre EXACTEMENT ce que rendait la baseline."""
    for r in mesure["anchor"]:
        assert r["after"] == r["before"], (
            f"temoin, cible u{r['tid']} d={r['d']} : le port APRES ({hex(r['after'])}) doit "
            f"coincider avec la baseline ({hex(r['before'])}) -- un caster ARME ne peut pas etre "
            "refuse par la regle dynamique")


def test_le_refus_est_nomme_sur_la_ligne_adjacente(mesure):
    """(6) Sur la ligne DISCRIMINANTE (cible adjacente, caster sans arme), on NOMME les trois
    valeurs : le natif rompt `TargetMatchesDynamicRule`, la baseline ACCEPTAIT, le port refuse."""
    adj = [r for r in mesure["decoy"] if r["d"] == 1 and r["nat"] is not None]
    assert adj, "aucune ligne adjacente mesurable pour le caster sans arme"
    for r in adj:
        assert r["nat"] == DYNAMIC, (
            f"cible u{r['tid']} d=1 : le natif doit rompre TargetMatchesDynamicRule, "
            f"trouve {hex(r['nat'])}")
        assert r["before"] == 0, (
            f"cible u{r['tid']} d=1 : la baseline l'ACCEPTAIT (degradation permissive), "
            f"trouve {hex(r['before'])}")
        assert r["after"] == r["nat"]
