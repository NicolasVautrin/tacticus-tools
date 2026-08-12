"""#979 -- le FOYER UNIQUE des VOIES d'inscription d'une face DECISION d'active, et leur PARTITION.

## Ce qu'il ferme

`probe_909_decision_actives_kit.py` et `audit_kit_coverage.py` etablissaient tous deux « la face
DECISION de cette active est portee » en testant une LISTE BLANCHE de registres, ecrite a la main
et DIFFERENTE dans les deux outils (3 registres chez l'un, 4 chez l'autre au 2026-08-12). Une liste
blanche ne peut pas montrer la voie qu'elle a oubliee : elle en avait deja rate deux, MESUREES --
`BESPOKE_SELFCAST` (#971, 3 faux GAP) puis `_MAKE_DMG_INPUT_OVERRIDES` (#974, la 5e voie, ou vivait
deja `1191 MartialInspiration`). Le compte annonce (32 non portees) sur-comptait donc de **22 %**.

La reponse n'est PAS d'allonger la liste. C'est le vice que le CLAUDE.md nomme deux fois (le
recenseur de roles de #270-r1, l'etape 7 de `probe_313`) et la parade y est la meme : **PARTITIONNER
un perimetre**, de sorte que tout conteneur y soit INSCRIT ou ECARTE AVEC SA RAISON, et que rien ne
puisse y rester muet.

## Le perimetre, et ce qu'il filtre

`PERIMETRE` = les arbres de source que la chaine de decision par-ability habite --
`engine/playbook/**` (les deux routes, les generateurs bespoke, la prediction) et
`engine/entities/abilities/active_ability.py` (le dispatch de sous-classe d'ability et les registres
de forme de prediction). Dans ces arbres, TOUT conteneur de niveau module a nom majuscule est
visite ; il entre dans la partition des qu'AU MOINS UN de ses elements (cle d'un dict, membre d'un
set/tuple/list) resout comme un `ActiveAbilityType` -- par ORDINAL ou par NOM.

Les conteneurs dont AUCUN element ne resout sont ECARTES par ce filtre, et le filtre DIT ce qu'il
ecarte (compte imprime + `--tout`). C'est le seul endroit ou un conteneur peut disparaitre sans
raison ecrite ; le seuil est `>= 1 element`, donc le plus bas possible.

⚠ Un element qui RESOUT ne prouve rien a lui seul, et le perimetre le rend visible plutot que de
le maquiller : `psyker.TRIGGERED_ATTACK_PLAYBOOKS` a **13 cles sur 18** qui sont des ordinaux
valides d'`ActiveAbilityType` (`1204` -> `LeadingTheCharge`, `1116` -> `RadBombardment`, ...) alors
que ses cles sont des `TriggeredAbilityType`. C'est exactement le partage d'ordinaux que le
CLAUDE.md chiffre (233 entre les deux enums, 231 nomment autre chose). Ces trois registres-la sont
donc ECARTES, avec cette raison -- pas absents.

## Le critere d'inscription, ecrit une fois

Un conteneur est une **VOIE** si son APPARTENANCE signifie « le port porte, pour cette ability,
quelque chose de PROPRE sur la face DECISION ».

Il est **ECARTE** s'il enonce autre chose :
  * un FAIT NATIF recense (les N classes qui partagent un corps, le tier `get_Priority`, la forme
    d'arrondi de la base de degat) -- y figurer ne porte rien ;
  * une donnee d'un AUTRE axe (cles `TriggeredAbilityType`, `UnitTrait`, `DamageProfileType`) ;
  * une NEGATION d'inscription (`NOT_REGISTERED`, `REGISTERED_ELSEWHERE`).

## Le TROISIEME etat : CONSTANTE

« Portee / non portee » est un axe FAUX pour une active dont le playbook natif EST le chemin
generique : il n'y a rien a porter, et la compter comme du travail est aussi faux que de rater un
port. Cet etat ne se derive d'aucune table offline -- il s'etablit en LISANT le corps natif --, donc
il est DECLARE, avec sa source, dans le ledger qui existe deja pour ca :
`coverage_attestations.py` (categorie `active-decision`, verdicts `RIEN_A_PORTER` et
`PORTE_HORS_REGISTRE`). Une attestation PERIMEE remet l'item au compte des manquants ; aucun chemin
ne peut faire disparaitre du travail.

Sortie ASCII. Usage : depuis `scripts/python/`  ->  python decision_face_voies.py [--tout]
"""
from __future__ import annotations

