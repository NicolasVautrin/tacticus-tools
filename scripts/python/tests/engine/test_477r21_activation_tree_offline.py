"""#477-r21 -- GARDE offline de l'ARBRE D'ACTIVATION (`Ability_Power` / `Effect_Refresh`).

`probe_477r21_activation_tree.py` MESURE en live (monte un runner, joue des tours, decoupe le
BLOC 1 de `System_StartMatch` et confronte a l'egalite brute). Ce fichier GARDE : il fige ce que
la mesure a etabli, et il verifie que le controle DISCRIMINE.

CE QUE LA GARDE AJOUTE AU PROBE. Le probe compare une FORME emise a partir de DONNEES copiees du
flux ; ce qui le rend concluant, ce sont les DERIVATIONS -- les choses que le port produit sans
que le parseur les lui donne. Ce fichier les fige une par une, en les OPPOSANT a leur contraire :

  1. l'egalite BRUTE d'un sous-arbre complet, extrait VERBATIM du flux natif ;
  2. `Tag=Effect_Id` reconstruit sur les QUATRE formes d'action, a partir du SEUL identifiant de
     l'entete de groupe -- et la garde verifie qu'un identifiant different s'y propage ;
  3. l'ASYMETRIE des tags : `ReceiveEffect` en porte jusqu'a cinq, les trois autres UN SEUL.
     C'est le `if (stepType == 0xf)` de `StreamHelper$$GetRefreshEffectTags`, et c'est la faute
     la plus facile a commettre (uniformiser les quatre) ;
  4. le PLACEMENT : `ActivateEffect` / `DeactivateEffect` sur le PORTEUR, `ReceiveEffect` /
     `LoseEffect` sur la CIBLE -- confronte sur un sous-arbre ou les deux DIVERGENT ;
  5. l'OUVERTURE CONDITIONNELLE, et son INVERSE : `GenerateEventGroup` n'ecrit RIEN sans action
     (`if (eventActions.Count > 0)`), la ou `EvaluateAbilityTrigger` ouvre toujours. Les deux
     groupes se ressemblent dans le flux et se comportent a l'oppose ;
  6. les GARDES des trois tags conditionnels (`Effect_SourceId` a 0, les trois sources) ;
  7. le REFUS d'`evaluate_abilities` quand on ne lui donne pas une sequence PAR DECLENCHEUR ;
  8. les ORDINAUX ECRITS AU SITE, figes tels que la tranche les a lus.

Les fragments de reference sont des EXTRAITS VERBATIM du flux natif (session Frida 1, board
C1_02, seed 777, build `rnca9r7q6c`), copies caractere pour caractere.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve()
PY = next(p for p in HERE.parents if p.name == "python")
if str(PY) not in sys.path:
    sys.path.insert(0, str(PY))

import probe_477r21_activation_tree as P  # noqa: E402
from engine.dsl.event_trigger_type import EventTriggerType  # noqa: E402
from engine.entities.effect_type import EffectType  # noqa: E402
from engine.entities.triggered_ability_type import TriggeredAbilityType  # noqa: E402
from engine.streams import (GroupType, StepType, StreamCache,  # noqa: E402
                            StreamDispatcher, TagKey)
from engine.streams import conformance as CONF  # noqa: E402
from engine.streams.evaluate_trigger import (evaluate_ability_trigger,  # noqa: E402
                                             execute_internal)
from engine.streams.input_messages import (START_MATCH_TRIGGERS,  # noqa: E402
                                           evaluate_abilities)
from engine.streams.refresh_effects import (EffectSetup, EffectState,  # noqa: E402
                                            add_activate_effect_action,
                                            add_deactivate_effect_action,
                                            add_lose_effect_action,
                                            add_receive_effect_action,
                                            generate_event_group,
                                            get_refresh_effect_tags)

# --- EXTRAITS VERBATIM du flux natif ---------------------------------------------------------

#: Le cas NOMINAL : une ability declenchee, un effet, un porteur = une cible.
SOUS_ARBRE_SIMPLE = (
    "    Group=Ability_Power Entity=11 Source=OnOnMeltaDamageAbility InitialTarget=\n"
    "        Group=Effect_Refresh Entity=69 Source=Melta_ExtraDmg InitialTarget=\n"
    "            Action=ActivateEffect Entity=12\n"
    "                Tag=Effect_Id:69\n"
    "            Action=ReceiveEffect Entity=12\n"
    "                Tag=Effect_CurrentLevel:1\n"
    "                Tag=Effect_SourceId:12\n"
    "                Tag=Effect_SourceTriggeredAbility:1211\n"
    "                Tag=Effect_Id:69\n"
    "        Finish_Group\n"
    "    Finish_Group\n"
)

#: Le cas d'AURA : le porteur (51) et les trois cibles (49, 55, 53) DIVERGENT. C'est ce
#: sous-arbre qui rend la derivation (D3) discriminante -- sans lui, confondre porteur et cible
#: serait invisible.
SOUS_ARBRE_AURA = (
    "    Group=Ability_Power Entity=51 Source=StructuralAnalyser InitialTarget=\n"
    "        Group=Effect_Refresh Entity=82 Source=StructuralAnalyserDmgBoost InitialTarget=\n"
    "            Action=ActivateEffect Entity=51\n"
    "                Tag=Effect_Id:82\n"
    "            Action=ReceiveEffect Entity=49\n"
    "                Tag=Effect_CurrentLevel:1\n"
    "                Tag=Effect_SourceId:51\n"
    "                Tag=Effect_SourceTriggeredAbility:1143\n"
    "                Tag=Effect_Id:82\n"
    "            Action=ReceiveEffect Entity=55\n"
    "                Tag=Effect_CurrentLevel:1\n"
    "                Tag=Effect_SourceId:51\n"
    "                Tag=Effect_SourceTriggeredAbility:1143\n"
    "                Tag=Effect_Id:82\n"
    "            Action=ReceiveEffect Entity=53\n"
    "                Tag=Effect_CurrentLevel:1\n"
    "                Tag=Effect_SourceId:51\n"
    "                Tag=Effect_SourceTriggeredAbility:1143\n"
    "                Tag=Effect_Id:82\n"
    "        Finish_Group\n"
    "    Finish_Group\n"
)

#: Un `Ability_Power` VIDE -- il existe, contrairement a un `Effect_Refresh` vide.
SOUS_ARBRE_VIDE = (
    "    Group=Ability_Power Entity=49 Source=OverwatchAutoAttack InitialTarget=\n"
    "    Finish_Group\n"
)

#: Un `Effect_Refresh` de profondeur 1 (source = un TRAIT, pas une ability declenchee), et un
#: effet a duree limitee (`Effect_RemainingTurns`). Les deux exercent des gardes distinctes.
SOUS_ARBRE_TRAIT = (
    "    Group=Effect_Refresh Entity=79 Source=HeavyWeapon_ExtraDmg InitialTarget=\n"
    "        Action=ActivateEffect Entity=49\n"
    "            Tag=Effect_Id:79\n"
    "        Action=ReceiveEffect Entity=49\n"
    "            Tag=Effect_CurrentLevel:1\n"
    "            Tag=Effect_SourceId:49\n"
    "            Tag=Effect_SourceTrait:1001\n"
    "            Tag=Effect_Id:79\n"
    "    Finish_Group\n"
)

SOUS_ARBRE_TURNS = (
    "    Group=Ability_Power Entity=53 Source=TeleportStrike InitialTarget=\n"
    "        Group=Effect_Refresh Entity=87 Source=TeleportStrike_TeleportingIn InitialTarget=\n"
    "            Action=ActivateEffect Entity=53\n"
    "                Tag=Effect_Id:87\n"
    "            Action=ReceiveEffect Entity=53\n"
    "                Tag=Effect_RemainingTurns:2\n"
    "                Tag=Effect_CurrentLevel:1\n"
    "                Tag=Effect_SourceId:53\n"
    "                Tag=Effect_SourceTriggeredAbility:1037\n"
    "                Tag=Effect_Id:87\n"
    "        Finish_Group\n"
    "    Finish_Group\n"
)

#: Un `LoseEffect` + `DeactivateEffect` : les deux formes que le nominal n'exerce pas.
SOUS_ARBRE_PERTE = (
    "    Group=Effect_Refresh Entity=104 Source=MartialSuperiority_Visual InitialTarget=\n"
    "        Action=LoseEffect Entity=65\n"
    "            Tag=Effect_Id:104\n"
    "        Action=DeactivateEffect Entity=65\n"
    "            Tag=Effect_Id:104\n"
    "    Finish_Group\n"
)

TOUS = (SOUS_ARBRE_SIMPLE, SOUS_ARBRE_AURA, SOUS_ARBRE_VIDE, SOUS_ARBRE_TRAIT,
        SOUS_ARBRE_TURNS, SOUS_ARBRE_PERTE)


def _bloc1(*fragments: str) -> list:
    return [l for f in fragments for l in f.split("\n") if l != ""]


def _emis(*fragments: str, mutation: str = "") -> str:
    par = P.parser_bloc1(_bloc1(*fragments))
    assert not par["hors"], "fragment hors perimetre : %s" % par["hors"]
    return P.emettre(par["portes"], mutation=mutation)


# --- 1. L'egalite BRUTE, sous-arbre par sous-arbre ---------------------------

@pytest.mark.parametrize("fragment", list(TOUS))
def test_chaque_sous_arbre_natif_est_reproduit_a_l_egalite_brute(fragment):
    emis = _emis(fragment)
    assert emis == fragment, (
        "1re ligne divergente : %s"
        % next((("port=%r natif=%r" % (a, b))
                for a, b in zip(emis.split("\n"), fragment.split("\n")) if a != b),
               "aucune -- les longueurs different"))


def test_les_six_sous_arbres_ENSEMBLE_sont_reproduits():
    """L'ordre est une ENTREE (le cache d'abilites et d'effets n'est pas porte) : ce que ce test
    fige, c'est que le port le PRESERVE, sans reordonner ni fusionner."""
    assert _emis(*TOUS) == "".join(TOUS)


