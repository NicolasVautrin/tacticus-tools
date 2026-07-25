"""VALIDATION LIVE des ports d'ability de summon (#65 SLICE 2 c') sur board/stats REELS.

On construit un runner live (board natif + units reels), on charge l'etat offline, puis on applique les
abilities portees via le CHEMIN REEL `summon_ai._apply_active_ability` (handler-vs-generic) et on confronte
la STRUCTURE au natif :

  - ValkyrieStrike (1018) : le port dedie EXCLUT du generique -> AUCUN degat immediat + effet 1022 pose
    (correction du sur-tir). Controle : `_is_active_attack_ability(1018) is True` (le sur-tir etait reel).
  - PlasmaGrenade (1098) : main sur target (hits = `nrOfHits`) + splash sur `_adjacent_enemies_of` (hits =
    `nrOfHits_2`). Le SET splash == voisins boardGraph (NATIF) de la cible INTER ennemis (hors cible).

Geometrie = adjacence NATIVE (boardGraph -> Board evenq). Degat exact (RNG cale) = raffinement non teste ici
(comme test_summon_trigger) ; on valide COUNTS + SET + no-fire, i.e. les priorites 1/2/4 du spec validator.

ORACLE des COUPS (#96) -- aucune valeur figee. Le decompile de
`IdunBattleLogic.Entities.Abilities.Active.Loki.PlasmaGrenadeAbility$$ExecuteBehaviour` passe
`GetNumberConstant(config, 0x2f)` (main) et `GetNumberConstant(config, 0x32)` (splash) TELS QUELS aux deux
feuilles `AttackWithAttackDamage` : ce sont des scalaires BRUTS, leur oracle est donc `constants.nrOfHits` /
`constants.nrOfHits_2` de gameconfig (0x2f/0x32 resolus sur `IdunBattle.Configuration.AbilityConstantType`).
Le `hits` que le diag expose est ici EXACTEMENT ce brut : la factory native de PlasmaGrenade est
`AttackWithAbilityDamage` (famille ABILITY), et `AbilityDamageOperation.Execute` n'appelle PAS `GetAttackHits`
-- le canal de coups (ExtraHits, Parry/Camouflage/Diminutive, auras) n'est pas traverse sur ce vecteur.
Les deux cles ayant des valeurs DIFFERENTES, l'une ne peut pas se faire passer pour l'autre.

NON committe (tests confront live, hors depot).
"""
from __future__ import annotations

import pytest

from engine.runner.snapshot import load_state
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.components import (OwnerComponent, PositionComponent, HealthComponent,
                                      UnitComponent)

PLASMA_GRENADE = 1098
VALKYRIE_STRIKE = 1018
VALKYRIE_EFFECT = 1022


def _seed_rng(s):
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"]); rng.mti = s["mti"]
    return rng


def _tile_of(board, state, uid):
    pc = state.get_entity(uid).get_component(PositionComponent)
    return board.id_at(pc.col, pc.row) if pc is not None else None


def _load(rpc, build_runner):
    """(state, board, dec, mkstate) -- `mkstate()` reconstruit un etat NEUF depuis les MEMES payloads deja
    en cache (aucun RPC, aucun runner de plus) : indispensable pour re-caster proprement, PV et rng remis
    a leur valeur d'origine (controles de derivation d'oracle)."""
    from engine.entities.pathfinding.board import Board
    rid = build_runner("777")["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")
    dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    s0 = rpc("dumpRng", {"runnerId": rid}, 30)

    def mkstate():
        st = load_state(dec, ob, snap, board=board)
        if isinstance(s0, dict) and s0.get("mt"):
            st.rng = _seed_rng(s0)
        return st
    return mkstate(), board, dec, mkstate


def _teams(state):
    """(_my_unit_id, enemies_by_team) : renvoie un caster de reference + la liste des ennemis d'une team."""
    by_team: dict = {}
    for eid, e in state.entities.items():
        oc = e.get_component(OwnerComponent)
        uc = e.get_component(UnitComponent)
        pc = e.get_component(PositionComponent)
        if oc is None or uc is None or pc is None or not uc.alive:
            continue
        by_team.setdefault(oc.team, []).append(eid)
    return by_team


