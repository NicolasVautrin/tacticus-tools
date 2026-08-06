"""#477-r24-r1 -- CLIQUET du mapping slot <-> methode de `Core.Services.IOperationProcessor`.

    python -m pytest scripts/python/tests/engine/test_477r24r1_slots_interface_offline.py -q

Ce que ce fichier empeche de revenir :

* qu'une citation « slot X = NomDeMethode » reparaisse FAUSSE dans le depot (etage 3, perimetre
  DERIVE d'un `git ls-files` -- aucune liste blanche de fichiers) ;
* qu'un renumerotage silencieux passe pour un vert. L'etage 2 FIGE les couples que cette tranche
  a tranches, mesures a la conversion. Il n'est pas redondant avec l'etage 1 : celui-ci compare
  l'entree versionnee a elle-meme et redevient vert des qu'on la regenere, alors que les valeurs
  ECRITES dans les fiches, elles, auraient change sans que personne ne le voie ;
* qu'un corpus vide passe pour un vert (etage 0 : le balayage assertionne son propre NON-VIDE) ;
* que l'appariement RETOMBE de la FENETRE a la LIGNE (etage 3bis, #477-r32). Le regime « slot et
  nom ADJACENTS » ecartait 166 lignes du meme patron ; les crans qui l'ouvrent sont gardes UN PAR
  UN, et le mutant `enjambants-decales` est INERTE a `fenetre=1` -- c'est ce qui prouve qu'il
  garde l'ELARGISSEMENT et pas l'appariement en general ;
* qu'un slot designe par son NOM SEUL nomme une methode qui n'existe pas (etage 5, #477-r32).
  C'est cette forme-la qui portait la seule faute du corpus : `components.py` ecrivait
  « le slot `ApplyStatModifiers` de l'`OperationProcessor` »  [slot-attribution:refute]
  alors que le slot est `TransformUnit` (0x66), et qu'`ApplyStatModifiers` est ce que
  l'Operation appelle DEUX niveaux plus bas.
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

import probe_477r24r1_slots_interface as P                             # noqa: E402


#: Les couples TRANCHES par cette tranche, figes a l'ordinal MESURE dans le metadata du build
#: `rnca9r7q6c`. Chacun est atteste par au moins un call-site decompile dont l'ARITE concorde.
#:
#: Les quatre premiers sont ceux que les deux lectures publiees se disputaient : elles avaient
#: RAISON TOUTES LES DEUX, et c'est la grandeur par laquelle on les comparait -- une « position
#: dans la classe » -- qui n'indexait rien.
COUPLES_FIGES = {
    0x12: ("StartMatch", 0),                    # `<Visit>b__18_0`            -- lecture #477-r20
    0x16: ("ContinueTurnPhase", 3),             # `StartMatchOperation`       -- lecture #477-r20
    0x20: ("VerifyAutomaticTurnEnd", 2),        # `RunPhase`                  -- lecture #477-r20
    0x57: ("HealUnit", 6),                      # `HealBehaviour$$Execute`    -- lecture #477-r24
    0x60: ("KillUnit", 3),                      # `<VerifyDeaths>b__0`        -- lecture #477-r24
    0x61: ("DestroyMachine", 2),                # `<VerifyDeaths>b__0`        -- lecture #477-r24
    0x63: ("ReviveUnit", 1),                    # `KillUnitOperation$$Execute`, branche `else`
    0x55: ("UnregisterEntityFromTriggers", 2),  # `<VerifyRemovedUnits>b__0`  -- corrige #477-r19
    0x06: ("RemoveUnit", 3),
    0x26: ("AddTrait", 3),
    0x51: ("EvaluateAbilities", 5),
    0x7E: ("SetUnitPosition", 3),               # corrige `revive.py` (y disait `MoveUnit`)
    #: #477-r32 : la seule faute du corpus. `components.py` nommait ce slot `ApplyStatModifiers`,
    #: qui n'est a AUCUN des 150. La chaine est LUE au decompile, sur TROIS call-sites qui
    #: prennent tous le meme slot : `ReviveUnitOperation$$SetHealth`,
    #: `SetupGameOperation$$ApplyModifiers` et `TransformActorToConfigIdOperation$$UpdateStats`
    #: -> `Core.Services.OperationProcessor$$TransformUnit(entity, statModifiers, isHidden)`
    #: -> `TransformUnitOperation$$Execute` -> `UnitExtensions$$ApplyStatModifiers`.
    0x66: ("TransformUnit", 3),
}

#: Nombre de slots de l'interface sur ce build. Fige : une table qui RETRECIT en silence est
#: exactement ce qui ferait passer une citation hors bornes pour « slot inconnu, on ignore ».
NB_SLOTS = 150


class _MethodDefSimulee:
    """Le strict minimum que `P.jouer` lit d'une `MethodDef` : slot, nom, arite.

    Il sert a rendre l'etage 2 observable HORS metadata (le jeu n'est pas forcement installe).
    Ce n'est pas un substitut de la derivation -- l'etage 4, lui, confronte la VRAIE.
    """

    __slots__ = ("slot", "name", "param_count")

    def __init__(self, slot: int, name: str, param_count: int) -> None:
        self.slot, self.name, self.param_count = slot, name, param_count


@pytest.fixture(scope="module")
def table() -> dict[int, tuple[str, int]]:
    return P.lire_tsv()


@pytest.fixture(scope="module")
def recolte():
    """La recolte au regime EN SERVICE (fenetre = `P.FENETRE`)."""
    return P.recolter()


@pytest.fixture(scope="module")
def citations(recolte) -> list[P.Citation]:
    return recolte[0]


@pytest.fixture(scope="module")
def noms_seuls(recolte) -> list[P.CitationNom]:
    return recolte[1]


@pytest.fixture(scope="module")
def recolte_fenetre1():
    """La recolte a `fenetre=1` -- le regime d'avant #477-r32, garde comme REFERENCE."""
    return P.recolter(fenetre=1)


@pytest.fixture(scope="module")
def localise():
    """Un `MetadataReader` deja localise -- la localisation coute ~15 s, on la fait UNE fois."""
    import build_pin
    import il2cpp_metadata
    from symbols_layout import build_dir

    try:
        meta = build_pin.global_metadata()
    except build_pin.BuildPinRefused as exc:
        pytest.skip("metadata IL2CPP non disponible (entree hors depot) : %s"
                    % str(exc).splitlines()[0])
    reader = il2cpp_metadata.read(meta)
    reader.locate(il2cpp_metadata.class_method_order(
        build_dir() / "frida" / "methods.tsv", P.KLASS))
    return reader, il2cpp_metadata


