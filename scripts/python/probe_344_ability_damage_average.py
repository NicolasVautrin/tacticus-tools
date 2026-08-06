#!/usr/bin/env python
"""Probe #344 -- la PREDICTION d'ability moyenne minDmg/maxDmg par DEUX chaines natives distinctes.

CE QUE LE DECOMPILE DIT (`rnca9r7q6c`, lu VERBATIM)
---------------------------------------------------
Le 6e argument que `<X>Playbook$$MakeDamagePredictions` passe a
`ComparablePlaybook<T>$$GenerateMultiHitAttackPredictions` prend l'une de DEUX formes. Chacune est
portee par UN corps DEDUPLIQUE (donc UN SEUL nom ghidra pour tous ses proprietaires) :

  (a) `<X>Ability$$GetDamageAmountMain`, corps partage etiquete
      `IdunBattleLogic.Entities.Abilities.Active.Loki.StranglethornCannonAbility$$GetDamageAmountMain`
      -> `IdunBattle.Entities.Abilities.AActiveAbility$$MinMaxDamageAverage`
      =  `DSLFormulas.Half( DSLFormulas.Sum(Direct(minDmg 0xc), Direct(maxDmg 0xd)), rule = 0 )`
      -> `IdunBattle.Entities.Formulas.DivideAmount$$Calculate`
      -> `IdunBattle.DSL.AAmountFormula$$RoundFix64Result(., 0)` = `Fix64.Round(., 0)`
      = DEMI-VERS-LE-PAIR.

  (b) `<X>Ability$$GetDamage`, corps partage etiquete
      `IdunBattleLogic.Entities.Abilities.Active.Loki.VigilanceEternalAbility$$GetDamage`
      -> `AActiveAbility$$MinMaxDamage(state, isPrediction: FALSE)` = `RandomAmount(minDmg, maxDmg)`,
      dont le playbook prend le slot 4 d'`IAmountFormula` =
      `IdunBattle.DSL.AAmountFormula$$CalculateAverage` = `(min + max) / 2` ENTIER = TRONCATURE.

Les xrefs de ces deux corps donnent 18 abilities de chaque cote (registres
`_PREDICTION_MINMAX_AVERAGE` / `_PREDICTION_MINMAX_RANDOM_READ` d'`entities/abilities/active_ability`).
Les deux formes ne divergent que sur `minDmg + maxDmg = 3 mod 4`, d'exactement 1 : un port qui
mettrait tout le monde d'un seul cote est faux dans l'autre moitie, et invisible deux fois sur trois.

CE QUE CE PROBE MESURE, ET POURQUOI IL FAUT DEUX BRAS
----------------------------------------------------
Une somme PAIRE ne separe aucun mode. Une somme IMPAIRE en separe deux groupes selon la parite du
FLOOR, et il faut les DEUX pour isoler UN mode :

  bras A : `mn + mx = 3 mod 4` (floor IMPAIR) -> `to_even` = floor+1, `trunc` = floor
  bras B : `mn + mx = 1 mod 4` (floor PAIR)   -> `to_even` = `trunc` = floor, `half_up`/`ceil` = floor+1

  | variante  | bras A (floor impair) | bras B (floor pair) |
  |-----------|-----------------------|---------------------|
  | `to_even` |        floor+1        |        floor        |
  | `trunc`   |        floor          |        floor        |
  | `half_up` |        floor+1        |        floor+1      |
  | `ceil`    |        floor+1        |        floor+1      |

=> une SEULE variante egale le natif sur les DEUX bras, et laquelle DEPEND DE LA FAMILLE :
`to_even` pour (a), `trunc` pour (b). Le probe la compare a ce que le REGISTRE prevoit ; il verifie
en outre que le code LIVRE (sans aucun patch) egale le natif sur les deux bras.

Deux leviers de PILOTAGE (la parite et la survie de l'ecart sont choisies, jamais subies) :
  - `--unit-stat '<vis>:ActiveAbilityLevel=<L>'` choisit le niveau, donc (minDmg, maxDmg), donc la
    classe de `mn + mx` modulo 4. Le regime obtenu est RE-DERIVE du live (l'objet ability du port,
    nourri de l'`abilityState` capte) : si le pilotage ne prend pas, le probe le DIT.
  - `--armor-target 0` retire l'etage armure. Piege herite de #339 sec.4 : un arrondi AVAL peut
    ABSORBER l'ecart d'une unite (mesure : BringerOfDespair niveau 2 sur cible blindee, les quatre
    variantes rendent (36,56)). Un bras ou tout coincide est declare NON DISCRIMINANT et fait
    ECHOUER le verdict au lieu de le verdir.

Oracle = `aiPlaybookPredict` (invocation DIRECTE de `<X>Playbook$$MakeDamagePredictions`), compare a
`engine.playbook.prediction.abilities.make_damage_predictions` sur le MEME etat live, sur la SEQUENCE
des events de la CIBLE PRINCIPALE (le volet AoE -- les cibles SECONDAIRES -- est un axe distinct,
affiche pour diagnostic via le compte total). Les points de branchement patches sont les DEUX moyennes
telles qu'IMPORTEES dans `engine.entities.abilities.active_ability` (`_round_fix64`,
`calculate_average`).

DEUXIEME ORACLE : la face NONCOMPARABLE (#356)
----------------------------------------------
`aiPlaybookPredict` ne peut STRUCTURELLEMENT rien rendre pour un playbook NonComparable -- les quatre
`Make*Predictions` ne sont declarees que sur la branche `ComparablePlaybook`1` (cf.
`docs/rl/case-350r3-oracle-noncomparable.md`). Mais la PREDICTION existe : `EvaluateNonComparable`
construit le MEME `ProbableDamageEvent` avant de le passer a `CalculateUtilityFromDamageEvent` -- il
le CONSOMME au lieu de le RENDRE. Le RPC `ncPlaybookPredict` (`via: "evaluate"`) le CAPTURE au
ctor. `--oracle nc` (auto des que l'ability a un playbook NC porte) commute donc :
  * cote natif : `ncPlaybookPredict` au lieu d'`aiPlaybookPredict` ;
  * cote port  : `playbook.damage_predictions(position, cible, ctx)` -- la SEQUENCE que le playbook
    NC porte CONSTRUIT, dans l'ordre natif -- au lieu de `make_damage_predictions`.
Le point de branchement patche est le MEME (`AActiveAbility.get_damage`), donc le verdict d'arrondi
se lit a l'identique sur les deux faces.

⚠ LA CAPTURE N'EST PAS « LA PREDICTION DE L'ABILITY » (#362). Le trampoline est sur le CTOR : il
voit TOUT ce que l'evaluation construit, y compris ce qu'un GATE construit sans le scorer.
`IdunBattle.AI.Playbook.BasePlaybook$$WillNormalAttackKill` -- premiere instruction du corps de
boucle de `KillMaimBurnPlaybook$$EvaluateNonComparable` -- predit l'attaque NORMALE, en fait un
`ProbableDamageEvent` avec le MEME `targetId`, et n'en retient que `get_WillBeKill`. D'ou DEUX
consequences que ce probe modelise : la comparaison porte sur la SEQUENCE (gate compris), et un
montage ou le gate MORD ne construit AUCUNE prediction d'ability -> NON CONFRONTE (rc 2), avec
`--victim-hp` comme levier de regime.

⚠ REGIME : une ability NC peut porter une precondition d'eligibilite (1202 VigilanceEternal exige une
cible ADJACENTE ou chargeable a portee 2 -- `VigilanceEternalAbility$$GetDynamicInvalidTargetReason`).
L'anneau de `_place_ring` la satisfait PAR CONSTRUCTION (toutes les cibles a distance 1) et le probe
le VERIFIE (`_nc_regime`) : un bras hors regime rend une erreur qui NOMME le montage, il ne rougit
pas comme un ecart d'arrondi.

⚠ SEQUENCE, ET NON « le premier event » (#351). Un playbook peut emettre PLUSIEURS events sur la MEME
cible : `...SorcerousFacadePlaybook$$MakeDamagePredictions` construit `[normale]` puis `AddRange(batch)`,
les deux sur `sel`. En ne lisant que le premier, le probe comparait l'ATTAQUE NORMALE -- qui ne lit
aucune moyenne minDmg/maxDmg -- et rendait donc un bras NON DISCRIMINANT (les quatre variantes egales),
c.-a-d. un ECHEC qui n'accusait pas la bonne chose. Comparer la sequence RETIENT du meme coup le COMPTE
d'events de la cible principale : c'est ce compte qui etait faux (natif 2, port 1).

ASCII only (cp1252). Usage (depuis scripts/python) :
    python probe_344_ability_damage_average.py
    python probe_344_ability_damage_average.py --caster darkaTerminator --ability 1150 --lvl-a 3 --lvl-b 2
    python probe_344_ability_damage_average.py --caster blackTerminator --ability 1022 --lvl-a 3 --lvl-b 2 --armor-target 0
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

from rl_collect_batch import _resolve_session, _rpc                          # noqa: E402
import engine.entities.abilities.active_ability as AA                        # noqa: E402
from engine.dsl.base import _round_fix64                                     # noqa: E402

# Montage par DEFAUT : FlailSwing (1042, `deathBlightlord`) -- ability du registre porte SANS
# handler `_MAKE_DMG_INPUT_OVERRIDES` ni override de `get_damage`, donc la base traverse bien le
# `AActiveAbility.get_damage` GENERIQUE qui est le site corrige.
CASTER = "deathBlightlord"
ABILITY = 1042
ABILITY_NAME = "FlailSwing"
FILLER_P = "astraBullgryn"
VICTIM = "necroWarden"          # cible TEMOIN : aucun trait de reduction de coups (pas de Parry)
FILLER_A = "ultraTitus"
BOARD = "MC1_67"
CENTER = (3, 4)
LVL_A = 2                       # minDmg+maxDmg = 3 mod 4 (bras discriminant)
LVL_B = 5                       # minDmg+maxDmg = 1 mod 4 (bras temoin de l'autre cote)
MULT = 100


def _r(sid, m, b, t=90):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


# -- variantes d'arrondi, appliquees au SEUL point de branchement ------------------------------

def _v_to_even(value: Fraction, mode: int) -> int:
    return _round_fix64(value, mode)


def _v_trunc(value: Fraction, mode: int) -> int:
    return int(value)                       # troncature vers zero = le port d'AVANT #344


def _v_half_up(value: Fraction, mode: int) -> int:
    return math.floor(value + Fraction(1, 2))


def _v_ceil(value: Fraction, mode: int) -> int:
    return math.ceil(value)


VARIANTS = (("to_even", _v_to_even), ("trunc", _v_trunc),
            ("half_up", _v_half_up), ("ceil", _v_ceil))


def _build(state_file: Path, seed: int, caster: str, victim: str, board: str,
           level: int, mult: int, armor_target=None, victim_hp=None) -> int:
    """`rl_duel build` -- board CHOISI (runner.md sec.2) et NIVEAU D'ABILITY PILOTE (`--unit-stat`,
    ecrit VERBATIM dans `BC.Units[]`), qui est le levier de la parite mesuree ici.

    `armor_target = 0` retire l'etage ARMURE de la cible. C'est le second levier de PILOTAGE :
    sur une cible blindee, la reduction d'armure ABSORBE souvent l'ecart d'une unite de la base
    (mesure : BringerOfDespair niveau 2, les quatre variantes rendent (36,56)) -- le bras est alors
    muet et ne prouve rien. Sans armure, l'ecart de base traverse jusqu'aux bornes observees.

    `victim_hp` = TROISIEME levier, requis par les playbooks NC a gate predictif (#362). Un playbook
    dont le corps commence par `IdunBattle.AI.Playbook.BasePlaybook$$WillNormalAttackKill` SAUTE
    toute cible que l'attaque NORMALE du caster tue deja a coup sur -- et ne construit alors AUCUNE
    prediction d'ability. Aux PV du seed, `worldKharn` (rank 17, 4 coups Eviscerate) sur-tue tout le
    pool : le regime de #344 y est INATTEIGNABLE. Forcer `Health`/`RemainingHealth` de la cible
    deplace le SEUL verdict `get_WillBeKill`, sans toucher ni la formule de degat, ni l'armure, ni
    le crit."""
    state_file.unlink(missing_ok=True)
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
           "--state-file", str(state_file), "--board", board, "--rank", "17",
           "--p-units", "%s,%s" % (caster, FILLER_P if caster != FILLER_P else CASTER),
           "--a-units", "%s,%s" % (victim, FILLER_A if victim != FILLER_A else VICTIM),
           "--unit-stat", "%s:ActiveAbilityLevel=%d,AbilityVariablesMultiplierPercentage=%d"
                          % (caster, level, mult),
           "--crit", "0,0", "--block-target", "0,0", "--no-ai"]
    if armor_target is not None:
        cmd += ["--armor-target", str(int(armor_target))]
    if victim_hp is not None:
        cmd += ["--unit-stat", "%s:Health=%d,RemainingHealth=%d"
                               % (victim, int(victim_hp), int(victim_hp))]
    proc = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not state_file.exists():
        raise RuntimeError("build KO : %s" % ((proc.stderr or proc.stdout or "")[-900:]))
    return int(json.loads(state_file.read_text())["runnerId"])


def _view(sid, rid):
    return _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)


def _move(sid, rid, uid, col, row):
    return _r(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": int(uid), "to": {"col": int(col), "row": int(row)}}}, 90)


def _place_ring(sid, rid, ids, center_visual, center):
    """GEOMETRIE DRIVEE (runner.md sec.4) : le caster au centre, tout le monde sur son ring 1."""
    from engine.entities.pathfinding.board import Board
    bg = _r(sid, "boardGraph", {"runnerId": rid}, 60)
    board = Board(bg["tiles"], adjacency="evenq")
    ccol, crow = center
    ring = [board.coord(t) for t in board.neighbours(board.id_at(ccol, crow))]
    if len(ring) < len(ids) - 1:
        raise RuntimeError("centre (%d,%d) trop pauvre en voisins (%d)" % (ccol, crow, len(ring)))
    _move(sid, rid, ids[center_visual], ccol, crow)
    slot = 0
    for v, uid in ids.items():
        if v == center_visual:
            continue
        _move(sid, rid, uid, *ring[slot])
        slot += 1


def _is_nc(ability: int) -> bool:
    """L'ability a-t-elle un playbook NonComparable PORTE ? (registre `engine.playbook.
    noncomparable.PLAYBOOKS`, mirror des classes de parent `NonComparablePlaybook`1`)."""
    from engine.playbook import noncomparable as NCPB
    return NCPB.is_noncomp(int(ability))


def _nc_regime(sid, rid, cid, tid, ability) -> dict:
    """Le montage atteint-il le REGIME d'eligibilite de l'ability NC ?

    Preuve GEOMETRIQUE, prise au decompile :
    `IdunBattleLogic.Entities.Abilities.Active.Loki.VigilanceEternalAbility$$GetDynamicInvalidTargetReason`
    rend `0` IMMEDIATEMENT si les tuiles du caster et de la cible sont ADJACENTES (predicat
    d'interface slot 0x62), avant meme d'essayer la charge -- l'anneau de `_place_ring` place
    justement toutes les cibles a distance hex 1. On confirme par `abilityReason`, dont le
    `targetReason.hex` EST le flag rendu par ce corps (`0x8000000` = `TargetIsInRange` = refus).

    ⚠ `abilityTargets` n'est PAS utilisable ici : apres le placement, les unites ont consomme leur
    action et le RPC ne les liste plus (mesure 2026-07-31 : `units: []`). Un montage ne se declare
    donc pas hors regime sur ce silence-la."""
    import hexgeo
    ob = _r(sid, "observeBattle", {"runnerId": rid}, 120)
    us = {int(u["squadId"]): u for u in (ob.get("units") or []) if not u.get("isDead")}
    c, t = us.get(int(cid)), us.get(int(tid))
    if c is None or t is None:
        return {"reached": False,
                "why": "caster %s ou cible %s absent d'observeBattle (%d unites vivantes : %s)"
                       % (cid, tid, len(us), sorted(us))}
    d = hexgeo.distance((c["col"], c["row"]), (t["col"], t["row"]))
    rr = _r(sid, "abilityReason", {"runnerId": rid, "casterId": int(cid), "targetId": int(tid),
                                   "abilityType": int(ability)}, 60)
    tr = (rr or {}).get("targetReason") or {}
    hx = tr.get("hex")
    # Critere PRINCIPAL : le flag rendu par `GetDynamicInvalidTargetReason` vaut 0 = cible eligible
    # (c'est le MEME jeu de regles que le slot 0x42 qu'interroge `GetEligibleTargetsEntities`).
    # Repli si `abilityReason` n'a pas resolu : l'ADJACENCE, qui court-circuite ce corps.
    if hx is None:
        reached, why = (d == 1), (None if d == 1 else
                                  "abilityReason muet et cible a distance %d" % d)
    else:
        reached = hx in ("0x0", "0x0000000000000000", 0)
        why = None if reached else "targetReason=%s %s (dist %d)" % (hx, tr.get("reasons"), d)
    return {"reached": bool(reached), "dist": d, "casterPos": (c["col"], c["row"]),
            "targetPos": (t["col"], t["row"]),
            "targetReasonHex": hx, "targetReasons": tr.get("reasons"), "why": why}


def _native_nc(sid, rid, cid, tid, ability):
    """Pendant NonComparable de `_native` : `ncPlaybookPredict(via="evaluate")` invoque le wrapper
    `Evaluate` du playbook sous un trampoline FENETRE sur `ProbableDamageEvent$$.ctor` et rend les
    events CONSTRUITS pendant l'evaluation. Meme filtre que `_native` : la SEQUENCE des events de la
    cible principale, plus le compte total (les autres cibles eligibles sont un axe distinct).

    ⚠ La capture n'est PAS « la prediction de l'ability » : le trampoline est sur le CTOR, donc il
    voit aussi ce qu'un GATE construit sans le scorer (#362 --
    `IdunBattle.AI.Playbook.BasePlaybook$$WillNormalAttackKill` predit l'attaque NORMALE et en fait
    un `ProbableDamageEvent` avec le MEME `targetId`). D'ou la comparaison a la SEQUENCE portee
    (`playbook.damage_predictions`) et non a la seule prediction d'ability."""
    r = _r(sid, "ncPlaybookPredict", {"runnerId": rid, "unitId": int(cid),
                                      "abilityType": int(ability), "via": "evaluate"}, 240)
    evs = (r or {}).get("captured") or []
    mains = [e for e in evs if e.get("targetId") == int(tid)]
    if not mains:
        return None, len(evs)
    return (tuple((e.get("healthDmgMin"), e.get("healthDmgMax"), e.get("appliedHits"))
                  for e in mains), len(evs))