import ast
import importlib
import os
import sys

_PYROOT = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(_PYROOT))
if _PYROOT not in sys.path:
    sys.path.insert(0, _PYROOT)

#: Les arbres de source visites. Un REPERTOIRE, jamais une liste de modules : une liste de modules
#: ne verrait pas le module NEUF, qui est precisement le mode de defaillance qu'on ferme.
PERIMETRE: tuple[str, ...] = (
    "engine/playbook",
    "engine/entities/abilities/active_ability.py",
)


class Voie:
    """Un conteneur de niveau module dont l'APPARTENANCE porte la face DECISION d'une active.

    `par` -- "valeur" : l'element est l'ordinal `ActiveAbilityType` ; "nom" : le nom du membre.
    L'appariement est LU au site (en-tete du registre + point de consommation), jamais deduit du
    fait qu'une cle « resout » : 233 ordinaux sont partages avec `TriggeredAbilityType`.
    """

    __slots__ = ("mod", "attr", "par", "raison", "consommateur")

    def __init__(self, mod: str, attr: str, par: str, raison: str, consommateur: str):
        self.mod, self.attr, self.par = mod, attr, par
        self.raison, self.consommateur = raison, consommateur

    @property
    def cle(self) -> tuple[str, str]:
        return (self.mod, self.attr)

    def __repr__(self) -> str:                      # ASCII, lisible en trace
        return "%s.%s" % (self.mod, self.attr)


