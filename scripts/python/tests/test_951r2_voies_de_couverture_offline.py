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
        # #979 : `audit_kit_coverage` etablit la face DECISION par ce foyer (14 voies PARTITIONNEES)
        # au lieu de sa propre liste blanche -- un ajout/retrait y change ses verdicts.
        "scripts/python/decision_face_voies.py",
        # #1024-r5 : le SECOND cran du gate de `kit_item_voies` lit la table de symboles du build
        # (`classe_d_effet_native`) -- une table absente ou un build desynchronise fait degrader le
        # gate vers PARTIEL, donc change les verdicts que ce fichier confronte.
        "scripts/python/build_pin.py", "scripts/python/symbols_layout.py",
        "scripts/python/il2cpp_provenance.py",
        # #962 : l'etage [3bis] LE JOUE en sous-processus -- c'est la SECONDE source du croisement,
        # donc une modification du recenseur peut changer le verdict de ce fichier.
        "scripts/python/probe_951r2_faux_manquants.py",
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
#: LA VOIE, et le PORTEUR par lequel on l'exerce. La cle est le nom du registre, la valeur un
#: couple `(registre, porteur)` -- `None` = le porteur est DERIVE du registre a l'execution.
#:
#: ⚠ POURQUOI CET ETAGE A CHANGE DE SUBSTRAT (#962). Il paramétrait quatre passifs NON PORTES et
#: exigeait qu'ils le restent. Ca ne pouvait pas tenir, et ce n'est pas une opinion : la population
#: des non-portes est celle que le projet a pour but de VIDER. Mesure, sur la seule duree de cette
#: tranche -- `Skullsmasher` (#953/#954) et `MedicusMinistorum` (#955) etaient deja portes a son
#: lancement ; `TimesplinterMantle`, choisi sur une mesure FRAICHE, a ete porte par #961 pendant
#: qu'elle courait ; puis `RedRampage` (#963), `WhisperingWeb` et `RefusalToBeOutdone` (#965) --
#: SIX peremptions, et la population des passifs non couverts est tombee de 12 a 3 en une journee.
#: Un etage qui rougit a chaque port n'est pas un cliquet, c'est une cadence d'echec.
#:
#: LE SENS DE LA MESURE EST DONC INVERSE, et c'est ce qui la rend durable : au lieu d'exiger qu'un
#: NON-PORTE reste non couvert (population qui tend vers zero), on MUTE la voie d'un PORTE et on
#: exige que le predicat le remarque (population qui ne fait que croitre). C'est l'idiome
#: `--mutants` de `probe_547` / #421 : un cliquet dont on n'a pas montre qu'il MORD est un vert qui
#: ne prouve rien.
#:
#: TROIS PROPRIETES, et la troisieme est la raison de ne PAS s'en remettre au seul etage [3bis] :
#:   * il ne se perime pas -- un port ne se DE-porte pas, et un registre ne se vide pas ;
#:   * il n'est pas tautologique -- la source est le REGISTRE, qu'on mute, pas `_passive_covered` ;
#:   * il est INDEPENDANT du recenseur `probe_951r2_faux_manquants.py`. Si celui-ci se cassait en
#:     rendant assez de noms mais en perdant les bons, [3bis] deviendrait aveugle et CET etage,
#:     lui, continuerait de mordre. C'etait la seule propriete que les temoins figes apportaient
#:     et que [3bis] n'a pas ; elle est conservee.
VOIES_A_MUTER = {
    # `FireOfAbsolution` et `DawnBlade` sont deja les temoins de l'etage [1] : si leur port
    # disparaissait, [1] rougirait AVANT celui-ci -- la premisse est donc gardee ailleurs.
    "IMPERATIVE_ABILITY_VECTORS": (IMPERATIVE_ABILITY_VECTORS, "FireOfAbsolution"),
    "RELIC_ABILITY_TRIGGERS": (RELIC_ABILITY_TRIGGERS, "DawnBlade"),
    # DERIVE : le registre principal n'a pas de temoin fige -- on prend son premier nom trie, donc
    # rien a re-choisir quand il bouge.
    "ABILITY_TRIGGERS": (ABILITY_TRIGGERS, None),
}


