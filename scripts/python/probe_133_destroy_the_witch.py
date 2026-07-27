"""Probe #133-A -- RECON LIVE du passif `DestroyTheWitch` (templHelbrecht, TriggeredAbilityType 1091).

Question mesuree : les DEUX owner-effects poses par
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.DestroyTheWitchAbility$$CreateBehaviour`
  - `DestroyTheWitch_ExtraMove`   (EffectType 1088, AddStaticStatModifierEffectToOwner MOVEMENT)
  - `DestroyTheWitch_ExtraDamage` (EffectType 1089, AddEffect(owner))
apparaissent-ils dans `decisionView.units[].effects` de Helbrecht,
  (a) AVEC un Psyker ENNEMI sur le plateau (condition active vraie),
  (b) SANS Psyker ennemi (condition active fausse -> `DestroyTheWitch_ExtraMove` doit DISPARAITRE,
      cf. `DestroyTheWitch_ExtraMoveEffect$$CreateActiveCondition` = >=1 ennemi trait Psyker) ?

On mesure AUSSI la stat MOVEMENT live (decisionView / combatSnapshot) dans les deux configurations :
c'est l'observable du volet mouvement.

Usage :  python probe_133_destroy_the_witch.py [--keep]
ASCII only (console cp1252).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import rl_collect_batch as R

PYDIR = Path(__file__).resolve().parent
LOGS = PYDIR.parents[1] / "logs" / "runners"

HELBRECHT = "templHelbrecht"
FRIEND = "templSwordBrother"     # allie MELEE adjacent -> volet AURA (+extraDmg aux amis adjacents)
PSYKER = "astraPrimarisPsy"      # trait Psyker (gate du volet MOVE et du volet DMG)
NONPSY = "orksNob"               # ennemi SANS trait Psyker -> cas NEGATIF


def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def build(sid, tag, a_units, p_units=None, board="MC1_67", seed="777"):
    LOGS.mkdir(parents=True, exist_ok=True)
    state = LOGS / ("dtw_%s.json" % tag)
    state.unlink(missing_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", seed,
            "--state-file", str(state), "--board", board,
            "--roster", "2", "--p-units", p_units or ("%s,%s" % (HELBRECHT, FRIEND)),
            "--a-units", a_units]
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state.exists():
        print("BUILD KO (%s): %s" % (tag, (p.stderr or p.stdout or "")[-500:]))
        return None, None
    st = json.loads(state.read_text())
    return st["runnerId"], state


def report(sid, rid, tag):
    dv = _unwrap(R._rpc(sid, "decisionView", [{"runnerId": rid, "maxRank": 1,
                                               "allAbilities": True}], timeout=90))
    if not (isinstance(dv, dict) and dv.get("ok")):
        print("[%s] decisionView KO: %s" % (tag, str(dv)[:200]))
        return
    print("=== %s ===" % tag)
    snap = _unwrap(R._rpc(sid, "combatSnapshot", [{"runnerId": rid}], timeout=40))
    stats = {}
    if isinstance(snap, dict):
        for u in (snap.get("units") or []):
            stats[u.get("id")] = u
    for u in (dv.get("units") or []):
        vid = u.get("visualId")
        su = stats.get(u.get("id")) or {}
        mv = su.get("movement")
        if mv is None:
            mv = (su.get("stats") or {}).get("movement")
        print("  u%-4s %-20s team=%s pos=%s movement=%s" % (
            u.get("id"), vid, u.get("owner"), u.get("pos"), mv))
        for e in (u.get("effects") or []):
            print("       eff %-42s type=%-6s lvl=%s statMod=%s" % (
                e.get("name"), e.get("effectType"), e.get("level"), e.get("statMod")))
    return dv


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--dump-unit", action="store_true", help="dump JSON brut de Helbrecht")
    args = ap.parse_args()
    sid = R._resolve_session()
    out = []
    cases = [
        # (tag, a_units, p_units)  -- p_units None = Helbrecht + allie melee
        ("enemy_psyker", "%s,%s" % (PSYKER, NONPSY), None),
        ("no_psyker", "%s,%s" % (NONPSY, "orksRuntherd"), None),
        # DISCRIMINANT : le Psyker est un ALLIE -> `Enemies(owner, UnitsWithTrait(Psyker))` vide
        ("ally_psyker", "%s,%s" % (NONPSY, "orksRuntherd"), "%s,%s" % (HELBRECHT, PSYKER)),
    ]
    for tag, a, p in cases:
        rid, state = build(sid, tag, a, p_units=p)
        if rid is None:
            continue
        out.append((rid, state))
        dv = report(sid, rid, tag)
        if args.dump_unit and dv:
            h = next((u for u in (dv.get("units") or []) if u.get("visualId") == HELBRECHT), None)
            print(json.dumps(h, indent=1)[:4000])
    if not args.keep:
        for rid, state in out:
            R._rpc(sid, "disposeRunner", [{"runnerId": rid}], timeout=20)
            state.unlink(missing_ok=True)
        print("[dispose] %s" % [r for r, _ in out])


if __name__ == "__main__":
    main()
