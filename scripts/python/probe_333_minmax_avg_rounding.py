#!/usr/bin/env python
"""Probe #333 -- `IdunBattle.Core.Services.MinMaxDamage$$Avg` ARRONDIT, et il arrondit VERS LE PAIR.

CE QUE LE DECOMPILE DIT (`rnca9r7q6c`, lu VERBATIM -- rien de deduit)
--------------------------------------------------------------------

    IdunBattle.Core.Services.MinMaxDamage$$Avg(this) =
        Fix64.op_Explicit( Fix64.Round(
            Fix64.op_Division( Fix64.op_Implicit(this.Min@+0x8) + Fix64.op_Implicit(this.Max@+0xc),
                               Fix64.op_Implicit(2) ),
            midpointRounding = 0 ) )

    FixMath.NET.Fix64$$Round(value, midpointRounding) :
        integral = value & 0xffffffff00000000 ; frac = value & 0xffffffff
        frac <  0x80000000                            -> integral
        frac == 0x80000000 && midpointRounding == 0   -> ((value >> 0x20) & 1) == 0 ? integral
                                                                                    : integral + One
        frac == 0x80000000 && midpointRounding != 0   -> integral < Zero ? integral : integral + One
        sinon                                         -> integral + One

`One` = statics+0x20 = 0x100000000 et `Zero` = statics+0x28 = 0 (`FixMath.NET.Fix64$$.cctor`).
`midpointRounding = 0` prend donc la branche de PARITE = `MidpointRounding.ToEven`.

Les DEUX consommateurs du rail de degat passent par la :
`IdunBattle.AI.Utilities.DamageUtility$$GetHealthDamage` = `Fix64(Avg(AccurateHealthDamage@+0x40))`
(sauf `LimitedByMinHp@+0x88` -> `CurrentHealth@+0x00`) et
`IdunBattle.AI.Utilities.DamageUtility$$GetShieldDamage` = `Avg(AccurateShieldDamage@+0x50)` ;
`...DamageUtility.u003CEvaluateAttackInStepsu003Ed__2$$MoveNext` les SOMME apres coup (deux
arrondis, pas un).

CE QUE CE PROBE MESURE, ET POURQUOI IL FAUT DEUX BRAS
----------------------------------------------------
Un `.5` EXACT n'existe que si `Min + Max` est IMPAIR, et c'est le SEUL regime ou les modes
d'arrondi se separent. Pire : sur un `.5` a partie entiere IMPAIRE, demi-vers-le-pair et
demi-vers-le-haut donnent la MEME valeur. Une mesure qui ne verrait que ce cote-la (c'est
exactement ce qu'avait #329 : `3771 + 5652`, floor `4711`, IMPAIR) ne dit RIEN du mode.

On PILOTE donc la parite au lieu de la subir. Levier : `AccurateHealthDamage` est CAPE aux PV de
la cible, et `rl_duel build --hp-target H` pose `Health = RemainingHealth = H` (et `Armor = 0`).
Avec `rawMin < H < rawMax`, les bornes valent exactement `[rawMin, H]` -- donc **H choisit la
parite de la somme ET celle de la partie entiere**.

  bras UP   : `H` tel que `rawMin + H` IMPAIR et `floor((rawMin+H)/2)` IMPAIR -> le natif MONTE
  bras DOWN : `H` tel que `rawMin + H` IMPAIR et `floor((rawMin+H)/2)` PAIR   -> le natif DESCEND

Les deux `H` different de 2 : meme regime de kill, meme geometrie, meme roster.

Sur chaque bras on confronte `pairUtility` NATIF
(`IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateUtilityFromPredictions`)
au terme degat du PORT nourri des MEMES predictions natives (`aiPlaybookPredict`) -- formule
ISOLEE : le feed est identique des deux cotes, donc tout ecart est un gap de LOGIQUE.

QUATRE variantes de port sont evaluees sur le MEME feed, en monkeypatchant le seul
`engine.utilities.damage.min_max_avg` :

  | variante          | bras UP (floor impair) | bras DOWN (floor pair) |
  |-------------------|------------------------|------------------------|
  | `to_even` (NATIF) |            0           |            0           |
  | `half_up`         |            0           |        -1 x pas        |
  | `kept_half` (port d'avant #333) |  +0.5 x pas |     -0.5 x pas       |
  | `trunc`           |        +1 x pas        |            0           |

`pas` = `100 / combinedMax` = la derivee de l'utilite par unite de degat (`DamageDealt` 80 +
`remaining` 20, cf. `DamageUtility$$.cctor`). **Aucune variante autre que `to_even` n'est nulle sur
les DEUX bras** : c'est la discrimination live du mode.

Le montage est PARAMETRE (attaquant / victime / board / centre de l'anneau) : le meme protocole
doit tenir ailleurs, sinon l'accord ne dit rien de plus qu'un ajustement. Trois montages joues,
tous OK -- cf. `docs/rl/case-333-arrondi-minmax-avg.md`.

ASCII only (cp1252). Usage (depuis scripts/python) :
    python probe_333_minmax_avg_rounding.py
    python probe_333_minmax_avg_rounding.py --attacker emperNoiseMarine --victim necroWarden
    python probe_333_minmax_avg_rounding.py --board C1_03 --center 3,6
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

import subprocess                                                            # noqa: E402

from rl_collect_batch import _resolve_session, _rpc                          # noqa: E402
from engine.weights import load as load_weights                             # noqa: E402
from engine_agreement_stages import _fields_from_native_event               # noqa: E402
import engine.utilities.damage as DMG                                       # noqa: E402
from probe_r34_overkill_decision import (view, by_visual, place_ring,        # noqa: E402
                                         playbook_events, native_pair_utility,
                                         port_pair_utility, _hpmax_by_id, _f,
                                         NORMAL_ATTACK)

# Attaquant SANS `ThrillSeekers` (son rider force `isForceOverkill` et rendrait l'observation
# ambigue -- meme precaution que #195).
ATTACKER = "ultraInceptorSgt"
FILLER_P = "astraBullgryn"      # 2e unite de mon camp : sans elle l'attaque finit mon tour
VICTIM = "genesPrimus"          # la cible mesuree
FILLER_A = "necroWarden"        # 2e ennemi : tuer la cible ne doit pas finir la bataille
BOARD = "MC1_67"
CENTER = (3, 4)                 # centre de l'anneau -- doit exister ET avoir assez de voisins

CALIB_HP = 200000               # passe 1 : PV hors de portee -> bornes NON capees


def _r(sid, m, b, t=90):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def _build(state_file: Path, seed: int, roster, hp_target: int, board: str) -> int:
    """`rl_duel build` -- board CHOISI (runner.md sec.2) ; `--crit 0,0` et `--block-target 0,0`
    neutralisent les deux canaux qui feraient bouger `MightBeOverkill`/`killSure` pour une raison
    ETRANGERE a l'arrondi mesure."""
    state_file.unlink(missing_ok=True)
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
           "--state-file", str(state_file), "--board", board, "--rank", "17",
           "--p-units", ",".join(roster["p"]), "--a-units", ",".join(roster["a"]),
           "--hp-target", str(hp_target), "--crit", "0,0", "--block-target", "0,0", "--no-ai"]
    proc = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not state_file.exists():
        raise RuntimeError("build KO : %s" % ((proc.stderr or proc.stdout or "")[-900:]))
    return int(json.loads(state_file.read_text())["runnerId"])