#: Les QUATRE actions d'EFFET, seules formes que le corpus de CE fichier exerce.
#: ⚠ `P.ACTIONS_PORTEES` en compte SIX depuis `#477-r21-r1` (`ChangeStats`, `ChangeAbility`) :
#: ces deux-la sortent de trois autres operations natives et sont gardees par
#: `test_477r21r1_formes_changestats_offline.py`. Comparer a l'ensemble complet ferait rougir ce
#: fichier pour une couverture qui n'est pas la sienne.
ACTIONS_D_EFFET = frozenset((StepType.ActivateEffect.name, StepType.ReceiveEffect.name,
                             StepType.LoseEffect.name, StepType.DeactivateEffect.name))


def test_le_corpus_de_reference_exerce_les_QUATRE_formes_d_action():
    """UN TEST QUI NE VOIT QU'UNE FORME NE GARDE QUE CELLE-LA. Le controle assertionne son propre
    non-vide : si un fragment disparaissait, la garde le dirait au lieu de retrecir en silence."""
    formes = {a.step for f in TOUS
              for p in P.parser_bloc1(_bloc1(f))["portes"]
              for a in _actions(p["obs"])}
    assert formes == set(ACTIONS_D_EFFET), formes
    assert ACTIONS_D_EFFET < set(P.ACTIONS_PORTEES), (
        "les quatre actions d'effet doivent rester un SOUS-ENSEMBLE STRICT du perimetre du "
        "probe -- sinon `#477-r21-r1` a disparu du registre")


