"""R6-b'' -- le `Maybe` after-hit d'un trigger `On(8)` est roule SUR LES COUPS D'UNE ATTAQUE
D'ABILITY, comme sur ceux d'une attaque NORMALE. Garde LIVE discriminante sur CET etage seul.

RE (decompile = verite, gqfc5mff6c) -- la chaine LUE, appelant par appelant :

  * `IdunBattle.Operations.ADamageOperation$$EvaluateAfterHitTriggers` (seul emetteur de `On(8)`)
    a EXACTEMENT TROIS appelants (xref), tous en **UNCONDITIONAL_CALL** et tous en DERNIERE
    instruction de leur `ExecuteHit` : `IdunBattle.Operations.AttackDamageOperation$$ExecuteHit`
    (famille ATTACK -- LA MEME fonction que l'attaque normale),
    `IdunBattle.Operations.AbilityDamageOperation$$ExecuteHit` (famille ABILITY) et
    `IdunBattle.Operations.MachineDamageOperation$$ExecuteHit`. Le vecteur ABILITY du port
    emprunte les DEUX premieres selon `is_attack_damage_op` -> AUCUN gate de famille.
  * l'index passe au trigger est `currentAttack+0x30` :
    `IdunBattle.Operations.AbilityDamageOperation$$ExecuteHits` le passe en 2e argument de son
    `ExecuteHit` et fait `+0x30 += 1` apres CHAQUE coup (mirror inline
    d'`IdunBattle.Operations.ADamageOperation$$UpdateCurrentAttackAfterHit`), exactement comme
    `IdunBattle.Operations.AttackDamageOperation$$ExecuteHits`.
  * il DEMARRE A 0 par CIBLE : `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage` et
    `$$AttackWithAbilityDamage` finissent tous deux par
    `IdunBattle.Entities.Behaviours.AttackBehaviour$$.ctor(caster, targets, <behaviour>, options)`,
    et `IdunBattle.Entities.Behaviours.AttackBehaviour$$Execute` emet
    `Core.Services.OperationProcessor$$StartAttack` (slot 0x3a) avant CHAQUE cible et
    `$$FinishAttack` (slot 0x3b) apres -> un `IdunBattle.Operations.StartAttackOperation$$Execute`
    (`new OngoingAttack` + Push sur `MatchState+0x60`) par cible.
  * le trigger : `IdunBattleLogic.Entities.Abilities.Triggered.Loki.GetStuckInAbility$$
    CreateTrigger` = `On(8,1) & AmountIsOdd(CurrentHitIndex()) & get_OwnerIsCaster &
    !AmountIsGreater(MinDistance(owner@0x160, target@0x178), Direct(2))` -- **aucun**
    `IsNormalAttack`, **aucun** `CurrentAbilityIs`.

DEUX MONTAGES, DE PART ET D'AUTRE DU SEUL GATE STRUCTUREL (la distance) -- c'est ce qui refute un
« +k tirages » ajuste :

  * `orksKillaKan` (GetStuckIn) caste `DakkaDakkaDakka` (1171, 6 coups Projectile) sur une cible
    ADJACENTE -> gate OUVERT : 3 index IMPAIRS (1, 3, 5) -> jusqu'a 3 tirages et 3 coups bonus ;
  * MEME porteur, MEME ability, cible a **3 hex** (portee max) -> gate FERME : AUCUN tirage. Le
    modele « on roule sans regarder la distance » y echoue, alors qu'il passerait le premier.

PREUVE COTE JEU, independante du port : un coup bonus GetStuckIn porte le tag live
`Additional_Hit_TriggeredAbility_Source: 1234` = `0x4d2`, le litteral EXACT que
`GetStuckInAbility$$CreateBehaviour` passe a `AddBonusHitsToCurrentHitGroup`. Le voir dans le flux
d'une attaque d'ABILITY EST la reponse au critere binaire, sans passer par le port.

TEMOIN : `admecRuststalker` caste `CordClaw` (1122) -- porteur SANS trigger after-hit. Les quatre
modeles DOIVENT coincider et reproduire le live : c'est ce qui prouve qu'on n'a pas ajoute un
tirage PARTOUT (`bonus_hit_chance is None` -> strict no-op).

MONTAGE : regime PERCAGE-DOMINANT (`--armor-target 6000`, fixture `_pierce_floor_regime`), crit et
block neutralises ; details et raison d'etre du montage : `_ability_after_hit_regime`.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))                       # helpers siblings
from _pierce_floor_regime import pierce_dominant_regime             # noqa: E402,F401 (fixture)
from _ability_after_hit_regime import (DAKKA_TARGET, VARIANTS,      # noqa: E402
                                       _want_close, _want_far,
                                       measure_ability_vector)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))                  # scripts/python
from probe_r6bp2_after_hit_maybe_ability import (                    # noqa: E402
    CC_ABILITY, CC_CARRIER, CC_TARGET, _replay_registered)
from probe_r6bp_after_hit_maybe_groups import live_hits_of_attacker   # noqa: E402
from _pierce_floor_regime import drive, _ok                           # noqa: E402

# Seeds MESUREES discriminantes (`probe_r6bp2_after_hit_maybe_ability.py`, 2026-07-28).
CLOSE_SEEDS = ["777", "31337", "12345", "20202"]
FAR_SEEDS = ["777", "31337", "12345"]
TEMOIN_SEEDS = ["777", "12345"]


def _assert_ratchet(off, live, seed, ctx):
    """(1) RATCHET : le port TEL QU'IL EST LIVRE reproduit le live coup par coup ET EN NOMBRE."""
    assert off["shipped"] == live, (
        f"[{ctx} seed {seed}] le port LIVRE ne reproduit pas l'attaque d'ability : "
        f"shipped={off['shipped']} live={live} (sans `Maybe`={off['no_maybe']}) -- "
        "`damage_ops/ability.py` thread-il encore `bonus_hit_chance=_gsi` "
        "(`getstuckin_combat_chance`) a `_run_hits` et a `execute_additional_hits` ?")


