"""#951-r2 -- garde OFFLINE : l'audit de kit VOIT ce qui est porte, et ne fait taire RIEN d'autre.

Deux mecanismes distincts produisaient le MEME symptome -- un item PORTE compte MANQUANT, donc un
agent dispatche sur du travail deja fait :

  1. **une voie de port que l'auditeur ne lit pas** -- `FireOfAbsolution` est joue par un APPEL
     IMPERATIF (`dispatch/ability.py`), donc il n'a AUCUNE entree de registre a lire ; `DawnBlade`
     vit dans `RELIC_ABILITY_TRIGGERS`, un registre qui EXISTAIT et n'etait pas lu ;
  2. **un verdict etabli que rien ne memorise** -- `1204 LeadingTheCharge` est prouvee SANS CONTENU
     PROPRE (#945) et `GalvanicField` a un verdict MESURE (#952) ; ecrits dans une case-doc, ces
     verdicts ne survivaient a aucune regeneration.

⚠ L'AXE DANGEREUX EST L'AUTRE. Un audit qui SOUS-compte fait RENONCER, ce qui est pire qu'un audit
qui sur-compte et fait perdre du temps. Les etages [3] et [4] sont donc les etages LOAD-BEARING :
ils exigent qu'un item reellement non porte REVIENNE toujours, et que la peremption d'une
attestation le REMETTE au compte.

Usage : depuis `scripts/python/`
    python -m pytest tests/test_951r2_voies_de_couverture_offline.py -q
"""
from __future__ import annotations

import ast
import copy
import os
import sys

import pytest

_PYROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PYROOT not in sys.path:
    sys.path.insert(0, _PYROOT)

DECLENCHEUR = {
    "chemins": (
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        # les deux auditeurs et le foyer de validite
        "scripts/python/audit_kit_coverage.py",
        "scripts/python/audit_combat_ability_coverage.py",
        "scripts/python/coverage_attestations.py",
        "scripts/ratchets-951r2-couverture-attestee.json",
        # les VOIES de port que l'audit lit -- toucher l'une d'elles peut rouvrir un faux manquant
        "scripts/python/engine/runner/operations/triggers/dispatch/ability.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/registry.py",
        "scripts/python/engine/entities/effects/factory.py",
        "scripts/python/engine/services/custom_normal_attack.py",
        "scripts/python/engine/entities/abilities/active_ability.py",
        "scripts/python/engine/playbook/noncomparable/__init__.py",
        "scripts/python/engine/runner/abilities/handler.py",
        # les ANCRAGES des attestations livrees : si l'un disparait, l'attestation doit PERIMER
        "scripts/python/engine/services/targeting_query.py",
        "scripts/python/engine/runner/abilities/repair.py",
        "scripts/python/tests/engine/test_945_loki_decision_faces_offline.py",
        "scripts/python/tests/engine/test_952_hunters_beyond_death_offline.py",
        "scripts/python/unit_map.py", "scripts/python/gameconfig.py",
        "scripts/python/enum_maps.py",
        # lu par `unit_map` en amont du recensement des kits (libelles i2)
        "data/i2_en.json",
    ),
    "build": True,
    "toujours": False,
    "raison": "Offline : garde les DEUX mecanismes de faux manquant de #951-r2 (une voie de port "
              "non lue ; un verdict etabli que rien ne memorise) et, surtout, l'axe DANGEREUX -- "
              "qu'un item reellement non porte REVIENNE toujours, et qu'une attestation perimee "
              "REMETTE son item au compte. Lit le gameconfig du build (kits lineup, traits, "
              "voies d'attribution) et `data/symbols/CURRENT` (clause de peremption) -> "
              "`build: True`.",
}

