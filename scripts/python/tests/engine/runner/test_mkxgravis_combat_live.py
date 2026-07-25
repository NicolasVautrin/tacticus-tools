"""#180 -- ATTAQUE NORMALE sur cible MkXGravis (trait 0x3f5) : l'armure est traversee 2x en COMBAT.

Verrou du port #180 : `AttackDamageOperation` doit appliquer `hit_mult=2` (double-perçage/armure) quand
la CIBLE porte MkXGravis, SAUF au crit (i2 « Any incoming Damage has to go through Armour a second time.
Does not apply to Crits »). Mirror natif `IdunBattle.Core.Services.DamagePrediction$$GetBaseDamageWithFixedPiercedArmor` (HasTrait(0x3f5)
&& !isCrit) dans le chemin combat `IdunBattle.Core.Services.DamagePrediction$$CalculateAbilityDamage` -> `CalculateBaseDamageWith
AllModifiers IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers` (decompile-confirme).

Cible = ultraInceptorSgt (traits Hero/Flying/MkXGravis, armure > 0 -> double-armure DISCRIMINANTE).
Attaquant = necroDestroyer (melee multi-coups vanille). Sur un coup PROPRE (non-crit), off per-coup ==
live per-coup : AVANT #180 offline sous-appliquait l'armure (per-coup trop haut) -> mismatch ; APRES ->
bit-exact. ASCII only.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))      # import du helper sibling
from _combat_replay import replay_normal_attack     # noqa: E402

ATTACKER = "necroDestroyer"
TARGET = "ultraInceptorSgt"      # Hero/Flying/MkXGravis


def test_normal_attack_mkxgravis_double_armor(live_session, rpc, build_runner):
    """Attaque normale multi-coups sur cible MkXGravis -> per-coup bit-exact (double-armure non-crit)."""
    r = replay_normal_attack(rpc, build_runner, ATTACKER, target=TARGET)
    if not r["ok"]:
        pytest.skip("%s->%s: %s" % (ATTACKER, TARGET, r["reason"]))
    if r["did_crit"] or r["did_block"] or r["did_evade"]:
        pytest.skip("coup non propre (crit/block/evade live) -- MkXGravis exempte le crit: %s" % r)
    assert r["armor"] and r["armor"] > 0, (
        "cible MkXGravis non armuree (armor=%s) -- double-armure non discriminante" % r["armor"])
    print("\n[MkXGravis combat] %s->%s hits=%s armor=%s pierce=%s live=%s off=%s" %
          (ATTACKER, TARGET, r["hits"], r["armor"], r["pierce"], r["live_ph"], r["off_ph"]))
    assert r["off_ph"] == r["live_ph"], (
        "combat MkXGravis NON bit-exact : off=%s live=%s (armor=%s pierce=%s) -- le hit_mult=2 "
        "(double-armure non-crit) est-il applique cote runner ?" % (r["off_ph"], r["live_ph"], r["armor"], r["pierce"]))