def _assert_discriminates(off, live, seed, ctx, losers):
    """(2) DISCRIMINATION : les modeles concurrents DOIVENT echouer, sinon la garde est AVEUGLE."""
    for name in losers:
        assert off[name] != live, (
            f"[{ctx} seed {seed}] le modele concurrent `{name}` reproduit AUSSI le live "
            f"({off[name]}) -- montage NON discriminant, rejouer "
            "`probe_r6bp2_after_hit_maybe_ability.py` pour re-selectionner les seeds.")


@pytest.mark.parametrize("seed", CLOSE_SEEDS)
def test_ability_vector_rolls_after_hit_maybe_live(live_session, rpc, pierce_dominant_regime,
                                                   seed):
    """Cible ADJACENTE -> gate `MinDistance <= 2` OUVERT : le port doit rouler le `Maybe` aux
    index IMPAIRS des coups de l'ABILITY. Deux modeles concurrents doivent tomber :
    `no_maybe` (= le port d'AVANT R6-b'') et `parity` (meme canal, index decale de 1 : MEME
    nombre de tirages, rangs differents -> refute un ajustement « +k tirages »)."""
    live, srcs, off, params = measure_ability_vector(rpc, pierce_dominant_regime, seed,
                                                     _want_close)
    print(f"\n[R6-b'' close] seed={seed} live={live} sources={srcs} params={params}")
    for name, _m in VARIANTS:
        print(f"[R6-b'' close] {name:<9}={off[name]}")
    assert len(live) >= 6, f"attaque a {len(live)} coups : montage non conforme (6 attendus)"
    _assert_ratchet(off, live, seed, "close")
    _assert_discriminates(off, live, seed, "close", ("no_maybe", "parity"))


