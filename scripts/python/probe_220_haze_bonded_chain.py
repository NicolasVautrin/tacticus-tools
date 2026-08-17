"""case-haze-bonded -- l'ENTITE BONDEE de `HazeOfCorruption_DamageTransfer` (1077), exercee sur la CHAINE
A DEUX RELAIS (`k = 2`).

QUESTION (binaire) : le predicat de report compare-t-il l'entite REELLEMENT bondee -- celle que le
5e argument d'`IdunBattleLogic.Entities.DSLBehaviors$$AddBondEffect` transmet et que
`IdunBattle.Entities.Behaviours.AddEffectBehaviour$$DefaultBondEffectBuilder` ecrit dans le composant
de bond de l'entite-effet (`+0x10`, relu par `IdunBattle.Entities.Effects.ABondEffect$$BondedEntityId`)
-- et le verdict tient-il quand le PREMIER relais MEURT du report ?

ARTEFACTS NATIFS (decompile, build `gqfc5mff6c`) :

    IdunBattleLogic.Entities.Abilities.Active.Loki.HazeOfCorruption_TargetFinderAbility$$CreateBehaviour
        if Count(units) > 0 : AddBondEffect(0x435, absRef, Target@0x178,  Get(units,0), Self@0x148, One)
        if Count(units) > 1 : AddBondEffect(0x435, absRef, Get(units,0),  Get(units,1), Self@0x148, One)
      -> les DEUX bonds portent le MEME `bondedEntity` (`Self@0x148` = Maladus) ; seule la SOURCE change.

    IdunBattle.Entities.Effects.Loki.HazeOfCorruption_DamageTransferEffect$$CreateTargetTrigger
        ( OnDeath(1,1) & ( TriggeringAbilityIs(0x435) | AreEqual(Actor@0x158, bonded) )
          | On(0x2d = UnitRevived) | On(0x34 = UnitFled) ) & IsAlive(bonded) & AreEqual(Target@0x178, EffectSource(Effect@0x150))
    IdunBattle.Entities.Effects.Loki.HazeOfCorruption_DamageTransferEffect$$CreateTargetTriggerBehaviour
        Attack(bonded, Owner@0x148, RemoveEffect + N x AttackDamage(bonded, Owner@0x148, ...))

MONTAGE (`_drive_pool` de `probe_207_haze_pool_ladder.py`, k = 2) :
    C = deathBlightlord ; T = astraBullgryn (aucun trigger, aucun summon) ; R1, R2 = les DEUX voisins
    COMMUNS de C et T. `--hp-target` BAS -> T meurt du coup d'arme, R1 meurt du REPORT, et c'est la
    chaine (bond 2 : source = R1, cible = R2) qui doit partir. C'est le SEUL regime live ou le
    predicat `AreEqual(Actor, bonded)` est exerce autrement que par coincidence.

TEMOINS exiges AVANT toute comparaison de nombres :
    * DEUX bonds 1077 dans le flux d'evenements natif (`Effect_SourceTriggeredAbility == 1076`),
      de `Effect_SourceId` DIFFERENTS (T puis R1) et de `BondEffect_BondedId` IDENTIQUE (= C) ;
    * R1 mort, et un evenement de degat dont la cible est R2.

CLI (depuis scripts/python) :
  python probe_220_haze_bonded_chain.py --seeds 777 --hp 1200
  python probe_220_haze_bonded_chain.py --seeds 777,88 --hp 1200,400 --dump-events

Discipline runner : state-file ABSOLU sous logs/, board explicite, dispose en fin. ASCII only.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid

from probe_r6_round_materialize import _mkrpc, PYDIR, ROOT, BOARD
from probe_159_ah_bounds import _board, _genrand_steps, _pos, _unit
from probe_dpw_weapon_cell import _replay_recording, _raw_stream
from probe_207_haze_pool_ladder import CARRIER, TARGET, EXTRAS, _drive_pool


def _build(seed, hp, armor):
    sf = ROOT / "logs" / "runners" / f"p220-{uuid.uuid4().hex[:8]}.json"
    sf.parent.mkdir(parents=True, exist_ok=True)
    args = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--state-file", str(sf),
            "--board", BOARD, "--roster", "1", "--p-units", CARRIER,
            "--a-units", ",".join([TARGET] + EXTRAS),
            "--crit", "0,0", "--block-target", "0,0",
            "--hp-target", str(hp), "--armor-target", str(armor)]
    proc = subprocess.run(args, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not sf.exists():
        print("BUILD KO:", (proc.stderr or proc.stdout or "")[-500:])
        return None, None
    return int(json.loads(sf.read_text())["runnerId"]), sf


def _units_map(dv, snap):
    """id -> {vis, pos, alive, hp} -- PV dans `combatSnapshot`, etat vivant dans `decisionView`
    (qui GARDE les cadavres, cf. `decisionView keeps dead units`)."""
    st = {}
    for u in (snap.get("units") or []):
        s = u.get("stats") or u
        uid = u.get("entityId")
        if uid is None:
            uid = u.get("id") or u.get("unitId")
        st[uid] = (s.get("health") or s.get("maxHealth"),
                   s.get("remainingHealth") if s.get("remainingHealth") is not None
                   else s.get("currentHealth"))
    out = {}
    for u in (dv.get("units") or []):
        p = u.get("pos") or {}
        h = st.get(u.get("id")) or (None, None)
        out[u.get("id")] = {"vis": u.get("visualId"), "pos": [p.get("col"), p.get("row")],
                            "alive": u.get("alive"), "hp": h[1], "hp_max": h[0],
                            "eff": [e.get("effectType") for e in (u.get("effects") or ())]}
    return out


def _events(res):
    evs = []
    for act in (res.get("actions") or []):
        for ev in (act.get("events") or []):
            td = ev.get("tags")
            td = json.loads(td) if isinstance(td, str) else (td or {})
            evs.append({"name": ev.get("name") or ev.get("type") or ev.get("eventType"),
                        "tags": td})
    return evs


def _dmg_rows(evs):
    """(cible, montant, effectType, abilityType, passive) des evenements de degat, DANS L'ORDRE."""
    out = []
    for e in evs:
        t = e["tags"]
        if "Amount" not in t:
            continue
        out.append((t.get("Damage_Target_Id") or t.get("Unit_Id") or t.get("Target_Id"),
                    int(t["Amount"]), t.get("Effect_Type"), t.get("Ability_Type"),
                    t.get("Passive_Ability_Type")))
    return out


