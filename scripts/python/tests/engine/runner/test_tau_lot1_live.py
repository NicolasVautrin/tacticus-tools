"""CONFRONT LIVE du lot #114 (TAU, face COMBAT) -- les abilities dont la face DECISION (playbook)
etait deja portee et dont le behaviour de cast etait un NO-OP :

    1081 FightingRetreat      (tauDarkstrider)  IdunBattleLogic.Entities.Abilities.Active.Loki.FightingRetreatAbility$$ExecuteBehaviour
    1077 EarlyWarningOverride (tauCrisis)       IdunBattleLogic.Entities.Abilities.Active.Loki.EarlyWarningOverrideAbility$$ExecuteBehaviour
    1082 InspiredToGreatness  (tauAunShi)       IdunBattleLogic.Entities.Abilities.Active.Loki.InspiredToGreatnessAbility$$ExecuteBehaviour

PROTOCOLE (aucune constante attendue en dur -- l'oracle est le natif) : on monte un runner isole, on
DRIVE les positions jusqu'a la configuration voulue, on VERIFIE la LEGALITE du cast via
`abilityTargets(...).fromHere` (#111 : un cast refuse pour cible illegale rend `mutated:false` et
2 evenements groupe 12 -- exactement l'observable d'une ability inerte ; `targets` est un SUPERSET
move-inclus qui peut etre illegal SUR PLACE), puis on execute le MEME cast OFFLINE
(`load_state` -> `_apply_active_ability`) et LIVE, et on compare l'EMPREINTE D'EFFETS
`{unite -> {effectType: remaining}}`.

⚠ FILTRE `IsActive` DU CANAL LIVE : `readEffectsByUnit` DROPPE les effets dont
`EffectComponent.IsActive @+0x5c` est nul (`if (!info.active || info.removed) continue`). Deux
consequences EXPLOITEES ici :
  * `Overwatch_AutoAttack` (1009) et `EarlyWarningOverride_ReactivateOverwatch` (1145) sont poses par
    le cast mais INACTIFS tant que c'est le tour du porteur (`RangedAutoAttackEffect$$
    CreateHandleTriggerAbilitiesInternal` : `Triggered(On(0x12) & NOT IsTurnOf(owner) & (HasEffect(
    owner, 0x516) | DoesNotHaveFlag(owner, 2=ActiveAbilityUsed)) & NOT HasEffect(owner, 0x429=Pinned),
    ActivateEffect)` / `Triggered(On(0x12) & IsTurnOf(owner), DeactivateEffect)`) -> on les mesure
    APRES un `endturn` ;
  * c'est ce MEME filtre qui fait du modele « presence == IsActive » (case-160) la representation
    fidele de `RangedSpecialist` (1515) cote port -> le 4e volet de FightingRetreat (`ActivateEffect`)
    se mesure comme une RE-APPARITION de l'effet.

Drive les positions ; lit l'etat LIVE ; state-files UNIQUES ; ASCII-only.
"""
from __future__ import annotations

import pytest

import hexgeo
from engine.runner.operations.summon_ai import _apply_active_ability

FIGHTING_RETREAT = 1081
EARLY_WARNING_OVERRIDE = 1077
FR_DMG_REDUCTION = 1157        # EffectType.FightingRetreatDmgReduction
FR_HIT_REDUCTION = 1158        # EffectType.FightingRetreatHitReduction
MARKERLIGHT = 1122             # EffectType.Markerlight
RANGED_SPECIALIST = 1515       # EffectType.RangedSpecialist (owner-effect du trait 1060)
EWO_EFFECTS = (1009, 1144, 1145, 1149)   # Overwatch_AutoAttack / SuppressCloseCombatWeakness /
#                                          EarlyWarningOverride_ReactivateOverwatch / _Visual
INSPIRED_TO_GREATNESS = 1082
ITG_OVERRIDE_LEVEL = 1180      # EffectType.InspiredToGreatness_OverrideLevel
BOARD = "MC1_67"


