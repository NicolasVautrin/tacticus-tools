"""#366-r1 -- `1227 HarlequinsPanoply_IgnoreHits`, GARDE.

i2 (`HarlequinsPanoply`) : « The first time each turn this unit blocks a hit, **all further hits of
the attack are discarded** and the Harlequin Player moves 1 hex closer to the origin of the attack,
if possible. » -- le volet DEPLACEMENT est porte depuis #406 (la file
`IdunBattle.Core.MatchState$$AddPendingTriggeredAbility`, drainee a la borne du message ; cf.
`engine/runner/operations/triggers/dispatch/pending.py`). Ses gardes sont en fin de fichier.

MONTAGE. Les deux porteurs du passif sont `eldarSmnHarlequin` (SUMMON) et `eldarNpc3Harlequin`
(npc). La voie summon classique NE MARCHE PAS ici : le seul artefact qui summone le Harlequin est
`EnvFactionSummons:Aeldari` (`constants.unitId == 'eldarSmnHarlequin'`, `nrOfSummons == 3`), une
ability d'ENVIRONNEMENT -- il n'existe AUCUNE unite du catalogue qui le summone. On passe donc par
la GREFFE du passif sur une unite du pool (`catalog_inject.write_grafted_seed_bc`, `case-92` §5bis
volet passif, meme voie que `1284 EchoesFromTheWarp_Revive`). La greffe est LEGITIME ici : les deux
`CreateTrigger` du cluster ne lisent du porteur que son compteur de blocks et ses effets -- ni stat,
ni trait, ni arme.

`--block-target "100,0"` force `BlockChance = 100` sur le greffon : CHAQUE coup est bloque, donc le
trigger `On(UnitBlocked)` part au coup 0 de facon deterministe (aucun tirage de block a subir).
`BlockDamage = 0` garde le degat des coups NON discardes intact -> l'observable est bien « combien de
coups ont porte », pas « de combien le block les a rognes ».

Les tests montent une bataille LIVE (stats/PV/armures/effets REELS) puis exercent le VRAI chokepoint
`AttackDamageOperation.execute` offline. ASCII only ; ADJACENCE = evenq.
"""
from __future__ import annotations

import pytest

from engine.runner.snapshot import load_state
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.components import (StatsComponent, OwnerComponent, PositionComponent,
                                      HealthComponent, UnitComponent)
from engine.runner.operations.damage import AttackDamageOperation
from engine.runner.operations.turnflow import StartTurnOperation
from engine.runner.operations.triggers.loki.harlequins_panoply import (
    HARLEQUINS_PANOPLY_IGNORE_HITS, make_hit_interceptor)

GRAFT = "astraBullgryn"          # greffon (a-units) : PV eleves -> survit aux 6 coups de la contre-epreuve
#: ⚠ `necroDestroyer` porte DEUX armes, et l'entete de ce fichier n'en citait qu'UNE (#933-r1) :
#: `unit_map melee-multihit` rend `6hmp60/6hR2p60` -- 6 coups de MELEE (portee 1) **et** 6 coups de
#: TIR de portee **2**, meme pierce. La distance de montage est bornee par la SECONDE : au-dela de
#: 2, `FindAttackWeapon` (slot 0xaf d'`IBattleQuery`) ne rend AUCUNE arme, et
#: `IdunBattleLogic.Entities.Abilities.Active.Loki.ALoki_NormalAttackAbility$$ExecuteBehaviour`
#: sort AVANT `ExecuteNormalAttack` -- le port le mirrore depuis #419-r1-tr14-r1-r1
#: (`damage_ops/normal.py` : « PAS D'ARME UTILISABLE = PAS D'ATTAQUE »).
ATTACKER = "necroDestroyer"      # p-units : 6hmp60 (melee) / 6hR2p60 (tir, portee 2)
ABILITY = "HarlequinsPanoply"


@pytest.fixture(scope="module")
def grafted_bc(tmp_path_factory):
    """Seed BC ou `HarlequinsPanoply` est GREFFE sur le greffon. DEUX ecritures obligatoires
    (`BC.Units[].PassiveAbilities` + `BC.Abilities.PassiveAbilities[<nom>]`) -- cf.
    `catalog_inject.graft_passive_ability`. L'assertion sur le rapport est le garde-fou du MONTAGE :
    un montage rate doit ASSERTER, jamais skipper."""
    import catalog_inject as CI
    out = tmp_path_factory.mktemp("panoply") / "grafted-bc.json"
    p, reports = CI.write_grafted_seed_bc(str(out), ["%s:%s" % (GRAFT, ABILITY)])
    assert reports[0]["abilityId"] == 1187, reports
    assert reports[0]["passiveAbilitiesAfter"] == [1187], reports
    return str(p)


