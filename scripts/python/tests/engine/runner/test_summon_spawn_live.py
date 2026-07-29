"""SPAWN de SUMMON — `SpawnUnitOperation` confronté au LIVE (étape 2 du runner autonome).

Valide le port de la chaîne summon (`IdunBattleLogic.Entities.Abilities.Active.Loki.ScarabHiveAbility$$ExecuteBehaviour` → `DSLFactory.Spawn` →
`AddUnitOperation`) : un summon d'ability spawn sur **la team ET le player du caster**, sur une tuile LIBRE
adjacente à la **cible**, avec des stats `ability_var(ScarabHive, summon*, casterLevel, mult)`.

Fixture = `necroSpyder` (caste `ScarabHive`) vs `necroDestroyer` (cible unique). On joue l'IA native
(`aiPlayByUnit`, pump) jusqu'à ce que les 2 `necroSmnSwarm` spawnent, on lit leur état LIVE (hp/attack/
team/player/pos), puis on relance `SpawnUnitOperation` OFFLINE depuis l'état d'AVANT et on confronte :
  • STATS : hp/attack/crit offline == live (résolution `ability_var` bit-exact) ;
  • OWNER : team+player offline == live == ceux du caster (CopyOwner) ;
  • PLACEMENT : les summons (offline ET live) sont hex-adjacents à la cible (`AdjacentTiles(target)`).

⚠ ADJACENCE = mode **evenq**. Placement RNG-exact (quelle tuile parmi les libres) = raffinement non testé
ici (on valide la RÈGLE : adjacent à la cible).

`test_spawn_requires_a_tile` (#254) est la GARDE du fantôme : `IdunBattle.Entities.Behaviours.
SpawnUnitBehaviour$$Execute` ITÈRE son tile-sélecteur et ne crée une entité que DEPUIS une tuile
itérée. Le port créait l'unité PUIS lui cherchait une place → cible encerclée = summon sans
`PositionComponent`, hors plateau, que rien ne ramasse (mesuré live : natif 1, port 2 dont 1 fantôme
— `probe_254_spawn_requires_tile.py`, C3_26/31337 et MC1_67/777).
"""
from __future__ import annotations

import pytest

from engine.runner.snapshot import load_state
from engine.runner.operations.spawn import SpawnUnitOperation, build_summon_context
from engine.runner.components import (StatsComponent, OwnerComponent, PositionComponent,
                                      UnitComponent)

CASTER_VIS = "necroSpyder"
ENEMY_VIS = "necroDestroyer"
SUMMON_VIS = "necroSmnSwarm"
SUMMON_ABILITY = "ScarabHive"
SUMMON_COUNT = 2
BUILD = ["--roster", "1", "--p-units", CASTER_VIS, "--a-units", ENEMY_VIS]


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _snap_stats(snap, eid):
    for u in (snap.get("units") or []):
        if u.get("entityId") == eid:
            return u.get("stats") or {}
    return {}


def _free_ring(state, board, target_id):
    """`CanAddUnit(AdjacentTiles(target))` recalculé ICI depuis le state (voisines natives
    walkables, inoccupées par une unité VIVANTE) — l'oracle du nombre de summons attendus."""
    tgt = state.get_entity(target_id)
    tp = tgt.get_component(PositionComponent)
    ttile = board.id_at(tp.col, tp.row)
    occupied = set()
    for e in state.entities.values():
        pc = e.get_component(PositionComponent)
        uc = e.get_component(UnitComponent)
        if pc is None or (uc is not None and not uc.alive):
            continue
        t = board.id_at(pc.col, pc.row)
        if t is not None:
            occupied.add(t)
    return [t for t in board.neighbours_native(ttile)
            if board.walkable(t) and t not in occupied]


def _wall_in(state, board, target_id, leave: int):
    """CRAFTE la géométrie : bouche les voisines LIBRES de la cible avec des tokens occupants
    jusqu'à n'en laisser que `leave`. On DÉPLACE/POSE, on ne subit pas la géométrie de spawn.
    Renvoie les ids des tokens posés."""
    from engine.runner.components import HealthComponent
    posed = []
    free = _free_ring(state, board, target_id)
    for tid in free[:max(0, len(free) - leave)]:
        t = board.by_id[tid]
        e = state.add_entity()
        e.add_component(UnitComponent(visual_id="necroWarden", alive=True, ai_controlled=False))
        e.add_component(OwnerComponent(team=99, player=99))
        e.add_component(HealthComponent(hp=1, hp_max=1))
        e.add_component(PositionComponent(col=t["col"], row=t["row"]))
        posed.append(e.id)
    return posed


