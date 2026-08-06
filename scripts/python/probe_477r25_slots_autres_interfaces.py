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
from symbols_layout import build_dir, current_build                     # noqa: E402

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
    ("IdunBattle.Entities.Abilities", "IActiveAbility", ("IActiveAbility",)),
)

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
_SLOT = r"v?slot\s*(?:d'interface\s*|itf\s*)?[`*]{0,2}\+?(?P<n%d>0x[0-9a-fA-F]+|\d+)[`*]{0,2}"

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
_RENVOIS = ("slot", "que ", "qu'", "interrog", "invoq", "appel", "utilis")
_ENTRE = r"(?:(?!%s)[^\n)]){0,%%d}?" % "|".join(_RENVOIS)

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


@dataclass(frozen=True)
class Citation:
    fichier: str
    ligne: int
    iface: str
    slot: int
    nom: str
    args: int | None
    texte: str


@dataclass(frozen=True)
class Ecartees:
    """Ce que l'etage 3 n'a PAS retenu. Un compte filtre DIT ce qu'il filtre."""

    sans_interface: int = 0
    deja_gardee: int = 0
    multi_non_qualifie: int = 0
    sans_couple: int = 0
    exemptees: int = 0
    nom_absent: tuple[str, ...] = ()


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
    reader = il2cpp_metadata.read(meta_path)
    methods_tsv = build_dir() / "frida" / "methods.tsv"
    reader.locate(il2cpp_metadata.class_method_order(
        methods_tsv, "%s.%s" % ANCRES_TYPES[0]))
    ancres = [(ns, nm, il2cpp_metadata.class_method_order(methods_tsv, "%s.%s" % (ns, nm)))
              for ns, nm in ANCRES_TYPES]
    lay = reader.locate_types(ancres)
    out: dict[str, dict[int, tuple[str, int, int]]] = {}
    refus: list[str] = []
    for ns, nom, _ in INTERFACES:
        try:
            table = reader.type_methods(ns, nom)
        except il2cpp_metadata.MetadataRefused as exc:
            refus.append("%s : %s" % (nom, str(exc).splitlines()[0]))
            continue
        out[nom] = {m.slot: (m.name, m.param_count, m.flags) for m in table}
    print("[1] DERIVATION : grille des types pas=%d, methodStart=+%d, method_count=+%d "
          "(%d ancres controlees par leurs noms)"
          % (lay.step, lay.off_method_start, lay.off_method_count, len(lay.ancres)))
    print("      %d interface(s) lues, %d slot(s) au total"
          % (len(out), sum(len(v) for v in out.values())))
    for r in refus:
        print("      REFUS : %s" % r)
    if refus:
        raise SystemExit("ROUGE : %d interface(s) declaree(s) ne se lisent pas dans le "
                         "metadata -- ont-elles change de nom ?" % len(refus))
    return out


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
        "#interface\tslot\tmethode\tparam_count\tflags",
    ]
    for _, iface, _ in INTERFACES:
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


def fichiers_balayes() -> list[Path]:
    try:
        out = subprocess.run(["git", "-C", str(REPO), "ls-files", "-z", *BALAYAGE_GLOBS],
                             capture_output=True, text=True, timeout=60, check=True)
    except (OSError, subprocess.SubprocessError) as exc:                # noqa: BLE001
        raise SystemExit("PAS MESURE : `git ls-files` muet (%s) -- le perimetre du balayage "
                         "ne peut pas etre DERIVE, et on n'en invente pas un." % exc)
    return [REPO / rel for rel in out.stdout.split("\0") if rel]


def _motifs(alias: tuple[str, ...]) -> str:
    return "|".join(re.escape(a) for a in alias)


def _regex_recepteur(alias: tuple[str, ...]) -> re.Pattern[str]:
    return re.compile(r"(?<![A-Za-z0-9_])(?:%s)(?![A-Za-z0-9_])" % _motifs(alias))


