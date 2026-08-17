#!/usr/bin/env python
"""Probe #217 — validation live de la face COMBAT de Stormcaller (active 1113, Njal spaceStormcaller).

Port : engine/runner/abilities/loki/stormcaller.py (mirror `IdunBattleLogic.Entities.Abilities.Active.Loki.StormcallerAbility$$ExecuteBehaviour` : AddEffect(Ice 0x11, cible+ring1) -> AttackWithAbilityDamage(3x Psychic, ennemis sur
tuiles GLACEES, overload IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAbilityDamage == SpiritLeech) -> AddEffect(Stunned 0x48a, Flying du cache,
TurnsFromRounds(1))). Methode = REPLAY-DIFF bit-exact (pattern test_lord_of_tempests_ice_live) :
meme etat pre-cast (dec/ob/snap/dumpRng), cast 1113 live ET offline, puis diff.

DEUX scenarios (2 runners, geometrie forcee par DRIVE, doctrine drive-positions) :
  A. seed 21701, cast a distance 3 (baseline PROPRE : zero glace ring-1 de Njal apres pose
     -> le bonus snowball LordOfTempests ne peut PAS s'appliquer) :
     A1. tuiles glacees live == offline == {tuile cible + ring-1} (elevation-gated) ;
     A2. deltas HP par unite live == offline BIT-EXACT (3x Psychic pierce100 NoBlocking) ;
     A3. stun : WingedPrime (Flying=4) stun live<->offline ssi attaque ; necroWarden JAMAIS.
  B. seed 21702, DISCRIMINANT snowball (tranche le residu case-35 « is_normal_attack » vs le
     decompile IdunBattle.Entities.Effects.Loki.LordOfTempests_ExtraDamageEffect$$CreateEffectDamageBonusForAttack gate=OwnerIsCaster SEUL) :
     - round 1 : attaque NORMALE de Njal a d=2 -> le passif LordOfTempests_AddIce (case-35,
       valide) GLACE la tuile de la victime ;
     - round 2 : drive Njal ADJACENT a une tuile glacee (count-ring1 pre-cast >= 1 -> l'effet
       LordOfTempests_ExtraDamage est IsActive live -> HYDRATE offline par load_state ; sans ce
       prealable, le filtre IsActive de decisionView PERD l'effet et le discriminant est pollue
       par un artefact d'hydratation, PAS par le gate) ;
     - cast 1113 a d=1..2 -> replay-diff : offline applique +extraDmg x count a l'attaque
       d'ABILITY (att_ctx threade, is_normal_attack defaut True) ; un mismatch d'exactement
       extraDmg x count par coup = le natif GATE les attaques d'ability (imprime pour diagnostic,
       has_lot_effect / count / extraDmg par hex).

ASCII only (cp1252). Usage: python probe_217_stormcaller.py [--seed-a 21701] [--seed-b 21702]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hexgeo  # noqa: E402
from rl_collect_batch import _resolve_session, _rpc  # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
NJAL_VIS = "spaceStormcaller"
FLY_VIS = "tyranWingedPrime"          # Flying=4 (unit_map find --trait Flying, lineup, mech:-)
CTRL_VIS = "necroWarden"              # controle non-Flying (jamais stun)
ABILITY = 1113
ICE = 17                              # EffectType.Ice (0x11)
STUNNED = 1162                        # EffectType.Stunned (0x48a)
BUILD_UNITS = ["--p-units", f"{NJAL_VIS},templAncient", "--a-units", f"{FLY_VIS},{CTRL_VIS}",
               "--hp-target", "300000", "--hp-player", "300000"]


def _r(sid, method, body, t=90):
    return (_rpc(sid, method, [body], timeout=t).get("result") or {})


def build(seed: int, tag: str) -> int:
    state = ROOT / "logs" / "runners" / f"_a217_storm_state_{tag}.json"   # SORTIE -> logs/ (#349)
    state.unlink(missing_ok=True)
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
         "--state-file", str(state), "--board", "MC1_67"] + BUILD_UNITS,
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not state.exists():
        print(f"[217] build {tag} KO: {(proc.stderr or proc.stdout or '')[-400:]}", file=sys.stderr)
        sys.exit(2)
    return json.loads(state.read_text())["runnerId"]


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _pos(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row"))


def _find(dec, vis):
    return next((u for u in (dec.get("units") or [])
                 if u.get("visualId") == vis and u.get("alive")), None)


def _hp(ob, uid):
    for u in (ob.get("units") or []):
        if u.get("squadId") == uid and not u.get("isDead"):
            return u.get("hp")
    return None


def _iced_positions(rpc, rid):
    tm = rpc("tileMeta", {"runnerId": rid}, 60)
    out = set()
    for t in (tm.get("tiles") or []):
        if any((e.get("name") == "Ice") for e in (t.get("effects") or [])):
            out.add((t.get("col"), t.get("row")))
    return out


def _offline_iced_positions(state, board):
    out = set()
    for tid, effs in (state.effects.by_unit or {}).items():
        if any((e.effect_type == ICE and not e.consumed) for e in effs):
            co = board.coord(int(tid))
            if co is not None:
                out.add(tuple(co))
    return out


def _advance_to_my_turn(rpc, rid, vis, max_iter=12):
    for _ in range(max_iter):
        dec = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        if not _ok(dec):
            return None, None
        u = _find(dec, vis)
        if u is None:
            return dec, None
        if dec.get("currentPlayer") == u.get("owner"):
            return dec, u
        rpc("aiPlayTurn", {"runnerId": rid}, 240)
        dec2 = rpc("decisionView", {"runnerId": rid}, 150)
        if _ok(dec2) and dec2.get("currentPlayer") != (u or {}).get("owner"):
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    return None, None


def _drive_to_dist(rpc, rid, lo, hi, max_turns=10):
    """DRIVE Njal a distance hex [lo..hi] de l'ennemi le plus proche (doctrine drive-positions)."""
    for _ in range(max_turns):
        dec, me = _advance_to_my_turn(rpc, rid, NJAL_VIS)
        if me is None:
            return None, None, None
        enemies = [u for u in (dec.get("units") or [])
                   if u.get("alive") and u.get("owner") != me.get("owner")]
        if not enemies:
            return None, None, None
        tgt = min(enemies, key=lambda e: hexgeo.distance(_pos(me), _pos(e)))
        d = hexgeo.distance(_pos(me), _pos(tgt))
        if lo <= d <= hi:
            return dec, me, tgt
        mt = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
        cmt = next((x for x in (mt.get("units") or []) if x.get("unitId") == me["id"]), None)
        tiles = [(t["col"], t["row"]) for t in ((cmt or {}).get("tiles") or [])
                 if t.get("col") is not None]
        if tiles:
            tp = _pos(tgt)

            def _key(pos):
                dd = hexgeo.distance(pos, tp)
                return (0 if lo <= dd <= hi else 1, abs(dd - hi), dd)
            best = min(tiles, key=_key)
            rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": me["id"], "to": {"col": best[0], "row": best[1]}}}, 60)
            dec2 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
            me2 = _find(dec2, NJAL_VIS)
            if me2 is not None:
                en2 = [u for u in (dec2.get("units") or [])
                       if u.get("alive") and u.get("owner") != me2.get("owner")]
                tgt2 = min(en2, key=lambda e: hexgeo.distance(_pos(me2), _pos(e))) if en2 else None
                if tgt2 is not None and lo <= hexgeo.distance(_pos(me2), _pos(tgt2)) <= hi:
                    return dec2, me2, tgt2
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    return None, None, None


