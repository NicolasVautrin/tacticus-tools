"""AnvilShield (#100) — les DEUX volets qui etaient du DEAD-CODE : `ApplyStun` + `FrozenAttackerAdvantage`.

i2 du passif `AnvilShield` (`spaceRockfist` << Arjac >>) :
  « Arjac blocks an additional 728 Damage and when he Blocks he covers the attacker's hex in Ice.
    **If Arjac is below 35% Health, or if his attacker is on a hex covered in Ice, he gains +20% Block
    chance and if he blocks a melee attack, the attacker is Stunned until the end of the attacker's
    next turn.** »

Artefacts natifs (build gqfc5mff6c) :
  - `IdunBattle.Entities.Effects.Loki.AnvilShield_BlockChanceBelowHealthCapEffect$$CreateActiveCondition`
      `AmountIsEqualOrGreater(Direct(GetNumberConstant(0x4f=healthPct)), StatAmount(Self, 5=HEALTH,
       1=CURRENT_PCT))` -> le gate sante est un **POURCENTAGE** (`StatPart.CURRENT_PCT`).
  - `IdunBattleLogic.Entities.Abilities.Triggered.Loki.AnvilShieldAbility_FrozenAttackerAdvantage$$CreateTrigger`
      `On(0x2b=PreUnitAbility) & IsNormalAttack & OwnerIsTarget & IsUnitOnTileWithEffect(caster, Ice)
       & !HasEffect(Self,1200,active) & !HasEffect(Self,1201,active)`
    -> `$$CreateBehaviour` = `AddStaticStatModifierEffect(Self, 1201, stat 7, blockChance)`.
  - `IdunBattle.Entities.Effects.Loki.AnvilShield_FrozenAttackerAdvantageEffect$$CreateTargetTrigger`
      `On(0xe=UnitPostAbility) & AreEqual(target, EffectSource(this))` -> le bonus ne vit QUE le temps
      de l'ability qui l'a declenche.
  - `...AnvilShieldAbility_ApplyStun$$CreateTrigger` `On(0x3d=UnitBlocked) & OwnerIsTarget &
      IsMeleeAttack & !HasTrait(caster, Steppable) & IsUnit & IsAlive &
      (HasEffect(target,1200,active) | HasEffect(target,1201,active))`
    -> `$$CreateBehaviour` = `AddEffect(1162 Stunned, source=Self, cible=caster,
       duree=If(IsTurnOf(caster), TurnsUntilEndOfCurrentPlayersNextTurn, TurnsFromRounds(1)))`.

Ce que ces tests GARDENT (classe de bug = le no-op SILENCIEUX) :
  - le vecteur `On(PreUnitAbility=0x2b)` (nouveau) et son pendant `On(UnitPostAbility=0xe)` ;
  - le gate `HasEffect(..., activeOnly)` (4e argument natif : le flag `EffectComponent+0x5c`, PAS un
    minLevel) et donc l'`ActiveCondition` de 1200 ;
  - le canal STAT 7 (BLOCK_CHANCE) des deux effets, et son driver d'ActiveCondition.

ASCII only (cp1252).
"""
from __future__ import annotations

import pytest

import hexgeo
from engine.entities.effect_type import EffectType
from engine.entities.pathfinding.board import Board
from engine.entities.stats import StatType
from engine.runner.snapshot import load_state
from engine.runner.components import PositionComponent, StatsComponent, HealthComponent
from engine.runner.operations.triggers.dispatch import (after_hit_normal_attack,
                                                        pre_unit_ability_triggers)
from engine.runner.operations.refresh_effects import refresh_stat_modifier_effects
from engine.runner.abilities.base import convert_rounds_to_turns

ARJAC = "spaceRockfist"
ATTACKER = "templSwordBrother"          # MELEE (le gate `IsMeleeAttack` d'ApplyStun l'exige)
ICE = int(EffectType.Ice)                                            # 0x11 = 17
STUNNED = int(EffectType.Stunned)                                    # 0x48a = 1162
CAP = int(EffectType.AnvilShield_BlockChanceBelowHealthCap)          # 0x4b0 = 1200
FROZEN = int(EffectType.AnvilShield_FrozenAttackerAdvantage)         # 0x4b1 = 1201
NORMAL_ATTACK = 69


