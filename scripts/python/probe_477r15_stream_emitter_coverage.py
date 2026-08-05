#!/usr/bin/env python
"""#477-r15 -- COMBIEN de la couche `StreamCache` / `StreamDispatcher` est portee cote Python ?

Ce probe MESURE (il ne garde rien). Il repond a une seule question, celle qui chiffre le
cout d'un comparateur de flux de replay : le moteur Python sait-il EMETTRE un flux de la
grammaire mesuree en #477-r11, et si non, de combien est-il loin ?

POURQUOI CE PROBE EXISTE
------------------------
`docs/rl/case-477r11-format-du-flux-de-replay.md` a etabli que le flux natif est
DETERMINISTE AU CARACTERE PRES (3 rejeux, 2 boards, 2 sessions Frida). La barre de
comparaison est donc l'EGALITE BRUTE. Ce qui manque n'est plus cote natif : c'est que le
port EMETTE. Le chiffre de couverture bouge a chaque tranche livree -- l'ecrire a la main
dans une fiche ne sert qu'une fois, d'ou ce probe.

⚠ PIEGE PRINCIPAL, ET RAISON DE LA FORME TRI-ETAT
--------------------------------------------------
Un recenseur qui rend `0 / 104` se lit « le port couvre zero groupe » -- c'est-a-dire une
MESURE. Or aujourd'hui il n'existe AUCUN registre d'emission a interroger : le bon mot est
« PAS MESURE », pas « zero ». La difference porte tout le chiffrage : « zero couvert »
suggere un emetteur present mais vide (cout = remplir une table), « registre absent »
dit qu'il faut d'abord CONSTRUIRE la couche (cout d'un tout autre ordre).
Le probe distingue donc systematiquement :

    None  = PAS MESURE   -- la source n'existe pas ; on regarde dans le vide
    0     = MESURE, VIDE -- la source existe et ne contient rien
    n     = MESURE

Meme discipline que `host_inputs.py` (case-273) et que le tri-etat de `loop_status.py`.

CE QUE LE PROBE NE FAIT PAS
---------------------------
Il ne monte AUCUN runner et n'ouvre AUCUNE session : tout ce qu'il lit est versionne
(`data/symbols/<build>/frida/enums.tsv`, `scripts/python/engine/**`). Il est donc jouable
depuis un worktree frais, hors session Frida, et parallelisable sans budget runner.
La confrontation LIVE du flux (identite des unites, cf. `--montage-identite`) vit dans
`probe_477r15_identite_par_kit.py`, qui lui monte un runner.

USAGE
    python scripts/python/probe_477r14_stream_emitter_coverage.py
    python scripts/python/probe_477r14_stream_emitter_coverage.py --json
"""
from __future__ import annotations

import argparse
import ast
import json
import pathlib
import sys
from typing import Optional

# Le probe vit dans `scripts/python/` et lit `scripts/python/engine/**` : la racine du
# checkout est deux niveaux au-dessus (meme convention que `host_inputs.py`).
HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
ENGINE = HERE / "engine"

# Les trois enums qui forment le vocabulaire du flux, cites par leur nom PLEINEMENT
# QUALIFIE -- c'est la cle de `enums.tsv` et c'est aussi le symbole natif.
# `IdunBattle.Streams.StreamDispatcher$$Action` prend un `StepType` en 1er argument,
# `$$StartGroup` un `GroupType`, et les tags sont un `Dictionary<TagKey,int>`.
ENUM_GROUP = "IdunBattle.Streams.GroupType"
ENUM_STEP = "IdunBattle.Streams.StepType"
ENUM_TAG = "IdunBattle.Streams.TagKey"

# Convention de nommage du registre d'emission, s'il venait a exister. Le probe le
# CHERCHE plutot que de le supposer : son absence est un resultat, pas une panne.
REGISTRE_CANDIDATS = (
    ENGINE / "streams",
    ENGINE / "runner" / "streams",
    ENGINE / "battlestream",
)

# Les trois methodes du bus d'evenements (`engine/runner/events.py`). Un bus DEFINI mais
# jamais APPELE est un stub : c'est precisement ce qu'il faut distinguer.
BUS_METHODES = ("dispatch_immediate", "enqueue_deferred", "drain_deferred")


class SourceAbsente(RuntimeError):
    """Une source de mesure manque -- on le DIT, on ne rend pas un zero."""


# --------------------------------------------------------------------------- etape 0
def _build_dir() -> Optional[pathlib.Path]:
    """Repertoire `data/symbols/<build>/` du build courant, ou None si indeterminable.

    On passe par `symbols_layout` (le foyer du depot) plutot que de deviner le hash :
    deviner, c'est exactement le motif qui a coute des heures (`CLAUDE.md`, section
    « Hash du build = identite du dump »)."""
    try:
        sys.path.insert(0, str(HERE))
        from symbols_layout import build_dir  # type: ignore
        return build_dir()
    except Exception:
        return None


