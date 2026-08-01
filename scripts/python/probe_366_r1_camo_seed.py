"""case-366-r1-camo-seed -- un effet CONDITION-GATED que la SIMULATION fait entrer dans sa
condition : `1014 CamoCloak_DmgReduction` (porteur `ultraEliminatorSgt` <<Certus>>).

CRITERE BINAIRE : << un porteur capte HORS couvert, puis DEPLACE en couvert par la sim OFFLINE,
recoit-il la meme reduction que le natif qui joue le meme pas ? >>

Ce probe DECOMPOSE la question en quatre etages, parce que trois causes distinctes produisent le
MEME silence (aucun degat retire) et qu'un scalaire ne les separe pas :

  S1 -- L'INSTANCE existe-t-elle cote NATIF quand la condition est FAUSSE ?
        `IdunBattleLogic.Entities.Abilities.Active.Loki.CamoCloakAbility$$CreateBehaviour` est un
        `AddEffect(0x3f6, AbilityStateReference, Owner, 0)` NU -- aucun `If(...)` : la pose est
        INCONDITIONNELLE. On le CONFIRME live par la DIFFERENCE des deux canaux du capteur :
        `decisionView` par DEFAUT (actif-only) vs `includeInactive: true`. INERTE != ABSENT, et
        c'est exactement la confusion que cette tranche leve.

  S2 -- L'instance arrive-t-elle dans l'ETAT OFFLINE ? Deux seeds, deux verdicts : le canal par
        DEFAUT (ce que fait l'ecrasante majorite des sites de capture) n'a RIEN a rallumer ; le
        canal `decision_view_seed_body` (`includeInactive`) porte l'instance avec `active: false`.

  S3 -- Le pas OFFLINE RALLUME-t-il l'instance ? `IdunBattle.Operations.MoveUnitOperation$$Execute`
        appelle `RefreshEffects(RefreshEffectTrigger.UnitPositionChanged = 7)` **DEUX FOIS** --
        avant ET apres `EvaluateAfterMoveTriggers` (deux `FUN_180028040(0x2f, .., processor, &{7,0})`
        encadrant l'appel, lus au decompile). Le SECOND est indispensable ici : c'est
        `EvaluateAfterMoveTriggers` qui emet `On(0x24 = UnitPositionChanged_1)`, donc c'est LUI qui
        fait poser `1013 LightCover` par `LightCoverAbility` -- l'entree meme que lit la
        `CreateActiveCondition` de `1014`. Un port qui n'a que le PREMIER refresh evalue la
        condition sur un etat ou le couvert n'est pas encore pose.

  S4 -- Le DEGAT. Le meme pas + le meme coup, joues LIVE et rejoues OFFLINE sur la MEME capture et
        le MEME flux MT. Plus la CONTRE-EPREUVE (instance 1014 retiree du monde offline), sans
        laquelle << port == live >> ne prouverait pas que la reduction change quoi que ce soit.

Montage : Certus SEUL de son camp (aucun ami `BigTarget` -> le seul membre du `op_BitwiseOr`
atteignable est `1013 LightCover`), board a fort taux de `DryBush`, ennemi `necroWarden` place a
distance 3. Certus DEMARRE hors couvert (deplace hors couvert si son spawn y est) et n'y entre
qu'au pas mesure.

Usage :
    python probe_366_r1_camo_seed.py --board C4_09 --seed 4242

Consommateur pytest : `tests/engine/runner/test_camo_cloak_seed_move_live.py`.
ASCII only (cp1252).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

_PYDIR = Path(__file__).resolve().parent
_ROOT = _PYDIR.parent.parent

from probe_366_r1_camo_cloak import (              # noqa: E402  (constantes + lecteurs partages)
    CARRIER, FOE, ABILITY, EFFECT, LIGHT_COVER, COVER_TILE,
    DMG_TARGET, HP_PLAYER, HP_TARGET,
    _by_vis, _unit, _eff, live_amounts, _endturn, _movable,
    _place_at_distance, _cover_positions, _ensure_turn,
)

BOARD = "C4_09"          # 17 tuiles `DryBush` (cf. runner.md S2bis) -- le couvert doit etre ATTEIGNABLE
SEED = "4242"


def build_args(board: str) -> list:
    """Certus SEUL : sans ami `BigTarget`, le 2e membre du `op_BitwiseOr` de
    `CamoCloak_DmgReductionEffect$$HasValidEffectTrigger` est structurellement FAUX, donc le gate
    ne peut basculer que par `1013 LightCover` -- une variable, pas deux."""
    return ["--p-units", CARRIER, "--a-units", FOE,
            "--crit", "0,0", "--crit-target", "0,0",
            "--block-target", "0,0", "--block-player", "0,0",
            "--hp-player", str(HP_PLAYER), "--hp-target", str(HP_TARGET),
            "--dmg-target", str(DMG_TARGET),
            "--board", board]


def _build_subprocess(seed: str, board: str) -> int:
    state = _ROOT / "logs" / ("_probe366r1camoseed-%d.json" % (os.getpid(),))
    state.parent.mkdir(parents=True, exist_ok=True)
    state.unlink(missing_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
            "--state-file", str(state), *build_args(board)]
    p = subprocess.run(argv, cwd=str(_PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state.exists():
        raise RuntimeError("build runner KO (rl_duel): " + ((p.stderr or p.stdout or "")[-600:]))
    return int(json.loads(state.read_text())["runnerId"])


# --------------------------------------------------------------------------- pilotage
def _pos(u):
    return (u["pos"]["col"], u["pos"]["row"])


def _move_off_cover(rpc, rid, vis, cover_pos, tries=8):
    """Le spawn peut deja etre une tuile de couvert : on en SORT avant de capturer, sinon le
    regime << capte hors couvert >> n'existe pas et la mesure ne dit rien."""
    for _ in range(tries):
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        mv = _by_vis(dv, vis)
        if mv is None:
            return None
        here = _pos(mv)
        if here not in cover_pos:
            return here
        tiles = [t for t in _movable(rpc, rid, mv["id"]) if t not in cover_pos]
        if not tiles:
            _endturn(rpc, rid)
            continue
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": mv["id"], "to": {"col": tiles[0][0], "row": tiles[0][1]}},
            "captureEvents": False}, 90)
    return None


