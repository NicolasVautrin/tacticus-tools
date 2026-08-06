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
  0c. SORTIE dans le `data/` du worktree COURANT (#349) : troisieme angle du
     meme invariant. `data/` est VERSIONNE et ne porte que des ENTREES ; ce
     qu'un run PRODUIT va dans `logs/`. Une sortie qui y atterrit salit
     `git status` sans que l'agent ait rien edite -- et brouille donc le signal
     meme dont l'invariant se sert comme garde-fou. Les etapes 0 et 0b sont
     aveugles au motif : le chemin est RELATIF (donc invisible a 0b) et
     `data/` n'est pas gitignore (donc hors verdict de 0).
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
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import host_inputs  # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]

#: Ce qui doit changer pour que ce cliquet puisse changer d'avis (#486-r12).
#: MESURE : 2 099 fichiers, tous sous `scripts/python/**` (tests compris). `.gitignore` et le
#: referentiel `data/` n'y apparaissent PAS -- ils sont lus par `git` (`check-ignore`,
#: `ls-files data`), hors de portee du hook, donc declares ICI par lecture du critere.
DECLENCHEUR = {
    "chemins": ("scripts/python/**/*.py", ".gitignore", "**/.gitignore", "data/**"),
    "build": False,
    "toujours": False,
    "raison": "Les trois etapes balaient `scripts/python/**/*.py` en AST (rglob, lecture "
              "unique partagee). S'y ajoutent DEUX entrees que seul `git` lit : les "
              "`.gitignore` (le verdict de l'etape 0 est `git check-ignore`, donc une regle "
              "modifiee suffit a le renverser) et `data/**` (l'etape 0c DERIVE son referentiel "
              "d'entrees VERSIONNEES de `git ls-files data`, et REFUSE de conclure s'il est "
              "vide). Le verdict n'est pas local a un fichier : le point fixe des etapes 0/0c "
              "partage un `modenv` -- 58 fichiers sur 2 090 empruntent une racine a un AUTRE "
              "module (#486-r1).",
}


# ---- lecture UNIQUE de `scripts/python/**`, partagee par les trois etapes -- #
#
# MESURE (2026-08-01, #409, profil cProfile + chronos par etape) : `--only-scan`
# coutait ~100 s en serie, ventiles ainsi -- ~54 s d'`open()`, ~16 s d'`ast.parse`,
# ~30 s d'`ast.walk`. Les trois postes venaient de la meme cause, la REPETITION :
#   * 3 traversees completes de l'arbre (etape 0, etape 0b, etape 0c), 1422
#     fichiers chacune. L'`open()` coute ~9 ms par fichier ici (filtre antivirus
#     au niveau du systeme -- le `read` lui-meme ne pese que 1,7 s pour 23 Mo, et
#     c'est aussi lent dans l'arbre principal que dans un worktree) ;
#   * 2 parses complets (le balayage AST est joue par l'etape 0 PUIS par la 0c) ;
#   * 11 `ast.walk` par fichier et par balayage, soit 22 traversees de chaque AST.
# Les trois etapes lisent EXACTEMENT les memes fichiers : on lit donc une fois,
# on parse une fois, on walke une fois. La lecture est en plus parallelisee --
# `open()` bloque hors GIL, donc 16 threads ramenent la passe de ~18 s a ~7 s.
# Aucun de ces trois changements ne touche a ce qui est DECIDE : cf. le probe
# `probe_319_scan_fidelity.py`, qui compare les verdicts et rejoue les mutations.

_READ_WORKERS = 16


class _Src:
    """Texte source d'un fichier balaye, deja decode."""

    __slots__ = ("text", "decode_error")

    def __init__(self, text: str, decode_error: UnicodeDecodeError | None):
        self.text = text
        self.decode_error = decode_error


def _decode(data: bytes) -> _Src:
    """Reproduit `Path.read_text` : utf-8 + newlines universelles.

    Les deux lecteurs d'origine ne lisaient PAS pareil -- l'etape 0b en
    `errors="replace"` (tolerante), le balayage AST en strict (fatal, la
    `UnicodeDecodeError` n'etant rattrapee par aucun des deux `except`).
    Partager la lecture ne doit pas transformer ce plantage en silence : on
    decode en strict, on ne bascule en `replace` qu'en repli, et l'erreur est
    CONSERVEE pour etre re-levee par `_file_infos` -- au meme moment qu'avant.
    """
    try:
        text, err = data.decode("utf-8"), None
    except UnicodeDecodeError as e:
        text, err = data.decode("utf-8", errors="replace"), e
    return _Src(text.replace("\r\n", "\n").replace("\r", "\n"), err)


_SRC_CACHE: dict[Path, dict[Path, _Src]] = {}


def _sources(scan_root: Path) -> dict[Path, _Src]:
    """`{fichier: source}` pour `scripts/python/**`, dans l'ordre `sorted`.

    Un fichier illisible (`OSError`) est ABSENT du dict : les deux balayages le
    sautaient deja, chacun avec son propre `except OSError`.
    """
    cached = _SRC_CACHE.get(scan_root)
    if cached is not None:
        return cached
    files = sorted((scan_root / "scripts" / "python").rglob("*.py"))

    def _read(f: Path) -> bytes | None:
        try:
            return f.read_bytes()
        except OSError:
            return None

    with ThreadPoolExecutor(max_workers=_READ_WORKERS) as ex:
        blobs = list(ex.map(_read, files))
    out = {f: _decode(b) for f, b in zip(files, blobs) if b is not None}
    _SRC_CACHE[scan_root] = out
    return out


def _reset_caches() -> None:
    """Vide les caches (le disque a change sous nos pieds)."""
    _SRC_CACHE.clear()
    _INFO_CACHE.clear()
    _PATHS_CACHE.clear()


# ---- balayage commun (etapes 0 et 0c) : evaluation CONCRETE des chemins --- #

_DYN = "<dyn>"


class _Eval:
    """Evalue un chemin construit dans le source, EN CONNAISSANT le fichier.

    L'ancienne version reconnaissait des FORMES par le texte (`"__file__" in
    src and "parent" in src`), et ratait en silence tout ce qui remontait par
    une racine deja nommee : `DATA = PYDIR.parent.parent / "data"` (le motif de
    `probe_113_votann.py`) n'etait PAS un chemin, pour elle. Ici on evalue pour
    de vrai -- `__file__` vaut le fichier balaye -- donc `.parent`,
    `.parents[N]`, `os.path.dirname/join`, `Path(...)`, `str(...)` et les
    variables (module ET locales, point fixe) se resolvent en un chemin ABSOLU
    que l'on rapporte ensuite a la racine balayee.

    Un segment non litteral (f-string, variable, `%`) devient `<dyn>` : le
    prefixe statique porte la decision, et pour l'etape 0c `<dyn>` est en
    lui-meme un verdict (aucune entree versionnee n'a de nom calcule).
    """

    def __init__(self, f: Path, env: dict, modenv: dict, alias: dict):
        self.f, self.env, self.modenv, self.alias = f, env, modenv, alias

    @staticmethod
    def _s(node: ast.AST) -> str | None:
        return node.value if (isinstance(node, ast.Constant)
                              and isinstance(node.value, str)) else None

    @staticmethod
    def _slash(base: Path, seg: str) -> Path:
        """`base / seg`, en NORMALISANT `..` -- `pathlib` ne le fait pas.

        Sans ca, `PYDIR / ".." / ".." / "logs" / "x.json"` (deux probes) rend
        `scripts/python/../../logs/x.json` : un chemin qui ne commence pas par
        `logs/`, donc classe « autre » au lieu de SORTIE, et le cliquet rougit
        sur une sortie parfaitement conforme.
        """
        if seg == "..":
            return base.parent
        return base if seg in (".", "") else base / seg

    def ev(self, node: ast.AST, depth: int = 0) -> Path | None:
        if depth > 12:
            return None
        if isinstance(node, ast.Name):
            return self.f if node.id == "__file__" else self.env.get(node.id)
        if isinstance(node, ast.Attribute):
            # `<module_importe>.VAR` (ex. `R.BOARDS_DIR` via `import runner as R`)
            if isinstance(node.value, ast.Name) and node.value.id in self.alias:
                return self.modenv.get(self.alias[node.value.id], {}).get(node.attr)
            if node.attr == "parent":
                b = self.ev(node.value, depth + 1)
                return b.parent if b is not None else None
            return None
        if isinstance(node, ast.Subscript):          # `<x>.parents[N]`
            v = node.value
            if isinstance(v, ast.Attribute) and v.attr == "parents":
                b = self.ev(v.value, depth + 1)
                n = node.slice.value if isinstance(node.slice, ast.Constant) else None
                if b is not None and isinstance(n, int):
                    try:
                        return b.parents[n]
                    except IndexError:
                        return None
            return None
        if isinstance(node, ast.Call):
            tail = _call_tail(node)
            if tail in ("Path", "str", "abspath", "realpath", "normpath",
                        "fspath") and node.args:
                return self.ev(node.args[0], depth + 1)
            if tail in ("resolve", "absolute", "expanduser") and isinstance(
                    node.func, ast.Attribute):
                return self.ev(node.func.value, depth + 1)
            if tail == "dirname" and node.args:
                b = self.ev(node.args[0], depth + 1)
                return b.parent if b is not None else None
            if tail in ("join", "joinpath"):
                if tail == "joinpath" and isinstance(node.func, ast.Attribute):
                    b, rest = self.ev(node.func.value, depth + 1), node.args
                elif node.args:
                    b, rest = self.ev(node.args[0], depth + 1), node.args[1:]
                else:
                    return None
                if b is None:
                    return None
                for a in rest:
                    b = self._slash(b, self._s(a) or _DYN)
                return b
            return None
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            b = self.ev(node.left, depth + 1)
            return None if b is None else self._slash(b, self._s(node.right) or _DYN)
        return None


def _call_tail(node: ast.Call) -> str:
    """Dernier segment pointe de `node.func`, sans regenerer du source.

    `ast.unparse(node.func).split(".")[-1]` reconstruit du texte Python pour
    CHAQUE appel du fichier -- 160 765 noeuds `Call` sur cet arbre, et le
    balayage repassait dessus a chaque `ast.walk`. Or le resultat est connu par
    construction : pour un `Attribute` c'est exactement `.attr` (un nom
    d'attribut ne contient jamais de point, donc c'est le dernier segment), pour
    un `Name` c'est `.id`. Verifie exhaustivement sur les 160 765 noeuds de
    l'arbre : 0 divergence. Les autres formes (`f(x)(y)`, `d[k]()`) restent sur
    `ast.unparse` -- elles sont rares et aucune ne tombe dans les listes de
    `tail` reconnues.
    """
    f = node.func
    if isinstance(f, ast.Attribute):
        return f.attr
    if isinstance(f, ast.Name):
        return f.id
    return ast.unparse(f).split(".")[-1]


def _is_join_call(node: ast.AST) -> bool:
    return (isinstance(node, ast.Call)
            and _call_tail(node) in ("join", "joinpath"))


def _base_of(node: ast.AST) -> ast.AST | None:
    """Sous-expression qui sert de BASE a `node`, si `node` est collectable."""
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        return node.left
    if _is_join_call(node):
        if isinstance(node.func, ast.Attribute) and node.func.attr == "joinpath":
            return node.func.value
        return node.args[0] if node.args else None
    return None


def _fragment_ids(cands: list[ast.AST]) -> set[int]:
    """Ids des sous-expressions qui ne sont que la BASE d'un chemin plus long.

    `ast.walk` visite tout le sous-arbre : sur `ROOT / "frida" / "assets" /
    "raw" / "Bundles"` il rend AUSSI les trois prefixes. Ce ne sont pas des
    chemins que le script construit, ce sont des fragments de syntaxe -- les
    compter revenait a INVENTER des lectures (`frida/assets` etait signale
    comme lu par `build_asset_manifest.py`, qui ne le nomme nulle part). Seule
    l'expression MAXIMALE est un chemin reel.

    On part des CANDIDATS et non de tous les noeuds : `_base_of` ne rend jamais
    autre chose que `None` en dehors d'un `BinOp`/`Div` ou d'un appel
    `join`/`joinpath` -- c'est-a-dire exactement l'ensemble des candidats. Les
    autres noeuds n'ajoutaient donc rien, ils coutaient une traversee complete.
    """
    inner: set[int] = set()
    for node in cands:
        cur = _base_of(node)
        while cur is not None:
            inner.add(id(cur))
            cur = _base_of(cur)
    return inner


class _FileInfo:
    """Ce que le balayage tire d'un fichier -- en UNE passe `ast.walk`.

    Les quatre buckets etaient auparavant remplis par quatre familles de
    traversees distinctes (alias, 4 x assignations, 4 x `import ... from`,
    fragments + candidats), rejouees a chaque balayage. L'ORDRE `ast.walk` est
    conserve bucket par bucket, et c'est necessaire : le point fixe en depend
    (un fichier voit le `modenv` deja mis a jour par ceux qui le precedent, et
    une assignation ecrase la precedente dans l'ordre de visite).
    """

    __slots__ = ("alias", "assigns", "imports_from", "cands", "frags")

    def __init__(self, tree: ast.Module):
        self.alias: dict[str, str] = {}
        self.assigns: list[tuple[str, ast.AST]] = []
        self.imports_from: list[ast.ImportFrom] = []
        self.cands: list[ast.AST] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if _call_tail(node) in ("join", "joinpath"):
                    self.cands.append(node)
            elif isinstance(node, ast.BinOp):
                if isinstance(node.op, ast.Div):
                    self.cands.append(node)
            elif isinstance(node, ast.Assign):
                if (len(node.targets) == 1
                        and isinstance(node.targets[0], ast.Name)):
                    self.assigns.append((node.targets[0].id, node.value))
            elif isinstance(node, ast.Import):
                for a in node.names:
                    self.alias[a.asname or a.name.split(".")[0]] = a.name
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    self.imports_from.append(node)
        self.frags = _fragment_ids(self.cands)


def _module_name(f: Path, pydir: Path) -> str:
    return f.relative_to(pydir).with_suffix("").as_posix().replace("/", ".")


_INFO_CACHE: dict[Path, dict[Path, tuple[ast.Module, _FileInfo]]] = {}


def _file_infos(scan_root: Path) -> dict[Path, tuple[ast.Module, _FileInfo]]:
    """`{fichier: (arbre, buckets)}`. L'arbre est RETENU : `frags` porte des
    `id()` de noeuds, qui ne restent uniques que tant que l'arbre est vivant."""
    cached = _INFO_CACHE.get(scan_root)
    if cached is not None:
        return cached
    out: dict[Path, tuple[ast.Module, _FileInfo]] = {}
    for f, src in _sources(scan_root).items():
        if src.decode_error is not None:
            raise src.decode_error        # lecture stricte : meme echec qu'avant
        try:
            tree = ast.parse(src.text)
        except SyntaxError:
            continue
        out[f] = (tree, _FileInfo(tree))
    _INFO_CACHE[scan_root] = out
    return out


_PATHS_CACHE: dict[tuple[Path, bool], list[tuple[Path, int, str]]] = {}


def _scan_repo_paths(scan_root: Path,
                     drop_fragments: bool = True) -> list[tuple[Path, int, str]]:
    """[(fichier, ligne, chemin relatif a `scan_root`)] pour `scripts/python/**`.

    Le relatif garde ses segments `<dyn>` : c'est a l'appelant de tronquer
    (etape 0) ou de les traiter comme un verdict (etape 0c).

    `drop_fragments=False` rend le balayage d'AVANT #319 -- fragments de syntaxe
    compris. C'est ce dont `probe_319_scan_fidelity.py` a besoin pour mesurer ce
    que le filtrage retire, et il n'a aucun autre moyen de le reconstituer.

    Le resultat est memoise : les etapes 0 et 0c posent la MEME question a
    l'arbre, et la calculer deux fois doublait le poste le plus cher du probe.
    """
    key = (scan_root, drop_fragments)
    cached = _PATHS_CACHE.get(key)
    if cached is not None:
        return cached
    pydir = scan_root / "scripts" / "python"
    infos = _file_infos(scan_root)
    envs: dict[Path, dict] = {f: {} for f in infos}
    modenv: dict[str, dict] = {}
    # Point fixe : une racine peut venir d'une autre variable du meme fichier
    # (`ROOT = PYDIR.parents[1]`) OU d'un module voisin (`from rl_gen_ref_tables
    # import ROOT`, `import runner as R` puis `R.BOARDS_DIR`).
    for _ in range(4):
        for f, (_tree, info) in infos.items():
            ev = _Eval(f, envs[f], modenv, info.alias)
            for name, value in info.assigns:
                p = ev.ev(value)
                if p is not None:
                    envs[f][name] = p
            modenv[_module_name(f, pydir)] = envs[f]
        for f, (_tree, info) in infos.items():
            for node in info.imports_from:
                src = modenv.get(node.module) or {}
                for a in node.names:
                    if a.name in src:
                        envs[f].setdefault(a.asname or a.name, src[a.name])
    out: list[tuple[Path, int, str]] = []
    for f, (_tree, info) in infos.items():
        ev = _Eval(f, envs[f], modenv, info.alias)
        for node in info.cands:
            if drop_fragments and id(node) in info.frags:
                continue
            p = ev.ev(node)
            if p is None:
                continue
            try:
                rel = p.relative_to(scan_root).as_posix()
            except ValueError:
                continue                      # hors du depot (AppData, temp, ...)
            if rel in ("", "."):
                continue
            out.append((f, getattr(node, "lineno", 0), rel))
    _PATHS_CACHE[key] = out
    return out


def _scan_paths(scan_root: Path,
                drop_fragments: bool = True) -> list[tuple[Path, str, str]]:
    """Vue etape 0 : chemins TRONQUES au premier segment dynamique."""
    out: list[tuple[Path, str, str]] = []
    for f, _lineno, rel in _scan_repo_paths(scan_root, drop_fragments):
        segs = rel.split("/")
        if _DYN in segs:
            segs = segs[:segs.index(_DYN)]
        if segs:
            out.append((f, "<path>", "/".join(segs)))
    return out


def _ask_git_ignored(rels: list[str], scan_root: Path, as_dir: bool) -> set[str]:
    """`git check-ignore -z --stdin` en un seul appel. `as_dir` = slash final.

    `-z` des DEUX cotes : sans lui, git QUOTE les chemins en sortie ("a/b") et
    la console Windows y ajoute un CR -- le set ne matchait alors rien et le
    balayage annoncait « 0 gitignore », soit exactement le faux negatif que ce
    probe est cense mesurer.
    """
    if not rels:
        return set()
    probe = [rel + "/" for rel in rels] if as_dir else list(rels)
    r = subprocess.run(["git", "check-ignore", "-z", "--stdin"],
                       cwd=str(scan_root), input="\0".join(probe),
                       capture_output=True, text=True, timeout=60)
    return {tok.replace("\\", "/").rstrip("/")
            for tok in (r.stdout or "").split("\0") if tok}


def _check_ignored(rels: list[str], scan_root: Path) -> dict[str, bool]:
    """Le chemin est-il gitignore ? Verdict INDEPENDANT de l'etat du disque.

    Une regle `.gitignore` a slash final (`frida/assets/`, ligne 41) est
    DIRECTORY-ONLY : git ne l'applique que s'il sait que la cible est un
    repertoire, et il le deduit du DISQUE. Consequence mesuree (#319) : le
    meme chemin est rendu « ignore » dans l'arbre principal (ou le repertoire
    existe) et « non ignore » dans un worktree frais (ou il est absent) -- le
    cliquet virait au vert precisement la ou travaillent les agents, et un
    « probe_273 : OK » rapporte de bonne foi depuis un worktree contredisait
    le rouge de l'arbre principal.

    C'est le motif #273 lui-meme retourne contre son propre garde-fou : un
    verdict qui depend d'un repertoire absent se lit « rien a signaler ».
    On interroge donc git DEUX fois -- chemin nu et chemin suffixe `/` -- et
    on retient l'UNION. Un chemin statique ne dit pas s'il designe un fichier
    ou un repertoire ; l'union est la reponse qui ne depend d'aucun checkout,
    et elle penche du cote fail-loud, seul cote acceptable pour un cliquet.
    """
    if not rels:
        return {}
    ignored = (_ask_git_ignored(rels, scan_root, as_dir=False)
               | _ask_git_ignored(rels, scan_root, as_dir=True))
    return {rel: (rel in ignored) for rel in rels}


# Chemins gitignores hors `logs/` qui restent construits depuis une racine
# `__file__`, et POURQUOI c'est admis. Toute AUTRE entree fait echouer l'etape 0
# -- c'est le cliquet : chaque nouveau `ROOT / <gitignore>` doit soit passer par
# `host_inputs`, soit venir s'expliquer ici.
# Une cle couvre le chemin ET ses sous-chemins (`_allowed_for`) : depuis que le
# balayage resout les variables intermediaires, `PUBLIC / "units"` et ses cinq
# soeurs remontent aussi -- six lignes d'allowlist pour UNE raison, c'est du
# bruit qui finit par cacher la vraie exception.
_ALLOWED: dict[str, str] = {
    "frida/assets/public":
        "SORTIE de build_asset_manifest.py (mkdir + ecriture), pas une entree "
        "-- couvre ses sous-repertoires (units/, boards/, i18n/, ...)",
    "frida/assets/raw/Bundles":
        "constante RAW, repli du bundle d'installation ; _bundle_dir resout "
        "par host_inputs et les appelants impriment deja [warn] missing",
}


def _allowed_for(rel: str, allowed: dict[str, str]) -> tuple[str, str] | None:
    """Cle d'allowlist couvrant `rel` (elle-meme ou un de ses prefixes)."""
    for k, why in allowed.items():
        if rel == k or rel.startswith(k + "/"):
            return k, why
    return None
# `frida/assets/raw` y figurait, justifie « prefixe de RAW » : c'etait l'aveu
# que le balayage remontait des fragments (cf. `_fragment_ids`). Le fragment
# elimine, la ligne n'a plus d'objet -- une exception se RETIRE quand sa cause
# est corrigee, elle ne se garde pas « au cas ou ».


# Racines gitignorees qui sont des SORTIES du depot, jamais des entrees.
#   `logs/` : sorties de run (state-files, dumps de probe) -- meurt avec le
#             worktree ;
#   `app/`  : arbre Java GENERE par `gen_battle_config_java.py` /
#             `gen_loki_effects.py`. Il n'y est apparu (#314) qu'en devenant
#             RELATIF : tant que le chemin etait absolu, l'etape 0 ne le voyait
#             pas du tout.
_OUTPUT_ROOTS = {"logs", "app"}


def _check_allowlist_live(allowed: dict[str, str], seen: set[str],
                          name: str) -> int:
    """Une exception admise qui ne correspond plus a RIEN doit disparaitre.

    Sans ce controle, une allowlist ne fait que croitre : la ligne survit a la
    correction qui l'a rendue inutile, et plus personne ne sait laquelle des
    entrees couvre encore un cas reel. C'est ainsi que ce genre de dette
    devient permanent. Le cliquet s'applique donc DANS LES DEUX SENS -- entrer
    oblige a se justifier, ne plus s'appliquer oblige a sortir.

    Le verdict n'est exploitable que parce que `_check_ignored` ne depend plus
    du disque (#319) : tant qu'il en dependait, une entree pouvait paraitre
    « morte » dans un worktree et vivante dans l'arbre principal.
    """
    dead = sorted(k for k in allowed if k not in seen)
    if not dead:
        return 0
    print(f"  FAIL -- {name} : exception(s) sans objet, a RETIRER "
          f"(plus aucun chemin balaye ne correspond)")
    for k in dead:
        print(f"      [MORTE] {k}")
    return 1


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
    used: set[str] = set()
    for rel in inputs:
        who = sorted({f.name for (f, _, r) in found if r == rel})
        hit = _allowed_for(rel, _ALLOWED)
        tag = "OK  " if hit else "FAIL"
        print(f"      [{tag}] {rel:<30} <- {', '.join(who)}")
        if hit:
            used.add(hit[0])
            print(f"               ({hit[1]})")
        else:
            rc = 1
    if rc:
        print("  FAIL -- entree gitignoree lue depuis la racine sans passer par "
              "host_inputs : un glob y rendrait [] SANS lever (cf. etape 1)")
    rc |= _check_allowlist_live(_ALLOWED, used, "_ALLOWED")
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

    Meme source que les etapes 0 et 0c (`_sources`) : c'etait la TROISIEME
    traversee complete de l'arbre pour lire les memes 1422 fichiers.
    """
    out: list[tuple[Path, int, str]] = []
    for f, src in _sources(scan_root).items():
        for i, ln in enumerate(src.text.splitlines(), 1):
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
    seen = set()
    for f, lineno, _ in hits:
        try:
            seen.add(f"{f.relative_to(scan_root).as_posix()}:{lineno}")
        except ValueError:
            seen.add(f"{f.as_posix()}:{lineno}")
    rc |= _check_allowlist_live(_ALLOWED_ABS, seen, "_ALLOWED_ABS")
    return rc


# ---- etape 0c : SORTIE dans le `data/` du worktree courant (#349) --------- #

# Chemins `data/...` qui ne designent PAS une entree versionnee et restent
# admis, avec la raison. Cle = "<fichier>:<chemin data/ resolu>" -- pas le
# numero de ligne (il bouge a chaque edition), pas le chemin seul (`data/<dyn>`
# couvrirait alors tous les state-files du depot).
#
# Ce qui est admis ici : des LECTURES d'entrees locales non versionnees,
# produites HORS run (dump IL2CPP, instantane gameconfig, spawn-probe
# exhaustif). Elles relevent de l'angle #273 -- un worktree ne les a pas, et
# une lecture nue y rend [] ou None sans le dire -- pas de #349. Une ECRITURE
# de run n'entre JAMAIS ici : elle demenage dans `logs/`.
_ALLOWED_DATA: dict[str, str] = {
    "scripts/python/audit_passive_ability_coverage.py:data/<dyn>":
        "LECTURE data/unspawnable_rank<N>.json (spawn-probe exhaustif), "
        "avec repli explicite sur UNSPAWNABLE_FALLBACK",
    "scripts/python/rl_collect_batch.py:data/<dyn>":
        "LECTURE data/unspawnable_rank<N>.json (meme source), repli idem",
    "scripts/python/gameconfig_diff.py:data/gameconfig":
        "LECTURE de l'instantane gameconfig versionne hors depot ; l'outil "
        "compare deux instantanes et dit lui-meme lequel manque",
    "scripts/python/playbook_keys.py:data/dumps":
        "LECTURE du dump IL2CPP local (per-hash, produit par dump-il2cpp-full)",
    "scripts/python/playbook_keys.py:data/dumps/<dyn>/stringliteral.json":
        "LECTURE du dump IL2CPP local (idem)",
    "scripts/python/rl_gen_ref_tables.py:data/dumps/<dyn>/dump.cs":
        "LECTURE du dump IL2CPP local ; absence -> SystemExit explicite",
    "scripts/python/rl_ingest_postgres.py:data/dumps":
        "LECTURE du dump IL2CPP local (auto-detection du hash de build)",
}


def _versioned_data_entries(scan_root: Path) -> set[str]:
    """Premiers segments sous `data/` que git SUIT, dans CE checkout.

    Derive de `git ls-files`, jamais d'une liste en dur : une liste ecrite ici
    se perimerait au premier ajout d'entree (et un cliquet perime rougit sur du
    legitime, ce qui le fait desarmer).
    """
    r = subprocess.run(["git", "ls-files", "-z", "data"], cwd=str(scan_root),
                       capture_output=True, text=True, timeout=60)
    out = {tok.replace("\\", "/").split("/")[1]
           for tok in (r.stdout or "").split("\0")
           if tok and "/" in tok.replace("\\", "/")}
    return out


def step0c(scan_root: Path) -> int:
    print("\n== 0c. SORTIE dans le `data/` du worktree courant (#349) ==")
    print(f"  arbre balaye        : {scan_root.as_posix()}")
    versioned = _versioned_data_entries(scan_root)
    print(f"  entrees versionnees : {len(versioned)} "
          f"({', '.join(sorted(versioned)) if versioned else 'AUCUNE'})")
    if not versioned:
        print("  FAIL -- `git ls-files data` ne rend RIEN : le verdict serait "
              "rendu contre un referentiel vide, donc faux dans les deux sens.")
        return 1
    hits = [(f, ln, rel) for (f, ln, rel) in _scan_repo_paths(scan_root)
            if rel == "data" or rel.startswith("data/")]
    bad: list[tuple[str, str, int]] = []
    for f, lineno, rel in hits:
        segs = rel.split("/")
        if len(segs) > 1 and segs[1] in versioned:
            continue                        # entree versionnee -> lecture (ou
        if len(segs) == 1:                  # regeneration) legitime
            continue                        # `data` nu : pas une destination
        try:
            src = f.relative_to(scan_root).as_posix()
        except ValueError:
            src = f.as_posix()
        bad.append((src, rel, lineno))
    print(f"  chemins data/       : {len(hits)}   "
          f"hors entree versionnee : {len(bad)}")
    rc = 0
    used: set[str] = set()
    for src, rel, lineno in sorted(set(bad)):
        key = f"{src}:{rel}"
        why = _ALLOWED_DATA.get(key)
        tag = "OK  " if why else "FAIL"
        print(f"      [{tag}] {src}:{lineno}  ->  {rel}")
        if why:
            used.add(key)
            print(f"               ({why})")
        else:
            rc = 1
    if rc:
        print("  FAIL -- `data/` ne porte que des ENTREES VERSIONNEES. Ce qu'un "
              "run PRODUIT (state-file, seed BC augmente, dump de probe) va "
              "dans `logs/` : sinon l'arbre d'un agent devient SALE sans qu'il "
              "ait rien edite, et le `git status` dont l'invariant se sert comme "
              "garde-fou ne veut plus rien dire.")
    else:
        print("  OK -- aucune sortie de run dans data/")
    rc |= _check_allowlist_live(_ALLOWED_DATA, used, "_ALLOWED_DATA")
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
                    help="etapes 0 + 0b + 0c seules (le cliquet, 100%% offline)")
    args = ap.parse_args(argv[1:])
    scan_root = Path(args.scan_root).resolve() if args.scan_root else ROOT
    if args.only_scan:
        return step0(scan_root) | step0b(scan_root) | step0c(scan_root)
    rc = (step0(scan_root) | step0b(scan_root) | step0c(scan_root)
          | step1() | step2() | step3())
    if args.demo_worktree:
        rc |= step4(args.ref)
    print("\n[273] rc=" + str(rc))
    return rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
