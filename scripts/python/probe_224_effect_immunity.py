#!/usr/bin/env python
"""probe_224_effect_immunity -- GATE D'IMMUNITE D'EFFET : que fait le NATIF sur une cible immunisee ?

Runners isoles (seed BC + MC1_67, camp joueur DEPLACE au contact). Quatre montages :

  `sentinel`   -- DISCRIMINANT PUR : `SentinelDirectivesAbility` (1139, admecDestroyer) =
                  `(InformWeapon + Attack) + AddEffect(Pinned)`, aucune branche conditionnelle, aucune
                  election d'attaquant. Joue sur `blackAbaddon` (trait `TerminatorArmour`, i2 : « This
                  unit cannot be Suppressed ») PUIS sur `blackPossession` (Chaos sans le trait).
  `generalise` -- le meme, sur un 2e porteur du trait d'une AUTRE faction (`deathTyphus`, sans
                  `Resilient`) + un 2e controle (`blackObliterator`).
  (defaut)     -- `ExemplarOfHateAbility` (1140, darkaAsmodai) = le montage de la MESURE #112.
  `driven` / `adjacent` -- variantes du montage #112 qui tentent de forcer un allie DarkAngels a
                  portee de la cible (le confond de l'election d'attaquant ; cf. case-224 §5.2).

On lit, pour chaque montage : la cascade d'evenements BRUTE (groupes `StartGroup` + messages) et les
effets de la cible AVANT/APRES (`decisionView.effects`, qui DROPPE les effets inactifs -- d'ou la
lecture des DEUX canaux).

Objet : trancher entre les deux lectures possibles du natif
  (1) `AddEffectOperation$$Execute` ABANDONNE (gate `EntityIsImmuneToEffect`), ou
  (2) l'effet est POSE puis DESACTIVE (`PinnedEffect$$CreateActiveCondition` = `!HasTrait(0x40f)`).
VERDICT MESURE : (1) -- aucun groupe `AddEffect`, aucune entite-effet (cf. case-224 §3).

Usage (depuis scripts/python, session Frida chaude) :
    python probe_224_effect_immunity.py [sentinel|generalise|driven|adjacent]

ASCII only (cp1252). Dispose SES runners (jamais ceux des autres).
"""
from __future__ import annotations

import json

import hexgeo
import probe_112_darkangels as PR
import rl_collect_batch as R

EXEMPLAR = 1140
PINNED = 1065
EOH_TARGET = 1293


def _dump_events(evts) -> None:
    for e in (evts or []):
        k = e.get("kind")
        if k == "group":
            print("    GROUP g=%s entity=%s source=%s" % (e.get("group"), e.get("entity"),
                                                          e.get("source")))
        elif k == "finish":
            print("    FINISH entity=%s" % (e.get("entity"),))
        else:
            tg = e.get("tags")
            if isinstance(tg, str):
                try:
                    tg = json.loads(tg)
                except Exception:
                    pass
            print("    ACTION step=%s entity=%s tags=%s" % (e.get("step"), e.get("entity"), tg))


def _case(sid, rid, dv, asmo, tgt, label):
    pos = PR.positions(dv)
    print("[%s] target u%s d=%s" % (label, tgt, hexgeo.distance(pos[asmo], pos[tgt])))
    print("  PRE  effects:", PR.eff_names(dv, tgt))
    legal = PR.legal_from_here(sid, rid, asmo, EXEMPLAR)
    print("  legal fromHere:", legal)
    if tgt not in legal:
        print("  ABANDON: cible non legale depuis la position courante")
        return
    r = PR.cast(sid, rid, asmo, tgt, EXEMPLAR)
    print("  applyAction ok=%s mutated=%s" % (r.get("ok"), r.get("mutated")))
    _dump_events(r.get("events"))
    dv2 = PR.rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True})
    print("  POST effects:", PR.eff_names(dv2, tgt))
    return dv2


SENTINEL = 1139


def _build_custom(sid, p_units, a_units):
    """`PR._build_once` avec des rosters CHOISIS (le probe 112 les a en dur)."""
    import copy
    seed = R._load_seed_bc()
    board_dump = R._load_board_dump(PR.BOARD)
    template, pool, _mow = R._normalize_and_extract_pool(sid, seed, PR.RANK, board_dump=board_dump)
    miss = [u for u in list(p_units) + list(a_units) if u not in pool]
    if miss:
        raise RuntimeError("hors pool rank %d : %s" % (PR.RANK, miss))
    bc = copy.deepcopy(template)
    R._patch_predefined_units(bc, list(a_units))
    pos = PR._contact_placement(bc, len(p_units))
    player_units = [{"unitId": u, "playerId": R.PLAYER_ID_HUMAN,
                     "col": pos[i][0], "row": pos[i][1]} for i, u in enumerate(p_units)]
    resp = R._rpc(sid, "initAndStart",
                  [{"configJson": json.dumps(bc), "seed": PR.SEED, "playerUnits": player_units}],
                  timeout=60)
    rid = (resp.get("result") or {}).get("runnerId")
    if rid is None:
        raise RuntimeError("initAndStart KO: %s" % (resp.get("error") or resp))
    PR._rids.append(rid)
    return rid


