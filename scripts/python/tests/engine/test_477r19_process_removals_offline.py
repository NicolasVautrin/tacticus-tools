"""#477-r19 -- GARDE offline de l'enveloppe `System_ProcessRemovals` et de son ANCRAGE.

Le probe `probe_477r19_process_removals.py` MESURE en live (il monte un runner, joue des tours
d'IA, extrait tous les groupes racines et confronte). Ce fichier GARDE : il fige ce que la
mesure a etabli, et il verifie que le controle DISCRIMINE.

CE QUE LA GARDE AJOUTE AU PROBE. Le probe a besoin d'une session Frida ; cette garde tourne
partout, a chaque passe. Elle fige quatre choses qu'aucun autre test ne tient :

  1. le groupe est VIDE -- zero `Action=`, zero `Tag=`. C'est la raison d'etre du cran : il n'a
     aucune donnee pour masquer une erreur de placement ;
  2. la garde `queue.Count < 1` -- une file vide n'emet RIEN, pas un groupe vide ;
  3. l'ancre `StartTurn` -- la forme que la premiere version de la RE avait manquee, et que le
     second board a revelee. Un test qui ne la garderait pas laisserait la regression revenir ;
  4. la DISCRIMINATION du test d'inclusion : une occurrence posee ailleurs qu'a une ancre doit
     etre refusee. Sans ce controle, « toutes les occurrences sont a une ancre » serait
     satisfait par un ensemble d'ancres trop large -- c'est-a-dire par rien.

Le fragment de reference est un EXTRAIT VERBATIM du flux natif (session Frida 10, boards C1_02
et MC1_67, seed 777, build `rnca9r7q6c`), copie caractere pour caractere : les six occurrences
mesurees sur les deux boards sont IDENTIQUES a ce fragment.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve()
PY = next(p for p in HERE.parents if p.name == "python")
if str(PY) not in sys.path:
    sys.path.insert(0, str(PY))

from engine.streams.dispatcher import StreamDispatcher
from engine.streams.group_type import GroupType
from engine.streams.step_type import StepType
from engine.streams.stream_cache import StreamCache
from engine.streams.tag_key import TagKey  # noqa: E402
from engine.streams import conformance as CONF  # noqa: E402
from engine.streams.game_setup import MATCH_ENTITY_ID  # noqa: E402
from engine.streams.input_messages import (PHASE_BARRIER_GROUPS,  # noqa: E402
                                           PROCESS_REMOVALS_SOURCE_ID,
                                           VERIFY_DEATHS_ANCHOR_GROUPS,
                                           verify_removed_units)

# --- EXTRAIT VERBATIM du flux natif : les 6 occurrences des 2 boards sont ce texte-la --------
FRAGMENT_NATIF = (
    "Group=System_ProcessRemovals Entity=1 Source= InitialTarget=\n"
    "Finish_Group\n"
)

#: La file `IdunBattle.Core.MatchState$$AddRemovedActor`. Seule sa NON-VACUITE gouverne
#: l'ouverture (`queue.Count < 1` => rien) : le contenu des ids n'est pas lu par la face stream.
FILE_NON_VIDE = (0,)


class Capture:
    def __init__(self) -> None:
        self.racines: list = []

    def on_root_group_finished(self, group: str) -> None:
        self.racines.append(group)

    def on_log(self, chunk: str) -> None:
        pass


def emettre(files, mutation: str = ""):
    """Emet un groupe par file NON VIDE. `mutation` est le levier de contre-epreuve."""
    cache = StreamCache()
    capture = Capture()
    cache.add_listener(capture)
    events = StreamDispatcher()
    events.subscribe(cache)
    for f in files:
        if mutation == "enveloppe":
            continue
        if mutation == "entite":
            events.start_group(GroupType.System_ProcessRemovals, MATCH_ENTITY_ID + 1,
                               PROCESS_REMOVALS_SOURCE_ID, None)
            events.finish_group()
        elif mutation == "source":
            events.start_group(GroupType.System_ProcessRemovals, MATCH_ENTITY_ID,
                               GroupType.System_ProcessRemovals.name, None)
            events.finish_group()
        elif mutation == "contenu":
            events.start_group(GroupType.System_ProcessRemovals, MATCH_ENTITY_ID,
                               PROCESS_REMOVALS_SOURCE_ID, None)
            events.action(StepType.RemoveUnit, 77,
                          {TagKey.Unit_IsDying: 0, TagKey.Unit_WasOverkilled: 0})
            events.finish_group()
        else:
            verify_removed_units(events, MATCH_ENTITY_ID, f)
    return "".join(capture.racines), capture.racines


# --- 1. L'egalite BRUTE, caractere par caractere ----------------------------

def test_enveloppe_egale_le_fragment_natif():
    texte, racines = emettre([FILE_NON_VIDE])
    assert texte == FRAGMENT_NATIF, (
        "premiere ligne divergente : %s"
        % next((("port=%r natif=%r" % (a, b))
                for a, b in zip(texte.split("\n"), FRAGMENT_NATIF.split("\n")) if a != b),
               "aucune -- les longueurs different"))
    assert len(racines) == 1, "un appel arme = un groupe racine flushe"


def test_le_groupe_est_VIDE():
    """La raison d'etre du cran : aucune `Action=`, aucun `Tag=`. Un groupe vide emis au mauvais
    endroit est une divergence de POSITION pure -- rien d'autre ne peut l'expliquer."""
    texte, _ = emettre([FILE_NON_VIDE])
    formes = [l.forme for l in CONF.parse_flux(texte) if l.forme != "VIDE"]
    assert formes == ["Group", "Finish_Group"], "le groupe porte autre chose : %s" % formes
    assert not [l for l in CONF.parse_flux(texte) if l.forme in ("Action", "Tag")]
    assert not [l for l in CONF.parse_flux(texte) if l.forme == "HORS_FORME"]


def test_la_garde_count_inferieur_a_1_n_emet_RIEN():
    """`if (queue.Count < 1) return;` -- lu dans le bloc inline de `VerifyDeaths`. Une file vide
    ne produit PAS un groupe vide : elle ne produit RIEN. Confondre les deux ajouterait une
    occurrence a chaque appel de `VerifyDeaths`, c'est-a-dire partout."""
    texte, racines = emettre([()])
    assert texte == ""
    assert racines == []


