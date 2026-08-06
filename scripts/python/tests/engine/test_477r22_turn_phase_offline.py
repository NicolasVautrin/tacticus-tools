"""#477-r22 -- GARDE offline du BLOC 2 de `System_StartMatch` : `PrepareTurn` + `StartTurn`.

Le probe `probe_477r22_turn_phase.py` MESURE en live (il monte un runner, joue des tours d'IA,
extrait TOUS les couples du flux et les confronte). Ce fichier GARDE : il fige ce que la mesure a
etabli, et il verifie que le controle DISCRIMINE.

CE QUE LA GARDE AJOUTE AU PROBE
-------------------------------
  1. l'egalite BRUTE de ce qui est porte, sur DEUX fragments verbatim de regimes opposes -- un
     `Group=StartTurn` PLEIN (imbrique dans `System_StartMatch`, C1_02) et un VIDE (roster 2v2
     crafte, MC1_67). Le second est ce qui rend l'ouverture INCONDITIONNELLE mesurable : c'est
     exactement le regime ou `RefreshEffectsOperation$$GenerateEventGroup` n'ecrirait RIEN
     (`if (eventActions.Count > 0)`, #477-r21) alors que `StartTurnOperation$$Execute` ouvre ;
  2. la SEQUENCE DES STAGES, derivee de deux entiers : `Change -> [Prepare, Draft, Start]` et
     `End -> [Change, Prepare, Draft, Start]`. C'est la seule chose que le port CALCULE, et le
     test fige aussi ce qu'elle REFUSE (partir de `Prepare` supprime l'`Action=PrepareTurn`) ;
  3. les REFUS d'`execute_stage` : un stage hors des cinq membres, et un stage dont l'operation
     n'est pas fournie -- en particulier `TurnStage.End`, dont l'operation
     (`IdunBattle.Operations.EndTurnOperation$$Execute`) n'est PAS portee. Le port doit LEVER,
     jamais emettre un flux ampute en silence ;
  4. l'ORDINAL ECRIT AU SITE pour `TurnStage` : `probe_313` compare le MIRROR au BUILD et
     redevient vert des qu'on regenere le mirror apres un renumerotage, alors que la valeur
     ecrite au site, elle, a change. Ce test-ci fige les cinq ordinaux MESURES a la conversion ;
  5. que l'ENTITE et les JOUEURS SUIVENT leurs parametres -- un port qui ecrirait `1` en dur
     passerait toutes les comparaisons du probe, dont les runners portent l'entite de match `1`.

Les fragments sont des EXTRAITS VERBATIM du flux natif (session Frida 1, build `rnca9r7q6c`),
copies caractere pour caractere.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve()
PY = next(p for p in HERE.parents if p.name == "python")
if str(PY) not in sys.path:
    sys.path.insert(0, str(PY))

from engine.entities.turn_stage import TurnStage, next_value_or_first  # noqa: E402
from engine.streams import (GroupType, StepType, StreamCache,  # noqa: E402
                            StreamDispatcher, TagKey)
from engine.streams import conformance as CONF  # noqa: E402
from engine.streams.refresh_effects import (EffectSetup,  # noqa: E402
                                            add_activate_effect_action,
                                            add_deactivate_effect_action,
                                            add_lose_effect_action,
                                            add_receive_effect_action,
                                            generate_event_group,
                                            get_refresh_effect_tags)
from engine.streams.evaluate_trigger import evaluate_ability_trigger  # noqa: E402
from engine.streams.inform_ops import get_inform_tags, inform  # noqa: E402
from engine.entities.triggered_ability_type import TriggeredAbilityType  # noqa: E402
from engine.streams.turn_phase import (OPERATION_PAR_STAGE,  # noqa: E402
                                       STAGES_PORTES, START_TURN_SOURCE_ID,
                                       continue_turn_phase, execute_stage,
                                       get_next_turn_stage, prepare_turn, start_turn)

# --- FRAGMENT 1 : le BLOC 2 de `System_StartMatch`, C1_02, VERBATIM ET COMPLET.
# ⚠ IL L'EST DEVENU AVEC #477-r22-r1 : il etait AMPUTE de son troisieme sous-arbre
# (`Group=Ability_Power Source=StandVigil` / `Action=Info` / `Tag=Custom_Data`), la seule forme
# du bloc que #477-r22 ne portait pas. Elle est desormais emise par
# `engine/streams/inform_ops.py` (`get_inform_tags` + `inform`), et le fragment n'ampute plus rien.
FRAGMENT_PLEIN = (
    "    Action=PrepareTurn Entity=1\n"
    "        Tag=Match_CurrentPlayerId:3\n"
    "        Tag=Match_PreviousPlayerId:0\n"
    "        Tag=Match_AmountOfTurnsStartedByCurrentPlayer:1\n"
    "    Group=StartTurn Entity=1 Source= InitialTarget=\n"
    "        Action=StartTurn Entity=1\n"
    "            Tag=Match_PreviousPlayerId:0\n"
    "        Group=Effect_Refresh Entity=104 Source=MartialSuperiority_Visual InitialTarget=\n"
    "            Action=LoseEffect Entity=65\n"
    "                Tag=Effect_Id:104\n"
    "            Action=DeactivateEffect Entity=65\n"
    "                Tag=Effect_Id:104\n"
    "        Finish_Group\n"
    "        Group=Effect_Refresh Entity=81 Source=Overwatch_AutoAttack InitialTarget=\n"
    "            Action=ActivateEffect Entity=49\n"
    "                Tag=Effect_Id:81\n"
    "            Action=ReceiveEffect Entity=49\n"
    "                Tag=Effect_CurrentLevel:1\n"
    "                Tag=Effect_SourceId:49\n"
    "                Tag=Effect_SourceTriggeredAbility:1011\n"
    "                Tag=Effect_Id:81\n"
    "        Finish_Group\n"
    "        Group=Ability_Power Entity=59 Source=StandVigil InitialTarget=\n"
    "            Action=Info Entity=NO_ENTITY\n"
    "                Tag=Custom_Data:1\n"
    "        Finish_Group\n"
    "    Finish_Group\n"
)

# --- FRAGMENT 2 : le MEME bloc 2, sur le roster 2v2 crafte (MC1_67). Le groupe est VIDE de tout
# contenu, et il s'ouvre quand meme -- c'est l'inverse d'`Effect_Refresh`.
FRAGMENT_VIDE = (
    "    Action=PrepareTurn Entity=1\n"
    "        Tag=Match_CurrentPlayerId:3\n"
    "        Tag=Match_PreviousPlayerId:0\n"
    "        Tag=Match_AmountOfTurnsStartedByCurrentPlayer:1\n"
    "    Group=StartTurn Entity=1 Source= InitialTarget=\n"
    "        Action=StartTurn Entity=1\n"
    "            Tag=Match_PreviousPlayerId:0\n"
    "    Finish_Group\n"
)

# --- FRAGMENT 3 : le PREFIXE verbatim d'un couple RACINE (C1_02, 2e tour de jeu). Profondeur 0,
# et surtout `current != previous` -- ce que le bloc 2 du match, lui, n'exerce pas (3 vs 0 y sont
# distincts aussi, mais le couple racine le montre APRES un vrai changement de joueur).
PREFIXE_RACINE = (
    "Action=PrepareTurn Entity=1\n"
    "    Tag=Match_CurrentPlayerId:4\n"
    "    Tag=Match_PreviousPlayerId:3\n"
    "    Tag=Match_AmountOfTurnsStartedByCurrentPlayer:1\n"
    "Group=StartTurn Entity=1 Source= InitialTarget=\n"
    "    Action=StartTurn Entity=1\n"
    "        Tag=Match_PreviousPlayerId:3\n"
)

MATCH = 1


class Capture:
    def __init__(self) -> None:
        self.racines: list = []

    def on_root_group_finished(self, group: str) -> None:
        self.racines.append(group)

    def on_log(self, chunk: str) -> None:
        pass


def _monter(imbrique: bool):
    """Rend `(events, capture, rendre)`. `rendre()` donne le texte, enveloppe retiree."""
    cache = StreamCache()
    capture = Capture()
    cache.add_listener(capture)
    events = StreamDispatcher()
    events.subscribe(cache)
    if imbrique:
        events.start_group(GroupType.System_StartMatch, MATCH, "", None)

    def rendre() -> str:
        if imbrique:
            events.finish_group()
        lignes = [l for l in "".join(capture.racines).split("\n") if l != ""]
        if imbrique:
            lignes = lignes[1:-1]
        return "\n".join(lignes) + "\n"

    return events, capture, rendre


def _effets_du_fragment_plein(events):
    """Les DEUX `Effect_Refresh` du fragment ET son `Ability_Power`, emis par les mirrors de
    #477-r21 et, pour le dernier, par `inform_ops` (#477-r22-r1).

    Leurs donnees sont COPIEES du fragment natif (borne (c)) ; ce que ce test garde ici, c'est
    que le contenu passe bien par la couture `corps` de `start_turn`, DANS le groupe."""
    def corps() -> None:
        e104 = EffectSetup(entity_id=104, effect_type=int(_effect_type("MartialSuperiority_Visual")))
        generate_event_group(events, [
            lambda: add_lose_effect_action(events, 65, e104),
            lambda: add_deactivate_effect_action(events, 65, e104),
        ], e104)
        e81 = EffectSetup(entity_id=81, effect_type=int(_effect_type("Overwatch_AutoAttack")),
                          current_level=1, source_id=49, source_triggered_ability=1011)
        generate_event_group(events, [
            lambda: add_activate_effect_action(events, 49, e81),
            lambda: add_receive_effect_action(
                events, 49, get_refresh_effect_tags(e81, StepType.ReceiveEffect)),
        ], e81)
        # #477-r22-r1 -- le troisieme sous-arbre : `EvaluateAbilityTrigger` ouvre le
        # `Group=Ability_Power`, et le behaviour DSL de `StandVigil_UpdateEffectRangeAbility`
        # y informe une cle unique via `InformOperation$$Execute`.
        evaluate_ability_trigger(
            events, 59, int(TriggeredAbilityType.StandVigil), None,
            lambda: inform(events, get_inform_tags(int(TagKey.Custom_Data), 1)))

    return corps


def _effect_type(nom: str) -> int:
    from engine.entities.effect_type import EffectType
    return EffectType[nom]


def _operations(events, corps, prepare_args, previous):
    """Les CINQ stages... moins `End`, volontairement absent (cf. `test_execute_stage_REFUSE`)."""
    return {
        TurnStage.Change: lambda: None,
        TurnStage.Prepare: lambda: prepare_turn(events, *prepare_args),
        TurnStage.Draft: lambda: None,
        TurnStage.Start: lambda: start_turn(events, MATCH, previous, corps),
    }


# ---------------------------------------------------------------- 1. egalite BRUTE

def test_le_bloc2_PLEIN_est_reproduit_a_l_egalite_brute():
    events, _cap, rendre = _monter(imbrique=True)
    ops = _operations(events, _effets_du_fragment_plein(events), (MATCH, 3, 0, 1), 0)
    continue_turn_phase(events, TurnStage.Change, TurnStage.Start, ops)
    emis = rendre()
    assert emis == FRAGMENT_PLEIN, "\n--- natif ---\n%s\n--- port ---\n%s" % (FRAGMENT_PLEIN, emis)
    rap = CONF.comparer(FRAGMENT_PLEIN, emis)
    assert rap.conforme and rap.egales == 27, \
        "27 = les 23 lignes de #477-r22 + les 4 du `Group=Ability_Power` / `Action=Info` que " \
        "#477-r22-r1 fait entrer au perimetre"


def test_le_bloc2_VIDE_s_ouvre_quand_meme_ouverture_INCONDITIONNELLE():
    """Le regime ou `Effect_Refresh` n'ecrirait RIEN -- et ou `StartTurn` ouvre. Mesure sur le
    roster 2v2 crafte : 1 `Group=StartTurn` sans aucun contenu, et il est bien dans le flux."""
    events, _cap, rendre = _monter(imbrique=True)
    ops = _operations(events, None, (MATCH, 3, 0, 1), 0)
    continue_turn_phase(events, TurnStage.Change, TurnStage.Start, ops)
    assert rendre() == FRAGMENT_VIDE


def test_le_couple_RACINE_s_ecrit_sans_indentation():
    events, _cap, rendre = _monter(imbrique=False)
    ops = _operations(events, None, (MATCH, 4, 3, 1), 3)
    continue_turn_phase(events, TurnStage.End, TurnStage.Start, ops)
    emis = rendre()
    assert emis.startswith(PREFIXE_RACINE), \
        "\n--- prefixe natif ---\n%s\n--- port ---\n%s" % (PREFIXE_RACINE, emis)


# ---------------------------------------------------------------- 2. la SEQUENCE derivee

def test_la_sequence_des_stages_est_DERIVEE_de_deux_entiers():
    """`TurnComponent$$GetNextTurnStage` + `EnumExt$$NextValueOrFirst`, rien d'autre."""
    vus = []
    events, _cap, _rendre = _monter(imbrique=False)
    ops = {s: (lambda s=s: vus.append(s)) for s in TurnStage}
    fin = continue_turn_phase(events, TurnStage.Change, TurnStage.Start, ops)
    assert vus == [TurnStage.Prepare, TurnStage.Draft, TurnStage.Start]
    assert fin is TurnStage.Start

    vus.clear()
    fin = continue_turn_phase(events, TurnStage.End, TurnStage.Start, ops)
    assert vus == [TurnStage.Change, TurnStage.Prepare, TurnStage.Draft, TurnStage.Start]
    assert fin is TurnStage.Start

    vus.clear()
    assert continue_turn_phase(events, TurnStage.Start, TurnStage.Start, ops) is TurnStage.Start
    assert vus == [], "un stage courant DEJA egal au demande ne traverse RIEN"