def case_sentinel(sid, victim_visual, label, a_units=("blackAbaddon", "blackPossession")):
    """`SentinelDirectives` (1139, admecDestroyer) = 1 attaque ranged + `AddEffect(Pinned)` INCONDITIONNEL
    (aucune election d'attaquant, aucune branche conditionnelle) -> discriminant PUR du gate d'immunite."""
    rid = _build_custom(sid, ["admecDestroyer"], list(a_units))
    try:
        dv = PR.rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True})
        bv = PR.units_by_visual(dv)
        caster = bv["admecDestroyer"]["id"]
        tgt = bv[victim_visual]["id"]
        pos = PR.positions(dv)
        print("[C %s] caster u%s @%s -> u%s (%s) @%s d=%s" % (
            label, caster, pos.get(caster), tgt, victim_visual, pos.get(tgt),
            hexgeo.distance(pos[caster], pos[tgt])))
        print("  PRE  effects:", PR.eff_names(dv, tgt))
        legal = PR.legal_from_here(sid, rid, caster, SENTINEL)
        print("  legal fromHere:", legal)
        if tgt not in legal:
            mv = PR.rpc(sid, "abilityTargets",
                        {"runnerId": rid, "unitId": caster, "abilityType": SENTINEL}, 90)
            print("  ABANDON: cible non legale (abilityTargets=%s)" % json.dumps(mv)[:600])
            return
        r = PR.cast(sid, rid, caster, tgt, SENTINEL)
        print("  applyAction ok=%s mutated=%s" % (r.get("ok"), r.get("mutated")))
        _dump_events(r.get("events"))
        dv2 = PR.rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True})
        print("  POST effects:", PR.eff_names(dv2, tgt))
    finally:
        PR.dispose(sid, rid)


def case_exemplar_driven(sid, victim_visual, label):
    """Montage A DEBIAISE : on DEPLACE `darkaHellblaster` AU CONTACT de la cible avant le cast, pour
    que la branche Chaos d'ExemplarOfHate ait a coup sur un attaquant DarkAngels a portee. Sans ca,
    l'absence de la branche entiere (override + attaque libre) confond l'absence de `Pinned`."""
    rid = PR.build(sid)
    try:
        dv = PR.rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True})
        bv = PR.units_by_visual(dv)
        asmo, hell = bv["darkaAsmodai"]["id"], bv["darkaHellblaster"]["id"]
        tgt = bv[victim_visual]["id"]
        pos = PR.positions(dv)
        # tuile libre adjacente a la cible pour l'allie elu
        occupied = set(pos.values())
        ring = [p for p in hexgeo.ring(pos[tgt][0], pos[tgt][1], 1) if p not in occupied]
        if ring:
            PR.act(sid, rid, {"kind": "move", "unitId": hell,
                              "col": ring[0][0], "row": ring[0][1]})
        dv = PR.rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True})
        pos = PR.positions(dv)
        print("[A' %s] asmodai u%s @%s | hellblaster u%s @%s | cible u%s @%s (d_allie=%s)" % (
            label, asmo, pos.get(asmo), hell, pos.get(hell), tgt, pos.get(tgt),
            hexgeo.distance(pos[hell], pos[tgt])))
        print("  PRE  effects:", PR.eff_names(dv, tgt))
        legal = PR.legal_from_here(sid, rid, asmo, EXEMPLAR)
        if tgt not in legal:
            print("  ABANDON: cible non legale (legal=%s)" % legal)
            return
        r = PR.cast(sid, rid, asmo, tgt, EXEMPLAR)
        print("  applyAction ok=%s mutated=%s" % (r.get("ok"), r.get("mutated")))
        _dump_events(r.get("events"))
        dv2 = PR.rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True})
        print("  POST effects:", PR.eff_names(dv2, tgt))
    finally:
        PR.dispose(sid, rid)


