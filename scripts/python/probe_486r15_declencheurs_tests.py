#!/usr/bin/env python
"""#486-r15 -- CLIQUET : chaque FICHIER de test DECLARE son declencheur, et le DECLARE JUSTE.

CE QUE CE CLIQUET EST SEUL A VOIR
----------------------------------
Un fichier de test qui (a) ne dit PAS ce qui doit changer pour qu'il puisse changer de verdict,
ou (b) le dit TROP ETROIT -- il LIT ou IMPORTE quelque chose que son `DECLENCHEUR` ne couvre pas.
La seconde faute est la dangereuse : elle ne produit ni erreur ni rouge, elle produit un test
QU'ON NE JOUE PAS quand son gisement vient de se rouvrir. C'est la signature de
`TARGETING_OPTIONS` -- permissive, silencieuse, alimentee par notre propre cadence de portage.

C'est le pendant EXACT de `probe_486r12_declencheurs.py`, qui pose la meme obligation aux
CLIQUETS de la banque. Le contrat (`declencheur_cliquet.py`) est PARTAGE et non duplique : meme
nom, memes quatre cles, meme semantique de glob, meme defaut `toujours: True`.

POURQUOI PAS UN HERITAGE (`class TestOffline` avec `should_trigger = False`)
-----------------------------------------------------------------------------
Deux raisons, l'une MESUREE et l'autre semantique -- et la seconde suffirait :

  * mesure du 2026-08-07 sur le corpus reel : **711 fichiers de test, 5 080 tests, 100 % en
    FONCTIONS de module, ZERO methode de classe**. L'heritage exigerait de convertir 5 080 tests
    dans 711 fichiers, sur precisement le code qui garde tout le reste ;
  * en Python, heriter NE FORCE AUCUNE SURCHARGE. Une sous-classe distraite heriterait
    SILENCIEUSEMENT de `False` et ne serait plus jouee -- sans un mot. C'est litteralement le
    gisement #455 (`test_summon_trait_effects_live.py` : 8 skipped / 0 passed / rc 0 sur
    `master`, zero assertion evaluee, trouve en ECARTANT une PR).

L'obligation est donc portee par un CLIQUET, pas par un type : un fichier distrait ne devient pas
invisible, il CASSE, et son auteur tranche.

LA GRANULARITE EST LE FICHIER, ET C'EST MESURE
-----------------------------------------------
Sur `test_477r24r1_slots_interface_offline.py` (2026-08-07) : UN test coute 15,0 s, le fichier
ENTIER (59 tests) 49,7 s -- les 58 autres pesent 34,7 s A EUX TOUS, ~0,6 s piece. Le cout FIXE
(les fixtures) est ~15 s et se paie quel que soit le nombre de tests joues ; le depot porte
485 fixtures `scope="module"` et 58 `scope="session"`. Selectionner 1 test sur 59 economiserait
30 % au mieux, pour 5 080 declarations au lieu de 711.
⚠ ET SURTOUT : une selection INTRA-FICHIER casserait `probe_455`. Un fichier dont tous les tests
sont deselectionnes n'emet AUCUN report (volet #455-r3, structurellement invisible), et un bilan
`passed == 0 and skipped > 0` fait ROUGIR la passe (volet #455). On detruirait le garde-fou
contre les tests fantomes pour economiser 0,6 s.

LES DEUX ETAGES
---------------
  [1] OBLIGATION -- perimetre DERIVE de `git ls-files scripts/python/tests` (jamais une allowlist :
      un fichier de test NEUF y entre TOUT SEUL, c'est la lecon de #457-r5 et #455-r3). Tout
      fichier sans `DECLENCHEUR` bien forme est une DETTE. La dette est un CLIQUET : elle est
      versionnee dans `scripts/ratchets-486r15-dette-declencheurs.txt` et ne peut que DECROITRE.
      Un fichier NEUF sans declaration est ROUGE immediatement ; un fichier qui sort de la dette
      ne peut plus y rentrer.
  [2] CONFRONTATION -- pour chaque fichier DECLARE, la declaration est confrontee a la MESURE :
      les fichiers qu'il OUVRE reellement (temoins de l'empreinte `probe_457`) et les modules
      que sa fermeture d'imports charge. Croire la declaration sur parole reviendrait a demander
      au declarant de s'auto-attester.

POURQUOI UNE DETTE PLUTOT QU'UN ROUGE IMMEDIAT SUR LES 711
-----------------------------------------------------------
Poser l'obligation seche rendrait `master` ROUGE sur 711 fichiers le jour de sa livraison, donc
la ferait desarmer dans l'heure. Le cliquet de dette tient l'INTENTION -- << nul test NEUF sans
declaration >> -- et rend la convergence MONOTONE et visible. `--sans-dette` joue le critere sec,
pour mesurer ce qui reste. Le cliquet ne PEUT PAS se degrader en silence : la dette est un
FICHIER VERSIONNE, donc toute reouverture apparait dans un diff.

TRI-ETAT (#471)
---------------
  0  : tout ce qui etait mesurable a ete mesure, rien ne rougit ;
  1  : au moins un fichier de test ne declare pas (hors dette), declare mal, ou LIT hors de son
       perimetre declare ;
  99 : rien n'a pu etre mesure (git muet, empreinte illisible) -- ni un vert ni un rouge.

Usage :
    python probe_486r15_declencheurs_tests.py
    python probe_486r15_declencheurs_tests.py --sans-dette     # le critere SEC
    python probe_486r15_declencheurs_tests.py --ecrire-dette   # (re)pose la ligne de base
    python probe_486r15_declencheurs_tests.py --verbose

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import declencheur_cliquet as DC                                        # noqa: E402
import repo_read                                                        # noqa: E402

ROOT = PYDIR.parents[1]
DETTE = ROOT / "scripts" / "ratchets-486r15-dette-declencheurs.txt"
EMPREINTE = ROOT / "scripts" / "ratchets-457-footprints.json"

EX_NON_MESURE = 99

#: Ce qui doit changer pour que ce cliquet puisse changer d'avis (#486-r15).
#: Il est SOUMIS A SON PROPRE CRITERE -- exiger des autres une declaration sans en porter une
#: serait indefendable, meme principe que `probe_486r12` dans la banque qu'il garde.
DECLENCHEUR = {
    "chemins": ("scripts/python/tests/**/*.py", "scripts/python/**/*.py",
                "scripts/ratchets-486r15-dette-declencheurs.txt",
                "scripts/ratchets-457-footprints.json"),
    "build": False,
    "toujours": False,
    "raison": "Quatre entrees, toutes dans l'arbre. Les FICHIERS DE TEST (son perimetre en est "
              "DERIVE, et il y lit le DECLENCHEUR par AST), tout `scripts/python/**` (il resout "
              "la fermeture d'imports de chaque fichier declare), la DETTE versionnee et "
              "l'EMPREINTE de probe_457 qu'il confronte. Aucune dependance au build ni au jeu : "
              "tout ce qu'il juge est du texte du depot.",
}


class MontageImpossible(RuntimeError):
    """Le cliquet n'a pas pu CONSTITUER l'objet de sa mesure. Rend `EX_NON_MESURE`, jamais 1.

    Meme critere etroit que `probe_457.MontageImpossible` : une panne de ce dont le cliquet
    DEPEND et qui n'est PAS le depot (git non lancable, systeme de fichiers). Un `git ls-files`
    a rc=0 et liste VIDE reste un ROUGE -- c'est une reponse valide de l'outil, donc un fait sur
    le depot (perimetre effondre).
    """


def _git(args: list) -> str:
    try:
        p = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
    except OSError as exc:
        raise MontageImpossible("`git %s` n'a pas pu etre lance (%s)"
                                % (" ".join(args), type(exc).__name__)) from exc
    if p.returncode != 0:
        raise MontageImpossible("`git %s` a rendu rc=%d : %s"
                                % (" ".join(args), p.returncode, (p.stderr or "").strip()[:200]))
    return p.stdout


def est_fichier_de_test(nom: str) -> bool:
    """La convention de collecte de pytest, laissee au DEFAUT par `pytest.ini`.

    Les DEUX formes comptent (`test_*.py` et `*_test.py`). Un perimetre DERIVE doit couvrir ce
    que pytest COLLECTE, pas ce qui se trouve exister -- sinon le prochain fichier ainsi nomme
    rouvre le trou qu'on vient de fermer (#457-r5)."""
    return nom.endswith(".py") and (nom.startswith("test_") or nom.endswith("_test.py"))