#: Les VOIES, avec leur POINT DE CONSOMMATION -- c'est lui qui etablit qu'elles portent la face,
#: pas leur nom. Ordre de decouverte, ajouts EN FIN DE BLOC (registre partage).
VOIES: list[Voie] = [
    Voie("engine.playbook.noncomparable", "PLAYBOOKS", "valeur",
         "la route NonComparable : `EvaluateNonComparable` porte TOUTE l'utilite de l'ability",
         "playbook.noncomparable.choose_action -> ai.action_generators (generateur par tier)"),
    Voie("engine.playbook.base", "REGISTRY", "valeur",
         "la route Comparable : override de `CalculateCustomUtility` / `ShouldExecute` / "
         "`MakeDamagePredictions` par sous-classe de `ComparablePlaybook`",
         "playbook.get_playbook_or_default -> ComparableAbilityGenerator._best_attack"),
    Voie("engine.entities.abilities.active_ability", "_SPECIAL_ABILITY_CLASSES", "nom",
         "sous-classe d'`AActiveAbility` mirroree PAR ability (formule de coups, AoE, degat "
         "conditionnel) -- consommee UNIQUEMENT sous `engine/playbook/prediction/`",
         "active_ability.active_ability_for -> playbook.prediction.make_damage_predictions"),
    Voie("engine.playbook.bespoke", "BESPOKE_SELFCAST", "valeur",
         "les Comparable qui overrident `EvaluateInternal` EN ENTIER (hors du plan `evals`, donc "
         "hors de `REGISTRY`). 4e voie, trouvee par #971 apres 3 faux GAP",
         "ai.action_generators.ComparableAbilityGenerator._bespoke_candidates"),
    Voie("engine.playbook.prediction.abilities", "_MAKE_DMG_INPUT_OVERRIDES", "valeur",
         "surcharge des ENTREES de `GenerateMultiHitAttackPredictions` (base / hits / profil) par "
         "le `<X>Playbook` natif. 5e voie, trouvee par #974 -- `1191` y vivait deja",
         "playbook.prediction.abilities.make_damage_predictions"),
    Voie("engine.playbook.prediction.abilities", "_MAKE_DMG_SELECTOR_ONLY", "valeur",
         "les playbooks qui n'emettent AUCUN batch `<Target>` separement : la cible n'a d'event "
         "que si le SELECTEUR la contient, et alors A SA PLACE (#359-r5)",
         "playbook.prediction.abilities.make_damage_predictions"),
    Voie("engine.playbook.prediction.abilities", "_MAKE_DMG_TARGET_GATE", "valeur",
         "gate de cible : une cible que le selecteur du playbook ne retient pas n'a AUCUN event",
         "playbook.prediction.abilities.make_damage_predictions"),
    Voie("engine.playbook.prediction.abilities", "_MAKE_DMG_EXTRA_EVENTS", "valeur",
         "batchs SUPPLEMENTAIRES per-ability (selecteur AUTRE que la cible et son AoE)",
         "playbook.prediction.abilities.make_damage_predictions"),
    Voie("engine.playbook.prediction.abilities", "_PLAYBOOK_PROFILE_OVERRIDE", "valeur",
         "le `Nullable<DamageProfile>` que le `<X>Playbook` natif passe EXPLICITEMENT a "
         "`GenerateMultiHitAttackPredictions` (audit #165)",
         "playbook.prediction.abilities / playbook.daemonic_ordnance"),
    Voie("engine.playbook.prediction.abilities", "_PREPEND_NORMAL_ATTACK_EVENT", "nom",
         "le playbook AJOUTE le batch de l'attaque normale devant le sien (`AddRange`, #351)",
         "playbook.prediction.abilities.make_damage_predictions"),
    Voie("engine.playbook.common", "HEAL_PLAYBOOKS", "valeur",
         "les playbooks de SOIN bespoke : un id absent retombe sur le generique `18`, donc "
         "l'appartenance dit bien qu'un corps PROPRE est porte",
         "ai.action_generators.ComparableAbilityGenerator._heal_candidates"),
    Voie("engine.playbook.nonattack", "NONATTACK_PLAYBOOKS", "valeur",
         "2e route Comparable : ability SANS prediction (pas de `damageProfile`), donc jamais "
         "dans `plans` -- registre EXPLICITE, aucune ability n'y arrive par defaut",
         "playbook.nonattack.nonattack_candidates"),
    Voie("engine.playbook.should_execute_gates", "LITERAL_ZERO_THRESHOLD_IDS", "valeur",
         "les ids dont `ShouldExecute` = `utility > Fix64(0)` LITTERAL et dont la route EST le "
         "generateur d'attaque Comparable",
         "playbook.should_execute_gates._register_all -> base.REGISTRY"),
    Voie("engine.playbook.should_execute_gates", "LITERAL_ZERO_ELSEWHERE", "valeur",
         "meme corps natif, mais gate porte sur une AUTRE route -- et la VALEUR NOMME le porteur "
         "(`module.symbole`), ce qui en fait une attestation verifiable, pas une liste blanche",
         "attestation lue par le probe ; porteurs = _heal_candidates / _repair_candidates"),
]