def _extra(bc):
    return ["--seed-bc", bc, "--rank", "17",
            "--p-units", ATTACKER, "--a-units", GRAFT,
            # BlockChance 100 -> block DETERMINISTE au coup 0 (aucun tirage de block a subir).
            # ⚠ `BlockDamage` DOIT etre > 0 : une source de block a montant nul n'entre pas dans
            # `block_sources` (mesure : avec "100,0" le port rend `did_block=False` sur les 6 coups,
            # donc AUCUN `On(UnitBlocked)`). 300 rogne sans annuler (degat/coup mesure ~510-640).
            "--block-target", "100,300"]


def _state(rpc, rid):
    from engine.entities.pathfinding.board import Board
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    assert isinstance(bg, dict) and bg.get("tiles"), "boardGraph indispo -- montage casse"
    board = Board(bg["tiles"], adjacency="evenq")
    dec = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
    tm = rpc("tileMeta", {"runnerId": rid}, 90)
    st = load_state(dec, ob, snap, board=board, tiles=tm)
    st.rng = IntBasedMersenneTwister(777)
    ids = {}
    for u in (dec.get("units") or []):
        if u.get("visualId") in (GRAFT, ATTACKER) and st.get_entity(u.get("id")) is not None:
            ids.setdefault(u["visualId"], int(u["id"]))
    assert GRAFT in ids and ATTACKER in ids, "unites absentes de l'etat capture: %r" % (ids,)
    return st, ids[ATTACKER], ids[GRAFT]


def _pos(st, uid):
    pc = st.get_entity(uid).get_component(PositionComponent)
    return (pc.col, pc.row)


def _set_pos(st, uid, col, row):
    pc = st.get_entity(uid).get_component(PositionComponent)
    pc.col, pc.row = int(col), int(row)


def _make_adjacent(st, attacker, defender):
    """DEPLACE l'attaquant sur une tuile libre adjacente au defenseur (jamais « bloque par la
    geometrie de spawn »). ASSERTE si aucune tuile n'est disponible."""
    board = st.board
    occupied = {_pos(st, e) for e, ent in st.entities.items()
                if ent.get_component(PositionComponent) is not None and e != attacker}
    for n in board.neighbours(board.id_at(*_pos(st, defender))):
        if not board.walkable(n):
            continue
        c = board.coord(n)
        p = (int(c[0]), int(c[1]))
        if p in occupied:
            continue
        _set_pos(st, attacker, p[0], p[1])
        return p
    raise AssertionError("aucune tuile libre adjacente au defenseur -- montage a revoir")


def _carries(st, uid):
    sc = st.get_entity(uid).get_component(StatsComponent)
    return list(getattr(sc.ctx, "passive_abilities", None) or [])


def _has_marker(st, uid):
    return any((not e.consumed) and (not e.expired)
               and e.effect_type == HARLEQUINS_PANOPLY_IGNORE_HITS
               for e in st.effects.by_unit.get(int(uid), []))


def _attack(st, attacker, defender):
    return AttackDamageOperation.execute(st, attacker, defender, 20)


def _hexdist(st, a, b):
    import hexgeo
    return hexgeo.distance(_pos(st, a), _pos(st, b))


#: LA DISTANCE DE MONTAGE, et elle est bornee DES DEUX COTES (#933-r1) :
#:   * `>= 2` -- le gate natif du deplacement est `NOT IsAdjacent(Owner@+0x30, Caster@+0x48, 3)` :
#:     au contact, l'arbre refuse et le porteur ne bouge pas (c'est `test_no_move_when_already_
#:     adjacent` qui garde ce bord) ;
#:   * `<= 2` -- la portee de la SECONDE arme de `necroDestroyer` (`6hR2p60`). A 3, aucune arme
#:     n'est utilisable, `AttackDamageOperation.execute` rend `None`, et les deux tests ci-dessous
#:     tombaient en `TypeError: 'NoneType' object is not subscriptable` / `assert []`.
#: Les deux bornes se rejoignent sur UNE valeur : 2. Elle etait a 3 depuis #406, et c'est le gate
#: d'arme entre par #419-r1-tr14-r1-r1 qui l'a rendue injouable -- le PORT avait raison contre le
#: montage, pas l'inverse : mesure du 2026-08-13, meme etat, distance 2 -> l'attaque rend son dict,
#: distance 3 -> `None`, alors que stats, PV et gates de mort sont tous SAINS des deux cotes.
DIST_MONTAGE = 2