def test_entite_et_source_du_groupe_racine():
    """L'entite est celle du MATCH (`((IEntity)state).Id`, `1` sur nos runners), et le
    `sourceId` est `String.Empty` -- meme lecture qu'au cran 1."""
    assert PROCESS_REMOVALS_SOURCE_ID == ""
    texte, _ = emettre([FILE_NON_VIDE])
    assert texte.split("\n")[0] == ("Group=System_ProcessRemovals Entity=%d Source= "
                                    "InitialTarget=" % MATCH_ENTITY_ID)


def test_un_groupe_racine_par_appel_arme():
    texte, racines = emettre([FILE_NON_VIDE, (), FILE_NON_VIDE, FILE_NON_VIDE])
    assert len(racines) == 3, "les files vides ne produisent rien"
    assert texte == FRAGMENT_NATIF * 3


# --- 2. LA CONTRE-EPREUVE : chaque mutation doit rougir ---------------------

@pytest.mark.parametrize("mutation", ["enveloppe", "entite", "source", "contenu"])
def test_chaque_mutation_rougit(mutation):
    """Un « 0 divergence » ne vaut rien si le comparateur rendait vert quoi qu'il arrive. Le
    garde du garde est `texte != sain` : une mutation qui ne change rien ne mesure rien."""
    files = [FILE_NON_VIDE, FILE_NON_VIDE]
    sain, _ = emettre(files)
    mute, _ = emettre(files, mutation=mutation)
    assert mute != sain, "la mutation `%s` n'a PAS change le texte emis" % mutation
    rap = CONF.comparer(sain, mute)
    assert rap.divergences, "la mutation `%s` ne produit aucune divergence" % mutation


# --- 3. L'ANCRAGE : les deux formes lues, et ce qu'elles REFUSENT -----------

def _seq(*symboles):
    """Une sequence de groupes racines au format du probe : `(symbole, texte, entite)`."""
    return [(s, "", "1") for s in symboles]


def _ancres(sequence):
    import probe_477r19_process_removals as R19
    positions, _detail = R19.ancres_admissibles(sequence)
    return positions


def test_ancre_A_apres_la_phase_des_morts():
    """`RunPhase(<phase des morts>)` rend la main, puis `VerifyDeaths` enchaine sur le bloc des
    retraits. Entre les deux s'intercale ce que la phase a declenche (`ProcessDamageEvents`,
    `ProcessPendingTriggeredAbilities`) -- mesure : `Ability_Power` puis `Effect_Refresh`."""
    seq = _seq("System_ProcessDeaths", "Ability_Power", "Effect_Refresh", "User_MoveUnit")
    assert _ancres(seq) == [3], "l'ancre doit tomber APRES ce que la phase declenche"


