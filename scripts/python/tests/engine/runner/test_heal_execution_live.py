"""#931-r1 -- la face EXECUTION du SOIN GENERIQUE `18 Heal`, confrontee au LIVE.

CE QUE CES TESTS VERROUILLENT. #931 a porte `1167 Heal_TwistedScience` et #966 `1212
HealingBalms_Heal` -- les deux SPECIALISATIONS que des passifs SUBSTITUENT au soin de trait. La
GENERIQUE, elle, restait hors d'`ABILITY_CLASSES` : `AbilityHandler` rendait `ported: False`,
posait les flags de tour et NE MUTAIT AUCUN PV. Cast accepte, tour consomme, zero soin -- et, sans
`TARGETING_OPTIONS`, `get_invalid_target_reason` rendait `0` sans le moindre gate, donc le moteur
acceptait en plus des cibles que `ActiveAbilityOperation$$IsInvalidTarget` REFUSE. Deux
degradations, toutes deux silencieuses.

CRITERE BINAIRE : apres le cast, les PV de la cible AUGMENTENT-ils du montant attendu, et le port
rend-il le MEME delta que le natif ?

CHAINE PORTEE (`engine/runner/abilities/heal.py`) :
    `IdunBattleLogic.Entities.Abilities.Active.Common.HealAbility$$CreateBehaviour`
      -> feuille `DSLBehaviors$$Heal` (`ForHeal` : scope 0, removeEffects 1)
      -> `IdunBattle.Operations.HealUnitOperation$$Execute`
           gate `Cursed` + `DamagePrediction$$PredictHeal` + `FillUpStatComponent$$FillUp`

MONTAGE : la fixture NOMMEE `_heal_stage` (soigneur trait `Healer` + ami BLESSE par
`--unit-stat <cible>:RemainingHealth=2000`, `advance=0`).

ASCII only (console cp1252).
"""
from __future__ import annotations

import os
import sys

import pytest

from engine.entities.pathfinding.board import Board
from engine.runner.abilities.attack_type import ABILITY_ATTACK_TYPE, AbilityAttackType
from engine.runner.abilities.handler import ABILITY_CLASSES
from engine.runner.abilities.heal import HealAbility, heal_amount
from engine.runner.abilities.targeting_rule import TargetingRule as TR
from engine.runner.components import HealthComponent, StatsComponent
from engine.runner.messages import ActiveAbilityMessage
from engine.runner.runner import Runner
from engine.runner.snapshot import load_state
from engine.entities.active_ability_type import ActiveAbilityType

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
#: POSE AU MERGE de la PR #995, pas par l'auteur -- le fichier est arrive sans, et la passe
#: rendait `rc=1` malgre 4 tests VERTS. Le defaut `toujours: True` est assume et MOTIVE :
#: c'est un test LIVE (il monte un runner via la fixture `_heal_stage`, donc il depend du
#: harnais entier -- `rl_duel`, RPC, snapshot, board), et le cliquet qui CONFRONTE un
#: perimetre etroit a ce que le fichier LIT reellement (`probe_486r15`) est SUSPENDU par
#: decision de l'utilisateur. Enumerer ici les seuls modules cites en import serait donc un
#: perimetre NON VERIFIE, c'est-a-dire le FAUX VERT que ce garde existe pour empecher.
#: A RESSERRER quand le cliquet sera re-arme : les foyers propres sont
#: `engine/runner/abilities/heal.py`, `handler.py`, `attack_type.py`,
#: `engine/runner/operations/heal.py` et la fixture `tests/engine/runner/_heal_stage.py`.
DECLENCHEUR = {
    "chemins": (),
    "build": True,
    "toujours": True,
    "raison": "Test LIVE monte sur le harnais runner complet ; perimetre etroit NON MESURE "
              "(probe_486r15 suspendu) -- large par honnetete, pas par negligence.",
}

sys.path.insert(0, os.path.dirname(__file__))
import _heal_stage as S                                    # noqa: E402

HEAL = S.HEAL_ABILITY_ID                                   # 0x12 = 18


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


def _live_units(rpc, rid):
    r = rpc("observeBattle", {"runnerId": rid}, 40)
    return {u["squadId"]: u for u in (r.get("units") or [])} if _ok(r) else {}


