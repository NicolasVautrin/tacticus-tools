"""#213 -- `GhostRevive` / `TimeFlux_Revive` (`thousTerminator` << Toth >>), GARDE.

Le SEUL revive NON-IN-PLACE du binaire. i2 : << When Toth moves, he leaves a time ghost behind on
the hex he moved from. If Toth is defeated, he is revived on the hex of the time ghost. >>

Chaine native gardee ici (arbres in extenso : `runner/operations/triggers/loki/ghost_revive.py`) :
  `MoveUnitOperation$$Execute` publie `On(0x1f = PreUnitMove)` AVANT toute mutation de position
  -> `TimeFluxReviveAbility` (= `GhostReviveAbility(1186)`) pose `GhostEffect` sur
     `CurrentTurnStartTile(self)` = `UnitComponent + 0x18c`
  -> Toth meurt AILLEURS : `On(1)` -> `GhostEffect$$CreateTargetTrigger` matche
     (`OnPreDeath(ignoreOverkill=1) & AreEqual(EffectSource, target)`)
  -> `Revive(..., tiles = Owner@0x148)` -> `ReviveData.revivePosition` NON NULLE
  -> garde `!pendingRevive.HasValue` en echec (mort ANNULEE) puis
     `ReviveUnitOperation$$SetRevivePosition` DEPLACE Toth sur la tuile du ghost.

GROUND TRUTH LIVE (`probe_213_ghost_revive.py`, board MC1_67, seed 31337, `--hp-player 12000`) :
  Toth demarre son tour en **(1,2)**, se deplace en **(3,2)**, y encaisse un coup letal
  -> il est **VIVANT en (1,2)** a **3290** PV, et la tuile (1,2) ne porte plus l'effet 1186.
  `3290 == round(TimeFlux.hp[L50] = 1828 x 180 %)`. Le PORT rend EXACTEMENT la meme paire.
  ⚠ Piege de mesure rencontre et neutralise : sans une 2e unite adverse qui garde son action, le
  runner bascule de tour juste apres le revive et la REGEN `TimeFlux` s'ajoute (3290 + 1197 = 4487).

Les tests montent une bataille LIVE (stats/PV/effets REELS) puis DRIVENT positions et etat offline ;
le move passe par `MoveUnitOperation`, la mort par le VRAI chokepoint
`AttackDamageOperation._fire_death_if_killed`. ASCII only ; ADJACENCE = evenq.
"""
from __future__ import annotations

import pytest

from engine.runner.snapshot import load_state
from engine.runner.events import EventBus
from engine.runner.operations.damage import AttackDamageOperation
from engine.runner.operations.movement import MoveUnitOperation
from engine.runner.operations.turnflow import StartTurnOperation
from engine.runner.operations.triggers.loki.ghost_revive import GHOST_EFFECT
from engine.runner.components import (UnitComponent, HealthComponent, StatsComponent,
                                      OwnerComponent, PositionComponent)
from engine.runner.prng import IntBasedMersenneTwister
from engine.entities.effects.magnitude import ability_var

TOTH = "thousTerminator"
BUILD = ["--p-units", "thousTerminator", "--a-units", "astraBullgryn,orksNob",
         "--hp-player", "12000"]


def _state(rpc, rid):
    from engine.entities.pathfinding.board import Board
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")
    dec = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
    tm = rpc("tileMeta", {"runnerId": rid}, 90)
    st = load_state(dec, ob, snap, board=board, tiles=tm)
    st.rng = IntBasedMersenneTwister(12345)
    td = next((u for u in (dec.get("units") or []) if u.get("visualId") == TOTH), None)
    if td is None or st.get_entity(td.get("id")) is None:
        pytest.skip("Toth absent de l'etat capture")
    return st, int(td["id"])


def _start_turn(st, uid):
    """Rejoue le `StartTurnOperation` du camp de `uid` -- seul ecrivain natif de
    `UnitComponent + 0x18c` (la tuile de debut de tour), et de tout le reste du debut de tour.

    Ce n'est PLUS un contournement de capture : depuis `f790ff4` + #230 le champ est capte par
    `combatSnapshot.units[].currentTurnStartTile` et seede par `snapshot._load_unit_turn_state` --
    `test_load_state_turn_state_live.py` garde precisement le premier move SANS cet appel. Il reste
    ici parce que ces scenarios enchainent PLUSIEURS tours : chaque nouveau tour doit reecrire la
    tuile (et purger les flags), ce qu'aucune capture ne peut faire a la place du port."""
    pl = st.get_entity(uid).get_component(OwnerComponent).player
    StartTurnOperation.execute(st, pl)


def _pos(st, uid):
    pc = st.get_entity(uid).get_component(PositionComponent)
    return (pc.col, pc.row)


def _move(st, uid, to):
    """Chemin de PRODUCTION du move cote port : `MovementHandler.visit_MoveUnitMessage` =
    `MoveUnitOperation.execute` (qui emet `On(PreUnitMove)` en tete) PUIS `after_move_triggers`
    (`On(0x24)` / `On(4)` / `On(0x1d)` / `On(0x1c)`). Le natif fait les deux dans le MEME
    `MoveUnitOperation$$Execute` ; le port a scinde en deux foyers -- un test qui n'appellerait que
    l'Operation raterait donc les retraits de ghost branches sur `On(0x24)`."""
    from engine.runner.operations.triggers import after_move_triggers
    MoveUnitOperation(uid, to).execute(st, EventBus())
    after_move_triggers(st, uid)


