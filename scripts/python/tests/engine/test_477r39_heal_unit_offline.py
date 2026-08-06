"""#477-r39 -- la face STREAM du pas `Action=HealInfo`, gardee OFFLINE.

Le probe `probe_477r22_turn_phase.py` MESURE (les `Action=HealInfo` du flux, reproduites a
l'egalite brute, 5 contre-epreuves) ; ce fichier GARDE les lectures qui ne se re-derivent
d'aucun flux :

  * les SIX cles d'`IdunBattle.Operations.HealUnitOperation$$Execute`, leur ordinal, et le fait
    qu'AUCUNE n'est conditionnelle -- lecture du CHEMIN DE SORTIE, qui separe ce foyer-ci de
    `StreamHelper$$GetDamageTags`, ou le `if (caster != null)` en est un vrai ;
  * l'absence de `Tag=Target_Id` : l'identifiant de la cible n'est ecrit qu'a l'entite de
    l'action ;
  * la FORME NUE : aucune ouverture de groupe, contrairement a `ApplyDamageOperation` ;
  * les DEUX cles que ce foyer partage avec `GetDamageTags` sans les lire au meme endroit
    (`Amount` = `result.<+0x04>` ici, `result.<+0x00>` la-bas).

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
from engine.streams.heal_unit import get_heal_tags, heal_unit  # noqa: E402


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
    base = dict(caster_entity_id=81, target_entity_id=83, remaining_health=6043,
                removed_negative_unit_effects=0, was_wounded_before_heal=True, amount=1197,
                number_of_members=1)
    base.update(kw)
    return get_heal_tags(**base)


# --- 1. Les SIX cles, toutes INCONDITIONNELLES -------------------------------

#: LES SIX CLES, DANS L'ORDRE D'INSERTION DU DECOMPILE (pas celui du flux, qui est trie par
#: ordinal par `StreamCache$$Action`).
ORDRE_D_INSERTION = (TagKey.UnitStats_RemainingHealth,
                     TagKey.UnitStats_RemovedNegativeUnitEffects,
                     TagKey.UnitStats_WasWoundedBeforeHeal,
                     TagKey.Amount, TagKey.Caster_Id, TagKey.UnitStats_NumberOfMembers)


def test_les_six_cles_sont_ecrites_dans_l_ordre_du_decompile():
    assert [TagKey(o) for o in _tags()] == list(ORDRE_D_INSERTION)


def test_aucune_des_six_n_est_conditionnelle():
    """⚠ C'EST LA LECTURE CENTRALE DE LA TRANCHE, ET ELLE SE LIT AU CHEMIN DE SORTIE. Le
    decompile enveloppe `Caster_Id`, `UnitStats_NumberOfMembers` et l'emission dans un
    `if (<caster> != null)` -- exactement la forme du `if (caster != null)` de
    `StreamHelper$$GetDamageTags` autour d'`Attacker_Id`. Mais ici aucune branche ne rejoint un
    `return` normal : l'echec tombe sur le helper de levee d'IL2CPP. Ce sont des NULL-CHECKS de
    codegen, pas un `if` du source -- donc le port ecrit toujours les six.

    Le controle est fait sur les valeurs qui FERAIENT tomber une garde si le port en portait
    une : caster nul-equivalent, aucun effet retire, cible intacte, soin nul."""
    minimal = _tags(caster_entity_id=0, removed_negative_unit_effects=0,
                    was_wounded_before_heal=False, amount=0, remaining_health=0,
                    number_of_members=0)
    for cle in ORDRE_D_INSERTION:
        assert int(cle) in minimal, cle.name
    assert len(minimal) == 6


def test_le_pendant_de_Target_Id_N_EXISTE_PAS():
    """`GetDamageTags` ecrit `Tag=Target_Id` ; ce foyer-ci ne l'ecrit pas. L'identifiant de la
    cible n'apparait qu'a UN endroit, l'entite de l'`Events.Action` -- c'est pourquoi
    `get_heal_tags` le recoit et ne le consomme pas."""
    assert int(TagKey.Target_Id) not in _tags()
    # ... et le passer ne change RIEN au dictionnaire : la cible n'alimente aucune cle
    assert _tags(target_entity_id=83) == _tags(target_entity_id=999)


def test_Caster_Id_n_est_PAS_Attacker_Id():
    """Deux cles distinctes pour le meme role dans deux foyers voisins : `Caster_Id` (180) ici,
    `Attacker_Id` (182) dans `GetDamageTags`. Les confondre laisserait un flux de meme forme."""
    tags = _tags(caster_entity_id=81)
    assert tags[int(TagKey.Caster_Id)] == 81
    assert int(TagKey.Attacker_Id) not in tags
    assert int(TagKey.Caster_Id) != int(TagKey.Attacker_Id)


def test_chaque_grandeur_va_a_SA_cle():
    """Six valeurs DEUX A DEUX distinctes : une permutation quelconque devient visible. Sans
    cela, le vert du bout-en-bout ne dirait rien de l'appariement (le corpus live porte deux
    couples de valeurs egales : `RemovedNegativeUnitEffects` et `NumberOfMembers` y valent 0 et
    1, et `WasWoundedBeforeHeal` vaut 1 comme `NumberOfMembers`)."""
    tags = _tags(caster_entity_id=11, remaining_health=22, removed_negative_unit_effects=33,
                 was_wounded_before_heal=True, amount=55, number_of_members=66)
    assert tags[int(TagKey.Caster_Id)] == 11
    assert tags[int(TagKey.UnitStats_RemainingHealth)] == 22
    assert tags[int(TagKey.UnitStats_RemovedNegativeUnitEffects)] == 33
    assert tags[int(TagKey.UnitStats_WasWoundedBeforeHeal)] == 1
    assert tags[int(TagKey.Amount)] == 55
    assert tags[int(TagKey.UnitStats_NumberOfMembers)] == 66


def test_WasWoundedBeforeHeal_est_un_BOOLEEN_pas_un_compte():
    """Le natif ecrit `(uint)wasWounded & 0xff` -- le retour de
    `IdunBattle.Entities.Components.HealthComponent$$IsWounded`, evalue AVANT le `FillUp`."""
    assert _tags(was_wounded_before_heal=False)[int(TagKey.UnitStats_WasWoundedBeforeHeal)] == 0
    assert _tags(was_wounded_before_heal=True)[int(TagKey.UnitStats_WasWoundedBeforeHeal)] == 1


# --- 2. La FORME : une action NUE --------------------------------------------

def test_heal_unit_ecrit_UNE_action_et_n_ouvre_AUCUN_groupe():
    """⚠ C'est ce qui distingue ce foyer de `ApplyDamageOperation$$Execute`, qui encadre son
    action d'un `StartGroup`/`FinishGroup`. Le decompile de `HealUnitOperation$$Execute` ne
    contient aucun appel d'ouverture ; le `Group=Ability_Power` que le flux montre autour vient
    de `EvaluateTriggerOperation$$EvaluateAbilityTrigger`, l'etage du dessus."""
    capture, events = _writer()
    # une action nue ne flushe rien : `StreamCache` n'emet qu'au `Finish_Group` d'un groupe
    # racine. L'enveloppe ci-dessous est TECHNIQUE, et c'est justement la preuve que le foyer
    # n'en ouvre pas.
    events.start_group(GroupType.Ability_Power, 81, "MedicusMinistorum", None)
    heal_unit(events, 83, {int(TagKey.Amount): 1197})
    events.finish_group()
    assert "".join(capture.racines) == (
        "Group=%s Entity=81 Source=MedicusMinistorum InitialTarget=\n"
        "    Action=%s Entity=83\n"
        "        Tag=%s:1197\n"
        "Finish_Group\n" % (GroupType.Ability_Power.name, StepType.HealInfo.name,
                            TagKey.Amount.name))


