"""Diagnostic #213 -- ETAGE `amount` du ghost-revive : d'ou vient le PV de resurrection ?

Le probe live rend 4487, le port 3290 = round(TimeFlux.hp[L50] = 1828 x 180 %). On MESURE ici les
entrees de l'etage (niveau de passif, multiplicateur de rarete, PV max, table `hp`) au lieu de
fitter un scalaire. ASCII only.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))
from rl_collect_batch import _resolve_session, _rpc  # noqa: E402

ROOT = PYDIR.parents[1]
STATE = str(ROOT / "logs" / "_probe213_diag_state.json")
HERO = "thousTerminator"


def rpc(sid, m, args, t=90):
    return (_rpc(sid, m, [args], timeout=t).get("result") or {})


def main():
    import gameconfig as GC
    sid = _resolve_session()
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", "31337", "--rank", "17",
           "--p-units", HERO, "--a-units", "astraBullgryn",
           "--hp-player", "12000", "--dmg-target", "99999",
           "--no-ai", "--board", "MC1_67", "--state-file", STATE]
    p = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True)
    if p.returncode != 0:
        sys.stdout.write(p.stdout[-1200:] + p.stderr[-1200:])
        return 2
    rid = json.loads(Path(STATE).read_text(encoding="utf-8"))["runnerId"]
    try:
        dv = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)
        ob = rpc(sid, "observeBattle", {"runnerId": rid}, 60)
        snap = rpc(sid, "combatSnapshot", {"runnerId": rid}, 90)
        from engine.runner.snapshot import load_state
        from engine.runner.components import StatsComponent, HealthComponent
        st = load_state(dv, ob, snap)
        hid = None
        for u in (dv.get("units") or []):
            if u.get("visualId") == HERO:
                hid = u.get("id")
        e = st.get_entity(hid)
        sc = e.get_component(StatsComponent)
        hc = e.get_component(HealthComponent)
        ctx = sc.ctx
        print("unit=%s id=%s" % (HERO, hid))
        print("  passive_ability_level        = %s" % getattr(ctx, "passive_ability_level", None))
        print("  active_ability_level         = %s" % getattr(ctx, "active_ability_level", None))
        print("  ability_variables_multiplier = %s" % getattr(ctx, "ability_variables_multiplier", None))
        print("  hp / hp_max                  = %s / %s" % (hc.hp, hc.hp_max))
        tf = GC.ability("TimeFlux") or {}
        hp_tab = (tf.get("variables") or {}).get("hp") or []
        hth_tab = (tf.get("variables") or {}).get("hpToHeal") or []
        print("  len(hp table) = %d ; hp[L50]=%s hp[L65]=%s" % (
            len(hp_tab), hp_tab[49] if len(hp_tab) > 49 else None,
            hp_tab[64] if len(hp_tab) > 64 else None))
        from engine.entities.effects.magnitude import ability_var
        lvl = getattr(ctx, "passive_ability_level", None)
        mult = getattr(ctx, "ability_variables_multiplier", 100)
        print("  ability_var(TimeFlux,hp, lvl=%s, mult=%s)        = %s" % (
            lvl, mult, ability_var("TimeFlux", "hp", lvl, multiplier_pct=mult)))
        print("  ability_var(TimeFlux,hpToHeal, lvl=%s, mult=%s)  = %s" % (
            lvl, mult, ability_var("TimeFlux", "hpToHeal", lvl, multiplier_pct=mult)))
        print("  ability_var(TimeFlux,maxHpToHeal,lvl=%s,mult=%s) = %s" % (
            lvl, mult, ability_var("TimeFlux", "maxHpToHeal", lvl, multiplier_pct=mult)))
        # ecart mesure = 4487 ; on cherche la combinaison (index, mult) qui le produit EXACTEMENT
        target = 4487
        hits = []
        for i, v in enumerate(hp_tab):
            for m in (100, 110, 120, 130, 140, 150, 160, 170, 175, 180, 190, 200, 210, 220):
                if round(v * m / 100.0) == target:
                    hits.append(("hp", i + 1, m, v))
        for i, v in enumerate(hth_tab):
            for m in (100, 150, 180, 200):
                if round(v * m / 100.0) == target:
                    hits.append(("hpToHeal", i + 1, m, v))
        print("  combinaisons (var, level, mult%%, base) donnant EXACTEMENT %d : %s" % (target, hits))
        print("  somme hp+hpToHeal (lvl=%s mult=%s) = %s" % (
            lvl, mult,
            (ability_var("TimeFlux", "hp", lvl, multiplier_pct=mult) or 0)
            + (ability_var("TimeFlux", "hpToHeal", lvl, multiplier_pct=mult) or 0)))
        return 0
    finally:
        rpc(sid, "disposeRunner", {"runnerId": rid}, 60)


if __name__ == "__main__":
    sys.exit(main())
