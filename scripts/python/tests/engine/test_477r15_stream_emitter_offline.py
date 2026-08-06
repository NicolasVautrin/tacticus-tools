"""#477-r15 -- GARDE offline de l'emetteur de flux et de son cliquet a trois etats.

Le probe `probe_477r15a_stream_conformance.py` MESURE en live (il monte un runner, capture le
flux natif, compare). Ce fichier GARDE : il fige ce que la mesure a etabli et, surtout, il
verifie que le comparateur DISCRIMINE.

POURQUOI LA CONTRE-EPREUVE EST LA MOITIE DU TEST. Un « 0 divergence nouvelle » ne vaut RIEN sans
elle : un comparateur qui rendrait vert quoi qu'il arrive donnerait exactement le meme resultat.
Chaque mutation ci-dessous casse UN choix du writer -- tri des tags, unite d'indentation,
separateur, ordre des tuiles, formatage de l'entite -- et le test exige que CHACUNE rougisse.
C'est la meme discipline que le bras C de #477-r11 (rejouer a seed+1 pour prouver que l'egalite
mesure quelque chose).

Le fragment de reference est un EXTRAIT VERBATIM du flux natif (session Frida 8, board C1_02,
seed 777, build `rnca9r7q6c`), reduit aux formes qui nous interessent. Il est ECRIT ICI plutot
que dans un fichier de donnees : il est specifique au build, et un lecteur doit pouvoir le
confronter d'un coup d'oeil au code qui le produit.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve()
PY = next(p for p in HERE.parents if p.name == "python")
if str(PY) not in sys.path:
    sys.path.insert(0, str(PY))

from engine.entities.entity_type import EntityType  # noqa: E402
from engine.entities.traits.unit_trait import UnitTrait  # noqa: E402
from engine.entities.triggered_ability_type import TriggeredAbilityType  # noqa: E402
from engine.streams.dispatcher import StreamDispatcher
from engine.streams.entity_id import BEntityId, format_enum_value
from engine.streams.group_type import GroupType
from engine.streams.step_type import StepType
from engine.streams.stream_cache import StreamCache
from engine.streams.tag_key import TagKey  # noqa: E402
from engine.streams import conformance as CONF  # noqa: E402
from engine.streams.divergence_registry import KNOWN_DIVERGENCES  # noqa: E402
from engine.streams.game_setup import (GameSetup, PlayerSetup, TileSetup,  # noqa: E402
                                       UnitSetup, emit_game_setup)
from engine.streams.unit_extensions import (ActiveAbilityState,  # noqa: E402
                                            TriggeredAbilityState, UnitFullState,
                                            get_full_state_update_tags,
                                            get_full_state_update_tags_for_active)

# --- EXTRAIT VERBATIM du flux natif (C1_02, seed 777) -----------------------
# Les tuiles 14..46 sont omises pour la lisibilite ; ce qui reste est copie caractere pour
# caractere, `Action=ChangeStats` et les cinq `Action=ChangeAbility` COMPRIS (tranche D).
FRAGMENT_NATIF = (
    "Group=System_GameSetup Entity=1 Source= InitialTarget=\n"
    "    Action=AddPlayer Entity=3\n"
    "        Tag=Player_Id:11\n"
    "    Action=AddPlayer Entity=4\n"
    "        Tag=Player_Id:12\n"
    "    Action=AddPlayer Entity=5\n"
    "        Tag=Player_Id:13\n"
    "    Action=AddTile Entity=12\n"
    "        Tag=Tile_Column:0\n"
    "        Tag=Tile_Row:0\n"
    "        Tag=Tile_IsTerritory:0\n"
    "    Action=AddTile Entity=13\n"
    "        Tag=Tile_Column:0\n"
    "        Tag=Tile_Row:1\n"
    "        Tag=Tile_IsTerritory:0\n"
    "    Action=AddMachinePlatform Entity=47\n"
    "        Tag=MachinePosition:2\n"
    "    Action=AddMachinePlatform Entity=48\n"
    "        Tag=MachinePosition:1\n"
    "    Group=AddUnit Entity=49 Source= InitialTarget=\n"
    "        Action=AddUnit Entity=49\n"
    "            Tag=UnitStats_IsBoss:0\n"
    "            Tag=Unit_Owner_Id:4\n"
    "            Tag=Unit_Parent_Id:0\n"
    "            Tag=Unit_Foot_Tile_Id_1:46\n"
    "            Tag=Unit_IsSummoned:0\n"
    "            Tag=Unit_SpawnSource:1\n"
    "        Action=ChangeStats Entity=49\n"
    "            Tag=UnitStats_InitRemainingHealth:6525\n"
    "            Tag=UnitStats_InitRemainingArmor:0\n"
    "            Tag=UnitStats_InitAliveMembers:1\n"
    "            Tag=UnitStats_MaxHealth:6525\n"
    "            Tag=UnitStats_MaxArmor:0\n"
    "            Tag=UnitStats_MaxMembers:1\n"
    "            Tag=UnitStats_Range:0\n"
    "            Tag=UnitStats_Attack:4919\n"
    "            Tag=UnitStats_FixedArmor:1408\n"
    "            Tag=UnitStats_Movement:4\n"
    "            Tag=UnitStats_BlockChance:0\n"
    "            Tag=UnitStats_BlockDamage:0\n"
    "            Tag=UnitStats_CritChance:0\n"
    "            Tag=UnitStats_CritDamage:0\n"
    "            Tag=UnitStats_TurnFinished:0\n"
    "            Tag=UnitStats_IsPlayDeathAnimationOnHit:1\n"
    "        Action=ChangeAbility Entity=49\n"
    "            Tag=UnitStats_ActiveAbility_Id:1100\n"
    "            Tag=UnitStats_ActiveAbility_CanStillBeUsed:1\n"
    "            Tag=UnitStats_ActiveAbility_RemainingCooldownTurns:0\n"
    "            Tag=UnitStats_ActiveAbility_IsDisabled:0\n"
    "            Tag=UnitStats_ActiveAbility_Level:50\n"
    "            Tag=UnitStats_ActiveAbility_VariableMultiplierPercentage:180\n"
    "        Action=ChangeAbility Entity=49\n"
    "            Tag=UnitStats_ActiveAbility_Id:69\n"
    "            Tag=UnitStats_ActiveAbility_CanStillBeUsed:1\n"
    "            Tag=UnitStats_ActiveAbility_RemainingCooldownTurns:0\n"
    "            Tag=UnitStats_ActiveAbility_IsDisabled:0\n"
    "            Tag=UnitStats_ActiveAbility_Level:1\n"
    "            Tag=UnitStats_ActiveAbility_VariableMultiplierPercentage:180\n"
    "        Action=ChangeAbility Entity=49\n"
    "            Tag=UnitStats_TriggeredAbility_Id:1174\n"
    "            Tag=UnitStats_TriggeredAbility_Level:50\n"
    "            Tag=UnitStats_TriggeredAbility_VariableMultiplierPercentage:180\n"
    "        Action=ChangeAbility Entity=49\n"
    "            Tag=UnitStats_TriggeredAbility_Id:1180\n"
    "            Tag=UnitStats_TriggeredAbility_Level:50\n"
    "            Tag=UnitStats_TriggeredAbility_VariableMultiplierPercentage:180\n"
    "        Action=ChangeAbility Entity=49\n"
    "            Tag=UnitStats_TriggeredAbility_Id:1161\n"
    "            Tag=UnitStats_TriggeredAbility_Level:50\n"
    "            Tag=UnitStats_TriggeredAbility_VariableMultiplierPercentage:180\n"
    "    Finish_Group\n"
    "Finish_Group\n"
)

#: L'etat de `thousTzaangor` au deploiement, tel que les canaux ECS le publient (session Frida 8,
#: C1_02, seed 777). Les valeurs sont celles du FLUX ci-dessus -- c'est ce qui rend la garde
#: lisible ; ce que le probe LIVE, lui, prouve, c'est qu'elles viennent bien des canaux ECS.
ETAT_49 = UnitFullState(
    entity_type=int(EntityType.Unit),
    max_health=6525, max_armor=0, max_members=1, fixed_armor=1408,
    init_remaining_health=6525, init_remaining_armor=0, init_alive_members=1,
    attack=4919, range=0, movement=4,
    block_chance=0, block_damage=0, crit_chance=0, crit_damage=0,
    turn_finished=False, has_death_animation_trait=False,
    has_death_animation_abilities=(False, False))

ACTIVES_49 = [
    ActiveAbilityState(ability_name=1100, level=50, variable_multiplier_percentage=180,
                       can_still_be_used=True),
    ActiveAbilityState(ability_name=69, level=1, variable_multiplier_percentage=180,
                       can_still_be_used=True),
]
TRIGGERED_49 = [(1174, TriggeredAbilityState(50, 180)),
                (1180, TriggeredAbilityState(50, 180)),
                (1161, TriggeredAbilityState(50, 180))]

SETUP = GameSetup(
    players=[PlayerSetup(3, 11), PlayerSetup(4, 12), PlayerSetup(5, 13)],
    tiles=[TileSetup(12, 0, 0), TileSetup(13, 0, 1)],
    platform_entity_ids=[47, 48],
    units=[UnitSetup(entity_id=49, owner_id=4, foot_tile_ids=[46],
                     full_state=ETAT_49, active_abilities=ACTIVES_49,
                     triggered_abilities=TRIGGERED_49)],
)


class _Capture:
    def __init__(self) -> None:
        self.racines: list[str] = []

    def on_root_group_finished(self, group: str) -> None:
        self.racines.append(group)

    def on_log(self, chunk: str) -> None:
        pass


def emettre(setup: GameSetup = SETUP) -> str:
    cache = StreamCache()
    capture = _Capture()
    cache.add_listener(capture)
    events = StreamDispatcher()
    events.subscribe(cache)
    emit_game_setup(events, setup)
    assert len(capture.racines) == 1, "un seul groupe racine doit etre flushe"
    return capture.racines[0]


# --- 1. Le writer produit EXACTEMENT le texte natif -------------------------

def test_flux_emis_identique_au_natif_caractere_par_caractere():
    """La barre est l'EGALITE BRUTE (#477-r11) : ni forme canonique, ni normalisation."""
    assert emettre() == FRAGMENT_NATIF


