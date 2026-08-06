"""#477-r22-r1 -- GARDE offline de la QUEUE du `Group=StartTurn` (slot `0x21`) et de `Action=Info`.

Le probe `probe_477r22_turn_phase.py` MESURE en live : il monte un runner, joue des tours d'IA,
rejoue le registre `UnitFlag.NoActionAvailable` depuis le debut du flux, derive les candidats
depuis `Action=AddUnit` / `Tag=Unit_Owner_Id`, et confronte chaque couple a l'egalite brute. Ce
fichier GARDE : il fige ce que la mesure a etabli et verifie que le controle DISCRIMINE.

CE QUE LA GARDE AJOUTE AU PROBE
-------------------------------
  1. le GATE. `UnitFlagsComponent$$Add` rend `false` si le drapeau etait deja la, `$$Remove`
     `false` s'il n'y etait pas, et `MarkUnitAsNoActionAvailableOperation$$Execute` RETOURNE sur
     ce `false`. Deux appels de meme sens n'ecrivent donc QU'UNE ligne -- une propriete que le
     corpus live n'exerce pas (chaque marque y change reellement le drapeau) ;
  2. LE SENS INVERSE de la valeur : `reverse = true` (`MarkUnitAsActionAvailable`, RETRAIT du
     drapeau) ecrit `1`. La faute naturelle est d'ecrire `int(<drapeau pose>)`, et le corpus live
     ne porte que des `1` -- le test fige donc les DEUX valeurs, ce qu'aucun flux mesure ne fait ;
  3. la TABLE DE VERITE complete de `VerifyUnitTurnEnded` (2 branches x 4 predicats), dont les
     regimes que le live n'atteint pas : unite morte, tour deja fini, drapeau absent + immobile
     (le seul chemin qui ecrit `0`) ;
  4. l'ORDRE : la queue vient APRES le corps du groupe, et la MACHINE apres la boucle d'unites ;
  5. la QUEUE VERBATIM d'un couple RACINE mesure (C1_02, 3e `Group=StartTurn`) : 6 candidats,
     10 unites deja marquees, et EXACTEMENT 3 lignes emises ;
  6. `Action=Info` : `Entity=NO_ENTITY` et UNE seule cle, les deux DERIVEES du port.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve()
PY = next(p for p in HERE.parents if p.name == "python")
if str(PY) not in sys.path:
    sys.path.insert(0, str(PY))

from engine.entities.unit_flag import UnitFlag  # noqa: E402
from engine.streams import (GroupType, StepType, StreamCache,  # noqa: E402
                            StreamDispatcher, TagKey)
from engine.streams.inform_ops import (get_inform_tags,  # noqa: E402
                                       get_inform_weapon_tags, inform)
from engine.streams.turn_phase import start_turn  # noqa: E402
from engine.streams.verify_turn_finished import (FLAG,  # noqa: E402
                                                 MachineTurnState,
                                                 NoActionAvailableFlags, UnitTurnState,
                                                 mark_unit_as_no_action_available,
                                                 verify_machine_turn_ended,
                                                 verify_unit_turn_ended,
                                                 verify_units_turn_finished)

MATCH = 1

#: LA QUEUE VERBATIM du 3e `Group=StartTurn` racine du flux `C1_02` (2 tours d'IA, session 1,
#: build `rnca9r7q6c`). Les six candidats sont ceux qu'`Action=AddUnit` / `Tag=Unit_Owner_Id`
#: attribue au joueur 3 ; dix unites portaient deja `UnitFlag.NoActionAvailable` ; TROIS lignes
#: sortent. Copie caractere pour caractere.
QUEUE_VERBATIM = (
    "    Action=ChangeStats Entity=59\n"
    "        Tag=UnitStats_ActionsAvailable:1\n"
    "    Action=ChangeStats Entity=65\n"
    "        Tag=UnitStats_ActionsAvailable:1\n"
    "    Action=ChangeStats Entity=67\n"
    "        Tag=UnitStats_ActionsAvailable:1\n"
)
CANDIDATS = (59, 61, 63, 65, 67, 123)
DRAPEAUX_AVANT = (49, 51, 53, 55, 57, 59, 61, 63, 65, 67)
MARQUEES = (59, 65, 67)


class Capture:
    def __init__(self) -> None:
        self.racines: list = []

    def on_root_group_finished(self, group: str) -> None:
        self.racines.append(group)

    def on_log(self, chunk: str) -> None:
        pass


def _monter(enveloppe: bool = False):
    """Rend `(events, rendre)`. `rendre()` donne le texte, enveloppe retiree si demandee."""
    cache = StreamCache()
    capture = Capture()
    cache.add_listener(capture)
    events = StreamDispatcher()
    events.subscribe(cache)
    if enveloppe:
        events.start_group(GroupType.System_StartMatch, MATCH, "", None)

    def rendre() -> str:
        if enveloppe:
            events.finish_group()
        lignes = [l for l in "".join(capture.racines).split("\n") if l != ""]
        if enveloppe:
            lignes = lignes[1:-1]
        return "\n".join(lignes) + "\n" if lignes else ""

    return events, rendre


def _unite(entite: int, **kw) -> UnitTurnState:
    base = dict(turn_ended=False, is_dead=False, has_tiles_to_move_to=False,
                has_action_available=False)
    base.update(kw)
    return UnitTurnState(entity_id=entite, **base)


# ------------------------------------------------------------------ 1. le GATE

def test_le_registre_rend_le_booleen_de_UnitFlagsComponent_Add_et_Remove():
    flags = NoActionAvailableFlags()
    assert flags.has(7) is False
    assert flags.add(7) is True, "`Add` sur un drapeau ABSENT rend true"
    assert flags.add(7) is False, "`Add` sur un drapeau DEJA POSE rend false"
    assert flags.has(7) is True
    assert flags.remove(7) is True
    assert flags.remove(7) is False, "`Remove` sur un drapeau ABSENT rend false"
    assert flags.has(7) is False


def test_deux_marques_de_MEME_SENS_n_ecrivent_QU_UNE_ligne():
    """Le `false` d'`Add`/`Remove` GATE l'emission -- regime qu'aucun couple du corpus live
    n'exerce, chaque marque y changeant reellement le drapeau."""
    events, rendre = _monter()
    flags = NoActionAvailableFlags()
    assert mark_unit_as_no_action_available(events, flags, 7, reverse=False) is True
    assert mark_unit_as_no_action_available(events, flags, 7, reverse=False) is False
    lignes = [l for l in rendre().split("\n") if l.strip()]
    assert lignes == ["Action=ChangeStats Entity=7",
                      "    Tag=UnitStats_ActionsAvailable:0"]


