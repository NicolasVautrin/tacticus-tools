"""#366-r1 -- `1108 ReinforcedHiveNode_ExtraArmor` ET `1109 ReinforcedHiveNode_ExtraBlock`
(les DEUX owner-effects du passif du SUMMON `tyranSmnWarrior`).

RE + residus : `engine/entities/effects/loki/reinforced_hive_node.py`.

Voie SUMMON (`docs/rl/case-291-summon-activation.md`) : le porteur n'est PAS au pool -- on
l'amene en bataille en spawnant son SUMMONER `tyranWingedPrime` (qui, lui, y est) et en castant
son active `AlphaWarrior` (1112) sur une tuile libre. On l'OBSERVE, on ne le COMMANDE pas.

Ce que le test verrouille, sur PLUSIEURS rounds consecutifs :

 A. La CONDITION -- `AmountIsOdd(Sum(RoundsStarted(Owner), Direct(1)))` = actif ssi
    `turnsStarted(porteur)` est PAIR, pour les DEUX effets (corps de `CreateActiveCondition`
    FONDU). Le test EXIGE d'avoir observe les DEUX parites (sinon il echoue : une passe qui
    n'aurait vu qu'un seul regime ne prouverait rien).
 B. La MAGNITUDE de 1108 -- `PercentageOf(StatAmount(Owner, FixedArmor, Initial),
    extraArmorPct=100)` : le `fixedArmor` COURANT du port doit egaler celui du live, aux deux
    parites.
 C. L'ATTRIBUTION de 1108 -- la contribution doit etre keyee sur l'effet (et NON dans le residu
    opaque `CAPTURED_SOURCE`), et le port doit rester d'accord avec le live APRES un
    `refresh_stat_modifier_effects` (le driver `RefreshEffectsOperation`).
    C'est (C) qui a attrape la regression du foyer PARTAGE `stat_modifications_by_source` :
    un effet capte INERTE (`active: false` par le canal `includeInactive`) se voyait attribuer
    une magnitude que le natif n'applique pas -> apres refresh, `FixedArmor` port **0** contre
    live **1595**.
 D. Le canal OVERRIDE de 1109 -- `blockChance` FORCEE a `blockChance = 100` (part 7
    `ValueOverride.SetOverride`, `isModifiable = 0`), donc 100 <-> 0 au rythme de la meme parite.
    Le port doit rendre la MEME valeur, et la porter dans son SLOT D'OVERRIDE, pas dans une
    modification par-source : une modification y serait FANTOME (invisible sous l'override, et
    de retour des que le driver joue le `RemoveOverride`).
 E. LA TRANSITION, qui est le vrai discriminant du canal (D) : depuis l'etat charge au round i,
    on bump `turnsStarted` et on rejoue le driver -- le port doit alors reproduire le
    `blockChance` que le LIVE affichera au round i+1. C'est le seul point du test ou le port
    SIMULE au lieu de re-seeder ; sans le volet SEED du fix il rendrait 100 la ou le natif
    retombe a 0.

Rien de code en dur : les magnitudes attendues se relisent du LIVE (part Initial du stat) et de
gameconfig (`extraArmorPct`, `blockChance`). ASCII only.
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
EXTRA_ARMOR = "ReinforcedHiveNode_ExtraArmor"    # EffectType 0x454 = 1108 (stat-mod additif)
EXTRA_BLOCK = "ReinforcedHiveNode_ExtraBlock"    # EffectType 0x455 = 1109 (override part 7)
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
    block_before = us.get_stat(int(StatType.BLOCK_CHANCE))
    bcomp = us.components.get(int(StatType.BLOCK_CHANCE))
    per_source = dict(us.components[int(StatType.FIXED_ARMOR)].modification.per_source)
    block_per_source = dict(bcomp.modification.per_source) if bcomp is not None else {}
    refresh_stat_modifier_effects(st, carrier_id)
    out = {
        "turns_started": int(ustate["turns_started"]),
        "live_active": live_eff,
        "live_armor": int(su["stats"]["fixedArmor"]),
        "live_initial": int(su["stats"]["fixedArmor"])
                        - int((su.get("statDelta") or {}).get("fixedArmor") or 0),
        "live_block": int(su["stats"]["blockChance"]),
        "live_block_initial": int(su["stats"]["blockChance"])
                              - int((su.get("statDelta") or {}).get("blockChance") or 0),
        "port_armor_before": int(port_before),
        "port_armor_after": int(us.get_stat(int(StatType.FIXED_ARMOR))),
        "port_block_before": int(block_before),
        "port_block_after": int(us.get_stat(int(StatType.BLOCK_CHANCE))),
        "port_block_override": (None if bcomp is None else bcomp.override.override),
        "port_block_modifiable": (None if bcomp is None else bcomp.override.is_modifiable),
        "per_source": per_source,
        "block_per_source": block_per_source,
        "port_active": {e.name: bool(e.is_active(ustate))
                        for e in st.effects.by_unit.get(carrier_id, [])
                        if e.name.startswith("ReinforcedHiveNode")},
        "port_active_names": {e.name for e in st.effects.active_effects(carrier_id, ustate)},
    }
    # (E) SIMULATION du tour SUIVANT du porteur sur CE MEME etat : `StartTurnOperation` bump le
    # compteur BRUT `UnitComponent.turnsStarted @+0x58` (= `GetStat(., 0xc)`), la condition bascule,
    # et le driver doit alors retirer l'override (part 8) / la modification (part 6). L'attendu se
    # lira du LIVE au round i+1 -- aucune valeur en dur.
    us.increment_base(int(StatType.TURNS_STARTED), 1)
    refresh_stat_modifier_effects(st, carrier_id)
    out["port_block_next_parity"] = int(us.get_stat(int(StatType.BLOCK_CHANCE)))
    out["port_armor_next_parity"] = int(us.get_stat(int(StatType.FIXED_ARMOR)))
    return out


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
    et le port doit rendre le MEME verdict que le flag live, POUR LES DEUX EFFETS (leur
    `CreateActiveCondition` est un corps FONDU : ils s'eteignent et se rallument ENSEMBLE).
    Les DEUX parites sont EXIGEES."""
    parities = {o["turns_started"] % 2 for o in hive_node_run}
    assert parities == {0, 1}, (
        "une seule parite de `turnsStarted` observee %s -- le test ne prouve rien, "
        "allonger ROUNDS" % sorted(parities))
    for o in hive_node_run:
        expected = (o["turns_started"] % 2 == 0)
        for eff in (EXTRA_ARMOR, EXTRA_BLOCK):
            assert o["live_active"].get(eff) == expected, (
                "live: %s actif=%s a turnsStarted=%d (attendu %s)"
                % (eff, o["live_active"].get(eff), o["turns_started"], expected))
            assert o["port_active"].get(eff) == expected, (
                "port: %s is_active=%s a turnsStarted=%d (attendu %s)"
                % (eff, o["port_active"].get(eff), o["turns_started"], expected))
            assert (eff in o["port_active_names"]) == expected
        assert o["live_active"].get(EXTRA_ARMOR) == o["live_active"].get(EXTRA_BLOCK), (
            "1108 et 1109 ne basculent PAS ensemble (%s) -- leur `CreateActiveCondition` est "
            "pourtant UN SEUL corps natif" % (o["live_active"],))


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


