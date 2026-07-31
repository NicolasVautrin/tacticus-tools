"""#353 -- la prediction de `RammingSpeed` (1059) confrontee au LIVE, par GREFFE.

Aucune unite du gameconfig ne porte 1059 (garde offline `test_353_..._offline.py` sec.E). Le montage
passe donc par la GREFFE de `docs/rl/case-92-catalog-injection.md` sec.5bis : `ActiveAbilities = [1059]`
sur l'entree `BC.Units` d'un heros DU POOL, dans une COPIE du seed BC, plus la config d'ability
manquante dans `BC.Abilities`. `aiPlaybookPredict` charge le playbook PAR ABILITY
(`PlaybookDatabase.LoadPlaybook(1059)`) : le code exerce est bien `RammingSpeedPlaybook`, et le RPC
le CONFIRME (`playbookClass`).

Ce que la garde verrouille, sur QUATRE bras (2 boards, 4 niveaux, 2 regimes d'armure) :
  1. le playbook natif charge est bien `RammingSpeedPlaybook` ;
  2. le port LIVRE egale le natif event pour event -- y compris le 2e event, sur le CASTER, que le
     port n'emettait PAS avant #353 ;
  3. chaque bras DISCRIMINE : le port d'AVANT (registres 1059 retires) diverge. Un bras ou les deux
     coincident ne prouverait rien et fait ECHOUER le verdict au lieu de le verdir.

ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[2]                 # scripts/python
sys.path.insert(0, str(PYDIR))

import probe_353_ramming_speed_prediction as P              # noqa: E402

# Quatre bras. `armor_target = 0` laisse l'ecart de base traverser jusqu'aux bornes ; le bras
# `armure 2312` verifie que le correctif tient AUSSI quand l'armure ecrase le degat au plancher
# (regime ou un ecart de base peut etre absorbe -- piege #339 sec.4).
MONTAGES = {
    "lvl8_mc167": dict(seed=35371, level=8, board="MC1_67", armor_target=0),
    "lvl2_mc167": dict(seed=35381, level=2, board="MC1_67", armor_target=0),
    "lvl30_c103": dict(seed=35401, level=30, board="C1_03", armor_target=0),
    "lvl45_armure": dict(seed=35411, level=45, board="MC1_67", armor_target=2312),
}


@pytest.fixture(scope="module")
def measured():
    out = {}
    for key, m in MONTAGES.items():
        sf = PYDIR.parents[1] / "logs" / ("t353_%s.json" % key)
        r = P.run(state_file=str(sf), verbose=False, **m)
        assert not r.get("error"), "%s KO : %s" % (key, r["error"])
        out[key] = r
    return out


def test_the_graft_loads_the_ramming_speed_playbook(measured):
    """Pre-condition : sans elle, un accord ne dirait rien du playbook vise."""
    for key, r in measured.items():
        assert r["graft"]["grafted_entries"] == 1, "%s : greffe non appliquee" % key
        assert r["graft"]["ability_config_injected"], (
            "%s : config d'ability non injectee -- le cast/la prediction leveraient" % key)
        assert r.get("native_playbook") == "RammingSpeedPlaybook", (
            "%s : playbook natif = %r, pas RammingSpeedPlaybook" % (key, r.get("native_playbook")))
        assert (r.get("native_ability_state") or {}).get("source") == "capteur", (
            "%s : l'AbilityState vient du defaut (0,100), pas du capteur -- le niveau pilote par "
            "`--unit-stat` n'a pas pris" % key)
        assert r["level_eff"] == r["level_asked"], "%s : niveau effectif != demande" % key


def test_the_port_equals_the_native_event_for_event(measured):
    for key, r in measured.items():
        assert r["port_sig"] == r["native_sig"], (
            "%s : port %s != natif %s" % (key, r["port_sig"], r["native_sig"]))


def test_the_native_emits_the_self_event_and_the_port_did_not_before(measured):
    """Le 2e batch (`<Caster>`, `nrOfHits_2` coups) est la moitie du correctif : le natif l'emet
    dans les quatre bras, et le port d'AVANT n'emettait qu'UN event."""
    for key, r in measured.items():
        cid = r["caster_id"]
        nat_self = [e for e in r["native_sig"] if e[0] == cid]
        assert len(nat_self) == 1, "%s : le natif n'emet pas l'event SELF (%s)" % (key, r["native_sig"])
        assert nat_self[0][3] == r["nrOfHits_2"], (
            "%s : coups de l'event SELF = %d, attendu nrOfHits_2 = %d"
            % (key, nat_self[0][3], r["nrOfHits_2"]))
        assert len(r["port_before_sig"]) == 1, (
            "%s : le port d'AVANT emettait deja plusieurs events -- le bras ne mesure plus le "
            "cablage du 2e batch" % key)


def test_every_arm_discriminates(measured):
    """Le port d'AVANT (base = avg, coups = formule generique, pas de 2e batch) doit DIVERGER."""
    for key, r in measured.items():
        assert not r["before_match"], (
            "%s : le port d'AVANT egalait deja le natif -- bras NON discriminant" % key)
        assert r["minDmg"] != r["avg_generique"], (
            "%s : minDmg == avg a ce niveau, l'axe BASE est muet" % key)
        assert r["ok"], "%s : verdict du probe = ECHEC" % key
