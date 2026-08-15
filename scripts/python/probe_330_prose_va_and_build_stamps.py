#!/usr/bin/env python3
"""#330 -- MESURE de population : VA absolues et estampilles de build dans la PROSE.

Pourquoi ce probe existe alors que `probe_va_in_code_vs_prose.py` est deja la : ce
dernier ne collecte QUE des `*.py` (`p.rglob("*.py")`). Lance sur `docs`, il imprime
"fichiers Python scannes : 0" puis "AUCUNE occurrence ... migration sans risque de
casse" -- un VERT sur un repertoire qu'il n'a jamais regarde. La migration de build
#251 n'avait donc aucun moyen de voir le gisement des `.md`.

Ce probe scanne la PROSE (`.md`, `.txt`, `.tsv`, `.json` de doc) sous les racines
donnees et repond a deux questions distinctes :

  (1) VA ABSOLUES -- formes `0x18xxxxxxx` / `@18xxxxxxx`. Meme regex que le probe
      code, pour que les deux comptes soient comparables. Les VA RELATIVES (offsets
      de champ `+0xa8`, slots de vtable, RVA calculees depuis l'image base) ne sont
      PAS concernees : le regex exige 9 chiffres hexa commencant par `18`, ce qu'un
      offset relatif n'a jamais.

      Ventilation, contre la table du build CURRENT (`data/symbols/<CURRENT>/ghidra/
      functions.tsv`) :
        - IMAGE_BASE          `0x180000000` exactement -- ce n'est pas une citation.
        - PLACEHOLDER (FUN_)  le "symbole" n'est que l'adresse deguisee -> RESTE en
                              VA, c'est la doctrine du CLAUDE.md. A LISTER, pas a
                              maquiller.
        - MIGRABLE            resout sur un vrai symbole -> doit devenir
                              `<symbole>[+0x<offset>]`.
        - HORS TABLE          avant le premier symbole connu -> non resolvable.

      Axe orthogonal, la FRAICHEUR (calcule quand une table d'un build anterieur est
      presente) : une VA qui est une adresse de debut de fonction EXACTE dans un
      ancien build mais PAS dans le build courant est une citation PERIMEE AVEREE --
      elle resoudra silencieusement sur une autre fonction.

      Troisieme axe, celui qui rend la mesure ACTIONNABLE -- la FAMILLE du document :
        - CASE-DOC (`case-*.md`) : compte rendu DATE d'un cas clos. "RE faite contre
          gqfc5mff6c" y est un fait exact, pas un mensonge ; ses VA sont figees avec
          le cas. Priorite basse.
        - REFERENCE VIVANTE (tout le reste : catalogues, inventaires, roadmaps,
          `docs/rl/playbook/*`, `.claude/**`) : consulte comme etat COURANT. C'est
          exactement le profil du defunt `dsl-vocabulary-catalog.md` -- estampille
          d'un build anterieur, sans bandeau, lu comme a jour. Priorite HAUTE.

  (2) ESTAMPILLES DE BUILD -- un hash de build (reconnu par `build_hash`, qui DERIVE la
      liste des builds de l'arbre au lieu d'epingler une forme) different du contenu de
      `data/symbols/CURRENT`. Distingue :
        - EN-TETE  : le hash apparait dans les `--stamp-lines` premieres lignes, ou
                     sur une ligne qui le DECLARE (`build: x`, `build **x**`, ...).
                     C'est l'estampille du document -- perimee, elle fait lire tout
                     le doc contre le mauvais binaire (cas declencheur : le defunt
                     `dsl-vocabulary-catalog.md`, estampille `gqfc5mff6c`).
        - CORPS    : mention ailleurs. Souvent LEGITIME (un doc de migration parle
                     forcement des deux builds) -- compte a part, jamais melange.

Mode CLIQUET (`--fail-on-header-stamp`) : sortie 1 s'il existe une estampille
d'EN-TETE perimee. C'est le seul axe ou zero est tenable aujourd'hui ; les VA sont un
stock historique qui se resorbe par tranches, pas un invariant.

Sortie ASCII pure (console Windows cp1252).
"""
from __future__ import annotations

