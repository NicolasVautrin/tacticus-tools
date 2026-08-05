"""#477-r20 -- GARDE offline de l'enveloppe `System_StartMatch` et de sa DECOUPE.

Le probe `probe_477r20_start_match.py` MESURE en live (il monte un runner, joue des tours d'IA,
extrait le groupe et confronte). Ce fichier GARDE : il fige ce que la mesure a etabli, et il
verifie que le controle DISCRIMINE.

CE QUE LA GARDE AJOUTE AU PROBE -- et pourquoi elle porte surtout sur la DECOUPE. Cette tranche
est la premiere ou le port n'emet PAS tout le groupe : 475 des 477 lignes du flux temoin restent
dehors. Un comparateur qui amputerait le natif de ce qu'il ne sait pas produire, sans le dire,
serait exactement la « projection implicite » que `engine.streams.conformance` existe pour
interdire. La garde fige donc :

  1. l'egalite BRUTE de ce qui EST porte -- entete, `Action=StartMatch` SANS tag, `Finish_Group` ;
  2. le dictionnaire VIDE de l'action : c'est une LECTURE (aucun `Dictionary$$Add` entre le ctor
     et l'appel dans `IdunBattle.Operations.StartMatchOperation$$Execute`), pas une deduction du
     flux -- un test qui l'oublierait laisserait passer un tag invente ;
  3. la DECOUPE et ses quatre refus : elle rougit si l'entete n'est pas la cible, si la premiere
     ligne de profondeur 1 n'est pas `Action=StartMatch`, si cette action porte des tags, ou si
     la somme `1 + 1 + tags + contenu + 1` ne retombe pas sur le total. Sans ces refus,
     l'amputation ne serait imputable a rien ;
  4. la VENTILATION du contenu : sous-arbres + lignes isolees == contenu, sinon des lignes
     disparaitraient du compte rendu sans que personne ne le voie ;
  5. l'ANCRAGE (A3)/(A4) et ce qu'il REFUSE : un flux ou le premier `Group=StartTurn` serait
     RACINE plutot qu'imbrique doit rougir -- c'est la consequence lue du dernier appel de
     l'operation (`ContinueTurnPhase`), donc le cran qui mesure la place du groupe.

Le fragment de reference est un EXTRAIT VERBATIM du flux natif (session Frida 10, board C1_02,
seed 777, build `rnca9r7q6c`), copie caractere pour caractere.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve()
PY = next(p for p in HERE.parents if p.name == "python")
if str(PY) not in sys.path:
    sys.path.insert(0, str(PY))

import probe_477r20_start_match as P  # noqa: E402
from engine.streams import (GroupType, StepType, StreamCache,  # noqa: E402
                            StreamDispatcher, TagKey)
from engine.streams import conformance as CONF  # noqa: E402
from engine.streams.game_setup import MATCH_ENTITY_ID  # noqa: E402
from engine.streams.input_messages import (PHASE_BARRIER_GROUPS,  # noqa: E402
                                           START_MATCH_SOURCE_ID, start_match,
                                           visit_start_battle_message)

# --- EXTRAIT VERBATIM du flux natif : l'enveloppe telle que le jeu l'ecrit -------------------
FRAGMENT_NATIF = (
    "Group=System_StartMatch Entity=1 Source= InitialTarget=\n"
    "    Action=StartMatch Entity=1\n"
    "Finish_Group\n"
)

#: Les trois premieres et les trois dernieres lignes du groupe REEL (C1_02, 2 tours). Elles
#: servent a construire des blocs de test qui ont la meme FORME que le natif, sans recopier les
#: 477 lignes.
DEBUT_REEL = (
    "Group=System_StartMatch Entity=1 Source= InitialTarget=\n"
    "    Action=StartMatch Entity=1\n"
    "    Group=Ability_Power Entity=11 Source=OnOnMeltaDamageAbility InitialTarget=\n"
    "        Group=Effect_Refresh Entity=69 Source=Melta_ExtraDmg InitialTarget=\n"
    "            Action=ActivateEffect Entity=12\n"
    "                Tag=Effect_Id:69\n"
    "        Finish_Group\n"
    "    Finish_Group\n"
    "    Action=PrepareTurn Entity=1\n"
    "        Tag=Match_CurrentPlayerId:3\n"
    "    Group=StartTurn Entity=1 Source= InitialTarget=\n"
    "        Action=StartTurn Entity=1\n"
    "    Finish_Group\n"
    "Finish_Group\n"
)


class Capture:
    def __init__(self) -> None:
        self.racines: list = []

    def on_root_group_finished(self, group: str) -> None:
        self.racines.append(group)

    def on_log(self, chunk: str) -> None:
        pass


def emettre(mutation: str = "", corps=None):
    cache = StreamCache()
    capture = Capture()
    cache.add_listener(capture)
    events = StreamDispatcher()
    events.subscribe(cache)
    if mutation:
        return P.emettre(mutation=mutation)
    visit_start_battle_message(events, MATCH_ENTITY_ID, corps=corps)
    return "".join(capture.racines), len(capture.racines)


# --- 1. L'egalite BRUTE de ce qui EST porte ---------------------------------

def test_enveloppe_egale_le_fragment_natif():
    texte, racines = emettre()
    assert texte == FRAGMENT_NATIF, (
        "premiere ligne divergente : %s"
        % next((("port=%r natif=%r" % (a, b))
                for a, b in zip(texte.split("\n"), FRAGMENT_NATIF.split("\n")) if a != b),
               "aucune -- les longueurs different"))
    assert racines == 1, "un appel = un groupe racine flushe"


def test_l_action_StartMatch_ne_porte_AUCUN_tag():
    """LECTURE, pas deduction du flux : `StartMatchOperation$$Execute` construit son dictionnaire
    puis appelle l'action SANS aucun `Dictionary$$Add` entre les deux."""
    cache = StreamCache()
    capture = Capture()
    cache.add_listener(capture)
    events = StreamDispatcher()
    events.subscribe(cache)
    events.start_group(GroupType.System_StartMatch, MATCH_ENTITY_ID,
                       START_MATCH_SOURCE_ID, None)
    start_match(events, MATCH_ENTITY_ID)
    events.finish_group()
    lignes = [l for l in CONF.parse_flux("".join(capture.racines)) if l.forme != "VIDE"]
    assert [l.cle_symbole for l in lignes] == ["Group=System_StartMatch",
                                               "Action=StartMatch", "Finish_Group"]
    assert not [l for l in lignes if l.forme == "Tag"], "le dictionnaire natif est VIDE"