import audit_kit_coverage as AKC                     # noqa: E402
import coverage_attestations as CA                   # noqa: E402
import enum_maps as EM                               # noqa: E402
from engine.runner.operations.triggers.dispatch.ability import (   # noqa: E402
    IMPERATIVE_ABILITY_VECTORS,
)
from engine.runner.operations.triggers.dispatch.registry import (  # noqa: E402
    ABILITY_TRIGGERS, RELIC_ABILITY_TRIGGERS,
)
from engine.entities.effects.factory import ABILITY_INIT_OWNER_EFFECTS   # noqa: E402
from engine.services.custom_normal_attack import (   # noqa: E402
    CUSTOM_NORMAL_ATTACK_BY_PASSIVE,
)

_VECTEUR_SRC = os.path.join(_PYROOT, "engine", "runner", "operations", "triggers",
                            "dispatch", "ability.py")


# ------------------------------------------------------------------ [1] les deux cas NOMMES
def test_cas_nomme_fire_of_absolution_est_vu_comme_couvert():
    """Le cas canonique de #951-r2. `FireOfAbsolution` (`adeptRetributor`) est porte EN ENTIER
    (`fire_of_absolution_tree` + `_fire_of_absolution_after_attack`, branches sur
    `On(AttackInAtomicGroup)`) et n'a AUCUNE entree de registre, parce que son vecteur est un appel
    imperatif. L'auditeur le comptait manquant."""
    assert AKC._passive_covered("FireOfAbsolution"), (
        "REGRESSION #951-r2 : `FireOfAbsolution` redevient un faux MANQUANT. La voie IMPERATIVE "
        "(`IMPERATIVE_ABILITY_VECTORS` de `dispatch/ability.py`) n'est plus lue par "
        "`_passive_covered` -- ou l'entree a disparu du registre.")


def test_cas_nomme_dawn_blade_est_vu_par_le_registre_de_RELIQUE():
    """`RELIC_ABILITY_TRIGGERS` est SEPARE d'`ABILITY_TRIGGERS` a dessein (montage natif distinct) --
    et c'est cette separation meme qui le rendait invisible a `_passive_covered`."""
    assert "DawnBlade" in RELIC_ABILITY_TRIGGERS, "premisse : le port de DawnBlade a disparu"
    assert AKC._passive_covered("DawnBlade"), (
        "REGRESSION #951-r2 : `RELIC_ABILITY_TRIGGERS` n'est plus lu par `_passive_covered`. "
        "`DawnBlade` (`tauFarsight`) redevient un faux manquant alors que `DawnBladeHealAbility` "
        "est portee.")


def test_cas_nomme_leading_the_charge_n_est_plus_compte_sans_face_DECISION():
    """#945 §7 a PROUVE que `LeadingTheChargePlaybook$$MakeDamagePredictions` est structurellement
    identique au corps generique. L'audit la recomptait manquante a chaque regeneration -- c'est le
    second mecanisme, et il ne se repare pas par une voie de plus : il se repare par une
    ATTESTATION."""
    rows = AKC.collect()
    hits = [a for r in rows for a in r["actives"] if a["name"] == "LeadingTheCharge"]
    assert hits, "premisse : `LeadingTheCharge` n'est plus dans aucun kit lineup"
    assert all(a["decision"] for a in hits), (
        "REGRESSION #951-r2 : `1204 LeadingTheCharge` est de nouveau comptee sans face DECISION. "
        "Son verdict `RIEN_A_PORTER` est perime ou absent du ledger -- verifier "
        "`python coverage_attestations.py`.")


def test_cas_nomme_galvanic_field_est_vu_comme_couvert():
    """Verdict MESURE par #952 : trois feuilles branchees, playbook a `Fix64(0)` sur les deux faces."""
    assert AKC._atteste("passif", "GalvanicField") is not None, (
        "REGRESSION #951-r2 : l'attestation de `GalvanicField` n'est plus VALIDE.")
    rows = AKC.collect()
    hits = [p for r in rows for p in r["passives"] if p["name"] == "GalvanicField"]
    assert hits and all(p["covered"] for p in hits), (
        "REGRESSION #951-r2 : `GalvanicField` est recompte manquant malgre le verdict #952.")


