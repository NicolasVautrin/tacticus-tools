#!/usr/bin/env python
"""Probe #60bis (tache #30) — member-cap du chemin DIRECT DAMAGE (DoT feu vs swarm).

RE (structure, decompile = verite) :
- `IdunBattle.Core.Services.DamagePrediction$$CalculateDirectDamage` (chemin EXECUTION : appele par
  `IdunBattle.Operations.DirectDamageOperation$$Execute` via IDamagePrediction slot 7) route le montant par
  `IdunBattle.Core.Services.DamagePrediction$$ApplyGroupUnitDamageLimit` avec profile=NULL : cap = hp - maxHealthWith(remaining-1)
  (un degat direct ne tue AU PLUS qu'UN membre), skip si flag payload.
- `IdunBattle.Core.Services.DamagePrediction$$ApplyTraitDamageLimitsToDirectDamage` = MEME wrapper (profile=NULL), dispatch virtuel
  = la variante per-hit du pipeline d'attaque (`IdunBattle.Core.Services.DamagePrediction$$CalculateDamageOperation`, bytes de mode
  du hit-struct) — la route empruntee par la feuille `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAbilityDamage` (DoT feu).
Le port `execute_direct` n'applique AUCUN member-cap (case-60 par. 5). Ce probe mesure LIVE si le
tick natif du DoT feu est cape a la frontiere de membre (et donc si le port doit caper).

Scenario v7 (pool rank 17, ennemi INERTE) :
- P = necroSpyder (ScarabHive 1007 -> necroSmnSwarm 5 membres) + adeptRetributor «Vindicta»
  (ranged 4x Flame r2 + passif FireOfAbsolution : splash 3x Flame Direct sur TOUTES les unites
  adjacentes a la cible — friendly-fire — chaque coup splash POSE le feu sur la tuile de sa
  victime, #136, + Maybe 30%/hex adjacents).
- A = astraBullgryn (aucun passif reactif), hp-target enorme, et JAMAIS ACTIVE : le tour ennemi
  est joue par `aiPlayByUnit {maxActivations:0, captureEvents:true}` = ZERO activation + EndTurn
  qui capture les evenements de FRONTIERE (les ticks DoT du debut de NOTRE tour). rpc-drive.ts :
  la boucle d'activations ne tourne pas (0), l'EndTurn force est applique avec capture.
- Cycle : le hive (sur l'ennemi) spawn des scarabs adjacents ; Vindicta (distance 2) attaque
  l'ennemi -> son splash blesse les scarabs adjacents (etats HORS frontiere si per-hit/crit < PV
  membre) ET enflamme leurs tuiles ; au debut de notre tour suivant chaque scarab sur tuile en feu
  TICK -> datapoint. Geste discriminant garanti en sus : deplacer un scarab PLEIN (2218, rem=5)
  sur une tuile en feu libre -> gap = 2218-1775 = 443 < tick 444 -> cap natif 443 vs uncapped 444.

Modele du tick VERIFIE EXACT (runs 60102/60105) : base = round_fix64(20% x hpMax) = 444 ; net =
apply_pierce_and_modifiers(base, pierce=Flame 25, armor) (= 444 nu, 111 sous aura +886).
Comptabilite hp par scarab : snapshot au debut de NOTRE tour (verite) -> maj par la reponse
applyAction de l'attaque Vindicta (hp post-splash) -> cascade aiturn (ticks/heals ordonnes).
ASCII only (cp1252). Usage: python probe_60bis_directcap.py [--seed 60107] [--max-rounds 16]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hexgeo  # noqa: E402
import gameconfig as GC  # noqa: E402
import stream_events as SE  # noqa: E402
from rl_collect_batch import _resolve_session, _rpc  # noqa: E402
from engine.dsl.base import _round_fix64  # noqa: E402
from engine.services.damage_prediction import apply_pierce_and_modifiers  # noqa: E402
from engine.services.trait_damage_limits import (  # noqa: E402
    get_group_unit_remaining_member_count, get_group_unit_max_health_with_remaining_members)
from engine.runner.abilities.base import profile_pierce  # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
STATE = ROOT / "logs" / "runners" / "_60bis_directcap_state.json"
P_UNITS = "necroSpyder,adeptRetributor"
A_UNITS = "astraBullgryn"
W, H = 7, 9
MV = {"necroSpyder": 3, "necroSmnSwarm": 4, "adeptRetributor": 3}
SPY_VIS, VIN_VIS, TANK_VIS, SWARM_VIS = ("necroSpyder", "adeptRetributor",
                                         "astraBullgryn", "necroSmnSwarm")
SCARAB_HIVE = 1007
DOT_EFFECT = 5          # Effect_Type Fire (project_effect_type_attribution)
# #98 : la duree NATIVE du feu = `IdunBattle.Core.Services.BattleQuery$$ConvertRoundsToTurns(DefaultAmountOfRounds(5)=2 rounds)
# = 2 x count(joueurs non-Environment) = **4 tours** dans un duel standard. `FIRE_TURNS` reste la
# FENETRE d'observation de ce probe (nb de tours pendant lesquels il considere un feu « vivant ») ;
# la valeur 2 y est un choix de probe, PAS la duree native (l'ancien commentaire l'affirmait a tort).
FIRE_TURNS = 2


def _r(sid: int, method: str, body: dict, t: float = 90) -> dict:
    return (_rpc(sid, method, [body], timeout=t).get("result") or {})


def build(seed: int) -> int:
    STATE.unlink(missing_ok=True)
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
         "--state-file", str(STATE), "--board", "MC1_67",
         "--p-units", P_UNITS, "--a-units", A_UNITS,
         "--hp-target", "500000"],  # chip mob + 4 hits Vindicta/tour : il doit tenir ~16 rounds
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not STATE.exists():
        print(f"[60bis] build KO: {(proc.stderr or proc.stdout or '')[-400:]}", file=sys.stderr)
        sys.exit(2)
    for ln in (proc.stdout or "").splitlines():
        if "[build]" in ln:
            print("  " + ln)
    return json.loads(STATE.read_text())["runnerId"]


def _alive(dv: dict) -> list[dict]:
    return [u for u in (dv.get("units") or []) if u.get("alive")]


def _by_vis(dv: dict, vis: str) -> list[dict]:
    return [u for u in _alive(dv) if u.get("visualId") == vis]


def _pos(u: dict) -> tuple:
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row"))


def _snap_unit(snap: dict, eid: int) -> dict:
    return next((u for u in (snap.get("units") or []) if u.get("entityId") == eid), {})


def _move(rpc, rid, uid, cur, goal, occupied, mv, exact: bool = False) -> tuple:
    """exact=True : n'accepte QUE la tuile `goal` (pose sur la tuile en feu)."""
    cands = [t for t in hexgeo.disk(cur[0], cur[1], mv)
             if 0 <= t[0] < W and 0 <= t[1] < H and t not in occupied and t != cur]
    if exact:
        cands = [goal] if goal in cands else []
    else:
        cands.sort(key=lambda t: (hexgeo.distance(t, goal), hexgeo.distance(t, cur)))
    for t in cands:
        try:
            r = rpc("applyAction", {"runnerId": rid, "actions": [
                {"kind": "move", "unitId": uid, "to": {"col": t[0], "row": t[1]}}]}, 60)
        except Exception:
            continue
        if isinstance(r, dict) and r.get("ok", True) and not r.get("error"):
            return t
    return cur