def test_pas_de_CR_ni_de_TAB():
    """Mesure du flux natif : 0 CR, 0 TAB, LF seul. La RE offline disait « tabulations » --
    c'est FAUX, et un writer qui les reintroduirait passerait inapercu d'un diff visuel."""
    texte = emettre()
    assert "\r" not in texte
    assert "\t" not in texte
    assert texte.endswith("Finish_Group\n")


def test_flush_racine_seulement_a_profondeur_zero():
    """`StreamCache$$SendRootGroupIfFinished` : rien ne sort tant que la pile n'est pas revenue
    a zero -- c'est ce qui fait du groupe racine l'unite de comparaison."""
    cache = StreamCache()
    capture = _Capture()
    cache.add_listener(capture)
    cache.start_group(GroupType.System_GameSetup, 1)
    assert cache.depth == 1
    cache.action(StepType.AddPlayer, 3, {TagKey.Player_Id: 11})
    assert capture.racines == []          # rien flushe : la pile est encore ouverte
    cache.finish_group()
    assert cache.depth == 0
    assert len(capture.racines) == 1


def test_action_hors_de_tout_groupe():
    """Forme structurelle REELLE que la RE ne laissait pas prevoir (#477-r11 § 1) : une
    `Action=` existe a profondeur 0 et se flushe immediatement."""
    cache = StreamCache()
    capture = _Capture()
    cache.add_listener(capture)
    cache.action(StepType.PrepareTurn, 1, {TagKey.Match_CurrentPlayerId: 3})
    assert capture.racines == ["Action=PrepareTurn Entity=1\n"
                               "    Tag=Match_CurrentPlayerId:3\n"]


