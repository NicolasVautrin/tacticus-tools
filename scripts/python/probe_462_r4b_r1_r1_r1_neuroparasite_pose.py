#!/usr/bin/env python
"""probe #462-r4b-r1-r1-r1 -- la POSE de `Neuroparasite` et sa MONTEE EN NIVEAU, cote PORT.

#462-r4b-r1-r1 (PR #553) a ferme la MAGNITUDE de l'additif defenseur de `Neuroparasite`
(port 4448 == natif 4448, bornes `(4392, 5461)`). Mais la mesure n'avait ete possible que parce que
la POSE venait du NATIF et que l'etat etait SEEDE : en self-play 100 % porte, le parasite
n'apparaissait JAMAIS, et tous les bras etaient au NIVEAU 1.

Ce probe mesure les DEUX faces manquantes, sur le MEME montage que son parent (dont il reutilise les
helpers -- un second montage serait un fork) :

  A. POSE      -- l'attaque PSYCHIQUE du Neurothrope pose-t-elle 1218 sur sa cible, cote PORT comme
                  cote NATIF ? (`NeuroparasiteAbility$$CreateTrigger` / `$$CreateBehaviour`)
  B. NIVEAU    -- une SECONDE attaque psychique fait-elle monter le parasite de 1 a 2, des deux
                  cotes ? (`NeuroparasiteEffect$$GetIncreaseLevelBehaviour`, cap
                  `$$GetMaximumLevel` = `buffMaxLevel[lvl] + NornCrown`)
  C. NON-REGRESSION -- le degat de la 2e attaque reste-t-il celui qu'a atteste #553 ?

L'etat BAKE est verifie explicitement (`bonded` = le Neurothrope, `ability_level` = le niveau de SON
passif) : c'est ce que relit `GetAbilityState(effect)` dans `GetMaximumLevel`, et c'est ce que le 3e
argument natif `abilityState` d'`AddBondEffect` transporte.

Usage (depuis scripts/python, session Frida chaude) :
    python probe_462_r4b_r1_r1_r1_neuroparasite_pose.py

ASCII only (cp1252). Dispose SES runners (jamais ceux des autres).
"""
from __future__ import annotations

import json
import sys

import hexgeo
import probe_112_darkangels as PR
import probe_462_r4b_r1_r1_defender_additive_carriers as P0
import probe_462_r4b_r1_terminator_commanded_attack as R1
import rl_collect_batch as R

NEUROPARASITE_EFFECT = P0.NEUROPARASITE_EFFECT       # 1218 = 0x4c2 (l'EFFET)
NEURO_CARRIER = P0.NEURO_CARRIER                     # tyranNeurothrope (HERO, AU POOL)
NEURO_VICTIM = P0.NEURO_VICTIM
NEURO_RANGE = P0.NEURO_RANGE                         # portee de l'arme PSYCHIQUE (la ranged)


def _parasites(state, uid):
    """Instances 1218 NON CONSOMMEES portees par `uid` dans un `State` du PORT."""
    eff = getattr(state, "effects", None)
    if eff is None:
        return []
    return [e for e in eff.by_unit.get(int(uid), [])
            if not e.consumed and e.effect_type == NEUROPARASITE_EFFECT]


def _live_parasite(dv, uid):
    """`(present, level)` du parasite cote NATIF, lu dans `decisionView.units[].effects`."""
    for u in (dv.get("units") or []):
        if u.get("id") != uid:
            continue
        for e in (u.get("effects") or []):
            if e.get("effectType") == NEUROPARASITE_EFFECT:
                return True, e.get("level")
    return False, None


