"""DamageUtility — barème de dégât FIDÈLE (RE ghidra gqfc5mff6c, doc §13.7). UNE CLASSE par feuille (nom NATIF).

DamageDealt(35) = `IdunBattle.AI.Utilities.DamageUtility` (@1810cf370, TypeDefIndex 12112).
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

KillUnit(36) (`KillUnitUtility` @1810cff10 ; @1810e1a90) : +DefinitelyKill(BC 100) si WillBeKill,
  +PossibleKill(BC 50) si MightBeKill ; 0 si Steppable ; *-1 si friendly-fire.
OverkillUnit(37) (`OverkillUnitUtility` @1810d0200 ; @1810e1ed0) : +DefinitelyOverkill(BC 40) si
  WillBeOverkill, +PossibleOverkill(BC 15) si MightBeOverkill ; ADDITIONNÉ (un kill garanti+overkill est
  PRÉFÉRÉ = certitude) — l'OPPOSÉ de l'ancien `attack_utility`.

Composite Damage(34) (membership LUE runtime, doc §13.8) = INSTANCE `ComposedUtility` (Damage n'est PAS une
classe ; `DamageUtility` c'est le LEAF type-35). Ici : les 3 DOMINANTS (DamageDealt + KillUnit + OverkillUnit).
Les 10 situationnels (poids BC × condition trait/effet/boss/objet) = 0 sur une attaque basique → TODO.

⚠ Devise NATIVE bornée ~[0, 250] (DamageDealt ~[0,100] + KillUnit ~[0,100] + Overkill ~[0,40]). Le terme
dégât est une FRACTION des PV max × 80.
"""
from __future__ import annotations

from ..weights import Weights
from .base import BaseUtility, ComposedUtility
from .utility_type import UtilityType

W_DAMAGE = 80.0       # Fix64(0x50), DamageUtility.cctor
W_REMAINING = 20.0    # Fix64(0x14), DamageUtility.cctor


def _clamp01(x: float) -> float:
    return 0.0 if x < 0.0 else (1.0 if x > 1.0 else x)


class DamageUtility(BaseUtility):
    """`DamageUtility` (@1810cf370, TypeDefIndex 12112 ; UtilityType.DamageDealt=35) — le LEAF DamageDealt
    (le NOM natif de la classe est `DamageUtility`, PAS `DamageDealtUtility`). Corps = `<EvaluateAttackInSteps>
    d__2.MoveNext @1810e2280`. `GetHealthDamage`/`GetShieldDamage` = méthodes natives (VA citées)."""
    UTILITY_TYPE = 35

    def get_health_damage(self, pred) -> float:
        """`DamageUtility.GetHealthDamage @1810cec60` : Avg(AccurateHealthDamage@0x58) ; si
        `LimitedByMinHp@0xB0` (dégât plafonné par une règle min-HP) -> CurrentHealth@0x0 entier."""
        if pred.get("limitedByMinHp"):
            return float(pred.get("hpBefore") or 0)
        dmin = pred.get("healthDmgMin") or 0
        dmax = pred.get("healthDmgMax") or 0
        return (dmin + dmax) / 2.0

    def get_shield_damage(self, pred) -> float:
        """`DamageUtility.GetShieldDamage @1810cf080` : Avg(AccurateShieldDamage@0x78). 0 si le
        prédicteur n'a pas splitté (cible sans bouclier)."""
        smin = pred.get("shieldDmgMin") or 0
        smax = pred.get("shieldDmgMax") or 0
        return (smin + smax) / 2.0

    def evaluate(self, pred, target_max_hp, wt) -> float:
        if not pred:
            return 0.0
        hp = pred.get("hpBefore") or 0
        shield = pred.get("shieldBefore") or 0
        # combinedMax = (MaxHealth+1) + (Shield+1). Fallback maxHP=hpBefore si non fourni (cible pleine).
        max_hp = target_max_hp if (target_max_hp and target_max_hp > 0) else hp
        combined_max = (max_hp + 1) + (shield + 1)
        if combined_max <= 0:
            return 0.0
        dmg = self.get_health_damage(pred) + self.get_shield_damage(pred)
        remaining = (hp + 1) + (shield + 1)          # GetRemainingHealth @1810cee40
        u_damage = _clamp01(dmg / combined_max) * W_DAMAGE
        u_remaining = (1.0 - _clamp01((remaining - dmg) / combined_max)) * W_REMAINING
        return u_damage + u_remaining


