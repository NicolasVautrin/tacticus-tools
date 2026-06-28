"""Carte mentale des UNITS — index interrogeable du kit de combat de chaque unité (gameconfig + i2).

But : retrouver vite l'unité voulue pour TESTER un mécanisme précis (dégât, multi-coups, crit, block,
réduction, trait, ability, effet). Évite la chasse au seed : on PIOQUE l'unité qui a la propriété cherchée,
puis on monte un runner contrôlé (buildPatchedRunner aiUnits / pilotage manuel) avec elle.

Source de vérité = gameconfig (chiffres : weapons.hits/Range, DamageProfile.PiercingRatio, stats, traits,
abilities) + i2_en.json (texte de RÈGLES via gameconfig.ability_description/trait_description) pour
classer ce que fait chaque ability/trait (buff dégât, réduction, crit, block, hits, perçage…).

CLI :
  python unit_map.py kit <unitId|nom>            # kit complet d'une unité
  python unit_map.py melee-multihit [--vanilla]  # unités à arme MÊLÉE multi-coups (option: sans modif dégât)
  python unit_map.py vanilla-target              # cibles SANS réduction de dégât (trait/ability)
  python unit_map.py find --melee-hits N --ranged-hits N --trait T --ability A --no-dmg-mods --faction F
  python unit_map.py mechanic <kw>               # unités dont un trait/ability mentionne kw (i2), ex. "block","crit","reduce"
  python unit_map.py doc                          # régénère docs/rl/unit-map.md (tableaux récap)
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import gameconfig as GC

# Mots-clés i2 (texte de règles) par CATÉGORIE de mécanisme de dégât/combat.
MECH = {
    "dmg_bonus": re.compile(r"\b(extra|bonus|increase|more|additional)\b.{0,30}\bdamage\b|deal.{0,20}more damage", re.I),
    "dmg_reduction": re.compile(r"reduc.{0,30}damage|damage.{0,20}reduc|take.{0,20}less damage|"
                                r"resilient|mitigat", re.I),
    "crit": re.compile(r"\bcrit", re.I),
    "block": re.compile(r"\bblock", re.I),
    "evasion": re.compile(r"evad|evasion|dodge", re.I),
    "extra_hits": re.compile(r"extra hit|additional hit|hits? twice|one more hit|extra attack", re.I),
    "pierce": re.compile(r"pierc|ignore.{0,15}armou?r|armou?r.{0,15}ignor|penetrat", re.I),
    "shield": re.compile(r"\bshield", re.I),
}
# traits "vanille-cassants" connus (réduction/armure/défense) — pour exclure une cible propre par sûreté.
REDUC_TRAIT = re.compile(r"resilient|terminator|tough|parry|terrify|deflect|impervious|armou?r", re.I)


def _weapons(u: dict) -> list[dict]:
    out = []
    for w in (u.get("weapons") or []):
        dp = GC.damage_profile(w.get("DamageProfile")) or {}
        out.append({
            "hits": int(w.get("hits") or 1),
            "range": int(w.get("Range") or 0),        # 0 = MÊLÉE
            "melee": not w.get("Range"),
            "profile": w.get("DamageProfile"),
            "pierce": int(dp.get("PiercingRatio") or 0),
            "profile_traits": dp.get("Traits") or [],
        })
    return out


def _abil_text(aid: str) -> str:
    try:
        return GC.ability_description(aid) or ""
    except Exception:
        return ""


def _trait_text(tid: str) -> str:
    try:
        return GC.trait_description(tid) or ""
    except Exception:
        return tid


def _norm_stats(raw) -> dict:
    """Normalise les stats en dict représentatif. lineup = dict ; npc = liste de blocs par rang
    (on prend le rang MAX) ; summons = None → {}."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, list) and raw:
        return max(raw, key=lambda b: (b.get("Rank", 0), b.get("StarLevel", 0))) if all(
            isinstance(b, dict) for b in raw) else {}
    return {}