def _place_near_pos(rpc, rid, mover_vis, anchor_pos, lo, hi, tries=25):
    """DEPLACE `mover_vis` jusqu'a une distance hex dans `[lo, hi]` d'une POSITION (et non d'une
    unite) : l'ancre est la tuile de DESTINATION du porteur, ou le coup sera tire. `lo >= 2` garde
    l'attaque RANGED (a distance 1 le natif prend l'arme de melee, et le gate `IsRangedAttack` de
    `1014` fermerait)."""
    import hexgeo
    for _ in range(tries):
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        mv = _by_vis(dv, mover_vis)
        if mv is None:
            return None
        d = hexgeo.distance(_pos(mv), tuple(anchor_pos))
        if lo <= d <= hi:
            return d
        if dv.get("currentPlayer") != mv.get("owner"):
            _endturn(rpc, rid)
            continue
        tiles = _movable(rpc, rid, mv["id"])
        if not tiles:
            _endturn(rpc, rid)
            continue
        best = min(tiles, key=lambda t: (0 if lo <= hexgeo.distance(t, tuple(anchor_pos)) <= hi
                                         else 1, abs(hexgeo.distance(t, tuple(anchor_pos)) - hi)))
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": mv["id"], "to": {"col": best[0], "row": best[1]}},
            "captureEvents": False}, 90)
        if lo <= hexgeo.distance(best, tuple(anchor_pos)) <= hi:
            return hexgeo.distance(best, tuple(anchor_pos))
        _endturn(rpc, rid)
    return None


