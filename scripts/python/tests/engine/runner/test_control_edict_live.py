"""AdMech S4b : ControlEdict (passif de Tan Gi'da / admecMarshall) confronte au LIVE.

ControlEdict = **passiveAbility** de admecMarshall -> ability-trigger after-normal-attack (registre
`ABILITY_TRIGGERS`, comme TheBetrayer/DecoysAndMisdirection/Hypersensory). GATE sur l'etat Imperative de S4a
(`state.effects.has_effect(caster, PROTECTOR=1247 / CONQUEROR=1248)`) :

  - **Protector actif** : apres que Tan attaque (normale) -> summon 1 Skitarii Vanguard (admecSmnVanguard) sur
    un hex LIBRE ADJACENT A TAN. Cap = `maxSummons[level]` (3/4/5) Vanguards a la fois.
  - **Conqueror actif** : apres que Tan attaque -> tous les Summons Mechanical amis ADJACENTS A TAN attaquent
    AUSSI sa cible si elle est a portee (attaque normale du summon).

KIT (gameconfig) : ability ControlEdict constants{unitId: admecSmnVanguard} ; variables per-niveau maxSummons
(3/4/5) + summonHp(->2546)/summonDmg(->509)/summonArmor(->1091) rarity-scaled. admecSmnVanguard = Summon +
Mechanical, melee Physical + ranged Toxic r2 (3 hits), passif RadSaturation (hors scope S4b, task #25).

Verdict RE : IdunBattleLogic.Entities.Abilities.Triggered.Loki.ControlEdictAbility$$CreateTrigger On(0x26) ; IdunBattleLogic.Entities.Abilities.Triggered.Loki.ControlEdictAbility$$CreateBehaviour = op_add(If(HasEffect Protector,
IdunBattleLogic.Entities.Abilities.Triggered.Loki.ControlEdictAbility$$SummonMinion), If(HasEffect Conqueror, IdunBattleLogic.Entities.Abilities.Triggered.Loki.ControlEdictAbility$$AttackWithMinions)). Port =
loki/control_edict.py (ControlEdictAbility) + SpawnUnitOperation.execute_control_edict_summon.

CE FICHIER :
  1. `test_control_edict_summon_live` : ORACLE LIVE -- DRIVE Tan a portee d'un ennemi (aiMovableTiles+move),
     attaque NORMALE sous Protector -> un Skitarii Vanguard apparait ADJACENT a Tan, sur sa team ; hp LIVE ==
     `build_summon_context("ControlEdict")` (confronte la lecture kit gameconfig au natif).
  2. `test_control_edict_protector_summon_offline_agreement` : OFFLINE face Protector (Vanguard adjacent Tan).
  3. `test_control_edict_cap_offline` : cap maxSummons[level] -> au-dela, plus de spawn.
  4. `test_control_edict_conqueror_summons_attack_offline_agreement` : OFFLINE face Conqueror (Summon
     Mechanical adjacent a Tan attaque la cible a portee ; hors-portee -> rien).

DRIVE POSITIONS/STATE (doctrine) : positions controlees (live via move ; offline via edit). ASCII only.
"""
from __future__ import annotations

import json
import os
from collections import deque

import pytest

TAN_VIS = "admecMarshall"          # Tan Gi'da (passif ControlEdict + actif DoctrinaImperatives)
SUMMON_VIS = "admecSmnVanguard"    # Skitarii Vanguard : CLE de config (kit) = unitId des constants ControlEdict.
SUMMON_LIVE_VIS = "admecNpc1Vanguard"   # ... mais son champ `visualId` (== ce que decisionView/observeBattle
                                        # exposent LIVE) differe de la cle. Cote LIVE on matche donc CE visualId ;
                                        # cote OFFLINE le port spawn avec la cle `admecSmnVanguard` (qui porte le kit
                                        # gameconfig -- GC.unit('admecNpc1Vanguard') est un stub sans kit).
SUMMON_ABILITY = "ControlEdict"
PROTECTOR = 1247                   # ProtectorImperative
CONQUEROR = 1248                   # ConquerorImperative
ENEMY_VIS = "necroWarden"
BUILD = ["--roster", "1", "--p-units", f"{TAN_VIS},admecRuststalker",
         "--a-units", f"{ENEMY_VIS},{ENEMY_VIS}"]

