#!/usr/bin/env python
"""gameconfig — helper MÉCANIQUE (lecture directe du gameconfig du jeu).

Pas de wiki généré : on lit la source de vérité (le gameconfig téléchargé par le
jeu, ~16 MB, hash par version) et on répond à la demande. Le wiki ne porte que
les NOTES TACTIQUES (séparé).

Source : `AppData/LocalLow/Snowprint/<produit>/gameconfig/<hash>.json`
    .clientGameConfig.units.{abilities, lineup(héros), npc(480), summons,
                             damageProfiles} + .globalValues.traitVariables

API :
    unit(id)           -> def normalisée (cherche lineup -> npc -> summons), +kind
    ability(id)        -> def (attackRangeType, constants=effet+conditions, variables, upgrades)
    damage_profile(n)  -> {PiercingRatio, ...}
    trait(id)          -> {variables: {params traitVariables matchés}}
    card_unit/ability/trait(...) -> texte compact lisible (kit résolu)

Usage : python scripts/python/gameconfig.py [unitId|nom]   (ex. `admecManipulus` OU `Actus`)
        python scripts/python/gameconfig.py --unit <id|nom>   (kit complet ; suggère si ambigu)
"""
from __future__ import annotations

import functools
import json
import re
import sys
from pathlib import Path


def _find_gameconfig() -> Path:
    base = Path.home() / "AppData" / "LocalLow" / "Snowprint"
    cands = list(base.glob("*/gameconfig/*.json"))
    if not cands:
        raise RuntimeError(f"gameconfig introuvable sous {base}")
    # le full config = le plus gros fichier (ignore gameconfigupgrade.json & co)
    return max(cands, key=lambda p: p.stat().st_size)


@functools.lru_cache(maxsize=1)
def _cfg() -> dict:
    data = json.loads(_find_gameconfig().read_text(encoding="utf-8"))
    return data.get("clientGameConfig") or data


@functools.lru_cache(maxsize=1)
def _index() -> dict:
    c = _cfg()
    u = c.get("units") or {}
    return {
        "abilities": u.get("abilities") or {},
        "lineup": u.get("lineup") or {},
        "npc": u.get("npc") or {},
        "summons": u.get("summons") or {},
        "damageProfiles": u.get("damageProfiles") or {},
        "traitVariables": (c.get("globalValues") or {}).get("traitVariables") or {},
    }


# --- accès brut ---

def unit(uid: str) -> dict | None:
    idx = _index()
    for kind in ("lineup", "npc", "summons"):
        if uid in idx[kind]:
            return {"id": uid, "kind": kind, **idx[kind][uid]}
    return None


def ability(aid: str) -> dict | None:
    a = _index()["abilities"].get(aid)
    return None if a is None else {"id": aid, **a}


def damage_profile(name: str) -> dict | None:
    return _index()["damageProfiles"].get(name)


def trait(tid: str) -> dict:
    tv = _index()["traitVariables"]
    low = tid.lower()
    matched = {k: v for k, v in tv.items() if k.lower().startswith(low)}
    return {"id": tid, "variables": matched}


def global_value(key: str):
    """Scalaire global de combat (`clientGameConfig.globalValues[key]`) — constantes non rattachées à un
    trait/ability (ex. `actOfFaithExtraCritChance`/`actOfFaithExtraCritDmgPct`, `overkillDmgPctOfHealth`,
    `meltaDamageExtraDmgPct`…). Distinct de `traitVariables` (que lit `trait()`). None si absent."""
    return ((_cfg().get("globalValues")) or {}).get(key)


def all_unit_ids() -> dict:
    idx = _index()
    return {k: sorted(idx[k].keys()) for k in ("lineup", "npc", "summons")}


# --- résolution unitId par clé OU nom d'affichage (ex. 'Actus' -> 'admecManipulus') ---

@functools.lru_cache(maxsize=1)
def _name_to_id() -> dict:
    """nom d'affichage (lower) -> unitId. lineup prioritaire sur npc/summons."""
    idx = _index()
    out: dict = {}
    for kind in ("lineup", "npc", "summons"):
        for uid, u in idx[kind].items():
            nm = str(u.get("name") or "").strip().lower()
            if nm:
                out.setdefault(nm, uid)
    return out


