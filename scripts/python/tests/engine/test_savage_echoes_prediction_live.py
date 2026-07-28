"""SavageEchoes (1230, Cezare `bloodTerminator`) -- face DECISION (PREDICTION DE DEGAT), confrontee au LIVE.

`IdunBattle.AI.Playbook.Loki.SavageEchoesPlaybook$$MakeDamagePredictions` ne passe PAS la
`IdunBattle.Entities.Abilities.AActiveAbility$$MinMaxDamage` generique en 6e argument de
`IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$GenerateMultiHitAttackPredictions`,
mais la formule PROPRE de l'ability,
`IdunBattleLogic.Entities.Abilities.Active.Loki.SavageEchoesAbility$$GetDamage` :

    Sum( MinMaxDamage(minDmg 0xc, maxDmg 0xd),
         Multiply( Get(GetVariableForLevel(config, 8 = extraDmg)),
                   Count( CanAddUnit( AdjacentTiles(Owner@0x148) ) ) ) )

Le chemin de prediction GENERIQUE s'arretait a `MinMaxDamage` -> l'IA sous-evaluait 1230 (mesure #27-3 :
paire offline 7.8931 contre native 12.0496 sur le montage (4,8)/(5,8)). Le handler
`_savage_echoes_inputs` (`engine/playbook/prediction/abilities.py`) evalue desormais l'arbre PARTAGE
`SavageEchoesAbility.get_damage_formula` -- le MEME que la face COMBAT
(`engine/runner/abilities/bloodangels.py`), un seul artefact natif, un seul port.

CE QUE CE TEST GARDE (oracle = `aiPlaybookPredict`, invocation DIRECTE du playbook natif -- PAS
`aiPredict`, qui est le preview Attack-based `GetAllPredictions` et ment sur l'ability, cf. #96/#101a) :
  A. BIT-EXACT : (healthDmgMin, healthDmgMax, appliedHits) natifs == prediction OFFLINE, sur PLUSIEURS
     comptes de tuiles libres pilotes par le montage (le caster est pose sur un hub a 6 voisins
     marchables, puis on BOUCHE ses voisins un a un).
  B. DISCRIMINANT : la MEME prediction, handler 1230 RETIRE du registre, DIVERGE (des que le compte > 0)
     -- sans quoi le test passerait meme si le terme etait ignore.
  C. MONOTONIE : boucher une tuile adjacente FAIT BAISSER le degat predit, natif comme offline, du MEME
     pas -- et un ALLIE bouche autant qu'un ENNEMI (`CanAddUnit` teste l'occupation, pas l'equipe).

AUCUN scalaire de gameplay n'est fige : les bornes viennent du natif a chaque montage.

PORTEUR HORS POOL : `bloodTerminator` est absent du seed BC capture -> on l'INJECTE avec SES CONFIGS
D'ABILITY via `catalog_inject.py` (une COPIE du seed sous `logs/`, jamais le seed partage). C'est ce qui
distingue ce harnais du clone nu de `tests/engine/runner/test_savage_echoes_live.py` : les variables
exotiques (extraDmg 8) sont materialisees, donc `GetVariableForLevel` ne throw pas et le playbook natif
repond.

ASCII only.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[2]                 # scripts/python
ROOT = PYDIR.parents[1]                                     # racine repo
SEED_BC = ROOT / "logs" / "bc_savage_pred.json"
CASTER_VIS, TARGET_VIS = "bloodTerminator", "tauCrisis"
ALLY_VIS, FOE_VIS = "ultraCalgar", "blackTerminator"
ABILITY = 1230


def _seed_bc() -> Path | None:
    """Seed BC augmentee de `bloodTerminator` + ses configs d'ability (catalog_inject)."""
    if SEED_BC.exists():
        return SEED_BC
    SEED_BC.parent.mkdir(parents=True, exist_ok=True)
    p = subprocess.run([sys.executable, "catalog_inject.py", "--units", CASTER_VIS,
                        "--out", str(SEED_BC)], cwd=str(PYDIR), capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    return SEED_BC if SEED_BC.exists() else None


def _units(rpc, rid):
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    return dv, {u.get("visualId"): u for u in (dv.get("units") or []) if u.get("alive")}


def _move(rpc, rid, uid, col, row):
    rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": uid, "to": {"col": col, "row": row}}}, 60)


def _native(rpc, rid, cid, tid):
    r = rpc("aiPlaybookPredict", {"runnerId": rid, "unitId": cid, "targetId": tid,
                                  "abilityType": ABILITY}, 120)
    return [(e.get("healthDmgMin"), e.get("healthDmgMax"), e.get("appliedHits"))
            for e in ((r or {}).get("events") or [])]


def _offline(rpc, rid, cid, tid, with_handler: bool):
    """Prediction OFFLINE (`make_damage_predictions`) pour (cid, tid, 1230), handler 1230 pose ou retire."""
    from engine import weights as W
    from engine.playbook import scene as _scene
    from engine.ai import context as AICTX
    from engine.playbook.prediction import abilities as PA

    _r = lambda m, b, t=60: rpc(m, b, t)                      # noqa: E731
    dv = _r("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    mov = _r("aiMovableTiles", {"runnerId": rid}, 60)
    mov_by_unit = {u.get("unitId"): u for u in ((mov or {}).get("units") or [])}
    ctx = AICTX.build(_r, rid, dv, mov_by_unit, cid, W.load(), _scene.build_predictor(_r, rid))
    mp = ctx.me.get("pos") or {}
    here = (mp.get("col"), mp.get("row"))
    saved = PA._MAKE_DMG_INPUT_OVERRIDES.pop(ABILITY, None)
    assert saved is not None, "le handler 1230 doit etre au registre _MAKE_DMG_INPUT_OVERRIDES"
    if with_handler:
        PA._MAKE_DMG_INPUT_OVERRIDES[ABILITY] = saved
    try:
        evs = PA.make_damage_predictions(ctx.scene, cid, tid, ABILITY, "SavageEchoes", attack_pos=here)
    finally:
        PA._MAKE_DMG_INPUT_OVERRIDES[ABILITY] = saved
    return ctx, [(e.prediction.accurate_health_damage.min, e.prediction.accurate_health_damage.max,
                  e.prediction.applied_hits) for e in evs]


def _free_tiles(ctx, cid):
    """`Count(CanAddUnit(AdjacentTiles(caster)))` recalcule OFFLINE (diag du montage)."""
    from engine.dsl import nodes as dsl
    sc = ctx.scene
    by_id = {u.get("id"): u for u in (sc.units or [])}
    dctx = dsl.DslContext(units=sc.units, caster=by_id.get(cid), board=getattr(sc, "board", None))
    return dsl.Count(dsl.CanAddUnit(dsl.AdjacentTiles(dsl.Caster()))).evaluate(dctx)


def _stage(rpc, rid, cid, tid, label):
    """(free_tiles, natif, offline AVEC, offline SANS) + assertions A et B pour UN montage."""
    ctx, on = _offline(rpc, rid, cid, tid, True)
    _, off = _offline(rpc, rid, cid, tid, False)
    nat = _native(rpc, rid, cid, tid)
    free = _free_tiles(ctx, cid)
    assert nat, f"{label}: aiPlaybookPredict n'a rendu AUCUN event (playbook natif muet)"
    assert on == nat, (f"{label} (free_tiles={free}) : prediction OFFLINE {on} != NATIVE {nat} "
                       f"-- l'arbre SavageEchoesAbility$$GetDamage n'est pas mirrore")
    if free > 0:
        assert off != nat, (f"{label} (free_tiles={free}) : la prediction SANS le handler 1230 vaut "
                            f"deja {off} == natif -> le test ne discrimine RIEN (terme extraDmg x "
                            f"free-tiles inoperant ou deja porte ailleurs)")
    print("[savage-pred] %-38s free=%s natif=%s offSANS=%s" % (label, free, nat, off))
    return free, nat, on, off


def test_savage_echoes_prediction_free_tile_term(live_session, rpc, build_runner):
    """A/B/C : la prediction de degat de 1230 porte `extraDmg x Count(CanAddUnit(AdjacentTiles(caster)))`
    et suit le compte de tuiles libres, bit-exact contre le playbook natif."""
    from engine.entities.pathfinding.board import Board

    bc = _seed_bc()
    if bc is None:
        pytest.skip("catalog_inject KO (seed BC de reference absente ?)")
    rid = build_runner("909", extra=["--seed-bc", str(bc), "--board", "MC1_67",
                                     "--p-units", f"{CASTER_VIS},{ALLY_VIS}",
                                     "--a-units", f"{TARGET_VIS},{FOE_VIS}",
                                     "--hp-player", "100000", "--hp-target", "60000"])["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="native_sym")
    dv, by_vis = _units(rpc, rid)
    for v in (CASTER_VIS, TARGET_VIS, ALLY_VIS, FOE_VIS):
        if v not in by_vis:
            pytest.skip(f"unite {v} absente du build (roster)")
    cid, tid = by_vis[CASTER_VIS]["id"], by_vis[TARGET_VIS]["id"]
    ally, foe = by_vis[ALLY_VIS]["id"], by_vis[FOE_VIS]["id"]

    # HUB = tuile marchable a 6 voisins TOUS marchables -> compte pilotable sur 3 valeurs au moins.
    hub = next((t for t in sorted(board.by_id)
                if board.walkable(t)
                and len([n for n in board.neighbours_native(t) if board.walkable(n)]) == 6), None)
    if hub is None:
        pytest.skip("board sans tuile a 6 voisins marchables (montage non discriminant)")
    hc = board.coord(hub)
    nbs = [board.coord(n) for n in board.neighbours_native(hub) if board.walkable(n)]

    _move(rpc, rid, cid, hc[0], hc[1])
    _move(rpc, rid, tid, nbs[0][0], nbs[0][1])            # cible adjacente (SavageEchoes = melee)
    # bouchons GARES loin du hub pour le montage de reference
    far = [board.coord(t) for t in sorted(board.by_id)
           if board.walkable(t) and board.coord(t) not in nbs and board.coord(t) != tuple(hc)]
    _move(rpc, rid, ally, far[0][0], far[0][1])
    _move(rpc, rid, foe, far[-1][0], far[-1][1])
    f0, nat0, _, _ = _stage(rpc, rid, cid, tid, "hub degage")

    _move(rpc, rid, ally, nbs[1][0], nbs[1][1])           # ALLIE du caster sur un voisin
    f1, nat1, _, _ = _stage(rpc, rid, cid, tid, "+1 ALLIE adjacent")

    _move(rpc, rid, foe, nbs[2][0], nbs[2][1])            # ENNEMI sur un autre voisin
    f2, nat2, _, _ = _stage(rpc, rid, cid, tid, "+1 ENNEMI adjacent")

    # C. le compte DESCEND et le degat natif descend AVEC (allie et ennemi bouchent PAREIL).
    assert f0 > f1 > f2, f"le montage n'a pas fait varier le compte de tuiles libres : {f0}, {f1}, {f2}"
    assert nat0[0][0] > nat1[0][0] > nat2[0][0], \
        (f"degat natif non decroissant quand on bouche les tuiles adjacentes : "
         f"{nat0} -> {nat1} -> {nat2} (le terme extraDmg x free-tiles ne serait pas geometrique)")
    step_ally = nat0[0][0] - nat1[0][0]
    step_foe = nat1[0][0] - nat2[0][0]
    assert step_ally == step_foe, \
        (f"un ALLIE ({step_ally}) et un ENNEMI ({step_foe}) ne bouchent pas pareil -- `CanAddUnit` "
         f"teste l'OCCUPATION de tuile, pas l'equipe")