def test_un_depart_de_Prepare_SUPPRIME_l_action_de_preparation():
    """La contre-epreuve `depart_prepare` du probe, figee : c'est ce qui fait de la sequence une
    DERIVATION plutot qu'une entree recopiee."""
    events, _cap, rendre = _monter(imbrique=True)
    ops = _operations(events, None, (MATCH, 3, 0, 1), 0)
    continue_turn_phase(events, TurnStage.Prepare, TurnStage.Start, ops)
    emis = rendre()
    assert StepType.PrepareTurn.name not in emis
    assert GroupType.StartTurn.name in emis
    assert emis != FRAGMENT_VIDE


def test_get_next_turn_stage_rend_None_a_l_egalite_et_cycle_sinon():
    assert get_next_turn_stage(TurnStage.Start, TurnStage.Start) is None
    assert get_next_turn_stage(TurnStage.End, TurnStage.Start) is TurnStage.Change
    assert get_next_turn_stage(TurnStage.Change, TurnStage.Start) is TurnStage.Prepare


def test_next_value_or_first_cycle_et_rend_le_PREMIER_hors_domaine():
    assert [next_value_or_first(s) for s in TurnStage] == [
        TurnStage.Prepare, TurnStage.Draft, TurnStage.Start, TurnStage.End, TurnStage.Change]
    # `Array.IndexOf` rend -1, et `(-1 + 1) % len == 0` : c'est le `OrFirst` du nom.
    assert next_value_or_first(99) is TurnStage.Change


