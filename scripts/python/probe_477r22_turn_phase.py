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

    @property
    def lignes_contenu(self) -> int:
        return sum(p["lignes"] for p in self.portes) + sum(h["lignes"] for h in self.hors)


def _entite(txt: str) -> int:
    return 0 if txt == "NO_ENTITY" else int(txt)


def _partitionner(contenu: List[str]) -> dict:
    """La partition PORTE / HORS PERIMETRE du contenu du groupe, au moyen du parseur de
    #477-r21 -- c'est exactement le meme jeu de formes, et le reutiliser est ce qui rend la
    RECOLTE reelle : un sous-arbre `Effect_Refresh` porte ici est porte par le MEME code.

    Un sous-arbre part HORS PERIMETRE EN ENTIER des qu'il porte une forme non portee ; il n'est
    jamais ampute ligne a ligne, ce qui laisserait croire que le reste est comparable."""
    portes: List[dict] = []
    hors: List[dict] = []
    i, n = 0, len(contenu)
    prof_attendue = profondeur(contenu[0]) if contenu else 0
    while i < n:
        ligne = contenu[i]
        mg = CONF.RE_GROUP.match(ligne)
        if not mg or profondeur(ligne) != prof_attendue:
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
    return {"portes": portes, "hors": hors}


def lire_couple(lignes: List[str], i_prepare: int, racine: str) -> TurnObs:
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
    par = _partitionner(contenu) if contenu else {"portes": [], "hors": []}
    obs = TurnObs(racine=racine, prof=prof, prepare=prep,
                  groupe_entity=_entite(mg.group("entity")), source=mg.group("source"),
                  initial_target=mg.group("target"),
                  action_entity=_entite(maa.group("entity")), action_tags=action_tags,
                  portes=par["portes"], hors=par["hors"],
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
    lever `lire_couple`, la ou partir des actions l'aurait simplement ignore."""
    lignes = [l for l in flux.split("\n") if l != ""]
    out: List[TurnObs] = []
    pile: List[str] = []
    for i, ligne in enumerate(lignes):
        mg = CONF.RE_GROUP.match(ligne)
        if mg:
            if mg.group("sym") == GroupType.StartTurn.name:
                racine = pile[0] if pile else GroupType.StartTurn.name
                out.append(lire_couple(lignes, i - 1 - len(TAGS_PREPARE), racine))
            pile.append(mg.group("sym"))
        elif CONF.RE_FINISH.match(ligne):
            if not pile:
                raise MesureImpossible("`Finish_Group` sans groupe ouvert, ligne %d" % i)
            pile.pop()
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
             "depart_prepare")


