"""#366-r1 -- `1227 HarlequinsPanoply_IgnoreHits`, GARDE.

i2 (`HarlequinsPanoply`) : « The first time each turn this unit blocks a hit, **all further hits of
the attack are discarded** and the Harlequin Player moves 1 hex closer to the origin of the attack,
if possible. » -- le volet DEPLACEMENT n'est PAS porte (residu nomme, cf. l'en-tete de
`engine/runner/operations/triggers/loki/harlequins_panoply.py`).

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
ATTACKER = "necroDestroyer"      # p-units : 6 coups de MELEE (`unit_map` : 6hmp60), pierce 60
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
    attaque a 0 degat, et le compte de coups reste celui de l'arme (`ExecuteHits` fait `i++` sur un
    coup discarde : l'index avance, seul le degat disparait)."""
    rid = build_runner("31337", extra=_extra(grafted_bc))["rid"]
    st, att, dfd = _state(rpc, rid)
    _make_adjacent(st, att, dfd)
    r = _attack(st, att, dfd)
    per_hit = list(r["per_hit"])
    assert len(per_hit) >= 2, "montage : il faut une arme MULTI-COUPS (%r)" % (per_hit,)
    assert per_hit[0] > 0, per_hit                       # le coup qui BLOQUE porte quand meme
    assert all(h == 0 for h in per_hit[1:]), per_hit     # tous les suivants sont JETES
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
    r1 = _attack(st, att, dfd)
    assert all(h == 0 for h in r1["per_hit"][1:]), r1["per_hit"]
    assert uc.blocks_made_this_turn >= 1                          # RegisterBlockMade a tourne
    r2 = _attack(st, att, dfd)                                    # MEME tour -> passif desarme
    assert all(h > 0 for h in r2["per_hit"]), r2["per_hit"]
    # turn-start du proprietaire du greffon -> ResetBlocksMadeThisTurn -> le passif se re-arme
    StartTurnOperation.execute(st, st.get_entity(dfd).get_component(OwnerComponent).player)
    assert uc.blocks_made_this_turn == 0
    r3 = _attack(st, att, dfd)
    assert all(h == 0 for h in r3["per_hit"][1:]), r3["per_hit"]


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
