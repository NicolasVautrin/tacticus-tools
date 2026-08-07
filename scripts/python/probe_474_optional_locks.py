"""Probe #474 -- un `git status` de LECTURE qui prend `.git/index.lock`.

LE FAIT, MESURE
---------------
`git status` prend `.git/index.lock` et l'y laisse **a 0 octet pendant ~toute sa duree**
(mesure sur depot jetable : lock vu 5/5, taille 0 sur tout l'echantillonnage ; 1,2 s sur
l'arbre reel d'apres `loop_status.mesurer_livraison`). Un process git TUE dans cette fenetre
ne nettoie rien -- `TerminateProcess` n'execute aucun `atexit` -- et laisse un lock que
**plus personne ne tient**. La commande suivante qui veut l'index meurt dessus :
`repo_refresh_and_write_index` echoue a prendre le lock et `builtin/merge.c` rend
`Unable to write index.`. C'est le gisement de #474 : 3 fusions/commits interrompus en 80 min.

Taux MESURE du residu, kill pendant la fenetre : **20/20** sur le binaire reel
(`mingw64/bin/git.exe`), **0/60** a **1,7 %** via le shim `cmd/git.exe` qui ne relaie pas le
signal. Le taux depend donc de QUI est atteint et de la largeur de la fenetre -- jamais nul.

CE QUE CE CLIQUET GARDE, ET POURQUOI CE CRITERE-LA
--------------------------------------------------
`--no-optional-locks` supprime la FENETRE au lieu de courir apres le residu, et c'est la
seule parade sure : nettoyer un `index.lock` parce qu'une commande a echoue corromprait le
depot le jour ou un git tourne VRAIMENT. Mesure : lock pris 0/5 avec l'option contre 5/5
sans, **sortie strictement IDENTIQUE**, et kill pendant la fenetre 0/15 contre 15/15.

Le perimetre est DERIVE (`git ls-files scripts`), sans allowlist. Les commandes visees sont
celles dont il est MESURE qu'elles prennent le lock -- `status` (3/3) et `describe --dirty`
(1/3) -- et AUCUNE autre : `diff`, `ls-files`, `stash list`, `rev-parse`, `worktree list`,
`for-each-ref`, `rev-list` ont toutes rendu 0/3. Elargir au-dela du mesure serait exactement
le vice que #474 combat (une parade posee sur un correlat non separe).

`git add`/`git commit` ne sont PAS vises : leur lock est une ECRITURE VOULUE, et
`--no-optional-locks` ne s'y applique pas.

Le perimetre s'arrete a `scripts/**`, et c'est une MESURE, pas une convention : sur les 286
fichiers executables versionnes HORS `scripts/` (`.py`, `.ps1`, `.ts`, `.js`, `.cjs`), **zero**
porte une invocation `git status`. Les outils qui pilotent la boucle -- et donc les seuls a
viser le `.git` PARTAGE depuis un contexte tuable -- vivent tous la. Un `git status` qui
apparaitrait demain dans `frida/host/*.ts` serait hors de portee de ce cliquet (residu
`#474-r3`) : l'elargir demanderait un parseur par langage, pour un gisement aujourd'hui vide.

DEUX ETAGES, PARCE QUE LE TEXTE NE SUFFIT PAS
----------------------------------------------
1. STATIQUE, sur le texte des fichiers versionnes de `scripts/**`. Python par AST (jamais par
   grep : ce depot porte ~25 mentions de `git status` en COMMENTAIRE, qu'un grep accuserait a
   tort) ; PowerShell par lignes de code, commentaires `#` et `<# #>` retires.
2. COMPORTEMENTAL, sur `loop_status.Sources.git` : l'option y est posee au FOYER, donc aucun
   site n'ecrit `status` a cote d'elle et l'etage 1 est structurellement aveugle a sa
   disparition. On MESURE le fait sur un depot jetable -- le lock ne doit pas apparaitre.

ASCII strict. N'ECRIT RIEN sous `scripts/python/` (#455) : tmpdir SYSTEME.
"""

from __future__ import annotations

import ast
import os
import re
import subprocess
import shutil
import sys
import tempfile
import threading
import time
from pathlib import Path

#: Ce qui doit changer pour que ce cliquet puisse changer d'avis.
DECLENCHEUR = {
    "chemins": ("scripts/*", "scripts/**"),
    "build": False,
    "toujours": False,
    "raison": "Etage 1 = AST (.py) et texte (.ps1/.psm1) de TOUT fichier versionne sous "
              "`scripts/`, perimetre DERIVE de `git ls-files scripts` ; etage 2 n'importe que "
              "`loop_status`, qui y vit aussi. Le depot jetable de l'etage 2 est fabrique "
              "ex nihilo, donc rien hors de `scripts/` n'entre dans le verdict.",
}

#: Les sous-commandes de LECTURE dont il est MESURE qu'elles prennent un lock optionnel.
#: `describe` n'en prend un que sous `--dirty` (c'est ce qui declenche le refresh d'index).
SOUS_COMMANDES = ("status", "describe")

