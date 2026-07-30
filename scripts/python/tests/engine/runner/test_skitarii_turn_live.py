"""AdMech S4b-C : le Skitarii Vanguard (admecSmnVanguard) JOUE son tour offline, confronte au LIVE.

Le Vanguard summoned par ControlEdict (#19) porte le trait `Summon` -> il est `ai_controlled` et joue son
tour au TURN-START de sa team via le CHEMIN GENERIQUE deja porte (#65) : `run_ai_control_pass`
(summon_ai.py) -> `DefaultAiUnitTactic.calculate_next_action` (playbook complet via le bridge offline) ->
apply move (move=3) + attaque NORMALE. Mirror natif =
`IdunBattle.Operations.PlayAutomaticUnitsOperation$$Execute` (slot `IOperationProcessor` 0x71 appele par
`IdunBattle.Operations.StartTurnOperation$$Execute`) -- et NON `IdunGameViews$$QueueComputerActions`,
citation corrigee par #291 (`docs/rl/case-291-summon-activation.md`).
CE N'EST PAS un playbook bespoke (`ControlEditPlaybook IdunBattle.AI.Playbook.Loki.ControlEdictPlaybook$$.ctor` = utility 0, no-op ; le Vanguard n'a
aucune active ability). Travail = VERIFIER, pas re-implementer.

CRUX = l'attaque normale MULTI-ARME du Vanguard, selectionnee PAR PORTEE via le service natif UNIQUE
(`IdunBattle.Core.Services.BattleQuery$$GetAttackWeaponForDefaultNormalAttack`, meme port prediction<->combat) :
  - kit gameconfig (admecSmnVanguard) : melee `Physical` (1 hit) + ranged `Toxic` r2 (3 hits) ;
  - ADJACENT (dist hex 1) -> arme MELEE Physical, `ranged=False`, 1 coup ;
  - dist hex 2 (portee Toxic) -> arme RANGED Toxic, `ranged=True`, 3 coups.
Le `dist` est calcule DANS `AttackDamageOperation.execute` depuis les positions REELLES (adjacence HEX
`are_tiles_adjacent`, PAS Chebyshev), donc l'arme suit la geometrie finale de l'attaque.

CONFRONTATION (house style test_summon_ability_ports) : runner LIVE (board natif evenq + units reels),
etat charge offline, Vanguard place a une distance CONTROLEE d'un ennemi (DRIVE positions), puis :
  1. `test_skitarii_melee_weapon_when_adjacent` : Vanguard adjacent -> execute -> arme MELEE (profil+hits
     du weapon melee gameconfig), ennemi perd des PV ;
  2. `test_skitarii_ranged_weapon_at_distance_2` : Vanguard a dist 2 -> execute -> arme RANGED Toxic
     (profil+hits du weapon ranged gameconfig), ennemi perd des PV ;
  3. `test_skitarii_played_by_generic_ai_pass` : Vanguard HORS portee mais dans move=3 -> `run_ai_control_pass`
     le JOUE : il se rapproche de l'ennemi (dist BFS decroit) et l'attaque (arme coherente avec la geometrie
     finale). Valide le cablage complet ai_controlled -> bridge -> tactic -> apply (move + attaque normale).

Oracle = kit LIVE gameconfig (armes/profils) + geometrie NATIVE (boardGraph). ASCII only. NON committe.

GAP FERME par cette confrontation (test 3) : `state_bridge.build_from_state` construisait l'`AiDecisionContext`
SANS les 3 champs boardGraph requis `tile_id_by_pos`/`neigh_by_pos`/`walkable_by_pos` (ajoutes au contexte pour
le ciblage placement/self-cast #116/#117, cote LIVE via context.build) -> TypeError, le pass generique offline
ne jouait AUCUN summon. Aucun test n'exercait ce chemin end-to-end -> bit-rot silencieux. Fix = mirror OFFLINE
des 3 seams (`_board_topology_maps`, depuis `State.board`).
"""
from __future__ import annotations

import pytest

import gameconfig as GC
import hexgeo