def case_exemplar_ally_adjacent(sid, victim_visual, label):
    """Montage A'' — confond ELIMINE : on DEPLACE LA CIBLE (les deux camps sont pilotables) au CONTACT de
    `darkaHellblaster`, donc l'election d'attaquant d'ExemplarOfHate a FORCEMENT un candidat a portee.
    Ce qui reste alors comme difference entre les deux cibles est le SEUL trait `TerminatorArmour`."""
    rid = PR.build(sid)
    try:
        dv = PR.rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True})
        bv = PR.units_by_visual(dv)
        asmo, hell = bv["darkaAsmodai"]["id"], bv["darkaHellblaster"]["id"]
        tgt = bv[victim_visual]["id"]
        pos = PR.positions(dv)
        occupied = set(pos.values())
        ring = [p for p in hexgeo.ring(pos[tgt][0], pos[tgt][1], 1) if p not in occupied]
        for p in ring:                                     # 1re tuile ou le deplacement de l'ALLIE passe
            PR.act(sid, rid, {"kind": "move", "unitId": hell, "col": p[0], "row": p[1]})
            dv = PR.rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True})
            if hexgeo.distance(PR.positions(dv)[tgt], PR.positions(dv)[hell]) == 1:
                break
        pos = PR.positions(dv)
        print("[A'' %s] asmodai u%s @%s | hellblaster u%s @%s | cible u%s @%s (d_allie=%s)" % (
            label, asmo, pos.get(asmo), hell, pos.get(hell), tgt, pos.get(tgt),
            hexgeo.distance(pos[hell], pos[tgt])))
        legal = PR.legal_from_here(sid, rid, asmo, EXEMPLAR)
        if tgt not in legal:
            print("  ABANDON: cible non legale (legal=%s)" % legal)
            return
        r = PR.cast(sid, rid, asmo, tgt, EXEMPLAR)
        print("  applyAction ok=%s mutated=%s" % (r.get("ok"), r.get("mutated")))
        _dump_events(r.get("events"))
        dv2 = PR.rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True})
        print("  POST effects:", PR.eff_names(dv2, tgt))
    finally:
        PR.dispose(sid, rid)


def main():
    import sys
    sid = R._resolve_session()
    only = sys.argv[1] if len(sys.argv) > 1 else "all"
    if only == "driven":
        case_exemplar_driven(sid, "blackAbaddon", "TerminatorArmour")
        case_exemplar_driven(sid, "blackPossession", "sans TerminatorArmour")
        return
    if only == "generalise":
        # 2e porteur du trait (GENERALISATION : l'immunite n'est pas un artefact de blackAbaddon --
        # deathTyphus est DeathGuard et n'a PAS `Resilient`) + 2e cible de controle sans le trait.
        # (`blackTerminator` ne convient PAS : son `TeleportStrike_TeleportingIn` le rend inciblable.)
        case_sentinel(sid, "deathTyphus", "TerminatorArmour #2",
                      a_units=("deathTyphus", "blackObliterator"))
        case_sentinel(sid, "blackObliterator", "sans TerminatorArmour #2",
                      a_units=("deathTyphus", "blackObliterator"))
        return
    if only == "adjacent":
        case_exemplar_ally_adjacent(sid, "blackAbaddon", "TerminatorArmour")
        case_exemplar_ally_adjacent(sid, "blackPossession", "sans TerminatorArmour")
        return
    if only in ("sentinel", "all"):
        case_sentinel(sid, "blackAbaddon", "TerminatorArmour")
        case_sentinel(sid, "blackPossession", "sans TerminatorArmour")
    if only == "sentinel":
        return
    rid = PR.build(sid)
    try:
        dv = PR.rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True})
        bv = PR.units_by_visual(dv)
        asmo = bv["darkaAsmodai"]["id"]
        abad = bv["blackAbaddon"]["id"]
        print("asmodai u%s | abaddon u%s" % (asmo, abad))
        for vid, u in sorted(bv.items()):
            print("  %-20s u%-4s ctrl=%s" % (vid, u.get("id"), u.get("ctrl")))
        _case(sid, rid, dv, asmo, abad, "A TerminatorArmour")
    finally:
        PR.dispose(sid, rid)

    # Contre-cas : meme cast, cible Chaos SANS TerminatorArmour -> runner NEUF (l'ability est
    # once-per-turn et termine le tour d'Asmodai).
    rid = PR.build(sid)
    try:
        dv = PR.rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True})
        bv = PR.units_by_visual(dv)
        asmo = bv["darkaAsmodai"]["id"]
        ctl = (bv.get("blackPossession") or bv.get("blackHaarken") or {}).get("id")
        print("asmodai u%s | controle u%s" % (asmo, ctl))
        _case(sid, rid, dv, asmo, ctl, "B sans TerminatorArmour")
    finally:
        PR.dispose(sid, rid)


if __name__ == "__main__":
    main()