def test_entite_zero_s_ecrit_NO_ENTITY():
    """`Enum.ToString()` de .NET : le NOM si la valeur est un membre, le decimal sinon.
    `IdunBattle.Core.BEntityId` n'a que `0=NO_ENTITY`, d'ou les deux comportements."""
    assert format_enum_value(BEntityId, 0) == "NO_ENTITY"
    assert format_enum_value(BEntityId, 49) == "49"
    cache = StreamCache()
    capture = _Capture()
    cache.add_listener(capture)
    cache.start_group(GroupType.User_PlaceUnit, 0)
    cache.finish_group()
    assert capture.racines[0].startswith(
        "Group=User_PlaceUnit Entity=NO_ENTITY Source= InitialTarget=\n")


def test_membre_None_s_ecrit_sans_echappement():
    """Le port echappe le mot-clef Python (`None_`), le jeu ecrit `None`."""
    assert format_enum_value(GroupType, 0) == "None"
    assert format_enum_value(StepType, 0) == "None"


# --- 2. CONTRE-EPREUVE : chaque mutation doit ROUGIR ------------------------

def _mutant(**kw):
    """Un `StreamCache` dont UN choix du writer est casse."""
    cls = type("StreamCacheMutant", (StreamCache,), kw)
    cache = cls()
    capture = _Capture()
    cache.add_listener(capture)
    events = StreamDispatcher()
    events.subscribe(cache)
    emit_game_setup(events, SETUP)
    return capture.racines[0]


def _nouvelles(flux_port: str) -> int:
    """Compte les divergences NOUVELLES, apres avoir verifie que la MUTATION A MORDU.

    Un bras negatif qui passe parce que le patch ne s'est pas applique rendrait exactement le
    meme vert qu'un comparateur qui discrimine. On exige donc d'abord que le flux mute DIFFERE
    du flux de reference -- sinon le test accuse la mutation, pas le comparateur."""
    assert flux_port != FRAGMENT_NATIF, "la mutation n'a pas mordu : flux identique au natif"
    return len(CONF.comparer(FRAGMENT_NATIF, flux_port).nouvelles)


def test_contre_epreuve_le_comparateur_discrimine_le_flux_correct():
    """Bras temoin : le flux JUSTE ne rend aucune divergence. Sans lui, les bras negatifs
    ci-dessous pourraient rougir pour une raison etrangere a la mutation."""
    rap = CONF.comparer(FRAGMENT_NATIF, emettre())
    assert rap.conforme, "le flux de reference doit etre conforme"
    assert rap.egales == rap.lignes_natif


def test_contre_epreuve_indentation_par_tabulation():
    """La faute qu'aurait produite la RE offline (`case-477` § 10.7)."""
    assert _nouvelles(_mutant(INDENT="\t")) > 0


def test_contre_epreuve_indentation_deux_espaces():
    assert _nouvelles(_mutant(INDENT="  ")) > 0


def test_contre_epreuve_separateur_CRLF():
    """`Path.write_text` traduit `\\n` en `\\r\\n` sous Windows : la faute est a portee de main."""
    mute = _mutant(FMT_GROUP="Group={0} Entity={1} Source={2} InitialTarget={3}\r\n",
                   FMT_ACTION="Action={0} Entity={1}\r\n",
                   FMT_TAG="Tag={0}:{1}\r\n",
                   FINISH_GROUP="Finish_Group\r\n")
    assert _nouvelles(mute) > 0


def test_contre_epreuve_tri_alphabetique_des_tags():
    """LE piege central : `SortedDictionary<TagKey,int>` trie sur la VALEUR de l'enum. Sur le
    seul bloc `AddUnit` du fragment, l'ordre alphabetique differe de l'ordre des ordinaux."""

    class TriAlpha(StreamCache):
        def action(self, action_type, entity_id, tags):
            ordonnes = sorted(tags, key=lambda k: format_enum_value(TagKey, k))
            log = [self.INDENT * self.depth,
                   self.FMT_ACTION.format(format_enum_value(StepType, action_type),
                                          format_enum_value(BEntityId, entity_id))]
            for key in ordonnes:
                log.append(self.INDENT * (self.depth + 1))
                log.append(self.FMT_TAG.format(format_enum_value(TagKey, key),
                                               str(int(tags[key]))))
            self.commit_batched_log(log)
            self.send_root_group_if_finished()

    cache = TriAlpha()
    capture = _Capture()
    cache.add_listener(capture)
    events = StreamDispatcher()
    events.subscribe(cache)
    emit_game_setup(events, SETUP)
    assert _nouvelles(capture.racines[0]) > 0


def test_contre_epreuve_valeur_de_tag_fausse():
    """Un `Tag=` sous une action que le port EMET doit rester NOUVEAU -- la propagation de cause
    ne le couvre pas."""
    faux = GameSetup(players=SETUP.players,
                     tiles=[TileSetup(12, 0, 0), TileSetup(13, 9, 9)],
                     platform_entity_ids=SETUP.platform_entity_ids,
                     units=SETUP.units)
    assert _nouvelles(emettre(faux)) > 0


