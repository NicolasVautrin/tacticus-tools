"""Etage 3 du montage mythique : la config d'ability est-elle synthetisable ?

Verifie, pour les 11 mythiques :
  - l'id TriggeredAbilityType existe ;
  - la definition gameconfig existe et porte Variables/Constants ;
  - synthesize_ability rend une config non vide ;
  - le porteur MoW est-il dans le pool / injectable au catalogue.

Sortie ASCII only. Lecture seule.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import catalog_inject  # noqa: E402
import gameconfig  # noqa: E402

MYTHIQUES = {
    "GuardianConstruct": "necroReanimator",
    "CabalOfSorcerers": "thousDaemonPrince",
    "HyperCorrosiveAcid": "tyranBiovore",
    "BlightedLand": "deathCrawler",
    "ContemptuousDisregard": "blackForgefiend",
    "MastersOfManoeuvre": "darkaStormSpeeder",
    "ShieldOfFaith": "adeptExorcist",
    "OnMyPosition": "astraOrdnanceBattery",
    "MoreGitzOverEre": "orksRukkatrukk",
    "ElectrochaffBackups": "tauBroadside",
    "WisdomOfTheAncients": "ultraDreadnought",
}


def main() -> int:
    print("=== ETAGE 1 : id TriggeredAbilityType + config synthetisable ===")
    for name, uid in MYTHIQUES.items():
        try:
            aid = catalog_inject.triggered_ability_id(name)
        except Exception as exc:  # noqa: BLE001
            print("  %-22s ID: ECHEC %s" % (name, type(exc).__name__))
            continue
        adef = gameconfig.ability(name)
        try:
            cfg = catalog_inject.synthesize_ability(name)
        except Exception as exc:  # noqa: BLE001
            print("  %-22s id=%-5s synth: ECHEC %s: %s" % (name, aid, type(exc).__name__, exc))
            continue
        nvar = len(cfg.get("Variables") or {})
        ncst = len(cfg.get("Constants") or {})
        lvls = catalog_inject.ability_level_count(name)
        print("  %-22s id=%-5s def=%-3s vars=%-3d consts=%-3d niveaux=%s"
              % (name, aid, "OUI" if adef else "NON", nvar, ncst, lvls))

    print()
    print("=== ETAGE 2 : porteur -- relic_carriers dit-il quelque chose ? ===")
    for name in MYTHIQUES:
        try:
            carriers = catalog_inject.relic_carriers(name)
        except Exception as exc:  # noqa: BLE001
            carriers = "ECHEC %s" % type(exc).__name__
        print("  %-22s relic_carriers=%s" % (name, carriers))

    print()
    print("=== ETAGE 3 : mythic_carriers derive du gameconfig (units.*.mythicAbilities) ===")
    cfg = gameconfig._cfg()
    for name, attendu in MYTHIQUES.items():
        porteurs = []
        for kind, entries in (cfg.get("units") or {}).items():
            if not isinstance(entries, dict):
                continue
            for uid, u in entries.items():
                if isinstance(u, dict) and name in (u.get("mythicAbilities") or []):
                    porteurs.append("%s(%s)" % (uid, kind))
        ok = "OK" if any(p.startswith(attendu + "(") for p in porteurs) else "MANQUE"
        print("  %-22s %-6s %s" % (name, ok, porteurs))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
