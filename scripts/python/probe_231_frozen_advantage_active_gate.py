#!/usr/bin/env python
"""#231 -- GENERALISATION du gate `IsActive @+0x5c` du rail TARGETS de l'effet 1201
(`AnvilShield_FrozenAttackerAdvantage`, porteur `spaceRockfist` << Arjac >>).

Le trigger propre de 1201 vient de
`IdunBattle.Entities.Effects.Loki.AnvilShield_FrozenAttackerAdvantageEffect$$CreateTargetTrigger`
(`On(0xe = UnitPostAbility) & AreEqual(target@0x178, EffectSource(this@0x150))`) -- donc du rail
evalue par `IdunBattle.Operations.EvaluateTriggerOperation$$EvaluateEffectTriggerTargets`, qui, DANS
sa boucle PAR CIBLE, recharge l'`EffectComponent` depuis l'entite-effet et n'appelle `ShouldTrigger`
(slot 0x13) puis `Execute` (slot 0x14) que `if (*(char *)(comp + 0x5c) != 0)`.

TABLE DE VERITE mesuree ici -- le trigger ne doit firer QUE sur (instance ACTIVE) ET
(target == porteur) :

  cas                  | 1201 actif | target      | 1200 actif | fire attendu
  ---------------------|------------|-------------|------------|-------------
  active_owner         | oui        | Arjac       | non        | OUI
  inactive_owner       | NON        | Arjac       | non        | non   <- le gate #231
  active_other         | oui        | attaquant   | non        | non   (AreEqual)
  inactive_other       | NON        | attaquant   | non        | non
  inactive_owner_lowhp | NON        | Arjac       | OUI        | non   <- gate 1201 != canal 1200

Chaque cas repart d'un etat OFFLINE FRAIS recharge depuis le MEME live (positions, glace, stats et
magnitude du canal stat 7 viennent tous du montage live). Les SEULES variables injectees sont celles
de la table : le flag `active` de l'instance (mirror de
`IdunBattle.Operations.RefreshEffectsOperation$$DeactivateEffect`, qui ecrit `+0x5c = 0`) et la cible
de l'evenement.

Deux montages (board, seed) pour que le verdict ne tienne pas a une geometrie.

Usage :  python probe_231_frozen_advantage_active_gate.py [--keep]
Sortie ASCII only (cp1252).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import hexgeo                                            # noqa: E402
from rl_collect_batch import _resolve_session, _rpc      # noqa: E402
from engine.entities.effect_type import EffectType       # noqa: E402
from engine.entities.pathfinding.board import Board      # noqa: E402
from engine.entities.stats import StatType               # noqa: E402
from engine.runner.snapshot import load_state            # noqa: E402
from engine.runner.components import (PositionComponent, StatsComponent,   # noqa: E402
                                      HealthComponent)
from engine.runner.operations.triggers.dispatch import (pre_unit_ability_triggers,   # noqa: E402
                                                        unit_post_ability_triggers)

ARJAC = "spaceRockfist"
ATTACKER = "templSwordBrother"                     # MELEE -> il bloque/est bloque au contact
ICE = int(EffectType.Ice)                          # 0x11
FROZEN = int(EffectType.AnvilShield_FrozenAttackerAdvantage)     # 0x4b1 = 1201
LOGS = HERE.parents[1] / "logs"

# (board, seed) -- deux geometries distinctes pour que le verdict ne tienne pas au terrain.
MONTAGES = [("MC1_67", 92231), ("C4_09", 92232)]


def _r(sid, m, b, t=180):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def dv(sid, rid):
    return _r(sid, "decisionView", {"runnerId": rid, "maxRank": 99, "allAbilities": True}, 300)


def act(sid, rid, action):
    return _r(sid, "applyAction", {"runnerId": rid, "action": action, "captureEvents": False}, 300)


def alive(dec, vis):
    return [u for u in (dec.get("units") or []) if u.get("visualId") == vis and u.get("alive")]


def by_id(dec, uid):
    return next((u for u in (dec.get("units") or []) if u.get("id") == uid), None)


def pos(u):
    p = (u or {}).get("pos") or {}
    return (p.get("col"), p.get("row"))


def iced(sid, rid):
    tm = _r(sid, "tileMeta", {"runnerId": rid}, 300)
    return {(t.get("col"), t.get("row"))
            for t in (tm.get("tiles") or [])
            if any(e.get("effectType") == ICE for e in (t.get("effects") or []))}


def movable(sid, rid, uid):
    mov = _r(sid, "aiMovableTiles", {"runnerId": rid, "side": "all"}, 300)
    for m in (mov.get("units") or []):
        if m.get("unitId") == uid:
            return [(t["col"], t["row"]) for t in (m.get("tiles") or [])]
    return []


def normal_attack_id(dec, uid):
    u = by_id(dec, uid)
    for ab in ((u or {}).get("abilities") or []):
        if ab.get("kind") == "normal":
            return ab.get("id")
    return None


def ensure_ice(sid, rid, att_id, arj_id, tries=12):
    """Fait FRAPPER Arjac par l'attaquant jusqu'a ce que la tuile de l'attaquant soit GLACEE.

    Chaque coup MELEE bloque declenche
    `IdunBattleLogic.Entities.Abilities.Triggered.Loki.AnvilShieldAbility_ApplyIce$$CreateBehaviour`
    = `AddEffect(0x11 = Ice, cible = CasterTile@0x168)`. On ne CRAFTE donc plus le blocage a 100 %
    (le clamp `STAT_CLAMP_MAX[7] = 100` rendrait le canal stat 7 aveugle) : on le laisse a 60 % et
    on repete les coups jusqu'a obtenir la glace."""
    aid = normal_attack_id(dv(sid, rid), att_id)
    if aid is None:
        return False
    for _ in range(tries):
        if pos(by_id(dv(sid, rid), att_id)) in iced(sid, rid):
            return True
        dec = dv(sid, rid)
        att = by_id(dec, att_id)
        if att is None or not att.get("alive"):
            return False
        if dec.get("currentPlayer") != att.get("owner"):
            act(sid, rid, {"kind": "endturn"})
            continue
        act(sid, rid, {"kind": "ability", "casterId": att_id, "targetId": arj_id,
                       "abilityType": aid})
        act(sid, rid, {"kind": "endturn"})
    return pos(by_id(dv(sid, rid), att_id)) in iced(sid, rid)


