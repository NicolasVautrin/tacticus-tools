"""#477-r25 -- CLIQUET des slots d'interface AUTRES que `Core.Services.IOperationProcessor`.

    python -m pytest scripts/python/tests/engine/test_477r25_slots_autres_interfaces_offline.py -q

Ce que ce fichier empeche de revenir :

* qu'une citation « slot X = NomDeMethode » reparaisse FAUSSE dans le depot (etage 3, perimetre
  DERIVE d'un `git ls-files` -- aucune liste blanche de fichiers) ;
* qu'un renumerotage inter-build passe pour un vert. C'est EXACTEMENT ce qui s'est produit :
  `IBattleQuery` a gagne des methodes entre `gqfc5mff6c` et `rnca9r7q6c`, et les fiches ecrites
  avant ont continue de citer les anciens numeros SANS QUE RIEN NE ROUGISSE. L'etage 2 fige les
  couples mesures, donc un renumerotage rend ROUGE au lieu de glisser ;
* qu'un corpus vide passe pour un vert (etage 0 : le balayage assertionne son propre NON-VIDE) ;
* que les deux derivations divergent en silence (etage 5 : la grille des TYPES et les ANCRES DE
  NOM de `#477-r24-r1` doivent rendre la MEME table pour `IOperationProcessor`).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve()
SCRIPTS = HERE.parents[2]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import probe_477r24r1_slots_interface as R24                            # noqa: E402
import probe_477r25_slots_autres_interfaces as P                        # noqa: E402


#: LES COUPLES TRANCHES PAR CETTE TRANCHE, figes a l'ordinal MESURE dans le metadata du build
#: `rnca9r7q6c`. Chacun est atteste par une source INDEPENDANTE du metadata -- un call-site
#: decompile, ou la lambda du decorateur enregistreur
#: `IdunBattle.Core.Services.RecordedSimulationRequestsBattleQuery`, qui re-appelle l'inner par
#: le MEME slot depuis une methode NOMMEE.
#:
#: Les cinq premiers sont ceux du cas nomme : `case-27` disait `GetAdjacentEnemies` au slot
#: `0x7f`, `case-250` au `0x7c`. Le nom ne designe pas UN slot mais QUATRE -- `0x7d..0x80` --
#: et `0x7c` n'en fait pas partie : c'est `GetAdjacentUnits`, amis compris.
COUPLES_FIGES: dict[str, dict[int, tuple[str, int]]] = {
    "IBattleQuery": {
        0x7C: ("GetAdjacentUnits", 4),          # ce que `case-250` prenait pour AdjacentEnemies
        0x7D: ("GetAdjacentEnemies", 3),        # `<GetAdjacentEnemies>b__0` DisplayClass152_0
        0x7F: ("GetAdjacentEnemies", 3),        # lecture de `case-27`, JUSTE
        0x80: ("GetAdjacentEnemies", 3),        # `<GetAdjacentEnemies>b__0` DisplayClass155_0
        0x81: ("GetAdjacentFriends", 2),        # `FightingRetreatAbility$$GetDynamicInvalid...`
        0x51: ("GetAdjacentTiles", 4),          # ce que `case-243` prenait pour FreeAdjacent
        0x52: ("GetFreeAdjacentTiles", 1),      # `<GetFreeAdjacentTiles>b__0` DisplayClass102_0
        0x64: ("GetTilesAtDistance", 3),        # lecture de `case-433`, JUSTE
        0x02: ("IsMeleeAttack", 4),             # ancre runtime de `case-27` (vtable 6, offset 4)
        0x4F: ("GetAdjacentTiles", 4),          # ancre runtime de `case-27` (vtable 0x53)
    },
    "IAttackQuery": {
        0x02: ("HasValidTargets", 3),
        0x0D: ("GetAllTilesInAbilityRange", 2),
        0x0E: ("GetAllTilesInAbilityRange", 3),
    },
    "IMovementQuery": {
        0x00: ("GetMovableTilesFor", 3),
        0x02: ("GetMovablePositionsFor", 3),
        0x03: ("HasAnyMovablePositionsFor", 3),
        0x0E: ("GetPathfinderTypeForUnit", 1),
    },
}

#: Nombre de slots par interface sur ce build. Fige : une table qui RETRECIT en silence est
#: exactement ce qui ferait passer une citation hors bornes pour « slot inconnu, on ignore ».
NB_SLOTS = {
    "IBattleQuery": 219, "IAttackQuery": 22, "IMatchState": 55, "IDamagePrediction": 20,
    "IDamagePredictionQuery": 19, "IDamageCalculations": 19, "IMovementQuery": 19,
    "ITargetingQuery": 13, "IEffect": 47, "IAmountFormula": 5, "ITargetsSelector": 15,
    "IPlaybook": 10, "IPseudoRNG": 8, "IStreamDispatcher": 3, "IPathfinders": 6,
    "IUtilitiesDatabase": 2, "IEffectsDatabase": 1, "IActiveAbility": 30,
}


@pytest.fixture(scope="module")
def tables() -> dict[str, dict[int, tuple[str, int, int]]]:
    return P.lire_tsv()


@pytest.fixture(scope="module")
def citations(tables) -> list[P.Citation]:
    cits, _ecartees, _recense = P.recolter(tables)
    return cits


@pytest.fixture(scope="module")
def recolte_fenetre1(tables):
    """La recolte a `fenetre=1` -- l'etat de #477-r25, garde comme REFERENCE."""
    return P.recolter(tables, fenetre=1)


