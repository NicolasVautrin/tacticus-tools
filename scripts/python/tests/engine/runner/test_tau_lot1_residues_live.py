"""CONFRONT LIVE des DEUX residus du lot #114 (cf. `docs/rl/case-114-tau-lot1.md` §5) -- les deux
sont des TRIGGERS D'EFFET que le lot avait laisses inertes :

  1. `InspiredToGreatness_OverrideLevelEffect$$CreateRemoveEffectTrigger` = `On(0xc) & OwnerIsCaster`
     -> l'override d'`ACTIVE_ABILITY_LEVEL` (effet 1180) doit DISPARAITRE au prochain cast d'ACTIF de
     son porteur. Avant ce lot il etait PERMANENT offline.
  2. `AReactivateOverwatchEffect$$CreateHandleTriggerAbilitiesInternal` (via
     `EarlyWarningOverride_ReactivateOverwatchEffect`, 1145) -> un kill en OVERWATCH pose
     `EarlyWarningOverride_HitReduction` (1146) = `EXTRA_HITS -hitsReduction` sur le tueur. Avant ce
     lot, 1145 etait un `BaseEffect` INERTE.

Chaque test exerce la branche AVANT **et** APRES (l'effet est LA, puis il n'y est plus / il n'y etait
pas, puis il y est) -- sans quoi un port qui ne fait rien passerait la moitie des assertions.

Drive les positions ; lit l'etat LIVE ; state-files UNIQUES ; ASCII-only.
"""
from __future__ import annotations

from collections import deque

import pytest

import hexgeo
from engine.runner.operations.summon_ai import _apply_active_ability

EARLY_WARNING_OVERRIDE = 1077          # ActiveAbilityType (tauCrisis, Re'vas)
INSPIRED_TO_GREATNESS = 1082           # ActiveAbilityType (tauAunShi)
ITG_OVERRIDE_LEVEL = 1180              # EffectType.InspiredToGreatness_OverrideLevel
OVERWATCH_AUTO_ATTACK = 1009           # EffectType.Overwatch_AutoAttack
EWO_REACTIVATE_OVERWATCH = 1145        # EffectType.EarlyWarningOverride_ReactivateOverwatch
EWO_HIT_REDUCTION = 1146               # EffectType.EarlyWarningOverride_HitReduction
BOARD = "MC1_67"


# ------------------------------------------------------------------ harnais (idem test_tau_lot1_live)

@pytest.fixture(scope="module")
def rpc_(host, live_session):
    def _rpc(m, b, t=90):
        r = host._rpc(live_session, m, [b], timeout=t)
        return r.get("result") if isinstance(r, dict) and "result" in r else r
    return _rpc


def _board(rpc, rid):
    from engine.entities.pathfinding.board import Board
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    return Board(bg["tiles"], adjacency="evenq")


def _load(rpc, rid, board):
    from engine.runner.snapshot import load_state
    dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    return load_state(dec, ob, snap, board=board), dec


def _dec(rpc, rid):
    return rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)


def _units(dec):
    return {int(u["id"]): u for u in (dec.get("units") or [])}