def _approach(rpc, rid, board, sq_caster, sq_target):
    """DEPLACE le soigneur jusqu'a une tuile LIBRE adjacente a la cible si besoin.

    Le preset `<TargetingOptions statics>+0x100` pose `RANGE_ADJACENT_IF_MELEE_CASTER`
    (`onlyAdjacent = IfNotRangedCaster`) : au CONTACT le cast est legal dans les DEUX regimes, ce
    qui rend le montage independant du profil d'arme du soigneur. Le masque `0x8500` ne pose PAS
    `CasterHasNotMoved` (0x10), donc bouger AVANT de caster reste legal. Un roster dont les spawns
    ne sont pas voisins ne doit PAS produire un skip (<< bloque par la geometrie >>) -- on CONDUIT
    les positions."""
    U = _live_units(rpc, rid)
    if sq_caster not in U or sq_target not in U:
        return False
    ct = board.id_at(U[sq_caster]["col"], U[sq_caster]["row"])
    tt = board.id_at(U[sq_target]["col"], U[sq_target]["row"])
    if ct is None or tt is None:
        return False
    if ct in board.neighbours(tt):
        return True
    occ = {board.id_at(u["col"], u["row"]) for u in U.values()}
    cands = [n for n in board.neighbours(tt)
             if n in board.by_id and board.walkable(n) and n not in occ]
    cands.sort(key=lambda n: abs(board.coord(n)[0] - U[sq_caster]["col"])
               + abs(board.coord(n)[1] - U[sq_caster]["row"]))
    for n in cands:
        c, r = board.coord(n)
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": sq_caster, "to": {"col": c, "row": r}}}, 40)
        U2 = _live_units(rpc, rid)
        ct2 = board.id_at(U2[sq_caster]["col"], U2[sq_caster]["row"]) if sq_caster in U2 else None
        if ct2 is not None and ct2 in board.neighbours(tt):
            return True
    return False


def _capture(rpc, rid, board):
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
    if not (_ok(dv) and _ok(ob) and _ok(snap)):
        return None, None
    return load_state(dv, ob, snap, board=board), ob


# ------------------------------------------------ etage 0 : le REGISTRE (offline, sans runner)
def test_18_est_au_registre_avec_son_masque_ET_son_attack_type():
    """La regle de non-regression : une ability qui entre dans `ABILITY_CLASSES` pose son
    `TARGETING_OPTIONS` **et** son `ABILITY_ATTACK_TYPE` DANS LE MEME COMMIT. Les deux valeurs sont
    RELUES au ctor (`...Common.HealAbility$$.ctor` recopie `<TargetingOptions statics>+0x100` puis
    appelle `ADeprecatedActiveAbility..ctor(this, &opts, 2)`), jamais deduites du voisin."""
    assert ABILITY_CLASSES.get(HEAL) is HealAbility, "18 absente d'ABILITY_CLASSES"
    opts = HealAbility.TARGETING_OPTIONS
    assert opts is not None, "sans masque, get_invalid_target_reason rend 0 SANS AUCUN GATE"
    assert int(opts.rules) == 0x8500, "rules != 0x8500 (preset statics+0x100)"
    assert opts.has(TR.TargetIsHealable) and opts.has(TR.TargetIsFriendly) \
        and opts.has(TR.CasterIsPossibleTarget)
    assert not opts.has(TR.TargetMatchesDynamicRule), (
        "le bit DYNAMIQUE est le contraste EXACT avec `28 Repair` (0x8002) : `HealAbility` n'a "
        "aucun override dynamique, tout son refus est STATIQUE")
    assert ABILITY_ATTACK_TYPE[ActiveAbilityType.Heal] == AbilityAttackType.Others


def test_le_masque_de_18_n_est_PAS_celui_de_28():
    """Contre-epreuve du piege << recopier le voisin de forme >> : les deux abilities sont jumelles
    par leur formule et par leur origine (un trait), et leurs masques sont pourtant DIFFERENTS sur
    les deux axes -- regles ET portee."""
    from engine.runner.abilities.repair import REPAIR_TARGETING_OPTIONS
    heal = HealAbility.TARGETING_OPTIONS
    assert int(heal.rules) != int(REPAIR_TARGETING_OPTIONS.rules), \
        "0x8500 contre 0x8002 -- un port qui recopie le voisin ecrit un masque FAUX"
    assert heal.range != REPAIR_TARGETING_OPTIONS.range, \
        "statics+0x00 (IfNotRangedCaster) contre statics+0x30 (onlyAdjacent + overrideRange 1)"