# --------------------------------------------------------- etage 0 : le corpus est NON VIDE


def test_etage0_le_balayage_voit_quelque_chose(citations: list[P.Citation]) -> None:
    """Un balayage qui ne visite rien rend 0 desaccord et passe pour vert. On l'interdit."""
    assert P.fichiers_balayes(), "perimetre VIDE : `git ls-files` n'a rien rendu"
    assert len(citations) >= 20, (
        "seulement %d attestation(s) recoltee(s) -- le corpus a fondu, ou les motifs de "
        "reconnaissance ne matchent plus. Un cliquet sur un corpus vide est un faux vert."
        % len(citations))
    assert len({c.fichier for c in citations}) >= 10, (
        "attestations concentrees sur %d fichier(s) seulement"
        % len({c.fichier for c in citations}))


# ------------------------------------------------- etage 1 : l'entree versionnee est saine


def test_etage1_table_contigue_et_complete(table: dict[int, tuple[str, int]]) -> None:
    assert len(table) == NB_SLOTS, "table de %d slots, %d attendus" % (len(table), NB_SLOTS)
    assert sorted(table) == list(range(NB_SLOTS)), (
        "les slots ne forment pas 0..%d contigus -- le slot n'indexerait donc plus une table "
        "contigue, et toute lecture par index serait fausse" % (NB_SLOTS - 1))
    assert all(nom and nargs >= 0 for nom, nargs in table.values())


# ------------------------------------------- etage 2 : les couples TRANCHES sont FIGES


@pytest.mark.parametrize("slot,attendu", sorted(COUPLES_FIGES.items()))
def test_etage2_couple_fige(table: dict[int, tuple[str, int]], slot: int,
                            attendu: tuple[str, int]) -> None:
    assert table[slot] == attendu, (
        "slot 0x%02x : la table dit %s/%d, la tranche avait MESURE %s/%d. Si le build a "
        "renumerote, ce ne sont pas seulement les tables qu'il faut regenerer -- ce sont "
        "toutes les fiches qui citent ces slots." % (slot, table[slot][0], table[slot][1],
                                                     attendu[0], attendu[1]))


def test_etage2_les_deux_lectures_publiees_sont_toutes_deux_justes(
        table: dict[int, tuple[str, int]]) -> None:
    """Le resultat de la tranche, ecrit comme une assertion.

    `#477-r24` concluait que les couples de `#477-r20` etaient « incompatibles » avec les siens.
    Ils ne le sont pas : les cinq tiennent ENSEMBLE dans la meme table.
    """
    lecture_a = {0x57: "HealUnit", 0x60: "KillUnit", 0x61: "DestroyMachine", 0x63: "ReviveUnit"}
    lecture_b = {0x16: "ContinueTurnPhase", 0x20: "VerifyAutomaticTurnEnd", 0x12: "StartMatch"}
    for slot, nom in {**lecture_a, **lecture_b}.items():
        assert table[slot][0] == nom, "slot 0x%02x != %s" % (slot, nom)
    assert not set(lecture_a) & set(lecture_b), "les deux lectures doivent porter sur des "\
        "slots DISJOINTS -- sinon le test ne prouve pas leur compatibilite"


def test_etage2_le_slot_du_retrait_nest_pas_remove_unit(
        table: dict[int, tuple[str, int]]) -> None:
    """#477-r24-r2 : `<VerifyRemovedUnits>b__0` n'appelle PAS `RemoveUnit`.

    Le site passe DEUX arguments ; `RemoveUnit` en prend TROIS. C'est l'arite qui tranche, et
    c'est elle qu'on garde : les deux noms doivent rester distinguables par ce seul critere.
    """
    assert table[0x55] == ("UnregisterEntityFromTriggers", 2)
    assert table[0x06] == ("RemoveUnit", 3)
    assert table[0x55][1] != table[0x06][1], (
        "les deux methodes ont desormais la meme arite -- le discriminant qui a tranche "
        "#477-r24-r2 a disparu, et l'attribution redevient indecidable par ce chemin")


# --------------------------------------- etage 3 : aucune citation FAUSSE dans le depot


def test_etage3_aucune_citation_fausse(table: dict[int, tuple[str, int]],
                                       citations: list[P.Citation]) -> None:
    faux_nom, faux_arite = P.confronter(citations, table)
    assert not faux_nom, "citation(s) au NOM faux :\n  " + "\n  ".join(faux_nom)
    assert not faux_arite, "citation(s) a l'ARITE fausse :\n  " + "\n  ".join(faux_arite)


@pytest.mark.parametrize("mutant", sorted(P.MUTANTS))
def test_etage3_la_garde_mord(table: dict[int, tuple[str, int]],
                              citations: list[P.Citation],
                              noms_seuls: list[P.CitationNom], mutant: str) -> None:
    """Contre-epreuve : chaque mutant doit faire bouger au moins un compteur.

    Une garde qu'on n'a jamais vue ROUGE ne prouve rien. `slot-decale` et `table-tronquee`
    frappent l'appariement, `nom-permute` l'attribution (sur des slots DERIVES des citations
    reelles, sinon le mutant serait inerte), `arite-fausse` la signature, `enjambants-decales`
    l'ELARGISSEMENT lui-meme.
    """
    base = P.jouer(table, citations, None, noms_seuls)
    mt, mc = P.muter(table, mutant, citations)
    mute = P.jouer(mt, mc, None, noms_seuls)
    assert mute != base, "le mutant `%s` n'a RIEN change (%s) -- il est inerte" % (mutant, base)


def test_etage3_chaque_etage_a_son_mutant(table: dict[int, tuple[str, int]],
                                          citations: list[P.Citation],
                                          noms_seuls: list[P.CitationNom]) -> None:
    """Chacun des QUATRE compteurs de `jouer` doit etre bouge par AU MOINS un mutant.

    Sans ce test, un etage neuf peut entrer sans contre-epreuve : les mutants existants
    continueraient de « mordre » sur les autres colonnes et la garde passerait pour complete.
    Mesure #477-r32 : l'etage 5 (NOM SEUL) est arrive ainsi, et n'etait garde par rien tant
    qu'il n'etait pas dans le tuple rendu par `jouer`.

    ⚠ LA DERIVATION EST SIMULEE DEPUIS L'ENTREE VERSIONNEE, et c'est ce qui rend la colonne 0
    (l'ecart derivation/versionne) observable SANS le jeu installe. Passer `None` la fige a 0
    et le test se lirait « aucun mutant ne garde l'etage 2 » alors que tous le gardent.
    """
    derive = [_MethodDefSimulee(s, n, k) for s, (n, k) in sorted(table.items())]
    base = P.jouer(table, citations, derive, noms_seuls)
    bouges = set()
    for mutant in P.MUTANTS:
        mt, mc = P.muter(table, mutant, citations)
        mute = P.jouer(mt, mc, derive, noms_seuls)
        bouges |= {i for i, (a, b) in enumerate(zip(base, mute)) if a != b}
    assert bouges == set(range(len(base))), (
        "les colonnes %s de `jouer` ne sont bougees par AUCUN mutant -- elles n'ont pas de "
        "contre-epreuve" % sorted(set(range(len(base))) - bouges))


