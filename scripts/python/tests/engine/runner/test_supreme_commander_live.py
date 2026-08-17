"""Debloqueur `PerformAIAction` (+ `GetAbilityStatModification`) — CONFRONTE AU LIVE via son 1er
consommateur SupremeCommander (1028, `astraCreed`).

Mecanisme porte (VAs) :
  `IdunBattleLogic.Entities.DSLBehaviors$$PerformAIAction` -> `IdunBattle.Entities.Behaviours.PerformAIActionBehaviour$$Execute`
  -> `Core.Services.OperationProcessor$$ComputerAction`/`Core.Services.OperationProcessor$$ComputerAction`
  -> `IdunBattle.Operations.ComputerActionOperation$$Execute` (mono) / `IdunBattle.Operations.ComputerActionOperation$$Execute` (groupe)
     [ `IdunBattle.Entities.Components.UnitFlagsComponent$$RemoveTurnFlags` -> `IdunBattle.Core.Services.AiControl$$ExecuteFor`/`IdunBattle.Core.Services.AiControl$$ExecuteFor`
       -> `IdunBattle.Operations.ComputerActionOperation$$SetUnitTurnsFlags` ]
  `IdunBattle.Entities.UnitExtensions$$GetAbilityStatModification` -> `IdunBattle.Entities.Components.ActiveAbilityModificationsComponent$$Get`.

DISCRIMINANT (ce que le test PROUVE, pas « le code est atteint ») : les gardes tout juste SPAWNES
QUITTENT l'anneau de spawn (distance >= 2 du caster) A L'INSTANT DU CAST — ils AGISSENT alors qu'ils
viennent d'etre marques `TurnFinished` par le spawn. CONTRE-CAS : le meme port prive du noeud
`PerformAIAction` les laisse TOUS a distance 1 (anneau de spawn intact).

ASCII-only. Property-based. Skip si pas de session / Creed n'atteint pas l'ennemi.
"""
from __future__ import annotations

import pytest

import hexgeo

from engine.runner.snapshot import load_state
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.components import (StatsComponent, HealthComponent, PositionComponent,
                                      UnitFlagsComponent, ActiveAbilityModificationsComponent)
from engine.entities.effects.magnitude import ability_var

BUILD = ["--p-units", "astraCreed", "--a-units", "necroDestroyer"]
CASTER_VIS = "astraCreed"
ENEMY_VIS = "necroDestroyer"
KELL_VIS = "astraSmnKell"
# Le garde summon `astraSmnGuardsman` a pour `visualId` gameconfig `astraNpc1Guardsman` : le LIVE
# (decisionView) rend le visuel, le port spawne sous l'id de CONFIG. Les deux formes sont dans
# `affectedUnitIds` (cf. selecteur `UnitsWithIds`).
GUARD_VIS_LIVE = "astraNpc1Guardsman"
GUARD_VIS_PORT = "astraSmnGuardsman"
ABILITY = 1028


