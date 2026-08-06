"""#477-r21-r1 -- GARDE offline des formes `ChangeStats` / `ChangeAbility` du bloc 1.

`probe_477r21_activation_tree.py` MESURE en live ; ce fichier FIGE ce que la mesure a etabli et
verifie que le controle DISCRIMINE. Il porte sur les TROIS operations natives que la tranche a
lues -- `TransformUnitOperation`, `RemoveActiveAbilityOperation`, `AddActiveAbilityOperation` --
et sur rien d'autre.

CE QUE LA GARDE FIGE, en l'OPPOSANT a son contraire :

  1. l'egalite BRUTE des trois motifs, extraits VERBATIM du flux natif ;
  2. les ORDINAUX DE LA TABLE `StatType -> ModStatTransformConfig`, tels que la tranche les a
     lus dans `TransformUnitOperation$$.cctor`. `probe_313` compare un MIRROR a un BUILD ; il
     redevient vert des qu'on regenere le mirror. Ce qu'il ne garde pas, c'est la valeur ECRITE
     AU SITE -- d'ou cet etage, qui la fige ;
  3. le fait que l'ORDRE des cles N'EST PAS ARITHMETIQUE : `Movement` numerote
     `Modification / Entity / Change`, `MaxHealth` numerote `Modification / Change / Entity`.
     C'est ce qui rend la table NECESSAIRE, et le test le rend visible ;
  4. `UnitStats_Transformed` INCONDITIONNEL -- pose avant la boucle, sans garde ;
  5. les DEUX gardes d'`AddTagIfImplemented` : la cle 0 (`UnitStats_Unimplemented`) ne pose
     rien, et un doublon NE REECRIT PAS ;
  6. l'ASYMETRIE `is_modifiable` entre `AddTagsForModifiable` (`!= 0`) et `AddTagsForFillUp`
     (`== 0`) -- elle est dans le binaire, et l'uniformiser serait une invention ;
  7. les REFUS : `NotImplementedError` sur un `StatPart` hors switch (le natif y LEVE un
     `System.NotImplementedException`), `ValueError` sur une lecture ECS manquante ;
  8. le fait que les SIX tags d'`AddActiveAbilityOperation` NE SONT PAS
     `GetFullStateUpdateTags(activeAbility)` -- la surcharge d'`UnitExtensions` en ajoute deux
     des qu'une ability porte un cout en munitions.

Les fragments de reference sont des EXTRAITS VERBATIM du flux natif (session Frida 1, boards
C1_02 / MC1_67, seed 777, build `rnca9r7q6c`), copies caractere pour caractere.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve()
PY = next(p for p in HERE.parents if p.name == "python")
if str(PY) not in sys.path:
    sys.path.insert(0, str(PY))

from engine.dsl.event_trigger_type import EventTriggerType  # noqa: E402
from engine.entities.stats import StatPart, StatType  # noqa: E402
from engine.streams.dispatcher import StreamDispatcher
from engine.streams.group_type import GroupType
from engine.streams.step_type import StepType
from engine.streams.stream_cache import StreamCache
from engine.streams.tag_key import TagKey  # noqa: E402
from engine.streams import conformance as CONF  # noqa: E402
from engine.streams.active_ability_ops import (AddedActiveAbility,  # noqa: E402
                                               add_active_ability,
                                               get_add_active_ability_tags,
                                               remove_active_ability)
from engine.streams.evaluate_trigger import evaluate_ability_trigger  # noqa: E402
from engine.streams.refresh_effects import (EffectSetup,  # noqa: E402
                                            add_activate_effect_action,
                                            add_receive_effect_action,
                                            generate_event_group,
                                            get_refresh_effect_tags)
from engine.streams.transform_unit import (FILL_STAT_TRANSFORM_CONFIG,  # noqa: E402
                                           INT_MIN, MOD_STAT_TRANSFORM_CONFIG,
                                           StatModifierSetup, StatOverrideReading,
                                           add_tag_if_implemented, add_tags_for_fill_up,
                                           add_tags_for_modifiable, build_transform_tags,
                                           transform_unit)
from engine.streams.unit_extensions import (ActiveAbilityState,  # noqa: E402
                                            get_full_state_update_tags_for_active)

# --- EXTRAITS VERBATIM du flux natif ---------------------------------------------------------

#: Motif A -- `RapidAssault_Movement` (board C1_02). Le `ChangeStats` est le DERNIER enfant du
#: `Group=Effect_Refresh`, parce que `UpdateEffectTargets` place `ApplyEffectsForTargets` en
#: derniere entree de sa `List<Action>`.
MOTIF_MOUVEMENT = (
    "        Group=Effect_Refresh Entity=88 Source=RapidAssault_Movement InitialTarget=\n"
    "            Action=ActivateEffect Entity=53\n"
    "                Tag=Effect_Id:88\n"
    "            Action=ReceiveEffect Entity=53\n"
    "                Tag=Effect_CurrentLevel:1\n"
    "                Tag=Effect_SourceId:53\n"
    "                Tag=Effect_Id:88\n"
    "            Action=ChangeStats Entity=53\n"
    "                Tag=UnitStats_Movement_Modification:1\n"
    "                Tag=UnitStats_Movement_Modification_Entity:88\n"
    "                Tag=UnitStats_Movement_Modification_Change:1\n"
    "                Tag=UnitStats_Transformed:1\n"
    "        Finish_Group\n")

#: Motif B -- `StandVigil_ExtraArmor` (board C1_02). Porteur 59, CIBLE 61 : le `ChangeStats`
#: porte la CIBLE, comme le `ReceiveEffect`, jamais le porteur.
MOTIF_ARMURE = (
    "        Group=Effect_Refresh Entity=95 Source=StandVigil_ExtraArmor InitialTarget=\n"
    "            Action=ActivateEffect Entity=59\n"
    "                Tag=Effect_Id:95\n"
    "            Action=ReceiveEffect Entity=61\n"
    "                Tag=Effect_CurrentLevel:1\n"
    "                Tag=Effect_SourceId:59\n"
    "                Tag=Effect_SourceTriggeredAbility:1308\n"
    "                Tag=Effect_Id:95\n"
    "            Action=ChangeStats Entity=61\n"
    "                Tag=UnitStats_FixedArmor_Modification:355\n"
    "                Tag=UnitStats_FixedArmor_Modification_Entity:95\n"
    "                Tag=UnitStats_FixedArmor_Modification_Change:355\n"
    "                Tag=UnitStats_Transformed:1\n"
    "        Finish_Group\n")

#: Motif C -- `TwistedScience` (board C1_02). Les deux actions sont enfants DIRECTS du
#: `Group=Ability_Power` : il n'y a AUCUN `Effect_Refresh` intermediaire.
MOTIF_ABILITY = (
    "    Group=Ability_Power Entity=63 Source=TwistedScience InitialTarget=\n"
    "        Action=ChangeStats Entity=63\n"
    "            Tag=UnitStats_RemoveActiveAbility:18\n"
    "        Action=ChangeAbility Entity=63\n"
    "            Tag=UnitStats_ActiveAbility_Id:1167\n"
    "            Tag=UnitStats_ActiveAbility_CanStillBeUsed:1\n"
    "            Tag=UnitStats_ActiveAbility_RemainingCooldownTurns:0\n"
    "            Tag=UnitStats_ActiveAbility_IsDisabled:0\n"
    "            Tag=UnitStats_ActiveAbility_Level:50\n"
    "            Tag=UnitStats_ActiveAbility_VariableMultiplierPercentage:180\n"
    "    Finish_Group\n")


def _emettre(profondeur: int, corps) -> str:
    """Emet `corps` a la profondeur voulue et rend le texte, enveloppe retiree."""
    cache = StreamCache()
    racines = []
    cache.add_listener(type("C", (), {"on_root_group_finished": lambda _s, g: racines.append(g),
                                      "on_log": lambda _s, _c: None})())
    events = StreamDispatcher()
    events.subscribe(cache)
    for _ in range(profondeur):
        events.start_group(GroupType.System_StartMatch, 1, "", None)
    corps(events)
    for _ in range(profondeur):
        events.finish_group()
    lignes = [l for l in "".join(racines).split("\n") if l != ""]
    return "\n".join(lignes[profondeur:len(lignes) - profondeur]) + "\n"


def _effet_mouvement() -> EffectSetup:
    from engine.entities.effect_type import EffectType
    return EffectSetup(entity_id=88, effect_type=int(EffectType.RapidAssault_Movement),
                       current_level=1, source_id=53)


# --- 1. EGALITE BRUTE des trois motifs --------------------------------------------------------

def test_motif_mouvement_egalite_brute():
    setup = _effet_mouvement()
    mod = StatModifierSetup(stat_type=StatType.MOVEMENT, stat_part=StatPart.MODIFICATION,
                            entity_id=88, stat_current=1, stat_from_modifier=1)
    texte = _emettre(2, lambda ev: generate_event_group(ev, [
        lambda: add_activate_effect_action(ev, 53, setup),
        lambda: add_receive_effect_action(
            ev, 53, get_refresh_effect_tags(setup, StepType.ReceiveEffect)),
        lambda: transform_unit(ev, 53, [mod]),
    ], setup))
    assert texte == MOTIF_MOUVEMENT, CONF.comparer(MOTIF_MOUVEMENT, texte).nouvelles


def test_motif_armure_egalite_brute_et_placement_sur_la_cible():
    from engine.entities.effect_type import EffectType
    setup = EffectSetup(entity_id=95, effect_type=int(EffectType.StandVigil_ExtraArmor),
                        current_level=1, source_id=59, source_triggered_ability=1308)
    mod = StatModifierSetup(stat_type=StatType.FIXED_ARMOR, stat_part=StatPart.MODIFICATION,
                            entity_id=95, stat_current=355, stat_from_modifier=355)
    texte = _emettre(2, lambda ev: generate_event_group(ev, [
        lambda: add_activate_effect_action(ev, 59, setup),      # PORTEUR
        lambda: add_receive_effect_action(
            ev, 61, get_refresh_effect_tags(setup, StepType.ReceiveEffect)),   # CIBLE
        lambda: transform_unit(ev, 61, [mod]),                  # CIBLE, comme le ReceiveEffect
    ], setup))
    assert texte == MOTIF_ARMURE, CONF.comparer(MOTIF_ARMURE, texte).nouvelles


def test_motif_ability_egalite_brute():
    from engine.entities.triggered_ability_type import TriggeredAbilityType
    ajoutee = AddedActiveAbility(ability_name=1167, level=50,
                                 variable_multiplier_percentage=180, can_still_be_used=True,
                                 remaining_cooldown_turns=0, is_disabled=False)

    def corps(ev):
        def enfants():
            remove_active_ability(ev, 63, 18)
            add_active_ability(ev, 63, ajoutee)
        evaluate_ability_trigger(ev, 63, int(TriggeredAbilityType.TwistedScience), None, enfants)

    assert _emettre(1, corps) == MOTIF_ABILITY


# --- 2. LES ORDINAUX ECRITS AU SITE -----------------------------------------------------------

def test_table_modifiable_ordinaux_figes():
    """Les 15 entrees de `TransformUnitOperation$$.cctor`, ordinal par ordinal.

    ⚠ CE TEST NE COMPARE PAS UN MIRROR A UN BUILD -- il fige la valeur ECRITE ICI. Un
    renumerotage de `TagKey` ou de `StatType` le fait rougir MEME si le mirror est regenere."""
    attendu = {
        0: (35, 36, 38, 37, 39, 40, 41),        # Attack
        1: (47, 48, 50, 49, 51, 52, 53),        # Movement
        2: (31, 32, 34, 33, 0, 0, 0),           # Range
        7: (54, 55, 57, 56, 61, 62, 63),        # BlockChance
        8: (64, 65, 67, 66, 0, 0, 0),           # BlockDamage
        9: (71, 72, 74, 73, 0, 0, 0),           # CriticalChance
        10: (75, 76, 78, 77, 0, 0, 0),          # CriticalDamage
        16: (42, 43, 45, 44, 0, 0, 0),          # FixedArmor
        17: (79, 79, 81, 80, 0, 0, 0),          # ExtraHits
        21: (85, 85, 87, 86, 0, 0, 0),          # ExtraPierceMelee
        22: (88, 88, 90, 89, 0, 0, 0),          # ExtraPierceRanged
        23: (82, 82, 84, 83, 0, 0, 0),          # ExtraHitsMelee
        24: (94, 94, 96, 95, 0, 0, 0),          # ExtraRange
        25: (97, 97, 99, 98, 0, 0, 0),          # ExtraMaxDamage
        26: (91, 91, 93, 92, 0, 0, 0),          # ExtraPierce
    }
    assert set(int(k) for k in MOD_STAT_TRANSFORM_CONFIG) == set(attendu)
    for stat_type, ords in attendu.items():
        cfg = MOD_STAT_TRANSFORM_CONFIG[StatType(stat_type)]
        assert (int(cfg.current_key), int(cfg.modification_key),
                int(cfg.modification_change_key), int(cfg.modification_entity_key),
                int(cfg.override_key), int(cfg.override_entity_key),
                int(cfg.override_is_modifiable_key)) == ords, StatType(stat_type).name


def test_table_fill_up_une_seule_entree_et_ses_ordinaux():
    assert set(int(k) for k in FILL_STAT_TRANSFORM_CONFIG) == {int(StatType.HEALTH)}
    cfg = FILL_STAT_TRANSFORM_CONFIG[StatType.HEALTH]
    assert (int(cfg.remaining_key), int(cfg.max_key), int(cfg.modification_key),
            int(cfg.modification_change_key), int(cfg.modification_entity_key)) == (5, 9, 10, 11,
                                                                                    12)
    assert (int(cfg.override_key), int(cfg.override_entity_key),
            int(cfg.override_is_modifiable_key)) == (0, 0, 0)
    assert cfg.event_trigger_type == EventTriggerType.HealthChanged
    assert cfg.modification_event_trigger_type is None


def test_event_trigger_type_recoupe_le_stat_type_par_son_NOM():
    """Le canal INDEPENDANT qui confirme la lecture des offsets du `.cctor`.

    Trois entrees seulement portent un `Nullable<EventTriggerType>` non vide, et les trois
    nomment exactement leur stat. Aucune erreur de decalage d'offset ne produirait cela."""
    porteurs = {int(k): v.event_trigger_type for k, v in MOD_STAT_TRANSFORM_CONFIG.items()
                if v.event_trigger_type is not None}
    porteurs.update({int(k): v.event_trigger_type for k, v in FILL_STAT_TRANSFORM_CONFIG.items()
                     if v.event_trigger_type is not None})
    assert porteurs == {int(StatType.ATTACK): EventTriggerType.AttackChanged,
                        int(StatType.BLOCK_DAMAGE): EventTriggerType.BlockDamageChanged,
                        int(StatType.HEALTH): EventTriggerType.HealthChanged}