def _match_units(query: str) -> list[tuple[str, str]]:
    """(uid, name) dont l'id OU le nom d'affichage contient `query` (sous-chaîne,
    insensible à la casse). Sert aux suggestions quand la requête est ambiguë."""
    idx = _index()
    q = query.lower()
    seen: set = set()
    out: list = []
    for kind in ("lineup", "npc", "summons"):
        for uid, u in idx[kind].items():
            nm = str(u.get("name") or "")
            if (q in uid.lower() or q in nm.lower()) and uid not in seen:
                seen.add(uid)
                out.append((uid, nm))
    return out


def resolve_unit_id(query: str) -> str | None:
    """unitId depuis une clé EXACTE (`admecManipulus`), sinon un NOM d'affichage
    exact (`Actus` -> `admecManipulus`), sinon une sous-chaîne UNIQUE (id ou nom).
    Ambigu ou absent -> None (le CLI proposera alors la liste des candidats)."""
    idx = _index()
    if any(query in idx[k] for k in ("lineup", "npc", "summons")):
        return query
    ni = _name_to_id()
    if query.lower() in ni:
        return ni[query.lower()]
    cands = _match_units(query)
    return cands[0][0] if len(cands) == 1 else None


# --- descriptions i2 (texte de RÈGLES, pas juste les chiffres) ---
# Le gameconfig ne porte QUE les mécaniques (nrOfHits/range/profiles). Le texte
# lisible (« Si Kharn a tué un ennemi… auto move+attaque ») vit dans la
# localisation i2 du jeu, dumpée dans data/i2_en.json. La recon DOIT croiser les
# deux : sans le texte i2, on rate les conditionnels (snowball TheBetrayer,
# triggers, auto-attaques de fin de tour, etc.).

@functools.lru_cache(maxsize=1)
def _i2() -> dict:
    p = Path(__file__).resolve().parents[2] / "data" / "i2_en.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


_STYLE_RE = re.compile(r"</?style[^>]*>")
_TOKEN_RE = re.compile(r"\{\[([A-Za-z0-9_]+)\]\}")


def _i2_text(key: str) -> str | None:
    return _i2().get(key)


def ability_description(aid: str, level: int | None = None) -> str | None:
    """Texte de règles d'une ability (i2 `Abilities/<id>_CurrentLevelDescription`),
    placeholders `{[nrOfHits]}`/`{[minDmg]}`/`{[range]}`… remplis depuis le
    gameconfig (constants + variables au niveau `level`, défaut = max), styles i2
    retirés, espaces normalisés. None si pas de description i2."""
    tmpl = (_i2_text(f"Abilities/{aid}_CurrentLevelDescription")
            or _i2_text(f"Abilities/{aid}_Description"))
    if not tmpl:
        return None
    a = ability(aid) or {}
    consts = a.get("constants") or {}
    variables = a.get("variables") or {}

    def val(key: str):
        if key in consts:
            return consts[key]
        v = variables.get(key)
        if isinstance(v, list) and v:
            i = (len(v) - 1) if level is None else max(0, min(level, len(v) - 1))
            return v[i]
        return v if v is not None else "{[" + key + "]}"

    txt = _TOKEN_RE.sub(lambda m: str(val(m.group(1))), tmpl)
    return " ".join(_STYLE_RE.sub("", txt).split())


def trait_description(tid: str) -> str | None:
    """Texte de règles d'un trait (i2 `Traits/<id>_Description`)."""
    tmpl = _i2_text(f"Traits/{tid}_Description")
    if not tmpl:
        return None
    return " ".join(_STYLE_RE.sub("", _TOKEN_RE.sub(
        lambda m: "{[" + m.group(1) + "]}", tmpl)).split())


# --- cartes compactes (lisibles par l'oracle) ---

def _dmg_curve(adef: dict) -> str | None:
    v = adef.get("variables") or {}
    mn, mx = v.get("minDmg"), v.get("maxDmg")
    if isinstance(mn, list) and isinstance(mx, list) and mn and mx:
        return f"dmg {mn[0]}-{mx[0]} (lvl1) -> {mn[-1]}-{mx[-1]} (lvl{len(mn)})"
    return None


