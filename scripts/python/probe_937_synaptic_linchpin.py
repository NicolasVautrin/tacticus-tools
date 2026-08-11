"""#937 -- `SynapticLinchpin` (passif d'`tyranWingedPrime`) : MESURE LIVE des quatre faits que la RE
predit, chacun sur un ATTAQUANT different, pour que le gate `HasTrait(actor, Synapse)` soit
DISCRIMINE et pas seulement satisfait.

RE (decompile = verite, cf. `engine/runner/operations/triggers/loki/synaptic_linchpin.py`) :

    CreateTrigger  = On(38 = NormalAttack, ownerNeedsToBeAlive: NOT(OwnerIsActor
                          & TriggeringAbilityIs(TriggeredAbilityType.FinalJustice = 1024)))
                     & HasTrait(actor@+0x40, UnitTrait.Synapse = 2024)
                     & AreFriends(owner@+0x30, actor@+0x40)
                     & IsAlive(target@+0x60)
    CreateBehaviour = Repeat(If(NOT AmountIsEqualOrGreater(
                                    UnitsWithId(Children(owner), "tyranSmnHormagaunt", 3),
                                    Direct(maxSummons)),
                                Spawn(owner, First(SortTilesByUtilityForSummon(
                                          CanAddUnit(AdjacentTiles(target)), 7, caster), 1),
                                      unitId, opts{+0x18 = UseNormalAttackIfAble(activeTarget,
                                                                                 target)})),
                            Direct(nrOfSummons = 1))

CE QUE LE PROBE MESURE (un `--attacker` par execution) :
  M1  l'attaquant porte `Synapse` (Winged Prime lui-meme, ou un ALLIE Synapse) et sa cible SURVIT
      -> UN `tyranSmnHormagaunt` apparait, sur la team du PORTEUR, ADJACENT a la cible ;
  M2  le Hormagaunt frais ATTAQUE la cible immediatement (delta de PV de la cible APRES le spawn,
      au-dela des degats de l'attaque declenchante) ;
  M3  l'attaquant SANS `Synapse` (`tyranTyrantGuard`) -> AUCUN Hormagaunt (le gate MORD) ;
  M4  le cap : repeter des attaques qualifiantes -> le compte de Hormagaunts vivants plafonne a
      `maxSummons[level]`.

⚠ COMPTAGE : le montage est TYRANIDE, donc d'autres spawns peuvent apparaitre en cours de mesure.
On compte donc UNIQUEMENT les `visualId` qui contiennent `Hormagaunt`, et on DIFFERENCIE l'ensemble
d'ids AVANT / APRES chaque action -- jamais un attendu ecrit en dur.

Usage (depuis scripts/python) :
    python probe_937_synaptic_linchpin.py --state-file <ABSOLU> [--board MC1_67] [--seed 777]
                                          [--attacker tyranWingedPrime] [--turns 16] [--keep]
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from collections import deque

import requests
from sibling_script import sibling_script

HOST = "http://127.0.0.1:8765"
PRIME = "tyranWingedPrime"          # le PORTEUR du passif (trait Synapse + FinalJustice)
SYNAPSE_ALLY = "tyranNeurothrope"   # allie porteur de `Synapse` -> le trigger doit fire AUSSI
PLAIN_ALLY = "tyranTyrantGuard"     # allie SANS `Synapse` -> cas NEGATIF du gate
ENEMIES = "astraBullgryn,necroWarden"
HORMA = "Hormagaunt"                # sous-chaine du `visualId` du summon (config `tyranSmnHormagaunt`)


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


def _dv(s, rid):
    return rpc(s, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)


def _find(dv, vis, alive=True):
    return next((u for u in (dv.get("units") or [])
                 if u.get("visualId") == vis and (u.get("alive") or not alive)), None)


def _hormas(dv):
    """ids des Hormagaunts VIVANTS -- on DERIVE l'ensemble, jamais un compte attendu en dur."""
    return {u["id"] for u in (dv.get("units") or [])
            if u.get("alive") and HORMA in (u.get("visualId") or "")}