def test_extra_block_overrides_block_chance_to_the_config_constant(hive_node_run):
    """(D) `1109` = `AddStatOverrideEffectToOwner(1109, statType = 7 BlockChance,
    Direct(GetNumberConstant(0x2d = blockChance)))` -> `StatOverrideEffect$$ApplyInternal` =
    `ChangeStat(Position(7, part 7 = OVERRIDE), Direct(<comp+0x14>))`.

    L'attendu se DERIVE de gameconfig (`blockChance`), et le regime INACTIF se lit sur la part
    Initial LIVE du meme stat. Le port doit rendre la MEME valeur AVANT et APRES le driver."""
    val = ability_var("ReinforcedHiveNode", "blockChance", is_constant=True)
    assert val, "constante gameconfig `blockChance` introuvable"
    seen = {0: 0, 1: 0}
    for o in hive_node_run:
        seen[o["turns_started"] % 2] += 1
        if o["turns_started"] % 2 == 0:
            assert o["live_block"] == int(val), (
                "live: blockChance %d != la constante `blockChance` %d (1109 ACTIF)"
                % (o["live_block"], int(val)))
        else:
            assert o["live_block"] == o["live_block_initial"], (
                "live: blockChance %d != sa part Initial %d alors que 1109 est INACTIF"
                % (o["live_block"], o["live_block_initial"]))
        assert o["port_block_before"] == o["live_block"], (
            "port %d != live %d (turnsStarted=%d) au seed"
            % (o["port_block_before"], o["live_block"], o["turns_started"]))
        assert o["port_block_after"] == o["live_block"], (
            "APRES refresh: port %d != live %d (turnsStarted=%d)"
            % (o["port_block_after"], o["live_block"], o["turns_started"]))
    assert seen[0] and seen[1], "les DEUX parites sont exigees (%s)" % (seen,)