#: Les conteneurs du PERIMETRE qui designent des actives sans porter leur face. Chacun sa RAISON --
#: c'est ce qui distingue un ecart raisonne d'un oubli, et c'est ce que la partition exige.
ECARTES: dict[tuple[str, str], str] = {
    # --- FAITS NATIFS recenses : y figurer n'implique AUCUN port ---------------------------------
    ("engine.playbook.normal_attack_kill_gate", "SPIRIT_LEECH_BODY_IDS"):
        "FAIT NATIF : les 14 classes qui partagent le corps `SpiritLeechPlaybook$$ShouldExecute`. "
        "Le module le dit lui-meme (<< cette liste enonce un FAIT NATIF, pas la ventilation du "
        "port >>) ; la couverture, elle, vient de `base.REGISTRY` ou `_register_all` les inscrit.",
    ("engine.playbook.normal_attack_kill_gate", "REGISTERED_ELSEWHERE"):
        "NEGATION d'inscription : les identites du corps que CE module n'enregistre PAS (un autre "
        "module pose une classe plus specialisee). La couverture vient de ce module-la.",
    ("engine.playbook.static_threshold_gate", "THRESHOLD_BY_ID"):
        "FAIT NATIF : les 12 classes de la famille << seuil statique >> et leur seuil mesure. Dix "
        "sont inscrites a `base.REGISTRY` par `_register_all`, deux en sont explicitement exclues.",
    ("engine.playbook.static_threshold_gate", "DERIVED_CCTOR_IDS"):
        "FAIT NATIF : les 4 classes qui declarent leur propre `.cctor` (`Fix64(1)`, ECRASE). "
        "Conserve pour expliquer une lecture passee, sans aucun effet sur le port.",
    ("engine.playbook.static_threshold_gate", "NO_DERIVED_CCTOR_IDS"):
        "FAIT NATIF : les 8 classes sans `.cctor` propre. Meme statut que son voisin.",
    ("engine.playbook.static_threshold_gate", "NOT_REGISTERED"):
        "NEGATION d'inscription : les 2 ids que ce module n'enregistre PAS parce que leur gate vit "
        "dans un generateur bespoke. `1184` est couverte par `bespoke.BESPOKE_SELFCAST` ; `1197` "
        "par le generateur `excruciating_frequencies_candidates`, atteste au ledger #951-r2.",
    ("engine.playbook.noncomparable._base", "NATIVE_PRIORITY"):
        "FAIT NATIF d'un AUTRE axe : le tier `get_Priority` (slot 0 d'`IPlaybook`), qui ORDONNE les "
        "generateurs NonComparable. Il ne porte PAS l'utilite -- `1159`, `1200` et `1209` y "
        "figurent alors que leur `EvaluateNonComparable` n'est pas porte.",
    # --- FORME de la base de prediction : lue et CONFIRMEE generique, donc rien de propre --------
    ("engine.entities.abilities.active_ability", "_PREDICTION_MINMAX_AVERAGE"):
        "FORME d'arrondi LUE (#344/#350) : la base EST la moyenne min/max, c.-a-d. le chemin "
        "GENERIQUE du port. Y figurer dit << lu et conforme >>, pas << porte >>.",
    ("engine.entities.abilities.active_ability", "_PREDICTION_MINMAX_RANDOM_READ"):
        "Idem, famille (b) : lecture RANDOM, qui coincide avec le defaut. Aucun branchement.",
    ("engine.entities.abilities.active_ability", "_A_VIA_GET_DAMAGE_AMOUNT_MAIN"):
        "Sous-famille de `_PREDICTION_MINMAX_AVERAGE` -- meme statut.",
    ("engine.entities.abilities.active_ability", "_A_VIA_STAFF_OF_STARS_GET_DAMAGE"):
        "Sous-famille de `_PREDICTION_MINMAX_AVERAGE` (forme a2) -- meme statut.",
    ("engine.entities.abilities.active_ability", "_A_VIA_OWN_ABILITY_BODY"):
        "Sous-famille de `_PREDICTION_MINMAX_AVERAGE` -- meme statut.",
    ("engine.entities.abilities.active_ability", "_A_INLINE_IN_PLAYBOOK"):
        "Sous-famille de `_PREDICTION_MINMAX_AVERAGE` -- meme statut.",
    ("engine.entities.abilities.active_ability", "_PREDICTION_DAMAGE_NOT_MINMAX_AVERAGE"):
        "Registre de LECTURE, purement documentaire : le module le dit (<< aucun code ne branche "
        "sur cette table >>). Quand l'ecart EST corrige, le correctif vit dans "
        "`_MAKE_DMG_INPUT_OVERRIDES`, qui est la voie -- inscrire celui-ci compterait porte ce "
        "qui n'est que LU.",
    ("engine.entities.abilities.active_ability", "_PREDICTION_FORMULA_ON_TRIGGERED_ABILITY"):
        "Table documentaire (#350-r3) ; sa VALEUR est un `TriggeredAbilityType`, sa cle ne sert "
        "qu'a dire que la formule ne porte PAS sur l'active homonyme.",
    ("engine.entities.abilities.active_ability", "_NONCOMPARABLE_ABILITIES"):
        "CLASSEMENT de route, et le foyer le dit explicitement : y figurer dit que le port CLASSE "
        "l'ability NonComparable (donc s'interdit de fabriquer un degat), PAS que son utilite est "
        "portee -- celle-ci vit dans `noncomparable.PLAYBOOKS`.",
    # --- cles d'un AUTRE enum : l'ordinal qui << resout >> est un partage, pas une identite ------
    ("engine.playbook.psyker", "TRIGGERED_ATTACK_PLAYBOOKS"):
        "Cles = `TriggeredAbilityType` (face ATTACK). 13 des 18 sont AUSSI des ordinaux valides "
        "d'`ActiveAbilityType` et nomment autre chose : c'est le partage d'ordinaux du CLAUDE.md, "
        "pas une couverture d'active.",
    ("engine.playbook.adjacent_unit_preference", "TRIGGERED_MOVE_PLAYBOOKS"):
        "Cles = `TriggeredAbilityType` (face MOVE). Meme partage d'ordinaux (13 sur 27).",
    ("engine.playbook.non_owner", "NON_OWNER_MOVE_PLAYBOOKS"):
        "Cles = `TriggeredAbilityType` NON-OWNER. Meme partage d'ordinaux (2 sur 19).",
    ("engine.playbook.non_owner", "_MECHANICAL_TRAITS"):
        "Elements = `UnitTrait` (5 Mechanical, 1000 LivingMetal, 1029 Vehicle), qualifies au site.",
    ("engine.playbook.sanguinary_priest", "TRAITS_MECHANICAL"):
        "Elements = `UnitTrait`, les trois d'`UnitExtensions$$IsMechanical` -- MEME fait natif que "
        "`non_owner._MECHANICAL_TRAITS` ci-dessus, mirore une SECONDE fois. 2 des 3 ordinaux sont "
        "aussi des `ActiveAbilityType` valides et nomment autre chose. Le doublon est signale, pas "
        "resolu ici : deux copies d'un meme fait natif peuvent diverger en silence.",
    ("engine.playbook.noncomparable.exemplar_of_hate", "_GRAND_ALLIANCE_TRAITS"):
        "Elements = traits de grande alliance, pas des abilities.",
    ("engine.playbook.noncomparable.it_itches", "_NOT_DISPLACEABLE"):
        "Elements = `UnitTrait` bloquants d'`IsDisplaceable` (Immovable / Hulking / BigTarget).",
    ("engine.playbook.prediction._shared", "_PROFILE_INDEX"):
        "Cles = noms de `DamageProfileType`, pas d'abilities.",
}