def test_summon_spawn_bit_exact(live_session, rpc, build_runner):
    from engine.entities.pathfinding.board import Board
    rid = build_runner("777", extra=BUILD)["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")

    dec0 = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    caster0 = next((u for u in (dec0.get("units") or []) if u.get("visualId") == CASTER_VIS), None)
    enemy0 = next((u for u in (dec0.get("units") or []) if u.get("visualId") == ENEMY_VIS), None)
    if caster0 is None or enemy0 is None:
        pytest.skip("caster/cible absent")
    caster_id, enemy_id = caster0["id"], enemy0["id"]
    my_team, my_player = caster0.get("team"), caster0.get("owner")

    # jouer l'IA native jusqu'au spawn des scarabs ; garder l'état d'AVANT chaque tour.
    before = None
    live = None
    for _ in range(12):
        b_dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        b_ob = rpc("observeBattle", {"runnerId": rid}, 40)
        b_snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
        before = (b_dec, b_ob, b_snap)
        rpc("aiPlayByUnit", {"runnerId": rid, "maxTurns": 1, "maxActivations": 9999,
                             "maxPump": 3000, "captureEvents": False}, 300)
        ob = rpc("observeBattle", {"runnerId": rid}, 40)
        swarms = [u for u in (ob.get("units") or []) if u.get("visualId") == SUMMON_VIS and not u.get("isDead")]
        if len(swarms) >= 1:
            snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
            live = {"swarms": swarms, "snap": snap,
                    "enemy_pos": next((u for u in (ob.get("units") or []) if u.get("squadId") == enemy_id), None)}
            break
    if live is None:
        pytest.skip("aucun scarab spawne en 12 tours IA")

    # === LIVE : stats + owner + adjacence ===
    sw = live["swarms"][0]
    sw_stats = _snap_stats(live["snap"], sw.get("squadId"))
    live_hp = sw.get("hp")
    live_team, live_player = sw.get("teamId"), sw.get("playerId")
    print(f"\n[SUMMON] live scarab hp={live_hp} stats(attack={sw_stats.get('attack')} "
          f"cc={sw_stats.get('critChance')}) team={live_team} player={live_player} "
          f"| caster team={my_team} player={my_player}")

    # owner = caster (CopyOwner)
    assert live_team == my_team and live_player == my_player, (
        f"summon owner live (team={live_team},player={live_player}) != caster (team={my_team},player={my_player})")

    # === OFFLINE : build_summon_context (stats) ===
    b_dec, b_ob, b_snap = before
    # niveau/mult du caster depuis son unitConfig
    csu = next((u for u in (b_snap.get("units") or [])
                if (u.get("unitConfig") or {}).get("visualId") == CASTER_VIS), None)
    cuc = (csu or {}).get("unitConfig") or {}
    lvl, mult = cuc.get("activeAbilityLevel"), int(cuc.get("abilityVariablesMultiplier") or 100)
    off_ctx = build_summon_context(0, SUMMON_VIS, SUMMON_ABILITY, lvl, mult)
    print(f"[SUMMON] offline ctx hp={off_ctx.health} attack={off_ctx.attack} cc={off_ctx.crit_chance} "
          f"(casterLevel={lvl} mult={mult})")
    assert off_ctx.health == live_hp, f"offline summon hp {off_ctx.health} != live {live_hp}"
    if sw_stats.get("attack") is not None:
        assert off_ctx.attack == sw_stats.get("attack"), \
            f"offline summon attack {off_ctx.attack} != live {sw_stats.get('attack')}"

    # === OFFLINE : SpawnUnitOperation (owner + placement) depuis l'etat d'AVANT ===
    state = load_state(b_dec, b_ob, b_snap, board=board)
    if state.get_entity(caster_id) is None or state.get_entity(enemy_id) is None:
        pytest.skip("caster/cible absents offline (snapshot incomplet)")
    n_free_before = len(_free_ring(state, board, enemy_id))
    before_ids = set(state.entities)
    spawned = SpawnUnitOperation.execute(state, caster_id, enemy_id, SUMMON_ABILITY, SUMMON_VIS, SUMMON_COUNT)
    # `First(<tri>, count)` rend min(count, len(source)) : le montage 1v1 laisse la cible dégagée,
    # donc les 2 summons doivent naître — mais l'assertion dit le VRAI invariant, pas la constante.
    assert len(spawned) == min(SUMMON_COUNT, n_free_before), (
        f"offline a spawne {len(spawned)} != min({SUMMON_COUNT}, {n_free_before})")
    assert n_free_before >= SUMMON_COUNT, (
        f"montage non discriminant : seulement {n_free_before} tuiles libres autour de la cible")
    assert set(state.entities) - before_ids == set(spawned), (
        "des entites ont ete creees HORS de la liste rendue (fantomes, cf. #254)")
    # owner + stats des summons offline
    enemy = state.get_entity(enemy_id)
    ep = enemy.get_component(PositionComponent)
    et = board.id_at(ep.col, ep.row)
    enemy_neigh = set(board.neighbours(et))
    for sid in spawned:
        e = state.get_entity(sid)
        oc = e.get_component(OwnerComponent)
        sc = e.get_component(StatsComponent)
        pc = e.get_component(PositionComponent)
        assert oc.team == my_team and oc.player == my_player, \
            f"summon offline owner (team={oc.team},player={oc.player}) != caster ({my_team},{my_player})"
        assert sc.ctx.health == live_hp, f"summon offline hp {sc.ctx.health} != live {live_hp}"
        assert pc is not None, "summon offline sans position (tuile libre adjacente cible introuvable)"
        assert board.id_at(pc.col, pc.row) in enemy_neigh, \
            f"summon offline ({pc.col},{pc.row}) PAS adjacent (evenq) a la cible"

    # === LIVE : les scarabs sont adjacents a la cible (regle de placement) ===
    epos = live.get("enemy_pos")
    if epos and epos.get("col") is not None:
        e_tile = board.id_at(epos["col"], epos["row"])
        e_neigh = set(board.neighbours(e_tile)) if e_tile is not None else set()
        for s in live["swarms"]:
            stile = board.id_at(s.get("col"), s.get("row")) if s.get("col") is not None else None
            assert stile in e_neigh, \
                f"scarab live ({s.get('col')},{s.get('row')}) PAS adjacent (evenq) a la cible {epos}"