def _drive_adjacent_to_ice(rpc, rid, max_turns=8):
    """DRIVE Njal sur une tuile ADJACENTE a une tuile GLACEE (count-ring1 pre-cast >= 1 -> l'effet
    snowball est IsActive live et hydrate offline) tout en gardant un ennemi a portee de cast
    (d <= 3, prefere 2). Renvoie (dec, njal, cible-la-plus-proche) ou (None, None, None)."""
    for _ in range(max_turns):
        dec, me = _advance_to_my_turn(rpc, rid, NJAL_VIS)
        if me is None:
            return None, None, None
        enemies = [u for u in (dec.get("units") or [])
                   if u.get("alive") and u.get("owner") != me.get("owner")]
        iced = _iced_positions(rpc, rid)
        if not enemies or not iced:
            return None, None, None

        def _score(pos):
            near_ice = any(hexgeo.distance(pos, p) == 1 for p in iced)
            de = min(hexgeo.distance(pos, _pos(e)) for e in enemies)
            return (0 if near_ice else 1, 0 if 1 <= de <= 3 else 1, abs(de - 2), de)

        if _score(_pos(me))[:2] == (0, 0):
            tgt = min(enemies, key=lambda e: hexgeo.distance(_pos(me), _pos(e)))
            return dec, me, tgt
        mt = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
        cmt = next((x for x in (mt.get("units") or []) if x.get("unitId") == me["id"]), None)
        tiles = [(t["col"], t["row"]) for t in ((cmt or {}).get("tiles") or [])
                 if t.get("col") is not None]
        if tiles:
            best = min(tiles, key=_score)
            rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": me["id"], "to": {"col": best[0], "row": best[1]}}}, 60)
            dec2 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
            me2 = _find(dec2, NJAL_VIS)
            if me2 is not None and _score(_pos(me2))[:2] == (0, 0):
                en2 = [u for u in (dec2.get("units") or [])
                       if u.get("alive") and u.get("owner") != me2.get("owner")]
                tgt2 = min(en2, key=lambda e: hexgeo.distance(_pos(me2), _pos(e))) if en2 else None
                if tgt2 is not None:
                    return dec2, me2, tgt2
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    return None, None, None


