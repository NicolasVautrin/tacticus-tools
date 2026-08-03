"""#462-r4a -- DECOMPOSITION PAR ETAGE du `+1` par coup de `test_terrifying_defense_live.py`.

Le rouge : attaque MELEE de `necroDestroyer` sur `eldarMauganRa` (porteur du trait `Terrifying`,
donc de l'effet `Terrifying_ExtraDefense` = `-30 %` de degat MELEE recu). Sur SIX coups, le port
rend systematiquement `live - 1`. Les bases different d'un coup a l'autre, donc ce n'est pas un
facteur : c'est un etage d'ARRONDI.

Ce probe ne recolle AUCUN scalaire. Il instrumente les DEUX patch-points du vecteur COMBAT normale
(`engine/runner/operations/damage_ops/normal.py` les nomme explicitement) :

    IdunBattle.Core.Services.DamagePrediction$$GetBaseDamageFix64            (bornes de base)
      -> IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers
           -> IdunBattle.Core.Services.DamagePrediction$$GetBaseDamageWithFixedPiercedArmor
                -> StaticBattleRules.Damage$$GetDamageWithPiercing           (percage/armure)
           -> IdunBattle.Core.Services.DamageCalculations$$ApplyCappedModifiers      (x2, capees)
           -> IdunBattle.Core.Services.DamageCalculations$$CalculateBaseDamageWithModifiers (x2, Round)

et imprime le Fix64 EXACT (raw) en entree et en sortie de chaque etage, pour la borne MIN et la
borne MAX. La sortie native n'est pas devinee : le tirage natif est `Next(min, max+1)` sur le MEME
RNG que le port (dumpRng), donc `live_ph[i] - off_ph[i]` constant sur N coups mesure directement le
DECALAGE DES BORNES -- c'est la seule inference faite ici, et elle est explicitee.

Usage :
    python scripts/python/probe_462_r4a_terrifying_rounding.py --state-file <chemin ABSOLU>
    ... [--attacker necroDestroyer] [--target eldarMauganRa] [--seed 777] [--board MC1_67]
    ... [--range 1] [--rounds 3]

ASCII only.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import uuid
from collections import deque
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import hexgeo                                                    # noqa: E402
from rl_collect_batch import _resolve_session, _rpc              # noqa: E402
from engine.services import fix64 as _fx                         # noqa: E402

ROOT = Path(_HERE).resolve().parents[1]

ATTACKER = "necroDestroyer"      # melee multi-coups, PAS de bonus gate has_moved -> replay propre
TARGET = "eldarMauganRa"         # carrier Terrifying (effet Terrifying_ExtraDefense capte live)
BOARD = "MC1_67"
SEED = "777"


class MontageError(RuntimeError):
    pass


def _r(sid, method, body, timeout=60):
    """RPC DEBALLE : le transport rend `{"result": ...}` quand le hook repond, l'enveloppe brute
    sinon (`{"error": ...}`). Les appelants lisent la charge utile, comme la fixture `rpc`."""
    r = _rpc(sid, method, [body], timeout=timeout)
    if isinstance(r, dict) and "result" in r and len(r) == 1:
        return r["result"]
    return r


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


# --------------------------------------------------------------------------- montage


def _build(state: Path, board: str, seed: str, p_units: str, a_units: str,
           cap_wait_s: int = 900, poll_s: int = 20, armor_target: int | None = None,
           hp: int | None = None):
    """Build avec ATTENTE du cap MAX_RUNNERS (session partagee entre agents : un refus de cap
    n'est pas un echec du scenario -- cf. runner.md §3).

    `hp` : PV forces des deux camps. INDISPENSABLE des qu'on DEPLACE les unites sur plusieurs
    tours -- sinon la cible arrive entamee et la prediction native est ECRETEE par la sante
    restante (`FillUpStatComponent.MaxReduceByMinimum`), ce qui rend l'oracle inexploitable."""
    args = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
            "--state-file", str(state), "--board", board, "--roster", "1",
            "--p-units", p_units, "--a-units", a_units]
    if armor_target is not None:
        args += ["--armor-target", str(armor_target)]
    if hp is not None:
        args += ["--hp-target", str(hp), "--hp-player", str(hp)]
    waited = 0.0
    while True:
        state.unlink(missing_ok=True)
        p = subprocess.run(args, cwd=str(Path(_HERE)), capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if state.exists():
            return json.loads(state.read_text())["runnerId"]
        out = (p.stderr or p.stdout or "")
        if ("runner cap reached" not in out and "runner creation paused" not in out) \
                or waited >= cap_wait_s:
            raise MontageError(f"build KO: {out[-500:]}")
        print(f"  cap/drain, attente {poll_s}s ({waited:.0f}/{cap_wait_s})")
        time.sleep(poll_s)
        waited += poll_s


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


def _tiles_at(board, center, r):
    return {tid for tid, d in _bfs(board, center).items() if d == r}


def _drive(sid, rid, attacker, target, want_range, rounds=30):
    """Amene `attacker` a distance BFS EXACTE `want_range` de `target`. Renvoie (board, dv, att, tgt)."""
    from engine.entities.pathfinding.board import Board
    bg = _r(sid, "boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and "tiles" in bg):
        raise MontageError(f"boardGraph indispo: {str(bg)[:300]}")
    board = Board(bg["tiles"], adjacency="native_sym")

    def utile(u):
        p = u.get("pos") or {}
        return board.id_at(p.get("col"), p.get("row")) if "col" in p else None

    my_player = None
    for _turn in range(rounds):
        dec = _r(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        if not _ok(dec):
            raise MontageError("decisionView KO")
        units = dec.get("units") or []
        att = next((u for u in units if u.get("visualId") == attacker and u.get("alive")), None)
        tgt = next((u for u in units if u.get("visualId") == target and u.get("alive")), None)
        if att is None or tgt is None:
            raise MontageError(f"unite manquante (att={att is not None} tgt={tgt is not None})")
        if my_player is None:
            my_player = att.get("owner")
        if dec.get("currentPlayer") != my_player:
            _r(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
            continue
        ctile, ttile = utile(att), utile(tgt)
        want_tiles = _tiles_at(board, ttile, want_range)
        if ctile in want_tiles:
            return board, att, tgt
        mt = _r(sid, "aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
        cmt = next((x for x in (mt.get("units") or []) if x.get("unitId") == att["id"]), None)
        reach = {board.id_at(t["col"], t["row"]): (t["col"], t["row"])
                 for t in ((cmt or {}).get("tiles") or [])}
        adj = [(tid, cr) for tid, cr in reach.items() if tid in want_tiles]
        if adj:
            _tid, (col, row) = adj[0]
            _r(sid, "applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": att["id"], "to": {"col": col, "row": row}}}, 40)
            dec2 = _r(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
            u2 = dec2.get("units") or []
            return (board,
                    next(u for u in u2 if u.get("id") == att["id"]),
                    next(u for u in u2 if u.get("id") == tgt["id"]))
        dist = _bfs(board, ttile)
        pool = [tid for tid in reach if tid in dist]
        if not pool:
            _r(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
            continue
        best = min(pool, key=lambda t: dist[t])
        col, row = reach[best]
        _r(sid, "applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": att["id"], "to": {"col": col, "row": row}}}, 40)
        _r(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
    raise MontageError(f"{attacker} n'a pas atteint {target} a range {want_range}")


# --------------------------------------------------------------------------- etages


def _fmt(raw) -> str:
    """Raw Fix64 -> '<valeur exacte> (raw=<n>)' en ASCII."""
    if raw is None:
        return "None"
    return "%.9f (raw=%d)" % (raw / float(_fx.ONE), raw)


def _instrument():
    """Enveloppe les DEUX patch-points nommes par `damage_ops/normal.py` et renvoie (restore, trace).

    On n'ecrit PAS de logique : on observe les entrees/sorties reelles du vecteur COMBAT normale,
    exactement la ou il compose `apply_pierce_and_modifiers` (face ATTAQUANT + les deux `Round` de
    `CalculateBaseDamageWithAllModifiers`) puis `apply_all_modifiers` (face DEFENSEUR)."""
    from engine.runner.operations.damage_ops import normal as N
    trace: list[dict] = []
    orig_ap = N.apply_pierce_and_modifiers
    orig_am = N.apply_all_modifiers

    def wrap_ap(value, pierce_pct=100, armor=0, mods=None, hit_mult=1,
                attacker_additive_pre=False):
        out = orig_ap(value, pierce_pct, armor, mods, hit_mult, attacker_additive_pre)
        trace.append({"stage": "pierce+attacker", "in": value, "pierce": pierce_pct,
                      "armor": armor,
                      "mods_pct": list(getattr(mods, "pct_list", []) or []),
                      "mods_add": getattr(mods, "additive", 0),
                      "mods_pierce": getattr(mods, "extra_pierce", 0),
                      "mods_pct_def": list(getattr(mods, "pct_list_defender", []) or []),
                      "mult_att": float(getattr(mods, "multiplicative", 1.0) or 1.0),
                      "mult_def": float(getattr(mods, "multiplicative_defender", 1.0) or 1.0),
                      "hit_mult": hit_mult, "add_pre": attacker_additive_pre,
                      "out_raw": _fx.from_number(out)})
        return out

    def wrap_am(value, mods, round_materialize=False):
        out = orig_am(value, mods, round_materialize)
        trace.append({"stage": "defender", "in_raw": _fx.from_number(value),
                      "def_pct": list(getattr(mods, "pct_list", []) or []),
                      "def_mult": float(getattr(mods, "multiplicative", 1.0) or 1.0),
                      "def_add": getattr(mods, "additive", 0),
                      "round_mat": round_materialize, "out": out})
        return out

    N.apply_pierce_and_modifiers = wrap_ap
    N.apply_all_modifiers = wrap_am

    def restore():
        N.apply_pierce_and_modifiers = orig_ap
        N.apply_all_modifiers = orig_am
    return restore, trace


def _decompose(entry: dict) -> dict:
    """Re-joue A LA MAIN les sous-etages de `apply_pierce_and_modifiers` pour l'entree tracee, en
    Fix64 EXACT, et rend le raw apres CHACUN. Mirror LU de
    `IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers`."""
    from engine.services.static_battle_rules import get_damage_with_piercing
    from engine.services.damage_modifiers import (apply_pct_entries,
                                                  calculate_base_damage_with_modifiers)
    pierce_eff = max(0, min(100, entry["pierce"] + entry["mods_pierce"]))
    d = entry["in"]
    steps = [("base", _fx.from_number(d))]
    for _ in range(max(1, entry["hit_mult"])):
        d = get_damage_with_piercing(d, pierce_eff, entry["armor"])
    steps.append(("pierced", _fx.from_number(d)))
    d = apply_pct_entries(d, list(entry["mods_pct"]) + list(entry["mods_pct_def"]))
    steps.append(("chaine %-list (1+2)", _fx.from_number(d)))
    d = calculate_base_damage_with_modifiers(d, entry["mult_att"])
    steps.append(("Multiplier ATT (etape 3)", _fx.from_number(d)))
    d = calculate_base_damage_with_modifiers(d, entry["mult_def"])
    steps.append(("Multiplier DEF (etape 4)", _fx.from_number(d)))
    return {"pierce_eff": pierce_eff, "steps": steps}


# --------------------------------------------------------------------------- scenario


def run(attacker=ATTACKER, target=TARGET, board_id=BOARD, seed=SEED, want_range=1,
        state_file=None, runner=None, verbose=True) -> dict:
    sid = _resolve_session()
    state = Path(state_file) if state_file else \
        ROOT / "logs" / "runners" / f"probe462r4a-{uuid.uuid4().hex[:8]}.json"
    state.parent.mkdir(parents=True, exist_ok=True)
    rid = int(runner) if runner else _build(state, board_id, seed, attacker, target)
    if verbose:
        print(f"runner {rid} board {board_id} seed {seed} : {attacker} -> {target}")
    try:
        from engine.runner.snapshot import load_state
        from engine.runner.runner import Runner
        from engine.runner.messages import AttackUnitMessage
        from engine.runner.prng import IntBasedMersenneTwister
        from engine.runner.components import HealthComponent

        board, att_u, tgt_u = _drive(sid, rid, attacker, target, want_range)
        att, tid = att_u["id"], tgt_u["id"]
        dv = _r(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        ob = _r(sid, "observeBattle", {"runnerId": rid}, 40)
        snap = _r(sid, "combatSnapshot", {"runnerId": rid}, 40)
        a2 = next((u for u in (dv.get("units") or []) if u.get("id") == att), None)
        norm = next((ab for ab in ((a2 or {}).get("abilities") or [])
                     if ab.get("kind") == "normal"), None)
        if norm is None:
            raise MontageError("pas d'attaque normale sur l'attaquant")
        st = load_state(dv, ob, snap, board=board)
        te = st.get_entity(tid)
        hc = te.get_component(HealthComponent) if te is not None else None
        if hc is None or hc.hp is None:
            raise MontageError("cible introuvable offline")
        hp_before = hc.hp
        # ORACLE DE LA FACE PREDICTION, pris AVANT l'attaque : le MEME couple, la MEME ability,
        # mais l'autre appelant natif de `CalculateBaseDamageWithAllModifiers`
        # (`IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw`). C'est le SECOND cas
        # discriminant : si le `+1` du combat vient bien du gate `attackModifiers.HasValue`, la
        # prediction -- ou l'appelant le construit -- doit rendre l'AUTRE valeur.
        pred = _r(sid, "aiPlaybookPredict", {"runnerId": rid, "unitId": att, "targetId": tid,
                                             "abilityType": norm["id"]}, 60) or {}
        pev = None
        if pred.get("ok"):
            evs = pred.get("events") or []
            pev = next((e for e in evs if e.get("targetId") == tid), evs[0] if evs else None)
        s0 = _r(sid, "dumpRng", {"runnerId": rid}, 30)
        if not _ok(s0):
            raise MontageError("dumpRng KO")

        def _seeded():
            rng = IntBasedMersenneTwister()
            rng.mt = list(s0["mt"])
            rng.mti = s0["mti"]
            return rng

        # --- LIVE (le natif tire dans SES bornes, sur CE meme etat de RNG)
        res = _r(sid, "applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": att, "targetId": tid,
            "abilityType": norm["id"]}}, 40)
        a0 = (res.get("actions") or [{}])[0]
        if not (_ok(res) and a0.get("ok")):
            raise MontageError(f"attaque live KO: {str(res)[:200]}")
        live_ph, did_evade = [], False
        for e in (a0.get("events") or []):
            td = e.get("tags")
            if not td:
                continue
            td = json.loads(td) if isinstance(td, str) else td
            if td.get("Target_Id") == tid and "Amount" in td \
                    and td.get("Active_Ability_Type") == norm["id"]:
                live_ph.append(td.get("Amount"))
                did_evade = did_evade or bool(td.get("Attack_DidEvade"))
        live_after = next((u.get("hp") for u in (res.get("units") or [])
                           if u.get("squadId") == tid), None)

        # --- OFFLINE, MEME RNG, avec les patch-points instrumentes
        restore, trace = _instrument()
        try:
            st.rng = _seeded()
            rn = Runner(st).install_default_handlers(20)
            rn.apply(AttackUnitMessage(att, tid))
            rr = rn.damage_handler.last
        finally:
            restore()
        off_ph = (rr or {}).get("per_hit")
        off_after = st.get_entity(tid).get_component(HealthComponent).hp

        out = {"rid": rid, "attacker": attacker, "target": target, "board": board_id,
               "seed": seed, "hp_before": hp_before, "live_after": live_after,
               "off_after": off_after, "live_ph": live_ph, "off_ph": off_ph,
               "did_evade": did_evade, "trace": trace, "rr": rr, "native_prediction": pev}
        if verbose:
            _report(out)
        return out
    finally:
        if not runner:
            _r(sid, "disposeRunner", {"runnerId": rid}, 30)
            try:
                state.unlink()
            except OSError:
                pass


def _report(out: dict) -> None:
    live, off = out["live_ph"], out["off_ph"]
    print(f"\nlive per-hit = {live}")
    print(f"off  per-hit = {off}")
    if live and off and len(live) == len(off):
        deltas = sorted({a - b for a, b in zip(live, off)})
        print(f"delta (live - off) = {deltas}"
              + ("   <- CONSTANT sur tous les coups => les BORNES sont decalees d'autant"
                 if len(deltas) == 1 else "   <- NON constant : ce n'est pas un decalage de bornes"))
    # Les deux premieres entrees `pierce+attacker` sont les bornes MIN et MAX de la plage NON-crit
    pa = [t for t in out["trace"] if t["stage"] == "pierce+attacker"]
    da = [t for t in out["trace"] if t["stage"] == "defender"]
    for k, (a, b) in enumerate(zip(pa[:2], da[:2])):
        label = "MIN" if k == 0 else "MAX"
        dec = _decompose(a)
        print(f"\n--- borne {label} : base={a['in']} pierce={a['pierce']}(+{a['mods_pierce']}"
              f"={dec['pierce_eff']}) armure={a['armor']} hit_mult={a['hit_mult']}")
        print(f"    mods ATTAQUANT pct={a['mods_pct']} additif={a['mods_add']}")
        print(f"    mods DEFENSEUR pct={b['def_pct']} additif={b['def_add']}"
              f" round_mat={b['round_mat']}")
        for name, raw in dec["steps"]:
            print(f"      {name:26s} {_fmt(raw)}")
        print(f"      {'--> sortie apply_all_mods':26s} {b['out']}")
    print(f"\nPV cible : avant={out['hp_before']} live={out['live_after']} off={out['off_after']}")
    pev = out.get("native_prediction")
    if isinstance(pev, dict):
        keys = [k for k in pev
                if any(s in k.lower() for s in ("dmg", "damage", "hits", "min", "max"))]
        print("\nPREDICTION NATIVE (aiPlaybookPredict, MEME couple/ability) : "
              + ", ".join(f"{k}={pev[k]}" for k in sorted(keys)))
    else:
        print("\nPREDICTION NATIVE : indisponible (aiPlaybookPredict KO)")


# --------------------------------------------------------------------------- modeles en lice


def _models(p_raw: int, mults) -> dict:
    """Les QUATRE modeles en lice pour l'etage `percage -> face DEFENSEUR`, tous en Fix64 EXACT.

      A `round_inter`  Round(Round(P) x m)  -- le port depuis #446-r2 (etape 3 presente)
      B `no_inter`     Round(P x m)         -- le port d'AVANT #446-r2
      C `ceil`         ceil(P x m)          -- le modele que l'identite de surface suggere
      D `sub_trunc`    P - floor(P x (1-m)) -- la reduction ecrite en SOUSTRACTION tronquee

    `mults` = la %-list DEFENSEUR (liste de (mult, cap)); un cap la rend inapplicable ici (aucun
    porteur n'en pose, cf. `#446-r2-r1`). Chaque modele rend l'ENTIER final (matérialisation
    incluse), pour etre compare tel quel a l'oracle natif."""
    ms = [_fx.mult_raw_from_float(m) for m, _cap in mults]

    def chain(v_raw, pre_round: bool):
        if pre_round:
            v_raw = _fx.round_raw(v_raw, 1)
        for m in ms:
            v_raw = _fx.mul(v_raw, m)
        return v_raw

    a = _fx.to_int(_fx.round_raw(chain(p_raw, True), 1))
    b = _fx.to_int(_fx.round_raw(chain(p_raw, False), 1))
    x = chain(p_raw, False)
    c = _fx.to_int(x) + (1 if (x & (_fx.ONE - 1)) else 0)
    d = p_raw
    for m in ms:
        d = d - (_fx.to_int(_fx.mul(d, _fx.ONE - m)) << 32)
    return {"A_round_inter": a, "B_no_inter": b, "C_ceil": c, "D_sub_trunc": _fx.to_int(d)}


def sweep(armors, attacker=ATTACKER, target=TARGET, board_id=BOARD, seed=SEED,
          state_file=None, verbose=True) -> dict:
    """BALAYAGE de l'armure de la cible. L'enjeu n'est pas l'armure : c'est la BRANCHE de
    `StaticBattleRules.Damage$$GetDamageWithPiercing` (`max(0, d - armure, d x percage)`). Armure
    BASSE -> la branche `d - armure` gagne et le percage sort ENTIER, donc `Round(P) == P` et les
    modeles A et B COINCIDENT tandis que C et D s'en separent franchement. Armure HAUTE -> branche
    percage, sortie FRACTIONNAIRE, A se separe de B. Un seul balayage tranche donc les quatre.

    Oracle = la PREDICTION native (`aiPlaybookPredict` -> `PredictAttackRaw`), lue par coup
    (`healthDmgMin / appliedHits`). Aucune attaque n'est jouee : l'oracle suffit."""
    sid = _resolve_session()
    state = Path(state_file) if state_file else \
        ROOT / "logs" / "runners" / f"probe462r4a-sweep-{uuid.uuid4().hex[:8]}.json"
    state.parent.mkdir(parents=True, exist_ok=True)
    rows, score = [], {"A_round_inter": 0, "B_no_inter": 0, "C_ceil": 0, "D_sub_trunc": 0}
    total = 0
    for armor in armors:
        rid = None
        try:
            rid = _build(state, board_id, seed, attacker, target, armor_target=armor)
            row = _one_sweep_point(sid, rid, attacker, target, armor)
        except MontageError as exc:
            rows.append({"armor": armor, "error": str(exc)})
            if verbose:
                print(f"  armure {armor}: MONTAGE KO -- {exc}")
            continue
        finally:
            if rid is not None:
                _r(sid, "disposeRunner", {"runnerId": rid}, 30)
        rows.append(row)
        for bound in ("min", "max"):
            nat = row[f"native_{bound}"]
            if nat is None:
                continue
            total += 1
            for k, v in row[f"models_{bound}"].items():
                if v == nat:
                    score[k] += 1
        if verbose:
            print(f"  armure {armor:>5} pierce={row['pierce']} defmods={row['def_pct']}")
            for bound in ("min", "max"):
                print(f"    borne {bound.upper():3s} base={row['base_' + bound]:>6}"
                      f" P={_fmt(row['p_raw_' + bound])}"
                      f" natif={row['native_' + bound]}  " +
                      "  ".join(f"{k}={v}" for k, v in sorted(row[f"models_{bound}"].items())))
    try:
        state.unlink()
    except OSError:
        pass
    if verbose:
        print(f"\nSCORE sur {total} bornes mesurees :")
        for k, v in sorted(score.items(), key=lambda kv: -kv[1]):
            print(f"  {k:16s} {v}/{total}")
    return {"rows": rows, "score": score, "total": total}


def _one_sweep_point(sid, rid, attacker, target, armor) -> dict:
    from engine.runner.snapshot import load_state
    from engine.runner.runner import Runner
    from engine.runner.messages import AttackUnitMessage
    from engine.runner.components import HealthComponent
    board, att_u, tgt_u = _drive(sid, rid, attacker, target, 1)
    att, tid = att_u["id"], tgt_u["id"]
    dv = _r(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = _r(sid, "observeBattle", {"runnerId": rid}, 40)
    snap = _r(sid, "combatSnapshot", {"runnerId": rid}, 40)
    a2 = next((u for u in (dv.get("units") or []) if u.get("id") == att), None)
    norm = next((ab for ab in ((a2 or {}).get("abilities") or [])
                 if ab.get("kind") == "normal"), None)
    if norm is None:
        raise MontageError("pas d'attaque normale")
    pred = _r(sid, "aiPlaybookPredict", {"runnerId": rid, "unitId": att, "targetId": tid,
                                         "abilityType": norm["id"]}, 60) or {}
    evs = (pred.get("events") or []) if pred.get("ok") else []
    pev = next((e for e in evs if e.get("targetId") == tid), evs[0] if evs else None)
    if not isinstance(pev, dict):
        raise MontageError("aiPlaybookPredict sans event pour la cible")
    hits = int(pev.get("appliedHits") or 0)
    if hits <= 0:
        raise MontageError(f"appliedHits invalide : {pev.get('appliedHits')}")

    def per_hit(total_):
        if total_ is None or total_ % hits:
            return None                      # non divisible -> agregation impure, on n'infere pas
        return total_ // hits

    st = load_state(dv, ob, snap, board=board)
    if st.get_entity(tid).get_component(HealthComponent) is None:
        raise MontageError("cible introuvable offline")
    from engine.runner.prng import IntBasedMersenneTwister
    s0 = _r(sid, "dumpRng", {"runnerId": rid}, 30)
    if not _ok(s0):
        raise MontageError("dumpRng KO")
    st.rng = IntBasedMersenneTwister()
    st.rng.mt = list(s0["mt"])
    st.rng.mti = s0["mti"]
    restore, trace = _instrument()
    try:
        rn = Runner(st).install_default_handlers(20)
        rn.apply(AttackUnitMessage(att, tid))
    finally:
        restore()
    pa = [t for t in trace if t["stage"] == "pierce+attacker"][:2]
    da = [t for t in trace if t["stage"] == "defender"][:2]
    if len(pa) < 2 or len(da) < 2:
        raise MontageError("trace incomplete (vecteur normale non traverse)")
    # La face DEFENSEUR vit desormais DANS l'accumulateur attaquant (`pct_list_defender` /
    # `multiplicative_defender`, fusionnes par `AttackDamageOperation._apply_defender_flat_
    # reductions`) ; `apply_all_modifiers` n'en voit plus que le residu. La CHAINE mesuree est donc
    # l'union, dans l'ordre natif (etapes 1 puis 2).
    chain = list(pa[0]["mods_pct"]) + list(pa[0]["mods_pct_def"]) + list(da[0]["def_pct"])
    out = {"armor": armor, "hits": hits, "pierce": pa[0]["pierce"],
           "def_pct": list(pa[0]["mods_pct_def"]) + list(da[0]["def_pct"]),
           "att_pct": list(pa[0]["mods_pct"]),
           "mult_att": pa[0]["mult_att"], "mult_def": pa[0]["mult_def"],
           "native_min": per_hit(pev.get("healthDmgMin")),
           "native_max": per_hit(pev.get("healthDmgMax"))}
    for k, (a, b) in zip(("min", "max"), zip(pa, da)):
        dec = _decompose(a)
        p_raw = dict(dec["steps"])["pierced"]
        out[f"base_{k}"] = a["in"]
        out[f"p_raw_{k}"] = p_raw
        out[f"models_{k}"] = _models(p_raw, list(a["mods_pct"]) + list(a["mods_pct_def"])
                                     + list(b["def_pct"]))
        out[f"port_{k}"] = b["out"]
        out[f"chain_{k}"] = chain
    return out


def two_faces(attacker=ATTACKER, target=TARGET, board_id=BOARD, seed=SEED,
              state_file=None, verbose=True) -> dict:
    """LE discriminant restant : les DEUX faces non neutres SUR LE MEME COUP.

    La face DEFENSEUR (`Terrifying_ExtraDefense`, x0.70) et la face ATTAQUANT (bonus d'ELEVATION,
    x1.50, `IdunBattle.Core.Services.DamageCalculations$$CalculateElevationBonusModifier`) ne
    commutent PAS des qu'un `Round` s'intercale. Les unites sont DEPLACEES pour fabriquer la
    configuration (attaquant sur une tuile STRICTEMENT plus haute, et adjacente pour la melee) --
    on ne se contente pas de la geometrie de spawn.

      ordre ATT-puis-DEF  : Round(Round(P x 1.5) x 0.7)
      ordre DEF-puis-ATT  : Round(Round(P x 0.7) x 1.5)

    Sur le percage fractionnaire du montage (P = 435.000000068) ces deux ordres donnent 457 et 458."""
    import probe_124_line_elevation_decision as P124
    from engine.runner.snapshot import load_state
    from engine.runner.runner import Runner
    from engine.runner.messages import AttackUnitMessage
    from engine.runner.prng import IntBasedMersenneTwister
    sid = _resolve_session()
    state = Path(state_file) if state_file else \
        ROOT / "logs" / "runners" / f"probe462r4a-2f-{uuid.uuid4().hex[:8]}.json"
    state.parent.mkdir(parents=True, exist_ok=True)
    rid = _build(state, board_id, seed, attacker, target, hp=90000)
    try:
        elev, walk, _tid = P124._board(sid, rid)
        dv, _pos = P124._positions(sid, rid)
        units = dv.get("units") or []
        mine = [u for u in units if u.get("ctrl") and u.get("alive")]
        cid = next((u["id"] for u in mine if u.get("visualId") == attacker), None)
        myplayer = next((u.get("owner") for u in mine), None)
        tgt = next((u for u in units if u.get("owner") != myplayer and u.get("alive")
                    and u.get("visualId") == target), None)
        if cid is None or tgt is None:
            raise MontageError("roster incomplet")
        # couple ADJACENT (a, t) avec elev[a] > elev[t], les deux walkable
        pair = None
        for a, ea in sorted(elev.items()):
            if not walk.get(a) or ea is None:
                continue
            for t in hexgeo.neighbors(a[0], a[1]):
                if walk.get(t) and elev.get(t) is not None and ea > elev[t]:
                    pair = (a, t)
                    break
            if pair:
                break
        if pair is None:
            raise MontageError("aucun couple adjacent a denivele sur ce board")
        wanted = {cid: pair[0], tgt["id"]: pair[1]}
        if not P124._drive_to(sid, rid, walk, elev, wanted):
            _dv, pos = P124._positions(sid, rid)
            raise MontageError(f"placement incomplet -- voulu {wanted}, obtenu "
                               f"{ {u: pos.get(u) for u in wanted} }")
        P124._give_turn_back(sid, rid, myplayer)
        row = _one_sweep_point(sid, rid, attacker, target, armor=None)
        row["tiles"] = {"attaquant": pair[0], "cible": pair[1],
                        "elev": (elev[pair[0]], elev[pair[1]])}
        if verbose:
            print(f"\n[DEUX FACES] attaquant {pair[0]} elev {elev[pair[0]]} -> cible {pair[1]} "
                  f"elev {elev[pair[1]]}")
            print(f"  modsATT={row['att_pct']}  modsDEF={row['def_pct']}  pierce={row['pierce']}")
            for b in ("min", "max"):
                print(f"  borne {b.upper():3s} base={row['base_' + b]} P={_fmt(row['p_raw_' + b])}"
                      f" natif={row['native_' + b]} port={row['port_' + b]}"
                      f" ordres: " + " ".join(
                          f"{k}={v}" for k, v in sorted(
                              _order_models(row['p_raw_' + b], row['att_pct'],
                                            row['def_pct']).items())))
        return row
    finally:
        _r(sid, "disposeRunner", {"runnerId": rid}, 30)
        try:
            state.unlink()
        except OSError:
            pass


def _order_models(p_raw: int, att, deff) -> dict:
    """Les deux ORDRES possibles, chacun avec son `Round` intercale."""
    def chain(seq):
        v = p_raw
        for group in seq:
            for m, _c in group:
                v = _fx.mul(v, _fx.mult_raw_from_float(m))
            v = _fx.round_raw(v, 1)
        return _fx.to_int(v)
    return {"ATT_puis_DEF": chain([att, deff]), "DEF_puis_ATT": chain([deff, att]),
            "fusionne_1_round": chain([list(att) + list(deff)])}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file")
    ap.add_argument("--runner")
    ap.add_argument("--attacker", default=ATTACKER)
    ap.add_argument("--target", default=TARGET)
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--seed", default=SEED)
    ap.add_argument("--range", type=int, default=1)
    ap.add_argument("--sweep", help="liste d'armures separees par des virgules -> balayage")
    ap.add_argument("--two-faces", action="store_true",
                    help="scenario de GENERALISATION : faces ATTAQUANT et DEFENSEUR non neutres "
                         "sur le meme coup (les unites sont DEPLACEES)")
    a = ap.parse_args()
    if a.two_faces:
        try:
            row = two_faces(attacker=a.attacker, target=a.target, board_id=a.board,
                            seed=a.seed, state_file=a.state_file)
        except MontageError as exc:
            print(f"MONTAGE NON INSTALLE : {exc}")
            return 2
        ok = all(row[f"native_{b}"] == row[f"port_{b}"] for b in ("min", "max"))
        print("\nVERDICT:", "ACCORD" if ok else "DIVERGENCE")
        return 0 if ok else 1
    if a.sweep:
        armors = [int(x) for x in a.sweep.split(",") if x.strip()]
        try:
            r = sweep(armors, attacker=a.attacker, target=a.target, board_id=a.board,
                      seed=a.seed, state_file=a.state_file)
        except MontageError as exc:
            print(f"MONTAGE NON INSTALLE : {exc}")
            return 2
        best = max(r["score"].values()) if r["total"] else 0
        print("\nVERDICT:", "MODELE UNIQUE" if best == r["total"] else "AUCUN MODELE COMPLET")
        return 0 if best == r["total"] else 1
    try:
        r = run(attacker=a.attacker, target=a.target, board_id=a.board, seed=a.seed,
                want_range=a.range, state_file=a.state_file, runner=a.runner)
    except MontageError as exc:
        print(f"MONTAGE NON INSTALLE : {exc}")
        return 2
    ok = r["live_ph"] == r["off_ph"]
    print("\nVERDICT:", "ACCORD" if ok else "DIVERGENCE")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
