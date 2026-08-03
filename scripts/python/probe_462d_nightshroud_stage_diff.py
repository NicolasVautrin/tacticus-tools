"""#462-r4d -- les BORNES NATIVES du tirage, INVERSEES a etat PRNG connu (sans inference).

Monte le scenario de `tests/engine/runner/test_nightshroud_combat_live.py` (`necroDestroyer` ->
`custoTrajann`, protege par l'aura Nightshroud d'`astraPrimarisPsy`) et decompose le coup etage par
etage. Son apport propre est `solve_bounds`.

**Pourquoi une INVERSION et pas une soustraction.** Quand le port et le natif divergent d'un
DECALAGE CONSTANT sur N coups, `live_ph[i] - off_ph[i]` mesure directement le decalage des bornes
(c'est ce que fait `probe_462_r4a_terrifying_rounding.py`, qui l'explicite comme sa seule
inference). Cette voie est INAPPLICABLE des que l'ecart n'est pas constant : le coup est un
`next_internal(lo, hi+1)`, un MODULO -- donc une borne basse decalee de 1 change la LARGEUR du
modulo et diffracte les six coups dans six directions, sans forme lisible. C'etait exactement le
symptome de ce test (`off=[180,180,112,158,240,183]` contre `live=[250,212,168,122,220,221]`,
signe INVERSE au 4e coup).

`solve_bounds` n'infere rien : a `rng0` connu (`dumpRng` avant le cast), la suite des `genrand` est
ENTIEREMENT determinee ; pour chaque largeur candidate `R` on calcule les N offsets et `lo` se
deduit du premier coup. Il ne reste qu'a exiger les N egalites -- une seule paire survit.

Sont aussi imprimes, pour attribuer l'ecart plutot que le constater :
  * `hits` / `base` / `pierce` / `armor` / `clean_min..max` offline (les entrees du tirage) ;
  * `rolls` et `per_hit` offline, les tags LIVE de chaque event de degat ;
  * le NOMBRE de tirages PRNG consommes par le natif pendant le cast (`dumpRng` avant/apres),
    confronte a ceux du port -- c'est ce qui SEPARE « formule differente » (memes tirages, valeurs
    differentes) de « flux desynchronise », et c'est ce qui a ecarte la piste RNG ici : 6 tirages
    des DEUX cotes.

`--sweep` force la stat DAMAGE de l'attaquant base par base : cela DEPLACE la partie fractionnaire
du percage, et separe des modeles d'arrondi que le cas nominal seul ne distingue pas (mesure : sur
4 bases, 8 bornes natives, dont 4 SEULES sont discriminantes).

Usage (depuis scripts/python) :
    python probe_462d_nightshroud_stage_diff.py [--solve] [--seed 777] [--board MC1_67]
    python probe_462d_nightshroud_stage_diff.py --sweep 906,907,911,1000
ASCII only (cp1252). Dispose SON runner en sortie.
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
from engine.entities.pathfinding.board import Board
from engine.runner.components import HealthComponent
from engine.runner.damage_model import defender_modifiers
from engine.runner.messages import AttackUnitMessage
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.runner import Runner
from engine.runner.snapshot import load_state

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]

ATTACKER = "necroDestroyer"
CARRIER = "astraPrimarisPsy"
TARGET = "custoTrajann"


def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _tags(e):
    tg = e.get("tags")
    return (json.loads(tg) if isinstance(tg, str) else tg) or {}


def _seed_rng(s):
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"])
    rng.mti = s["mti"]
    return rng


def _bfs(board, src):
    dist = {src: 0}
    q = deque([src])
    while q:
        x = q.popleft()
        for n in board.neighbours(x):
            if n not in dist and (n == src or board.walkable(n)):
                dist[n] = dist[x] + 1
                q.append(n)
    return dist


def _rng_advance(before: dict, after: dict) -> int:
    """Nombre de `genrand` consommes entre deux dumps du Mersenne Twister natif.

    Le twister regenere son bloc de 624 mots quand `mti` atteint 624 : un simple delta de `mti`
    sous-compte alors d'un bloc. On detecte la regeneration par le changement du vecteur `mt`."""
    b, a = int(before["mti"]), int(after["mti"])
    same_block = list(before["mt"]) == list(after["mt"])
    return (a - b) if same_block else (a - b + 624)


