"""Recon MONTAGE mythique : ids d'enum, presence dans le seed BC, pool.

Repond a : par quelle voie une mythicAbility arrive-t-elle en bataille ?
Hypothese lue au decompile (IdunMetaLogic.UserProgress.TertiaryAbilities$$GetTertiaryAbility) :
la mythique et la relique partagent le champ TERTIAIRE.

Sortie ASCII only. Lecture seule.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import gameconfig  # noqa: E402

MYTHIQUES = [
    "GuardianConstruct",
    "CabalOfSorcerers",
    "HyperCorrosiveAcid",
    "BlightedLand",
    "ContemptuousDisregard",
    "MastersOfManoeuvre",
    "ShieldOfFaith",
    "OnMyPosition",
    "MoreGitzOverEre",
    "ElectrochaffBackups",
    "WisdomOfTheAncients",
]

PORTEURS = {
    "GuardianConstruct": "necroReanimator",
    "CabalOfSorcerers": "thousDaemonPrince",
    "HyperCorrosiveAcid": "tyranBiovore",
    "BlightedLand": "deathCrawler",
    "ContemptuousDisregard": "blackForgefiend",
    "MastersOfManoeuvre": "darkaStormSpeeder",
}


def _seed_bc() -> dict:
    p = Path(__file__).resolve().parents[2] / "data" / "seed-bc.json"
    if not p.exists():
        print("SEED BC ABSENT : %s" % p)
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def main() -> int:
    print("=== ETAGE 1 : id d'enum de chaque mythique ===")
    for name in MYTHIQUES:
        aid = gameconfig.ability_id(name)
        adef = gameconfig.ability(name)
        kind = None
        if adef is not None:
            kind = adef.get("_voie") or adef.get("kind")
        print("  %-24s id=%-6s def=%s" % (name, aid, "OUI" if adef else "NON"))

    print()
    print("=== ETAGE 2 : voie de declaration dans le gameconfig (abilities.*) ===")
    cfg = gameconfig._cfg()
    ab = cfg.get("abilities", {})
    print("  cles de gc['abilities'] : %s" % sorted(ab.keys()))
    for voie, entries in ab.items():
        if not isinstance(entries, dict):
            continue
        hits = [n for n in MYTHIQUES if n in entries]
        if hits:
            print("  voie %-22s contient %d/%d mythiques : %s"
                  % (voie, len(hits), len(MYTHIQUES), hits))

    print()
    print("=== ETAGE 3 : seed BC -- ou les mythiques pourraient vivre ===")
    bc = _seed_bc()
    if bc:
        abil = bc.get("Abilities") or {}
        print("  BC.Abilities cles : %s" % sorted(abil.keys()))
        for k, v in abil.items():
            if isinstance(v, dict):
                hits = [n for n in MYTHIQUES if n in v]
                print("    %-22s %4d entrees ; mythiques presentes : %s"
                      % (k, len(v), hits if hits else "AUCUNE"))
            elif isinstance(v, list):
                print("    %-22s liste de %d" % (k, len(v)))
        units = bc.get("Units") or []
        print("  BC.Units : %d unites" % len(units))
        if units:
            print("  cles d'une Unit : %s" % sorted(units[0].keys()))
        porteurs_au_seed = [u for u in units
                            if u.get("UnitId") in set(PORTEURS.values())
                            or u.get("Id") in set(PORTEURS.values())]
        print("  porteurs de mythique presents au seed : %d" % len(porteurs_au_seed))
        avec_tert = [u for u in units if u.get("TertiaryAbility")]
        print("  unites du seed avec TertiaryAbility non nulle : %d" % len(avec_tert))
        for u in avec_tert:
            print("    %-24s Tertiary=%s Level=%s"
                  % (u.get("UnitId") or u.get("Id"), u.get("TertiaryAbility"),
                     u.get("TertiaryAbilityLevel")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