def _setup(sid, sf, seed, hp_target, roster, board, center):
    """Build + GEOMETRIE DRIVEE : l'attaquant au centre, tout le monde sur son ring 1 (sinon la
    portee refuse l'attaque et la prediction rend un degat nul -- et des bornes `[0,0]` se lisent
    a tort comme "couple non mesurable")."""
    rid = _build(sf, seed, roster, hp_target, board)
    dv = view(sid, rid)
    ids = {}
    for v in tuple(roster["p"]) + tuple(roster["a"]):
        u = by_visual(dv, v)
        if u is None:
            raise RuntimeError("unite absente du build : %s" % v)
        ids[v] = int(u["id"])
    place_ring(sid, rid, ids, roster["p"][0], tuple(center))
    return rid, ids


def _main_event(sid, rid, att_id, tgt_id):
    evs = playbook_events(sid, rid, att_id, tgt_id)
    return evs, next((e for e in evs if e.get("targetId") == tgt_id), None)


# -- variantes d'arrondi, appliquees au SEUL point de branchement -----------------------------

def _to_even(a, b):
    from engine.services.min_max_damage import min_max_avg
    return min_max_avg(a, b)


def _half_up(a, b):
    s = int(a) + int(b)
    return s // 2 + (s & 1)          # AwayFromZero sur des bornes >= 0