def _actions(obs) -> list:
    if isinstance(obs, P.ActionObs):
        return [obs]
    if isinstance(obs, P.AbilityPowerObs):
        return [a for e in obs.enfants for a in _actions(e)]
    return list(obs.actions)


# --- 2. (D1) `Effect_Id` reconstruit, jamais recopie -------------------------

def test_Effect_Id_est_sur_les_QUATRE_formes_et_vaut_l_entite_du_GROUPE():
    """Le parseur ne lit l'identifiant d'effet QUE dans l'entete `Group=Effect_Refresh Entity=` :
    les `Tag=Effect_Id` du natif ne l'alimentent pas. Ce test fige la propriete que cela
    mesure -- toute action d'un groupe porte l'identifiant de CE groupe."""
    assert TagKey.Effect_Id.name not in P.TAG_VERS_CHAMP, (
        "si `Effect_Id` entrait dans la table de traduction, (D1) cesserait de mesurer quoi que "
        "ce soit -- il serait recopie du natif")
    for fragment in TOUS:
        for l in _emis(fragment).split("\n"):
            pass
    for step in (StepType.ActivateEffect, StepType.DeactivateEffect, StepType.LoseEffect,
                 StepType.ReceiveEffect):
        tags = get_refresh_effect_tags(EffectSetup(entity_id=4242, effect_type=0), step)
        assert tags[int(TagKey.Effect_Id)] == 4242


