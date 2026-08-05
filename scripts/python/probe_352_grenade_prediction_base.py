#!/usr/bin/env python
"""Probe #352 -- la BASE de prediction de `1098 PlasmaGrenade` et `1048 FragstormGrenadeLauncher`.

CE QUE LE DECOMPILE DIT (`rnca9r7q6c`, lu VERBATIM, une ability apres l'autre -- surtout PAS
generalise de l'une a l'autre : les deux call-sites n'appellent meme pas la MEME fonction)
------------------------------------------------------------------------------------------

`IdunBattle.AI.Playbook.Loki.PlasmaGrenadePlaybook$$MakeDamagePredictions` (1098)

    damage  = IdunBattleLogic.Entities.DSLFormulas$$Get(GetVariableForLevel(config, 0xc = minDmg, state))
    hits    = GetNumberConstant(config, 0x2f = nrOfHits)
    hits2   = GetNumberConstant(config, 0x32 = nrOfHits_2)
    profile = GetDamageProfile(config)                       // Nullable NON vide (Plasma)
    list    = GenerateMultiHitAttackPredictions(caster, casterPosition, target, <selecteur Target>,
                                                damage, hits, profile, null, 0)
    foreach (e in TargetsSelector.SelectUniqueUnits(PlasmaGrenadeAbility$$GetOtherTargets,
                                                    AbilityEntities(Target = target), 3))
        list.AddRange( GenerateMultiHitAttackPredictions(caster, casterPosition, target,
                           <selecteur Target>, damage, hits2, profile, null, 0) );

  -> base = **minDmg SEUL** (`Get` == `Direct`), hits = `nrOfHits` LITTERAL. Le volet secondaire est
     le meme quirk que Stikkbomb (#57e) : `param_4` reste la CIBLE et `param_5` le selecteur `Target`,
     donc les N events portent tous sur la cible principale ; seul leur NOMBRE depend du set.
     `...PlasmaGrenadeAbility$$GetOtherTargets` = `Enemies(caster@0x30, AdjacentUnits(Target@0x60,
     unique: 1, sel: 3), 1)` = ennemis DU CASTER adjacents a la cible, plafonnes a 3 par
     `SelectUniqueUnits`.

`IdunBattle.AI.Playbook.Loki.FragstormGrenadeLauncherPlaybook$$MakeDamagePredictions` (1048)

    maxDmg = GetVariableForLevel(config, 0xd = maxDmg, state)
    hits   = GetNumberConstant(config, 0x2f = nrOfHits)
    result = battleQuery.GetAttackPrediction(caster, target, casterPosition,
                                             Nullable(AbilityOrEffect(ability)),
                                             amount: hits * maxDmg, GetDamageProfile(config),
                                             null, default)
    list   = new[] { new ProbableDamageEvent(target, result, null, null) }.ToList();
    if (result.WillBeKill)
        foreach (e in SelectUniqueUnits(FragstormGrenadeLauncherAbility$$GetOtherTargets,
                                        AbilityEntities(Target = target), 3))
            list.Add( new ProbableDamageEvent(target,
                          battleQuery.GetAttackPrediction(e, target, casterPosition, ...,
                                                          amount: maxDmg, ...), null, null) );

  -> AUCUN `GenerateMultiHitAttackPredictions` : appel DIRECT de la surcharge « amount » de
     `IBattleQuery.GetAttackPrediction` (slot d'interface 0x24 -- le generique prend le 0x28 de la
     MEME interface, `Playbook<T>+0x28`). Cette surcharge n'a PAS de parametre `hits` :
     `IdunBattle.Core.Services.BattleQuery$$GetAttackPrediction` transmet **`hits: 1` en dur** a
     `IdunBattle.Core.Services.DamagePredictionQuery$$GetAttackPrediction`.
     => la prediction principale est **UN coup de `nrOfHits x maxDmg`**, pas `nrOfHits` coups d'une
     moyenne. Config 1048 @lvl65 : `6 x 2183 = 13098` contre `avg(1746, 2183) = 1964` x 6.

CE QUE CE PROBE MESURE
----------------------
Oracle = `aiPlaybookPredict` (invocation DIRECTE de `<X>Playbook$$MakeDamagePredictions`), compare a
`engine.playbook.prediction.abilities.make_damage_predictions` sur le MEME etat live. DEUX versions
du port sont confrontees a chaque montage :

  - `apres` = le code LIVRE (entree `_MAKE_DMG_INPUT_OVERRIDES`) ;
  - `avant` = le MEME code, l'entree du registre RETIREE -- c'est-a-dire le chemin generique
    (moyenne min/max + `GetDefaultAttackHits`) qui etait livre avant #352.

Un montage ou `avant` == `apres` ne prouve rien (bras NON discriminant) et fait ECHOUER le verdict
au lieu de le verdir -- meme discipline que #344.

Porteurs (gate de confrontabilite, ventilee) :
  - 1048 : `templAggressor` [lineup, **au pool** `rl_duel build --list-pool`] -> build standard.
  - 1098 : `eldarSmnGuardian` [SUMMON, sans invocateur : aucune ability du gameconfig ne le declare]
    et `eldarNpc1Guardian` [npc]. Amene par CATALOGUE INJECTE + trait `Summon` retire (recette
    case-245 / `probe_243_splash_range_clamp`), qui rend l'unite CONTROLABLE.

ASCII only (cp1252). Usage (depuis scripts/python) :
    python probe_352_grenade_prediction_base.py
    python probe_352_grenade_prediction_base.py --only 1048
"""
from __future__ import annotations

