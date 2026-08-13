"""Registre des unites NPC (et summons) avec leur KIT COMPLET et l'etat des DEUX FACES.

Pendant NPC de `audit_kit_coverage.py`, qui ne balaie que les 127 `lineup`. Le gisement npc est
le plus gros du parc (491 unites) et n'etait couvert par AUCUN audit : un npc n'est pas du
"decor", c'est l'adversaire que le moteur doit simuler fidelement, et c'est aussi le porteur
unique de nombreuses mecaniques qu'on confronte par GREFFE sur une unite du pool.

TOUT EST DERIVE, RIEN N'EST RECOPIE. Les predicats de couverture viennent des FOYERS EXISTANTS,
jamais d'une liste blanche locale -- la lecon de #951-r2 et #979 (un recenseur qui tient sa
propre liste de registres rate ceux qu'il ne connait pas, et rend un faux MANQUANT) :

  - face COMBAT active   -> `engine.runner.abilities.handler.ABILITY_CLASSES` (id ActiveAbilityType)
  - face DECISION active -> `decision_face_voies.face_portee` (FOYER UNIQUE, 14 voies PARTITIONNEES)
  - passifs              -> `audit_kit_coverage._passive_covered` (SIX canaux, dont l'attaque
                            normale substituee -- celui qui m'avait fait compter `TalonOfHorus`
                            manquante alors qu'elle est portee)
  - traits               -> les trois registres trait->X + effet homonyme, comme l'audit lineup

CE QUI N'EST PAS DERIVABLE ICI, et le document le DIT au lieu de rendre un zero (lecon #323) :
les voies `trait` (mapping natif hors gameconfig), `liveevent`, `summon` et `tile`. Un kit
affiche COMPLET l'est au sens des voies derivables du gameconfig, pas au sens absolu.

⚠ KIT GAMECONFIG != ENTITE EN BATAILLE. Ce registre lit le kit INTRINSEQUE. Le natif monte
`BC.Units[].PassiveAbilities`, pas le kit -- une GREFFE (`replace=True`) VIDE `PassiveAbilities`.
Pour savoir ce qu'une unite porte REELLEMENT en bataille, c'est le canal `unitAbilityStates`,
pas ce document.

Usage :
    python audit_npc_registry.py                  # npc -> docs/rl/npc-registry.md
    python audit_npc_registry.py --kind summons   # les 65 summons
    python audit_npc_registry.py --tsv <chemin>   # export TSV queryable en plus du markdown
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import decision_face_voies as DFV
import gameconfig as GC
import unit_map as UM
from audit_kit_coverage import (
    TRAIT_COMMON_MAX, _atteste, _has_effect_named_after, _passive_covered,
)
from engine.entities.active_ability_type import ActiveAbilityType
from engine.entities.effects.factory import TRAIT_DERIVED_ABILITIES, TRAIT_OWNER_EFFECTS
from engine.runner.abilities.handler import ABILITY_CLASSES
from engine.runner.operations.triggers.dispatch.registry import TRAIT_TRIGGERS

RACINE = Path(__file__).resolve().parents[2]
SORTIE = RACINE / "docs" / "rl" / "npc-registry.md"

#: nom -> ordinal `ActiveAbilityType`. Une active du gameconfig ABSENTE de cet enum n'est PAS une
#: anomalie de dump : c'est une INVERSION DE VOIE (l'ability est une `TriggeredAbilityType`
#: attribuee par une autre voie, cf. `Maugetar` 1498, relique d'`eldarMauganRa`). On la marque.
NOM_VERS_ID = {m.name: int(m) for m in ActiveAbilityType}

#: Les voies d'attribution qu'AUCUNE source offline ne rend (cf. `unit_map.VOIES_NON_COUVERTES`
#: et `case-323-unit-map-attribution-voies.md`). Les taire ferait lire ce registre comme exhaustif.
VOIES_ABSENTES = UM.VOIES_NON_COUVERTES


def _trait_couvert(t: str) -> bool:
    """Meme predicat que l'audit lineup, sur les memes registres."""
    return (t in TRAIT_TRIGGERS or t in TRAIT_DERIVED_ABILITIES
            or t in TRAIT_OWNER_EFFECTS or _has_effect_named_after(t))