def _approach_cover(rpc, rid, vis, cover_pos, tries=25):
    """Amene `vis` a UN PAS d'une tuile de couvert SANS y entrer : le pas MESURE doit etre le
    premier qui franchit la frontiere du gate. Rend `(here, dest)`."""
    import hexgeo
    for _ in range(tries):
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        mv = _by_vis(dv, vis)
        if mv is None:
            return (None, None)
        here = _pos(mv)
        tiles = _movable(rpc, rid, mv["id"])
        # ADJACENTE, pas seulement atteignable : le pas mesure doit tenir en UN hex, pour que la
        # capture puisse etre prise HORS du tour du porteur (ou aucun legal-move n'est publie).
        onto = sorted(t for t in tiles if t in cover_pos and hexgeo.distance(here, t) == 1)
        if here not in cover_pos and onto:
            return (here, onto[0])
        if dv.get("currentPlayer") != mv.get("owner"):
            _endturn(rpc, rid)
            continue
        goal = min(cover_pos, key=lambda c: hexgeo.distance(here, c))
        cand = [t for t in tiles if t not in cover_pos]
        if not cand:
            _endturn(rpc, rid)
            continue
        tgt = min(cand, key=lambda t: hexgeo.distance(t, goal))
        if tgt == here:
            _endturn(rpc, rid)
            continue
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": mv["id"], "to": {"col": tgt[0], "row": tgt[1]}},
            "captureEvents": False}, 90)
    return (None, None)


# --------------------------------------------------------------------------- capture / offline
def _capture(rpc, rid):
    """Les DEUX canaux du capteur, pris au MEME instant : c'est leur DIFFERENCE qui distingue
    << inerte >> de << absent >>."""
    from engine.runner.snapshot import decision_view_seed_body
    return {
        "dv": rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150),
        "dv_inactive": rpc("decisionView", decision_view_seed_body(rid, allAbilities=True), 150),
        "ob": rpc("observeBattle", {"runnerId": rid}, 90),
        "snap": rpc("combatSnapshot", {"runnerId": rid}, 120),
        "rng": rpc("dumpRng", {"runnerId": rid}, 40),
    }


def _load(cap, board, channel: str):
    """`channel` = 'default' (ce que font la plupart des sites de capture) | 'inactive'
    (`decision_view_seed_body`)."""
    from engine.runner.snapshot import load_state
    dv = cap["dv"] if channel == "default" else cap["dv_inactive"]
    return load_state(dv, cap["ob"], cap["snap"], board=board)


def _with_rng(st, cap):
    from engine.runner.prng import IntBasedMersenneTwister
    rng = IntBasedMersenneTwister()
    rng.mt = list(cap["rng"]["mt"])
    rng.mti = cap["rng"]["mti"]
    st.rng = rng
    return st


def _inst(st, uid, etype=EFFECT):
    return next((e for e in (st.effects.by_unit.get(uid) or []) if e.effect_type == etype), None)


def _effect_view(st, uid):
    from engine.runner.components import unit_state_for_effects
    us = unit_state_for_effects(st, uid)
    inst = _inst(st, uid)
    return {"present": inst is not None,
            "flag_active": None if inst is None else bool(inst.active),
            "cond_is_active": None if inst is None else bool(inst.is_active(us)),
            "port_has_1013": bool(st.effects.has_effect(uid, LIGHT_COVER)),
            "us_light_cover": us.get("has_effect_light_cover"),
            "in_active_effects": any(e.effect_type == EFFECT
                                     for e in st.effects.active_effects(uid, us))}


def offline_move_then_hit(cap, board, channel, carrier_id, foe_id, dest, strip=False):
    """Rejoue OFFLINE le MEME pas puis le MEME coup, sur la MEME capture et le MEME flux MT.
    Rend `(vue de l'effet AVANT le pas, vue APRES le pas, per-coup)`."""
    from engine.runner.runner import Runner
    from engine.runner.messages import AttackUnitMessage, MoveUnitMessage
    st = _with_rng(_load(cap, board, channel), cap)
    if strip:
        inst = _inst(st, carrier_id)
        if inst is not None:
            inst.consumed = True
    before = _effect_view(st, carrier_id)
    runner = Runner(st).install_default_handlers(20)
    runner.apply(MoveUnitMessage(carrier_id, tuple(dest)))
    after = _effect_view(st, carrier_id)
    runner.apply(AttackUnitMessage(foe_id, carrier_id))
    last = getattr(getattr(runner, "damage_handler", None), "last", None)
    return before, after, list((last or {}).get("per_hit") or [])


