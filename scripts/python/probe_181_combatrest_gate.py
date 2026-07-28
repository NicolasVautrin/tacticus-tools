"""Diagnostic #181 : pourquoi le cast SELF de CombatRestoratives (1002) est-il refuse offline ?

Reproduit la fixture de `tests/engine/runner/test_combat_restoratives_live.py` (caster central,
allies sur les voisins, HP-20000) et decompose la cascade etage par etage. ASCII only.
"""
from __future__ import annotations

import json
import subprocess
import sys
import urllib.request
from pathlib import Path

from engine.entities.pathfinding.board import Board
from engine.runner.abilities.handler import ABILITY_CLASSES
from engine.runner.abilities import targeting as T
from engine.runner.abilities.targeting_rule import TargetingRule as TR
from engine.runner.components import (PositionComponent, StatsComponent, HealthComponent, OwnerComponent)
from engine.runner.snapshot import load_state

HOST = "http://127.0.0.1:8765"
ABILITY = 1002
CASTER = "ultraApothecary"
BUILD = ["--p-units", "ultraApothecary,adeptHospitaller,eldarRanger,deathBlightbringer,necroWarden",
         "--a-units", "worldKharn,ultraTitus", "--rank", "17", "--hp-player", "300000",
         "--board", "MC1_67"]


def _sid() -> int:
    with urllib.request.urlopen(HOST + "/api/admin/status", timeout=10) as r:
        return json.loads(r.read())["session"]["id"]


