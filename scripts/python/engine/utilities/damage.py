"""DamageUtility — barème de dégât FIDÈLE (RE ghidra gqfc5mff6c, doc §13.7).

DamageDealt(35) = `IdunBattle.AI.Utilities.DamageUtility`.
- `.cctor` (@1810cf2e0) : **W_damage = Fix64(0x50) = 80**, **W_remaining = Fix64(0x14) = 20**.
- `<EvaluateAttackInSteps>d__2.MoveNext` (@1810e2280) — RE LECTURE INTÉGRALE (2026-07-02) :
    hAvg        = Avg(AccurateHealthDamage@0x58) ; si LimitedByMinHp@0xB0 -> CurrentHealth@0x0
    sAvg        = Avg(AccurateShieldDamage@0x78)                        # bouclier COMPTE dans l'utilité
    D           = hAvg + sAvg
    combinedMax = (target.MaxHealth + 1) + (GetShield(target) + 1)     # boss : config 0xa9 (@1810ce8a0)
    remaining   = (target.CurrentHealth + 1) + (GetShield(target) + 1) # GetRemainingHealth @1810cee40
    u_damage    = Clamp(D / combinedMax, 0, 1) * 80
    u_remaining = (1 - Clamp((remaining - D) / combinedMax, 0, 1)) * 20
    u           = u_damage + u_remaining ;  *-1 si friendly-fire (cible = ami)
  Preuve numérique (trace scorerUtilTrace seed777 step-11) : 86 dmg 936-2568 hp 8585/9037
  -> 20.38 EXACT ; 82 (worldTerminator shield 3989, santé 0-58 + bouclier 2871-3989)
  -> 25.57 EXACT = la raison du pick natif [82,78] (Σ=50.49 + tuile 50 = 100.49).

KillUnit(36) (@1810e1a90)    : +DefinitelyKill(BC 100) si WillBeKill, +PossibleKill(BC 50) si MightBeKill ;
                               0 si la cible est Steppable ; *-1 si friendly-fire.
OverkillUnit(37) (@1810e1ed0): +DefinitelyOverkill(BC 40) si WillBeOverkill, +PossibleOverkill(BC 15) si
                               MightBeOverkill ; *-1 si friendly-fire. Le natif ADDITIONNE l'overkill
                               (un kill garanti+overkill est PRÉFÉRÉ à un kill marginal = certitude) —
                               c'est l'OPPOSÉ de l'ancien `attack_utility` qui le SOUSTRAYAIT.

Composite Damage(34) (membership LUE runtime, doc §13.8) =
  OnlyImpervious(40) · DamageDealt(35) · KillUnit(36) · DislikeObjects(38) · DislikeBoss(43) ·
  DislikeEnvUnits(39) · OverkillUnit(37) · EnemyOnTerritoryTile(41) · Triggered(2) · TriggeredNonOwner(4) ·
  UnitSpecific(3) · OptimizedGait(59) · AttackTargetWithEffect(42).
Ici : les 3 DOMINANTS (DamageDealt + KillUnit + OverkillUnit). Les 10 situationnels (poids BC × condition
trait/effet/boss/objet) = 0 sur une attaque basique d'unité → portés incrémentalement (TODO).

⚠ Devise NATIVE bornée ~[0, 250] (DamageDealt ~[0,100] + KillUnit ~[0,100] + Overkill ~[0,40]) — pas de
milliers bruts, pas de knob. Le terme dégât est une FRACTION des PV max × 80.
"""
from __future__ import annotations

from ..weights import Weights

W_DAMAGE = 80.0       # Fix64(0x50), DamageUtility.cctor
W_REMAINING = 20.0    # Fix64(0x14), DamageUtility.cctor


def _clamp01(x: float) -> float:
    return 0.0 if x < 0.0 else (1.0 if x > 1.0 else x)


