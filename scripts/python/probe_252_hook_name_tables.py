#!/usr/bin/env python3
"""GARDE : les tables de noms FIGEES de `frida/hooks/data/` collent-elles au build courant ?

POURQUOI
--------
Cinq fichiers de `frida/hooks/data/*.ts` recopient un enum natif sous forme de table
`{ id: "Nom" }`. Contrairement a `introspect.ts` -- qui lit l'enum A L'EXECUTION via `dumpEnum`
et se met donc a jour tout seul -- ces tables sont GELEES au build ou elles ont ete generees.
Leur en-tete dit « Regenerate when GameAssembly.dll is updated », et rien ne le verifiait.

L'enjeu est reel : le 2026-07-29 le jeu a RETIRE `ArmorChanged` (valeur 40) au milieu de
`EventTriggerType`, decalant de -1 les 36 membres suivants. Une table figee continue alors de
nommer correctement les 40 premiers ids et ment SILENCIEUSEMENT sur tous les autres -- le pire
mode de defaillance, puisque la sortie reste plausible.

Trois en-tetes sur cinq citent d'ailleurs un build PERIME (`gqfc5mff6c`, `kqkbjqfb6c`) ou une
source disparue (`sources_win`, `data/dumps/<hash>/dump.cs`).

CE QUE CETTE SONDE NE FAIT PAS : elle ne regenere rien. Elle DIT ce qui a bouge, id par id.
La regeneration reste manuelle -- une table peut avoir des entrees VOULUES hors enum (ex.
`9999: "STRIPPED"` dans triggered-ability-names.ts), qu'un regenerateur naif effacerait.

Sortie 0 = toutes les tables collent ; 1 = au moins une derive.
ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "python"))

from symbols_layout import current_build  # noqa: E402

DATA = REPO / "frida" / "hooks" / "data"

# fichier -> (cle dans enums.tsv, la table indexe-t-elle un INDEX DE BIT plutot qu'une valeur ?)
TABLES = {
    "ability-names.ts":            ("IdunBattle.Entities.Enum.ActiveAbilityType", False),
    "effect-type-names.ts":        ("IdunBattle.Entities.Enum.EffectType", False),
    "event-trigger-type-names.ts": ("IdunBattle.DSL.EventTriggerType", False),
    "triggered-ability-names.ts":  ("IdunBattle.Entities.Enum.TriggeredAbilityType", False),
    "targeting-rule-names.ts":     ("IdunBattle.Core.Services.TargetingRule", True),
    # #283 : rapatriee ici depuis `features/ai-utility-trace.ts`, ou elle vivait INLINE et
    # echappait donc a cette garde. Elle etait figee sur `gqfc5mff6c` : `AttackTile` (insere en
    # 8) manquait et les 37 ids suivants nommaient leur VOISIN.
    "utility-type-names.ts":       ("IdunBattle.Configuration.UtilityType", False),
}

ENTREE = re.compile(r'^\s*(-?\d+)\s*:\s*"([^"]*)"', re.M)


def enum_du_jeu(build: str, cle: str) -> dict[int, set[str]]:
    """-> {valeur: {noms}}. Un ENSEMBLE de noms, pas un nom.

    Plusieurs membres peuvent PARTAGER une valeur -- mesure : `ActiveAbilityType` et
    `TriggeredAbilityType` ont tous deux `9999 = STRIPPED` ET `9999 = testAssetBundles`.
    Garder le dernier lu faisait crier la garde sur une table pourtant juste."""
    p = REPO / "data" / "symbols" / build / "frida" / "enums.tsv"
    for ligne in p.open(encoding="utf-8"):
        if ligne.startswith(cle + "\t"):
            corps = ligne.rstrip("\n").split("\t", 1)[1]
            out: dict[int, set[str]] = {}
            for paire in corps.split(","):
                v, _, n = paire.partition("=")
                if n:
                    try:
                        out.setdefault(int(v), set()).add(n)
                    except ValueError:
                        pass
            return out
    raise SystemExit("cle absente de enums.tsv : %s" % cle)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--build", default=None, help="defaut : data/symbols/CURRENT")
    ap.add_argument("--lister", type=int, default=12, help="nb d'ecarts detailles par table")
    args = ap.parse_args()

    build = args.build or current_build()
    print("build : %s" % build)
    print("")
    derive = False

    for nom, (cle, par_bit) in sorted(TABLES.items()):
        f = DATA / nom
        if not f.is_file():
            print("  %-30s ABSENT" % nom)
            derive = True
            continue
        table = {int(m.group(1)): m.group(2) for m in ENTREE.finditer(f.read_text(encoding="utf-8"))}
        jeu = enum_du_jeu(build, cle)
        if par_bit:
            # La table indexe des INDEX DE BIT ; l'enum porte des valeurs 1<<bit. On projette
            # l'enum vers l'espace des bits, en ignorant les composites (plusieurs bits allumes).
            jeu = {v.bit_length() - 1: n for v, n in jeu.items()
                   if v > 0 and (v & (v - 1)) == 0}

        # `jeu[k]` est un ENSEMBLE : la table est juste des qu'elle nomme L'UN des membres
        # partageant cette valeur (cf. le doublon 9999 STRIPPED/testAssetBundles).
        faux = [(k, table[k], "|".join(sorted(jeu[k])))
                for k in sorted(table) if k in jeu and table[k] not in jeu[k]]
        absents = [k for k in sorted(table) if k not in jeu]
        manquants = [k for k in sorted(jeu) if k not in table]

        etat = "OK " if not (faux or absents) else "DERIVE"
        if faux or absents:
            derive = True
        print("  %-6s %-30s table=%-5d jeu=%-5d  faux=%-4d hors-enum=%-4d absents-de-la-table=%d"
              % (etat, nom, len(table), len(jeu), len(faux), len(absents), len(manquants)))

        for k, vu, attendu in faux[:args.lister]:
            print("           %6d : table dit %-34s le jeu dit %s" % (k, '"%s"' % vu, '"%s"' % attendu))
        if len(faux) > args.lister:
            print("           ... et %d autres ecarts" % (len(faux) - args.lister))
        for k in absents[:args.lister]:
            print("           %6d : %-34s N'EXISTE PLUS dans l'enum" % (k, '"%s"' % table[k]))

    print("")
    if derive:
        print("AU MOINS UNE TABLE DERIVE -- regenerer a la main (voir la docstring : ne pas")
        print("effacer les entrees VOULUES hors enum, ex. 9999:\"STRIPPED\").")
        print("Ces tables vivent dans frida/hooks/* : leur correction exige un rebuild + REINJECT.")
        return 1
    print("toutes les tables figees collent au build %s" % build)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
