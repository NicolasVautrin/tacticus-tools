"""#366-r1 -- `1108 ReinforcedHiveNode_ExtraArmor` (passif du SUMMON `tyranSmnWarrior`).

RE + residus : `engine/entities/effects/loki/reinforced_hive_node.py`.

Voie SUMMON (`docs/rl/case-291-summon-activation.md`) : le porteur n'est PAS au pool -- on
l'amene en bataille en spawnant son SUMMONER `tyranWingedPrime` (qui, lui, y est) et en castant
son active `AlphaWarrior` (1112) sur une tuile libre. On l'OBSERVE, on ne le COMMANDE pas.

Ce que le test verrouille, sur PLUSIEURS rounds consecutifs :

 A. La CONDITION -- `AmountIsOdd(Sum(RoundsStarted(Owner), Direct(1)))` = actif ssi
    `turnsStarted(porteur)` est PAIR. Le test EXIGE d'avoir observe les DEUX parites (sinon il
    echoue : une passe qui n'aurait vu qu'un seul regime ne prouverait rien).
 B. La MAGNITUDE -- `PercentageOf(StatAmount(Owner, FixedArmor, Initial), extraArmorPct=100)` :
    le `fixedArmor` COURANT du port doit egaler celui du live, aux deux parites.
 C. L'ATTRIBUTION -- la contribution doit etre keyee sur l'effet 1108 (et NON dans le residu
    opaque `CAPTURED_SOURCE`), et le port doit rester d'accord avec le live APRES un
    `refresh_stat_modifier_effects` (le driver `RefreshEffectsOperation`).
    C'est (C) qui a attrape la regression du foyer PARTAGE `stat_modifications_by_source` :
    un effet capte INERTE (`active: false` par le canal `includeInactive`) se voyait attribuer
    une magnitude que le natif n'applique pas -> apres refresh, `FixedArmor` port **0** contre
    live **1595**.

Rien de code en dur : la magnitude attendue se relit du LIVE (part Initial du stat) et de
gameconfig (`extraArmorPct`). ASCII only.
"""
from __future__ import annotations

import pytest

from engine.entities.effects.magnitude import ability_var
from engine.entities.stats import StatType
from engine.runner.components import StatsComponent, unit_state_for_effects
from engine.runner.operations.refresh_effects import refresh_stat_modifier_effects
from engine.runner.snapshot import decision_view_seed_body, load_state

SUMMONER = "tyranWingedPrime"          # au pool rank 17 ; porte l'active AlphaWarrior (1112)
ALPHA_WARRIOR = 1112
EXTRA_ARMOR = "ReinforcedHiveNode_ExtraArmor"    # EffectType 0x454 = 1108
EXTRA_BLOCK = "ReinforcedHiveNode_ExtraBlock"    # EffectType 0x455 = 1109 (residu, cf. RE)
ROUNDS = 4                                        # assez pour voir les DEUX parites


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _dv(rpc, rid):
    return rpc("decisionView", decision_view_seed_body(rid, allAbilities=True), 150)


def _carrier_row(dv):
    """L'unite qui PORTE les effets `ReinforcedHiveNode_*` -- identifiee par ses EFFETS, jamais
    par un `visualId` suppose (le summon se projette sous le visual `tyranNpc4Warrior`)."""
    for u in (dv.get("units") or []):
        if any(str(e.get("name", "")).startswith("ReinforcedHiveNode")
               for e in (u.get("effects") or [])):
            return u
    return None


