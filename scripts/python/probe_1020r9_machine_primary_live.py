#!/usr/bin/env python
"""#1020-r9 -- la branche `MachinePrimaryAbilityIsBlocked`, CONFRONTEE au canal live.

Trois choses a MESURER, et aucune n'est une opinion :

  1. le DISCRIMINANT `kind == EntityKind.Machine` est-il porte ? -> `machineId` present sur
     `decisionView.mows[]` et absent de TOUTE ligne `.units[]` ;
  2. `ActiveAbilityComponent+0x30` est-il derivable ? -> l'INDICE 0 de la liste d'actives, que
     `MachineFactory$$AddConfiguredAbilities` y ecrit, et que le canal doit rendre dans le MEME
     ordre que `gameconfig.units.<id>.activeAbilities` ;
  3. la separation REGRESSE-t-elle ? -> le verdict de `can_use_ability` sur la MoW REELLE, compare
     au bras d'AVANT (le repli `not blockers`), ability par ability, avec et sans bloqueur.

Usage : python probe_1020r9_machine_primary_live.py --state-file <absolu> [--runner N]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import gameconfig as GC                                        # noqa: E402
from engine import battle_query as BQ                          # noqa: E402
from rl_collect_batch import _resolve_session, _rpc            # noqa: E402


def _avant(unit, ability):
    """Le bras d'AVANT : deux branches, la machine FONDUE dans `ActiveAbilitiesAreBlocked`."""
    blockers = BQ._active_ability_blockers(unit)
    if (ability or {}).get("kind") == "normal":
        return not any(b["include_normal_attack"] for b in blockers)
    return not blockers


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True)
    ap.add_argument("--runner", type=int, default=None)
    args = ap.parse_args()

    rid = args.runner
    if rid is None:
        rid = json.load(open(args.state_file, encoding="utf-8")).get("runnerId")
    if rid is None:
        print("PAS MESURE : aucun runnerId")
        return 2

    sid = _resolve_session()
    dv = _rpc(sid, "decisionView", [{"runnerId": int(rid), "allAbilities": True}], 60)["result"]
    mows = dv.get("mows") or []
    units = dv.get("units") or []
    if not mows:
        print("PAS MESURE : aucune MACHINE OF WAR dans ce runner (monter avec `--p-mow <id>`)")
        return 2

    # --- 1. le DISCRIMINANT -------------------------------------------------------------------
    avec = [u for u in units if u.get("machineId") is not None]
    print("1. DISCRIMINANT `EntityKind.Machine`")
    print("   mows portant `machineId`  : %d / %d" % (
        sum(1 for m in mows if m.get("machineId") is not None), len(mows)))
    print("   units portant `machineId` : %d / %d  %s" % (
        len(avec), len(units), "(attendu 0)" if not avec else "<-- ANOMALIE"))

    # --- 2. `+0x30` = l'INDICE 0, recoupe par le gameconfig ------------------------------------
    print("2. `ActiveAbilityComponent+0x30` (l'INDICE 0 de la liste d'actives)")
    concordants = 0
    for m in mows:
        vis = m.get("visualId")
        canal = [a for a in (m.get("abilities") or []) if a.get("kind") in ("active", "granted")]
        etiquetees = [a for a in (m.get("abilities") or []) if a.get("kind") == "machinePrimary"]
        cfg = ((GC.unit(vis) or {}).get("activeAbilities") or []) if vis else []
        port = BQ.machine_primary_ability_id(m)
        attendu_nom = cfg[0] if cfg else None
        print("   %s : canal=%s" % (vis, [(a.get("id"), a.get("name")) for a in canal]))
        print("        gameconfig.activeAbilities = %s" % (cfg,))
        print("        etiquetees `machinePrimary` = %d  (0 = le DEDUP les efface, cf. #1020-r10)"
              % len(etiquetees))
        print("        machine_primary_ability_id -> %s" % port)
        nom_port = next((a.get("name") for a in canal if a.get("id") == port), None)
        ok = (attendu_nom is not None and nom_port == attendu_nom)
        concordants += int(ok)
        print("        CONCORDANCE canal <-> gameconfig : %s (%s vs %s)"
              % ("OUI" if ok else "NON", nom_port, attendu_nom))

    # --- 3. NON-REGRESSION : la separation rend-elle le MEME verdict ? -------------------------
    print("3. NON-REGRESSION -- separation vs repli, ability par ability")
    ecarts = 0
    total = 0
    etats = [("sans bloqueur", [])]
    etats += [("bloqueur %d (%s)" % (et, spec["name"]), [{"effectType": et}])
              for et, spec in BQ.ACTIVE_ABILITY_BLOCKER_EFFECTS.items()]
    for m in mows:
        for libelle, effs in etats:
            porteur = {**m, "effects": effs}
            for a in (m.get("abilities") or []):
                total += 1
                apres = BQ.can_use_ability(porteur, a)
                avant = _avant(porteur, a)
                if apres != avant:
                    ecarts += 1
                    print("   ECART %s / ability %s (%s) : avant=%s apres=%s"
                          % (libelle, a.get("id"), a.get("kind"), avant, apres))
    print("   %d comparaisons, %d ecart(s)  (attendu 0 : les trois membres portent "
          "`include_machine_primary_ability = 1`)" % (total, ecarts))

    print("\nVERDICT : discriminant=%s  concordance=%d/%d  ecarts=%d"
          % ("OK" if not avec else "ANOMALIE", concordants, len(mows), ecarts))
    return 0 if (not avec and concordants == len(mows) and ecarts == 0) else 1


if __name__ == "__main__":
    raise SystemExit(main())
