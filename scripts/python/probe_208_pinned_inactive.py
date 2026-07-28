#!/usr/bin/env python
"""probe_208_pinned_inactive -- `Pinned` sur `TerminatorArmour` : POSE puis INERTE (pas un refus).

Suite directe de `probe_224_effect_immunity.py`, qui avait conclu « refus de pose » sur une
inference fautive (l'absence de groupe d'evenement ne distingue pas « pas pose » de « pose et
inerte »). Ce probe mesure les DEUX faces, sans hook neuf :

  A. MECANISME -- `decisionView` avec `includeInactive: true`. Le canal par defaut DROPPE les effets
     dont `EffectComponent.IsActive @+0x5c` est faux (`readEffectsByUnit`, frida/hooks/game/effects.ts) :
     c'est CE filtre qui faisait croire a un refus. Avec le flag, l'entite-effet est publiee telle
     quelle, `active` compris.
       attendu cible `TerminatorArmour` : 1065 Pinned PRESENT, active=False
       attendu cible de controle        : 1065 Pinned PRESENT, active=True

  B. OBSERVABLE CHIFFRE -- `exposureView` (degat que la CIBLE peut infliger a mon unite, calcule par
     le predicteur NATIF) AVANT / APRES la pose, sur un runner a UN SEUL ennemi (donc `reach_dmg`
     isole cet ennemi).
       attendu cible `TerminatorArmour` : reach_dmg INCHANGE (aucun x0.70)
       attendu cible de controle        : reach_dmg REDUIT (~x0.70, `PinnedDmgReductionPct` = 30)

Poseur : `SentinelDirectives` (1139, admecDestroyer) = `(InformWeapon + Attack) + AddEffect(Pinned)`,
INCONDITIONNEL -> discriminant pur.

Usage (depuis scripts/python, session Frida chaude) :
    python probe_208_pinned_inactive.py [immune|control|all]

ASCII only (cp1252). Dispose SES runners (jamais ceux des autres).
"""
from __future__ import annotations

import sys

import probe_112_darkangels as PR
import probe_224_effect_immunity as IM
import rl_collect_batch as R

SENTINEL = 1139
PINNED = 1065
PINNER = "admecDestroyer"
IMMUNE_VICTIM = "blackAbaddon"        # trait TerminatorArmour
CONTROL_VICTIM = "blackPossession"    # Chaos sans le trait


def _effects_of(dv, uid) -> list:
    u = next((x for x in (dv.get("units") or []) if x.get("id") == uid), None)
    return list((u or {}).get("effects") or [])


def _pinned_entry(dv, uid):
    for e in _effects_of(dv, uid):
        if int(e.get("effectType") or -1) == PINNED:
            return e
    return None


def _exposure(sid, rid, uid):
    """`reachDmgMin/Max` de MON unite `uid` = somme du degat que les ennemis peuvent lui infliger
    (predicteur NATIF `GetAllPredictions`). Avec UN SEUL ennemi, c'est le degat de CET ennemi.
    `allAbilities=False` -> ATTAQUE NORMALE seule : la plage ne bouge alors QUE si un modificateur
    de degat de l'attaquant change (c'est exactement le x0.70 de `PinnedEffect
    $$CreateEffectDamageBonusForAttack` qu'on cherche a voir/ne pas voir)."""
    ev = PR.rpc(sid, "exposureView",
                {"runnerId": rid, "unitId": uid, "allAbilities": False}, 120)
    for u in (ev.get("units") or []):
        if u.get("unitId") == uid:
            return u
    return None


def _fmt_exp(e):
    if e is None:
        return "None"
    thr = [(t.get("enemyId"), t.get("dmgMin"), t.get("dmgMax")) for t in (e.get("threats") or [])]
    return "min=%s max=%s threats=%s err=%s" % (e.get("reachDmgMin"), e.get("reachDmgMax"),
                                                thr, e.get("err"))


def case(sid, victim_visual, label):
    rid = IM._build_custom(sid, [PINNER], [victim_visual])
    try:
        dv = PR.rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 90)
        bv = PR.units_by_visual(dv)
        if PINNER not in bv or victim_visual not in bv:
            print("[%s] roster incomplet: %s" % (label, sorted(bv)))
            return
        caster, tgt = bv[PINNER]["id"], bv[victim_visual]["id"]
        print("[%s] caster u%s -> u%s (%s)" % (label, caster, tgt, victim_visual))

        exp0 = _exposure(sid, rid, caster)
        print("  PRE  exposure(u%s) %s" % (caster, _fmt_exp(exp0)))
        print("  PRE  effects(all)=%s" % [(e.get("effectType"), e.get("name"), e.get("active"))
                                          for e in _effects_of(dv, tgt)])

        legal = PR.legal_from_here(sid, rid, caster, SENTINEL)
        if tgt not in legal:
            print("  ABANDON: cible non legale depuis la position courante (legal=%s)" % legal)
            return
        r = PR.cast(sid, rid, caster, tgt, SENTINEL)
        print("  cast ok=%s mutated=%s" % (r.get("ok"), r.get("mutated")))

        dv_def = PR.rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 90)
        dv_all = PR.rpc(sid, "decisionView",
                        {"runnerId": rid, "allAbilities": True, "includeInactive": True}, 90)
        p_def, p_all = _pinned_entry(dv_def, tgt), _pinned_entry(dv_all, tgt)
        print("  POST effects(default)      =%s" % [(e.get("effectType"), e.get("name"))
                                                    for e in _effects_of(dv_def, tgt)])
        print("  POST effects(includeInactive)=%s"
              % [(e.get("effectType"), e.get("name"), e.get("active")) for e in _effects_of(dv_all, tgt)])
        print("  A) Pinned canal defaut = %s | canal includeInactive = %s (active=%s)"
              % (p_def is not None, p_all is not None,
                 None if p_all is None else p_all.get("active")))

        exp1 = _exposure(sid, rid, caster)
        print("  POST exposure(u%s) %s" % (caster, _fmt_exp(exp1)))
        d0 = (exp0 or {}).get("reachDmgMax")
        d1 = (exp1 or {}).get("reachDmgMax")
        ratio = (float(d1) / float(d0)) if (d0 and d1 is not None) else None
        print("  B) reachDmgMax %s -> %s  ratio=%s"
              % (d0, d1, "n/a" if ratio is None else round(ratio, 4)))
    finally:
        PR.dispose(sid, rid)


def main():
    sid = R._resolve_session()
    only = sys.argv[1] if len(sys.argv) > 1 else "all"
    if only == "generalise":
        # 2e porteur du trait, AUTRE faction, SANS `Resilient` (=> l'inertie n'est pas un artefact
        # de `blackAbaddon`) + 2e controle sans le trait. Meme couple de montages que
        # `probe_224_effect_immunity.py --generalise`.
        case(sid, "deathTyphus", "TerminatorArmour #2")
        case(sid, "blackObliterator", "sans TerminatorArmour #2")
        return
    if only in ("immune", "all"):
        case(sid, IMMUNE_VICTIM, "TerminatorArmour")
    if only in ("control", "all"):
        case(sid, CONTROL_VICTIM, "sans TerminatorArmour")


if __name__ == "__main__":
    main()
