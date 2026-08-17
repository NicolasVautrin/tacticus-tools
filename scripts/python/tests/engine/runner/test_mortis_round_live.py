"""case-220 UM : MortisRound (actif 1004, ultraEliminatorSgt « Eliminator Sergeant ») PORT -> arbre DSL,
WIRING valide LIVE.

`MortisRoundAbility$$IdunBattleLogic.Entities.Abilities.Active.Loki.MortisRoundAbility$$ExecuteBehaviour` (callback `<ExecuteBehaviour>b__0 IdunBattleLogic.Entities.Abilities.Active.Loki.MortisRoundAbility.u003Cu003Ec__DisplayClass1_0$$u003CExecuteBehaviouru003Eb__0`, MIRROR
1:1) = `AtomicGroup(0x3f, callback)` ou le callback `AActiveAbility.Execute(attack)` PUIS `Execute(push)` :
    attack = AttackWithAttackDamage(caster@0x160, target@0x178, MinMaxDamage(minDmg 0xc/maxDmg 0xd),
             GetDamageProfile=HeavyRound, hitsNode, AbilityOrEffect(*this+0x10=1004))   # 1x HeavyRound ranged
    push   = PushUnit(caster@0x160, target@0x178)                                       # recul 1 hex

Port = `mortis_round_tree` (ultramarines.py) : `AtomicGroup(op_and(AttackWithAttackDamage(Target(),
"MortisRound","HeavyRound",ranged), PushUnit(Caster(),Target())))`. Overload attaque = IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage (famille
ATTACK, resolu par XREF du call-site IdunBattleLogic.Entities.Abilities.Active.Loki.MortisRoundAbility$$ExecuteBehaviour+0x1e3). i2 : « Deals 1x 3274-3638 Heavy Round Damage to a single
target within range 3, which is then pushed back 1 hex. »

VALIDATION (deterministe-sur-etat-live, board+stats REELS, drive-positions) :
  (1) PUSH : caster+cible ADJACENTS (tuile libre derriere, oppose caster) -> la cible recule d'1 hex a
      l'oppose du caster (`DisplaceUnitOperation`) ;
  (2) ATTAQUE mono-cible 1 coup : la cible est degatee, un 2e ennemi voisin N'EST PAS touche ;
  (3) DISCRIMINANT geometrie : deux positions caster distinctes -> deux tuiles de push distinctes (le push
      suit la direction caster->cible, PAS une constante).

RESIDU documente (PAS teste ici) : le trait HeavyWeapon du carrier DOUBLE le bonus +heavyWeaponExtraDmg%
(`TriggeringAbilityIs(0x3ec=1004)` IdunBattle.Entities.Effects.Loki.HeavyWeapon_ExtraDmgEffect$$CreateDamageModifier) ; le port ne l'applique PAS aux attaques d'ability (is_ranged
non threade dans execute_ability_attack : blast radius ArmoriumCherub/SpiritLeech/PlasmaCannon). => la
MAGNITUDE du degat est residuelle (cross-cutting, candidat) ; seul le WIRING attaque+push est asserte.
ASCII-only. Skip si pas de session / Eliminator non buildable / geometrie infaisable.
"""
from __future__ import annotations

import pytest

import hexgeo

BUILD = ["--roster", "1", "--p-units", "ultraEliminatorSgt",
         "--a-units", "necroWarden,necroDestroyer", "--hp-target", "80000"]
CASTER_VIS = "ultraEliminatorSgt"
ABILITY = 1004


def _find_by_vis(state, vis):
    from engine.runner.components import UnitComponent
    for uid, e in state.entities.items():
        uc = e.get_component(UnitComponent)
        if uc is not None and uc.alive and uc.visual_id == vis:
            return uid
    return None


def _team(state, uid):
    from engine.runner.components import OwnerComponent
    e = state.get_entity(uid)
    oc = e.get_component(OwnerComponent) if e is not None else None
    return oc.team if oc is not None else None


def _enemies_of(state, uid):
    from engine.runner.components import UnitComponent, OwnerComponent
    mine = _team(state, uid)
    out = []
    for oid, e in state.entities.items():
        uc = e.get_component(UnitComponent)
        oc = e.get_component(OwnerComponent)
        if uc is None or oc is None or not uc.alive or oc.team == mine:
            continue
        out.append(oid)
    return out


