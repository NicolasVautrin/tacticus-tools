"""#935 -- QUELS cliquets offline la SELECTION PAR DIFF ne peut PAS voir, et pourquoi.

LE FAIT QUI OUVRE CETTE TRANCHE, MESURE LE 2026-08-11. Neuf fichiers de `scripts/python/tests/`
(racine) etaient ROUGES sur `origin/master` a `7611776e`, dont sept armes par des merges du jour
meme. L'orchestrateur en jouait HUIT, choisis a la main et jamais re-derives -- le vice
<< un declencheur trop etroit est un faux vert >>, applique a la conduite.

`probe_457 --since <base>` EST la voie derivee : son perimetre se derive (tout test non-`_live.py`),
donc un cliquet neuf y entre tout seul. Mais la SELECTION, elle, rate exactement la classe de
cliquets qui gardent le depot :

    merge   selection --since        le cliquet qui a rougi         retenu ?
    #911    45/313                   test_314_absolute_repo_path     NON
    #911    45/313                   test_host_inputs                NON
    #893    275/307                  test_step_ordinal_ratchet       NON
    #900    283/309                  test_449_r2_spread_face_combat  NON
    #909    284/312                  test_366_r1_bcpatch_port_blind  NON

Ce n'est PAS une question d'etroitesse : a #893 la selection retenait **90 %** du perimetre et
manquait quand meme le cliquet fautif. La cause est STRUCTURELLE, et le code de `impacted_files`
la nomme deja sans la combler : la moitie MESUREE traite les `.py` par le GRAPHE D'IMPORTS, et
l'empreinte (`dirs`) ne sert QUE pour les changements HORS-`.py`. Un cliquet qui **BALAIE** des
`.py` sans les IMPORTER -- `probe_273._scan_abs_repo`, `SW.sweep_py`, l'inventaire de
`probe_449r2`, celui de `probe_366_r1` -- n'a donc aucune arete vers le fichier qu'il accuse.
Meme chose pour un cliquet qui delegue a un SOUS-PROCESSUS : les fichiers qu'il ouvre ne sont
traces ni par le graphe ni par l'empreinte (`test_host_inputs_offline.py` a une empreinte
`dirs: []`, `temoins: []` alors qu'il lance `probe_273` en entier).

CE PROBE REND CETTE CLASSE DERIVABLE. Il ne l'enumere pas : il lit l'AST du fichier de test ET de
la CLOTURE de ses imports locaux, et classe INSELECTIONNABLE tout ce qui balaie ou sous-traite.
Un cliquet neuf de cette forme entre donc dans la liste sans que personne y pense -- ce qui est
exactement la propriete que la liste de huit n'avait pas.

⚠ CE QU'IL N'EST PAS : un SELECTEUR. La partition qu'il rendrait possible a ete MESUREE puis
ECARTEE -- le taux de retention median de `--since` sur les 11 merges vaut **90 %** (14, 59, 59,
90, 90, 91, 91, 91, 91, 92, 100), donc la selection n'economise qu'un dixieme du mur, et sa
classification coute a elle seule 73,7 s. Le geste a chaque merge est le COMPLET
(`probe_457 --jobs 8`, mur mesure **763 s** pour 323 fichiers).

Ce probe est donc la MESURE QUI INTERDIT de << re-optimiser >> vers `--since` sans traiter d'abord
son angle mort (residu #935-r1). Un jour ou le complet deviendrait trop cher, la composition sure
est `{ce que rend ce probe} UNION {selection --since}` -- jamais la selection seule.

⚠ SUR-APPROXIMATION ASSUMEE, et dans le sens SUR : un module qui appelle `glob` sur un repertoire
de DONNEES (pas de `.py`) est classe balayeur alors que l'empreinte le couvrirait. Le prix est du
temps de test ; le prix de l'erreur inverse est un rouge de `master` que personne ne voit. Le
compte des deux classes est imprime a chaque run, donc une derive de l'approximation se voit.

Usage (depuis `scripts/python`) :

    python probe_935_cliquets_insellectionnables.py            # la liste + les causes
    python probe_935_cliquets_insellectionnables.py --liste    # un chemin par ligne, pour un pipe

ASCII only (console cp1252). 100 % OFFLINE : aucun runner, aucun RPC.
"""
from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