import argparse
import copy
import itertools
import json
import os
import subprocess
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
sys.path.insert(0, str(PYDIR))

import catalog_inject as CI                                          # noqa: E402
import hexgeo                                                        # noqa: E402
import rl_duel as RD                                                 # noqa: E402
from rl_collect_batch import _resolve_session, _rpc                  # noqa: E402

BOARD = "MC1_67"
SEED = 777
RANK = 17
ENEMY = "necroWarden"          # cible TEMOIN : aucun trait de reduction de coups
FILLER_P = "astraBullgryn"
CARRIER_HEALTH = 5000

_seq = itertools.count()


# --------------------------------------------------------------------------- plomberie RPC

def _r(sid, method, body, timeout=90):
    out = _rpc(sid, method, [body], timeout=timeout)
    return out.get("result") if isinstance(out, dict) and "result" in out else out


def _dv(sid, rid):
    return _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 1}, 180)


def _act(sid, rid, action, timeout=90):
    return _r(sid, "applyAction", {"runnerId": rid, "action": action}, timeout)


def _pos(u):
    q = (u or {}).get("pos") or {}
    return (q.get("col"), q.get("row"))


def _by_vis(dv, vis):
    for u in (dv.get("units") or []):
        if u.get("visualId") == vis and u.get("alive"):
            return u
    return None


def _spawn_visual(unit_id: str) -> str:
    """`UnitConfiguration.VisualId` du catalogue = ce que `decisionView` expose ; il DIFFERE de l'`Id`
    gameconfig pour un summon (`eldarSmnGuardian` -> `eldarNpc1Guardian`)."""
    import gameconfig as _G
    return (_G.unit(unit_id) or {}).get("visualId") or unit_id


# --------------------------------------------------------------------------- builds

def _state_file(tag: str) -> Path:
    p = ROOT / "logs" / ("_probe352-%s-%d-%d.json" % (tag, os.getpid(), next(_seq)))
    p.parent.mkdir(parents=True, exist_ok=True)
    p.unlink(missing_ok=True)
    return p


