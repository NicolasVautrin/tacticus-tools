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


def test_etage3bis_un_segment_de_chemin_nest_pas_un_nom_de_methode() -> None:
    """`slot 0x46 -> `IdunBattle.Operations.DiscardHitOperation`` ne nomme PAS `IdunBattle`.

    Le qualificateur etant OPTIONNEL en forme A, le moteur y renonce et attrape la TETE DU
    NAMESPACE. Mesure #477-r32 : 4 sites, tous artefacts, tous ranges parmi les « noms inconnus
    de l'interface » -- exactement la ou une VRAIE citation fausse doit sortir.
    """
    bloc = "-> slot IOperationProcessor 0x46 -> `IdunBattle.Operations.DiscardHitOperation$$Execute`"
    vus = {m.group("nom%d" % k) for k, rx in enumerate(P.RE_COUPLES_ML) for m in rx.finditer(bloc)}
    assert "IdunBattle" not in vus, "la tete du namespace est prise pour un nom de methode"


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
