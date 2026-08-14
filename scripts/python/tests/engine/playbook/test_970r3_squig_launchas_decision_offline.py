"""#970-r3 -- garde OFFLINE des deux faces DECISION du lot : `1200 SquigLaunchas` (PORTEE) et
`1168 EntropyCannons` (`RIEN_A_PORTER`, atteste).

Ce que chaque etage FIGE, et pourquoi il existe :

  0. INSCRIPTION ET SEUILS. 1200 est dans `PLAYBOOKS` (tier NonComparable, base LUE dans
     `frida/classes.tsv`) et PAS dans `REGISTRY` (l'y mettre serait un port MORT). `MIN_UTILITY`
     vient du `.cctor` (`Fix64(1)`), `PRIORITY` du sweep #170 (1000 = `AbilityPriority.First`),
     `RNG_TERM` de la borne BASSE **LUE** de `Next(1, 10)`. Valeurs LUES au decompile : un
     renumerotage du build ne doit pas les faire glisser en silence.
  1. LE MONTAGE N'EST PAS CREUX. Les trois `visualId` du probe resolvent au gameconfig et portent
     ce qu'on croit. Sans ce cran, un `visualId` inexistant rend un `_unit_cfg` VIDE -> tous les
     regimes << N Orks >> deviennent << N non-Orks >> et la passe accuse le port a la place du
     montage. Ce n'est pas theorique : c'est la faute commise a la premiere passe du probe.
  2. LE GATE SEPARE, ET LA SEPARATION EST NON VIDE. Il existe des cibles LEGALES (elles ont passe
     `GetDynamicInvalidTargetReason`, donc elles sont dans `abilityTargets`) sur lesquelles le
     gate de SUMMON refuse. L'ensemble des regimes separants est assertionne NON VIDE : un test
     qui n'en aurait aucun passerait pour vert en ne prouvant rien.
  3. LE FILTRE DE TRAIT MORD. `NonSteppableOrObjectUnits` retire l'`Object` AVANT le comptage, et
     la contre-epreuve remplace l'`Object` par une unite ordinaire : le verdict doit BASCULER.
  4. L'ARGMAX EST KEEP-FIRST. L'utilite portee est CONSTANTE et `Bucket$$AddAction` ne remplace
     que sur `>` STRICT : permuter `fromHere` doit changer la cible emise.
  5. CONTRE-EPREUVE DE SEUIL. Monter `nrOfUnits_3`/`nrOfUnits_4` doit faire disparaitre l'emission
     d'un regime qui passait. Une garde dont aucune mutation ne mord est un vert qui ment.
  6. `1168` : le verdict `RIEN_A_PORTER` est au ledger, VALIDE sur le build courant, et 1168 n'est
     dans AUCUN registre de face DECISION -- c'est ce couple qui EST le verdict.

AUCUN runner : tout est offline, `NCContext` bati a la main. ASCII only.
"""
from __future__ import annotations

#: Ce qui doit changer pour que ce FICHIER puisse changer de verdict (#486-r15).
#: Trop LARGE est sain, trop ETROIT est un FAUX VERT.
DECLENCHEUR = {
    "chemins": (
        # LA MESURE : le probe porte les regimes, l'ordre et les `visualId` du montage.
        "scripts/python/probe_970r3_squig_launchas_decision.py",
        # LA FACE PORTEE et son foyer d'enumeration de cibles.
        "scripts/python/engine/playbook/noncomparable/squig_launchas.py",
        "scripts/python/engine/playbook/noncomparable/_targets.py",
        # LE REGISTRE et la BASE : une ability retiree de `PLAYBOOKS` ou un `native_priority`
        # renumerote changent le verdict de l'etage 0.
        "scripts/python/engine/playbook/noncomparable/__init__.py",
        "scripts/python/engine/playbook/noncomparable/_base.py",
        # LE TIER COMPARABLE : l'etage 0 exige que 1200 n'y soit PAS, et l'etage 6 que 1168 ne
        # soit dans AUCUN des deux.
        "scripts/python/engine/playbook/base.py",
        # LE LEDGER et son foyer de validite : ils portent le verdict de 1168 (etage 6).
        "scripts/ratchets-951r2-couverture-attestee.json",
        "scripts/python/coverage_attestations.py",
        "scripts/python/decision_face_voies.py",
        # LA GEOMETRIE : `is_adjacent` / `neigh_map` decident quels allies sont adjacents.
        "scripts/python/engine/battle_query.py",
        "scripts/python/hexgeo.py",
        # LE SUBSTRAT DE TRAITS ET DE FACTION, lus a l'execution.
        "scripts/python/engine/entities/traits/unit_trait.py",
        "scripts/python/engine/entities/unit_faction.py",
        # LES MIRRORS D'ENUM et le gameconfig : `nrOfUnits_3`/`nrOfUnits_4`, `FactionId`, traits.
        "scripts/python/engine/entities/active_ability_type.py",
        "scripts/python/engine/entities/effects/magnitude.py",
        "scripts/python/gameconfig.py",
    ),
    # Le fichier LIT le gameconfig du build courant (seuils, factions, traits) ET confronte
    # l'attestation de 1168 au build de `data/symbols/CURRENT`.
    "build": True,
    "toujours": False,
    "raison": (
        "Garde des deux faces DECISION #970-r3 : seuil du `.cctor` et tier `get_Priority` de 1200, "
        "separation du gate de SUMMON vis-a-vis du gate de CIBLAGE, filtre de trait, ordre "
        "keep-first de l'argmax, et existence+validite du verdict `RIEN_A_PORTER` de 1168. Les "
        "seuils, factions et traits sont RELEVES au gameconfig a chaque passe et l'attestation est "
        "confrontee a `data/symbols/CURRENT` -- d'ou `build: True`. `toujours: False` : le fichier "
        "est purement offline et sa cascade est bornee par les chemins ci-dessus."),
}

