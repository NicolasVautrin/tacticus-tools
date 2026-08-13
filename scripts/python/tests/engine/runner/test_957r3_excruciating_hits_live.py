"""#957-r3 -- GARDE de la confrontation LIVE du `hits` de `1197 ExcruciatingFrequencies`.

Le cliquet OFFLINE (`tests/engine/test_957r3_excruciating_hits_offline.py`) garde la FORME de
l'override (`hits_override = constants["nrOfHits"]`, et le regime qui la rend discriminante). Ce
fichier-ci garde l'ACCORD avec le NATIF, sur le porteur reel `emperNoiseMarine`, dans un regime ou
les deux candidats sont SEPARES.

CE QUI REND LE REGIME ATTEIGNABLE (et ce que le residu croyait impossible) : `ExtraHits` n'est PAS
un champ de l'entree BC -- `--unit-stat` ne peut donc pas le poser directement, contrairement a ce
que #957-r3 proposait. Mais `IdunBattle.Entities.Effects.Loki.Swarm_HitReductionEffect` (1021) pose
`EXTRA_HITS = -min(nrOfMembers - 1, membres morts)`, et ses TROIS entrees sont, elles, des champs BC :
`Traits` (le trait `Swarm`), `NumberOfMembers`, et `RemainingHealth` (qui fait les membres morts).

    NumberOfMembers = 5, Traits += Swarm, RemainingHealth = 800 (sur 8533)
        -> `statModSources` : extraHits = -4
        -> litteral   = nrOfHits                              = 1
        -> generique  = GetDefaultAttackHits(1, -4, 0, False) = max(1 - 4, 0) = 0

⚠ `--hp-player` NE MARCHE PAS : il aligne `Health` sur `RemainingHealth`, donc 0 membre mort, donc
`extraHits = 0` -- accord DEGENERE. C'est le champ PER-UNIT `RemainingHealth` qui creuse l'ecart.

⚠ `aiPlaybookPredict` et `statModSources` veulent le **`squadId`** d'`observeBattle`, pas son
`entityId` : passer l'`entityId` rend `unit <n> not found (unit/machine)`.

Montage et mesure : `probe_957r3_excruciating_hits.py` (ce fichier n'en est que le cran).
ASCII only.
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[3]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import probe_130_placement_sort_rng as P130  # noqa: E402
import probe_957r3_excruciating_hits as P  # noqa: E402

DECLENCHEUR = {
    "chemins": ("scripts/python/engine/playbook/prediction/abilities.py",
                "scripts/python/engine/playbook/excruciating_frequencies.py",
                "scripts/python/engine/entities/abilities/active_ability.py",
                "scripts/python/engine/services/damage_prediction.py",
                "scripts/python/probe_957r3_excruciating_hits.py",
                "scripts/python/tests/engine/runner/test_957r3_excruciating_hits_live.py"),
    "build": True,
    "toujours": False,
    "raison": "Il confronte au NATIF (`aiPlaybookPredict`) le nombre de coups predit par le "
              "playbook de 1197, dans le SEUL regime du build ou le litteral et le chemin "
              "generique sont separes (`Swarm` -> `ExtraHits` negatif).",
}


@pytest.fixture(scope="module", name="mesure_swarm")
def _mesure_swarm():
    """Le montage DISCRIMINANT, monte UNE fois pour le module. Rend le dict de `_confronte`."""
    rpc = P130.Rpc()
    sf = P.ROOT / "logs" / "runners" / ("t957r3-%s.json" % uuid.uuid4().hex[:8])
    sf.parent.mkdir(parents=True, exist_ok=True)
    extra = ["--place", "%s:6,6" % P.PORTEUR,
             "--unit-stat", "%s:NumberOfMembers=%d" % (P.PORTEUR, P.MEMBRES_SWARM),
             "--unit-stat", "%s:Traits=%s" % (P.PORTEUR, P.TRAITS_SWARM),
             "--unit-stat", "%s:RemainingHealth=%d" % (P.PORTEUR, P.PV_RESTANTS)]
    rid = P._build(sf, P.PORTEUR, extra)
    if rid is None:
        pytest.fail("montage impossible : `rl_duel build` a echoue (ce n'est PAS un verdict sur le "
                    "port -- reparer le montage)")
    try:
        ob = rpc("observeBattle", {"runnerId": rid}, 40)
        nr_hits, _cfg = P._nr_of_hits()
        res = P._confronte(rpc, rid, ob, P.PORTEUR, nr_hits)
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 30)
        Path(sf).unlink(missing_ok=True)
    assert res.get("ok"), "confrontation impossible : %s" % res.get("raison")
    return res


def test_le_regime_est_bien_ARME(mesure_swarm):
    """TEMOIN NON NUL, et il passe AVANT le verdict : sans `ExtraHits != 0` le litteral et le
    chemin generique coincident, et l'accord du test suivant ne prouverait RIEN."""
    from engine.services.damage_prediction import get_default_attack_hits
    extra = mesure_swarm["extraHits"]
    assert extra is not None, "`statModSources` muet -- NON MESURE (jamais rabattu sur 0)"
    assert extra != 0, (
        "`ExtraHits` = 0 : le montage `Swarm` n'a PAS arme le regime (piege connu : `--hp-player` "
        "aligne `Health` sur `RemainingHealth`, donc aucun membre mort)")
    litteral = mesure_swarm["nrOfHits"]
    generique = get_default_attack_hits(litteral, int(extra), 0, False)
    assert generique != litteral, (
        "regime DEGENERE : litteral=%d et generique=%d coincident malgre `ExtraHits`=%s"
        % (litteral, generique, extra))