_DUMP = os.path.join(os.environ.get("TEMP", "/tmp"), "control_edict_groundtruth.json")


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _effect_ids(u):
    return {e.get("effectType") for e in (u.get("effects") or [])}


def _find(dec, vis, alive=True):
    return next((u for u in (dec.get("units") or [])
                 if u.get("visualId") == vis and (u.get("alive") or not alive)), None)


def _find_all(dec, vis):
    return [u for u in (dec.get("units") or []) if u.get("visualId") == vis and u.get("alive")]


def _advance_to_my_turn(rpc, rid, vis, max_iter=20):
    for _ in range(max_iter):
        dec = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        if not _ok(dec):
            return None, None
        u = _find(dec, vis)
        if u is None:
            return dec, None
        if dec.get("currentPlayer") == u.get("owner"):
            return dec, u
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}, "captureEvents": False}, 60)
    return None, None


def _tile_of(board, u):
    p = u.get("pos") or {}
    return board.id_at(p.get("col"), p.get("row")) if p.get("col") is not None else None


def _bfs_dist(board, start):
    """Distance BFS (board.neighbours) de `start` a toutes les tuiles atteignables."""
    seen = {start: 0}
    q = deque([start])
    while q:
        x = q.popleft()
        for n in board.neighbours(x):
            if n not in seen:
                seen[n] = seen[x] + 1
                q.append(n)
    return seen


def _tan_normal_ability_id(tan):
    """id de l'attaque NORMALE de Tan (abilities kind=='normal') -> On(0x26) qui declenche ControlEdict."""
    for ab in (tan.get("abilities") or []):
        if ab.get("kind") == "normal":
            return ab.get("id")
    return None


def _normal_attack_eval(dec, tan_id, norm_id, want_target=None):
    """(targetId, abilityId) d'un plan d'attaque NORMALE de Tan (dec.attackPlans[tan].evals), ou (None, None).
    Filtre sur l'ability NORMALE (norm_id) -> On(0x26) pas une special (On(9)) ; et sur `want_target` si fourni."""
    for p in (dec.get("attackPlans") or []):
        if p.get("unitId") != tan_id:
            continue
        for ev in (p.get("evals") or []):
            if ev.get("targetId") is None:
                continue
            if want_target is not None and ev.get("targetId") != want_target:
                continue
            if norm_id is not None and ev.get("abilityId") != norm_id:
                continue
            return ev.get("targetId"), ev.get("abilityId")
    return None, None


def _attack(rpc, rid, tan_id, tgt, ability):
    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": tan_id, "targetId": tgt, "abilityType": ability},
        "captureEvents": True}, 120)
    dec_after = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    return tgt, res, dec_after


def _tan_attack_range():
    """Portee d'attaque normale de Tan = max(Range des armes) ; melee (Range absent) -> 1."""
    import gameconfig as GC
    ranges = [int(w.get("Range") or 0) for w in ((GC.unit(TAN_VIS) or {}).get("weapons") or [])]
    mx = max(ranges) if ranges else 0
    return mx if mx > 0 else 1


def _attack_when_in_range(rpc, rid, board, dec, tan, enemy_id, R):
    """Si Tan est REELLEMENT a portee (<=R, BFS depuis sa tuile ACTUELLE) de `enemy_id`, applique son attaque
    NORMALE (eval attackPlans, abilityId=69). Renvoie (target, res, dec_after) ou None si pas a portee/plan."""
    tan_id = tan["id"]
    a_tile = _tile_of(board, tan)
    e = _find_by_id(dec, enemy_id)
    e_tile = _tile_of(board, e) if e is not None else None
    if a_tile is None or e_tile is None:
        return None
    dgoal = _bfs_dist(board, e_tile)
    if dgoal.get(a_tile, 99) > R:                         # pas a portee depuis la tuile ACTUELLE
        return None
    norm_id = _tan_normal_ability_id(tan)
    tgt, ab = _normal_attack_eval(dec, tan_id, norm_id, want_target=enemy_id)
    if tgt is None:
        return None
    return _attack(rpc, rid, tan_id, tgt, ab)


def _find_by_id(dec, uid):
    return next((u for u in (dec.get("units") or []) if u.get("id") == uid), None)