def _pick_target_with_adjacent_enemy(state, board):
    """Cherche (caster_team_unit, target, expected_splash) : une cible d'une team B ayant >=1 autre unite B
    adjacente (boardGraph), et un caster de team A. DRIVE une 2e unite B adjacente si aucune naturelle."""
    by_team = _teams(state)
    if len(by_team) < 2:
        return None
    teams = sorted(by_team.keys())
    team_a, team_b = teams[0], teams[1]
    caster = by_team[team_a][0]
    # cherche une cible team_b ayant un voisin team_b
    for tgt in by_team[team_b]:
        ttile = _tile_of(board, state, tgt)
        if ttile is None:
            continue
        neigh = set(board.neighbours(ttile))
        adj = [u for u in by_team[team_b]
               if u != tgt and _tile_of(board, state, u) in neigh]
        if adj:
            return caster, tgt, sorted(adj)
    # aucune adjacence naturelle -> DRIVE : place une 2e unite team_b sur une tuile libre adjacente a la 1re
    if len(by_team[team_b]) < 2:
        return None
    tgt = by_team[team_b][0]
    victim = by_team[team_b][1]
    ttile = _tile_of(board, state, tgt)
    occupied = {_tile_of(board, state, u) for u in state.entities
                if state.get_entity(u).get_component(PositionComponent) is not None}
    for nb in board.neighbours(ttile):
        info = board.by_id.get(nb)
        if info is not None and nb not in occupied and board.walkable(nb):
            state.get_entity(victim).get_component(PositionComponent).col = info["col"]
            state.get_entity(victim).get_component(PositionComponent).row = info["row"]
            return caster, tgt, [victim]
    return None


def test_valkyrie_strike_no_immediate_damage(rpc, build_runner):
    """1018 = post l'effet 1022, ZERO degat immediat (sur-tir generique corrige)."""
    from engine.runner.operations.summon_ai import _apply_active_ability, _is_active_attack_ability
    state, board, _dec, _mk = _load(rpc, build_runner)
    by_team = _teams(state)
    if len(by_team) < 2:
        pytest.skip("pas 2 teams")
    teams = sorted(by_team.keys())
    caster, target = by_team[teams[0]][0], by_team[teams[1]][0]

    # controle : sans le port dedie, 1018 (damageProfile Blast) serait classe attaque -> sur-tir reel.
    assert _is_active_attack_ability(VALKYRIE_STRIKE) is True

    thc = state.get_entity(target).get_component(HealthComponent)
    hp_before = thc.hp
    res = _apply_active_ability(state, caster, target, VALKYRIE_STRIKE)
    hp_after = state.get_entity(target).get_component(HealthComponent).hp
    eff_names = [getattr(ef, "name", None) for ef in state.effects.active_effects(target, {"hp": hp_after})] \
        if state.effects is not None else []
    print(f"\n[VALKYRIE] routed={res.get('routed')} hp {hp_before}->{hp_after} effects={eff_names}")

    assert res.get("routed") == "handler", f"1018 non route au handler (sur-tir NON corrige) : {res}"
    assert hp_after == hp_before, f"1018 a inflige {hp_before - hp_after} degat IMMEDIAT (doit etre 0)"
    assert any((n or "").startswith("ValkyrieStrike") for n in eff_names) \
        or VALKYRIE_EFFECT in [getattr(ef, "effect_type", None) for ef in
                               (state.effects.active_effects(target, {"hp": hp_after}) if state.effects else [])], \
        f"effet 1022 ValkyrieStrike_Effect non pose : {eff_names}"