import sys                                                          # noqa: E402
from pathlib import Path                                            # noqa: E402

import pytest                                                       # noqa: E402

PYDIR = Path(__file__).resolve().parents[3]                         # scripts/python
sys.path.insert(0, str(PYDIR))

import coverage_attestations as CA                                  # noqa: E402
import decision_face_voies as DFV                                   # noqa: E402
import probe_970r3_squig_launchas_decision as P                     # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType   # noqa: E402
from engine.playbook.base import REGISTRY                           # noqa: E402
from engine.playbook.noncomparable import PLAYBOOKS                 # noqa: E402

SQUIG = int(ActiveAbilityType.SquigLaunchas)      # 0x4b0 = 1200
ENTROPY = int(ActiveAbilityType.EntropyCannons)   # 0x490 = 1168


@pytest.fixture(scope="module")
def mesure():
    return P.mesurer()


# --- etage 0 : inscription et valeurs LUES au decompile ----------------------------------------

def test_etage0_1200_est_au_tier_noncomparable_et_pas_au_tier_comparable():
    """Base LUE dans `data/symbols/<build>/frida/classes.tsv` :
    `IdunBattle.AI.Playbook.Loki.SquigLaunchasPlaybook` -> `NonComparablePlaybook`1`.

    Le `.ctor` est etiquete `ComparablePlaybook<...>$$.ctor` par ghidra (corps DEDUPLIQUE, piege
    #487-r1) : s'y fier inscrirait 1200 au tier COMPARABLE, ou son `EvaluateNonComparable` ne
    serait JAMAIS appele -- un port MORT."""
    assert SQUIG in PLAYBOOKS, "1200 absente de noncomparable.PLAYBOOKS"
    assert SQUIG not in REGISTRY, "1200 inscrite a tort au registre COMPARABLE"
    assert type(PLAYBOOKS[SQUIG]).__name__ == "SquigLaunchasPlaybook"


def test_etage0_seuil_tier_et_terme_aleatoire(mesure):
    """`MIN_UTILITY` = le `.cctor` (`Fix64.op_Implicit(1)`) ; `PRIORITY` = 1000
    (`AbilityPriority.First`, sweep #170) ; `RNG_TERM` = la borne BASSE **LUE** de `Next(1, 10)`.

    `IntBasedMersenneTwister$$NextInternal` rend `min + (g % (max - min))` -> borne haute EXCLUE ->
    `[1, 9]`, donc la borne basse est **1** et non 0. Elle doit etre `>= MIN_UTILITY`, sans quoi le
    port supprimerait TOUTES les actions que le natif emet (le gate du `Bucket` est un `>=`)."""
    pb = PLAYBOOKS[SQUIG]
    assert pb.MIN_UTILITY == 1.0
    assert pb.PRIORITY == 1000
    assert pb.RNG_TERM == 1.0
    assert pb.RNG_TERM >= pb.MIN_UTILITY, (
        "la borne BASSE du tirage est sous le seuil du Bucket : le port supprimerait des actions "
        "que le natif emet toujours")


