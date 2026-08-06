"""#486-r12 -- LE DECLENCHEUR d'un cliquet : ce qui doit changer pour qu'il change d'avis.

LA QUESTION, ET POURQUOI ELLE NE SE DERIVE PAS
-----------------------------------------------
`scripts/ratchets.ps1` porte ~46 entrees, TOUTES rejouees a chaque fois. Les tests ont
`probe_457 --since` (selection DERIVEE : graphe d'imports + empreinte MESUREE des fichiers
qu'un test ouvre reellement). Les cliquets n'avaient rien.

<< Qu'est-ce qui doit changer pour que ce cliquet change d'avis ? >> ne se calcule pas depuis
l'exterieur : elle se lit dans le CRITERE du cliquet. Chaque cliquet la DECLARE donc chez lui,
sous une forme executable, au niveau module :

    #: Ce qui doit changer pour que ce cliquet puisse changer d'avis.
    DECLENCHEUR = {
        "chemins": ("scripts/python/**/*.py",),   # globs, style git pathspec
        "build": True,        # son verdict depend-il d'un artefact du JEU installe ?
        "toujours": False,    # True = rien ne permet de le borner, il se rejoue TOUJOURS
        "raison": "<ce que le cliquet LIT, et pourquoi ces chemins suffisent>",
    }

LE DEFAUT EST `toujours: True`, ET C'EST UN RESULTAT
-----------------------------------------------------
Un declencheur trop LARGE coute du temps ; un declencheur trop ETROIT fabrique un FAUX VERT --
le cliquet n'est pas joue alors que son gisement vient de se rouvrir. L'asymetrie est totale,
donc le doute se resout TOUJOURS du cote large. C'est le patron de `probe_457` (<< tout doute
rejoue TOUT, et le DIT >>), transpose du test au cliquet. Ecrire `toujours: True` avec sa raison
est une mesure rendue, jamais un aveu.

TROIS CHOSES SONT AJOUTEES AU PERIMETRE PAR CE FOYER, JAMAIS PAR LE DECLARANT
------------------------------------------------------------------------------
  1. **Le source du cliquet lui-meme.** Un cliquet dont on ne rejouerait pas la modification
     n'a aucun sens ; l'ecrire 46 fois serait 46 occasions de l'oublier.
  2. **`data/symbols/**` quand `build: True`.** C'est le seul artefact du jeu que le depot
     versionne ; le reste (le binaire, le gameconfig de `AppData`) vit HORS de l'arbre, donc
     aucun diff ne peut le montrer -- `build: True` veut precisement dire << un changement de
     build peut faire basculer ce verdict sans qu'un seul fichier du depot bouge >>.
  3. **`scripts/ratchets.ps1`** : rien, ici. La banque ne change aucun verdict -- elle choisit
     qui court. C'est le garde `probe_486r12_declencheurs.py` qui la lit, pas les cliquets.

SEMANTIQUE DES GLOBS -- `**/` VAUT ZERO SEGMENT OU PLUS
--------------------------------------------------------
`scripts/python/**/*.py` couvre `scripts/python/probe_x.py` AUTANT que
`scripts/python/tests/engine/test_y.py`. C'est la semantique git pathspec, et c'est
DELIBEREMENT l'inverse de `pathlib.Path.match` / du glob de `pathlib`, ou `**/` exige un
segment intermediaire. Ce depot a deja paye cette confusion deux fois : `probe_431` classait
967 fichiers versionnes dans AUCUN seau (#458), et `probe_457` excluait les 24 fichiers poses
DIRECTEMENT sous `tests/` (#457-r5) -- les plus lourds du perimetre. Un matcher qui rate ce que
le declarant croyait couvrir est exactement la forme du faux vert que cette tranche combat.

Sortie ASCII stricte (console Windows cp1252).
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]

#: Nom de la constante, au niveau module, dans le source du cliquet.
NOM = "DECLENCHEUR"

#: Les quatre cles, exactement -- ni plus (une cle inventee ne serait lue par personne), ni
#: moins (une cle absente serait un defaut implicite, donc invisible).
CLES = ("chemins", "build", "toujours", "raison")

#: Ce que `build: True` ajoute. Cf. l'en-tete : le reste des artefacts du jeu est HORS ARBRE.
CHEMINS_BUILD = ("data/symbols/**",)

#: Une raison qui tient en trois mots ne dit pas ce que le cliquet LIT. Le seuil est bas
#: expres : il ecarte `"idem"` / `"voir plus haut"`, il n'impose pas une dissertation.
RAISON_MIN = 40


class DeclencheurAbsent(Exception):
    """Le fichier ne porte pas de `DECLENCHEUR` au niveau module."""


def _rel(p) -> str:
    """Chemin POSIX relatif a la racine du depot, ou chemin absolu POSIX s'il est dehors."""
    q = str(p).replace("\\", "/")
    r = str(RACINE).replace("\\", "/").rstrip("/") + "/"
    if q.lower().startswith(r.lower()):
        return q[len(r):]
    return q


