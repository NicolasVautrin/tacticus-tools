"""SUMMON hors PickNextUnit — confronte au LIVE que les unités invoquées par ability (trait `Summon`)
ne sont JAMAIS activées par la boucle de **playbook** de l'IA (`PickNextUnit`) : elles sont exclues de
`AnAiGroupOperator.GetValidUnits` @1811833e0 (gate `BaseUnitComponent+0x60 >= 1001` = groupe
summons/objects). ⚠ Cela NE veut PAS dire qu'elles n'agissent pas : l'IA les joue quand même via des
**behaviours DSL FORCÉS** `PerformAIAction`/`PerformAIAttack` (`PerformAIActionBehaviour` @180fcba10 =
exécute la décision IA move+attaque du summon), DÉCLENCHÉS hors PickNextUnit :
  - **à l'apparition** (necron ScarabHive : `PerformAIAttack` dans `SpawnUnitOptions`, 1 fois) ;
  - **chaque début de tour** pour d'autres (Tyranid CallRipperSwarms : `*_PendingSummonEffect`
    bondé au summoner, `IsTurnOf(owner)` @180f37e70 -> `PerformAIAction`).
Ce test prouve UNIQUEMENT l'exclusion de PickNextUnit (`aiStepDryRun` = enumerator
`CalculateNextActionForPlayer`, qui ne marche QUE le groupe normal). Le scarab necron, lui, n'agit
de fait qu'à l'apparition (confirmé live : 0 action sur 3 tours, ennemis à PV pleins).

Oracle = IA native (`aiStepDryRun`) ; assertion **GÉNÉRIQUE** (tout trait-`Summon`, pas un id figé),
**indépendante du seed**. Teams **adaptées à l'objectif** (necroSpyder summoner seul vs tanky
non-prioritaires) pour garder ≥1 summon vivant (cf. doctrine « adapter les teams à l'objectif »).

Discriminant offline = trait `Summon` (gameconfig) ; `necroSmn*` l'ont, les unités normales ont `Hero`.
"""
from __future__ import annotations

import pytest

import gameconfig as gc
import engine_validate as EV

SUMMONER = "necroSpyder"          # caste ScarabHive -> 2x necroSmnSwarm (trait Summon)
BUILD = ["--roster", "1", "--p-units", SUMMONER,
         "--a-units", "necroWarden,necroOverlord,necroWarden"]


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _is_summon(visual_id) -> bool:
    """Unité invoquée = trait `Summon` (gameconfig). Discriminant offline du gate GetValidUnits."""
    if not visual_id:
        return False
    uid = gc.resolve_unit_id(visual_id)
    u = gc.unit(uid) if uid else None
    return "Summon" in ((u or {}).get("traits") or [])


def _native_acts(dry_action):
    acts = []
    for m in (dry_action.get("messages") or []):
        c = m.get("cls")
        if c == "MoveUnitMessage":
            acts.append({"kind": "move", "unitId": m["unitId"],
                         "to": {"col": m["to"]["col"], "row": m["to"]["row"]}})
        elif c == "ActiveAbilityMessage":
            acts.append({"kind": "ability", "casterId": m["casterId"],
                         "targetId": m.get("targetId"), "abilityType": m["abilityType"]})
        elif c == "FinishUnitTurnMessage":
            acts.append({"kind": "finish", "unitId": m["unitId"]})
    return acts


def test_summon_not_activated_live(live_session, rpc, build_runner):
    rid = build_runner("777", extra=BUILD)["rid"]

    def alive_summons():
        ob = rpc("observeBattle", {"runnerId": rid}, 40)
        return [u for u in (ob.get("units") or [])
                if not u.get("isDead") and _is_summon(u.get("visualId"))]

    # jouer l'IA native jusqu'a ce qu'au moins 1 unite-trait-Summon soit VIVANTE.
    summons = []
    for _ in range(16):
        summons = alive_summons()
        if summons:
            break
        rpc("aiPlayByUnit", {"runnerId": rid, "maxTurns": 1, "maxActivations": 9999,
                             "maxPump": 3000, "captureEvents": False}, 300)
    if not summons:
        pytest.skip("aucun summon spawne en 16 tours IA")
    sc_player = summons[0].get("playerId")

    # passer la main a l'equipe des summons (endturn ; quirk H19 -> plusieurs essais).
    cp = rpc("decisionView", {"runnerId": rid}, 60).get("currentPlayer")
    for _ in range(6):
        if cp == sc_player:
            break
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 30)
        cp = rpc("decisionView", {"runnerId": rid}, 60).get("currentPlayer")

    # marcher la trajectoire native : confronter chaque activation.
    activated_summon = []                 # (uid, vis) si un summon est active -> REFUTE l'exclusion
    turns_summon_alive_not_activated = 0  # garde anti-vacuite
    cur_alive = cur_activated = False
    for _ in range(60):
        dry = rpc("aiStepDryRun", {"runnerId": rid}, 40)
        if not (_ok(dry) and dry.get("hasNext")):
            ob = rpc("observeBattle", {"runnerId": rid}, 40)
            if cur_alive and not cur_activated:
                turns_summon_alive_not_activated += 1
            cur_alive = cur_activated = False
            if ob.get("stage") in (3, "Finished"):
                break
            cpn = rpc("decisionView", {"runnerId": rid}, 60).get("currentPlayer")
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 30)
            if rpc("decisionView", {"runnerId": rid}, 60).get("currentPlayer") == cpn:
                break                     # flip bloque
            continue
        uid = dry.get("activatedUnitId") or EV.native_first(dry.get("action") or {}).get("unit")
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 180)
        me = next((u for u in (dv.get("units") or []) if u.get("id") == uid), None)
        vis = (me or {}).get("visualId")
        if dv.get("currentPlayer") == sc_player and alive_summons():
            cur_alive = True
        if _is_summon(vis):
            cur_activated = True
            activated_summon.append((uid, vis))
        acts = _native_acts(dry.get("action") or {})
        if acts:
            rpc("applyAction", {"runnerId": rid, "actions": acts}, 40)

    print(f"\n[summon-noact] activated_summon={activated_summon} "
          f"turns_summon_alive_not_activated={turns_summon_alive_not_activated}")

    # 1. AUCUNE unite trait-Summon ne doit jamais etre activee par l'IA (exclusion GetValidUnits).
    assert not activated_summon, \
        f"un summon (trait Summon) a ete active par l'IA -> REFUTE l'exclusion: {activated_summon}"
    # 2. anti-vacuite : il faut avoir observe >=1 fenetre summon-vivant-mais-non-active.
    assert turns_summon_alive_not_activated >= 1, \
        "test vacuous : aucune fenetre observee avec un summon vivant sur son tour (revoir le setup)"
