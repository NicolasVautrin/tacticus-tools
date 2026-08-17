"""Tache #94 — consommateurs SPAWN/AI-CONTROL : Waaagh (1058), SendInTheNextWave (1016),
Incursion (1021), Poxwalkers (1040). Confrontation LIVE de la face COMBAT portee.

VAs portees :
  `IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$ExecuteBehaviour` (+ `IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$GetBuffBehaviour`,
     `IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$GetPossibleMovementTiles`, `IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$GetAttackBehaviour`,
     `IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$GetSummonBehaviour`, `IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$GetTriggerSummonsBehaviour`)
  `IdunBattleLogic.Entities.Abilities.Active.Loki.SendInTheNextWaveAbility$$ExecuteBehaviour` (+ `IdunBattleLogic.Entities.Abilities.Active.Loki.SendInTheNextWaveAbility$$GetNumSummons`,
     `IdunBattleLogic.Entities.Abilities.Active.Loki.SendInTheNextWaveAbility$$GetSpawnTilesSelector`, `IdunBattleLogic.Entities.Abilities.Active.Loki.SendInTheNextWaveAbility$$GetSpawnedUnitRange`)
  `IdunBattleLogic.Entities.Abilities.Active.Loki.IncursionAbility$$ExecuteBehaviour` (+ `IdunBattleLogic.Entities.Abilities.Active.Loki.IncursionAbility$$GetNextSpawnTile`,
     `IdunBattleLogic.Entities.Abilities.Active.Loki.IncursionAbility$$GetContinueTrigger`)
  `IdunBattleLogic.Entities.Abilities.Active.Loki.SpawnPoxwalkersAbility$$ExecuteBehaviour`
     (+ `IdunBattle.Entities.Effects.Loki.ContagionsOfNurgle_ArmorReduction_Effect$$CalculateRange`)
Primitives : `IdunBattleLogic.Entities.DSLSelectors$$UnitsWithVisualId`, `IdunBattleLogic.Entities.DSLFormulas$$VisualUnitIdFromUnitId`,
  `IdunBattleLogic.Entities.DSLBehaviors$$ChainBehaviour`, `IdunBattleLogic.Entities.DSLBehaviors$$UseNormalAttackIfAble`,
  `IdunBattleLogic.Entities.DSLBehaviors$$PerformAIAttackFromCurrentPosition`, `IdunBattleLogic.Entities.DSLFormulas$$UnitMovementRangeWithBonus`.

ASCII-only. Skip si pas de session / geometrie non cooperative.
"""
from __future__ import annotations

import os
import sys

import pytest

import hexgeo

from engine.runner.components import HealthComponent, PositionComponent, UnitComponent
from engine.entities.effects.magnitude import ability_var

sys.path.insert(0, os.path.dirname(__file__))      # tests/engine/runner -> import du helper sibling

from _summon_montage import (upos as _upos, board_of as _board,        # noqa: E402
                             drive_until_castable as _drive_until_castable,
                             cast_and_replay as _cast_and_replay,
                             port_spawn_positions, waaagh_scenario, waaagh_ally_scenario)


# ============================================================================================== #
# Waaagh (1058, orksWarboss) — 2e consommateur de PerformAIAction (asGroup=1, resetTurnFlags=1)
# ============================================================================================== #

# Roster / board / seed : `_summon_montage` (source unique) — le montage est une FABRIQUE
# reutilisable, pas un bloc inline recopie par chaque test.


@pytest.fixture(scope="session")
def waaagh(rpc, build_runner):
    return waaagh_scenario(rpc, build_runner)


def test_waaagh_spawn_count_matches_live(waaagh):
    """`Spawn(PickRandomly(CanAddUnit(AdjacentTiles(casterTile)), nrOfSummons=2))` : le port invoque le
    MEME nombre d'Ork Boyz que le natif. (Comptage sur les `changes.appeared` de l'action -- source
    PRIMAIRE du runner, robuste meme si la bataille se termine au cast.)"""
    d = waaagh
    if not d["live_appeared"]:
        pytest.skip("cast live n'a spawn aucun Ork Boy (aucune tuile libre adjacente)")
    assert len(d["res"]["spawned"]) == len(d["live_appeared"]), (
        f"port {len(d['res']['spawned'])} Ork Boyz != live {len(d['live_appeared'])}")
    base = int((__import__("gameconfig").ability("Waaagh")["constants"])["nrOfSummons"])
    assert len(d["live_appeared"]) == base, (
        f"live a summon {len(d['live_appeared'])} Ork Boyz != nrOfSummons {base}")


def test_waaagh_summon_stats_bit_exact_vs_live(waaagh):
    """`SpawnUnitOptions.WithStatsFromConfig` : PV du summon = `summonHp[level] x mult` — confronte la
    SOURCE (formule config), pas une constante figee. `changes.appeared.hpAfter` = PV a l'apparition."""
    d = waaagh
    if not d["live_appeared"]:
        pytest.skip("pas d'Ork Boy live")
    from engine.runner.components import StatsComponent
    sc = d["state"].get_entity(d["caster_id"]).get_component(StatsComponent)
    ctx = sc.ctx if sc is not None else None
    lvl = getattr(ctx, "active_ability_level", None)
    mult = int(getattr(ctx, "ability_variables_multiplier", 100) or 100)
    expected = ability_var("Waaagh", "summonHp", lvl, multiplier_pct=mult)
    live_hp = {ch.get("hpAfter") for ch in d["live_appeared"]}
    assert live_hp == {expected}, f"live hp a l'apparition {live_hp} != formule config {expected}"
    for gid in d["res"]["spawned"]:
        hc = d["state"].get_entity(gid).get_component(HealthComponent)
        assert hc.hp_max == expected, f"port hp_max {hc.hp_max} != {expected}"