SUMMON_VIS = "admecSmnVanguard"        # cle config (kit) du Vanguard ; visualId live = admecNpc1Vanguard
TAN_VIS = "admecMarshall"              # caster present dans le build -> fournit le niveau (scaling summon)
SUMMON_ABILITY = "ControlEdict"
ENEMY_VIS = "necroWarden"
BUILD = ["--roster", "1", "--p-units", f"{TAN_VIS},admecRuststalker",
         "--a-units", f"{ENEMY_VIS},{ENEMY_VIS}"]


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _skitarii_weapons():
    """(melee_weapon, ranged_weapon) du kit gameconfig admecSmnVanguard (Range absent=melee, present=ranged)."""
    weapons = (GC.unit(SUMMON_VIS) or {}).get("weapons") or []
    melee = next((w for w in weapons if not w.get("Range")), None)
    ranged = next((w for w in weapons if w.get("Range")), None)
    return melee, ranged


def _load(rpc, build_runner, seed="777"):
    """Runner LIVE -> etat offline (board natif evenq + snapshots + RNG cale). Mirror test_summon_ability_ports.

    `tiles=tileMeta` est OBLIGATOIRE : sans ce canal, `state.effects` ne porte AUCUN effet de TUILE, donc
    le gate #131 (`BasePathfinder$$NodesInNextLevel` -> `IsValidContinuePathTile` : une tuile
    `BlockEnteringUnits`/Swamp est un cul-de-sac de la flood-fill) est un no-op SILENCIEUX et la passe IA
    peut choisir une tuile de deplacement ILLEGALE (c'etait la cause du rouge de ce fichier, cf. case-r5)."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    from engine.runner.prng import IntBasedMersenneTwister
    rid = build_runner(seed, extra=BUILD)["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")
    tiles = rpc("tileMeta", {"runnerId": rid}, 90)
    dec = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
    s0 = rpc("dumpRng", {"runnerId": rid}, 30)
    state = load_state(dec, ob, snap, board=board, tiles=tiles)
    if _ok(s0) and s0.get("mt"):
        rng = IntBasedMersenneTwister(); rng.mt = list(s0["mt"]); rng.mti = s0["mti"]; state.rng = rng
    return state, board


def _tan(state):
    """(tan_id, level, mult, team, player) depuis l'etat offline -> scaling du summon (niveau du caster)."""
    from engine.runner.components import StatsComponent, OwnerComponent, UnitComponent
    for eid, e in state.entities.items():
        uc = e.get_component(UnitComponent)
        if uc is None or uc.visual_id != TAN_VIS:
            continue
        sc = e.get_component(StatsComponent); oc = e.get_component(OwnerComponent)
        if sc is None or oc is None:
            return None
        ctx = sc.ctx
        lvl = getattr(ctx, "active_ability_level", None)
        mult = int(getattr(ctx, "ability_variables_multiplier", 100) or 100)
        return eid, lvl, mult, oc.team, oc.player
    return None


def _pick_enemy(state, tan_team):
    """Un ennemi VIVANT (team != tan_team) avec position + HealthComponent."""
    from engine.runner.components import OwnerComponent, UnitComponent, HealthComponent, PositionComponent
    for eid, e in state.entities.items():
        oc = e.get_component(OwnerComponent); uc = e.get_component(UnitComponent)
        hc = e.get_component(HealthComponent); pc = e.get_component(PositionComponent)
        if oc is None or uc is None or hc is None or pc is None or not uc.alive:
            continue
        if oc.team == tan_team or hc.hp is None:
            continue
        return eid, pc
    return None


def _occupied(state):
    from engine.runner.operations.spawn import _occupied_tiles
    return _occupied_tiles(state)


def _free_neighbour(state, board, tile):
    """1re tuile LIBRE walkable voisine (board.neighbours) de `tile` -> adjacence HEX garantie (melee)."""
    occ = _occupied(state)
    for n in sorted(board.neighbours(tile)):
        if n not in occ and board.walkable(n):
            return n
    return None