@pytest.fixture(scope="module")
def lecteur():
    """Un `MetadataReader` deja localise (grille des methodes ET des types) -- ~12 s, UNE fois."""
    import build_pin
    import il2cpp_metadata
    from symbols_layout import build_dir

    try:
        meta = build_pin.global_metadata()
    except build_pin.BuildPinRefused as exc:
        pytest.skip("metadata IL2CPP non disponible (entree hors depot) : %s"
                    % str(exc).splitlines()[0])
    methods_tsv = build_dir() / "frida" / "methods.tsv"
    reader = il2cpp_metadata.read(meta)
    reader.locate(il2cpp_metadata.class_method_order(
        methods_tsv, "%s.%s" % P.ANCRES_TYPES[0]))
    reader.locate_types([(ns, nm, il2cpp_metadata.class_method_order(
        methods_tsv, "%s.%s" % (ns, nm))) for ns, nm in P.ANCRES_TYPES])
    return reader, il2cpp_metadata


# --------------------------------------------------------- etage 0 : le corpus est NON VIDE


def test_etage0_le_balayage_voit_quelque_chose(citations: list[P.Citation]) -> None:
    """Un balayage qui ne visite rien rend 0 desaccord et passe pour vert. On l'interdit."""
    assert P.fichiers_balayes(), "perimetre VIDE : `git ls-files` n'a rien rendu"
    assert len(citations) >= 60, (
        "seulement %d attestation(s) recoltee(s) -- le corpus a fondu, ou les motifs de "
        "reconnaissance ne matchent plus. Un cliquet sur un corpus vide est un faux vert."
        % len(citations))
    assert len({c.iface for c in citations}) >= 4, (
        "attestations concentrees sur %d interface(s) -- le probe ne couvre plus qu'un cas"
        % len({c.iface for c in citations}))