def test_un_identifiant_d_effet_different_se_propage_a_TOUTES_les_lignes():
    """La contre-partie : si le port ecrivait l'identifiant en dur, ce test tomberait."""
    mute = _emis(SOUS_ARBRE_SIMPLE, mutation="effect_id")
    assert "Entity=70 Source=Melta_ExtraDmg" in mute
    assert "Tag=Effect_Id:70" in mute and "Tag=Effect_Id:69" not in mute


# --- 3. (D3) l'ASYMETRIE des tags entre les quatre formes -------------------

def test_seul_ReceiveEffect_porte_plus_d_un_tag():
    """`if (stepType == StepType.ReceiveEffect)` de `StreamHelper$$GetRefreshEffectTags` : les
    trois autres formes retombent sur la sortie commune, qui n'ecrit que `Effect_Id`."""
    effet = EffectSetup(entity_id=69, effect_type=int(EffectType.Melta_ExtraDmg),
                        current_level=1, source_id=12, source_triggered_ability=1211)
    assert list(get_refresh_effect_tags(effet, StepType.ReceiveEffect)) != \
        [int(TagKey.Effect_Id)]
    for step in (StepType.ActivateEffect, StepType.DeactivateEffect, StepType.LoseEffect):
        assert list(get_refresh_effect_tags(effet, step)) == [int(TagKey.Effect_Id)], step.name


def test_uniformiser_les_quatre_formes_ROUGIT():
    """La faute la plus facile : appliquer la branche `ReceiveEffect` a l'`ActivateEffect`."""
    mute = _emis(SOUS_ARBRE_SIMPLE, mutation="tags_activate")
    rap = CONF.comparer(SOUS_ARBRE_SIMPLE, mute)
    assert rap.divergences


# --- 4. (D3bis) le PLACEMENT porteur / cible --------------------------------

def test_ActivateEffect_porte_le_PORTEUR_et_ReceiveEffect_la_CIBLE():
    """Confronte sur l'AURA, le seul cas ou les deux DIVERGENT. Sur le cas nominal ils
    coincident, donc il ne prouverait rien."""
    emis = _emis(SOUS_ARBRE_AURA)
    assert "Action=ActivateEffect Entity=51" in emis
    for cible in (49, 55, 53):
        assert "Action=ReceiveEffect Entity=%d" % cible in emis
    assert "Action=ActivateEffect Entity=49" not in emis


def test_la_mutation_placement_MORD_sur_l_aura_et_PAS_sur_le_nominal():
    """LE GARDE DU GARDE. Une mutation qui ne peut pas mordre ne mesure rien, quel que soit son
    verdict -- et sur un sous-arbre ou porteur et cible coincident, `placement` est INERTE. Le
    probe le publie ; ce test fige les deux cotes."""
    assert _emis(SOUS_ARBRE_AURA, mutation="placement") != SOUS_ARBRE_AURA
    assert _emis(SOUS_ARBRE_SIMPLE, mutation="placement") == SOUS_ARBRE_SIMPLE


# --- 5. (D4) l'OUVERTURE CONDITIONNELLE, et son inverse ---------------------

def test_GenerateEventGroup_n_ecrit_RIEN_sans_action():
    """`if (eventActions.Count > 0)` enveloppe l'ouverture ET la fermeture."""
    cache, capture, events = _writer()
    generate_event_group(events, [], EffectSetup(entity_id=69, effect_type=0))
    assert "".join(capture.racines) == "", "un groupe VIDE ne doit produire AUCUNE ligne"