@pytest.mark.parametrize("voie", sorted(VOIES_A_MUTER))
def test_le_predicat_REMARQUE_le_retrait_d_une_voie_de_port(voie):
    """L'axe dangereux, mesure par MUTATION. On retire du registre la cle d'un passif REELLEMENT
    porte, et on exige que `_passive_covered` bascule a False. S'il reste True, il ne LIT plus
    cette voie -- il est devenu PERMISSIF, et l'audit fera RENONCER a du travail reel.

    Un audit qui sous-compte est PIRE qu'un audit qui sur-compte : il fait renoncer au lieu de
    faire perdre du temps. La mutation est defaite dans un `finally` -- l'etat du registre est
    re-verifie APRES, parce qu'un cliquet qui laisse le processus altere contamine ses voisins de
    shard (le canal MEMOIRE de #956-r1)."""
    registre, porteur = VOIES_A_MUTER[voie]
    assert registre, "PREMISSE : le registre `%s` est VIDE -- il n'y a rien a muter" % voie
    if porteur is None:
        porteur = sorted(registre)[0]
    assert porteur in registre, (
        "PREMISSE : `%s` n'est plus dans `%s`. Si son port a ete retire, c'est l'etage [1] qui "
        "doit le dire ; ici il n'y a plus rien a mesurer." % (porteur, voie))
    assert AKC._passive_covered(porteur), (
        "PREMISSE : `%s` est inscrit dans `%s` mais `_passive_covered` le declare deja NON "
        "couvert. La mutation ci-dessous ne mesurerait rien -- c'est le predicat qui ne lit pas "
        "cette voie, et c'est deja le defaut de #951-r2." % (porteur, voie))

    sauve = registre.pop(porteur)
    try:
        assert not AKC._passive_covered(porteur), (
            "PERMISSIVITE : `%s` reste declare COUVERT alors que son entree a ete retiree de "
            "`%s` -- la SEULE voie qui le portait. `_passive_covered` ne lit donc plus ce "
            "registre, ou rend `True` par un chemin qui ne depend pas de lui." % (porteur, voie))
    finally:
        registre[porteur] = sauve
    assert AKC._passive_covered(porteur), (
        "MUTATION NON DEFAITE : `%s` n'est pas redevenu couvert apres restauration de `%s`. Ce "
        "test vient de laisser le processus dans un etat altere." % (porteur, voie))


def test_la_mutation_porte_sur_des_voies_REELLEMENT_DISTINCTES():
    """NON-DEGENERESCENCE de la table elle-meme : trois entrees qui pointeraient le MEME objet
    mesureraient une seule voie en se donnant l'air d'en mesurer trois."""
    ids = {voie: id(reg) for voie, (reg, _p) in VOIES_A_MUTER.items()}
    assert len(set(ids.values())) == len(ids), (
        "des entrees de `VOIES_A_MUTER` designent le MEME registre : %r" % ids)
    assert len(VOIES_A_MUTER) >= 3, (
        "moins de trois voies mutees : l'etage a perdu de la portee sans que rien ne le dise")


# --------------------- [3bis] LE MEME AXE, DERIVE : il ne peut pas se perimer
#: Memoisation : le recenseur coute ~60 s (il importe les 561 modules `engine.**`) et DEUX tests
#: le consomment. Le sentinelle distingue << pas encore appele >> de << appele, resultat None >> --
#: une panne de mesure ne doit pas etre re-tentee en silence ni confondue avec un resultat.
_SANS_TRACE_CACHE: list = []


