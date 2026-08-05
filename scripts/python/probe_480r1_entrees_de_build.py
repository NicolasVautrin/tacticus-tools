"""Probe #480-r1 / #480-r4 -- le depot doit etre AUTO-CONSTRUCTIBLE, et sa doc doit le DIRE JUSTE.

DEUX RESIDUS, UNE SEULE CLASSE DE FAUTE
---------------------------------------
`probe_365` a ferme la porte des ENTREES : un fichier versionne ne peut plus importer une cible
gitignoree, absente ou vide. Il repond, dit sa docstring, a « le depot est-il auto-constructible ? ».

Mesure du 2026-08-05 : il rendait **VERT** (209 fichiers, 881 imports) pendant que, sur un worktree
frais, `npm ci && npm run build:hooks` rendait **rc 1** --
`Unable to write bundle: ENOENT ... frida/dist/hooks.js`. La compilation reussissait ; c'est
l'ECRITURE qui echouait, parce que `frida/dist/` est gitignore et que git ne materialise jamais un
repertoire vide. Meme classe de faute, **autre porte** : #365 gardait les entrees, personne ne
gardait la SORTIE. C'est le vice que #365 s'etait lui-meme donne pour cible (« un cliquet qui verdit
pendant que le build casse est pire que pas de cliquet »), rouvert d'un cran plus bas.

Et une TROISIEME face, sur l'axe de la DOC : `frida/hooks/scratch/` est versionne depuis #365
(`774df416`, 2026-07-31) et **66 de ses modules sont dans le bundle**, mais quatre endroits le
qualifiaient encore de gitignore / jetable / « jamais une dependance de prod ». Une qualification
fausse fait mal calibrer le risque **dans les deux sens** : elle fait ecarter 142 erreurs `tsc` d'un
perimetre d'audit, et elle avait fait ecrire d'un repertoire d'entrees de build qu'il n'existait
« nulle part ailleurs ».

CE QUE LE PROBE FAIT -- trois etapes, critere DERIVE a chaque fois
------------------------------------------------------------------
  1. **SORTIE** -- pour chaque script de `frida/package.json` qui NOMME son fichier de sortie
     (`-o <chemin>` / `--outfile <chemin>`), le repertoire parent doit etre garanti present au
     checkout : soit le script le cree lui-meme, soit il contient un fichier VERSIONNE (git
     materialise alors le repertoire). Derive du `package.json`, donc mord sur tout script futur.
  2. **DOC** -- les repertoires qui contiennent une ENTREE DE BUILD sont derives de la fermeture des
     imports depuis `frida/hooks/main.ts` (jamais d'une liste de noms). Aucun d'eux ne doit etre
     qualifie par un terme d'EXCLUSION (`gitignore`, `jamais versionne`, `jetable`, « jamais une
     dependance ») dans un fichier versionne, **a moins que ce meme fichier n'affirme ailleurs**
     que le repertoire est versionne / entree de build -- c'est ce qui distingue le RECIT d'un
     incident passe (legitime) de la QUALIFICATION au present (fausse).
  3. **TEMOIN croise** (informatif) -- fermeture vs contenu reel de `frida/dist/hooks.js`. Tri-etat :
     le bundle est gitignore, donc son absence se dit `NON MESURE`, jamais `0`.

Chaque etape imprime son TEMOIN (« N visites »). Un zero sans temoin est indistinguable d'un
balayage qui n'a rien visite -- patron trouve huit fois le 2026-08-04.

Sortie ASCII stricte (console Windows cp1252).
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PKG = ROOT / "frida" / "package.json"
ENTRY = ROOT / "frida" / "hooks" / "main.ts"
BUNDLE = ROOT / "frida" / "dist" / "hooks.js"

# --- etape 1 : sortie nommee sur la ligne de commande -------------------------------------------
OUT_RE = re.compile(r"(?:-o|--outfile)[=\s]+(\S+)")
# Le script pourvoit lui-meme a son repertoire (mkdirSync / mkdir -p / md).
MKDIR_RE = re.compile(r"mkdirSync|mkdir\b")

# --- etape 2 : imports -----------------------------------------------------------------------
STATIC_RE = re.compile(r"""(?:^|[\s;}])(?:from|import)\s+['"](\.[^'"]+)['"]""", re.M)
DYN_RE = re.compile(r"""\bimport\s*\(\s*['"](\.[^'"]+)['"]\s*\)""")

# Termes qui DECLASSENT un repertoire (le disent hors du depot ou hors de la production).
EXCLUSION = (
    "gitignor", "jamais versionn", "non versionn", "pas versionn",
    "jetable", "jamais une dependance", "jamais une dépendance",
)
# Termes par lesquels une ligne REHABILITE le repertoire qu'elle nomme.
REHABILITATION = (
    "versionn", "n'est plus ignore", "n'est plus ignoré",
    "entree de build", "entrée de build", "bundl",
)
# La rehabilitation doit etre PROCHE de la mention fautive et porter sur LE MEME repertoire.
#
# ⚠ Deux defauts mesures sur la premiere version de cette etape, tous deux la rendant VERTE
#   pendant que les quatre fautes existaient :
#     1. chercher la rehabilitation dans le FICHIER ENTIER -- « versionn » apparait dans presque
#        toute case-doc (data/, hooks-legacy/...), donc la clause etait toujours vraie ;
#     2. chercher le chemin COMPLET -- la doc ecrit `hooks/scratch/`, jamais `frida/hooks/scratch`.
#   D'ou : fenetre bornee, et formes de chemin DERIVEES par suffixes.
FENETRE_REHAB = 12


def formes_chemin(d: str) -> list[str]:
    """Suffixes de `d` d'au moins DEUX segments.

    Un seul segment (`scratch`, `hooks`) matcherait « from scratch », « scratchpad », « les hooks » :
    le mot nu ne DESIGNE pas un repertoire. Deux segments suffisent a lever l'ambiguite tout en
    acceptant l'ecriture usuelle de la doc, qui omet le prefixe `frida/`.
    """
    seg = d.split("/")
    return ["/".join(seg[i:]) for i in range(len(seg) - 1)]


def compile_formes(formes: list[str]) -> re.Pattern:
    """Une SEULE regex par repertoire : sans ca, le balayage refait 14 passes par ligne
    (14 repertoires x 746 905 lignes) et depasse les deux minutes."""
    return re.compile("|".join(re.escape(f) + r"(?![\w-])(?!/\w)" for f in formes))


def mentionne(ligne_bas: str, rx: re.Pattern) -> bool:
    """La ligne designe-t-elle CE repertoire, et pas un voisin ?

    Deux frontieres, toutes deux mesurees necessaires (cf. `compile_formes`) :
      * `(?![\\w-])` -- sinon `hooks/scratch` matche `hooks/scratchpad` ;
      * `(?!/\\w)`   -- sinon `frida/hooks` matche `frida/hooks/scratch`, et CHAQUE faute
        remontait DEUX fois, attribuee en plus au mauvais repertoire.
    Effet de bord assume : une ligne qui ne cite qu'un FICHIER (`hooks/scratch/x.ts`) ne compte pas
    comme qualifiant le repertoire -- ce probe juge des repertoires.
    """
    return rx.search(ligne_bas) is not None


def rehabilite(ligne_bas: str) -> bool:
    """La ligne AFFIRME-t-elle que le repertoire est versionne / entree de build ?

    ⚠ On retire d'abord les motifs d'EXCLUSION, sinon « jamais versionnes » compte comme une
    rehabilitation (il contient « versionn ») et la faute la plus nette du corpus -- celle du
    `CLAUDE.md` -- se blanchit toute seule. Mesure : sans ce retrait, 3 des 4 fautes reelles
    passaient au vert.
    """
    reste = ligne_bas
    for e in EXCLUSION:
        reste = reste.replace(e, " ")
    return any(r in reste for r in REHABILITATION)


def _git(*args: str) -> list[str]:
    out = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True)
    return [l.strip() for l in out.stdout.splitlines() if l.strip()]


def resolve_import(src: Path, spec: str) -> Path | None:
    base = (src.parent / spec).resolve()
    cands = []
    if base.suffix == ".js":
        cands.append(base.with_suffix(".ts"))
    cands.append(base)
    if base.suffix not in (".ts", ".js"):
        cands += [base.with_suffix(".ts"), base / "index.ts"]
    for c in cands:
        if c.is_file():
            return c
    return None


def closure(entry: Path) -> set[Path]:
    seen: set[Path] = set()
    stack = [entry]
    while stack:
        f = stack.pop()
        if f in seen:
            continue
        seen.add(f)
        try:
            txt = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for spec in list(STATIC_RE.findall(txt)) + list(DYN_RE.findall(txt)):
            t = resolve_import(f, spec)
            if t is not None and t not in seen:
                stack.append(t)
    return seen


def rel(p: Path) -> str:
    return str(p.relative_to(ROOT)).replace("\\", "/")


def etape1_sortie(verbose: bool) -> tuple[int, list[str]]:
    """Chaque script qui NOMME sa sortie doit avoir un repertoire de sortie garanti."""
    fautes: list[str] = []
    if not PKG.is_file():
        print("[480] ETAPE 1 -- SORTIE : %s ABSENT -- NON MESURE" % rel(PKG))
        return 1, ["package.json absent"]

    scripts = json.loads(PKG.read_text(encoding="utf-8")).get("scripts", {})
    tracked = set(_git("ls-files"))
    visites = 0
    sans_sortie_nommee: list[str] = []

    for name, cmd in sorted(scripts.items()):
        outs = OUT_RE.findall(cmd)
        if not outs:
            sans_sortie_nommee.append(name)
            continue
        for o in outs:
            visites += 1
            outdir = (PKG.parent / o).resolve().parent
            d = rel(outdir)
            if outdir == PKG.parent:
                continue  # racine du paquet : existe par construction
            cree_par_le_script = bool(MKDIR_RE.search(cmd))
            materialise = any(t.startswith(d + "/") for t in tracked)
            if verbose:
                print("        %-14s -> %s  (cree=%s versionne=%s)"
                      % (name, d, cree_par_le_script, materialise))
            if not (cree_par_le_script or materialise):
                fautes.append("%s : sortie %s -- repertoire '%s' ni cree par le script ni "
                              "materialise par un fichier versionne" % (name, o, d))

    print("[480] ETAPE 1 -- SORTIE : %d scripts, %d sorties nommees visitees" % (len(scripts), visites))
    print("        scripts SANS sortie nommee (hors portee, l'outil pourvoit) : %d %s"
          % (len(sans_sortie_nommee), sorted(sans_sortie_nommee)))
    for f in fautes:
        print("  ROUGE  %s" % f)
    if fautes:
        print("  => un checkout frais ne peut pas ECRIRE le bundle : `git` ne materialise jamais")
        print("     un repertoire vide, et l'outil de build ne cree pas son repertoire de sortie.")
    return len(fautes), fautes


def etape2_doc(verbose: bool) -> tuple[int, list[str]]:
    """Aucun repertoire d'entrees de build ne doit etre qualifie 'hors depot' / 'jetable'."""
    if not ENTRY.is_file():
        print("[480] ETAPE 2 -- DOC : entree %s ABSENTE -- NON MESURE" % rel(ENTRY))
        return 1, ["entree absente"]

    atteints = closure(ENTRY)
    dirs = sorted({rel(p.parent) for p in atteints})
    docs = [ROOT / f for f in _git("ls-files", "*.md", "scripts/python/*.py")]

    rx_par_dir = {d: compile_formes([f.lower() for f in formes_chemin(d)]) for d in dirs}
    fautes: list[str] = []
    lignes_visitees = 0
    for doc in docs:
        try:
            txt = doc.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        lines = txt.splitlines()
        bas = [l.lower() for l in lines]
        txt_bas = txt.lower()
        lignes_visitees += len(lines)
        for d, rx in rx_par_dir.items():
            # Pre-filtre sur le document ENTIER : sans lui, chaque ligne est visitee une fois
            # par repertoire (14 x 746 923) et le cliquet passe la minute et demie.
            if not rx.search(txt_bas):
                continue
            for i, lb in enumerate(bas):
                if not mentionne(lb, rx):
                    continue
                hits = [e for e in EXCLUSION if e in lb]
                if not hits:
                    continue
                # Rehabilitation : une ligne PROCHE qui nomme LE MEME repertoire et l'assume.
                # La ligne COURANTE compte : « 69 fichiers VERSIONNES et BUNDLES, qualifies
                # "gitignore" » denonce la faute, elle ne la commet pas.
                lo, hi = max(0, i - FENETRE_REHAB), min(len(bas), i + FENETRE_REHAB + 1)
                rehab = any(mentionne(bas[j], rx) and rehabilite(bas[j])
                            for j in range(lo, hi))
                if not rehab:
                    fautes.append("%s:%d  '%s' qualifie %s  |  %s"
                                  % (rel(doc), i + 1, hits[0], d, lines[i].strip()[:110]))

    print("[480] ETAPE 2 -- DOC : %d fichiers atteignables depuis %s, dans %d repertoires"
          % (len(atteints), rel(ENTRY), len(dirs)))
    print("        documents versionnes balayes : %d  (%d lignes)" % (len(docs), lignes_visitees))
    if verbose:
        for d in dirs:
            print("        entree de build : %s" % d)
    for f in fautes:
        print("  ROUGE  %s" % f)
    if fautes:
        print("  => ce repertoire porte des ENTREES DE BUILD (atteignables depuis hooks/main.ts).")
        print("     Le dire gitignore / jetable fait mal calibrer le risque DANS LES DEUX SENS :")
        print("     ca ecarte son code d'un perimetre d'audit, et ca fait croire qu'il n'existe")
        print("     nulle part ailleurs. Corriger la qualification, ou -- si le fichier RACONTE")
        print("     un etat passe -- y ecrire aussi ce qu'il est aujourd'hui.")
    return len(fautes), fautes