class KillUnitUtility(BaseUtility):
    """`KillUnitUtility` (@1810cff10, TypeDefIndex 12124 ; UtilityType.KillUnit=36) ; @1810e1a90 :
    DefinitelyKill si WillBeKill (killSure), sinon PossibleKill si MightBeKill (kill). 0 sinon.
    (Steppable/friendly-fire non gérés : le moteur ne cible que des ennemis vivants.)"""
    UTILITY_TYPE = 36

    def evaluate(self, pred, target_max_hp, wt) -> float:
        if not pred:
            return 0.0
        if pred.get("killSure"):
            return wt.kill(definite=True)     # WillBeKill -> DefinitelyKill (100)
        if pred.get("kill"):
            return wt.kill(definite=False)    # MightBeKill -> PossibleKill (50)
        return 0.0


class OverkillUnitUtility(BaseUtility):
    """`OverkillUnitUtility` (@1810d0200, TypeDefIndex 12129 ; UtilityType.OverkillUnit=37) ; @1810e1ed0 :
    `WillBeOverkill` @18102ba40 (borne MIN) -> DefinitelyOverkill(40) ; sinon `MightBeOverkill` @18102b940
    (borne MAX) -> PossibleOverkill(15). Les deux = `DamagePrediction.IsOverkill @181032db0` : le dégât est
    un KILL **et** l'over-shoot `(dmg − hp)/hp × 100 >= overkillDmgPctOfHealth` (=100 => dmg >= 2×hp), OU
    `ForceOverkill@0xB2` + dmg>=hp. ⚠ #84 : le natif lit le dégât santé **BRUT** (@0x24/@0x28, NON capé par
    HP) — le port historique lisait `AccurateHealthDamage` CAPÉ à HP (`min(dmg,hp) > hp` = TOUJOURS FAUX)
    -> `OverkillUnit` INERTE pour toute attaque. Réactivé via `raw_health_damage` + `is_overkill` (l'over-shoot
    est déjà porté pour le cap Resilient, `trait_damage_limits.is_overkill`)."""
    UTILITY_TYPE = 37

    def evaluate(self, pred, target_max_hp, wt) -> float:
        if not pred:
            return 0.0
        from ..services.trait_damage_limits import is_overkill, _overkill_threshold_pct
        hp = pred.get("hpBefore") or 0
        if hp <= 0:
            return 0.0
        # raw* = dégât santé NON capé par HP (mirror @0x24/@0x28). Fallback capped (INERTE, ancien comportement)
        # si un caller (runner/move) ne fournit pas encore les champs raw -> pas de régression sur ces chemins.
        raw_min = pred.get("rawHealthDmgMin")
        raw_max = pred.get("rawHealthDmgMax")
        if raw_min is None or raw_max is None:
            raw_min, raw_max = pred.get("healthDmgMin") or 0, pred.get("healthDmgMax") or 0
        thr = _overkill_threshold_pct()
        allow = 1 if pred.get("forceOverkill") else 0
        if is_overkill(hp, raw_min, default_flag=0, allow_flag=allow, suppress=0, cond=1, threshold_pct=thr):
            return wt.overkill(definite=True)     # WillBeOverkill -> DefinitelyOverkill (40)
        if is_overkill(hp, raw_max, default_flag=0, allow_flag=allow, suppress=0, cond=1, threshold_pct=thr):
            return wt.overkill(definite=False)    # MightBeOverkill -> PossibleOverkill (15)
        return 0.0


# Composite Damage(34) = INSTANCE `ComposedUtility` (PAS de classe dediee ; Damage est un UtilityType, le
# composite est un ComposedUtility enregistre a 34 ; `DamageUtility` c'est le LEAF type-35). 3 feuilles
# DOMINANTES (DamageDealt=DamageUtility + KillUnit + OverkillUnit) ; 10 situationnels TODO. Devise ~[0,250].
DAMAGE_UTILITY = ComposedUtility([DamageUtility(), KillUnitUtility(), OverkillUnitUtility()],
                                 utility_type=UtilityType.Damage)


def damage_composite(pred: dict | None, target_max_hp: int | None, wt: Weights) -> float:
    """Composite Damage(34) = `DAMAGE_UTILITY.evaluate` (Σ des 3 feuilles dominantes). Wrapper mince pour
    les appelants (`probable_damage_event`, `runner/operations/triggers`, `move`). None -> 0."""
    if not pred:
        return 0.0
    return DAMAGE_UTILITY.evaluate(pred, target_max_hp, wt)