def collecter(kind: str) -> list[dict]:
    """Une ligne par unite du `kind` demande, avec ses items ventilés par face."""
    voies_deci = DFV.voies_par_ability()
    kits = [k for k in UM.all_kits() if k["kind"] == kind]

    # Un trait porte par TOUT le monde est une couche globale du moteur, pas du travail de kit.
    # Meme seuil que l'audit lineup, pour que les deux documents se comparent.
    porteurs_trait: Counter = Counter()
    for k in kits:
        for t in k["traits"]:
            porteurs_trait[t] += 1

    lignes = []
    for k in kits:
        actives = []
        for nm in k["voies"].get("active", []):
            aid = NOM_VERS_ID.get(nm)
            att_c, att_d = _atteste("active-combat", nm), _atteste("active-decision", nm)
            actives.append({
                "name": nm, "id": aid,
                "combat": (aid is not None and aid in ABILITY_CLASSES) or att_c is not None,
                "decision": bool(DFV.face_portee(aid, nm, voies_deci)) or att_d is not None,
                # `id is None` = le nom n'est pas un `ActiveAbilityType` : voie inversee, a lire
                # dans un AUTRE enum. Ne jamais le confondre avec « ability inconnue ».
                "voie_inversee": aid is None,
            })
        passifs = []
        for nm in k["voies"].get("passive", []):
            att = _atteste("passif", nm)
            passifs.append({"name": nm, "covered": _passive_covered(nm) or att is not None})
        traits = []
        for t in k["traits"]:
            if porteurs_trait[t] > TRAIT_COMMON_MAX:
                continue
            att = _atteste("trait", t)
            traits.append({"name": t, "carriers": porteurs_trait[t],
                           "covered": _trait_couvert(t) or att is not None})

        manque_combat = (sum(1 for a in actives if not a["combat"])
                         + sum(1 for p in passifs if not p["covered"])
                         + sum(1 for t in traits if not t["covered"]))
        lignes.append({
            "id": k["id"], "name": k["name"], "faction": k["faction"] or "?",
            "alliance": k["alliance"] or "?", "rarity": k["rarity"], "movement": k["movement"],
            "melee_hits": k["melee_hits"], "ranged_hits": k["ranged_hits"],
            "actives": actives, "passifs": passifs, "traits": traits,
            "autres_voies": {v: lst for v, lst in k["voies"].items()
                             if v not in ("active", "passive") and lst},
            "manque": manque_combat,
            "deci_ouvertes": sum(1 for a in actives if not a["decision"]),
        })
    return lignes


def _face(a: dict) -> str:
    return ("C" if a["combat"] else "-") + ("D" if a["decision"] else "-")


def _fmt_items(ligne: dict) -> str:
    """Le kit d'une unite, en une cellule : actives avec leur face, passifs et traits manquants."""
    bouts = []
    for a in ligne["actives"]:
        marque = "[%s]" % _face(a)
        if a["voie_inversee"]:
            marque += "!"
        bouts.append("%s%s%s" % (a["name"], "" if a["id"] is None else "(%d)" % a["id"], marque))
    return "<br>".join(bouts) if bouts else "-"


