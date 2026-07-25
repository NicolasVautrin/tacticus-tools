#!/usr/bin/env python
"""Probe du lot << l'effet est porte, la pose manque >> -- 4 maillons de POSE cables :

  1. MasterAnnihilator (admecDominus)  : pose du marqueur 1249 + REMOVE-BY-SOURCE  (IdunBattleLogic.Entities.Abilities.Triggered.Loki.MasterAnnihilatorAbility$$CreateTrigger/IdunBattleLogic.Entities.Abilities.Triggered.Loki.MasterAnnihilatorAbility$$CreateBehaviour)
  2. FleshmetalGuns    (blackObliterator) : ROTATION turn-start des effets 1067/1212/1221 (IdunBattleLogic.Entities.Abilities.Triggered.Loki.ArchContaminatorAbility$$CreateTrigger/IdunBattleLogic.Entities.Abilities.Active.Loki.FleshMetalGunsAbility$$CreateBehaviour)
  3. TerrifyingCrescendo (emperNoiseMarine) : ACCUMULATION du stack de 1424 (IdunBattleLogic.Entities.Abilities.Triggered.Loki.TerrifyingCrescendoAbility$$CreateTrigger/IdunBattleLogic.Entities.Abilities.Triggered.Loki.TerrifyingCrescendoAbility$$CreateBehaviour)
  4. AnvilShield       (spaceRockfist)  : dispatch On(UnitBlocked) -> Ice sur la tuile de l'attaquant
                                          (IdunBattle.Operations.ADamageOperation$$EvaluateAfterHitTriggers emetteur ; IdunBattleLogic.Entities.Abilities.Triggered.Loki.AnvilShieldAbility_ApplyIce$$CreateTrigger/IdunBattleLogic.Entities.Abilities.Triggered.Loki.AnvilShieldAbility_ApplyIce$$CreateBehaviour)

Le probe monte UN runner live (roster = les 4 porteurs), reconstruit le `State` OFFLINE depuis le
snapshot, et exerce chaque maillon en imprimant l'ETAT OBSERVE (effet present / niveau / duree / source)
-- pas un << smoke OK >>. Chaque bloc imprime aussi ses CONTROLES NEGATIFS.

ASCII only (cp1252). Usage : python probe_lot_pose.py [--seed 92201] [--reuse]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rl_collect_batch import _resolve_session, _rpc      # noqa: E402

PYDIR = Path(__file__).resolve().parent
STATE = Path(r"C:\Users\nicolasv\tacticus-tools\data\_lot4pose_main_state.json")
BOARD = "MC1_67"
P_UNITS = "admecDominus,blackObliterator,emperNoiseMarine,spaceRockfist"
A_UNITS = "necroWarden,necroWarden,necroWarden"

VIS = {"MA": "admecDominus", "FG": "blackObliterator",
       "TC": "emperNoiseMarine", "AS": "spaceRockfist", "EN": "necroWarden"}


def _r(sid, method, body, t=90):
    return (_rpc(sid, method, [body], timeout=t).get("result") or {})


def build(seed: int) -> int:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.unlink(missing_ok=True)
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
         "--state-file", str(STATE), "--board", BOARD,
         "--p-units", P_UNITS, "--a-units", A_UNITS,
         "--hp-target", "400000", "--hp-player", "400000"],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not STATE.exists():
        print("[lot] build KO: " + (proc.stderr or proc.stdout or "")[-500:], file=sys.stderr)
        sys.exit(2)
    return json.loads(STATE.read_text())["runnerId"]


def offline_state(sid, rid):
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    from engine.runner.prng import IntBasedMersenneTwister
    bg = _r(sid, "boardGraph", {"runnerId": rid}, 60)
    board = Board(bg["tiles"], adjacency="evenq")
    dec = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    ob = _r(sid, "observeBattle", {"runnerId": rid}, 60)
    snap = _r(sid, "combatSnapshot", {"runnerId": rid}, 90)
    st = load_state(dec, ob, snap, board=board)
    s0 = _r(sid, "dumpRng", {"runnerId": rid}, 30)
    if s0.get("mt"):
        rng = IntBasedMersenneTwister()
        rng.mt = list(s0["mt"])
        rng.mti = s0["mti"]
        st.rng = rng
    return st, dec, board


def uid_of(dec, vis):
    for u in (dec.get("units") or []):
        if u.get("visualId") == vis and u.get("alive"):
            return u["id"]
    return None


def uids_of(dec, vis):
    return [u["id"] for u in (dec.get("units") or []) if u.get("visualId") == vis and u.get("alive")]


def show(state, uid, tag=""):
    """Etat OBSERVE des effets d'une unite : (nom, type, level, remaining, source, consumed)."""
    if state.effects is None:
        return "no-effects-state"
    rows = []
    for e in state.effects.by_unit.get(int(uid), []):
        rows.append("%s(t=%s lvl=%s rem=%s src=%s%s)" % (
            e.name, e.effect_type, e.level, e.remaining_turns, e.source,
            " CONSUMED" if e.consumed else ""))
    return ("u%d%s: " % (uid, tag)) + (", ".join(rows) if rows else "<aucun>")