def fichiers_de_test() -> list:
    """TOUS les fichiers de test versionnes, live compris. DERIVE de `git ls-files`.

    Live compris a dessein : l'obligation porte sur la DECLARATION, pas sur la selection. Un test
    live n'est pas selectionne par `probe_457` (qui ne voit que l'offline), mais son auteur doit
    savoir dire ce dont son verdict depend -- et c'est la moitie du corpus."""
    out = []
    for ligne in _git(["ls-files", "scripts/python/tests"]).splitlines():
        rel = ligne.strip()
        if rel and est_fichier_de_test(rel.rsplit("/", 1)[-1]):
            out.append(rel)
    return sorted(out)


def lire_dette() -> set:
    """Les fichiers TOLERES sans declaration. Absente -> ensemble VIDE (critere sec)."""
    try:
        lignes = DETTE.read_text(encoding="utf-8").splitlines()
    except OSError:
        return set()
    return {l.strip() for l in lignes if l.strip() and not l.startswith("#")}


def ecrire_dette(manquants) -> None:
    entete = [
        "# #486-r15 -- DETTE de declaration `DECLENCHEUR` sur les fichiers de test.",
        "# ARTEFACT GENERE ET VERSIONNE : ne pas fusionner a la main, REGENERER",
        "# (`python scripts/python/probe_486r15_declencheurs_tests.py --ecrire-dette`).",
        "#",
        "# CE FICHIER NE PEUT QUE RETRECIR. Un fichier de test NEUF n'y est pas, donc son",
        "# absence de declaration est ROUGE tout de suite ; un fichier qui en sort ne peut",
        "# plus y rentrer. C'est ce qui rend la convergence monotone et VISIBLE (tout",
        "# elargissement apparait dans un diff).",
        "#",
        "# %d fichier(s)." % len(manquants),
    ]
    DETTE.write_text("\n".join(entete + sorted(manquants)) + "\n", encoding="utf-8")