def test_spawn_requires_a_tile(live_session, rpc, build_runner):
    """#254 — GARDE DU FANTÔME : le nombre de summons est `min(count, tuiles libres)`, et AUCUNE
    entité n'est créée sans `PositionComponent`.

    `IdunBattle.Entities.Behaviours.SpawnUnitBehaviour$$Execute` (branche `SpawnUnitOptions+0x60 ==
    0`) est un `foreach (tile in tileSelector.Select(ctx))` : l'entité NAÎT de l'itération, donc
    zéro tuile = zéro entité, zéro `On(UnitAdded)`, zéro on-appearance. Le port bouclait
    `range(count)` et ne posait la position que `if tile is not None` — le trop-plein devenait un
    summon hors plateau.

    Trois régimes CRAFTÉS sur le même état live (on bouche les voisines de la cible, on ne subit
    pas la géométrie) : 2 libres → 2 summons, 1 libre → 1 summon, 0 libre → AUCUNE entité. Face
    NATIVE des trois régimes : `probe_254_spawn_requires_tile.py` (natif 2/1/refus de cast, mêmes
    positions que le port, sur MC1_67/777 et C3_26/31337).

    ⚠ Un montage insuffisant ASSERTE — jamais un `skip` : un skip sur échec de montage passe VERT
    en ne testant rien. Les seuls `skip` tolérés ici sont l'INDISPONIBILITÉ de la plateforme
    (pas de `boardGraph`, unité absente du build) — jamais une géométrie qui ne convient pas."""
    from engine.entities.pathfinding.board import Board
    rid = build_runner("777", extra=BUILD)["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="native_sym")
    dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    caster0 = next((u for u in (dec.get("units") or []) if u.get("visualId") == CASTER_VIS), None)
    enemy0 = next((u for u in (dec.get("units") or []) if u.get("visualId") == ENEMY_VIS), None)
    if caster0 is None or enemy0 is None:
        pytest.skip("caster/cible absent")
    caster_id, enemy_id = caster0["id"], enemy0["id"]

    probe = load_state(dec, ob, snap, board=board)
    assert probe.get_entity(caster_id) is not None and probe.get_entity(enemy_id) is not None, \
        "caster/cible absents du state offline : le snapshot ne porte pas le montage"
    n_free0 = len(_free_ring(probe, board, enemy_id))
    assert n_free0 >= SUMMON_COUNT, (
        f"montage non discriminant : {n_free0} tuiles libres autour de la cible, il en faut "
        f"{SUMMON_COUNT} pour crafter les trois regimes (DEPLACER la cible, pas skipper)")

    for leave in (2, 1, 0):
        state = load_state(dec, ob, snap, board=board)
        _wall_in(state, board, enemy_id, leave)
        n_free = len(_free_ring(state, board, enemy_id))
        assert n_free == leave, f"montage rate : {n_free} libres au lieu de {leave}"
        before = set(state.entities)
        spawned = SpawnUnitOperation.execute(state, caster_id, enemy_id,
                                             SUMMON_ABILITY, SUMMON_VIS, SUMMON_COUNT)
        created = set(state.entities) - before
        want = min(SUMMON_COUNT, leave)
        assert len(spawned) == want, f"{leave} tuile(s) libre(s) -> {len(spawned)} summons != {want}"
        assert created == set(spawned), (
            f"{leave} libre(s) : entites creees {sorted(created)} != rendues {sorted(spawned)}")
        ghosts = [i for i in created
                  if state.get_entity(i).get_component(PositionComponent) is None]
        assert not ghosts, f"{leave} libre(s) : summon(s) SANS PositionComponent {ghosts} (#254)"
