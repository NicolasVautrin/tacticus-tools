"""#106 -- fork `IsMeleeAttack` : la NATURE du coup sur le vecteur `execute_normal_like`.

Mesure LIVE le splash Psyker (`PsykerExtraAttackAbility`, vecteur after-hit -> `execute_normal_like`)
d'un porteur qui a AUSSI un effet gate sur la nature du coup :
  * `tyranNeurothrope` = Psyker + **RangedSpecialist** (+33% aux attaques RANGED,
    `IdunBattle.Entities.Effects.Loki.RangedSpecialistEffect$$CreateEffectDamageBonusForAttack`).
Si le natif traite le splash comme RANGED, le degat du splash porte le +33% ; le port ne le portait
PAS avant #106 (la facade `execute_normal_like` ne threadait pas `is_melee` a l'axe attaquant ->
`is_ranged=None` -> gate `IsRangedAttack` faux).

Usage (depuis scripts/python) :
    python probe_106_splash_nature.py --seed 777 --board MC1_67 --state-file <ABSOLU>
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import deque
from pathlib import Path

import requests

HOST = "http://127.0.0.1:8765"
CASTER = "tyranNeurothrope"
ENEMIES = "darkaCompanion,tyranWingedPrime,ultraInceptorSgt,spaceBlackmane,necroSpyder"


def sid() -> int:
    return int(requests.get(f"{HOST}/api/admin/status", timeout=10).json()["session"]["id"])


def rpc(s: int, method: str, args=None, timeout: int = 60):
    """`timeout` en SECONDES cote appelant ; le host attend des MILLISECONDES."""
    r = requests.post(f"{HOST}/api/scripts/{s}/rpc",
                      json={"method": method, "args": [args or {}], "timeout": int(timeout) * 1000},
                      timeout=timeout + 30)
    if r.status_code >= 400:
        raise RuntimeError("%s HTTP %d: %s" % (method, r.status_code, r.text[:400]))
    body = r.json()
    if "error" in body and body.get("error"):
        raise RuntimeError(str(body["error"])[:400])
    return body.get("result")


def bfs(board, src):
    dist = {src: 0}
    q = deque([src])
    while q:
        x = q.popleft()
        for n in board.neighbours(x):
            if n not in dist and (n == src or board.walkable(n)):
                dist[n] = dist[x] + 1
                q.append(n)
    return dist


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--state-file", required=True)
    ap.add_argument("--turns", type=int, default=40)
    a = ap.parse_args()

    out = subprocess.run([sys.executable, "rl_duel.py", "build", "--seed", a.seed,
                          "--board", a.board, "--state-file", a.state_file,
                          "--roster", "1", "--p-units", CASTER, "--a-units", ENEMIES],
                         capture_output=True, text=True)
    if out.returncode != 0:
        print("BUILD FAILED rc=%d" % out.returncode)
        print((out.stdout or "")[-1500:])
        print((out.stderr or "")[-1500:])
        return 1
    rid = json.loads(Path(a.state_file).read_text(encoding="utf-8"))["runnerId"]
    print("runnerId=%s" % rid)
    s = sid()

    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    from engine.runner.runner import Runner
    from engine.runner.messages import AttackUnitMessage
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.components import StatsComponent

    bg = rpc(s, "boardGraph", {"runnerId": rid}, 60)
    board = Board(bg["tiles"], adjacency="evenq")

    def tile_of(u):
        p = u.get("pos") or {}
        return board.id_at(p.get("col"), p.get("row")) if p.get("col") is not None else None

    dec = rpc(s, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ps0 = next((u for u in dec["units"] if u.get("visualId") == CASTER and u.get("alive")), None)
    if ps0 is None:
        print("caster absent")
        return 2
    me = ps0["owner"]
    norm = next((ab for ab in (ps0.get("abilities") or []) if ab.get("kind") == "normal"), None)
    norm_id = norm["id"]
    print("caster u%s norm_ability=%s effects=%s"
          % (ps0["id"], norm_id, [e.get("name") for e in (ps0.get("effects") or [])]))

    chosen = None
    for _ in range(a.turns):
        dec = rpc(s, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        ps = next((u for u in dec["units"] if u["id"] == ps0["id"] and u.get("alive")), None)
        if ps is None:
            print("caster mort")
            return 3
        ens = [u for u in dec["units"] if u.get("owner") != me and u.get("alive")]
        if len(ens) < 2:
            print("moins de 2 ennemis")
            return 4
        if dec.get("currentPlayer") != me:
            rpc(s, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
            continue
        at = rpc(s, "abilityTargets", {"runnerId": rid, "unitId": ps["id"], "allAbilities": True}, 90)
        fh = set()
        for unit in (at.get("units") or []):
            if unit.get("unitId") != ps["id"]:
                continue
            for ab in (unit.get("abilities") or []):
                if ab.get("abilityId") != norm_id:
                    continue
                for tg in (ab.get("fromHere") or []):
                    if tg.get("kind") == "unit":
                        fh.add(tg.get("targetId"))
        dist_ps = bfs(board, tile_of(ps))
        cands = []
        for T in ens:
            if T["id"] not in fh or dist_ps.get(tile_of(T), 99) < 2:
                continue
            nb = set(board.neighbours(tile_of(T)))
            adjE = [e for e in ens if tile_of(e) in nb]
            if len(adjE) == 1:
                cands.append((T, adjE[0]))
        if cands:
            chosen = cands[0]
            break
        goals = [T for T in ens if set(board.neighbours(tile_of(T))) & {tile_of(e) for e in ens if e is not T}]
        goal = min(goals or ens, key=lambda T: dist_ps.get(tile_of(T), 99))
        dgoal = bfs(board, tile_of(goal))
        mt = rpc(s, "aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
        cmt = next((x for x in (mt.get("units") or []) if x.get("unitId") == ps["id"]), None)
        reach = {board.id_at(t["col"], t["row"]): (t["col"], t["row"])
                 for t in ((cmt or {}).get("tiles") or [])}
        pool = [t for t in reach if t in dgoal and dgoal[t] >= 2] or [t for t in reach if t in dgoal]
        if pool:
            best = min(pool, key=lambda t: dgoal[t])
            col, row = reach[best]
            rpc(s, "applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": ps["id"], "to": {"col": col, "row": row}}}, 40)
        dv2 = rpc(s, "decisionView", {"runnerId": rid, "maxRank": 1}, 60)
        if dv2.get("currentPlayer") == me:
            rpc(s, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
    if chosen is None:
        print("aucun scenario splash atteint")
        return 5

    T, adjE = chosen
    att, tid, eid = ps0["id"], T["id"], adjE["id"]
    dv = rpc(s, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc(s, "observeBattle", {"runnerId": rid}, 40)
    snap = rpc(s, "combatSnapshot", {"runnerId": rid}, 40)
    state = load_state(dv, ob, snap, board=board)
    ae = state.get_entity(att)
    ctx = ae.get_component(StatsComponent).ctx
    effs = state.effects.active_effects(att, {"hp": None}) if state.effects else []
    print("attacker traits=%s active_effects=%s" % (ctx.traits, [e.name for e in effs]))
    s0 = rpc(s, "dumpRng", {"runnerId": rid}, 30)
    rng = IntBasedMersenneTwister()
    rng.mt = list(s0["mt"])
    rng.mti = s0["mti"]
    state.rng = rng

    res = rpc(s, "applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": att, "targetId": tid, "abilityType": norm_id}}, 60)
    a0 = (res.get("actions") or [{}])[0]
    by_target = {}
    flags = {}
    for e in (a0.get("events") or []):
        td = e.get("tags")
        if not td:
            continue
        td = json.loads(td) if isinstance(td, str) else td
        if "Amount" in td and td.get("Target_Id") is not None:
            by_target.setdefault(td["Target_Id"], []).append(td["Amount"])
            flags.setdefault(td["Target_Id"], []).append(
                (td.get("Attack_DidCrit"), td.get("Attack_DidBlock"), td.get("Attack_DidEvade")))
    print("LIVE by_target=%s flags=%s (primary=%s splash=%s)" % (by_target, flags, tid, eid))

    def replay(nature):
        """Rejoue l'attaque depuis l'etat CAPTURE AVANT le tir live (meme dv/ob/snap, meme rng).
        `nature` = valeur d'`is_melee` FORCEE sur la feuille du splash :
          * "port"  -> la valeur du port (False = RANGED, mirror du natif) ;
          * None    -> nature NON threadee = EXACTEMENT le comportement pre-#106 du call-site
                       (`execute_normal_like` ne threadait pas la nature), sans toucher au coup
                       PRIMAIRE (qui, lui, a toujours threade sa nature d'arme) ;
          * True    -> contre-cas : nature MELEE forcee (le gate ranged doit se taire)."""
        import engine.runner.operations.triggers.loki.psyker as P
        st = load_state(dv, ob, snap, board=board)
        r2 = IntBasedMersenneTwister()
        r2.mt = list(s0["mt"])
        r2.mti = s0["mti"]
        st.rng = r2
        orig = P.psyker_smite_tree
        if nature != "port":
            def _forced_tree(pct, profile, _n=nature):
                node = orig(pct, profile)
                node.is_melee = _n
                return node
            P.psyker_smite_tree = _forced_tree
        try:
            rr = Runner(st).install_default_handlers(20)
            rr.apply(AttackUnitMessage(att, tid))
        finally:
            P.psyker_smite_tree = orig
        d = rr.damage_handler
        sp = [x for x in (d.after_hit or []) if x.get("trait") == "Psyker"]
        return ((d.last or {}).get("per_hit"), d.last.get("ranged"), d.last.get("profile"),
                (sp[0]["target"] if sp else None),
                (sp[0]["result"]["per_hit"] if sp else None))

    # FACE PREDICTION du MEME coup : `PsykerPlaybook._predict_amount_vs_target` (slot 0x23) passe
    # `is_ranged=True` -- elle appliquait DEJA le gate ranged. Avant #106 la face COMBAT ne le faisait
    # pas : les deux faces du MEME splash divergeaient. On les confronte au live.
    try:
        from fractions import Fraction
        import gameconfig as GC
        from engine.playbook.scene import Scene
        from engine.playbook.psyker import PsykerPlaybook
        from engine.entities.formulas import _round_fix64
        st_pred = load_state(dv, ob, snap, board=board)
        scene = Scene.from_state(st_pred)
        pct = int((GC.trait("Psyker") or {}).get("variables", {}).get("psykerExtraDmg") or 0)
        amount = int(_round_fix64(Fraction(pct * int(scene.attack_current(att)), 100), 0))
        pred = PsykerPlaybook()._predict_amount_vs_target(scene, att, eid, amount, scene.pos(att))
        pr = pred.accurate_health_damage
        print("PREDICTION splash amount=%s -> [%s,%s]" % (amount, pr.min, pr.max))
    except Exception as exc:                       # diag only : ne fait pas echouer la mesure combat
        print("PREDICTION splash indisponible: %r" % (exc,))

    off_primary, off_ranged, off_prof, off_sp_tid, off_sp = replay("port")
    lg_primary, _, _, lg_sp_tid, lg_sp = replay(None)
    _, _, _, _, mel_sp = replay(True)
    print("OFF primary=%s ranged=%s profile=%s" % (off_primary, off_ranged, off_prof))
    print("OFF splash target=%s per_hit=%s" % (off_sp_tid, off_sp))
    print("LEGACY (nature non threadee = pre-#106) primary=%s splash target=%s per_hit=%s"
          % (lg_primary, lg_sp_tid, lg_sp))
    print("CONTRE-CAS (nature MELEE forcee) splash per_hit=%s" % (mel_sp,))
    print("VERDICT primary live=%s off=%s | splash live=%s off=%s legacy=%s melee=%s | "
          "discriminant=%s | contre-cas=%s"
          % (by_target.get(tid), off_primary, by_target.get(eid), off_sp, lg_sp, mel_sp,
             lg_sp != off_sp, mel_sp != off_sp))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