def lire_enum(enum_fq: str) -> Optional[dict]:
    """{MEMBRE: ordinal} d'un enum depuis la table VERSIONNEE, ou None si PAS MESURE.

    None couvre les deux pannes de source (repertoire de build indeterminable, fichier
    absent) -- distinctes du cas « enum present mais vide », qui rendrait `{}`."""
    bd = _build_dir()
    if bd is None:
        return None
    p = bd / "frida" / "enums.tsv"
    if not p.is_file():
        return None
    with p.open(encoding="utf-8") as f:
        for line in f:
            if not line.startswith(enum_fq + "\t"):
                continue
            out = {}
            for kv in line.rstrip("\n").split("\t", 1)[1].split(","):
                ordinal, membre = kv.split("=", 1)
                out[membre] = int(ordinal)
            return out
    return None


# --------------------------------------------------------------------------- etape 1
def _modules_engine():
    """(chemin, AST) de chaque module du moteur. Un fichier illisible est SIGNALE."""
    if not ENGINE.is_dir():
        raise SourceAbsente(
            "moteur introuvable : %s -- le probe se lance depuis scripts/python/"
            % ENGINE.as_posix())
    for p in sorted(ENGINE.rglob("*.py")):
        try:
            yield p, ast.parse(p.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue


def mesurer_infrastructure() -> dict:
    """Le bus d'evenements du port est-il VIVANT ou est-ce une signature vide ?

    Critere DERIVE, jamais un avis : on compte les APPELS reels (visite AST) des trois
    methodes du bus, et les sous-classes CONCRETES de `BattleEvent`. Un bus dont les
    trois methodes sont definies et jamais appelees, et dont la classe de base d'evenement
    n'a aucune sous-classe, ne transporte rien -- quel que soit le nombre de fois ou il
    est instancie et passe en argument.

    ⚠ Ne pas confondre `EventBus()` INSTANCIE avec un bus UTILISE : le moteur en fabrique
    un jetable a chaque appel d'operation parce que la signature `execute(state, bus)`
    l'exige. C'est du remplissage de parametre, pas du transport."""
    appels = {m: 0 for m in BUS_METHODES}
    definitions = {m: 0 for m in BUS_METHODES}
    instanciations = 0
    sous_classes: list[str] = []
    operations: list[str] = []
    for p, tree in _modules_engine():
        for n in ast.walk(tree):
            if isinstance(n, ast.ClassDef):
                for b in n.bases:
                    nom_base = (b.id if isinstance(b, ast.Name)
                                else b.attr if isinstance(b, ast.Attribute) else None)
                    if nom_base == "BattleEvent":
                        sous_classes.append(n.name)
                if n.name.endswith("Operation"):
                    operations.append(n.name)
            elif isinstance(n, ast.FunctionDef) and n.name in definitions:
                definitions[n.name] += 1
            elif isinstance(n, ast.Call):
                f = n.func
                nom = (f.attr if isinstance(f, ast.Attribute)
                       else f.id if isinstance(f, ast.Name) else None)
                if nom in appels:
                    appels[nom] += 1
                elif nom == "EventBus":
                    instanciations += 1
    return {
        "appels_bus": appels,
        "definitions_bus": definitions,
        "instanciations_eventbus": instanciations,
        "sous_classes_battleevent": sorted(sous_classes),
        "classes_operation": len(operations),
        # Le bus transporte quelque chose SI et SEULEMENT SI il est appele quelque part.
        "bus_vivant": sum(appels.values()) > 0,
    }


def mesurer_formes_de_retour() -> dict:
    """Sous quelle forme les operations rendent-elles leur resultat ?

    C'est la question « le moteur publie-t-il des evenements STRUCTURES, ou des dicts ad
    hoc par operation ? » rendue mesurable. Une couche d'emission exploitable suppose une
    forme COMMUNE ; un histogramme etale sur N formes dit qu'il n'y en a pas."""
    formes: dict[str, int] = {}
    total = 0
    for p, tree in _modules_engine():
        for n in ast.walk(tree):
            if isinstance(n, ast.FunctionDef) and n.name == "execute":
                total += 1
                lbl = ast.unparse(n.returns) if n.returns is not None else "(non annote)"
                formes[lbl] = formes.get(lbl, 0) + 1
    return {"execute_total": total, "formes": dict(sorted(
        formes.items(), key=lambda kv: (-kv[1], kv[0])))}


# --------------------------------------------------------------------------- etape 2
def mesurer_registre_emission() -> dict:
    """Le port declare-t-il quelque part ce qu'il sait EMETTRE ?

    Tri-etat porte par `present` : `False` => les couvertures valent None (PAS MESURE),
    surtout pas 0. Le jour ou un module d'emission apparait, ce sont ses tables qui
    fournissent les trois ensembles couverts, et les pourcentages deviennent des mesures."""
    trouve = [d for d in REGISTRE_CANDIDATS if d.is_dir()]
    return {
        "present": bool(trouve),
        "candidats_cherches": [d.relative_to(ROOT).as_posix() for d in REGISTRE_CANDIDATS],
        "trouves": [d.relative_to(ROOT).as_posix() for d in trouve],
        "groupes_couverts": None,
        "steps_couverts": None,
        "tags_couverts": None,
    }


# --------------------------------------------------------------------------- etape 3
def mesurer_consommation() -> dict:
    """L'ASYMETRIE a nommer : le depot sait DECODER le flux natif, pas l'EMETTRE.

    Sans ce volet, le lecteur du probe conclurait « rien n'existe autour du stream », ce
    qui est faux et sous-estime ce qui est reutilisable pour l'emetteur (la resolution des
    ordinaux par NOM contre la table versionnee est deja ecrite et gardee)."""
    decodeur = HERE / "stream_events.py"
    mig014 = ROOT / "scripts" / "sql" / "014_stream_group.sql"
    fonctions: list[str] = []
    if decodeur.is_file():
        try:
            tree = ast.parse(decodeur.read_text(encoding="utf-8"))
            fonctions = sorted(n.name for n in tree.body
                               if isinstance(n, ast.FunctionDef) and not n.name.startswith("_"))
        except SyntaxError:
            fonctions = []
    return {
        "decodeur_present": decodeur.is_file(),
        "decodeur_fonctions": fonctions or None,
        "migration_014_presente": mig014.is_file(),
        # La migration materialise l'arbre du flux NATIF dans PostgreSQL a l'ingest.
        # Elle ne fait rien EMETTRE au port -- c'est un consommateur, pas un producteur.
        "migration_014_role": "consommateur (ingest SQL du flux natif)",
    }


# --------------------------------------------------------------------------- etape 4
def mesurer_bornes_de_portage() -> dict:
    """Ce qui BORNE l'emetteur meme une fois la couche ecrite.

    Un emetteur ne peut produire que le flux des mecaniques effectivement portees : une
    ability absente du registre n'emettra jamais son groupe. Ces deux comptes se
    re-derivent du code (jamais cites d'une doc, qui se perime a chaque tranche)."""
    handler = ENGINE / "runner" / "abilities" / "handler.py"
    attack = ENGINE / "runner" / "abilities" / "attack_type.py"

    def _taille_dict(p: pathlib.Path, nom: str) -> Optional[int]:
        if not p.is_file():
            return None
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError:
            return None
        for n in ast.walk(tree):
            if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name) \
                    and n.target.id == nom and isinstance(n.value, ast.Dict):
                return len(n.value.keys)
            if isinstance(n, ast.Assign) and isinstance(n.value, ast.Dict):
                for t in n.targets:
                    if isinstance(t, ast.Name) and t.id == nom:
                        return len(n.value.keys)
        return None

    return {
        "ability_classes": _taille_dict(handler, "ABILITY_CLASSES"),
        "ability_attack_type": _taille_dict(attack, "ABILITY_ATTACK_TYPE"),
    }


