"""R6-b -- ORDRE tirage/reduction du canal COUPS ADDITIONNELS HETEROGENES (#179/#202-B),
garde LIVE discriminante sur l'ETAGE ORDRE SEUL (la materialisation, elle, est verrouillee par
`test_additional_hits_rounding_live.py`).

RE (decompile = verite, gqfc5mff6c) -- `IdunBattle.Operations.AttackDamageOperation$$ExecuteHit`,
ou retombent les DEUX voies natives de coups additionnels
(`IdunBattle.Operations.AttackDamageOperation$$ExecuteAdditionalHitsWithoutDamageProfileType`
-> `ExecuteHits` ; `IdunBattle.Operations.ExecuteAdditionalHitsWithDamageProfileTypeOperation$$
Execute` -> slot 0x3c `Core.Services.OperationProcessor$$AttackDamage` ->
`IdunBattle.Operations.AttackDamageOperation$$Execute` -> `ExecuteHits`) :

  1. `IdunBattle.Core.HitDamage$$GetDamage(attackData.HitDamage, rng, useAverage)` -- lu verbatim :
         if (min == max) return min ;                 # AUCUN tirage
         if (useAverage)  return (min + max) / 2 ;    # AUCUN tirage
         return rng.Range(min, max + 1) ;             # 1 tirage
  2. le crit (`CritDamageInfo`, dont le champ 0 EST ce degat) ;
  3. slot 4 `IdunBattle.Core.Services.DamagePrediction$$PredictAttack` (le `Nullable<int>` damage
     de la struct d'entree = `CritDamageInfo.Damage`) -> cellule reduite ;
  4. slot 8 `IdunBattle.Core.Services.DamagePrediction$$RandomlyResolveMinMaxDamage` -- lu
     verbatim : `rng.Range(pred.min, pred.max + 1)`, **SANS aucun gate min == max** (contraste
     EXACT avec `HitDamage$$GetDamage`, qui en a un).

Et `IdunBattle.Operations.AdditionalHitsFromEffects$$GetAdditionalHitsData` construit l'AttackData
de chaque groupe par `IdunBattle.Core.HitDamage$$.ctor(min = descripteur.minDmg,
max = Nullable(descripteur.maxDmg))` : pour un groupe PREDEFINED le struct est donc NON degenere.
=> etape 1 tire (LA valeur), etape 4 tire sur une cellule degeneree (tirage GASPILLE) :
**ROLL-THEN-REDUCE, 2 tirages/coup** -- exactement la branche `post_roll` de
`damage_hits.py::_one_hit`, deja mirroree et validee pour le vecteur ability bounds-mode de la
MEME famille ATTACK.

MONTAGE : `orksRuntherd` (passif `SquigHound` -> effet 0x50c, 2 coups PREDEFINED [minDmg,maxDmg]
profil Physical PiercingRatio 1) attaque au CONTACT une cible forcee en regime PERCAGE-DOMINANT
(`--armor-target 6000`, fixture `_pierce_floor_regime`). Ce regime rend l'ORDRE observable sur le
PREMIER coup : la reduction y est une MULTIPLICATION (`d x fix(1/100)`), donc la LARGEUR de la
plage reduite (14 cellules) differe de la largeur BRUTE (1329) -> le modulo du tirage n'est pas
le meme, et toute valeur tiree change. Cible sans `BigTarget`/`Vehicle` (BeastSlayer inerte) et
sans `SwornProtector`.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))      # import du helper sibling
from _pierce_floor_regime import (drive, live_amounts,               # noqa: E402
                                  replay_orders, _ok,
                                  pierce_dominant_regime)            # noqa: F401 (fixture)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))                  # scripts/python
from probe_r6_round_materialize import additional_hits_variant       # noqa: E402
from probe_r6b_additional_hits_order import _cast_cord_claw as cast_cord_claw   # noqa: E402

CARRIER = "orksRuntherd"           # passif SquigHound -> 2 coups Physical (pierce 1)
TARGET = "ultraApothecary"         # ni BigTarget ni Vehicle -> BeastSlayer inerte
# Seeds dont le 1er coup du groupe DISCRIMINE les deux ordres (mesure `probe_r6 --case ah_matrix`,
# 2026-07-28 : 5/5 seeds discriminants, roll-then-reduce 5/5 vs reduce-then-roll 0/5) :
ORDER_SEEDS = ["12345", "314159", "88"]


@pytest.mark.parametrize("seed", ORDER_SEEDS)
def test_additional_hits_roll_then_reduce_live(live_session, rpc, pierce_dominant_regime, seed):
    r = pierce_dominant_regime(seed, CARRIER, TARGET, armor=6000)
    rid, board = r["rid"], r["board"]
    cid, tid, moved = drive(rpc, rid, board, CARRIER, TARGET)
    if cid is None:
        pytest.skip(f"{CARRIER} n'a pas atteint {TARGET} au contact")
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
    rng0 = rpc("dumpRng", {"runnerId": rid}, 30)
    if not (isinstance(rng0, dict) and rng0.get("mt")):
        pytest.skip("dumpRng indispo")
    cu = next((u for u in (dv.get("units") or []) if u.get("id") == cid), {})
    nrm = next((a for a in (cu.get("abilities") or []) if a.get("kind") == "normal"), None)
    if nrm is None:
        pytest.skip("pas d'attaque normale")
    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": cid, "targetId": tid,
        "abilityType": nrm["id"]}, "captureEvents": True}, 120)
    if not _ok(res):
        pytest.skip(f"attaque live KO: {str(res)[:120]}")
    live, dirty = live_amounts(res, tid)
    if dirty:
        pytest.skip("coup non propre (crit/block/evade)")

    off = replay_orders(dv, ob, snap, board, rng0, cid, tid, None, moved, {
        "reduce_then_roll": additional_hits_variant("reduce_then_roll", None),
        "roll_then_reduce": additional_hits_variant("roll_then_reduce", None)})
    rtr, rer, ship, arme = (off["reduce_then_roll"], off["roll_then_reduce"],
                            off["shipped"], off["arme"])
    n_arme = len(arme)
    print(f"\n[R6-b ordre] seed={seed} live={live} arme_offline={arme}")
    print(f"[R6-b ordre] groupe reduce_then_roll={rtr} roll_then_reduce={rer} livre={ship}")
    assert rer and rtr, "aucun coup additionnel rejoue offline (le porteur a-t-il l'effet ?)"
    # Les coups d'ARME precedent le groupe dans le flux d'events, et le grot spawne par
    # `SquigHound` le SUIT -> on ancre sur les coups d'arme (bit-exacts) et on lit le 1er coup
    # du GROUPE.
    assert live[:n_arme] == arme, (
        f"les coups d'ARME divergent (live={live[:n_arme]} off={arme}) : le flux RNG n'est PAS "
        "aligne a l'entree du groupe -- la mesure ne porterait pas sur l'ordre.")
    assert n_arme < len(live), (
        f"aucun event live apres les {n_arme} coups d'arme : le groupe n'a pas ete emis")
    live_g0 = live[n_arme]
    # (1) le regime DOIT discriminer les deux ordres sur CE coup, sinon la garde ne prouve rien.
    assert rtr[0] != rer[0], (
        f"seed {seed} : 1er coup du groupe NON discriminant (les deux ordres donnent {rer[0]}) -- "
        "rejouer `probe_r6_round_materialize.py --case ah_matrix` pour re-selectionner les seeds.")
    # (2) le natif tire le BRUT PUIS reduit.
    assert rer[0] == live_g0, (
        f"roll-then-reduce != live : off={rer[0]} live={live_g0} (groupe offline {rer}, "
        f"live {live[n_arme:]})")
    # (3) DISCRIMINATION : l'ordre inverse (celui du port d'avant R6-b) doit ECHOUER.
    assert rtr[0] != live_g0, (
        f"reduce-then-roll reproduit aussi le live ({rtr[0]}) : la garde est AVEUGLE.")
    # (4) RATCHET : le port TEL QU'IL EST LIVRE doit resoudre dans l'ordre natif.
    assert ship[0] == live_g0, (
        f"le port LIVRE ne resout pas dans l'ordre natif : shipped={ship[0]} live={live_g0} "
        f"(roll_then_reduce={rer[0]}, reduce_then_roll={rtr[0]}) -- `execute_additional_hits` "
        "d'`operations/additional_hits.py` reduit-il encore les BORNES avant de tirer ?")


# --------------------------------------------------------------------------------------------
# 2e CAS DISCRIMINANT, sur l'AUTRE AXE (CONSOMMATION) et un AUTRE PORTEUR.
#
# `admecRuststalker` caste `CordClaw` (1122), dont le 2e volet est `AddEffect(1250, target=Self)` :
# ses attaques SUIVANTES portent 2 coups PREDEFINED profil `DirectDamage` PiercingRatio **100**.
# A p100, `idun.…StaticBattleRules.Damage$$GetDamageWithPiercing` rend `max(0, d - armure,
# d x 1.0) = d` : la reduction est l'IDENTITE, donc les DEUX ordres donnent le MEME 1er coup --
# ce montage est AVEUGLE a l'axe « largeur du modulo » teste ci-dessus. Ce qui discrimine ici est
# le SEUL resolve slot-8 GASPILLE (`RandomlyResolveMinMaxDamage` sans gate min == max), qui
# decale le flux RNG d'un tirage : c'est le DEUXIEME coup qui tranche.
#
# Ce porteur n'a NI `GetStuckIn` (le `Maybe` de `EvaluateAfterHitTriggers` qui pollue le 2e coup
# d'`orksRuntherd`, residu R6-b') NI extra-degat conditionnel -> montage propre de bout en bout.
# --------------------------------------------------------------------------------------------
CC_CARRIER = "admecRuststalker"
CC_TARGET = "necroWarden"
CC_A_UNITS = "necroWarden,necroWarden"   # 2 cibles : le cast peut en tuer une, l'attaque vise l'autre
CC_EFFECT = 1250                         # CordClaw_AdditionHits, pose sur le CASTER
CC_SEEDS = ["777", "12345"]


@pytest.mark.parametrize("seed", CC_SEEDS)
def test_additional_hits_wasted_resolve_live(live_session, rpc, pierce_dominant_regime, seed):
    r = pierce_dominant_regime(seed, CC_CARRIER, CC_A_UNITS, armor=6000)
    rid, board = r["rid"], r["board"]
    if not cast_cord_claw(rpc, rid, board):
        pytest.skip(f"{CC_CARRIER} n'a pas pu caster CordClaw")
    cid, tid, moved = drive(rpc, rid, board, CC_CARRIER, CC_TARGET)
    if cid is None:
        pytest.skip(f"{CC_CARRIER} n'a pas atteint {CC_TARGET} au contact apres le cast")
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
    cu = next((u for u in (dv.get("units") or []) if u.get("id") == cid), {})
    if CC_EFFECT not in {e.get("effectType") for e in (cu.get("effects") or [])}:
        pytest.skip(f"effet {CC_EFFECT} absent du caster au tour d'attaque")
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
    rng0 = rpc("dumpRng", {"runnerId": rid}, 30)
    if not (isinstance(rng0, dict) and rng0.get("mt")):
        pytest.skip("dumpRng indispo")
    nrm = next((a for a in (cu.get("abilities") or []) if a.get("kind") == "normal"), None)
    if nrm is None:
        pytest.skip("pas d'attaque normale")
    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": cid, "targetId": tid,
        "abilityType": nrm["id"]}, "captureEvents": True}, 120)
    if not _ok(res):
        pytest.skip(f"attaque live KO: {str(res)[:120]}")
    live, dirty = live_amounts(res, tid)
    if dirty:
        pytest.skip("coup non propre (crit/block/evade)")

    off = replay_orders(dv, ob, snap, board, rng0, cid, tid, None, moved, {
        "reduce_then_roll": additional_hits_variant("reduce_then_roll", None),
        "roll_then_reduce": additional_hits_variant("roll_then_reduce", None),
        # MEME ordre, mais SANS le resolve slot-8 : isole la CONSOMMATION de l'ordre lui-meme.
        "roll_then_reduce_no_resolve": additional_hits_variant("roll_then_reduce", None,
                                                               is_attack_op=False)})
    rtr, rer = off["reduce_then_roll"], off["roll_then_reduce"]
    nores, ship, arme = off["roll_then_reduce_no_resolve"], off["shipped"], off["arme"]
    n_arme = len(arme)
    print(f"\n[R6-b resolve] seed={seed} live={live} arme_offline={arme}")
    print(f"[R6-b resolve] groupe rtr={rtr} rer={rer} sans_resolve={nores} livre={ship}")
    assert len(rer) >= 2, f"le groupe CordClaw doit faire 2 coups, offline={rer}"
    assert live[:n_arme] == arme, (
        f"les coups d'ARME divergent (live={live[:n_arme]} off={arme}) : flux RNG desaligne")
    assert len(live) >= n_arme + 2, (
        f"moins de 2 events live apres les {n_arme} coups d'arme : groupe non emis ({live})")
    g_live = live[n_arme:n_arme + 2]
    # (1) axe LARGEUR aveugle ici (pierce 100 = reduction identite) -> 1er coup identique partout.
    #     C'est ce qui fait de ce montage un cas INDEPENDANT du premier.
    assert rtr[0] == rer[0] == g_live[0], (
        f"1er coup : rtr={rtr[0]} rer={rer[0]} live={g_live[0]} -- le profil DirectDamage p100 "
        "devrait rendre les deux ordres identiques sur ce coup")
    # (2) le 2e coup tranche, et c'est le RESOLVE GASPILLE qui le fait.
    assert rer[1] == g_live[1], (
        f"2e coup : roll-then-reduce AVEC resolve={rer[1]} != live={g_live[1]}")
    assert nores[1] != g_live[1], (
        f"2e coup : la variante SANS resolve reproduit aussi le live ({nores[1]}) -- la garde "
        "ne prouve alors rien sur la consommation")
    assert rtr[1] != g_live[1], (
        f"2e coup : reduce-then-roll reproduit aussi le live ({rtr[1]}) : garde AVEUGLE")
    # (3) RATCHET sur le port LIVRE, les DEUX coups.
    assert ship[:2] == g_live, (
        f"le port LIVRE ne reproduit pas le groupe : shipped={ship[:2]} live={g_live} "
        f"(rer={rer[:2]}, rtr={rtr[:2]}, sans_resolve={nores[:2]})")
