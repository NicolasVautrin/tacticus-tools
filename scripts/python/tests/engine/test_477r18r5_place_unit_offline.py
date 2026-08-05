"""#477-r18-r5 -- GARDE offline de l'enveloppe `User_PlaceUnit`.

Le probe `probe_477r18r5_user_place_unit.py` MESURE en live (il monte un runner, extrait TOUS
les groupes racines `User_PlaceUnit`, compare a l'egalite brute). Ce fichier GARDE : il fige ce
que la mesure a etabli, et il verifie que la comparaison DISCRIMINE.

CE QUE LA GARDE AJOUTE AU PROBE. Le probe a besoin d'une session Frida ; cette garde tourne
partout, a chaque passe. Elle fige les trois choix du mirror qu'aucun autre test ne tient :

  1. `Entity=NO_ENTITY` sur la ligne d'ouverture -- structurel, l'entite de l'unite n'existe pas
     encore quand le groupe s'ouvre ;
  2. UN groupe racine par message -- le natif flushe a chaque retour a profondeur 0 ;
  3. le contenu est EXACTEMENT le `Group=AddUnit` du deploiement -- aucun `StepType` ni `TagKey`
     neuf, ce qui est la raison meme pour laquelle cette tranche a ete choisie en premier.

Le fragment de reference est un EXTRAIT VERBATIM du flux natif (session Frida 10, board C1_02,
seed 777, build `rnca9r7q6c`, `--p-units astraBullgryn`), copie caractere pour caractere. Il est
ECRIT ICI plutot que dans un fichier de donnees, pour la meme raison que celui de
`test_477r15_stream_emitter_offline.py` : il est specifique au build, et un lecteur doit pouvoir
le confronter d'un coup d'oeil au code qui le produit.
"""
from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import pytest

HERE = Path(__file__).resolve()
PY = next(p for p in HERE.parents if p.name == "python")
if str(PY) not in sys.path:
    sys.path.insert(0, str(PY))

from engine.entities.entity_type import EntityType  # noqa: E402
from engine.entities.spawn_source import SpawnSource  # noqa: E402
from engine.entities.triggered_ability_type import TriggeredAbilityType  # noqa: E402
from engine.streams import (BEntityId, GroupType, StepType, StreamCache,  # noqa: E402
                            StreamDispatcher, TagKey, format_enum_value)
from engine.streams import conformance as CONF  # noqa: E402
from engine.streams.game_setup import UnitSetup, add_unit  # noqa: E402
from engine.streams.input_messages import (PLACE_UNIT_SOURCE_ID,  # noqa: E402
                                           visit_add_unit_message)
from engine.streams.unit_extensions import (ActiveAbilityState,  # noqa: E402
                                            TriggeredAbilityState, UnitFullState)