def test_entite_et_source_du_groupe_racine():
    """`sourceId` = `String.Empty` (troisieme occurrence de la meme lecture), et l'entite est
    celle du MATCH -- que le natif obtient ici par `GetMatchEntity(state).Id`."""
    assert START_MATCH_SOURCE_ID == ""
    texte, _ = emettre()
    assert texte.split("\n")[0] == ("Group=System_StartMatch Entity=%d Source= "
                                    "InitialTarget=" % MATCH_ENTITY_ID)


def test_l_entite_SUIT_le_parametre_et_n_est_pas_une_constante_recopiee():
    """Les deux voies natives (l'appel a `GetMatchEntity` a l'ouverture, le litteral de
    l'`Action=`) valent la meme chose sur nos runners. Le port les fait donc suivre le MEME
    parametre -- ce test interdit qu'une des deux redevienne une constante en dur."""
    cache = StreamCache()
    capture = Capture()
    cache.add_listener(capture)
    events = StreamDispatcher()
    events.subscribe(cache)
    visit_start_battle_message(events, 4242)
    texte = "".join(capture.racines)
    assert "Group=System_StartMatch Entity=4242 " in texte
    assert "Action=StartMatch Entity=4242" in texte
    assert "Entity=1" not in texte


def test_le_corps_rend_le_trou_EXPRIMABLE_sans_changer_l_enveloppe():
    """`corps` est le seul degre de liberte du mirror : un appelant qui saurait produire l'un des
    trois blocs non portes le passe ici. L'enveloppe et l'`Action=StartMatch` doivent rester
    inchangees, et le contenu se placer ENTRE l'action et le `Finish_Group`."""
    def corps():
        pass
    sans, _ = emettre()
    avec, _ = emettre(corps=corps)
    assert avec == sans, "un corps vide ne doit rien changer"

    cache = StreamCache()
    capture = Capture()
    cache.add_listener(capture)
    events = StreamDispatcher()
    events.subscribe(cache)

    def corps_reel():
        events.start_group(GroupType.Effect_Refresh, 69, "Melta_ExtraDmg", None)
        events.finish_group()

    visit_start_battle_message(events, MATCH_ENTITY_ID, corps=corps_reel)
    lignes = [l.cle_symbole for l in CONF.parse_flux("".join(capture.racines))
              if l.forme != "VIDE"]
    assert lignes == ["Group=System_StartMatch", "Action=StartMatch",
                      "Group=Effect_Refresh", "Finish_Group", "Finish_Group"], lignes