# ============================================================================================
#  Le perimetre, visite
# ============================================================================================

def _fichiers_du_perimetre() -> list[str]:
    out = []
    for rel in PERIMETRE:
        p = os.path.join(_PYROOT, rel.replace("/", os.sep))
        if os.path.isdir(p):
            for racine, _dirs, fics in os.walk(p):
                out += [os.path.join(racine, f) for f in fics if f.endswith(".py")]
        elif os.path.exists(p):
            out.append(p)
    return sorted(out)


def _nom_de_module(path: str) -> str:
    rel = os.path.relpath(path, _PYROOT).replace(os.sep, "/")[:-3]
    if rel.endswith("/__init__"):
        rel = rel[: -len("/__init__")]
    return rel.replace("/", ".")


def conteneurs_du_perimetre() -> list[tuple[str, str]]:
    """`(module, NOM)` de tout conteneur de niveau module a nom MAJUSCULE du perimetre.

    Par AST : le nom se lit sans importer, donc l'inventaire reste lisible meme si un module casse.
    La VALEUR, elle, exige l'import (cf. `elements`)."""
    out = []
    for path in _fichiers_du_perimetre():
        mod = _nom_de_module(path)
        with open(path, encoding="utf-8") as f:
            arbre = ast.parse(f.read())
        for n in arbre.body:
            if not isinstance(n, (ast.Assign, ast.AnnAssign)):
                continue
            cibles = n.targets if isinstance(n, ast.Assign) else [n.target]
            for t in cibles:
                if isinstance(t, ast.Name) and t.id.isupper():
                    out.append((mod, t.id))
    return out


