#!/usr/bin/env python
"""Probe #362 -- ce que `ncPlaybookPredict` capture VRAIMENT sur `1132 KillMaimBurn`.

LA QUESTION BINAIRE
-------------------
Le residu `#356-r1` a inscrit une divergence : natif `(8536, 8536, 4)` contre port `(86, 129, 1)`,
avec la lecture « prediction BORNEE AUX PV MAX de la cible ». Ce probe tranche *d'ou vient cet
event*, parce que le decompile en propose une origine tres differente :

`IdunBattle.AI.Playbook.Loki.KillMaimBurnPlaybook$$EvaluateNonComparable` ouvre sa boucle par
`IdunBattle.AI.Playbook.BasePlaybook$$WillNormalAttackKill(entities)` -- `continue` si vrai. Or ce
corps-la CONSTRUIT lui-meme un `IdunBattle.AI.Playbook.ProbableDamageEvent$$.ctor` (il predit
l'attaque NORMALE par `IBattleQuery` slot 0x21 puis lit
`IdunBattle.Core.Services.DamagePredictionResult$$get_WillBeKill`). L'oracle, ancre precisement sur
ce ctor, capture donc AUSSI les events du GATE -- avec le MEME `targetId` que l'event d'ability.

Deux predictions falsifiables en decoulent :
  * `appliedHits` de l'event capte quand le gate mord = les coups de l'ARME NORMALE du caster
    (`worldKharn.weapons[0].hits` = **4**), et non `nrOfHits` de l'ability (= **1**) ;
  * si le gate mord sur TOUTES les cibles, le bucket est VIDE et la capture ne contient QUE des
    events d'attaque normale -- le natif n'a construit AUCUNE prediction d'ability.

REGIME PILOTE, PAS SUBI
-----------------------
Le probe joue le MEME montage a deux regimes, et le seul curseur est les PV de la cible :
  * `gate=ON`  -- cible aux PV du seed : la normale de Kharn sur-tue -> `WillBeKill` vrai ;
  * `gate=OFF` -- `--unit-stat <victime>:Health=...,RemainingHealth=...` : la meme normale ne tue
    plus -> le natif poursuit et construit l'event d'ABILITY apres celui du gate.
Chaque cote est confronte a son pendant PORTE (`make_normal_attack_predictions` pour la normale,
`generate_multi_hit_attack_prediction` pour l'ability), et l'ordre de construction est verifie.

ASCII only (cp1252). Usage (depuis scripts/python) :
    python probe_362_kill_maim_burn_nc.py
    python probe_362_kill_maim_burn_nc.py --level 3 --victim-hp 400000 --json
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

from rl_collect_batch import _resolve_session, _rpc                          # noqa: E402
from probe_344_ability_damage_average import (_ctx, _nc_context, _place_ring,  # noqa: E402
                                              _view)

CASTER = "worldKharn"
ABILITY = 1132
ABILITY_NAME = "KillMaimBurn"
VICTIM = "necroWarden"
FILLER_P = "astraBullgryn"
FILLER_A = "ultraTitus"
BOARD = "MC1_67"
CENTER = (3, 4)


def _r(sid, m, b, t=90):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def _build(state_file: Path, seed: int, level: int, victim_hp: int | None,
           filler_a_hp: int | None = None) -> int:
    """`rl_duel build` -- board CHOISI, niveau d'ability PILOTE, PV de la cible PILOTES.

    `victim_hp` est le SEUL curseur entre les deux regimes : il ne touche ni la formule de degat de
    l'ability, ni l'armure, ni le crit -- il deplace uniquement le verdict de
    `DamagePredictionResult$$get_WillBeKill` sur l'attaque NORMALE du caster."""
    state_file.unlink(missing_ok=True)
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
           "--state-file", str(state_file), "--board", BOARD, "--rank", "17",
           "--p-units", "%s,%s" % (CASTER, FILLER_P),
           "--a-units", "%s,%s" % (VICTIM, FILLER_A),
           "--unit-stat", "%s:ActiveAbilityLevel=%d,AbilityVariablesMultiplierPercentage=100"
                          % (CASTER, level),
           "--crit", "0,0", "--block-target", "0,0", "--armor-target", "0", "--no-ai"]
    if victim_hp is not None:
        cmd += ["--unit-stat", "%s:Health=%d,RemainingHealth=%d" % (VICTIM, victim_hp, victim_hp)]
    if filler_a_hp is not None:
        cmd += ["--unit-stat", "%s:Health=%d,RemainingHealth=%d"
                               % (FILLER_A, filler_a_hp, filler_a_hp)]
    proc = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not state_file.exists():
        raise RuntimeError("build KO : %s" % ((proc.stderr or proc.stdout or "")[-900:]))
    return int(json.loads(state_file.read_text())["runnerId"])