def _drive_normal_attack_under_protector(rpc, rid, board, max_turns=16):
    """DRIVE Tan A PORTEE REELLE d'un ennemi (BFS depuis sa tuile ACTUELLE, pas les attackPlans move-inclusive)
    puis lui fait faire son attaque NORMALE (ability 69 = On(0x26)), en gardant Protector (jamais le toggle).
    Renvoie (target_id, res, dec_after) ou (None,None,None). Mirror du drive act_of_faith (approche+attaque)."""
    R = _tan_attack_range()
    for _ in range(max_turns):
        dec, tan = _advance_to_my_turn(rpc, rid, TAN_VIS)
        if tan is None:
            return None, None, None
        if PROTECTOR not in _effect_ids(tan):
            return None, None, None                       # imperative bascule -> plus la face summon
        tan_id = tan["id"]
        enemies = [u for u in (dec.get("units") or [])
                   if u.get("alive") and u.get("owner") != tan.get("owner") and (u.get("pos") or {}).get("col") is not None]
        if not enemies:
            return None, None, None
        target = enemies[0]
        enemy_id = target["id"]
        e_tile = _tile_of(board, target)
        # deja a portee ? -> attaque.
        hit = _attack_when_in_range(rpc, rid, board, dec, tan, enemy_id, R)
        if hit is not None:
            return hit
        # sinon : approcher (tuile atteignable minimisant la distance hex a la cible).
        dgoal = _bfs_dist(board, e_tile)
        mt = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
        cmt = next((x for x in (mt.get("units") or []) if x.get("unitId") == tan_id), None)
        reach = {board.id_at(t["col"], t["row"]): (t["col"], t["row"])
                 for t in ((cmt or {}).get("tiles") or []) if t.get("col") is not None}
        pool = [tid for tid in reach if tid in dgoal]
        if not pool:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
            continue
        best = min(pool, key=lambda t: dgoal[t])
        col, row = reach[best]
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": tan_id, "to": {"col": col, "row": row}}}, 40)
        # meme tour apres le move : re-tenter l'attaque si desormais a portee ; sinon endturn.
        dec2 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        tan2 = _find(dec2, TAN_VIS)
        if tan2 is not None:
            hit2 = _attack_when_in_range(rpc, rid, board, dec2, tan2, enemy_id, R)
            if hit2 is not None:
                return hit2
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
    return None, None, None