def test_waaagh_buff_effects_posed_live_and_port(waaagh):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$GetBuffBehaviour` : les 3 effets (1099 ExtraMovement / 1100 ExtraDamage /
    1101 ExtraHits) sont poses sur le caster LIVE **et** par le port (le selecteur inclut le caster).

    ⚠ Le volet LIVE est CONDITIONNEL **par necessite** : dans CE scenario (roster a 1-2 unites) le cast
    epuise les activations du camp -> le tour bascule -> le TICK de fin de tour passe et les 3 buffs
    (`Direct(1)` = 1 TOUR) ont DEJA expire quand `decisionView` est relu (mesure #95 : « effects [] »
    sur TOUTES les unites, caster compris). Le volet live INCONDITIONNEL vit dans
    `test_waaagh_buff_contrib_live.py`, qui garde le tour OUVERT avec une 4e unite jamais activee
    (mesure #506 : **7 passed** -- les buffs SONT bien poses live, ce fichier-ci ne le re-mesure pas).

    #506 -- LA CONDITION ETAIT UN PROXY, ET LE PROXY A LACHE. Elle s'ecrivait `if live_effects:`,
    c.-a-d. « le caster porte au moins un effet », ce qui ne valait QUE tant que le seul effet
    possible etait un buff Waaagh. Depuis `c4be3896` (#419-r6, le defaut passe a << equiper >>) la
    cible SURVIT au cast, `decisionView` publie encore le caster, et celui-ci porte un effet TIERS
    (`BigTarget_AdjacentEffect`, qui n'expire pas) : la condition devenait vraie dans le regime
    qu'elle etait ecrite pour EXCLURE, et l'assertion mordait sur un tour deja tique.

    La condition est desormais **MESUREE** sur l'etat live, pas devinee : le tour du caster est-il
    encore OUVERT (`dv1.currentPlayer == owner du caster`) ? Et les DEUX branches assertionnent --
    tour ouvert => les 3 buffs sont la ; tour tique => ils n'y sont PLUS, ce qui est exactement la
    duree `Direct(1)` mesuree en #95. Aucune branche n'est vide."""
    d = waaagh
    from engine.entities.effect_type import EffectType
    want = {"Waaagh_ExtraMovement", "Waaagh_ExtraDamage", "Waaagh_ExtraHits"}
    st = d["state"]
    port_names = set()
    if st.effects is not None:
        for ef in (st.effects.by_unit.get(d["caster_id"]) or []):
            port_names.add(getattr(ef, "name", None) or "")
    assert want <= port_names, f"port : effets sur le caster {sorted(port_names)} ne couvre pas {sorted(want)}"
    dv1 = d.get("dv1") or {}
    me1 = next((u for u in (dv1.get("units") or []) if u.get("id") == d["caster_id"]), None)
    if me1 is None:
        return                       # bataille terminee au cast : `decisionView` ne publie plus rien
    if dv1.get("currentPlayer") == me1.get("owner"):
        assert want <= d["live_effects"], (
            "live, TOUR ENCORE OUVERT : effets sur le caster %s ne couvre pas %s"
            % (sorted(d["live_effects"]), sorted(want)))
    else:
        assert not (want & d["live_effects"]), (
            "live, tour DEJA TIQUE : les buffs `Direct(1)` %s devraient avoir expire, effets = %s"
            % (sorted(want & d["live_effects"]), sorted(d["live_effects"])))


def test_waaagh_move_range_uses_effect_not_double_count(waaagh):
    """`IdunBattleLogic.Entities.DSLFormulas$$UnitMovementRangeWithBonus` = `If(HasEffect(caster,1099), StatAmount(MOVEMENT),
    Sum(StatAmount(MOVEMENT), bonus))` -> ANTI-DOUBLE-COMPTE : comme le buff 1099 est pose AVANT
    l'etage move, la portee resolue == MOVEMENT courant (deja +extraMovement), PAS MOVEMENT+2x."""
    d = waaagh
    from engine.runner.components import StatsComponent
    from engine.entities.stats import StatType
    sc = d["state"].get_entity(d["caster_id"]).get_component(StatsComponent)
    mv_after = int(sc.ctx.stats.get_stat(int(StatType.MOVEMENT), 0))
    extra = int(ability_var("Waaagh", "extraMovement", is_constant=True) or 0)
    assert d["res"]["move_range"] == mv_after, (
        f"move_range {d['res']['move_range']} != MOVEMENT post-buff {mv_after} "
        f"(double-comptage de +{extra} ?)")


def test_waaagh_perform_ai_action_selects_board_wide(waaagh):
    """`PerformAIAction(Friends(UnitsWithVisualId(VisualUnitIdFromUnitId(unitId), 1)), 1, 1)` : le
    selecteur est BOARD-WIDE -> TOUS les Ork Boyz allies sont pousses a agir (au moins ceux qui viennent
    d'etre invoques)."""
    d = waaagh
    if not d["res"]["spawned"]:
        pytest.skip("port n'a spawn aucun Ork Boy")
    ai = set(d["res"]["ai_units"] or [])
    assert ai, "PerformAIAction n'a selectionne AUCUNE unite (UnitsWithVisualId vide ?)"
    assert set(d["res"]["spawned"]) <= ai, (
        f"les Ork Boyz spawnes {d['res']['spawned']} ne sont pas tous dans ai_units {sorted(ai)}")


def test_waaagh_fresh_summons_act_live_and_port(waaagh):
    """DISCRIMINANT : un Ork Boy tout juste invoque a QUITTE l'anneau de spawn (dist >= 2 de la position
    du caster AU MOMENT DU SPAWN) -> il a joue une action AI alors qu'il venait d'etre pose. Confronte
    live ET port. (Le spawn precede le MOVE du caster : l'anneau de reference est la position INITIALE.)"""
    d = waaagh
    if not d["live_appeared"] or not d["res"]["spawned"]:
        pytest.skip("pas d'Ork Boy (live ou port)")
    live_d = [hexgeo.distance((ch["to"]["col"], ch["to"]["row"]), d["caster_pos"])
              for ch in d["live_appeared"] if ch.get("to")]
    port_d = []
    for gid in d["res"]["spawned"]:
        pc = d["state"].get_entity(gid).get_component(PositionComponent)
        if pc is not None:
            port_d.append(hexgeo.distance((pc.col, pc.row), d["caster_pos"]))
    assert live_d and port_d
    if max(live_d) < 2:
        pytest.skip(f"live : aucun Ork Boy n'a quitte l'anneau (dists={live_d}) -> pas de discriminant")
    assert max(port_d) >= 2, f"port : aucun Ork Boy n'a quitte l'anneau (dists={port_d})"


def test_waaagh_fresh_summons_get_no_activation_live_and_port(waaagh):
    """#291 -- `IdunBattle.Entities.Behaviours.SpawnUnitBehaviour$$TriggerSpawnedUnitBehaviours`
    TERMINE le tour de l'unite qui apparait pendant le tour de son proprietaire
    (`IOperationProcessor` slot 0x23 = `FinishUnitTurn(spawned, isTerminated: true)`), et
    `FinishUnitTurnOperation$$Execute` enchaine sur le slot 0x76 = `MarkUnitAsNoActionAvailable`.

    LIVE   : le summon frais est donc ABSENT de `decisionView.toActivate` (qui filtre exactement sur
             `IsControlledByCurrentPlayer && IsAlive && HasActionLeft`) -- il n'obtient JAMAIS
             d'activation au tour de son apparition. Ce n'est pas un trou de harnais, c'est le natif.
    PORT   : le summon spawne porte `TURN_FINISHED` ET `TURN_FINISHED_FORCED` (`isTerminated=true`).
    CONTRE-EPREUVE (sinon l'assertion serait triviale) : le caster, lui, EST connu de `toActivate`
    AVANT son cast -- la liste n'est donc pas vide par construction."""
    from engine.runner.components import UnitFlagsComponent
    d = waaagh
    if not d["res"]["spawned"]:
        pytest.skip("port n'a spawn aucun Ork Boy")
    # -- contre-epreuve : la liste PRE-cast n'est pas vide et contient le caster --
    assert d["caster_id"] in (d["dv0"].get("toActivate") or []), (
        "montage : le caster doit etre activable AVANT son cast (sinon `toActivate` ne mesure rien)")
    # -- LIVE : aucun summon frais n'est activable --
    live_ids = [u["id"] for u in (d["live_new"] or [])]
    if live_ids:
        acti = set(d["dv1"].get("toActivate") or [])
        assert not (set(live_ids) & acti), (
            f"live : un summon frais est dans toActivate ({sorted(set(live_ids) & acti)}) -- "
            f"le FinishUnitTurn(spawned, terminated) natif n'aurait pas eu lieu")
    # -- PORT : les flags de tour du finish forced sont poses --
    for gid in d["res"]["spawned"]:
        fl = d["state"].get_entity(gid).get_component(UnitFlagsComponent)
        assert fl is not None and fl.has(UnitFlagsComponent.TURN_FINISHED), (
            f"port : le summon {gid} n'a pas TURN_FINISHED (TriggerSpawnedUnitBehaviours non porte)")
        assert fl.has(UnitFlagsComponent.TURN_FINISHED_FORCED), (
            f"port : le summon {gid} n'a pas TURN_FINISHED_FORCED (isTerminated=true non porte)")


def test_waaagh_summons_rejoin_automatic_pass_next_turn(waaagh):
    """#291, GENERALISATION -- le finish-turn de l'apparition ne doit PAS figer le summon : il le sort
    de la passe automatique du tour COURANT (`PlayAutomaticUnitsOperation$$Execute` gate sur
    `!HasFlag(u, 3 = TurnFinished)`) et l'y REMET au tour SUIVANT, parce que
    `StartTurnOperation$$Execute` appelle `RemoveTurnFlags(includeNoAction=0, newActivation=1)` sur
    les unites du joueur entrant AVANT le slot 0x71 `PlayAutomaticUnits`.

    C'est le scenario qui CASSERAIT le port si le gate etait pose sans son reset : les summons ne
    joueraient plus jamais. On mesure les DEUX etats successifs sur le meme `State`, en faisant
    tourner le VRAI turn-flow (`EndTurnOperation` x2 -> retour au joueur)."""
    from engine.runner.operations.summon_ai import collect_ai_controlled
    from engine.runner.operations.turnflow import EndTurnOperation
    d = waaagh
    if not d["res"]["spawned"]:
        pytest.skip("port n'a spawn aucun Ork Boy")
    st = d["state"]
    e0 = st.get_entity(d["res"]["spawned"][0])
    player = e0.get_component(__import__(
        "engine.runner.components", fromlist=["OwnerComponent"]).OwnerComponent).player
    spawned = set(d["res"]["spawned"])
    # AVANT : le tour du proprietaire n'a pas change -> les summons sont TurnFinished, donc HORS
    # de la passe automatique (c'est le natif : ils viennent d'agir via `PerformAIAction`).
    assert not (spawned & set(collect_ai_controlled(st, player))), (
        "un summon fraichement apparu ne doit PAS etre repris par la passe automatique du MEME tour")
    # ... puis on fait reellement tourner le turn-flow jusqu'au retour du joueur.
    EndTurnOperation.execute(st, advance=True)          # joueur -> adverse (StartTurn adverse)
    EndTurnOperation.execute(st, advance=True)          # adverse -> joueur (StartTurn joueur)
    assert st.current_player_id == player, "montage : le tour n'est pas revenu au proprietaire"
    alive = {g for g in spawned
             if (st.get_entity(g) is not None
                 and st.get_entity(g).get_component(UnitComponent) is not None
                 and st.get_entity(g).get_component(UnitComponent).alive)}
    if not alive:
        pytest.skip("aucun summon survivant apres deux fins de tour")
    assert alive & set(collect_ai_controlled(st, player)), (
        "APRES le turn-start du proprietaire, les summons vivants doivent RE-ENTRER dans la passe "
        "automatique (sinon le gate TurnFinished les fige definitivement)")


def test_spawn_finish_turn_gate_spares_steppable(waaagh):
    """#291, CONTRE-CAS du GATE -- `TriggerSpawnedUnitBehaviours` ne termine PAS le tour d'une unite
    portant `UnitTrait.Steppable`(27) : le decompile lit
    `HasTrait(u, 0x1b) ? false : !HasTrait(u, 0x10 = Hero)`. Sans ce contre-cas, « le summon est
    finish-turn » ne prouverait pas que le port porte le GATE plutot qu'un finish inconditionnel.
    Le token decoy (`genesSmnDecoy`, traits `Steppable`+`Decoy`) passe par le MEME choke point."""
    from engine.runner.components import UnitFlagsComponent, PositionComponent as _PC
    from engine.runner.operations.spawn import spawn_decoy
    d = waaagh
    st = d["fresh"]()
    if st.board is None:
        pytest.skip("pas de board dans l'etat rejoue")
    occupied = {(pc.col, pc.row) for e in st.entities.values()
                for pc in [e.get_component(_PC)] if pc is not None}
    tile = next((tid for tid, t in st.board.by_id.items()
                 if (t["col"], t["row"]) not in occupied), None)
    if tile is None:
        pytest.skip("aucune tuile libre pour poser le decoy")
    did = spawn_decoy(st, tile, d["caster_id"])
    assert did is not None, "montage : le decoy n'a pas ete pose"
    fl = st.get_entity(did).get_component(UnitFlagsComponent)
    assert fl is None or not fl.has(UnitFlagsComponent.TURN_FINISHED), (
        "un Steppable ne doit PAS etre finish-turn a l'apparition (gate HasTrait(0x1b) non porte)")


def test_waaagh_counter_case_without_perform_ai_action(waaagh):
    """CONTRE-CAS : MEME etat-avant, MEME arbre de spawn, SANS `PerformAIAction` -> TOUS les Ork Boyz
    restent a distance 1. Sans ce contraste, « il a bouge » ne prouve rien."""
    from engine.dsl.effects import ExecutionContext
    from engine.runner.abilities.orks import waaagh_spawn_tree
    from engine.runner.abilities.behaviours.context import entities_from_state
    d = waaagh
    if not d["res"]["spawned"]:
        pytest.skip("port n'a spawn aucun Ork Boy")
    st = d["fresh"]()
    ectx = ExecutionContext(state=st, rng=st.rng)
    waaagh_spawn_tree(d["res"]["count"]).execute(
        entities_from_state(st, d["caster_id"], d["enemy_id"]), ectx)
    spawned = [p["unit"] for n, p in ectx.emitted if n == "SpawnUnit"]
    assert spawned, "contre-cas : aucun spawn"
    dists = []
    for gid in spawned:
        pc = st.get_entity(gid).get_component(PositionComponent)
        if pc is not None:
            dists.append(hexgeo.distance((pc.col, pc.row), d["caster_pos"]))
    assert dists and max(dists) == 1, (
        f"contre-cas : un Ork Boy a bouge SANS PerformAIAction (dists={dists})")


# ============================================================================================== #
# SendInTheNextWave (1016, astraYarrick) — Spawn + on-appearance UseNormalAttackIfAble
# ============================================================================================== #

SITNW_CASTER = "astraYarrick"
SITNW_ENEMY = "necroWarden"
GUARD_VIS = {"astraSmnGuardsman", "astraNpc1Guardsman"}


@pytest.fixture(scope="session")
def sitnw(rpc, build_runner):
    from engine.runner.abilities.astramilitarum import SendInTheNextWaveAbility
    rid = build_runner("31337", extra=["--p-units", SITNW_CASTER,
                                       "--a-units", f"{SITNW_ENEMY},necroDestroyer"])["rid"]
    board = _board(rpc, rid)
    c, tid = _drive_until_castable(rpc, rid, SITNW_CASTER, SITNW_ENEMY, 1016, max_dist=2)
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    tgt = next(u for u in dv["units"] if u["id"] == tid)
    d = _cast_and_replay(rpc, rid, board, c["id"], tid, 1016, SendInTheNextWaveAbility, GUARD_VIS)
    d.update({"rid": rid, "caster_id": c["id"], "enemy_id": tid, "enemy_pos": _upos(tgt)})
    return d


def test_sitnw_count_matches_live(sitnw):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.SendInTheNextWaveAbility$$GetNumSummons` = `Min(nrOfSummons + Count(allies morts), maxSummons[level])`.
    Sans perte alliee -> nrOfSummons = 2 ; le port et le natif spawnent le MEME nombre."""
    d = sitnw
    if not d["live_summons"]:
        pytest.skip("cast live n'a spawn aucun Cadian")
    assert len(d["res"]["spawned"]) == len(d["live_summons"]), (
        f"port {len(d['res']['spawned'])} Cadians != live {len(d['live_summons'])} "
        f"(count resolu={d['res']['count']})")


def test_sitnw_spawn_within_range_of_target(sitnw):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.SendInTheNextWaveAbility$$GetSpawnTilesSelector` : les Cadians apparaissent dans le disque de rayon
    `GetSpawnedUnitRange`=2 autour de la CIBLE (live et port)."""
    d = sitnw
    if not d["live_summons"]:
        pytest.skip("pas de Cadian live")
    for u in d["live_summons"]:
        p = _upos(u)
        if p[0] is None:
            continue
        assert hexgeo.distance(p, d["enemy_pos"]) <= 2, (
            f"live : Cadian en {p} a dist {hexgeo.distance(p, d['enemy_pos'])} > 2 de la cible")
    for gid in d["res"]["spawned"]:
        pc = d["state"].get_entity(gid).get_component(PositionComponent)
        assert pc is not None and hexgeo.distance((pc.col, pc.row), d["enemy_pos"]) <= 2, (
            f"port : Cadian hors du rayon 2 de la cible")