def _start_turn_mute(events: StreamDispatcher, obs: TurnObs, previous: int,
                     corps: Optional[Callable[[], None]], mutation: str) -> None:
    """LES CONTRE-EPREUVES STRUCTURELLES -- celles qui ne se font pas en muant une DONNEE.

    Chacune reproduit `engine/streams/turn_phase.start_turn` AVEC UNE FAUTE PRECISE, lue comme
    la faute naturelle a cet endroit. Ce n'est PAS un chemin du port : c'est la variante que le
    port aurait pu prendre, et que le decompile refute."""
    if mutation == "tag_startturn":
        # `Match_CurrentPlayerId` a la place de `Match_PreviousPlayerId` : la faute naturelle,
        # puisque `StartTurnOperation` LIT les deux (`uVar7` et `local_res20`) et n'en ecrit qu'un
        events.start_group(GroupType.StartTurn, obs.groupe_entity, START_TURN_SOURCE_ID, None)
        events.action(StepType.StartTurn, obs.action_entity,
                      {int(TagKey.Match_CurrentPlayerId): int(previous)})
        if corps is not None:
            corps()
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
        events.finish_group()
        return
    raise MesureImpossible("mutation structurelle inconnue : %s" % mutation)


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
                R21.emettre_sous_arbre(events, p["obs"])

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
            _start_turn_mute(events, obs, previous_start, corps, mutation)
            return
        start_turn(events, entite_start, previous_start, corps)

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
    """Le texte NATIF ampute des sous-arbres HORS PERIMETRE -- et de rien d'autre."""
    tete = obs.lignes[:1 + len(TAGS_PREPARE) + 1 + 1 + len(obs.action_tags)]
    corps = [l for p in obs.portes for l in p["texte"]]
    return "\n".join(tete + corps + [obs.lignes[-1]]) + "\n"


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
    d4_vides = sum(1 for c in couples if not c.portes and not c.hors)
    d4_pleins = len(couples) - d4_vides
    return {"d1_departs": [stages_de_depart_compatibles(c) for c in couples],
            "d2_prepare_hors_ordre_alpha": d2,
            "d2_current_different_de_previous": d2b,
            "d3_trois_entites_egales": d3,
            "d4_groupes_vides": d4_vides, "d4_groupes_pleins": d4_pleins}


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

    ce = []
    obs0 = dedans[0]
    attendu0 = natif_porte(obs0)
    sain = emettre(obs0, DEPART_IMBRIQUE)
    for nom in MUTATIONS:
        try:
            texte = emettre(obs0, DEPART_IMBRIQUE, mutation=nom)
        except (MesureImpossible, ValueError):
            texte = sain
        a_morde = texte != sain
        r = CONF.comparer(attendu0, texte)
        ce.append((nom, a_morde, len(r.nouvelles) + len(r.connues)))

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
          "%d HORS PERIMETRE = %d lignes"
          % (len(obs0.portes), sum(p["lignes"] for p in obs0.portes),
             len(obs0.hors), sum(h["lignes"] for h in obs0.hors)))
    motifs: Dict[str, int] = {}
    for c in res["couples"]:
        for h in c.hors:
            motifs[h["forme"]] = motifs.get(h["forme"], 0) + 1
    for f in sorted(motifs, key=lambda c: -motifs[c]):
        print("      hors perimetre (tout le flux) : %-46s x%d" % (f, motifs[f]))
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
    print("  VOCABULAIRE du natif PORTE : %d GroupType, %d StepType, %d TagKey -- %s"
          % (len(res["voc_porte"]["GroupType"]), len(res["voc_porte"]["StepType"]),
             len(res["voc_porte"]["TagKey"]), ",".join(sorted(res["voc_porte"]["StepType"]))))
    print("  CONTRE-EPREUVE (%d mutations, chacune doit MORDRE puis rougir) :" % len(MUTATIONS))
    for nom, a_morde, divs in res["contre_epreuve"]:
        print("      %-22s a_morde=%-5s divergences=%-4d %s"
              % (nom, a_morde, divs, "OK" if (a_morde and divs) else "ROUGE"))
        if not a_morde:
            print("          ! la mutation n'a PAS change ce qu'elle mute -- elle ne mesure "
                  "rien, quel que soit son verdict.")
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

    plans = [(b.strip(), args.p_units, args.a_units, b.strip())
             for b in args.boards.split(",") if b.strip()]
    if not args.sans_roster_crafte and not args.p_units and not args.a_units:
        # LE SCENARIO CRAFTE : meme roster 2v2 qu'aux deux crans precedents, ou le contenu du
        # groupe tombe d'un facteur 3,7. Il DEPLACE le regime au lieu de rejouer le meme.
        plans.append(("MC1_67", "adeptHospitaller,astraBullgryn",
                      "blackTerminator,worldJakhal", "MC1_67-2v2"))
    print("[477-r22] session=%d  scenarios=%s  tours=%d"
          % (session, ",".join(p[3] for p in plans), args.tours))

    resultats = []
    for board, pu, au, etiquette in plans:
        print("")
        print("=== SCENARIO %s (board %s%s) ==="
              % (etiquette, board, ", roster crafte" if pu or au else ""))
        try:
            res = scenario(session, board, args.tours, pu, au, etiquette)
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
    ce_ko = [(r["etiquette"], nom) for r in resultats
             for nom, a_morde, divs in r["contre_epreuve"] if not (a_morde and divs)]
    if ce_ko:
        print("  ROUGE : %d mutation(s) NE ROUGISSENT PAS -- le vert du scenario sain ne prouve "
              "alors rien : %s" % (len(ce_ko), ", ".join("%s/%s" % (b, n) for b, n in ce_ko)))
        rc = 1
    inertes = [(r["etiquette"], cle) for r in resultats for cle in
               ("d2_current_different_de_previous", "d4_groupes_pleins")
               if r["derivations"][cle] == 0]
    if inertes:
        print("  ATTENTION : derivation(s) qu'AUCUNE donnee du corpus n'exerce -- le vert ne "
              "dit rien sur elles : %s" % ", ".join("%s/%s" % (b, c) for b, c in inertes))
    if rc == 0:
        print("  VERT : %d / %d couple(s) `Action=%s` + `Group=%s` reproduits a l'EGALITE "
              "BRUTE, donnees fournies."
              % (total_ok, total, StepType.PrepareTurn.name, GroupType.StartTurn.name))
        print("  NON COUVERT : le CONTENU du groupe hors des formes de #477-r21 "
              "(`#477-r22-r1`), les gardes de `HandleNextTurn` (`#477-r22-r2`), et la SELECTION "
              "des effets (`#477-r21-r2`).")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
