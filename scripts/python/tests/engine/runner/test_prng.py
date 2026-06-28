"""RNG MT19937 — validation contre le VECTEUR DE RÉFÉRENCE canonique (mt19937ar).

EXCEPTION ASSUMÉE au principe « tests confront live » : le RNG du jeu est un MT19937
STANDARD (prouvé bit-pour-bit au décompilé, cf. engine/runner/prng.py). Le vecteur
publié `mt19937ar.out` EST la spécification que le binaire implémente — vérité externe
canonique et VERSION-INDÉPENDANTE, supérieure à un snapshot live. La confrontation du
binaire LIVE (RPC dump-RNG : même seed → mêmes sorties) reste un complément à venir.
"""
from __future__ import annotations

import random

from engine.runner.prng import MersenneTwister, IntBasedMersenneTwister

# 10 premiers genrand_int32 de mt19937ar (init_by_array, clé {0x123,0x234,0x345,0x456}).
# Référence EXTERNE publiée (non dérivée du port) → valide twist+tempering+init_genrand.
_REF = [1067595299, 955945823, 477289528, 4107218783, 4228976476,
        3344332714, 3355579695, 227628506, 810200273, 2591290167]


def _init_by_array(mt: MersenneTwister, key) -> None:
    """init_by_array standard (helper de TEST uniquement — le jeu seede par int).
    Appelle init_genrand(19650218) puis mélange la clé → exerce tout le cœur."""
    mt.init_genrand(19650218)
    i, j = 1, 0
    for _ in range(max(624, len(key))):
        mt.mt[i] = ((mt.mt[i] ^ ((mt.mt[i - 1] ^ (mt.mt[i - 1] >> 30)) * 1664525))
                    + key[j] + j) & 0xFFFFFFFF
        i += 1
        j += 1
        if i >= 624:
            mt.mt[0] = mt.mt[623]
            i = 1
        if j >= len(key):
            j = 0
    for _ in range(623):
        mt.mt[i] = ((mt.mt[i] ^ ((mt.mt[i - 1] ^ (mt.mt[i - 1] >> 30)) * 1566083941))
                    - i) & 0xFFFFFFFF
        i += 1
        if i >= 624:
            mt.mt[0] = mt.mt[623]
            i = 1
    mt.mt[0] = 0x80000000
    mt.mti = 624


def test_genrand_matches_reference_vector():
    mt = MersenneTwister()
    _init_by_array(mt, [0x123, 0x234, 0x345, 0x456])
    got = [mt.genrand_int32() for _ in range(10)]
    assert got == _REF, f"MT19937 != référence:\n got={got}\n ref={_REF}"


def test_matches_python_stdlib_mt19937():
    """Validation croisée contre le MT19937 de la stdlib Python (implémentation
    canonique INDÉPENDANTE, version-indépendante) : à état mt[] identique, nos
    genrand_int32 == getrandbits(32) de Python sur 200 tirages."""
    mine = IntBasedMersenneTwister(0x4D2)            # seed arbitraire
    random.setstate((3, tuple(mine.mt + [mine.mti]), None))
    assert [mine.genrand_int32() for _ in range(200)] == \
           [random.getrandbits(32) for _ in range(200)]


def test_init_genrand_deterministic_and_32bit():
    a = IntBasedMersenneTwister(777)
    b = IntBasedMersenneTwister(777)
    sa = [a.genrand_int32() for _ in range(64)]
    sb = [b.genrand_int32() for _ in range(64)]
    assert sa == sb, "même seed → mêmes sorties (déterminisme)"
    assert all(0 <= x <= 0xFFFFFFFF for x in sa)


def test_default_seed_is_5489():
    """genrand sur instance non seedée == init_genrand(5489) (seed défaut natif)."""
    unseeded = MersenneTwister()                 # mti = 625 → seedera 5489
    seeded = MersenneTwister()
    seeded.init_genrand(5489)
    assert [unseeded.genrand_int32() for _ in range(5)] == \
           [seeded.genrand_int32() for _ in range(5)]


def test_next_range_bounds_pow2_and_reject():
    r = IntBasedMersenneTwister(12345)
    for _ in range(2000):
        assert 5 <= r.next_internal(5, 17) < 17        # range 12 (non puissance de 2)
    for _ in range(2000):
        assert 0 <= r.next(16) < 16                     # range 16 (puissance de 2)
    assert r.next_internal(9, 10) == 9                  # range 1 dégénéré
