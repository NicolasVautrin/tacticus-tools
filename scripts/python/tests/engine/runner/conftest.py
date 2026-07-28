"""Fixtures locales a la tranche RUNNER.

`psychic_aoe_case` — MONTAGE NOMME ET REUTILISABLE des deux AoE Psychic (PlagueWind 1035 /
Doombolt 1102). Le montage lui-meme (build isole, drive des positions des DEUX camps, capture
`decisionView`/`observeBattle`/`combatSnapshot`/`boardGraph`/`dumpRng`, replay OFFLINE sur le MEME
etat et le MEME `state.rng`, cast LIVE, comparaison per-coup, contre-epreuve de discriminance) vit
dans `scripts/python/probe_psychic_aoe.py` — la fixture n'est que sa PORTE pytest : un seul point
qui traduit « harnais indisponible » en skip (converti en ECHEC par le conftest racine) et qui garde
les tests lisibles.

Consommateurs : `test_plague_wind_live.py`, `test_doombolt_live.py`. Ajouter un cas = ajouter une
entree dans `probe_psychic_aoe.CASES`, pas dupliquer un montage inline dans un test.

`overkill_gate_case` (#178, etendue #R33) — meme forme : la PORTE pytest du montage A de
`scripts/python/probe_178_overkill_gate.py`, qui mesure les ARGUMENTS de la surcharge d'instance de
`IdunBattle.Core.Services.DamagePrediction$$IsOverkill`. Deux PAIRES : (`control` / `titus`) pour
les gates d'unite (`CanBeOverkilled`, `PreventOverkill`) et (`crit` / `nocrit`) pour `isCritical`.
Dans chaque paire on tue avec la MEME attaque, le MEME degat et les MEMES PV -- une seule variable
change. `overkill_revive_case` (#R33) = le montage B, a observable INDEPENDANT (porte revive
`Narthecium` « unless Overkilled ») et tueur SANS `ThrillSeekers`, qui ATTRIBUE l'observation a
`isCritical` puis isole `isForceOverkill` (regime `revive-flail`). Consommateur des deux :
`test_overkill_gate_live.py`."""
from __future__ import annotations

import pytest

import probe_psychic_aoe as P
import probe_178_overkill_gate as OVK


@pytest.fixture
def psychic_aoe_case(live_session):
    """Fabrique : `psychic_aoe_case("pw-chain")` -> le dict de resultats du probe.

    `live_session` est tire ICI (le montage exige la session Frida) ; le runner est DISPOSE par le
    probe lui-meme en sortie de `run()`, donc rien a liberer au teardown. `seed`/`board` sont
    surchargeables pour rejouer un cas sur un second couple (discipline de generalisation)."""
    def _build(case: str, seed: str = "31337", board_id: str = "MC1_67") -> dict:
        assert case in P.CASES, f"cas inconnu : {case} (connus : {sorted(P.CASES)})"
        r = P.run(case, seed=seed, board_id=board_id, verbose=True)
        if "error" in r:
            pytest.skip(f"build runner KO / harnais indisponible ({case}): {r['error']}")
        return r
    return _build


@pytest.fixture(scope="module")
def overkill_gate_case(live_session):
    """Fabrique : `overkill_gate_case("titus")` -> le dict de mesure du probe #178.

    Portee MODULE : les deux regimes de la paire sont montes une fois pour tout le fichier de test
    (chaque regime = un build + un drive + une attaque letale). `live_session` est tire ICI (le
    montage exige la session Frida) ; le runner est DISPOSE par le probe en sortie de `run()`."""
    cache: dict = {}

    def _case(case: str, seed: int = 17811) -> dict:
        assert case in OVK.CASES, f"cas inconnu : {case} (connus : {sorted(OVK.CASES)})"
        if case not in cache:
            r = OVK.run(case, seed=seed, verbose=True)
            if "error" in r:
                pytest.skip(f"montage overkill-gate KO ({case}): {r['error']}")
            cache[case] = r
        return cache[case]
    return _case


@pytest.fixture(scope="module")
def overkill_revive_case(live_session):
    """Fabrique : `overkill_revive_case("revive-crit")` -> le dict du montage B du probe #178/#R33.

    Observable INDEPENDANT du crescendo (`Narthecium_ReviveEffect` revive « unless Overkilled ») et
    tueur SANS le trait `ThrillSeekers` -> c'est ce montage qui ATTRIBUE l'overkill au flag
    `isCritical` plutot qu'au rider ThrillSeekers. Portee MODULE (un build par regime)."""
    cache: dict = {}

    def _case(case: str, seed: int = 17833) -> dict:
        assert case in OVK.REVIVE_CASES, \
            f"cas inconnu : {case} (connus : {sorted(OVK.REVIVE_CASES)})"
        if case not in cache:
            r = OVK.run_revive(case, seed=seed, verbose=True)
            if "error" in r:
                pytest.skip(f"montage overkill-revive KO ({case}): {r['error']}")
            cache[case] = r
        return cache[case]
    return _case