_TRACE: list = []
_SAVED: dict = {}


def _install_bounds_trace():
    """Instrumente le PATCH-POINT documente du vecteur NORMALE (`damage_ops.normal` resout ses
    dependances dans SES globals) pour lire les ETAGES du calcul des bornes reduites :
    `get_base_damage_fix64` -> `apply_pierce_and_modifiers` -> `apply_all_modifiers`.
    Purement observationnel (les valeurs rendues sont celles des fonctions d'origine)."""
    from engine.runner.operations.damage_ops import normal as N
    _TRACE.clear()
    _SAVED.clear()
    for name in ("get_base_damage_fix64", "apply_pierce_and_modifiers", "apply_all_modifiers"):
        _SAVED[name] = getattr(N, name)

    def _wrap(name):
        fn = _SAVED[name]

        def _w(*a, **k):
            r = fn(*a, **k)
            _TRACE.append((name, [repr(x) for x in a], {kk: repr(vv) for kk, vv in k.items()}, repr(r)))
            return r
        return _w

    for name in _SAVED:
        setattr(N, name, _wrap(name))
    return _TRACE


def _restore_bounds_trace():
    from engine.runner.operations.damage_ops import normal as N
    for name, fn in _SAVED.items():
        setattr(N, name, fn)


class Live:
    def __init__(self, sid, rid):
        self.sid, self.rid = sid, rid

    def rpc(self, method, body=None, timeout=90):
        return _unwrap(R._rpc(self.sid, method, [body] if body is not None else [], timeout=timeout))


def _drive_target_to_thorns(live, rid, board, rounds=14):
    """Amene la CIBLE sur une tuile `Thorns_DefenseReduction` (regime de GENERALISATION).

    La tuile Thorns pose une modification de stat DEFENSE `-50`, que
    `IdunBattle.Core.Services.DamageCalculations$$CalculateModifiersFromStatModifications` NEGE en
    `x1.5`. Cumulee au `EffectBonus.ForPercentDecrease(20)` de MartialKatah que la cible porte deja,
    elle met les DEUX canaux defenseur en jeu SUR LE MEME COUP -- c'est le seul regime qui separe
    « les deux canaux partagent un etage » de « ils en ont chacun un ». Rend la position atteinte,
    ou None si le regime ne s'installe pas."""
    tm = live.rpc("tileMeta", {"runnerId": rid}, 60)
    rows = tm.get("tiles") if isinstance(tm, dict) else tm
    want = [(t.get("col"), t.get("row")) for t in (rows or [])
            if "Thorns_DefenseReduction" in (t.get("effects") or [])]
    if not want:
        return None
    for _ in range(rounds):
        dec = live.rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        tgt = next((u for u in (dec.get("units") or [])
                    if u.get("visualId") == TARGET and u.get("alive")), None)
        if tgt is None:
            return None
        p = tgt.get("pos") or {}
        if (p.get("col"), p.get("row")) in want:
            return (p.get("col"), p.get("row"))
        if dec.get("currentPlayer") != tgt.get("owner"):
            live.rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
            continue
        mt = live.rpc("aiMovableTiles", {"runnerId": rid, "side": "hostile"}, 60)
        row = next((x for x in (mt.get("units") or []) if x.get("unitId") == tgt["id"]), None)
        reach = [(t["col"], t["row"]) for t in ((row or {}).get("tiles") or [])]
        hit = [q for q in reach if q in want]
        # a defaut d'y arriver d'un bond : se rapprocher de la Thorns la plus proche
        dest = hit[0] if hit else (min(reach, key=lambda q: min(
            abs(q[0] - w[0]) + abs(q[1] - w[1]) for w in want)) if reach else None)
        if dest is None:
            live.rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
            continue
        live.rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": tgt["id"], "to": {"col": dest[0], "row": dest[1]}}}, 40)
        live.rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
    return None


