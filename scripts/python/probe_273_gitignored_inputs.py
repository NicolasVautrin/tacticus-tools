#!/usr/bin/env python
"""Probe #273 -- les ENTREES gitignorees lues depuis la racine du depot.

La question binaire, par consommateur : le script distingue-t-il « 0 trace parce
qu'il n'y en a pas » de « 0 trace parce que je regarde au mauvais endroit » ?

Etapes (toutes OFFLINE -- aucun RPC, aucune session Frida) :

  0. RE-DERIVE le balayage : tous les chemins construits depuis une racine
     derivee de `__file__` dans `scripts/python/**`, classes SORTIE (sous
     `logs/`) vs ENTREE, et confrontes a `git check-ignore`.
  0b. CHEMIN ABSOLU vers l'arbre principal (#314) : l'etape 0 ne voit QUE les
     chemins derives de `__file__`. Un litteral pointant la racine du depot par
     lettre de lecteur lui est INVISIBLE -- et c'est le motif qui perce
     l'isolation par worktree : le script tourne dans le worktree mais ECRIT
     dans l'arbre de l'orchestrateur. Cette etape le fait rougir.
  1. MECANISME : `Path(<inexistant>).glob(...)` rend [] SANS lever -- c'est
     exactement ce qui fait passer un capteur mort pour une mesure. Contre-
     epreuve : `host_inputs.find` LEVE sur le meme chemin.
  2. RESOLUTION effective dans CE checkout (arbre local ? arbre principal ?).
  3. TRI-ETAT : [] n'est rendu que quand le repertoire EXISTE, et l'override
     `TACTICUS_HOST_DATA_ROOT` est bien prioritaire.
  4. (option `--demo-worktree`) cree un worktree JETABLE a l'instant et y
     compare le comportement AVANT (glob nu) / APRES (host_inputs).

Usage :
    python probe_273_gitignored_inputs.py
    python probe_273_gitignored_inputs.py --demo-worktree
"""
from __future__ import annotations

import argparse
import ast
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import host_inputs  # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]


# ---- etape 0 : balayage des chemins construits depuis une racine ---------- #

def _root_vars(tree: ast.Module) -> set[str]:
    """Noms de variables (module-level) valant une racine derivee de `__file__`.

    Reconnait `Path(__file__).resolve().parents[N]`, `.parent.parent`,
    `os.path.dirname(os.path.abspath(__file__))` et les DERIVES d'une racine
    deja reconnue (`ROOT = PYDIR.parents[1]`).
    """
    roots: set[str] = set()
    for _ in range(3):                      # point fixe (derivations en chaine)
        for node in tree.body:
            if not isinstance(node, ast.Assign) or len(node.targets) != 1:
                continue
            tgt = node.targets[0]
            if not isinstance(tgt, ast.Name):
                continue
            src = ast.unparse(node.value)
            if "__file__" in src and ("parent" in src or "dirname" in src):
                roots.add(tgt.id)
            elif any(f"{r}." in src or src == r for r in roots):
                if "parent" in src or "dirname" in src:
                    roots.add(tgt.id)
    return roots


def _joined(node: ast.AST, roots: set[str]) -> tuple[str, list[str]] | None:
    """`<root> / "a" / "b"` -> ("<root>", ["a", "b"]). None si autre forme.

    La base peut etre une variable racine (`ROOT`) OU l'expression racine
    ECRITE EN LIGNE (`Path(__file__).resolve().parents[2] / "frida" / ...`) --
    c'est la forme d'`inspect_ai_trace.py`, qu'un balayage par nom de variable
    RATE en silence.
    """
    segs: list[str] = []
    cur = node
    while isinstance(cur, ast.BinOp) and isinstance(cur.op, ast.Div):
        r = cur.right
        if isinstance(r, ast.Constant) and isinstance(r.value, str):
            segs.append(r.value)
        else:
            segs.append("<dyn>")
        cur = cur.left
    if not segs:
        return None
    if isinstance(cur, ast.Name) and cur.id in roots:
        return cur.id, list(reversed(segs))
    src = ast.unparse(cur)
    if "__file__" in src and ("parent" in src or "dirname" in src):
        return "<inline>", list(reversed(segs))
    return None