def test_l_ordre_des_ordinaux_n_est_PAS_arithmetique():
    """CE QUI REND LA TABLE NECESSAIRE -- et qu'une deduction « +1 / +2 » manquerait.

    `Movement` et `MaxHealth` inversent leurs deux derniers ordinaux. Un port qui deduirait les
    trois cles d'un `StatType` par arithmetique serait juste sur l'un et faux sur l'autre."""
    mouvement = MOD_STAT_TRANSFORM_CONFIG[StatType.MOVEMENT]
    sante = FILL_STAT_TRANSFORM_CONFIG[StatType.HEALTH]
    assert int(mouvement.modification_entity_key) < int(mouvement.modification_change_key)
    assert int(sante.modification_change_key) < int(sante.modification_entity_key)


# --- 3. LES INVARIANTS ET LES GARDES ----------------------------------------------------------

def test_transformed_est_inconditionnel_et_hidden_ne_l_est_pas():
    assert build_transform_tags([]) == {int(TagKey.UnitStats_Transformed): 1}
    avec = build_transform_tags([], is_hidden=True)
    assert avec == {int(TagKey.UnitStats_Transformed): 1,
                    int(TagKey.UnitStats_Modification_Hidden): 1}


def test_add_tag_if_implemented_cle_zero_ne_pose_rien():
    tags = {}
    add_tag_if_implemented(tags, TagKey.UnitStats_Unimplemented, 7)
    assert tags == {}
    # ... et le contraire : une cle non nulle passe.
    add_tag_if_implemented(tags, TagKey.UnitStats_Attack, 7)
    assert tags == {int(TagKey.UnitStats_Attack): 7}


