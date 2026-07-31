"""#149 slice-11 : ScarabSummon (1047) MIGRATION vers l'arbre DSL -- la behaviour EST `scarab_summon_tree()`.

`IdunBattleLogic.Entities.Abilities.Active.Loki.ScarabSummonAbility$$ExecuteBehaviour` (DECOMPILE) = un noeud `Spawn` UNIQUE (plain `Execute`) :
    Execute( Spawn(self@0x160,
                   PickRandomly(CanAddUnit(AdjacentTiles(self@0x160)), 1),   # 1 tuile libre adjacente a SOI
                   unitId=GetStringConstant(config,0)=necroSmnSwarm,
                   SpawnUnitOptions.CopyOwner(caster)                        # clone owner+stats du parent
                     .onAppearance = PerformAIAttack(1)) )                   # le double attaque immediatement
DISTINCT de ScarabHive (WithStatsFromConfig summoner-scaled + AddEffect(0x4a3) + attaque de la CIBLE) :
ScarabSummon = auto-DEDOUBLEMENT du swarm (CopyOwner clone-du-parent, count-1, PAS d'effet, attaque AI du double).

Le caster EST un `necroSmnSwarm` (un summon). Comme il n'est PAS buildable via --p-units (absent d'unit_map),
on le materialise d'abord via le chemin ScarabHive VALIDE (necroSpyder spawn 2 swarms), puis on prend un swarm
comme caster de ScarabSummon. On valide que la MIGRATION prend bien le chemin DSL (`dsl:True`) et reproduit la
structure : 1 necroSmnSwarm CLONE spawne owner du swarm-parent, adjacent au swarm-parent, l'attaque on-appearance
ampute l'ennemi le plus proche, `sum(attacks.total) == PV perdus` depuis le spawn du clone. Lit l'etat LIVE.
ASCII-only. NON committe (tests confront live, hors depot).
"""
from __future__ import annotations

import pytest

from engine.runner.snapshot import load_state
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.components import HealthComponent, PositionComponent, OwnerComponent, UnitComponent
from engine.runner.abilities.loki import ScarabHiveAbility, ScarabSummonAbility

CASTER_VIS = "necroSpyder"      # summoner (materialise le 1er swarm via ScarabHive)
ENEMY_VIS = "necroDestroyer"    # cible tanky (survit aux attaques on-appearance)
SUMMON_VIS = "necroSmnSwarm"
# `--dmg-target 1` : la frappe ADVERSE est neutralisee. Necessaire depuis #348 -- le double s'APPROCHE
# avant de frapper (`+0x78 moveAmount = null` -> `GenerateActionTiles` sur la plage complete), et ce
# pas declenche le vecteur after-move de la cible (`EvaluateAfterMoveTriggers` -> overwatch), qui le
# TUAIT avant son attaque. Un clone mort ne frappe pas : le test mesurait alors l'overwatch, pas
# l'on-appearance qu'il verrouille.
BUILD = ["--roster", "1", "--p-units", CASTER_VIS, "--a-units", ENEMY_VIS, "--dmg-target", "1"]


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _seed_rng(s):
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"]); rng.mti = s["mti"]
    return rng