def _pos(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row"))


def _find(dec, vid):
    return next((u for u in _units(dec).values() if u.get("visualId") == vid), None)


def _effs_live(dec, uid) -> dict:
    """`{effectType: remaining}` de l'unite -- `decisionView.effects` (deja filtre `IsActive`)."""
    u = _units(dec).get(int(uid))
    return {int(e["effectType"]): e.get("remaining") for e in ((u or {}).get("effects") or [])
            if e.get("effectType") is not None}


def _effs_off(state, uid) -> dict:
    """MEME empreinte cote port (`remaining_turns` None == le `remaining 0` live = permanent)."""
    effs = (state.effects.by_unit if state.effects is not None else {}).get(int(uid), [])
    return {int(e.effect_type): (0 if e.remaining_turns is None else int(e.remaining_turns))
            for e in effs if not e.consumed}


def _from_here(rpc, rid, caster, ability):
    at = rpc("abilityTargets", {"runnerId": rid, "unitId": caster, "abilityType": ability}, 90) or {}
    row = next((u for u in (at.get("units") or []) if u.get("unitId") == caster), None)
    ab = ((row or {}).get("abilities") or [{}])[0]
    return ab.get("fromHere") or []


def _movable(rpc, rid, uid):
    mv = rpc("aiMovableTiles", {"runnerId": rid}) or {}
    row = next((u for u in (mv.get("units") or []) if u.get("unitId") == uid), None)
    return [(t.get("col"), t.get("row")) for t in ((row or {}).get("tiles") or [])]


def _move(rpc, rid, uid, to):
    return rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": uid, "to": {"col": to[0], "row": to[1]}}}, 90)


def _endturn(rpc, rid, n=1):
    for _ in range(n):
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 90)


def _cast(rpc, rid, caster, ability, target=None):
    r = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": caster, "abilityType": ability,
        "targetId": (caster if target is None else target)}}, 90) or {}
    return (r.get("actions") or [{}])[0]


def _hp_live(rpc, rid) -> dict:
    ob = rpc("observeBattle", {"runnerId": rid}, 40) or {}
    return {u["squadId"]: (u["hp"], u.get("isDead")) for u in (ob.get("units") or [])}


# ============================================================ 1) retrait de l'override 1180 (#114 §5.2)

def _drive_aunshi_next_to_revas(rpc, rid, max_iter=6):
    """DRIVE : Aun'Shi ADJACENT a Re'vas (1082 est un cast UNIT-TARGET sur un allie adjacent)."""
    for _ in range(max_iter):
        dec = _dec(rpc, rid)
        aun, rv = _find(dec, "tauAunShi"), _find(dec, "tauCrisis")
        if aun is None or rv is None:
            return None, None, dec
        if hexgeo.distance(_pos(aun), _pos(rv)) == 1:
            return aun["id"], rv["id"], dec
        cands = _movable(rpc, rid, aun["id"])
        if cands:
            _move(rpc, rid, aun["id"], min(cands, key=lambda q: hexgeo.distance(q, _pos(rv))))
        else:
            _endturn(rpc, rid, 2)
    return None, None, _dec(rpc, rid)