def run(seed="777", board_id="MC1_67", verbose=True, attack=None, thorns=False):
    """Monte le scenario, mesure les deux cotes et rend le dict de decomposition (ou `{error}`).

    `attack` (optionnel) force la stat DAMAGE de l'attaquant : c'est le levier du BALAYAGE, qui
    DEPLACE la fraction du percage d'une base a l'autre et separe les modeles d'arrondi que le
    scenario nominal ne distingue pas."""
    def _say(*a):
        if verbose:
            print(*a)

    sid = R._resolve_session()
    state_file = ROOT / "logs" / "runners" / f"ns462d-{uuid.uuid4().hex[:6]}.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    stat_args = ["--unit-stat", f"{ATTACKER}:Damage={int(attack)}"] if attack else []
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--board", board_id,
            "--roster", "1", "--p-units", ATTACKER, "--a-units", f"{CARRIER},{TARGET}",
            *stat_args, "--state-file", str(state_file)]
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state_file.exists():
        return {"error": "build runner KO: " + (p.stderr or p.stdout or "")[-300:]}
    rid = json.loads(state_file.read_text())["runnerId"]
    live = Live(sid, rid)
    try:
        bg = live.rpc("boardGraph", {"runnerId": rid}, 60)
        board = Board(bg["tiles"], adjacency="native_sym")

        def utile(u):
            q = u.get("pos") or {}
            return board.id_at(q.get("col"), q.get("row")) if "col" in q else None

        if thorns:
            moved = _drive_target_to_thorns(live, rid, board)
            if moved is None:
                return {"error": "regime THORNS NON INSTALLE : aucune tuile Thorns marchable "
                                 "atteinte par la cible -- le cumul EffectBonus%/stat-mod DEFENSE "
                                 "n'est pas exerce et ce bras ne prouverait rien"}
        my_player = None
        for _turn in range(24):
            dec = live.rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
            units = dec.get("units") or []
            champ = next((u for u in units if u.get("visualId") == ATTACKER and u.get("alive")), None)
            tgt = next((u for u in units if u.get("visualId") == TARGET and u.get("alive")), None)
            if champ is None or tgt is None:
                return {"error": "unite manquante (build KO)"}
            if my_player is None:
                my_player = champ.get("owner")
            if dec.get("currentPlayer") != my_player:
                live.rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
                continue
            ctile, ttile = utile(champ), utile(tgt)
            dist = _bfs(board, ttile)
            if ctile in board.neighbours(ttile):
                return _measure(live, rid, board, tgt, champ, None, _say)
            mt = live.rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
            cmt = next((x for x in (mt.get("units") or []) if x.get("unitId") == champ["id"]), None)
            reach = {board.id_at(t["col"], t["row"]): (t["col"], t["row"])
                     for t in ((cmt or {}).get("tiles") or [])}
            adj = [(tid, cr) for tid, cr in reach.items() if tid in board.neighbours(ttile)]
            if adj:
                _tid, (col, row) = adj[0]
                return _measure(live, rid, board, tgt, champ, (col, row), _say)
            pool = [tid for tid in reach if tid in dist]
            if not pool:
                live.rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
                continue
            best = min(pool, key=lambda t: dist[t])
            col, row = reach[best]
            live.rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": champ["id"], "to": {"col": col, "row": row}}}, 40)
            live.rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
        return {"error": f"{ATTACKER} n'a pas atteint {TARGET} en 24 tours"}
    finally:
        live.rpc("disposeRunner", {"runnerId": rid}, 20)