def _kept_half(a, b):
    return (int(a) + int(b)) / 2.0   # le port d'AVANT #333


def _trunc(a, b):
    return (int(a) + int(b)) // 2


VARIANTS = (("to_even", _to_even), ("half_up", _half_up),
            ("kept_half", _kept_half), ("trunc", _trunc))


def _port_utility(events, hpmax, team_by_id, my_team, wt, fn):
    """Terme degat du PORT sur le feed NATIF, avec `min_max_avg` remplace par `fn`. Le patch
    porte sur le nom IMPORTE dans `engine.utilities.damage` -- c'est le seul point ou le rail
    de degat consulte l'arrondi."""
    orig = DMG.min_max_avg
    DMG.min_max_avg = fn
    try:
        return port_pair_utility(events, hpmax, team_by_id, my_team, wt)
    finally:
        DMG.min_max_avg = orig


def _pick_hp(raw_min: int, raw_max: int):
    """Les DEUX PV qui posent un `.5` EXACT, de part et d'autre de la parite de la partie entiere.
    Contrainte : `rawMin < H < rawMax` (sinon la borne basse est capee aussi et la somme redevient
    paire, ou la cible passe en `WillBeKill`)."""
    start = (raw_min + raw_max) // 2
    up = down = None
    for delta in range(0, 64):
        for h in (start + delta, start - delta):
            if not (raw_min < h < raw_max):
                continue
            s = raw_min + h
            if s % 2 == 0:
                continue
            k = s // 2                      # floor (somme impaire)
            if k % 2 == 1 and up is None:
                up = h
            if k % 2 == 0 and down is None:
                down = h
        if up is not None and down is not None:
            break
    return up, down


def _measure_arm(sid, sf, seed, hp, wt, label, roster, board, center) -> dict:
    att, vic = roster["p"][0], roster["a"][0]
    rid = None
    try:
        rid, ids = _setup(sid, sf, seed, hp, roster, board, center)
        dv = view(sid, rid)
        team_by_id = {int(u["id"]): u.get("team") for u in (dv.get("units") or [])}
        hpmax = _hpmax_by_id(sid, rid)
        evs, main = _main_event(sid, rid, ids[att], ids[vic])
        if main is None:
            return {"label": label, "hp": hp, "error": "aucun event natif pour la paire"}
        f = _fields_from_native_event(main)
        nat = native_pair_utility(sid, rid, ids[att], ids[vic])
        my_team = team_by_id.get(ids[att])
        ports = {name: _port_utility(evs, hpmax, team_by_id, my_team, wt, fn)
                 for name, fn in VARIANTS}
    finally:
        if rid is not None:
            _r(sid, "disposeRunner", {"runnerId": rid}, 30)

    dmin, dmax = int(f["healthDmgMin"]), int(f["healthDmgMax"])
    s = dmin + dmax
    combined_max = (int(hpmax.get(ids[vic]) or 0) + 1) + (int(f["shieldBefore"] or 0) + 1)
    step = 100.0 / combined_max if combined_max else 0.0
    return {"label": label, "hp": hp, "runner": rid, "events": len(evs),
            "healthDmgMin": dmin, "healthDmgMax": dmax, "sum": s,
            "sum_odd": bool(s % 2), "floor": s // 2, "floor_odd": bool((s // 2) % 2),
            "shieldDmgMin": int(f["shieldDmgMin"] or 0), "shieldDmgMax": int(f["shieldDmgMax"] or 0),
            "hpBefore": int(f["hpBefore"] or 0), "hpMax": int(hpmax.get(ids[vic]) or 0),
            "kill": bool(f["kill"]), "killSure": bool(f["killSure"]),
            "limitedByMinHp": bool(f["limitedByMinHp"]),
            "combinedMax": combined_max, "step": step,
            "native": nat, "ports": ports,
            "deltas": {k: (None if nat is None else nat - v) for k, v in ports.items()}}