def elements(mod: str, attr: str):
    """Les elements a confronter : les CLES d'un dict, les membres d'un set/tuple/list. `None` si
    l'attribut n'est pas un conteneur (ou n'existe plus)."""
    v = getattr(importlib.import_module(mod), attr, None)
    if isinstance(v, dict):
        return list(v.keys())
    if isinstance(v, (set, frozenset, tuple, list)):
        return list(v)
    return None


def _tables():
    import enum_maps as EM
    return set(EM.ACTIVE_ABILITY_TYPE), set(EM.ACTIVE_ABILITY_TYPE.values())


def resout(x, ids: set, noms: set) -> bool:
    """L'element designe-t-il un `ActiveAbilityType` ? Par ORDINAL ou par NOM. `bool` exclu : c'est
    un `int` en Python, et `True` vaudrait l'ability 1."""
    if isinstance(x, bool):
        return False
    if isinstance(x, int):
        return int(x) in ids
    if isinstance(x, str):
        return x in noms
    return False


def partition() -> dict:
    """La PARTITION du perimetre. Rien n'en sort sans etiquette :

      inscrits   -- (mod, attr) present dans `VOIES`
      ecartes    -- present dans `ECARTES`, donc avec sa raison ecrite
      muets      -- designe des actives, et NI l'un NI l'autre  ==> le cliquet rougit
      hors_sujet -- aucun element ne resout comme `ActiveAbilityType` (compte, et liste sur `--tout`)
      inertes    -- l'attribut n'est pas un conteneur, ou il est VIDE
      fantomes   -- inscrit dans `VOIES`/`ECARTES` mais introuvable dans le perimetre
    """
    ids, noms = _tables()
    v_cles = {v.cle for v in VOIES}
    vus = set()
    out = {"inscrits": [], "ecartes": [], "muets": [], "hors_sujet": [], "inertes": [],
           "fantomes": []}
    for mod, attr in conteneurs_du_perimetre():
        vus.add((mod, attr))
        els = elements(mod, attr)
        if not els:
            out["inertes"].append((mod, attr))
            continue
        n_ok = sum(1 for e in els if resout(e, ids, noms))
        if (mod, attr) in v_cles:
            out["inscrits"].append((mod, attr, n_ok, len(els)))
        elif (mod, attr) in ECARTES:
            out["ecartes"].append((mod, attr, n_ok, len(els)))
        elif n_ok == 0:
            out["hors_sujet"].append((mod, attr, len(els)))
        else:
            out["muets"].append((mod, attr, n_ok, len(els)))
    for cle in sorted(v_cles | set(ECARTES)):
        if cle not in vus:
            out["fantomes"].append(cle)
    return out


# ============================================================================================
#  Ce que les consommateurs (probe_909, audit_kit_coverage) appellent
# ============================================================================================

def voies_par_ability() -> dict:
    """`(aid, nom) -> [noms de voies]`. Une ability y figure des qu'UNE voie la porte.

    Les deux cles sont acceptees parce que les voies elles-memes sont indexees des deux facons
    (`_SPECIAL_ABILITY_CLASSES` par NOM, les autres par ORDINAL) -- forcer une seule indexation
    obligerait chaque appelant a re-deriver la table de noms, donc a diverger."""
    par_id: dict[int, list] = {}
    par_nom: dict[str, list] = {}
    for v in VOIES:
        els = elements(v.mod, v.attr) or []
        for e in els:
            if v.par == "valeur" and isinstance(e, int) and not isinstance(e, bool):
                par_id.setdefault(int(e), []).append(v.attr)
            elif v.par == "nom" and isinstance(e, str):
                par_nom.setdefault(e, []).append(v.attr)
    return {"par_id": par_id, "par_nom": par_nom}


def face_portee(aid, nom, tables=None) -> list[str]:
    """Les VOIES qui portent la face DECISION de cette active. Liste VIDE = non portee par un
    registre (elle peut encore etre CONSTANTE ou portee hors registre : cf. `attestation`)."""
    t = tables or voies_par_ability()
    out = list(t["par_id"].get(int(aid), [])) if aid is not None else []
    out += t["par_nom"].get(nom, [])
    return sorted(set(out))