def _build_pool(carrier: str, seed: int, board: str, target_hp=None):
    """Porteur PRESENT au pool -> `rl_duel build` standard. Pas de `--hp-target` : il mettrait
    l'ARMURE de la cible a 0 (runner.md sec.3), or c'est justement l'etage qui separe `1 x 13098`
    de `6 x 1964` le plus nettement.

    `target_hp` passe par `--unit-stat` (patch PER-UNIT du BC deja normalise) et NON par
    `--hp-target`, pour la meme raison : il faut une cible qui SURVIT au coup sans perdre son
    armure. Sans lui, les deux bornes sont clampees aux PV (`min == max`) et le spread +/-20%
    n'est pas observable -- un bras qui ne montre plus qu'un plancher."""
    sf = _state_file("pool")
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--state-file", str(sf),
           "--board", board, "--rank", str(RANK),
           "--p-units", "%s,%s" % (carrier, FILLER_P),
           "--a-units", ",".join([ENEMY] * 3),
           "--crit", "0,0", "--block-target", "0,0", "--no-ai"]
    if target_hp:
        cmd += ["--unit-stat", "%s:Health=%d,RemainingHealth=%d" % (ENEMY, target_hp, target_hp)]
    proc = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not sf.exists():
        raise RuntimeError("build KO : %s" % ((proc.stderr or proc.stdout or "")[-900:]))
    return int(json.loads(sf.read_text())["runnerId"]), sf


def _build_injected(sid, carrier: str, seed: int, board: str, level: int = 1, mult: int = 100):
    """Porteur SUMMON hors pool -> catalogue injecte + trait `Summon` retire (case-245). Le retrait
    n'est pas une levee de gate : `Summon` rend l'unite AUTOMATIQUE
    (`IdunBattle.Entities.UnitExtensions$$IsAutomatic`), le moteur la joue lui-meme et l'oracle ne
    verrait plus qu'une charge consommee."""
    sf = _state_file("inj")
    bc0, added, ab_added, _unres = CI.augment(RD._load_seed_bc(None), [carrier, ENEMY], rank=RANK)
    dump = RD._load_board_dump(board)
    template, _pool, _pool_mow = RD._normalize_and_extract_pool(sid, bc0, RANK, board_dump=dump)
    bc = copy.deepcopy(template)
    e = next((u for u in bc["Units"] if u.get("Id") == carrier), None)
    if e is None:
        raise RuntimeError("%s absent du catalogue BC.Units apres augment" % carrier)
    e["Health"], e["RemainingHealth"] = CARRIER_HEALTH, CARRIER_HEALTH
    e["Traits"] = [t for t in (e.get("Traits") or []) if t != "Summon"]
    # Niveau d'ability PILOTE (meme levier que `rl_duel build --unit-stat`, ecrit VERBATIM dans
    # `BC.Units[]`) : au niveau 1 l'ecart minDmg (7) / avg (8) ne vaut qu'un point, ce qui rendrait
    # le bras a peine discriminant. Le regime EFFECTIF est re-derive du live par `_config_view`.
    e["ActiveAbilityLevel"] = int(level)
    e["AbilityVariablesMultiplierPercentage"] = int(mult)
    RD._patch_predefined_units(bc, [ENEMY] * 3)
    spawns = RD._spawn_points_by_twpi(bc)
    pts = spawns.get(0) or []
    if not pts:
        raise RuntimeError("aucun spawn joueur sur %s" % board)
    pu = [{"unitId": carrier, "playerId": RD.PLAYER_ID_HUMAN,
           "col": int(pts[0][0]), "row": int(pts[0][1])}]
    resp = _rpc(sid, "initAndStart",
                [{"configJson": json.dumps(bc), "seed": seed, "playerUnits": pu,
                  "owner": str(sf.resolve())}], timeout=120)
    rid = ((resp or {}).get("result") or {}).get("runnerId")
    if rid is None:
        raise RuntimeError("initAndStart KO: %s" % json.dumps(resp)[:400])
    sf.write_text(json.dumps({"runnerId": int(rid)}), encoding="utf-8")
    print("  [catalogue] units ajoutees=%s abilities=%s" % (added, ab_added))
    return int(rid), sf


# --------------------------------------------------------------------------- geometrie DRIVEE

def _board(sid, rid):
    from engine.entities.pathfinding.board import Board
    bg = _r(sid, "boardGraph", {"runnerId": rid}, 60)
    return Board(bg["tiles"], adjacency="evenq")