def _capture(rpc, rid):
    """`tileMeta` INCLUS (#102) : les effets portes par les TUILES (la glace pre-existante que
    `UnitsOnTilesWithEffect` selectionne) ne transitent QUE par ce canal."""
    dec = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
    s = rpc("dumpRng", {"runnerId": rid}, 30)
    tm = rpc("tileMeta", {"runnerId": rid}, 60)
    return dec, ob, snap, s, tm


def _offline_state(dec, ob, snap, s, board, tiles=None):
    from engine.runner.snapshot import load_state
    from engine.runner.prng import IntBasedMersenneTwister
    state = load_state(dec, ob, snap, board=board, tiles=tiles)
    if _ok(s):
        rng = IntBasedMersenneTwister()
        rng.mt = list(s["mt"])
        rng.mti = s["mti"]
        state.rng = rng
    return state


def _live_stunned(dec, uid):
    u = next((x for x in (dec.get("units") or []) if x.get("id") == uid), None)
    return any((e.get("effectType") == STUNNED or e.get("name") == "Stunned")
               for e in ((u or {}).get("effects") or []))


def _cast_normal(rpc, rid, caster, target_id):
    """Attaque NORMALE live du caster (ability kind=='normal' de decisionView)."""
    norm = next((ab for ab in (caster.get("abilities") or []) if ab.get("kind") == "normal"), None)
    if norm is None:
        return None
    return rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": caster["id"], "targetId": target_id,
        "abilityType": norm["id"]}}, 120)