def test_sitnw_on_appearance_attack(sitnw):
    """`SpawnUnitOptions+0x18 = UseNormalAttackIfAble(activeTarget@0x180, target@0x178)` : chaque Cadian
    tire sur la CIBLE a son apparition -> la cible perd des PV PENDANT le cast, live ET port.
    (Existence de l'attaque confrontee, pas le scalaire : le montant depend du tirage RNG.)"""
    d = sitnw
    if not d["live_summons"]:
        pytest.skip("pas de Cadian live")
    if d["live_tgt_delta"] <= 0:
        pytest.skip("live : la cible n'a pas perdu de PV (hors de portee des Cadians ?)")
    assert d["res"]["attacks"], "port : aucun UseActiveAbility on-appearance emis"
    assert d["port_tgt_delta"] > 0, (
        f"live : cible -{d['live_tgt_delta']} PV ; port : -{d['port_tgt_delta']} -> l'on-appearance "
        f"portee ne deale pas")


def test_sitnw_on_appearance_precedes_finish_turn(sitnw):
    """#291, GENERALISATION sur la branche `on_appearance` -- autre summoner (`astraYarrick`), autre
    ability (1016), autre seed, et surtout autre BRANCHE du port : quand `SpawnUnitOptions+0x18`
    porte un sous-behaviour, `TriggerSpawnedUnitBehaviours` l'execute D'ABORD et n'appelle
    `FinishUnitTurn(spawned, isTerminated: true)` qu'ENSUITE. Les deux doivent donc COEXISTER :
    l'attaque on-appearance a bien eu lieu (garde `test_sitnw_on_appearance_attack`) ET les Cadians
    portent les flags de fin de tour. Un port qui aurait pose le finish AVANT ne serait pas distinguable
    ici (aucun consommateur offline de `TURN_FINISHED` sur ce chemin) -- ce test garde l'invariant
    OBSERVABLE : les deux effets sont presents, cote live comme cote port."""
    from engine.runner.components import UnitFlagsComponent
    d = sitnw
    if not d["res"]["spawned"]:
        pytest.skip("port n'a spawn aucun Cadian")
    live_ids = [u["id"] for u in (d["live_new"] or [])]
    if live_ids:
        acti = set(d["dv1"].get("toActivate") or [])
        assert not (set(live_ids) & acti), (
            f"live : un Cadian frais est dans toActivate ({sorted(set(live_ids) & acti)})")
    for gid in d["res"]["spawned"]:
        fl = d["state"].get_entity(gid).get_component(UnitFlagsComponent)
        assert fl is not None and fl.has(UnitFlagsComponent.TURN_FINISHED_FORCED), (
            f"port : le Cadian {gid} n'a pas TURN_FINISHED_FORCED apres son on-appearance")


