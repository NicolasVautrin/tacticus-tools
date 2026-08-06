"""MONTAGE reutilisable << LIVING METAL >> -- un porteur Necron BLESSE + un temoin NON reparable.

POURQUOI UN MONTAGE, ET PAS UN SETUP INLINE (#310). Le trigger `LivingMetalRepairAbility` a un
artefact natif `Repair(..., ForRegenerate)` et non un `Heal`, et la difference se mesure sur QUATRE
regimes qui exigent tous LA MEME bataille :

  R0  NOMINAL      : porteur BLESSE, aucun effet -> `repaired == round_half_even(pct % maxHP)`,
                     et le meme delta que le natif au turn-start de son proprietaire.
  R1  GATE         : `IdunBattle.Core.Services.AttackQuery$$EntityCanBeRepaired` est-il seulement
                     BRANCHE ? Il faut une unite NON reparable dans le MEME etat (le montage porte
                     donc `ultraApothecary`, Imperial non mecanique -- soignable, PAS reparable).
  R2  CURSED       : `EffectType.Cursed` (79) bloque `HealUnitOperation` et **PAS**
                     `RepairUnitOperation` -> c'est le regime ou l'ancien cablage REFUSAIT une regen
                     que le natif accorde.
  R3  MODIFIER     : le `RepairModifier` de `PredictRepair` (bonus de reparation RECUS par la cible)
                     ne vit QUE sur la voie repair -> `NanoscarabRepairProtocols` (1545) change le
                     montant, ce que la voie heal ignorait.

Un montage qui ne porterait QUE le Necron blesse ne separerait rien : R1 n'aurait pas de temoin, et
« ca regenere » / « ca regenere toujours, meme quand il ne faut pas » rendraient le meme vert.

ROSTER (team 1 = moi ; les deux HERO sont dans `rl_duel.py build --list-pool`, rank 17) :

  | role      | unite             | ce qui compte                                                    |
  |-----------|-------------------|------------------------------------------------------------------|
  | porteur   | `necroWarden`     | trait `LivingMetal` (1000) -> le trigger 0x3f2 lui est accorde    |
  |           |                   | (`TRAIT_TRIGGERS["LivingMetal"]`). `LivingMetal` implique         |
  |           |                   | `IdunBattle.Entities.UnitExtensions$$IsMechanical`, donc          |
  |           |                   | `IsAffectedByHealType(., 1)` est VRAI -- cf. R1 ci-dessous        |
  | temoin    | `ultraApothecary` | Imperial NON mecanique : soignable (`heal type 0`) et PAS         |
  |           |                   | reparable (`heal type 1`) -- le discriminant heal/repair, deja    |
  |           |                   | utilise par `test_repair_execution_live.py`                       |
  | (adverse) | `orksWarboss`     | de quoi avoir une vraie bataille                                  |

⚠ CE QUE LE MONTAGE NE PEUT PAS PRODUIRE, ET IL FAUT LE DIRE. Aucun porteur du trait `LivingMetal`
ne peut faire REFUSER le gate : le trait IMPLIQUE `IsMechanical`, qui est exactement le disjunct
d'`IsAffectedByHealType(unit, 1)` ; et `python unit_map.py find --trait LivingMetal` rend 52
porteurs dont AUCUNE Machine of War (donc `IsMachine` ne mord pas non plus). Le regime R1 se joue
donc sur le TEMOIN : on demande au trigger de reparer une unite non reparable, ce qui n'arrive
jamais en bataille mais exerce le gate PAR LE CHEMIN EXACT du trigger. C'est un controle
STRUCTUREL du cablage, pas un scenario de jeu -- et c'est ecrit ici pour qu'on ne le lise pas comme
davantage.

`damaged_carrier` = `RemainingHealth` posee sur le PORTEUR seul, via `--unit-stat` : le SEUL levier
qui rend la cible blessee sans toucher a sa sante MAX (`--hp-player N` ecrit `Health` ET
`RemainingHealth`, donc l'unite reste a 100 % et `IsDamagedUnit` reste FAUX -- meme piege que
`_repair_stage`).

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

CARRIER_VIS = "necroWarden"        # trait LivingMetal -> trigger 0x3f2 accorde
WITNESS_VIS = "ultraApothecary"    # NON mecanique -> IsAffectedByHealType(., 1) FAUX
ENEMY_VIS = ("orksWarboss",)

SEED = "777"
BOARD = "MC1_67"

# `EffectType.Cursed` = 0x4f. Gate EXCLUSIF du soin : `IdunBattle.Operations.HealUnitOperation$$Execute`
# fait `EntityExtensions.HasEffect(entity, 0x4f)` et force le montant a 0 ;
# `IdunBattle.Operations.RepairUnitOperation$$Execute` n'a AUCUN test de ce type (son seul equivalent
# est `UnitExtensions$$HasHealBlockers` = le dict `HealthComponent+0x78`, distinct -- et aucune classe
# `CursedEffect` n'existe dans le build, l'EffectType 79 n'est lu QUE par le heal).
CURSED_EFFECT_TYPE = 79

# `NanoscarabRepairProtocolsEffect` (EffectType 1545) -- l'un des 3 SEULS implementeurs du descripteur
# `IdunBattle.Entities.Effects.BaseEffect$$RepairBonus` (RE #45d), et le seul dont le porteur puisse
# etre un Necron : `necroReanimator` le pose sur ses allies Mechanical. `ForAddition`, add =
# `hpToRepair[level]`.
NANOSCARAB_EFFECT_TYPE = 1545
NANOSCARAB_EFFECT_NAME = "NanoscarabRepairProtocols"

_PYDIR = Path(__file__).resolve().parents[3]          # scripts/python
_ROOT = _PYDIR.parents[1]                             # racine du checkout


def build_args(damaged_carrier: int | None = 2000, advance: int = 0) -> list[str]:
    """Arguments `rl_duel build` du montage (hors `--seed`/`--state-file`)."""
    argv = ["--p-units", f"{CARRIER_VIS},{WITNESS_VIS}",
            "--a-units", ",".join(ENEMY_VIS),
            "--board", BOARD]
    if damaged_carrier is not None:
        # le TEMOIN est blesse lui aussi : sans ca, `IsDamagedUnit` suffirait a expliquer son refus
        # et le controle R1 ne separerait plus le gate `IsAffectedByHealType` du gate « pleins PV ».
        argv += ["--unit-stat",
                 f"{CARRIER_VIS}:RemainingHealth={damaged_carrier};"
                 f"{WITNESS_VIS}:RemainingHealth={damaged_carrier}"]
    if advance:
        argv += ["--advance", str(advance)]
    return argv


def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def _build_subprocess(damaged_carrier: int | None, advance: int) -> int:
    """Monte le runner par `rl_duel.py build` ; rend son runnerId.

    State-file sous `logs/` du CHECKOUT COURANT (jamais `data/`, qui est versionne et ne porte que
    des ENTREES) et suffixe par le PID pour ne pas disposer le runner d'un frere."""
    state = _ROOT / "logs" / f"_living_metal_stage-{os.getpid()}.json"
    state.parent.mkdir(parents=True, exist_ok=True)
    state.unlink(missing_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", SEED,
            "--state-file", str(state), *build_args(damaged_carrier, advance)]
    p = subprocess.run(argv, cwd=str(_PYDIR), capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    if not state.exists():
        raise RuntimeError("build runner KO (rl_duel): "
                           + ((p.stderr or p.stdout or "")[-400:]))
    return json.loads(state.read_text())["runnerId"]


def build_stage(rpc, build_runner=None, damaged_carrier: int | None = 2000,
                advance: int = 0) -> dict:
    """Monte le montage et resout les entityId par visualId.

    Rend `{"rid", "carrier", "witness", "enemies", "observations"}` (ids d'ENTITE live)."""
    if build_runner is not None:
        rid = build_runner(SEED, extra=build_args(damaged_carrier, advance))["rid"]
    else:
        rid = _build_subprocess(damaged_carrier, advance)

    ob = _unwrap(rpc("observeBattle", {"runnerId": rid})) or {}
    obs = ob.get("units") or ob.get("observations") or []
    carrier = next((o.get("entityId") for o in obs if o.get("visualId") == CARRIER_VIS), None)
    witness = next((o.get("entityId") for o in obs if o.get("visualId") == WITNESS_VIS), None)
    enemies = [o.get("entityId") for o in obs if o.get("visualId") in ENEMY_VIS]
    return {"rid": rid, "carrier": carrier, "witness": witness,
            "enemies": enemies, "observations": obs}


def make_effect(name: str, effect_type: int, level, source, multiplier_pct: int = 100):
    """Instancie UN effet materialise (`EffectFactory.create`) pret a etre pose par
    `state.effects.add_effect(uid, eff)` -- le meme chemin que `AddEffectOperation` offline.

    Sert aux regimes R2/R3 : poser sur l'etat CAPTURE l'effet dont on veut mesurer l'influence,
    sans dependre d'un poseur present dans la bataille (`necroReanimator` est hors du pool
    spawnable -- il faut `catalog_inject`, cf. `runner.md` §1bis)."""
    from engine.entities.effects.factory import EffectFactory
    return EffectFactory.create({"name": name, "effectType": effect_type, "level": level,
                                 "source": source},
                                ability_variables_multiplier=multiplier_pct)