def run_scenario(rpc, rid, tag: str, lo: int, hi: int, fails: list,
                 prep_ice: bool = False) -> None:
    """Drive a [lo..hi], cast 1113, replay-diff live vs offline (ice/HP/stun + discriminant snowball).
    `prep_ice` (scenario B) : round 1 = attaque NORMALE a d=2 (le passif LordOfTempests glace la
    tuile de la victime, case-35) -> au round 2 le drive DOIT amener >=1 glace au ring-1 de Njal
    AVANT le cast (sinon l'effet snowball n'est pas hydrate offline -> discriminant pollue -> tag geo)."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.runner import Runner
    from engine.runner.messages import ActiveAbilityMessage
    from engine.runner.components import HealthComponent
    from engine.entities.effects.magnitude import ability_var

    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        fails.append(f"{tag}:boardGraph")
        return
    board = Board(bg["tiles"], adjacency="evenq")

    if prep_ice:
        dec, njal, tgt = _drive_to_dist(rpc, rid, 2, 2)
        if njal is None or tgt is None:
            fails.append(f"{tag}:prep-drive")
            return
        res = _cast_normal(rpc, rid, njal, tgt["id"])
        a0 = ((res or {}).get("actions") or [{}])[0] if res else {}
        if not (a0.get("ok") and a0.get("mutated")):
            fails.append(f"{tag}:prep-attack")
            return
        if not _iced_positions(rpc, rid):
            print(f"[217-{tag}] prep : AUCUNE glace posee par l'attaque normale (LordOfTempests)")
            fails.append(f"{tag}:prep-noice")
            return
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
        dec, njal, tgt = _drive_adjacent_to_ice(rpc, rid)
    else:
        dec, njal, tgt = _drive_to_dist(rpc, rid, lo, hi)
    if njal is None or tgt is None:
        print(f"[217-{tag}] drive KO (d=[{lo}..{hi}] non atteint) -> datapoint non mesure")
        fails.append(f"{tag}:drive")
        return
    caster_id, target_id = njal["id"], tgt["id"]
    my_pos, tgt_pos = _pos(njal), _pos(tgt)
    d = hexgeo.distance(my_pos, tgt_pos)
    enemies = [u for u in (dec.get("units") or [])
               if u.get("alive") and u.get("owner") != njal.get("owner")]
    print(f"[217-{tag}] njal={my_pos} cible={tgt.get('visualId')}@{tgt_pos} d={d} "
          f"ennemis={[(u.get('visualId'), _pos(u)) for u in enemies]}")

    ice0 = _iced_positions(rpc, rid)
    dec0, ob0, snap0, s0, tm0 = _capture(rpc, rid)
    hp0 = {u["id"]: _hp(ob0, u["id"]) for u in enemies}
    # #102 : les glaces PRE-EXISTANTES viennent desormais DU LOAD (`load_state(tiles=tileMeta)`).
    # L'hydratation defensive manuelle a ete retiree : c'est justement ce que le vecteur remplace,
    # et la garde ci-dessous verifie que le load a bien reproduit l'ensemble live.
    state = _offline_state(dec0, ob0, snap0, s0, board, tiles=tm0)
    if state.get_entity(caster_id) is None or state.rng is None or state.effects is None:
        fails.append(f"{tag}:etat-offline")
        return
    off_ice0 = _offline_iced_positions(state, board)
    if off_ice0 != ice0:
        print(f"[217-{tag}] SEED TUILES : offline {sorted(off_ice0)} != live {sorted(ice0)}")
        fails.append(f"{tag}:tile-seed")
    count_pre = sum(1 for p in ice0 if hexgeo.distance(my_pos, p) == 1)
    has_lot = any("LordOfTempests" in (getattr(e, "name", "") or "")
                  for e in (state.effects.by_unit.get(caster_id) or []))
    if prep_ice:
        print(f"[217-{tag}] pre-cast: glaces={sorted(ice0)} count-ring1(njal)={count_pre} "
              f"effet-LoT-hydrate-offline={has_lot}")
        if count_pre <= 0 or not has_lot:
            print(f"[217-{tag}] geometrie/hydratation non cooperative -> discriminant pollue")
            fails.append(f"{tag}:geo")

    # --- LIVE : cast 1113 ---
    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": caster_id, "targetId": target_id,
        "abilityType": ABILITY}, "captureEvents": True}, 240)
    a0 = ((res or {}).get("actions") or [{}])[0]
    if not (a0.get("ok") and a0.get("mutated")):
        print(f"[217-{tag}] cast live KO/illegal a d={d}: {str(res)[:240]}")
        fails.append(f"{tag}:cast")
        return
    ob2 = rpc("observeBattle", {"runnerId": rid}, 60)
    dec2 = rpc("decisionView", {"runnerId": rid}, 150)
    live_new_ice = _iced_positions(rpc, rid) - ice0
    live_dmg = {uid: (hp0[uid] - _hp(ob2, uid)) if (hp0.get(uid) is not None
                and _hp(ob2, uid) is not None) else None for uid in hp0}

    # --- OFFLINE : ActiveAbilityMessage(1113) sur le MEME etat/rng ---
    off_ice0 = _offline_iced_positions(state, board)
    runner = Runner(state).install_default_handlers(20)
    runner.apply(ActiveAbilityMessage(caster_id, target_id, ABILITY))
    diag = runner.ability_handler.last or {}
    if diag.get("ported") is not True:
        print(f"[217-{tag}] ability 1113 NON portee (no-op silencieux): {diag}")
        fails.append(f"{tag}:ported")
        return
    off_new_ice = _offline_iced_positions(state, board) - off_ice0
    off_dmg = {}
    for uid in hp0:
        e = state.get_entity(uid)
        hc = e.get_component(HealthComponent) if e is not None else None
        off_dmg[uid] = (hp0[uid] - hc.hp) if (hc is not None and hp0.get(uid) is not None) else None

    # --- 1. zone de glace --- (une tuile DEJA glacee pre-cast ne re-apparait pas dans les
    # NOUVELLES poses — gate already-present des deux cotes -> comparer les diffs + l'union)
    zone = {tgt_pos} | {tuple(board.coord(t)) for t in board.neighbours(board.id_at(*tgt_pos))
                        if board.coord(t) is not None}
    ok_ice = (live_new_ice == off_new_ice) and (tgt_pos in (live_new_ice | ice0)) \
        and live_new_ice <= zone
    print(f"[217-{tag}] 1 ICE: live={sorted(live_new_ice)} offline={sorted(off_new_ice)} "
          f"zone-attendue(<=)={sorted(zone)} pre={sorted(ice0)}: {'OK' if ok_ice else 'X'}")
    if not ok_ice:
        fails.append(f"{tag}:ice")

    # --- 2. degats par ennemi (bit-exact) + discriminant snowball ---
    count_ring1 = sum(1 for p in (live_new_ice | ice0) if hexgeo.distance(my_pos, p) == 1)
    lvl = None
    try:
        from engine.runner.components import StatsComponent
        sc = state.get_entity(caster_id).get_component(StatsComponent)
        lvl = getattr(sc.ctx, "passive_ability_level", None)
        mult = getattr(sc.ctx, "ability_variables_multiplier", 100)
        per_hex = ability_var("LordOfTempests", "extraDmg", lvl, multiplier_pct=mult) or 0
    except Exception:
        per_hex = 0
    ok_dmg = all(live_dmg.get(uid) == off_dmg.get(uid) for uid in hp0)
    print(f"[217-{tag}] 2 DMG: live={live_dmg} offline={off_dmg} "
          f"[snowball: count-ring1={count_ring1} extraDmg/hex={per_hex} lvl={lvl}] "
          f"attacks-off={diag.get('attacks')}: {'OK' if ok_dmg else 'X'}")
    if not ok_dmg:
        fails.append(f"{tag}:dmg")

    # --- 3. stun Flying oui / controle non ---
    for u in enemies:
        uid = u["id"]
        fly = u.get("visualId") == FLY_VIS
        lv = _live_stunned(dec2, uid)
        off = state.effects.has_effect(uid, effect_type=STUNNED)
        agree = lv == off
        expect = " (attendu stun)" if fly and uid in [a.get("target") for a in diag.get("attacks") or []] else ""
        print(f"[217-{tag}] 3 STUN {u.get('visualId')} u{uid}: live={lv} offline={off}{expect}: "
              f"{'OK' if agree else 'X'}")
        if not agree:
            fails.append(f"{tag}:stun-{u.get('visualId')}")
        if not fly and (lv or off):
            fails.append(f"{tag}:stun-controle")


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed-a", type=int, default=21701)
    ap.add_argument("--seed-b", type=int, default=21702)
    args = ap.parse_args(argv)
    sid = _resolve_session()
    fails: list = []

    # A. baseline d=3 (zero glace ring-1 de Njal -> pas de snowball possible)
    rid_a = build(args.seed_a, "a")
    rpc = lambda m, b, t=90: _r(sid, m, b, t)   # noqa: E731
    print(f"[217] A seed={args.seed_a} runner={rid_a}")
    try:
        run_scenario(rpc, rid_a, "A", lo=3, hi=3, fails=fails)
    finally:
        rpc("disposeRunner", {"runnerId": rid_a}, 60)

    # B. discriminant snowball : normale d=2 (glace LoT) -> drive adjacent glace -> cast d=1..2
    rid_b = build(args.seed_b, "b")
    print(f"[217] B seed={args.seed_b} runner={rid_b}")
    try:
        run_scenario(rpc, rid_b, "B", lo=1, hi=2, fails=fails, prep_ice=True)
    finally:
        rpc("disposeRunner", {"runnerId": rid_b}, 60)

    print(f"[217] VERDICT: {'PASS' if not fails else 'FAIL ' + ','.join(fails)}")
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