# --------------------------------------------------------------------------- helpers live
def _dv(rpc, rid):
    return rpc("decisionView", {"runnerId": rid, "maxRank": 99, "allAbilities": True}, 150)


def _act(rpc, rid, action):
    return rpc("applyAction", {"runnerId": rid, "action": action, "captureEvents": False}, 150)


def _alive(dec, vis):
    return [u for u in (dec.get("units") or []) if u.get("visualId") == vis and u.get("alive")]


def _by_id(dec, uid):
    return next((u for u in (dec.get("units") or []) if u.get("id") == uid), None)


def _pos(u):
    p = (u or {}).get("pos") or {}
    return (p.get("col"), p.get("row"))


def _effs(u, effect_type):
    return [e for e in ((u or {}).get("effects") or []) if e.get("effectType") == effect_type]


def _iced(rpc, rid):
    """{(col,row): [effets Ice]} — l'ORACLE natif des tuiles glacees."""
    tm = rpc("tileMeta", {"runnerId": rid}, 90)
    out = {}
    for t in (tm.get("tiles") or []):
        ic = [e for e in (t.get("effects") or []) if e.get("effectType") == ICE]
        if ic:
            out[(t.get("col"), t.get("row"))] = ic
    return out


def _stat(rpc, rid, uid, key):
    snap = rpc("combatSnapshot", {"runnerId": rid}, 120)
    for u in (snap.get("units") or []):
        if u.get("entityId") == uid:
            return (u.get("stats") or {}).get(key)
    return None


def _movable(rpc, rid, uid):
    mov = rpc("aiMovableTiles", {"runnerId": rid, "side": "all"}, 90)
    for m in (mov.get("units") or []):
        if m.get("unitId") == uid:
            return [(t["col"], t["row"]) for t in (m.get("tiles") or [])]
    return []


def _drive_to(rpc, rid, uid, anchor, want):
    """DRIVE des DEUX camps (runner.md §4 : `applyAction` ne verifie pas la propriete de l'unite) :
    place `uid` a la distance hex `want` d'`anchor`. On ne SUBIT jamais les spawns."""
    tiles = _movable(rpc, rid, uid)
    if not tiles:
        return None
    best = min(tiles, key=lambda t: abs(hexgeo.distance(t, anchor) - want))
    _act(rpc, rid, {"kind": "move", "unitId": uid, "to": {"col": best[0], "row": best[1]}})
    return hexgeo.distance(best, anchor)


def _bring_adjacent(rpc, rid, caster_vis, enemy_vis, rounds=30):
    """Amene `caster_vis` au CONTACT (dist 1) d'un `enemy_vis` en ne deplacant QUE le caster.

    ⚠ On ne DRIVE PAS Arjac : le faire marcher vers mes unites declenche leur OVERWATCH (elles
    l'attaquent), il BLOQUE (`--block-target 100`) et `ApplyIce` glace LEUR tuile -> le controle
    negatif du coup #1 (« attaquant HORS glace ») serait deja pollue au moment de la 1re attaque.
    """
    for _ in range(rounds):
        dec = _dv(rpc, rid)
        me = _alive(dec, caster_vis)
        ens = [u for u in _alive(dec, enemy_vis) if _pos(u)[0] is not None]
        if not me or not ens:
            _act(rpc, rid, {"kind": "endturn"})       # deep-strike : pas encore atterri
            continue
        caster, tgt = me[0], ens[0]
        if dec.get("currentPlayer") != caster.get("owner"):
            _act(rpc, rid, {"kind": "endturn"})
            continue
        if hexgeo.distance(_pos(caster), _pos(tgt)) <= 1:
            return dec, caster, tgt
        if _drive_to(rpc, rid, caster["id"], _pos(tgt), 1) is None:
            _act(rpc, rid, {"kind": "endturn"})
    return None, None, None