def place(state, board, uid, col, row):
    from engine.runner.components import PositionComponent
    pc = state.get_entity(uid).get_component(PositionComponent)
    pc.col, pc.row = col, row


def free_adjacent(state, board, anchor_uid, taken):
    from engine.runner.components import PositionComponent
    pc = state.get_entity(anchor_uid).get_component(PositionComponent)
    t0 = board.id_at(pc.col, pc.row)
    occ = set()
    for eid, e in state.entities.items():
        p = e.get_component(PositionComponent)
        if p is not None:
            occ.add((p.col, p.row))
    for n in board.neighbours(t0):
        c = board.coord(n)
        if c not in occ and c not in taken:
            return c
    return None


# ----------------------------------------------------------------------------------------------
def item1_master_annihilator(state, dec, board):
    from engine.runner.operations.triggers.dispatch import after_hit_normal_attack
    from engine.runner.operations.effects import AddEffectOperation
    from engine.entities.effect_type import EffectType
    MARK = int(EffectType.MasterAnnihilator_extraHit)
    print("\n=== [1] MasterAnnihilator -- pose + remove-by-source ===")
    vit = uid_of(dec, VIS["MA"])
    ens = uids_of(dec, VIS["EN"])
    other = uid_of(dec, VIS["FG"])          # 2e << poseur >> (source DIFFERENTE) pour le controle
    if vit is None or len(ens) < 3:
        print("  SKIP : roster incomplet (3 ennemis requis)"); return
    e1, e2, e3 = ens[0], ens[1], ens[2]
    from engine.runner.components import PositionComponent
    vp = state.get_entity(vit).get_component(PositionComponent)
    print("  vitruvius=u%d @(%d,%d) | cibles e1=u%d e2=u%d | controle e3=u%d (marque par u%d)"
          % (vit, vp.col, vp.row, e1, e2, e3, other))

    # CONTROLE NEGATIF : un marqueur 1249 pose par une AUTRE source sur une TROISIEME unite.
    AddEffectOperation.execute(state, source=other, target=e3, effect_type=MARK,
                               name="MasterAnnihilator_extraHit")
    print("  [pre] " + show(state, e1, " e1"))
    print("  [pre] " + show(state, e3, " e3 (autre source)"))

    r1 = after_hit_normal_attack(state, vit, e1, ranged=False, profile="Physical")
    print("  attaque #1 vitruvius -> e1 : trig=%s" % [d for d in r1 if d.get("ability") == "MasterAnnihilator"])
    print("  [t1] " + show(state, e1, " e1"))

    r2 = after_hit_normal_attack(state, vit, e2, ranged=False, profile="Physical")
    print("  attaque #2 vitruvius -> e2 : trig=%s" % [d for d in r2 if d.get("ability") == "MasterAnnihilator"])
    print("  [t2] " + show(state, e1, " e1  (attendu: marque de vitruvius RETIRE = remove-by-source)"))
    print("  [t2] " + show(state, e2, " e2  (attendu: marque de vitruvius POSE)"))
    print("  [t2] " + show(state, e3, " e3  (attendu: marque de l'AUTRE source INTACT)"))

    def _n(uid, src=None):
        return sum(1 for e in state.effects.by_unit.get(uid, [])
                   if e.effect_type == MARK and not e.consumed and (src is None or e.source == src))
    print("  VERDICT: e1 actifs=%d (attendu 0) | e2 source-vitruvius=%d (attendu 1) "
          "| e3 source-AUTRE=%d (attendu 1 = NON retire)" % (_n(e1), _n(e2, vit), _n(e3, other)))
    # MAGNITUDE : le marqueur pose est-il ACTIF (canal +1 coup recu, non-Psychic) ?
    mk = next((e for e in state.effects.by_unit.get(e2, [])
               if e.effect_type == MARK and not e.consumed), None)
    if mk is not None:
        b_phys = mk.create_effect_hits_malus_for_defense(is_melee=True, damage_profile="Physical")
        b_psy = mk.create_effect_hits_malus_for_defense(is_melee=True, damage_profile="Psychic")
        print("  MAGNITUDE marqueur pose : Physical -> %s (attendu +1) | Psychic -> %s (attendu None)"
              % (getattr(b_phys, "hits_bonus", b_phys), b_psy))