def test_EvaluateAbilityTrigger_OUVRE_meme_sans_corps():
    """L'inverse exact : le `StartGroup` ne depend que du porteur, jamais du contenu. Le flux
    temoin porte 2 / 1 / 1 `Ability_Power` vides selon le scenario."""
    assert _emis(SOUS_ARBRE_VIDE) == SOUS_ARBRE_VIDE
    assert _emis(SOUS_ARBRE_VIDE).count("\n") == 2


def test_supprimer_les_actions_fait_DISPARAITRE_le_groupe_Effect_Refresh():
    mute = _emis(SOUS_ARBRE_SIMPLE, mutation="ouverture_vide")
    assert "Effect_Refresh" not in mute
    assert "Ability_Power" in mute, ("seul le groupe d'EFFET disparait -- celui d'ABILITY reste, "
                                     "c'est la difference lue entre les deux operations")


# --- 6. LES GARDES des tags conditionnels -----------------------------------

def test_Effect_SourceId_a_ZERO_ne_produit_AUCUN_tag():
    """`if (effectComponent.<+0x10> != 0)` -- lu, et distinct d'une absence de champ."""
    sans = get_refresh_effect_tags(
        EffectSetup(entity_id=69, effect_type=0, source_id=0), StepType.ReceiveEffect)
    assert int(TagKey.Effect_SourceId) not in sans
    avec = get_refresh_effect_tags(
        EffectSetup(entity_id=69, effect_type=0, source_id=12), StepType.ReceiveEffect)
    assert avec[int(TagKey.Effect_SourceId)] == 12


def test_les_TROIS_sources_sont_INDEPENDANTES():
    """Le decompile lit deux `HasValue` imbriques (slot 6) puis un troisieme (slot 7) : rien
    n'impose qu'une seule soit posee. Le flux temoin n'en montre jamais deux, mais le port ne
    doit pas transformer cette observation en regle."""
    tags = get_refresh_effect_tags(
        EffectSetup(entity_id=69, effect_type=0, source_active_ability=7,
                    source_triggered_ability=1211, source_trait=1001), StepType.ReceiveEffect)
    assert tags[int(TagKey.Effect_SourceActiveAbility)] == 7
    assert tags[int(TagKey.Effect_SourceTriggeredAbility)] == 1211
    assert tags[int(TagKey.Effect_SourceTrait)] == 1001


def test_Effect_RemainingTurns_distingue_ABSENT_de_ZERO():
    """LE DRAPEAU EST UN CHAMP DISTINCT DE LA VALEUR (`+0x5d` vs `+0x64`) : un effet permanent
    porte `0` sous un drapeau faux. Un port qui testerait `> 0` ecraserait le cas `0`."""
    assert int(TagKey.Effect_RemainingTurns) not in get_refresh_effect_tags(
        EffectSetup(entity_id=69, effect_type=0), StepType.ReceiveEffect)
    zero = get_refresh_effect_tags(
        EffectSetup(entity_id=69, effect_type=0, remaining_turns=0), StepType.ReceiveEffect)
    assert zero[int(TagKey.Effect_RemainingTurns)] == 0


def test_Effect_State_pose_les_DEUX_tags_ensemble():
    """LU, JAMAIS CONFRONTE : aucune occurrence sur les flux temoins. Le decompile teste
    `HasValue` UNE fois puis emet les deux tags d'affilee."""
    tags = get_refresh_effect_tags(
        EffectSetup(entity_id=69, effect_type=0, state=EffectState(3, 180)),
        StepType.ReceiveEffect)
    assert tags[int(TagKey.Effect_State_Level)] == 3
    assert tags[int(TagKey.Effect_State_VariableMultiplierPercentage)] == 180


# --- 7. Le `Source=` : un NOM d'enum, pas un litteral -----------------------

def test_Source_est_le_NOM_de_l_enum_et_un_ordinal_INCONNU_s_ecrit_en_DECIMAL():
    """`System.Enum$$ToString` rend le NOM quand la valeur est un membre, le decimal sinon --
    meme regle que pour `Entity=NO_ENTITY` (#477-r18-r5). Le port ne doit ni lever ni inventer."""
    cache, capture, events = _writer()
    evaluate_ability_trigger(events, 11, 999999)
    assert "Group=Ability_Power Entity=11 Source=999999 InitialTarget=" in \
        "".join(capture.racines)


