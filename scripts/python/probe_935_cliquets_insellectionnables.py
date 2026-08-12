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

⚠ L'ANGLE MORT QUE CE PROBE MESURAIT EST FERME (#935-r1). `impacted_files` porte desormais un
TROISIEME axe : l'empreinte enregistre les `.py` lus APPLICATIVEMENT (discriminant pris a
l'ECRITURE, sur la frame appelante) et les apparie aux `.py` du diff. Mesure sur les memes 13 cas
temoins : **6 manques -> 1**, et **0** une fois l'entree du cas SOUS-TRAITANT re-mesuree ; perimetre
moyen retenu **74,8 % -> 79,9 %**. Ce probe garde donc son role de MESURE de la classe -- et il est
lui-meme CONFRONTE, cf. ci-dessous. Detail : `docs/rl/case-935-r1-axe-py-de-l-empreinte.md`.

⚠ SUR-APPROXIMATION ASSUMEE, et dans le sens SUR : un module qui appelle `glob` sur un repertoire
de DONNEES (pas de `.py`) est classe balayeur alors que l'empreinte le couvrirait. Le prix est du
temps de test ; le prix de l'erreur inverse est un rouge de `master` que personne ne voit.
⚠ ET LE COMPTE IMPRIME N'ETAIT PAS UN GARDE-FOU. Cette doc disait << une derive de l'approximation
se voit >> : personne ne lisait le compte, et rien ne rougissait -- le vice exact de `probe_181`
avant #430. La CONTRE-EPREUVE vit depuis #935-r1 dans `probe_935r1_contre_epreuve_classes.py`, qui
oppose cette classe DEDUITE a l'empreinte MESUREE. Elle a trouve **19 faux negatifs** a son premier
passage (17 `inspect.getsource`, 1 import DYNAMIQUE qui cassait la cloture, 1
`Path(MODULE.__file__).read_text()`) -- tous couverts depuis, la classe passant de 160/175 a
180/155.

Usage (depuis `scripts/python`) :

    python probe_935_cliquets_insellectionnables.py            # la liste + les causes
    python probe_935_cliquets_insellectionnables.py --liste    # un chemin par ligne, pour un pipe