# ----------------------------------------------------------------------------------------------
def item2_fleshmetal(state, dec, board):
    from engine.runner.operations.turnflow import StartTurnOperation
    from engine.runner.components import OwnerComponent, StatsComponent
    from engine.entities.stats import StatType
    print("\n=== [2] FleshmetalGuns -- rotation Modulo(UnitTurnsStarted, 3) sur PLUSIEURS tours ===")
    volk = uid_of(dec, VIS["FG"])
    if volk is None:
        print("  SKIP : Volk absent"); return
    player = state.get_entity(volk).get_component(OwnerComponent).player
    sc = state.get_entity(volk).get_component(StatsComponent)
    print("  [pre] turnsStarted=%s | %s" % (sc.ctx.stats.get_stat(int(StatType.TURNS_STARTED), 0),
                                            show(state, volk)))
    seq = []
    for k in range(5):
        StartTurnOperation.execute(state, player)
        ts = sc.ctx.stats.get_stat(int(StatType.TURNS_STARTED), 0)
        names = sorted(e.name for e in state.effects.by_unit.get(volk, [])
                       if not e.consumed and str(e.name).startswith("FleshmetalGuns"))
        seq.append((ts, names))
        print("  tour #%d : turnsStarted=%s -> %s" % (k + 1, ts, names))
    print("  VERDICT sequence (attendu cycle Melta/Flame/HeavyRound selon turns%%3 == 1/2/0) : %s"
          % [(t, n) for t, n in seq])
    # MAGNITUDE : l'effet POSE par la rotation doit rendre le MEME groupe de coups bonus que l'effet
    # SEEDE live (meme classe + meme scaling) -> preuve que la pose n'est pas << presente mais inerte >>.
    ctx = {"is_melee": False}
    posed = next((e for e in state.effects.by_unit.get(volk, [])
                  if not e.consumed and str(e.name).startswith("FleshmetalGuns")), None)
    if posed is not None:
        print("  MAGNITUDE effet POSE (%s, ablvl=%s mult=%s) : %s"
              % (posed.name, posed.ability_level, posed.ability_variables_multiplier,
                 posed.additional_hit_groups(ctx)))
    # reference : l'effet SEEDE live (etat frais) pour la MEME variante FocusedMalice.
    from engine.entities.effects.factory import EffectFactory
    from engine.runner.components import StatsComponent as _SC
    vctx = state.get_entity(volk).get_component(_SC).ctx
    ref = EffectFactory.create({"name": "FleshmetalGunsFocusedMalice", "effectType": 1067,
                                "level": 1, "remaining": 0, "source": volk},
                               ability_variables_multiplier=int(getattr(vctx, "ability_variables_multiplier", 100)),
                               ability_level=getattr(vctx, "passive_ability_level", None))
    print("  MAGNITUDE reference SEED-like (FocusedMalice, ablvl=%s mult=%s) : %s"
          % (ref.ability_level, ref.ability_variables_multiplier, ref.additional_hit_groups(ctx)))