def lire(chemin) -> dict:
    """Le `DECLENCHEUR` d'un fichier Python, lu par AST -- le module n'est JAMAIS execute.

    Importer le cliquet pour lire sa declaration serait absurde : `probe_120` tirerait tout
    `engine/`, `probe_391` tirerait pytest, et un cliquet dont l'import PLANTE ne pourrait plus
    declarer -- alors que c'est exactement l'etat ou l'on veut le savoir. `ast.literal_eval`
    n'evalue que des litteraux, donc aucun effet de bord n'est possible.
    """
    p = Path(chemin)
    src = p.read_text(encoding="utf-8", errors="replace")
    arbre = ast.parse(src, filename=str(p))
    for node in arbre.body:
        cibles = (node.targets if isinstance(node, ast.Assign)
                  else [node.target] if isinstance(node, ast.AnnAssign) else [])
        if not any(isinstance(t, ast.Name) and t.id == NOM for t in cibles):
            continue
        if node.value is None:
            raise DeclencheurAbsent("%s : `%s` declare sans valeur" % (_rel(p), NOM))
        try:
            return ast.literal_eval(node.value)
        except (ValueError, SyntaxError) as e:
            raise DeclencheurAbsent("%s : `%s` n'est pas un litteral (%s)"
                                    % (_rel(p), NOM, type(e).__name__))
    raise DeclencheurAbsent("%s : aucun `%s` au niveau module" % (_rel(p), NOM))


