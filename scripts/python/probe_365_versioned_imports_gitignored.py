"""Probe #365 -- un fichier VERSIONNE ne doit pas importer statiquement un chemin GITIGNORE.

LA FAUTE QUE CE CLIQUET REND VISIBLE (mesuree le 2026-07-31, CORRIGEE depuis)
-----------------------------------------------------------------------------
`frida/hooks/controller.ts` est SUIVI PAR GIT et importait **67** modules `./scratch/*.js` que
`.gitignore` excluait ALORS. Ces sondes sont VERSIONNEES depuis (meme commit que ce probe,
`774df416`) et vivent sous `frida/hooks/probes/` depuis #480-r6 ; l'etat decrit ici est celui
de la faute, pas celui du depot.
Trois consequences, toutes constatees le meme jour :

  1. **Le depot n'est pas auto-constructible.** Un clone frais ne compile pas : `frida-compile`
     rend 67 `TS-1 Cannot find module './scratch/*.js'`.
  2. **Aucun worktree d'agent ne compile** -- c'est la raison pour laquelle des agents ont invente
     des JUNCTIONS vers l'arbre principal pour builder.
  3. **Ces junctions ont detruit la cible.** Sous Windows, une suppression recursive forcee
     (`git worktree remove --force`) SUIT un point de reparse et vide le repertoire pointe. Les 67
     modules, gitignores et jamais versionnes, n'existaient nulle part ailleurs.

La junction n'etait donc pas la cause, c'etait le SYMPTOME. La cause est ici : une entree de build
d'un fichier versionne qui n'est pas versionnee. D'ou ce cliquet -- il rend la CLASSE de faute
visible, pas seulement cette instance.

CE QUE LE PROBE FAIT
--------------------
Pour chaque fichier `.ts` SUIVI PAR GIT sous `frida/`, il resout chaque import RELATIF
(`import ... from "./x.js"`, `import "./x.js"`, `export ... from "./x.js"`) vers un fichier du
disque -- en appliquant la convention ESM/TypeScript `.js` -> `.ts` -- puis demande a git si la
cible est ignoree.

  * cible GITIGNOREE  -> ROUGE (la faute de #365)
  * cible ABSENTE     -> ROUGE (le depot ne construit pas)
  * cible VIDE (0 o)  -> ROUGE (voir ci-dessous)
  * sinon             -> vert

⚠ POURQUOI LE CAS « 0 OCTET » EST TRAITE A PART. A la restauration des 67 modules, TROIS sont
revenus VIDES. Le probe, qui ne testait que l'existence, est passe AU VERT -- alors que
`frida-compile` echouait toujours : `File '.../dsl-node-probe.ts' is not a module` (un fichier
vide n'exporte rien, donc un import nomme ne resout pas). Un cliquet qui verdit pendant que le
build casse est pire que pas de cliquet : il transforme une panne en « rien a signaler ».
Le probe ne remplace PAS `frida-compile` -- il repond a « le depot est-il auto-constructible ? »,
pas a « le TypeScript compile-t-il ». Les deux se lancent.

`git check-ignore --stdin` fait le travail en UN appel : interroger git fichier par fichier sur
des centaines d'imports serait lent et masquerait les erreurs.

Sortie ASCII stricte (console Windows cp1252).
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# `from "..."` / `import "..."` / `export ... from "..."`, guillemets simples ou doubles, et
# uniquement les chemins RELATIFS (un import de paquet npm n'a rien a voir avec le depot).
IMPORT_RE = re.compile(r"""(?:from|import)\s*\(?\s*['"](\.[^'"]+)['"]""")


def tracked_ts_files() -> list[Path]:
    out = subprocess.run(["git", "ls-files", "frida/**/*.ts", "frida/*.ts"],
                         cwd=ROOT, capture_output=True, text=True, check=True)
    return [ROOT / line.strip() for line in out.stdout.splitlines() if line.strip()]


def resolve_import(src: Path, spec: str) -> Path | None:
    """Chemin sur disque vise par `spec` depuis `src`, ou None si aucune forme ne resout.

    La convention ESM du projet ecrit `./x.js` pour la source `./x.ts` : sans cette bascule, TOUS
    les imports paraitraient absents et le probe serait un generateur de faux positifs.
    """
    base = (src.parent / spec).resolve()
    cands = [base]
    if base.suffix == ".js":
        cands.insert(0, base.with_suffix(".ts"))
    else:
        cands += [base.with_suffix(".ts"), base / "index.ts"]
    for c in cands:
        if c.is_file():
            return c
    return cands[0]  # inexistant : on rend le candidat prefere pour le message


def gitignored(paths: list[Path]) -> set[Path]:
    """Sous-ensemble de `paths` que git IGNORE. Un seul appel, via --stdin."""
    if not paths:
        return set()
    rels = [str(p.relative_to(ROOT)).replace("\\", "/") for p in paths]
    proc = subprocess.run(["git", "check-ignore", "--stdin"], cwd=ROOT, input="\n".join(rels),
                          capture_output=True, text=True)
    # rc 0 = au moins un ignore ; rc 1 = aucun ; rc >= 128 = vraie erreur, qu'on ne masque pas.
    if proc.returncode >= 128:
        raise RuntimeError("git check-ignore a echoue : %s" % proc.stderr.strip())
    hit = {line.strip().replace("\\", "/") for line in proc.stdout.splitlines() if line.strip()}
    return {ROOT / h for h in hit}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--verbose", action="store_true", help="lister chaque import resolu")
    a = ap.parse_args()

    files = tracked_ts_files()
    edges: list[tuple[Path, str, Path]] = []
    for f in files:
        try:
            txt = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for spec in IMPORT_RE.findall(txt):
            edges.append((f, spec, resolve_import(f, spec)))

    targets = [t for (_, _, t) in edges]
    ignored = gitignored([t for t in targets if t.exists()])

    missing = [(s, spec, t) for (s, spec, t) in edges if not t.exists()]
    ignored_edges = [(s, spec, t) for (s, spec, t) in edges if t in ignored]
    # Une cible de 0 octet EXISTE mais n'est pas un module : `import { x } from ...` ne resout
    # rien. C'est l'etat dans lequel une restauration partielle laisse les fichiers.
    empty = [(s, spec, t) for (s, spec, t) in edges
             if t.exists() and t.stat().st_size == 0]

    print("[365] fichiers .ts suivis par git sous frida/ : %d" % len(files))
    print("[365] imports relatifs resolus                : %d" % len(edges))
    if a.verbose:
        for s, spec, t in edges:
            rel = str(t.relative_to(ROOT)).replace("\\", "/") if str(t).startswith(str(ROOT)) else str(t)
            print("        %s -> %s [%s]" % (s.name, spec, "OK" if t.exists() else "ABSENT"))

    def _grp(edges_):
        out: dict[str, list[str]] = {}
        for s, spec, _ in edges_:
            out.setdefault(str(s.relative_to(ROOT)).replace("\\", "/"), []).append(spec)
        return out

    rc = 0
    if ignored_edges:
        rc = 1
        print("\n[365] ROUGE -- import STATIQUE d'une cible GITIGNOREE (%d):" % len(ignored_edges))
        for src, specs in sorted(_grp(ignored_edges).items()):
            print("  %s  (%d imports)" % (src, len(specs)))
            for sp in sorted(specs)[:4]:
                print("      %s" % sp)
            if len(specs) > 4:
                print("      ... et %d autres" % (len(specs) - 4))
        print("  => versionner la cible, ou couper la dependance statique.")
        print("     Un fichier versionne qui importe du gitignore rend le depot non constructible")
        print("     (clone frais ET worktree d'agent), ce qui pousse a des contournements par")
        print("     junction -- et une junction supprimee en recursif VIDE la cible sous Windows.")

    if missing:
        rc = 1
        print("\n[365] ROUGE -- import STATIQUE d'une cible ABSENTE du disque (%d):"
              % len(missing))
        for src, specs in sorted(_grp(missing).items()):
            print("  %s  (%d imports)" % (src, len(specs)))
            for sp in sorted(specs)[:4]:
                print("      %s" % sp)
            if len(specs) > 4:
                print("      ... et %d autres" % (len(specs) - 4))

    if empty:
        rc = 1
        print("\n[365] ROUGE -- import STATIQUE d'une cible VIDE (0 octet, donc PAS un module) (%d):"
              % len(empty))
        for src, specs in sorted(_grp(empty).items()):
            print("  %s" % src)
            for sp in sorted(specs):
                print("      %s" % sp)
        print("  => restauration PARTIELLE. `frida-compile` rendra \"is not a module\".")

    if rc == 0:
        print("\n[365] OK -- aucun fichier versionne n'importe de cible gitignoree, absente ou vide.")
    return rc


if __name__ == "__main__":
    sys.exit(main())