def kit(uid: str) -> dict | None:
    u = GC.unit(uid)
    if u is None:
        return None
    ws = _weapons(u)
    melee = [w for w in ws if w["melee"]]
    ranged = [w for w in ws if not w["melee"]]
    abils = (u.get("activeAbilities") or []) + (u.get("passiveAbilities") or [])
    # classe les mécanismes mentionnés par les abilities + traits (texte i2)
    mech: dict[str, list[str]] = {k: [] for k in MECH}
    for aid in abils:
        t = _abil_text(aid)
        for k, rx in MECH.items():
            if rx.search(t):
                mech[k].append(aid)
    for tid in (u.get("traits") or []):
        t = _trait_text(tid)
        for k, rx in MECH.items():
            if rx.search(t):
                mech[k].append("trait:" + tid)
    return {
        "id": uid, "name": u.get("name"), "kind": u.get("kind"),
        "faction": u.get("FactionId"), "alliance": u.get("GrandAllianceId"),
        "rarity": u.get("BaseRarity"), "movement": u.get("Movement"),
        "stats": _norm_stats(u.get("stats")),
        "melee_hits": max([w["hits"] for w in melee], default=0),
        "ranged_hits": max([w["hits"] for w in ranged], default=0),
        "melee_pierce": (melee[0]["pierce"] if melee else None),
        "ranged_pierce": (ranged[0]["pierce"] if ranged else None),
        "weapons": ws, "traits": u.get("traits") or [], "abilities": abils,
        "mech": {k: v for k, v in mech.items() if v},
    }


def all_kits() -> list[dict]:
    ids = GC.all_unit_ids()
    out = []
    for kind in ("lineup", "npc", "summons"):
        for uid in ids[kind]:
            k = kit(uid)
            if k:
                out.append(k)
    return out


def _has_dmg_mod(k: dict) -> bool:
    """L'unité porte-t-elle un modificateur de dégât (offensif/défensif) sur ses abilities/traits ?"""
    m = k["mech"]
    if any(m.get(c) for c in ("dmg_bonus", "dmg_reduction", "crit", "block", "evasion",
                              "extra_hits", "pierce", "shield")):
        return True
    return any(REDUC_TRAIT.search(t) for t in k["traits"])


# ─────────────────────────────────────────────────────────────── requêtes CLI

def _print_row(k: dict):
    mm = "/".join(f"{w['hits']}h{'m' if w['melee'] else 'R'+str(w['range'])}p{w['pierce']}"
                  for w in k["weapons"])
    mech = ",".join(k["mech"].keys()) or "-"
    print(f"  {k['id']:<26} {str(k['name'])[:20]:<20} {k['kind']:<7} "
          f"HP{k['stats'].get('Health',0):>4} D{k['stats'].get('Damage',0):>3} "
          f"A{k['stats'].get('FixedArmor',0):>3} | {mm:<22} | mech:{mech}")


def cmd_melee_multihit(vanilla: bool):
    rows = [k for k in all_kits() if k["melee_hits"] >= 2]
    if vanilla:
        rows = [k for k in rows if not _has_dmg_mod(k)]
    rows.sort(key=lambda k: (-k["melee_hits"], k["id"]))
    print(f"=== {len(rows)} unités MÊLÉE multi-coups{' VANILLE (sans modif dégât)' if vanilla else ''} ===")
    for k in rows:
        _print_row(k)


def cmd_vanilla_target():
    rows = [k for k in all_kits() if not _has_dmg_mod(k)]
    rows.sort(key=lambda k: (k["kind"], k["id"]))
    print(f"=== {len(rows)} cibles VANILLE (aucune réduction/modif dégât trait+ability) ===")
    for k in rows:
        _print_row(k)


def cmd_mechanic(kw: str):
    kwl = kw.lower()
    print(f"=== unités dont un trait/ability mentionne '{kw}' (i2) ===")
    for k in all_kits():
        hits = [aid for aid in k["abilities"] if kwl in _abil_text(aid).lower()]
        thits = [tid for tid in k["traits"] if kwl in _trait_text(tid).lower()]
        if hits or thits:
            print(f"  {k['id']:<26} {str(k['name'])[:18]:<18} ab:{hits} tr:{thits}")


