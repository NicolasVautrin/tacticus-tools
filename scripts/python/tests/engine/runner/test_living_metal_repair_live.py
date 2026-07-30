"""#310 -- `LivingMetalRepairAbility` passe par `RepairUnitOperation`, PAS par `HealUnitOperation`.

CE QUE CES TESTS VERROUILLENT. L'artefact natif du trigger est
`IdunBattleLogic.Entities.Abilities.Active.Loki.LivingMetalRepairAbility$$CreateBehaviour`, relu
verbatim sur `rnca9r7q6c` :

    pct    = AbilityConfiguration.GetNumberConstant(config, 0x12)          # trait var livingMetalHp
    amount = DSLFormulas.PercentageOf(StatAmount(self, Health 5, Maximum 2), Direct(pct))
    return   DSLBehaviors.Repair(self, self, amount, AbilityOrEffect(...),
                                 RepairBehaviourOptions.ForRegenerate())

-> `RepairBehaviour$$Execute` -> `OperationProcessor$$RepairUnit` ->
`IdunBattle.Operations.RepairUnitOperation$$Execute`. Le port appelait `HealUnitOperation`. Les deux
Operations natives finissent sur le MEME `FillUpStatComponent$$FillUp`, donc l'etat PV bougeait --
mais elles ne sont PAS interchangeables, et l'ecart va DANS LES DEUX SENS :

  * PERMISSIF   : le gate `AttackQuery$$EntityCanBeRepaired` etait absent (test `..._refuses_...`) ;
  * RESTRICTIF  : `HealUnitOperation` porte un gate `HasEffect(entity, 0x4f Cursed)` que
                  `RepairUnitOperation` **n'a pas** -- le port REFUSAIT donc une regen que le natif
                  accorde (test `..._is_not_blocked_by_cursed`) ;
  * CHIFFRE     : le `RepairModifier` de `PredictRepair` (bonus de reparation RECUS par la cible)
                  n'existe QUE sur la voie repair (test `..._applies_the_repair_modifier`).

CRITERE BINAIRE : le trigger emprunte-t-il la chaine `Repair`, avec ses trois etages, ou la chaine
`Heal` ? Chaque test ci-dessous isole UN etage qui ne peut se comporter pareil des deux cotes.

MONTAGE : la fixture NOMMEE `_living_metal_stage` (jamais inline), qui porte les DEUX arms exiges --
une cible reparable (`necroWarden`, trait LivingMetal) et un temoin NON reparable (`ultraApothecary`,
non mecanique). La fixture DIT aussi ce qu'elle ne peut pas produire : aucun porteur de LivingMetal
ne peut faire refuser le gate (le trait implique `IsMechanical`), donc le regime R1 se joue sur le
temoin -- controle STRUCTUREL du cablage, pas scenario de jeu.

ASCII only (console cp1252).
"""
from __future__ import annotations

import os
import sys

import pytest

from engine.runner.snapshot import load_state
from engine.runner.components import HealthComponent, StatsComponent
from engine.runner.operations.triggers import turn_start_other_triggers
from engine.runner.operations.triggers.base import TriggerEvent
from engine.runner.operations.triggers.loki.living_metal import (
    LivingMetalRepairAbility, living_metal_pct, _round_half_even,
    REGENERATE_SCOPE, REGENERATE_REMOVE_EFFECTS)
from engine.entities.pathfinding.board import Board

sys.path.insert(0, os.path.dirname(__file__))
import _living_metal_stage as S                                # noqa: E402


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _board(rpc, rid):
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        return None
    return Board(bg["tiles"], adjacency="native_sym")


def _by_vis(state, vis):
    for uid, e in state.entities.items():
        sc = e.get_component(StatsComponent)
        if sc is not None and getattr(sc.ctx, "visual_id", None) == vis:
            return uid
    return None


def _hc(state, uid):
    return state.get_entity(uid).get_component(HealthComponent)


def _capture(rpc, rid, board):
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    if not (_ok(dv) and _ok(ob) and _ok(snap)):
        return None, None
    return load_state(dv, ob, snap, board=board), dv