def test_l_entite_de_l_action_est_celle_de_la_CIBLE():
    """`caster` et `target` sont a un argument d'ecart dans la signature native, et le flux les
    montre DIFFERENTES (`Action=HealInfo Entity=83` / `Tag=Caster_Id:81`)."""
    capture, events = _writer()
    events.start_group(GroupType.Ability_Power, 81, "", None)
    heal_unit(events, 83, _tags(caster_entity_id=81, target_entity_id=83))
    events.finish_group()
    texte = "".join(capture.racines)
    assert "Action=%s Entity=83" % StepType.HealInfo.name in texte
    assert "Tag=%s:81" % TagKey.Caster_Id.name in texte


# --- 3. Le PARSEUR du probe : ses deux refus ---------------------------------

def _observee(tags=None):
    act = R21.ActionObs(step=StepType.HealInfo.name, entity=83)
    act.tags = list(tags if tags is not None else [
        (TagKey.UnitStats_RemainingHealth.name, 6043),
        (TagKey.UnitStats_RemovedNegativeUnitEffects.name, 0),
        (TagKey.UnitStats_WasWoundedBeforeHeal.name, 1),
        (TagKey.UnitStats_NumberOfMembers.name, 1),
        (TagKey.Caster_Id.name, 81),
        (TagKey.Amount.name, 1197)])
    return act


