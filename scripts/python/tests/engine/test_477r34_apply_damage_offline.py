"""#477-r34 -- la face STREAM du `Group=Damage`, gardee OFFLINE.

Le probe `probe_477r22_turn_phase.py` MESURE (61 `Group=Damage` reproduits sur tout le flux,
8 contre-epreuves) ; ce fichier GARDE les lectures qui ne se re-derivent d'aucun flux :

  * les QUINZE cles de `IdunBattle.Core.Services.StreamHelper$$GetDamageTags`, leur ordinal, et
    lesquelles sont CONDITIONNELLES ;
  * le RETOUR ANTICIPE quand la source du coup est vide -- asymetrique, et non exerce par le
    corpus live (72 / 72 des `Group=Damage` observes portent une source) ;
  * `Attack_Is_First_Hit` = `hitIndex == 0`, et non le champ `isFirstDamagingHit` ;
  * l'appariement champ d'`AbilityOrEffect` -> `TagKey` des DEUX cascades, dont le couple
    `TriggeredAbility` -> `Passive_Ability_Type` que le nom ne donne pas ;
  * la FORME du groupe : `Source=` vide, `InitialTarget=` vide, l'action AVANT le corps.

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve()
RACINE = HERE.parents[2]
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

import probe_477r21_activation_tree as R21  # noqa: E402
from engine.streams import GroupType, StepType, StreamCache, StreamDispatcher, TagKey  # noqa: E402
from engine.streams.apply_damage import DAMAGE_SOURCE_ID, apply_damage  # noqa: E402
from engine.streams.damage_result import (AbilityOrEffect,  # noqa: E402
                                          DamageAppliedResult, DamageSource)
from engine.streams.stream_helper import (ADDITIONAL_HIT_SOURCE_TAGS,  # noqa: E402
                                          SOURCE_TAGS, get_damage_tags)


class _Capture:
    def __init__(self) -> None:
        self.racines = []

    def on_root_group_finished(self, group: str) -> None:
        self.racines.append(group)

    def on_log(self, chunk: str) -> None:
        pass


def _writer():
    cache = StreamCache()
    capture = _Capture()
    cache.add_listener(capture)
    events = StreamDispatcher()
    events.subscribe(cache)
    return capture, events


def _tags(**kw):
    base = dict(target_entity_id=81, damage_result=DamageAppliedResult(), num_members_died=0,
                caster_entity_id=21, amount=565, remaining_health=2479, remaining_armor=0,
                total_shield=0, number_of_members=1)
    base.update(kw)
    return get_damage_tags(**base)


# --- 1. Les QUINZE cles, et le partage inconditionnel / conditionnel ---------

#: LES DOUZE CLES QUE `GetDamageTags` ECRIT SANS AUCUNE GARDE -- lues entre le ctor du
#: dictionnaire et le premier `if` du decompile.
INCONDITIONNELLES = (TagKey.UnitStats_RemainingHealth, TagKey.UnitStats_RemainingArmor,
                     TagKey.Shields_RemainingAmount, TagKey.UnitStats_NumberOfMembers,
                     TagKey.Attack_DidCrit, TagKey.Attack_DidBlock, TagKey.Attack_DidEvade,
                     TagKey.Attack_WasOverkill, TagKey.Attack_Is_First_Hit,
                     TagKey.Attack_WasMemberKilled, TagKey.Target_Id, TagKey.Amount)


def test_les_douze_cles_inconditionnelles_sont_TOUJOURS_ecrites():
    # aucune source, aucun caster, aucun mort : le minimum absolu
    tags = _tags(caster_entity_id=None)
    for cle in INCONDITIONNELLES:
        assert int(cle) in tags, cle.name
    # `DamageProfileType` l'est aussi, mais elle est ecrite APRES `Amount` : on la garde a part
    # pour que l'ordre du decompile reste lisible dans ce test.
    assert int(TagKey.DamageProfileType) in tags


def test_Attacker_Id_est_CONDITIONNEL_au_caster():
    assert int(TagKey.Attacker_Id) not in _tags(caster_entity_id=None)
    assert _tags(caster_entity_id=21)[int(TagKey.Attacker_Id)] == 21


def test_NumberOfMembers_Change_est_CONDITIONNEL_mais_WasMemberKilled_NON():
    sans = _tags(num_members_died=0)
    assert int(TagKey.UnitStats_NumberOfMembers_Change) not in sans
    assert sans[int(TagKey.Attack_WasMemberKilled)] == 0
    avec = _tags(num_members_died=2)
    assert avec[int(TagKey.UnitStats_NumberOfMembers_Change)] == 2
    assert avec[int(TagKey.Attack_WasMemberKilled)] == 1


def test_Attack_Is_First_Hit_sort_de_hitIndex_egal_zero():
    """⚠ ET NON DU CHAMP `isFirstDamagingHit`, qui existe a `+0x18` et n'est PAS lu ici. Le
    getter a un corps deduplique (`return *(int*)(this + 0x14) == 0;`) que Ghidra nomme
    `IdunMetaLogic.UserProgress.ProductCost$$get_IsFree`."""
    assert _tags(damage_result=DamageAppliedResult(hit_index=0))[
        int(TagKey.Attack_Is_First_Hit)] == 1
    for index in (1, 2, 7):
        assert _tags(damage_result=DamageAppliedResult(hit_index=index))[
            int(TagKey.Attack_Is_First_Hit)] == 0


def test_les_quatre_booleens_du_DamageAppliedResult_vont_a_leur_cle():
    """Les quatre octets `+0x0c`..`+0x0f`, chacun a SA cle. Une permutation serait invisible
    tant que les quatre valent la meme chose -- le test les separe donc une a une."""
    for champ, cle in ((("did_block"), TagKey.Attack_DidBlock),
                       (("did_evade"), TagKey.Attack_DidEvade),
                       (("did_crit"), TagKey.Attack_DidCrit),
                       (("did_overkill"), TagKey.Attack_WasOverkill)):
        tags = _tags(damage_result=DamageAppliedResult(**{champ: True}))
        assert tags[int(cle)] == 1, champ
        autres = [c for _n, c in (("did_block", TagKey.Attack_DidBlock),
                                  ("did_evade", TagKey.Attack_DidEvade),
                                  ("did_crit", TagKey.Attack_DidCrit),
                                  ("did_overkill", TagKey.Attack_WasOverkill)) if c is not cle]
        assert [tags[int(c)] for c in autres] == [0, 0, 0], champ


# --- 2. Les DEUX cascades, et le retour anticipe -----------------------------

def test_l_appariement_des_deux_cascades_est_celui_du_decompile():
    """⚠ `TriggeredAbility` PRODUIT `Passive_Ability_Type` : le nom du champ et celui de la cle
    ne se ressemblent pas, et c'est la seule chose qui rend la confusion visible --
    `TriggeredAbilityType` partage 458 ordinaux avec `EffectType`."""
    assert [(champ, cle.name) for champ, cle in SOURCE_TAGS] == [
        ("active_ability", TagKey.Active_Ability_Type.name),
        ("triggered_ability", TagKey.Passive_Ability_Type.name),
        ("effect", TagKey.Effect_Type.name)]
    assert [(champ, cle.name) for champ, cle in ADDITIONAL_HIT_SOURCE_TAGS] == [
        ("active_ability", TagKey.Additional_Hit_ActiveAbility_Source.name),
        ("triggered_ability", TagKey.Additional_Hit_TriggeredAbility_Source.name),
        ("effect", TagKey.Additional_Hit_Effect_Source.name)]
    # les six cles sont DEUX A DEUX distinctes : aucune n'est partagee entre les cascades
    toutes = [int(cle) for _c, cle in SOURCE_TAGS + ADDITIONAL_HIT_SOURCE_TAGS]
    assert len(set(toutes)) == 6


@pytest.mark.parametrize("champ,cle", [(c, k) for c, k in SOURCE_TAGS])
def test_la_cascade_de_source_ecrit_UNE_cle_et_la_bonne(champ, cle):
    dr = DamageAppliedResult(source=DamageSource(source=AbilityOrEffect(**{champ: 1234})))
    tags = _tags(damage_result=dr)
    assert tags[int(cle)] == 1234
    assert [int(k) for _c, k in SOURCE_TAGS if int(k) in tags] == [int(cle)]


def test_la_cascade_s_arrete_au_PREMIER_champ_non_vide():
    """Le natif teste les trois EN CASCADE ; deux champs remplis n'ecrivent qu'UN tag, celui du
    premier. Le struct n'impose pas l'exclusivite, le port ne l'impose pas non plus."""
    dr = DamageAppliedResult(source=DamageSource(
        source=AbilityOrEffect(active_ability=11, triggered_ability=22, effect=33)))
    tags = _tags(damage_result=dr)
    assert tags[int(TagKey.Active_Ability_Type)] == 11
    assert int(TagKey.Passive_Ability_Type) not in tags
    assert int(TagKey.Effect_Type) not in tags


