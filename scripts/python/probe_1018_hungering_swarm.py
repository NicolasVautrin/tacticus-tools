"""#1018 -- CONFRONTATION LIVE de `HungeringSwarm_ExtraHits` (1041).

Mesure ce que le NATIF fait, sur un montage ou le seul degre de liberte est la GEOMETRIE des
Hormagaunts allies autour de la CIBLE. L'oracle de coups est le nombre d'EVENEMENTS de degat
portes par une attaque normale (meme extraction que
`tests/engine/runner/test_ah_master_annihilator_astartes_banner_live.py::_amounts`).

Attendu du port (arbre natif, cf. `engine/entities/effects/loki/hungering_swarm.py`) :

    coups = base_arme + extraHit * |{ allies de l'Owner, adjacents a la CIBLE, != Caster,
                                      dont l'unitId est dans la constante unitIds }|

Les TROIS phases sont des contre-epreuves les unes des autres -- deux hypotheses qui rendent le
meme nombre ne concluent rien, donc chaque phase deplace UN SEUL facteur :

  * `armed`   -- 2 Hormagaunts allies ADJACENTS a la cible -> le compte vaut 2 ;
  * `far`     -- LES MEMES unites, mais posees HORS du ring-1 de la cible : seule la GEOMETRIE
                 change (meme roster, memes stats, meme ability) -> le compte doit tomber a 0.
                 C'est le rail casse : il refute << ces Hormagaunts ajoutent des coups par leur
                 seule PRESENCE dans la bataille >> ;
  * `kronos`  -- 2 `tyranNpc1HormagauntKronos` ADJACENTS (memes traits, meme nom d'affichage
                 << Hormagaunt >>, memes deux passifs), donc geometrie IDENTIQUE a `armed` : seul
                 leur `unitId` change, et il n'est PAS dans la constante `unitIds`. Le compte doit
                 valoir 0. C'est la contre-epreuve qui separe << je compte les voisins allies >>
                 de << je filtre par UnitsWithIds >>.

Usage (state-file ABSOLU, `--runner` explicite pour re-jouer sur un runner deja monte) :

    python probe_1018_hungering_swarm.py --phase armed  --state-file <abs>.json
    python probe_1018_hungering_swarm.py --phase far    --state-file <abs>.json
    python probe_1018_hungering_swarm.py --phase kronos --state-file <abs>.json
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.request

HOTE = "http://127.0.0.1:8765"
ATTACKER = "tyranNpc1Hormagaunt"
PEER_ARMED = "tyranNpc1Hormagaunt"
PEER_KRONOS = "tyranNpc1HormagauntKronos"      # meme unite au sens du JEU, autre `unitId`
TARGET = "ultraTitus"
BOARD = "MC1_67"

#: Placement -- la cible au centre, l'attaquant sur un voisin, les deux pairs selon la phase.
#: `hexgeo.distance((3,4), .) == 1` pour (2,3) (2,4) (3,3) (3,5) (4,3) (4,4) : VERIFIE, pas suppose.
T_POS = (3, 4)
ATT_POS = (2, 4)                                # adjacent a la cible
NEAR = [(4, 4), (3, 5)]                         # adjacents a la cible
FAR = [(4, 1), (2, 1)]                          # distance >= 2 de la cible, memes unites


_SID: "int | None" = None


def session_id() -> int:
    """Id de la session Frida VIVANTE, LU du host (`/api/admin/status`) -- jamais un littéral.
    Un id en dur (`/api/scripts/6/rpc`) rend un HTTP 500 des que le host a redemarre."""
    global _SID
    if _SID is None:
        with urllib.request.urlopen(f"{HOTE}/api/admin/status", timeout=10) as r:
            st = json.loads(r.read().decode())
        s = (st or {}).get("session") or {}
        if s.get("status") != "running":
            raise SystemExit(f"[1018] pas de session Frida vivante : {s.get('status')!r}")
        _SID = int(s["id"])
    return _SID


def rpc(method: str, params: dict, timeout: int = 60):
    """Le corps attendu par le host est `{method, args: [<params>], timeout: <ms>}` -- `args`,
    POSITIONNEL. C'est la forme de `rl_duel.py::_rpc` et de `tests/conftest.py::rpc`. Un corps
    `{"params": {...}}` est accepte par HTTP mais le `runnerId` y est INVISIBLE : le host vise
    alors le runner << live >> et rend `stage null (need Running)` -- mesure #1018, deux fois."""
    body = json.dumps({"method": method, "args": [params],
                       "timeout": int(timeout * 1000)}).encode()
    req = urllib.request.Request(f"{HOTE}/api/scripts/{session_id()}/rpc", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout + 10) as r:
        out = json.loads(r.read().decode())
    if isinstance(out, dict) and out.get("error"):
        raise RuntimeError(f"{method}: {out['error']}")
    res = out.get("result", out) if isinstance(out, dict) else out
    if isinstance(res, dict) and res.get("ok") is False:
        raise RuntimeError(f"{method}: {res.get('error')}")
    return res