def test_etage0_la_forme_recepteur_slot_nom_est_captee(tables) -> None:
    """La forme du CAS NOMME (`battleQuery.<slot 0x7c> GetAdjacentEnemies`) doit etre vue.  [slot-attribution:refute]

    Les trois formes heritees de `#477-r24-r1` ne la captent PAS : elles attendent un signe
    egal, ou un qualificateur COLLE au nom. Sans la forme D, les deux attributions litigieuses
    du cas nomme sont INVISIBLES -- une garde aveugle a ce qu'elle est censee arbitrer.
    """
    ligne = "adjEnemies = battleQuery.<slot 0x7c> GetAdjacentEnemies(caster, owner, false);"  # [slot-attribution:refute]
    formes = P._COUPLES["IBattleQuery"][0]
    vus = {(int(m.group("n%d" % k), 0), m.group("nom%d" % k))
           for k, rx in enumerate(formes) for m in rx.finditer(ligne)}
    assert (0x7C, "GetAdjacentEnemies") in vus, (
        "la forme `recepteur.<slot N> Nom` n'est pas captee -- vus : %s" % sorted(vus))


# ------------------------------------------------- etage 1 : l'entree versionnee est saine


@pytest.mark.parametrize("iface", sorted(NB_SLOTS))
def test_etage1_table_contigue_depuis_zero(tables, iface: str) -> None:
    """Chaque interface couverte occupe 0..N-1 sans trou.

    Ce n'est pas cosmetique : une interface qui en ETEND une autre demarre AU-DESSUS de zero
    (mesure : `IsSimple` a le slot 9 dans la table qui suit `IAmountFormula`), et lire ses
    slots comme des index fabriquerait un mapping faux. Le jour ou une des 18 basculera dans
    ce regime, ce test le dira.
    """
    table = tables[iface]
    assert len(table) == NB_SLOTS[iface], (
        "%s : %d slots, %d attendus" % (iface, len(table), NB_SLOTS[iface]))
    assert sorted(table) == list(range(NB_SLOTS[iface])), (
        "%s : les slots ne forment pas 0..%d contigus" % (iface, NB_SLOTS[iface] - 1))


def test_etage1_ioperationprocessor_nest_PAS_dans_cette_entree(tables) -> None:
    """Le perimetre est « les AUTRES interfaces » -- la garder ici dupliquerait #477-r24-r1."""
    assert "IOperationProcessor" not in tables


# ------------------------------------------- etage 2 : les couples TRANCHES sont FIGES


@pytest.mark.parametrize("iface,slot,attendu", sorted(
    (i, s, v) for i, d in COUPLES_FIGES.items() for s, v in d.items()))
def test_etage2_couple_fige(tables, iface: str, slot: int, attendu: tuple[str, int]) -> None:
    nom, nargs, _flags = tables[iface][slot]
    assert (nom, nargs) == attendu, (
        "%s slot 0x%02x : la table dit %s/%d, la tranche avait MESURE %s/%d. Si le build a "
        "renumerote, ce ne sont pas seulement les tables qu'il faut regenerer -- ce sont "
        "toutes les fiches qui citent ces slots." % (iface, slot, nom, nargs, *attendu))


def test_etage2_un_nom_designe_un_ENSEMBLE_de_slots(tables) -> None:
    """Le retournement du cas, ecrit comme une assertion.

    `case-27` (`0x7f`) et `case-250` (`0x7c`) ne pouvaient PAS etre departages par recoupement :
    `GetAdjacentEnemies` occupe QUATRE slots, donc plusieurs valeurs sont a priori plausibles.
    Ce qui tranche, c'est que `0x7c` n'est dans AUCUN d'eux.
    """
    bq = tables["IBattleQuery"]
    enemies = sorted(s for s, v in bq.items() if v[0] == "GetAdjacentEnemies")
    friends = sorted(s for s, v in bq.items() if v[0] == "GetAdjacentFriends")
    libres = sorted(s for s, v in bq.items() if v[0] == "GetFreeAdjacentTiles")
    assert enemies == [0x7D, 0x7E, 0x7F, 0x80], enemies
    assert friends == [0x81, 0x82, 0x83, 0x84], friends
    assert libres == [0x52, 0x53], libres
    assert 0x7C not in enemies and bq[0x7C][0] == "GetAdjacentUnits"
    assert 0x80 not in friends, "0x80 est un GetAdjacentEnemies, pas un GetAdjacentFriends"
    assert 0x51 not in libres and bq[0x51][0] == "GetAdjacentTiles"