def _regex_couples(alias: tuple[str, ...], qualificateur_obligatoire: bool):
    """Les trois formes de couple (slot, nom), instanciees pour un jeu de recepteurs."""
    qual = r"(?:(?:[A-Za-z0-9_.<>]*\.)?(?:%s)(?:\$\$|\.)|(?<![A-Za-z0-9_])\$\$)" % _motifs(alias)
    #: Forme A -- `slot 0x7e = MoveUnit`. Le qualificateur y est OPTIONNEL quand la ligne ne
    #: mentionne qu'UNE interface : sans cela, la forme la plus courante du depot est perdue.
    a_qual = qual if qualificateur_obligatoire else "(?:%s)?" % qual
    return (
        re.compile((_SLOT % 0) + r"\s*(?:=|->|:)\s*[`*]{0,2}" + a_qual + (_NOM % 0)),
        #: Forme D -- `battleQuery.<slot 0x7d> GetAdjacentEnemies(...)`. LE RECEPTEUR PRECEDE
        #: LE SLOT, et le nom suit sans qualificateur ni signe egal. C'est la forme qu'ecrit
        #: le cas nomme (`case-250`), et aucune des trois autres ne la capte -- mesure : les
        #: deux attributions litigieuses `0x7c`/`0x80` etaient INVISIBLES au probe sans elle.
        #: L'attribution y est explicite (recepteur colle au slot), donc elle vaut AUSSI en
        #: regime multi-interface.
        re.compile(r"(?:%s)\s*\.\s*[`*<]{0,3}" % _motifs(alias) + (_SLOT % 1)
                   + r"[`*>]{0,3}\s*" + (_NOM % 1)),
        #: Forme B -- `battleQuery.GetAdjacentEnemies` ... slot 0x7d   (nom PUIS slot)
        re.compile(qual + (_NOM % 2) + (_ENTRE % 40) + (_SLOT % 2)),
        #: Forme C -- slot 0x7d ... `BattleQuery$$GetAdjacentEnemies`   (slot PUIS nom)
        re.compile((_SLOT % 3) + (_ENTRE % 60) + qual + (_NOM % 3)),
    )


#: Les regex sont construites UNE fois : deux jeux par interface (qualificateur obligatoire
#: ou non), selon que la ligne mentionne une seule interface ou plusieurs.
_COUPLES = {iface: (_regex_couples(alias, False), _regex_couples(alias, True))
            for _, iface, alias in INTERFACES}
_RECEPTEURS = {iface: _regex_recepteur(alias) for _, iface, alias in INTERFACES}
_RE_DEJA_GARDEE = _regex_recepteur(DEJA_GARDEE)


def _compter_args(texte: str) -> int | None:
    """Nombre d'arguments du premier appel parenthese, ou None s'il n'y en a pas."""
    ouvre = texte.find("(")
    if ouvre < 0:
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