def test_scarab_summon_migration_is_dsl_tree(live_session, rpc, build_runner):
    """`ScarabSummonAbility.execute_behaviour` prend le chemin DSL (`scarab_summon_tree`) : 1 clone spawne
    adjacent au swarm-parent + on-appearance qui ampute l'ennemi le plus proche, sum(attacks) == PV perdus."""
    from engine.entities.pathfinding.board import Board
    rid = build_runner("777", extra=BUILD)["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")

    dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    s0 = rpc("dumpRng", {"runnerId": rid}, 30)
    spyder = next((u for u in (dec.get("units") or []) if u.get("visualId") == CASTER_VIS), None)
    enemy = next((u for u in (dec.get("units") or []) if u.get("visualId") == ENEMY_VIS), None)
    if spyder is None or enemy is None or not _ok(s0):
        pytest.skip("summoner/cible/rng absent")
    spyder_id, enemy_id = spyder["id"], enemy["id"]

    state = load_state(dec, ob, snap, board=board)
    state.rng = _seed_rng(s0)
    if state.get_entity(spyder_id) is None or state.get_entity(enemy_id) is None:
        pytest.skip("summoner/cible absents offline")

    # === materialise un swarm (caster de ScarabSummon) via le chemin ScarabHive VALIDE ===
    hive = ScarabHiveAbility().execute_behaviour(state, spyder_id, enemy_id)
    hive_spawned = (hive or {}).get("spawned") or []
    if not hive_spawned:
        pytest.skip("ScarabHive n'a pas spawne de swarm (prerequis)")
    swarm_id = hive_spawned[0]                      # le swarm-parent qui va s'auto-dedoubler

    # === GEOMETRIE PILOTEE ===
    # Le double atterrit sur UNE tuile TIREE parmi les voisines LIBRES du parent
    # (`PickRandomly(CanAddUnit(AdjacentTiles(self@0x160)), 1)`), et son on-appearance passe par le corps
    # unique `perform_ai_ability_unit_behaviour`, qui GATE l'attaque sur la portee d'arme
    # (`IdunBattle.Core.Services.TargetingQuery$$GetRange` = 1 : le swarm n'a qu'une arme de MELEE).
    # On rend donc la tuile d'atterrissage DETERMINISTE (une seule voisine libre, les autres bloquees par
    # des ALLIES) et ADJACENTE a la cible. Sans ce pilotage, le double tombait au hasard a 1 ou 2 hex de
    # l'ennemi et le test mesurait le residu « le port n'APPROCHE pas le double » (le natif, lui, joue un
    # TOUR complet : `PerformAIAttack` = `+0x70 allowMoveAction=1`, `+0x78 moveAmount=null`), au lieu de
    # l'on-appearance qu'il veut valider.
    blockers = [spyder_id] + list(hive_spawned[1:])          # tous ALLIES du swarm (aucun ennemi de plus)
    trio = None
    for c in sorted(board.by_id):
        if not board.walkable(c):
            continue
        nb = [n for n in board.neighbours(c) if board.walkable(n)]
        if not (2 <= len(nb) <= len(blockers) + 1):
            continue
        for p in nb:
            js = [j for j in board.neighbours(p) if board.walkable(j) and j != c and j not in nb]
            if js:
                trio = (c, p, js[0], [n for n in nb if n != p])
                break
        if trio:
            break
    if trio is None:
        pytest.skip("aucune geometrie (parent, tuile libre unique, cible adjacente) sur ce board")
    c_tile, p_tile, j_tile, block_tiles = trio

    def _put(uid, tile):
        pc = state.get_entity(uid).get_component(PositionComponent)
        pc.col, pc.row = board.coord(tile)

    _put(swarm_id, c_tile)
    for tile, uid in zip(block_tiles, blockers):
        _put(uid, tile)
    _put(enemy_id, j_tile)
    print(f"\n[SCARABSUMMON geo] parent@{c_tile} ; seule libre P@{p_tile} ; cible@{j_tile} ; "
          f"bloquees={block_tiles}")

    sowner = state.get_entity(swarm_id).get_component(OwnerComponent)
    spc = state.get_entity(swarm_id).get_component(PositionComponent)
    assert spc is not None, "swarm-parent sans position"
    swarm_neigh = set(board.neighbours(board.id_at(spc.col, spc.row)))

    before_ids = set(state.entities.keys())
    # Le pre-step ScarabHive a fait attaquer l'ennemi par 2 swarms -> il est deja bas (risque d'OVERKILL qui
    # decouplerait le total roule du delta HP). On restaure les PV des ennemis a plein AVANT ScarabSummon (drive
    # d'etat legitime) : le clone attaque une cible fraiche tanky -> invariant propre `delta HP == total roule`.
    for i, e in state.entities.items():
        oc = e.get_component(OwnerComponent)
        hc = e.get_component(HealthComponent)
        if oc is not None and hc is not None and oc.team != sowner.team:
            hc.hp = hc.hp_max
    # PV de TOUS les ennemis AVANT le cast (la cible on-appearance = nearest enemy, capturee par le diag ; on
    # assied la validation sur le delta HP agrege des ennemis == somme des degats du diag).
    enemy_hp_before = {i: e.get_component(HealthComponent).hp
                       for i, e in state.entities.items()
                       if (e.get_component(OwnerComponent) or OwnerComponent(-1, -1)).team != sowner.team
                       and e.get_component(HealthComponent) is not None}

    # === chemin DSL migre (appel DIRECT de la classe d'ability ; ScarabSummon est SANS cible) ===
    res = ScarabSummonAbility().execute_behaviour(state, swarm_id, None)
    print(f"\n[SCARABSUMMON migration] dsl={res.get('dsl')} replica={res.get('replica')} "
          f"spawned={res.get('spawned')} attacks={res.get('attacks')}")

    assert res is not None and res.get("dsl") is True, f"arbre DSL non pris: {res}"
    assert res.get("replica") is True, f"champ replica manquant: {res}"
    spawned = res.get("spawned") or []
    assert len(spawned) == 1, f"{len(spawned)} clones spawnes (attendu 1 = COUNT)"

    # le clone est une NOUVELLE entite necroSmnSwarm, owner du swarm-parent (CopyOwner), adjacent au swarm-parent
    new_ids = [i for i in state.entities.keys() if i not in before_ids]
    assert set(spawned) == set(new_ids), f"spawned {sorted(spawned)} != nouvelles entites {sorted(new_ids)}"
    # ⚠ La tuile lue est le POINT DE CHUTE (`spawn_pos`, capture a l'emission `SpawnUnit`), PAS la
    # position finale : depuis #348 l'on-appearance `PerformAIAttack` (`+0x78 moveAmount = null`)
    # DEPLACE le double avant de frapper -- confronte live (`test_ai_approach_live`, regime `touch` :
    # le natif change lui aussi de tuile alors qu'il est deja au contact). Lire la position finale
    # mesurerait cette approche, pas le placement `AdjacentTiles(self)` que ce test verrouille.
    spawn_pos = res.get("spawn_pos") or {}
    for sid in spawned:
        e = state.get_entity(sid)
        oc = e.get_component(OwnerComponent)
        uc = e.get_component(UnitComponent)
        landed = spawn_pos.get(sid)
        assert uc is not None and uc.visual_id == SUMMON_VIS, f"clone {sid} n'est pas un {SUMMON_VIS}"
        assert oc.team == sowner.team and oc.player == sowner.player, "clone owner != swarm-parent (CopyOwner)"
        assert landed is not None and board.id_at(*landed) in swarm_neigh, (
            "clone PAS adjacent au swarm-parent a l'atterrissage")
        assert board.id_at(*landed) == p_tile, (
            "le clone n'a pas atterri sur la SEULE voisine libre -> geometrie pilotee non tenue")

    # === on-appearance : l'ennemi le plus proche perd des PV, sum(attacks.total) == somme des PV perdus ===
    attacks = res.get("attacks") or []
    assert attacks, "aucune attaque on-appearance emise"
    assert len(attacks) == 1, f"attendu 1 attaque on-appearance (COUNT=1 -> 1 clone) : {attacks}"
    # la cible doit etre un ennemi (team != celle du clone) -- PerformAIAttack -> nearest enemy
    for a in attacks:
        toc = state.get_entity(a["target"]).get_component(OwnerComponent)
        assert toc is not None and toc.team != sowner.team, "on-appearance a frappe un allie (pas un ennemi)"
    total = sum((a.get("total") or 0) for a in attacks)
    # delta HP agrege sur les ennemis == somme des degats du diag (robuste a quelle cible est la plus proche)
    hp_lost = sum(enemy_hp_before[i] - state.get_entity(i).get_component(HealthComponent).hp
                  for i in enemy_hp_before if state.get_entity(i) is not None)
    print(f"[SCARABSUMMON migration] on-appearance total={total} PV ennemis perdus={hp_lost}")
    assert total > 0, f"attaque on-appearance nulle: {attacks}"
    assert hp_lost == total, f"PV ennemis perdus {hp_lost} != sum(attacks) {total}"
