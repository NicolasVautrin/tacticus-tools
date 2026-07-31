#!/usr/bin/env python
"""Probe #342 -- le terme BOUCLIER du composite `Damage(34)`, CONFRONTE LIVE.

CE QUE #333 A LAISSE OUVERT
--------------------------
#333 a discrimine live le mode d'arrondi de `IdunBattle.Core.Services.MinMaxDamage$$Avg`
(`MidpointRounding.ToEven`) -- mais SEULEMENT sur le terme SANTE
(`IdunBattle.AI.Utilities.DamageUtility$$GetHealthDamage`). Le terme BOUCLIER
(`IdunBattle.AI.Utilities.DamageUtility$$GetShieldDamage` = `Avg(AccurateShieldDamage@+0x50)`)
recevait le meme correctif PAR SYMETRIE, sans aucune mesure : `AccurateShieldDamage` valait
`[0, 0]` sur tous les montages, faute de savoir poser un bouclier.

POURQUOI LE HARNAIS NE SAVAIT PAS EN POSER
-----------------------------------------
`BC.Units[].Shield` (`IdunBattle.Configuration.UnitConfiguration.Shield@+0x4c`) n'est lu par
AUCUN chemin de deploiement :

  * `IdunBattle.Entities.Components.ShieldComponent$$.ctor` ne fait qu'allouer une `List` VIDE
    -- aucune valeur initiale, aucun parametre ;
  * le SEUL ecrivain de cette liste est
    `IdunBattle.Entities.Components.ShieldComponent$$AddOrUpdateShield`, dont l'unique appelant
    est `IdunBattle.Operations.CreateShieldOperation$$Execute` ;
  * `IdunBattle.Operations.AddUnitOperation$$Execute` (le deploiement) n'accede jamais a
    `+0x4c` et n'emet aucune `CreateShieldOperation` ;
  * `Idun.Source.IdunBattle.View.BattleConfigBuilder$$GetUnitConfiguration` -- la fonction
    native qui REMPLIT chaque `BC.Units[]` -- ecrit 29 champs et saute `+0x4c`.

=> Le bouclier ne s'OBTIENT qu'en le faisant POSER en bataille, par un des neuf appelants de
`IdunBattleLogic.Entities.DSLBehaviors$$CreateShield`. Le plus controlable est
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.ArcaneShieldAbility` (`thousSorcerer`,
deja porte et garde par #N1) : son trigger `On(0x1c = ArrivedAtFinalTile)` fire au 1er
deplacement de son porteur -- donc le simple `place_ring` du montage le declenche. On met le
sorcier dans l'equipe de la VICTIME : il accorde le bouclier a son meilleur voisin allie.

COMMENT LA PARITE EST PILOTEE (le pendant de `--hp-target` de #333)
------------------------------------------------------------------
En regime "tout passe au bouclier" (`Damage` bas), les DEUX bornes valent
`hits x round(k x Damage)` : leur somme est TOUJOURS paire, aucun `.5` n'existe et la mesure
serait vide. Le regime utile est celui du CAP : quand le degat MAX depasse le bouclier,
`AccurateShieldDamage.Max` est fige a `shieldBefore` (IMPAIR ici) pendant que `Min` reste
multiple du nombre de coups (PAIR) -- la somme est alors IMPAIRE, et un pas de 1 sur
`--unit-stat "<attaquant>:Damage=D"` fait BASCULER la parite de la partie entiere.

  bras UP   : `D` tel que `floor((sMin+sMax)/2)` est IMPAIR -> le natif MONTE
  bras DOWN : `D` tel que ce meme floor est PAIR            -> le natif DESCEND

ISOLATION DU TERME MESURE
-------------------------
Le composite somme `GetHealthDamage` ET `GetShieldDamage`, tous deux arrondis SEPAREMENT. Les
quatre variantes ne sont donc PAS appliquees a `min_max_avg` (ce qui bougerait les deux termes
a la fois, et le terme SANTE suffirait a expliquer l'ecart) : elles remplacent la SEULE methode
`DamageUtility.get_shield_damage`. Le terme sante garde `to_even` dans les quatre cas.

  | variante          | bras UP (floor impair) | bras DOWN (floor pair) |
  |-------------------|------------------------|------------------------|
  | `to_even` (NATIF) |            0           |            0           |
  | `half_up`         |            0           |        -1 x pas        |
  | `kept_half`       |        +0.5 x pas      |      -0.5 x pas        |
  | `trunc`           |        +1 x pas        |            0           |

`pas` = `100 / combinedMax` avec `combinedMax = (maxHP + 1) + (shield + 1)`
(`IdunBattle.AI.Utilities.DamageUtility$$CombinedMax`).

ASCII only (cp1252). Usage (depuis scripts/python) :
    python probe_342_shield_term_rounding.py
    python probe_342_shield_term_rounding.py --attacker emperNoiseMarine --victim necroWarden
    python probe_342_shield_term_rounding.py --board C1_03 --center 3,6
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
from engine.weights import load as load_weights                             # noqa: E402
from engine_agreement_stages import _fields_from_native_event               # noqa: E402
import engine.utilities.damage as DMG                                       # noqa: E402
from probe_r34_overkill_decision import (view, by_visual, place_ring,        # noqa: E402
                                         playbook_events, native_pair_utility,
                                         port_pair_utility, _hpmax_by_id, _f)

ATTACKER = "ultraInceptorSgt"   # attaquant SANS `ThrillSeekers` (cf. #333 / #195)
FILLER_P = "astraBullgryn"      # 2e unite de mon camp : sans elle l'attaque finit mon tour
VICTIM = "genesPrimus"          # la cible mesuree -- c'est ELLE qui recoit le bouclier
SHIELDER = "thousSorcerer"      # porteur d'`ArcaneShield`, place DANS L'EQUIPE DE LA VICTIME
BOARD = "MC1_67"
CENTER = (3, 4)

CALIB_DAMAGE = 200              # sonde en regime NON cape : donne le ratio degat/`Damage`
MAX_SCAN = 14                   # nb max de `Damage` essayes pour trouver les deux parites


def _r(sid, m, b, t=90):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def _build(state_file: Path, seed: int, roster, board: str, damage=None) -> int:
    """`rl_duel build` -- board CHOISI (runner.md sec.2). `--crit 0,0` / `--block-target 0,0`
    neutralisent les deux canaux qui feraient bouger `MightBeOverkill`/`killSure` pour une raison
    ETRANGERE a l'arrondi mesure. `--no-ai` : l'adversaire ne joue rien pendant le placement."""
    state_file.unlink(missing_ok=True)
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
           "--state-file", str(state_file), "--board", board, "--rank", "17",
           "--p-units", ",".join(roster["p"]), "--a-units", ",".join(roster["a"]),
           "--crit", "0,0", "--block-target", "0,0", "--no-ai"]
    if damage is not None:
        cmd += ["--unit-stat", "%s:Damage=%d" % (roster["p"][0], int(damage))]
    proc = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not state_file.exists():
        raise RuntimeError("build KO : %s" % ((proc.stderr or proc.stdout or "")[-900:]))
    return int(json.loads(state_file.read_text())["runnerId"])


def _setup(sid, sf, seed, roster, board, center, damage):
    """Build + GEOMETRIE DRIVEE. Le `place_ring` a un SECOND role ici : le deplacement du
    `thousSorcerer` declenche `On(0x1c = ArrivedAtFinalTile)`, donc la pose du bouclier."""
    rid = _build(sf, seed, roster, board, damage)
    dv = view(sid, rid)
    ids = {}
    for v in tuple(roster["p"]) + tuple(roster["a"]):
        u = by_visual(dv, v)
        if u is None:
            raise RuntimeError("unite absente du build : %s" % v)
        ids[v] = int(u["id"])
    place_ring(sid, rid, ids, roster["a"][0], tuple(center))
    return rid, ids


def _measure(sid, sf, seed, roster, board, center, damage, wt, label) -> dict:
    """Un bras : bornes natives, `pairUtility` natif, et les quatre variantes du terme BOUCLIER."""
    att, vic = roster["p"][0], roster["a"][0]
    rid = None
    try:
        rid, ids = _setup(sid, sf, seed, roster, board, center, damage)
        dv = view(sid, rid)
        team_by_id = {int(u["id"]): u.get("team") for u in (dv.get("units") or [])}
        hpmax = _hpmax_by_id(sid, rid)
        evs = playbook_events(sid, rid, ids[att], ids[vic])
        main = next((e for e in evs if e.get("targetId") == ids[vic]), None)
        if main is None:
            return {"label": label, "damage": damage, "error": "aucun event natif pour la paire"}
        f = _fields_from_native_event(main)
        nat = native_pair_utility(sid, rid, ids[att], ids[vic])
        my_team = team_by_id.get(ids[att])
        ports = {name: _port_utility(evs, hpmax, team_by_id, my_team, wt, fn)
                 for name, fn in VARIANTS}
        # `current` = le port TEL QU'IL EST, SANS aucun patch. Les quatre variantes REMPLACENT
        # `get_shield_damage` : sans cette 5e mesure, une regression du code REEL passerait
        # inapercue (la garde ne verrouillerait que le catalogue de variantes, pas le moteur).
        ports["current"] = port_pair_utility(evs, hpmax, team_by_id, my_team, wt)
    finally:
        if rid is not None:
            _r(sid, "disposeRunner", {"runnerId": rid}, 30)

    smin, smax = int(f["shieldDmgMin"] or 0), int(f["shieldDmgMax"] or 0)
    hmin, hmax_d = int(f["healthDmgMin"] or 0), int(f["healthDmgMax"] or 0)
    s = smin + smax
    shield = int(f["shieldBefore"] or 0)
    combined_max = (int(hpmax.get(ids[vic]) or 0) + 1) + (shield + 1)
    step = 100.0 / combined_max if combined_max else 0.0
    return {"label": label, "damage": damage, "runner": rid, "events": len(evs),
            "shieldBefore": shield, "shieldCapped": bool(smax == shield and shield > 0),
            "shieldDmgMin": smin, "shieldDmgMax": smax, "sum": s,
            "sum_odd": bool(s % 2), "floor": s // 2, "floor_odd": bool((s // 2) % 2),
            "healthDmgMin": hmin, "healthDmgMax": hmax_d,
            "hpBefore": int(f["hpBefore"] or 0), "hpMax": int(hpmax.get(ids[vic]) or 0),
            "kill": bool(f["kill"]), "killSure": bool(f["killSure"]),
            "limitedByMinHp": bool(f["limitedByMinHp"]),
            "combinedMax": combined_max, "step": step,
            "native": nat, "ports": ports,
            "deltas": {k: (None if nat is None else nat - v) for k, v in ports.items()}}


# -- variantes d'arrondi, appliquees au SEUL terme BOUCLIER -----------------------------------

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
    """Terme degat du PORT sur le feed NATIF, avec le SEUL `get_shield_damage` remplace par `fn`.
    Le terme SANTE garde son arrondi natif dans les quatre variantes -- c'est ce qui rend la
    mesure ATTRIBUABLE au bouclier (patcher `min_max_avg` bougerait les deux termes)."""
    orig = DMG.DamageUtility.get_shield_damage

    def _patched(self, pred):
        return float(fn(pred.get("shieldDmgMin") or 0, pred.get("shieldDmgMax") or 0))

    DMG.DamageUtility.get_shield_damage = _patched
    try:
        return port_pair_utility(events, hpmax, team_by_id, my_team, wt)
    finally:
        DMG.DamageUtility.get_shield_damage = orig


def check_bc_shield_field(seed: int = 34209, state_file=None, victim: str = VICTIM,
                          board: str = BOARD, amount: int = 6000, verbose: bool = True) -> dict:
    """MESURE (a) -- OU la valeur `--unit-stat "<u>:Shield=N"` se perd, tranchee aux DEUX BOUTS.

    On compare le BC REELLEMENT ENVOYE a `initAndStart` (que `rl_duel build` archive tel quel dans
    son `--state-file`) a ce que la bataille contient (`combatSnapshot.shields`). Les trois
    hypotheses se separent d'elles-memes :

      * `bc_shield != amount`     -> l'outil Python n'ecrit pas (ou `buildNormalizedBC` ecrase) ;
      * `bc_shield == amount` et `shields == []` -> le BC porte la valeur et le NATIF l'ignore.

    Le second cas est celui qui est mesure, et il est CLOS au decompile : voir l'en-tete du module.
    """
    sid = _resolve_session()
    sf = Path(state_file) if state_file else (PYDIR.parents[1] / "logs" / "p342field.json")
    sf.parent.mkdir(parents=True, exist_ok=True)
    sf.unlink(missing_ok=True)
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
           "--state-file", str(sf), "--board", board, "--rank", "17",
           "--p-units", ATTACKER, "--a-units", victim, "--no-ai",
           "--unit-stat", "%s:Shield=%d" % (victim, amount)]
    proc = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not sf.exists():
        return {"error": "build KO : %s" % ((proc.stderr or proc.stdout or "")[-900:])}
    st = json.loads(sf.read_text(encoding="utf-8"))
    rid = int(st["runnerId"])
    bc_units = [u for u in ((st.get("bc") or {}).get("Units") or [])
                if u.get("VisualId") == victim]
    bc_shield = int(bc_units[0].get("Shield") or 0) if bc_units else None
    try:
        dv = view(sid, rid)
        u = by_visual(dv, victim)
        vic_id = None if u is None else int(u["id"])
        snap = _r(sid, "combatSnapshot", {"runnerId": rid}, 120)
        by_ent = {int(x.get("entityId")): x for x in (snap.get("units") or [])
                  if x.get("entityId") is not None}
        shields = (by_ent.get(vic_id) or {}).get("shields")
        all_shields = {int(k): v.get("shields") for k, v in by_ent.items()}
    finally:
        _r(sid, "disposeRunner", {"runnerId": rid}, 30)
    out = {"asked": amount, "bc_shield": bc_shield, "shields": shields,
           "all_shields": all_shields, "build_accepted": True,
           "written_to_bc": bc_shield == amount,
           "materialised": bool(shields)}
    if verbose:
        print("[342a] --unit-stat %s:Shield=%d -> accepte par le montage : OUI"
              % (victim, amount))
        print("[342a]   BC ENVOYE a initAndStart : Units[%s].Shield = %s  (%s)"
              % (victim, bc_shield,
                 "ECRIT" if out["written_to_bc"] else "PERDU cote outil/normalisation"))
        print("[342a]   bataille (combatSnapshot) : shields = %s  (%s)"
              % (shields, "MATERIALISE" if out["materialised"] else "AUCUN bouclier"))
    return out


def _expected(arm: dict) -> dict:
    """Ce que le decompile PREDIT pour chaque variante, en multiples du pas d'utilite."""
    if not arm.get("sum_odd"):
        return {k: 0.0 for k, _ in VARIANTS}
    if arm["floor_odd"]:                     # natif = floor + 1
        return {"to_even": 0.0, "half_up": 0.0, "kept_half": +0.5, "trunc": +1.0}
    return {"to_even": 0.0, "half_up": -1.0, "kept_half": -0.5, "trunc": 0.0}