@pytest.fixture(scope="module")
def living_metal_stage(build_runner, rpc):
    """Le montage #310, monte UNE fois pour tout le fichier (portee MODULE : chaque test ne fait
    ensuite que capturer l'etat et muter UNE variable dans sa copie OFFLINE)."""
    stage = S.build_stage(rpc, build_runner=build_runner)
    if stage.get("carrier") is None or stage.get("witness") is None:
        pytest.fail("montage LivingMetal NON INSTALLE : carrier=%s witness=%s"
                    % (stage.get("carrier"), stage.get("witness")))
    return stage


@pytest.fixture(scope="module")
def living_metal_state(living_metal_stage, rpc):
    """Capture OFFLINE du montage (state + decisionView). Chaque test la RE-CAPTURE pour lui-meme
    quand il mute l'etat -- cette fixture-ci ne sert qu'aux lectures non destructives."""
    rid = living_metal_stage["rid"]
    board = _board(rpc, rid)
    if board is None:
        pytest.fail("boardGraph indisponible -- le montage ne peut pas etre lu")
    state, dv = _capture(rpc, rid, board)
    if state is None:
        pytest.fail("capture du montage LivingMetal KO")
    return state, dv, board


def _fresh_state(rpc, stage, board):
    """Nouvelle capture INDEPENDANTE (chaque test qui MUTE en prend une a lui)."""
    state, dv = _capture(rpc, stage["rid"], board)
    if state is None:
        pytest.fail("re-capture du montage LivingMetal KO")
    return state, dv


def _regen_of(results, uid):
    """L'entree `living_metal_repair` du porteur dans le resultat de `turn_start_other_triggers`."""
    return next((r for r in results
                 if r.get("type") == "living_metal_repair" and r.get("unit") == uid), None)


# ── R0 -- NOMINAL : le montant, et il doit etre le MEME que le natif ────────────────────────────

