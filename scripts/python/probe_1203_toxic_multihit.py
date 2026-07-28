"""MESURE de la GRANULARITE du canal `OnToxicDamageAbility` (1203) sur un porteur MULTI-COUPS.

Ce que `probe_1203_toxic_contamination.py` ne pouvait PAS discriminer : son porteur
(`genesBiophagus`, arme `Toxic` 1 coup) rend « un tirage par COUP » et « un tirage par SERIE »
OBSERVATIONNELLEMENT IDENTIQUES. Le residu etait explicitement laisse ouvert par
`docs/rl/case-1203-on-toxic-damage.md` §5.

Le seul porteur d'ARME `Toxic` MULTI-COUPS confrontable est le SUMMON `admecSmnVanguard`
(3 coups, range 2), amene en bataille par son summoner `admecMarshall` (HERO, present dans
`rl_duel.py build --list-pool`) : le passif `ControlEdict` le spawne apres une attaque NORMALE
du Marshall (`IdunBattleLogic.Entities.Abilities.Triggered.Loki.ControlEdictAbility$$SummonMinion`,
branche PROTECTOR). Les autres porteurs multi-coups sont NPC, sauf la MoW `deathCrawler` -- ecartee
a dessein : le RPC `combatSnapshot` corrompt tout runner contenant une entite `Machine`
(residu O7 de `docs/rl/port-residuals-inventory.md`), et ce probe repose sur `combatSnapshot`.

RE (decompile ghidra, build gqfc5mff6c) -- ce que la mesure doit confirmer :
    IdunBattleLogic.Entities.Abilities.Damage.Loki.OnToxicDamageAbility$$CreateBehaviour
        If( IsFirstHitInSeries() & Maybe(ConfigConst(0x4b3, Self@0x148, 0x2a = chance)),
            AddEffect(0x4dc = Contaminated, stateRef, Tiles(target@0x178)) )
`IdunBattle.Entities.Triggers.IsFirstHitInSeriesTrigger$$ShouldTrigger` lit
`IdunBattle.Entities.Abilities.AbilityEntities$$get_IsFirstHit` = `Nullable<int>` @+0x110, vrai ssi
l'index vaut 0 ; son FRERE `get_IsFirstHitGroup` vit a @+0x118 -- DEUX compteurs DISTINCTS, donc
« serie » (index de coup) n'est PAS « groupe dans l'attaque ». `ADamageOperation$$SetupHitGroup`
cree un groupe PAR CIBLE (il y stocke `GetStat(cible, 5)` @+0x50) et
`ADamageOperation$$UpdateCurrentAttackAfterHit` incremente le compteur de groupes de l'attaque.
=> une SERIE = les coups portes sur UNE cible ; le tirage est UN par cible, pas un par coup.

MESURE (discriminante) : sur l'attaque du Vanguard (3 coups sur la MEME cible), on confronte
l'ETAT MT (`mt`/`mti`) apres l'attaque, LIVE (`dumpRng`) contre OFFLINE. Un port qui tirerait
par COUP consommerait 3 `next_bool` la ou le natif en consomme 1 -> les MT divergent. C'est
l'oracle de CONSOMMATION : `call_count` ne convient pas (incremente par `next_internal` ET par
`genrand_int32`, +2 par `NextBool`).

Usage : python probe_1203_toxic_multihit.py [--seed 777] [--board MC1_67]
Pre-requis : session Frida vivante et WARMEE (aucun (re)inject ici). ASCII only.
"""
from __future__ import annotations

import argparse
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
SUMMONER_VIS = "admecMarshall"        # Tan Gi'da -- HERO du pool, porte le passif `ControlEdict`
# PIEGE #38b : la cle de config du summon (`ControlEdict.constants.unitId` = `admecSmnVanguard`)
# n'est PAS le `visualId` expose par decisionView/observeBattle -- il faut le resoudre via
# `gameconfig.unit(<cle>)["visualId"]` (= `admecNpc1Vanguard`, meme arme `Toxic` 3 coups r2).
# Comparer sur la cle rend 0 summon vu : c'est la cause racine du bug #38b.
SUMMON_KEY = "admecSmnVanguard"
ESCORT_VIS = "adeptHospitaller"
FOES = "necroWarden,necroWarden"      # temoin SANS `Daemon` : aucun tirage de block surnumeraire
CONTAMINATED = 1244                   # 0x4dc -- effet de TUILE
TOXIC_PROFILE = "Toxic"