def _scan_paths(scan_root: Path) -> list[tuple[Path, str, str]]:
    """[(fichier, var_racine, chemin_relatif)] pour tout `scripts/python/**`."""
    files = sorted((scan_root / "scripts" / "python").rglob("*.py"))
    trees: dict[Path, ast.Module] = {}
    local_roots: dict[Path, set[str]] = {}
    for f in files:
        try:
            trees[f] = ast.parse(f.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        local_roots[f] = _root_vars(trees[f])
    # Une racine IMPORTEE d'un module local en est une aussi (`from
    # rl_gen_ref_tables import ROOT`) -- sans ca, rl_gen_enum_columns.py sort
    # du balayage sans qu'on le sache.
    known = {n for s in local_roots.values() for n in s}
    out: list[tuple[Path, str, str]] = []
    for f, tree in trees.items():
        roots = set(local_roots.get(f) or ())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                roots |= {a.asname or a.name for a in node.names
                          if (a.asname or a.name) in known}
        for node in ast.walk(tree):
            j = _joined(node, roots)
            if j is None:
                continue
            var, segs = j
            # un chemin dont un segment est dynamique : on garde le prefixe
            # statique -- c'est lui qui porte la decision gitignore.
            if "<dyn>" in segs:
                segs = segs[:segs.index("<dyn>")]
            if not segs:
                continue
            out.append((f, var, "/".join(segs)))
    return out


def _check_ignored(rels: list[str], scan_root: Path) -> dict[str, bool]:
    """`git check-ignore -z --stdin` en un seul appel.

    `-z` des DEUX cotes : sans lui, git QUOTE les chemins en sortie ("a/b") et
    la console Windows y ajoute un CR -- le set ne matchait alors rien et le
    balayage annoncait « 0 gitignore », soit exactement le faux negatif que ce
    probe est cense mesurer.
    """
    if not rels:
        return {}
    r = subprocess.run(["git", "check-ignore", "-z", "--stdin"],
                       cwd=str(scan_root), input="\0".join(rels),
                       capture_output=True, text=True, timeout=60)
    ignored = {tok.replace("\\", "/")
               for tok in (r.stdout or "").split("\0") if tok}
    return {rel: (rel in ignored) for rel in rels}


# Chemins gitignores hors `logs/` qui restent construits depuis une racine
# `__file__`, et POURQUOI c'est admis. Toute AUTRE entree fait echouer l'etape 0
# -- c'est le cliquet : chaque nouveau `ROOT / <gitignore>` doit soit passer par
# `host_inputs`, soit venir s'expliquer ici.
_ALLOWED: dict[str, str] = {
    "frida/assets/public":
        "SORTIE de build_asset_manifest.py (mkdir + ecriture), pas une entree",
    "frida/assets/raw":
        "prefixe de RAW, repli documente -- l'acces reel passe par "
        "host_inputs dans _bundle_dir",
    "frida/assets/raw/Bundles":
        "constante RAW, repli du bundle d'installation ; _bundle_dir resout "
        "par host_inputs et les appelants impriment deja [warn] missing",
}


# Racines gitignorees qui sont des SORTIES du depot, jamais des entrees.
#   `logs/` : sorties de run (state-files, dumps de probe) -- meurt avec le
#             worktree ;
#   `app/`  : arbre Java GENERE par `gen_battle_config_java.py` /
#             `gen_loki_effects.py`. Il n'y est apparu (#314) qu'en devenant
#             RELATIF : tant que le chemin etait absolu, l'etape 0 ne le voyait
#             pas du tout.
_OUTPUT_ROOTS = {"logs", "app"}


def step0(scan_root: Path) -> int:
    print("== 0. balayage des chemins construits depuis une racine __file__ ==")
    print(f"  arbre balaye        : {scan_root.as_posix()}")
    found = _scan_paths(scan_root)
    rels = sorted({rel for (_, _, rel) in found})
    ign = _check_ignored(rels, scan_root)
    n_ign = sum(1 for r in rels if ign.get(r))
    outputs = [r for r in rels if ign.get(r) and r.split("/")[0] in _OUTPUT_ROOTS]
    inputs = [r for r in rels if ign.get(r) and r.split("/")[0] not in _OUTPUT_ROOTS]
    print(f"  occurrences         : {len(found)}")
    print(f"  chemins distincts   : {len(rels)}")
    print(f"  dont gitignores     : {n_ign}")
    print(f"    - SORTIES ({'/, '.join(sorted(_OUTPUT_ROOTS))}/) : {len(outputs)}"
          f"  [conforme, NE PAS toucher]")
    print(f"    - autres          : {len(inputs)}")
    rc = 0
    for rel in inputs:
        who = sorted({f.name for (f, _, r) in found if r == rel})
        why = _ALLOWED.get(rel)
        tag = "OK  " if why else "FAIL"
        print(f"      [{tag}] {rel:<30} <- {', '.join(who)}")
        if why:
            print(f"               ({why})")
        else:
            rc = 1
    if rc:
        print("  FAIL -- entree gitignoree lue depuis la racine sans passer par "
              "host_inputs : un glob y rendrait [] SANS lever (cf. etape 1)")
    return rc


# ---- etape 0b : chemin ABSOLU vers l'arbre principal (#314) --------------- #

# Toute forme de chemin absolu dont un segment vaut exactement `tacticus-tools`
# -- separateur antislash ou slash, simple ou double (chaine NON raw). Le
# separateur FINAL est optionnel : `ROOT = Path(r"<lecteur>:...tacticus-tools")`
# suivi de `ROOT / "logs"` perce l'isolation exactement pareil, et c'est la
# forme qu'un premier jet du balayage RATAIT (7 fichiers manques sur 22).
# Ancre sur une lettre de lecteur : sans elle, une mention de prose
# (`fleet_board.py` : "tacticus-tools . campagne de portage") remonterait.
_ABS_REPO = re.compile(
    r"[A-Za-z]:[\\/]{1,2}(?:[^\s\"'<>|]*?[\\/]{1,2})?tacticus-tools(?![-\w])")

# Chemins absolus vers le depot qui restent ADMIS, et POURQUOI. Cle =
# "<fichier>:<ligne>" ; toute AUTRE occurrence fait echouer l'etape 0b. Comme
# `_ALLOWED` de l'etape 0, c'est le point de passage oblige : reintroduire le
# motif oblige a venir s'expliquer ici.
_ALLOWED_ABS: dict[str, str] = {}


def _scan_abs_repo(scan_root: Path) -> list[tuple[Path, int, str]]:
    """[(fichier, no_ligne, extrait)] pour tout `scripts/python/**`.

    Balayage TEXTUEL, pas AST : le motif doit rougir aussi dans un commentaire
    ou une docstring -- un chemin absolu ecrit en prose est une invitation a le
    recopier, et l'etape 0 (AST) ne le verrait pas non plus.
    """
    out: list[tuple[Path, int, str]] = []
    for f in sorted((scan_root / "scripts" / "python").rglob("*.py")):
        try:
            lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for i, ln in enumerate(lines, 1):
            m = _ABS_REPO.search(ln)
            if m:
                out.append((f, i, ln.strip()[:100]))
    return out


def step0b(scan_root: Path) -> int:
    print("\n== 0b. chemin ABSOLU vers l'arbre principal (#314) ==")
    print(f"  arbre balaye        : {scan_root.as_posix()}")
    hits = _scan_abs_repo(scan_root)
    print(f"  occurrences         : {len(hits)}")
    rc = 0
    for f, lineno, snippet in hits:
        try:
            rel = f.relative_to(scan_root).as_posix()
        except ValueError:
            rel = f.as_posix()
        why = _ALLOWED_ABS.get(f"{rel}:{lineno}")
        tag = "OK  " if why else "FAIL"
        print(f"      [{tag}] {rel}:{lineno}")
        print(f"               {snippet}")
        if why:
            print(f"               ({why})")
        else:
            rc = 1
    if rc:
        print("  FAIL -- un script lance depuis un WORKTREE ecrirait (ou lirait) "
              "dans l'ARBRE PRINCIPAL. Sortie de run -> chemin RELATIF sous "
              "`logs/` (`Path(__file__).resolve().parents[2] / 'logs' / ...`) ; "
              "entree gitignoree -> `host_inputs.require()/find()`.")
    else:
        print("  OK -- aucun chemin absolu vers le depot")
    return rc


# ---- etape 1 : le mecanisme ---------------------------------------------- #

_ABSENT = "frida/data/_absent_273"          # n'existe dans AUCUN arbre


def step1() -> int:
    print("\n== 1. mecanisme : glob() sur un chemin inexistant ==")
    p = ROOT / _ABSENT
    print(f"  chemin              : {p.as_posix()}")
    print(f"  .exists()           : {p.exists()}")
    got = list(p.glob("*.jsonl"))
    print(f"  list(.glob(...))    : {got!r}   <- AUCUNE levee, resultat vide")
    assert got == [], "glob sur chemin inexistant devrait rendre []"
    try:
        host_inputs.find(_ABSENT, "*.jsonl")
        print("  host_inputs.find    : ECHEC -- n'a pas leve")
        return 1
    except host_inputs.HostInputUnavailable as e:
        first = str(e).splitlines()[0]
        print(f"  host_inputs.find    : LEVE -- {first}")
    return 0


# ---- etape 2 : resolution effective -------------------------------------- #

def step2() -> int:
    print("\n== 2. resolution dans CE checkout ==")
    for line in host_inputs.describe().splitlines():
        print("  " + line)
    try:
        files = host_inputs.find("frida/data/ai-traces", "*.jsonl")
        print(f"  ai-traces *.jsonl   : {len(files)} fichier(s) [MESURE]")
    except host_inputs.HostInputUnavailable:
        print("  ai-traces *.jsonl   : PAS MESURE (repertoire introuvable)")
    return 0


# ---- etape 3 : tri-etat + override --------------------------------------- #

def step3() -> int:
    print("\n== 3. tri-etat : [] seulement quand le repertoire EXISTE ==")
    rc = 0
    with tempfile.TemporaryDirectory() as td:
        fake = Path(td)
        (fake / "frida" / "data" / "ai-traces").mkdir(parents=True)
        os.environ["TACTICUS_HOST_DATA_ROOT"] = str(fake)
        try:
            res = host_inputs.resolve("frida/data/ai-traces")
            ok_env = res.origin == "env"
            print(f"  override env pris   : {ok_env} ({res.origin})")
            rc |= 0 if ok_env else 1
            got = host_inputs.find("frida/data/ai-traces", "*.jsonl")
            print(f"  repertoire VIDE     : {got!r}  <- MESURE et VIDE")
            rc |= 0 if got == [] else 1
            (fake / "frida" / "data" / "ai-traces" / "9-x.jsonl").write_text(
                "{}\n", encoding="utf-8")
            got = host_inputs.find("frida/data/ai-traces", "*.jsonl")
            print(f"  repertoire PLEIN    : {len(got)} fichier(s)")
            rc |= 0 if len(got) == 1 else 1
            # un rel absent SOUS l'override : les autres candidats existent-ils ?
            res2 = host_inputs.resolve(_ABSENT)
            print(f"  {_ABSENT} : "
                  f"{'INTROUVABLE (pas mesure)' if res2.path is None else res2.origin}")
            rc |= 0 if res2.path is None else 1
        finally:
            os.environ.pop("TACTICUS_HOST_DATA_ROOT", None)
    return rc


# ---- etape 4 : demonstration en worktree frais --------------------------- #

_DEMO = r'''
import sys
from pathlib import Path
root = Path(sys.argv[1])
sys.path.insert(0, str(root / "scripts" / "python"))
legacy = root / "frida" / "data" / "ai-traces"
print("  AVANT (glob nu depuis ROOT du worktree)")
print("    repertoire       : " + legacy.as_posix())
print("    .exists()        : " + str(legacy.exists()))
print("    glob('*.jsonl')  : " + repr(list(legacy.glob("*.jsonl"))))
try:
    import host_inputs
except ImportError:
    print("  APRES  : host_inputs ABSENT de ce checkout (branche AVANT)")
    raise SystemExit(0)
res = host_inputs.resolve("frida/data/ai-traces")
print("  APRES (host_inputs)")
print("    " + res.label())
try:
    n = len(host_inputs.find("frida/data/ai-traces", "*.jsonl"))
    print("    find('*.jsonl')  : " + str(n) + " fichier(s) [MESURE]")
except host_inputs.HostInputUnavailable as e:
    print("    find('*.jsonl')  : LEVE -- " + str(e).splitlines()[0])
'''


def step4(ref: str) -> int:
    print(f"\n== 4. worktree JETABLE cree a l'instant sur {ref} ==")
    base = Path(tempfile.gettempdir()) / f"wt273-{os.getpid()}-{abs(hash(ref)) % 9999}"
    add = subprocess.run(["git", "worktree", "add", "--detach", str(base), ref],
                         cwd=str(ROOT), capture_output=True, text=True, timeout=300)
    if add.returncode != 0:
        print("  echec git worktree add : " + (add.stderr or "").strip())
        return 1
    try:
        print(f"  worktree            : {base.as_posix()}")
        # `-I` (isolated) + cwd DANS le worktree : sans lui, le cwd de CE
        # process (`scripts/python` de l'arbre courant) reste en tete de
        # `sys.path` et le sous-process importe le `host_inputs` de l'arbre
        # APPELANT -- la demonstration « AVANT » serait alors truquee.
        r = subprocess.run([sys.executable, "-I", "-c", _DEMO, str(base)],
                           cwd=str(base), capture_output=True, text=True,
                           timeout=180)
        print((r.stdout or "").rstrip())
        if r.returncode != 0:
            print("  stderr : " + (r.stderr or "").strip()[:800])
    finally:
        subprocess.run(["git", "worktree", "remove", "--force", str(base)],
                       cwd=str(ROOT), capture_output=True, text=True, timeout=300)
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo-worktree", action="store_true",
                    help="cree un worktree jetable et y compare AVANT/APRES")
    ap.add_argument("--ref", default="HEAD",
                    help="ref checkoutee dans le worktree jetable")
    ap.add_argument("--scan-root", default=None,
                    help="arbre a balayer a l'etape 0 (defaut : celui-ci) -- "
                         "pointer un worktree sur origin/master donne l'AVANT")
    ap.add_argument("--only-scan", action="store_true",
                    help="etapes 0 + 0b seules (le cliquet, 100%% offline)")
    args = ap.parse_args(argv[1:])
    scan_root = Path(args.scan_root).resolve() if args.scan_root else ROOT
    if args.only_scan:
        return step0(scan_root) | step0b(scan_root)
    rc = step0(scan_root) | step0b(scan_root) | step1() | step2() | step3()
    if args.demo_worktree:
        rc |= step4(args.ref)
    print("\n[273] rc=" + str(rc))
    return rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
