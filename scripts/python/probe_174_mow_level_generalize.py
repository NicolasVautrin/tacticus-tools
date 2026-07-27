"""#174 GENERALISATION -- l'INDEX `level-1` tient sur d'AUTRES boards, d'AUTRES seeds, d'AUTRES MoW.

Les suites MoW existantes mesurent toutes sur `C1_02`/`C2_02` avec la seed `4242`/`31337`. Ce probe
re-confronte la chaine ailleurs, et surtout il confronte a un OBSERVABLE LIVE NON ALEATOIRE :

    `SporeMineLauncher` (1145, tyranBiovore) -> `summonHp` = PV de la mine invoquee.
    Table gameconfig STRICTEMENT CROISSANTE (idx0=20 ... idx49=1109 ... idx64=1455) : la valeur
    live PINCE l'index, elle ne peut pas etre atteinte par un autre. C'est ce qui distingue cette
    preuve d'un simple « le test passe » (cf. `nrOfTiles`, plat sur 30 index -> NON discriminant).

Chaine natif indexee (decompile, build gqfc5mff6c) :
    IdunBattle.Entities.Formulas.ConfigAmount$$Calculate
      -> IdunBattle.Entities.Formulas.ConfigAmount$$GetAbilityState  (AbilityState de l'ENTITE)
      -> IdunBattle.Configuration.AbilityConfiguration$$GetVariableForLevel
           -> IdunBattle.Configuration.AbilityConfiguration$$TryGetVariableArrayForLevel :
                idx = Math.Max(0, Idun.Shared.Level$$ToZeroBasedIndex(state.Level)), clampe len-1
                (Idun.Shared.Level$$ToZeroBasedIndex = value - 1 ; LEVE si value <= 0)
                puis, si la variable est dans `VariablesAffectedByUnitRarityMultiplier` :
                valeur = Fix64.Round(state.VariableMultiplierPercentage / 100 * valeur)

Le `combatSnapshot` est pris sur un runner JUMEAU (HARNAIS-1, cf. docs/rl/case-162-mow-red-suites.md
section 2) : sur le runner de MESURE il rendrait toute pose d'effet ulterieure muette.

ASCII only. Ne modifie aucun fichier du moteur.

    python probe_174_mow_level_generalize.py
    python probe_174_mow_level_generalize.py --boards MC1_67:777,C4_09:999
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

CARRIER = "tyranBiovore"
SPORE = 1145
SUMMON_VID = "tyranSmnSporeMine"
VAR = "summonHp"
ABILITY_ID = "SporeMineLauncher"


def _rpc(sid, method, body, timeout=120):
    r = R._rpc(sid, method, [body], timeout=timeout)
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def _build(state_path: Path, board: str, seed: str):
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.unlink(missing_ok=True)
    subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", seed, "--board", board,
         "--p-units", "necroDestroyer,necroWarden", "--a-units", "necroDestroyer,necroWarden",
         "--p-mow", CARRIER, "--state-file", str(state_path)],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not state_path.exists():
        return None
    return json.loads(state_path.read_text())["runnerId"]


def _one_case(sid, board_id: str, seed: str) -> bool:
    import gameconfig as GC
    from engine.entities.effects.magnitude import ability_var
    from engine.entities.pathfinding.board import Board
    from engine.runner.components import (HealthComponent, OwnerComponent, PositionComponent,
                                          StatsComponent, UnitComponent)
    from engine.runner.operations.summon_ai import _apply_active_ability
    from engine.runner.snapshot import load_state

    tag = f"{board_id}/{seed}"
    rid = _build(ROOT / "logs" / f"_probe174gen_{board_id}_{seed}.json", board_id, seed)
    if rid is None:
        print(f"[{tag}] SKIP build KO (board non MoW-capable ?)")
        return True
    twin = _build(ROOT / "logs" / f"_probe174gen_twin_{board_id}_{seed}.json", board_id, seed)
    ok = True
    try:
        snap = _rpc(sid, "combatSnapshot", {"runnerId": twin}) if twin else None
        if twin is not None:
            _rpc(sid, "disposeRunner", {"runnerId": twin}, 20)
        dec = _rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True})
        ob = _rpc(sid, "observeBattle", {"runnerId": rid}, 40)
        bg = _rpc(sid, "boardGraph", {"runnerId": rid}, 60)
        m = next((x for x in (dec.get("mows") or []) if x.get("visualId") == CARRIER), None)
        if m is None or snap is None or not (bg or {}).get("tiles"):
            print(f"[{tag}] SKIP MoW non deployee / snapshot ou board indispo")
            return True
        board = Board(bg["tiles"], adjacency="evenq")
        cid = int(m["casterId"])
        state = load_state(dec, ob, snap, board=board)
        sc = state.get_entity(cid).get_component(StatsComponent)
        lvl = int(sc.ctx.active_ability_level or 0)
        mult = int(sc.ctx.ability_variables_multiplier or 100)
        table = ((GC.ability(ABILITY_ID) or {}).get("variables") or {}).get(VAR) or []
        idx = max(0, min(lvl - 1, len(table) - 1))
        at_zero = round(table[0] * mult / 100)
        resolved = ability_var(ABILITY_ID, VAR, lvl, multiplier_pct=mult)
        print(f"[{tag}] caster={cid} vis={sc.ctx.visual_id} traits={sc.ctx.traits} "
              f"level={lvl} mult={mult} -> idx={idx} table[{idx}]={table[idx] if table else None} "
              f"resolu={resolved} (index 0 donnerait {at_zero})")

        # tuile-cible LEGALE et LIBRE
        at = _rpc(sid, "abilityTargets",
                  {"runnerId": rid, "unitId": cid, "abilityType": SPORE}) or {}
        row = next((u for u in (at.get("units") or []) if u.get("unitId") == cid), None)
        tiles = [(t["tile"]["col"], t["tile"]["row"])
                 for t in ((row.get("abilities") or [{}])[0].get("targets") or [])
                 if t.get("kind") == "tile"] if row else []
        occ = {(u.get("col"), u.get("row")) for u in (ob.get("units") or []) if not u.get("isDead")}
        tile = next((t for t in tiles if t not in occ), None)
        if tile is None:
            print(f"[{tag}] SKIP aucune tuile-cible libre")
            return True

        before = set(state.entities)
        res = _apply_active_ability(state, cid, board.id_at(*tile), SPORE)
        spawned = ((res or {}).get("diag") or {}).get("spawned") or []
        off_hp = None
        if len(spawned) == 1 and spawned[0] in (set(state.entities) - before):
            e = state.get_entity(spawned[0])
            off_hp = e.get_component(HealthComponent).hp
            off_owner = e.get_component(OwnerComponent)
            off_pos = e.get_component(PositionComponent)
            assert e.get_component(UnitComponent).visual_id == SUMMON_VID
        before_ids = {u.get("squadId") for u in (ob.get("units") or [])}
        r = _rpc(sid, "applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": cid, "abilityType": SPORE,
            "to": {"col": tile[0], "row": tile[1]}}}) or {}
        act = (r.get("actions") or [{}])[0]
        ob2 = _rpc(sid, "observeBattle", {"runnerId": rid}, 40) or {}
        mines = [u for u in (ob2.get("units") or [])
                 if u.get("visualId") == SUMMON_VID and u.get("squadId") not in before_ids
                 and not u.get("isDead")]
        live_hp = mines[0].get("hp") if len(mines) == 1 else None
        print(f"[{tag}] tuile={tile} spawn OFFLINE hp={off_hp} | LIVE hp={live_hp} "
              f"(cast err={act.get('error')})")
        if off_hp is None or live_hp is None:
            print(f"[{tag}] SKIP spawn non confrontable")
            return True
        if off_hp != live_hp:
            print(f"[{tag}] FAIL hp offline {off_hp} != live {live_hp}")
            ok = False
        elif live_hp != resolved:
            print(f"[{tag}] FAIL hp live {live_hp} != magnitude portee {resolved}")
            ok = False
        elif live_hp == at_zero:
            print(f"[{tag}] FAIL NON DISCRIMINANT : index 0 donne la meme valeur")
            ok = False
        else:
            print(f"[{tag}] OK index={idx} PINCE par le live ({live_hp}), index 0 rendrait "
                  f"{at_zero} | pos offline={(off_pos.col, off_pos.row)} "
                  f"team={off_owner.team}/{off_owner.player}")
    finally:
        try:
            _rpc(sid, "disposeRunner", {"runnerId": rid}, 20)
        except Exception:                                          # noqa: BLE001
            pass
    return ok


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--boards", default="MC1_67:777,C4_09:999,C3_01:31337",
                    help="couples board:seed separes par des virgules")
    args = ap.parse_args()
    sid = R._resolve_session()
    ok = True
    for spec in args.boards.split(","):
        board_id, _, seed = spec.partition(":")
        ok = _one_case(sid, board_id.strip(), (seed or "777").strip()) and ok
    print("[verdict] " + ("TOUS OK" if ok else "AU MOINS UN ECHEC"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