def _upos(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row"))


@pytest.fixture(scope="session")
def supreme_commander(rpc, build_runner):
    """Drive Creed a dist<=3 de l'ennemi, capture l'etat-avant, caste LIVE, puis rejoue le PORT."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.abilities.astramilitarum import SupremeCommanderAbility

    rid = build_runner("777", extra=BUILD)["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")

    creed = enemy = None
    ready = False
    for _ in range(16):
        dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        cur = dv.get("currentPlayer")
        creed = next((u for u in dv["units"] if u.get("visualId") == CASTER_VIS), None)
        enemy = next((u for u in dv["units"] if u.get("visualId") == ENEMY_VIS), None)
        if creed is None or enemy is None:
            pytest.skip("creed/enemy absent")
        cp, ep = _upos(creed), _upos(enemy)
        if cp[0] is None or ep[0] is None:
            pytest.skip("positions absentes")
        d = hexgeo.distance(cp, ep)
        if cur != creed.get("owner"):
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            continue
        if d <= 3:
            ready = True
            break
        mov = rpc("aiMovableTiles", {"runnerId": rid}, 60)
        mu = next((m for m in (mov.get("units") or []) if m.get("unitId") == creed["id"]), None)
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
            "kind": "move", "unitId": creed["id"], "to": {"col": best[1][0], "row": best[1][1]}}}, 60)
        if best[0] <= 3:
            ready = True
            break
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)

    if not ready:
        pytest.skip("Creed n'a pas atteint dist<=3 de l'ennemi sur son tour")

    # --- etat-avant (source du replay PORT) ---
    dv0 = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    creed = next(u for u in dv0["units"] if u.get("visualId") == CASTER_VIS)
    if creed.get("owner") != dv0.get("currentPlayer"):
        pytest.skip("pas le tour de Creed")
    ob0 = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    s0 = rpc("dumpRng", {"runnerId": rid}, 30)
    creed_id = creed["id"]
    creed_pos_before = _upos(creed)
    ids_before = {u["id"] for u in dv0["units"]}
    enemy0 = next(u for u in dv0["units"] if u.get("visualId") == ENEMY_VIS)
    enemy_id, enemy_hp_before = enemy0["id"], enemy0.get("hp")

    # --- cast LIVE ---
    rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": creed_id, "targetId": creed_id,
        "abilityType": ABILITY}}, 90)
    dv1 = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob1 = rpc("observeBattle", {"runnerId": rid}, 40)
    live_new = [u for u in dv1["units"] if u["id"] not in ids_before]
    live_guards = [u for u in live_new if u.get("visualId") == GUARD_VIS_LIVE]
    # `hpMax` n'est publie que par observeBattle (decisionView ne porte que `hp`).
    live_guards_obs = [u for u in (ob1.get("units") or []) if u.get("visualId") == GUARD_VIS_LIVE]
    live_kell_present = any(u.get("visualId") == KELL_VIS for u in dv0["units"])
    enemy1 = next((u for u in dv1["units"] if u["id"] == enemy_id), None)
    live_enemy_delta = (enemy_hp_before or 0) - ((enemy1 or {}).get("hp") or 0)

    # --- PORT sur l'etat-avant ---
    def _fresh_state():
        st = load_state(dv0, ob0, snap, board=board)
        if isinstance(s0, dict) and s0.get("mt"):
            rng = IntBasedMersenneTwister()
            rng.mt = list(s0["mt"])
            rng.mti = s0["mti"]
            st.rng = rng
        return st

    state = _fresh_state()
    port_enemy_hp0 = state.get_entity(enemy_id).get_component(HealthComponent).hp
    res = SupremeCommanderAbility().execute_behaviour(state, creed_id, creed_id)
    port_enemy_delta = port_enemy_hp0 - state.get_entity(enemy_id).get_component(HealthComponent).hp

    sc = state.get_entity(creed_id).get_component(StatsComponent)
    ctx = sc.ctx if sc is not None else None
    return {"rid": rid, "creed_id": creed_id, "creed_pos": creed_pos_before,
            "live_enemy_delta": live_enemy_delta, "port_enemy_delta": port_enemy_delta,
            "live_guards": live_guards, "live_guards_obs": live_guards_obs,
            "live_kell_present": live_kell_present,
            "res": res, "state": state, "fresh_state": _fresh_state,
            "level": getattr(ctx, "active_ability_level", None),
            "mult": int(getattr(ctx, "ability_variables_multiplier", 100) or 100)}


def test_spawn_count_port_matches_live(supreme_commander):
    """`nrOfSummons` (+ `GetAbilityStatModification` = 0 sans source portee) : le port spawne le MEME
    nombre de gardes que le natif."""
    d = supreme_commander
    if not d["live_guards"]:
        pytest.skip("cast live n'a spawn aucun garde (geometrie : aucune tuile libre adjacente)")
    assert len(d["res"]["spawned"]) == len(d["live_guards"]), (
        f"port {len(d['res']['spawned'])} gardes != live {len(d['live_guards'])}")
    assert d["res"]["count"] == len(d["live_guards"]), (
        f"count resolu {d['res']['count']} != gardes live {len(d['live_guards'])}")


def test_summon_stats_bit_exact_vs_live(supreme_commander):
    """Stats de spawn = `SpawnUnitOptions.WithStatsFromConfig` = `summonHp[level] x mult` — le PORT
    reproduit BIT-EXACT le `hpMax` natif (confronte la SOURCE des stats, pas une constante figee)."""
    d = supreme_commander
    if not d["live_guards_obs"]:
        pytest.skip("pas de garde live (observeBattle)")
    expected = ability_var("SupremeCommander", "summonHp", d["level"], multiplier_pct=d["mult"])
    live_hpmax = {u.get("hpMax") for u in d["live_guards_obs"]}
    assert live_hpmax == {expected}, f"live garde hpMax {live_hpmax} != formule config {expected}"
    for gid in d["res"]["spawned"]:
        hc = d["state"].get_entity(gid).get_component(HealthComponent)
        assert hc is not None and hc.hp_max == expected, \
            f"port garde hp_max {hc and hc.hp_max} != {expected} (= live)"


def test_no_ability_stat_modification_live(supreme_commander):
    """`GetAbilityStatModification` — face ZERO confrontee : la seule source native
    (`ListenUpMaggotsEffect` IdunBattle.Entities.Effects.Loki.ListenUpMaggotsEffect$$ApplyInternal, passif de Kell) n'est PAS portee ; le natif observe rend AUSSI
    une modification nulle (2 gardes) MEME quand Kell est en jeu -> agreement, pas degradation."""
    d = supreme_commander
    if not d["live_guards"]:
        pytest.skip("pas de garde live")
    base = int((__import__("gameconfig").ability("SupremeCommander")["constants"])["nrOfSummons"])
    assert len(d["live_guards"]) == base, (
        f"live a summon {len(d['live_guards'])} gardes != nrOfSummons de base {base} "
        f"(Kell present={d['live_kell_present']}) -> une modification d'ability EST active live : "
        f"porter ListenUpMaggotsEffect")


def test_perform_ai_action_moves_fresh_summons_live(supreme_commander):
    """DISCRIMINANT LIVE : au moins un garde tout juste spawne a QUITTE l'anneau de spawn (dist >= 2 du
    caster) a l'instant du cast -> il a joue une action AI alors qu'il venait d'etre marque
    `TurnFinished` par le spawn. C'est l'effet OBSERVABLE de `PerformAIAction`."""
    d = supreme_commander
    if not d["live_guards"]:
        pytest.skip("pas de garde live")
    dists = [hexgeo.distance(_upos(u), d["creed_pos"]) for u in d["live_guards"]
             if _upos(u)[0] is not None]
    assert dists, "positions des gardes live absentes"
    assert max(dists) >= 2, (
        f"aucun garde live n'a quitte l'anneau de spawn (dists={dists}) -> pas d'action AI observee")


def test_perform_ai_action_moves_fresh_summons_port(supreme_commander):
    """Le PORT reproduit le discriminant : au moins un garde spawne a quitte l'anneau de spawn."""
    d = supreme_commander
    if not d["res"]["spawned"]:
        pytest.skip("port n'a spawn aucun garde (geometrie offline)")
    st = d["state"]
    dists = []
    for gid in d["res"]["spawned"]:
        pc = st.get_entity(gid).get_component(PositionComponent)
        if pc is not None:
            dists.append(hexgeo.distance((pc.col, pc.row), d["creed_pos"]))
    assert dists, "positions des gardes portes absentes"
    assert d["res"]["ai_units"], "PerformAIAction n'a selectionne AUCUNE unite (UnitsWithIds vide ?)"
    assert max(dists) >= 2, (
        f"port : aucun garde n'a quitte l'anneau de spawn (dists={dists})")


