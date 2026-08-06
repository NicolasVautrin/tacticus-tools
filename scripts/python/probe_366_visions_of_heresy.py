"""case-366-r1 -- MONTAGE LIVE des deux `EffectType` de percage de `VisionsOfHeresy`
(`1345 ExtraPierceMelee` / `1346 ExtraPierceRanged`, porteur `bloodDeathCompany` <<Lucien>>).

CRITERE BINAIRE : << le port compte-t-il le percage supplementaire comme le natif, sur les DEUX
axes (melee ET ranged) ? >> -- mesure dans un regime ou le percage MORD, c.-a-d. une cible dont
l'armure fait gagner la branche PERCAGE du plancher natif
`idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Damage$$GetDamageWithPiercing`
(`max(0, d - armure, d x pierce%)`). Levier : `--armor-target` (cf. `_pierce_floor_regime.py`).
A armure basse, +20 points de percage ne changent RIEN au degat : un accord obtenu la ne prouve
rien, et c'est exactement ce que ce montage refuse de faire.

TROIS ETAGES MESURES SEPAREMENT (jamais un scalaire unique) :

  E1 -- POSE. A pleins PV les deux effets sont ABSENTS de `decisionView.effects` (canal ACTIF-ONLY)
        et PRESENTS sous `includeInactive: true`, avec `active: false`. C'est la preuve DIRECTE
        qu'ils sont poses a l'INIT de l'ability et eteints par leur `CreateActiveCondition`.
  E2 -- STAT. `combatSnapshot.stats.extraPierce{Melee,Ranged}` du natif : 0 au-dessus du seuil,
        `extraPierceRatio` en dessous. C'est l'etage DISCRIMINANT du port : offline, on part de la
        capture PLEINS PV (ou le canal live ne livre RIEN), on descend les PV, on joue le driver
        `refresh_stat_modifier_effects`, et `ctx.extra_pierce_*` doit rejoindre la valeur native.
  E3 -- DEGAT. Le MEME coup, joue LIVE et rejoue OFFLINE, dans les DEUX regimes (au-dessus puis
        en dessous du seuil). Le regime est DISCRIMINANT par construction (les per-coup des deux
        regimes different) et le port doit reproduire les DEUX.

Le montage pilote les DEUX camps (`applyAction` ne verifie pas la propriete du caster) : l'ennemi
descend Lucien sous le seuil, ce qui est le SEUL moyen d'observer la bascule. `--unit-stat` met
l'armure de Lucien a 0 pour que cette descente prenne quelques coups et non quarante.

Usage :
    python probe_366_visions_of_heresy.py --axis melee  [--seed 31337] [--board MC1_67]
    python probe_366_visions_of_heresy.py --axis ranged [--seed 4242]  [--board C4_09]

Consommateur pytest : `tests/engine/runner/test_visions_of_heresy_pierce_live.py`.
ASCII only (cp1252).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

_PYDIR = Path(__file__).resolve().parent
_ROOT = _PYDIR.parent.parent

CARRIER = "bloodDeathCompany"          # <<Lucien>>, seul porteur du passif VisionsOfHeresy (1264)
FOE = "templSwordBrother"              # cible melee ; encaisse (armure forcee) et cogne Lucien
ABILITY = "VisionsOfHeresy"
PIERCE_MELEE = 1345                    # 0x541
PIERCE_RANGED = 1346                   # 0x542
ARMOR = 6000                           # branche PERCAGE dominante (levier R6)
BOARD = "MC1_67"
SEED = "31337"
MAX_CHIP = 40                          # coups max pour descendre Lucien sous le seuil


# --------------------------------------------------------------------------- build
def build_args(axis: str, board: str, armor: int) -> list:
    """Arguments `rl_duel build`. Une seule variable bouge (le percage) :
      * `--crit 0,0` / `--crit-target 0,0` / `--block-target 0,0` / `--block-player 0,0` : aucun
        aleas crit/block, sur les QUATRE faces. Les deux dernieres ont ete AJOUTEES par #419-r6 :
        `--crit`/`--block-player` n'epinglent que les p-units et `--crit-target`/`--block-target`
        que les a-units, or ce montage PILONNE Lucien (p-unit) avec la cible (a-unit) pour le
        descendre sous le seuil -- les deux camps frappent. Tant que le canal crit/block etait
        globalement muet, poser deux faces sur quatre suffisait PAR ACCIDENT ; depuis que le
        defaut equipe (#419-r6), le bras RANGED tombait en rouge sur ce seul manque ;
      * `--hp-target 300000` PUIS `--armor-target N` : dans `rl_duel.py` le bloc `--armor-target`
        s'execute APRES celui de `--hp-target` (qui met l'armure a 0), donc l'armure CHOISIE
        SURVIT -- c'est elle qui arme la branche PERCAGE. Les PV enormes evitent l'ecretage letal
        de la cible entre les deux mesures ;
      * `--hp-player 20000` : Lucien encaisse PLEIN (armure mise a 0) et a assez de PV pour que la
        descente sous 50 % prenne quelques coups sans le tuer. Levier de MONTAGE, pas de mesure :
        le percage mesure est celui de LUCIEN CONTRE la cible, son armure a lui n'y entre pas.
    """
    return ["--p-units", CARRIER, "--a-units", FOE,
            "--crit", "0,0", "--crit-target", "0,0",
            "--block-target", "0,0", "--block-player", "0,0",
            "--hp-target", "300000", "--hp-player", "20000",
            "--armor-target", str(armor),
            "--board", board]


def _build_subprocess(seed: str, axis: str, board: str, armor: int) -> int:
    state = _ROOT / "logs" / ("_probe366r1-%s-%d.json" % (axis, os.getpid()))
    state.parent.mkdir(parents=True, exist_ok=True)
    state.unlink(missing_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
            "--state-file", str(state), *build_args(axis, board, armor)]
    p = subprocess.run(argv, cwd=str(_PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state.exists():
        raise RuntimeError("build runner KO (rl_duel): " + ((p.stderr or p.stdout or "")[-600:]))
    return int(json.loads(state.read_text())["runnerId"])


# --------------------------------------------------------------------------- lecture live
def _unit(dec, uid):
    return next((u for u in (dec.get("units") or []) if u.get("id") == uid), None)


def _by_vis(dec, vis):
    return next((u for u in (dec.get("units") or []) if u.get("visualId") == vis and u.get("alive")),
                None)


def _eff(u, etype):
    return next((e for e in ((u or {}).get("effects") or []) if e.get("effectType") == etype), None)


def _stats(snap, uid):
    for u in (snap.get("units") or []):
        if u.get("entityId") == uid:
            return u.get("stats") or {}
    return {}


def live_amounts(res, target_id):
    """Per-coup LIVE attribues a `target_id`, dans l'ordre des events + flag de salete
    (crit/block/evade : le coup ne serait plus une mesure isolee du percage)."""
    out, dirty = [], False
    for act in (res.get("actions") or []):
        for e in (act.get("events") or []):
            td = e.get("tags")
            td = json.loads(td) if isinstance(td, str) else (td or {})
            if td.get("Target_Id") == target_id and "Amount" in td:
                out.append(int(td.get("Amount")))
                dirty = dirty or bool(td.get("Attack_DidCrit")) or bool(td.get("Attack_DidBlock")) \
                    or bool(td.get("Attack_DidEvade"))
    return out, dirty


# --------------------------------------------------------------------------- pilotage
def _endturn(rpc, rid):
    return rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"},
                               "captureEvents": False}, 90)


def _movable(rpc, rid, uid):
    mov = rpc("aiMovableTiles", {"runnerId": rid, "side": "all"}, 90)
    for m in (mov.get("units") or []):
        if m.get("unitId") == uid:
            return [(t["col"], t["row"]) for t in (m.get("tiles") or [])]
    return []


def _place_at_distance(rpc, rid, board, mover_vis, anchor_vis, want, tries=25):
    """DEPLACE `mover_vis` jusqu'a la distance hex `want` d'`anchor_vis` (on ne SUBIT jamais la
    geometrie de spawn -- on la fabrique). Rend la distance atteinte, ou None."""
    import hexgeo
    for _ in range(tries):
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        mv, an = _by_vis(dv, mover_vis), _by_vis(dv, anchor_vis)
        if mv is None or an is None:
            return None
        mpos = (mv["pos"]["col"], mv["pos"]["row"])
        apos = (an["pos"]["col"], an["pos"]["row"])
        if hexgeo.distance(mpos, apos) == want:
            return want
        if dv.get("currentPlayer") != mv.get("owner"):
            _endturn(rpc, rid)
            continue
        tiles = _movable(rpc, rid, mv["id"])
        if not tiles:
            _endturn(rpc, rid)
            continue
        best = min(tiles, key=lambda t: (abs(hexgeo.distance(t, apos) - want),
                                         hexgeo.distance(t, apos)))
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": mv["id"], "to": {"col": best[0], "row": best[1]}},
            "captureEvents": False}, 90)
        if hexgeo.distance(best, apos) == want:
            return want
        _endturn(rpc, rid)
    return None


def _hp_pct(dec, uid, hp_max):
    u = _unit(dec, uid)
    return None if (u is None or not hp_max) else 100.0 * float(u.get("hp") or 0) / float(hp_max)


def _chip_below(rpc, rid, foe_id, carrier_id, hp_max, threshold_pct):
    """Fait DESCENDRE Lucien sous `threshold_pct` % PV en le faisant frapper par l'ennemi
    (les deux camps sont pilotables : `applyAction` ne verifie pas la propriete du caster).

    L'ennemi est MELEE : on le RAMENE au contact a chaque tour au lieu de subir la geometrie --
    sur l'axe RANGED, Lucien est a distance 2 et l'ennemi ne pourrait pas frapper sans ce pas.
    Rend le % atteint, ou None (Lucien mort / pilonnage impossible)."""
    import hexgeo
    for _ in range(MAX_CHIP):
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        car = _unit(dv, carrier_id)
        if car is None or not car.get("alive"):
            return None
        pct = 100.0 * float(car.get("hp") or 0) / float(hp_max)
        if pct <= threshold_pct:
            return pct
        foe = _unit(dv, foe_id)
        if foe is None or not foe.get("alive"):
            return None
        if dv.get("currentPlayer") != foe.get("owner"):
            _endturn(rpc, rid)
            continue
        cpos = (car["pos"]["col"], car["pos"]["row"])
        fpos = (foe["pos"]["col"], foe["pos"]["row"])
        if hexgeo.distance(fpos, cpos) != 1:
            tiles = _movable(rpc, rid, foe_id)
            adj = [t for t in tiles if hexgeo.distance(t, cpos) == 1]
            if not adj:
                _endturn(rpc, rid)
                continue
            rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": foe_id, "to": {"col": adj[0][0], "row": adj[0][1]}},
                "captureEvents": False}, 90)
        norm = next((a for a in (foe.get("abilities") or []) if a.get("kind") == "normal"), None)
        if norm is None:
            return None
        r = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": foe_id, "targetId": carrier_id,
            "abilityType": norm["id"]}, "captureEvents": False}, 150)
        if not (isinstance(r, dict) and r.get("ok")):
            return None
        _endturn(rpc, rid)
    return None


# --------------------------------------------------------------------------- offline
def _capture(rpc, rid):
    return {
        "dv": rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150),
        "dv_inactive": rpc("decisionView", {"runnerId": rid, "allAbilities": True,
                                            "includeInactive": True}, 150),
        "ob": rpc("observeBattle", {"runnerId": rid}, 90),
        "snap": rpc("combatSnapshot", {"runnerId": rid}, 120),
        "rng": rpc("dumpRng", {"runnerId": rid}, 40),
    }


def _load(cap, board):
    from engine.runner.snapshot import load_state
    return load_state(cap["dv"], cap["ob"], cap["snap"], board=board)


def offline_pierce(cap, board, carrier_id, hp_override=None):
    """`(extra_pierce, extra_pierce_melee, extra_pierce_ranged, effets)` du PORT sur la capture,
    apres `refresh_stat_modifier_effects` (mirror `RefreshEffectsOperation`). `hp_override` = PV
    imposes AVANT le refresh -> c'est la BASCULE offline de la `CreateActiveCondition`."""
    from engine.runner.components import StatsComponent, HealthComponent
    from engine.runner.operations.refresh_effects import refresh_stat_modifier_effects
    st = _load(cap, board)
    ent = st.get_entity(carrier_id)
    hc = ent.get_component(HealthComponent)
    if hp_override is not None:
        hc.hp = int(hp_override)
    refresh_stat_modifier_effects(st, carrier_id)
    ctx = ent.get_component(StatsComponent).ctx
    effs = [(e.name, bool(e.is_active({"hp": hc.hp, "max_hp": hc.hp_max})), type(e).__name__)
            for e in (st.effects.by_unit.get(carrier_id) or [])
            if e.effect_type in (PIERCE_MELEE, PIERCE_RANGED)]
    return (ctx.extra_pierce, ctx.extra_pierce_melee, ctx.extra_pierce_ranged, effs,
            (hc.hp, hc.hp_max))


