"""#486-r12 -- MESURER ce qu'un cliquet LIT vraiment, pour ne pas croire sa parole.

POURQUOI UNE MESURE, ET PAS UNE RELECTURE DU SOURCE
----------------------------------------------------
Un `DECLENCHEUR` (cf. `declencheur_cliquet.py`) est une DECLARATION. La confronter au source du
cliquet ne prouverait rien de plus que ce que le declarant a bien voulu voir : un `read_text`
cache derriere un helper, un `import` qui traine un paquet entier, une table lue par un module
tiers -- tout cela est invisible a l'oeil et decisif pour le verdict.

Ce depot a deja le precedent exact : `probe_457._FilesPerTest` pose un audit hook sur `open` et
enregistre, POUR CHAQUE FICHIER DE TEST, les fichiers du depot qu'il ouvre REELLEMENT. On
reprend l'idee au niveau du CLIQUET.

CE QUE LA MESURE VOIT, ET CE QU'ELLE NE VOIT PAS -- DIT, JAMAIS TU
-------------------------------------------------------------------
  * VU : tout `open` en LECTURE d'un fichier sous la racine du depot, dans le process du
    cliquet ET dans tous ses sous-process PYTHON (le hook se propage par `sitecustomize`).
  * PAS VU : ce que lit un sous-process NON-python -- `git ls-files`, `git check-ignore`,
    `pwsh`. Ces programmes lisent l'index, `.gitignore`, parfois des blobs. Ils sont donc
    COMPTES et NOMMES (`P\t<programme>`), et le cliquet qui en lance est marque
    `MESURE INCOMPLETE` : sa confrontation garde son sens dans UN SEUL sens (ce qui est vu
    doit etre couvert), jamais dans l'autre.
  * PAS VU NON PLUS : un fichier dont l'EXISTENCE seule decide (`Path.exists`, `iterdir`), et
    un fichier lu par `os.stat`. C'est pourquoi un declencheur se prend LARGE : la mesure
    borne par le BAS ce qu'il faut couvrir, elle ne dit pas que c'est suffisant.

LE `__pycache__` EST RAMENE A SA SOURCE
-----------------------------------------
`import engine.x` ouvre `engine/__pycache__/x.cpython-313.pyc` quand le bytecode est a jour, et
`engine/x.py` sinon. Sans normalisation, la meme mesure rendrait deux perimetres DIFFERENTS
selon l'etat du cache de la machine -- exactement le vice que `probe_457` a paye (#464-r2). On
ecrit donc toujours la SOURCE.

Sortie ASCII stricte (console Windows cp1252).
"""
from __future__ import annotations

import atexit
import os
import re
import sys
from pathlib import Path

#: Le dossier ou chaque process depose sa trace. Pose par le mesureur, lu par `installer`.
ENV_TRACE = "TACTICUS_DECLENCHEUR_TRACE"

#: Ce qu'on ne compte JAMAIS comme une entree : nos propres sorties et la plomberie git.
_EXCLUS = ("logs/", ".git/", "scripts/python/logs/", "frida/dist/", "node_modules/")

#: LES MEMES, mais reconnus A N'IMPORTE QUEL NIVEAU -- `_EXCLUS` teste un PREFIXE, donc il ne
#: voit ni `frida/node_modules/` ni un cache pose ailleurs qu'a la racine.
#:
#: ⚠ MESURE DU 2026-08-10, ET C'EST UN ECART DE REPRODUCTIBILITE, PAS UN DETAIL (#486-r36). Deux
#: passes du MEME arbre ont diverge sur une seule chose : `probe_283:on` et `probe_283:prose`
#: portaient le groupe `scripts/python/.pytest_cache/*.md` dans l'une et pas dans l'autre. Ce
#: fichier est ECRIT PAR PYTEST et GITIGNORE (par le `.gitignore` que pytest depose lui-meme) :
#: il n'existe que si quelqu'un a joue une passe dans ce repertoire. Une empreinte VERSIONNEE
#: qui en depend varie d'une machine a l'autre -- et si le declencheur ne couvrait pas `.md`,
#: elle produirait un FAUX ROUGE que personne ne pourrait reproduire. C'est exactement le vice
#: que `source_de` corrige deja pour `__pycache__` (#464-r2), sur un autre repertoire de cache.
#:
#: ⚠ `__pycache__` N'Y EST PAS, ET NE DOIT PAS Y ETRE : il est RAMENE A SA SOURCE par
#: `source_de`, donc l'exclure ferait disparaitre du perimetre tout module importe -- c'est-a-dire
#: precisement ce que la fermeture d'imports doit voir.
_SEGMENTS_EXCLUS = frozenset({".pytest_cache", "node_modules", ".git"})