def test_contre_epreuve_ordre_des_tuiles():
    """L'ordre des tuiles vient du parcours du board dump (colonne par colonne). L'inverser
    doit se voir."""
    inverse = GameSetup(players=SETUP.players,
                        tiles=[TileSetup(12, 0, 1), TileSetup(13, 0, 0)],
                        platform_entity_ids=SETUP.platform_entity_ids,
                        units=SETUP.units)
    assert _nouvelles(emettre(inverse)) > 0


def test_contre_epreuve_positions_des_plateformes_inversees():
    """Les deux positions sont EN DUR dans le decompile (2 puis 1) : les inverser doit rougir."""
    import engine.streams.game_setup as GS
    d_origine = GS.PLATFORM_POSITIONS
    try:
        GS.PLATFORM_POSITIONS = tuple(reversed(d_origine))
        assert _nouvelles(emettre()) > 0
    finally:
        GS.PLATFORM_POSITIONS = d_origine


def test_contre_epreuve_groupe_AddUnit_desarme():
    """`BattleQuery$$get_UseGroupForAddUnit` a faux : sans groupe englobant, le flux differe.
    Ce test ne dit pas laquelle des deux formes est la bonne -- il dit qu'elles ne sont PAS
    interchangeables, donc que le drapeau compte."""
    sans = GameSetup(players=SETUP.players, tiles=SETUP.tiles,
                     platform_entity_ids=SETUP.platform_entity_ids,
                     units=SETUP.units, use_group_for_add_unit=False)
    assert _nouvelles(emettre(sans)) > 0


def _setup_avec(**kw) -> GameSetup:
    """Le SETUP de reference, avec UN attribut de son unique unite remplace."""
    from dataclasses import replace
    return GameSetup(players=SETUP.players, tiles=SETUP.tiles,
                     platform_entity_ids=SETUP.platform_entity_ids,
                     units=[replace(SETUP.units[0], **kw)])


def test_contre_epreuve_une_stat_fausse():
    """Tranche D : une seule des seize valeurs de `ChangeStats` suffit a faire rougir."""
    from dataclasses import replace
    assert _nouvelles(emettre(_setup_avec(
        full_state=replace(ETAT_49, attack=4918)))) > 0


def test_les_actives_sont_emises_AVANT_les_declenchees():
    """L'ORDRE est une PROPRIETE DU NATIF : `AddUnitOperation$$Execute` itere
    `ActiveAbilityComponent.Abilities` PUIS `TriggeredAbilityComponent.Abilities`. Les deux
    boucles ecrivent le meme `Action=ChangeAbility` sur la meme entite -- seul l'ORDRE des blocs
    les distingue, et c'est ce qu'un port pourrait intervertir sans s'en rendre compte.

    On lit l'ordre sur le TEXTE emis, puis on le PERMUTE pour verifier que le comparateur y est
    sensible : sans cette seconde moitie, l'assertion d'ordre ne prouverait pas que le cliquet
    saurait la faire respecter."""
    lignes = emettre().split("\n")
    ordre = [("active" if "ActiveAbility_Id" in lignes[i + 1] else "declenchee")
             for i, l in enumerate(lignes) if l.strip() == "Action=ChangeAbility Entity=49"]
    assert ordre == ["active", "active", "declenchee", "declenchee", "declenchee"]
    # Permutation du TEXTE : les deux blocs d'active passent apres les trois declenchees.
    blocs, courant = [], []
    for l in lignes:
        if l.strip().startswith("Action=ChangeAbility"):
            if courant:
                blocs.append(courant)
            courant = [l]
        elif courant and l.strip().startswith("Tag="):
            courant.append(l)
        elif courant:
            blocs.append(courant)
            courant = []
    permute = emettre()
    for bloc in blocs:
        permute = permute.replace("\n".join(bloc) + "\n", "")
    tete = "\n".join("\n".join(b) for b in blocs[2:] + blocs[:2]) + "\n"
    permute = permute.replace("    Finish_Group\n", tete + "    Finish_Group\n", 1)
    assert permute != FRAGMENT_NATIF, "la permutation n'a pas mordu"
    assert len(CONF.comparer(FRAGMENT_NATIF, permute).nouvelles) > 0


def test_contre_epreuve_ordre_des_actives_permute():
    """L'ordre DANS une collection compte aussi : `1100` puis `69`, pas l'inverse."""
    assert _nouvelles(emettre(_setup_avec(
        active_abilities=list(reversed(ACTIVES_49))))) > 0


def test_contre_epreuve_un_id_de_declenchee_faux():
    assert _nouvelles(emettre(_setup_avec(
        triggered_abilities=[(1174, TriggeredAbilityState(50, 180)),
                             (1181, TriggeredAbilityState(50, 180)),
                             (1161, TriggeredAbilityState(50, 180))]))) > 0


def test_full_state_absent_n_emet_aucune_ligne_ChangeStats():
    """Le SEUL degre de liberte du mirror, et il est VISIBLE : `full_state=None` signifie
    « l'appelant ne fournit pas l'etat », donc le port n'emet rien plutot que d'inventer seize
    valeurs. Le comparateur classe alors la ligne absente -- il ne la lit jamais comme egale."""
    port = emettre(_setup_avec(full_state=None,
                               active_abilities=[], triggered_abilities=[]))
    assert "Action=ChangeStats" not in port
    assert "Action=ChangeAbility" not in port
    manquantes = {d.cle for d in CONF.comparer(FRAGMENT_NATIF, port).divergences}
    assert "MANQUANT Action=ChangeStats" in manquantes
    assert "MANQUANT Action=ChangeAbility" in manquantes


