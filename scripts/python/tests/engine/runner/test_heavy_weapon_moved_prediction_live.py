"""#266 -- GATE NO-MOVE de `HeavyWeapon_ExtraDmg` (effet 1008) sur la face **PREDICTION**, confronte
au LIVE dans les DEUX sens. Pendant prediction de `test_heavy_weapon_moved_gate_live` (face COMBAT).

CE QUE LA PREDICTION NATIVE VOIT SOUS `HasFlag(Self, UnitFlag.Moved)` -- deux termes, decompile relu :

  1. **le flag REEL**. `IdunBattle.Core.Services.DamageCalculations$$CalculateAttackerModifiersForPrediction`
     ne substitue QUE la POSITION (`AbilityEntities+0x40`, tuile de l'ATTAQUANT prise du parametre,
     alors que celle de la CIBLE est re-derivee par `EntityExtensions$$GetMainTile`). Les conditions
     d'effet sont deleguees aux membres 0x16/0x17/0x18 avec cette meme `AbilityEntities`, et
     `IdunBattle.Entities.Conditions.HasFlagAbilityTrigger$$ShouldTrigger` interroge
     `IdunBattle.Entities.Components.UnitFlagsComponent$$Has` sur l'ECS COURANT -- aucun flag n'y est
     maquille.
  2. **la tuile SIMULEE**. Une prediction depuis une tuile AUTRE que la tuile courante passe par
     `IdunBattle.Operations.SimulateEffectsOperation$$DoActionInSimulatedTile`, qui appelle le MEME
     `IdunBattle.Entities.UnitExtensions$$SetMovedFlag` que `MoveUnitOperation$$Execute` avant
     d'executer l'action, puis restaure. Le choix est lu verbatim dans
     `SimulateEffectsOperation.u003Cu003Ec__DisplayClass5_0u003C...u003E$$u003CExecuteu003Eb__0` :
     `op_Equality(GetUnitPosition(state, unit), simulatedPos)` -> `DoActionInSimulatedOnSameTile`
     (aucun `SetMovedFlag`), sinon `DoActionInSimulatedTile`.

Le port ne portait QUE le terme 2 (`attack_pos != scene.pos(uid)`). `prediction.prediction_has_moved`
porte desormais les deux, le flag venant de `combatSnapshot.units[].unitFlags` ->
`Scene.moved_by_id`.

MONTAGE -- RUNNERS JUMEAUX. Meme seed, meme board, meme roster, meme geometrie, caster sur LA MEME
tuile T1 ; le flag `Moved` est le SEUL ecart :
  * runner A -- deux cycles de tour PUIS le pas vers T1 est joue AVANT le dernier cycle : le caster
    est en T1 avec `Moved` PURGE par `StartTurnOperation$$Execute` -> `RemoveTurnFlags` ;
  * runner B -- meme nombre de cycles, mais le pas est joue APRES : `Moved` est POSE.
Deux runners plutot qu'un, parce que l'instance de prediction par defaut est
`CachedDamagePredictionQuery` (cle {unit, tile, ability}) : re-interroger la MEME tuile apres une
mutation pourrait rendre une valeur STALE, et une egalite se lirait a tort comme « le flag n'a aucun
effet ».

ORACLE NATIF = `pairUtility` (`ComparablePlaybook$$CalculateUtilityFromPredictions`), qui ne lit
qu'un Fix64. Ce n'est PAS `aiPlaybookPredict` / `aiPredict` : sur le build `rnca9r7q6c` leur decodage
de `ProbableDamageEvent` / `DamagePredictionResult` est PERIME (`healthDmg{Min,Max}` a 0 avec un
`hpBefore` correct, `targetId` a `null`, `appliedHits` valant un PV) -- regression d'outillage
PRE-EXISTANTE, cote hooks. L'utilite est MONOTONE en degat : elle donne le SENS ; la MAGNITUDE exacte
(x1.25 = `traitVariables.heavyWeaponExtraDmg`) est lue cote port, et le contrefactuel ci-dessous
interdit qu'elle vienne d'autre chose que du flag.

CIBLE = `orksNob` (ni Mechanical, ni MkXGravis, ni TerminatorArmour) -> la `DamageCondition` de
`HeavyGravCannonEffect` est FAUSSE, ce passif est INERTE. CASTER = `admecDestroyer`, dont
`HeavyWeapon` est le SEUL trait a modifier le degat en pourcentage.

Aucune valeur de degat en dur : le ratio attendu vient de la config. ASCII only.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(__file__))      # import du helper sibling
from _config_oracle import trait_variable           # noqa: E402

import hexgeo
from engine.entities.pathfinding.board import Board

PYDIR = Path(__file__).resolve().parents[3]
ROOT = PYDIR.parents[1]

CASTER_VIS = "admecDestroyer"      # Sy-Gex : trait HeavyWeapon (+25% ranged not-moved), portee 3
TARGET_VIS = "orksNob"             # HeavyGravCannon INERTE (aucun des 3 traits de sa condition)
FILLER_VIS = "necroWarden"
NORMAL_ATTACK = 69                 # `Loki_NormalAttack` de admecDestroyer (ActiveAbilityType per-unit)
SEED = "26610"
BOARD = "MC1_67"


def _pos(u):
    p = (u or {}).get("pos") or {}
    return (p.get("col"), p.get("row")) if p.get("col") is not None else None


def _find(dv, vis):
    return next((u for u in (dv.get("units") or [])
                 if u.get("visualId") == vis and u.get("alive")), None)


def _find_id(dv, uid):
    return next((u for u in (dv.get("units") or []) if u.get("id") == uid), None)


def _build(rpc):
    """Runner ISOLE dedie (state-file absolu unique). Rend (rid, state_file)."""
    sf = ROOT / "logs" / "runners" / f"hwpred-{uuid.uuid4().hex[:8]}.json"
    sf.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", SEED, "--state-file", str(sf),
         "--board", BOARD, "--roster", "1", "--p-units", CASTER_VIS,
         "--a-units", f"{TARGET_VIS},{FILLER_VIS}", "--hp-target", "300000"],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not sf.exists():
        pytest.skip(f"build KO: {(proc.stderr or proc.stdout or '')[-300:]}")
    return int(json.loads(sf.read_text())["runnerId"]), sf


def _dv(rpc, rid):
    return rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)


def _move(rpc, rid, uid, c):
    rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": uid, "to": {"col": c[0], "row": c[1]}}}, 60)


def _my_turn(rpc, rid, owner, max_turns=10):
    for _ in range(max_turns):
        if _dv(rpc, rid).get("currentPlayer") == owner:
            return True
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    return False


def _cycle(rpc, rid, owner):
    rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    return _my_turn(rpc, rid, owner)


def _flags(rpc, rid, uid):
    snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
    row = next((u for u in (snap.get("units") or []) if u.get("entityId") == uid), {})
    return row.get("unitFlags"), (snap.get("unitFlagTypes") or {}).get("Moved")


def _stage(rpc, rid, board, keep_moved_flag: bool):
    """Geometrie COMMUNE puis pas du caster vers T1. Le SEUL ecart entre les deux variantes est
    l'ORDRE du dernier cycle de tour (donc le flag), pas la position finale ni le nombre de tours."""
    walk = [board.coord(t) for t in sorted(board.by_id) if board.walkable(t)]
    elev = {(t["col"], t["row"]): int(t.get("elevation") or 0) for t in board.by_id.values()}

    def nb_free(c):
        return [n for n in board.neighbours(board.id_at(c[0], c[1])) if board.walkable(n)]

    dv = _dv(rpc, rid)
    me = _find(dv, CASTER_VIS)
    if me is None:
        pytest.skip(f"{CASTER_VIS} absent du build")
    owner = me.get("owner")
    if not _my_turn(rpc, rid, owner):
        pytest.skip("tour du caster non atteint")
    dv = _dv(rpc, rid)
    me, tgt = _find(dv, CASTER_VIS), _find(dv, TARGET_VIS)
    if me is None or tgt is None:
        pytest.skip("caster/cible absents")
    cid, tid = me["id"], tgt["id"]

    open_tiles = [c for c in walk if len(nb_free(c)) == 6]
    if not open_tiles:
        pytest.skip("board sans tuile a 6 voisins marchables")
    home = open_tiles[len(open_tiles) // 2]
    _move(rpc, rid, cid, home)
    home = _pos(_find_id(_dv(rpc, rid), cid)) or home
    spots = [c for c in open_tiles if hexgeo.distance(c, home) == 2 and c != home]
    if not spots:
        pytest.skip(f"aucune tuile degagee a distance 2 de {home}")
    _move(rpc, rid, tid, spots[0])
    dv = _dv(rpc, rid)
    far = [c for c in walk if hexgeo.distance(c, home) > 6]
    for i, u in enumerate(dv.get("units") or []):
        if u.get("alive") and u.get("id") not in (cid, tid) and i < len(far):
            _move(rpc, rid, u["id"], far[i])

    # Le caster a consomme son pas pour rejoindre `home` : premier cycle avant de choisir T1.
    if not _cycle(rpc, rid, owner):
        pytest.skip("retour au tour du caster impossible")
    dv = _dv(rpc, rid)
    tpos = _pos(_find_id(dv, tid))
    mt = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
    row = next((x for x in ((mt or {}).get("units") or []) if x.get("unitId") == cid), None)
    cands = [c for c in ((t["col"], t["row"]) for t in ((row or {}).get("tiles") or []))
             if c != home and elev.get(c) == elev.get(home)
             and hexgeo.distance(c, tpos) == hexgeo.distance(home, tpos)]
    if not cands:
        pytest.skip(f"aucune tuile equivalente (meme elevation, meme distance) atteignable de {home}")
    t1 = cands[0]

    if keep_moved_flag:
        if not _cycle(rpc, rid, owner):          # 2e cycle AVANT le pas -> le flag survit
            pytest.skip("retour au tour du caster impossible")
        _move(rpc, rid, cid, t1)
    else:
        _move(rpc, rid, cid, t1)
        if not _cycle(rpc, rid, owner):          # 2e cycle APRES le pas -> le flag est purge
            pytest.skip("retour au tour du caster impossible")
    if _pos(_find_id(_dv(rpc, rid), cid)) != t1:
        pytest.skip(f"le caster n'a pas atteint {t1}")
    return cid, tid, t1, tpos


def _native_utility(rpc, rid, cid, tid):
    r = rpc("pairUtility", {"runnerId": rid, "unitId": cid, "targetId": tid,
                            "abilityType": NORMAL_ATTACK}, 90)
    if not (isinstance(r, dict) and r.get("ok")):
        pytest.skip(f"pairUtility KO: {r}")
    return r.get("utility")


def _port_scene(rpc, rid):
    from engine.playbook import scene as SC
    from engine.playbook.scene import Scene
    predictor = SC.build_predictor(lambda m, b=None, t=120: rpc(m, b, t), rid)
    if predictor is None:
        pytest.skip("build_predictor KO (combatSnapshot indispo)")
    sctx = SC.step_context(predictor, _dv(rpc, rid))
    return Scene.from_predictor_sctx(predictor, sctx, None)


def _port_pred(scene, cid, tid):
    from engine.playbook.prediction import make_normal_attack_predictions
    ev = make_normal_attack_predictions(scene, cid, tid, attack_pos=scene.pos(cid))
    if ev is None:
        pytest.skip("make_normal_attack_predictions rend None")
    return (ev.prediction.accurate_health_damage.min, ev.prediction.accurate_health_damage.max)


def _measure(rpc, keep_moved_flag: bool):
    rid, sf = _build(rpc)
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            pytest.skip("boardGraph indispo")
        board = Board(bg["tiles"], adjacency="native_sym")
        cid, tid, t1, tpos = _stage(rpc, rid, board, keep_moved_flag)
        flags, moved_id = _flags(rpc, rid, cid)
        assert isinstance(flags, list), (
            f"combatSnapshot.units[{cid}].unitFlags = {flags!r} : canal NON MESURE -- `None` "
            f"(capteur mort) n'est pas `[]` (lu, aucun flag). Sans lui la face PREDICTION redevient "
            f"aveugle au flag et le +25% ranged revient en silence")
        assert (moved_id in flags) is keep_moved_flag, (
            f"protocole casse : flag Moved={moved_id in flags} alors que le montage visait "
            f"{keep_moved_flag} (unitFlags={flags})")
        scene = _port_scene(rpc, rid)
        assert scene.has_moved(cid) is keep_moved_flag, (
            f"`Scene.has_moved` rend {scene.has_moved(cid)!r} alors que le live porte "
            f"{keep_moved_flag} -- le canal `combatSnapshot.unitFlags` -> `Scene.moved_by_id` "
            f"n'arrive pas jusqu'a la Scene")
        return {"nat": _native_utility(rpc, rid, cid, tid), "port": _port_pred(scene, cid, tid),
                "scene": scene, "cid": cid, "tid": tid, "t1": t1, "tpos": tpos}
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 20)
        except Exception:
            pass
        try:
            sf.unlink()
        except Exception:
            pass