def recolter(tables: dict[str, dict[int, tuple[str, int, int]]]) -> tuple[
        list[Citation], Ecartees, dict[str, int]]:
    """(citations retenues, ce qui est ecarte et compte, recensement des recepteurs)."""
    retenues: list[Citation] = []
    sans_iface = deja = multi = sans_couple = exempt = 0
    nom_absent: list[str] = []
    recense: dict[str, int] = {}
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
        for no, ligne in enumerate(texte.splitlines(), 1):
            if not re.search(r"v?slot", ligne):
                continue
            vues = [iface for _, iface, _ in INTERFACES if _RECEPTEURS[iface].search(ligne)]
            if not vues:
                if _RE_DEJA_GARDEE.search(ligne):
                    deja += 1
                else:
                    sans_iface += 1
                    for m in _RE_RECEVEUR_CANDIDAT.finditer(ligne):
                        recense[m.group(1)] = recense.get(m.group(1), 0) + 1
                continue
            if MARQUEUR_REFUTE in ligne:
                exempt += 1
                continue
            multi_iface = len(vues) > 1 or bool(_RE_DEJA_GARDEE.search(ligne))
            trouve = False
            for iface in vues:
                table = tables.get(iface, {})
                #: ⚠ EN REGIME MULTI-INTERFACE, SEULE LA FORME A EST GARDEE. Les formes B et
                #: C rapprochent un nom et un slot SEPARES par du texte -- et quand la ligne
                #: parle de deux interfaces, ce texte est justement ce qui les separe :
                #: « `BattleQuery$$GetNormalAttackPrediction` invoque `IDamagePrediction`
                #: slot 9 » attribuerait le slot 9 d'IDamagePrediction a la methode de
                #: BattleQuery. Mesure : 2 faux positifs sur 59 leves par ce seul cran.
                #: Les formes A et D restent : leur attribution est portee par un
                #: qualificateur ou un recepteur COLLE, pas par la proximite.
                formes = _COUPLES[iface][1 if multi_iface else 0]
                if multi_iface:
                    formes = formes[:2]
                for k, rx in enumerate(formes):
                    for m in rx.finditer(ligne):
                        slot = int(m.group("n%d" % k), 0)
                        nom = m.group("nom%d" % k)
                        trouve = True
                        if nom not in {v[0] for v in table.values()}:
                            nom_absent.append(
                                "%s:%d [%s] slot 0x%x = %s -- ce nom n'est a AUCUN slot de "
                                "cette interface | %s" % (rel, no, iface, slot, nom,
                                                          ligne.strip()[:120]))
                            continue
                        queue = ligne[m.end():]
                        args = _compter_args(queue) if RE_APPEL.match(queue) else None
                        retenues.append(Citation(fichier=rel, ligne=no, iface=iface, slot=slot,
                                                 nom=nom, args=args,
                                                 texte=ligne.strip()[:150]))
            if not trouve:
                if multi_iface:
                    multi += 1
                else:
                    sans_couple += 1
    #: Deduplication : deux formes peuvent capter le MEME couple sur la meme ligne.
    uniques: list[Citation] = []
    deja_vu: set[tuple[str, int, str, int, str]] = set()
    for c in retenues:
        cle = (c.fichier, c.ligne, c.iface, c.slot, c.nom)
        if cle in deja_vu:
            continue
        deja_vu.add(cle)
        uniques.append(c)
    return uniques, Ecartees(sans_interface=sans_iface, deja_gardee=deja,
                             multi_non_qualifie=multi, sans_couple=sans_couple,
                             exemptees=exempt, nom_absent=tuple(nom_absent)), recense


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
    args = ap.parse_args()

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

    cits, ecartees, recense = recolter(versionne)
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

    print("[3] CITATIONS : %d attestation(s) (slot ET nom ADJACENTS) sur %d fichier(s)"
          % (len(cits), len({c.fichier for c in cits})))
    print("      ECARTEES, et c'est DIT :")
    print("        %5d ligne(s) sans aucun recepteur d'interface couverte"
          % ecartees.sans_interface)
    print("        %5d ligne(s) citant IOperationProcessor -- gardees par #477-r24-r1"
          % ecartees.deja_gardee)
    print("        %5d ligne(s) MULTI-interfaces dont le couple n'est pas qualifie"
          % ecartees.multi_non_qualifie)
    print("        %5d ligne(s) citant un slot SANS lui accoler de nom" % ecartees.sans_couple)
    print("        %5d ligne(s) exemptees au site par %s" % (ecartees.exemptees,
                                                            MARQUEUR_REFUTE))
    print("        %5d fichier(s) EXCLU(S) et nomme(s) : %s" % (len(EXCLUS), ", ".join(EXCLUS)))
    print("        %5d couple(s) dont le NOM est absent de l'interface appariee "
          "(indecidable -- listes, ni verts ni rouges)" % len(ecartees.nom_absent))
    for f in ecartees.nom_absent:
        print("            %s" % f)

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

    rouge = bool(ecarts or faux_nom or faux_arite)
    print()
    print("VERDICT : %s" % ("ROUGE" if rouge else "VERT"))
    if derive is None:
        print("  NB : l'etage 1 n'a PAS ete mesure -- ce vert ne dit rien du metadata,")
        print("       seulement que le depot est coherent avec l'entree versionnee.")
    return 1 if rouge else 0


if __name__ == "__main__":
    raise SystemExit(main())