# --- 2. LA CONTRE-EPREUVE : chaque mutation doit MORDRE puis rougir ----------

@pytest.mark.parametrize("mutation", list(P.MUTATIONS_TEXTE))
def test_chaque_mutation_rougit(mutation):
    """Un « 0 divergence » ne vaut rien si le comparateur rendait vert quoi qu'il arrive. Le
    garde du garde est `texte != sain` : au cran precedent une mutation N'A PAS ROUGI parce
    qu'elle ajoutait un groupe qui COMPENSAIT celui qu'elle retirait."""
    sain, _ = P.emettre()
    mute, _ = P.emettre(mutation=mutation)
    assert mute != sain, "la mutation `%s` n'a PAS change le texte emis" % mutation
    rap = CONF.comparer(sain, mute)
    assert rap.divergences, "la mutation `%s` ne produit aucune divergence" % mutation


def test_une_mutation_INCONNUE_ne_mord_PAS():
    """LE GARDE DU GARDE DU GARDE. `a_morde=True` ne vaut que si le levier de mutation est
    REELLEMENT cable : si `emettre` retombait sur une branche par defaut differente du port sain,
    toutes les mutations « mordraient » sans rien mesurer. Un nom inconnu doit rendre EXACTEMENT
    le texte sain -- c'est ce qui prouve que les dix `a_morde` viennent bien de leur branche."""
    sain, n = P.emettre()
    inconnue, m = P.emettre(mutation="cette-mutation-n-existe-pas")
    assert inconnue == sain and m == n


def test_une_mutation_d_ancrage_INCONNUE_ne_mord_PAS():
    seq, flux = _seq_et_flux(SETUP, PLACE, DEBUT_REEL, APRES)
    assert P.ancrage(seq, flux, mutation="inconnue") == P.ancrage(seq, flux)
    assert P.muter_flux(flux, "inconnue") == flux


def test_les_dix_mutations_sont_TOUTES_cablees():
    """Le pendant positif : chaque nom declare doit changer quelque chose. Une mutation declaree
    mais non cablee passerait le test precedent ET serait comptee dans le rapport du probe."""
    sain, _ = P.emettre()
    for nom in P.MUTATIONS_TEXTE:
        mute, _ = P.emettre(mutation=nom)
        assert mute != sain, "mutation de texte `%s` NON CABLEE" % nom
    seq, flux = _seq_et_flux(SETUP, PLACE, DEBUT_REEL, APRES)
    sain_a = P.ancrage(seq, flux)
    for nom in P.MUTATIONS_ANCRAGE:
        assert P.ancrage(seq, flux, mutation=nom) != sain_a, "mutation d'ancrage `%s` NON CABLEE" % nom
    assert len(P.MUTATIONS_TEXTE) + len(P.MUTATIONS_ANCRAGE) == 10


