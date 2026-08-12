"""#909 -- cliquet de la face DECISION des actives de kit. 100 % OFFLINE (aucun runner).

CE QUE CE FICHIER GARDE, ET POURQUOI CES INVARIANTS-LA
-------------------------------------------------------
`probe_909_decision_actives_kit.py` MESURE ; ce fichier REFUSE que la mesure derive en silence.
Les etages 1 a 4 sont des INVARIANTS (une violation est toujours une faute), pas des seuils --
une garde en seuil se degrade sans bruit. L'etage 5 est le seul cliquet chiffre, et il porte sur
un fait du BUILD, pas sur notre avancement.

Le gisement garde ici est celui que NOTRE PROPRE CADENCE alimente, exactement comme
`TARGETING_OPTIONS` et `ABILITY_ATTACK_TYPE` : une ability qu'on inscrit dans un des trois
registres de decision sans qu'aucun playbook natif ne lui corresponde est un port de VIDE -- il ne
leve rien, ne casse aucun test, et fait croire la face couverte.
"""
from __future__ import annotations

DECLENCHEUR = {
    "chemins": (
        # Le probe sous test et la table native qu'il lit.
        "scripts/python/probe_909_decision_actives_kit.py",
        # #979 : le probe ne teste plus une LISTE BLANCHE de registres -- l'appartenance vient du
        # foyer `decision_face_voies`, et le TROISIEME etat (CONSTANTE) du ledger. Les deux
        # entrent donc dans sa fermeture, et changer l'un change directement le compte.
        "scripts/python/decision_face_voies.py",
        "scripts/python/coverage_attestations.py",
        "scripts/ratchets-951r2-couverture-attestee.json",
        "data/symbols/*/metadata/active_playbook_builders.tsv",
        # La table de symboles dont l'etage 4 et l'etage 6 derivent les methodes par classe.
        "data/symbols/*/ghidra/functions.tsv",
        # Les TROIS registres de la face DECISION des actives : y ajouter ou en retirer une
        # entree change directement le compte des non portees et les etages 1, 2 et 6.
        "scripts/python/engine/playbook/noncomparable/__init__.py",
        "scripts/python/engine/playbook/base.py",
        "scripts/python/engine/playbook/__init__.py",
        "scripts/python/engine/entities/abilities/active_ability.py",
        # La population : le kit gameconfig lu par `population()`.
        "scripts/python/unit_map.py", "scripts/python/gameconfig.py",
        # ⚠ AJOUTE PAR MESURE (#922) : `unit_map` ouvre AUSSI la table i2 pour resoudre les noms
        # affiches. La declaration ne la nommait pas, et personne ne pouvait le voir -- ce fichier
        # n'avait AUCUNE empreinte gravee, donc `probe_486r15` ne confrontait que la fermeture
        # d'imports, aveugle a un JSON ouvert au runtime. Le premier `probe_457 --measure-missing`
        # qui l'a joue a rendu le chemin visible et le cliquet ROUGE.
        "data/i2_en.json",
        # Le mirror d'enum confronte a l'etage 3.
        "scripts/python/enum_maps.py",
        "scripts/python/engine/entities/active_ability_type.py",
    ),
    "build": True,
    "toujours": False,
    "raison": "Ce fichier confronte TROIS registres Python au dict natif `+0x68` de "
              "`IdunBattle.AI.PlaybookDatabase`. Il change de verdict quand un registre bouge "
              "(port livre ou retire), quand le kit gameconfig bouge, quand le mirror d'enum "
              "bouge, ou au CHANGEMENT DE BUILD -- d'ou `build: True` : la table native est "
              "specifique au hash, et une table d'un autre build ferait rougir l'etage 4.",
}

import os                                                                # noqa: E402
import sys                                                               # noqa: E402

import pytest                                                            # noqa: E402

_ICI = os.path.dirname(os.path.abspath(__file__))
_PYROOT = os.path.dirname(os.path.dirname(_ICI))
if _PYROOT not in sys.path:
    sys.path.insert(0, _PYROOT)