# ------------------------------------------------------------------ harnais

@pytest.fixture(scope="module")
def rpc_(host, live_session):
    def _rpc(m, b, t=90):
        r = host._rpc(live_session, m, [b], timeout=t)
        return r.get("result") if isinstance(r, dict) and "result" in r else r
    return _rpc


def _load(rpc, rid):
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")
    dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    return load_state(dec, ob, snap, board=board), board, dec


def _dec(rpc, rid):
    return rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)


def _units(dec):
    return {int(u["id"]): u for u in (dec.get("units") or [])}


def _pos(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row"))


def _footprint_live(dec) -> dict:
    """`{unitId -> {effectType: remaining}}` -- decisionView.effects (deja filtre `IsActive`)."""
    out = {}
    for u in (dec.get("units") or []):
        effs = {int(e["effectType"]): e.get("remaining") for e in (u.get("effects") or [])
                if e.get("effectType") is not None}
        if effs:
            out[int(u["id"])] = effs
    return out


def _footprint_off(state) -> dict:
    """MEME empreinte cote port (`remaining_turns` None == le `remaining 0` live = permanent)."""
    out = {}
    for key, effs in (state.effects.by_unit if state.effects is not None else {}).items():
        cur = {int(e.effect_type): (0 if e.remaining_turns is None else int(e.remaining_turns))
               for e in effs if not e.consumed}
        if cur:
            out[int(key)] = cur
    return out


def _delta(before: dict, after: dict) -> dict:
    out = {}
    for k, effs in after.items():
        new = {et: rem for et, rem in effs.items() if et not in (before.get(k) or {})}
        if new:
            out[int(k)] = new
    return out


def _from_here(rpc, rid, caster, ability):
    """Cibles LEGALES DEPUIS LA POSITION COURANTE (`fromHere`) — JAMAIS `targets` (superset
    move-inclus : une cible qui n'y est atteignable qu'APRES deplacement rend un cast REFUSE,
    observable `mutated:false` trompeusement identique a « l'ability ne fait rien », cf. #111)."""
    at = rpc("abilityTargets", {"runnerId": rid, "unitId": caster, "abilityType": ability}, 90) or {}
    row = next((u for u in (at.get("units") or []) if u.get("unitId") == caster), None)
    ab = ((row or {}).get("abilities") or [{}])[0]
    return ab.get("fromHere") or []


def _movable(rpc, rid, uid):
    mv = rpc("aiMovableTiles", {"runnerId": rid}, 60) or {}
    row = next((u for u in (mv.get("units") or []) if u.get("unitId") == uid), None)
    return [(t.get("col"), t.get("row")) for t in ((row or {}).get("tiles") or [])]


def _move(rpc, rid, uid, to):
    rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": uid, "to": {"col": to[0], "row": to[1]}}}, 90)


def _endturn(rpc, rid, n=1):
    for _ in range(n):
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 90)


def _cast(rpc, rid, caster, ability, target=None):
    r = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": caster, "abilityType": ability,
        "targetId": (caster if target is None else target)}}, 90) or {}
    return (r.get("actions") or [{}])[0]


def _ai_turn(rpc, rid):
    """Fait JOUER l'IA native (le tour adverse) -- `applyAction endturn` rend la main SANS que l'IA
    agisse : sans ce `aiPlayByUnit`, l'ennemi ne bouge ni ne frappe jamais."""
    return rpc("aiPlayByUnit", {"runnerId": rid, "maxTurns": 1, "maxActivations": 9999}, 180)


def _hp_live(rpc, rid) -> dict:
    ob = rpc("observeBattle", {"runnerId": rid}, 40) or {}
    return {u["squadId"]: (u["hp"], u["hpMax"]) for u in (ob.get("units") or [])}


def _hp_off(state) -> dict:
    from engine.runner.components import HealthComponent
    return {eid: e.get_component(HealthComponent).hp for eid, e in state.entities.items()
            if e.get_component(HealthComponent) is not None}


