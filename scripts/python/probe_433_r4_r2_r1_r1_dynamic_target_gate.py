"""probe #433-r4-r2-r1-r1 -- ce qui SEPARE deux abilities au MEME preset de ciblage.

LE FAIT A EXPLIQUER. `LightOfSanguinius` (1177) et `LeadingTheCharge` (1204) partagent le MEME
preset (`IdunBattle.Core.Services.TargetingOptions$$.cctor`, statique `+0x240`), donc le meme
`TargetingRange` (`UseWholeBoard`) ET le meme masque `Rules = 0x102004032` -- et rendent pourtant des
zones DIFFERENTES. Le discriminant est donc EN AVAL du `TargetingRange`.

LA CHAINE, LUE. `IdunBattle.Entities.Abilities.AActiveAbility$$.ctor` ne se contente pas de recopier
les 0x40 octets du preset dans `this.<TargetingOptions @+0x70>` : il ECRASE ensuite DEUX champs par
des delegues lies a des methodes VIRTUELLES de l'instance --

    this.TargetingOptions.<+0x30> = new TargetingOptions.DynamicTargetingRule(this, <klass+0x470>)
    this.TargetingOptions.<+0x38> = new TargetingOptions.DynamicTargetingTargetRule(this, <klass+0x480>)

`klass+0x470` / `klass+0x480` sont les champs `MethodInfo*` (a `+8` du debut de slot) des slots de
vtable commencant a `klass+0x468` / `klass+0x478` -- la vtable IL2CPP demarrant a `klass+0x138` avec
un pas de 0x10, ce sont les index 51 et 52. RESOLUS AU RUNTIME (`resolveVtableSlot`), ce sont
`GetDynamicInvalidCasterReason` et `GetDynamicInvalidTargetReason`.

Le champ `+0x38` est EXACTEMENT celui qu'invoque le troisieme predicat de
`IdunBattle.Core.Services.TargetingQuery$$GetPossibleTargetsForOptions` (la lambda
`u003Cu003Ec__DisplayClass34_0$$u003CGetPossibleTargetsForOptionsu003Eb__2`, appliquee en
`RemoveAll` quand `Rules & 2`) : la tuile est RETIREE de la zone quand le delegue rend une raison non
nulle. C'est donc `GetDynamicInvalidTargetReason` -- et lui seul -- qui donne sa FORME a la zone
au-dela du `TargetingRange`.

CE QUE LE PROBE MESURE :

  * `--step gate` : pour CHAQUE classe derivant (transitivement) de `AActiveAbility`, l'adresse du
    slot `+0x478` resolue AU RUNTIME. Les classes dont l'adresse EGALE celle d'`AActiveAbility`
    n'ont pas de gate ; les autres surchargent. C'est la seule facon de conclure : les corps
    triviaux etant DEDUPLIQUES par IL2CPP, l'absence d'un `<X>$$GetDynamicInvalidTargetReason` dans
    les tables ne prouve RIEN. Croise avec l'inventaire des abilities `UseWholeBoard` du port.

  * `--step sweep` : la ZONE mesuree, natif contre port, sur un sweep de positions. Le terme
    s'isole par `bonus = util + 10 * sum_E d(P,E)` (branche A pure d'`EarlyWarningOverridePlaybook`)
    -- `0` = en portee, `50` = hors portee -- et la partition n'est attribuable qu'a UN ennemi
    vivant. Deux kits, choisis pour que le modele porte les SEPARE :
      - `bloodDante` : arme MELEE + `LightOfSanguinius` (whole-board, `constants.range = 5`)
        -> zone d'ability != portee d'arme, c'est le cas DISCRIMINANT ;
      - `astraDreir` : arme MELEE + `LeadingTheCharge` (whole-board, gate de MOUVEMENT).

Usage (ASCII only, depuis scripts/python) :
  python probe_433_r4_r2_r1_r1_dynamic_target_gate.py --step gate
  python probe_433_r4_r2_r1_r1_dynamic_target_gate.py --step sweep
  python probe_433_r4_r2_r1_r1_dynamic_target_gate.py --step all
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hexgeo                                                     # noqa: E402
from rl_collect_batch import _resolve_session, _rpc               # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]

CASTER = "tauCrisis"          # HERO du pool ; seul porteur `lineup` de 1077 EarlyWarningOverride
ABILITY = 1077                # ActiveAbilityType.EarlyWarningOverride
BOARD = "MC1_67"
SEED = "777"

AACTIVE_NS = "IdunBattle.Entities.Abilities"
AACTIVE_CLS = "AActiveAbility"
SLOT_DYNAMIC_TARGET = 0x478   # index 52 de la vtable (klass+0x138 + 52*0x10)
SLOT_DYNAMIC_CASTER = 0x468   # index 51


def _r(sid, m, b, t=90):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


# ------------------------------------------------------------------------------------------------
# --step gate : QUI surcharge `GetDynamicInvalidTargetReason` ?
# ------------------------------------------------------------------------------------------------
def _active_ability_classes():
    """Toutes les classes dont la chaine de parents atteint `AActiveAbility`, lues dans la table
    de symboles VERSIONNEE (`data/symbols/<build>/frida/classes.tsv`, colonnes
    `fullName \\t size \\t parent \\t ...`)."""
    build = (ROOT / "data" / "symbols").glob("*/frida/classes.tsv")
    parents: dict[str, str] = {}
    for path in build:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("#!"):
                    continue
                cols = line.rstrip("\n").split("\t")
                if len(cols) >= 3 and cols[0] and "<" not in cols[0]:
                    parents[cols[0]] = cols[2]
    base = AACTIVE_NS + "." + AACTIVE_CLS
    out = []
    for name in parents:
        seen, cur = 0, name
        while cur and seen < 12:
            cur = parents.get(cur)
            seen += 1
            if cur == base:
                out.append(name)
                break
    return sorted(out)


def _split(full):
    i = full.rfind(".")
    return (full[:i], full[i + 1:]) if i > 0 else ("", full)


def _slot_addr(sid, ns, cls, off):
    try:
        res = _r(sid, "resolveVtableSlot", {"ns": ns, "cls": cls, "start": off, "end": off}, 30)
    except Exception as exc:                                      # pragma: no cover - diagnostic
        return None, str(exc)[:80]
    if not res.get("ok"):
        return None, (res.get("error") or "?")[:80]
    slots = res.get("slots") or []
    return (slots[0].get("ghidraVA") if slots else None), None


def step_gate(sid):
    from engine.services.ability_range import TARGETING_RANGE_BY_ABILITY
    from engine.runner.abilities.handler import ABILITY_CLASSES

    whole = set()
    for aid, cls in ABILITY_CLASSES.items():
        opts = getattr(cls, "TARGETING_OPTIONS", None)
        rng = getattr(opts, "range", None) if opts is not None else None
        if rng is not None and getattr(rng, "use_whole_board", False):
            whole.add(getattr(cls, "__name__", ""))
    for aid, rng in TARGETING_RANGE_BY_ABILITY.items():
        if getattr(rng, "use_whole_board", False):
            from engine.entities.active_ability_type import ActiveAbilityType
            try:
                whole.add(ActiveAbilityType(aid).name + "Ability")
            except ValueError:
                pass

    base_addr, err = _slot_addr(sid, AACTIVE_NS, AACTIVE_CLS, SLOT_DYNAMIC_TARGET)
    print("base AActiveAbility.GetDynamicInvalidTargetReason = %s (%s)" % (base_addr, err))
    if base_addr is None:
        return 1

    names = _active_ability_classes()
    print("classes derivant de AActiveAbility (classes.tsv) : %d" % len(names))
    overriders, missing = [], []
    for full in names:
        ns, cls = _split(full)
        addr, err = _slot_addr(sid, ns, cls, SLOT_DYNAMIC_TARGET)
        if addr is None:
            missing.append((full, err))
            continue
        if addr != base_addr:
            overriders.append((full, cls, addr, cls in whole))
    print("")
    print("SURCHARGES de GetDynamicInvalidTargetReason : %d / %d" % (len(overriders), len(names)))
    for full, cls, addr, is_whole in sorted(overriders):
        print("  %-4s %-72s %s" % ("WB" if is_whole else "", full, addr))
    print("")
    hit = sorted(c for _, c, _, w in overriders if w)
    print("dont WHOLE_BOARD : %d / %d  -> %s" % (len(hit), len(whole), ", ".join(hit)))
    no_gate = sorted(w for w in whole if w not in {c for _, c, _, _ in overriders})
    print("WHOLE_BOARD SANS gate (zone = tout le plateau) : %d -> %s"
          % (len(no_gate), ", ".join(no_gate)))
    if missing:
        print("non resolues : %d (ex. %s)" % (len(missing), missing[:3]))
    return 0


# ------------------------------------------------------------------------------------------------
# --step sweep : la ZONE, natif contre port
# ------------------------------------------------------------------------------------------------
def _build(enemy, extra=None):
    state = ROOT / "logs" / "runners" / ("p433r1r1-%s.json" % uuid.uuid4().hex[:8])
    state.parent.mkdir(parents=True, exist_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", SEED, "--board", BOARD,
            "--state-file", str(state), "--p-units", CASTER, "--a-units", enemy,
            "--hp-target", "90000", "--hp-player", "90000"] + list(extra or [])
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state.exists():
        return None, (p.stderr or p.stdout or "")[-1200:]
    return json.loads(state.read_text())["runnerId"], None


def _dispose(sid, rid):
    if rid is None:
        return
    try:
        _r(sid, "disposeRunner", {"runnerId": rid}, 60)
    except Exception:                                             # pragma: no cover - diagnostic
        pass


def _walkable(sid, rid):
    bg = _r(sid, "boardGraph", {"runnerId": rid}, 60)
    out = {}
    for t in (bg.get("tiles") or []):
        pos = t.get("pos") or {}
        if t.get("walkable", True):
            out[(pos.get("col"), pos.get("row"))] = t
    return out


def _place(sid, rid, caster_id, enemy_id, o_pos, e_pos):
    for uid, p in ((enemy_id, e_pos), (caster_id, o_pos)):
        _r(sid, "applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": uid, "to": {"col": p[0], "row": p[1]}}}, 90)
    for _ in range(4):
        _r(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
        mov = _r(sid, "aiMovableTiles", {"runnerId": rid}, 90)
        by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
        if (by_unit.get(caster_id) or {}).get("tiles"):
            return True
    return False


def step_sweep(sid, enemy, radius_max=9):
    from engine.services.ability_range import unit_threat_reach

    rid, err = _build(enemy)
    if rid is None:
        print("BUILD FAILED (%s): %s" % (enemy, err))
        return 2
    try:
        dv = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
        units = dv.get("units") or []
        c = next((u for u in units if u.get("visualId") == CASTER), None)
        e = next((u for u in units if u.get("visualId") == enemy), None)
        if c is None or e is None:
            print("MONTAGE: caster/ennemi absent (%s)" % enemy)
            return 2
        alive = [u for u in units if not u.get("isDead") and u.get("teamId") == e.get("teamId")]
        if len(alive) != 1:
            print("MONTAGE REFUSE (%s): %d ennemis vivants, la partition n'est pas attribuable"
                  % (enemy, len(alive)))
            return 2
        walk = _walkable(sid, rid)
        e_pos = (e["pos"]["col"], e["pos"]["row"])
        cand = [p for p in walk
                if 2 <= hexgeo.distance(p, e_pos) <= radius_max and p != e_pos]
        cand.sort(key=lambda p: (hexgeo.distance(p, e_pos), p))
        far = max(cand, key=lambda p: hexgeo.distance(p, e_pos))
        if not _place(sid, rid, c["unitId"], e["unitId"], far, e_pos):
            print("MONTAGE: pas de move set frais (%s)" % enemy)
            return 2
        got = {}
        for p in cand:
            res = _r(sid, "ncEvaluate", {"runnerId": rid, "unitId": c["unitId"],
                                         "abilityId": ABILITY,
                                         "tile": {"col": p[0], "row": p[1]}}, 60)
            u = res.get("utility")
            if u is None:
                continue
            bonus = float(u) + 10.0 * hexgeo.distance(p, e_pos)
            got[p] = bonus
        in_native = sorted(p for p, b in got.items() if abs(b) < 1e-6)
        reach_port = unit_threat_reach(enemy)
        by_d = {}
        for p, b in got.items():
            by_d.setdefault(hexgeo.distance(p, e_pos), []).append(abs(b) < 1e-6)
        print("kit=%s  positions=%d  port reach=%d" % (enemy, len(got), reach_port))
        for d in sorted(by_d):
            v = by_d[d]
            print("  d=%-2d natif in=%d/%d   port in=%s"
                  % (d, sum(1 for x in v if x), len(v), d <= reach_port))
        fn = [p for p in got if (abs(got[p]) < 1e-6)
              and not (hexgeo.distance(p, e_pos) <= reach_port)]
        fp = [p for p in got if (abs(got[p]) >= 1e-6)
              and (hexgeo.distance(p, e_pos) <= reach_port)]
        print("  faux negatifs=%d  faux positifs=%d  natif in=%d"
              % (len(fn), len(fp), len(in_native)))
        return 0
    finally:
        _dispose(sid, rid)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", default="all", choices=["gate", "sweep", "all"])
    ap.add_argument("--enemy", action="append", default=None)
    args = ap.parse_args()
    sid = _resolve_session()
    rc = 0
    if args.step in ("gate", "all"):
        rc |= step_gate(sid)
    if args.step in ("sweep", "all"):
        for enemy in (args.enemy or ["bloodDante", "astraDreir"]):
            print("")
            rc |= step_sweep(sid, enemy)
    return rc


if __name__ == "__main__":
    sys.exit(main())