def measure(sid) -> dict:
    """Les trois mesures, sur UN seul runner (le montage est multi-tours par nature)."""
    out = {}
    p_units = [NEURO_CARRIER]
    a_units = [NEURO_VICTIM]
    layout = P0._enemy_layout(sid, p_units, a_units)
    if NEURO_VICTIM not in layout:
        return {"skip": "victime absente du layout adverse: %s" % sorted(layout)}
    # MEME patch de survie que le probe parent : le montage est MULTI-TOURS, donc le tour adverse
    # doit s'ecouler sans tuer le porteur ni deplacer la cible (`Movement: 0`). Aucun de ces champs
    # n'entre dans ce qu'on mesure.
    patch = {NEURO_CARRIER: {"Health": 300000, "RemainingHealth": 300000},
             NEURO_VICTIM: {"Health": 300000, "RemainingHealth": 300000, "Damage": 1,
                            "Movement": 0}}
    rid = P0._build(sid, p_units, a_units, armor=P0.ARMOR_PIERCE, unit_patch=patch,
                    anchor=layout[NEURO_VICTIM], occupied=layout.values())
    try:
        dv = PR.rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        bv = PR.units_by_visual(dv)
        for need in (NEURO_CARRIER, NEURO_VICTIM):
            if need not in bv:
                return {"skip": "roster incomplet: %s" % sorted(bv)}
        neuro, tgt = bv[NEURO_CARRIER]["id"], bv[NEURO_VICTIM]["id"]
        out["neuro"], out["target"] = neuro, tgt
        # `my_team` LU AVANT toute action (quirk mesure par le probe parent : avec un roster d'UNE
        # unite le tour bascule des qu'elle a agi, et `my_team` sortirait `None`).
        my_team = next((u.get("team") for u in (dv.get("units") or []) if u.get("ctrl")), None)
        normal_id = P0._normal_attack_id(dv, neuro)
        if normal_id is None:
            return {"skip": "attaque normale du Neurothrope introuvable"}
        # L'arme PSYCHIQUE est la RANGED (portee 3) -> rester HORS CONTACT, sinon l'attaque part en
        # melee `Physical` et le gate `CurrentAttackDamageProfilesContain(0xd)` ne s'ouvre pas.
        pos = PR.positions(dv)
        ok, dv = P0._move_within(sid, rid, dv, neuro, pos[tgt], NEURO_RANGE, min_dist=2)
        if not ok:
            return {"skip": "aucune tuile legale a 2<=d<=%d de la victime" % NEURO_RANGE}
        if tgt not in PR.legal_from_here(sid, rid, neuro, normal_id):
            return {"skip": "cible non legale pour l'attaque du Neurothrope"}

        # ---- A. POSE ------------------------------------------------------------------------
        # Etat AVANT toute attaque : le parasite n'existe NULLE PART. On rejoue l'attaque cote PORT
        # sur cet etat, PUIS on la joue cote NATIF, et on compare ce que chacun a pose.
        board, dv, ob, cs = R1._snapshot(sid, rid)
        st_pre = R1._seeded_state(sid, rid, board, dv, ob, cs)
        out["pre_port_parasites"] = len(_parasites(st_pre, tgt))
        out["pre_live_parasite"] = _live_parasite(dv, tgt)[0]
        last1, st_after = P0._replay_attack(sid, rid, board, dv, ob, cs, neuro, tgt)
        posed = _parasites(st_after, tgt)
        out["port_pose_count"] = len(posed)
        if posed:
            e = posed[0]
            out["port_pose"] = {"level": e.level, "bonded": e.bonded, "source": e.source,
                                "remaining": e.remaining_turns,
                                "ability_level": getattr(e, "ability_level", None),
                                "multiplier": getattr(e, "ability_variables_multiplier", None),
                                "cls": type(e).__name__}
        out["port_attack1_per_hit"] = list(last1.get("per_hit") or [])
        out["port_attack1_profile"] = last1.get("profile")

        first = PR.act(sid, rid, {"kind": "ability", "casterId": neuro, "targetId": tgt,
                                  "abilityType": normal_id})
        if not first.get("ok"):
            return dict(out, skip="1ere attaque live KO: %s" % str(first)[:200])
        dv = PR.rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        live_present, live_level = _live_parasite(dv, tgt)
        out["live_pose"] = {"present": live_present, "level": live_level}
        if not live_present:
            return dict(out, skip="parasite 1218 NON pose cote NATIF apres la 1ere attaque "
                                  "(le gate Psychic ne s'est pas ouvert)")

        # ---- B. NIVEAU ----------------------------------------------------------------------
        # Tour suivant : une unite n'agit qu'une fois par tour. On rend la main a l'IA adverse puis
        # on RE-VERIFIE la geometrie (son tour a pu la changer).
        ok, dv = P0._advance_to_my_turn(sid, rid, my_team)
        if not ok:
            return dict(out, skip="la main n'est pas revenue au joueur (currentPlayer=%s)"
                                  % dv.get("currentPlayer"))
        pos = PR.positions(dv)
        if tgt not in pos or neuro not in pos:
            return dict(out, skip="unite disparue apres le tour adverse")
        ok, dv = P0._move_within(sid, rid, dv, neuro, pos[tgt], NEURO_RANGE, min_dist=2)
        if not ok:
            return dict(out, skip="hors plage [2,%d] apres le tour adverse" % NEURO_RANGE)
        if tgt not in PR.legal_from_here(sid, rid, neuro, normal_id):
            return dict(out, skip="cible non legale au tour 2 (d=%s)"
                                  % hexgeo.distance(PR.positions(dv)[neuro],
                                                    PR.positions(dv)[tgt]))
        board, dv, ob, cs = R1._snapshot(sid, rid)
        out["t2_live_level_before"] = _live_parasite(dv, tgt)[1]
        st2 = R1._seeded_state(sid, rid, board, dv, ob, cs)
        pre2 = _parasites(st2, tgt)
        out["t2_port_level_before"] = pre2[0].level if pre2 else None
        # Le CAP natif, calcule par le port sur l'instance SEEDEE (`GetMaximumLevel`).
        if pre2:
            from engine.runner.operations.triggers.loki.neuroparasite import (
                neuroparasite_maximum_level)
            out["t2_port_max_level"] = neuroparasite_maximum_level(st2, pre2[0])
        last2, st_after2 = P0._replay_attack(sid, rid, board, dv, ob, cs, neuro, tgt)
        post2 = _parasites(st_after2, tgt)
        out["t2_port_level_after"] = post2[0].level if post2 else None
        out["port_attack2_per_hit"] = list(last2.get("per_hit") or [])
        out["port_attack2_total"] = last2.get("total")
        out["port_attack2_profile"] = last2.get("profile")

        hp0 = PR.hp_of(sid, rid)
        res = PR.act(sid, rid, {"kind": "ability", "casterId": neuro, "targetId": tgt,
                                "abilityType": normal_id})
        if not res.get("ok"):
            return dict(out, skip="2e attaque live KO: %s" % str(res)[:200])
        hp1 = PR.hp_of(sid, rid)
        dv = PR.rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        out["t2_live_level_after"] = _live_parasite(dv, tgt)[1]
        out["live_attack2_per_hit"] = R1._live_hits(res, tgt)
        out["live_attack2_delta"] = (hp0.get(tgt) or (0,))[0] - (hp1.get(tgt) or (0,))[0]
        return out
    finally:
        PR.dispose(sid, rid)