def _find(dec, vid):
    return next((u for u in _units(dec).values() if u.get("visualId") == vid), None)


def _foes(dec, team=1):
    return [u for u in _units(dec).values() if u.get("team") != team]


# ------------------------------------------------------------------ 1081 FightingRetreat

def _drive_darkstrider_into_melee(rpc, rid, max_iter=6):
    """DRIVE : rapproche Darkstrider d'un ork jusqu'a l'ADJACENCE, puis passe DEUX tours -- son
    `RangedSpecialist` (1515) se DESACTIVE au turn-start suivant (`RangedSpecialistEffect$$
    CreateHandleTriggerAbilitiesInternal` : `On(0x12) & If(HasAdjacentEnemies, Deactivate, Activate)`),
    ce qui rend le 4e volet du cast (`ActivateEffect`) OBSERVABLE."""
    for _ in range(max_iter):
        dec = _dec(rpc, rid)
        ds = _find(dec, "tauDarkstrider")
        foes = _foes(dec)
        if ds is None or not foes:
            return None, dec
        dpos = _pos(ds)
        near = min(foes, key=lambda f: hexgeo.distance(dpos, _pos(f)))
        if hexgeo.distance(dpos, _pos(near)) == 1 and _from_here(rpc, rid, ds["id"], FIGHTING_RETREAT):
            return ds["id"], dec
        cands = _movable(rpc, rid, ds["id"])
        if cands:
            _move(rpc, rid, ds["id"], min(cands, key=lambda q: hexgeo.distance(q, _pos(near))))
        _endturn(rpc, rid, 2)
    return None, _dec(rpc, rid)


def test_fighting_retreat_confront_live(rpc_, build_runner):
    """1081 `FightingRetreatAbility$$ExecuteBehaviour` -- scenario NOMINAL (>=1 ennemi adjacent).

    L'empreinte d'effets OFFLINE doit etre EXACTEMENT celle du natif : les TROIS debuffs
    (1157/1158/1122) sur CHAQUE ennemi adjacent avec le MEME `remaining`
    (`TurnsUntilEndOfCurrentPlayersNextTurn` = `ConvertRoundsToTurns(1) + 1`), + la RE-ACTIVATION du
    `RangedSpecialist` (1515) du caster, qui l'avait PERDU en demarrant son tour au contact."""
    rid = build_runner("114001", ["--p-units", "tauDarkstrider,tauCrisis",
                                  "--a-units", "orksNob,orksNob", "--hp-player", "60000"],
                       board=BOARD)["rid"]
    caster, dec = _drive_darkstrider_into_melee(rpc_, rid)
    if caster is None:
        pytest.fail("scenario NON atteint : Darkstrider n'a pas pu engager le contact "
                    "(drive des positions KO)")
    ds = _units(dec)[caster]
    adj = [u for u in _foes(dec) if hexgeo.distance(_pos(ds), _pos(u)) == 1]
    ds_effs = {int(e["effectType"]) for e in (ds.get("effects") or [])}
    assert RANGED_SPECIALIST not in ds_effs, (
        "scenario NON discriminant : le RangedSpecialist du caster est encore ACTIF avant le cast "
        "(il n'a pas demarre son tour au contact) -> la re-activation ne se verrait pas")

    state, _board, _d = _load(rpc_, rid)
    off_before = _footprint_off(state)
    res = _apply_active_ability(state, caster, caster, FIGHTING_RETREAT)
    diag = (res or {}).get("diag") or {}
    assert res.get("routed") == "handler" and diag.get("ported") is True, \
        f"1081 non portee (routed={res.get('routed')})"
    off = _delta(off_before, _footprint_off(state))

    live_before = _footprint_live(_dec(rpc_, rid))
    act = _cast(rpc_, rid, caster, FIGHTING_RETREAT)
    assert not act.get("error"), f"cast natif bloque: {act.get('error')}"
    live = _delta(live_before, _footprint_live(_dec(rpc_, rid)))
    print(f"\n[1081] caster=u{caster} adjacents={[u['id'] for u in adj]} "
          f"turns={diag.get('turns')} n_adj={diag.get('adjacent_enemies')}\n"
          f"       off={off}\n       live={live}")

    assert off == live, f"empreinte d'effets offline {off} != live {live}"
    for u in adj:
        assert set(off.get(u["id"], {})) == {FR_DMG_REDUCTION, FR_HIT_REDUCTION, MARKERLIGHT}, \
            f"ennemi adjacent u{u['id']} : debuffs {off.get(u['id'])} != les 3 attendus"
    assert off.get(caster, {}).get(RANGED_SPECIALIST) is not None, \
        "le RangedSpecialist du caster n'a PAS ete re-active par le cast"
    # branche TURN-FLOW : >=1 ennemi adjacent -> ResetTurn (le tour est ROUVERT), pas FinishTurn.
    assert [f["op"] for f in (diag.get("turn_flow") or [])] == ["ResetTurn"], \
        f"branche turn-flow inattendue: {diag.get('turn_flow')}"
    assert act.get("actionConsumed") is False, \
        "le natif a CONSOMME l'action alors que Darkstrider est adjacent a un ennemi"