def _free_tile_at_hexdist(state, board, ref_col, ref_row, d):
    """Tuile LIBRE walkable a `hexgeo.distance` == d de (ref_col,ref_row) et NON voisine board (si d>=2)."""
    occ = _occupied(state)
    ref_tile = board.id_at(ref_col, ref_row)
    neigh = set(board.neighbours(ref_tile)) if ref_tile is not None else set()
    for tid in board.by_id:
        if tid in occ or not board.walkable(tid):
            continue
        if d >= 2 and tid in neigh:
            continue
        c, r = board.coord(tid)
        if hexgeo.distance((ref_col, ref_row), (c, r)) == d:
            return tid, c, r
    return None, None, None


def _bfs_dist(board, start):
    from collections import deque
    seen = {start: 0}; q = deque([start])
    while q:
        x = q.popleft()
        for n in board.neighbours(x):
            if n not in seen:
                seen[n] = seen[x] + 1; q.append(n)
    return seen


def _spawn(state, board, col, row, ability, lvl, mult, team, player):
    from engine.runner.operations.spawn import _spawn_config_grot
    tile = board.id_at(col, row)
    return _spawn_config_grot(state, SUMMON_VIS, tile, ability, lvl, mult, team, player)


def _prep(rpc, build_runner):
    """Charge l'etat + resout (tan_id, lvl, mult, team, player) + un ennemi. Skip propre si indispo."""
    state, board = _load(rpc, build_runner)
    tan = _tan(state)
    if tan is None:
        pytest.skip("Tan Gi'da absent offline / sans StatsComponent")
    tan_id, lvl, mult, team, player = tan
    if lvl is None:
        pytest.skip("niveau du caster indisponible (scaling summon non resoluble)")
    if state.rng is None:
        pytest.skip("RNG non cale (dumpRng KO)")
    en = _pick_enemy(state, team)
    if en is None:
        pytest.skip("aucun ennemi vivant avec position/HP")
    enemy_id, epc = en
    return state, board, lvl, mult, team, player, enemy_id, epc


def test_skitarii_melee_weapon_when_adjacent(live_session, rpc, build_runner):
    """Vanguard ADJACENT a l'ennemi -> attaque normale = arme MELEE (Physical, `ranged=False`, hits melee)."""
    from engine.runner.operations.damage import AttackDamageOperation
    from engine.runner.components import HealthComponent, PositionComponent
    from engine.services.battle_query import are_tiles_adjacent

    state, board, lvl, mult, team, player, enemy_id, epc = _prep(rpc, build_runner)
    melee_w, _ranged_w = _skitarii_weapons()
    if melee_w is None:
        pytest.skip("kit admecSmnVanguard sans arme melee")
    exp_profile = melee_w.get("DamageProfile")
    exp_hits = int(melee_w.get("hits") or 1)

    etile = board.id_at(epc.col, epc.row)
    nb = _free_neighbour(state, board, etile)
    if nb is None:
        pytest.skip("aucune tuile libre adjacente a l'ennemi")
    sc, sr = board.coord(nb)
    sid = _spawn(state, board, sc, sr, SUMMON_ABILITY, lvl, mult, team, player)
    if sid is None:
        pytest.skip("spawn Vanguard KO")
    spc = state.get_entity(sid).get_component(PositionComponent)
    assert are_tiles_adjacent((spc.col, spc.row), (epc.col, epc.row), board), "Vanguard non adjacent (drive KO)"

    hp0 = state.get_entity(enemy_id).get_component(HealthComponent).hp
    r = AttackDamageOperation.execute(state, sid, enemy_id)
    hp1 = state.get_entity(enemy_id).get_component(HealthComponent).hp
    print(f"[skitarii melee] profile={r.get('profile')} ranged={r.get('ranged')} hits={r.get('hits')} "
          f"hp {hp0}->{hp1} (attendu MELEE {exp_profile} x{exp_hits})")

    assert r is not None, "attaque melee sans resultat"
    assert r.get("ranged") is False, f"arme melee attendue (ranged=False), obtenu ranged={r.get('ranged')}"
    assert r.get("profile") == exp_profile, f"profil {r.get('profile')} != melee gameconfig {exp_profile}"
    assert r.get("hits") == exp_hits, f"hits melee {r.get('hits')} != gameconfig {exp_hits}"
    assert hp1 < hp0, f"attaque melee sans degat ({hp0}->{hp1})"


