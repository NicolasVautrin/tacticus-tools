"""#477-r25 -- les slots des AUTRES interfaces que `Core.Services.IOperationProcessor`.

    python scripts/python/probe_477r25_slots_autres_interfaces.py
    python scripts/python/probe_477r25_slots_autres_interfaces.py --recenser
    python scripts/python/probe_477r25_slots_autres_interfaces.py --regenerer
    python scripts/python/probe_477r25_slots_autres_interfaces.py --mutants

CE QUE CE PROBE TRANCHE
-----------------------
`#477-r24-r1` a montre que le mapping slot <-> methode SE LIT dans `Il2CppMethodDefinition.slot`,
et l'a derive pour UNE interface. Il a laisse les autres non confrontees, en signalant que le
depot se contredit deja lui-meme (`case-27` place `GetAdjacentEnemies` au slot `0x7f`,
`case-250` au `0x7c`).

LE RETOURNEMENT : LES DEUX SONT LISIBLES, ET LE NOM NE DESIGNE PAS UN SLOT MAIS UN ENSEMBLE.
`GetAdjacentEnemies` occupe QUATRE slots consecutifs (`0x7d..0x80`), `GetAdjacentFriends` quatre
(`0x81..0x84`), `GetFreeAdjacentTiles` deux (`0x52`, `0x53`). Un desaccord « 0x7f contre 0x7c »
n'etait donc pas arbitrable par recoupement : les deux VALEURS etaient plausibles. Le metadata
tranche -- `0x7f` est `GetAdjacentEnemies`, `0x7c` est `GetAdjacentUnits` (4 arguments, amis
compris).

LA DERIVATION EST DIFFERENTE DE CELLE DE #477-r24-r1, ET C'EST VOULU
--------------------------------------------------------------------
`#477-r24-r1` localisait la table d'une interface par des ANCRES DE NOM : des methodes uniques
dont on prenait l'intersection des debuts de table possibles. Ca marche quand on connait des
noms caracteristiques -- et ca refuse des qu'une ancre appartient a une AUTRE interface
implementee par la meme classe (mesure : `IDamagePrediction` -> `INCOHERENT`, ses ancres ne
partagent aucun debut).

Ici la table est designee par le TYPE lui-meme : `il2cpp_metadata.locate_types` derive la grille
`Il2CppTypeDefinition` et lit `methodStart` / `method_count` de l'interface NOMMEE. Aucune ancre
de nom, donc aucune ambiguite d'interface -- et un CONTROLE CROISE gratuit : les deux mecanismes
rendent les MEMES 150 slots pour `Core.Services.IOperationProcessor`.

LES CINQ ETAGES
---------------
0. RECENSEMENT -- quelles interfaces le depot cite-t-il avec un slot ? Le perimetre n'est pas
   une liste ecrite d'avance : on balaie, on apparie le RECEPTEUR ecrit au site, et ce qui n'est
   PAS apparie est COMPTE ET IMPRIME (`--recenser` le detaille recepteur par recepteur).
1. DERIVATION -- lit les slots de chaque interface dans `global-metadata.dat`. Tri-etat :
   metadata absent ou desynchronise => `PAS MESURE`, jamais un zero ni un vert.
2. CLIQUET -- confronte a l'entree VERSIONNEE `data/symbols/<build>/metadata/interface_slots.tsv`.
   C'est elle qui rend les etages 3-4 jouables dans un worktree ou le jeu n'est pas installe.
3. CITATIONS -- confronte chaque couple (slot, nom) au metadata.
4. ARITE -- compare le nombre d'arguments ecrit au site au `param_count`.

CE QUE CE PROBE ECARTE, ET QUI EST COMPTE
-----------------------------------------
* les lignes dont AUCUN recepteur ne designe une interface couverte ;
* les lignes qui citent `IOperationProcessor` : elles sont gardees par
  `probe_477r24r1_slots_interface.py`, et les compter deux fois n'ajoute rien ;
* sur une ligne qui mentionne PLUSIEURS interfaces, les couples SANS qualificateur -- rien ne
  dit a laquelle ils se rapportent, et on ne DEVINE pas (mesure : `case-250-tau-targeting.md`
  en porte une avec trois interfaces sur la meme ligne) ;
* les couples dont le NOM n'existe a AUCUN slot de l'interface appariee. Indecidable
  mecaniquement : soit le recepteur est mal apparie, soit le nom est faux. Ils sont LISTES
  sous `NOM ABSENT DE L'INTERFACE`, jamais rendus verts ni rouges.

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import argparse
import bisect
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import build_pin                                                        # noqa: E402
import il2cpp_metadata                                                  # noqa: E402
#: ⚠ FOYER UNIQUE DES CRANS PARTAGES (#477-r36, elargi par #477-r42). Ils sont IMPORTES, jamais
#: recopies : les deux cliquets balayent le MEME depot, et deux motifs jumeaux qui derivent l'un
#: de l'autre rouvriraient ici le gisement que l'autre vient de fermer. `probe_477r24r1` ne fait
#: rien de couteux a l'import (il compile ses regex, c'est tout).
#:
#: * `_appel` / `PROFONDEUR_APPEL` -- l'absorption de la liste d'arguments (#477-r36) ;
#: * `_entre` -- LE REMPLISSAGE, avec sa capture (#477-r42). `_RENVOIS` est le meme tuple des
#:   deux cotes ; l'importer est ce qui garantit qu'il le RESTE ;
#: * `ceder_aux_locaux` -- la priorite au NON-FRANCHISSEMENT de virgule (#477-r42) ;
#: * `_regex_noms` -- le motif du RECENSEUR, dont #477-r36 a corrige le lookbehind (`$` HORS du
#:   lookbehind, faute de quoi un nom QUALIFIE est invisible et le gisement sous-compte de 48 %).
#:   La ventilation de ce probe (#477-r42) nait avec ce motif-la, jamais avec une copie.
from probe_477r24r1_slots_interface import (                             # noqa: E402
    _appel, _compter_args, _entre, _regex_noms, _RENVOIS, ceder_aux_locaux, PROFONDEUR_APPEL)
from symbols_layout import build_dir, current_build                     # noqa: E402

import repo_read                                                        # noqa: E402
import verdict_cache                                                    # noqa: E402

REPO = HERE.parent.parent

#: Les CLASSES CONCRETES qui ancrent la grille des types. Elles ne servent qu'a fixer
#: `methodStart` / `method_count` et a CONTROLER le resultat par leurs noms de methodes ;
#: aucune n'est l'interface cherchee. Il en faut au moins 3 (cf. `locate_types`).
ANCRES_TYPES = (
    ("Core.Services", "OperationProcessor"),
    ("IdunBattle.Core.Services", "BattleQuery"),
    ("IdunBattle.Core.Services", "AttackQuery"),
    ("IdunBattle.Core.Services", "MovementQuery"),
    ("IdunBattle.Core.Services", "DamageCalculations"),
    ("IdunBattle.Core", "MatchState"),
)

#: LES INTERFACES COUVERTES, et les RECEPTEURS par lesquels le depot les designe.
#: Le perimetre est DERIVE du recensement (`--recenser`) : chaque entree est ici parce que le
#: depot cite au moins un slot avec ce recepteur. Les recepteurs non apparies sont imprimes,
#: chiffres, et constituent le residu -- jamais un silence.
#: Chaque motif est confronte a la ligne en respectant la CASSE : `BattleQuery` (la classe) et
#: `battleQuery` (la variable) designent la meme interface, mais `Query` seul ne designe rien.
INTERFACES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("IdunBattle.Core.Services", "IBattleQuery",
     ("IBattleQuery", "BattleQuery", "battleQuery", "boardQuery", "board-query")),
    ("IdunBattle.Core.Services", "IAttackQuery",
     ("IAttackQuery", "AttackQuery", "attackQuery")),
    ("IdunBattle.Core", "IMatchState",
     ("IMatchState", "MatchState", "matchState")),
    ("IdunBattle.Core.Services", "IDamagePrediction",
     ("IDamagePrediction", "damagePrediction")),
    ("IdunBattle.Core.Services", "IDamagePredictionQuery",
     ("IDamagePredictionQuery", "DamagePredictionQuery")),
    ("IdunBattle.Core.Services", "IDamageCalculations",
     ("IDamageCalculations", "DamageCalculations")),
    ("IdunBattle.Core.Services", "IMovementQuery",
     ("IMovementQuery", "MovementQuery", "movementQuery")),
    ("IdunBattle.Core.Services", "ITargetingQuery",
     ("ITargetingQuery", "targetingQuery")),
    ("IdunBattle.Entities.Effects", "IEffect", ("IEffect",)),
    ("IdunBattle.DSL", "IAmountFormula", ("IAmountFormula",)),
    ("IdunBattle.DSL", "ITargetsSelector", ("ITargetsSelector",)),
    ("IdunBattle.AI.Playbook", "IPlaybook", ("IPlaybook",)),
    ("IdunBattle.Utils.PRNG", "IPseudoRNG", ("IPseudoRNG",)),
    ("IdunBattle.Streams", "IStreamDispatcher", ("IStreamDispatcher",)),
    ("IdunBattle.Entities.Pathfinding", "IPathfinders", ("IPathfinders",)),
    ("IdunBattle.Core.Services", "IUtilitiesDatabase", ("IUtilitiesDatabase",)),
    ("IdunBattle.Core.Services", "IEffectsDatabase", ("IEffectsDatabase",)),
    #: `AActiveAbility` est la classe abstraite qui l'implemente, et c'est SOUS CE NOM que le
    #: depot cite ses slots (`AActiveAbility$$IsDisabled` slot 0x13). L'omettre ne rendait pas
    #: le probe muet : il RATTACHAIT ces slots a l'interface voisine citee sur la meme ligne,
    #: et rendait FAUSSES deux citations JUSTES (mesure : 3 sites).
    ("IdunBattle.Entities.Abilities", "IActiveAbility",
     ("IActiveAbility", "AActiveAbility")),
)

#: DES TABLES QU'ON LIT SANS EN FAIRE DES RECEPTEURS (#1031). Un type entre ici quand le depot
#: CITE ses slots mais qu'en faire un recepteur rendrait FAUSSES des citations JUSTES.
#:
#: `IdunBattle.DSL.TargetsSelector` est le cas mesure. Le depot ecrit ses slots dans DEUX
#: referentiels a la fois, et les deux sont EXACTS (lus au `global-metadata.dat` de
#: `rnca9r7q6c`) :
#:
#:   vtable de la CLASSE   `TargetsSelector`  : Select = 23, Count = 24, SelectTile = 16
#:   table de l'INTERFACE  `ITargetsSelector` : Select =  0, Count =  2, SelectTile = 12
#:
#: `case-978-faces-decision-thousandsons-eldar.md:37` cite les DEUX sur une ligne (<< slot 23 =
#: `Select`, slot 24 = `Count`, recoupes par `ITargetsSelector` (slots 0 et 2) >>), et c'est
#: exactement ce qu'il faut ecrire : les deux appels sont des `klass+0x2b8` / `klass+0x2a8`.
#: Le probe, lui, rattachait 23 et 24 a la seule interface NOMMEE sur la ligne, et rendait
#: FAUSSE une citation JUSTE -- le vice deja mesure pour `AActiveAbility` juste au-dessus.
#:
#: ⚠ MAIS LE REMEDE D'`AActiveAbility` (un ALIAS de recepteur) EST REFUSE ICI, MESURE A L'APPUI.
#: Le depot qualifie majoritairement par le nom de CLASSE une methode dont il cite le slot
#: d'INTERFACE -- `backlog.md:438` << le slot de vtable 12 du selecteur EST
#: `IdunBattle.DSL.TargetsSelector$$SelectTile` >> (12 = interface ; la classe dit 16) et
#: `backlog.md:690` << `slot 1` = `IdunBattle.DSL.TargetsSelector$$SelectFirst` >> (1 =
#: interface ; la classe dit 5). Faire de `TargetsSelector` un recepteur retournerait ces DEUX
#: citations JUSTES en rouge : on aurait deplace la faute, pas ferme le gisement.
#:
#: D'ou ce troisieme etat, qui est celui que le probe sait deja rendre : le couple part en
#: `autre_iface` -- << JUSTE, mais sur TargetsSelector (le site ecrit ITargetsSelector) >> --
#: donc ni vert ni rouge, et LISTE. C'est le seul verdict que la mesure autorise.
REFERENTIELS: tuple[tuple[str, str], ...] = (
    ("IdunBattle.DSL", "TargetsSelector"),
)


def types_lus() -> tuple[tuple[str, str], ...]:
    """(namespace, nom) de TOUT type dont on lit la table -- interfaces PUIS referentiels.

    Foyer unique : la derivation, l'ecriture du TSV et le controle croise doivent porter sur le
    MEME ensemble. Les enumerer separement a trois endroits est precisement ce qui laisse une
    table derivee sans etre ecrite, ou ecrite sans etre controlee."""
    return tuple((ns, nom) for ns, nom, _ in INTERFACES) + REFERENTIELS


#: L'interface deja gardee par `probe_477r24r1_slots_interface.py`. Ses citations sont
#: ECARTEES ICI et comptees : les garder deux fois n'ajouterait aucune couverture.
DEJA_GARDEE = ("IOperationProcessor", "OperationProcessor", "processor")

#: L'entree versionnee, relative a `data/symbols/<build>/`.
TSV_REL = ("metadata", "interface_slots.tsv")

#: Les fichiers balayes. Perimetre DERIVE d'un `git ls-files`, jamais d'une liste ecrite.
BALAYAGE_GLOBS = ("docs/rl/*.md", "docs/*.md", "scripts/python/*.py",
                  "scripts/python/tests/**/*.py", "engine/**/*.py", "frida/hooks/**/*.ts")

#: Un slot cite. Toutes les formes que le depot ecrit (reprises de #477-r24-r1, qui les a
#: mesurees) : `<slot 0x16>`, `slot 0x16`, `slot **0x16**`, `slot `0x16``, `slot +6`, `vslot`.
#: ⚠ LE QUALIFICATIF EST INSENSIBLE A LA CASSE. Le depot ecrit aussi « slot d'INTERFACE »
#: (4 sites), et sans ce cran le motif ne reconnaissait meme pas le SLOT -- la ligne partait
#: dans `sans_couple` sans qu'aucune fenetre puisse rien y faire. Mesure : c'est ce qui cachait
#: la citation fausse de `displace.py` (« slot d'INTERFACE 0x4c = ...180Behind »), jumelle de
#: celle que #477-r30 a trouvee a la main dans le test (#477-r30).
_SLOT = r"v?slot\s*(?i:d'interface\s*|itf\s*)?[`*]{0,2}\+?(?P<n%d>0x[0-9a-fA-F]+|\d+)[`*]{0,2}"

#: Un nom de methode. Le lookahead doit interdire les CARACTERES DE MOT en plus du `$$`,
#: faute de quoi le moteur backtracke et rend un nom TRONQUE qui, lui, n'est plus suivi de
#: `$$` (mesure #477-r24-r1 : `FinishAttackOperatio`).
_NOM = r"(?P<nom%d>[A-Z][A-Za-z0-9_]{3,})(?![A-Za-z0-9$])"

#: Rien d'autre ne doit s'intercaler entre le slot et son nom -- ni un AUTRE `slot`, ni une
#: parenthese FERMANTE. Les deux faux positifs sont mesures (#477-r24-r1).
#: ⚠ NI UN RENVOI. Un pronom relatif ou un verbe d'invocation RETOURNE la relation : « le slot
#: `0xe` QUE `BattleQuery$$IsTileInRangeOfAnyAbility` interroge » designe le slot APPELE, pas
#: celui de la methode nommee -- et la citation est JUSTE (`0xe` =
#: `GetCurrentAndMovablePositionsFor`, ce qu'une requete de portee interroge en effet).
#: Mesure : 8 des 49 desaccords etaient de cette forme, tous FAUX.
#: ⚠ NI UNE PONCTUATION FORTE. Un `:` ou un `;` ouvre une nouvelle proposition, et le slot qui
#: suit ne qualifie plus la methode nommee avant : « `AttackQuery$$GetAllTilesInAbilityRange`
#: surcharge 4 arguments : slot 0x14, slot 0x13 » enumere les GATES evalues, qui sont des slots
#: d'`IActiveAbility`. Mesure : 2 sites, tous deux JUSTES, rendus faux sans ce cran.
#: ⚠ LA VIRGULE N'EST PLUS UN RENVOI, ET C'EST UNE MESURE (#477-r42). Elle arretait le
#: remplissage parce que le depot ecrit ses chaines de gates en ENUMERATION -- « slot 0x14
#: `AActiveAbility$$CanStillBeUsed`, slot 0x13 `AActiveAbility$$IsDisabled` » --, ou la forme
#: « nom PUIS slot » apparie le nom d'un element au slot du SUIVANT.
#:
#: Ce n'est PAS la virgule qui rend ce couple faux : c'est que `CanStillBeUsed` est DEJA apparie
#: a `0x14`, a sa GAUCHE IMMEDIATE, sans rien franchir. Le cran porte donc desormais sur ce
#: fait-la (`ceder_aux_locaux`, foyer partage), et la virgule redevient du texte. Mesure sur CE
#: corpus, a fenetre egale : **+23 couples JUSTES**, les **2** faux de l'enumeration DISSOUS,
#: **0** couple perdu. Le discriminant « la virgule ne bloque que si le remplissage traverse un
#: saut de ligne » a ete essaye et REFUSE : les deux faux de l'enumeration sont MONO-LIGNE, et
#: la citation juste qu'il faut liberer, elle, traverse -- il n'aide donc NI l'un NI l'autre.
#:
#: ⚠ NI UNE FLECHE. Dans « nom PUIS slot », une fleche marque un ENCHAINEMENT d'appels --
#: « `BattleQuery$$ReachedSummonCap` -> slot 0x52 » designe ce que la methode APPELLE. La
#: fleche reste licite dans la forme A, ou elle joue le role du signe egal.
#: (`_RENVOIS` est IMPORTE du foyer -- meme tuple des deux cotes, et il le reste.)


#: UNE CONTINUATION -- ce qui s'intercale la ou une espace suffirait, quand la phrase reprend
#: a la ligne suivante. `\s*` ne suffit PAS : le depot commente en Python (`#`), en TS (`//`,
#: `*` d'un bloc), et ecrit du markdown (`>`, `*`, `-`, `|` de tableau). Mesure : sans ce
#: motif, `displace.py` ecrivait « slot d'INTERFACE 0x4c = » en fin de ligne et
#: `BattleQuery$$GetMinimumTiles180Behind` sur la suivante -- une citation FAUSSE (0x4c est
#: `...180Front`) que le seul `#` de continuation rendait invisible (#477-r30).
_CONT = r"(?:[ \t]*\r?\n[ \t]*(?:\#+|//+|\*|>+|\||-)?[ \t]*)*[ \t]*"


def _esp(traverse: bool) -> str:
    """Le separateur « espace » des formes A et D. Il franchit la ligne en regime fenetre."""
    return _CONT if traverse else r"\s*"

#: L'arite n'est confrontee que si le site montre VRAIMENT ses arguments juste apres le couple.
#: AUCUNE espace toleree : un appel s'ecrit `Nom(args)`, jamais `Nom (args)`.
RE_APPEL = re.compile(r"\A[`*>]{0,2}\(")

#: Marqueur d'EXEMPTION au site : une ligne qui CITE une attribution refutee pour la nommer
#: comme telle porte legitimement un couple (slot, nom) faux. Compte et imprime, jamais muet.
MARQUEUR_REFUTE = "[slot-attribution:refute]"

#: Le probe est EXCLU de son propre balayage : sa documentation contient des exemples de
#: syntaxe qui ne sont pas des attributions. L'exclusion est NOMMEE et imprimee.
EXCLUS = ("scripts/python/probe_477r25_slots_autres_interfaces.py",)

#: Recepteurs a IGNORER au recensement : ce sont des mots de la prose ou des identifiants
#: trop generiques pour designer une interface. Ils sont comptes sous `NON APPARIES`.
_RE_RECEVEUR_CANDIDAT = re.compile(
    r"(?<![A-Za-z0-9_])(I[A-Z][A-Za-z0-9]{3,}|[A-Za-z][A-Za-z0-9_]{2,})\s*(?:\$\$|\.)")


#: LA FENETRE, en LIGNES, sur laquelle un couple (slot, nom) est apparie. `1` = l'etat de
#: #477-r25 : slot et nom sur la MEME ligne, ce qui ecartait 665 lignes.
#:
#: LA VALEUR EST MESUREE, PAS CHOISIE (`--courbe` la re-derive). Sur le corpus du 2026-08-06 :
#:
#:     W    citations   enjambantes   sans_couple   indecidables
#:     1        161            0           664            5
#:     2        230           59           641           12
#:     3        230           59           641           12
#:     6        230           59           641           12
#:
#: Le gain est INTEGRALEMENT capte a W=2, et la courbe est PLATE ensuite -- jusqu'a W=12,
#: pas une citation, pas un indecidable, pas un desaccord de plus. Ce plateau est un EFFET
#: DU CRAN LIGNE VIDE (cf. `_blocs`) : aucun couple du corpus n'enjambe trois lignes NON
#: VIDES. `3` est donc pris comme MARGE a cout mesure NUL -- une continuation en deux temps
#: (« slot 0x40 » / « est » / « `BattleQuery$$...` ») serait captee, et rien d'autre ne
#: bouge. Au-dela, meme absence de gain et cout en temps croissant (6,5 s a W=1, 16 s a W=8).
FENETRE = 3


@dataclass(frozen=True)
class Citation:
    fichier: str
    ligne: int
    iface: str
    slot: int
    nom: str
    args: int | None
    texte: str
    #: La ligne ou le NOM est ecrit. `ligne_nom != ligne` <=> le couple ENJAMBE un saut de
    #: ligne, donc il n'existe que grace a la fenetre (#477-r30).
    ligne_nom: int = 0
    #: Le remplissage a-t-il FRANCHI une virgule ? Donnee du cran `priorite-non-franchissement`
    #: (#477-r42). Seules les formes B et C ont un remplissage capturable.
    franchit_virgule: bool = False


#: LA VENTILATION DU RESIDU (#477-r42) -- LE RECENSEUR QUI N'EXISTAIT PAS.
#:
#: Ce probe ecartait ~647 lignes sous un compte NU (« citant un slot SANS lui accoler de nom »).
#: Il n'y avait pas de ventilation FAUSSE : il n'y en avait AUCUNE. Ecrire la ventilation, c'est
#: ecrire le recenseur -- et un recenseur ne peut pas rendre zero sur ce qu'il ne VISITE pas.
#:
#: TROIS EXIGENCES, reprises de la lecon la plus chere du dossier #270-r1 :
#: 1. il VISITE toutes les lignes ecartees, jamais un echantillon ni un seuil ;
#: 2. il DERIVE la cause du contexte (la FORME de la mention de slot, puis le voisinage), il ne
#:    la cherche pas dans une liste blanche de motifs -- une forme non prevue sort sous
#:    `autre (<forme>)`, et cette sortie est ATTEIGNABLE (mesure : `slotted`, `slots0`, tout ce
#:    que `RE_SLOT` reconnait mais qu'aucune forme nommee ne decrit) ;
#: 3. la somme des causes VAUT le total, et c'est ASSERTIONNE, pas affirme.
CAUSES = {
    "sans_numero": "la ligne mentionne un slot sans le CHIFFRER (prose, `slots` au pluriel, "
                   "tournure que `_SLOT` ne reconnait pas)",
    "nom_seul_sans_numero": "le slot est designe par un NOM sans numero (« slot `KillUnit` ») "
                            "-- il n'y a pas de couple a confronter, mais le nom, lui, est une "
                            "attestation que ce probe ne garde PAS (residu, cf. l'etage 5 de "
                            "#477-r32 sur l'autre cliquet)",
    "numero_sans_aucun_nom": "le slot est chiffre et AUCUN nom capitalise n'est ecrit dans la "
                             "fenetre -- rien a contredire",
    "numero_nom_hors_interface": "le slot est chiffre, un nom capitalise est dans la fenetre "
                                 "mais il n'est a AUCUN slot de l'interface appariee -- c'est "
                                 "le plus souvent une classe, une Operation ou un enum",
    "nom_ecarte_par_un_cran": "le slot est chiffre ET un nom de l'interface appariee est dans "
                              "la fenetre, mais un cran conservateur l'ecarte -- LE gisement",
}


@dataclass(frozen=True)
class Ecartees:
    """Ce que l'etage 3 n'a PAS retenu. Un compte filtre DIT ce qu'il filtre."""

    sans_interface: int = 0
    deja_gardee: int = 0
    multi_non_qualifie: int = 0
    sans_couple: int = 0
    exemptees: int = 0
    nom_absent: tuple[str, ...] = ()
    #: Les couples ENJAMBANTS ecartes parce que le MEME slot, a la MEME ligne, est deja apparie
    #: SUR SA LIGNE (#477-r36). Un compte filtre dit ce qu'il filtre : ils sont listes, pas tus.
    cedes_au_mono_ligne: tuple[str, ...] = ()
    #: Les couples ayant FRANCHI une virgule et cede a une attribution sans franchissement
    #: (#477-r42). Meme regle : listes, jamais tus.
    cedes_au_non_franchissement: tuple[str, ...] = ()
    #: `{cause: [(fichier, ligne, interface, texte), ...]}` pour les `sans_couple`. `None` =
    #: PAS MESURE (pas de tables fournies), jamais un dictionnaire vide qui se lirait « aucune
    #: ligne dans cette cause ». La somme des causes VAUT `sans_couple`.
    ventilation: dict[str, tuple[tuple[str, int, str, str], ...]] | None = None


