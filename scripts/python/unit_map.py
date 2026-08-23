"""Carte mentale des UNITS — index interrogeable du kit de combat de chaque unité (gameconfig + i2).

But : retrouver vite l'unité voulue pour TESTER un mécanisme précis (dégât, multi-coups, crit, block,
réduction, trait, ability, effet). Évite la chasse au seed : on PIOQUE l'unité qui a la propriété cherchée,
puis on monte un runner contrôlé (`rl_duel build`) avec elle.
  ⛔ Cette ligne citait `buildPatchedRunner aiUnits` : le champ `aiUnits` du patch a été RETIRÉ le
     2026-08-23 (aucun appelant, et sa variante `aiUnitsAt` no-opait en silence). Elle était le
     DERNIER endroit du dépôt à le nommer — donc la seule piste qu'aurait suivie un lecteur.

Source de vérité = gameconfig (chiffres : weapons.hits/Range, DamageProfile.PiercingRatio, stats, traits,
abilities) + i2_en.json (texte de RÈGLES via gameconfig.ability_description/trait_description) pour
classer ce que fait chaque ability/trait (buff dégât, réduction, crit, block, hits, perçage…).

CLI :
  python unit_map.py kit <unitId|nom>            # kit complet d'une unité
  python unit_map.py melee-multihit [--vanilla]  # unités à arme MÊLÉE multi-coups (option: sans modif dégât)
  python unit_map.py vanilla-target              # cibles SANS réduction de dégât (trait/ability)
  python unit_map.py find --melee-hits N --ranged-hits N --trait T --ability A --no-dmg-mods --faction F
  python unit_map.py find --ability A --ability-voie relic     # restreint à UNE voie d'attribution
  python unit_map.py voies [--ability A]         # les voies d'attribution : couvertes / NON couvertes
  python unit_map.py mechanic <kw>               # unités dont un trait/ability mentionne kw (i2), ex. "block","crit","reduce"
  python unit_map.py doc                          # régénère docs/rl/unit-map.md (tableaux récap)

⚠ `find --ability` N'EST PAS UN ORACLE DE MORT — cf. `voies` et le pied de page qu'il imprime
quand il rend 0 unité. Jusqu'à #323 il ne lisait que `activeAbilities` + `passiveAbilities` : il
rendait donc « 0 unité » pour toute ability accordée par une RELIQUE, et ce zéro a fait classer
`NetherRealmCasket` / l'effet 1462 en DEAD alors que trois héros du pool la portent (#310 → #317).
Détail : `docs/rl/case-323-unit-map-attribution-voies.md`.
"""
from __future__ import annotations

import argparse
import functools
import json
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

# ─────────────────────────────────── VOIES d'attribution d'une ability à une unité (#323)
#
# Une unité porte une ability par PLUSIEURS chemins, et cet outil n'en lisait que DEUX. Le zéro
# rendu par `find --ability` sur les autres voies a déjà FERMÉ UN RÉSIDU À TORT (`NetherRealmCasket`
# → effet 1462, classé DEAD par #310, rouvert par #317). La liste ci-dessous est MESURÉE sur le
# gameconfig (`probe_323_ability_carrier_voies.py`), pas supposée.
#
# COUVERTES par cet outil (dérivables du gameconfig, index exact) :
#   active  `units.<kind>.<id>.activeAbilities`      — l'actif du kit
#   passive `units.<kind>.<id>.passiveAbilities`     — le passif du kit
#   relic   `units.<kind>.<id>.relicAbilities`       — la relique EN DUR (npc « Boss » surtout)
#   mythic  `units.<kind>.<id>.mythicAbilities`      — l'ability mythique d'une Machine of War
#   item    `items[*].abilityId` + `items[*].allowedUnits` — la relique ÉQUIPABLE par un héros ;
#           matérialisée en bataille dans `BattleConfiguration.Units[].TertiaryAbility`
#
# NON COUVERTES, et c'est ASSUMÉ (aucune n'est dérivable du gameconfig seul) :
#   trait      un TRAIT accorde une ability sans aucune entrée `units.*Abilities` — le mapping vit
#              dans le natif (`Mechanic` → `ActiveAbilityType` 28 `Repair` ; `LivingMetal` →
#              `TriggeredAbilityType` 1010). Interroger `find --trait <T>`, pas `--ability`.
#   liveevent les `Enhancement*` d'un `liveEvents.idunLiveEventConfigs[].enhancements` : accordées
#              hors bataille régulière, à aucune unité du catalogue.
#   summon     le summon n'est pas « porté » par son summoner : il entre en bataille avec SON kit
#              propre. Chercher le summon lui-même, puis remonter à son summoner.
#   tile       les power-ups de terrain (`PowerUp_*`) : posés par le BOARD, pas par une unité.
UNIT_ABILITY_FIELDS = {
    "active": "activeAbilities",
    "passive": "passiveAbilities",
    "relic": "relicAbilities",
    "mythic": "mythicAbilities",
}
VOIE_KEYS = tuple(UNIT_ABILITY_FIELDS) + ("item",)
VOIES_NON_COUVERTES = (
    ("trait", "un TRAIT accorde l'ability (mapping NATIF, hors gameconfig) -- ex. `Mechanic` -> "
              "ActiveAbilityType 28 Repair, `LivingMetal` -> TriggeredAbilityType 1010. "
              "Interroger `find --trait <T>`."),
    ("liveevent", "enhancement de live-event (`Enhancement*`) : accorde hors bataille reguliere, "
                  "a aucune unite du catalogue."),
    ("summon", "un summon porte SON kit propre ; il n'apparait pas sur son summoner. Chercher le "
               "summon, puis remonter au summoner (qui, lui, doit etre spawnable)."),
    ("tile", "power-up de TERRAIN (`PowerUp_*`) : pose par le BOARD, pas par une unite."),
)