def _neighbours(board, pos):
    return [board.coord(t) for t in board.neighbours(board.id_at(pos[0], pos[1]))]


def _movable(sid, rid, uid):
    mov = _r(sid, "aiMovableTiles", {"runnerId": rid}, 90)
    for m in ((mov or {}).get("units") or []):
        if m.get("unitId") == int(uid):
            return [(t["col"], t["row"]) for t in (m.get("tiles") or [])
                    if t.get("col") is not None]
    return []


def _walk_to(sid, rid, uid, dest, rounds=10):
    """Amene `uid` sur `dest` en enchainant les tours (`endturn` ne fait PAS jouer l'IA, runner.md
    sec.4). Un simple `move` ne suffit pas : la portee de deplacement d'un tour est bornee, et les
    spawns sont a l'autre bout du plateau -- c'est exactement le piege « bloque par la geometrie de
    spawn » que la doctrine interdit d'invoquer. Rend la position ATTEINTE."""
    for _ in range(rounds):
        tiles = _movable(sid, rid, uid)
        if not tiles:
            _act(sid, rid, {"kind": "endturn"}, 60)
            continue
        if tuple(dest) in tiles:
            _act(sid, rid, {"kind": "move", "unitId": int(uid),
                            "to": {"col": dest[0], "row": dest[1]}}, 90)
            return tuple(dest)
        best = min(tiles, key=lambda t: (hexgeo.distance(t, dest), t))
        _act(sid, rid, {"kind": "move", "unitId": int(uid),
                        "to": {"col": best[0], "row": best[1]}}, 90)
        _act(sid, rid, {"kind": "endturn"}, 60)
    return None


def _place(sid, rid, caster_vis, center, n_adj_foes):
    """Montage EXPLICITE (runner.md sec.4 : on DRIVE les positions des DEUX camps) :
        caster -> `center` ; cible -> un voisin de `center` ; `n_adj_foes` autres ennemis ->
        des voisins du centre EGALEMENT adjacents a la cible.
    C'est ce dernier point qui arme le volet secondaire de 1098
    (`Enemies(caster, AdjacentUnits(Target))`) ET celui de 1048
    (`SurroundingEnemies(caster, range) - Target`) ; sans lui les deux sets sont vides et le
    montage ne mesure que le batch principal.
    Rend (decisionView, casterId, targetId, distance caster-cible, nb d'ennemis adjacents a la
    cible, nb d'ennemis a portee <= 2 du caster hors cible)."""
    board = _board(sid, rid)
    dv = _dv(sid, rid)
    cu = _by_vis(dv, caster_vis)
    if cu is None:
        raise RuntimeError("porteur %s absent du plateau" % caster_vis)
    cid = int(cu["id"])
    _walk_to(sid, rid, cid, center)
    dv = _dv(sid, rid)
    cu = _by_vis(dv, caster_vis)
    here = _pos(cu)
    foes = sorted((u for u in (dv.get("units") or [])
                   if u.get("alive") and u.get("owner") != cu.get("owner")),
                  key=lambda u: int(u["id"]))
    if not foes:
        raise RuntimeError("aucun ennemi sur le plateau")
    ring = _neighbours(board, here)
    if not ring:
        raise RuntimeError("centre %s sans voisin" % (here,))
    tgt = int(foes[0]["id"])
    tpos = ring[0]
    _walk_to(sid, rid, tgt, tpos)
    # voisins du CENTRE qui sont AUSSI voisins de la cible -> ennemis simultanement a portee du
    # caster et adjacents a la cible (les deux sets natifs sont armes d'un coup).
    both = [t for t in ring if t != tpos and hexgeo.distance(t, tpos) == 1]
    for i, f in enumerate(foes[1:1 + n_adj_foes]):
        if i >= len(both):
            break
        _walk_to(sid, rid, int(f["id"]), both[i])
    dv = _dv(sid, rid)
    cu = _by_vis(dv, caster_vis)
    tu = next((u for u in (dv.get("units") or []) if int(u["id"]) == tgt), None)
    cpos, tp = _pos(cu), _pos(tu)
    others = [u for u in (dv.get("units") or [])
              if u.get("alive") and u.get("owner") != cu.get("owner") and int(u["id"]) != tgt]
    n_adj_t = sum(1 for u in others if hexgeo.distance(_pos(u), tp) == 1)
    n_near_c = sum(1 for u in others if hexgeo.distance(_pos(u), cpos) <= 2)
    return dv, cid, tgt, hexgeo.distance(cpos, tp), n_adj_t, n_near_c