def measure_melee_negative(sid) -> dict:
    """CONTROLE NEGATIF du gate `CurrentAttackDamageProfilesContain(0xd = Psychic)`.

    Le Neurothrope est bi-arme : melee `Physical`, ranged `Psychic` (portee 3). Amene AU CONTACT, son
    attaque normale part en `Physical` -> le gate ne s'ouvre pas et le parasite ne DOIT etre pose ni
    par le port ni par le natif. Sans ce bras, un port qui aurait OUBLIE le gate rendrait exactement
    les memes chiffres que le bras nominal : c'est le seul regime qui SEPARE les deux modeles."""
    p_units = [NEURO_CARRIER]
    a_units = [NEURO_VICTIM]
    layout = P0._enemy_layout(sid, p_units, a_units)
    if NEURO_VICTIM not in layout:
        return {"skip": "victime absente du layout adverse: %s" % sorted(layout)}
    patch = {NEURO_CARRIER: {"Health": 300000, "RemainingHealth": 300000},
             NEURO_VICTIM: {"Health": 300000, "RemainingHealth": 300000, "Damage": 1,
                            "Movement": 0}}
    rid = P0._build(sid, p_units, a_units, armor=P0.ARMOR_PIERCE, unit_patch=patch,
                    anchor=layout[NEURO_VICTIM], occupied=layout.values())
    try:
        dv = PR.rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        bv = PR.units_by_visual(dv)
        if NEURO_CARRIER not in bv or NEURO_VICTIM not in bv:
            return {"skip": "roster incomplet: %s" % sorted(bv)}
        neuro, tgt = bv[NEURO_CARRIER]["id"], bv[NEURO_VICTIM]["id"]
        normal_id = P0._normal_attack_id(dv, neuro)
        pos = PR.positions(dv)
        ok, dv = P0._move_within(sid, rid, dv, neuro, pos[tgt], 1, min_dist=1)   # AU CONTACT
        if not ok:
            return {"skip": "aucune tuile legale au contact de la victime"}
        if tgt not in PR.legal_from_here(sid, rid, neuro, normal_id):
            return {"skip": "cible non legale au contact"}
        board, dv, ob, cs = R1._snapshot(sid, rid)
        last, st_after = P0._replay_attack(sid, rid, board, dv, ob, cs, neuro, tgt)
        res = PR.act(sid, rid, {"kind": "ability", "casterId": neuro, "targetId": tgt,
                                "abilityType": normal_id})
        if not res.get("ok"):
            return {"skip": "attaque melee live KO: %s" % str(res)[:200]}
        dv = PR.rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        return {"neuro": neuro, "target": tgt, "port_profile": last.get("profile"),
                "port_parasites": len(_parasites(st_after, tgt)),
                "live_parasite": _live_parasite(dv, tgt)[0],
                "port_per_hit": list(last.get("per_hit") or [])}
    finally:
        PR.dispose(sid, rid)