def test_add_tag_if_implemented_doublon_NE_REECRIT_PAS():
    """Le natif logge et laisse le dictionnaire INTACT -- la PREMIERE valeur gagne."""
    tags = {}
    add_tag_if_implemented(tags, TagKey.UnitStats_Attack, 7)
    add_tag_if_implemented(tags, TagKey.UnitStats_Attack, 99)
    assert tags == {int(TagKey.UnitStats_Attack): 7}


def test_stat_sans_override_n_ecrit_aucun_tag_d_override():
    """`Range` a ses trois cles d'override a 0 : la branche `Override` n'ecrit alors RIEN."""
    tags = {}
    add_tags_for_modifiable(
        tags, StatModifierSetup(stat_type=StatType.RANGE, stat_part=StatPart.OVERRIDE, value=3),
        MOD_STAT_TRANSFORM_CONFIG[StatType.RANGE])
    assert tags == {}
    # ... alors que `Attack`, qui les porte, ecrit la sentinelle.
    tags = {}
    add_tags_for_modifiable(
        tags, StatModifierSetup(stat_type=StatType.ATTACK, stat_part=StatPart.OVERRIDE, value=3),
        MOD_STAT_TRANSFORM_CONFIG[StatType.ATTACK])
    assert tags == {int(TagKey.UnitStats_Attack_Override): INT_MIN}


