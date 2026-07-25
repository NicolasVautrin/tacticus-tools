"""Gen-stealer G6b : passif HypersensoryAbilities (Judh genesKelermorph) MoveAndSpawnDecoy + contre-attaque.

i2 : « ... After the attack [1re du tour ennemi], she moves to a free adjacent hex and places a decoy on the
hex she moved from. Then, if she is within 2 hexes of the unit that attacked her, she deals 3x <MinMax>
Projectile Damage to that unit. » Artefacts natifs (RE re-expert #16) :
  - IdunBattleLogic.Entities.Abilities.Triggered.Loki.HypersensoryAbilitiesAbility_MoveAndSpawnDecoy$$CreateTrigger : `On(9=Attack) BRUT & OwnerOrOwnerTileIsTarget & IsEnemyTurn
      & Not(HasEffect 0x57f=1407) & Not(HasBeenAttackedAmountThisTurn >= 2)`.
  - IdunBattleLogic.Entities.Abilities.Triggered.Loki.HypersensoryAbilitiesAbility_MoveAndSpawnDecoy$$CreateBehaviour : move (GetTilePriority) -> decoy sur PreviousTile -> contre-attaque
      (gate IsInRange(range=2) & IsAlive x2 & Not(IsObscured)) -> AddEffect(1407) EN DERNIER.
  - IdunBattleLogic.Entities.Abilities.Triggered.Loki.HypersensoryAbilitiesAbility_MoveAndSpawnDecoy$$GetTilePriority : prio 0 si dist(tile,attaquant)==range & Not(IsObscured) ; 1 si adjacent ; 2.
  - `On(9)` emis par FinishAttackOperation IdunBattle.Operations.FinishAttackOperation$$Execute pour TOUTE attaque (normale ET ability) -> Judh
      reagit a n'importe quelle attaque la ciblant (after_hit_normal_attack l'emet desormais).
config : Projectile pierce 15, range=2, nrOfHits=3, unitToSpawn=genesSmnDecoy, dmg 1455-2183@L65.

VALIDATION : deterministe-sur-etat-live (comme G2..G6a). BUILD un runner (Judh + ennemi), capture l'etat
LIVE, charge offline, DRIVE les positions, et asserte le WIRING du port :
  (A) le passif enregistre le trigger MoveAndSpawnDecoy sur Judh (collect_triggered_abilities) ;
  (B) reaction a la 1re attaque du tour ennemi : Judh MOVE vers une tuile adjacente libre + DECOY sur la
      tuile QUITTEE + flag 1407 pose ;
  (C) contre-attaque : attaquant a <= range hex -> il encaisse 3x Projectile (PV baissent) ;
  (D) once/turn : 2e attaque du meme tour -> AUCUNE reaction (flag 1407 + compteur>=2) ; reset au start_turn
      efface le flag -> Judh se re-arme ;
  (E) integration : `after_hit_normal_attack` emet On(9) -> le trigger fire (bout-en-bout depuis le vecteur
      d'attaque normale).
ASCII-only. Skip si pas de session / Judh non buildable.
"""
from __future__ import annotations

import pytest

JUDH_VIS = "genesKelermorph"
ENEMY_VIS = "necroWarden"
BUILD = ["--p-units", "genesKelermorph", "--a-units", "necroWarden"]
FLAG_1407 = "HypersensoryAbilities_HasBeenAttacked"


# ------------------------------------------------------------------ helpers etat

def _find_by_vis(state, vis, alive_only=True):
    from engine.runner.components import UnitComponent
    for uid, e in state.entities.items():
        uc = e.get_component(UnitComponent)
        if uc is not None and uc.visual_id == vis and (uc.alive or not alive_only):
            return uid
    return None


def _uc(state, uid):
    from engine.runner.components import UnitComponent
    e = state.get_entity(uid)
    return e.get_component(UnitComponent) if e is not None else None


def _hc(state, uid):
    from engine.runner.components import HealthComponent
    e = state.get_entity(uid)
    return e.get_component(HealthComponent) if e is not None else None


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


def _has_flag_1407(state, uid):
    return state.effects is not None and state.effects.has_effect(
        uid, name=FLAG_1407)