def declarations(fichiers) -> tuple:
    """`({rel: declencheur}, {rel: faute})`. Lecture PARALLELE + pre-filtre par SOUS-CHAINE.

    Aucun fichier n'est IMPORTE : `declencheur_cliquet.lire` passe par `ast.literal_eval`, donc
    un fichier de test dont l'import PLANTE peut quand meme declarer -- et c'est exactement
    l'etat ou l'on veut le savoir.
    """
    textes = repo_read.read_texts([str(ROOT / f) for f in fichiers], errors="replace")
    ok: dict = {}
    ko: dict = {}
    for rel, texte in zip(fichiers, textes):
        if texte is None:
            ko[rel] = "fichier illisible"
            continue
        if DC.NOM not in texte:
            ko[rel] = "aucun `%s` au niveau module" % DC.NOM
            continue
        try:
            d = DC.lire(ROOT / rel)
        except (DC.DeclencheurAbsent, OSError, SyntaxError) as exc:
            ko[rel] = str(exc)
            continue
        fautes = DC.valider(d)
        if fautes:
            ko[rel] = "declaration MAL FORMEE : %s" % "; ".join(fautes)
            continue
        ok[rel] = d
    return ok, ko


# ============================================================== fermeture d'imports CIBLEE
class Fermeture:
    """La fermeture TOUS IMPORTS d'un fichier, resolue PAR LE DISQUE, sans indexer l'arbre.

    POURQUOI PAS `import_closure.Cloture` (#486-r11) : il repond a une AUTRE question -- << que
    charge `import M` ? >> -- et EXCLUT donc les imports differes (corps de fonction,
    `TYPE_CHECKING`), a raison pour son critere. Ici, un `import` ecrit dans un corps de test
    S'EXECUTE bel et bien pendant le test : l'exclure SOUS-approximerait la fermeture, et une
    sous-approximation dans un garde de couverture est un FAUX VERT. Les deux fermetures sont
    donc distinctes par leur CRITERE, pas par negligence.

    POURQUOI PAS `probe_457._graphe` : il lit et parse les 2 096 modules du domaine (32,7 s
    mesurees). Ici on ne visite que ce que les fichiers DECLARES atteignent -- mediane 95 modules.
    """

    def __init__(self, racine: Path) -> None:
        self.racine = Path(racine)
        self._resolus: dict = {}
        self._cibles: dict = {}

    def resoudre(self, nom: str):
        """Le chemin relatif au depot du module `nom` sous `scripts/python`, ou `None`."""
        if nom in self._resolus:
            return self._resolus[nom]
        base = self.racine / "scripts" / "python"
        for suffixe in ("%s.py" % nom.replace(".", "/"),
                        "%s/__init__.py" % nom.replace(".", "/")):
            cand = base / suffixe
            if cand.is_file():
                self._resolus[nom] = "scripts/python/" + suffixe
                return self._resolus[nom]
        self._resolus[nom] = None
        return None

    def cibles(self, rel: str) -> set:
        """Les modules importes DIRECTEMENT par `rel` (tous imports, y compris differes)."""
        if rel in self._cibles:
            return self._cibles[rel]
        out: set = set()
        try:
            arbre = ast.parse((self.racine / rel).read_bytes())
        except (OSError, SyntaxError, ValueError):
            self._cibles[rel] = out
            return out
        noms: set = set()
        for n in ast.walk(arbre):
            if isinstance(n, ast.Import):
                noms.update(a.name for a in n.names)
            elif isinstance(n, ast.ImportFrom) and n.module:
                noms.add(n.module)
                noms.update(n.module + "." + a.name for a in n.names)
        for nom in noms:
            morceaux = nom.split(".")
            for i in range(len(morceaux), 0, -1):
                cible = self.resoudre(".".join(morceaux[:i]))
                if cible:
                    out.add(cible)
                    break
        self._cibles[rel] = out
        return out

    def conftests(self, rel: str) -> set:
        """Les `conftest.py` qui s'appliquent a `rel`, de la racine du rootdir a son repertoire.

        AUCUN test n'IMPORTE son conftest : c'est de la semantique PYTEST, invisible a l'AST.
        L'oublier ferait passer pour << non couvert >> ce qui l'est, mais surtout laisserait une
        declaration ignorer les fixtures `autouse` et le `green_skip_guard` de #455 -- dont le
        verdict de CHAQUE test depend. Meme arete que `probe_457._conftest_edges`, dans l'autre
        sens."""
        out: set = set()
        morceaux = rel.split("/")[:-1]
        for i in range(len(morceaux), 1, -1):
            cand = "/".join(morceaux[:i]) + "/conftest.py"
            if (self.racine / cand).is_file():
                out.add(cand)
        return out

    def de(self, rel: str) -> set:
        vus: set = set()
        pile = [rel] + sorted(self.conftests(rel))
        while pile:
            x = pile.pop()
            if x in vus:
                continue
            vus.add(x)
            pile.extend(self.cibles(x) - vus)
        vus.discard(rel)
        return vus


