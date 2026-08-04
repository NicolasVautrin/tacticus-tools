"""#291 -- un SUMMON n'obtient jamais d'ACTIVATION : ecart de port ou comportement natif ?

RE (decompile = verite, cf. docs/rl/case-291-summon-activation.md) :
  * `IdunBattle.Entities.Behaviours.SpawnUnitBehaviour$$TriggerSpawnedUnitBehaviours` termine
    EXPLICITEMENT le tour de l'unite fraichement apparue --
    `IOperationProcessor` slot 0x23 = `FinishUnitTurn(spawned, isTerminated: true)` -- des lors que
    `TurnComponent.CurrentPlayerId == parentPlayerId` et que l'unite n'a NI `UnitTrait.Steppable`(27)
    NI `UnitTrait.Hero`(16) (override par le `Nullable<bool>` de `SpawnUnitOptions`).
  * `IdunBattle.Operations.FinishUnitTurnOperation$$Execute` finit par le slot 0x76 =
    `MarkUnitAsNoActionAvailable(unit)` -> `IdunBattle.Entities.UnitExtensions$$HasActionLeft` = false.
  * donc le summon est ABSENT de `decisionView.toActivate` (qui filtre exactement sur
    `IsControlledByCurrentPlayer && IsAlive && HasActionLeft`) : c'est NATIF, pas un trou de harnais.
  * il agit malgre tout par DEUX voies natives distinctes :
      (a) IMMEDIATE -- le noeud DSL `PerformAIAction` cable dans l'ability du summoner
          (`WaaaghAbility$$ExecuteBehaviour`, 5e `Group`) -> `ComputerAction(unit, forced)` qui
          SAUVE/RESTAURE les flags de tour ;
      (b) TURN-START suivant -- `IdunBattle.Operations.StartTurnOperation$$Execute` appelle le slot
          0x71 = `PlayAutomaticUnits(player)` (gate : `!battleQuery.NoAutomaticUnitTurns` et
          `PlayerType` dans {Human(0), Network(3), HumanAI(4)}) ->
          `IdunBattle.Operations.PlayAutomaticUnitsOperation$$Execute` joue chaque unite
          `IdunBattle.Entities.UnitExtensions$$IsAutomatic` (trait `Summon`(2) ou `Object`(13)),
          vivante et !`TurnFinished`, jusqu'a 5 `ComputerAction`, puis `FinishUnitTurn(u, false)`.

Ce probe MESURE les deux voies sur `orksWarboss`/`Waaagh`(1058) -> `orksOrkBoys` :
  E1 cast      : le summon apparait-il ? ou ? avec quels flags ?
  E2 activation: est-il dans `toActivate` ? `hasActionLeft` ? (attendu NATIF : NON / false)
  E3 immediate : a-t-il BOUGE / ATTAQUE dans les events du cast (voie a) ?
  E4 turn-start: bouge-t-il TOUT SEUL au debut du tour suivant de sa team, SANS action du joueur
                 (voie b) ? -> mesure = delta de position/HP entre la fin du tour adverse et le
                 tout debut de mon tour.

Usage (depuis scripts/python) :
    python probe_291_summon_activation.py --state-file <ABSOLU> [--board MC1_67] [--seed 777]
                                          [--turns 25] [--keep]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import requests
from sibling_script import sibling_script

HOST = "http://127.0.0.1:8765"
CASTER = "orksWarboss"
ALLY = "orksNob"
ENEMIES = "darkaCompanion,tyranWingedPrime,ultraInceptorSgt"
WAAAGH = 1058


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


def snap(s: int, rid: int) -> dict:
    """decisionView reduit : {units:{id:{...}}, toActivate:[...], currentPlayer, turn}."""
    dv = rpc(s, "decisionView", {"runnerId": rid, "maxRank": 1}, 90)
    return {
        "currentPlayer": dv.get("currentPlayer"), "turn": dv.get("turn"),
        "toActivate": list(dv.get("toActivate") or []),
        "units": {u["id"]: {
            "visualId": u.get("visualId"), "owner": u.get("owner"), "alive": u.get("alive"),
            # `decisionView` publie le champ `hasAction` (pas `hasActionLeft`) — c'est
            # `UnitExtensions$$HasActionLeft`, cf. `projectUnitsFull`.
            "pos": u.get("pos"), "hp": u.get("hp"), "hasAction": u.get("hasAction"),
            "ctrl": u.get("ctrl"),
        } for u in (dv.get("units") or [])},
    }


def show(tag: str, sn: dict, only=None) -> None:
    print("  [%s] turn=%s currentPlayer=%s toActivate=%s"
          % (tag, sn["turn"], sn["currentPlayer"], sn["toActivate"]))
    for uid, u in sorted(sn["units"].items()):
        if only is not None and uid not in only:
            continue
        print("    u%-4s %-22s owner=%-4s alive=%-5s pos=%-18s hp=%-6s hasAction=%s ctrl=%s"
              % (uid, u["visualId"], u["owner"], u["alive"], u["pos"], u["hp"],
                 u["hasAction"], u["ctrl"]))


def dump_events(evts, limit=60) -> None:
    for e in (evts or [])[:limit]:
        print("     ev kind=%-6s group=%-6s step=%-6s entity=%-5s source=%-12s tags=%s"
              % (e.get("kind"), e.get("group"), e.get("step"), e.get("entity"),
                 str(e.get("source"))[:12], str(e.get("tags") or "")[:150]))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--state-file", required=True)
    ap.add_argument("--turns", type=int, default=25)
    ap.add_argument("--reuse", action="store_true", help="ne rebuild pas (state-file existant)")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()

    if not a.reuse:
        out = subprocess.run([sys.executable, sibling_script("rl_duel.py"), "build", "--seed", a.seed,
                              "--board", a.board, "--state-file", a.state_file,
                              "--p-units", f"{CASTER},{ALLY}", "--a-units", ENEMIES],
                             capture_output=True, text=True)
        if out.returncode != 0:
            print("BUILD FAILED rc=%d" % out.returncode)
            print((out.stdout or "")[-1500:])
            print((out.stderr or "")[-1500:])
            return 1
    rid = json.loads(Path(a.state_file).read_text(encoding="utf-8"))["runnerId"]
    print("runnerId=%s board=%s seed=%s" % (rid, a.board, a.seed))
    s = sid()
    try:
        sn = snap(s, rid)
        wb_id = next((uid for uid, u in sn["units"].items()
                      if u["visualId"] == CASTER and u["alive"]), None)
        if wb_id is None:
            print("warboss absent")
            return 2
        me = sn["units"][wb_id]["owner"]
        print("me=%s warboss=u%s" % (me, wb_id))

        # ---- E0 : APPROCHE jusqu'a ce que le gate dynamique de Waaagh s'ouvre ---------------- #
        from engine.entities.pathfinding.board import Board
        from collections import deque
        bg = rpc(s, "boardGraph", {"runnerId": rid}, 60)
        board = Board(bg["tiles"], adjacency="evenq")

        def tile_of(u):
            p = u.get("pos") or {}
            return (board.id_at(p.get("col"), p.get("row"))
                    if p.get("col") is not None else None)

        def bfs(src):
            dist, q = {src: 0}, deque([src])
            while q:
                x = q.popleft()
                for n in board.neighbours(x):
                    if n not in dist and (n == src or board.walkable(n)):
                        dist[n] = dist[x] + 1
                        q.append(n)
            return dist

        legal = None
        for t in range(a.turns):
            sn = snap(s, rid)
            if sn["currentPlayer"] != me:
                rpc(s, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
                continue
            if not sn["units"].get(wb_id, {}).get("alive"):
                print("warboss mort avant le cast")
                return 3
            at = rpc(s, "abilityTargets", {"runnerId": rid, "unitId": wb_id,
                                           "allAbilities": True}, 90)
            tg = []
            for unit in (at.get("units") or []):
                if unit.get("unitId") != wb_id:
                    continue
                for ab in (unit.get("abilities") or []):
                    if ab.get("abilityId") == WAAAGH:
                        tg = ab.get("fromHere") or []
            print("  approche t%-2d wbPos=%s waaaghTargets=%d"
                  % (t, sn["units"][wb_id]["pos"], len(tg)))
            if tg:
                legal = tg[0]
                break
            ens = [u for uid, u in sn["units"].items() if u["owner"] != me and u["alive"]]
            if not ens:
                print("plus d'ennemi")
                return 4
            dgoal = bfs(tile_of(ens[0]))
            mt = rpc(s, "aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
            cmt = next((x for x in (mt.get("units") or []) if x.get("unitId") == wb_id), None)
            reach = {board.id_at(ti["col"], ti["row"]): (ti["col"], ti["row"])
                     for ti in ((cmt or {}).get("tiles") or [])}
            pool = [ti for ti in reach if ti in dgoal]
            if pool:
                best = min(pool, key=lambda x: dgoal[x])
                col, row = reach[best]
                rpc(s, "applyAction", {"runnerId": rid, "action": {
                    "kind": "move", "unitId": wb_id, "to": {"col": col, "row": row}}}, 60)
            rpc(s, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
        if legal is None:
            print("VERDICT montage: aucune cible legale de Waaagh atteinte en %d tours" % a.turns)
            return 5

        # ---- E1 : CAST ---------------------------------------------------------------------- #
        pre = snap(s, rid)
        act = {"kind": "ability", "casterId": wb_id, "abilityType": WAAAGH}
        if legal.get("kind") == "unit":
            act["targetId"] = legal.get("targetId")
        else:
            act["to"] = {"col": legal.get("col"), "row": legal.get("row")}
        res = rpc(s, "applyAction", {"runnerId": rid, "action": act}, 120)
        a0 = (res.get("actions") or [{}])[0]
        print("E1 cast ok=%s error=%s mutated=%s spawned=%s eventCount=%s"
              % (a0.get("ok"), a0.get("error"), a0.get("mutated"), a0.get("spawned"),
                 a0.get("eventCount")))
        print("   EVENTS DU CAST (voie a = PerformAIAction attendu en fin de chaine) :")
        dump_events(a0.get("events"))

        # ---- E2 : ACTIVATION du summon fraichement apparu ------------------------------------ #
        post = snap(s, rid)
        newborn = sorted(set(post["units"]) - set(pre["units"]))
        print("E2 unites APPARUES = %s" % newborn)
        if not newborn:
            print("VERDICT montage: aucun summon apparu -> mesure impossible")
            return 6
        show("post-cast", post, only=set(newborn) | {wb_id})
        for uid in newborn:
            u = post["units"][uid]
            print("E2 summon u%s : hasActionLeft=%s  dans toActivate=%s  (attendu NATIF: False/False)"
                  % (uid, u["hasAction"], uid in post["toActivate"]))

        # ---- E3 : la VOIE (a) a-t-elle deplace/fait attaquer le summon ? --------------------- #
        # Un `ComputerAction` immediat produit des events portes par l'entite du summon.
        own = [e for e in (a0.get("events") or []) if e.get("entity") in newborn]
        print("E3 events PORTES par un summon dans le cast = %d" % len(own))
        dump_events(own)

        # ---- E4 : la VOIE (b) -- turn-start automatique du tour SUIVANT ---------------------- #
        # On finit le tour, on laisse l'IA jouer, puis on RE-LIT au tout debut de notre tour
        # SANS avoir agi : tout delta de position/HP vient de `PlayAutomaticUnits`.
        rpc(s, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 90)
        # tour adverse (IA) -> on avance jusqu'a revenir a nous
        guard = 0
        while guard < 6:
            cur = snap(s, rid)
            if cur["currentPlayer"] == me:
                break
            try:
                rpc(s, "aiTurn", {"runnerId": rid}, 180)
            except Exception:
                rpc(s, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 90)
            guard += 1
        mine = snap(s, rid)
        print("E4 debut de MON tour suivant (aucune action jouee depuis) :")
        show("turn-start", mine, only=set(newborn) | {wb_id})
        for uid in newborn:
            b = post["units"].get(uid) or {}
            n = mine["units"].get(uid) or {}
            print("E4 summon u%s : pos %s -> %s | alive %s -> %s | hasAction %s -> %s | toActivate=%s"
                  % (uid, b.get("pos"), n.get("pos"), b.get("alive"), n.get("alive"),
                     b.get("hasAction"), n.get("hasAction"), uid in mine["toActivate"]))
        # dommages infliges aux ennemis pendant la bascule (indice d'attaque automatique)
        for uid, u in sorted(mine["units"].items()):
            if u["owner"] == me:
                continue
            hp0 = (post["units"].get(uid) or {}).get("hp")
            if hp0 is not None and u["hp"] != hp0:
                print("E4 ennemi u%s %s hp %s -> %s" % (uid, u["visualId"], hp0, u["hp"]))
        return 0
    finally:
        if not a.keep:
            try:
                subprocess.run([sys.executable, sibling_script("rl_duel.py"), "dispose",
                                "--state-file", a.state_file], capture_output=True, text=True)
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