def test_control_edict_summon_live(live_session, rpc, build_runner):
    """ORACLE LIVE (RE-independant) : sous Protector (SetStart), DRIVE Tan a portee d'un ennemi et lui fait
    faire une attaque NORMALE -> un Skitarii Vanguard apparait sur SA team, ADJACENT a lui ; hp LIVE ==
    `build_summon_context("ControlEdict", level, mult)` (valide la lecture kit gameconfig). DUMPE la
    ground-truth. Skip propre si Tan ne peut atteindre un ennemi / Protector bascule."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.operations.spawn import build_summon_context
    import hexgeo

    rid = build_runner("777", extra=BUILD)["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")

    dec, tan = _advance_to_my_turn(rpc, rid, TAN_VIS)
    if tan is None:
        pytest.skip("Tan Gi'da absent / pas atteint son tour")
    my_team, my_player = tan.get("team"), tan.get("owner")
    n_before = len(_find_all(dec, SUMMON_LIVE_VIS))

    target_id, res, dec2 = _drive_normal_attack_under_protector(rpc, rid, board)
    if target_id is None or not _ok(res):
        pytest.skip("Tan n'a pas pu attaquer un ennemi sous Protector (geometrie/tour)")

    ob2 = rpc("observeBattle", {"runnerId": rid}, 60)
    snap2 = rpc("combatSnapshot", {"runnerId": rid}, 90)
    vanguards = _find_all(dec2, SUMMON_LIVE_VIS)
    tan2 = _find(dec2, TAN_VIS)
    tan_pos2 = (tan2 or {}).get("pos")

    def _cfg(vis):
        for u in (snap2.get("units") or []):
            if (u.get("unitConfig") or {}).get("visualId") == vis:
                return u.get("unitConfig") or {}
        return {}
    tcfg = _cfg(TAN_VIS)
    lvl = tcfg.get("activeAbilityLevel")
    mult = int(tcfg.get("abilityVariablesMultiplier") or 100)
    off_ctx = build_summon_context(0, SUMMON_VIS, SUMMON_ABILITY, lvl, mult) if lvl is not None else None

    vg_hp = None
    for u in (ob2.get("units") or []):
        if u.get("visualId") == SUMMON_LIVE_VIS and not u.get("isDead"):
            vg_hp = u.get("hp")
    gt = {"note": "ControlEdict ground-truth (S4b port target)", "team": my_team, "player": my_player,
          "target_id": target_id, "n_vanguards_before": n_before, "n_vanguards_after": len(vanguards),
          "tan_pos_after": tan_pos2, "vanguards": vanguards, "caster_level": lvl, "mult": mult,
          "live_vanguard_hp": vg_hp,
          "offline_summon_hp": (off_ctx.health if off_ctx is not None else None)}
    with open(_DUMP, "w", encoding="utf-8") as f:
        json.dump(gt, f, ensure_ascii=True, indent=1, default=str)
    print(f"[ControlEdict LIVE] vanguards {n_before}->{len(vanguards)} ; live_hp={vg_hp} "
          f"offline_hp={(off_ctx.health if off_ctx else None)} (lvl={lvl} mult={mult}) -> {_DUMP}")

    # --- un NOUVEAU Vanguard est apparu sur la team de Tan ---
    assert len(vanguards) == n_before + 1, \
        f"ControlEdict Protector : attendu +1 Vanguard (={n_before + 1}), obtenu {len(vanguards)}"
    vg = vanguards[-1]
    assert vg.get("team") == my_team, f"Vanguard team {vg.get('team')} != team de Tan {my_team}"
    # placement : ADJACENT a Tan (i2 'free adjacent hex').
    vg_pos = vg.get("pos")
    if tan_pos2 and vg_pos:
        d = hexgeo.distance((tan_pos2["col"], tan_pos2["row"]), (vg_pos["col"], vg_pos["row"]))
        assert d == 1, f"Vanguard non adjacent a Tan (dist={d})"
    # stats : hp LIVE == build_summon_context (valide la lecture kit gameconfig).
    if off_ctx is not None and vg_hp is not None:
        assert off_ctx.health == vg_hp, \
            f"offline summon hp {off_ctx.health} != live {vg_hp} (kit ControlEdict summonHp KO)"


def test_control_edict_protector_summon_offline_agreement(live_session, rpc, build_runner):
    """OFFLINE-AGREEMENT (port S4b, face Protector) : sous Protector, driver l'attaque de Tan offline
    (`after_hit_normal_attack`) pose 1 Skitarii Vanguard sur un hex LIBRE ADJACENT A TAN, owner = team+player
    de Tan, stats == `build_summon_context("ControlEdict", level, mult)`."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.components import StatsComponent, OwnerComponent, PositionComponent, UnitComponent
    from engine.runner.operations.spawn import build_summon_context
    from engine.runner.operations.triggers.dispatch.attack import after_hit_normal_attack
    import hexgeo

    rid = build_runner("777", extra=BUILD)["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")

    dec, tan = _advance_to_my_turn(rpc, rid, TAN_VIS)
    if tan is None:
        pytest.skip("Tan Gi'da absent / pas atteint son tour")
    tan_id = tan["id"]
    if PROTECTOR not in _effect_ids(tan):
        pytest.skip("Protector(1247) non actif pre-attaque (SetStart)")
    enemy = _find(dec, ENEMY_VIS)
    enemy_id = (enemy or {}).get("id")
    if enemy_id is None:
        pytest.skip("cible ennemie absente")

    dec0 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    ob0 = rpc("observeBattle", {"runnerId": rid}, 60)
    snap0 = rpc("combatSnapshot", {"runnerId": rid}, 90)
    s0 = rpc("dumpRng", {"runnerId": rid}, 30)
    state = load_state(dec0, ob0, snap0, board=board)
    if _ok(s0):
        rng = IntBasedMersenneTwister(); rng.mt = list(s0["mt"]); rng.mti = s0["mti"]; state.rng = rng

    tan_ent = state.get_entity(tan_id)
    if tan_ent is None or tan_ent.get_component(StatsComponent) is None or state.effects is None:
        pytest.skip("Tan sans StatsComponent/effects offline (snapshot incomplet)")
    if not state.effects.has_effect(tan_id, effect_type=PROTECTOR):
        pytest.skip("Protector non reconstruit offline (snapshot n'expose pas 1247)")

    tctx = tan_ent.get_component(StatsComponent).ctx
    lvl = getattr(tctx, "active_ability_level", None)
    mult = int(getattr(tctx, "ability_variables_multiplier", 100) or 100)
    exp_ctx = build_summon_context(0, SUMMON_VIS, SUMMON_ABILITY, lvl, mult)

    before_ids = set(state.entities.keys())
    after_hit_normal_attack(state, tan_id, enemy_id, ranged=False, profile=None)

    new_ids = [i for i in state.entities.keys() if i not in before_ids]
    vgs = [i for i in new_ids
           if (uc := state.get_entity(i).get_component(UnitComponent)) is not None
           and uc.visual_id == SUMMON_VIS]
    assert len(vgs) == 1, f"attendu 1 Vanguard spawne, obtenu {len(vgs)} (new={new_ids})"
    ve = state.get_entity(vgs[0])
    voc = ve.get_component(OwnerComponent); vpc = ve.get_component(PositionComponent)
    vsc = ve.get_component(StatsComponent)
    toc = tan_ent.get_component(OwnerComponent); tpc = tan_ent.get_component(PositionComponent)
    assert voc.team == toc.team and voc.player == toc.player, \
        f"Vanguard owner ({voc.team},{voc.player}) != Tan ({toc.team},{toc.player})"
    assert vpc is not None and tpc is not None, "Vanguard/Tan sans position offline"
    assert hexgeo.distance((tpc.col, tpc.row), (vpc.col, vpc.row)) == 1, "Vanguard offline non adjacent a Tan"
    assert vsc.ctx.health == exp_ctx.health, \
        f"Vanguard offline hp {vsc.ctx.health} != build_summon_context {exp_ctx.health}"
    print(f"[ControlEdict Protector offline] Vanguard adjacent a Tan hp={vsc.ctx.health} owner OK")