def test_asymetrie_is_modifiable_entre_les_deux_familles():
    """⚠ `!= 0` chez `AddTagsForModifiable`, `== 0` chez `AddTagsForFillUp`. VERBATIM.

    Les deux fonctions testent le MEME champ dans les DEUX sens. La garde le fige au lieu de
    laisser un futur relecteur « corriger » l'une des deux."""
    tags = {}
    add_tags_for_modifiable(
        tags, StatModifierSetup(stat_type=StatType.ATTACK, stat_part=StatPart.OVERRIDE,
                                override=StatOverrideReading(value=12, is_modifiable=True)),
        MOD_STAT_TRANSFORM_CONFIG[StatType.ATTACK])
    assert tags[int(TagKey.UnitStats_Attack_Override_IsModifiable)] == 1
    # La famille fill-up n'a AUCUNE cle d'override sur `Health`, donc on ne peut pas l'observer
    # par les tags : on lit alors la branche par son EFFET sur une config fabriquee pour le
    # test, avec les memes cles que la famille modifiable.
    from engine.streams.transform_unit import FillStatTransformConfig
    faux = FillStatTransformConfig(
        TagKey.UnitStats_RemainingHealth, TagKey.UnitStats_MaxHealth,
        TagKey.UnitStats_MaxHealth_Modification, TagKey.UnitStats_MaxHealth_Modification_Change,
        TagKey.UnitStats_MaxHealth_Modification_Entity,
        TagKey.UnitStats_Attack_Override, TagKey.UnitStats_Attack_Override_Entity,
        TagKey.UnitStats_Attack_Override_IsModifiable, None, None)
    tags = {}
    add_tags_for_fill_up(
        tags, StatModifierSetup(stat_type=StatType.HEALTH, stat_part=StatPart.OVERRIDE,
                                override=StatOverrideReading(value=12, is_modifiable=True),
                                number_of_members=3), faux)
    assert tags[int(TagKey.UnitStats_Attack_Override_IsModifiable)] == 0