# ============================================================================================== #
# Incursion (1021, blackPossession) — ChainBehaviour + on-appearance UseNormalAttackIfAble
# ============================================================================================== #

INC_CASTER = "blackPossession"
INC_ENEMY = "necroWarden"
BLOOD_VIS = {"blackSmnBloodletter"}


@pytest.fixture(scope="session")
def incursion(rpc, build_runner):
    from engine.runner.abilities.blacklegion import IncursionAbility
    rid = build_runner("1357", extra=["--p-units", INC_CASTER,
                                      "--a-units", f"{INC_ENEMY},necroDestroyer"])["rid"]
    board = _board(rpc, rid)
    c, tid = _drive_until_castable(rpc, rid, INC_CASTER, INC_ENEMY, 1021, max_dist=2)
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    tgt = next(u for u in dv["units"] if u["id"] == tid)
    d = _cast_and_replay(rpc, rid, board, c["id"], tid, 1021, IncursionAbility, BLOOD_VIS)
    d.update({"rid": rid, "caster_id": c["id"], "enemy_id": tid, "enemy_pos": _upos(tgt)})
    return d


def test_incursion_chain_bounded_and_adjacent(incursion):
    """`ChainBehaviour(Direct(maxSummons=6), Spawn(ActiveTarget@0x180))` avec
    `IdunBattleLogic.Entities.Abilities.Active.Loki.IncursionAbility$$GetNextSpawnTile` = 1 tuile LIBRE ADJACENTE a la cible par iteration : le port invoque
    entre 1 et 6 Bloodletters, TOUS adjacents a la cible, et pas plus que le nombre d'hex libres."""
    d = incursion
    n_port = len(d["res"]["spawned"])
    assert n_port <= d["res"]["max_summons"], (
        f"port {n_port} Bloodletters > maxSummons {d['res']['max_summons']} (chaine non bornee)")
    for gid in d["res"]["spawned"]:
        pc = d["state"].get_entity(gid).get_component(PositionComponent)
        assert pc is not None and hexgeo.distance((pc.col, pc.row), d["enemy_pos"]) == 1, (
            "port : Bloodletter non adjacent a la cible (AdjacentTiles(target))")