def test_le_parseur_REFUSE_une_action_a_qui_il_manque_une_cle():
    tronquee = _observee()
    tronquee.tags = [t for t in tronquee.tags if t[0] != TagKey.Caster_Id.name]
    with pytest.raises(R21.MesureImpossible):
        R21.entrees_heal(tronquee)


def test_le_parseur_REFUSE_une_action_qui_porte_une_cle_de_PLUS():
    trop = _observee()
    trop.tags.append((TagKey.HealIsSelfCasting.name, 1))
    with pytest.raises(R21.MesureImpossible):
        R21.entrees_heal(trop)


def test_HealInfo_DANS_un_Effect_Refresh_est_REFUSEE():
    """Le perimetre est le motif « enfant DIRECT d'un `Group=Ability_Power` ». Aucune closure de
    `RefreshEffectsOperation$$UpdateEffectTargets` n'appelle `HealUnitOperation`."""
    sous = ["Group=%s Entity=104 Source=DespoiledGround InitialTarget=" % (
                GroupType.Effect_Refresh.name),
            "    Action=%s Entity=83" % StepType.HealInfo.name,
            "        Tag=%s:1" % TagKey.Amount.name,
            "Finish_Group"]
    obs = R21._lire_sous_arbre(sous)
    _capture, events = _writer()
    with pytest.raises(R21.MesureImpossible):
        R21.emettre_sous_arbre(events, obs)


# --- 4. Bout en bout : le motif observe, reproduit ---------------------------

#: LE MOTIF OBSERVE, VERBATIM (roster 2v2 `adeptHospitaller`, board MC1_67). L'ordre des tags
#: est celui des ORDINAUX -- `StreamCache$$Action` re-trie, et il differe de l'ordre
#: d'insertion du decompile.
_OBSERVE = """Group=Ability_Power Entity=81 Source=MedicusMinistorum InitialTarget=
    Action=HealInfo Entity=83
        Tag=UnitStats_RemainingHealth:6043
        Tag=UnitStats_RemovedNegativeUnitEffects:0
        Tag=UnitStats_WasWoundedBeforeHeal:1
        Tag=UnitStats_NumberOfMembers:1
        Tag=Caster_Id:81
        Tag=Amount:1197
Finish_Group
"""


def test_le_motif_observe_est_reproduit_a_l_egalite_BRUTE():
    lignes = [l for l in _OBSERVE.split("\n") if l != ""]
    obs = R21._lire_sous_arbre(lignes)
    capture, events = _writer()
    R21.emettre_sous_arbre(events, obs)
    assert "".join(capture.racines) == _OBSERVE


def test_l_ordre_ECRIT_est_celui_des_ORDINAUX_pas_celui_de_l_insertion():
    """Deux ordres distincts, et c'est mesurable : `Amount` est INSERE quatrieme et ECRIT
    sixieme, parce que son ordinal (225) est le plus grand des six."""
    ecrit = [l.split("Tag=")[1].split(":")[0] for l in _OBSERVE.split("\n") if "Tag=" in l]
    assert ecrit == [c.name for c in sorted(ORDRE_D_INSERTION, key=int)]
    assert ecrit != [c.name for c in ORDRE_D_INSERTION]


def test_les_cinq_mutations_de_la_famille_MORDENT_sur_ce_motif():
    """Chaque mutation applicable doit CHANGER le texte -- une mutation inerte ne mesure rien,
    quel que soit son verdict."""
    lignes = [l for l in _OBSERVE.split("\n") if l != ""]
    obs = R21._lire_sous_arbre(lignes)
    act = obs.enfants[0]
    hors = []
    for nom in R21.MUTATIONS_HEAL:
        if not R21.applicable_heal(nom, act):
            hors.append(nom)
            continue
        capture, events = _writer()
        R21.emettre_sous_arbre(events, obs, nom)
        assert "".join(capture.racines) != _OBSERVE, nom
    assert hors == [], hors


def test_la_forme_HealInfo_est_bien_ENTREE_au_perimetre():
    """Le pendant executable de l'entree au registre : avant `#477-r39` le motif ci-dessus
    partait hors perimetre EN ENTIER. `FORMES_PAR_TRANCHE` porte exactement ce qui l'y
    retenait, et le retirer doit le remettre dehors -- sans quoi le compte AVANT / APRES du
    probe mesurerait zero sans le dire."""
    lignes = [l for l in _OBSERVE.split("\n") if l != ""]
    assert R21.formes_etrangeres(lignes) == []
    retirees = R21.FORMES_PAR_TRANCHE["#477-r39"]
    assert R21.formes_etrangeres(lignes, retirees) == ["Action=%s" % StepType.HealInfo.name]