def _tile(board_n, u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row")) if p.get("col") is not None else None


def _neighbours(tiles, key):
    return tiles.get(key, ())


def _build_adj(bg):
    """(col,row) -> voisins, depuis le `boardGraph` (adjacence NATIVE, champ brut)."""
    by_id, adj = {}, {}
    for t in (bg.get("tiles") or []):
        by_id[t["id"]] = (t["col"], t["row"])
    for t in (bg.get("tiles") or []):
        adj[(t["col"], t["row"])] = tuple(by_id[n] for n in (t.get("neighbours") or []) if n in by_id)
    return adj


def _advance_to_my_turn(s, rid, vis, max_iter=20):
    for _ in range(max_iter):
        dv = _dv(s, rid)
        u = _find(dv, vis)
        if u is None:
            return dv, None
        if dv.get("currentPlayer") == u.get("owner"):
            return dv, u
        rpc(s, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    return None, None


def _normal_id(u):
    return next((a.get("id") for a in (u.get("abilities") or []) if a.get("kind") == "normal"), None)


def _dump_events(res) -> None:
    """Journal BRUT du cast (`captureEvents: true`) : c'est LA seule voie qui montre si le trigger
    natif a FIRE (un `SpawnUnit`/`AddUnit`/`TriggerTriggeredAbility` y apparait), par opposition a
    un simple delta d'etat qui ne dit pas POURQUOI il est nul."""
    if not isinstance(res, dict):
        print("[937]   events: reponse non-dict %r" % (res,))
        return
    keys = sorted(res)
    print("[937]   applyAction ok=%s cles=%s" % (res.get("ok"), keys))
    acts = res.get("actions") or []
    print("[937]   actions n=%d" % len(acts))
    for x in acts[:5]:
        if not isinstance(x, dict):
            continue
        print("[937]     kind=%s ok=%s changes=%s"
              % (x.get("kind"), x.get("ok"), json_short(x.get("changes"), 400)))
        _linchpin_window(x.get("events") or [])
    evs = res.get("events") or res.get("capturedEvents") or []
    print("[937]   events n=%d" % len(evs))


def _linchpin_window(evs) -> None:
    """FENETRE du groupe `SynapticLinchpin` : les events entre son ouverture (`kind: group`,
    `source: SynapticLinchpin`) et son `finish` -- c'est LA (le spawn + l'attaque du summon)."""
    flat = []

    def _flat(xs):
        for e in xs:
            if isinstance(e, dict):
                flat.append(e)
                _flat(e.get("events") or e.get("children") or [])
    _flat(evs)
    depth, on = 0, False
    for e in flat:
        if e.get("kind") == "group" and e.get("source") == "SynapticLinchpin" and not on:
            on, depth = True, 0
            print("[937]   >>> FENETRE SynapticLinchpin (entity=%s)" % e.get("entity"))
            continue
        if not on:
            continue
        if e.get("kind") == "group":
            depth += 1
        elif e.get("kind") == "finish":
            if depth == 0:
                print("[937]   <<< fin de fenetre")
                on = False
                continue
            depth -= 1
        print("[937]       %s" % json_short({k: v for k, v in e.items()
                                             if k not in ("events", "children")}, 300))


def _walk_events(evs, depth) -> None:
    """Journal RECURSIF du cast : le natif imbrique les groupes (`kind: group`), et c'est DANS ces
    groupes que vivent les operations engendrees par un trigger (`SpawnUnit`/`AddUnit`)."""
    pad = "  " * (depth + 3)
    for e in evs[:120]:
        if not isinstance(e, dict):
            print("[937] %s%r" % (pad, e))
            continue
        kind = e.get("kind")
        sub = e.get("events") or e.get("children") or []
        head = {k: v for k, v in e.items() if k not in ("events", "children")}
        print("[937] %s%s" % (pad, json_short(head, 220)))
        if sub:
            _walk_events(sub, depth + 1)
        if kind is None:
            pass
    for e in evs[:60]:
        if isinstance(e, dict):
            print("[937]     %s" % json_short(e))
        else:
            print("[937]     %r" % (e,))


def json_short(d, n=260):
    import json as _j
    return _j.dumps(d)[:n]


def _bfs(adj, start):
    seen, q = {start: 0}, deque([start])
    while q:
        x = q.popleft()
        for n in adj.get(x, ()):
            if n not in seen:
                seen[n] = seen[x] + 1
                q.append(n)
    return seen


def _attack_once(s, rid, adj, attacker_vis, max_turns=16):
    """DRIVE : approche `attacker_vis` d'un ennemi et lui fait porter son attaque NORMALE.
    Rend (dv_avant, dv_apres, target_id, target_hp_avant) ou (None, None, None, None)."""
    for _ in range(max_turns):
        dv, att = _advance_to_my_turn(s, rid, attacker_vis)
        if att is None:
            return None, None, None, None
        aid, norm = att["id"], _normal_id(att)
        foes = [u for u in (dv.get("units") or [])
                if u.get("alive") and u.get("owner") != att.get("owner")
                and (u.get("pos") or {}).get("col") is not None]
        if not foes or norm is None:
            return None, None, None, None
        # CHOIX DE CIBLE **DRIVE**, pas subi : le behaviour a besoin d'au moins UNE tuile posable
        # adjacente a la cible APRES que l'attaquant se soit mis au contact (il en consomme une).
        # On classe donc par (voisins libres, PV) decroissants -- une cible sans voisin libre rend
        # un groupe de trigger VIDE qui ressemble a un trigger qui n'a pas fire.
        occupied = {((u.get("pos") or {}).get("col"), (u.get("pos") or {}).get("row"))
                    for u in (dv.get("units") or []) if u.get("alive")}

        def _free_around(u):
            p = u.get("pos") or {}
            nb = adj.get((p.get("col"), p.get("row")), ())
            return sum(1 for t in nb if t not in occupied)

        foes.sort(key=lambda u: (_free_around(u), int(u.get("hp") or 0)), reverse=True)
        tgt = foes[0]
        print("[937]   cibles candidates (libres_autour, hp) = %s"
              % [(u.get("visualId"), _free_around(u), u.get("hp")) for u in foes])
        at, et = _tile(adj, att), _tile(adj, tgt)
        if at is not None and et is not None and _bfs(adj, et).get(at, 99) <= 1:
            hp0 = int(tgt.get("hp") or 0)
            res = rpc(s, "applyAction", {"runnerId": rid, "action": {
                "kind": "ability", "casterId": aid, "targetId": tgt["id"],
                "abilityType": norm}, "captureEvents": True}, 120)
            _dump_events(res)
            return dv, _dv(s, rid), tgt["id"], hp0
        # approcher
        dgoal = _bfs(adj, et) if et is not None else {}
        mt = rpc(s, "aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
        cmt = next((x for x in (mt.get("units") or []) if x.get("unitId") == aid), None)
        reach = {(t["col"], t["row"]) for t in ((cmt or {}).get("tiles") or [])
                 if t.get("col") is not None}
        pool = [t for t in reach if t in dgoal]
        if pool:
            best = min(pool, key=lambda t: dgoal[t])
            rpc(s, "applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": aid, "to": {"col": best[0], "row": best[1]}}}, 40)
            dv2 = _dv(s, rid)
            att2 = _find(dv2, attacker_vis)
            if att2 is not None and et is not None and _bfs(adj, et).get(_tile(adj, att2), 99) <= 1:
                tgt2 = next((u for u in (dv2.get("units") or []) if u.get("id") == tgt["id"]), None)
                if tgt2 is not None and tgt2.get("alive"):
                    hp0 = int(tgt2.get("hp") or 0)
                    res = rpc(s, "applyAction", {"runnerId": rid, "action": {
                        "kind": "ability", "casterId": aid, "targetId": tgt["id"],
                        "abilityType": _normal_id(att2)}, "captureEvents": True}, 120)
                    _dump_events(res)
                    return dv2, _dv(s, rid), tgt["id"], hp0
        rpc(s, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
    return None, None, None, None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--state-file", required=True)
    ap.add_argument("--attacker", default=PRIME)
    ap.add_argument("--turns", type=int, default=16)
    ap.add_argument("--rounds", type=int, default=1, help="nombre d'attaques qualifiantes (cap)")
    ap.add_argument("--reuse", action="store_true")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()

    if not a.reuse:
        out = subprocess.run([sys.executable, sibling_script("rl_duel.py"), "build",
                              "--seed", a.seed, "--board", a.board, "--state-file", a.state_file,
                              "--p-units", f"{PRIME},{SYNAPSE_ALLY},{PLAIN_ALLY}",
                              "--a-units", ENEMIES],
                             capture_output=True, text=True)
        if out.returncode != 0:
            print("BUILD FAILED rc=%d" % out.returncode)
            print((out.stdout or "")[-1500:])
            print((out.stderr or "")[-1500:])
            return 2
    import json
    rid = int(json.loads(open(a.state_file, encoding="utf-8").read())["runnerId"])
    s = sid()
    print("[937] session=%d runner=%d attacker=%s" % (s, rid, a.attacker))
    bg = rpc(s, "boardGraph", {"runnerId": rid}, 60)
    adj = _build_adj(bg)

    rc = 0
    try:
        for i in range(int(a.rounds)):
            dv0, dv1, tid, hp0 = _attack_once(s, rid, adj, a.attacker, max_turns=a.turns)
            if dv1 is None:
                print("[937] ROUND %d : NON CONFRONTE -- l'attaquant n'a pas pu frapper" % i)
                rc = 3
                break
            before, after = _hormas(dv0), _hormas(dv1)
            new = sorted(after - before)
            # DIFF SUR TOUTES LES UNITES, pas seulement les Hormagaunts : un summon dont le
            # `visualId` LIVE differe de la CLE de config (cas mesure sur ControlEdict :
            # `admecSmnVanguard` -> `admecNpc1Vanguard`) serait invisible d'un filtre par nom.
            all0 = {u["id"] for u in (dv0.get("units") or [])}
            all1 = {u["id"] for u in (dv1.get("units") or [])}
            print("[937]   ENTITES NEUVES (toutes) = %s"
                  % [(x, next((u.get("visualId") for u in (dv1.get("units") or [])
                               if u.get("id") == x), None)) for x in sorted(all1 - all0)])
            tgt = next((u for u in (dv1.get("units") or []) if u.get("id") == tid), None)
            tpos = (tgt or {}).get("pos") or {}
            # GEOMETRIE : `CanAddUnit(AdjacentTiles(target))`. Un groupe de trigger VIDE peut venir
            # (a) du cap, (b) de l'absence de tuile posable -- on les SEPARE en mesurant (b).
            if tpos.get("col") is not None:
                occupied = {((u.get("pos") or {}).get("col"), (u.get("pos") or {}).get("row"))
                            for u in (dv1.get("units") or []) if u.get("alive")}
                nb = adj.get((tpos["col"], tpos["row"]), ())
                print("[937]   voisins de la cible = %d ; LIBRES (hors occupants vivants) = %s"
                      % (len(nb), [t for t in nb if t not in occupied]))
            print("[937] ROUND %d : cible=%s hp %s -> %s (alive=%s)"
                  % (i, tid, hp0, (tgt or {}).get("hp"), (tgt or {}).get("alive")))
            print("[937]   hormagaunts avant=%s apres=%s NOUVEAUX=%s"
                  % (sorted(before), sorted(after), new))
            for nid in new:
                u = next((x for x in (dv1.get("units") or []) if x.get("id") == nid), {})
                p = u.get("pos") or {}
                d = None
                if p.get("col") is not None and tpos.get("col") is not None:
                    d = _bfs(adj, (tpos["col"], tpos["row"])).get((p["col"], p["row"]))
                print("[937]   summon id=%s vis=%s owner=%s pos=%s hp=%s dist_a_cible=%s"
                      % (nid, u.get("visualId"), u.get("owner"), p, u.get("hp"), d))
    finally:
        if not a.keep:
            try:
                rpc(s, "disposeRunner", {"runnerId": rid}, 30)
                print("[937] runner %d dispose" % rid)
            except Exception as exc:                    # noqa: BLE001 -- diagnostic seulement
                print("[937] dispose KO : %s" % str(exc)[:200])
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