def test_etage2_larite_separe_les_voisins_du_cas_nomme(tables) -> None:
    """Ce qui a permis de trancher au DECOMPILE : les arites different.

    `FightingRetreatAbility$$GetDynamicInvalidTargetReason` passe 3 arguments au slot `0x7d` et
    2 au slot `0x81`. Si les voisins avaient la meme arite, le call-site ne dirait plus rien --
    ce test garde le discriminant lui-meme.
    """
    bq = tables["IBattleQuery"]
    assert bq[0x7D][1] == 3 and bq[0x7C][1] == 4, "AdjacentEnemies(3) vs AdjacentUnits(4)"
    assert bq[0x81][1] == 2, "AdjacentFriends prend 2 arguments"
    assert len({bq[0x7C][1], bq[0x7D][1], bq[0x81][1]}) == 3, (
        "les trois arites doivent rester DISTINCTES -- sinon le call-site ne departage plus")


# --------------------------------------- etage 3 : aucune citation FAUSSE dans le depot


def test_etage3_aucune_citation_fausse(tables, citations: list[P.Citation]) -> None:
    faux_nom, faux_arite, _autre = P.confronter(citations, tables)
    assert not faux_nom, "citation(s) au SLOT/NOM faux :\n  " + "\n  ".join(faux_nom)
    assert not faux_arite, "citation(s) a l'ARITE fausse :\n  " + "\n  ".join(faux_arite)


@pytest.mark.parametrize("mutant", sorted(P.MUTANTS))
def test_etage3_la_garde_mord(tables, citations: list[P.Citation], mutant: str) -> None:
    """Contre-epreuve : chaque mutant doit faire bouger au moins un compteur."""
    base = P.jouer(tables, citations, None)
    mute = P.jouer(P.muter(tables, mutant, citations), citations, None)
    assert mute != base, "le mutant `%s` n'a RIEN change (%s) -- il est inerte" % (mutant, base)


# ------------------------------------------ etage 3bis : la FENETRE elle-meme (#477-r30)


def test_etage3bis_la_fenetre_APPORTE_des_couples_enjambants(
        citations: list[P.Citation]) -> None:
    """La fenetre doit voir ce que `fenetre=1` ne voyait pas -- sinon elle ne sert a rien.

    C'est le cliquet du gisement de #477-r30 : `#477-r25` exigeait slot et nom ADJACENTS, et
    une citation FAUSSE y a survecu (`test_thunderous_assault_push_live.py`, corrigee a la
    main) uniquement parce qu'un saut de ligne les separait.
    """
    assert P.FENETRE >= 2, "la fenetre est retombee a 1 -- le gisement de #477-r30 se rouvre"
    enjambants = [c for c in citations if c.ligne != c.ligne_nom]
    assert len(enjambants) >= 40, (
        "seulement %d couple(s) ENJAMBANT(S) sur %d -- l'appariement en fenetre ne mord plus"
        % (len(enjambants), len(citations)))
    assert len({c.fichier for c in enjambants}) >= 20, (
        "les couples enjambants sont concentres sur %d fichier(s) -- ce n'est plus un gisement"
        % len({c.fichier for c in enjambants}))