# ------------------------------------------------------------------ etage 1 : DERIVATION


def deriver() -> dict[str, dict[int, tuple[str, int, int]]] | None:
    """`{interface: {slot: (nom, param_count, flags)}}`, ou `None` si le metadata manque.

    `None` = PAS MESURE. Ce n'est ni une table vide ni un vert.
    """
    try:
        meta_path = build_pin.global_metadata()
    except build_pin.BuildPinRefused as exc:
        print("[1] DERIVATION : PAS MESURE -- %s" % str(exc).splitlines()[0])
        return None
    methods_tsv = build_dir() / "frida" / "methods.tsv"
    #: ⚠ MEMOISATION, PAS TAUTOLOGIE (#486-r1) -- meme raisonnement que dans #477-r24-r1 : la cle
    #: contient le HASH DU BINAIRE DU JEU (`global-metadata.dat` + `frida/methods.tsv`), donc
    #: l'entree n'est reutilisee que si la source de la derivation est bit-a-bit identique. Les
    #: deux cotes de la confrontation de l'etage 2 restent INDEPENDANTS : ce qui est cache est
    #: le cote METADATA, jamais l'entree versionnee a laquelle il est confronte.
    #: 0,05 s de hachage pour ~14 s de derivation ; `None` -> on recalcule, jamais on n'atteste.
    sha = verdict_cache.sha_gros_fichiers(meta_path, methods_tsv)
    if sha is None:
        out, refus, lay = _deriver_vraiment(meta_path, methods_tsv)
    else:
        out, refus, lay = cache().contribution(
            "<global-metadata>", "deriver", sha,
            lambda: _deriver_vraiment(meta_path, methods_tsv))
    print("[1] DERIVATION : grille des types pas=%d, methodStart=+%d, method_count=+%d "
          "(%d ancres controlees par leurs noms)"
          % (lay[0], lay[1], lay[2], lay[3]))
    print("      %d interface(s) lues, %d slot(s) au total"
          % (len(out), sum(len(v) for v in out.values())))
    for r in refus:
        print("      REFUS : %s" % r)
    if refus:
        raise SystemExit("ROUGE : %d interface(s) declaree(s) ne se lisent pas dans le "
                         "metadata -- ont-elles change de nom ?" % len(refus))
    return out