def _place_adjacent(state, board, judh, enemy):
    """Place l'ennemi ADJACENT a Judh (dist hex 1) sur une tuile marchable, en s'assurant qu'il reste des
    tuiles adjacentes LIBRES a Judh (pour le move) et une tuile a dist 2 de l'ennemi. Renvoie True si OK."""
    import hexgeo
    jpos = _pos(state, judh)
    if jpos is None:
        return False
    # tuile marchable adjacente a Judh, differente des positions occupees, pour l'ennemi
    occ = {p for p in (_pos(state, u) for u in state.entities) if p is not None} - {jpos}
    for (c, r) in hexgeo.disk(jpos[0], jpos[1], 1):
        if (c, r) == jpos or (c, r) in occ:
            continue
        t = board.id_at(c, r)
        if t is None or not board.walkable(t):
            continue
        _set_pos(state, enemy, c, r)
        return True
    return False


# ------------------------------------------------------------------ fixture

@pytest.fixture(scope="session")
def g6b_state(rpc, build_runner):
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

    probe = build_state()
    judh = _find_by_vis(probe, JUDH_VIS)
    enemy = _find_by_vis(probe, ENEMY_VIS)
    if judh is None or enemy is None:
        pytest.skip("Judh (genesKelermorph) et/ou ennemi (necroWarden) absents du build")
    return {"build_state": build_state, "board": board}


def _je(state):
    return _find_by_vis(state, JUDH_VIS), _find_by_vis(state, ENEMY_VIS)


# ------------------------------------------------------------------ tests

def test_g6b_passive_registers_trigger(g6b_state):
    """(A) Le passif HypersensoryAbilities enregistre le trigger MoveAndSpawnDecoy sur Judh (voie
    passiveAbilities du registre AbilityAndEffectCache)."""
    from engine.runner.operations.triggers.dispatch import collect_triggered_abilities
    from engine.runner.operations.triggers.genestealer import HypersensoryMoveAndSpawnDecoyAbility
    state = g6b_state["build_state"]()
    judh, _ = _je(state)
    trigs = collect_triggered_abilities(state)
    mine = [t for t in trigs
            if isinstance(t, HypersensoryMoveAndSpawnDecoyAbility) and t.owner_id == judh]
    assert len(mine) == 1, "Judh doit porter exactement 1 trigger MoveAndSpawnDecoy"
    assert mine[0].event_id == 9, "le trigger ecoute On(9=Attack)"


def test_g6b_reaction_move_decoy_flag(g6b_state):
    """(B) 1re attaque du tour ennemi : Judh MOVE vers une tuile adjacente libre + DECOY sur la tuile QUITTEE
    + flag 1407 pose. On drive : ennemi adjacent, compteur Judh=1 (post-1re-attaque), puis On(9)."""
    from engine.runner.operations.triggers.dispatch import evaluate_trigger_operation
    from engine.runner.operations.triggers.base import TriggerEvent
    from engine.dsl.event_trigger_type import EventTriggerType
    from engine.runner.components import UnitComponent
    state = g6b_state["build_state"]()
    board = g6b_state["board"]
    judh, enemy = _je(state)
    if not _place_adjacent(state, board, judh, enemy):
        pytest.skip("pas de tuile adjacente libre pour placer l'ennemi")
    jpos0 = _pos(state, judh)
    n_units0 = len(state.entities)
    # post-1re-attaque : compteur = 1 (record_attacked l'a incremente avant On(9))
    _uc(state, judh).times_attacked_this_turn = 1
    assert not _has_flag_1407(state, judh)

    ev = TriggerEvent(EventTriggerType.Attack, enemy, judh, ranged=False, profile=None, is_crit=False)
    res = evaluate_trigger_operation(state, ev)

    jpos1 = _pos(state, judh)
    assert jpos1 != jpos0, f"Judh doit avoir bouge (de {jpos0}) ; res={res}"
    # decoy spawn sur la tuile QUITTEE
    from engine.runner.components import PositionComponent
    decoy_here = [uid for uid, e in state.entities.items()
                  if (pc := e.get_component(PositionComponent)) is not None
                  and (pc.col, pc.row) == jpos0
                  and (u := e.get_component(UnitComponent)) is not None and u.visual_id == "genesSmnDecoy"]
    assert len(decoy_here) == 1, f"un decoy genesSmnDecoy doit etre pose sur la tuile quittee {jpos0}"
    assert len(state.entities) == n_units0 + 1, "exactement 1 entite ajoutee (le decoy)"
    # flag once/turn pose
    assert _has_flag_1407(state, judh), "le flag 1407 doit etre pose apres la reaction"


