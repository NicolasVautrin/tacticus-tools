"""probe #572-r1 -- LE MAXIMUM DE PV EFFECTIF : un stat-mod `StatType.Health` releve-t-il le meme
reservoir cote port que cote natif ?

CE QUI EST MESURE, ET POURQUOI CE N'EST PAS LE MEME CANAL QUE #572

#572 a confronte les PV **COURANTS** (`+9970`, feuille `ChangeStat(Owner, Health, mode Add)`) et
les a trouves bit-exacts. Il n'a PAS confronte le **MAXIMUM**, qui vient de l'AUTRE feuille --
`AddStaticStatModifierEffectToOwner(0x4e3, StatType.Health, extraHp)`. Le natif l'envoie dans
`IdunBattle.Entities.UnitExtensions$$ApplyStatModifier` **case 5**, qui route vers
`IdunBattle.Entities.Components.FillUpStatComponent$$ApplyModifier` -- donc dans le
`ValueModification` (+0x28) du `HealthComponent` lui-meme, d'ou
`get_CurrentMaximumValue()` = `base + modTotal` le relit. Le port, lui, ecrivait dans
`UnitStats.components[5]`, **que rien ne relit pour les PV**.

LE CANAL DE MESURE EST LE POINT DELICAT, ET IL Y EN A **DEUX QUI NE DISENT PAS LA MEME CHOSE** :

  * `observeBattle.hpMax` lit le champ BRUT `FillUpStatComponent+0x14`
    (`game/match-state.ts::COMP_FIELD.hpMax`) -- la BASE. Il ne bouge PAS quand une modification
    est posee, donc il ne peut pas mesurer ce residu ;
  * `combatSnapshot.healthMax` invoque `GetStat(unit, StatType.Health, StatPart.Maximum)`
    (`rpc-snapshot.ts`, #45b'), c'est-a-dire `get_CurrentMaximumValue()` -- le MAXIMUM EFFECTIF.

C'est le SECOND qu'il faut lire. Un banc qui lirait le premier verrait « natif inchange, port
inchange » et conclurait a un accord ALORS QUE LE RESIDU EST INTACT -- exactement le regime
degenere qu'il faut refuser.

Le montage (gate OUVERT de `1061 UnbreakableDuty`, deux allies Imperial+Hero sacrifies) est celui
de #572, reutilise tel quel : `probe_572_unbreakable_duty.build_montage`.

Usage :
    python probe_572r1_hpmax_effectif.py
ASCII only.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import probe_572_unbreakable_duty as P572                            # noqa: E402
import probe_112_darkangels as PR                                    # noqa: E402
import probe_462_r4b_r1_terminator_commanded_attack as R1            # noqa: E402
from rl_collect_batch import _resolve_session                        # noqa: E402

UNBREAKABLE_DUTY = P572.UNBREAKABLE_DUTY


def health_max(cs: dict, uid: int):
    """`combatSnapshot.units[].healthMax` = `GetStat(unit, StatType.Health, StatPart.Maximum)`, donc
    `FillUpStatComponent$$get_CurrentMaximumValue()`. `None` = capteur absent -- et on le DIT au
    lieu de rendre un zero (sans lui, ce probe ne mesure rien)."""
    for u in (cs.get("units") or []):
        i = u.get("squadId", u.get("entityId"))
        if i is not None and int(i) == int(uid):
            return u.get("healthMax")
    return None


def port_max(st, uid: int):
    """`HealthComponent.hp_max` cote port = `current_maximum_value()` depuis #572-r1."""
    from engine.runner.components import HealthComponent
    e = st.get_entity(int(uid))
    hc = e.get_component(HealthComponent) if e is not None else None
    return None if hc is None else hc.hp_max


def port_max_parts(st, uid: int):
    """Les TROIS parts que le natif separe et que le port confondait : `Current`, `Maximum`
    (= base + modTotal) et `Initial` (= le champ brut +0x10)."""
    from engine.entities.stats import StatPart
    from engine.runner.components import HealthComponent
    e = st.get_entity(int(uid))
    hc = e.get_component(HealthComponent) if e is not None else None
    if hc is None:
        return None
    return {"current": hc.get_stat_part(StatPart.CURRENT),
            "maximum": hc.get_stat_part(StatPart.MAXIMUM),
            "initial": hc.get_stat_part(StatPart.INITIAL),
            "modification": hc.get_stat_part(StatPart.MODIFICATION)}