def test_inspired_to_greatness_override_removed_on_next_active_cast_live(rpc_, build_runner):
    """`InspiredToGreatness_OverrideLevelEffect$$CreateRemoveEffectTrigger` = `On(0xc) &
    OwnerIsCaster` -> `BaseEffect$$GetRemoveEffectBehaviour`.

    SEQUENCE (les deux faces de la branche) :
      a. Re'vas CONSOMME son actif (1077) -> elle entre dans le `canReset` de 1082 ;
      b. Aun'Shi caste 1082 sur elle -> l'effet 1180 est POSE (et son actif re-arme).
         **CONTROLE `OwnerIsCaster`** : ce cast-la emet lui aussi `On(0xc)` (caster = Aun'Shi) et il est
         emis APRES l'execution de la behaviour -- un port qui aurait oublie le conjoint `OwnerIsCaster`
         (ou qui emettrait `On(0xc)` avant l'execution) retirerait le 1180 DANS LA FOULEE de sa pose.
         L'assertion << 1180 present apres (b) >> est donc discriminante, pas decorative ;
      c. le tour revient a Re'vas, elle RE-CASTE 1077 (l'utilisation supplementaire que 1082 lui a
         accordee) -> `On(0xc) & OwnerIsCaster` est enfin satisfait : 1180 doit DISPARAITRE, live
         comme offline. Avant ce lot l'override etait permanent cote port.
    """
    rid = build_runner("114101", ["--p-units", "tauCrisis,tauAunShi,tauMarksman",
                                  "--a-units", "orksNob,orksNob", "--no-ai"], board=BOARD)["rid"]
    board = _board(rpc_, rid)
    caster, ally, dec = _drive_aunshi_next_to_revas(rpc_, rid)
    if caster is None:
        pytest.fail("scenario NON atteint : Aun'Shi n'a pas pu se placer au contact de Re'vas")

    # (a) l'allie CONSOMME son actif -> `CanStillBeUsed = false` -> il entre dans `canReset`.
    act0 = _cast(rpc_, rid, ally, EARLY_WARNING_OVERRIDE)
    assert not act0.get("error") and act0.get("mutated") is True, \
        f"le cast prealable de Re'vas (1077) n'a pas mute l'etat: {act0}"

    # (b) Aun'Shi caste 1082 -> pose de 1180 sur Re'vas.
    fh = _from_here(rpc_, rid, caster, INSPIRED_TO_GREATNESS)
    assert any(t.get("targetId") == ally for t in fh), \
        f"1082 sur u{ally} ILLEGAL depuis la position courante (fromHere={fh})"
    # CONTROLE `OwnerIsCaster` cote PORT : le MEME cast, joue OFFLINE, emet `On(0xc)` avec
    # caster=Aun'Shi APRES sa behaviour -- un port sans le conjoint `OwnerIsCaster` (ou qui emettrait
    # `On(0xc)` avant l'execution) retirerait le 1180 dans la foulee de sa pose.
    state_b, _db = _load(rpc_, rid, board)
    res_b = _apply_active_ability(state_b, caster, ally, INSPIRED_TO_GREATNESS)
    assert (res_b or {}).get("routed") == "handler", f"1082 non routee offline: {res_b}"
    assert ITG_OVERRIDE_LEVEL in _effs_off(state_b, ally), \
        (f"le port a retire 1180 DANS LE CAST QUI LE POSE (effets={_effs_off(state_b, ally)}) -- "
         f"le conjoint `OwnerIsCaster` d'`On(0xc)` n'est pas applique")
    act1 = _cast(rpc_, rid, caster, INSPIRED_TO_GREATNESS, target=ally)
    assert not act1.get("error"), f"cast 1082 bloque: {act1.get('error')}"
    live_posed = _effs_live(_dec(rpc_, rid), ally)
    assert ITG_OVERRIDE_LEVEL in live_posed, \
        f"1180 absent apres le cast de 1082 (effets={live_posed}) -- scenario NON monte"

    # (c) le tour revient a Re'vas (son tour a ete clos par son propre cast de 1077).
    _endturn(rpc_, rid, 2)
    dec_before = _dec(rpc_, rid)
    live_before = _effs_live(dec_before, ally)
    assert ITG_OVERRIDE_LEVEL in live_before, \
        f"1180 a disparu AVANT le 2e cast (effets={live_before}) -- l'oracle serait fausse"
    usable = {a["id"]: a.get("usable") for a in (_units(dec_before)[ally].get("abilities") or [])}
    if usable.get(EARLY_WARNING_OVERRIDE) is not True:
        pytest.skip(f"l'actif de Re'vas n'est pas re-arme au tour suivant (usable={usable})")

    # --- confront : MEME cast, offline puis live ---
    state, _d = _load(rpc_, rid, board)
    off_before = _effs_off(state, ally)
    assert ITG_OVERRIDE_LEVEL in off_before, \
        f"1180 absent de l'etat OFFLINE seede (effets={off_before}) -- le canal de seed a change"
    res = _apply_active_ability(state, ally, ally, EARLY_WARNING_OVERRIDE)
    assert (res or {}).get("routed") == "handler", f"1077 non routee offline: {res}"
    off_after = _effs_off(state, ally)

    act2 = _cast(rpc_, rid, ally, EARLY_WARNING_OVERRIDE)
    assert not act2.get("error"), f"2e cast 1077 bloque: {act2.get('error')}"
    live_after = _effs_live(_dec(rpc_, rid), ally)

    print(f"\n[1180] caster=u{caster} porteur=u{ally}\n"
          f"       off  {sorted(off_before)} -> {sorted(off_after)}\n"
          f"       live {sorted(live_before)} -> {sorted(live_after)}")

    assert ITG_OVERRIDE_LEVEL not in live_after, \
        f"le natif n'a PAS retire 1180 au 2e cast d'actif (effets={live_after}) -- RE a revoir"
    assert ITG_OVERRIDE_LEVEL not in off_after, \
        f"le port a GARDE l'override 1180 apres le 2e cast d'actif (effets={off_after})"
    # le retrait doit avoir RESTAURE le niveau d'ability (part OVERRIDE de `<Effect>.RevertInternal`).
    from engine.runner.components import StatsComponent
    sc = state.get_entity(int(ally)).get_component(StatsComponent)
    lvl_after = getattr(sc.ctx, "active_ability_level", None) if sc is not None else None
    assert lvl_after is not None, "active_ability_level illisible apres le retrait de l'override"


