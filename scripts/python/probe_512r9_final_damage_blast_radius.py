"""#512-r9 -- RAYON DE SOUFFLE de l'ajout d'`On(0x42 = EventTriggerType.FinalDamage)` au vecteur
`amount` (`damage_ops/normal_like.py`).

POURQUOI CE PROBE EXISTE, AVANT LE PATCH ET PAS APRES
-----------------------------------------------------
`#512-r7` a mesure 24 couples (classe, event) pour 0 divergence AVANT de deplacer `On(9)`. Ajouter
un evenement ENTIER a un vecteur est le meme geste, en plus violent : tout ecouteur de l'event 66
se met a fire sur un chemin qui ne l'atteignait pas. On recense donc QUI ecoute -- DEPUIS LE CODE,
jamais une liste recopiee -- avant de toucher au foyer.

CE QU'IL MESURE
---------------
  etape 1 : toutes les classes-triggers du port qui ecoutent `event_id == 66` (ou dont `event_ids`
            le contient), avec leur VOIE de registration et la CLE du registre ;
  etape 2 : les porteurs gameconfig de chaque cle, ventiles par `kind` (lineup / npc / summon) --
            c'est ce qui dit si l'ecart est CONFRONTABLE ;
  etape 3 : les SITES d'emission de `On(66)` cote port, confrontes aux XREFS NATIVES de
            `IdunBattle.Operations.ADamageOperation$$RegisterFinalDamage`. Les xrefs entrantes sont
            EXHAUSTIVES (`AttackDamageOperation$$Execute`, `AbilityDamageOperation$$Execute`) et le
            port mirroite la premiere DEUX fois (`damage_ops/normal.py` = attaque normale,
            `damage_ops/normal_like.py` = mode `amount`) et la seconde UNE fois
            (`damage_ops/ability.py`) -> l'attendu est **3** sites, un par vecteur d'attaque.
            ⚠ C'est un INVARIANT, pas un inventaire : un vecteur d'attaque qui perdrait son
            emission ferait rc 1. Les vecteurs sont DERIVES (les modules de `damage_ops/` qui
            portent une facade d'attaque), jamais listes.

Sortie ASCII pure (console cp1252). rc = 0 si l'invariant de l'etape 3 tient, 1 sinon.

Usage (offline, aucun runner, aucune session) :
    python probe_512r9_final_damage_blast_radius.py
    python probe_512r9_final_damage_blast_radius.py --no-carriers
"""
from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import gameconfig as GC  # noqa: E402
from engine.dsl.event_trigger_type import EventTriggerType  # noqa: E402
from engine.runner.operations.triggers.dispatch.registry import (  # noqa: E402
    TRAIT_TRIGGERS, ABILITY_TRIGGERS, ACTIVE_ABILITY_TRIGGERS,
    RELIC_ABILITY_TRIGGERS, GLOBAL_TRIGGERS, EFFECT_TRIGGERS)

ON_FINAL_DAMAGE = int(EventTriggerType.FinalDamage)      # 0x42 = 66

#: les vecteurs d'ATTAQUE du port -- chacun mirroite une des deux `Execute` natives, donc chacun
#: doit porter l'emission. DERIVE : le dossier `damage_ops/` moins les modules sans facade
#: d'attaque (`__init__` = agregat, `additional_hits` = sous-operation de groupe, qui vit DANS
#: l'operation et n'a donc pas de `RegisterFinalDamage` propre).
DOSSIER_VECTEURS = _HERE / "engine" / "runner" / "operations" / "damage_ops"
#: la facade qui, dans un module de `damage_ops/`, en fait un VECTEUR D'ATTAQUE (par opposition a
#: `execute_direct`, un DoT : le natif n'y appelle pas `RegisterFinalDamage`).
FACADES_ATTAQUE = ("execute", "execute_ability_attack", "execute_normal_like")


def _listens(cls) -> bool:
    """La classe ecoute-t-elle `On(66)` ? Mirror du gate de `evaluate_trigger_operation`."""
    ev_id = getattr(cls, "event_id", None)
    if ev_id is not None and int(ev_id) == ON_FINAL_DAMAGE:
        return True
    return ON_FINAL_DAMAGE in tuple(int(x) for x in (getattr(cls, "event_ids", ()) or ()))


def collecter_ecouteurs() -> "list[tuple[str, str, type]]":
    """(voie, cle, classe) pour toute classe-trigger qui ecoute `On(66)`."""
    out: "list[tuple[str, str, type]]" = []
    for voie, reg in (("trait", TRAIT_TRIGGERS), ("passive", ABILITY_TRIGGERS),
                      ("active", ACTIVE_ABILITY_TRIGGERS), ("relic", RELIC_ABILITY_TRIGGERS)):
        for key, classes in reg.items():
            for cls in classes:
                if _listens(cls):
                    out.append((voie, str(key), cls))
    for cls in GLOBAL_TRIGGERS:
        if _listens(cls):
            out.append(("global", "-", cls))
    for eff_type, classes in EFFECT_TRIGGERS.items():
        for cls in classes:
            if _listens(cls):
                out.append(("effect", str(int(eff_type)), cls))
    return out


def _porteurs(voie: str, key: str) -> "dict[str, list[str]]":
    """Porteurs gameconfig de la cle, ventiles par `kind`. Vide pour les voies non derivables du
    gameconfig (`global`, `effect` : l'effet est POSE en bataille, son porteur se remonte par son
    poseur)."""
    field = {"trait": "traits", "passive": "passiveAbilities",
             "active": "activeAbilities", "relic": "relicAbilities"}.get(voie)
    if field is None:
        return {}
    out: "dict[str, list[str]]" = {}
    for kind, uids in (GC.all_unit_ids() or {}).items():
        for uid in uids:
            u = GC.unit(uid) or {}
            if key in (u.get(field) or []):
                out.setdefault(str(kind), []).append(str(uid))
    return out