def test_g6b_counter_attack_in_range(g6b_state):
    """(C) L'attaquant a <= range(2) hex apres le move -> contre-attaque 3x Projectile : ses PV baissent."""
    from engine.runner.operations.triggers.dispatch import evaluate_trigger_operation
    from engine.runner.operations.triggers.base import TriggerEvent
    from engine.dsl.event_trigger_type import EventTriggerType
    state = g6b_state["build_state"]()
    board = g6b_state["board"]
    judh, enemy = _je(state)
    if not _place_adjacent(state, board, judh, enemy):
        pytest.skip("pas de tuile adjacente libre")
    ehc = _hc(state, enemy)
    if ehc is None or ehc.hp is None:
        pytest.skip("ennemi sans HealthComponent")
    hp_before = ehc.hp
    _uc(state, judh).times_attacked_this_turn = 1
    ev = TriggerEvent(EventTriggerType.Attack, enemy, judh, ranged=False, profile=None, is_crit=False)
    res = evaluate_trigger_operation(state, ev)
    # l'ennemi reste a <=2 hex de Judh (move recule au plus de 1 hex ; range=2) -> contre-attaque
    import hexgeo
    if hexgeo.distance(_pos(state, judh), _pos(state, enemy)) > 2:
        pytest.skip("apres move l'ennemi est hors range 2 (config board) : contre-attaque non exercee")
    assert ehc.hp < hp_before, f"l'attaquant doit encaisser la contre-attaque (hp {ehc.hp} < {hp_before}) ; res={res}"


def test_g6b_once_per_turn_then_rearm(g6b_state):
    """(D) 2e attaque du meme tour -> AUCUNE reaction (flag 1407 + compteur>=2). reset_times_attacked
    (start_turn) efface le flag ET le compteur -> Judh se re-arme."""
    from engine.runner.operations.triggers.dispatch import evaluate_trigger_operation
    from engine.runner.operations.triggers.base import TriggerEvent
    from engine.runner.operations.minimal_health import reset_times_attacked
    from engine.dsl.event_trigger_type import EventTriggerType
    state = g6b_state["build_state"]()
    board = g6b_state["board"]
    judh, enemy = _je(state)
    if not _place_adjacent(state, board, judh, enemy):
        pytest.skip("pas de tuile adjacente libre")
    # 1re attaque -> reaction (flag pose, compteur 1)
    _uc(state, judh).times_attacked_this_turn = 1
    ev = TriggerEvent(EventTriggerType.Attack, enemy, judh, ranged=False, profile=None, is_crit=False)
    evaluate_trigger_operation(state, ev)
    assert _has_flag_1407(state, judh)
    jpos_after1 = _pos(state, judh)

    # 2e attaque MEME tour : compteur passe a 2, flag present -> aucune reaction (Judh ne rebouge pas)
    _uc(state, judh).times_attacked_this_turn = 2
    evaluate_trigger_operation(state, ev)
    assert _pos(state, judh) == jpos_after1, "2e attaque du meme tour : Judh ne doit PAS reagir"

    # reset start_turn : efface flag + compteur -> re-arme
    reset_times_attacked(state)
    assert not _has_flag_1407(state, judh), "le flag 1407 doit etre efface au start_turn"
    assert _uc(state, judh).times_attacked_this_turn == 0


def test_g6b_on9_emitted_from_normal_attack(g6b_state):
    """(E) Integration : `after_hit_normal_attack` emet On(9) -> le trigger MoveAndSpawnDecoy fire depuis le
    vecteur d'attaque NORMALE (bout-en-bout, sans passer par evaluate_trigger_operation a la main)."""
    from engine.runner.operations.triggers.dispatch import after_hit_normal_attack
    state = g6b_state["build_state"]()
    board = g6b_state["board"]
    judh, enemy = _je(state)
    if not _place_adjacent(state, board, judh, enemy):
        pytest.skip("pas de tuile adjacente libre")
    jpos0 = _pos(state, judh)
    _uc(state, judh).times_attacked_this_turn = 1     # etat post-1re-attaque (record_attacked deja passe)
    res = after_hit_normal_attack(state, enemy, judh, ranged=False, profile=None, is_crit=False)
    assert any(isinstance(d, dict) and d.get("ability") == "HypersensoryAbilities_MoveAndSpawnDecoy"
               for d in (res or [])), f"On(9) via after_hit_normal_attack doit declencher MoveAndSpawnDecoy ; res={res}"
    assert _pos(state, judh) != jpos0, "Judh doit avoir bouge suite au On(9) de l'attaque normale"