def _deriver_vraiment(meta_path: Path, methods_tsv: Path) -> tuple[dict, list[str], tuple]:
    """La lecture REELLE du metadata. `(tables, refus, (pas, methodStart, method_count, ancres))`.

    Les quatre chiffres de la grille sont rendus parce que la ligne imprimee les cite : une
    sortie a chaud doit etre celle d'un run a froid, bit pour bit.
    """
    reader = il2cpp_metadata.read(meta_path)
    reader.locate(il2cpp_metadata.class_method_order(
        methods_tsv, "%s.%s" % ANCRES_TYPES[0]))
    ancres = [(ns, nm, il2cpp_metadata.class_method_order(methods_tsv, "%s.%s" % (ns, nm)))
              for ns, nm in ANCRES_TYPES]
    lay = reader.locate_types(ancres)
    out: dict[str, dict[int, tuple[str, int, int]]] = {}
    refus: list[str] = []
    for ns, nom in types_lus():
        try:
            table = reader.type_methods(ns, nom)
        except il2cpp_metadata.MetadataRefused as exc:
            refus.append("%s : %s" % (nom, str(exc).splitlines()[0]))
            continue
        #: ⚠ LES SLOTS `65535` SONT ECARTES, et seulement pour les REFERENTIELS de CLASSE.
        #: Une classe declare aussi des methodes NON VIRTUELLES (`.ctor`, `op_BitwiseAnd`,
        #: surcharges non-slottees) : le metadata leur donne `slot = 0xffff`, qui n'indexe
        #: rien. Les garder ecraserait la table sur une cle unique et fabriquerait un couple
        #: (65535, <derniere lue>) qu'aucun site ne cite. Une INTERFACE n'en porte pas.
        out[nom] = {m.slot: (m.name, m.param_count, m.flags)
                    for m in table if m.slot != 0xFFFF}
    return out, refus, (lay.step, lay.off_method_start, lay.off_method_count, len(lay.ancres))


# --------------------------------------------------------------------- etage 2 : CLIQUET


def tsv_path(build: str | None = None) -> Path:
    return build_dir(build).joinpath(*TSV_REL)


def lire_tsv() -> dict[str, dict[int, tuple[str, int, int]]]:
    p = tsv_path()
    if not p.is_file():
        raise SystemExit(
            "ROUGE : l'entree versionnee est absente (%s).\n"
            "  La regenerer sur une machine ou le jeu est installe :\n"
            "  python scripts/python/probe_477r25_slots_autres_interfaces.py --regenerer"
            % p.as_posix())
    out: dict[str, dict[int, tuple[str, int, int]]] = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        iface, slot, nom, nargs, flags = line.split("\t")[:5]
        out.setdefault(iface, {})[int(slot)] = (nom, int(nargs), int(flags, 0))
    return out


def ecrire_tsv(tables: dict[str, dict[int, tuple[str, int, int]]]) -> Path:
    p = tsv_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    lignes = [
        "# Slots d'interface LUS dans le champ `slot` d'`Il2CppMethodDefinition`",
        "# (global-metadata.dat du build %s), table designee par le TYPE via la grille" % current_build(),
        "# `Il2CppTypeDefinition` -- cf. `il2cpp_metadata.locate_types`.",
        "# `Core.Services.IOperationProcessor` n'est PAS ici : elle a sa propre entree",
        "# (`ioperationprocessor_slots.tsv`, #477-r24-r1).",
        "# Entree VERSIONNEE : c'est ce qui rend la garde jouable sans le jeu installe.",
        "# Regenerer : python scripts/python/probe_477r25_slots_autres_interfaces.py --regenerer",
        "# Les types de `REFERENTIELS` (classes) y figurent aussi : ils sont LUS pour dire",
        "# << juste, mais sur cette table-la >>, JAMAIS apparies a un recepteur (#1031).",
        "#interface\tslot\tmethode\tparam_count\tflags",
    ]
    for _, iface in types_lus():
        for slot in sorted(tables.get(iface, {})):
            nom, nargs, flags = tables[iface][slot]
            lignes.append("%s\t%d\t%s\t%d\t0x%04x" % (iface, slot, nom, nargs, flags))
    p.write_text("\n".join(lignes) + "\n", encoding="utf-8")
    return p


def cliquet(derive: dict[str, dict[int, tuple[str, int, int]]] | None,
            versionne: dict[str, dict[int, tuple[str, int, int]]]) -> list[str]:
    if derive is None:
        print("[2] CLIQUET   : PAS MESURE (pas de derivation a confronter) -- %d interface(s), "
              "%d slot(s) dans l'entree versionnee, utilises tels quels par les etages 3-4"
              % (len(versionne), sum(len(v) for v in versionne.values())))
        return []
    ecarts: list[str] = []
    for iface, table in derive.items():
        ref = versionne.get(iface)
        if ref is None:
            ecarts.append("%s absente de l'entree versionnee (%d slots derives)"
                          % (iface, len(table)))
            continue
        for slot, val in table.items():
            if ref.get(slot) != val:
                ecarts.append("%s slot %d : metadata %s/%d != versionne %s"
                              % (iface, slot, val[0], val[1],
                                 "ABSENT" if slot not in ref else "%s/%d" % ref[slot][:2]))
        for slot in sorted(set(ref) - set(table)):
            ecarts.append("%s slot %d (%s) versionne mais ABSENT du metadata"
                          % (iface, slot, ref[slot][0]))
    for iface in sorted(set(versionne) - set(derive)):
        ecarts.append("%s versionnee mais NON DERIVEE" % iface)
    print("[2] CLIQUET   : %d ecart(s) derivation vs entree versionnee" % len(ecarts))
    for e in ecarts[:20]:
        print("      %s" % e)
    return ecarts


# ------------------------------------------------------- etages 0 et 3 : CITATIONS


_FICHIERS: list[Path] | None = None
_TEXTES: list[tuple[str, str]] | None = None