def test_living_metal_regen_matches_the_native_at_turn_start(living_metal_stage, rpc):
    """LE test de non-regression du rebranchement : au turn-start de son proprietaire, le porteur
    regenere `round_half_even(pct % maxHP)` -- et le natif rend EXACTEMENT le meme delta.

    Ce test ne separe PAS heal de repair (les deux mutent les PV pareil sur un porteur sain) : c'est
    precisement son role. Il verrouille que le rebranchement n'a RIEN casse du regime nominal, qui
    est le seul que la mesure live de #203 couvrait."""
    rid = living_metal_stage["rid"]
    board = _board(rpc, rid)
    if board is None:
        pytest.fail("boardGraph indisponible")
    dv0 = rpc("decisionView", {"runnerId": rid, "maxRank": 1}, 60)
    cur = (dv0 or {}).get("currentPlayer")
    state, dv = _capture(rpc, rid, board)
    if state is None:
        pytest.fail("capture pre-endturn KO")
    cid = _by_vis(state, S.CARRIER_VIS)
    if cid is None:
        pytest.fail("porteur absent offline")
    hc = _hc(state, cid)
    assert int(hc.hp) < int(hc.hp_max), (
        "le montage doit livrer un porteur BLESSE (--unit-stat RemainingHealth) ; hp=%d max=%d"
        % (int(hc.hp), int(hc.hp_max)))

    # equipe du porteur = celle dont le turn-start declenche la regen (`OwnerIsActor`).
    from engine.runner.components import OwnerComponent
    p_team = int(state.get_entity(cid).get_component(OwnerComponent).player)
    pct = living_metal_pct()
    expected = min(_round_half_even(int(hc.hp_max) * pct / 100),
                   int(hc.hp_max) - int(hc.hp))
    assert expected > 0, "montant de regen degenere (pct=%d maxHP=%d)" % (pct, int(hc.hp_max))

    # --- OFFLINE ---------------------------------------------------------------------------------
    off_pre = int(hc.hp)
    res = turn_start_other_triggers(state, p_team)
    entry = _regen_of(res, cid)
    assert entry is not None, "aucune regen LivingMetal offline au turn-start du proprietaire"
    assert "repaired" in entry, (
        "l'entree doit porter `repaired` -- le mutateur est RepairUnitOperation (#310), pas "
        "HealUnitOperation ; entree=%s" % entry)
    off_delta = int(_hc(state, cid).hp) - off_pre

    # --- SCOPING : le turn-start ADVERSE ne regenere pas (`OwnerIsActor`) -------------------------
    state2, _ = _capture(rpc, rid, board)
    cid2 = _by_vis(state2, S.CARRIER_VIS)
    other = 1 - p_team if p_team in (0, 1) else (p_team + 1)
    assert _regen_of(turn_start_other_triggers(state2, other), cid2) is None, (
        "le porteur regenere au tour ADVERSE -- le scoping OwnerIsActor a saute")

    # --- LIVE : on amene le tour du proprietaire et on mesure le delta natif ----------------------
    if cur == p_team:
        rpc("applyAction", {"runnerId": rid, "actions": [{"kind": "endturn"}]}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    live_pre = next((int((u.get("stats") or {}).get("health") or 0)
                     for u in (snap.get("units") or []) if u.get("entityId") == cid), None)
    rpc("applyAction", {"runnerId": rid, "actions": [{"kind": "endturn"}]}, 60)
    snap2 = rpc("combatSnapshot", {"runnerId": rid}, 60)
    live_post = next((int((u.get("stats") or {}).get("health") or 0)
                      for u in (snap2.get("units") or []) if u.get("entityId") == cid), None)
    if live_pre is None or live_post is None:
        pytest.fail("combatSnapshot n'expose pas les PV du porteur (pre=%s post=%s)"
                    % (live_pre, live_post))
    live_delta = live_post - live_pre

    print("\n[LIVINGMETAL/nominal] pct=%d maxHP=%d attendu=%d offline=%d live=%d"
          % (pct, int(hc.hp_max), expected, off_delta, live_delta))
    assert off_delta == expected, "offline %d != attendu %d" % (off_delta, expected)
    assert live_delta == off_delta, (
        "le natif a regenere %d, le port %d -- le rebranchement a change le montant"
        % (live_delta, off_delta))


# ── R1 -- GATE : une cible NON reparable n'est pas regeneree ────────────────────────────────────

def test_living_metal_refuses_a_non_repairable_target(living_metal_state):
    """LE CRITERE de #310 : une unite NON reparable est-elle regeneree par le trigger ?

    `IdunBattle.Entities.UnitExtensions$$IsAffectedByHealType(unit, 1)` = `HasTrait(0x421
    AffectedByHealAndRepair) || IsMechanical(unit)` -- FAUX pour un Imperial non mecanique. Le natif
    sort alors de `RepairUnitOperation$$Execute` sur un `OperationResult` VIDE : aucune mutation.
    L'ancien cablage passait par `HealUnitOperation`, qui ne consulte JAMAIS ce predicat : il aurait
    soigne. C'est le ROUGE de ce lot.

    CONTROLE STRUCTUREL, et la fixture le dit : ce regime n'est pas atteignable en bataille (porter
    LivingMetal implique `IsMechanical`). On exerce le gate PAR LE CHEMIN EXACT du trigger --
    `LivingMetalRepairAbility(owner_id=<temoin>).execute_behaviour(...)` -- ce qui est exactement la
    question posee. Le meme test verifie que le temoin est bien SOIGNABLE, sinon il ne separerait
    pas « non reparable » de « cible degeneree »."""
    state, _, _ = living_metal_state
    wid = _by_vis(state, S.WITNESS_VIS)
    if wid is None:
        pytest.fail("temoin %s absent offline" % S.WITNESS_VIS)
    from engine.runner.abilities.attack_query import (entity_can_be_healed,
                                                      entity_can_be_repaired,
                                                      is_affected_by_heal_type)
    hw = _hc(state, wid)
    assert int(hw.hp) < int(hw.hp_max), (
        "le temoin doit etre BLESSE : sinon son refus s'expliquerait par IsDamagedUnit et le "
        "controle ne separerait plus le gate IsAffectedByHealType")
    assert not is_affected_by_heal_type(state, wid, 1), (
        "%s ne doit PAS etre affecte par le heal-type 1 (Mechanical)" % S.WITNESS_VIS)
    assert entity_can_be_healed(state, wid, wid, scope=0, remove_effects=False), (
        "le meme temoin DOIT etre soignable -- sans ca le controle ne separe rien")
    assert not entity_can_be_repaired(state, wid, wid, scope=REGENERATE_SCOPE,
                                      remove_effects=REGENERATE_REMOVE_EFFECTS), (
        "EntityCanBeRepaired doit REFUSER une cible non mecanique")

    pre = int(hw.hp)
    ability = LivingMetalRepairAbility(wid)
    out = ability.execute_behaviour(state, TriggerEvent(
        event_id=ability.event_id, actor_id=wid, target_id=wid,
        ranged=False, profile=None, player_id=0))
    print("\n[LIVINGMETAL/gate] temoin=%s hp=%d/%d -> %s"
          % (S.WITNESS_VIS, pre, int(hw.hp_max), out))
    assert out is None, (
        "le trigger a REGENERE une cible non reparable (%s) -- c'est EXACTEMENT le residu #310 "
        "(HealUnitOperation ne consulte pas EntityCanBeRepaired)" % out)
    assert int(_hc(state, wid).hp) == pre, "l'Operation refusee ne doit RIEN muter"


# ── R2 -- CURSED : le gate du HEAL ne doit PAS s'appliquer a la regen ───────────────────────────

def test_living_metal_is_not_blocked_by_cursed(living_metal_stage, rpc):
    """L'ecart RESTRICTIF, celui que l'ancien cablage produisait a l'insu de tous.

    `IdunBattle.Operations.HealUnitOperation$$Execute` fait
    `EntityExtensions.HasEffect(entity, 0x4f = 79 Cursed)` et force le montant a 0.
    `IdunBattle.Operations.RepairUnitOperation$$Execute` **n'a aucun test de ce genre** : son seul
    equivalent est `UnitExtensions$$HasHealBlockers`, qui lit le dict `HealthComponent+0x78` -- un
    conteneur DISTINCT, et aucune classe `CursedEffect` n'existe dans le build (l'EffectType 79
    n'est lu QUE par le heal).

    Donc : un porteur LivingMetal sous `Cursed` DOIT regenerer. L'ancien port rendait 0. Une seule
    variable change par rapport a R0 : l'effet pose sur l'etat OFFLINE."""
    board = _board(rpc, living_metal_stage["rid"])
    if board is None:
        pytest.fail("boardGraph indisponible")
    state, _ = _fresh_state(rpc, living_metal_stage, board)
    cid = _by_vis(state, S.CARRIER_VIS)
    if cid is None:
        pytest.fail("porteur absent offline")
    from engine.runner.components import OwnerComponent
    p_team = int(state.get_entity(cid).get_component(OwnerComponent).player)
    hc = _hc(state, cid)
    pct = living_metal_pct()
    expected = min(_round_half_even(int(hc.hp_max) * pct / 100), int(hc.hp_max) - int(hc.hp))
    assert expected > 0, "montant degenere"

    # SEULE variable modifiee : Cursed sur le porteur.
    state.effects.add_effect(cid, S.make_effect("Cursed", S.CURSED_EFFECT_TYPE, None, cid))
    assert state.effects.has_effect(cid, effect_type=S.CURSED_EFFECT_TYPE), "Cursed non pose"

    off_pre = int(hc.hp)
    entry = _regen_of(turn_start_other_triggers(state, p_team), cid)
    off_delta = int(_hc(state, cid).hp) - off_pre
    print("\n[LIVINGMETAL/cursed] attendu=%d offline=%d entry=%s" % (expected, off_delta, entry))
    assert entry is not None and off_delta == expected, (
        "un porteur sous Cursed n'a PAS regenere (delta=%d, attendu %d) -- le gate 0x4f de "
        "HealUnitOperation s'applique encore, alors que RepairUnitOperation ne le porte pas"
        % (off_delta, expected))


# ── R3 -- MODIFIER : le RepairModifier n'existe QUE sur la voie repair ──────────────────────────

def test_living_metal_applies_the_repair_modifier(living_metal_stage, rpc):
    """L'ecart CHIFFRE, et le seul qui ait un poseur reel dans le jeu.

    `IdunBattle.Core.Services.DamagePrediction$$PredictRepair` etage 1 :

        if (EntityExtensions.IsActor(caster))
            predicted = (int)( Fix64(mod.flatBonus + amount) * mod.multiplier )

    ou `mod` = `RepairCalculations$$CalculateRepairModifierForPrediction`, le FOLD des descripteurs
    `BaseEffect$$RepairBonus` portes par la CIBLE. `NanoscarabRepairProtocolsEffect` (1545) en est
    un : `ForAddition`, add = `hpToRepair[level]`. Son poseur est `necroReanimator`, qui repare
    justement ses allies MECHANICAL -- c'est-a-dire, chez les Necrons, exactement les porteurs de
    LivingMetal. Le caster de la regen est le porteur lui-meme, donc `IsActor` est vrai et l'etage
    s'applique.

    La voie `Heal` n'a AUCUN equivalent : l'ancien port rendait le montant nu.

    L'effet est pose sur l'etat OFFLINE plutot que caste live parce que `necroReanimator` est HORS
    du pool spawnable (l'un des 17 lineup absents du seed BC, cf. `runner.md` §1bis) : le monter
    live exigerait `catalog_inject` + le pilotage d'un cast de MoW. Ce qui est verrouille ici est
    donc la CONFORMITE AU DECOMPILE de l'etage, pas sa mesure live -- et c'est dit."""
    board = _board(rpc, living_metal_stage["rid"])
    if board is None:
        pytest.fail("boardGraph indisponible")
    state, _ = _fresh_state(rpc, living_metal_stage, board)
    cid = _by_vis(state, S.CARRIER_VIS)
    if cid is None:
        pytest.fail("porteur absent offline")
    from engine.runner.components import OwnerComponent
    from engine.entities.effects.magnitude import ability_var
    p_team = int(state.get_entity(cid).get_component(OwnerComponent).player)
    hc = _hc(state, cid)
    pct = living_metal_pct()
    base = _round_half_even(int(hc.hp_max) * pct / 100)
    missing = int(hc.hp_max) - int(hc.hp)

    sc = state.get_entity(cid).get_component(StatsComponent)
    mult = int(getattr(sc.ctx, "ability_variables_multiplier", 100) or 100)
    lvl = getattr(sc.ctx, "active_ability_level", None) or getattr(sc.ctx, "passive_ability_level", None)
    bonus = ability_var(S.NANOSCARAB_EFFECT_NAME, "hpToRepair", lvl, multiplier_pct=mult)
    if not bonus:
        pytest.fail("hpToRepair de %s illisible (lvl=%s mult=%d) -- le regime n'a plus de magnitude"
                    % (S.NANOSCARAB_EFFECT_NAME, lvl, mult))
    expected = min(base + int(bonus), missing)
    assert expected > base, (
        "le montage n'est pas discriminant : le manque (%d) sature deja le montant nu (%d)"
        % (missing, base))

    # SEULE variable modifiee : le bonus de reparation porte par la CIBLE.
    state.effects.add_effect(cid, S.make_effect(
        S.NANOSCARAB_EFFECT_NAME, S.NANOSCARAB_EFFECT_TYPE, lvl, cid, multiplier_pct=mult))

    off_pre = int(hc.hp)
    entry = _regen_of(turn_start_other_triggers(state, p_team), cid)
    off_delta = int(_hc(state, cid).hp) - off_pre
    print("\n[LIVINGMETAL/modifier] base=%d hpToRepair(lvl=%s mult=%d)=%s attendu=%d offline=%d"
          % (base, lvl, mult, bonus, expected, off_delta))
    assert entry is not None, "aucune regen"
    assert off_delta == expected, (
        "offline %d != base %d + RepairModifier %d -- l'etage 1 de PredictRepair n'est pas "
        "traverse (c'est ce que HealUnitOperation ignorait)" % (off_delta, base, int(bonus)))


# ── ORDRE des etages : le cap de GROUPE vient APRES le modifier ─────────────────────────────────

def test_group_cap_is_applied_after_the_repair_modifier():
    """GARDE D'ORDRE, sans live -- `PredictRepair` applique le `RepairModifier` PUIS
    `Min(amount, GetGroupUnitHealLimit)`. L'ancien trigger faisait le cap A LA MAIN, AVANT.

    L'ordre est OBSERVABLE des que les deux etages mordent : capper d'abord puis multiplier rend
    `cap x mult`, multiplier d'abord puis capper rend `cap`. On l'exerce sur `predict_repair`
    directement, avec un etat NU (aucun runner) : un `State` a une seule entite multi-membres.

    Ce test ne depend d'aucune bataille -- c'est une propriete de la fonction, et c'est justement ce
    qui le rend robuste au roster."""
    from engine.runner.state import State, Entity
    from engine.runner.operations.repair import predict_repair
    from engine.services.trait_damage_limits import get_group_unit_heal_limit
    from engine.entities.unit_context import UnitContext

    # hp = 1500 sur 4000 / 4 membres : DELIBEREMENT hors frontiere de membre. A 1000 (pile une
    # frontiere) le cap vaut 0 et le test ne separerait plus « cappe » de « refuse ».
    hp, hp_max, members = 1500, 4000, 4
    st = State()
    e = Entity(1)
    e.add_component(HealthComponent(hp=hp, hp_max=hp_max))
    e.add_component(StatsComponent(UnitContext(entity_id=1, visual_id="necroSmnSwarm",
                                               number_of_members=members)))
    st.entities[1] = e

    cap = get_group_unit_heal_limit(hp_max, members, hp)
    assert 0 < cap < hp_max - hp, (
        "le montage doit exercer un cap NON degenere ET plus serre que MaxFillUp (cap=%d)" % cap)
    got = predict_repair(st, None, 1, cap + 5000, scope=1)
    print("\n[LIVINGMETAL/order] cap=%d predict(cap+5000, scope=1)=%d" % (cap, got))
    assert got == cap, "scope=1 doit capper a GetGroupUnitHealLimit (%d), obtenu %d" % (cap, got)
    # scope=0 : la branche n'est PAS prise (les 12 autres call-sites natifs passent `ForRepair`).
    got0 = predict_repair(st, None, 1, cap + 5000, scope=0)
    assert got0 == hp_max - hp, (
        "scope=0 ne doit capper qu'au MaxFillUp (%d), obtenu %d" % (hp_max - hp, got0))


# ── GARDE DE CABLAGE : le module ne doit plus connaitre `HealUnitOperation` ─────────────────────

def test_living_metal_module_does_not_call_heal_unit_operation():
    """CLIQUET de non-regression : le mutateur du trigger est `RepairUnitOperation`.

    Une garde par IMPORT plutot que par comportement, parce que c'est le cablage lui-meme qui a
    derape (#310) et qu'un futur refactor pourrait le re-brancher sans qu'aucun des tests ci-dessus
    ne rougisse dans le regime nominal -- les deux Operations mutent les PV pareil sur un porteur
    sain, et c'est PRECISEMENT pour ca que le bug a survecu."""
    import inspect
    import engine.runner.operations.triggers.loki.living_metal as LM
    src = inspect.getsource(LM)
    body = src.split('"""', 2)[-1]                    # hors docstring de module
    assert "HealUnitOperation" not in body, (
        "living_metal.py reference encore HealUnitOperation dans son CODE -- l'artefact natif est "
        "un Repair(., ForRegenerate)")
    assert "RepairUnitOperation" in body, "living_metal.py doit appeler RepairUnitOperation"
    assert (REGENERATE_SCOPE, REGENERATE_REMOVE_EFFECTS) == (1, False), (
        "RepairBehaviourOptions$$ForRegenerate ecrit (+0x10 = 1, +0x14 = 0)")