def test_le_registre_est_initialisable_et_ne_decide_de_rien_par_lui_meme():
    flags = NoActionAvailableFlags(DRAPEAUX_AVANT)
    assert flags.marques() == frozenset(DRAPEAUX_AVANT)
    assert all(flags.has(u) for u in DRAPEAUX_AVANT)
    assert flags.has(123) is False, "123 entre en cours de bataille, il n'a jamais ete marque"


# ------------------------------------------------------------------ 2. le SENS de la valeur

def test_la_valeur_est_l_INVERSE_du_sens_du_drapeau():
    """`reverse = false` POSE le drapeau et ecrit `0` ; `reverse = true` le RETIRE et ecrit `1`.
    Le corpus live ne porte que des `1` : ce test-ci fige les DEUX."""
    events, rendre = _monter()
    flags = NoActionAvailableFlags()
    mark_unit_as_no_action_available(events, flags, 11, reverse=False)   # POSE  -> 0
    mark_unit_as_no_action_available(events, flags, 11, reverse=True)    # RETIRE -> 1
    lignes = [l.strip() for l in rendre().split("\n") if l.strip()]
    assert lignes == ["Action=ChangeStats Entity=11",
                      "Tag=UnitStats_ActionsAvailable:0",
                      "Action=ChangeStats Entity=11",
                      "Tag=UnitStats_ActionsAvailable:1"]


