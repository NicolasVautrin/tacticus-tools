"""#1005-r2 -- `ChaliceOfBaal` (relique 1550) CONFRONTEE LIVE, les cinq etages.

Le port etait complet et garde OFFLINE depuis #1005 ; ce qui manquait, c'est que **les trois
observables n'avaient jamais ete releves live** -- aucun montage n'avait fait mourir une unite au
contact de `bloodSanguinary`. Ce fichier les garde, plus le RESET, contre le NATIF.

Le montage ET les criteres vivent dans `probe_1005r2_chalice_of_baal_live.py` (foyer unique : ce
fichier ne duplique ni l'un ni l'autre, meme discipline que `test_576_blood_chalice_live.py`).

Le montage EXIGE ses regimes ; s'il ne les obtient pas il ECHOUE, il ne skippe pas (#268) -- sauf
indisponibilite du host, qui n'est pas un verdict sur le port. ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[3]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import probe_1005r2_chalice_of_baal_live as P                              # noqa: E402

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        # SOCLE COMMUN a TOUT fichier de test : la cascade des `conftest.py` et sa fermeture.
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/tests/engine/runner/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        "scripts/python/catalog_inject.py",
        "scripts/python/gameconfig.py", "scripts/python/enum_maps.py",
        "scripts/python/host_inputs.py", "scripts/python/rl_collect_batch.py",
        "scripts/python/stream_events.py", "scripts/python/symbols_layout.py",
        "scripts/python/engine/runner/snapshot.py",
        # PROPRE A CE FICHIER -- le probe qui porte le montage ET les criteres, et ses helpers.
        "scripts/python/probe_1005r2_chalice_of_baal_live.py",
        "scripts/python/probe_112_darkangels.py",
        "scripts/python/probe_27_custom_utility_inventory.py",
        "scripts/python/rl_duel.py",
        # LE MOTEUR ENTIER, deliberement : la cascade traverse le declenchement de trigger, la
        # couche d'effets, le soin et la donnee persistante. Enumerer les seuls fichiers de #1005
        # serait DECLARER TROP ETROIT, et un declencheur trop etroit est un FAUX VERT.
        "scripts/python/*.py",
        "scripts/python/engine/*.py",
        "scripts/python/engine/**/*.py",
        "scripts/python/tests/**/*.py",
    ),
    "build": True,
    "toujours": False,
    "raison": ("le port de la relique 1550 (trigger `On(UnitDeath)`, arbre "
               "`Heal & AddEffect(1569) & SetPersistentData`, reset `On(TurnEnd)`), la magnitude "
               "`hp[TertiaryAbilityLevel]` lue au gameconfig, et le montage de relique "
               "(`--equip-relic` + `--place`) dont deux ecritures echouent en silence"),
}


@pytest.fixture(scope="module")
def mesure():
    m = P.mesurer(seed=31337, board="MC1_67")
    if not m.get("ok") and "build KO" in str(m.get("raison") or ""):
        pytest.skip("host indisponible -- ce n'est pas un verdict sur le port (runner non montable)")
    return m


def test_le_montage_a_produit_ses_regimes(mesure):
    """Le montage EXIGE ses regimes : sans porteur, allie et trois ennemis places, les cinq etages
    seraient vacants et passeraient pour verts."""
    assert mesure.get("ok"), mesure.get("raison")
    assert mesure["porteur"] and mesure["allie"], mesure
    assert len(mesure["ennemis"]) == 3 and all(mesure["ennemis"]), mesure
    assert mesure["hp_attendu"] > 0, "magnitude gameconfig NULLE -- montage degenere"


@pytest.mark.parametrize("indice", range(6))
def test_etage(mesure, indice):
    """Les six verdicts du probe, un par test -- pour que la ventilation soit LISIBLE au rapport
    plutot que masquee derriere un `assert not bad`."""
    v = P.verdicts(mesure)
    assert len(v) == 6, v            # NON-DEGENERESCENCE : la liste des criteres n'a pas fondu
    nom, ok, detail = v[indice]
    assert ok, "%s -- %r" % (nom, detail)