def _drive_ally_into_melee(rpc, rid, max_iter=8):
    """DRIVE (GENERALISATION) : `tauCrisis` AU CONTACT d'un ork, `tauDarkstrider` adjacent a
    `tauCrisis` mais a >=2 de tout ennemi. Apres deux tours, c'est l'ALLIE qui perd son
    `RangedSpecialist` -- le caster, lui, garde le sien."""
    for _ in range(max_iter):
        dec = _dec(rpc, rid)
        rv, ds, foes = _find(dec, "tauCrisis"), _find(dec, "tauDarkstrider"), _foes(dec)
        if rv is None or ds is None or not foes:
            return None, None, dec
        rpos, dpos = _pos(rv), _pos(ds)
        near = min(foes, key=lambda f: hexgeo.distance(rpos, _pos(f)))
        npos = _pos(near)
        if (hexgeo.distance(rpos, npos) == 1 and hexgeo.distance(dpos, rpos) == 1
                and min(hexgeo.distance(dpos, _pos(f)) for f in foes) >= 2
                and _from_here(rpc, rid, ds["id"], FIGHTING_RETREAT)):
            return ds["id"], rv["id"], dec
        cands = _movable(rpc, rid, rv["id"])
        if cands:
            rpos = min(cands, key=lambda q: (abs(hexgeo.distance(q, npos) - 1),
                                             hexgeo.distance(q, npos)))
            _move(rpc, rid, rv["id"], rpos)
        cands = _movable(rpc, rid, ds["id"])
        if cands:
            ok = [q for q in cands if hexgeo.distance(q, rpos) == 1
                  and min(hexgeo.distance(q, _pos(f)) for f in foes) >= 2]
            _move(rpc, rid, ds["id"],
                  ok[0] if ok else min(cands, key=lambda q: hexgeo.distance(q, rpos)))
        _endturn(rpc, rid, 2)
    return None, None, _dec(rpc, rid)


