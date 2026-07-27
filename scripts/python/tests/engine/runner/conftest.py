"""Fixtures locales a la tranche RUNNER.

`psychic_aoe_case` — MONTAGE NOMME ET REUTILISABLE des deux AoE Psychic (PlagueWind 1035 /
Doombolt 1102). Le montage lui-meme (build isole, drive des positions des DEUX camps, capture
`decisionView`/`observeBattle`/`combatSnapshot`/`boardGraph`/`dumpRng`, replay OFFLINE sur le MEME
etat et le MEME `state.rng`, cast LIVE, comparaison per-coup, contre-epreuve de discriminance) vit
dans `scripts/python/probe_psychic_aoe.py` — la fixture n'est que sa PORTE pytest : un seul point
qui traduit « harnais indisponible » en skip (converti en ECHEC par le conftest racine) et qui garde
les tests lisibles.

Consommateurs : `test_plague_wind_live.py`, `test_doombolt_live.py`. Ajouter un cas = ajouter une
entree dans `probe_psychic_aoe.CASES`, pas dupliquer un montage inline dans un test."""
from __future__ import annotations

import pytest

import probe_psychic_aoe as P


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
