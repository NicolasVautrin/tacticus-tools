"""#1039 -- le canal `rarity`, garde OFFLINE de son APPARIEMENT.

    python scripts/python/probe_1039_canal_rarete.py

POURQUOI CE PROBE EXISTE, ET CE QU'IL NE FAIT PAS. Le capteur vit dans
`frida/hooks/game/rarity.ts` : il ne s'execute que dans le process du jeu, et le VOIR
emettre exige une fenetre de reinject. Sa RESOLUTION est deja gardee hors Frida par
`frida/tools/probe-1039-rarity-canal.ts` (mutations adversariales sur une disposition
capturee). Ce probe-ci garde l'autre moitie, celle qui ne se voit dans aucun des deux :
l'APPARIEMENT de l'enum, cote table VERSIONNEE du build et cote mirror Python.

Le gisement, en une phrase : CINQ enums du build portent EXACTEMENT les six memes membres
aux memes ordinaux, donc une confusion d'appariement est SILENCIEUSE EN ORDINAL. Le seul
canal ou elle est visible est le NOM PLEIN -- et c'est exactement ce que `case-1024` §4 et
les residus #999-r1 / #999-r3 avaient rate, en nommant `IdunMetaLogic.UserProgress.Model.
UnitRarity` la ou les gates de bataille lisent `idun.meta.Rarity`.

CE QU'IL MESURE, quatre etages, chacun re-derive et jamais recopie :
  0. la table `data/symbols/<build>/frida/enums.tsv` porte bien N >= 2 enums de rarete aux
     membres IDENTIQUES -- donc l'ordinal ne discrimine PAS ;
  1. le mirror `engine/entities/rarity.py` est en bijection avec `idun.meta.Rarity`,
     et PAS seulement avec « un enum de rarete » ;
  2. le TYPE DECLARE du parametre `rarity` aux foyers natifs, LU dans
     `data/symbols/<build>/frida/methods.tsv`, est `idun.meta.Rarity` -- a TOUS ;
  3. la source du hook EXIGE ce nom plein, et le RPC publie le contrat annonce.

CE QU'IL NE MESURE PAS : que le bundle injecte emette ces valeurs, ni ce que le capteur
rend sur une entite reelle. Cela exige un reinject.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

ENUM_ATTENDU = "idun.meta.Rarity"
# Les quatre foyers natifs dont le parametre `rarity` porte un TYPE DECLARE. Ils sont
# NOMMES ici (pas cherches par motif) parce que leur liste est le resultat d'une lecture,
# pas d'une heuristique -- un grep sur "Rarity" ramenerait aussi les enums eux-memes.
FOYERS = [
    "IdunBattleLogic.Entities.DSLSelectors.UnitsWithRarity",
    "IdunBattleLogic.Entities.DSLTriggers.HasRarity",
    "IdunBattle.Entities.UnitExtensions.HasRarity",
    "IdunBattle.Entities.Formulas.UnitsWithRaritySelector..ctor",
]
HOOK = RACINE / "frida" / "hooks" / "game" / "rarity.ts"
RPC = RACINE / "frida" / "hooks" / "features" / "ai-step" / "rpc-snapshot.ts"
MIRROR = RACINE / "scripts" / "python" / "engine" / "entities" / "rarity.py"


def build_courant() -> str:
    return (RACINE / "data" / "symbols" / "CURRENT").read_text(encoding="utf-8").strip()


def lire_enums(build: str) -> dict[str, dict[str, int]]:
    """`enums.tsv` -> {nom plein: {membre: ordinal}}."""
    chemin = RACINE / "data" / "symbols" / build / "frida" / "enums.tsv"
    out: dict[str, dict[str, int]] = {}
    with chemin.open(encoding="utf-8") as fh:
        for ligne in fh:
            if ligne.startswith("#") or "\t" not in ligne:
                continue
            nom, membres = ligne.rstrip("\n").split("\t", 1)
            paires: dict[str, int] = {}
            for morceau in membres.split(","):
                if "=" not in morceau:
                    continue
                val, cle = morceau.split("=", 1)
                try:
                    paires[cle] = int(val)
                except ValueError:
                    continue
            if paires:
                out[nom] = paires
    return out


def main() -> int:
    echecs = 0
    build = build_courant()
    print("[1039] build = %s" % build)
    enums = lire_enums(build)

    # --- Etage 0 : l'ordinal ne discrimine PAS ---------------------------------------
    print("\n=== ETAGE 0 : combien d'enums portent les MEMES membres que %s ==="
          % ENUM_ATTENDU)
    if ENUM_ATTENDU not in enums:
        print("ROUGE : %s absent de enums.tsv -- le type declare des gates n'existe pas"
              % ENUM_ATTENDU)
        return 1
    reference = enums[ENUM_ATTENDU]
    jumeaux = sorted(n for n, m in enums.items() if m == reference)
    print("  membres : %s" % reference)
    for nom in jumeaux:
        print("    %s%s" % (nom, "   <- celui que le COMBAT lit"
                            if nom == ENUM_ATTENDU else ""))
    # Un test qui rendrait un ensemble VIDE passerait pour vert : on assertionne son
    # propre non-vide, comme le cliquet des ordinaux communs de #270-r1-r1-r3.
    if len(jumeaux) < 2:
        print("ROUGE : %d enum(s) seulement -- l'ambiguite que ce probe garde n'existe"
              " plus sur ce build ; relire la prose de frida/hooks/game/rarity.ts"
              % len(jumeaux))
        echecs += 1
    else:
        print("  => %d enums INDISCERNABLES par ordinal : le NOM PLEIN est le seul"
              " discriminant" % len(jumeaux))

    # --- Etage 1 : le mirror Python est apparie au BON --------------------------------
    print("\n=== ETAGE 1 : mirror engine/entities/rarity.py <-> %s ===" % ENUM_ATTENDU)
    if not MIRROR.exists():
        print("ROUGE : mirror absent -> %s" % MIRROR)
        echecs += 1
    else:
        from engine.entities.rarity import Rarity  # noqa: PLC0415  (mirror, pas un cycle)
        porte = {m.name: int(m.value) for m in Rarity}
        if porte != reference:
            print("ROUGE : mirror %s != build %s" % (porte, reference))
            echecs += 1
        else:
            print("  bijection OK (%d membres)" % len(porte))
        # Le mirror doit NOMMER le bon enum dans sa docstring : c'est le seul endroit ou
        # un relecteur voit lequel des cinq il transcrit.
        texte = MIRROR.read_text(encoding="utf-8")
        if ENUM_ATTENDU not in texte:
            print("ROUGE : le mirror ne CITE pas `%s` -- lequel des %d transcrit-il ?"
                  % (ENUM_ATTENDU, len(jumeaux)))
            echecs += 1
        else:
            print("  le mirror cite `%s`" % ENUM_ATTENDU)

    # --- Etage 2 : le TYPE DECLARE aux foyers natifs ----------------------------------
    print("\n=== ETAGE 2 : type declare du parametre `rarity` aux %d foyers ==="
          % len(FOYERS))
    methodes = RACINE / "data" / "symbols" / build / "frida" / "methods.tsv"
    vus: dict[str, str] = {}
    with methodes.open(encoding="utf-8") as fh:
        for ligne in fh:
            cols = ligne.rstrip("\n").split("\t")
            if len(cols) < 6 or cols[1] not in FOYERS:
                continue
            for param in cols[5].split(","):
                if param.startswith("rarity:"):
                    vus[cols[1]] = param.split(":", 1)[1]
    for foyer in FOYERS:
        got = vus.get(foyer)
        ok = got == ENUM_ATTENDU
        print("  %-58s %s" % (foyer, got if got else "PAS DE PARAMETRE `rarity`"))
        if not ok:
            echecs += 1
    if len(vus) != len(FOYERS):
        print("ROUGE : %d foyer(s) sur %d n'exposent pas de parametre `rarity` --"
              " la liste NOMMEE de ce probe est perimee" % (len(FOYERS) - len(vus),
                                                            len(FOYERS)))
        echecs += 1
    elif all(v == ENUM_ATTENDU for v in vus.values()):
        print("  => %d/%d concordants" % (len(vus), len(FOYERS)))

    # --- Etage 3 : la source du hook EXIGE le nom plein, et publie son contrat ---------
    print("\n=== ETAGE 3 : source du hook ===")
    if not HOOK.exists() or not RPC.exists():
        print("ROUGE : source du hook absente (%s / %s)" % (HOOK, RPC))
        return 1
    src_hook = HOOK.read_text(encoding="utf-8")
    src_rpc = RPC.read_text(encoding="utf-8")
    attendus = [
        (HOOK.name, src_hook, 'RARITY_ENUM_FULL_NAME = "%s"' % ENUM_ATTENDU),
        (HOOK.name, src_hook, "probe.rawFieldOffset(comp, RARITY_FIELD)"),
        (HOOK.name, src_hook, "full !== RARITY_ENUM_FULL_NAME"),
        (RPC.name, src_rpc, "rarity: wants(\"rarity\") ? readRarity(e) : null"),
        (RPC.name, src_rpc, "rarityEnum:"),
        (RPC.name, src_rpc, "rarityTypes:"),
        (RPC.name, src_rpc, "rarityLayout:"),
    ]
    for fichier, texte, motif in attendus:
        present = motif in texte
        print("  %-22s %s  %s" % (fichier, "OK   " if present else "ABSENT", motif))
        if not present:
            echecs += 1
    # Aucune LECTURE ne doit passer par une constante : le seul `0x74`/`0x80` tolere est
    # celui des deux `DECOMPILED_*`, qui n'alimentent QUE le rapport de derive.
    lectures_en_dur = [
        ligne.strip() for ligne in src_hook.splitlines()
        if re.search(r"\.add\(\s*0x[0-9a-fA-F]+\s*\)", ligne)
    ]
    if lectures_en_dur:
        print("ROUGE : lecture(s) a offset CONSTANT dans %s :" % HOOK.name)
        for ligne in lectures_en_dur:
            print("    %s" % ligne)
        echecs += 1
    else:
        print("  aucune lecture a offset constant dans %s" % HOOK.name)

    print("\n[1039] PORTEE : ce probe garde l'APPARIEMENT et le CONTRAT, hors Frida.")
    print("[1039] NON COUVERT : que le bundle injecte emette ces valeurs, et ce que")
    print("       `readRarity` rend sur une entite reelle -- il faut une fenetre de")
    print("       reinject. Le capteur reste NON CONFRONTE EN LIVE.")
    print("\nBILAN : %s" % ("OK" if echecs == 0 else "%d ECHEC(S)" % echecs))
    return 0 if echecs == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