@functools.lru_cache(maxsize=1)
def _relic_items() -> dict:
    """`{unitId: [(abilityId, itemId)]}` — la relique ÉQUIPABLE, voie que l'unité n'expose PAS.

    Un item `isRelic` porte `abilityId` + `allowedUnits` : l'ability n'apparaît nulle part sur la
    fiche des héros concernés. C'est la voie qui manquait (`R_Booster_Crit_NetherRealmCasket` →
    `NetherRealmCasket`, `allowedUnits = [necroWarden, necroSpyder, necroDestroyer]`)."""
    doc = json.loads(GC._find_gameconfig().read_text(encoding="utf-8"))
    cg = doc.get("clientGameConfig") or doc
    out: dict[str, list[tuple[str, str]]] = {}
    for iid, it in (cg.get("items") or {}).items():
        aid = it.get("abilityId")
        if not aid:
            continue
        for uid in (it.get("allowedUnits") or []):
            out.setdefault(uid, []).append((aid, iid))
    return out


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
    # `voies` = l'ability indexée PAR CHEMIN d'attribution (#323). `abilities` reste l'union
    # active+passive (les deux voies historiques) pour ne pas déplacer le sens des appelants
    # existants ; `abilities_all` est l'union de TOUTES les voies dérivables du gameconfig.
    voies: dict[str, list[str]] = {k: list(u.get(f) or []) for k, f in UNIT_ABILITY_FIELDS.items()}
    items = _relic_items().get(uid) or []
    voies["item"] = [aid for aid, _ in items]
    abils = voies["active"] + voies["passive"]
    all_abils = [a for k in VOIE_KEYS for a in voies[k]]
    # classe les mécanismes mentionnés par les abilities + traits (texte i2). On balaie TOUTES les
    # voies : une relique de crit (`R_Booster_Crit_*`) est un modificateur de dégât aussi réel
    # qu'un passif, et l'ignorer faisait passer son porteur pour une cible « vanille ».
    mech: dict[str, list[str]] = {k: [] for k in MECH}
    for aid in all_abils:
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
        "voies": {k: v for k, v in voies.items() if v},
        "relic_items": [{"ability": a, "item": i} for a, i in items],
        "abilities_all": all_abils,
        "mech": {k: v for k, v in mech.items() if v},
    }


def carrier_voies(k: dict, needle: str) -> list[str]:
    """Par QUELLES voies l'unité `k` porte une ability dont le nom contient `needle` ?

    Rend p. ex. `['relic']`, `['item']`, `['active', 'item']`. Vide = ne la porte pas. C'est ce
    qui rend le verdict AUDITABLE : « 0 unité » et « 3 unités, toutes par la voie item » sont
    deux réponses différentes, et seule la seconde dit si le porteur l'a en bataille."""
    n = needle.lower()
    return [v for v in VOIE_KEYS if any(n in a.lower() for a in (k.get("voies") or {}).get(v, []))]


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

def _print_row(k: dict, voies: list[str] | None = None):
    mm = "/".join(f"{w['hits']}h{'m' if w['melee'] else 'R'+str(w['range'])}p{w['pierce']}"
                  for w in k["weapons"])
    mech = ",".join(k["mech"].keys()) or "-"
    # `voie=` n'est imprimé que sur une requête `--ability` : c'est ce qui distingue « porté par
    # le kit » de « porté par une relique ÉQUIPABLE » (donc absent de la fiche d'unité).
    vtxt = f" | voie:{','.join(voies)}" if voies else ""
    print(f"  {k['id']:<26} {str(k['name'])[:20]:<20} {k['kind']:<7} "
          f"HP{k['stats'].get('Health',0):>4} D{k['stats'].get('Damage',0):>3} "
          f"A{k['stats'].get('FixedArmor',0):>3} | {mm:<22} | mech:{mech}{vtxt}")


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
        # `abilities_all` (et non `abilities`) : une relique porte du texte de règles comme
        # n'importe quelle ability -- la restreindre ferait rater ses porteurs (#323).
        hits = [aid for aid in k["abilities_all"] if kwl in _abil_text(aid).lower()]
        thits = [tid for tid in k["traits"] if kwl in _trait_text(tid).lower()]
        if hits or thits:
            print(f"  {k['id']:<26} {str(k['name'])[:18]:<18} ab:{hits} tr:{thits}")


