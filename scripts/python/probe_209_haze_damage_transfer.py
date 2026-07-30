"""case-209 -- la CHARGE UTILE du bond 0x435 = 1077 `HazeOfCorruption_DamageTransfer`.

QUESTION (binaire) : quand la cible d'un `deathBlightlord` MEURT sous le coup, quel degat exact le
RELAIS (l'unite bondee par le target-finder de case-207) encaisse-t-il ?

Le volet RNG (`HazeOfCorruption_TargetFinderAbility`) est deja porte et bit-exact (case-207) : ce
probe ne le remesure pas. Il exerce la branche que case-207 n'a JAMAIS atteinte -- aucun de ses
montages ne faisait mourir la cible (`--hp-target 90000`).

ARTEFACT NATIF vise (decompile, build `gqfc5mff6c`) :

    IdunBattle.Entities.Effects.Loki.HazeOfCorruption_DamageTransferEffect$$CreateTargetTrigger
        ( OnDeath(1,1) & ( TriggeringAbilityIs(0x435) | AreEqual(Actor@0x158, bonded) )
          | On(0x2d = UnitRevived) | On(0x35 = UnitFled) )
        & IsAlive(bonded) & AreEqual(Target@0x178, EffectSource(Effect@0x150))

    …$$CreateTargetTriggerBehaviour
        dmgs = GetLeftOverDamages(entities)
        beh  = Nothing() + GetRemoveEffectBehaviour()
        foreach d in dmgs:
            beh += AttackDamage(bonded, Owner@0x148, Get(d.amount), Direct(d.type),
                                One@0xc0, AbilityOrEffect(0x435), <defaut>)
        return Attack(bonded, Owner@0x148, beh, <defaut>)

MONTAGE (reutilise la geometrie CRAFTEE de `probe_207_haze_pool_ladder.py`, k = 1) :
    C = deathBlightlord ; T = astraBullgryn (aucun trigger, aucun summon -> UNE seule emission
    de `On(0x2b)`) ; R = astraDreir place sur un voisin COMMUN de C et T -> pool = {R}, un bond.
    `--hp-target` BAS -> T meurt sous le coup -> la branche transfert TIRE.

TEMOIN que la branche a tire (exige AVANT toute comparaison de nombres) : un evenement de degat
dont la cible est R et qui suit la mort de T, plus la disparition du bond 1077 (RemoveEffect).

CLI (depuis scripts/python) :
  python probe_209_haze_damage_transfer.py --seeds 777 --hp 1200
  python probe_209_haze_damage_transfer.py --seeds 777,88 --hp 1200,400 --dump-events

Discipline runner : state-file ABSOLU sous logs/, board explicite, dispose en fin. ASCII only.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

from probe_r6_round_materialize import _mkrpc, PYDIR, ROOT, BOARD
from probe_159_ah_bounds import _board, _genrand_steps, _pos, _unit
from probe_dpw_weapon_cell import _replay_recording, _raw_stream
from probe_207_haze_pool_ladder import CARRIER, TARGET, EXTRAS, _drive_pool


def _build(seed, hp, armor):
    sf = ROOT / "logs" / "runners" / f"p209-{uuid.uuid4().hex[:8]}.json"
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


def _hp_map(dv, snap):
    """id -> (visualId, PV courants, PV max, vivant) -- PV lus dans `combatSnapshot` (les stats
    d'unite), l'etat vivant dans `decisionView` (qui GARDE les cadavres)."""
    st = {}
    for u in (snap.get("units") or []):
        s = u.get("stats") or {}
        st[u.get("entityId")] = (s.get("health"), s.get("remainingHealth"), s.get("fixedArmor"))
    out = {}
    for u in (dv.get("units") or []):
        p = u.get("pos") or {}
        h = st.get(u.get("id")) or (None, None, None)
        out[u.get("id")] = {"vis": u.get("visualId"), "pos": [p.get("col"), p.get("row")],
                            "alive": u.get("alive"), "hp": h[1], "hp_max": h[0], "armor": h[2],
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


def _run(rpc, seed, hp, args):
    rid, sf = _build(seed, hp, args.armor)
    if rid is None:
        return None
    try:
        board = _board(rpc, rid)
        cid, tid, aid, err = _drive_pool(rpc, rid, board, args.k)
        if cid is None:
            print("[209] seed %s hp=%s : drive KO -- %s" % (seed, hp, err))
            return None
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        ob = rpc("observeBattle", {"runnerId": rid}, 60)
        snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
        before = _hp_map(dv, snap)
        rng0 = rpc("dumpRng", {"runnerId": rid}, 30)
        res = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": cid, "targetId": tid, "abilityType": aid},
            "captureEvents": True}, 120)
        rng1 = rpc("dumpRng", {"runnerId": rid}, 30)
        dv2 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        snap2 = rpc("combatSnapshot", {"runnerId": rid}, 90)
        after = _hp_map(dv2, snap2)
        evs = _events(res)
        relay = None
        for uid, u in before.items():
            if u["vis"] in EXTRAS and u["pos"] is not None:
                # le relais = l'extra reellement place sur un voisin commun (les autres sont exiles)
                if relay is None or (before[relay]["pos"] == [None, None]):
                    relay = uid
        # Degat d'ARME par coup, cote PORT : `_replay_recording` rejoue l'attaque sur le MEME flux
        # `rng0` (case-207 : bit-exact 4/4 seeds). `per_hit` = les d_i DEMANDES, avant tout clamp PV
        # -- c'est eux qu'on confronte aux montants transferes.
        # TRACE des deux volets case-209 pendant le rejeu : combien de fois chaque trigger est
        # EVALUE et combien de fois il FIRE. Sans cette separation, un volet muet est indiscernable
        # d'un volet non collecte.
        from engine.runner.operations.triggers.loki import haze_of_corruption as _HZ
        trace = {"bonus_match": 0, "bonus_fire": 0, "xfer_match": 0, "xfer_fire": 0}
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
                    return _oe(self, st, ev)
                c.matches, c.execute_behaviour = m, x
            _mk(key, cls, *_orig[key])
        try:
            off = _replay_recording(dv, ob, snap, board, rng0, cid, tid, 0)
        finally:
            for key, cls in (("bonus", _HZ.HazeCorruptionBonusHitAbility),
                             ("xfer", _HZ.HazeOfCorruptionDamageTransferTrigger)):
                cls.matches, cls.execute_behaviour = _orig[key]
        # `extraDmg[passive_level]` de `HazeOfCorruption` : ce que `GetVariableForLevel(config, 8)`
        # rend a `HazeCorruption_BonusHitAbility$$CreateBehaviour`. Sert a confronter le montant du
        # coup BONUS (profil Toxic) a sa source config, sans le deduire du montant transfere.
        import gameconfig as GC
        cu = next((u for u in (dv.get("units") or []) if u.get("id") == cid), None) or {}
        lvl = cu.get("passiveAbilityLevel") or cu.get("passive_ability_level")
        var = ((GC.ability("HazeOfCorruption") or {}).get("variables") or {}).get("extraDmg") or []
        extra = var[lvl - 1] if (isinstance(lvl, int) and 1 <= lvl <= len(var)) else None
        return {"seed": seed, "hp": hp, "rid": rid, "cid": cid, "tid": tid, "relay": relay,
                "passive_level": lvl, "extra_dmg": extra, "caster_keys": sorted(cu.keys()),
                "n_native": _genrand_steps(rng0, rng1), "n_off": off["n_genrand"],
                "per_hit": list(off["per_hit"]), "cell": off["cell"],
                "off_entities": list(off.get("entities") or []), "trace": dict(trace),
                "raw": _raw_stream(rng0, 10),
                "before": before, "after": after, "events": evs}
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 20)
        except Exception:
            pass
        try:
            sf.unlink()
        except Exception:
            pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="777")
    ap.add_argument("--hp", default="1200")
    ap.add_argument("--armor", type=int, default=0)
    ap.add_argument("--k", type=int, default=1)
    ap.add_argument("--dump-events", action="store_true")
    args = ap.parse_args()
    rpc = _mkrpc()
    rows = []
    for seed in [s for s in args.seeds.split(",") if s.strip()]:
        for hp in [int(h) for h in str(args.hp).split(",") if h.strip()]:
            r = _run(rpc, seed, hp, args)
            if r is None:
                continue
            rows.append(r)
            print("[209] seed %s hp=%d : caster=%s cible=%s relais=%s  genrand natif=%s"
                  % (seed, hp, r["cid"], r["tid"], r["relay"], r["n_native"]))
            for uid in (r["cid"], r["tid"], r["relay"]):
                if uid is None:
                    continue
                b, a = r["before"].get(uid) or {}, r["after"].get(uid) or {}
                print("      id=%-4s %-16s pos=%s -> %s  hp %s -> %s  alive %s -> %s  eff %s -> %s"
                      % (uid, b.get("vis"), b.get("pos"), a.get("pos"), b.get("hp"), a.get("hp"),
                         b.get("alive"), a.get("alive"), b.get("eff"), a.get("eff")))
            dmg = [(td["tags"].get("Damage_Target_Id") or td["tags"].get("Unit_Id")
                    or td["tags"].get("Target_Id"), int(td["tags"]["Amount"]),
                    td["tags"].get("Effect_Type"), td["tags"].get("Ability_Type"))
                   for td in r["events"] if "Amount" in td["tags"]]
            print("      degats (cible, montant, effectType, abilityType) = %s" % json.dumps(dmg))
            print("      arme PORT per_hit = %s  cellule = %s  (port %s genrand)"
                  % (r["per_hit"], r["cell"], r["n_off"]))
            # Chaque `raw[i]` RESOLU dans la cellule d'arme : dit QUEL tirage du flux produit un
            # montant donne -> separe « le port se trompe de valeur » de « le port se trompe de
            # RANG dans le flux » (decomposition par etage, jamais un scalaire fitte).
            from probe_dpw_weapon_cell import resolve as _rs
            lo, hi = r["cell"]
            print("      raw resolus dans la cellule = %s"
                  % [(_i, _rs(lo, hi, _g)) for _i, _g in enumerate(r["raw"])])
            # CONFRONTATION : PV finaux + `LeftOverDamage` cote PORT vs les degats LIVE.
            for e in r["off_entities"]:
                if e.get("id") in (r["tid"], r["relay"]):
                    print("      PORT id=%-4s %-16s hp=%-6s alive=%-5s leftOver=%s"
                          % (e.get("id"), e.get("vis"), e.get("hp"), e.get("alive"),
                             json.dumps(e.get("left_over"))))
            live_relay = sum(m for (t, m, _e, _a) in dmg if t == r["relay"])
            port_relay = None
            for e in r["off_entities"]:
                if e.get("id") == r["relay"] and e.get("hp") is not None:
                    # PV de depart = `--hp-target` (force sur toutes les a-units par `rl_duel build`).
                    port_relay = int(hp) - int(e["hp"])
            print("      RELAIS degat LIVE=%s  PORT=%s   trace=%s"
                  % (live_relay, port_relay, json.dumps(r["trace"])))
            names = {}
            for e in r["events"]:
                names[e["name"]] = names.get(e["name"], 0) + 1
            print("      events = %s" % json.dumps(names))
            if args.dump_events:
                for e in r["events"]:
                    print("        %-32s %s" % (e["name"], json.dumps(e["tags"])[:420]))
    return 0 if rows else 1


if __name__ == "__main__":
    sys.exit(main())
