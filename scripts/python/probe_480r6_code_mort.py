"""Probe #480-r6 -- ce qui est ECRIT dans `frida/` et que PERSONNE n'atteint.

LA QUESTION, ET POURQUOI ELLE SE POSE A TROIS ETAGES
-----------------------------------------------------
`#480-r1` a etabli que `frida/hooks/scratch/` n'est pas un brouillon : 73 fichiers versionnes,
66 dans le bundle injecte. La question suivante -- « combien de ce code est MORT ? » -- a ete
mesuree au niveau du FICHIER : 8 non atteignables sur 209, soit 3,8 %. Ce compte REFUTE
« beaucoup de fichiers morts », et il ne dit RIEN du code mort a l'INTERIEUR des fichiers
atteignables : un export jamais importe, un RPC declare et jamais appele.

Ce probe mesure les trois etages, chacun avec son propre critere et son propre temoin :

  1. FICHIER      -- fermeture des imports depuis les entrees DECLAREES (package.json,
                     tsconfig.include), pas depuis une liste de noms.
  2. EXPORT       -- pour chaque symbole exporte d'un fichier atteignable : un AUTRE fichier
                     TS/JS du depot le mentionne-t-il ?
  3. RPC          -- pour chaque `ctx.rpc.<nom> =` : le host, le front ou Python l'invoquent-ils ?

TROIS LANGAGES, ET C'EST LE POINT
----------------------------------
Un RPC n'est PAS appele depuis TypeScript la plupart du temps : il l'est depuis
`scripts/python/**` (`{"method": "<nom>"}`), depuis le front (`api.rpc(sid, "<nom>")`), ou par
une route du host (`rpcCall(sid, "<nom>")`). Un balayage qui ne regarde que le TypeScript
rendrait un faux « mort » pour l'essentiel du catalogue. Les trois sont donc croises, et
l'appartenance de chaque appelant est IMPRIMEE (`host` / `front` / `python` / `test` / `doc`).

⚠ Le compte LARGE (le nom apparait quelque part) et le compte STRICT (le nom apparait dans une
FORME D'APPEL RPC) sont rendus TOUS LES DEUX. `#480` a mesure pourquoi : `commit` matche 137 fois
cote Python, tous faux positifs. Le large ne peut pas conclure « vivant » ; le strict ne peut pas
conclure « mort ». Un RPC n'est declare MORT que si les DEUX rendent zero hors `frida/hooks/`.

CE QUE CE PROBE NE VOIT PAS -- imprime a chaque passe, jamais tu
----------------------------------------------------------------
  * un `require()` / `import()` a chaine CALCULEE (concatenation, variable) ;
  * un symbole atteint par REFLEXION (`obj[nom]` ou `nom` vient d'une donnee) ;
  * un RPC invoque a la main (curl, console du navigateur, message d'un agent) ;
  * ce qui est reellement EXPOSE PAR LA SESSION injectee -- residu `#480-r3` : rien ne le mesure,
    et un RPC ecrit mais non cable rend un `HTTP 500` indiscernable d'une erreur d'execution.

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
FRIDA = ROOT / "frida"

# --- entrees DECLAREES du build -----------------------------------------------------------------
# Derivees, jamais ecrites en dur : `-o`/`--outfile` nomme la SORTIE, l'argument qui precede
# nomme l'ENTREE ; `tsconfig.include` nomme les racines du typecheck.
ENTRY_RE = re.compile(r"(?:frida-compile|esbuild)\s+(\S+\.ts)")

STATIC_RE = re.compile(r"""(?:^|[\s;}])(?:from|import)\s+['"]([^'"]+)['"]""", re.M)
DYN_RE = re.compile(r"""\bimport\s*\(\s*['"]([^'"]+)['"]\s*\)""")
REQ_RE = re.compile(r"""\brequire\s*\(\s*['"]([^'"]+)['"]\s*\)""")
# Une chaine NON litterale dans un import/require : le scan ne peut pas la suivre, il la COMPTE.
DYN_CALC_RE = re.compile(r"""\b(?:import|require)\s*\(\s*(?!['"])""")

# --- etage 2 : exports --------------------------------------------------------------------------
EXPORT_DECL_RE = re.compile(
    r"^\s*export\s+(?:declare\s+)?(?:default\s+)?"
    r"(?:async\s+)?(function\*?|class|const|let|var|interface|type|enum|namespace)\s+"
    r"([A-Za-z_$][\w$]*)", re.M)
EXPORT_LIST_RE = re.compile(r"^\s*export\s*\{([^}]*)\}", re.M)
# Un `interface` / `type` EXPORTE ne pese RIEN a l'execution : il disparait a la transpilation.
# Le compter avec les `const`/`function` ferait lire « 157 fonctions mortes » la ou il n'y a
# souvent que du bruit de declaration -- la ventilation par NATURE est ce qui rend le chiffre
# exploitable.
NATURE_SANS_POIDS = {"interface", "type"}

# --- etage 3 : RPC ------------------------------------------------------------------------------
RPC_DECL_RE = re.compile(r"""(?:^|[^\w.])(?:ctx|c)?\.?rpc\.([A-Za-z_$][\w$]*)\s*=(?!=)""")
# `rpc.exports = rpcHandlers` (hooks/main.ts) est l'API FRIDA qui PUBLIE la table, pas une entree
# de cette table. Sans cette exclusion le probe s'accuse lui-meme d'un RPC mort qui n'existe pas.
RPC_NON_METHODE = {"exports"}

# Formes d'APPEL d'un RPC, toutes langues confondues. Le nom y est TOUJOURS un litteral :
#   host   : rpcCall(sid, "nom", [...])
#   front  : api.rpc(sessionId, "nom", [...])
#   python : {"method": "nom", ...}  /  rpc(sid, "nom", ...)
# On ne cherche donc pas un token nu (qui rend `commit` 137 fois), mais le litteral QUOTE.
#
# ⚠ L'INDEX est construit dans l'autre sens -- on extrait les noms PRESENTS dans le corpus, puis
#   on teste l'appartenance. Une regex par RPC x un corpus de 3 000 documents ne finit pas :
#   mesure, > 600 s. Le sens inverse est en O(corpus), soit quelques secondes.
QUOTE_ID_RE = re.compile(r"""['"]([A-Za-z_$][\w$]*)['"]""")
APPEL_RE = re.compile(
    r"""(?:rpcCall|\.rpc|\brpc)\s*\(\s*[^)\n]{0,80}?['"]([A-Za-z_$][\w$]*)['"]"""
    r"""|['"]method['"]\s*:\s*['"]([A-Za-z_$][\w$]*)['"]"""
    r"""|\bmethod\s*=\s*['"]([A-Za-z_$][\w$]*)['"]""")


def _git(*args: str) -> list[str]:
    out = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True)
    return [l.strip() for l in out.stdout.splitlines() if l.strip()]


def rel(p: Path) -> str:
    return str(p.relative_to(ROOT)).replace("\\", "/")


def resolve_import(src: Path, spec: str) -> Path | None:
    """Resout un specificateur RELATIF. Un paquet npm rend None (hors perimetre, et c'est dit)."""
    if not spec.startswith("."):
        return None
    base = (src.parent / spec).resolve()
    cands: list[Path] = []
    if base.suffix == ".js":
        cands.append(base.with_suffix(".ts"))
    cands.append(base)
    if base.suffix not in (".ts", ".js", ".cjs", ".json"):
        cands += [base.with_suffix(".ts"), base.with_suffix(".js"), base / "index.ts"]
    for c in cands:
        if c.is_file():
            return c
    return None


def closure(entries: list[Path]) -> tuple[set[Path], int, int]:
    """Fermeture des imports. Rend (fichiers, aretes, imports a chaine CALCULEE non suivis)."""
    seen: set[Path] = set()
    stack = list(entries)
    aretes = 0
    calcules = 0
    while stack:
        f = stack.pop()
        if f in seen:
            continue
        seen.add(f)
        try:
            txt = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        calcules += len(DYN_CALC_RE.findall(txt))
        for spec in (list(STATIC_RE.findall(txt)) + list(DYN_RE.findall(txt))
                     + list(REQ_RE.findall(txt))):
            t = resolve_import(f, spec)
            if t is not None:
                aretes += 1
                if t not in seen:
                    stack.append(t)
    return seen, aretes, calcules


def chemin_atteinte(entries: list[Path], cible: Path) -> list[Path] | None:
    """Plus court chemin d'imports entree -> cible.

    C'est le TEMOIN qui tranche une divergence entre deux scans : « atteignable » n'est pas
    une opinion, c'est une chaine d'aretes qu'on affiche. Sans lui, deux comptes qui different
    se departagent a l'autorite, pas a la mesure.
    """
    from collections import deque
    prev: dict[Path, Path | None] = {e: None for e in entries}
    q = deque(entries)
    while q:
        f = q.popleft()
        if f == cible:
            out = []
            cur: Path | None = f
            while cur is not None:
                out.append(cur)
                cur = prev[cur]
            return list(reversed(out))
        try:
            txt = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for spec in (list(STATIC_RE.findall(txt)) + list(DYN_RE.findall(txt))
                     + list(REQ_RE.findall(txt))):
            t = resolve_import(f, spec)
            if t is not None and t not in prev:
                prev[t] = f
                q.append(t)
    return None


def entrees_declarees() -> tuple[list[Path], list[str]]:
    """Entrees de build DERIVEES de `package.json` + racines des `tsconfig.include`."""
    ent: list[Path] = []
    notes: list[str] = []
    pkg = FRIDA / "package.json"
    if pkg.is_file():
        for name, cmd in sorted(json.loads(pkg.read_text(encoding="utf-8"))
                                .get("scripts", {}).items()):
            for e in ENTRY_RE.findall(cmd):
                p = (FRIDA / e).resolve()
                if p.is_file() and p not in ent:
                    ent.append(p)
                    notes.append("package.json:%s -> %s" % (name, rel(p)))
    # `tsc -p <cfg>` : l'entree n'est pas un fichier mais un `include`. Le point d'entree
    # EXECUTABLE du host est son `index.ts` ; c'est ce que `npm run dev` (tsx) lance.
    for cfg, idx in (("tsconfig.host.json", FRIDA / "host" / "index.ts"),):
        if (FRIDA / cfg).is_file() and idx.is_file() and idx not in ent:
            ent.append(idx)
            notes.append("%s (include host/**) -> entree executable %s" % (cfg, rel(idx)))
    return ent, notes


def etage1_fichiers(verbose: bool) -> tuple[set[Path], list[Path]]:
    ent, notes = entrees_declarees()
    print("[480r6] ETAGE 1 -- FICHIER : entrees DECLAREES (derivees, jamais une liste de noms)")
    for n in notes:
        print("        %s" % n)
    if not ent:
        print("  ROUGE  aucune entree derivee -- NON MESURE")
        return set(), []

    atteints, aretes, calcules = closure(ent)
    suivis = [ROOT / f for f in _git("ls-files", "frida")]
    src = [p for p in suivis
           if p.suffix in (".ts", ".js", ".cjs") and not p.name.endswith(".d.ts")]
    # Le front est du JS charge par le NAVIGATEUR (balises <script type=module>), pas par le
    # bundle ni par le host : il a sa propre racine et n'entre pas dans cette fermeture.
    front = [p for p in src if rel(p).startswith("frida/public/")]
    scope = [p for p in src if p not in front]
    morts = sorted(p for p in scope if p not in atteints)

    print("        %d fichiers suivis sous frida/, dont %d sources (.ts/.js/.cjs hors .d.ts)"
          % (len(suivis), len(src)))
    print("        perimetre de la fermeture : %d (les %d du front sont charges par le "
          "NAVIGATEUR, racine propre)" % (len(scope), len(front)))
    print("        atteints : %d  |  aretes resolues : %d  |  NON ATTEIGNABLES : %d"
          % (len([p for p in atteints if p in scope]), aretes, len(morts)))
    print("        imports a chaine CALCULEE rencontres (non suivis par ce scan) : %d" % calcules)
    for m in morts:
        print("  MORT?  %s" % rel(m))
    if verbose:
        for p in sorted(atteints):
            print("        atteint : %s" % rel(p))
    return atteints, morts


def exports_de(f: Path) -> dict[str, str]:
    """Rend {nom exporte -> nature}. La nature d'un re-export en liste est inconnue (`?`)."""
    try:
        txt = f.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    out: dict[str, str] = {n: k for k, n in EXPORT_DECL_RE.findall(txt)}
    for grp in EXPORT_LIST_RE.findall(txt):
        for item in grp.split(","):
            item = item.strip()
            if not item:
                continue
            # `export { a as b }` -> le nom EXPORTE est `b`.
            m = re.match(r"([A-Za-z_$][\w$]*)\s+as\s+([A-Za-z_$][\w$]*)", item)
            out.setdefault(m.group(2) if m else item.split()[0], "?")
    out.pop("default", None)
    return out


def etage2_exports(atteints: set[Path], verbose: bool) -> list[tuple[str, str]]:
    """Un export est MORT s'il n'est mentionne dans AUCUN autre fichier source du depot.

    Critere volontairement LARGE (token nu, tous fichiers TS/JS du depot, pas seulement
    `frida/`) : il ne peut produire aucun faux MORT -- une homonymie ne cree que des faux
    VIVANTS. C'est le bon sens du filtre quand la conclusion sert a SUPPRIMER du code.
    """
    fichiers = sorted(p for p in atteints if p.suffix in (".ts", ".js", ".cjs"))
    corpus: dict[Path, str] = {}
    for f in [ROOT / x for x in _git("ls-files", "*.ts", "*.js", "*.cjs", "*.mjs")]:
        if f.is_file():
            try:
                corpus[f] = f.read_text(encoding="utf-8", errors="replace")
            except OSError:
                pass

    morts: list[tuple[str, str]] = []
    par_nature: dict[str, int] = {}
    exportes_par_nature: dict[str, int] = {}
    sur_exportes: list[tuple[str, str]] = []      # utilise CHEZ LUI, l'export est superflu
    total = 0
    for f in fichiers:
        exps = exports_de(f)
        total += len(exps)
        try:
            propre = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            propre = ""
        for e, nature in sorted(exps.items()):
            exportes_par_nature[nature] = exportes_par_nature.get(nature, 0) + 1
            rx = re.compile(r"(?<![\w$])%s(?![\w$])" % re.escape(e))
            hits = [g for g, txt in corpus.items() if g != f and rx.search(txt)]
            if hits:
                if verbose:
                    print("        %s :: %s -> %d fichier(s)" % (rel(f), e, len(hits)))
                continue
            par_nature[nature] = par_nature.get(nature, 0) + 1
            # Usage LOCAL : plus d'une occurrence dans son propre fichier = declaration + usage.
            if len(rx.findall(propre)) > 1:
                sur_exportes.append((rel(f), "%s (%s)" % (e, nature)))
            else:
                morts.append((rel(f), "%s (%s)" % (e, nature)))

    poids = sum(v for k, v in par_nature.items() if k not in NATURE_SANS_POIDS)
    print("[480r6] ETAGE 2 -- EXPORT : %d fichiers atteignables, %d symboles exportes"
          % (len(fichiers), total))
    print("        corpus de recherche : %d fichiers .ts/.js/.cjs/.mjs VERSIONNES du depot entier"
          % len(corpus))
    print("        exportes par nature : %s"
          % ", ".join("%s=%d" % kv for kv in sorted(exportes_par_nature.items())))
    print("        NON mentionnes ailleurs : %d  (par nature : %s)"
          % (len(morts) + len(sur_exportes),
             ", ".join("%s=%d" % kv for kv in sorted(par_nature.items()))))
    print("        dont SANS POIDS a l'execution (interface/type, effaces a la transpilation) : %d"
          % (len(morts) + len(sur_exportes) - poids))
    print("        dont A POIDS (const/function/class/enum/var) : %d" % poids)
    print()
    print("        [A] SUR-EXPORTE -- utilise DANS SON PROPRE FICHIER, l'`export` est superflu : %d"
          % len(sur_exportes))
    for f, e in sur_exportes:
        print("    sur-export  %s :: %s" % (f, e))
    print()
    print("        [B] AUCUN USAGE, nulle part, meme pas chez lui : %d" % len(morts))
    for f, e in morts:
        print("  MORT?      %s :: %s" % (f, e))
    print("        NON VU par cet etage : la reflexion (`obj[nom]`), un nom construit par")
    print("        concatenation, et tout appelant hors du depot.")
    return morts


def etage3_rpc(atteints: set[Path], verbose: bool) -> list[str]:
    hooks = sorted(p for p in atteints if rel(p).startswith("frida/hooks/"))
    decl: dict[str, list[str]] = {}
    for f in hooks:
        try:
            txt = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for m in RPC_DECL_RE.findall(txt):
            if m in RPC_NON_METHODE:
                continue
            decl.setdefault(m, []).append(rel(f))

    # Corpus d'appelants, VENTILE par langage/role, et la ventilation est une PARTITION : les
    # tests vivent SOUS `scripts/python/tests`, donc les compter a part exige de les retirer de
    # `python`. Un groupe `tests/` a la racine rendait 0 fichier -- un corpus vide qui se lit
    # comme « aucun test n'appelle », alors qu'il ne regardait nulle part.
    py_tous = [f for f in _git("ls-files", "scripts/python") if f.endswith(".py")]
    py_tests = [f for f in py_tous if "/tests/" in f]
    autre_tous = [f for f in _git("ls-files", "scripts", "hooks-legacy", ".claude")
                  if f.endswith((".py", ".js", ".ts", ".ps1", ".cjs"))]
    groupes = {
        "host":   [f for f in _git("ls-files", "frida/host") if f.endswith((".ts", ".js"))],
        "front":  [f for f in _git("ls-files", "frida/public") if f.endswith(".js")],
        "python": [f for f in py_tous if f not in set(py_tests)],
        "test":   py_tests,
        "doc":    _git("ls-files", "*.md"),
        "autre":  [f for f in autre_tous if not f.startswith("scripts/python/")],
    }
    # Index INVERSE : par groupe, l'ensemble des identifiants apparaissant entre quotes (large)
    # et l'ensemble de ceux qui apparaissent dans une FORME D'APPEL RPC (strict).
    large_idx: dict[str, dict[str, set[str]]] = {}   # groupe -> nom -> {fichiers}
    strict_idx: dict[str, dict[str, set[str]]] = {}
    lus = {}
    for g, files in groupes.items():
        li: dict[str, set[str]] = {}
        si: dict[str, set[str]] = {}
        n = 0
        for rf in files:
            p = ROOT / rf
            if not p.is_file():
                continue
            try:
                t = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            n += 1
            for m in QUOTE_ID_RE.findall(t):
                li.setdefault(m, set()).add(rf)
            for tup in APPEL_RE.findall(t):
                for m in tup:
                    if m:
                        si.setdefault(m, set()).add(rf)
        large_idx[g], strict_idx[g], lus[g] = li, si, n

    exe = ("host", "front", "python", "test", "autre")
    sans_appelant: list[str] = []
    tableau: list[tuple[str, dict[str, int], dict[str, int]]] = []
    for nom in sorted(decl):
        large = {g: len(large_idx[g].get(nom, ())) for g in groupes}
        strict = {g: len(strict_idx[g].get(nom, ())) for g in groupes}
        if sum(large[g] for g in exe) == 0 and sum(strict[g] for g in exe) == 0:
            sans_appelant.append(nom)
        tableau.append((nom, large, strict))

    print("[480r6] ETAGE 3 -- RPC : %d noms declares (`ctx.rpc.<nom> =`) dans %d fichiers de hooks"
          % (len(decl), len(hooks)))
    for g, files in groupes.items():
        print("        corpus %-7s : %d fichiers versionnes, %d lus, %d identifiants quotes, "
              "%d en forme d'appel RPC"
              % (g, len(files), lus[g], len(large_idx[g]), len(strict_idx[g])))
    print("        RPC sans AUCUN appelant executable (large ET strict a zero) : %d"
          % len(sans_appelant))
    if verbose:
        for nom, large, strict in tableau:
            print("        %-38s large=%s strict=%s"
                  % (nom, {k: v for k, v in large.items() if v},
                     {k: v for k, v in strict.items() if v}))
    for nom in sans_appelant:
        print("  MORT?  rpc.%-34s declare dans %s" % (nom, ", ".join(sorted(set(decl[nom])))))
    print("        NON VU par cet etage : un appel a la main (curl, console du navigateur, un")
    print("        agent qui tape le nom), et ce que la SESSION expose vraiment (#480-r3).")
    return sans_appelant


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--etage", type=int, choices=(1, 2, 3), help="n'en jouer qu'un")
    ap.add_argument("--chemin", nargs="+", metavar="FICHIER",
                    help="afficher le chemin d'imports entree -> FICHIER (temoin d'atteignabilite)")
    a = ap.parse_args()

    if a.chemin:
        ent, _ = entrees_declarees()
        for c in a.chemin:
            cible = (ROOT / c).resolve()
            ch = chemin_atteinte(ent, cible)
            if ch is None:
                print("[480r6] %s : AUCUN chemin depuis les entrees declarees" % c)
            else:
                print("[480r6] %s : ATTEINT en %d arete(s)" % (c, len(ch) - 1))
                for i, p in enumerate(ch):
                    print("        %s%s" % ("  " * i, rel(p)))
        return 0

    atteints, morts_f = etage1_fichiers(a.verbose)
    print()
    if a.etage in (None, 2):
        etage2_exports(atteints, a.verbose)
        print()
    if a.etage in (None, 3):
        etage3_rpc(atteints, a.verbose)
        print()

    print("[480r6] Ce probe MESURE, il ne juge pas : un symbole liste `MORT?` est un CANDIDAT.")
    print("        Le trancher demande de lire le site -- une sonde one-shot gardee volontairement")
    print("        n'a pas d'appelant, et c'est sa nature, pas sa mort (#480 SS8).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