# --- EXTRAIT VERBATIM du flux natif (C1_02, seed 777, entite 51 = astraBullgryn) ------------
FRAGMENT_NATIF = (
    "Group=User_PlaceUnit Entity=NO_ENTITY Source= InitialTarget=\n"
    "    Group=AddUnit Entity=51 Source= InitialTarget=\n"
    "        Action=AddUnit Entity=51\n"
    "            Tag=UnitStats_IsBoss:0\n"
    "            Tag=Unit_Owner_Id:3\n"
    "            Tag=Unit_Parent_Id:0\n"
    "            Tag=Unit_Foot_Tile_Id_1:12\n"
    "            Tag=Unit_IsSummoned:0\n"
    "            Tag=Unit_SpawnSource:5\n"
    "        Action=ChangeStats Entity=51\n"
    "            Tag=UnitStats_InitRemainingHealth:9539\n"
    "            Tag=UnitStats_InitRemainingArmor:0\n"
    "            Tag=UnitStats_InitAliveMembers:1\n"
    "            Tag=UnitStats_MaxHealth:9539\n"
    "            Tag=UnitStats_MaxArmor:0\n"
    "            Tag=UnitStats_MaxMembers:1\n"
    "            Tag=UnitStats_Range:0\n"
    "            Tag=UnitStats_Attack:3011\n"
    "            Tag=UnitStats_FixedArmor:3513\n"
    "            Tag=UnitStats_Movement:3\n"
    "            Tag=UnitStats_BlockChance:0\n"
    "            Tag=UnitStats_BlockDamage:0\n"
    "            Tag=UnitStats_CritChance:0\n"
    "            Tag=UnitStats_CritDamage:0\n"
    "            Tag=UnitStats_TurnFinished:0\n"
    "            Tag=UnitStats_IsPlayDeathAnimationOnHit:1\n"
    "        Action=ChangeAbility Entity=51\n"
    "            Tag=UnitStats_ActiveAbility_Id:1017\n"
    "            Tag=UnitStats_ActiveAbility_CanStillBeUsed:1\n"
    "            Tag=UnitStats_ActiveAbility_RemainingCooldownTurns:0\n"
    "            Tag=UnitStats_ActiveAbility_IsDisabled:0\n"
    "            Tag=UnitStats_ActiveAbility_Level:50\n"
    "            Tag=UnitStats_ActiveAbility_VariableMultiplierPercentage:180\n"
    "        Action=ChangeAbility Entity=51\n"
    "            Tag=UnitStats_ActiveAbility_Id:69\n"
    "            Tag=UnitStats_ActiveAbility_CanStillBeUsed:1\n"
    "            Tag=UnitStats_ActiveAbility_RemainingCooldownTurns:0\n"
    "            Tag=UnitStats_ActiveAbility_IsDisabled:0\n"
    "            Tag=UnitStats_ActiveAbility_Level:1\n"
    "            Tag=UnitStats_ActiveAbility_VariableMultiplierPercentage:180\n"
    "        Action=ChangeAbility Entity=51\n"
    "            Tag=UnitStats_TriggeredAbility_Id:1028\n"
    "            Tag=UnitStats_TriggeredAbility_Level:50\n"
    "            Tag=UnitStats_TriggeredAbility_VariableMultiplierPercentage:180\n"
    "        Action=ChangeAbility Entity=51\n"
    "            Tag=UnitStats_TriggeredAbility_Id:1030\n"
    "            Tag=UnitStats_TriggeredAbility_Level:50\n"
    "            Tag=UnitStats_TriggeredAbility_VariableMultiplierPercentage:180\n"
    "    Finish_Group\n"
    "Finish_Group\n"
)

#: Les seize valeurs de `ChangeStats` lues au fragment. `is_play_death_animation_on_hit:1` se
#: DEDUIT des trois booleens (`!(trait | ability1 | ability2)`), il n'est pas un champ.
ETAT_51 = UnitFullState(
    entity_type=int(EntityType.Unit),
    max_health=9539, max_armor=0, max_members=1, fixed_armor=3513,
    init_remaining_health=9539, init_remaining_armor=0, init_alive_members=1,
    attack=3011, range=0, movement=3,
    block_chance=0, block_damage=0, crit_chance=0, crit_damage=0,
    turn_finished=False, has_death_animation_trait=False,
    has_death_animation_abilities=(False, False))

UNITE_51 = UnitSetup(
    entity_id=51, owner_id=3, foot_tile_ids=[12],
    source=int(SpawnSource.Deployment),
    full_state=ETAT_51,
    active_abilities=(
        ActiveAbilityState(ability_name=1017, level=50,
                           variable_multiplier_percentage=180,
                           can_still_be_used=True, remaining_cooldown_turns=0,
                           is_disabled=False),
        ActiveAbilityState(ability_name=69, level=1,
                           variable_multiplier_percentage=180,
                           can_still_be_used=True, remaining_cooldown_turns=0,
                           is_disabled=False),
    ),
    triggered_abilities=(
        (1028, TriggeredAbilityState(level=50, variable_multiplier_percentage=180)),
        (1030, TriggeredAbilityState(level=50, variable_multiplier_percentage=180)),
    ))