_PYDIR = Path(__file__).resolve().parent
if str(_PYDIR) not in sys.path:
    sys.path.insert(0, str(_PYDIR))

import probe_457_offline_tests_green as P457                                  # noqa: E402

#: Ce qui doit changer pour que ce cliquet puisse changer d'avis (#486-r15).
DECLENCHEUR = {
    "chemins": ("scripts/python/tests/**", "scripts/python/**/*.py"),
    "build": False,
    "toujours": False,
    "raison": "Sa sortie est une FONCTION de l'arbre `scripts/python/**` : tout module qui entre "
              "dans la cloture d'imports d'un test peut le faire changer de classe.",
}

#: Appels qui ENUMERENT un arbre de fichiers. Le nom suffit : ce sont des noms de methode
#: `pathlib`/`glob`/`os` que rien d'autre ne porte dans ce depot.
_APPELS_DE_BALAYAGE = {"rglob", "glob", "iglob", "walk", "iterdir", "scandir"}

#: Appels qui delegent a un PROCESSUS FILS. Ce que le fils ouvre n'est trace par rien --
#: ni graphe d'imports, ni empreinte (elle n'instrumente que le process du test).
_APPELS_DE_SOUS_PROCESSUS = {"run", "Popen", "check_output", "check_call", "call"}

#: La marque d'un balayage delegue a git plutot qu'au systeme de fichiers.
_MARQUEURS_GIT = ("ls-files",)


def _module_local(nom: str) -> Path | None:
    """Le fichier de `scripts/python/**` que designe ce nom de module importe, ou `None`."""
    bouts = nom.split(".")
    direct = _PYDIR.joinpath(*bouts).with_suffix(".py")
    if direct.is_file():
        return direct
    paquet = _PYDIR.joinpath(*bouts) / "__init__.py"
    return paquet if paquet.is_file() else None


def _imports_locaux(arbre: ast.Module) -> set[str]:
    out: set[str] = set()
    for n in ast.walk(arbre):
        if isinstance(n, ast.Import):
            out.update(a.name for a in n.names)
        elif isinstance(n, ast.ImportFrom) and n.module and not n.level:
            out.add(n.module)
            out.update("%s.%s" % (n.module, a.name) for a in n.names)
    return out


def _cause_du_fichier(chemin: Path) -> str | None:
    """La raison pour laquelle CE fichier est insellectionnable, ou `None`."""
    try:
        src = chemin.read_text(encoding="utf-8")
        arbre = ast.parse(src)
    except (OSError, SyntaxError, UnicodeDecodeError):
        #: illisible => on ne peut RIEN affirmer, donc on le joue (sens sur, et on le dit).
        return "source illisible -- aucune classification possible"
    for n in ast.walk(arbre):
        if not isinstance(n, ast.Call):
            continue
        f = n.func
        nom = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
        if nom in _APPELS_DE_BALAYAGE and _enumere_des_sources(n, nom):
            return ("BALAYAGE (`%s`) : les fichiers enumeres ne sont dans aucun graphe d'imports"
                    % nom)
        if nom in _APPELS_DE_SOUS_PROCESSUS and isinstance(f, ast.Attribute):
            racine = getattr(f.value, "id", "")
            if racine in ("subprocess", "sp"):
                return ("SOUS-PROCESSUS (`%s.%s`) : ce que le fils ouvre n'est trace ni par le "
                        "graphe ni par l'empreinte" % (racine, nom))
        if _balaye_par_git(n):
            return "BALAYAGE PAR GIT (`ls-files`) : meme angle mort que `rglob`"
    return None