def test_skitarii_ranged_weapon_at_distance_2(live_session, rpc, build_runner):
    """Vanguard a dist hex 2 (portee Toxic) -> attaque normale = arme RANGED Toxic (`ranged=True`, 3 hits)."""
    from engine.runner.operations.damage import AttackDamageOperation
    from engine.runner.components import HealthComponent, PositionComponent
    from engine.services.battle_query import are_tiles_adjacent

    state, board, lvl, mult, team, player, enemy_id, epc = _prep(rpc, build_runner)
    _melee_w, ranged_w = _skitarii_weapons()
    if ranged_w is None:
        pytest.skip("kit admecSmnVanguard sans arme ranged")
    exp_profile = ranged_w.get("DamageProfile")
    exp_hits = int(ranged_w.get("hits") or 1)
    exp_range = int(ranged_w.get("Range") or 0)
    if exp_range < 2:
        pytest.skip(f"arme ranged Range={exp_range} < 2 (scenario dist-2 non applicable)")

    tid, sc, sr = _free_tile_at_hexdist(state, board, epc.col, epc.row, 2)
    if tid is None:
        pytest.skip("aucune tuile libre a dist hex 2 de l'ennemi")
    sid = _spawn(state, board, sc, sr, SUMMON_ABILITY, lvl, mult, team, player)
    if sid is None:
        pytest.skip("spawn Vanguard KO")
    spc = state.get_entity(sid).get_component(PositionComponent)
    assert not are_tiles_adjacent((spc.col, spc.row), (epc.col, epc.row), board), "Vanguard adjacent a tort"
    assert hexgeo.distance((spc.col, spc.row), (epc.col, epc.row)) == 2, "Vanguard pas a dist hex 2 (drive KO)"

    hp0 = state.get_entity(enemy_id).get_component(HealthComponent).hp
    r = AttackDamageOperation.execute(state, sid, enemy_id)
    hp1 = state.get_entity(enemy_id).get_component(HealthComponent).hp
    print(f"[skitarii ranged] profile={r.get('profile')} ranged={r.get('ranged')} hits={r.get('hits')} "
          f"hp {hp0}->{hp1} (attendu RANGED {exp_profile} x{exp_hits} r{exp_range})")

    assert r is not None, "attaque ranged sans resultat"
    assert r.get("ranged") is True, f"arme ranged attendue (ranged=True), obtenu ranged={r.get('ranged')}"
    assert r.get("profile") == exp_profile, f"profil {r.get('profile')} != ranged gameconfig {exp_profile}"
    assert r.get("hits") == exp_hits, f"hits ranged {r.get('hits')} != gameconfig {exp_hits}"
    assert hp1 < hp0, f"attaque ranged sans degat ({hp0}->{hp1})"