def test_fighting_retreat_ally_reactivation_and_finishturn_live(rpc_, build_runner):
    """1081 -- GENERALISATION la plus DISCRIMINANTE : caster SANS ennemi adjacent, mais un ALLIE
    adjacent au `RangedSpecialist` DESACTIVE.

    Elle exerce les DEUX branches qu'un port « colle au scenario nominal » raterait :
      * le 4e volet porte sur `adjFriends op_Addition caster` -- c'est l'ALLIE qui doit voir son
        1515 revenir (le caster n'a rien perdu) ;
      * le 5e volet bascule sur `FinishTurn` (`AmountIsGreater(Direct(0), Direct(0))` faux) : le
        natif CONSOMME l'action, et AUCUN debuff n'est pose (aucun ennemi adjacent).
    Le cast reste LEGAL par la branche `HasDeactivatedRangedSpecialist` de
    `FightingRetreatAbility$$GetDynamicInvalidTargetReason` -- c'est aussi ce qui PROUVE que la
    legalite du cast ne se reduit pas a « un ennemi adjacent »."""
    rid = build_runner("114003", ["--p-units", "tauCrisis,tauDarkstrider",
                                  "--a-units", "orksNob,orksNob", "--hp-player", "60000",
                                  "--no-ai"], board=BOARD)["rid"]
    caster, ally, dec = _drive_ally_into_melee(rpc_, rid)
    if caster is None:
        pytest.fail("scenario NON atteint : impossible de placer l'allie au contact et le caster "
                    "hors contact (drive des positions KO)")
    ally_effs = {int(e["effectType"]) for e in (_units(dec)[ally].get("effects") or [])}
    ds_effs = {int(e["effectType"]) for e in (_units(dec)[caster].get("effects") or [])}
    assert RANGED_SPECIALIST not in ally_effs, \
        "scenario NON discriminant : l'allie a encore son RangedSpecialist ACTIF"
    assert RANGED_SPECIALIST in ds_effs, \
        "scenario NON discriminant : le caster a AUSSI perdu son RangedSpecialist"

    state, _board, _d = _load(rpc_, rid)
    off_before = _footprint_off(state)
    res = _apply_active_ability(state, caster, caster, FIGHTING_RETREAT)
    diag = (res or {}).get("diag") or {}
    off = _delta(off_before, _footprint_off(state))
    live_before = _footprint_live(_dec(rpc_, rid))
    act = _cast(rpc_, rid, caster, FIGHTING_RETREAT)
    assert not act.get("error"), f"cast natif bloque: {act.get('error')}"
    live = _delta(live_before, _footprint_live(_dec(rpc_, rid)))
    print(f"\n[1081/gen] caster=u{caster} ally=u{ally} n_adj={diag.get('adjacent_enemies')}\n"
          f"       off={off}\n       live={live}\n       flow={diag.get('turn_flow')}")

    assert off == live, f"empreinte offline {off} != live {live} (branche allie/FinishTurn)"
    assert off.get(ally, {}).get(RANGED_SPECIALIST) is not None, \
        "le RangedSpecialist de l'ALLIE adjacent n'a pas ete re-active"
    assert diag.get("adjacent_enemies") == 0, \
        f"le scenario devait avoir 0 ennemi adjacent (vu {diag.get('adjacent_enemies')})"
    assert [f["op"] for f in (diag.get("turn_flow") or [])] == ["FinishTurn"], \
        f"branche turn-flow attendue FinishTurn, vue {diag.get('turn_flow')}"
    assert all(FR_DMG_REDUCTION not in v and MARKERLIGHT not in v for v in off.values()), \
        f"des debuffs ont ete poses sans ennemi adjacent: {off}"
    assert act.get("actionConsumed") is True, \
        "le natif n'a PAS consomme l'action alors qu'aucun ennemi n'est adjacent"


# ------------------------------------------------------------------ 1077 EarlyWarningOverride

