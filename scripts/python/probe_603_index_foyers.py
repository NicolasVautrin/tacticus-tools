"""#603 -- FOYER/BLOCAGE des residus : la CALIBRATION qui refute la voie mecanique, et l'INDEX de dispatch.

LE CRITERE, ENONCE AVANT LA METHODE
------------------------------------
Question binaire : **peut-on DERIVER mecaniquement le champ `FOYER:` d'un residu depuis le
texte de sa fiche ?** Si oui, on remplit 176 lignes par programme. Si non, on le DIT et on
lit. L'oracle est GRATUIT et il preexiste : **116 fiches deja annotees a la main**.

LA REPONSE EST NON, ET ELLE EST MESUREE (2026-08-10, `f39a1ee4`)
-----------------------------------------------------------------
Trois sources, chacune plausible, toutes refutees en ACCORD EXACT sur les 103 fiches dont le
foyer humain est non vide :

    A  chemins cites dans le CORPS de la fiche      exact   2  partiel  9  faux 17  abst 75
    B  symbole natif cite -> fichier qui le mirror  exact   1  partiel 30  faux 29  abst 43
    D  foyer d'une fiche SOEUR (meme famille #n)    exact   0  partiel 19  faux 50  abst 34
    A+B+D                                           exact   1  partiel 49  faux 46  abst  7

`A+B+D` couvre **35 %** des chemins humains en en proposant **1010 pour 192 vrais** (5,3x).
Un remplissage automatique ecrirait donc majoritairement des foyers FAUX -- et un foyer faux
est PIRE que son absence : il fait dispatcher deux agents sur le meme fichier en croyant les
avoir separes. C'est le meme resultat sur l'axe BLOCAGE, ou la derivation par mots-cles rend
**55 %** d'accord contre **59 %** pour la baseline triviale << tout `aucun` >> : elle est
donc MOINS BONNE QUE DE NE RIEN FAIRE, et sa faute dominante est le faux positif (20 fiches
que l'humain a classees `aucun` et que les mots-cles arment en `capteur`/`seeding`).

POURQUOI LA VOIE MECANIQUE NE POUVAIT PAS MARCHER
---------------------------------------------------
Le << Point d'entree >> et le corps disent OU LIRE ; le foyer dit OU ECRIRE. Mesure directe :
sur les 103 fiches, les chemins du foyer humain apparaissent VERBATIM dans le corps pour
**3 seulement**. Le foyer est un acte de LECTURE (<< je viens de lire le decompile et je sais
quel mirror est en cause >>), pas une extraction. Aucun regex ne le remplace.

CE QUE CE FOYER FAIT DONC
--------------------------
  * `--calibrer`   : rejoue la mesure ci-dessus. C'est un CLIQUET : si une source devenait
                     fiable (nouvelle discipline d'ecriture des fiches), il le dirait.
  * `--recenser`   : partition EXHAUSTIVE du backlog, bac `INDETERMINE` visible, somme imprimee.
  * `--feuille`    : la feuille de travail d'une lecture HUMAINE (fiche + candidats A/B/D).
  * `--index`      : (re)genere `docs/rl/index-foyers.md`, une VUE de ce que le backlog PORTE.
                     L'index ne contient aucune proposition : il PROJETTE les champs ecrits.
                     Il ne peut donc pas se perimer autrement que le backlog lui-meme.

Sortie ASCII stricte (console Windows cp1252).
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import backlog_entries as B  # noqa: E402

RACINE = Path(__file__).resolve().parents[2]
BACKLOG = RACINE / "docs" / "rl" / "backlog.md"
INDEX = RACINE / "docs" / "rl" / "index-foyers.md"

EX_OK = 0
EX_ROUGE = 1
EX_NON_MESURE = 99

_SYM = re.compile(r"([A-Za-z0-9_.]+\$\$[A-Za-z0-9_.<>]+)")


# --------------------------------------------------------------------------- inventaire


def _git(*args: str) -> str:
    r = subprocess.run(["git", "-C", str(RACINE)] + list(args),
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError("git %s a echoue : %s" % (" ".join(args), r.stderr.strip()[:200]))
    return r.stdout


class Depot:
    """Les chemins VERSIONNES, seule autorite sur << ce fichier existe-t-il >>."""

    def __init__(self) -> None:
        self.fichiers = {l for l in _git("ls-files").split("\n") if l}
        self.reps: set[str] = set()
        for f in self.fichiers:
            p = f
            while "/" in p:
                p = p.rsplit("/", 1)[0]
                self.reps.add(p + "/")

    def resoudre(self, p: str) -> str | None:
        """Chemin canonique versionne, ou None. Tolere l'omission de `scripts/python/`.

        Un glob (`.../**`, `probe_366r1_*.py`) est RENDU TEL QUEL s'il apparie au moins un
        fichier : c'est une ecriture legitime du backlog (11 foyers humains en portent), et
        la refuser ferait rendre << introuvable >> a des foyers justes.
        """
        for c in (p, "scripts/python/" + p):
            if c in self.fichiers:
                return c
            if c.rstrip("/") + "/" in self.reps:
                return c.rstrip("/") + "/"
            if "*" in c:
                motif = re.escape(c).replace(r"\*\*", ".*").replace(r"\*", "[^/]*")
                if any(re.fullmatch(motif, f) for f in self.fichiers):
                    return c
        return None


def _index_symboles(depot: Depot) -> dict[str, set[str]]:
    idx: dict[str, set[str]] = {}
    for f in sorted(depot.fichiers):
        if not (f.startswith("scripts/python/") and f.endswith(".py")):
            continue
        if "/tests/" in f:
            continue
        try:
            txt = (RACINE / f).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for m in _SYM.finditer(txt):
            idx.setdefault(m.group(1), set()).add(f)
    return idx


# --------------------------------------------------------------------------- sources


def source_a(e: B.Entree, depot: Depot) -> set[str]:
    """Chemins cites dans le corps de la fiche (hors `docs/`)."""
    out = set()
    for p in B.chemins_de(e.corps):
        if p.startswith("docs/"):
            continue
        r = depot.resoudre(p)
        if r and not r.startswith("docs/"):
            out.add(r)
    return out


def source_b(e: B.Entree, idx: dict[str, set[str]]) -> set[str]:
    """Fichiers du port qui CITENT un symbole natif nomme dans la fiche."""
    out = set()
    for m in _SYM.finditer(e.corps):
        out |= idx.get(m.group(1), set())
    return out


def _famille(ident: str) -> str | None:
    m = re.match(r"#?(\d+)", ident)
    return m.group(1) if m else None


def source_d(e: B.Entree, verite: dict[str, set[str]],
             par_famille: dict[str, list[B.Entree]]) -> set[str]:
    """Foyer des fiches SOEURS (meme racine `#n`)."""
    out: set[str] = set()
    for autre in par_famille.get(_famille(e.ident) or "", []):
        if autre.ident != e.ident:
            out |= verite.get(autre.ident, set())
    return out


# --------------------------------------------------------------------------- modes


def _charger():
    entrees = B.lire(BACKLOG)
    depot = Depot()
    ouvertes = [e for e in entrees if e.ouverte]
    annotees = [e for e in ouvertes if e.annotee]
    verite: dict[str, set[str]] = {}
    for e in annotees:
        s = set()
        for p in e.foyer_chemins:
            r = depot.resoudre(p)
            if r:
                s.add(r)
        verite[e.ident] = s
    return entrees, ouvertes, annotees, verite, depot


def mode_recenser() -> int:
    entrees, ouvertes, annotees, verite, depot = _charger()
    non = [e for e in ouvertes if not e.annotee]
    fermees = [e for e in entrees if e.ferme]

    print("=" * 78)
    print("[603] RECENSEMENT du backlog -- partition EXHAUSTIVE")
    print("=" * 78)
    print("lignes de tableau visitees : %d" % len(entrees))
    print("   FERMEES (titre barre)        : %d" % len(fermees))
    print("   OUVERTES                     : %d" % len(ouvertes))
    print("      dont ANNOTEES (FOYER+BLOCAGE) : %d" % len(annotees))
    print("      dont NON ANNOTEES             : %d" % len(non))
    somme = len(fermees) + len(annotees) + len(non)
    print("   SOMME %d + %d + %d = %d  (== %d visitees : %s)"
          % (len(fermees), len(annotees), len(non), somme, len(entrees),
             "OUI" if somme == len(entrees) else "NON -- PARTITION CASSEE"))

    print("\n-- par SECTION (les lignes de tableau) --")
    par_sec: dict[str, Counter] = defaultdict(Counter)
    for e in entrees:
        etat = "fermee" if e.ferme else ("annotee" if e.annotee else "non annotee")
        par_sec[e.section][etat] += 1
    for sec, c in par_sec.items():
        ecart = B.SECTIONS_NON_DISPATCHABLES.get(
            next((k for k in B.SECTIONS_NON_DISPATCHABLES if sec.startswith(k)), ""), None)
        print("   %-58s %s" % (sec[:58], dict(c)))
        if ecart:
            print("      ECARTEE DE L'INDEX : %s" % ecart)

    pu = B.puces(BACKLOG)
    print("\n-- entrees en PUCE (hors tableau) : %d --" % len(pu))
    cp: Counter = Counter(s for _, s, _ in pu)
    for sec, n in cp.most_common():
        barrees = sum(1 for _, s, t in pu if s == sec and t.startswith("- ~~"))
        print("   %-58s %3d dont %d barrees" % (sec[:58], n, barrees))
    print("   ECARTEES DE L'INDEX DE DISPATCH : aucune ne porte de champ FOYER, et la section")
    print("   qui en concentre le plus dit d'elle-meme << pas encore des taches >>. Elles sont")
    print("   COMPTEES ici pour que ce recensement ne rende pas zero sur ce qu'il ne visite pas.")

    print("\n-- ce que ce recensement N'A PAS mesure --")
    print("   * les fiches d'une section NON DISPATCHABLE ne sont pas jugees sur leur foyer ;")
    print("   * une ligne sans jeton `[modele]` n'a pas de point d'insertion derivable :")
    sans = [e for e in ouvertes if e.pos_modele is None]
    print("     %d ligne(s) ouverte(s) dans ce cas -> %s"
          % (len(sans), ", ".join(e.ident for e in sans) or "aucune"))
    return EX_OK


def mode_calibrer(verbeux: bool = False) -> int:
    entrees, ouvertes, annotees, verite, depot = _charger()

    # ---- L'ORACLE NE PEUT PAS CONTENIR CE QUE CETTE TRANCHE A ECRIT.
    # #603 a inscrit 173 champs `FOYER:` dans le backlog. Les laisser dans l'oracle ferait
    # noter le deriveur contre des reponses issues de la MEME lecture -- un oracle qui se note
    # lui-meme. On EXCLUT donc les fiches listees par `scripts/migration-603-foyers.tsv`, et on le DIT :
    # la calibration porte sur les fiches annotees par d'AUTRES tranches, seule verite terrain
    # independante disponible.
    from index_foyers import cle, lire_decisions
    ecrites_par_603 = set(lire_decisions())
    annotees = [e for e in annotees if cle(e.ident) not in ecrites_par_603]
    verite = {k: v for k, v in verite.items() if cle(k) not in ecrites_par_603}

    idx = _index_symboles(depot)
    par_famille: dict[str, list[B.Entree]] = defaultdict(list)
    for e in annotees:
        f = _famille(e.ident)
        if f:
            par_famille[f].append(e)

    corpus = [e for e in annotees if verite.get(e.ident)]
    if not corpus:
        print("[603] AUCUNE fiche annotee a foyer non vide -- rien a calibrer.")
        return EX_NON_MESURE

    print("=" * 78)
    print("[603] CALIBRATION du dériveur contre les fiches DEJA annotees a la main".replace("é", "e"))
    print("=" * 78)
    print("oracle : %d fiches annotees PAR D'AUTRES TRANCHES, dont %d a foyer non vide (les %d"
          % (len(annotees), len(corpus), len(annotees) - len(corpus)))
    print("         autres portent `aucun`, `?` ou `docs/**`, qui ne designent aucun fichier)")
    print("         Les %d fiches ecrites par #603 sont EXCLUES : un oracle qui contient les"
          % len(ecrites_par_603))
    print("         reponses de la meme lecture se noterait lui-meme.")

    sources = {
        "A corps de la fiche": lambda e: source_a(e, depot),
        "B symbole natif": lambda e: source_b(e, idx),
        "D fiche soeur": lambda e: source_d(e, verite, par_famille),
        "A+B": lambda e: source_a(e, depot) | source_b(e, idx),
        "A+B+D": lambda e: (source_a(e, depot) | source_b(e, idx)
                            | source_d(e, verite, par_famille)),
    }
    print("\n%-24s %7s %8s %6s %11s %8s" %
          ("source", "exact", "partiel", "faux", "abstention", "n"))
    resultats = {}
    for nom, fn in sources.items():
        ex = pa = fa = ab = 0
        for e in corpus:
            v = verite[e.ident]
            d = fn(e)
            if not d:
                ab += 1
            elif d == v:
                ex += 1
            elif d & v:
                pa += 1
            else:
                fa += 1
        resultats[nom] = (ex, pa, fa, ab)
        print("%-24s %7d %8d %6d %11d %8d" % (nom, ex, pa, fa, ab, len(corpus)))

    tot_v = sum(len(verite[e.ident]) for e in corpus)
    print("\n%-24s %s" % ("", "-- rappel/precision PAR CHEMIN --"))
    for nom, fn in sources.items():
        couverts = sum(len(fn(e) & verite[e.ident]) for e in corpus)
        proposes = sum(len(fn(e)) for e in corpus)
        print("%-24s couvre %4d/%4d chemins humains (%3.0f%%) en proposant %5d (%.1fx)"
              % (nom, couverts, tot_v, 100.0 * couverts / tot_v, proposes,
                 proposes / max(tot_v, 1)))

    # ---- axe BLOCAGE : derivation par mots-cles contre baseline triviale
    print("\n-- axe BLOCAGE --")
    ok = sum(1 for e in annotees if e.blocage and _blocage_mots_cles(e.corps) == e.blocage)
    base = sum(1 for e in annotees if e.blocage == "aucun")
    n = sum(1 for e in annotees if e.blocage)
    print("   derivation par mots-cles : %d/%d = %.0f%%" % (ok, n, 100.0 * ok / n))
    print("   baseline << tout aucun >> : %d/%d = %.0f%%" % (base, n, 100.0 * base / n))
    verdict_bloc = "REFUTEE" if ok <= base else "utilisable"
    print("   => derivation par mots-cles %s (elle doit BATTRE la baseline)" % verdict_bloc)

    # ---- VERDICT
    meilleur = max(resultats.items(), key=lambda kv: kv[1][0])
    ex, pa, fa, ab = meilleur[1]
    print("\n" + "=" * 78)
    print("VERDICT : meilleure source = %s, accord EXACT %d/%d (%.0f%%), FAUX %d"
          % (meilleur[0], ex, len(corpus), 100.0 * ex / len(corpus), fa))
    if ex < fa:
        print("  => DERIVATION MECANIQUE REFUTEE : elle produit plus de foyers FAUX que de")
        print("     foyers justes. Un foyer faux fait dispatcher deux agents sur le meme")
        print("     fichier en croyant les avoir separes -- il est PIRE que son absence.")
        print("     Le champ se remplit donc par LECTURE de la fiche, et ce foyer ne sert")
        print("     qu'a fournir des CANDIDATS (`--feuille`) et a valider les chemins ecrits.")
    else:
        print("  => la derivation bat le bruit ; re-examiner si on veut l'automatiser.")
    print("=" * 78)

    if verbeux:
        print("\n-- detail des ecarts (source A+B+D) --")
        fn = sources["A+B+D"]
        for e in corpus[:40]:
            v, d = verite[e.ident], fn(e)
            if d != v:
                print("  %-20s humain=%s" % (e.ident, sorted(v)))
                print("  %-20s derive=%s" % ("", sorted(d)[:6]))
    return EX_OK


_MOTS_BLOCAGE = {
    "capteur": (r"fen[eê]tre de reinject", r"reinject", r"\bcapteur\b", r"NON ARME",
                r"non arm[eé]", r"frida/hooks", r"hooker\b"),
    "seeding": (r"ne publie (?:pas|rien)", r"n'expose pas", r"absent[e]? du seed",
                r"le substrat ne publie"),
    "etage": (r"n'est pas port[eé]", r"non port[eé]", r"restent NON PORTES",
              r"fonction native interm[eé]diaire"),
    "porteur": (r"aucun porteur", r"0 porteur", r"pas de porteur", r"non confrontable"),
}


def _blocage_mots_cles(txt: str) -> str:
    """Derivation NAIVE du blocage -- conservee UNIQUEMENT comme temoin de calibration.

    Elle est MESUREE moins bonne que la baseline triviale (55 % contre 59 %) : elle ne doit
    JAMAIS alimenter une ecriture. Elle existe pour que le cliquet puisse le REDIRE.
    """
    for mot in ("capteur", "seeding", "etage", "porteur"):
        for pat in _MOTS_BLOCAGE[mot]:
            if re.search(pat, txt, re.I):
                return mot
    return "aucun"


def mode_feuille(sortie: Path | None, limite: int | None) -> int:
    """Feuille de travail pour la lecture HUMAINE des fiches non annotees."""
    entrees, ouvertes, annotees, verite, depot = _charger()
    idx = _index_symboles(depot)
    par_famille: dict[str, list[B.Entree]] = defaultdict(list)
    for e in annotees:
        f = _famille(e.ident)
        if f:
            par_famille[f].append(e)

    non = [e for e in ouvertes if not e.annotee]
    if limite:
        non = non[:limite]
    lignes = []
    for e in non:
        a = sorted(source_a(e, depot))
        b = sorted(source_b(e, idx))
        d = sorted(source_d(e, verite, par_famille))
        lignes.append("### %s  (ligne %d, modele %s%s)"
                      % (e.ident, e.ligne, e.modele,
                         "" if e.pos_modele is not None else ", SANS POINT D'INSERTION"))
        lignes.append("CORPS: " + " ".join(e.corps.split()))
        if a:
            lignes.append("candA(corps): " + ", ".join(a[:8]))
        if b:
            lignes.append("candB(symbole): " + ", ".join(b[:8]))
        if d:
            lignes.append("candD(soeur): " + ", ".join(d[:8]))
        lignes.append("")
    txt = "\n".join(lignes)
    if sortie:
        sortie.write_text(txt, encoding="utf-8", newline="\n")
        print("[603] feuille ecrite : %s (%d fiches, %d caracteres)"
              % (sortie, len(non), len(txt)))
    else:
        sys.stdout.write(txt)
    return EX_OK


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="#603 -- FOYER/BLOCAGE des residus")
    ap.add_argument("--recenser", action="store_true")
    ap.add_argument("--calibrer", action="store_true")
    ap.add_argument("--feuille", action="store_true")
    ap.add_argument("--index", action="store_true")
    ap.add_argument("--sortie", type=Path, default=None)
    ap.add_argument("--limite", type=int, default=None)
    ap.add_argument("-v", "--verbeux", action="store_true")
    a = ap.parse_args(argv)

    if not (a.recenser or a.calibrer or a.feuille or a.index):
        a.recenser = a.calibrer = True

    rc = EX_OK
    if a.recenser:
        rc = max(rc, mode_recenser())
    if a.calibrer:
        rc = max(rc, mode_calibrer(a.verbeux))
    if a.feuille:
        rc = max(rc, mode_feuille(a.sortie, a.limite))
    if a.index:
        from index_foyers import ecrire_index
        rc = max(rc, ecrire_index(BACKLOG, INDEX))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
