#!/usr/bin/env python
"""Probe #490 -- validation live de la face COMBAT de PsychicMaelstrom (active 1027, Sibyll
`astraPrimarisPsy`).

Port : `engine/runner/abilities/loki/psychic_maelstrom.py` (mirror de
`IdunBattleLogic.Entities.Abilities.Active.Loki.PsychicMaelstromAbility$$ExecuteBehaviour`).

CE QUE CE PROBE MESURE, ET POURQUOI CETTE FORME
-----------------------------------------------
Le nombre de coups de 1027 est une FORMULE evaluee au cast :
`Multiply(Sum(Direct(1), 4 x ConditionalAmount(Maybe(chance_i), Direct(1))), Direct(nrOfHits))`,
soit 1 a 5 coups selon quatre `NextBool(75/50/25/10)`. Un accord sur UN cast ne prouverait donc
rien (un port qui figerait `hits=1` tomberait juste une fois sur trois). La methode est le
REPLAY-DIFF bit-exact repete : meme etat pre-cast (`decisionView`/`observeBattle`/`combatSnapshot`/
`dumpRng`), cast live PUIS cast offline sur cet etat, et diff des deltas HP -- N fois de suite,
en EXIGEANT que le nombre de coups VARIE d'un cast a l'autre (temoin non-degenere : un accord
obtenu uniquement sur des casts a 1 coup ne discriminerait pas).

L'accord bit-exact du DEGAT porte trois choses a la fois :
  (a) le nombre de coups (une divergence de coup change le total de ~1900 PV) ;
  (b) l'ORDRE des tirages -- les quatre `NextBool` partent AVANT les tirages de degat
      (`SumAmount$$Calculate` evalue a..e, puis `AbilityDamageBehaviour$$ExecuteTarget` attaque) ;
      les permuter decalerait tout le flux `IntBasedMersenneTwister` et le total avec ;
  (c) la route d'Operation (famille ABILITY : `AbilityDamageOperation`, aucun crit).

Verifie AUSSI `last['ported'] is True` (face EXECUTER : sans lui, le cast est un no-op silencieux)
et que le nombre de coups offline est bien dans `[1 .. 5 x nrOfHits]`.

ASCII only (cp1252).
Usage: python probe_490_psychic_maelstrom.py [--seed 49001] [--board MC1_67] [--casts 8]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hexgeo  # noqa: E402
from rl_collect_batch import _resolve_session, _rpc  # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]

SIBYLL_VIS = "astraPrimarisPsy"      # Sibyll -- SEUL porteur lineup de 1027 (4 autres = npc)
ABILITY = 1027
ABILITY_ID = "PsychicMaelstrom"
RANGE = 2                            # constants.range de 1027 (RANGE_FROM_CONFIG)

BUILD_UNITS = ["--p-units", f"{SIBYLL_VIS},templAncient",
               "--a-units", "ultraTitus,necroWarden",
               "--hp-target", "400000", "--hp-player", "400000"]


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _pos(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row"))


def _find(dec, vis):
    return next((u for u in (dec.get("units") or [])
                 if u.get("visualId") == vis and u.get("alive")), None)


def _hp(ob, uid):
    for u in (ob.get("units") or []):
        if u.get("squadId") == uid and not u.get("isDead"):
            return u.get("hp")
    return None


def build(rpcless_seed: int, board: str, tag: str) -> int:
    state = ROOT / "logs" / "runners" / f"_a490_pm_state_{tag}.json"   # SORTIE -> logs/ (#349)
    state.parent.mkdir(parents=True, exist_ok=True)
    state.unlink(missing_ok=True)
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(rpcless_seed),
         "--state-file", str(state), "--board", board] + BUILD_UNITS,
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not state.exists():
        print(f"[490] build KO: {(proc.stderr or proc.stdout or '')[-500:]}", file=sys.stderr)
        sys.exit(2)
    return json.loads(state.read_text())["runnerId"]


def _advance_to_my_turn(rpc, rid, vis, max_iter=12):
    for _ in range(max_iter):
        dec = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        if not _ok(dec):
            return None, None
        u = _find(dec, vis)
        if u is None:
            return dec, None
        if dec.get("currentPlayer") == u.get("owner"):
            return dec, u
        rpc("aiPlayTurn", {"runnerId": rid}, 240)
        dec2 = rpc("decisionView", {"runnerId": rid}, 150)
        if _ok(dec2) and dec2.get("currentPlayer") != (u or {}).get("owner"):
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    return None, None


def _drive_in_range(rpc, rid, max_turns=10):
    """DRIVE Sibyll a distance hex <= RANGE d'un ennemi (doctrine drive-positions : on DEPLACE,
    on ne se plaint pas de la geometrie de spawn)."""
    for _ in range(max_turns):
        dec, me = _advance_to_my_turn(rpc, rid, SIBYLL_VIS)
        if me is None:
            return None, None, None
        enemies = [u for u in (dec.get("units") or [])
                   if u.get("alive") and u.get("owner") != me.get("owner")]
        if not enemies:
            return None, None, None
        tgt = min(enemies, key=lambda e: hexgeo.distance(_pos(me), _pos(e)))
        if 1 <= hexgeo.distance(_pos(me), _pos(tgt)) <= RANGE:
            return dec, me, tgt
        mt = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
        cmt = next((x for x in (mt.get("units") or []) if x.get("unitId") == me["id"]), None)
        tiles = [(t["col"], t["row"]) for t in ((cmt or {}).get("tiles") or [])
                 if t.get("col") is not None]
        if tiles:
            tp = _pos(tgt)
            best = min(tiles, key=lambda p: (0 if 1 <= hexgeo.distance(p, tp) <= RANGE else 1,
                                             hexgeo.distance(p, tp)))
            rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": me["id"], "to": {"col": best[0], "row": best[1]}}}, 60)
            dec2 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
            me2 = _find(dec2, SIBYLL_VIS)
            if me2 is not None:
                en2 = [u for u in (dec2.get("units") or [])
                       if u.get("alive") and u.get("owner") != me2.get("owner")]
                t2 = min(en2, key=lambda e: hexgeo.distance(_pos(me2), _pos(e))) if en2 else None
                if t2 is not None and 1 <= hexgeo.distance(_pos(me2), _pos(t2)) <= RANGE:
                    return dec2, me2, t2
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    return None, None, None


def _capture(rpc, rid):
    dec = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
    s = rpc("dumpRng", {"runnerId": rid}, 30)
    return dec, ob, snap, s


def _offline_state(dec, ob, snap, s, board):
    from engine.runner.snapshot import load_state
    from engine.runner.prng import IntBasedMersenneTwister
    state = load_state(dec, ob, snap, board=board)
    if _ok(s):
        rng = IntBasedMersenneTwister()
        rng.mt = list(s["mt"])
        rng.mti = s["mti"]
        state.rng = rng
    return state


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=49001)
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--casts", type=int, default=8)
    args = ap.parse_args()

    from engine.entities.pathfinding.board import Board
    from engine.runner.runner import Runner
    from engine.runner.messages import ActiveAbilityMessage
    from engine.runner.components import HealthComponent
    from engine.entities.effects.magnitude import ability_var

    sid = _resolve_session()

    def rpc(method, body, t=90):
        return (_rpc(sid, method, [body], timeout=t).get("result") or {})

    nr_of_hits = int(ability_var(ABILITY_ID, "nrOfHits", is_constant=True) or 0)
    chances = [int(ability_var(ABILITY_ID, k, is_constant=True) or 0)
               for k in ("chance", "chance_2", "chance_3", "chance_4")]
    print(f"[490] kit 1027 : nrOfHits={nr_of_hits} chances={chances} range={RANGE}")

    rid = build(args.seed, args.board, "a")
    print(f"[490] runner {rid} (seed {args.seed}, board {args.board})")
    fails: list = []
    hits_seen: list = []
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            print("[490] boardGraph KO")
            return 2
        board = Board(bg["tiles"], adjacency="evenq")

        for n in range(args.casts):
            dec, me, tgt = _drive_in_range(rpc, rid)
            if me is None or tgt is None:
                print(f"[490] cast#{n}: drive KO -> datapoint NON MESURE")
                break
            caster_id, target_id = me["id"], tgt["id"]
            d = hexgeo.distance(_pos(me), _pos(tgt))
            dec0, ob0, snap0, s0 = _capture(rpc, rid)
            enemies = [u for u in (dec0.get("units") or [])
                       if u.get("alive") and u.get("owner") != me.get("owner")]
            hp0 = {u["id"]: _hp(ob0, u["id"]) for u in enemies}
            state = _offline_state(dec0, ob0, snap0, s0, board)
            if state.get_entity(caster_id) is None or state.rng is None:
                fails.append(f"cast{n}:etat-offline")
                break

            res = rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "ability", "casterId": caster_id, "targetId": target_id,
                "abilityType": ABILITY}, "captureEvents": True}, 240)
            a0 = ((res or {}).get("actions") or [{}])[0]
            if not (a0.get("ok") and a0.get("mutated")):
                print(f"[490] cast#{n} live KO/illegal a d={d}: {str(res)[:240]}")
                fails.append(f"cast{n}:cast-live")
                break
            ob2 = rpc("observeBattle", {"runnerId": rid}, 60)
            live_dmg = {uid: (hp0[uid] - _hp(ob2, uid))
                        if (hp0.get(uid) is not None and _hp(ob2, uid) is not None) else None
                        for uid in hp0}

            runner = Runner(state).install_default_handlers(20)
            runner.apply(ActiveAbilityMessage(caster_id, target_id, ABILITY))
            diag = runner.ability_handler.last or {}
            if diag.get("ported") is not True:
                print(f"[490] cast#{n}: ability 1027 NON portee (no-op silencieux): {diag}")
                fails.append(f"cast{n}:ported")
                break
            off_dmg = {}
            for uid in hp0:
                e = state.get_entity(uid)
                hc = e.get_component(HealthComponent) if e is not None else None
                off_dmg[uid] = (hp0[uid] - hc.hp) if (hc is not None
                                                      and hp0.get(uid) is not None) else None
            hits = ((diag.get("attacks") or [{}])[0] or {}).get("hits")
            hits_seen.append(hits)
            same = live_dmg == off_dmg
            print(f"[490] cast#{n} d={d} cible={tgt.get('visualId')} hits(offline)={hits} "
                  f"live={live_dmg} offline={off_dmg} : {'OK' if same else 'X'}")
            if not same:
                fails.append(f"cast{n}:diff")
            if hits is None or not (1 <= int(hits) <= 5 * max(1, nr_of_hits)):
                fails.append(f"cast{n}:hits-hors-bornes({hits})")
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 60)

    # TEMOIN NON DEGENERE : un accord obtenu uniquement sur des casts a 1 coup ne discriminerait
    # pas un port qui figerait `hits`. On EXIGE d'avoir vu au moins deux valeurs distinctes.
    distinct = sorted(set(h for h in hits_seen if h is not None))
    print(f"[490] nombres de coups observes = {hits_seen} (distincts = {distinct})")
    if len(distinct) < 2:
        print("[490] TEMOIN DEGENERE : moins de 2 valeurs de coups distinctes -- "
              "l'accord ne discrimine pas un `hits` fige. Relancer avec --casts plus grand "
              "ou un autre --seed.")
        fails.append("temoin-degenere")
    if fails:
        print(f"[490] ECHECS : {fails}")
        return 1
    print(f"[490] PROBE OK -- {len(hits_seen)} cast(s) bit-exacts, coups variables {distinct}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