def _ensure_off_ice(rpc, rid, att_id, arj_id, tries=4):
    """Place l'attaquant sur une tuile ADJACENTE a Arjac qui n'est PAS glacee.

    ⚠ Necessaire : l'approche elle-meme produit deja de l'Ice. En arrivant au contact, l'OVERWATCH
    d'Arjac (effet pose par l'IA au deploiement cote a-units) l'attaque, la RIPOSTE de l'attaquant
    frappe Arjac, Arjac BLOQUE (`--block-target 100`) et `ApplyIce` glace la tuile ou il se tient.
    On repositionne donc l'attaquant sur une tuile propre pour disposer d'un CONTROLE NEGATIF reel.
    """
    for _ in range(tries):
        dec = _dv(rpc, rid)
        att, arj = _by_id(dec, att_id), _by_id(dec, arj_id)
        if att is None or arj is None or not att.get("alive"):
            return None, None, None
        iced = _iced(rpc, rid)
        if hexgeo.distance(_pos(att), _pos(arj)) <= 1 and _pos(att) not in iced:
            return dec, att, arj
        if dec.get("currentPlayer") != att.get("owner"):
            _act(rpc, rid, {"kind": "endturn"})
            continue
        cand = [t for t in _movable(rpc, rid, att_id)
                if hexgeo.distance(t, _pos(arj)) <= 1 and t not in iced]
        if not cand:
            _act(rpc, rid, {"kind": "endturn"})
            continue
        _act(rpc, rid, {"kind": "move", "unitId": att_id,
                        "to": {"col": cand[0][0], "row": cand[0][1]}})
    return None, None, None


def _offline(rpc, rid, dec=None):
    """`State` OFFLINE (board + effets d'UNITE + effets de TUILE) reconstruit depuis la capture LIVE.

    `tiles=tileMeta` (#102) : les effets portes par les TUILES (ici l'Ice pose par `ApplyIce`) sont
    seedes PAR LE LOAD. Sans ce canal, le rejeu offline repartait d'un plateau vierge et la
    precondition `IsUnitOnTileWithEffect(caster, Ice)` du `CreateTrigger` de
    `AnvilShieldAbility_FrozenAttackerAdvantage` etait FAUSSE offline alors qu'elle etait VRAIE live
    -> le test devait re-poser la glace a la main (ce qui court-circuitait justement ce qu'il garde)."""
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    board = Board(bg["tiles"], adjacency="evenq") if bg.get("tiles") else None
    dec = dec or _dv(rpc, rid)
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 120)
    tm = rpc("tileMeta", {"runnerId": rid}, 60)
    return load_state(dec, ob, snap, board=board, tiles=tm), dec, board


def _off_effect(state, uid, effect_type):
    if state.effects is None:
        return None
    for e in state.effects.by_unit.get(int(uid), []):
        if not e.consumed and e.effect_type == int(effect_type):
            return e
    return None


def _off_block_chance(state, uid):
    sc = state.get_entity(uid).get_component(StatsComponent)
    return sc.ctx.stat(StatType.BLOCK_CHANCE)


