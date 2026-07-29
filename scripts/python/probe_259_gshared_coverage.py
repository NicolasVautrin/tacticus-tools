#!/usr/bin/env python3
"""#259 -- que vaut CHAQUE voie de retablissement des generiques pleinement partages ?

LE FAIT
-------
`data/symbols/gqfc5mff6c/ghidra/functions.tsv` nomme 4 015 corps
`u003C__Il2CppFullySharedGenericTypeu003E` (4 882 avec la variante `...GenericStructType`).
La table du build courant en nomme ZERO. Ces noms n'ont JAMAIS transite par la chaine Frida
(0 occurrence dans `frida/methods.tsv`, des deux cotes) : ils venaient du seul applier legacy
`GhidraApplyIl2CppNamesWin.java`, qui lisait le `script.json` d'Il2CppDumper v39 et a ete
supprime le 2026-07-25 (`8e591496`). La table de `gqfc5mff6c` gardait ses noms parce que le
PROJET Ghidra avait ete symbolise par lui ; la premiere re-symbolisation complete les a fait
tomber a 0, en silence.

CE QUE MESURE CETTE SONDE (et pourquoi chaque etape existe)
-----------------------------------------------------------
1. INVENTAIRE PAR FAMILLE des deux tables Ghidra. C'est la vue qui manquait : les quatre axes
   de `symbols_sync.py` verifient la PROVENANCE ou la FORME, aucun ne compte la COUVERTURE.
   La famille `GSHARED` est isolee sur le MECANISME (`__Il2CppFullySharedGeneric*`), pas sur un
   namespace -- une perte qui traverse tous les namespaces reste invisible a la maille namespace
   (mesure : `IdunBattle.AI.Playbook` ne bouge que de 2 122 -> 2 083, soit -1,8 %, alors que
   plusieurs centaines de corps y ont disparu).
2. BRUIT INTER-BUILD REEL, mesure sur les tables FRIDA -- MEME outil des deux cotes, donc
   churn de MISE A JOUR pur, sans contamination par le changement d'outillage. C'est CE
   chiffre qui dimensionne le seuil de l'axe 5, pas le diff des tables Ghidra (contamine).
3. ATTRIBUTION : combien de symboles de la table Ghidra la chaine Frida sait REPRODUIRE
   (`GhidraApplyIl2CppSymbols.canonicalName` recalcule ici a l'identique), et combien sont
   HORS de sa portee. La difference est exactement ce que la voie Il2CppDumper rendrait.
4. LES DEUX CIBLES NOMMEES de #257 (`ComparablePlaybook<...>$$CalculateActionUtility` et
   `$$CalculateUtilityFromTilePrediction`), qui portent l'instrument de decomposition par
   etage et bloquent #257 -> #258.

CE QUE LA SONDE NE PEUT PAS TRANCHER, ET C'EST DIT
--------------------------------------------------
Elle ne dit pas si un `MethodInfo` d'instance INFLATEE exposerait le corps partage : cela
demande une lecture LIVE (le dump Frida courant n'enumere que les classes rendues par
`il2cpp_image_get_class`, donc les DEFINITIONS generiques, dont le `methodPointer` est un
THUNK -- cf. `IdunBattle.AI.Playbook.TriggeredAbilityPlaybook`1$$Init`, 12 lignes qui
redispatchent via `methodInfo[2]`, a une adresse DIFFERENTE du corps pleinement partage).

Sortie 0 = la couverture gshared est retablie ; 1 = elle est encore perdue.
ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "python"))

from symbols_layout import build_dir, current_build  # noqa: E402

BASE = 0x180000000

# Marqueur du MECANISME, pas d'un namespace : Unity substitue ce type-placeholder au parametre
# generique quand il compile UN SEUL corps pour toutes les instanciations (full generic sharing).
MARQUEUR_GSHARED = "__Il2CppFullySharedGeneric"

# Les deux cibles de #257 : elles portent l'instrument de decomposition par etage (utilite
# totale par candidat, terme de tuile complet).
CIBLES_257 = (
    "IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E"
    "$$CalculateActionUtility",
    "IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E"
    "$$CalculateUtilityFromTilePrediction",
)


# ---------------------------------------------------------------- lecture des tables

def lire_ghidra(build: str) -> dict[int, str]:
    p = build_dir(build) / "ghidra" / "functions.tsv"
    if not p.is_file():
        raise SystemExit("table ghidra absente : %s" % p)
    out: dict[int, str] = {}
    with p.open(encoding="utf-8", errors="replace") as fh:
        for ligne in fh:
            if ligne.startswith("#") or "\t" not in ligne:
                continue
            a, _, nom = ligne.rstrip("\n").partition("\t")
            try:
                out[int(a, 16)] = nom.strip()
            except ValueError:
                continue
    return out


def lire_frida(build: str) -> dict[int, tuple[str, str]]:
    """RVA -> (nom complet, classe declarante), tel que dumpe par Frida."""
    p = build_dir(build) / "frida" / "methods.tsv"
    if not p.is_file():
        raise SystemExit("table frida absente : %s" % p)
    out: dict[int, tuple[str, str]] = {}
    with p.open(encoding="utf-8", errors="replace") as fh:
        for ligne in fh:
            if ligne.startswith("#") or "\t" not in ligne:
                continue
            parts = ligne.rstrip("\n").split("\t")
            if len(parts) < 3:
                continue
            try:
                out[int(parts[0], 16)] = (parts[1], parts[2])
            except ValueError:
                continue
    return out


# ------------------------------------------------- forme canonique (mirror de l'applier)

def _echappe(s: str) -> str:
    """`GhidraApplyIl2CppSymbols.escapeAngles` -- espace -> '_', chevrons -> u003C/u003E."""
    return s.replace(" ", "_").replace("<", "u003C").replace(">", "u003E")


def canonique(nom_complet: str, classe: str) -> str:
    """`GhidraApplyIl2CppSymbols.canonicalName` -- `Namespace.Classe$$Membre`.

    Recalculee ICI a l'identique : c'est ce qui permet de dire, symbole par symbole, si la
    chaine Frida SAIT le produire. Toute divergence entre les deux implementations rendrait
    l'attribution fausse -- l'etape 3 la detecterait (taux d'accord effondre)."""
    prefixe = classe + "."
    membre = nom_complet[len(prefixe):] if nom_complet.startswith(prefixe) else nom_complet
    return _echappe(classe) + "$$" + _echappe(membre)


# ------------------------------------------------------------------------- familles

def famille(nom: str) -> str:
    """Grande famille d'un symbole. L'ordre des tests IMPORTE.

    `GSHARED` passe AVANT le namespace : sans ca les 4 882 corps partages se diluent dans
    `IdunBattle` / `System` / `UnityEngine` et la perte devient invisible -- c'est exactement
    ce qui s'est produit."""
    if MARQUEUR_GSHARED in nom:
        return "GSHARED"
    if nom.startswith(("FUN_", "DAT_", "PTR_")):
        return "PLACEHOLDER"
    if "$$" in nom:
        return "il2cpp:" + nom.split("$$")[0].split(".")[0].split("`")[0]
    return "AUTRE"


def familles_ghidra(table: dict[int, str]) -> Counter:
    return Counter(famille(n) for n in table.values())


def familles_frida(table: dict[int, tuple[str, str]]) -> Counter:
    return Counter(classe.split(".")[0].split("`")[0] for _, classe in table.values())


# ------------------------------------------------------------------------- etapes

def etape1(ref: str, cur: str) -> int:
    print("=== ETAPE 1 : inventaire par FAMILLE des tables Ghidra ===")
    a, b = lire_ghidra(ref), lire_ghidra(cur)
    fa, fb = familles_ghidra(a), familles_ghidra(b)
    print("  %s : %d symboles   |   %s : %d symboles" % (ref, len(a), cur, len(b)))
    print()
    print("  %-28s %8s %8s %8s" % ("famille", ref[:8], cur[:8], "ratio"))
    perdues = 0
    for nom, vieux in sorted(fa.items(), key=lambda kv: -kv[1]):
        neuf = fb.get(nom, 0)
        if vieux < 100 and neuf < 100:
            continue
        r = (neuf / vieux) if vieux else float("inf")
        alerte = "  <<< CHUTE" if (vieux >= 100 and r < 0.60) else ""
        if alerte:
            perdues += 1
        print("  %-28s %8d %8d %8.3f%s" % (nom, vieux, neuf, r, alerte))
    for nom, neuf in sorted(fb.items(), key=lambda kv: -kv[1]):
        if nom not in fa and neuf >= 100:
            print("  %-28s %8s %8d %8s   (NOUVELLE)" % (nom, "-", neuf, "-"))
    print()
    print("  familles en chute : %d" % perdues)
    print()
    return perdues


def etape2(ref: str, cur: str) -> None:
    print("=== ETAPE 2 : bruit inter-build REEL (tables FRIDA, meme outil des deux cotes) ===")
    fa = familles_frida(lire_frida(ref))
    fb = familles_frida(lire_frida(cur))
    print("  %s : %d methodes   |   %s : %d methodes"
          % (ref, sum(fa.values()), cur, sum(fb.values())))
    lignes = []
    for nom, vieux in fa.items():
        lignes.append(((fb.get(nom, 0) / vieux) if vieux else 0.0, vieux, fb.get(nom, 0), nom))
    lignes.sort()
    gros = [l for l in lignes if l[1] >= 100]
    petits = [l for l in lignes if l[1] < 100]
    print()
    print("  familles >= 100 methodes : %d" % len(gros))
    for r, v, n, k in gros[:6]:
        print("     ratio min %.3f  %6d -> %6d  %s" % (r, v, n, k))
    print("     ...")
    for r, v, n, k in gros[-2:]:
        print("     ratio max %.3f  %6d -> %6d  %s" % (r, v, n, k))
    if petits:
        print("  familles <  100 methodes : %d  (ratio min %.3f, max %.3f)"
              % (len(petits), min(l[0] for l in petits), max(l[0] for l in petits)))
    disparues = [k for k in fa if k not in fb]
    print("  familles DISPARUES : %d" % len(disparues))
    print()
    print("  LECTURE : c'est le plancher de bruit qui dimensionne le seuil de l'axe 5.")
    print("  Une famille >= 100 qui PERD des membres n'a PAS ete observee sur cette MAJ.")
    print()


def etape3(build: str) -> tuple[int, int, int]:
    print("=== ETAPE 3 : attribution -- ce que la chaine Frida sait REPRODUIRE (%s) ===" % build)
    g, f = lire_ghidra(build), lire_frida(build)
    canon = {rva: canonique(n, d) for rva, (n, d) in f.items()}
    identique = different = sans_fonction = 0
    for rva, nom in canon.items():
        vu = g.get(rva + BASE)
        if vu is None:
            sans_fonction += 1
        elif vu == nom:
            identique += 1
        else:
            different += 1
    hors = [n for a, n in g.items()
            if (a - BASE) not in canon and not n.startswith(("FUN_", "DAT_", "PTR_"))]
    gshared = sum(1 for n in hors if MARQUEUR_GSHARED in n)
    print("  frida = %d methodes ; ghidra = %d symboles" % (len(f), len(g)))
    print("  nom Ghidra == canonicalName(frida) : %d  (%.1f %% des methodes frida)"
          % (identique, 100.0 * identique / max(1, len(f))))
    print("  nom Ghidra DIFFERENT               : %d" % different)
    print("  methode frida sans fonction Ghidra : %d" % sans_fonction)
    print("  symboles NOMMES hors chaine Frida  : %d" % len(hors))
    print("     dont %s* : %d" % (MARQUEUR_GSHARED, gshared))
    print("     dont autres (gshared classique <object>, thunks, runtime C++) : %d"
          % (len(hors) - gshared))
    print()
    return identique, len(hors), gshared


def etape4(ref: str, cur: str) -> bool:
    print("=== ETAPE 4 : les deux cibles nommees de #257 ===")
    a, b = lire_ghidra(ref), lire_ghidra(cur)
    par_nom_a: dict[str, int] = {}
    for adr, nom in a.items():
        par_nom_a.setdefault(nom, adr)
    par_nom_b: dict[str, int] = {}
    for adr, nom in b.items():
        par_nom_b.setdefault(nom, adr)
    toutes_la = True
    for cible in CIBLES_257:
        va_ref = par_nom_a.get(cible)
        va_cur = par_nom_b.get(cible)
        print("  %s" % cible)
        print("     %-12s : %s" % (ref, ("%#x" % va_ref) if va_ref else "ABSENT"))
        print("     %-12s : %s" % (cur, ("%#x" % va_cur) if va_cur else "ABSENT"))
        if va_cur is None:
            toutes_la = False
    print()
    return toutes_la


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--ref", default="gqfc5mff6c",
                    help="build de REFERENCE (celui dont la table portait les gshared)")
    ap.add_argument("--build", default=None, help="build courant ; defaut = data/symbols/CURRENT")
    args = ap.parse_args()

    cur = args.build or current_build()
    print("reference : %s" % args.ref)
    print("courant   : %s" % cur)
    print()
    if args.ref == cur:
        print("ATTENTION : reference == courant, la comparaison est l'identite.")
        print()

    etape1(args.ref, cur)
    etape2(args.ref, cur)
    print("--- attribution du build de REFERENCE (chaine legacy Il2CppDumper) ---")
    _, hors_ref, gshared_ref = etape3(args.ref)
    print("--- attribution du build COURANT (chaine Frida) ---")
    _, hors_cur, gshared_cur = etape3(cur)
    ok = etape4(args.ref, cur)

    print("--- VERDICT ---")
    print("  ce que la chaine legacy nommait en plus : %d symboles"
          % max(0, hors_ref - hors_cur))
    print("  dont corps pleinement partages          : %d" % max(0, gshared_ref - gshared_cur))
    if ok:
        print("  COUVERTURE GSHARED RETABLIE : les deux cibles de #257 resolvent.")
        return 0
    print("  COUVERTURE GSHARED PERDUE : les cibles de #257 ne resolvent PAS.")
    print("  Voies et protocole : docs/rl/case-259-couverture-gshared.md")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