def card_ability(aid: str) -> str:
    a = ability(aid)
    if not a:
        alt = _auto_resolve(aid)
        if alt:
            return f"{aid}: pas une ability. {alt}"
        return f"{aid}: (introuvable — ni ability/trait/effet/unité)"
    parts = [aid]
    if a.get("attackRangeType"):
        parts.append(a["attackRangeType"])
    c = a.get("constants") or {}
    if c:
        prof = c.get("damageProfile")
        if prof:
            dp = damage_profile(prof) or {}
            parts.append(f"profile={prof}{dp if dp else ''}")
        rest = {k: v for k, v in c.items() if k != "damageProfile"}
        if rest:
            parts.append(json.dumps(rest, separators=(",", ":")))
    cur = _dmg_curve(a)
    if cur:
        parts.append(cur)
    line = "  ".join(parts)
    desc = ability_description(aid)
    if desc:
        line += f"\n      « {desc} »"
    return line


def card_unit(query: str) -> str:
    uid = resolve_unit_id(query)
    if uid is None:
        alt = _auto_resolve(query)              # peut-être une ability/trait/effet, pas une unité
        if alt:
            return f"{query}: pas une unité. {alt}"
        m = _match_units(query)
        if m:
            opts = ", ".join(f"{u} «{n}»" for u, n in m[:12])
            more = f" … (+{len(m) - 12})" if len(m) > 12 else ""
            return f"{query}: ambigu/inconnu — candidats : {opts}{more}"
        return f"{query}: (introuvable — ni unité/ability/trait/effet)"
    u = unit(uid)
    if not u:
        return f"{uid}: (unit inconnue)"
    lines = [
        f"{uid} «{u.get('name')}» [{u.get('kind')}] "
        f"{u.get('FactionId')}/{u.get('GrandAllianceId')} "
        f"move={u.get('Movement')} rarity={u.get('BaseRarity', '-')}"
    ]
    weapons = u.get("weapons") or []
    if weapons:
        ws = []
        for w in weapons:
            dp = damage_profile(w.get("DamageProfile")) or {}
            rng = f"r{w['Range']}" if w.get("Range") else "melee"
            ws.append(f"{w.get('hits')}x {w.get('DamageProfile')}"
                      f"{dp if dp else ''} ({rng})")
        lines.append("  weapons: " + ", ".join(ws))
    for tid in (u.get("traits") or []):
        td = trait_description(tid)
        lines.append(f"  [trait] {tid}" + (f" — « {td} »" if td else ""))
    for aid in (u.get("activeAbilities") or []):
        lines.append("  [active]  " + card_ability(aid))
    for aid in (u.get("passiveAbilities") or []):
        lines.append("  [passive] " + card_ability(aid))
    return "\n".join(lines)


def card_trait(tid: str) -> str:
    t = trait(tid)
    desc = trait_description(tid)
    if not desc and not t["variables"]:        # ni description i2 ni variable -> pas un trait connu
        alt = _auto_resolve(tid)
        if alt:
            return f"{tid}: pas un trait. {alt}"
    head = (f"{tid}: " + json.dumps(t["variables"], separators=(",", ":"))
            if t["variables"]
            else f"{tid}: (pas de variable traitVariables)")
    return head + (f"\n  « {desc} »" if desc else "")


def recon_effect(name: str) -> str:
    """Recon d'un EFFET par son nom `EffectType` (ce que `decisionView` expose
    dans le champ `effects`, ex. 'ContagionsOfNurgle_ArmorReduction1',
    'HeavyRailRifle_PendingTarget', 'TeleportStrike_TeleportingIn', 'Ice').

    Un effet est nommé `<Ability/Trait>_<suffixe>` : on retrouve sa SOURCE en
    rognant le suffixe (préfixes décroissants) et on imprime la carte de
    l'ability ou du trait source (chiffres gameconfig + texte de règles i2).
    Les effets « moteur » purs (Ice, Stunned, Taunted_*) sans ability/trait
    source → fallback i2 direct, sinon à enrichir au wiki."""
    parts = name.split("_")
    for i in range(len(parts), 0, -1):
        cand = "_".join(parts[:i])
        if ability(cand):
            return f"[effet] {name}  ←  ability «{cand}»\n  " + card_ability(cand)
        if trait_description(cand) or trait(cand)["variables"]:
            return f"[effet] {name}  ←  trait «{cand}»\n  " + card_trait(cand)
    # Effet moteur sans ability/trait source : tenter une description i2 directe.
    direct = (_i2_text(f"Traits/{name}_Description")
              or _i2_text(f"Abilities/{name}_Description"))
    if direct:
        clean = " ".join(_STYLE_RE.sub("", _TOKEN_RE.sub(
            lambda m: "{[" + m.group(1) + "]}", direct)).split())
        return f"[effet] {name}  (effet moteur)\n  « {clean} »"
    return (f"[effet] {name}  (effet moteur — pas d'ability/trait source ni "
            f"description i2 ; sémantique à enrichir au wiki)")