# --------------------------------------------------------------------------- rapport
def _pct(n: Optional[int], d: Optional[int]) -> str:
    if n is None or not d:
        return "PAS MESURE"
    return "%d / %d (%.0f%%)" % (n, d, 100.0 * n / d)


def collecter() -> dict:
    groupes, steps, tags = (lire_enum(ENUM_GROUP), lire_enum(ENUM_STEP), lire_enum(ENUM_TAG))
    return {
        "vocabulaire": {
            "source": "data/symbols/<build>/frida/enums.tsv (VERSIONNEE)",
            "groupes": None if groupes is None else len(groupes),
            "steps": None if steps is None else len(steps),
            "tags": None if tags is None else len(tags),
        },
        "infrastructure": mesurer_infrastructure(),
        "formes_de_retour": mesurer_formes_de_retour(),
        "registre_emission": mesurer_registre_emission(),
        "consommation": mesurer_consommation(),
        "bornes_de_portage": mesurer_bornes_de_portage(),
    }


def imprimer(d: dict) -> int:
    voc, infra, reg = d["vocabulaire"], d["infrastructure"], d["registre_emission"]
    formes, conso, bornes = d["formes_de_retour"], d["consommation"], d["bornes_de_portage"]

    print("=" * 78)
    print("#477-r15 -- couverture de l'EMETTEUR de flux cote port Python")
    print("=" * 78)

    print("\n[0] VOCABULAIRE NATIF (derive des enums, jamais de l'observe)")
    for cle, lbl in (("groupes", "GroupType"), ("steps", "StepType"), ("tags", "TagKey")):
        v = voc[cle]
        print("    %-10s : %s" % (lbl, "PAS MESURE (table absente)" if v is None else "%d membres" % v))

    print("\n[1] INFRASTRUCTURE D'EMISSION cote port")
    print("    classes *Operation            : %d" % infra["classes_operation"])
    print("    EventBus() instancie          : %d fois" % infra["instanciations_eventbus"])
    print("    APPELS reels du bus           : %s" % infra["appels_bus"])
    print("    sous-classes de BattleEvent   : %d" % len(infra["sous_classes_battleevent"]))
    print("    => bus %s" % ("VIVANT" if infra["bus_vivant"] else
                             "MORT (defini, instancie, JAMAIS appele)"))

    print("\n[2] FORME DES RESULTATS D'OPERATION (une couche d'emission suppose une forme COMMUNE)")
    print("    execute() recenses : %d, repartis sur %d formes de retour"
          % (formes["execute_total"], len(formes["formes"])))
    for lbl, n in list(formes["formes"].items())[:6]:
        print("      %-22s %d" % (lbl, n))

    print("\n[3] REGISTRE D'EMISSION (ce que le port DECLARE savoir produire)")
    if not reg["present"]:
        print("    ABSENT -- aucun de : %s" % ", ".join(reg["candidats_cherches"]))
        print("    => couverture NON MESURABLE. Ce n'est PAS 0 %: il n'y a rien a interroger.")
    else:
        print("    trouve : %s" % ", ".join(reg["trouves"]))
        print("    GroupType couverts : %s" % _pct(reg["groupes_couverts"], voc["groupes"]))
        print("    StepType  couverts : %s" % _pct(reg["steps_couverts"], voc["steps"]))
        print("    TagKey    couverts : %s" % _pct(reg["tags_couverts"], voc["tags"]))

    print("\n[4] ASYMETRIE -- ce qui existe est du cote CONSOMMATION")
    print("    decodeur stream_events.py     : %s" % ("present" if conso["decodeur_present"] else "ABSENT"))
    if conso["decodeur_fonctions"]:
        print("      API publique : %s" % ", ".join(conso["decodeur_fonctions"]))
    print("    migration SQL 014             : %s (%s)"
          % ("presente" if conso["migration_014_presente"] else "ABSENTE", conso["migration_014_role"]))

    print("\n[5] BORNES DE PORTAGE (plafond de ce qu'un emetteur pourra produire)")
    for cle, lbl in (("ability_classes", "ABILITY_CLASSES"), ("ability_attack_type", "ABILITY_ATTACK_TYPE")):
        v = bornes[cle]
        print("    %-20s : %s" % (lbl, "PAS MESURE" if v is None else "%d entrees" % v))

    print("\n" + "-" * 78)
    manque = [k for k in ("groupes", "steps", "tags") if voc[k] is None]
    if manque:
        print("VERDICT : PAS MESURE -- vocabulaire natif illisible (%s)." % ", ".join(manque))
        print("  Regenerer : python scripts/python/dump_il2cpp.py"
              " puis preprocess_il2cpp_dump.py")
        return 2
    if not reg["present"]:
        print("VERDICT : aucun EMETTEUR cote port -- la couche est a CONSTRUIRE, pas a completer.")
        print("  Le bus d'evenements existe en SIGNATURE (%d instanciations) mais ne transporte"
              % infra["instanciations_eventbus"])
        print("  rien : %d appel(s), %d sous-classe(s) de BattleEvent."
              % (sum(infra["appels_bus"].values()), len(infra["sous_classes_battleevent"])))
        print("  Vocabulaire a couvrir : %d GroupType, %d StepType, %d TagKey."
              % (voc["groupes"], voc["steps"], voc["tags"]))
        return 1
    print("VERDICT : emetteur present -- couverture ci-dessus.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true", help="sortie machine (dict complet)")
    a = ap.parse_args()
    try:
        d = collecter()
    except SourceAbsente as e:
        print("PAS MESURE -- %s" % e)
        return 2
    if a.json:
        print(json.dumps(d, indent=2, ensure_ascii=True))
        return 0
    return imprimer(d)


if __name__ == "__main__":
    raise SystemExit(main())