def _measure(live, rid, board, tgt, champ, move_to, _say):
    att, tid = champ["id"], tgt["id"]
    if move_to is not None:
        live.rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": att, "to": {"col": move_to[0], "row": move_to[1]}}}, 40)
    dv2 = live.rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob2 = live.rpc("observeBattle", {"runnerId": rid}, 40)
    a2 = next((u for u in (dv2.get("units") or []) if u.get("id") == att), None)
    norm = next((ab for ab in ((a2 or {}).get("abilities") or []) if ab.get("kind") == "normal"), None)
    if norm is None:
        return {"error": "pas d'attaque normale"}
    snap2 = live.rpc("combatSnapshot", {"runnerId": rid}, 40)
    state = load_state(dv2, ob2, snap2, board=board)
    te = state.get_entity(tid)
    hc = te.get_component(HealthComponent) if te is not None else None
    if hc is None or hc.hp is None:
        return {"error": "cible introuvable offline"}
    active = state.effects.active_effects(tid, {"hp": hc.hp}) if state.effects is not None else []
    ns_names = [getattr(ef, "name", "?") for ef in active if "Nightshroud" in (getattr(ef, "name", "") or "")]
    dmods, _ = defender_modifiers(state, tid, hc.hp, is_melee=True, damage_profile=None, attacker_id=att)
    hp_before = hc.hp

    s0 = live.rpc("dumpRng", {"runnerId": rid}, 30)
    if not _ok(s0):
        return {"error": "dumpRng KO"}
    state.rng = _seed_rng(s0)
    runner = Runner(state).install_default_handlers(20)
    res = live.rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": att, "targetId": tid, "abilityType": norm["id"]}}, 40)
    s1 = live.rpc("dumpRng", {"runnerId": rid}, 30)
    a0 = (res.get("actions") or [{}])[0]
    if not (_ok(res) and a0.get("ok")):
        return {"error": f"attaque live KO: {str(res)[:160]}"}

    live_hits = []
    for e in (a0.get("events") or []):
        td = _tags(e)
        if td.get("Target_Id") == tid and "Amount" in td and td.get("Active_Ability_Type") == norm["id"]:
            live_hits.append(td)
    live_after = next((u.get("hp") for u in (res.get("units") or []) if u.get("squadId") == tid), None)

    mti_off_before = state.rng.mti
    trace = _install_bounds_trace()
    runner.apply(AttackUnitMessage(att, tid))
    _restore_bounds_trace()
    rr = runner.damage_handler.last or {}
    off_after = state.get_entity(tid).get_component(HealthComponent).hp
    off_draws = state.rng.mti - mti_off_before          # le port ne regenere pas sur 6 coups

    out = {
        "rng0": {"mt": list(s0["mt"]), "mti": int(s0["mti"])},
        "hp_before": hp_before, "live_after": live_after, "off_after": off_after,
        "live_ph": [t.get("Amount") for t in live_hits],
        "off_ph": rr.get("per_hit"),
        "live_tags": live_hits,
        "off_stage": {k: rr.get(k) for k in
                      ("hits", "base", "pierce", "armor", "after_hit", "clean_min", "clean_max",
                       "did_crit", "did_block", "did_evade", "crits", "rolls", "total")},
        "flat_reductions": list(dmods.flat_reductions),
        "def_mods": repr(dmods),
        "ns_names": ns_names,
        "native_draws": _rng_advance(s0, s1) if _ok(s1) else None,
        "off_draws": off_draws,
        "bounds_trace": list(trace),
    }
    if _say:
        _say("=== #462-r4d decomposition Nightshroud ===")
        _say(f"  ns_effects        : {out['ns_names']}")
        _say(f"  flat_reductions   : {out['flat_reductions']}")
        _say(f"  hp_before         : {hp_before}   live_after={live_after}  off_after={off_after}")
        _say(f"  live per-hit      : {out['live_ph']}")
        _say(f"  off  per-hit      : {out['off_ph']}")
        _say(f"  off stage         : {out['off_stage']}")
        _say(f"  PRNG natif tire   : {out['native_draws']}   port tire : {off_draws}")
        for i, t in enumerate(live_hits):
            keep = {k: v for k, v in t.items() if k not in ("Target_Id", "Active_Ability_Type")}
            _say(f"  live hit[{i}]      : {keep}")
        _say(f"  def_mods          : {out['def_mods']}")
        for st in out["bounds_trace"]:
            _say(f"  [etage] {st[0]}({', '.join(st[1])}{'' if not st[2] else ', ' + str(st[2])}) -> {st[3]}")
    return out