def _passifs_sans_trace_structurelle() -> list:
    """Les passifs que le RECENSEUR STRUCTUREL range en << AUCUNE TRACE STRUCTURELLE >>.

    SOURCE INDEPENDANTE, et c'est tout l'interet : `probe_951r2_faux_manquants.py` n'interroge
    AUCUN registre par son nom -- il importe les 561 modules `engine.**`, visite tout attribut de
    module qui est un conteneur (donc tout registre, connu ou non, decouvert par sa FORME) et tout
    symbole defini dont le nom snake_case cite l'item (la voie IMPERATIVE, qui n'a par construction
    aucun registre). `_passive_covered`, lui, lit une liste de voies. Les confronter n'est donc pas
    une tautologie : c'est exactement le croisement que #951-r2 a du faire a la main.

    SOUS-PROCESSUS, delibere : le recenseur importe tout `engine.**`, ce qui polluerait
    `sys.modules` de la passe et rendrait ce fichier dependant de son voisinage de shard
    (le canal MEMOIRE de #956-r1). Il rend `None` s'il n'a pas pu mesurer -- jamais une liste vide,
    qui se lirait comme << rien a signaler >>."""
    import subprocess
    try:
        r = subprocess.run([sys.executable, "probe_951r2_faux_manquants.py"],
                           cwd=_PYROOT, capture_output=True, text=True, timeout=900)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode not in (0, 1) or "AUCUNE TRACE STRUCTURELLE" not in (r.stdout or ""):
        return None
    dedans, out = False, []
    for ln in r.stdout.splitlines():
        if ln.startswith("=== AUCUNE TRACE STRUCTURELLE"):
            dedans = True
            continue
        if dedans and ln.startswith("==="):
            break
        if dedans and ln.startswith("[passif] "):
            out.append(ln[len("[passif] "):].split(" ")[0])
    return out


def _sans_trace_memoise() -> list:
    """`_passifs_sans_trace_structurelle` appelee UNE fois par passe. `None` (panne de mesure) est
    memoise comme tel : on ne re-tente pas, et on ne le confond pas avec une liste vide."""
    if not _SANS_TRACE_CACHE:
        _SANS_TRACE_CACHE.append(_passifs_sans_trace_structurelle())
    return _SANS_TRACE_CACHE[0]


def test_tout_passif_SANS_TRACE_structurelle_reste_compte_manquant():
    """L'axe dangereux de l'etage [3], mais sur une population DERIVEE au lieu de quatre noms figes.

    INVARIANT : un passif dont le recenseur structurel ne trouve NI registre NI symbole dedie dans
    les 561 modules `engine.**`, et qui n'a AUCUNE attestation, DOIT etre compte manquant. Si l'un
    d'eux devenait << couvert >>, `_passive_covered` serait devenu PERMISSIF -- et l'audit ferait
    RENONCER a du travail reel, ce qui est pire qu'un audit qui sur-compte.

    Il ne se PERIME pas : quand un passif est porte, il acquiert une trace et SORT de la population
    tout seul. C'est ce que les quatre temoins figes ci-dessus ne savent pas faire -- mesure de
    cette tranche : DEUX d'entre eux etaient deja perimes en arrivant, un TROISIEME l'est devenu
    pendant qu'elle courait."""
    sans_trace = _sans_trace_memoise()
    assert sans_trace is not None, (
        "RECENSEUR MUET : `probe_951r2_faux_manquants.py` n'a pas rendu sa section << AUCUNE TRACE "
        "STRUCTURELLE >>. Un recenseur qui ne mesure pas ne rend PAS une liste vide -- ce test "
        "rougit plutot que de passer sur du vide.")
    # ⚠ CE SEUIL EST A 1, ET C'EST UNE MESURE, PAS UNE INDULGENCE. La population des passifs sans
    # trace est celle que le projet a pour but de VIDER : 12 au matin du 2026-08-12, 3 le soir.
    # Le jour ou elle atteindra ZERO, cet etage deviendra inerte PAR CONSTRUCTION -- et c'est
    # exactement pourquoi l'etage [3] ci-dessus a change de substrat : lui MUTE un PORTE, donc il
    # se nourrit de la population qui CROIT. Ecrire ici un seuil plus haut ferait rougir la
    # tranche qui FINIT le portage, ce qui serait absurde.
    if not sans_trace:
        # LE JOUR PREDIT PAR LE PARAGRAPHE CI-DESSUS EST ARRIVE : 2026-08-13, `WayOfTheShortBlade`
        # (#1019) etait le DERNIER passif sans trace structurelle, et la population est tombee a
        # ZERO. La consigne ecrite dans l'ancien message d'echec etait << il faut le DIRE ici >> :
        # c'est ce que fait cette branche. Le seuil `>= 1` faisait rougir la tranche qui FINIT le
        # portage -- exactement ce que son propre commentaire qualifiait d'absurde. C'est le
        # CINQUIEME seuil de la journee a rougir sur le PROGRES (apres les trois de #1015 et celui
        # du merge de #1011).
        #
        # L'etage est desormais INERTE PAR CONSTRUCTION, et son inertie est SANS DANGER a une
        # condition : que la garde de permissivite n'ait pas de fenetre. On la verifie donc ici
        # DIRECTEMENT, par un TEMOIN -- un nom FABRIQUE, hors enum et hors ledger, que
        # `_passive_covered` doit refuser. C'est litteralement l'enonce que cet etage protegeait
        # (<< le predicat n'est pas devenu permissif >>), et il ne doit RIEN a la population : il
        # reste vrai que la liste compte 12 passifs, 3, ou zero.
        temoin = "TemoinPassifQuiNExisteDansAucunRegistre951r2"
        assert not AKC._passive_covered(temoin), (
            "PREDICAT PERMISSIF : `_passive_covered` rend VRAI sur un nom FABRIQUE (`%s`). La "
            "population des passifs sans trace est vide, donc cet etage ne peut plus rien "
            "attraper par elle -- ce temoin est ce qui reste, et il vient de tomber." % temoin)
        assert AKC._atteste("passif", temoin) is None, (
            "le ledger d'attestations rend une entree pour un nom FABRIQUE (`%s`)" % temoin)
        print("[951r2] passifs SANS TRACE structurelle : 0 -- etage INERTE par construction, "
              "garde de permissivite tenue par le temoin et par l'etage [3] (mutation).")
        return
    couverts = [n for n in sans_trace if AKC._passive_covered(n)]
    assert not couverts, (
        "SOUS-COMPTAGE : %s declare(nt) couvert(s) alors que le recensement STRUCTUREL ne leur "
        "trouve ni registre ni symbole dedie dans les 561 modules `engine.**`. Les deux sources "
        "sont INDEPENDANTES : leur desaccord signale un predicat devenu permissif, ou un port "
        "reel que le recenseur ne voit pas -- dans les deux cas, il faut le trancher a la main."
        % sorted(couverts))
    attestes = [n for n in sans_trace if AKC._atteste("passif", n) is not None]
    assert not attestes, (
        "%s : attestation(s) posee(s) sur un passif sans aucune trace structurelle. Si c'est "
        "delibere (verdict RIEN_A_PORTER), ce test doit changer AVEC la mesure qui l'etablit."
        % sorted(attestes))