def _scan_damage(sid, sf, seed, roster, board, center, wt, verbose):
    """Trouve les DEUX `Damage` qui posent un `.5` EXACT de part et d'autre de la parite de la
    partie entiere du terme BOUCLIER. Deux etapes :

      1. sonde a `CALIB_DAMAGE` en regime NON cape -> ratio `shieldDmgMax / Damage` ;
      2. balayage a partir du premier `Damage` qui CAPE la borne haute au bouclier (c'est ce cap
         qui rend la somme IMPAIRE : `Max` fige a `shieldBefore`, `Min` multiple des coups).
    """
    probe = _measure(sid, sf, seed, roster, board, center, CALIB_DAMAGE, wt, "calibration")
    if probe.get("error"):
        return None, None, probe
    if probe["shieldBefore"] <= 0:
        probe["error"] = ("aucun bouclier pose : %s n'a pas accorde ArcaneShield (deplacement "
                          "refuse, ou aucun allie dans son rayon)" % roster["a"][1])
        return None, None, probe
    if probe["shieldDmgMax"] <= 0:
        probe["error"] = "sonde a Damage=%d : degat bouclier nul (les unites ne sont pas au " \
                         "contact -- changer --center)" % CALIB_DAMAGE
        return None, None, probe
    ratio = probe["shieldDmgMax"] / float(CALIB_DAMAGE)
    d0 = int(probe["shieldBefore"] / ratio) + 1
    if verbose:
        print("[342] calibration : bouclier pose = %d | sonde Damage=%d -> shieldDmg=[%d, %d] "
              "(ratio max/D = %.4f) -> balayage a partir de Damage=%d"
              % (probe["shieldBefore"], CALIB_DAMAGE, probe["shieldDmgMin"],
                 probe["shieldDmgMax"], ratio, d0))
    up = down = None
    scanned = []
    for k in range(MAX_SCAN):
        d = d0 + k
        m = _measure(sid, sf, seed, roster, board, center, d, wt, "scan")
        if m.get("error"):
            continue
        scanned.append({"damage": d, "s": [m["shieldDmgMin"], m["shieldDmgMax"]],
                        "capped": m["shieldCapped"], "sum_odd": m["sum_odd"],
                        "floor_odd": m["floor_odd"]})
        if verbose:
            print("[342]   Damage=%-5d shieldDmg=[%5d, %5d] cape=%-5s somme=%-6s floor=%s"
                  % (d, m["shieldDmgMin"], m["shieldDmgMax"], m["shieldCapped"],
                     "IMPAIRE" if m["sum_odd"] else "PAIRE",
                     "IMPAIR" if m["floor_odd"] else "PAIR"))
        if not m["sum_odd"]:
            continue
        if m["floor_odd"] and up is None:
            up = d
        if (not m["floor_odd"]) and down is None:
            down = d
        if up is not None and down is not None:
            break
    return up, down, {"scan": scanned, "shieldBefore": probe["shieldBefore"]}