# ------------------------------------ etage 3bis : la FENETRE elle-meme (#477-r32)


def test_etage3bis_la_fenetre_APPORTE_des_couples_enjambants(
        citations: list[P.Citation]) -> None:
    """La fenetre doit voir ce que `fenetre=1` ne voyait pas -- sinon elle ne sert a rien."""
    assert P.FENETRE >= 2, "la fenetre est retombee a 1 -- le gisement de #477-r32 se rouvre"
    enjambants = [c for c in citations if c.ligne != c.ligne_nom]
    assert len(enjambants) >= 12, (
        "seulement %d couple(s) ENJAMBANT(S) sur %d -- l'appariement en fenetre ne mord plus "
        "(mesure a 16 le 2026-08-06)" % (len(enjambants), len(citations)))
    assert len({c.fichier for c in enjambants}) >= 10, (
        "les couples enjambants sont concentres sur %d fichier(s) -- ce n'est plus un gisement"
        % len({c.fichier for c in enjambants}))


def test_etage3bis_la_fenetre_RETRECIT_la_zone_aveugle(recolte, recolte_fenetre1) -> None:
    """Un cliquet dont la zone aveugle ne retrecit pas est un inventaire, pas une garde."""
    _ref_cits, _ref_noms, ref = recolte_fenetre1
    _cits, _noms, ecartees = recolte
    assert ecartees.sans_couple < ref.sans_couple, (
        "zone aveugle INCHANGEE : %d ligne(s) sans couple a fenetre=1 comme a fenetre=%d"
        % (ref.sans_couple, P.FENETRE))
    assert ref.sans_couple - ecartees.sans_couple >= 5, (
        "la fenetre ne recupere que %d ligne(s) (%d -> %d) -- mesure a 8 le 2026-08-06"
        % (ref.sans_couple - ecartees.sans_couple, ref.sans_couple, ecartees.sans_couple))


def test_etage3bis_fenetre1_reste_le_regime_precedent(recolte_fenetre1) -> None:
    """`fenetre=1` doit RESTER exactement l'ancien regime : 0 couple enjambant.

    Sans cette assertion, un elargissement accidentel du regime de base passerait pour un gain
    de la fenetre, et la comparaison des deux regimes ne voudrait plus rien dire.
    """
    ref_cits, _ref_noms, _ref = recolte_fenetre1
    assert all(c.ligne == c.ligne_nom for c in ref_cits), (
        "a fenetre=1, un couple s'etale sur deux lignes -- le regime de base a fui")


def test_etage3bis_le_mutant_des_enjambants_est_INERTE_a_fenetre1(
        table, citations: list[P.Citation], noms_seuls, recolte_fenetre1) -> None:
    """Le mutant qui garde la fenetre doit MORDRE en fenetre et NE RIEN FAIRE a fenetre=1.

    C'est ce qui prouve qu'il garde bien l'ELARGISSEMENT, et pas l'appariement en general : les
    quatre mutants herites mordent dans les deux regimes, donc aucun d'eux ne dirait qu'on a
    perdu la fenetre.
    """
    ref_cits, _ref_noms, _ref = recolte_fenetre1
    mt, mc = P.muter(table, "enjambants-decales", citations)
    assert P.jouer(mt, mc, None, noms_seuls) != P.jouer(table, citations, None, noms_seuls), (
        "le mutant `enjambants-decales` ne mord PAS en fenetre -- la fenetre n'est pas gardee")
    with pytest.raises(SystemExit, match="IMPOSSIBLE"):
        #: A `fenetre=1` il n'existe AUCUN couple enjambant : le mutant n'a rien a muter, et il
        #: REFUSE au lieu de rendre une mutation vide qui passerait pour appliquee.
        P.muter(table, "enjambants-decales", ref_cits)


def test_etage3bis_le_bloc_ne_franchit_pas_une_ligne_VIDE() -> None:
    """Une ligne vide est une frontiere de paragraphe -- cran mesure par #477-r30.

    ⚠ Le couple d'exemple est VRAI (`0x65` = `MoveUnit`), et ce n'est pas cosmetique : ce
    fichier EST dans le corpus balaye. Un exemple faux y ferait rougir le probe sur son propre
    cliquet le jour ou un cran s'ouvrirait -- exactement le vice que l'exclusion du probe
    lui-meme evite pour ses regex de documentation.
    """
    lignes = ["processor slot 0x65 =", "", "`OperationProcessor$$MoveUnit`"]
    hauteurs = {len(off) for i0, _b, off in P._blocs(lignes, 3) if i0 == 0}
    assert hauteurs == {1}, (
        "le bloc demarrant sur la ligne du slot franchit la ligne vide (hauteurs %s)"
        % sorted(hauteurs))


def test_etage3bis_la_coupure_entre_QUALIFICATEUR_et_NOM_est_franchie() -> None:
    """La forme REELLE de ce corpus : le qualificateur finit la ligne, le nom ouvre la suivante.

    `turnflow.py` et `runner.py` ecrivent « slot `IOperationProcessor` 0x21 =
    `Core.Services.OperationProcessor$$` » puis, ligne suivante, `VerifyUnitsTurnFinished`.
    C'est une coupure DIFFERENTE de celle mesuree par #477-r30 (qui tombait entre le signe egal
    et le qualificateur) : elle a son propre cran, et il faut donc son propre test.
    """
    bloc = ("# invoque le slot `IOperationProcessor` 0x21 = `Core.Services.OperationProcessor$$\n"
            "# VerifyUnitsTurnFinished` (AUCUN argument)")
    vus = {(int(m.group("n%d" % k), 0), m.group("nom%d" % k))
           for k, rx in enumerate(P.RE_COUPLES_ML) for m in rx.finditer(bloc)}
    assert (0x21, "VerifyUnitsTurnFinished") in vus, (
        "le couple a cheval sur la coupure qualificateur/nom n'est pas capte -- vus : %s"
        % sorted(vus))
    mono = {(int(m.group("n%d" % k), 0), m.group("nom%d" % k))
            for k, rx in enumerate(P.RE_COUPLES) for m in rx.finditer(bloc)}
    assert (0x21, "VerifyUnitsTurnFinished") not in mono, (
        "le regime mono-ligne voit le couple a cheval -- la comparaison des deux regimes ne "
        "mesure plus rien")


