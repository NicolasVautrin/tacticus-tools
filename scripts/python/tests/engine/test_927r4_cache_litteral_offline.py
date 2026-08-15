"""#927-r4 -- le litteral `matchAbilityEntities` de CHAQUE call-site porte est CONFRONTE au natif.

CE QUE CE FICHIER GARDE, ET POURQUOI PAS CE QUE LE RESIDU PROPOSAIT
------------------------------------------------------------------
Le residu proposait de rendre `match_ability_entities` OBLIGATOIRE au noeud `Cache` et de
transcrire le litteral aux ~35 call-sites portes. La mesure a fait renoncer a ce geste-la, et
en a impose un plus fort :

  1. RIEN N'EST FAUX AUJOURD'HUI. Appariement site-a-site des **44** call-sites PYTHON du noeud
     avec le litteral que pousse LEUR call-site natif : **44 concordants, 0 divergent**. Rendre
     le parametre obligatoire aurait donc ete un durcissement, pas un correctif -- au prix de
     42 hunks sur 28 fichiers dans un depot ou plusieurs PR volent en permanence.
  2. UN PARAMETRE OBLIGATOIRE FORCE A ECRIRE, PAS A LIRE. `Cache(x, True)` pose de memoire est
     exactement la meme faute que `Cache(x)` : les deux valent le mode majoritaire sans que
     personne ait relu le natif. Ce que le gisement demande, c'est une CONFRONTATION.
  3. LA CONFRONTATION ATTRAPE STRICTEMENT PLUS. Elle voit aussi les DEUX sites qui ecrivent
     deja leur litteral (si l'un devenait faux), et une forme que l'obligatoire ne peut pas
     voir : un `Cache` porte SANS call-site natif -- un noeud invente.

CE QUE LA MESURE A CORRIGE DANS LE CENSUS DE REFERENCE
-----------------------------------------------------
#927-r3 annoncait **119** call-sites natifs (112 DICT / 7 SLOT). Re-mesure : **121** (114 / 7).
L'ecart n'est pas une erreur de comptage mais un TROU DE FORME -- le scan ne cherchait que
`E8` (call) et ratait les TAIL CALLS. `...FuryOfTheAncientsAbility$$GetTarget` et
`...SorcerousFacadeAbility$$GetTarget` finissent tous deux par `mov r8b, 1 ; jmp <Cache>`.
Ironie utile : le premier est precisement le call-site que #927 declare avoir ajoute, et son
propre census ne le voyait pas. Contre-controle : Ghidra rend 125 xrefs = 121
`UNCONDITIONAL_CALL` + 4 `DATA`.

La table du census vit dans `data/symbols/<build>/metadata/dsl_cache_call_sites.tsv` (une
ENTREE versionnee, comme `remove_on_death_step.tsv`), regeneree par
`python scripts/python/probe_927r4_cache_census.py --regenerer`.

Aucun runner, aucun RPC, aucun binaire : ce fichier lit la table versionnee et l'arbre Python.
"""
from __future__ import annotations

#: Ce qui doit changer pour que ce FICHIER puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        # LE FOYER : le noeud, et l'outil qui produit ET rejoue l'appariement.
        "scripts/python/engine/entities/selectors/geometry.py",
        "scripts/python/probe_927r4_cache_census.py",
        # TOUT call-site du noeud vit sous l'un de ces deux arbres.
        "scripts/python/engine/runner/abilities/**/*.py",
        "scripts/python/engine/runner/operations/triggers/**/*.py",
    ),
    "build": True,
    "toujours": False,
    "raison": "Il confronte chaque call-site PYTHON du noeud `Cache` au litteral que pousse "
              "SON call-site natif, via la table `metadata/dsl_cache_call_sites.tsv`. Un "
              "changement de build peut deplacer un litteral ; un port neuf ajoute un site.",
}

import pytest                                                                   # noqa: E402

from probe_927r4_cache_census import (                                          # noqa: E402
    apparier, lire_table, litteraux_du_symbole)
from engine.entities.selectors.geometry import Cache                            # noqa: E402

#: MESURE au build `t6dpr4k06g` (2026-08-15). Ce ne sont pas des seuils : ce sont les valeurs
#: LUES. Un changement de build les fait bouger legitimement -- et ce test est alors la pour
#: EXIGER qu'on regenere la table et qu'on RELISE, pas pour rassurer.
CENSUS_ATTENDU = {"total": 121, "dict": 114, "slot": 7}

#: Les SEPT appelants natifs qui poussent `matchAbilityEntities = 0` (mode SLOT), NOMMES.
SLOT_ATTENDUS = {
    "DakkaDakkaDakkaAbility$$ExecuteBehaviour",
    "DakkaDakkaDakkaAbility$$GetLeftoverHitsPerTargetFormula",
    "DarkTalonStrikeAbility$$ExecuteBehaviour",
    "ResurrectionOrbAbility$$GetResurrectBehaviour",
    "StormcallerAbility$$ExecuteBehaviour",
    "HeavyRailRifle_AttackAbility$$CreateBehaviour",
    "LightImUpAbility$$CreateBehaviour",
}


@pytest.fixture(scope="module")
def table():
    return lire_table()


@pytest.fixture(scope="module")
def sites(table):
    return apparier(table)


# --------------------------------------------------------------------------------------------
# [1] LA TABLE DU CENSUS -- ce qu'elle porte, et son NON-VIDE
# --------------------------------------------------------------------------------------------