def test_block_override_is_in_the_override_slot_not_a_phantom_modification(hive_node_run):
    """(D bis) Le canal doit etre le BON : `ValueOverride` (`StatComponent+0x20`), pas une
    `ValueModification`. Une modification y serait FANTOME -- invisible tant que l'override est
    la (`GetOverrideValueWithModification` rend `override` seul quand `isModifiable = 0`), et de
    RETOUR integralement des que le driver joue le `RemoveOverride`. C'est exactement ce que
    (E) mesure."""
    val = ability_var("ReinforcedHiveNode", "blockChance", is_constant=True)
    for o in hive_node_run:
        assert not o["block_per_source"], (
            "modification par-source sur blockChance (%s) -- le natif n'en pose AUCUNE : "
            "`StatOverrideEffect$$ApplyInternal` ecrit la part 7, pas la part 5|9"
            % (o["block_per_source"],))
        if o["turns_started"] % 2 == 0:
            assert o["port_block_override"] == int(val), (
                "slot d'override = %s au lieu de %d (turnsStarted=%d)"
                % (o["port_block_override"], int(val), o["turns_started"]))
            assert o["port_block_modifiable"] is False, (
                "`isModifiable` doit etre FAUX (`ReinforcedHiveNode_ExtraBlockEffect$$.ctor` "
                "passe r8 = 0 a `StatOverrideEffect..ctor`, ecrit en +0x480)")
        else:
            assert o["port_block_override"] is None, (
                "override pose alors que 1109 est INACTIF (%s)" % (o["port_block_override"],))


def test_simulated_next_turn_reproduces_the_live_of_the_next_round(hive_node_run):
    """(E) LE DISCRIMINANT. Depuis l'etat charge au round i, on bump `turnsStarted` (mirror du
    bump de `IdunBattle.Operations.StartTurnOperation$$Execute`) et on rejoue le driver : le port
    doit reproduire ce que le LIVE affiche au round i+1. C'est la seule assertion qui SIMULE au
    lieu de re-seeder -- donc la seule qui exerce le `RemoveOverride`/`SetOverride` du driver sur
    un etat qui n'a pas ete re-capte.

    Sans le volet SEED du fix (delta capte verse dans `CAPTURED_SOURCE` au lieu du slot
    d'override), le port rendrait 100 la ou le natif retombe a 0."""
    pairs = 0
    for cur, nxt in zip(hive_node_run, hive_node_run[1:]):
        if nxt["turns_started"] != cur["turns_started"] + 1:
            continue                       # rounds non consecutifs pour le porteur : on saute
        pairs += 1
        assert cur["port_block_next_parity"] == nxt["live_block"], (
            "simulation du tour suivant : port blockChance %d != live %d au round suivant "
            "(turnsStarted %d -> %d)"
            % (cur["port_block_next_parity"], nxt["live_block"],
               cur["turns_started"], nxt["turns_started"]))
        assert cur["port_armor_next_parity"] == nxt["live_armor"], (
            "simulation du tour suivant : port fixedArmor %d != live %d au round suivant "
            "(turnsStarted %d -> %d)"
            % (cur["port_armor_next_parity"], nxt["live_armor"],
               cur["turns_started"], nxt["turns_started"]))
    assert pairs >= 2, (
        "moins de 2 transitions consecutives observees (%d) -- il en faut une dans CHAQUE sens "
        "(actif->inactif ET inactif->actif) pour que l'assertion prouve quelque chose" % pairs)