# ----------------------------------------------------------------------------------------------
def item3_crescendo(state, dec, board):
    from engine.runner.operations.effects import AddEffectOperation
    from engine.runner.operations.triggers.dispatch import after_hit_normal_attack
    from engine.entities.effect_type import EffectType
    from engine.runner.operations.triggers.loki.terrifying_crescendo import crescendo_max_level
    CRESC = int(EffectType.TerrifyingCrescendo_ExtraDmg)
    PIN = int(EffectType.Pinned)
    print("\n=== [3] TerrifyingCrescendo -- accumulation (compteur qui MONTE) ===")
    shiron = uid_of(dec, VIS["TC"])
    ens = uids_of(dec, VIS["EN"])
    if shiron is None or not ens:
        print("  SKIP : roster incomplet"); return
    print("  cap buffMaxLevel = %s" % crescendo_max_level())
    print("  [pre] " + show(state, shiron))
    lvls = []
    for k in range(9):
        # chemin REEL : Shiron pose Pinned (SuppressiveFire) -> On(PreEffectAdded=62) -> +1 stack.
        AddEffectOperation.execute(state, source=shiron, target=ens[k % len(ens)],
                                   effect_type=PIN, name="Pinned")
        cur = [e.level for e in state.effects.by_unit.get(shiron, [])
               if e.effect_type == CRESC and not e.consumed]
        lvls.append(cur[0] if cur else None)
        print("  pose Pinned #%d (source=Shiron) -> crescendo level = %s" % (k + 1, lvls[-1]))
    print("  VERDICT montee : %s (attendu 1,2,3,4,5,6,6,6,6 -- cap a buffMaxLevel)" % lvls)
    # CONTROLE NEGATIF : un Pinned pose par une AUTRE unite ne doit PAS incrementer Shiron.
    other = uid_of(dec, VIS["FG"])
    before = lvls[-1]
    AddEffectOperation.execute(state, source=other, target=ens[0], effect_type=PIN, name="Pinned")
    after = [e.level for e in state.effects.by_unit.get(shiron, [])
             if e.effect_type == CRESC and not e.consumed]
    print("  CONTROLE (Pinned pose par u%d, PAS Shiron) : level %s -> %s (attendu inchange)"
          % (other, before, after[0] if after else None))
    print("  [post] " + show(state, shiron))
    # MAGNITUDE : l'effet accumule doit produire l'additif RANGED = extraDmg[ablvl] x mult x level.
    from engine.entities.effects.magnitude import ability_var
    from engine.runner.components import StatsComponent as _SC
    eff = next((e for e in state.effects.by_unit.get(shiron, [])
                if e.effect_type == CRESC and not e.consumed), None)
    sctx = state.get_entity(shiron).get_component(_SC).ctx
    if eff is not None:
        per = ability_var("TerrifyingCrescendo", "extraDmg", eff.ability_level,
                          multiplier_pct=eff.ability_variables_multiplier)
        rng_b = eff.create_effect_damage_bonus_for_attack(is_ranged=True)
        mel_b = eff.create_effect_damage_bonus_for_attack(is_ranged=False)
        print("  MAGNITUDE : ablvl=%s (unite passif=%s) mult=%s extraDmg/stack=%s | level=%s"
              % (eff.ability_level, getattr(sctx, "passive_ability_level", None),
                 eff.ability_variables_multiplier, per, eff.level))
        print("  MAGNITUDE : additif RANGED = %s (attendu %s) | MELEE = %s (attendu None, gate IsRangedAttack)"
              % (getattr(rng_b, "damage_bonus", rng_b),
                 (int(per) * int(eff.level)) if per else None, mel_b))


# ----------------------------------------------------------------------------------------------
def item4_anvilshield(state, dec, board):
    from engine.runner.operations.triggers.dispatch import after_hit_normal_attack
    from engine.runner.components import PositionComponent
    from engine.entities.effect_type import EffectType
    ICE = int(EffectType.Ice)
    print("\n=== [4] AnvilShield -- dispatch On(UnitBlocked) -> Ice sur la tuile de l'attaquant ===")
    arjac = uid_of(dec, VIS["AS"])
    ens = uids_of(dec, VIS["EN"])
    if arjac is None or not ens:
        print("  SKIP : roster incomplet"); return
    att = ens[-1]
    c = free_adjacent(state, board, arjac, set())
    if c:
        place(state, board, att, *c)
    apc = state.get_entity(att).get_component(PositionComponent)
    tile = board.id_at(apc.col, apc.row)
    print("  attaquant u%d @ (%d,%d) tile=%s | arjac=u%d" % (att, apc.col, apc.row, tile, arjac))
    print("  [pre] tuile attaquant : %s" % show(state, tile, " (tile)"))
    # CONTROLE NEGATIF : attaque SANS block -> aucun Ice.
    after_hit_normal_attack(state, att, arjac, ranged=False, profile="Physical", did_block=False)
    n0 = sum(1 for e in state.effects.by_unit.get(tile, []) if e.effect_type == ICE and not e.consumed)
    print("  attaque SANS block -> Ice sur la tuile = %d (attendu 0)" % n0)
    r = after_hit_normal_attack(state, att, arjac, ranged=False, profile="Physical", did_block=True)
    n1 = sum(1 for e in state.effects.by_unit.get(tile, []) if e.effect_type == ICE and not e.consumed)
    print("  attaque AVEC block -> trig=%s" % [d for d in r if d.get("ability") == "AnvilShield"])
    print("  [post] tuile attaquant : %s" % show(state, tile, " (tile)"))
    print("  VERDICT: Ice sur la tuile de l'attaquant = %d (attendu 1)" % n1)


