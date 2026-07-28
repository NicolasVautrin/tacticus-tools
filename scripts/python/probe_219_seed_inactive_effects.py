#!/usr/bin/env python
"""probe_219_seed_inactive_effects -- le SEED de `load_state` capte-t-il les effets INERTES ?

Suite directe de #208 / `case-224-effect-immunity-gate.md` SS 6 (« ce qui n'est PAS couvert » (a)) :
un `Pinned` inerte ne pouvait PAS arriver par `load_state`, parce que la capture `decisionView` par
DEFAUT droppe les effets dont `EffectComponent.IsActive @+0x5c` est faux (`readEffectsByUnit`,
frida/hooks/game/effects.ts). Seule la pose OFFLINE l'exercait.

Ce probe mesure les DEUX volets, sans hook neuf (le drapeau `includeInactive` existe cote hook
depuis `d9d0008`) :

  A. COUT du canal -- `decisionView` par defaut vs `includeInactive: true`, sur une bataille 5v5
     ORDINAIRE et sur le montage a effet inerte : octets de charge utile, nombre d'entrees d'effets,
     nombre d'entrees inertes. C'est le chiffre qui autorise (ou non) a generaliser le drapeau.

  B. CRITERE BINAIRE -- apres un `load_state` d'une bataille ou une unite porte un effet INERTE :
       * canal `includeInactive` -> `state.effects.by_unit[cible]` CONTIENT 1065, `active=False` ;
       * `state.effects.active_effects(cible)` ne le contient PAS (correspondance preservee :
         port `by_unit` = canal includeInactive, port `active_effects` = canal par defaut) ;
       * AUCUN nombre ne bouge : la plage d'attaque normale de la cible est IDENTIQUE entre l'etat
         seede par le canal par defaut et celui seede par `includeInactive`.
     Contre-cas : la meme ability sur une cible SANS `TerminatorArmour` -> effet ACTIF des deux
     cotes, present dans `active_effects`, et x0.70 applique dans les DEUX seeds.

Montage (identique a `probe_208_pinned_inactive.py`) : `SentinelDirectives` (1139, admecDestroyer)
= `(InformWeapon + Attack) + AddEffect(Pinned)` INCONDITIONNEL -> discriminant pur.

Usage (depuis scripts/python, session Frida chaude) :
    python probe_219_seed_inactive_effects.py [cost|seed|all]

ASCII only (cp1252). Dispose SES runners (jamais ceux des autres).
"""
from __future__ import annotations

import json
import sys

import probe_112_darkangels as PR
import probe_224_effect_immunity as IM
import rl_collect_batch as R
from engine.entities.effect_type import EffectType
from engine.entities.pathfinding.board import Board
from engine.runner.components import unit_state_for_effects
from engine.runner.damage_model import normal_attack_per_hit_range
from engine.runner.snapshot import decision_view_seed_body, load_state

SENTINEL = 1139
PINNED = int(EffectType.Pinned)
PINNER = "admecDestroyer"
INERT_VICTIM = "blackAbaddon"          # trait TerminatorArmour -> Pinned pose mais INERTE
CONTROL_VICTIM = "blackPossession"     # Chaos sans le trait -> Pinned ACTIF
PINNED_PCT = 0.70                      # `Effect.PinnedDmgReductionPct` = 30 (BC, pas un litteral porte)


# ------------------------------------------------------------------ capture

def _dv(sid, rid, include_inactive: bool) -> dict:
    body = (decision_view_seed_body(rid, allAbilities=True, maxRank=1) if include_inactive
            else {"runnerId": rid, "allAbilities": True, "maxRank": 1})
    return PR.rpc(sid, "decisionView", body, 90)


def _rest(sid, rid):
    """`observeBattle` + `combatSnapshot` + `boardGraph` -- le reste de ce que `load_state` mange."""
    bg = PR.rpc(sid, "boardGraph", {"runnerId": rid}, 60)
    board = Board(bg["tiles"], adjacency="native_sym") if (bg or {}).get("tiles") else None
    ob = PR.rpc(sid, "observeBattle", {"runnerId": rid}, 40)
    cs = PR.rpc(sid, "combatSnapshot", {"runnerId": rid}, 60)
    return board, ob, cs