class Capture:
    def __init__(self) -> None:
        self.racines: list = []

    def on_root_group_finished(self, group: str) -> None:
        self.racines.append(group)

    def on_log(self, chunk: str) -> None:
        pass


def emettre(units, mutation: str = ""):
    """Emet un `User_PlaceUnit` par unite. `mutation` est le levier de contre-epreuve."""
    cache = StreamCache()
    capture = Capture()
    cache.add_listener(capture)
    events = StreamDispatcher()
    events.subscribe(cache)
    ordonnees = list(reversed(units)) if mutation == "ordre" else list(units)
    for unit in ordonnees:
        if mutation == "spawn_source":
            unit = replace(unit, source=int(SpawnSource.InitialOperations))
        elif mutation == "tuile":
            unit = replace(unit, foot_tile_ids=[int(unit.foot_tile_ids[0]) + 1])
        elif mutation == "owner":
            unit = replace(unit, owner_id=int(unit.owner_id) + 1)
        if mutation == "enveloppe":
            add_unit(events, unit)
        elif mutation == "entite":
            events.start_group(GroupType.User_PlaceUnit, unit.entity_id,
                               PLACE_UNIT_SOURCE_ID, None)
            add_unit(events, unit)
            events.finish_group()
        else:
            visit_add_unit_message(events, unit)
    return "".join(capture.racines), capture.racines


# --- 1. L'egalite BRUTE, caractere par caractere ----------------------------

def test_enveloppe_egale_le_fragment_natif():
    texte, racines = emettre([UNITE_51])
    assert texte == FRAGMENT_NATIF, (
        "premiere ligne divergente : %s"
        % next((("port=%r natif=%r" % (a, b))
                for a, b in zip(texte.split("\n"), FRAGMENT_NATIF.split("\n")) if a != b),
               "aucune -- les longueurs different (%d vs %d lignes)"
               % (texte.count("\n"), FRAGMENT_NATIF.count("\n"))))
    assert len(racines) == 1, "un message d'entree = un groupe racine flushe"


def test_un_groupe_racine_par_message():
    """`StreamCache$$SendRootGroupIfFinished` flushe a chaque retour a profondeur 0 : N messages
    donnent N groupes racines, jamais un seul bloc."""
    unites = [UNITE_51,
              replace(UNITE_51, entity_id=53, foot_tile_ids=[19]),
              replace(UNITE_51, entity_id=55, foot_tile_ids=[26])]
    texte, racines = emettre(unites)
    assert len(racines) == 3
    assert texte == "".join(racines)
    assert texte.count("Group=User_PlaceUnit ") == 3


def test_entite_du_groupe_racine_est_no_entity():
    """Le groupe s'ouvre AVANT que l'unite existe : son entite est la sentinelle, et c'est
    `System.Enum$$ToString` qui l'ecrit en clair -- pas une branche du writer."""
    texte, _ = emettre([UNITE_51])
    assert texte.split("\n")[0] == "Group=User_PlaceUnit Entity=NO_ENTITY Source= InitialTarget="
    assert format_enum_value(BEntityId, 0) == "NO_ENTITY"
    assert format_enum_value(BEntityId, 51) == "51"


def test_source_id_est_la_chaine_vide_lue_au_decompile():
    """`<Visit>g__AddUnit|0` passe le premier champ statique de `System.String`, c'est-a-dire
    `String.Empty` -- pas un slot de litteral, et pas `null`."""
    assert PLACE_UNIT_SOURCE_ID == ""
    texte, _ = emettre([UNITE_51])
    assert " Source= InitialTarget=" in texte.split("\n")[0]


# --- 2. LA CONTRE-EPREUVE : chaque mutation doit rougir ---------------------

@pytest.mark.parametrize("mutation", ["enveloppe", "entite", "spawn_source",
                                      "ordre", "tuile", "owner"])
