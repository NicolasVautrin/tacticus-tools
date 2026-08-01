"""ARBITRAGE LIVE de l'ORDRE des tirages autour du vecteur `On(DamageDealt = 0x10)`.

QUESTION (binaire, tranchee par le MT live, pas par une valeur de degat) : quand un coup de profil
`Toxic` TUE sa cible et que la mort declenche elle-meme un tirage, le `Maybe(chance)` d'
`IdunBattleLogic.Entities.Abilities.Damage.Loki.OnToxicDamageAbility$$CreateBehaviour` tombe-t-il
AVANT ou APRES le tirage de la mort ?

  * ORDRE « BUS » (= la place NATIVE de `On(0x10)`) : `IdunBattle.Operations.ApplyDamageOperation$$
    Execute` emet `On(0x39 = PreDamageTaken)` -> `On(0xf)` -> `On(0x10)` **avant** que la mort ne soit traitee
    (`VerifyDeaths` -> `IdunBattle.Operations.KillUnitOperation$$Execute`). Le `Maybe` precede donc
    le tirage de mort.
  * ORDRE « IMPERATIF » (= le port aujourd'hui) : `_on_toxic_damage_ability` est appele depuis
    `after_hit_normal_attack`, c.-a-d. APRES `_apply_damage_pipeline` -- donc APRES les vecteurs de
    mort emis par `_fire_death_if_killed`.

MONTAGE DISCRIMINANT (le seul regime ou les deux ordres divergent, cf. `probe_o10_defork.py`) :
`tyranParasite` porte une arme `Toxic` (1 coup) ET le passif `BarbedOvipositor`, dont
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.BarbedOvipositorAbility$$CreateBehaviour`
consomme un `PickRandomly` sur `On(0 = UnitDeath)`. La victime `astraBullgryn` n'est ni
`Mechanical` ni `Steppable` -> elle passe les deux exclusions du `CreateTrigger`. `--hp-target`
la rend one-shottable, donc le kill est DETERMINISTE.

VERDICT : on rejoue la MEME attaque offline dans les deux ordres depuis le MEME etat MT (`dumpRng`),
et on confronte au LIVE **le verdict de contamination ET l'etat MT final**. Le MT est l'oracle : deux
tirages permutes peuvent rendre le meme degat, jamais le meme MT.

Usage : python probe_o10_rng_order.py [--hp 500] [--attacks 6]
Pre-requis : session Frida vivante et WARMEE (aucun (re)inject ici). ASCII only.
"""
from __future__ import annotations

import argparse
import copy
import json
import subprocess
import sys
import uuid
from collections import deque
from pathlib import Path

import requests

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
HOST = "http://127.0.0.1:8765"
BOARD = "MC1_67"
CARRIER = "tyranParasite"          # HERO --list-pool : arme Toxic 1 coup + passif BarbedOvipositor
ESCORT = "adeptHospitaller"        # 2e p-unit (garde une activation)
FOE = "astraBullgryn"              # ni Mechanical ni Steppable -> BarbedOvipositor peut firer
CONTAMINATED = 1244
TOXIC = "Toxic"


def _sid():
    return requests.get(f"{HOST}/api/admin/status", timeout=10).json()["session"]["id"]


def _rpc(sid, method, body=None, timeout=180):
    r = requests.post(f"{HOST}/api/scripts/{sid}/rpc",
                      json={"method": method, "args": [body] if body is not None else []},
                      timeout=timeout).json()
    return r.get("result", r)


def _build(sid, hp, seed, n_foes):
    sf = ROOT / "logs" / "runners" / f"o10order-{uuid.uuid4().hex[:8]}.json"
    sf.parent.mkdir(parents=True, exist_ok=True)
    p = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--state-file", str(sf),
         "--board", BOARD, "--roster", str(max(2, n_foes)), "--hp-target", str(hp),
         "--p-units", f"{CARRIER},{ESCORT}", "--a-units", ",".join([FOE] * n_foes)],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not sf.exists():
        print("[order] build KO:", (p.stderr or p.stdout)[-500:])
        return None
    return json.loads(sf.read_text())["runnerId"]