# ============================================================ 2) re-entree en overwatch (#114 §5.3)

def _max_range(vid: str) -> int:
    import gameconfig as GC
    ws = (GC.unit(vid) or {}).get("weapons") or []
    return max([int(w.get("Range") or 0) for w in ws] or [0]) or 1


def test_early_warning_override_reactivate_overwatch_live(rpc_, build_runner):
    """`AReactivateOverwatchEffect$$CreateHandleTriggerAbilitiesInternal`, Triggered #1, specialise par
    `EarlyWarningOverride_ReactivateOverwatchEffect` (1145).

    SCENARIO : Re'vas caste 1077 (elle porte des lors 1009 + 1145), la main passe a l'adversaire, et
    on DRIVE un ork (PV forces a 1 par `--hp-target 1`) d'UN PAS dans sa portee de tir. Le vecteur
    after-move declenche l'overwatch, qui TUE -> `KillUnitOperation$$RecordDeathReason` grave sur la
    victime une `DamageSource` d'`AbilityOrEffect` = 1009 (via
    `StaticBattleRules$$GetDamageSourceAbility` : une attaque REGULIERE declenchee par un effet
    s'attribue a son DECLENCHEUR) -> `LegitDeathReasons` est satisfait -> Re'vas recoit
    `EarlyWarningOverride_HitReduction` (1146).

    Les DEUX faces sont verifiees : 1146 ABSENT avant le kill, PRESENT apres -- live ET offline (le
    move est REJOUE offline depuis l'etat capture AVANT, MT cale par `dumpRng`)."""
    from engine.runner.runner import Runner
    from engine.runner.messages import MoveUnitMessage
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.components import StatsComponent, UnitComponent
    from engine.entities.stats import StatType

    rid = build_runner("114102", ["--p-units", "tauCrisis,tauMarksman",
                                  "--a-units", "orksNob,orksNob",
                                  "--hp-target", "1"], board=BOARD)["rid"]
    board = _board(rpc_, rid)
    dec = _dec(rpc_, rid)
    rv = _find(dec, "tauCrisis")
    assert rv is not None, "tauCrisis absent du runner"
    revas = rv["id"]
    my_player = rv.get("owner")
    my_team = rv.get("team")
    R = _max_range("tauCrisis")                 # portee de tir de Re'vas (= portee d'overwatch)
    FOE_MOVE = 4                                # `orksNob` move (affiche par le builder) -- borne de drive

    # DRIVE (les DEUX camps : `applyAction move` accepte l'unite du joueur COURANT, adversaire compris) :
    # on rapproche Re'vas des orks tant qu'ils sont hors de portee-de-pas, on caste 1077 des que le
    # PROCHAIN pas d'un ork peut le faire entrer dans sa portee, puis on fait entrer l'ork.
    fired = None
    cast_done = False
    for _ in range(10):
        dec = _dec(rpc_, rid)
        if not dec.get("ok", True) or _units(dec).get(revas) is None:
            break                                       # bataille finie / vue indisponible
        rvl = _units(dec)[revas]
        rpos = _pos(rvl)
        hp = _hp_live(rpc_, rid)
        foes = [u for u in _units(dec).values()
                if u.get("team") != my_team and hp.get(u["id"], (0, None))[0] > 0]
        if not foes:
            break
        dmin = min(hexgeo.distance(rpos, _pos(f)) for f in foes)

        if dec.get("currentPlayer") == my_player:
            if not cast_done and dmin <= FOE_MOVE + R:
                # a portee de PAS : on arme l'overwatch MAINTENANT (le cast clot son tour).
                fh = _from_here(rpc_, rid, revas, EARLY_WARNING_OVERRIDE)
                assert any(t.get("targetId") == revas for t in fh), \
                    f"self-cast 1077 ILLEGAL depuis la position courante (fromHere={fh})"
                act = _cast(rpc_, rid, revas, EARLY_WARNING_OVERRIDE)
                assert not act.get("error"), f"cast 1077 bloque: {act.get('error')}"
                cast_done = True
            elif not cast_done:
                near = min(foes, key=lambda f: hexgeo.distance(rpos, _pos(f)))
                cands = [q for q in _movable(rpc_, rid, revas)
                         if hexgeo.distance(q, _pos(near)) > R]     # rester HORS de portee
                if cands:
                    _move(rpc_, rid, revas,
                          min(cands, key=lambda q: hexgeo.distance(q, _pos(near))))
            _endturn(rpc_, rid, 1)
            continue

        # --- tour ADVERSE : on fait AVANCER les orks (le tour bascule seul quand ils ont agi) ---
        if cast_done:
            rv_effs = _effs_live(dec, revas)
            assert OVERWATCH_AUTO_ATTACK in rv_effs and EWO_REACTIVATE_OVERWATCH in rv_effs, \
                f"Re'vas n'est pas en overwatch avec 1145 (effets={rv_effs}) -- scenario NON monte"
            assert EWO_HIT_REDUCTION not in rv_effs, \
                f"1146 deja present AVANT le kill (effets={rv_effs}) -- l'oracle serait fausse"
        moved = False
        for foe in foes:
            tiles = _movable(rpc_, rid, foe["id"])
            if not tiles:
                continue
            best = min(tiles, key=lambda q: hexgeo.distance(q, rpos))
            enters = cast_done and hexgeo.distance(best, rpos) <= R
            state = off_before = None
            if enters:
                # === capture AVANT le move (etat + MT cale : l'overwatch est le 1er conso RNG) ===
                state, _d = _load(rpc_, rid, board)
                s0 = rpc_("dumpRng", {"runnerId": rid}, 30)
                if not (isinstance(s0, dict) and s0.get("mt")):
                    pytest.skip("dumpRng KO")
                rng = IntBasedMersenneTwister()
                rng.mt = list(s0["mt"])
                rng.mti = s0["mti"]
                state.rng = rng
                off_before = _effs_off(state, revas)
            _move(rpc_, rid, foe["id"], best)             # === move LIVE ===
            moved = True
            if not enters:
                continue
            if _hp_live(rpc_, rid).get(foe["id"], (1, None))[0] > 0:
                continue                                  # pas tue par l'overwatch -> continuer
            runner = Runner(state).install_default_handlers(20)     # === REPLAY offline ===
            runner.apply(MoveUnitMessage(foe["id"], best))
            fired = {"foe": foe["id"], "tile": best, "off_before": off_before,
                     "state": state, "after_move": runner.movement_handler.after_move}
            break
        if fired is not None:
            break
        if not moved:
            break                                        # plus rien a bouger : budget de tours epuise
    if fired is None:
        pytest.fail("scenario NON atteint : aucun kill en overwatch obtenu (drive des positions KO)")

    state = fired["state"]
    off_after = _effs_off(state, revas)
    live_after = _effs_live(_dec(rpc_, rid), revas)
    sc = state.get_entity(int(revas)).get_component(StatsComponent)
    extra_hits = int(sc.ctx.stat(StatType.EXTRA_HITS)) if sc is not None else None
    dead = state.get_entity(int(fired["foe"])).get_component(UnitComponent)
    print(f"\n[1146] revas=u{revas} tue u{fired['foe']} en {fired['tile']}\n"
          f"       off  {sorted(fired['off_before'])} -> {sorted(off_after)}\n"
          f"       live {sorted(live_after)}\n"
          f"       EXTRA_HITS offline={extra_hits} death_source={getattr(dead, 'death_source', None)}")

    assert EWO_HIT_REDUCTION not in fired["off_before"], \
        f"1146 deja present dans l'etat offline AVANT le move ({fired['off_before']})"
    assert EWO_HIT_REDUCTION in live_after, \
        f"le natif n'a PAS pose 1146 apres le kill en overwatch (effets={live_after}) -- RE a revoir"
    assert EWO_HIT_REDUCTION in off_after, \
        f"le port n'a PAS pose 1146 apres le kill en overwatch (effets={off_after})"
    assert off_after[EWO_HIT_REDUCTION] == live_after[EWO_HIT_REDUCTION], \
        (f"remaining offline {off_after[EWO_HIT_REDUCTION]} != live "
         f"{live_after[EWO_HIT_REDUCTION]} pour 1146")
    # la DEATH-REASON gravee doit etre l'EFFET 1009, pas l'attaque normale (GetDamageSourceAbility).
    assert getattr(dead, "death_source", None) is not None \
        and dead.death_source[2] == OVERWATCH_AUTO_ATTACK, \
        f"death_source offline inattendue: {getattr(dead, 'death_source', None)}"
    # le stat-mod EXTRA_HITS est NEGATIF (`Negative(HitReductionValue())`).
    assert extra_hits is not None and extra_hits < 0, \
        f"EXTRA_HITS offline {extra_hits} : le stat-mod -hitsReduction n'a pas ete applique"


