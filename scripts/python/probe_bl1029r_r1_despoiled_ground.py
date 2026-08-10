#!/usr/bin/env python
"""Probe #BL-1029r-r1 -- POURQUOI le 10e coup du cast de Drachnyen manque offline.

HYPOTHESE A TESTER (elle CONTREDIT la piste ecartee par la fiche) : le coup additionnel
`LetTheGalaxyBurn` de la 3e attaque (celle de la triggered 1485 `Drachnyen_ExtraAttack`) part LIVE
non pas parce que le `Maybe(33 %)` reussit, mais parce que la cible est DEJA sur une tuile a
status-effect quand cette attaque demarre -- `DespoiledGround` (EffectType 1476), pose a la CLOTURE
de l'attaque NORMALE par le volet 2 de `IdunBattleLogic.Entities.Abilities.Triggered.Loki.
LetTheGalaxyBurn_ResetAbility$$CreateBehaviour`, volet NON PORTE.

Le gate du coup (`IdunBattle.Entities.Effects.Loki.LetTheGalaxyBurnEffect$$CreateAdditionalHits`)
est `OwnerIsCaster & ( TargetHasTileEffect | IsPersistentData )` : la branche gauche rend le coup
CERTAIN. La fiche ecartait cette piste en observant que le `Maybe` est evalue AVANT le gate de
tuile du trigger de POSE, donc consomme son tirage dans les deux regimes -- vrai pour la
CONSOMMATION, mais ca ne dit RIEN du verdict du COUP, qui passe par l'autre branche.

Ce que le probe MESURE (aucune assertion : c'est un probe) :
  1. `tileMeta` de la tuile de la cible AVANT le cast, APRES le cast ;
  2. les effets de l'UNITE cible avant/apres (l'effet va-t-il sur la TUILE ou sur l'UNITE ?) ;
  3. la CASCADE complete du cast, dans l'ordre, pour situer la pose de `DespoiledGround` par
     rapport aux coups de l'extra attack ;
  4. les coups OFFLINE (port) sur le meme etat, pour rejouer l'ecart 9 vs 10.

ASCII only (cp1252).
Usage: python probe_bl1029r_r1_despoiled_ground.py --state-file <ABS> [--seed 777] [--board MC1_67]
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
from engine.runner.snapshot import load_state  # noqa: E402
from engine.runner.runner import Runner  # noqa: E402
from engine.runner.messages import ActiveAbilityMessage  # noqa: E402
from engine.runner.components import HealthComponent  # noqa: E402
from engine.entities.pathfinding.board import Board  # noqa: E402
from engine.runner.prng import IntBasedMersenneTwister  # noqa: E402

PYDIR = Path(__file__).resolve().parent
ABADDON = "blackAbaddon"
ENEMIES = "necroWarden,necroDestroyer,necroOverlord"
DRACHNYEN = 1029


def _seed_rng(s):
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"])
    rng.mti = s["mti"]
    return rng


def _pos(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row"))


def _tags(ev):
    try:
        return json.loads(ev.get("tags") or "{}")
    except Exception:
        return {}


def _cascade(r):
    out = list(r.get("cascade") or [])
    for a in (r.get("actions") or []):
        out += list(a.get("events") or [])
    return out


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--hp-target", default="500000")
    ap.add_argument("--state-file", required=True)
    args = ap.parse_args(argv)

    state_file = Path(args.state_file)
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.unlink(missing_ok=True)
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(args.seed),
         "--state-file", str(state_file), "--board", args.board,
         "--p-units", ABADDON, "--a-units", ENEMIES, "--hp-target", str(args.hp_target)],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not state_file.exists():
        print("[dg] build KO: " + (proc.stderr or proc.stdout or "")[-600:])
        return 2
    rid = json.loads(state_file.read_text())["runnerId"]
    sid = _resolve_session()

    def rpc(m, b, t=90):
        return (_rpc(sid, m, [b], timeout=t).get("result") or {})

    print("[dg] seed=%d board=%s runner=%s" % (args.seed, args.board, rid))
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        board = Board(bg["tiles"], adjacency="native_sym")

        def dview():
            return rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 1}, 150)

        def tile_fx():
            tm = rpc("tileMeta", {"runnerId": rid}, 60)
            return {(t.get("col"), t.get("row")): [e.get("name") for e in (t.get("effects") or [])]
                    for t in (tm.get("tiles") or [])}

        dec = dview()
        cst = next((u for u in (dec.get("units") or [])
                    if u.get("alive") and u.get("visualId") == ABADDON), None)
        if cst is None:
            print("[dg] caster absent")
            return 2
        for _ in range(12):
            if dec.get("currentPlayer") == cst.get("owner"):
                break
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            dec = dview()
        alive = [u for u in (dec.get("units") or []) if u.get("alive")]
        cst = next((u for u in alive if u.get("id") == cst["id"]), None)
        ens = [u for u in alive if u.get("owner") != cst.get("owner")]
        C = _pos(cst)
        occ = {_pos(u) for u in alive} - {C}
        nb = [board.coord(t) for t in sorted(board.by_id)
              if board.walkable(t) and hexgeo.distance(board.coord(t), C) == 1
              and board.coord(t) not in occ]
        if not nb:
            print("[dg] pas de voisin libre")
            return 2
        tgt = ens[0]["id"]
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": tgt, "to": {"col": nb[0][0], "row": nb[0][1]}}}, 90)
        dec = dview()
        alive = [u for u in (dec.get("units") or []) if u.get("alive")]
        cst = next((u for u in alive if u.get("id") == cst["id"]), None)
        tu = next((u for u in alive if u.get("id") == tgt), None)
        T = _pos(tu)
        print("[dg] caster=%s@%s cible=%s@%s" % (cst["id"], C, tgt, T))

        fx_before = tile_fx()
        print("[dg] AVANT: tuile cible %s effets=%s" % (T, fx_before.get(T)))
        print("[dg] AVANT: tuile caster %s effets=%s" % (C, fx_before.get(C)))
        print("[dg] AVANT: effets UNITE cible = %s"
              % json.dumps([e.get("name") for e in (tu.get("effects") or [])])[:400])

        ob = rpc("observeBattle", {"runnerId": rid}, 60)
        snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
        s0 = rpc("dumpRng", {"runnerId": rid}, 30)
        pre_hp = {u["id"]: u.get("hp") for u in alive}
        state = load_state(dec, ob, snap, board=board)
        if s0 and s0.get("mt"):
            state.rng = _seed_rng(s0)

        # --- OFFLINE (port), meme etat, meme RNG ---
        runner = Runner(state).install_default_handlers(20)
        runner.apply(ActiveAbilityMessage(caster_id=cst["id"], target_id=tgt,
                                          ability_type=DRACHNYEN))
        last = runner.ability_handler.last or {}
        e = state.get_entity(tgt)
        hc = e.get_component(HealthComponent) if e is not None else None
        off_dpv = (pre_hp.get(tgt) - hc.hp) if (hc is not None and pre_hp.get(tgt) is not None) else None
        print("[dg] OFFLINE dPV cible = %s" % off_dpv)
        print("[dg] OFFLINE last = %s" % json.dumps(last, default=str)[:2500])

        # --- LIVE ---
        r = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": cst["id"], "targetId": tgt,
            "abilityType": DRACHNYEN}}, 240)
        a0 = ((r or {}).get("actions") or [{}])[0]
        if not a0.get("ok"):
            print("[dg] cast LIVE KO %s" % str(r)[:400])
            return 2
        casc = _cascade(r)
        print("[dg] LIVE cascade (%d events) --- ordre ---" % len(casc))
        for i, ev in enumerate(casc):
            t = _tags(ev)
            keep = {k: v for k, v in t.items()
                    if k in ("Amount", "Target_Id", "Active_Ability_Type", "Triggered_Ability_Type",
                            "Effect_Type", "Effect_Name", "Source_Id", "Tile_Col", "Tile_Row",
                            "UnitStats_RemainingHealth")}
            print("  [%02d] kind=%s src=%s ent=%s %s"
                  % (i, ev.get("kind"), ev.get("source"), ev.get("entity"),
                     json.dumps(keep, default=str)[:260]))

        dec2 = dview()
        tu2 = next((u for u in (dec2.get("units") or []) if u.get("id") == tgt), None)
        fx_after = tile_fx()
        print("[dg] APRES: tuile cible %s effets=%s" % (T, fx_after.get(T)))
        print("[dg] APRES: effets UNITE cible = %s"
              % json.dumps([e.get("name") for e in ((tu2 or {}).get("effects") or [])])[:400])
        print("[dg] APRES: dPV cible LIVE = %s"
              % ((pre_hp.get(tgt) - (tu2 or {}).get("hp"))
                 if (tu2 or {}).get("hp") is not None else None))
        diff = {k: v for k, v in fx_after.items() if (fx_before.get(k) or []) != (v or [])}
        print("[dg] DIFF tile effects (avant -> apres) = %s"
              % json.dumps({str(k): [fx_before.get(k), v] for k, v in diff.items()})[:800])
        return 0
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 60)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
