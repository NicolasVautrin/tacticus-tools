#!/usr/bin/env python
"""Probe #1323 -- `FuelledByFury_ExtraDamage` (0x52b), les DEUX etages.

QUESTION BINAIRE MESUREE : le bonus de degat de `FuelledByFury` est-il ABSENT du port, ou present
mais mal magnifie ? Le decompile repond ABSENT sur les DEUX etages (aucune classe d'effet pour 1323
dans `entities/effects/factory.py`, aucune entree `ABILITY_TRIGGERS["FuelledByFury"]`). Ce probe le
MESURE, etage par etage, en separant explicitement :

  * ETAGE 1 -- le COMPTEUR : `IdunBattleLogic.Entities.Abilities.Triggered.Loki.
    FuelledByFury_ExtraDamageAbility$$CreateTrigger` = `On(0xe=UnitPostAbility) & AreFriends(Owner,
    caster) & HasTrait(caster, 0x10=Hero) & !HasTrait(caster, 0x419=MachineOfWar) &
    IsActiveAbilityCountedAsUsed(false)` -> `If(HasEffect, IncreaseEffectLevel(+1, SANS cap),
    AddEffect(0x52b))`. Observable : `decisionView.units[].effects[].level` sur Titus.
  * ETAGE 2 -- la MAGNITUDE : `IdunBattle.Entities.Effects.Loki.FuelledByFury_ExtraDamageEffect$$
    CreateEffectDamageBonusForAttack` = `ForAddition(get_OwnerIsCaster, GetCurrentExtraDamage())`,
    `GetCurrentExtraDamage` = `Multiply(ConfigVar(8=extraDmg), EffectLevel)`. Observable : le degat
    par coup de l'attaque normale de Titus, rejoue OFFLINE sur le MEME MT.

Porter (1) sans (2) donne un compteur mort ; porter (2) sans (1) donne un effet inerte -- les deux
defauts sont PERMISSIFS (ni erreur ni crash). D'ou la PAIRE DE REGIMES, seule mesure qui conclut :

    fury = 0  -> l'effet 1323 est ABSENT de Titus : l'etage 2 n'est pas exerce ;
    fury = N  -> l'effet 1323 est present au niveau N : l'etage 2 doit rendre +N x extraDmg par coup.

Un port SANS la classe d'effet reproduit le regime `fury=0` et RATE `fury=N` ; un port SANS le
trigger reste a `fury=0` pour toujours. Le lot des deux regimes est donc discriminant sur les deux
etages a la fois.

GATE DE CONFRONTABILITE : le porteur unique de `FuelledByFury` est `ultraTitus` << Titus >>, HERO
present dans `rl_duel.py build --list-pool` (rank 17). Les casters allies sont eux aussi des heros du
pool. Aucun porteur npc/summon dans ce montage.

GEOMETRIE DRIVEE (jamais subie) : `applyAction move` ne verifie NI la propriete NI la portee -> on
teleporte la victime au centre et Titus + les deux casters sur son ring 1. Le filler ennemi est tenu
a l'ecart (sans lui, tuer la victime terminerait la bataille et `decisionView` cesserait de rendre
les unites).

PIEGE DE HARNAIS GARDE : `applyAction` peut rendre `ok=True` SANS RIEN MUTER (unite hors
`toActivate`, ou pas son tour). Chaque pose est donc RELUE dans l'etat (position effective, niveau
d'effet effectif) et le probe ABANDONNE si la mutation n'a pas eu lieu -- un no-op silencieux se
lirait sinon comme une divergence geante.

ASCII only (cp1252). Usage :
  python probe_1323_fuelled_by_fury.py [--seed 777] [--board MC1_67] [--keep]
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
from engine.entities.pathfinding.board import Board                        # noqa: E402
from engine.runner.snapshot import load_state                              # noqa: E402
from engine.runner.runner import Runner                                    # noqa: E402
from engine.runner.messages import AttackUnitMessage                       # noqa: E402
from engine.runner.prng import IntBasedMersenneTwister                     # noqa: E402
from engine.runner.operations.triggers.dispatch import unit_post_ability_triggers   # noqa: E402

TITUS = "ultraTitus"              # SEUL porteur de `FuelledByFury` (hero du pool, rank 17)
# 2 heros ALLIES (trait `Hero` = le << Character >> de l'i2) a active ENNEMI-ciblee de portee 2, sans
# aura OFFENSIVE (leurs passifs PsychicFortress / Nightshroud sont DEFENSIFS : ils ne touchent pas le
# degat SORTANT de Titus, donc le delta A/B reste imputable au seul FuelledByFury).
CASTERS = ("ultraTigurius", "astraPrimarisPsy")
VICTIM = "genesPrimus"            # cible des attaques de Titus (PV gonfles : elle doit survivre)
FILLER = "astraBullgryn"          # 2e ennemi tenu a l'ecart : sans lui la bataille se termine
FURY = "FuelledByFury_ExtraDamage"
NORMAL_ATTACK = 69                # `Loki_NormalAttack` (id CONCRET, cf. NormalAttackType@0x28)


def _r(sid, m, b, t=120):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def _seed_rng(s):
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"])
    rng.mti = s["mti"]
    return rng


def build(state_file: Path, seed: int, board: str, casters) -> int:
    state_file.unlink(missing_ok=True)
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
         "--state-file", str(state_file), "--board", board, "--rank", "17",
         "--p-units", ",".join((TITUS,) + tuple(casters)),
         "--a-units", "%s,%s" % (VICTIM, FILLER),
         "--hp-target", "60000", "--crit", "0,0", "--block-target", "0,0"],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not state_file.exists():
        print("[1323] build KO : %s" % ((proc.stderr or proc.stdout or "")[-900:]))
        sys.exit(2)
    return int(json.loads(state_file.read_text())["runnerId"])


def view(sid, rid):
    return _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 180)


def alive_units(dv):
    return [u for u in (dv.get("units") or []) if u.get("alive")]


def by_visual(dv, vis):
    return next((u for u in alive_units(dv) if u.get("visualId") == vis), None)


def upos(u):
    p = (u or {}).get("pos") or {}
    return (p.get("col"), p.get("row")) if p.get("col") is not None else None


def fury_level(dv, unit_id) -> int:
    """Niveau de `FuelledByFury_ExtraDamage` sur `unit_id` (0 = effet absent)."""
    for u in (dv.get("units") or []):
        if int(u.get("id") or -1) != int(unit_id):
            continue
        for e in (u.get("effects") or []):
            if e.get("name") == FURY and not e.get("removed"):
                return int(e.get("level") or 0)
    return 0


def move(sid, rid, uid, coord):
    """Teleporte `uid` et RELIT sa position : `applyAction` peut rendre ok=True sans muter."""
    _r(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": int(uid), "to": {"col": int(coord[0]), "row": int(coord[1])}}}, 90)
    dv = view(sid, rid)
    u = next((x for x in alive_units(dv) if int(x["id"]) == int(uid)), None)
    return upos(u) == (int(coord[0]), int(coord[1]))


def reach_my_turn(sid, rid, my_player, max_end=14):
    dv = view(sid, rid)
    for _ in range(max_end):
        if dv.get("currentPlayer") == my_player:
            return dv
        _r(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
        dv = view(sid, rid)
    return dv if dv.get("currentPlayer") == my_player else None


def capture(sid, rid):
    """Quadruplet PRE-action : `decisionView` + `observeBattle` + `combatSnapshot` + `dumpRng`."""
    return {"dv": view(sid, rid),
            "ob": _r(sid, "observeBattle", {"runnerId": rid}, 60),
            "snap": _r(sid, "combatSnapshot", {"runnerId": rid}, 90),
            "rng": _r(sid, "dumpRng", {"runnerId": rid}, 40)}


def offline_state(cap, board):
    st = load_state(cap["dv"], cap["ob"], cap["snap"], board=board)
    if isinstance(cap["rng"], dict) and cap["rng"].get("mt"):
        st.rng = _seed_rng(cap["rng"])
    return st


def live_cast(sid, rid, caster_id, target_id, ability_type):
    """Casse une ability LIVE et rend `{ok, per_hit_by_target, n_events}`."""
    act = {"kind": "ability", "casterId": int(caster_id), "abilityType": int(ability_type)}
    if target_id is not None:
        act["targetId"] = int(target_id)
    res = _r(sid, "applyAction", {"runnerId": rid, "action": act}, 120)
    a0 = (res.get("actions") or [{}])[0]
    per = {}
    for e in (a0.get("events") or []):
        td = e.get("tags")
        if not td:
            continue
        td = json.loads(td) if isinstance(td, str) else td
        if "Amount" in td and td.get("Active_Ability_Type") == int(ability_type):
            per.setdefault(td.get("Target_Id"), []).append(td.get("Amount"))
    return {"ok": bool(res.get("ok") and a0.get("ok")), "per": per,
            "n_events": len(a0.get("events") or []), "raw": res}


def ability_targets(sid, rid, unit_id, ability_type):
    """Cibles LEGALES `fromHere` (cast immediat, sans bouger) de `unit_id` x `ability_type`."""
    out = _r(sid, "abilityTargets", {"runnerId": rid, "unitId": int(unit_id),
                                     "abilityType": int(ability_type)}, 90)
    for u in (out.get("units") or []):
        for a in (u.get("abilities") or []):
            if int(a.get("abilityId") or -1) == int(ability_type):
                return [t.get("unitId") for t in (a.get("fromHere") or []) if t.get("unitId")]
    return []


def replay_normal_attack(sid, rid, board, attacker_id, target_id):
    """Rejoue LA MEME attaque normale live puis OFFLINE (MT cale) et rend les deux profils de coups."""
    cap = capture(sid, rid)
    fury_before = fury_level(cap["dv"], attacker_id)
    st = offline_state(cap, board)
    live = live_cast(sid, rid, attacker_id, target_id, NORMAL_ATTACK)
    if not live["ok"]:
        return {"ok": False, "reason": "attaque live refusee: %s" % str(live["raw"])[:200]}
    params = fury_params(st, attacker_id)
    runner = Runner(st).install_default_handlers(20)
    runner.apply(AttackUnitMessage(int(attacker_id), int(target_id)))
    rr = runner.damage_handler.last
    return {"ok": True, "fury": fury_before, "params": params,
            "live_ph": live["per"].get(int(target_id)) or [],
            "off_ph": (rr or {}).get("per_hit"),
            "armor": (rr or {}).get("armor"), "pierce": (rr or {}).get("pierce"),
            "fury_after_live": fury_level(view(sid, rid), attacker_id),
            # ETAGE 1 cote OFFLINE : l'attaque NORMALE de Titus emet elle aussi `On(0xe)` (avec
            # `ability_type=1013`), et `IsActiveAbilityCountedAsUsed` DOIT la refuser.
            "fury_after_off": _fury_offline(st, attacker_id)}


def fury_params(st, unit_id):
    """DECOMPOSITION PAR ETAGE de la magnitude, lue sur l'effet MATERIALISE offline :
    `(level, ability_level, multiplier_pct, extraDmg_base, par_stack)` --
    `par_stack = round(extraDmg[ability_level] x multiplier/100)` (`ability_var`), et le bonus par
    coup = `par_stack x level` (`Multiply(ConfigVar(8), EffectLevel)`). Rend None si l'effet est
    absent (regime fury=0)."""
    from engine.entities.effects.magnitude import ability_var
    eff = getattr(st, "effects", None)
    if eff is None:
        return None
    for e in eff.by_unit.get(int(unit_id), []):
        if e.consumed or int(e.effect_type) != 1323:
            continue
        base = ability_var("FuelledByFury", "extraDmg", e.ability_level, multiplier_pct=100)
        per = ability_var("FuelledByFury", "extraDmg", e.ability_level,
                          multiplier_pct=e.ability_variables_multiplier)
        return (int(e.level or 0), e.ability_level, e.ability_variables_multiplier, base, per)
    return None


def _fury_offline(st, unit_id) -> int:
    eff = getattr(st, "effects", None)
    if eff is None:
        return 0
    lv = 0
    for e in eff.by_unit.get(int(unit_id), []):
        if (not e.consumed) and int(e.effect_type) == 1323:
            lv = max(lv, int(e.level or 0))
    return lv


def accumulate_step(sid, rid, board, titus_id, caster_id, ability_type, target_id):
    """UN cast allie : niveau LIVE avant/apres + le MEME evenement `On(0xe)` rejoue OFFLINE."""
    cap = capture(sid, rid)
    before = fury_level(cap["dv"], titus_id)
    st = offline_state(cap, board)
    live = live_cast(sid, rid, caster_id, target_id, ability_type)
    after_live = fury_level(view(sid, rid), titus_id)
    # OFFLINE : on emet EXACTEMENT le vecteur natif de cloture d'ability (dernier evenement
    # d'`ActiveAbilityOperation$$ExecuteInternal`) sur l'etat PRE-cast.
    unit_post_ability_triggers(st, int(caster_id), (int(target_id) if target_id else None),
                               ranged=False, profile=None, ability_type=int(ability_type))
    after_off = _fury_offline(st, titus_id)
    return {"ok": live["ok"], "caster": caster_id, "ability": ability_type,
            "before": before, "after_live": after_live, "after_off": after_off,
            "n_events": live["n_events"], "raw": (None if live["ok"] else str(live["raw"])[:200])}


def predicted(sid, rid, attacker_id, target_id):
    p = (_r(sid, "aiPredict", {"runnerId": rid, "unitId": int(attacker_id),
                               "targetId": int(target_id), "abilityType": NORMAL_ATTACK}, 90)
         or {}).get("pred") or {}
    if p.get("totalDmgMin") is None:
        return None
    return (int(p["totalDmgMin"]), int(p["totalDmgMax"]))


def run(seed: int, board_name: str, keep: bool, casters_ids=CASTERS):
    sid = _resolve_session()
    state_file = PYDIR.parent.parent / "logs" / ("_probe_1323-%d-%s.json" % (seed, board_name))
    state_file.parent.mkdir(parents=True, exist_ok=True)
    rid = build(state_file, seed, board_name, casters_ids)
    print("[1323] runner %d (seed %s, board %s)" % (rid, seed, board_name))
    try:
        bg = _r(sid, "boardGraph", {"runnerId": rid}, 90)
        board = Board(bg["tiles"], adjacency="native_sym")
        dv = view(sid, rid)
        titus = by_visual(dv, TITUS)
        victim = by_visual(dv, VICTIM)
        filler = by_visual(dv, FILLER)
        casters = [by_visual(dv, c) for c in casters_ids]
        if not (titus and victim and filler and all(casters)):
            print("[1323] roster incomplet"); return 2
        my_player = titus.get("owner")

        # --- GEOMETRIE DRIVEE : victime au centre, Titus + casters sur son ring 1 -------------
        # ELEVATION EGALE exigee entre le centre et son ring : sinon le bonus d'elevation
        # (`IdunBattle.Core.Services.DamageCalculations$$CalculateElevationBonusModifier`, +50 %)
        # MULTIPLIE le bonus additif de FuelledByFury et le delta A/B cesse d'etre lisible comme
        # `nrHits x fury x extraDmg` (confond mesure a la 1re passe : +2976 au lieu de 1984 = x1.5).
        # La geometrie est DRIVEE, pas subie : on choisit un centre dont >=3 voisins marchables sont
        # a la MEME elevation que lui.
        def _flat_ring(t):
            e = board.elevation(t)
            return [n for n in board.neighbours(t)
                    if board.walkable(n) and board.elevation(n) == e]
        need = 1 + len(casters)                  # Titus + un caster par tuile de ring
        cands = [t for t in sorted(board.by_id)
                 if board.walkable(t) and len(_flat_ring(t)) >= need]
        if not cands:
            print("[1323] aucune tuile centrale a >=%d voisins marchables de MEME elevation" % need)
            return 2
        center_tile = cands[len(cands) // 2]
        center = board.coord(center_tile)
        ring = [board.coord(n) for n in _flat_ring(center_tile)]
        if len(ring) < need:
            print("[1323] ring plat < %d tuiles" % need); return 2
        far = next((board.coord(t) for t in cands
                    if hexgeo.distance(board.coord(t), center) >= 4), None)
        if far is None:
            print("[1323] aucune tuile d'ecart >= 4 pour le filler"); return 2
        placements = [(filler["id"], far), (victim["id"], center), (titus["id"], ring[0])]
        placements += [(cu["id"], ring[1 + i]) for i, cu in enumerate(casters)]
        # Les 5 unites echangent leurs tuiles : la cible de l'une peut etre occupee par une autre
        # PAS ENCORE deplacee -> on repasse jusqu'a stabilisation (3 passes suffisent pour 5 unites).
        todo = list(placements)
        for _ in range(3):
            todo = [(uid, co) for uid, co in todo if not move(sid, rid, uid, co)]
            if not todo:
                break
        if todo:
            print("[1323] placements REFUSES (no-op silencieux) : %s" % todo)
            return 2
        print("[1323] centre %s ; ring %s" % (str(center), str(ring[:3])))

        if reach_my_turn(sid, rid, my_player) is None:
            print("[1323] mon tour jamais atteint"); return 2

        # --- REGIME A : fury = 0 --------------------------------------------------------------
        dv = view(sid, rid)
        f0 = fury_level(dv, titus["id"])
        pred0 = predicted(sid, rid, titus["id"], victim["id"])
        a = replay_normal_attack(sid, rid, board, titus["id"], victim["id"])
        if not a.get("ok"):
            print("[1323] regime A KO : %s" % a.get("reason")); return 2
        print("")
        print("=== REGIME A (fury=%d) ===" % f0)
        print("  pred live  : %s" % (str(pred0)))
        print("  live  coups: %s" % a["live_ph"])
        print("  offline    : %s   (armor=%s pierce=%s)" % (a["off_ph"], a["armor"], a["pierce"]))
        print("  EXACT      : %s" % (a["live_ph"] == a["off_ph"]))
        print("  fury apres l'attaque NORMALE de Titus : live=%d offline=%d  (attendu 0 : "
              "IsActiveAbilityCountedAsUsed refuse IsNormalAttack)"
              % (a["fury_after_live"], a["fury_after_off"]))

        # --- ACCUMULATION : les deux casters allies -------------------------------------------
        print("")
        print("=== ACCUMULATION (etage 1) ===")
        steps = []
        for cu in casters:
            act = next((ab for ab in (cu.get("abilities") or []) if ab.get("kind") == "active"), None)
            if act is None:
                print("  %s : pas d'active" % cu.get("visualId")); continue
            # `fromHere` = legalite EXACTE du cast immediat ; vide -> on retombe sur la victime
            # (les deux actives choisies ciblent un ENNEMI a portee 2, et le caster est sur son ring 1).
            tgts = ability_targets(sid, rid, cu["id"], act["id"])
            tgt = tgts[0] if tgts else victim["id"]
            s = accumulate_step(sid, rid, board, titus["id"], cu["id"], act["id"], tgt)
            steps.append(s)
            print("  %-16s %-22s (id %s, cible %s) : fury %d -> live %d | offline %d %s"
                  % (cu.get("visualId"), act.get("name"), act["id"], tgt,
                     s["before"], s["after_live"], s["after_off"],
                     "" if s["ok"] else "[CAST REFUSE] " + str(s["raw"])))

        # --- REGIME B : fury = N --------------------------------------------------------------
        if reach_my_turn(sid, rid, my_player) is None:
            print("[1323] mon tour (2) jamais atteint"); return 2
        dv = view(sid, rid)
        fN = fury_level(dv, titus["id"])
        predN = predicted(sid, rid, titus["id"], victim["id"])
        b = replay_normal_attack(sid, rid, board, titus["id"], victim["id"])
        print("")
        print("=== REGIME B (fury=%d) ===" % fN)
        if not b.get("ok"):
            print("  KO : %s" % b.get("reason")); return 2
        print("  pred live  : %s" % (str(predN)))
        print("  live  coups: %s" % b["live_ph"])
        print("  offline    : %s   (armor=%s pierce=%s)" % (b["off_ph"], b["armor"], b["pierce"]))
        print("  EXACT      : %s" % (b["live_ph"] == b["off_ph"]))
        pr = b.get("params")
        if pr:
            lvl, ablvl, mult, base, per = pr
            print("  ETAGES     : level=%s  ability_level=%s  multiplier=%s%%  extraDmg[base]=%s"
                  " -> par stack %s ; bonus/coup = %s x %s = %s"
                  % (lvl, ablvl, mult, base, per, per, lvl, (per or 0) * lvl))
        if pred0 and predN:
            d_min, d_max = predN[0] - pred0[0], predN[1] - pred0[1]
            n_hits = len(b["live_ph"]) or 1
            print("  DELTA pred live (B - A) : min %+d  max %+d" % (d_min, d_max))
            if pr and pr[4]:
                print("  ATTENDU (nrHits %d x fury %d x par-stack %d) = %d  -> %s"
                      % (n_hits, pr[0], pr[4], n_hits * pr[0] * pr[4],
                         "CONCORDE" if d_min == n_hits * pr[0] * pr[4] else "ECART"))

        print("")
        print("=== VERDICT ===")
        ok_a = a["live_ph"] == a["off_ph"] and len(a["live_ph"]) > 0
        ok_b = b["live_ph"] == b["off_ph"] and len(b["live_ph"]) > 0
        ok_acc = all(s["after_live"] == s["after_off"] for s in steps) and bool(steps)
        print("  etage 1 (compteur)  : %s" % ("OK" if ok_acc else "DESACCORD"))
        print("  etage 2 fury=0      : %s" % ("OK" if ok_a else "DESACCORD"))
        print("  etage 2 fury=%d      : %s" % (fN, "OK" if ok_b else "DESACCORD"))
        print("  paire discriminante : %s" % ("OUI (fury 0 != %d)" % fN if fN != f0 else "NON"))
        return 0 if (ok_a and ok_b and ok_acc and fN != f0) else 1
    finally:
        if not keep:
            _r(sid, "disposeRunner", {"runnerId": rid}, 40)
            state_file.unlink(missing_ok=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--casters", default=",".join(CASTERS),
                    help="visualIds des HEROS allies casteurs (1 stack attendu par cast)")
    a = ap.parse_args()
    sys.exit(run(a.seed, a.board, a.keep, tuple(x for x in a.casters.split(",") if x)))


if __name__ == "__main__":
    main()
