"""#477-r24-r1 -- CLIQUET du mapping slot <-> methode de `Core.Services.IOperationProcessor`.

    python -m pytest scripts/python/tests/engine/test_477r24r1_slots_interface_offline.py -q

Ce que ce fichier empeche de revenir :

* qu'une citation « slot X = NomDeMethode » reparaisse FAUSSE dans le depot (etage 3, perimetre
  DERIVE d'un `git ls-files` -- aucune liste blanche de fichiers) ;
* qu'un renumerotage silencieux passe pour un vert. L'etage 2 FIGE les couples que cette tranche
  a tranches, mesures a la conversion. Il n'est pas redondant avec l'etage 1 : celui-ci compare
  l'entree versionnee a elle-meme et redevient vert des qu'on la regenere, alors que les valeurs
  ECRITES dans les fiches, elles, auraient change sans que personne ne le voie ;
* qu'un corpus vide passe pour un vert (etage 0 : le balayage assertionne son propre NON-VIDE).
"""
from __future__ import annotations

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
}

#: Nombre de slots de l'interface sur ce build. Fige : une table qui RETRECIT en silence est
#: exactement ce qui ferait passer une citation hors bornes pour « slot inconnu, on ignore ».
NB_SLOTS = 150


@pytest.fixture(scope="module")
def table() -> dict[int, tuple[str, int]]:
    return P.lire_tsv()


@pytest.fixture(scope="module")
def citations() -> list[P.Citation]:
    cits, _autre, _sans, _exempt = P.recolter()
    return cits


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
                              citations: list[P.Citation], mutant: str) -> None:
    """Contre-epreuve : chaque mutant doit faire bouger au moins un compteur.

    Une garde qu'on n'a jamais vue ROUGE ne prouve rien. `slot-decale` et `table-tronquee`
    frappent l'appariement, `nom-permute` l'attribution (sur des slots DERIVES des citations
    reelles, sinon le mutant serait inerte), `arite-fausse` la signature.
    """
    base = P.jouer(table, citations, None)
    mute = P.jouer(P.muter(table, mutant, citations), citations, None)
    assert mute != base, "le mutant `%s` n'a RIEN change (%s) -- il est inerte" % (mutant, base)


# ------------------------------- etage 4 : la derivation depuis le metadata, si elle est la


def test_etage4_derivation_concorde_avec_lentree_versionnee(
        table: dict[int, tuple[str, int]]) -> None:
    """Si le jeu est installe, la table versionnee doit etre CELLE du metadata.

    Skip NOMME quand le metadata n'est pas la : c'est une entree hors depot (invariant 3 du
    CLAUDE.md, troisieme categorie). « Pas mesure » n'est pas « mesure et vide ».
    """
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
    derive = reader.interface_table(P.ANCRES)
    assert {m.slot: (m.name, m.param_count) for m in derive} == table
