"""#438-r1 -- CLIQUET LIVE du regime MULTI-EVENTS (AoE) de la feuille ATTACK.

CE QUE CETTE GARDE PROTEGE, et ce qu'AUCUNE autre ne pouvait voir. La feuille
`TriggeredAbilities(2)` de la face ATTACK est evaluee **PAR EVENT** du composite `Damage(35)`, et
chaque event porte SA propre `DamagePrediction` (le case natif est un
`UtilityAttackCase.ForDamagePrediction`). #438 a cable `ev.prediction` dans la boucle de
`engine/playbook/base.py::calculate_utility_from_predictions` -- correct par construction, mais
sur un montage a **UN SEUL** event : dans ce regime, << la prediction de l'event courant >> et
<< celle du premier event >> sont la MEME CHOSE, donc rien n'y est atteste.

Le montage (`probe_438r1_multi_events_aoe.py`) greffe `1204 BarbedOvipositor` sur `astraBullgryn`,
dont l'active `FragBomb (1017)` frappe une ZONE : trois events, chacun avec sa prediction. Les PV
sont calibres pour que les trois ne soient PAS dans le meme regime de kill -- sans quoi le montage
serait degenere et l'accord vide.

MESURE du 2026-08-18 (`t6dpr4k06g`, `MC1_67`/777) : regimes `(will=False, might=True)`,
`(False, False)`, `(False, False)` ; `pairUtility` natif **123.33483331371099** contre port
**123.334833**. CONTRE-EPREUVE `--mutant premiere-prediction` : port **173.334833**, soit
**+50.000000 EXACTEMENT** = deux `BARBEDOVIPOSITOR_PossibleKill` (25) surnumeraires.

ASCII only.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import probe_438r1_multi_events_aoe as P                   # noqa: E402

#: #486-r15 -- ce qui doit changer pour que ce fichier puisse changer de verdict.
DECLENCHEUR = {
    "chemins": (
        "scripts/python/probe_438r1_multi_events_aoe.py",
        "scripts/python/engine/playbook/base.py",
        "scripts/python/engine/playbook/barbed_ovipositor.py",
    ),
    "build": False,
    "toujours": True,
    "raison": ("`toujours` parce que le verdict est un ACCORD LIVE sur `pairUtility`, qui somme le "
               "composite `Damage(35)` ENTIER : n'importe quelle feuille de ce composite, ou "
               "n'importe quel etage de la prediction de degat, deplace le total. Un declencheur "
               "limite aux trois foyers du terme serait un faux vert."),
}


@pytest.fixture(scope="module")
def mesure():
    return P.mesurer(verbose=False)


def test_le_montage_s_installe(mesure):
    """Un montage qui ne s'installe pas n'est PAS un verdict."""
    assert not mesure.get("error"), mesure.get("error")


def test_la_greffe_a_pris(mesure):
    """GARDE DE SOURCE : `1204` doit etre dans le kit DECLENCHE LU LIVE du greffon. Sans elle, le
    playbook serait enregistre et jamais appele, et l'accord ne prouverait rien de lui."""
    assert P.ABILITY in (mesure.get("kit") or ()), (
        "greffe non prise : kit declenche LIVE = %r" % (mesure.get("kit"),))


def test_le_regime_est_bien_MULTI_EVENTS(mesure):
    """Le cast doit produire AU MOINS DEUX events. C'est la seule difference avec #438, et c'est
    tout l'objet du residu."""
    assert (mesure.get("n_events") or 0) >= 2, (
        "%d event(s) seulement -- regime DEGENERE, identique a celui de #438"
        % (mesure.get("n_events") or 0))


def test_les_events_ne_sont_PAS_dans_le_meme_regime(mesure):
    """CRAN ANTI-DEGENERE. Deux events du meme regime de kill donnent le MEME total, que le port
    passe la prediction de l'event courant ou celle du premier : un accord y serait parfaitement
    lisible et entierement vide. Mesure : sans calibrage des PV, les trois events tombaient tous
    dans `WillBeKill`."""
    regimes = {(r["will"], r["might"]) for r in (mesure.get("regimes") or ())}
    assert len(regimes) >= 2, (
        "les %d events sont tous dans le regime %r -- le calibrage des PV n'a pas mordu"
        % (mesure.get("n_events"), regimes))


def test_le_port_s_accorde_au_natif_sur_le_total(mesure):
    """L'ACCORD. `pairUtility` natif == utilite d'action du port, a EPS pres (Fix64 contre float)."""
    assert mesure.get("accord") is True, (
        "port %.6f contre natif %r" % (mesure.get("port"), mesure.get("natif")))