def test_source_VIDE_fait_RETOURNER_avant_le_hit_additionnel():
    """⚠ L'ASYMETRIE EST LUE, ET ELLE N'EST PAS EXERCEE PAR LE CORPUS LIVE (72 / 72 des
    `Group=Damage` observes portent une source). `if (!damageResult.<+0x40>.HasValue) return
    tags;` : le bloc `Additional_Hit_*` n'est meme pas evalue."""
    dr = DamageAppliedResult(source=DamageSource(
        source=None, additional_hit_source=AbilityOrEffect(effect=99)))
    tags = _tags(damage_result=dr)
    for _champ, cle in SOURCE_TAGS + ADDITIONAL_HIT_SOURCE_TAGS:
        assert int(cle) not in tags, cle.name


def test_source_PRESENTE_mais_vide_saute_l_Add_et_evalue_QUAND_MEME_l_additionnel():
    """L'AUTRE branche de l'asymetrie : le `Nullable` a une valeur, ses trois champs sont
    vides -> le natif fait un `goto` qui saute l'`Add` et tombe sur le bloc `+0x78`."""
    dr = DamageAppliedResult(source=DamageSource(
        source=AbilityOrEffect(), additional_hit_source=AbilityOrEffect(effect=99)))
    tags = _tags(damage_result=dr)
    for _champ, cle in SOURCE_TAGS:
        assert int(cle) not in tags
    assert tags[int(TagKey.Additional_Hit_Effect_Source)] == 99