def _nc_context(scene, ctx, cid, here):
    """`NCContext` MINIMAL (uid + position + scene + poids + units) : c'est tout ce que
    `damage_predictions` consomme. Construit explicitement plutot que de faire passer l'
    `AiDecisionContext` pour un `NCContext` par duck-typing."""
    from engine.playbook.noncomparable._base import NCContext
    return NCContext(uid=int(cid), origin=here, reach_nc=[here], epos=[], fpos=[], plan={},
                     hp_cur_by_id={}, scene=scene, wt=ctx.wt, units=ctx.units)


def _offline_nc(scene, ctx, cid, tid, ability, ability_name, here, fn=None, all_targets=None):
    """Pendant NonComparable de `_offline` : la SEQUENCE que le playbook NC PORTE **construit** pour
    la cible principale -- `playbook.damage_predictions(position, cible, ctx)`, qui rend
    `[(tag, DamagePredictionResult)]` dans l'ordre natif (cf.
    `engine/playbook/noncomparable/_base.py`). C'est le pendant EXACT de ce que l'oracle capture au
    ctor, gate compris, et non `make_damage_predictions` (dont le gate d'affichage #109 rend `[]`
    pour toute NonComparable). Le point de branchement patche (`AActiveAbility.get_damage`) reste le
    meme, donc la variante d'arrondi se mesure a l'identique.

    Rend `(sequence, n_events_total, has_ability)` : `has_ability` dit si le montage a laisse le
    playbook construire sa prediction d'ABILITY -- la SEULE porteuse de la moyenne minDmg/maxDmg.
    Faux = regime non atteint (le gate a mordu), pas un ecart d'arrondi."""
    from engine.playbook import noncomparable as NCPB
    pb = NCPB.playbook_for(int(ability))
    nc = _nc_context(scene, ctx, cid, here)
    o_round, o_avg = AA._round_fix64, AA.calculate_average
    if fn is not None:
        AA._round_fix64 = fn
        AA.calculate_average = lambda mn, mx: fn(Fraction(int(mn) + int(mx), 2), 0)
    try:
        seq = pb.damage_predictions(here, int(tid), nc)
        n = 0
        for other in (all_targets or [int(tid)]):
            n += len(pb.damage_predictions(here, int(other), nc))
    finally:
        AA._round_fix64, AA.calculate_average = o_round, o_avg
    has_ability = any(tag == "ability" for tag, _dp in seq)
    if not seq:
        return None, n, has_ability
    return (tuple((dp.accurate_health_damage.min, dp.accurate_health_damage.max, dp.applied_hits)
                  for _tag, dp in seq), n, has_ability)