def test_la_mutation_tags_est_bien_celle_qui_manquerait_le_plus():
    """Un tag invente sur l'`Action=StartMatch` est la faute la plus facile a commettre (toutes
    les autres actions du flux en portent). Elle doit rougir en VALEUR, pas passer."""
    sain, _ = P.emettre()
    mute, _ = P.emettre(mutation="tags")
    rap = CONF.comparer(sain, mute)
    assert any("Tag=" in d.cle for d in rap.divergences), [d.cle for d in rap.divergences]


# --- 3. LA DECOUPE et ses quatre refus --------------------------------------

def test_decoupe_du_bloc_reel():
    dec = P.decouper(DEBUT_REEL)
    assert dec["action_est_start_match"] is True
    assert dec["tags_action"] == []
    assert dec["entite_entete"] == "1" and dec["entite_action"] == "1"
    assert dec["source_entete"] == ""
    assert dec["somme_exacte"] is True
    assert dec["texte_ampute"] == FRAGMENT_NATIF
    assert len(dec["contenu"]) == len(dec["lignes"]) - 3


def test_la_decoupe_REFUSE_un_entete_qui_n_est_pas_la_cible():
    with pytest.raises(P.MesureImpossible):
        P.decouper("Group=System_GameSetup Entity=1 Source= InitialTarget=\n"
                   "    Action=StartMatch Entity=1\n"
                   "Finish_Group\n")


def test_la_decoupe_REFUSE_un_bloc_trop_court():
    with pytest.raises(P.MesureImpossible):
        P.decouper("Group=System_StartMatch Entity=1 Source= InitialTarget=\n"
                   "Finish_Group\n")


def test_la_decoupe_VOIT_une_premiere_action_differente():
    """Si le natif ecrivait autre chose en tete, la LECTURE serait fausse -- et c'est le probe
    qui doit le dire, pas le lecteur du rapport."""
    dec = P.decouper("Group=System_StartMatch Entity=1 Source= InitialTarget=\n"
                     "    Action=PrepareTurn Entity=1\n"
                     "    Action=StartMatch Entity=1\n"
                     "Finish_Group\n")
    assert dec["action_est_start_match"] is False


def test_la_decoupe_COMPTE_les_tags_de_l_action():
    """Le dictionnaire natif est vide ; s'il cessait de l'etre, les tags doivent SORTIR du
    contenu et etre comptes a part -- sinon la somme mentirait dans les deux sens."""
    dec = P.decouper("Group=System_StartMatch Entity=1 Source= InitialTarget=\n"
                     "    Action=StartMatch Entity=1\n"
                     "        Tag=Match_CurrentPlayerId:3\n"
                     "        Tag=Match_PreviousPlayerId:0\n"
                     "    Group=Ability_Power Entity=11 Source=X InitialTarget=\n"
                     "    Finish_Group\n"
                     "Finish_Group\n")
    assert len(dec["tags_action"]) == 2
    assert len(dec["contenu"]) == 2
    assert dec["somme_exacte"] is True


def test_la_somme_de_la_decoupe_est_EXACTE_sur_un_bloc_quelconque():
    """La propriete qui rend l'amputation imputable : rien ne se perd entre le total du groupe et
    ce qui est publie."""
    for bloc in (DEBUT_REEL, FRAGMENT_NATIF):
        dec = P.decouper(bloc)
        n = len([l for l in bloc.split("\n") if l != ""])
        assert 1 + 1 + len(dec["tags_action"]) + len(dec["contenu"]) + 1 == n


# --- 4. LA VENTILATION : rien ne disparait du compte rendu -------------------

def test_ventilation_somme_exacte_et_sous_arbres():
    dec = P.decouper(DEBUT_REEL)
    vent = P.ventiler(dec["contenu"])
    assert vent["somme_exacte"] is True
    syms = [s for s, _src, _n in vent["sous_arbres"]]
    assert syms == ["Ability_Power", "StartTurn"], syms
    assert vent["isolees"] == 2, "l'`Action=PrepareTurn` et son tag ne sont dans aucun sous-arbre"
    assert vent["total_arbres"] + vent["isolees"] == len(dec["contenu"])


