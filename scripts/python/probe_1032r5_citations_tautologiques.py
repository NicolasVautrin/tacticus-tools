"""#1032-r5 -- RECENSER les phrases ou une migration VA -> SYMBOLE a FONDU DEUX SURCHARGES.

LE GISEMENT. La regle « on cite un SYMBOLE, jamais une adresse » a un COUT CACHE quand la cible est
SURCHARGEE : deux VAs distinctes resolvent sur le MEME nom, et une phrase qui portait un CONTRASTE
(`@A` contre `@B`) devient une TAUTOLOGIE (`X` contre `X`). Rien ne le signale : le texte reste
grammatical, il ne dit simplement plus rien. Cas motivant, deja repare :
`abilities/sisterhood.py` disait mot pour mot << `X`, ABSENT de `X` ; `X` == `X` SAUF QUE... >>.

CRITERE. Une ligne est SUSPECTE quand la MEME citation `<Namespace>.<Classe>$$<Methode>` y apparait
au moins DEUX fois. Deux familles la peuplent, et elles ne se distinguent PAS par le compte :

  * LEGITIME -- les occurrences portent des SUFFIXES D'OFFSET differents (`...$$Execute+0x7dc` /
    `...$$Execute+0x82e`) : ce sont deux POINTS d'une meme fonction, et l'offset EST le
    discriminant. La citation, elle, est bien la meme.
  * LEGITIME -- la PROSE porte le discriminant a cote (`(mono) / (groupe)`, `(7 args) -> core`,
    `surcharge 6-args`). Le contraste vit dans la phrase, pas dans le symbole.
  * VACANTE -- rien ne distingue les deux occurrences : la phrase est vide.

Le probe RANGE, il ne tranche pas : la troisieme famille se lit une par une, et la reparation
consiste a NOMMER chaque surcharge par le parametre qui la separe, lu dans
`data/symbols/<build>/frida/methods.tsv` (`--signatures <Methode>` l'imprime).

&#9888; LA 3e FAMILLE PORTE DE VRAIS FAUX POSITIFS, ET C'EST MESURE. Une ligne peut nommer DEUX FOIS
la meme fonction pour une raison legitime : `abilities/tyranids.py` ecrit << DIFFERENCE avec
`AberrantHypermorphAbility$$ExecuteBehaviour` (VERIFIE par decompile
`SporeMineLauncherAbility$$ExecuteBehaviour` vs `AberrantHypermorphAbility$$ExecuteBehaviour`) >> --
le contraste y est porte par un TROISIEME symbole, et la repetition est celle du sujet. Un critere
qui condamnerait automatiquement se ferait donc desarmer ; celui-ci INVENTORIE.

    python probe_1032r5_citations_tautologiques.py                  # le recensement, range
    python probe_1032r5_citations_tautologiques.py --vacantes       # la 3e famille seule
    python probe_1032r5_citations_tautologiques.py --signatures AttackWithAttackDamage

ASCII only.
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
REPO = PYDIR.parents[1]

#: `<Namespace>.<Classe>$$<Methode>` -- MEME forme que `probe_419r1tr9r4r1r3_symboles_cites_absents`.
CITE = re.compile(r"\b([A-Za-z_][\w.]*)\$\$([A-Za-z_]\w*)")
#: Un SUFFIXE D'OFFSET juste apres la citation : `+0x1eb`. C'est le discriminant LEGITIME numero 1.
OFFSET = re.compile(r"\$\$[A-Za-z_]\w*\+0x[0-9a-fA-F]+")
#: Un discriminant EN PROSE, entre parentheses ou introduit par un mot d'arite/de role. Liste
#: DELIBEREMENT large : le probe RANGE, il ne condamne pas -- un faux « legitime » se relit.
PROSE = re.compile(
    r"\(mono\)|\(groupe\)|\bcore\b|\bsurcharge\b|\bENVELOPPE\b|\bCOEUR\b|"
    r"\d+[- ]args?\b|\bparam \d|\bhits:|\bdamageProfile:|\bordinal\b|\boverload\b",
    re.IGNORECASE)

EXT = {".py"}


def _lignes(racine: Path):
    for p in sorted(racine.rglob("*")):
        if p.is_file() and p.suffix in EXT:
            try:
                src = p.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for num, ligne in enumerate(src.splitlines(), 1):
                yield p, num, ligne


def recenser(racine: Path):
    """Rend `{famille: [(fichier, ligne, citation, compte, texte)]}` -- trois familles."""
    out = {"OFFSETS": [], "PROSE": [], "VACANTE": []}
    for p, num, ligne in _lignes(racine):
        cites = ["%s$$%s" % (a, b) for a, b in CITE.findall(ligne)]
        if not cites:
            continue
        c = Counter(cites)
        rep = sorted(k for k, v in c.items() if v >= 2)
        if not rep:
            continue
        # Un suffixe d'offset present sur la ligne suffit : c'est LUI qui separe les occurrences.
        famille = "OFFSETS" if OFFSET.search(ligne) else ("PROSE" if PROSE.search(ligne)
                                                          else "VACANTE")
        for k in rep:
            out[famille].append((p.relative_to(REPO).as_posix(), num, k, c[k], ligne.strip()))
    return out


def signatures(methode: str) -> int:
    """Les surcharges de `<Methode>` et le parametre qui les separe -- la SOURCE de la reparation."""
    import probe_419r1tr9r4r1r3_symboles_cites_absents as P
    build = P.build_courant()
    tsv = REPO / "data" / "symbols" / build / "frida" / "methods.tsv"
    if not tsv.exists():
        print("NON MESURE : %s absent" % tsv.relative_to(REPO).as_posix())
        return 2
    trouve = 0
    for l in tsv.read_text(encoding="utf-8").splitlines():
        c = l.split("\t")
        if len(c) < 6 or not c[1].endswith("." + methode):
            continue
        trouve += 1
        print("  %s.%s" % (c[2], methode))
        print("      -> %s (%s)" % (c[4], c[5] or ""))
    if not trouve:
        print("NON MESURE : aucune surcharge nommee %r dans la table" % methode)
        return 2
    print("")
    print("SURCHARGES : %d" % trouve)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--racine", default="scripts/python")
    ap.add_argument("--vacantes", action="store_true", help="la 3e famille seule")
    ap.add_argument("--signatures", metavar="METHODE",
                    help="imprime les surcharges de METHODE et leurs parametres")
    a = ap.parse_args()
    if a.signatures:
        return signatures(a.signatures)

    racine = REPO / a.racine
    if not racine.exists():
        print("NON MESURE : racine %r absente" % a.racine)
        return 2
    fam = recenser(racine)
    total = sum(len(v) for v in fam.values())
    print("RACINE             : %s" % a.racine)
    print("CITATIONS REPETEES : %d sur une meme ligne" % total)
    if total == 0:
        print("NON MESURE : aucune ligne ne porte deux fois la meme citation -- ce zero est")
        print("             SUSPECT (le corpus en porte des dizaines), verifier le motif `CITE`.")
        return 2
    for nom, libelle in (("OFFSETS", "discriminant = un SUFFIXE D'OFFSET (`+0x...`) : LEGITIME"),
                         ("PROSE", "discriminant = LA PROSE (arite, `core`, `(mono)/(groupe)`)"),
                         ("VACANTE", "AUCUN discriminant -- la phrase ne dit plus rien")):
        if a.vacantes and nom != "VACANTE":
            continue
        print("")
        print("=== %-8s %d -- %s" % (nom, len(fam[nom]), libelle))
        for f, num, cite, n, txt in fam[nom]:
            print("  %s:%d  x%d  %s" % (f, num, n, cite))
            print("        | %s" % txt[:150])
    print("")
    print("REPARER : nommer chaque surcharge par le parametre qui la separe --")
    print("          `--signatures <Methode>` imprime la table, et les XREFS (`list_xrefs`)")
    print("          tranchent QUELLE surcharge un call-site donne vise. Le pseudo-C ne le dit")
    print("          PAS : il affiche le meme nom pour toutes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