def fichiers_balayes() -> list[Path]:
    """Le perimetre, DERIVE de `git ls-files`. Memoise : `recolter` est appele TROIS fois, plus
    `_compter_autre_casse` -- quatre traversees du meme perimetre, pour le meme resultat.
    Une panne de git reste un `SystemExit` PAS MESURE, jamais un perimetre vide.
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
    """`[(chemin relatif, texte)]` -- lecture PARALLELE, UNE fois pour les quatre traversees.

    Meme traitement d'erreur qu'avant : un fichier illisible ou non-UTF-8 est ABSENT (l'ancien
    `except (OSError, UnicodeDecodeError): continue`), donc les denominateurs ne bougent pas.
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
# LOCALITE ETABLIE. `_contribution` ne lit QUE le texte d'UN fichier : dans l'ancienne boucle,
# les seules variables partagees etaient des ACCUMULATEURS (`retenues`, les cinq compteurs,
# `nom_absent`, `recense` qui est purement additif, `ventile`), et le `vus_absents` de
# deduplication portait une cle COMMENCANT par `rel` -- intra-fichier par construction. Tout ce
# qui relie deux fichiers (dedup global, priorite au mono-ligne, `ceder_aux_locaux`,
# `confronter`) reste HORS cache et se rejoue integralement.
#
# Le CONTEXTE porte le source de CE cliquet, celui de #477-r24-r1 (dont il importe `_appel`,
# `_entre`, `_regex_noms`, `ceder_aux_locaux`) et l'entree versionnee des slots : editer une
# regex de l'un ou l'autre, ou changer de build, fait MANQUER toutes les entrees.

_CACHE: verdict_cache.CacheCliquet | None = None


def _encoder(v, appel: str = ""):
    #: ⚠ DEUX FORMES DE VALEUR DANS LE MEME CACHE, et c'est pourquoi l'encodeur recoit l'APPEL :
    #: `autre_casse` est un simple entier, les recoltes sont des nonuplets. Un encodeur qui ne
    #: regardait que la valeur levait `TypeError` -- faute attrapee par le controle de fidelite
    #: (le run SANS cache passait, celui AVEC cache plantait), pas par un test.
    if appel == "autre_casse":
        return v
    if appel == "deriver":
        out, refus, lay = v
        return [{k: [[s, n, pc, fl] for s, (n, pc, fl) in sorted(t.items())]
                 for k, t in out.items()}, list(refus), list(lay)]
    #: Les cles vides ne sont pas ecrites -- `recolter` accumule par `+=`, donc l'omission est
    #: VALEUR-PRESERVANTE, et l'artefact est VERSIONNE.
    cits, sans_iface, deja, multi, sans_couple, exempt, nom_absent, recense, ventile = v
    return [[[c.fichier, c.ligne, c.iface, c.slot, c.nom, c.args, c.texte, c.ligne_nom,
              c.franchit_virgule] for c in cits],
            sans_iface, deja, multi, sans_couple, exempt, list(nom_absent), recense,
            {k: [list(x) for x in vs] for k, vs in ventile.items() if vs}]


def _decoder(b, appel: str = ""):
    if appel == "autre_casse":
        return b
    if appel == "deriver":
        return ({k: {x[0]: (x[1], x[2], x[3]) for x in t} for k, t in b[0].items()},
                list(b[1]), tuple(b[2]))
    cits = [Citation(fichier=x[0], ligne=x[1], iface=x[2], slot=x[3], nom=x[4], args=x[5],
                     texte=x[6], ligne_nom=x[7], franchit_virgule=x[8]) for x in b[0]]
    return (cits, b[1], b[2], b[3], b[4], b[5], b[6], b[7],
            {k: [(x[0], x[1], x[2], x[3]) for x in vs] for k, vs in b[8].items()})


def cache() -> verdict_cache.CacheCliquet:
    global _CACHE
    if _CACHE is None:
        _CACHE = verdict_cache.CacheCliquet(
            nom="probe_477r25_slots_autres_interfaces",
            contexte=verdict_cache.sha_fichiers_texte(
                Path(__file__).resolve(), HERE / "probe_477r24r1_slots_interface.py",
                HERE / "il2cpp_metadata.py", tsv_path()),
            encoder=_encoder, decoder=_decoder)
    return _CACHE


def _id_appel(fenetre: int, traverse: bool, relaches: tuple[str, ...],
              virgule_bloquante: bool, ventiler: bool) -> str:
    """Identifiant LISIBLE et deterministe du jeu de parametres d'une recolte."""
    return "w%d%s%s%s%s" % (
        fenetre, "+t" if traverse else "", "+vb" if virgule_bloquante else "",
        "+n" if ventiler else "",
        "+r:" + ",".join(sorted(relaches)) if relaches else "")


def _motifs(alias: tuple[str, ...]) -> str:
    return "|".join(re.escape(a) for a in alias)


def _regex_recepteur(alias: tuple[str, ...]) -> re.Pattern[str]:
    return re.compile(r"(?<![A-Za-z0-9_])(?:%s)(?![A-Za-z0-9_])" % _motifs(alias))


def _regex_couples(alias: tuple[str, ...], qualificateur_obligatoire: bool,
                   traverse: bool = False, virgule_bloquante: bool = False):
    """Les quatre formes de couple (slot, nom), instanciees pour un jeu de recepteurs.

    `traverse` n'agit que sur les formes B et C (cf. `_entre`) : A et D franchissent le saut
    de ligne par construction, leur separateur etant un `\\s*`.

    `virgule_bloquante = True` rend le regime d'AVANT #477-r42 (la virgule arretait le
    remplissage). C'est une REFERENCE mesurable, jamais un regime de service.
    """
    qual = r"(?:(?:[A-Za-z0-9_.<>]*\.)?(?:%s)(?:\$\$|\.)|(?<![A-Za-z0-9_])\$\$)" % _motifs(alias)
    #: Forme A -- `slot 0x7e = MoveUnit`. Le qualificateur y est OPTIONNEL quand la ligne ne
    #: mentionne qu'UNE interface : sans cela, la forme la plus courante du depot est perdue.
    #: Il est CAPTURE (`q0`) pour que l'appelant puisse retrouver, apres coup, s'il etait la --
    #: c'est ce qui permet de juger le regime multi-interface sur le SPAN du couple plutot que
    #: sur le bloc entier, sans avoir a rejouer un second jeu de regex (#477-r30).
    a_qual = ("(?P<q0>%s)" % qual) if qualificateur_obligatoire else "(?P<q0>%s)?" % qual
    esp = _esp(traverse)
    #: ⚠ L'APPEL DU SLOT EST ABSORBE D'UN BLOC (cran IMPORTE de #477-r36). Sa liste d'arguments
    #: porte les `(`, `)`, `,`, `:`, `;` que `_entre` exclut : sans ce cran, le nom ECRIT SUR LA
    #: MEME LIGNE que son slot reste bloque par ses propres arguments, et la forme C part alors du
    #: slot pour attraper le nom de la ligne SUIVANTE. Le degat n'est donc PAS « un couple
    #: manquant » mais un couple FAUX. Mesure (`case-287r11`, PR #737) : trois citations JUSTES du
    #: depot, aucune appariable, **2 couples faux** et `master` ROUGE.
    return (
        re.compile((_SLOT % 0) + _appel(0) + esp + r"(?:=|->|:)" + esp
                   + r"[`*]{0,2}" + a_qual + (_NOM % 0)),
        #: Forme D -- `battleQuery.<slot 0x7d> GetAdjacentEnemies(...)`. LE RECEPTEUR PRECEDE
        #: LE SLOT, et le nom suit sans qualificateur ni signe egal. C'est la forme qu'ecrit
        #: le cas nomme (`case-250`), et aucune des trois autres ne la capte -- mesure : les
        #: deux attributions litigieuses `0x7c`/`0x80` etaient INVISIBLES au probe sans elle.
        #: L'attribution y est explicite (recepteur colle au slot), donc elle vaut AUSSI en
        #: regime multi-interface.
        re.compile(r"(?:%s)\s*\.\s*[`*<]{0,3}" % _motifs(alias) + (_SLOT % 1)
                   + r"[`*>]{0,3}" + esp + (_NOM % 1)),
        #: Forme B -- `battleQuery.GetAdjacentEnemies` ... slot 0x7d   (nom PUIS slot)
        #: ⚠ ELLE NE FRANCHIT JAMAIS LE SAUT DE LIGNE, meme en regime fenetre. Dans une
        #: enumeration verticale, le nom ecrit AVANT appartient a l'item precedent, pas au slot
        #: qui suit -- c'est le vice du cran VIRGULE (#477-r25), transpose de la virgule au
        #: saut de ligne. Mesure : sur 3 couples que ce franchissement propose, 3 sont FAUX
        #: (`probe_433_..._c_caster_gates.py` : « = AActiveAbility$$CanStillBeUsed » (slot 0x14
        #: de la ligne d'avant) rattache au « slot 0x13 » de la ligne d'apres).
        re.compile(qual + (_NOM % 2) + _appel(2)
                   + _entre(40, False, _RENVOIS, virgule_bloquante, k=2) + (_SLOT % 2)),
        #: Forme C -- slot 0x7d ... `BattleQuery$$GetAdjacentEnemies`   (slot PUIS nom)
        re.compile((_SLOT % 3) + _appel(3)
                   + _entre(60, traverse, _RENVOIS, virgule_bloquante, k=3) + qual + (_NOM % 3)),
    )


#: Les regex sont construites UNE fois : deux jeux par interface (qualificateur obligatoire
#: ou non), selon que la ligne mentionne une seule interface ou plusieurs.
_COUPLES = {iface: (_regex_couples(alias, False), _regex_couples(alias, True))
            for _, iface, alias in INTERFACES}
#: Le meme, en regime FENETRE : les formes B et C ont le droit de franchir un saut de ligne.
_COUPLES_ML = {iface: (_regex_couples(alias, False, True), _regex_couples(alias, True, True))
               for _, iface, alias in INTERFACES}
_RECEPTEURS = {iface: _regex_recepteur(alias) for _, iface, alias in INTERFACES}
_RE_DEJA_GARDEE = _regex_recepteur(DEJA_GARDEE)
RE_SLOT = re.compile(r"v?slot")

#: LA FORME DE LA MENTION DE SLOT, DERIVEE -- premier etage du recenseur (#477-r42).
#: L'ordre compte : du plus CONTRAINT au plus lache. La derniere entree n'est PAS un fourre-tout,
#: c'est « le mot `slot` isole » ; ce que `RE_SLOT` reconnait sans qu'AUCUNE entree ne decrive
#: (`slotted`, `slots0`, `vslotXY`) sort sous `autre (<extrait>)`, et c'est cette sortie-la qui
#: empeche la ventilation d'etre une liste blanche.
_FORMES_MENTION: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("chiffre", re.compile(_SLOT % 0)),
    ("nom_seul", re.compile(r"(?<![A-Za-z0-9_])v?slots?\s+[`*]{0,2}[A-Z][A-Za-z0-9]{3,}")),
    ("pluriel", re.compile(r"(?<![A-Za-z0-9_])v?slots(?![A-Za-z0-9_])")),
    ("nu", re.compile(r"(?<![A-Za-z0-9_])v?slot(?![A-Za-z0-9_])")),
)

#: N'IMPORTE QUEL nom capitalise, isole. Il sert a distinguer « rien a contredire » de « un nom
#: est ecrit, mais il n'est a aucun slot de l'interface » -- deux residus de nature differente,
#: qu'un compte unique confondait.
_RE_NOM_QUELCONQUE = re.compile(r"(?<![A-Za-z0-9_])[A-Z][A-Za-z0-9]{3,}(?![A-Za-z0-9])")

#: LA PORTEE DU BALAYAGE, ET CE QU'ELLE NE VOIT PAS. `RE_SLOT` est SENSIBLE A LA CASSE : une
#: ligne qui ecrit « Slot 0x12 = ... » n'entre meme pas dans le corpus, donc elle n'apparait dans
#: AUCUNE cause -- elle est INVISIBLE, pas ecartee. Un recenseur qui tairait cela rendrait une
#: partition exacte d'un ensemble incomplet. Ce motif la CHIFFRE.
_RE_SLOT_AUTRE_CASSE = re.compile(r"(?<![A-Za-z0-9_])[Ss][Ll][Oo][Tt]s?(?![A-Za-z0-9_])")