def _sid():
    return requests.get(f"{HOST}/api/admin/status", timeout=10).json()["session"]["id"]


def _rpc(sid, method, body=None, timeout=180):
    r = requests.post(f"{HOST}/api/scripts/{sid}/rpc",
                      json={"method": method, "args": [body] if body is not None else []},
                      timeout=timeout).json()
    return r.get("result", r)


def _build(seed, board):
    sf = ROOT / "logs" / "runners" / f"toxmulti-{uuid.uuid4().hex[:8]}.json"
    sf.parent.mkdir(parents=True, exist_ok=True)
    p = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--state-file", str(sf),
         "--board", board, "--roster", "2",
         "--p-units", f"{SUMMONER_VIS},{ESCORT_VIS}", "--a-units", FOES],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not sf.exists():
        print("[probe] build KO:", (p.stderr or p.stdout)[-500:])
        return None, sf
    return json.loads(sf.read_text())["runnerId"], sf


def _bfs(board, src):
    dist, q = {src: 0}, deque([src])
    while q:
        x = q.popleft()
        for n in board.neighbours(x):
            if n not in dist and (n == src or board.walkable(n)):
                dist[n] = dist[x] + 1
                q.append(n)
    return dist


def _drive(sid, rid, board, vis, rounds=14):
    """DRIVE les positions (doctrine : jamais « bloque par la geometrie de spawn ») jusqu'a ce que
    l'unite `vis` ait un `attackPlan` LIVE ; joue le MOVE du plan et rend
    `(unitId, targetId, abilityType normal)`. None si aucun contact."""
    my = None
    for _ in range(rounds):
        dv = _rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        units = dv.get("units") or []
        me = next((u for u in units if u.get("visualId") == vis and u.get("alive")), None)
        if me is None:
            return None
        if my is None:
            my = me.get("owner")
        # `currentPlayer` NE SUFFIT PAS : un summon apparu pendant le tour peut avoir deja consomme
        # son activation. La porte reelle est `toActivate` -- sans elle, `applyAction` accepte le
        # cast (`ok=True`) mais ne mute RIEN et ne tire RIEN (no-op silencieux).
        if dv.get("currentPlayer") != my or me["id"] not in (dv.get("toActivate") or []):
            _rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            continue
        norm = next((a for a in (me.get("abilities") or []) if a.get("kind") == "normal"), None)
        if norm is None:
            return None
        plan = next((ap for ap in (dv.get("attackPlans") or []) if ap.get("unitId") == me["id"]), None)
        ev = next((e for e in ((plan or {}).get("evals") or [])
                   if e.get("targetId") is not None and (e.get("ranked") or [])), None)
        if ev is not None:
            rk = ev["ranked"][0]
            here = (me.get("pos") or {})
            if rk.get("col") is None or (rk.get("col"), rk.get("row")) == (here.get("col"),
                                                                          here.get("row")):
                return me["id"], ev["targetId"], norm["id"]   # DEJA a portee : on tire sans bouger
            # PLACER D'ABORD, ATTEINDRE SON TOUR ENSUITE : un `move` peut consommer l'activation ou
            # faire BASCULER le joueur courant -- le cast qui suivrait serait refuse EN SILENCE
            # (`ok=True`, 0 mutation, 0 tirage). On joue donc le move puis on RE-EVALUE : on ne rend
            # la main a l'appelant que sur un plan ne demandant PLUS de deplacement.
            _rpc(sid, "applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": me["id"], "to": {"col": rk["col"], "row": rk["row"]}}}, 60)
            continue
        pos = me.get("pos") or {}
        enemies = [u for u in units if u.get("owner") != my and u.get("alive") and (u.get("pos") or {})]
        if pos.get("col") is None or not enemies:
            return None
        tp = min(((u["pos"]["col"], u["pos"]["row"]) for u in enemies),
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


def _mt(rng):
    return (list(rng.mt), rng.mti)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--runner", type=int, default=None, help="reutilise un runner existant")
    args = ap.parse_args()

    sys.path.insert(0, str(PYDIR))
    import gameconfig as GC
    from engine.entities.pathfinding.board import Board
    from engine.runner.components import HealthComponent, PositionComponent, UnitComponent
    from engine.runner.messages import AttackUnitMessage
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.runner import Runner
    from engine.runner.snapshot import load_state

    carrier_vis = (GC.unit(SUMMON_KEY) or {}).get("visualId") or SUMMON_KEY   # #38b
    print(f"[probe] summon config={SUMMON_KEY} -> visualId LIVE={carrier_vis}")

    sid = _sid()
    sf = None
    if args.runner:
        rid = args.runner
    else:
        rid, sf = _build(args.seed, args.board)
        if rid is None:
            return 2
    print(f"[probe] session={sid} runner={rid} seed={args.seed} board={args.board}")

    bg = _rpc(sid, "boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        print("[probe] boardGraph indispo")
        return 2
    board = Board(bg["tiles"], adjacency="evenq")

    # --- etape 1 : faire attaquer le SUMMONER -> `ControlEdict` spawne le Vanguard -------------
    for attempt in range(6):
        dv = _rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        if any(u.get("visualId") == carrier_vis and u.get("alive") for u in (dv.get("units") or [])):
            break
        drive = _drive(sid, rid, board, SUMMONER_VIS)
        if drive is None:
            print("[probe] summoner sans contact -> pas de spawn possible")
            return 2
        uid, tgt, norm = drive
        res = _rpc(sid, "applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": uid, "targetId": tgt, "abilityType": norm}}, 60)
        ok = isinstance(res, dict) and res.get("ok")
        print(f"[probe] attaque summoner #{attempt} ok={ok}")
        _rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)

    dv = _rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    smn = [u for u in (dv.get("units") or []) if u.get("visualId") == carrier_vis and u.get("alive")]
    print(f"[probe] summons vivants={len(smn)} ids={[u['id'] for u in smn]}")
    if not smn:
        print("[probe] AUCUN summon -> mesure multi-coups impossible sur ce runner")
        return 2

    # --- etape 2 : confronter l'attaque, unite par unite --------------------------------------
    # DECOMPOSITION PAR ETAGE (jamais fitter un scalaire) : on confronte D'ABORD le SUMMONER
    # (`admecMarshall`, arme `Toxic` 1 coup) = TEMOIN mono-coup deja couvert par le test live
    # existant, PUIS le summon (3 coups). Si le temoin est bit-exact et le multi-coups non, la
    # granularite (par COUP vs par SERIE) est en cause ; si les DEUX divergent, la cause est en
    # amont du canal 1203 et il ne faut surtout pas la lui imputer.
    compared, placements = 0, 0
    for tag, vis in ((f"ranged-1coup:{SUMMONER_VIS}", SUMMONER_VIS),
                     (f"multi-3coups:{carrier_vis}", carrier_vis)):
      for attempt in range(12):
        drive = _drive(sid, rid, board, vis)
        if drive is None:
            break
        me_id, tgt_id, norm_id = drive

        dv2 = _rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        ob2 = _rpc(sid, "observeBattle", {"runnerId": rid}, 60)
        snap = _rpc(sid, "combatSnapshot", {"runnerId": rid}, 90)
        s1 = _rpc(sid, "dumpRng", {"runnerId": rid}, 30)
        if not (isinstance(s1, dict) and s1.get("ok")):
            print("[probe] dumpRng KO")
            return 2
        state = load_state(dv2, ob2, snap, board=board)
        if state.effects is None:
            print("[probe] EffectsState absent")
            return 2
        rng = IntBasedMersenneTwister()
        rng.mt, rng.mti = list(s1["mt"]), s1["mti"]
        state.rng = rng

        pc = state.get_entity(tgt_id).get_component(PositionComponent)
        tgt_tile = board.id_at(pc.col, pc.row) if pc is not None else None
        pre_live = _tiles_with(sid, rid, board, CONTAMINATED)
        if tgt_tile is None or tgt_tile in pre_live:
            _rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            continue

        res = _rpc(sid, "applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": me_id, "targetId": tgt_id,
            "abilityType": norm_id}}, 60)
        if not (isinstance(res, dict) and res.get("ok")
                and (res.get("actions") or [{}])[0].get("ok")):
            _rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            continue
        live_hp = next((u.get("hp") for u in (res.get("units") or [])
                        if u.get("squadId") == tgt_id), None)
        live_cont = tgt_tile in _tiles_with(sid, rid, board, CONTAMINATED)
        s2 = _rpc(sid, "dumpRng", {"runnerId": rid}, 30)
        live_mt = (list(s2["mt"]), s2["mti"]) if isinstance(s2, dict) and s2.get("ok") else None
        # GARDE ANTI-NO-OP (piege deja paye) : `applyAction` rend `ok=True` meme quand le cast est
        # REFUSE en silence (le joueur courant a bascule apres le move) -- aucune mutation, aucun
        # tirage. Signature : le MT live n'a PAS avance. Confronter dans cet etat imputerait au
        # canal 1203 un ecart qui n'est qu'un coup NON JOUE cote live.
        if live_mt is not None and live_mt[1] == s1["mti"] and live_mt[0] == list(s1["mt"]):
            act0 = (res.get("actions") or [{}])[0]
            print(f"[{tag} #{attempt}] SKIP no-op live (MT inchange, mti={s1['mti']}) "
                  f"mutated={act0.get('mutated')} evts={len(res.get('events') or [])}")
            _rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            continue

        runner = Runner(state).install_default_handlers(20)
        runner.apply(AttackUnitMessage(me_id, tgt_id))
        off_hp = state.get_entity(tgt_id).get_component(HealthComponent).hp
        off_cont = state.effects.has_effect(tgt_tile, effect_type=CONTAMINATED)
        last = runner.damage_handler.last or {}
        off_mt = _mt(state.rng)

        print(f"[{tag} #{attempt}] profile={last.get('profile')} hits={last.get('hits')} "
              f"hp live={live_hp} off={off_hp} contaminated live={live_cont} off={off_cont} "
              f"tile={tgt_tile}")
        # ETAGE « coups » : le detail per-coup offline face au detail per-coup LIVE (events
        # `UnitDamaged`). Un ecart de NOMBRE de coups, ou un coup a coup, localise l'etage fautif
        # bien avant le total de PV.
        print(f"[{tag} #{attempt}] coups offline={last.get('rolls') or last.get('damages')} "
              f"total_off={last.get('damage')}")
        dmg_ev = [e for e in (res.get("events") or [])
                  if isinstance(e, dict) and "Damage" in str(e.get("type") or e.get("name") or "")]
        print(f"[{tag} #{attempt}] events degat LIVE ({len(dmg_ev)}) = "
              f"{[ {k: v for k, v in e.items() if k in ('type','name','Damage','damage','Effect_Type','TargetId')} for e in dmg_ev[:8] ]}")
        if live_mt is not None:
            same = (off_mt[0] == live_mt[0] and off_mt[1] == live_mt[1])
            print(f"[{tag} #{attempt}] MT apres attaque : identique={same} "
                  f"mti off={off_mt[1]} live={live_mt[1]} (mti_avant={s1['mti']})")
        compared += 1
        placements += int(bool(live_cont))
        if live_cont:                      # une POSE confrontee = le cas discriminant, on s'arrete
            break
        _rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
      else:
        print(f"[{tag}] aucune confrontation aboutie en 12 tentatives")

    print(f"[probe] attaques confrontees={compared} poses confrontees={placements}")
    if sf is not None:
        _rpc(sid, "disposeRunner", {"runnerId": rid}, 60)
        print(f"[probe] runner {rid} dispose")
    return 0 if compared else 1


if __name__ == "__main__":
    raise SystemExit(main())