# --- 2bis. Les trois surcharges de `GetFullStateUpdateTags` -----------------

def test_garde_d_entree_rend_un_dictionnaire_VIDE_hors_EntityType_Unit():
    """`GetFullStateUpdateTags(unit)` commence par `if (unit == null || unit.Type != Unit)` et
    saute a la construction d'un `Dictionary` NEUF, qu'il rend tel quel. L'appelant emet donc une
    `Action=ChangeStats` SANS AUCUN TAG -- pas « pas de ligne », une ligne vide de tags."""
    from dataclasses import replace
    for autre in (EntityType.Machine, EntityType.MachinePlatform, EntityType.Effect):
        assert get_full_state_update_tags(replace(ETAT_49, entity_type=int(autre))) == {}
    assert len(get_full_state_update_tags(ETAT_49)) == 16


def test_les_seize_tags_et_leurs_ordinaux():
    """Le CONTENU exact du dictionnaire, fige contre le decompile. Un tag ajoute ou retire par
    un futur build doit faire rougir ici, pas seulement en live."""
    tags = get_full_state_update_tags(ETAT_49)
    assert sorted(tags) == sorted([
        TagKey.UnitStats_InitRemainingHealth, TagKey.UnitStats_InitRemainingArmor,
        TagKey.UnitStats_InitAliveMembers, TagKey.UnitStats_MaxHealth,
        TagKey.UnitStats_MaxArmor, TagKey.UnitStats_MaxMembers, TagKey.UnitStats_Range,
        TagKey.UnitStats_Attack, TagKey.UnitStats_FixedArmor, TagKey.UnitStats_Movement,
        TagKey.UnitStats_BlockChance, TagKey.UnitStats_BlockDamage,
        TagKey.UnitStats_CritChance, TagKey.UnitStats_CritDamage,
        TagKey.UnitStats_TurnFinished, TagKey.UnitStats_IsPlayDeathAnimationOnHit])


def test_IsPlayDeathAnimationOnHit_est_la_NEGATION_d_un_OU_a_trois_porteurs():
    """`(HasTrait(UnitTrait.FinalJustice) | TryGetAbility(TriggeredAbilityType.FinalJustice)
    | TryGetAbility(TriggeredAbilityType.Bounce)) ^ 1`. Les trois porteurs sont testes UN A UN :
    un port qui n'en lirait qu'un rendrait le meme resultat sur l'unite de reference (qui n'en
    porte aucun) et divergerait ailleurs."""
    from dataclasses import replace
    tag = TagKey.UnitStats_IsPlayDeathAnimationOnHit
    assert get_full_state_update_tags(ETAT_49)[tag] == 1
    assert get_full_state_update_tags(
        replace(ETAT_49, has_death_animation_trait=True))[tag] == 0
    assert get_full_state_update_tags(
        replace(ETAT_49, has_death_animation_abilities=(True, False)))[tag] == 0
    assert get_full_state_update_tags(
        replace(ETAT_49, has_death_animation_abilities=(False, True)))[tag] == 0
    # Les deux enums portent un `FinalJustice` a des ordinaux DIFFERENTS : c'est le TYPE DECLARE
    # du parametre natif qui tranche, pas le nom. Si un build les alignait, ce test ne dirait
    # plus rien -- d'ou l'assertion sur leur difference.
    assert int(UnitTrait.FinalJustice) != int(TriggeredAbilityType.FinalJustice)


def test_le_cooldown_est_TOUJOURS_emis_meme_Nullable_vide():
    """`Nullable$$GetValueOrDefault` : un cooldown absent s'ecrit `0`, il ne fait pas disparaitre
    le tag. C'est l'INVERSE du couple munitions ci-dessous, et confondre les deux est facile."""
    sans = ActiveAbilityState(ability_name=69, level=1, variable_multiplier_percentage=180,
                              can_still_be_used=True, remaining_cooldown_turns=None)
    tags = get_full_state_update_tags_for_active(sans)
    assert tags[TagKey.UnitStats_ActiveAbility_RemainingCooldownTurns] == 0
    avec = get_full_state_update_tags_for_active(
        ActiveAbilityState(ability_name=69, level=1, variable_multiplier_percentage=180,
                           can_still_be_used=False, remaining_cooldown_turns=3,
                           is_disabled=True))
    assert avec[TagKey.UnitStats_ActiveAbility_RemainingCooldownTurns] == 3
    assert avec[TagKey.UnitStats_ActiveAbility_CanStillBeUsed] == 0
    assert avec[TagKey.UnitStats_ActiveAbility_IsDisabled] == 1


def test_les_deux_tags_de_munitions_sont_CONDITIONNELS_et_mal_nommes():
    """Emis UNIQUEMENT si `AmmoCost.HasValue`. Et leurs ordinaux sont ceux des tags nommes
    `UnitStats_TriggeredAbility_*` (29 et 30) alors qu'ils sont ecrits par la surcharge ACTIVE :
    un port qui « corrigerait » ce nom evident ecrirait de faux ordinaux."""
    base = dict(ability_name=1187, level=50, variable_multiplier_percentage=100,
                can_still_be_used=True)
    sans = get_full_state_update_tags_for_active(ActiveAbilityState(**base))
    assert TagKey.UnitStats_TriggeredAbility_AmmoCost not in sans
    assert TagKey.UnitStats_TriggeredAbility_EnoughAmmo not in sans
    assert len(sans) == 6
    avec = get_full_state_update_tags_for_active(
        ActiveAbilityState(ammo_cost=2, has_enough_ammo=False, **base))
    assert avec[TagKey.UnitStats_TriggeredAbility_AmmoCost] == 2
    assert avec[TagKey.UnitStats_TriggeredAbility_EnoughAmmo] == 0
    assert len(avec) == 8


