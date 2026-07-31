"""#352 -- les bases de prediction de `1098 PlasmaGrenade` et `1048 FragstormGrenadeLauncher`,
confrontees au LIVE, avec `1051 Stikkbomb` en TEMOIN.

Les deux abilities figuraient dans `_PREDICTION_DAMAGE_NOT_MINMAX_AVERAGE` avec « corrige = non » :
le port leur rendait la moyenne min/max generique, faux sur un axe PLUS PROFOND que l'arrondi.
Ce que le decompile dit, et que cette garde verrouille (detail : `docs/rl/case-352-*.md`) :

  1098 -- base = `DSLFormulas$$Get(GetVariableForLevel(0xc = minDmg))` SEUL et hits =
          `GetNumberConstant(0x2f = nrOfHits)` LITTERAL (le generique passe par
          `GetDefaultAttackHits`, qui AJOUTE la stat `ExtraHits` du caster).
  1048 -- le playbook n'appelle AUCUN `GenerateMultiHitAttackPredictions` : il appelle la surcharge
          « amount » de `IBattleQuery.GetAttackPrediction`, laquelle pose **`hits: 1` en dur** ->
          UN coup de `nrOfHits x maxDmg`, pas `nrOfHits` coups d'une moyenne.

TROIS choses sont gardees, et la troisieme est celle qu'on oublierait :

  1. le code LIVRE egale le natif (`aiPlaybookPredict`) sur chaque montage ;
  2. le contrefactuel « avant #352 » (l'entree de `_MAKE_DMG_INPUT_OVERRIDES` RETIREE) en DIFFERE --
     un montage ou les deux coincident ne prouve rien et fait ECHOUER, pas verdir ;
  3. le COMPTE d'events natif. Les volets secondaires de 1098 et 1048 sont STRUCTURELLEMENT MORTS
     (leur selecteur depend du caster, or le playbook l'evalue sur un `AbilityEntities` au caster
     nul), alors que celui de 1051 est VIVANT (`AdjacentUnits(Target)` ne depend que de la cible).
     Sur la MEME geometrie le natif rend donc 1 / 1 / 3. Sans le temoin 1051, « 1 event » se lirait
     comme un montage rate -- et quelqu'un « reparerait » un volet qui doit rester absent.

ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[2]                 # scripts/python
sys.path.insert(0, str(PYDIR))

import probe_352_grenade_prediction_base as P               # noqa: E402
from engine.entities.abilities.active_ability import (      # noqa: E402
    _PREDICTION_DAMAGE_NOT_MINMAX_AVERAGE)


@pytest.fixture(scope="module")
def measured():
    out = P.run(verbose=False)
    for row in out["rows"]:
        assert not row.get("error"), "%s KO : %s" % (row.get("name"), row["error"])
    assert out["rows"], "aucun montage joue"
    return out["rows"]


def test_both_abilities_are_declared_fixed_in_the_table():
    """Pre-condition : la table de #350 doit ANNONCER les deux comme corrigees, et le registre doit
    porter leur handler. C'est la garde offline #350 qui verifie l'equivalence des deux ; ici on
    verifie seulement que ce test parle bien des deux entrees qu'il pretend confronter."""
    import engine.playbook.prediction.abilities as PA
    for aid in (1098, 1048):
        assert aid in _PREDICTION_DAMAGE_NOT_MINMAX_AVERAGE
        assert _PREDICTION_DAMAGE_NOT_MINMAX_AVERAGE[aid][2] is True
        assert aid in PA._MAKE_DMG_INPUT_OVERRIDES


def test_geometry_is_actually_armed(measured):
    """Le compte d'events ne dit rien si la geometrie n'est pas montee : on exige la cible collee au
    caster ET deux ennemis a la fois adjacents a la cible et a portee 2 du caster."""
    for row in measured:
        assert row["geometry_ok"], (
            "%d %s : geometrie non armee (dist=%s, adj_cible=%s, a_portee_caster=%s)"
            % (row["ability"], row["name"], row["dist"], row["adj_foes_of_target"],
               row["foes_within2_of_caster"]))


def test_shipped_code_matches_native(measured):
    """Le code LIVRE (aucun patch) egale l'oracle `aiPlaybookPredict` sur chaque montage."""
    for row in measured:
        assert row["after_ok"], (
            "%d %s : le port LIVRE rend %s la ou le natif rend %s (minDmg=%s maxDmg=%s nrOfHits=%s)"
            % (row["ability"], row["name"], row["after"], row["native"],
               row["config"][0], row["config"][1], row["config"][2]))


def test_the_generic_path_is_refused_by_the_native(measured):
    """Le coeur de #352 : sans l'entree du registre, le port retombe sur la moyenne generique -- et
    le natif la REFUSE. Retirer l'un des deux handlers re-creerait exactement cet ecart."""
    for row in measured:
        assert row["discriminates"], (
            "%d %s : le chemin generique rend %s, identique au port livre -- ce montage ne demontre "
            "plus que le handler est load-bearing" % (row["ability"], row["name"], row["before"]))


def test_native_event_counts_separate_dead_from_live_secondary_volets(measured):
    """1051 emet son volet secondaire (3 events), 1098 et 1048 n'en emettent AUCUN (1 event), sur la
    MEME geometrie. C'est cette ligne qui interdit de « reparer » les deux volets morts."""
    by_id = {}
    for row in measured:
        by_id.setdefault(row["ability"], []).append(row)
    for row in measured:
        assert row["events_ok"], (
            "%d %s : le natif rend %d events, attendus %d -- soit le volet secondaire a change de "
            "statut, soit la geometrie n'exerce plus le meme set"
            % (row["ability"], row["name"], row["n_events"]["native"], row["expected_events"]))
    assert 1051 in by_id, "temoin 1051 absent : sans lui, '1 event' ne se distingue pas d'un montage rate"
    assert all(r["n_events"]["native"] >= 3 for r in by_id[1051])
    for aid in (1098, 1048):
        assert all(r["n_events"]["native"] == 1 for r in by_id[aid])
