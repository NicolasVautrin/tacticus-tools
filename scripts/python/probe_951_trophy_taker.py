#!/usr/bin/env python3
"""#951 -- MESURE LIVE de `TrophyTaker` (`worldExecutions` << Tarvakh >>).

Trois regimes, tous montes sur le MEME runner pour que le seul ecart soit celui qu'on mesure :

  A. TEMOIN     -- 0 unite vaincue, cible a PV PLEINS      -> aucun bonus, aucun stat-mod 1288
  B. ENTAMEE    -- 0 unite vaincue, cible SOUS `hpPct`     -> `extraDmg` + `extraCritDmg`
  C. APRES KILL -- 1 unite normale vaincue                 -> stat-mod 1288 = `extraCritChance x 1`

La geometrie et les PV sont CALCULES et ASSERTIONNES ; le probe REFUSE de conclure si un regime
n'est pas atteint. Sortie ASCII (cp1252).

Usage :
    python probe_951_trophy_taker.py --state-file <ABSOLU unique> [--seed 4321] [--board MC1_67]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import deque
from pathlib import Path

import gameconfig as GC
from engine.runner.operations.triggers.loki import trophy_taker as TTT
from engine.entities.effect_type import EffectType
from engine.entities.effects.magnitude import ability_var
from engine.entities.pathfinding.board import Board

ICI = Path(__file__).resolve().parent
CARRIER = "worldExecutions"          # Tarvakh -- HERO au pool, porteur de `TrophyTaker`
CIBLE = "necroWarden"                # cible d'OBSERVATION : beaucoup de PV, entamee au seed
VICTIME = "orksNob"                  # victime a tuer : 1 PV, unite NORMALE (ni Object ni Steppable)
EXTRA_CRIT_CHANCE = int(EffectType.TrophyTaker_ExtraCritChance)    # 0x508 = 1288
EXTRA_CRIT_DAMAGE = int(EffectType.TrophyTaker_ExtraCritDamage)    # 0x509 = 1289


_SID = None


def _rpc(nom, args, timeout=90):
    """Transport RPC PARTAGE avec la suite live (`rl_collect_batch`), jamais une URL recopiee :
    l'endpoint et l'enveloppe `{result: ...}` sont son affaire, pas celle de ce probe."""
    global _SID
    import rl_collect_batch as R
    if _SID is None:
        _SID = R._resolve_session()
    r = R._rpc(_SID, nom, [args] if args is not None else [], timeout=timeout)
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def _bfs(board, src):
    dist, q = {src: 0}, deque([src])
    while q:
        x = q.popleft()
        for n in board.neighbours(x):
            if n not in dist and (n == src or board.walkable(n)):
                dist[n] = dist[x] + 1
                q.append(n)
    return dist


def _alive(dv, vis):
    return next((u for u in (dv.get("units") or [])
                 if u.get("visualId") == vis and u.get("alive")), None)


def _eff(u, etype):
    return next((e for e in ((u or {}).get("effects") or []) if e.get("effectType") == etype), None)


def _tile(board, u):
    p = u.get("pos") or {}
    return board.id_at(p.get("col"), p.get("row"))


def _drive(rid, board, mover_vis, anchor_vis, want, side, tours=30):
    """Amene `mover_vis` a EXACTEMENT `want` hexes d'`anchor_vis`. Rend la distance atteinte."""
    for _ in range(tours):
        dv = _rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True})
        mv, an = _alive(dv, mover_vis), _alive(dv, anchor_vis)
        if mv is None or an is None:
            return None
        dist = _bfs(board, _tile(board, an))
        if dist.get(_tile(board, mv)) == want:
            return want
        if dv.get("currentPlayer") != mv.get("owner"):
            _rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
            continue
        mt = _rpc("aiMovableTiles", {"runnerId": rid, "side": side}, 60)
        row = next((x for x in (mt.get("units") or []) if x.get("unitId") == mv["id"]), None)
        reach = {board.id_at(t["col"], t["row"]): (t["col"], t["row"])
                 for t in ((row or {}).get("tiles") or [])}
        exact = [t for t in reach if dist.get(t) == want]
        pool = exact or [t for t in reach if t in dist]
        if not pool:
            _rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
            continue
        best = exact[0] if exact else min(pool, key=lambda t: abs(dist[t] - want))
        col, r = reach[best]
        _rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": mv["id"], "to": {"col": col, "row": r}}}, 40)
        if not exact:
            _rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
    dv = _rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True})
    mv, an = _alive(dv, mover_vis), _alive(dv, anchor_vis)
    if mv is None or an is None:
        return None
    return _bfs(board, _tile(board, an)).get(_tile(board, mv))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True)
    ap.add_argument("--seed", default="4321")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--pv-cible", type=int, default=200000)
    ap.add_argument("--pv-restants", type=int, default=20000)     # 10 % -> SOUS hpPct = 50
    ap.add_argument("--sans-kill", action="store_true",
                    help="saute le REGIME C : le porteur n'a vaincu PERSONNE quand le REGIME B est "
                         "mesure. C'est la CONTRE-EPREUVE de l'ecart de base -- elle isole les "
                         "effets du porteur dont la magnitude depend du COMPTEUR de victimes "
                         "(`BlessingsOfKhorne_ModifiersEffect$$GetMultiplierBasedOnDefeatedInMelee`), "
                         "que la capture ne publie PAS.")
    a = ap.parse_args()

    cfg = GC.ability("TrophyTaker")
    hp_pct = int(cfg["constants"]["hpPct"])
    print("[951] hpPct = %d ; variables rarity-scalees = %s"
          % (hp_pct, sorted(cfg["variablesAffectedByRarityBonus"])))

    cmd = [sys.executable, str(ICI / "rl_duel.py"), "build", "--seed", a.seed,
           "--board", a.board, "--state-file", a.state_file, "--roster", "1",
           "--p-units", CARRIER, "--a-units", "%s,%s" % (CIBLE, VICTIME),
           "--hp-player", "999999", "--crit", "0,0", "--crit-target", "0,0",
           "--block-target", "0,0", "--block-player", "0,0",
           "--unit-stat", "%s:Health=%d,RemainingHealth=%d" % (CIBLE, a.pv_cible, a.pv_restants),
           "--unit-stat", "%s:Health=1,RemainingHealth=1" % VICTIME]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if p.returncode != 0:
        print("[951] build KO rc=%d" % p.returncode)
        print((p.stdout or "")[-2000:])
        print((p.stderr or "")[-2000:])
        return 2
    etat = json.loads(Path(a.state_file).read_text(encoding="utf-8"))
    rid = etat.get("runnerId") or etat.get("rid")
    print("[951] runner %s sur %s" % (rid, a.board))

    bg = _rpc("boardGraph", {"runnerId": rid}, 60)
    board = Board(bg["tiles"], adjacency="native_sym")

    dv = _rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True})
    car = _alive(dv, CARRIER)
    if car is None:
        print("[951] porteur ABSENT -- AUCUNE mesure")
        return 3
    row = next((u for u in (dv.get("units") or []) if u.get("id") == car["id"]), None)
    print("[951] effets du porteur au seed : %s"
          % sorted({e.get("effectType") for e in (row.get("effects") or [])}))
    pose = _eff(row, EXTRA_CRIT_DAMAGE)
    print("[951] effet 1289 (pose a l'INIT) present au seed : %s" % (pose is not None))

    for vis in (CIBLE, VICTIME):
        u = _alive(dv, vis)
        if u is None:
            print("[951] %s ABSENTE" % vis)
            return 3
        pct = None
        if u.get("hp") is not None and u.get("maxHp"):
            pct = round(100.0 * float(u["hp"]) / float(u["maxHp"]), 1)
        print("[951] %s : hp=%s / max=%s (%s %%)" % (vis, u.get("hp"), u.get("maxHp"), pct))

    # REGIME C -- amener le porteur au contact de la VICTIME et la tuer
    got = 1 if a.sans_kill else _drive(rid, board, CARRIER, VICTIME, 1, "friendly")
    if a.sans_kill:
        print("[951] --sans-kill : REGIME C SAUTE, le porteur n'aura vaincu personne")
    if got != 1:
        print("[951] pilotage KO : porteur/victime = %s != 1 -- AUCUNE mesure" % got)
        return 4
    dv = _rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True})
    car, vic = _alive(dv, CARRIER), _alive(dv, VICTIME)
    if car is None or vic is None:
        print("[951] unite manquante apres pilotage")
        return 4
    if dv.get("currentPlayer") != car.get("owner"):
        _rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
        dv = _rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True})
        car, vic = _alive(dv, CARRIER), _alive(dv, VICTIME)
    norm = next((x for x in (car.get("abilities") or []) if x.get("kind") == "normal"), None)
    if norm is None:
        print("[951] pas d'attaque normale sur le porteur")
        return 4
    # CAPTURE AVANT LE KILL -- le seul point ou le port peut REJOUER le trigger : apres, le
    # compteur natif a avance et la capture ne le publie pas (residu #951-r3).
    port_mod = None
    if not a.sans_kill:
        from engine.runner.snapshot import load_state as _ls
        from engine.runner.messages import AttackUnitMessage as _AUM
        from engine.runner.prng import IntBasedMersenneTwister as _MT
        from engine.runner.runner import Runner as _R
        _dv = _rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True})
        _ob = _rpc("observeBattle", {"runnerId": rid}, 60)
        _sn = _rpc("combatSnapshot", {"runnerId": rid}, 60)
        _st = _ls(_dv, _ob, _sn, board=board)
        _s = _rpc("dumpRng", {"runnerId": rid}, 30)
        _rng = _MT()
        _rng.mt = list(_s["mt"])
        _rng.mti = _s["mti"]
        _st.rng = _rng
        _run = _R(_st).install_default_handlers(20)
        # Le trigger est-il seulement COLLECTE sur ce porteur ? Un `[]` ici ne dit pas la meme
        # chose qu'un `matches` faux : le premier accuse le CABLAGE, le second la LECTURE.
        from engine.runner.operations.triggers.dispatch import core as _core
        _tr = [t for t in _core.collect_triggered_abilities(_st)
               if getattr(t, "owner_id", None) == car["id"]]
        print("[951] triggers COLLECTES sur le porteur : %s"
              % sorted({type(t).__name__ for t in _tr}))
        _sc = _st.get_entity(car["id"]).get_component(
            __import__("engine.runner.components", fromlist=["StatsComponent"]).StatsComponent)
        print("[951] passives MESUREES du porteur : %s"
              % (getattr(_sc.ctx, "passive_abilities", None),))
        _run.apply(_AUM(car["id"], vic["id"]))
        print("[951] effets du porteur APRES replay : %s"
              % sorted({e.effect_type for e in (_st.effects.by_unit.get(car["id"]) or [])}))
        # DECOMPOSITION PAR ETAGE du multiplicateur : `UnitsDefeatedBy` -> `NormalUnits` -> `Count`.
        # Un `0` final ne dit pas LEQUEL des trois etages l'a produit.
        from engine.runner.abilities.behaviours.context import entities_from_state as _efs
        from engine.entities.selectors.tiles import Caster as _C
        from engine.entities.selectors.units import NormalUnits as _NU, UnitsDefeatedBy as _UDB
        from engine.entities.unit_selection_type import UnitSelectionType as _UST
        _ent = _efs(_st, car["id"], vic["id"], actor_id=car["id"])
        _e1 = _UDB(_C()).evaluate(_ent)
        _e2 = _NU(_UDB(_C()), int(_UST.Any)).evaluate(_ent)
        print("[951] etage UnitsDefeatedBy -> %s ; + NormalUnits -> %s"
              % ([u.get("id") for u in _e1], [u.get("id") for u in _e2]))
        print("[951] arbre du multiplicateur -> %s"
              % TTT.trophy_taker_crit_chance_multiplier_tree().evaluate(_ent))
        port_mod = [(e.effect_type, getattr(e, "stat_type", None), getattr(e, "value", None))
                    for e in (_st.effects.by_unit.get(car["id"]) or [])
                    if e.effect_type == EXTRA_CRIT_CHANCE]
        from engine.runner.components import UnitComponent as _UC
        _uc = _st.get_entity(car["id"]).get_component(_UC)
        print("[951] REPLAY OFFLINE du kill : compteur du port = %d ; stat-mod 1288 pose = %s"
              % (len(_uc.defeated_units), port_mod))
    res = {"ok": None} if a.sans_kill else _rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": car["id"], "targetId": vic["id"],
        "abilityType": norm["id"]}}, 90)
    print("[951] kill : ok=%s" % (res.get("ok")))

    dv2 = _rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True,
                                "includeInactive": True})
    row2 = next((u for u in (dv2.get("units") or []) if u.get("id") == car["id"]), None)
    mod = _eff(row2, EXTRA_CRIT_CHANCE)
    vic2 = next((u for u in (dv2.get("units") or []) if u.get("visualId") == VICTIME), None)
    print("[951] victime morte : %s" % (vic2 is not None and not vic2.get("alive")))
    print("[951] stat-mod 1288 sur le porteur APRES le kill : %s" % json.dumps(mod))
    snap = _rpc("combatSnapshot", {"runnerId": rid}, 60)
    uc = next((u.get("unitConfig") or {} for u in (snap.get("units") or [])
               if u.get("entityId") == car["id"]), {})
    lvl = uc.get("passiveAbilityLevel")
    mult = uc.get("abilityVariablesMultiplier") or 100
    attendu = ability_var("TrophyTaker", "extraCritChance", lvl, multiplier_pct=mult)
    print("[951] niveau passif = %s ; multiplicateur = %s ; extraCritChance attendu = %s"
          % (lvl, mult, attendu))
    sms = _rpc("statModSources", {"runnerId": rid, "unitId": car["id"]}, 60)
    cc = ((next((u for u in (sms.get("units") or []) if u.get("entityId") == car["id"]), {})
           .get("mods") or {}).get("critChance") or {})
    print("[951] critChance NATIF par source : total=%s bySource=%s"
          % (cc.get("total"), cc.get("bySource")))

    # ---------------------------------------------------------------- REGIME B : cible SOUS hpPct
    # Le porteur va au contact de la cible d'observation, puis on rejoue LE MEME coup live et
    # OFFLINE sur la MEME graine RNG -- le seul canal ou le bonus `extraDmg` est OBSERVABLE.
    got = _drive(rid, board, CARRIER, CIBLE, 1, "friendly")
    if got != 1:
        print("[951] pilotage KO : porteur/cible = %s != 1 -- REGIME B NON MESURE" % got)
        return 5
    for _ in range(4):
        dv = _rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True})
        car = _alive(dv, CARRIER)
        if car is not None and dv.get("currentPlayer") == car.get("owner"):
            break
        _rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
    dv = _rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True})
    car, cib = _alive(dv, CARRIER), _alive(dv, CIBLE)
    if car is None or cib is None:
        print("[951] unite manquante avant le REGIME B")
        return 5
    d = _bfs(board, _tile(board, car)).get(_tile(board, cib))
    if d != 1:
        print("[951] geometrie: porteur/cible = %s != 1 au moment de la mesure" % d)
        return 5

    ob = _rpc("observeBattle", {"runnerId": rid}, 60)
    snap = _rpc("combatSnapshot", {"runnerId": rid}, 60)
    from engine.runner.snapshot import load_state
    from engine.runner.components import HealthComponent
    from engine.runner.messages import AttackUnitMessage
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.runner import Runner
    state = load_state(dv, ob, snap, board=board)
    hc = state.get_entity(cib["id"]).get_component(HealthComponent)
    pct = None if not (hc and hc.hp is not None and hc.hp_max) else \
        round(100.0 * hc.hp / hc.hp_max, 1)
    print("[951] REGIME B : cible hp=%s/%s (%s %%) ; seuil hpPct=%d -> gate %s"
          % (getattr(hc, "hp", None), getattr(hc, "hp_max", None), pct, hp_pct,
             "OUVERT" if (pct is not None and pct < hp_pct) else "FERME"))
    if pct is None:
        print("[951] PV de la cible NON MESURES -- REGIME B impossible")
        return 5
    if pct >= hp_pct:
        # Regime TEMOIN volontaire (`--pv-restants` haut) : le gate est FERME des DEUX cotes, donc
        # tout ecart natif/port qui subsiste ici est PREEXISTANT a ce passif. C'est la seule facon
        # de savoir si un ecart mesure en regime OUVERT vient de TrophyTaker ou d'ailleurs.
        print("[951] REGIME TEMOIN : gate FERME des deux cotes (pct %s >= %d)" % (pct, hp_pct))
    # DIAGNOSTIC PAR ETAGE -- ou le bonus se perd-il, si jamais il se perd ?
    inst = next((e for e in (state.effects.by_unit.get(car["id"]) or [])
                 if e.effect_type == EXTRA_CRIT_DAMAGE), None)
    print("[951] instance 1289 cote PORT : classe=%s ability_level=%s mult=%s"
          % (type(inst).__name__ if inst is not None else None,
             getattr(inst, "ability_level", None),
             getattr(inst, "ability_variables_multiplier", None)))
    if inst is not None:
        ctx_reel = {"tgt_hp": hc.hp, "tgt_hp_max": hc.hp_max}
        print("[951] bonus DEGAT du port avec (tgt_hp, tgt_hp_max) = %s"
              % (inst.create_effect_damage_bonus_for_attack(att_ctx=ctx_reel),))
    s0 = _rpc("dumpRng", {"runnerId": rid}, 30)
    rng = IntBasedMersenneTwister()
    rng.mt = list(s0["mt"])
    rng.mti = s0["mti"]
    state.rng = rng
    runner = Runner(state).install_default_handlers(20)
    off_defeated = len(getattr(
        state.get_entity(car["id"]).get_component(
            __import__("engine.runner.components", fromlist=["UnitComponent"]).UnitComponent),
        "defeated_units", []))
    print("[951] compteur OFFLINE d'unites vaincues au chargement : %d "
          "(le seed ne le publie PAS -- residu attendu)" % off_defeated)
    hp_avant = hc.hp
    res2 = _rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": car["id"], "targetId": cib["id"],
        "abilityType": norm["id"]}}, 90)
    if not (isinstance(res2, dict) and res2.get("ok")):
        print("[951] attaque live KO : %s" % str(res2)[:300])
        return 5
    # Les PV NATIFS se relisent dans `observeBattle` (indexe par entityId) -- PAS dans
    # `res.units[].squadId`, qui est un id de SQUAD : les confondre rend les PV d'une AUTRE unite.
    # Le DEGAT se lit dans les EVENTS de l'action, pas dans les PV d'apres coup : `applyAction`
    # cloture le tour du porteur, le tour adverse s'ouvre, et un `necroWarden` (`LivingMetal`)
    # REGENERE -- mesure faite, ses PV MONTENT de 80000 a 93290 apres l'attaque. Comparer des PV
    # d'apres coup melangerait donc le degat et la regeneration, et le verdict serait ininterpretable.
    a0 = (res2.get("actions") or [{}])[0]
    coups = []
    for e in (a0.get("events") or []):
        td = e.get("tags")
        if not td:
            continue
        td = json.loads(td) if isinstance(td, str) else td
        if td.get("Target_Id") == cib["id"] and "Amount" in td:
            coups.append(int(td["Amount"]))
    # INSTRUMENTATION : le canal DEGAT du port passe-t-il l'instance 1289 ET les cles du gate ?
    # C'est le seul moyen de savoir si un ecart vient du GATE, de la MAGNITUDE, ou du CABLAGE.
    import engine.entities.effects as EFX
    vu = {"appels": 0, "cles": None, "classes": None, "bonus": None}
    vrai_boucle = EFX._attacker_effect_bonuses

    def _espion(effects, *a, **k):
        vu["appels"] += 1
        ctx = k.get("att_ctx")
        if vu["cles"] is None:
            vu["cles"] = sorted((ctx or {}).keys())
            vu["classes"] = sorted({type(e).__name__ for e in EFX._as_effects(effects)})
        out = vrai_boucle(effects, *a, **k)
        if vu["bonus"] is None:
            vu["bonus"] = [(b.kind, b.value) for b in out]
        return out

    EFX._attacker_effect_bonuses = _espion
    try:
        runner.apply(AttackUnitMessage(car["id"], cib["id"]))
    finally:
        EFX._attacker_effect_bonuses = vrai_boucle
    print("[951] canal DEGAT du port : appels=%d classes=%s" % (vu["appels"], vu["classes"]))
    print("[951] canal DEGAT du port : cles att_ctx = %s" % (vu["cles"],))
    print("[951] canal DEGAT du port : bonus rendus = %s" % (vu["bonus"],))
    hc2 = state.get_entity(cib["id"]).get_component(HealthComponent)
    port = (hp_avant - hc2.hp) if hc2.hp is not None else None
    print("[951] REGIME B : coups NATIFS = %s (total %s)" % (coups, sum(coups)))
    print("[951] REGIME B : degat PORT = %s ; ECART = %s"
          % (port, (sum(coups) - port) if port is not None else "n/a"))
    print("[951] state-file : %s" % a.state_file)
    return 0


if __name__ == "__main__":
    sys.exit(main())
