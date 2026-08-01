"""#366-r1b -- `1111 WireweaveNet_CounterAttack` (passif `WireweaveNet` d'`eldarRanger`
<< Calandis >>) : RIPOSTE `On(0x2a = PreUnitAbility)` AVANT que l'attaque entrante ne s'execute,
UNE SEULE FOIS par tour ennemi.

RE + residus : `engine/runner/operations/triggers/loki/wireweave_net.py`
(chaine `WireweaveNetAbility` -> `WireweaveNet_CounterAttackEffect : CounterAttackEffect :
PlayerTurnEffect`), face DECISION : `engine/utilities/wireweave_net.py`.

Scenarios CRAFTES (positions et tour PILOTES -- le runner est un bac a sable), confrontes au LIVE
par REPLAY-DIFF RNG-seede :

 1. POSITIF   -- un ennemi MELEE adjacent frappe Calandis pendant le tour ADVERSE -> la riposte part
                 (2 coups `Piercing` sur l'attaquant) PUIS l'attaque entrante ; PV offline == PV live
                 des DEUX cotes (le stream RNG reste aligne -> la riposte est jouee au MEME rang).
 2. NEGATIF `IsMeleeAttack` -- MEME cible, attaquant RANGED a 2 hexes -> AUCUNE riposte.
 3. ARMEMENT -- le flag `EffectComponent.IsActive @+0x5c` de l'instance 1111, lu sur le canal
                 `decisionView includeInactive` : VRAI avant le coup, FAUX apres. C'est la mesure
                 DIRECTE du `& DeactivateEffect(effect)` de `$$CreateTargetTriggerBehaviour`
                 (= le "the FIRST time" d'i2), et du fait que l'effet EXISTE meme inactif.
 4. ATTRIBUTION -- les montants de la riposte sont dans les bornes `minDmg/maxDmg[niveau PASSIF] x
                 multiplicateur`, et l'instance offline est bien de la classe portee. Sans cette
                 garde, "l'attaquant perd des PV" serait VERT pour l'Overwatch de Calandis, qui
                 frappe le meme adversaire sur un AUTRE vecteur.
 5. FENETRE (offline pur) -- le LIVE REFUSE l'action d'une unite hors-tour, donc le conjoint
                 `NOT IsTurnOf(Owner)` s'isole en basculant `state.current_player_id` sur l'etat
                 DEJA charge (meme parti que #133).

Lit l'etat LIVE (rien de hardcode). ASCII only.
"""
from __future__ import annotations

import json
from collections import deque

import pytest

from engine.entities.effect_type import EffectType
from engine.entities.effects.loki.counter_attack import WireweaveNetCounterAttackEffect
from engine.entities.effects.magnitude import ability_var
from engine.entities.pathfinding.board import Board
from engine.runner.components import HealthComponent
from engine.runner.messages import AttackUnitMessage
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.runner import Runner
from engine.runner.snapshot import load_state

CARRIER = "eldarRanger"           # Calandis -- HERO au pool, porteur du passif `WireweaveNet`
MELEE_ATTACKER = "orksNob"        # melee pur -> cas POSITIF
RANGED_ATTACKER = "necroWarden"   # arme Range 3 (Gauss) -> cas NEGATIF `IsMeleeAttack`
EFFECT = int(EffectType.WireweaveNet_CounterAttack)     # 0x457 = 1111
ABILITY = "WireweaveNet"


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _seed_rng(s):
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"]); rng.mti = s["mti"]
    return rng


def _bfs(board, src):
    dist = {src: 0}; q = deque([src])
    while q:
        x = q.popleft()
        for n in board.neighbours(x):
            if n not in dist and (n == src or board.walkable(n)):
                dist[n] = dist[x] + 1; q.append(n)
    return dist


def _alive(dv, vis):
    return next((u for u in (dv.get("units") or [])
                 if u.get("visualId") == vis and u.get("alive")), None)


def _row(dv, uid):
    return next((u for u in (dv.get("units") or []) if u.get("id") == uid), None)


def _eff(u, etype):
    return next((e for e in ((u or {}).get("effects") or []) if e.get("effectType") == etype), None)