def test_chaque_mutation_rougit(mutation):
    """Un « 0 divergence » ne vaut rien si le comparateur rendait vert quoi qu'il arrive.

    Le garde du garde est `texte != sain` : une mutation qui ne change pas le texte emis ne
    mesure rien, quel que soit son verdict."""
    unites = [UNITE_51,
              replace(UNITE_51, entity_id=53, owner_id=3, foot_tile_ids=[19])]
    sain, _ = emettre(unites)
    mute, _ = emettre(unites, mutation=mutation)
    assert mute != sain, "la mutation `%s` n'a PAS change le texte emis" % mutation
    rap = CONF.comparer(sain, mute)
    assert rap.divergences, "la mutation `%s` ne produit aucune divergence" % mutation


# --- 3. LE VOCABULAIRE : la tranche n'ajoute AUCUN `StepType` ni `TagKey` ---

#: Ce que le groupe `System_GameSetup` exerce deja (mesure #477-r15, re-derivee ici du
#: FRAGMENT de `test_477r15_stream_emitter_offline` par le meme parseur). Ecrit en membres
#: d'enum, jamais en chaines libres : un renumerotage de build ferait bouger le nom, pas la cle.
STEPS_DU_DEPLOIEMENT = {StepType.AddPlayer, StepType.AddTile, StepType.AddMachinePlatform,
                        StepType.AddUnit, StepType.ChangeStats, StepType.ChangeAbility}
GROUPES_DU_DEPLOIEMENT = {GroupType.System_GameSetup, GroupType.AddUnit}


def test_la_tranche_n_ajoute_qu_un_group_type():
    """C'est la RAISON du choix de cette tranche (`case-477r18` § 6) : `+1 GroupType,
    +0 StepType, +0 TagKey`. Si un `StepType` ou un `TagKey` apparaissait ici, le contenu ne
    serait plus le `AddUnit` deja porte -- la tranche aurait deborde."""
    texte, _ = emettre([UNITE_51])
    groupes, steps = set(), set()
    for l in CONF.parse_flux(texte):
        if l.forme == "Group":
            groupes.add(l.symbole)
        elif l.forme == "Action":
            steps.add(l.symbole)
    assert groupes == {GroupType.User_PlaceUnit.name, GroupType.AddUnit.name}
    neufs = groupes - {g.name for g in GROUPES_DU_DEPLOIEMENT}
    assert neufs == {GroupType.User_PlaceUnit.name}, "un GroupType inattendu : %s" % neufs
    assert steps <= {s.name for s in STEPS_DU_DEPLOIEMENT}, (
        "StepType hors du deploiement : %s" % (steps - {s.name for s in STEPS_DU_DEPLOIEMENT}))


def test_les_tags_sont_ceux_du_add_unit_du_deploiement():
    """Le meme contenu emis SOUS l'enveloppe et SANS elle porte exactement les memes tags : le
    seul apport de la tranche est la paire `Group=`/`Finish_Group`."""
    avec, _ = emettre([UNITE_51])
    sans, _ = emettre([UNITE_51], mutation="enveloppe")
    tags_avec = [l.symbole for l in CONF.parse_flux(avec) if l.forme == "Tag"]
    tags_sans = [l.symbole for l in CONF.parse_flux(sans) if l.forme == "Tag"]
    assert tags_avec == tags_sans
    assert TagKey.Unit_SpawnSource.name in tags_avec
    # Et la difference se resume aux DEUX lignes d'enveloppe, plus l'indentation du reste.
    assert avec.count("\n") == sans.count("\n") + 2


def test_le_spawn_source_est_un_champ_du_message_pas_une_constante():
    """Le decompile lit `AddUnitMessage+0x28` et le passe tel quel a
    `Core.Services.OperationProcessor$$AddUnit(unitId, unitFeetTileIds, playerId, spawnSource,
    options)` : le port doit donc le RECEVOIR, jamais l'ecrire en dur. Ce test le prouve en
    montrant que la valeur emise SUIT `UnitSetup.source`."""
    for source in (SpawnSource.Deployment, SpawnSource.InitialOperations,
                   SpawnSource.Drafting):
        texte, _ = emettre([replace(UNITE_51, source=int(source))])
        assert ("Tag=%s:%d" % (TagKey.Unit_SpawnSource.name, int(source))) in texte