def test_plasma_grenade_main_plus_splash(rpc, build_runner, monkeypatch):
    """1098 = attaque main (`nrOfHits` coups) sur target + splash (`nrOfHits_2` coups) sur les ennemis
    adjacents (set == boardGraph). Les deux comptes viennent de gameconfig (cf. ORACLE en en-tete)."""
    import gameconfig as GC
    from engine.runner.operations.summon_ai import _apply_active_ability
    cst = (GC.ability("PlasmaGrenade") or {}).get("constants") or {}
    cfg_main, cfg_splash = cst.get("nrOfHits"), cst.get("nrOfHits_2")
    assert cfg_main is not None and cfg_splash is not None, \
        f"oracle introuvable : constants nrOfHits/nrOfHits_2 de PlasmaGrenade (lu: {cst})"
    cfg_main, cfg_splash = int(cfg_main), int(cfg_splash)
    assert cfg_main != cfg_splash, (
        f"constants.nrOfHits == nrOfHits_2 == {cfg_main} : les deux volets ne sont plus distinguables, "
        f"ce test ne verrait plus une feuille qui lirait la MAUVAISE cle")
    state, board, _dec, mkstate = _load(rpc, build_runner)
    picked = _pick_target_with_adjacent_enemy(state, board)
    if picked is None:
        pytest.skip("pas de cible avec ennemi adjacent (ni drivable)")
    caster, target, expected_splash = picked

    # SET attendu recalcule apres un eventuel drive de position (verite = voisins boardGraph INTER ennemis).
    ttile = _tile_of(board, state, target)
    neigh = set(board.neighbours(ttile))
    co_team = state.get_entity(caster).get_component(OwnerComponent).team
    enemies_adj = sorted(
        u for u, e in state.entities.items()
        if u not in (caster, target)
        and (e.get_component(OwnerComponent) or OwnerComponent(-1, -1)).team != co_team
        and (e.get_component(UnitComponent) or UnitComponent(None, False)).alive
        and _tile_of(board, state, u) in neigh)

    res = _apply_active_ability(state, caster, target, PLASMA_GRENADE)
    diag = (res or {}).get("diag") or {}
    # #149 slice-6 : PlasmaGrenade est un arbre DSL -> le diag expose `main_attack`/`splash` (chaque `attack`
    # porte un scalaire `hits` = nb de coups, cf. AttackDamageOperation.execute_ability_attack), PLUS de champs
    # scalaires `hits_main`/`hits_splash` (ancien retour imperatif `_splash_ability_behaviour`).
    main = diag.get("main_attack") or {}
    splash = diag.get("splash") or []
    splash_ids = sorted(x["target"] for x in splash)
    splash_hits = sorted({(x.get("attack") or {}).get("hits") for x in splash})
    print(f"\n[PLASMA] routed={res.get('routed')} hits_main={main.get('hits')} "
          f"splash_hits={splash_hits} splash={splash_ids} expected={enemies_adj}")

    assert res.get("routed") == "handler", f"1098 non route au handler : {res}"
    assert diag.get("main_attack") is not None, "attaque main absente"
    assert main.get("hits") == cfg_main, \
        f"hits main {main.get('hits')} != constants.nrOfHits={cfg_main} (oracle gameconfig, 0x2f)"
    for x in splash:                                        # chaque volet splash = constants.nrOfHits_2
        h = (x.get("attack") or {}).get("hits")
        assert h == cfg_splash, (f"hits splash cible {x.get('target')} = {h} != "
                                 f"constants.nrOfHits_2={cfg_splash} (oracle gameconfig, 0x32)")
    assert splash_ids == enemies_adj, \
        f"SET splash {splash_ids} != voisins boardGraph INTER ennemis {enemies_adj}"
    assert len(splash_ids) >= 1, "aucune cible splash (condition non remplie)"

    # === DERIVATION de la cle SPLASH : on DECALE `nrOfHits_2` et le port doit SUIVRE ===
    # `nrOfHits_2` vaut 1, exactement la valeur de repli du lecteur (`ability_var(...) or 1`) : une feuille
    # qui lirait une cle MAL NOMMEE rendrait 1 elle aussi et l'egalite ci-dessus ne la verrait pas (piege
    # " repli de meme valeur ", #96). Le volet MAIN doit rester a `nrOfHits` -> les deux feuilles lisent
    # bien des cles DISTINCTES. Etat NEUF depuis les payloads en cache (aucun RPC, PV et rng d'origine).
    pos_snap = {u: _tile_of(board, state, u) for u in state.entities}
    bumped = cfg_splash + 2
    orig_ability = GC.ability
    patched = dict(orig_ability("PlasmaGrenade") or {})
    patched["constants"] = {**cst, "nrOfHits_2": str(bumped)}
    monkeypatch.setattr(GC, "ability", lambda aid: patched if aid == "PlasmaGrenade" else orig_ability(aid))
    st2 = mkstate()
    for u, tile in pos_snap.items():                        # rejoue le DRIVE de positions a l'identique
        info = board.by_id.get(tile) if tile is not None else None
        pc = st2.get_entity(u).get_component(PositionComponent) if st2.get_entity(u) else None
        if info is not None and pc is not None:
            pc.col, pc.row = info["col"], info["row"]
    diag2 = (_apply_active_ability(st2, caster, target, PLASMA_GRENADE) or {}).get("diag") or {}
    main2 = (diag2.get("main_attack") or {}).get("hits")
    splash2 = sorted({(x.get("attack") or {}).get("hits") for x in (diag2.get("splash") or [])})
    print(f"[PLASMA oracle] nrOfHits_2 {cfg_splash}->{bumped} : splash_hits {splash_hits}->{splash2} "
          f"main_hits={main2} (attendu {cfg_main}, inchange)")
    assert splash2 == [bumped], (
        f"splash hits {splash2} != [{bumped}] : la feuille SPLASH ne DERIVE pas de constants.nrOfHits_2 "
        f"(cle mal nommee retombant sur le repli 1, ou valeur figee)")
    assert main2 == cfg_main, (
        f"main hits {main2} != constants.nrOfHits={cfg_main} apres decalage de nrOfHits_2 : le volet MAIN "
        f"lit la cle du SPLASH")
