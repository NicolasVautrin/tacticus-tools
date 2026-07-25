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
Primitives : `IdunBattleLogic.Entities.DSLFactory$$UnitsWithVisualId`, `IdunBattleLogic.Entities.DSLFactory$$VisualUnitIdFromUnitId`,
  `IdunBattleLogic.Entities.DSLFactory$$ChainBehaviour`, `IdunBattleLogic.Entities.DSLFactory$$UseNormalAttackIfAble`,
  `IdunBattleLogic.Entities.DSLFactory$$PerformAIAttackFromCurrentPosition`, `IdunBattleLogic.Entities.DSLFactory$$UnitMovementRangeWithBonus`.

ASCII-only. Skip si pas de session / geometrie non cooperative.
"""
from __future__ import annotations

import pytest

import hexgeo

from engine.runner.snapshot import load_state
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.components import HealthComponent, PositionComponent, UnitComponent
from engine.entities.effects.magnitude import ability_var


def _upos(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row"))


def _board(rpc, rid):
    from engine.entities.pathfinding.board import Board
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    return Board(bg["tiles"], adjacency="evenq")


def _legal_targets(rpc, rid, uid, ability):
    """Cibles LEGALES de `ability` pour l'unite `uid`, telles que le NATIF les publie (`abilityTargets`
    -> `GetDynamicInvalidTargetReason` de la classe d'ability). C'est la SEULE porte fiable : p.ex.
    `IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$GetDynamicInvalidTargetReason` n'accepte une cible que s'il existe au moins
    une tuile de CHARGE (`GetPossibleMovementTiles` non vide) -> un simple critere de distance ne suffit
    pas (verifie live : cible a dist 2 REFUSEE, cible a dist 5 ACCEPTEE)."""
    at = rpc("abilityTargets", {"runnerId": rid}, 90)
    out = []
    for u in (at.get("units") or []):
        if u.get("unitId") != uid:
            continue
        for a in (u.get("abilities") or []):
            if a.get("abilityId") != int(ability):
                continue
            for t in (a.get("targets") or []):
                if t.get("targetId") is not None:
                    out.append(t["targetId"])
    return out


def _drive_until_castable(rpc, rid, caster_vis, enemy_vis, ability, tries=16, max_dist=None):
    """Rapproche le caster de l'ennemi, tour par tour, JUSQU'A ce que le natif publie une cible legale
    pour `ability` (et, si `max_dist` est donne, que la distance soit <= max_dist).
    Renvoie (caster_live, target_id). Skip si jamais castable.

    `max_dist` sert aux abilities dont la porte de TARGETING est PLUS LARGE que la garde d'EXECUTION :
    `IdunBattleLogic.Entities.Abilities.Active.Loki.IncursionAbility$$GetNextSpawnTile` exige `IsInRange(caster, target, range=2)` alors que
    `abilityTargets` accepte la cible bien au-dela (verifie live : cible legale a dist 5, 0 summon)."""
    for _ in range(tries):
        dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        c = next((u for u in (dv.get("units") or []) if u.get("visualId") == caster_vis), None)
        e = next((u for u in (dv.get("units") or []) if u.get("visualId") == enemy_vis), None)
        if c is None or e is None:
            pytest.skip(f"{caster_vis}/{enemy_vis} absent")
        cp, ep = _upos(c), _upos(e)
        if cp[0] is None or ep[0] is None:
            pytest.skip("positions absentes")
        if dv.get("currentPlayer") != c.get("owner"):
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            continue
        d = hexgeo.distance(cp, ep)
        tgts = _legal_targets(rpc, rid, c["id"], ability)
        if tgts and (max_dist is None or d <= max_dist):
            return c, (e["id"] if e["id"] in tgts else tgts[0])
        mov = rpc("aiMovableTiles", {"runnerId": rid}, 60)
        mu = next((m for m in (mov.get("units") or []) if m.get("unitId") == c["id"]), None)
        best = None
        for t in (mu or {}).get("tiles") or []:
            if t.get("col") is None:
                continue
            dd = hexgeo.distance((t["col"], t["row"]), ep)
            if best is None or dd < best[0]:
                best = (dd, (t["col"], t["row"]))
        if best is None or best[0] >= d:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            continue
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": c["id"], "to": {"col": best[1][0], "row": best[1][1]}}}, 60)
        if _legal_targets(rpc, rid, c["id"], ability) and (max_dist is None or best[0] <= max_dist):
            dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
            c = next(u for u in dv["units"] if u.get("visualId") == caster_vis)
            tg = _legal_targets(rpc, rid, c["id"], ability)
            return c, (e["id"] if e["id"] in tg else tg[0])
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    pytest.skip(f"{caster_vis} : aucune cible legale pour {ability} (geometrie)")


def _cast_and_replay(rpc, rid, board, caster_id, target_id, ability, ability_cls, new_vis):
    """Capture l'etat-avant, caste LIVE, rejoue le PORT sur le MEME etat-avant (rng cale)."""
    dv0 = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob0 = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    s0 = rpc("dumpRng", {"runnerId": rid}, 30)
    ids_before = {u["id"] for u in dv0["units"]}
    tgt0 = next((u for u in dv0["units"] if u["id"] == target_id), None)
    tgt_hp0 = (tgt0 or {}).get("hp")

    act = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": caster_id, "targetId": target_id,
        "abilityType": ability}}, 120)
    a0 = ((act or {}).get("actions") or [{}])[0]
    if not a0.get("mutated"):
        pytest.skip(f"cast live non mute (ability {ability} refusee : {a0.get('error')})")
    dv1 = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    dv1_units = dv1.get("units") or []
    # Filet : si la bataille s'est TERMINEE au cast (cible tuee), `decisionView` ne publie plus d'unites
    # -> on lit les apparitions dans les `changes` de l'action (source PRIMAIRE, publiee par le runner).
    live_new = [u for u in dv1_units if u["id"] not in ids_before]
    live_summons = [u for u in live_new if u.get("visualId") in new_vis]
    appeared = [ch for ch in (a0.get("changes") or []) if ch.get("appeared")]
    tgt1 = next((u for u in dv1_units if u["id"] == target_id), None)
    live_tgt_delta = (tgt_hp0 or 0) - ((tgt1 or {}).get("hp") or 0)
    if tgt1 is None:                                  # bataille finie -> delta lu dans les changes
        ch = next((c for c in (a0.get("changes") or []) if c.get("squadId") == target_id), None)
        if ch is not None:
            live_tgt_delta = -(ch.get("hpDelta") or 0)
    live_effects = {ef.get("name") for u in dv1_units if u["id"] == caster_id
                    for ef in (u.get("effects") or [])}

    def _fresh():
        st = load_state(dv0, ob0, snap, board=board)
        if isinstance(s0, dict) and s0.get("mt"):
            rng = IntBasedMersenneTwister()
            rng.mt = list(s0["mt"])
            rng.mti = s0["mti"]
            st.rng = rng
        return st

    state = _fresh()
    port_hp0 = state.get_entity(target_id).get_component(HealthComponent).hp
    res = ability_cls().execute_behaviour(state, caster_id, target_id)
    port_tgt_delta = port_hp0 - state.get_entity(target_id).get_component(HealthComponent).hp
    return {"res": res, "state": state, "fresh": _fresh, "dv0": dv0, "act": a0,
            "live_summons": live_summons, "live_appeared": appeared,
            "live_tgt_delta": live_tgt_delta,
            "port_tgt_delta": port_tgt_delta, "live_effects": live_effects}