def _effects_of(dv, uid) -> list:
    u = next((x for x in (dv.get("units") or []) if x.get("id") == uid), None)
    return list((u or {}).get("effects") or [])


def _entry(dv, uid, effect_type):
    for e in _effects_of(dv, uid):
        if int(e.get("effectType") or -1) == int(effect_type):
            return e
    return None


def _effect_stats(dv) -> dict:
    """Volume du canal : octets JSON, nb d'unites/MoW, nb d'entrees d'effets, dont INERTES."""
    rows = list(dv.get("units") or []) + list(dv.get("mows") or [])
    effs = [e for u in rows for e in (u.get("effects") or [])]
    return {"bytes": len(json.dumps(dv, separators=(",", ":"))),
            "rows": len(rows), "effects": len(effs),
            "inactive": sum(1 for e in effs if e.get("active") is False)}


# ------------------------------------------------------------------ A. cout du canal

def _cost_on(sid, rid, label) -> None:
    a = _effect_stats(_dv(sid, rid, False))
    b = _effect_stats(_dv(sid, rid, True))
    d_b = b["bytes"] - a["bytes"]
    pct = (100.0 * d_b / a["bytes"]) if a["bytes"] else 0.0
    print("  [%s] defaut        : %6d octets | %2d lignes | %2d effets"
          % (label, a["bytes"], a["rows"], a["effects"]))
    print("  [%s] includeInactive: %6d octets | %2d lignes | %2d effets (%d inertes)"
          % (label, b["bytes"], b["rows"], b["effects"], b["inactive"]))
    print("  [%s] DELTA          : %+6d octets (%+.2f %%) | %+d effets"
          % (label, d_b, pct, b["effects"] - a["effects"]))


def run_inert(sid) -> None:
    """INVENTAIRE des effets inertes d'une bataille ORDINAIRE : QUI sont les entrees que le drapeau
    ajoute. C'est ce que juge l'impact d'une activation inconditionnelle -- pas seulement le volume."""
    print("[C] INVENTAIRE des effets inertes (5v5 ordinaire, t0)")
    rid = PR.build(sid)
    try:
        dv = _dv(sid, rid, True)
        n = 0
        for u in list(dv.get("units") or []) + list(dv.get("mows") or []):
            for e in (u.get("effects") or []):
                if e.get("active") is False:
                    n += 1
                    print("  u%-4s %-20s %-42s type=%s rem=%s src=%s"
                          % (u.get("id"), u.get("visualId"), e.get("name"),
                             e.get("effectType"), e.get("remaining"), e.get("source")))
        print("  total inertes = %d" % n)
    finally:
        PR.dispose(sid, rid)


def run_cost(sid) -> None:
    """Cout sur une bataille ORDINAIRE 5v5 (aucun effet inerte attendu) : c'est le surcout que
    paierait une activation INCONDITIONNELLE du drapeau."""
    print("[A] COUT du canal includeInactive")
    rid = PR.build(sid)
    try:
        _cost_on(sid, rid, "5v5 t0")
        # Un tour d'IA pose des effets reels (buffs/debuffs) -> canal plus charge.
        try:
            PR.rpc(sid, "aiPlayByUnit",
                   {"runnerId": rid, "maxTurns": 1, "maxActivations": 9999, "maxPump": 400}, 300)
            _cost_on(sid, rid, "5v5 t1")
        except Exception as exc:                                  # tour IA indispo -> t0 suffit
            print("  (aiPlayByUnit indisponible: %s)" % str(exc)[:120])
    finally:
        PR.dispose(sid, rid)


# ------------------------------------------------------------------ B. critere binaire

def _carried(state, uid) -> dict:
    effs = (state.effects.by_unit.get(int(uid)) if state.effects is not None else None) or []
    return {int(e.effect_type): e for e in effs if not e.consumed and e.effect_type is not None}


def _active(state, uid) -> set:
    if state.effects is None:
        return set()
    return {e.effect_type for e in
            state.effects.active_effects(int(uid), unit_state_for_effects(state, int(uid)))}


