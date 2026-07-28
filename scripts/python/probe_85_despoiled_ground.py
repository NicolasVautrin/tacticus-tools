#!/usr/bin/env python
"""Probe #85 -- DespoiledGround (effet de TUILE 0x5c4 = 1476) : POSE, EXPIRATION, DEGAT.

Les DEUX manques que #85 visait, et ce que ce montage MESURE :

  1. le vecteur `On(0x10 = DamageDealt)` -- emis par `IdunBattle.Operations.ApplyDamageOperation$$
     Execute` (sequence `0x3a` -> `0xf` -> `0x10`), consomme par
     `IdunBattleLogic.Entities.Abilities.Active.Loki.FleshMetalGuns_TileEffectAbility$$CreateTrigger`
     (`On(0x10) & get_OwnerIsCaster & HasEffect(Self@0x148, 0x4c5 = WarpHail)`) ;
  2. la CLASSE d'effet 1476 (`Idun.Source.IdunBattle.Logic.Entities.Effects.DespoiledGroundEffect`)
     et ce qu'elle inflige (`IdunBattleLogic.Entities.Abilities.Active.Loki.
     EnvDespoiledGroundTileAbility$$CreateBehaviour`, tick `On(0x14)`).

PORTEUR : `blackObliterator` << Volk >> (Black Legion) -- **HERO, present dans `--list-pool` rank 17**.
Sa rotation d'armes (`FleshMetalGunsAbility`, #222) pose `FleshmetalGunsWarpHail` (0x4c5 = 1221) au
debut de son tour quand `UnitTurnsStarted(Self) mod 3 == 0` : le montage ATTEND ce tour-la plutot que
d'esperer un tirage.

QUATRE MESURES, chacune confrontee LIVE <-> OFFLINE depuis la MEME capture :
  A. POSE     : la tuile de la victime porte 1476 (source = Volk) apres une attaque de Volk sous
                WarpHail ; le rejeu offline de la MEME attaque pose la MEME chose.
  B. CONTROLE NEGATIF (offline) : sans l'effet WarpHail sur Volk, le MEME rejeu ne pose RIEN
                (c'est le gate `HasEffect(Self, 0x4c5)` du `CreateTrigger`).
  C. EXPIRATION : on avance les DEUX cotes du MEME nombre de tours sans plus rien faire ; la tuile
                doit perdre 1476 au MEME tour (duree = `ConvertRoundsToTurns(DefaultAmountOfRounds(
                0x5c4) = 2 rounds)`).
  D. DEGAT    : l'occupant de la tuile despoilee perd, a chaque debut de tour, un montant tire dans
                `[DespoiledGroundMinDmgPct, DespoiledGroundMaxDmgPct]` % de sa PV MAX (BC `Effect`
                = 6 % .. 9 %). On confronte le delta de PV LIVE a cette BANDE (le tirage natif
                `RandomAmount` n'est pas rejouable coup-pour-coup ici : l'assertion porte sur la
                BANDE, pas sur un scalaire fitte).

ASCII only (cp1252). Usage :
  python probe_85_despoiled_ground.py
  python probe_85_despoiled_ground.py --seed 8503 --board MC1_67
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

import hexgeo                                                              # noqa: E402
from rl_collect_batch import _resolve_session, _rpc                        # noqa: E402
from engine.entities.effect_type import EffectType                         # noqa: E402
from engine.entities.pathfinding.board import Board                        # noqa: E402
from engine.entities.effects.magnitude import bc_effect_config             # noqa: E402
from engine.runner.snapshot import load_state                              # noqa: E402
from engine.runner.components import HealthComponent                       # noqa: E402
from engine.runner.operations.damage import AttackDamageOperation          # noqa: E402
from engine.runner.operations.turnflow import EndTurnOperation             # noqa: E402
from engine.runner.operations.effects import default_amount_of_rounds      # noqa: E402
from engine.runner.abilities.base import convert_rounds_to_turns           # noqa: E402

VOLK = "blackObliterator"        # passif FleshmetalGuns (rotation) + volet TileEffect (#85)
ALLY = "admecDominus"            # 2e unite de mon camp : sans elle l'attaque de Volk clot mon tour
# 2 ennemis (tuer le seul ennemi terminerait la bataille). `astraBullgryn` et PAS un Necron : le trait
# `LivingMetal` (#203) regenere au meme boundary de tour (`On(0x13 = TurnStart_Other)`) et CONFONDRAIT
# le delta de PV du DoT (mesure : victime Necron -> +36 k de regen dans le meme tick). Bullgryn est
# aussi **Imperial** (26) -> c'est une cible ELIGIBLE au bonus +15 % de l'effet 1478.
FOE = "astraBullgryn"
DESPOILED = int(EffectType.DespoiledGround)                    # 0x5c4 = 1476
WARP_HAIL = int(EffectType.FleshmetalGunsWarpHail)             # 0x4c5 = 1221
NORMAL_ATTACK = 69               # `Loki_NormalAttack` (id CONCRET, cf. NormalAttackType@0x28)
HP = 400000                      # PV enormes des DEUX cotes : un mort ne porte plus rien


def _r(sid, m, b, t=120):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def build(state_file: Path, seed: int, board_id: str, foe: str = FOE) -> int:
    state_file.unlink(missing_ok=True)
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
         "--state-file", str(state_file), "--board", board_id, "--rank", "17",
         "--p-units", ",".join([VOLK, ALLY]), "--a-units", ",".join([foe, foe]),
         "--hp-target", str(HP), "--hp-player", str(HP)],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not state_file.exists():
        print("[85] build KO : %s" % ((proc.stderr or proc.stdout or "")[-900:]))
        return None
    return int(json.loads(state_file.read_text())["runnerId"])


def view(sid, rid):
    return _r(sid, "decisionView", {"runnerId": rid, "maxRank": 99, "allAbilities": True}, 180)


def tile_rows(sid, rid):
    """`tileMeta` brut + index {(col,row): [effets]} -- l'ORACLE natif des effets de TUILE."""
    tm = _r(sid, "tileMeta", {"runnerId": rid}, 120)
    idx = {(t.get("col"), t.get("row")): (t.get("effects") or []) for t in (tm.get("tiles") or [])}
    return tm, idx


