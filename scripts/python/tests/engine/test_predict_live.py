"""Agrément prédiction de dégât — `engine` (chaîne fidèle base×hits + perçage +
armure + MODIFIER effets) CONFRONTÉE à l'oracle natif LIVE (`decisionView`
dmgMin/dmgMax).

Réutilise `predict_validate.build_samples` (SOURCE UNIQUE de la chaîne — le test ne
re-dérive jamais la logique) sur un runner ISOLÉ frais : la prédiction exige des
cibles à portée, donc le harnais DRIVE les unités au contact (mutation) — on
n'emprunte pas un runner live partagé pour ne rien perturber.

Property-based, indépendant version/seed : on exige l'agrément EXACT (±3 ; arrondi
//100 vs Fix64) sur TOUS les échantillons d'attaque normale « clean » (non
`predOptimistic`), quelle que soit la bataille. Le seed n'est qu'un générateur
(env `PREDICT_SEED`), hors critère. Skip si pas de session ou aucun échantillon à
portée. Oracle = natif en cours d'exécution, aucun snapshot gelé.
"""
from __future__ import annotations

import os

import pytest


@pytest.fixture(scope="session")
def predict_samples(live_session, build_runner):
    """Échantillons d'agrément capturés une fois (runner isolé frais auto-disposé)."""
    import predict_validate as PV

    info = build_runner(os.environ.get("PREDICT_SEED", "777"))   # générateur, hors critère
    rows = PV.build_samples(live_session, info["rid"], info["my_team"],
                            int(os.environ.get("PREDICT_MAX_TURNS", "6")))
    if not rows:
        pytest.skip("aucun échantillon d'attaque normale à portée (drive insuffisant)")
    return rows


def test_normal_attack_prediction_matches_oracle(predict_samples):
    """Chaque attaque normale clean : prédiction offline == oracle natif, exact."""
    import predict_validate as PV

    clean = [r for r in predict_samples if PV.sample_is_clean(r)]
    assert clean, "aucun échantillon clean (non predOptimistic) capturé"
    failures = [
        f"u{r['att']}->u{r['tgt']}/{r['tgtVis']}: "
        f"oracle={r['oracle']} offline={r['offline']} "
        f"base={r['base']} pierce={r['pierce']} armor={r['armor']} "
        f"hits={r['hits']} mods={r['mods']} effects={r['effects']}"
        for r in clean if not PV.sample_is_ok(r)
    ]
    assert not failures, (
        f"divergences prédiction vs oracle ({len(failures)}/{len(clean)} clean):\n  "
        + "\n  ".join(failures))


def test_prediction_has_meaningful_coverage(predict_samples):
    """Garde-fou anti-faux-vert : au moins quelques attaquants distincts couverts
    (sinon le test ci-dessus passerait sur un échantillon trivial)."""
    import predict_validate as PV

    attackers = {r["att"] for r in predict_samples if PV.sample_is_clean(r)}
    assert len(attackers) >= 2, (
        f"couverture trop faible : {len(attackers)} attaquant(s) clean "
        f"— augmente PREDICT_MAX_TURNS ou vérifie le drive")
