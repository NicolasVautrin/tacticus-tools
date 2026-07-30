"""MONTAGE reutilisable << REPARATION >> -- un repareur MECHANIC + un ami MECHANICAL blesse.

POURQUOI UN MONTAGE, ET PAS UN SETUP INLINE (#298, residu de #278). Le rail de DECISION de la
reparation a QUATRE etages natifs distincts, et chacun se mesure sur la MEME bataille :

  E0  `IdunBattle.Entities.Components.ActiveAbilityComponent` : l'ability de reparation est-elle dans
      la collection `Abilities` (@0x20), et pas seulement dans le slot scalaire `RepairType` (@0x2c) ?
  E1  `IdunBattle.AI.Tactics.ABaseAiActorTactic$$InitAbilityTypeLists` : son `ActiveAbilityType`
      entre-t-il dans `_comparableAbilities` / `_nonComparableAbilities[priority]` -- donc dans le
      `_abilityTypes` d'un des 6 generateurs montes par
      `IdunBattle.AI.Tactics.ABaseAiActorTactic$$GetDefaultActiveAbilityActionGenerators` ?
  E2  `IdunBattle.AI.ActionGenerators.ActiveAbilityActionGenerator$$GetUnitAbilitiesInOrder` :
      l'ability survit-elle au filtre `_abilityTypes.Contains(...)` pour CETTE unite ?
  E3  `IdunBattle.AI.Playbook.Loki.Repair_GalvanicFieldPlaybook$$MakeRepairPredictions` ->
      `IdunBattle.Core.Services.DamagePrediction$$PredictRepair` : la prediction est-elle calculee ?

Un montage qui ne porte PAS un repareur ET une cible reparable ne separe rien : l'absence de
`repair_prediction` s'expliquerait alors par le seul manque de cible. D'ou le roster ci-dessous.

ROSTER (team 1 = moi ; les deux sont HERO et presents dans `rl_duel.py build --list-pool`, rank 17) :

  | role      | unite              | ce qui compte                                                    |
  |-----------|--------------------|------------------------------------------------------------------|
  | repairer  | `admecManipulus`   | traits {Hero, Mechanical, Mechanic, Flying} ; le trait `Mechanic` |
  |           |                    | derive l'ability de reparation (cf.                              |
  |           |                    | `IdunBattle.Entities.Factories.UnitFactory$$AddDerivedAbilities`, |
  |           |                    | branche `StaticBattleRules.Trait$$GetActiveAbility`), et son      |
  |           |                    | passif `GalvanicField` la specialise en `Repair_GalvanicField`    |
  |           |                    | (1119, membre de `StaticBattleRules.ActiveAbility$$IsRegularRepair`)|
  | repairee  | `admecRuststalker` | trait `Mechanical` -> `IdunBattle.Core.Services.AttackQuery$$EntityCanBeRepaired` |
  | (adverse) | `orksWarboss`,     | de quoi avoir une vraie bataille et des tours IA a jouer          |
  |           | `orksKillaKan`     |                                                                   |

`hp_player` (defaut 1500) force les PV des unites de team 1 BAS des le build : la cible de
reparation est donc blessee SANS dependre du hasard de `--advance`. Piege connu et assume :
`--hp-player` MET AUSSI `Armor`/`FixedArmor` a 0 -- sans effet ici, la reparation reguliere
restaure la SANTE (`PredictRepair` finit par `CONCAT44(MaxFillUp(...), GetStat(target, Health))`),
pas l'armure (c'est `PredictArmorRestore`).

`advance` (defaut 2) fait jouer 2 tours IA vs IA avant la mesure : l'etat n'est pas un debut de
partie artificiel, et les unites sont a portee.

Le montage s'utilise DEUX facons, avec le meme code :
  * depuis pytest       : `build_stage(rpc, build_runner=build_runner)`
  * depuis un probe CLI : `build_stage(rpc)` -- construit par subprocess `rl_duel.py build`

ASCII only (console cp1252).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPAIRER_VIS = "admecManipulus"      # trait Mechanic -> reparation derivee ; passif GalvanicField
REPAIREE_VIS = "admecRuststalker"    # trait Mechanical -> reparable
ENEMY_VIS = ("orksWarboss", "orksKillaKan")

SEED = "777"
BOARD = "MC1_67"

# Ids d'ActiveAbilityType de la reparation REGULIERE, lus au decompile de
# `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.ActiveAbility$$IsRegularRepair`
# (comparaisons a 0x1c=28 `Repair` et 0x45f=1119 `Repair_GalvanicField`). `NanoscarabRepairProtocols`
# (1224) n'en fait PAS partie.
REGULAR_REPAIR_IDS = (28, 1119)

_PYDIR = Path(__file__).resolve().parents[3]          # scripts/python
_ROOT = _PYDIR.parents[1]                             # racine du checkout


def build_args(hp_player: int | None = 1500, advance: int = 2,
               damaged_repairee: int | None = None) -> list[str]:
    """Arguments `rl_duel build` du montage (hors `--seed`/`--state-file`).

    `damaged_repairee` = valeur de `RemainingHealth` posee sur la CIBLE seule, via
    `--unit-stat`. C'est le SEUL levier qui rend la cible BLESSEE sans toucher a sa
    sante MAX : `--hp-player N` ecrit `Health` ET `RemainingHealth` a N, donc l'unite
    reste a 100 % et `IdunBattle.Core.Services.AttackQuery$$IsDamagedUnit` reste FAUX
    -- piege mesure le 2026-07-30, il annulait le scenario qu'il devait creer.
    """
    argv = ["--p-units", f"{REPAIRER_VIS},{REPAIREE_VIS}",
            "--a-units", ",".join(ENEMY_VIS),
            "--board", BOARD]
    if hp_player is not None:
        argv += ["--hp-player", str(hp_player)]
    if damaged_repairee is not None:
        argv += ["--unit-stat",
                 f"{REPAIREE_VIS}:RemainingHealth={damaged_repairee}"]
    if advance:
        argv += ["--advance", str(advance)]
    return argv


def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def _build_subprocess(hp_player: int | None, advance: int,
                      damaged_repairee: int | None) -> int:
    """Monte le runner par `rl_duel.py build` ; rend son runnerId.

    State-file sous `logs/` du CHECKOUT COURANT (jamais `data/`, qui est versionne et ne
    porte que des ENTREES) et suffixe par le PID pour ne pas disposer le runner d'un frere.
    """
    state = _ROOT / "logs" / f"_repair_stage-{os.getpid()}.json"
    state.parent.mkdir(parents=True, exist_ok=True)
    state.unlink(missing_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", SEED,
            "--state-file", str(state),
            *build_args(hp_player, advance, damaged_repairee)]
    p = subprocess.run(argv, cwd=str(_PYDIR), capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    if not state.exists():
        raise RuntimeError("build runner KO (rl_duel): "
                           + ((p.stderr or p.stdout or "")[-400:]))
    return json.loads(state.read_text())["runnerId"]


def build_stage(rpc, build_runner=None, hp_player: int | None = 1500,
                advance: int = 2, damaged_repairee: int | None = None) -> dict:
    """Monte le montage et resout les entityId par visualId.

    `rpc(method, body)` = appel RPC deballe. `build_runner` = fabrique pytest du conftest
    (portee = celle de la fixture appelante) ; absente, on construit par subprocess.

    Rend `{"rid", "repairer", "repairee", "enemies", "repair_ability"}` -- `repair_ability`
    est l'entree `abilityTargets` de la reparation reguliere du repareur, ou None.
    """
    if build_runner is not None:
        rid = build_runner(
            SEED, extra=build_args(hp_player, advance, damaged_repairee))["rid"]
    else:
        rid = _build_subprocess(hp_player, advance, damaged_repairee)

    view = _unwrap(rpc("abilityTargets", {"runnerId": rid, "allAbilities": True}))
    units = (view or {}).get("units") or []
    by_vis = {u.get("visualId"): u for u in units}
    repairer = (by_vis.get(REPAIRER_VIS) or {}).get("unitId")
    repair_ab = None
    if repairer is not None:
        for a in by_vis[REPAIRER_VIS].get("abilities") or []:
            if a.get("abilityId") in REGULAR_REPAIR_IDS:
                repair_ab = a
                break

    ob = _unwrap(rpc("observeBattle", {"runnerId": rid})) or {}
    obs = ob.get("units") or ob.get("observations") or []
    repairee = next((o.get("entityId") for o in obs
                     if o.get("visualId") == REPAIREE_VIS), None)
    enemies = [o.get("entityId") for o in obs
               if o.get("visualId") in ENEMY_VIS]

    return {"rid": rid, "repairer": repairer, "repairee": repairee,
            "enemies": enemies, "repair_ability": repair_ab,
            "observations": obs}