def despoiled_tiles(idx):
    """{(col,row): [instances 1476]} -- restreint aux tuiles portant DespoiledGround."""
    out = {}
    for co, fx in idx.items():
        hit = [e for e in fx if e.get("effectType") == DESPOILED]
        if hit:
            out[co] = hit
    return out


def by_visual(dv, vis, alive=True):
    return [u for u in (dv.get("units") or [])
            if u.get("visualId") == vis and (bool(u.get("alive")) or not alive)]


def by_id(dv, uid):
    return next((u for u in (dv.get("units") or []) if int(u.get("id")) == int(uid)), None)


def pos_of(u):
    p = (u or {}).get("pos") or {}
    return (p.get("col"), p.get("row"))


def _grand_alliance(u):
    """Traits de GRANDE ALLIANCE de l'unite (gameconfig `GrandAllianceId` -> nom de trait,
    `idun.Idun.Source.Shared.GrandAlliance$$GetTrait`) -- le gate `HasTrait(elem, 0x7ea = Chaos)` du
    2e volet d'`EnvDespoiledGroundTileAbility$$CreateBehaviour`."""
    import gameconfig as GC
    ga = (GC.unit((u or {}).get("visualId")) or {}).get("GrandAllianceId")
    return [ga] if ga else []


def eff_names(u, prefix=""):
    return sorted(str(e.get("name")) for e in ((u or {}).get("effects") or [])
                  if str(e.get("name")).startswith(prefix))


def has_effect_live(u, effect_type):
    return any(e.get("effectType") == effect_type for e in ((u or {}).get("effects") or []))


def endturn(sid, rid):
    return _r(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 120)


def move(sid, rid, uid, co):
    return _r(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": int(uid), "to": {"col": int(co[0]), "row": int(co[1])}}}, 120)


def attack(sid, rid, aid, tid):
    return _r(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": int(aid), "targetId": int(tid),
        "abilityType": NORMAL_ATTACK}}, 150)


def movable(sid, rid, uid):
    mov = _r(sid, "aiMovableTiles", {"runnerId": rid}, 120)
    for m in (mov.get("units") or []):
        if int(m.get("unitId") or -1) == int(uid):
            return [(t["col"], t["row"]) for t in (m.get("tiles") or [])]
    return []