def _measure(sid, sf, seed, level, victim_hp, label) -> dict:
    rid = None
    try:
        rid = _build(sf, seed, level, victim_hp)
        dv = _view(sid, rid)
        ids = {}
        for v in (CASTER, FILLER_P, VICTIM, FILLER_A):
            u = next((x for x in (dv.get("units") or [])
                      if x.get("visualId") == v and x.get("alive")), None)
            if u is None:
                return {"label": label, "error": "unite absente du build : %s" % v}
            ids[v] = int(u["id"])
        _place_ring(sid, rid, ids, CASTER, CENTER)
        cid, tid = ids[CASTER], ids[VICTIM]
        ctx, _dv2 = _ctx(sid, rid, cid)
        scene = ctx.scene
        mp = ctx.me.get("pos") or {}
        here = (mp.get("col"), mp.get("row"))

        # -- NATIF : la capture BRUTE, sans filtre (c'est elle l'objet du probe) ------------------
        nat = _r(sid, "ncPlaybookPredict", {"runnerId": rid, "unitId": cid,
                                            "abilityType": ABILITY, "via": "evaluate"}, 240)
        caps = [{"targetId": e.get("targetId"), "healthDmgMin": e.get("healthDmgMin"),
                 "healthDmgMax": e.get("healthDmgMax"), "appliedHits": e.get("appliedHits")}
                for e in (nat.get("captured") or [])]

        # -- PORT : les DEUX predictions que le natif peut construire pour la cible principale ----
        from engine.playbook.prediction import (generate_multi_hit_attack_prediction,
                                                make_normal_attack_predictions)
        na = make_normal_attack_predictions(scene, cid, tid, here)
        na_t = None
        na_kill = None
        if na is not None:
            p = na.prediction
            na_t = (p.accurate_health_damage.min, p.accurate_health_damage.max, p.applied_hits)
            na_kill = bool(p.will_be_kill())
        ab = generate_multi_hit_attack_prediction(scene, cid, tid, ABILITY, ABILITY_NAME,
                                                  attack_pos=here)
        ab_t = None
        if ab is not None:
            ab_t = (ab.accurate_health_damage.min, ab.accurate_health_damage.max, ab.applied_hits)

        out = {"label": label, "runner": rid, "level": level, "victim_hp_forced": victim_hp,
               "casterId": cid, "targetId": tid, "here": here,
               "hp": scene.hp(tid), "hpmax": scene.hpmax(tid),
               "playbookClass": nat.get("playbookClass"), "evalName": nat.get("evalName"),
               "abilityState": nat.get("abilityState"),
               "capturedCount": nat.get("capturedCount"), "captured": caps,
               "bucket": nat.get("bucket"), "bucketUtil": nat.get("bucketUtil"),
               "bucketAction": nat.get("bucketAction"),
               "port_normal_attack": na_t, "port_normal_attack_will_be_kill": na_kill,
               "port_ability": ab_t}
        if nat.get("error"):
            out["ncError"] = nat["error"]
        return out
    finally:
        if rid is not None:
            _r(sid, "disposeRunner", {"runnerId": rid}, 30)