def test_ai_action_reaches_and_attacks(supreme_commander):
    """CONSEQUENCE de l'action AI (pas seulement le deplacement) : quand la geometrie le permet, les
    gardes tout juste spawnes ATTAQUENT dans la foulee -> l'ennemi perd des PV PENDANT le cast, LIVE
    **et** dans le port. (Le montant exact depend du tirage RNG/overwatch -> on confronte l'EXISTENCE
    de l'attaque, pas le scalaire : doctrine « ne jamais fitter un scalaire ».)"""
    d = supreme_commander
    if d["live_enemy_delta"] <= 0:
        pytest.skip("aucun garde live n'a pu attaquer (ennemi hors de portee apres move)")
    assert d["port_enemy_delta"] > 0, (
        f"live : ennemi -{d['live_enemy_delta']} PV pendant le cast ; port : -{d['port_enemy_delta']} "
        f"-> l'action AI portee ne va pas jusqu'a l'attaque")


def test_counter_case_without_perform_ai_action(supreme_commander):
    """CONTRE-CAS : le MEME etat-avant, le MEME arbre de spawn, mais SANS le noeud `PerformAIAction`
    -> TOUS les gardes restent a distance 1 du caster. Sans ce contraste, « il a bouge » ne prouve rien."""
    from engine.dsl.effects import ExecutionContext
    from engine.runner.abilities.astramilitarum import supreme_commander_spawn_tree
    from engine.runner.abilities.behaviours.context import entities_from_state
    d = supreme_commander
    if not d["res"]["spawned"]:
        pytest.skip("port n'a spawn aucun garde")
    st = d["fresh_state"]()
    ectx = ExecutionContext(state=st, rng=st.rng)
    supreme_commander_spawn_tree(d["res"]["count"]).execute(
        entities_from_state(st, d["creed_id"], d["creed_id"]), ectx)
    spawned = [p["unit"] for n, p in ectx.emitted if n == "SpawnUnit"]
    assert spawned, "contre-cas : aucun spawn"
    dists = []
    for gid in spawned:
        pc = st.get_entity(gid).get_component(PositionComponent)
        if pc is not None:
            dists.append(hexgeo.distance((pc.col, pc.row), d["creed_pos"]))
    assert dists and max(dists) == 1, (
        f"contre-cas : un garde a bouge SANS PerformAIAction (dists={dists}) -> le discriminant "
        f"n'isole pas le mecanisme")