def drive_to(sid, rid, uid, anchor, want):
    """DRIVE des DEUX camps (runner.md : `applyAction` ne verifie pas la propriete de l'unite) :
    place `uid` a la distance hex la plus proche de `want` de `anchor`. On ne SUBIT jamais les
    spawns. Rend la distance obtenue (ou None si l'unite n'a aucune tuile atteignable)."""
    tiles = movable(sid, rid, uid)
    if not tiles:
        return None
    best = min(tiles, key=lambda t: abs(hexgeo.distance(t, anchor) - want))
    move(sid, rid, uid, best)
    return hexgeo.distance(best, anchor)


def bring_in_range(sid, rid, caster_vis, enemy_vis, want, rounds=30):
    """Amene `caster_vis` a distance hex `want` d'un `enemy_vis`, en pilotant les DEUX camps
    (mirror du helper de `tests/engine/runner/test_lot_pose_live.py`). On DEPLACE les unites pour
    remplir la condition -- jamais << bloque par la geometrie de spawn >>."""
    for _ in range(rounds):
        dv = view(sid, rid)
        me = [u for u in by_visual(dv, caster_vis) if pos_of(u)[0] is not None]
        ens = [u for u in by_visual(dv, enemy_vis) if pos_of(u)[0] is not None]
        if not me or not ens:
            endturn(sid, rid)
            continue
        caster = me[0]
        if dv.get("currentPlayer") != caster.get("owner"):
            drive_to(sid, rid, ens[0]["id"], pos_of(caster), want)
            if view(sid, rid).get("currentPlayer") != caster.get("owner"):
                endturn(sid, rid)
            continue
        cand = [e for e in ens if hexgeo.distance(pos_of(e), pos_of(caster)) <= want]
        if cand:
            return dv, caster, min(cand, key=lambda e: hexgeo.distance(pos_of(e), pos_of(caster)))
        tgt = min(ens, key=lambda e: hexgeo.distance(pos_of(e), pos_of(caster)))
        if drive_to(sid, rid, caster["id"], pos_of(tgt), want) is None:
            endturn(sid, rid)
            continue
        dv = view(sid, rid)
        me = [u for u in by_visual(dv, caster_vis) if pos_of(u)[0] is not None]
        tgt = by_id(dv, tgt["id"])
        if not me or tgt is None:
            return None, None, None
        if hexgeo.distance(pos_of(tgt), pos_of(me[0])) <= want:
            return dv, me[0], tgt
        if dv.get("currentPlayer") == caster.get("owner"):
            endturn(sid, rid)
    return None, None, None


def wait_warp_hail(sid, rid, volk_id, owner, maxit=14):
    """Avance les tours jusqu'a un tour de Volk ou il porte `FleshmetalGunsWarpHail` (0x4c5).
    C'est la rotation NATIVE (`Modulo(UnitTurnsStarted(Self), 3) == 0`) qui decide -- on l'attend,
    on ne la force pas. Rend le `decisionView` de ce tour (ou None)."""
    for _ in range(maxit):
        dv = view(sid, rid)
        volk = by_id(dv, volk_id)
        if (dv.get("currentPlayer") == owner and volk is not None
                and has_effect_live(volk, WARP_HAIL)):
            return dv
        endturn(sid, rid)
    return None


def capture(sid, rid, dv=None):
    """Capture COMPLETE (dec/ob/snap/board/tileMeta) -> `State` offline avec ses effets de TUILE."""
    dv = dv or view(sid, rid)
    ob = _r(sid, "observeBattle", {"runnerId": rid}, 90)
    snap = _r(sid, "combatSnapshot", {"runnerId": rid}, 150)
    bg = _r(sid, "boardGraph", {"runnerId": rid}, 90)
    tm, _idx = tile_rows(sid, rid)
    board = Board(bg["tiles"], adjacency="evenq") if bg.get("tiles") else None
    st = load_state(dv, ob, snap, board=board, tiles=tm)
    # MT du runner AVANT le coup live -> le rejeu offline tire les MEMES valeurs (replay-diff).
    s = _r(sid, "dumpRng", {"runnerId": rid}, 30) or {}
    if s.get("mt"):
        from engine.runner.prng import IntBasedMersenneTwister
        r = IntBasedMersenneTwister()
        r.mt = list(s["mt"])
        r.mti = s["mti"]
        st.rng = r
    return st, dv, board


