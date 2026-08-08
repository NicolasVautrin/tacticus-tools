"""#270-r2 -- CLIQUET : aucun registre d'un FOYER n'est muet.

LE VICE. L'etape 1 de `probe_313` DECOUVRE toute `IntEnum` sous `engine/` -- c'est elle qui empeche
le trou de se re-creuser. L'etape 5, elle, ne gardait que les dicts INSCRITS A LA MAIN : exactement
le mode de defaillance que l'etape 1 existe pour fermer, reintroduit un cran plus bas.

ET CE N'ETAIT PAS HYPOTHETIQUE. Le residu parlait d'un << huitieme registre ajoute demain >>. Au
premier passage de l'etape 7, **quatre** registres reels manquaient deja, tous dans
`engine/entities/effects/factory.py` et tous lus par `.get(<nom>, [])`, donc porteurs de la MEME
degradation muette : `TRAIT_OWNER_EFFECTS`, `TRAIT_DERIVED_ABILITIES`, `ABILITY_INIT_OWNER_EFFECTS`,
`ABILITY_OWNER_EFFECTS`.

POURQUOI UNE PARTITION ET PAS UNE DECOUVERTE. << Un dict dont les cles designent un enum >> n'est
pas decidable par AST : une table de constantes et un registre d'abilities ont la meme forme. La
reponse est donc la PARTITION -- dans les modules qui hebergent DEJA un registre inscrit, tout dict
de niveau module est soit INSCRIT, soit ECARTE AVEC SA RAISON. Rien ne peut y etre muet.

100 % OFFLINE.
"""
from __future__ import annotations

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        # Le probe sous test, et les DEUX FOYERS qu'il partitionne. Un dict de niveau module
        # ajoute dans l'un d'eux doit faire rougir ce cliquet -- c'est tout son objet.
        "scripts/python/probe_313_enum_mirror_bijection.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/registry.py",
        "scripts/python/engine/entities/effects/factory.py",
        # Les deux dependances du probe, mesurees par `probe_486r15` (pas devinees) : il lit le
        # corpus en parallele et memorise son verdict. Trop LARGE est sain, trop ETROIT est un
        # faux vert -- c'est exactement ce que ce garde a rendu au premier passage.
        "scripts/python/repo_read.py", "scripts/python/verdict_cache.py",
    ),
    "build": True,
    "toujours": False,
    "raison": "Le probe, les deux foyers de registre, et le BUILD : l'etape 5 confronte chaque "
              "cle aux enums du dump, donc un changement de build peut faire apparaitre une "
              "cle MORTE ou EGAREE sans qu'aucun fichier Python ait bouge.",
}

import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parents[2]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import probe_313_enum_mirror_bijection as P                                 # noqa: E402


def test_aucun_registre_de_foyer_n_est_MUET():
    """CLIQUET -- invariant `MUETS == 0`, jamais un seuil."""
    inscrits = {(c.mod, c.attr) for c in P.CONSOMMATEURS}
    dicts = P.dicts_de_foyer()
    assert dicts, "aucun dict trouve : la partition ne visite plus rien"
    muets = [(m, n) for (m, n) in dicts
             if (m, n) not in inscrits and n not in P.HORS_PERIMETRE]
    assert not muets, (
        "registres MUETS (ni inscrits dans CONSOMMATEURS, ni ecartes avec leur raison) : %s"
        % (muets,))


def test_la_partition_MORD():
    """CONTRE-EPREUVE. Un zero d'instrument aveugle ne vaut rien. On retire un consommateur du
    registre et on verifie que son dict redevient MUET -- c'est exactement l'etat de `master` avant
    cette tranche, ou quatre dicts etaient dans ce cas."""
    temoin = next(c for c in P.CONSOMMATEURS if c.attr == "EFFECT_CLASSES")
    sauve = list(P.CONSOMMATEURS)
    try:
        P.CONSOMMATEURS.remove(temoin)
        inscrits = {(c.mod, c.attr) for c in P.CONSOMMATEURS}
        muets = [(m, n) for (m, n) in P.dicts_de_foyer()
                 if (m, n) not in inscrits and n not in P.HORS_PERIMETRE]
        assert (temoin.mod, temoin.attr) in muets, (
            "la partition ne voit plus un registre desinscrit : elle ne garde rien")
    finally:
        P.CONSOMMATEURS[:] = sauve


def test_les_foyers_sont_DERIVES_pas_ecrits():
    """Inscrire un registre dans un module NEUF doit mettre AUSSITOT tout ce module sous partition.
    Si la liste des foyers etait ecrite, le module neuf y echapperait -- le vice, deplace d'un cran
    de plus."""
    foyers = P.foyers()
    assert foyers == {c.mod for c in P.CONSOMMATEURS}
    assert "engine.entities.effects.factory" in foyers, (
        "le foyer trouve par cette tranche a disparu du registre")


def test_les_deux_registres_d_ability_declarent_DEUX_enums():
    """La VOIE ne dit pas l'enum. `spawn.py::_seed_ability_owner_effects` boucle sur
    `activeAbilities + passiveAbilities`, et deux inversions connues existent (`ShroudPsalm`,
    `Maugetar`). Forcer un enum unique fabriquerait des EGAREES sur des cles justes."""
    for nom in ("ABILITY_INIT_OWNER_EFFECTS", "ABILITY_OWNER_EFFECTS"):
        c = P.PAR_CONSO[nom]
        assert set(c.classes) == {"ActiveAbilityType", "TriggeredAbilityType"}, (
            "%s doit declarer les DEUX enums d'ability ; obtenu %r" % (nom, c.classes))


def test_la_chaine_TRAIT_DERIVED_n_a_aucune_ORPHELINE():
    """LE CRAN DU DESSOUS. Une ability derivee d'un trait que rien ne materialise donne
    `.get(nom, [])` -> `[]` : aucun owner-effect pose, le porteur perd sa reduction en SILENCE.

    ⚠ Ce cran a servi immediatement : deux valeurs de `TRAIT_DERIVED_ABILITIES` (`DiminutiveAbility`,
    `ShadowInTheWarp`) ne sont dans AUCUN enum du build -- ce sont des noms INTERNES au port, tires
    de la CLASSE native (`IdunBattleLogic.Entities.Abilities.Triggered.Loki.DiminutiveAbility`) ou
    du TRAIT. Les compter INTROUVABLES aurait accuse deux entrees justes ; ne rien verifier aurait
    laisse passer une chaine rompue. La bonne mesure est celle-ci : elles doivent etre CONSOMMEES."""
    orphelines = P.chaine_trait_derivee_cassee()
    assert not orphelines, (
        "abilities derivees d'un trait sans consommateur (chaine rompue en silence) : %s"
        % (orphelines,))
    assert P.abilities_derivees_de_trait(), "l'espace de noms derive est VIDE : rien n'est verifie"