#: `mod` est NON GREEDY et le suffixe accepte des POINTS : le nom d'un bytecode optimise est
#: `mod.cpython-311.opt-1.pyc`, donc un suffixe sans point (`[^./]+`) ne le reconnaissait pas --
#: et le fichier serait alors compte comme une entree `.pyc` que nul glob ne couvre.
_RX_PYC = re.compile(r"^(?P<base>.*/)?__pycache__/(?P<mod>[^/.]+)\.[^/]+\.pyc$")

_ETAT = None


def source_de(rel: str) -> str:
    """`a/b/__pycache__/x.cpython-313.pyc` -> `a/b/x.py`. Inchange sinon."""
    m = _RX_PYC.match(rel)
    if not m:
        return rel
    return (m.group("base") or "") + m.group("mod") + ".py"


def programme_de(args) -> str:
    """Le nom du programme lance, depuis `sys.audit("subprocess.Popen", exe, args, cwd, env)`.

    ⚠ SOUS WINDOWS, `exe` VAUT `None` ET `args` EST UNE LIGNE DE COMMANDE, pas une liste.
    Mesure : `subprocess.run(["git", "--version"])` emet `(None, 'git --version', None, None)`.
    Ne lire que `exe` rendait donc `programmes` VIDE -- et un cliquet qui lance `git` passait
    pour integralement mesure, ce qui est exactement le faux VERT que le tri-etat existe pour
    interdire. Trouve parce que la premiere mesure des 11 cliquets a rendu ZERO sous-process
    opaque alors que quatre d'entre eux lancent `git ls-files`.
    """
    exe, ligne = (list(args) + [None, None])[:2]
    val = exe or ligne
    if isinstance(val, (list, tuple)) and val:
        val = val[0]
    txt = str(val or "").strip()
    if txt.startswith('"'):
        txt = txt[1:].split('"', 1)[0]
    else:
        txt = txt.split(" ", 1)[0]
    return Path(txt).name.lower() or "<illisible>"


class _Trace:
    """Audit hook + vidage a la mort du process. Un fichier par PID : deux process qui
    ecriraient la meme ligne au meme instant se corrompraient, et la fusion est triviale."""

    def __init__(self, racine: str, dossier: str) -> None:
        self.racine = str(racine).replace("\\", "/").rstrip("/") + "/"
        self._prefixe = self.racine.lower()
        self._n = len(self.racine)
        self.dossier = Path(dossier)
        self.lectures: set = set()
        self.programmes: set = set()
        self._ecrit = False
        sys.addaudithook(self._hook)
        atexit.register(self.vider)

    # -- chemin CHAUD : appele a chaque `open` du process. Sortir au plus vite. ------------
    def _hook(self, event, args):
        if event == "open":
            p = args[0]
            if type(p) is not str or len(p) <= self._n:
                return
            if not p.replace("\\", "/").lower().startswith(self._prefixe):
                return
            if _est_ecriture(args):
                return
            rel = source_de(p.replace("\\", "/")[self._n:])
            if rel.startswith(_EXCLUS) or _SEGMENTS_EXCLUS.intersection(rel.split("/")[:-1]):
                return
            self.lectures.add(rel)
        elif event == "subprocess.Popen":
            try:
                self.programmes.add(programme_de(args))
            except Exception:                                      # noqa: BLE001 - jamais fatal
                self.programmes.add("<illisible>")

    def vider(self) -> None:
        if self._ecrit:
            return
        self._ecrit = True
        try:
            self.dossier.mkdir(parents=True, exist_ok=True)
            lignes = ["L\t" + r for r in sorted(self.lectures)]
            lignes += ["P\t" + p for p in sorted(self.programmes)]
            (self.dossier / ("%d.tsv" % os.getpid())).write_text(
                "\n".join(lignes) + "\n", encoding="utf-8")
        except Exception:                                          # noqa: BLE001 - jamais fatal
            pass


