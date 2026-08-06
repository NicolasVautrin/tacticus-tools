#!/usr/bin/env python3
"""#477-r22 -- le BLOC 2 de `System_StartMatch` : `Action=PrepareTurn` + `Group=StartTurn`.

    python probe_477r22_turn_phase.py [--session N] [--boards C1_02,MC1_67] [--tours 2]
                                      [--p-units ...] [--a-units ...] [--sans-roster-crafte]

CE QU'IL MESURE, ET CE QU'IL COPIE
----------------------------------
#477-r20 a porte l'ENVELOPPE de `System_StartMatch` et chiffre son contenu en TROIS blocs ;
#477-r21 a porte le bloc 1 (l'arbre d'activation). Cette tranche porte le bloc 2 -- le dernier
appel de `IdunBattle.Operations.StartMatchOperation$$Execute`,
`processor.<slot 0x16>(TurnStage.Start, false, true)` c'est-a-dire `ContinueTurnPhase`.

⚠ LE NUMERO DE SLOT EST UN REPERE DE CALL-SITE, PAS UNE ATTRIBUTION ETABLIE. `#477-r24-r1` a
mesure sur `Core.Services.IOperationProcessor` un decalage slot->classe local de 12, INCOMPATIBLE
avec la lecture de `case-477r20` reprise ici ; une des deux est fausse et rien ne dit laquelle.
Ce probe n'en depend pas : il identifie les deux operations par leur EMISSION (seuls producteurs
de `StepType.PrepareTurn` et de `GroupType.StartTurn` dans le binaire), et c'est le FLUX qui
tranche -- 29 / 29 couples a l'egalite brute.

⚠ CE BLOC-LA SE RECOLTE HORS DE SON GROUPE, ET C'EST LA MESURE QUI COMPTE. Le `Group=StartTurn`
n'a qu'UN producteur dans le binaire (`IdunBattle.Operations.StartTurnOperation$$Execute`), et la
lambda `InputMessageProcessor$$u003CVisitu003Eb__20_0` de `Visit(StartTurnMessage)` atteint
`ContinueTurnPhase` par le MEME slot avec les MEMES trois arguments. Le probe confronte donc
TOUTES les occurrences du flux, pas seulement celle du groupe -- et publie le compte.
Ce compte est MESURE, jamais deduit d'une ventilation par groupe racine : deux fois deja sur ce
dossier une telle ventilation a ete prise pour une prediction d'atteignabilite, et refutee.

Le port emet une FORME a partir de DONNEES. Les donnees (identifiants d'entite, joueurs, contenu
du groupe) viennent du flux natif : elles sont COPIEES et comptent en borne (c) sans rien
prouver. Ce qui est MESURE est ce que le port DERIVE :

  (D1) LA SEQUENCE DES STAGES. Le port recoit DEUX entiers (`TurnStage` courant et demande) et
       en derive quels etages s'executent, donc que `Action=PrepareTurn` precede
       `Group=StartTurn` et que rien ne s'intercale. Le probe balaie les CINQ stages de depart
       possibles et publie combien produisent le texte natif : un depart qui ne conviendrait pas
       est une REFUTATION de la boucle ;
  (D2) L'APPARIEMENT CLE <-> VALEUR des trois tags de `PrepareTurn`, et le fait que
       `Action=StartTurn` n'en porte QU'UN, le meme `Match_PreviousPlayerId`. Le parseur rend les
       tags dans l'ordre ALPHABETIQUE ; le port les re-emet dans l'ordre des ORDINAUX ;
  (D3) L'ENTITE. Trois appels natifs distincts a `GetMatchEntity(state).<Id>` (l'action de
       preparation, l'ouverture du groupe, l'action du groupe) ; le port les fait suivre le meme
       parametre, et le probe EXIGE que les trois coincident sur le flux ;
  (D4) L'OUVERTURE INCONDITIONNELLE du groupe et la PLACE de `Action=StartTurn`, premiere ligne,
       AVANT tout le contenu. C'est l'inverse d'`Effect_Refresh` (#477-r21), dont l'ouverture est
       gardee par `eventActions.Count > 0` ;
  (D5) LE `Source=` VIDE et l'`InitialTarget=` VIDE, lus comme litteral d'index 0 et
       `default(BEntityId?)`.

⚠ CE PROBE NE PEUT PAS RENDRE VERT SUR LE CONTENU DU GROUPE, ET C'EST VOULU. Ce qui n'est pas
porte est ENUMERE, sa somme confrontee au total, et jamais ampute ligne a ligne.

DISCIPLINE : deux boards de tailles differentes + un roster crafte, un runner a la fois, dispose
dans le `finally`, state-files sous `logs/`. ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import probe_477r15a_stream_conformance as R15A  # noqa: E402
import probe_477r19_process_removals as R19  # noqa: E402
import probe_477r20_start_match as R20  # noqa: E402
import probe_477r21_activation_tree as R21  # noqa: E402
from engine.entities.turn_stage import TurnStage  # noqa: E402
from engine.streams import GroupType, StepType, StreamCache, StreamDispatcher, TagKey  # noqa: E402
from engine.streams import conformance as CONF  # noqa: E402
from engine.streams.turn_phase import (START_TURN_SOURCE_ID,  # noqa: E402
                                       continue_turn_phase, prepare_turn, start_turn)
from engine.streams.verify_turn_finished import (FLAG,  # noqa: E402
                                                 NoActionAvailableFlags, UnitTurnState,
                                                 mark_unit_as_no_action_available,
                                                 verify_units_turn_finished)

ROOT = HERE.parents[1]
OUT = ROOT / "logs"

MesureImpossible = R15A.MesureImpossible
profondeur = R20.profondeur

#: Memes deux boards que les quatre crans precedents (35 vs 63 tuiles).
BOARDS_DEFAUT = ("C1_02", "MC1_67")

#: LES TROIS TAGS DE `Action=PrepareTurn`, DANS L'ORDRE DES ORDINAUX -- l'ordre dans lequel
#: `StreamCache$$Action` les ecrit (`SortedDictionary<TagKey,int>`). Ils sont LUS dans les trois
#: `Dictionary$$Add` de `IdunBattle.Operations.PrepareTurnOperation$$Execute` (`0x9d`, `0x9e`,
#: `0x9f`), et le probe REFUSE un flux qui n'en porterait pas exactement ces trois-la : une
#: decoupe qui accepterait autre chose ne mesurerait plus la meme chose.
TAGS_PREPARE = (TagKey.Match_CurrentPlayerId, TagKey.Match_PreviousPlayerId,
                TagKey.Match_AmountOfTurnsStartedByCurrentPlayer)

#: L'UNIQUE TAG DE `Action=StartTurn` -- un seul `Dictionary$$Add` dans
#: `IdunBattle.Operations.StartTurnOperation$$Execute`.
TAG_START_TURN = TagKey.Match_PreviousPlayerId

#: LE STAGE COURANT AU MOMENT DE L'APPEL, par contexte. Ce sont les deux seules valeurs que la RE
#: autorise, et le probe les CONFRONTE (cf. `stages_de_depart_compatibles`) au lieu de les
#: supposer :
#:   * dans `System_StartMatch` : `TurnComponent+0x10` vaut `0` -- le composant vient d'etre
#:     construit, et `TurnStage.Change` EST le zero de l'enum ;
#:   * en racine : le `Group=EndTurn` qui precede est l'emission du stage `End`, donc
#:     `TurnComponent+0x10 == TurnStage.End`.
DEPART_IMBRIQUE = TurnStage.Change
DEPART_RACINE = TurnStage.End


@dataclass
class PrepareObs:
    """Une `Action=PrepareTurn` observee."""

    entity: int
    tags: List[Tuple[str, int]] = field(default_factory=list)
    """DANS L'ORDRE DU FLUX -- pour que l'ordre reste derive par le port."""


@dataclass
class TurnObs:
    """Un couple `Action=PrepareTurn` + `Group=StartTurn` observe."""

    racine: str
    prof: int
    prepare: PrepareObs
    groupe_entity: int
    source: str
    initial_target: str
    action_entity: int
    action_tags: List[Tuple[str, int]]
    portes: List[dict]
    hors: List[dict]
    lignes: List[str]
    """LE TEXTE NATIF COMPLET du couple, entete de `PrepareTurn` incluse."""
    marques: List[dict] = field(default_factory=list)
    """LA QUEUE DU GROUPE (#477-r22-r1) : les `Action=ChangeStats` + `Tag=%s` du slot `0x21`,
    dans l'ordre du flux. Chacune fait EXACTEMENT deux lignes.""" \
        % TagKey.UnitStats_ActionsAvailable.name
    candidats: List[int] = field(default_factory=list)
    """LES UNITES DU JOUEUR COURANT, DERIVEES DE DEUX CANAUX QUI IGNORENT LA QUEUE : la carte
    `entite -> Tag=Unit_Owner_Id` construite depuis les `Action=AddUnit` du flux, filtree par le
    `Tag=Match_CurrentPlayerId` de l'`Action=PrepareTurn` du couple. C'est ce que le natif
    itere (`PlayerComponent$$get_CurrentlyOwnedUnitIds`), et l'ordre est celui des
    `Action=AddUnit`."""
    drapeaux_avant: frozenset = frozenset()
    """L'ETAT DU BIT `UnitFlag.NoActionAvailable` JUSTE AVANT LE `Group=StartTurn`, rejoue depuis
    le DEBUT du flux : chaque `Tag=%s:0` le pose, chaque `:1` le retire. Les sites qui le posent
    hors de cette tranche (`FinishUnitTurnOperation$$Execute`, `ActiveAbilityOperation$$
    ExecuteInternal`) ne sont pas portes ici -- leur EFFET sur le bit est donc rejoue depuis le
    flux, et c'est declare.""" % TagKey.UnitStats_ActionsAvailable.name

    @property
    def lignes_contenu(self) -> int:
        return (sum(p["lignes"] for p in self.portes) + sum(h["lignes"] for h in self.hors)
                + sum(m["lignes"] for m in self.marques))

    @property
    def entites_marquees(self) -> List[int]:
        return [m["entite"] for m in self.marques]


def _entite(txt: str) -> int:
    return 0 if txt == "NO_ENTITY" else int(txt)


def _marque(lignes: List[str], i: int) -> Optional[Tuple[int, int]]:
    """LA SIGNATURE, STRUCTURELLE, D'UNE EMISSION DU SLOT `0x21` -- `(entite, valeur)` ou `None`.

    `IdunBattle.Operations.MarkUnitAsNoActionAvailableOperation$$Execute` construit un
    `Dictionary<TagKey,int>` NEUF et n'y fait qu'UN SEUL `Add` : sa ligne d'action porte donc
    EXACTEMENT un tag, et ce tag est `TagKey.UnitStats_ActionsAvailable`. Le probe exige les
    trois traits -- `Action=ChangeStats`, un tag a `prof + 1`, et PAS de second tag -- plutot
    que de reconnaitre le motif au seul nom du tag : une `Action=ChangeStats` a plusieurs cles
    sort d'un AUTRE producteur (`TransformUnitOperation`), et la confondre absorberait dans ce
    foyer une forme qu'il ne produit pas."""
    ma = CONF.RE_ACTION.match(lignes[i])
    if not ma or ma.group("sym") != StepType.ChangeStats.name:
        return None
    prof = profondeur(lignes[i])
    if i + 1 >= len(lignes):
        return None
    mt = CONF.RE_TAG.match(lignes[i + 1])
    if (not mt or profondeur(lignes[i + 1]) != prof + 1
            or mt.group("sym") != TagKey.UnitStats_ActionsAvailable.name):
        return None
    if i + 2 < len(lignes):
        suivant = CONF.RE_TAG.match(lignes[i + 2])
        if suivant is not None and profondeur(lignes[i + 2]) == prof + 1:
            return None
    return _entite(ma.group("entity")), int(mt.group("value"))


def _partitionner(contenu: List[str]) -> dict:
    """La partition PORTE / MARQUES / HORS PERIMETRE du contenu du groupe, au moyen du parseur de
    #477-r21 -- c'est exactement le meme jeu de formes, et le reutiliser est ce qui rend la
    RECOLTE reelle : un sous-arbre `Effect_Refresh` porte ici est porte par le MEME code.

    Un sous-arbre part HORS PERIMETRE EN ENTIER des qu'il porte une forme non portee ; il n'est
    jamais ampute ligne a ligne, ce qui laisserait croire que le reste est comparable.

    ⚠ LES MARQUES NE SONT PAS DES SOUS-ARBRES, ET LEUR REGLE EST STRUCTURELLE (#477-r22-r1). Une
    emission du slot `0x21` est une `Action=` NUE a la profondeur du groupe, suivie de son unique
    tag : elle ne passe donc pas par `_formes_portees` (qui juge des SOUS-ARBRES) mais par
    `_marque`. C'est aussi ce qui interdit qu'un `Tag=%s` cache AILLEURS dans le flux fasse entrer
    au perimetre un sous-arbre entier.""" % TagKey.UnitStats_ActionsAvailable.name
    portes: List[dict] = []
    hors: List[dict] = []
    marques: List[dict] = []
    i, n = 0, len(contenu)
    prof_attendue = profondeur(contenu[0]) if contenu else 0
    while i < n:
        ligne = contenu[i]
        mg = CONF.RE_GROUP.match(ligne)
        if not mg or profondeur(ligne) != prof_attendue:
            m = _marque(contenu, i) if profondeur(ligne) == prof_attendue else None
            if m is not None:
                marques.append({"entite": m[0], "valeur": m[1], "lignes": 2,
                                "texte": contenu[i:i + 2]})
                i += 2
                continue
            hors.append({"raison": "ligne isolee", "forme": ligne.strip().split(" ")[0],
                         "lignes": 1, "texte": [ligne]})
            i += 1
            continue
        j = R21._bloc(contenu, i)
        sous = contenu[i:j + 1]
        etrangeres = sorted(R21._formes(sous) - R21._formes_portees())
        if etrangeres:
            hors.append({"raison": "forme(s) non portee(s)", "forme": ",".join(etrangeres),
                         "lignes": len(sous), "texte": sous})
        else:
            portes.append({"obs": R21._lire_sous_arbre(sous), "lignes": len(sous), "texte": sous})
        i = j + 1
    return {"portes": portes, "hors": hors, "marques": marques}


def lire_couple(lignes: List[str], i_prepare: int, racine: str,
                proprio: Optional[Dict[int, int]] = None,
                drapeaux: frozenset = frozenset()) -> TurnObs:
    """LA DECOUPE D'UN COUPLE, structurelle et VERIFIEE.

    Elle est LUE dans `ContinueTurnPhaseOperation$$Execute` : la boucle traverse `Prepare` (qui
    emet l'action et ses trois tags), puis `Draft` (qui n'emet rien sur le regime confronte),
    puis `Start` (qui ouvre le groupe). Cinq refus l'arment, chacun capable de faire rougir :

      * la ligne `i_prepare` est une `Action=PrepareTurn` ;
      * les TROIS lignes suivantes sont des `Tag=` a `prof + 1`, et leurs symboles sont
        EXACTEMENT `TAGS_PREPARE`, dans cet ordre ;
      * la 5e ligne est un `Group=StartTurn` a la MEME profondeur que l'action -- c'est
        l'ancrage A1, et rien ne s'intercale ;
      * la 1re ligne du groupe est une `Action=StartTurn` portant EXACTEMENT un `Tag=` , et ce
        tag est `TAG_START_TURN` ;
      * la somme est exacte : `4 + 1 + 2 + contenu + 1 == len(couple)`."""
    ma = CONF.RE_ACTION.match(lignes[i_prepare])
    if not ma or ma.group("sym") != StepType.PrepareTurn.name:
        raise MesureImpossible("la ligne %d n'est pas une `Action=%s` : [%s]"
                               % (i_prepare, StepType.PrepareTurn.name, lignes[i_prepare]))
    prof = profondeur(lignes[i_prepare])
    prep = PrepareObs(entity=_entite(ma.group("entity")))
    for k in range(1, 1 + len(TAGS_PREPARE)):
        mt = CONF.RE_TAG.match(lignes[i_prepare + k])
        if not mt or profondeur(lignes[i_prepare + k]) != prof + 1:
            raise MesureImpossible("`Action=%s` sans son %de `Tag=` a la profondeur %d : [%s]"
                                   % (StepType.PrepareTurn.name, k, prof + 1,
                                      lignes[i_prepare + k]))
        prep.tags.append((mt.group("sym"), int(mt.group("value"))))
    attendus = [t.name for t in TAGS_PREPARE]
    if [n for n, _v in prep.tags] != attendus:
        raise MesureImpossible("`Action=%s` porte %s -- les trois `Dictionary$$Add` lus dans "
                               "`PrepareTurnOperation$$Execute` donnent %s"
                               % (StepType.PrepareTurn.name,
                                  ",".join(n for n, _v in prep.tags), ",".join(attendus)))

    i_groupe = i_prepare + 1 + len(TAGS_PREPARE)
    mg = CONF.RE_GROUP.match(lignes[i_groupe])
    if not mg or mg.group("sym") != GroupType.StartTurn.name or profondeur(lignes[i_groupe]) != prof:
        raise MesureImpossible("ANCRAGE A1 ROUGE : la ligne qui suit `Action=%s` + ses %d tags "
                               "n'est pas un `Group=%s` de profondeur %d : [%s]"
                               % (StepType.PrepareTurn.name, len(TAGS_PREPARE),
                                  GroupType.StartTurn.name, prof, lignes[i_groupe]))
    fin = R21._bloc(lignes, i_groupe)
    groupe = lignes[i_groupe:fin + 1]

    maa = CONF.RE_ACTION.match(groupe[1])
    if not maa or maa.group("sym") != StepType.StartTurn.name:
        raise MesureImpossible("la 1re ligne du `Group=%s` n'est pas `Action=%s` : [%s]"
                               % (GroupType.StartTurn.name, StepType.StartTurn.name, groupe[1]))
    action_tags: List[Tuple[str, int]] = []
    k = 2
    while k < len(groupe) - 1 and CONF.RE_TAG.match(groupe[k]):
        mt = CONF.RE_TAG.match(groupe[k])
        action_tags.append((mt.group("sym"), int(mt.group("value"))))
        k += 1
    if [n for n, _v in action_tags] != [TAG_START_TURN.name]:
        raise MesureImpossible("`Action=%s` porte %d tag(s) (%s) -- l'unique `Dictionary$$Add` "
                               "lu dans `StartTurnOperation$$Execute` donne %s"
                               % (StepType.StartTurn.name, len(action_tags),
                                  ",".join(n for n, _v in action_tags), TAG_START_TURN.name))

    contenu = groupe[k:-1]
    par = (_partitionner(contenu) if contenu
           else {"portes": [], "hors": [], "marques": []})
    # LES CANDIDATS SONT DERIVES, PAS LUS DANS LA QUEUE : c'est
    # `PlayerComponent$$get_CurrentlyOwnedUnitIds`
    # du joueur COURANT, reconstruit par la carte `Action=AddUnit` -> `Tag=Unit_Owner_Id` et le
    # `Tag=Match_CurrentPlayerId` de l'`Action=PrepareTurn`. Les deux canaux ignorent totalement
    # les lignes que le slot `0x21` ecrit -- c'est ce qui rend (D6) falsifiable.
    joueur = dict(prep.tags)[TagKey.Match_CurrentPlayerId.name]
    candidats = [e for e, o in (proprio or {}).items() if o == joueur]
    obs = TurnObs(racine=racine, prof=prof, prepare=prep,
                  groupe_entity=_entite(mg.group("entity")), source=mg.group("source"),
                  initial_target=mg.group("target"),
                  action_entity=_entite(maa.group("entity")), action_tags=action_tags,
                  portes=par["portes"], hors=par["hors"], marques=par["marques"],
                  candidats=candidats, drapeaux_avant=drapeaux,
                  lignes=lignes[i_prepare:fin + 1])
    attendu = (1 + len(TAGS_PREPARE)) + 1 + (1 + len(action_tags)) + obs.lignes_contenu + 1
    if attendu != len(obs.lignes):
        raise MesureImpossible("somme du couple FAUSSE : %d != %d -- une amputation ne serait "
                               "alors pas imputable" % (attendu, len(obs.lignes)))
    return obs


def couples_du_flux(flux: str) -> List[TurnObs]:
    """TOUS les couples du flux, dans l'ordre. Le nom du groupe RACINE de chacun est resolu par
    la pile, pour que la ventilation « dans `System_StartMatch` » / « ailleurs » soit MESUREE.

    ⚠ LE PARCOURS PART DES `Group=StartTurn`, PAS DES `Action=PrepareTurn`, et c'est ce qui rend
    l'ancrage A1 falsifiable : un `Group=StartTurn` qui ne serait PAS precede de son action ferait
    lever `lire_couple`, la ou partir des actions l'aurait simplement ignore.

    ⚠ LE PARCOURS TIENT DEUX ETATS QUI SE REJOUENT DEPUIS LE DEBUT DU FLUX (#477-r22-r1), et tous
    deux sont pris AVANT le couple, jamais dedans :

      * la carte `entite -> proprietaire`, alimentee par chaque `Action=AddUnit` et son
        `Tag=Unit_Owner_Id`. Elle est INCREMENTALE parce que le flux ajoute des unites en cours de
        bataille (une invocation apparait par un `Action=AddUnit` tardif) ;
      * le bit `UnitFlag.NoActionAvailable` par unite, pose par chaque `Tag=%s:0` et retire par
        chaque `:1`. Ces lignes-la sortent, pour la plupart, de call-sites du slot `0x76` que
        cette tranche NE PORTE PAS (`FinishUnitTurnOperation$$Execute`,
        `ActiveAbilityOperation$$ExecuteInternal`) : leur effet sur le bit est donc REJOUE depuis
        le flux, et c'est une entree declaree. Ce qui reste DERIVE, c'est ce que le port en fait
        -- la branche de `VerifyUnitTurnEnded`, donc la VALEUR emise.""" \
        % TagKey.UnitStats_ActionsAvailable.name
    lignes = [l for l in flux.split("\n") if l != ""]
    out: List[TurnObs] = []
    pile: List[str] = []
    proprio: Dict[int, int] = {}
    drapeaux: set = set()
    attente_owner: Optional[int] = None
    for i, ligne in enumerate(lignes):
        mg = CONF.RE_GROUP.match(ligne)
        if mg:
            if mg.group("sym") == GroupType.StartTurn.name:
                racine = pile[0] if pile else GroupType.StartTurn.name
                out.append(lire_couple(lignes, i - 1 - len(TAGS_PREPARE), racine,
                                       dict(proprio), frozenset(drapeaux)))
            pile.append(mg.group("sym"))
        elif CONF.RE_FINISH.match(ligne):
            if not pile:
                raise MesureImpossible("`Finish_Group` sans groupe ouvert, ligne %d" % i)
            pile.pop()
        ma = CONF.RE_ACTION.match(ligne)
        if ma and ma.group("sym") == StepType.AddUnit.name:
            attente_owner = _entite(ma.group("entity"))
        mt = CONF.RE_TAG.match(ligne)
        if (mt and attente_owner is not None
                and mt.group("sym") == TagKey.Unit_Owner_Id.name):
            proprio[attente_owner] = int(mt.group("value"))
            attente_owner = None
        marque = _marque(lignes, i)
        if marque is not None:
            entite, valeur = marque
            if valeur == 0:
                drapeaux.add(entite)
            else:
                drapeaux.discard(entite)
    if pile:
        raise MesureImpossible("%d groupe(s) jamais ferme(s)" % len(pile))
    return out


class Capture:
    def __init__(self) -> None:
        self.racines: List[str] = []

    def on_root_group_finished(self, group: str) -> None:
        self.racines.append(group)

    def on_log(self, chunk: str) -> None:
        pass


MUTATIONS = ("entite_prepare", "entite_start_turn", "valeur_previous", "prepare_permute",
             "prepare_tag_manquant", "tag_startturn", "ordre_action", "source_groupe",
             "depart_prepare",
             # `#477-r22-r1` -- la QUEUE du groupe (slot `0x21`) et la forme `Action=Info`
             "marque_valeur", "marque_entite", "marque_tag", "marque_branche", "marque_ordre",
             "verif_avant_corps", "info_entite", "info_tag_arme")


def applicable(nom: str, obs: TurnObs) -> bool:
    """LE DOMAINE DE DEFINITION D'UNE MUTATION, derive des DONNEES du couple.

    ⚠ IL EXISTE DEUX INERTIES, ET LES CONFONDRE REND LE GARDE INUTILISABLE. Mesure du
    2026-08-06, sur un roster 1v1 crafte : `ordre_action` (deplacer le contenu AVANT l'action)
    n'a mordu sur AUCUN des 6 couples -- non parce qu'elle serait morte, mais parce qu'AUCUN
    couple de ce regime n'a de contenu PORTE a deplacer (tout y est hors perimetre ou vide).

      * INERTE PAR CONSTRUCTION -- la mutation est applicable et ne change rien : elle ne
        mesure rien, quel que soit son verdict. C'est ROUGE ;
      * INERTE PAR ABSENCE DE DONNEE -- le corpus n'a aucun couple ou elle soit applicable :
        c'est une ATTENTION, du meme ordre que « derivation qu'aucune donnee n'exerce ».

    Le domaine est CALCULE ici, jamais declare a la main dans le verdict : c'est ce qui empeche
    d'excuser apres coup une mutation qui vient de ne pas mordre."""
    if nom == "ordre_action":
        # elle deplace `corps`, et `corps` est `None` quand aucun sous-arbre n'est PORTE
        return bool(obs.portes)
    if nom == "prepare_permute":
        # permuter deux valeurs EGALES ne change rien
        par_nom = dict(obs.prepare.tags)
        return (par_nom[TagKey.Match_CurrentPlayerId.name]
                != par_nom[TagKey.Match_PreviousPlayerId.name])
    if nom in ("marque_valeur", "marque_entite", "marque_tag", "marque_branche"):
        # sans AUCUNE marque, il n'y a rien a muter dans la queue du groupe
        return bool(obs.marques)
    if nom == "marque_ordre":
        # inverser l'ordre d'une liste d'UN element ne change rien
        return len(obs.marques) > 1
    if nom == "verif_avant_corps":
        # deplacer la queue AVANT le corps n'est observable que si les DEUX sont non vides
        return bool(obs.portes) and bool(obs.marques)
    if nom in ("info_entite", "info_tag_arme"):
        # elles mutent une `Action=Info` : il en faut une, PORTEE, dans le contenu du groupe
        return _compte_info(obs) > 0
    return True


def _compte_info(obs: TurnObs) -> int:
    """Le nombre d'`Action=Info` dans les sous-arbres PORTES du couple -- le domaine de la
    mutation `info_entite`, CALCULE, jamais declare."""
    def _visiter(o) -> int:
        if isinstance(o, R21.ActionObs):
            return 1 if o.step == StepType.Info.name else 0
        if isinstance(o, R21.AbilityPowerObs):
            return sum(_visiter(e) for e in o.enfants)
        return 0

    return sum(_visiter(p["obs"]) for p in obs.portes)


def _start_turn_mute(events: StreamDispatcher, obs: TurnObs, previous: int,
                     corps: Optional[Callable[[], None]], mutation: str,
                     verifier: Optional[Callable[[], None]] = None) -> None:
    """LES CONTRE-EPREUVES STRUCTURELLES -- celles qui ne se font pas en muant une DONNEE.

    Chacune reproduit `engine/streams/turn_phase.start_turn` AVEC UNE FAUTE PRECISE, lue comme
    la faute naturelle a cet endroit. Ce n'est PAS un chemin du port : c'est la variante que le
    port aurait pu prendre, et que le decompile refute.

    ⚠ LES TROIS VARIANTES APPELLENT `verifier` AU MEME ENDROIT QUE LE PORT (juste avant
    `FinishGroup`) : leur faute porte sur l'entete ou sur l'action, jamais sur la queue -- sinon
    elles mesureraient deux choses a la fois et leur rouge ne designerait plus rien."""
    if mutation == "tag_startturn":
        # `Match_CurrentPlayerId` a la place de `Match_PreviousPlayerId` : la faute naturelle,
        # puisque `StartTurnOperation` LIT les deux (`uVar7` et `local_res20`) et n'en ecrit qu'un
        events.start_group(GroupType.StartTurn, obs.groupe_entity, START_TURN_SOURCE_ID, None)
        events.action(StepType.StartTurn, obs.action_entity,
                      {int(TagKey.Match_CurrentPlayerId): int(previous)})
        if corps is not None:
            corps()
        if verifier is not None:
            verifier()
        events.finish_group()
        return
    if mutation == "ordre_action":
        # le contenu AVANT l'action, alors que le decompile place l'`Events.Action` juste apres
        # le `StartGroup` et les trois appels delegues APRES elle
        events.start_group(GroupType.StartTurn, obs.groupe_entity, START_TURN_SOURCE_ID, None)
        if corps is not None:
            corps()
        events.action(StepType.StartTurn, obs.action_entity,
                      {int(TAG_START_TURN): int(previous)})
        if verifier is not None:
            verifier()
        events.finish_group()
        return
    if mutation == "source_groupe":
        # `Source=` non vide : le slot de litteral resolu en index 0 (`""`) est ce qui le vide
        events.start_group(GroupType.StartTurn, obs.groupe_entity,
                           GroupType.StartTurn.name, None)
        events.action(StepType.StartTurn, obs.action_entity,
                      {int(TAG_START_TURN): int(previous)})
        if corps is not None:
            corps()
        if verifier is not None:
            verifier()
        events.finish_group()
        return
    raise MesureImpossible("mutation structurelle inconnue : %s" % mutation)


def etats_unites(obs: TurnObs, mutation: str = "") -> List[UnitTurnState]:
    """LES ENTREES DE `verify_units_turn_finished`, et la LIGNE DE PARTAGE de cette tranche.

    DERIVE (mesure) :
      * QUELLES unites le natif visite -- `candidats`, reconstruit depuis la carte
        `Action=AddUnit` / `Tag=Unit_Owner_Id` et le `Tag=Match_CurrentPlayerId`. Aucun des deux
        canaux ne regarde la queue du groupe. Si la derivation etait fausse, une unite marquee
        par le natif serait absente de l'iteration du port -> MANQUANT ;
      * DANS QUEL ORDRE -- celui des `Action=AddUnit` ;
      * `turn_ended`, pose a `False` par LECTURE et non par copie : le slot `0x21` est appele en
        FIN de `IdunBattle.Operations.StartTurnOperation$$Execute`, apres la boucle qui applique
        `IdunBattle.Entities.Components.UnitFlagsComponent$$RemoveTurnFlags` a CHAQUE unite de
        `PlayerComponent$$get_CurrentlyOwnedUnitIds` -- et `RemoveTurnFlags` retire
        INCONDITIONNELLEMENT `UnitFlag.TurnFinished`, dont `UnitFlagsComponent$$TurnEnded` est
        exactement le test ;
      * la BRANCHE de `VerifyUnitTurnEnded`, donc la VALEUR emise : elle sort du registre
        `NoActionAvailableFlags`, rejoue depuis le debut du flux (cf. `couples_du_flux`).

    COPIE (borne (c)) : les DEUX predicats de mobilite. `HasTilesToMoveTo` (pathfinding) et
    `HasActionAvailable` (prediction de degat) ne sont observables NULLE PART dans le flux ; le
    probe les pose au strict minimum qui reproduit la decision native, et l'assignation depend
    de la branche, ce qui la rend lisible :

      * drapeau PRESENT -> le natif emet ssi `tiles || action` : le probe pose `tiles = a_emis` ;
      * drapeau ABSENT  -> le natif emet ssi `!tiles && !action` : le probe pose
        `tiles = not a_emis`.

    ⚠ CE N'EST DONC PAS LA SELECTION QUI EST MESUREE, C'EST LA FORME ET LA VALEUR. Ecrire
    l'inverse serait une mesure circulaire ; le probe le DIT ici et le repete en borne (c)."""
    etats: List[UnitTurnState] = []
    emises = {m["entite"] for m in obs.marques}
    candidats = list(obs.candidats)
    if mutation == "marque_ordre":
        candidats.reverse()
    for entite in candidats:
        a_emis = entite in emises
        present = entite in obs.drapeaux_avant
        tiles = a_emis if present else (not a_emis)
        etats.append(UnitTurnState(entity_id=entite, turn_ended=False, is_dead=False,
                                   has_tiles_to_move_to=tiles, has_action_available=False))
    return etats


def _verifier_mute(events: StreamDispatcher, flags: NoActionAvailableFlags,
                   unites: List[UnitTurnState], mutation: str) -> None:
    """LES CONTRE-EPREUVES DE LA QUEUE -- chacune reproduit
    `IdunBattle.Operations.VerifyUnitsTurnFinishedOperation$$VerifyUnitTurnEnded` +
    `MarkUnitAsNoActionAvailableOperation$$Execute` AVEC UNE FAUTE PRECISE, lue comme la faute
    naturelle a cet endroit. Ce n'est PAS un chemin du port."""
    for unite in unites:
        if unite.turn_ended or unite.is_dead:
            continue
        present = flags.has(unite.entity_id)
        if mutation == "marque_branche":
            # le test du drapeau INVERSE : la faute naturelle, puisque le nom de l'operation
            # (`MarkUnitAsNoActionAvailable`) et le sens du tag (`ActionsAvailable`) s'opposent
            present = not present
        if not present:
            if unite.has_tiles_to_move_to or unite.has_action_available:
                continue
            reverse = False
        else:
            if not unite.has_tiles_to_move_to and not unite.has_action_available:
                continue
            reverse = True
        change = flags.remove(unite.entity_id) if reverse else flags.add(unite.entity_id)
        if not change:
            continue
        entite = unite.entity_id
        cle = int(TagKey.UnitStats_ActionsAvailable)
        valeur = 1 if reverse else 0
        if mutation == "marque_valeur":
            # la valeur SUIT le drapeau au lieu de l'inverser : `0` quand on RETIRE le drapeau
            valeur = 0 if reverse else 1
        elif mutation == "marque_entite":
            # l'entite de MATCH a la place de celle de l'unite -- ce que portent les DEUX autres
            # emissions du meme groupe (`Action=StartTurn`, `Action=PrepareTurn`)
            entite += 1
        elif mutation == "marque_tag":
            # `UnitStats_TurnFinished` (0x70) a la place de `UnitStats_ActionsAvailable` (0x6f) :
            # les deux cles sont voisines par l'ordinal ET par le sens, et le flux les montre
            # cote a cote dans `Group=User_EndTurn`
            cle = int(TagKey.UnitStats_TurnFinished)
        events.action(StepType.ChangeStats, int(entite), {cle: int(valeur)})


def emettre(obs: TurnObs, depart: TurnStage, mutation: str = "") -> str:
    """Emet le couple AVEC LE PORT, a la profondeur du natif.

    ⚠ L'ENVELOPPE `System_StartMatch` DU CAS IMBRIQUE EST OUVERTE PUIS RETIREE DU TEXTE COMPARE :
    elle appartient a #477-r20, deja confrontee, et cette tranche ne se re-decerne pas son vert.

    ⚠ LES CINQ STAGES SONT PASSES EXPLICITEMENT, MEME VIDES. `TurnStage.Change` et
    `TurnStage.Draft` recoivent un no-op : le premier parce que
    `IdunBattle.Operations.ChangeTurnOperation$$Execute` n'appelle JAMAIS le dispatcher de flux
    (LU sur son decompile entier), le second parce que le slot `0x19` n'ecrit rien sur le regime
    confronte (0 ligne entre `Action=PrepareTurn` et `Group=StartTurn`, sur toutes les
    occurrences). `TurnStage.End` n'est PAS fourni : si la sequence le traversait, `execute_stage`
    LEVERAIT plutot que d'emettre un `Group=EndTurn` que ce paquet ne porte pas."""
    cache = StreamCache()
    capture = Capture()
    cache.add_listener(capture)
    events = StreamDispatcher()
    events.subscribe(cache)
    if obs.prof == 1:
        events.start_group(GroupType.System_StartMatch, 1, "", None)

    par_nom = dict(obs.prepare.tags)
    courant = par_nom[TagKey.Match_CurrentPlayerId.name]
    precedent = par_nom[TagKey.Match_PreviousPlayerId.name]
    demarres = par_nom[TagKey.Match_AmountOfTurnsStartedByCurrentPlayer.name]
    entite_prepare = obs.prepare.entity
    entite_start = obs.groupe_entity
    previous_start = dict(obs.action_tags)[TAG_START_TURN.name]

    if mutation == "entite_prepare":
        entite_prepare += 1
    elif mutation == "entite_start_turn":
        entite_start += 1
    elif mutation == "valeur_previous":
        previous_start += 1
    elif mutation == "prepare_permute":
        courant, precedent = precedent, courant

    corps = None
    if obs.portes:
        def corps() -> None:  # noqa: E306
            for p in obs.portes:
                # `info_entite` / `info_tag_arme` sont des mutations de #477-r21 (la forme
                # `Action=Info`), relayees ici parce que c'est CE probe qui les EXERCE : le
                # BLOC 1, corpus de #477-r21, ne porte aucune `Action=Info` (domaine 0 la-bas).
                R21.emettre_sous_arbre(
                    events, p["obs"],
                    mutation if mutation in ("info_entite", "info_tag_arme") else "")

    # LA QUEUE DU GROUPE -- slot `0x21` =
    # `Core.Services.OperationProcessor$$VerifyUnitsTurnFinished`
    # (arite 0, LU dans `data/symbols/<build>/metadata/interface_slots.tsv`). Le registre est
    # RECONSTRUIT a chaque appel : `emettre` est jouee des dizaines de fois par couple (cinq
    # departs x N mutations), et un registre partage ferait dependre le resultat de l'ordre des
    # appels -- exactement le genre de vert qui ne prouve rien.
    flags = NoActionAvailableFlags(obs.drapeaux_avant)
    unites = etats_unites(obs, mutation)

    def _verifier() -> None:
        if mutation in ("marque_valeur", "marque_entite", "marque_tag", "marque_branche"):
            _verifier_mute(events, flags, unites, mutation)
            return
        verify_units_turn_finished(events, flags, unites)

    def _prepare() -> None:
        if mutation == "prepare_tag_manquant":
            # le 3e `Dictionary$$Add` omis -- un flux ampute d'une seule ligne
            events.action(StepType.PrepareTurn, entite_prepare,
                          {int(TagKey.Match_CurrentPlayerId): int(courant),
                           int(TagKey.Match_PreviousPlayerId): int(precedent)})
            return
        prepare_turn(events, entite_prepare, courant, precedent, demarres)

    def _start() -> None:
        if mutation in ("tag_startturn", "ordre_action", "source_groupe"):
            _start_turn_mute(events, obs, previous_start, corps, mutation, _verifier)
            return
        if mutation == "verif_avant_corps":
            # le slot `0x21` AVANT les six autres appels delegues, alors que le decompile le
            # place APRES le cinquieme `EvaluateAbilities(TurnStart_Actions)` et juste avant
            # `Events.FinishGroup()`
            start_turn(events, entite_start, previous_start, _verifier, corps)
            return
        start_turn(events, entite_start, previous_start, corps, _verifier)

    operations = {
        TurnStage.Change: lambda: None,
        TurnStage.Prepare: _prepare,
        TurnStage.Draft: lambda: None,
        TurnStage.Start: _start,
    }
    depart_effectif = TurnStage.Prepare if mutation == "depart_prepare" else depart
    continue_turn_phase(events, depart_effectif, TurnStage.Start, operations)

    if obs.prof == 1:
        events.finish_group()
    lignes = [l for l in "".join(capture.racines).split("\n") if l != ""]
    if obs.prof == 1:
        lignes = lignes[1:-1]
    return "\n".join(lignes) + "\n"


def natif_porte(obs: TurnObs) -> str:
    """Le texte NATIF ampute des sous-arbres HORS PERIMETRE -- et de rien d'autre.

    ⚠ LES MARQUES SONT CONCATENEES APRES LES SOUS-ARBRES, ET C'EST FALSIFIABLE. Le decompile
    place le slot `0x21` APRES les six autres appels delegues ; si le flux montrait une marque
    AVANT un sous-arbre porte, cette concatenation la deplacerait et le diff rougirait. Ce n'est
    donc pas une commodite de mise en forme : c'est la derivation d'ordre, exposee au diff."""
    tete = obs.lignes[:1 + len(TAGS_PREPARE) + 1 + 1 + len(obs.action_tags)]
    corps = [l for p in obs.portes for l in p["texte"]]
    queue = [l for m in obs.marques for l in m["texte"]]
    return "\n".join(tete + corps + queue + [obs.lignes[-1]]) + "\n"


def stages_de_depart_compatibles(obs: TurnObs) -> List[str]:
    """(D1) LES DEPARTS QUI PRODUISENT LE TEXTE NATIF, sur les CINQ possibles.

    C'est ce qui fait de la sequence une DERIVATION et non une entree : le port recoit un stage
    de depart, la boucle en derive les etages traverses, et le flux TRANCHE. Un depart de
    `Prepare` ou de `Draft` supprime l'`Action=PrepareTurn` ; un depart de `Start` ne produit
    RIEN. Restent `Change` et `End`, indiscernables par le flux (le stage `Change` n'emet pas) --
    et c'est publie, pas tu."""
    attendu = natif_porte(obs)
    out = []
    for stage in TurnStage:
        try:
            if emettre(obs, stage) == attendu:
                out.append(stage.name)
        except (MesureImpossible, ValueError):
            pass
    return out


def derivations(couples: List[TurnObs]) -> dict:
    """CE QUE LES DERIVATIONS ONT A MORDRE SUR CE CORPUS -- publie, jamais suppose."""
    d2 = sum(1 for c in couples
             if [n for n, _v in c.prepare.tags] != sorted(n for n, _v in c.prepare.tags))
    d2b = sum(1 for c in couples
              if dict(c.prepare.tags)[TagKey.Match_CurrentPlayerId.name]
              != dict(c.prepare.tags)[TagKey.Match_PreviousPlayerId.name])
    d3 = sum(1 for c in couples
             if c.prepare.entity == c.groupe_entity == c.action_entity)
    d4_vides = sum(1 for c in couples if not c.portes and not c.hors and not c.marques)
    d4_pleins = len(couples) - d4_vides
    # --- (D6)..(D9) : la QUEUE du groupe (#477-r22-r1). Chacune publie SON compte d'exercice.
    d6_marques = sum(len(c.marques) for c in couples)
    d6_candidats = sum(len(c.candidats) for c in couples)
    # (D6) RECOUPEMENT : toute unite marquee par le natif doit etre un CANDIDAT derive.
    d6_hors_candidats = sum(1 for c in couples for e in c.entites_marquees
                            if e not in c.candidats)
    # (D7) la VALEUR, derivee du registre : `1` <=> le drapeau etait POSE avant le groupe.
    d7_accord = d7_total = 0
    valeurs = set()
    for c in couples:
        for m in c.marques:
            d7_total += 1
            valeurs.add(m["valeur"])
            if (m["valeur"] == 1) == (m["entite"] in c.drapeaux_avant):
                d7_accord += 1
    # (D8) l'ORDRE : les marques suivent-elles l'ordre des `Action=AddUnit` ?
    d8_ordonnes = sum(1 for c in couples if c.marques and c.entites_marquees
                      == [e for e in c.candidats if e in set(c.entites_marquees)])
    # (D9) `Action=Info` entrees au perimetre (#477-r22-r1, second motif).
    d9_info = sum(_compte_info(c) for c in couples)
    return {"d1_departs": [stages_de_depart_compatibles(c) for c in couples],
            "d2_prepare_hors_ordre_alpha": d2,
            "d2_current_different_de_previous": d2b,
            "d3_trois_entites_egales": d3,
            "d4_groupes_vides": d4_vides, "d4_groupes_pleins": d4_pleins,
            "d6_marques": d6_marques, "d6_candidats": d6_candidats,
            "d6_hors_candidats": d6_hors_candidats,
            "d7_accord": d7_accord, "d7_total": d7_total,
            "d7_valeurs": sorted(valeurs),
            "d8_couples_ordonnes": d8_ordonnes,
            "d8_couples_avec_marques": sum(1 for c in couples if c.marques),
            "d9_info": d9_info}


def conformite_du_foyer(flux: str) -> dict:
    """LE FOYER `MarkUnitAsNoActionAvailableOperation$$Execute` CONFRONTE SUR TOUT LE FLUX
    -- la generalisation de cette tranche, et le SEUL endroit ou la valeur `0` est exercee.

    Le `Group=StartTurn` n'exerce qu'une des deux branches de `VerifyUnitTurnEnded` : dans nos
    trois scenarios, TOUTES ses marques valent `1` (le drapeau y est RETIRE). La valeur `0` --
    celle que le natif ecrit quand il POSE le drapeau -- n'y apparait jamais, parce qu'une unite
    qui commence son tour a toujours une tuile ou aller. Elle apparait EN NOMBRE ailleurs dans le
    flux (`FinishUnitTurnOperation$$Execute`, `ActiveAbilityOperation$$ExecuteInternal`,
    `MoveUnitOperation`), qui appellent le MEME slot `0x76` et donc le MEME foyer.

    Ce controle rejoue donc le flux ENTIER : pour chaque emission du foyer, il DERIVE le sens
    (`reverse = <le drapeau est-il pose ?>`, lu dans le registre construit par les emissions
    PRECEDENTES) puis emet avec le port et confronte le texte.

    ⚠ CE N'EST PAS CIRCULAIRE, ET C'EST CE QUI LE REND UTILE. Le registre a l'instant `k` ne
    connait que les lignes `1..k-1` ; la valeur de la ligne `k` est une PREDICTION. Une
    prediction fausse se voit de deux facons : une VALEUR differente, ou -- si le port croit le
    drapeau deja dans l'etat demande -- une ligne MANQUANTE, le gate d'`Add`/`Remove` ayant
    supprime l'emission."""
    lignes = [l for l in flux.split("\n") if l != ""]
    flags = NoActionAvailableFlags()
    valeurs: Dict[int, int] = {}
    egales = 0
    divergences: List[str] = []
    for i, ligne in enumerate(lignes):
        m = _marque(lignes, i)
        if m is None:
            continue
        entite, valeur = m
        valeurs[valeur] = valeurs.get(valeur, 0) + 1
        cache = StreamCache()
        capture = Capture()
        cache.add_listener(capture)
        events = StreamDispatcher()
        events.subscribe(cache)
        mark_unit_as_no_action_available(events, flags, entite, flags.has(entite))
        emis = [l.strip() for l in "".join(capture.racines).split("\n") if l.strip()]
        attendu = [lignes[i].strip(), lignes[i + 1].strip()]
        if emis == attendu:
            egales += 1
        else:
            divergences.append("L%d natif=%s port=%s" % (i, attendu, emis or ["<RIEN>"]))
    return {"emissions": sum(valeurs.values()), "egales": egales,
            "divergences": divergences, "valeurs": dict(sorted(valeurs.items()))}


def _porte_un_damage(obs) -> bool:
    """« ce sous-arbre PORTE contient-il un `Group=Damage` ? » -- pour le compte AVANT/APRES du
    verdict. Recursif parce que le flux les montre imbriques sous un `Group=Ability_Power`."""
    if isinstance(obs, R21.DamageObs):
        return True
    if isinstance(obs, R21.AbilityPowerObs):
        return any(_porte_un_damage(e) for e in obs.enfants)
    return False


def _groupes_damage(flux: str) -> List[Tuple[int, List[str], "R21.DamageObs"]]:
    """TOUS les `Group=Damage` du flux, dans l'ordre : `(ligne, texte, obs)`.

    Le parcours ne suppose RIEN de leur place : ils apparaissent sous `User_UseAbility`, sous
    `System_ProcessDeaths` et -- c'est ce qui ouvre `#477-r34` -- sous `StartTurn`."""
    lignes = [l for l in flux.split("\n") if l != ""]
    out = []
    for i, ligne in enumerate(lignes):
        mg = CONF.RE_GROUP.match(ligne)
        if not mg or mg.group("sym") != GroupType.Damage.name:
            continue
        fin = R21._bloc(lignes, i)
        sous = lignes[i:fin + 1]
        out.append((i, sous, R21._lire_groupe_damage(sous)))
    return out


def _emettre_damage(obs: "R21.DamageObs", mutation: str = "") -> str:
    """Emet UN `Group=Damage` avec le port, sans indentation d'enveloppe."""
    cache = StreamCache()
    capture = Capture()
    cache.add_listener(capture)
    events = StreamDispatcher()
    events.subscribe(cache)
    R21.emettre_sous_arbre(events, obs, mutation)
    return "".join(capture.racines)


def _nu(lignes) -> List[str]:
    """Le texte sans son indentation -- un `Group=Damage` du flux est imbrique, celui du port
    part de la profondeur 0. C'est la SEULE difference qu'on neutralise, et elle est de mise en
    forme : `StreamCache` la produit deja, elle a ete confrontee par `#477-r15a`."""
    if isinstance(lignes, str):
        lignes = lignes.split("\n")
    return [l.strip() for l in lignes if l.strip()]


def conformite_du_groupe_damage(flux: str) -> dict:
    """LE FOYER `IdunBattle.Operations.ApplyDamageOperation$$Execute` CONFRONTE SUR TOUT LE FLUX
    -- la GENERALISATION de `#477-r34`, et la raison pour laquelle ses contre-epreuves vivent
    ici plutot que dans la boucle des couples.

    ⚠ LES COUPLES N'EN PORTENT QUE TROIS, ET AUCUN SUR LA MOITIE DES SCENARIOS. Le
    `Group=StartTurn` ne contient un `Group=Damage` que lorsqu'un effet de TUILE frappe au debut
    du tour (`EnvFireTileDamage`, `EnvDespoiledGroundTileDamage`) ; sur `C1_02` a 2 tours il n'y
    en a aucun. Des mutations jouees sur ce seul corpus auraient donc un domaine NUL sur
    plusieurs scenarios -- exactement le vice que le garde-fou de ce probe refuse. Elles sont
    jouees sur TOUTES les occurrences du flux, dont le compte est PUBLIE.

    ⚠ CE N'EST PAS LE MEME REGIME QUE `conformite_du_foyer` (le slot `0x76`), ET LA DIFFERENCE
    EST DECLAREE. Le foyer des marques DERIVE sa valeur d'un registre construit par les lignes
    PRECEDENTES : sa valeur est une prediction. Ici, les quinze tags sont des ENTREES lues dans
    le flux (borne (c)) ; ce que le port DERIVE est enumere par `R21.entrees_damage` --
    l'ENTITE (une valeur, trois occurrences produites), le booleen `Attack_WasMemberKilled`
    (derive de la PRESENCE d'un autre tag), la conditionnalite de
    `UnitStats_NumberOfMembers_Change`, la FORME du groupe et l'ordre de ses lignes."""
    groupes = _groupes_damage(flux)
    egales = 0
    divergences: List[str] = []
    # (DD1) les TROIS occurrences de l'entite coincident-elles dans le NATIF ?
    dd1 = sum(1 for _i, _t, o in groupes
              if o.groupe_entity == o.action_entity == dict(o.tags).get(TagKey.Target_Id.name))
    # (DD2) `Attack_WasMemberKilled` suit-il la PRESENCE de `UnitStats_NumberOfMembers_Change` ?
    dd2 = dd2_tues = 0
    for _i, _t, o in groupes:
        d = dict(o.tags)
        tue = TagKey.UnitStats_NumberOfMembers_Change.name in d
        dd2_tues += 1 if tue else 0
        if bool(d[TagKey.Attack_WasMemberKilled.name]) == tue:
            dd2 += 1
    voies: Dict[str, int] = {}
    for _i, _t, o in groupes:
        d = dict(o.tags)
        for _champ, cle in R21.SOURCE_TAGS + R21.ADDITIONAL_HIT_SOURCE_TAGS:
            if cle.name in d:
                voies[cle.name] = voies.get(cle.name, 0) + 1
    avec_corps = sum(1 for _i, _t, o in groupes if o.enfants)
    for i, texte, obs in groupes:
        emis = _nu(_emettre_damage(obs))
        if emis == _nu(texte):
            egales += 1
        elif len(divergences) < 6:
            divergences.append("L%d natif=%d lignes port=%d lignes" % (i, len(_nu(texte)),
                                                                       len(emis)))
    ce = []
    for nom in R21.MUTATIONS_DAMAGE:
        mordus = muets = rouges = hors_domaine = 0
        for _i, texte, obs in groupes:
            if not R21.applicable_damage(nom, obs):
                hors_domaine += 1
                continue
            sain = _emettre_damage(obs)
            try:
                mute = _emettre_damage(obs, nom)
            except (MesureImpossible, ValueError):
                mute = sain
            if mute == sain:
                muets += 1
                continue
            mordus += 1
            if _nu(mute) != _nu(texte):
                rouges += 1
        ce.append((nom, mordus, muets, rouges, hors_domaine))
    return {"groupes": len(groupes), "egales": egales, "divergences": divergences,
            "dd1": dd1, "dd2": dd2, "dd2_tues": dd2_tues, "voies": voies,
            "avec_corps": avec_corps, "contre_epreuve": ce,
            "lignes": sum(len(_nu(t)) for _i, t, _o in groupes)}


def ventilation_du_reste(couples: List[TurnObs]) -> List[dict]:
    """CE QUI RESTE HORS PERIMETRE, ET **QUI** L'Y RETIENT (#477-r34).

    ⚠ NOMMER UN BLOC PAR L'UNE DES FORMES QU'IL PORTE SURESTIME CE QUE PORTER CETTE FORME
    RAPPORTE, ET C'EST MESURE. `case-477r22` § 7.6 attribue les 47 lignes du roster 2v2 a
    `Group=Damage` ; la ventilation ci-dessous montre que **36** d'entre elles en sont, et que
    les **11** autres sont un `Group=Ability_Power` + une `Action=HealInfo` (pipeline de SOIN,
    `TagKey.Caster_Id` / `UnitStats_WasWoundedBeforeHeal` /
    `UnitStats_RemovedNegativeUnitEffects`). La regle « un sous-arbre part hors perimetre EN
    ENTIER » -- qui est juste -- fait donc que porter la famille `Damage` ne fait rien entrer de
    ce bloc-la : la forme QUI BLOQUE est ailleurs.

    Pour chaque bloc encore hors perimetre, cette fonction rend les formes ETRANGERES (celles
    qu'aucun module de `engine/streams` ne produit) et le nombre de lignes qui appartiennent a
    un `Group=Damage` -- c'est-a-dire ce que cette tranche sait deja reproduire mais que la
    partition retient."""
    out: List[dict] = []
    for c in couples:
        for h in c.hors:
            lignes = h["texte"]
            etrangeres = sorted(R21._formes(lignes) - R21._formes_portees())
            en_damage = 0
            i = 0
            while i < len(lignes):
                mg = CONF.RE_GROUP.match(lignes[i])
                if mg and mg.group("sym") == GroupType.Damage.name:
                    fin = R21._bloc(lignes, i)
                    en_damage += fin + 1 - i
                    i = fin + 1
                    continue
                i += 1
            out.append({"racine": c.racine, "lignes": h["lignes"],
                        "etrangeres": etrangeres, "lignes_damage": en_damage})
    return out


def effect_refresh_recoltes(couples: List[TurnObs]) -> dict:
    """CE QUE LA TRANCHE DEBLOQUE POUR `Effect_Refresh`, mesure -- le fil de #477-r19-r2.

    ⚠ LE « 26 » DE #477-r19-r2 COMPTE DES `Effect_Refresh`, PAS DES `Group=StartTurn`. Sa
    ventilation dit « 147 occurrences reparties sur 9 groupes racines, dont `StartTurn` 26 » : ce
    sont les `Effect_Refresh` dont la RACINE est un `StartTurn`. Les `Group=StartTurn`, eux, sont
    beaucoup moins nombreux (5 sur le meme flux). Confondre les deux surestime la recolte d'un
    facteur 5 -- et c'est exactement le genre de citation qu'on ne re-derive pas assez.

    Les deux chiffres ne disent pas la meme chose, comme au cran precedent : REPRODUITS a
    l'egalite brute donnees fournies, et AUTONOMES sans aucune entree copiee (toujours 0 --
    `#477-r21-r2` et `#477-r21-r3` restent ouverts)."""
    portes = [p for c in couples for p in c.portes]
    hors = [h for c in couples for h in c.hors]
    return R21.effect_refresh_comparables(portes, hors)


def scenario(session: int, board: str, tours: int, p_units: str, a_units: str,
             etiquette: str) -> dict:
    state = OUT / ("state-477r22-%s.json" % etiquette)
    state.parent.mkdir(parents=True, exist_ok=True)
    rid = R19.build(board, state, p_units, a_units)
    try:
        joues = 0
        for _ in range(tours):
            q = subprocess.run([sys.executable, "rl_duel.py", "aiturn",
                                "--state-file", str(state)],
                               cwd=str(HERE), capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=900)
            if q.returncode != 0:
                break
            joues += 1
        flux = (R15A.rpc(session, "replayOutputStream",
                         {"runnerId": rid, "maxChars": 8000000}).get("outputStream") or "")
    finally:
        R15A.dispose(state)
    if not flux:
        raise MesureImpossible("`replayOutputStream` rend un flux VIDE")

    # -- LA DECOUPE DU GROUPE, comme aux quatre crans precedents : la somme est confrontee.
    sequence = R19.sequence_racines(flux)
    cibles = [t for sym, t, _e in sequence if sym == GroupType.System_StartMatch.name]
    if len(cibles) != 1:
        raise MesureImpossible("%d groupe(s) `%s` -- le montage n'envoie qu'UN "
                               "`StartBattleMessage`"
                               % (len(cibles), GroupType.System_StartMatch.name))
    dec = R21.decouper_bloc1(cibles[0])

    couples = couples_du_flux(flux)
    dedans = [c for c in couples if c.racine == GroupType.System_StartMatch.name]
    dehors = [c for c in couples if c.racine != GroupType.System_StartMatch.name]
    if len(dedans) != 1:
        raise MesureImpossible("%d couple(s) `%s` dans `%s` -- la decoupe lue dans "
                               "`StartMatchOperation$$Execute` en attend exactement 1"
                               % (len(dedans), GroupType.StartTurn.name,
                                  GroupType.System_StartMatch.name))
    # LE BLOC 2 EST LA QUEUE, ET LA QUEUE EST LE COUPLE : le probe l'EXIGE plutot que de le
    # supposer -- si `StartMatchOperation` emettait quoi que ce soit apres `ContinueTurnPhase`,
    # les deux differeraient et la tranche le dirait.
    if len(dec["queue"]) != len(dedans[0].lignes):
        raise MesureImpossible("la QUEUE du groupe fait %d ligne(s), le couple %d -- le bloc 2 "
                               "n'est alors pas exactement le couple"
                               % (len(dec["queue"]), len(dedans[0].lignes)))

    resultats = []
    for etiq, lot in (("bloc2", dedans), ("hors_groupe", dehors)):
        for k, obs in enumerate(lot):
            depart = DEPART_IMBRIQUE if obs.prof == 1 else DEPART_RACINE
            attendu = natif_porte(obs)
            emis = emettre(obs, depart)
            rap = CONF.comparer(attendu, emis)
            resultats.append({"lot": etiq, "index": k, "obs": obs, "rapport": rap,
                              "depart": depart.name})

    der = derivations(couples)

    # LES CONTRE-EPREUVES SE JOUENT SUR **CHAQUE** COUPLE, PAS SUR UN SEUL -- et c'est une mesure
    # qui l'a impose. La premiere version ne mutait que le couple du bloc 2 ; sur le roster
    # crafte ce couple a un contenu VIDE, et `ordre_action` (deplacer le contenu avant l'action)
    # n'y change RIEN : elle rendait `a_morde=False`, donc un verdict sans objet. Le critere est
    # donc double, et il distingue les deux echecs : une mutation doit MORDRE sur au moins un
    # couple, et ROUGIR partout ou elle mord. L'inertie par couple est PUBLIEE, jamais tue.
    ce = []
    for nom in MUTATIONS:
        mordus, muets, rouges, hors_domaine = 0, 0, 0, 0
        for obs in couples:
            if not applicable(nom, obs):
                hors_domaine += 1
                continue
            depart = DEPART_IMBRIQUE if obs.prof == 1 else DEPART_RACINE
            sain = emettre(obs, depart)
            try:
                texte = emettre(obs, depart, mutation=nom)
            except (MesureImpossible, ValueError):
                texte = sain
            if texte == sain:
                muets += 1
                continue
            mordus += 1
            r = CONF.comparer(natif_porte(obs), texte)
            if r.nouvelles or r.connues:
                rouges += 1
        ce.append((nom, mordus, muets, rouges, hors_domaine))

    obs0 = dedans[0]
    attendu0 = natif_porte(obs0)
    sain = emettre(obs0, DEPART_IMBRIQUE)

    # le rapport de conformite du BLOC 2 lui-meme, avec ses bornes (c)
    rap_bloc2 = CONF.comparer(attendu0, sain, entrees_du_natif=(
        "les IDENTIFIANTS D'ENTITE ECS (l'entite de match, et celles des effets du contenu) et "
        "les IDENTIFIANTS DE JOUEUR (`Match_CurrentPlayerId`, `Match_PreviousPlayerId`, "
        "`Match_AmountOfTurnsStartedByCurrentPlayer`). Le port ne simule ni le `TurnComponent` "
        "ni l'allocation ECS (`#477-r16`, `#477-r21-r3`)",
        "le STAGE COURANT au moment de l'appel (`TurnComponent+0x10`). Il est LU par la RE "
        "(`Change` dans `System_StartMatch`, `End` en racine) et le probe publie combien des "
        "CINQ departs produisent le texte natif -- 3 sur 5 sont refutes, `Change` et `End` sont "
        "indiscernables par le flux",
        "la SELECTION et l'ORDRE des sous-arbres du contenu -- ce que les cinq "
        "`EvaluateAbilities(TurnStart_*)` et le `RefreshEffects` du groupe decident "
        "(`#477-r21-r2`)",
        "la DECISION de `VerifyUnitsTurnFinishedOperation$$VerifyUnitTurnEnded` -- c'est-a-dire "
        "les DEUX predicats de mobilite `HasTilesToMoveTo` (`MovementQuery$$"
        "HasAnyMovablePositionsFor`) et `HasActionAvailable` (`DamagePredictionQuery$$"
        "CanAttackAnyUnitFromTilesWithAnyAbility`), qui n'apparaissent NULLE PART dans le flux. "
        "Le probe les pose au minimum qui reproduit la decision native (`etats_unites`). Ce qui "
        "reste MESURE de cette queue est enumere en (D6)..(D8) : QUELLES unites sont candidates "
        "et DANS QUEL ORDRE (derive de la carte `Action=AddUnit` / `Tag=Unit_Owner_Id`), et la "
        "VALEUR emise (derivee du registre `UnitFlag.NoActionAvailable`)",
        "l'ETAT du bit `UnitFlag.NoActionAvailable` a l'entree du groupe, rejoue depuis le flux "
        "parce que les autres call-sites du slot `0x76` (`FinishUnitTurnOperation$$Execute`, "
        "`ActiveAbilityOperation$$ExecuteInternal`) ne sont pas portes par cette tranche",
        "les %d ligne(s) de contenu HORS PERIMETRE, mises de cote parce qu'elles portent une "
        "forme qu'aucun module de `engine/streams` ne produit. Elles sont ENUMEREES et leur "
        "total est confronte" % sum(h["lignes"] for h in obs0.hors),
    ))

    for nom, contenu in (("natif-porte", attendu0), ("port", sain),
                         ("natif-bloc2", "\n".join(dec["queue"]) + "\n")):
        with open(OUT / ("477r22-%s-%s.txt" % (etiquette, nom)), "w",
                  encoding="utf-8", newline="") as f:
            f.write(contenu)

    return {"etiquette": etiquette, "board": board, "tours": joues,
            "lignes_flux": flux.count("\n"), "decoupe": dec, "couples": couples,
            "dedans": dedans, "dehors": dehors, "resultats": resultats,
            "derivations": der, "contre_epreuve": ce, "rapport": rap_bloc2,
            "effect_refresh": effect_refresh_recoltes(couples),
            "foyer": conformite_du_foyer(flux),
            "damage": conformite_du_groupe_damage(flux),
            "reste": ventilation_du_reste(couples),
            "voc_porte": R19.vocabulaire(attendu0)}


def imprimer(res: dict) -> None:
    dec, der = res["decoupe"], res["derivations"]
    obs0 = res["dedans"][0]
    print("  flux : %d lignes, %d tour(s) d'IA joue(s)" % (res["lignes_flux"], res["tours"]))
    print("  DECOUPE : groupe %d lignes = entete 1 + `Action=%s` 1 + BLOC 1 %d + BLOC 2 %d "
          "+ Finish 1 -> somme exacte : %s"
          % (len(dec["lignes"]), StepType.StartMatch.name, len(dec["bloc1"]), len(dec["queue"]),
             "OK" if dec["somme_exacte"] else "ROUGE"))
    print("  BLOC 2 = `Action=%s` + %d tags + `Group=%s` (%d lignes) -- couple confirme"
          % (StepType.PrepareTurn.name, len(TAGS_PREPARE), GroupType.StartTurn.name,
             len(obs0.lignes) - 1 - len(TAGS_PREPARE)))
    print("  PARTITION du contenu du groupe (bloc 2) : %d sous-arbre(s) PORTE(s) = %d lignes | "
          "%d MARQUE(s) du slot 0x21 = %d lignes | %d HORS PERIMETRE = %d lignes"
          % (len(obs0.portes), sum(p["lignes"] for p in obs0.portes),
             len(obs0.marques), sum(m["lignes"] for m in obs0.marques),
             len(obs0.hors), sum(h["lignes"] for h in obs0.hors)))
    motifs: Dict[str, int] = {}
    for c in res["couples"]:
        for h in c.hors:
            motifs[h["forme"]] = motifs.get(h["forme"], 0) + 1
    for f in sorted(motifs, key=lambda c: -motifs[c]):
        print("      hors perimetre (tout le flux) : %-46s x%d" % (f, motifs[f]))
    if not motifs:
        print("      hors perimetre (tout le flux) : AUCUN -- les %d couple(s) sont INTEGRALEMENT "
              "au perimetre" % len(res["couples"]))
    print("  DERIVATIONS -- ce que le port produit SANS que le parseur le lui donne :")
    departs = der["d1_departs"]
    print("      (D1) sequence des stages : departs compatibles sur les %d couple(s) -> %s"
          % (len(departs), " | ".join(",".join(d) if d else "AUCUN" for d in departs)))
    print("      (D2) ordre des tags de `Action=%s` : %d bloc(s) ou l'ordre des ORDINAUX differe "
          "de l'alphabetique ; %d ou current != previous"
          % (StepType.PrepareTurn.name, der["d2_prepare_hors_ordre_alpha"],
             der["d2_current_different_de_previous"]))
    print("      (D3) les TROIS entites coincident sur %d / %d couple(s)"
          % (der["d3_trois_entites_egales"], len(res["couples"])))
    print("      (D4) ouverture inconditionnelle : %d `%s` SANS contenu vs %d avec"
          % (der["d4_groupes_vides"], GroupType.StartTurn.name, der["d4_groupes_pleins"]))
    print("      (D5) `Source=` et `InitialTarget=` vides : %d / %d couple(s)"
          % (sum(1 for c in res["couples"]
                 if c.source == START_TURN_SOURCE_ID and c.initial_target == ""),
             len(res["couples"])))
    print("      (D6) queue du slot 0x21 : %d marque(s) sur %d candidat(s) DERIVE(s) de "
          "`Unit_Owner_Id` ; %d marque(s) HORS des candidats (doit valoir 0)"
          % (der["d6_marques"], der["d6_candidats"], der["d6_hors_candidats"]))
    print("      (D7) valeur derivee du registre `%s` : %d / %d accord(s) ; valeurs exercees %s"
          % (FLAG.name, der["d7_accord"], der["d7_total"],
             der["d7_valeurs"] or "-"))
    if der["d7_total"] and len(der["d7_valeurs"]) < 2:
        print("          ! REGIME A UNE SEULE VALEUR (%s) : l'egalite brute ne SEPARE donc pas "
              "ici les deux branches de `VerifyUnitTurnEnded` -- seule la contre-epreuve "
              "`marque_valeur` les separe." % der["d7_valeurs"])
    print("      (D8) ordre des marques = ordre des `Action=%s` : %d / %d couple(s) marques"
          % (StepType.AddUnit.name, der["d8_couples_ordonnes"],
             der["d8_couples_avec_marques"]))
    print("      (D9) `Action=%s` entrees au perimetre : %d occurrence(s)"
          % (StepType.Info.name, der["d9_info"]))
    print("  RECOLTE -- `Group=%s` reproduits a l'EGALITE BRUTE (donnees fournies) :"
          % GroupType.StartTurn.name)
    for lot, libelle in (("bloc2", "dans `%s`" % GroupType.System_StartMatch.name),
                         ("hors_groupe", "HORS de ce groupe")):
        sous = [r for r in res["resultats"] if r["lot"] == lot]
        ok = [r for r in sous if r["rapport"].conforme]
        lignes_ok = sum(r["rapport"].lignes_natif for r in ok)
        print("      %-38s %d / %d couple(s), %d ligne(s) egales"
              % (libelle, len(ok), len(sous), lignes_ok))
        for r in sous:
            if not r["rapport"].conforme:
                print("          ROUGE couple #%d (racine=%s) : %d divergence(s)"
                      % (r["index"], r["obs"].racine, len(r["rapport"].divergences)))
    foy = res["foyer"]
    print("      FOYER `MarkUnitAsNoActionAvailableOperation$$Execute` sur TOUT le flux : "
          "%d / %d emission(s) reproduite(s) ; valeurs exercees %s"
          % (foy["egales"], foy["emissions"],
             ",".join("%d x%d" % (v, n) for v, n in foy["valeurs"].items()) or "-"))
    for d in foy["divergences"][:6]:
        print("          ROUGE %s" % d)
    eff = res["effect_refresh"]
    print("      `%s` DANS LES COUPLES : %d REPRODUIT(s) a l'egalite brute (donnees fournies), "
          "%d hors perimetre ; AUTONOMES : %d"
          % (GroupType.Effect_Refresh.name, eff["reproduits"], eff["hors_perimetre"],
             eff["autonomes"]))
    dmg = res["damage"]
    print("      FOYER `ApplyDamageOperation$$Execute` sur TOUT le flux : %d / %d `Group=%s` "
          "reproduit(s) (%d lignes) ; %d avec un corps"
          % (dmg["egales"], dmg["groupes"], GroupType.Damage.name, dmg["lignes"],
             dmg["avec_corps"]))
    for d in dmg["divergences"][:6]:
        print("          ROUGE %s" % d)
    print("          (DD1) les TROIS occurrences de l'entite (entete, action, `Tag=%s`) "
          "coincident : %d / %d" % (TagKey.Target_Id.name, dmg["dd1"], dmg["groupes"]))
    print("          (DD2) `%s` suit la PRESENCE de `%s` : %d / %d ; %d groupe(s) avec mort"
          % (TagKey.Attack_WasMemberKilled.name,
             TagKey.UnitStats_NumberOfMembers_Change.name, dmg["dd2"], dmg["groupes"],
             dmg["dd2_tues"]))
    print("          voies de source exercees : %s"
          % (", ".join("%s x%d" % (k, v) for k, v in sorted(dmg["voies"].items())) or "AUCUNE"))
    print("      CONTRE-EPREUVE `%s` (%d mutations ; sur son DOMAINE, chacune doit MORDRE puis "
          "ROUGIR) :" % (GroupType.Damage.name, len(R21.MUTATIONS_DAMAGE)))
    for nom, mordus, muets, rouges, hors_domaine in dmg["contre_epreuve"]:
        etat = ("HORS DOMAINE" if mordus + muets == 0
                else "OK" if (muets == 0 and rouges == mordus) else "ROUGE")
        print("          %-30s domaine=%-3d mord=%-3d INERTE=%-2d rougit=%d/%-3d %s"
              % (nom, mordus + muets, mordus, muets, rouges, mordus, etat))
    print("  VOCABULAIRE du natif PORTE : %d GroupType, %d StepType, %d TagKey -- %s"
          % (len(res["voc_porte"]["GroupType"]), len(res["voc_porte"]["StepType"]),
             len(res["voc_porte"]["TagKey"]), ",".join(sorted(res["voc_porte"]["StepType"]))))
    print("  CONTRE-EPREUVE (%d mutations x %d couple(s) ; sur son DOMAINE, chacune doit MORDRE "
          "puis ROUGIR) :" % (len(MUTATIONS), len(res["couples"])))
    for nom, mordus, muets, rouges, hors_domaine in res["contre_epreuve"]:
        etat = ("HORS DOMAINE" if mordus + muets == 0
                else "OK" if (muets == 0 and rouges == mordus) else "ROUGE")
        print("      %-22s domaine=%-2d mord=%-2d INERTE=%-2d rougit=%d/%-2d %s"
              % (nom, mordus + muets, mordus, muets, rouges, mordus, etat))
        if muets:
            print("          ! INERTE PAR CONSTRUCTION sur %d couple(s) de son domaine -- une "
                  "mutation qui ne change pas ce qu'elle mute ne mesure rien, quel que soit son "
                  "verdict." % muets)
        if hors_domaine:
            print("          (hors domaine sur %d couple(s) : la faute qu'elle teste n'y est pas "
                  "exprimable -- publie, jamais tu)" % hors_domaine)
    for ligne in CONF.rapport(res["rapport"]):
        print("  " + ligne)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", type=int, default=None)
    ap.add_argument("--boards", default=",".join(BOARDS_DEFAUT))
    ap.add_argument("--tours", type=int, default=2)
    ap.add_argument("--p-units", default="")
    ap.add_argument("--a-units", default="")
    ap.add_argument("--sans-roster-crafte", action="store_true")
    args = ap.parse_args()

    try:
        session = args.session if args.session is not None else R15A.session_courante()
    except MesureImpossible as e:
        print("[477-r22] MESURE IMPOSSIBLE : %s" % e)
        return 2

    plans = [(b.strip(), args.p_units, args.a_units, b.strip(), args.tours)
             for b in args.boards.split(",") if b.strip()]
    if not args.sans_roster_crafte and not args.p_units and not args.a_units:
        # LE SCENARIO CRAFTE : meme roster 2v2 qu'aux deux crans precedents, ou le contenu du
        # groupe tombe d'un facteur 3,7. Il DEPLACE le regime au lieu de rejouer le meme.
        plans.append(("MC1_67", "adeptHospitaller,astraBullgryn",
                      "blackTerminator,worldJakhal", "MC1_67-2v2", args.tours))
        # ⚠ LE SCENARIO LONG EST ENTRE AVEC `#477-r34`, ET C'EST UNE MESURE QUI L'A IMPOSE.
        # A DEUX tours, AUCUN des trois scenarios ci-dessus ne porte de `Group=Damage` DANS un
        # `Group=StartTurn` : un degat de debut de tour vient d'un effet de TUILE, qui exige
        # qu'une unite ait eu le temps de s'y poser. La famille de `#477-r34` n'y serait donc
        # jamais exercee A L'ENDROIT que cette tranche fait entrer au perimetre -- le foyer,
        # lui, l'est en nombre sur tout le flux, mais ce n'est pas la meme mesure. A SIX tours
        # sur `C1_02`, la mesure rend 1 couple porteur et 36 lignes qui entrent.
        plans.append(("C1_02", "", "", "C1_02-6t", max(6, args.tours)))
    print("[477-r22] session=%d  scenarios=%s"
          % (session, ",".join("%s(%dt)" % (p[3], p[4]) for p in plans)))

    resultats = []
    for board, pu, au, etiquette, tours in plans:
        print("")
        print("=== SCENARIO %s (board %s, %d tour(s)%s) ==="
              % (etiquette, board, tours, ", roster crafte" if pu or au else ""))
        try:
            res = scenario(session, board, tours, pu, au, etiquette)
        except MesureImpossible as e:
            print("  MESURE IMPOSSIBLE : %s" % e)
            return 2
        resultats.append(res)
        imprimer(res)

    print("")
    print("=== VERDICT (corpus = %d scenario(s)) ===" % len(resultats))
    rc = 0
    total_ok = total = 0
    for r in resultats:
        ok = [x for x in r["resultats"] if x["rapport"].conforme]
        total_ok += len(ok)
        total += len(r["resultats"])
        hors_ok = len([x for x in r["resultats"]
                       if x["lot"] == "hors_groupe" and x["rapport"].conforme])
        print("  %-12s couples=%-3d conformes=%-3d  dont HORS `%s` : %d / %d  "
              "lignes egales=%d"
              % (r["etiquette"], len(r["resultats"]), len(ok),
                 GroupType.System_StartMatch.name, hors_ok, len(r["dehors"]),
                 sum(x["rapport"].egales for x in r["resultats"])))
    nouvelles = sum(len(x["rapport"].nouvelles) for r in resultats for x in r["resultats"])
    if nouvelles:
        print("  ROUGE : %d divergence(s) NOUVELLE(s)." % nouvelles)
        rc = 1
    horsforme = sum(len(x["rapport"].hors_forme) for r in resultats for x in r["resultats"])
    if horsforme:
        print("  ROUGE : %d ligne(s) hors des 4 formes -- une forme nous manque." % horsforme)
        rc = 1
    somme_ko = [r["etiquette"] for r in resultats if not r["decoupe"]["somme_exacte"]]
    if somme_ko:
        print("  ROUGE : DECOUPE dont le total est faux sur %s -- l'amputation ne serait alors "
              "pas imputable." % ",".join(somme_ko))
        rc = 1
    sans_hors = [r["etiquette"] for r in resultats if not r["dehors"]]
    if sans_hors:
        print("  ROUGE : aucun `%s` HORS du groupe sur %s -- la RECOLTE, qui est la mesure de "
              "cette tranche, n'aurait alors rien a mesurer."
              % (GroupType.StartTurn.name, ",".join(sans_hors)))
        rc = 1
    ce_muettes = [(r["etiquette"], nom) for r in resultats
                  for nom, mordus, muets, _rouges, _hd in r["contre_epreuve"]
                  if muets > 0]
    if ce_muettes:
        print("  ROUGE : %d mutation(s) INERTES PAR CONSTRUCTION (applicables et sans effet) -- "
              "elles ne mesurent rien, quel que soit leur verdict : %s"
              % (len(ce_muettes), ", ".join("%s/%s" % (b, n) for b, n in ce_muettes)))
        rc = 1
    ce_ko = [(r["etiquette"], nom) for r in resultats
             for nom, mordus, _muets, rouges, _hd in r["contre_epreuve"]
             if mordus > 0 and rouges != mordus]
    if ce_ko:
        print("  ROUGE : %d mutation(s) ONT MORDU SANS ROUGIR -- le vert du scenario sain ne "
              "prouve alors rien : %s" % (len(ce_ko), ", ".join("%s/%s" % (b, n)
                                                                for b, n in ce_ko)))
        rc = 1
    ce_vides = [(r["etiquette"], nom) for r in resultats
                for nom, mordus, muets, _rouges, _hd in r["contre_epreuve"]
                if mordus + muets == 0]
    if ce_vides:
        print("  ATTENTION : %d mutation(s) HORS DOMAINE sur tout un scenario -- la faute "
              "qu'elles testent n'y est pas exprimable, leur silence ne dit donc rien : %s"
              % (len(ce_vides), ", ".join("%s/%s" % (b, n) for b, n in ce_vides)))
    # ⚠ HORS DOMAINE SUR **TOUS** LES SCENARIOS, C'EST UN ROUGE, PAS UNE ATTENTION -- et c'est une
    # MESURE qui l'a impose (#477-r22-r1) : les deux mutations `info_*`, ajoutees d'abord a
    # `probe_477r21`, y avaient un domaine NUL sur les QUATRE scenarios du BLOC 1 ; le garde-fou
    # homologue de ce probe-la les a refusees. Une mutation qu'AUCUN scenario n'exerce ne mesure
    # rien du tout : elle appartient au probe dont le corpus la porte, ou a personne.
    partout_vides = [nom for nom in MUTATIONS
                     if all(m + mu == 0 for r in resultats
                            for n, m, mu, _ro, _hd in r["contre_epreuve"] if n == nom)]
    if partout_vides:
        print("  ROUGE : %d mutation(s) au domaine NUL sur TOUS les scenarios -- rien ne les "
              "confronte : %s" % (len(partout_vides), ", ".join(partout_vides)))
        rc = 1
    # --- #477-r22-r1 : les TROIS recoupements de la queue, chacun ROUGE a part entiere. Ils ne
    # portent pas sur le TEXTE (que l'egalite brute couvre deja) mais sur la DERIVATION : une
    # unite marquee hors des candidats derives, une valeur qui ne suit pas le registre, ou un
    # ordre qui n'est pas celui des `Action=AddUnit` signalent que le port a eu raison PAR
    # ACCIDENT sur ce corpus.
    d6_ko = [(r["etiquette"], r["derivations"]["d6_hors_candidats"]) for r in resultats
             if r["derivations"]["d6_hors_candidats"]]
    if d6_ko:
        print("  ROUGE : %d unite(s) marquee(s) HORS des candidats derives de `Unit_Owner_Id` -- "
              "la derivation (D6) est fausse : %s"
              % (sum(n for _b, n in d6_ko), ", ".join("%s:%d" % (b, n) for b, n in d6_ko)))
        rc = 1
    d7_ko = [r["etiquette"] for r in resultats
             if r["derivations"]["d7_accord"] != r["derivations"]["d7_total"]]
    if d7_ko:
        print("  ROUGE : la VALEUR emise ne suit pas le registre `%s` sur %s -- (D7) fausse."
              % (FLAG.name, ",".join(d7_ko)))
        rc = 1
    foyer_ko = [(r["etiquette"], len(r["foyer"]["divergences"])) for r in resultats
                if r["foyer"]["divergences"]]
    if foyer_ko:
        print("  ROUGE : le foyer `MarkUnitAsNoActionAvailableOperation$$Execute` ne reproduit "
              "pas %d emission(s) du flux : %s"
              % (sum(n for _b, n in foyer_ko), ", ".join("%s:%d" % (b, n) for b, n in foyer_ko)))
        rc = 1
    # --- #477-r34 : la famille `Group=Damage`, confrontee sur TOUT le flux.
    dmg_ko = [(r["etiquette"], len(r["damage"]["divergences"])) for r in resultats
              if r["damage"]["divergences"]]
    if dmg_ko:
        print("  ROUGE : le foyer `ApplyDamageOperation$$Execute` ne reproduit pas %d "
              "`Group=%s` : %s" % (sum(n for _b, n in dmg_ko), GroupType.Damage.name,
                                   ", ".join("%s:%d" % (b, n) for b, n in dmg_ko)))
        rc = 1
    dd1_ko = [r["etiquette"] for r in resultats
              if r["damage"]["dd1"] != r["damage"]["groupes"]]
    if dd1_ko:
        print("  ROUGE : l'entete, l'action et le `Tag=%s` ne portent pas la MEME entite sur "
              "%s -- (DD1) fausse." % (TagKey.Target_Id.name, ",".join(dd1_ko)))
        rc = 1
    dd2_ko = [r["etiquette"] for r in resultats
              if r["damage"]["dd2"] != r["damage"]["groupes"]]
    if dd2_ko:
        print("  ROUGE : `%s` ne suit pas la PRESENCE de `%s` sur %s -- (DD2) fausse."
              % (TagKey.Attack_WasMemberKilled.name,
                 TagKey.UnitStats_NumberOfMembers_Change.name, ",".join(dd2_ko)))
        rc = 1
    dmg_muettes = [(r["etiquette"], nom) for r in resultats
                   for nom, _m, muets, _ro, _hd in r["damage"]["contre_epreuve"] if muets > 0]
    if dmg_muettes:
        print("  ROUGE : %d mutation(s) `damage_*` INERTES PAR CONSTRUCTION : %s"
              % (len(dmg_muettes), ", ".join("%s/%s" % (b, n) for b, n in dmg_muettes)))
        rc = 1
    dmg_ce_ko = [(r["etiquette"], nom) for r in resultats
                 for nom, mordus, _mu, rouges, _hd in r["damage"]["contre_epreuve"]
                 if mordus > 0 and rouges != mordus]
    if dmg_ce_ko:
        print("  ROUGE : %d mutation(s) `damage_*` ONT MORDU SANS ROUGIR : %s"
              % (len(dmg_ce_ko), ", ".join("%s/%s" % (b, n) for b, n in dmg_ce_ko)))
        rc = 1
    # ⚠ MEME CRAN QUE POUR LES MUTATIONS DU COUPLE : un domaine NUL sur TOUS les scenarios est
    # un ROUGE, pas une attention -- rien ne confronte alors la faute que la mutation teste.
    dmg_partout_vides = [nom for nom in R21.MUTATIONS_DAMAGE
                         if all(m + mu == 0 for r in resultats
                                for n, m, mu, _ro, _hd in r["damage"]["contre_epreuve"]
                                if n == nom)]
    if dmg_partout_vides:
        print("  ROUGE : %d mutation(s) `damage_*` au domaine NUL sur TOUS les scenarios -- "
              "rien ne les confronte : %s"
              % (len(dmg_partout_vides), ", ".join(dmg_partout_vides)))
        rc = 1
    dmg_vides = [r["etiquette"] for r in resultats if r["damage"]["groupes"] == 0]
    if dmg_vides:
        print("  ATTENTION : aucun `Group=%s` sur %s -- la famille de `#477-r34` n'y est pas "
              "exercee." % (GroupType.Damage.name, ",".join(dmg_vides)))
    voies_totales = {}
    for r in resultats:
        for k, v in r["damage"]["voies"].items():
            voies_totales[k] = voies_totales.get(k, 0) + v
    voies_mortes = [cle.name for _champ, cle in R21.SOURCE_TAGS + R21.ADDITIONAL_HIT_SOURCE_TAGS
                    if cle.name not in voies_totales]
    if voies_mortes:
        print("  ATTENTION : %d voie(s) des DEUX cascades de `GetDamageTags` qu'aucune donnee "
              "du corpus n'exerce -- le vert ne dit rien sur elles : %s"
              % (len(voies_mortes), ", ".join(voies_mortes)))
    foyer_une_valeur = [r["etiquette"] for r in resultats if len(r["foyer"]["valeurs"]) < 2]
    if foyer_une_valeur:
        print("  ATTENTION : le foyer n'exerce QU'UNE valeur sur %s -- la correspondance "
              "`reverse -> 0/1` n'y est alors pas separee." % ",".join(foyer_une_valeur))
    d8_ko = [r["etiquette"] for r in resultats
             if r["derivations"]["d8_couples_ordonnes"]
             != r["derivations"]["d8_couples_avec_marques"]]
    if d8_ko:
        print("  ROUGE : l'ordre des marques n'est pas celui des `Action=%s` sur %s -- (D8) "
              "fausse." % (StepType.AddUnit.name, ",".join(d8_ko)))
        rc = 1
    inertes = [(r["etiquette"], cle) for r in resultats for cle in
               ("d2_current_different_de_previous", "d4_groupes_pleins", "d6_marques",
                "d9_info")
               if r["derivations"][cle] == 0]
    if inertes:
        print("  ATTENTION : derivation(s) qu'AUCUNE donnee du corpus n'exerce -- le vert ne "
              "dit rien sur elles : %s" % ", ".join("%s/%s" % (b, c) for b, c in inertes))
    if rc == 0:
        print("  VERT : %d / %d couple(s) `Action=%s` + `Group=%s` reproduits a l'EGALITE "
              "BRUTE, donnees fournies."
              % (total_ok, total, StepType.PrepareTurn.name, GroupType.StartTurn.name))
        hors_total = sum(h["lignes"] for r in resultats for c in r["couples"] for h in c.hors)
        marques = sum(r["derivations"]["d6_marques"] for r in resultats)
        print("  QUEUE DU SLOT 0x21 : %d marque(s) AU PERIMETRE (%d lignes) ; contenu encore HORS "
              "PERIMETRE : %d ligne(s)." % (marques, 2 * marques, hors_total))
        dmg_total = sum(r["damage"]["groupes"] for r in resultats)
        dmg_lignes = sum(r["damage"]["lignes"] for r in resultats)
        print("  FAMILLE `Group=%s` (#477-r34) : %d groupe(s) reproduit(s) sur TOUT le flux "
              "(%d lignes), dont %d DANS un `Group=%s`."
              % (GroupType.Damage.name, dmg_total, dmg_lignes,
                 sum(1 for r in resultats for c in r["couples"] for p in c.portes
                     if _porte_un_damage(p["obs"])), GroupType.StartTurn.name))
        print("  CE QUI RESTE HORS PERIMETRE, ET QUI L'Y RETIENT :")
        for r in resultats:
            if not r["reste"]:
                print("      %-12s AUCUN -- les couple(s) sont INTEGRALEMENT au perimetre"
                      % r["etiquette"])
            for b in r["reste"]:
                print("      %-12s %3d ligne(s), dont %d de `Group=%s` (deja reproduites par le "
                      "foyer) ; BLOQUE PAR : %s"
                      % (r["etiquette"], b["lignes"], b["lignes_damage"], GroupType.Damage.name,
                         ",".join(b["etrangeres"])))
        print("  NON COUVERT : la DECISION de `VerifyUnitTurnEnded` (les deux predicats de "
              "mobilite), les gardes de `HandleNextTurn` (`#477-r22-r2`), la SELECTION des "
              "effets (`#477-r21-r2`), la DECISION qu'un coup produise un `Group=%s` (elle vit "
              "dans le pipeline de degat amont), et la famille `Group=ResurrectUnit` "
              "(`#477-r34` ne porte QUE `Group=%s`)."
              % (GroupType.Damage.name, GroupType.Damage.name))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