def _forme_mention(ligne: str) -> str:
    """La FORME de la mention de slot, DERIVEE de la ligne. Jamais `None` : `autre (...)` sinon."""
    for nom, rx in _FORMES_MENTION:
        if rx.search(ligne):
            return nom
    m = RE_SLOT.search(ligne)
    extrait = ligne[m.start():m.start() + 16].strip() if m else ligne.strip()[:16]
    return "autre (%s)" % extrait


def _compter_autre_casse() -> int:
    """Les lignes qui ecrivent `slot` avec une AUTRE casse, donc INVISIBLES au balayage.

    Ce n'est pas un residu de plus : c'est la PORTEE de la mesure. Une partition exacte d'un
    ensemble incomplet se lit comme exhaustive, et c'est precisement le vice que ce recenseur
    existe pour ne pas commettre.
    """
    #: LOCAL par fichier -- le compte d'un fichier ne depend que de son texte -- donc cache
    #: (#486-r1). Mesure : ce balayage seul pesait ~13 s a chaud, la moitie du residu du cliquet.
    cch = cache()
    return sum(cch.contribution(rel, "autre_casse", verdict_cache.sha_texte(texte),
                                lambda t=texte: _compter_autre_casse_fichier(t))
               for rel, texte in textes_balayes())


def _compter_autre_casse_fichier(texte: str) -> int:
    return sum(1 for ligne in texte.splitlines()
               if _RE_SLOT_AUTRE_CASSE.search(ligne) and not RE_SLOT.search(ligne))


def _cause_ecartee(ligne: str, autour: str, rx_noms: re.Pattern[str] | None) -> str:
    """La cause DERIVEE d'une ligne ecartee. Le libelle rendu est une cle de `CAUSES`, ou
    `autre (<forme>)` -- jamais un silence, jamais un tas par defaut.
    """
    forme = _forme_mention(ligne)
    if forme == "nom_seul":
        return "nom_seul_sans_numero"
    if forme in ("pluriel", "nu"):
        return "sans_numero"
    if forme != "chiffre":
        return forme                                    # `autre (<extrait>)`, deja libelle
    if rx_noms is not None and rx_noms.search(autour):
        return "nom_ecarte_par_un_cran"
    if _RE_NOM_QUELCONQUE.search(autour):
        return "numero_nom_hors_interface"
    return "numero_sans_aucun_nom"


#: ⚠ `_compter_args` N'EST PLUS RECOPIE ICI (#1031) -- il est IMPORTE du foyer, comme `_appel`,
#: `_entre` et `_regex_noms` juste au-dessus. Les deux copies portaient le meme cran d'elision, et
#: c'est precisement ce qui a fait manquer sa correction des DEUX cotes : l'elision PARTIELLE
#: (`(..., hitIndex)`) etait invisible ici comme la-bas. Un cran duplique se corrige a moitie.


def _blocs(lignes: list[str], fenetre: int):
    """(index 0-based de la 1re ligne, texte joint, offsets de debut de chaque ligne du bloc).

    A `fenetre = 1`, chaque bloc EST une ligne : le regime de #477-r25, a l'identique.

    ⚠ TOUTES LES TAILLES de 1 a `fenetre` sont rendues, pas seulement `fenetre`, et un bloc
    demarre a CHAQUE ligne. Les deux crans ont ete MESURES necessaires :
    * ne demarrer qu'une ligne sur `fenetre` ferait dependre la couverture de la PARITE du
      numero de ligne, ce qui n'est pas un critere ;
    * ne rendre que la taille MAXIMALE casse la MONOTONIE -- un bloc plus large voit plus
      d'interfaces, bascule en regime multi-interface (formes A et D seules) et PERD un couple
      que le bloc etroit voyait. Mesure : `sans_couple` remontait de 642 (W=2) a 645 (W=4),
      c'est-a-dire qu'ELARGIR RETRECISSAIT la couverture. Rendre toutes les tailles fait de la
      recolte une UNION, donc monotone par construction, et le couple est alors juge dans le
      plus PETIT contexte qui le porte.
    """
    for i0 in range(len(lignes)):
        #: ⚠ UNE LIGNE VIDE EST UNE FRONTIERE, et le bloc s'y arrete. Un couple n'enjambe pas
        #: un changement de paragraphe : mesure, 2 des faux positifs de l'elargissement
        #: (`case-433-...-a-gates-whole-board.md` « # + slot 10 » puis, apres une ligne vide,
        #: `AActiveAbility$$GetPossibleTargetTiles` ; `formulas.py` idem) ne tiennent qu'a ce
        #: franchissement, et AUCUN couple juste ne le demande.
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


def _contribution(rel: str, texte: str, tables, fenetre: int, couples, rx_noms) -> tuple:
    """LA CONTRIBUTION D'UN SEUL FICHIER a l'etage 3 -- verdict LOCAL, donc cachable (#486-r1).

    Elle ne lit QUE `texte`. Etabli avant de poser le cache : les seules variables partagees de
    l'ancienne boucle etaient des ACCUMULATEURS, `recense` est purement ADDITIF, et le
    `vus_absents` de deduplication portait une cle COMMENCANT par `rel` -- donc intra-fichier par
    construction. Aucun canal ne courait d'un fichier a l'autre.

    Rend `(citations, sans_interface, deja_gardee, multi, sans_couple, exemptees, noms absents,
    recensement partiel, ventilation partielle)`. Tout ce qui est INTER-fichier -- deduplication
    globale, priorite au mono-ligne, priorite au non-franchissement, confrontation aux tables --
    reste chez `recolter`, hors cache.
    """
    retenues: list[Citation] = []
    sans_iface = deja = multi = sans_couple = exempt = 0
    nom_absent: list[str] = []
    vus_absents: set[tuple[str, int, str, int, str, int]] = set()
    recense: dict[str, int] = {}
    ventile: dict[str, list[tuple[str, int, str, str]]] = {c: [] for c in CAUSES}
    lignes = texte.splitlines()
    #: PRE-CALCUL PAR LIGNE. Sans lui, les 18 regex de recepteur sont rejouees sur chaque
    #: bloc de chaque taille -- mesure : le balayage passait de 7 s a plus de 2 min.
    a_slot = [bool(RE_SLOT.search(l)) for l in lignes]
    #: Une ligne n'est examinee que si un slot est ecrit a moins de `fenetre` lignes d'elle
    #: -- ailleurs, aucun bloc ne la joindra jamais a un slot.
    utile = [any(a_slot[max(0, i - fenetre + 1):i + fenetre]) for i in range(len(lignes))]
    ifaces_l = [frozenset(iface for _, iface, _ in INTERFACES
                          if _RECEPTEURS[iface].search(l)) if u else frozenset()
                for l, u in zip(lignes, utile)]
    garde_l = [bool(_RE_DEJA_GARDEE.search(l)) if u else False
               for l, u in zip(lignes, utile)]
    #: Les lignes portant un slot d'ou SORT au moins un couple. C'est ce qui distingue
    #: « ecartee » de « couverte », et c'est une propriete de LIGNE, pas de bloc : une
    #: meme ligne est vue par `fenetre` blocs.
    couvertes: set[int] = set()
    exemptees_l: set[int] = set()
    for i0, bloc, offsets in _blocs(lignes, fenetre):
        fin = i0 + len(offsets)
        if not any(a_slot[i0:fin]):
            continue
        union = frozenset().union(*ifaces_l[i0:fin])
        if not union:
            continue
        #: L'ordre reste celui de `INTERFACES` -- une sortie qui depend de l'ordre d'un
        #: `set` n'est pas relisible d'un run a l'autre.
        vues = [iface for _, iface, _ in INTERFACES if iface in union]
        for iface in vues:
            table = tables.get(iface, {})
            #: Les formes sont jouees en regime MONO (qualificateur OPTIONNEL en forme A) ;
            #: le regime reel est tranche APRES coup, sur le SPAN du couple. Le groupe `q0`
            #: dit si le qualificateur etait la, ce qu'exige le regime multi.
            for k, rx in enumerate(couples[iface][0]):
                for m in rx.finditer(bloc):
                    slot = int(m.group("n%d" % k), 0)
                    nom = m.group("nom%d" % k)
                    no = i0 + bisect.bisect_right(offsets, m.start("n%d" % k))
                    no_nom = i0 + bisect.bisect_right(offsets, m.start("nom%d" % k))
                    #: ⚠ L'INTERFACE ET LE REGIME SE JUGENT SUR LE SPAN DU COUPLE, PAS SUR
                    #: LE BLOC. A `fenetre = 1` c'est la meme chose (span = ligne), mais des
                    #: que le bloc s'elargit, une interface nommee TROIS LIGNES PLUS BAS
                    #: n'a plus a s'attribuer un slot qu'elle ne porte pas -- mesure : c'est
                    #: ainsi que « `$$FinishAttack` (slot 0x3b) » se voyait attribuer a
                    #: `IMatchState` parce que la ligne suivante ecrit `MatchState+0x60`.
                    #: Jugee sur le span, l'attribution redevient celle du site.
                    a, b = min(no, no_nom), max(no, no_nom)
                    span = frozenset().union(*ifaces_l[a - 1:b])
                    if iface not in span:
                        continue
                    #: ⚠ EN REGIME MULTI-INTERFACE, SEULES LES FORMES A ET D SONT GARDEES.
                    #: Les formes B et C rapprochent un nom et un slot SEPARES par du texte
                    #: -- et quand le span parle de deux interfaces, ce texte est justement
                    #: ce qui les separe : « `BattleQuery$$GetNormalAttackPrediction`
                    #: invoque `IDamagePrediction` slot 9 » attribuerait le slot 9
                    #: d'IDamagePrediction a la methode de BattleQuery. Mesure : 2 faux
                    #: positifs sur 59 leves par ce seul cran. Les formes A et D restent :
                    #: leur attribution est portee par un qualificateur ou un recepteur
                    #: COLLE, pas par la proximite.
                    if len(span) > 1 or any(garde_l[a - 1:b]):
                        if k > 1 or (k == 0 and m.group("q0") is None):
                            continue
                    #: L'exemption au site vaut si elle est ecrite sur l'une OU l'autre
                    #: des deux lignes du couple. A `fenetre = 1` c'est la meme.
                    if (MARQUEUR_REFUTE in lignes[no - 1]
                            or MARQUEUR_REFUTE in lignes[no_nom - 1]):
                        #: La ligne du SLOT compte alors comme exemptee, meme si c'est la
                        #: ligne du NOM qui porte le marqueur : sinon elle retomberait en
                        #: `sans_couple` et se lirait comme une zone aveugle alors qu'elle
                        #: est une exemption ASSUMEE.
                        exemptees_l.add(no)
                        continue
                    couvertes.add(no)
                    if nom not in {v[0] for v in table.values()}:
                        #: ⚠ DEDUPLIQUE comme les citations : le meme couple est vu par
                        #: chaque taille de bloc qui le contient. Sans cette cle, le compte
                        #: des indecidables se lisait comme du bruit CROISSANT avec la
                        #: fenetre (5 -> 33 -> 88 -> 168 a W=4) alors qu'il ne s'agissait
                        #: que du MEME site recompte -- un compteur qui gonfle sans que
                        #: rien n'apparaisse fait renoncer a un elargissement legitime.
                        cle_abs = (rel, no, iface, slot, nom, no_nom)
                        if cle_abs in vus_absents:
                            continue
                        vus_absents.add(cle_abs)
                        nom_absent.append(
                            "%s:%d [%s] slot 0x%x = %s -- ce nom n'est a AUCUN slot de "
                            "cette interface | %s" % (rel, no, iface, slot, nom,
                                                      lignes[no - 1].strip()[:120]))
                        continue
                    queue = bloc[m.end():]
                    args = _compter_args(queue) if RE_APPEL.match(queue) else None
                    retenues.append(Citation(
                        fichier=rel, ligne=no, iface=iface, slot=slot, nom=nom, args=args,
                        ligne_nom=no_nom,
                        franchit_virgule="," in (m.groupdict().get("rem%d" % k) or ""),
                        texte=lignes[no - 1].strip()[:150]))
    #: CE QUI RESTE ECARTE se compte LIGNE PAR LIGNE -- une ligne, un verdict. Compter par
    #: bloc melangerait les regimes et rendrait les chiffres incomparables d'une fenetre
    #: a l'autre, alors que c'est justement ce qu'on veut mesurer.
    for no, ligne in enumerate(lignes, 1):
        if not RE_SLOT.search(ligne) or no in couvertes:
            continue
        vues = [iface for _, iface, _ in INTERFACES if _RECEPTEURS[iface].search(ligne)]
        if not vues:
            if _RE_DEJA_GARDEE.search(ligne):
                deja += 1
            else:
                sans_iface += 1
                for m in _RE_RECEVEUR_CANDIDAT.finditer(ligne):
                    recense[m.group(1)] = recense.get(m.group(1), 0) + 1
        elif MARQUEUR_REFUTE in ligne or no in exemptees_l:
            exempt += 1
        elif len(vues) > 1 or _RE_DEJA_GARDEE.search(ligne):
            multi += 1
        else:
            sans_couple += 1
            #: LE RECENSEUR (#477-r42) -- la cause est DERIVEE de la ligne et de son
            #: voisinage, jamais cherchee dans une liste blanche. `rx_noms` porte les noms
            #: de l'interface REELLEMENT appariee a cette ligne (`vues[0]`, unique ici par
            #: construction : le cas multi est parti dans `multi` juste au-dessus).
            if rx_noms is not None:
                autour = "\n".join(lignes[max(0, no - fenetre):no - 1 + fenetre])
                ventile.setdefault(
                    _cause_ecartee(ligne, autour, rx_noms.get(vues[0])), []
                ).append((rel, no, vues[0], ligne.strip()[:120]))

    return (retenues, sans_iface, deja, multi, sans_couple, exempt, nom_absent,
            recense, ventile)