def _argmax_arm(sid, sf, seed, level, hp_survivor, label) -> dict:
    """GENERALISATION : le gate CHANGE-T-IL la cible choisie ?

    Deux ennemis sur l'anneau, un seul curseur : les PV. `necroWarden` survit a l'attaque normale de
    Kharn (PV forces), `ultraTitus` ne survit pas (PV du seed). Sans le gate, le port scorerait les
    DEUX et prefererait le mourant (le composite d'utilite prime le kill sur). Avec le gate, le natif
    et le port ne scorent QUE le survivant : la cible EMISE change, pas seulement un scalaire."""
    rid = None
    try:
        rid = _build(sf, seed, level, hp_survivor)
        dv = _view(sid, rid)
        ids = {}
        for v in (CASTER, FILLER_P, VICTIM, FILLER_A):
            u = next((x for x in (dv.get("units") or [])
                      if x.get("visualId") == v and x.get("alive")), None)
            if u is None:
                return {"label": label, "error": "unite absente du build : %s" % v}
            ids[v] = int(u["id"])
        _place_ring(sid, rid, ids, CASTER, CENTER)
        cid = ids[CASTER]
        foes = {VICTIM: ids[VICTIM], FILLER_A: ids[FILLER_A]}
        ctx, _dv2 = _ctx(sid, rid, cid)
        scene = ctx.scene
        mp = ctx.me.get("pos") or {}
        here = (mp.get("col"), mp.get("row"))

        nat = _r(sid, "ncPlaybookPredict", {"runnerId": rid, "unitId": cid,
                                            "abilityType": ABILITY, "via": "evaluate"}, 240)

        from engine.playbook import noncomparable as NCPB
        from engine.playbook.prediction import make_normal_attack_predictions
        from engine.playbook.probable_damage_event import (ProbableDamageEvent,
                                                           calculate_utility_from_damage_event)
        pb = NCPB.playbook_for(ABILITY)
        nc = _nc_context(scene, ctx, cid, here)

        with_gate, without_gate, kill = {}, {}, {}
        for name, tid in foes.items():
            with_gate[name] = pb.evaluate_non_comparable(here, tid, nc)
            na = make_normal_attack_predictions(scene, cid, tid, here)
            kill[name] = None if na is None else bool(na.prediction.will_be_kill())
            dp = pb._ability_prediction(here, tid, nc)   # CONTREFACTUEL : le gate retire
            without_gate[name] = (None if dp is None else calculate_utility_from_damage_event(
                ProbableDamageEvent(target=tid, prediction=dp), nc.wt, scene.hpmax(tid)))

        def _argmax(d):
            xs = [(k, v) for k, v in d.items() if v is not None and v >= pb.MIN_UTILITY]
            return max(xs, key=lambda kv: kv[1])[0] if xs else None

        return {"label": label, "runner": rid, "level": level, "casterId": cid, "here": here,
                "foes": foes, "hp": {k: scene.hp(v) for k, v in foes.items()},
                "willBeKill": kill,
                "bucket": nat.get("bucket"), "bucketUtil": nat.get("bucketUtil"),
                "bucketAction": nat.get("bucketAction"),
                "capturedCount": nat.get("capturedCount"),
                "port_with_gate": with_gate, "port_without_gate": without_gate,
                "argmax_with_gate": _argmax(with_gate),
                "argmax_without_gate": _argmax(without_gate)}
    finally:
        if rid is not None:
            _r(sid, "disposeRunner", {"runnerId": rid}, 30)