def test_incursion_count_matches_live(incursion):
    """Nombre de Bloodletters : port == live (meme geometrie d'hex libres autour de la cible,
    meme borne `maxSummons`, meme condition de continuation)."""
    d = incursion
    if not d["live_summons"]:
        pytest.skip("cast live n'a spawn aucun Bloodletter")
    assert len(d["res"]["spawned"]) == len(d["live_summons"]), (
        f"port {len(d['res']['spawned'])} != live {len(d['live_summons'])} Bloodletters")


def test_incursion_on_appearance_attack(incursion):
    """On-appearance `UseNormalAttackIfAble(activeTarget, cible)` : la cible encaisse pendant le cast."""
    d = incursion
    if d["live_tgt_delta"] <= 0:
        pytest.skip("live : la cible n'a pas perdu de PV")
    assert d["res"]["attacks"], "port : aucun UseActiveAbility on-appearance"
    assert d["port_tgt_delta"] > 0, (
        f"live -{d['live_tgt_delta']} PV ; port -{d['port_tgt_delta']}")


def test_incursion_chain_stops_when_target_dead(incursion):
    """CONTRE-CAS de la CONDITION DE CONTINUATION (`IdunBattleLogic.Entities.Abilities.Active.Loki.IncursionAbility$$GetContinueTrigger` :
    `IsAlive(caster) & IsAlive(target) & IsInRange(caster, target, range)`) : si la cible est DEJA morte
    a l'entree, la chaine ne fait AUCUNE iteration -> 0 spawn. Sans ce contraste, la boucle bornee ne
    prouve pas la re-evaluation par-iteration."""
    from engine.runner.abilities.blacklegion import IncursionAbility
    d = incursion
    st = d["fresh"]()
    tgt = st.get_entity(d["enemy_id"])
    tgt.get_component(UnitComponent).alive = False
    tgt.get_component(HealthComponent).hp = 0
    res = IncursionAbility().execute_behaviour(st, d["caster_id"], d["enemy_id"])
    assert not res["spawned"], (
        f"cible morte : la chaine a quand meme invoque {res['spawned']} -> GetContinueTrigger inerte")