def rpc(sid, method, body, timeout=90):
    payload = json.dumps({"method": method, "args": [body]}).encode()
    req = urllib.request.Request(HOST + "/api/scripts/%d/rpc" % sid, data=payload,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        out = json.loads(r.read())
    return out.get("result", out)


def main() -> int:
    sid = _sid()
    state_file = Path(__file__).with_name("_probe181_gate.json")
    state_file.unlink(missing_ok=True)
    subprocess.run([sys.executable, "rl_duel.py", "build", "--seed", "777",
                    "--state-file", str(state_file), *BUILD],
                   cwd=str(Path(__file__).parent), capture_output=True, text=True)
    if not state_file.exists():
        print("build KO")
        return 1
    rid = json.loads(state_file.read_text())["runnerId"]
    print("runner", rid)

    bg = rpc(sid, "boardGraph", {"runnerId": rid}, 60)
    board = Board(bg["tiles"], adjacency="native_sym")
    dv = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True})
    ob = rpc(sid, "observeBattle", {"runnerId": rid}, 40)
    snap = rpc(sid, "combatSnapshot", {"runnerId": rid}, 40)
    state = load_state(dv, ob, snap, board=board)

    def by_vis(vis):
        for uid, e in state.entities.items():
            sc = e.get_component(StatsComponent)
            if sc is not None and getattr(sc.ctx, "visual_id", None) == vis:
                return uid
        return None

    ids = {k: by_vis(v) for k, v in (("apo", CASTER), ("imp", "adeptHospitaller"),
                                     ("xen", "eldarRanger"), ("cha", "deathBlightbringer"),
                                     ("mech", "necroWarden"))}
    apo = ids["apo"]
    if any(v is None for v in ids.values()):
        print("roster incomplet", ids)
        return 1

    # FIXTURE COMPLETE, recopiee de tests/engine/runner/test_combat_restoratives_live.py
    center = None
    for uid, e in state.entities.items():
        pc = e.get_component(PositionComponent)
        if pc is None:
            continue
        t = board.id_at(pc.col, pc.row)
        if t is not None and len([n for n in board.neighbours(t) if board.walkable(n)]) >= 4:
            center = board.coord(t)
            break
    # QUI occupe deja la tuile "centre" que la fixture donne au caster ?
    occupants = []
    for uid, e in state.entities.items():
        pc = e.get_component(PositionComponent)
        sc = e.get_component(StatsComponent)
        if pc is not None and (pc.col, pc.row) == center:
            oc = e.get_component(OwnerComponent)
            occupants.append((uid, getattr(sc.ctx, "visual_id", None) if sc else None,
                              getattr(oc, "team", None) if oc else None))
    print("occupants de la tuile centre %s AVANT teleportation : %s" % (center, occupants))
    p = state.get_entity(apo).get_component(PositionComponent)
    p.col, p.row = center
    neigh = [board.coord(n) for n in board.neighbours(board.id_at(*center)) if board.walkable(n)]
    for uid, c in zip((ids["imp"], ids["xen"], ids["cha"], ids["mech"]), neigh):
        q = state.get_entity(uid).get_component(PositionComponent)
        q.col, q.row = c
    for uid in ids.values():
        hh = state.get_entity(uid).get_component(HealthComponent)
        hh.hp = int(hh.hp_max) - 20000
    print("placement: apo=%s neigh=%s" % (center, neigh[:4]))

    ability = ABILITY_CLASSES[ABILITY]()
    opts = ability.TARGETING_OPTIONS
    print("masque  : rules=%#x self_cast=%s range=%s fmt=%s"
          % (int(opts.rules), opts.self_cast, opts.range, opts.force_melee_target))
    print("caster  = %d, cible = LUI-MEME" % apo)
    print("  get_invalid_caster_reason      = %#x"
          % T.get_invalid_caster_reason(state, apo, ability))
    o2 = T.set_config_values_in_targeting_options(opts, ability)
    print("  options apres set_config       : range=%s" % (o2.range,))
    tu = T._unit_of(state, apo)
    tuid = None if tu is None else apo
    print("  _unit_of(cible)                = %s (tuid=%s)" % (tu, tuid))
    print("  _targets_the_caster            = %s"
          % T._targets_the_caster(state, apo, apo, tuid, o2))
    print("  get_range                      = %s" % (T.get_range(state, apo, o2),))
    print("  get_range_broken_rule          = %#x"
          % T.get_range_broken_rule(state, apo, apo, o2))
    r = T.get_invalid_target_reason(state, apo, apo, ability)
    print("  get_invalid_target_reason      = %#x %s"
          % (r, TR(r).name if r else ""))
    print("  is_invalid_target (VERDICT)    = %#x"
          % T.is_invalid_target(state, apo, apo, ability))

    # --- le CAST reel, tel que le test le joue (Runner + handler complet)
    from engine.runner.runner import Runner
    from engine.runner.messages import ActiveAbilityMessage
    pre = {k: int(state.get_entity(u).get_component(HealthComponent).hp) for k, u in ids.items()}
    runner = Runner(state).install_default_handlers(20)
    runner.apply(ActiveAbilityMessage(caster_id=apo, target_id=apo, ability_type=ABILITY))
    last = runner.ability_handler.last or {}
    post = {k: int(state.get_entity(u).get_component(HealthComponent).hp) for k, u in ids.items()}
    print("  handler.last                   = %s" % {k: v for k, v in last.items()
                                                     if k in ("ported", "invalid_target",
                                                              "actor_dead", "dsl", "heals",
                                                              "imperial_amount", "sans_amount",
                                                              "replaced_aborted", "replaced_from", "replaced_target")})
    print("  deltas HP                      = %s" % {k: post[k] - pre[k] for k in ids})

    nat = rpc(sid, "abilityReason", {"runnerId": rid, "casterId": apo,
                                     "abilityType": ABILITY, "targetId": apo}, 60) or {}
    print("  NATIF targetReason             = %s %s"
          % ((nat.get("targetReason") or {}).get("hex"),
             (nat.get("targetReason") or {}).get("reasons")))
    print("  NATIF casterReason             = %s %s"
          % ((nat.get("casterReason") or {}).get("hex"),
             (nat.get("casterReason") or {}).get("reasons")))
    rpc(sid, "disposeRunner", {"runnerId": rid}, 20)
    state_file.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