def test_ventilation_d_un_contenu_VIDE():
    vent = P.ventiler([])
    assert vent["sous_arbres"] == [] and vent["isolees"] == 0
    assert vent["somme_exacte"] is True


# --- 5. `Effect_Refresh` : ce que la tranche NE debloque PAS -----------------

def test_effect_refresh_est_ventile_par_CHEMIN_pas_seulement_par_racine():
    """Le coeur du resultat de la tranche. Un `Effect_Refresh` n'est comparable que si TOUT le
    chemin de la racine jusqu'a lui est emis. Sur le flux temoin, 35 des 42 passent par un
    `Ability_Power` et 2 par le `StartTurn` imbrique : porter la seule racine n'en rend AUCUN
    atteignable."""
    eff = P.profondeurs_effect_refresh(DEBUT_REEL)
    assert eff["total"] == 1
    assert eff["par_profondeur"] == {2: 1}
    assert eff["par_chemin"] == {"System_StartMatch > Ability_Power": 1}
    assert eff["chemin_porte"] == 0, ("un `Effect_Refresh` sous un `Ability_Power` n'a PAS son "
                                      "chemin porte par la seule enveloppe")


def test_effect_refresh_a_profondeur_1_a_bien_son_chemin_porte():
    """La contre-partie : le compteur DISCRIMINE. S'il rendait 0 quel que soit le flux, la mesure
    du paragraphe precedent ne vaudrait rien."""
    eff = P.profondeurs_effect_refresh(
        "Group=System_StartMatch Entity=1 Source= InitialTarget=\n"
        "    Action=StartMatch Entity=1\n"
        "    Group=Effect_Refresh Entity=79 Source=HeavyWeapon_ExtraDmg InitialTarget=\n"
        "    Finish_Group\n"
        "Finish_Group\n")
    assert eff["total"] == 1 and eff["chemin_porte"] == 1


# --- 6. L'ANCRAGE : les quatre predictions, et ce qu'elles REFUSENT ----------

def _flux(*blocs) -> str:
    return "".join(blocs)


SETUP = "Group=System_GameSetup Entity=1 Source= InitialTarget=\nFinish_Group\n"
PLACE = "Group=User_PlaceUnit Entity=NO_ENTITY Source= InitialTarget=\nFinish_Group\n"
APRES = "Group=User_EndTurn Entity=1 Source= InitialTarget=\nFinish_Group\n"
STARTTURN_RACINE = ("Group=StartTurn Entity=1 Source= InitialTarget=\n"
                    "    Action=StartTurn Entity=1\n"
                    "Finish_Group\n")


def _seq_et_flux(*blocs):
    import probe_477r19_process_removals as R19
    flux = _flux(*blocs)
    return R19.sequence_racines(flux), flux


def test_ancrage_sain():
    seq, flux = _seq_et_flux(SETUP, PLACE, DEBUT_REEL, APRES, STARTTURN_RACINE)
    anc = P.ancrage(seq, flux)
    assert anc["unique"] is True
    assert anc["avant_ok"] is True and anc["avant"] == ["System_GameSetup", "User_PlaceUnit"]
    assert anc["a3"] is True, "le premier `Group=StartTurn` du flux est le groupe IMBRIQUE"
    assert anc["a4"] is True, "le premier `Action=PrepareTurn` est a profondeur 1 DEDANS"
    assert anc["ok"] is True


def test_ancrage_REFUSE_un_premier_StartTurn_RACINE():
    """LA PREDICTION DISCRIMINANTE. `ContinueTurnPhase` est le DERNIER appel de
    `StartMatchOperation$$Execute`, donc le premier `StartTurn` du flux est DANS le groupe. Un
    flux ou il serait racine AVANT doit rougir."""
    seq, flux = _seq_et_flux(SETUP, PLACE, STARTTURN_RACINE, DEBUT_REEL, APRES)
    anc = P.ancrage(seq, flux)
    assert anc["a3"] is False and anc["ok"] is False