# Porteur du trait `SuppressiveFire` (pose `Pinned` 1065 sur la cible d'une attaque RANGED) dont
# l'arme ranged n'est PAS psychique -> il fait monter le parasite par la SEULE voie `On(0x3d)`.
PINNER = "templAggressor"
PINNER_RANGE = 2                    # `Bolter` (l'arme melee `Power` ne poserait pas de Pinned)


def measure_pinned_level(sid) -> dict:
    """2e `Triggered()` de `NeuroparasiteEffect$$CreateHandleTriggerAbilitiesInternal` :
    `On(0x3d = PreEffectAdded) & OwnerIsTarget & TriggeringEffectIs(0x429 = 1065 Pinned)`.

    Sequence, DANS LE MEME TOUR (les deux unites du joueur agissent chacune une fois) :
      1. le Neurothrope frappe en PSYCHIQUE -> `On(9)` pose le parasite (niveau 1) ;
      2. `templAggressor` frappe la MEME cible avec son `Bolter` (RANGED, NON psychique) -> son trait
         `SuppressiveFire` pose `Pinned`, dont la POSE emet `On(0x3d)` -> le parasite monte a 2.

    DISCRIMINANT : le profil `Bolter` ferme le gate de l'AUTRE trigger (`On(9) &
    CurrentAttackDamageProfilesContain(0xd)`). Un port qui aurait oublie ce gate rendrait **3** au
    lieu de 2 (les deux triggers auraient mordu sur la meme attaque)."""
    p_units = [NEURO_CARRIER, PINNER]
    a_units = [NEURO_VICTIM]
    layout = P0._enemy_layout(sid, p_units, a_units)
    if NEURO_VICTIM not in layout:
        return {"skip": "victime absente du layout adverse: %s" % sorted(layout)}
    patch = {NEURO_CARRIER: {"Health": 300000, "RemainingHealth": 300000},
             PINNER: {"Health": 300000, "RemainingHealth": 300000},
             NEURO_VICTIM: {"Health": 300000, "RemainingHealth": 300000, "Damage": 1,
                            "Movement": 0}}
    rid = P0._build(sid, p_units, a_units, armor=P0.ARMOR_PIERCE, unit_patch=patch,
                    anchor=layout[NEURO_VICTIM], occupied=layout.values())
    try:
        dv = PR.rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        bv = PR.units_by_visual(dv)
        for need in (NEURO_CARRIER, PINNER, NEURO_VICTIM):
            if need not in bv:
                return {"skip": "roster incomplet: %s" % sorted(bv)}
        neuro, pinner, tgt = bv[NEURO_CARRIER]["id"], bv[PINNER]["id"], bv[NEURO_VICTIM]["id"]
        neuro_atk = P0._normal_attack_id(dv, neuro)
        pin_atk = P0._normal_attack_id(dv, pinner)
        if neuro_atk is None or pin_atk is None:
            return {"skip": "attaque normale introuvable (neuro=%s pinner=%s)" % (neuro_atk, pin_atk)}
        # (1) POSE par l'attaque psychique du Neurothrope (natif).
        pos = PR.positions(dv)
        ok, dv = P0._move_within(sid, rid, dv, neuro, pos[tgt], NEURO_RANGE, min_dist=2)
        if not ok:
            return {"skip": "Neurothrope hors plage [2,%d]" % NEURO_RANGE}
        if tgt not in PR.legal_from_here(sid, rid, neuro, neuro_atk):
            return {"skip": "cible non legale pour le Neurothrope"}
        first = PR.act(sid, rid, {"kind": "ability", "casterId": neuro, "targetId": tgt,
                                  "abilityType": neuro_atk})
        if not first.get("ok"):
            return {"skip": "attaque psychique live KO: %s" % str(first)[:200]}
        dv = PR.rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        present, lvl1 = _live_parasite(dv, tgt)
        if not present:
            return {"skip": "parasite non pose par l'attaque psychique"}
        # (2) l'Aggressor a portee de son BOLTER (RANGED : min_dist force l'arme non-melee).
        pos = PR.positions(dv)
        ok, dv = P0._move_within(sid, rid, dv, pinner, pos[tgt], PINNER_RANGE, min_dist=2)
        if not ok:
            return {"skip": "Aggressor hors plage [2,%d]" % PINNER_RANGE}
        if tgt not in PR.legal_from_here(sid, rid, pinner, pin_atk):
            return {"skip": "cible non legale pour l'Aggressor"}
        board, dv, ob, cs = R1._snapshot(sid, rid)
        st_pre = R1._seeded_state(sid, rid, board, dv, ob, cs)
        pre = _parasites(st_pre, tgt)
        last, st_after = P0._replay_attack(sid, rid, board, dv, ob, cs, pinner, tgt)
        post = _parasites(st_after, tgt)
        res = PR.act(sid, rid, {"kind": "ability", "casterId": pinner, "targetId": tgt,
                                "abilityType": pin_atk})
        if not res.get("ok"):
            return {"skip": "attaque Bolter live KO: %s" % str(res)[:200]}
        dv = PR.rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        live_types = sorted(e.get("effectType") for u in (dv.get("units") or [])
                            if u.get("id") == tgt for e in (u.get("effects") or []))
        return {"neuro": neuro, "pinner": pinner, "target": tgt,
                "level_after_psychic_live": lvl1,
                "port_profile": last.get("profile"),
                "port_level_before": pre[0].level if pre else None,
                "port_level_after": post[0].level if post else None,
                "live_level_after": _live_parasite(dv, tgt)[1],
                "live_effect_types": live_types}
    finally:
        PR.dispose(sid, rid)


