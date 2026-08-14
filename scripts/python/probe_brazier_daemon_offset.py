"""#221 -- Localise l'ETAGE d'une desync BrazierOfHolyFire (1041) vs cible DAEMON : combien de tirages
`state.rng` separent la sequence PORT de la sequence LIVE, et OU.

Methode : depuis l'etat rng capture AVANT le cast live, on rejoue l'attaque offline en PRE-CONSOMMANT
k tirages (k = 0..6) et on cherche le k pour lequel les coups du port collent au live. Un k > 0 qui
recolle designe « le natif tire k fois de plus (ou de moins) » -- on remonte ensuite a l'etage.

Depuis #221 le PORT matche a k=0 (le jet de block de `Daemon_ExtraBlock` est roule). La serie
`[legacy sans Attack]` rejoue, sur les MEMES donnees et le MEME etat rng, le comportement d'AVANT
(`DaemonExtraBlockEffect` neutralise) : elle chiffre l'ecart dans un seul run et garde le probe
discriminant. ASCII only.

Usage : python probe_brazier_daemon_offset.py [--target blackObliterator]
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
from engine.runner.snapshot import load_state
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.abilities.base import ability_attack_params, ability_pierce_effect_bonus
from engine.runner.operations.damage import AttackDamageOperation

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
ABILITY = 1041


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", default="blackObliterator")
    ap.add_argument("--seed", default="777")
    a = ap.parse_args()
    sid = R._resolve_session()

    def rpc(m, b=None, t=90):
        return _unwrap(R._rpc(sid, m, [b] if b is not None else [], timeout=t))

    sf = ROOT / "logs" / "runners" / f"offset-{uuid.uuid4().hex[:8]}.json"
    sf.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, "rl_duel.py", "build", "--seed", a.seed, "--state-file", str(sf),
                    "--board", "MC1_67", "--roster", "1", "--p-units", "adeptCanoness",
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

        my, cid, tid = None, None, None
        for _ in range(25):
            dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
            caster, tgt = _find(dv["units"], "adeptCanoness"), _find(dv["units"], a.target)
            my = my if my is not None else caster.get("owner")
            if dv.get("currentPlayer") != my:
                rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
                continue
            cid = caster["id"]
            at = rpc("abilityTargets", {"runnerId": rid, "unitId": cid, "abilityType": ABILITY}, 90)
            ab = next((x for x in ((at.get("units") or [{}])[0].get("abilities") or [])
                       if x.get("abilityId") == ABILITY), {})
            if tgt["id"] in [x.get("targetId") for x in (ab.get("fromHere") or [])]:
                tid = tgt["id"]
                break
            dist = bfs(bd.id_at(*_cr(tgt)))
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
        if tid is None:
            print("APPROACH KO")
            return 1

        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        ob = rpc("observeBattle", {"runnerId": rid}, 60)
        snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
        s0 = rpc("dumpRng", {"runnerId": rid}, 30)
        tgt_u = next(u for u in dv["units"] if u["id"] == tid)
        print("cible %s traits=%s hp=%s" % (tid, tgt_u.get("visualId"), tgt_u.get("hp")))

        res = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": cid, "targetId": tid, "abilityType": ABILITY},
            "captureEvents": True}, 150)
        live = []
        for act in (res.get("actions") or []):
            for e in (act.get("events") or []):
                td = e.get("tags")
                td = json.loads(td) if isinstance(td, str) else (td or {})
                if "Amount" in td and td.get("Active_Ability_Type") == ABILITY \
                        and td.get("Target_Id") == tid:
                    live.append(td["Amount"])
        print("LIVE per_hit:", live)

        st0 = load_state(dv, ob, snap, board=bd)
        bmin, bmax, pierce, _h = ability_attack_params(st0, cid, "BrazierOfHolyFire", "Flame",
                                                       ranged=True)
        pb = ability_pierce_effect_bonus(st0, cid, tid, ABILITY, is_ranged=True)
        _, _, pierce_eff, _ = ability_attack_params(st0, cid, "BrazierOfHolyFire", "Flame",
                                                    ranged=True, pierce_effect_bonus=pb)
        print("bornes [%d,%d] pierce=%d (avec effect_bonus=%d)" % (bmin, bmax, pierce, pierce_eff))

        for k in range(0, 7):
            st = load_state(dv, ob, snap, board=bd)
            st.rng = _rng(s0)
            for _ in range(k):
                st.rng.next_internal(0, 100)                 # tirages « poubelle » pre-consommes
            atk = AttackDamageOperation.execute_ability_attack(
                st, cid, tid, bmin, bmax, pierce_eff, len(live) or 4, damage_profile="Flame",
                is_melee=False, ability_type=ABILITY, is_attack_damage_op=True)
            ph = (atk or {}).get("per_hit") or []
            tag = "  <== MATCH" if ph == live else ""
            print("k=%d off=%s%s" % (k, ph, tag))
        # variante LEGACY (#221) : `_block_sources` SANS l'Attack du defenseur -> la source
        # `Daemon_ExtraBlock` disparait et le port saute le jet de block. Rejoue ICI, sur les MEMES
        # donnees et le MEME etat rng, pour chiffrer l'ecart avant/apres dans un seul run.
        _orig = DaemonExtraBlockEffect.create_effect_block_source_for_defense
        DaemonExtraBlockEffect.create_effect_block_source_for_defense = (
            # #1015-r1 -- 3e substrat (`defender_max_health`) ajoute au hook ; meme raison qu'en
        # `probe_221` : un probe n'est pas joue par la banque, donc la faute y dormirait.
        lambda self, defender_fixed_armor=0, defender_attack=0, defender_max_health=0: None)
        try:
            for k in range(0, 3):
                st = load_state(dv, ob, snap, board=bd)
                st.rng = _rng(s0)
                for _ in range(k):
                    st.rng.next_internal(0, 100)
                atk = AttackDamageOperation.execute_ability_attack(
                    st, cid, tid, bmin, bmax, pierce_eff, len(live) or 4, damage_profile="Flame",
                    is_melee=False, ability_type=ABILITY, is_attack_damage_op=True)
                ph = (atk or {}).get("per_hit") or []
                tag = "  <== MATCH" if ph == live else ""
                print("[legacy sans Attack] k=%d off=%s%s" % (k, ph, tag))
        finally:
            DaemonExtraBlockEffect.create_effect_block_source_for_defense = _orig
        # variante FAMILLE "ability" (1 tirage/coup) pour trancher la classification de factory
        for k in range(0, 3):
            st = load_state(dv, ob, snap, board=bd)
            st.rng = _rng(s0)
            for _ in range(k):
                st.rng.next_internal(0, 100)
            atk = AttackDamageOperation.execute_ability_attack(
                st, cid, tid, bmin, bmax, pierce_eff, len(live) or 4, damage_profile="Flame",
                is_melee=False, ability_type=ABILITY, is_attack_damage_op=False)
            ph = (atk or {}).get("per_hit") or []
            tag = "  <== MATCH" if ph == live else ""
            print("[ability] k=%d off=%s%s" % (k, ph, tag))
        return 0
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 20)
        except Exception:
            pass
        sf.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