import probe_909_decision_actives_kit as P


@pytest.fixture(scope="module")
def mesure():
    build = P.build_courant()
    try:
        entrees = P.lire_table(build)
    except P.ExtractionRefusee as exc:
        pytest.fail("table #909 illisible pour le build %s : %s -- la regenerer par "
                    "`python probe_909_decision_actives_kit.py --regenerer`" % (build, exc))
    natif = {e["cle"]: e["classe"] for e in entrees if e["dict"] == "active"}
    pop, ecartes = P.population()
    return {"build": build, "entrees": entrees, "natif": natif, "pop": pop, "ecartes": ecartes,
            "portees": {n: v for n, v in pop.items() if v["via"]},
            "non_portees": {n: v for n, v in pop.items() if not v["via"]}}


def test_etage0_population_non_vide(mesure):
    """Un test qui mesure le VIDE passerait pour vert. On assertionne d'abord le non-vide."""
    assert mesure["pop"], "aucune active de kit lineup lue -- le gameconfig n'a pas ete charge"
    assert mesure["natif"], "aucune cle dans le dict natif des actives"
    assert mesure["non_portees"], (
        "0 active non portee : soit la face decision est integralement portee (le dire et retirer "
        "ce garde), soit le predicat de couverture est casse et rend vrai partout")


def test_etage1_aucun_port_fantome(mesure):
    """INVARIANT -- toute active de kit PORTEE correspond a un playbook natif.

    Le port ne peut pas inventer un playbook que le natif n'a pas : l'inscrire au registre
    detournerait le scoring vers une voie que le jeu n'emprunte jamais.
    """
    fantomes = sorted((v["id"], n) for n, v in mesure["portees"].items()
                      if v["id"] not in mesure["natif"])
    assert not fantomes, (
        "%d active(s) inscrite(s) a un registre de decision SANS playbook natif correspondant "
        "dans `PlaybookDatabase` (+0x68) : %s" % (len(fantomes), fantomes))


def test_etage2_aucun_port_de_vide(mesure):
    """INVARIANT -- aucune active portee n'est appariee au playbook PAR DEFAUT.

    `Common.DefaultActiveAbilityPlaybook` est la voie GENERIQUE : y porter un scoring par-ability
    revient a dupliquer le tronc commun sous un nom propre.
    """
    vides = sorted((v["id"], n) for n, v in mesure["portees"].items()
                   if (mesure["natif"].get(v["id"]) or "").endswith(P.PLAYBOOK_PAR_DEFAUT))
    assert not vides, (
        "%d active(s) portee(s) dont le natif est le playbook par defaut : %s" % (len(vides), vides))


def test_etage3_cles_natives_toutes_dans_le_mirror(mesure):
    """INVARIANT -- toute cle du dict natif est un membre nomme d'`ActiveAbilityType`.

    C'est le pendant de `probe_313` sur ce canal : une cle absente du mirror signale un mirror en
    retard sur le build, donc des noms FAUX ecrits partout ailleurs.
    """
    import enum_maps as EM
    inconnues = sorted(k for k in mesure["natif"] if k not in EM.ACTIVE_ABILITY_TYPE)
    assert not inconnues, (
        "%d cle(s) du dict natif absente(s) du mirror ACTIVE_ABILITY_TYPE : %s -- regenerer le "
        "mirror avant de nommer quoi que ce soit" % (len(inconnues), inconnues))


def test_etage4_toute_classe_citee_existe_dans_les_symboles(mesure):
    """INVARIANT -- la table versionnee ne cite que des classes presentes dans `functions.tsv`.

    Garde contre une table regeneree depuis un autre build (ou depuis un desassemblage
    desynchronise) : les noms resteraient plausibles, et la ventilation entierement fausse.
    """
    sym = P.charge_symboles(mesure["build"])
    connues = {s.split("$" + "$", 1)[0] for s in sym.values() if "$" + "$" in s}
    orphelines = sorted({e["classe"] for e in mesure["entrees"]} - connues)
    assert not orphelines, (
        "%d classe(s) de la table absente(s) de ghidra/functions.tsv du build %s : %s"
        % (len(orphelines), mesure["build"], orphelines[:10]))