def test_ancre_B_apres_StartTurn():
    """LA FORME QUE LA PREMIERE RE AVAIT MANQUEE. `VerifyTurnEnd` lit :
    `processor.<0x20>(...)` (qui ecrit `EndTurn` puis `StartTurn`), `ProcessPendingTriggeredAbilities`,
    puis `VerifyDeaths`. Un `System_ProcessRemovals` peut donc suivre un `StartTurn` SANS
    aucune mort en amont -- c'est exactement ce que MC1_67 a montre (3e occurrence)."""
    seq = _seq("User_UseAbility", "EndTurn", "StartTurn")
    assert _ancres(seq) == [3]
    assert GroupType.StartTurn in VERIFY_DEATHS_ANCHOR_GROUPS


def test_l_ancrage_REFUSE_une_position_quelconque():
    """La discrimination : sans elle, « toutes les occurrences sont a une ancre » serait
    satisfait par un ensemble trop large, c'est-a-dire par rien."""
    seq = _seq("System_GameSetup", "User_PlaceUnit", "User_MoveUnit", "User_UseAbility")
    assert _ancres(seq) == [], "aucune ancre : ni mort, ni debut de tour"


def test_la_barriere_arrete_l_avance():
    """Un autre message d'entree ne peut pas s'intercaler (`Apply` n'a pas rendu la main) : le
    premier `User_*` rencontre borne l'ancre."""
    seq = _seq("System_ProcessDeaths", "User_MoveUnit", "Ability_Power")
    assert _ancres(seq) == [1], "la barriere doit stopper AVANT le `User_MoveUnit`"
    sans_barriere = _seq("System_ProcessDeaths", "Ability_Power", "Effect_Refresh")
    assert _ancres(sans_barriere) == [3], "sans barriere, l'ancre court jusqu'a la fin"


def test_deux_rafales_donnent_deux_ancres_distinctes():
    seq = _seq("System_ProcessDeaths", "User_MoveUnit", "User_UseAbility",
               "System_ProcessDeaths", "EndTurn")
    assert _ancres(seq) == [1, 4]


def test_les_deux_ensembles_sont_non_vides_et_leur_intersection_est_VOULUE():
    """`StartTurn` est A LA FOIS une ancre et une barriere, et ce n'est pas une contradiction :
    l'ancre demarre APRES lui, la barriere arrete l'avance d'une ancre PRECEDENTE. Un test qui
    exigerait la disjonction ferait supprimer l'un des deux."""
    assert VERIFY_DEATHS_ANCHOR_GROUPS, "un ensemble vide rendrait le controle muet"
    assert PHASE_BARRIER_GROUPS, "un ensemble vide ferait courir toute ancre jusqu'a la fin"
    assert GroupType.StartTurn in (VERIFY_DEATHS_ANCHOR_GROUPS & PHASE_BARRIER_GROUPS)
    assert GroupType.System_ProcessDeaths not in PHASE_BARRIER_GROUPS, (
        "une rafale de morts imbriquees s'intercale LEGITIMEMENT : `VerifyDeaths` est "
        "re-entrante (`RunPhase` la rappelle apres l'action)")
    assert GroupType.System_ProcessRemovals not in PHASE_BARRIER_GROUPS


# --- 4. LES ORDINAUX, figes tels que la tranche les a MESURES ---------------

def test_ordinaux_figes_a_la_tranche():
    """`probe_313` compare le MIRROR au build : il redevient vert des qu'on regenere le mirror
    apres un renumerotage, alors que la valeur ECRITE au site, elle, a change. Ce test fige les
    ordinaux tels que la tranche les a lus au decompile et mesures dans le flux."""
    assert int(GroupType.System_ProcessRemovals) == 6    # la lambda passe `6` a `StartGroup`
    assert int(GroupType.System_ProcessDeaths) == 5      # `<VerifyDeaths>b__0` passe `5`
    assert MATCH_ENTITY_ID == 1                          # `Entity=1` des deux groupes
    # Le contenu que `RemoveUnitOperation$$Execute` emettrait si ses gardes laissaient passer.
    assert int(StepType.RemoveUnit) == 0xb
    assert int(TagKey.Unit_IsDying) == 0x88
    assert int(TagKey.Unit_WasOverkilled) == 0x89
