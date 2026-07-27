"""#162 -- le `StatsComponent` d'une MACHINE OF WAR est ECRASE par `_load_stats_and_effects`,
donc TOUTE variable d'ability MoW indexee par NIVEAU est lue au niveau 1.

CHAINE (mesuree, pas deduite) :
  1. `decisionView.mows[].abilities[]` porte bien `level`/`multiplier` (50 / 140 pour orksRukkatrukk)
     et `engine.runner.snapshot._machine_ability_state` les lit correctement.
  2. `_load_machines` pose donc un `StatsComponent` CORRECT sur l'entite Machine
     (`ctx.active_ability_level = 50`, `ctx.ability_variables_multiplier = 140`).
  3. `_load_stats_and_effects` tourne APRES (`load_state` : `_load_machines` puis
     `_load_stats_and_effects`) et boucle sur `snapshot["units"]` SANS filtrer `entityType`.
     Or le RPC `combatSnapshot` inclut les entites `Machine` (`EntityType.Machine`, #93) --
     l'en-tete de `_load_machine_stats` (et NON de `_load_machines`, l'attribution du dossier
     #162 etait imprecise) affirmait l'inverse (« combatSnapshot n'expose QUE EntityType.Unit ») :
     affirmation PERIMEE.
  4. Pour cette ligne Machine, `unitConfig` vaut `{"error": "visualId introuvable"}` (le registre
     `BattleQuery.GetUnitConfig` est keye par VisualId d'UNITE) -> aucun `abilityVariablesMultiplier`
     -> le `ctx` reconstruit N'A NI niveau NI multiplicateur, et `add_component` REMPLACE celui de
     `_load_machines`.

CONSEQUENCE : `ability_var(<ability MoW>, <var>, level=None)` retombe sur le niveau 1. Toutes les
magnitudes per-level des MoW sont fausses -- `nrOfTiles`, `nrOfRounds`, `minDmg`/`maxDmg`...

Ce probe MESURE la chaine et montre le contre-factuel (re-poser le niveau restaure la valeur
native). Il ne modifie AUCUN fichier du moteur. ASCII-only.

>>> CORRIGE depuis #174 : le probe rend desormais `[verdict] pas d'ecrasement` -- il sert de
    NON-REGRESSION. La preuve de l'INDEX (`level-1`) et la generalisation multi-board vivent dans
    `probe_174_mow_level_index.py` / `probe_174_mow_level_generalize.py`.

    python probe_162_mow_ability_level.py --mow orksRukkatrukk --ability SquigMine --var nrOfTiles
    python probe_162_mow_ability_level.py --mow deathCrawler --ability PlagueburstMortar --var nrOfTiles
    python probe_162_mow_ability_level.py --mow adeptExorcist --ability ThriceBlessedConflagration --var nrOfRounds
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import rl_collect_batch as R

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]


def _rpc(sid, method, body, timeout=120):
    r = R._rpc(sid, method, [body], timeout=timeout)
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mow", default="orksRukkatrukk")
    ap.add_argument("--ability", default="SquigMine")
    ap.add_argument("--var", default="nrOfTiles")
    ap.add_argument("--board", default="C1_02")
    ap.add_argument("--seed", default="4242")
    args = ap.parse_args()

    import gameconfig as GC
    from engine.entities.effects.magnitude import ability_var
    from engine.runner.components import StatsComponent
    from engine.runner.snapshot import load_state, _machine_ability_state

    sid = R._resolve_session()
    state_path = ROOT / "logs" / f"_probe162lvl_{args.mow}.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.unlink(missing_ok=True)
    p = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", args.seed, "--board", args.board,
         "--p-units", "necroDestroyer,necroWarden", "--a-units", "necroDestroyer,necroWarden",
         "--p-mow", args.mow, "--state-file", str(state_path)],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not state_path.exists():
        print("[FAIL] build KO:\n" + (p.stderr or p.stdout or "")[-600:])
        return 2
    rid = json.loads(state_path.read_text())["runnerId"]
    print(f"[ok] runner {rid} mow={args.mow}")

    try:
        dec = _rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True})
        ob = _rpc(sid, "observeBattle", {"runnerId": rid}, 40)
        snap = _rpc(sid, "combatSnapshot", {"runnerId": rid})
        m = next((x for x in (dec.get("mows") or []) if x.get("visualId") == args.mow), None)
        if m is None:
            print("[FAIL] MoW non deployee")
            return 3
        mid = int(m["casterId"])

        # 1. le canal SOURCE est bon
        lvl, mult = _machine_ability_state(m)
        print(f"[1] _machine_ability_state(decisionView.mows) -> level={lvl} multiplier={mult}")

        # 2. la ligne Machine EST dans combatSnapshot (contredit l'en-tete de _load_machines)
        rows = [u for u in (snap.get("units") or []) if u.get("entityType") == 6]
        print(f"[2] combatSnapshot : {len(rows)} ligne(s) entityType=6 (Machine) ; "
              f"unitConfig={json.dumps((rows[0] if rows else {}).get('unitConfig'))}")

        # 3. ce que le StatsComponent porte APRES load_state
        state = load_state(dec, ob, snap)
        ent = state.get_entity(mid)
        sc = ent.get_component(StatsComponent) if ent is not None else None
        got_lvl = getattr(sc.ctx, "active_ability_level", None) if sc is not None else None
        got_mult = getattr(sc.ctx, "ability_variables_multiplier", None) if sc is not None else None
        print(f"[3] load_state -> ctx.active_ability_level={got_lvl} "
              f"ctx.ability_variables_multiplier={got_mult}")

        # 4. l'ecart de magnitude qui en decoule
        table = ((GC.ability(args.ability) or {}).get("variables") or {}).get(args.var)
        v_bug = ability_var(args.ability, args.var, got_lvl,
                            multiplier_pct=int(got_mult or 100))
        v_ref = ability_var(args.ability, args.var, lvl, multiplier_pct=int(mult or 100))
        print(f"[4] {args.ability}.{args.var} : niveau LU={got_lvl} -> {v_bug} | "
              f"niveau REEL={lvl} -> {v_ref}"
              + (f" | table[0]={table[0]} table[-1]={table[-1]}" if table else ""))

        # 5. contre-factuel : re-poser le niveau restaure la valeur native
        if sc is not None:
            sc.ctx.active_ability_level = lvl
            sc.ctx.ability_variables_multiplier = mult
            again = getattr(sc.ctx, "active_ability_level", None)
            print(f"[5] apres re-pose du niveau : ctx.active_ability_level={again} -> "
                  f"{args.var}={ability_var(args.ability, args.var, again, multiplier_pct=mult)}")
        print("[verdict] ECRASEMENT CONFIRME" if got_lvl != lvl else "[verdict] pas d'ecrasement")
    finally:
        try:
            _rpc(sid, "disposeRunner", {"runnerId": rid}, 20)
            print(f"[ok] runner {rid} dispose")
        except Exception as e:                                     # noqa: BLE001
            print(f"[warn] dispose KO: {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
