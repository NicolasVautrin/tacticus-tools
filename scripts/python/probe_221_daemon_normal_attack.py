"""GENERALISATION #221 : le jet de block `Daemon_ExtraBlock` (1034) sur le vecteur ATTAQUE NORMALE.

Le gap avait ete chiffre sur le vecteur ABILITY (`probe_brazier_daemon_offset.py`, BrazierOfHolyFire).
L'etage corrige est PARTAGE (`AttackDamageOperation._block_sources`, appele par `execute` /
`execute_ability_attack` / `execute_normal_like`) -- ce probe verifie l'AUTRE face : une attaque
NORMALE multi-coups contre une cible Daemon consomme-t-elle la meme suite de tirages que le natif ?

Chaine native : `IdunBattle.Operations.AttackDamageOperation$$ExecuteHit` -> sub-op 0x42 ->
`IdunBattle.Core.Services.DamagePrediction$$CalculateDamageOperation` -> (slot 0)
`IdunBattle.Core.Services.DamageCalculations$$CalculateBlockChances` (= `GetMultiValueStat(7)` =
entree PAR DEFAUT `{entityId 0, GetStat(7)}` + entrees par-entite) -> (slot 2)
`IdunBattle.Core.Services.DamageCalculations$$ApplyRandomBlockDamage` (1 `NextBool(chance)` par source
tentee, arret a la 1re reussite, `AddFailedBlockId(entityId)` sinon).

Trois series rejouees sur le MEME etat rng capture avant l'attaque :
  * PORT           -> doit matcher le live per-coup, bit-exact ;
  * LEGACY         -> `DaemonExtraBlockEffect` neutralise (l'etat d'AVANT #221) : montre le decalage ;
  * LEGACY k=1..2  -> combien de tirages manquaient.

Usage : python probe_221_daemon_normal_attack.py [--attacker necroDestroyer]
                   [--target blackObliterator] [--seed 777] [--board MC1_67]
ASCII only.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from collections import deque
from pathlib import Path

import rl_collect_batch as R
from engine.entities.effects.loki.hits import DaemonExtraBlockEffect
from engine.entities.pathfinding.board import Board
from engine.runner.messages import AttackUnitMessage
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.runner import Runner
from engine.runner.snapshot import load_state

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]


def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def _cr(u):
    p = (u or {}).get("pos") or {}
    return (p.get("col"), p.get("row")) if p.get("col") is not None else None


def _find(units, vis):
    return next((u for u in (units or []) if u.get("visualId") == vis and u.get("alive")), None)


def _rng(s):
    r = IntBasedMersenneTwister()
    r.mt = list(s["mt"])
    r.mti = s["mti"]
    return r


def _offline_per_hit(dv, ob, snap, bd, att, tgt, s0, pre_draws=0):
    """Rejoue l'attaque NORMALE offline depuis l'etat rng `s0`, en pre-consommant `pre_draws`."""
    st = load_state(dv, ob, snap, board=bd)
    st.rng = _rng(s0)
    for _ in range(pre_draws):
        st.rng.next_internal(0, 100)
    runner = Runner(st).install_default_handlers(20)
    runner.apply(AttackUnitMessage(att, tgt))
    last = runner.damage_handler.last or {}
    return (last.get("attack") or last).get("per_hit") or []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--attacker", default="necroDestroyer")
    ap.add_argument("--target", default="blackObliterator")
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    a = ap.parse_args()
    sid = R._resolve_session()

    def rpc(m, b=None, t=90):
        return _unwrap(R._rpc(sid, m, [b] if b is not None else [], timeout=t))

    sf = ROOT / "logs" / "runners" / f"d221norm-{uuid.uuid4().hex[:8]}.json"
    sf.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, "rl_duel.py", "build", "--seed", a.seed, "--state-file", str(sf),
                    "--board", a.board, "--roster", "1", "--p-units", a.attacker,
                    "--a-units", a.target], cwd=str(PYDIR), capture_output=True, text=True)
    if not sf.exists():
        print("BUILD KO")
        return 1
    rid = int(json.loads(sf.read_text())["runnerId"])
    try:
        bd = Board(rpc("boardGraph", {"runnerId": rid}, 60)["tiles"], adjacency="native_sym")

        def bfs(src):
            dist, q = {src: 0}, deque([src])
            while q:
                x = q.popleft()
                for n in bd.neighbours(x):
                    if n not in dist and (n == src or bd.walkable(n)):
                        dist[n] = dist[x] + 1
                        q.append(n)
            return dist

        # APPROCHE : on DEPLACE l'attaquant jusqu'au contact de la cible (jamais « bloque par la
        # geometrie de spawn ») -- la configuration testee doit etre atteinte, pas subie.
        my, cid, tid, norm = None, None, None, None
        for _ in range(30):
            dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
            att_u, tgt_u = _find(dv["units"], a.attacker), _find(dv["units"], a.target)
            if att_u is None or tgt_u is None:
                print("UNITE ABSENTE")
                return 1
            my = my if my is not None else att_u.get("owner")
            if dv.get("currentPlayer") != my:
                rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
                continue
            cid, tid = att_u["id"], tgt_u["id"]
            norm = next((ab for ab in (att_u.get("abilities") or [])
                         if ab.get("kind") == "normal"), None)
            at = rpc("abilityTargets", {"runnerId": rid, "unitId": cid,
                                        "abilityType": (norm or {}).get("id")}, 90)
            ab = next((x for x in ((at.get("units") or [{}])[0].get("abilities") or [])
                       if x.get("abilityId") == (norm or {}).get("id")), {})
            if tid in [x.get("targetId") for x in (ab.get("fromHere") or [])]:
                break
            dist = bfs(bd.id_at(*_cr(tgt_u)))
            mt = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
            cmt = next((x for x in (mt.get("units") or []) if x.get("unitId") == cid), None)
            reach = {bd.id_at(t["col"], t["row"]): (t["col"], t["row"])
                     for t in ((cmt or {}).get("tiles") or [])}
            pool = [t for t in reach if t in dist and dist[t] >= 1]
            if not pool:
                rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
                continue
            c, r = reach[min(pool, key=lambda t: dist[t])]
            rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": cid, "to": {"col": c, "row": r}}}, 60)
        else:
            print("APPROACH KO")
            return 1

        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        ob = rpc("observeBattle", {"runnerId": rid}, 60)
        snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
        s0 = rpc("dumpRng", {"runnerId": rid}, 30)
        tgt_u = next(u for u in dv["units"] if u["id"] == tid)
        print("attaquant %s u%s -> cible %s u%s (hp %s)"
              % (a.attacker, cid, a.target, tid, tgt_u.get("hp")))

        res = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": cid, "targetId": tid,
            "abilityType": norm["id"]}, "captureEvents": True}, 150)
        live = []
        for act in (res.get("actions") or []):
            for e in (act.get("events") or []):
                td = e.get("tags")
                td = json.loads(td) if isinstance(td, str) else (td or {})
                if "Amount" in td and td.get("Target_Id") == tid \
                        and td.get("Active_Ability_Type") == norm["id"]:
                    live.append(td["Amount"])
        print("LIVE per_hit:", live)
        if not live:
            print("AUCUN EVENT DE DEGAT -- scenario non discriminant")
            return 1

        off = _offline_per_hit(dv, ob, snap, bd, cid, tid, s0)
        print("PORT   per_hit: %s%s" % (off, "  <== MATCH" if off == live else ""))

        _orig = DaemonExtraBlockEffect.create_effect_block_source_for_defense
        DaemonExtraBlockEffect.create_effect_block_source_for_defense = (
            # #1015-r1 -- 3e substrat (`defender_max_health`) ajoute au hook. RECOPIE, pas `**_` :
        # ce stub est dans un PROBE, que la banque ne joue pas -- l'incompatibilite de signature y
        # serait restee silencieuse jusqu'au prochain run manuel.
        lambda self, defender_fixed_armor=0, defender_attack=0, defender_max_health=0: None)
        try:
            for k in range(0, 3):
                lg = _offline_per_hit(dv, ob, snap, bd, cid, tid, s0, pre_draws=k)
                print("LEGACY k=%d per_hit: %s%s" % (k, lg, "  <== MATCH" if lg == live else ""))
        finally:
            DaemonExtraBlockEffect.create_effect_block_source_for_defense = _orig
        return 0
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 20)
        except Exception:
            pass
        sf.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