def _appelle_final_damage(arbre: ast.AST) -> "list[int]":
    """Lignes ou le module appelle `final_damage_triggers` -- en forme B (`<mod>.final_damage_
    triggers(...)`, un `ast.Attribute`) OU en forme A (`final_damage_triggers(...)`, un `ast.Name`).

    ⚠ LES DEUX FORMES, ET C'EST LE POINT : un recenseur qui ne visiterait que `ast.Name` serait
    aveugle a la forme B -- or c'est EXACTEMENT celle qu'utilisent les trois vecteurs (`from
    ..triggers.dispatch import attack as attack_dispatch` puis `attack_dispatch.final_damage_
    triggers(...)`), pour que `probe_437*` puisse les substituer. Il rendrait donc `0 site` et
    passerait pour vert sur un port qui n'emet rien."""
    lignes: "list[int]" = []
    for n in ast.walk(arbre):
        if not isinstance(n, ast.Call):
            continue
        f = n.func
        nom = (f.attr if isinstance(f, ast.Attribute)
               else (f.id if isinstance(f, ast.Name) else None))
        if nom == "final_damage_triggers":
            lignes.append(n.lineno)
    return lignes


def _definit_une_facade_attaque(arbre: ast.AST) -> "list[str]":
    """Les facades d'ATTAQUE que ce module definit (celles qui montent une `AttackDamageOperation`/
    `AbilityDamageOperation` native, donc celles auxquelles `RegisterFinalDamage` s'applique)."""
    vus = []
    for n in ast.walk(arbre):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in FACADES_ATTAQUE:
            vus.append(n.name)
    return sorted(set(vus))


def mesurer_sites() -> "dict[str, dict]":
    """Par module de `damage_ops/`, les facades d'attaque definies et les lignes d'emission."""
    out: "dict[str, dict]" = {}
    for p in sorted(DOSSIER_VECTEURS.glob("*.py")):
        try:
            arbre = ast.parse(p.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError, OSError):
            continue
        facades = _definit_une_facade_attaque(arbre)
        if not facades:
            continue
        out[p.name] = {"facades": facades, "lignes": _appelle_final_damage(arbre)}
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="#512-r9 blast radius of On(66 = FinalDamage)")
    ap.add_argument("--no-carriers", action="store_true", help="skip gameconfig carrier lookup")
    a = ap.parse_args()

    print("=" * 78)
    print("ETAPE 1 -- ECOUTEURS de On(0x42 = 66 = EventTriggerType.FinalDamage)")
    print("=" * 78)
    ecouteurs = collecter_ecouteurs()
    print("total: %d classes-triggers" % len(ecouteurs))
    for voie, key, cls in sorted(ecouteurs, key=lambda t: (t[0], t[1], t[2].__name__)):
        print("  [%-7s] %-28s %s" % (voie, key, cls.__name__))
        print("            module: %s" % cls.__module__)
    print("")

    if not a.no_carriers:
        print("=" * 78)
        print("ETAPE 2 -- PORTEURS gameconfig par cle (kind: nb, exemples)")
        print("=" * 78)
        for voie, key, cls in sorted(ecouteurs, key=lambda t: (t[0], t[1], t[2].__name__)):
            if voie in ("global", "effect"):
                print("  [%-7s] %-28s -> voie NON derivable du gameconfig (poseur a remonter)"
                      % (voie, key))
                continue
            car = _porteurs(voie, key)
            if not car:
                print("  [%-7s] %-28s -> 0 porteur gameconfig" % (voie, key))
                continue
            tot = sum(len(v) for v in car.values())
            print("  [%-7s] %-28s -> %d porteurs" % (voie, key, tot))
            for kind in sorted(car):
                ids = sorted(car[kind])
                print("            %-8s %3d  %s" % (kind, len(ids), ", ".join(ids[:6])
                                                    + (" ..." if len(ids) > 6 else "")))
        print("")

    print("=" * 78)
    print("ETAPE 3 -- SITES D'EMISSION, un par VECTEUR D'ATTAQUE (invariant)")
    print("=" * 78)
    sites = mesurer_sites()
    if not sites:
        print("  AUCUN module de damage_ops/ ne definit de facade d'attaque -- le recenseur ne")
        print("  visite plus rien (un zero de recenseur n'est pas une preuve).")
        return 1
    muets = []
    for nom in sorted(sites):
        d = sites[nom]
        etat = "OK  %d emission(s) L%s" % (len(d["lignes"]),
                                           ",".join(str(x) for x in d["lignes"])) \
            if d["lignes"] else "MUET -- aucun On(66)"
        print("  %-18s facades=%-40s %s" % (nom, ",".join(d["facades"]), etat))
        if not d["lignes"]:
            muets.append(nom)
    print("")
    if muets:
        print("ECHEC : %d vecteur(s) d'attaque n'emet(tent) AUCUN On(0x42) : %s"
              % (len(muets), ", ".join(muets)))
        print("  Le foyer natif `IdunBattle.Operations.ADamageOperation$$RegisterFinalDamage` est")
        print("  sur la base COMMUNE : les DEUX `Execute` l'appellent, donc TOUT vecteur qui")
        print("  mirroite l'une des deux doit l'emettre (residu #512-r9).")
        return 1
    print("OK : les %d vecteurs d'attaque de damage_ops/ emettent On(0x42)." % len(sites))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