# ------------------------------------------------ [2] la DOUBLE declaration, et pourquoi elle tue
def test_la_voie_imperative_est_DISJOINTE_des_autres_registres_de_passif():
    """⚠ Un garde d'EXISTENCE est aveugle a la DOUBLE declaration. Ici la double declaration n'est
    pas une redondance benigne : inscrire un nom a la fois dans `IMPERATIVE_ABILITY_VECTORS` et dans
    un registre de trigger le ferait jouer DEUX FOIS -- c'est exactement ce que le parametre
    `fire_of_absolution=False` d'`evaluate_abilities_for_event` existe pour empecher sur la voie
    normale. Le symptome serait un splash double, sans erreur."""
    autres = {
        "ABILITY_TRIGGERS": set(ABILITY_TRIGGERS),
        "ABILITY_INIT_OWNER_EFFECTS": set(ABILITY_INIT_OWNER_EFFECTS),
        "CUSTOM_NORMAL_ATTACK_BY_PASSIVE": set(CUSTOM_NORMAL_ATTACK_BY_PASSIVE),
        "RELIC_ABILITY_TRIGGERS": set(RELIC_ABILITY_TRIGGERS),
    }
    for nom, reg in autres.items():
        chevauche = set(IMPERATIVE_ABILITY_VECTORS) & reg
        assert not chevauche, (
            "DOUBLE FIRE : %s est declare(s) a la fois dans `IMPERATIVE_ABILITY_VECTORS` et dans "
            "`%s`. Le passif serait joue deux fois par attaque -- pas une double couverture, un "
            "BUG. Choisir UNE voie." % (sorted(chevauche), nom))