def _place_at_distance(st, attacker, defender, want):
    """DEPLACE l'attaquant sur une tuile LIBRE a distance hex `want` du defenseur -- et ASSERTE si
    aucune n'existe (jamais « bloque par la geometrie de spawn »). Le montage du DEPLACEMENT exige
    `want >= 2` (gate natif `NOT IsAdjacent(Owner, Caster, 3)`) ET `want <= 2` (portee d'arme du
    caster) : cf. `DIST_MONTAGE`."""
    import hexgeo
    board = st.board
    dpos = _pos(st, defender)
    occupied = {_pos(st, e) for e, ent in st.entities.items()
                if ent.get_component(PositionComponent) is not None and e != attacker}
    for tid in board.by_id:
        if not board.walkable(tid):
            continue
        c = board.coord(int(tid))
        p = (int(c[0]), int(c[1]))
        if p in occupied or hexgeo.distance(p, dpos) != int(want):
            continue
        _set_pos(st, attacker, p[0], p[1])
        return p
    raise AssertionError("aucune tuile libre a distance %d du defenseur -- montage a revoir" % want)


# ---------------------------------------------------------------- 1. la GREFFE a mordu
def test_graft_is_mounted(rpc, build_runner, grafted_bc):
    """Garde de MONTAGE : le greffon porte REELLEMENT `HarlequinsPanoply` cote port (canal MESURE
    `UnitContext.passive_abilities`), et l'intercepteur per-coup le reconnait. Sans ca, tous les
    tests suivants seraient VERTS pour la mauvaise raison."""
    rid = build_runner("31337", extra=_extra(grafted_bc))["rid"]
    st, att, dfd = _state(rpc, rid)
    assert ABILITY in _carries(st, dfd), _carries(st, dfd)
    icept = make_hit_interceptor(st, att, dfd)
    assert icept is not None and icept._discard is not None and icept._pose is not None


# ---------------------------------------------------------------- 2. le DISCARD
def test_further_hits_of_the_attack_are_discarded(rpc, build_runner, grafted_bc):
    """L'observable central : un coup bloque -> 1227 pose -> TOUS les coups suivants de la MEME
    attaque sont JETES, et le compte de coups reste celui de l'arme (`ExecuteHits` fait `i++` sur un
    coup discarde : l'index avance, seul le degat disparait).

    ⚠ #462-r4e-o-r1-r1 -- ce test assertionnait `all(h == 0 for h in per_hit[1:])`, qui est
    VACUEUSEMENT VRAI depuis que `per_hit` ne porte plus que les events EMIS (un coup discarde sort
    d'`ExecuteHit` AVANT la sub-op 0x42, donc avant `ApplyDamage`, donc sans `UnitDamaged`). La
    propriete est desormais portee par la CARDINALITE : 1 event pour N coups executes."""
    rid = build_runner("31337", extra=_extra(grafted_bc))["rid"]
    st, att, dfd = _state(rpc, rid)
    _make_adjacent(st, att, dfd)
    r = _attack(st, att, dfd)
    per_hit = list(r["per_hit"])
    hits_exec = int(r.get("hits") or r.get("hits_executed") or 0)
    assert hits_exec >= 2, "montage : il faut une arme MULTI-COUPS (%r coups)" % (hits_exec,)
    assert len(per_hit) == 1, (
        "un coup discarde a laisse un event : per_hit=%r pour %d coups" % (per_hit, hits_exec))
    assert per_hit[0] > 0, per_hit                       # le coup qui BLOQUE porte quand meme
    assert r["total"] == per_hit[0], (r["total"], per_hit)