def _native(sid, rid, cid, tid, ability):
    """(bornes de TOUS les events de la CIBLE PRINCIPALE, nombre total d'events).

    On isole la cible PRINCIPALE : les events des cibles SECONDAIRES (volet AoE) sont un AXE
    DISTINCT de l'arrondi mesure ici -- plusieurs playbooks emettent un batch secondaire que le port
    ne reproduit pas encore.

    ⚠ Mais « la cible principale » n'est PAS « le premier event » : un playbook peut emettre
    PLUSIEURS events sur la MEME cible. `...SorcerousFacadePlaybook$$MakeDamagePredictions` en emet
    deux -- `[ProbableDamageEvent(sel, attaque normale)]` puis `AddRange(GenerateMultiHit
    AttackPredictions(...))`, tous deux sur `sel` (MESURE #351 : `count = 2`, meme `targetId`). Ne
    garder que le premier rendait le bras MUET : l'attaque normale ne lit aucune moyenne minDmg/
    maxDmg, donc les quatre variantes d'arrondi y coincident. La comparaison porte donc sur la
    SEQUENCE (l'ordre est celui du natif, et il est observable). Pour toute ability mono-event par
    cible -- toutes les autres du registre -- le tuple a un seul element : comportement inchange."""
    r = _r(sid, "aiPlaybookPredict", {"runnerId": rid, "unitId": int(cid),
                                      "targetId": int(tid), "abilityType": int(ability)}, 120)
    evs = (r or {}).get("events") or []
    mains = [e for e in evs if e.get("targetId") == int(tid)] or (evs[:1] if evs else [])
    if not mains:
        return None, 0
    return (tuple((e.get("healthDmgMin"), e.get("healthDmgMax"), e.get("appliedHits"))
                  for e in mains), len(evs))


