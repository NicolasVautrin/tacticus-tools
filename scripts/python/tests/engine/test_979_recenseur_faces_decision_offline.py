"""#979 -- le CLIQUET du recenseur des faces DECISION.

CE QUE CE FICHIER GARDE
-----------------------
`probe_909_decision_actives_kit.py` et `audit_kit_coverage.py` etablissaient tous deux « la face
DECISION de cette active est portee » en testant une LISTE BLANCHE de registres, ECRITE A LA MAIN
et DIFFERENTE dans les deux outils (3 registres chez l'un, 4 chez l'autre). Elles avaient deja rate
deux voies, MESUREES -- `BESPOKE_SELFCAST` (#971, 3 faux GAP dont un a fait redispatcher un agent)
puis `_MAKE_DMG_INPUT_OVERRIDES` (#974). Le gisement se rouvre a NOTRE PROPRE cadence : chaque lot
de portage qui invente un registre le creuse.

Le foyer `decision_face_voies.py` n'ENUMERE plus les voies : il PARTITIONNE un perimetre. Ce
fichier garde les cinq proprietes sans lesquelles la partition ne vaudrait rien :

  1. AUCUN conteneur MUET ni FANTOME (c'est le cliquet lui-meme) ;
  2. les DEUX consommateurs rendent le MEME verdict (ils divergeaient) ;
  3. les deux voies historiquement ratees sont VUES, et les retirer fait retomber leurs abilities ;
  4. l'etat est TERNAIRE, et une attestation PERIMEE REMET l'item au compte des manquants ;
  5. un element qui « resout » ne prouve RIEN -- les registres clefs par `TriggeredAbilityType` et
     le tier `get_Priority` sont ECARTES, et les compter declarerait portees des faces qui ne le
     sont pas.

Chaque etage porte sa CONTRE-EPREUVE : la mutation est jouee, le rouge est constate, l'etat est
restaure. Un garde qu'on n'a pas vu mordre ne prouve rien.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import coverage_attestations as CA                               # noqa: E402
import decision_face_voies as DFV                                # noqa: E402
import enum_maps as EM                                           # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType  # noqa: E402

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
#: Perimetre pris LARGE : l'etage 1 partitionne TOUT `engine/playbook/**` et `active_ability.py`,
#: donc n'importe quel fichier de ces arbres peut y ajouter un conteneur MUET. On le declare par
#: GLOB plutot que d'enumerer 128 chemins qui perimeraient au premier module neuf -- ce serait le
#: vice meme que ce fichier garde.
DECLENCHEUR = {
    "chemins": (
        # Le foyer, et les deux consommateurs que l'etage 2 confronte.
        "scripts/python/decision_face_voies.py",
        "scripts/python/probe_909_decision_actives_kit.py",
        "scripts/python/audit_kit_coverage.py",
        # Le ledger des verdicts CONSTANTE / PORTE_HORS_REGISTRE et son foyer de validite.
        "scripts/ratchets-951r2-couverture-attestee.json",
        "scripts/python/coverage_attestations.py",
        # Le PERIMETRE partitionne, en entier : tout module y ajoutant un conteneur de niveau
        # module keye par ability doit rejouer ce test.
        "scripts/python/engine/playbook/**/*.py",
        "scripts/python/engine/playbook/*.py",
        "scripts/python/engine/entities/abilities/active_ability.py",
        # La population et la table de noms dont les etages 2 a 5 se servent.
        "scripts/python/unit_map.py",
        "scripts/python/enum_maps.py",
        # L'etage 2 joue `audit_kit_coverage.collect()`, qui traverse le second auditeur
        # (`_classify`) et lit les libelles i2. Les deux entrent donc dans sa fermeture.
        "scripts/python/audit_combat_ability_coverage.py",
        "data/i2_en.json",
    ),
    # Le perimetre est lu sur DISQUE et la population depend du gameconfig + du dump de symboles :
    # un changement de BUILD peut inverser un verdict sans qu'aucun fichier Python ne bouge.
    "build": True,
    "toujours": True,
    "raison": ("la partition lit l'arbre `engine/playbook/**` sur DISQUE et la population vient du "
               "gameconfig du build courant ; un module neuf ou un changement de build peut donc "
               "changer le verdict sans qu'un chemin nomme ci-dessus soit touche."),
}

BLOOD = int(ActiveAbilityType.BloodChalice)              # 0x497 = 1175
CULT = int(ActiveAbilityType.CultDemagogue)              # 0x49b = 1179
MOMENT = int(ActiveAbilityType.MomentShackle)            # 0x4a0 = 1184
MARTIAL = int(ActiveAbilityType.MartialInspiration)      # 0x4a7 = 1191
TALONS = int(ActiveAbilityType.TalonsOfTheEmperor)       # 0x4c3 = 1195
LASH = int(ActiveAbilityType.LashOfTorment)              # 0x4ac = 1196
SFS = int(ActiveAbilityType.StrikeFromTheShadows)        # 0x4c9 = 1225
LTC = int(ActiveAbilityType.LeadingTheCharge)            # 0x4b4 = 1204
EXCRU = int(ActiveAbilityType.ExcruciatingFrequencies)   # 0x4ad = 1197
MACRO = int(ActiveAbilityType.MacroPlasmaIncinerator)    # 0x48f... = 1159
SQUIG = int(ActiveAbilityType.SquigLaunchas)             # 0x4b8 = 1200
INFERNAL = int(ActiveAbilityType.InfernalCannon)         # 0x4b9 = 1209


def _nom(aid: int) -> str:
    return EM.ACTIVE_ABILITY_TYPE[int(aid)]


# =================================================================================================
#  ETAGE 1 -- la PARTITION : rien ne peut y rester muet
# =================================================================================================

def test_etage1_aucun_conteneur_MUET_ni_FANTOME():
    """LE cliquet. Un conteneur de niveau module du perimetre qui designe des `ActiveAbilityType`
    est INSCRIT (`VOIES`) ou ECARTE AVEC SA RAISON (`ECARTES`) ; sinon il sort MUET.

    C'est le patron de l'etape 7 de `probe_313` : on ne DECOUVRE pas les registres (une table de
    constantes et un registre d'abilities ont la meme forme), on PARTITIONNE un perimetre."""
    p = DFV.partition()
    assert p["inscrits"], "partition vide : le perimetre ne resout plus rien -- mesure cassee"
    assert not p["muets"], (
        "conteneur(s) MUET(s) -- ni inscrit dans `decision_face_voies.VOIES`, ni ecarte avec sa "
        "raison dans `ECARTES` : %s"
        % ", ".join("%s.%s (%d/%d designent une active)" % (m, a, k, n)
                    for m, a, k, n in p["muets"]))
    assert not p["fantomes"], (
        "conteneur(s) inscrit(s) au foyer mais INTROUVABLE(s) dans le perimetre : %s"
        % ", ".join("%s.%s" % c for c in p["fantomes"]))


def test_etage1_contre_epreuve_retirer_une_raison_rend_MUET():
    """La mutation JOUEE : on retire `NATIVE_PRIORITY` de `ECARTES`. Il doit sortir MUET.

    Sans cette contre-epreuve, un `ECARTES` qui aurait avale tout le perimetre (ou une partition
    devenue vide) passerait pour vert."""
    cle = ("engine.playbook.noncomparable._base", "NATIVE_PRIORITY")
    assert cle in DFV.ECARTES, "temoin absent : la contre-epreuve ne mordrait rien"
    sauve = DFV.ECARTES.pop(cle)
    try:
        p = DFV.partition()
        assert cle in [(m, a) for m, a, _k, _n in p["muets"]], \
            "MUTATION NON MORDANTE : un conteneur sans raison doit sortir MUET"
    finally:
        DFV.ECARTES[cle] = sauve
    assert not DFV.partition()["muets"], "etat NON restaure apres la contre-epreuve"


# =================================================================================================
#  ETAGE 2 -- les DEUX consommateurs lisent le MEME foyer
# =================================================================================================

def test_etage2_le_probe_et_l_audit_ne_peuvent_plus_diverger():
    """`probe_909.population()` et `audit_kit_coverage.collect()` repondaient a la MEME question
    par DEUX listes blanches differentes (3 registres contre 4). Ils passent desormais tous deux
    par `decision_face_voies` : ce test le VERIFIE sur la population reelle, au lieu de le croire.

    Comparaison sur l'ETAT BOOLEEN `portee` -- l'audit ne connait pas l'etat ternaire (une
    CONSTANTE y est decomptee par l'attestation, donc `decision = True`), donc on confronte
    `portee OU constante` d'un cote a `decision` de l'autre."""
    import audit_kit_coverage as AK
    import probe_909_decision_actives_kit as P909

    pop, _ecartes = P909.population()
    lignes = {r["id"]: r for r in AK.collect()}
    vu = 0
    for nm, v in pop.items():
        cote_probe = v["etat"] in ("PORTEE", "CONSTANTE")
        for uid in v["porteurs"]:
            for a in (lignes.get(uid) or {}).get("actives", []):
                if a["name"] != nm:
                    continue
                vu += 1
                assert bool(a["decision"]) == cote_probe, (
                    "DIVERGENCE sur %s (%s) chez %s : audit.decision=%s, probe.etat=%s"
                    % (nm, v["id"], uid, a["decision"], v["etat"]))
    assert vu > 100, "confrontation DEGENEREE : seulement %d couples (unite, active) compares" % vu


# =================================================================================================
#  ETAGE 3 -- les deux voies historiquement RATEES sont vues, et leur retrait mord
# =================================================================================================

@pytest.mark.parametrize("aid,voie", [
    (BLOOD, "BESPOKE_SELFCAST"),        # #971 : 3 faux GAP
    (CULT, "BESPOKE_SELFCAST"),         #        `1179` a ete REDISPATCHEE sur cette foi
    (MOMENT, "BESPOKE_SELFCAST"),
    (MARTIAL, "_MAKE_DMG_INPUT_OVERRIDES"),   # #974 : la 5e voie
    (TALONS, "_MAKE_DMG_INPUT_OVERRIDES"),
])
def test_etage3_les_voies_ratees_sont_vues(aid, voie):
    """Ces cinq abilities etaient declarees NON PORTEES par le recenseur alors qu'elles le sont.
    `1175 BloodChalice` figurait meme au lot soumis a #979 comme travail a faire."""
    etat, _detail = DFV.etat(aid, _nom(aid))
    assert etat == "PORTEE", "%s (%s) doit etre PORTEE, etat = %s" % (_nom(aid), aid, etat)
    assert voie in DFV.face_portee(aid, _nom(aid)), \
        "%s doit etre portee par `%s` ; voies vues = %s" % (_nom(aid), voie,
                                                            DFV.face_portee(aid, _nom(aid)))


def test_etage3_contre_epreuve_retirer_une_voie_rend_NON_PORTEE():
    """Mutation JOUEE : on retire `_MAKE_DMG_INPUT_OVERRIDES` de `VOIES`. `1191` et `1195` doivent
    retomber NON PORTEE -- c'est-a-dire reproduire EXACTEMENT le faux verdict d'avant #974."""
    sauve = list(DFV.VOIES)
    try:
        DFV.VOIES[:] = [v for v in sauve if v.attr != "_MAKE_DMG_INPUT_OVERRIDES"]
        for aid in (MARTIAL, TALONS):
            etat, _d = DFV.etat(aid, _nom(aid))
            assert etat == "NON PORTEE", \
                "MUTATION NON MORDANTE : sans la 5e voie, %s doit retomber NON PORTEE" % _nom(aid)
    finally:
        DFV.VOIES[:] = sauve
    assert DFV.etat(MARTIAL, _nom(MARTIAL))[0] == "PORTEE", "etat NON restaure"


# =================================================================================================
#  ETAGE 4 -- l'etat TERNAIRE, et la peremption qui REMET du travail
# =================================================================================================

@pytest.mark.parametrize("aid,verdict", [
    (LTC, "RIEN_A_PORTER"),      # #945 -- deja au ledger avant #979
    (LASH, "RIEN_A_PORTER"),     # #974 -- n'existait que dans un message de commit et un test
    (SFS, "RIEN_A_PORTER"),      # #976 -- idem
])
def test_etage4_les_CONSTANTES_sont_declarees_avec_leur_source(aid, verdict):
    """Une active dont le playbook natif EST le chemin generique n'est ni portee ni a porter. Cet
    etat n'est derivable d'AUCUNE table offline (il s'etablit en lisant le corps natif), donc il
    est DECLARE au ledger `coverage_attestations` avec sa raison, sa source, son build et son
    ancrage. Trois clauses le font PERIMER, et une attestation perimee REMET l'item au compte."""
    etat, detail = DFV.etat(aid, _nom(aid))
    assert etat == "CONSTANTE", "%s (%s) doit etre CONSTANTE, etat = %s" % (_nom(aid), aid, etat)
    e = DFV.attestations()[_nom(aid)]
    assert e["verdict"] == verdict
    assert e["raison"].strip(), "une attestation sans raison est une liste blanche deguisee"
    assert os.path.exists(os.path.join(DFV._REPO, e["source"].split("#")[0])), \
        "source introuvable : %s" % e["source"]


def test_etage4_ExcruciatingFrequences_est_portee_HORS_registre():
    """`1197` est portee depuis #56-t3b par un GENERATEUR bespoke appele EN DUR dans
    `ComparableAbilityGenerator.generate` -- son playbook natif cible une TUILE et ses evals ont
    `rankCount = 0`, donc aucun `plan` ne l'amene. AUCUN conteneur de niveau module ne peut
    l'exprimer : c'est le verdict `PORTE_HORS_REGISTRE`, dont le `porteur` est RESOLVABLE."""
    etat, detail = DFV.etat(EXCRU, _nom(EXCRU))
    assert etat == "PORTEE", "1197 doit etre PORTEE (hors registre), etat = %s" % etat
    assert not DFV.face_portee(EXCRU, _nom(EXCRU)), \
        "1197 n'a AUCUN conteneur qui la porte -- si elle en a un, l'attestation est a retirer"
    e = DFV.attestations()[_nom(EXCRU)]
    assert e["verdict"] == "PORTE_HORS_REGISTRE"
    mod, _, sym = e["porteur"].partition(":")
    import importlib
    assert hasattr(importlib.import_module(mod), sym), \
        "porteur non resolvable : %s -- le port a disparu, l'item redevient du travail" % e["porteur"]


def test_etage4_contre_epreuve_une_attestation_PERIMEE_remet_le_travail():
    """Mutation JOUEE : on perime les trois attestations en leur donnant un build faux. Les trois
    CONSTANTES doivent redevenir NON PORTEE, et `1197` aussi. Le sens de la degradation est
    CHOISI : la peremption ne sait que RAJOUTER du travail."""
    vrai = CA.build_courant
    try:
        CA.build_courant = lambda: "buildquinexistepas"
        att = DFV.attestations()
        assert not att, "MUTATION NON MORDANTE : le build faux doit tout perimer"
        for aid in (LTC, LASH, SFS, EXCRU):
            etat, _d = DFV.etat(aid, _nom(aid), att=att)
            assert etat == "NON PORTEE", \
                "%s doit REDEVENIR du travail quand son attestation perime" % _nom(aid)
    finally:
        CA.build_courant = vrai
    assert DFV.etat(LTC, _nom(LTC))[0] == "CONSTANTE", "etat NON restaure"


# =================================================================================================
#  ETAGE 5 -- un element qui « resout » ne prouve RIEN
# =================================================================================================

def test_etage5_les_registres_TRIGGERED_sont_ecartes_et_leurs_ordinaux_resolvent_quand_meme():
    """Le piege que la partition rend VISIBLE au lieu de le maquiller : `TRIGGERED_ATTACK_PLAYBOOKS`
    est keye par `TriggeredAbilityType`, et 13 de ses 18 cles sont AUSSI des ordinaux valides
    d'`ActiveAbilityType` -- `1204` y nomme `LeadingTheCharge`, `1116` `RadBombardment`. Les
    inscrire comme voie declarerait portees des faces qui ne le sont pas.

    Ce test ASSERTIONNE SON PROPRE NON-VIDE : si l'intersection etait vide, il passerait pour vert
    en ne verifiant rien (le controle de #270-r1-r1-r3, transpose)."""
    import importlib
    ids = set(EM.ACTIVE_ABILITY_TYPE)
    total = 0
    for mod, attr in (("engine.playbook.psyker", "TRIGGERED_ATTACK_PLAYBOOKS"),
                      ("engine.playbook.adjacent_unit_preference", "TRIGGERED_MOVE_PLAYBOOKS"),
                      ("engine.playbook.non_owner", "NON_OWNER_MOVE_PLAYBOOKS")):
        assert (mod, attr) in DFV.ECARTES, "%s.%s doit etre ECARTE avec sa raison" % (mod, attr)
        assert (mod, attr) not in {v.cle for v in DFV.VOIES}, \
            "%s.%s est keye par TriggeredAbilityType : l'inscrire serait un faux PORTEE" % (mod, attr)
        d = getattr(importlib.import_module(mod), attr)
        total += sum(1 for k in d if int(k) in ids)
    assert total > 0, ("controle DEGENERE : aucun ordinal `TriggeredAbilityType` ne resout comme "
                       "`ActiveAbilityType`, donc ce test ne verifie rien")


def test_etage5_le_tier_get_Priority_ne_porte_PAS_la_face():
    """`noncomparable._base.NATIVE_PRIORITY` est keye par de VRAIS `ActiveAbilityType` -- aucun
    partage d'ordinal ici, contrairement aux trois registres ci-dessus. C'est pourtant un AUTRE
    axe : le tier `get_Priority` ORDONNE les generateurs NonComparable, il ne porte aucune utilite.
    L'inscrire comme voie declarerait portees des faces qui ne le sont pas.

    Les temoins sont DERIVES, pas ecrits : la liste ecrite se serait perimee au premier de ces ids
    porte par un autre lot -- et c'est arrive pendant l'ecriture de ce fichier (`1209
    InfernalCannon` est entree a `PLAYBOOKS` avec #978, entre le lancement de #979 et son rebase).
    Le test ASSERTIONNE SON PROPRE NON-VIDE : le jour ou les 22 tiers seront tous portes, il ROUGIT
    au lieu de passer en ne verifiant rien."""
    from engine.playbook.noncomparable._base import NATIVE_PRIORITY
    assert ("engine.playbook.noncomparable._base", "NATIVE_PRIORITY") in DFV.ECARTES, \
        "NATIVE_PRIORITY doit etre ECARTE avec sa raison"
    tables = DFV.voies_par_ability()
    orphelins = sorted(a for a in map(int, NATIVE_PRIORITY)
                       if a in EM.ACTIVE_ABILITY_TYPE and not DFV.face_portee(a, _nom(a), tables))
    assert orphelins, ("controle DEGENERE : les 22 tiers sont tous portes par une voie, donc "
                       "inscrire NATIVE_PRIORITY serait devenu sans effet -- relire cet ecart")
    for aid in orphelins:
        etat, _d = DFV.etat(aid, _nom(aid))
        assert etat in ("NON PORTEE", "CONSTANTE"), \
            "%s n'a que son TIER -- son `EvaluateNonComparable` n'est pas porte (etat %s)" \
            % (_nom(aid), etat)