def test_etage3bis_le_recepteur_entre_slot_et_numero_est_reconnu() -> None:
    """« slot `IOperationProcessor` 0x21 », « slot processor 0x76 » sont des SLOTS.

    Sans ce cran le motif ne voyait meme pas le NUMERO : la ligne partait en `sans_couple` et
    AUCUNE fenetre n'aurait pu la rattraper. C'est le pendant exact du « slot d'INTERFACE »
    mesure par #477-r30 sur l'autre cliquet.
    """
    for texte, attendu in (("slot `IOperationProcessor` 0x21", 0x21),
                           ("slot IOperationProcessor 0x46", 0x46),
                           ("slot processor 0x76", 0x76),
                           ("slot `Core.Services.OperationProcessor` 0x23", 0x23),
                           ("slot d'interface 0x4c", 0x4C),
                           ("slot d'INTERFACE 0x4c", 0x4C),
                           ("slot +6", 6),
                           ("vslot 0x60", 0x60)):
        m = re.search(P._SLOT % 0, texte)
        assert m is not None and int(m.group("n0"), 0) == attendu, (
            "« %s » n'est pas reconnu comme le slot 0x%x" % (texte, attendu))


def test_etage3bis_la_FLECHE_reste_licite_dans_le_sens_slot_PUIS_nom() -> None:
    """La FLECHE n'est un RENVOI que dans le sens « nom PUIS slot ».

    #477-r25 l'excluait des DEUX sens, et ce cran, importe tel quel, faisait PERDRE une citation
    JUSTE de ce corpus (`backlog.md` : « `FinishAttack` slot 0x3b -> le meme nom qualifie »).
    Dans « slot PUIS nom » la fleche marque une RESOLUTION, donc exactement l'attribution
    cherchee ; dans l'autre sens elle marque un ENCHAINEMENT d'appels, et le cran tient.
    """
    resolution = "`FinishAttack` slot 0x3b → `OperationProcessor$$FinishAttack` → suite"
    vus = {(int(m.group("n%d" % k), 0), m.group("nom%d" % k))
           for k, rx in enumerate(P.RE_COUPLES_ML) for m in rx.finditer(resolution)}
    assert (0x3B, "FinishAttack") in vus, (
        "le sens « slot PUIS nom » perd son couple a cause de la fleche -- vus : %s"
        % sorted(vus))
    #: ... et le sens INVERSE doit rester bloque : la fleche y designe l'APPELE.
    enchainement = "`OperationProcessor$$FinishAttack` -> slot 0x3c"
    vus_b = {(int(m.group("n2"), 0), m.group("nom2"))
             for m in P.RE_COUPLES_ML[2].finditer(enchainement)}
    assert (0x3C, "FinishAttack") not in vus_b, (
        "la forme « nom PUIS slot » franchit la fleche -- elle attribue au slot APPELE le nom "
        "de la methode APPELANTE")


def test_etage3bis_un_segment_de_chemin_nest_pas_un_nom_de_methode() -> None:
    """`slot 0x46 -> `IdunBattle.Operations.DiscardHitOperation`` ne nomme PAS `IdunBattle`.

    Le qualificateur etant OPTIONNEL en forme A, le moteur y renonce et attrape la TETE DU
    NAMESPACE. Mesure #477-r32 : 4 sites, tous artefacts, tous ranges parmi les « noms inconnus
    de l'interface » -- exactement la ou une VRAIE citation fausse doit sortir.
    """
    bloc = "-> slot IOperationProcessor 0x46 -> `IdunBattle.Operations.DiscardHitOperation$$Execute`"
    vus = {m.group("nom%d" % k) for k, rx in enumerate(P.RE_COUPLES_ML) for m in rx.finditer(bloc)}
    assert "IdunBattle" not in vus, "la tete du namespace est prise pour un nom de methode"


def test_etage3bis_le_residu_est_VENTILE_et_la_somme_vaut_le_total(table) -> None:
    """Un compte qui ne dit pas SA CAUSE est un inventaire (#477-r34).

    Les trois causes forment une PARTITION : leur somme doit valoir `sans_couple`, sinon une
    ligne tomberait dans un tas que personne ne regarde -- exactement le vice qu'un recenseur a
    liste blanche de motifs reproduit a chaque fois.
    """
    _cits, _noms, ecartees = P.recolter(
        noms_interface=frozenset(v[0] for v in table.values()))
    vent = ecartees.ventilation
    assert vent is not None, "ventilation PAS MESUREE alors que la table est fournie"
    assert set(vent) == set(P.CAUSES), "les causes ne sont pas celles declarees : %s" % sorted(vent)
    assert sum(len(v) for v in vent.values()) == ecartees.sans_couple, (
        "la somme des causes (%d) ne vaut PAS le total ecarte (%d) -- ce n'est plus une partition"
        % (sum(len(v) for v in vent.values()), ecartees.sans_couple))
    assert vent["nom_ecarte_par_un_cran"], (
        "aucune ligne dans le tas qui est LE gisement -- soit il est ferme (le dire), soit le "
        "critere ne mesure plus rien")


def test_etage3bis_la_ventilation_est_TRI_ETAT() -> None:
    """Sans table de noms, la ventilation vaut `None` -- PAS MESUREE, jamais un dict vide.

    Un dictionnaire de listes vides se lirait « aucune ligne dans aucune cause », c'est-a-dire
    « residu ferme », alors que rien n'aurait ete mesure.
    """
    _cits, _noms, ecartees = P.recolter(fenetre=1)
    assert ecartees.ventilation is None


# ------------------------- etage 3ter : les QUATRE formes de #477-r36 et leurs crans


