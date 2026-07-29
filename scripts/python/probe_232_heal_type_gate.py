"""probe #232 -- le gate `IsAffectedByHealType` cote DECISION (engine/playbook/noncomparable/heals.py).

MESURE (offline, aucun RPC) le GISEMENT de divergence entre l'ancien critere du module
(« le trait `Mechanical` est-il dans le kit gameconfig ? ») et le mirror natif
`IdunBattle.Entities.UnitExtensions$$IsAffectedByHealType(unit, healType)` :

    if (HasTrait(unit, 0x421 = AffectedByHealAndRepair)) return true;
    if (healType == 0 &&  IsMechanical(unit)) return false;      // Heal   : pas les mecaniques
    if (healType == 1 && !IsMechanical(unit)) return false;      // Repair : QUE les mecaniques
    return true;

`IdunBattle.Entities.UnitExtensions$$IsMechanical` = HasTrait(Mechanical=5) OU
HasTrait(LivingMetal=0x3e8=1000) OU HasTrait(Vehicle=0x405=1029).

Etapes :
  0. inventaire des trois traits mecaniques + de 0x421 dans le gameconfig (669 unites) ;
  1. les unites que l'ANCIEN critere classait a l'envers (LivingMetal/Vehicle sans Mechanical),
     ventilees par kind (lineup / npc / summons) -> le gisement CONFRONTABLE ;
  2. verdicts des 6 gates portes sur un NCContext synthetique (sans Scene) : la table
     unite x (heal 0 / repair 1) que consomment les quatre playbooks.

Usage :  python probe_232_heal_type_gate.py [--limit N]
Sortie ASCII pure (cp1252).
"""
from __future__ import annotations

import argparse
import sys

import gameconfig as GC
from engine.entities.traits.unit_trait import UnitTrait, unit_trait_names
from engine.playbook.noncomparable._base import NCContext
from engine.playbook.noncomparable.heals import _affected_by_heal_type

MECH_TRAITS = (UnitTrait.Mechanical, UnitTrait.LivingMetal, UnitTrait.Vehicle)


def _all_units() -> list:
    """[(unitId, kind)] de TOUT le gameconfig (lineup + npc + summons)."""
    out = []
    for kind, ids in (GC.all_unit_ids() or {}).items():
        for uid in ids:
            out.append((uid, kind))
    return sorted(out)


def _bare_ctx() -> NCContext:
    """NCContext MINIMAL sans Scene : `_affected_by_heal_type` retombe alors sur la borne
    statique `entity_trait_names(None, visualId)` = kit gameconfig (+ grande-alliance)."""
    return NCContext(uid=0, origin=None, reach_nc=[], epos=[], fpos=[], plan={}, hp_cur_by_id={})


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=40, help="lignes de detail max par section")
    args = ap.parse_args()

    units = _all_units()
    print("=== etape 0 : inventaire des traits du gate (gameconfig, %d unites) ===" % len(units))
    counts = {}
    for t in list(MECH_TRAITS) + [UnitTrait.AffectedByHealAndRepair]:
        n = sum(1 for uid, _ in units if t.name in unit_trait_names(uid))
        counts[t.name] = n
        print("  %-24s (id %5d) : %4d unites" % (t.name, int(t), n))

    print()
    print("=== etape 1 : gisement -- l'ancien critere (trait `Mechanical` seul) se trompe ===")
    wrong = []
    for uid, kind in units:
        names = unit_trait_names(uid)
        old_mech = UnitTrait.Mechanical.name in names
        new_mech = any(t.name in names for t in MECH_TRAITS)
        has421 = UnitTrait.AffectedByHealAndRepair.name in names
        if old_mech != new_mech or has421:
            extra = [t.name for t in MECH_TRAITS[1:] if t.name in names]
            wrong.append((uid, kind, ",".join(extra) or "-", has421))
    print("  %d unites divergent (IsMechanical vrai SANS le trait `Mechanical`, ou 0x421 present)"
          % len(wrong))
    by_kind = {}
    for uid, kind, extra, has421 in wrong:
        by_kind.setdefault(kind, []).append(uid)
    for kind in sorted(by_kind):
        print("    kind=%-8s : %3d" % (kind, len(by_kind[kind])))
    for uid, kind, extra, has421 in wrong[:args.limit]:
        print("      %-28s kind=%-8s traits+=%-22s 0x421=%s" % (uid, kind, extra, has421))
    if len(wrong) > args.limit:
        print("      ... (%d de plus)" % (len(wrong) - args.limit))

    print()
    print("=== etape 2 : verdict des gates portes (NCContext sans Scene = borne statique) ===")
    ctx = _bare_ctx()
    print("  %-28s %-8s %-9s %-9s %s" % ("unite", "kind", "heal(0)", "repair(1)", "old(non-Mech)"))
    shown = 0
    for uid, kind, extra, has421 in wrong:
        obs = {"squadId": None, "visualId": uid}
        h0 = _affected_by_heal_type(ctx, obs, 0)
        h1 = _affected_by_heal_type(ctx, obs, 1)
        old = UnitTrait.Mechanical.name not in unit_trait_names(uid)
        print("  %-28s %-8s %-9s %-9s %s" % (uid, kind, h0, h1, old))
        shown += 1
        if shown >= args.limit:
            print("  ... (%d de plus)" % (len(wrong) - shown))
            break
    print()
    print("LECTURE : colonne heal(0) FALSE + old TRUE = l'ancien port comptait cette unite comme")
    print("          soignable (Rites/RevitalizingMalignancy) alors que le natif la REFUSE ;")
    print("          colonne repair(1) TRUE + old TRUE = le gate repair de DefendTheDivineWork")
    print("          rendait l'ability non evaluee alors que le natif l'accepte.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