# ---------------------------------------------------------------- 3. les REFUS

def test_execute_stage_REFUSE_un_stage_dont_l_operation_n_est_pas_fournie():
    """`TurnStage.End` en est le cas reel : `EndTurnOperation$$Execute` n'est PAS portee, et un
    port qui l'avalerait emettrait un flux ampute du `Group=EndTurn` SANS erreur."""
    events, _cap, _rendre = _monter(imbrique=False)
    ops = {TurnStage.Prepare: lambda: None, TurnStage.Start: lambda: None}
    with pytest.raises(ValueError) as exc:
        execute_stage(events, TurnStage.End, ops)
    assert "EndTurnOperation" in str(exc.value)
    assert OPERATION_PAR_STAGE[TurnStage.End] in str(exc.value)


def test_execute_stage_REFUSE_un_stage_hors_des_cinq_membres():
    events, _cap, _rendre = _monter(imbrique=False)
    with pytest.raises(ValueError):
        execute_stage(events, 7, {s: (lambda: None) for s in TurnStage})


def test_les_deux_stages_PORTES_sont_declares_et_leurs_symboles_natifs_aussi():
    assert set(STAGES_PORTES) == {TurnStage.Prepare, TurnStage.Start}
    assert OPERATION_PAR_STAGE[TurnStage.Prepare].endswith("PrepareTurnOperation$$Execute")
    assert OPERATION_PAR_STAGE[TurnStage.Start].endswith("StartTurnOperation$$Execute")
    assert set(OPERATION_PAR_STAGE) == set(TurnStage), \
        "le `switch` natif a CINQ branches nommees ; en oublier une rendrait le refus muet"


