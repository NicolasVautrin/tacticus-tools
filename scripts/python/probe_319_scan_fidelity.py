#!/usr/bin/env python
"""Probe #319 -- le cliquet de #273 mesure-t-il ce qu'il pretend mesurer ?

`probe_273_gitignored_inputs.py --only-scan` est le garde-fou a passer avant
d'ouvrir une PR. Un garde-fou n'a de valeur que si son verdict est (a) FIDELE
-- il ne signale que des chemins reellement construits -- et (b) REPRODUCTIBLE
-- il rend le meme verdict dans un worktree et dans l'arbre principal. Les deux
proprietes etaient FAUSSES, et c'est ce probe qui les garde.

Ce qu'il verifie, toutes etapes OFFLINE (aucun RPC, aucune session Frida) :

  1. FIDELITE : un fragment de chemin ne doit pas etre pris pour une lecture.
     `ast.walk` visite les sous-expressions : sur
     `ROOT / "frida" / "assets" / "raw" / "Bundles"` il rendait AUSSI
     `frida/assets`, signale FAIL comme une entree lue par
     `build_asset_manifest.py` -- qui ne le nomme nulle part.
  2. COUVERTURE : eliminer les fragments ne doit RIEN perdre. Tout chemin de
     l'ancien balayage doit rester couvert par un chemin maximal qui le
     prefixe (0 orphelin).
  3. DETERMINISME : le verdict ne doit pas dependre de l'existence des
     repertoires sur le disque. Une regle `.gitignore` a slash final est
     DIRECTORY-ONLY : git ne l'applique que s'il voit un repertoire. D'ou le
     desaccord mesure -- rouge dans l'arbre principal (ou `frida/assets/`
     existe), vert dans un worktree frais. Le cliquet virait au vert
     precisement la ou travaillent les agents.
  4. MUTATIONS : le cliquet rougit-il encore pour de vraies regressions ?
     Un garde-fou qu'on assouplit doit prouver qu'il mord toujours.

Usage :
    python probe_319_scan_fidelity.py
"""
from __future__ import annotations

import ast
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
sys.path.insert(0, str(PYDIR))
import probe_273_gitignored_inputs as P  # noqa: E402

PROBE_273 = PYDIR / "probe_273_gitignored_inputs.py"

# Arbre minimal suffisant pour exercer le cliquet : le probe lui-meme, son
# helper, et le consommateur qui porte les deux exceptions `_ALLOWED`. Copier
# tout `scripts/python/**` (1145 fichiers) rendait le probe trop lent pour
# etre joue avant chaque PR -- donc jamais joue.
_MINIMAL = ("probe_273_gitignored_inputs.py", "host_inputs.py",
            "build_asset_manifest.py")


# ---- etape 1+2 : fidelite et couverture du balayage ---------------------- #