def test_incursion_chain_stops_out_of_range(incursion):
    """MEME contre-cas sur le volet PORTEE : caster teleporte loin (> `range`=2 de la cible) ->
    `IsInRange` faux -> 0 spawn."""
    from engine.runner.abilities.blacklegion import IncursionAbility
    d = incursion
    st = d["fresh"]()
    board = st.board
    tp = st.get_entity(d["enemy_id"]).get_component(PositionComponent)
    far = None
    occ = {(e.get_component(PositionComponent).col, e.get_component(PositionComponent).row)
           for e in st.entities.values() if e.get_component(PositionComponent) is not None}
    for p in hexgeo.disk(tp.col, tp.row, 8):
        t = board.id_at(p[0], p[1])
        if t is None or p in occ or not board.walkable(t):
            continue
        if hexgeo.distance(p, (tp.col, tp.row)) >= 4:
            far = p
            break
    if far is None:
        pytest.skip("aucune tuile libre a dist >= 4 de la cible sur ce board")
    cpc = st.get_entity(d["caster_id"]).get_component(PositionComponent)
    cpc.col, cpc.row = far
    res = IncursionAbility().execute_behaviour(st, d["caster_id"], d["enemy_id"])
    assert not res["spawned"], (
        f"caster hors portee : la chaine a quand meme invoque {res['spawned']} -> IsInRange inerte")


# ============================================================================================== #
# Poxwalkers (1040, deathBlightbringer) — self-cast, count RandomAmount/100, on-appearance PerformAIAttack
# ============================================================================================== #

POX_CASTER = "deathBlightbringer"
POX_ENEMY = "necroWarden"
POX_VIS = {"deathPoxwalker"}


@pytest.fixture(scope="session")
def poxwalkers(rpc, build_runner):
    from engine.runner.abilities.deathguard import SpawnPoxwalkersAbility
    rid = build_runner("2468", extra=["--p-units", POX_CASTER,
                                      "--a-units", f"{POX_ENEMY},necroDestroyer"])["rid"]
    board = _board(rpc, rid)
    c, tid = _drive_until_castable(rpc, rid, POX_CASTER, POX_ENEMY, 1040, max_dist=3)
    d = _cast_and_replay(rpc, rid, board, c["id"], tid, 1040, SpawnPoxwalkersAbility, POX_VIS)
    d.update({"rid": rid, "caster_id": c["id"], "caster_pos": _upos(c), "enemy_id": tid})
    return d


def test_poxwalkers_radius_from_turns_started(poxwalkers):
    """`IdunBattle.Entities.Effects.Loki.ContagionsOfNurgle_ArmorReduction_Effect$$CalculateRange` : rayon = 1 si
    TurnsStarted <= 2, 2 si 3..4, 3 si >= 5. Le port lit la MEME stat (0xc) du caster."""
    from engine.runner.components import StatsComponent
    from engine.entities.stats import StatType
    d = poxwalkers
    sc = d["state"].get_entity(d["caster_id"]).get_component(StatsComponent)
    ts = int(sc.ctx.stats.get_stat(int(StatType.TURNS_STARTED), 0))
    want = 1 if ts <= 2 else (2 if ts <= 4 else 3)
    assert d["res"]["radius"] == want, f"radius {d['res']['radius']} != {want} (TurnsStarted={ts})"


def test_poxwalkers_count_in_config_band(poxwalkers):
    """`Divide(RandomAmount(n*chance, n*chance_2), 100, Ceiling)` : le nombre invoque (port ET live) est
    dans la BANDE config [ceil(n*chance/100), ceil(n*chance_2/100)] ou n = nb d'hex libres du rayon.
    On confronte la BANDE, pas un scalaire (le tirage RNG n'est pas cale bit-a-bit)."""
    from math import ceil
    from engine.runner.components import StatsComponent
    from engine.runner.abilities.deathguard import poxwalkers_spawn_tiles
    d = poxwalkers
    st = d["fresh"]()
    n_tiles = len(poxwalkers_spawn_tiles(st, d["caster_id"], d["res"]["radius"]))
    if n_tiles == 0:
        pytest.skip("aucune tuile libre autour du caster")
    sc = st.get_entity(d["caster_id"]).get_component(StatsComponent)
    lvl = getattr(sc.ctx, "active_ability_level", None)
    mult = int(getattr(sc.ctx, "ability_variables_multiplier", 100) or 100)
    lo = ceil(n_tiles * int(ability_var("Poxwalkers", "chance", lvl, multiplier_pct=mult)) / 100)
    hi = ceil(n_tiles * int(ability_var("Poxwalkers", "chance_2", lvl, multiplier_pct=mult)) / 100)
    assert lo <= d["res"]["count"] <= hi, (
        f"port count {d['res']['count']} hors bande [{lo},{hi}] (n_tiles={n_tiles})")
    if d["live_summons"]:
        assert lo <= len(d["live_summons"]) <= hi, (
            f"live {len(d['live_summons'])} Poxwalkers hors bande [{lo},{hi}] -> formule de count fausse")


def test_poxwalkers_spawn_within_radius(poxwalkers):
    """Les Poxwalkers apparaissent dans le disque `radius` autour du CASTER (self-cast)."""
    d = poxwalkers
    for gid in d["res"]["spawned"]:
        pc = d["state"].get_entity(gid).get_component(PositionComponent)
        assert pc is not None and hexgeo.distance((pc.col, pc.row), d["caster_pos"]) <= d["res"]["radius"]
    for u in d["live_summons"]:
        p = _upos(u)
        if p[0] is not None:
            assert hexgeo.distance(p, d["caster_pos"]) <= d["res"]["radius"], (
                f"live : Poxwalker en {p} hors du rayon {d['res']['radius']}")