def _bfs(board, src):
    dist, q = {src: 0}, deque([src])
    while q:
        x = q.popleft()
        for n in board.neighbours(x):
            if n not in dist and (n == src or board.walkable(n)):
                dist[n] = dist[x] + 1
                q.append(n)
    return dist


def _drive(sid, rid, board):
    my = None
    for _ in range(14):
        dv = _rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 200)
        units = dv.get("units") or []
        me = next((u for u in units if u.get("visualId") == CARRIER and u.get("alive")), None)
        if me is None:
            return None
        if my is None:
            my = me.get("owner")
        if dv.get("currentPlayer") != my or me["id"] not in (dv.get("toActivate") or []):
            _rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            continue
        norm = next((a for a in (me.get("abilities") or []) if a.get("kind") == "normal"), None)
        if norm is None:
            return None
        plan = next((p for p in (dv.get("attackPlans") or []) if p.get("unitId") == me["id"]), None)
        ev = next((e for e in ((plan or {}).get("evals") or [])
                   if e.get("targetId") is not None and (e.get("ranked") or [])), None)
        if ev is not None:
            rk, here = ev["ranked"][0], (me.get("pos") or {})
            if rk.get("col") is None or (rk["col"], rk["row"]) == (here.get("col"), here.get("row")):
                return me["id"], ev["targetId"], norm["id"]
            _rpc(sid, "applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": me["id"], "to": {"col": rk["col"], "row": rk["row"]}}}, 60)
            continue
        pos = me.get("pos") or {}
        foes = [u for u in units if u.get("owner") != my and u.get("alive") and (u.get("pos") or {})]
        if pos.get("col") is None or not foes:
            return None
        tp = min(((u["pos"]["col"], u["pos"]["row"]) for u in foes),
                 key=lambda p: abs(p[0] - pos["col"]) + abs(p[1] - pos["row"]))
        dist = _bfs(board, board.id_at(*tp))
        mt = _rpc(sid, "aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60) or {}
        cmt = next((x for x in (mt.get("units") or []) if x.get("unitId") == me["id"]), None)
        reach = {board.id_at(t["col"], t["row"]): (t["col"], t["row"])
                 for t in ((cmt or {}).get("tiles") or [])}
        pool = [t for t in reach if t in dist]
        if pool:
            col, row = reach[min(pool, key=lambda t: dist[t])]
            _rpc(sid, "applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": me["id"], "to": {"col": col, "row": row}}}, 60)
        _rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    return None


