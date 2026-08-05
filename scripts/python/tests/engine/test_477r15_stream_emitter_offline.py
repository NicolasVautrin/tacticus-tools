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

from engine.streams import (BEntityId, GroupType, StepType, StreamCache,  # noqa: E402
                            StreamDispatcher, TagKey, format_enum_value)
from engine.streams import conformance as CONF  # noqa: E402
from engine.streams.divergence_registry import KNOWN_DIVERGENCES  # noqa: E402
from engine.streams.game_setup import (GameSetup, PlayerSetup, TileSetup,  # noqa: E402
                                       UnitSetup, emit_game_setup)

# --- EXTRAIT VERBATIM du flux natif (C1_02, seed 777) -----------------------
# Les tuiles 14..46 et les `Action=ChangeStats` / `ChangeAbility` sont omis pour la lisibilite ;
# ce qui reste est copie caractere pour caractere.
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
    "    Finish_Group\n"
    "Finish_Group\n"
)

SETUP = GameSetup(
    players=[PlayerSetup(3, 11), PlayerSetup(4, 12), PlayerSetup(5, 13)],
    tiles=[TileSetup(12, 0, 0), TileSetup(13, 0, 1)],
    platform_entity_ids=[47, 48],
    units=[UnitSetup(entity_id=49, owner_id=4, foot_tile_ids=[46])],
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


def test_purge_une_entree_non_exercee_est_perimee():
    """LA purge. Une entree que le corpus n'exerce plus doit rougir : sans cela le registre ne
    fait que grossir jusqu'a tout couvrir (lecon de `probe_181`)."""
    perimees = CONF.entrees_perimees({"MANQUANT Action=ChangeStats"})
    assert "MANQUANT Action=ChangeAbility" in perimees
    # ... et un corpus qui exerce TOUT le registre ne rend aucune entree perimee.
    assert CONF.entrees_perimees(set(KNOWN_DIVERGENCES)) == []


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


@pytest.mark.parametrize("cle", sorted(KNOWN_DIVERGENCES))
def test_chaque_cle_du_registre_est_bien_formee(cle: str):
    """Une cle mal formee ne serait jamais appariee -- l'entree deviendrait un commentaire
    inerte que la purge ne saurait meme pas signaler."""
    forme, _, symbole = cle.partition(" ")
    assert forme in (CONF.MANQUANT, CONF.EN_TROP, CONF.VALEUR)
    assert symbole, "la cle doit porter un symbole"
    if symbole == "Finish_Group":
        return
    genre, _, membre = symbole.partition("=")
    assert genre in ("Group", "Action", "Tag")
    table = {"Group": GroupType, "Action": StepType, "Tag": TagKey}[genre]
    noms = {m.name[:-1] if m.name == "None_" else m.name for m in table}
    assert membre in noms, "%s n'est pas un membre de %s" % (membre, genre)
