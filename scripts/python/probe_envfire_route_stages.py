#!/usr/bin/env python
"""Decomposition PAR ETAGE du DoT `EnvFireTile` : route `execute_direct` (percage/armure seuls) vs
route `AbilityDamageOperation` (`execute_ability_attack`, famille ABILITY).

Pour CHAQUE unite d'un runner live, imprime les entrees/sorties de chaque etage natif :
base Fix64 (`PercentageOf`), percage (`PiercingRatio(Flame)`), armure (`defender_fixed_armor`),
multiplicateur de coup CIBLE (`target_hit_multiplier`, trait MkXGravis 0x3f5), mods DEFENSEUR
(pct-list / additif / reductions plates / capees), etage LIMITES mode 2 (member-cap, Resilient),
puis le total des DEUX routes. Sert a localiser le PREMIER etage ou les deux divergent.
ASCII only. Usage: python probe_envfire_route_stages.py [--seed 777]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import gameconfig as GC  # noqa: E402
from rl_collect_batch import _resolve_session, _rpc  # noqa: E402
from engine.runner.snapshot import load_state  # noqa: E402
from engine.runner.components import HealthComponent, StatsComponent, UnitComponent  # noqa: E402
from engine.runner.damage_model import defender_fixed_armor, defender_modifiers  # noqa: E402
from engine.runner.operations.damage import AttackDamageOperation  # noqa: E402
from engine.runner.abilities.base import profile_pierce  # noqa: E402
from engine.entities.traits import target_hit_multiplier  # noqa: E402
from engine.entities.pathfinding.board import Board  # noqa: E402
from engine.entities.stats import StatType, StatPart  # noqa: E402
from engine.entities.selectors.accessors import Target  # noqa: E402
from engine.entities.formulas import PercentageOf, StatAmount  # noqa: E402
from engine.dsl.base import Const  # noqa: E402
from engine.runner.abilities.behaviours.context import entities_from_state  # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
STATE = ROOT / "logs" / "runners" / "_envfire_stages_state.json"


def _r(sid, m, b, t=90):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="777")
    ap.add_argument("--p-units", default=None)
    ap.add_argument("--a-units", default=None)
    ap.add_argument("--hp-target", default=None)
    args = ap.parse_args(argv)
    sid = _resolve_session()
    STATE.unlink(missing_ok=True)
    STATE.parent.mkdir(parents=True, exist_ok=True)
    extra = []
    if args.p_units:
        extra += ["--p-units", args.p_units]
    if args.a_units:
        extra += ["--a-units", args.a_units]
    if args.hp_target:
        extra += ["--hp-target", args.hp_target]
    subprocess.run([sys.executable, "rl_duel.py", "build", "--seed", args.seed,
                    "--state-file", str(STATE), "--board", "MC1_67", *extra],
                   cwd=str(PYDIR), capture_output=True, text=True,
                   encoding="utf-8", errors="replace")
    if not STATE.exists():
        print("[stages] build KO"); return 2
    rid = json.loads(STATE.read_text())["runnerId"]
    try:
        dv = _r(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True})
        ob = _r(sid, "observeBattle", {"runnerId": rid}, 40)
        snap = _r(sid, "combatSnapshot", {"runnerId": rid}, 40)
        bg = _r(sid, "boardGraph", {"runnerId": rid}, 60)
        board = Board(bg["tiles"], adjacency="native_sym") if bg.get("tiles") else None
        st = load_state(dv, ob, snap, board=board)
        pct = int(GC.global_value("fireDmgPct") or 20)
        pierce = int(profile_pierce(None, "Flame", ranged=False))
        print(f"[stages] runner={rid} pct={pct} pierce={pierce}")
        amount = PercentageOf(Const(pct), StatAmount(Target(), int(StatType.HEALTH),
                                                     int(StatPart.MAXIMUM)))
        for eid, e in list(st.entities.items()):
            thc = e.get_component(HealthComponent)
            tsc = e.get_component(StatsComponent)
            tuc = e.get_component(UnitComponent)
            if thc is None or tsc is None or tuc is None:
                continue
            vis = tuc.visual_id
            traits = sorted((GC.unit(vis) or {}).get("traits") or [])
            base = int(amount.evaluate(entities_from_state(st, eid, eid)))
            armor = defender_fixed_armor(st, eid)
            hit_mult = target_hit_multiplier(tsc.ctx.trait_objects())
            dmods, _da = defender_modifiers(st, eid, thc.hp, is_melee=None,
                                            damage_profile="Flame", attacker_id=None,
                                            is_normal_attack=False)
            limits = AttackDamageOperation._target_limits(e, thc, "Flame", is_special=2)
            print(f"\n  u{eid} {vis} hp={thc.hp}/{thc.hp_max} traits={traits}")
            print(f"    base={base} pierce={pierce} armor={armor} hit_mult={hit_mult}")
            print(f"    def_mods: pct_list={dmods.pct_list} additive={dmods.additive} "
                  f"flat_red={getattr(dmods, 'flat_reductions', None)} "
                  f"capped={getattr(dmods, 'capped_reductions', None)}")
            print(f"    limits(mode2)={limits}")
        return 0
    finally:
        _r(sid, "disposeRunner", {"runnerId": rid}, 15)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
