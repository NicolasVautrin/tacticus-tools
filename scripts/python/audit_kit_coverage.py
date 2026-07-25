"""Audit de la couverture moteur PAR KIT (unites lineup) — vue "kits restants a porter".

Complement KIT-centrique de `audit_combat_ability_coverage.py` (#95, vue par-ability) : pour
chaque unite LINEUP (jouable en walk), croise son kit gameconfig complet avec les registres
moteur des deux faces :

  FACE COMBAT (execution) :
    - actives  -> `engine.runner.abilities.handler.ABILITY_CLASSES` (id ActiveAbilityType)
    - passives -> `triggers.dispatch.ABILITY_TRIGGERS` (nom d'ability) et
                  `effects.factory.ABILITY_INIT_OWNER_EFFECTS` (effet owner pose au spawn)
    - traits   -> `triggers.dispatch.TRAIT_TRIGGERS` + `effects.factory.TRAIT_DERIVED_ABILITIES`
  FACE DECISION (scoring) : DEUX registres, pas un —
    - `engine.playbook.noncomparable.PLAYBOOKS` (id) : les abilities NON-COMPARABLES, qui ont
      leur propre voie de scoring ;
    - `engine.playbook.base.REGISTRY` (id) : les abilities COMPARABLES dotees d'un override
      `CalculateCustomUtility` (#27) — leur voie generique est commune, seul le terme custom est
      par-ability. Lire le 1er SEUL faisait ressortir `[--]` (= rien de porte) sur des abilities
      dont la face DECISION est portee, ex. DoomSiren(1199) alors que `DoomSirenPlaybook` existe.
    Le reste de la voie comparable est generique et n'est pas audite ici.

APPROXIMATIONS assumees (l'audit RANGE les kits par volume de travail, il ne PROUVE pas une
couverture) : un passif peut etre implemente ailleurs (mod attaquant, effet, legalite) sans
figurer dans ces registres -> faux "MISSING" possibles, a trancher au recon du kit. Les traits
FREQUENTS (>TRAIT_COMMON_MAX unites : Hero, Psyker, Flying, ...) sont presumes couverts par les
couches globales (mouvement/legalite/smite) et exclus du comptage.

Genere `docs/rl/kit-coverage.md`. A relancer apres tout port / changement de build.
Usage : depuis `scripts/python/`  ->  `python audit_kit_coverage.py`
"""
from __future__ import annotations

import os
import sys
from collections import Counter, defaultdict

_PYROOT = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(_PYROOT))
if _PYROOT not in sys.path:
    sys.path.insert(0, _PYROOT)

import enum_maps as EM
import gameconfig as GC
import unit_map as UM
from audit_combat_ability_coverage import _classify
from engine.entities.effects.factory import ABILITY_INIT_OWNER_EFFECTS, TRAIT_DERIVED_ABILITIES
from engine.playbook import REGISTRY as CUSTOM_PLAYBOOKS   # comparables a override CalculateCustomUtility
from engine.playbook.noncomparable import PLAYBOOKS
from engine.runner.abilities.handler import ABILITY_CLASSES
from engine.runner.operations.triggers.dispatch import ABILITY_TRIGGERS, TRAIT_TRIGGERS

OUT = os.path.join(_REPO, "docs", "rl", "kit-coverage.md")

# Au-dela de ce nombre de porteurs, un trait est presume couvert par les couches globales
# (stats/mouvement/legalite) et n'est pas compte comme travail de kit.
TRAIT_COMMON_MAX = 12