import argparse
import bisect
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "scripts" / "python") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts" / "python"))

import build_hash  # noqa: E402

SYMBOLS_DIR = REPO / "data" / "symbols"
IMAGE_BASE = 0x180000000

# Meme regex que probe_va_in_code_vs_prose.py -- les deux comptes doivent etre comparables.
VA_RE = re.compile(r"(?<![0-9a-fA-Fx])(?:0x|@)(18[0-9a-fA-F]{7})(?![0-9a-fA-F])")

# LA CIBLE DU RECENSEUR -- DERIVEE DE L'ARBRE, PLUS JAMAIS ECRITE ICI (#330-r3).
#
# Ce module portait `r"(?<![a-z0-9])([a-z0-9]{8}6c)(?![a-z0-9])"`, et `DECLARES_RE` la MEME forme
# une seconde fois. Le suffixe `6c` etait une REGULARITE des six premiers builds observes, pas une
# regle : `BUILD_RE.search(current_build())` rendait `None` sur `t6dpr4k06g`. Mesure du
# 2026-08-15, sur le seul perimetre de ce probe (`docs` + `.claude`, `.md/.txt/.tsv`) :
# 60 occurrences du build courant invisibles, dans 17 fichiers -- dont les trois `.tsv` de
# `docs/rl/dsl-usage/`, qui n'ont aucune autre garde que leur estampille.
#
# La forme se DERIVE (`build_hash` : tables versionnees, `CURRENT`, position de chemin,
# installation locale) et `build_hash.verifier_la_forme()` REFUSE si un build connu lui echappe.
BUILD_RE = build_hash.build_re()

# Une ligne qui DECLARE le build de reference du document, ou qu'elle se trouve. Le hash y est le
# MEME motif derive -- les porter separement, c'etait garantir qu'ils divergent (ils avaient
# diverge : la doctrine du depot a corrige `build-pin.ts` sans voir ces deux-ci).
DECLARES_RE = re.compile(
    r"(build|dump|binaire|binary|symbols?|table)\b[^\n]{0,40}?" + BUILD_RE.pattern,
    re.IGNORECASE,
)

PROSE_EXT = {".md", ".txt", ".tsv"}
DEFAULT_ROOTS = ("docs", ".claude")
# `.claude/worktrees` = les checkouts des autres agents ; `data/symbols` = les tables
# elles-memes (leur README cite forcement des hashes, et functions.tsv EST une liste
# d'adresses). Ni l'un ni l'autre n'est de la prose du depot.
DEFAULT_EXCLUDES = (".claude/worktrees", "data/symbols", "node_modules")


# --------------------------------------------------------------------------- tables


def read_current_build() -> str:
    p = SYMBOLS_DIR / "CURRENT"
    if not p.exists():
        raise SystemExit("data/symbols/CURRENT absent -- impossible de savoir quel build est courant")
    return p.read_text(encoding="utf-8").strip()


def available_builds() -> list:
    if not SYMBOLS_DIR.is_dir():
        return []
    return sorted(d.name for d in SYMBOLS_DIR.iterdir()
                  if d.is_dir() and (d / "ghidra" / "functions.tsv").exists())