def test_poxwalkers_on_appearance_perform_ai_attack(poxwalkers):
    """`SpawnUnitOptions+0x18 = PerformAIAttackFromCurrentPosition(activeTarget@0x180)` : la feuille
    `PerformAIAttack` est bien fire PAR summon (domaine UNITE via ActiveTarget)."""
    d = poxwalkers
    if not d["res"]["spawned"]:
        pytest.skip("port n'a spawn aucun Poxwalker")
    assert len(d["res"]["attacks"]) == len(d["res"]["spawned"]), (
        f"port : {len(d['res']['attacks'])} PerformAIAttack pour {len(d['res']['spawned'])} summons "
        f"-> le sous-behaviour on-appearance n'est pas fire par summon")


# ============================================================================================== #
# GENERALISATION ? scenarios CRAFTES qui n'ont PAS servi a construire le port.
# ============================================================================================== #

@pytest.fixture(scope="session")
def waaagh_ally(rpc, build_runner):
    """Board + roster DIFFERENTS (`_summon_montage.waaagh_ally_scenario`) : le Warboss + un allie ORK
    (orksNob). Il doit etre BUFFE (meme faction -> `UnitsFromFaction(Friends, Orks)`) mais PAS pousse
    a agir (le selecteur de `PerformAIAction` filtre sur le visualId `orksOrkBoys` via
    `UnitsWithVisualId`)."""
    return waaagh_ally_scenario(rpc, build_runner)


def test_waaagh_ork_ally_is_buffed_not_forced_to_act(waaagh_ally):
    """GENERALISATION (board C3_01, roster a 2 heros) : l'allie ORK est BUFFE (il est dans
    `UnitsFromFaction(Friends(@0x80), Orks)` du selecteur de `GetBuffBehaviour`) mais PAS selectionne par
    `PerformAIAction` (dont le selecteur `UnitsWithVisualId(VisualUnitIdFromUnitId(unitId))` ne retient
    que les `orksOrkBoys`). Discrimine les DEUX selecteurs, qui sont differents."""
    d = waaagh_ally
    want = {"Waaagh_ExtraMovement", "Waaagh_ExtraDamage", "Waaagh_ExtraHits"}
    st = d["state"]
    port_ally_eff = {getattr(ef, "name", None) or ""
                     for ef in (st.effects.by_unit.get(d["ally_id"]) or [])} if st.effects else set()
    assert want <= port_ally_eff, (
        f"port : l'allie Ork n'est PAS buffe ({sorted(port_ally_eff)}) -> UnitsFromFaction(Orks) KO")
    assert d["ally_id"] not in (d["res"]["ai_units"] or []), (
        f"port : l'allie Ork {d['ally_id']} est dans ai_units {d['res']['ai_units']} -> le filtre "
        f"UnitsWithVisualId ne s'applique pas")
    # ⚠ CONDITIONNEL par necessite (cf. test_waaagh_buff_effects_posed_live_and_port) : ici le cast
    # epuise le camp -> bascule de tour -> tick -> les buffs `Direct(1)` ont deja expire a la relecture.
    # Le volet live INCONDITIONNEL (allie Ork a 9 hex, buffe) est dans test_waaagh_buff_contrib_live.py.
    if d["ally_effects"]:
        assert want <= d["ally_effects"], (
            f"live : l'allie Ork n'est pas buffe ({sorted(d['ally_effects'])})")


def test_waaagh_summon_movement_stat_matches_live(waaagh_ally):
    """GRANDEUR, pas geometrie : la stat MOVEMENT d'un Ork Boy PORTE == le `movement` du MEME summon
    cote NATIF (`combatSnapshot` POST-cast).

    `IdunBattle.Entities.Behaviours.SpawnUnitBehaviour$$GetStatsToOverride` ne rend qu'une LISTE de
    `StatModifier` (les deux listes `options+0x20` litterales et `options+0x28` (statType, IAmount)
    evaluees) : c'est un override PARTIEL applique SUR l'unite deja construite depuis sa
    `UnitConfiguration`. Aucune ability de summon ne porte de var `summonMovement` -> le Movement du
    summon est celui de SA CONFIG, plus les modificateurs d'effet. Ici l'etage BUFF pose
    `Waaagh_ExtraMovement` (1099, +1) sur tous les allies de faction Orks, Ork Boyz compris :
    le natif publie donc `movement = base + 1` avec `statDelta.movement = 1`.

    Ce test est INDEPENDANT de la geometrie (aucun skip conditionne a la disposition des unites) :
    il confronte directement la valeur que le port doit reproduire."""
    from engine.runner.components import StatsComponent
    from engine.entities.stats import StatType
    d = waaagh_ally
    if not d["live_summons"] or not d["res"]["spawned"]:
        pytest.skip("pas d'Ork Boy (live ou port)")
    live_mv = {d["live_new_stats"].get(u["id"], {}).get("movement")
               for u in d["live_summons"]} - {None}
    if not live_mv:
        pytest.skip("combatSnapshot ne publie pas `movement` pour les summons frais")
    port_mv = set()
    for gid in d["res"]["spawned"]:
        sc = d["state"].get_entity(gid).get_component(StatsComponent)
        assert sc is not None, f"port : Ork Boy {gid} sans StatsComponent"
        port_mv.add(int(sc.ctx.get_stat(int(StatType.MOVEMENT))))
    assert port_mv == live_mv, (
        f"port MOVEMENT {sorted(port_mv)} != natif movement {sorted(live_mv)} -- la stat de "
        f"deplacement du summon n'est pas seedee depuis sa config (base + modificateurs d'effet)")
    assert min(port_mv) > 1, (
        f"port MOVEMENT {sorted(port_mv)} <= 1 : le summon ne porte que le BONUS d'effet, pas sa "
        f"base de config")