def test_fill_up_sante_ajoute_toujours_le_nombre_de_membres():
    tags = {}
    add_tags_for_fill_up(
        tags, StatModifierSetup(stat_type=StatType.HEALTH, stat_part=StatPart.CURRENT, value=42,
                                number_of_members=3),
        FILL_STAT_TRANSFORM_CONFIG[StatType.HEALTH])
    assert tags == {int(TagKey.UnitStats_RemainingHealth): 42,
                    int(TagKey.UnitStats_NumberOfMembers): 3}


def test_modificateur_sans_entite_n_ecrit_qu_un_seul_tag():
    """La garde `if (modifierId.HasValue)` d'`AddModificationTags` -- deux tags sur trois."""
    tags = {}
    add_tags_for_modifiable(
        tags, StatModifierSetup(stat_type=StatType.MOVEMENT, stat_part=StatPart.MODIFICATION,
                                stat_current=4),
        MOD_STAT_TRANSFORM_CONFIG[StatType.MOVEMENT])
    assert tags == {int(TagKey.UnitStats_Movement_Modification): 4}


# --- 4. LES REFUS -----------------------------------------------------------------------------

def test_stat_part_hors_switch_LEVE():
    """`default:` du natif = `System.NotImplementedException`, jamais un tag manquant."""
    for part in (StatPart.CURRENT_PCT, StatPart.MAXIMUM, StatPart.MISSING):
        with pytest.raises(NotImplementedError):
            add_tags_for_modifiable(
                {}, StatModifierSetup(stat_type=StatType.ATTACK, stat_part=part, value=1),
                MOD_STAT_TRANSFORM_CONFIG[StatType.ATTACK])
    # ... et le contraire : `Maximum` EXISTE dans la famille fill-up.
    tags = {}
    add_tags_for_fill_up(
        tags, StatModifierSetup(stat_type=StatType.HEALTH, stat_part=StatPart.MAXIMUM, value=9,
                                number_of_members=1),
        FILL_STAT_TRANSFORM_CONFIG[StatType.HEALTH])
    assert tags[int(TagKey.UnitStats_MaxHealth)] == 9