def valider(d) -> list[str]:
    """Les fautes de FORME, en clair. Liste vide = la declaration est bien formee.

    Ce n'est PAS le controle de fidelite -- celui-la confronte la declaration a la MESURE, et
    vit dans `probe_486r12_declencheurs.py`. Ici on ne juge que ce qui se lit sans rien jouer.
    """
    e: list[str] = []
    if not isinstance(d, dict):
        return ["`%s` n'est pas un dict (%s)" % (NOM, type(d).__name__)]

    manquantes = [c for c in CLES if c not in d]
    if manquantes:
        e.append("cle(s) manquante(s) : %s" % ", ".join(manquantes))
    inconnues = sorted(set(d) - set(CLES))
    if inconnues:
        e.append("cle(s) inconnue(s) : %s -- le contrat en a quatre, pas plus"
                 % ", ".join(inconnues))

    chemins = d.get("chemins")
    if chemins is not None:
        if not isinstance(chemins, (tuple, list)):
            e.append("`chemins` doit etre un tuple/list de globs (%s)" % type(chemins).__name__)
        else:
            for g in chemins:
                if not isinstance(g, str) or not g.strip():
                    e.append("glob vide ou non-str : %r" % (g,))
                    continue
                if "\\" in g:
                    e.append("glob %r : separateur Windows -- les chemins s ecrivent en POSIX" % g)
                if g.startswith("/") or (len(g) > 1 and g[1] == ":"):
                    e.append("glob %r : chemin ABSOLU -- relatif a la racine du depot, toujours" % g)
                if ".." in g.split("/"):
                    e.append("glob %r : `..` -- un declencheur ne sort pas du depot" % g)

    for cle in ("build", "toujours"):
        if cle in d and not isinstance(d[cle], bool):
            e.append("`%s` doit etre un booleen (%s)" % (cle, type(d[cle]).__name__))

    raison = d.get("raison")
    if raison is not None:
        if not isinstance(raison, str):
            e.append("`raison` doit etre une chaine (%s)" % type(raison).__name__)
        else:
            try:
                raison.encode("ascii")
            except UnicodeEncodeError:
                e.append("`raison` porte du non-ASCII -- elle est IMPRIMEE (console cp1252)")
            if len(raison.strip()) < RAISON_MIN:
                e.append("`raison` trop courte (%d < %d) : elle doit dire ce que le cliquet LIT"
                         % (len(raison.strip()), RAISON_MIN))

    # Un cliquet borne SANS chemin ne serait jamais rejoue par rien : c'est le faux vert
    # absolu, et c'est la seule combinaison que la forme peut refuser a elle seule.
    if d.get("toujours") is False and not d.get("chemins") and not d.get("build"):
        e.append("`toujours: False` avec un perimetre VIDE : rien ne le rejouerait JAMAIS. "
                 "Si tu ne sais pas le borner, ecris `toujours: True` avec sa raison.")
    return e


def perimetre(d, source_rel: str | None = None) -> tuple[str, ...]:
    """Les globs EFFECTIFS : ceux declares, plus ce que ce foyer ajoute (cf. en-tete)."""
    out = list(d.get("chemins") or ())
    if d.get("build"):
        out += list(CHEMINS_BUILD)
    if source_rel:
        out.append(source_rel)
    # dedup en gardant l'ordre : la sortie est lue par un humain quand le garde rougit.
    vus, uniq = set(), []
    for g in out:
        if g not in vus:
            vus.add(g)
            uniq.append(g)
    return tuple(uniq)


_RX: dict[str, re.Pattern] = {}


def _regex(glob: str) -> re.Pattern:
    """Glob -> regex. `**/` = ZERO segment ou plus (semantique git pathspec, cf. en-tete)."""
    r = _RX.get(glob)
    if r is not None:
        return r
    out, i = [], 0
    while i < len(glob):
        if glob.startswith("**/", i):
            out.append("(?:[^/]+/)*")
            i += 3
        elif glob.startswith("**", i):
            out.append(".*")
            i += 2
        elif glob[i] == "*":
            out.append("[^/]*")
            i += 1
        elif glob[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(glob[i]))
            i += 1
    r = re.compile("^" + "".join(out) + "$")
    _RX[glob] = r
    return r


def couvre(globs, rel: str) -> str | None:
    """Le PREMIER glob qui couvre `rel`, ou None. Rendre le glob (pas un booleen) : quand le
    garde rougit, il doit pouvoir dire par quoi une lecture etait censee etre couverte."""
    # ⚠ JAMAIS `lstrip("./")` : `str.lstrip` prend un ENSEMBLE DE CARACTERES, donc il mange le
    # point de `.gitignore` et rend `gitignore` -- qu'aucun glob ne couvre plus. Mesure : la
    # premiere confrontation des onze a rendu UN rouge, `probe_319 LU hors perimetre :
    # .gitignore`, alors que `.gitignore` etait bel et bien DECLARE. Faute du normalisateur,
    # pas du critere -- et elle penchait du cote BRUYANT (faux rouge), donc elle s'est vue.
    q = str(rel).replace("\\", "/")
    while q.startswith("./"):
        q = q[2:]
    for g in globs:
        if _regex(g).match(q):
            return g
    return None