def _scenario(rpc, build_runner, attacker, want_dist):
    """Monte le duel Calandis vs `attacker`, amene CALANDIS a `want_dist` hexes de l'attaquant (on
    deplace MON unite : son propre Overwatch ne se declenche donc pas pendant le placement), passe au
    tour ADVERSE, puis rejoue l'attaque de l'ennemi LIVE et OFFLINE. Renvoie la classification ou
    `{ok: False, reason}` (le test appelant decide skip/fail)."""
    b = build_runner("777", extra=["--roster", "1", "--p-units", CARRIER,
                                   "--a-units", attacker,
                                   "--hp-player", "999999", "--hp-target", "999999",
                                   "--crit", "0,0", "--crit-target", "0,0",
                                   "--block-target", "0,0", "--block-player", "0,0"])
    rid = b["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and "tiles" in bg):
        return {"ok": False, "reason": "boardGraph indispo"}
    board = Board(bg["tiles"], adjacency="native_sym")

    def tile(u):
        p = u.get("pos") or {}
        return board.id_at(p.get("col"), p.get("row"))

    for _turn in range(30):
        dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        if not _ok(dv):
            return {"ok": False, "reason": "decisionView KO"}
        car, att = _alive(dv, CARRIER), _alive(dv, attacker)
        if car is None or att is None:
            return {"ok": False, "reason": "unite manquante"}
        dist = _bfs(board, tile(att))
        if dist.get(tile(car)) == want_dist:
            break
        if dv.get("currentPlayer") != car.get("owner"):
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
            continue
        mt = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
        row = next((x for x in (mt.get("units") or []) if x.get("unitId") == car["id"]), None)
        reach = {board.id_at(t["col"], t["row"]): (t["col"], t["row"])
                 for t in ((row or {}).get("tiles") or [])}
        exact = [t for t in reach if dist.get(t) == want_dist]
        pool = exact or [t for t in reach if t in dist]
        if not pool:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
            continue
        best = exact[0] if exact else min(pool, key=lambda t: dist[t])
        col, r = reach[best]
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": car["id"], "to": {"col": col, "row": r}}}, 40)
        if not exact:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
    # tour ADVERSE = la fenetre d'armement (`turnsEnabled = 1` -> `NOT IsTurnOf(Owner)`)
    for _ in range(4):
        dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        car = _alive(dv, CARRIER)
        if car is not None and dv.get("currentPlayer") != car.get("owner"):
            break
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    car, att = _alive(dv, CARRIER), _alive(dv, attacker)
    if car is None or att is None:
        return {"ok": False, "reason": "unite manquante post-setup"}
    got = _bfs(board, tile(att)).get(tile(car))
    if got != want_dist:
        return {"ok": False, "reason": f"distance {got} != {want_dist} apres pilotage"}
    norm = next((a for a in (att.get("abilities") or []) if a.get("kind") == "normal"), None)
    if norm is None:
        return {"ok": False, "reason": "pas d'attaque normale sur l'attaquant"}

    # -- ARMEMENT AVANT le coup, lu sur le canal `includeInactive` (le flag @+0x5c est publie la)
    dvi = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True,
                               "includeInactive": True}, 90)
    row_before = _eff(_row(dvi, car["id"]), EFFECT)

    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
    state = load_state(dv, ob, snap, board=board)   # board OBLIGATOIRE : `IsMeleeAttack` est POSITIONNEL
    uc = next((u.get("unitConfig") or {} for u in (snap.get("units") or [])
               if u.get("entityId") == car["id"]), {})
    plvl = uc.get("passiveAbilityLevel")
    mult = uc.get("abilityVariablesMultiplier") or 100
    hp_before = {}
    for u in (car, att):
        e = state.get_entity(u["id"])
        hc = e.get_component(HealthComponent) if e is not None else None
        if hc is None or hc.hp is None:
            return {"ok": False, "reason": "unite sans PV offline"}
        hp_before[u["id"]] = hc.hp
    inst = next((e for e in (state.effects.by_unit.get(car["id"]) or [])
                 if e.effect_type == EFFECT and not e.consumed), None)
    s0 = rpc("dumpRng", {"runnerId": rid}, 30)
    if not _ok(s0):
        return {"ok": False, "reason": "dumpRng KO"}
    state.rng = _seed_rng(s0)
    runner = Runner(state).install_default_handlers(20)

    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": att["id"], "targetId": car["id"],
        "abilityType": norm["id"]}}, 60)
    a0 = (res.get("actions") or [{}])[0]
    if not (_ok(res) and a0.get("ok")):
        return {"ok": False, "reason": f"attaque live KO: {str(res)[:150]}"}
    live_hp = {u.get("squadId"): u.get("hp") for u in (res.get("units") or [])}
    counter_amounts, dirty = [], False
    for e in (a0.get("events") or []):
        td = e.get("tags")
        if not td:
            continue
        td = json.loads(td) if isinstance(td, str) else td
        if td.get("Target_Id") == att["id"] and "Amount" in td:
            counter_amounts.append(int(td.get("Amount")))
            dirty = dirty or bool(td.get("Attack_DidCrit")) or bool(td.get("Attack_DidBlock"))

    dvi2 = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True,
                                "includeInactive": True}, 90)
    row_after = _eff(_row(dvi2, car["id"]), EFFECT)

    runner.apply(AttackUnitMessage(att["id"], car["id"]))
    off_hp = {}
    for u in (car, att):
        e = state.get_entity(u["id"])
        hc = e.get_component(HealthComponent) if e is not None else None
        off_hp[u["id"]] = hc.hp if hc is not None else None
    return {"ok": True, "reason": None, "state": state, "board": board, "rid": rid,
            "carrier": car["id"], "attacker": att["id"], "dist": got,
            "hp_before": hp_before, "live_hp": live_hp, "off_hp": off_hp,
            "counter_amounts": counter_amounts, "dirty": dirty,
            "inst": inst, "passive_level": plvl, "multiplier": mult,
            "armed_before": row_before, "armed_after": row_after,
            "dv": dv, "ob": ob, "snap": snap}