def _ctx(sid, rid, cid):
    from engine import weights as W
    from engine.playbook import scene as _scene
    from engine.ai import context as AICTX
    rpc = lambda m, b, t=60: _r(sid, m, b, t)                       # noqa: E731
    dv = _view(sid, rid)
    mov = _r(sid, "aiMovableTiles", {"runnerId": rid}, 60)
    mov_by_unit = {u.get("unitId"): u for u in ((mov or {}).get("units") or [])}
    return AICTX.build(rpc, rid, dv, mov_by_unit, int(cid), W.load(),
                       _scene.build_predictor(rpc, rid)), dv


def _minmax_config(scene, cid, ability, ability_name):
    """(minDmg, maxDmg) EFFECTIFS du port -- re-derives du live (level/mult captes), jamais supposes."""
    import gameconfig as GC
    from engine.entities.abilities.ability_configuration import AbilityConfiguration
    from engine.entities.abilities.active_ability import active_ability_for
    ctx0 = scene.ctx(int(cid))
    cfg = AbilityConfiguration.from_gameconfig(ability_name, GC.ability(ability_name))
    if ctx0 is None or cfg is None:
        return None
    ab = active_ability_for(ability_name, int(ability), ctx0, cfg,
                            ability_state=scene.ability_state(int(cid), int(ability)))
    lvl, mult = ab.level, ab.multiplier
    return (cfg.get_variable_for_level("minDmg", lvl, 0, mult),
            cfg.get_variable_for_level("maxDmg", lvl, 0, mult), lvl, mult)


