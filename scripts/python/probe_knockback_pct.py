#!/usr/bin/env python
"""#61 : ISOLER le degat de KNOCKBACK (push bloque) et trancher pct 10 vs 20.

Contexte : `IdunBattle.Core.Services.DamageCalculations$$CalculateKnockbackDamage` = int(Fix64.Ceiling(maxHealth x
pct/100)), pct = config @+0x24 = `BattleConfiguration.Damage.KnockbackPercentage`. Le seed BC courant
(build gqfc5mff6c) porte KnockbackPercentage=20, mais #47 a mesure 10% via hpDelta COMBINE (attaque +
knockback). Ce probe LIT l'event knockback ISOLE (StreamDispatcher, tags) pour lever le confond.

Cible = necroWarden (Makhotep) = HERO Necron MONO-modele -> maxHealth total == par-modele (aucun /2
possible). hp-target IMPAIR (30001) : discrimine 3001 (=Ceiling(30001x0.10)) vs 6001 (=Ceiling(30001x0.20)).

Scenario : caster ultraEliminatorSgt + cible adjacente. mode=blocked (defaut) : cible sur un BORD tel
que la tuile "derriere" (oppose caster) est HORS-BOARD -> push bloque -> knockback. mode=free : tuile
derriere LIBRE -> push reussit -> CONTREFACTUEL : aucun degat de mur (0 event knockback). Dump de TOUS
les events (step, entity, tags, source) + changes.
ASCII only. Usage : python probe_knockback_pct.py [hp_target] [blocked|free]
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stream_events as SE  # noqa: E402
from rl_collect_batch import _resolve_session, _rpc  # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
STATE = ROOT / "logs" / "runners" / "p61-kbpct-a1f7b5.json"
CASTER_VIS = "ultraEliminatorSgt"
TARGET_VIS = "necroWarden"
ABILITY = 1004


def _r(sid, m, b, t=90):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def _find(dec, vis):
    return next((u for u in (dec.get("units") or [])
                 if u.get("visualId") == vis and u.get("alive")), None)


def _pos(u):
    p = (u or {}).get("pos")
    return (p.get("col"), p.get("row")) if isinstance(p, dict) else None


def main():
    from engine.runner.operations.displace import _dir_index, _step
    from engine.entities.pathfinding.board import Board

    hp_target = int(sys.argv[1]) if len(sys.argv) > 1 else 30001
    mode = sys.argv[2] if len(sys.argv) > 2 else "blocked"
    want_free = (mode == "free")
    sid = _resolve_session()
    STATE.parent.mkdir(parents=True, exist_ok=True)
    build = ["--roster", "1", "--p-units", CASTER_VIS,
             "--a-units", f"{TARGET_VIS},necroDestroyer", "--hp-target", str(hp_target)]
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", "909",
         "--state-file", str(STATE), "--board", "MC1_67", *build],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not STATE.exists():
        print("BUILD KO:", (proc.stderr or proc.stdout or "")[-400:])
        return 1
    rid = json.loads(STATE.read_text())["runnerId"]
    print("runnerId", rid, "hp_target", hp_target)
    try:
        bg = _r(sid, "boardGraph", {"runnerId": rid}, 60)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            print("SKIP: boardGraph indispo")
            return 0
        board = Board(bg["tiles"], adjacency="native_sym")
        dec0 = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        ob0 = _r(sid, "observeBattle", {"runnerId": rid}, 60)
        caster = _find(dec0, CASTER_VIS)
        target = _find(dec0, TARGET_VIS)
        if caster is None or target is None:
            print("SKIP: caster/cible absents")
            return 0
        cid, eid = caster["id"], target["id"]
        third = next((u for u in (dec0.get("units") or [])
                      if u.get("alive") and u.get("id") not in (cid, eid)), None)
        tid3 = (third or {}).get("id")

        # maxHealth reel de la cible (observeBattle hpMax)
        obu = {u.get("squadId"): u for u in (ob0.get("units") or [])}
        tmax = (obu.get(eid) or {}).get("hpMax")
        print("target maxHealth (observeBattle hpMax) =", tmax)

        # --- chercher (C caster, T cible) : mode blocked = derriere HORS-BOARD ; free = derriere LIBRE ---
        pair = None
        for T in sorted(board.by_id):
            if not board.walkable(T):
                continue
            tc = board.coord(T)
            for C in board.neighbours(T):
                if not board.walkable(C) or C == T:
                    continue
                cc = board.coord(C)
                di = _dir_index(cc[0], cc[1], tc[0], tc[1])
                if di is None:
                    continue
                bcol, brow = _step(tc[0], tc[1], di)
                B = board.id_at(bcol, brow)
                behind_free = (B is not None and board.walkable(B) and B not in (T, C))
                if want_free and behind_free:
                    pair = (C, T, di, B)
                    break
                if (not want_free) and (B is None or not board.walkable(B)):
                    pair = (C, T, di, None)
                    break
            if pair:
                break
        if pair is None:
            print(f"SKIP: aucune config {mode} trouvee")
            return 0
        C, T, di, B = pair
        cc, tc = board.coord(C), board.coord(T)
        print(f"config push {'LIBRE' if want_free else 'BLOQUE'} : caster@{cc} (tile {C})  "
              f"cible@{tc} (tile {T})  dir={di} -> {'derriere tile ' + str(B) if want_free else 'hors-board'}")

        # parquer le 3e loin (jamais sur C/T/B -- en free mode B doit rester libre pour le push)
        if tid3 is not None:
            far = next((t for t in sorted(board.by_id)
                        if board.walkable(t) and t not in (C, T, B)), None)
            if far is not None:
                fc = board.coord(far)
                _r(sid, "applyAction", {"runnerId": rid, "action": {
                    "kind": "move", "unitId": tid3, "to": {"col": fc[0], "row": fc[1]}}}, 90)
        # placer cible au bord, caster adjacent interieur
        _r(sid, "applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": eid, "to": {"col": tc[0], "row": tc[1]}}}, 90)
        _r(sid, "applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": cid, "to": {"col": cc[0], "row": cc[1]}}}, 90)

        dec1 = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        ob1 = _r(sid, "observeBattle", {"runnerId": rid}, 60)
        obu1 = {u.get("squadId"): u for u in (ob1.get("units") or [])}
        c1 = _find(dec1, CASTER_VIS)
        t1 = _find(dec1, TARGET_VIS)
        print(f"apres move : caster@{_pos(c1)} cible@{_pos(t1)} "
              f"cible hp={obu1.get(eid, {}).get('hp')}/{obu1.get(eid, {}).get('hpMax')}")

        cast = _r(sid, "applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": cid, "targetId": eid, "abilityType": ABILITY}}, 120)

        print("\n==== CAST result (ok=%s) ====" % cast.get("ok"))
        atk_amt = 0
        kb_amt = 0
        moved = None
        for ai, act in enumerate(cast.get("actions") or []):
            print(f"-- action[{ai}] ok={act.get('ok')} mutated={act.get('mutated')} "
                  f"eventCount={act.get('eventCount')}")
            for ch in (act.get("changes") or []):
                if ch.get("squadId") == eid:
                    moved = ch.get("moved")
                print("   CHANGE", json.dumps(ch, sort_keys=True))
            for ev in (act.get("events") or []):
                print("   EVENT", json.dumps({k: ev.get(k) for k in
                      ("kind", "step", "entity", "source", "tags")}, sort_keys=True))
                if ev.get("entity") == eid and ev.get("step") == SE.step_id("UnitDamaged") \
                        and ev.get("tags"):
                    try:
                        tg = json.loads(ev["tags"])
                    except Exception:
                        tg = {}
                    a = tg.get("Amount")
                    if a is not None and tg.get("Active_Ability_Type") is not None:
                        atk_amt += int(a)
                    elif a is not None and tg.get("DamageProfileType") == 0:
                        kb_amt += int(a)
        print(f"\n== VERDICT == mode={mode} moved={moved} attaque_isolee={atk_amt} knockback_isole={kb_amt}")
        if tmax:
            print(f"   Ceiling({tmax}x10/100)={-(-tmax*10//100)}  Ceiling({tmax}x20/100)={-(-tmax*20//100)}")
            if want_free:
                print("   attendu (push libre) : knockback_isole = 0" +
                      ("  -> OK" if kb_amt == 0 else "  -> FAIL"))
            else:
                exp20 = -(-tmax * 20 // 100)
                print("   attendu (push bloque) : knockback_isole = Ceiling(maxHealthx20%) = " +
                      f"{exp20}" + ("  -> OK" if kb_amt == exp20 else "  -> FAIL"))
        # maxHealth final + discrimination
        obf = _r(sid, "observeBattle", {"runnerId": rid}, 60)
        obuf = {u.get("squadId"): u for u in (obf.get("units") or [])}
        tf = obuf.get(eid) or {}
        print(f"\ntarget final hp={tf.get('hp')}/{tf.get('hpMax')}")
        if tmax:
            print(f"discrimination : Ceiling({tmax}x10/100)={-(-tmax*10//100)}  "
                  f"Ceiling({tmax}x20/100)={-(-tmax*20//100)}")
    finally:
        _rpc(sid, "disposeRunner", [{"runnerId": rid}], timeout=20)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