def _strip_voh(st, carrier_id):
    """CONTRE-EPREUVE : retire du monde offline les deux effets de percage de VisionsOfHeresy
    (contribution stat REVERTEE par leur propre cle, puis instances consommees pour que le driver
    ne les re-applique pas). Sert a montrer que le regime est DISCRIMINANT -- sans ce controle,
    << le port reproduit le live >> ne prouve pas que le percage y change quoi que ce soit."""
    from engine.runner.components import StatsComponent
    from engine.entities.effects import effect_stat_mod_key
    ent = st.get_entity(carrier_id)
    ctx = ent.get_component(StatsComponent).ctx
    for e in (st.effects.by_unit.get(carrier_id) or []):
        if e.effect_type in (PIERCE_MELEE, PIERCE_RANGED):
            key = effect_stat_mod_key(e)
            for stt in (e.reverted_stats() or []):
                if key is not None:
                    ctx.stats.revert_stat(int(stt), key)
            e.consumed = True


def offline_pierce_ratio(cap, board, carrier_id, foe_id, axis, hp_override=None):
    """`select_weapon_pierce` du PORT (foyer PARTAGE prediction+combat, mirror
    `GetAttackPiercingDamageRatio`) sur la capture -> `(pierce, is_ranged, hits, profil)`.
    C'est l'etage NUMERIQUE isole : il ne depend d'aucun tirage."""
    from engine.runner.components import StatsComponent, HealthComponent, PositionComponent
    from engine.runner.operations.refresh_effects import refresh_stat_modifier_effects
    from engine.services.battle_query import select_weapon_pierce
    import hexgeo
    st = _load(cap, board)
    ent = st.get_entity(carrier_id)
    if hp_override is not None:
        ent.get_component(HealthComponent).hp = int(hp_override)
    refresh_stat_modifier_effects(st, carrier_id)
    ctx = ent.get_component(StatsComponent).ctx
    p1 = ent.get_component(PositionComponent)
    p2 = st.get_entity(foe_id).get_component(PositionComponent)
    d = hexgeo.distance((p1.col, p1.row), (p2.col, p2.row))
    return select_weapon_pierce(ctx, d == 1, dist=d)


