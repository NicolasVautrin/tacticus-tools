"""#366-r1 -- `1284 EchoesFromTheWarp_Revive`, GARDE.

SECONDE instanciation de `IdunBattleLogic.Entities.Abilities.Triggered.Loki.GhostReviveAbility` /
`IdunBattle.Entities.Effects.Loki.GhostEffect` (la premiere, `1186 TimeFlux_Revive`, est gardee par
`test_ghost_revive_live.py`). MEME classe, MEME arbre -- une seule chose change, la branche
d'`amount` du `CreateTargetTriggerBehaviour` :

    source == 0x485 (1157 TimeFlux) ? Direct(ConfigVar('hp')) : StatAmount(src, Health, Initial)

i2 : « When this unit moves, it leaves a time ghost behind on the hex it moved from. ... **The first
time this unit dies each battle**, if its time ghost is on the battlefield then it revives with
**Full Health** at its location. This works even if this unit is **Overkilled**. »

MONTAGE -- l'unique porteur `thousNpc4Terminator` est un **npc**, que `buildNormalizedBC` refuse
structurellement (#228). On passe donc par la GREFFE du passif sur une unite DU POOL
(`catalog_inject.write_grafted_seed_bc`, `case-92` §5bis volet passif). Greffon : `thousTerminator`
(« Toth ») -- MEME faction, MEMES traits `WeaverOfFate`/`TerminatorArmour` que le vrai porteur ; la
greffe REMPLACE sa liste de passives, donc `TimeFlux` (ghost 1186 + regen) disparait et aucun
confond n'est possible entre les deux instanciations.

DISCRIMINANT PRINCIPAL. Le montant du revive doit SUIVRE la PV initiale du greffon : deux regimes de
`Health` rendent deux montants differents. Une constante, la branche `Direct(ConfigVar('hp'))` de
TimeFlux (qui rendrait 3290) ou une lecture de `StatPart.Current` (qui rendrait 0, l'unite venant de
mourir) echouent tous les trois.

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
from engine.runner.operations.triggers.loki.ghost_revive import (ECHOES_GHOST_EFFECT,
                                                                 TIME_FLUX_GHOST_EFFECT)
from engine.runner.components import (UnitComponent, HealthComponent, StatsComponent,
                                      OwnerComponent, PositionComponent)
from engine.runner.prng import IntBasedMersenneTwister

GRAFT = "thousTerminator"
ABILITY = "EchoesFromTheWarp"
HP = 9000                     # `Health` du BC -> `FillUpStatComponent$$Initialize` -> StatPart.Initial


@pytest.fixture(scope="module")
def grafted_bc(tmp_path_factory):
    """Seed BC ou `EchoesFromTheWarp` est GREFFE sur le greffon. DEUX ecritures obligatoires
    (`BC.Units[].PassiveAbilities` + `BC.Abilities.PassiveAbilities[<nom>]`) -- cf.
    `catalog_inject.graft_passive_ability`."""
    import catalog_inject as CI
    out = tmp_path_factory.mktemp("echoes") / "grafted-bc.json"
    p, reports = CI.write_grafted_seed_bc(str(out), ["%s:%s" % (GRAFT, ABILITY)])
    assert reports[0]["abilityId"] == 1219, reports
    assert reports[0]["passiveAbilitiesAfter"] == [1219], reports
    return str(p)


def _extra(bc, hp=HP):
    return ["--seed-bc", bc, "--rank", "17",
            "--p-units", GRAFT, "--a-units", "astraBullgryn,orksNob",
            "--unit-stat", "%s:Health=%d,RemainingHealth=%d,Armor=0,FixedArmor=0" % (GRAFT, hp, hp)]


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
    td = next((u for u in (dec.get("units") or []) if u.get("visualId") == GRAFT), None)
    if td is None or st.get_entity(td.get("id")) is None:
        pytest.skip("greffon absent de l'etat capture")
    return st, int(td["id"])


def _ctx(st, uid):
    return st.get_entity(uid).get_component(StatsComponent).ctx


def _start_turn(st, uid):
    StartTurnOperation.execute(st, st.get_entity(uid).get_component(OwnerComponent).player)


def _pos(st, uid):
    pc = st.get_entity(uid).get_component(PositionComponent)
    return (pc.col, pc.row)


def _move(st, uid, to):
    from engine.runner.operations.triggers import after_move_triggers
    MoveUnitOperation(uid, to).execute(st, EventBus())
    after_move_triggers(st, uid)


def _free_neighbour(st, uid, exclude=()):
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


def _ghost_tiles(st, effect_type=ECHOES_GHOST_EFFECT):
    if st.effects is None or st.board is None:
        return []
    return sorted(int(t) for t, effs in st.effects.by_unit.items()
                  if int(t) in st.board.by_id
                  and any((not e.consumed) and e.effect_type == int(effect_type) for e in effs))


def _an_enemy(st, uid):
    toc = st.get_entity(uid).get_component(OwnerComponent)
    for eid, e in sorted(st.entities.items()):
        oc, uc = e.get_component(OwnerComponent), e.get_component(UnitComponent)
        if oc is None or oc.team == toc.team:
            continue
        if uc is not None and uc.alive:
            return eid
    pytest.skip("aucun ennemi vivant")


def _kill(st, uid, killer_id):
    e = st.get_entity(uid)
    hc = e.get_component(HealthComponent)
    hp_before = int(hc.hp)
    hc.hp = 0
    return AttackDamageOperation._fire_death_if_killed(st, uid, killer_id, hp_before, 0, e,
                                                       damage=hp_before) or []


def test_grafted_passive_is_visible_to_the_port_live(live_session, rpc, build_runner,
                                                     grafted_bc):
    """PRE-CONDITION DU MONTAGE, et garde du canal #366-r1 : le passif GREFFE doit etre VU par le
    port. `collect_triggered_abilities` derivait les passives du gameconfig par `visualId` -- une
    greffe y serait restee INVISIBLE, et tout ce fichier aurait garde du vide. La source est
    desormais la MESURE (`unitAbilityStates`, hierarchie 2 = `UnitConfiguration.PassiveAbilities`,
    cf. `UnitFactory$$AddConfiguredAbilities`)."""
    rid = build_runner("31337", extra=_extra(grafted_bc))["rid"]
    st, uid = _state(rpc, rid)
    ctx = _ctx(st, uid)
    assert ctx.passive_abilities is not None, \
        ("canal `unitAbilityStates` MUET -- `passive_abilities` non seede "
         f"(ability_states_seed={st.ability_states_seed})")
    assert ABILITY in ctx.passive_abilities, \
        f"le passif greffe n'est pas monte : {ctx.passive_abilities}"
    assert "TimeFlux" not in ctx.passive_abilities, \
        ("la greffe devait REMPLACER les passives du greffon -- `TimeFlux` encore la, "
         f"le ghost 1186 confondrait la mesure : {ctx.passive_abilities}")
    from engine.runner.operations.triggers.dispatch.core import collect_triggered_abilities
    names = {type(a).__name__ for a in collect_triggered_abilities(st) if a.owner_id == uid}
    assert "EchoesFromTheWarpAbility" in names, f"ability non inscrite au dispatch : {sorted(names)}"
    assert "TimeFluxReviveAbility" not in names, f"1186 inscrit a tort : {sorted(names)}"


def test_echoes_revives_at_full_health_on_the_ghost_tile_live(live_session, rpc, build_runner,
                                                             grafted_bc):
    """FACE POSITIVE. Le greffon demarre son tour en A, bouge en B (B != A), y meurt -> il revient
    VIVANT **en A** a **PV PLEINS** (`StatAmount(src, Health, Initial)`), et le ghost 1284 est
    consomme. La tuile de mort et la tuile de revive DIFFERENT : sans quoi un revive in-place serait
    indetectable."""
    rid = build_runner("31337", extra=_extra(grafted_bc))["rid"]
    st, uid = _state(rpc, rid)
    _start_turn(st, uid)
    a = _pos(st, uid)
    b = _free_neighbour(st, uid)
    if b is None:
        pytest.skip("aucune tuile voisine libre")
    assert a != b
    _move(st, uid, b)
    assert _pos(st, uid) == b, "le move n'a pas ete applique"
    tile_a = st.board.id_at(*a)
    assert _ghost_tiles(st) == [tile_a], \
        f"le ghost 1284 doit etre pose sur la tuile de DEBUT DE TOUR {a} (tile {tile_a})"
    assert _ghost_tiles(st, TIME_FLUX_GHOST_EFFECT) == [], \
        "aucun ghost 1186 ne doit exister (TimeFlux a ete remplace par la greffe)"

    hp_max = int(st.get_entity(uid).get_component(HealthComponent).hp_max)
    out = _kill(st, uid, _an_enemy(st, uid))
    e = st.get_entity(uid)
    assert e.get_component(UnitComponent).alive, f"le greffon aurait du etre revive (sorties={out})"
    assert _pos(st, uid) == a, \
        f"revive attendu sur la tuile du ghost {a}, obtenu {_pos(st, uid)} (mort en {b})"
    assert int(e.get_component(HealthComponent).hp) == hp_max, \
        "« Full Health » : le montant doit valoir la PV INITIALE, pas une variable de config"
    assert any("kill_cancelled_by_revive" in r for r in out), \
        f"la garde `!pendingRevive.HasValue` n'a pas annule la mort (sorties={out})"
    assert _ghost_tiles(st) == [], "le ghost devait etre CONSOMME par la resurrection"


def test_echoes_revive_amount_follows_initial_health_live(live_session, rpc, build_runner,
                                                          grafted_bc):
    """LE DISCRIMINANT DU FORK. Deux regimes de `Health` (donc de `StatPart.Initial`) doivent rendre
    DEUX montants differents, chacun egal a la PV initiale. Ce test echoue si le port :
      * prend la branche `Direct(ConfigVar('hp'))` de `TimeFlux` (valeur CONSTANTE, et
        `EchoesFromTheWarp` n'a d'ailleurs AUCUNE variable au gameconfig) ;
      * lit `StatPart.Current` (l'unite vient de mourir -> 0) ;
      * ou fige un scalaire quelconque."""
    seen = {}
    for hp in (9000, 15000):
        rid = build_runner("31337", extra=_extra(grafted_bc, hp))["rid"]
        st, uid = _state(rpc, rid)
        _start_turn(st, uid)
        a = _pos(st, uid)
        b = _free_neighbour(st, uid)
        if b is None:
            pytest.skip("aucune tuile voisine libre")
        _move(st, uid, b)
        assert _ghost_tiles(st) == [st.board.id_at(*a)], "pre-condition : le ghost est pose"
        hp_max = int(st.get_entity(uid).get_component(HealthComponent).hp_max)
        _kill(st, uid, _an_enemy(st, uid))
        e = st.get_entity(uid)
        assert e.get_component(UnitComponent).alive, f"pas de revive au regime Health={hp}"
        seen[hp_max] = int(e.get_component(HealthComponent).hp)
    assert len(seen) == 2, \
        f"les deux regimes n'ont pas produit deux PV max distinctes ({seen}) -- test non discriminant"
    for hp_max, revived in seen.items():
        assert revived == hp_max, f"revive a {revived}, attendu {hp_max} (PV initiale)"


def test_echoes_no_move_no_ghost_live(live_session, rpc, build_runner, grafted_bc):
    """FACE NEGATIVE 1 : sans MOVE, aucun `On(PreUnitMove)` -> aucun ghost -> mort definitive.
    Discriminant du VECTEUR : le port ne doit pas ressusciter « par defaut »."""
    rid = build_runner("31337", extra=_extra(grafted_bc))["rid"]
    st, uid = _state(rpc, rid)
    _start_turn(st, uid)
    assert _ghost_tiles(st) == [], "aucun ghost ne doit exister avant le premier move"
    out = _kill(st, uid, _an_enemy(st, uid))
    assert not st.get_entity(uid).get_component(UnitComponent).alive, \
        f"revive sans avoir bouge (sorties={out})"


def test_echoes_revive_is_once_per_battle_live(live_session, rpc, build_runner, grafted_bc):
    """FACE NEGATIVE 2 -- `NOT HasBeenRevivedByAbility(self, 1284)`, le « **the first time this unit
    dies each battle** » de l'i2. Le set `ActorStatisticsComponent+0xe0` n'est JAMAIS remis a zero :
    apres un revive, un nouveau move ne repose plus de ghost, et la 2e mort est definitive."""
    rid = build_runner("31337", extra=_extra(grafted_bc))["rid"]
    st, uid = _state(rpc, rid)
    _start_turn(st, uid)
    a = _pos(st, uid)
    b = _free_neighbour(st, uid)
    if b is None:
        pytest.skip("aucune tuile voisine libre")
    _move(st, uid, b)
    foe = _an_enemy(st, uid)
    _kill(st, uid, foe)
    uc = st.get_entity(uid).get_component(UnitComponent)
    assert uc.alive and _pos(st, uid) == a, "le 1er revive doit avoir eu lieu (pre-condition)"
    assert ECHOES_GHOST_EFFECT in uc.revived_by_abilities, \
        "`ReviveUnitOperation` doit enregistrer 1284 dans `revived_by_abilities`"
    _start_turn(st, uid)
    b2 = _free_neighbour(st, uid)
    if b2 is None:
        pytest.skip("aucune tuile voisine libre pour le 2e move")
    _move(st, uid, b2)
    assert _ghost_tiles(st) == [], \
        "un 2e ghost a ete pose alors que le greffon a DEJA ete ressuscite par 1284"
    out = _kill(st, uid, foe)
    assert not st.get_entity(uid).get_component(UnitComponent).alive, \
        f"ressuscite DEUX fois par le meme ghost (sorties={out})"


def test_echoes_ghost_vanishes_when_another_unit_enters_live(live_session, rpc, build_runner,
                                                             grafted_bc):
    """FACE NEGATIVE 3 -- retrait n°3 (`On(0x24 = UnitPositionChanged_1) & NOT AreEqual(caster,
    EffectSource) & Contains(TargetTiles, Owner)`), enregistre pour 1284 comme pour 1186. C'est le
    « the time ghost vanishes if the hex becomes occupied by another unit » de l'i2."""
    rid = build_runner("31337", extra=_extra(grafted_bc))["rid"]
    st, uid = _state(rpc, rid)
    _start_turn(st, uid)
    a = _pos(st, uid)
    b = _free_neighbour(st, uid)
    if b is None:
        pytest.skip("aucune tuile voisine libre")
    _move(st, uid, b)
    assert _ghost_tiles(st) == [st.board.id_at(*a)], "pre-condition : le ghost est pose"
    foe = _an_enemy(st, uid)
    _move(st, foe, a)
    assert _ghost_tiles(st) == [], \
        "le ghost devait etre dissipe par l'arrivee d'une autre unite sur sa tuile"
    out = _kill(st, uid, foe)
    assert not st.get_entity(uid).get_component(UnitComponent).alive, \
        f"revive alors que le ghost avait ete dissipe (sorties={out})"
