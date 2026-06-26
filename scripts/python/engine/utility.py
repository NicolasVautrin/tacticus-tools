"""Barème d'utilité d'une action — `ComparablePlaybook.CalculateActionUtility` (§1.1).

PREMIÈRE COUPE, validation-driven. Le cœur RE'd + validé = les poids kill/overkill
(`KillUnit`/`OverkillUnit`). Le terme per-damage NON-létal (config `+0x80`) n'est pas
encore exactement RE'd → approximation linéaire bornée < PossibleKill (invariant : un
kill bat toujours un chip). À RAFFINER par l'agreement (le harnais dira où ça diverge).
cf. docs/rl/playbook-engine.md §1.1 / §6 (mapping damage→utilité = raffinement agreement-driven).
"""
from __future__ import annotations

from .weights import Weights


def attack_utility(pred: dict | None, wt: Weights) -> float:
    """Utilité d'une attaque depuis une prédiction `aiPredict` (DamagePredictionResult :
    `kill`=MightBeKill, `killSure`=WillBeKill, `healthDmgMin/Max`, `hpBefore`). Le moteur
    natif lit ces seuils EXACTS (cf. TF04) → on s'aligne dessus."""
    if not pred:
        return 0.0
    hp = pred.get("hpBefore") or 0
    dmin = pred.get("healthDmgMin") or 0
    dmax = pred.get("healthDmgMax") or 0
    u = 0.0
    if pred.get("killSure"):                       # WillBeKill (garanti)
        u += wt.kill(definite=True)                # 100
        if dmin - hp > 0:                          # overkill garanti
            u -= wt.overkill(definite=True)        # 40
    elif pred.get("kill"):                         # MightBeKill (possible)
        u += wt.kill(definite=False)               # 50
        if dmax - hp > 0:
            u -= wt.overkill(definite=False)       # 15
    else:                                          # non-létal : fraction de PV (approx)
        frac = (dmax / hp) if hp > 0 else 0.0      # À RAFFINER (agreement)
        u += frac * wt.kill(definite=False)        # borné < PossibleKill par construction
    return u