# --------------------------------------------------------------------------- tests
def test_anvil_shield_stuns_blocked_melee_attacker_on_ice_live(live_session, rpc, build_runner):
    """DISCRIMINANT DETERMINISTE du volet `ApplyStun` + de son prerequis `FrozenAttackerAdvantage`.

    Arjac cote a-units avec `--block-target 100,500` : le BLOCAGE est CRAFTE (100 %), pas espere -> la
    SEULE variable entre les deux coups est « l'attaquant est-il sur une tuile GLACEE ». Arjac reste a
    PLEINS PV (donc 1200 INACTIF) : le gate d'`ApplyStun` ne peut venir QUE de 1201.

      coup #1, attaquant HORS glace : Arjac bloque -> `ApplyIce` glace la tuile de l'attaquant,
               mais AUCUN Stun (gate 1200|1201 faux)                      == CONTROLE NEGATIF ;
      coup #2, MEME tuile, desormais GLACEE : `On(0x2b)` pose 1201 -> gate vrai -> **Stunned**.
    """
    rid = build_runner("92201", extra=["--p-units", f"{ATTACKER},templAggressor",
                                       "--a-units", ARJAC,
                                       "--block-target", "100,500",
                                       "--hp-target", "400000", "--hp-player", "400000"])["rid"]
    assert not _iced(rpc, rid), "le plateau porte deja de l'Ice au build : l'observation ne serait pas causale"

    dec, att, arj = _bring_adjacent(rpc, rid, ATTACKER, ARJAC)
    if att is None:
        pytest.skip("attaquant/Arjac injoignables")
    assert not _effs(arj, CAP), (
        "1200 est ACTIF alors qu'Arjac est a pleins PV -> l'ActiveCondition healthPct est cassee "
        "(le test ne discriminerait plus 1201)")

    # --- COUP #1 = LA RIPOSTE DE L'APPROCHE (controle negatif, obtenu naturellement).
    # En arrivant au contact, l'OVERWATCH d'Arjac (a-units = cote IA) l'attaque, l'attaquant RIPOSTE
    # au corps a corps, Arjac BLOQUE (100 %) -> `ApplyIce` glace la tuile de l'attaquant. Cette
    # attaque MELEE bloquee s'est produite alors que l'attaquant n'etait PAS encore sur la glace et
    # qu'Arjac est a pleins PV (1200 inactif) : le gate `HasEffect(1200|1201, activeOnly)` etait donc
    # FAUX -> l'attaquant ne doit PAS etre Stunned.
    iced = _iced(rpc, rid)
    assert _pos(att) in iced, (
        "la tuile de l'attaquant n'est pas glacee apres l'echange de l'approche -> aucun blocage "
        "melee n'a eu lieu, le discriminant ne tient pas (verifier --block-target)")
    assert {e.get("source") for e in iced[_pos(att)]} == {arj["id"]}, (
        "l'Ice de la tuile de l'attaquant ne vient pas d'Arjac -> source d'Ice parasite")
    assert not _effs(att, STUNNED), (
        "CONTROLE NEGATIF ROMPU : l'attaquant est Stunned alors qu'il n'etait PAS sur la glace au "
        "moment du coup et qu'Arjac est a pleins PV -> le gate `HasEffect(1200|1201, activeOnly)` "
        "d'ApplyStun ne filtre plus")

    # --- capture AVANT le coup #2 : c'est l'etat que le port doit rejouer.
    state, dec_pre, board = _offline(rpc, rid)
    if board is None:
        pytest.skip("boardGraph indispo (rejeu offline impossible)")

    # --- COUP #2 (attaquant DESORMAIS sur la glace) : 1201 -> gate vrai -> Stunned.
    dec2 = _dv(rpc, rid)
    if dec2.get("currentPlayer") != att["owner"]:
        _act(rpc, rid, {"kind": "endturn"})
        _act(rpc, rid, {"kind": "endturn"})
    r = _act(rpc, rid, {"kind": "ability", "casterId": att["id"], "targetId": arj["id"],
                        "abilityType": NORMAL_ATTACK})
    if not (isinstance(r, dict) and r.get("ok")):
        pytest.skip(f"attaque #2 KO: {str(r)[:150]}")
    dec3 = _dv(rpc, rid)
    att3 = _by_id(dec3, att["id"])
    stun = _effs(att3, STUNNED)
    assert stun, ("l'attaquant BLOQUE depuis une tuile GLACEE n'est pas Stunned -> le volet ApplyStun "
                  "(ou son prerequis FrozenAttackerAdvantage / le vecteur On(PreUnitAbility)) est muet")
    assert stun[0].get("source") == arj["id"], (
        f"source du Stunned={stun[0].get('source')}, attendu {arj['id']} (Arjac = `Self@0x148`)")
    # DUREE : `If(IsTurnOf(caster), TurnsUntilEndOfCurrentPlayersNextTurn, TurnsFromRounds(1))` ; le
    # coup est porte PENDANT le tour de l'attaquant -> branche VRAIE = `ConvertRoundsToTurns(1) + 1`.
    expected = convert_rounds_to_turns(state, 1) + 1
    assert stun[0].get("remaining") == expected, (
        f"duree Stunned live={stun[0].get('remaining')} != ConvertRoundsToTurns(1)+1={expected} "
        f"(facteur={state.turn_order_player_count})")
    # 1201 est TRANSITOIRE : consomme par son propre trigger `On(UnitPostAbility)` a la fin de l'ability.
    arj3 = _by_id(dec3, arj["id"])
    assert not _effs(arj3, FROZEN), (
        "1201 survit a l'attaque -> le trigger `On(UnitPostAbility)` de l'effet ne le consomme pas "
        "(le +20 % block deviendrait permanent)")

    # --- REJEU OFFLINE de la MEME sequence depuis la capture pre-coup#2 : memes verdicts.
    # #102 : la precondition « tuile glacee » vient desormais DU LOAD (`load_state(tiles=tileMeta)`),
    # plus d'une re-pose manuelle. C'est le discriminant du vecteur de seeding : si `load_state`
    # n'hydratait pas les effets de TUILE, l'assertion ci-dessous tomberait et tout le rejeu
    # `On(PreUnitAbility)` -> 1201 -> Stun serait muet offline alors qu'il est vrai live.
    apc = state.get_entity(att["id"]).get_component(PositionComponent)
    att_tile = board.id_at(apc.col, apc.row)
    assert state.effects.has_effect(att_tile, effect_type=ICE), (
        f"l'etat CHARGE ne porte pas l'Ice de la tuile {(apc.col, apc.row)} (tile-id {att_tile}) "
        f"alors que le live la porte -> le seed des effets de TUILE de `load_state` est muet (#102)")
    assert _off_effect(state, att["id"], STUNNED) is None
    pre = _off_block_chance(state, arj["id"])
    pre_unit_ability_triggers(state, att["id"], arj["id"], ranged=False, profile="Power",
                              ability_type=1013)
    assert _off_effect(state, arj["id"], FROZEN) is not None, (
        "offline : `On(PreUnitAbility)` ne pose pas 1201 alors que l'attaquant est sur la glace")
    # +20 sur le canal STAT 7, CLAMPE a 100 (`StatComponent.GetClampedValue`, STAT_CLAMP_MAX[7]) — ici
    # le block est crafte a 100 donc l'observable du canal est le clamp ; la valeur EXACTE +20 est
    # gardee par `test_anvil_shield_block_chance_cap_activates_below_health_pct_live` (base 0).
    assert _off_block_chance(state, arj["id"]) == min(100, pre + 20), (
        f"offline : blockChance {pre} -> {_off_block_chance(state, arj['id'])} (attendu "
        f"{min(100, pre + 20)}, canal stat 7 de 1201)")
    after_hit_normal_attack(state, att["id"], arj["id"], ranged=False, profile="Power",
                            did_block=True)
    off_stun = _off_effect(state, att["id"], STUNNED)
    assert off_stun is not None, "offline : l'attaquant bloque depuis la glace n'est pas Stunned"
    assert off_stun.source == arj["id"]
    assert off_stun.remaining_turns == expected, (
        f"offline : duree Stunned={off_stun.remaining_turns} != live/{expected}")
    assert _off_effect(state, arj["id"], FROZEN) is None, (
        "offline : 1201 n'est pas consomme par `On(UnitPostAbility)` en fin d'attaque")
    assert _off_block_chance(state, arj["id"]) == pre, (
        "offline : le +20 % block n'est pas reverte au retrait de 1201 (stat 7 fuit)")