def test_les_noms_du_flux_sont_TOUS_des_membres_des_mirrors():
    """(D5). Un nom absent du mirror doit faire ROUGIR le probe, pas etre ignore."""
    for fragment in TOUS:
        for l in fragment.split("\n"):
            m = CONF.RE_GROUP.match(l)
            if not m:
                continue
            if m.group("sym") == GroupType.Effect_Refresh.name:
                assert m.group("source") in EffectType.__members__, m.group("source")
            elif m.group("sym") == GroupType.Ability_Power.name:
                assert m.group("source") in TriggeredAbilityType.__members__, m.group("source")


def test_le_probe_REFUSE_un_Source_absent_du_mirror():
    with pytest.raises(P.MesureImpossible):
        _emis("    Group=Effect_Refresh Entity=69 Source=CeNomNExistePas InitialTarget=\n"
              "        Action=ActivateEffect Entity=12\n"
              "            Tag=Effect_Id:69\n"
              "    Finish_Group\n")


# --- 8. `evaluate_abilities` : le REFUS qui evite un flux ampute -------------

def test_evaluate_abilities_EXIGE_une_sequence_par_declencheur():
    cache, capture, events = _writer()
    with pytest.raises(ValueError):
        evaluate_abilities(events, [[]])
    with pytest.raises(ValueError):
        evaluate_abilities(events, [[], [], []])
    evaluate_abilities(events, [[], []])          # le cas nominal ne leve pas
    assert "".join(capture.racines) == ""


def test_evaluate_abilities_PRESERVE_l_ordre_des_deux_declencheurs():
    cache, capture, events = _writer()
    vus = []
    evaluate_abilities(events, [[lambda: vus.append("init")], [lambda: vus.append("start")]])
    assert vus == ["init", "start"]
    assert [t.name for t in START_MATCH_TRIGGERS] == ["MatchInit", "MatchStart"]


def test_execute_internal_n_emet_RIEN_de_lui_meme():
    cache, capture, events = _writer()
    execute_internal(events, [])
    assert "".join(capture.racines) == ""


# --- 9. LA CONTRE-EPREUVE : chaque mutation MORD puis rougit ----------------

def _domaines_du_corpus() -> dict:
    return P.domaines([p for f in TOUS for p in P.parser_bloc1(_bloc1(f))["portes"]])


#: ⚠ LE PARAMETRAGE EST DERIVE DU DOMAINE, PAS DE LA LISTE DES MUTATIONS. Une mutation qu'AUCUN
#: site du corpus n'expose ne peut pas mordre : la compter rouge accuserait le port pour une
#: absence de DONNEE. Celles-la sont figees NOMMEMENT par le test suivant, jamais tues.
MUTATIONS_EXERCEES = tuple(m for m, d in _domaines_du_corpus().items() if d > 0)


@pytest.mark.parametrize("mutation", list(MUTATIONS_EXERCEES))
def test_chaque_mutation_est_CABLEE_et_rougit(mutation):
    sain = _emis(*TOUS)
    mute = _emis(*TOUS, mutation=mutation)
    assert mute != sain, "la mutation `%s` n'a PAS change le texte emis" % mutation
    assert CONF.comparer(sain, mute).divergences, "`%s` ne produit aucune divergence" % mutation


def test_les_mutations_au_domaine_NUL_sont_NOMMEES_et_ce_sont_celles_de_r1():
    """LE CONTROLE DU PARAMETRAGE CI-DESSUS. Sans lui, retirer un fragment du corpus ferait
    disparaitre des mutations de la boucle SANS QUE RIEN NE LE DISE -- le vice exact que
    `#455-r3` a nomme (un test qui ne s'execute plus n'echoue pas, il s'evapore)."""
    dom = _domaines_du_corpus()
    assert set(dom) == set(P.MUTATIONS), "le domaine ne couvre pas toutes les mutations"
    nulles = {m for m, d in dom.items() if d == 0}
    assert nulles == {"stat_table", "sans_transformed", "modifier_entity", "remove_step",
                      "ability_tags_ammo"}, nulles
    assert MUTATIONS_EXERCEES, "aucune mutation exercee -- la boucle ci-dessus serait VIDE"


