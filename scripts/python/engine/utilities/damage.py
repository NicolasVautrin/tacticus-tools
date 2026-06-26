"""DamageUtility — barème de dégât FIDÈLE (RE ghidra gqfc5mff6c, doc §13.7).

DamageDealt(35) = `IdunBattle.AI.Utilities.DamageUtility`.
- `.cctor` (@1810cf2e0) : **W_damage = Fix64(0x50) = 80**, **W_remaining = Fix64(0x14) = 20**.
- `<EvaluateAttackInSteps>d__2.MoveNext` (@1810e2280) :
    dmg         = Avg(healthMinMax) [+ Avg(shieldMinMax)]               # voir NOTE bouclier
    combinedMax = (target.MaxHealth + 1) + (target.Shield + 1)         # boss : MaxHealth -> 169
    u_damage    = Clamp(dmg / combinedMax, 0, 1) * 80
    u_remaining = (1 - Clamp((remaining - dmg) / combinedMax, 0, 1)) * 20    # remaining = PV courants
    u           = u_damage + u_remaining ;  *-1 si friendly-fire (cible = ami)

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


def _avg_health_dmg(pred: dict) -> float:
    """`MinMaxDamage.Avg(AccurateHealthDamage)` = (min+max)/2 du dégât SANTÉ.
    NOTE bouclier : le natif ajoute aussi `Avg(shieldMinMax)`. `aiPredict` n'expose pas le dégât
    bouclier séparé (seulement healthDmg + totalDmg). On porte le dégât SANTÉ (dominant ; exact si la
    cible n'a pas de bouclier). Bouclier = TODO (champ non exposé). cf. doc §13.7."""
    dmin = pred.get("healthDmgMin") or 0
    dmax = pred.get("healthDmgMax") or 0
    return (dmin + dmax) / 2.0


def damage_dealt(pred: dict | None, target_max_hp: int | None) -> float:
    """DamageDealt(35) FIDÈLE : `clamp(dmg/maxPool,0,1)*80 + (1-clamp((remaining-dmg)/maxPool,0,1))*20`.
    `remaining` = PV courants (`hpBefore`) ; `maxPool` = MaxHealth + Shield + 2 (cible non-boss)."""
    if not pred:
        return 0.0
    remaining = pred.get("hpBefore") or 0
    shield = pred.get("shieldBefore") or 0
    # combinedMax = (MaxHealth+1) + (Shield+1). Fallback maxHP=hpBefore si non fourni (cible pleine).
    max_hp = target_max_hp if (target_max_hp and target_max_hp > 0) else remaining
    combined_max = (max_hp + 1) + (shield + 1)
    if combined_max <= 0:
        return 0.0
    dmg = _avg_health_dmg(pred)
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