def test_etage3ter_les_formes_r36_APPORTENT_des_couples(citations: list[P.Citation]) -> None:
    """Les formes neuves doivent rapporter ce que A/B/C ne voyaient pas -- sinon elles ne
    servent a rien, et le mutant qui les garde n'aurait rien a muter.
    """
    neuves = [c for c in citations if c.forme >= 3 or c.appel_absorbe]
    assert len(neuves) >= 20, (
        "seulement %d couple(s) propre(s) a #477-r36 sur %d -- l'appel absorbe / la resolution "
        "commentee / le placeholder ne mordent plus (mesure a 30 le 2026-08-06)"
        % (len(neuves), len(citations)))
    assert len({c.forme for c in neuves}) >= 3, (
        "les couples neufs sortent tous des memes formes (%s) -- les autres sont mortes"
        % sorted({c.forme for c in neuves}))


def test_etage3ter_le_regime_historique_ne_porte_AUCUNE_forme_neuve() -> None:
    """`historique=True` doit rendre EXACTEMENT l'etat d'avant : ni forme D/E/F, ni appel absorbe.

    Sans cette assertion, la REFERENCE fuit : le gain des formes neuves se confondrait avec
    celui de la fenetre, et le mutant qui doit y etre inerte mordrait quand meme.
    """
    cits, _ns, _ec = P.recolter(historique=True)
    assert cits, "le regime historique ne rend AUCUN couple -- il ne peut servir de reference"
    assert all(c.forme <= 2 and not c.appel_absorbe for c in cits), (
        "le regime historique porte une forme neuve : %s"
        % sorted({(c.forme, c.appel_absorbe) for c in cits}))


def test_etage3ter_le_mutant_des_formes_r36_est_INERTE_en_regime_historique(
        table, citations: list[P.Citation], noms_seuls) -> None:
    """Il doit MORDRE en service et REFUSER en regime historique.

    C'est ce qui prouve qu'il garde l'ELARGISSEMENT et non l'appariement en general : les cinq
    mutants herites mordent dans les deux regimes, donc aucun ne dirait qu'on a perdu les formes
    de #477-r36 (meme mesure que celle de #477-r30 sur ses quatre mutants).
    """
    hist, _hn, _he = P.recolter(historique=True)
    mt, mc = P.muter(table, "formes-r36-decalees", citations)
    assert P.jouer(mt, mc, None, noms_seuls) != P.jouer(table, citations, None, noms_seuls), (
        "le mutant `formes-r36-decalees` ne mord PAS -- les formes neuves ne sont pas gardees")
    with pytest.raises(SystemExit, match="IMPOSSIBLE"):
        #: Aucun couple ne porte le cran : le mutant REFUSE plutot que de rendre une mutation
        #: vide qui passerait pour appliquee.
        P.muter(table, "formes-r36-decalees", hist)


def test_etage3ter_lappel_du_slot_est_absorbe_dun_BLOC() -> None:
    """Un slot s'ecrit sous forme d'APPEL, et sa liste d'arguments porte les `(`, `)`, `,`, `:`,
    `;` que le remplissage exclut. Elle est absorbee d'un bloc EQUILIBRE et COLLE.

    Le couple d'exemple est VRAI (`5` = `AddUnit`, 5 arguments) -- ce fichier EST dans le corpus
    balaye, un exemple faux y ferait rougir le cliquet sur son propre artefact.
    """
    bloc = ("processor.AddUnit(unitId, unitFeetTileIds, playerId, spawnSource, options);"
            "   // slot 5 d'IOperationProcessor")
    vus = {(int(m.group("n%d" % k), 0), m.group("nom%d" % k))
           for k, rx in enumerate(P.RE_COUPLES_ML) for m in rx.finditer(bloc)}
    assert (5, "AddUnit") in vus, (
        "la liste d'arguments n'est pas absorbee -- vus : %s" % sorted(vus))
    hist = P._regex_couples(True, historique=True)
    vus_h = {(int(m.group("n%d" % k), 0), m.group("nom%d" % k))
             for k, rx in enumerate(hist) for m in rx.finditer(bloc)}
    assert (5, "AddUnit") not in vus_h, (
        "le regime historique voit deja ce couple -- la reference ne mesure plus rien")


def test_etage3ter_la_resolution_commentee_exige_son_MARQUEUR() -> None:
    """Apres `#`/`//`, un nom ne RESOUT le slot que s'il porte un marqueur : `=` avant, `->`/`→`
    ou sa signature apres.

    Sans ce cran, `processor.<slot 0x11>(...)  # RemoveEffectOperation` -- ou le commentaire
    nomme la CLASSE vers laquelle le slot aiguille -- sortirait en citation FAUSSE. C'est un
    site REEL (`engine/runner/operations/remove_effects.py`), et le seul couple que le
    relachement `resolution-marquee` fait apparaitre.
    """
    captes = ("<IOperationProcessor slot 0x76>(unit)   # = MarkUnitAsNoActionAvailable (POSE)",
              "<IOperationProcessor slot 0x77>(unit);  // MarkUnitAsActionAvailable -> RETRAIT",
              "IOperationProcessor.<slot 0x23>(spawned, true)   # FinishUnitTurn(u, isTerminated)")
    for bloc in captes:
        vus = {(int(m.group("n%d" % k), 0), m.group("nom%d" % k))
               for k, rx in enumerate(P.RE_COUPLES_ML) for m in rx.finditer(bloc)}
        assert any(s in {0x76, 0x77, 0x23} for s, _n in vus), (
            "la resolution commentee n'est pas captee sur « %s » -- vus : %s" % (bloc, sorted(vus)))
    #: ... et le commentaire SANS marqueur ne resout rien.
    nu = "processor.<slot 0x11>(matchState.GetEntity(effectId))   # RemoveEffectOperation"
    vus_nu = {m.group("nom%d" % k)
              for k, rx in enumerate(P.RE_COUPLES_ML) for m in rx.finditer(nu)}
    assert "RemoveEffectOperation" not in vus_nu, (
        "un commentaire libre est pris pour une resolution -- il nomme la CLASSE appelee")