# ============================================================================================== #
# Waaagh (1058, orksWarboss) — 2e consommateur de PerformAIAction (asGroup=1, resetTurnFlags=1)
# ============================================================================================== #

WAAAGH_CASTER = "orksWarboss"
WAAAGH_ENEMY = "necroWarden"
BOY_VIS = {"orksOrkBoys", "orksNpc2OrkBoy"}      # config id / visualId (cf. VisualUnitIdFromUnitId)


@pytest.fixture(scope="session")
def waaagh(rpc, build_runner):
    from engine.runner.abilities.orks import WaaaghAbility
    rid = build_runner("31337", extra=["--p-units", WAAAGH_CASTER,
                                       "--a-units", f"{WAAAGH_ENEMY},necroDestroyer"])["rid"]
    board = _board(rpc, rid)
    c, tid = _drive_until_castable(rpc, rid, WAAAGH_CASTER, WAAAGH_ENEMY, 1058)
    d = _cast_and_replay(rpc, rid, board, c["id"], tid, 1058, WaaaghAbility, BOY_VIS)
    d.update({"rid": rid, "caster_id": c["id"], "caster_pos": _upos(c), "enemy_id": tid})
    return d


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
    1101 ExtraHits) sont poses sur le caster LIVE **et** par le port (le selecteur inclut le caster)."""
    d = waaagh
    from engine.entities.effect_type import EffectType
    want = {"Waaagh_ExtraMovement", "Waaagh_ExtraDamage", "Waaagh_ExtraHits"}
    st = d["state"]
    port_names = set()
    if st.effects is not None:
        for ef in (st.effects.by_unit.get(d["caster_id"]) or []):
            port_names.add(getattr(ef, "name", None) or "")
    assert want <= port_names, f"port : effets sur le caster {sorted(port_names)} ne couvre pas {sorted(want)}"
    if d["live_effects"]:
        assert want <= d["live_effects"], (
            f"live : effets sur le caster {sorted(d['live_effects'])} ne couvre pas {sorted(want)}")


def test_waaagh_move_range_uses_effect_not_double_count(waaagh):
    """`IdunBattleLogic.Entities.DSLFactory$$UnitMovementRangeWithBonus` = `If(HasEffect(caster,1099), StatAmount(MOVEMENT),
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


def test_waaagh_counter_case_without_perform_ai_action(waaagh):
    """CONTRE-CAS : MEME etat-avant, MEME arbre de spawn, SANS `PerformAIAction` -> TOUS les Ork Boyz
    restent a distance 1. Sans ce contraste, « il a bouge » ne prouve rien."""
    from engine.dsl.effects import ExecutionContext
    from engine.runner.abilities.orks import waaagh_spawn_tree
    from engine.runner.abilities.behaviours import entities_from_state
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

WAAAGH_ALLY = "orksNob"        # Hero Orks : MEME faction (donc BUFFE) mais visualId != orksOrkBoys
GEN_BOARD = "C3_01"


@pytest.fixture(scope="session")
def waaagh_ally(rpc, build_runner):
    """Board + roster DIFFERENTS : le Warboss + un allie ORK (orksNob) amene ADJACENT. Il doit etre
    BUFFE (meme faction -> `UnitsFromFaction(Friends, Orks)`) mais PAS pousse a agir (le selecteur de
    `PerformAIAction` filtre sur le visualId `orksOrkBoys` via `UnitsWithVisualId`)."""
    from engine.runner.abilities.orks import WaaaghAbility
    rid = build_runner("777", extra=["--p-units", f"{WAAAGH_CASTER},{WAAAGH_ALLY}",
                                     "--a-units", f"{WAAAGH_ENEMY},necroDestroyer",
                                     "--board", GEN_BOARD])["rid"]
    board = _board(rpc, rid)
    c, tid = _drive_until_castable(rpc, rid, WAAAGH_CASTER, WAAAGH_ENEMY, 1058)
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ally = next((u for u in dv["units"] if u.get("visualId") == WAAAGH_ALLY), None)
    if ally is None:
        pytest.skip("allie ork absent")
    ally_pos_before = _upos(ally)
    d = _cast_and_replay(rpc, rid, board, c["id"], tid, 1058, WaaaghAbility, BOY_VIS)
    dv1 = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ally1 = next((u for u in (dv1.get("units") or []) if u["id"] == ally["id"]), None)
    d.update({"rid": rid, "caster_id": c["id"], "ally_id": ally["id"],
              "ally_pos_before": ally_pos_before,
              "ally_pos_after": _upos(ally1) if ally1 else None,
              "ally_effects": {ef.get("name") for ef in (ally1 or {}).get("effects") or []}})
    return d


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
    if d["ally_effects"]:
        assert want <= d["ally_effects"], (
            f"live : l'allie Ork n'est pas buffe ({sorted(d['ally_effects'])})")


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