def _bond_rows(evs):
    """Les poses de bond 1077 du flux natif : (Effect_Id, source, bonded, remaining)."""
    out = []
    for e in evs:
        t = e["tags"]
        if t.get("Effect_SourceTriggeredAbility") != 1076:
            continue
        out.append((t.get("Effect_Id"), t.get("Effect_SourceId"), t.get("BondEffect_BondedId"),
                    t.get("Effect_RemainingTurns")))
    return out


def _replay_traced(dv, ob, snap, board, rng0, cid, tid, legacy=False):
    """Rejoue l'attaque OFFLINE en TRACANT (a) chaque pose d'effet avec son `bonded`, (b) chaque
    `matches`/`execute_behaviour` des deux volets Haze, avec le `bonded` retenu.

    `legacy=True` = CONTREFACTUEL sur le MEME etat fige : on remet les deux approximations d'AVANT
    case-haze-bonded -- le `bonded` INFERE (« le tueur porte `HazeOfCorruption` ») et le slot declencheur reduit
    au seul `ev.triggering_effect` (donc `None` sur le vecteur mort -> gate anti-chaine PERMISSIF).
    C'est ce qui separe « le correctif est porteur » de « le montage ne discrimine rien »."""
    from engine.runner.operations import effects as _EFF
    from engine.runner.operations.triggers.loki import haze_of_corruption as _HZ
    posted, fires = [], []
    trace = {"bonus_match": 0, "bonus_fire": 0, "xfer_match": 0, "xfer_fire": 0}
    _legacy_saved = None
    if legacy:
        _legacy_saved = (_HZ._triggering_ability_or_effect,
                         _HZ.HazeOfCorruptionDamageTransferTrigger._bonded_id)
        _HZ._triggering_ability_or_effect = (
            lambda state, ev: getattr(ev, "triggering_effect", None))

        def _legacy_bonded(self, state, inst, ev):
            if ev.killer_id is not None and self._carries_haze(state, ev.killer_id):
                return int(ev.killer_id)
            return None
        _HZ.HazeOfCorruptionDamageTransferTrigger._bonded_id = _legacy_bonded

    _orig_add = _EFF.AddEffectOperation.execute

    def _spy_add(state, source, target, effect_type, **kw):
        r = _orig_add(state, source, target, effect_type, **kw)
        posted.append({"type": int(effect_type), "source": source, "target": target,
                       "bonded": kw.get("bonded"), "placed": r is not None})
        return r

    _EFF.AddEffectOperation.execute = staticmethod(_spy_add)
    _orig = {}
    for key, cls in (("bonus", _HZ.HazeCorruptionBonusHitAbility),
                     ("xfer", _HZ.HazeOfCorruptionDamageTransferTrigger)):
        _orig[key] = (cls.matches, cls.execute_behaviour)

        def _mk(k, c, om, oe):
            def m(self, st, ev, _om=om, _k=k):
                trace[_k + "_match"] += 1
                return _om(self, st, ev)

            def x(self, st, ev, _oe=oe, _k=k):
                trace[_k + "_fire"] += 1
                r = _oe(self, st, ev)
                if r is not None:
                    fires.append({"volet": r.get("volet") or "bonus_hit", "unit": r.get("unit"),
                                  "source": r.get("source"), "bonded": r.get("bonded"),
                                  "killer": r.get("killer"), "target": r.get("target"),
                                  "transferred": r.get("transferred"), "total": r.get("total")})
                return r
            c.matches, c.execute_behaviour = m, x
        _mk(key, cls, *_orig[key])
    try:
        off = _replay_recording(dv, ob, snap, board, rng0, cid, tid, 0)
    finally:
        _EFF.AddEffectOperation.execute = staticmethod(_orig_add)
        for key, cls in (("bonus", _HZ.HazeCorruptionBonusHitAbility),
                         ("xfer", _HZ.HazeOfCorruptionDamageTransferTrigger)):
            cls.matches, cls.execute_behaviour = _orig[key]
        if _legacy_saved is not None:
            (_HZ._triggering_ability_or_effect,
             _HZ.HazeOfCorruptionDamageTransferTrigger._bonded_id) = _legacy_saved
    off["posted"] = [p for p in posted if p["type"] == _HZ.HAZE_DAMAGE_TRANSFER]
    off["fires"] = fires
    off["trace"] = dict(trace)
    return off