def offline_hits(cap, board, caster_id, target_id, ability_id, moved, strip_voh=False):
    """Rejoue le MEME coup OFFLINE sur la MEME capture et le MEME flux MT -> per-coup du port.
    `strip_voh` = CONTRE-EPREUVE sans les deux effets de percage (cf. `_strip_voh`)."""
    from engine.runner.runner import Runner
    from engine.runner.messages import AttackUnitMessage, ActiveAbilityMessage
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.components import set_moved_flag
    st = _load(cap, board)
    if strip_voh:
        _strip_voh(st, caster_id)
    if moved:
        set_moved_flag(st, caster_id)
    rng = IntBasedMersenneTwister()
    rng.mt = list(cap["rng"]["mt"])
    rng.mti = cap["rng"]["mti"]
    st.rng = rng
    runner = Runner(st).install_default_handlers(20)
    if ability_id is None:
        runner.apply(AttackUnitMessage(caster_id, target_id))
    else:
        runner.apply(ActiveAbilityMessage(caster_id=caster_id, target_id=target_id,
                                          ability_type=ability_id))
    last = getattr(getattr(runner, "damage_handler", None), "last", None)
    return list((last or {}).get("per_hit") or [])


def _ensure_turn(rpc, rid, owner, tries=6):
    """Fait tourner les fins de tour jusqu'a ce que `owner` soit le joueur courant. La CAPTURE
    doit etre prise dans le MEME etat de tour que le coup qu'on va jouer -- sinon le rejeu offline
    part d'un etat qui n'est plus celui du coup."""
    for _ in range(tries):
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        if dv.get("currentPlayer") == owner:
            return dv
        _endturn(rpc, rid)
    return None


