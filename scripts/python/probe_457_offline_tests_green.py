"""#457 -- CLIQUET : TOUT fichier de test qui n'est pas `_live.py` doit etre VERT.

CE QU'IL EST SEUL A VOIR
------------------------
Un fichier de test 100 % OFFLINE, ROUGE EN PERMANENCE sur `master`, que rien ne signale.

Mesure du 2026-08-02, sur `master` propre : `tests/engine/runner/test_multihex_substrate.py`
rendait `3 failed, 15 passed` -- et le rouge datait du 2026-08-01. Trois raisons CUMULEES le
rendaient invisible, et aucune n'est un oubli individuel :

  1. `CLAUDE.md` PROSCRIT la suite complete -- a raison : 405 des 489 fichiers de test montent un
     runner, la suite entiere sature la session Frida partagee.
  2. Un agent ne rejoue que les tests de SA tranche, et ce fichier n'etait la tranche de personne.
  3. Les trois entrees pytest de la banque (`pytest_signatures`, `pytest_attestations`,
     `pytest_adjacency`) nomment leurs fichiers A LA MAIN. C'est une ALLOWLIST : un fichier n'y
     entre que si quelqu'un pense a l'y mettre. Personne n'y a pense pour celui-la.

C'est la forme deja trouvee par #435 et #455, et la correction durable a chaque fois ete d'entrer
le garde dans la banque. Ce cliquet la generalise : son perimetre se DERIVE (tout ce qui n'est pas
`_live.py`), donc un fichier offline neuf y entre TOUT SEUL, sans que personne ait a y penser.

Il voit aussi la SECONDE moitie du meme vice, plus couteuse : le VERT VACUEUX. Dans le fichier
mesure, un quatrieme test passait au vert avec zero assertion utile -- son anneau de voisins etait
vide, donc `set([centre]) == {centre} | set([])` etait trivialement vraie. Un fichier rouge se
repare ; un fichier vert-a-vide s'accumule.

POURQUOI IL NE COUTE (PRESQUE) RIEN
-----------------------------------
La proscription de la suite complete vise le cout des tests LIVE. Les OFFLINE, eux, ne montent
aucun runner : mesure du 2026-08-02, 84 fichiers, 896 tests, 116 s d'un bloc -- et ~56 s de ce
total sont l'IMPORT des modules, pas les assertions. Eclate en trois shards, le plus long tombe a
86 s, donc SOUS le mur de la banque : le cout marginal en parallele est nul. Meme arbitrage que
`probe_283`, pour la meme raison.

LE PERIMETRE, ET POURQUOI CE CRITERE-LA
---------------------------------------
Le critere retenu est `not name.endswith("_live.py")`. Un critere plus fin a ete essaye puis
REFUTE PAR MESURE : classer par la CLOTURE DE FIXTURES (`"host" not in item.fixturenames`) rendait
153 fichiers << offline >>, dont des DIZAINES de `*_live.py` -- ils montent leur runner a la main,
sans passer par les fixtures `host`/`live_session`/`build_runner`. Joue tel quel, ce critere partait
monter des runners et depassait 600 s. Le suffixe, lui, est DECLARATIF et tenu par le depot.

La cloture de fixtures reste utilisee, mais comme FILET et non comme critere : un item d'un fichier
non-`_live.py` qui reclame quand meme une fixture live est DESELECTIONNE et RAPPORTE (mesure :
1 item, `test_act_of_faith_crit_resets_both_paths.py`, fichier MIXTE). On ne rougit pas dessus --
ce cliquet garde << les tests offline sont verts >>, pas << le nommage est parfait >>.

PERIMETRE (#434) : la liste vient de `git ls-files` lance dans CE checkout, donc elle ne peut pas
lire l'arbre d'un autre agent. ECRITURE (#455) : aucune -- `-p no:cacheprovider` empeche pytest de
deposer `.pytest_cache` sous `scripts/python/`, que la banque enumere en parallele.

ASCII only (cp1252).
"""
from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
import time
from pathlib import Path

import pytest

#: Fixture RACINE du monde live. La cloture calculee par pytest (`item.fixturenames`) est
#: TRANSITIVE : un item qui reclame `live_runner` -> `build_runner` -> `host` porte les trois.
#: Verifie le 2026-08-02 sur les 512 fichiers collectes -- `host` et `live_session` couvrent
#: EXACTEMENT les memes 359 fichiers, et `rpc`/`build_runner`/`live_runner` en sont des
#: sous-ensembles stricts (294 / 248 / 2). Une seule racine suffit donc a tous les reconnaitre.
LIVE_FIXTURE_ROOT = "host"

#: Repertoire des tests, relatif a `scripts/python` (= rootdir pytest, cf. `pytest.ini`).
TESTS_GLOB = "scripts/python/tests/**/test_*.py"