def _get_health_damage(pred: dict) -> float:
    """`DamageUtility.GetHealthDamage @1810cec60` : Avg(AccurateHealthDamage@0x58) ; si
    `LimitedByMinHp@0xB0` (dégât plafonné par une règle min-HP) -> CurrentHealth@0x0 entier."""
    if pred.get("limitedByMinHp"):
        return float(pred.get("hpBefore") or 0)
    dmin = pred.get("healthDmgMin") or 0
    dmax = pred.get("healthDmgMax") or 0
    return (dmin + dmax) / 2.0


def _get_shield_damage(pred: dict) -> float:
    """`DamageUtility.GetShieldDamage @1810cf080` : Avg(AccurateShieldDamage@0x78). 0 si le
    prédicteur n'a pas splitté (cible sans bouclier)."""
    smin = pred.get("shieldDmgMin") or 0
    smax = pred.get("shieldDmgMax") or 0
    return (smin + smax) / 2.0


def damage_dealt(pred: dict | None, target_max_hp: int | None) -> float:
    """DamageDealt(35) FIDÈLE (`<EvaluateAttackInSteps>d__2.MoveNext @1810e2280`) :
        D = hAvg + sAvg ; maxPool = (MaxHealth+1)+(Shield+1) ;
        remaining = (CurrentHealth+1)+(Shield+1)   # GetRemainingHealth @1810cee40
        u = clamp(D/maxPool,0,1)*80 + (1-clamp((remaining-D)/maxPool,0,1))*20."""
    if not pred:
        return 0.0
    hp = pred.get("hpBefore") or 0
    shield = pred.get("shieldBefore") or 0
    # combinedMax = (MaxHealth+1) + (Shield+1). Fallback maxHP=hpBefore si non fourni (cible pleine).
    max_hp = target_max_hp if (target_max_hp and target_max_hp > 0) else hp
    combined_max = (max_hp + 1) + (shield + 1)
    if combined_max <= 0:
        return 0.0
    dmg = _get_health_damage(pred) + _get_shield_damage(pred)
    remaining = (hp + 1) + (shield + 1)
    u_damage = _clamp01(dmg / combined_max) * W_DAMAGE
    u_remaining = (1.0 - _clamp01((remaining - dmg) / combined_max)) * W_REMAINING
    return u_damage + u_remaining


def kill_unit(pred: dict | None, wt: Weights) -> float:
    """KillUnit(36) FIDÈLE : DefinitelyKill si WillBeKill (killSure), sinon PossibleKill si MightBeKill
    (kill). 0 sinon. (Steppable/friendly-fire non gérés : le moteur ne cible que des ennemis vivants.)"""
    if not pred:
        return 0.0
    if pred.get("killSure"):
        return wt.kill(definite=True)     # WillBeKill -> DefinitelyKill (100)
    if pred.get("kill"):
        return wt.kill(definite=False)    # MightBeKill -> PossibleKill (50)
    return 0.0


def overkill_unit(pred: dict | None, wt: Weights) -> float:
    """OverkillUnit(37) FIDÈLE : ADDITIONNÉ (natif). WillBeOverkill = le dégât MIN dépasse STRICTEMENT
    les PV (kill garanti avec gaspillage) -> DefinitelyOverkill ; MightBeOverkill = dégât MAX dépasse
    strictement -> PossibleOverkill."""
    if not pred:
        return 0.0
    hp = pred.get("hpBefore") or 0
    dmin = pred.get("healthDmgMin") or 0
    dmax = pred.get("healthDmgMax") or 0
    if dmin > hp:
        return wt.overkill(definite=True)     # WillBeOverkill -> DefinitelyOverkill (40)
    if dmax > hp:
        return wt.overkill(definite=False)    # MightBeOverkill -> PossibleOverkill (15)
    return 0.0


def damage_composite(pred: dict | None, target_max_hp: int | None, wt: Weights) -> float:
    """Composite Damage(34) — 3 feuilles DOMINANTES (DamageDealt + KillUnit + OverkillUnit), devise
    native ~[0,250]. Les 10 situationnels = 0 sur attaque basique (TODO incrémental, doc §13.9)."""
    if not pred:
        return 0.0
    return (damage_dealt(pred, target_max_hp)
            + kill_unit(pred, wt)
            + overkill_unit(pred, wt))