def test_anvil_shield_stun_via_health_cap_branch_and_gates_live(live_session, rpc, build_runner):
    """GENERALISATION — l'AUTRE branche du gate d'`ApplyStun` (1200, « below 35 % Health ») + les
    CONTROLES NEGATIFS de chaque predicat du `CreateTrigger`.

    Sous le seuil, 1201 ne peut PAS etre pose (son propre trigger exige `!HasEffect(Self,1200)`) : tout
    Stun observe la vient donc SANS ambiguite de la branche 1200 — le pendant exact du test precedent,
    qui isolait la branche 1201 a pleins PV.
    """
    import gameconfig as GC
    cap_pct = int(((GC.ability("AnvilShield") or {}).get("constants") or {}).get("healthPct"))
    # `--block-target 100,1` : blocage CERTAIN (chance 100) n'absorbant qu'1 point -> les coups
    # continuent d'entamer Arjac (avec `100,500` il encaisse 0 et ne descend jamais). `--hp-target
    # 9000` borne la descente a ~10 coups (le trait Resilient l'empeche de mourir hors overkill).
    rid = build_runner("92203", extra=["--p-units", f"{ATTACKER},templAggressor",
                                       "--a-units", ARJAC,
                                       "--block-target", "100,1",
                                       "--hp-target", "9000", "--hp-player", "400000"])["rid"]
    dec, att, arj = _bring_adjacent(rpc, rid, ATTACKER, ARJAC)
    if att is None:
        pytest.skip("attaquant/Arjac injoignables")
    hpmax = _stat(rpc, rid, arj["id"], "health") or 1
    for _ in range(60):
        d = _dv(rpc, rid)
        a = _by_id(d, arj["id"])
        if a is None or not a.get("alive"):
            pytest.skip("Arjac mort avant le seuil")
        if 100.0 * (a.get("hp") or 0) / hpmax <= cap_pct:
            break
        if d.get("currentPlayer") != att["owner"]:
            _act(rpc, rid, {"kind": "endturn"})
            continue
        if not _act(rpc, rid, {"kind": "ability", "casterId": att["id"], "targetId": arj["id"],
                               "abilityType": NORMAL_ATTACK}).get("ok"):
            pytest.skip("attaque KO pendant la descente")
        _act(rpc, rid, {"kind": "endturn"})
    else:
        pytest.skip("seuil healthPct non atteint")

    # capture SOUS le seuil (1200 ACTIF) -> c'est l'etat que le port doit rejouer.
    state, dec_low, board = _offline(rpc, rid)
    if board is None:
        pytest.skip("boardGraph indispo")
    arj_low = _by_id(dec_low, arj["id"])
    assert _effs(arj_low, CAP), "1200 inactif sous le seuil : le scenario ne teste pas la branche visee"

    d = _dv(rpc, rid)
    if d.get("currentPlayer") != att["owner"]:
        _act(rpc, rid, {"kind": "endturn"})
        _act(rpc, rid, {"kind": "endturn"})
    if not _act(rpc, rid, {"kind": "ability", "casterId": att["id"], "targetId": arj["id"],
                           "abilityType": NORMAL_ATTACK}).get("ok"):
        pytest.skip("attaque finale KO")
    dec_f = _dv(rpc, rid)
    att_f, arj_f = _by_id(dec_f, att["id"]), _by_id(dec_f, arj["id"])
    assert _effs(att_f, STUNNED), (
        "aucun Stun alors qu'Arjac est SOUS le seuil et bloque a 100 % -> la branche 1200 du gate "
        "d'ApplyStun est morte")
    assert not _effs(arj_f, FROZEN), (
        "1201 est pose alors que 1200 est ACTIF -> le gate `!HasEffect(Self,1200)` de "
        "FrozenAttackerAdvantage ne filtre plus (double pose du +20 %)")

    # --- CONTROLES NEGATIFS offline : chaque predicat du `CreateTrigger` doit BLOQUER le Stun.
    from engine.runner.operations.triggers.loki.anvil_shield import AnvilShieldApplyStunAbility
    from engine.runner.operations.triggers.base import TriggerEvent
    from engine.dsl.event_trigger_type import EventTriggerType
    from engine.runner.components import UnitComponent

    trig = AnvilShieldApplyStunAbility(arj["id"])

    def _ev(actor, target):
        return TriggerEvent(EventTriggerType.UnitBlocked, actor, target, ranged=False, profile="Power")

    assert trig.matches(state, _ev(att["id"], arj["id"])), (
        "le trigger ne matche pas le cas NOMINAL sous le seuil (controles negatifs non concluants)")
    # (1) OwnerIsTarget : ce n'est pas Arjac qui a bloque.
    assert not trig.matches(state, _ev(att["id"], att["id"]))
    # (2) IsMeleeAttack (position-based) : on eloigne l'attaquant -> attaque RANGED.
    apc = state.get_entity(att["id"]).get_component(PositionComponent)
    keep = (apc.col, apc.row)
    tpc = state.get_entity(arj["id"]).get_component(PositionComponent)
    far = next(((c, r) for c in range(0, 12) for r in range(0, 12)
                if board.id_at(c, r) is not None
                and hexgeo.distance((c, r), (tpc.col, tpc.row)) == 3), None)
    assert far is not None, "aucune tuile a distance 3 d'Arjac sur ce board (controle impossible)"
    apc.col, apc.row = far                             # hors adjacence -> IsRangedAttack
    assert not trig.matches(state, _ev(att["id"], arj["id"])), (
        "le gate IsMeleeAttack ne filtre pas une attaque a distance")
    apc.col, apc.row = keep
    # (3) IsAlive(caster) : attaquant mort.
    uc = state.get_entity(att["id"]).get_component(UnitComponent)
    uc.alive = False
    assert not trig.matches(state, _ev(att["id"], arj["id"])), "le gate IsAlive(caster) ne filtre pas"
    uc.alive = True
    # (4) HasEffect(1200|1201, activeOnly) : on « soigne » Arjac au-dessus du seuil -> 1200 INACTIF.
    hc = state.get_entity(arj["id"]).get_component(HealthComponent)
    hp_keep = hc.hp
    hc.hp = hc.hp_max
    assert not trig.matches(state, _ev(att["id"], arj["id"])), (
        "le gate `HasEffect(1200, activeOnly)` ne filtre plus une fois Arjac au-dessus du seuil "
        "-> le 4e argument natif est traite comme un minLevel au lieu du flag IsActive")
    hc.hp = hp_keep
    assert trig.matches(state, _ev(att["id"], arj["id"])), "etat non restaure apres les controles"