# ------------------------------------------------------------------ le test LIVE du residu
def test_heal_restores_health_live_and_offline(build_runner, rpc):
    """LE test du residu : le cast SOIGNE, du MEME montant live et offline.

    Le montant attendu n'est PAS un scalaire hardcode : il est RE-DERIVE du port
    (`heal_amount` = `Common.HealAbility$$HealAmount` = `Attack(caster) x Max(WeaponHighestHits, 1)`)
    puis cape par ce qui manque a la cible (`FillUpStatComponent$$MaxFillUp`). Les trois valeurs
    doivent coincider : `live_delta == offline_delta == expected > 0`."""
    stage = S.build_stage(rpc, build_runner=build_runner)
    rid = stage["rid"]
    board = _board(rpc, rid)
    if board is None:
        pytest.skip("boardGraph indispo")

    U0 = _live_units(rpc, rid)
    sq_c = next((sq for sq, u in U0.items() if u.get("visualId") == S.HEALER_VIS), None)
    sq_t = next((sq for sq, u in U0.items() if u.get("visualId") == S.HEALEE_VIS), None)
    if sq_c is None or sq_t is None:
        pytest.skip("soigneur/cible absents live")
    assert _approach(rpc, rid, board, sq_c, sq_t), (
        "impossible d'amener %s au contact de %s -- le montage doit CONDUIRE les positions"
        % (S.HEALER_VIS, S.HEALEE_VIS))

    state, ob = _capture(rpc, rid, board)
    if state is None:
        pytest.skip("capture pre-cast KO")
    cid = _by_vis(state, S.HEALER_VIS)
    tid = _by_vis(state, S.HEALEE_VIS)
    if cid is None or tid is None:
        pytest.skip("roster incomplet offline (%s / %s)" % (cid, tid))

    hc = _hc(state, tid)
    assert int(hc.hp) < int(hc.hp_max), (
        "le montage doit livrer une cible BLESSEE (--unit-stat RemainingHealth) ; hp=%d max=%d"
        % (int(hc.hp), int(hc.hp_max)))
    amount = heal_amount(state, cid)
    expected = min(int(amount), int(hc.hp_max) - int(hc.hp))
    assert expected > 0, "montant de soin degenere (amount=%d)" % amount

    off_pre = int(hc.hp)
    runner = Runner(state).install_default_handlers(20)
    runner.apply(ActiveAbilityMessage(caster_id=cid, target_id=tid, ability_type=HEAL))
    last = runner.ability_handler.last or {}
    assert last.get("ported"), (
        "ability 18 NON routee cote combat (%s) -- c'est EXACTEMENT le residu #931-r1" % (last,))
    off_delta = int(_hc(state, tid).hp) - off_pre

    U = _live_units(rpc, rid)
    live_pre = U[sq_t]["hp"]
    rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": sq_c, "targetId": sq_t, "abilityType": HEAL}}, 60)
    U2 = _live_units(rpc, rid)
    if sq_t not in U2:
        pytest.skip("observe post-cast KO")
    live_delta = U2[sq_t]["hp"] - live_pre

    print("\n[HEAL/%s id=18] amount=%d expected=%d live=%d offline=%d"
          % (S.HEALER_VIS, amount, expected, live_delta, off_delta))
    assert live_delta > 0, (
        "le natif n'a RIEN soigne (delta=%d) -- montage invalide, pas un verdict de port"
        % live_delta)
    assert off_delta == expected, "offline %d != attendu %d" % (off_delta, expected)
    assert live_delta == off_delta, "live %d != offline %d" % (live_delta, off_delta)


def test_le_gate_de_ciblage_refuse_un_ENNEMI_et_une_cible_SAINE(build_runner, rpc):
    """GENERALISATION : le masque `0x8500` n'est pas decoratif. Deux refus, deux raisons DISTINCTES,
    mesures sur le MEME montage que le test ci-dessus :
      * `TargetIsFriendly` (0x400) sur un ENNEMI ;
      * `TargetIsHealable` (0x100) sur un allie a PLEINE sante (`AttackQuery$$IsDamagedUnit` faux).
    Sans `TARGETING_OPTIONS`, `get_invalid_target_reason` rendrait `0` dans les DEUX cas."""
    from engine.runner.abilities.targeting import get_invalid_target_reason

    stage = S.build_stage(rpc, build_runner=build_runner)
    rid = stage["rid"]
    board = _board(rpc, rid)
    if board is None:
        pytest.skip("boardGraph indispo")
    state, _ = _capture(rpc, rid, board)
    if state is None:
        pytest.skip("capture KO")
    cid = _by_vis(state, S.HEALER_VIS)
    tid = _by_vis(state, S.HEALEE_VIS)
    eid = next((_by_vis(state, v) for v in S.ENEMY_VIS if _by_vis(state, v) is not None), None)
    if cid is None or tid is None or eid is None:
        pytest.skip("roster incomplet offline")

    ab = HealAbility()
    # PRE-ASSERTIONS DE MONTAGE : un `0` rendu par la cascade a DEUX causes possibles (la regle ne
    # mord pas / la cible n'est pas ce qu'on croit). On les separe AVANT d'accuser le port.
    from engine.runner.abilities.targeting import units_are_friendly, _unit_of
    assert _unit_of(state, eid) is not None, \
        "montage : l'ennemi %s ne resout pas en UNITE, la cascade sauterait toutes ses regles" % eid
    assert not units_are_friendly(state, cid, eid), \
        "montage : %s et %s sont du MEME camp -- le refus teste ci-dessous n'a pas d'objet" % (cid, eid)
    # Un ENNEMI : le bit `TargetIsFriendly` mord, quelle que soit sa sante.
    assert get_invalid_target_reason(state, cid, eid, ab) == int(TR.TargetIsFriendly), \
        "une cible ENNEMIE doit etre refusee par TargetIsFriendly (0x400)"
    # Un ALLIE BLESSE : accepte (temoin non degenere -- sans lui le test ci-dessus ne prouve rien).
    hc = _hc(state, tid)
    assert int(hc.hp) < int(hc.hp_max), "montage : la cible doit etre blessee"
    assert get_invalid_target_reason(state, cid, tid, ab) == 0, \
        "un allie BLESSE doit etre accepte -- sinon le refus ci-dessous n'est pas discriminant"
    # Le MEME allie, remis a PLEINE sante : `TargetIsHealable` mord.
    hc.hp = int(hc.hp_max)
    assert get_invalid_target_reason(state, cid, tid, ab) == int(TR.TargetIsHealable), \
        "une cible a pleine sante doit etre refusee par TargetIsHealable (0x100)"