def test_l_entite_ecrite_est_celle_de_l_UNITE_pas_celle_du_match():
    """`MarkUnitAsNoActionAvailableOperation$$Execute` passe `<IEntity slot 0>(unit)`, la ou les
    deux autres emissions du meme groupe portent l'entite de MATCH. Les runners portent tous
    l'entite de match `1` : un port qui l'ecrirait en dur passerait le live."""
    events, rendre = _monter()
    # `reverse=True` RETIRE le drapeau : il faut qu'il soit POSE, sinon `Remove` rend `false`
    # et le natif n'emet rien -- c'est le gate teste plus haut.
    mark_unit_as_no_action_available(events, NoActionAvailableFlags([4242]), 4242, reverse=True)
    assert rendre().split("\n")[0] == "Action=ChangeStats Entity=4242"


def test_les_ordinaux_ECRITS_AU_SITE_sont_ceux_MESURES():
    """`probe_313` compare le MIRROR au BUILD et redevient vert des qu'on regenere le mirror
    apres un renumerotage ; ce test-ci fige la valeur ECRITE AU SITE."""
    assert int(TagKey.UnitStats_ActionsAvailable) == 0x6f
    assert int(StepType.ChangeStats) == 0xc
    assert int(UnitFlag.NoActionAvailable) == 4
    assert FLAG is UnitFlag.NoActionAvailable
    assert int(TagKey.UnitStats_TurnFinished) == 0x70, \
        "la cle VOISINE, celle que la contre-epreuve `marque_tag` du probe substitue"
    assert int(TagKey.Custom_Data) == 0xcc


# ------------------------------------------------------------------ 3. la TABLE DE VERITE

def _emet(unite: UnitTurnState, drapeau_pose: bool) -> str:
    events, rendre = _monter()
    flags = NoActionAvailableFlags([unite.entity_id] if drapeau_pose else [])
    verify_unit_turn_ended(events, flags, unite)
    return rendre()


def test_les_deux_gates_d_entree_court_circuitent_TOUT():
    """`UnitFlagsComponent$$TurnEnded()` puis `HealthComponent$$IsDead()` : les deux rendent la
    main AVANT le test du drapeau, donc quels que soient les predicats de mobilite."""
    for pose in (False, True):
        assert _emet(_unite(5, turn_ended=True, has_tiles_to_move_to=True), pose) == ""
        assert _emet(_unite(5, is_dead=True, has_tiles_to_move_to=True), pose) == ""
    assert _emet(_unite(5, is_dead=True, has_health_component=False), False) != "", \
        "`TryGetComponent<HealthComponent>` echoue -> le natif ne teste PAS la mort"


def test_branche_drapeau_ABSENT_le_seul_chemin_qui_ecrit_zero():
    """`!Has(NoActionAvailable)` : le natif POSE le drapeau ssi l'unite ne peut NI bouger NI
    agir. C'est le seul chemin qui ecrit `0`, et le corpus live ne l'exerce pas dans un
    `Group=StartTurn`."""
    assert _emet(_unite(5), False).strip().split("\n")[-1].strip() \
        == "Tag=UnitStats_ActionsAvailable:0"
    assert _emet(_unite(5, has_tiles_to_move_to=True), False) == ""
    assert _emet(_unite(5, has_action_available=True), False) == ""
    assert _emet(_unite(5, has_tiles_to_move_to=True, has_action_available=True), False) == ""


