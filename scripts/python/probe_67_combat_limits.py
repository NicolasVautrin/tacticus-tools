#!/usr/bin/env python
"""Probe #67 — etage LIMITES du COMBAT (member-cap Swarm / bypass Blast / Resilient) en EXECUTION.

RE (structure, decompile = verite) :
- L'EXECUTION native applique `IdunBattle.Core.Services.DamagePrediction$$ApplyTraitDamageLimitsToDamage` par COUP :
  attaque normale via la routine per-coup d'`IdunBattle.Operations.AttackDamageOperation$$ExecuteHit` (wrappers mode-1
  `IdunBattle.Core.Services.DamagePrediction$$ApplyTraitDamageLimitsToAttackDamage/IdunBattle.Core.Services.DamagePrediction$$ApplyTraitDamageLimitsToAttackDamage`, virtual-only : cellules min/max
  capees AVANT la resolution du tirage), ability/splash via `IdunBattle.Core.Services.DamagePrediction$$CalculateAbilityDamage`
  (mode 2 : `ApplyTraitDamageLimitsToDamage(2, &dmg, &dmg, profil, cible, ..., hp=hc+0x18)`).
- Sous-limites : `IdunBattle.Core.Services.DamagePrediction$$ApplyGroupUnitDamageLimit` (member-cap, skip si profil
  HitsMultipleMembers=Blast ; flag natif = octet 0 CONSTANT, l'overkill ne bypasse PAS),
  `IdunBattle.Core.Services.DamagePrediction$$ApplyResilientTraitDamageLimit` (trait 1009 : cap a hp-1, gate `IdunBattle.Core.Services.DamagePrediction$$IsOverkill`), `IdunBattle.Core.Services.DamagePrediction$$ApplyImperviousTraitDamageLimit` (trait 28, mode attack only).
Le port #67 cable cet etage (partage avec la prediction, `services/trait_damage_limits.py`)
dans `_run_hits` (runner/operations/damage.py) entre le tirage et le split.

4 scenarios (replay-diff : meme MT via dumpRng, load_state offline, comparaison hp exacte) :
  swarm     P=adeptRetributor  A=necroSpyder     : l'ennemi caste ScarabHive SUR ma Vindicta
            (cast manuel a son tour -> scarabs PLEINS spawn adjacents) ; Vindicta (4x Flame r2)
            attaque un scarab PLEIN (2218, 5 membres) -> caps per-coup attendus 443/443/444/444,
            hp final 444 EXACT (sequence observee live run 60102, #57d).
  blast     P=astraOrdnance (Blast r3, profil HitsMultipleMembers) meme montage : le degat
            TRAVERSE la frontiere de membre (bypass) -> hp final = 2218 - degat plein.
  resilient P=adeptRetributor  A=astraYarrick --hp-target 3000 (tours ennemis sautes) :
            coups ~2100-2900 -> AUCUN n'ouvre la porte overkill (roll < hpMax + rem) : le coup
            letal cape a rem-1 (= hp-1), les suivants a 0 -> hp final 1 EXACT. (A hp 1500 la
            porte s'ouvrait au coup 2 : live [1499, 1] -> mort, reproduit EXACT offline, run
            67072 — datapoint overkill mi-sequence.)
  overkill  idem --hp-target 300 : 1er coup accum >= 2x hpMax -> porte IsOverkill ouverte ->
            cap Resilient BYPASSE -> il meurt (hp 0).
Verdict par scenario : off_after == live_after (et pattern per-coup pour swarm/resilient).
ASCII only (cp1252). Usage: python probe_67_combat_limits.py [--scenario all] [--seed 67001]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hexgeo  # noqa: E402
import gameconfig as GC  # noqa: E402
import stream_events as SE  # noqa: E402
from rl_collect_batch import _resolve_session, _rpc  # noqa: E402
from engine.runner.snapshot import load_state  # noqa: E402
from engine.runner.runner import Runner  # noqa: E402
from engine.runner.messages import AttackUnitMessage  # noqa: E402
from engine.runner.prng import IntBasedMersenneTwister  # noqa: E402
from engine.runner.components import HealthComponent  # noqa: E402
from engine.services.trait_damage_limits import (  # noqa: E402
    get_group_unit_remaining_member_count, get_group_unit_max_health_with_remaining_members)

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
W, H = 7, 9                      # MC1_67
SCARAB_HIVE = 1007
SWARM_VIS = "necroSmnSwarm"


def _r(sid: int, method: str, body: dict, t: float = 90) -> dict:
    return (_rpc(sid, method, [body], timeout=t).get("result") or {})


def build(seed: int, tag: str, p_units: str, a_units: str, hp_target: int | None) -> tuple:
    state_file = ROOT / "logs" / "runners" / f"_67_{tag}_state.json"   # SORTIE -> logs/ (#349)
    state_file.unlink(missing_ok=True)
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
           "--state-file", str(state_file), "--board", "MC1_67",
           "--p-units", p_units, "--a-units", a_units]
    if hp_target:
        cmd += ["--hp-target", str(hp_target)]
    proc = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not state_file.exists():
        print(f"[67] build {tag} KO: {(proc.stderr or proc.stdout or '')[-400:]}", file=sys.stderr)
        return None, state_file
    return json.loads(state_file.read_text())["runnerId"], state_file


def _alive(dv: dict) -> list[dict]:
    return [u for u in (dv.get("units") or []) if u.get("alive")]


def _by_vis(dv: dict, vis: str) -> list[dict]:
    return [u for u in _alive(dv) if u.get("visualId") == vis]


def _pos(u: dict) -> tuple:
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row"))


def _hp_map(ob: dict) -> dict:
    return {u.get("squadId"): (u.get("hp"), u.get("hpMax")) for u in (ob.get("units") or [])}


def _normal_id(dv: dict, uid: int):
    for u in (dv.get("units") or []):
        if u.get("id") == uid:
            for ab in (u.get("abilities") or []):
                if ab.get("kind") == "normal":
                    return ab.get("id") if ab.get("id") is not None else ab.get("abilityId")
    return None


def _endturn(rpc, rid) -> None:
    try:
        rpc("applyAction", {"runnerId": rid, "actions": [{"kind": "endturn"}]}, 60)
    except Exception:
        pass


def _flip_to(rpc, rid, player: int, max_flips: int = 4) -> bool:
    for _ in range(max_flips):
        cp = rpc("decisionView", {"runnerId": rid, "maxRank": 1}, 60).get("currentPlayer")
        if cp == player:
            return True
        _endturn(rpc, rid)
    return False


def _move_toward(rpc, rid, uid, cur, goal, occupied, mv, want_dist: int) -> tuple:
    """Deplace `uid` vers une tuile a distance <= want_dist de `goal` (meilleure d'abord)."""
    cands = [t for t in hexgeo.disk(cur[0], cur[1], mv)
             if 0 <= t[0] < W and 0 <= t[1] < H and t not in occupied and t != cur]
    cands.sort(key=lambda t: (hexgeo.distance(t, goal), hexgeo.distance(t, cur)))
    for t in cands:
        try:
            r = rpc("applyAction", {"runnerId": rid, "actions": [
                {"kind": "move", "unitId": uid, "to": {"col": t[0], "row": t[1]}}]}, 60)
        except Exception:
            continue
        if (r.get("actions") or [{}])[0].get("ok"):
            return t
    return cur


def _seed_rng(s: dict) -> IntBasedMersenneTwister:
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"])
    rng.mti = s["mti"]
    return rng


def _fresh_my_turn(rpc, rid, mine: int) -> bool:
    """Garantit un tour A MOI FRAIS (activation pleine pour mes unites) : cycle un endturn puis
    flip jusqu'a currentPlayer == mine. applyAction est permissif sur le proprietaire, mais une
    unite qui a deja agi ce tour no-op silencieusement (ok=True, mutated=false — vu run 67021)."""
    _endturn(rpc, rid)
    return _flip_to(rpc, rid, mine)


def _live_amounts(res: dict, tgt_id: int, norm_id: int) -> tuple[list[int], int | None]:
    """(amounts, hp_apres) des coups de l'ATTAQUE NORMALE live sur `tgt_id` (events step 4 de la
    reponse applyAction, filtres `Active_Ability_Type == norm_id` sans Effect_Type). Les events
    d'un vecteur SEPARE dans la meme action — ex. le volet feu probabiliste de FireOfAbsolution
    (eff=5, ab=None, present ~1 run sur 2 : runs 67031 non / 67041+67051 oui) — sont ecartes :
    ils ne font pas partie de l'attaque normale que replaye l'offline. `hp_apres` = la
    RemainingHealth du DERNIER coup normal (frontiere de comparaison off/live)."""
    out, last_rem = [], None
    for a in (res.get("actions") or []):
        for ev in (a.get("events") or []):
            if ev.get("kind") == "action" and ev.get("step") == SE.step_id("UnitDamaged"):
                try:
                    tags = json.loads(ev.get("tags") or "{}")
                except Exception:
                    continue
                if tags.get("Target_Id") != tgt_id or tags.get("Amount") is None:
                    continue
                if tags.get("Active_Ability_Type") != norm_id or tags.get("Effect_Type"):
                    print(f"[67]   (event step-4 hors attaque normale ecarte: "
                          f"amt={tags.get('Amount')} eff={tags.get('Effect_Type')} "
                          f"ab={tags.get('Active_Ability_Type')} "
                          f"rem={tags.get('UnitStats_RemainingHealth')})")
                    continue
                out.append(int(tags["Amount"]))
                if tags.get("UnitStats_RemainingHealth") is not None:
                    last_rem = int(tags["UnitStats_RemainingHealth"])
    return out, last_rem


def replay_attack(rpc, rid, att_id: int, tgt_id: int, norm_id: int) -> dict | None:
    """Attaque LIVE + replay OFFLINE (meme MT) — renvoie {hp_before, live_after, off_after, rr}."""
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    dv2 = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob2 = rpc("observeBattle", {"runnerId": rid}, 40)
    state = load_state(dv2, ob2, snap)
    te = state.get_entity(tgt_id)
    hc = te.get_component(HealthComponent) if te is not None else None
    if hc is None or hc.hp is None:
        print("[67]   replay KO: cible sans HealthComponent offline")
        return None
    hp_before = hc.hp
    s1 = rpc("dumpRng", {"runnerId": rid}, 30)
    if not s1.get("mt"):
        print("[67]   replay KO: dumpRng indispo")
        return None
    state.rng = _seed_rng(s1)
    runner = Runner(state).install_default_handlers(20)
    res = rpc("applyAction", {"runnerId": rid, "actions": [
        {"kind": "ability", "casterId": att_id, "targetId": tgt_id,
         "abilityType": norm_id}]}, 60)
    a0 = (res.get("actions") or [{}])[0]
    if not a0.get("ok") or not a0.get("mutated"):
        print(f"[67]   attaque LIVE refusee/no-op (ok={a0.get('ok')} mutated={a0.get('mutated')}) "
              f"— activation deja consommee ?")
        return None
    live_after = next((u.get("hp") for u in (res.get("units") or [])
                       if u.get("squadId") == tgt_id), None)
    if live_after is None:
        ch = next((c for c in (a0.get("changes") or []) if c.get("squadId") == tgt_id), None)
        live_after = ch.get("hpAfter") if ch else None
    runner.apply(AttackUnitMessage(att_id, tgt_id))
    rr = runner.damage_handler.last
    off_after = state.get_entity(tgt_id).get_component(HealthComponent).hp
    live_hits, live_after_normal = _live_amounts(res, tgt_id, norm_id)
    return {"hp_before": hp_before, "live_after": live_after,
            "off_after": off_after, "rr": rr, "live_hits": live_hits,
            "live_after_normal": live_after_normal if live_after_normal is not None
            else live_after}


def _effective_seq(per_hit: list, hp_before: int) -> list[int]:
    """Sequence per-coup EFFECTIVE attendue cote live : l'Amount d'un event step-4 =
    min(degat du coup, hp restant), et les coups offline roules APRES la mort de la cible
    ne produisent AUCUN event live (le natif s'arrete a la mort) -> tronque a 0 hp."""
    out, rem = [], int(hp_before or 0)
    for d in (per_hit or []):
        if rem <= 0:
            break
        eff = min(int(d), rem)
        out.append(eff)
        rem -= eff
    return out


def expected_swarm_caps(hp_max: int, n: int, hits: int) -> list[int]:
    """Caps per-coup attendus vs cible multi-membre PLEINE (rolls tous >= cap) — hp avance."""
    out, hp = [], hp_max
    for _ in range(hits):
        rem = get_group_unit_remaining_member_count(hp_max, n, hp)
        if rem <= 1:
            out.append(None)          # plus de cap (dernier membre) : degat = roll
            continue
        cap = hp - get_group_unit_max_health_with_remaining_members(hp_max, n, rem - 1)
        out.append(cap)
        hp -= cap
    return out


def _hive_fromhere(rpc, rid, spy_id: int) -> tuple[list, list]:
    """(fromHere, targets) du ScarabHive pour le spyder (listes d'ids de cible legale)."""
    at = rpc("abilityTargets", {"runnerId": rid, "unitId": spy_id}, 60)
    for u in (at.get("units") or []):
        for ab in (u.get("abilities") or []):
            if ab.get("abilityId") != SCARAB_HIVE:
                continue
            fhs = [t.get("targetId") for t in (ab.get("fromHere") or [])
                   if t.get("targetId") is not None]
            tgs = [t.get("targetId") for t in (ab.get("targets") or [])
                   if t.get("targetId") is not None]
            return fhs, tgs
    return [], []


def _spawn_scarabs(rpc, rid, my_team: int, spy_id: int, att_id: int, bait_id: int,
                   max_rounds: int = 8) -> bool:
    """Fait caster ScarabHive par le spyder ENNEMI sur mon APPAT (astraBullgryn : le burst du
    cast + les scarabs agissant a l'apparition tuent une cible fragile — vu run 67011, Vindicta
    7029 hp morte au tour du cast). L'attaquant reste EN RETRAIT (>=3 du spyder) ; l'appat
    avance. applyAction accepte les gestes des unites ennemies hors de leur tour -> pas besoin
    de flips pour le cast manuel. Retour True des qu'un scarab (PLEIN au spawn) est vivant."""
    for rnd in range(max_rounds):
        dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1}, 60)
        if not (dv.get("units") or []):
            print("[67]   bataille terminee avant spawn (decisionView vide)")
            return False
        if _by_vis(dv, SWARM_VIS):
            return True
        spy_u = next((u for u in _alive(dv) if u.get("id") == spy_id), None)
        bait_u = next((u for u in _alive(dv) if u.get("id") == bait_id), None)
        if spy_u is None or bait_u is None:
            ob = rpc("observeBattle", {"runnerId": rid}, 40)
            print(f"[67]   spyder ou appat mort avant spawn — hp={_hp_map(ob)}")
            return False
        # l'appat avance vers le spyder ; le spyder avance vers l'appat ; cast des que legal
        occ = {_pos(u) for u in _alive(dv)}
        if hexgeo.distance(_pos(bait_u), _pos(spy_u)) > 2:
            _move_toward(rpc, rid, bait_id, _pos(bait_u), _pos(spy_u), occ,
                         int((GC.unit(bait_u.get("visualId")) or {}).get("Movement") or 2), 2)
            dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1}, 60)
            occ = {_pos(u) for u in _alive(dv)}
            spy_u = next((u for u in _alive(dv) if u.get("id") == spy_id), spy_u)
            bait_u = next((u for u in _alive(dv) if u.get("id") == bait_id), bait_u)
        fhs, tgs = _hive_fromhere(rpc, rid, spy_id)
        if bait_id not in fhs:
            _move_toward(rpc, rid, spy_id, _pos(spy_u), _pos(bait_u), occ,
                         int((GC.unit(spy_u.get("visualId")) or {}).get("Movement") or 3), 1)
            fhs, tgs = _hive_fromhere(rpc, rid, spy_id)
        if bait_id in fhs or fhs:
            fh = bait_id if bait_id in fhs else fhs[0]
            r = rpc("applyAction", {"runnerId": rid, "actions": [
                {"kind": "ability", "casterId": spy_id, "targetId": fh,
                 "abilityType": SCARAB_HIVE}]}, 60)
            print(f"[67]   r{rnd}: hive cast sur u{fh} "
                  f"ok={(r.get('actions') or [{}])[0].get('ok')}")
        else:
            print(f"[67]   r{rnd}: hive pas encore castable (approche, fh={fhs} tg={tgs})")
        dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1}, 60)
        if _by_vis(dv, SWARM_VIS):
            return True
        _endturn(rpc, rid)      # cycle les tours (le spawn du hive peut venir au tour necron)
    return False


