"""#464-r1 -- un script frere invoque par CHEMIN RELATIF est resolu depuis le CWD.

CE QUE CE CLIQUET EST SEUL A VOIR
---------------------------------
Un appel de la forme

    subprocess.run([sys.executable, "rl_duel.py", "build", ...])      # sans cwd=

melange un chemin ABSOLU (`sys.executable`) et un chemin RELATIF (`"rl_duel.py"`), que
Python resout depuis le CWD. Hors de `scripts/python`, l'interpreteur enfant rend
`can't open file '<cwd>\\rl_duel.py'` (rc 2) et le frere n'est JAMAIS lance.

Aucun autre cliquet ne regarde cet axe. `probe_273` etape 0c garde les chemins `data/`
(destination d'une SORTIE), `probe_440` garde le PERIMETRE d'un balayage, `probe_365`
garde les imports d'une cible gitignoree : aucun ne lit l'argv d'un `subprocess`.

POURQUOI IL FAUT UN CLIQUET, ET PAS SEULEMENT LA CORRECTION
------------------------------------------------------------
Le gisement est du COPIER-COLLER : les 22 sites corriges par #464-r1 portaient le meme
littéral `"rl_duel.py"` dans 15 fichiers, chacun ne les fabrique. C'est donc, comme
`TARGETING_OPTIONS` ou `ABILITY_ATTACK_TYPE`, un gisement que NOTRE PROPRE CADENCE
alimente : le prochain probe live naitra du copier-coller d'un voisin. Corriger sans
cliqueter, c'est se preparer a re-corriger.

LA FORME SURE, celle que le depot doit copier :

    from sibling_script import sibling_script
    subprocess.run([sys.executable, sibling_script("rl_duel.py"), ...])

⚠ CE QU'IL NE FAUT PAS FAIRE -- ajouter `cwd=` : `rl_duel.py` ancre un `--state-file`
RELATIF sur la RACINE du depot, pas sur le CWD. Un `cwd=` different de celui de
l'appelant DECOUPLE l'ecriture du state-file de sa relecture. Le cliquet accepte
pourtant `cwd=` comme neutralisation : c'est la bonne reponse pour les 467 autres appels
du depot (git, pytest, outils tiers), et le piege ci-dessus est propre a `rl_duel`.

PERIMETRE : `git ls-files scripts/python` de CE checkout (#434 -- un cliquet ne balaie
que son propre arbre, jamais le worktree du voisin). N'ECRIT RIEN (#455).

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

#: Ancre sur `__file__`, jamais sur le CWD -- ce cliquet garde precisement ce vice, il
#: serait absurde qu'il le porte.
_PYDIR = Path(__file__).resolve().parent

#: Les fabriques de sous-processus dont le premier argument est un argv.
_SUBPROC_FN = {"run", "Popen", "check_output", "check_call", "call"}


def repo_root() -> Path:
    """Racine du checkout COURANT (le worktree, si on y tourne)."""
    return _PYDIR.parents[1]


def _const_str(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def fichiers() -> list[str]:
    """Tout `.py` SUIVI sous `scripts/python`, `tests/` compris.

    `tests/` en fait partie par construction : un test qui invoque un script frere a
    exactement le meme defaut, et pytest ne fixe pas le CWD (il fixe le rootdir)."""
    out = subprocess.run(["git", "ls-files", "scripts/python"], cwd=str(repo_root()),
                         capture_output=True, text=True, check=True)
    return sorted(l.strip() for l in out.stdout.splitlines()
                  if l.strip().endswith(".py"))


def _argv_litteral(call: ast.Call, listes: dict[str, ast.AST]) -> list[str | None] | None:
    """Les elements de l'argv, en suivant UNE indirection par variable.

    Suivre la variable n'est pas un raffinement : 4 des 15 fichiers trouves par #464-r1
    passaient leur argv par un `cmd = [...]` intermediaire, et c'est exactement ce que le
    recensement initial (litteral en place seulement) ne voyait pas -- il annoncait 13
    fichiers la ou il y en avait 15.
    """
    argv = call.args[0]
    if isinstance(argv, ast.Name) and argv.id in listes:
        argv = listes[argv.id]
    if isinstance(argv, ast.BinOp) and isinstance(argv.op, ast.Add):
        argv = argv.left
        if isinstance(argv, ast.Name) and argv.id in listes:
            argv = listes[argv.id]
    if not isinstance(argv, (ast.List, ast.Tuple)):
        return None
    return [_const_str(e) for e in argv.elts]


def sites(rel: str, src: str) -> list[tuple[int, list[str]]]:
    """(ligne, scripts relatifs) de chaque invocation fragile du fichier."""
    arbre = ast.parse(src)
    listes: dict[str, ast.AST] = {}
    for node in ast.walk(arbre):
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and isinstance(node.value, (ast.List, ast.Tuple))):
            listes[node.targets[0].id] = node.value

    trouves = []
    for node in ast.walk(arbre):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        f = node.func
        nom = f.attr if isinstance(f, ast.Attribute) else (
            f.id if isinstance(f, ast.Name) else "")
        if nom not in _SUBPROC_FN:
            continue
        # `cwd=` explicite neutralise ; `**kwargs` est indecidable -> on ne l'accuse pas.
        if any(kw.arg == "cwd" or kw.arg is None for kw in node.keywords):
            continue
        chaines = _argv_litteral(node, listes)
        if chaines is None:
            continue
        # `git <sous-commande>` : son axe est `-C`, garde ailleurs -- pas le sujet ici.
        if chaines and chaines[0] in ("git", "git.exe"):
            continue
        fragiles = [c for c in chaines
                    if c and c.endswith(".py") and "*" not in c
                    and not Path(c).is_absolute()]
        if fragiles:
            trouves.append((node.lineno, fragiles))
    return trouves


def main() -> int:
    racine = repo_root()
    print("[464] arbre balaye : %s" % racine.as_posix())
    cibles = fichiers()
    if not cibles:
        print("[464] FAIL -- `git ls-files scripts/python` ne rend RIEN : le verdict "
              "serait rendu contre un perimetre vide, donc faux dans les deux sens.")
        return 1

    mauvais: list[tuple[str, int, list[str]]] = []
    lus = 0
    for rel in cibles:
        try:
            src = (racine / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        lus += 1
        try:
            for ligne, scripts in sites(rel, src):
                mauvais.append((rel, ligne, scripts))
        except SyntaxError:
            continue

    print("[464] fichiers balayes : %d" % lus)
    if mauvais:
        print("[464] %d invocation(s) d'un script frere par chemin RELATIF, sans cwd= :"
              % len(mauvais))
        for rel, ligne, scripts in mauvais:
            print("        %s:%d  ->  %s" % (rel, ligne, ", ".join(scripts)))
        print("[464] La forme sure : sibling_script(\"<nom>.py\") "
              "(cf. scripts/python/sibling_script.py).")
        print("[464] VERDICT: FAIL")
        return 1

    print("[464] OK -- aucune invocation de script frere resolue depuis le CWD.")
    print("[464] VERDICT: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