def recolter(tables: dict[str, dict[int, tuple[str, int, int]]],
             fenetre: int = FENETRE, traverse: bool | None = None,
             relaches: tuple[str, ...] = (), virgule_bloquante: bool = False,
             ventiler: bool = True) -> tuple[
        list[Citation], Ecartees, dict[str, int]]:
    """(citations retenues, ce qui est ecarte et compte, recensement des recepteurs).

    `fenetre` = nombre de LIGNES sur lesquelles un couple peut s'etaler. `traverse` dit si les
    formes B et C (nom et slot separes par du texte) ont le droit de franchir le saut de ligne ;
    par defaut, oui des que la fenetre depasse 1.

    `virgule_bloquante` rejoue le regime d'AVANT #477-r42 (REFERENCE mesurable). `relaches`
    desarme un cran NOMME (`priorite-non-franchissement`) : c'est une MESURE, pas un service.
    `ventiler = False` coupe le RECENSEUR -- la ventilation rend alors `None` (PAS MESURE), et
    c'est ce qu'on passe aux courbes, ou seul le compte importe.
    """
    if traverse is None:
        traverse = fenetre > 1
    if virgule_bloquante:
        couples = {iface: (_regex_couples(alias, False, traverse, True),
                           _regex_couples(alias, True, traverse, True))
                   for _, iface, alias in INTERFACES}
    else:
        couples = _COUPLES_ML if traverse else _COUPLES
    #: Les noms de chaque interface, pour le RECENSEUR. Le motif vient du FOYER (`_regex_noms`,
    #: importe de #477-r24-r1) -- pas d'une copie qui reproduirait son ancien lookbehind.
    rx_noms = ({iface: _regex_noms(frozenset(v[0] for v in t.values()))
                for iface, t in tables.items() if t} if ventiler else None)
    ventile: dict[str, list[tuple[str, int, str, str]]] = {c: [] for c in CAUSES}
    retenues, nom_absent, recense = [], [], {}
    sans_iface = deja = multi = sans_couple = exempt = 0
    appel = _id_appel(fenetre, traverse, relaches, virgule_bloquante, rx_noms is not None)
    cch = cache()
    for rel, texte in textes_balayes():
        #: ⚠ LE PRE-FILTRE RESTE JOUE A CHAQUE RUN, ET N'ENTRE PAS AU CACHE : il coute une
        #: recherche de sous-chaine sur un texte deja lu.
        if "slot" not in texte:
            continue
        lot = cch.contribution(rel, appel, verdict_cache.sha_texte(texte),
                               lambda r=rel, t=texte: _contribution(
                                   r, t, tables, fenetre, couples, rx_noms))
        retenues += lot[0]
        sans_iface += lot[1]
        deja += lot[2]
        multi += lot[3]
        sans_couple += lot[4]
        exempt += lot[5]
        nom_absent += lot[6]
        for nomrec, k in lot[7].items():
            recense[nomrec] = recense.get(nomrec, 0) + k
        for cause, v in lot[8].items():
            ventile.setdefault(cause, []).extend(v)
    #: Deduplication : plusieurs formes -- et, en fenetre, plusieurs BLOCS -- peuvent capter le
    #: MEME couple. La cle inclut la ligne du NOM : deux noms identiques a deux endroits
    #: differents sont deux citations.
    #: ⚠ LES NON-FRANCHISSANTS PASSENT D'ABORD (#477-r42) : garder l'exemplaire qui a franchi une
    #: virgule ferait mentir `franchit_virgule` sur un couple parfaitement local.
    uniques: list[Citation] = []
    deja_vu: set[tuple[str, int, str, int, str, int]] = set()
    for c in sorted(retenues, key=lambda x: x.franchit_virgule):
        cle = (c.fichier, c.ligne, c.iface, c.slot, c.nom, c.ligne_nom)
        if cle in deja_vu:
            continue
        deja_vu.add(cle)
        uniques.append(c)
    #: ⚠ PRIORITE AU MONO-LIGNE (#477-r36). Un couple ENJAMBANT cede si le MEME slot, ecrit a la
    #: MEME ligne, est deja apparie SUR SA LIGNE : la citation la plus LOCALE gagne. C'est le
    #: symetrique du cran deja ecrit pour la forme B (« dans une enumeration verticale, le nom
    #: ecrit AVANT appartient a l'item precedent ») -- ici, le nom ecrit APRES appartient a
    #: l'item SUIVANT. La regle est CONSERVATRICE : elle ne peut que RETIRER des enjambants, et
    #: seulement la ou une attribution locale existe deja pour le meme slot.
    locaux = {(c.fichier, c.ligne, c.iface, c.slot) for c in uniques if c.ligne == c.ligne_nom}
    cedes = [c for c in uniques
             if c.ligne != c.ligne_nom and (c.fichier, c.ligne, c.iface, c.slot) in locaux]
    if cedes:
        gardes = {id(c) for c in cedes}
        uniques = [c for c in uniques if id(c) not in gardes]
    #: ⚠ PRIORITE AU NON-FRANCHISSEMENT DE VIRGULE (#477-r42) -- foyer PARTAGE, cf.
    #: `ceder_aux_locaux`. C'est ce cran qui remplace l'ancien « la virgule arrete le
    #: remplissage » : sur CE corpus il dissout les DEUX faux de l'enumeration
    #: (`slot 0x14 \`X\`, slot 0x13 \`Y\``) sans en perdre un seul.
    cedes_v: list[Citation] = []
    if "priorite-non-franchissement" not in relaches:
        uniques, cedes_v = ceder_aux_locaux(
            uniques, lambda c: c.franchit_virgule,
            lambda c: (c.fichier, c.ligne, c.iface, c.slot),
            lambda c: (c.fichier, c.ligne_nom, c.iface, c.nom))
    return uniques, Ecartees(sans_interface=sans_iface, deja_gardee=deja,
                             cedes_au_mono_ligne=tuple(
                                 "%s:%d [%s] slot 0x%x = %s (nom lu ligne %d) | %s"
                                 % (c.fichier, c.ligne, c.iface, c.slot, c.nom, c.ligne_nom,
                                    c.texte[:100]) for c in cedes),
                             cedes_au_non_franchissement=tuple(
                                 "%s:%d [%s] slot 0x%x = %s (nom lu ligne %d) | %s"
                                 % (c.fichier, c.ligne, c.iface, c.slot, c.nom, c.ligne_nom,
                                    c.texte[:100]) for c in cedes_v),
                             multi_non_qualifie=multi, sans_couple=sans_couple,
                             exemptees=exempt, nom_absent=tuple(nom_absent),
                             ventilation=None if rx_noms is None
                             else {c: tuple(v) for c, v in ventile.items()}), recense


def confronter(cits: list[Citation],
               tables: dict[str, dict[int, tuple[str, int, int]]]) -> tuple[
                   list[str], list[str], list[str]]:
    """(noms/slots faux, arites fausses, couples justes mais sur une AUTRE interface)."""
    faux_nom: list[str] = []
    faux_arite: list[str] = []
    autre_iface: list[str] = []
    for c in cits:
        table = tables.get(c.iface, {})
        attendu = table.get(c.slot)
        ailleurs = sorted(s for s, v in table.items() if v[0] == c.nom)
        if attendu is None or attendu[0] != c.nom:
            #: ⚠ AVANT D'ACCUSER, ON CHERCHE SI LE COUPLE EST JUSTE AILLEURS. Un recepteur
            #: peut designer la classe qui DELEGUE, pas celle qui declare : « slot 0x40 ->
            #: `AttackQuery.HasValidTargets` » cite le slot d'`IBattleQuery`, dont
            #: l'implementation appelle `AttackQuery`. Le couple est alors JUSTE, et c'est
            #: notre appariement qui est faux -- l'imputer au depot serait une accusation
            #: fabriquee par l'outil.
            porteuses = [f for f, t in tables.items()
                         if f != c.iface and t.get(c.slot, ("",))[0] == c.nom]
            if porteuses:
                autre_iface.append(
                    "%s:%d slot 0x%x = %s : JUSTE, mais sur %s (le site ecrit %s) | %s"
                    % (c.fichier, c.ligne, c.slot, c.nom, "/".join(porteuses), c.iface,
                       c.texte))
                continue
            faux_nom.append(
                "%s:%d [%s] slot 0x%x : le site nomme %s, le metadata dit %s ; %s est aux "
                "slots %s | %s"
                % (c.fichier, c.ligne, c.iface, c.slot, c.nom,
                   "AUCUNE METHODE (hors table, %d slots)" % len(table) if attendu is None
                   else attendu[0], c.nom,
                   ", ".join("0x%x" % s for s in ailleurs) or "aucun", c.texte))
            continue
        if c.args is not None and c.args != attendu[1]:
            faux_arite.append(
                "%s:%d [%s] slot 0x%x %s : %d argument(s) au site, %d dans la signature | %s"
                % (c.fichier, c.ligne, c.iface, c.slot, c.nom, c.args, attendu[1], c.texte))
    return faux_nom, faux_arite, autre_iface