# --- 2ter. #477-r15-r4/r5/r6 : les trois grandeurs qui CESSENT d'etre copiees -----
#
# Ces gardes ne verifient PAS les capteurs (qui vivent dans `frida/hooks/*` -- c'est le role de
# `probe_477r15r4_capteurs_offline.py`). Elles verifient ce dont le port a besoin pour que la
# mesure SERVE : que chaque tag est SENSIBLE a la grandeur qu'on vient de brancher. Un tag
# insensible resterait vert quel que soit le canal, et brancher un capteur ne prouverait rien.


def test_UnitStats_Range_est_SENSIBLE_a_la_valeur_recue():
    """#477-r15-r4. Le port emettait `0` EN DUR parce qu'aucun RPC ne publiait
    `StatType.Range` ; il recoit desormais `GetStat(unit, StatType.Range, StatPart.Current)`,
    dont `IdunBattle.Entities.Components.StatComponent$$GetStatPart` case 0 EST
    `get_CurrentValue` -- l'appel exact que fait la ligne du tag.

    Ce que ce test etablit : une valeur DIFFERENTE produit un flux DIFFERENT. Sans lui, le
    capteur pourrait publier n'importe quoi sans que l'egalite bouge, et le `0` mesure du corpus
    se lirait comme une confirmation alors qu'il ne serait qu'une coincidence."""
    from dataclasses import replace
    assert get_full_state_update_tags(ETAT_49)[TagKey.UnitStats_Range] == 0
    mute = get_full_state_update_tags(replace(ETAT_49, range=7))
    assert mute[TagKey.UnitStats_Range] == 7
    assert _nouvelles(emettre(_setup_avec(full_state=replace(ETAT_49, range=7)))) > 0


def test_MaxMembers_et_InitAliveMembers_sont_DEUX_tags_distincts():
    """#477-r15-r5. Les deux lisent le MEME composant par DEUX accesseurs de
    `IdunBattle.Entities.Components.FillUpStatComponent` -- `get_CurrentMaximumValue()` (case 2
    de son `GetStatPart`) et le champ BRUT `RemainingValue(+0x18)` (case 0).

    ⚠ AU DEPLOIEMENT ILS COINCIDENT (aucun membre mort), donc le flux ne les separe pas : c'est
    un regime DEGENERE, et un accord y est vide de sens. Ce que ce test etablit est ce que le
    regime ne peut pas montrer -- que le PORT, lui, les distingue, et qu'une divergence entre les
    deux se verrait immediatement. La discrimination du CANAL se mesure ailleurs
    (`probe_477r15r5_membres_discrimine.py`), et le regime du groupe `System_GameSetup` ne
    permettra JAMAIS de la mesurer sur le flux : c'est ecrit, pas contourne."""
    from dataclasses import replace
    tags = get_full_state_update_tags(ETAT_49)
    assert tags[TagKey.UnitStats_MaxMembers] == tags[TagKey.UnitStats_InitAliveMembers] == 1
    assert int(TagKey.UnitStats_MaxMembers) != int(TagKey.UnitStats_InitAliveMembers)
    # Un membre mort : le maximum ne bouge pas, le restant si.
    use = get_full_state_update_tags(replace(ETAT_49, max_members=5, init_alive_members=4))
    assert use[TagKey.UnitStats_MaxMembers] == 5
    assert use[TagKey.UnitStats_InitAliveMembers] == 4
    assert _nouvelles(emettre(_setup_avec(
        full_state=replace(ETAT_49, max_members=5, init_alive_members=4)))) > 0


def test_MaxHealth_MaxArmor_et_leurs_bruts_sont_QUATRE_tags_distincts():
    """#477-r15-r7. Meme forme que le test des membres ci-dessus, sur les DEUX autres
    `IdunBattle.Entities.Components.FillUpStatComponent` de l'unite. Chaque composant est lu par
    DEUX accesseurs differents, et le natif en fait DEUX tags :

        Tag=UnitStats_MaxHealth          (9)  <- `get_CurrentMaximumValue()`   (case 2)
        Tag=UnitStats_InitRemainingHealth (2) <- champ BRUT `RemainingValue(+0x18)` (case 0)
        Tag=UnitStats_MaxArmor          (13)  <- `get_CurrentMaximumValue()`   (case 2)
        Tag=UnitStats_InitRemainingArmor (3)  <- champ BRUT `RemainingValue(+0x18)` (case 0)

    ⚠ AU DEPLOIEMENT ILS COINCIDENT (rien n'a ete perdu ni modifie), donc le flux ne les separe
    pas -- regime DEGENERE, accord vide de sens. Ce test etablit ce que le regime ne peut pas
    montrer : que le PORT, lui, les distingue. La discrimination des CANAUX se mesure ailleurs
    (`probe_477r15r7_max_discrimine.py`).

    ⚠ ET IL Y A UN SECOND DEGENERESCENCE, PROPRE A L'ARMURE : sur `thousTzaangor` elle vaut ZERO
    des deux cotes. Deux zeros sont egaux quelle que soit la lecture. Le test l'ASSERTE au lieu de
    le subir -- si un futur corpus portait une armure non nulle, cette ligne tomberait et
    signalerait que le regime a change."""
    from dataclasses import replace
    tags = get_full_state_update_tags(ETAT_49)
    assert tags[TagKey.UnitStats_MaxHealth] == tags[TagKey.UnitStats_InitRemainingHealth] == 6525
    assert tags[TagKey.UnitStats_MaxArmor] == tags[TagKey.UnitStats_InitRemainingArmor] == 0
    assert ETAT_49.max_armor == 0, ("l'armure du corpus de reference est NULLE : l'egalite du "
                                    "flux sur `UnitStats_MaxArmor` compare deux zeros")
    ordinaux = {int(TagKey.UnitStats_MaxHealth), int(TagKey.UnitStats_InitRemainingHealth),
                int(TagKey.UnitStats_MaxArmor), int(TagKey.UnitStats_InitRemainingArmor)}
    assert len(ordinaux) == 4, "les quatre tags doivent etre quatre ordinaux distincts"
    # Un maximum modifie (ce que fait `TwistedScience` sur la sante) : le restant ne bouge pas.
    use = get_full_state_update_tags(replace(ETAT_49, max_health=8708, max_armor=350))
    assert use[TagKey.UnitStats_MaxHealth] == 8708
    assert use[TagKey.UnitStats_InitRemainingHealth] == 6525
    assert use[TagKey.UnitStats_MaxArmor] == 350
    assert use[TagKey.UnitStats_InitRemainingArmor] == 0


