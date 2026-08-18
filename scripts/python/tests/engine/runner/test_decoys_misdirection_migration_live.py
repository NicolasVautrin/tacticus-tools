"""Gen-stealer G2 : DecoysAndMisdirection (passif Isaak genesPrimus) MIGRATION -> triggers step-on-decoy.

Passif natif = DEUX abilities-triggers (split par faction, PAS par event) :
  - `DamageEnemies` (IdunBattleLogic.Entities.Abilities.Triggered.Loki.DecoysAndMisdirection_DamageEnemiesAbility$$CreateTrigger, behaviour IdunBattleLogic.Entities.Abilities.Triggered.Loki.DecoysAndMisdirection_DamageEnemiesAbility$$CreateBehaviour) : `On(0x1d=UnitPositionChanged_2) &
    AreEnemies(owner, actor) & AmountIsGreaterThanZero(GetValidDeadDecoys)` -> `Repeat(AttackWithAbilityDamage(
    owner, stepper, MinMaxDamage, Blast, hits=1), Count(dead decoys))`. Feuille = `AttackBehaviour(
    AbilityDamageBehaviour)` (decompile IdunBattleLogic.Entities.Abilities.Triggered.Loki.DecoysAndMisdirection_DamageEnemiesAbility$$CreateBehaviour + factory :
    l'enveloppe `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAbilityDamage(damageProfile:System.Nullable<IdunBattle.Entities.Enum.DamageProfileType>, hits:System.Int32)`
    -> le COEUR `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAbilityDamage(abilityOrEffect, options:IdunBattle.Entities.Behaviours.AbilityDamageBehaviourOptions)`,
    tranchee par la XREF entrante ; #1032-r5, cette ligne disait `X->X`. VERIFIES : pipeline
    crit/block COMPLET) -> leaf port `AttackWithAttackDamage` (execute_ability_attack).
  - `BuffFriends` (IdunBattleLogic.Entities.Abilities.Triggered.Loki.DecoysAndMisdirection_BuffFriendsAbility$$CreateTrigger, behaviour IdunBattleLogic.Entities.Abilities.Triggered.Loki.DecoysAndMisdirection_BuffFriendsAbility$$CreateBehaviour) : `(On(0x2e = UnitResurrected)|On(0x1d)) & AreFriends(owner,
    actor) & ...` -> `AddEffect(1379 +582, on=stepper)` + `If(HasFaction(stepper, GenestealerCults),
    spawn_decoy(hex adjacent libre))`.
Vecteur = `dispatch.after_move_triggers` emet On(4) PUIS On(0x1d) (mirror IdunBattle.Operations.MoveUnitOperation$$EvaluateAfterMoveTriggers).
Le decoy est crushe INLINE (`_kill_steppable_units`, G1) AVANT -> GetValidDeadDecoys le lit deja mort.

⚠ ORACLE : une confrontation live du MONTANT natif du Blast est ENTANGLED (verifie live 2026-07-18) -- la seule
source live de decoy (CultDemagogue G4) voit ses decoys CONSOMMES par les tours AI immediats des Neophytes
(0 decoy vivant post-cast) -> pas de decoy stable a driver un ennemi dessus. On valide donc le WIRING G2
DETERMINISTIQUEMENT sur un ETAT LIVE REEL (units/teams/factions/board/positions capturés live) : on pose un
decoy ami via le `spawn_decoy` G1 (live-valide) a cote d'une unite reelle, on REJOUE le step-on (MoveUnitOperation
+ after_move_triggers = code natif-mirror), et on asserte que le bon trigger fire (crush + Blast sur l'ENNEMI /
effet 1379 + nouveau decoy sur l'ALLIE GS). Le MONTANT du Blast vient du pipeline execute_ability_attack deja
live-valide (Stikkbomb/Fragstorm/Plasma). ASCII-only. Skip si pas de session / geometrie infaisable.
"""
from __future__ import annotations

import pytest

import hexgeo

BUILD = ["--p-units", "genesPrimus", "--a-units", "necroDestroyer,necroWarden,eldarRanger"]
CASTER_VIS = "genesPrimus"
DECOYS_EXTRA_DMG = 1379


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


