"""#477-r24-r1 -- le mapping slot <-> methode de `Core.Services.IOperationProcessor`.

    python scripts/python/probe_477r24r1_slots_interface.py
    python scripts/python/probe_477r24r1_slots_interface.py --regenerer
    python scripts/python/probe_477r24r1_slots_interface.py --mutants
    python scripts/python/probe_477r24r1_slots_interface.py --courbe

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
_SLOT = (r"v?slot\s*(?i:d'interface\s*|itf\s*)?"
         r"(?:[`*]{0,2}(?:Core\.Services\.)?(?:I?OperationProcessor|processor|proc)[`*]{0,2}\s*)?"
         r"[`*]{0,2}\+?(?P<n%d>0x[0-9a-fA-F]+|\d+)[`*]{0,2}")

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
#: l'autre cliquet, et re-mesures ici : sans eux, l'elargissement sort 4 desaccords de plus,
#: tous FAUX (« le slot 0x21 QUE `RunPhase` invoque » designe le slot APPELE, pas la methode
#: nommee ; une enumeration verticale apparie le nom d'un item au slot du SUIVANT).
_RENVOIS = ("slot", "que ", "qu'", "interrog", "invoq", "appel", "utilis", "evalu", "->", "→")


def _entre(n: int, traverse: bool) -> str:
    """Le remplissage tolere entre les deux membres d'un couple, borne a `n` caracteres.

    `traverse` dit si ce remplissage a le droit de franchir un SAUT DE LIGNE. C'est le SEUL
    parametre par lequel la fenetre agit sur les formes B et C ; les formes A et D, elles,
    separent leurs membres par un separateur qui traverse deja (cf. `_esp`).
    """
    classe = "[^);:,]" if traverse else r"[^\n);:,]"
    return r"(?:(?!%s)%s){0,%d}?" % ("|".join(_RENVOIS), classe, n)


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


def _regex_couples(traverse: bool):
    """LES TROIS FORMES DE COUPLE (slot, nom) RETENUES COMME ATTESTATION.

    Un nom simplement PRESENT sur la ligne ne compte pas : il faut qu'il soit ADJACENT au slot.
    Sans cette contrainte, une ligne de `backlog.md` fournit trente « noms » et le controle
    devient du bruit (mesure #477-r24-r1 : 32 desaccords, 30 faux).
    """
    esp = _esp(traverse)
    coupure = _COUPURE if traverse else ""
    return (
        #: A -- `slot 0x7e = MoveUnit`, `slot **0x43** = `OperationProcessor$$ApplyDamage``
        re.compile((_SLOT % 0) + esp + r"(?:=|->|:)" + esp + r"[`*]{0,2}(?:" + _QUAL + r")?"
                   + coupure + (_NOM % 0)),
        #: B -- `processor.FinishAttack` slot 0x3b   (nom PUIS slot, colles)
        #: ⚠ ELLE NE FRANCHIT JAMAIS LE SAUT DE LIGNE, meme en regime fenetre. Dans une
        #: enumeration verticale, le nom ecrit AVANT appartient a l'item precedent, pas au slot
        #: qui suit -- cran mesure par #477-r30, conserve ici a l'identique.
        re.compile(_QUAL + (_NOM % 1) + _entre(40, False) + (_SLOT % 1)),
        #: C -- slot 0x3a ... `OperationProcessor$$StartAttack`   (slot PUIS nom, colles)
        re.compile((_SLOT % 2) + _entre(60, traverse) + _QUAL + coupure + (_NOM % 2)),
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


@dataclass(frozen=True)
class CitationNom:
    """Un slot designe par son NOM SEUL, sans numero (« le slot `KillUnit` de l'... »)."""

    fichier: str
    ligne: int
    nom: str
    texte: str


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
    reader = il2cpp_metadata.read(meta_path)
    order = il2cpp_metadata.class_method_order(
        build_dir() / "frida" / "methods.tsv", KLASS)
    reader.locate(order)
    table = reader.interface_table(ANCRES)
    print("[1] DERIVATION : %d slots lus dans le metadata (pas=%d octets), %d ancres concordantes"
          % (len(table), reader.entry_size or 0, len(ANCRES)))
    return table


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


def fichiers_balayes() -> list[Path]:
    try:
        out = subprocess.run(["git", "-C", str(REPO), "ls-files", "-z", *BALAYAGE_GLOBS],
                             capture_output=True, text=True, timeout=60, check=True)
    except (OSError, subprocess.SubprocessError) as exc:                # noqa: BLE001
        raise SystemExit("PAS MESURE : `git ls-files` muet (%s) -- le perimetre du balayage "
                         "ne peut pas etre DERIVE, et on n'en invente pas un." % exc)
    return [REPO / rel for rel in out.stdout.split("\0") if rel]


def _compter_args(texte: str, apres: int = 0) -> int | None:
    """Nombre d'arguments du premier appel parenthese apres `apres`, ou None s'il n'y en a pas.

    ⚠ `(...)` et `(...)` en ellipse rendent `None`, pas `1` : l'ellipse DIT que les arguments ne
    sont pas detailles. Les compter pour un ferait rougir une citation qui ne pretend rien sur
    l'arite (cran repris de #477-r25).
    """
    ouvre = texte.find("(", apres)
    if ouvre < 0:
        return None
    ferme = texte.find(")", ouvre)
    if 0 < ferme and texte[ouvre + 1:ferme].strip(". …") == "":
        return None
    prof, arg, vus = 0, 0, False
    for ch in texte[ouvre:]:
        if ch in "([<{":
            prof += 1
        elif ch in ")]>}":
            prof -= 1
            if prof == 0:
                return arg + 1 if vus else 0
        elif ch == "," and prof == 1:
            arg += 1
        elif prof == 1 and not ch.isspace():
            vus = True
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


def recolter(fenetre: int = FENETRE,
             traverse: bool | None = None) -> tuple[list[Citation], list[CitationNom], Ecartees]:
    """(couples (slot, nom), citations par NOM SEUL, ce qui est ecarte et compte).

    `fenetre` = nombre de LIGNES sur lesquelles un couple peut s'etaler. `traverse` dit si les
    formes A et C ont le droit de franchir le saut de ligne ; par defaut, oui des que la fenetre
    depasse 1.
    """
    if traverse is None:
        traverse = fenetre > 1
    couples = RE_COUPLES_ML if traverse else RE_COUPLES
    rx_nom_seul = RE_NOM_SEUL_ML if traverse else RE_NOM_SEUL
    retenues: list[Citation] = []
    noms_seuls: list[CitationNom] = []
    vus_noms: set[tuple[str, int, str]] = set()
    autre_iface = sans_couple = exemptees = 0
    for path in fichiers_balayes():
        rel = path.relative_to(REPO).as_posix()
        if rel in EXCLUS:
            continue
        try:
            texte = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if "slot" not in texte:
            continue
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
                    retenues.append(Citation(
                        fichier=rel, ligne=no, slot=slot, noms=(nom,), args=args,
                        ligne_nom=no_nom, texte=lignes[no - 1].strip()[:150]))
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
    #: Deduplication : plusieurs formes -- et, en fenetre, plusieurs BLOCS -- peuvent capter le
    #: MEME couple. La cle inclut la ligne du NOM : deux noms identiques a deux endroits
    #: differents sont deux citations.
    uniques: list[Citation] = []
    deja_vu: set[tuple[str, int, int, str, int]] = set()
    for c in retenues:
        cle = (c.fichier, c.ligne, c.slot, c.noms[0], c.ligne_nom)
        if cle in deja_vu:
            continue
        deja_vu.add(cle)
        uniques.append(c)
    return uniques, noms_seuls, Ecartees(autre_interface=autre_iface, sans_couple=sans_couple,
                                         exemptees=exemptees)


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
}


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
        #: ⚠ LE VOISIN DOIT PORTER UN NOM DIFFERENT. L'interface a des SURCHARGES a des slots
        #: adjacents (`0x2e`/`0x2f` = `RefreshEffects`, `0x34`/`0x35` = `ComputerAction`) : y
        #: prendre le voisin immediat rendrait une mutation NULLE qui passerait pour appliquee.
        def _voisin(slot: int) -> str | None:
            for d in (1, -1, 2, -2):
                v = table.get(slot + d)
                if v is not None and v[0] != table[slot][0]:
                    return v[0]
            return None

        mutees: list[Citation] = []
        touchees = 0
        for c in cits:
            autre = _voisin(c.slot) if (c.ligne != c.ligne_nom and c.slot in table) else None
            if autre is None:
                mutees.append(c)
                continue
            touchees += 1
            mutees.append(replace(c, noms=(autre,)))
        if not touchees:
            raise SystemExit("contre-epreuve IMPOSSIBLE : aucun couple ENJAMBANT a muter -- ce "
                             "mutant ne peut pas discriminer la fenetre, et on ne fait pas "
                             "semblant qu'il mord.")
        return table, mutees
    raise SystemExit("mutant inconnu : %s" % nom)


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
    args = ap.parse_args()

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

    cits, noms_seuls, ecartees = recolter(fenetre=args.fenetre)
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
    print("      ECARTEES, et c'est DIT :")
    print("        %5d ligne(s) dont le recepteur ne designe pas cet OperationProcessor "
          "(autre interface -- residu #477-r25)" % ecartees.autre_interface)
    print("        %5d ligne(s) qui citent un slot SANS lui accoler de nom, MEME sur %d "
          "ligne(s) -- rien a contredire, donc rien a garder"
          % (ecartees.sans_couple, args.fenetre))
    print("        %5d ligne(s) exemptees au site par %s" % (ecartees.exemptees,
                                                            MARQUEUR_REFUTE))
    print("        %5d fichier(s) EXCLU(S) et nomme(s) : %s" % (len(EXCLUS), ", ".join(EXCLUS)))
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

    rouge = bool(ecarts or faux_nom or faux_arite or faux_seuls)
    print()
    print("VERDICT : %s" % ("ROUGE" if rouge else "VERT"))
    if table is None:
        print("  NB : l'etage 1 n'a PAS ete mesure -- ce vert ne dit rien du metadata,")
        print("       seulement que le depot est coherent avec l'entree versionnee.")
    return 1 if rouge else 0


if __name__ == "__main__":
    raise SystemExit(main())