def _report(m):
    if m.get("skip"):
        print("SKIP %s" % m["skip"])
        print(json.dumps({k: v for k, v in m.items() if k != "skip"}, default=str, indent=1))
        return
    print("== A. POSE (attaque 1, PSYCHIQUE) ==")
    print("  avant : port=%s parasite(s), natif present=%s"
          % (m["pre_port_parasites"], m["pre_live_parasite"]))
    print("  PORT  : %s parasite(s) pose(s) -> %s"
          % (m["port_pose_count"], json.dumps(m.get("port_pose"), default=str)))
    print("  NATIF : %s" % json.dumps(m.get("live_pose"), default=str))
    print("  degat attaque 1 (port) : %s profil=%s"
          % (m.get("port_attack1_per_hit"), m.get("port_attack1_profile")))
    print("== B. NIVEAU (attaque 2, meme profil) ==")
    print("  avant : port=%s natif=%s | cap GetMaximumLevel (port) = %s"
          % (m.get("t2_port_level_before"), m.get("t2_live_level_before"),
             m.get("t2_port_max_level")))
    print("  apres : port=%s natif=%s"
          % (m.get("t2_port_level_after"), m.get("t2_live_level_after")))
    print("== C. NON-REGRESSION magnitude (attaque 2) ==")
    print("  PORT  per_hit = %s (total %s) profil=%s"
          % (m.get("port_attack2_per_hit"), m.get("port_attack2_total"),
             m.get("port_attack2_profile")))
    print("  NATIF per_hit = %s (delta PV %s)"
          % (m.get("live_attack2_per_hit"), m.get("live_attack2_delta")))


def _report_melee(m):
    print("== D. CONTROLE NEGATIF (attaque MELEE `Physical`, gate Psychic FERME) ==")
    if m.get("skip"):
        print("  SKIP %s" % m["skip"])
        return
    print("  profil port=%s  per_hit=%s" % (m.get("port_profile"), m.get("port_per_hit")))
    print("  parasites poses : PORT=%s  NATIF=%s"
          % (m.get("port_parasites"), m.get("live_parasite")))


def _report_pinned(m):
    print("== E. MONTEE PAR `Pinned` (On(0x3d), attaque Bolter NON psychique) ==")
    if m.get("skip"):
        print("  SKIP %s" % m["skip"])
        return
    print("  niveau apres l'attaque psychique (natif) = %s" % m.get("level_after_psychic_live"))
    print("  profil de l'attaque du pinner (port) = %s" % m.get("port_profile"))
    print("  niveau : PORT %s -> %s | NATIF -> %s"
          % (m.get("port_level_before"), m.get("port_level_after"), m.get("live_level_after")))
    print("  effets natifs sur la cible : %s" % (m.get("live_effect_types"),))


def main():
    sid = R._resolve_session()
    only = sys.argv[1] if len(sys.argv) > 1 else "all"
    try:
        if only in ("pose", "all"):
            _report(measure(sid))
        if only in ("melee", "all"):
            _report_melee(measure_melee_negative(sid))
        if only in ("pinned", "all"):
            _report_pinned(measure_pinned_level(sid))
    finally:
        for rid in list(PR._rids):
            PR.dispose(sid, rid)


if __name__ == "__main__":
    main()
