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

QUATRE CHOSES SONT AJOUTEES AU PERIMETRE PAR CE FOYER, JAMAIS PAR LE DECLARANT
--------------------------------------------------------------------------------
  1. **Le source du cliquet lui-meme.** Un cliquet dont on ne rejouerait pas la modification
     n'a aucun sens ; l'ecrire 46 fois serait 46 occasions de l'oublier.
  2. **`data/symbols/**` quand `build: True`.** C'est le seul artefact du jeu que le depot
     versionne ; le reste (le binaire, le gameconfig de `AppData`) vit HORS de l'arbre, donc
     aucun diff ne peut le montrer -- `build: True` veut precisement dire << un changement de
     build peut faire basculer ce verdict sans qu'un seul fichier du depot bouge >>.
  3. **LA CASCADE DE HARNAIS d'un fichier de test** (#531) : les `conftest.py` qui s'appliquent
     a lui, ET leur fermeture d'imports. AUCUN test n'importe son conftest -- c'est de la
     semantique PYTEST, invisible a l'AST -- et pourtant le verdict de chaque test en depend
     (fixtures `autouse`, `green_skip_guard` de #455). Mesure du 2026-08-07 : la cascade rend
     **435** chemins pour `tests/`, **446** pour `tests/engine/`, **472** pour
     `tests/engine/runner/` -- un PLANCHER que le test ne choisit pas et ne peut pas reduire.
     Les faire recopier par chaque declarant etait la cause MESUREE du glob universel : la
     seule declaration honnete etait aussi la plus chere, et elle rougissait au moindre import
     ajoute au conftest -- par quelqu'un d'autre. `test_524r1_bond_sous_effets_offline.py` a
     rendu `master` ROUGE pour l'avoir declaree honnetement (16 chemins recopies a la main).
     ⚠ Ce n'est PAS un assouplissement : le perimetre effectif est le MEME qu'avec les lignes
     recopiees, en PLUS FIDELE. Ce qui change, c'est QUI les ecrit -- le foyer, une fois, par
     DERIVATION.
  4. **`scripts/ratchets.ps1`** : rien, ici. La banque ne change aucun verdict -- elle choisit
     qui court. C'est le garde `probe_486r12_declencheurs.py` qui la lit, pas les cliquets.

L'AJOUT 3 EST UN PREREQUIS DE LA SELECTION, PAS UN CONFORT
------------------------------------------------------------
`probe_457.impacted_files` decide en DEUX moities, et la DECLAREE court-circuite la MESUREE :
un fichier qui declare n'est retenu que si un glob declare apparie le diff -- il ne passe JAMAIS
par le graphe d'imports. Resserrer les declarations SANS deriver le harnais fabriquerait donc
exactement le faux vert que #486 combat : un changement de `board.py` ne rejouerait plus les
tests dont le conftest l'importe. L'ajout 3 est ce qui rend le resserrement SUR.

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

#: Nom de la constante FACULTATIVE qui affine, ENTREE DE BANQUE PAR ENTREE DE BANQUE (#486-r19).
#:
#: LE PROBLEME QU'ELLE RESOUT. Un `DECLENCHEUR` se declare par FICHIER, mais la banque a des
#: entrees plus fines : `probe_283` en porte SIX (`--step diff|mirror|exec|tables|prose|on`) et
#: `probe_457` en porte HUIT (shards). Sur les 25 entrees du groupe C, QUATORZE partagent ainsi
#: un fichier avec des perimetres DIFFERENTS. La seule declaration non fautive etait alors
#: l'UNION -- et l'union est trop large pour presque toutes : ventilation MESUREE de `probe_283`
#: (couts isoles du 2026-08-07) : `diff` 1,1 s ne lit QUE `data/symbols/<build>/frida/enums.tsv`
#: quand `mirror` 32,6 s et `tables` 12,3 s lisent tout `.py`/`.ts`/`.js` du depot, et que `exec`
#: 80,0 s / `prose` 66,1 s / `on` 15,7 s ne lisent que `scripts/python/**`. Sous l'union, un `.ts`
#: de `frida/` rejoue 161,8 s d'etapes qui ne le lisent pas.
#:
#: ⚠ NE PAS le simuler en SCINDANT le fichier : les six etapes de `probe_283` partagent
#: `_fichiers_du_depot` / `_sources`, et c'est la memoisation de ces deux-la qui tient leur cout.
#:
#: L'ASYMETRIE QUI RENDAIT LA CHOSE ABSURDE : l'EMPREINTE, elle, est deja par ENTREE
#: (`declencheurs-empreinte.tsv` est keye sur l'id de banque). L'etage 2 de `probe_486r12`
#: confrontait donc une mesure FINE a une declaration GROSSIERE -- `probe_283:diff` ne pouvait
#: structurellement pas rougir, et surtout ne disait RIEN.
#:
#:     DECLENCHEUR_PAR_ENTREE = {
#:         "probe_283:diff": {"chemins": (), "build": True, "toujours": False,
#:                            "raison": "<ce que CETTE entree lit>"},
#:         ...
#:     }
#:
#: Les regles, dans l'ordre ou elles mordent :
#:   * le `DECLENCHEUR` de fichier reste OBLIGATOIRE -- il est l'UNION et le repli de toute
#:     entree non affinee. Retirer ce repli rendrait une entree neuve INDECLAREE en silence,
#:     ce qui est le faux vert que cette famille combat ;
#:   * une entree affinee est validee comme un declencheur ORDINAIRE (les quatre cles, meme
#:     forme, meme longueur minimale de raison) : il n'y a pas d'heritage partiel, parce
#:     qu'une cle heritee serait un defaut IMPLICITE, donc invisible ;
#:   * une CLE qui ne designe aucune entree de la banque est une declaration MORTE, donc un
#:     ROUGE -- meme regle que `Rougit` en direction morte (#426). C'est le seul moyen de voir
#:     un `probe_283:step` renomme ou retire.
NOM_PAR_ENTREE = "DECLENCHEUR_PAR_ENTREE"

#: Les quatre cles OBLIGATOIRES, exactement -- ni plus (une cle inventee ne serait lue par
#: personne), ni moins (une cle absente serait un defaut implicite, donc invisible).
CLES = ("chemins", "build", "toujours", "raison")

#: LE BYPASS DE CONFRONTATION (#486-r24), facultatif -- une CHAINE, qui EST sa raison.
#:
#: CE QU'IL DESARME, ET CE QU'IL NE DESARME PAS. Il desarme le seul etage de CONFRONTATION
#: (<< tout ce que ce fichier importe ou ouvre est-il dans son perimetre declare ? >>), et RIEN
#: d'autre : l'obligation de DECLARER reste, la validation de FORME reste, et la selection
#: continue de servir les globs declares.
#:
#: POURQUOI IL VAUT MIEUX QUE L'ETAT ANTERIEUR -- IL EXISTAIT DEJA, INVISIBLE. Mesure du
#: 2026-08-07 : 43 fichiers de test sur 52 declaraient un glob couvrant tout le Python, et 0
#: declarait `toujours: True`. Un glob universel n'est rien d'autre qu'un bypass -- il rend la
#: confrontation TOUJOURS satisfaite. Le prix de cette forme-la : elle MENT sur le perimetre
#: (donc elle empoisonne la selection, qui sert les globs declares), elle n'est pas COMPTABLE
#: (personne ne peut dire combien de fichiers se sont derobes) et elle ne dit pas POURQUOI. La
#: cle ci-dessous echange une evasion silencieuse contre une declaration COMPTEE.
#:
#:     DECLENCHEUR = {
#:         "chemins": ("scripts/python/tests/x/y.py",),
#:         "build": False, "toujours": False,
#:         "raison": "...",
#:         "hors_confrontation": "<pourquoi la fermeture d'imports ne borne PAS ce fichier>",
#:     }
#:
#: ⚠ CE N'EST PAS LA REPONSE A LA CASCADE DE HARNAIS. Un fichier qui n'est trop large que par
#: les `conftest.py` qu'il traine n'a pas besoin de bypasser : l'ajout 3 ci-dessus lui DERIVE
#: cette cascade. Les deux populations sont DISTINCTES et se mesurent separement -- les
#: confondre ferait du bypass la nouvelle echappatoire universelle, ce qui deplacerait le
#: probleme au lieu de le fermer.
CLE_HORS_CONFRONTATION = "hors_confrontation"

#: Les cles FACULTATIVES admises. Toute autre reste une faute de forme : le contrat ne se
#: complete pas par l'usage, sinon la moitie des declarations porterait une cle que personne ne
#: lit -- et qui aurait l'air de faire quelque chose.
CLES_FACULTATIVES = (CLE_HORS_CONFRONTATION,)

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


def _constante(chemin, nom: str, obligatoire: bool):
    """La constante `nom` d'un module, lue par AST -- le module n'est JAMAIS execute.

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
        if not any(isinstance(t, ast.Name) and t.id == nom for t in cibles):
            continue
        if node.value is None:
            raise DeclencheurAbsent("%s : `%s` declare sans valeur" % (_rel(p), nom))
        try:
            return ast.literal_eval(node.value)
        except (ValueError, SyntaxError) as e:
            raise DeclencheurAbsent("%s : `%s` n'est pas un litteral (%s)"
                                    % (_rel(p), nom, type(e).__name__))
    if obligatoire:
        raise DeclencheurAbsent("%s : aucun `%s` au niveau module" % (_rel(p), nom))
    return None


def lire(chemin) -> dict:
    """Le `DECLENCHEUR` d'un fichier Python. Obligatoire : son absence est un rouge."""
    return _constante(chemin, NOM, obligatoire=True)


def lire_par_entree(chemin) -> dict:
    """Le `DECLENCHEUR_PAR_ENTREE` d'un fichier Python, ou `{}` s'il n'en porte pas.

    FACULTATIF, et le rester est un choix defendable : un cliquet a une seule entree de banque
    n'a rien a affiner. Ce qui ne l'est pas, c'est de declarer une entree qui n'existe pas
    (cf. `valider_par_entree`)."""
    d = _constante(chemin, NOM_PAR_ENTREE, obligatoire=False)
    return d if d is not None else {}


def valider(d, perimetre_derive: bool = False) -> list[str]:
    """Les fautes de FORME, en clair. Liste vide = la declaration est bien formee.

    Ce n'est PAS le controle de fidelite -- celui-la confronte la declaration a la MESURE, et
    vit dans `probe_486r12_declencheurs.py`. Ici on ne juge que ce qui se lit sans rien jouer.

    `perimetre_derive` DIT SI UN PERIMETRE S'AJOUTE A CE QUI EST DECLARE (#486-r31), et c'est
    la seule regle d'ici que ca change -- celle du perimetre VIDE. Deux populations, deux
    verites :

      * un CLIQUET de la banque (`perimetre_derive=False`, le defaut) : `perimetre(d)` ne rend
        QUE ce qu'il declare. `toujours: False` + rien declare = rien ne le rejouera jamais ;
      * un FICHIER DE TEST (`perimetre_derive=True`) : `perimetre(d, source_rel)` ajoute le
        fichier LUI-MEME et la cascade de ses `conftest.py` (ajout 3 du foyer, #531). Son
        perimetre effectif n'est donc JAMAIS vide, et `chemins: ()` y est une declaration
        parfaitement bornee -- << rejoue-moi quand MOI ou mon harnais changent >>.

    MESURE QUI L'A ETABLI (2026-08-08, `tests/engine/runner/
    test_refresh_active_flag_discriminant_offline.py`, merge par la PR #834) : declaration
    reelle `chemins=() build=False toujours=False` -> `valider` rendait **1 erreur** quand
    `perimetre` rendait **475 chemins**, et `probe_486r15` rendait PASS. Deux gardes de la meme
    famille se contredisaient sur le meme fichier au meme commit : la regle jugeait le dict
    DECLARE pendant que sa justification parlait du perimetre EFFECTIF.

    ⚠ CE QUI NE DOIT PAS EN DECOULER : que la borne disparaisse pour les tests. Un test qui
    declare `chemins: ()` en important la moitie du moteur reste ROUGE -- par la CONFRONTATION
    (`probe_486r15` etage 2), qui est le garde adapte a cette question. On deplace la faute vers
    le cran qui sait la voir, on ne la supprime pas.
    """
    e: list[str] = []
    if not isinstance(d, dict):
        return ["`%s` n'est pas un dict (%s)" % (NOM, type(d).__name__)]

    manquantes = [c for c in CLES if c not in d]
    if manquantes:
        e.append("cle(s) manquante(s) : %s" % ", ".join(manquantes))
    inconnues = sorted(set(d) - set(CLES) - set(CLES_FACULTATIVES))
    if inconnues:
        e.append("cle(s) inconnue(s) : %s -- le contrat en a quatre obligatoires et %d "
                 "facultative(s) (%s), pas plus"
                 % (", ".join(inconnues), len(CLES_FACULTATIVES), ", ".join(CLES_FACULTATIVES)))

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
    # ⚠ SEULEMENT quand rien ne s'ajoute au declare (#486-r31) : pour un fichier de TEST, le
    # foyer derive la cascade de harnais et le fichier lui-meme, donc le perimetre effectif
    # n'est jamais vide et cette regle accuserait a tort (mesure : 1 erreur contre 475 chemins).
    if (not perimetre_derive and d.get("toujours") is False
            and not d.get("chemins") and not d.get("build")):
        e.append("`toujours: False` avec un perimetre VIDE : rien ne le rejouerait JAMAIS. "
                 "Si tu ne sais pas le borner, ecris `toujours: True` avec sa raison.")

    # -- LE BYPASS (#486-r24). Une cle qui EST sa raison : la porter sans rien dire est
    # impossible par construction, il n'y a pas de valeur << vraie >> a poser.
    if CLE_HORS_CONFRONTATION in d:
        motif = d[CLE_HORS_CONFRONTATION]
        if not isinstance(motif, str):
            e.append("`%s` doit etre une CHAINE -- elle EST la raison du bypass (%s)"
                     % (CLE_HORS_CONFRONTATION, type(motif).__name__))
        else:
            try:
                motif.encode("ascii")
            except UnicodeEncodeError:
                e.append("`%s` porte du non-ASCII -- elle est IMPRIMEE (console cp1252)"
                         % CLE_HORS_CONFRONTATION)
            if len(motif.strip()) < RAISON_MIN:
                e.append("`%s` trop courte (%d < %d) : elle doit dire POURQUOI la fermeture "
                         "d'imports ne borne pas ce fichier, pas qu'elle ne le borne pas"
                         % (CLE_HORS_CONFRONTATION, len(motif.strip()), RAISON_MIN))
        # Un `toujours: True` n'est DEJA jamais confronte (cf. `probe_486r12.etage_mesure` et
        # `probe_486r15.confronter`) : y ajouter un bypass est une declaration MORTE, donc du
        # copier-coller qui a l'air de faire quelque chose. Meme regle que la cle MORTE de
        # `valider_par_entree`.
        if d.get("toujours"):
            e.append("`%s` avec `toujours: True` : SANS OBJET -- une declaration `toujours` "
                     "n'est deja jamais confrontee. Retirer l'une des deux."
                     % CLE_HORS_CONFRONTATION)
    return e


def hors_confrontation(d):
    """Le MOTIF de bypass d'une declaration, ou `None`. Foyer unique de cette lecture.

    Rendre le MOTIF plutot qu'un booleen, pour la meme raison que `couvre` rend le glob : quand
    le cliquet imprime son compte, il doit pouvoir dire SUR QUEL MOTIF chaque fichier se derobe.
    Une doctrine qui ne s'affiche pas se degrade en silence."""
    motif = (d or {}).get(CLE_HORS_CONFRONTATION)
    return motif.strip() if isinstance(motif, str) and motif.strip() else None


def valider_par_entree(par_entree, ids_du_script) -> list[str]:
    """Les fautes de FORME d'un `DECLENCHEUR_PAR_ENTREE`. Liste vide = bien forme.

    `ids_du_script` = les ids de banque que CE script porte, DERIVES de `scripts/ratchets.ps1`
    (jamais une liste ecrite ici : c'est la lecon de #457-r6 sur les allowlists). Une cle hors
    de cet ensemble est une DECLARATION MORTE -- l'entree a ete renommee, retiree, ou n'a jamais
    existe -- et le silence y serait exactement le faux vert que #486-r12 combat : personne ne
    joue le perimetre fin qu'on croit avoir declare."""
    e: list[str] = []
    if not isinstance(par_entree, dict):
        return ["`%s` n'est pas un dict (%s)" % (NOM_PAR_ENTREE, type(par_entree).__name__)]
    connus = set(ids_du_script or ())
    for cle in sorted(par_entree, key=str):
        if not isinstance(cle, str) or not cle.strip():
            e.append("`%s` : cle vide ou non-str : %r" % (NOM_PAR_ENTREE, cle))
            continue
        if connus and cle not in connus:
            e.append("`%s` : cle MORTE %r -- aucune entree de banque de ce script ne porte cet "
                     "id (connues : %s)" % (NOM_PAR_ENTREE, cle, ", ".join(sorted(connus))))
            continue
        for f in valider(par_entree[cle]):
            e.append("`%s[%s]` : %s" % (NOM_PAR_ENTREE, cle, f))
    return e


def resoudre(d, par_entree, ident: str) -> dict:
    """La declaration EFFECTIVE d'une entree de banque : la sienne si elle en a une, sinon
    celle du FICHIER -- qui est l'union, donc le repli conservateur."""
    fine = (par_entree or {}).get(ident)
    return fine if isinstance(fine, dict) else d


def hors_de_l_union(d, par_entree) -> list:
    """[(ident, glob)] -- les globs d'une entree que le `DECLENCHEUR` du fichier ne couvre PAS.

    INFORMATIF, jamais un rc, et pour la meme raison que `redondants` : `_couvre_glob` teste par
    SUBSTITUTION, donc il est CONSERVATEUR (au pire il ne signale pas) et un rouge fonde dessus
    serait fragile. Mais un ecart signale que le declencheur de FICHIER a cesse d'etre l'union
    de ses entrees -- or c'est ce qu'il PRETEND etre, et c'est lui qui sert de repli a toute
    entree neuve."""
    large = list((d or {}).get("chemins") or ())
    if (d or {}).get("build"):
        large += list(CHEMINS_BUILD)
    out = []
    for ident in sorted(par_entree or {}, key=str):
        fine = par_entree[ident]
        if not isinstance(fine, dict):
            continue
        for g in (fine.get("chemins") or ()):
            if isinstance(g, str) and not any(_couvre_glob(h, g) for h in large):
                out.append((ident, g))
    return out


# ============================================================== la cascade de HARNAIS (#531)
#: Racine des tests. Un fichier hors de cet arbre n'a pas de cascade `conftest.py` a lui deriver.
PREFIXE_TESTS = "scripts/python/tests/"

_HARNAIS: dict = {}


class Fermeture:
    """La fermeture TOUS IMPORTS d'un fichier, resolue PAR LE DISQUE, sans indexer l'arbre.

    Elle vivait dans `probe_486r15_declencheurs_tests.py` ; elle est ICI depuis #531, parce que
    le PERIMETRE EFFECTIF en depend desormais (ajout 3) -- et le perimetre est servi aussi bien
    au cliquet qu'a la SELECTION de `probe_457`. Deux derivations d'un meme critere ouvrent un
    ecart silencieux : le garde jugerait alors un autre perimetre que celui que la selection
    joue. Meme arbitrage que `probe_463r1` pour le recensement offline.

    POURQUOI PAS `import_closure.Cloture` (#486-r11) : il repond a une AUTRE question -- << que
    charge `import M` ? >> -- et EXCLUT donc les imports differes (corps de fonction,
    `TYPE_CHECKING`), a raison pour son critere. Ici, un `import` ecrit dans un corps de test
    S'EXECUTE bel et bien pendant le test : l'exclure SOUS-approximerait la fermeture, et une
    sous-approximation dans un garde de couverture est un FAUX VERT.

    POURQUOI PAS `probe_457._graphe` : il lit et parse les 2 096 modules du domaine (32,7 s
    mesurees). Ici on ne visite que ce que les fichiers vises atteignent -- mediane 95 modules.
    """

    def __init__(self, racine=None) -> None:
        self.racine = Path(racine or RACINE)
        self._resolus: dict = {}
        self._cibles: dict = {}

    def resoudre(self, nom: str):
        """Le chemin relatif au depot du module `nom` sous `scripts/python`, ou `None`."""
        if nom in self._resolus:
            return self._resolus[nom]
        base = self.racine / "scripts" / "python"
        for suffixe in ("%s.py" % nom.replace(".", "/"),
                        "%s/__init__.py" % nom.replace(".", "/")):
            cand = base / suffixe
            if cand.is_file():
                self._resolus[nom] = "scripts/python/" + suffixe
                return self._resolus[nom]
        self._resolus[nom] = None
        return None

    @staticmethod
    def _paquet(rel: str, niveau: int):
        """Le prefixe de module d'un import RELATIF de niveau `niveau`, ou `None`.

        ⚠ SANS CECI, LA FERMETURE SOUS-APPROXIME -- et une sous-approximation dans un garde de
        couverture est un FAUX VERT. Mesure du 2026-08-07 : `engine/runner/snapshot.py`, que le
        conftest de `tests/` importe, n'ecrit QUE des imports relatifs (`from .state import
        State`, `from ..services.damage_config import ...`). `ast.ImportFrom` rend alors
        `module='state'` avec `level=1` -- un nom que `resoudre` cherche a `scripts/python/
        state.py`, ou il n'y a rien. Resultat : la cascade de harnais de `tests/` rendait 12
        chemins au lieu de la fermeture reelle, donc un changement dans `engine/runner/state.py`
        ne rejouait PAS les tests dont le conftest en depend.
        """
        parts = rel.split("/")
        if parts[:2] != ["scripts", "python"]:
            return None
        parts = parts[2:]
        # `a/b/__init__.py` EST le paquet `a.b`, et `a/b/c.py` VIT DANS `a.b` : dans les deux
        # cas le paquet courant est le repertoire, donc `parts[:-1]`.
        base = parts[:-1]
        recul = niveau - 1
        if recul > len(base):
            return None
        return base[:len(base) - recul] if recul else base

    def cibles(self, rel: str) -> set:
        """Les modules importes DIRECTEMENT par `rel` (tous imports, y compris differes)."""
        if rel in self._cibles:
            return self._cibles[rel]
        out: set = set()
        try:
            arbre = ast.parse((self.racine / rel).read_bytes())
        except (OSError, SyntaxError, ValueError):
            self._cibles[rel] = out
            return out
        noms: set = set()
        for n in ast.walk(arbre):
            if isinstance(n, ast.Import):
                noms.update(a.name for a in n.names)
            elif isinstance(n, ast.ImportFrom):
                if n.level:
                    base = self._paquet(rel, n.level)
                    if base is None:
                        continue
                    prefixe = ".".join(base + ([n.module] if n.module else []))
                    if not prefixe:
                        continue
                    noms.add(prefixe)
                    noms.update(prefixe + "." + a.name for a in n.names)
                elif n.module:
                    noms.add(n.module)
                    noms.update(n.module + "." + a.name for a in n.names)
        for nom in noms:
            morceaux = nom.split(".")
            for i in range(len(morceaux), 0, -1):
                cible = self.resoudre(".".join(morceaux[:i]))
                if cible:
                    out.add(cible)
                    break
        self._cibles[rel] = out
        return out

    def conftests(self, rel: str) -> set:
        """Les `conftest.py` qui s'appliquent a `rel`, de la racine du rootdir a son repertoire.

        AUCUN test n'IMPORTE son conftest : c'est de la semantique PYTEST, invisible a l'AST.
        L'oublier ferait passer pour << non couvert >> ce qui l'est, mais surtout laisserait une
        declaration ignorer les fixtures `autouse` et le `green_skip_guard` de #455 -- dont le
        verdict de CHAQUE test depend. Meme arete que `probe_457._conftest_edges`, dans l'autre
        sens."""
        out: set = set()
        morceaux = rel.split("/")[:-1]
        for i in range(len(morceaux), 1, -1):
            cand = "/".join(morceaux[:i]) + "/conftest.py"
            if (self.racine / cand).is_file():
                out.add(cand)
        return out

    def de(self, rel: str) -> set:
        vus: set = set()
        pile = [rel] + sorted(self.conftests(rel))
        while pile:
            x = pile.pop()
            if x in vus:
                continue
            vus.add(x)
            pile.extend(self.cibles(x) - vus)
        vus.discard(rel)
        return vus


def _fermeture(racine) -> Fermeture:
    cle = str(Path(racine or RACINE))
    f = _HARNAIS.get(("F", cle))
    if f is None:
        f = Fermeture(cle)
        _HARNAIS[("F", cle)] = f
    return f


def chemins_du_harnais(source_rel: str, racine=None) -> tuple[str, ...]:
    """La cascade de harnais d'un fichier de test : ses `conftest.py` ET leur fermeture.

    C'est l'ajout 3 du foyer (cf. en-tete). Il ne depend QUE du repertoire du fichier, donc il
    est memoise par repertoire -- la selection de `probe_457` l'appelle une fois par fichier du
    perimetre (~520 fichiers pour ~15 repertoires distincts).

    Hors de `scripts/python/tests/`, il rend le tuple VIDE : un cliquet n'a pas de conftest, et
    lui en deriver un elargirait son perimetre sans raison.
    """
    rel = str(source_rel).replace("\\", "/")
    if not rel.startswith(PREFIXE_TESTS):
        return ()
    rep = rel.rsplit("/", 1)[0]
    cache = _HARNAIS.get(("H", str(Path(racine or RACINE)), rep))
    if cache is not None:
        return cache
    ferm = _fermeture(racine)
    conftests = ferm.conftests(rel)
    out = set(conftests)
    for c in conftests:
        out |= ferm.de(c)
    res = tuple(sorted(out))
    _HARNAIS[("H", str(Path(racine or RACINE)), rep)] = res
    return res


def perimetre(d, source_rel: str | None = None, racine=None) -> tuple[str, ...]:
    """Les globs EFFECTIFS : ceux declares, plus ce que ce foyer ajoute (cf. en-tete)."""
    out = list(d.get("chemins") or ())
    if d.get("build"):
        out += list(CHEMINS_BUILD)
    if source_rel:
        out.append(source_rel)
        out += list(chemins_du_harnais(source_rel, racine))
    # dedup en gardant l'ordre : la sortie est lue par un humain quand le garde rougit.
    vus, uniq = set(), []
    for g in out:
        if g not in vus:
            vus.add(g)
            uniq.append(g)
    return tuple(uniq)


def redondants(d) -> list:
    """[(glob couvert, glob couvrant)] -- INFORMATIF, jamais une faute (cf. `valider`).

    POURQUOI CE N'EST PAS UN ROUGE, et pourquoi ce n'est pas rien non plus. Le groupe B
    (#486-r13) a ecrit SYSTEMATIQUEMENT les deux formes -- `a/*.py` ET `a/**/*.py` -- faute de
    trancher la semantique de `**/`. Elle est tranchee ICI (zero segment ou plus), donc la
    premiere forme est integralement couverte par la seconde : l'union est identique, aucun
    verdict ne bouge, et rougir dessus punirait un declarant PRUDENT. Mais un glob que rien ne
    peut selectionner de plus est une trace d'hesitation sur le contrat : il se signale.

    ⚠ Le critere est GLOB-A-GLOB, jamais le fichier reel : `a/*.py` est couvert par
    `a/**/*.py` parce que tout ce que le premier peut matcher, le second le matche aussi. On
    ne demande PAS s'il existe un fichier -- un declencheur decrit ce qui PEUT changer,
    y compris un fichier qui n'existe pas encore.
    """
    globs = list(d.get("chemins") or ())
    out = []
    for i, g in enumerate(globs):
        for j, h in enumerate(globs):
            if i != j and g != h and _couvre_glob(h, g):
                out.append((g, h))
                break
    return out


def _couvre_glob(large: str, etroit: str) -> bool:
    """`large` couvre-t-il tout ce que `etroit` peut matcher ? Teste par SUBSTITUTION : on
    remplace chaque joker de `etroit` par un temoin qu'il accepte, et on demande a `large`.
    Suffisant pour la seule forme qui nous occupe (`a/*.py` vs `a/**/*.py`) et conservateur
    partout ailleurs -- au pire on ne signale pas."""
    temoin = etroit.replace("**/", "z1/z2/").replace("**", "z1/z2").replace("*", "z3")
    temoin = temoin.replace("?", "z")
    return couvre([large], temoin) is not None


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
