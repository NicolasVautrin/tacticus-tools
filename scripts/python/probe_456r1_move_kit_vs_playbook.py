"""#456-r1 -- DEPARTAGER les deux causes de l'ecart de valeur du terme MOVE (9 lignes sur 102).

CE QUE #456 A LAISSE OUVERT. Son etage E5 a mesure que le port rend `0.0` la ou le natif produit
20/40/101/202/303, a LOCALISE l'etage (`load_playbook` rend `None` pour `1133 CyclicIonBlaster` et
`1145 SereneUnifier`) et a REFUSE de departager deux causes :

  (a) le PLAYBOOK de l'ability n'est pas porte cote Python -- le registre `TRIGGERED_MOVE_PLAYBOOKS`
      n'a pas d'entree pour elle, alors que le natif en a une ;
  (b) le KIT lu par le port est plus etroit que l'`AbilitiesComponent` que le natif itere -- le
      terme natif vient d'une ability que le canal du port ne publie PAS.

CE PROBE LES DEPARTAGE, PAR UNITE, SANS la decomposition par playbook (`contribs`, qui exige une
fenetre de reinject). Le discriminant est le KIT, pas la valeur :

    kit_natif  = `unitAbilityStates` -> `TriggeredAbility.AbilityName` (`raw[0]`) de CHAQUE entree
                 du `TriggeredAbilityComponent`. C'est LITTERALEMENT la collection que
                 `IdunBattle.AI.Utilities.TriggeredAbilitiesUtility.u003CEvaluateMovementInStepsu003Ed__2$$MoveNext`
                 enumere (`case.unit@+0x10` -> GetComponent -> `+0x18` -> GetEnumerator).
    kit_port   = `runner_tile_leaf_ctx(state, uid)["unit_triggered_abilities"]`, ce que la feuille
                 `TriggeredAbilitiesUtility.evaluate` du port boucle reellement.

    (b) mord si  kit_natif \\ kit_port  != {}                 -> le port ne VOIT pas l'ability
    (a) mord si  {ab in kit_natif : load_playbook(ab) is None} != {}   -> le port la voit et n'a
                                                                          pas son playbook

Les deux sont INDEPENDANTES et peuvent coexister sur la meme bataille, sur des unites differentes :
c'est precisement pourquoi #456 refusait de generaliser de l'une a l'autre.

Montage : celui de #443-r1a (`MC1_67`/777, greffe 1120 sur `tauCrisis`), pour que la mesure porte
sur LES MEMES 102 events -- un autre montage ne fermerait pas le meme residu.

Usage (depuis scripts/python) :
    python probe_456r1_move_kit_vs_playbook.py --state-file <ABSOLU> [--no-graft] [--keep]

ASCII only.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import requests

HOST = "http://127.0.0.1:8765"
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

BOARD = "MC1_67"
SEED = "777"
FALLBACK_P_UNITS = ["tauCrisis", "tauAunShi", "tauDarkstrider", "ultraTitus"]
FALLBACK_A_UNITS = ["tauShadowsun", "astraCreed"]


# ------------------------------------------------------------------ verdict (fonction PURE)

def check_kit_gap(rows) -> dict:
    """LE VERDICT DE TRANCHAGE. `rows` : une par unite vue dans les events du capteur, avec
    `unitId`, `visualId`, `kit_natif`, `kit_port`, `sans_playbook` (ids du kit NATIF que
    `load_playbook` ne charge pas).

    Rend `{"status", "message", "cause_b", "cause_a"}` ou :
      * `cause_b` = {unitId: [ids vus par le natif, invisibles du port]} ;
      * `cause_a` = {unitId: [ids vus par le natif ET par le port, sans playbook au registre]}.

    STATUT `no-rows` si aucune unite n'a pu etre confrontee : on ne conclut RIEN (ni « pas de
    trou », ni « trou partout ») -- un kit natif vide se lit comme un canal muet, pas comme une
    mesure, tant qu'on n'a pas au moins une unite dont le kit natif est NON VIDE."""
    if not rows:
        return {"status": "no-rows", "cause_a": {}, "cause_b": {},
                "message": "aucune unite confrontee -- RIEN n'est conclu"}
    if not any(r.get("kit_natif") for r in rows):
        return {"status": "degenerate", "cause_a": {}, "cause_b": {},
                "message": ("le kit NATIF est vide sur les %d unite(s) : le canal "
                            "`unitAbilityStates` est MUET ici, la comparaison serait degeneree "
                            "(vide == vide passerait)" % len(rows))}
    cause_b, cause_a = {}, {}
    for r in rows:
        nat, port = list(r.get("kit_natif") or ()), set(r.get("kit_port") or ())
        invisibles = [a for a in nat if a not in port]
        if invisibles:
            cause_b[r["unitId"]] = invisibles
        sp = [a for a in nat if a in port and a in set(r.get("sans_playbook") or ())]
        if sp:
            cause_a[r["unitId"]] = sp
    if not cause_a and not cause_b:
        return {"status": "ok", "cause_a": {}, "cause_b": {},
                "message": ("%d unite(s) : kit natif == kit port partout, et toute ability du kit "
                            "a son playbook au registre MOVE" % len(rows))}
    parts = []
    if cause_b:
        parts.append("CAUSE (b) KIT TROP ETROIT sur %d unite(s) : %s"
                     % (len(cause_b), json.dumps(cause_b, sort_keys=True)))
    if cause_a:
        parts.append("CAUSE (a) PLAYBOOK NON PORTE sur %d unite(s) : %s"
                     % (len(cause_a), json.dumps(cause_a, sort_keys=True)))
    return {"status": "gap", "cause_a": cause_a, "cause_b": cause_b,
            "message": " | ".join(parts)}


# ------------------------------------------------------------------ transport

def sid() -> int:
    return int(requests.get(f"{HOST}/api/admin/status", timeout=10).json()["session"]["id"])


def rpc(s: int, method: str, args=None, timeout: int = 60, tolerate_unknown: bool = False):
    r = requests.post(f"{HOST}/api/scripts/{s}/rpc",
                      json={"method": method, "args": [args or {}], "timeout": int(timeout) * 1000},
                      timeout=timeout + 30)
    if r.status_code >= 400:
        if tolerate_unknown:
            return None
        raise RuntimeError("%s HTTP %d: %s" % (method, r.status_code, r.text[:400]))
    body = r.json()
    if body.get("error"):
        if tolerate_unknown:
            return None
        raise RuntimeError(str(body["error"])[:400])
    return body.get("result")


def native_kits(s: int, rid: int) -> dict:
    """`{unitId: [TriggeredAbilityType]}` -- l'`AbilitiesComponent` REEL, toutes hierarchies
    confondues (`raw[0]` = `TriggeredAbility.AbilityName`). MEME lecture que
    `engine/ai/context.py::live_triggered_kits`, refaite ici pour que le probe ne depende pas du
    cache d'un autre module."""
    out: dict = {}
    r = rpc(s, "unitAbilityStates", {"runnerId": rid}, 60) or {}
    for u in (r.get("units") or []):
        uid = u.get("entityId")
        if uid is None:
            continue
        ids = []
        for t in (u.get("triggered") or []):
            raw = (t or {}).get("raw") or []
            v = raw[0] if raw else None
            if isinstance(v, int) and v > 0 and v not in ids:
                ids.append(v)
        out[int(uid)] = ids
    return out