def test_etage5_le_dict_non_owner_recoupe_l_inventaire_477(mesure):
    """TEMOIN CROISE -- le dict `+0x98` doit rendre le meme compte que #477-r33/#477-r37.

    Ces 28 classes non-owner concretes ont ete comptees par une voie ENTIEREMENT independante
    (filtre par PARENT dans `frida/classes.tsv`). Deux mesures independantes qui concordent
    valident la lecture du binaire faite ici ; si l'une bouge sans l'autre, l'une des deux est
    fausse et il faut savoir laquelle AVANT de publier un chiffre.
    """
    n = sum(1 for e in mesure["entrees"] if e["dict"] == "nonowner")
    assert n == 28, (
        "le dict non-owner (+0x98) rend %d entrees ; #477-r33 et #477-r37 en comptent 28 par le "
        "filtre par PARENT. Divergence a trancher avant de publier -- ce n'est pas un compteur "
        "d'avancement, c'est un fait du build." % n)


def test_etage6_la_ventilation_est_une_partition_exhaustive(mesure):
    """INVARIANT -- chaque active non portee tombe dans EXACTEMENT une categorie, et la somme
    des categories vaut le total.

    Un recenseur ne peut pas rendre zero sur ce qu'il ne visite pas : la categorie `indetermine`
    existe expres, et sa presence est un signal, pas un trou tolere.
    """
    sym = P.charge_symboles(mesure["build"])
    meths = P.methodes_par_classe(sym)
    cats = {"noncomparable": 0, "prediction": 0, "registry": 0, "indetermine": 0}
    for _nm, v in mesure["non_portees"].items():
        cls = mesure["natif"].get(v["id"]) or ""
        noms = {m.split("u003C")[0] for m, _, _ in meths.get(cls, [])} - {".ctor", ".cctor", ""}
        if "EvaluateNonComparable" in noms:
            cats["noncomparable"] += 1
        elif "MakeDamagePredictions" in noms:
            cats["prediction"] += 1
        elif noms:
            cats["registry"] += 1
        else:
            cats["indetermine"] += 1
    assert sum(cats.values()) == len(mesure["non_portees"]), (
        "partition non exhaustive : %s pour %d non portees" % (cats, len(mesure["non_portees"])))
    assert cats["indetermine"] == 0, (
        "%d active(s) sans AUCUNE methode propre listee : %s. IL2CPP deduplique les corps "
        "triviaux, donc l'absence ne prouve pas la non-surcharge -- il faut trancher au slot de "
        "vtable, pas laisser la categorie se remplir en silence." % (cats["indetermine"], cats))


def test_etage7_le_predicat_natif_reste_degenere_ou_le_dit(mesure):
    """CLIQUET DE LECTURE -- tant que 100 % des actives de kit sont des cles du dict natif, la
    ventilation « avec / sans playbook natif » ne discrimine RIEN et ne doit pas etre publiee
    comme un resultat.

    Le jour ou ce test tombe, c'est que le regime a CHANGE : des actives de kit sans playbook
    natif existent, la ventilation redevient informative, et la case-doc doit etre reecrite.
    """
    dedans = sum(1 for v in mesure["pop"].values() if v["id"] in mesure["natif"])
    total = len(mesure["pop"])
    assert dedans == total, (
        "REGIME CHANGE : %d/%d actives de kit sont des cles du dict natif. La ventilation "
        "« avec / sans playbook natif » redevient discriminante -- mettre a jour "
        "docs/rl/case-909-face-decision-actives-de-kit.md, qui documente le regime degenere."
        % (dedans, total))
