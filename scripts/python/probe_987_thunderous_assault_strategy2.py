"""#987 (residus #977-r3 / #977-r4) -- exercer la STRATEGIE 2 de `1043 ThunderousAssault`.

LE GATE, ET LE LEVIER QUE LE RESIDU N'AVAIT PAS VU
--------------------------------------------------
`IdunBattle.AI.Playbook.Loki.ThunderousAssaultPlaybook$$GenerateStrategy2Action` :

    highest = GetHighestTileUtilityUnitCanMoveTo(unit)     # max sur `IBattleQuery` slot 0xb
    r       = GetPushableTargetOnHighestUtilityTile(unit, actionTile)
    if (r != null && r.Value >= highest) return GenerateAction(actionTile, r.Target, r.Value)
    return null

    GetHighestTileUtilityUnitCanMoveTo(unit):
        best = Fix64(0)
        foreach (p in battleQuery.<slot itf 0xb>(unit, null))   # LES TUILES DE MOUVEMENT
            best = max(best, GetUtility(Tile).EvaluateAttack(Base(unit, p.MainTile, ...)))
        return best

`#977-r3` cherchait un BOARD (? elevation plate autour des cibles, mais une tuile occupee dont
l'utilite depasse toutes les tuiles libres du caster ?). Or `highest` n'est pas une propriete du
board : c'est un **max sur l'ensemble des tuiles de MOUVEMENT du caster**. Reduire cet ensemble
reduit `highest` -- et `--unit-stat "<caster>:Movement=0"` le reduit a la seule tuile courante.
Le gate est un `>=`, pas un `>` : l'EGALITE suffit.

CE QUE CE PROBE MESURE
----------------------
Sur le MEME montage que `probe_977` (board `MC1_67`, seed 777, memes placements), avec et sans
`Movement=0` sur `templSwordBrother` :
  * `highest` et la meilleure cible poussable `(target, value)`, LUS AU PORT (les deux termes du
    gate, jamais un scalaire fitte) ;
  * la strategie 1 rend-elle `null` (condition d'entree dans la strategie 2) ;
  * l'action finalement emise, et par QUELLE strategie.

`ncEvaluate` est structurellement AVEUGLE a `1043` (il decode `Bucket+0x20`, que
`GenerateBucketWithMultipleStrategies` n'ecrit jamais) : l'oracle natif de ce playbook est
`aiDryRunAllUnits`, pas le capteur de bucket.

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
sys.path.insert(0, str(PYDIR))

import probe_977_faces_decision_kit as P977                        # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType  # noqa: E402

TA_ID = int(ActiveAbilityType.ThunderousAssault)        # 0x413 = 1043
CASTER = "templSwordBrother"


def _build(immobile: bool, seed=777, board="MC1_67"):
    sf = ROOT / "logs" / "runners" / ("p987ta-%s.json" % uuid.uuid4().hex[:8])
    sf.parent.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--board", board,
           "--state-file", str(sf), "--no-ai",
           "--p-units", "worldJakhal,worldEightbound,genesPatriarch,%s" % CASTER,
           "--p-mow", "deathCrawler",
           "--a-units", "necroWarden,necroDestroyer,tauCrisis,ultraTitus"]
    for p in P977._PLACE:
        cmd += ["--place", p]
    for p in P977._A_PLACE:
        cmd += ["--a-place", p]
    if immobile:
        # Le SEUL changement entre les deux bras : l'ensemble des tuiles de mouvement du caster,
        # donc l'ensemble sur lequel `GetHighestTileUtilityUnitCanMoveTo` prend son max.
        cmd += ["--unit-stat", "%s:Movement=0" % CASTER]
    proc = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not sf.exists():
        return None, (proc.stderr or proc.stdout or "")[-1200:]
    return int(json.loads(sf.read_text())["runnerId"]), None


def _measure(rpc, sid, rid, uid):
    """Les DEUX termes du gate, lus au PORT -- decomposition par etage, pas un scalaire."""
    import engine.playbook.noncomparable.thunderous_assault as TA

    # `_nc_ctx` rend `(contexte AI complet, NCContext)` : c'est le SECOND que les playbooks lisent.
    _c, nc = P977._nc_ctx(rpc, sid, rid, uid)
    pb = TA.ThunderousAssaultPlaybook()
    out = {}
    try:
        out["highest"] = pb.highest_tile_utility_unit_can_move_to(nc)
    except Exception as exc:
        out["highest"] = "KO %s: %s" % (type(exc).__name__, exc)
    try:
        r = pb.pushable_target_on_highest_utility_tile(nc, nc.origin)
        out["best_pushable"] = None if r is None else {"target": r[0], "value": r[1]}
    except Exception as exc:
        out["best_pushable"] = "KO %s: %s" % (type(exc).__name__, exc)
    for name in ("strategy1", "strategy2"):
        try:
            out[name] = getattr(pb, name)(nc, nc.origin)
        except Exception as exc:
            out[name] = "KO %s: %s" % (type(exc).__name__, exc)
    try:
        out["candidates"] = pb.generate_candidates(nc)
    except Exception as exc:
        out["candidates"] = "KO %s: %s" % (type(exc).__name__, exc)
    return out


def run(immobile: bool, verbose=True, seed=777, board="MC1_67") -> dict:
    rid, err = _build(immobile, seed=seed, board=board)
    if rid is None:
        return {"error": "build KO : %s" % err}
    # `_rpc_mod()` rend `(_resolve_session, _rpc)` : le premier RESOUT la session, le second est
    # l'appelant RPC. `_r(rpc, sid, ...)` attend donc `(fonction, id de session)`, dans cet ordre.
    _resolve, rpc = P977._rpc_mod()
    sid = _resolve()
    try:
        dv = P977._r(rpc, sid, "decisionView", {"runnerId": rid, "allAbilities": True})
        u = next((x for x in (dv.get("units") or []) if x.get("visualId") == CASTER), None)
        if u is None:
            return {"error": "%s absent du build" % CASTER}
        uid = int(u["id"])
        out = {"immobile": bool(immobile), "runner": rid, "uid": uid,
               "pos": u.get("pos"), "movement": (u.get("stats") or {}).get("Movement")}
        out.update(_measure(rpc, sid, rid, uid))
        try:
            dry = P977._r(rpc, sid, "aiDryRunAllUnits", {"runnerId": rid}, 240)
            unit = next((x for x in (dry.get("units") or [])
                         if int(x.get("unitId", -1)) == uid), None)
            out["native_proposed"] = None if unit is None else unit.get("proposed")
            out["native_proposes_1043"] = bool(unit is not None and any(
                int(m.get("abilityType", -1)) == TA_ID for m in (unit.get("proposed") or [])))
        except Exception as exc:
            out["native_proposed"] = "aiDryRun KO: %s" % exc
            out["native_proposes_1043"] = None
        if verbose:
            _report(out)
        return out
    finally:
        try:
            P977._r(rpc, sid, "disposeRunner", {"runnerId": rid}, 60)
        except Exception:
            pass


def _report(r):
    print("[987/1043] immobile=%-5s runner=%s uid=%s pos=%s Movement=%s"
          % (r["immobile"], r["runner"], r["uid"], r["pos"], r.get("movement")))
    print("           highest (max des tuiles de MOUVEMENT)   = %s" % r.get("highest"))
    print("           meilleure cible poussable (tuile OCCUPEE) = %s" % r.get("best_pushable"))
    print("           strategie1 = %s" % json.dumps(r.get("strategy1"), default=str)[:220])
    print("           strategie2 = %s" % json.dumps(r.get("strategy2"), default=str)[:220])
    print("           candidats du port = %s" % json.dumps(r.get("candidates"), default=str)[:260])
    print("           NATIF propose 1043 = %s | proposed=%s"
          % (r.get("native_proposes_1043"), json.dumps(r.get("native_proposed"))[:200]))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--arm", choices=("mobile", "immobile", "both"), default="both")
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--board", default="MC1_67")
    a = ap.parse_args()
    arms = ("mobile", "immobile") if a.arm == "both" else (a.arm,)
    for arm in arms:
        run(arm == "immobile", seed=a.seed, board=a.board)
    return 0


if __name__ == "__main__":
    sys.exit(main())