def test_etage3bis_la_fenetre_RETRECIT_la_zone_aveugle(tables,
                                                       recolte_fenetre1) -> None:
    """Un cliquet dont la zone aveugle ne retrecit pas est un inventaire, pas une garde.

    On compare les DEUX regimes sur le MEME corpus : le nombre de lignes qui citent un slot
    sans qu'aucun nom ne lui soit appariable doit avoir BAISSE.
    """
    _ref_cits, ref, _ = recolte_fenetre1
    _cits, ecartees, _ = P.recolter(tables)
    assert ecartees.sans_couple < ref.sans_couple, (
        "zone aveugle INCHANGEE : %d ligne(s) sans couple a fenetre=1 comme a fenetre=%d"
        % (ref.sans_couple, P.FENETRE))
    assert ref.sans_couple - ecartees.sans_couple >= 15, (
        "la fenetre ne recupere que %d ligne(s) (%d -> %d) -- mesure a 24 le 2026-08-06"
        % (ref.sans_couple - ecartees.sans_couple, ref.sans_couple, ecartees.sans_couple))


def test_etage3bis_fenetre1_reste_le_regime_de_477r25(recolte_fenetre1) -> None:
    """`fenetre=1` doit RESTER exactement l'ancien regime : 0 couple enjambant, 0 faux.

    Sans cette assertion, un elargissement accidentel du regime de base passerait pour un
    gain de la fenetre.
    """
    ref_cits, _ref, _ = recolte_fenetre1
    assert all(c.ligne == c.ligne_nom for c in ref_cits), (
        "a fenetre=1, un couple s'etale sur deux lignes -- le regime de base a fui")


def test_etage3bis_le_mutant_des_enjambants_est_INERTE_a_fenetre1(
        tables, citations: list[P.Citation], recolte_fenetre1) -> None:
    """Le mutant qui garde la fenetre doit MORDRE en fenetre et NE RIEN FAIRE a fenetre=1.

    C'est ce qui prouve qu'il garde bien l'ELARGISSEMENT, et pas l'appariement en general :
    les quatre mutants herites de #477-r25 mordent dans les deux regimes, donc aucun d'eux
    ne dirait qu'on a perdu la fenetre.
    """
    ref_cits, _ref, _ = recolte_fenetre1
    mute = P.muter(tables, "enjambants-decales", citations)
    assert P.jouer(mute, citations, None) != P.jouer(tables, citations, None), (
        "le mutant `enjambants-decales` ne mord PAS en fenetre -- la fenetre n'est pas gardee")
    assert P.jouer(mute, ref_cits, None) == P.jouer(tables, ref_cits, None), (
        "le mutant `enjambants-decales` mord AUSSI a fenetre=1 : il ne discrimine pas les "
        "couples que seule la fenetre voit, donc il ne garde pas l'elargissement")


def test_etage3bis_le_bloc_ne_franchit_pas_une_ligne_VIDE() -> None:
    """Une ligne vide est une frontiere de paragraphe -- mesure : 2 faux positifs tenaient a ce
    seul franchissement (`case-433-...-a-gates-whole-board.md`, `formulas.py`)."""
    lignes = ["slot 0x40 =", "", "`BattleQuery$$HasValidTargets`"]
    hauteurs = {len(off) for _i0, _b, off in P._blocs(lignes, 3) if _i0 == 0}
    assert hauteurs == {1}, (
        "le bloc demarrant sur la ligne du slot franchit la ligne vide (hauteurs %s)"
        % sorted(hauteurs))


def test_etage3bis_la_continuation_de_commentaire_est_franchie() -> None:
    """`\\s*` ne suffit pas : le depot reprend ses phrases derriere un `#`, un `//`, un `>`.

    C'est ce qui cachait la citation fausse jumelle de celle de #477-r30 (`displace.py`
    ecrivait « slot d'INTERFACE 0x4c = » puis, ligne suivante, `...GetMinimumTiles180Behind`).
    """
    bloc = ("#    ... rendue par le slot d'INTERFACE 0x4c =\n"      # [slot-attribution:refute]
            "#    `IdunBattle.Core.Services.BattleQuery$$GetMinimumTiles180Behind+0x38` -> ...")
    formes = P._COUPLES_ML["IBattleQuery"][0]
    vus = {(int(m.group("n%d" % k), 0), m.group("nom%d" % k))
           for k, rx in enumerate(formes) for m in rx.finditer(bloc)}
    assert (0x4C, "GetMinimumTiles180Behind") in vus, (
        "le couple a cheval sur une continuation `#` n'est pas capte -- vus : %s" % sorted(vus))
    #: Et le meme couple doit rester INVISIBLE au regime mono-ligne, sinon la mesure
    #: comparative fenetre=1 / fenetre=N ne veut plus rien dire.
    mono = P._COUPLES["IBattleQuery"][0]
    vus1 = {(int(m.group("n%d" % k), 0), m.group("nom%d" % k))
            for k, rx in enumerate(mono) for m in rx.finditer(bloc)}
    assert (0x4C, "GetMinimumTiles180Behind") not in vus1