def test_heavy_weapon_moved_gate_prediction_live(live_session, rpc):
    """Runners jumeaux, MEME tuile, le flag `Moved` seul change.

    (a) NATIF : l'utilite du couple (attaque normale, cible) CHUTE quand le caster a bouge -> la
        prediction native LIT le flag ; sans (a) tout le reste serait de l'auto-confirmation.
    (b) PORT : le degat predit chute d'EXACTEMENT `traitVariables.heavyWeaponExtraDmg` (+25%), lu
        dans la config, jamais code en dur.
    (c) CONTREFACTUEL, dans les DEUX sens : forcer `Scene.moved_by_id` a l'hypothese INVERSE fait
        basculer la valeur du port sur celle de l'autre runner. C'est ce qui distingue un gate
        correct d'un bonus purement supprime -- un port qui aurait « enleve HeavyWeapon » rendrait
        deux fois la meme valeur et echouerait (b) comme (c)."""
    pct = trait_variable("HeavyWeapon", "heavyWeaponExtraDmg")     # 25, lu de la config
    a = _measure(rpc, keep_moved_flag=False)                        # flag ABSENT
    b = _measure(rpc, keep_moved_flag=True)                         # flag POSE
    print(f"\n[HWPRED] A(flag absent) natif={a['nat']} port={a['port']} @{a['t1']} cible@{a['tpos']}")
    print(f"[HWPRED] B(flag pose)   natif={b['nat']} port={b['port']} @{b['t1']} cible@{b['tpos']}")

    assert a["t1"] == b["t1"] and a["tpos"] == b["tpos"], (
        f"geometries A/B differentes (caster {a['t1']} vs {b['t1']}, cible {a['tpos']} vs "
        f"{b['tpos']}) -- les deux mesures ne sont pas comparables")
    # (a) le natif lui-meme discrimine
    assert a["nat"] is not None and b["nat"] is not None and a["nat"] > b["nat"], (
        f"utilite native A(flag absent)={a['nat']} <= B(flag pose)={b['nat']} : la prediction "
        f"native ne reagit pas au flag sur ce montage -> il ne prouve rien")
    # (b) magnitude cote port = la variable de trait
    ratio = tuple(round(x / y, 4) for x, y in zip(a["port"], b["port"]))
    exp = 1 + pct / 100.0
    assert all(abs(r - exp) < 0.01 for r in ratio), (
        f"port A/B = {ratio}, attendu {exp} (= 1 + heavyWeaponExtraDmg/100) : le gate no-move de "
        f"la face PREDICTION ne coupe pas exactement le bonus du trait")
    # (c) contrefactuel dans les deux sens : le flag est bien le SEUL levier
    a["scene"].moved_by_id[a["cid"]] = True
    b["scene"].moved_by_id[b["cid"]] = False
    a_forced = _port_pred(a["scene"], a["cid"], a["tid"])
    b_forced = _port_pred(b["scene"], b["cid"], b["tid"])
    print(f"[HWPRED] contrefactuel : A force moved=True -> {a_forced} (attendu {b['port']}) ; "
          f"B force moved=False -> {b_forced} (attendu {a['port']})")
    assert a_forced == b["port"], (
        f"A avec le flag FORCE a True rend {a_forced}, attendu la valeur de B {b['port']} : la "
        f"chute observee ne vient pas du flag")
    assert b_forced == a["port"], (
        f"B avec le flag FORCE a False rend {b_forced}, attendu la valeur de A {a['port']} : la "
        f"chute observee ne vient pas du flag")
