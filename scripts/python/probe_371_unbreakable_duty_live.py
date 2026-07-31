"""#371 -- MONTAGE LIVE des DEUX self-buffs PERMANENTS de `UnbreakableDuty` (1251 / 1256).

CE QU'IL MESURE, et ce qu'il NE mesure PAS. `UnbreakableDuty_Health` (0x4e3) et
`UnbreakableDuty_Damage` (0x4e8) sont poses par
`IdunBattleLogic.Entities.Abilities.Active.Loki.UnbreakableDutyAbility$$ExecuteBehaviour` via
`AddStaticStatModifierEffectToOwner(<effectType>, <statType>, ConfigVar(<cle>), turns = NULL)` --
`turns` NULL, donc **PERMANENTS**. Le bug de DUREE du lot G1 ne les concerne pas : rien ne les fait
expirer, et un montage d'expiration serait du theatre. Ce que leur inscription au registre ferme est
l'**ATTRIBUTION** : sans elle, les deux contributions tombent dans le residu opaque
(`CAPTURED_SOURCE`) de `seed_unit_stats`, ou elles ne sont ni verifiables ni retirables.

D'ou l'observable de CE montage : **`residu == 0`**, c'est-a-dire l'egalite entre
  - la magnitude RE-DERIVEE de gameconfig (`UnbreakableDuty.variables.extraHp` / `.extraDmg` au
    niveau d'ability, scalees par `AbilityVariablesMultiplierPercentage`), et
  - le `statDelta` que le NATIF publie apres le cast.
Deux sources independantes : c'est une validation NON CIRCULAIRE de l'index de variable lu au
decompile (`ConfigVar(0x1e) = extraHp`, tranche par elimination sur les trois variables de
l'ability).

LA GATE DU NATIF, et comment le montage l'arme. Le behaviour entier est sous
`If(AmountIsEqualOrGreater(Count(UnitsWithTraits(Friends(AllDeadOrResurrectedUnits), [0x1a, 0x10])),
Direct(2)), ..., null)` -- il faut **>= 2 allies MORTS** portant l'un des deux traits (cf.
`UnbreakableDutyAbility$$GetAmountOfDeadImperialUnits`). Le montage les fabrique : deux allies
Black Templars mis a **1 PV** par `--unit-stat`, puis TUES en pilotant l'unite adverse
(`applyAction` ne verifie pas la propriete du `casterId`). Sans ces deux morts, le cast reussit et
ne pose RIEN -- un vert parfaitement vide.

Usage : `python probe_371_unbreakable_duty_live.py [--seed 3712] [--board MC1_67] [--keep]`.
Consommateur pytest : `tests/engine/runner/test_static_statmod_g1_live.py`.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

_PYDIR = Path(__file__).resolve().parent
_ROOT = _PYDIR.parent.parent

CARRIER = "templAncient"                      # seul porteur `lineup` d'UnbreakableDuty au pool
FODDER = ("templAggressor", "templChampion")  # les DEUX morts qu'exige la gate (Black Templars)
ENEMIES = ("orksNob", "astraBullgryn")
UD_HEALTH = 1251                              # 0x4e3 -- stat 5 HEALTH, ConfigVar(0x1e = extraHp)
UD_DAMAGE = 1256                              # 0x4e8 -- stat 0 ATTACK, ConfigVar(8  = extraDmg)
UNBREAKABLE_DUTY = 1061                       # ActiveAbilityType (lu live, jamais suppose)
BOARD = "MC1_67"
SEED = "3712"


def build_args() -> list[str]:
    stats = ";".join("%s:Health=1,RemainingHealth=1" % v for v in FODDER)
    return ["--roster", "3",
            "--p-units", ",".join((CARRIER,) + FODDER),
            "--a-units", ",".join(ENEMIES),
            "--board", BOARD,
            "--hp-player", "60000", "--hp-target", "60000",
            "--unit-stat", stats,
            "--no-ai"]


def _build_subprocess(seed: str) -> int:
    state = _ROOT / "logs" / ("_probe371ud-%d.json" % os.getpid())
    state.parent.mkdir(parents=True, exist_ok=True)
    state.unlink(missing_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", seed,
            "--state-file", str(state), *build_args()]
    p = subprocess.run(argv, cwd=str(_PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state.exists():
        raise RuntimeError("build runner KO (rl_duel): " + ((p.stderr or p.stdout or "")[-500:]))
    return json.loads(state.read_text())["runnerId"]


def _stat(snap, uid, key):
    for u in (snap.get("units") or []):
        if u.get("entityId") == uid:
            return (u.get("stats") or {}).get(key)
    return None


def _delta(snap, uid, key):
    for u in (snap.get("units") or []):
        if u.get("entityId") == uid:
            return int((u.get("statDelta") or {}).get(key, 0) or 0)
    return None


def _has_effect(dec, uid, effect_type):
    for u in (dec.get("units") or []):
        if u.get("id") == uid:
            return any(e.get("effectType") == effect_type for e in (u.get("effects") or []))
    return False


def _normal_ability(dec, uid):
    for u in (dec.get("units") or []):
        if u.get("id") == uid:
            for a in (u.get("abilities") or []):
                if a.get("kind") == "normal":
                    return a.get("id")
    return None


def run(rpc, seed: str = SEED, board: str = BOARD, build_runner=None, keep: bool = False) -> dict:
    r = _run(rpc, seed, board, build_runner)
    if not keep and r.get("rid") is not None:
        try:
            rpc("disposeRunner", {"runnerId": r["rid"]}, 40)
        except Exception:                                # pragma: no cover (nettoyage best-effort)
            pass
    return r


def _run(rpc, seed: str, board: str, build_runner) -> dict:
    from engine.entities.effects.magnitude import ability_var
    from engine.entities.pathfinding.board import Board
    from engine.entities.stats import StatType, CAPTURED_SOURCE
    from engine.runner.components import StatsComponent
    from engine.runner.snapshot import load_state

    extra = list(build_args())
    extra[extra.index("--board") + 1] = board
    rid = (build_runner(seed, extra=extra)["rid"] if build_runner is not None
           else _build_subprocess(seed))
    out = {"rid": rid, "seed": seed, "board": board, "ok": False, "why": None}

    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        out["why"] = "boardGraph indispo"
        return out
    brd = Board(bg["tiles"], adjacency="evenq")

    def dec():
        return rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)

    def snap():
        return rpc("combatSnapshot", {"runnerId": rid}, 60)

    def act(action, timeout=60):
        return rpc("applyAction", {"runnerId": rid, "action": action}, timeout)

    d = dec()
    ids = {u.get("visualId"): u.get("id") for u in (d.get("units") or [])}
    missing = [v for v in (CARRIER,) + FODDER + ENEMIES if v not in ids]
    if missing:
        out["why"] = "unites absentes du live : %s" % (missing,)
        return out
    out["ids"] = dict(ids)
    carrier = ids[CARRIER]
    owner = next(u.get("owner") for u in (d.get("units") or []) if u.get("id") == carrier)

    # --- 1. armer la GATE : tuer les DEUX allies a 1 PV avec les unites adverses ----------------
    # Positions DRIVEES des DEUX camps (`applyAction` ne verifie pas la propriete du `unitId`) :
    # une victime et son killer sur deux couples de tuiles ADJACENTES choisis, un killer par
    # victime (une unite qui a deja bouge ne peut plus se replacer dans le meme tour).
    PAIRS = (((3, 3), (2, 3)), ((3, 6), (2, 6)))
    for vis, (vtile, ktile) in zip(FODDER, PAIRS):
        victim, killer = ids[vis], ids[ENEMIES[FODDER.index(vis)]]
        mv = act({"kind": "move", "unitId": victim, "to": {"col": vtile[0], "row": vtile[1]}})
        mk = act({"kind": "move", "unitId": killer, "to": {"col": ktile[0], "row": ktile[1]}})
        ab = _normal_ability(dec(), killer)
        if ab is None:
            out["why"] = "pas d'attaque normale resolue pour le killer u%s" % (killer,)
            return out
        res = act({"kind": "ability", "casterId": killer, "targetId": victim,
                   "abilityType": ab}, 90)
        out.setdefault("kills", []).append(
            {"visualId": vis, "moved_victim": bool(isinstance(mv, dict) and mv.get("ok")),
             "moved_killer": bool(isinstance(mk, dict) and mk.get("ok")),
             "hit": bool(isinstance(res, dict) and res.get("ok")),
             "hp": _stat(snap(), victim, "health")})

    d = dec()
    dead = [u.get("visualId") for u in (d.get("units") or [])
            if u.get("visualId") in FODDER and u.get("isDead")]
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    dead_ob = [u.get("visualId") for u in (ob.get("units") or [])
               if u.get("visualId") in FODDER and u.get("isDead")]
    out["dead"] = sorted(set(dead) | set(dead_ob))
    if len(out["dead"]) < 2:
        out["why"] = ("gate NON ARMEE : %d allie(s) mort(s) sur les 2 exiges par "
                      "AmountIsEqualOrGreater(Count(...), Direct(2))" % (len(out["dead"]),))
        return out

    # --- 2. rendre la main au camp du porteur, puis CASTER -------------------------------------
    for _ in range(6):
        if dec().get("currentPlayer") == owner:
            break
        act({"kind": "endturn"}, 40)
    if dec().get("currentPlayer") != owner:
        out["why"] = "impossible de rendre la main au camp du porteur"
        return out

    snap_b = snap()
    out["before"] = {"attack": _stat(snap_b, carrier, "attack"),
                     "health": _stat(snap_b, carrier, "health"),
                     "d_attack": _delta(snap_b, carrier, "attack"),
                     "d_health": _delta(snap_b, carrier, "health")}
    res = act({"kind": "ability", "casterId": carrier, "targetId": carrier,
               "abilityType": UNBREAKABLE_DUTY}, 90)
    out["cast_ok"] = bool(isinstance(res, dict) and res.get("ok"))
    if not out["cast_ok"]:
        out["why"] = "cast UnbreakableDuty refuse : %s" % (str(res)[:200],)
        return out

    dec_a, snap_a = dec(), snap()
    ob_a = rpc("observeBattle", {"runnerId": rid}, 40)
    out["after"] = {"attack": _stat(snap_a, carrier, "attack"),
                    "health": _stat(snap_a, carrier, "health"),
                    "d_attack": _delta(snap_a, carrier, "attack"),
                    "d_health": _delta(snap_a, carrier, "health")}
    out["effects"] = {"1251": _has_effect(dec_a, carrier, UD_HEALTH),
                      "1256": _has_effect(dec_a, carrier, UD_DAMAGE)}
    if not (out["effects"]["1251"] and out["effects"]["1256"]):
        out["why"] = "les deux effets ne sont pas poses : %s" % (out["effects"],)
        return out

    # --- 3. magnitudes RE-DERIVEES de gameconfig (source INDEPENDANTE du delta natif) -----------
    lvl, mult = None, 100
    for u in (snap_a.get("units") or []):
        if u.get("entityId") == carrier:
            cfg = u.get("unitConfig") or {}
            lvl = cfg.get("activeAbilityLevel")
            mult = cfg.get("abilityVariablesMultiplier") or 100
    out["level"], out["multiplier"] = lvl, mult
    out["config"] = {
        "extraHp": ability_var("UnbreakableDuty", "extraHp", lvl, multiplier_pct=mult),
        "extraDmg": ability_var("UnbreakableDuty", "extraDmg", lvl, multiplier_pct=mult)}

    # --- 4. SEED offline de la capture post-cast : attribution par-source vs residu opaque ------
    from engine.entities.effects.factory import EFFECT_CLASSES

    def _offline(declare: bool) -> dict:
        saved = {n: EFFECT_CLASSES.pop(n, None)
                 for n in ("UnbreakableDuty_Health", "UnbreakableDuty_Damage")}
        if declare:
            for n, k in saved.items():
                if k is not None:
                    EFFECT_CLASSES[n] = k
        try:
            s = load_state(dec_a, ob_a, snap_a, board=brd)
            e = s.get_entity(carrier)
            c = e.get_component(StatsComponent) if e is not None else None
            if c is None or c.ctx is None:
                return {"why": "StatsComponent absent"}
            cx = c.ctx
            r = {"attack": int(cx.stat(StatType.ATTACK)), "health": int(cx.stat(StatType.HEALTH))}
            for label, stat, et in (("attack", StatType.ATTACK, UD_DAMAGE),
                                    ("health", StatType.HEALTH, UD_HEALTH)):
                ps = dict(cx.stats.components[int(stat)].modification.per_source)
                r["%s_attributed" % label] = sum(
                    ps[k] for k in ps if isinstance(k, tuple) and k[:2] == ("statmod", et))
                r["%s_opaque" % label] = int(ps.get(CAPTURED_SOURCE, 0))
            return r
        finally:
            for n, k in saved.items():
                if k is not None:
                    EFFECT_CLASSES[n] = k

    out["declared"] = _offline(True)
    out["undeclared"] = _offline(False)
    out["ok"] = True
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seed", default=SEED)
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()

    import rl_collect_batch as R
    sid = R._resolve_session()

    def _unwrap(x):
        return x.get("result") if isinstance(x, dict) and "result" in x else x

    def rpc(method, body=None, timeout=90):
        return _unwrap(R._rpc(sid, method, [body] if body is not None else [], timeout=timeout))

    r = run(rpc, seed=a.seed, board=a.board, keep=a.keep)
    print("runner=%s ok=%s why=%s" % (r.get("rid"), r.get("ok"), r.get("why")))
    print("morts armant la gate : %s" % (r.get("dead"),))
    if not r.get("ok"):
        return 1
    b, af, cfg = r["before"], r["after"], r["config"]
    print("cast UnbreakableDuty(%d) par u%s (niveau %s, multiplier %s%%)"
          % (UNBREAKABLE_DUTY, r["ids"][CARRIER], r["level"], r["multiplier"]))
    print("  effets poses : 1251=%s 1256=%s" % (r["effects"]["1251"], r["effects"]["1256"]))
    print("  ATTACK  %s -> %s  (statDelta %s -> %s)  | extraDmg[config] = %s"
          % (b["attack"], af["attack"], b["d_attack"], af["d_attack"], cfg["extraDmg"]))
    print("  HEALTH  %s -> %s  (statDelta %s -> %s)  | extraHp[config]  = %s"
          % (b["health"], af["health"], b["d_health"], af["d_health"], cfg["extraHp"]))
    d, u = r["declared"], r["undeclared"]
    print("  [SEED offline, INSCRIT]     attack attribue=%s residu=%s | health attribue=%s residu=%s"
          % (d["attack_attributed"], d["attack_opaque"], d["health_attributed"], d["health_opaque"]))
    print("  [SEED offline, NON INSCRIT] attack attribue=%s residu=%s | health attribue=%s residu=%s"
          % (u["attack_attributed"], u["attack_opaque"], u["health_attributed"], u["health_opaque"]))
    print("  (les stats COURANTES sont identiques dans les deux bras : %s/%s vs %s/%s -- c'est bien "
          "l'ATTRIBUTION qui change, pas la valeur)"
          % (d["attack"], d["health"], u["attack"], u["health"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