def _pos(state, uid):
    from engine.runner.components import PositionComponent
    e = state.get_entity(uid)
    pc = e.get_component(PositionComponent) if e is not None else None
    return (pc.col, pc.row) if pc is not None else None


def _set_pos(state, uid, col, row):
    from engine.runner.components import PositionComponent
    e = state.get_entity(uid)
    pc = e.get_component(PositionComponent) if e is not None else None
    if pc is not None:
        pc.col, pc.row = int(col), int(row)


def _hp(state, uid):
    from engine.runner.components import HealthComponent
    e = state.get_entity(uid)
    hc = e.get_component(HealthComponent) if e is not None else None
    return hc.hp if hc is not None else None


def _open_triple(board):
    """(C caster, T cible adjacente, B derriere-oppose) : C voisin de T, B = tuile derriere T (oppose C)
    via la geometrie du push (`_dir_index`/`_step`), les 3 walkable et distincts."""
    from engine.runner.operations.displace import _dir_index, _step
    for T in sorted(board.by_id):
        if not board.walkable(T):
            continue
        for C in board.neighbours(T):
            if not board.walkable(C) or C == T:
                continue
            cc, tc = board.coord(C), board.coord(T)
            di = _dir_index(cc[0], cc[1], tc[0], tc[1])
            if di is None:
                continue
            bcol, brow = _step(tc[0], tc[1], di)
            B = board.id_at(bcol, brow)
            if B is None or B in (T, C) or not board.walkable(B):
                continue
            return board.coord(C), board.coord(T), board.coord(B)
    return None


def _park_far(state, board, keep_ids, center):
    from engine.runner.components import UnitComponent
    used = set()
    far = [t for t in board.by_id
           if board.walkable(t) and hexgeo.distance(board.coord(t), center) > 4]
    far.sort()
    it = iter(far)
    for uid, e in state.entities.items():
        uc = e.get_component(UnitComponent)
        if uid in keep_ids or uc is None or not uc.alive:
            continue
        for t in it:
            if t not in used:
                used.add(t)
                _set_pos(state, uid, *board.coord(t))
                break


@pytest.fixture(scope="session")
def mr_state(rpc, build_runner):
    """Etat LIVE reel (Eliminator + necrons) charge offline, rng seede, rejouable a volonte."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    from engine.runner.prng import IntBasedMersenneTwister

    rid = build_runner("909", extra=BUILD)["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="native_sym")
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    rng0 = rpc("dumpRng", {"runnerId": rid}, 30)

    def build_state():
        st = load_state(dv, ob, snap, board=board)
        if isinstance(rng0, dict) and rng0.get("mt"):
            r = IntBasedMersenneTwister()
            r.mt = list(rng0["mt"]); r.mti = rng0["mti"]
            st.rng = r
        return st

    if _find_by_vis(build_state(), CASTER_VIS) is None:
        pytest.skip("Eliminator (ultraEliminatorSgt) absent du build (non spawnable ?)")
    return {"build_state": build_state, "board": board}


def test_mortis_push_and_single_target(mr_state):
    """(1) PUSH : la cible recule d'1 hex a l'oppose du caster (tuile geometrique predite) ;
    (2) ATTAQUE mono-cible 1 coup : la cible est degatee, un 2e ennemi voisin de la cible N'EST PAS touche."""
    from engine.runner.abilities.ultramarines import MortisRoundAbility
    state = mr_state["build_state"]()
    board = mr_state["board"]
    caster = _find_by_vis(state, CASTER_VIS)
    enemies = _enemies_of(state, caster)
    if caster is None or len(enemies) < 1:
        pytest.skip("Eliminator + 1 ennemi requis")
    tri = _open_triple(board)
    if tri is None:
        pytest.skip("aucun triplet (caster, cible adjacente, derriere) ouvert")
    cc, tc, bc = tri
    target = enemies[0]
    e2 = enemies[1] if len(enemies) > 1 else None
    # e2 sur un VOISIN de la cible distinct de la tuile de push (garde mono-cible)
    e2_coord = None
    if e2 is not None:
        ttile = board.id_at(*tc)
        for n in board.neighbours(ttile):
            nc = board.coord(n)
            if board.walkable(n) and nc != cc and nc != bc:
                e2_coord = nc
                break
    keep = {caster, target} | ({e2} if e2 is not None else set())
    _park_far(state, board, keep, tc)
    _set_pos(state, target, *tc)
    _set_pos(state, caster, *cc)
    if e2 is not None and e2_coord is not None:
        _set_pos(state, e2, *e2_coord)
    assert hexgeo.distance(cc, tc) == 1, "setup: caster adjacent a la cible"

    hp_t0 = _hp(state, target)
    hp_e2_0 = _hp(state, e2) if e2 is not None else None
    res = MortisRoundAbility().execute_behaviour(state, caster, target)
    assert res is not None and res.get("dsl") is True, f"port non execute: {res}"
    # (1) PUSH geometrique : cible poussee derriere (oppose caster)
    assert _pos(state, target) == bc, \
        f"cible pas poussee sur la tuile geometrique {bc} (pos={_pos(state, target)}, push={res.get('push')})"
    # (2) ATTAQUE : 1 coup, cible degatee
    main = res.get("main_attack") or {}
    per_hit = main.get("per_hit") or []
    assert len(per_hit) == 1, f"attaque {len(per_hit)} coups != 1 (i2 « 1x »)"
    assert _hp(state, target) < hp_t0, f"cible pas endommagee (hp {hp_t0} -> {_hp(state, target)})"
    # (2bis) mono-cible : e2 voisin non touche
    if e2 is not None and e2_coord is not None and hp_e2_0 is not None:
        assert _hp(state, e2) == hp_e2_0, \
            f"e2 voisin endommage (hp {hp_e2_0} -> {_hp(state, e2)}) -- MortisRound est mono-cible"


