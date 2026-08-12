"""#951-r2 -- le LEDGER des VERDICTS de couverture, et le foyer UNIQUE de leur validite.

## Le probleme qu'il ferme

`audit_kit_coverage.py` etablit la couverture en lisant des REGISTRES. Il existe une seconde
raison, parfaitement legitime, pour qu'un item n'y figure PAS : **le natif n'a rien de propre a
porter**. Mesure #951-r2 :

  * `1204 LeadingTheCharge` -- `LeadingTheChargePlaybook$$MakeDamagePredictions` est
    STRUCTURELLEMENT identique au corps generique, verdict etabli et VERROUILLE par #945 ;
  * `GalvanicField` -- ses trois feuilles sont branchees et son playbook rend `Fix64(0)` sur les
    deux faces, verdict MESURE par #952.

Les deux etaient recomptes MANQUANTS a chaque regeneration, et un agent a failli etre redispatche
dessus. Un verdict etabli qui n'est ecrit QUE dans une case-doc ne survit a aucun outil.

## Pourquoi un LEDGER et pas une liste blanche

Une liste blanche « ces noms-la sont OK » ment des que le sujet bouge, et personne ne le voit. Ce
ledger reprend le motif deja eprouve par `probe_462`/#465 : chaque entree porte sa RAISON, sa
SOURCE, son COMMIT, et surtout des ANCRAGES VERIFIABLES qui la font PERIMER quand le sujet bouge.

## L'ASYMETRIE est INVERSE de celle de #465, et c'est structurel

Chez #465 le verdict permissif est `VERT` et il ne perime jamais (un vert perime est
CONSERVATEUR). Ici c'est l'exact contraire : **l'attestation EST le geste permissif** (elle RETIRE
du travail du compte). Donc :

  * une attestation VALIDE decompte l'item -- et il reste IMPRIME, jamais tu ;
  * une attestation PERIMEE **rend l'item MANQUANT**, avec la raison de peremption.

**Aucun chemin ne peut faire disparaitre du travail.** La peremption ne sait que EN RAJOUTER. Un
audit qui sous-compte fait RENONCER, ce qui est pire qu'un audit qui sur-compte et fait perdre du
temps : le sens de la degradation est donc choisi, pas subi.

## Les trois clauses de validite

1. **`build`** -- le verdict a ete lu sur un decompile ; un changement de build peut l'invalider en
   silence. Toute attestation dont le `build` n'est pas celui de `data/symbols/CURRENT` PERIME.
2. **`cliquet`** -- le fichier de test qui garde le verdict doit EXISTER. S'il disparait, plus rien
   ne tient le verdict : il perime.
3. **`porteur`** -- `module:symbole` du code qui PORTE reellement le mecanisme, quand le verdict est
   « porte hors registre ». Il doit etre RESOLVABLE. Si le port disparait, l'attestation perime et
   l'item redevient du travail -- c'est ce qui la distingue d'une declaration morte.

Une entree DOIT porter au moins un ancrage (`cliquet` ou `porteur`) : sans ancrage, elle ne serait
qu'une liste blanche deguisee, et le test l'interdit.

Sortie ASCII. Usage : depuis `scripts/python/`  ->  python coverage_attestations.py [--verbose]
"""
from __future__ import annotations

import importlib
import json
import os
import sys

_PYROOT = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(_PYROOT))

LEDGER = os.path.join(_REPO, "scripts", "ratchets-951r2-couverture-attestee.json")

#: Les categories d'items que le ledger a le droit d'attester. Une categorie inconnue est REFUSEE
#: (elle signifierait qu'on decompte quelque chose que l'audit ne sait pas nommer).
CATEGORIES = ("passif", "trait", "active-decision", "active-combat",
              "conditionnelle-item", "conditionnelle-mythic")

#: Les verdicts admissibles. `RIEN_A_PORTER` = le natif n'a pas de contenu propre (ou il est mort) ;
#: `PORTE_HORS_REGISTRE` = le mecanisme est porte, mais par une voie sans registre.
VERDICTS = ("RIEN_A_PORTER", "PORTE_HORS_REGISTRE")

VALIDE = "VALIDE"
PERIMEE = "PERIMEE"