@pytest.mark.parametrize("champ,valeur", [("max_health", 8708), ("max_armor", 350)])
def test_chaque_maximum_est_SENSIBLE_a_la_valeur_recue(champ: str, valeur: int):
    """#477-r15-r7, contre-epreuve. Chacun des deux maximums doit faire rougir INDIVIDUELLEMENT.

    Sans ce bras, brancher les capteurs n'aurait rien prouve : un tag insensible resterait vert
    avec ou sans mesure, et l'egalite du corpus se lirait comme une confirmation."""
    from dataclasses import replace
    assert _nouvelles(emettre(_setup_avec(
        full_state=replace(ETAT_49, **{champ: valeur})))) > 0


def test_l_etat_NEUF_d_une_active_est_celui_qu_ecrit_le_ctor_natif():
    """#477-r15-r6. Les trois tags d'etat de l'entree d'ATTAQUE NORMALE etaient poses aux
    defauts du port, faute de canal (`ActiveAbilityComponent$$GetActives` la filtre, donc
    `decisionView` ne la publie pas). Ils sont desormais LUS sur l'instance
    (`unitAbilityStates.actives[].state`).

    Ce test fige POURQUOI ces defauts etaient justes, lu dans
    `IdunBattle.Entities.Components.ActiveAbility$$.ctor` :

        this.<CanStillBeUsed +0x28> = 1
        this.<RemainingCooldownTurns +0x2c> = Nullable<int>()     // vide -> GetValueOrDefault = 0
        this.<HasEnoughAmmo +0x40> = 1
        // IsDisabled (+0x35) et AmmoCost (+0x38) ne sont PAS ecrits -> zero de l'allocation

    Le port ne se trompait donc pas -- il ne MESURAIT pas. Si un futur build changeait ce ctor,
    ce test tomberait ICI plutot qu'en live, et il nomme la fonction a relire."""
    neuve = ActiveAbilityState(ability_name=69, level=1, variable_multiplier_percentage=180,
                               can_still_be_used=True)
    tags = get_full_state_update_tags_for_active(neuve)
    assert tags[TagKey.UnitStats_ActiveAbility_CanStillBeUsed] == 1
    assert tags[TagKey.UnitStats_ActiveAbility_RemainingCooldownTurns] == 0
    assert tags[TagKey.UnitStats_ActiveAbility_IsDisabled] == 0
    # ... et les deux tags de munitions ne sont PAS emis (AmmoCost non ecrit par le ctor).
    assert TagKey.UnitStats_TriggeredAbility_AmmoCost not in tags
    # C'est exactement ce que porte l'entree `Id:69` du fragment natif.
    assert "Tag=UnitStats_ActiveAbility_Id:69\n" in FRAGMENT_NATIF
    assert neuve.has_enough_ammo is True


@pytest.mark.parametrize("champ,valeur", [
    ("can_still_be_used", False),
    ("remaining_cooldown_turns", 3),
    ("is_disabled", True),
])
def test_chaque_tag_d_etat_de_l_attaque_normale_est_SENSIBLE(champ: str, valeur):
    """#477-r15-r6, contre-epreuve. Les trois tags doivent faire rougir INDIVIDUELLEMENT sur
    l'entree d'attaque normale (`Id:69`, la SECONDE active). Sans ce bras, brancher le capteur
    n'aurait rien prouve : un tag insensible resterait vert avec ou sans mesure."""
    from dataclasses import replace
    actives = [ACTIVES_49[0], replace(ACTIVES_49[1], **{champ: valeur})]
    assert _nouvelles(emettre(_setup_avec(active_abilities=actives))) > 0


# --- 3. Le cliquet lui-meme -------------------------------------------------

def test_ligne_hors_des_quatre_formes_est_signalee():
    """Une forme inconnue ne doit pas etre ignoree en silence -- c'est ainsi qu'on apprend
    qu'une forme nous manque."""
    rap = CONF.comparer(FRAGMENT_NATIF + "Quelque chose d'autre\n", emettre())
    assert rap.hors_forme, "une ligne hors des 4 formes doit etre signalee"


def test_propagation_de_cause_bornee_a_un_cran():
    """Un `Tag=` herite de son PORTEUR seulement si ce porteur est inscrit au registre. Sous une
    action que le port emet, il reste NOUVEAU."""
    natif = ("Action=AddPlayer Entity=3\n"
             "    Tag=Player_Id:11\n"
             "    Tag=Match_CurrentPlayerId:3\n")
    port = ("Action=AddPlayer Entity=3\n"
            "    Tag=Player_Id:11\n")
    rap = CONF.comparer(natif, port)
    assert len(rap.nouvelles) == 1
    assert rap.nouvelles[0].cle == "MANQUANT Tag=Match_CurrentPlayerId"