ASCII only (console cp1252). 100 % OFFLINE : aucun runner, aucun RPC.
"""
from __future__ import annotations

import argparse
import ast
import functools
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

#: LIRE LE SOURCE D'UN OBJET DEJA IMPORTE (#935-r1). Aucune ENUMERATION n'est en jeu, donc les
#: criteres ci-dessus etaient structurellement aveugles -- et c'est la forme la plus REPANDUE du
#: gisement : la contre-epreuve (`probe_935r1_contre_epreuve_classes.py`) a trouve **19** faux
#: negatifs a son premier passage, dont **17** de cette seule forme (`inspect.getsource(...)`).
#: L'arete est reelle : le test change d'avis quand le CORPS de la fonction lue change, ce qu'aucun
#: `import` ne dit -- il dit seulement que le module est charge.
_APPELS_DE_LECTURE_DE_SOURCE = {"getsource", "getsourcelines", "getsourcefile", "findsource",
                                "getfile", "getmodule", "unparse"}

#: Appels qui LISENT un fichier NOMME. Retenus SEULEMENT si un litteral de l'appel porte `.py` --
#: sans ce filtre, tout `read_text` de donnees contaminerait la classe (meme arbitrage que
#: `_enumere_des_sources`).
_APPELS_DE_LECTURE = {"read_text", "read_bytes", "open", "read"}

#: La marque d'un balayage delegue a git plutot qu'au systeme de fichiers.
_MARQUEURS_GIT = ("ls-files",)


@functools.lru_cache(maxsize=None)
def _module_local(nom: str) -> Path | None:
    """Le fichier de `scripts/python/**` que designe ce nom de module importe, ou `None`.

    MEMOISE : deux `stat` par nom, et les memes noms reviennent a chaque test de la cloture."""
    bouts = nom.split(".")
    direct = _PYDIR.joinpath(*bouts).with_suffix(".py")
    if direct.is_file():
        return direct
    paquet = _PYDIR.joinpath(*bouts) / "__init__.py"
    return paquet if paquet.is_file() else None


def _imports_locaux(arbre: ast.Module) -> set[str]:
    """Les noms de modules que ce fichier charge -- `import`, `from`, ET `import_module` (#935-r1).

    L'import DYNAMIQUE cassait la cloture en silence : `test_519_comptes_derives_offline.py` charge
    `probe_519_comptes_de_table` par `importlib.import_module("...")`, donc la remontee s'arretait
    la et le balayage du probe restait invisible. C'est un faux negatif trouve par la
    contre-epreuve, pas une precaution."""
    out: set[str] = set()
    for n in ast.walk(arbre):
        if isinstance(n, ast.Import):
            out.update(a.name for a in n.names)
        elif isinstance(n, ast.ImportFrom) and n.module and not n.level:
            out.add(n.module)
            out.update("%s.%s" % (n.module, a.name) for a in n.names)
        elif isinstance(n, ast.Call):
            f = n.func
            nom = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
            if nom in ("import_module", "__import__") and n.args:
                a0 = n.args[0]
                if isinstance(a0, ast.Constant) and isinstance(a0.value, str):
                    out.add(a0.value)
    return out


#: MEMOISATION DE L'ARBRE PARSE (#935-r1). `classer` remonte la cloture d'imports de CHAQUE test :
#: `_cause_du_fichier` etait deja cachee, mais l'`ast.parse` du meme module etait REFAIT une fois
#: par test qui l'atteint. Mesure : 79,0 s -> 6,3 s sur le perimetre entier (335 fichiers), soit
#: 12,5x. C'est la lecon de #941-r2 : le discriminant n'est pas << combien de VERDICTS >> mais
#: << combien d'APPELS >>. Cle = le chemin RESOLU ; la valeur ne depend que du CONTENU du fichier,
#: donc le cache ne fige aucun verdict -- il fige un parse.
_IMPORTS_CACHE: dict = {}


def _imports_du_fichier(chemin: Path) -> set[str]:
    """Les noms de modules importes par ce fichier, MEMOISES par chemin."""
    cle = str(chemin)
    if cle not in _IMPORTS_CACHE:
        try:
            _IMPORTS_CACHE[cle] = _imports_locaux(ast.parse(chemin.read_text(encoding="utf-8")))
        except (OSError, SyntaxError, UnicodeDecodeError):
            _IMPORTS_CACHE[cle] = set()
    return _IMPORTS_CACHE[cle]


def _cause_du_fichier(chemin: Path) -> str | None:
    """La raison pour laquelle CE fichier est insellectionnable, ou `None`."""
    try:
        src = chemin.read_text(encoding="utf-8")
        arbre = ast.parse(src)
    except (OSError, SyntaxError, UnicodeDecodeError):
        #: illisible => on ne peut RIEN affirmer, donc on le joue (sens sur, et on le dit).
        return "source illisible -- aucune classification possible"
    noms_py = _noms_lies_a_un_py(arbre)
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
        if nom in _APPELS_DE_LECTURE_DE_SOURCE and isinstance(f, ast.Attribute):
            if getattr(f.value, "id", "") in ("inspect", "ast", "insp"):
                return ("LECTURE DE SOURCE (`%s`) : le verdict depend du CORPS lu, pas de "
                        "l'import" % nom)
        if nom in _APPELS_DE_LECTURE and _lit_un_py_nomme(n, noms_py):
            return ("LECTURE D'UN `.py` NOMME (`%s`) : le fichier est ouvert comme DONNEE, aucun "
                    "import ne le revele" % nom)
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


def _noms_lies_a_un_py(arbre) -> set:
    """Les variables dont la VALEUR porte un litteral de chemin `.py`.

    Le chemin et sa lecture sont presque toujours DEUX instructions -- `p = _PYDIR / "engine" /
    ... / "normal.py"` puis `p.read_text(...)`. Un critere qui exige le litteral DANS l'appel les
    rate tous les deux, et c'est un faux negatif mesure (`test_419r1tr14r4r2r1r1`). On ne fait pas
    de dataflow : une liaison SIMPLE de nom suffit a couvrir la forme reelle."""
    out: set = set()
    for n in ast.walk(arbre):
        if not isinstance(n, (ast.Assign, ast.AnnAssign)) or n.value is None:
            continue
        if not any(isinstance(c, ast.Constant) and isinstance(c.value, str)
                   and c.value.endswith(".py") for c in ast.walk(n.value)):
            continue
        cibles = n.targets if isinstance(n, ast.Assign) else [n.target]
        out.update(t.id for t in cibles if isinstance(t, ast.Name))
    return out


def _lit_un_py_nomme(appel, noms_py: set) -> bool:
    """`True` si cette lecture porte sur un `.py` DESIGNE -- litteral, nom lie, ou `__file__`.

    `Path(MODULE.__file__).read_text()` est la troisieme forme, et elle ne porte AUCUN litteral :
    le chemin vient du module deja importe. L'arete reste invisible du graphe -- importer un module
    ne dit pas qu'on depend de son TEXTE."""
    if any(s.endswith(".py") for s in _litteraux(appel)):
        return True
    for sous in ast.walk(appel):
        if isinstance(sous, ast.Attribute) and sous.attr == "__file__":
            return True
        if isinstance(sous, ast.Name) and sous.id in noms_py:
            return True
    return False


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
            # `sorted` : `_imports_locaux` rend un SET, dont l'ordre d'iteration depend de
            # `PYTHONHASHSEED`. La CLASSE ne changeait pas, mais le module ACCUSE oui -- mesure du
            # 2026-08-12, 20 lignes sur 160 designaient un autre module d'un run a l'autre. Un
            # probe dont la sortie bouge sans que rien ne bouge n'est pas confrontable.
            for nom in sorted(_imports_du_fichier(f)):
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
