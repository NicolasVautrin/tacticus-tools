"""Probe #914 -- DECOMPOSITION PAR ETAGE du rouge `test_hailstrike_pierce_envelope_live`.

Le test encadre chaque degat live par les bornes que le port calcule AVEC le bonus de percage de
`Hailstrike_ExtraPierce` (1509). Sur `master` (4c8f81d8) un tir sort : `2856 > 2701`.

CE PROBE NE FITTE RIEN. Il monte le MEME regime que la fixture `hailstrike_armor` du test (cible a
armure INTACTE, PV patches dans le seed BC) et imprime, TIR PAR TIR, les entrees et sorties de
CHAQUE etage que traverse `AttackDamageOperation` :

  * geometrie      : distance hex attaquant->cible, adjacence (le canal de SELECTION D'ARME) ;
  * arme           : celle que le port choisit (`select_weapon`) ET celle que le NATIF annonce dans
                     les tags `Attack_Weapon_*` de l'evenement de degat -- les deux sont lisibles,
                     donc l'etage « quelle arme » se tranche par MESURE et non par deduction ;
  * percage        : `pierce` sans bonus, `_pbonus` (`ability_pierce_effect_bonus`), `pierce` avec ;
  * base           : `ctx.stat(ATTACK)` de l'attaquant, `minDmg/maxDmg` de l'arme, `spread` ;
  * armure         : `defender_fixed_armor` ;
  * sortie         : `total`, `clean_min`, `clean_max` du port, et le montant LIVE.

Puis il RESOUD, sans rien ajuster dans le port : quel ratio de percage `p` rendrait le montant live
ATTEIGNABLE, et quelle base le rendrait atteignable a `p` inchange. Deux localisateurs -- ils
DESIGNENT un etage, ils ne DECIDENT de rien.

Usage :
    python probe_914_hailstrike_enveloppe.py --state-file <ABSOLU> [--tirs 6]

ASCII only (console cp1252).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import hexgeo
import probe_123_hailstrike_phase2 as P123
from engine.entities.effect_type import EffectType
from engine.entities.effects.loki.darkangels import HailstrikeExtraPierceEffect
from engine.entities.pathfinding.board import Board
from engine.entities.stats import StatType
from engine.runner.components import HealthComponent, StatsComponent
from engine.runner.messages import AttackUnitMessage
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.runner import Runner
from engine.runner.snapshot import load_state
from rl_collect_batch import _resolve_session

PYDIR = Path(__file__).resolve().parent
ABILITY = 1214


def _dv(sid, rid):
    return P123.dview(sid, rid)


def _pos(u):
    return P123.upos(u)


def _snapshot(sid, rid):
    bg = P123.rpc(sid, "boardGraph", {"runnerId": rid}, 90)
    board = Board(bg["tiles"], adjacency="native_sym") if (bg or {}).get("tiles") else None
    return (_dv(sid, rid), P123.rpc(sid, "observeBattle", {"runnerId": rid}, 90),
            P123.rpc(sid, "combatSnapshot", {"runnerId": rid}, 120),
            P123.rpc(sid, "dumpRng", {"runnerId": rid}, 60), board)


def _offline(dv, ob, snap, rng0, board):
    st = load_state(dv, ob, snap, board=board)
    if isinstance(rng0, dict) and rng0.get("mt"):
        r = IntBasedMersenneTwister()
        r.mt = list(rng0["mt"])
        r.mti = rng0["mti"]
        st.rng = r
    return st


def _damage_tags(cast):
    """Tous les evenements de degat de l'action, tags DECODES et COMPLETS (on n'en jette aucun :
    l'etage « quelle arme » se lit dans `Attack_Weapon_*`, que le test ne regardait pas)."""
    out = []
    for act in (cast.get("actions") or []):
        for e in (act.get("events") or []):
            td = e.get("tags")
            td = json.loads(td) if isinstance(td, str) else td
            if td and "Amount" in td:
                out.append(td)
    return out


def _ctx_of(st, uid):
    e = st.get_entity(uid)
    sc = e.get_component(StatsComponent) if e is not None else None
    return getattr(sc, "ctx", None) if sc is not None else None


