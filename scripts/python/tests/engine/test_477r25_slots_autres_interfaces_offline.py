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