# ------------------------------------------------------------------- contre-epreuve


MUTANTS = {
    "slot-decale": "decale d'un cran les slots de l'interface la plus citee (etages 2 et 3)",
    "nom-permute": "permute deux noms REELLEMENT cites (etages 2 et 3 doivent MORDRE)",
    "table-tronquee": "coupe la plus grande interface a la moitie de ses slots (etage 3)",
    "arite-fausse": "ajoute 1 a tous les param_count (etage 4 doit MORDRE)",
    #: ⚠ CELUI-CI MUTE LES SLOTS QUE SEULE LA FENETRE VOIT. Les quatre autres mordaient deja
    #: avant #477-r30 : ils ne disent RIEN de l'elargissement. Un mutant qui ne peut pas
    #: distinguer fenetre=1 de fenetre=N ne garde pas la fenetre.
    "enjambants-decales": "decale les slots des couples qui ENJAMBENT une ligne -- inerte a "
                          "fenetre=1, doit MORDRE au-dela",
    #: ⚠ MEME RAISON, UN CRAN PLUS LOIN (#477-r42). Les cinq mutants ci-dessus mordent DEJA sans
    #: le franchissement de virgule : aucun ne dit quoi que ce soit du cran qui l'autorise, ni de
    #: la priorite qui l'encadre. Celui-ci porte sur les couples que SEUL ce franchissement
    #: rapporte, et il REFUSE en regime `--virgule-bloquante`, ou il n'a rien a muter.
    "franchissants-decales": "decale les slots des couples qui ont FRANCHI une virgule -- inerte "
                             "en regime --virgule-bloquante, doit MORDRE en service",
}


def _iface_la_plus_citee(cits: list[Citation]) -> str:
    compte: dict[str, int] = {}
    for c in cits:
        compte[c.iface] = compte.get(c.iface, 0) + 1
    if not compte:
        raise SystemExit("contre-epreuve IMPOSSIBLE : aucune citation retenue -- un mutant "
                         "qui ne peut pas mordre n'est pas une contre-epreuve.")
    return max(compte, key=lambda k: compte[k])


def muter(tables: dict[str, dict[int, tuple[str, int, int]]], nom: str,
          cits: list[Citation]) -> dict[str, dict[int, tuple[str, int, int]]]:
    out = {k: dict(v) for k, v in tables.items()}
    if nom == "slot-decale":
        cible = _iface_la_plus_citee(cits)
        out[cible] = {s + 1: v for s, v in tables[cible].items()}
        return out
    if nom == "nom-permute":
        #: Les deux slots permutes sont DERIVES des citations reelles : permuter deux slots
        #: que personne ne cite rend une contre-epreuve INERTE qui passe pour mordante
        #: (mesure #477-r24-r1).
        attestes = [(c.iface, c.slot) for c in cits if c.slot in tables.get(c.iface, {})]
        vus = list(dict.fromkeys(attestes))
        meme = [x for x in vus if x[0] == vus[0][0]] if vus else []
        if len(meme) < 2:
            raise SystemExit("contre-epreuve IMPOSSIBLE : moins de 2 slots attestes sur une "
                             "meme interface -- ce mutant ne peut pas mordre.")
        (iface, a), (_, b) = meme[0], meme[1]
        out[iface][a], out[iface][b] = out[iface][b], out[iface][a]
        return out
    if nom == "table-tronquee":
        cible = max(tables, key=lambda k: len(tables[k]))
        garde = len(tables[cible]) // 2
        out[cible] = {s: v for s, v in tables[cible].items() if s < garde}
        return out
    if nom == "arite-fausse":
        return {k: {s: (n, a + 1, f) for s, (n, a, f) in v.items()} for k, v in tables.items()}
    if nom == "enjambants-decales":
        #: On PERMUTE le nom du slot cite avec celui du slot voisin, pour chaque couple qui
        #: enjambe une ligne. Si l'appariement en fenetre disparait, ce mutant devient INERTE
        #: -- et c'est exactement ce qu'on veut pouvoir constater.
        #: ⚠ SEULS LES SLOTS QUE PERSONNE NE CITE SUR UNE SEULE LIGNE sont vises, ET dont le
        #: voisin permute ne l'est pas non plus. Sans ce filtre le mutant mord AUSSI a
        #: fenetre=1 (mesure : 63 desaccords) : il gardait l'appariement en general, pas
        #: l'ELARGISSEMENT -- et n'aurait donc rien dit d'une fenetre perdue.
        mono = {(c.iface, c.slot) for c in cits if c.ligne == c.ligne_nom}
        vises = [(c.iface, c.slot) for c in cits if c.ligne != c.ligne_nom
                 and c.slot in tables.get(c.iface, {})
                 and c.slot + 1 in tables.get(c.iface, {})
                 and (c.iface, c.slot) not in mono
                 and (c.iface, c.slot + 1) not in mono]
        if not vises:
            raise SystemExit("contre-epreuve IMPOSSIBLE : aucun couple ENJAMBANT atteste sur "
                             "un slot que personne ne cite en une ligne -- ce mutant ne peut "
                             "pas discriminer la fenetre.")
        for iface, s in dict.fromkeys(vises):
            out[iface][s], out[iface][s + 1] = out[iface][s + 1], out[iface][s]
        return out
    if nom == "franchissants-decales":
        #: Meme construction que ci-dessus, sur l'autre cran : seuls les slots que PERSONNE ne
        #: cite sans franchir de virgule sont vises, ET dont le voisin permute ne l'est pas non
        #: plus. Sans ce filtre, le mutant mordrait AUSSI en `--virgule-bloquante` : il garderait
        #: l'appariement en general, pas le FRANCHISSEMENT.
        local = {(c.iface, c.slot) for c in cits if not c.franchit_virgule}
        vises = [(c.iface, c.slot) for c in cits if c.franchit_virgule
                 and c.slot in tables.get(c.iface, {})
                 and c.slot + 1 in tables.get(c.iface, {})
                 and (c.iface, c.slot) not in local
                 and (c.iface, c.slot + 1) not in local]
        if not vises:
            raise SystemExit("contre-epreuve IMPOSSIBLE : aucun couple ayant FRANCHI une virgule "
                             "sur un slot que personne ne cite autrement -- ce mutant ne peut "
                             "pas discriminer le cran de #477-r42.")
        for iface, s in dict.fromkeys(vises):
            out[iface][s], out[iface][s + 1] = out[iface][s + 1], out[iface][s]
        return out
    raise SystemExit("mutant inconnu : %s" % nom)


def jouer(tables: dict[str, dict[int, tuple[str, int, int]]], cits: list[Citation],
          derive: dict[str, dict[int, tuple[str, int, int]]] | None) -> tuple[int, int, int]:
    if derive is None:
        ecarts = 0
    else:
        ecarts = sum(1 for iface, t in derive.items() for s, v in t.items()
                     if tables.get(iface, {}).get(s) != v)
    faux_nom, faux_arite, _ = confronter(cits, tables)
    return ecarts, len(faux_nom), len(faux_arite)