def test_une_mutation_INCONNUE_ne_mord_PAS():
    """LE GARDE DU GARDE. Si `emettre` retombait sur une branche par defaut differente du port
    sain, toutes les mutations « mordraient » sans rien mesurer."""
    assert _emis(*TOUS, mutation="cette-mutation-n-existe-pas") == _emis(*TOUS)


# --- 10. LA DECOUPE et la PARTITION -----------------------------------------

def test_la_partition_MET_DE_COTE_un_sous_arbre_a_forme_non_portee():
    """Un sous-arbre qui porte une forme etrangere part HORS PERIMETRE EN ENTIER -- jamais
    ampute ligne a ligne, ce qui laisserait croire que le reste est comparable."""
    # ⚠ LA FORME ETRANGERE A CHANGE AVEC `#477-r21-r1` : `Action=ChangeStats` est desormais
    # PORTEE (`TransformUnitOperation`), donc elle ne met plus rien de cote. Le temoin est
    # maintenant `Action=Info`, qu'aucun module d'`engine/streams` ne produit.
    avec_info = (
        "    Group=Ability_Power Entity=53 Source=RapidAssault InitialTarget=\n"
        "        Group=Effect_Refresh Entity=88 Source=RapidAssault_Movement InitialTarget=\n"
        "            Action=ActivateEffect Entity=53\n"
        "                Tag=Effect_Id:88\n"
        "            Action=Info Entity=53\n"
        "                Tag=Info_Type_Protection:1\n"
        "        Finish_Group\n"
        "    Finish_Group\n")
    par = P.parser_bloc1(_bloc1(SOUS_ARBRE_SIMPLE, avec_info))
    assert len(par["portes"]) == 1 and len(par["hors"]) == 1
    assert par["hors"][0]["lignes"] == 8, "le sous-arbre ENTIER, pas les 2 lignes etrangeres"
    assert par["somme_exacte"] is True
    # ... et le CONTRAIRE : le meme sous-arbre avec `ChangeStats` a la place entre au perimetre.
    avec_changestats = avec_info.replace(
        "Action=Info Entity=53\n"
        "                Tag=Info_Type_Protection:1\n",
        "Action=ChangeStats Entity=53\n"
        "                Tag=UnitStats_Movement_Modification:1\n"
        "                Tag=UnitStats_Transformed:1\n")
    par = P.parser_bloc1(_bloc1(SOUS_ARBRE_SIMPLE, avec_changestats))
    assert len(par["portes"]) == 2 and len(par["hors"]) == 0


def test_la_somme_de_la_partition_est_EXACTE():
    par = P.parser_bloc1(_bloc1(*TOUS))
    assert par["lignes_portees"] + par["lignes_hors"] == len(_bloc1(*TOUS))
    assert par["lignes_hors"] == 0 and par["somme_exacte"] is True


def test_la_decoupe_du_BLOC_1_s_arrete_au_PrepareTurn():
    groupe = ("Group=System_StartMatch Entity=1 Source= InitialTarget=\n"
              "    Action=StartMatch Entity=1\n"
              + SOUS_ARBRE_SIMPLE +
              "    Action=PrepareTurn Entity=1\n"
              "        Tag=Match_CurrentPlayerId:3\n"
              "    Group=StartTurn Entity=1 Source= InitialTarget=\n"
              "    Finish_Group\n"
              "Finish_Group\n")
    dec = P.decouper_bloc1(groupe)
    # 11 lignes de bloc 1 (le sous-arbre entier) ; 4 de queue (`Action=PrepareTurn`, son tag, le
    # `Group=StartTurn` et son `Finish_Group`) -- le `Finish_Group` racine n'est dans NI l'un NI
    # l'autre, et c'est ce que la somme exacte verifie.
    assert len(dec["bloc1"]) == 11 and len(dec["queue"]) == 4
    assert dec["somme_exacte"] is True
    assert "\n".join(dec["bloc1"]) + "\n" == SOUS_ARBRE_SIMPLE