def run(seed: int = 34201, state_file=None, verbose: bool = True,
        attacker: str = ATTACKER, victim: str = VICTIM, shielder: str = SHIELDER,
        board: str = BOARD, center=CENTER) -> dict:
    """Le montage est PARAMETRE (attaquant / victime / porteur de bouclier / board / centre) :
    le meme protocole doit tenir ailleurs, sinon l'accord ne dit rien de plus qu'un ajustement."""
    sid = _resolve_session()
    sf = Path(state_file) if state_file else (PYDIR.parents[1] / "logs" / "p342.json")
    sf.parent.mkdir(parents=True, exist_ok=True)
    wt = load_weights()
    roster = {"p": (attacker, FILLER_P if attacker != FILLER_P else ATTACKER),
              "a": (victim, shielder)}
    if verbose:
        print("[342] montage : %s -> %s (bouclier pose par %s) sur %s, anneau centre en %s"
              % (attacker, victim, shielder, board, tuple(center)))

    d_up, d_down, cal = _scan_damage(sid, sf, seed + 900, roster, board, center, wt, verbose)
    if cal.get("error"):
        return {"error": cal["error"]}
    if d_up is None or d_down is None:
        return {"error": "aucun couple de Damage donnant les deux parites (UP=%s DOWN=%s) apres "
                         "%d essais" % (d_up, d_down, MAX_SCAN), "calibration": cal}

    arms = {"up": _measure(sid, sf, seed, roster, board, center, d_up, wt,
                           "UP (le natif MONTE)"),
            "down": _measure(sid, sf, seed + 1, roster, board, center, d_down, wt,
                             "DOWN (le natif DESCEND)")}

    ok = True
    for key, arm in arms.items():
        if arm.get("error"):
            ok = False
            if verbose:
                print("[342] bras %s : ERREUR %s" % (key, arm["error"]))
            continue
        exp = _expected(arm)
        exp["current"] = 0.0          # le port en vigueur DOIT egaler le natif
        arm["expected_steps"] = exp
        arm["measured_steps"] = {k: (None if d is None or not arm["step"] else d / arm["step"])
                                 for k, d in arm["deltas"].items()}
        arm["ok"] = all(
            arm["measured_steps"][k] is not None and abs(arm["measured_steps"][k] - exp[k]) < 0.02
            for k in tuple(n for n, _ in VARIANTS) + ("current",))
        # Le regime doit etre NON DEGENERE : bouclier reellement pose, borne haute CAPEE (c'est
        # ce qui produit l'imparite), somme impaire, et pas de court-circuit `LimitedByMinHp`.
        arm["ok"] = bool(arm["ok"] and arm["sum_odd"] and arm["shieldBefore"] > 0
                         and arm["shieldCapped"] and not arm["limitedByMinHp"])
        ok &= arm["ok"]
        if verbose:
            print("\n=== bras %s === Damage=%d bouclier=%d shieldDmg=[%d,%d] somme=%d (%s) "
                  "floor=%d (%s) sante=[%d,%d] combinedMax=%d pas=%.6f"
                  % (arm["label"], arm["damage"], arm["shieldBefore"], arm["shieldDmgMin"],
                     arm["shieldDmgMax"], arm["sum"], "IMPAIRE" if arm["sum_odd"] else "PAIRE",
                     arm["floor"], "IMPAIR" if arm["floor_odd"] else "PAIR",
                     arm["healthDmgMin"], arm["healthDmgMax"], arm["combinedMax"], arm["step"]))
            print("  kill=%s killSure=%s limitedByMinHp=%s  natif=%s"
                  % (arm["kill"], arm["killSure"], arm["limitedByMinHp"], _f(arm["native"])))
            for name in tuple(n for n, _ in VARIANTS) + ("current",):
                print("    %-10s port=%-14s delta=%-14s = %+.3f pas (attendu %+.3f)"
                      % (name, _f(arm["ports"][name]), _f(arm["deltas"][name]),
                         arm["measured_steps"][name] or 0.0, exp[name]))

    verdict = {"ok": bool(ok), "calibration": cal, "damage_up": d_up, "damage_down": d_down,
               "arms": arms,
               "montage": {"attacker": attacker, "victim": victim, "shielder": shielder,
                           "board": board, "center": tuple(center)}}
    # La DISCRIMINATION du mode : aucune autre variante ne peut etre nulle sur les DEUX bras.
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
    ap.add_argument("--seed", type=int, default=34201)
    ap.add_argument("--state-file", default=None)
    ap.add_argument("--attacker", default=ATTACKER)
    ap.add_argument("--victim", default=VICTIM)
    ap.add_argument("--shielder", default=SHIELDER)
    ap.add_argument("--board", default=BOARD, help="board CHOISI (runner.md sec.2), jamais subi")
    ap.add_argument("--center", default="%d,%d" % CENTER,
                    help="centre de l'anneau (col,row) -- a adapter au board")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--part", default="rounding", choices=("rounding", "field", "all"),
                    help="`field` = la mesure (a) : ou se perd `--unit-stat <u>:Shield=N`")
    a = ap.parse_args()
    if a.part in ("field", "all"):
        f = check_bc_shield_field(victim=a.victim, board=a.board)
        if a.part == "field":
            return 0 if (f.get("written_to_bc") and not f.get("materialised")) else 1
    out = run(seed=a.seed, state_file=a.state_file, attacker=a.attacker, victim=a.victim,
              shielder=a.shielder, board=a.board,
              center=tuple(int(x) for x in a.center.split(",")))
    if out.get("error"):
        print("[342] ERREUR : %s" % out["error"])
    if a.json:
        print(json.dumps(out, indent=1, default=str))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
