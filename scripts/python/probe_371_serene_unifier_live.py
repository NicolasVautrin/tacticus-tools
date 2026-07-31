"""#371 -- MONTAGE LIVE du critere du lot G1 : un stat-mod SEEDE qui EXPIRE, confronte au natif.

CE QU'IL MESURE, et pourquoi ce montage-la. `SereneUnifierStormOfFire` (0x493 = 1171) est le SEUL
membre inscrit du gisement G1 qui porte un vrai timer -- posé par
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.SereneUnifierAbility$$CreateBehaviour` via
`AddStaticStatModifierEffect(units, 0x493, stat = 0 ATTACK, ConfigVar(8 = extraDmg),
TurnsFromRounds(1))`, phase `k = 0` du cycle `Modulo(PlayerTurnsStarted, Direct(3), Direct(k))`.

Le cycle donne au montage sa fenetre, et il est OBSERVE, pas suppose (mesure du 2026-07-31, seed
3711, board MC1_67, `tauAunShi` seul porteur du pool) :

    SenseOfStone(r2) -> SenseOfStone(r1) -> ZephyrsGrace(r2) -> ZephyrsGrace(r1)
                     -> StormOfFire(r2)  -> StormOfFire(r1)  -> SenseOfStone(r2) -> ...

=> `StormOfFire` VIT DEUX TOURS puis part, et la phase suivante (`1169 SenseOfStone`) ne pose AUCUN
stat-mod d'ATTACK. La fenetre « effet parti, aucun remplacant sur la meme stat » existe donc
naturellement : c'est elle qu'on mesure.

LE PIEGE QUE CE MONTAGE EVITE. `decisionView.effects` n'expose ni le stat ni le montant d'un effet
capte. Un test qui lirait ATTACK juste APRES la pose passerait au vert que l'effet soit declare ou
non (le residu opaque de `seed_unit_stats` reproduit toujours le `Current` capte). Ici on capture
l'etat AVEC l'effet actif, on le seede offline, puis on FAIT EXPIRER des DEUX cotes -- et c'est la
seule fenetre ou les deux mondes divergent.

ON MESURE SUR AUN'SHI LUI-MEME (source == porteur). Le buff arrose aussi les amis adjacents et les
amis T'au a <= 2, mais pour eux le seed porte le niveau d'ability du PORTEUR, pas du POSEUR (meme
limite que `RitesOfBattle`) : la magnitude offline n'y serait pas exacte, et le residu opaque
absorberait l'ecart. Le porteur-source est le regime ou l'attribution est EXACTE, donc le seul ou
`residu == 0` est une assertion legitime.

Usage : `python probe_371_serene_unifier_live.py [--seed 3711] [--board MC1_67] [--keep]`.
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

CARRIER = "tauAunShi"          # seul porteur `lineup` du passif SereneUnifier (1145) au pool
ALLY = "tauCrisis"             # 2e T'au : le buff l'arrose aussi -> temoin de propagation
ENEMIES = ("orksNob", "astraBullgryn")
STORM_OF_FIRE = 1171           # 0x493
SENSE_OF_STONE = 1169          # 0x491 -- phase k=1, DEJA portee (classe bespoke, aucun stat-mod)
BOARD = "MC1_67"
SEED = "3711"
MAX_TURNS = 14                 # le cycle fait 6 tours ; 14 laisse deux passages


def build_args() -> list[str]:
    """Arguments `rl_duel build` du montage. `--hp-*` eleves : les deux camps encaissent, la
    bataille dure assez pour voir le cycle passer. `--no-ai` : on pilote les fins de tour nous-memes,
    donc aucune action adverse ne peut tuer le porteur au milieu de la fenetre."""
    return ["--roster", "2",
            "--p-units", "%s,%s" % (CARRIER, ALLY),
            "--a-units", ",".join(ENEMIES),
            "--board", BOARD,
            "--hp-target", "60000", "--hp-player", "60000",
            "--no-ai"]


def _build_subprocess(seed: str) -> int:
    state = _ROOT / "logs" / ("_probe371-%d.json" % os.getpid())
    state.parent.mkdir(parents=True, exist_ok=True)
    state.unlink(missing_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", seed,
            "--state-file", str(state), *build_args()]
    p = subprocess.run(argv, cwd=str(_PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state.exists():
        raise RuntimeError("build runner KO (rl_duel): " + ((p.stderr or p.stdout or "")[-500:]))
    return json.loads(state.read_text())["runnerId"]


def _effect(dec, uid, effect_type):
    """(present, remaining) de `effect_type` sur `uid` dans un `decisionView`."""
    for u in (dec.get("units") or []):
        if u.get("id") == uid:
            for e in (u.get("effects") or []):
                if e.get("effectType") == effect_type:
                    return True, e.get("remaining")
    return False, None


def _attack(snap, uid):
    for u in (snap.get("units") or []):
        if u.get("entityId") == uid:
            return (u.get("stats") or {}).get("attack")
    return None


def run(rpc, seed: str = SEED, board: str = BOARD, build_runner=None, keep: bool = False) -> dict:
    """Monte le montage, mesure LIVE + MOTEUR, rend le dict. Libere le runner sauf `keep`."""
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
    from engine.runner.operations.turnflow import EndTurnOperation
    from engine.runner.snapshot import load_state

    extra = list(build_args())
    if board != BOARD:                                   # `--board` est deja dans build_args()
        extra[extra.index("--board") + 1] = board
    if build_runner is not None:
        rid = build_runner(seed, extra=[a for a in extra if a not in ("--board", board)] +
                           ["--board", board])["rid"]
    else:
        rid = _build_subprocess(seed)
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

    def endturn():
        return rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)

    d0 = dec()
    uid = next((u.get("id") for u in (d0.get("units") or [])
                if u.get("visualId") == CARRIER), None)
    if uid is None:
        out["why"] = "%s absent du live" % CARRIER
        return out
    out["uid"] = uid

    # --- 1. attendre la phase k = 0 du cycle (StormOfFire actif) --------------------------------
    phases = []
    d = d0
    for _ in range(MAX_TURNS):
        for et, nm in ((STORM_OF_FIRE, "StormOfFire"), (SENSE_OF_STONE, "SenseOfStone"), (1170, "ZephyrsGrace")):
            present, rem = _effect(d, uid, et)
            if present:
                phases.append("%s(r%s)" % (nm, rem))
                break
        else:
            phases.append("-")
        present, rem = _effect(d, uid, STORM_OF_FIRE)
        if present and isinstance(rem, int) and rem > 0:
            break
        endturn()
        d = dec()
    out["phases"] = phases
    present, rem = _effect(d, uid, STORM_OF_FIRE)
    if not (present and isinstance(rem, int) and rem > 0):
        out["why"] = ("%d (StormOfFire) jamais actif en %d tours -- phases vues : %s"
                      % (STORM_OF_FIRE, MAX_TURNS, phases))
        return out
    out["remaining"] = rem

    # --- 2. CAPTURE avec l'effet ACTIF (c'est la voie SEEDE) -------------------------------------
    cap_dec = d
    cap_ob = rpc("observeBattle", {"runnerId": rid}, 40)
    cap_snap = snap()
    out["attack_live_on"] = _attack(cap_snap, uid)
    out["extra_dmg_config"] = ability_var("SereneUnifier", "extraDmg",
                                          _passive_level(cap_snap, uid))

    # --- 3. la MEME capture rejouee DEUX FOIS : inscription PRESENTE puis RETIREE ----------------
    # C'est le bras discriminant. Sans lui, le montage ne prouverait rien : AVANT l'expiration les
    # deux mondes rendent la MEME valeur (le residu opaque reproduit toujours le `Current` capte).
    from engine.entities.effects.factory import EFFECT_CLASSES

    def _offline(declare: bool) -> dict:
        saved = EFFECT_CLASSES.pop("SereneUnifierStormOfFire", None)
        if declare and saved is not None:
            EFFECT_CLASSES["SereneUnifierStormOfFire"] = saved
        try:
            s = load_state(cap_dec, cap_ob, cap_snap, board=brd)
            e = s.get_entity(uid)
            c = e.get_component(StatsComponent) if e is not None else None
            if c is None or c.ctx is None:
                return {"why": "StatsComponent absent du State charge"}
            cx = c.ctx
            ps = dict(cx.stats.components[int(StatType.ATTACK)].modification.per_source)
            res = {
                "attack_on": int(cx.stat(StatType.ATTACK)),
                "statmod_keys": [str(k) for k in ps
                                 if isinstance(k, tuple) and k[:2] == ("statmod", STORM_OF_FIRE)],
                "attributed": sum(ps[k] for k in ps if isinstance(k, tuple)
                                  and k[:2] == ("statmod", STORM_OF_FIRE)),
                "opaque_residual": int(ps.get(CAPTURED_SOURCE, 0)),
            }
            for _ in range(int(rem)):
                EndTurnOperation.execute(s, advance=True)
            res["still_here"] = any(x.effect_type == STORM_OF_FIRE and not x.consumed
                                    for x in s.effects.by_unit.get(uid, []))
            res["attack_off"] = int(cx.stat(StatType.ATTACK))
            return res
        finally:
            if saved is not None:
                EFFECT_CLASSES["SereneUnifierStormOfFire"] = saved

    declared = _offline(True)
    if declared.get("why"):
        out["why"] = declared["why"]
        return out
    undeclared = _offline(False)
    out["attack_off_on"] = declared["attack_on"]
    out["statmod_keys"] = declared["statmod_keys"]
    out["attributed"] = declared["attributed"]
    out["opaque_residual"] = declared["opaque_residual"]
    out["off_still_here"] = declared["still_here"]
    out["attack_off_off"] = declared["attack_off"]
    out["undeclared"] = undeclared

    for _ in range(int(rem) + 2):
        endturn()
        if not _effect(dec(), uid, STORM_OF_FIRE)[0]:
            break
    out["live_still_here"] = _effect(dec(), uid, STORM_OF_FIRE)[0]
    out["attack_live_off"] = _attack(snap(), uid)

    out["ok"] = True
    return out


def _passive_level(snap, uid):
    for u in (snap.get("units") or []):
        if u.get("entityId") == uid:
            cfg = u.get("unitConfig") or {}
            return cfg.get("passiveAbilityLevel") or cfg.get("activeAbilityLevel")
    return None


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
    print("cycle observe : %s" % (" -> ".join(r.get("phases") or []),))
    if not r.get("ok"):
        return 1
    print("u%s %s -- StormOfFire actif, remaining=%s, extraDmg[config]=%s"
          % (r["uid"], CARRIER, r["remaining"], r["extra_dmg_config"]))
    print("  ATTACK avec l'effet   : live=%s  moteur=%s" % (r["attack_live_on"], r["attack_off_on"]))
    print("  attribution du seed   : cles=%s montant=%s residu_opaque=%s"
          % (r["statmod_keys"], r["attributed"], r["opaque_residual"]))
    print("  ATTACK apres expiration: live=%s  moteur=%s (effet present live=%s moteur=%s)"
          % (r["attack_live_off"], r["attack_off_off"], r["live_still_here"], r["off_still_here"]))
    d_live = (r["attack_live_on"] or 0) - (r["attack_live_off"] or 0)
    d_off = r["attack_off_on"] - r["attack_off_off"]
    print("  DELTA a l'expiration  : live=%s  moteur=%s" % (d_live, d_off))
    u = r.get("undeclared") or {}
    print("  [CONTRE-EPREUVE] MEME capture, inscription RETIREE :")
    print("     ATTACK avec l'effet=%s (identique -> INDISCERNABLE avant l'echeance)"
          % (u.get("attack_on"),))
    print("     residu opaque=%s  cles statmod=%s" % (u.get("opaque_residual"), u.get("statmod_keys")))
    print("     ATTACK apres expiration=%s (live=%s) -> ecart de %s"
          % (u.get("attack_off"), r["attack_live_off"],
             (u.get("attack_off") or 0) - (r["attack_live_off"] or 0)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