# ---------------------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def wwn_positive(live_session, rpc, build_runner):
    return _scenario(rpc, build_runner, MELEE_ATTACKER, want_dist=1)


@pytest.fixture(scope="module")
def wwn_ranged(live_session, rpc, build_runner):
    return _scenario(rpc, build_runner, RANGED_ATTACKER, want_dist=2)


def test_wireweave_net_counter_positive(wwn_positive):
    """POSITIF : attaque MELEE adjacente pendant le tour adverse -> la riposte part LIVE (l'attaquant
    perd des PV avant d'avoir frappe) et le REPLAY offline reproduit les PV des DEUX unites AU PV
    PRES. L'egalite sur la CIBLE (Calandis) prouve en outre que la riposte est jouee au MEME RANG
    dans le flux RNG que le natif : un decalage l'aurait desynchronise (c'est exactement le bruit
    de 263 que #366-r1 avait du neutraliser faute de ce port)."""
    c = wwn_positive
    if not c["ok"]:
        pytest.skip(c["reason"])
    cid, aid = c["carrier"], c["attacker"]
    assert c["live_hp"][aid] < c["hp_before"][aid], (
        "AUCUNE riposte live : l'attaquant garde ses PV "
        f"({c['live_hp'][aid]} == {c['hp_before'][aid]}) -- le scenario n'exerce rien")
    assert len(c["counter_amounts"]) == 2, (
        f"riposte live attendue en 2 coups (`GetNumberConstant(cfg, 0x2f)` = nrOfHits = 2), "
        f"obtenu {c['counter_amounts']}")
    assert c["off_hp"][aid] == c["live_hp"][aid], (
        f"PV ATTAQUANT offline {c['off_hp'][aid]} != live {c['live_hp'][aid]} "
        f"(riposte non reproduite : amounts live={c['counter_amounts']})")
    assert c["off_hp"][cid] == c["live_hp"][cid], (
        f"PV CALANDIS offline {c['off_hp'][cid]} != live {c['live_hp'][cid]} "
        "(flux RNG desynchronise -> la riposte n'est pas jouee au bon rang)")


def test_wireweave_net_counter_attribution(wwn_positive):
    """GARDE D'ATTRIBUTION : le degat encaisse par l'attaquant vient bien de la RIPOSTE 1111 et pas
    d'un autre canal du meme porteur (Calandis porte AUSSI `Overwatch`, dont l'auto-attaque frappe le
    meme adversaire). On exige (a) la classe d'effet portee, (b) 2 coups, (c) chaque coup <= la borne
    HAUTE `maxDmg[passif] x multiplicateur` du profil `Piercing` -- un tir d'Overwatch (arme Energy
    r3, degat de base 45 x stats) ne respecterait pas ce gabarit."""
    c = wwn_positive
    if not c["ok"]:
        pytest.skip(c["reason"])
    assert c["inst"] is not None, (
        "l'instance 1111 est ABSENTE de l'etat charge -- le seed `ABILITY_INIT_OWNER_EFFECTS"
        "['WireweaveNet']` ne compense pas le canal `decisionView` (actifs seuls)")
    assert type(c["inst"]) is WireweaveNetCounterAttackEffect, (
        f"1111 est route sur {type(c['inst']).__name__} au lieu de la classe portee")
    lo = ability_var(ABILITY, "minDmg", c["passive_level"], multiplier_pct=c["multiplier"])
    hi = ability_var(ABILITY, "maxDmg", c["passive_level"], multiplier_pct=c["multiplier"])
    assert lo and hi and lo <= hi
    assert not c["dirty"], "coup CRIT/BLOCK : le montage n'a pas neutralise les tirages"
    for amt in c["counter_amounts"]:
        assert 0 < amt <= hi, (
            f"coup de riposte {amt} hors du gabarit config [.., {hi}] "
            f"(minDmg={lo}) -- le degat n'est pas celui de 1111")


