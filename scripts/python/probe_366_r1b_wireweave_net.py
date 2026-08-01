"""Probe #366-r1b -- RIPOSTE `1111 WireweaveNet_CounterAttack` (`eldarRanger` << Calandis >>).

i2 : "The first time Calandis is targeted by a normal melee attack during the enemy's turn, the
attacker immediately takes 2x 873-1310 Piercing Damage. If the attacker is eliminated, their melee
attack is not executed."

Scenario CRAFTE (le runner est un bac a sable : on pilote les DEUX camps ; on DEPLACE les unites,
on ne subit jamais la geometrie de spawn) :

  1. build 1v1 Calandis (moi) vs un attaquant MELEE adverse ;
  2. on amene l'attaquant a distance 1 (ou 2 pour le cas negatif RANGED) ;
  3. `endturn` -> tour ADVERSE = la fenetre d'armement (`turnsEnabled = 1` -> `NOT IsTurnOf(Owner)`) ;
  4. CAPTURE (dv / dv+includeInactive / observeBattle / combatSnapshot / dumpRng) ;
  5. l'attaquant frappe Calandis d'une attaque NORMALE -> le natif joue d'abord la RIPOSTE
     (2 coups `Piercing` sur l'attaquant, `On(0x2a = PreUnitAbility)`) puis l'attaque entrante ;
  6. REPLAY-DIFF : la MEME capture + le MEME flux MT rejoues OFFLINE -> per-coup identiques DES DEUX
     COTES (riposte sur l'attaquant ET attaque entrante sur Calandis), et PV finaux identiques.

GARDE D'ATTRIBUTION (le point qui rend la mesure opposable) : "du degat sur l'attaquant" ne
suffit PAS -- Calandis porte AUSSI le trait `Overwatch`, dont l'auto-attaque coute du degat au
meme adversaire sur un AUTRE vecteur. On exige donc, cumulativement :
  * exactement `nrOfHits` = 2 coups attribues a l'attaquant DANS l'action de son attaque ;
  * chaque coup dans les bornes du profil `Piercing` derivees de `minDmg/maxDmg[niveau PASSIF] x
    multiplicateur de rarete` (bornes RAW ; le degat sante est <= car perce/armure diluent) ;
  * la CONTRE-EPREUVE offline (effet 1111 retire) qui fait DISPARAITRE ces coups ;
  * le CONTREFACTUEL de tour, qui les fait disparaitre AUSSI sans toucher a l'effet.

Cas NEGATIFS crates :
  --neg-owner-turn : DISCRIMINANT PUR de la fenetre d'armement -- MEME geometrie, MEME attaquant,
                     MEME cible, SEUL le joueur courant change (`applyAction` ne verifie pas la
                     propriete du `casterId`, cf. runner.md S4). Aucune riposte attendue.
  --neg-ranged     : l'attaquant frappe a distance 2 -> `IsMeleeAttack` (predicat POSITIONNEL) ferme.
  --two-attackers  : DEUX ennemis melee frappent dans le MEME tour -> riposte au PREMIER seulement
                     ("the FIRST time" = `& DeactivateEffect(effect)` du behaviour).
  --lethal         : attaquant a PV bas -> la riposte le TUE et son attaque est ANNULEE (gate
                     acteur-mort POST-`On(0x2a)` d'`ActiveAbilityOperation$$ExecuteInternal`, deja
                     porte par #133).

Usage : python probe_366_r1b_wireweave_net.py [--attacker orksNob] [--neg-owner-turn|--neg-ranged]
                                              [--two-attackers] [--lethal] [--board MC1_67]
                                              [--seed 777] [--keep]
ASCII only (console cp1252).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import deque
from pathlib import Path

import rl_collect_batch as R
from engine.entities.effects.magnitude import ability_var
from engine.entities.pathfinding.board import Board
from engine.entities.effect_type import EffectType
from engine.runner.components import HealthComponent
from engine.runner.messages import AttackUnitMessage
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.runner import Runner
from engine.runner.snapshot import load_state

PYDIR = Path(__file__).resolve().parent
LOGS = PYDIR.parents[1] / "logs" / "runners"

CARRIER = "eldarRanger"                 # << Calandis >> -- HERO, dans le pool spawnable
ABILITY = "WireweaveNet"                # le PASSIF porteur (TriggeredAbilityType 0x457 = 1111)
EFFECT = int(EffectType.WireweaveNet_CounterAttack)   # 0x457 = 1111
PROFILE = "Piercing"
BOARD = "MC1_67"
SEED = "777"
HP_PLAYER = "999999"                    # Calandis survit a tout (et son armure passe a 0)
HP_TARGET = "999999"                    # l'attaquant survit a l'Overwatch de l'approche


def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def rpc(sid, m, body=None, timeout=60):
    return _unwrap(R._rpc(sid, m, [body] if body is not None else [], timeout=timeout))


def _seed_rng(s):
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"])
    rng.mti = s["mti"]
    return rng


def build(tag, attackers, hp_target, board, seed):
    LOGS.mkdir(parents=True, exist_ok=True)
    state = LOGS / ("wwn_%s.json" % tag)
    state.unlink(missing_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
            "--state-file", str(state), "--board", board,
            "--p-units", CARRIER, "--a-units", ",".join(attackers),
            "--hp-player", HP_PLAYER, "--hp-target", str(hp_target),
            # une seule variable bouge : ni crit ni block ne doivent salir le per-coup
            "--crit", "0,0", "--crit-target", "0,0",
            "--block-target", "0,0", "--block-player", "0,0"]
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state.exists():
        print("BUILD KO: %s" % (p.stderr or p.stdout or "")[-800:])
        return None, None
    return int(json.loads(state.read_text())["runnerId"]), state


def _bfs(board, src):
    dist = {src: 0}
    q = deque([src])
    while q:
        x = q.popleft()
        for n in board.neighbours(x):
            if n not in dist and (n == src or board.walkable(n)):
                dist[n] = dist[x] + 1
                q.append(n)
    return dist


def _by_vis(dv, vis):
    return next((u for u in (dv.get("units") or []) if u.get("visualId") == vis and u.get("alive")),
                None)


def _unit(dv, uid):
    return next((u for u in (dv.get("units") or []) if u.get("id") == uid), None)


def _eff_row(u, etype):
    return next((e for e in ((u or {}).get("effects") or []) if e.get("effectType") == etype), None)


def _per_target(res):
    """Per-coup LIVE {target_id: [amounts]} + flag de salete (crit/block/evade rendraient le coup
    incomparable a un rejeu deterministe). Lit TOUTES les actions de la reponse."""
    out, dirty = {}, False
    for act in (res.get("actions") or []):
        for e in (act.get("events") or []):
            td = e.get("tags")
            td = json.loads(td) if isinstance(td, str) else (td or {})
            if "Amount" in td and td.get("Target_Id") is not None:
                out.setdefault(td["Target_Id"], []).append(int(td["Amount"]))
                dirty = dirty or bool(td.get("Attack_DidCrit")) or bool(td.get("Attack_DidBlock")) \
                    or bool(td.get("Attack_DidEvade"))
    return out, dirty


def _hp(st, uid):
    e = st.get_entity(uid)
    hc = e.get_component(HealthComponent) if e is not None else None
    return hc.hp if hc is not None else None


def _load(cap, board):
    return load_state(cap["dv"], cap["ob"], cap["snap"], board=board)


def _capture(sid, rid):
    return {
        "dv": rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150),
        "dv_inactive": rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True,
                                                 "includeInactive": True}, 150),
        "ob": rpc(sid, "observeBattle", {"runnerId": rid}, 90),
        "snap": rpc(sid, "combatSnapshot", {"runnerId": rid}, 120),
        "rng": rpc(sid, "dumpRng", {"runnerId": rid}, 40),
    }


def _strip_effect(st, carrier_id):
    """CONTRE-EPREUVE : retire 1111 du monde OFFLINE (instance consommee). Sans ce controle,
    << le port reproduit le live >> ne prouverait pas que le regime MORD."""
    n = 0
    for e in (st.effects.by_unit.get(carrier_id) or []):
        if e.effect_type == EFFECT:
            e.consumed = True
            n += 1
    return n


def offline_play(cap, board, caster_id, target_id, watch, strip=False, force_player=None):
    """Rejoue le MEME coup OFFLINE sur la MEME capture et le MEME flux MT. Rend les PV finaux des
    unites de `watch` + le VERDICT de presence de l'effet.
      * `strip`        : sans l'effet 1111 (contre-epreuve de discriminance) ;
      * `force_player` : ecrase `State.current_player_id` -- CONTREFACTUEL de la fenetre d'armement
        (mirror `TurnComponent.CurrentPlayerId`)."""
    st = _load(cap, board)
    stripped = _strip_effect(st, watch[0]) if strip else 0
    if force_player is not None:
        st.current_player_id = int(force_player)
    inst = next((e for e in (st.effects.by_unit.get(watch[0]) or [])
                 if e.effect_type == EFFECT and not e.consumed), None)
    before = {u: _hp(st, u) for u in watch}
    st.rng = _seed_rng(cap["rng"])
    runner = Runner(st).install_default_handlers(20)
    runner.apply(AttackUnitMessage(caster_id, target_id))
    return {"hp": {u: _hp(st, u) for u in watch},
            "hp_before": before,
            "stripped": stripped,
            "effect_present": inst is not None,
            "effect_cls": type(inst).__name__ if inst is not None else None,
            "effect_active": None if inst is None else bool(inst.active),
            "effect_active_after": None if inst is None else bool(inst.active)}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--attacker", default="orksNob")
    ap.add_argument("--attacker2", default="necroWarden")
    ap.add_argument("--neg-owner-turn", action="store_true")
    ap.add_argument("--neg-ranged", action="store_true")
    ap.add_argument("--two-attackers", action="store_true")
    ap.add_argument("--lethal", action="store_true")
    ap.add_argument("--hp-target", default=HP_TARGET)
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--seed", default=SEED)
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()

    tag = ("negowner" if a.neg_owner_turn else "negranged" if a.neg_ranged
           else "two" if a.two_attackers else "lethal" if a.lethal else "pos")
    want_dist = 2 if a.neg_ranged else 1
    mine_turn = bool(a.neg_owner_turn)          # cas negatif : on reste sur le tour de Calandis
    attackers = [a.attacker] + ([a.attacker2] if a.two_attackers else [])
    hp_target = "3000" if a.lethal else a.hp_target

    sid = R._resolve_session()
    rid, state_file = build(tag, attackers, hp_target, a.board, a.seed)
    if rid is None:
        return
    r = {"tag": tag, "rid": rid, "board": a.board, "seed": a.seed}
    try:
        bg = rpc(sid, "boardGraph", {"runnerId": rid}, 90)
        board = Board(bg["tiles"], adjacency="native_sym")

        def tile(u):
            p = u.get("pos") or {}
            return board.id_at(p.get("col"), p.get("row"))

        dv0 = rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        car = _by_vis(dv0, CARRIER)
        if car is None:
            print("porteur absent du deploiement"); return
        # magnitude ATTENDUE (garde d'attribution) : bornes RAW du profil `Piercing`
        snap0 = rpc(sid, "combatSnapshot", {"runnerId": rid}, 120)
        uc0 = next((u.get("unitConfig") or {} for u in (snap0.get("units") or [])
                    if u.get("entityId") == car["id"]), {})
        plvl = uc0.get("passiveAbilityLevel")
        mult = uc0.get("abilityVariablesMultiplier") or 100
        r["passive_level"], r["multiplier"] = plvl, mult
        r["expected_raw_min"] = ability_var(ABILITY, "minDmg", plvl, multiplier_pct=mult)
        r["expected_raw_max"] = ability_var(ABILITY, "maxDmg", plvl, multiplier_pct=mult)

        # --- 1. amener CHAQUE attaquant a la distance voulue de Calandis ----------------------
        for vis in attackers:
            for _turn in range(30):
                dv = rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)
                car, att = _by_vis(dv, CARRIER), _by_vis(dv, vis)
                if car is None or att is None:
                    print("unite manquante (%s)" % vis); return
                dist = _bfs(board, tile(car))
                if dist.get(tile(att)) == want_dist:
                    break
                if dv.get("currentPlayer") != att.get("owner"):
                    rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
                    continue
                mt = rpc(sid, "aiMovableTiles", {"runnerId": rid, "side": "all"}, 90)
                row = next((x for x in (mt.get("units") or []) if x.get("unitId") == att["id"]), None)
                reach = {board.id_at(t["col"], t["row"]): (t["col"], t["row"])
                         for t in ((row or {}).get("tiles") or [])}
                exact = [t for t in reach if dist.get(t) == want_dist]
                pool = exact or [t for t in reach if t in dist]
                if not pool:
                    rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
                    continue
                best = exact[0] if exact else min(pool, key=lambda t: dist[t])
                col, rw = reach[best]
                rpc(sid, "applyAction", {"runnerId": rid, "action": {
                    "kind": "move", "unitId": att["id"], "to": {"col": col, "row": rw}}}, 60)
                if not exact:
                    rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)

        # --- 2. positionner le TOUR -----------------------------------------------------------
        for _ in range(6):
            dv = rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)
            car = _by_vis(dv, CARRIER)
            if (dv.get("currentPlayer") == car.get("owner")) == mine_turn:
                break
            rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)

        # --- 3. l'ARMEMENT, lu sur le canal `includeInactive` ---------------------------------
        cap = _capture(sid, rid)
        car = _by_vis(cap["dv"], CARRIER)
        atts = [_by_vis(cap["dv"], v) for v in attackers]
        if car is None or any(x is None for x in atts):
            print("unite manquante a la capture"); return
        r["carrier_id"] = car["id"]
        r["attacker_ids"] = [x["id"] for x in atts]
        r["current_player"] = cap["dv"].get("currentPlayer")
        r["carrier_owner"] = car.get("owner")
        r["dist"] = [_bfs(board, tile(car)).get(tile(x)) for x in atts]
        act_row = _eff_row(_unit(cap["dv"], car["id"]), EFFECT)
        ina_row = _eff_row(_unit(cap["dv_inactive"], car["id"]), EFFECT)
        r["armed_in_active_channel"] = act_row is not None
        r["armed_flag"] = None if ina_row is None else ina_row.get("active")

        # ce que le PORT materialise sur CETTE capture (etage separe du degat)
        st_view = _load(cap, board)
        pinst = next((e for e in (st_view.effects.by_unit.get(car["id"]) or [])
                      if e.effect_type == EFFECT and not e.consumed), None)
        r["port_effect"] = {"present": pinst is not None,
                            "cls": type(pinst).__name__ if pinst is not None else None,
                            "active": None if pinst is None else bool(pinst.active)}

        # --- 4. LE COUP (live) ----------------------------------------------------------------
        watch = [car["id"]] + [x["id"] for x in atts]
        off_before = {u: _hp(_load(cap, board), u) for u in watch}
        r["hp_before"] = off_before

        a1 = atts[0]
        norm = next((x for x in (_unit(cap["dv"], a1["id"]) or {}).get("abilities") or []
                     if x.get("kind") == "normal"), None)
        if norm is None:
            print("aucune attaque normale exposee sur l'attaquant"); return
        res = rpc(sid, "applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": a1["id"], "targetId": car["id"],
            "abilityType": norm["id"]}}, 150)
        if not (isinstance(res, dict) and res.get("ok")):
            print("coup live KO: %s" % (str(res)[:300],)); return
        per, dirty = _per_target(res)
        r["live_per_target"] = per
        r["live_dirty"] = dirty
        r["live_counter_on_attacker"] = per.get(a1["id"], [])
        r["live_hits_on_carrier"] = per.get(car["id"], [])
        r["live_hp"] = {u.get("squadId"): u.get("hp") for u in (res.get("units") or [])}

        # armement APRES le coup. ATTENTION, CONFONDANT MESURE : en 1v1 l'attaque CLOT le tour
        # ennemi, et `On(0x12) & IsTurnOf(Owner) -> DeactivateEffect` fait tomber le flag AUSSI --
        # le cas `--neg-ranged` le montre (aucune riposte, flag a `false` quand meme). Le flag seul
        # ne prouve donc PAS le `& DeactivateEffect(effect)` du behaviour : il faut lire
        # `current_player_after` (tour INCHANGE = mesure propre) ou passer par `--two-attackers`.
        dvi2 = rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True,
                                         "includeInactive": True}, 150)
        row2 = _eff_row(_unit(dvi2, car["id"]), EFFECT)
        r["armed_flag_after"] = None if row2 is None else row2.get("active")
        r["current_player_after"] = dvi2.get("currentPlayer")
        r["turn_rolled_over"] = (r["current_player_after"] != r["current_player"])

        # --- 5. OFFLINE : replay-diff + contre-epreuve + contrefactuel -------------------------
        r["port"] = offline_play(cap, board, a1["id"], car["id"], watch)
        r["port_stripped"] = offline_play(cap, board, a1["id"], car["id"], watch, strip=True)
        r["port_owner_turn"] = offline_play(cap, board, a1["id"], car["id"], watch,
                                            force_player=car.get("owner"))

        # --- 6. SECOND attaquant, MEME tour ("the FIRST time") ------------------------------
        if a.two_attackers and len(atts) > 1:
            a2 = atts[1]
            dv2 = rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)
            n2 = next((x for x in (_unit(dv2, a2["id"]) or {}).get("abilities") or []
                       if x.get("kind") == "normal"), None)
            if n2 is not None:
                res2 = rpc(sid, "applyAction", {"runnerId": rid, "action": {
                    "kind": "ability", "casterId": a2["id"], "targetId": car["id"],
                    "abilityType": n2["id"]}}, 150)
                per2, _ = _per_target(res2)
                r["second_counter_on_attacker"] = per2.get(a2["id"], [])
                r["second_hits_on_carrier"] = per2.get(car["id"], [])

        # --- VERDICT ---------------------------------------------------------------------------
        live_hp = r["live_hp"]
        port_hp = r["port"]["hp"]
        match = all(port_hp.get(u) == live_hp.get(u) for u in watch)
        r["MATCH"] = match
        print(json.dumps(r, indent=1, default=str))
        print("[VERDICT %s] %s" % (tag, "MATCH" if match else "DIVERGENCE"))
    finally:
        if not a.keep:
            rpc(sid, "disposeRunner", {"runnerId": rid}, 30)
            state_file.unlink(missing_ok=True)
            print("[dispose] %s" % rid)


if __name__ == "__main__":
    main()
