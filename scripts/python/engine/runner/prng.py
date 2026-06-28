"""RNG de bataille — port FIDÈLE de `IdunBattle.Utils.PRNG.*` (RE gqfc5mff6c).

MT19937 STANDARD confirmé bit-pour-bit depuis le décompilé :
  • `MersenneTwister.init_genrand` @180e3a750 : mt[0]=seed ;
    mt[i] = 1812433253*(mt[i-1]^(mt[i-1]>>30)) + i   (mult 0x6c078965).
  • `MersenneTwister.genrand_int32` @180e3a3e0 : twist (UPPER=0x80000000|LOWER=
    0x7fffffff, M=397, MATRIX_A=0x9908b0df via mag01[y&1]) + tempering standard
    (>>11 ; <<7 & 0x9d2c5680 ; <<15 & 0xefc60000 ; >>18). Seed défaut 5489 si non
    seedé (mti==625). Compteur d'appels @this+0x14, mti @+0x28, mt[] @+0x20.
  • `MersenneTwister.genrand_real2` @180e3a6b0 : (g>>2)/2^30 ∈ [0,1) (Fix64).
  • `IntBasedMersenneTwister.NextInternal(lo,hi)` @180e39be0 : entier ∈ [lo,hi).
    range puissance-de-2 → ((range*(g>>1))>>31)+lo ; sinon rejet façon Java
    nextInt (r=g>>1 ; v=r%range ; rejet si (range-1)+(r-v) déborde int32<0).
  • `IntBasedMersenneTwister.Next(bound)` @180e394e0 : [0,bound), même math (min=0).

NB : le compteur @+0x14 est incrémenté par genrand_int32 ET par Next/NextInternal
(diagnostic seulement ; sans effet sur les sorties). Le bit-exact rend le runner
reproductible (rejouer le même seed → mêmes tirages).
"""
from __future__ import annotations

_U32 = 0xFFFFFFFF
_N = 624
_M = 397
_MATRIX_A = 0x9908B0DF
_UPPER = 0x80000000
_LOWER = 0x7FFFFFFF


def _i32(x: int) -> int:
    """Tronque en int32 signé (pour le test de débordement du rejet)."""
    x &= _U32
    return x - 0x100000000 if x & 0x80000000 else x


class MersenneTwister:
    """MT19937 standard (cf. en-tête)."""

    __slots__ = ("mt", "mti", "call_count")

    def __init__(self):
        self.mt = [0] * _N
        self.mti = _N + 1          # non seedé → genrand seedera avec 5489
        self.call_count = 0

    def init_genrand(self, seed: int) -> None:
        mt = self.mt
        mt[0] = seed & _U32
        for i in range(1, _N):
            mt[i] = (1812433253 * (mt[i - 1] ^ (mt[i - 1] >> 30)) + i) & _U32
        self.mti = _N

    def genrand_int32(self) -> int:
        self.call_count += 1
        mt = self.mt
        if self.mti >= _N:
            if self.mti == _N + 1:          # jamais seedé → seed défaut natif
                self.init_genrand(5489)
            for kk in range(_N - _M):                    # 0..226
                y = (mt[kk] & _UPPER) | (mt[kk + 1] & _LOWER)
                mt[kk] = mt[kk + _M] ^ (y >> 1) ^ (_MATRIX_A if y & 1 else 0)
            for kk in range(_N - _M, _N - 1):            # 227..622
                y = (mt[kk] & _UPPER) | (mt[kk + 1] & _LOWER)
                mt[kk] = mt[kk + (_M - _N)] ^ (y >> 1) ^ (_MATRIX_A if y & 1 else 0)
            y = (mt[_N - 1] & _UPPER) | (mt[0] & _LOWER)
            mt[_N - 1] = mt[_M - 1] ^ (y >> 1) ^ (_MATRIX_A if y & 1 else 0)
            self.mti = 0
        y = mt[self.mti]
        self.mti += 1
        y ^= y >> 11
        y ^= (y << 7) & 0x9D2C5680
        y ^= (y << 15) & 0xEFC60000
        y ^= y >> 18
        return y & _U32

    def genrand_real2(self) -> float:
        """∈ [0,1) — (g>>2)/2^30 (le jeu calcule en Fix64 ; ici float suffit hors
        bit-exact Fix64). Pour le bit-exact, préférer les Next entiers."""
        return (self.genrand_int32() >> 2) / (1 << 30)


class IntBasedMersenneTwister(MersenneTwister):
    """Wrapper entier (cf. en-tête). `seed` int (de la BC) → init_genrand."""

    __slots__ = ()

    def __init__(self, seed: int | None = None):
        super().__init__()
        if seed is not None:
            self.init_genrand(seed)

    def next_internal(self, lo: int, hi: int) -> int:
        """Entier ∈ [lo, hi) (hi exclu) — NextInternal @180e39be0."""
        self.call_count += 1
        rng = hi - lo
        if (-rng & rng) == rng:                      # puissance de 2 (ou 0)
            r = self.genrand_int32() >> 1
            return ((rng * r) >> 31) + lo
        while True:                                  # rejet façon Java nextInt
            r = self.genrand_int32() >> 1
            v = r % rng
            if _i32((rng - 1) + (r - v)) >= 0:
                return v + lo

    def next_bool(self, chance: int) -> bool:
        """`IntBasedMersenneTwister.NextBool(chance)` @180e39720 — bit-exact (RE LECTURE) :
            v = ((genrand>>1) % 99) + 1   ∈ [1,99]   (rejet façon Java, range 99)
            return v <= chance
        ≡ `next_internal(1, 100) <= chance` (MÊME consommation genrand + compteur). Primitive
        des rolls crit/block/evasion (`DamageCalculations.RollCritical`/`ApplyRandomBlockDamage`/
        `ApplyRandomEvasion` → `IPseudoRNG.NextBool`, slot #5). chance≥99→toujours vrai ; ≤0→faux."""
        return self.next_internal(1, 100) <= chance

    def next(self, bound: int) -> int:
        """Entier ∈ [0, bound) — IPseudoRNG.Next @180e394e0 (même math, min=0)."""
        self.call_count += 1
        rng = bound
        if (-rng & rng) == rng:
            r = self.genrand_int32() >> 1
            return (rng * r) >> 31
        while True:
            r = self.genrand_int32() >> 1
            v = r % rng
            if _i32((rng - 1) + (r - v)) >= 0:
                return v