OPTION = "--no-optional-locks"

#: Options GLOBALES de git qui consomment l'argument suivant. Sans elles, la valeur d'un `-C`
#: serait prise pour la sous-commande (ou, pire, la ferait sauter).
OPTIONS_A_VALEUR = ("-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path")

EX_NON_MESURE = 99


class MontageImpossible(RuntimeError):
    """Panne de ce dont le probe DEPEND et qui n'est PAS le depot (#471).

    Le critere : << un depot PARFAIT, a cet instant, sur cette machine, aurait-il produit ce
    meme echec ? >>. `git` injoignable -> OUI -> INDISPONIBLE. Un `git ls-files` a rc=0 et
    liste VIDE, lui, reste un ROUGE : c'est une reponse valide, donc un fait sur le depot.
    """


def racine() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def _git(args: list[str], quoi: str) -> subprocess.CompletedProcess:
    try:
        p = subprocess.run(["git", "-C", str(racine()), OPTION, *args],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
    except OSError as exc:
        raise MontageImpossible("`git %s` non lancable (%s) -- %s"
                                % (" ".join(args), type(exc).__name__, quoi)) from exc
    if p.returncode != 0:
        raise MontageImpossible("`git %s` rc=%d -- %s. stderr: %s"
                                % (" ".join(args), p.returncode, quoi,
                                   (p.stderr or "").strip()[:300]))
    return p


# ------------------------------------------------------------------ etage 1 : Python (AST)
def _fautes_python(texte: str, rel: str) -> list[str]:
    """Les argv git LITTERAUX qui nomment une sous-commande preneuse de lock sans l'option.

    Par AST, jamais par grep : seul un littera de LISTE dont l'element 0 vaut `git` est un
    argv. Un `git status` cite dans un commentaire ou une docstring n'est pas du code, et
    l'accuser rendrait le cliquet inutilisable dans CE depot (~25 mentions en prose).
    """
    try:
        arbre = ast.parse(texte)
    except SyntaxError as exc:
        return ["%s: source non parsable (%s)" % (rel, exc.msg)]
    fautes = []
    for n in ast.walk(arbre):
        if not isinstance(n, (ast.List, ast.Tuple)):
            continue
        # Les POSITIONS comptent : un element non constant (variable, f-string, `*args`) est un
        # TROU, pas un mot a supprimer. L'ecraser decalait tout -- mesure : sur
        # `["git", "-C", chemin, "status"]` le `-C` consommait `"status"` et l'argv passait
        # inapercu, c'est-a-dire EXACTEMENT la forme de `loop_status.Sources.git`.
        elems: list = [e.value if isinstance(e, ast.Constant) and isinstance(e.value, str)
                       else None for e in n.elts]
        if not elems or elems[0] is None:
            continue
        tete = elems[0]
        if not (tete == "git" or tete.endswith("git.exe") or tete.endswith("/git")):
            continue
        vise, i = None, 1
        while i < len(elems):
            m = elems[i]
            if m is None:
                # Indecidable : ce trou POURRAIT etre la sous-commande. On n'accuse pas.
                break
            if m in OPTIONS_A_VALEUR:
                i += 2                                  # l'option ET sa valeur, meme si trou
                continue
            if m.startswith("-"):
                i += 1
                continue
            vise = m
            break
        if vise not in SOUS_COMMANDES:
            continue
        mots = [m for m in elems if m is not None]
        if vise == "describe" and "--dirty" not in mots:
            continue
        if OPTION in mots:
            continue
        fautes.append("%s:%d  argv git `%s` sans %s"
                      % (rel, n.lineno, " ".join(mots[:6]), OPTION))
    return fautes


# -------------------------------------------------------------- etage 1 : PowerShell (texte)
_BLOC = re.compile(r"<#.*?#>", re.S)
#: `git` en position de COMMANDE : debut de ligne, ou apres `&`, `(`, `@(`, `|`, `;`, `=`.
_APPEL = re.compile(r"(?:^|[&(|;=]|@\()\s*git\s+(?P<queue>[^\r\n]*)")


def _fautes_powershell(texte: str, rel: str) -> list[str]:
    fautes = []
    sans_bloc = _BLOC.sub(lambda m: "\n" * m.group().count("\n"), texte)
    for i, ligne in enumerate(sans_bloc.splitlines(), start=1):
        code = ligne.split("#", 1)[0] if not ligne.lstrip().startswith("#") else ""
        if not code.strip():
            continue
        for m in _APPEL.finditer(code):
            queue = m.group("queue")
            # meme regle que l'AST : sauter les options et la VALEUR de celles qui en prennent
            mots, saute, vise = queue.split(), False, None
            for w in mots:
                if saute:
                    saute = False
                    continue
                if w in OPTIONS_A_VALEUR:
                    saute = True
                    continue
                if w.startswith("-"):
                    continue
                vise = w
                break
            if vise not in SOUS_COMMANDES:
                continue
            if vise == "describe" and "--dirty" not in mots:
                continue
            if OPTION in mots:
                continue
            fautes.append("%s:%d  `git %s` sans %s" % (rel, i, queue.strip()[:60], OPTION))
    return fautes


def etage_statique() -> tuple[int, int]:
    out = _git(["ls-files", "scripts"], "impossible d'enumerer le perimetre").stdout
    rels = [l.strip() for l in out.splitlines() if l.strip()]
    if not rels:
        # rc=0 + liste VIDE = reponse VALIDE de l'outil, donc un fait sur le depot -> ROUGE.
        print("[474] etape 1 : perimetre VIDE -- `git ls-files scripts` n'a rien rendu")
        return (1, 0)
    fautes, vus = [], 0
    for rel in rels:
        p = racine() / rel
        if not p.exists():
            continue
        if p.suffix == ".py":
            vus += 1
            fautes += _fautes_python(p.read_text(encoding="utf-8", errors="replace"), rel)
        elif p.suffix in (".ps1", ".psm1"):
            vus += 1
            fautes += _fautes_powershell(p.read_text(encoding="utf-8", errors="replace"), rel)
    print("[474] etape 1 STATIQUE : %d fichier(s) analyse(s) sur %d versionne(s) sous scripts/"
          % (vus, len(rels)))
    for f in fautes:
        print("  FAUTE %s" % f)
    if not fautes:
        print("  OK -- aucune invocation `git status` / `git describe --dirty` sans %s" % OPTION)
    return (len(fautes), vus)


# ------------------------------------------------------- etage 2 : le FOYER, par le COMPORTEMENT
def etage_comportement() -> int:
    """`loop_status.Sources.git("status", ...)` fait-il apparaitre `.git/index.lock` ?

    L'etage 1 ne peut PAS voir ce foyer : l'option y est posee a cote de `*args`, donc aucun
    littera n'y nomme `status`. On mesure le fait au lieu de le lire.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        import loop_status as LS
    except Exception as exc:                                    # pragma: no cover
        raise MontageImpossible("import de loop_status impossible : %r" % (exc,)) from exc

    base = Path(tempfile.mkdtemp(prefix="probe474-"))           # tmpdir SYSTEME (#455)
    try:
        depot = base / "depot"
        depot.mkdir()

        def g(*a):
            return subprocess.run(["git", *a], cwd=str(depot), capture_output=True, text=True,
                                  timeout=120)
        g("init", "-q", "-b", "master")
        g("config", "user.email", "p@p")
        g("config", "user.name", "p")
        for i in range(400):
            (depot / ("f%03d.txt" % i)).write_text("%d\n" % i, encoding="ascii")
        g("add", "-A")
        g("commit", "-qm", "base")
        # salir l'index : sans cela `status` n'a rien a reecrire et ne prend pas le lock
        (depot / "f000.txt").write_text("modifie\n", encoding="ascii")

        lock = depot / ".git" / "index.lock"
        vu = {"n": 0, "echant": 0}
        stop = threading.Event()

        def guetter():
            while not stop.is_set():
                vu["echant"] += 1
                if lock.exists():
                    vu["n"] += 1
                time.sleep(0.001)

        t = threading.Thread(target=guetter)
        t.start()
        try:
            src = LS.Sources(repo=depot, avec_gh=False, avec_host=False, timeout=60.0)
            rc, _ = src.git("status", "--porcelain=v2", "--branch")
        finally:
            stop.set()
            t.join()

        print("[474] etape 2 COMPORTEMENT : Sources.git('status') rc=%d, lock apercu %d fois "
              "sur %d echantillons" % (rc, vu["n"], vu["echant"]))
        if rc != 0:
            print("  FAUTE le foyer n'a pas su lire un depot jetable SAIN (rc=%d)" % rc)
            return 1
        if vu["echant"] < 5:
            # Le guetteur n'a pas eu le temps d'echantillonner : on n'a RIEN mesure.
            raise MontageImpossible("guetteur non ordonnance (%d echantillon(s))" % vu["echant"])
        if vu["n"]:
            print("  FAUTE `loop_status.Sources.git` PREND `.git/index.lock` -- l'option a "
                  "disparu du foyer (#474). Un git tue dans cette fenetre laisse un lock "
                  "orphelin dans l'ARBRE PRINCIPAL.")
            return 1
        print("  OK -- le lock n'apparait jamais")
        return 0
    finally:
        shutil.rmtree(base, ignore_errors=True)


def main() -> int:
    print("probe_474 -- aucun `git status` de lecture ne prend `.git/index.lock`")
    try:
        n1, _ = etage_statique()
        n2 = etage_comportement()
    except MontageImpossible as exc:
        print("[474] MONTAGE IMPOSSIBLE : %s" % exc)
        print("[474] rc=%d -- RIEN n'a ete mesure. Ce n'est PAS un verdict sur le depot."
              % EX_NON_MESURE)
        return EX_NON_MESURE
    total = n1 + n2
    if total:
        print("VERDICT: FAIL -- %d faute(s)" % total)
    else:
        print("VERDICT: PASS")
    return total


if __name__ == "__main__":
    sys.exit(main())