def amounts(res, tid: int, ability_id) -> list:
    """Les montants de degat de l'attaque = UN PAR COUP. Meme extraction que le test #204."""
    out = []
    for a in (res.get("actions") or []) if isinstance(res, dict) else []:
        for e in (a.get("events") or []):
            td = e.get("tags")
            if not td:
                continue
            td = json.loads(td) if isinstance(td, str) else td
            if "Amount" in td and td.get("Target_Id") == tid \
                    and td.get("Active_Ability_Type") == ability_id:
                out.append(int(td["Amount"]))
    return out


def build(phase: str, state_file: str, seed: str) -> int:
    peer = PEER_KRONOS if phase == "kronos" else PEER_ARMED
    spots = FAR if phase == "far" else NEAR
    argv = [sys.executable, "rl_duel.py", "build", "--seed", seed, "--board", BOARD,
            "--state-file", state_file,
            "--p-units", f"{ATTACKER},{peer},{peer}",
            "--explicit-stats", ATTACKER,
            "--a-units", TARGET,
            "--hp-target", "900000", "--armor-target", "0",
            "--crit", "0,0", "--block-target", "0,0",
            "--place", f"{ATTACKER}:{ATT_POS[0]},{ATT_POS[1]}"]
    if phase != "kronos":
        argv += ["--place", f"{peer}:{spots[0][0]},{spots[0][1]}",
                 "--place", f"{peer}:{spots[1][0]},{spots[1][1]}"]
    else:
        argv += ["--explicit-stats", PEER_KRONOS,
                 "--place", f"{peer}:{spots[0][0]},{spots[0][1]}",
                 "--place", f"{peer}:{spots[1][0]},{spots[1][1]}"]
    argv += ["--a-place", f"{TARGET}:{T_POS[0]},{T_POS[1]}"]
    p = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", errors="replace")
    for ln in (p.stdout or "").splitlines():
        if "runnerId=" in ln:
            return int(ln.split("runnerId=")[1].split()[0])
    print(p.stdout[-3000:] if p.stdout else "", p.stderr[-2000:] if p.stderr else "")
    raise SystemExit("[1018] build a echoue -- pas de runnerId")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=("armed", "far", "kronos"), required=True)
    ap.add_argument("--state-file", required=True)
    ap.add_argument("--seed", default="777")
    ap.add_argument("--runner", type=int, default=None,
                    help="re-joue sur un runner deja monte (sinon build)")
    ap.add_argument("--keep", action="store_true", help="ne PAS disposer le runner en sortie")
    a = ap.parse_args()

    rid = a.runner if a.runner is not None else build(a.phase, a.state_file, a.seed)
    print(f"[1018] phase={a.phase} runner={rid}")
    try:
        dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)
        units = [u for u in (dv.get("units") or []) if u.get("alive")]
        by_vis: dict = {}
        for u in units:
            by_vis.setdefault(u.get("visualId"), []).append(u)
        tgt = (by_vis.get(TARGET) or [None])[0]
        atts = by_vis.get(ATTACKER) or []
        if tgt is None or not atts:
            raise SystemExit(f"[1018] roster inattendu : visualIds={sorted(by_vis)}")

        def pos(u):
            p = u.get("pos") or {}
            return (p.get("col"), p.get("row"))

        tp = pos(tgt)
        # L'ATTAQUANT est celui des `tyranNpc1Hormagaunt` qui est ADJACENT a la cible.
        import hexgeo
        att = next((u for u in atts if hexgeo.distance(pos(u), tp) == 1), None)
        if att is None:
            raise SystemExit("[1018] aucun attaquant adjacent a la cible -- montage rate")
        aid, tid = att["id"], tgt["id"]

        # Le COMPTE natif attendu par le port, derive de l'etat LU (jamais suppose).
        ids = {"tyranNpc1Hormagaunt", "tyranNpc2RipperSwarm",
               "tyranSmnHormagaunt", "tyranSmnRipperSwarm"}
        peers = [u for u in units
                 if u["id"] not in (aid, tid)
                 and hexgeo.distance(pos(u), tp) == 1
                 and u.get("team") == att.get("team")
                 and u.get("visualId") in ids]
        print(f"[1018] attaquant u{aid}@{pos(att)}  cible u{tid}@{tp}")
        for u in units:
            print(f"        u{u['id']:<4} {u.get('visualId'):<28} team={u.get('team')} "
                  f"pos={pos(u)} d(cible)={hexgeo.distance(pos(u), tp)}")
        print(f"[1018] pairs comptes par le filtre unitIds = {len(peers)} "
              f"-> bonus attendu = +{len(peers)} coup(s)")

        norm = next((ab for ab in (att.get("abilities") or [])
                     if "NormalAttack" in str(ab.get("name") or "")), None)
        if norm is None:
            raise SystemExit(f"[1018] pas d'attaque normale sur u{aid}")
        res = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": aid, "targetId": tid,
            "abilityType": norm["id"]}}, 90)
        am = amounts(res, tid, norm["id"])
        print(f"[1018] RESULTAT phase={a.phase} : {len(am)} coup(s) natif(s) -> {am}")
        return 0
    finally:
        if a.runner is None and not a.keep:
            try:
                rpc("disposeRunner", {"runnerId": rid}, 30)
                print(f"[1018] runner {rid} dispose")
            except Exception as e:                                # noqa: BLE001
                print(f"[1018] dispose KO: {e}")


if __name__ == "__main__":
    raise SystemExit(main())
