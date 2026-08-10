"""#433-r3-r3 -- LE BALAYAGE DES SLOTS CITES EXISTE DEJA ; CE QUI MANQUE EST SA PORTEE.

La ligne de backlog demande << un balayage des slots cites en commentaire, au changement de
build >>. Ce balayage EXISTE : `probe_477r25_slots_autres_interfaces.py` recolte les couples
`(interface, slot, nom)` sur tout le depot et les confronte a
`data/symbols/<build>/metadata/interface_slots.tsv`. Mesure du 2026-08-10 sur `rnca9r7q6c` :
**0 citation au SLOT/NOM faux, 0 arite fausse** -- donc l'enonce << reste a faire >> est PERIME.

CE QUI RESTE, et que ce probe mesure : `probe_477r25.RE_SLOT` est **SENSIBLE A LA CASSE**. Son
propre recenseur le DIT (`_RE_SLOT_AUTRE_CASSE`, section << PORTEE DE LA MESURE >>) et le CHIFFRE
-- 189 lignes ecrivent `Slot`/`SLOT` et n'entrent dans AUCUNE cause : elles sont INVISIBLES, pas
ecartees. Un compte de fautes rendu sur un corpus incomplet se lit comme exhaustif ; c'est le vice
exact que ce recenseur existe pour ne pas commettre, et le chiffrer ne le REPARE pas.

METHODE -- l'ANGLE MORT est mesure par le MEME appareil, sur un texte NORMALISE :

  1. on prend le perimetre et les tables de #477-r25 (aucune liste blanche recopiee : les deux
     sont DERIVES de son module, donc un elargissement de son perimetre elargit celui-ci) ;
  2. pour chaque fichier, on rejoue sa recolte DEUX fois -- texte tel quel (REFERENCE), puis
     texte dont les seules occurrences de `slot` a autre casse sont abaissees (`Slot` -> `slot`).
     Rien d'autre n'est touche : les noms d'interface, de methode et les chiffres sont intacts ;
  3. les citations NOUVELLES (celles que la casse cachait) sont confrontees aux tables.

Le probe est ROUGE si une citation nouvelle est FAUSSE (slot/nom ou arite), VERT sinon. Il est
`PAS MESURE` (rc 3) si le metadata du build manque -- jamais un zero.

⚠ CE PROBE N'ECRIT PAS DANS LE CACHE VERSIONNE de #477-r25 : il appelle `_contribution`, la
fonction PURE par fichier, jamais `recolter` (qui passe par `verdict_cache`). Faire entrer un
texte MUTE dans un cache partage y laisserait des verdicts qui ne decrivent aucun fichier du
depot.

Usage :
    python probe_433_r3_r3_slots_autre_casse.py            # verdict
    python probe_433_r3_r3_slots_autre_casse.py --lister   # + les citations rendues visibles
    python probe_433_r3_r3_slots_autre_casse.py --mutate   # contre-epreuve (doit ROUGIR)
"""
from __future__ import annotations

import argparse
import re
import sys

import probe_477r25_slots_autres_interfaces as R25

#: Les occurrences de `slot`/`slots` ecrites avec une AUTRE casse que celle que `R25.RE_SLOT`
#: reconnait. Le motif est DERIVE du sien (`_RE_SLOT_AUTRE_CASSE`), pas recopie : c'est lui qui
#: definit ce que << autre casse >> veut dire pour l'appareil qu'on complete.
_RE_AUTRE_CASSE = R25._RE_SLOT_AUTRE_CASSE


def normaliser_casse(texte: str) -> tuple[str, int]:
    """Abaisse la casse des SEULES occurrences de `slot`/`slots` ; rend `(texte, n abaissees)`.

    Ce qui n'est PAS touche : les noms d'interface, de methode, les chiffres, la ponctuation.
    Une occurrence deja en minuscules est laissee telle quelle (elle est deja vue par R25), donc
    le compte rendu est bien celui du DELTA de perimetre.
    """
    n = 0

    def _abaisse(m: re.Match) -> str:
        nonlocal n
        s = m.group(0)
        if s.islower():
            return s
        n += 1
        return s.lower()

    return _RE_AUTRE_CASSE.sub(_abaisse, texte), n


def _rx_noms(tables) -> dict:
    """Le meme dictionnaire de motifs que `R25.recolter` construit pour son recenseur."""
    return {iface: R25._regex_noms(frozenset(v[0] for v in t.values()))
            for iface, t in tables.items() if t}


def _cle(c) -> tuple:
    return (c.fichier, c.ligne, c.iface, c.slot, c.nom, c.ligne_nom)