def test_mortis_push_direction_opposite_caster(mr_state):
    """DISCRIMINANT geometrie : deux positions caster autour de la MEME cible -> deux tuiles de push
    DISTINCTES, chacune a l'oppose du caster (le push suit la direction caster->cible, pas une constante)."""
    from engine.runner.abilities.ultramarines import MortisRoundAbility
    from engine.runner.operations.displace import _dir_index, _step
    board = mr_state["board"]

    # trouve T avec DEUX voisins C1,C2 opposes ayant chacun une tuile-derriere libre
    def _cfg():
        for T in sorted(board.by_id):
            if not board.walkable(T):
                continue
            tc = board.coord(T)
            opts = []
            for C in board.neighbours(T):
                cc = board.coord(C)
                if not board.walkable(C):
                    continue
                di = _dir_index(cc[0], cc[1], tc[0], tc[1])
                if di is None:
                    continue
                b = board.id_at(*_step(tc[0], tc[1], di))
                if b is None or b == T or b == C or not board.walkable(b):
                    continue
                opts.append((cc, board.coord(b)))
            if len(opts) >= 2 and opts[0][1] != opts[1][1]:
                return tc, opts[0], opts[1]
        return None
    cfg = _cfg()
    if cfg is None:
        pytest.skip("pas de cible avec 2 directions de push distinctes")
    tc, (cc1, bc1), (cc2, bc2) = cfg

    results = []
    for cc, bc in ((cc1, bc1), (cc2, bc2)):
        state = mr_state["build_state"]()
        caster = _find_by_vis(state, CASTER_VIS)
        enemies = _enemies_of(state, caster)
        if caster is None or not enemies:
            pytest.skip("Eliminator + 1 ennemi requis")
        target = enemies[0]
        _park_far(state, board, {caster, target}, tc)
        _set_pos(state, target, *tc)
        _set_pos(state, caster, *cc)
        MortisRoundAbility().execute_behaviour(state, caster, target)
        results.append((cc, _pos(state, target), bc))

    (cA, pA, bA), (cB, pB, bB) = results
    assert pA == bA, f"push depuis {cA}: cible -> {pA} != oppose attendu {bA}"
    assert pB == bB, f"push depuis {cB}: cible -> {pB} != oppose attendu {bB}"
    assert pA != pB, f"push identique {pA} depuis deux positions caster distinctes {cA}/{cB} (pas directionnel)"