def test_le_predicat_refuse_un_nom_inexistant():
    """Controle negatif elementaire : sans lui, un predicat rendu permissif passerait toute la
    garde au vert."""
    assert not AKC._passive_covered("ZzzAbilityQuiNExistePas")
    assert AKC._atteste("passif", "ZzzAbilityQuiNExistePas") is None


def test_le_total_CONCORDE_avec_le_recensement_structurel():
    """Ce test etait un PLANCHER (`total >= 10`), et le plancher est mort de sa belle mort : le
    total est tombe a 5 le 2026-08-12 parce que le portage AVANCE, pas parce que le predicat a
    derive. Un seuil qui rougit quand le travail progresse fait relever le seuil -- c'est la
    degradation decrite par `feedback_threshold_guard_decays`, et elle etait ici garantie.

    L'INVARIANT qui le remplace ne se perime pas : le total des items comptes manquants ne peut
    pas etre INFERIEUR au nombre de passifs que le recensement STRUCTUREL range sans aucune trace.
    Les deux descendent ensemble quand on porte ; ils DIVERGENT quand le predicat devient
    permissif -- ce qui est exactement le signal cherche, et sur une borne DERIVEE au lieu d'un
    chiffre ecrit a la main.

    ⚠ Cet invariant est plus FAIBLE que l'ancien plancher sur un point, et c'est assume : il
    tolere un total nul si le recensement est vide. La permissivite, elle, reste gardee par
    l'etage [3] (mutation), qui ne depend d'aucune population decroissante."""
    total = sum(r["missing"] for r in AKC.collect())
    sans_trace = _sans_trace_memoise()
    assert sans_trace is not None, (
        "RECENSEUR MUET : impossible de deriver la borne. Ce test rougit plutot que de se rabattre "
        "sur un plancher ecrit a la main.")
    assert total >= len(sans_trace), (
        "SOUS-COMPTAGE : le total d'items comptes manquants (%d) est INFERIEUR au nombre de "
        "passifs que le recenseur structurel range sans aucune trace (%d : %s). Les deux sources "
        "sont independantes ; leur divergence signale un predicat de couverture devenu permissif."
        % (total, len(sans_trace), sorted(sans_trace)))


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