# --------------------------------------------------------------------------- montage
def run(rpc, seed: str = SEED, board_id: str = BOARD, keep: bool = False) -> dict:
    r = {"seed": seed, "board": board_id, "rid": None}
    try:
        _run(rpc, r, seed, board_id)
    except Exception as exc:                              # montage KO -> ERREUR, jamais un vert
        r["error"] = "%s: %s" % (type(exc).__name__, exc)
    finally:
        if not keep and r.get("rid") is not None:
            try:
                rpc("disposeRunner", {"runnerId": r["rid"]}, 40)
            except Exception:                             # nettoyage best-effort
                pass
    return r


def _run(rpc, r: dict, seed: str, board_id: str) -> None:
    from engine.entities.effects.magnitude import ability_var
    from engine.entities.pathfinding.board import Board

    rid = _build_subprocess(seed, board_id)
    r["rid"] = rid
    bg = rpc("boardGraph", {"runnerId": rid}, 90)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        raise RuntimeError("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="native_sym")

    dv0 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    car, foe = _by_vis(dv0, CARRIER), _by_vis(dv0, FOE)
    if car is None or foe is None:
        raise RuntimeError("porteur/cible absents du deploiement")
    r["carrier_id"], r["foe_id"] = car["id"], foe["id"]

    snap0 = rpc("combatSnapshot", {"runnerId": rid}, 120)
    uc0 = next((u.get("unitConfig") or {} for u in (snap0.get("units") or [])
                if u.get("entityId") == car["id"]), {})
    r["passive_level"] = uc0.get("passiveAbilityLevel")
    r["multiplier"] = uc0.get("abilityVariablesMultiplier")
    r["dmg_reduction_config"] = ability_var(ABILITY, "dmgReduction", r["passive_level"],
                                            multiplier_pct=(r["multiplier"] or 100))

    cpos = _cover_positions(rpc, rid)
    r["cover_tiles"] = len(cpos)
    if not cpos:
        raise RuntimeError("board %s sans tuile %s" % (board_id, COVER_TILE))
    if _move_off_cover(rpc, rid, CARRIER, cpos) is None:
        raise RuntimeError("Certus n'a pas pu sortir du couvert avant la capture")
    here, dest = _approach_cover(rpc, rid, CARRIER, cpos)
    if dest is None:
        raise RuntimeError("aucune tuile %s atteignable en UN pas" % COVER_TILE)

    # geometrie d'ATTAQUE : l'ennemi a 2..3 hex de la tuile de DESTINATION (le coup est tire APRES
    # le pas), donc l'ancre est `dest`, PAS la position de depart. Ce placement consomme des tours
    # -- le porteur en ressort avec une activation FRAICHE, ce qui est precisement ce qu'il faut :
    # le pas MESURE doit etre son premier pas du tour.
    r["foe_dist_to_dest"] = _place_near_pos(rpc, rid, FOE, dest, 2, 3)
    if r["foe_dist_to_dest"] is None:
        raise RuntimeError("ennemi non amene a 2..3 hex de la destination")
    # CYCLE DE TOUR COMPLET, puis capture DANS LE TOUR DE L'ENNEMI : c'est la seule facon d'avoir
    # une ACTIVATION FRAICHE cote tireur (`_place_near_pos` vient de depenser la sienne). Le pas du
    # porteur, lui, est joue HORS de son tour -- `applyAction` ne verifie pas la propriete, et
    # `MoveUnitMessage` offline non plus : les deux cotes voient donc le MEME pas.
    if _ensure_turn(rpc, rid, car["owner"]) is None:
        raise RuntimeError("tour du porteur non atteint")
    _endturn(rpc, rid)
    if _ensure_turn(rpc, rid, foe["owner"]) is None:
        raise RuntimeError("tour ennemi (frais) non atteint")
    # les fins de tour ont pu bouger le porteur : on REVERIFIE qu'il est hors couvert et que la
    # destination est bien une tuile de couvert ADJACENTE -- sinon la mesure porterait sur autre
    # chose. (Hors tour, `aiMovableTiles` ne rend rien : on lit la GEOMETRIE, pas le legal-move.)
    import hexgeo
    dv1 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    mv = _by_vis(dv1, CARRIER)
    if mv is None:
        raise RuntimeError("porteur disparu")
    here = _pos(mv)
    if here in cpos:
        raise RuntimeError("porteur deja en couvert au moment de la capture")
    adj = sorted(t for t in cpos if hexgeo.distance(here, t) == 1)
    if not adj:
        raise RuntimeError("aucune tuile %s adjacente au porteur a la capture" % COVER_TILE)
    dest = adj[0]
    r["carrier_pos_before"], r["dest"] = list(here), list(dest)
    r["foe_dist_to_dest_final"] = hexgeo.distance(_pos(_by_vis(dv1, FOE)), tuple(dest))
    if not (2 <= r["foe_dist_to_dest_final"] <= 3):
        raise RuntimeError("distance ennemi/destination %s hors [2,3]"
                           % r["foe_dist_to_dest_final"])

    # ---- S1 : l'INSTANCE cote NATIF, condition FAUSSE ----------------------------------------
    cap = _capture(rpc, rid)
    r["capture_current_player"] = cap["dv"].get("currentPlayer")
    row_a, row_i = _unit(cap["dv"], car["id"]), _unit(cap["dv_inactive"], car["id"])
    r["S1_default_channel_has_1014"] = _eff(row_a, EFFECT) is not None
    ei = _eff(row_i, EFFECT)
    r["S1_inactive_channel_has_1014"] = ei is not None
    r["S1_inactive_channel_flag"] = None if ei is None else ei.get("active")
    r["S1_native_has_1013"] = _eff(row_i, LIGHT_COVER) is not None

    # ---- S2/S3/S4 : les DEUX seeds, le MEME pas, le MEME coup ---------------------------------
    for channel in ("default", "inactive"):
        before, after, hits = offline_move_then_hit(cap, board, channel, car["id"], foe["id"], dest)
        r["S2_%s_before_move" % channel] = before
        r["S3_%s_after_move" % channel] = after
        r["S4_%s_hits" % channel] = hits
    _, _, hits_strip = offline_move_then_hit(cap, board, "inactive", car["id"], foe["id"], dest,
                                             strip=True)
    r["S4_inactive_hits_no_effect"] = hits_strip

    # ---- LIVE : le MEME pas, puis le MEME coup ------------------------------------------------
    rng_before = list(cap["rng"]["mt"]), cap["rng"]["mti"]
    resM = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": car["id"], "to": {"col": dest[0], "row": dest[1]}},
        "captureEvents": True}, 150)
    if not (isinstance(resM, dict) and resM.get("ok")):
        raise RuntimeError("pas live KO: %s" % (str(resM)[:200],))
    rng_mid = rpc("dumpRng", {"runnerId": rid}, 40)
    r["rng_untouched_by_move"] = (list(rng_mid["mt"]) == rng_before[0]
                                  and rng_mid["mti"] == rng_before[1])

    dvm = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    dvmi = rpc("decisionView", {"runnerId": rid, "allAbilities": True,
                                "includeInactive": True}, 150)
    rm, rmi = _unit(dvm, car["id"]), _unit(dvmi, car["id"])
    r["S3_live_default_channel_has_1014"] = _eff(rm, EFFECT) is not None
    emi = _eff(rmi, EFFECT)
    r["S3_live_flag"] = None if emi is None else emi.get("active")
    r["S3_live_has_1013"] = _eff(rmi, LIGHT_COVER) is not None

    foe_row = _unit(dvm, foe["id"])
    norm = next((a for a in ((foe_row or {}).get("abilities") or [])
                 if a.get("kind") == "normal"), None)
    if norm is None:
        raise RuntimeError("aucune attaque normale exposee sur l'ennemi")
    resA = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": foe["id"], "targetId": car["id"],
        "abilityType": norm["id"]}}, 150)
    if not (isinstance(resA, dict) and resA.get("ok")):
        raise RuntimeError("coup live KO: %s" % (str(resA)[:200],))
    hits, dirty = live_amounts(resA, car["id"])
    if not hits:
        raise RuntimeError("coup joue mais aucun degat attribue au porteur")
    r["S4_live_hits"], r["dirty"] = hits, dirty

    # ---- verdicts -----------------------------------------------------------------------------
    r["agree_inactive_seed"] = (r["S4_live_hits"] == r["S4_inactive_hits"])
    r["agree_default_seed"] = (r["S4_live_hits"] == r["S4_default_hits"])
    r["discriminant"] = (r["S4_inactive_hits"] != r["S4_inactive_hits_no_effect"])
    if r["S4_live_hits"] and r["S4_inactive_hits_no_effect"]:
        n = min(len(r["S4_live_hits"]), len(r["S4_inactive_hits_no_effect"]))
        r["delta_per_hit"] = sorted({r["S4_inactive_hits_no_effect"][i] - r["S4_live_hits"][i]
                                     for i in range(n)})


