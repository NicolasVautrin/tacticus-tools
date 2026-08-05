"""Le CLIQUET A TROIS ETATS : classer chaque divergence entre flux natif et flux emis.

Pur, offline, sans session : il prend DEUX textes et rend un verdict. Le montage live (monter
un runner, capturer le flux natif, reconstruire les entrees du port) vit dans
`probe_477r15a_stream_conformance.py`.

CE QU'IL COMPARE, ET COMMENT IL LE DIT
--------------------------------------
Il aligne les deux flux LIGNE A LIGNE (`difflib.SequenceMatcher`, deterministe), puis nomme
chaque divergence par sa FORME et son SYMBOLE (`MANQUANT Action=X`, `EN_TROP Group=Y`,
`VALEUR Tag=Z`). Le symbole vient toujours des trois enums natifs -- jamais d'un extrait de
texte -- donc une renumerotation de build fait bouger le nom, pas la cle.

Chaque divergence tombe dans un des trois etats de `case-477r15` § 6 :
`conforme` / `divergent CONNU` (inscrit au registre) / `divergent NOUVEAU` (le seul qui rougit).

CE QU'IL NE COMPARE PAS -- ET C'EST IMPRIME, PAS SOUS-ENTENDU
--------------------------------------------------------------
« Un comparateur qui ne compare que ce que les deux cotes possedent est une projection
IMPLICITE, pire que le registre tenu a la main, parce que personne ne l'a ecrite. »
(#477-r11 § 5). Trois bornes, toutes DERIVEES et toutes publiees par `rapport()` :

  (a) les membres de `GroupType` / `StepType` / `TagKey` que le corpus n'exerce PAS. Le
      perimetre se derive des ENUMS (104 / 62 / 244), jamais de l'observe : un comparateur
      calibre sur l'observe serait muet sur le reste SANS LE DIRE (`#477-r13`) ;
  (b) les omissions STRUCTURELLES du flux natif -- ce qu'aucun comparateur de flux ne pourra
      jamais trancher, quoi qu'on porte (#477-r11 § 5, #477-r17) ;
  (c) les ENTREES que le port a recues du flux natif lui-meme. Comparer une valeur qu'on a
      copiee de l'oracle ne mesure rien : ces champs sont nommes, et exclus du verdict.
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Sequence

from .divergence_registry import KNOWN_DIVERGENCES
from .group_type import GroupType
from .step_type import StepType
from .tag_key import TagKey

# Les quatre formes de ligne, telles que `StreamCache` les ecrit. Une ligne qui n'entre dans
# aucune est un HORS-FORME : elle rougit, parce que c'est ainsi qu'on apprend qu'une forme
# nous manque au lieu de l'ignorer en silence.
RE_GROUP = re.compile(
    r"^(?P<ind> *)Group=(?P<sym>[^ ]*) Entity=(?P<entity>[^ ]*)"
    r" Source=(?P<source>[^ ]*) InitialTarget=(?P<target>.*)$")
RE_ACTION = re.compile(r"^(?P<ind> *)Action=(?P<sym>[^ ]*) Entity=(?P<entity>.*)$")
RE_TAG = re.compile(r"^(?P<ind> *)Tag=(?P<sym>[^:]*):(?P<value>.*)$")
RE_FINISH = re.compile(r"^(?P<ind> *)Finish_Group$")

#: Ce que le flux natif N'A PAS -- borne (b), derivee de #477-r11 § 5 et #477-r17. Ce ne sont
#: pas des divergences : ce sont des grandeurs qu'AUCUN diff de flux ne peut trancher.
OMISSIONS_STRUCTURELLES: dict[str, str] = {
    "StatType.Defense": "aucun porteur dans le flux",
    "StatType.EvasionChance": "aucun porteur dans le flux",
    "StatType.ExtraHits": "MODIFICATION seule -- le flux rapporte le delta, jamais la valeur",
    "StatType.ExtraHitsMelee": "MODIFICATION seule",
    "StatType.ExtraMaxDamage": "MODIFICATION seule",
    "StatType.ExtraPierce": "MODIFICATION seule",
    "StatType.ExtraPierceMelee": "MODIFICATION seule",
    "StatType.ExtraPierceRanged": "MODIFICATION seule",
    "StatType.ExtraRange": "MODIFICATION seule",
    "observeBattle.visualId": "le flux ne nomme JAMAIS le kit d'une unite (#477-r17) : un "
                              "rapport de divergence dira « l'entite 83 », pas « le second "
                              "adeptCanoness »",
    "observeBattle.rank": "aucun porteur dans le flux",
    "PRNG.tirage_brut": "le flux dit « a crite : non » et le degat final, jamais le nombre "
                        "tire ni le seuil -- cette information vit dans le canal "
                        "`replayRngEvents` (#477-r11 § 6)",
}

MANQUANT = "MANQUANT"
EN_TROP = "EN_TROP"
VALEUR = "VALEUR"


@dataclass(frozen=True)
class Ligne:
    """Une ligne de flux, decomposee. `cle_symbole` est ce qui NOMME la ligne (`Action=AddUnit`),
    `texte` sa forme brute (ce qui est reellement compare)."""

    numero: int
    texte: str
    forme: str          # "Group" | "Action" | "Tag" | "Finish_Group" | "HORS_FORME" | "VIDE"
    symbole: str        # membre d'enum, ou "" pour Finish_Group / hors-forme
    profondeur: int

    @property
    def cle_symbole(self) -> str:
        if self.forme == "Finish_Group":
            return "Finish_Group"
        if self.forme in ("HORS_FORME", "VIDE"):
            return self.forme
        return "%s=%s" % (self.forme, self.symbole)


@dataclass
class Divergence:
    forme: str          # MANQUANT | EN_TROP | VALEUR
    cle: str            # "<forme> <cle_symbole>"
    cause: Optional[str]        # non-None <=> inscrite au registre
    natif: Optional[str] = None
    port: Optional[str] = None
    numero_natif: Optional[int] = None

    @property
    def connue(self) -> bool:
        return self.cause is not None


@dataclass
class Rapport:
    lignes_natif: int = 0
    lignes_port: int = 0
    egales: int = 0
    divergences: List[Divergence] = field(default_factory=list)
    hors_forme: List[Ligne] = field(default_factory=list)
    #: cles EXERCEES par ce corpus -- l'entree de la purge du registre.
    cles_exercees: set = field(default_factory=set)
    #: bornes (a) : ce que le corpus n'exerce pas, par enum.
    non_exerces: dict = field(default_factory=dict)
    #: bornes (c) : champs copies du natif, donc non mesures.
    entrees_du_natif: List[str] = field(default_factory=list)

    @property
    def nouvelles(self) -> List[Divergence]:
        return [d for d in self.divergences if not d.connue]

    @property
    def connues(self) -> List[Divergence]:
        return [d for d in self.divergences if d.connue]

    @property
    def conforme(self) -> bool:
        return not self.divergences and not self.hors_forme


def parse_ligne(numero: int, texte: str) -> Ligne:
    """Range une ligne dans une des quatre formes. La profondeur se DEDUIT de l'indentation
    (4 espaces par niveau) -- elle n'est pas comparee, elle sert au diagnostic."""
    if texte == "":
        return Ligne(numero, texte, "VIDE", "", 0)
    for forme, rx in (("Group", RE_GROUP), ("Action", RE_ACTION), ("Tag", RE_TAG)):
        m = rx.match(texte)
        if m:
            return Ligne(numero, texte, forme, m.group("sym"),
                         len(m.group("ind")) // 4)
    m = RE_FINISH.match(texte)
    if m:
        return Ligne(numero, texte, "Finish_Group", "", len(m.group("ind")) // 4)
    return Ligne(numero, texte, "HORS_FORME", "", 0)


def parse_flux(texte: str) -> List[Ligne]:
    """Decoupe sur LF. Le separateur n'est PAS normalise : un CRLF laisserait un `\\r` en fin
    de ligne, la ligne deviendrait HORS_FORME, et le probe le dirait -- c'est voulu (mesurer
    le separateur sur un fichier reecrit est le piege de #477-r11)."""
    return [parse_ligne(i, ln) for i, ln in enumerate(texte.split("\n"))]


def _sans_vides(lignes: Iterable[Ligne]) -> List[Ligne]:
    return [l for l in lignes if l.forme != "VIDE"]


def comparer(flux_natif: str, flux_port: str,
             entrees_du_natif: Sequence[str] = ()) -> Rapport:
    """Aligne les deux flux et CLASSE chaque divergence. Ne decide rien : le verdict se lit
    sur `Rapport.nouvelles`."""
    natif = _sans_vides(parse_flux(flux_natif))
    port = _sans_vides(parse_flux(flux_port))
    rap = Rapport(lignes_natif=len(natif), lignes_port=len(port),
                  entrees_du_natif=list(entrees_du_natif))
    rap.hors_forme = [l for l in natif + port if l.forme == "HORS_FORME"]

    sm = difflib.SequenceMatcher(a=[l.texte for l in natif],
                                 b=[l.texte for l in port], autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            rap.egales += i2 - i1
            for l in natif[i1:i2]:
                rap.cles_exercees.add(l.cle_symbole)
            continue
        if tag == "replace":
            # Un `replace` apparie position a position tant que les deux cotes en ont ;
            # le reliquat retombe sur MANQUANT / EN_TROP.
            commun = min(i2 - i1, j2 - j1)
            for k in range(commun):
                a, b = natif[i1 + k], port[j1 + k]
                forme = VALEUR if a.cle_symbole == b.cle_symbole else MANQUANT
                cle = "%s %s" % (forme, a.cle_symbole)
                rap.divergences.append(Divergence(
                    forme, cle, KNOWN_DIVERGENCES.get(cle),
                    natif=a.texte, port=b.texte, numero_natif=a.numero))
                rap.cles_exercees.add(cle)
            i1, j1 = i1 + commun, j1 + commun
            tag = "delete" if i2 > i1 else "insert"
        if tag == "delete" or i2 > i1:
            for a in natif[i1:i2]:
                cle = "%s %s" % (MANQUANT, a.cle_symbole)
                rap.divergences.append(Divergence(
                    MANQUANT, cle, KNOWN_DIVERGENCES.get(cle),
                    natif=a.texte, numero_natif=a.numero))
                rap.cles_exercees.add(cle)
        if tag == "insert" or j2 > j1:
            for b in port[j1:j2]:
                cle = "%s %s" % (EN_TROP, b.cle_symbole)
                rap.divergences.append(Divergence(
                    EN_TROP, cle, KNOWN_DIVERGENCES.get(cle), port=b.texte))
                rap.cles_exercees.add(cle)

    rap.non_exerces = perimetre_non_exerce(natif + port)
    return rap


def perimetre_non_exerce(lignes: Sequence[Ligne]) -> dict:
    """Borne (a) : par enum, les membres qu'AUCUNE des deux faces n'a ecrits.

    Le perimetre se derive de l'ENUM, jamais de l'observe -- c'est tout l'objet de `#477-r13`."""
    vus = {"GroupType": set(), "StepType": set(), "TagKey": set()}
    for l in lignes:
        if l.forme == "Group":
            vus["GroupType"].add(l.symbole)
        elif l.forme == "Action":
            vus["StepType"].add(l.symbole)
        elif l.forme == "Tag":
            vus["TagKey"].add(l.symbole)
    out = {}
    for nom, cls in (("GroupType", GroupType), ("StepType", StepType), ("TagKey", TagKey)):
        tous = {m.name[:-1] if m.name == "None_" else m.name for m in cls}
        out[nom] = {"total": len(tous), "exerces": len(vus[nom] & tous),
                    "non_exerces": sorted(tous - vus[nom])}
    return out


def entrees_perimees(cles_exercees_du_corpus: set) -> List[str]:
    """LA PURGE. Toute entree du registre que le corpus n'exerce PAS est PERIMEE et doit rougir.

    Sans elle le registre ne fait que grossir jusqu'a tout couvrir -- lecon de `probe_181`. La
    reponse a une entree perimee est de la SUPPRIMER du registre, jamais de l'elargir."""
    return sorted(set(KNOWN_DIVERGENCES) - set(cles_exercees_du_corpus))


def rapport(rap: Rapport, perimees: Sequence[str] = (), lignes_max: int = 12) -> List[str]:
    """Le compte rendu ASCII. Il IMPRIME les trois bornes -- non compare != egal."""
    out: List[str] = []
    out.append("FLUX : natif=%d lignes  port=%d lignes  EGALES=%d"
               % (rap.lignes_natif, rap.lignes_port, rap.egales))
    out.append("DIVERGENCES : %d connues / %d NOUVELLES"
               % (len(rap.connues), len(rap.nouvelles)))
    if rap.hors_forme:
        out.append("  HORS DES 4 FORMES : %d ligne(s) -- une forme nous manque"
                   % len(rap.hors_forme))
        for l in rap.hors_forme[:lignes_max]:
            out.append("    L%d [%s]" % (l.numero, l.texte))
    vues_connues: dict[str, int] = {}
    for d in rap.connues:
        vues_connues[d.cle] = vues_connues.get(d.cle, 0) + 1
    for cle in sorted(vues_connues):
        out.append("  CONNUE x%-4d %s" % (vues_connues[cle], cle))
        out.append("               cause : %s" % KNOWN_DIVERGENCES[cle])
    for d in rap.nouvelles[:lignes_max]:
        out.append("  NOUVELLE  %s" % d.cle)
        if d.natif is not None:
            out.append("     natif [%s]" % d.natif)
        if d.port is not None:
            out.append("     port  [%s]" % d.port)
    if len(rap.nouvelles) > lignes_max:
        out.append("  ... et %d autre(s) NOUVELLE(s)" % (len(rap.nouvelles) - lignes_max))
    if perimees:
        out.append("REGISTRE PERIME : %d entree(s) que ce corpus n'exerce PLUS -- a SUPPRIMER"
                   % len(perimees))
        for cle in perimees:
            out.append("    %s" % cle)
    out.append("")
    out.append("NON COMPARE (publie, jamais sous-entendu) -- non compare != egal")
    out.append("  (a) perimetre DERIVE des enums, membres qu'aucune face n'ecrit :")
    for nom in ("GroupType", "StepType", "TagKey"):
        d = rap.non_exerces.get(nom) or {}
        out.append("      %-10s exerces %d / %d" % (nom, d.get("exerces", 0), d.get("total", 0)))
    out.append("  (b) omissions STRUCTURELLES du flux (aucun diff ne les tranchera) : %d"
               % len(OMISSIONS_STRUCTURELLES))
    for nom in sorted(OMISSIONS_STRUCTURELLES):
        out.append("      %-32s %s" % (nom, OMISSIONS_STRUCTURELLES[nom]))
    out.append("  (c) ENTREES prises du flux natif (copiees de l'oracle => non mesurees) : %d"
               % len(rap.entrees_du_natif))
    for nom in rap.entrees_du_natif:
        out.append("      %s" % nom)
    return out