def test_wireweave_net_disarms_after_first_counter(wwn_positive):
    """"the FIRST time" : `$$CreateTargetTriggerBehaviour` = `GetCounterAttackBehaviour(effect) &
    DeactivateEffect(effect)`. Mesure DIRECTE du champ `EffectComponent.IsActive @+0x5c`, publie par
    `decisionView includeInactive` : VRAI avant le coup, FAUX apres -- l'entite-effet SURVIT (elle
    n'est pas retiree), seul son flag tombe. C'est ce qui distingue ce cas d'un `RemoveEffect`."""
    c = wwn_positive
    if not c["ok"]:
        pytest.skip(c["reason"])
    assert c["armed_before"] is not None, (
        "1111 absent du canal includeInactive AVANT le coup -- l'effet n'est pas pose")
    assert c["armed_before"].get("active") is True, (
        f"1111 non ARME pendant le tour ennemi : {c['armed_before']} "
        "(`On(TurnEnd) & IsTurnOf(Owner) -> ActivateEffect` n'a pas joue)")
    assert c["armed_after"] is not None, (
        "1111 a DISPARU apres la riposte : le natif DESACTIVE, il ne RETIRE pas")
    assert c["armed_after"].get("active") is False, (
        f"1111 encore arme apres la riposte : {c['armed_after']} "
        "-- le `& DeactivateEffect(effect)` ne mord pas, la riposte serait re-jouable le meme tour")


def test_wireweave_net_no_counter_on_ranged(wwn_ranged):
    """NEGATIF `IsMeleeAttack` (predicat POSITIONNEL natif) : MEME porteur, MEME evenement
    `On(0x2a = PreUnitAbility)`, mais l'attaquant tire a 2 hexes -> le natif ne riposte PAS. Sans le
    gate, le port infligerait 2 coups `Piercing` fantomes a l'attaquant."""
    c = wwn_ranged
    if not c["ok"]:
        pytest.skip(c["reason"])
    aid = c["attacker"]
    assert c["dist"] >= 2, f"scenario non discriminant : distance {c['dist']}"
    assert c["live_hp"][aid] == c["hp_before"][aid], (
        f"le natif a riposte a distance ({c['live_hp'][aid]} < {c['hp_before'][aid]}) -- "
        "le gate IsMeleeAttack ne serait pas ce que dit le decompile")
    assert c["off_hp"][aid] == c["live_hp"][aid], (
        f"RIPOSTE FANTOME offline : PV attaquant {c['off_hp'][aid]} != live {c['live_hp'][aid]}")
    assert c["off_hp"][c["carrier"]] == c["live_hp"][c["carrier"]], (
        f"PV Calandis offline {c['off_hp'][c['carrier']]} != live {c['live_hp'][c['carrier']]}")


def test_wireweave_net_window_is_enemy_turn_offline(wwn_positive):
    """FENETRE D'ARMEMENT, isolee OFFLINE : le LIVE refuse l'action d'une unite hors-tour, donc le
    conjoint `NOT IsTurnOf(Owner)` (branche `turnsEnabled = 1` d'`IsEnabledTurnType`) se confronte en
    basculant `state.current_player_id` sur l'etat DEJA charge -- MEME capture, MEME flux MT, MEME
    geometrie, SEUL le joueur courant change. Sans lui, Calandis riposterait pendant SON tour."""
    c = wwn_positive
    if not c["ok"]:
        pytest.skip(c["reason"])
    st = load_state(c["dv"], c["ob"], c["snap"], board=c["board"])
    cid, aid = c["carrier"], c["attacker"]
    st.current_player_id = _row(c["dv"], cid).get("owner")     # c'est le tour de CALANDIS
    hp0 = st.get_entity(aid).get_component(HealthComponent).hp
    st.rng = IntBasedMersenneTwister(1)
    Runner(st).install_default_handlers(20).apply(AttackUnitMessage(aid, cid))
    hp1 = st.get_entity(aid).get_component(HealthComponent).hp
    assert hp1 == hp0, (
        f"riposte jouee pendant le tour du PORTEUR (attaquant {hp0} -> {hp1}) -- "
        "la fenetre d'armement `NOT IsTurnOf(Owner)` ne ferme pas")