def _spawn_summon(rpc, rid):
    """Cast `AlphaWarrior` du summoner sur une tuile libre. ASSERTE le montage (jamais un skip)."""
    dv = _dv(rpc, rid)
    assert _ok(dv), f"decisionView KO: {dv}"
    caster = next((u for u in (dv.get("units") or [])
                   if u.get("visualId") == SUMMONER and u.get("alive")), None)
    assert caster is not None, (
        f"{SUMMONER} absent du runner -- montage casse (pool rank 17 ?)")
    at = rpc("abilityTargets", {"runnerId": rid, "allAbilities": True}, 120)
    assert _ok(at), f"abilityTargets KO: {at}"
    tiles = []
    for row in (at.get("units") or []):
        if int(row.get("unitId", -1)) != int(caster["id"]):
            continue
        for ab in (row.get("abilities") or []):
            if int(ab.get("abilityId", -1)) != ALPHA_WARRIOR:
                continue
            # `fromHere` = castable SANS bouger (legalite EXACTE du cast immediat) ; `targets`
            # est le superset MOVE-inclus. On ne veut que le premier.
            for t in (ab.get("fromHere") or ab.get("targets") or []):
                p = t.get("tile") or {}
                if p.get("col") is not None:
                    tiles.append((int(p["col"]), int(p["row"])))
    assert tiles, (
        f"aucune tuile de spawn legale pour AlphaWarrior -- montage casse (payload={at})")
    col, row = tiles[0]
    act = rpc("applyAction", {"runnerId": rid,
                              "action": {"kind": "ability", "casterId": int(caster["id"]),
                                         "to": {"col": col, "row": row},
                                         "abilityType": ALPHA_WARRIOR}}, 90)
    assert _ok(act), f"cast AlphaWarrior KO: {act}"
    dv = _dv(rpc, rid)
    carrier = _carrier_row(dv)
    assert carrier is not None, (
        "le cast n'a pose AUCUN effet ReinforcedHiveNode -- le summon n'est pas arrive "
        f"(events={act.get('eventCount')}, spawned={act.get('spawned')})")
    return int(carrier["id"])


def _end_round(rpc, rid):
    """Termine toutes mes unites puis le tour. Le tour adverse et les unites automatiques se
    jouent dans la foulee cote runner."""
    dv = _dv(rpc, rid)
    for uid in (dv.get("toActivate") or []):
        rpc("applyAction", {"runnerId": rid,
                            "action": {"kind": "finish", "unitId": int(uid)}}, 60)
    rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 90)


def _observe(rpc, rid, carrier_id):
    """UN point de mesure : live (effets + stats) ET port (state charge + refresh)."""
    dv = _dv(rpc, rid)
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
    assert _ok(dv) and _ok(ob) and _ok(snap)
    row = next((u for u in (dv.get("units") or []) if int(u["id"]) == carrier_id), None)
    if row is None or not row.get("alive"):
        return None
    live_eff = {str(e.get("name")): bool(e.get("active", True))
                for e in (row.get("effects") or [])
                if str(e.get("name", "")).startswith("ReinforcedHiveNode")}
    su = next((x for x in (snap.get("units") or [])
               if int(x.get("entityId", -1)) == carrier_id), None)
    assert su is not None, "porteur absent de combatSnapshot"
    st = load_state(dv, ob, snap)
    ent = st.get_entity(carrier_id)
    us = ent.get_component(StatsComponent).ctx.stats
    ustate = unit_state_for_effects(st, carrier_id)
    port_before = us.get_stat(int(StatType.FIXED_ARMOR))
    per_source = dict(us.components[int(StatType.FIXED_ARMOR)].modification.per_source)
    refresh_stat_modifier_effects(st, carrier_id)
    return {
        "turns_started": int(ustate["turns_started"]),
        "live_active": live_eff,
        "live_armor": int(su["stats"]["fixedArmor"]),
        "live_initial": int(su["stats"]["fixedArmor"])
                        - int((su.get("statDelta") or {}).get("fixedArmor") or 0),
        "port_armor_before": int(port_before),
        "port_armor_after": int(us.get_stat(int(StatType.FIXED_ARMOR))),
        "per_source": per_source,
        "port_active": {e.name: bool(e.is_active(ustate))
                        for e in st.effects.by_unit.get(carrier_id, [])
                        if e.name.startswith("ReinforcedHiveNode")},
        "port_active_names": {e.name for e in st.effects.active_effects(carrier_id, ustate)},
    }


@pytest.fixture(scope="module")
def hive_node_run(live_session, rpc, build_runner):
    """UN runner, le summon spawne, puis `ROUNDS` observations consecutives."""
    rid = build_runner(seed="777", board="MC1_67",
                       extra=["--p-units", f"{SUMMONER},tyranTyrantGuard",
                              "--a-units", "orksNob,orksRuntherd",
                              "--hp-target", "300000"])["rid"]
    carrier = _spawn_summon(rpc, rid)
    obs = []
    for _ in range(ROUNDS):
        o = _observe(rpc, rid, carrier)
        if o is None:
            break                      # le summon est mort : on garde ce qu'on a mesure
        obs.append(o)
        _end_round(rpc, rid)
    assert len(obs) >= 2, f"pas assez d'observations ({len(obs)}) -- montage casse"
    return obs