def test_waaagh_summons_leave_spawn_ring_alt_board(waaagh_ally):
    """GENERALISATION du discriminant de deplacement sur le montage ALTERNATIF (board C3_01, seed
    777, roster a 2 heros -- aucun des trois n'a servi a construire le port) : les Ork Boyz frais
    quittent l'anneau de spawn LIVE **et** PORT.

    Deux mesures, la seconde etant celle que la geometrie ne peut pas offrir gratuitement :
      * distance finale au caster >= 2 (les tuiles de spawn sont des hex ADJACENTS au caster) ;
      * DISTANCE PARCOURUE > 1 depuis la tuile d'APPARITION (`port_spawn_positions`) -- un summon
        dont la portee de deplacement serait tombee a 1 ne peut pas la franchir."""
    d = waaagh_ally
    if not d["live_appeared"] or not d["res"]["spawned"]:
        pytest.skip("pas d'Ork Boy (live ou port)")
    live_d = [hexgeo.distance((ch["to"]["col"], ch["to"]["row"]), d["caster_pos"])
              for ch in d["live_appeared"] if ch.get("to")]
    if not live_d or max(live_d) < 2:
        pytest.skip(f"live : aucun Ork Boy n'a quitte l'anneau (dists={live_d}) -> pas de discriminant")
    spawn_pos = port_spawn_positions(d)
    port_d, travelled = [], []
    for gid in d["res"]["spawned"]:
        pc = d["state"].get_entity(gid).get_component(PositionComponent)
        if pc is None:
            continue
        port_d.append(hexgeo.distance((pc.col, pc.row), d["caster_pos"]))
        if gid in spawn_pos:
            travelled.append(hexgeo.distance(spawn_pos[gid], (pc.col, pc.row)))
    assert port_d and max(port_d) >= 2, (
        f"port : aucun Ork Boy n'a quitte l'anneau (dists={port_d}, live={live_d})")
    assert travelled and max(travelled) > 1, (
        f"port : distance PARCOURUE depuis la tuile d'apparition {travelled} <= 1 -- la portee de "
        f"deplacement du summon est tombee a 1 (spawn={spawn_pos})")


def test_waaagh_target_damage_live_and_port(waaagh):
    """L'etage ATTAQUE (`IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$GetAttackBehaviour` : `If(IsAdjacent(caster,target),
    UseActiveAbility(normal))`) + les actions AI des Ork Boyz font ENCAISSER la cible pendant le cast,
    live ET port. (Existence confrontee, pas le scalaire.)"""
    d = waaagh
    if d["live_tgt_delta"] <= 0:
        pytest.skip("live : la cible n'a pas encaisse (charge impossible ?)")
    assert d["port_tgt_delta"] > 0, (
        f"live -{d['live_tgt_delta']} PV ; port -{d['port_tgt_delta']} -> l'etage attaque/AI porte "
        f"ne deale pas")


def test_sitnw_num_summons_grows_with_dead_allies(sitnw):
    """GENERALISATION de `IdunBattleLogic.Entities.Abilities.Active.Loki.SendInTheNextWaveAbility$$GetNumSummons` (terme DYNAMIQUE non exerce par le scenario de
    construction) : `Min(nrOfSummons + Count(Attackable(Friends(AllDeadOrResurrectedUnits))),
    maxSummons[level])`. On INJECTE des allies MORTS dans l'etat-avant et on verifie que le count monte
    d'autant, PUIS qu'il PLAFONNE a `maxSummons`. (Offline : provoquer N morts amies live coute une
    bataille entiere ; la FORMULE est ici exercee sur le vrai etat runner.)"""
    from engine.runner.abilities.astramilitarum import send_in_the_next_wave_num_summons
    from engine.runner.components import OwnerComponent, StatsComponent
    import gameconfig as GC
    d = sitnw
    st = d["fresh"]()
    base = int((GC.ability("SendInTheNextWave")["constants"])["nrOfSummons"])
    assert send_in_the_next_wave_num_summons(st, d["caster_id"]) == base, (
        "etat-avant sans perte : count != nrOfSummons")
    coc = st.get_entity(d["caster_id"]).get_component(OwnerComponent)
    sc = st.get_entity(d["caster_id"]).get_component(StatsComponent)
    lvl = getattr(sc.ctx, "active_ability_level", None)
    mult = int(getattr(sc.ctx, "ability_variables_multiplier", 100) or 100)
    cap = int(ability_var("SendInTheNextWave", "maxSummons", lvl, multiplier_pct=mult))
    # injecte des cadavres ALLIES (mirror `AllDeadOrResurrectedUnits` + `Friends(owner)`)
    added = 0
    for i in range(cap + 2):
        e = st.add_entity(900000 + i)
        e.add_component(UnitComponent(visual_id="astraSmnGuardsman", alive=False))
        e.add_component(OwnerComponent(team=coc.team, player=coc.player))
        added += 1
        got = send_in_the_next_wave_num_summons(st, d["caster_id"])
        assert got == min(base + added, cap), (
            f"count {got} != min({base}+{added}, cap={cap}) -> formule GetNumSummons fausse")
    assert send_in_the_next_wave_num_summons(st, d["caster_id"]) == cap, "plafond maxSummons non applique"


def test_poxwalkers_radius_bands_offline(poxwalkers):
    """GENERALISATION de `IdunBattle.Entities.Effects.Loki.ContagionsOfNurgle_ArmorReduction_Effect$$CalculateRange` : les TROIS
    bandes (TurnsStarted <=2 -> 1 ; 3..4 -> 2 ; >=5 -> 3) exercees sur le vrai etat runner en pilotant la
    stat 0xc. Le scenario de construction n'en couvre qu'UNE."""
    from engine.runner.abilities.deathguard import contagions_of_nurgle_range
    from engine.runner.components import StatsComponent
    from engine.entities.stats import StatType
    d = poxwalkers
    st = d["fresh"]()
    stats = st.get_entity(d["caster_id"]).get_component(StatsComponent).ctx.stats
    for ts, want in ((0, 1), (1, 1), (2, 1), (3, 2), (4, 2), (5, 3), (9, 3)):
        stats.set_stat_override(int(StatType.TURNS_STARTED), ts)
        assert int(stats.get_stat(int(StatType.TURNS_STARTED), 0)) == ts, "override de stat inoperant"
        got = contagions_of_nurgle_range(st, d["caster_id"])
        assert got == want, f"TurnsStarted={ts} -> radius {got} != {want}"