def rendre(lignes: list[dict], kind: str) -> str:
    n = len(lignes)
    complets = [r for r in lignes if r["manque"] == 0]
    travail = [r for r in lignes if r["manque"] > 0]

    # Comptes PAR ITEM DISTINCT : c'est la bonne unite de travail (une ability portee par 6 npc
    # se porte UNE fois). Le compte par unite, lui, dit l'exposition.
    act, pas, tra = {}, {}, {}
    for r in lignes:
        for a in r["actives"]:
            act[a["name"]] = a
        for p in r["passifs"]:
            pas[p["name"]] = p["covered"]
        for t in r["traits"]:
            tra[t["name"]] = t["covered"]
    faces = Counter(_face(a) for a in act.values())
    inversees = sorted(a["name"] for a in act.values() if a["voie_inversee"])

    L = []
    A = L.append
    A("# Registre des unites `%s` — kit complet et etat des DEUX FACES\n\n" % kind)
    A("> Genere par `scripts/python/audit_npc_registry.py`. **Ne jamais fusionner un conflit sur\n"
      "> ce fichier : le REGENERER.** A rejouer au changement de build ou apres tout port.\n"
      ">\n"
      "> Pendant NPC de `kit-coverage.md`, qui ne balaie que les 127 `lineup`. Tous les predicats\n"
      "> de couverture viennent des FOYERS PARTAGES (`ABILITY_CLASSES`, `decision_face_voies`,\n"
      "> `_passive_covered`, les registres trait->X) — aucune liste blanche locale.\n\n")

    A("## Les deux faces, et pourquoi elles se comptent SEPAREMENT\n\n")
    A("`[CD]` = combat et decision portees · `[C-]` = executee fidelement mais **choisie avec un\n"
      "scoring qui n'est pas celui du natif** · `[-D]` = scoree mais **NO-OP silencieux** a\n"
      "l'execution · `[--]` = ni l'un ni l'autre. Le suffixe `!` marque une **voie inversee**\n"
      "(le nom n'est pas un `ActiveAbilityType` — l'ability vit dans un autre enum).\n\n")
    A("Une divergence `[C-]` est INVISIBLE en replay : l'execution est fidele, seule la POLITIQUE\n"
      "differe. C'est la doctrine « DECIDER != EXECUTER ».\n\n")

    A("## Bilan\n\n")
    A("- Unites `%s` : **%d** ; kits sans manque : **%d** ; kits avec du travail : **%d**\n"
      % (kind, n, len(complets), len(travail)))
    A("- Actives distinctes : **%d** — %s\n"
      % (len(act), " · ".join("`[%s]` **%d**" % (f, c) for f, c in sorted(faces.items()))))
    A("- Passifs distincts : **%d** — portes **%d**, non portes **%d**\n"
      % (len(pas), sum(1 for v in pas.values() if v), sum(1 for v in pas.values() if not v)))
    A("- Traits de kit distincts (hors traits communs, > %d porteurs) : **%d** — couverts **%d**,\n"
      "  non couverts **%d**\n"
      % (TRAIT_COMMON_MAX, len(tra), sum(1 for v in tra.values() if v),
         sum(1 for v in tra.values() if not v)))
    if inversees:
        A("- **Voies inversees** (nom absent d'`ActiveAbilityType`) : **%d** — %s\n"
          % (len(inversees), ", ".join("`%s`" % x for x in inversees)))
    A("\n")

    A("## Ce que ce registre NE VOIT PAS\n\n")
    A("Quatre voies d'attribution ne sont derivables d'AUCUNE source offline. Un kit affiche sans\n"
      "manque l'est au sens des voies du gameconfig, **pas au sens absolu** — c'est exactement le\n"
      "faux zero de #323, et le dire est ce qui empeche de le relire comme une preuve.\n\n")
    for nom, pourquoi in VOIES_ABSENTES:
        A("- **`%s`** — %s\n" % (nom, pourquoi))
    A("\n> ⚠ Et le kit gameconfig **n'est pas** l'entite en bataille : le natif monte\n"
      "> `BC.Units[].PassiveAbilities`, pas le kit. Une greffe `replace=True` VIDE\n"
      "> `PassiveAbilities`. La verite de ce qu'une unite porte en bataille est le canal\n"
      "> `unitAbilityStates`, jamais ce document.\n\n")

    # --- priorisation : par item distinct non porte, avec son nombre de porteurs ---------
    A("## Travail restant, par ITEM (l'unite de travail reelle)\n\n")
    A("Une ability portee par six npc se porte **une** fois : c'est l'item qui prioritise, pas\n"
      "l'unite. La colonne `porteurs` dit l'exposition.\n\n")
    porteurs_de: dict[tuple[str, str], list[str]] = defaultdict(list)
    for r in lignes:
        for a in r["actives"]:
            if not a["combat"]:
                porteurs_de[("active", a["name"])].append(r["id"])
        for p in r["passifs"]:
            if not p["covered"]:
                porteurs_de[("passif", p["name"])].append(r["id"])
        for t in r["traits"]:
            if not t["covered"]:
                porteurs_de[("trait", t["name"])].append(r["id"])
    A("| type | item | porteurs | exemples |\n|---|---|---:|---|\n")
    for (typ, nom), us in sorted(porteurs_de.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        A("| %s | %s | %d | %s |\n" % (typ, nom, len(us), ", ".join(sorted(us)[:3])))

    # --- faces DECISION ouvertes, comptees a part -----------------------------------------
    deci = sorted({a["name"] for r in lignes for a in r["actives"]
                   if a["combat"] and not a["decision"]})
    A("\n## Faces DECISION ouvertes sur des actives EXECUTEES (%d)\n\n" % len(deci))
    A("Ces abilities s'executent fidelement mais sont CHOISIES avec un scoring qui n'est pas celui\n"
      "du natif. Aucun compteur de manque ne les voit — elles ne sont pas des items absents, ce\n"
      "sont des **faces** absentes d'items presents.\n\n")
    A(", ".join("`%s`" % x for x in deci) + "\n" if deci else "_aucune_\n")

    # --- inventaire complet ---------------------------------------------------------------
    A("\n## Inventaire complet, par faction\n\n")
    par_faction: dict[str, list[dict]] = defaultdict(list)
    for r in lignes:
        par_faction[r["faction"]].append(r)
    for fac in sorted(par_faction):
        rs = sorted(par_faction[fac], key=lambda r: (-r["manque"], r["id"]))
        A("### %s — %d unites, %d avec du travail\n\n"
          % (fac, len(rs), sum(1 for r in rs if r["manque"] > 0)))
        A("| unite | manque | actives (face) | passifs non portes | traits non couverts | autres voies |\n")
        A("|---|---:|---|---|---|---|\n")
        for r in rs:
            pm = ", ".join(p["name"] for p in r["passifs"] if not p["covered"]) or "-"
            tm = ", ".join(t["name"] for t in r["traits"] if not t["covered"]) or "-"
            av = ", ".join("%s:%s" % (v, "/".join(l)) for v, l in r["autres_voies"].items()) or "-"
            A("| %s | %d | %s | %s | %s | %s |\n"
              % (r["id"], r["manque"], _fmt_items(r), pm, tm, av))
        A("\n")
    return "".join(L)


def ecrire_tsv(lignes: list[dict], chemin: Path) -> None:
    """Export plat, une ligne par (unite, item) -- la forme queryable."""
    with chemin.open("w", encoding="utf-8", newline="") as f:
        f.write("unite\tfaction\talliance\trarete\ttype\titem\tid\tface_combat\tface_decision\n")
        for r in lignes:
            for a in r["actives"]:
                f.write("%s\t%s\t%s\t%s\tactive\t%s\t%s\t%d\t%d\n"
                        % (r["id"], r["faction"], r["alliance"], r["rarity"], a["name"],
                           "" if a["id"] is None else a["id"], a["combat"], a["decision"]))
            for p in r["passifs"]:
                f.write("%s\t%s\t%s\t%s\tpassif\t%s\t\t%d\t\n"
                        % (r["id"], r["faction"], r["alliance"], r["rarity"], p["name"],
                           p["covered"]))
            for t in r["traits"]:
                f.write("%s\t%s\t%s\t%s\ttrait\t%s\t\t%d\t\n"
                        % (r["id"], r["faction"], r["alliance"], r["rarity"], t["name"],
                           t["covered"]))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--kind", default="npc", choices=("npc", "summons", "lineup"),
                    help="perimetre a balayer (defaut: npc)")
    ap.add_argument("--out", default=None, help="markdown de sortie (defaut: docs/rl/<kind>-registry.md)")
    # Le TSV est un artefact JUMEAU du markdown, pas une option : le markdown se LIT, le TSV se
    # REQUETE (une ligne par couple unite-item). Les emettre ensemble evite qu'ils divergent --
    # un TSV regenere a la main derriere un markdown a jour serait invisible et faux.
    ap.add_argument("--tsv", default=None,
                    help="export TSV plat (defaut: le jumeau .tsv du markdown ; '-' pour aucun)")
    a = ap.parse_args(argv)

    lignes = collecter(a.kind)
    if not lignes:
        print("[error] aucune unite de kind=%s -- NON MESURE, rien ecrit" % a.kind)
        return 2

    sortie = Path(a.out) if a.out else (SORTIE if a.kind == "npc"
                                        else RACINE / "docs" / "rl" / ("%s-registry.md" % a.kind))
    sortie.parent.mkdir(parents=True, exist_ok=True)
    sortie.write_text(rendre(lignes, a.kind), encoding="utf-8")
    print("ecrit -> %s" % sortie)

    if a.tsv != "-":
        tsv = Path(a.tsv) if a.tsv else sortie.with_suffix(".tsv")
        ecrire_tsv(lignes, tsv)
        print("ecrit -> %s" % tsv)

    act = {x["name"]: x for r in lignes for x in r["actives"]}
    faces = Counter((("C" if x["combat"] else "-") + ("D" if x["decision"] else "-"))
                    for x in act.values())
    pas = {p["name"]: p["covered"] for r in lignes for p in r["passifs"]}
    print("%s=%d | actives=%d %s | passifs=%d (portes %d) | kits sans manque=%d"
          % (a.kind, len(lignes), len(act), dict(sorted(faces.items())), len(pas),
             sum(1 for v in pas.values() if v), sum(1 for r in lignes if r["manque"] == 0)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