def test_la_lecture_des_voies_conditionnelles_reste_DISCRIMINANTE():
    """Contre-garde d'inventaire, heritee de #341 : la lecture de `RELIC_ABILITY_TRIGGERS` ne doit
    pas vider la section conditionnelle de sa substance.

    CE QUE CETTE GARDE A REMPLACE, ET POURQUOI. Elle exigeait `len(ouvertes) >= 20` -- un PLANCHER
    DE POPULATION. Ce critere ne mesure pas ce que la docstring annonce : il tombe quand le travail
    AVANCE (mesure du 2026-08-13 : le port de `NornCrown` a fait passer la section de 20 a 19, donc
    `master` serait devenu rouge POUR AVOIR PORTE UNE ABILITY), et il resterait VERT si le predicat
    devenait reellement permissif tant qu'il reste 20 items. Il rougit sur le progres et se tait sur
    la regression -- l'exact inverse de son intention. Meme forme que les trois seuils remplaces par
    #1015, et que celui de #1008 avant eux.

    L'INVARIANT QU'IL APPROXIMAIT est que la lecture DISCRIMINE, et il se garde par un TEMOIN, donc
    sans rien devoir a la cadence de portage :
      (a) le recensement VISITE quelque chose (son propre non-vide) ;
      (b) un nom qui n'est dans AUCUN registre revient `covered = False`. C'est litteralement
          << la lecture n'est pas permissive >>, et c'est vrai que la section compte 20 items
          ouverts ou zero ;
      (c) la partition est exhaustive -- `covered` est un booleen sur CHAQUE entree, aucune ne peut
          rester muette.
    Le compte d'ouvertes reste IMPRIME (il descend a mesure qu'on porte, c'est le but), il ne fait
    plus office de critere."""
    name2id = {v: k for k, v in EM.ACTIVE_ABILITY_TYPE.items()}
    cond = AKC.collect_conditionnelles(name2id)

    # (a) le recensement visite quelque chose -- sinon tout ce qui suit serait vrai par vacuite.
    assert cond, ("recensement conditionnel VIDE : plus aucune ability n'atteint une unite `lineup` "
                  "par `mythicAbilities` ou par une relique equipable. Un recenseur qui ne visite "
                  "rien ne peut rien rendre.")

    # (c) partition exhaustive : chaque entree porte un verdict booleen, aucune n'est muette.
    muettes = [c["name"] for c in cond if not isinstance(c.get("covered"), bool)]
    assert muettes == [], "entrees conditionnelles sans verdict booleen : %r" % muettes

    # (b) LE TEMOIN -- un nom fabrique, absent de tout registre et de tout ledger. Si la lecture le
    # declare couvert, elle est devenue permissive, et ce constat ne depend d'AUCUNE population.
    temoin = "TemoinNomQuiNExistePasDansAucunRegistre951r2"
    assert temoin not in name2id, "le temoin doit rester un nom FABRIQUE, hors enum"
    assert not AKC._passive_covered(temoin), (
        "LECTURE PERMISSIVE : `_passive_covered` rend VRAI sur un nom fabrique (`%s`) qui n'est "
        "dans aucun registre. Toute la section conditionnelle serait alors declaree couverte, et le "
        "compte d'ouvertes tomberait a zero pour une raison qui n'est pas du travail fait." % temoin)
    assert AKC._atteste("conditionnelle-item", temoin) is None, (
        "le ledger d'attestations rend une entree pour un nom fabrique (`%s`)" % temoin)

    ouvertes = [c for c in cond if not c["covered"]]
    print("[951r2] voies conditionnelles : %d entrees, %d ouvertes" % (len(cond), len(ouvertes)))