def test_active_condition_follows_turns_started_parity(hive_node_run):
    """(A) `AmountIsOdd(Sum(RoundsStarted(Owner), Direct(1)))` -- actif ssi `turnsStarted` PAIR,
    et le port doit rendre le MEME verdict que le flag live. Les DEUX parites sont EXIGEES."""
    parities = {o["turns_started"] % 2 for o in hive_node_run}
    assert parities == {0, 1}, (
        "une seule parite de `turnsStarted` observee %s -- le test ne prouve rien, "
        "allonger ROUNDS" % sorted(parities))
    for o in hive_node_run:
        expected = (o["turns_started"] % 2 == 0)
        assert o["live_active"].get(EXTRA_ARMOR) == expected, (
            "live: 1108 actif=%s a turnsStarted=%d (attendu %s)"
            % (o["live_active"].get(EXTRA_ARMOR), o["turns_started"], expected))
        assert o["port_active"].get(EXTRA_ARMOR) == expected, (
            "port: is_active=%s a turnsStarted=%d (attendu %s)"
            % (o["port_active"].get(EXTRA_ARMOR), o["turns_started"], expected))
        assert (EXTRA_ARMOR in o["port_active_names"]) == expected


def test_extra_armor_magnitude_is_100pct_of_initial_armor(hive_node_run):
    """(B) `PercentageOf(StatAmount(Owner, FixedArmor, Initial), Direct(extraArmorPct))`.
    L'attendu se DERIVE : part Initial LIVE x `extraArmorPct` gameconfig / 100."""
    pct = ability_var("ReinforcedHiveNode", "extraArmorPct", is_constant=True)
    assert pct, "constante gameconfig `extraArmorPct` introuvable"
    seen_active = 0
    for o in hive_node_run:
        base = o["live_initial"]
        assert base > 0, "part Initial de FixedArmor nulle -- montage casse"
        if o["turns_started"] % 2 == 0:
            seen_active += 1
            assert o["live_armor"] == base + round(base * int(pct) / 100), (
                "live: armure %d != Initial %d + %d%% " % (o["live_armor"], base, int(pct)))
        else:
            assert o["live_armor"] == base, (
                "live: armure %d != Initial %d alors que 1108 est INACTIF"
                % (o["live_armor"], base))
        assert o["port_armor_before"] == o["live_armor"], (
            "port %d != live %d (turnsStarted=%d)"
            % (o["port_armor_before"], o["live_armor"], o["turns_started"]))
    assert seen_active >= 1, "aucun round ACTIF observe"


def test_contribution_is_attributed_and_survives_the_refresh(hive_node_run):
    """(C) La contribution est keyee sur l'effet 1108 (residu opaque NUL), et le port reste
    d'accord avec le live APRES `refresh_stat_modifier_effects`.

    C'est l'assertion qui a rougi sur la regression du foyer `stat_modifications_by_source`
    (attribution d'un effet capte INERTE) : `port_armor_after` valait 0 contre 1595 live."""
    for o in hive_node_run:
        keyed = {k: v for k, v in o["per_source"].items()
                 if isinstance(k, tuple) and k[0] == "statmod" and k[1] == 1108}
        opaque = {k: v for k, v in o["per_source"].items() if not isinstance(k, tuple)}
        if o["turns_started"] % 2 == 0:
            assert keyed, (
                "contribution NON attribuee a 1108 (per_source=%s) -- elle resterait dans le "
                "residu opaque, donc NON RETIRABLE" % (o["per_source"],))
            assert sum(keyed.values()) == o["live_armor"] - o["live_initial"], (
                "magnitude attribuee %s != delta natif %d"
                % (keyed, o["live_armor"] - o["live_initial"]))
            assert not opaque, (
                "residu opaque NON NUL %s -- une part du delta natif n'est pas expliquee"
                % (opaque,))
        else:
            assert not keyed, (
                "1108 est INACTIF et pourtant attribue (%s) -- le natif ne pose AUCUNE "
                "ValueModification pour un effet a `EffectComponent.IsActive == 0` "
                "(RefreshEffectsOperation$$DeactivateEffect)" % (keyed,))
            assert not opaque, (
                "residu opaque NON NUL %s a turnsStarted impair" % (opaque,))
        assert o["port_armor_after"] == o["live_armor"], (
            "APRES refresh: port %d != live %d (turnsStarted=%d) -- c'est la signature de la "
            "regression #366-r1 (attribution d'un effet capte INERTE, retiree par le driver)"
            % (o["port_armor_after"], o["live_armor"], o["turns_started"]))