def case_seed(sid, victim_visual, label, expect_active, a_units=None) -> None:
    rid = IM._build_custom(sid, [PINNER], list(a_units or [INERT_VICTIM, CONTROL_VICTIM]))
    try:
        dv0 = _dv(sid, rid, False)
        bv = PR.units_by_visual(dv0)
        if PINNER not in bv or victim_visual not in bv:
            print("[%s] roster incomplet: %s" % (label, sorted(bv)))
            return
        caster, tgt = bv[PINNER]["id"], bv[victim_visual]["id"]
        if tgt not in PR.legal_from_here(sid, rid, caster, SENTINEL):
            print("[%s] cible hors portee depuis la position courante -- ABANDON" % label)
            return
        res = PR.cast(sid, rid, caster, tgt, SENTINEL)
        print("[%s] cast u%s -> u%s ok=%s" % (label, caster, tgt, res.get("ok")))

        board, ob, cs = _rest(sid, rid)
        dv_def, dv_all = _dv(sid, rid, False), _dv(sid, rid, True)
        e_def, e_all = _entry(dv_def, tgt, PINNED), _entry(dv_all, tgt, PINNED)
        print("  LIVE  canal defaut: 1065=%s | canal includeInactive: 1065=%s (active=%s)"
              % (e_def is not None, e_all is not None,
                 None if e_all is None else e_all.get("active")))

        st_def = load_state(dv_def, ob, cs, board=board)
        st_all = load_state(dv_all, ob, cs, board=board)
        c_def, c_all = _carried(st_def, tgt), _carried(st_all, tgt)
        a_def, a_all = _active(st_def, tgt), _active(st_all, tgt)
        inst = c_all.get(PINNED)
        print("  PORT  seed(defaut)        : by_unit 1065=%s | active_effects 1065=%s"
              % (PINNED in c_def, PINNED in a_def))
        print("  PORT  seed(includeInactive): by_unit 1065=%s (flag active=%s) | active_effects 1065=%s"
              % (PINNED in c_all, None if inst is None else inst.active, PINNED in a_all))

        r_def = normal_attack_per_hit_range(st_def, tgt) or {}
        r_all = normal_attack_per_hit_range(st_all, tgt) or {}
        print("  PORT  plage d'attaque normale de la cible : seed(defaut) max=%s | seed(inactive) max=%s"
              % (r_def.get("max"), r_all.get("max")))
        ok_num = r_def.get("max") == r_all.get("max")
        ok_seed = (PINNED in c_all) and (inst is not None and inst.active is expect_active) \
            and ((PINNED in a_all) is expect_active)
        print("  VERDICT [%s] seed=%s (attendu actif=%s) | nombres inchanges=%s"
              % (label, "OK" if ok_seed else "KO", expect_active, ok_num))
    finally:
        PR.dispose(sid, rid)


def run_seed(sid) -> None:
    print("[B] CRITERE -- load_state seede-t-il l'effet INERTE avec son flag ?")
    case_seed(sid, INERT_VICTIM, "TerminatorArmour (inerte)", expect_active=False)
    case_seed(sid, CONTROL_VICTIM, "sans TerminatorArmour (actif)", expect_active=True)


def run_generalise(sid) -> None:
    """2e porteur de `TerminatorArmour`, AUTRE faction et SANS `Resilient` (`deathTyphus`) + 2e
    controle sans le trait (`blackObliterator`) -- meme couple de montages que
    `probe_208_pinned_inactive.py --generalise`. Le seed doit se comporter a l'identique."""
    print("[D] GENERALISATION -- 2e porteur du trait / 2e controle")
    pair = ["deathTyphus", "blackObliterator"]
    case_seed(sid, "deathTyphus", "TerminatorArmour #2 (inerte)", False, a_units=pair)
    case_seed(sid, "blackObliterator", "sans TerminatorArmour #2 (actif)", True, a_units=pair)


def main() -> None:
    sid = R._resolve_session()
    only = sys.argv[1] if len(sys.argv) > 1 else "all"
    if only in ("generalise",):
        run_generalise(sid)
        return
    if only in ("cost", "all"):
        run_cost(sid)
    if only in ("inert", "all"):
        run_inert(sid)
    if only in ("seed", "all"):
        run_seed(sid)


if __name__ == "__main__":
    main()