def temoins_mesures(rel: str) -> tuple:
    """`(temoins, mesure)` de l'empreinte `probe_457` pour ce fichier. `mesure=False` si absent.

    TRI-ETAT : une entree absente n'est PAS << il n'ouvre rien >>, c'est << pas mesure >>. La
    confrontation ne peut alors rien conclure, et le DIT -- elle ne valide pas par defaut.
    """
    try:
        emp = json.loads(EMPREINTE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return (), False
    entree = (emp.get("par_test") or {}).get(rel.split("scripts/python/", 1)[-1])
    if not isinstance(entree, dict):
        return (), False
    return tuple(entree.get("temoins") or ()), True


def confronter(decl: dict, verbeux: bool = False) -> tuple:
    """`(rouges, non_mesures)` -- ce que chaque declaration ne couvre PAS.

    DEUX SOURCES, et elles ne voient pas la meme chose :
      * la FERMETURE D'IMPORTS -- ce que le fichier CHARGE. Exacte, calculee ici ;
      * les TEMOINS de l'empreinte -- ce que le fichier a reellement OUVERT pendant ses tests.
        Elle seule voit un `read_text("data/...")` qu'aucun import ne revele.
    """
    ferm = Fermeture(ROOT)
    rouges: list = []
    non_mesures: list = []
    for rel in sorted(decl):
        globs = DC.perimetre(decl[rel], rel)
        decouverts = sorted(m for m in ferm.de(rel) if not DC.couvre(globs, m))
        tem, mesure = temoins_mesures(rel)
        if not mesure:
            non_mesures.append(rel)
        decouverts += sorted(t for t in tem if not DC.couvre(globs, t))
        if decouverts:
            rouges.append((rel, decouverts))
        elif verbeux:
            print("    OK  %s  (%d module(s) de fermeture, %d temoin(s))"
                  % (rel, len(ferm.de(rel)), len(tem)))
    return rouges, non_mesures


def _run(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sans-dette", action="store_true", dest="sans_dette",
                    help="Joue le critere SEC : toute absence de declaration est ROUGE.")
    ap.add_argument("--ecrire-dette", action="store_true", dest="ecrire",
                    help="(Re)pose la ligne de base. Elle ne doit JAMAIS s'elargir.")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args(argv)

    fichiers = fichiers_de_test()
    if not fichiers:
        # Reponse VALIDE de git avec une liste vide = fait sur le depot (perimetre effondre),
        # pas une panne d'outil. C'est un ROUGE, la frontiere a ne pas laisser glisser.
        print("[486r15] FAIL -- le perimetre ne designe AUCUN fichier de test")
        return 1

    ok, ko = declarations(fichiers)
    dette = set() if args.sans_dette else lire_dette()

    if args.ecrire:
        ecrire_dette(sorted(ko))
        print("[486r15] dette (re)ecrite : %d fichier(s) sans declaration sur %d -> %s"
              % (len(ko), len(fichiers), DETTE))
        return 0

    # -- ETAGE 1 : OBLIGATION
    hors_dette = sorted(r for r in ko if r not in dette)
    elargie = sorted(r for r in dette if r not in ko and r in fichiers)
    print("[486r15] %d fichier(s) de test ; %d DECLARE(S), %d sans declaration (dont %d tolere(s) "
          "par la dette)" % (len(fichiers), len(ok), len(ko), len(ko) - len(hors_dette)))
    if elargie:
        print("[486r15] %d entree(s) de dette PERIMEE(S) (le fichier declare, ou a disparu) -- "
              "regenerer la dette : %s" % (len(elargie), ", ".join(elargie[:4])))

    # -- ETAGE 2 : CONFRONTATION
    rouges, non_mesures = confronter(ok, args.verbose)
    if non_mesures:
        print("[486r15] %d declaration(s) NON CONFRONTEE(S) a l'empreinte (aucune entree mesuree) "
              ": la fermeture d'imports seule a ete verifiee -- %s"
              % (len(non_mesures), ", ".join(x.rsplit("/", 1)[-1] for x in non_mesures[:4])))

    mauvais = 0
    for rel in hors_dette:
        print("[486r15] ROUGE -- %s : %s" % (rel, ko[rel]))
        mauvais += 1
    for rel, decouverts in rouges:
        print("[486r15] ROUGE -- %s DECLARE TROP ETROIT : %d chemin(s) lu(s)/importe(s) hors du "
              "perimetre declare" % (rel, len(decouverts)))
        for d in decouverts[:8]:
            print("             %s" % d)
        mauvais += 1

    if mauvais:
        print("[486r15] VERDICT: FAIL -- %d fichier(s) en faute" % mauvais)
        return 1
    print("[486r15] VERDICT: PASS -- %d declaration(s) confrontee(s), dette de %d fichier(s)"
          % (len(ok), len(ko)))
    return 0


def main(argv=None) -> int:
    try:
        return _run(argv)
    except MontageImpossible as exc:
        print("[486r15] MONTAGE EN ECHEC : %s" % exc)
        print("[486r15] RIEN n'a ete mesure. Ce n'est PAS un verdict sur le depot.")
        print("[486r15] rc=%d" % EX_NON_MESURE)
        return EX_NON_MESURE


if __name__ == "__main__":
    sys.exit(main())