def test_lecture_ecs_manquante_LEVE_au_lieu_d_ecrire_zero():
    with pytest.raises(ValueError):
        add_tags_for_modifiable(
            {}, StatModifierSetup(stat_type=StatType.MOVEMENT, stat_part=StatPart.MODIFICATION,
                                  entity_id=88),
            MOD_STAT_TRANSFORM_CONFIG[StatType.MOVEMENT])


def test_stat_part_initial_sans_modifications_LEVE():
    events = StreamDispatcher()
    with pytest.raises(ValueError):
        transform_unit(events, 53, [StatModifierSetup(
            stat_type=StatType.MOVEMENT, stat_part=StatPart.INITIAL, value=4)])


def test_stat_type_inconnu_des_trois_etages_n_ecrit_aucun_tag():
    """`StatType.DEFENSE` n'est dans aucune des deux tables et n'est pas
    `ActiveAbilityLevel` : le natif fait un `continue`, ce n'est PAS une erreur."""
    assert build_transform_tags([StatModifierSetup(
        stat_type=StatType.DEFENSE, stat_part=StatPart.MODIFICATION, stat_current=1)]) == {
        int(TagKey.UnitStats_Transformed): 1}


def test_active_ability_level_est_le_troisieme_etage():
    """Le seul cas en dur d'`Execute`, hors des deux tables -- et sa branche `continue`."""
    assert build_transform_tags([StatModifierSetup(
        stat_type=StatType.ACTIVE_ABILITY_LEVEL, stat_part=StatPart.OVERRIDE, value=7)]) == {
        int(TagKey.UnitStats_Transformed): 1, int(TagKey.UnitStats_ActiveAbility_Level): 7}
    assert build_transform_tags([StatModifierSetup(
        stat_type=StatType.ACTIVE_ABILITY_LEVEL, stat_part=StatPart.REMOVE_OVERRIDE)]) == {
        int(TagKey.UnitStats_Transformed): 1, int(TagKey.UnitStats_ActiveAbility_Level): INT_MIN}
    # `Current` n'est ni `Override` ni `RemoveOverride` : `continue`, aucun tag.
    assert build_transform_tags([StatModifierSetup(
        stat_type=StatType.ACTIVE_ABILITY_LEVEL, stat_part=StatPart.CURRENT, value=7)]) == {
        int(TagKey.UnitStats_Transformed): 1}