# ---------------------------------------------------------------- 3. contre-epreuve : SANS le passif
def test_without_the_passive_every_hit_lands(rpc, build_runner, grafted_bc):
    """CONTRE-EPREUVE. On retire le passif du contexte du greffon -- et on VERIFIE que la mutation a
    MORDU (l'intercepteur ne monte plus les deux triggers) AVANT d'interpreter le resultat : VERT est
    le resultat SUSPECT sur une contre-epreuve. Sans le passif, les 6 coups portent."""
    rid = build_runner("31337", extra=_extra(grafted_bc))["rid"]
    st, att, dfd = _state(rpc, rid)
    _make_adjacent(st, att, dfd)
    st.get_entity(dfd).get_component(StatsComponent).ctx.passive_abilities = []
    assert ABILITY not in _carries(st, dfd)                       # la mutation a mordu (1/2)
    icept = make_hit_interceptor(st, att, dfd)
    assert icept is not None and icept._discard is None           # la mutation a mordu (2/2)
    r = _attack(st, att, dfd)
    # `all()` sur une liste VIDE est vrai : on assertionne d'abord la CARDINALITE (#462-r4e-o-r1-r1).
    assert len(r["per_hit"]) == int(r["hits"]), (r["per_hit"], r["hits"])
    assert all(h > 0 for h in r["per_hit"]), r["per_hit"]
    assert not _has_marker(st, dfd)


# ---------------------------------------------------------------- 4. « the FIRST time each turn »
def test_only_the_first_block_of_the_turn_arms_it(rpc, build_runner, grafted_bc):
    """`NOT HasBlockedThisTurn(Target)` : la 2e attaque du MEME tour ne re-arme PAS le passif -- le
    compteur `ActorStatisticsComponent+0x8c` a ete incremente par le `RegisterBlocks` du 1er coup
    bloque. Et le compteur est REMIS A ZERO au turn-start du proprietaire du greffon
    (`StartTurnOperation$$ResetUnit`), ce qui re-arme le passif."""
    rid = build_runner("31337", extra=_extra(grafted_bc))["rid"]
    st, att, dfd = _state(rpc, rid)
    _make_adjacent(st, att, dfd)
    uc = st.get_entity(dfd).get_component(UnitComponent)
    assert uc.blocks_made_this_turn == 0
    assert uc.blocks_made_this_battle == 0
    r1 = _attack(st, att, dfd)
    # #462-r4e-o-r1-r1 : CARDINALITE (un coup discarde n'emet AUCUN event), pas « les suivants a 0 »
    # -- qui serait vacueusement vrai sur une liste d'une seule entree.
    assert len(r1["per_hit"]) == 1, (r1["per_hit"], r1.get("hits"))
    assert uc.blocks_made_this_turn >= 1                          # RegisterBlockMade a tourne
    # `RegisterBlockMade` pousse les DEUX compteurs -- `+0x8c` ET `+0x88` (#393-r1). Le battle
    # counter n'a AUCUN lecteur porte ; cette garde est ce qui le tient au mirror du `+=` double.
    assert uc.blocks_made_this_battle == uc.blocks_made_this_turn, (
        "battle=%d turn=%d" % (uc.blocks_made_this_battle, uc.blocks_made_this_turn))
    n_battle = uc.blocks_made_this_battle
    r2 = _attack(st, att, dfd)                                    # MEME tour -> passif desarme
    assert len(r2["per_hit"]) == int(r2["hits"]), (r2["per_hit"], r2["hits"])
    assert all(h > 0 for h in r2["per_hit"]), r2["per_hit"]
    # turn-start du proprietaire du greffon -> ResetBlocksMadeThisTurn -> le passif se re-arme
    StartTurnOperation.execute(st, st.get_entity(dfd).get_component(OwnerComponent).player)
    assert uc.blocks_made_this_turn == 0
    # `ResetBlocksMadeThisTurn` n'ecrit QUE `+0x8c` (decompile) : le compteur de BATAILLE survit.
    assert uc.blocks_made_this_battle >= n_battle, (
        "le reset de tour a rogne le compteur de BATAILLE : %d < %d"
        % (uc.blocks_made_this_battle, n_battle))
    r3 = _attack(st, att, dfd)
    assert len(r3["per_hit"]) == 1, (r3["per_hit"], r3.get("hits"))   # re-arme -> discard a nouveau