def test_branche_drapeau_PRESENT_le_chemin_du_corpus_live():
    """`Has(NoActionAvailable)` : le natif RETIRE le drapeau ssi l'unite a REGAGNE une option.
    C'est le chemin des 13 lignes mesurees."""
    assert _emet(_unite(5, has_tiles_to_move_to=True), True).strip().split("\n")[-1].strip() \
        == "Tag=UnitStats_ActionsAvailable:1"
    assert _emet(_unite(5, has_action_available=True), True).strip().split("\n")[-1].strip() \
        == "Tag=UnitStats_ActionsAvailable:1"
    assert _emet(_unite(5), True) == "", "immobile ET sans action : le drapeau reste"


def test_la_MEME_unite_avec_les_MEMES_predicats_change_de_valeur_selon_le_drapeau():
    """C'est exactement ce que le port DERIVE, et ce que la contre-epreuve `marque_branche`
    du probe attaque."""
    mobile = _unite(5, has_tiles_to_move_to=True)
    assert _emet(mobile, True) != ""
    assert _emet(mobile, False) == ""
    immobile = _unite(5)
    assert _emet(immobile, True) == ""
    assert _emet(immobile, False) != ""


# ------------------------------------------------------------------ 4. l'ORDRE

def test_la_queue_suit_l_ordre_recu_et_la_MACHINE_vient_APRES_la_boucle():
    events, rendre = _monter()
    flags = NoActionAvailableFlags([9, 8, 7, 42])
    emises = verify_units_turn_finished(
        events, flags,
        [_unite(9, has_tiles_to_move_to=True), _unite(8, has_tiles_to_move_to=True),
         _unite(7, has_tiles_to_move_to=True)],
        machine=MachineTurnState(entity_id=42, turn_ended=False, can_attack_any_unit=True))
    assert emises == [9, 8, 7, 42], "l'ordre est celui de `CurrentlyOwnedUnitIds`, machine ENSUITE"
    entites = [l.strip().split("Entity=")[1] for l in rendre().split("\n")
               if l.strip().startswith("Action=")]
    assert entites == ["9", "8", "7", "42"]


def test_la_MACHINE_n_a_PAS_de_test_de_mort_et_son_predicat_est_AUTRE():
    """`VerifyMachineTurnEnded` ne touche jamais `HealthComponent` et n'evalue ni
    `HasTilesToMoveTo` ni `HasActionAvailable` : seulement
    `<IDamagePredictionQuery slot 2>` = `MachineCanAttackAnyUnitWithAnyAbility`."""
    events, rendre = _monter()
    flags = NoActionAvailableFlags([42])
    assert verify_machine_turn_ended(
        events, flags, MachineTurnState(42, turn_ended=True, can_attack_any_unit=True)) is False
    assert rendre() == ""
    events, rendre = _monter()
    flags = NoActionAvailableFlags()
    assert verify_machine_turn_ended(
        events, flags, MachineTurnState(42, turn_ended=False, can_attack_any_unit=False)) is True
    assert rendre().strip().split("\n")[-1].strip() == "Tag=UnitStats_ActionsAvailable:0"


def test_start_turn_place_la_queue_APRES_le_corps_et_AVANT_le_Finish_Group():
    """L'ordre est LU dans `StartTurnOperation$$Execute` : le slot `0x21` vient apres les cinq
    `EvaluateAbilities(TurnStart_*)`. C'est la contre-epreuve `verif_avant_corps` du probe."""
    events, rendre = _monter()
    flags = NoActionAvailableFlags([9])
    start_turn(events, MATCH, 3,
               corps=lambda: events.action(StepType.Info, 0, {}),
               verifier=lambda: verify_units_turn_finished(
                   events, flags, [_unite(9, has_tiles_to_move_to=True)]))
    lignes = [l.strip() for l in rendre().split("\n") if l.strip()]
    assert lignes[0].startswith("Group=StartTurn")
    assert lignes[1] == "Action=StartTurn Entity=1"
    assert lignes[3].startswith("Action=Info")
    assert lignes[4] == "Action=ChangeStats Entity=9"
    assert lignes[-1] == "Finish_Group"