def _offline(scene, cid, tid, ability, ability_name, here, fn=None):
    """Prediction OFFLINE. `fn = None` = le code LIVRE (aucun patch). Sinon les DEUX moyennes que
    `AActiveAbility.get_damage` peut emprunter (`_round_fix64` pour la famille `MinMaxDamageAverage`,
    `calculate_average` pour la famille `RandomAmount`) sont remplacees par `fn` -- de sorte que la
    variante mesure bien UN mode d'arrondi, quelle que soit la famille de l'ability."""
    from engine.playbook.prediction import abilities as PA
    o_round, o_avg = AA._round_fix64, AA.calculate_average
    if fn is not None:
        AA._round_fix64 = fn
        AA.calculate_average = lambda mn, mx: fn(Fraction(int(mn) + int(mx), 2), 0)
    try:
        evs = PA.make_damage_predictions(scene, int(cid), int(tid), int(ability), ability_name,
                                         attack_pos=here)
    finally:
        AA._round_fix64, AA.calculate_average = o_round, o_avg
    # MEME regle de selection que `_native` : TOUS les events de la cible principale, dans l'ordre.
    mains = [e for e in evs if e.target == int(tid)] or (evs[:1] if evs else [])
    if not mains:
        return None, 0
    return (tuple((e.prediction.accurate_health_damage.min,
                   e.prediction.accurate_health_damage.max,
                   e.prediction.applied_hits) for e in mains), len(evs))