def _find_enemy(state, my_team):
    from engine.runner.components import UnitComponent, OwnerComponent
    for uid, e in state.entities.items():
        uc = e.get_component(UnitComponent)
        oc = e.get_component(OwnerComponent)
        if uc is None or oc is None or not uc.alive:
            continue
        if oc.team != my_team:
            return uid
    return None


def _pos(state, uid):
    from engine.runner.components import PositionComponent
    e = state.get_entity(uid)
    pc = e.get_component(PositionComponent) if e is not None else None
    return (pc.col, pc.row) if pc is not None else None


def _hp(state, uid):
    from engine.runner.components import HealthComponent
    e = state.get_entity(uid)
    hc = e.get_component(HealthComponent) if e is not None else None
    return hc.hp if hc is not None else None


def _free_tile_near(state, board, uid, max_radius=6):
    """La tuile LIBRE marchable la plus PROCHE de `uid` (rayon hex croissant) -> (tile_id, (col,row)). None si
    aucune dans `max_radius`. Le step-on rejoué est une MoveUnitOperation (non range-gated) -> la distance ne
    change pas le trigger, mais on prend la plus proche pour un scénario réaliste."""
    from engine.runner.components import PositionComponent, UnitComponent
    pos = _pos(state, uid)
    if pos is None:
        return None
    occ = set()
    for e in state.entities.values():
        pc = e.get_component(PositionComponent)
        uc = e.get_component(UnitComponent)
        if pc is None or (uc is not None and not uc.alive):
            continue
        occ.add((pc.col, pc.row))
    seen = set()
    for radius in range(1, int(max_radius) + 1):
        for (c, r) in sorted(hexgeo.disk(pos[0], pos[1], radius)):
            if (c, r) in seen:
                continue
            seen.add((c, r))
            if (c, r) == pos or (c, r) in occ:
                continue
            t = board.id_at(c, r)
            if t is None or not board.walkable(t):
                continue
            return (t, (c, r))
    return None