def test_early_warning_override_confront_live(rpc_, build_runner):
    """1077 `EarlyWarningOverrideAbility$$ExecuteBehaviour` : QUATRE effets sur le caster
    (`TurnsFromRounds(1)`) + `nrOfSummons` Shield Drones sur des tuiles LIBRES adjacentes.

    Les effets 1009/1145 sont poses mais INACTIFS pendant le tour du porteur (cf. l'en-tete) -> la
    mesure live se fait en DEUX temps : (a) immediatement (les 2 effets ACTIFS, avec leur
    `remaining`, confrontes a l'offline) ; (b) apres `endturn` (les 4, types confrontes a l'offline)."""
    rid = build_runner("114002", ["--p-units", "tauCrisis,tauDarkstrider",
                                  "--a-units", "orksNob,orksNob", "--no-ai"], board=BOARD)["rid"]
    dec = _dec(rpc_, rid)
    rv = _find(dec, "tauCrisis")
    assert rv is not None, "tauCrisis absent du runner"
    caster = rv["id"]
    fh = _from_here(rpc_, rid, caster, EARLY_WARNING_OVERRIDE)
    assert any(t.get("targetId") == caster for t in fh), \
        f"self-cast 1077 ILLEGAL depuis la position courante (fromHere={fh}) -- un cast lance ici " \
        f"rendrait mutated:false, indiscernable d'une ability inerte (#111)"

    state, board, _d = _load(rpc_, rid)
    off_before = _footprint_off(state)
    n_units_before = len(state.entities)
    res = _apply_active_ability(state, caster, caster, EARLY_WARNING_OVERRIDE)
    diag = (res or {}).get("diag") or {}
    assert res.get("routed") == "handler" and diag.get("ported") is True, \
        f"1077 non portee (routed={res.get('routed')})"
    off = _delta(off_before, _footprint_off(state))

    live_before = _footprint_live(_dec(rpc_, rid))
    n_live_before = len(_units(_dec(rpc_, rid)))
    act = _cast(rpc_, rid, caster, EARLY_WARNING_OVERRIDE)
    assert not act.get("error"), f"cast natif bloque: {act.get('error')}"
    dec_after = _dec(rpc_, rid)
    live_now = _delta(live_before, _footprint_live(dec_after))
    _endturn(rpc_, rid, 1)                          # le tour passe a l'adversaire -> 1009/1145 ACTIFS
    live_next = _delta(live_before, _footprint_live(_dec(rpc_, rid)))

    drones = [u for u in _units(dec_after).values() if u.get("visualId") == "tauSmnDroneShield"]
    print(f"\n[1077] caster=u{caster} tiles={diag.get('tiles')} count={diag.get('count')}\n"
          f"       off={off}\n       live(tour du caster)={live_now}\n"
          f"       live(tour adverse)={live_next}\n"
          f"       drones live={[(d['id'], _pos(d)) for d in drones]}")

    # (a) les effets VISIBLES pendant le tour du caster : sous-ensemble EXACT (types + remaining).
    assert set(live_now.get(caster, {})) <= set(off.get(caster, {})), \
        f"le natif pose des effets que le port ne pose pas: {live_now} vs {off}"
    for et, rem in (live_now.get(caster) or {}).items():
        assert off[caster][et] == rem, \
            f"remaining offline {off[caster][et]} != live {rem} pour l'effet {et}"
    # (b) tour ADVERSE : les 4 effets sont ACTIFS -> les TYPES doivent coincider exactement.
    assert set(live_next.get(caster, {})) == set(off.get(caster, {})) == set(EWO_EFFECTS), \
        (f"types d'effets offline {sorted(off.get(caster, {}))} != live {sorted(live_next.get(caster, {}))} "
         f"(attendu {sorted(EWO_EFFECTS)})")
    # SUMMONS : cardinal `nrOfSummons` et tuiles LIBRES ADJACENTES au caster, offline comme live.
    assert len(drones) == diag["count"] == len(diag["tiles"]), \
        f"{len(drones)} drones live vs count={diag['count']} tiles={diag['tiles']} offline"
    assert len(state.entities) == n_units_before + diag["count"], "spawn offline incomplet"
    assert len(_units(dec_after)) == n_live_before + diag["count"], "spawn live incomplet"
    cpos = _pos(_units(dec_after)[caster])
    for d in drones:
        assert hexgeo.distance(cpos, _pos(d)) == 1, \
            f"drone u{d['id']} en {_pos(d)} n'est PAS adjacent au caster {cpos}"
    ctile = board.id_at(*cpos)
    for t in diag["tiles"]:
        assert t in board.neighbours(ctile), \
            f"tuile de spawn offline {t} hors du voisinage du caster"