# --------------------------------------------------------------------------- oracle / port

def _native(sid, rid, cid, tid, ability):
    r = _r(sid, "aiPlaybookPredict", {"runnerId": rid, "unitId": int(cid),
                                      "targetId": int(tid), "abilityType": int(ability)}, 120)
    evs = (r or {}).get("events") or []
    main = next((e for e in evs if e.get("targetId") == int(tid)), evs[0] if evs else None)
    if main is None:
        return None, 0
    return (main.get("healthDmgMin"), main.get("healthDmgMax"), main.get("appliedHits")), len(evs)


def _ctx(sid, rid, cid):
    from engine import weights as W
    from engine.playbook import scene as _scene
    from engine.ai import context as AICTX
    rpc = lambda m, b, t=60: _r(sid, m, b, t)                       # noqa: E731
    dv = _dv(sid, rid)
    mov = _r(sid, "aiMovableTiles", {"runnerId": rid}, 60)
    mov_by_unit = {u.get("unitId"): u for u in ((mov or {}).get("units") or [])}
    return AICTX.build(rpc, rid, dv, mov_by_unit, int(cid), W.load(),
                       _scene.build_predictor(rpc, rid))


def _offline(scene, cid, tid, ability, ability_name, here, with_override: bool):
    """Prediction OFFLINE. `with_override = False` = contrefactuel « avant #352 » : l'entree du
    registre `_MAKE_DMG_INPUT_OVERRIDES` est RETIREE, donc la base retombe sur le chemin generique
    (moyenne min/max) et les coups sur `GetDefaultAttackHits`."""
    from engine.entities.active_ability_type import ActiveAbilityType
    from engine.playbook.prediction import abilities as PA
    # La cle est REINSEREE en MEMBRE (#270-r1 volet 2) : un `pop` + reinsertion REMPLACE la cle
    # (une affectation sur cle existante, elle, la conserve), donc un `int(...)` laisserait le
    # registre avec une cle non typee apres restauration.
    cle = ActiveAbilityType(int(ability))
    saved = PA._MAKE_DMG_INPUT_OVERRIDES.pop(cle, None) if not with_override else None
    try:
        evs = PA.make_damage_predictions(scene, int(cid), int(tid), int(ability), ability_name,
                                         attack_pos=here)
    finally:
        if saved is not None:
            PA._MAKE_DMG_INPUT_OVERRIDES[cle] = saved
    main = next((e for e in evs if e.target == int(tid)), evs[0] if evs else None)
    if main is None:
        return None, 0
    return ((main.prediction.accurate_health_damage.min,
             main.prediction.accurate_health_damage.max,
             main.prediction.applied_hits), len(evs))


def _config_view(scene, cid, ability, ability_name):
    """(minDmg, maxDmg, nrOfHits, level, mult) EFFECTIFS -- re-derives du live, jamais supposes."""
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
            cfg.get_variable_for_level("maxDmg", lvl, 0, mult),
            int((cfg.constants or {}).get("nrOfHits") or 0), lvl, mult,
            ab.get_special_hits(False))


# --------------------------------------------------------------------------- un montage