def _endturn(rpc, rid) -> None:
    try:
        rpc("applyAction", {"runnerId": rid, "actions": [{"kind": "endturn"}]}, 60)
    except Exception:
        pass


def _hive_target(rpc, rid, spy_id: int) -> tuple:
    at = rpc("abilityTargets", {"runnerId": rid, "unitId": spy_id}, 60)
    for u in (at.get("units") or []):
        for ab in (u.get("abilities") or []):
            if ab.get("abilityId") != SCARAB_HIVE:
                continue
            fh = [t.get("targetId") for t in (ab.get("fromHere") or [])
                  if t.get("targetId") is not None]
            tg = [t.get("targetId") for t in (ab.get("targets") or [])
                  if t.get("targetId") is not None]
            return (fh[0] if fh else None, tg[0] if tg else None)
    return (None, None)


def _enemy_turn_active(rpc, rid, my_team: int) -> list:
    """Tour ENNEMI REEL (aiPlayByUnit captureEvents) — UNIQUEMENT quand le tank est VERROUILLE au
    coin (tous ses voisins occupes par des scarabs : il ne peut que melee, jamais bouger/chasser).
    Necessaire pour la capture des evenements de FRONTIERE (ticks DoT + heals LivingMetal de NOTRE
    debut de tour) : un tour a 0 activation ne les capture pas (run 60108, events=0)."""
    aenemy = 4 if my_team == 1 else 3
    for _ in range(3):
        cp = rpc("decisionView", {"runnerId": rid, "maxRank": 1}, 60).get("currentPlayer")
        if cp == aenemy:
            break
        _endturn(rpc, rid)
    else:
        print("[60bis] /!\\ flip H19 impossible -> tour ennemi saute")
        return []
    r = rpc("aiPlayByUnit", {"runnerId": rid, "maxTurns": 1, "maxActivations": 9999,
                             "maxPump": 2000, "captureEvents": True}, 300)
    print(f"[60bis]   enemy-turn ACTIF ok={r.get('ok')} stop={r.get('stopReason')} "
          f"events={r.get('cascadeCount')}")
    return r.get("cascade") or []