def test_anvil_shield_block_chance_cap_activates_below_health_pct_live(live_session, rpc, build_runner):
    """`AnvilShield_BlockChanceBelowHealthCap` (1200) — l'ActiveCondition est un POURCENTAGE de PV
    (`StatAmount(Self, HEALTH, CURRENT_PCT)` vs `GetNumberConstant(0x4f=healthPct)`), et sa
    contribution BLOCK_CHANCE (+20, var `blockChance` NON rarity-scale) entre EXACTEMENT au passage
    du seuil.

    Live : `decisionView.effects` n'expose que les effets ACTIFS -> 1200 est ABSENT a pleins PV et
    APPARAIT sous le seuil, avec `blockChance` qui passe de 0 a 20.
    Offline : l'effet est POSE des l'init (`ABILITY_INIT_OWNER_EFFECTS`) mais INERTE tant que
    `is_active()` est faux ; le driver `refresh_stat_modifier_effects` (mirror `RefreshEffectsOperation`)
    fait entrer/sortir sa modification.
    """
    import gameconfig as GC
    cap_pct = int(((GC.ability("AnvilShield") or {}).get("constants") or {}).get("healthPct"))
    rid = build_runner("92202", extra=["--p-units", f"{ATTACKER},templAggressor",
                                       "--a-units", ARJAC,
                                       "--hp-target", "60000", "--hp-player", "400000"])["rid"]
    dec, att, arj = _bring_adjacent(rpc, rid, ATTACKER, ARJAC)
    if att is None:
        pytest.skip("attaquant/Arjac injoignables")

    # (a) PLEINS PV : 1200 inactif -> absent du live, blockChance de base.
    base_bc = _stat(rpc, rid, arj["id"], "blockChance")
    assert not _effs(arj, CAP), "1200 est expose a pleins PV -> l'ActiveCondition ne filtre pas"
    state0, _dec0, board0 = _offline(rpc, rid)
    off0 = _off_effect(state0, arj["id"], CAP)
    assert off0 is not None, (
        "offline : 1200 n'est pas pose a l'init -> le gate `HasEffect(1200)` d'ApplyStun serait MORT "
        "dans tout runner demarrant Arjac a pleins PV (ABILITY_INIT_OWNER_EFFECTS['AnvilShield'])")
    hc0 = state0.get_entity(arj["id"]).get_component(HealthComponent)
    assert not off0.is_active({"hp": hc0.hp, "max_hp": hc0.hp_max}), "offline : 1200 actif a pleins PV"
    assert _off_block_chance(state0, arj["id"]) == base_bc, (
        f"offline blockChance={_off_block_chance(state0, arj['id'])} != live {base_bc} a pleins PV "
        "(la contribution de 1200 fuit alors que l'effet est INACTIF)")

    # (b) On descend Arjac sous le seuil (attaques repetees de l'attaquant ; 60 iterations max).
    hpmax = _stat(rpc, rid, arj["id"], "health") or 1
    for _ in range(60):
        d = _dv(rpc, rid)
        a = _by_id(d, arj["id"])
        if a is None or not a.get("alive"):
            pytest.skip("Arjac mort avant le seuil")
        hp = a.get("hp") or 0
        if 100.0 * hp / hpmax <= cap_pct:
            break
        if d.get("currentPlayer") != att["owner"]:
            _act(rpc, rid, {"kind": "endturn"})
            continue
        r = _act(rpc, rid, {"kind": "ability", "casterId": att["id"], "targetId": arj["id"],
                            "abilityType": NORMAL_ATTACK})
        if not (isinstance(r, dict) and r.get("ok")):
            pytest.skip(f"attaque KO: {str(r)[:150]}")
        _act(rpc, rid, {"kind": "endturn"})
    else:
        pytest.skip("seuil healthPct non atteint en 30 coups")

    dec_low = _dv(rpc, rid)
    arj_low = _by_id(dec_low, arj["id"])
    assert _effs(arj_low, CAP), (
        f"1200 n'apparait pas alors qu'Arjac est sous {cap_pct} % PV -> l'ActiveCondition (CURRENT_PCT) "
        "est mal portee")
    live_bc = _stat(rpc, rid, arj["id"], "blockChance")
    assert live_bc == base_bc + 20, (
        f"blockChance live={live_bc}, attendu {base_bc}+20 (var `blockChance` d'AnvilShield, NON "
        "rarity-scale)")

    # (c) OFFLINE (meme capture) : meme valeur, et le driver d'ActiveCondition la RETIRE si on remonte.
    state1, _dec1, _b1 = _offline(rpc, rid, dec_low)
    off1 = _off_effect(state1, arj["id"], CAP)
    hc1 = state1.get_entity(arj["id"]).get_component(HealthComponent)
    assert off1 is not None and off1.is_active({"hp": hc1.hp, "max_hp": hc1.hp_max})
    refresh_stat_modifier_effects(state1, arj["id"])
    assert _off_block_chance(state1, arj["id"]) == live_bc, (
        f"offline blockChance={_off_block_chance(state1, arj['id'])} != live {live_bc} sous le seuil")
    hc1.hp = hc1.hp_max                       # « soin » : on repasse au-dessus du seuil
    refresh_stat_modifier_effects(state1, arj["id"])
    assert _off_block_chance(state1, arj["id"]) == base_bc, (
        "le driver ne RETIRE pas la contribution de 1200 quand Arjac repasse au-dessus du seuil "
        "(mirror `RefreshEffectsOperation.DeactivateEffect` -> `RevertModification`)")