def scenario_swarm(sid, seed: int, attacker_vis: str, expect_bypass: bool) -> int:
    """swarm (adeptRetributor, caps attendus) / blast (astraOrdnance, bypass attendu)."""
    tag = "blast" if expect_bypass else "swarm"
    rid, state_file = build(seed, tag, f"{attacker_vis},astraBullgryn", "necroSpyder", None)
    if rid is None:
        return 2
    rpc = lambda m, b, t=90: _r(sid, m, b, t)   # noqa: E731
    try:
        dv0 = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        att_u = (_by_vis(dv0, attacker_vis) or [None])[0]
        spy_u = (_by_vis(dv0, "necroSpyder") or [None])[0]
        bait_u = (_by_vis(dv0, "astraBullgryn") or [None])[0]
        if att_u is None or spy_u is None or bait_u is None:
            print(f"[67] {tag}: roster KO")
            return 2
        att, spy, bait = att_u["id"], spy_u["id"], bait_u["id"]
        my_team = att_u.get("team")
        norm = _normal_id(dv0, att)
        gau = GC.unit(attacker_vis) or {}
        rng_w = next((w for w in (gau.get("weapons") or []) if w.get("Range")), {})
        w_range = int(rng_w.get("Range") or 1)
        mv = int(gau.get("Movement") or 3)
        print(f"[67] {tag}: runner={rid} att=u{att} (normale={norm}, r{w_range}) "
              f"spyder=u{spy} appat=u{bait}")
        if not _spawn_scarabs(rpc, rid, my_team, spy, att, bait):
            print(f"[67] {tag}: aucun scarab spawne -> ECHEC montage")
            return 3
        # tour FRAIS puis approche a distance 2..w_range (arme RANGED, ex. 4 coups Vindicta)
        # du scarab PLEIN le plus proche ; dist 1 (melee 1 coup) = pis-aller si encercle.
        mine = 3 if my_team == 1 else 4
        tgt = t_hp = t_hpmax = None
        n = int((GC.unit(SWARM_VIS) or {}).get("nrOfMembers") or 1)
        for _ in range(5):
            if not _fresh_my_turn(rpc, rid, mine):
                print(f"[67] {tag}: flip vers mon tour impossible")
                return 3
            dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1}, 60)
            ob = rpc("observeBattle", {"runnerId": rid}, 40)
            hp = _hp_map(ob)
            att_u = next((u for u in _alive(dv) if u.get("id") == att), None)
            fulls = [u for u in _by_vis(dv, SWARM_VIS)
                     if hp.get(u["id"], (None, None))[0] == hp.get(u["id"], (None, None))[1]]
            if att_u is None or not fulls:
                print(f"[67] {tag}: pas de scarab PLEIN "
                      f"(swarms={[(u['id'], hp.get(u['id'])) for u in _by_vis(dv, SWARM_VIS)]})")
                return 3
            fulls.sort(key=lambda u: hexgeo.distance(_pos(att_u), _pos(u)))
            s_pos = _pos(fulls[0])
            d = hexgeo.distance(_pos(att_u), s_pos)
            if 2 <= d <= w_range:
                tgt = fulls[0]["id"]
                t_hp, t_hpmax = hp[tgt]
                break
            occ = {_pos(u) for u in _alive(dv)}
            cands = [t for t in hexgeo.disk(_pos(att_u)[0], _pos(att_u)[1], mv)
                     if 0 <= t[0] < W and 0 <= t[1] < H and t not in occ and t != _pos(att_u)]
            best = sorted((t for t in cands if 2 <= hexgeo.distance(t, s_pos) <= w_range),
                          key=lambda t: hexgeo.distance(t, s_pos))
            if best:
                r2 = rpc("applyAction", {"runnerId": rid, "actions": [
                    {"kind": "move", "unitId": att, "to": {"col": best[0][0], "row": best[0][1]}}]}, 60)
                if (r2.get("actions") or [{}])[0].get("ok"):
                    tgt = fulls[0]["id"]
                    t_hp, t_hpmax = hp[tgt]
                    break
            elif d == 1:                       # encercle : melee 1 coup, datapoint valable
                tgt = fulls[0]["id"]
                t_hp, t_hpmax = hp[tgt]
                break
            else:
                _move_toward(rpc, rid, att, _pos(att_u), s_pos, occ, mv, w_range)
        if tgt is None:
            print(f"[67] {tag}: cible jamais a portee -> ECHEC montage")
            return 3
        out = replay_attack(rpc, rid, att, tgt, norm)
        if out is None:
            return 3
        rr = out["rr"] or {}
        live_hits = out.get("live_hits") or []
        live_an = out.get("live_after_normal")
        live_dmg = (out["hp_before"] or 0) - int(live_an or 0)
        print(f"[67] {tag}: scarab u{tgt} PLEIN {t_hp}/{t_hpmax} n={n} | offline hits="
              f"{rr.get('hits')} rolls={rr.get('rolls')} per_hit={rr.get('per_hit')}")
        print(f"[67] {tag}: live per-coup {live_hits} : {out['hp_before']} -> {live_an} "
              f"(attaque normale ; hp fin d'action {out['live_after']}) | offline -> "
              f"{out['off_after']} (total {rr.get('total')})")
        seq_ok = live_hits == _effective_seq(rr.get("per_hit"), out["hp_before"])
        if expect_bypass:
            okc = live_dmg > 443 and out["off_after"] == live_an and seq_ok
            print(f"[67] {tag}: bypass Blast {'OK' if okc else 'ECHEC'} "
                  f"(degat {live_dmg} {'>' if live_dmg > 443 else '<='} 443, "
                  f"off==live: {out['off_after'] == live_an}, seq: {seq_ok})")
            return 0 if okc else 1
        caps = expected_swarm_caps(t_hpmax, n, int(rr.get("hits") or 0))
        exp = [c if (c is not None and r >= c) else r
               for c, r in zip(caps, rr.get("rolls") or [])]
        okc = (out["off_after"] == live_an and seq_ok and (rr.get("per_hit") or []) == exp)
        print(f"[67] {tag}: caps attendus {caps} -> per_hit attendu {exp} | "
              f"{'OK' if okc else 'ECHEC'} (off==live: {out['off_after'] == live_an}, "
              f"seq live==off: {seq_ok})")
        return 0 if okc else 1
    finally:
        try:
            _r(sid, "disposeRunner", {"runnerId": rid}, 15)
            print(f"[67] {tag}: runner {rid} dispose")
        except Exception as e:
            print(f"[67] {tag}: dispose KO: {e}")
        state_file.unlink(missing_ok=True)