def _free_neighbour(st, uid, exclude=()):
    """Une tuile voisine LIBRE et walkable de `uid` (le port ne doit jamais dependre du spawn)."""
    board = st.board
    occupied = {_pos(st, e) for e, ent in st.entities.items()
                if ent.get_component(PositionComponent) is not None and e != uid}
    for n in board.neighbours(board.id_at(*_pos(st, uid))):
        if not board.walkable(n):
            continue
        c = board.coord(n)
        p = (int(c[0]), int(c[1]))
        if p in occupied or p in exclude:
            continue
        return p
    return None


def _ghost_tiles(st):
    """Ids des TUILES portant l'effet 1186 ACTIF (non consomme)."""
    if st.effects is None or st.board is None:
        return []
    return sorted(int(t) for t, effs in st.effects.by_unit.items()
                  if int(t) in st.board.by_id
                  and any((not e.consumed) and e.effect_type == GHOST_EFFECT for e in effs))


def _kill(st, uid, killer_id):
    e = st.get_entity(uid)
    hc = e.get_component(HealthComponent)
    hp_before = int(hc.hp)
    hc.hp = 0
    return AttackDamageOperation._fire_death_if_killed(st, uid, killer_id, hp_before, 0, e,
                                                       damage=hp_before) or []


def _expected_revive_hp(st, uid):
    """`Direct(GetVariableForLevel(config, 0x1d='hp', abilityState))`, clampe par `SetHealth`."""
    sc = st.get_entity(uid).get_component(StatsComponent)
    lvl = getattr(sc.ctx, "passive_ability_level", None)
    mult = getattr(sc.ctx, "ability_variables_multiplier", 100)
    hp = int(ability_var("TimeFlux", "hp", lvl, multiplier_pct=mult))
    hc = st.get_entity(uid).get_component(HealthComponent)
    return min(hp, int(hc.hp_max)) if hc.hp_max else hp


def _an_enemy(st, uid):
    toc = st.get_entity(uid).get_component(OwnerComponent)
    for eid, e in sorted(st.entities.items()):
        oc, uc = e.get_component(OwnerComponent), e.get_component(UnitComponent)
        if oc is None or oc.team == toc.team:
            continue
        if uc is not None and uc.alive:
            return eid
    pytest.skip("aucun ennemi vivant")


def test_ghost_revive_moves_toth_back_to_turn_start_tile_live(live_session, rpc, build_runner):
    """FACE POSITIVE, et le SEUL discriminant qui compte : la tuile de MORT et la tuile de REVIVE
    DIFFERENT. Toth demarre son tour en A, bouge en B (B != A), y meurt -> il revient VIVANT **en A**
    a `min(ConfigVar('hp'), maxPV)`, et le ghost est consomme."""
    rid = build_runner("31337", extra=BUILD)["rid"]
    st, tid = _state(rpc, rid)
    _start_turn(st, tid)
    a = _pos(st, tid)
    b = _free_neighbour(st, tid)
    if b is None:
        pytest.skip("aucune tuile voisine libre pour deplacer Toth")
    assert a != b
    _move(st, tid, b)
    assert _pos(st, tid) == b, "le move n'a pas ete applique"
    tile_a = st.board.id_at(*a)
    assert _ghost_tiles(st) == [tile_a], \
        f"le ghost 1186 doit etre pose sur la tuile de DEBUT DE TOUR {a} (tile {tile_a})"

    out = _kill(st, tid, _an_enemy(st, tid))
    e = st.get_entity(tid)
    assert e.get_component(UnitComponent).alive, f"Toth aurait du etre revive (sorties={out})"
    assert _pos(st, tid) == a, \
        f"revive attendu sur la tuile du ghost {a}, obtenu {_pos(st, tid)} (mort en {b})"
    assert int(e.get_component(HealthComponent).hp) == _expected_revive_hp(st, tid)
    assert any("kill_cancelled_by_revive" in r for r in out), \
        f"la garde `!pendingRevive.HasValue` n'a pas annule la mort (sorties={out})"
    assert _ghost_tiles(st) == [], "le ghost devait etre CONSOMME par la resurrection"


def test_ghost_revive_no_move_no_ghost_live(live_session, rpc, build_runner):
    """FACE NEGATIVE 1 : sans MOVE, aucun `On(PreUnitMove)` -> aucun ghost -> Toth reste MORT.
    C'est le discriminant du VECTEUR : le port ne doit pas ressusciter << par defaut >>."""
    rid = build_runner("31337", extra=BUILD)["rid"]
    st, tid = _state(rpc, rid)
    _start_turn(st, tid)
    assert _ghost_tiles(st) == [], "aucun ghost ne doit exister avant le premier move"
    out = _kill(st, tid, _an_enemy(st, tid))
    assert not st.get_entity(tid).get_component(UnitComponent).alive, \
        f"Toth revive sans avoir bouge (sorties={out})"