def _tiles_with(sid, rid, board, effect_type):
    tm = _rpc(sid, "tileMeta", {"runnerId": rid}, 60) or {}
    out = set()
    for t in (tm.get("tiles") or []):
        if any(e.get("effectType") == effect_type for e in (t.get("effects") or [])):
            tid = board.id_at(t["col"], t["row"])
            if tid is not None:
                out.add(tid)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hp", type=int, default=500, help="PV des a-units (one-shot deterministe)")
    ap.add_argument("--attacks", type=int, default=6)
    ap.add_argument("--seed", default="777")
    ap.add_argument("--foes", type=int, default=4, help="nb de victimes (repetitions du regime)")
    ap.add_argument("--out", default="rng-order", help="nom du fichier de trace")
    args = ap.parse_args()

    sys.path.insert(0, str(PYDIR))
    import gameconfig as GC
    from engine.entities.pathfinding.board import Board
    from engine.runner.components import HealthComponent, PositionComponent, UnitComponent
    from engine.runner.messages import AttackUnitMessage
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.runner import Runner
    from engine.runner.snapshot import load_state

    chance = int(GC.global_value("toxicDamageContaminationChance"))
    sid = _sid()
    rid = _build(sid, args.hp, args.seed, args.foes)
    if rid is None:
        return
    print(f"[order] runner={rid} seed={args.seed} foes={args.foes} hp_target={args.hp} "
          f"chance={chance}")
    rows = []
    try:
        bg = _rpc(sid, "boardGraph", {"runnerId": rid}, 60)
        board = Board(bg["tiles"], adjacency="evenq")
        for k in range(args.attacks):
            drive = _drive(sid, rid, board)
            if drive is None:
                print("[order] plus de contact -> stop")
                break
            me_id, tgt_id, norm_id = drive
            dv = _rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 200)
            ob = _rpc(sid, "observeBattle", {"runnerId": rid}, 60)
            snap = _rpc(sid, "combatSnapshot", {"runnerId": rid}, 90)
            s1 = _rpc(sid, "dumpRng", {"runnerId": rid}, 30)
            if not (isinstance(s1, dict) and s1.get("ok")):
                break
            base = load_state(dv, ob, snap, board=board)
            if base.effects is None:
                break
            pc = base.get_entity(tgt_id).get_component(PositionComponent)
            tile = board.id_at(pc.col, pc.row) if pc is not None else None
            if tile is None or tile in _tiles_with(sid, rid, board, CONTAMINATED):
                _rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
                continue

            # ---- LE PORT TEL QU'IL EST (quel que soit l'ordre qu'il implemente)
            st = copy.deepcopy(base)
            st.rng = IntBasedMersenneTwister()
            st.rng.mt, st.rng.mti = list(s1["mt"]), s1["mti"]
            rolls = []
            orig = IntBasedMersenneTwister.next_internal

            def _tap(self, lo, hi, _o=orig):
                v = _o(self, lo, hi)
                rolls.append((int(lo), int(hi), int(v)))
                return v

            IntBasedMersenneTwister.next_internal = _tap
            try:
                r = Runner(st).install_default_handlers(20)
                r.apply(AttackUnitMessage(me_id, tgt_id))
            finally:
                IntBasedMersenneTwister.next_internal = orig
            imp_cont = st.effects.has_effect(tile, effect_type=CONTAMINATED)
            imp_mt = (list(st.rng.mt), st.rng.mti)
            thc = st.get_entity(tgt_id).get_component(HealthComponent)
            imp_hp, imp_dead = (thc.hp if thc else None), (not st.get_entity(tgt_id)
                                                           .get_component(UnitComponent).alive)
            last = r.damage_handler.last or {}

            # ---- LES DEUX ORDRES CANONIQUES, reconstruits ANALYTIQUEMENT depuis le MEME MT et la
            #      liste de tirages OBSERVEE : on ne devine rien, on PERMUTE le `Maybe(1,100)`.
            #        BUS  = place NATIVE : `ApplyDamageOperation$$Execute` emet `On(0x10)` AVANT que la
            #               mort ne soit traitee -> [coups d'arme] [Maybe] [tirages de mort]
            #        AFTER_DEATH = l'ancienne place imperative (`after_hit_normal_attack`) ->
            #               [coups d'arme] [tirages de mort] [Maybe]
            #      Les deux consomment le MEME nombre de tirages -> MEME MT final : seul le VERDICT
            #      de pose les distingue (c'est pour ca qu'un critere « delta mti » est aveugle ici).
            def _replay(order):
                c = IntBasedMersenneTwister()
                c.mt, c.mti = list(s1["mt"]), s1["mti"]
                mv = None
                for item in order:
                    if item == "maybe":
                        mv = c.next_internal(1, 100)
                    else:
                        c.next_internal(item[0], item[1])
                return {"maybe_value": int(mv), "contaminated": bool(mv <= chance),
                        "mt": (list(c.mt), c.mti)}

            bus = after_death = None
            maybe_idx = next((i for i, r3 in enumerate(rolls) if r3[:2] == (1, 100)), None)
            n_hit = int(last.get("hits") or 1)
            others = [r3 for i, r3 in enumerate(rolls) if i != maybe_idx]
            if maybe_idx is not None and len(others) > n_hit:      # il Y A des tirages de mort
                bus = _replay(others[:n_hit] + ["maybe"] + others[n_hit:])
                after_death = _replay(others + ["maybe"])

            # ---- LIVE
            res = _rpc(sid, "applyAction", {"runnerId": rid, "action": {
                "kind": "ability", "casterId": me_id, "targetId": tgt_id,
                "abilityType": norm_id}}, 60)
            ok = isinstance(res, dict) and res.get("ok") and (res.get("actions") or [{}])[0].get("ok")
            s2 = _rpc(sid, "dumpRng", {"runnerId": rid}, 30)
            live_cont = tile in _tiles_with(sid, rid, board, CONTAMINATED)
            ob2 = _rpc(sid, "observeBattle", {"runnerId": rid}, 60)
            live_dead = any(u.get("squadId") == tgt_id and u.get("isDead")
                            for u in (ob2.get("units") or []))
            live_mt = (list(s2["mt"]), s2["mti"]) if isinstance(s2, dict) and s2.get("ok") else None

            def _m(model):
                return (None if model is None else
                        {"contaminated": model["contaminated"], "maybe_value": model["maybe_value"],
                         "mti": model["mt"][1],
                         "mt_eq_live": (live_mt is not None and model["mt"] == live_mt)})

            row = {
                "k": k, "ok": bool(ok), "tile": tile, "profile": last.get("profile"),
                "hits": last.get("hits"), "rolls": rolls,
                "port": {"contaminated": imp_cont, "hp": imp_hp, "dead": imp_dead,
                         "mti": imp_mt[1], "mt_eq_live": (live_mt is not None
                                                          and imp_mt == live_mt)},
                "bus": _m(bus), "after_death": _m(after_death),
                "live": {"contaminated": live_cont, "dead": live_dead,
                         "mti": (live_mt[1] if live_mt else None), "mti_before": s1["mti"]},
            }
            rows.append(row)
            print(f"[order] #{k} profile={row['profile']} hits={row['hits']} tile={tile} "
                  f"rolls={[(a, b, v) for a, b, v in rolls]}")
            print(f"[order] #{k}   PORT       cont={imp_cont} dead={imp_dead} mti={imp_mt[1]} "
                  f"MT==live? {row['port']['mt_eq_live']}")
            if bus is not None:
                print(f"[order] #{k}   BUS(natif) cont={bus['contaminated']} "
                      f"maybe={bus['maybe_value']} mti={bus['mt'][1]}")
                print(f"[order] #{k}   AFTERDEATH cont={after_death['contaminated']} "
                      f"maybe={after_death['maybe_value']} mti={after_death['mt'][1]}")
            else:
                print(f"[order] #{k}   ORDRES NON RECONSTRUITS (aucun tirage de mort -> regime NON "
                      f"discriminant : les deux ordres coincident)")
            print(f"[order] #{k}   LIVE       cont={live_cont} dead={live_dead} "
                  f"mti {s1['mti']} -> {row['live']['mti']}")
            if not live_dead:
                _rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    finally:
        try:
            _rpc(sid, "disposeRunner", {"runnerId": rid}, 60)
        except Exception:
            pass

    disc = [r for r in rows if r["bus"] is not None]
    print(f"[order] attaques confrontees={len(rows)} dont DISCRIMINANTES (mort + tirage)={len(disc)}")
    n_port = sum(1 for r in disc if r["port"]["contaminated"] == r["live"]["contaminated"])
    n_bus = sum(1 for r in disc if r["bus"]["contaminated"] == r["live"]["contaminated"])
    n_ad = sum(1 for r in disc if r["after_death"]["contaminated"] == r["live"]["contaminated"])
    for r in disc:
        print(f"[order]   #{r['k']} port={r['port']['contaminated']} bus={r['bus']['contaminated']} "
              f"afterdeath={r['after_death']['contaminated']} live={r['live']['contaminated']}")
    print(f"[order] ACCORD AVEC LE LIVE : port={n_port}/{len(disc)} bus={n_bus}/{len(disc)} "
          f"afterdeath={n_ad}/{len(disc)}")
    out = ROOT / "logs" / "o10-defork"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{args.out}.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
    print(f"[order] trace -> {out / (args.out + '.json')}")


if __name__ == "__main__":
    main()