# --------------------------------------------------------------------------- CLI
def main() -> int:
    ap = argparse.ArgumentParser(
        description="case-366-r1-camo-seed : un effet condition-gated que la SIM fait entrer "
                    "dans sa condition")
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--seed", default=SEED)
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()

    import rl_collect_batch as R

    def _unwrap(x):
        return x.get("result") if isinstance(x, dict) and "result" in x else x

    sid = R._resolve_session()

    def rpc(method, body=None, timeout=120):
        return _unwrap(R._rpc(sid, method, [body] if body is not None else [], timeout=timeout))

    r = run(rpc, a.seed, a.board, a.keep)
    print(json.dumps(r, indent=1, default=str))
    if r.get("error"):
        return 1
    print("")
    print("[366-r1-camo-seed] runner=%s board=%s seed=%s  %s -> %s (couvert)"
          % (r["rid"], a.board, a.seed, r["carrier_pos_before"], r["dest"]))
    print("  config : dmgReduction[PASSIF L%s] x mult %s = %s"
          % (r["passive_level"], r["multiplier"], r["dmg_reduction_config"]))
    print("  S1 NATIF hors couvert : canal DEFAUT 1014=%s | canal includeInactive 1014=%s "
          "flag=%s | 1013=%s"
          % (r["S1_default_channel_has_1014"], r["S1_inactive_channel_has_1014"],
             r["S1_inactive_channel_flag"], r["S1_native_has_1013"]))
    for ch in ("default", "inactive"):
        print("  S2/S3 seed=%-8s avant=%s" % (ch, json.dumps(r["S2_%s_before_move" % ch])))
        print("        seed=%-8s apres=%s" % (ch, json.dumps(r["S3_%s_after_move" % ch])))
    print("  S3 NATIF apres le pas : canal DEFAUT 1014=%s flag=%s | 1013=%s"
          % (r["S3_live_default_channel_has_1014"], r["S3_live_flag"], r["S3_live_has_1013"]))
    print("  S4 DEGAT : live=%s | port(inactive)=%s (agree=%s) | port(default)=%s (agree=%s)"
          % (r["S4_live_hits"], r["S4_inactive_hits"], r["agree_inactive_seed"],
             r["S4_default_hits"], r["agree_default_seed"]))
    print("     CONTRE-EPREUVE (sans 1014) : %s  (discriminant=%s, delta/coup=%s)"
          % (r["S4_inactive_hits_no_effect"], r["discriminant"], r.get("delta_per_hit")))
    print("     RNG intact apres le pas live : %s" % (r["rng_untouched_by_move"],))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