def test_etage0_les_seuils_viennent_du_gameconfig_pas_du_code(mesure):
    """`GetNumberConstant(0x81) = nrOfUnits_3` et `GetNumberConstant(0x82) = nrOfUnits_4`, LUS a
    l'execution. Un `0` signifierait << constante non lisible >>, et le gate deviendrait
    TOUJOURS VRAI (`Count >= 0`) -- la face DECISION cesserait de separer sans rien casser."""
    s = mesure["seuils"]
    assert s["orks_min"] >= 1, "nrOfUnits_3 non lisible -> le gate ne separe plus"
    assert s["friends_min"] >= 1, "nrOfUnits_4 non lisible -> le gate ne separe plus"
    assert s["friends_min"] > s["orks_min"], (
        "le seuil ALLIES doit etre plus haut que le seuil ORKS (le disjoint Ork est le plus "
        "permissif des deux)")


# --- etage 1 : le montage n'est pas creux ------------------------------------------------------

def test_etage1_le_montage_resout_ses_visualid(mesure):
    """Un `visualId` inexistant rend un `_unit_cfg` VIDE -> `FactionId is None` et `traits == []`,
    donc tous les regimes << N Orks >> deviennent << N non-Orks >> et le filtre de trait n'est
    jamais exerce. La passe accuserait alors le PORT a la place du MONTAGE."""
    v = mesure["visuals"]
    assert v["ork_faction"] == "Orks", "`%s` ne resout pas en faction Orks" % P.ORK
    assert v["non_ork_faction"] and v["non_ork_faction"] != "Orks"
    assert v["objet_traits"], "`%s` ne porte ni Object ni Steppable" % P.OBJET
    assert v["ork_traits_propres"], "l'Ork temoin porte Object/Steppable : il serait filtre"


# --- etage 2 : le gate SEPARE, et la separation est NON VIDE -----------------------------------

def test_etage2_tous_les_regimes_concordent(mesure):
    div = [r for r in mesure["regimes"] if r["emis"] != r["attendu"]]
    assert not div, "regimes divergents : %s" % [
        (r["libelle"], "emis=%s" % r["emis"], "attendu=%s" % r["attendu"]) for r in div]


def test_etage2_la_separation_est_non_vide_et_aucun_separant_n_emet(mesure):
    """LE cran de la tranche. Un regime SEPARANT est une cible LEGALE (elle a passe
    `...SquigLaunchasAbility$$GetDynamicInvalidTargetReason`, donc elle est dans `abilityTargets`)
    que le gate de SUMMON (`...$$FulfillsSummonCriteria`, seuils PLUS HAUTS) refuse.

    Sans face DECISION, le port proposait 1200 sur ces cibles-la. C'est le TEMOIN NON NUL : un
    ensemble vide ferait passer pour vert une garde qui ne prouve rien."""
    sep = mesure["separants"]
    assert sep, "AUCUN regime separant : la garde ne prouve rien"
    emetteurs = [s["libelle"] for s in sep if s["emis"]]
    assert not emetteurs, "le gate ne mord pas sur : %s" % emetteurs


# --- etage 3 : le filtre de trait mord ---------------------------------------------------------

def test_etage3_le_filtre_de_trait_bascule_le_verdict(mesure):
    """`NonSteppableOrObjectUnits` = intersection des complementaires de `Steppable` et `Object`
    (foyer `entities/selectors/units.py`). La contre-epreuve est un COUPLE : trois non-Orks + un
    `Object` REFUSE, quatre non-Orks ACCEPTE. Si les deux rendaient la meme chose, le filtre ne
    serait pas ce qui decide."""
    par_libelle = {r["libelle"]: r["emis"] for r in mesure["regimes"]}
    avec_objet = par_libelle["3 non-Orks + 1 Object"]
    sans_objet = par_libelle["4 non-Orks (temoin du filtre)"]
    assert avec_objet is False and sans_objet is True, (
        "le filtre de trait ne decide pas : avec Object=%s, sans=%s" % (avec_objet, sans_objet))


def test_etage3b_l_adjacence_a_la_CIBLE_decide(mesure):
    """`AdjacentUnits(target@+0x178)` est ancre sur la tuile de la CIBLE : un allie a distance >= 2
    ne compte pas, meme s'il est allie et de la bonne faction.

    TROU TROUVE PAR MUTATION, pas suppose : tant que le montage ne portait que des voisins
    immediats, neutraliser `bq.is_adjacent` ne faisait rougir AUCUNE assertion -- la garde etait
    MUETTE sur l'etage geometrique. Le couple ci-dessous (memes unites, autre distance) la rend
    mordante."""
    par_libelle = {r["libelle"]: r["emis"] for r in mesure["regimes"]}
    assert par_libelle["4 non-Orks (temoin du filtre)"] is True, "temoin adjacent : doit EMETTRE"
    assert par_libelle["4 non-Orks a distance >= 2"] is False, (
        "des allies HORS ring-1 comptent : l'ancrage d'`AdjacentUnits` sur la cible est perdu")
    assert par_libelle["4 Orks a distance >= 2"] is False, (
        "des Orks HORS ring-1 comptent : l'ancrage d'`AdjacentUnits` sur la cible est perdu")