def _auto_resolve(name: str) -> str | None:
    """Filet ANTI-FUMBLE : `name` introuvable dans le mode demandé ? on le cherche
    dans les AUTRES catégories (ability / trait / effet / unité) et on renvoie sa
    carte, avec une note disant ce que c'est. Évite à l'agent de DEVINER des noms
    au hasard quand il a juste tapé le mauvais flag (ex. `--ability TeleportStrike`
    alors que c'est un TRAIT). None si vraiment introuvable partout."""
    if ability(name):
        return "→ c'est une ABILITY :\n  " + card_ability(name)
    if trait_description(name) or trait(name)["variables"]:
        return "→ c'est un TRAIT :\n  " + card_trait(name)
    eff = recon_effect(name)
    if "pas d'ability/trait source" not in eff:
        return "→ résolu comme EFFET :\n  " + eff
    uid = resolve_unit_id(name)
    if uid:
        return "→ c'est une UNITÉ :\n  " + card_unit(name)
    return None


def _demo(argv: list[str]) -> int:
    if argv:
        for uid in argv:
            print(card_unit(uid)); print()
        return 0
    ids = all_unit_ids()
    print(f"[gameconfig] {_find_gameconfig().name}")
    print(f"[counts] lineup={len(ids['lineup'])} npc={len(ids['npc'])} "
          f"summons={len(ids['summons'])} "
          f"abilities={len(_index()['abilities'])} "
          f"damageProfiles={len(_index()['damageProfiles'])} "
          f"traitVariables={len(_index()['traitVariables'])}")
    print("\n=== CARTE UNIT (héros) ===")
    print(card_unit("custoVexilusPraetor"))
    print("\n=== CARTE UNIT (npc) ===")
    print(card_unit("necroNpc1Warrior"))
    print("\n=== CARTE ABILITY ===")
    print(card_ability("GauntletsOfUltramar"))
    print(card_ability("PsychicMaelstrom"))
    print("\n=== CARTE TRAIT ===")
    print(card_trait("Resilient"))
    print(card_trait("BeastSlayer"))
    return 0


def main(argv: list[str]) -> int:
    """CLI. Modes :
      gameconfig.py <unitId|nom>...    → carte(s) d'unité (kit complet : traits+actifs+passifs décodés).
                                          Accepte la CLÉ (admecManipulus) OU le NOM (Actus).
      gameconfig.py --unit <id|nom>... → idem, explicite (suggère des candidats si ambigu/inconnu)
      gameconfig.py --effect <name>... → recon d'un effet (decisionView.effects)
      gameconfig.py --ability <name>...→ carte d'une ability par nom
      gameconfig.py --trait <name>...  → carte d'un trait par nom
    Sans argument : démo."""
    if argv and argv[0] in ("--unit", "-u"):
        if len(argv) < 2:
            print("usage: gameconfig.py --unit <unitId|nom>...", file=sys.stderr)
            return 2
        for name in argv[1:]:
            print(card_unit(name))
            print()
        return 0
    if argv and argv[0] in ("--effect", "-e"):
        if len(argv) < 2:
            print("usage: gameconfig.py --effect <EffectName>...", file=sys.stderr)
            return 2
        for name in argv[1:]:
            print(recon_effect(name)); print()
        return 0
    if argv and argv[0] in ("--ability", "-a"):
        for name in argv[1:]:
            print(card_ability(name)); print()
        return 0
    if argv and argv[0] in ("--trait", "-t"):
        for name in argv[1:]:
            print(card_trait(name)); print()
        return 0
    return _demo(argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