def test_le_registre_est_VIDE_et_c_est_une_mesure(monkeypatch):
    """Les deux seules entrees qu'il portait (`MANQUANT Action=ChangeStats` et
    `MANQUANT Action=ChangeAbility`, 43 lignes du deploiement) ont ete FERMEES par la tranche D.
    Les laisser les aurait fait rougir comme PERIMEES -- c'est ce que la purge existe pour
    obtenir, et la reponse correcte est de SUPPRIMER, jamais d'elargir.

    ⚠ Un registre vide ne dit RIEN sur ce qui n'est pas compare : cela vit dans les trois bornes
    de `conformance.rapport`, verifiees par `test_le_rapport_publie_les_trois_bornes`."""
    assert KNOWN_DIVERGENCES == {}


def test_purge_une_entree_non_exercee_est_perimee(monkeypatch):
    """LA purge, verifiee sur un registre INJECTE -- pas sur le registre reel, qui est vide.

    Un test qui dependrait du contenu du registre cesserait de mordre au moment exact ou il
    devient utile : c'est la degradation en silence d'une garde par seuil."""
    factice = {"MANQUANT Action=ChangeStats": "cause factice",
               "MANQUANT Action=ChangeAbility": "cause factice"}
    monkeypatch.setattr(CONF, "KNOWN_DIVERGENCES", factice)
    perimees = CONF.entrees_perimees({"MANQUANT Action=ChangeStats"})
    assert perimees == ["MANQUANT Action=ChangeAbility"]
    # ... et un corpus qui exerce TOUT le registre ne rend aucune entree perimee.
    assert CONF.entrees_perimees(set(factice)) == []
    # Registre vide => rien ne peut etre perime, quel que soit le corpus.
    monkeypatch.setattr(CONF, "KNOWN_DIVERGENCES", {})
    assert CONF.entrees_perimees(set()) == []
    assert CONF.entrees_perimees({"MANQUANT Action=AddUnit"}) == []


def test_le_perimetre_se_derive_des_enums_pas_de_l_observe():
    """Les trois totaux viennent des mirrors, jamais du corpus : un comparateur calibre sur
    l'observe serait muet sur le reste sans le dire (`#477-r13`)."""
    rap = CONF.comparer(FRAGMENT_NATIF, emettre())
    assert rap.non_exerces["GroupType"]["total"] == len(GroupType)
    assert rap.non_exerces["StepType"]["total"] == len(StepType)
    assert rap.non_exerces["TagKey"]["total"] == len(TagKey)
    # Le fragment n'exerce qu'une petite part : c'est PUBLIE, pas masque.
    assert rap.non_exerces["TagKey"]["exerces"] < len(TagKey)


def test_le_rapport_publie_les_trois_bornes():
    """NON COMPARE != EGAL : le rapport doit NOMMER ce qu'il ne compare pas."""
    rap = CONF.comparer(FRAGMENT_NATIF, emettre(),
                        entrees_du_natif=("id d'entite des joueurs",))
    texte = "\n".join(CONF.rapport(rap))
    assert "NON COMPARE" in texte
    assert "perimetre DERIVE des enums" in texte
    for nom in CONF.OMISSIONS_STRUCTURELLES:
        assert nom in texte, "l'omission %s doit etre nommee" % nom
    assert "id d'entite des joueurs" in texte


def _cle_bien_formee(cle: str) -> bool:
    """Une cle de registre est `<FORME> <Genre>=<Membre>` (ou `<FORME> Finish_Group`), le membre
    devant appartenir a l'enum du genre. Une cle mal formee ne serait JAMAIS appariee --
    l'entree deviendrait un commentaire inerte que la purge ne saurait meme pas signaler."""
    forme, _, symbole = cle.partition(" ")
    if forme not in (CONF.MANQUANT, CONF.EN_TROP, CONF.VALEUR) or not symbole:
        return False
    if symbole == "Finish_Group":
        return True
    genre, _, membre = symbole.partition("=")
    table = {"Group": GroupType, "Action": StepType, "Tag": TagKey}.get(genre)
    if table is None:
        return False
    return membre in {m.name[:-1] if m.name == "None_" else m.name for m in table}


@pytest.mark.parametrize("cle,attendu", [
    ("MANQUANT Action=ChangeStats", True),
    ("EN_TROP Group=AddUnit", True),
    ("VALEUR Tag=UnitStats_Attack", True),
    ("MANQUANT Finish_Group", True),
    ("MANQUANT Action=ChangeStat", False),      # membre inexistant (faute de frappe)
    ("ABSENT Action=ChangeStats", False),       # forme inconnue
    ("MANQUANT Etape=ChangeStats", False),      # genre inconnu
    ("MANQUANT", False),                        # pas de symbole
])
def test_le_critere_de_bonne_formation_discrimine(cle: str, attendu: bool):
    """Le critere lui-meme, teste sur des cas VALIDES et INVALIDES. Il est verifie ici plutot que
    par un `parametrize` sur le registre : celui-ci est VIDE, et un parametrize vide ne teste
    rien tout en restant vert."""
    assert _cle_bien_formee(cle) is attendu


def test_chaque_cle_du_registre_est_bien_formee():
    """Applique le critere ci-dessus aux entrees REELLES -- vacuement vrai tant que le registre
    est vide, mordant des qu'une entree y revient."""
    mauvaises = [c for c in KNOWN_DIVERGENCES if not _cle_bien_formee(c)]
    assert mauvaises == []