# ----------------------------------------------------------------------------------------------
def item5_adversarial(state, dec, board):
    """CONTRE-SCENARIOS : chaque gate du trigger doit REFUSER quand sa condition tombe. Un port qui
    << marche >> sur le happy path mais ignore ses gates echoue ICI."""
    from engine.runner.operations.turnflow import StartTurnOperation
    from engine.runner.operations.triggers.dispatch import after_hit_normal_attack
    from engine.runner.components import OwnerComponent, UnitComponent, PositionComponent
    from engine.entities.effect_type import EffectType
    MARK, ICE = int(EffectType.MasterAnnihilator_extraHit), int(EffectType.Ice)
    print("\n=== [5] CONTRE-SCENARIOS (les gates doivent REFUSER) ===")
    vit, volk = uid_of(dec, VIS["MA"]), uid_of(dec, VIS["FG"])
    arjac, shiron = uid_of(dec, VIS["AS"]), uid_of(dec, VIS["TC"])
    ens = uids_of(dec, VIS["EN"])
    if not all((vit, volk, arjac, shiron)) or not ens:
        print("  SKIP : roster incomplet"); return

    def _n(uid, t):
        return sum(1 for e in state.effects.by_unit.get(uid, [])
                   if e.effect_type == t and not e.consumed)

    # (a) MasterAnnihilator vs un ALLIE -> AreEnemies FAUX -> aucune marque.
    before = _n(volk, MARK)
    after_hit_normal_attack(state, vit, volk, ranged=False, profile="Physical")
    print("  (a) Vitruvius attaque un ALLIE (Volk) -> marques %d -> %d (attendu inchange)"
          % (before, _n(volk, MARK)))

    # (b) un NON-porteur attaque un ennemi -> aucune marque (le trigger est per-porteur).
    before = _n(ens[0], MARK)
    after_hit_normal_attack(state, arjac, ens[0], ranged=False, profile="Physical")
    print("  (b) Arjac (NON porteur) attaque un ennemi -> marques %d -> %d (attendu inchange)"
          % (before, _n(ens[0], MARK)))

    # (c) FleshmetalGuns : debut de tour du joueur ADVERSE -> IsTurnOf(Self) FAUX -> pas de rotation.
    enemy_player = state.get_entity(ens[0]).get_component(OwnerComponent).player
    b = sorted(e.name for e in state.effects.by_unit.get(volk, [])
               if not e.consumed and str(e.name).startswith("FleshmetalGuns"))
    StartTurnOperation.execute(state, enemy_player)
    a = sorted(e.name for e in state.effects.by_unit.get(volk, [])
               if not e.consumed and str(e.name).startswith("FleshmetalGuns"))
    print("  (c) turn-start du joueur ADVERSE -> Volk %s -> %s (attendu INCHANGE)" % (b, a))

    # (d) FleshmetalGuns : porteur MORT -> le dispatch gate `owner vivant` -> pas de rotation.
    my_player = state.get_entity(volk).get_component(OwnerComponent).player
    state.get_entity(volk).get_component(UnitComponent).alive = False
    b = sorted(e.name for e in state.effects.by_unit.get(volk, [])
               if not e.consumed and str(e.name).startswith("FleshmetalGuns"))
    StartTurnOperation.execute(state, my_player)
    a = sorted(e.name for e in state.effects.by_unit.get(volk, [])
               if not e.consumed and str(e.name).startswith("FleshmetalGuns"))
    print("  (d) porteur MORT au turn-start -> Volk %s -> %s (attendu INCHANGE)" % (b, a))
    state.get_entity(volk).get_component(UnitComponent).alive = True

    # (e) AnvilShield : un NON-porteur bloque -> aucune Ice.
    att = ens[-1]
    apc = state.get_entity(att).get_component(PositionComponent)
    tile = board.id_at(apc.col, apc.row)
    before = _n(tile, ICE) if tile is not None else 0
    after_hit_normal_attack(state, att, shiron, ranged=False, profile="Physical", did_block=True)
    print("  (e) BLOCK par un NON-porteur (Shiron) -> Ice sur la tuile attaquant %d -> %d (attendu inchange)"
          % (before, _n(tile, ICE) if tile is not None else 0))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=92201)
    ap.add_argument("--reuse", action="store_true", help="reutilise le runner du state-file")
    args = ap.parse_args()
    sid = _resolve_session()
    if args.reuse and STATE.exists():
        rid = json.loads(STATE.read_text())["runnerId"]
    else:
        rid = build(args.seed)
    print("[lot] session=%s runner=%s" % (sid, rid))
    for fn in (item1_master_annihilator, item2_fleshmetal, item3_crescendo, item4_anvilshield,
               item5_adversarial):
        st, dec, board = offline_state(sid, rid)      # etat FRAIS par item (isolation)
        fn(st, dec, board)
    if not args.reuse:
        _rpc(sid, "disposeRunner", [{"runnerId": rid}], timeout=60)
        print("\n[lot] runner %s dispose" % rid)


if __name__ == "__main__":
    main()