def _scan_with_fragments(scan_root: Path) -> list[str]:
    """L'ANCIEN balayage : `ast.walk` sans filtrage des sous-expressions."""
    out: list[str] = []
    files = sorted((scan_root / "scripts" / "python").rglob("*.py"))
    trees, local_roots = {}, {}
    for f in files:
        try:
            trees[f] = ast.parse(f.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        local_roots[f] = P._root_vars(trees[f])
    known = {n for s in local_roots.values() for n in s}
    for f, tree in trees.items():
        roots = set(local_roots.get(f) or ())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                roots |= {a.asname or a.name for a in node.names
                          if (a.asname or a.name) in known}
        for node in ast.walk(tree):
            j = P._joined(node, roots)
            if j is None:
                continue
            _, segs = j
            if "<dyn>" in segs:
                segs = segs[:segs.index("<dyn>")]
            if segs:
                out.append("/".join(segs))
    return out


def step_fidelity() -> int:
    print("== 1+2. fidelite et couverture du balayage ==")
    old = sorted(set(_scan_with_fragments(ROOT)))
    new = sorted({rel for (_, _, rel) in P._scan_paths(ROOT)})
    dropped = sorted(set(old) - set(new))
    added = sorted(set(new) - set(old))
    print(f"  chemins distincts   : {len(old)} (avec fragments) -> {len(new)}")
    print(f"  fragments elimines  : {len(dropped)}")
    rc = 0
    if added:
        print(f"  FAIL -- le balayage AJOUTE des chemins : {added}")
        rc = 1
    # Couverture : chaque fragment doit rester couvert par un chemin maximal.
    orphans = [r for r in dropped
               if not any(m == r or m.startswith(r + "/") for m in new)]
    print(f"  orphelins           : {len(orphans)}  (perte reelle de couverture)")
    if orphans:
        for r in orphans:
            print(f"      [FAIL] {r} -- plus aucun chemin maximal ne le couvre")
        rc = 1
    # Le cas qui a motive #319, nommement.
    for frag in ("frida/assets", "frida/assets/raw"):
        if frag in new:
            print(f"      [FAIL] {frag} est un FRAGMENT, il ne doit plus etre "
                  f"compte comme un chemin construit")
            rc = 1
    if rc == 0:
        print("  OK -- aucun fragment compte, aucune couverture perdue")
    return rc


# ---- etape 3 : determinisme vis-a-vis du disque -------------------------- #

def _fresh_tree() -> Path:
    base = Path(tempfile.mkdtemp(prefix="probe319-"))
    subprocess.run(["git", "init", "-q", str(base)],
                   capture_output=True, text=True, timeout=120, check=True)
    shutil.copy(ROOT / ".gitignore", base / ".gitignore")
    dst = base / "scripts" / "python"
    dst.mkdir(parents=True)
    for name in _MINIMAL:
        shutil.copy(PYDIR / name, dst / name)
    return base


def _run_scan(scan_root: Path) -> tuple[int, str]:
    """Joue le probe_273 DE L'ARBRE TEMPORAIRE, pas celui du checkout.

    Piege mesure : lancer `PROBE_273` du checkout avec `--scan-root <tmp>`
    laisse `_ALLOWED` inchangee -- la mutation « exception morte » n'avait
    alors aucun effet et le test la declarait VERTE. Le rouge accusait le
    montage, pas le cliquet. On execute donc la COPIE, seule a porter la
    mutation.
    """
    probe = scan_root / "scripts" / "python" / "probe_273_gitignored_inputs.py"
    r = subprocess.run([sys.executable, str(probe), "--only-scan",
                        "--scan-root", str(scan_root)],
                       capture_output=True, text=True, timeout=300,
                       cwd=str(scan_root / "scripts" / "python"))
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def step_determinism() -> int:
    print("\n== 3. determinisme : le verdict depend-il du DISQUE ? ==")
    tree = _fresh_tree()
    try:
        rc_absent, out_absent = _run_scan(tree)
        # Reproduit l'arbre principal : les repertoires gitignores EXISTENT.
        for rel in ("frida/assets/raw/Bundles", "frida/assets/public", "app"):
            (tree / rel).mkdir(parents=True, exist_ok=True)
        rc_present, out_present = _run_scan(tree)
        print(f"  repertoires ABSENTS : rc={rc_absent}")
        print(f"  repertoires PRESENTS: rc={rc_present}")
        same = _body(out_absent) == _body(out_present)
        print(f"  sorties identiques  : {same}")
        if not same or rc_absent != rc_present:
            print("  FAIL -- le verdict depend de l'etat du disque : le cliquet "
                  "vire au vert dans un worktree et au rouge dans l'arbre "
                  "principal (ou l'inverse). Un « probe_273 : OK » rapporte de "
                  "bonne foi ne voudrait alors rien dire.")
            for a, b in zip(_body(out_absent).splitlines(),
                            _body(out_present).splitlines()):
                if a != b:
                    print(f"      absent : {a}")
                    print(f"      present: {b}")
            return 1
        print("  OK -- meme verdict avec et sans les repertoires")
        return 0
    finally:
        shutil.rmtree(tree, ignore_errors=True)


def _body(out: str) -> str:
    """Sortie sans la ligne « arbre balaye » (chemin du tmpdir, non pertinent)."""
    return "\n".join(ln for ln in out.splitlines() if "arbre balaye" not in ln)


# ---- etape 4 : mutations -- le cliquet mord-il toujours ? ----------------- #

def _mut_new_input(tree: Path) -> None:
    (tree / "scripts" / "python" / "zz_new_reader.py").write_text(
        "from pathlib import Path\n"
        "ROOT = Path(__file__).resolve().parents[2]\n"
        "TRACES = ROOT / 'frida' / 'data' / 'ai-traces'\n"
        "print(list(TRACES.glob('*.jsonl')))\n", encoding="utf-8")


def _mut_new_input_dyn(tree: Path) -> None:
    (tree / "scripts" / "python" / "zz_new_reader_dyn.py").write_text(
        "from pathlib import Path\n"
        "ROOT = Path(__file__).resolve().parents[2]\n"
        "def get(name):\n"
        "    return ROOT / 'frida' / 'data' / 'rl-batches' / name\n",
        encoding="utf-8")


def _mut_dead_allowlist(tree: Path) -> None:
    p = tree / "scripts" / "python" / "probe_273_gitignored_inputs.py"
    s = p.read_text(encoding="utf-8")
    p.write_text(s.replace(
        "_ALLOWED: dict[str, str] = {",
        '_ALLOWED: dict[str, str] = {\n    "frida/zz_obsolete": "raison perimee",'),
        encoding="utf-8")


# Nom du depot SCINDE. Ce fichier doit ecrire un vrai chemin absolu dans sa
# fixture sans que l'etape 0b s'attrape sur CE fichier-ci : son balayage est
# TEXTUEL et ligne a ligne, donc un litteral entier rougirait ici. La parade
# est la concatenation, pas une entree dans `_ALLOWED_ABS` -- une exception
# posee pour faire taire son propre cliquet est le premier pas vers une
# allowlist qui ne se relit plus.
_REPO = "tacticus" "-tools"


def _mut_abs_path(tree: Path) -> None:
    (tree / "scripts" / "python" / "zz_abs.py").write_text(
        "from pathlib import Path\n"
        "OUT = Path(r'C:\\Users\\nicolasv\\" + _REPO + "') / 'logs' / 'x.json'\n",
        encoding="utf-8")


def _mut_fragment_only(tree: Path) -> None:
    """Le faux positif de #319 : un fragment gitignore, jamais construit."""
    (tree / "scripts" / "python" / "zz_frag.py").write_text(
        "from pathlib import Path\n"
        "ROOT = Path(__file__).resolve().parents[2]\n"
        "RAW = ROOT / 'frida' / 'assets' / 'raw' / 'Bundles'\n", encoding="utf-8")


def _mut_none(tree: Path) -> None:
    pass


_CASES = [
    ("entree gitignoree lue depuis ROOT", _mut_new_input, True,
     "frida/data/ai-traces"),
    ("entree gitignoree, segment final dynamique", _mut_new_input_dyn, True,
     "frida/data/rl-batches"),
    ("exception _ALLOWED devenue morte", _mut_dead_allowlist, True,
     "[MORTE] frida/zz_obsolete"),
    ("chemin absolu vers l'arbre principal (0b)", _mut_abs_path, True,
     "zz_abs.py"),
    ("arbre non mute", _mut_none, False, None),
    ("fragment de chemin (faux positif #319)", _mut_fragment_only, False, None),
]


def step_mutations() -> int:
    print("\n== 4. mutations : le cliquet rougit-il encore ? ==")
    rc = 0
    for label, mutate, expect_fail, needle in _CASES:
        tree = _fresh_tree()
        try:
            mutate(tree)
            got, out = _run_scan(tree)
            ok = ((got != 0) == expect_fail) and (needle is None or needle in out)
            attendu = "ROUGE" if expect_fail else "VERT "
            print(f"      [{'OK  ' if ok else 'FAIL'}] attendu {attendu} : "
                  f"{label} (rc={got})")
            if not ok:
                rc = 1
                print("        " + out.replace("\n", "\n        ")[:1200])
        finally:
            shutil.rmtree(tree, ignore_errors=True)
    return rc


def main() -> int:
    rc = step_fidelity() | step_determinism() | step_mutations()
    print("\n[319] rc=" + str(rc))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