def _live_attack(rpc, rid, caster_id, target_id, tries=4):
    """Attaque NORMALE live du caster sur la cible -> `(per_coup, dirty, ability_id, why)`.
    `why` non nul = le coup n'a PAS eu lieu (on RAPPORTE la raison ; un montage qui n'atteint pas
    son regime doit REFUSER, jamais rendre une mesure degradee)."""
    why = "aucune tentative"
    for _ in range(tries):
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        cst = _unit(dv, caster_id)
        if cst is None or not cst.get("alive"):
            return None, False, None, "caster absent ou mort"
        if dv.get("currentPlayer") != cst.get("owner"):
            _endturn(rpc, rid)
            why = "tour adverse"
            continue
        norm = next((a for a in (cst.get("abilities") or []) if a.get("kind") == "normal"), None)
        if norm is None:
            return None, False, None, "aucune attaque normale exposee"
        res = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": caster_id, "targetId": target_id,
            "abilityType": norm["id"]}}, 150)
        if not (isinstance(res, dict) and res.get("ok")):
            why = "applyAction KO: %s" % (str(res)[:200],)
            _endturn(rpc, rid)
            continue
        hits, dirty = live_amounts(res, target_id)
        if not hits:
            return None, False, norm["id"], "coup joue mais aucun degat attribue a la cible"
        return hits, dirty, norm["id"], None
    return None, False, None, why


