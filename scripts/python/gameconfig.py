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

Usage : python scripts/python/gameconfig.py [unitId]
"""
from __future__ import annotations

import functools
import json
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


def all_unit_ids() -> dict:
    idx = _index()
    return {k: sorted(idx[k].keys()) for k in ("lineup", "npc", "summons")}


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
        return f"{aid}: (inconnue dans gameconfig)"
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
    return "  ".join(parts)


def card_unit(uid: str) -> str:
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
    if u.get("traits"):
        lines.append("  traits: " + ", ".join(u["traits"]))
    for aid in (u.get("activeAbilities") or []):
        lines.append("  [active]  " + card_ability(aid))
    for aid in (u.get("passiveAbilities") or []):
        lines.append("  [passive] " + card_ability(aid))
    return "\n".join(lines)


def card_trait(tid: str) -> str:
    t = trait(tid)
    if not t["variables"]:
        return f"{tid}: (pas de variable traitVariables — sémantique à enrichir au wiki)"
    return f"{tid}: " + json.dumps(t["variables"], separators=(",", ":"))


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


if __name__ == "__main__":
    sys.exit(_demo(sys.argv[1:]))