# ---------------------------------------------------------------- 4. l'ORDINAL au SITE

def test_les_cinq_ordinaux_de_TurnStage_sont_ceux_MESURES_a_la_conversion():
    """`probe_313` compare le MIRROR au BUILD et redevient vert des qu'on regenere le mirror
    apres un renumerotage. Ce test-ci fige la valeur ECRITE AU SITE -- le `3` que
    `StartMatchOperation$$Execute` passe en dur est `TurnStage.Start`, pas autre chose."""
    assert [(s.name, int(s)) for s in TurnStage] == [
        ("Change", 0), ("Prepare", 1), ("Draft", 2), ("Start", 3), ("End", 4)]


def test_les_tags_du_bloc2_sont_ceux_LUS_dans_les_Dictionary_Add():
    assert int(TagKey.Match_CurrentPlayerId) == 0x9d
    assert int(TagKey.Match_PreviousPlayerId) == 0x9e
    assert int(TagKey.Match_AmountOfTurnsStartedByCurrentPlayer) == 0x9f
    assert int(StepType.PrepareTurn) == 0x26
    assert int(StepType.StartTurn) == 2
    assert int(GroupType.StartTurn) == 0x2f
    assert int(GroupType.StartTurn) != int(GroupType.System_StartTurn), \
        "les deux se ressemblent et NE SONT PAS le meme groupe -- `System_StartTurn` est ouvert " \
        "par la lambda `<Visit>b__20_0`, `StartTurn` par `StartTurnOperation$$Execute`"


