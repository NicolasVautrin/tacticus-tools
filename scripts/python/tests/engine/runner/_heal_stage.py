"""MONTAGE reutilisable << SOIN GENERIQUE >> -- un soigneur trait `Healer` + un ami BLESSE (#931-r1).

Pendant EXACT de `_repair_stage.py` (#298/#299) sur l'axe SOIN. Le parallele n'est pas cosmetique :
`18 Heal` et `28 Repair` sont toutes deux des abilities **DERIVEES D'UN TRAIT**
(`IdunBattle.Entities.Factories.UnitFactory$$AddDerivedAbilities` ->
`idun...StaticBattleRules.Trait$$GetActiveAbility`), donc absentes du gameconfig, multi-factions, et
invisibles de toute recherche par `unitId`.

ROSTER (team 1 = moi ; les deux sont dans `rl_duel.py build --list-pool`, rank 17) :

  | role   | unite             | ce qui compte                                                     |
  |--------|-------------------|-------------------------------------------------------------------|
  | healer | `ultraApothecary` | trait `Healer` -> l'ability `18 Heal` est DERIVEE. Il ne porte     |
  |        | << Incisus >>     | AUCUN passif de substitution, donc il garde bien `18` (contre-     |
  |        |                   | temoins : `genesBiophagus` et `spaceWolfPriest`, qui la PERDENT)   |
  | healee | `ultraTitus`      | non-Mechanical -> `AttackQuery$$EntityCanBeHealed` (healType 0)    |
  | (adv.) | `orksWarboss`,    | de quoi avoir une vraie bataille                                   |
  |        | `orksKillaKan`    |                                                                    |

⚠ **`--unit-stat <cible>:RemainingHealth=N`, JAMAIS `--hp-player`** : ce dernier ecrit `Health` ET
`RemainingHealth`, donc la cible reste a 100 % et `IdunBattle.Core.Services.AttackQuery$$IsDamagedUnit`
reste FAUX -- le montage annulerait le scenario qu'il doit creer (piege mesure par #299).

ASCII only (console cp1252).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

HEALER_VIS = "ultraApothecary"      # trait `Healer` -> `18 Heal` derivee, AUCUNE substitution
HEALEE_VIS = "ultraTitus"           # non-Mechanical -> soignable (healType 0)
ENEMY_VIS = ("orksWarboss", "orksKillaKan")

SEED = "777"
BOARD = "MC1_67"

#: `ActiveAbilityType.Heal` -- l'ability derivee du trait `Healer`.
HEAL_ABILITY_ID = 18

_PYDIR = Path(__file__).resolve().parents[3]          # scripts/python
_ROOT = _PYDIR.parents[1]                             # racine du checkout


def build_args(advance: int = 0, damaged_healee: int | None = 2000) -> list[str]:
    argv = ["--p-units", f"{HEALER_VIS},{HEALEE_VIS}",
            "--a-units", ",".join(ENEMY_VIS),
            "--board", BOARD]
    if damaged_healee is not None:
        argv += ["--unit-stat", f"{HEALEE_VIS}:RemainingHealth={damaged_healee}"]
    if advance:
        argv += ["--advance", str(advance)]
    return argv


def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def _build_subprocess(advance: int, damaged_healee: int | None) -> int:
    """State-file sous `logs/` du CHECKOUT COURANT (jamais `data/`) et suffixe par le PID."""
    state = _ROOT / "logs" / f"_heal_stage-{os.getpid()}.json"
    state.parent.mkdir(parents=True, exist_ok=True)
    state.unlink(missing_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", SEED,
            "--state-file", str(state), *build_args(advance, damaged_healee)]
    p = subprocess.run(argv, cwd=str(_PYDIR), capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    if not state.exists():
        raise RuntimeError("build runner KO (rl_duel): "
                           + ((p.stderr or p.stdout or "")[-400:]))
    return json.loads(state.read_text())["runnerId"]


def build_stage(rpc, build_runner=None, advance: int = 0,
                damaged_healee: int | None = 2000) -> dict:
    """Monte le montage et resout les entityId par visualId.

    Rend `{"rid", "healer", "healee", "enemies", "heal_ability", "observations"}` --
    `heal_ability` est l'entree `abilityTargets` de `18` chez le soigneur, ou `None`."""
    if build_runner is not None:
        rid = build_runner(SEED, extra=build_args(advance, damaged_healee))["rid"]
    else:
        rid = _build_subprocess(advance, damaged_healee)

    view = _unwrap(rpc("abilityTargets", {"runnerId": rid, "allAbilities": True}))
    units = (view or {}).get("units") or []
    by_vis = {u.get("visualId"): u for u in units}
    healer = (by_vis.get(HEALER_VIS) or {}).get("unitId")
    heal_ab = None
    if healer is not None:
        for a in by_vis[HEALER_VIS].get("abilities") or []:
            if a.get("abilityId") == HEAL_ABILITY_ID:
                heal_ab = a
                break

    ob = _unwrap(rpc("observeBattle", {"runnerId": rid})) or {}
    obs = ob.get("units") or ob.get("observations") or []
    healee = next((o.get("entityId") for o in obs
                   if o.get("visualId") == HEALEE_VIS), None)
    enemies = [o.get("entityId") for o in obs if o.get("visualId") in ENEMY_VIS]

    return {"rid": rid, "healer": healer, "healee": healee,
            "enemies": enemies, "heal_ability": heal_ab, "observations": obs}