def test_la_decoupe_REFUSE_un_groupe_SANS_PrepareTurn():
    """La DECOUPE est lue dans l'operation : si ce jalon disparaissait, le probe doit le DIRE,
    pas se rabattre sur « tout le groupe est du bloc 1 »."""
    with pytest.raises(P.MesureImpossible):
        P.decouper_bloc1("Group=System_StartMatch Entity=1 Source= InitialTarget=\n"
                         "    Action=StartMatch Entity=1\n"
                         + SOUS_ARBRE_SIMPLE + "Finish_Group\n")


def test_les_ids_d_effet_sont_comptes_RECURSIVEMENT():
    """Une premiere version ne visitait que la profondeur 1 et rendait `0 valeurs distinctes` en
    borne (c) sur un corpus ou tous les effets sont imbriques -- un zero rassurant et faux."""
    par = P.parser_bloc1(_bloc1(SOUS_ARBRE_SIMPLE, SOUS_ARBRE_AURA))
    assert P._ids_effet(par["portes"]) == {69, 82}


# --- 11. LES ORDINAUX, figes tels que la tranche les a MESURES --------------

def test_ordinaux_figes_a_la_tranche():
    """`probe_313` compare le MIRROR au build : il redevient vert des qu'on regenere le mirror
    apres un renumerotage, alors que la valeur ECRITE au site, elle, a change. Ce test fige les
    ordinaux tels que la tranche les a lus au decompile."""
    # les deux groupes, litteraux de `StartGroup`
    assert int(GroupType.Ability_Power) == 0x15       # `EvaluateAbilityTrigger`
    assert int(GroupType.Effect_Refresh) == 0x16      # `RefreshEffectsOperation$$StartEventGroup`
    # les quatre actions, litteraux de `Events.Action` ET argument de `GetEffectTags`
    assert int(StepType.ReceiveEffect) == 0x0f
    assert int(StepType.LoseEffect) == 0x10
    assert int(StepType.ActivateEffect) == 0x11
    assert int(StepType.DeactivateEffect) == 0x12
    # les onze cles de `StreamHelper$$GetRefreshEffectTags` -- un intervalle CONTIGU, et c'est ce
    # qui rend la lecture verifiable : `0xa4`..`0xae` sans trou.
    assert int(TagKey.BondEffect_BondedId) == 0xa4
    assert int(TagKey.Effect_RemainingTurns) == 0xa5
    assert int(TagKey.Effect_PreviousLevel) == 0xa6
    assert int(TagKey.Effect_CurrentLevel) == 0xa7
    assert int(TagKey.Effect_SourceId) == 0xa8
    assert int(TagKey.Effect_SourceActiveAbility) == 0xa9
    assert int(TagKey.Effect_SourceTriggeredAbility) == 0xaa
    assert int(TagKey.Effect_SourceTrait) == 0xab
    assert int(TagKey.Effect_State_Level) == 0xac
    assert int(TagKey.Effect_State_VariableMultiplierPercentage) == 0xad
    assert int(TagKey.Effect_Id) == 0xae
    # les deux declencheurs, litteraux du slot `0x51` de `StartMatchOperation$$Execute`
    assert int(EventTriggerType.MatchInit) == 0x19
    assert int(EventTriggerType.MatchStart) == 0x1a
    # LE RECOUPEMENT QUI CONFIRME LA LECTURE DU `Source=` : le groupe ecrit le NOM d'un
    # `TriggeredAbilityType`, et l'effet qu'il enveloppe ecrit l'ORDINAL du meme. Deux canaux
    # natifs distincts -- leur accord confirme, il ne remplace pas la lecture.
    assert int(TriggeredAbilityType.OnOnMeltaDamageAbility) == 1211
    assert int(TriggeredAbilityType.StructuralAnalyser) == 1143
    assert int(TriggeredAbilityType.TeleportStrike) == 1037


# --- utilitaires -------------------------------------------------------------

class _Capture:
    def __init__(self) -> None:
        self.racines: list = []

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
    return cache, capture, events
