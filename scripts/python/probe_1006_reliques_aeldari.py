"""Probe #1006 -- reliques AELDARI `Maugetar` (1498) / `PhoenixGem` (1458) : ce que le SUBSTRAT publie.

MESURE, pas garde. Repond aux trois questions que le port ne peut pas deviner :

  1. l'effet de la relique EST-IL pose par le natif quand on monte `--equip-relic` ?
     (la prose de `test_revive_retrofit_offline_live.py` dit « non posable via rl_duel build » --
      premisse anterieure au montage #237) ;
  2. quel NIVEAU / MULTIPLICATEUR l'instance d'effet porte-t-elle ? (relique = etat TERTIAIRE, pas
     l'etat PASSIF, qui vaut 50 sur tout runner normalise -- l'ecart est SILENCIEUX) ;
  3. le canal `additional_hit_groups` rend-il un groupe pour `Maugetar_HasNotMoved` (1497) ?

Usage (depuis `scripts/python`, ASCII only) :

    python probe_1006_reliques_aeldari.py --state-file <ABSOLU>.json
    python probe_1006_reliques_aeldari.py --build --state-file <ABSOLU>.json [--board MC1_67]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from rl_collect_batch import _rpc, _resolve_session          # noqa: E402
from engine.runner.snapshot import load_state
from engine.entities.pathfinding.board import Board
from engine.runner.components import UnitComponent, StatsComponent
from engine.entities.effect_type import EffectType

MAUGETAR_HAS_NOT_MOVED = int(EffectType.Maugetar_HasNotMoved)     # 0x5d9 = 1497
PHOENIX_GEM_CAN_REVIVE = int(EffectType.PhoenixGem_CanRevive)     # 0x5ab = 1451
WATCHED = {MAUGETAR_HAS_NOT_MOVED: "Maugetar_HasNotMoved",
           PHOENIX_GEM_CAN_REVIVE: "PhoenixGem_CanRevive"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True)
    args = ap.parse_args()

    st_file = Path(args.state_file)
    if not st_file.exists():
        print("ABSENT: %s -- monter le runner d'abord (rl_duel build --equip-relic ...)" % st_file)
        return 2
    meta = json.loads(st_file.read_text(encoding="utf-8"))
    rid = int(meta["runnerId"])
    sess = _resolve_session()
    print("runner=%d session=%s" % (rid, sess))

    # CANAL AMBIANT `unitAbilityStates` (#363) : sans lui, `UnitContext.tertiary_ability` reste
    # `None` et `triggered_ability_state` retombe sur l'etat PASSIF -- exactement l'ecart qu'on
    # cherche a mesurer. Le harnais de test le lie via `tests/conftest.py` ; un probe doit le faire.
    from engine.runner.snapshot import bind_live_rpc
    bind_live_rpc(lambda method, body=None, timeout=60:
                  (lambda r: r.get("result") if isinstance(r, dict) and "result" in r else r)(
                      _rpc(sess, method, body if body is not None else {}, int(timeout))))

    def rpc(name, params, to):
        """`_rpc` rend l'enveloppe `{result: <payload>}` sur cette voie ; on DEBALLE, sans
        fabriquer de succes quand la cle manque."""
        r = _rpc(sess, name, params, to)
        return r.get("result") if isinstance(r, dict) and "result" in r else r

    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    for nm, r in (("boardGraph", bg), ("decisionView", dv), ("observeBattle", ob),
                  ("combatSnapshot", snap)):
        if not (isinstance(r, dict) and r.get("ok")):
            print("RPC KO: %s -> %s" % (nm, str(r)[:200]))
            return 3
    board = Board(bg["tiles"], adjacency="evenq")
    state = load_state(dv, ob, snap, board=board)
    if getattr(state, "effects", None) is None:
        print("pas d'EffectsState")
        return 3

    found = 0
    for uid, ent in state.entities.items():
        uc = ent.get_component(UnitComponent)
        sc = ent.get_component(StatsComponent)
        ctx = sc.ctx if sc is not None else None
        insts = state.effects.by_unit.get(int(uid)) or []
        for e in insts:
            et = int(getattr(e, "effect_type", -1) or -1)
            if et not in WATCHED:
                continue
            found += 1
            print("u%s [%s] effet %d %s : name=%r classe=%s" % (
                uid, getattr(uc, "visual_id", "?"), et, WATCHED[et],
                getattr(e, "name", None), type(e).__name__))
            print("    ability_level=%r level=%r active_ability_level=%r mult=%r consumed=%r" % (
                getattr(e, "ability_level", None), getattr(e, "level", None),
                getattr(e, "active_ability_level", None),
                getattr(e, "ability_variables_multiplier", None), getattr(e, "consumed", None)))
            print("    ctx.tertiary_ability=%r level=%r mult=%r | passive_ability_level=%r" % (
                getattr(ctx, "tertiary_ability", None),
                getattr(ctx, "tertiary_ability_level", None),
                getattr(ctx, "tertiary_ability_variables_multiplier", None),
                getattr(ctx, "passive_ability_level", None)))
            # Les DEUX regimes du gate `AttackDamageIsCritical`, plus le tri-etat « non mesure » :
            # un groupe rendu sans crit serait une sur-application, un groupe absent AVEC crit un
            # port inerte. Le troisieme appel force le niveau TERTIAIRE par le callable du ctx.
            from engine.runner.operations.triggers.base import triggered_ability_state
            for lbl, extra in (("sans crit", {"attack_had_critical": False}),
                               ("crit", {"attack_had_critical": True}),
                               ("non mesure", {}),
                               ("crit + etat tertiaire", {
                                   "attack_had_critical": True,
                                   "tertiary_ability_state_of":
                                       lambda oid, ab: triggered_ability_state(state, int(oid), ab)})):
                base = {"owner_id": int(uid), "att_id": int(uid), "is_melee": False}
                try:
                    grp = e.additional_hit_groups({**base, **extra})
                except Exception as exc:  # noqa: BLE001 -- on VEUT voir l'echec, pas le masquer
                    grp = "EXC %s" % exc
                print("    additional_hit_groups [%s] -> %r" % (lbl, grp))
            if et == PHOENIX_GEM_CAN_REVIVE:
                # Le pendant MAGNITUDE de PhoenixGem : `GetVariableForLevel(0x1d = hp)`. On imprime
                # les DEUX lectures pour que l'ecart soit visible, pas deduit.
                from engine.entities.effects.magnitude import ability_var
                lv_t, mt = triggered_ability_state(state, int(uid), "PhoenixGem")
                lv_i = getattr(e, "active_ability_level", None) or getattr(e, "ability_level", None)
                print("    hp[etat TERTIAIRE lvl=%r] = %r | hp[instance lvl=%r] = %r" % (
                    lv_t, ability_var("PhoenixGem", "hp", lv_t, multiplier_pct=mt or 100),
                    lv_i, ability_var("PhoenixGem", "hp", lv_i,
                                      multiplier_pct=getattr(e, "ability_variables_multiplier", 100))))
    if not found:
        print("AUCUNE instance des effets surveilles -- la relique n'est PAS montee")
        return 1
    print("instances trouvees: %d" % found)
    return 0


if __name__ == "__main__":
    sys.exit(main())