def test_chaque_vecteur_declare_est_REELLEMENT_appele_dans_son_module():
    """Une declaration morte serait pire que l'absence : elle ATTESTE une couverture que rien ne
    porte. Le controle est STRUCTUREL (AST du module qui declare), pas un grep : le callable doit
    apparaitre en position d'APPEL dans le fichier meme ou le registre vit."""
    with open(_VECTEUR_SRC, encoding="utf-8") as f:
        arbre = ast.parse(f.read())
    appeles = {n.func.id for n in ast.walk(arbre)
               if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    for nm, fn in IMPERATIVE_ABILITY_VECTORS.items():
        assert callable(fn), "`%s` declare une valeur non appelable : %r" % (nm, fn)
        assert fn.__name__ in appeles, (
            "DECLARATION MORTE : `%s` -> `%s` est inscrit a `IMPERATIVE_ABILITY_VECTORS`, mais ce "
            "callable n'est APPELE nulle part dans `dispatch/ability.py`. L'audit compterait donc "
            "`%s` couvert sans que rien ne le joue -- exactement le sous-comptage que #951-r2 "
            "existe pour empecher, dans l'autre sens." % (nm, fn.__name__, nm))


# --------------------------------------------- [3] CONTRE-EPREUVE : un vrai manquant revient TOUJOURS
#: Temoins MESURES le 2026-08-12 (#962) par `probe_951r2_faux_manquants.py` : chacun figure dans la
#: section << AUCUNE TRACE STRUCTURELLE >> -- ni registre, ni symbole dedie dans les 561 modules
#: `engine.**`, et aucune attestation.
#:
#: ⚠ CE PARAMETRAGE PERIME PAR CONSTRUCTION, et c'est le seul entretien qu'il demande : le jour ou
#: l'un de ces passifs est PORTE, ce test rougit. Le remede est alors de RE-CHOISIR un temoin dans
#: la liste courante des vrais manquants (`probe_951r2_faux_manquants.py`, section << AUCUNE TRACE
#: STRUCTURELLE >>, categorie `passif`) -- JAMAIS de retirer le temoin sans le remplacer, ce qui
#: viderait l'etage load-bearing en silence. Precedent : `Skullsmasher` (#953/#954) et
#: `MedicusMinistorum` (#955) ont ete portes, et leur ligne est restee ici, rendant `master` rouge.
TEMOINS_NON_PORTES = ["RedRampage", "WhisperingWeb", "TimesplinterMantle", "RefusalToBeOutdone"]


@pytest.mark.parametrize("nom", TEMOINS_NON_PORTES)
def test_un_passif_reellement_NON_porte_reste_compte_manquant(nom):
    """L'axe dangereux. Ces quatre passifs n'ont AUCUNE trace structurelle dans `engine/**`
    (recensement `probe_951r2_faux_manquants.py` : ni registre, ni symbole dedie) et aucune
    attestation. Si l'un d'eux devient << couvert >>, le predicat est devenu PERMISSIF et l'audit
    fait desormais RENONCER a du travail reel."""
    # NON-DEGENERESCENCE : un temoin qui aurait disparu du gameconfig rendrait `not covered`
    # trivialement vrai, et l'etage passerait au vert en ne mesurant plus rien.
    porteurs = [r["id"] for r in AKC.collect()
                for p in r["passives"] if p["name"] == nom]
    assert porteurs, (
        "TEMOIN DEGENERE : `%s` ne figure dans le passif d'AUCUN kit lineup -- l'assertion "
        "ci-dessous serait vraie sans rien mesurer. Re-choisir un temoin dans la liste courante "
        "des vrais manquants (`probe_951r2_faux_manquants.py`)." % nom)
    assert not AKC._passive_covered(nom), (
        "SOUS-COMPTAGE : `%s` est declare couvert alors qu'aucun registre ne le porte. Un audit "
        "qui sous-compte est PIRE qu'un audit qui sur-compte : il fait renoncer au lieu de faire "
        "perdre du temps. (Si `%s` vient d'etre PORTE, ce test est a JOUR et c'est le TEMOIN qui "
        "est perime : le remplacer dans `TEMOINS_NON_PORTES`.)" % (nom, nom))
    assert AKC._atteste("passif", nom) is None, (
        "`%s` a recu une attestation : si c'est delibere, ce test doit changer AVEC la mesure qui "
        "l'etablit -- jamais l'inverse." % nom)


def test_les_temoins_couvrent_encore_une_part_des_vrais_manquants():
    """Garde de NON-DEGENERESCENCE de la LISTE elle-meme (et non de chaque temoin) : si la
    liste devenait vide ou se detachait de l'inventaire courant, l'etage [3] serait vert sans
    rien garder. Elle doit rester un SOUS-ENSEMBLE des passifs comptes manquants."""
    manquants = {p["name"] for r in AKC.collect() for p in r["passives"] if not p["covered"]}
    assert TEMOINS_NON_PORTES, "la liste de temoins est VIDE : l'etage [3] ne mesure plus rien"
    hors = [n for n in TEMOINS_NON_PORTES if n not in manquants]
    assert not hors, (
        "TEMOIN(S) HORS INVENTAIRE : %s ne figure(nt) plus parmi les passifs comptes manquants. "
        "Soit ils ont ete PORTES (re-choisir), soit le predicat est devenu permissif." % hors)


def test_le_predicat_refuse_un_nom_inexistant():
    """Controle negatif elementaire : sans lui, un predicat rendu permissif passerait toute la
    garde au vert."""
    assert not AKC._passive_covered("ZzzAbilityQuiNExistePas")
    assert AKC._atteste("passif", "ZzzAbilityQuiNExistePas") is None


def test_le_total_ne_s_est_pas_effondre():
    """Garde de PLANCHER : la reparation retire 3 items du total (FireOfAbsolution, GalvanicField,
    IndirectFire). Si le total tombait bien plus bas, c'est que le predicat est devenu permissif --
    la borne dit ce qu'elle borne, et elle ne fige pas le chiffre exact (il bouge a chaque port)."""
    total = sum(r["missing"] for r in AKC.collect())
    assert total >= 10, (
        "SOUS-COMPTAGE : le total d'items manquants est tombe a %d. Trois retraits sont attendus "
        "(#951-r2) ; un effondrement signale un predicat de couverture devenu permissif." % total)


# ----------------------------------- [4] la PEREMPTION d'une attestation REMET l'item au compte
def _entree(**kw):
    base = {
        "categorie": "passif", "nom": "ZzzSujet", "verdict": "RIEN_A_PORTER",
        "raison": "raison ecrite", "source": "docs/rl/case-945-loki-faces-decision.md#7",
        "build": CA.build_courant(),
        "cliquet": "scripts/python/tests/engine/test_945_loki_decision_faces_offline.py",
    }
    base.update(kw)
    return base


def test_une_attestation_complete_est_VALIDE():
    assert CA.validite(_entree(), CA.build_courant())[0] == CA.VALIDE


@pytest.mark.parametrize("mutation,attendu", [
    ({"build": "zzz_autre_build"}, "build"),
    ({"cliquet": "scripts/python/tests/zzz_inexistant.py"}, "cliquet"),
    ({"cliquet": "", "porteur": ""}, "ancrage"),
    ({"porteur": "engine.services.targeting_query:ZzzSymboleAbsent", "cliquet": ""}, "porteur"),
    ({"porteur": "zzz.module.absent:X", "cliquet": ""}, "porteur"),
    ({"raison": "   "}, "raison"),
    ({"source": "docs/rl/case-zzz-inexistante.md"}, "source"),
    ({"verdict": "PEUT_ETRE"}, "verdict"),
    ({"categorie": "zzz-inconnue"}, "categorie"),
])
def test_toute_clause_qui_tombe_fait_PERIMER(mutation, attendu):
    """Le foyer UNIQUE, balaye clause par clause. Chaque mutation doit PERIMER -- et une entree
    perimee ne figure PAS dans `attestations_valides`, donc son item redevient MANQUANT."""
    etat, raison = CA.validite(_entree(**mutation), CA.build_courant())
    assert etat == CA.PERIMEE, (
        "PERMISSIVITE : la mutation %r reste VALIDE. Une attestation qui survit a la disparition "
        "de son ancrage est une liste blanche deguisee." % (mutation,))
    assert attendu in raison.lower(), "raison de peremption peu parlante : %r" % raison


def test_une_categorie_ou_un_verdict_INCONNU_ne_s_evapore_pas():
    """Meme vice que #455-r3 / #465 : une valeur hors des categories connues ne doit pas rendre
    l'entree invisible au controle. La formule est INVERSE d'une selection de cas de peremption --
    on exige les conditions du SEUL cas permissif."""
    for champ in ("verdict", "categorie"):
        e = _entree(**{champ: None})
        assert CA.validite(e, CA.build_courant())[0] == CA.PERIMEE
    assert CA.validite({}, CA.build_courant())[0] == CA.PERIMEE
    assert CA.validite(None, CA.build_courant())[0] == CA.PERIMEE


def test_un_build_NON_LISIBLE_perime_tout_au_lieu_de_valoir_accord():
    """Tri-etat, meme regle que `host_inputs` : une mesure ABSENTE n'est jamais rendue comme un
    accord. Sans ce cran, un checkout sans `data/symbols/CURRENT` validerait toutes les
    attestations d'un coup."""
    etat, raison = CA.validite(_entree(), "")
    assert etat == CA.PERIMEE and "non lisible" in raison.lower()


def test_la_peremption_REMET_l_item_au_compte(tmp_path):
    """La contre-epreuve de bout en bout, sur le vrai `collect()` : un ledger dont l'attestation de
    `GalvanicField` est perimee doit faire REVENIR l'item dans les manquants. C'est la promesse
    centrale -- la peremption ne sait que RAJOUTER du travail."""
    perime = {"attestations": {"passif:GalvanicField": _entree(
        nom="GalvanicField", build="zzz_build_perime")}}
    sauve = AKC._ATTESTEES
    try:
        import json
        p = tmp_path / "ledger.json"
        p.write_text(json.dumps(perime), encoding="utf-8")
        AKC._ATTESTEES = CA.attestations_valides(str(p))
        assert ("passif", "GalvanicField") not in AKC._ATTESTEES
        hits = [p_ for r in AKC.collect() for p_ in r["passives"] if p_["name"] == "GalvanicField"]
        assert hits and not any(p_["covered"] for p_ in hits), (
            "PEREMPTION PERMISSIVE : l'attestation de `GalvanicField` est perimee et l'item reste "
            "decompte. Le sens de la degradation est INVERSE : une attestation perimee doit "
            "REMETTRE son item au compte des manquants.")
    finally:
        AKC._ATTESTEES = sauve


# ------------------------------------------------ [5] le ledger LIVRE est integralement verifiable
def test_toutes_les_attestations_livrees_sont_VALIDES():
    """Un ledger livre avec une entree deja perimee serait un cliquet mort ne : personne ne le
    regarderait, et l'item serait recompte sans qu'on sache pourquoi."""
    val, per = CA.ventiler()
    assert not per, ("attestation(s) PERIMEE(S) livree(s) : %s"
                     % [(c, r) for c, _e, r in per])
    assert val, "le ledger est VIDE : les deux cas mesures de #951-r2 ont disparu"


def test_chaque_attestation_porte_une_raison_ET_un_ancrage():
    """Anti « liste blanche » : la raison doit etre SUBSTANTIELLE et l'ancrage present. Sans ces
    deux exigences, le ledger redeviendrait le fichier d'exceptions que #951-r2 refuse."""
    for cle, e, _r in CA.ventiler()[0]:
        assert len((e.get("raison") or "")) >= 80, (
            "attestation `%s` : raison trop courte (%d car.) pour etre relisible. Ecrire CE QUI A "
            "ETE LU, pas << deja verifie >>." % (cle, len(e.get("raison") or "")))
        assert e.get("cliquet") or e.get("porteur"), "attestation `%s` sans ancrage" % cle
        assert e.get("_commit"), "attestation `%s` sans commit" % cle


def test_aucune_attestation_ne_contredit_un_registre():
    """Symetrique de la disjonction [2], cote verdict : attester `RIEN_A_PORTER` sur un nom qui EST
    dans un registre de port signifierait que l'une des deux ecritures ment. La contradiction doit
    rougir, pas se resoudre silencieusement en faveur de l'une des deux."""
    for cle, e, _r in CA.ventiler()[0]:
        if e["verdict"] != "RIEN_A_PORTER" or not e["categorie"].startswith(("passif", "trait")):
            continue
        assert e["nom"] not in ABILITY_TRIGGERS and e["nom"] not in RELIC_ABILITY_TRIGGERS, (
            "CONTRADICTION : `%s` est atteste RIEN_A_PORTER et figure pourtant dans un registre de "
            "trigger. L'un des deux ment." % cle)


def test_les_voies_conditionnelles_restent_non_vides():
    """Contre-garde d'inventaire, heritee de #341 : la lecture de `RELIC_ABILITY_TRIGGERS` ne doit
    pas vider la section conditionnelle de sa substance."""
    cond = AKC.collect_conditionnelles({v: k for k, v in EM.ACTIVE_ABILITY_TYPE.items()})
    ouvertes = [c for c in cond if not c["covered"]]
    assert len(ouvertes) >= 20, (
        "la section conditionnelle est tombee a %d abilities ouvertes : la lecture des nouveaux "
        "registres est devenue permissive." % len(ouvertes))
