#!/usr/bin/env python3
"""#419-r1-tr9-r4-r1-r3 / #1032-r3 -- le cliquet des SYMBOLES CITES : existent-ils ?

Le pendant, sur l'axe des NOMS, de `probe_va_in_code_vs_prose.py` (axe des ADRESSES).

    python probe_419r1tr9r4r1r3_symboles_cites_absents.py                # perimetre DSL*
    python probe_419r1tr9r4r1r3_symboles_cites_absents.py --tous         # toutes les classes
    python probe_419r1tr9r4r1r3_symboles_cites_absents.py --racine docs  # la prose aussi
    python probe_419r1tr9r4r1r3_symboles_cites_absents.py --cliquet      # rc 1 si migrable
    python probe_419r1tr9r4r1r3_symboles_cites_absents.py --corrige      # REECRIT (prose seule)
    python probe_419r1tr9r4r1r3_symboles_cites_absents.py --regenerer    # l'entree versionnee

CE QU'IL MESURE. Toute citation de la forme `<Namespace>.<Classe>$$<Methode>` ecrite dans une
docstring / un commentaire / une chaine du corpus est confrontee aux sources du build :

  * `data/symbols/<build>/metadata/dsl_declared_methods.tsv` -- l'entree VERSIONNEE que
    `--regenerer` derive du `global-metadata.dat`. **Source COMPLETE** pour les cinq classes
    statiques du DSL, et la SEULE qui fasse autorite sur elles (cf. plus bas) ;
  * `data/symbols/<build>/ghidra/functions.tsv`  -- format `<adresse>\\t<Classe>$$<Methode>` ;
  * `data/symbols/<build>/frida/methods.tsv`     -- format `<rva>\\t<Classe>.<Methode>\\t...`.

POURQUOI LES DEUX TABLES NE SUFFISENT PAS, ET LE MESUREMENT QUI LE MONTRE
-------------------------------------------------------------------------
Les deux tables sont indexees par ADRESSE, et l'ICF fond les corps identiques : un corps partage
par N methodes n'a qu'UN proprietaire nomme. Consequences MESUREES sur `t6dpr4k06g` :

  * `IdunBattleLogic.Entities.DSLFactory` parait ne porter que **5** methodes dans
    `ghidra/functions.tsv` -- le `global-metadata.dat` en declare **35** (les 30 manquantes sont
    des accesseurs de propriete a corps trivial, dont `get_Sel` / `get_Val` / `get_Do` / `get_If`,
    les quatre sous-fabriques). << 5 methodes >> est donc un artefact de table, pas un fait ;
  * `DSLFormulas$$Difference` et `DSLSelectors$$Null` sont ABSENTS des deux tables et EXISTENT
    dans le metadata. Un garde qui n'aurait lu que les tables les aurait classes
    << mecanique disparue >>, alors que ce sont de simples changements de PROPRIETAIRE.

CE QUE LE GISEMENT EST REELLEMENT : UNE SCISSION DE CLASSE
----------------------------------------------------------
Le build de mai portait UNE classe `DSLFactory` qui declarait tout le DSL (selecteurs, triggers,
behaviours, formules) -- c'est ce que le port cite. Le build courant l'a SCINDEE en cinq :
`DSLFactory` ne garde que l'etat et les quatre sous-fabriques, et les noeuds vivent sous
`DSLSelectors` (257), `DSLTriggers` (198), `DSLBehaviors` (183), `DSLFormulas` (135). Le NOM COURT
est identique des deux cotes : la migration est donc mecanique DES QUE le proprietaire est unique.
Les champs ont bouge en meme temps (`factory+0x148 Owner` == `DSLSelectors+0x30`, ecart 0x118) --
ce probe ne garde QUE l'axe des noms.

VENTILATION (l'absence ne prouve rien -- d'ou le tri, et le cliquet ne rougit que sur le SUR)
---------------------------------------------------------------------------------------------
  * `TROUVEE`            -- la classe citee declare bien la methode.
  * `A_MIGRER`           -- EXACTEMENT UNE des cinq classes DSL la declare, et ce n'est pas celle
    qui est citee. Mecanique, et le SEUL etat sur lequel le cliquet rougit.
  * `AMBIGUE_DSL`        -- PLUSIEURS des cinq la declarent (`Cache` en a 3, `If` 3, `Get` 2...).
    Le discriminant est le TYPE DE RETOUR au site, pas le nom : on ne DEVINE pas, on LISTE.
  * `HORS_FAMILLE_DSL`   -- aucune des cinq, mais la methode existe ailleurs dans les tables.
  * `INTROUVABLE`        -- nulle part. Corps deduplique, generique, coquille -- ou une citation
    NEGATIVE deliberee (le corpus en porte : << aucun `DSLFactory$$RemoveTrait` n'existe >>).

Sortie ASCII pure (console cp1252).
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

REPO = HERE.parents[1]

#: `Namespace.Classe$$Methode`. Le `$$` est le separateur Ghidra ; la partie gauche peut porter
#: des points (le namespace) et la droite un `.ctor`/`.cctor`.
#:
#: ⚠ Le backtick n'est accepte QUE dans la forme IL2CPP `Nom`1` (backtick suivi d'un chiffre
#: d'arite). Le laisser libre dans le charset faisait avaler le backtick de FERMETURE d'un
#: `code span` markdown : mesure d'origine, la citation `AttackWithAttackDamage` (43 sites,
#: gisement REEL) etait scindee en deux entrees dont une fantome a 74 sites, rangee en
#: `SANS HOMONYME` -- le probe SOUS-COMPTAIT son propre gisement en le deguisant en bruit.
_MOT = r"[A-Za-z_]\w*(?:`\d+)?"
CITATION_RE = re.compile(r"\b(%s(?:\.%s)*)\$\$(\.?%s)" % (_MOT, _MOT, _MOT))

#: Le perimetre par defaut = les cinq classes statiques du DSL, foyer du residu.
PREFIXE_DSL = ("DSLFactory", "DSLTriggers", "DSLBehaviors", "DSLSelectors", "DSLFormulas")

#: Le namespace qui les porte, pour reconstruire une citation PLEINE.
NS_DSL = "IdunBattleLogic.Entities"

#: L'entree VERSIONNEE, relative a `data/symbols/<build>/`. C'est elle qui rend ce probe jouable
#: dans un worktree ou le jeu n'est pas installe.
TSV_REL = ("metadata", "dsl_declared_methods.tsv")

EXT_TEXTE = {".py", ".md", ".ts", ".txt"}

#: ⚠ CE QUI NE DOIT JAMAIS ETRE REECRIT : une citation NEGATIVE. Le corpus en porte -- des phrases
#: dont TOUT LE PROPOS est qu'un symbole N'EXISTE PAS (`probe_225_trait_gates` : << Aucun
#: `DSLFactory$$RemoveTrait` n'existe >>) ou qu'une citation etait FAUSSE (`selectors/units.py`,
#: qui cite l'ancienne orthographe `First` comme l'affirmation que #1032-r2 refute). Les reecrire
#: DETRUIRAIT le sens de la phrase : elle dirait alors qu'un symbole existant n'existe pas.
#:
#: ⚠ **CE PROBE S'EST REECRIT LUI-MEME, ET C'EST POURQUOI CES DEUX PHRASES NE CITENT PLUS**
#: (mesure du 2026-08-17) : sa propre docstring portait deux citations de l'ancienne orthographe,
#: en position d'ANECDOTE et d'EXEMPLE. `--corrige` les a migrees -- ce qui a rendu FAUSSE la
#: phrase qui disait << voila la citation qu'il ne faut pas migrer >>. Un migrateur de masse est
#: dans son propre perimetre : ne pas y ecrire de citation qu'on ne veut pas voir migrer.
#:
#: ⚠ **LE FILTRE EST ETROIT, ET IL L'EST PAR MESURE.** Sa premiere forme retenait aussi `aucun`,
#: `absent`, `faux`, `perime` : sur les 27 lignes qu'elle a bloquees, **22 etaient des faux
#: positifs** (<< aucun batch AoE >>, << 0 si absent >>, << aucune formule >>, << ABSENT des xrefs
#: de <autre symbole> >>) -- un filtre trop large ne protege pas, il PARALYSE la migration en
#: laissant croire qu'elle a fini. Ne restent que les formes ou la negation porte sur l'EXISTENCE
#: du symbole lui-meme. Ce qui est retenu est LISTE, jamais reecrit en silence, et se relit a la
#: main -- c'est le seul regime honnete pour un filtre qui ne comprend pas la phrase.
NEGATIF_RE = re.compile(
    r"n'existe|nexiste|inexistant|introuvable|ne porte que|FAUSSE|PERIMEE|N'EXISTE",
    re.IGNORECASE)


class Refus(RuntimeError):
    """Mesure IMPOSSIBLE. Jamais rabattue sur un verdict."""


def build_courant() -> str:
    return (REPO / "data" / "symbols" / "CURRENT").read_text(encoding="utf-8").strip()


# ------------------------------------------------------------------ l'entree VERSIONNEE


def chemin_tsv(build: str) -> Path:
    return REPO.joinpath("data", "symbols", build, *TSV_REL)


def charger_declarations(build: str) -> dict[str, set[str]]:
    """`{classe courte -> {methodes DECLAREES}}` pour les cinq classes DSL.

    Source COMPLETE (le metadata declare TOUT, l'ICF ne fond que les corps). Absente => `{}`,
    et le probe le DIT : il retombe alors sur les seules tables, donc sur une lecture qui
    SOUS-COMPTE -- jamais sur un vert."""
    p = chemin_tsv(build)
    if not p.exists():
        return {}
    out: dict[str, set[str]] = defaultdict(set)
    with p.open("r", encoding="utf-8") as fh:
        for ligne in fh:
            if ligne.startswith("#"):
                continue
            c = ligne.rstrip("\n").split("\t")
            if len(c) < 2:
                continue
            out[c[0].rsplit(".", 1)[-1]].add(c[1])
    return dict(out)


def regenerer(build: str) -> int:
    """Derive les methodes DECLAREES des cinq classes DSL depuis `global-metadata.dat`.

    Meme forme que `probe_477r25 --regenerer` : le jeu vit HORS du depot, donc la derivation
    n'est possible que sur la machine ou il est installe, et son resultat entre au depot comme
    une ENTREE VERSIONNEE (`data/` = ce qu'on LIT)."""
    import build_pin
    import il2cpp_metadata as MD

    dll = build_pin.game_dll()
    meta = next(iter(dll.parent.rglob("global-metadata.dat")), None)
    if meta is None:
        raise Refus("NON MESURE : `global-metadata.dat` introuvable a cote de GameAssembly.dll")
    methods_tsv = REPO / "data" / "symbols" / build / "frida" / "methods.tsv"
    ancres = (("Core.Services", "OperationProcessor"),
              ("IdunBattle.Core.Services", "BattleQuery"),
              ("IdunBattle.Core.Services", "AttackQuery"),
              ("IdunBattle.Core.Services", "MovementQuery"),
              ("IdunBattle.Core.Services", "DamageCalculations"),
              ("IdunBattle.Core", "MatchState"))
    types = tuple((NS_DSL, n) for n in PREFIXE_DSL)
    table = MD.noms_declares(meta, methods_tsv, ancres, types)
    if table is None:
        raise Refus("NON MESURE : metadata non alignable sur ce build -- rien devine, rien ecrit.")

    lignes = ["#! genere par probe_419r1tr9r4r1r3_symboles_cites_absents.py --regenerer",
              "#! source : global-metadata.dat du build %s (les DECLARATIONS, pas les corps)" % build,
              "#! <classe pleine>\\t<methode>"]
    total = 0
    for (ns, nom), noms in sorted(table.items()):
        for m in sorted(set(noms)):
            lignes.append("%s.%s\t%s" % (ns, nom, m))
            total += 1
    if total == 0:
        raise Refus("NON MESURE : 0 declaration lue -- on n'ECRIT pas une entree vide.")
    p = chemin_tsv(build)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(lignes) + "\n", encoding="utf-8")
    print("ECRIT : %s (%d declaration(s), %d classe(s))"
          % (p.relative_to(REPO).as_posix(), total, len(table)))
    return 0


# ------------------------------------------------------------------ les deux TABLES


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


def fichiers(racines, exclure=()):
    exclus = {e.replace("\\", "/") for e in exclure}
    for racine in racines:
        rp = REPO / racine
        if not rp.exists():
            continue
        candidats = [rp] if rp.is_file() else [p for p in sorted(rp.rglob("*"))
                                               if p.is_file() and p.suffix in EXT_TEXTE]
        for p in candidats:
            if p.relative_to(REPO).as_posix() in exclus:
                continue
            yield p


# ------------------------------------------------------------------ le RECENSEMENT


def recenser(racines, decl, prop, par_methode, tous=False, exclure=()):
    """Rend `(compteurs, sites)` ou `sites[categorie]` liste `(fichier, ligne, cite, detail)`."""
    cats = Counter()
    sites = defaultdict(list)
    nb_fichiers = 0
    for p in fichiers(racines, exclure):
        try:
            src = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        nb_fichiers += 1
        for num, ligne in enumerate(src.splitlines(), 1):
            for m in CITATION_RE.finditer(ligne):
                cls_plein, meth = m.group(1), m.group(2)
                court = cls_plein.rsplit(".", 1)[-1]
                if not tous and court not in PREFIXE_DSL:
                    continue
                cite = "%s$$%s" % (cls_plein, meth)
                if court in decl:
                    if meth in decl[court]:
                        cats["TROUVEE"] += 1
                        continue
                    proprios = sorted(d for d, s in decl.items() if meth in s)
                    if len(proprios) == 1:
                        cats["A_MIGRER"] += 1
                        sites["A_MIGRER"].append((p, num, cite, proprios[0]))
                        continue
                    if len(proprios) > 1:
                        cats["AMBIGUE_DSL"] += 1
                        sites["AMBIGUE_DSL"].append((p, num, cite, "/".join(proprios)))
                        continue
                elif meth in prop.get(court, ()) or meth in prop.get(cls_plein, ()):
                    cats["TROUVEE"] += 1
                    continue
                ailleurs = {c.rsplit(".", 1)[-1] for c in par_methode.get(meth, set())}
                if ailleurs:
                    cats["HORS_FAMILLE_DSL"] += 1
                    sites["HORS_FAMILLE_DSL"].append((p, num, cite, ", ".join(sorted(ailleurs)[:6])))
                else:
                    cats["INTROUVABLE"] += 1
                    sites["INTROUVABLE"].append((p, num, cite, ""))
    return cats, sites, nb_fichiers


def corriger(a_migrer) -> tuple[int, list]:
    """Reecrit `<X>$$<m>` en `<NS>.<Proprietaire>$$<m>` pour les sites A_MIGRER.

    DEUX gardes, et aucune n'est decorative :
      * la ligne ne doit pas etre une CITATION NEGATIVE (cf. `NEGATIF_RE`) -- une phrase dont le
        propos est qu'un symbole n'existe pas deviendrait FAUSSE en etant << corrigee >> ;
      * on ne reecrit que le TOKEN cite, jamais la ligne -- et le namespace ecrit est celui du
        build (`IdunBattleLogic.Entities`), pour que la citation soit grepable telle quelle.
    Les lignes retenues par la premiere garde sont RENDUES, jamais tues.
    """
    par_fichier = defaultdict(list)
    refuses = []
    for p, num, cite, proprio in a_migrer:
        par_fichier[p].append((num, cite, proprio))
    total = 0
    for p, items in par_fichier.items():
        lignes = p.read_text(encoding="utf-8").splitlines(keepends=True)
        change = False
        for num, cite, proprio in items:
            i = num - 1
            if not (0 <= i < len(lignes)) or cite not in lignes[i]:
                continue
            if NEGATIF_RE.search(lignes[i]):
                refuses.append((p, num, cite, "citation NEGATIVE : la phrase AFFIRME l'absence"))
                continue
            meth = cite.split("$$", 1)[1]
            lignes[i] = lignes[i].replace(cite, "%s.%s$$%s" % (NS_DSL, proprio, meth))
            change = True
            total += 1
        if change:
            p.write_text("".join(lignes), encoding="utf-8", newline="")
    return total, refuses


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--racine", action="append", default=None,
                    help="racine a balayer (defaut : scripts/python)")
    ap.add_argument("--exclure", action="append", default=None,
                    help="chemin RELATIF a ne pas balayer (repetable)")
    ap.add_argument("--tous", action="store_true",
                    help="toutes les classes citees, pas seulement DSL*")
    ap.add_argument("--cliquet", action="store_true",
                    help="rc 1 des qu'une citation est MIGRABLE (proprietaire DSL unique)")
    ap.add_argument("--corrige", action="store_true",
                    help="REECRIT les citations A_MIGRER (prose seulement)")
    ap.add_argument("--regenerer", action="store_true",
                    help="derive l'entree versionnee depuis le global-metadata.dat du jeu")
    ap.add_argument("--detail", action="store_true", help="chaque site, une ligne")
    args = ap.parse_args()

    build = build_courant()
    if args.regenerer:
        try:
            return regenerer(build)
        except (Refus, OSError) as exc:
            print("NON MESURE : %s" % exc)
            return 2

    racines = args.racine or ["scripts/python"]
    exclure = tuple(args.exclure or ())
    prop, par_methode, vus = charger_tables(build)
    decl = charger_declarations(build)

    print("BUILD              : %s" % build)
    print("SYMBOLES EN TABLE  : %d (ghidra + frida fusionnees)" % vus)
    if decl:
        print("DECLARATIONS DSL   : %s"
              % ", ".join("%s %d" % (k, len(v)) for k, v in sorted(decl.items())))
    else:
        print("DECLARATIONS DSL   : ABSENTES (%s) -- lecture DEGRADEE aux seules tables, qui"
              % chemin_tsv(build).relative_to(REPO).as_posix())
        print("                     SOUS-COMPTENT (l'ICF fond les corps). `--regenerer` les ecrit.")
    print("RACINES            : %s" % ", ".join(racines))
    if exclure:
        print("EXCLUS             : %s" % ", ".join(exclure))
    print("PERIMETRE          : %s" % ("toutes les classes" if args.tous
                                       else "classes " + "/".join(PREFIXE_DSL)))

    cats, sites, nb_fichiers = recenser(racines, decl, prop, par_methode,
                                        tous=args.tous, exclure=exclure)
    total = sum(cats.values())
    print("FICHIERS BALAYES   : %d" % nb_fichiers)
    print("")
    print("CITATIONS          : %d" % total)
    for k in ("TROUVEE", "A_MIGRER", "AMBIGUE_DSL", "HORS_FAMILLE_DSL", "INTROUVABLE"):
        print("  %-22s %d" % (k, cats[k]))
    if total == 0:
        print("")
        print("ROUGE : le recensement n'a trouve AUCUNE citation -- un balayage vide n'est pas")
        print("        un vert. Le motif ou les racines sont-ils encore justes ?")
        return 1 if args.cliquet else 0

    for cat, titre in (("A_MIGRER", "MIGRABLES -- une seule des cinq classes DSL la declare"),
                       ("AMBIGUE_DSL", "AMBIGUES -- plusieurs la declarent ; le TYPE DE RETOUR "
                                       "au site tranche, jamais le nom"),
                       ("HORS_FAMILLE_DSL", "HORS FAMILLE DSL -- la methode vit ailleurs"),
                       ("INTROUVABLE", "INTROUVABLES -- nulle part (corps fondu, generique, "
                                       "coquille, ou citation NEGATIVE deliberee)")):
        if not sites[cat]:
            continue
        print("")
        print("=== %s ===" % titre)
        groupes = defaultdict(list)
        for p, num, cite, detail in sites[cat]:
            groupes[(cite, detail)].append((p, num))
        for (cite, detail), lieux in sorted(groupes.items(), key=lambda kv: -len(kv[1])):
            print("  %-62s %3d site(s)  -> %s" % (cite, len(lieux), detail))
            if args.detail:
                for p, num in lieux:
                    print("        %s:%d" % (p.relative_to(REPO).as_posix(), num))

    if args.corrige:
        n, refuses = corriger(sites["A_MIGRER"])
        print("")
        print("REECRITURES        : %d" % n)
        if refuses:
            print("REFUSEES (%d) -- citations NEGATIVES, la reecriture les rendrait FAUSSES :"
                  % len(refuses))
            for p, num, cite, pourquoi in refuses:
                print("    %s:%d  %s  (%s)" % (p.relative_to(REPO).as_posix(), num, cite, pourquoi))
        return 0

    if args.cliquet:
        if not decl:
            print("")
            print("NON MESURE : l'entree versionnee des declarations DSL est absente -- le")
            print("             cliquet ne se rabat NI sur un vert NI sur un rouge.")
            return 2
        if cats["A_MIGRER"]:
            print("")
            print("ROUGE : %d citation(s) designent une classe qui ne declare pas la methode,"
                  % cats["A_MIGRER"])
            print("        alors qu'UNE SEULE des cinq classes DSL la declare. `--corrige`.")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
