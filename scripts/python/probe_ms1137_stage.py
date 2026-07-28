#!/usr/bin/env python
"""DECOMPOSITION PAR ETAGE du degat de 1137 MurderousSwing -- l'outil qui a trouve l'aura.

On ne fitte AUCUN scalaire. On imprime, etage par etage, ce que le port LIT et CALCULE, puis on
confronte au degat LIVE du MEME cast :

  1. `ctx` du caster        : `active_ability_level`, `ability_variables_multiplier`
  2. config brute           : `minDmg[lvl]` / `maxDmg[lvl]` / `extraDmg[lvl]`
  3. `ability_var`          : les memes, SCALES par le multiplier de rarete
  4. `ability_attack_params`: `(bmin, bmax, pierce, hits)` reellement passes a la feuille
  5. REPONSE DU PIPELINE    : le meme `AttackDamageOperation.execute_ability_attack` rejoue a base
     FIXE (1000, 2000) sur chaque cible -> le facteur (armure/percage/effets) par cible
  6. LIVE vs OFFLINE        : le degat par cible

C'est l'etage 5 qui rend le diagnostic possible : le facteur etant LINEAIRE en la base, un ecart
LIVE/OFFLINE d'un rapport CONSTANT sur DEUX cibles d'armures differentes ne peut PAS venir du
noeud de degat -- il vient d'un modificateur que le port ne porte pas. Mesure du 2026-07-28 :
rapport 2,000 exact sur les deux cibles -> `SereneUnifierSenseOfStone` (aura d'equipe de
`tauAunShi`, effet 1169 sans classe d'effet portee = `BaseEffect` nu). Roster change, rapport 1,000.

ASCII only (cp1252). Usage :
  python probe_ms1137_stage.py --k 2
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

import gameconfig as GC                                              # noqa: E402
import probe_murderous_swing_1137 as MS                              # noqa: E402
from engine.runner.snapshot import load_state                        # noqa: E402
from engine.runner.abilities.base import ability_attack_params       # noqa: E402
from engine.runner.components import StatsComponent                  # noqa: E402
from engine.runner.operations.damage import AttackDamageOperation    # noqa: E402
from engine.entities.effects.magnitude import ability_var            # noqa: E402


def _state(r):
    s = r["snapshot"]
    st = load_state(s["dv"], s["ob"], s["snap"], board=r["board"])
    st.rng = MS.seed_rng(s["rng"])
    return st


def stages(r):
    st = _state(r)
    caster, targets = r["caster"], r["adjacent"]
    ce = st.get_entity(caster)
    sc = ce.get_component(StatsComponent) if ce is not None else None
    ctx = sc.ctx if sc is not None else None
    lvl = getattr(ctx, "active_ability_level", 0) if ctx is not None else 0
    mult = int(getattr(ctx, "ability_variables_multiplier", 100) or 100) if ctx is not None else 100
    print("[1] ctx    level=%s mult=%s" % (lvl, mult))
    v = (GC.ability("MurderousSwing") or {}).get("variables") or {}

    def at(key):
        seq = v.get(key) or []
        return seq[lvl] if 0 <= lvl < len(seq) else None
    print("[2] config brut  minDmg=%s maxDmg=%s extraDmg=%s" % (at("minDmg"), at("maxDmg"),
                                                                at("extraDmg")))
    print("[3] ability_var  minDmg=%s maxDmg=%s extraDmg=%s"
          % (ability_var("MurderousSwing", "minDmg", lvl, multiplier_pct=mult),
             ability_var("MurderousSwing", "maxDmg", lvl, multiplier_pct=mult),
             ability_var("MurderousSwing", "extraDmg", lvl, multiplier_pct=mult)))
    p = ability_attack_params(st, caster, "MurderousSwing", "Piercing", ranged=False)
    print("[4] params       bmin=%s bmax=%s pierce=%s hits=%s" % p)
    for t in targets:
        row = []
        for base in (1000, 2000):
            s2 = _state(r)
            a = AttackDamageOperation.execute_ability_attack(
                s2, caster, t, base, base, p[2], p[3], damage_profile="Piercing", is_melee=True,
                ability_type=MS.ABILITY, is_attack_damage_op=True)
            row.append("%d->%s" % (base, (a or {}).get("total")))
        print("[5] pipeline u%-4s %s" % (t, " ".join(row)))
    off = {}
    for h in (r["last"].get("hits") or []):
        a = h.get("attack") or {}
        off[h.get("target")] = list(a.get("per_hit") or [])
    print("[6] LIVE %s" % r["live_damage"])
    print("[6] OFF  %s  (deltas=%s)" % (off, r["last"].get("per_target_delta")))
    for t in targets:
        lv = sum(r["live_damage"].get(t) or [])
        ov = sum(off.get(t) or [])
        print("[6] u%-4s live=%s off=%s ratio=%s"
              % (t, lv, ov, ("%.4f" % (ov / lv)) if lv else "n/a"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=2)
    ap.add_argument("--seed", type=int, default=20137)
    ap.add_argument("--hp-target", type=int, default=500000)
    ap.add_argument("--board", default="MC1_67")
    a = ap.parse_args()
    r = MS.run(a.k, a.seed, a.hp_target, verbose=False, board_id=a.board)
    if "error" in r:
        print("[stage] ERROR: %s" % r["error"])
        return 1
    stages(r)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
