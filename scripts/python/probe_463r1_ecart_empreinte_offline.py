#!/usr/bin/env python
"""#463-r1 -- CLIQUET : l'empreinte de `probe_457` couvre EXACTEMENT le perimetre offline.

CE QU'IL GARDE
--------------
UN SEUL fait, dans les DEUX sens :

  * `NON MESURE` -- un fichier de test offline RECENSE qui n'a pas d'entree dans
    `scripts/ratchets-457-footprints.json`. Il se rejoue TOUJOURS sous `--since` (une entree
    absente se lit << jamais mesure >>, #486-r15) et il prend le poids MAXIMUM connu dans
    `bins_of`, donc il deplace les vrais lourds ;
  * `FANTOME` -- une entree d'empreinte qui ne correspond a AUCUN fichier du perimetre. Le
    fichier a ete supprime, ou RENOMME -- typiquement en `_live.py`. Benin pour la selection,
    mais c'est la TRACE d'un renommage, et `--measure-missing` ne le purge pas (seul
    `--measure`, qui reecrit l'empreinte en entier, le fait).

LA CADENCE MESUREE, ET POURQUOI CE GISEMENT-LA EXISTE
------------------------------------------------------
Rien ne mesure automatiquement les poids d'un fichier de test offline NEUF : `--measure-missing`
est un geste EXPLICITE, et son oubli est SILENCIEUX. Le 2026-08-07, TROIS reouvertures en UNE
journee, toutes par nos propres livraisons -- 231->232 (`d9c430cb`), 232->233 (`94fd2b72`),
233->234 (`0010d088`). C'est donc notre CADENCE DE PORTAGE qui l'alimente, au meme titre que
`TARGETING_OPTIONS` et `ABILITY_ATTACK_TYPE`, et il etait le seul des trois sans cliquet.

⛔ CE QUE CE CLIQUET REFUSE DE FAIRE, ET LE CONTRE-CAS QUI L'INTERDIT
---------------------------------------------------------------------
IL NE MESURE PAS A LA PLACE DE L'HUMAIN. Le remede << evident >> -- lancer `--measure-missing`
tout seul sur le fichier manquant -- est FAUX, et le contre-cas date du MEME JOUR que les trois
reouvertures. Le 2026-08-07 au matin, le MEME ecart `N-1 / N` appelait la reponse INVERSE
(`40917cd0`) : le fichier n'etait pas offline, c'etait un test LIVE MAL NOMME, qu'il fallait
RENOMMER. L'avoir mesure aurait grave dans un fichier VERSIONNE une empreinte derivee d'un run
LIVE -- donc d'une selection etroite (le filet de `probe_457` deselectionne les items live avant
qu'ils ne s'executent) -- donc un FAUX VERT durable, exactement ce que le silence d'aujourd'hui
evite.

Le discriminant << ce fichier est-il offline ? >> N'EST PAS MECANISABLE : il porte sur l'INTENTION
de l'auteur. Ce cliquet ROUGIT, NOMME, DONNE UN INDICE LU, et REND LA MAIN. Il enonce les deux
issues et n'en choisit AUCUNE.

L'INDICE EST LU, PAS COMPTE -- LE PIEGE DU FILTRE
--------------------------------------------------
Un grep `live_session|build_runner|rpc` pour classer offline/live matche AUSSI LA PROSE : vecu sur
`test_524r1_bond_sous_effets_offline.py`, ou `rpc` apparaissait dans une CHAINE DE MESSAGE. Un
filtre qui COMPTE accuse donc a tort. Deux etages ici, et les deux DISENT sur quoi ils ont
matche :

  1. la RECLAMATION DE FIXTURE, lue dans la SIGNATURE (`ast`) : pytest resout une fixture par le
     NOM DU PARAMETRE, donc `def test_x(live_session)` est un fait, pas une correspondance de
     texte. `@pytest.mark.usefixtures("host")` est lu de meme. L'ensemble des fixtures LIVE est
     DERIVE des `conftest.py` (fermeture transitive depuis `probe_457.LIVE_FIXTURE_ROOT`), jamais
     une liste ecrite ici ;
  2. les autres occurrences sont classees par le TYPE DE TOKEN (`tokenize`) -- `NAME` (code),
     `STRING`, `COMMENT` -- et rendues avec leur ligne. Une occurrence en `STRING` est nommee
     PROSE et n'accuse personne.

PAS D'ALLOWLIST, PAS D'ECHAPPATOIRE -- ET C'EST UNE MESURE, PAS UN PARTI PRIS
------------------------------------------------------------------------------
#486-r15 a du poser une DETTE versionnee parce que l'obligation seche rendait `master` rouge sur
711 fichiers. Ici, l'ecart mesure sur `master` au 2026-08-07 est **0 manquant / 0 fantome** pour
234 fichiers : l'obligation seche est DEJA satisfaite, donc aucune dette n'est necessaire, et en
inventer une serait fabriquer d'avance le trou par lequel le gisement revient. Les deux gestes qui
eteignent ce rouge coutent quelques secondes ; une echappatoire ferait exactement ce que le
silence d'aujourd'hui fait.

TRI-ETAT (#471)
---------------
  0  : perimetre et empreinte coincident ;
  1  : au moins un `NON MESURE` ou un `FANTOME`, ou l'empreinte n'est pas au format attendu ;
  99 : RIEN n'a pu etre mesure (git muet, empreinte illisible/absente) -- ni un vert ni un rouge.

CE MODULE EST AUSSI LE FOYER DU RECENSEMENT OFFLINE
-----------------------------------------------------
Le perimetre etait DERIVE trois fois, separement : `probe_457.candidate_files` (ce que
`--measure-missing` joue), `loop_status.mesurer_empreinte` (le capteur du hook `Stop`), et ce
cliquet en aurait fait une QUATRIEME. Deux derivations d'un meme critere ouvrent un ecart
SILENCIEUX -- c'est ce que `probe_457._modules_du_graphe` documente deja pour le domaine du
graphe. `perimetre_offline` est donc LE foyer, et ses trois lecteurs l'importent.

Il reste LEGER a dessein (`json` / `ast` / `tokenize`, aucun `pytest`, aucun `repo_read`, et pas
meme un import de `probe_457` -- son contrat est LU dans son source, cf. `_contrat_de_probe_457`).
Mesure du 2026-08-07 : `import probe_457_offline_tests_green` coute **1,53 s** en process frais,
quand `loop_status` court sous les 3 s du hook `Stop`. Ce cliquet, lui, tient en **0,5 s** de
travail (import 0,27 s, contrat 0,015 s, empreinte 0,003 s) -- son poste dominant est le
`git ls-files`, qui varie de 0,19 a 0,66 s selon la contention sur le `.git/` partage entre
worktrees, donc le mur observe est de 1,3 a 2,9 s en campagne. C'est le cout de `probe_457` qui
interdit a `loop_status` d'importer le producteur, et c'est pour cela que le foyer vit ICI.

Usage :
    python probe_463r1_ecart_empreinte_offline.py
    python probe_463r1_ecart_empreinte_offline.py --verbose

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

# `ast`, `tokenize` et `argparse` sont importes PARESSEUSEMENT (34 ms mesures a eux trois) : ils
# ne servent QU'aux indices et au CLI, jamais au recensement. Or `loop_status` importe ce module
# et court sous les 3 s du hook `Stop`, budget deja serre (`gh` y prend 2,90 s -- #467-r6). Meme
# patron que `loop_status`, qui differe `urllib.request` pour la meme raison. `json` et
# `subprocess`, eux, restent en tete : ils portent le recensement, et `loop_status` les a deja.

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]

#: Repertoire des tests. MEME valeur que `probe_457.TESTS_DIR`, qui la prend ICI (foyer unique).
#: PATHSPEC DE REPERTOIRE et non glob : `git ls-files <dir>` descend recursivement, sans
#: semantique `**` a deviner -- le vice de #457-r5, ou `**/` exigeait un niveau intermediaire et
#: rendait invisibles les 23 fichiers poses DIRECTEMENT dans `tests/`.
TESTS_DIR = "scripts/python/tests"

#: Prefixe retire des chemins rendus : l'empreinte est clee sur des chemins relatifs au ROOTDIR
#: de `pytest.ini` (`scripts/python`), pas a la racine du depot.
PREFIXE_ROOTDIR = "scripts/python/"

#: Le fichier d'empreinte, VERSIONNE.
EMPREINTE = "scripts/ratchets-457-footprints.json"

#: rc << RIEN N'A ETE MESURE >>. Meme convention que `probe_457.EX_NON_MESURE` et
#: `scripts/ratchets-bg.ps1` : un appelant DOIT le lire << pas de verdict sur le depot >>,
#: jamais comme un rouge de gisement, jamais comme un vert.
EX_NON_MESURE = 99

#: Combien de fichiers en ecart sont DETAILLES avant de resumer. Un cliquet qui deverse 234 blocs
#: d'indices ne se lit pas ; le COMPTE, lui, reste exact et le reste est nomme en une ligne.
PLAFOND_DETAIL = 12


class MontageImpossible(RuntimeError):
    """Le cliquet n'a pas pu CONSTITUER l'objet de sa mesure. Rend `EX_NON_MESURE`, JAMAIS 1.

    Meme critere ETROIT que `probe_457.MontageImpossible` : ne leve que sur une panne de ce dont
    ce cliquet depend et qui N'EST PAS le depot -- `git` injoignable, empreinte illisible. Un
    `git ls-files` qui repond rc=0 avec une liste VIDE n'est PAS une panne : c'est une reponse
    valide, donc un fait sur le depot, et le garde anti-effondrement le traite en ROUGE.
    """


# --------------------------------------------------------------------- LE FOYER DU RECENSEMENT

def est_fichier_de_test(nom: str) -> bool:
    """Convention de collecte de pytest, laissee au DEFAUT par `pytest.ini` (pas de `python_files`).

    Les DEUX formes comptent. `*_test.py` n'existe pas dans le depot aujourd'hui, mais un
    perimetre DERIVE doit couvrir ce que pytest COLLECTE, pas ce qui se trouve exister -- sinon le
    prochain fichier ainsi nomme rouvre exactement le trou qu'on vient de fermer (#457-r5).
    """
    return nom.endswith(".py") and (nom.startswith("test_") or nom.endswith("_test.py"))


def perimetre_offline(sortie_ls_files: str) -> list:
    """Les fichiers de test NON `_live.py`, en chemins relatifs a `scripts/python`.

    FONCTION PURE : elle prend le TEXTE rendu par `git ls-files scripts/python/tests` et ne
    touche ni au disque ni a git. C'est ce qui permet a ses trois lecteurs de garder CHACUN sa
    propre facon d'appeler git -- `probe_457` par son foyer `_git` (qui leve `MontageImpossible`),
    `loop_status` par son `Sources.git` (qui porte un cache TTL et un tri-etat) -- tout en
    partageant le CRITERE, qui est la seule chose qui doive etre unique.

    Le suffixe `_live.py` est le critere de perimetre de `probe_457`, et il est DECLARATIF : un
    critere plus fin (la cloture de fixtures) a ete essaye puis REFUTE PAR MESURE -- il rendait
    153 fichiers << offline >> dont des dizaines de `*_live.py` qui montent leur runner a la main.
    """
    out = []
    for ligne in sortie_ls_files.splitlines():
        rel = ligne.strip()
        if not rel or rel.endswith("_live.py") or not rel.startswith(PREFIXE_ROOTDIR):
            continue
        if not est_fichier_de_test(rel.rsplit("/", 1)[-1]):
            continue
        out.append(rel[len(PREFIXE_ROOTDIR):])
    return sorted(out)


def ventiler(perimetre, entrees) -> dict:
    """L'ecart, DANS LES DEUX SENS. `{"manquants": [...], "fantomes": [...]}`.

    Le sens `perimetre \\ empreinte` est le gisement (un test neuf jamais mesure). Le sens
    inverse, `empreinte \\ perimetre`, est celui qu'un simple COMPTE ne peut pas voir : le capteur
    de `loop_status` rendait `couverts = len([r for r in perimetre if r in entrees])`, donc une
    empreinte portant 300 cles dont 66 fantomes pour un perimetre de 234 integralement couvert
    affichait `234/234` et se taisait. Compter une INTERSECTION ne montre jamais ce qui deborde.
    """
    connues = set(entrees or ())
    dans_le_perimetre = set(perimetre)
    return {
        "manquants": [r for r in perimetre if r not in connues],
        "fantomes": sorted(r for r in connues if r not in dans_le_perimetre),
    }


# ------------------------------------------------------------------------------ LECTURE DE GIT

def _git(args: list, quoi: str, racine=None):
    """FOYER UNIQUE des appels a `git` de ce cliquet. Toute panne -> `MontageImpossible` (#471).

    Un `CalledProcessError` nu sortirait en rc=1, indistinguable d'un ecart reel -- c'est le
    crash EXACT mesure le 2026-08-04 sur `probe_457:s3` (rc 128 lu comme << un test est rouge >>).
    """
    cmd = ["git", "-C", str(racine or ROOT), *args]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
    except OSError as exc:
        raise MontageImpossible("`git %s` n'a pas pu etre lance (%s: %s) -- %s"
                                % (" ".join(args), type(exc).__name__, exc, quoi)) from exc
    if proc.returncode != 0:
        raise MontageImpossible("`git %s` a rendu rc=%d -- %s. stderr: %s"
                                % (" ".join(args), proc.returncode, quoi,
                                   (proc.stderr or "").strip()[:300]))
    return proc.stdout


def recenser(racine=None) -> list:
    """Le perimetre offline du depot, DERIVE de `git ls-files` (jamais une allowlist)."""
    return perimetre_offline(_git(["ls-files", TESTS_DIR],
                                  "impossible d'enumerer le perimetre des tests", racine))


def lire_empreinte(racine=None) -> dict:
    """L'empreinte VERSIONNEE. Illisible ou absente -> `MontageImpossible`, jamais `{}`.

    Un `{}` silencieux ferait rendre << 234 fichiers non mesures >> pour une panne de lecture :
    un rouge de gisement pour un echec de MONTAGE, soit le patron repare par #471.
    """
    chemin = (Path(racine) if racine else ROOT) / EMPREINTE
    try:
        return json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise MontageImpossible("`%s` illisible (%s: %s) -- l'ecart n'est pas calculable"
                                % (EMPREINTE, type(exc).__name__, str(exc)[:120])) from exc


#: Le producteur de l'empreinte, dont ce cliquet LIT le contrat (jamais ne le recopie).
SOURCE_457 = "probe_457_offline_tests_green.py"

#: Les deux constantes du contrat : la version de format que `probe_457` ECRIT, et la fixture
#: RACINE du monde live dont l'indice derive la fermeture.
CONTRAT_457 = ("FORMAT_EMPREINTE", "LIVE_FIXTURE_ROOT")


def _contrat_de_probe_457(racine=None) -> tuple:
    """`(FORMAT_EMPREINTE, LIVE_FIXTURE_ROOT)`, LUS DANS LE SOURCE du producteur.

    POURQUOI PAS UN IMPORT, ALORS QUE C'EST PLUS FIDELE. Mesure du 2026-08-07 : `import
    probe_457_offline_tests_green` coute **1,53 s** en process frais (il tire `pytest` et
    `repo_read`), pour DEUX litteraux. Le cliquet entier tombe de **2,8 s a ~0,5 s** en le
    retirant, et sa contre-epreuve n'a plus a recopier toute la cloture du producteur dans son
    depot jetable. Un cliquet cher se fait desarmer -- c'est la lecon de #457-r6 et de #486-r5.

    POURQUOI PAS UNE RECOPIE NON PLUS : une constante recopiee derive en silence. Ici la source
    de verite reste le FICHIER de `probe_457` ; on en extrait la valeur par `ast`, ce qui est
    DERIVE, pas duplique. Meme patron que `probe_467r4`, qui confronte le contrat de
    `loop_status` au CODE SOURCE du host plutot qu'a une liste ecrite.

    LA FRAGILITE EST NOMMEE, JAMAIS SILENCIEUSE : si l'une des deux cesse d'etre un litteral au
    niveau module, l'extraction leve `MontageImpossible` (rc 99, << je n'ai pas pu lire le
    contrat >>) au lieu de retomber sur une valeur devinee. Et
    `test_463r1_ecart_empreinte_offline` confronte ce qui est EXTRAIT a ce que l'import REEL
    rend -- c'est le cran qui interdit a cette lecture de mentir.
    """
    import ast
    chemin = (Path(racine) if racine else ROOT) / PREFIXE_ROOTDIR / SOURCE_457
    try:
        arbre = ast.parse(chemin.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError) as exc:
        raise MontageImpossible("`%s` illisible (%s: %s) -- le contrat de l'empreinte n'a pas pu "
                                "etre lu" % (SOURCE_457, type(exc).__name__,
                                             str(exc)[:120])) from exc
    lus: dict = {}
    for noeud in arbre.body:
        if not isinstance(noeud, ast.Assign) or not isinstance(noeud.value, ast.Constant):
            continue
        for cible in noeud.targets:
            if isinstance(cible, ast.Name) and cible.id in CONTRAT_457:
                lus[cible.id] = noeud.value.value
    absentes = [n for n in CONTRAT_457 if n not in lus]
    if absentes:
        raise MontageImpossible(
            "`%s` ne porte plus %s comme litteral(aux) de module -- le contrat de l'empreinte "
            "n'est plus lisible sans importer le producteur (1,53 s). Rendre la constante "
            "litterale, ou basculer ce cliquet sur un import." % (SOURCE_457, ", ".join(absentes)))
    return lus["FORMAT_EMPREINTE"], lus["LIVE_FIXTURE_ROOT"]


# ------------------------------------------------------------- L'INDICE : LU, JAMAIS COMPTE

def fixtures_live(racine=None) -> set:
    """Les fixtures dont la cloture atteint la RACINE du monde live, DERIVEES des `conftest.py`.

    Pytest resout une fixture par le NOM DU PARAMETRE et sa cloture est TRANSITIVE : un test qui
    reclame `live_runner` -> `build_runner` -> `host` porte les trois. On reconstruit ce graphe
    statiquement (`ast`) sur les `conftest.py` VERSIONNES, puis on prend la fermeture depuis la
    racine.

    POURQUOI PAS UNE LISTE ECRITE ICI : parce qu'une fixture live ajoutee demain n'y serait pas,
    et que l'indice se degraderait EN SILENCE -- le vice meme que ce cliquet existe pour fermer.
    Rendre l'ensemble VIDE est possible (aucun conftest lisible) ; l'appelant le DIT alors, au
    lieu de conclure << aucun indice live >>.
    """
    import ast
    racine = Path(racine) if racine else ROOT
    graphe: dict = {}
    for ligne in _git(["ls-files", "scripts/python"],
                      "impossible d'enumerer les conftest", racine).splitlines():
        rel = ligne.strip()
        if not rel.endswith("/conftest.py"):
            continue
        try:
            arbre = ast.parse((racine / rel).read_text(encoding="utf-8"))
        except (OSError, SyntaxError, UnicodeDecodeError):
            continue
        for noeud in ast.walk(arbre):
            if not isinstance(noeud, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not any("fixture" in ast.dump(d) for d in noeud.decorator_list):
                continue
            params = [a.arg for a in noeud.args.args] + [a.arg for a in noeud.args.kwonlyargs]
            graphe.setdefault(noeud.name, set()).update(params)

    # La RACINE entre TOUJOURS, meme si aucun conftest n'a pu etre lu : c'est elle que
    # `probe_457` interroge sur `item.fixturenames`, et un test peut la reclamer directement.
    _, racine_live = _contrat_de_probe_457(racine)
    vivantes = {racine_live}
    change = True
    while change:
        change = False
        for nom, params in graphe.items():
            if nom not in vivantes and (params & vivantes):
                vivantes.add(nom)
                change = True
    return vivantes


def reclamations_live(source: str, live: set) -> list:
    """Les fixtures LIVE reclamees dans la SIGNATURE d'un test. `[(fonction, param, ligne)]`.

    C'est un FAIT, pas une correspondance de texte : pytest injecte la fixture dont le nom est
    celui du parametre. `@pytest.mark.usefixtures("host")` est la seconde forme et compte pareil.
    """
    import ast
    try:
        arbre = ast.parse(source)
    except (SyntaxError, ValueError):
        return []
    trouves = []
    for noeud in ast.walk(arbre):
        if not isinstance(noeud, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for a in list(noeud.args.args) + list(noeud.args.kwonlyargs):
            if a.arg in live:
                trouves.append((noeud.name, a.arg, a.lineno))
        for deco in noeud.decorator_list:
            if not isinstance(deco, ast.Call):
                continue
            if "usefixtures" not in ast.dump(deco.func):
                continue
            for arg in deco.args:
                if isinstance(arg, ast.Constant) and arg.value in live:
                    trouves.append((noeud.name, "usefixtures(%s)" % arg.value, deco.lineno))
    return trouves


def modules_freres_importes(source: str) -> list:
    """Les modules de `scripts/python` que ce fichier importe. SECOND indice, brut et non classe.

    Il existe parce que le PREMIER a un angle mort MESURE (cf. `angle_mort_de_l_indice`) : un
    fichier peut monter son runner par un PROBE qu'il importe, sans jamais nommer de fixture.
    On les LISTE, on ne les classe pas -- decider si `probe_500_foul_infusion` parle au host
    demanderait la fermeture d'imports de l'arbre (29,5 s mesurees), et ce serait de nouveau
    trancher a la place du lecteur.
    """
    import ast
    try:
        arbre = ast.parse(source)
    except (SyntaxError, ValueError):
        return []
    noms = set()
    for n in ast.walk(arbre):
        if isinstance(n, ast.Import):
            noms.update(a.name.split(".")[0] for a in n.names)
        elif isinstance(n, ast.ImportFrom) and n.module and n.level == 0:
            noms.add(n.module.split(".")[0])
    return sorted(n for n in noms if (PYDIR / (n + ".py")).exists())


def angle_mort_de_l_indice(racine=None) -> tuple:
    """`(sans_reclamation, total_live)` sur les `*_live.py` du depot. RE-DERIVE, jamais cite.

    LA MESURE QUI INTERDIT DE CONCLURE. << Aucune fixture live reclamee >> se lit spontanement
    << donc le fichier est offline >>. C'est FAUX, et le chiffre le dit : le 2026-08-07,
    **90 des 513** `*_live.py` du depot (17,5 %) ne reclament AUCUNE fixture -- ils montent leur
    runner a la main, ou par une fixture LOCALE qui appelle un probe. C'est la meme limite qui a
    fait REFUTER la cloture de fixtures comme critere de perimetre pour `probe_457`.

    Ce compte est calcule A L'EXECUTION et imprime a cote de l'indice : cite en dur, il se
    perimerait, et un lecteur y verrait une garantie la ou il n'y a qu'une frequence.
    """
    racine = Path(racine) if racine else ROOT
    live = fixtures_live(racine)
    total, sans = 0, 0
    for ligne in _git(["ls-files", TESTS_DIR],
                      "impossible d'enumerer les tests live", racine).splitlines():
        rel = ligne.strip()
        if not rel.endswith("_live.py"):
            continue
        total += 1
        try:
            src = (racine / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if not reclamations_live(src, live):
            sans += 1
    return sans, total


def occurrences_classees(source: str, live: set) -> list:
    """Toute autre occurrence d'un nom LIVE, CLASSEE PAR TYPE DE TOKEN. `[(classe, ligne, extrait)]`

    LE PIEGE DU FILTRE, traite : un grep matche la PROSE. Mesure sur
    `test_524r1_bond_sous_effets_offline.py` -- `rpc` y vivait dans une CHAINE DE MESSAGE, et un
    filtre qui COMPTE aurait accuse le fichier d'etre live. On rend donc `STRING` / `COMMENT`
    (prose) ou `NAME` (code) avec le numero de ligne, pour que le lecteur LISE la correspondance.
    """
    import io
    import re
    import tokenize
    # BORNES DE MOT dans la prose : sans elles, `host` matcherait `ghost` et `hostile`, et
    # l'indice bruiterait exactement la ou il doit rassurer. Les `NAME`, eux, sont deja des
    # jetons entiers -- l'egalite suffit.
    motif = re.compile(r"\b(%s)\b" % "|".join(re.escape(n) for n in sorted(live))) if live else None
    vus = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(source).readline):
            if tok.type == tokenize.NAME and tok.string in live:
                vus.append(("NAME", tok.start[0], tok.line.strip()[:70]))
            elif tok.type in (tokenize.STRING, tokenize.COMMENT) and motif \
                    and motif.search(tok.string):
                vus.append(("STRING" if tok.type == tokenize.STRING else "COMMENT",
                            tok.start[0], tok.line.strip()[:70]))
    except (tokenize.TokenError, IndentationError, SyntaxError, UnicodeDecodeError):
        return []
    return vus


# ------------------------------------------------------------------------------------- RENDU

_ISSUE_MESURER = ("(a) le fichier est REELLEMENT offline -> le MESURER :\n"
                  "            cd scripts/python ; $env:TACTICUS_ALLOW_RATCHETS=1 ; "
                  "python probe_457_offline_tests_green.py --measure-missing")
_ISSUE_RENOMMER = ("(b) il monte un runner ou reclame une fixture live -> le RENOMMER en "
                   "`*_live.py`\n            (contre-cas `40917cd0` : le mesurer graverait une "
                   "empreinte derivee d'un run LIVE, donc un FAUX VERT)")


def _detailler(rel: str, live: set, racine, verbeux: bool) -> None:
    """Imprime l'INDICE d'un fichier NON MESURE, sans jamais conclure a sa place."""
    chemin = (Path(racine) if racine else ROOT) / PREFIXE_ROOTDIR / rel
    try:
        source = chemin.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print("      indice : ILLISIBLE (%s) -- aucun indice, a toi de lire le fichier"
              % type(exc).__name__)
        return
    if not live:
        print("      indice : PAS MESURE -- aucune fixture live n'a pu etre derivee des conftest")
        return

    reclams = reclamations_live(source, live)
    if reclams:
        print("      indice : %d fonction(s) RECLAMENT une fixture LIVE (lu dans la SIGNATURE) :"
              % len(reclams))
        for nom, param, ligne in reclams[:5]:
            print("                 %s(%s)  ligne %d" % (nom[:44], param, ligne))
        return

    autres = occurrences_classees(source, live)
    prose = [o for o in autres if o[0] != "NAME"]
    code = [o for o in autres if o[0] == "NAME"]
    print("      indice : AUCUNE fonction ne reclame de fixture live.")
    freres = modules_freres_importes(source)
    if freres:
        print("                 mais il importe %d module(s) de `scripts/python` : %s"
              % (len(freres), ", ".join(freres[:6])))
        print("                 -> un fichier peut monter son runner PAR un probe qu'il importe.")
    if not autres:
        print("                 et aucune occurrence des noms live dans le fichier.")
    else:
        print("                 %d occurrence(s) hors signature : %d en PROSE (STRING/COMMENT), "
              "%d en NAME." % (len(autres), len(prose), len(code)))
        for classe, ligne, extrait in (autres if verbeux else autres[:3]):
            print("                 ligne %-5d %-7s | %s" % (ligne, classe, extrait))
        if prose and not code:
            print("                 -> toutes en PROSE : ce n'est PAS un indice de test live "
                  "(cf. `test_524r1_bond_sous_effets_offline.py`).")


def rapporter(ecart: dict, perimetre: list, live: set, racine=None, verbeux: bool = False) -> None:
    """La sortie du cliquet. NOMME, DONNE UN INDICE, et REFUSE DE TRANCHER."""
    manquants, fantomes = ecart["manquants"], ecart["fantomes"]
    print("[463-r1] perimetre offline : %d fichier(s) ; empreinte : %d NON MESURE(S), %d FANTOME(S)"
          % (len(perimetre), len(manquants), len(fantomes)))
    if live:
        print("[463-r1] fixtures LIVE derivees des conftest : %d (%s)"
              % (len(live), ", ".join(sorted(live)[:6])))

    for rel in manquants[:PLAFOND_DETAIL]:
        print("")
        print("  NON MESURE  %s" % rel)
        _detailler(rel, live, racine, verbeux)
    if len(manquants) > PLAFOND_DETAIL:
        print("")
        print("  ... et %d autre(s) NON MESURE(S), non detailles ici :"
              % (len(manquants) - PLAFOND_DETAIL))
        for rel in manquants[PLAFOND_DETAIL:]:
            print("      %s" % rel)

    if manquants:
        print("")
        # L'ANGLE MORT, MESURE ET DIT. Sans lui, << aucune fixture reclamee >> se lirait
        # << donc offline >>, et le cliquet aurait TRANCHE en creux -- par une absence de
        # preuve presentee comme une preuve d'absence.
        try:
            sans, total = angle_mort_de_l_indice(racine)
            if total:
                print("  ATTENTION -- L'ABSENCE DE RECLAMATION N'EST PAS UNE PREUVE D'OFFLINE : "
                      "%d des %d `*_live.py`" % (sans, total))
                print("    de ce depot (%.1f %%) n'en reclament AUCUNE non plus -- ils montent "
                      "leur runner" % (100.0 * sans / total))
                print("    a la main ou via une fixture LOCALE. C'est la limite qui a fait "
                      "REFUTER la cloture")
                print("    de fixtures comme critere de perimetre pour `probe_457`. LIS le "
                      "fichier.")
                print("")
        except MontageImpossible:
            print("  (angle mort de l'indice : PAS MESURE -- git muet)")
            print("")
        print("  DEUX ISSUES, ET CE CLIQUET N'EN CHOISIT AUCUNE -- le discriminant")
        print("  << ce fichier est-il offline ? >> porte sur l'INTENTION, il n'est pas mecanisable :")
        print("        %s" % _ISSUE_MESURER)
        print("        %s" % _ISSUE_RENOMMER)

    for rel in fantomes[:PLAFOND_DETAIL]:
        print("")
        print("  FANTOME     %s" % rel)
        print("      mesure dans l'empreinte, ABSENT du perimetre offline : supprime, ou RENOMME")
        print("      (un `_live.py` sort du perimetre). `--measure-missing` ne purge PAS les")
        print("      fantomes ; seul `--measure`, qui reecrit l'empreinte en entier, le fait.")
    if len(fantomes) > PLAFOND_DETAIL:
        print("")
        print("  ... et %d autre(s) FANTOME(S) : %s"
              % (len(fantomes) - PLAFOND_DETAIL, ", ".join(fantomes[PLAFOND_DETAIL:][:8])))


# -------------------------------------------------------------------------------- POINT D'ENTREE

def mesurer(racine=None) -> dict:
    """La mesure complete. Leve `MontageImpossible` si elle n'a pas pu etre CONSTITUEE."""
    perimetre = recenser(racine)
    empreinte = lire_empreinte(racine)
    attendu, _ = _contrat_de_probe_457(racine)
    format_lu = empreinte.get("_format")
    entrees = (empreinte.get("par_test") or {}) if format_lu == attendu else {}
    return {"perimetre": perimetre, "format_lu": format_lu, "format_attendu": attendu,
            "ecart": ventiler(perimetre, entrees)}


def _run(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--verbose", action="store_true",
                    help="Detaille TOUTES les occurrences classees, pas seulement les 3 "
                         "premieres.")
    args = ap.parse_args(argv)

    m = mesurer()
    perimetre = m["perimetre"]

    if not perimetre:
        # Reponse VALIDE de git avec une liste vide = fait sur le depot, donc un ROUGE
        # d'effondrement de perimetre -- surtout pas un << rien a signaler >>. Meme frontiere que
        # `probe_457` (`FAIL shard VIDE`).
        print("[463-r1] ROUGE : le perimetre offline est VIDE -- `%s` ne designe aucun fichier de"
              " test. Ce n'est pas une absence d'ecart, c'est un perimetre effondre." % TESTS_DIR)
        return 1

    if m["format_lu"] != m["format_attendu"]:
        print("[463-r1] ROUGE : empreinte au format %s, attendu %d."
              % (m["format_lu"], m["format_attendu"]))
        print("[463-r1] L'ecart PAR FICHIER n'est pas calculable sur un format inconnu -- et")
        print("[463-r1] `probe_457 --since` refuse deja de s'en servir, donc il rejoue TOUT.")
        print("[463-r1] Regenerer : cd scripts/python ; $env:TACTICUS_ALLOW_RATCHETS=1 ; "
              "python probe_457_offline_tests_green.py --measure")
        return 1

    ecart = m["ecart"]
    if not ecart["manquants"] and not ecart["fantomes"]:
        print("[463-r1] VERDICT: PASS -- %d fichier(s) offline, tous mesures, aucun fantome."
              % len(perimetre))
        return 0

    # Les indices ne sont derives QUE s'il y a un ecart a expliquer : en regime normal ce cliquet
    # ne lit aucun fichier de test.
    live = fixtures_live()
    rapporter(ecart, perimetre, live, verbeux=args.verbose)
    print("")
    print("[463-r1] VERDICT: FAIL -- %d NON MESURE(S), %d FANTOME(S)."
          % (len(ecart["manquants"]), len(ecart["fantomes"])))
    print("[463-r1] AUCUNE allowlist, AUCUNE echappatoire : les deux gestes ci-dessus coutent")
    print("[463-r1] quelques secondes, et l'ecart sur `master` etait de 0 quand ce cliquet a ete")
    print("[463-r1] ecrit -- une exception ne ferait que rouvrir le gisement qu'il ferme.")
    return 1


def main(argv=None) -> int:
    """TROIS issues, jamais deux (#471) : 0 = pas d'ecart, 1 = ecart, `EX_NON_MESURE` = montage."""
    try:
        return _run(argv)
    except MontageImpossible as exc:
        print("[463-r1] MONTAGE EN ECHEC : %s" % exc)
        print("[463-r1] RIEN n'a ete mesure. Ce n'est PAS un verdict sur le depot -- ni un rouge")
        print("[463-r1] de gisement, ni un vert.")
        print("[463-r1] rc=%d" % EX_NON_MESURE)
        return EX_NON_MESURE


if __name__ == "__main__":
    sys.exit(main())