# --- 4. LE MIRROR D'ENUM, apparie par son ordinal MESURE --------------------

# --- 5. L'IMPUTATION AU CANAL ne doit PAS pouvoir absoudre un port faux ----
#
# Le probe live a rencontre (2026-08-05, MC1_67, 5 heros dont `ultraCalgar`) trois ecarts de
# VALEUR dus au fait que ses canaux lisent l'etat APRES le build, donc apres les auras de
# `System_StartMatch`. Il les impute au CANAL quand l'ecart EGALE EXACTEMENT la modification
# publiee ensuite. Cette regle serait un relachement dangereux si elle absolvait autre chose :
# ces tests-la sont ce qui l'en empeche.

def _rapport_et_modifs(valeur_natif, valeur_port):
    """Deux mini-flux qui ne different que par une valeur d'`UnitStats_Attack`."""
    gabarit = ("Group=User_PlaceUnit Entity=NO_ENTITY Source= InitialTarget=\n"
               "    Action=ChangeStats Entity=85\n"
               "        Tag=UnitStats_Attack:%d\n"
               "Finish_Group\n")
    return CONF.comparer(gabarit % valeur_natif, gabarit % valeur_port), (gabarit % valeur_natif)


def test_imputation_au_canal_exige_l_egalite_exacte():
    import probe_477r18r5_user_place_unit as R18R5

    rap, natif = _rapport_et_modifs(1507, 2805)
    assert len(rap.divergences) == 1
    # (a) modification EGALE a l'ecart -> imputee au canal.
    canal, restantes = R18R5.reconcilier(rap, natif, {(85, "Attack"): 1298})
    assert len(canal) == 1 and not restantes
    # (b) modification DIFFERENTE de l'ecart -> le port reste l'accuse.
    canal, restantes = R18R5.reconcilier(rap, natif, {(85, "Attack"): 1})
    assert not canal and len(restantes) == 1
    # (c) modification sur une AUTRE entite -> pas d'absolution.
    canal, restantes = R18R5.reconcilier(rap, natif, {(87, "Attack"): 1298})
    assert not canal and len(restantes) == 1
    # (d) modification sur une AUTRE stat -> pas d'absolution.
    canal, restantes = R18R5.reconcilier(rap, natif, {(85, "Movement"): 1298})
    assert not canal and len(restantes) == 1
    # (e) AUCUNE modification publiee -> pas d'absolution.
    canal, restantes = R18R5.reconcilier(rap, natif, {})
    assert not canal and len(restantes) == 1


def test_un_port_faux_de_un_n_est_pas_absous():
    """Le cas qui compte : un bug de `+1` sur une stat, dans un flux ou une aura modifie
    justement cette stat -- mais de 1298, pas de 1."""
    import probe_477r18r5_user_place_unit as R18R5

    rap, natif = _rapport_et_modifs(1507, 1508)
    canal, restantes = R18R5.reconcilier(rap, natif, {(85, "Attack"): 1298})
    assert not canal, "un ecart de 1 ne doit pas etre absous par une modification de 1298"
    assert len(restantes) == 1


def test_ordinaux_figes_a_la_tranche():
    """`probe_313` compare le MIRROR au build : il redevient vert des qu'on regenere le mirror
    apres un renumerotage, alors que la valeur ECRITE au site, elle, a change. Ce test fige les
    ordinaux tels que la tranche les a mesures dans le flux."""
    assert int(GroupType.User_PlaceUnit) == 0xd      # `<Visit>g__AddUnit|0` passe 0xd
    assert int(SpawnSource.Deployment) == 5          # `Tag=Unit_SpawnSource:5` du flux
    assert int(BEntityId.NO_ENTITY) == 0
    assert int(TriggeredAbilityType.FinalJustice) == 0x400