def _expected(arm: dict) -> dict:
    """Ce que le decompile PREDIT pour chaque variante, en multiples du pas d'utilite."""
    if not arm.get("sum_odd"):
        return {k: 0.0 for k, _ in VARIANTS}
    if arm["floor_odd"]:                     # natif = floor + 1
        return {"to_even": 0.0, "half_up": 0.0, "kept_half": +0.5, "trunc": +1.0}
    return {"to_even": 0.0, "half_up": -1.0, "kept_half": -0.5, "trunc": 0.0}


def run(seed: int = 33301, state_file=None, verbose: bool = True,
        attacker: str = ATTACKER, victim: str = VICTIM, board: str = BOARD,
        center=CENTER) -> dict:
    """Le montage est PARAMETRE (attaquant / victime / board) : le meme protocole doit tenir sur
    un autre couple et un autre plateau, sinon l'accord ne dit rien de plus qu'un ajustement."""
    sid = _resolve_session()
    sf = Path(state_file) if state_file else (PYDIR.parents[1] / "logs" / "p333.json")
    sf.parent.mkdir(parents=True, exist_ok=True)
    wt = load_weights()
    roster = {"p": (attacker, FILLER_P if attacker != FILLER_P else ATTACKER),
              "a": (victim, FILLER_A if victim != FILLER_A else VICTIM)}

    # PASSE 1 -- bornes NON capees (PV hors de portee). Elles fixent la fenetre de pilotage.
    rid = None
    try:
        rid, ids = _setup(sid, sf, seed + 900, CALIB_HP, roster, board, center)
        _evs, main = _main_event(sid, rid, ids[attacker], ids[victim])
        if main is None:
            return {"error": "calibration : aucun event natif pour la paire"}
        cal = _fields_from_native_event(main)
        raw_min, raw_max = int(cal["healthDmgMin"]), int(cal["healthDmgMax"])
    finally:
        if rid is not None:
            _r(sid, "disposeRunner", {"runnerId": rid}, 30)

    if verbose:
        print("[333] montage : %s -> %s sur %s, anneau centre en %s"
              % (attacker, victim, board, tuple(center)))
        print("[333] calibration : bornes NON capees = [%d, %d]" % (raw_min, raw_max))
    if raw_max - raw_min < 4:
        # Des bornes `[0,0]` ne disent PAS "couple non mesurable" : elles disent que l'anneau
        # choisi n'a pas mis les unites au CONTACT sur ce board (centre hors plateau, ou trop
        # pauvre en voisins). Le message doit envoyer changer le CENTRE, pas le roster.
        return {"error": "fenetre de pilotage trop etroite : bornes [%d,%d] (centre %s sur %s -- "
                         "si elles valent [0,0], l'anneau ne met pas au contact : changer --center)"
                         % (raw_min, raw_max, tuple(center), board),
                "raw": [raw_min, raw_max]}

    hp_up, hp_down = _pick_hp(raw_min, raw_max)
    if hp_up is None or hp_down is None:
        return {"error": "aucun couple de PV donnant les deux parites dans ]%d,%d["
                         % (raw_min, raw_max), "raw": [raw_min, raw_max]}
    if verbose:
        print("[333] PV pilotes : UP=%d (somme %d, floor %d IMPAIR) | DOWN=%d (somme %d, floor %d PAIR)"
              % (hp_up, raw_min + hp_up, (raw_min + hp_up) // 2,
                 hp_down, raw_min + hp_down, (raw_min + hp_down) // 2))

    arms = {"up": _measure_arm(sid, sf, seed, hp_up, wt, "UP (le natif MONTE)", roster, board,
                               center),
            "down": _measure_arm(sid, sf, seed + 1, hp_down, wt, "DOWN (le natif DESCEND)",
                                 roster, board, center)}

    ok = True
    for key, arm in arms.items():
        if arm.get("error"):
            ok = False
            if verbose:
                print("[333] bras %s : ERREUR %s" % (key, arm["error"]))
            continue
        exp = _expected(arm)
        arm["expected_steps"] = exp
        arm["measured_steps"] = {k: (None if d is None or not arm["step"] else d / arm["step"])
                                 for k, d in arm["deltas"].items()}
        arm["ok"] = all(
            arm["measured_steps"][k] is not None and abs(arm["measured_steps"][k] - exp[k]) < 0.02
            for k, _ in VARIANTS)
        arm["ok"] = bool(arm["ok"] and arm["sum_odd"] and not arm["limitedByMinHp"])
        ok &= arm["ok"]
        if verbose:
            print("\n=== bras %s === PV=%d bornes=[%d,%d] somme=%d (%s) floor=%d (%s) "
                  "shield=[%d,%d] combinedMax=%d pas=%.6f"
                  % (arm["label"], arm["hp"], arm["healthDmgMin"], arm["healthDmgMax"], arm["sum"],
                     "IMPAIRE" if arm["sum_odd"] else "PAIRE", arm["floor"],
                     "IMPAIR" if arm["floor_odd"] else "PAIR", arm["shieldDmgMin"],
                     arm["shieldDmgMax"], arm["combinedMax"], arm["step"]))
            print("  kill=%s killSure=%s limitedByMinHp=%s  natif=%s"
                  % (arm["kill"], arm["killSure"], arm["limitedByMinHp"], _f(arm["native"])))
            for name, _fn in VARIANTS:
                print("    %-10s port=%-14s delta=%-14s = %+.3f pas (attendu %+.3f)"
                      % (name, _f(arm["ports"][name]), _f(arm["deltas"][name]),
                         arm["measured_steps"][name] or 0.0, exp[name]))

    verdict = {"ok": bool(ok), "raw": [raw_min, raw_max], "arms": arms,
               "montage": {"attacker": attacker, "victim": victim, "board": board,
                           "center": tuple(center)}}
    # La DISCRIMINATION du mode : aucune autre variante ne peut etre nulle sur les DEUX bras.
    # (Calculee HORS de `verbose` -- c'est un resultat, pas un affichage.)
    if all(not a.get("error") for a in arms.values()):
        both = {name: all(abs((arms[k].get("measured_steps") or {}).get(name) or 9) < 0.02
                          for k in arms) for name, _ in VARIANTS}
        verdict["nul_on_both_arms"] = [n for n, v in both.items() if v]
        verdict["ok"] = bool(verdict["ok"] and verdict["nul_on_both_arms"] == ["to_even"])
    if verbose:
        print("\n=== VERDICT ===")
        for key, arm in arms.items():
            print("  %-5s : %s" % (key, "OK" if arm.get("ok") else "ECHEC"))
        if "nul_on_both_arms" in verdict:
            print("  variantes nulles sur les DEUX bras : %s"
                  % ", ".join(verdict["nul_on_both_arms"]))
        print("  -> %s" % ("OK" if verdict["ok"] else "ECHEC"))
    return verdict


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=33301)
    ap.add_argument("--state-file", default=None)
    ap.add_argument("--attacker", default=ATTACKER)
    ap.add_argument("--victim", default=VICTIM)
    ap.add_argument("--board", default=BOARD, help="board CHOISI (runner.md sec.2), jamais subi")
    ap.add_argument("--center", default="%d,%d" % CENTER,
                    help="centre de l'anneau (col,row) -- a adapter au board")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    out = run(seed=a.seed, state_file=a.state_file, attacker=a.attacker, victim=a.victim,
              board=a.board, center=tuple(int(x) for x in a.center.split(",")))
    if out.get("error"):
        print("[333] ERREUR : %s" % out["error"])
    if a.json:
        print(json.dumps(out, indent=1, default=str))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