# ------------------------------------------------------------------ 1082 InspiredToGreatness

def _drive_until_ally_damaged(rpc, rid, ally_vid, max_iter=8):
    """DRIVE : avance vers les orks et laisse l'IA NATIVE jouer son tour jusqu'a ce que `ally_vid`
    soit ENDOMMAGE (le soin/repair de 1082 est plafonne par `FillUp` -> une cible a PV pleins rendrait
    0 et le montant serait INOBSERVABLE)."""
    for _ in range(max_iter):
        dec = _dec(rpc, rid)
        hp = _hp_live(rpc, rid)
        ally = _find(dec, ally_vid)
        aun = _find(dec, "tauAunShi")
        foes = [u for u in _foes(dec) if hp.get(u["id"], (1, 1))[0] > 0]
        if ally is None or aun is None or not foes:
            return None
        if hp.get(aun["id"], (0, 1))[0] <= 0:
            return None                                   # le caster est mort -> scenario perdu
        if hp.get(ally["id"], (1, 1))[0] < hp.get(ally["id"], (1, 1))[1]:
            return ally["id"]
        apos = _pos(ally)
        near = min(foes, key=lambda f: hexgeo.distance(apos, _pos(f)))
        cands = _movable(rpc, rid, ally["id"])
        if cands:
            apos = min(cands, key=lambda q: hexgeo.distance(q, _pos(near)))
            _move(rpc, rid, ally["id"], apos)
        cands = _movable(rpc, rid, aun["id"])
        if cands:                                         # Aun'Shi reste ADJACENT (cast unit-target)
            ok = [q for q in cands if hexgeo.distance(q, apos) == 1]
            _move(rpc, rid, aun["id"], ok[0] if ok else min(cands, key=lambda q: hexgeo.distance(q, apos)))
        _endturn(rpc, rid, 1)
        _ai_turn(rpc, rid)
    return None