def etape3_temoin() -> None:
    """Fermeture vs bundle reel. Tri-etat : le bundle est gitignore, son absence n'est pas un zero."""
    if not ENTRY.is_file():
        print("[480] ETAPE 3 -- TEMOIN : entree absente -- NON MESURE")
        return
    atteints = closure(ENTRY)
    if not BUNDLE.is_file():
        print("[480] ETAPE 3 -- TEMOIN : %d fichiers atteignables ; bundle %s ABSENT -- "
              "compare NON MESURE (lancer `npm run build:hooks`)" % (len(atteints), rel(BUNDLE)))
        return
    txt = BUNDLE.read_text(encoding="utf-8", errors="replace")
    marques = set(re.findall(r"//\s*((?:hooks|il2cpp)[\w/.-]*\.ts)", txt))
    print("[480] ETAPE 3 -- TEMOIN : %d fichiers atteignables depuis main.ts ; "
          "%d modules marques dans le bundle (%d o)"
          % (len(atteints), len(marques), BUNDLE.stat().st_size))
    print("        (l'ecart normal vient du tree-shaking esbuild : un module dont AUCUN symbole")
    print("         importe n'est appele ne sort pas dans le bundle.)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()

    n1, _ = etape1_sortie(a.verbose)
    print()
    n2, _ = etape2_doc(a.verbose)
    print()
    etape3_temoin()

    print()
    if n1 or n2:
        print("[480] ROUGE -- etape 1 : %d faute(s) ; etape 2 : %d faute(s)" % (n1, n2))
        return 1
    print("[480] OK -- la sortie du build est garantie, et aucune entree de build n'est")
    print("      qualifiee hors depot ou jetable.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