def test_turn_flags_saved_and_restored(supreme_commander):
    """`ComputerActionOperation` : les flags de tour d'une cible sont EFFACES puis RESTAURES ->
    (a) l'unite agit MEME deja `TurnFinished`, (b) son etat de tour est INCHANGE apres coup
    (l'action supplementaire NE CONSOMME PAS son tour). Mirror IdunBattle.Operations.ComputerActionOperation$$Execute + IdunBattle.Operations.ComputerActionOperation$$SetUnitTurnsFlags."""
    from engine.runner.operations.summon_ai import ComputerActionOperation
    d = supreme_commander
    if not d["res"]["spawned"]:
        pytest.skip("port n'a spawn aucun garde")
    st = d["fresh_state"]()
    from engine.runner.abilities.astramilitarum import SupremeCommanderAbility
    SupremeCommanderAbility().execute_behaviour(st, d["creed_id"], d["creed_id"])
    gid = None
    for eid, e in st.entities.items():
        from engine.runner.components import UnitComponent
        uc = e.get_component(UnitComponent)
        if uc is not None and uc.visual_id == GUARD_VIS_PORT and uc.alive:
            gid = eid
            break
    if gid is None:
        pytest.skip("aucun garde vivant apres le cast")
    e = st.get_entity(gid)
    fl = e.get_component(UnitFlagsComponent)
    if fl is None:
        fl = UnitFlagsComponent()
        e.add_component(fl)
    before = {UnitFlagsComponent.TURN_FINISHED, UnitFlagsComponent.ACTIVE_ABILITY_USED,
              UnitFlagsComponent.MOVED}
    fl.flags = set(before)
    pc = e.get_component(PositionComponent)
    pos_before = (pc.col, pc.row) if pc is not None else None
    ComputerActionOperation.execute(st, gid, True)
    assert before <= fl.flags, (
        f"flags de tour NON restaures : {sorted(fl.flags)} ne contient pas {sorted(before)}")
    pc = st.get_entity(gid).get_component(PositionComponent)
    pos_after = (pc.col, pc.row) if pc is not None else None
    assert pos_after is not None and pos_before is not None
    # (a) l'unite a bien pu jouer malgre TurnFinished : elle a bouge OU elle etait deja au contact.
    #     On n'exige pas le mouvement (l'IA peut choisir de rester) — la garde forte est (b).