def _litteraux(noeud) -> list:
    """Les chaines litterales portees par cet appel, arguments et mots-cles compris."""
    out = []
    for sous in ast.walk(noeud):
        if isinstance(sous, ast.Constant) and isinstance(sous.value, str):
            out.append(sous.value)
    return out


def _enumere_des_sources(appel, nom: str) -> bool:
    """`True` si ce balayage peut rendre des `.py`.

    ⚠ LE MOTIF EST LE DISCRIMINANT, et sans lui la classe explose : mesure du 2026-08-11, un
    critere par NOM D'APPEL seul rendait **289 insellectionnables sur 323** -- `gameconfig.glob`
    (donnees JSON) et un `--name-only` cite en PROSE suffisaient a contaminer toute la cloture.
    Un balayage de DONNEES est deja couvert par l'empreinte (`dirs`, granularite repertoire) ;
    seul celui qui rend des `.py` est aveugle au graphe d'imports."""
    if nom in ("walk", "iterdir", "scandir"):
        return True                      # sans motif : on ne peut pas exclure les `.py`
    return any(".py" in s for s in _litteraux(appel))


def _balaye_par_git(appel) -> bool:
    """`True` si cet appel demande a git la LISTE des fichiers.

    Le marqueur doit etre un ARGUMENT, jamais une occurrence dans le source : mesure du
    2026-08-11, chercher `ls-files` dans le texte brut classait `engine/battle_query.py`
    balayeur a cause d'une mention en commentaire."""
    return any(m in s for s in _litteraux(appel) for m in _MARQUEURS_GIT)


def classer(perimetre=None) -> tuple[dict, list]:
    """({test relatif -> (module accuse, cause)}, [tests selectionnables]).

    Le perimetre est DERIVE de `probe_457.candidate_files()` -- jamais enumere ici : c'est la
    propriete entiere de cette tranche."""
    if perimetre is None:
        perimetre = P457.candidate_files()
    insellectionnables: dict = {}
    selectionnables: list = []
    cache: dict = {}
    for rel in perimetre:
        chemin = _PYDIR / rel
        vus: set[Path] = set()
        pile = [chemin]
        cause = None
        accuse = None
        while pile and cause is None:
            f = pile.pop()
            if f in vus:
                continue
            vus.add(f)
            if f not in cache:
                cache[f] = _cause_du_fichier(f)
            if cache[f] is not None:
                cause, accuse = cache[f], f
                break
            try:
                arbre = ast.parse(f.read_text(encoding="utf-8"))
            except (OSError, SyntaxError, UnicodeDecodeError):
                continue
            for nom in _imports_locaux(arbre):
                cible = _module_local(nom)
                if cible is not None and cible not in vus:
                    pile.append(cible)
        if cause is None:
            selectionnables.append(rel)
        else:
            insellectionnables[rel] = (accuse.relative_to(_PYDIR).as_posix(), cause)
    return insellectionnables, selectionnables


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--liste", action="store_true",
                    help="un chemin par ligne (nodeid relatif a scripts/python), rien d'autre.")
    a = ap.parse_args(argv)

    ins, sel = classer()
    if a.liste:
        for rel in sorted(ins):
            print(rel)
        return 0

    total = len(ins) + len(sel)
    print("[935] perimetre offline DERIVE (`probe_457.candidate_files`) : %d fichier(s)" % total)
    print("[935] INSELECTIONNABLES : %d  |  selectionnables par `--since` : %d"
          % (len(ins), len(sel)))
    if not total:
        print("[935] perimetre VIDE -- ce n'est pas un verdict, c'est un montage en echec")
        return 99
    for rel in sorted(ins):
        accuse, cause = ins[rel]
        via = "" if accuse == rel else "  <- %s" % accuse
        print("    %-62s %s%s" % (rel, cause.split(" : ")[0], via))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