def _graft_seed_bc(tag: str):
    import catalog_inject as CI
    out = os.path.join(os.path.dirname(_HERE), "..", "logs", "seedbc-456r1-%s.json" % tag)
    out = os.path.abspath(out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    return CI.write_grafted_seed_bc(out, ["tauCrisis:SaviorProtocols"], replace=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default=SEED)
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--state-file", required=True)
    ap.add_argument("--no-graft", action="store_true")
    ap.add_argument("--reuse", action="store_true")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()

    s = sid()
    st = rpc(s, "triggeredMoveTraceStatus", {}, 30, tolerate_unknown=True)
    if st is None:
        print("E0 canal   [not_reinjected] le capteur #443-r1a n'est PAS charge -- NON CONFRONTE")
        return 7
    print("E0 canal   [ok] capteur charge")

    seed_bc = None
    if not a.no_graft:
        try:
            seed_bc, _ = _graft_seed_bc(str(os.getpid()))
        except Exception as e:                                            # noqa: BLE001
            print("   greffe 1120 INDISPONIBLE (%s) -- on continue sans" % str(e)[:160])

    if not a.reuse:
        argv = [sys.executable, "rl_duel.py", "build", "--seed", str(a.seed),
                "--board", a.board, "--state-file", a.state_file,
                "--p-units", ",".join(FALLBACK_P_UNITS),
                "--a-units", ",".join(FALLBACK_A_UNITS)]
        if seed_bc:
            argv += ["--seed-bc", str(seed_bc)]
        out = subprocess.run(argv, cwd=_HERE, capture_output=True, text=True,
                             encoding="utf-8", errors="replace")
        if out.returncode != 0:
            print("BUILD FAILED rc=%d" % out.returncode)
            print((out.stdout or "")[-1500:])
            print((out.stderr or "")[-1500:])
            return 1
    rid = json.loads(Path(a.state_file).read_text(encoding="utf-8"))["runnerId"]
    print("runnerId=%s board=%s seed=%s session=%s greffe=%s"
          % (rid, a.board, a.seed, s, bool(seed_bc)))

    try:
        rpc(s, "triggeredMoveTraceClear", {}, 30)
        rpc(s, "triggeredMoveTraceOn", {}, 60)
        rpc(s, "aiDryRunAllUnits", {"runnerId": rid}, 180, tolerate_unknown=True)
        dump = rpc(s, "triggeredMoveTraceDump", {"runnerId": rid, "max": 4000}, 60) or {}
        entries = dump.get("entries") or []
        print("E1 events  [%s] %d event(s) captes" % ("ok" if entries else "vide", len(entries)))

        kits = native_kits(s, rid)
        print("E2 kit natif : %d unite(s) dans `unitAbilityStates`" % len(kits))

        # ---- l'etat du port, MEME reconstruction que `probe_443r1a._port_rows` ---------------- #
        from engine.entities.pathfinding.board import Board
        from engine.playbook.adjacent_unit_preference import load_playbook
        from engine.runner.snapshot import load_state
        from engine.utilities.tile import runner_tile_leaf_ctx

        dv = rpc(s, "decisionView", {"runnerId": rid}, 120)
        ob = rpc(s, "observeBattle", {"runnerId": rid}, 60)
        snap = rpc(s, "combatSnapshot", {"runnerId": rid}, 60)
        bg = rpc(s, "boardGraph", {"runnerId": rid}, 90)
        state = load_state(dv, ob, snap, board=Board(bg["tiles"], adjacency="native_sym"))
        vis = {int(u["id"]): u.get("visualId") for u in (dv.get("units") or [])
               if u.get("id") is not None}

        uids = sorted({int(e["unitId"]) for e in entries if e.get("unitId") is not None})
        rows = []
        for uid in uids:
            try:
                leaf = runner_tile_leaf_ctx(state, uid, None)
            except Exception:                                             # noqa: BLE001
                leaf = None
            if leaf is None:
                continue
            kp = [int(x) for x in (leaf.get("unit_triggered_abilities") or ())]
            kn = [int(x) for x in (kits.get(uid) or ())]
            rows.append({"unitId": uid, "visualId": vis.get(uid),
                         "kit_natif": kn, "kit_port": kp,
                         "sans_playbook": [x for x in kn if load_playbook(x) is None]})
        for r in rows:
            print("   u%-4s %-16s natif=%-28s port=%-16s sans_playbook=%s"
                  % (r["unitId"], r["visualId"], r["kit_natif"], r["kit_port"],
                     r["sans_playbook"]))

        v = check_kit_gap(rows)
        print("E3 tranche [%s] %s" % (v["status"], v["message"]))
        return 0 if v["status"] == "ok" else 8
    finally:
        try:
            rpc(s, "triggeredMoveTraceOff", {}, 30, tolerate_unknown=True)
        except Exception:                                                 # noqa: BLE001
            pass
        if not a.keep:
            try:
                subprocess.run([sys.executable, "rl_duel.py", "dispose",
                                "--state-file", a.state_file], cwd=_HERE,
                               capture_output=True, text=True)
            except Exception:                                             # noqa: BLE001
                pass


if __name__ == "__main__":
    raise SystemExit(main())
