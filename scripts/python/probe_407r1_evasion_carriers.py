#!/usr/bin/env python
"""probe #407-r1 -- le regime `evasionChance > 0` a-t-il un PORTEUR ?

QUESTION (binaire) : `IdunBattle.Core.Services.DamagePrediction$$CalculateDamageOperation`
evalue l'ESQUIVE avant le BLOCK (slot 1 `CalculateEvasionChance`, slot 3 `ApplyRandomEvasion`) et
ne descend au block que si l'esquive n'a pas eu lieu. A `evasionChance == 0` l'esquive ne consomme
AUCUN tirage et rend le degat inchange -> les deux ordres coincident. La question de portage se
reduit donc a : **une unite peut-elle arriver en bataille avec `GetStat(unit, 15) > 0` ?**

CHAINE NATIVE, lue de bout en bout (rnca9r7q6c) :
  * `IdunBattle.Core.Services.DamageCalculations$$CalculateEvasionChance`
        = `IdunBattle.Entities.UnitExtensions$$GetStat(defender, 0xf, ...)` -- corps d'UNE ligne ;
  * `IdunBattle.Entities.UnitExtensions$$GetStatComponent` : `case 0xf` ->
        `IdunBattle.Entities.Components.EvasionChanceComponent` (un `StatComponent`, cf.
        `data/symbols/<build>/frida/classes.tsv`) ;
  * `IdunBattle.Entities.Blueprints$$Unit` ATTACHE ce composant a toute unite (`UnitEntity+0x78`)
    -- le composant EXISTE donc toujours, avec sa valeur initiale ;
  * la valeur ne peut monter que par SEED (stat initiale de la `BattleConfiguration`) ou par
    MODIFICATION (`IdunBattle.Entities.UnitExtensions$$ApplyStatModifier`, alimente soit par
    `ApplyStatModifiers` au montage, soit par les foyers DSL `AddStaticStatModifierEffect*` /
    `AddDynamicStatModifierEffect*` / `AddOrUpdateStaticStatModifierEffect` /
    `AddStatOverrideEffect*`, dont le `statType` est un LITTERAL du `CreateBehaviour`).

Ce probe balaye les DEUX voies sur les sources disponibles offline, et ne conclut JAMAIS d'un seul
recensement (cf. #323 -- un « 0 porteur » rendu par un outil unique ne prouve rien) :

  A. seed BC (`data/seed-bc.json`) : le SCHEMA d'unite porte-t-il seulement un champ d'evasion ?
     (sans champ, la voie SEED est fermee par construction)
  B. gameconfig (source de verite du jeu) : stats d'unite, constantes d'ability, et balayage
     TEXTUEL du document entier ;
  C. enums natifs (`data/symbols/<build>/frida/enums.tsv`) : un `EffectType` / `ActiveAbilityType` /
     `TriggeredAbilityType` / `UnitTrait` nomme-t-il l'esquive ?
  D. i2 (textes joueur) : le vocabulaire visible du joueur.

La voie E -- « un `CreateBehaviour` natif passe le littéral 15 comme `statType` » -- se lit dans
ghidra et n'est pas rejouable ici ; son resultat (2026-08-01, rnca9r7q6c) est RAPPELE en fin de
sortie pour que le lecteur ait les cinq voies sous les yeux.

Aucun runner, aucun RPC : 100 % offline. Sortie ASCII (cp1252).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import gameconfig as gc  # noqa: E402
from engine.entities.stats import StatType  # noqa: E402

_REPO = _HERE.parent.parent

# Le StatType vise. Mirror de `IdunBattle.Entities.Enum.StatType` : `15=EvasionChance`.
EVASION_STAT = int(StatType.EVASION_CHANCE)

# Vocabulaire de l'esquive, cote DONNEES comme cote TEXTE.
_WORDS = ("evasion", "evade", "evading", "dodge", "dodging", "miss chance")
_RX_WORDS = re.compile("|".join(_WORDS), re.I)

# Un enum qui NOMME l'esquive n'est un indice de PORTEUR que s'il decrit un effet, une ability
# ou un trait. `StatType` porte la stat elle-meme (c'est la cible, pas la source) et `TagKey`
# est le canal de TELEMETRIE du stream (`140=Attack_DidEvade`, ce que les tests live lisent deja
# via `td["Attack_DidEvade"]`) : ni l'un ni l'autre ne POSE d'evasion.
_ENUM_NOT_A_CARRIER = ("StatType", "TagKey", "StatPart")

# Voie E -- resultat de la lecture ghidra (non rejouable offline, cite pour memoire).
_GHIDRA_NOTE = [
    "aucune occurrence de `DAT_0000000f` dans TOUT le decompile (0 / 65000 fonctions) --",
    "  c'est l'une des DEUX formes sous lesquelles ghidra rend un litteral de statType",
    "  (mesure de calibration : `BeastSlayerAbility$$CreateAddBlockEffectBehaviour` rend le",
    "  statType 7 en `(void *)0x7` et le statType 8 en `&DAT_00000008`) ;",
    "`(void *)0xf` apparait dans 64 fonctions, dont UNE SEULE touche un foyer de stat-mod :",
    "  `ShroudPsalmAbility$$ExecuteBehaviour` -- et son `AddStaticStatModifierEffect` y passe",
    "  `(void *)0x10` (FixedArmor), pas 0xf ;",
    "les ~75 appelants des 10 foyers d'ecriture de stat (les 3 surcharges d'`AddStaticStat",
    "  ModifierEffect`, les 2 d'`...ToOwner`, les 2 d'`AddDynamic...`, `AddDynamic...ToOwner`,",
    "  `AddOrUpdateStaticStatModifierEffect`, `AddStatOverrideEffect(ToOwner)`) ont ete listes",
    "  par xrefs entrantes : aucun ne passe 15 ;",
    "`UnitExtensions$$ApplyStatModifier` (le foyer BAS NIVEAU) n'a que DEUX appelants :",
    "  `ApplyStatModifiers` (le seeding depuis la BC, dont le schema n'a pas d'evasion) et",
    "  `idun.tests.trait_impervious_test` (du code de TEST, hors jeu).",
]


def _walk(node, path=""):
    """Parcours generique (dict/list) -> (chemin, cle, valeur scalaire)."""
    if isinstance(node, dict):
        for k, v in node.items():
            p = f"{path}.{k}" if path else str(k)
            if isinstance(v, (dict, list)):
                yield from _walk(v, p)
            else:
                yield p, str(k), v
    elif isinstance(node, list):
        for i, v in enumerate(node):
            p = f"{path}[{i}]"
            if isinstance(v, (dict, list)):
                yield from _walk(v, p)
            else:
                yield p, "", v


def scan_seed_bc() -> dict:
    """Voie A -- le seed BC versionne. On rend le SCHEMA d'unite : sans champ d'evasion, aucune
    valeur ne peut descendre de la `BattleConfiguration` vers `EvasionChanceComponent`."""
    p = _REPO / "data" / "seed-bc.json"
    if not p.exists():
        return {"present": False}
    bc = json.loads(p.read_text(encoding="utf-8"))
    units = bc.get("Units") or []
    schema = sorted({k for u in units if isinstance(u, dict) for k in u})
    hits = [(path, val) for path, key, val in _walk(bc) if _RX_WORDS.search(str(key))]
    return {"present": True, "n_units": len(units), "unit_schema": schema, "hits": hits,
            "schema_has_evasion": [k for k in schema if _RX_WORDS.search(k)]}


def scan_gameconfig() -> dict:
    """Voies B -- le gameconfig du jeu (source de verite : stats d'unite + abilities + texte)."""
    cfg = gc._cfg()
    idx = gc._index()
    out = {"unit_stat_keys": set(), "unit_hits": [], "const_hits": [],
           "text_hits": 0, "text_samples": [], "n_units": 0, "n_abilities": 0}
    for bucket in ("lineup", "npc", "summons"):
        for uid, u in (idx.get(bucket) or {}).items():
            out["n_units"] += 1
            for path, key, val in _walk(u):
                if _RX_WORDS.search(str(key)) and val not in (0, "0", None, False):
                    out["unit_hits"].append((bucket, uid, path, val))
                if "stat" in path.lower() and isinstance(val, (int, float)):
                    out["unit_stat_keys"].add(key)
    # B4 : le gameconfig EXPRIME-T-IL seulement un StatType ? Si aucun champ ne porte d'index
    # d'enum `StatType`, alors AUCUNE ability ne peut viser une stat PAR DONNEE -- tout statType
    # est un LITTERAL du natif, et le recensement se rabat entierement sur la voie E (ghidra).
    # C'est ce qui BORNE la question : sans cette mesure, un « 0 » du balayage textuel pourrait
    # n'etre que l'angle mort d'un champ numerique (le faux negatif de #323).
    _names = {m.name: int(m) for m in StatType}
    out["stat_typed_fields"] = []
    for aid, a in (idx.get("abilities") or {}).items():
        out["n_abilities"] += 1
        for path, key, val in _walk(a):
            if _RX_WORDS.search(str(val)) or _RX_WORDS.search(str(key)):
                out["const_hits"].append((aid, path, key, str(val)[:80]))
            if re.search(r"stat(type)?$|^stat|targetstat|affectedstat", key, re.I) \
                    or (isinstance(val, str) and val in _names):
                out["stat_typed_fields"].append((aid, path, key, str(val)[:60]))
    raw = json.dumps(cfg)
    out["doc_bytes"] = len(raw)
    for m in _RX_WORDS.finditer(raw):
        out["text_hits"] += 1
        if len(out["text_samples"]) < 8:
            out["text_samples"].append(raw[max(0, m.start() - 80):m.end() + 80])
    out["unit_stat_keys"] = sorted(out["unit_stat_keys"])
    return out


def scan_enums() -> dict:
    """Voie C -- les enums natifs dumpes. Un porteur d'esquive laisserait forcement une trace
    dans `EffectType` (l'effet applique), `ActiveAbilityType`/`TriggeredAbilityType` (l'ability)
    ou `UnitTrait`. Le seul `Evasion*` attendu est `StatType 15` lui-meme."""
    build = (_REPO / "data" / "symbols")
    cands = sorted(p for p in build.glob("*/frida/enums.tsv"))
    if not cands:
        return {"present": False}
    out = {"present": True, "files": [], "hits": []}
    for p in cands:
        out["files"].append(str(p.relative_to(_REPO)))
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            parts = line.split("\t")
            if len(parts) < 2 or not parts[0].startswith("IdunBattle"):
                continue
            members = [m for m in parts[1].split(",") if _RX_WORDS.search(m)]
            if members:
                out["hits"].append((p.parent.parent.name, parts[0], members))
    return out


def scan_i2() -> dict:
    """Voie D -- les textes joueur. Un libelle vivant ne prouve pas un porteur, mais son absence
    totale du vocabulaire d'ABILITY/TRAIT en est un indice fort."""
    p = _REPO / "data" / "i2_en.json"
    if not p.exists():
        return {"present": False}
    raw = p.read_text(encoding="utf-8")
    keys = [(m.group(1), m.group(2)[:90])
            for m in re.finditer(r'"([^"]+)"\s*:\s*"((?:[^"\\]|\\.)*)"', raw)
            if _RX_WORDS.search(m.group(1)) or _RX_WORDS.search(m.group(2))]
    gameplay = [(k, v) for k, v in keys
                if k.split("/")[0] in ("Abilities", "Traits", "Units", "Effects")]
    return {"present": True, "keys": keys, "gameplay": gameplay}


def main() -> int:
    ap = argparse.ArgumentParser(description="recensement des porteurs d'evasion (#407-r1)")
    ap.add_argument("--json", action="store_true", help="sortie machine")
    args = ap.parse_args()

    seed = scan_seed_bc()
    cfg = scan_gameconfig()
    enums = scan_enums()
    i2 = scan_i2()

    # Un porteur au sens de la gate de confrontabilite : quelque chose qui POSE une valeur > 0 sur
    # `EvasionChanceComponent`. `StatType`/`TagKey`/`StatPart` decrivent la stat et son canal
    # d'observation, pas une source -- les exclure (cf. `_ENUM_NOT_A_CARRIER`).
    carriers = (list(cfg["unit_hits"]) + list(cfg["const_hits"])
                + list(seed.get("schema_has_evasion") or [])
                + [h for h in enums.get("hits", [])
                   if not h[1].split(".")[-1] in _ENUM_NOT_A_CARRIER])

    if args.json:
        print(json.dumps({"seed_bc": seed, "gameconfig": cfg, "enums": enums, "i2": i2,
                          "carriers": carriers}, default=str)[:20000])
        return 0

    print("=== #407-r1 : porteurs du regime evasionChance > 0 (StatType %d) ===" % EVASION_STAT)
    print()
    print("-- A. seed BC (data/seed-bc.json) : la voie SEED --")
    if not seed.get("present"):
        print("   seed-bc.json ABSENT du checkout (entree versionnee attendue)")
    else:
        print("   unites: %d | champs du schema: %d" % (seed["n_units"], len(seed["unit_schema"])))
        print("   schema: %s" % ", ".join(seed["unit_schema"]))
        print("   champ d'evasion dans le schema : %s"
              % (seed["schema_has_evasion"] or "AUCUN -> voie SEED fermee par construction"))
        print("   occurrences du vocabulaire dans tout le BC : %d" % len(seed["hits"]))
    print()
    print("-- B. gameconfig (source de verite) --")
    print("   unites: %d | abilities: %d | document: %d octets"
          % (cfg["n_units"], cfg["n_abilities"], cfg["doc_bytes"]))
    print("   cles de stats d'unite : %s" % ", ".join(k for k in cfg["unit_stat_keys"] if k))
    print("   unites avec evasion > 0 : %d" % len(cfg["unit_hits"]))
    for h in cfg["unit_hits"][:20]:
        print("     %s" % (h,))
    print("   constantes d'ability nommant l'evasion : %d" % len(cfg["const_hits"]))
    for h in cfg["const_hits"][:20]:
        print("     %s" % (h,))
    print("   occurrences TEXTUELLES dans tout le document : %d" % cfg["text_hits"])
    for s in cfg["text_samples"]:
        print("     ... %s ..." % s.replace("\n", " "))
    print("   champs d'ability PORTANT un StatType : %d %s"
          % (len(cfg["stat_typed_fields"]),
             "-> aucune ability ne vise une stat PAR DONNEE : tout statType est un LITTERAL du "
             "natif (voie E)" if not cfg["stat_typed_fields"] else ""))
    for h in cfg["stat_typed_fields"][:20]:
        print("     %s" % (h,))
    print()
    print("-- C. enums natifs (EffectType / ActiveAbilityType / TriggeredAbilityType / ...) --")
    if not enums.get("present"):
        print("   enums.tsv ABSENT du checkout")
    else:
        print("   fichiers lus : %s" % ", ".join(enums["files"]))
        for build, name, members in enums["hits"]:
            print("     [%s] %-46s %s" % (build, name, members[:8]))
        non_stat = [h for h in enums["hits"]
                    if h[1].split(".")[-1] not in _ENUM_NOT_A_CARRIER]
        print("   enums SOURCE (Effect/Ability/Trait) nommant l'esquive : %s"
              % (non_stat or "AUCUN"))
        print("   NB : `TagKey 140=Attack_DidEvade` EST le canal live d'observation d'une esquive")
        print("        (deja lu par les tests block existants) -- un observateur, pas un poseur.")
    print()
    print("-- D. i2 (textes joueur) --")
    if not i2.get("present"):
        print("   i2_en.json ABSENT du checkout")
    else:
        print("   cles touchant le vocabulaire : %d (dont gameplay Abilities/Traits/Effects: %d)"
              % (len(i2["keys"]), len(i2["gameplay"])))
        for k, v in i2["gameplay"][:20]:
            print("     %s = %s" % (k, v))
        print("   NB : `UI/BattleFlyout_Evade` existe cote UI -- un libelle, pas un porteur.")
    print()
    print("-- E. decompile ghidra (lecture 2026-08-01, non rejouable ici) --")
    for line in _GHIDRA_NOTE:
        print("   %s" % line)
    print()
    print("VERDICT : %s" % ("ATTEIGNABLE -- porteur(s) trouve(s) : %s" % carriers[:5] if carriers
                            else "NON CONFRONTE -- aucun porteur sur les 5 voies balayees ; "
                                 "le regime evasionChance > 0 n'est atteint par AUCUNE unite"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