def test_control_edict_cap_offline(live_session, rpc, build_runner):
    """OFFLINE (port S4b, cap Protector) : au-dela de `maxSummons[level]` (3/4/5) Vanguards amis, une attaque
    de Tan ne summon PLUS (i2 'no more than N at the same time'). Le cap se lit via `ability_var("ControlEdict",
    "maxSummons", level)`. On pre-remplit `cap` Vanguards sur des tuiles libres NON adjacentes a Tan (le cap
    compte team-wide, pas l'adjacence) en LAISSANT >=1 tuile libre adjacente a Tan -> c'est le CAP (pas la
    geometrie) qui bloque le spawn."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    from engine.runner.components import StatsComponent, UnitComponent, OwnerComponent
    from engine.entities.effects.magnitude import ability_var
    from engine.runner.operations.spawn import (_spawn_config_grot, _free_tiles_adjacent, _occupied_tiles)
    from engine.runner.operations.triggers.dispatch.attack import after_hit_normal_attack

    rid = build_runner("777", extra=BUILD)["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")
    dec, tan = _advance_to_my_turn(rpc, rid, TAN_VIS)
    if tan is None:
        pytest.skip("Tan Gi'da absent / pas atteint son tour")
    tan_id = tan["id"]
    if PROTECTOR not in _effect_ids(tan):
        pytest.skip("Protector non actif pre-attaque")
    enemy = _find(dec, ENEMY_VIS)
    enemy_id = (enemy or {}).get("id")
    if enemy_id is None:
        pytest.skip("cible ennemie absente")

    dec0 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    ob0 = rpc("observeBattle", {"runnerId": rid}, 60)
    snap0 = rpc("combatSnapshot", {"runnerId": rid}, 90)
    state = load_state(dec0, ob0, snap0, board=board)
    tan_ent = state.get_entity(tan_id)
    if tan_ent is None or tan_ent.get_component(StatsComponent) is None or state.effects is None:
        pytest.skip("Tan sans StatsComponent/effects offline")
    if not state.effects.has_effect(tan_id, effect_type=PROTECTOR):
        pytest.skip("Protector non reconstruit offline")

    toc_ctx = tan_ent.get_component(StatsComponent).ctx
    lvl = getattr(toc_ctx, "active_ability_level", None)
    mult = int(getattr(toc_ctx, "ability_variables_multiplier", 100) or 100)
    cap = int(ability_var(SUMMON_ABILITY, "maxSummons", lvl) or 5)
    assert cap > 0, f"maxSummons non resoluble (level={lvl})"
    tan_oc = tan_ent.get_component(OwnerComponent)

    # tuiles libres NON adjacentes a Tan (reserve les voisins de Tan pour qu'un spawn SOIT possible) ; place cap.
    tan_neigh = set(_free_tiles_adjacent(state, tan_id, set()))
    if not tan_neigh:
        pytest.skip("aucune tuile libre adjacente a Tan (geometrie) -> spawn impossible meme sans cap")
    occ = _occupied_tiles(state)
    free_far = [t for t in board.by_id.keys()
                if board.walkable(t) and t not in occ and t not in tan_neigh]
    if len(free_far) < cap:
        pytest.skip(f"pas assez de tuiles libres non-adjacentes pour saturer le cap ({len(free_far)}/{cap})")
    for t in free_far[:cap]:
        _spawn_config_grot(state, SUMMON_VIS, t, SUMMON_ABILITY, lvl, mult, tan_oc.team, tan_oc.player)

    def _count():
        return sum(1 for e in state.entities.values()
                   if (u := e.get_component(UnitComponent)) is not None and u.alive and u.visual_id == SUMMON_VIS
                   and (o := e.get_component(OwnerComponent)) is not None and o.team == tan_oc.team)
    n_before = _count()
    assert n_before == cap, f"pre-remplissage KO : {n_before} Vanguards places != cap {cap}"
    after_hit_normal_attack(state, tan_id, enemy_id, ranged=False, profile=None)
    n_after = _count()
    print(f"[ControlEdict cap offline] cap={cap} (level={lvl}) vanguards {n_before}->{n_after} (attendu inchange)")
    assert n_after == n_before, f"cap KO : {n_before}->{n_after} apres attaque au cap sature (max={cap})"


def test_control_edict_conqueror_summons_attack_offline_agreement(live_session, rpc, build_runner):
    """OFFLINE-AGREEMENT (port S4b, face Conqueror) : apres toggle vers Conqueror, un Summon Mechanical
    ADJACENT a Tan attaque AUSSI la cible de Tan si A PORTEE. DRIVE : place la cible sur un voisin libre de
    Tan + un Vanguard (Summon+Mechanical) sur un AUTRE voisin libre (a portee 2 de la cible), drive l'attaque
    de Tan (`after_hit_normal_attack`) -> la cible perd des PV. Contre-epreuve : sans Summon adjacent, rien."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.components import StatsComponent, HealthComponent, PositionComponent, OwnerComponent
    from engine.runner.abilities.loki import DoctrinaImperativesAbility
    from engine.runner.operations.spawn import _spawn_config_grot, _occupied_tiles
    from engine.runner.operations.triggers.dispatch.attack import after_hit_normal_attack
    import hexgeo

    rid = build_runner("777", extra=BUILD)["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")
    dec, tan = _advance_to_my_turn(rpc, rid, TAN_VIS)
    if tan is None:
        pytest.skip("Tan Gi'da absent / pas atteint son tour")
    tan_id = tan["id"]
    if PROTECTOR not in _effect_ids(tan):
        pytest.skip("Protector non actif pre-attaque -> toggle non amorcable")
    enemy = _find(dec, ENEMY_VIS)
    enemy_id = (enemy or {}).get("id")
    if enemy_id is None:
        pytest.skip("cible ennemie absente")

    dec0 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    ob0 = rpc("observeBattle", {"runnerId": rid}, 60)
    snap0 = rpc("combatSnapshot", {"runnerId": rid}, 90)
    s0 = rpc("dumpRng", {"runnerId": rid}, 30)
    state = load_state(dec0, ob0, snap0, board=board)
    if _ok(s0):
        rng = IntBasedMersenneTwister(); rng.mt = list(s0["mt"]); rng.mti = s0["mti"]; state.rng = rng
    tan_ent = state.get_entity(tan_id)
    en_ent = state.get_entity(enemy_id)
    if tan_ent is None or en_ent is None or tan_ent.get_component(StatsComponent) is None \
            or en_ent.get_component(HealthComponent) is None or state.effects is None:
        pytest.skip("entites/composants offline incomplets")
    if not state.effects.has_effect(tan_id, effect_type=PROTECTOR):
        pytest.skip("Protector non reconstruit offline -> toggle non amorcable")

    tpc = tan_ent.get_component(PositionComponent)
    epc = en_ent.get_component(PositionComponent)
    toc = tan_ent.get_component(OwnerComponent)
    if tpc is None or epc is None or toc is None:
        pytest.skip("positions/owner offline manquants")

    # 2 voisins LIBRES distincts de Tan : cible sur l'un, Vanguard sur l'autre.
    ttile = board.id_at(tpc.col, tpc.row)
    occ = _occupied_tiles(state)
    occ.discard(board.id_at(epc.col, epc.row))            # la cible va etre deplacee -> sa tuile devient libre
    free_neigh = [t for t in sorted(board.neighbours(ttile)) if board.walkable(t) and t not in occ]
    if len(free_neigh) < 2:
        pytest.skip(f"pas assez de voisins libres de Tan ({len(free_neigh)}/2)")
    en_tile, vg_tile = free_neigh[0], free_neigh[1]
    ec, er = board.coord(en_tile); epc.col, epc.row = ec, er   # DRIVE la cible sur un voisin de Tan

    # toggle offline vers Conqueror (Protector present -> Conqueror).
    DoctrinaImperativesAbility().execute_behaviour(state, tan_id, tan_id)
    assert state.effects.has_effect(tan_id, effect_type=CONQUEROR), "toggle KO : Conqueror absent offline"

    tctx = tan_ent.get_component(StatsComponent).ctx
    lvl = getattr(tctx, "active_ability_level", None)
    mult = int(getattr(tctx, "ability_variables_multiplier", 100) or 100)
    vgid = _spawn_config_grot(state, SUMMON_VIS, vg_tile, SUMMON_ABILITY, lvl, mult, toc.team, toc.player)
    if vgid is None:
        pytest.skip("spawn du Vanguard stand-in KO")
    vg_ent = state.get_entity(vgid)
    vpc = vg_ent.get_component(PositionComponent)
    assert hexgeo.distance((tpc.col, tpc.row), (vpc.col, vpc.row)) == 1, "Vanguard non adjacent a Tan (drive KO)"
    assert hexgeo.distance((vpc.col, vpc.row), (epc.col, epc.row)) <= 2, "cible hors portee Toxic du Vanguard"

    hp_before = en_ent.get_component(HealthComponent).hp
    res = after_hit_normal_attack(state, tan_id, enemy_id, ranged=False, profile=None)
    hp_after = en_ent.get_component(HealthComponent).hp
    print(f"[ControlEdict Conqueror offline] cible hp {hp_before}->{hp_after} "
          f"(Vanguard Mechanical adjacent a Tan attaque la cible a portee)")
    assert hp_after < hp_before, \
        "face Conqueror : le Summon Mechanical adjacent a Tan n'a PAS attaque la cible a portee"

    # contre-epreuve : le meme etat SANS Vanguard adjacent -> aucune attaque (cible intacte).
    state2 = load_state(dec0, ob0, snap0, board=board)
    if _ok(s0):
        rng2 = IntBasedMersenneTwister(); rng2.mt = list(s0["mt"]); rng2.mti = s0["mti"]; state2.rng = rng2
    if state2.effects is not None:
        DoctrinaImperativesAbility().execute_behaviour(state2, tan_id, tan_id)  # Conqueror, mais AUCUN summon
    en2 = state2.get_entity(enemy_id)
    hp2_before = en2.get_component(HealthComponent).hp
    after_hit_normal_attack(state2, tan_id, enemy_id, ranged=False, profile=None)
    hp2_after = en2.get_component(HealthComponent).hp
    assert hp2_after == hp2_before, \
        f"Conqueror sans Summon adjacent : la cible perd des PV a tort ({hp2_before}->{hp2_after})"
