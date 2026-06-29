"""ATTAQUE NORMALE sur cible ARMURÉE — verrou de l'ORDRE reduce-then-roll (replay-diff LIVE).

Re-vérifie (demande user) que l'attaque NORMALE du runner (`AttackDamageOperation.execute`) est
bit-exact sur une cible à FORTE armure, où l'ordre réduction↔tirage est DISCRIMINANT (≠ cible armure 0).

Confirmé live (necroDestroyer 6 coups mêlée → necroOverlord, armure 1909 pierce 60) :
  • reduce-then-roll (runner) = live À L'UNITÉ : [514,582,514,578,642,603].
  • roll-then-reduce (ordre des ABILITIES) = FAUX ici : [520,519,532,441,493,589].
=> attaque normale = **reduce-then-roll** (bornes pré-réduites puis tirage), GENUINELY DIFFÉRENT du
dégât d'ABILITY = **roll-then-reduce** (`RandomAmount` brut puis réduction ; cf. test_damage_ability_live).
Ce test verrouille la distinction : un futur « unifie les deux ordres » casserait ICI (sur l'armure).

Cible VANILLE tanky `necroOverlord` (hp~8536, armure~1909, effects=[] : survit, 0 reduction/block).
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))      # import du helper sibling
from _combat_replay import replay_normal_attack     # noqa: E402

ATTACKER = "necroDestroyer"
TARGET = "necroOverlord"


def test_normal_attack_armored_reduce_then_roll(live_session, rpc, build_runner):
    """Attaque normale multi-coups sur cible armurée → per-coup bit-exact (reduce-then-roll)."""
    r = replay_normal_attack(rpc, build_runner, ATTACKER, target=TARGET)
    if not r["ok"]:
        pytest.skip(f"{ATTACKER}->{TARGET}: {r['reason']}")
    if r["did_crit"] or r["did_block"] or r["did_evade"]:
        pytest.skip(f"coup non propre (crit/block/evade live): {r}")
    # l'armure DOIT être > 0 pour que l'ordre soit discriminant (sinon test non concluant).
    assert r["armor"] and r["armor"] > 0, (
        f"cible non armurée (armor={r['armor']}) — test non discriminant ; choisir une cible armurée")
    print(f"\n[NORMAL armored] {ATTACKER}->{TARGET} hits={r['hits']} armor={r['armor']} pierce={r['pierce']} "
          f"live={r['live_ph']} off={r['off_ph']} (reduce-then-roll)")
    # VERROU : le PER-COUP (= l'ordre réduction↔tirage) doit être bit-exact. On asserte le per-coup
    # directement (PAS `exact` qui inclut aussi les PV-après — désalignables par overwatch/dérive ;
    # necroDestroyer porte Overwatch_AutoAttack). Le per-coup identique prouve reduce-then-roll.
    assert r["off_ph"] == r["live_ph"], (
        f"attaque normale NON bit-exact sur cible armurée : off={r['off_ph']} live={r['live_ph']} "
        f"(armor={r['armor']} pierce={r['pierce']}) — l'ordre reduce-then-roll est-il toujours correct ?")