# --- 3. La FORME du groupe ---------------------------------------------------

def test_apply_damage_ecrit_le_groupe_puis_l_action_puis_ferme():
    capture, events = _writer()
    apply_damage(events, 81, {int(TagKey.Amount): 565})
    assert "".join(capture.racines) == (
        "Group=%s Entity=81 Source= InitialTarget=\n"
        "    Action=%s Entity=81\n"
        "        Tag=%s:565\n"
        "Finish_Group\n" % (GroupType.Damage.name, StepType.UnitDamaged.name,
                            TagKey.Amount.name))


def test_le_Source_du_groupe_est_le_litteral_VIDE():
    assert DAMAGE_SOURCE_ID == ""


def test_le_corps_vient_APRES_l_action_jamais_avant():
    capture, events = _writer()

    def corps():
        events.action(StepType.Info, 0, {int(TagKey.Custom_Data): 7})

    apply_damage(events, 81, {int(TagKey.Amount): 1}, corps)
    lignes = [l for l in "".join(capture.racines).split("\n") if l]
    assert lignes[1].strip().startswith("Action=%s" % StepType.UnitDamaged.name)
    assert lignes[3].strip().startswith("Action=%s" % StepType.Info.name)


# --- 4. Le PARSEUR du probe : ses trois refus --------------------------------