# ---------------------------------------------------------------- 5. rien n'est en dur

def test_l_entite_SUIT_le_parametre_et_n_est_pas_une_constante_recopiee():
    """Les runners portent tous l'entite de match `1` : un port qui l'ecrirait en dur passerait
    toutes les comparaisons live. Ce test le refuse."""
    events, _cap, rendre = _monter(imbrique=False)
    prepare_turn(events, 4242, 7, 9, 11)
    start_turn(events, 4243, 9)
    emis = rendre()
    assert "Action=PrepareTurn Entity=4242" in emis
    assert "Group=StartTurn Entity=4243 " in emis
    assert "Action=StartTurn Entity=4243" in emis


def test_les_trois_joueurs_SUIVENT_leurs_parametres_et_ne_sont_pas_confondus():
    events, _cap, rendre = _monter(imbrique=False)
    prepare_turn(events, MATCH, 7, 9, 11)
    lignes = [l.strip() for l in rendre().split("\n") if l.strip()]
    assert lignes == ["Action=PrepareTurn Entity=1",
                      "Tag=Match_CurrentPlayerId:7",
                      "Tag=Match_PreviousPlayerId:9",
                      "Tag=Match_AmountOfTurnsStartedByCurrentPlayer:11"], \
        "les trois valeurs sont DISTINCTES : une permutation se verrait"


def test_l_ordre_des_tags_est_celui_des_ORDINAUX_pas_de_l_alphabetique():
    """`Match_AmountOfTurnsStartedByCurrentPlayer` (159) est le PREMIER dans l'ordre alphabetique
    et le DERNIER dans celui des ordinaux -- le tri de `StreamCache$$Action` le montre."""
    events, _cap, rendre = _monter(imbrique=False)
    prepare_turn(events, MATCH, 7, 9, 11)
    noms = [l.strip().split("=")[1].split(":")[0]
            for l in rendre().split("\n") if l.strip().startswith("Tag=")]
    assert noms == [TagKey.Match_CurrentPlayerId.name,
                    TagKey.Match_PreviousPlayerId.name,
                    TagKey.Match_AmountOfTurnsStartedByCurrentPlayer.name]
    assert noms != sorted(noms), "l'ordre alphabetique donnerait un flux FAUX"


def test_le_Source_du_groupe_est_VIDE_et_l_InitialTarget_aussi():
    assert START_TURN_SOURCE_ID == ""
    events, _cap, rendre = _monter(imbrique=False)
    start_turn(events, MATCH, 0)
    assert rendre().split("\n")[0] == "Group=StartTurn Entity=1 Source= InitialTarget="


def test_l_action_du_groupe_est_la_PREMIERE_ligne_avant_tout_contenu():
    """L'ordre est LU : `Events.Action` suit immediatement le `StartGroup`, les trois appels
    delegues (slots `0x2f`, `0x4d`, `0x21`) viennent APRES elle."""
    events, _cap, rendre = _monter(imbrique=False)
    start_turn(events, MATCH, 0, lambda: events.action(StepType.Info, 0, {}))
    lignes = [l.strip() for l in rendre().split("\n") if l.strip()]
    assert lignes[0].startswith("Group=StartTurn")
    assert lignes[1] == "Action=StartTurn Entity=1"
    assert lignes[3].startswith("Action=Info")