def _measure(sid, ability: int, ability_name: str, carrier: str, injected: bool,
             center, n_adj_foes: int, seed: int, board: str, level: int, mult: int,
             expected_events: int, target_hp=None) -> dict:
    rid = sf = None
    try:
        if injected:
            rid, sf = _build_injected(sid, carrier, seed, board, level, mult)
        else:
            rid, sf = _build_pool(carrier, seed, board, target_hp)
        carrier_vis = _spawn_visual(carrier)
        dv, cid, tid, dist, n_adj_t, n_near_c = _place(sid, rid, carrier_vis, center, n_adj_foes)
        scene = _ctx(sid, rid, cid).scene
        cv = _config_view(scene, cid, ability, ability_name)
        cu = next((u for u in (dv.get("units") or []) if int(u["id"]) == cid), None)
        cp = _pos(cu)
        nat, n_nat = _native(sid, rid, cid, tid, ability)
        after, n_after = _offline(scene, cid, tid, ability, ability_name, cp, True)
        before, n_before = _offline(scene, cid, tid, ability, ability_name, cp, False)
    finally:
        if rid is not None:
            _r(sid, "disposeRunner", {"runnerId": rid}, 30)
        if sf is not None:
            Path(sf).unlink(missing_ok=True)
    out = {"ability": ability, "name": ability_name, "carrier": carrier, "runner": rid,
           "dist": dist, "adj_foes_of_target": n_adj_t, "foes_within2_of_caster": n_near_c,
           "config": cv, "native": nat, "after": after, "before": before,
           "n_events": {"native": n_nat, "after": n_after, "before": n_before}}
    out["expected_events"] = int(expected_events)
    out["after_ok"] = (after == nat and nat is not None)
    out["discriminates"] = (before != after)
    # La geometrie doit etre REELLEMENT armee, sinon « 1 event » ne prouve rien : on exige les 2
    # ennemis colles a la cible ET a portee du caster avant de lire le compte d'events.
    out["geometry_ok"] = (n_adj_t >= 2 and n_near_c >= 2 and dist == 1)
    out["events_ok"] = (n_nat == int(expected_events))
    out["ok"] = bool(out["after_ok"] and out["discriminates"]
                     and out["geometry_ok"] and out["events_ok"])
    return out


# `expected_events` = nombre d'events que le NATIF doit rendre sur cette geometrie (2 ennemis colles
# a la cible ET a portee 2 du caster). C'est l'axe qui tranche « volet secondaire MORT » contre
# « montage rate », et il est ASSERTE, pas seulement affiche :
#   1051 -> 3 : son set `...StikkbombAbility$$GetAdjacentDamageTargets` = `AdjacentUnits(Target,
#               unique, sel)` ne depend QUE de `Target`, renseigne dans l'`AbilityEntities` du
#               playbook -> 1 + 2 events (quirk #57e : les 2 portent sur la CIBLE).
#   1098 -> 1 : son set `...PlasmaGrenadeAbility$$GetOtherTargets` = `Enemies(caster@0x30,
#               AdjacentUnits(Target@0x60, 1, 3), 1)` depend du CASTER -- or le playbook construit
#               `AbilityEntities..ctor(entities, caster: 0, actor: 0, target: target, ...)`, caster
#               NUL -> set vide -> volet secondaire STRUCTURELLEMENT mort.
#   1048 -> 1 : son `AbilityEntities` est un memset(0) COMPLET (`FUN_1802abdd0(&local_248, 0, 0x128)`)
#               et son set `...FragstormGrenadeLauncherAbility$$GetOtherTargets` =
#               `Damageable(SurroundingEnemies(caster@0x30, ConfigConst(0x16), 1, 3) - Target@0x60)`
#               depend du caster ET de la cible -> vide lui aussi. Le gate `result.WillBeKill` est
#               par ailleurs FRANCHI sur ce montage (le natif rend min == max == PV de la cible).
MONTAGES = [
    # (ability, nom, porteur, injecte ?, centre, nb ennemis colles, level, mult, events, PV cible)
    (1048, "FragstormGrenadeLauncher", "templAggressor", False, (3, 4), 2, 0, 100, 1, None),
    # Le MEME 1048 sur une cible qui SURVIT : sans ce bras les deux bornes sont clampees aux PV
    # (`min == max`) et l'on ne verifie qu'un plancher. Avec, le spread +/-20% et l'armure
    # traversent -- c'est la que `1 coup de nrOfHits x maxDmg` et `nrOfHits coups d'une moyenne`
    # divergent le plus (l'armure est deduite UNE fois au lieu de SIX).
    (1048, "FragstormGrenadeLauncher", "templAggressor", False, (3, 4), 2, 0, 100, 1, 400000),
    (1098, "PlasmaGrenade", "eldarSmnGuardian", True, (3, 4), 2, 50, 100, 1, None),
    # TEMOIN + NON-REGRESSION : meme mold de batch principal (base `Get(minDmg)` + `nrOfHits`
    # LITTERAL, deja porte par `_stikkbomb_inputs`), mais volet secondaire VIVANT.
    (1051, "Stikkbomb", "orksOrkBoys", True, (3, 4), 2, 50, 100, 3, None),
]