def test_inspired_to_greatness_confront_live(rpc_, build_runner):
    """1082 `InspiredToGreatnessAbility$$ExecuteBehaviour` -- les TROIS volets, sur la branche
    DISCRIMINANTE `canReset` (l'allie A consomme son actif) :

      * le SPLIT de montant : `hpToHeal` (petit) et NON `hpToHeal_2` (grand) -- les deux valeurs
        different d'un facteur 4, un port qui se tromperait de branche serait visible au PV pres ;
      * la branche `Repair` de `If(IsRepairable, Repair, Heal)` : la cible (`tauCrisis`) est
        MECANIQUE. Si le port prenait `Heal`, la garde `healable_heal_type_0` la rejetterait et le
        gain de PV serait NUL -- le +N PV mesure PROUVE donc l'aiguillage ;
      * `ResetActiveAbility` : l'actif de l'allie redevient `usable` cote LIVE.

    On garde une TROISIEME unite non activee pour que le cast ne finisse PAS le tour d'equipe : sinon
    le passage a l'adversaire ACTIVE les effets d'overwatch de l'allie (`On(0x12)`) et pollue
    l'empreinte d'effets avec des effets que 1082 n'a pas poses."""
    rid = build_runner("114004", ["--p-units", "tauCrisis,tauAunShi,tauMarksman",
                                  "--a-units", "orksNob,orksNob", "--hp-player", "60000"],
                       board=BOARD)["rid"]
    ally = _drive_until_ally_damaged(rpc_, rid, "tauCrisis")
    if ally is None:
        pytest.fail("scenario NON atteint : l'allie n'a jamais ete endommage (drive/IA KO)")
    caster = _find(_dec(rpc_, rid), "tauAunShi")["id"]
    # l'allie CONSOMME son actif -> `CanStillBeUsed = false` -> il entre dans `canReset`.
    act0 = _cast(rpc_, rid, ally, EARLY_WARNING_OVERRIDE)
    assert not act0.get("error") and act0.get("mutated") is True, \
        f"le cast prealable de l'allie (1077) n'a pas mute l'etat: {act0}"
    fh = _from_here(rpc_, rid, caster, INSPIRED_TO_GREATNESS)
    assert any(t.get("targetId") == ally for t in fh), (
        f"1082 sur u{ally} ILLEGAL depuis la position courante (fromHere={fh}) -- le cast serait "
        f"REFUSE (mutated:false), indiscernable d'une ability inerte (#111)")

    state, _board, _d = _load(rpc_, rid)
    off_hp_before, off_eff_before = _hp_off(state), _footprint_off(state)
    res = _apply_active_ability(state, caster, ally, INSPIRED_TO_GREATNESS)
    diag = (res or {}).get("diag") or {}
    assert res.get("routed") == "handler" and diag.get("ported") is True, \
        f"1082 non portee (routed={res.get('routed')})"
    assert diag.get("unknown_reset_verdict") is False, \
        "verdict `EntityCanHaveActiveAbilityReset` INCONNU (canal ActiveAbilitiesComponent absent)"
    off_hp = {k: v - off_hp_before[k] for k, v in _hp_off(state).items()
              if k in off_hp_before and v != off_hp_before[k]}
    off_eff = _delta(off_eff_before, _footprint_off(state))

    live_hp_before, live_eff_before = _hp_live(rpc_, rid), _footprint_live(_dec(rpc_, rid))
    act = _cast(rpc_, rid, caster, INSPIRED_TO_GREATNESS, target=ally)
    assert not act.get("error"), f"cast natif bloque: {act.get('error')}"
    dec_after = _dec(rpc_, rid)
    live_hp = {k: v[0] - live_hp_before[k][0] for k, v in _hp_live(rpc_, rid).items()
               if k in live_hp_before and v[0] != live_hp_before[k][0]}
    live_eff = _delta(live_eff_before, _footprint_live(dec_after))
    usable = {a["id"]: a.get("usable") for a in (_units(dec_after)[ally].get("abilities") or [])}
    print(f"\n[1082] caster=u{caster} ally=u{ally} canReset={diag.get('can_reset')} "
          f"amounts={diag.get('amounts')}\n"
          f"       off dHP={off_hp} eff={off_eff}\n       live dHP={live_hp} eff={live_eff}\n"
          f"       usable(apres)={usable}")

    assert off_hp == live_hp, f"delta de PV offline {off_hp} != live {live_hp}"
    assert off_hp.get(ally), "aucun PV rendu a l'allie (la branche Repair/Heal n'a rien fait)"
    assert off_hp[ally] == diag["amounts"]["hpToHeal"], (
        f"montant {off_hp[ally]} != hpToHeal={diag['amounts']['hpToHeal']} "
        f"(hpToHeal_2={diag['amounts']['hpToHeal_2']}) -- MAUVAISE branche du split canReset")
    assert diag.get("can_reset") == [ally], \
        f"le split canReset devait contenir l'allie, vu {diag.get('can_reset')}"
    assert diag["repaired"] and diag["repaired"][0]["repairs"], \
        "la branche REPAIR n'a pas ete prise sur une cible MECANIQUE"
    assert off_eff == live_eff, f"empreinte d'effets offline {off_eff} != live {live_eff}"
    assert ITG_OVERRIDE_LEVEL in off_eff.get(ally, {}), \
        f"effet 1180 InspiredToGreatness_OverrideLevel absent de l'empreinte: {off_eff}"
    assert usable.get(EARLY_WARNING_OVERRIDE) is True, \
        f"l'actif de l'allie n'a PAS ete re-arme cote natif (usable={usable})"
    assert diag["reset"] and diag["reset"][0]["gate"] is True \
        and EARLY_WARNING_OVERRIDE in diag["reset"][0]["reset"], \
        f"ResetActiveAbility offline n'a pas re-arme l'actif: {diag.get('reset')}"