def build_courant() -> str:
    """Le build sur lequel les decompiles sont lus. `""` si non lisible -- et un build non lisible
    PERIME tout, il ne vaut jamais accord (meme regle tri-etat que `host_inputs`)."""
    p = os.path.join(_REPO, "data", "symbols", "CURRENT")
    try:
        with open(p, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def charger(chemin: str = None) -> dict:
    try:
        with open(chemin or LEDGER, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"attestations": {}}


def _resout(porteur: str) -> bool:
    """`module:symbole` -> le symbole existe-t-il VRAIMENT ? Un `module:` sans symbole exige juste
    que le module s'importe."""
    if not porteur or ":" not in porteur:
        return False
    mod, _, sym = porteur.partition(":")
    try:
        m = importlib.import_module(mod)
    except Exception:
        return False
    return True if not sym else hasattr(m, sym)


def validite(entree: dict, build: str) -> tuple[str, str]:
    """(etat, raison) -- LE foyer UNIQUE. Les lecteurs (`audit_kit_coverage`, le probe, le test)
    passent tous par ici : un garde-fou dont le verdict derive entre ses lecteurs ne vaut rien.

    ⚠ Le SEUL etat qui decompte est `VALIDE`. Toute autre valeur -- y compris une entree malformee,
    une categorie inconnue ou un verdict inconnu -- rend `PERIMEE`, donc REMET l'item au compte.
    C'est la formule invariante de #465 transposee : on ne selectionne pas des cas de peremption
    (une categorie oubliee redeviendrait permissive), on exige les conditions du seul cas permissif.
    """
    if not isinstance(entree, dict):
        return PERIMEE, "entree malformee"
    if entree.get("verdict") not in VERDICTS:
        return PERIMEE, "verdict inconnu: %r" % (entree.get("verdict"),)
    if entree.get("categorie") not in CATEGORIES:
        return PERIMEE, "categorie inconnue: %r" % (entree.get("categorie"),)
    if not (entree.get("raison") or "").strip():
        return PERIMEE, "aucune raison ecrite"
    src = (entree.get("source") or "").strip()
    if not src or not os.path.exists(os.path.join(_REPO, src.split("#")[0])):
        return PERIMEE, "source absente du depot: %r" % (src,)
    b = entree.get("build") or ""
    if not build:
        return PERIMEE, "build courant NON LISIBLE (data/symbols/CURRENT)"
    if b != build:
        return PERIMEE, ("lu sur le build %r, le build courant est %r -- un decompile relu ailleurs "
                         "n'atteste rien ici" % (b, build))
    cliquet, porteur = (entree.get("cliquet") or "").strip(), (entree.get("porteur") or "").strip()
    if not cliquet and not porteur:
        return PERIMEE, "aucun ancrage verifiable (ni `cliquet` ni `porteur`)"
    if cliquet and not os.path.exists(os.path.join(_REPO, cliquet)):
        return PERIMEE, "cliquet absent: %r -- plus rien ne tient ce verdict" % cliquet
    if porteur and not _resout(porteur):
        return PERIMEE, "porteur non resolvable: %r -- le port a disparu" % porteur
    return VALIDE, entree["verdict"]


def attestations_valides(chemin: str = None) -> dict[tuple[str, str], dict]:
    """(categorie, nom) -> entree, pour les seules attestations VALIDES."""
    b = build_courant()
    out = {}
    for cle, e in (charger(chemin).get("attestations") or {}).items():
        etat, _r = validite(e, b)
        if etat == VALIDE:
            out[(e["categorie"], e["nom"])] = e
    return out


def ventiler(chemin: str = None) -> tuple[list, list]:
    """(valides, perimees) -- chaque element est `(cle, entree, raison)`."""
    b = build_courant()
    val, per = [], []
    for cle, e in sorted((charger(chemin).get("attestations") or {}).items()):
        etat, r = validite(e, b)
        (val if etat == VALIDE else per).append((cle, e, r))
    return val, per


def main() -> int:
    val, per = ventiler()
    print("build courant : %r" % (build_courant() or "(NON LISIBLE)"))
    print("attestations VALIDES : %d ; PERIMEES : %d" % (len(val), len(per)))
    for cle, e, r in val:
        print("  [VALIDE ] %-34s %-20s %s" % (cle, e.get("verdict"), e.get("source")))
        if "--verbose" in sys.argv:
            print("            raison : %s" % e.get("raison"))
    for cle, e, r in per:
        print("  [PERIMEE] %-34s %s" % (cle, r))
    if per:
        print()
        print("Une attestation PERIMEE REMET son item au compte des manquants -- c'est le sens sur")
        print("(la peremption ne sait que RAJOUTER du travail). Relire le decompile, puis re-attester.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