# ---------------------------------------------------------------- 4bis. le gate `NOT HasTrait(Object)`
def test_object_attacker_does_not_arm_it(rpc, build_runner, grafted_bc):
    """`NOT HasTrait(Caster@DSLSelectors+0x48, 0xd = UnitTrait.Object)` -- sur le vecteur
    `On(UnitBlocked)`, `Caster` est l'ATTAQUANT. Un attaquant `Object` (tourelle / decor) n'arme donc
    PAS le passif : les 6 coups portent. Le trait est POSE sur le contexte de l'attaquant (le seul
    levier qui produit ce regime -- aucune unite `Object` du pool ne porte une arme a 6 coups)."""
    rid = build_runner("31337", extra=_extra(grafted_bc))["rid"]
    st, att, dfd = _state(rpc, rid)
    _make_adjacent(st, att, dfd)
    actx = st.get_entity(att).get_component(StatsComponent).ctx
    actx.traits = list(actx.traits or []) + ["Object"]
    assert "Object" in actx.traits                       # la mutation a mordu
    r = _attack(st, att, dfd)
    assert len(r["per_hit"]) == int(r["hits"]), (r["per_hit"], r["hits"])
    assert all(h > 0 for h in r["per_hit"]), r["per_hit"]
    assert not _has_marker(st, dfd)


# ---------------------------------------------------------------- 5. le marqueur ne SURVIT pas
def test_marker_does_not_survive_the_attack(rpc, build_runner, grafted_bc):
    """`HarlequinsPanoply_IgnoreHitsEffect$$CreateTargetTrigger` = `On(9 = Attack) & OwnerIsTarget`
    -> le marqueur part a la CLOTURE de l'attaque. C'est ce qui empeche la degradation la plus
    permissive possible (un porteur qui annulerait TOUTES les attaques suivantes)."""
    rid = build_runner("31337", extra=_extra(grafted_bc))["rid"]
    st, att, dfd = _state(rpc, rid)
    _make_adjacent(st, att, dfd)
    _attack(st, att, dfd)
    assert not _has_marker(st, dfd), "1227 a SURVECU a son attaque -> discard permanent"


# ================================================================= #406 : le DEPLACEMENT d'1 hex
# `HarlequinsPanoplyAbility$$CreateBehaviour` branche `UnitBlocked` pose AUSSI
# `TriggerAbilityDelayed(Owner, 0x4a3, 3)`, qui ENFILE (`IdunBattle.Core.MatchState$$
# AddPendingTriggeredAbility`). Le drain -- `IdunBattle.Messages.InputMessageProcessor$$
# ProcessPendingTriggeredAbilities` -- n'est appele que par `RunPhase` / `VerifyTurnEnd`, donc APRES
# le retour de `action()`. Les deux gardes ci-dessous separent exactement ces deux temps.

def test_block_only_queues_the_move_it_does_not_move(rpc, build_runner, grafted_bc):
    """TEMPS 1 -- l'attaque ENFILE et ne DEPLACE PAS. C'est la garde anti-regression du seul point
    qui rendait ce port dangereux : un `MoveUnit` execute inline ferait entrer `On(PreUnitMove)` /
    `On(UnitAfterMove)` (l'OVERWATCH) au milieu de la resolution des coups, dans un ordre qui n'est
    pas celui du natif."""
    from engine.runner.operations.triggers.loki.harlequins_panoply import HARLEQUINS_PANOPLY_ABILITY
    rid = build_runner("31337", extra=_extra(grafted_bc))["rid"]
    st, att, dfd = _state(rpc, rid)
    _place_at_distance(st, att, dfd, DIST_MONTAGE)
    before = _pos(st, dfd)
    assert st.pending_triggered_abilities == []
    r = _attack(st, att, dfd)
    assert len(r["per_hit"]) == 1, (r["per_hit"], r.get("hits"))      # le passif a bien mordu
    assert _pos(st, dfd) == before, "le porteur a bouge PENDANT l'attaque -- collapse inline"
    q = list(st.pending_triggered_abilities)
    assert len(q) == 1, q
    assert (q[0][0], q[0][1]) == (dfd, HARLEQUINS_PANOPLY_ABILITY), q
    assert q[0][2].actor_id == att, q                                  # `Caster@+0x48` = l'attaquant


