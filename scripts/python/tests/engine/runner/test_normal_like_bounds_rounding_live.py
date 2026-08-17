"""R6 -- MATERIALISATION des bornes REDUITES du vecteur `execute_normal_like` (garde LIVE
discriminante). Jumeau de `test_normal_attack_bounds_rounding_live` (#131), sur l'AUTRE facade
offline de la MEME operation native.

RE (decompile = verite) : `execute_normal_like` porte le mode `amount` de la feuille
`IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage` ET le `UseNormalAttackIfAble`
on-appearance d'un summon -- famille ATTACK dans les deux cas, donc
`IdunBattle.Operations.AttackDamageOperation$$Execute` -> `ExecuteHits` -> `ExecuteHit`. Ce
per-coup resout sa cellule par le slot 4 `IdunBattle.Core.Services.DamagePrediction$$PredictAttack`
(cache -> `PredictAttackRaw`) puis le slot 8
`IdunBattle.Core.Services.DamagePrediction$$RandomlyResolveMinMaxDamage` -- MEME fonction que
l'attaque NORMALE, dont le dernier etage
(`IdunBattle.Core.Services.DamageCalculations$$CalculateBaseDamageWithModifiers`, slot 0x10) fait
`Fix64.Round(Mul(v, multiplier), AwayFromZero)`. Un port qui TRONQUE ici est donc un FORK de port
(une operation native, deux facades offline dont une fausse).

MONTAGE : `ultraInceptorSgt` caste `DeathFromAbove` (1003) -> chaque `ultraSmnInceptor` execute son
on-appearance `UseNormalAttackIfAble` = 6 coups Bolter (PiercingRatio 20) via `execute_normal_like`.
La cible est forcee en regime PERCAGE-DOMINANT par `--armor-target` (cf. `_pierce_floor_regime`).
Bornes brutes [798,1196] -> cellules [159,239] (troncature) vs [160,239] (arrondi) : la LARGEUR du
modulo change, donc CHAQUE valeur tiree change.

CE QUE LA GARDE VERROUILLE :
  1. le regime EST discriminant (les deux materialisations donnent des cellules DIFFERENTES) ;
  2. ARRONDI == live PER-COUP ;
  3. TRONCATURE != live -> une regression vers `op_Explicit` casse ici ;
  4. TEMOIN (`--armor-target` BAS, branche ARMURE) : les deux modeles COINCIDENT et valent le
     live -> refute « l'arrondi collait par chance ».
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))      # import du helper sibling
from _pierce_floor_regime import (drive, live_amounts,               # noqa: E402
                                  replay_materializations, _ok,
                                  pierce_dominant_regime)            # noqa: F401 (fixture)

CASTER = "ultraInceptorSgt"        # DeathFromAbove 1003 -> summon `ultraSmnInceptor`
DEATH_FROM_ABOVE = 1003
TARGET = "necroWarden"             # aucun effet de defense %-gate, pas de SwornProtector
MODULE = "engine.runner.operations.damage_ops.normal_like"


def _run(rpc, regime, seed, armor):
    r = regime(seed, CASTER, TARGET, armor=armor)
    rid, board = r["rid"], r["board"]
    cid, tid, moved = drive(rpc, rid, board, CASTER, TARGET, ability_id=DEATH_FROM_ABOVE)
    if cid is None:
        pytest.skip(f"{CASTER} n'a pas amene {TARGET} a portee de cast")
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
    rng0 = rpc("dumpRng", {"runnerId": rid}, 30)
    if not (isinstance(rng0, dict) and rng0.get("mt")):
        pytest.skip("dumpRng indispo")
    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": cid, "targetId": tid,
        "abilityType": DEATH_FROM_ABOVE}, "captureEvents": True}, 120)
    if not _ok(res):
        pytest.skip(f"cast live KO: {str(res)[:120]}")
    live, dirty = live_amounts(res, tid)
    if not live:
        pytest.skip("aucun degat live attribue (aucun Inceptor n'a attaque)")
    if dirty:
        pytest.skip("coup non propre (crit/block/evade)")
    off = replay_materializations(dv, ob, snap, board, rng0, cid, tid,
                                  DEATH_FROM_ABOVE, moved, MODULE, recorder="normal_like")
    return live, off


def test_normal_like_reduced_bounds_are_rounded_live(live_session, rpc, pierce_dominant_regime):
    """Regime DISCRIMINANT (armure haute -> branche PERCAGE) : le natif ARRONDIT."""
    live, off = _run(rpc, pierce_dominant_regime, "777", armor=6000)
    print(f"\n[R6 normal_like] live      ={live}")
    print(f"[R6 normal_like] troncature={off['floor']}")
    print(f"[R6 normal_like] arrondi   ={off['round']}")
    print(f"[R6 normal_like] port livre={off['shipped']}")
    assert off["round"], "aucun coup `execute_normal_like` rejoue offline (montage casse)"
    # (1) le regime DOIT etre discriminant, sinon la garde ne prouve rien.
    assert off["floor"] != off["round"], (
        f"regime NON discriminant (les deux materialisations rendent {off['round']}) : la branche "
        "PERCAGE du plancher ne mord pas, ou une %-list a deja arrondi. Relire "
        "`_pierce_floor_regime` (conditions a/b/c) et remonter --armor-target.")
    # (2) le natif ARRONDIT (Fix64$$Round AwayFromZero) : bit-exact PER-COUP.
    assert off["round"] == live, (
        f"bornes ARRONDIES != live : off={off['round']} live={live} -- la materialisation des "
        "cellules de `PredictAttackRaw` a-t-elle change, ou un etage AMONT a-t-il regresse ?")
    # (3) DISCRIMINATION : la troncature (le port d'avant R6) doit ECHOUER ici.
    assert off["floor"] != live, (
        f"la TRONCATURE reproduit aussi le live ({off['floor']}) : la garde est AVEUGLE.")
    # (4) RATCHET : le port LIVRE doit materialiser comme le natif (ROUGE avant R6).
    assert off["shipped"] == live, (
        f"le port LIVRE ne reproduit pas le live : shipped={off['shipped']} live={live} "
        f"(arrondi={off['round']}, troncature={off['floor']}) -- `execute_normal_like` "
        "TRONQUE-t-il encore ses bornes reduites (`round_materialize` non pose) ?")


def test_normal_like_bounds_control_armor_branch_live(live_session, rpc, pierce_dominant_regime):
    """TEMOIN : armure BASSE -> la branche `d - armure` du plancher l'emporte -> la valeur est
    ENTIERE -> les deux materialisations COINCIDENT et valent le live. Refute « l'arrondi collait
    par chance » (un +1 systematique aurait fait diverger CE cas aussi)."""
    live, off = _run(rpc, pierce_dominant_regime, "777", armor=300)
    print(f"\n[R6 normal_like temoin] live={live} floor={off['floor']} round={off['round']} "
          f"livre={off['shipped']}")
    assert off["floor"] == off["round"], (
        f"le regime TEMOIN est discriminant ({off['floor']} vs {off['round']}) : l'armure basse "
        "n'a pas fait gagner la branche `d - armure` -- montage a revoir.")
    assert off["round"] == live, (
        f"regime NON discriminant mais offline != live (off={off['round']} live={live}) : la "
        "divergence n'est PAS la materialisation, c'est un etage AMONT.")
    assert off["shipped"] == live, (
        f"le port LIVRE diverge du live HORS regime discriminant (shipped={off['shipped']} "
        f"live={live}) : la cause n'est pas la materialisation.")