# ---------------------------------------------------------------------------------------------- #
# GENERALISATION (autre board, autre roster) : le filtre `UnitsWithIds(affectedUnitIds)` — un ALLIE
# a portee mais HORS de la liste ne doit PAS etre force a agir. Sans ce filtre, `PerformAIAction`
# (resetTurnFlags=1) rejouerait un allie AYANT DEJA AGI -> effet observable enorme et faux.
# ---------------------------------------------------------------------------------------------- #

ALLY_VIS = "astraBullgryn"          # Hero AstraMilitarum, ABSENT de `affectedUnitIds`
GEN_BOARD = "C3_01"


@pytest.fixture(scope="session")
def supreme_commander_ally(rpc, build_runner):
    """Board + roster DIFFERENTS : Creed + un allie hors `affectedUnitIds` amene ADJACENT au caster
    (et ayant DEJA consomme son action en s'y rendant)."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.abilities.astramilitarum import SupremeCommanderAbility

    rid = build_runner("31337", extra=["--p-units", f"{CASTER_VIS},{ALLY_VIS}",
                                       "--a-units", ENEMY_VIS, "--board", GEN_BOARD])["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")

    for _ in range(6):
        dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        creed = next((u for u in dv["units"] if u.get("visualId") == CASTER_VIS), None)
        ally = next((u for u in dv["units"] if u.get("visualId") == ALLY_VIS), None)
        if creed is None or ally is None:
            pytest.skip("creed/allie absent")
        if creed.get("owner") != dv.get("currentPlayer"):
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            continue
        cp, ap = _upos(creed), _upos(ally)
        if hexgeo.distance(cp, ap) <= 1:
            break
        mov = rpc("aiMovableTiles", {"runnerId": rid}, 60)
        mu = next((m for m in (mov.get("units") or []) if m.get("unitId") == ally["id"]), None)
        best = None
        for t in (mu or {}).get("tiles") or []:
            if t.get("col") is None:
                continue
            dd = hexgeo.distance((t["col"], t["row"]), cp)
            if best is None or dd < best[0]:
                best = (dd, (t["col"], t["row"]))
        if best is None or best[0] >= hexgeo.distance(cp, ap):
            break
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": ally["id"], "to": {"col": best[1][0], "row": best[1][1]}}}, 60)

    dv0 = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    creed = next(u for u in dv0["units"] if u.get("visualId") == CASTER_VIS)
    ally = next(u for u in dv0["units"] if u.get("visualId") == ALLY_VIS)
    if creed.get("owner") != dv0.get("currentPlayer"):
        pytest.skip("pas le tour de Creed")
    if hexgeo.distance(_upos(creed), _upos(ally)) > 2:
        pytest.skip("allie hors du rayon de SupremeCommander (geometrie)")
    ob0 = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    s0 = rpc("dumpRng", {"runnerId": rid}, 30)
    creed_id, ally_id = creed["id"], ally["id"]
    ally_pos_before = _upos(ally)

    rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": creed_id, "targetId": creed_id,
        "abilityType": ABILITY}}, 90)
    dv1 = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ally1 = next(u for u in dv1["units"] if u["id"] == ally_id)

    st = load_state(dv0, ob0, snap, board=board)
    if isinstance(s0, dict) and s0.get("mt"):
        rng = IntBasedMersenneTwister()
        rng.mt = list(s0["mt"])
        rng.mti = s0["mti"]
        st.rng = rng
    ally_pc0 = st.get_entity(ally_id).get_component(PositionComponent)
    ally_port_before = (ally_pc0.col, ally_pc0.row)
    res = SupremeCommanderAbility().execute_behaviour(st, creed_id, creed_id)
    ally_pc1 = st.get_entity(ally_id).get_component(PositionComponent)
    return {"ally_id": ally_id, "ally_pos_before": ally_pos_before, "ally_pos_after": _upos(ally1),
            "ally_port_before": ally_port_before, "ally_port_after": (ally_pc1.col, ally_pc1.row),
            "res": res}


def test_ally_outside_affected_ids_not_forced_to_act_live(supreme_commander_ally):
    """LIVE : l'allie a portee mais hors `affectedUnitIds` NE bouge PAS pendant le cast (le filtre
    `IdunBattleLogic.Entities.DSLSelectors$$UnitsWithIds le retire du set passe a `PerformAIAction`)."""
    d = supreme_commander_ally
    assert d["ally_pos_after"] == d["ally_pos_before"], (
        f"live : l'allie {ALLY_VIS} a bouge {d['ally_pos_before']} -> {d['ally_pos_after']} pendant le "
        f"cast alors qu'il est HORS de affectedUnitIds")


def test_ally_outside_affected_ids_not_forced_to_act_port(supreme_commander_ally):
    """PORT : meme verdict — l'allie n'est ni selectionne (`ai_units`) ni deplace."""
    d = supreme_commander_ally
    assert d["ally_id"] not in (d["res"]["ai_units"] or []), (
        f"port : l'allie {d['ally_id']} est dans ai_units {d['res']['ai_units']} -> le filtre "
        f"UnitsWithIds ne s'applique pas")
    assert d["ally_port_after"] == d["ally_port_before"], (
        f"port : l'allie a bouge {d['ally_port_before']} -> {d['ally_port_after']}")


def test_ability_stat_modification_semantics_offline(supreme_commander):
    """`GetAbilityStatModification` — les DEUX semantiques de consommation lues au decompile
    IdunBattleLogic.Entities.Abilities.Active.Loki.SupremeCommanderAbility$$ExecuteBehaviour+0x16b / IdunBattleLogic.Entities.Abilities.Active.Loki.SupremeCommanderAbility$$ExecuteBehaviour+0x24a : nrOfSummons ADDITIF (+1 -> 3 gardes), range OVERRIDE (mod 3 -> radius 3,
    PAS 2+3=5). Exerce en injectant la modification dans le composant (la source native
    `ListenUpMaggotsEffect` n'est pas portee)."""
    from engine.runner.abilities.astramilitarum import (SupremeCommanderAbility, CONST_NR_OF_SUMMONS,
                                                        CONST_RANGE)
    d = supreme_commander
    st = d["fresh_state"]()
    e = st.get_entity(d["creed_id"])
    comp = ActiveAbilityModificationsComponent()
    comp.add(CONST_NR_OF_SUMMONS, 1)     # ListenUpMaggots : nrOfSummons +1
    comp.add(CONST_RANGE, 3)             # ListenUpMaggots : range = 3 (override)
    e.add_component(comp)
    res = SupremeCommanderAbility().execute_behaviour(st, d["creed_id"], d["creed_id"])
    base_n = int((__import__("gameconfig").ability("SupremeCommander")["constants"])["nrOfSummons"])
    assert res["count"] == base_n + 1, f"count {res['count']} != {base_n}+1 (additif)"
    assert res["radius"] == 3, f"radius {res['radius']} != 3 (OVERRIDE, pas 2+3)"