@pytest.fixture(scope="session")
def g2_state(rpc, build_runner):
    """Etat LIVE reel (Isaak genesPrimus + ennemis) chargé offline : units/teams/factions/board/positions live."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    from engine.runner.prng import IntBasedMersenneTwister

    rid = build_runner("777", extra=BUILD)["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")
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
    return {"build_state": build_state, "board": board}


def test_g2_enemy_step_blast(g2_state):
    """Path ENNEMI : un decoy AMI (posé via spawn_decoy G1) est écrasé par un ENNEMI qui move dessus ->
    `DamageEnemies` fire un Blast sur le stepper (crush + dégâts). On(0x1d), AreEnemies(Isaak, stepper)."""
    from engine.runner.operations.spawn import spawn_decoy
    from engine.runner.operations.movement import MoveUnitOperation
    from engine.runner.operations.triggers.dispatch.move_death import after_move_triggers
    from engine.runner.events import EventBus
    from engine.runner.components import UnitComponent
    state = g2_state["build_state"]()
    board = g2_state["board"]
    isaak = _find_by_vis(state, CASTER_VIS)
    if isaak is None:
        pytest.skip("Isaak absent")
    enemy = _find_enemy(state, _team(state, isaak))
    if enemy is None:
        pytest.skip("pas d'ennemi vivant")
    adj = _free_tile_near(state, board, enemy)
    if adj is None:
        pytest.skip("pas de tuile libre adjacente a l'ennemi")
    tile_id, tile_coord = adj
    decoy_id = spawn_decoy(state, tile_id, isaak)          # decoy AMI d'Isaak (owner = team+player Isaak)
    assert decoy_id is not None
    hp0 = _hp(state, enemy)
    # rejoue le step-on : crush (G1) INLINE puis after_move_triggers -> On(0x1d) -> DamageEnemies
    MoveUnitOperation(enemy, tile_coord).execute(state, EventBus())
    res = after_move_triggers(state, enemy)
    dc = state.get_entity(decoy_id).get_component(UnitComponent)
    assert dc is not None and not dc.alive, "le decoy ami n'a pas ete crushe par le step-on ennemi"
    blast = [r for r in res if r.get("ability") == "DecoysAndMisdirection_DamageEnemies"]
    assert blast and int(blast[0].get("count") or 0) >= 1, \
        "DamageEnemies n'a pas fire de Blast sur le stepper ennemi"
    hp1 = _hp(state, enemy)
    assert hp0 is not None and hp1 is not None and hp1 < hp0, \
        f"le stepper ennemi n'a pas subi le Blast (hp {hp0} -> {hp1})"


def test_g2_friendly_step_buff_and_decoy(g2_state):
    """Path ALLIE : un decoy AMI écrasé par un ALLIE GS Cult (Isaak) qui move dessus -> `BuffFriends` pose
    l'effet 1379 (+582) sur le stepper ET (faction GS) spawn un NOUVEAU decoy adjacent. On(0x1d),
    AreFriends(Isaak, stepper)."""
    from engine.runner.operations.spawn import spawn_decoy
    from engine.runner.operations.movement import MoveUnitOperation
    from engine.runner.operations.triggers.dispatch.move_death import after_move_triggers
    from engine.runner.events import EventBus
    from engine.runner.components import UnitComponent
    state = g2_state["build_state"]()
    board = g2_state["board"]
    isaak = _find_by_vis(state, CASTER_VIS)
    if isaak is None:
        pytest.skip("Isaak absent")
    adj = _free_tile_near(state, board, isaak)
    if adj is None:
        pytest.skip("pas de tuile libre adjacente a Isaak")
    tile_id, tile_coord = adj
    decoy_id = spawn_decoy(state, tile_id, isaak)          # decoy AMI (meme team qu'Isaak)
    assert decoy_id is not None
    if state.effects is None:
        pytest.skip("pas d'EffectsState (combatSnapshot)")
    MoveUnitOperation(isaak, tile_coord).execute(state, EventBus())
    res = after_move_triggers(state, isaak)
    dc = state.get_entity(decoy_id).get_component(UnitComponent)
    assert dc is not None and not dc.alive, "le decoy ami n'a pas ete crushe par le step-on allie"
    buff = [r for r in res if r.get("ability") == "DecoysAndMisdirection_BuffFriends"]
    assert buff, "BuffFriends n'a pas fire pour l'allie qui marche sur un decoy ami"
    assert state.effects.has_effect(isaak, effect_type=DECOYS_EXTRA_DMG), \
        "l'effet 1379 (+582 extraDmg) n'a pas ete pose sur le stepper allie"
    # Isaak est Genestealer Cults -> HasFaction gate TRUE -> un NOUVEAU decoy est spawn dans un hex adjacent
    assert buff[0].get("spawned_decoy") is not None, \
        "aucun nouveau decoy spawn (gate faction GS Cult)"


def test_g2_no_trigger_without_dead_decoy(g2_state):
    """GARDE : un move ordinaire (sans decoy ami crushé) ne déclenche NI DamageEnemies NI BuffFriends
    (`AmountIsGreaterThanZero(GetValidDeadDecoys)` = 0). Confirme que le vecteur On(0x1d) ne sur-fire pas."""
    from engine.runner.operations.movement import MoveUnitOperation
    from engine.runner.operations.triggers.dispatch.move_death import after_move_triggers
    from engine.runner.events import EventBus
    state = g2_state["build_state"]()
    board = g2_state["board"]
    isaak = _find_by_vis(state, CASTER_VIS)
    if isaak is None:
        pytest.skip("Isaak absent")
    enemy = _find_enemy(state, _team(state, isaak))
    if enemy is None:
        pytest.skip("pas d'ennemi vivant")
    adj = _free_tile_near(state, board, enemy)          # tuile libre SANS decoy
    if adj is None:
        pytest.skip("pas de tuile libre adjacente")
    _tile_id, tile_coord = adj
    MoveUnitOperation(enemy, tile_coord).execute(state, EventBus())
    res = after_move_triggers(state, enemy)
    dm = [r for r in res if r.get("ability", "").startswith("DecoysAndMisdirection")]
    assert not dm, f"DecoysAndMisdirection a fire sans decoy mort valide : {dm}"