def bring_adjacent(sid, rid, rounds=30):
    """Amene l'attaquant MELEE au contact d'Arjac en ne deplacant QUE l'attaquant (driver les deux
    camps est permis, mais faire marcher Arjac declencherait l'overwatch adverse)."""
    for _ in range(rounds):
        dec = dv(sid, rid)
        me = alive(dec, ATTACKER)
        ens = [u for u in alive(dec, ARJAC) if pos(u)[0] is not None]
        if not me or not ens:
            act(sid, rid, {"kind": "endturn"})
            continue
        att, arj = me[0], ens[0]
        if dec.get("currentPlayer") != att.get("owner"):
            act(sid, rid, {"kind": "endturn"})
            continue
        if hexgeo.distance(pos(att), pos(arj)) <= 1:
            return dec, att, arj
        tiles = movable(sid, rid, att["id"])
        if not tiles:
            act(sid, rid, {"kind": "endturn"})
            continue
        best = min(tiles, key=lambda t: hexgeo.distance(t, pos(arj)))
        act(sid, rid, {"kind": "move", "unitId": att["id"],
                       "to": {"col": best[0], "row": best[1]}})
    return None, None, None


def offline(sid, rid):
    bg = _r(sid, "boardGraph", {"runnerId": rid}, 120)
    board = Board(bg["tiles"], adjacency="evenq") if bg.get("tiles") else None
    dec = dv(sid, rid)
    ob = _r(sid, "observeBattle", {"runnerId": rid}, 120)
    snap = _r(sid, "combatSnapshot", {"runnerId": rid}, 300)
    tm = _r(sid, "tileMeta", {"runnerId": rid}, 120)
    return load_state(dec, ob, snap, board=board, tiles=tm), board


def off_effect(state, uid, etype):
    if state.effects is None:
        return None
    for e in state.effects.by_unit.get(int(uid), []):
        if not e.consumed and e.effect_type == int(etype):
            return e
    return None


def block_chance(state, uid):
    return state.get_entity(uid).get_component(StatsComponent).ctx.stat(StatType.BLOCK_CHANCE)


def build(seed, board):
    LOGS.mkdir(parents=True, exist_ok=True)
    state_file = LOGS / ("_p231_%s_%s.json" % (board, seed))
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--board", board,
           "--p-units", "%s,templAggressor" % ATTACKER, "--a-units", ARJAC,
           # 60 % et non 100 % : a 100 le `blockChance` de base sature le clamp stat 7 (100) et le
           # canal du +20 % deviendrait INOBSERVABLE. `ensure_ice` compense par la repetition.
           "--block-target", "60,500", "--hp-target", "400000", "--hp-player", "400000",
           "--state-file", str(state_file)]
    subprocess.run(cmd, cwd=str(HERE), check=True)
    return int(json.loads(state_file.read_text())["runnerId"])


