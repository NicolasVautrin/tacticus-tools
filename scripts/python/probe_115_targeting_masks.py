"""#115 -- MESURE des `TARGETING_OPTIONS` posees sur les actives DarkAngels / Aeldari / WorldEaters.

Confronte, CIBLE PAR CIBLE et ABILITY PAR ABILITY, le gate de cible OFFLINE
(`engine/runner/abilities/targeting.py` arme par le masque `TARGETING_OPTIONS` de chaque classe)
a l'ORACLE NATIF `abilityReason(casterId, abilityType, targetId)` (masque `TargetingRule` rendu par
`IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason` + `...GetInvalidCasterReason`).

CONTRAT DE FIDELITE (identique a `tests/engine/runner/test_ability_target_gate_live.py`) :

    natif == 0   =>  port == 0          STRICT (le port n'invente jamais un refus)
    natif != 0   =>  port == natif      (regle PORTEE)
                 ou  port == 0          (regle NON PORTEE -> permissif, documente)
    jamais       :   port != 0 et port != natif

Usage (session warmee, runner deja construit) :
    python probe_115_targeting_masks.py --runner <rid>

ASCII only (console cp1252).
"""
from __future__ import annotations

import argparse
import json
import sys

import oracle_targeting as O
import rl_collect_batch as R

from engine.entities.pathfinding.board import Board
from engine.runner.abilities.handler import ABILITY_CLASSES
from engine.runner.abilities.targeting import is_invalid_target
from engine.runner.snapshot import load_state

# (abilityType, visualId du porteur) -- les 10 actives des 3 modules de faction.
CARRIERS = [
    (1150, "darkaTerminator", "PlasmaCannon"),
    (1092, "darkaAzrael", "DarkTalonStrike"),
    (1213, "darkaStormSpeeder", "DeathOnTheWind"),
    (1214, "darkaStormSpeeder", "Hailstrike"),
    (1103, "darkaHellblaster", "Supercharge"),
    (1140, "darkaAsmodai", "ExemplarOfHate"),
    (1189, "darkaCompanion", "CalibaniteGreatsword"),
    (1066, "eldarFarseer", "Executioner"),
    (1067, "eldarMauganRa", "HarvesterOfSouls"),
    (1131, "worldJakhal", "JakhalStimms"),
]


def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runner", type=int, required=True)
    a = ap.parse_args()
    sid = R._resolve_session()

    def rpc(method, body, timeout=90):
        return _unwrap(R._rpc(sid, method, [body], timeout=timeout))

    rid = a.runner
    dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True})
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    board = Board(bg["tiles"], adjacency="evenq")
    units = dec.get("units") or []
    alive = [u for u in units if u.get("alive")]
    by_vis = {}
    for u in units:
        by_vis.setdefault(u.get("visualId"), u)
    # MACHINES OF WAR : hors `decisionView.units` (`decisionView.mows`, cf. `_machine_rows`) ; la
    # cle d'acteur est `casterId` (entite Machine Type=6), c'est elle que `abilityReason`/
    # `applyAction{kind:"ability", casterId}` attendent.
    for m in (dec.get("mows") or []):
        if m.get("casterId") is not None:
            by_vis.setdefault(m.get("visualId"), {"id": m["casterId"],
                                                  "visualId": m.get("visualId")})
    print("[probe] runner=%d units=%d alive=%d" % (rid, len(units), len(alive)))
    print("[probe] visualIds: %s" % sorted(by_vis))

    wrong, exact, permissive, bloques = [], [], [], []
    for at, vis, name in CARRIERS:
        caster = by_vis.get(vis)
        if caster is None:
            print("  -- %-22s (%d) : porteur %s absent de ce runner" % (name, at, vis))
            continue
        klass = ABILITY_CLASSES.get(at)
        opts = getattr(klass, "TARGETING_OPTIONS", None)
        print("  == %-22s (%d) caster u%s rules=%s"
              % (name, at, caster["id"], "None" if opts is None else hex(opts.rules)))
        # LE CRAN D'ORACLE (#287-r9). `casterReason` etait DEJA lu plus bas (`natc`) -- et
        # seulement IMPRIME : aucune ligne de verdict ne le consultait. Or il ne depend PAS de la
        # cible : quand il vaut `TargetingRule.ValidRequest`, `AttackQuery$$GetInvalidTargetReason`
        # a refuse EN AMONT de la cascade et TOUS les `targetReason` de la boucle qui suit valent
        # `1`, quel que soit le masque. `1150 PlasmaCannon` porte `initialCooldownTurns = 1` : au
        # tour 1 ce probe confrontait donc un etage que le port ne traverse pas.
        # LA PARADE EST DE DEBLOQUER, PAS D'EXCLURE -- et l'echec du deblocage COMPTE comme faute.
        # ⚠ `rpc` local compte ses timeouts en SECONDES, le foyer les passe en MILLISECONDES.
        empeche = O.debloquer_oracle(lambda m, b, t=60000: rpc(m, b, max(30, int(t) // 1000)),
                                     rid, int(caster["id"]), at, jouer_adverse=False)
        if empeche:
            print("     ORACLE COURT-CIRCUITE, NON MESURE : %s" % empeche)
            bloques.append((name, at, empeche))
            continue
        for tgt in alive:
            r = rpc("abilityReason", {"runnerId": rid, "casterId": caster["id"],
                                      "abilityType": at, "targetId": tgt["id"]}, 60) or {}
            tr = r.get("targetReason") or {}
            cr = r.get("casterReason") or {}
            nat = int(tr.get("hex") or "0x0", 16)
            natc = int(cr.get("hex") or "0x0", 16)
            state = load_state(dec, ob, snap, board=board)
            port = is_invalid_target(state, int(caster["id"]), int(tgt["id"]), klass())
            row = (name, tgt["id"], tgt.get("visualId"), hex(nat), list(tr.get("reasons") or []),
                   hex(natc), hex(port))
            if port == nat and nat:
                exact.append(row)
            elif port == 0 and nat:
                permissive.append(row)
            elif port != nat:
                wrong.append(row)
            print("     tgt u%-4s %-20s natif=%-16s %-34s port=%s"
                  % (tgt["id"], tgt.get("visualId"), hex(nat),
                     ",".join(tr.get("reasons") or []) or "-", hex(port)))

    print("")
    print("[probe] REFUS REPRODUITS A L'IDENTIQUE (port == natif != 0) : %d" % len(exact))
    for r in exact:
        print("   %-22s tgt u%-4s %-20s %s %s" % (r[0], r[1], r[2], r[3], r[4]))
    print("[probe] PERMISSIF (natif refuse, regle non portee -> port 0) : %d" % len(permissive))
    for r in permissive:
        print("   %-22s tgt u%-4s %-20s %s %s" % (r[0], r[1], r[2], r[3], r[4]))
    print("[probe] VIOLATIONS DU CONTRAT : %d" % len(wrong))
    for r in wrong:
        print("   %-22s tgt u%-4s %-20s natif=%s %s port=%s"
              % (r[0], r[1], r[2], r[3], r[4], r[6]))
    # #287-r9 : une ability NON MESUREE ne peut pas sortir en vert. Le deblocage a echoue, donc le
    # masque n'a ete confronte sur AUCUNE cible -- ce n'est ni un accord ni un desaccord.
    print("[probe] ABILITIES NON MESUREES (oracle court-circuite en amont) : %d" % len(bloques))
    for nom, at, why in bloques:
        print("   %-22s (%d) : %s" % (nom, at, why))
    return 1 if (wrong or bloques) else 0


if __name__ == "__main__":
    sys.exit(main())
