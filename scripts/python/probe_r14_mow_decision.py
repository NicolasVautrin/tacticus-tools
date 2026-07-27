#!/usr/bin/env python
"""R14 -- face DECISION des MACHINES OF WAR : le port PROPOSE-t-il, et coincide-t-il avec le natif ?

Chemin natif mirrore (RE gqfc5mff6c) :

    IdunBattle.AI.OperationalDeciders.DefaultGroupOperator$$CalculateNextActionForPlayer
        entities = GetEntitiesFromIds(playerComponent.CurrentlyOwnedUnitIds)
        if (playerComponent+0x78 != 0) entities.Add(state.GetEntity(playerComponent+0x78))   # la MoW
        -> CalculateNextActionForUnitGroup(entities)
    IdunBattle.Core.Services.AiQuery$$GetUnitTacticForUnit
        IsSteppable -> SkipTurn ; IsUseless -> SkipTurn ; IsMachine -> DefaultMachineTactic ; ...
    IdunBattle.AI.Tactics.DefaultMachineTactic.<CalculateNextActionForUnit>d__5$$MoveNext
        pour chaque generateur de GetDefaultActiveAbilityActionGenerators (PAS de Movement) :
            gen.GenerateActions(machine, UnitPosition.NullPosition(), new OrderedSet())

ORACLE = `aiStepDryRun` (= `CalculateNextActionForPlayer`, LECTURE SEULE, `mutated:false`) apres
`finish` de tous les allies reguliers, pour que la seule proposition restante soit celle de la MoW.
`aiDryRunAllUnits` n'itere QUE `EntityType.Unit` : il ne verra jamais une Machine (limite d'outil,
pas contre-exemple).

Usage (depuis scripts/python, session Frida warmee) :
    python probe_r14_mow_decision.py --runner <id>
    python probe_r14_mow_decision.py --build --mow adeptExorcist --board C1_02 [--ammo 5]
    python probe_r14_mow_decision.py --sweep [--ammo 5]      # les 8 MoW du pool, 1 runner a la fois

ASCII only (cp1252).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rl_collect_batch import _resolve_session, _rpc  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def _r(sid: int, method: str, body: dict, t: float = 90) -> dict:
    return (_rpc(sid, method, [body], timeout=t).get("result") or {})


def _ammo_bc(ammo: int) -> Path:
    """Seed BC + munitions de MoW. Le seed part a `MachineOfWarAmmo = 0` -> toute ability a
    `munitionsCost` est refusee par `ActiveAbility$$get_CanCurrentlyBeUsed` (4e terme)."""
    src = ROOT / "data" / "seed-bc.json"
    bc = json.loads(src.read_text(encoding="utf-8"))
    for _pid, p in ((bc.get("Player") or {}).get("Players") or {}).items():
        if isinstance(p, dict) and p.get("PlayerType") != 2:
            p["MachineOfWarAmmo"] = ammo
    out = ROOT / "logs" / "runners" / f"bc-r14-{uuid.uuid4().hex[:8]}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(bc), encoding="utf-8")
    return out


def _build(mow: str, board: str, seed: str, ammo: int, p_units: str, a_units: str) -> int:
    state = ROOT / "logs" / "runners" / f"r14-{uuid.uuid4().hex[:8]}.json"
    state.parent.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", seed, "--board", board,
           "--p-mow", mow, "--p-units", p_units, "--a-units", a_units,
           "--state-file", str(state)]
    if ammo:
        cmd += ["--seed-bc", str(_ammo_bc(ammo))]
    subprocess.run(cmd, cwd=str(Path(__file__).resolve().parent), check=True)
    return int(json.loads(state.read_text(encoding="utf-8"))["runnerId"])


def _native_chunk(action: dict) -> dict:
    out = {"move": None, "ability": None, "finish": False, "unit": None}
    for m in (action or {}).get("messages") or []:
        cls = m.get("cls")
        if cls == "MoveUnitMessage" and out["move"] is None:
            out["move"] = (m.get("to") or {}).get("col"), (m.get("to") or {}).get("row")
            out["unit"] = out["unit"] if out["unit"] is not None else m.get("unitId")
        elif cls == "ActiveAbilityMessage" and out["ability"] is None:
            out["ability"] = {"ability": m.get("abilityType"), "target": m.get("targetId")}
            out["unit"] = out["unit"] if out["unit"] is not None else m.get("casterId")
        elif cls == "FinishUnitTurnMessage":
            out["finish"] = True
            out["unit"] = out["unit"] if out["unit"] is not None else m.get("unitId")
    return out


MOW_POOL = ["adeptExorcist", "astraOrdnanceBattery", "blackForgefiend", "deathCrawler",
            "orksRukkatrukk", "tauBroadside", "tyranBiovore", "ultraDreadnought"]


def _one(sid: int, rid: int, endturns: int) -> dict:
    """Un pas de mesure sur un runner deja bati : etat des abilities de la MoW, decision NATIVE
    (`aiStepDryRun` apres `finish` des allies) et decision du PORT (`engine_decide`)."""
    for _ in range(endturns):
        _r(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    dv = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    mows = dv.get("mows") or []
    if not mows:
        return {"error": "aucune MoW dans decisionView.mows"}
    mow = mows[0]
    cid, myteam = mow["casterId"], mow.get("team")
    abst = [(a.get("id"), a.get("usable"), a.get("cooldown"), a.get("ammoCost"), a.get("hasAmmo"))
            for a in (mow.get("abilities") or [])]
    for u in [x["id"] for x in (dv.get("units") or [])
              if x.get("alive") and x.get("team") == myteam]:
        _r(sid, "applyAction", {"runnerId": rid, "action": {"kind": "finish", "unitId": u}}, 60)
    dv = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    dry = _r(sid, "aiStepDryRun", {"runnerId": rid}, 180)
    nat = _native_chunk(dry.get("action") or {})
    from engine import weights
    from engine_validate import engine_decide
    eng = engine_decide(sid, rid, dv, {}, cid, weights.load(), None)
    return {"caster": cid, "abilities": abst, "nat": nat, "eng": eng,
            "hasAction": mow.get("hasAction")}


def _sweep(sid: int, a) -> int:
    """Les 8 MoW du pool, UN runner a la fois (dispose entre chaque). Verifie les invariants du
    CHEMIN (routage + absence de mouvement + refus des abilities non `CanCurrentlyBeUsed`), pas la
    coincidence par-ability (elle exige que le playbook de l'ability soit porte)."""
    bad = 0
    for mow in MOW_POOL:
        rid = None
        try:
            rid = _build(mow, a.board, a.seed, a.ammo, a.p_units, a.a_units)
            res = _one(sid, rid, a.endturns)
            if res.get("error"):
                print(f"[sweep] {mow:22} ERREUR {res['error']}")
                bad += 1
                continue
            nat, eng = res["nat"], res["eng"]
            nat_ab = (nat["ability"] or {}).get("ability")
            eng_ab = eng.get("ability")
            legal = {x[0] for x in res["abilities"]
                     if x[1] is not False and not (x[2] is not None and int(x[2]) >= 1)
                     and not (x[3] is not None and x[4] is False)}
            ok_no_move = eng.get("kind") != "move" and eng.get("to") is None
            ok_legal = eng_ab is None or eng_ab in legal
            ok_caster = nat["unit"] == res["caster"] or nat["unit"] is None
            flag = "OK " if (ok_no_move and ok_legal and ok_caster) else "BAD"
            if flag == "BAD":
                bad += 1
            print(f"[sweep] {mow:22} {flag} caster={res['caster']} legales={sorted(legal)} "
                  f"natif={nat_ab} port={eng.get('kind')}/{eng_ab} to={eng.get('to')} "
                  f"match={nat_ab == eng_ab}")
        except Exception as exc:                                   # noqa: BLE001
            print(f"[sweep] {mow:22} EXCEPTION {exc}")
            bad += 1
        finally:
            if rid is not None:
                _r(sid, "disposeRunner", {"runnerId": rid}, 60)
    print(f"[sweep] invariants du chemin VIOLES sur {bad}/{len(MOW_POOL)} MoW")
    return 1 if bad else 0


def main(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runner", type=int, default=None)
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--sweep", action="store_true")
    ap.add_argument("--mow", default="adeptExorcist")
    ap.add_argument("--board", default="C1_02")
    ap.add_argument("--seed", default="4242")
    ap.add_argument("--ammo", type=int, default=5)
    ap.add_argument("--p-units", default="adeptCanoness,adeptRetributor")
    ap.add_argument("--a-units", default="ultraTitus,worldTerminator")
    ap.add_argument("--endturns", type=int, default=2,
                    help="endturn x N avant mesure (les MoW ont initialCooldownTurns=1)")
    a = ap.parse_args(argv)

    sid = _resolve_session()
    if a.sweep:
        return _sweep(sid, a)
    rid = _build(a.mow, a.board, a.seed, a.ammo, a.p_units, a.a_units) if a.build else a.runner
    if rid is None:
        print("[r14] --runner <id> ou --build requis", file=sys.stderr)
        return 2
    print(f"[r14] session={sid} runner={rid}")

    for _ in range(a.endturns):
        _r(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)

    dv = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    mows = dv.get("mows") or []
    if not mows:
        print("[r14] aucune MoW dans decisionView.mows", file=sys.stderr)
        return 2
    for m in mows:
        st = [(x.get("id"), x.get("usable"), x.get("cooldown"), x.get("ammoCost"), x.get("hasAmmo"))
              for x in (m.get("abilities") or [])]
        print(f"[r14] mow caster={m.get('casterId')} vis={m.get('visualId')} "
              f"team={m.get('team')} hasAction={m.get('hasAction')} "
              f"abilities(id,usable,cd,ammoCost,hasAmmo)={st}")

    mow = mows[0]
    cid = mow["casterId"]
    myteam = mow.get("team")
    allies = [u["id"] for u in (dv.get("units") or [])
              if u.get("alive") and u.get("team") == myteam]
    for u in allies:                       # ne laisser QUE la MoW a activer
        _r(sid, "applyAction", {"runnerId": rid, "action": {"kind": "finish", "unitId": u}}, 60)

    dv = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    dry = _r(sid, "aiStepDryRun", {"runnerId": rid}, 180)
    nat = _native_chunk(dry.get("action") or {})
    print(f"[r14] NATIF ok={dry.get('ok')} hasNext={dry.get('hasNext')} "
          f"mutated={dry.get('mutated')} unit={nat['unit']} move={nat['move']} "
          f"ability={nat['ability']} finish={nat['finish']}")

    from engine import weights
    from engine_validate import engine_decide
    eng = engine_decide(sid, rid, dv, {}, cid, weights.load(), None)
    print(f"[r14] PORT  caster={cid} -> {eng}")

    ok_caster = (nat["unit"] == cid)
    same = (nat["ability"] is not None and eng.get("kind") == "ability"
            and eng.get("ability") == nat["ability"]["ability"]
            and eng.get("target") == nat["ability"]["target"])
    print(f"[r14] VERDICT caster_is_mow={ok_caster} proposable={eng.get('kind') == 'ability'} "
          f"match={same}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
