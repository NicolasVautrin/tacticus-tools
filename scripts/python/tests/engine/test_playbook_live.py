"""Agrément playbook — décision du MOTEUR (`engine.engine_decide`) CONFRONTÉE pas à
pas à l'IA NATIVE LIVE (`aiStepDryRun`).

Réutilise `engine_validate.run_agreement` (SOURCE UNIQUE de la comparaison) : on
marche la trajectoire native sur un runner ISOLÉ frais (run_agreement applique les
actions natives → mutation), et on compare à chaque chunk décisionnel :
  • ABILITY (sélection cible+ability) = PILIER validé → exigé EXACT (100%).
  • POSITIONING (destination move) = scoring partiel (proxy) → plancher de
    non-régression (% override par env), pas un critère exact.

Property-based, indépendant version/seed : agrément vs natif en cours d'exécution,
assertions génériques sur tous les pas. Le seed (env `PLAYBOOK_SEED`) n'est qu'un
générateur de bataille. Skip si pas de session / aucun chunk comparé. Aucun snapshot
gelé : l'oracle est l'IA native live.
"""
from __future__ import annotations

import os

import pytest

STEPS = int(os.environ.get("PLAYBOOK_STEPS", "12"))
MIN_EXACT_PCT = int(os.environ.get("PLAYBOOK_MIN_EXACT", "45"))   # plancher positioning exact
MIN_NEAR_PCT = int(os.environ.get("PLAYBOOK_MIN_NEAR", "65"))     # plancher positioning ≤1hex
MIN_DECISIONS = int(os.environ.get("PLAYBOOK_MIN_DECISIONS", "3"))


@pytest.fixture(scope="session")
def playbook_agreement(live_session, build_runner):
    """Marche la trajectoire native une fois (runner isolé frais auto-disposé) →
    résultat d'agrément {pos, ability, records}."""
    import engine_validate as EV

    info = build_runner(os.environ.get("PLAYBOOK_SEED", "777"))   # générateur, hors critère
    wt = EV.weights.load()
    res = EV.run_agreement(live_session, info["rid"], STEPS, wt)
    if not res["pos"]["n"] and not res["ability"]["n"]:
        pytest.skip("aucun chunk décisionnel comparé (trajectoire native vide)")
    return res


def test_decision_coverage(playbook_agreement):
    """Garde-fou anti-faux-vert : assez de décisions comparées pour que les tests
    d'agrément aient du sens."""
    n = playbook_agreement["pos"]["n"] + playbook_agreement["ability"]["n"]
    assert n >= MIN_DECISIONS, (
        f"couverture trop faible : {n} décisions (augmente PLAYBOOK_STEPS)")


def test_ability_selection_matches_native(playbook_agreement):
    """PILIER : la sélection d'ability (cible + ability) doit être EXACTE vs native."""
    ab = playbook_agreement["ability"]
    if ab["n"] == 0:
        pytest.skip("aucun cast d'ability natif sur cette trajectoire")
    misses = [r for r in playbook_agreement["records"]
              if r["kind"] == "ability" and not r["match"]]
    detail = "\n  ".join(
        f"step {r['step']} u{r['uid']}: native={r['native']} engine={r['engine']} "
        f"(engine_kind={r['engine_kind']})" for r in misses)
    assert not misses, (
        f"sélection d'ability != native ({len(misses)}/{ab['n']}):\n  " + detail)


def test_positioning_within_regression_floor(playbook_agreement):
    """POSITIONING : plancher de non-régression (proxy partiel — pas un critère
    exact). Override : PLAYBOOK_MIN_EXACT / PLAYBOOK_MIN_NEAR."""
    pos = playbook_agreement["pos"]
    if pos["n"] == 0:
        pytest.skip("aucun move natif comparé sur cette trajectoire")
    exact_pct = 100 * pos["exact"] // pos["n"]
    near_pct = 100 * pos["near"] // pos["n"]
    misses = "\n  ".join(
        f"step {r['step']} u{r['uid']}: native->{r['native']} engine->{r['engine']} "
        f"(dist={r['dist']})"
        for r in playbook_agreement["records"]
        if r["kind"] == "move" and (r["dist"] is None or r["dist"] > 1))
    assert exact_pct >= MIN_EXACT_PCT and near_pct >= MIN_NEAR_PCT, (
        f"positioning sous le plancher : exact={exact_pct}% (min {MIN_EXACT_PCT}) "
        f"≤1hex={near_pct}% (min {MIN_NEAR_PCT}) sur {pos['n']} moves\n  " + misses)