def test_double_active_ability_level_LEVE():
    """Le natif appelle `Dictionary$$Add` DIRECTEMENT sur ce troisieme etage, pas
    `AddTagIfImplemented` : un doublon y leve au lieu d'etre absorbe."""
    with pytest.raises(ValueError):
        build_transform_tags([
            StatModifierSetup(stat_type=StatType.ACTIVE_ABILITY_LEVEL,
                              stat_part=StatPart.OVERRIDE, value=7),
            StatModifierSetup(stat_type=StatType.ACTIVE_ABILITY_LEVEL,
                              stat_part=StatPart.OVERRIDE, value=9)])


# --- 5. LES TROIS PRODUCTEURS DE `ChangeStats` SONT DISTINCTS ---------------------------------

def test_retrait_d_ability_ecrit_un_seul_tag():
    texte = _emettre(2, lambda ev: remove_active_ability(ev, 63, 18))
    assert texte == ("        Action=ChangeStats Entity=63\n"
                     "            Tag=UnitStats_RemoveActiveAbility:18\n")


def test_les_six_tags_d_ajout_NE_SONT_PAS_get_full_state_update_tags():
    """⚠ LA CONFUSION LA PLUS FACILE, ET ELLE EST SILENCIEUSE SANS MUNITIONS.

    `AddActiveAbilityOperation$$Execute` inline SIX tags ; la surcharge d'`UnitExtensions` en
    ecrit les memes six PLUS deux des que `AmmoCost.HasValue`. Sur une ability sans munitions
    les deux fonctions coincident -- c'est pourquoi ce test EXIGE d'abord la coincidence, puis
    la divergence."""
    a = AddedActiveAbility(ability_name=1167, level=50, variable_multiplier_percentage=180,
                           can_still_be_used=True, remaining_cooldown_turns=0, is_disabled=False)
    inline = get_add_active_ability_tags(a)
    assert len(inline) == 6
    sans_ammo = get_full_state_update_tags_for_active(ActiveAbilityState(
        ability_name=1167, level=50, variable_multiplier_percentage=180, can_still_be_used=True,
        remaining_cooldown_turns=0, is_disabled=False))
    assert {int(k): int(v) for k, v in sans_ammo.items()} == inline    # coincidence
    avec_ammo = get_full_state_update_tags_for_active(ActiveAbilityState(
        ability_name=1167, level=50, variable_multiplier_percentage=180, can_still_be_used=True,
        remaining_cooldown_turns=0, is_disabled=False, ammo_cost=2, has_enough_ammo=True))
    assert len(avec_ammo) == 8                                         # divergence
    assert int(TagKey.UnitStats_TriggeredAbility_AmmoCost) not in inline


def test_cooldown_nul_est_emis_a_zero_pas_omis():
    """`Nullable$$GetValueOrDefault` : le tag sort TOUJOURS, a `0` quand le Nullable est vide."""
    tags = get_add_active_ability_tags(AddedActiveAbility(
        ability_name=1, level=1, variable_multiplier_percentage=0, can_still_be_used=False,
        remaining_cooldown_turns=None))
    assert tags[int(TagKey.UnitStats_ActiveAbility_RemainingCooldownTurns)] == 0


def test_ajout_emet_change_ability_pas_change_stats():
    texte = _emettre(1, lambda ev: add_active_ability(ev, 63, AddedActiveAbility(
        ability_name=1167, level=50, variable_multiplier_percentage=180,
        can_still_be_used=True, remaining_cooldown_turns=0, is_disabled=False)))
    assert texte.lstrip().startswith("Action=%s " % StepType.ChangeAbility.name)
    assert StepType.ChangeStats.name not in texte