def test_ancrage_REFUSE_un_PrepareTurn_a_profondeur_0_avant():
    """`Action=PrepareTurn` existe A PROFONDEUR 0 hors de tout groupe (mesure #477-r18 § 2) --
    mais pas AVANT le `System_StartMatch`, puisque c'est lui qui l'emet en premier."""
    seq, flux = _seq_et_flux(SETUP, "Action=PrepareTurn Entity=1\n", PLACE, DEBUT_REEL)
    anc = P.ancrage(seq, flux)
    assert anc["a4"] is False and anc["ok"] is False


def test_ancrage_REFUSE_une_racine_inattendue_AVANT():
    seq, flux = _seq_et_flux(SETUP, APRES, PLACE, DEBUT_REEL)
    anc = P.ancrage(seq, flux)
    assert anc["avant_ok"] is False and anc["ok"] is False


def test_ancrage_REFUSE_deux_occurrences():
    seq, flux = _seq_et_flux(SETUP, PLACE, DEBUT_REEL, DEBUT_REEL)
    anc = P.ancrage(seq, flux)
    assert anc["unique"] is False and anc["ok"] is False


@pytest.mark.parametrize("mutation", list(P.MUTATIONS_ANCRAGE))
def test_chaque_mutation_d_ancrage_MORD(mutation):
    seq, flux = _seq_et_flux(SETUP, PLACE, DEBUT_REEL, APRES)
    sain = P.ancrage(seq, flux)
    mute = P.ancrage(seq, flux, mutation=mutation)
    assert mute != sain, "la mutation `%s` n'a PAS change l'ancrage" % mutation
    assert mute["ok"] is False, "la mutation `%s` doit faire rougir l'ancrage" % mutation


def test_System_StartMatch_reste_une_BARRIERE_de_phase():
    """Il est dans `PHASE_BARRIER_GROUPS` depuis #477-r19 (c'est un message d'entree) : porter
    son enveloppe ne doit pas l'en retirer, sinon l'ancrage du cran precedent se relache."""
    assert GroupType.System_StartMatch in PHASE_BARRIER_GROUPS


# --- 7. LES ORDINAUX, figes tels que la tranche les a MESURES ----------------

def test_ordinaux_figes_a_la_tranche():
    """`probe_313` compare le MIRROR au build : il redevient vert des qu'on regenere le mirror
    apres un renumerotage, alors que la valeur ECRITE au site, elle, a change. Ce test fige les
    ordinaux tels que la tranche les a lus au decompile."""
    assert int(GroupType.System_StartMatch) == 4     # la lambda `<Visit>b__18_0` passe `4`
    assert int(StepType.StartMatch) == 1             # `Events.Action(1, 1, <dict vide>)`
    assert MATCH_ENTITY_ID == 1                      # `Entity=1` des trois voies
    # Ce que la tranche NE porte PAS, mais qu'elle NOMME : les deux blocs du contenu.
    assert int(GroupType.Ability_Power) == 0x15
    assert int(GroupType.Effect_Refresh) == 0x16
    assert int(GroupType.StartTurn) == 0x2f
    assert int(GroupType.RarityCapTransform) == 0x2e   # `StartGroup(0x2e, ...)` du bloc rarete
    assert int(StepType.PlayerInitialRarity) == 0x3d   # `Action(0x3d, ...)` du meme bloc
    assert int(StepType.PrepareTurn) == 0x26
    assert int(TagKey.Match_CurrentPlayerId) == 0x9d
    # LE RECOUPEMENT QUI CONFIRME LA LECTURE DU BLOC RARETE : le seul `Dictionary$$Add` de ce
    # bloc ecrit la cle `0xd4`, et `0xd4` NOMME `Rarity`. Une lecture fausse de ce fragment
    # aurait donne une cle qui ne nomme rien de rapport avec un `PlayerInitialRarity`.
    assert int(TagKey.Rarity) == 0xd4