def test_la_table_du_census_porte_le_compte_mesure(table):
    """Le total et sa ventilation. Les rater par la FORME (tail calls oublies) est exactement
    ce qui est arrive a #927-r3 : le compte etait faux de 2, en silence."""
    vals = [v for l in table.values() for v in l]
    assert vals, "TEMOIN VIDE : la table du census ne porte aucun litteral"
    assert {"total": len(vals), "dict": vals.count(1), "slot": vals.count(0)} == CENSUS_ATTENDU
    assert set(vals) == {0, 1}, "un litteral hors {0, 1} : relire le call-site a l'octet"


def test_les_sept_appelants_en_mode_SLOT_sont_ceux_qui_sont_NOMMES(table):
    """C'est le contenu SEMANTIQUE du census : qui memoise sans regarder le contexte."""
    slot = {n.rsplit(".", 1)[-1] for n, v in table.items() if 0 in v}
    assert slot == SLOT_ATTENDUS


# --------------------------------------------------------------------------------------------
# [2] L'APPARIEMENT -- chaque site PYTHON contre SON call-site natif
# --------------------------------------------------------------------------------------------

def test_le_balayage_trouve_bien_des_call_sites(sites):
    """NON-DEGENERESCENCE. Sans ce cran, un import renomme ou un balayage casse rendrait une
    liste vide, et TOUS les tests ci-dessous passeraient sur zero site."""
    assert len(sites) >= 40, "balayage degenere : %d call-sites Python trouves" % len(sites)


def test_chaque_call_site_PYTHON_est_APPARIE_a_un_call_site_natif(sites):
    """Un site qu'on ne sait pas rattacher au natif est le cas le plus dangereux : ni juste ni
    faux, juste INVERIFIABLE. Le remede est d'ECRIRE le symbole natif au site -- ce que la
    doctrine demande deja par ailleurs (« on cite un SYMBOLE »)."""
    orphelins = ["%s:%d" % (r, l) for r, l, _e, app in sites if not app]
    assert not orphelins, (
        "call-sites du noeud `Cache` sans symbole natif apparie :\n  %s\n"
        "Ecrire au site le symbole de son call-site natif (commentaire de fin de ligne)."
        % "\n  ".join(orphelins))


def test_le_litteral_EFFECTIF_de_chaque_site_est_celui_du_natif(table, sites):
    """LE CRAN CENTRAL. `effectif` = le litteral ecrit, ou le DEFAUT du noeud quand le site se
    tait. Un defaut est un litteral comme un autre : il doit concorder, pas etre presume."""
    defaut = int(Cache(None).match_ability_entities)
    divergents = []
    for rel, ln, ecrit, app in sites:
        effectif = defaut if ecrit is None else int(bool(ecrit))
        natifs = litteraux_du_symbole(table, app)
        if natifs != [effectif]:
            divergents.append("%s:%d effectif=%d natif=%s via %s"
                              % (rel, ln, effectif, natifs, app))
    assert not divergents, "\n  ".join(["litteral PORTE != litteral NATIF :"] + divergents)


# --------------------------------------------------------------------------------------------
# [3] LE DEFAUT DU NOEUD -- attesté, jamais decrete
# --------------------------------------------------------------------------------------------

def test_le_defaut_du_noeud_est_le_mode_MAJORITAIRE_du_census(table):
    """Le natif n'a AUCUN defaut a l'execution : les 121 call-sites poussent chacun un litteral
    CONSTANT (0 indetermine a la mesure). Le defaut du port est donc une commodite de portage,
    et la seule valeur defendable est celle du plus grand nombre -- verifiee ici contre la
    table, pas recopiee d'une prose."""
    vals = [v for l in table.values() for v in l]
    majoritaire = max({0, 1}, key=vals.count)
    assert int(Cache(None).match_ability_entities) == majoritaire


def test_aucun_site_MUET_ne_porte_une_ability_du_mode_SLOT(table, sites):
    """LA GARDE ANTI-REGRESSION. Le jour ou l'un des cinq call-sites SLOT encore non
    materialises entre au port (`DakkaDakkaDakka`, `ResurrectionOrb`, `HeavyRailRifle`, le 2e
    `LightImUp`), un `Cache(...)` pose sans litteral prendrait le mode DICT -- et re-calculerait
    la ou le natif re-sert sa memoisation, silencieusement."""
    fautifs = []
    for rel, ln, ecrit, app in sites:
        if ecrit is None and (set(app) & SLOT_ATTENDUS):
            fautifs.append("%s:%d porte %s" % (rel, ln, sorted(set(app) & SLOT_ATTENDUS)))
    assert not fautifs, "\n  ".join(
        ["sites MUETS rattaches a une ability en mode SLOT :"] + fautifs)


def test_les_sites_qui_ECRIVENT_le_mode_SLOT_sont_bien_ceux_du_natif(sites):
    """Le pendant du test precedent : un `match_ability_entities=False` ecrit sur une ability
    que le natif keye par contexte est la faute SYMETRIQUE, et elle sur-memoise."""
    ecrivains = {(r, l): app for r, l, e, app in sites if e is False}
    assert ecrivains, "TEMOIN VIDE : aucun site n'ecrit le mode SLOT"
    for (r, l), app in ecrivains.items():
        assert set(app) & SLOT_ATTENDUS, (
            "%s:%d ecrit le mode SLOT mais s'apparie a %s, qui n'est pas des sept" % (r, l, app))