def _run(rpc, seed, hp, args):
    rid, sf = _build(seed, hp, args.armor)
    if rid is None:
        return None
    try:
        board = _board(rpc, rid)
        cid, tid, aid, err = _drive_pool(rpc, rid, board, args.k)
        if cid is None:
            print("[220] seed %s hp=%s : drive KO -- %s" % (seed, hp, err))
            return None
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        ob = rpc("observeBattle", {"runnerId": rid}, 60)
        snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
        before = _units_map(dv, snap)
        rng0 = rpc("dumpRng", {"runnerId": rid}, 30)
        res = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": cid, "targetId": tid, "abilityType": aid},
            "captureEvents": True}, 120)
        rng1 = rpc("dumpRng", {"runnerId": rid}, 30)
        dv2 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        snap2 = rpc("combatSnapshot", {"runnerId": rid}, 90)
        after = _units_map(dv2, snap2)
        evs = _events(res)
        # Les relais = les EXTRAS reellement places (adjacents au caster ET a la cible).
        import hexgeo
        cpos, tpos = before[cid]["pos"], before[tid]["pos"]
        relays = [uid for uid, u in before.items()
                  if u["vis"] in EXTRAS and u["pos"] and u["pos"][0] is not None
                  and hexgeo.distance(tuple(u["pos"]), tuple(cpos)) == 1
                  and hexgeo.distance(tuple(u["pos"]), tuple(tpos)) == 1]
        off = _replay_traced(dv, ob, snap, board, rng0, cid, tid)
        cf = (_replay_traced(dv, ob, snap, board, rng0, cid, tid, legacy=True)
              if getattr(args, "cf", False) else None)
        return {"seed": seed, "hp": hp, "rid": rid, "cid": cid, "tid": tid, "relays": relays,
                "cf": ({"n": cf["n_genrand"], "trace": cf["trace"],
                        "fires": cf["fires"],
                        "hp": {e["id"]: e["hp"] for e in (cf.get("entities") or [])}}
                       if cf is not None else None),
                "n_native": _genrand_steps(rng0, rng1), "n_off": off["n_genrand"],
                "per_hit": list(off["per_hit"]), "cell": off["cell"],
                "off_entities": list(off.get("entities") or []),
                "posted": off["posted"], "fires": off["fires"], "trace": off["trace"],
                "raw": _raw_stream(rng0, 10), "before": before, "after": after,
                "dmg": _dmg_rows(evs), "bonds": _bond_rows(evs), "events": evs}
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 20)
        except Exception:
            pass
        try:
            sf.unlink()
        except Exception:
            pass