def _zero_carrier_footer(needle: str):
    """Le pied de page qu'un « 0 unité » DOIT porter — sinon il se lit comme « dead ».

    C'est le dispositif anti-faux-verdict de #323 : le zéro de `find --ability NetherRealmCasket`
    a été lu comme une preuve de mort dans `case-310`, alors que l'outil ne regardait simplement
    pas la voie relique. Un zéro ne prouve désormais QUE l'absence sur les voies listées."""
    print(f"[voies] '{needle}' est ABSENTE des {len(VOIE_KEYS)} voies derivables du gameconfig "
          f"({', '.join(VOIE_KEYS)}).")
    print("[voies] CE ZERO NE PROUVE PAS QUE L'ABILITY EST MORTE. Voies NON couvertes ici :")
    for name, why in VOIES_NON_COUVERTES:
        print(f"          {name:<10} {why}")
    print("[voies] Avant de conclure 'dead', tranche par une SECONDE source (decompile / "
          "`probe_323_ability_carrier_voies.py`).")


def cmd_find(a):
    rows = all_kits()
    if a.melee_hits is not None:
        rows = [k for k in rows if k["melee_hits"] >= a.melee_hits]
    if a.ranged_hits is not None:
        rows = [k for k in rows if k["ranged_hits"] >= a.ranged_hits]
    if a.trait:
        rows = [k for k in rows if any(a.trait.lower() in t.lower() for t in k["traits"])]
    if a.ability:
        # #323 : on interroge TOUTES les voies dérivables du gameconfig, pas seulement
        # active+passive. `--ability-voie` restreint à une voie nommée quand on veut isoler
        # (ex. `--ability-voie item` = la seule relique ÉQUIPABLE, absente de la fiche d'unité).
        want = VOIE_KEYS if a.ability_voie in (None, "all") else (a.ability_voie,)
        rows = [k for k in rows
                if any(v in want for v in carrier_voies(k, a.ability))]
    if a.faction:
        rows = [k for k in rows if (k["faction"] or "").lower() == a.faction.lower()]
    if a.no_dmg_mods:
        rows = [k for k in rows if not _has_dmg_mod(k)]
    rows.sort(key=lambda k: (-k["melee_hits"], -k["ranged_hits"], k["id"]))
    print(f"=== {len(rows)} unités ===")
    for k in rows[:80]:
        _print_row(k, voies=carrier_voies(k, a.ability) if a.ability else None)
    if a.ability and not rows:
        _zero_carrier_footer(a.ability)


def cmd_voies(needle: str | None):
    """Le tableau de COUVERTURE — ce que l'outil sait voir, et ce qu'il ne saura jamais voir."""
    print("=== voies d'attribution d'une ability a une unite (#323) ===")
    print("-- COUVERTES par unit_map (derivables du gameconfig) :")
    kits = all_kits()
    for v in VOIE_KEYS:
        src = ("items[*].abilityId + allowedUnits" if v == "item"
               else "units.<kind>.<id>." + UNIT_ABILITY_FIELDS[v])
        carriers = [k for k in kits if (k.get("voies") or {}).get(v)]
        abils = {a for k in carriers for a in (k.get("voies") or {}).get(v, [])}
        print("   %-8s %-42s %4d unites, %3d abilities" % (v, src, len(carriers), len(abils)))
    print("-- NON couvertes (ASSUMEES -- aucune n'est derivable du gameconfig seul) :")
    for name, why in VOIES_NON_COUVERTES:
        print("   %-10s %s" % (name, why))
    if needle:
        print(f"\n=== '{needle}' -- porteurs par voie ===")
        n = 0
        for k in kits:
            vs = carrier_voies(k, needle)
            if vs:
                n += 1
                print("   %-26s %-7s voies=%s" % (k["id"], k["kind"], vs))
        if not n:
            print("   aucun porteur sur les voies couvertes.")
            _zero_carrier_footer(needle)


def cmd_kit(query: str):
    uid = GC.resolve_unit_id(query) or query
    k = kit(uid)
    if k is None:
        print(f"unité introuvable: {query}"); return
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
    f.add_argument("--ability-voie", choices=("all",) + VOIE_KEYS, default="all",
                   help="restreint --ability a UNE voie d'attribution (defaut: toutes)")
    f.add_argument("--no-dmg-mods", action="store_true")
    v = sub.add_parser("voies")
    v.add_argument("--ability", default=None)
    a = ap.parse_args(argv)
    if a.cmd == "melee-multihit": cmd_melee_multihit(a.vanilla)
    elif a.cmd == "vanilla-target": cmd_vanilla_target()
    elif a.cmd == "mechanic": cmd_mechanic(a.kw)
    elif a.cmd == "kit": cmd_kit(a.query)
    elif a.cmd == "find": cmd_find(a)
    elif a.cmd == "voies": cmd_voies(a.ability)
    elif a.cmd == "doc": cmd_doc()
    else: ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