def recolter_delta(tables, muter: bool = False):
    """(citations rendues VISIBLES par l'abaissement de casse, nb de fichiers touches,
    nb d'occurrences abaissees).

    `muter` injecte une faute FABRIQUEE dans le texte normalise (une citation `Slot` dont le nom
    est celui du slot VOISIN) -- contre-epreuve : sans elle, un probe qui ne trouverait jamais
    rien serait indistinguable d'un probe casse.
    """
    rx = _rx_noms(tables)
    delta, fichiers, abaissees = [], 0, 0
    #: DEDUPLICATION, comme `R25.recolter` : plusieurs FORMES -- et, en fenetre, plusieurs BLOCS --
    #: captent le MEME couple. Sans elle une citation unique se compte six fois, et le nombre
    #: imprime cesse de designer des sites.
    vus: set[tuple] = set()
    #: ⚠ LE MUTANT S'INJECTE AVANT L'ABAISSEMENT, jamais apres. Ajoute au texte NORMALISE, il
    #: garde sa majuscule et reste invisible des DEUX cotes : la contre-epreuve passe alors au
    #: VERT et se lit comme une preuve, alors qu'elle n'a rien exerce. Faute commise ici meme, et
    #: c'est le seul regime ou ce probe pouvait mentir.
    mutant = _ligne_mutante(tables) if muter else ""
    for rel, texte in R25.textes_balayes():
        source = texte + mutant
        norm, n = normaliser_casse(source)
        if n == 0:
            continue
        fichiers += 1
        abaissees += n
        avant = {_cle(c) for c in R25._contribution(
            rel, source, tables, R25.FENETRE, R25._COUPLES_ML, rx)[0]}
        for c in R25._contribution(rel, norm, tables, R25.FENETRE, R25._COUPLES_ML, rx)[0]:
            if _cle(c) in avant or _cle(c) in vus:
                continue
            vus.add(_cle(c))
            delta.append(c)
    return delta, fichiers, abaissees


def _ligne_mutante(tables) -> str:
    """Une citation FABRIQUEE, ecrite en `Slot` (donc invisible a R25 seul) et FAUSSE.

    Le couple est DERIVE de la table : on prend un slot d'`IBattleQuery` et on lui accole le nom
    du slot SUIVANT. Une faute inventee de toutes pieces (nom absent de l'interface) serait
    classee `indecidable` par `confronter` et ne rougirait rien -- c'est exactement le mutant
    inerte qu'il faut eviter.

    ⚠ ET LES DEUX NOMS DOIVENT DIFFERER. `IBattleQuery` aligne des SURCHARGES homonymes sur des
    slots consecutifs (96/97/98 = `AreEntitiesAdjacent`, 122/123/124 = `GetAdjacentUnits`) :
    decaler d'un cran y produit un couple JUSTE, donc un mutant qui ne peut pas rougir. Mesure :
    le premier tirage (milieu de table, sans cette contrainte) tombait exactement dessus.
    """
    table = tables.get("IBattleQuery", {})
    slots = sorted(s for s in table if s + 1 in table and table[s][0] != table[s + 1][0])
    if not slots:
        raise SystemExit("PAS MESURE : aucune paire de slots consecutifs de noms DIFFERENTS -- "
                         "aucun mutant mordant ne peut etre fabrique")
    s = slots[len(slots) // 2]
    return "\n# Slot 0x%x = `IBattleQuery.%s` (mutant #433-r3-r3)\n" % (s, table[s + 1][0])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lister", action="store_true",
                    help="imprime les citations rendues visibles par l'abaissement de casse")
    ap.add_argument("--mutate", action="store_true",
                    help="contre-epreuve : injecte une citation FAUSSE en `Slot` (doit ROUGIR)")
    args = ap.parse_args()

    tables = R25.deriver()
    source = "global-metadata du build"
    if tables is None:
        tables = R25.lire_tsv()
        source = "l'entree versionnee `interface_slots.tsv`"
    if not tables:
        print("PAS MESURE : ni le metadata du build ni le TSV versionne ne donnent de table.")
        return 3

    invisibles = R25._compter_autre_casse_fichier
    total_invisibles = sum(invisibles(t) for _, t in R25.textes_balayes())

    print("[0] PORTEE   : tables lues depuis %s (%d interface(s))" % (source, len(tables)))
    print("[1] ANGLE MORT de `probe_477r25` : %d ligne(s) ecrivent `slot` avec une AUTRE casse "
          "et n'entrent dans AUCUNE de ses causes." % total_invisibles)

    delta, fichiers, abaissees = recolter_delta(tables, muter=args.mutate)
    print("[2] ABAISSEMENT : %d occurrence(s) sur %d fichier(s) -> %d citation(s) NOUVELLE(S)"
          % (abaissees, fichiers, len(delta)))

    faux_nom, faux_arite, autre_iface = R25.confronter(delta, tables)
    if args.lister:
        for c in delta:
            print("      %s:%d [%s] slot 0x%x = %s" % (c.fichier, c.ligne, c.iface, c.slot,
                                                       c.nom))
    if autre_iface:
        print("[3] %d couple(s) JUSTES mais portes par une AUTRE interface (appariement, pas "
              "faute du depot) :" % len(autre_iface))
        for x in autre_iface:
            print("      " + x)
    print("[3] CONFRONTATION : %d citation(s) au SLOT/NOM faux" % len(faux_nom))
    for x in faux_nom:
        print("      " + x)
    print("[4] ARITE     : %d citation(s) dont le compte d'arguments contredit la signature"
          % len(faux_arite))
    for x in faux_arite:
        print("      " + x)

    rouge = bool(faux_nom or faux_arite)
    print("")
    print("VERDICT : %s" % ("ROUGE" if rouge else "VERT"))
    if not rouge and not args.mutate:
        print("  L'angle mort de CASSE est MESURE et INOFFENSIF sur ce build : les %d lignes "
              "invisibles" % total_invisibles)
        print("  ne portent aucun couple faux. Ce n'est pas une deduction -- elles ont ete "
              "RENDUES visibles")
        print("  et confrontees. Rejouer au changement de build (c'est ce que #433-r3-r3 "
              "demandait).")
    return 1 if rouge else 0


if __name__ == "__main__":
    sys.exit(main())