def off_despoiled(st, board):
    """{(col,row): [instances 1476]} cote OFFLINE (les tuiles sont des entites d'`EffectsState`)."""
    out = {}
    if st.effects is None or board is None:
        return out
    for tid, lst in st.effects.by_unit.items():
        hit = [e for e in lst if (not e.consumed) and e.effect_type == DESPOILED]
        if not hit:
            continue
        try:
            out[board.coord(int(tid))] = hit
        except Exception:
            continue
    return out


def run(seed: int = 8501, board_id: str = "MC1_67", foe: str = FOE,
        verbose: bool = True) -> dict:
    sid = _resolve_session()
    state_file = PYDIR.parent.parent / "logs" / ("probe85_%s.json" % seed)
    state_file.parent.mkdir(parents=True, exist_ok=True)
    rid = build(state_file, seed, board_id, foe=foe)
    if rid is None:
        return {"error": "build KO"}
    out: dict = {"rid": rid, "seed": seed, "board": board_id, "foe": foe}
    try:
        dv = view(sid, rid)
        volks = by_visual(dv, VOLK)
        foes = by_visual(dv, foe)
        if not volks or not foes:
            return {"error": "roster incomplet (volk=%d foe=%d)" % (len(volks), len(foes))}
        volk, owner = volks[0], volks[0].get("owner")

        # (0) le plateau ne porte AUCUN DespoiledGround au build -> toute pose observee est CAUSALE.
        _tm, idx0 = tile_rows(sid, rid)
        out["despoiled_at_build"] = sorted(despoiled_tiles(idx0))

        # (1) CONTACT d'abord (les deux camps sont drives), puis (2) le tour WarpHail : `wait_warp_hail`
        #     ne fait qu'enchainer des `endturn` -> aucune unite ne bouge, la distance est preservee.
        dv, volk, tgt = bring_in_range(sid, rid, VOLK, foe, 1)
        if volk is None:
            return {"error": "Volk/cible injoignables (contact non obtenu)"}
        owner = volk.get("owner")

        # (2) attendre le tour WarpHail de Volk (rotation NATIVE, jamais forcee).
        dv = wait_warp_hail(sid, rid, volk["id"], owner)
        if dv is None:
            return {"error": "WarpHail jamais atteint en 14 tours"}
        volk, tgt = by_id(dv, volk["id"]), by_id(dv, tgt["id"])
        out["volk_effects_at_warphail"] = eff_names(volk, "Fleshmetal")
        out["dist_volk_target"] = hexgeo.distance(pos_of(volk), pos_of(tgt))

        # (3) capture AVANT l'attaque -> l'offline rejouera la MEME attaque sur le MEME etat.
        #     DEUX etats INDEPENDANTS pris au MEME instant : `st` (rejeu nominal) et `st_ctrl`
        #     (controle negatif). Capturer le controle APRES l'attaque live le contaminerait (le
        #     `tileMeta` porterait deja le 1476 pose par le natif).
        st, dv, board = capture(sid, rid, dv)
        st_ctrl, _dv_c, _b_c = capture(sid, rid, dv)
        tpos = pos_of(tgt)
        tile_id = board.id_at(*tpos) if board is not None else None
        out["target_tile"] = {"pos": list(tpos), "id": tile_id}

        # ---------------------------------------------------------------- A. POSE (live)
        r = attack(sid, rid, volk["id"], tgt["id"])
        out["attack_ok"] = bool(isinstance(r, dict) and r.get("ok"))
        _tm2, idx2 = tile_rows(sid, rid)
        live_desp = despoiled_tiles(idx2)
        out["live_despoiled"] = {str(list(k)): [{"source": e.get("source"),
                                                 "remaining": e.get("remaining"),
                                                 "name": e.get("name")} for e in v]
                                 for k, v in live_desp.items()}
        out["live_pose_on_target_tile"] = tpos in live_desp
        out["live_pose_source"] = ([e.get("source") for e in live_desp.get(tpos, [])] or [None])[0]
        out["live_pose_remaining"] = ([e.get("remaining") for e in live_desp.get(tpos, [])]
                                      or [None])[0]
        out["expected_remaining"] = convert_rounds_to_turns(
            st, default_amount_of_rounds(DESPOILED))

        # ---------------------------------------------------------------- A'. POSE (offline)
        AttackDamageOperation.execute(st, int(volk["id"]), int(tgt["id"]), 20)
        off_desp = off_despoiled(st, board)
        out["off_despoiled"] = {str(list(k)): [{"source": e.source, "remaining": e.remaining_turns,
                                                "name": str(e.name)} for e in v]
                                for k, v in off_desp.items()}
        out["off_pose_on_target_tile"] = tpos in off_desp
        out["off_pose_source"] = ([e.source for e in off_desp.get(tpos, [])] or [None])[0]
        out["off_pose_remaining"] = ([e.remaining_turns for e in off_desp.get(tpos, [])]
                                     or [None])[0]

        # ------------------------------------------------- B. CONTROLE NEGATIF (offline, sans WarpHail)
        if st_ctrl.effects is not None:
            for e in list(st_ctrl.effects.by_unit.get(int(volk["id"]), [])):
                if e.effect_type == WARP_HAIL:
                    e.consumed = True                # `HasEffect(Self, 0x4c5)` devient FAUX
        AttackDamageOperation.execute(st_ctrl, int(volk["id"]), int(tgt["id"]), 20)
        out["off_control_no_warphail"] = sorted(str(list(k)) for k in off_despoiled(st_ctrl, board))

        # ---------------------------------------------------------------- D. DEGAT (tick 0x14)
        # La victime est DEBOUT sur la tuile despoilee : au prochain debut de tour elle doit perdre
        # entre min% et max% de sa PV MAX (`RandomAmount(PercentageOf(maxHP, cfg9),
        # PercentageOf(maxHP, cfg10))`). On mesure le delta LIVE d'un seul boundary de tour.
        lo_pct = bc_effect_config("DespoiledGroundMinDmgPct")
        hi_pct = bc_effect_config("DespoiledGroundMaxDmgPct")
        dv_a = view(sid, rid)
        tgt_a = by_id(dv_a, tgt["id"])
        hp_before = (tgt_a or {}).get("hp")
        # Capture AVANT le boundary de tour : c'est l'etat sur lequel l'offline rejouera LE MEME tick.
        st_dot, _dvd, _board_d = capture(sid, rid, dv_a)   # noqa: F841 (lu par la bande DSL plus bas)
        tgt_e = st_dot.get_entity(int(tgt["id"]))
        hc = tgt_e.get_component(HealthComponent) if tgt_e is not None else None
        hp_max = (tgt_a or {}).get("hpMax") or (hc.hp_max if hc is not None else None)
        off_before = hc.hp if hc is not None else None
        endturn(sid, rid)                            # -> StartTurn du camp adverse : tick 0x14
        dv_b = view(sid, rid)
        tgt_b = by_id(dv_b, tgt["id"])
        hp_after = (tgt_b or {}).get("hp")
        # BANDE de reference = celle que le NOEUD DSL lui-meme lit (`StatAmount(Target(), Health=5,
        # Maximum=2)`), PAS le `hpMax` de `decisionView` : c'est cette stat-la que
        # `PercentageOf(..., EffectConfig(9|10))` multiplie cote natif comme cote port.
        from engine.runner.abilities.behaviours import entities_from_state as _efs
        from engine.entities.formulas import StatAmount as _SA
        from engine.entities.selectors import Target as _Tg
        _tile_of_victim = _board_d.id_at(*pos_of(tgt_a)) if _board_d is not None else None
        dsl_max = None
        try:
            dsl_max = int(_SA(_Tg(), 5, 2).evaluate(
                _efs(st_dot, _tile_of_victim, int(tgt["id"]))))
        except Exception:
            dsl_max = None
        out["dot"] = {"hp_before": hp_before, "hp_after": hp_after, "hp_max": hp_max,
                      "dsl_max_health": dsl_max,
                      "delta": (None if (hp_before is None or hp_after is None)
                                else int(hp_before) - int(hp_after)),
                      "band_pct": [lo_pct, hi_pct],
                      "band_abs": (None if not dsl_max else
                                   [round(int(dsl_max) * int(lo_pct) / 100),
                                    round(int(dsl_max) * int(hi_pct) / 100)])}
        # Rejeu OFFLINE du MEME boundary de tour. `EndTurnOperation.execute(advance=True)` = la
        # sequence COMPLETE `EndTurn -> ChangeTurn -> StartTurn` (mirror exact d'un `endturn` live) :
        # c'est `ChangeTurnOperation` qui pose `state.current_player_id`, donc c'est le SEUL chemin
        # ou le noeud `IsTurnOf` du 2e volet peut rendre vrai. Appeler `StartTurnOperation` tout seul
        # laisserait le joueur courant PERIME (mesure : 1478 jamais pose).
        res = EndTurnOperation.execute(st_dot, advance=True) or {}
        off_after = hc.hp if hc is not None else None
        out["dot"]["next_player"] = dv_b.get("currentPlayer")
        out["dot"]["off_next_player"] = st_dot.current_player_id
        out["dot"]["off_before"] = off_before
        out["dot"]["off_after"] = off_after
        out["dot"]["off_delta"] = (None if (off_before is None or off_after is None)
                                   else int(off_before) - int(off_after))
        out["dot"]["off_tick_events"] = [e for e in (res.get("start") or [])
                                         if isinstance(e, dict) and e.get("tile_effect")]
        out["dot"]["off_max_hp"] = (hc.hp_max if hc is not None else None)
        # 2e volet du behaviour : `If(IsTurnOf(elem) & HasTrait(elem, Chaos) & NOT HasTrait(elem,
        # Immune), AddEffect(0x5c6 = 1478))`. L'occupant est la victime ; le gate de TRAIT decide.
        out["buff_1478"] = {
            "victim_traits_grand_alliance": [t for t in ("Chaos", "Imperial", "Xenos")
                                             if t in _grand_alliance(tgt_b)],
            "live": sorted(str(e.get("name")) for e in ((tgt_b or {}).get("effects") or [])
                           if str(e.get("name")).startswith("DespoiledGround")),
            "off": sorted(str(e.name) for e in (st_dot.effects.by_unit.get(int(tgt["id"])) or [])
                          if not e.consumed and str(e.name).startswith("DespoiledGround")),
        }

        # ---------------------------------------------------------------- C. EXPIRATION
        # Avance PARALLELE : 1 endturn live = 1 EndTurnOperation offline, plus rien d'autre.
        st_exp, dv_exp, board_e = capture(sid, rid)
        tile_e = board_e.id_at(*tpos) if board_e is not None else None
        off0 = next((e for e in (st_exp.effects.by_unit.get(tile_e) or [])
                     if e.effect_type == DESPOILED and not e.consumed), None)
        out["expiry_seed_remaining"] = None if off0 is None else off0.remaining_turns
        _tm3, idx3 = tile_rows(sid, rid)
        live0 = ([e.get("remaining") for e in despoiled_tiles(idx3).get(tpos, [])] or [None])[0]
        out["expiry_live_seed_remaining"] = live0
        trace, live_off, off_off = [], None, None
        span = 2 * int(live0 or 2) + 3
        for k in range(1, span + 1):
            endturn(sid, rid)
            EndTurnOperation.execute(st_exp, advance=True)
            _tmk, idxk = tile_rows(sid, rid)
            live_rem = ([e.get("remaining") for e in despoiled_tiles(idxk).get(tpos, [])]
                        or [None])[0]
            off_present = bool(st_exp.effects.has_effect(tile_e, effect_type=DESPOILED))
            trace.append((k, live_rem, off_present))
            if live_rem is None and live_off is None:
                live_off = k
            if not off_present and off_off is None:
                off_off = k
            if live_off is not None and off_off is not None:
                break
        out["expiry"] = {"trace": trace, "live_off_turn": live_off, "off_off_turn": off_off}
    finally:
        _r(sid, "disposeRunner", {"runnerId": rid}, 30)
        state_file.unlink(missing_ok=True)
    if verbose:
        print(json.dumps(out, indent=1, default=str))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=8501)
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--foe", default=FOE,
                    help="victime : IMPERIAL (defaut, controle NEGATIF du gate Chaos du 1478) "
                         "ou CHAOS (ex. blackTerminator, controle POSITIF)")
    args = ap.parse_args()
    run(seed=args.seed, board_id=args.board, foe=args.foe, verbose=True)


if __name__ == "__main__":
    main()