# ================================================== 3) GENERALISATION : les DEUX gates, en negatif

def test_tau_lot1_residues_gates_negative_live(rpc_, build_runner):
    """GENERALISATION la plus DISCRIMINANTE des deux ports : la MEME unite (Re'vas), le MEME etat
    (1180 pose, overwatch arme), mais une ACTION D'UN AUTRE GENRE -- une ATTAQUE NORMALE, pendant SON
    tour, qui TUE. Elle exerce les trois conjoints qu'un port << colle au scenario nominal >> raterait :

      * `StaticBattleRules.ActiveAbility$$IsActiveAbility` : une attaque REGULIERE n'emet PAS
        `On(0xc)` -> l'override de niveau 1180 doit SURVIVRE a l'attaque. Un port qui emettrait
        `On(UnitActiveAbility)` depuis la voie normale (les deux voies emettent bien `On(0x2b)` et
        `On(0xe)`, #120 -- l'erreur est naturelle) le retirerait ici.
      * `AReactivateOverwatchEffect` conjoint `NOT IsTurnOf(owner@0x148)` : le kill a lieu pendant le
        tour de Re'vas -> pas de re-entree en overwatch.
      * `LegitDeathReasons` : la `DamageSource` gravee est l'ATTAQUE NORMALE (le marqueur de kind
        0x3f5), pas l'effet 1009 -> `HasDeathReason(dying, Ability, 0x3f1)` est FAUX. Un port qui
        aurait rabattu << toute mort causee par le porteur >> poserait 1146 ici.

    -> 1180 PRESENT et 1146 ABSENT, live comme offline, apres un kill qui pourtant remplit
    << le porteur a tue >>."""
    from engine.runner.operations.damage import AttackDamageOperation
    from engine.runner.prng import IntBasedMersenneTwister

    rid = build_runner("114103", ["--p-units", "tauCrisis,tauAunShi,tauMarksman",
                                  "--a-units", "orksNob,orksNob",
                                  "--hp-target", "1"], board=BOARD)["rid"]
    board = _board(rpc_, rid)
    caster, ally, dec = _drive_aunshi_next_to_revas(rpc_, rid)
    if caster is None:
        pytest.fail("scenario NON atteint : Aun'Shi n'a pas pu se placer au contact de Re'vas")
    revas, my_player = ally, _units(dec)[ally].get("owner")
    my_team = _units(dec)[ally].get("team")
    R = _max_range("tauCrisis")

    # (a) Re'vas consomme son actif (1077) : elle ARME l'overwatch (1009 + 1145) ET entre dans
    #     le `canReset` de 1082.
    act0 = _cast(rpc_, rid, revas, EARLY_WARNING_OVERRIDE)
    assert not act0.get("error") and act0.get("mutated") is True, f"cast 1077 KO: {act0}"
    _endturn(rpc_, rid, 1)

    # (b) tour ADVERSE : on rapproche les orks en les gardant HORS de portee d'overwatch (sinon le
    #     tir partirait ici et poserait 1146 -- ce qui ruinerait le discriminant).
    for _ in range(4):
        dec = _dec(rpc_, rid)
        if not dec.get("ok", True) or dec.get("currentPlayer") == my_player:
            break
        rpos = _pos(_units(dec)[revas])
        moved = False
        for foe in [u for u in _units(dec).values() if u.get("team") != my_team and u.get("alive")]:
            tiles = [q for q in _movable(rpc_, rid, foe["id"]) if hexgeo.distance(q, rpos) > R]
            if not tiles:
                continue
            _move(rpc_, rid, foe["id"], min(tiles, key=lambda q: hexgeo.distance(q, rpos)))
            moved = True
        if not moved:
            break
    dec = _dec(rpc_, rid)
    if dec.get("currentPlayer") != my_player:
        _endturn(rpc_, rid, 1)
        dec = _dec(rpc_, rid)
    assert dec.get("currentPlayer") == my_player, \
        f"la main n'est pas revenue au joueur (currentPlayer={dec.get('currentPlayer')})"

    # (c) Aun'Shi caste 1082 sur Re'vas -> 1180 pose (son actif est aussi re-arme, sans importance ici).
    fh = _from_here(rpc_, rid, caster, INSPIRED_TO_GREATNESS)
    assert any(t.get("targetId") == revas for t in fh), \
        f"1082 sur u{revas} ILLEGAL depuis la position courante (fromHere={fh})"
    act1 = _cast(rpc_, rid, caster, INSPIRED_TO_GREATNESS, target=revas)
    assert not act1.get("error"), f"cast 1082 bloque: {act1.get('error')}"

    # (d) Re'vas se rapproche d'un ork jusqu'a portee de tir, puis l'ATTAQUE (kill : PV forces a 1).
    dec = _dec(rpc_, rid)
    rpos = _pos(_units(dec)[revas])
    foes = [u for u in _units(dec).values() if u.get("team") != my_team and u.get("alive")]
    if not foes:
        pytest.fail("scenario NON atteint : plus d'ennemi vivant")
    near = min(foes, key=lambda f: hexgeo.distance(rpos, _pos(f)))
    if hexgeo.distance(rpos, _pos(near)) > R:
        cands = [q for q in _movable(rpc_, rid, revas)
                 if hexgeo.distance(q, _pos(near)) <= R]
        if not cands:
            pytest.fail("scenario NON atteint : Re'vas ne peut pas se mettre a portee de tir "
                        "(drive des positions KO)")
        _move(rpc_, rid, revas, min(cands, key=lambda q: hexgeo.distance(q, _pos(near))))
    dec = _dec(rpc_, rid)
    live_before = _effs_live(dec, revas)
    assert ITG_OVERRIDE_LEVEL in live_before, \
        f"1180 absent AVANT l'attaque (effets={live_before}) -- scenario NON monte"
    assert EWO_HIT_REDUCTION not in live_before, \
        f"1146 deja present AVANT l'attaque (effets={live_before})"

    state, _d = _load(rpc_, rid, board)
    s0 = rpc_("dumpRng", {"runnerId": rid}, 30)
    if not (isinstance(s0, dict) and s0.get("mt")):
        pytest.skip("dumpRng KO")
    rng = IntBasedMersenneTwister()
    rng.mt = list(s0["mt"])
    rng.mti = s0["mti"]
    state.rng = rng
    off_before = _effs_off(state, revas)
    AttackDamageOperation.execute(state, revas, near["id"], 20)          # === attaque OFFLINE ===
    off_after = _effs_off(state, revas)

    # ATTAQUE NORMALE LIVE : `applyAction` n'a pas de kind "attack" -- l'attaque normale EST une
    # active ability (`ALoki_NormalAttackAbility`), d'`ActiveAbilityType` per-unite (memoire
    # << normal attack = concrete ability id >>), donnee par `decisionView.abilities[kind=normal]`.
    normal_ab = next((a["id"] for a in (_units(dec)[revas].get("abilities") or [])
                      if a.get("kind") == "normal"), None)
    assert normal_ab is not None, \
        f"pas d'entree d'attaque normale dans decisionView: {_units(dec)[revas].get('abilities')}"
    act2 = _cast(rpc_, rid, revas, normal_ab, target=near["id"])          # === attaque LIVE ===
    assert not act2.get("error"), f"attaque normale bloquee: {act2.get('error')}"
    hp = _hp_live(rpc_, rid)
    live_after = _effs_live(_dec(rpc_, rid), revas)
    from engine.runner.components import UnitComponent
    dead_off = state.get_entity(int(near["id"])).get_component(UnitComponent)
    print(f"\n[gates] revas=u{revas} attaque u{near['id']} hp_live={hp.get(near['id'])}\n"
          f"       off  {sorted(off_before)} -> {sorted(off_after)}\n"
          f"       live {sorted(live_before)} -> {sorted(live_after)}\n"
          f"       death_source offline={getattr(dead_off, 'death_source', None)}")
    if hp.get(near["id"], (1, None))[0] > 0:
        pytest.fail("scenario NON atteint : l'attaque normale n'a pas tue (PV cible non forces ?)")

    assert ITG_OVERRIDE_LEVEL in live_after, \
        f"le natif a retire 1180 sur une ATTAQUE NORMALE (effets={live_after}) -- RE a revoir"
    assert ITG_OVERRIDE_LEVEL in off_after, \
        (f"le port a retire 1180 sur une ATTAQUE NORMALE (effets={off_after}) -- le gate "
         f"`IsActiveAbility` d'`On(0xc)` n'est pas applique")
    assert EWO_HIT_REDUCTION not in live_after, \
        f"le natif a pose 1146 sur un kill HORS overwatch (effets={live_after}) -- RE a revoir"
    assert EWO_HIT_REDUCTION not in off_after, \
        (f"le port a pose 1146 sur un kill HORS overwatch pendant le tour du porteur "
         f"(effets={off_after}) -- gates `NOT IsTurnOf` / `LegitDeathReasons` non appliques")
    assert getattr(dead_off, "death_source", None) is not None \
        and dead_off.death_source[2] != OVERWATCH_AUTO_ATTACK, \
        (f"la raison de mort offline est l'effet d'overwatch alors que le kill vient d'une attaque "
         f"normale: {getattr(dead_off, 'death_source', None)}")