def _enemy_turn_skip(rpc, rid, my_team: int) -> None:
    """Tour ENNEMI SAUTE (inerte) : on endturn A SA PLACE jusqu'a recuperer la main. Un enemi en
    tours reels CHASSE a travers la carte (le hive, ancre a la tuile de cast, ne suit pas — vu run
    60109) ; un tour ennemi inerte fige tout. Le tick DoT de NOTRE debut de tour se mesure alors
    par DIFF (hp estime vs snapshot suivant) — voie validee run 60108 (u97 : 888 -> 444)."""
    amine = 3 if my_team == 1 else 4
    for _ in range(4):
        cp = rpc("decisionView", {"runnerId": rid, "maxRank": 1}, 60).get("currentPlayer")
        if cp == amine:
            return
        _endturn(rpc, rid)
    print("[60bis] /!\\ flip retour impossible (cp ne revient pas a moi)")


def _hp_events(cascade: list) -> list[dict]:
    """Mutations PV ORDONNEES (toutes cibles) : `UnitDamaged` / `HealInfo` / `RepairInfo`.

    Pas resolus PAR NOM (#254b-b) : `StepType` est implicitement numerote, un membre retire au
    milieu decale tout ce qui suit. Ces trois-la precedent le `RestoreArmorInfo` retire par
    `rnca9r7q6c`, donc leurs ordinaux n'ont pas bouge -- raison de plus pour ne pas les figer :
    rien ne signalerait leur invalidation au prochain build."""
    out = []
    s_dmg = SE.step_id("UnitDamaged")
    s_heal = (SE.step_id("HealInfo"), SE.step_id("RepairInfo"))
    for ev in cascade:
        if ev.get("kind") != "action":
            continue
        tags = SE._tags(ev)
        step = ev.get("step")
        if step == s_dmg:
            out.append({"kind": "dmg", "target": tags.get("Target_Id"),
                        "amount": tags.get("Amount") or 0,
                        "effect_type": tags.get("Effect_Type")})
        elif step in s_heal:
            out.append({"kind": "heal", "target": tags.get("Target_Id"),
                        "amount": tags.get("Amount") or 0, "effect_type": None})
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=60107)
    ap.add_argument("--max-rounds", type=int, default=16)
    args = ap.parse_args(argv)
    sid = _resolve_session()
    rid = build(args.seed)
    rpc = lambda m, b, t=90: _r(sid, m, b, t)   # noqa: E731

    pct = int(GC.global_value("fireDmgPct") or 20)
    pierce = int(profile_pierce(None, "Flame", ranged=False))
    print(f"[60bis] seed={args.seed} runner={rid} fireDmgPct={pct} pierce(Flame)={pierce}")

    dots, binding_hits = [], 0
    hive_cast = False
    vin_norm = None                    # ability id de l'attaque NORMALE de Vindicta
    hp_prev: dict[int, int] = {}       # eid scarab -> hp courant estime
    kit: dict[int, tuple] = {}         # eid -> (hp_max, n_base, armor)
    fire_tiles: dict[tuple, int] = {}  # tuile -> round de pose
    try:
        dv0 = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        my_team = next((u.get("team") for u in _alive(dv0) if u.get("visualId") == SPY_VIS), 1)
        ids = {v: (_by_vis(dv0, v) or [{}])[0].get("id") for v in (SPY_VIS, VIN_VIS, TANK_VIS)}
        if any(x is None for x in ids.values()):
            print(f"[60bis] roster KO ({ids})"); return 2
        spy, vin, tank = ids[SPY_VIS], ids[VIN_VIS], ids[TANK_VIS]
        for u in (dv0.get("units") or []):
            if u.get("id") == vin:
                for ab in (u.get("abilities") or []):
                    if ab.get("kind") == "normal":
                        vin_norm = ab.get("id") if ab.get("id") is not None else ab.get("abilityId")
        print(f"[60bis] spyder=u{spy} vindicta=u{vin} (normale={vin_norm}) tank=u{tank} "
              f"my_team={my_team} cp={dv0.get('currentPlayer')}")

        for rnd in range(args.max_rounds):
            dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1}, 60)
            if not _by_vis(dec, TANK_VIS):
                print(f"[60bis] tank mort round {rnd} -> stop"); break
            spy_u = (_by_vis(dec, SPY_VIS) or [None])[0]
            vin_u = (_by_vis(dec, VIN_VIS) or [None])[0]
            tank_u = _by_vis(dec, TANK_VIS)[0]
            swarms = _by_vis(dec, SWARM_VIS)
            tp = _pos(tank_u)
            pos = {u["id"]: _pos(u) for u in swarms}
            live_fire = {t: r0 for t, r0 in fire_tiles.items() if rnd - r0 < FIRE_TURNS}
            print(f"[60bis] r{rnd}: vin={_pos(vin_u) if vin_u else None} tank={tp} "
                  f"hp_tank={tank_u.get('hp')} scarabs={len(swarms)} feux={sorted(live_fire)}")

            if hive_cast and not swarms:
                hive_cast = False
                print(f"[60bis] r{rnd}: reserve scarabs epuisee -> re-cast du hive")
            if not hive_cast and spy_u is not None:
                fh, _tg = _hive_target(rpc, rid, spy)
                if fh is not None:
                    rr = rpc("applyAction", {"runnerId": rid, "actions": [
                        {"kind": "ability", "casterId": spy, "targetId": fh,
                         "abilityType": SCARAB_HIVE}]}, 90)
                    hive_cast = isinstance(rr, dict) and not rr.get("error")
                    print(f"[60bis] r{rnd}: CAST ScarabHive -> u{fh} ok={hive_cast}")
                    dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1}, 60)
                    swarms = _by_vis(dec, SWARM_VIS)
                    pos = {u["id"]: _pos(u) for u in swarms}

            # snapshot : hp + kit de TOUS les scarabs. Le TICK du debut de CE tour se mesure par
            # DIFF (hp estime post-attaque du tour precedent vs snapshot) : ennemi INERTE => les
            # SEULES mutations entre les deux = les effets de debut de tour (tick feu, LivingMetal
            # jamais observe). Tuiles TICKANTES a ce debut de tour = posees il y a 1..FIRE_TURNS.
            tick_fire = {t for t, r0 in fire_tiles.items() if 1 <= rnd - r0 <= FIRE_TURNS}
            if swarms:
                snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
                for u in swarms:
                    eid = u["id"]
                    su = _snap_unit(snap, eid)
                    st, sd = su.get("stats") or {}, su.get("statDelta") or {}
                    hp = int(st.get("health") or 0)
                    hp_max = hp - int(sd.get("health") or 0)
                    n_base = (int(st.get("numberOfMembers") or 0)
                              - int(sd.get("numberOfMembers") or 0))
                    armor = int(st.get("fixedArmor") or 0)
                    if eid in hp_prev and hp != hp_prev[eid]:
                        diff = hp_prev[eid] - hp
                        t = pos.get(eid)
                        if diff > 0 and t in tick_fire:
                            hp_at_tick = hp_prev[eid]
                            base = int(_round_fix64(Fraction(pct * hp_max, 100), 0))
                            uncapped = int(round(apply_pierce_and_modifiers(
                                base, pierce_pct=pierce, armor=armor, mods=None)))
                            rem = get_group_unit_remaining_member_count(
                                hp_max, n_base, hp_at_tick)
                            cap = None
                            if rem > 1:
                                cap = (hp_at_tick
                                       - get_group_unit_max_health_with_remaining_members(
                                           hp_max, n_base, rem - 1))
                            capped = min(uncapped, cap) if cap is not None else uncapped
                            binding = capped != uncapped
                            verdict = ("CAPPED" if diff == capped else
                                       "UNCAPPED" if diff == uncapped else "NI-L-UN-NI-L-AUTRE")
                            if verdict == "NI-L-UN-NI-L-AUTRE":
                                # canal DIFF pollue par LivingMetal (tick - heal melanges) :
                                # datapoint NON retenu (le canal cascade, lui, est ordonne)
                                print(f"[60bis] r{rnd}: diff AMBIGU u{eid} diff={diff} "
                                      f"hp={hp_at_tick} (LivingMetal ?) -> ignore")
                            else:
                                if binding:
                                    binding_hits += 1
                                dots.append({"rnd": rnd, "eid": eid, "hp_at_tick": hp_at_tick,
                                             "native": diff, "uncapped": uncapped, "cap": cap,
                                             "capped": capped, "rem": rem, "binding": binding,
                                             "verdict": verdict, "channel": "diff"})
                                print(f"[60bis] r{rnd}: DOT(diff) u{eid} natif={diff} "
                                      f"hp={hp_at_tick} rem={rem} uncapped={uncapped} cap={cap} "
                                      f"{'** DISCRIMINANT **' if binding else '(non discr.)'} "
                                      f"-> {verdict}")
                        else:
                            print(f"[60bis] r{rnd}: /!\\ continuite u{eid}: attendu "
                                  f"{hp_prev[eid]} lu {hp} (tuile={t}, pas en feu tickant)")
                    hp_prev[eid] = hp
                    kit[eid] = (hp_max, n_base, armor)

            occupied = {_pos(u) for u in _alive(dec)}

            # COLMATER LE COIN : poser des scarabs sur les voisins LIBRES du tank. Tank verrouille
            # (0 voisin libre) => son activation ne peut que melee un scarab adjacent (Physical,
            # pas de feu), jamais bouger/chasser => on peut jouer son tour en REEL (capture).
            free_nb = [t for t in hexgeo.ring(tp[0], tp[1], 1)
                       if 0 <= t[0] < W and 0 <= t[1] < H and t not in occupied]
            for t in list(free_nb):
                cand = [u for u in swarms
                        if u["id"] in pos and hexgeo.distance(pos[u["id"]], tp) > 1
                        and hexgeo.distance(pos[u["id"]], t) <= MV[SWARM_VIS]]
                if not cand:
                    continue
                b = min(cand, key=lambda u: hexgeo.distance(pos[u["id"]], t))
                newp = _move(rpc, rid, b["id"], pos[b["id"]], t, occupied, MV[SWARM_VIS],
                             exact=True)
                if newp == t:
                    occupied.discard(pos[b["id"]])
                    pos[b["id"]] = t
                    occupied.add(t)
                    free_nb.remove(t)
                    print(f"[60bis] r{rnd}: mur — scarab u{b['id']} bouche {t}")

            # Vindicta : approche a distance 2 du tank (tours ENNEMIS REELS : Bullgryn threat =
            # MV3+1 -> ne s'exposer que si le MUR de scarabs autour de lui est assez ferme, il ne
            # peut alors pas bouger) puis ATTAQUE NORMALE ranged (4x Flame sur le tank + splash
            # FireOfAbsolution 3x Flame Direct sur TOUS les scarabs adjacents + feu pose sur la
            # tuile de chaque victime splash, #136).
            wall = sum(1 for u in swarms if hexgeo.distance(pos[u["id"]], tp) == 1)
            tank_hp = int(tank_u.get("hp") or 0)
            if vin_u is not None:
                vp = _pos(vin_u)
                if hexgeo.distance(vp, tp) > 2:      # ennemi INERTE : approche sans danger
                    ring2 = [t for t in hexgeo.ring(tp[0], tp[1], 2)
                             if 0 <= t[0] < W and 0 <= t[1] < H and t not in occupied]
                    if ring2:
                        goal = min(ring2, key=lambda t: hexgeo.distance(t, vp))
                        vp = _move(rpc, rid, vin, vp, goal, occupied, MV[VIN_VIS])
                # gates : (1) une victime splash existe (sinon on ne fait que torcher le tank) ;
                # (2) budget brulure du tank (20% PVmax/tick sur SA tuile — il meurt en ~5 ticks
                # d'attaques consecutives) : on cesse d'attaquer sous 150k pour laisser le feu
                # de sa tuile expirer.
                if (hexgeo.distance(vp, tp) <= 2 and vin_norm is not None and wall >= 1
                        and tank_hp > 220000):
                    rr = rpc("applyAction", {"runnerId": rid, "actions": [
                        {"kind": "ability", "casterId": vin, "targetId": tank,
                         "abilityType": vin_norm}]}, 90)
                    ok = isinstance(rr, dict) and not rr.get("error")
                    hits = {u.get("squadId"): u.get("hp") for u in (rr.get("units") or [])}
                    burned, killed = [], []
                    for eid, old in list(hp_prev.items()):
                        if eid not in hits:
                            continue
                        nh = int(hits[eid] or 0)
                        if nh <= 0:
                            # victime TUEE par le splash SUR sa tuile re-enflammee -> tuile
                            # LIBRE + feu FRAIS = candidate ideale pour le B-placement
                            if eid in pos:
                                fire_tiles[pos[eid]] = rnd
                                occupied.discard(pos[eid])
                                killed.append((f"u{eid}", pos[eid]))
                            hp_prev.pop(eid, None)
                        elif nh < old:
                            hp_prev[eid] = nh
                            if eid in pos:
                                fire_tiles[pos[eid]] = rnd     # feu pose par le coup splash (#136)
                                burned.append((f"u{eid}", old - nh, pos[eid]))
                        else:
                            hp_prev[eid] = nh
                    print(f"[60bis] r{rnd}: VIN attaque tank ok={ok} wall={wall} "
                          f"splash={burned} kills={killed}")

            # geste discriminant APRES l'attaque : poser un scarab PLEIN (2218, rem=5) sur une
            # tuile en feu LIBRE (typiquement liberee par un kill splash, feu re-pose a l'instant)
            # -> tick GARANTI au prochain debut de tour : cap natif 443 (atterrit 1775) vs 444.
            live_fire = {t: r0 for t, r0 in fire_tiles.items() if rnd - r0 < FIRE_TURNS}
            placed_flag = False
            for t in sorted(live_fire, key=lambda x: -live_fire[x]):    # feux les plus FRAIS d'abord
                if t in occupied:
                    continue
                cand = [u for u in swarms
                        if hp_prev.get(u["id"]) == kit.get(u["id"], (0,))[0]
                        and kit.get(u["id"], (0, 0))[1] >= 2
                        and u["id"] in pos and hexgeo.distance(pos[u["id"]], t) <= MV[SWARM_VIS]]
                if not cand:
                    continue
                b = min(cand, key=lambda u: hexgeo.distance(pos[u["id"]], t))
                newp = _move(rpc, rid, b["id"], pos[b["id"]], t, occupied, MV[SWARM_VIS],
                             exact=True)
                if newp == t:
                    occupied.discard(pos[b["id"]])
                    pos[b["id"]] = t
                    occupied.add(t)
                    placed_flag = True
                    print(f"[60bis] r{rnd}: scarab PLEIN u{b['id']} pose sur feu {t} "
                          f"(hp={hp_prev[b['id']]})")
                    break
            if spy_u is not None:
                sp_cur = _pos(spy_u)
                if hive_cast:
                    # ennemi INERTE : tenir a distance ~3 du tank pour pouvoir RE-caster le hive
                    # quand la reserve de scarabs s'epuise
                    if hexgeo.distance(sp_cur, tp) > 3:
                        _move(rpc, rid, spy, sp_cur, tp, occupied, MV[SPY_VIS])
                else:
                    _move(rpc, rid, spy, sp_cur, tp, occupied, MV[SPY_VIS])
                    fh2, _tg2 = _hive_target(rpc, rid, spy)
                    if fh2 is not None:
                        rr = rpc("applyAction", {"runnerId": rid, "actions": [
                            {"kind": "ability", "casterId": spy, "targetId": fh2,
                             "abilityType": SCARAB_HIVE}]}, 90)
                        hive_cast = isinstance(rr, dict) and not rr.get("error")
                        print(f"[60bis] r{rnd}: CAST ScarabHive post-move -> u{fh2} "
                              f"ok={hive_cast}")
            _endturn(rpc, rid)
            # B vient d'etre pose sur une tuile en feu : SAUTER le tour ennemi (le tank melerait
            # B a 444 avant son tick — vu run 60111). B est PLEIN => LivingMetal INERTE dessus =>
            # le DIFF du prochain snapshot est le tick PUR (2218 -> 1775 cape vs 1774 non-cape).
            dv2 = rpc("decisionView", {"runnerId": rid, "maxRank": 1}, 60)
            occ2 = {_pos(u) for u in _alive(dv2)}
            tank_locked = all(t in occ2 for t in hexgeo.ring(tp[0], tp[1], 1)
                              if 0 <= t[0] < W and 0 <= t[1] < H)
            if placed_flag or not tank_locked:
                _enemy_turn_skip(rpc, rid, my_team)
                continue
            cascade = _enemy_turn_active(rpc, rid, my_team)
            evs = _hp_events(cascade)
            run_hp = dict(hp_prev)
            for e in evs:
                tgt = e.get("target")
                if tgt not in run_hp:
                    continue
                if e["kind"] == "dmg" and e["effect_type"] == DOT_EFFECT:
                    hp_max, n_base, armor = kit.get(tgt, (0, 1, 0))
                    hp_at_tick = run_hp[tgt]
                    base = int(_round_fix64(Fraction(pct * hp_max, 100), 0))
                    uncapped = int(round(apply_pierce_and_modifiers(
                        base, pierce_pct=pierce, armor=armor, mods=None)))
                    rem = get_group_unit_remaining_member_count(hp_max, n_base, hp_at_tick)
                    cap = None
                    if rem > 1:
                        cap = hp_at_tick - get_group_unit_max_health_with_remaining_members(
                            hp_max, n_base, rem - 1)
                    capped = min(uncapped, cap) if cap is not None else uncapped
                    binding = capped != uncapped
                    verdict = ("CAPPED" if e["amount"] == capped else
                               "UNCAPPED" if e["amount"] == uncapped else "NI-L-UN-NI-L-AUTRE")
                    if binding:
                        binding_hits += 1
                    dots.append({"rnd": rnd, "eid": tgt, "hp_at_tick": hp_at_tick,
                                 "native": e["amount"], "uncapped": uncapped, "cap": cap,
                                 "capped": capped, "rem": rem, "binding": binding,
                                 "verdict": verdict, "channel": "cascade"})
                    print(f"[60bis] r{rnd}: DOT(cascade) u{tgt} natif={e['amount']} "
                          f"hp={hp_at_tick} rem={rem} uncapped={uncapped} cap={cap} "
                          f"{'** DISCRIMINANT **' if binding else '(non discr.)'} -> {verdict}")
                run_hp[tgt] = max(0, run_hp[tgt] + (e["amount"] if e["kind"] == "heal"
                                                    else -e["amount"]))
            hp_prev = run_hp

        print(f"\n[60bis] BILAN: {len(dots)} ticks DoT observes, {binding_hits} discriminants")
        for d in dots:
            print(f"  r{d['rnd']} u{d['eid']} hp={d['hp_at_tick']} rem={d['rem']} "
                  f"native={d['native']} uncapped={d['uncapped']} cap={d['cap']} "
                  f"{'DISCR' if d['binding'] else '     '} -> {d['verdict']}")
        disc = [d for d in dots if d["binding"]]
        weird = [d for d in dots if d["verdict"] == "NI-L-UN-NI-L-AUTRE"]
        if weird:
            print("[60bis] /!\\ ticks inexpliques (ni cap ni uncapped) -> modele a revoir")
            return 3
        if not disc:
            print("[60bis] aucun datapoint discriminant -> relancer (seed/rounds)")
            return 4
        caps = {d["verdict"] for d in disc}
        print(f"[60bis] VERDICT sur points discriminants: {caps}")
        return 0 if caps == {"CAPPED"} else (1 if caps == {"UNCAPPED"} else 5)
    finally:
        try:
            _r(sid, "disposeRunner", {"runnerId": rid}, 15)
            print(f"[60bis] runner {rid} dispose")
        except Exception as e:
            print(f"[60bis] dispose KO: {e}")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
