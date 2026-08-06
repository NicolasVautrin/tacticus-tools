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
  2bis. RACCOURCIS (#409) : le cliquet est passe de ~100 s a ~24 s. L'essentiel
     de la baisse vient de repetitions supprimees (une lecture au lieu de
     trois, un parse au lieu de deux, un `ast.walk` au lieu de vingt-deux) --
     rien a verifier la. Mais TROIS points calculent autrement : ils sont
     confrontes a leur forme d'origine, exhaustivement sur l'arbre balaye.
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

#: Ce qui doit changer pour que ce cliquet puisse changer d'avis (#486-r12).
#: MESURE : 2 100 fichiers et **11 process** -- le seul des onze du groupe A a en tracer plus
#: d'un (il rejoue `probe_273` dans des arbres jetables). Ses lectures du DEPOT sont pourtant
#: exactement celles de `probe_273` : les arbres de mutation vivent dans `tempfile`, hors racine.
DECLENCHEUR = {
    "chemins": ("scripts/python/**/*.py", ".gitignore", "**/.gitignore", "data/**"),
    "build": False,
    "toujours": False,
    "raison": "DEUX natures dans un meme cliquet. Ses etapes 3 et 4 sont des CONTRE-EPREUVES : "
              "elles ne dependent que de {son source, celui de `probe_273`}, la portee la plus "
              "etroite du depot. Mais ses etapes 1, 2 et 2bis confrontent l'ancien balayage au "
              "nouveau SUR L'ARBRE REEL (`P._scan_paths(ROOT)`, `P._file_infos(ROOT)`) : un "
              "fichier neuf peut y creer un orphelin de couverture. Son perimetre est donc "
              "celui de `probe_273`, sans reduction possible.",
}

# Arbre minimal suffisant pour exercer le cliquet : le probe lui-meme, son
# helper, et les consommateurs qui portent les exceptions des DEUX allowlists.
# Copier tout `scripts/python/**` (1422 fichiers) rendrait ce probe aussi lent
# que le cliquet lui-meme -- donc jamais joue.
#
# Les six derniers viennent de `_ALLOWED_DATA` (etape 0c, #349). Sans eux, les
# sept exceptions de cette allowlist ne correspondent a RIEN dans l'arbre
# jetable, et `_check_allowlist_live` les declare MORTES : rc=1 quoi qu'on
# mute. Meme cause pour le referentiel `data/` pose par `_fresh_tree`.
_MINIMAL = ("probe_273_gitignored_inputs.py", "host_inputs.py",
            "build_asset_manifest.py",
            "audit_passive_ability_coverage.py", "gameconfig_diff.py",
            "playbook_keys.py", "rl_collect_batch.py", "rl_gen_ref_tables.py",
            "rl_ingest_postgres.py")

# Entrees VERSIONNEES de `data/` a reproduire dans l'arbre jetable. L'etape 0c
# derive son referentiel de `git ls-files data` et REFUSE de conclure s'il est
# vide -- a raison : « le verdict serait rendu contre un referentiel vide, donc
# faux dans les deux sens ». Un `git init` nu tombait exactement la-dedans.
_VERSIONED_DATA = ("boards/_x.json", "i2_en.json", "seed-bc.json",
                   "symbols/_x.tsv")


# ---- etape 1+2 : fidelite et couverture du balayage ---------------------- #

def _scan_with_fragments(scan_root: Path) -> list[str]:
    """L'ANCIEN balayage : `ast.walk` SANS filtrage des sous-expressions.

    Il etait ici REIMPLEMENTE, contre deux helpers (`_root_vars`, `_joined`) que
    `probe_273` n'a plus depuis que son evaluateur resout les chemins au lieu de
    reconnaitre des formes par le texte. Consequence mesuree le 2026-08-01 :
    `AttributeError: module ... has no attribute '_root_vars'` a la ligne 68,
    AVANT le premier controle -- ce probe, dont tout l'objet est de prouver que
    le cliquet #273 mord encore, ne prouvait plus rien du tout, et ses six
    mutations n'etaient plus jouees. Une reimplementation d'un balayage qu'on ne
    controle pas se perime en silence : on demande donc a `probe_273` lui-meme
    de rendre sa vue non filtree.
    """
    return [rel for (_, _, rel) in P._scan_paths(scan_root, drop_fragments=False)]


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


# ---- etape 2bis : les RACCOURCIS de balayage rendent-ils la meme chose ? -- #

def _tail_ref(node: ast.Call) -> str:
    """La forme d'ORIGINE : regenerer le source et couper au dernier point."""
    return ast.unparse(node.func).split(".")[-1]


def _frags_ref(tree: ast.Module) -> set[int]:
    """La forme d'ORIGINE : chasser `_base_of` depuis TOUS les noeuds."""
    inner: set[int] = set()
    for node in ast.walk(tree):
        cur = P._base_of(node)
        while cur is not None:
            inner.add(id(cur))
            cur = P._base_of(cur)
    return inner


_DECODE_CASES = [
    ("CRLF", b"a = 1\r\nb = 2\r\n"),
    ("CR seul", b"a = 1\rb = 2\r"),
    ("BOM", b"\xef\xbb\xbfa = 1\n"),
    ("form feed", b"x = 1\n\x0cy = 2\n"),
    ("utf-8 invalide", b"# \xff\xfe casse\n"),
    ("vide", b""),
]


def step_shortcuts() -> int:
    """Les trois raccourcis #409 calculent-ils EXACTEMENT la meme chose ?

    Reduire le cout du cliquet (#409 : ~100 s -> ~24 s) s'est fait en supprimant
    des REPETITIONS -- une lecture au lieu de trois, un parse au lieu de deux, un
    `ast.walk` au lieu de vingt-deux. Ces suppressions-la ne changent rien par
    construction. Trois points, eux, CALCULENT autrement, et ce sont les seuls
    qui puissent diverger : ils sont donc confrontes ici a leur forme d'origine,
    de facon EXHAUSTIVE sur l'arbre balaye.
    """
    print("\n== 2bis. raccourcis de balayage vs forme d'origine (#409) ==")
    rc = 0
    infos = P._file_infos(ROOT)

    n_calls = bad = 0
    for tree, _info in infos.values():
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                n_calls += 1
                if P._call_tail(node) != _tail_ref(node):
                    bad += 1
    print(f"  _call_tail          : {n_calls} noeuds Call, {bad} divergence(s)")
    if bad:
        print("      [FAIL] _call_tail ne rend plus le dernier segment pointe")
        rc = 1

    nf = 0
    for tree, info in infos.values():
        if info.frags != _frags_ref(tree):
            nf += 1
    print(f"  _fragment_ids       : {len(infos)} fichiers, {nf} divergence(s)")
    if nf:
        print("      [FAIL] partir des candidats ne rend plus le meme ensemble "
              "de fragments")
        rc = 1

    tmp = Path(tempfile.mkdtemp(prefix="probe319-dec-"))
    try:
        for label, data in _DECODE_CASES:
            f = tmp / "x.py"
            f.write_bytes(data)
            got = P._decode(data)
            ref = f.read_text(encoding="utf-8", errors="replace")
            try:
                f.read_text(encoding="utf-8")
                ref_raises = False
            except UnicodeDecodeError:
                ref_raises = True
            ok = (got.text == ref) and ((got.decode_error is not None) == ref_raises)
            print(f"      [{'OK  ' if ok else 'FAIL'}] _decode {label}"
                  f"{'  (leve en strict)' if ref_raises else ''}")
            if not ok:
                rc = 1
                print(f"        attendu {ref!r} / leve={ref_raises}")
                print(f"        obtenu  {got.text!r} / "
                      f"leve={got.decode_error is not None}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if rc == 0:
        print("  OK -- les trois raccourcis rendent la forme d'origine")
    return rc


# ---- etape 3 : determinisme vis-a-vis du disque -------------------------- #

def _fresh_tree() -> Path:
    """Depot jetable ou le cliquet est VERT -- donc ou une mutation se VOIT.

    Le `git add` suffit : `git ls-files` lit l'INDEX, pas un commit. Sans ce
    referentiel `data/`, l'etape 0c refusait de conclure et rendait rc=1 sur
    TOUS les cas -- les quatre « attendu ROUGE » passaient alors pour la
    mauvaise raison, et les deux « attendu VERT » etaient impossibles.
    """
    base = Path(tempfile.mkdtemp(prefix="probe319-"))
    subprocess.run(["git", "init", "-q", str(base)],
                   capture_output=True, text=True, timeout=120, check=True)
    shutil.copy(ROOT / ".gitignore", base / ".gitignore")
    dst = base / "scripts" / "python"
    dst.mkdir(parents=True)
    for name in _MINIMAL:
        shutil.copy(PYDIR / name, dst / name)
    for rel in _VERSIONED_DATA:
        p = base / "data" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("{}\n", encoding="utf-8")
    subprocess.run(["git", "add", "-f", "data"], cwd=str(base),
                   capture_output=True, text=True, timeout=120, check=True)
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


def _mut_data_output(tree: Path) -> None:
    """L'invariant #349 : ce qu'un run PRODUIT ne va pas dans `data/`."""
    (tree / "scripts" / "python" / "zz_data_out.py").write_text(
        "from pathlib import Path\n"
        "ROOT = Path(__file__).resolve().parents[2]\n"
        "OUT = ROOT / 'data' / '_run_output.json'\n"
        "OUT.write_text('{}')\n", encoding="utf-8")


def _mut_data_versioned_read(tree: Path) -> None:
    """Contre-epreuve de la precedente : LIRE une entree versionnee est legitime."""
    (tree / "scripts" / "python" / "zz_data_in.py").write_text(
        "from pathlib import Path\n"
        "ROOT = Path(__file__).resolve().parents[2]\n"
        "SEED = ROOT / 'data' / 'seed-bc.json'\n"
        "print(SEED.read_text())\n", encoding="utf-8")


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
    ("sortie de run dans data/ (0c, #349)", _mut_data_output, True,
     "data/_run_output.json"),
    ("arbre non mute", _mut_none, False, None),
    ("fragment de chemin (faux positif #319)", _mut_fragment_only, False, None),
    ("lecture d'une entree data/ VERSIONNEE (0c)", _mut_data_versioned_read,
     False, None),
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
    rc = (step_fidelity() | step_shortcuts() | step_determinism()
          | step_mutations())
    print("\n[319] rc=" + str(rc))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