def test_skitarii_played_by_generic_ai_pass(live_session, rpc, build_runner):
    """Vanguard HORS portee (BFS 3) mais dans move=3 -> `run_ai_control_pass` le JOUE : il se rapproche de
    l'ennemi (dist BFS decroit) et l'attaque (arme coherente avec la geometrie finale). Valide le cablage
    ai_controlled -> bridge -> tactic -> apply (move + attaque normale)."""
    from engine.runner.operations.summon_ai import run_ai_control_pass, collect_ai_controlled, NORMAL_ATTACK_ID
    from engine.runner.components import HealthComponent, PositionComponent
    from engine.services.battle_query import are_tiles_adjacent

    state, board, lvl, mult, team, player, enemy_id, epc = _prep(rpc, build_runner)
    etile = board.id_at(epc.col, epc.row)
    bfs = _bfs_dist(board, etile)

    # tuile LIBRE a BFS-dist 3 de l'ennemi (hors portee Toxic 2, atteignable en move=3).
    occ = _occupied(state)
    spot = next((t for t in board.by_id
                 if bfs.get(t) == 3 and t not in occ and board.walkable(t)), None)
    if spot is None:
        pytest.skip("aucune tuile libre a BFS-dist 3 de l'ennemi")
    sc, sr = board.coord(spot)
    sid = _spawn(state, board, sc, sr, SUMMON_ABILITY, lvl, mult, team, player)
    if sid is None:
        pytest.skip("spawn Vanguard KO")

    # #291 -- ce montage POSE un Vanguard « deja present au debut du tour », il ne simule pas une
    # apparition du tour courant. Or le spawn mirrore desormais `SpawnUnitBehaviour$$
    # TriggerSpawnedUnitBehaviours`, qui TERMINE le tour d'une unite qui apparait pendant le tour de
    # son proprietaire -- et `PlayAutomaticUnitsOperation$$Execute` gate sur `!HasFlag(u, 3 =
    # TurnFinished)`. Dans une vraie partie, `StartTurnOperation$$Execute` appelle `RemoveTurnFlags`
    # sur les unites du joueur ENTRANT **avant** le slot 0x71 `PlayAutomaticUnits` ; le montage
    # appelle `run_ai_control_pass` nu, il doit donc mirrorer ce reset explicitement. (Le retirer
    # ferait tomber le test -- ce qui est le bon comportement : un summon frais NE joue PAS au tour
    # de son apparition, cf. `test_waaagh_fresh_summons_get_no_activation_live_and_port`.)
    from engine.runner.components import UnitFlagsComponent as _UF
    _fl = state.get_entity(sid).get_component(_UF)
    if _fl is not None:
        _fl.remove_turn_flags(include_no_action=False, new_activation=True)

    # le Vanguard doit etre la SEULE unite ai_controlled du player (Tan/Ruststalker = Heroes).
    assert sid in collect_ai_controlled(state, player), "Vanguard non collecte comme ai_controlled"

    def _skit_tile():
        p = state.get_entity(sid).get_component(PositionComponent)
        return board.id_at(p.col, p.row) if p is not None else None

    d_before = bfs.get(_skit_tile(), 99)
    hp0 = state.get_entity(enemy_id).get_component(HealthComponent).hp
    results = run_ai_control_pass(state, player)
    hp1 = state.get_entity(enemy_id).get_component(HealthComponent).hp
    res = next((x for x in results if x.get("uid") == sid), None)
    d_after = bfs.get(_skit_tile(), 99)
    atk = (res or {}).get("attack") or {}
    print(f"[skitarii generic] res={ {k: res.get(k) for k in ('moved','kind','ability','target')} if res else None} "
          f"d_bfs {d_before}->{d_after} hp {hp0}->{hp1} atk(ranged={atk.get('ranged')},hits={atk.get('hits')})")

    assert res is not None and "error" not in res, f"Vanguard non joue par le pass generique : {res}"
    # 1. il s'est RAPPROCHE de l'ennemi (move vers la cible).
    assert res.get("moved") is not None, "le Vanguard n'a pas bouge (move attendu, hors portee au depart)"
    assert d_after < d_before, f"le Vanguard ne s'est pas rapproche (BFS {d_before}->{d_after})"
    # 2. il a ATTAQUE l'ennemi avec son attaque NORMALE.
    assert res.get("kind") == "ability" and res.get("ability") == NORMAL_ATTACK_ID, \
        f"attaque normale attendue, obtenu kind={res.get('kind')} ability={res.get('ability')}"
    assert res.get("target") == enemy_id, f"cible {res.get('target')} != ennemi {enemy_id}"
    assert atk, "aucun resultat d'attaque (attaque non executee)"
    assert hp1 < hp0, f"le Vanguard a decide d'attaquer mais l'ennemi n'a pas perdu de PV ({hp0}->{hp1})"
    # 3. arme coherente avec la geometrie FINALE (adjacent -> melee ; sinon ranged).
    sp = state.get_entity(sid).get_component(PositionComponent)
    adj_final = are_tiles_adjacent((sp.col, sp.row), (epc.col, epc.row), board)
    assert bool(atk.get("ranged")) == (not adj_final), \
        f"arme incoherente avec la geometrie finale (adjacent={adj_final}, ranged={atk.get('ranged')})"