def _report(r, dump_events):
    print("[220] seed %s hp=%d : caster=%s cible=%s relais=%s   genrand natif=%s port=%s"
          % (r["seed"], r["hp"], r["cid"], r["tid"], r["relays"], r["n_native"], r["n_off"]))
    print("      arme PORT per_hit = %s  cellule = %s" % (r["per_hit"], r["cell"]))
    print("      BONDS natifs (effectId, source, bonded, rem) = %s" % json.dumps(r["bonds"]))
    print("      BONDS port   (source, target, bonded, pose)  = %s"
          % json.dumps([[p["source"], p["target"], p["bonded"], p["placed"]] for p in r["posted"]]))
    print("      degats LIVE (cible, montant, effT, abilT, passif) = %s" % json.dumps(r["dmg"]))
    print("      fires PORT = %s" % json.dumps(r["fires"]))
    print("      trace PORT = %s" % json.dumps(r["trace"]))
    if r.get("cf") is not None:
        c = r["cf"]
        print("      CONTREFACTUEL (gate d'AVANT case-haze-bonded) : genrand=%s trace=%s"
              % (c["n"], json.dumps(c["trace"])))
        for uid in [r["tid"]] + r["relays"]:
            print("        cf id=%-4s hp=%s (port %s, natif dmg=%s)"
                  % (uid, c["hp"].get(uid),
                     next((e["hp"] for e in r["off_entities"] if e["id"] == uid), None),
                     sum(m for (t, m, _e, _a, _p) in r["dmg"] if t == uid)))
    port = {e["id"]: e for e in r["off_entities"]}
    ok = r["n_native"] == r["n_off"]
    for uid in [r["tid"]] + r["relays"]:
        b = r["before"].get(uid) or {}
        p = port.get(uid) or {}
        # PV de depart = `--hp-target` (force sur TOUTES les a-units par `rl_duel build`) : le
        # `combatSnapshot` d'APRES ne rend plus les PV quand la bataille s'est terminee.
        live_dmg = sum(m for (t, m, _e, _a, _p) in r["dmg"] if t == uid)
        port_dmg = (int(r["hp"]) - int(p["hp"])) if p.get("hp") is not None else None
        same = live_dmg == port_dmg
        ok = ok and same
        print("      id=%-4s %-16s LIVE dmg=%-6s | PORT hp=%-6s alive=%-5s dmg=%-6s leftOver=%s  %s"
              % (uid, b.get("vis"), live_dmg, p.get("hp"), p.get("alive"), port_dmg,
                 json.dumps(p.get("left_over")), "OK" if same else "DIVERGE"))
    if dump_events:
        for e in r["events"]:
            print("        %-32s %s" % (e["name"], json.dumps(e["tags"])[:420]))
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="777")
    ap.add_argument("--hp", default="1200")
    ap.add_argument("--armor", type=int, default=0)
    ap.add_argument("--k", type=int, default=2)
    ap.add_argument("--cf", action="store_true",
                    help="rejoue AUSSI le contrefactuel 'gate d'AVANT case-haze-bonded' sur le meme etat")
    ap.add_argument("--dump-events", action="store_true")
    args = ap.parse_args()
    rpc = _mkrpc()
    rows, oks = [], 0
    for seed in [s for s in args.seeds.split(",") if s.strip()]:
        for hp in [int(h) for h in str(args.hp).split(",") if h.strip()]:
            r = _run(rpc, seed, hp, args)
            if r is None:
                continue
            rows.append(r)
            oks += 1 if _report(r, args.dump_events) else 0
    if not rows:
        print("[220] aucun montage exploitable")
        return 1
    print()
    print("[220] BILAN %d montages : PV+vivant port==live %d/%d ; genrand port==natif %d/%d"
          % (len(rows), oks, len(rows),
             sum(1 for r in rows if r["n_native"] == r["n_off"]), len(rows)))
    return 0 if oks == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())