def _est_ecriture(args) -> bool:
    """`open` en ECRITURE ? Un cliquet qui ECRIT (son cache, un tmpdir) ne DEPEND pas de ce
    qu'il ecrit -- compter ces chemins gonflerait le perimetre d'artefacts qu'il produit."""
    mode = args[1] if len(args) > 1 else None
    if isinstance(mode, str):
        return any(c in mode for c in "wax+")
    flags = args[2] if len(args) > 2 else None
    if isinstance(flags, int):
        masque = (getattr(os, "O_WRONLY", 0) | getattr(os, "O_RDWR", 0)
                  | getattr(os, "O_CREAT", 0) | getattr(os, "O_APPEND", 0)
                  | getattr(os, "O_TRUNC", 0))
        return bool(flags & masque)
    return False


def installer(racine: str | None = None, dossier: str | None = None) -> bool:
    """Pose le hook dans CE process. Idempotent, et JAMAIS fatal : un `sitecustomize` qui leve
    ferait planter tous les process python de la machine pendant la mesure."""
    global _ETAT
    if _ETAT is not None:
        return True
    dossier = dossier or os.environ.get(ENV_TRACE)
    if not dossier:
        return False
    racine = racine or str(Path(__file__).resolve().parents[2])
    try:
        _ETAT = _Trace(racine, dossier)
    except Exception:                                              # noqa: BLE001
        return False
    return True


# ================================================================================= mesureur
_SITE = """# genere par declencheur_trace.preparer (#486-r12) -- NE PAS VERSIONNER.
# Le chemin est retire de `sys.path` SITOT le module charge : le laisser ferait importer les
# helpers de `scripts/python` a la place de ceux d'un arbre JETABLE (probe_319 en monte un), ce
# qui changerait le verdict du cliquet mesure -- une mesure ne doit rien deplacer.
import sys
_p = %(pydir)r
sys.path.insert(0, _p)
try:
    import declencheur_trace as _t
    _t.installer(%(racine)r)
except Exception:
    pass
finally:
    try:
        sys.path.remove(_p)
    except ValueError:
        pass
"""


def preparer(dossier_sortie, dossier_site, racine=None) -> dict:
    """Ecrit le `sitecustomize.py` de propagation et rend les variables d'environnement.

    Le tmpdir n'est mis en TETE de `PYTHONPATH` que parce qu'il ne contient QUE
    `sitecustomize.py` : aucun module du depot ne peut etre masque par lui.
    """
    racine = racine or str(Path(__file__).resolve().parents[2])
    pydir = str(Path(__file__).resolve().parent)
    site = Path(dossier_site)
    site.mkdir(parents=True, exist_ok=True)
    (site / "sitecustomize.py").write_text(
        _SITE % {"pydir": pydir, "racine": racine}, encoding="utf-8")
    env = dict(os.environ)
    env[ENV_TRACE] = str(dossier_sortie)
    ancien = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(site) + (os.pathsep + ancien if ancien else "")
    return env


def fusionner(dossier) -> tuple[set, set, int]:
    """(lectures, programmes lances, nombre de process traces) pour un dossier de traces."""
    lectures: set = set()
    programmes: set = set()
    fichiers = sorted(Path(dossier).glob("*.tsv")) if Path(dossier).is_dir() else []
    for f in fichiers:
        for ligne in f.read_text(encoding="utf-8", errors="replace").splitlines():
            if not ligne.strip():
                continue
            tag, _, val = ligne.partition("\t")
            if tag == "L":
                lectures.add(val)
            elif tag == "P":
                programmes.add(val)
    return lectures, programmes, len(fichiers)


#: Les programmes dont on SAIT qu'ils lisent le depot sans passer par notre hook. Un cliquet qui
#: en lance a une mesure INCOMPLETE, et le garde le dit au lieu de conclure.
OPAQUES = ("git", "git.exe", "pwsh", "pwsh.exe", "powershell", "powershell.exe")


def opaques(programmes) -> list:
    return sorted(p for p in programmes if p in OPAQUES)
