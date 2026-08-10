#!/usr/bin/env python3
"""#419-r1-tr9-r4-r1-r3 -- le cliquet manquant : un SYMBOLE CITE existe-t-il dans les tables ?

Le pendant, sur l'axe des NOMS, de `probe_va_in_code_vs_prose.py` (axe des ADRESSES).

CE QU'IL MESURE. Toute citation de la forme `<Namespace>.<Classe>$$<Methode>` ecrite dans une
docstring / un commentaire / une chaine du corpus est confrontee aux DEUX tables du build :

  * `data/symbols/<build>/ghidra/functions.tsv`  -- format `<adresse>\\t<Classe>$$<Methode>` ;
  * `data/symbols/<build>/frida/methods.tsv`     -- format `<rva>\\t<Classe>.<Methode>\\t...`.

Une citation INTROUVABLE dans les deux est un symbole qui n'existe pas : le lecteur qui la grepe
ne trouve rien, et il ne peut pas savoir si c'est la table qui est vieille ou la citation qui est
fausse. Le probe va plus loin qu'un simple verdict : quand la METHODE existe sous un AUTRE
proprietaire, il le NOMME -- c'est ce qui rend la correction mecanique.

POURQUOI CE PROBE EXISTE. Mesure d'origine (#419-r1-tr9-r4-r1) : le port citait
`IdunBattleLogic.Entities.DSLFactory$$IsNormalAttack`. `DSLFactory` EST une classe du build, mais
elle ne porte que CINQ methodes (`Init`, `Triggered`, `SetAllowRandom`, `SetDisallowRandom`,
`.ctor`) -- les predicats vivent sur `DSLTriggers`, les feuilles sur `DSLBehaviors`, les selecteurs
sur `DSLSelectors`, les formules sur `DSLFormulas`. La faute est donc INVISIBLE a un garde
« le namespace existe-t-il » : il faut confronter le COUPLE (classe, methode).

L'ABSENCE NE PROUVE RIEN -- ET C'EST POURQUOI LE VERDICT EST VENTILE. Le CLAUDE.md le dit :
IL2CPP deduplique les corps triviaux (un corps partage par N classes n'a qu'UN proprietaire dans
la table) et les definitions generiques pleinement partagees sont absentes du dump FRIDA. Une
citation introuvable peut donc etre JUSTE. Le probe separe :

  * `INTROUVABLE_AVEC_HOMONYME`  -- la methode existe ailleurs => la citation designe le mauvais
    proprietaire. C'est le gisement dur, et le seul sur lequel le cliquet ROUGIT.
  * `INTROUVABLE_SANS_HOMONYME`  -- ni la classe ni la methode ne repondent. Peut etre un corps
    dedupliqu'e, un generique, ou une coquille : LISTE, jamais compte comme rouge.

Sortie ASCII pure (console cp1252).

    python probe_419r1tr9r4r1r3_symboles_cites_absents.py                # perimetre DSL*
    python probe_419r1tr9r4r1r3_symboles_cites_absents.py --tous         # toutes les classes
    python probe_419r1tr9r4r1r3_symboles_cites_absents.py --racine docs  # la prose aussi
    python probe_419r1tr9r4r1r3_symboles_cites_absents.py --cliquet      # rc 1 si homonyme
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

#: `Namespace.Classe$$Methode`. Le `$$` est le separateur Ghidra ; la partie gauche peut porter
#: des points (le namespace) et la droite un `.ctor`/`.cctor`.
#:
#: ⚠ Le backtick n'est accepte QUE dans la forme IL2CPP `Nom`1` (backtick suivi d'un chiffre
#: d'arite). Le laisser libre dans le charset faisait avaler le backtick de FERMETURE d'un
#: `code span` markdown : mesure d'origine, `DSLFactory$$AttackWithAttackDamage` (43 sites,
#: gisement REEL) etait scinde en deux entrees dont une fantome a 74 sites, rangee en
#: `SANS HOMONYME` -- le probe SOUS-COMPTAIT son propre gisement en le deguisant en bruit.
_MOT = r"[A-Za-z_]\w*(?:`\d+)?"
CITATION_RE = re.compile(r"\b(%s(?:\.%s)*)\$\$(\.?%s)" % (_MOT, _MOT, _MOT))

#: Le perimetre par defaut = les cinq classes statiques du DSL, foyer du residu.
PREFIXE_DSL = ("DSLFactory", "DSLTriggers", "DSLBehaviors", "DSLSelectors", "DSLFormulas")

EXT_TEXTE = {".py", ".md", ".ts", ".txt"}


def build_courant() -> str:
    return (REPO / "data" / "symbols" / "CURRENT").read_text(encoding="utf-8").strip()


def charger_tables(build: str):
    """-> (proprietaires: {classe_courte -> {methodes}}, par_methode: {methode -> {classes}}).

    Les DEUX tables sont fusionnees : la ghidra publie les generiques pleinement partages que la
    frida n'a pas, la frida publie les signatures. Ne lire qu'une seule fabriquerait des faux
    positifs -- exactement la faute que ce probe est cense empecher.
    """
    base = REPO / "data" / "symbols" / build
    prop = defaultdict(set)
    par_methode = defaultdict(set)
    vus = 0

    fg = base / "ghidra" / "functions.tsv"
    if not fg.exists():
        raise SystemExit("MESURE IMPOSSIBLE : %s absent" % fg)
    with fg.open("r", encoding="utf-8", errors="replace") as fh:
        for ligne in fh:
            parts = ligne.rstrip("\n").split("\t")
            if len(parts) < 2 or "$$" not in parts[1]:
                continue
            cls, meth = parts[1].split("$$", 1)
            prop[cls].add(meth)
            prop[cls.rsplit(".", 1)[-1]].add(meth)
            par_methode[meth].add(cls)
            vus += 1

    ff = base / "frida" / "methods.tsv"
    if not ff.exists():
        raise SystemExit("MESURE IMPOSSIBLE : %s absent" % ff)
    with ff.open("r", encoding="utf-8", errors="replace") as fh:
        for ligne in fh:
            parts = ligne.rstrip("\n").split("\t")
            if len(parts) < 3:
                continue
            plein, cls = parts[1], parts[2]
            if not plein.startswith(cls):
                continue
            meth = plein[len(cls):].lstrip(".")
            if not meth:
                continue
            prop[cls].add(meth)
            prop[cls.rsplit(".", 1)[-1]].add(meth)
            par_methode[meth].add(cls)
            vus += 1

    if vus == 0:
        raise SystemExit("MESURE IMPOSSIBLE : les deux tables sont vides")
    return prop, par_methode, vus


def fichiers(racines):
    for racine in racines:
        rp = REPO / racine
        if not rp.exists():
            continue
        if rp.is_file():
            yield rp
            continue
        for p in sorted(rp.rglob("*")):
            if p.is_file() and p.suffix in EXT_TEXTE:
                yield p


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--racine", action="append", default=None,
                    help="racine a balayer (defaut : scripts/python)")
    ap.add_argument("--tous", action="store_true",
                    help="toutes les classes citees, pas seulement DSL*")
    ap.add_argument("--cliquet", action="store_true",
                    help="rc 1 des qu'une citation a un homonyme ailleurs")
    ap.add_argument("--corrige", action="store_true",
                    help="REECRIT les citations a homonyme UNIQUE (prose seulement)")
    args = ap.parse_args()

    racines = args.racine or ["scripts/python"]
    build = build_courant()
    prop, par_methode, vus = charger_tables(build)

    print("BUILD              : %s" % build)
    print("SYMBOLES EN TABLE  : %d (ghidra + frida fusionnees)" % vus)
    print("RACINES            : %s" % ", ".join(racines))
    print("PERIMETRE          : %s" % ("toutes les classes" if args.tous
                                       else "classes " + "/".join(PREFIXE_DSL)))

    cats = Counter()
    homonymes = []          # (fichier, ligne, cite, {classes proprietaires})
    orphelines = []         # (fichier, ligne, cite)
    nb_fichiers = 0

    for p in fichiers(racines):
        try:
            src = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        nb_fichiers += 1
        for num, ligne in enumerate(src.splitlines(), 1):
            for m in CITATION_RE.finditer(ligne):
                cls_plein, meth = m.group(1), m.group(2)
                court = cls_plein.rsplit(".", 1)[-1]
                if not args.tous and court not in PREFIXE_DSL:
                    continue
                cite = "%s$$%s" % (cls_plein, meth)
                if meth in prop.get(court, ()) or meth in prop.get(cls_plein, ()):
                    cats["TROUVEE"] += 1
                    continue
                ailleurs = par_methode.get(meth, set())
                if ailleurs:
                    cats["INTROUVABLE_AVEC_HOMONYME"] += 1
                    homonymes.append((p, num, cite, ailleurs))
                else:
                    cats["INTROUVABLE_SANS_HOMONYME"] += 1
                    orphelines.append((p, num, cite))

    total = sum(cats.values())
    print("FICHIERS BALAYES   : %d" % nb_fichiers)
    print("")
    print("CITATIONS          : %d" % total)
    for k in ("TROUVEE", "INTROUVABLE_AVEC_HOMONYME", "INTROUVABLE_SANS_HOMONYME"):
        print("  %-28s %d" % (k, cats[k]))

    if homonymes:
        print("")
        print("=== INTROUVABLES, MAIS LA METHODE EXISTE AILLEURS (le gisement) ===")
        par_cite = defaultdict(list)
        for p, num, cite, ailleurs in homonymes:
            par_cite[(cite, tuple(sorted(ailleurs)))].append((p, num))
        for (cite, ailleurs), sites in sorted(par_cite.items(), key=lambda kv: -len(kv[1])):
            proprios = sorted({c.rsplit(".", 1)[-1] for c in ailleurs})
            print("")
            print("  CITE   : %s        (%d site(s))" % (cite, len(sites)))
            print("  REEL   : %s" % ", ".join("%s$$%s" % (c, cite.split("$$", 1)[1])
                                              for c in proprios[:4]))
            for p, num in sites[:6]:
                print("           %s:%d" % (p.relative_to(REPO).as_posix(), num))
            if len(sites) > 6:
                print("           ... et %d autre(s)" % (len(sites) - 6))

    if orphelines:
        print("")
        print("=== INTROUVABLES SANS HOMONYME (liste, PAS un rouge) ===")
        print("  Corps dedupliqu'e, generique pleinement partage, ou coquille :")
        print("  l'ABSENCE dans les tables ne prouve rien (cf. CLAUDE.md).")
        for cite, n in Counter(c for _, _, c in orphelines).most_common(20):
            print("    %-70s %d" % (cite, n))

    if args.corrige:
        n = corriger(homonymes)
        print("")
        print("REECRITURES        : %d" % n)

    if args.cliquet and cats["INTROUVABLE_AVEC_HOMONYME"]:
        print("")
        print("ROUGE : %d citation(s) designent un proprietaire qui ne porte pas la methode."
              % cats["INTROUVABLE_AVEC_HOMONYME"])
        return 1
    return 0


def corriger(homonymes) -> int:
    """Reecrit les citations dont la methode a un proprietaire UNIQUE dans les tables.

    Deux gardes, et elles ne sont pas decoratives :
      * proprietaire AMBIGU (>1 classe) -> on ne touche pas. Choisir a la place du lecteur
        ecrirait un nom FAUX, pire que le nom absent (meme regle que la conversion d'enums).
      * la ligne doit etre de la PROSE. On n'ecrit jamais dans un identifiant executable.
    """
    par_fichier = defaultdict(list)
    for p, num, cite, ailleurs in homonymes:
        proprios = {c.rsplit(".", 1)[-1] for c in ailleurs}
        if len(proprios) != 1:
            continue
        par_fichier[p].append((num, cite, proprios.pop()))

    total = 0
    for p, items in par_fichier.items():
        lignes = p.read_text(encoding="utf-8").splitlines(keepends=True)
        for num, cite, proprio in items:
            cls_plein, meth = cite.split("$$", 1)
            ns = cls_plein.rsplit(".", 1)[0] if "." in cls_plein else ""
            neuf = ("%s.%s$$%s" % (ns, proprio, meth)) if ns else ("%s$$%s" % (proprio, meth))
            i = num - 1
            if 0 <= i < len(lignes) and cite in lignes[i]:
                lignes[i] = lignes[i].replace(cite, neuf)
                total += 1
        p.write_text("".join(lignes), encoding="utf-8")
    return total


if __name__ == "__main__":
    sys.exit(main())