def _etages(st, attacker, target):
    """Entrees/sorties de chaque etage du port pour CE coup, sans le jouer (lectures pures)."""
    from engine.runner.abilities.base import ability_pierce_effect_bonus
    from engine.runner.components import PositionComponent
    from engine.runner.damage_model import select_weapon, select_weapon_pierce, defender_fixed_armor
    from engine.services.battle_query import are_tiles_adjacent

    ctx = _ctx_of(st, attacker)
    ea, et = st.get_entity(attacker), st.get_entity(target)
    ap = ea.get_component(PositionComponent) if ea is not None else None
    tp = et.get_component(PositionComponent) if et is not None else None
    adj = dist = None
    if ap is not None and tp is not None:
        adj = are_tiles_adjacent((ap.col, ap.row), (tp.col, tp.row), st.board)
        dist = hexgeo.distance((ap.col, ap.row), (tp.col, tp.row))
    p0, ranged, whits = select_weapon_pierce(ctx, dist, is_adjacent=adj)
    w = select_weapon(ctx, dist, is_adjacent=adj) or {}
    bonus = ability_pierce_effect_bonus(st, attacker, target, None,
                                        is_ranged=bool(ranged), is_overwatch=False)
    p1 = select_weapon_pierce(ctx, dist, effect_bonus=bonus)[0] if bonus else p0
    effs = [type(x).__name__ for x in (st.effects.by_unit.get(attacker) or [])] \
        if st.effects is not None else []
    tctx = _ctx_of(st, target)
    hc = et.get_component(HealthComponent) if et is not None else None
    return {
        "dist": dist, "adjacent": adj, "ranged": bool(ranged), "weapon_hits": whits,
        "weapon": {k: w.get(k) for k in ("Id", "Name", "DamageProfile", "Range", "Hits",
                                         "MinDamage", "MaxDamage", "AttackRangeType")},
        "pierce_sans_bonus": p0, "effect_bonus": bonus, "pierce_avec_bonus": p1,
        "attack_stat": int(ctx.stat(StatType.ATTACK)) if ctx is not None else None,
        "armor_fixed": defender_fixed_armor(st, target),
        # Les DEUX canaux orthogonaux : `DamageCalculations$$CouldCrit` = `GetStat(9) > 0 &&
        # GetStat(10) > 0` (attaquant), et le block du DEFENSEUR. Si l'un est arme, la plage
        # NON-CRIT que le port rend ne borne PAS le montant live.
        "crit_chance_att": int(ctx.stat(StatType.CRIT_CHANCE)) if ctx is not None else None,
        "crit_damage_att": int(ctx.stat(StatType.CRIT_DAMAGE)) if ctx is not None else None,
        "block_chance_def": int(tctx.stat(StatType.BLOCK_CHANCE)) if tctx is not None else None,
        "hp_cible": getattr(hc, "hp", None),
        "effets_attaquant": effs,
    }


def _resoudre(res, live_amt):
    """DEUX localisateurs. (1) a base inchangee, quel `p` rendrait `live_amt` atteignable ?
    (2) a `p` inchange, quelle base ? On remonte les bornes BRUTES depuis `clean_*` et `pierce`,
    exactement comme la case-117 5ter l'a fait -- aucune constante ecrite en dur."""
    p = int(res.get("pierce") or 0)
    lo, hi = res.get("clean_min"), res.get("clean_max")
    if not p or lo is None or hi is None:
        return {}
    brut_lo, brut_hi = lo * 100.0 / p, hi * 100.0 / p
    p_ok = [q for q in range(1, 101)
            if int(brut_lo * q / 100.0) <= live_amt <= round(brut_hi * q / 100.0 + 1e-9)]
    facteur = live_amt / hi if hi else None
    return {"bornes_brutes": [round(brut_lo, 1), round(brut_hi, 1)],
            "p_qui_rendrait_atteignable": (p_ok[0], p_ok[-1]) if p_ok else [],
            "facteur_live_sur_borne_haute": round(facteur, 4) if facteur else None}


def mesure(args) -> int:
    sid = _resolve_session()
    rid = P123.build(args.state_file, tanky=True, regime_propre=bool(args.regime_propre))
    print("[914] runner %d -- cible a armure INTACTE, PV forces par --unit-stat ; regime_propre=%s"
          % (rid, bool(args.regime_propre)))
    try:
        return _boucle(sid, rid, args)
    finally:
        try:
            P123.rpc(sid, "disposeRunner", {"runnerId": rid}, 30)
        except Exception:
            pass