def _measure_arm(sid, sf, seed, label, level, caster, victim, ability, ability_name,
                 board, center, mult, armor_target=None, nc: bool = False,
                 victim_hp=None) -> dict:
    rid = None
    regime = None
    try:
        rid = _build(sf, seed, caster, victim, board, level, mult, armor_target, victim_hp)
        dv = _view(sid, rid)
        ids = {}
        for v in (caster, FILLER_P, victim, FILLER_A):
            u = next((x for x in (dv.get("units") or [])
                      if x.get("visualId") == v and x.get("alive")), None)
            if u is None:
                return {"label": label, "error": "unite absente du build : %s" % v}
            ids[v] = int(u["id"])
        _place_ring(sid, rid, ids, caster, center)
        cid, tid = ids[caster], ids[victim]
        ctx, _dv2 = _ctx(sid, rid, cid)
        scene = ctx.scene
        mm = _minmax_config(scene, cid, ability, ability_name)
        if mm is None:
            return {"label": label, "error": "config d'ability introuvable"}
        mn, mx, lvl_eff, mult_eff = mm
        mp = ctx.me.get("pos") or {}
        here = (mp.get("col"), mp.get("row"))
        if nc:
            # Le REGIME d'abord : hors regime, une capture nulle accuserait le MONTAGE, pas le port.
            regime = _nc_regime(sid, rid, cid, tid, ability)
            if not regime.get("reached"):
                return {"label": label, "regime": regime, "no_regime": True,
                        "error": "MONTAGE HORS REGIME NC : %s" % regime.get("why")}
            foes = [ids[victim], ids[FILLER_A]]
            nat, n_nat = _native_nc(sid, rid, cid, tid, ability)
            _p = {name: _offline_nc(scene, ctx, cid, tid, ability, ability_name, here, fn, foes)
                  for name, fn in VARIANTS}
            ports = {k: v[0] for k, v in _p.items()}
            shipped, n_port, has_ability = _offline_nc(scene, ctx, cid, tid, ability, ability_name,
                                                       here, None, foes)
            if not has_ability:
                # TROISIEME issue (#362) : le playbook NC n'a construit AUCUNE prediction d'ABILITY
                # -- son gate predictif a mordu (`WillNormalAttackKill` -> `continue`). Le natif a
                # RAISON, il n'y a simplement rien de l'arrondi a mesurer ici. Rougir accuserait le
                # port ; c'est le MONTAGE qui n'atteint pas le regime.
                return {"label": label, "regime": regime, "no_regime": True,
                        "error": "MONTAGE HORS REGIME NC : le gate predictif du playbook a saute "
                                 "la cible (aucune prediction d'ability construite) -- piloter les "
                                 "PV de la cible (--victim-hp)"}
        else:
            nat, n_nat = _native(sid, rid, cid, tid, ability)
            _p = {name: _offline(scene, cid, tid, ability, ability_name, here, fn)
                  for name, fn in VARIANTS}
            ports = {k: v[0] for k, v in _p.items()}
            shipped, n_port = _offline(scene, cid, tid, ability, ability_name, here, None)
    finally:
        if rid is not None:
            _r(sid, "disposeRunner", {"runnerId": rid}, 30)

    s = int(mn) + int(mx)
    return {"label": label, "runner": rid, "level_asked": level, "level_eff": lvl_eff,
            "mult_eff": mult_eff, "minDmg": int(mn), "maxDmg": int(mx), "sum": s,
            "sum_mod4": s % 4, "floor": s // 2, "native": nat, "ports": ports,
            "shipped": shipped, "n_events_native": n_nat, "n_events_port": n_port,
            "oracle": "nc" if nc else "comparable", "regime": regime}


def _grade(arm: dict) -> dict:
    """Verdict d'UN bras : quelles variantes egalent le natif, et le bras DISCRIMINE-t-il ?"""
    nat = arm.get("native")
    if not nat:
        # Le REGIME a deja ete verifie en amont pour la face NC : une capture nulle ICI accuse donc
        # bien l'oracle, pas le montage -- et le message NOMME lequel des deux oracles s'est tu.
        arm["error"] = ("ncPlaybookPredict n'a capture AUCUN event (regime NC verifie)"
                        if arm.get("oracle") == "nc"
                        else "aiPlaybookPredict n'a rendu AUCUN event")
        return arm
    arm["match"] = {k: (v == nat) for k, v in arm["ports"].items()}
    arm["shipped_ok"] = (arm.get("shipped") == nat)
    distinct = {json.dumps(v) for v in arm["ports"].values()}
    # Un bras ou toutes les variantes rendent la MEME prediction ne prouve rien (l'ecart d'une
    # unite a ete absorbe en aval) -- cf. l'en-tete, piege herite de #339 sec.4.
    arm["discriminates"] = len(distinct) > 1
    arm["ok"] = bool(arm["shipped_ok"] and arm["discriminates"])
    return arm


