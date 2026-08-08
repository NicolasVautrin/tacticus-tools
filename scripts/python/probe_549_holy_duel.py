"""#549 -- `HolyDuel` (1050, `templChampion`) : confrontation NATIF / PORT des DEUX faces.

L'ability etait un NO-OP SILENCIEUX (absente d'`ABILITY_CLASSES`) : la DECISION pouvait la choisir
(`playbook/noncomparable/holy_duel.py` existe depuis longtemps) alors que l'EXECUTION ne faisait
RIEN -- 0 degat, 0 effet, aucune erreur.

CE QUE CHAQUE PAS MESURE
------------------------
* `--step cast` : le cast lui-meme, NATIF puis PORT sur l'ETAT CAPTURE JUSTE AVANT.
    - les effets poses SUR LA CIBLE          : 1091 + la famille `Taunted` (27/25/26/1237)
    - les effets poses SUR LE CHAMPION       : la famille `Taunted` + 1092 + 1093
      (c'est LE point du cas : `HolyDuel_TauntEffect$$ApplyInternal` pose TROIS de ses quatre
       sous-effets sur l'entite BONDEE, pas sur le porteur)
    - le `bondedEntityId` de chaque instance : croise (celui de la cible pointe le champion, ceux
      du champion pointent la cible)
    - le DEGAT de l'attaque normale du cast  : il doit porter `+extraDmg` DES ce coup, puisque
      l'arbre pose le bond AVANT (`op_BitwiseAnd` evalue a gauche d'abord).

* `--step adjacency` : le trigger (c) `get_Adjacent` d'`ABondEffect`, DEUX bras geometriques
  (le meme geste a une tuile pres, cf. `probe_462_r4b_r1_r1_r1_r1_b_bond_range.py` §4) --
  ELOIGNE : le push met les duellistes a distance 2 -> le bond doit TOMBER ;
  PROCHE  : le push les laisse a distance 1 -> le bond doit RESTER.
  Mesure NATIVE **et** PORT (`BondRemoveOnAdjacencyLost`), la ou l'ancien bras ne pouvait mesurer
  que le natif (le port ne posait pas 1091).

USAGE
    python probe_549_holy_duel.py --step cast
    python probe_549_holy_duel.py --step adjacency
    python probe_549_holy_duel.py --step all

ASCII only.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hexgeo                                                        # noqa: E402
import probe_112_darkangels as PR                                    # noqa: E402
import probe_462_r4b_r1_r1_r1_r1_b_bond_range as B                   # noqa: E402
import probe_462_r4b_r1_terminator_commanded_attack as R1            # noqa: E402
from probe_462_r4b_r1_terminator_commanded_attack import _live_hits  # noqa: E402
from rl_collect_batch import _resolve_session                        # noqa: E402

HOLY_DUEL = 1050
HOLY_DUEL_TAUNT = 1091
HOLY_DUEL_EXTRA_DMG = 1092
HOLY_DUEL_DMG_REDUCTION = 1093
TAUNTED_FAMILY = (27, 25, 26, 1237)
DUEL_FAMILY = tuple(sorted(set(TAUNTED_FAMILY) | {HOLY_DUEL_TAUNT, HOLY_DUEL_EXTRA_DMG,
                                                  HOLY_DUEL_DMG_REDUCTION}))


# ------------------------------------------------------------------------------------------------
# lecture des DEUX cotes, meme forme
# ------------------------------------------------------------------------------------------------
def live_family(dv, uid):
    """{effectType: bondedEntityId|None} des effets de la famille DUEL portes par `uid`."""
    u = next((x for x in (dv.get("units") or []) if x.get("id") == uid), None)
    out = {}
    for e in ((u or {}).get("effects") or []):
        et = int(e.get("effectType") or -1)
        if et in DUEL_FAMILY:
            out[et] = e.get("bondedEntityId")
    return out


def port_family(st, uid):
    """Le pendant OFFLINE, meme forme : `EffectsState.by_unit` filtre sur la famille DUEL."""
    eff = getattr(st, "effects", None)
    if eff is None:
        return {}
    out = {}
    for e in eff.by_unit.get(int(uid), []):
        if not e.consumed and e.effect_type is not None and int(e.effect_type) in DUEL_FAMILY:
            out[int(e.effect_type)] = getattr(e, "bonded", None)
    return out


def port_forced(st, uid):
    from engine.runner.components import ForcedAttackTargetsComponent
    e = st.get_entity(int(uid))
    c = e.get_component(ForcedAttackTargetsComponent) if e is not None else None
    return sorted(c.get()) if c is not None else []


# ------------------------------------------------------------------------------------------------
# --step cast
# ------------------------------------------------------------------------------------------------
def measure_cast(sid):
    """NATIF puis PORT, sur le MEME etat de depart. Rend le dict que lit
    `tests/engine/runner/test_549_holy_duel_live.py` (le probe MESURE, le test GARDE)."""
    from engine.runner.abilities.handler import ABILITY_CLASSES, AbilityHandler
    from engine.runner.messages import ActiveAbilityMessage
    from engine.entities.effects.magnitude import ability_var
    from engine.runner.components import OwnerComponent, StatsComponent

    print("1050 dans `ABILITY_CLASSES` : %s" % (HOLY_DUEL in ABILITY_CLASSES))
    ctx = B.build_montage(sid, mode="proche", taunter=B.HOLY_DUELIST)
    champ, victim = ctx["taunter"], ctx["victim"]
    try:
        print("placement : champion %s  victime %s  (dist %d)"
              % (ctx["placed"]["taunter"], ctx["placed"]["victim"],
                 hexgeo.distance(ctx["placed"]["taunter"], ctx["placed"]["victim"])))
        # etat AVANT le cast -- c'est de la que le PORT partira
        board, dv0, ob0, cs0 = R1._snapshot(sid, ctx["rid"])
        st = R1._seeded_state(sid, ctx["rid"], board, dv0, ob0, cs0)
        hp0 = PR.hp_of(sid, ctx["rid"])
        # ---- face NATIVE ----
        res_live = B.cast_taunt(ctx, ability=HOLY_DUEL)
        dv = PR.rpc(sid, "decisionView", {"runnerId": ctx["rid"], "maxRank": 1,
                                          "allAbilities": True}, 90)
        hp1 = PR.hp_of(sid, ctx["rid"])
        nat_v, nat_c = live_family(dv, victim), live_family(dv, champ)
        nat_dmg = (hp0[victim][0] - hp1[victim][0]) if hp0.get(victim) and hp1.get(victim) else None
        nat_hits = _live_hits(res_live, victim)
        print("[NATIF] cible    %s" % (sorted(nat_v.items()),))
        print("[NATIF] champion %s" % (sorted(nat_c.items()),))
        print("[NATIF] degat de l'attaque normale du cast : %s  (par coup : %s)"
              % (nat_dmg, nat_hits))
    finally:
        PR.dispose(sid, ctx["rid"])

    # ---- face PORT, sur l'etat capture AVANT le cast ----
    p_hp0 = R1._hp(st, victim)
    # Le CHEMIN REEL : le visiteur de message, pas un appel direct a `execute_behaviour` -- c'est
    # lui qui portait le no-op silencieux.
    h = AbilityHandler(st)
    h.visit_ActiveAbilityMessage(ActiveAbilityMessage(
        caster_id=int(champ), target_id=int(victim), ability_type=HOLY_DUEL))
    res = h.last or {}
    p_hp1 = R1._hp(st, victim)
    port_v, port_c = port_family(st, victim), port_family(st, champ)
    port_dmg = (p_hp0 - p_hp1) if (p_hp0 is not None and p_hp1 is not None) else None
    print("[PORT ] retour   %s" % ({k: res.get(k) for k in ("ability", "ported", "dsl")},))
    print("[PORT ] cible    %s   forcedTargets=%s" % (sorted(port_v.items()), port_forced(st, victim)))
    print("[PORT ] champion %s   forcedTargets=%s" % (sorted(port_c.items()), port_forced(st, champ)))
    atk = (res or {}).get("attack") or {}
    inner = atk.get("attack") if isinstance(atk.get("attack"), dict) else atk
    print("[PORT ] degat de l'attaque normale du cast : %s  (par coup : %s)"
          % (port_dmg, (inner or {}).get("per_hit_health")))
    print("[PORT ] payload attaque : %s"
          % ({k: v for k, v in (inner or {}).items()
              if k in ("hits", "min", "max", "lo", "hi", "pierce", "profile", "weapon",
                       "base_min", "base_max", "mods", "crit")},))
    # ETAGE PAR ETAGE : la contribution que 1092 verse dans l'accumulateur ATTAQUANT, relue sur
    # l'etat POST-cast (l'effet y est, bonde a la victime).
    from engine.runner.damage_model import attacker_modifiers, defender_modifiers
    m_att, _ = attacker_modifiers(st, int(champ), None, target_id=int(victim),
                                  is_ranged=False, damage_profile="Power")
    m_def, _ = defender_modifiers(st, int(victim), None, is_melee=True,
                                  damage_profile="Power", attacker_id=int(champ))
    print("[PORT ] modifiers attaquant %s" % (m_att,))
    print("[PORT ] modifiers defenseur %s" % (m_def,))
    # CONTROLE : le MEME accumulateur contre une TIERCE unite ennemie (le gate `AreEqual` doit
    # rendre l'additif du duel INERTE). `None` = aucune tierce dans ce montage.
    # N'IMPORTE QUELLE autre unite fait le controle : le gate lu est `AreEqual(Target@0x60,
    # BondedEntityFromEffect)`, une egalite d'IDENTITE -- il n'y a AUCUN gate d'equipe a satisfaire,
    # et c'est precisement ce qu'on verifie (l'additif doit disparaitre sur toute cible != bonde).
    tierce = next((int(uid) for uid, e in st.entities.items()
                   if int(uid) not in (int(champ), int(victim))
                   and e.get_component(OwnerComponent) is not None
                   and e.get_component(StatsComponent) is not None), None)
    det_tierce = None
    if tierce is not None:
        m_t, _ = attacker_modifiers(st, int(champ), None, target_id=tierce,
                                    is_ranged=False, damage_profile="Power")
        det_tierce = list(m_t.details)
        print("[PORT ] modifiers attaquant vs TIERCE u%s : %s" % (tierce, det_tierce))
    # La magnitude ATTENDUE, re-derivee de la MEME source que le port : `extraDmg[level]` du
    # gameconfig, scale par le multiplicateur de rarete du CHAMPION.
    _sc = st.get_entity(int(champ)).get_component(StatsComponent)
    _cctx = _sc.ctx if _sc is not None else None
    _lvl = getattr(_cctx, "active_ability_level", None)
    _mult = int(getattr(_cctx, "ability_variables_multiplier", 100) or 100)
    expected_extra = int(ability_var("HolyDuel", "extraDmg", _lvl, multiplier_pct=_mult) or 0)
    print("[PORT ] extraDmg attendu : niveau=%s mult=%s%% -> %s" % (_lvl, _mult, expected_extra))

    print("")
    print("=" * 96)
    rc = 0
    # 1. la CIBLE porte 1091 (bonde au champion) + le composite 27 et ses trois enfants
    attendu_v = {HOLY_DUEL_TAUNT} | set(TAUNTED_FAMILY)
    for lbl, got in (("NATIF", nat_v), ("PORT", port_v)):
        manque = attendu_v - set(got)
        if manque:
            print("  ROUGE [%s] la CIBLE ne porte pas %s" % (lbl, sorted(manque)))
            rc = 1
    # 2. le CHAMPION porte 27 + enfants + 1092 + 1093
    attendu_c = set(TAUNTED_FAMILY) | {HOLY_DUEL_EXTRA_DMG, HOLY_DUEL_DMG_REDUCTION}
    for lbl, got in (("NATIF", nat_c), ("PORT", port_c)):
        manque = attendu_c - set(got)
        if manque:
            print("  ROUGE [%s] le CHAMPION ne porte pas %s" % (lbl, sorted(manque)))
            rc = 1
    # 3. les bonds sont CROISES cote port (le natif ne publie le bonded que si le capteur est charge)
    if port_v.get(HOLY_DUEL_TAUNT) != champ:
        print("  ROUGE [PORT] 1091 sur la cible : bonded=%s attendu %s"
              % (port_v.get(HOLY_DUEL_TAUNT), champ))
        rc = 1
    for et in (27, HOLY_DUEL_EXTRA_DMG, HOLY_DUEL_DMG_REDUCTION):
        if port_c.get(et) != victim:
            print("  ROUGE [PORT] %d sur le champion : bonded=%s attendu %s"
                  % (et, port_c.get(et), victim))
            rc = 1
    # 4. le taunt est OPPOSABLE : la cible ne peut attaquer que le champion, et reciproquement
    if port_forced(st, victim) != [champ] or port_forced(st, champ) != [victim]:
        print("  ROUGE [PORT] cibles forcees non croisees : cible=%s champion=%s"
              % (port_forced(st, victim), port_forced(st, champ)))
        rc = 1
    # 5. le DEGAT : l'attaque normale du cast doit porter le `+extraDmg` DES ce coup
    print("  degat cast : natif=%s (%s) port=%s" % (nat_dmg, nat_hits, port_dmg))
    if nat_dmg is None or port_dmg is None:
        print("  INCONCLUSIF : un des deux degats n'est pas lisible")
        rc = 1
    elif int(nat_dmg) != int(port_dmg):
        print("  ROUGE : le degat de l'attaque du cast diverge (ecart %d)" % (nat_dmg - port_dmg))
        rc = 1
    if rc == 0:
        print("  => les deux faces posent la MEME famille sur les MEMES porteurs, bonds croises,")
        print("     cibles forcees croisees.")
    return {"rc": rc, "champ": int(champ), "victim": int(victim),
            "nat_victim": sorted(nat_v), "nat_champ": sorted(nat_c),
            "port_victim": sorted(port_v), "port_champ": sorted(port_c),
            "port_bond_victim": port_v, "port_bond_champ": port_c,
            "port_forced_victim": port_forced(st, victim),
            "port_forced_champ": port_forced(st, champ),
            "nat_dmg": nat_dmg, "port_dmg": port_dmg, "nat_hits": nat_hits,
            "port_att_details": list(m_att.details),
            "port_att_details_tierce": det_tierce,
            "expected_extra_dmg": expected_extra}


def step_cast(sid):
    return measure_cast(sid)["rc"]


# ------------------------------------------------------------------------------------------------
# --step adjacency : le trigger (c), NATIF *et* PORT
# ------------------------------------------------------------------------------------------------
def adjacency_bras(sid, mode):
    from engine.runner.events import EventBus
    from engine.runner.operations.displace import DisplaceUnitOperation
    from engine.runner.components import PositionComponent

    ctx = B.build_montage(sid, mode=mode, taunter=B.HOLY_DUELIST)
    champ, victim = ctx["taunter"], ctx["victim"]
    try:
        B.cast_taunt(ctx, ability=HOLY_DUEL)
        dv = PR.rpc(sid, "decisionView", {"runnerId": ctx["rid"], "maxRank": 1,
                                          "allAbilities": True}, 90)
        pos = PR.positions(dv)
        nat_before = sorted(live_family(dv, victim))
        nat_before_c = sorted(live_family(dv, champ))
        d_before = hexgeo.distance(pos[victim], pos[champ])
        if HOLY_DUEL_TAUNT not in nat_before:
            raise RuntimeError("montage : 1091 n'est pas pose (%s)" % (nat_before,))
        board, dv1, ob1, cs1 = R1._snapshot(sid, ctx["rid"])
        st = R1._seeded_state(sid, ctx["rid"], board, dv1, ob1, cs1)
        B.cast_push(ctx)
        dv = PR.rpc(sid, "decisionView", {"runnerId": ctx["rid"], "maxRank": 1,
                                          "allAbilities": True}, 90)
        pos = PR.positions(dv)
        nat_after = sorted(live_family(dv, victim))
        nat_after_c = sorted(live_family(dv, champ))
        d_after = hexgeo.distance(pos[victim], pos[champ])
        moved = pos[victim] != ctx["placed"]["victim"]
    finally:
        PR.dispose(sid, ctx["rid"])

    def _pos(uid):
        e = st.get_entity(int(uid))
        pc = e.get_component(PositionComponent) if e is not None else None
        return None if pc is None else (pc.col, pc.row)

    p_before = sorted(port_family(st, victim))
    p_before_c = sorted(port_family(st, champ))
    r = DisplaceUnitOperation(int(ctx["pusher"]), int(victim)).execute(st, EventBus())
    p_after = sorted(port_family(st, victim))
    p_after_c = sorted(port_family(st, champ))
    print("[%s/NATIF] pousse=%s dist %d -> %d  cible %s -> %s  champion %s -> %s"
          % (mode, moved, d_before, d_after, nat_before, nat_after, nat_before_c, nat_after_c))
    print("[%s/PORT ] pousse=%s dist %d -> %d  cible %s -> %s  champion %s -> %s"
          % (mode, r.get("moved"), d_before, hexgeo.distance(_pos(victim), _pos(champ)),
             p_before, p_after, p_before_c, p_after_c))
    return {"mode": mode, "moved": moved, "nat_before": nat_before, "nat_after": nat_after,
            "nat_before_c": nat_before_c, "nat_after_c": nat_after_c,
            "port_moved": bool(r.get("moved")), "port_before": p_before, "port_after": p_after,
            "port_before_c": p_before_c, "port_after_c": p_after_c}


def step_adjacency(sid):
    out = {m: adjacency_bras(sid, m) for m in ("eloigne", "proche")}
    e, p = out["eloigne"], out["proche"]
    print("")
    print("=" * 96)
    print("VERDICT (c) `get_Adjacent` -- le duel s'arrete quand les duellistes se separent")
    rc = 0
    if not (e["moved"] and p["moved"] and e["port_moved"] and p["port_moved"]):
        print("  INCONCLUSIF : un des quatre push n'a pas eu lieu.")
        return 1
    if HOLY_DUEL_TAUNT in e["nat_after"] or HOLY_DUEL_TAUNT not in p["nat_after"]:
        print("  ROUGE [NATIF] attendu : tombe ELOIGNE, survit PROCHE ; obtenu %s / %s"
              % (e["nat_after"], p["nat_after"]))
        rc = 1
    if HOLY_DUEL_TAUNT in e["port_after"] or HOLY_DUEL_TAUNT not in p["port_after"]:
        print("  ROUGE [PORT ] attendu : tombe ELOIGNE, survit PROCHE ; obtenu %s / %s"
              % (e["port_after"], p["port_after"]))
        rc = 1
    # CASCADE : le retrait du parent emporte les enfants des DEUX cotes du duel -- et c'est le
    # CROISEMENT de porteur (`_remove_sub_effects` balaye aussi l'entite bondee) qui est confronte
    # ici : le NATIF vide bien le CHAMPION, pas seulement la cible.
    for lbl, after_v, after_c in (("NATIF", e["nat_after"], e["nat_after_c"]),
                                  ("PORT ", e["port_after"], e["port_after_c"])):
        if after_v or after_c:
            print("  ROUGE [%s] bras ELOIGNE : des effets survivent au retrait de 1091 "
                  "(cible=%s champion=%s)" % (lbl, after_v, after_c))
            rc = 1
    for lbl, after_c in (("NATIF", p["nat_after_c"]), ("PORT ", p["port_after_c"])):
        if not after_c:
            print("  ROUGE [%s] bras PROCHE : le champion a perdu ses effets de duel" % lbl)
            rc = 1
    if rc == 0:
        print("  => NATIF et PORT concordent sur les deux bras, et la cascade vide les DEUX")
        print("     porteurs (le composite, ses enfants, 1092 et 1093).")
    return rc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", default="all", choices=["cast", "adjacency", "all"])
    args = ap.parse_args()
    sid = _resolve_session()
    rc = 0
    if args.step in ("cast", "all"):
        rc |= step_cast(sid)
    if args.step in ("adjacency", "all"):
        rc |= step_adjacency(sid)
    return rc


if __name__ == "__main__":
    sys.exit(main())