def test_le_natif_predit_le_LITTERAL_pas_le_generique(mesure_swarm):
    """LA question binaire. `...ExcruciatingFrequenciesPlaybook$$MakeDamagePredictions` passe
    `IdunBattle.Entities.Abilities.AActiveAbility$$GetHits()` = `GetNumberConstant(0x2f)` BRUT au
    generateur multi-coups ; le chemin generique du port (`get_special_hits` ->
    `IdunBattle.Core.Services.DamagePrediction$$GetDefaultAttackHits`) y AJOUTE la stat
    `ExtraHits` du caster."""
    from engine.services.damage_prediction import get_default_attack_hits
    hits = sorted({e["appliedHits"] for e in mesure_swarm["events"]
                   if e["appliedHits"] is not None})
    assert hits, "`aiPlaybookPredict` n'a rendu AUCUN evenement -- rien a confronter"
    litteral = mesure_swarm["nrOfHits"]
    generique = get_default_attack_hits(litteral, int(mesure_swarm["extraHits"]), 0, False)
    assert hits == [litteral], (
        "appliedHits NATIFS = %s ; litteral (`nrOfHits`) = %d ; generique "
        "(`GetDefaultAttackHits`) = %d -- le natif ne predit PAS le litteral"
        % (hits, litteral, generique))


def test_le_port_predit_LA_MEME_chose_que_le_natif(mesure_swarm):
    """L'accord proprement dit : le `hits_override` du port vaut ce que le natif a applique."""
    import gameconfig as GC
    from engine.entities.abilities.ability_configuration import AbilityConfiguration
    from engine.playbook.prediction.abilities import _excruciating_frequencies_inputs

    cfg = AbilityConfiguration.from_gameconfig("ExcruciatingFrequencies",
                                               GC.ability("ExcruciatingFrequencies"))
    port = _excruciating_frequencies_inputs(None, None, None, None, cfg).get("hits_override")
    hits = sorted({e["appliedHits"] for e in mesure_swarm["events"]
                   if e["appliedHits"] is not None})
    assert hits == [port], (
        "le port surcharge %s coups la ou le natif en applique %s" % (port, hits))