# --- etage 4 : l'argmax est keep-first ---------------------------------------------------------

def test_etage4_l_ordre_de_fromhere_decide_la_cible(mesure):
    """`Bucket$$AddAction` ne remplace que sur `>` STRICT et l'utilite portee est CONSTANTE : la
    PREMIERE cible enumeree gagne. Permuter `fromHere` doit donc changer la cible emise -- c'est
    le second cran de #957 (un `set` ferait decider l'argmax par le HACHAGE)."""
    kf = mesure["keep_first"]
    assert kf["ordre_A"] is not None and kf["ordre_B"] is not None, (
        "aucune cible emise dans l'epreuve d'inversion : elle ne mesure rien")
    assert kf["ordre_A"] != kf["ordre_B"], (
        "l'ordre de `fromHere` ne decide pas la cible : argmax non keep-first")


# --- etage 5 : contre-epreuve de seuil ---------------------------------------------------------

def test_etage5_monter_le_seuil_supprime_l_emission(monkeypatch, mesure):
    """MUTATION : les deux seuils montent au-dessus de ce que le regime le plus permissif fournit.
    L'emission doit DISPARAITRE. Le temoin (avant mutation) est mesure et assertionne non vide --
    une mutation qui part d'un etat deja muet ne prouverait rien."""
    pb = PLAYBOOKS[SQUIG]
    ctx = P.ctx_pour([(P.CIBLE_ID, P.T)], P._anneau(4, P.NON_ORK))
    temoin = pb.generate_candidates(ctx)
    assert temoin, "temoin VIDE : la mutation ne peut rien montrer"

    monkeypatch.setattr(type(pb), "_threshold", lambda self, key: 99, raising=True)
    apres = pb.generate_candidates(ctx)
    assert not apres, "le seuil ne gate pas : 4 allies passent encore un seuil de 99"


def test_etage5b_baisser_le_seuil_ouvre_un_regime_qui_refusait(monkeypatch):
    """MUTATION SYMETRIQUE -- sans elle, un port qui refuserait TOUT passerait l'etage 5."""
    pb = PLAYBOOKS[SQUIG]
    ctx = P.ctx_pour([(P.CIBLE_ID, P.T)], P._anneau(1, P.ORK))
    assert not pb.generate_candidates(ctx), "temoin : 1 Ork doit REFUSER (seuil 2)"

    monkeypatch.setattr(type(pb), "_threshold", lambda self, key: 1, raising=True)
    assert pb.generate_candidates(ctx), "avec un seuil de 1, 1 Ork adjacent doit ACCEPTER"


# --- etage 6 : le verdict de 1168 ---------------------------------------------------------------

def test_etage6_1168_porte_un_verdict_rien_a_porter_valide_sur_ce_build():
    """`RIEN_A_PORTER` n'est pas une absence : c'est un VERDICT, et il doit etre lisible par le
    foyer de validite. Une attestation PERIMEE (build change, cliquet disparu) REMET l'item au
    compte des manquants -- c'est l'asymetrie voulue du ledger, verifiee ici."""
    att = DFV.attestations()
    e = att.get("EntropyCannons")
    assert e is not None, (
        "aucune attestation VALIDE pour EntropyCannons (verdict absent ou perime sur le build %s)"
        % CA.build_courant())
    assert e["verdict"] == "RIEN_A_PORTER"
    assert e["build"] == CA.build_courant()
    etat, detail = DFV.etat(ENTROPY, "EntropyCannons")
    assert etat == "CONSTANTE", "etat inattendu pour 1168 : %s (%s)" % (etat, detail)


def test_etage6b_1168_n_est_dans_aucun_registre_de_face_decision():
    """Le verdict EST le couple << atteste ET absent des registres >>. L'inscrire quelque part
    serait un port SPECULATIF : son `MakeDamagePredictions` est la forme CANONIQUE (meme `h_body`
    que `LashOfTorment`, deja attestee, et que `MightFromBelow`), donc le chemin GENERIQUE du port
    EST deja son mirror."""
    assert ENTROPY not in PLAYBOOKS
    assert ENTROPY not in REGISTRY
    assert DFV.face_portee(ENTROPY, "EntropyCannons") == [], (
        "1168 est inscrite a une voie de registre alors qu'elle est attestee RIEN_A_PORTER")