def test_start_turn_sans_verifier_n_emet_AUCUNE_queue():
    """La compatibilite du parametre est VERIFIEE, pas supposee : `verifier=None` doit rendre
    exactement le groupe de #477-r22."""
    events, rendre = _monter()
    start_turn(events, MATCH, 3)
    assert [l.strip() for l in rendre().split("\n") if l.strip()] == [
        "Group=StartTurn Entity=1 Source= InitialTarget=",
        "Action=StartTurn Entity=1",
        "Tag=Match_PreviousPlayerId:3",
        "Finish_Group"]


# ------------------------------------------------------------------ 5. la QUEUE VERBATIM

def test_la_queue_VERBATIM_du_couple_racine_mesure():
    """Six candidats derives de `Unit_Owner_Id`, dix drapeaux poses, TROIS lignes emises -- et
    l'entite `123`, entree en cours de bataille, n'a jamais ete marquee donc ne peut pas
    l'etre ici."""
    events, rendre = _monter(enveloppe=True)
    flags = NoActionAvailableFlags(DRAPEAUX_AVANT)
    # ⚠ LE PREDICAT DEPEND DE LA BRANCHE, ET C'EST CE QUI L'A FAIT ROUGIR A LA PREMIERE
    # ECRITURE : pour `123`, dont le drapeau est ABSENT, `tiles = False` ferait POSER le drapeau
    # (`Action=ChangeStats ... :0`) -- une ligne que le natif n'ecrit pas. La regle est celle du
    # probe (`etats_unites`) : `tiles = a_emis` si le drapeau est pose, `not a_emis` sinon.
    unites = [_unite(e, has_tiles_to_move_to=((e in MARQUEES) if flags.has(e)
                                              else (e not in MARQUEES)))
              for e in CANDIDATS]
    emises = verify_units_turn_finished(events, flags, unites)
    assert emises == list(MARQUEES)
    assert rendre() == QUEUE_VERBATIM
    assert flags.has(59) is False and flags.has(61) is True, \
        "le registre a MUTE : les trois marquees ont perdu le drapeau, les autres l'ont garde"


def test_une_unite_JAMAIS_marquee_ne_peut_pas_etre_RE_ouverte():
    """L'entite `123` (une unite apparue en cours de bataille) est un candidat, mais son drapeau
    est absent : la branche `!Has` s'applique, et une unite mobile n'y emet RIEN."""
    events, rendre = _monter()
    flags = NoActionAvailableFlags(DRAPEAUX_AVANT)
    assert verify_units_turn_finished(
        events, flags, [_unite(123, has_tiles_to_move_to=True)]) == []
    assert rendre() == ""


# ------------------------------------------------------------------ 6. `Action=Info`

def test_get_inform_tags_ecrit_UNE_seule_cle():
    assert get_inform_tags(int(TagKey.Custom_Data), 1) == {int(TagKey.Custom_Data): 1}
    assert len(get_inform_tags(int(TagKey.Custom_Data), 0)) == 1


def test_inform_ecrit_NO_ENTITY_et_le_couple_cle_valeur():
    events, rendre = _monter()
    inform(events, get_inform_tags(int(TagKey.Custom_Data), 1))
    assert [l.strip() for l in rendre().split("\n") if l.strip()] == [
        "Action=Info Entity=NO_ENTITY", "Tag=Custom_Data:1"]


def test_les_DEUX_foyers_d_Inform_ne_produisent_PAS_les_memes_cles():
    """`DSLBehaviors$$Inform(TagKey, IAmountFormula)` ecrit UNE cle ; `$$InformWeapon` en ecrit
    DEUX (trois avec `useSpecial`). Les confondre est la contre-epreuve `info_tag_arme`."""
    une = get_inform_tags(int(TagKey.Custom_Data), 1)
    arme = get_inform_weapon_tags(14, True, False)
    assert set(une) & set(arme) == set(), "les deux foyers n'ont AUCUNE cle en commun"
    assert len(arme) == 2 and len(get_inform_weapon_tags(14, True, True)) == 3