_PYDIR = Path(__file__).resolve().parent


def repo_root() -> Path:
    """Racine du checkout COURANT. Depuis un worktree, c'est le worktree -- jamais l'arbre
    principal (#434 : un cliquet ne balaie QUE son propre checkout)."""
    return _PYDIR.parents[1]


def candidate_files() -> list[str]:
    """Les fichiers de test NON `_live.py`, en chemins relatifs a `scripts/python`.

    Passe par `git ls-files` : seul l'index de CE checkout est consulte, donc ni les worktrees
    voisins ni les fichiers non suivis n'y entrent. Tri stable -- le shard doit etre reproductible."""
    out = subprocess.run(["git", "ls-files", TESTS_GLOB], capture_output=True, text=True,
                         cwd=str(repo_root()), check=True)
    prefix = "scripts/python/"
    rels = []
    for line in out.stdout.splitlines():
        rel = line.strip()
        if not rel or rel.endswith("_live.py") or not rel.startswith(prefix):
            continue
        rels.append(rel[len(prefix):])
    return sorted(rels)


def shard_of(rel: str, total: int) -> int:
    """Shard STABLE d'un fichier : md5 du chemin relatif, modulo `total`.

    Stable = independant de l'ordre et du nombre de fichiers, donc l'ajout d'un fichier ne
    redistribue pas les autres (un modulo sur l'INDEX du tri, lui, decale tout le monde)."""
    digest = hashlib.md5(rel.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % total


class _DeselectLiveItems:
    """Retire les items dont la cloture de fixtures touche le monde live, et les RAPPORTE."""

    def __init__(self) -> None:
        self.kept = 0
        self.dropped_items = 0
        self.dropped_files: set[str] = set()

    def pytest_collection_modifyitems(self, session, config, items):   # noqa: D102
        keep = []
        for item in items:
            if LIVE_FIXTURE_ROOT in set(getattr(item, "fixturenames", ())):
                self.dropped_items += 1
                self.dropped_files.add(str(item.path))
            else:
                keep.append(item)
        self.kept = len(keep)
        items[:] = keep


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--shard", default="0/1",
                    help="k/N -- ne joue que le shard k parmi N (defaut 0/1 = tout).")
    ap.add_argument("--list", action="store_true",
                    help="Imprime les fichiers du shard et sort, sans rien jouer.")
    args = ap.parse_args(argv)

    try:
        k_txt, n_txt = args.shard.split("/", 1)
        k, n = int(k_txt), int(n_txt)
    except ValueError:
        print("[457] --shard attend la forme k/N (ex. 0/3)")
        return 2
    if n < 1 or not (0 <= k < n):
        print("[457] --shard hors bornes : %s" % args.shard)
        return 2

    every = candidate_files()
    mine = [rel for rel in every if shard_of(rel, n) == k]
    print("[457] %d fichier(s) de test non-`_live.py` ; shard %d/%d -> %d fichier(s)"
          % (len(every), k, n, len(mine)))

    if args.list:
        for rel in mine:
            print("   ", rel)
        return 0

    if not mine:
        # Un shard vide n'est pas un succes : c'est le signe que le perimetre s'est effondre
        # (glob devenu faux, `git ls-files` muet). Le dire, plutot que rendre un vert.
        print("[457] FAIL shard VIDE -- le perimetre ne designe aucun fichier")
        return 1

    plugin = _DeselectLiveItems()
    started = time.time()
    # `-p no:cacheprovider` : aucune ecriture sous `scripts/python/` (#455 -- la banque enumere
    # cet arbre en parallele). `--import-mode=importlib` est deja dans `pytest.ini` ; on ne le
    # repete pas, pour que ce cliquet joue EXACTEMENT la configuration de production.
    rc = pytest.main(["-q", "-p", "no:cacheprovider", *mine], plugins=[plugin])
    elapsed = time.time() - started

    print("[457] %d test(s) joue(s) en %.1f s -- pytest rc=%d" % (plugin.kept, elapsed, int(rc)))
    if plugin.dropped_items:
        print("[457] %d item(s) DESELECTIONNE(S) (fixture live dans un fichier non-`_live.py`) :"
              % plugin.dropped_items)
        for path in sorted(plugin.dropped_files):
            try:
                shown = str(Path(path).relative_to(_PYDIR))
            except ValueError:
                shown = path
            print("    ", shown.replace("\\", "/"))
        print("[457] (rapporte, non bloquant : ce cliquet garde le VERT des offline, pas le nommage)")

    if int(rc) != 0:
        print("[457] VERDICT: FAIL -- au moins un test offline est ROUGE (pytest rc=%d)" % int(rc))
        return 1
    print("[457] VERDICT: PASS -- tous les tests offline du shard sont verts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