def test_etage3ter_le_nom_du_placeholder_exige_sa_FERMETURE() -> None:
    """`<slot 0x3c AttackDamage>` : tout ce qui est ENTRE les chevrons designe le slot.

    Le cran n'est pas « le nom est colle au numero » mais « le placeholder est FERME » : c'est
    la fermeture qui empeche la prose d'entrer, exactement comme la tournure « de l'<recepteur> »
    sur l'etage NOM SEUL.
    """
    bloc = "result.Combine( processor.<slot 0x3c AttackDamage>(caster, t, abilityOrEffect, opts) )"
    vus = {(int(m.group("n%d" % k), 0), m.group("nom%d" % k))
           for k, rx in enumerate(P.RE_COUPLES_ML) for m in rx.finditer(bloc)}
    assert (0x3C, "AttackDamage") in vus, (
        "le nom ecrit dans le placeholder n'est pas capte -- vus : %s" % sorted(vus))
    ouvert = "le slot 0x3c AttackDamage est celui du degat"
    vus_o = {(int(m.group("n%d" % k), 0), m.group("nom%d" % k))
             for k, rx in enumerate(P.RE_COUPLES_ML) for m in rx.finditer(ouvert)}
    assert (0x3C, "AttackDamage") not in vus_o, (
        "le placeholder NON FERME est accepte -- la prose « slot 0x12 SANS ARGUMENT » entrerait")


def test_etage3ter_la_resolution_en_prose_exige_le_DELIMITEUR_de_code() -> None:
    """« <slot 0x16>(…) c'est-a-dire `ContinueTurnPhase` » est une attribution ; « -- AVANT
    ContinueTurnPhase » n'en est pas une.

    Le discriminant est le delimiteur de code OUVRANT, et c'est une MESURE : sans lui, le mot en
    capitales `AVANT` d'un site REEL (`case-477r22-bloc2-tour.md`) devient un « nom de methode »
    absent de l'interface, donc une citation FAUSSE.
    """
    resolu = "`processor.<slot 0x16>(TurnStage.Start, false, true)` c'est-a-dire `ContinueTurnPhase`."
    vus = {(int(m.group("n%d" % k), 0), m.group("nom%d" % k))
           for k, rx in enumerate(P.RE_COUPLES_ML) for m in rx.finditer(resolu)}
    assert (0x16, "ContinueTurnPhase") in vus, (
        "la resolution en prose n'est pas captee -- vus : %s" % sorted(vus))
    prose = "processor.<slot 0x2f>(RefreshEffectOptions{8, null});   -- AVANT ContinueTurnPhase"
    vus_p = {m.group("nom%d" % k)
             for k, rx in enumerate(P.RE_COUPLES_ML) for m in rx.finditer(prose)}
    assert "AVANT" not in vus_p, (
        "un mot de PROSE en capitales est pris pour un nom de methode -- vus : %s" % sorted(vus_p))


def test_etage3ter_le_recepteur_APRES_le_numero_est_reconnu() -> None:
    """« le slot 0x66 DE L'`IOperationProcessor` » -- la symetrique du cran de #477-r32.

    C'est la tournure meme dont l'etage NOM SEUL a fait son discriminant. Sans elle, la
    resolution qui SUIT le recepteur reste hors d'atteinte, et c'est ce qui cachait
    l'attribution du slot `0x66`, celle-la meme que #477-r32 declarait CONFRONTABLE.
    """
    for texte in ("le slot 0x66 de l'`IOperationProcessor`",
                  "le slot 0x66 de `Core.Services.OperationProcessor`",
                  "slot 0x66 of IOperationProcessor"):
        m = re.search(P._SLOT % 0, texte)
        assert m is not None and int(m.group("n0"), 0) == 0x66, (
            "« %s » n'est pas reconnu comme le slot 0x66" % texte)
        assert m.end() == len(texte), (
            "le recepteur ecrit APRES le numero n'est pas absorbe : « %s » s'arrete a %d"
            % (texte, m.end()))


def test_etage3ter_larite_se_confronte_sur_lappel_ABSORBE(citations: list[P.Citation]) -> None:
    """L'appel absorbe rend l'etage ARITE applicable aux formes ou l'appel PRECEDE le nom.

    C'est le cran qui a trouve la faute de #477-r24-r2 (`RemoveUnit`, 3 arguments, 2 au site) ;
    jusqu'ici il ne pouvait juger que les sites montrant leurs arguments APRES le couple.
    """
    par_absorption = [c for c in citations if c.appel_absorbe and c.args is not None]
    assert len(par_absorption) >= 10, (
        "seulement %d citation(s) dont l'arite vient de l'appel ABSORBE -- l'etage 4 ne s'est pas "
        "elargi (mesure a 25 le 2026-08-06)" % len(par_absorption))


def test_etage3ter_la_PROFONDEUR_dimbrication_est_suffisante() -> None:
    """Un appel plus PROFOND que ce que le motif suit n'est PAS absorbe -- et le degat n'est pas
    « un couple manquant » mais un couple FAUX : le nom de la ligne reste bloque, et le slot va
    chercher celui de la ligne SUIVANTE.

    Le cas est REEL et mesure sur le corpus voisin (`probe_477r25`, site `case-287r11`) :
    `battleQuery.GetAllAliveUnits(Nullable<int>(GetCurrentOwnerEntityId(caster)))` compte
    3 niveaux. `--profondeur` re-derive la courbe, plate des p = 2 sur CE corpus.
    """
    assert P.PROFONDEUR_APPEL >= 3, (
        "la profondeur est retombee a %d -- un appel a deux niveaux d'arguments imbriques "
        "n'est plus absorbe" % P.PROFONDEUR_APPEL)
    trois = "processor.<slot 0x11>(matchState.GetEntity(GetId(effect)))   # = RemoveEffect"
    vus = {(int(m.group("n%d" % k), 0), m.group("nom%d" % k))
           for k, rx in enumerate(P.RE_COUPLES_ML) for m in rx.finditer(trois)}
    assert (0x11, "RemoveEffect") in vus, (
        "un appel a 3 niveaux n'est pas absorbe -- vus : %s" % sorted(vus))
    peu = P._regex_couples(True, profondeur=1)
    vus_p = {(int(m.group("n%d" % k), 0), m.group("nom%d" % k))
             for k, rx in enumerate(peu) for m in rx.finditer(trois)}
    assert (0x11, "RemoveEffect") not in vus_p, (
        "la profondeur 1 suffit deja -- la courbe ne mesure plus rien")


def test_etage3ter_le_recenseur_voit_les_noms_QUALIFIES(table) -> None:
    """Le RECENSEUR de la ventilation avait `$` dans son lookbehind : un nom QUALIFIE lui etait
    invisible.

    Consequence MESUREE : `OperationProcessor$$RemoveUnit` etait range en « aucun nom dans la
    fenetre, rien a contredire », et le gisement etait sous-compte de 24 lignes (50 annoncees,
    74 reelles). C'est « un recenseur ne peut pas rendre zero sur ce qu'il ne visite pas »,
    applique au recenseur lui-meme.
    """
    rx = P._regex_noms(frozenset(v[0] for v in table.values()))
    assert rx.search("`Core.Services.OperationProcessor$$RemoveUnit`"), (
        "le recenseur ne voit pas un nom QUALIFIE par `$$` -- il sous-compte le gisement")
    assert rx.search("processor.MoveUnit(u, tiles)"), (
        "le recenseur ne voit pas un nom qualifie par un point")
    assert not rx.search("XRemoveUnit"), (
        "le recenseur prend un SUFFIXE de mot pour un nom -- le lookbehind a saute")