class SymbolTable:
    """Table `<adresse VA hexa>\\t<symbole>` d'un build, interrogeable par adresse."""

    def __init__(self, build: str):
        self.build = build
        self.addrs = []          # trie
        self.names = []          # parallele a addrs
        self.exact = {}          # adresse -> symbole (debut de fonction)
        path = SYMBOLS_DIR / build / "ghidra" / "functions.tsv"
        pairs = []
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("#"):
                    continue
                addr, _, name = line.rstrip("\n").partition("\t")
                if not name:
                    continue
                try:
                    a = int(addr, 16)
                except ValueError:
                    continue
                pairs.append((a, name))
        pairs.sort()
        for a, name in pairs:
            self.addrs.append(a)
            self.names.append(name)
            self.exact.setdefault(a, name)

    def whereis(self, va: int):
        """-> (symbole, offset) du symbole englobant, ou (None, None) si avant le premier.

        AUCUNE borne : le "symbole englobant" peut etre un voisin arbitrairement lointain
        (l'adresse tombe alors dans une zone non nommee -- donnees, slots methodPointers).
        Utiliser `covering()` pour exiger que la VA soit REELLEMENT dans la fonction.
        """
        i = bisect.bisect_right(self.addrs, va) - 1
        if i < 0:
            return None, None
        return self.names[i], va - self.addrs[i]

    def covering(self, va: int):
        """-> (symbole, offset) SEULEMENT si la VA tombe dans l'etendue de la fonction.

        L'etendue est bornee par le symbole SUIVANT : c'est un majorant (du padding peut
        s'y glisser), mais il elimine le vrai faux positif -- une adresse de DONNEE citee
        loin apres la derniere fonction nommee, que `whereis` attribue sans sourciller.
        Mesure a l'appui : `EffectsDatabase$$InitializeEffects` fait 0x194c0 octets sur
        rnca9r7q6c ; un seuil fixe (0x10000) l'aurait tronquee.
        """
        i = bisect.bisect_right(self.addrs, va) - 1
        if i < 0:
            return None, None
        span = (self.addrs[i + 1] - self.addrs[i]) if i + 1 < len(self.addrs) else 0x1000
        off = va - self.addrs[i]
        if off >= span:
            return None, None
        return self.names[i], off


# --------------------------------------------------------------------------- scan


def iter_prose_files(roots, excludes):
    for root in roots:
        p = REPO / root
        if p.is_file():
            files = [p]
        elif p.is_dir():
            files = [f for f in p.rglob("*") if f.is_file() and f.suffix.lower() in PROSE_EXT]
        else:
            continue
        for f in files:
            rel = f.relative_to(REPO).as_posix()
            if any(ex in rel for ex in excludes):
                continue
            yield f, rel


def classify_va(va: int, tables: list):
    """-> (categorie, citation, build de resolution).

    ORDRE DE RESOLUTION -- et c'est le point qui a failli fausser la mesure : une VA ecrite
    contre un build ANTERIEUR resout, contre la table COURANTE, sur une fonction arbitraire.
    On essaie donc TOUTES les tables, en privilegiant une correspondance EXACTE de debut de
    fonction (signature d'une citation d'adresse de fonction) avant un point interne.

    `tables` = [table courante, tables anterieures...].
    """
    if va == IMAGE_BASE:
        return "IMAGE_BASE", None, None
    for t in tables:                                   # 1. debut de fonction exact
        n = t.exact.get(va)
        if n and not n.startswith("FUN_"):
            return "MIGRABLE", n, t.build
    for t in tables:                                   # 2. point interne d'une fonction nommee
        n, off = t.covering(va)
        if n and not n.startswith("FUN_"):
            return "MIGRABLE", "%s+0x%x" % (n, off), t.build
    for t in tables:                                   # 3. corps reel, mais sans nom
        n, off = t.covering(va)
        if n:
            return "PLACEHOLDER (FUN_)", "%s+0x%x" % (n, off) if off else n, t.build
    return "HORS CODE (donnees / slot methodPointers)", None, None


# `case-<...>.md` OU tout fichier sous un repertoire `case-<N>/` (ex. `docs/rl/case-220/orks.md`,
# qui est un chapitre du compte rendu #220, pas un document de reference).
CASE_DOC_RE = re.compile(r"(^|/)case-[^/]*(/|\.(md|txt|tsv)$)", re.IGNORECASE)