# ------------------------------------------------------------------------------- main


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--regenerer", action="store_true",
                    help="reecrit l'entree versionnee depuis le metadata installe")
    ap.add_argument("--recenser", action="store_true",
                    help="imprime les recepteurs NON APPARIES (ce qui borne la tranche)")
    ap.add_argument("--mutants", action="store_true",
                    help="contre-epreuve : chaque mutant doit faire MORDRE un etage")
    ap.add_argument("--fenetre", type=int, default=FENETRE, metavar="N",
                    help="lignes sur lesquelles un couple (slot, nom) peut s'etaler "
                         "(defaut %d ; 1 = l'etat de #477-r25)" % FENETRE)
    ap.add_argument("--courbe", action="store_true",
                    help="re-derive le CHOIX de la fenetre : gain et bruit pour N = 1..8")
    ap.add_argument("--ventiler", action="store_true",
                    help="detaille CE QUI RESTE hors couverture, ligne par ligne, par CAUSE")
    ap.add_argument("--virgule-bloquante", action="store_true",
                    help="rejoue le regime d'AVANT #477-r42 (la virgule ARRETE le remplissage)")
    ap.add_argument("--relacher", action="store_true",
                    help="desarme le cran `priorite-non-franchissement` et publie ce qu'il CACHE")
    ap.add_argument("--verifier-cache", action="store_true",
                    help="RECALCULE tout en ignorant le cache versionne et le confronte entree "
                         "par entree (#486-r1) -- le seul controle qui voie une entree falsifiee "
                         "de facon coherente")
    args = ap.parse_args()

    if args.verifier_cache:
        #: MODE ESPION : le fichier est charge, jamais servi. Le run recalcule donc TOUT.
        global _CACHE
        _CACHE = verdict_cache.CacheCliquet(
            nom="probe_477r25_slots_autres_interfaces",
            contexte=verdict_cache.sha_fichiers_texte(
                Path(__file__).resolve(), HERE / "probe_477r24r1_slots_interface.py",
                HERE / "il2cpp_metadata.py", tsv_path()),
            encoder=_encoder, decoder=_decoder, relire=False)

    print("=== #477-r25 -- slots des AUTRES interfaces (hors IOperationProcessor) ===")
    print("build qui fait foi : %s" % current_build())

    derive = deriver()

    if args.regenerer:
        if derive is None:
            raise SystemExit("REFUSE : impossible de regenerer sans metadata (cf. etage 1).")
        p = ecrire_tsv(derive)
        print("    entree versionnee reecrite : %s (%d interfaces, %d slots)"
              % (p.relative_to(REPO).as_posix(), len(derive),
                 sum(len(v) for v in derive.values())))
        print("    NE PAS OUBLIER : `git add %s`" % p.relative_to(REPO).as_posix())
        return 0

    versionne = lire_tsv()
    ecarts = cliquet(derive, versionne)

    if args.courbe:
        print()
        print("=== LE CHOIX DE LA FENETRE, RE-DERIVE (fenetre en service : %d) ===" % FENETRE)
        print("  W  citations  enjambantes  sans_couple  indecidables  desaccords")
        for w in (1, 2, 3, 4, 5, 6, 8):
            c, e, _ = recolter(versionne, fenetre=w, ventiler=False)
            fn, _fa, _au = confronter(c, versionne)
            print("  %2d   %6d     %6d       %6d        %6d      %6d"
                  % (w, len(c), sum(1 for x in c if x.ligne != x.ligne_nom),
                     e.sans_couple, len(e.nom_absent), len(fn)))
        print("  Lire : `citations` et `sans_couple` disent le GAIN, `indecidables` le BRUIT.")
        print("  La ou les deux premieres colonnes cessent de bouger, elargir n'apporte plus.")
        return 0

    if args.relacher:
        print()
        print("=== CE QUE LE CRAN `priorite-non-franchissement` CACHE (#477-r42) ===")
        base, _be, _br = recolter(versionne, fenetre=args.fenetre, ventiler=False)
        connus = {(c.fichier, c.ligne, c.iface, c.slot, c.nom, c.ligne_nom) for c in base}
        lot, _le, _lr = recolter(versionne, fenetre=args.fenetre, ventiler=False,
                                 relaches=("priorite-non-franchissement",))
        neufs = [c for c in lot
                 if (c.fichier, c.ligne, c.iface, c.slot, c.nom, c.ligne_nom) not in connus]
        faux = [c for c in neufs
                if versionne.get(c.iface, {}).get(c.slot, ("",))[0] != c.nom]
        print("  %d couple(s) neuf(s), dont %d au NOM qui ne concorde PAS" % (len(neufs),
                                                                             len(faux)))
        print("  cause du cran : un couple qui a FRANCHI une virgule cede si l'un de ses membres")
        print("  est deja apparie SANS en franchir -- la citation la plus LOCALE gagne.")
        for c in neufs:
            att = versionne.get(c.iface, {}).get(c.slot, ("",))[0]
            print("    %-8s %s:%d [%s] slot 0x%x -> %s (table : %s) | %s"
                  % ("CONCORDE" if att == c.nom else "DOUTEUX", c.fichier, c.ligne, c.iface,
                     c.slot, c.nom, att or "hors table", c.texte[:80]))
        return 0

    cits, ecartees, recense = recolter(versionne, fenetre=args.fenetre,
                                       virgule_bloquante=args.virgule_bloquante)
    par_iface: dict[str, int] = {}
    for c in cits:
        par_iface[c.iface] = par_iface.get(c.iface, 0) + 1
    print("[0] RECENSEMENT : %d interface(s) declaree(s), %d effectivement citee(s) avec un "
          "couple (slot, nom)" % (len(INTERFACES), len(par_iface)))
    for iface in sorted(par_iface, key=lambda k: -par_iface[k]):
        print("      %-24s %3d attestation(s), %3d slots dans le metadata"
              % (iface, par_iface[iface], len(versionne.get(iface, {}))))
    for _, iface, _ in INTERFACES:
        if iface not in par_iface:
            print("      %-24s   0 attestation -- declaree, JAMAIS citee avec un nom" % iface)

    enjambantes = sum(1 for c in cits if c.ligne != c.ligne_nom)
    print("[3] CITATIONS : %d attestation(s) sur %d fichier(s), appariees sur une FENETRE de "
          "%d ligne(s)" % (len(cits), len({c.fichier for c in cits}), args.fenetre))
    print("      dont %d couple(s) qui ENJAMBENT un saut de ligne -- invisibles a #477-r25, "
          "qui exigeait slot et nom ADJACENTS" % enjambantes)
    #: ⚠ LA ZONE AVEUGLE SE PUBLIE AVEC SON RETRECISSEMENT, pas seulement avec sa taille.
    #: Un cliquet dont on ne sait pas si l'angle mort a bouge est un inventaire (#477-r30).
    if args.fenetre > 1:
        ref_cits, ref, _ = recolter(versionne, fenetre=1, ventiler=False)
        print("      REFERENCE fenetre=1 (l'etat de #477-r25) : %d attestation(s), "
              "%d ligne(s) sans couple" % (len(ref_cits), ref.sans_couple))
        print("      RETRECISSEMENT de la zone aveugle : %d -> %d ligne(s) sans couple (-%d)"
              % (ref.sans_couple, ecartees.sans_couple, ref.sans_couple - ecartees.sans_couple))
    if not args.virgule_bloquante:
        #: La SECONDE reference : le regime d'avant #477-r42, a fenetre EGALE. Sans elle, le
        #: gain du franchissement de virgule se confondrait avec celui de la fenetre.
        v_cits, v_ec, _ = recolter(versionne, fenetre=args.fenetre, virgule_bloquante=True,
                                   ventiler=False)
        print("      REFERENCE --virgule-bloquante (l'etat d'avant #477-r42, meme fenetre) : %d "
              "attestation(s), %d ligne(s) sans couple" % (len(v_cits), v_ec.sans_couple))
        print("      dont %d couple(s) qui ont FRANCHI une virgule -- invisibles quand elle "
              "arretait le remplissage" % sum(1 for c in cits if c.franchit_virgule))
    print("      ECARTEES, et c'est DIT :")
    print("        %5d ligne(s) sans aucun recepteur d'interface couverte"
          % ecartees.sans_interface)
    print("        %5d ligne(s) citant IOperationProcessor -- gardees par #477-r24-r1"
          % ecartees.deja_gardee)
    print("        %5d ligne(s) MULTI-interfaces dont le couple n'est pas qualifie"
          % ecartees.multi_non_qualifie)
    print("        %5d ligne(s) citant un slot SANS lui accoler de nom, MEME sur %d ligne(s)"
          % (ecartees.sans_couple, args.fenetre))
    print("        %5d ligne(s) exemptees au site par %s" % (ecartees.exemptees,
                                                            MARQUEUR_REFUTE))
    print("        %5d fichier(s) EXCLU(S) et nomme(s) : %s" % (len(EXCLUS), ", ".join(EXCLUS)))
    print("        %5d couple(s) dont le NOM est absent de l'interface appariee "
          "(indecidable -- listes, ni verts ni rouges)" % len(ecartees.nom_absent))
    for f in ecartees.nom_absent:
        print("            %s" % f)
    print("        %5d couple(s) ENJAMBANT(S) ayant CEDE a une attribution locale du meme slot "
          "(#477-r36)" % len(ecartees.cedes_au_mono_ligne))
    for f in ecartees.cedes_au_mono_ligne:
        print("            %s" % f)
    print("        %5d couple(s) ayant FRANCHI une virgule et CEDE a une attribution sans "
          "franchissement (#477-r42)" % len(ecartees.cedes_au_non_franchissement))
    for f in ecartees.cedes_au_non_franchissement:
        print("            %s" % f)

    #: ⚠ LE RESIDU SE PUBLIE AVEC SA CAUSE (#477-r42). Ce probe n'avait AUCUN recenseur : ses
    #: ~647 lignes ecartees sortaient sous un compte NU, ce qui se lit « rien a signaler » alors
    #: que c'est la zone ou une citation fausse peut dormir. Un compte seul est un inventaire.
    vent = ecartees.ventilation
    if vent is None:
        print("      VENTILATION du residu : PAS MESUREE (recenseur coupe)")
    else:
        total = sum(len(v) for v in vent.values())
        #: ⚠ ASSERTIONNEE, PAS AFFIRMEE : la somme des causes VAUT le total. C'est ce qui
        #: transforme la ventilation d'une LISTE BLANCHE en une PARTITION.
        assert total == ecartees.sans_couple, (total, ecartees.sans_couple)
        print("      VENTILATION de ces %d lignes -- la somme des causes VAUT le total :"
              % ecartees.sans_couple)
        for cause in sorted(vent, key=lambda c: -len(vent[c])):
            print("        %5d  %-26s %s"
                  % (len(vent[cause]), cause, CAUSES.get(cause, "CAUSE NON PREVUE -- "
                                                         "derivee de la ligne, a instruire")))
        #: ⚠ LA PORTEE SE PUBLIE AVEC LA PARTITION. Une partition exacte d'un ensemble INCOMPLET
        #: se lit comme exhaustive : ce qui suit dit ce que le balayage NE VOIT PAS.
        print("      PORTEE DE LA MESURE -- ce que cette partition ne couvre PAS :")
        print("        les %d lignes sans recepteur, les %d d'IOperationProcessor et les %d "
              "MULTI-interfaces" % (ecartees.sans_interface, ecartees.deja_gardee,
                                    ecartees.multi_non_qualifie))
        print("        les %d ligne(s) qui ecrivent `slot` AVEC UNE AUTRE CASSE (`Slot 0x12`) : "
              "`RE_SLOT` est sensible a la casse, donc elles n'entrent dans AUCUNE cause -- "
              "elles sont INVISIBLES, pas ecartees" % _compter_autre_casse())
        print("        les fichiers hors `BALAYAGE_GLOBS` (%s)" % ", ".join(BALAYAGE_GLOBS))
        if args.ventiler:
            for cause in sorted(vent, key=lambda c: -len(vent[c])):
                print()
                print("      --- %s (%d) ---" % (cause, len(vent[cause])))
                for rel, no, iface, txt in vent[cause]:
                    print("        %s:%d [%s] %s" % (rel, no, iface, txt))

    faux_nom, faux_arite, autre = confronter(cits, versionne)
    print("        %5d couple(s) JUSTES mais portes par une AUTRE interface couverte "
          "(appariement du recepteur, pas faute du depot)" % len(autre))
    for f in autre:
        print("            %s" % f)
    print("      %d citation(s) au SLOT/NOM faux" % len(faux_nom))
    for f in faux_nom:
        print("        %s" % f)
    print("[4] ARITE     : %d citation(s) dont le compte d'arguments contredit la signature"
          % len(faux_arite))
    for f in faux_arite:
        print("        %s" % f)

    if args.recenser:
        print()
        print("=== RECEPTEURS NON APPARIES (ce qui BORNE la tranche) ===")
        print("Un recepteur ci-dessous apparait sur une ligne qui cite un slot, sans qu'aucune")
        print("interface couverte ne soit reconnue. C'est le residu, chiffre.")
        for k in sorted(recense, key=lambda x: -recense[x])[:40]:
            print("  %5d  %s" % (recense[k], k))
        print("  ... %d recepteur(s) distinct(s) au total" % len(recense))

    if args.mutants:
        print()
        print("=== CONTRE-EPREUVE (a_mordu est rendu SEPAREMENT du verdict) ===")
        base = jouer(versionne, cits, derive)
        for nom, quoi in MUTANTS.items():
            mut = jouer(muter(versionne, nom, cits), cits, derive)
            print("  %-16s a_mordu=%-5s  cliquet %d -> %d, nom %d -> %d, arite %d -> %d   (%s)"
                  % (nom, str(mut != base).upper(), base[0], mut[0], base[1], mut[1],
                     base[2], mut[2], quoi))

    #: LE CACHE (#486-r1) -- muet dans le regime normal : la sortie avec cache chaud doit etre
    #: BIT POUR BIT celle d'un run a froid. Ecrit uniquement dans le regime CANONIQUE ; un
    #: `--fenetre N` ou un `--virgule-bloquante` produirait d'autres jeux de parametres, et les
    #: ecrire chasserait du fichier les entrees que la boucle de merge utilise.
    canonique = args.fenetre == FENETRE and not args.virgule_bloquante
    if args.verifier_cache:
        divergences = verdict_cache.verifier(cache())
        print()
        print("=== VERIFICATION DU CACHE VERSIONNE (#486-r1) ===")
        print("  entrees sur disque : %d   recalculees : %d"
              % (len(cache()._sur_disque), len(cache()._vues)))
        for d in divergences:
            print("  DIVERGENCE %s" % d)
        if divergences:
            #: rc DEDIE : ce n'est pas le verdict du cliquet sur le depot, c'est le CACHE qui ment.
            print("  rc=3 -- le cache versionne n'atteste PAS ce que le calcul rend. Le")
            print("  REGENERER : python scripts/python/probe_477r25_slots_autres_interfaces.py")
            return 3
        print("  OK -- chaque entree du cache vaut ce que le recalcul integral produit.")
    _ecrit = None
    if canonique and not args.verifier_cache:
        # #486-r22 : garde le cache pour demander PLUS BAS si cette reecriture a CHANGE le
        # fichier versionne -- un vrai rouge de gisement prime sur un rouge d'intendance.
        _ecrit = cache()
        _ecrit.enregistrer()

    rouge = bool(ecarts or faux_nom or faux_arite)
    print()
    print("VERDICT : %s" % ("ROUGE" if rouge else "VERT"))
    if derive is None:
        print("  NB : l'etage 1 n'a PAS ete mesure -- ce vert ne dit rien du metadata,")
        print("       seulement que le depot est coherent avec l'entree versionnee.")
    if rouge:
        return 1
    return verdict_cache.rendre_compte_du_cache(_ecrit, 0) if _ecrit is not None else 0


if __name__ == "__main__":
    raise SystemExit(main())