# --------- etage 3quater : la VIRGULE cede la place a la LOCALITE, et le SECOND commentaire


def test_etage3quater_le_franchissement_de_virgule_APPORTE_sans_rien_perdre(table) -> None:
    """La virgule arretait le remplissage ; sur CE corpus elle cachait **7** couples JUSTES.

    Le cran ne disparait pas : il change d'objet. Ce qui rend faux le couple d'une enumeration
    `slot N1 \\`X\\`, slot N2 \\`Y\\`` n'est pas la virgule, c'est que `X` est deja apparie a
    `N1` sans rien franchir (`ceder_aux_locaux`). Le test garde les deux moities.
    """
    cits, _ns, _ec = P.recolter()
    ref, _rns, _rec = P.recolter(virgule_bloquante=True)
    cle = lambda c: (c.fichier, c.ligne, c.slot, c.noms[0], c.ligne_nom)      # noqa: E731
    juste = lambda k: table.get(k[2], ("",))[0] == k[3]                       # noqa: E731
    neufs = {cle(c) for c in cits} - {cle(c) for c in ref}
    perdus = {cle(c) for c in ref} - {cle(c) for c in cits}
    assert neufs, "le franchissement de virgule n'apporte plus rien sur ce corpus"
    #: ⚠ LE CRITERE PORTE SUR LES JUSTES. Un couple que la table CONTREDIT a le droit de
    #: disparaitre -- c'est meme ce que le cran de localite existe pour faire (mesure sur le
    #: corpus voisin : `astramilitarum.py` 0xab -> `GetSurroundingTiles`, faux, retire).
    perdus_justes = [k for k in perdus if juste(k)]
    assert not perdus_justes, ("le franchissement de virgule PERD des couples JUSTES : %s"
                               % sorted(perdus_justes)[:5])
    faux = [k for k in neufs if not juste(k)]
    assert not faux, "le franchissement de virgule fait entrer des couples FAUX : %s" % faux[:5]


def test_etage3quater_la_regle_de_localite_est_CONSERVATRICE() -> None:
    """Elle ne peut que RETIRER, et seulement la ou un membre est deja pris SANS franchissement.

    Un cran qui pourrait AJOUTER changerait de nature : il deviendrait une heuristique
    d'appariement, pas un garde-fou.
    """
    from dataclasses import dataclass                                       # noqa: PLC0415

    @dataclass(frozen=True)
    class Faux:
        slot: int
        nom: str
        franchit: bool

    lot = [Faux(0x14, "CanStillBeUsed", False), Faux(0x13, "IsDisabled", False),
           Faux(0x13, "CanStillBeUsed", True), Faux(0x99, "MoveUnit", True)]
    gardes, cedes = P.ceder_aux_locaux(lot, lambda c: c.franchit,
                                       lambda c: c.slot, lambda c: c.nom)
    assert len(gardes) + len(cedes) == len(lot), "la regle a fabrique ou perdu un element"
    assert Faux(0x13, "CanStillBeUsed", True) in cedes, (
        "le couple dont les DEUX membres sont deja pris n'a pas cede")
    assert Faux(0x99, "MoveUnit", True) in gardes, (
        "un franchissant dont AUCUN membre n'est pris a cede -- la regle n'est plus "
        "conservatrice, elle devine")


def test_etage3quater_la_resolution_vit_dans_le_SECOND_commentaire() -> None:
    """`processor.<slot 0x21>();  // -- \\`verifier\\`` puis, LIGNE SUIVANTE, `// = \\`...\\``.

    ⚠ LA CAUSE EST DOUBLE, ET C'EST UNE MESURE. La forme D exigeait le PREMIER commentaire ET
    refusait un nom PLEINEMENT QUALIFIE (`_NOM` interdit une tete de namespace). Chacune seule
    rend **0** couple neuf ; leur conjonction rend le site, **0 faux, 0 perdu**.
    """
    bloc = ("        processor.<slot 0x21>();                     // -- `verifier`\n"
            "                          // = `Core.Services.OperationProcessor"
            "$$VerifyUnitsTurnFinished`")
    vus = {(int(m.group("n%d" % k), 0), m.group("nom%d" % k))
           for k, rx in enumerate(P.RE_COUPLES_ML) for m in rx.finditer(bloc)}
    assert (0x21, "VerifyUnitsTurnFinished") in vus, (
        "la resolution du SECOND commentaire n'est pas captee -- vus : %s" % sorted(vus))
    #: Et elle reste INVISIBLE au regime mono-ligne : la comparaison fenetre=1 / fenetre=N doit
    #: continuer de vouloir dire quelque chose.
    vus1 = {(int(m.group("n%d" % k), 0), m.group("nom%d" % k))
            for k, rx in enumerate(P.RE_COUPLES) for m in rx.finditer(bloc)}
    assert (0x21, "VerifyUnitsTurnFinished") not in vus1


def test_etage3quater_la_LOCALITE_du_commentaire_est_tenue() -> None:
    """On suit le BLOC DE COMMENTAIRE CONTIGU -- jamais du CODE.

    « Sauter le premier commentaire » perdrait exactement ce que `appel-colle` tient : une ligne
    de CODE intercalee doit couper la resolution.
    """
    avec_code = ("        processor.<slot 0x21>();       // -- `verifier`\n"
                 "        refresh(x);                    // = `Core.Services.OperationProcessor"
                 "$$VerifyUnitsTurnFinished`")
    vus = {(int(m.group("n%d" % k), 0), m.group("nom%d" % k))
           for k, rx in enumerate(P.RE_COUPLES_ML) for m in rx.finditer(avec_code)}
    assert (0x21, "VerifyUnitsTurnFinished") not in vus, (
        "la forme D franchit une ligne de CODE -- la localite d'`appel-colle` est perdue")
    #: Et le cran est RELACHABLE : desarme, il franchit -- c'est ce qui prouve qu'il agit.
    relache = P._regex_couples(True, relaches=("commentaire-contigu",))
    vus_r = {(int(m.group("n%d" % k), 0), m.group("nom%d" % k))
             for k, rx in enumerate(relache) for m in rx.finditer(avec_code)}
    assert (0x21, "VerifyUnitsTurnFinished") in vus_r, (
        "le cran `commentaire-contigu` ne change RIEN -- il ne garde donc rien")


