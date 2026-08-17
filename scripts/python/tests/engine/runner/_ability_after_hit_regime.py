"""FIXTURE NOMMEE ET REUTILISABLE — le montage « ATTAQUE D'ABILITY d'un porteur de trigger
after-hit `On(8)` », seul montage qui rende le `Maybe` du VECTEUR ABILITY observable.

POURQUOI cette fixture existe (et pourquoi elle doit resservir) : le `Maybe` after-hit
(`IdunBattleLogic.Entities.Abilities.Triggered.Loki.GetStuckInAbility$$CreateBehaviour`) n'est
observable que si TROIS conditions tiennent EN MEME TEMPS, et aucune n'est facile a reunir :

  (a) le CASTER porte le trigger (`GetStuckIn`) -- il n'y a que **cinq** heros porteurs
      (`orksBigMek`, `orksKillaKan`, `orksNob`, `orksRuntherd`, `orksWarboss`) ;
  (b) il dispose d'une ability qui INFLIGE DES DEGATS sur >= 2 coups : le trigger exige un index
      de coup IMPAIR (`AmountIsOdd(CurrentHitIndex())`), donc une ability mono-coup ne le
      declenche JAMAIS. Un seul porteur remplit (a)+(b) : `orksKillaKan` / `DakkaDakkaDakka`
      (1171, **6 coups** Projectile, famille ATTACK) ;
  (c) `MinDistance(caster, target) <= 2` -- gate structurel du trigger. L'ability porte a 3 hex :
      la distance est donc un LEVIER, pas une contrainte (cf. `_want_close` / `_want_far` du
      probe, qui fabriquent les deux cotes du gate).

S'y ajoute le regime PERCAGE-DOMINANT de `_pierce_floor_regime` (`--armor-target 6000`, crit et
block neutralises) : il rabat le degat par coup autour de ~330, ce qui laisse la cible VIVANTE au
bout de 6 a 9 coups -- indispensable, sinon la branche `ChainLeftOverHitsAttackDamage` de
l'ability (leftover hits redistribues) s'allume et la mesure ne porte plus sur le seul vecteur.

L'ability 1171 n'etant PAS au registre `ABILITY_CLASSES`, le rejeu offline appelle
`AttackDamageOperation.execute_ability_attack` DIRECTEMENT avec les parametres que sa feuille
`IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage` lui passerait (lus au decompile :
`AActiveAbility$$MinMaxDamage`, `DakkaDakkaDakkaAbility$$GetNumHits`,
`AbilityConfiguration$$GetDamageProfile`). C'est la DECOMPOSITION PAR ETAGE : on mesure l'etage
porte (le vecteur de degat d'ability), pas l'arbre DSL de l'ability -- et le RATCHET (les coups
doivent reproduire le live) refuse tout parametre faux.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))                       # helpers siblings
from _pierce_floor_regime import _ok                                 # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))                  # scripts/python
from probe_r6bp2_after_hit_maybe_ability import (                    # noqa: E402
    DAKKA_ABILITY, DAKKA_CARRIER, DAKKA_TARGET, VARIANTS,
    _drive_ability, _replay_dakka, _want_close, _want_far)
from probe_r6bp_after_hit_maybe_groups import live_hits_of_attacker   # noqa: E402

__all__ = ["DAKKA_ABILITY", "DAKKA_CARRIER", "DAKKA_TARGET", "VARIANTS",
           "_want_close", "_want_far", "measure_ability_vector"]


def measure_ability_vector(rpc, regime, seed, want, target=DAKKA_TARGET, armor=6000):
    """Monte la bataille, AMENE `orksKillaKan` a la distance voulue de `target` (jamais « bloque
    par la geometrie de spawn » : `_drive_ability` DEPLACE jusqu'a satisfaire `want` ET la
    legalite de cast), joue `DakkaDakkaDakka` LIVE, puis rejoue le MEME cast offline sous les
    quatre modeles de `VARIANTS`.

    `want(hexdist, cheby)` = `_want_close` (adjacent -> gate du trigger OUVERT) ou `_want_far`
    (3 hex -> gate FERME). Rend `(live, sources, off, params)` ou `pytest.skip`."""
    r = regime(seed, DAKKA_CARRIER, target, armor=armor)
    rid, board = r["rid"], r["board"]
    cid, tid, moved = _drive_ability(rpc, rid, board, DAKKA_CARRIER, target, DAKKA_ABILITY, want)
    if cid is None:
        pytest.skip(f"{DAKKA_CARRIER} n'a pas atteint la position voulue face a {target}")
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
    rng0 = rpc("dumpRng", {"runnerId": rid}, 30)
    if not (isinstance(rng0, dict) and rng0.get("mt")):
        pytest.skip("dumpRng indispo")
    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": cid, "targetId": tid,
        "abilityType": DAKKA_ABILITY}, "captureEvents": True}, 120)
    if not _ok(res):
        pytest.skip(f"cast live KO: {str(res)[:120]}")
    # FILTRE `Attacker_Id` + `Target_Id` : la comparaison devient EXACTE EN NOMBRE, donc un
    # `Maybe` qui REUSSIT (coup bonus DEFERE en plus) est observable comme tel.
    live, dirty, srcs = live_hits_of_attacker(res, tid, cid)
    if dirty:
        pytest.skip("coup non propre (crit/block/evade)")
    if not live:
        pytest.skip("aucun event de degat live (cast sans effet ?)")
    off, params = _replay_dakka(dv, ob, snap, board, rng0, cid, tid, moved)
    if off is None:
        pytest.skip("parametres offline de l'ability indisponibles")
    return live, srcs, off, params