def mesure(sid) -> dict:
    from engine.runner.abilities.handler import AbilityHandler
    from engine.runner.messages import ActiveAbilityMessage

    ctx = P572.build_montage(sid, with_sacrifices=True)
    caster, ally, foe = ctx["caster"], ctx["ally"], ctx["foe"]
    out = {"rid": ctx["rid"], "caster": caster}
    try:
        dv = PR.rpc(sid, "decisionView", {"runnerId": ctx["rid"], "maxRank": 1,
                                          "allAbilities": True}, 90)
        owner = P572._owner_of(dv, caster)
        mine, theirs = P572._my_player_ids(dv)
        P572._pass_turn_to(sid, ctx["rid"], theirs)      # seule l'IA peut frapper MES unites
        killed = [(sac, P572._kill(sid, ctx["rid"], sac, owner, verbose=False))
                  for sac in ctx["sacs"]]
        out["sacrifices"] = killed
        if not all(ok for _s, ok in killed):
            return out                                    # montage rate -- on le DIT
        P572._pass_turn_to(sid, ctx["rid"], mine)

        # ---- ETAT DE DEPART COMMUN, capture juste AVANT le cast --------------------------------
        board, dv0, ob0, cs0 = R1._snapshot(sid, ctx["rid"])
        st = R1._seeded_state(sid, ctx["rid"], board, dv0, ob0, cs0)
        out["natif_max_avant"] = health_max(cs0, caster)
        out["port_max_avant"] = port_max(st, caster)
        out["port_parts_avant"] = port_max_parts(st, caster)
        out["attendu"] = P572.expected_vars(st, caster)

        # ---- face NATIVE ------------------------------------------------------------------------
        legal = PR.legal_from_here(sid, ctx["rid"], caster, UNBREAKABLE_DUTY)
        tgt = caster if caster in legal else (ally if ally in legal else None)
        if tgt is None:
            out["cast_refuse"] = legal
            return out
        res = PR.cast(sid, ctx["rid"], caster, tgt, UNBREAKABLE_DUTY)
        if not res.get("ok"):
            out["cast_refuse"] = str(res)[:200]
            return out
        _b, _d1, ob1, cs1 = R1._snapshot(sid, ctx["rid"])
        out["natif_max_apres"] = health_max(cs1, caster)
        # Le canal BRUT, publie a titre de CONTRE-LECTURE : il ne doit PAS bouger (c'est `+0x14`).
        out["natif_hpmax_brut_avant"] = _obs_hpmax(ob0, caster)
        out["natif_hpmax_brut_apres"] = _obs_hpmax(ob1, caster)
    finally:
        PR.dispose(sid, ctx["rid"])

    # ---- face PORT, sur l'etat capture AVANT le cast --------------------------------------------
    h = AbilityHandler(st)
    h.visit_ActiveAbilityMessage(ActiveAbilityMessage(
        caster_id=int(caster), target_id=int(tgt), ability_type=UNBREAKABLE_DUTY))
    out["port_max_apres"] = port_max(st, caster)
    out["port_parts_apres"] = port_max_parts(st, caster)
    return out


def _obs_hpmax(ob: dict, uid: int):
    for u in (ob.get("units") or []):
        i = u.get("squadId", u.get("entityId"))
        if i is not None and int(i) == int(uid):
            return u.get("hpMax")
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.parse_args()
    sid = _resolve_session()
    m = mesure(sid)
    print("[572r1] runner=%s caster=%s sacrifices=%s"
          % (m["rid"], m["caster"], m.get("sacrifices")))
    if m.get("cast_refuse") is not None:
        print("[572r1] MONTAGE INVALIDE : cast refuse -- %s" % (m["cast_refuse"],))
        return 2
    if "natif_max_apres" not in m:
        print("[572r1] MONTAGE INVALIDE : les sacrifices n'ont pas ete tues")
        return 2
    extra_hp = int((m.get("attendu") or {}).get("extraHp") or 0)
    print("[572r1] extraHp attendu (config, level x mult) = %s" % extra_hp)
    print("[572r1] MAXIMUM EFFECTIF (combatSnapshot.healthMax = GetStat(Health, StatPart.Maximum))")
    print("        natif : %s -> %s   (delta %s)"
          % (m["natif_max_avant"], m["natif_max_apres"],
             None if (m["natif_max_avant"] is None or m["natif_max_apres"] is None)
             else m["natif_max_apres"] - m["natif_max_avant"]))
    print("        port  : %s -> %s   (delta %s)"
          % (m["port_max_avant"], m["port_max_apres"],
             None if (m["port_max_avant"] is None or m["port_max_apres"] is None)
             else m["port_max_apres"] - m["port_max_avant"]))
    print("[572r1] CONTRE-LECTURE, canal BRUT (observeBattle.hpMax = FillUpStatComponent+0x14)")
    print("        natif : %s -> %s   (il ne DOIT pas bouger : une modification n'ecrit pas +0x14)"
          % (m["natif_hpmax_brut_avant"], m["natif_hpmax_brut_apres"]))
    print("[572r1] parts du port  avant=%s" % (m["port_parts_avant"],))
    print("[572r1] parts du port  apres=%s" % (m["port_parts_apres"],))
    rc = 0
    nd = (None if (m["natif_max_avant"] is None or m["natif_max_apres"] is None)
          else m["natif_max_apres"] - m["natif_max_avant"])
    pd = (None if (m["port_max_avant"] is None or m["port_max_apres"] is None)
          else m["port_max_apres"] - m["port_max_avant"])
    if nd is None or pd is None:
        print("  NON MESURE : un des deux canaux est absent (capteur ou composant)")
        return 2
    if nd != extra_hp:
        print("  ROUGE : le natif n'a pas releve son maximum de `extraHp` (delta %s != %s)"
              % (nd, extra_hp))
        rc = 1
    if pd != nd:
        print("  ROUGE : delta de MAXIMUM natif=%s port=%s -- le port ecrit dans un autre reservoir"
              % (nd, pd))
        rc = 1
    if m["natif_hpmax_brut_avant"] != m["natif_hpmax_brut_apres"]:
        print("  ROUGE : le canal BRUT +0x14 a bouge -- la lecture du residu est a revoir")
        rc = 1
    if rc == 0:
        print("  => le MAXIMUM EFFECTIF concorde (%s des deux cotes), et le canal brut n'a pas "
              "bouge : la modification vit bien dans le composant fill-up." % nd)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