@pytest.mark.parametrize("seed", FAR_SEEDS)
def test_ability_vector_after_hit_maybe_distance_gate_live(live_session, rpc,
                                                           pierce_dominant_regime, seed):
    """MEME porteur, MEME ability, cible a **3 hex** -> gate `!AmountIsGreater(MinDistance,
    Direct(2))` FERME : AUCUN tirage. Le modele `always` (canal branche sans le gate de distance)
    doit tomber -- il passerait pourtant le montage adjacent. C'est le second cote du gate, celui
    qu'un port « qui roule toujours » raterait en silence."""
    live, srcs, off, params = measure_ability_vector(rpc, pierce_dominant_regime, seed, _want_far)
    print(f"\n[R6-b'' far] seed={seed} live={live} sources={srcs} params={params}")
    for name, _m in VARIANTS:
        print(f"[R6-b'' far] {name:<9}={off[name]}")
    assert not [s for s in srcs if s and s.startswith("trig:")], (
        f"[far seed {seed}] le live porte un coup bonus GetStuckIn a 3 hex : le gate de distance "
        f"du trigger ne serait donc pas celui qui est porte (sources={srcs}).")
    _assert_ratchet(off, live, seed, "far")
    _assert_discriminates(off, live, seed, "far", ("always",))


@pytest.mark.parametrize("seed", TEMOIN_SEEDS)
def test_ability_vector_without_after_hit_trigger_bit_exact_live(live_session, rpc,
                                                                 pierce_dominant_regime, seed):
    """TEMOIN : `admecRuststalker` caste `CordClaw` (1122, 4x DirectDamage melee, ability
    REGISTREE -> rejeu par `ActiveAbilityMessage` COMPLET). Porteur SANS trigger after-hit ->
    `getstuckin_combat_chance` rend None -> `shipped`, `no_maybe` et `parity` DOIVENT coincider ET
    reproduire le live : c'est LUI qui prouve que R6-b'' n'a pas ajoute un tirage partout.

    Le 4e modele, `always`, FORCE le canal (il court-circuite le gate PORTEUR autant que le gate
    de distance) : il doit ECHOUER ici, sinon le montage serait AVEUGLE a un tirage surnumeraire
    -- le temoin est donc lui aussi DISCRIMINANT, pas seulement un cliquet."""
    r = pierce_dominant_regime(seed, CC_CARRIER, CC_TARGET, armor=6000)
    rid, board = r["rid"], r["board"]
    cid, tid, moved = drive(rpc, rid, board, CC_CARRIER, CC_TARGET, ability_id=CC_ABILITY)
    if cid is None:
        pytest.skip(f"{CC_CARRIER} n'a pas atteint {CC_TARGET}")
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
    rng0 = rpc("dumpRng", {"runnerId": rid}, 30)
    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": cid, "targetId": tid,
        "abilityType": CC_ABILITY}, "captureEvents": True}, 120)
    if not _ok(res):
        pytest.skip(f"cast live KO: {str(res)[:120]}")
    live, dirty, srcs = live_hits_of_attacker(res, tid, cid)
    if dirty or not live:
        pytest.skip("coup non propre (crit/block/evade) ou aucun event")
    off = _replay_registered(dv, ob, snap, board, rng0, cid, tid, CC_ABILITY, moved)
    print(f"\n[R6-b'' temoin] seed={seed} live={live} sources={srcs}")
    for name, _m in VARIANTS:
        print(f"[R6-b'' temoin] {name:<9}={off[name]}")
    for name in ("shipped", "no_maybe", "parity"):
        assert off[name] == live, (
            f"[temoin seed {seed}] modele `{name}` = {off[name]} != live {live} -- un porteur "
            "SANS trigger after-hit doit rester BIT-EXACT (aucun tirage ajoute).")
    assert off["always"] != live, (
        f"[temoin seed {seed}] le modele `always` (canal FORCE sans gate porteur) reproduit AUSSI "
        f"le live ({off['always']}) -- ce temoin serait AVEUGLE a un tirage surnumeraire.")