def run(only=None, seed: int = SEED, board: str = BOARD, verbose: bool = True,
        center_override=None) -> dict:
    sid = _resolve_session()
    rows = []
    for ability, name, carrier, injected, center, n_adj, level, mult, exp_ev, thp in MONTAGES:
        if only and int(ability) != int(only):
            continue
        if center_override is not None:
            center = tuple(center_override)
        if verbose:
            print("\n=== %d %s -- porteur %s (%s) sur %s%s ==="
                  % (ability, name, carrier, "catalogue injecte" if injected else "pool", board,
                     "" if not thp else " -- cible a %d PV (survit)" % thp))
        try:
            row = _measure(sid, ability, name, carrier, injected, center, n_adj, seed, board,
                           level, mult, exp_ev, thp)
        except Exception as exc:                                    # noqa: BLE001
            row = {"ability": ability, "name": name, "carrier": carrier,
                   "error": "%s: %s" % (type(exc).__name__, exc), "ok": False}
        rows.append(row)
        if verbose:
            _print_row(row)
    ok = bool(rows) and all(r.get("ok") for r in rows)
    if verbose:
        print("\n=== VERDICT #352 === %s" % ("OK" if ok else "ECHEC"))
    return {"ok": ok, "rows": rows}


def _print_row(row):
    if row.get("error"):
        print("  ERREUR : %s" % row["error"])
        return
    cv = row.get("config") or ()
    if cv:
        print("  config live : minDmg=%s maxDmg=%s nrOfHits=%s (level=%s mult=%s) "
              "GetDefaultAttackHits=%s" % (cv[0], cv[1], cv[2], cv[3], cv[4], cv[5]))
    print("  distance caster-cible = %s | ennemis adjacents a la cible = %s | "
          "ennemis a d<=2 du caster (hors cible) = %s"
          % (row.get("dist"), row.get("adj_foes_of_target"), row.get("foes_within2_of_caster")))
    print("  geometrie armee : %s" % row.get("geometry_ok"))
    print("  natif  = %-30s (events=%d, attendus=%d -> %s)"
          % (str(row["native"]), row["n_events"]["native"], row["expected_events"],
             "OK" if row.get("events_ok") else "ECART"))
    print("  apres  = %-30s (events=%d) %s"
          % (str(row["after"]), row["n_events"]["after"],
             "== NATIF" if row["after_ok"] else "!= NATIF"))
    print("  avant  = %-30s (events=%d) %s"
          % (str(row["before"]), row["n_events"]["before"],
             "== NATIF (bras NON discriminant)" if row["before"] == row["native"] else "!= NATIF"))
    print("  -> %s" % ("OK" if row.get("ok") else "ECHEC"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", type=int, default=None, help="ne jouer qu'une ability (1048|1098)")
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--board", default=BOARD, help="board CHOISI (runner.md sec.2), jamais subi")
    ap.add_argument("--center", default=None,
                    help="tuile 'col,row' ou planter le caster (defaut : celle du montage)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    ctr = tuple(int(x) for x in a.center.split(",")) if a.center else None
    out = run(only=a.only, seed=a.seed, board=a.board, center_override=ctr)
    if a.json:
        print(json.dumps(out, indent=1, default=str))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