def test_etage3bis_le_qualificatif_de_slot_est_insensible_a_la_CASSE() -> None:
    """« slot d'INTERFACE 0x4c » doit etre reconnu comme un slot.

    Sans ce cran le motif ne voyait meme pas le SLOT : la ligne partait en `sans_couple` et
    AUCUNE fenetre n'aurait pu la rattraper. 4 sites du depot ecrivent la forme majuscule.
    """
    for texte in ("slot d'interface 0x4c", "slot d'INTERFACE 0x4c", "slot d'Interface 0x4c"):
        m = re.search(P._SLOT % 0, texte)
        assert m is not None and int(m.group("n0"), 0) == 0x4C, (
            "« %s » n'est pas reconnu comme un slot" % texte)


# ------------- etage 3ter : l'APPEL ABSORBE et la PRIORITE AU MONO-LIGNE (#477-r36)


def test_etage3ter_lappel_du_slot_est_absorbe_dun_BLOC() -> None:
    """Le nom ecrit sur la MEME ligne que son slot ne doit pas rester bloque par ses ARGUMENTS.

    Le degat n'etait PAS « un couple manquant » : faute de pouvoir apparier le nom local, la
    forme C partait du slot pour attraper celui de la ligne SUIVANTE. Mesure (PR #737,
    `case-287r11`) : trois citations JUSTES du depot, **2 couples FAUX**, `master` ROUGE.

    Le couple d'exemple est VRAI (`IBattleQuery` 0x68 = `GetFreeSurroundingTiles`) -- ce fichier
    EST dans le corpus balaye.
    """
    bloc = ("    freeTiles = battleQuery.GetFreeSurroundingTiles(GetMainTile(caster, state), "
            "range, 0, 1);   # slot 104")
    rxs = P._COUPLES_ML["IBattleQuery"][0]
    vus = {(int(m.group("n%d" % k), 0), m.group("nom%d" % k))
           for k, rx in enumerate(rxs) for m in rx.finditer(bloc)}
    assert (0x68, "GetFreeSurroundingTiles") in vus, (
        "la liste d'arguments bloque encore le nom de sa propre ligne -- vus : %s" % sorted(vus))


def test_etage3ter_la_PRIORITE_AU_MONO_LIGNE_cede_au_plus_LOCAL() -> None:
    """Un couple ENJAMBANT cede si le MEME slot est deja apparie SUR SA LIGNE.

    C'est le symetrique du cran deja ecrit pour la forme B (« dans une enumeration verticale, le
    nom ecrit AVANT appartient a l'item precedent ») : le nom ecrit APRES appartient a l'item
    SUIVANT. La regle est CONSERVATRICE -- elle ne peut que retirer des enjambants, et seulement
    la ou une attribution locale du meme slot existe.
    """
    tables = P.lire_tsv()
    cits, ecartees, _rec = P.recolter(tables)
    assert ecartees.cedes_au_mono_ligne, (
        "aucun couple n'a cede -- soit le gisement est ferme (le dire), soit la regle ne mesure "
        "plus rien")
    #: Ce qui a cede ne doit PLUS etre dans les citations retenues.
    enjambants = {(c.fichier, c.ligne, c.iface, c.slot) for c in cits if c.ligne != c.ligne_nom}
    locaux = {(c.fichier, c.ligne, c.iface, c.slot) for c in cits if c.ligne == c.ligne_nom}
    assert not (enjambants & locaux), (
        "un couple enjambant coexiste avec une attribution locale du meme slot : %s"
        % sorted(enjambants & locaux)[:5])