def run(seed: int = 36201, level: int = 3, victim_hp: int = 400000,
        arg_level: int = 50, arg_hp: int = 30000,
        state_file=None, verbose: bool = True) -> dict:
    sid = _resolve_session()
    sf = Path(state_file) if state_file else (PYDIR.parents[1] / "logs" / "p362.json")
    sf.parent.mkdir(parents=True, exist_ok=True)

    on = _measure(sid, sf, seed, level, None, "gate=ON  (PV du seed)")
    off = _measure(sid, sf, seed + 1, level, victim_hp, "gate=OFF (PV forces)")
    arg = _argmax_arm(sid, sf, seed + 2, arg_level, arg_hp,
                      "argmax (1 survivant, 1 mourant)")

    if verbose:
        print("[362] montage : %s / %s (%d) -> %s sur %s, anneau centre en %s"
              % (CASTER, ABILITY_NAME, ABILITY, VICTIM, BOARD, tuple(CENTER)))
        for arm in (on, off):
            print("\n=== %s ===" % arm["label"])
            if arm.get("error"):
                print("  ERREUR : %s" % arm["error"])
                continue
            print("  playbook natif        : %s (%s)" % (arm["playbookClass"], arm["evalName"]))
            print("  cible %s : hp=%s hpmax=%s" % (arm["targetId"], arm["hp"], arm["hpmax"]))
            print("  capture BRUTE (%s events) :" % arm["capturedCount"])
            for e in arm["captured"]:
                print("      tgt=%-4s (%s, %s, %s coups)"
                      % (e["targetId"], e["healthDmgMin"], e["healthDmgMax"], e["appliedHits"]))
            print("  bucket                : %s util=%s action=%s"
                  % (arm.get("bucket"), arm.get("bucketUtil"), arm.get("bucketAction")))
            print("  port attaque NORMALE  : %s  willBeKill=%s"
                  % (arm["port_normal_attack"], arm["port_normal_attack_will_be_kill"]))
            print("  port ability 1132     : %s" % (arm["port_ability"],))
        print("\n=== %s ===" % arg["label"])
        if arg.get("error"):
            print("  ERREUR : %s" % arg["error"])
        else:
            print("  niveau=%d  ids=%s  hp=%s  willBeKill=%s"
                  % (arg["level"], arg["foes"], arg["hp"], arg["willBeKill"]))
            print("  natif bucket          : util=%s action=%s (capture=%s events)"
                  % (arg["bucketUtil"], arg["bucketAction"], arg["capturedCount"]))
            print("  port AVEC gate        : %s -> argmax=%s"
                  % (arg["port_with_gate"], arg["argmax_with_gate"]))
            print("  port SANS gate (contrefactuel) : %s -> argmax=%s"
                  % (arg["port_without_gate"], arg["argmax_without_gate"]))

    # VERDICTS derives de la mesure (jamais ecrits d'avance) :
    mains_on = [e for e in (on.get("captured") or []) if e["targetId"] == on.get("targetId")]
    mains_off = [e for e in (off.get("captured") or []) if e["targetId"] == off.get("targetId")]
    t_on = [(e["healthDmgMin"], e["healthDmgMax"], e["appliedHits"]) for e in mains_on]
    t_off = [(e["healthDmgMin"], e["healthDmgMax"], e["appliedHits"]) for e in mains_off]
    gate_event_is_normal_attack = bool(t_on) and t_on[0] == on.get("port_normal_attack")
    gate_on_skips = (on.get("port_normal_attack_will_be_kill") is True
                     and len(t_on) == 1 and on.get("bucket") == "empty")
    gate_off_builds_both = (off.get("port_normal_attack_will_be_kill") is False
                           and len(t_off) == 2
                           and t_off[0] == off.get("port_normal_attack")
                           and t_off[1] == off.get("port_ability"))
    # Le gate DISCRIMINE si (a) le contrefactuel SANS gate designerait une AUTRE cible, et
    # (b) l'utilite que le natif a reellement mise au bucket est celle du survivant, pas celle du
    # mourant. C'est `bucketUtil` (Fix64 du `BucketAction`) qui tranche, pas `bucketAction` : son
    # champ `targetLow` est le dword bas d'un POINTEUR d'entite, pas un unitId -- il n'identifie
    # rien de comparable offline (mesure : 705051616).
    def _close(a, b, tol=1e-6):
        return (a is not None and b is not None
                and abs(float(a) - float(b)) <= tol * max(1.0, abs(float(b))))

    nat_util = arg.get("bucketUtil")
    u_gate = (arg.get("port_with_gate") or {}).get(arg.get("argmax_with_gate"))
    u_nogate = (arg.get("port_without_gate") or {}).get(arg.get("argmax_without_gate"))
    argmax_agrees = _close(nat_util, u_gate) and not _close(nat_util, u_nogate)
    gate_changes_target = (arg.get("argmax_with_gate") is not None
                           and arg.get("argmax_without_gate") is not None
                           and arg["argmax_with_gate"] != arg["argmax_without_gate"])
    ok = bool(gate_event_is_normal_attack and gate_on_skips and gate_off_builds_both
              and argmax_agrees and gate_changes_target)

    if verbose:
        print("\n=== VERDICT ===")
        print("  l'event capte quand le gate mord EST l'attaque normale du port : %s"
              % gate_event_is_normal_attack)
        print("  gate ON  -> 1 seul event + bucket vide (cible sautee)          : %s" % gate_on_skips)
        print("  gate OFF -> [normale, ability] dans cet ordre, port == natif   : %s"
              % gate_off_builds_both)
        print("  argmax : bucketUtil natif == utilite du port AVEC gate         : %s "
              "(natif=%s avec-gate=%s sans-gate=%s)"
              % (argmax_agrees, nat_util, u_gate, u_nogate))
        print("  le gate CHANGE la cible (contrefactuel sans gate != avec)      : %s"
              % gate_changes_target)
        print("  -> %s" % ("OK" if ok else "ECHEC"))

    return {"ok": ok, "gate_on": on, "gate_off": off, "argmax": arg,
            "gate_event_is_normal_attack": gate_event_is_normal_attack,
            "gate_on_skips": gate_on_skips, "gate_off_builds_both": gate_off_builds_both,
            "argmax_agrees": argmax_agrees, "gate_changes_target": gate_changes_target}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=36201)
    ap.add_argument("--level", type=int, default=3)
    ap.add_argument("--victim-hp", type=int, default=400000,
                    help="PV forces de la cible au bras gate=OFF (seul curseur entre les regimes)")
    ap.add_argument("--arg-level", type=int, default=50,
                    help="niveau d'ability du bras argmax (assez haut pour depasser MIN_UTILITY)")
    ap.add_argument("--arg-hp", type=int, default=30000,
                    help="PV du SURVIVANT au bras argmax : > degat de la normale, mais assez bas "
                         "pour que l'utilite de l'ability reste au-dessus de MIN_UTILITY")
    ap.add_argument("--state-file", default=None)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    out = run(seed=a.seed, level=a.level, victim_hp=a.victim_hp, arg_level=a.arg_level,
              arg_hp=a.arg_hp, state_file=a.state_file)
    if a.json:
        print(json.dumps(out, indent=1, default=str))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