def scenario_resilient(sid, seed: int, hp_target: int, expect_dead: bool) -> int:
    """resilient (hp-target 1500 : survit a 1 PV) / overkill (hp-target 300 : meurt)."""
    tag = "overkill" if expect_dead else "resilient"
    # resilient = hp NATIF (jamais --hp-target : il fausse les bornes de roll — artefact
    # harnais, cf. docstring) ; overkill = hp-target bas (drift masque par Amount=min(roll,hp)).
    rid, state_file = build(seed, tag, "adeptRetributor", "astraYarrick",
                            hp_target if expect_dead else None)
    if rid is None:
        return 2
    rpc = lambda m, b, t=90: _r(sid, m, b, t)   # noqa: E731
    try:
        dv0 = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        att_u = (_by_vis(dv0, "adeptRetributor") or [None])[0]
        jak_u = (_by_vis(dv0, "astraYarrick") or [None])[0]
        if att_u is None or jak_u is None:
            print(f"[67] {tag}: roster KO")
            return 2
        att, jak = att_u["id"], jak_u["id"]
        my_team = att_u.get("team")
        mine = 3 if my_team == 1 else 4
        norm = _normal_id(dv0, att)
        print(f"[67] {tag}: runner={rid} att=u{att} (normale={norm}) yarrick=u{jak} "
              f"hp-target={hp_target}")
        # marche vers le yarrick (inerte : tours ennemis sautes) jusqu'a portee 2, puis tour
        # FRAIS avant l'attaque (activation pleine — cf. _fresh_my_turn)
        for _ in range(8):
            dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1}, 60)
            a_u = next((u for u in _alive(dv) if u.get("id") == att), None)
            j_u = next((u for u in _alive(dv) if u.get("id") == jak), None)
            if a_u is None or j_u is None:
                print(f"[67] {tag}: unite disparue avant contact")
                return 3
            d = hexgeo.distance(_pos(a_u), _pos(j_u))
            if d <= 2:
                break
            occ = {_pos(u) for u in _alive(dv)}
            _move_toward(rpc, rid, att, _pos(a_u), _pos(j_u), occ, 3, 2)
            if not _fresh_my_turn(rpc, rid, mine):
                print(f"[67] {tag}: flip retour impossible")
                return 3
        else:
            print(f"[67] {tag}: jamais a portee -> ECHEC montage")
            return 3
        if expect_dead:
            if not _fresh_my_turn(rpc, rid, mine):
                print(f"[67] {tag}: flip pre-attaque impossible")
                return 3
            out = replay_attack(rpc, rid, att, jak, norm)
            if out is None:
                return 3
            rr = out["rr"] or {}
            live_hits = out.get("live_hits") or []
            live_an = out.get("live_after_normal")
            seq_ok = live_hits == _effective_seq(rr.get("per_hit"), out["hp_before"])
            print(f"[67] {tag}: offline rolls={rr.get('rolls')} per_hit={rr.get('per_hit')} | "
                  f"live per-coup {live_hits} : {out['hp_before']} -> {live_an} | "
                  f"offline -> {out['off_after']}")
            okc = live_an == 0 and out["off_after"] == 0 and seq_ok
            print(f"[67] {tag}: overkill (porte IsOverkill ouverte, cap bypasse) "
                  f"{'OK' if okc else 'ECHEC'} (seq: {seq_ok})")
            return 0 if okc else 1
        # RESILIENT a hp NATIF (--hp-target fausse les bornes de roll — artefact harnais, vu
        # 67081/67091 vs 67093 bit-exact) : attaques repetees, chaque tour = un replay-diff
        # FRAIS (load_state + dumpRng re-synchronisent, y compris apres le feu FoA hors-replay).
        # Le tour LETAL doit laisser la cible a EXACTEMENT 1 PV (cap Resilient rem-1, porte
        # overkill fermee : accum = (maxHp - hp_debut) + bruts < 2x maxHp).
        turns_ok, cap_seen = [], False
        for turn in range(14):
            if not _fresh_my_turn(rpc, rid, mine):
                print(f"[67] {tag}: flip pre-attaque impossible (tour {turn})")
                return 3
            out = replay_attack(rpc, rid, att, jak, norm)
            if out is None:
                return 3
            rr = out["rr"] or {}
            live_hits = out.get("live_hits") or []
            live_an = out.get("live_after_normal")
            seq_ok = live_hits == _effective_seq(rr.get("per_hit"), out["hp_before"])
            hp_ok = out["off_after"] == live_an
            turns_ok.append(seq_ok and hp_ok)
            rem = int(out["hp_before"] or 0)      # preuve du cap : un coup LIVE == rem-1 (rem>1)
            for a in live_hits:
                if rem > 1 and a == rem - 1:
                    cap_seen = True
                rem -= a
            print(f"[67] {tag}: tour {turn}: live {live_hits} {out['hp_before']}->{live_an} | "
                  f"off per_hit={rr.get('per_hit')} ->{out['off_after']} | "
                  f"seq={seq_ok} hp={hp_ok}")
            if live_an is not None and live_an <= 1:
                # Deux issues natives legitimes, l'offline doit COLLER dans les deux :
                #  - tenu a EXACTEMENT 1 PV (porte overkill fermee au coup letal, ex. 67111) ;
                #  - TUE si la porte s'ouvre (hp_depart bas : accum >= 2x hp_depart, ex. 67201 —
                #    c'est le datapoint qui a discrimine param_11 = hp_depart, pas hpMax).
                # Exigences : chaque tour off==live (seq+hp), ET le cap rem-1 VU au moins une fois.
                okc = (out["off_after"] == live_an and all(turns_ok)
                       and len(turns_ok) >= 2 and cap_seen)
                print(f"[67] {tag}: Resilient (cap rem-1 + porte overkill) "
                      f"{'OK' if okc else 'ECHEC'} (final live {live_an} / off "
                      f"{out['off_after']} ; tours concordants {sum(turns_ok)}/{len(turns_ok)}, "
                      f"cap vu: {cap_seen})")
                return 0 if okc else 1
        print(f"[67] {tag}: cible jamais descendue a <=1 PV en 14 tours -> ECHEC montage")
        return 3
    finally:
        try:
            _r(sid, "disposeRunner", {"runnerId": rid}, 15)
            print(f"[67] {tag}: runner {rid} dispose")
        except Exception as e:
            print(f"[67] {tag}: dispose KO: {e}")
        state_file.unlink(missing_ok=True)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", default="all",
                    choices=("all", "swarm", "blast", "resilient", "overkill"))
    ap.add_argument("--seed", type=int, default=67001)
    ap.add_argument("--hp-resilient", type=int, default=3000)
    ap.add_argument("--hp-overkill", type=int, default=300)
    args = ap.parse_args(argv)
    sid = _resolve_session()
    results = {}
    if args.scenario in ("all", "swarm"):
        results["swarm"] = scenario_swarm(sid, args.seed, "adeptRetributor", False)
    if args.scenario in ("all", "blast"):
        results["blast"] = scenario_swarm(sid, args.seed + 1, "astraOrdnance", True)
    if args.scenario in ("all", "resilient"):
        results["resilient"] = scenario_resilient(sid, args.seed + 2, args.hp_resilient, False)
    if args.scenario in ("all", "overkill"):
        results["overkill"] = scenario_resilient(sid, args.seed + 3, args.hp_overkill, True)
    print(f"[67] VERDICTS: {results} (0=OK 1=ECHEC 2=build-KO 3=montage-KO)")
    return max(results.values()) if results else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