def _boucle(sid, rid, args) -> int:
    d = _dv(sid, rid)
    m = P123.mow_of(d)
    if m is None:
        print("[914] MoW absente -- montage KO")
        return 2
    ally = P123.find(d, P123.ALLY)
    foes = [u for u in (d.get("units") or []) if u.get("owner") != m.get("owner") and u.get("alive")]
    if ally is None or not foes:
        print("[914] allie/ennemi absent -- montage KO")
        return 2
    d = P123.drive(sid, rid, P123.ALLY, foes[0]["id"], 2)
    ally = P123.find(d, P123.ALLY)
    pos = {u["id"]: _pos(u) for u in (d.get("units") or [])}
    tgts = [f["id"] for f in foes if hexgeo.distance(pos[ally["id"]], pos[f["id"]]) == 2]
    if not tgts:
        print("[914] aucun ennemi a distance 2 apres deplacement -- montage KO")
        return 2
    mow_id, ally_id = m["casterId"], ally["id"]

    fh = P123.legal_targets(sid, rid, mow_id, ABILITY)
    if ally_id not in fh:
        print("[914] l'allie n'est pas cible legale de Hailstrike -- montage KO")
        return 2
    P123.rpc(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": mow_id, "targetId": ally_id, "abilityType": ABILITY}}, 150)
    d = _dv(sid, rid)
    au = next((u for u in (d.get("units") or []) if u["id"] == ally_id), {})
    nid = next((a.get("id") for a in (au.get("abilities") or []) if a.get("kind") == "normal"), None)
    print("[914] attaque normale de l'allie = ability %s" % nid)

    hors = 0
    for n in range(int(args.tirs)):
        dd = _dv(sid, rid)
        au = next((u for u in (dd.get("units") or []) if u["id"] == ally_id), {})
        if dd.get("currentPlayer") != m.get("owner") or not au.get("hasAction"):
            P123.rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 90)
            dd = _dv(sid, rid)
            au = next((u for u in (dd.get("units") or []) if u["id"] == ally_id), {})
            if not au.get("hasAction"):
                print("[914] tir %d : l'allie n'a plus d'action -- arret" % n)
                break
        if not any((e.get("name") or "") == EffectType.Hailstrike.name
                   for e in (au.get("effects") or [])):
            fh = P123.legal_targets(sid, rid, mow_id, ABILITY)
            if ally_id not in fh:
                print("[914] tir %d : buff absent et re-cast impossible -- arret" % n)
                break
            P123.rpc(sid, "applyAction", {"runnerId": rid, "action": {
                "kind": "ability", "casterId": mow_id, "targetId": ally_id,
                "abilityType": ABILITY}}, 150)
        tgt = tgts[n % len(tgts)]
        dv, ob, snap, rng0, board = _snapshot(sid, rid)
        st0 = _offline(dv, ob, snap, rng0, board)
        et = _etages(st0, ally_id, tgt)

        cast = P123.rpc(sid, "applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": ally_id, "targetId": tgt, "abilityType": nid},
            "captureEvents": True}, 150)
        tags = [t for t in _damage_tags(cast) if t.get("Attacker_Id") == ally_id]
        P123.rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 90)
        if not tags:
            print("[914] tir %d : aucun degat live attribue a l'allie" % n)
            continue
        live_amt = tags[0].get("Amount")

        st = _offline(dv, ob, snap, rng0, board)
        rr = Runner(st).install_default_handlers(20)
        rr.apply(AttackUnitMessage(attacker_id=ally_id, target_id=tgt))
        res = rr.damage_handler.last or {}
        stm = _offline(dv, ob, snap, rng0, board)
        for e in (stm.effects.by_unit.get(ally_id) or []):
            if isinstance(e, HailstrikeExtraPierceEffect):
                e.create_effect_piercing_bonus_for_attack = lambda ctx=None: None
        rrm = Runner(stm).install_default_handlers(20)
        rrm.apply(AttackUnitMessage(attacker_id=ally_id, target_id=tgt))
        resm = rrm.damage_handler.last or {}

        dedans = (res.get("clean_min") is not None
                  and res["clean_min"] <= live_amt <= res["clean_max"])
        hors += 0 if dedans else 1
        print("[914] ---- tir %d : cible u%s" % (n, tgt))
        print("[914]   ETAGES  %s" % json.dumps(et, default=str))
        print("[914]   PORT    %s" % json.dumps(
            {k: res.get(k) for k in ("hits", "total", "base", "pierce", "armor",
                                     "clean_min", "clean_max")}, default=str))
        print("[914]   MUTE    %s" % json.dumps(
            {k: resm.get(k) for k in ("total", "pierce", "clean_min", "clean_max")}, default=str))
        print("[914]   LIVE    amount=%s dedans=%s tags=%s"
              % (live_amt, dedans, json.dumps(tags[0], default=str)))
        print("[914]   RESOUD  %s" % json.dumps(_resoudre(res, live_amt), default=str))
    print("[914] BILAN : %d tir(s) HORS des bornes du port AVEC le bonus" % hors)
    return 0 if hors == 0 else 1


def _parser():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--state-file", default=str(Path(__file__).resolve().parents[2]
                                                / "logs" / "runners"
                                                / ("p914_%d.json" % os.getpid())))
    ap.add_argument("--tirs", type=int, default=6)
    ap.add_argument("--regime-propre", action="store_true",
                    help="eteint les DEUX canaux orthogonaux (crit attaquant, block defenseur) pour "
                         "que le coup appartienne a la plage NON-CRIT que le port encadre")
    return ap


if __name__ == "__main__":
    sys.exit(mesure(_parser().parse_args()))