#: La categorie du ledger `coverage_attestations` qui porte les verdicts de face DECISION.
CATEGORIE_LEDGER = "active-decision"


def attestations() -> dict:
    """`nom d'ability -> entree du ledger`, pour les seules attestations VALIDES de la categorie
    `active-decision`. Une attestation PERIMEE n'arrive jamais ici : l'item redevient du travail."""
    import coverage_attestations as CA
    return {nom: e for (cat, nom), e in CA.attestations_valides().items()
            if cat == CATEGORIE_LEDGER}


def etat(aid, nom, tables=None, att=None) -> tuple[str, str]:
    """L'etat TERNAIRE d'une face DECISION : `("PORTEE"|"CONSTANTE"|"NON PORTEE", detail)`.

    L'ordre des tests n'est pas indifferent. Une voie de registre PRIME sur une attestation : si le
    port a fini par ecrire quelque chose de propre, c'est ce qu'il faut lire, et l'attestation
    devenue fausse doit se voir (elle sortira comme `PORTEE` + attestation, cf. `--tout`).
    """
    voies = face_portee(aid, nom, tables)
    if voies:
        return "PORTEE", ",".join(voies)
    e = (att if att is not None else attestations()).get(nom)
    if e is None:
        return "NON PORTEE", ""
    if e.get("verdict") == "PORTE_HORS_REGISTRE":
        return "PORTEE", "ledger:%s" % e.get("porteur", "?")
    return "CONSTANTE", "ledger:%s" % e.get("source", "?")


# ============================================================================================
#  CLI / cliquet
# ============================================================================================

def main() -> int:
    tout = "--tout" in sys.argv
    p = partition()
    print("[979] PARTITION du perimetre des faces DECISION")
    print("   perimetre : %s" % ", ".join(PERIMETRE))
    print("   fichiers visites          : %d" % len(_fichiers_du_perimetre()))
    print("   conteneurs de niveau module : %d" % len(conteneurs_du_perimetre()))
    print("   INSCRITS (VOIES)          : %d" % len(p["inscrits"]))
    print("   ECARTES AVEC RAISON       : %d" % len(p["ecartes"]))
    print("   MUETS                     : %d" % len(p["muets"]))
    print("   ECARTES PAR CE FILTRE (aucun element ne resout comme ActiveAbilityType) : %d"
          % len(p["hors_sujet"]))
    print("   inertes (non-conteneur ou vide) : %d" % len(p["inertes"]))
    if p["fantomes"]:
        print("   FANTOMES (inscrits mais introuvables) : %d" % len(p["fantomes"]))
        for mod, attr in p["fantomes"]:
            print("      %s.%s" % (mod, attr))
    for mod, attr, n_ok, n in p["muets"]:
        print("   MUET   %s.%s -- %d/%d elements designent une active, et il n'est NI inscrit "
              "dans VOIES NI ecarte avec sa raison" % (mod, attr, n_ok, n))
    if tout:
        print("\n   -- INSCRITS")
        for mod, attr, n_ok, n in sorted(p["inscrits"]):
            print("      %-46s %-34s %3d/%3d" % (mod, attr, n_ok, n))
        print("   -- ECARTES")
        for mod, attr, n_ok, n in sorted(p["ecartes"]):
            print("      %-46s %-34s %3d/%3d" % (mod, attr, n_ok, n))
        print("   -- ECARTES PAR LE FILTRE")
        for mod, attr, n in sorted(p["hors_sujet"]):
            print("      %-46s %-34s   0/%3d" % (mod, attr, n))

    att = attestations()
    print("\n[979] LEDGER -- attestations VALIDES de categorie `%s` : %d"
          % (CATEGORIE_LEDGER, len(att)))
    for nom, e in sorted(att.items()):
        print("   %-28s %-20s %s" % (nom, e.get("verdict"), e.get("source")))
    return 1 if (p["muets"] or p["fantomes"]) else 0


if __name__ == "__main__":
    sys.exit(main())