def family(rel: str) -> str:
    """CASE-DOC (compte rendu date, fige avec son cas) vs REFERENCE (lu comme etat courant)."""
    return "CASE-DOC" if CASE_DOC_RE.search(rel) else "REFERENCE"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("roots", nargs="*", default=list(DEFAULT_ROOTS))
    ap.add_argument("--exclude", action="append", default=list(DEFAULT_EXCLUDES))
    ap.add_argument("--stamp-lines", type=int, default=12,
                    help="nombre de lignes de tete ou un hash compte comme ESTAMPILLE (defaut 12)")
    ap.add_argument("--top", type=int, default=15, help="nombre de fichiers detailles")
    ap.add_argument("--list-placeholders", action="store_true",
                    help="lister les occurrences qui RESTENT en VA (FUN_ / hors table)")
    ap.add_argument("--list-header-stamps", action="store_true", default=True)
    ap.add_argument("--fail-on-header-stamp", action="store_true",
                    help="cliquet : sortie 1 s'il reste une estampille d'EN-TETE perimee")
    args = ap.parse_args()

    current = read_current_build()
    builds = available_builds()
    if current not in builds:
        raise SystemExit("table du build courant (%s) absente ; disponibles : %s"
                         % (current, ", ".join(builds) or "aucune"))
    cur = SymbolTable(current)
    olds = [SymbolTable(b) for b in builds if b != current]
    tables = [cur] + olds

    print("build courant (data/symbols/CURRENT) : %s" % current)
    print("tables chargees : %s" % ", ".join([current] + [t.build for t in olds]))
    print("racines : %s" % ", ".join(args.roots))
    # LA CIBLE DU RECENSEUR, DITE AVANT TOUT COMPTE (#330-r3) : ce probe a compte 2 903
    # occurrences pendant qu'il en ratait 176 -- celles du build COURANT. Un recenseur qui ne
    # dit pas ce qu'il cherche laisse lire ses zeros comme des mesures.
    try:
        rap = build_hash.verifier_la_forme()
        forme_refusee = ""
    except build_hash.FormeRefusee as exc:
        rap = build_hash.rapport_des_sources()
        forme_refusee = str(exc)
    build_hash.imprimer_les_sources(rap)
    if forme_refusee:
        print("  !! FORME REFUSEE -- %s" % forme_refusee.replace("\n", "\n     "))
    print("")

    files = list(iter_prose_files(args.roots, args.exclude))

    va_cats = Counter()
    va_per_file = Counter()
    fresh_cats = Counter()                    # A JOUR / PERIMEE AVEREE / INDETERMINEE
    fresh_by_family = defaultdict(Counter)
    stale_exact = []          # (rel, ligne, va, build ancien, symbole ancien)
    stale_per_file = Counter()
    residual = []             # (rel, ligne, va, categorie, symbole)
    header_stamps = []        # (rel, ligne, hash, texte)
    header_stamp_families = Counter()
    body_stamps = Counter()
    body_stamp_hashes = Counter()
    files_with_va = set()
    files_with_header_stamp = set()
    candidats = Counter()
    connus = set(rap["connus"])

    for path, rel in files:
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        # INVENTAIRE (non bloquant) : les jetons de la FORME d'un hash qu'aucun build connu ne
        # porte. Seul canal par lequel un build NEUF peut se signaler avant d'avoir une table ou
        # un chemin -- et BRUYANT par construction, donc il ne decide rien (cf. build_hash).
        candidats.update(build_hash.candidats_de_forme(text, connus))
        fam = family(rel)
        lines = text.splitlines()
        for lineno, line in enumerate(lines, 1):
            for m in VA_RE.finditer(line):
                va = int(m.group(1), 16)
                cat, cite, from_build = classify_va(va, tables)
                va_cats[cat] += 1
                va_per_file[rel] += 1
                files_with_va.add(rel)
                if cat.startswith(("PLACEHOLDER", "HORS CODE")):
                    residual.append((rel, lineno, va, cat, cite or ""))
                if cat == "IMAGE_BASE":
                    continue
                if va in cur.exact:
                    fresh = "A JOUR (debut de fonction du build courant)"
                else:
                    fresh = "INDETERMINEE (offset interne ou orpheline)"
                    for t in olds:
                        if va in t.exact and not t.exact[va].startswith("FUN_"):
                            fresh = "PERIMEE AVEREE"
                            naive, _ = cur.whereis(va)
                            stale_exact.append((rel, lineno, va, t.build, t.exact[va], naive))
                            stale_per_file[rel] += 1
                            break
                fresh_cats[fresh] += 1
                fresh_by_family[fam][fresh] += 1

            for m in BUILD_RE.finditer(line):
                h = m.group(1)
                if h == current:
                    continue
                is_header = lineno <= args.stamp_lines or bool(DECLARES_RE.search(line))
                if is_header:
                    header_stamps.append((rel, lineno, h, line.strip()[:120]))
                    header_stamp_families[fam] += 1
                    files_with_header_stamp.add(rel)
                else:
                    body_stamps[rel] += 1
                    body_stamp_hashes[h] += 1

    total_va = sum(va_cats.values())
    print("=== (1) VA ABSOLUES dans la PROSE ===")
    print("fichiers de prose scannes : %d" % len(files))
    print("fichiers contenant au moins une VA absolue : %d" % len(files_with_va))
    print("occurrences totales : %d" % total_va)
    print("")
    known = ("MIGRABLE", "PLACEHOLDER (FUN_)",
             "HORS CODE (donnees / slot methodPointers)", "IMAGE_BASE")
    tags = {"MIGRABLE": "a migrer vers <symbole>[+0x<off>]",
            "PLACEHOLDER (FUN_)": "RESTE en VA (le symbole n'est que l'adresse deguisee)",
            "HORS CODE (donnees / slot methodPointers)": "RESTE en VA (aucune fonction ne la couvre)",
            "IMAGE_BASE": "hors sujet (0x180000000 n'est pas une citation)"}
    print("  ventilation (resolution contre TOUTES les tables : %s) :"
          % ", ".join(t.build for t in tables))
    for cat in known:
        print("    %-42s %6d   %s" % (cat, va_cats.get(cat, 0), tags[cat]))
    for cat, n in sorted(va_cats.items()):
        if cat not in known:
            print("    %-42s %6d" % (cat, n))
    legit = sum(va_cats.get(c, 0) for c in
                ("PLACEHOLDER (FUN_)", "HORS CODE (donnees / slot methodPointers)"))
    print("    -> MIGRABLES %d / LEGITIMEMENT EN VA %d / hors sujet %d"
          % (va_cats.get("MIGRABLE", 0), legit, va_cats.get("IMAGE_BASE", 0)))
    print("")
    print("  fraicheur (citations, image base exclue) :")
    if olds:
        for k in ("A JOUR (debut de fonction du build courant)", "PERIMEE AVEREE",
                  "INDETERMINEE (offset interne ou orpheline)"):
            print("    %-46s %6d" % (k, fresh_cats.get(k, 0)))
        print("    (PERIMEE AVEREE = adresse de DEBUT de fonction exacte dans un build")
        print("     ANTERIEUR mais pas dans %s -> resout SILENCIEUSEMENT sur une autre fonction)"
              % current)
        print("")
        divergent = sum(1 for r in stale_exact if r[5] != r[4])
        print("  PIEGE DE MIGRATION -- sur ces %d occurrences perimees, %d resolvent, contre la"
              % (len(stale_exact), divergent))
        print("  table COURANTE, sur un symbole DIFFERENT de celui qu'elles designaient. Les migrer")
        print("  avec `ghidra_symbols.py whereis` (qui lit le build charge) produirait %d citations"
              % divergent)
        print("  FAUSSES mais d'apparence propre. La migration doit lire la table du build D'ORIGINE.")
        for rel, lineno, va, b, old_name, new_name in stale_exact[:3]:
            print("    ex. %s:%d  0x%x" % (rel, lineno, va))
            print("        %-12s -> %s" % (b, old_name[:96]))
            print("        %-12s -> %s" % (current, (new_name or "?")[:96]))
    else:
        print("    aucune table de build anterieur -> axe non mesurable")
    print("")
    print("  par FAMILLE de document :")
    for fam in ("REFERENCE", "CASE-DOC"):
        c = fresh_by_family.get(fam, Counter())
        print("    %-10s total %5d   dont PERIMEE AVEREE %5d"
              % (fam, sum(c.values()), c.get("PERIMEE AVEREE", 0)))
    print("    (REFERENCE = lu comme etat COURANT -> priorite HAUTE ; CASE-DOC = compte")
    print("     rendu date, fige avec son cas -> priorite basse)")
    print("")
    print("  top fichiers REFERENCE par VA PERIMEE AVEREE (le gisement actionnable) :")
    ref_stale = Counter({r: n for r, n in stale_per_file.items() if family(r) == "REFERENCE"})
    for rel, n in ref_stale.most_common(args.top):
        print("    %-62s %d" % (rel[:62], n))
    if len(ref_stale) > args.top:
        print("    ... et %d autre(s) fichier(s) REFERENCE" % (len(ref_stale) - args.top))
    print("")
    print("  top fichiers par volume de VA (toutes familles) :")
    for rel, n in va_per_file.most_common(args.top):
        print("    %-62s %d" % (rel[:62], n))
    if len(va_per_file) > args.top:
        print("    ... et %d autre(s) fichier(s)" % (len(va_per_file) - args.top))
    print("")

    if args.list_placeholders and residual:
        print("  --- occurrences qui RESTENT en VA (%d) ---" % len(residual))
        for rel, lineno, va, cat, name in residual:
            print("    %s:%d  0x%x  %s  %s" % (rel, lineno, va, cat, name or ""))
        print("")

    print("=== (2) ESTAMPILLES DE BUILD != %s ===" % current)
    print("estampilles d'EN-TETE / declaratives perimees : %d occurrence(s) dans %d fichier(s)"
          % (len(header_stamps), len(files_with_header_stamp)))
    for fam in ("REFERENCE", "CASE-DOC"):
        print("    %-10s %d occurrence(s)" % (fam, header_stamp_families.get(fam, 0)))
    if args.list_header_stamps and header_stamps:
        shown = [h for h in header_stamps if family(h[0]) == "REFERENCE"]
        print("  --- estampilles de REFERENCE (priorite HAUTE, %d) ---" % len(shown))
        for rel, lineno, h, txt in shown:
            print("    %s:%d  [%s]  %s" % (rel, lineno, h, txt))
    print("")
    print("mentions en CORPS (souvent legitimes -- doc de migration, historique) : %d dans %d fichier(s)"
          % (sum(body_stamps.values()), len(body_stamps)))
    for h, n in body_stamp_hashes.most_common():
        print("    hash %s : %d mention(s)" % (h, n))
    print("")

    print("=== (3) JETONS DE LA FORME D'UN HASH, qu'AUCUN build connu ne porte (inventaire) ===")
    print("Ce canal ne decide RIEN, et c'est mesure : la forme generique seule rend %d jeton(s)"
          % len(candidats))
    print("distinct(s) sur cette prose, pour %d build(s) reel(s). Le critere qui discrimine est la"
          % len(connus))
    print("POSITION (`games|dumps|symbols/<x>`), pas la forme. Il existe pour qu'un build NEUF")
    print("puisse se signaler avant d'avoir une table ou un chemin.")
    print("  jetons : %d distinct(s), %d occurrence(s)" % (len(candidats), sum(candidats.values())))
    for h, n in candidats.most_common(args.top):
        print("    %-14s %d" % (h, n))
    if len(candidats) > args.top:
        print("    ... et %d autre(s) jeton(s)" % (len(candidats) - args.top))
    print("")

    if args.fail_on_header_stamp and forme_refusee:
        print("CLIQUET ROUGE : la FORME du hash de build ne reconnait plus un build CONNU.")
        print("  %s" % forme_refusee.replace("\n", "\n  "))
        return 1
    if args.fail_on_header_stamp and header_stamps:
        print("CLIQUET ROUGE : %d estampille(s) d'en-tete perimee(s) -- un lecteur lira ce document"
              % len(header_stamps))
        print("contre le mauvais binaire. Corriger, ou poser un bandeau de peremption explicite.")
        return 1
    if args.fail_on_header_stamp:
        print("CLIQUET VERT : aucune estampille d'en-tete perimee.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
