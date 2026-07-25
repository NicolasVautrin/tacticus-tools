"""Port FIDÈLE de `FixMath.NET.Fix64` (Q31.32, gqfc5mff6c) — l'arithmétique à virgule fixe du moteur.

TOUT le pipeline dégât natif (spread, perçage, %-list, matérialisation) calcule en Fix64 : un long
64-bit signé dont les 32 bits bas sont la fraction (`raw = valeur × 2^32`). Le port historique
calculait en float64 → aux frontières ENTIÈRES (exactement là où kill/killSure flippe), le bruit
flottant traverse l'entier dans les DEUX sens : ni `round()` ni `floor()` float ne matchent le natif
(#30a : fix `round→floor` = 777s6 réparé mais 4 régressions, net 5→8 mismatches). Seule l'émulation
EXACTE (raw int Python, précision arbitraire) est fidèle.

Sémantique VÉRIFIÉE au décompilé (2026-07-19) :
  • `FixMath.NET.Fix64$$op_Multiply`  : produit 128-bit exact, TRONCATURE des 32 bits bas (hihi<<32 + hilo
    + lohi + lolo>>>32) = `(a·b) >> 32` (floor vers −∞). PAS d'arrondi.
  • `FixMath.NET.Fix64$$op_Division`  : long-division qui accumule le quotient à 2^-33 près puis
    `(q+1)>>1` = ROUND-HALF-UP sur la magnitude, signe appliqué après. ≠ troncature !
  • `FixMath.NET.Fix64$$op_Explicit`  : `raw >> 32` = floor (matérialisation Fix64→long).
  • `FixMath.NET.Fix64$$Round`        : frac<0.5→floor ; frac>0.5→floor+1 ; frac==0.5 → mode 0 = ToEven,
    mode 1 = AwayFromZero (négatif→floor, positif→floor+1).
  • `FromInt`                 : `n << 32`.

Les saturations MinValue/MaxValue natives (overflow 64-bit) ne sont PAS émulées : les grandeurs du
pipeline dégât (≤ ~10^5) en sont à 30 bits de marge ; Python est en précision arbitraire.
"""
from __future__ import annotations

ONE: int = 1 << 32          # Fix64.One (static +0x20)
_FRAC_MASK: int = ONE - 1


def from_int(n: int) -> int:
    """Fix64.FromInt — raw = n × 2^32."""
    return n << 32


def from_number(x) -> int:
    """Coercion d'entrée de chaîne → raw. int = exact (FromInt) ; Fix64 = passthrough exact (.raw) ;
    float legacy = approximation nearest (interop uniquement — les chemins exacts ne passent QUE des
    int/Fix64, un float non-Fix64 signale un caller hors chaîne, ex. additif fractionnaire #64)."""
    if isinstance(x, Fix64):
        return x.raw
    if isinstance(x, int):
        return x << 32
    return round(x * ONE)


def mul(a_raw: int, b_raw: int) -> int:
    """FixMath.NET.Fix64$$op_Multiply — produit exact puis TRONCATURE (floor vers −∞).
    Le `>>` Python sur int négatif est arithmétique (floor) = exactement le natif."""
    return (a_raw * b_raw) >> 32


def div(a_raw: int, b_raw: int) -> int:
    """FixMath.NET.Fix64$$op_Division — ROUND-HALF-UP sur |a|/|b| (quotient accumulé à 2^-33 près
    puis `(q+1)>>1`), signe appliqué après. b=0 → MaxValue natif (jamais atteint ici : diviseurs
    = constantes config non nulles, ex. 100)."""
    if b_raw == 0:
        return (1 << 63) - 1        # Fix64.MaxValue (mirror FixMath.NET.Fix64$$op_Division branche divide-by-zero)
    q2 = (abs(a_raw) << 33) // abs(b_raw)
    m = (q2 + 1) >> 1
    return -m if (a_raw < 0) != (b_raw < 0) else m


def round_raw(raw: int, mode: int = 1) -> int:
    """FixMath.NET.Fix64$$Round — arrondit à l'ENTIER Fix64 (raw intégral). mode 0 = ToEven,
    mode 1 = AwayFromZero (le seul utilisé par le pipeline dégât : spread, min/max, %-list capée)."""
    frac = raw & _FRAC_MASK
    integral = raw - frac           # floor vers −∞ (masque bas = décompile `& 0xffffffff00000000`)
    if frac < 0x80000000:
        return integral
    if frac == 0x80000000:
        if mode == 0:
            if ((raw >> 32) & 1) == 0:
                return integral     # ToEven : entier pair → floor
        elif integral < 0:
            return integral         # AwayFromZero négatif : -2.5 → -3 (= floor)
    return integral + ONE


def to_int(raw: int) -> int:
    """FixMath.NET.Fix64$$op_Explicit — matérialisation Fix64→long = `raw >> 32` (floor).
    C'est LA conversion int du pipeline (bornes prédiction IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw+0x1ed7+, dégât tiré combat
    `IdunBattle.Core.Services.DamagePrediction$$CalculateAbilityDamage`) — PAS un round."""
    return raw >> 32


def mult_raw_from_float(mult: float) -> int:
    """Reconstruit le raw EXACT d'un multiplicateur %-list stocké en float (`1 ± pct/100`,
    `IdunBattle.Core.Services.DamageCalculations$$GetMultiplierFromDamageBonus` = `One ± Div(FromInt(|pct|), FromInt(100))`).
    Pour pct ENTIER, `round(mult × 2^32)` = le raw natif exactement : l'erreur float du mult
    (≤ ~2e-6 unité raw) est très en-deçà du demi-pas, et aucune frontière .5 n'existe
    (pct×2^33/100 impair impossible pour pct entier). Évite de changer le format `pct_list`."""
    return round(mult * ONE)


class Fix64(float):
    """Valeur Fix64 qui EST un float (lisible par tous les callers legacy : round(), int(),
    comparaisons, arithmétique dégradée) tout en portant le raw exact (`.raw`) pour la chaîne
    exacte. ⚠ Toute arithmétique Python directe (`+`, `*`) sur ce type retombe en float et PERD
    l'exactitude — les fonctions de chaîne doivent passer par mul/div/round_raw/to_int sur `.raw`."""
    __slots__ = ("raw",)

    def __new__(cls, raw: int) -> "Fix64":
        self = super().__new__(cls, raw / ONE)
        self.raw = raw
        return self