def test_drain_moves_the_holder_one_hex_closer(rpc, build_runner, grafted_bc):
    """TEMPS 2 -- le drain execute la branche `Custom` : `MoveUnit(Owner, First(SortByDistance(
    MovableTilesInRange(Owner, MainTileOfUnits(Owner), Const(1)), Caster)))` = UN hex vers
    l'attaquant. `Const(1)` est LU (`IdunBattleLogic.Entities.DSLFormulas$$.ctor` : `+0x20` = 1),
    pas la stat Movement -- d'ou l'assertion `dist_after == dist_before - 1` et non « <= »."""
    from engine.runner.operations.triggers.dispatch.pending import (
        process_pending_triggered_abilities)
    rid = build_runner("31337", extra=_extra(grafted_bc))["rid"]
    st, att, dfd = _state(rpc, rid)
    _place_at_distance(st, att, dfd, DIST_MONTAGE)
    before, d0 = _pos(st, dfd), _hexdist(st, att, dfd)
    _attack(st, att, dfd)
    out = process_pending_triggered_abilities(st)
    assert st.pending_triggered_abilities == [], "la file n'a pas ete videe"
    assert out and out[0]["ability"] == "HarlequinsPanoply_Move", out
    assert out[0]["moved"] is True, out
    assert _pos(st, dfd) != before, "le drain n'a PAS deplace le porteur"
    assert _hexdist(st, att, dfd) == d0 - 1, (d0, _hexdist(st, att, dfd))


def test_no_move_when_already_adjacent(rpc, build_runner, grafted_bc):
    """CONTRE-EPREUVE du gate `NOT IsAdjacent(Owner@+0x30, Caster@+0x48, 3)` : au CONTACT, le
    `If` est FAUX et le porteur ne bouge pas -- alors que la file, elle, a bien ete armee (c'est
    l'arbre qui refuse, pas l'enfilement). VERT est le resultat suspect sur une contre-epreuve :
    on verifie donc d'abord que l'enfilement a EU LIEU."""
    from engine.runner.operations.triggers.dispatch.pending import (
        process_pending_triggered_abilities)
    rid = build_runner("31337", extra=_extra(grafted_bc))["rid"]
    st, att, dfd = _state(rpc, rid)
    _make_adjacent(st, att, dfd)
    assert _hexdist(st, att, dfd) == 1
    before = _pos(st, dfd)
    _attack(st, att, dfd)
    assert len(st.pending_triggered_abilities) == 1, st.pending_triggered_abilities
    out = process_pending_triggered_abilities(st)
    assert out and out[0]["moved"] is False, out
    assert _pos(st, dfd) == before, "le porteur a bouge alors qu'il etait DEJA adjacent"


def test_runner_apply_drains_the_queue(rpc, build_runner, grafted_bc):
    """La BORNE du drain cote port : `Runner.apply`, entre les post-handlers et `phase_end_triggers`
    (= `EndPhase`). Mirror de la position LUE du 1er `$$ProcessPendingTriggeredAbilities` de
    `IdunBattle.Messages.InputMessageProcessor$$RunPhase`. Le test enfile A LA MAIN puis fait passer
    un message NEUTRE : ce qui est verifie ici est la borne, pas le contenu de l'ability."""
    from engine.runner.runner import Runner
    from engine.runner.messages import Message
    from engine.runner.operations.triggers.base import TriggerEvent
    from engine.runner.operations.triggers.dispatch.pending import add_pending_triggered_ability
    from engine.runner.operations.triggers.loki.harlequins_panoply import HARLEQUINS_PANOPLY_ABILITY
    from engine.dsl.event_trigger_type import EventTriggerType
    rid = build_runner("31337", extra=_extra(grafted_bc))["rid"]
    st, att, dfd = _state(rpc, rid)
    _place_at_distance(st, att, dfd, DIST_MONTAGE)
    d0 = _hexdist(st, att, dfd)
    add_pending_triggered_ability(st, dfd, HARLEQUINS_PANOPLY_ABILITY,
                                  TriggerEvent(int(EventTriggerType.Custom), att, dfd,
                                               ranged=False, profile=None))
    Runner(st).apply(Message())          # aucun handler installe -> seule la BORNE est exercee
    assert st.pending_triggered_abilities == [], "Runner.apply n'a pas draine la file"
    assert _hexdist(st, att, dfd) == d0 - 1, (d0, _hexdist(st, att, dfd))