# --- cas de la matrice : (nom, active, cible = 'owner'|'other', low_hp, fire attendu) -------------
CASES = [
    ("active_owner",         True,  "owner", False, True),
    ("inactive_owner",       False, "owner", False, False),
    ("active_other",         True,  "other", False, False),
    ("inactive_other",       False, "other", False, False),
    ("inactive_owner_lowhp", False, "owner", True,  False),
]


def run_case(sid, rid, att_id, arj_id, name, active, target, low_hp):
    """Recharge un etat FRAIS, pose 1201 par le vrai vecteur, applique la mutation du cas, emet
    `On(UnitPostAbility)`. Renvoie (fired, detail) ou (None, raison) si le montage ne tient pas."""
    state, board = offline(sid, rid)
    if board is None:
        return None, "boardGraph indispo"
    apc = state.get_entity(att_id).get_component(PositionComponent)
    if not state.effects.has_effect(board.id_at(apc.col, apc.row), effect_type=ICE):
        return None, "tuile de l'attaquant non glacee dans l'etat charge"
    base_bc = block_chance(state, arj_id)
    pre_unit_ability_triggers(state, att_id, arj_id, ranged=False, profile="Power",
                              ability_type=1013)
    inst = off_effect(state, arj_id, FROZEN)
    if inst is None:
        return None, "1201 non pose par On(PreUnitAbility)"
    bonus_bc = block_chance(state, arj_id)

    inst.active = bool(active)          # RefreshEffectsOperation$$Activate/DeactivateEffect (+0x5c)
    if low_hp:                          # 1200 devient ACTIF (ActiveCondition healthPct)
        hc = state.get_entity(arj_id).get_component(HealthComponent)
        hc.hp = max(1, int(hc.hp_max * 0.10))
    tgt = arj_id if target == "owner" else att_id
    unit_post_ability_triggers(state, att_id, tgt, ranged=False, profile="Power",
                               ability_type=1013)

    fired = off_effect(state, arj_id, FROZEN) is None
    after_bc = block_chance(state, arj_id)
    ok_bc = (after_bc == base_bc) if fired else (after_bc == bonus_bc)
    return fired, "bc %s->%s->%s%s" % (base_bc, bonus_bc, after_bc, "" if ok_bc else " BC-KO")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true", help="ne pas disposer les runners")
    args = ap.parse_args()

    sid = _resolve_session()
    print("=== #231 gate IsActive du rail TARGETS (effet 1201) ===")
    print("session=%s" % sid)
    ok = True
    tested = 0
    for board, seed in MONTAGES:
        rid = build(seed, board)
        try:
            dec, att, arj = bring_adjacent(sid, rid)
            if att is None:
                print("[%s/%s] SKIP montage (unites injoignables)" % (board, seed))
                continue
            if not ensure_ice(sid, rid, att["id"], arj["id"]):
                print("[%s/%s] SKIP montage (tuile de l'attaquant non glacee)" % (board, seed))
                continue
            print("")
            print("[%s/%s] runner=%s attaquant=%s Arjac=%s"
                  % (board, seed, rid, att["id"], arj["id"]))
            print("  %-22s %-7s %-6s %-7s %-6s %-6s %s"
                  % ("cas", "actif", "cible", "1200", "attdu", "obs", "detail"))
            for name, active, target, low_hp, want in CASES:
                fired, detail = run_case(sid, rid, att["id"], arj["id"],
                                         name, active, target, low_hp)
                if fired is None:
                    print("  %-22s SKIP (%s)" % (name, detail))
                    continue
                tested += 1
                good = (fired == want) and ("BC-KO" not in detail)
                ok = ok and good
                print("  %-22s %-7s %-6s %-7s %-6s %-6s %s%s"
                      % (name, "oui" if active else "NON", target,
                         "oui" if low_hp else "non",
                         "fire" if want else "inert", "fire" if fired else "inert",
                         detail, "" if good else "   <-- ECART"))
        finally:
            if not args.keep:
                _r(sid, "disposeRunner", {"runnerId": rid}, 60)

    print("")
    print("cas mesures : %d" % tested)
    if tested == 0:
        print("RESULT: FAIL (aucun cas mesure -- montage non atteint)")
        return 1
    print("RESULT: %s" % ("OK" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