_GROUPE = ["Group=%s Entity=81 Source= InitialTarget=" % GroupType.Damage.name,
           "    Action=%s Entity=81" % StepType.UnitDamaged.name,
           "        Tag=%s:1" % TagKey.Target_Id.name,
           "Finish_Group"]


def test_le_parseur_REFUSE_une_premiere_action_qui_n_est_pas_UnitDamaged():
    faux = list(_GROUPE)
    faux[1] = "    Action=%s Entity=81" % StepType.ChangeStats.name
    with pytest.raises(R21.MesureImpossible):
        R21._lire_groupe_damage(faux)


def test_le_parseur_REFUSE_un_tag_que_GetDamageTags_n_ecrit_pas():
    faux = list(_GROUPE)
    faux.insert(3, "        Tag=%s:1" % TagKey.Effect_Id.name)
    with pytest.raises(R21.MesureImpossible):
        R21._lire_groupe_damage(faux)


def test_la_partition_ECARTE_un_Group_Damage_a_Source_non_vide():
    """L'axe des SOURCES vaut aussi pour `Group=Damage` : le litteral lu est vide, donc un
    `Source=` renseigne sort d'un producteur qu'on n'a pas lu."""
    faux = list(_GROUPE)
    faux[0] = "Group=%s Entity=81 Source=QuelqueChose InitialTarget=" % GroupType.Damage.name
    etrangeres = R21.formes_etrangeres(faux)
    assert any("Source=QuelqueChose" in e for e in etrangeres), etrangeres


# --- 5. Bout en bout : un `Group=Damage` du flux, reproduit ------------------

#: UN `Group=Damage` OBSERVE, verbatim (scenario `C1_02`, effet de tuile `EnvFireTileDamage`).
#: Il porte la voie `Effect_Type` -- celle qu'un port qui apparierait la cle au NOM du champ
#: rendrait faux.
_OBSERVE = """Group=Damage Entity=67 Source= InitialTarget=
    Action=UnitDamaged Entity=67
        Tag=UnitStats_RemainingHealth:10344
        Tag=UnitStats_RemainingArmor:0
        Tag=UnitStats_NumberOfMembers:1
        Tag=Attack_Is_First_Hit:1
        Tag=Attack_DidCrit:0
        Tag=Attack_DidBlock:0
        Tag=Attack_DidEvade:0
        Tag=Attack_WasOverkill:0
        Tag=Attack_WasMemberKilled:0
        Tag=Target_Id:67
        Tag=Attacker_Id:40
        Tag=Amount:138
        Tag=DamageProfileType:3
        Tag=Effect_Type:5
        Tag=Shields_RemainingAmount:0
Finish_Group
"""


def test_un_Group_Damage_observe_est_reproduit_a_l_egalite_BRUTE():
    lignes = [l for l in _OBSERVE.split("\n") if l != ""]
    obs = R21._lire_groupe_damage(lignes)
    capture, events = _writer()
    R21.emettre_sous_arbre(events, obs)
    assert "".join(capture.racines) == _OBSERVE


def test_les_huit_mutations_de_la_famille_MORDENT_sur_ce_groupe():
    """Chaque mutation applicable doit CHANGER le texte -- une mutation inerte ne mesure rien,
    quel que soit son verdict. `damage_ordre_action` est hors domaine ici (le groupe n'a pas de
    corps) et `damage_voie_additionnelle` aussi (aucun hit additionnel) : le test l'exige de
    `applicable_damage`, il ne l'excuse pas apres coup."""
    lignes = [l for l in _OBSERVE.split("\n") if l != ""]
    obs = R21._lire_groupe_damage(lignes)
    hors = []
    for nom in R21.MUTATIONS_DAMAGE:
        if not R21.applicable_damage(nom, obs):
            hors.append(nom)
            continue
        capture, events = _writer()
        R21.emettre_sous_arbre(events, obs, nom)
        assert "".join(capture.racines) != _OBSERVE, nom
    assert sorted(hors) == ["damage_ordre_action", "damage_voie_additionnelle"]