def test_ghost_revive_is_once_per_battle_live(live_session, rpc, build_runner):
    """FACE NEGATIVE 2 -- `NOT HasBeenRevivedByAbility(self, 1186)` : le set
    `ActorStatisticsComponent+0xe0` (alimente par `ReviveUnitOperation`, JAMAIS remis a zero)
    interdit un SECOND ghost-revive dans la meme bataille. On rejoue tout le cycle : Toth revive,
    puis rebouge (le gate refuse de reposer un ghost), puis remeurt -> MORT."""
    rid = build_runner("31337", extra=BUILD)["rid"]
    st, tid = _state(rpc, rid)
    _start_turn(st, tid)
    a = _pos(st, tid)
    b = _free_neighbour(st, tid)
    if b is None:
        pytest.skip("aucune tuile voisine libre")
    _move(st, tid, b)
    foe = _an_enemy(st, tid)
    _kill(st, tid, foe)
    uc = st.get_entity(tid).get_component(UnitComponent)
    assert uc.alive and _pos(st, tid) == a, "le 1er revive doit avoir eu lieu (pre-condition)"
    assert GHOST_EFFECT in uc.revived_by_abilities, \
        "`ReviveUnitOperation` doit enregistrer 1186 dans `revived_by_abilities`"
    # 2e cycle : nouveau tour, nouveau move -> le gate `HasBeenRevivedByAbility` doit REFUSER la pose
    _start_turn(st, tid)
    b2 = _free_neighbour(st, tid)
    if b2 is None:
        pytest.skip("aucune tuile voisine libre pour le 2e move")
    _move(st, tid, b2)
    assert _ghost_tiles(st) == [], \
        "un 2e ghost a ete pose alors que Toth a DEJA ete ressuscite par 1186"
    out = _kill(st, tid, foe)
    assert not st.get_entity(tid).get_component(UnitComponent).alive, \
        f"Toth a ete ressuscite DEUX fois par le meme ghost (sorties={out})"


def test_ghost_vanishes_when_another_unit_enters_the_tile_live(live_session, rpc, build_runner):
    """FACE NEGATIVE 3 -- retrait n°3 du `CreateHandleTriggerAbilitiesInternal` :
    `On(0x24 = UnitPositionChanged_1) & NOT AreEqual(caster, EffectSource) & Contains(TargetTiles,
    Owner)`. Une AUTRE unite qui marche sur la tuile du ghost le dissipe -> Toth meurt pour de bon.
    C'est le << the time ghost vanishes if the hex becomes occupied by another unit >> de l'i2."""
    rid = build_runner("31337", extra=BUILD)["rid"]
    st, tid = _state(rpc, rid)
    _start_turn(st, tid)
    a = _pos(st, tid)
    b = _free_neighbour(st, tid)
    if b is None:
        pytest.skip("aucune tuile voisine libre")
    _move(st, tid, b)
    tile_a = st.board.id_at(*a)
    assert _ghost_tiles(st) == [tile_a], "pre-condition : le ghost est pose"
    # une AUTRE unite marche sur A (position DRIVEE : on l'y amene par le vrai `MoveUnitOperation`)
    foe = _an_enemy(st, tid)
    _move(st, foe, a)
    assert _ghost_tiles(st) == [], \
        "le ghost devait etre dissipe par l'arrivee d'une autre unite sur sa tuile"
    out = _kill(st, tid, foe)
    assert not st.get_entity(tid).get_component(UnitComponent).alive, \
        f"Toth revive alors que son ghost avait ete dissipe (sorties={out})"


def test_ghost_moves_with_toth_second_move_live(live_session, rpc, build_runner):
    """Retrait n°1 : `On(0x1f) & AreEqual(caster, EffectSource)` -- quand le POSEUR rebouge, l'ancien
    ghost part. Le registre etant SNAPSHOTE en tete de dispatch (mirror du snapshot+`Queue.Clear`
    natif), le ghost POSE pendant ce meme dispatch n'est pas retire : apres deux moves consecutifs il
    reste EXACTEMENT un ghost, sur la tuile de debut de tour du tour COURANT."""
    rid = build_runner("31337", extra=BUILD)["rid"]
    st, tid = _state(rpc, rid)
    _start_turn(st, tid)
    a = _pos(st, tid)
    b = _free_neighbour(st, tid)
    if b is None:
        pytest.skip("aucune tuile voisine libre")
    _move(st, tid, b)
    assert _ghost_tiles(st) == [st.board.id_at(*a)]
    # nouveau TOUR : la tuile de debut de tour devient B, un 2e move doit deplacer le ghost sur B
    _start_turn(st, tid)
    c = _free_neighbour(st, tid, exclude=(a,))
    if c is None:
        pytest.skip("aucune 2e tuile voisine libre")
    _move(st, tid, c)
    assert _ghost_tiles(st) == [st.board.id_at(*b)], \
        "apres le 2e move le ghost doit etre sur B (tuile de debut du tour courant), et UN SEUL"