def solve_bounds(rng0: dict, live_ph: list, max_range: int = 8000):
    """QUELLES BORNES le natif a-t-il tirees ? -- inversion du tirage, a etat PRNG connu.

    Le coup d'une attaque normale est UN `next_internal(lo, hi+1)` (modulo facon Java sur
    `genrand>>1`), donc la suite des `genrand` est ENTIEREMENT determinee par `rng0` : pour une
    largeur `R` donnee, les 6 offsets sont calculables, et `lo` se deduit du PREMIER coup live.
    Il ne reste qu'a balayer `R` (6000 candidats, pas 6000x6000) et a exiger les SIX egalites.

    Rend la liste des `(lo, hi)` compatibles avec les six valeurs LIVE. Vide = aucune paire de
    bornes CONSTANTE ne les explique (les bornes varient d'un coup a l'autre)."""
    out = []
    for R in range(1, max_range + 1):
        rng = _seed_rng(rng0)
        offs = [rng.next_internal(0, R) for _ in live_ph]
        lo = live_ph[0] - offs[0]
        if lo < 0:
            continue
        if all(lo + o == v for o, v in zip(offs, live_ph)):
            out.append((lo, lo + R - 1))
    return out


def bounds(r: dict) -> tuple:
    """Bornes (lo, hi) OFFLINE du coup non-crite, relues du resultat du runner."""
    hits = max(1, r["off_stage"]["hits"] or 1)
    return ((r["off_stage"]["clean_min"] or 0) // hits, (r["off_stage"]["clean_max"] or 0) // hits)


def native_bounds(r: dict):
    """Bornes NATIVES, inversees du tirage a etat PRNG connu. `None` si aucune paire constante."""
    sol = solve_bounds(r["rng0"], r["live_ph"])
    return sol[0] if len(sol) == 1 else (sol or None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--solve", action="store_true",
                    help="inverse aussi les bornes du tirage NATIF (cf. solve_bounds)")
    ap.add_argument("--attack", type=int, default=None,
                    help="force la stat DAMAGE de l'attaquant (levier du balayage)")
    ap.add_argument("--thorns", action="store_true",
                    help="GENERALISATION : amene la cible sur une tuile Thorns -> les DEUX canaux "
                         "defenseur (EffectBonus%% et stat-mod DEFENSE) sur le meme coup")
    ap.add_argument("--sweep", default=None,
                    help="balayage : liste de stats DAMAGE separees par des virgules. Pour chaque "
                         "valeur, imprime bornes OFFLINE vs NATIVES -- le desaccord SEPARE les "
                         "modeles d'arrondi que le cas nominal ne distingue pas.")
    a = ap.parse_args()
    if a.sweep:
        rows, bad = [], 0
        for v in [int(x) for x in a.sweep.split(",") if x.strip()]:
            r = run(seed=a.seed, board_id=a.board, verbose=False, attack=v, thorns=a.thorns)
            if "error" in r:
                print(f"  attack={v:<6} ERROR: {r['error'][:120]}")
                bad += 1
                continue
            off, nat = bounds(r), native_bounds(r)
            ok = (nat == off)
            bad += 0 if ok else 1
            print(f"  attack={v:<6} base={r['off_stage']['base']:<6} "
                  f"pierce={r['off_stage']['pierce']:<4} armor={r['off_stage']['armor']:<6} "
                  f"OFFLINE={off}  NATIF={nat}  {'OK' if ok else 'DIVERGE'}")
            rows.append((v, off, nat))
        print(f"VERDICT: {len(rows) - bad if rows else 0}/{len(rows)} bases bit-exactes")
        return 0 if bad == 0 else 1
    r = run(seed=a.seed, board_id=a.board, verbose=True, attack=a.attack, thorns=a.thorns)
    if "error" in r:
        print("[probe] ERROR:", r["error"])
        return 2
    if a.solve:
        print(f"  bornes OFFLINE    : {bounds(r)}")
        print(f"  bornes NATIVES    : {native_bounds(r) or 'AUCUNE paire constante'}")
    print("VERDICT:", "BIT-EXACT" if r["off_ph"] == r["live_ph"] else "DIVERGE")
    return 0 if r["off_ph"] == r["live_ph"] else 1


if __name__ == "__main__":
    sys.exit(main())
