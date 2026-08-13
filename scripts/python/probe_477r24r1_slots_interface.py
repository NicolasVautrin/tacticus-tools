"""#477-r24-r1 -- le mapping slot <-> methode de `Core.Services.IOperationProcessor`.

    python scripts/python/probe_477r24r1_slots_interface.py
    python scripts/python/probe_477r24r1_slots_interface.py --regenerer
    python scripts/python/probe_477r24r1_slots_interface.py --mutants
    python scripts/python/probe_477r24r1_slots_interface.py --courbe
    python scripts/python/probe_477r24r1_slots_interface.py --ventiler

CE QUE CE PROBE TRANCHE
-----------------------
Deux lectures publiees se contredisaient sur ce mapping. Elles etaient TOUTES LES DEUX
JUSTES : leurs slots concordent avec le metadata. Ce qui etait faux, c'est la grandeur
intermediaire par laquelle on les comparait -- une « position dans la classe », qui n'indexe
RIEN. Le slot d'interface est un rang dans la table de l'INTERFACE ; la position d'une methode
dans le dump de la CLASSE est un tout autre ordre, et le « decalage » entre les deux n'a aucune
raison d'etre constant. Deux decalages locaux differents ne sont donc PAS une contradiction.

Detail : `docs/rl/case-477r24r1-mapping-slot-interface.md`.

LES QUATRE ETAGES
-----------------
1. DERIVATION -- relit le `slot` dans `global-metadata.dat` (via `il2cpp_metadata`, qui localise
   les tables PAR CONTENU, sans lire le header). Tri-etat : metadata absent ou desynchronise
   => `PAS MESURE`, jamais un zero ni un vert.
2. CLIQUET -- confronte la derivation a l'entree VERSIONNEE
   `data/symbols/<build>/metadata/ioperationprocessor_slots.tsv`. C'est elle qui rend les
   etages 3 et 4 jouables dans un worktree frais, ou le jeu n'est pas forcement installe.
3. CITATIONS -- balaie le depot et confronte CHAQUE citation « slot X = NomDeMethode » portant
   sur cet OperationProcessor. Perimetre DERIVE : on visite tous les fichiers, on extrait toutes
   les citations de slot, et ce qui est ECARTE est COMPTE ET IMPRIME (une citation de slot vise
   le plus souvent une AUTRE interface -- `battleQuery`, `attackQuery`, un effet -- et le seul
   discriminant fiable est le RECEPTEUR ecrit au site).
4. ARITE -- quand la citation montre ses arguments, les compte et les confronte au
   `param_count` du metadata. C'est le cran qui a effectivement trouve la faute de #477-r24-r2 :
   `RemoveUnit` prend 3 arguments, le site n'en passe que 2.

L'APPARIEMENT SE FAIT SUR UNE FENETRE DE LIGNES (#477-r32)
----------------------------------------------------------
Jusqu'a #477-r32 ce probe exigeait slot et nom sur la MEME ligne, et ecartait 166 lignes du
patron « slot cite, nom introuvable ». `#477-r30` avait deja fait la mesure sur l'autre cliquet
(`probe_477r25_slots_autres_interfaces.py`) : elargir de la LIGNE a la FENETRE y a sorti
59 couples enjambants et **8 citations fausses**, dont deux jumelles de fautes deja corrigees --
restees dans le port parce qu'un saut de ligne les cachait. Le mecanisme est repris ici a
l'identique (blocs de toutes tailles, frontiere sur ligne VIDE, continuation de commentaire),
et le choix de `FENETRE` est RE-DERIVE sur CE corpus par `--courbe` : la courbe de #477-r30 ne
vaut pas pour celui-ci.

DEUXIEME CRAN, MESURE ICI : LE RECEPTEUR ECRIT ENTRE `slot` ET LE NUMERO
------------------------------------------------------------------------
Ce corpus ecrit « slot `IOperationProcessor` 0x21 », « slot processor 0x76 », « slot 0x3c
AttackDamage ». Sans ce cran, le motif ne reconnaissait meme pas le SLOT : la ligne partait dans
`sans_couple` et AUCUNE fenetre n'aurait pu la rattraper. C'est la meme forme de gisement que le
« slot d'INTERFACE » de #477-r30 -- un qualificatif non prevu qui rend le slot INVISIBLE, pas
seulement le couple.

CE QUE CE PROBE NE VOIT PAS, ET C'EST DIT
-----------------------------------------
* les citations de slot SANS nom de methode (« slot 0x55 `(entity, false)` ») : il n'y a rien a
  contredire, donc rien a garder. Elles sont COMPTEES et imprimees sous `SANS NOM` ;
* les slots des AUTRES interfaces (`IBattleQuery`, `IAttackQuery`, `IMatchState`, les effets).
  Ils sont ecartes, comptes, et c'est le residu #477-r25 ;
* la PROSE : « le processeur retire l'unite » ne porte aucun slot ;
* les couples dont le NOM n'est a AUCUN slot de l'interface : indecidables mecaniquement (soit
  le recepteur est mal apparie, soit le nom est faux), ils sont LISTES sous `NOM ABSENT`, jamais
  rendus verts ni rouges -- comme dans #477-r25.

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import argparse
import bisect
import re
import subprocess
import sys
from dataclasses import dataclass, replace
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import build_pin                                                        # noqa: E402
import il2cpp_metadata                                                  # noqa: E402
import repo_read                                                        # noqa: E402
import verdict_cache                                                    # noqa: E402
from symbols_layout import build_dir, current_build                     # noqa: E402

REPO = HERE.parent.parent

#: La classe qui IMPLEMENTE l'interface. Son ordre de methodes, lu cote Frida, sert d'ancre
#: pour localiser la table du metadata -- il n'est PAS la verite (cf. `class_method_order`).
KLASS = "Core.Services.OperationProcessor"

#: Noms de methodes, uniques dans le metadata, portes par l'interface cherchee. Ils fixent le
#: debut de sa table ; s'ils ne designent pas tous le MEME debut, le module REFUSE.
ANCRES = ("ContinueTurnPhase", "VerifyAutomaticTurnEnd", "ReviveUnit", "HealUnit",
          "RunComputerActionsForCurrentPlayer", "MarkUnitAsNoActionAvailable")

#: L'entree versionnee, relative a `data/symbols/<build>/`.
TSV_REL = ("metadata", "ioperationprocessor_slots.tsv")

#: Les fichiers balayes a l'etage 3. Perimetre DERIVE d'un `git ls-files`, jamais d'une liste.
BALAYAGE_GLOBS = ("docs/rl/*.md", "docs/*.md", "scripts/python/*.py",
                  "scripts/python/tests/**/*.py", "engine/**/*.py", "frida/hooks/**/*.ts")

#: Un slot cite. Toutes les formes que le depot ecrit :
#:   `<slot 0x16>`, `slot 0x16`, `slot **0x16**`, `slot `0x16``, `slot +6`, `slot 6`, `vslot`
#: ⚠ LE QUALIFICATIF EST INSENSIBLE A LA CASSE (cran de #477-r30, transpose), ET LE RECEPTEUR A
#: LE DROIT DE S'ECRIRE ENTRE `slot` ET LE NUMERO. Le depot ecrit « slot `IOperationProcessor`
#: 0x21 » (14 sites), « slot processor 0x76 », « le slot 0x23 de `Core.Services.
#: OperationProcessor` ». Sans ce cran le motif ne reconnaissait meme pas le SLOT -- la ligne
#: partait dans `sans_couple` et AUCUNE fenetre n'aurait pu la rattraper (#477-r32).
#: ⚠ ET IL A AUSSI LE DROIT DE S'ECRIRE APRES LE NUMERO (#477-r36) : « le slot 0x66 DE L'
#: `IOperationProcessor` ». C'est la SYMETRIQUE exacte du cran precedent, et c'est la tournure
#: meme dont l'etage NOM SEUL a fait son discriminant (« de l'<recepteur> »). Sans elle, la
#: resolution qui SUIT le recepteur est hors d'atteinte : le remplissage doit traverser
#: « de l'`IOperationProcessor`, » et bute sur la virgule. Mesure : c'est ce qui cachait
#: l'attribution du slot 0x66 = `TransformUnit`, celle-la meme que #477-r32 declarait avoir
#: rendue CONFRONTABLE.
_SUFFIXE_RECEP = (r"(?:[ \t]*(?:de|of)[ \t]*(?:l['`'’][ \t]*)?[`*]{0,2}"
                  r"(?:Core\.Services\.)?I?OperationProcessor[`*]{0,2})?")

_SLOT = (r"v?slot\s*(?i:d'interface\s*|itf\s*)?"
         r"(?:[`*]{0,2}(?:Core\.Services\.)?(?:I?OperationProcessor|processor|proc)[`*]{0,2}\s*)?"
         r"[`*]{0,2}\+?(?P<n%d>0x[0-9a-fA-F]+|\d+)[`*]{0,2}") + _SUFFIXE_RECEP

#: Le RECEPTEUR ecrit au site -- seul discriminant fiable de l'interface visee.
RE_RECEVEUR = re.compile(r"IOperationProcessor|OperationProcessor|(?<![A-Za-z])processor\s*\.")

#: Un nom de methode RATTACHE a cet OperationProcessor : symbole natif verbatim, acces pointe,
#: ou `$$Nom` isole (le `$$` non precede d'un identifiant, sinon `KillUnitOperation$$Execute`
#: passerait pour la methode `Execute` de l'interface).
_QUAL = (r"(?:(?:[A-Za-z0-9_.]*\.)?I?OperationProcessor(?:\$\$|\.)|(?<![A-Za-z])processor\."
         r"|(?<![A-Za-z0-9_])\$\$)")
#: Un nom SUIVI de `$$` est un nom de CLASSE (`FinishAttackOperation$$Execute`), pas une methode
#: de l'interface -- le rejeter est ce qui separe l'attestation de la chaine d'appel citee.
#: La classe negative doit inclure les CARACTERES DE MOT, sinon le moteur backtracke et rend un
#: nom TRONQUE qui, lui, n'est plus suivi de `$$` (mesure : `FinishAttackOperatio`).
#: ⚠ NI UN SEGMENT DE CHEMIN QUALIFIE. `slot 0x46 -> `IdunBattle.Operations.DiscardHitOperation`
#: rendait le nom `IdunBattle` : le qualificateur etant OPTIONNEL en forme A, le moteur y renonce
#: et attrape la TETE DU NAMESPACE. Mesure #477-r32 : 4 sites, tous artefacts, et tous ranges en
#: « nom inconnu de l'interface » -- exactement la ou une VRAIE citation fausse doit sortir. Un
#: nom suivi d'un POINT PUIS D'UNE LETTRE est un segment de chemin, jamais une methode.
_NOM = r"(?P<nom%d>[A-Z][A-Za-z0-9]{3,})(?![A-Za-z0-9$]|\.[A-Za-z])"
#: Rien d'autre ne doit s'intercaler entre le slot et son nom -- ni un AUTRE `slot`, ni une
#: parenthese FERMANTE. Sans la premiere exclusion, `... StartAttack slot 0x3a -> ...
#: FinishAttack slot 0x3b ...` attribue le nom du second au premier ; sans la seconde,
#: `$$StartAttack` (slot 0x3a) avant CHAQUE cible / `$$FinishAttack`' saute par-dessus la
#: fermeture et attrape le nom de la PROPOSITION SUIVANTE. Les deux faux positifs sont mesures.
#: ⚠ NI UN RENVOI, NI UNE PONCTUATION FORTE, NI UNE VIRGULE -- crans MESURES par #477-r25 sur
#: l'autre cliquet : « le slot 0x21 QUE `RunPhase` invoque » designe le slot APPELE, pas la
#: methode nommee ; une enumeration verticale apparie le nom d'un item au slot du SUIVANT.
_RENVOIS = ("slot", "que ", "qu'", "interrog", "invoq", "appel", "utilis", "evalu", "->", "→")

#: ⚠ LA FLECHE N'EST UN RENVOI QUE DANS LE SENS « NOM PUIS SLOT ». Elle y marque un
#: ENCHAINEMENT (« `BattleQuery$$ReachedSummonCap` -> slot 0x52 » designe ce que la methode
#: APPELLE) ; dans le sens « SLOT PUIS NOM » elle marque une RESOLUTION (« slot 0x3b ->
#: `OperationProcessor$$FinishAttack` »), c'est-a-dire exactement l'attribution cherchee.
#: `#477-r25` l'excluait des DEUX sens, et re-mesure ici, cran par cran, c'est le SEUL des dix
#: renvois qui coute quelque chose : retirer `→` de la forme C rend **1 couple de plus, JUSTE**
#: (`backlog.md` : « `FinishAttack` slot 0x3b -> `OperationProcessor$$FinishAttack` »), et
#: retirer `->` n'en rend **aucun**. Les deux sont retires de la forme C par leur CAUSE -- pas
#: parce que l'un rapporte : garder l'ASCII et lacher l'unicode serait un fit sur le corpus.
_RENVOIS_SLOT_PUIS_NOM = tuple(r for r in _RENVOIS if r not in ("->", "→"))


def _entre(n: int, traverse: bool, renvois: tuple[str, ...] = _RENVOIS,
           sans_virgule: bool = False, k: int | None = None) -> str:
    """Le remplissage tolere entre les deux membres d'un couple, borne a `n` caracteres.

    `traverse` dit si ce remplissage a le droit de franchir un SAUT DE LIGNE. C'est le SEUL
    parametre par lequel la fenetre agit sur les formes B et C ; la forme A, elle, separe ses
    membres par un separateur qui traverse deja (cf. `_esp`).

    `sans_virgule = True` REMET le cran VIRGULE d'avant #477-r42 (la virgule arrete le
    remplissage). Ce n'est plus le regime de service : c'est la REFERENCE mesurable
    (`--virgule-bloquante`), au meme titre qu'`--historique`.

    `k` nomme le groupe qui CAPTURE le remplissage (`rem<k>`). C'est ce qui permet de savoir,
    apres coup, si un couple a FRANCHI une virgule -- la donnee du cran `priorite-non-
    franchissement`. Sans capture, la question n'est pas posable : le motif ne dit pas ce qu'il
    a traverse.

    ⚠ FOYER UNIQUE, PARTAGE AVEC `probe_477r25_slots_autres_interfaces.py`. Les deux cliquets
    balayent le MEME depot ; deux motifs jumeaux qui derivent l'un de l'autre y rouvrent le
    gisement que l'autre vient de fermer (mesure #477-r36 : `master` etait ROUGE pour cette
    raison exacte). Chaque appelant passe SON jeu de renvois, jamais sa propre copie du motif.
    """
    exclus = ");:," if sans_virgule else ");:"
    classe = "[^%s]" % exclus if traverse else r"[^\n%s]" % exclus
    corps = r"(?:(?!%s)%s){0,%d}?" % ("|".join(renvois), classe, n)
    return corps if k is None else r"(?P<rem%d>%s)" % (k, corps)


def ceder_aux_locaux(couples, franchit, cle_slot, cle_nom):
    """LA CITATION LA PLUS LOCALE GAGNE -- foyer du cran `priorite-non-franchissement` (#477-r42).

    Un couple dont le remplissage a FRANCHI une virgule CEDE si l'un de ses deux membres -- le
    SLOT a sa ligne, ou le NOM a la sienne -- est deja apparie par un couple qui n'en a franchi
    AUCUNE. Rend `(gardes, cedes)`.

    ⚠ C'EST LE DISCRIMINANT QUE LE CRAN VIRGULE N'ETAIT PAS (#477-r42). La virgule etait un PROXY
    grossier de « ce membre est deja pris » : dans l'enumeration `slot N1 \\`X\\`, slot N2 \\`Y\\``,
    ce qui rend `(N2, X)` faux n'est pas la virgule -- c'est que `X` est deja apparie a `N1`, a sa
    GAUCHE IMMEDIATE, sans rien franchir. Mesure : la regle dissout les DEUX faux de ce regime
    (`test_433_..._c_caster_gates_{live,offline}.py`) et libere `, dont l'implementation
    \\`...$$AddUnit\\`` -- +6 couples JUSTES ici, +23 sur le corpus voisin, 0 perdu.

    ⚠ ELLE EST CONSERVATRICE PAR CONSTRUCTION : elle ne peut que RETIRER, et seulement la ou une
    attribution SANS FRANCHISSEMENT existe deja pour le meme membre. C'est le symetrique du cran
    « priorite au mono-ligne » de #477-r36, transpose du SAUT DE LIGNE a la VIRGULE.
    """
    sans = [c for c in couples if not franchit(c)]
    slots_pris = {cle_slot(c) for c in sans}
    noms_pris = {cle_nom(c) for c in sans}
    gardes, cedes = [], []
    for c in couples:
        if franchit(c) and (cle_slot(c) in slots_pris or cle_nom(c) in noms_pris):
            cedes.append(c)
        else:
            gardes.append(c)
    return gardes, cedes


#: UNE CONTINUATION -- ce qui s'intercale la ou une espace suffirait, quand la phrase reprend a
#: la ligne suivante. `\s*` ne suffit PAS : le depot commente en Python (`#`), en TS (`//`, `*`
#: d'un bloc), et ecrit du markdown (`>`, `*`, `-`, `|` de tableau). Repris VERBATIM de
#: #477-r30, qui l'a mesure necessaire.
_CONT = r"(?:[ \t]*\r?\n[ \t]*(?:\#+|//+|\*|>+|\||-)?[ \t]*)*[ \t]*"

#: UNE COUPURE -- la meme chose, mais la ou AUCUNE espace n'etait toleree : entre le
#: qualificateur et le nom. `Core.Services.OperationProcessor$$` en fin de ligne et
#: `VerifyUnitsTurnFinished` sur la suivante est une forme REELLE de ce corpus (mesure : 3
#: sites, dont `turnflow.py` et `runner.py`). Elle vaut UNE fois, jamais zero espace + un blanc :
#: en regime mono-ligne, ce motif est remplace par la chaine VIDE, donc `fenetre=1` ne bouge pas.
_COUPURE = r"(?:[ \t]*\r?\n[ \t]*(?:\#+|//+|\*|>+|\||-)?[ \t]*)?"


def _esp(traverse: bool) -> str:
    """Le separateur « espace » de la forme A. Il franchit la ligne en regime fenetre."""
    return _CONT if traverse else r"\s*"


#: UN SLOT S'ECRIT SOUS FORME D'APPEL, ET SA LISTE D'ARGUMENTS EST UN BLOC ATOMIQUE (#477-r36).
#: `processor.<slot 0x16>(TurnStage.Start /*3*/, forceEndTurn: false, isManual: true);` -- la
#: liste porte les `(`, `)`, `,`, `:`, `;` que `_entre` exclut, si bien que la resolution ecrite
#: JUSTE APRES etait hors d'atteinte des formes A, B et C. MESURE : c'est la premiere cause du
#: gisement `nom_ecarte_par_un_cran` (23 des 50 lignes portent un appel entre le slot et son nom).
#:
#: ⚠ CE N'EST PAS LE RELACHEMENT « la parenthese fermante ne bloque plus » de #477-r32 (6 couples
#: neufs, 4 artefacts) : on ABSORBE une paire EQUILIBREE et COLLEE, on n'IGNORE pas la fermeture.
#: Hors de ce bloc, `_entre` garde TOUTES ses exclusions -- c'est ce qui empeche `slot 0x3a` de
#: sauter par-dessus une fermeture pour attraper le nom de la proposition SUIVANTE. Les deux crans
#: (colle, equilibre) sont RELACHABLES separement et mesures (`--relacher`).
#:
#: Le motif est « deroule » (`[^()]*(?:\([^()]*\)[^()]*)*`) et non `(?:[^()]|\(...\))*` : la
#: seconde forme est ambigue et backtracke exponentiellement sur une ligne longue de `backlog.md`.
#: LA PROFONDEUR D'IMBRICATION que l'absorption sait suivre. `re` ne fait pas de recursion : le
#: motif est DEROULE, un niveau a la fois. La valeur est MESUREE (`--profondeur`), pas choisie --
#: et elle n'est pas cosmetique : un appel plus profond que ce que le motif suit n'est PAS absorbe,
#: le nom de sa ligne reste bloque, et le slot va chercher celui de la ligne SUIVANTE.
#: Mesure sur le corpus voisin (`probe_477r25`, site `case-287r11`) :
#: `GetAllAliveUnits(Nullable<int>(GetCurrentOwnerEntityId(caster)))` est a 3 niveaux.
PROFONDEUR_APPEL = 3


def _equilibre(profondeur: int) -> str:
    """Une paire de parentheses equilibree, DEROULEE jusqu'a `profondeur` niveaux.

    Le motif est ecrit en « boucle deroulee » (`[^()]*(?:\\(...\\)[^()]*)*`) et non
    `(?:[^()]|\\(...\\))*` : la seconde forme est AMBIGUE et backtracke exponentiellement sur une
    ligne longue de `backlog.md`. Mesure : le relachement `nom-en-backticks` n'a pas rendu en 120 s
    avec un separateur ambigu en amont.
    """
    corps = r"[^()\n]*"
    for _ in range(profondeur - 1):
        corps = r"[^()\n]*(?:\(%s\)[^()\n]*)*" % corps
    return r"\(%s\)" % corps


def _appel(k: int, colle: bool = True, equilibre: bool = True, actif: bool = True,
           profondeur: int = PROFONDEUR_APPEL) -> str:
    if not actif:
        return ""
    avant = r"[`*>]{0,2}" if colle else r"[^\n(]{0,20}?"
    corps = _equilibre(profondeur) if equilibre else r"\([^\n]*"
    return r"(?:%s(?P<appel%d>%s)[`*]{0,2}[ \t]*;?)?" % (avant, k, corps)


#: LE MARQUEUR DE COMMENTAIRE -- `#` (Python), `//` (TS/pseudo-code). Volontairement PAS `--` :
#: le corpus ecrit « processor.<slot 0x2f>(...);  -- AVANT ContinueTurnPhase », ou ce qui suit est
#: de la PROSE et non une resolution (le mot `AVANT` passerait pour un nom de methode).
_MARQ_COMMENT = r"[ \t]*(?:\#+|//+)[ \t]*"

#: LA RESOLUTION PEUT ETRE DANS LE SECOND COMMENTAIRE, ET LA LOCALITE TIENT QUAND MEME (#477-r42).
#: `engine/streams/turn_phase.py` ecrit `processor.<slot 0x21>();  // -- \`verifier\`` puis, LIGNE
#: SUIVANTE, `// = \`...$$VerifyUnitsTurnFinished\``. La forme D exigeait le PREMIER commentaire :
#: elle butait sur `-- \`verifier\``, qui ne resout rien.
#:
#: ⚠ « SAUTER LE PREMIER COMMENTAIRE » N'EST PAS CE QU'ON FAIT -- ce serait perdre exactement ce
#: que `appel-colle` tient. On suit le BLOC DE COMMENTAIRE CONTIGU : la ligne suivante doit etre
#: ELLE-MEME une ligne de commentaire (rien que des espaces avant son marqueur). On ne franchit
#: jamais du CODE, et le cran est relachable (`commentaire-contigu`) pour publier ce qu'il ecarte.
#:
#: ⚠ LA CONTINUATION SEULE NE SUFFIT PAS, ET C'EST UNE MESURE. La forme D refusait AUSSI le nom
#: PLEINEMENT QUALIFIE (`_NOM` interdit `Core` suivi de `.S` -- cran de #477-r32 contre les tetes
#: de namespace), or le site ecrit `Core.Services.OperationProcessor$$VerifyUnitsTurnFinished`.
#: Mesure, cause par cause : continuation seule **0** couple neuf ; qualificateur seul **0** ;
#: les deux ensemble **+1, JUSTE, 0 faux, 0 perdu**, et le plateau est atteint des k = 1.
def _marq_commentaire(traverse: bool, contigu: bool = True) -> str:
    """Le marqueur de la forme D, prolonge au bloc de commentaire CONTIGU en regime fenetre."""
    if not traverse:
        return _MARQ_COMMENT
    #: `contigu = False` desarme la LOCALITE : la ligne suivante n'a plus a etre ELLE-MEME un
    #: commentaire -- du CODE peut la preceder. C'est une MESURE (`--relacher
    #: commentaire-contigu`), jamais un regime de service : c'est precisement ce franchissement
    #: qui perdrait ce que `appel-colle` tient.
    suite = (r"[ \t]*(?:\#+|//+)[ \t]*" if contigu else r"[^\n]*?(?:\#+|//+)?[ \t]*")
    return _MARQ_COMMENT + r"(?:[^\n]*\r?\n%s)?" % suite


def _regex_couples(traverse: bool, relaches: tuple[str, ...] = (), historique: bool = False,
                   profondeur: int = PROFONDEUR_APPEL, virgule_bloquante: bool = False):
    """LES CINQ FORMES DE COUPLE (slot, nom) RETENUES COMME ATTESTATION.

    Un nom simplement PRESENT sur la ligne ne compte pas : il faut qu'il soit ADJACENT au slot.
    Sans cette contrainte, une ligne de `backlog.md` fournit trente « noms » et le controle
    devient du bruit (mesure #477-r24-r1 : 32 desaccords, 30 faux).

    `relaches` desarme un cran NOMME (cf. `CRANS`) pour la duree d'une mesure. Le regime EN
    SERVICE est `relaches = ()` ; toute autre valeur sert a publier ce que le cran CACHE.

    `historique = True` rend le regime d'AVANT #477-r36 : les trois formes A/B/C, sans absorption
    d'appel. Il joue ici le role que `fenetre = 1` joue pour #477-r32 -- une REFERENCE mesurable,
    et le seul regime ou le mutant des formes neuves doit etre INERTE.

    `virgule_bloquante = True` rend le regime d'AVANT #477-r42, ou la virgule ARRETAIT le
    remplissage. Meme role de REFERENCE : c'est ce qui permet de chiffrer ce que le cran remplace.
    """
    esp = _esp(traverse)
    coupure = _COUPURE if traverse else ""
    colle = "appel-colle" not in relaches
    equilibre = "appel-equilibre" not in relaches
    if historique:
        return (
            re.compile((_SLOT % 0) + esp + r"(?:=|->|:)" + esp + r"[`*]{0,2}(?:" + _QUAL + r")?"
                       + coupure + (_NOM % 0)),
            re.compile(_QUAL + (_NOM % 1) + _entre(40, False, _RENVOIS, True) + (_SLOT % 1)),
            re.compile((_SLOT % 2) + _entre(60, traverse, _RENVOIS_SLOT_PUIS_NOM, True)
                       + _QUAL + coupure + (_NOM % 2)),
        )
    qual_c = r"(?:" + _QUAL + r")?" if "qualificateur-forme-c" in relaches else _QUAL
    #: Le conditionnel `(?(eq3)|...)` : SI le commentaire porte un `=` avant le nom, rien de plus
    #: n'est exige ; SINON le nom doit etre suivi d'un enchainement (`->`, `→`) ou de sa SIGNATURE
    #: (`(`). C'est ce cran qui separe « # = MarkUnitAsNoActionAvailable (POSE) » (une resolution)
    #: de « # RemoveEffectOperation » (le nom de la CLASSE vers laquelle le slot aiguille, qui
    #: n'est a AUCUN slot -- il sortirait en citation FAUSSE, et ce serait un artefact).
    marq = "" if "resolution-marquee" in relaches else r"(?(eq3)|(?=[ \t]*(?:\(|->|→)))"
    ouvre = "" if "placeholder-ferme" in relaches else r"<"
    ferme = r"[ \t]*" if "placeholder-ferme" in relaches else r"[ \t]*>"
    bt = r"[`*]{0,2}" if "nom-en-backticks" in relaches else r"`"
    #: LE CRAN VIRGULE N'EST PLUS DANS LE MOTIF (#477-r42) : il est passe du REMPLISSAGE au
    #: POST-FILTRE (`ceder_aux_locaux`). `virgule_bloquante` rejoue l'ancien regime, en reference.
    virg = virgule_bloquante
    marq_d = _marq_commentaire(traverse, "commentaire-contigu" not in relaches)
    return (
        #: A -- `slot 0x7e = MoveUnit`, `slot **0x43** = `OperationProcessor$$ApplyDamage``
        re.compile((_SLOT % 0) + _appel(0, colle, equilibre, profondeur=profondeur)
                   + esp + r"(?:=|->|:)" + esp
                   + r"[`*]{0,2}(?:" + _QUAL + r")?" + coupure + (_NOM % 0)),
        #: B -- `processor.FinishAttack` slot 0x3b   (nom PUIS slot, colles)
        #: ⚠ ELLE NE FRANCHIT JAMAIS LE SAUT DE LIGNE, meme en regime fenetre. Dans une
        #: enumeration verticale, le nom ecrit AVANT appartient a l'item precedent, pas au slot
        #: qui suit -- cran mesure par #477-r30, conserve ici a l'identique.
        re.compile(_QUAL + (_NOM % 1) + _appel(1, colle, equilibre, profondeur=profondeur)
                   + _entre(40, False, _RENVOIS, virg, k=1) + (_SLOT % 1)),
        #: C -- slot 0x3a ... `OperationProcessor$$StartAttack`   (slot PUIS nom, colles)
        re.compile((_SLOT % 2) + _appel(2, colle, equilibre, profondeur=profondeur)
                   + _entre(60, traverse, _RENVOIS_SLOT_PUIS_NOM, virg, k=2)
                   + qual_c + coupure + (_NOM % 2)),
        #: D -- LA RESOLUTION COMMENTEE : `<IOperationProcessor slot 0x76>(unit)  # = MarkUnitAs…`
        #: Le qualificateur n'y est PAS exige, et c'est ce qui la distingue de C : le marqueur de
        #: commentaire joue son role -- apres `#`/`//`, en fin de ligne de pseudo-code, ce qui est
        #: ecrit RESOUT ce qui precede. Le cran `resolution-marquee` (ci-dessus) est ce qui
        #: empeche cette forme de recolter n'importe quel commentaire.
        #: ⚠ ET LE NOM Y A LE DROIT D'ETRE PLEINEMENT QUALIFIE (#477-r42). `_NOM` refuse une tete
        #: de namespace (`Core` suivi de `.S`), donc sans ce `(?:_QUAL)?` la resolution
        #: `= \`Core.Services.OperationProcessor$$VerifyUnitsTurnFinished\`` est hors d'atteinte.
        #: Mesure : le qualificateur SEUL ne rend aucun couple, la continuation SEULE non plus --
        #: c'est leur CONJONCTION qui rend le site, et elle ne coute ni faux ni perte.
        re.compile((_SLOT % 3) + _appel(3, colle, equilibre, profondeur=profondeur) + marq_d
                   + r"(?:(?P<eq3>=)[ \t]*)?[`*]{0,2}(?:" + _QUAL + r")?" + (_NOM % 3)
                   + r"[`*]{0,2}" + marq),
        #: E -- LE NOM DANS LE PLACEHOLDER : `processor.<slot 0x3c AttackDamage>(caster, …)`.
        #: Tout ce qui est ENTRE les chevrons designe le slot -- c'est la cause du cran, et non
        #: « le nom est colle au numero » : sans la fermeture, `slot SANS ARGUMENT` et `slot SOIT`
        #: rentrent (meme faux positif de PROSE que celui mesure sur l'etage NOM SEUL).
        re.compile(ouvre + (_SLOT % 4) + r"[ \t]+[`*]{0,2}" + (_NOM % 4) + r"[`*]{0,2}" + ferme),
        #: F -- LA RESOLUTION EN PROSE : `processor.<slot 0x16>(TurnStage.Start, …)` c'est-a-dire
        #: `ContinueTurnPhase`. Le qualificateur n'y est pas ecrit non plus ; ce qui tient lieu de
        #: cran, c'est le couple (marqueur de RESOLUTION, nom entre BACKTICKS). Relacher `_QUAL`
        #: en forme C rendrait les memes couples, mais avec **88 artefacts** pour 4 justes
        #: (`--relacher qualificateur-forme-c`) : c'est le delimiteur de code qui fait la
        #: difference, pas la tolerance.
        #: ⚠ SON SEPARATEUR EST `_COUPURE`, PAS `_CONT`, ET C'EST UNE MESURE. `_CONT` est une
        #: BOUCLE dont le corps peut matcher a vide ; place derriere un marqueur aussi peu
        #: contraint que `-{2,}`, elle backtracke exponentiellement sur les tableaux de
        #: `backlog.md` (mesure : le relachement `nom-en-backticks` n'a pas rendu en 120 s).
        #: Une continuation SUFFIT -- la seule forme reelle qui traverse est
        #: « …, c'est-a-dire\n   `ContinueTurnPhase` ».
        re.compile((_SLOT % 5) + _appel(5, colle, equilibre, profondeur=profondeur) + r"[`*]{0,2}[ \t]*,?[ \t]*"
                   #: ⚠ SEUL LE DELIMITEUR OUVRANT EST EXIGE. Le fermant vient APRES la signature
                   #: quand le site l'ecrit (« `…$$TransformUnit(entity, statModifiers,
                   #: isHidden)` ») : l'exiger colle au nom rejetait la citation la plus
                   #: complete du corpus. C'est l'OUVERTURE qui discrimine la prose
                   #: (« -- AVANT ContinueTurnPhase » n'en a pas), et le relachement
                   #: `nom-en-backticks` le verifie.
                   + r"(?:c'est-[àa]-dire|-{2,}|=|->|→)[ \t]*" + coupure + bt
                   + r"(?:" + _QUAL + r")?" + (_NOM % 5) + r"[`*]{0,2}"),
    )


#: LA CITATION PAR NOM SEUL -- « le slot `KillUnit` de l'`IOperationProcessor` ». Elle ne porte
#: AUCUN numero, donc il n'y a pas de couple a confronter ; mais le NOM, lui, doit etre une
#: methode de l'interface. C'est ce cran qui a trouve la faute de #477-r32 : `components.py`
#: ecrivait « le slot `ApplyStatModifiers` de l'`OperationProcessor` », et `ApplyStatModifiers`
#: n'est a AUCUN des 150 slots -- c'est ce que l'Operation appelle DEUX NIVEAUX plus bas.
#:
#: ⚠ LE DISCRIMINANT EST LA TOURNURE « de l'<recepteur> », PAS LE MOT EN CAPITALE. Un motif qui
#: se contente de `slot <Mot>` recolte la PROSE (`slot SANS ARGUMENT`, `slot SOIT`, `slots
#: AUTRES que`) : mesure #477-r32, 5 faux positifs pour 7 citations reelles. La tournure les
#: dissout toutes, sans en perdre une seule.
_NOM_SEUL = (r"(?<![A-Za-z0-9_])v?slots?\s+[`*]{0,2}(?P<nomseul>[A-Z][A-Za-z0-9]{3,})[`*]{0,2}"
             r"%s(?:de|of)%s(?:l[''’][ \t]*)?[`*]{0,2}(?:Core\.Services\.)?"
             r"I?OperationProcessor")


def _regex_nom_seul(traverse: bool) -> re.Pattern[str]:
    esp = _esp(traverse)
    return re.compile(_NOM_SEUL % (esp, esp))


#: LES CRANS CONSERVATEURS RELACHABLES, chacun avec sa CAUSE. `--relacher` les desarme UN PAR UN
#: et publie les couples que chacun CACHE, avec leur verdict. Un zero ne vaut que releve ainsi :
#: c'est la methode qui a montre, sur #477-r32, que les 8 couples douteux etaient TOUS des
#: artefacts du relachement et non des fautes du depot.
CRANS = {
    "appel-colle": "la liste d'arguments absorbee doit etre COLLEE au slot (sinon un appel "
                   "quelconque de la ligne sert de pont vers un nom qui n'est pas le sien)",
    "appel-equilibre": "elle doit etre une paire de parentheses EQUILIBREE (sinon on retombe sur "
                       "le relachement « la fermeture ne bloque plus », 4 artefacts en #477-r32)",
    "resolution-marquee": "le nom commente doit porter un marqueur de RESOLUTION (`=` avant, "
                          "`->`/`→` ou sa signature apres) -- sinon tout commentaire est recolte",
    "placeholder-ferme": "le nom du slot doit etre DANS les chevrons (sinon la PROSE `slot SANS "
                         "ARGUMENT`, `slot SOIT` entre, comme sur l'etage NOM SEUL)",
    "nom-en-backticks": "la resolution EN PROSE (forme F) n'accepte le nom que dans un "
                        "delimiteur de code -- c'est ce qui separe « c'est-a-dire "
                        "`ContinueTurnPhase` » de « -- AVANT ContinueTurnPhase »",
    "qualificateur-forme-c": "la forme C exige un qualificateur (`OperationProcessor$$`, "
                             "`processor.`, `$$`) devant le nom -- CRAN HERITE, jamais relache "
                             "en service",
    #: ⚠ CE CRAN A REMPLACE `virgule-dans-le-remplissage` (#477-r42), et le remplacement est une
    #: MESURE, pas un gout. L'ancien arretait le remplissage a la premiere virgule ; il cachait
    #: **7** couples JUSTES sur ce corpus (dont `slot 5 ... dont l'implementation \\`$$AddUnit\\``)
    #: et **0** faux. Ce qu'il protegeait vraiment -- l'enumeration `slot N1 \\`X\\`, slot N2
    #: \\`Y\\`` -- n'est pas un fait de VIRGULE mais de LOCALITE : `X` y est deja apparie a `N1`,
    #: a sa gauche immediate. Le cran porte donc desormais sur ce fait-la.
    "priorite-non-franchissement": "un couple qui a FRANCHI une virgule cede si l'un de ses "
                                   "membres (slot ou nom) est deja apparie SANS en franchir -- "
                                   "la citation la plus LOCALE gagne (cf. `ceder_aux_locaux`)",
    #: ⚠ IL NE SE RELACHE QU'EN REGIME FENETRE : hors fenetre, la forme D ne suit aucun bloc.
    "commentaire-contigu": "la resolution peut vivre dans le SECOND commentaire, mais la ligne "
                           "suivante doit etre ELLE-MEME un commentaire -- relacher, c'est "
                           "franchir du CODE, ce qui perd la localite d'`appel-colle`",
}

#: Les deux jeux, construits UNE fois. `RE_COUPLES` = le regime mono-ligne (l'etat d'avant
#: #477-r32, garde comme REFERENCE mesurable) ; `RE_COUPLES_ML` = le regime fenetre.
RE_COUPLES = _regex_couples(False)
RE_COUPLES_ML = _regex_couples(True)
RE_NOM_SEUL = _regex_nom_seul(False)
RE_NOM_SEUL_ML = _regex_nom_seul(True)
RE_SLOT = re.compile(r"v?slot")

#: Le probe est EXCLU de son propre balayage : ses regex de documentation contiennent des
#: exemples de syntaxe (`slot 0x7e = MoveUnit`) qui ne sont pas des attributions. Un controle
#: qui rougit sur son propre artefact fait renoncer a des mesures justes. L'exclusion est
#: NOMMEE et imprimee, jamais silencieuse.
EXCLUS = ("scripts/python/probe_477r24r1_slots_interface.py",)

#: L'arite n'est confrontee que si le site montre VRAIMENT ses arguments juste apres le couple
#: (`processor.<slot 0x60>(killer, u, opts)`), jamais sur une parenthese quelconque de la ligne.
#: AUCUNE espace n'est toleree : un appel s'ecrit `Nom(args)`, jamais `Nom (args)` -- sans quoi
#: une parenthese de PROSE (« ... $$EvaluateAbilities` (litteral `0x17`) ») compte pour un argument.
RE_APPEL = re.compile(r"\A[`*>]{0,2}\(")

#: Marqueur d'EXEMPTION au site : une ligne qui CITE une attribution refutee pour la nommer
#: comme telle porte legitimement un couple (slot, nom) faux. Compte et imprime, jamais muet.
MARQUEUR_REFUTE = "[slot-attribution:refute]"


#: LA FENETRE, en LIGNES, sur laquelle un couple (slot, nom) est apparie. `1` = l'etat d'avant
#: #477-r32 : slot et nom sur la MEME ligne, ce qui ecartait 166 lignes.
#:
#: LA VALEUR EST MESUREE, PAS CHOISIE (`--courbe` la re-derive) -- et la courbe de #477-r30
#: (plate des W=2) NE VAUT PAS pour ce corpus-ci : elle est re-mesuree ligne par ligne, avec ses
#: chiffres publies dans `docs/rl/case-477r25-slots-autres-interfaces.md`.
FENETRE = 3


@dataclass(frozen=True)
class Citation:
    fichier: str
    ligne: int
    slot: int
    noms: tuple[str, ...]
    args: int | None
    texte: str
    #: La ligne ou le NOM est ecrit. `ligne_nom != ligne` <=> le couple ENJAMBE un saut de
    #: ligne, donc il n'existe que grace a la fenetre (#477-r32).
    ligne_nom: int = 0
    #: L'index de la FORME qui l'a capte (0=A, 1=B, 2=C, 3=D resolution commentee, 4=E
    #: placeholder) et si son appel a ete ABSORBE. `forme >= 3 or appel_absorbe` <=> le couple
    #: n'existe que grace a #477-r36 -- c'est ce que son mutant mute, et ce qui le rend INERTE
    #: dans le regime historique.
    forme: int = 0
    appel_absorbe: bool = False
    #: Le remplissage a-t-il FRANCHI une virgule ? Donnee du cran `priorite-non-franchissement`
    #: (#477-r42) et de son mutant. Seules les formes B et C ont un remplissage capturable.
    franchit_virgule: bool = False


@dataclass(frozen=True)
class CitationNom:
    """Un slot designe par son NOM SEUL, sans numero (« le slot `KillUnit` de l'... »)."""

    fichier: str
    ligne: int
    nom: str
    texte: str


#: LA VENTILATION DU RESIDU. Un compte qui ne dit pas SA CAUSE est un inventaire ; sa cause en
#: fait une tache. Trois causes, exhaustives par construction (leur somme est `sans_couple`).
CAUSES = {
    "sans_numero": "la ligne nomme un slot sans le CHIFFRER (prose, ou tournure que l'etage 5 "
                   "ne reconnait pas)",
    "numero_sans_nom": "le slot est chiffre, AUCUN nom de methode de l'interface n'est ecrit "
                       "dans la fenetre -- rien a contredire",
    "nom_ecarte_par_un_cran": "le slot est chiffre ET un nom de l'interface est dans la fenetre, "
                              "mais un cran conservateur l'ecarte -- LE gisement restant",
}


@dataclass(frozen=True)
class Ecartees:
    """Ce que l'etage 3 n'a PAS retenu. Un compte filtre DIT ce qu'il filtre.

    ⚠ IL N'Y A PAS DE CATEGORIE « INDECIDABLE » ICI, ET C'EST UNE DIFFERENCE VOULUE AVEC
    `probe_477r25_slots_autres_interfaces.py`. La-bas, un nom absent de l'interface appariee peut
    accuser l'APPARIEMENT (18 interfaces, recepteur devine sur la ligne) ; ici l'interface est
    UNIQUE et le recepteur est ECRIT. Un nom qui n'est a aucun slot est donc une citation FAUSSE,
    et la ranger en « ni vert ni rouge » enterrerait exactement ce que ce cliquet doit trouver.
    """

    autre_interface: int = 0
    sans_couple: int = 0
    exemptees: int = 0
    #: `{cause: [(fichier, ligne, texte), ...]}` pour les `sans_couple`. La somme des trois
    #: causes VAUT `sans_couple` -- c'est une partition, pas une liste blanche de motifs.
    ventilation: dict[str, tuple[tuple[str, int, str], ...]] | None = None
    #: Les couples qui ont FRANCHI une virgule et ont CEDE a une attribution sans franchissement
    #: (#477-r42). Un compte filtre dit ce qu'il filtre : ils sont listes, jamais tus.
    cedes_au_non_franchissement: tuple[str, ...] = ()


# ------------------------------------------------------------------ etage 1 : DERIVATION


def deriver() -> list[il2cpp_metadata.MethodDef] | None:
    """Les methodes de l'interface indexees par slot, ou `None` si le metadata n'est pas la.

    `None` = PAS MESURE. Ce n'est ni une table vide ni un vert : les appelants doivent le
    distinguer, et l'impression le dit en toutes lettres.
    """
    try:
        meta_path = build_pin.global_metadata()
    except build_pin.BuildPinRefused as exc:
        print("[1] DERIVATION : PAS MESURE -- %s" % str(exc).splitlines()[0])
        return None
    methods_tsv = build_dir() / "frida" / "methods.tsv"
    #: ⚠ CETTE MEMOISATION N'EST PAS TAUTOLOGIQUE, ET LA DISTINCTION EST TOUT (#486-r1).
    #: L'etage 2 confronte CETTE derivation a l'entree VERSIONNEE `ioperationprocessor_slots.tsv`.
    #: Cacher la TABLE VERSIONNEE et la comparer a elle-meme detruirait le critere -- c'est
    #: precisement ce qu'on ne fait pas. Ce qui est memoise ici, c'est le resultat d'une VRAIE
    #: lecture du binaire du jeu, sous une cle qui contient le HASH DE CE BINAIRE : elle n'est
    #: reutilisee que si le `global-metadata.dat` ET `frida/methods.tsv` sont bit-a-bit
    #: identiques. Les deux cotes de la confrontation restent donc INDEPENDANTS.
    #: ⚠ ET LE TRI-ETAT TIENT : sans le jeu installe, `global_metadata()` a deja leve
    #: (PAS MESURE ci-dessus) ; si le hash n'est pas calculable, `sha` vaut `None` et on
    #: RECALCULE au lieu de servir une attestation qu'aucune machine n'a produite ici.
    #: Mesure : 0,05 s de hachage pour ~14 s de derivation.
    sha = verdict_cache.sha_gros_fichiers(meta_path, methods_tsv)
    if sha is None:
        table, pas = _deriver_vraiment(meta_path, methods_tsv)
    else:
        table, pas = cache().contribution(
            "<global-metadata>", "deriver", sha,
            lambda: _deriver_vraiment(meta_path, methods_tsv))
    print("[1] DERIVATION : %d slots lus dans le metadata (pas=%d octets), %d ancres concordantes"
          % (len(table), pas, len(ANCRES)))
    return table


def _deriver_vraiment(meta_path: Path,
                      methods_tsv: Path) -> tuple[list[il2cpp_metadata.MethodDef], int]:
    """La lecture REELLE du metadata. `(table, pas de la grille)` -- le pas est rendu parce que
    la ligne imprimee le cite, et qu'une sortie a chaud doit etre celle d'un run a froid."""
    reader = il2cpp_metadata.read(meta_path)
    reader.locate(il2cpp_metadata.class_method_order(methods_tsv, KLASS))
    return reader.interface_table(ANCRES), reader.entry_size or 0


# --------------------------------------------------------------------- etage 2 : CLIQUET


def tsv_path(build: str | None = None) -> Path:
    return build_dir(build).joinpath(*TSV_REL)


def lire_tsv() -> dict[int, tuple[str, int]]:
    p = tsv_path()
    if not p.is_file():
        raise SystemExit(
            "ROUGE : l'entree versionnee est absente (%s).\n"
            "  La regenerer sur une machine ou le jeu est installe :\n"
            "  python scripts/python/probe_477r24r1_slots_interface.py --regenerer"
            % p.as_posix())
    out: dict[int, tuple[str, int]] = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        slot, nom, nargs = line.split("\t")[:3]
        out[int(slot)] = (nom, int(nargs))
    return out


def ecrire_tsv(table: list[il2cpp_metadata.MethodDef]) -> Path:
    p = tsv_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    lignes = [
        "# Core.Services.IOperationProcessor -- slot d'interface -> methode, LU dans le champ",
        "# `slot` d'`Il2CppMethodDefinition` (global-metadata.dat du build %s)." % current_build(),
        "# Entree VERSIONNEE : c'est ce qui rend la garde jouable sans le jeu installe.",
        "# Regenerer : python scripts/python/probe_477r24r1_slots_interface.py --regenerer",
        "#slot\tmethode\tparam_count\tflags",
    ]
    lignes += ["%d\t%s\t%d\t0x%04x" % (m.slot, m.name, m.param_count, m.flags) for m in table]
    p.write_text("\n".join(lignes) + "\n", encoding="utf-8")
    return p


def cliquet(table: list[il2cpp_metadata.MethodDef] | None,
            versionne: dict[int, tuple[str, int]]) -> list[str]:
    if table is None:
        print("[2] CLIQUET   : PAS MESURE (pas de derivation a confronter) -- "
              "%d slots dans l'entree versionnee, utilises tels quels par les etages 3-4"
              % len(versionne))
        return []
    ecarts: list[str] = []
    for m in table:
        attendu = versionne.get(m.slot)
        if attendu is None:
            ecarts.append("slot %d (%s) absent de l'entree versionnee" % (m.slot, m.name))
        elif attendu != (m.name, m.param_count):
            ecarts.append("slot %d : metadata %s/%d != versionne %s/%d"
                          % (m.slot, m.name, m.param_count, attendu[0], attendu[1]))
    for slot in sorted(set(versionne) - {m.slot for m in table}):
        ecarts.append("slot %d (%s) versionne mais ABSENT du metadata"
                      % (slot, versionne[slot][0]))
    print("[2] CLIQUET   : %d ecart(s) derivation vs entree versionnee" % len(ecarts))
    for e in ecarts[:20]:
        print("      %s" % e)
    return ecarts


# ------------------------------------------------------------------- etage 3 : CITATIONS


_FICHIERS: list[Path] | None = None
_TEXTES: list[tuple[str, str]] | None = None


def fichiers_balayes() -> list[Path]:
    """Le perimetre, DERIVE de `git ls-files`. Memoise : `recolter` est appele QUATRE fois.

    La memoisation ne change pas le perimetre -- `git ls-files` rendait deja le meme resultat aux
    quatre appels du meme run. Une panne de git reste un `SystemExit` PAS MESURE, jamais un
    perimetre vide qui se lirait « rien a signaler ».
    """
    global _FICHIERS
    if _FICHIERS is not None:
        return _FICHIERS
    try:
        out = subprocess.run(["git", "-C", str(REPO), "ls-files", "-z", *BALAYAGE_GLOBS],
                             capture_output=True, text=True, timeout=60, check=True)
    except (OSError, subprocess.SubprocessError) as exc:                # noqa: BLE001
        raise SystemExit("PAS MESURE : `git ls-files` muet (%s) -- le perimetre du balayage "
                         "ne peut pas etre DERIVE, et on n'en invente pas un." % exc)
    _FICHIERS = [REPO / rel for rel in out.stdout.split("\0") if rel]
    return _FICHIERS


def textes_balayes() -> list[tuple[str, str]]:
    """`[(chemin relatif, texte)]` -- lecture PARALLELE, UNE fois pour les quatre recoltes.

    Meme traitement d'erreur qu'avant : un fichier illisible ou non-UTF-8 est simplement ABSENT
    (l'ancien `except (OSError, UnicodeDecodeError): continue`), donc les denominateurs imprimes
    ne bougent pas. `repo_read.to_text` reproduit exactement ce que `Path.read_text` rendait, fins
    de ligne universelles comprises.
    """
    global _TEXTES
    if _TEXTES is not None:
        return _TEXTES
    chemins = [p for p in fichiers_balayes()
               if p.relative_to(REPO).as_posix() not in EXCLUS]
    out: list[tuple[str, str]] = []
    for p, texte in zip(chemins, repo_read.read_texts(chemins)):
        if texte is not None:
            out.append((p.relative_to(REPO).as_posix(), texte))
    _TEXTES = out
    return _TEXTES


# ------------------------------------------------- le CACHE de verdict par fichier (#486-r1)
#
# LOCALITE ETABLIE, et c'est ce qui autorise le cache. La contribution d'un fichier a l'etage 3
# (`_contribution`) ne lit QUE son propre texte : les seules variables partagees de l'ancienne
# boucle etaient des ACCUMULATEURS (`retenues`, `noms_seuls`, les trois compteurs, `ventile`) et
# un `vus_noms` dont la cle COMMENCE par `rel` -- donc intra-fichier par construction, jamais un
# canal entre deux fichiers. Tout ce qui est INTER-fichier (deduplication, `ceder_aux_locaux`,
# `confronter`) reste HORS du cache et se rejoue integralement a chaque run.
#
# Le CONTEXTE porte le source de ce cliquet ET l'entree versionnee des slots : editer une regex ou
# changer de build fait MANQUER toutes les entrees. Invalider trop est sur ; trop peu serait faux.

_CACHE: verdict_cache.CacheCliquet | None = None


def _encoder(v: tuple, appel: str = "") -> list:
    if appel == "deriver":
        table, pas = v
        return [[[m.name, m.slot, m.param_count, m.flags, m.file_offset] for m in table], pas]
    #: ⚠ LES CAUSES VIDES NE SONT PAS ECRITES. `recolter` accumule par `ventile[cause] += v` :
    #: une cle absente ajoute exactement ce qu'ajoute une liste vide, donc l'omission est
    #: VALEUR-PRESERVANTE (verifie par le controle de fidelite froid == chaud). Sur un artefact
    #: VERSIONNE, les 5 cles vides de chaque entree muette pesaient plus que les entrees utiles.
    cits, noms, autre, sans, exempt, ventile = v
    return [[[c.fichier, c.ligne, c.slot, list(c.noms), c.args, c.texte, c.ligne_nom,
              c.forme, c.appel_absorbe, c.franchit_virgule] for c in cits],
            [[c.fichier, c.ligne, c.nom, c.texte] for c in noms],
            autre, sans, exempt,
            {k: [list(x) for x in vs] for k, vs in ventile.items() if vs}]


def _decoder(b: list, appel: str = "") -> tuple:
    if appel == "deriver":
        return ([il2cpp_metadata.MethodDef(name=x[0], slot=x[1], param_count=x[2],
                                           flags=x[3], file_offset=x[4]) for x in b[0]], b[1])
    cits = [Citation(fichier=x[0], ligne=x[1], slot=x[2], noms=tuple(x[3]), args=x[4],
                     texte=x[5], ligne_nom=x[6], forme=x[7], appel_absorbe=x[8],
                     franchit_virgule=x[9]) for x in b[0]]
    noms = [CitationNom(fichier=x[0], ligne=x[1], nom=x[2], texte=x[3]) for x in b[1]]
    return (cits, noms, b[2], b[3], b[4],
            {k: [(x[0], x[1], x[2]) for x in v] for k, v in b[5].items()})


def cache() -> verdict_cache.CacheCliquet:
    global _CACHE
    if _CACHE is None:
        _CACHE = verdict_cache.CacheCliquet(
            nom="probe_477r24r1_slots_interface",
            contexte=verdict_cache.sha_fichiers_texte(Path(__file__).resolve(),
                                                HERE / "il2cpp_metadata.py", tsv_path()),
            encoder=_encoder, decoder=_decoder)
    return _CACHE


def _id_appel(fenetre: int, traverse: bool, relaches: tuple[str, ...], historique: bool,
              profondeur: int, virgule_bloquante: bool, ventile: bool) -> str:
    """Identifiant LISIBLE et deterministe du jeu de parametres d'une recolte."""
    return "w%d%s%s%s%s%s%s" % (
        fenetre, "+t" if traverse else "", "+h" if historique else "",
        "" if profondeur == PROFONDEUR_APPEL else "+p%d" % profondeur,
        "+vb" if virgule_bloquante else "", "+n" if ventile else "",
        "+r:" + ",".join(sorted(relaches)) if relaches else "")


#: Ce qu'un auteur ecrit pour dire << je n'enumere pas les arguments >>. Les trois formes vivent
#: dans l'arbre : ASCII `..` et `...`, et l'ellipse UNICODE `…` (le depot en porte, cf.
#: `probe_283._FUN_PUB`). Un segment qui ne contient QUE ces caracteres est une ELISION.
_ELISION = re.compile(r"\A[.…]{1,3}\Z")


def _compter_args(texte: str, apres: int = 0) -> int | None:
    """Nombre d'arguments du premier appel parenthese apres `apres`, ou None s'il n'y en a pas.

    ⚠ UNE ELLIPSE, MEME EN POSITION D'UN SEUL ARGUMENT, REND `None` (#1031). L'ellipse DIT que
    les arguments ne sont pas detailles ; les compter ferait rougir une citation qui ne pretend
    RIEN sur l'arite.

    Le cran existait deja pour l'elision TOTALE (`(...)`), et c'est ce qui laissait passer
    l'elision PARTIELLE -- la forme reellement ecrite dans l'arbre, ou l'auteur elide le debut
    et NOMME ce qui l'interesse. Mesure du 2026-08-13, le rouge de `master` :

        transfer_damage.py:11   -> Core.Services.OperationProcessor$$TransferDamage(..., hitIndex)

    lue comme << 2 arguments >>, confrontee aux 6 de la signature, donc rouge. Or la citation
    dit exactement l'inverse de ce qu'on lui reproche : elle DECLARE ne pas les enumerer, et
    ne nomme `hitIndex` que parce que la ligne du dessus vient d'expliquer d'ou il sort.
    C'est la meme lecture que `probe_283._FUN_PUB`, qui accepte `FUN_...(0x50, …, 0x3d)`.

    ⚠ AUCUN TROU OUVERT : un site qui ecrit TOUS ses arguments reste confronte a la signature.
    Seul celui qui declare une elision sort du gate -- il ne peut pas mentir sur ce qu'il
    n'affirme pas.
    """
    ouvre = texte.find("(", apres)
    if ouvre < 0:
        return None
    prof, segs, cur = 0, [], []
    for ch in texte[ouvre:]:
        if ch in "([<{":
            prof += 1
            if prof == 1:
                continue
        elif ch in ")]>}":
            prof -= 1
            if prof == 0:
                segs.append("".join(cur))
                if any(_ELISION.match(s.strip()) for s in segs):
                    return None
                utiles = [s for s in segs if s.strip()]
                return len(segs) if utiles else 0
        elif ch == "," and prof == 1:
            segs.append("".join(cur))
            cur = []
            continue
        if prof >= 1:
            cur.append(ch)
    return None


def _blocs(lignes: list[str], fenetre: int):
    """(index 0-based de la 1re ligne, texte joint, offsets de debut de chaque ligne du bloc).

    A `fenetre = 1`, chaque bloc EST une ligne : le regime d'avant #477-r32, a l'identique.

    ⚠ TOUTES LES TAILLES de 1 a `fenetre` sont rendues, pas seulement `fenetre`, et un bloc
    demarre a CHAQUE ligne. Les deux crans ont ete MESURES necessaires par #477-r30, et le
    second l'est ENCORE ici : ne rendre que la taille maximale casse la MONOTONIE -- un bloc plus
    large voit plus de texte, donc plus de renvois et de ponctuation forte, et PERD un couple que
    le bloc etroit voyait. Rendre toutes les tailles fait de la recolte une UNION, donc monotone
    par construction, et le couple est juge dans le plus PETIT contexte qui le porte.

    ⚠ UNE LIGNE VIDE EST UNE FRONTIERE, et le bloc s'y arrete. Un couple n'enjambe pas un
    changement de paragraphe -- mesure #477-r30 : 2 des faux positifs de l'elargissement ne
    tenaient qu'a ce franchissement, et AUCUN couple juste ne le demande.
    """
    for i0 in range(len(lignes)):
        hauteur = min(fenetre, len(lignes) - i0)
        for j in range(i0 + 1, i0 + hauteur):
            if not lignes[j].strip():
                hauteur = j - i0
                break
        for w in range(1, hauteur + 1):
            vues = lignes[i0:i0 + w]
            offsets = [0]
            for l in vues[:-1]:
                offsets.append(offsets[-1] + len(l) + 1)
            yield i0, "\n".join(vues), offsets


def _regex_noms(noms: frozenset[str]) -> re.Pattern[str]:
    """Un motif qui reconnait N'IMPORTE QUEL nom de methode de l'interface, isole.

    ⚠ LE `$` EST HORS DU LOOKBEHIND, ET C'EST UNE CORRECTION DE #477-r36. Avec
    `(?<![A-Za-z0-9_$])`, ce motif ne voyait PAS un nom QUALIFIE -- `OperationProcessor$$RemoveUnit`
    lui etait invisible, alors que c'est la forme la plus courante du corpus. Consequence
    MESUREE : la VENTILATION rangeait ces lignes en `numero_sans_nom` (« rien a contredire »)
    alors qu'elles portaient un nom appariable, et le gisement etait donc SOUS-COMPTE. C'est le
    vice « un recenseur ne peut pas rendre zero sur ce qu'il ne visite pas », sur le recenseur
    lui-meme. Le lookbehind garde son role -- refuser un SUFFIXE de mot (`XRemoveUnit`).
    """
    return re.compile(r"(?<![A-Za-z0-9_])(?:%s)(?![A-Za-z0-9$])"
                      % "|".join(re.escape(n) for n in sorted(noms)))


def _contribution(rel: str, texte: str, fenetre: int, couples, rx_nom_seul,
                  rx_un_nom) -> tuple:
    """LA CONTRIBUTION D'UN SEUL FICHIER a l'etage 3 -- verdict LOCAL, donc cachable (#486-r1).

    Elle ne lit QUE `texte`. C'est ce qui a ete ETABLI avant de poser le cache : dans l'ancienne
    boucle, les seules variables partagees entre fichiers etaient des ACCUMULATEURS, et le
    `vus_noms` de deduplication portait une cle COMMENCANT par `rel` -- donc intra-fichier par
    construction. Aucun canal ne courait d'un fichier a l'autre.

    Rend `(citations, citations par nom seul, autre_interface, sans_couple, exemptees,
    ventilation partielle)`. Tout ce qui est INTER-fichier -- deduplication globale, priorite au
    non-franchissement, confrontation a la table -- reste chez `recolter`, hors cache.
    """
    retenues: list[Citation] = []
    noms_seuls: list[CitationNom] = []
    vus_noms: set[tuple[str, int, str]] = set()
    autre_iface = sans_couple = exemptees = 0
    ventile: dict[str, list[tuple[str, int, str]]] = {c: [] for c in CAUSES}
    lignes = texte.splitlines()
    #: PRE-CALCUL PAR LIGNE : une ligne n'est examinee que si un slot est ecrit a moins de
    #: `fenetre` lignes d'elle -- ailleurs, aucun bloc ne la joindra jamais a un slot.
    a_slot = [bool(RE_SLOT.search(l)) for l in lignes]
    utile = [any(a_slot[max(0, i - fenetre + 1):i + fenetre]) for i in range(len(lignes))]
    recept_l = [bool(RE_RECEVEUR.search(l)) if u else False
                for l, u in zip(lignes, utile)]
    #: Les lignes portant un slot d'ou SORT au moins un couple. C'est ce qui distingue
    #: « ecartee » de « couverte », et c'est une propriete de LIGNE, pas de bloc.
    couvertes: set[int] = set()
    exemptees_l: set[int] = set()
    for i0, bloc, offsets in _blocs(lignes, fenetre):
        fin = i0 + len(offsets)
        if not any(a_slot[i0:fin]) or not any(recept_l[i0:fin]):
            continue
        for k, rx in enumerate(couples):
            for m in rx.finditer(bloc):
                slot = int(m.group("n%d" % k), 0)
                nom = m.group("nom%d" % k)
                no = i0 + bisect.bisect_right(offsets, m.start("n%d" % k))
                no_nom = i0 + bisect.bisect_right(offsets, m.start("nom%d" % k))
                #: ⚠ LE RECEPTEUR SE JUGE SUR LE SPAN DU COUPLE, PAS SUR LE BLOC. A
                #: `fenetre = 1` c'est la meme chose (span = ligne), mais des que le bloc
                #: s'elargit, un `OperationProcessor` nomme trois lignes plus bas n'a plus a
                #: s'attribuer un slot ecrit au-dessus de lui -- ce serait attribuer a cette
                #: interface un slot que le site rapporte a une autre (mesure #477-r30, ou
                #: le vice symetrique attribuait `$$FinishAttack` a `IMatchState`).
                a, b = min(no, no_nom), max(no, no_nom)
                if not any(recept_l[a - 1:b]):
                    continue
                #: L'exemption au site vaut si elle est ecrite sur l'une OU l'autre des
                #: lignes du couple. A `fenetre = 1` c'est la meme.
                if (MARQUEUR_REFUTE in lignes[no - 1]
                        or MARQUEUR_REFUTE in lignes[no_nom - 1]):
                    exemptees_l.add(no)
                    continue
                couvertes.add(no)
                queue = bloc[m.end():]
                args = _compter_args(queue) if RE_APPEL.match(queue) else None
                #: ⚠ L'APPEL ABSORBE REND L'ETAGE ARITE APPLICABLE AUX FORMES OU L'APPEL EST
                #: ECRIT AVANT LE NOM (#477-r36). Jusqu'ici l'arite ne se confrontait que
                #: quand le site montrait ses arguments APRES le couple : la forme B
                #: (`processor.AddUnit(a, b, c, d, e)  // slot 5`) et la forme D
                #: (`<slot 0x76>(unit)  # MarkUnitAsNoActionAvailable`) etaient hors de
                #: portee du cran qui a trouve la faute de #477-r24-r2. Elles y entrent.
                capte = m.groupdict().get("appel%d" % k)
                if args is None and capte:
                    args = _compter_args(capte)
                retenues.append(Citation(
                    fichier=rel, ligne=no, slot=slot, noms=(nom,), args=args,
                    ligne_nom=no_nom, forme=k, appel_absorbe=bool(capte),
                    franchit_virgule="," in (m.groupdict().get("rem%d" % k) or ""),
                    texte=lignes[no - 1].strip()[:150]))
        #: LES CITATIONS PAR NOM SEUL, sur le MEME bloc. Elles ne portent pas de numero,
        #: donc la ligne qu'elles couvrent n'est pas forcement une ligne a slot chiffre --
        #: mais elle cesse de compter comme « slot cite sans nom ».
        for m in rx_nom_seul.finditer(bloc):
            no = i0 + bisect.bisect_right(offsets, m.start("nomseul"))
            if MARQUEUR_REFUTE in lignes[no - 1]:
                exemptees_l.add(no)
                continue
            couvertes.add(no)
            cle = (rel, no, m.group("nomseul"))
            if cle in vus_noms:
                continue
            vus_noms.add(cle)
            noms_seuls.append(CitationNom(fichier=rel, ligne=no, nom=m.group("nomseul"),
                                          texte=lignes[no - 1].strip()[:150]))
    #: CE QUI RESTE ECARTE se compte LIGNE PAR LIGNE -- une ligne, un verdict. Compter par
    #: bloc melangerait les regimes et rendrait les chiffres incomparables d'une fenetre a
    #: l'autre, alors que c'est justement ce qu'on veut mesurer.
    for no, ligne in enumerate(lignes, 1):
        if not RE_SLOT.search(ligne) or no in couvertes:
            continue
        if not RE_RECEVEUR.search(ligne):
            autre_iface += 1
        elif MARQUEUR_REFUTE in ligne or no in exemptees_l:
            exemptees += 1
        else:
            sans_couple += 1
            #: VENTILATION -- la cause est DERIVEE de la ligne et de son voisinage, jamais
            #: d'une liste de motifs : un slot non chiffre, un slot chiffre sans nom
            #: appariable dans la fenetre, ou un slot chiffre AVEC un nom que seul un cran
            #: conservateur ecarte. C'est ce dernier tas qui est le gisement (#477-r34).
            if rx_un_nom is not None:
                if not re.search(_SLOT % 0, ligne):
                    quoi = "sans_numero"
                else:
                    autour = "\n".join(lignes[max(0, no - fenetre):no - 1 + fenetre])
                    quoi = ("nom_ecarte_par_un_cran" if rx_un_nom.search(autour)
                            else "numero_sans_nom")
                ventile[quoi].append((rel, no, ligne.strip()[:120]))

    return retenues, noms_seuls, autre_iface, sans_couple, exemptees, ventile


def recolter(fenetre: int = FENETRE, traverse: bool | None = None,
             noms_interface: frozenset[str] | None = None,
             relaches: tuple[str, ...] = (), historique: bool = False,
             profondeur: int = PROFONDEUR_APPEL, virgule_bloquante: bool = False
             ) -> tuple[list[Citation], list[CitationNom], Ecartees]:
    """(couples (slot, nom), citations par NOM SEUL, ce qui est ecarte et compte).

    `fenetre` = nombre de LIGNES sur lesquelles un couple peut s'etaler. `traverse` dit si les
    formes A et C ont le droit de franchir le saut de ligne ; par defaut, oui des que la fenetre
    depasse 1. `noms_interface` n'est utile qu'a la VENTILATION du residu : sans lui, le champ
    `ventilation` reste `None` -- PAS MESURE, jamais un dictionnaire vide qui se lirait « aucune
    ligne dans cette cause ». `relaches` desarme des crans NOMMES (cf. `CRANS`) : c'est une
    MESURE, jamais un regime de service.
    """
    if traverse is None:
        traverse = fenetre > 1
    rx_un_nom = _regex_noms(noms_interface) if noms_interface else None
    if relaches or historique or profondeur != PROFONDEUR_APPEL or virgule_bloquante:
        couples = _regex_couples(traverse, relaches, historique, profondeur, virgule_bloquante)
    else:
        couples = RE_COUPLES_ML if traverse else RE_COUPLES
    rx_nom_seul = RE_NOM_SEUL_ML if traverse else RE_NOM_SEUL
    ventile: dict[str, list[tuple[str, int, str]]] = {c: [] for c in CAUSES}
    retenues, noms_seuls, autre_iface, sans_couple, exemptees = [], [], 0, 0, 0
    appel = _id_appel(fenetre, traverse, relaches, historique, profondeur,
                      virgule_bloquante, rx_un_nom is not None)
    cch = cache()
    for rel, texte in textes_balayes():
        #: ⚠ LE PRE-FILTRE RESTE JOUE A CHAQUE RUN, ET N'ENTRE PAS AU CACHE. Il coute une
        #: recherche de sous-chaine sur un texte deja lu ; cacher les ~2600 fichiers qu'il ecarte
        #: gonflerait l'artefact versionne sans rien economiser.
        if "slot" not in texte:
            continue
        lot = cch.contribution(rel, appel, verdict_cache.sha_texte(texte),
                               lambda r=rel, t=texte: _contribution(
                                   r, t, fenetre, couples, rx_nom_seul, rx_un_nom))
        retenues += lot[0]
        noms_seuls += lot[1]
        autre_iface += lot[2]
        sans_couple += lot[3]
        exemptees += lot[4]
        for cause, v in lot[5].items():
            ventile[cause] += v
    #: Deduplication : plusieurs formes -- et, en fenetre, plusieurs BLOCS -- peuvent capter le
    #: MEME couple. La cle inclut la ligne du NOM : deux noms identiques a deux endroits
    #: differents sont deux citations.
    #: ⚠ LES NON-FRANCHISSANTS PASSENT D'ABORD. Un meme couple peut etre capte par une forme qui
    #: franchit une virgule ET par une qui n'en franchit pas ; garder l'exemplaire franchissant
    #: ferait mentir `franchit_virgule` sur un couple parfaitement local (#477-r42).
    uniques: list[Citation] = []
    deja_vu: set[tuple[str, int, int, str, int]] = set()
    for c in sorted(retenues, key=lambda x: x.franchit_virgule):
        cle = (c.fichier, c.ligne, c.slot, c.noms[0], c.ligne_nom)
        if cle in deja_vu:
            continue
        deja_vu.add(cle)
        uniques.append(c)
    #: LA CITATION LA PLUS LOCALE GAGNE (#477-r42) -- cf. `ceder_aux_locaux`. Le cran est
    #: RELACHABLE : le desarmer publie ce qu'il ecarte, dont les DEUX faux de l'enumeration.
    cedes: list[Citation] = []
    if "priorite-non-franchissement" not in relaches:
        uniques, cedes = ceder_aux_locaux(
            uniques, lambda c: c.franchit_virgule,
            lambda c: (c.fichier, c.ligne, c.slot),
            lambda c: (c.fichier, c.ligne_nom, c.noms[0]))
    return uniques, noms_seuls, Ecartees(
        autre_interface=autre_iface, sans_couple=sans_couple, exemptees=exemptees,
        cedes_au_non_franchissement=tuple(
            "%s:%d slot 0x%x = %s (nom lu ligne %d) | %s"
            % (c.fichier, c.ligne, c.slot, c.noms[0], c.ligne_nom, c.texte[:100])
            for c in cedes),
        ventilation=None if rx_un_nom is None
        else {c: tuple(v) for c, v in ventile.items()})


def confronter_noms(cits: list[CitationNom],
                    table: dict[int, tuple[str, int]]) -> list[str]:
    """Les citations par NOM SEUL dont le nom n'est a AUCUN slot de l'interface.

    Il n'y a pas de numero a contredire : le seul verdict possible est l'APPARTENANCE. C'est
    suffisant -- mesure #477-r32, la seule faute du corpus etait de cette forme.
    """
    connus = {v[0] for v in table.values()}
    return ["%s:%d le slot nomme %s n'existe PAS sur l'interface (%d methodes) | %s"
            % (c.fichier, c.ligne, c.nom, len(connus), c.texte)
            for c in cits if c.nom not in connus]


def confronter(cits: list[Citation], table: dict[int, tuple[str, int]]) -> tuple[list[str], list[str]]:
    faux_nom: list[str] = []
    faux_arite: list[str] = []
    for c in cits:
        attendu = table.get(c.slot)
        if attendu is None:
            faux_nom.append("%s:%d slot %d INCONNU de l'interface (%d slots) | %s"
                            % (c.fichier, c.ligne, c.slot, len(table), c.texte))
            continue
        nom, nargs = attendu
        if nom not in c.noms:
            #: ⚠ ON DIT OU LE NOM CITE VIT REELLEMENT. « le metadata dit X » seul laisse croire
            #: a une faute de frappe ; savoir que le nom cite est a `0x7d` et pas a `0x7c` fait
            #: la difference entre corriger le NOM et corriger le SLOT (#477-r32).
            ailleurs = sorted(s for s, v in table.items() if v[0] in c.noms)
            faux_nom.append("%s:%d slot 0x%x : le site nomme %s, le metadata dit %s ; %s est "
                            "aux slots %s | %s"
                            % (c.fichier, c.ligne, c.slot, "/".join(c.noms), nom,
                               "/".join(c.noms),
                               ", ".join("0x%x" % s for s in ailleurs) or "aucun", c.texte))
            continue
        if c.args is not None and c.args != nargs:
            faux_arite.append("%s:%d slot 0x%x %s : %d argument(s) au site, %d dans la "
                              "signature | %s" % (c.fichier, c.ligne, c.slot, nom, c.args,
                                                  nargs, c.texte))
    return faux_nom, faux_arite


# ------------------------------------------------------------------- contre-epreuve


MUTANTS = {
    "slot-decale": "decale tous les slots de 1 (etage 2 doit MORDRE)",
    "nom-permute": "permute deux noms de la table (etages 2 et 3 doivent MORDRE)",
    "table-tronquee": "coupe la table a 40 slots (etage 3 doit MORDRE)",
    "arite-fausse": "ajoute 1 a tous les param_count (etage 4 doit MORDRE)",
    #: ⚠ CELUI-CI MUTE LES CITATIONS QUI ENJAMBENT, PAS LA TABLE. Les quatre autres mordaient
    #: deja avant #477-r32 : ils ne disent RIEN de l'elargissement. Un mutant qui ne peut pas
    #: distinguer fenetre=1 de fenetre=N ne garde pas la fenetre (mesure #477-r30 : ses quatre
    #: mutants herites mordaient dans les DEUX regimes, donc aucun ne gardait le cran ajoute).
    #:
    #: ⚠ ET IL NE PEUT PAS PORTER SUR LA TABLE, contrairement a celui de #477-r30 -- c'est une
    #: MESURE de ce corpus, pas un choix : les 16 couples enjambants se repartissent sur 8 slots
    #: (`0x06`, `0x21`, `0x3c`, `0x43`, `0x51`, `0x71`, `0x76`, `0x77`), et les 8 sont AUSSI
    #: cites sur une seule ligne ailleurs. Toute mutation de la TABLE mordrait donc dans les deux
    #: regimes, exactement comme les quatre mutants herites. La mutation porte donc sur la
    #: CITATION -- « un couple a cheval se voit attribuer le nom du slot voisin » --, qui est
    #: precisement la faute que l'elargissement existe pour trouver, et qui n'a aucun porteur a
    #: `fenetre = 1` puisqu'il n'y a alors aucun couple a cheval.
    "enjambants-decales": "attribue au couple qui ENJAMBE une ligne le nom du slot VOISIN -- "
                          "inerte a fenetre=1, doit MORDRE au-dela",
    #: ⚠ MEME RAISON, UN CRAN PLUS LOIN (#477-r36). Les cinq mutants ci-dessus mordent DEJA sans
    #: les trois formes neuves : aucun ne dit quoi que ce soit de l'appel absorbe, de la
    #: resolution commentee ni du placeholder. Celui-ci porte sur les couples que SEULES ces
    #: formes rapportent (`forme >= 3 or appel_absorbe`) et il est INERTE dans le regime
    #: `historique` -- ou il REFUSE, plutot que de rendre une mutation vide qui passerait pour
    #: appliquee.
    "formes-r36-decalees": "attribue au couple capte par une forme NEUVE (appel absorbe, "
                           "resolution commentee, placeholder) le nom du slot VOISIN -- inerte "
                           "en regime historique, doit MORDRE en service",
    #: ⚠ MEME RAISON, ENCORE UN CRAN PLUS LOIN (#477-r42). Les six mutants ci-dessus mordent DEJA
    #: sans le franchissement de virgule : aucun ne dit quoi que ce soit du cran qui l'autorise.
    #: Celui-ci porte sur les couples que SEUL ce franchissement rapporte, et il REFUSE en regime
    #: `--virgule-bloquante`, ou il n'a rien a muter.
    "franchissants-decales": "attribue au couple qui a FRANCHI une virgule le nom du slot "
                             "VOISIN -- inerte en regime --virgule-bloquante, doit MORDRE en "
                             "service",
}


def _voisin_different(table: dict[int, tuple[str, int]], slot: int) -> str | None:
    """Le nom d'un slot voisin qui DIFFERE du sien, ou `None`.

    ⚠ LE VOISIN DOIT PORTER UN NOM DIFFERENT. L'interface a des SURCHARGES a des slots adjacents
    (`0x2e`/`0x2f` = `RefreshEffects`, `0x34`/`0x35` = `ComputerAction`) : prendre le voisin
    immediat rendrait une mutation NULLE qui passerait pour appliquee.
    """
    for d in (1, -1, 2, -2):
        v = table.get(slot + d)
        if v is not None and v[0] != table[slot][0]:
            return v[0]
    return None


def muter(table: dict[int, tuple[str, int]], nom: str,
          cits: list[Citation]) -> tuple[dict[int, tuple[str, int]], list[Citation]]:
    """(table mutee, citations mutees). UN SEUL des deux bouge par mutant, jamais les deux.

    La signature rend DEUX objets parce que le mutant de la fenetre ne peut pas porter sur la
    table (cf. `MUTANTS`). Les quatre mutants herites rendent les citations INCHANGEES.
    """
    if nom == "slot-decale":
        return {s + 1: v for s, v in table.items()}, cits
    if nom == "nom-permute":
        #: Les deux slots a permuter sont DERIVES des citations reelles, jamais choisis en dur :
        #: permuter deux slots que personne ne cite rend une contre-epreuve INERTE qui passe
        #: pour mordante (mesure : `22 <-> 99` ne mordait pas -- aucun site ne les nomme).
        attestes = [s for s in dict.fromkeys(c.slot for c in cits) if s in table]
        if len(attestes) < 2:
            raise SystemExit("contre-epreuve IMPOSSIBLE : moins de 2 slots attestes -- "
                             "ce mutant ne peut pas mordre, et on ne le fait pas semblant.")
        out = dict(table)
        a, b = attestes[0], attestes[1]
        out[a], out[b] = out[b], out[a]
        return out, cits
    if nom == "table-tronquee":
        return {s: v for s, v in table.items() if s < 40}, cits
    if nom == "arite-fausse":
        return {s: (n, k + 1) for s, (n, k) in table.items()}, cits
    if nom == "enjambants-decales":
        #: On reecrit le NOM de chaque couple qui enjambe une ligne, en y mettant celui du slot
        #: VOISIN. Si l'appariement en fenetre disparait, il n'y a plus aucun couple enjambant,
        #: la mutation ne porte sur rien, et le mutant devient INERTE -- c'est exactement ce
        #: qu'on veut pouvoir constater.
        #: ⚠ LE VOISIN DOIT PORTER UN NOM DIFFERENT (cf. `_voisin_different`).
        return table, _decaler(table, cits, lambda c: c.ligne != c.ligne_nom, "ENJAMBANT",
                               "la fenetre")
    if nom == "formes-r36-decalees":
        return table, _decaler(table, cits, lambda c: c.forme >= 3 or c.appel_absorbe,
                               "capte par une forme NEUVE (#477-r36)",
                               "l'appel absorbe / la resolution commentee / le placeholder")
    if nom == "franchissants-decales":
        return table, _decaler(table, cits, lambda c: c.franchit_virgule,
                               "ayant FRANCHI une virgule (#477-r42)",
                               "le franchissement de virgule et sa priorite au plus local")
    raise SystemExit("mutant inconnu : %s" % nom)


def _decaler(table: dict[int, tuple[str, int]], cits: list[Citation], porte, quoi: str,
             cran: str) -> list[Citation]:
    """Reecrit le NOM des citations retenues par `porte` avec celui d'un slot VOISIN.

    Si aucune citation ne porte le cran mesure, le module REFUSE : un mutant qui n'a rien a
    muter rend une mutation VIDE qui passe pour appliquee, et c'est precisement ce qu'il ne
    faut pas laisser croire.
    """
    mutees: list[Citation] = []
    touchees = 0
    for c in cits:
        autre = (_voisin_different(table, c.slot)
                 if (porte(c) and c.slot in table) else None)
        if autre is None:
            mutees.append(c)
            continue
        touchees += 1
        mutees.append(replace(c, noms=(autre,)))
    if not touchees:
        raise SystemExit("contre-epreuve IMPOSSIBLE : aucun couple %s a muter -- ce mutant ne "
                         "peut pas discriminer %s, et on ne fait pas semblant qu'il mord."
                         % (quoi, cran))
    return mutees


def jouer(table: dict[int, tuple[str, int]], cits: list[Citation],
          derive: list[il2cpp_metadata.MethodDef] | None,
          noms_seuls: list[CitationNom] | tuple[()] = ()) -> tuple[int, int, int, int]:
    """(ecarts etage 2, noms faux etage 3, arites fausses etage 4, noms seuls faux etage 5).

    ⚠ L'ETAGE 5 EST DANS LE TUPLE, sinon aucun mutant ne le garderait : un mutant se juge sur
    ce que `jouer` RESTITUE, et un etage absent du tuple est un etage sans contre-epreuve.
    """
    if derive is None:
        ecarts = 0
    else:
        ecarts = sum(1 for m in derive if table.get(m.slot) != (m.name, m.param_count))
    faux_nom, faux_arite = confronter(cits, table)
    return ecarts, len(faux_nom), len(faux_arite), len(confronter_noms(list(noms_seuls), table))


# ------------------------------------------------------------------------------- main


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--regenerer", action="store_true",
                    help="reecrit l'entree versionnee depuis le metadata installe")
    ap.add_argument("--mutants", action="store_true",
                    help="contre-epreuve : chaque mutant doit faire MORDRE un etage")
    ap.add_argument("--fenetre", type=int, default=FENETRE, metavar="N",
                    help="lignes sur lesquelles un couple (slot, nom) peut s'etaler "
                         "(defaut %d ; 1 = l'etat d'avant #477-r32)" % FENETRE)
    ap.add_argument("--courbe", action="store_true",
                    help="re-derive le CHOIX de la fenetre : gain et bruit pour N = 1..8")
    ap.add_argument("--ventiler", action="store_true",
                    help="detaille CE QUI RESTE hors couverture, par CAUSE (residu #477-r34)")
    ap.add_argument("--relacher", action="store_true",
                    help="desarme CHAQUE cran conservateur separement et publie ce qu'il CACHE")
    ap.add_argument("--profondeur", action="store_true",
                    help="re-derive le CHOIX de PROFONDEUR_APPEL : gain et bruit pour p = 1..5")
    ap.add_argument("--historique", action="store_true",
                    help="rejoue le regime d'AVANT #477-r36 (formes A/B/C, sans appel absorbe)")
    ap.add_argument("--virgule-bloquante", action="store_true",
                    help="rejoue le regime d'AVANT #477-r42 (la virgule ARRETE le remplissage)")
    ap.add_argument("--verifier-cache", action="store_true",
                    help="RECALCULE tout en ignorant le cache versionne et le confronte entree "
                         "par entree (#486-r1) -- le seul controle qui voie une entree falsifiee "
                         "de facon coherente")
    args = ap.parse_args()

    if args.verifier_cache:
        #: MODE ESPION : le fichier est charge, jamais servi. Le run normal ci-dessous recalcule
        #: donc TOUT, et `verdict_cache.verifier` confronte les deux.
        global _CACHE
        _CACHE = verdict_cache.CacheCliquet(
            nom="probe_477r24r1_slots_interface",
            contexte=verdict_cache.sha_fichiers_texte(Path(__file__).resolve(),
                                                HERE / "il2cpp_metadata.py", tsv_path()),
            encoder=_encoder, decoder=_decoder, relire=False)

    print("=== #477-r24-r1 -- slots de Core.Services.IOperationProcessor ===")
    print("build qui fait foi : %s" % current_build())

    table = deriver()

    if args.regenerer:
        if table is None:
            raise SystemExit("REFUSE : impossible de regenerer sans metadata (cf. etage 1).")
        p = ecrire_tsv(table)
        print("    entree versionnee reecrite : %s (%d slots)"
              % (p.relative_to(REPO).as_posix(), len(table)))
        print("    NE PAS OUBLIER : `git add %s`" % p.relative_to(REPO).as_posix())
        return 0

    versionne = lire_tsv()
    ecarts = cliquet(table, versionne)

    if args.courbe:
        print()
        print("=== LE CHOIX DE LA FENETRE, RE-DERIVE (fenetre en service : %d) ===" % FENETRE)
        print("  W  citations  enjambantes  nom_seul  sans_couple  desaccords  arites_fausses")
        for w in (1, 2, 3, 4, 5, 6, 8):
            c, ns, e = recolter(fenetre=w)
            fn, fa = confronter(c, versionne)
            print("  %2d   %6d     %6d     %6d     %6d      %6d        %6d"
                  % (w, len(c), sum(1 for x in c if x.ligne != x.ligne_nom), len(ns),
                     e.sans_couple, len(fn), len(fa)))
        print("  Lire : `citations` et `sans_couple` disent le GAIN, les deux dernieres ce que")
        print("  l'elargissement FAIT SORTIR. La ou les deux premieres colonnes cessent de")
        print("  bouger, elargir n'apporte plus -- et le cout en temps, lui, continue.")
        return 0

    if args.profondeur:
        print()
        print("=== LA PROFONDEUR D'IMBRICATION, RE-DERIVEE (en service : %d) ==="
              % PROFONDEUR_APPEL)
        print("   p  citations  absorbees  arite_confrontee  sans_couple  desaccords")
        for p in (1, 2, 3, 4, 5):
            c, _ns, e = recolter(fenetre=args.fenetre, profondeur=p)
            fn, _fa = confronter(c, versionne)
            print("  %2d   %6d     %6d            %6d       %6d      %6d"
                  % (p, len(c), sum(1 for x in c if x.appel_absorbe),
                     sum(1 for x in c if x.args is not None), e.sans_couple, len(fn)))
        print("  Lire : un appel PLUS PROFOND que `p` n'est pas absorbe -- le nom de sa ligne")
        print("  reste bloque, et le slot va chercher celui de la ligne SUIVANTE. La ou les")
        print("  colonnes cessent de bouger, approfondir n'apporte plus.")
        return 0

    if args.relacher:
        print()
        print("=== CE QUE CHAQUE CRAN CACHE (il est desarme SEPAREMENT) ===")
        base, _bns, _be = recolter(fenetre=args.fenetre)
        #: ⚠ LA CLE INCLUT LA LIGNE DU NOM (#477-r42). Sans elle, un couple re-admis par un
        #: relachement mais deja apparie AUTREMENT sur la meme ligne passait pour « pas neuf » :
        #: `priorite-non-franchissement` rendait alors **0**, et un cran qui rend zero se lit
        #: comme gratuit alors qu'il ECARTE. Un compte qui ne dit pas ce qu'il filtre est
        #: exactement le vice que cette famille de probes existe pour ne pas repeter.
        connus = {(c.fichier, c.ligne, c.slot, c.noms[0], c.ligne_nom) for c in base}
        connus_nat = {v[0] for v in versionne.values()}
        for cran, quoi in CRANS.items():
            try:
                lot, _ns, _e = recolter(fenetre=args.fenetre, relaches=(cran,))
            except re.error as exc:                                       # noqa: BLE001
                print("  %-22s PAS MESURE -- motif invalide (%s)" % (cran, exc))
                continue
            neufs = [c for c in lot
                     if (c.fichier, c.ligne, c.slot, c.noms[0], c.ligne_nom) not in connus]
            faux = [c for c in neufs if versionne.get(c.slot, ("", 0))[0] != c.noms[0]]
            print("  %-22s %3d couple(s) neuf(s), dont %d au NOM qui ne concorde PAS"
                  % (cran, len(neufs), len(faux)))
            print("      cause du cran : %s" % quoi)
            for c in neufs:
                verdict = ("CONCORDE" if versionne.get(c.slot, ("", 0))[0] == c.noms[0]
                           else ("nom INCONNU de l'interface"
                                 if c.noms[0] not in connus_nat else "nom d'un AUTRE slot"))
                print("        %-8s %s:%d slot 0x%x -> %s | %s"
                      % (verdict if verdict == "CONCORDE" else "DOUTEUX", c.fichier, c.ligne,
                         c.slot, c.noms[0], c.texte[:90]))
        return 0

    cits, noms_seuls, ecartees = recolter(
        fenetre=args.fenetre, historique=args.historique,
        virgule_bloquante=args.virgule_bloquante,
        noms_interface=frozenset(v[0] for v in versionne.values()))
    enjambantes = sum(1 for c in cits if c.ligne != c.ligne_nom)
    print("[3] CITATIONS : %d attestation(s) sur %d fichier(s), appariees sur une FENETRE de "
          "%d ligne(s)" % (len(cits), len({c.fichier for c in cits}), args.fenetre))
    print("      dont %d couple(s) qui ENJAMBENT un saut de ligne -- invisibles avant #477-r32, "
          "qui exigeait slot et nom ADJACENTS" % enjambantes)
    #: ⚠ LA ZONE AVEUGLE SE PUBLIE AVEC SON RETRECISSEMENT, pas seulement avec sa taille.
    #: Un cliquet dont on ne sait pas si l'angle mort a bouge est un inventaire (#477-r30).
    if args.fenetre > 1:
        ref_cits, _ref_noms, ref = recolter(fenetre=1)
        print("      REFERENCE fenetre=1 (l'etat d'avant #477-r32) : %d attestation(s), "
              "%d ligne(s) sans couple" % (len(ref_cits), ref.sans_couple))
        print("      RETRECISSEMENT de la zone aveugle : %d -> %d ligne(s) sans couple (-%d)"
              % (ref.sans_couple, ecartees.sans_couple, ref.sans_couple - ecartees.sans_couple))
    if not args.historique:
        #: La seconde REFERENCE : le regime d'avant #477-r36, a fenetre EGALE. Sans elle, le
        #: gain des trois formes neuves se confondrait avec celui de la fenetre.
        h_cits, _h_noms, h_ec = recolter(fenetre=args.fenetre, historique=True)
        neuves = sum(1 for c in cits if c.forme >= 3 or c.appel_absorbe)
        print("      REFERENCE historique (l'etat d'avant #477-r36, meme fenetre) : %d "
              "attestation(s), %d ligne(s) sans couple" % (len(h_cits), h_ec.sans_couple))
        print("      dont %d couple(s) que SEULES les formes de #477-r36 rapportent "
              "(appel absorbe, resolution commentee, placeholder)" % neuves)
    if not args.virgule_bloquante:
        #: La TROISIEME reference : le regime d'avant #477-r42, a fenetre EGALE. Sans elle, le
        #: gain du franchissement de virgule se confondrait avec celui des formes de #477-r36.
        v_cits, _v_noms, v_ec = recolter(fenetre=args.fenetre, virgule_bloquante=True)
        print("      REFERENCE --virgule-bloquante (l'etat d'avant #477-r42, meme fenetre) : %d "
              "attestation(s), %d ligne(s) sans couple" % (len(v_cits), v_ec.sans_couple))
        print("      dont %d couple(s) qui ont FRANCHI une virgule -- invisibles quand elle "
              "arretait le remplissage" % sum(1 for c in cits if c.franchit_virgule))
    print("      ECARTEES, et c'est DIT :")
    print("        %5d ligne(s) dont le recepteur ne designe pas cet OperationProcessor "
          "(autre interface -- residu #477-r25)" % ecartees.autre_interface)
    print("        %5d ligne(s) qui citent un slot SANS lui accoler de nom, MEME sur %d "
          "ligne(s) -- rien a contredire, donc rien a garder"
          % (ecartees.sans_couple, args.fenetre))
    print("        %5d ligne(s) exemptees au site par %s" % (ecartees.exemptees,
                                                            MARQUEUR_REFUTE))
    print("        %5d fichier(s) EXCLU(S) et nomme(s) : %s" % (len(EXCLUS), ", ".join(EXCLUS)))
    print("        %5d couple(s) ayant FRANCHI une virgule et CEDE a une attribution sans "
          "franchissement (#477-r42)" % len(ecartees.cedes_au_non_franchissement))
    for f in ecartees.cedes_au_non_franchissement:
        print("            %s" % f)
    #: ⚠ LE RESIDU SE PUBLIE AVEC SA CAUSE. Un compte seul est un inventaire ; c'est la cause qui
    #: en fait une tache, et qui dit lequel des trois tas est reellement un gisement (#477-r34).
    vent = ecartees.ventilation
    if vent is None:
        print("      VENTILATION du residu : PAS MESUREE (pas de table de noms fournie)")
    else:
        assert sum(len(v) for v in vent.values()) == ecartees.sans_couple
        print("      VENTILATION de ces %d lignes -- la somme des causes VAUT le total :"
              % ecartees.sans_couple)
        for cause, quoi in CAUSES.items():
            print("        %5d  %-24s %s" % (len(vent[cause]), cause, quoi))
        if args.ventiler:
            for cause in CAUSES:
                print()
                print("      --- %s ---" % cause)
                for rel, no, txt in vent[cause]:
                    print("        %s:%d %s" % (rel, no, txt))
    faux_nom, faux_arite = confronter(cits, versionne)
    print("      %d citation(s) au NOM faux" % len(faux_nom))
    for f in faux_nom:
        print("        %s" % f)
    print("[4] ARITE     : %d citation(s) dont le compte d'arguments contredit la signature"
          % len(faux_arite))
    for f in faux_arite:
        print("        %s" % f)
    faux_seuls = confronter_noms(noms_seuls, versionne)
    print("[5] NOM SEUL  : %d slot(s) designe(s) par leur NOM sans numero, dont %d dont le nom "
          "n'est a AUCUN slot" % (len(noms_seuls), len(faux_seuls)))
    for f in faux_seuls:
        print("        %s" % f)

    if args.mutants:
        print()
        print("=== CONTRE-EPREUVE (a_mordu est rendu SEPAREMENT du verdict) ===")
        base = jouer(versionne, cits, table, noms_seuls)
        for nom, quoi in MUTANTS.items():
            mt, mc = muter(versionne, nom, cits)
            mut = jouer(mt, mc, table, noms_seuls)
            mordu = mut != base
            print("  %-18s a_mordu=%-5s  cliquet %d -> %d, nom %d -> %d, arite %d -> %d, "
                  "nom_seul %d -> %d   (%s)"
                  % (nom, str(mordu).upper(), base[0], mut[0], base[1], mut[1],
                     base[2], mut[2], base[3], mut[3], quoi))

    #: LE CACHE (#486-r1) -- il n'imprime RIEN dans le regime normal, et c'est voulu : la sortie
    #: avec cache chaud doit etre BIT POUR BIT celle d'un run a froid, sans quoi le controle de
    #: fidelite ne pourrait pas les comparer. Il n'est ecrit que dans le regime CANONIQUE : un
    #: `--fenetre N` ou un `--historique` produirait d'autres jeux de parametres, et les ecrire
    #: chasserait du fichier les entrees que la boucle de merge, elle, utilise.
    canonique = (args.fenetre == FENETRE and not args.historique
                 and not args.virgule_bloquante)
    if args.verifier_cache:
        divergences = verdict_cache.verifier(cache())
        print()
        print("=== VERIFICATION DU CACHE VERSIONNE (#486-r1) ===")
        print("  entrees sur disque : %d   recalculees : %d"
              % (len(cache()._sur_disque), len(cache()._vues)))
        for d in divergences:
            print("  DIVERGENCE %s" % d)
        if divergences:
            #: rc DEDIE : ce n'est pas le verdict du cliquet sur le depot, c'est le CACHE qui
            #: ment. Les confondre ferait corriger le code a la place de l'artefact.
            print("  rc=3 -- le cache versionne n'atteste PAS ce que le calcul rend. Le")
            print("  REGENERER : python scripts/python/probe_477r24r1_slots_interface.py")
            return 3
        print("  OK -- chaque entree du cache vaut ce que le recalcul integral produit.")
    _ecrit = None
    if canonique and not args.verifier_cache:
        # #486-r22 : on garde le cache pour demander PLUS BAS si cette reecriture a CHANGE le
        # fichier versionne -- un vrai rouge de gisement prime sur un rouge d'intendance.
        _ecrit = cache()
        _ecrit.enregistrer()

    rouge = bool(ecarts or faux_nom or faux_arite or faux_seuls)
    print()
    print("VERDICT : %s" % ("ROUGE" if rouge else "VERT"))
    if table is None:
        print("  NB : l'etage 1 n'a PAS ete mesure -- ce vert ne dit rien du metadata,")
        print("       seulement que le depot est coherent avec l'entree versionnee.")
    if rouge:
        return 1
    return verdict_cache.rendre_compte_du_cache(_ecrit, 0) if _ecrit is not None else 0


if __name__ == "__main__":
    raise SystemExit(main())