def cmd_find(a):
    rows = all_kits()
    if a.melee_hits is not None:
        rows = [k for k in rows if k["melee_hits"] >= a.melee_hits]
    if a.ranged_hits is not None:
        rows = [k for k in rows if k["ranged_hits"] >= a.ranged_hits]
    if a.trait:
        rows = [k for k in rows if any(a.trait.lower() in t.lower() for t in k["traits"])]
    if a.ability:
        rows = [k for k in rows if any(a.ability.lower() in x.lower() for x in k["abilities"])]
    if a.faction:
        rows = [k for k in rows if (k["faction"] or "").lower() == a.faction.lower()]
    if a.no_dmg_mods:
        rows = [k for k in rows if not _has_dmg_mod(k)]
    rows.sort(key=lambda k: (-k["melee_hits"], -k["ranged_hits"], k["id"]))
    print(f"=== {len(rows)} unités ===")
    for k in rows[:80]:
        _print_row(k)


def cmd_kit(query: str):
    uid = GC.resolve_unit_id(query) or query
    k = kit(uid)
    if k is None:
        print(f"unité introuvable: {query}"); return
    import json
    print(json.dumps(k, indent=1, ensure_ascii=False))


def cmd_doc():
    out = Path(__file__).resolve().parents[2] / "docs" / "rl" / "unit-map.md"
    kits = all_kits()
    melee_mh = sorted([k for k in kits if k["melee_hits"] >= 2 and not _has_dmg_mod(k)],
                      key=lambda k: (-k["melee_hits"], k["id"]))
    vanilla = sorted([k for k in kits if not _has_dmg_mod(k)], key=lambda k: k["id"])
    lines = ["# Carte des units — index de test (généré par unit_map.py)", "",
             f"{len(kits)} units (123 lineup + 481 npc + 65 summons). Régénérer : `python unit_map.py doc`.",
             "", "Config Damage BC : ArmorPercentage=50, DamageSpread=20, ElevationBonus=50, "
             "Trench=25, Knockback=20, RangedInMeleeReduction=-50.", "",
             "## Attaquants MÊLÉE multi-coups VANILLE (test multi-coups propre)", "",
             "| id | nom | hits | pierce | HP/D/A |", "|---|---|---|---|---|"]
    for k in melee_mh[:40]:
        lines.append(f"| {k['id']} | {k['name']} | {k['melee_hits']} | {k['melee_pierce']} | "
                     f"{k['stats'].get('Health')}/{k['stats'].get('Damage')}/{k['stats'].get('FixedArmor')} |")
    lines += ["", f"## Cibles VANILLE sans réduction ({len(vanilla)}) — extrait", "",
              ", ".join(k["id"] for k in vanilla[:60]), ""]
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"écrit {out} ({len(kits)} units indexées ; {len(melee_mh)} mêlée-multi vanille, {len(vanilla)} vanille)")


def main(argv):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("melee-multihit").add_argument("--vanilla", action="store_true")
    sub.add_parser("vanilla-target")
    sub.add_parser("mechanic").add_argument("kw")
    sub.add_parser("kit").add_argument("query")
    sub.add_parser("doc")
    f = sub.add_parser("find")
    f.add_argument("--melee-hits", type=int); f.add_argument("--ranged-hits", type=int)
    f.add_argument("--trait"); f.add_argument("--ability"); f.add_argument("--faction")
    f.add_argument("--no-dmg-mods", action="store_true")
    a = ap.parse_args(argv)
    if a.cmd == "melee-multihit": cmd_melee_multihit(a.vanilla)
    elif a.cmd == "vanilla-target": cmd_vanilla_target()
    elif a.cmd == "mechanic": cmd_mechanic(a.kw)
    elif a.cmd == "kit": cmd_kit(a.query)
    elif a.cmd == "find": cmd_find(a)
    elif a.cmd == "doc": cmd_doc()
    else: ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
