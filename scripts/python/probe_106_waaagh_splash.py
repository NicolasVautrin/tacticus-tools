"""#106 -- CONTRE-CAS melee-only : `Waaagh_ExtraDamage` (1100) NE doit PAS buffer un coup RANGED.

Le cas #106 part de `IdunBattle.Entities.Effects.Loki.Waaagh_ExtraDamageEffect$$CreateEffectDamageBonusForAttack`
(axe DEGAT) et `IdunBattle.Entities.Effects.Loki.Waaagh_ExtraHitsEffect$$CreateEffectHitsBonusForAttack`
(axe COUPS) : MEME condition native `IsNormalAttack & IsMeleeAttack & get_OwnerIsCaster`, deux
representations divergentes cote port sur nature inconnue.

MONTAGE. `WaaaghAbility$$GetBuffedUnitsSelector` = `Unique(caster + AdjacentFriends(caster,1) +
UnitsFromFaction(Friends, Orks))` -> un allie ADJACENT de N'IMPORTE QUELLE faction recoit le buff.
On met donc `orksWarboss` a cote de `tyranNeurothrope` (Psyker), on caste Waaagh, puis le Neurothrope
tire son arme RANGED psychique -> le splash Psyker passe par `execute_normal_like(is_melee=False)`.
Le porteur du splash porte alors 1100 (melee-only, +extraDmg PLAT) : le natif ne doit PAS l'appliquer.

#111 -- Le cast de Waaagh exige une CIBLE ENNEMIE LEGALE (cf. le commentaire au call-site).
La version initiale de ce probe ciblait le CASTER lui-meme : le moteur refusait le cast en amont de
tout etage de pose, aucun buff n'etait pose, et le probe sortait en `NON DISCRIMINANT`. La cible est
desormais lue dans `abilityTargets(...).fromHere` du Warboss.

Usage (depuis scripts/python) :
    python probe_106_waaagh_splash.py --seed 777 --board MC1_67 --state-file <ABSOLU>
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
BUFFER = "orksWarboss"
ENEMIES = "darkaCompanion,tyranWingedPrime,ultraInceptorSgt,spaceBlackmane,necroSpyder"
WAAAGH_ABILITY = 1058


def sid() -> int:
    return int(requests.get(f"{HOST}/api/admin/status", timeout=10).json()["session"]["id"])


def rpc(s: int, method: str, args=None, timeout: int = 60):
    r = requests.post(f"{HOST}/api/scripts/{s}/rpc",
                      json={"method": method, "args": [args or {}], "timeout": int(timeout) * 1000},
                      timeout=timeout + 30)
    if r.status_code >= 400:
        raise RuntimeError("%s HTTP %d: %s" % (method, r.status_code, r.text[:400]))
    body = r.json()
    if body.get("error"):
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
                          "--roster", "2", "--p-units", f"{CASTER},{BUFFER}",
                          "--a-units", ENEMIES],
                         capture_output=True, text=True)
    if out.returncode != 0:
        print("BUILD FAILED rc=%d" % out.returncode)
        print((out.stdout or "")[-1200:])
        print((out.stderr or "")[-1200:])
        return 1
    rid = json.loads(Path(a.state_file).read_text(encoding="utf-8"))["runnerId"]
    print("runnerId=%s" % rid)
    s = sid()

    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    from engine.runner.runner import Runner
    from engine.runner.messages import AttackUnitMessage
    from engine.runner.prng import IntBasedMersenneTwister

    bg = rpc(s, "boardGraph", {"runnerId": rid}, 60)
    board = Board(bg["tiles"], adjacency="evenq")

    def tile_of(u):
        p = u.get("pos") or {}
        return board.id_at(p.get("col"), p.get("row")) if p.get("col") is not None else None

    dec = rpc(s, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ps0 = next((u for u in dec["units"] if u.get("visualId") == CASTER and u.get("alive")), None)
    wb0 = next((u for u in dec["units"] if u.get("visualId") == BUFFER and u.get("alive")), None)
    if ps0 is None or wb0 is None:
        print("caster/buffer absent")
        return 2
    me = ps0["owner"]
    norm = next((ab for ab in (ps0.get("abilities") or []) if ab.get("kind") == "normal"), None)
    norm_id = norm["id"]
    print("psyker=u%s warboss=u%s norm=%s" % (ps0["id"], wb0["id"], norm_id))

    chosen = None
    for _ in range(a.turns):
        dec = rpc(s, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        ps = next((u for u in dec["units"] if u["id"] == ps0["id"] and u.get("alive")), None)
        wb = next((u for u in dec["units"] if u["id"] == wb0["id"] and u.get("alive")), None)
        if ps is None or wb is None:
            print("psyker ou warboss mort")
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
        # Le Warboss COLLE au psyker a chaque tour (il doit etre AdjacentFriends au moment du cast).
        if tile_of(wb) not in set(board.neighbours(tile_of(ps))):
            mtw = rpc(s, "aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
            wmt = next((x for x in (mtw.get("units") or []) if x.get("unitId") == wb["id"]), None)
            dps = bfs(board, tile_of(ps))
            reachw = {board.id_at(t["col"], t["row"]): (t["col"], t["row"])
                      for t in ((wmt or {}).get("tiles") or [])}
            poolw = [t for t in reachw if t in dps]
            if poolw:
                bw = min(poolw, key=lambda t: dps[t])
                cw, rw_ = reachw[bw]
                rpc(s, "applyAction", {"runnerId": rid, "action": {
                    "kind": "move", "unitId": wb["id"], "to": {"col": cw, "row": rw_}}}, 40)
                dec = rpc(s, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
                wb = next((u for u in dec["units"] if u["id"] == wb0["id"] and u.get("alive")), wb)
        # #111 : le scenario n'est atteint que si le Warboss peut AUSSI caster -- son gate
        # `WaaaghAbility$$GetDynamicInvalidTargetReason` exige une tuile LIBRE adjacente a une cible
        # ennemie, atteignable en (MOVEMENT + extraMovement) pas. Sans cette condition, la boucle
        # « reussissait » sur la seule geometrie du psyker et le cast qui suivait etait un no-op.
        atw = rpc(s, "abilityTargets", {"runnerId": rid, "unitId": wb["id"],
                                        "allAbilities": True}, 90)
        wfh = [t for unit in (atw.get("units") or []) if unit.get("unitId") == wb["id"]
               for ab in (unit.get("abilities") or []) if ab.get("abilityId") == WAAAGH_ABILITY
               for t in (ab.get("fromHere") or []) if t.get("kind") == "unit"]
        if cands and wfh:
            chosen = (cands[0][0], cands[0][1], ps, wb)
            break
        if cands and not wfh:
            print("splash OK mais Waaagh non castable depuis la tuile du Warboss -> on avance")
        goals = [T for T in ens
                 if set(board.neighbours(tile_of(T))) & {tile_of(e) for e in ens if e is not T}]
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
    T, adjE, ps, wb = chosen
    att, tid, eid = ps0["id"], T["id"], adjE["id"]

    # Amener le Warboss ADJACENT au psyker (selecteur Waaagh = AdjacentFriends, toute faction).
    ps_tile = tile_of(ps)
    nb_ps = set(board.neighbours(ps_tile))
    if tile_of(wb) not in nb_ps:
        mt = rpc(s, "aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
        wmt = next((x for x in (mt.get("units") or []) if x.get("unitId") == wb["id"]), None)
        dest = None
        for t in ((wmt or {}).get("tiles") or []):
            if board.id_at(t["col"], t["row"]) in nb_ps:
                dest = (t["col"], t["row"])
                break
        if dest is None:
            print("warboss ne peut pas devenir adjacent au psyker ce tour")
            return 6
        rpc(s, "applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": wb["id"], "to": {"col": dest[0], "row": dest[1]}}}, 40)

    # Caster Waaagh depuis le Warboss (self-buff + buff des allies adjacents).
    dvp = rpc(s, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    psp = next((u for u in dvp["units"] if u["id"] == att), None)
    wbp = next((u for u in dvp["units"] if u["id"] == wb["id"]), None)
    print("pre-cast: psyker pos=%s tile=%s | warboss pos=%s tile=%s | adjacent=%s"
          % (psp.get("pos"), tile_of(psp), wbp.get("pos"), tile_of(wbp),
             tile_of(wbp) in set(board.neighbours(tile_of(psp)))))
    # #111 -- Waaagh a une CIBLE ENNEMIE OBLIGATOIRE. Le gate natif
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$GetDynamicInvalidTargetReason` =
    # `Count(GetPossibleMovementTiles(target)) > 0` (une tuile LIBRE adjacente a la cible, atteignable
    # par le caster en MOVEMENT+extraMovement pas). Une cible ILLEGALE (le caster lui-meme, un allie,
    # un ennemi hors portee de charge) fait sortir `IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal`
    # a `IdunBattle.Operations.ActiveAbilityOperation$$IsInvalidTarget`, AVANT tout etage de pose :
    # `ok=true, mutated=false, actionConsumed=false`, events = [group User_UseAbility, finish].
    # -> on prend la cible dans `abilityTargets(...).fromHere` (legalite EXACTE du cast immediat),
    # PAS dans `targets` (superset « ce tour, MOVE inclus » : y piocher peut rendre un no-op).
    atw = rpc(s, "abilityTargets", {"runnerId": rid, "unitId": wb["id"], "allAbilities": True}, 90)
    wtg = [t for unit in (atw.get("units") or []) if unit.get("unitId") == wb["id"]
           for ab in (unit.get("abilities") or []) if ab.get("abilityId") == WAAAGH_ABILITY
           for t in (ab.get("fromHere") or []) if t.get("kind") == "unit"]
    if not wtg:
        print("aucune cible LEGALE pour Waaagh depuis la tuile du Warboss "
              "(gate GetDynamicInvalidTargetReason) -> scenario non atteint")
        return 8
    rw = rpc(s, "applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": wb["id"], "targetId": wtg[0]["targetId"],
        "abilityType": WAAAGH_ABILITY}}, 120)
    rw0 = (rw.get("actions") or [{}])[0]
    print("waaagh cast target=%s ok=%s mutated=%s actionConsumed=%s"
          % (wtg[0]["targetId"], rw0.get("ok"), rw0.get("mutated"), rw0.get("actionConsumed")))

    dv = rpc(s, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    psx = next((u for u in dv["units"] if u["id"] == att), None)
    wbx = next((u for u in dv["units"] if u["id"] == wb["id"]), None)
    eff_names = [e.get("name") for e in (psx.get("effects") or [])]
    print("psyker effects apres Waaagh: %s" % eff_names)
    print("warboss effects apres Waaagh: %s"
          % [e.get("name") for e in ((wbx or {}).get("effects") or [])])
    print("psyker pos apres=%s tile=%s | warboss pos apres=%s tile=%s"
          % (psx.get("pos"), tile_of(psx), (wbx or {}).get("pos"), tile_of(wbx or {})))
    if not any("Waaagh_ExtraDamage" in (n or "") for n in eff_names):
        print("NON DISCRIMINANT: le psyker ne porte pas Waaagh_ExtraDamage")
        return 7

    ob = rpc(s, "observeBattle", {"runnerId": rid}, 40)
    snap = rpc(s, "combatSnapshot", {"runnerId": rid}, 40)
    s0 = rpc(s, "dumpRng", {"runnerId": rid}, 30)

    res = rpc(s, "applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": att, "targetId": tid, "abilityType": norm_id}}, 60)
    a0 = (res.get("actions") or [{}])[0]
    by_target, flags = {}, {}
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

    def replay(legacy: bool):
        import engine.runner.operations.triggers.loki.psyker as P
        st = load_state(dv, ob, snap, board=board)
        r2 = IntBasedMersenneTwister()
        r2.mt = list(s0["mt"])
        r2.mti = s0["mti"]
        st.rng = r2
        orig = P.psyker_smite_tree
        if legacy:
            def _legacy_tree(pct, profile):
                node = orig(pct, profile)
                node.is_melee = None
                return node
            P.psyker_smite_tree = _legacy_tree
        try:
            rr = Runner(st).install_default_handlers(20)
            rr.apply(AttackUnitMessage(att, tid))
        finally:
            P.psyker_smite_tree = orig
        d = rr.damage_handler
        sp = [x for x in (d.after_hit or []) if x.get("trait") == "Psyker"]
        return ((d.last or {}).get("per_hit"),
                (sp[0]["result"]["per_hit"] if sp else None))

    off_primary, off_sp = replay(False)
    lg_primary, lg_sp = replay(True)
    print("OFF     primary=%s splash=%s" % (off_primary, off_sp))
    print("LEGACY  primary=%s splash=%s" % (lg_primary, lg_sp))
    print("VERDICT primary live=%s off=%s | splash live=%s off=%s legacy=%s | discriminant=%s"
          % (by_target.get(tid), off_primary, by_target.get(eid), off_sp, lg_sp, lg_sp != off_sp))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