def run(seed: int = 34401, state_file=None, verbose: bool = True, caster: str = CASTER,
        victim: str = VICTIM, ability: int = ABILITY, ability_name: str = ABILITY_NAME,
        board: str = BOARD, center=CENTER, lvl_a: int = LVL_A, lvl_b: int = LVL_B,
        mult: int = MULT, armor_target=None, oracle: str = "auto", victim_hp=None) -> dict:
    # GATE DE PERIMETRE (#356). `expected` se DEDUIT d'une dichotomie a deux registres ; une ability
    # ABSENTE DES DEUX n'a pas de reponse -- le `else "trunc"` en fabriquerait une. Le trou etait
    # inatteignable tant que le probe ne parlait qu'aux Comparables ; `--oracle auto` ouvre les
    # playbooks NC, dont beaucoup ne passent AUCUN triplet a `CalculateUtilityFromDamageEvent`
    # (mesure 2026-07-31 : `IdunBattle.AI.Playbook.Loki.DarkTalonStrikePlaybook$$EvaluateNonComparable`
    # score `Fix64(DarkTalonStrikeAbility$$GetAttackTargets(GetTilesInBestLine()).Count)` -- un
    # COMPTE de cibles, aucun degat). Sur celles-la `ncPlaybookPredict` capture legitimement ZERO,
    # et un ECHEC se lirait « bug de port » alors que le natif a raison.
    known = set(AA._PREDICTION_MINMAX_AVERAGE) | set(AA._PREDICTION_MINMAX_RANDOM_READ)
    if int(ability) not in known:
        msg = ("HORS PERIMETRE : %s (%d) n'est dans AUCUN des deux registres d'arrondi "
               "(_PREDICTION_MINMAX_AVERAGE / _PREDICTION_MINMAX_RANDOM_READ) -- son playbook ne "
               "passe pas (damage, profile, hits) a CalculateUtilityFromDamageEvent. Rien a "
               "mesurer ici ; ce n'est ni un OK ni un ECHEC." % (ability_name, ability))
        if verbose:
            print("[344] %s" % msg)
        return {"ok": None, "out_of_scope": True, "reason": msg, "arms": {},
                "montage": {"caster": caster, "victim": victim, "ability": ability,
                            "ability_name": ability_name}}

    # `auto` = la face que le natif IMPOSE (playbook NonComparable -> aucun `Make*Predictions`).
    nc = _is_nc(ability) if oracle == "auto" else (oracle == "nc")
    # DEUXIEME GATE DE PERIMETRE (#356). Cote OFFLINE, la face NC est mesuree par la SEQUENCE que
    # le playbook NC PORTE construit (`playbook.damage_predictions`). Sans playbook porte il n'y a
    # aucune sequence a opposer a la capture, et une comparaison ad hoc ne mesurerait plus
    # l'arrondi. Mesure 2026-07-31 sur `worldKharn`/`1132 KillMaimBurn`, avant son port : natif
    # `(8536, 8536, 4)` contre `(86, 129, 1)` pour le chemin generique -- lu a l'epoque comme un
    # ecart de formule. #362 a tranche : `(8536, 8536, 4)` etait l'attaque NORMALE de Kharn
    # (`weapons[0].hits` = 4, bornes CAPEES a la sante restante), construite par le gate
    # `WillNormalAttackKill` et captee par le meme ctor. Le probe aurait rougi comme un ecart
    # d'ARRONDI ce qui etait un PORT MANQUANT *et* une confusion d'event.
    if nc and not _is_nc(ability):
        msg = ("HORS PERIMETRE : %s (%d) n'a AUCUN playbook NonComparable porte "
               "(engine.playbook.noncomparable.PLAYBOOKS) -- le cote offline mesurerait un chemin "
               "qui n'est pas le sien. L'oracle natif, lui, repond : le porter d'abord."
               % (ability_name, ability))
        if verbose:
            print("[344] %s" % msg)
        return {"ok": None, "out_of_scope": True, "reason": msg, "arms": {},
                "montage": {"caster": caster, "victim": victim, "ability": ability,
                            "ability_name": ability_name}}

    sid = _resolve_session()
    sf = Path(state_file) if state_file else (PYDIR.parents[1] / "logs" / "p344.json")
    sf.parent.mkdir(parents=True, exist_ok=True)

    arms = {}
    for key, label, lvl, sd in (("a", "A (3 mod 4 -- le natif MONTE)", lvl_a, seed),
                                ("b", "B (1 mod 4 -- le natif DESCEND)", lvl_b, seed + 1)):
        arm = _measure_arm(sid, sf, sd, label, lvl, caster, victim, ability, ability_name,
                           board, center, mult, armor_target, nc=nc, victim_hp=victim_hp)
        if not arm.get("error"):
            _grade(arm)
        arms[key] = arm

    # TROIS ISSUES, JAMAIS DEUX (#356 sec.6, etendu #362) : un bras hors REGIME ne rougit pas comme
    # un ecart d'arrondi -- il rend NON CONFRONTE (rc 2), et NOMME le levier de pilotage manquant.
    no_regime = [k for k in ("a", "b") if arms[k].get("no_regime")]
    if no_regime:
        msg = ("NON CONFRONTE : bras %s hors regime NC -- %s"
               % (",".join(no_regime), arms[no_regime[0]].get("error")))
        if verbose:
            print("[344] %s" % msg)
        return {"ok": None, "not_confronted": True, "reason": msg, "arms": arms,
                "oracle": "nc" if nc else "comparable",
                "montage": {"caster": caster, "victim": victim, "ability": ability,
                            "ability_name": ability_name, "board": board, "center": tuple(center),
                            "lvl_a": lvl_a, "lvl_b": lvl_b, "mult": mult,
                            "armor_target": armor_target, "victim_hp": victim_hp}}

    # Les DEUX bras doivent etre dans le regime ANNONCE, sinon le pilotage du niveau n'a pas pris.
    regimes_ok = (arms["a"].get("sum_mod4") == 3 and arms["b"].get("sum_mod4") == 1)
    nul_on_both = [n for n, _fn in VARIANTS
                   if all((arms[k].get("match") or {}).get(n) for k in ("a", "b"))]
    # Ce que le REGISTRE de `active_ability` prevoit pour CETTE ability : `to_even` si son playbook
    # passe `MinMaxDamageAverage` (famille (a)), `trunc` sinon (famille (b) = `RandomAmount` +
    # `AAmountFormula$$CalculateAverage`). Le probe verifie que le LIVE tranche dans ce sens.
    expected = "to_even" if int(ability) in AA._PREDICTION_MINMAX_AVERAGE else "trunc"
    family = ("(a) MinMaxDamageAverage -> Half -> Fix64.Round(0)"
              if expected == "to_even"
              else "(b) MinMaxDamage(false) = RandomAmount -> CalculateAverage (troncature)")
    ok = bool(regimes_ok and all(arms[k].get("ok") for k in ("a", "b"))
              and nul_on_both == [expected])

    if verbose:
        print("[344] montage : %s / %s (%d) -> %s sur %s, anneau centre en %s"
              % (caster, ability_name, ability, victim, board, tuple(center)))
        print("[344] oracle : %s (%s)"
              % ("ncPlaybookPredict (face NONCOMPARABLE)" if nc
                 else "aiPlaybookPredict (face COMPARABLE)",
                 "auto" if oracle == "auto" else "force par --oracle"))
        print("[344] famille lue au decompile : %s -> variante attendue = %s" % (family, expected))
        for key in ("a", "b"):
            arm = arms[key]
            if arm.get("error"):
                print("\n=== bras %s === ERREUR : %s" % (key, arm["error"]))
                continue
            if arm.get("regime"):
                print("\n[344] regime NC du bras %s : caster=%s cible=%s dist=%s reason=%s %s"
                      % (key, arm["regime"].get("casterPos"), arm["regime"].get("targetPos"),
                         arm["regime"].get("dist"), arm["regime"].get("targetReasonHex"),
                         arm["regime"].get("targetReasons")))
            print("\n=== bras %s === %s" % (key, arm["label"]))
            print("  niveau demande=%d effectif=%d mult=%d | minDmg=%d maxDmg=%d somme=%d "
                  "(mod4=%d) floor=%d"
                  % (arm["level_asked"], arm["level_eff"], arm["mult_eff"], arm["minDmg"],
                     arm["maxDmg"], arm["sum"], arm["sum_mod4"], arm["floor"]))
            print("  natif   = %-34s (events natif=%d port=%d)"
                  % (str(arm["native"]), arm["n_events_native"], arm["n_events_port"]))
            print("  LIVRE   = %-34s %s"
                  % (str(arm["shipped"]), "== NATIF" if arm["shipped_ok"] else "!= NATIF"))
            for name, _fn in VARIANTS:
                print("    %-9s port=%-34s %s"
                      % (name, str(arm["ports"][name]), "== NATIF" if arm["match"][name] else "!="))
            print("  bras discriminant : %s" % arm["discriminates"])
        print("\n=== VERDICT ===")
        print("  regimes pilotes comme annonces : %s" % regimes_ok)
        print("  variantes egales au natif sur les DEUX bras : %s" % (nul_on_both or "aucune"))
        print("  attendue par le registre : %s" % expected)
        print("  -> %s" % ("OK" if ok else "ECHEC"))

    return {"ok": ok, "arms": arms, "regimes_ok": regimes_ok, "nul_on_both_arms": nul_on_both,
            "expected_variant": expected, "family": family, "oracle": "nc" if nc else "comparable",
            "montage": {"caster": caster, "victim": victim, "ability": ability,
                        "ability_name": ability_name, "board": board, "center": tuple(center),
                        "lvl_a": lvl_a, "lvl_b": lvl_b, "mult": mult,
                        "armor_target": armor_target, "victim_hp": victim_hp}}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=34401)
    ap.add_argument("--state-file", default=None)
    ap.add_argument("--caster", default=CASTER)
    ap.add_argument("--victim", default=VICTIM)
    ap.add_argument("--ability", type=int, default=ABILITY)
    ap.add_argument("--ability-name", default=None,
                    help="nom gameconfig de l'ability (defaut : resolu depuis --ability)")
    ap.add_argument("--board", default=BOARD, help="board CHOISI (runner.md sec.2), jamais subi")
    ap.add_argument("--center", default="%d,%d" % CENTER)
    ap.add_argument("--lvl-a", type=int, default=LVL_A, help="niveau dont minDmg+maxDmg = 3 mod 4")
    ap.add_argument("--lvl-b", type=int, default=LVL_B, help="niveau dont minDmg+maxDmg = 1 mod 4")
    ap.add_argument("--mult", type=int, default=MULT)
    ap.add_argument("--armor-target", type=int, default=None,
                    help="armure FORCEE de la cible (0 = etage armure retire, cf. _build)")
    ap.add_argument("--victim-hp", type=int, default=None,
                    help="PV FORCES de la cible (Health+RemainingHealth). Levier de REGIME des "
                         "playbooks NC a gate predictif : sans lui, WillNormalAttackKill saute la "
                         "cible et aucune prediction d'ability n'est construite (#362)")
    ap.add_argument("--oracle", choices=("auto", "comparable", "nc"), default="auto",
                    help="face mesuree : `auto` = `nc` des que l'ability a un playbook "
                         "NonComparable porte (#356), sinon `comparable`")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    name = a.ability_name
    if name is None:
        import gameconfig as GC
        name = GC.ability_name(a.ability) or ABILITY_NAME
    out = run(seed=a.seed, state_file=a.state_file, caster=a.caster, victim=a.victim,
              ability=a.ability, ability_name=name, board=a.board,
              center=tuple(int(x) for x in a.center.split(",")),
              lvl_a=a.lvl_a, lvl_b=a.lvl_b, mult=a.mult, armor_target=a.armor_target,
              oracle=a.oracle, victim_hp=a.victim_hp)
    if a.json:
        print(json.dumps(out, indent=1, default=str))
    if out.get("out_of_scope") or out.get("not_confronted"):
        return 2            # ni OK ni ECHEC : rien de mesurable / regime non atteint
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