def test_etage3quater_le_mutant_des_franchissants_REFUSE_en_regime_bloquant(table) -> None:
    """Un mutant qui n'a rien a muter REFUSE, plutot que de rendre une mutation vide."""
    ref, _ns, _ec = P.recolter(virgule_bloquante=True)
    assert not any(c.franchit_virgule for c in ref), (
        "le regime de reference contient des franchissants : il ne mesure pas ce qu'il dit")
    with pytest.raises(SystemExit) as exc:
        P.muter(table, "franchissants-decales", ref)
    assert "IMPOSSIBLE" in str(exc.value)


# ------------------------------------- etage 5 : les citations par NOM SEUL (#477-r32)


def test_etage5_les_citations_par_nom_seul_nomment_une_vraie_methode(
        table: dict[int, tuple[str, int]], noms_seuls: list[P.CitationNom]) -> None:
    """« le slot `X` de l'`OperationProcessor` » : `X` doit etre une des 150 methodes."""
    assert noms_seuls, ("aucune citation par NOM SEUL recoltee -- le motif ne matche plus, et "
                        "un etage qui ne visite rien rend 0 faute et se lit comme un vert")
    faux = P.confronter_noms(noms_seuls, table)
    assert not faux, "slot(s) nomme(s) qui n'existent PAS sur l'interface :\n  " + "\n  ".join(faux)


def test_etage5_la_PROSE_en_capitales_nest_pas_une_citation() -> None:
    """Le discriminant est la tournure « de l'<recepteur> », PAS le mot en capitale.

    Un motif qui se contente de `slot <Mot>` recolte « slot SANS ARGUMENT », « slot SOIT
    `FinishUnitTurn` », « slots AUTRES que ». Mesure #477-r32 : 5 faux positifs pour 7 citations
    reelles -- un etage qui rougit sur de la prose fait renoncer a une mesure juste.
    """
    for prose in ("la lambda appelle UN slot SANS ARGUMENT ; `OperationProcessor$$StartMatch`",
                  "Que ce slot SOIT `FinishUnitTurn` est PROUVE -- `OperationProcessor` le dit",
                  "CLIQUET des slots d'interface AUTRES que `Core.Services.IOperationProcessor`"):
        assert not P.RE_NOM_SEUL_ML.search(prose), "prose prise pour une citation : %s" % prose
    for vraie in ("il passe au slot `MoveUnit` de l'`IOperationProcessor` -- d'ou",
                  "le slot `RefreshEffects` de l'`OperationProcessor`",
                  "le slot `KillUnit` de l'`IOperationProcessor`, c'est-a-dire"):
        assert P.RE_NOM_SEUL_ML.search(vraie), "citation reelle NON vue : %s" % vraie


def test_etage5_apply_stat_modifiers_nest_PAS_un_slot(table) -> None:
    """La faute que cette tranche a trouvee, ecrite comme une assertion.

    `components.py` nommait le slot `ApplyStatModifiers`. Ce nom n'est a AUCUN des 150 slots :
    c'est `IdunBattle.Entities.UnitExtensions$$ApplyStatModifiers`, atteint DEUX niveaux plus
    bas par `TransformUnitOperation$$Execute`. Le slot, lui, est `TransformUnit` (0x66).
    """
    noms = {v[0] for v in table.values()}
    assert "ApplyStatModifiers" not in noms
    assert table[0x66] == ("TransformUnit", 3)


# ------------------------------- etage 4 : la derivation depuis le metadata, si elle est la


def test_etage4_derivation_concorde_avec_lentree_versionnee(
        table: dict[int, tuple[str, int]], localise) -> None:
    """Si le jeu est installe, la table versionnee doit etre CELLE du metadata.

    Skip NOMME quand le metadata n'est pas la : c'est une entree hors depot (invariant 3 du
    CLAUDE.md, troisieme categorie). « Pas mesure » n'est pas « mesure et vide ».
    """
    reader, _ = localise
    derive = reader.interface_table(P.ANCRES)
    assert {m.slot: (m.name, m.param_count) for m in derive} == table


def test_etage4_la_table_ne_depend_pas_des_ancres_choisies(localise) -> None:
    """Generalisation : d'autres ancres, disjointes de celles de production, rendent la MEME table.

    Si le resultat dependait du tirage, la table serait un artefact du choix des ancres et non
    une lecture du metadata.
    """
    reader, _ = localise

    def table_avec(ancres: tuple[str, ...]) -> dict[int, tuple[str, int]]:
        return {m.slot: (m.name, m.param_count) for m in reader.interface_table(ancres)}

    ref = table_avec(P.ANCRES)
    for autres in (("StartMatch", "RevealRoom"),
                   ("AddResurrectDraftPoint", "VerifyDoors"),
                   ("SkipToNextWave", "AddReinforcementShield")):
        assert not set(autres) & set(P.ANCRES), "le tirage doit etre DISJOINT des ancres "\
            "de production, sinon il ne prouve rien"
        assert table_avec(autres) == ref, "tirage %s : table differente" % (autres,)


def test_etage4_une_ancre_HOMONYME_seule_est_refusee(localise) -> None:
    """Le refus qui evite une table d'une AUTRE interface -- vu MORDRE.

    `StartMatch` est declaree par CINQ interfaces : seule, elle ne designe pas une table. Une
    seconde ancre suffit a dissoudre l'ambiguite par intersection.

    ⚠ Ce n'est PAS la surcharge qui multiplie les candidats. Dans une table contigue, toutes les
    entrees d'une meme interface rendent la meme base -- verifie ici sur `EvaluateAbilities`,
    surchargee ET dispersee (slots 77-79, 81-82), qui n'en propose qu'UNE.
    """
    r, il2cpp_metadata = localise
    with pytest.raises(il2cpp_metadata.MetadataRefused, match="AMBIGU"):
        r.interface_table(("StartMatch",))

    t = r.interface_table(("StartMatch", "RevealRoom"))
    assert {m.slot: m.name for m in t}[0x63] == "ReviveUnit"

    #: contre-modele : une ancre surchargee et DISPERSEE reste sans ambiguite
    seule = r.interface_table(("EvaluateAbilities",))
    assert {m.slot: m.name for m in seule}[0x63] == "ReviveUnit"