def collect():
    name2id = {v: k for k, v in EM.ACTIVE_ABILITY_TYPE.items()}
    trait_units: Counter = Counter()
    for k in UM.all_kits():
        u = GC.unit(k["id"]) or {}
        for t in (u.get("traits") or []):
            trait_units[t] += 1

    rows = []
    for k in UM.all_kits():
        if k.get("kind") != "lineup":
            continue
        u = GC.unit(k["id"]) or {}
        actives = []
        for nm in (u.get("activeAbilities") or []):
            aid = name2id.get(nm)
            actives.append({
                "name": nm, "id": aid, "cat": _classify(nm),
                "combat": aid in ABILITY_CLASSES,
                "decision": aid in PLAYBOOKS or aid in CUSTOM_PLAYBOOKS,
            })
        passives = []
        for nm in (u.get("passiveAbilities") or []):
            passives.append({
                "name": nm,
                "covered": nm in ABILITY_TRIGGERS or nm in ABILITY_INIT_OWNER_EFFECTS,
            })
        kit_traits = []
        for t in (u.get("traits") or []):
            if trait_units[t] > TRAIT_COMMON_MAX:
                continue                       # trait commun -> couche globale, pas du travail de kit
            kit_traits.append({
                "name": t, "carriers": trait_units[t],
                "covered": t in TRAIT_TRIGGERS or t in TRAIT_DERIVED_ABILITIES,
            })
        missing = (sum(1 for a in actives if not a["combat"])
                   + sum(1 for p in passives if not p["covered"])
                   + sum(1 for t in kit_traits if not t["covered"]))
        rows.append({
            "id": k["id"], "faction": u.get("FactionId") or "?",
            "actives": actives, "passives": passives, "traits": kit_traits,
            "missing": missing,
        })
    return rows


def _fmt_active(a: dict) -> str:
    face = ("C" if a["combat"] else "-") + ("D" if a["decision"] else "-")
    tag = "OK" if a["combat"] else "NO-OP %s" % a["cat"]
    return "%s(%s) [%s] %s" % (a["name"], a["id"] if a["id"] is not None else "?", face, tag)


def main():
    rows = collect()
    done = [r for r in rows if r["missing"] == 0]
    todo = sorted((r for r in rows if r["missing"] > 0),
                  key=lambda r: (-r["missing"], r["faction"], r["id"]))
    by_faction: dict[str, list] = defaultdict(list)
    for r in todo:
        by_faction[r["faction"]].append(r)

    lines = []
    lines.append("# Couverture moteur par KIT (unites lineup)\n\n")
    lines.append("> Genere par `scripts/python/audit_kit_coverage.py` (kit gameconfig x registres moteur\n"
                 "> des deux faces). Vue KIT-centrique complementaire de `combat-ability-coverage.md`\n"
                 "> (par-ability). Faces : `[CD]` = combat/decision portees, `[--]` = aucune ; `D` couvre\n"
                 "> les DEUX registres de scoring (non-comparables + overrides custom des comparables).\n"
                 "> A regenerer\n"
                 "> apres tout port. Les MISSING passifs/traits sont des CANDIDATS (approximation\n"
                 "> registres, cf. docstring du script) : trancher au recon du kit.\n\n")
    lines.append("## Bilan\n\n")
    lines.append("- Unites lineup : **%d** ; kits COMPLETS (aucun manque detecte) : **%d** ; "
                 "kits avec du travail : **%d**\n" % (len(rows), len(done), len(todo)))
    lines.append("- Volume total : **%d** items manquants (actives no-op + passifs/traits non registres)\n\n"
                 % sum(r["missing"] for r in todo))
    lines.append("## Par faction (kits avec du travail, tries par volume)\n")
    for fac in sorted(by_faction, key=lambda f: -sum(r["missing"] for r in by_faction[f])):
        frows = by_faction[fac]
        lines.append("\n### %s — %d kits, %d items\n\n" % (fac, len(frows), sum(r["missing"] for r in frows)))
        lines.append("| unite | manque | actives | passifs manquants | traits de kit manquants |\n")
        lines.append("|---|---|---|---|---|\n")
        for r in frows:
            acts = "<br>".join(_fmt_active(a) for a in r["actives"]) or "-"
            pmiss = ", ".join(p["name"] for p in r["passives"] if not p["covered"]) or "-"
            tmiss = ", ".join("%s(x%d)" % (t["name"], t["carriers"])
                              for t in r["traits"] if not t["covered"]) or "-"
            lines.append("| %s | %d | %s | %s | %s |\n" % (r["id"], r["missing"], acts, pmiss, tmiss))
    lines.append("\n## Kits lineup COMPLETS (%d)\n\n" % len(done))
    lines.append(", ".join(sorted(r["id"] for r in done)) + "\n")

    with open(OUT, "w", encoding="utf-8") as f:
        f.writelines(lines)
    print("ecrit -> %s" % OUT)
    print("lineup=%d complets=%d avec-travail=%d items=%d"
          % (len(rows), len(done), len(todo), sum(r["missing"] for r in todo)))


if __name__ == "__main__":
    main()