def test_etage3ter_le_cran_est_IMPORTE_pas_recopie() -> None:
    """Les deux cliquets balayent le MEME depot : deux motifs jumeaux qui derivent l'un de
    l'autre rouvriraient ici le gisement que l'autre vient de fermer.

    Le foyer unique est `probe_477r24r1_slots_interface._appel`. Ce test le FIGE : c'est le seul
    endroit ou la regression « on a recopie le motif » se voit.
    """
    import probe_477r24r1_slots_interface as R24                            # noqa: PLC0415

    assert P._appel is R24._appel, (
        "l'absorption d'appel n'est plus le foyer unique -- elle a ete recopiee")
    assert P.PROFONDEUR_APPEL is R24.PROFONDEUR_APPEL


# ------------------------------- etages 4-5 : la derivation, si le metadata est la


def test_etage4_derivation_concorde_avec_lentree_versionnee(tables, lecteur) -> None:
    """Si le jeu est installe, la table versionnee doit etre CELLE du metadata."""
    reader, _ = lecteur
    for ns, iface, _ in P.INTERFACES:
        lu = {m.slot: (m.name, m.param_count, m.flags) for m in reader.type_methods(ns, iface)}
        assert lu == tables[iface], "%s diverge du metadata" % iface


def test_etage5_les_deux_derivations_rendent_la_MEME_table(lecteur) -> None:
    """CONTROLE CROISE : la grille des TYPES et les ANCRES DE NOM doivent concorder.

    `#477-r24-r1` localise la table d'une interface par des ancres de NOM (intersection des
    debuts de table compatibles) ; cette tranche la designe par le TYPE. Les deux chemins ne
    partagent que le fichier de metadata. S'ils divergeaient, l'un des deux serait faux -- et
    rien d'autre ne le dirait, puisque chacun se verifie contre sa PROPRE entree versionnee.
    """
    reader, _ = lecteur
    par_ancres = {m.slot: (m.name, m.param_count) for m in reader.interface_table(R24.ANCRES)}
    par_type = {m.slot: (m.name, m.param_count)
                for m in reader.type_methods("Core.Services", "IOperationProcessor")}
    assert par_type == par_ancres, (
        "les deux derivations divergent sur `IOperationProcessor` : %d vs %d slots"
        % (len(par_type), len(par_ancres)))
    assert len(par_type) == 150, "150 slots attendus, %d lus" % len(par_type)


def test_etage5_la_grille_des_types_refuse_sans_assez_dancres(lecteur) -> None:
    """Le refus qui evite un PAS faux -- vu MORDRE.

    Deux ancres rendent leur ECART, qui peut etre un multiple du pas ; il en faut trois pour
    que le PGCD le designe. Le module doit REFUSER, pas rendre une grille au petit bonheur.
    """
    reader, il2cpp_metadata = lecteur
    with pytest.raises(il2cpp_metadata.MetadataRefused, match="au moins 3"):
        reader.locate_types([("Core.Services", "OperationProcessor", [("Init", 4)]),
                             ("IdunBattle.Core", "MatchState", [("AddDeath", 5)])])


def test_etage5_un_type_inconnu_est_REFUSE_pas_devine(lecteur) -> None:
    """Un nom de type absent doit LEVER, jamais rendre une table vide qui se lirait vert."""
    reader, il2cpp_metadata = lecteur
    with pytest.raises(il2cpp_metadata.MetadataRefused, match="NON MESURE"):
        reader.type_methods("IdunBattle.Core.Services", "IQuiNExistePas")