# --------------------------------------------------------------------------- montage
def run(rpc, axis: str = "melee", seed: str = SEED, board_id: str = BOARD,
        armor: int = ARMOR, keep: bool = False) -> dict:
    r = {"axis": axis, "seed": seed, "board": board_id, "armor": armor, "rid": None}
    try:
        _run(rpc, r, axis, seed, board_id, armor)
    except Exception as exc:                              # montage KO -> ERREUR, jamais un vert
        r["error"] = "%s: %s" % (type(exc).__name__, exc)
    finally:
        if not keep and r.get("rid") is not None:
            try:
                rpc("disposeRunner", {"runnerId": r["rid"]}, 40)
            except Exception:                             # nettoyage best-effort
                pass
    return r


def _run(rpc, r: dict, axis: str, seed: str, board_id: str, armor: int) -> None:
    import gameconfig as GC
    from engine.entities.effects.magnitude import ability_var
    from engine.entities.pathfinding.board import Board

    want_dist = 1 if axis == "melee" else 2
    stat_key = "extraPierceMelee" if axis == "melee" else "extraPierceRanged"
    etype = PIERCE_MELEE if axis == "melee" else PIERCE_RANGED
    r["stat_key"], r["effect_type"] = stat_key, etype
    r["threshold_pct"] = int(((GC.ability(ABILITY) or {}).get("constants") or {})["healthPct"])

    rid = _build_subprocess(seed, axis, board_id, armor)
    r["rid"] = rid
    bg = rpc("boardGraph", {"runnerId": rid}, 90)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        raise RuntimeError("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="native_sym")

    dv0 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    car, foe = _by_vis(dv0, CARRIER), _by_vis(dv0, FOE)
    if car is None or foe is None:
        raise RuntimeError("porteur/cible absents du deploiement")
    r["carrier_id"], r["foe_id"] = car["id"], foe["id"]
    snap0 = rpc("combatSnapshot", {"runnerId": rid}, 120)
    r["hp_max"] = int(_stats(snap0, car["id"]).get("health") or 0)
    r["passive_level"] = int(((next((u for u in (snap0.get("units") or [])
                                    if u.get("entityId") == car["id"]), {}) or {})
                              .get("unitConfig") or {}).get("passiveAbilityLevel") or 0)
    r["extra_pierce_ratio_config"] = ability_var(ABILITY, "extraPierceRatio", r["passive_level"])

    # -- geometrie : on FABRIQUE la distance voulue (1 = arme melee, 2 = arme ranged)
    got = _place_at_distance(rpc, rid, board, CARRIER, FOE, want_dist)
    if got != want_dist:
        raise RuntimeError("distance %s non atteinte (axe %s)" % (want_dist, axis))

    # -- E1/E2/E3 regime HAUT (au-dessus du seuil) -----------------------------------------
    if _ensure_turn(rpc, rid, car["owner"]) is None:
        raise RuntimeError("tour du porteur non atteint (regime HAUT)")
    capA = _capture(rpc, rid)
    uA = _unit(capA["dv"], car["id"])
    uA_inact = _unit(capA["dv_inactive"], car["id"])
    r["high_hp_pct"] = _hp_pct(capA["dv"], car["id"], r["hp_max"])
    r["high_effect_in_active_channel"] = _eff(uA, etype) is not None
    ei = _eff(uA_inact, etype)
    r["high_effect_in_inactive_channel"] = ei is not None
    r["high_effect_active_flag"] = None if ei is None else ei.get("active")
    r["high_stat_live"] = _stats(capA["snap"], car["id"]).get(stat_key)

    op = offline_pierce(capA, board, car["id"])
    r["high_offline"] = {"extra_pierce": op[0], "melee": op[1], "ranged": op[2],
                         "effects": op[3], "hp": op[4]}
    pr = offline_pierce_ratio(capA, board, car["id"], foe["id"], axis)
    r["high_port_pierce_ratio"] = {"pierce": pr[0], "is_ranged": pr[1], "hits": pr[2],
                                   "profile": pr[3]}

    hitsA, dirtyA, ab_id, whyA = _live_attack(rpc, rid, car["id"], foe["id"])
    if not hitsA:
        raise RuntimeError("coup live au regime HAUT non joue (%s)" % whyA)
    r["high_live_hits"], r["high_dirty"] = hitsA, dirtyA
    r["high_port_hits"] = offline_hits(capA, board, car["id"], foe["id"], None, False)
    # Le flux d'events live porte AUSSI ce qui SUIT le groupe d'arme -- ici la seconde attaque
    # `VisionsOfHeresy_Attack` (i2 : << After performing a normal attack, Lucien performs a second
    # attack ... 2x Bolter >>), qui n'est PAS portee (residu nomme, hors perimetre case-366-r1).
    # On isole donc le GROUPE D'ARME par sa cardinalite portee, et on garde la QUEUE en clair.
    r["high_live_weapon"] = hitsA[:len(r["high_port_hits"])]
    r["high_live_tail"] = hitsA[len(r["high_port_hits"]):]

    # -- descente sous le seuil ------------------------------------------------------------
    got_pct = _chip_below(rpc, rid, foe["id"], car["id"], r["hp_max"], r["threshold_pct"])
    if got_pct is None:
        raise RuntimeError("seuil %s%% non atteint (Lucien mort ou pilonnage bloque)"
                           % r["threshold_pct"])
    r["low_hp_pct"] = got_pct

    # la geometrie a pu bouger pendant le pilonnage -> on la REFABRIQUE
    got = _place_at_distance(rpc, rid, board, CARRIER, FOE, want_dist)
    if got != want_dist:
        raise RuntimeError("distance %s non retablie apres pilonnage" % want_dist)

    if _ensure_turn(rpc, rid, car["owner"]) is None:
        raise RuntimeError("tour du porteur non atteint (regime BAS)")
    capB = _capture(rpc, rid)
    uB = _unit(capB["dv"], car["id"])
    r["low_effect_in_active_channel"] = _eff(uB, etype) is not None
    r["low_stat_live"] = _stats(capB["snap"], car["id"]).get(stat_key)
    r["low_hp"] = int((uB or {}).get("hp") or 0)

    opB = offline_pierce(capB, board, car["id"])
    r["low_offline"] = {"extra_pierce": opB[0], "melee": opB[1], "ranged": opB[2],
                        "effects": opB[3], "hp": opB[4]}
    prB = offline_pierce_ratio(capB, board, car["id"], foe["id"], axis)
    r["low_port_pierce_ratio"] = {"pierce": prB[0], "is_ranged": prB[1], "hits": prB[2],
                                  "profile": prB[3]}
    # -- BASCULE INVERSE (mirror `DeactivateEffect` -> `RevertModification`) : << soin >> offline
    #    au-dessus du seuil -> la contribution doit RESSORTIR.
    opB_healed = offline_pierce(capB, board, car["id"], hp_override=opB[4][1])
    r["low_capture_healed_offline"] = {"extra_pierce": opB_healed[0], "melee": opB_healed[1],
                                       "ranged": opB_healed[2], "effects": opB_healed[3],
                                       "hp": opB_healed[4]}

    # -- E2 DISCRIMINANT : la capture PLEINS PV ne livre RIEN par le canal live ; le port doit
    #    quand meme produire le bon percage une fois les PV descendus OFFLINE.
    opA_low = offline_pierce(capA, board, car["id"], hp_override=r["low_hp"])
    r["high_capture_dropped_offline"] = {"extra_pierce": opA_low[0], "melee": opA_low[1],
                                         "ranged": opA_low[2], "effects": opA_low[3],
                                         "hp": opA_low[4]}

    hitsB, dirtyB, _, whyB = _live_attack(rpc, rid, car["id"], foe["id"])
    if not hitsB:
        raise RuntimeError("coup live au regime BAS non joue (%s)" % whyB)
    r["low_live_hits"], r["low_dirty"] = hitsB, dirtyB
    r["low_port_hits"] = offline_hits(capB, board, car["id"], foe["id"], None, False)
    r["low_live_weapon"] = hitsB[:len(r["low_port_hits"])]
    r["low_live_tail"] = hitsB[len(r["low_port_hits"]):]
    # CONTRE-EPREUVE de DISCRIMINANCE : MEME capture, MEME flux MT, effets de percage RETIRES.
    # Si ces per-coup egalent `low_port_hits`, le regime ne mord pas et la mesure ne prouve rien.
    r["low_port_hits_without_effect"] = offline_hits(capB, board, car["id"], foe["id"], None, False,
                                                     strip_voh=True)
    r["ok"] = True


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--axis", choices=("melee", "ranged"), default="melee")
    ap.add_argument("--seed", default=SEED)
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--armor", type=int, default=ARMOR)
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()

    import rl_collect_batch as R
    sid = R._resolve_session()

    def _unwrap(x):
        return x.get("result") if isinstance(x, dict) and "result" in x else x

    def rpc(method, body=None, timeout=120):
        return _unwrap(R._rpc(sid, method, [body] if body is not None else [], timeout=timeout))

    r = run(rpc, axis=a.axis, seed=a.seed, board_id=a.board, armor=a.armor, keep=a.keep)
    print(json.dumps({k: v for k, v in r.items() if k not in ()}, indent=1, default=str))
    if r.get("error"):
        return 1
    print("")
    print("[366-r1/%s] runner=%s board=%s seed=%s armure_cible=%s"
          % (a.axis, r["rid"], a.board, a.seed, a.armor))
    print("  seuil healthPct=%s  extraPierceRatio[L%s]=%s"
          % (r["threshold_pct"], r["passive_level"], r["extra_pierce_ratio_config"]))
    print("  E1 POSE  : a %.1f%% PV -- canal ACTIF=%s  canal includeInactive=%s (active=%s)"
          % (r["high_hp_pct"], r["high_effect_in_active_channel"],
             r["high_effect_in_inactive_channel"], r["high_effect_active_flag"]))
    print("  E2 STAT  : %s live HAUT=%s  BAS=%s | port HAUT=%s  BAS=%s"
          % (r["stat_key"], r["high_stat_live"], r["low_stat_live"],
             r["high_offline"]["melee" if a.axis == "melee" else "ranged"],
             r["low_offline"]["melee" if a.axis == "melee" else "ranged"]))
    key = "melee" if a.axis == "melee" else "ranged"
    print("           capture PLEINS PV + PV descendus OFFLINE -> port=%s (attendu %s)"
          % (r["high_capture_dropped_offline"][key], r["low_stat_live"]))
    print("           capture BASSE + << soin >> OFFLINE au-dessus du seuil -> port=%s (attendu 0)"
          % (r["low_capture_healed_offline"][key],))
    print("           ratio de percage du port : HAUT=%s BAS=%s (profil %s, ranged=%s)"
          % (r["high_port_pierce_ratio"]["pierce"], r["low_port_pierce_ratio"]["pierce"],
             r["low_port_pierce_ratio"]["profile"], r["low_port_pierce_ratio"]["is_ranged"]))
    print("  E3 DEGAT : HAUT live(arme)=%s port=%s | BAS live(arme)=%s port=%s"
          % (r["high_live_weapon"], r["high_port_hits"],
             r["low_live_weapon"], r["low_port_hits"]))
    print("           CONTRE-EPREUVE (BAS sans les effets, meme flux MT) : %s"
          % (r["low_port_hits_without_effect"],))
    print("           queue live NON portee (2e attaque VisionsOfHeresy_Attack) : HAUT=%s BAS=%s"
          % (r["high_live_tail"], r["low_live_tail"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
