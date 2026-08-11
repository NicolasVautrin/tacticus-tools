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

LES TROIS ETAGES
----------------
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
  [3] BYPASS (#486-r24) -- un fichier peut declarer `hors_confrontation: "<raison>"` et sortir
      de l'etage 2. Il est alors COMPTE, son motif est IMPRIME, il doit etre ATTESTE dans
      `scripts/ratchets-486r24-bypass-confrontation.txt`, et son bypass doit SERVIR : un bypass
      qui ne masque aucun decouvert est une declaration MORTE, donc un rouge.

L'ORDRE : `probe_457 --measure-missing` D'ABORD, CE CLIQUET ENSUITE (#486-r29)
------------------------------------------------------------------------------
CE CLIQUET N'A PAS LE MEME NOMBRE DE SOURCES AVANT ET APRES `--measure-missing`, et l'ordre
prescrit jusqu'au 2026-08-08 etait l'INVERSE de celui qu'il faut. Sans entree d'empreinte, la
seconde source est VIDE : l'etage 2 verifie la fermeture d'imports SEULE, qui est strictement
plus etroite. L'auteur jouait donc le cliquet dans le regime a UNE source, gravait l'empreinte
juste apres, et livrait ; la confrontation passait a DEUX sources AU MERGE.

MESURE DU 2026-08-08. La PR #832 etait VERTE chez son auteur (`probe_486r15 PASS` rapporte) et
ROUGE sur `master` au commit de merge `18edd540` : **8 chemins** manquants, **tous** apportes par
les temoins (6 `__init__.py` de cascade + `caches/ability_and_effect_cache.py` +
`streams/verify_turn_finished.py`), **0** par la fermeture -- et l'entree d'empreinte fautive
arrivait DANS LA MEME PR. Ce n'est donc pas une negligence d'auteur : aucun rappel de discipline
ne le ferme, c'est l'ORDRE qui etait faux.

AMPLEUR DU REGIME A UNE SOURCE, mesuree le 2026-08-08 sur le parc : **28 des 74** declarations
(38 %) n'ont AUCUNE entree d'empreinte, donc leur vert ne vaut que pour une source ; et sur les
46 qui en ont une, les temoins apportent **206** chemins que la fermeture d'imports NE VOIT PAS.

D'ou deux crans, ici et dans la prescription :
  * le VERDICT SE QUALIFIE -- `PASS SOUS RESERVE` quand au moins une declaration est jugee a une
    seule source, avec le compte, la LISTE et l'ordre a jouer. Le rc reste 0 (ce n'est pas une
    faute), mais le texte ne se lit plus comme un vert plein. Auparavant ces fichiers etaient
    comptes parmi les << confrontee(s) >>, ce qui etait faux ;
  * `--proposer` etait DEJA correct sur ce point (il DIT qu'il ne voit que les imports quand
    l'empreinte manque) -- c'est la checklist qui ne l'etait pas.

L'ASYMETRIE QUE L'ETAGE 3 CORRIGE, ET POURQUOI ELLE ETAIT LA VRAIE FAUTE (#486-r24)
------------------------------------------------------------------------------------
Ce cliquet rougissait sur le TROP ETROIT et benissait le TROP LARGE. L'auteur rationnel ecrivait
donc un glob couvrant tout le Python : vert pour toujours, et jamais rejoue par personne. Mesure
du 2026-08-07 sur `origin/master` : sur **63** fichiers declarants, **62 portent au moins un glob
INDISCRIMINANT** (il couvre un fichier de test ou un probe TIERS -- or aucun test ne depend d'un
autre consommateur du socle qu'il n'importe pas), et **0** declarait honnetement `toujours: True`.

Autrement dit : LE BYPASS EXISTAIT DEJA. Il se posait en mentant sur le perimetre, ce qui a un
prix que la cle explicite n'a pas -- il empoisonne la SELECTION (`probe_457` sert les globs
declares : un glob universel fait rejouer le fichier a chaque PR Python, dont 25 tests LIVE), il
n'est pas COMPTABLE, et il ne dit pas POURQUOI. L'etage 3 echange une evasion silencieuse contre
une declaration comptee.

CE QUE LA MESURE DIT DE LA POPULATION, ET POURQUOI LE BYPASS N'EST PAS LA REPONSE POUR TOUS
---------------------------------------------------------------------------------------------
Ventilation des 62, mesuree en retirant les globs indiscriminants puis en derivant la cascade de
harnais (`declencheur_cliquet.chemins_du_harnais`, ajout 3 du foyer) :

  * **19 CASCADE** -- decouverts ramenes a ZERO par le seul harnais derive. Ils n'ont JAMAIS eu
    besoin d'un bypass : ils payaient les 16 modules racine que la cascade des `conftest.py` leur
    imputait (#531). C'est le foyer qui les porte desormais ;
  *  **1 DECORATIF** -- le glob universel ne couvrait rien que la declaration fine ne couvrait ;
  * **38 A RESSERRER** -- 1 a 12 decouverts, tous NOMMABLES, et le plus souvent UN SEUL : le
    probe frere du test (`probe_<n>_<sujet>.py`). Une ligne, pas un bypass ;
  *  **4 BALAYAGE** -- 40 a 67 decouverts structurels : ces tests LISENT l'arbre. Aucune
    enumeration ne les bornera. Ce sont les seuls candidats legitimes au bypass.

Soit **4 sur 63**. C'est pourquoi l'etage 3 refuse un bypass qui ne masque rien : sans ce cran,
les 19 CASCADE et le DECORATIF auraient pose la cle par imitation, et l'echappatoire aurait
simplement change de nom.

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
    python probe_486r15_declencheurs_tests.py --ecrire-bypass  # (re)pose la population du bypass
    python probe_486r15_declencheurs_tests.py --proposer <fichier_de_test>   # AIDE A L'ECRITURE
    python probe_486r15_declencheurs_tests.py --verbose

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import argparse
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
BYPASS = ROOT / "scripts" / "ratchets-486r24-bypass-confrontation.txt"
EMPREINTE = ROOT / "scripts" / "ratchets-457-footprints.json"

EX_NON_MESURE = 99

#: Ce qui doit changer pour que ce cliquet puisse changer d'avis (#486-r15).
#: Il est SOUMIS A SON PROPRE CRITERE -- exiger des autres une declaration sans en porter une
#: serait indefendable, meme principe que `probe_486r12` dans la banque qu'il garde.
DECLENCHEUR = {
    "chemins": ("scripts/python/tests/**/*.py", "scripts/python/**/*.py",
                "scripts/ratchets-486r15-dette-declencheurs.txt",
                "scripts/ratchets-486r24-bypass-confrontation.txt",
                "scripts/ratchets-457-footprints.json"),
    "build": False,
    "toujours": False,
    "raison": "Cinq entrees, toutes dans l'arbre. Les FICHIERS DE TEST (son perimetre en est "
              "DERIVE, et il y lit le DECLENCHEUR par AST), tout `scripts/python/**` (il resout "
              "la fermeture d'imports de chaque fichier declare), la DETTE versionnee, la "
              "population ATTESTEE du bypass, et l'EMPREINTE de probe_457 qu'il confronte. "
              "Aucune dependance au build ni au jeu : tout ce qu'il juge est du texte du depot.",
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


def declarations(fichiers, lues: dict | None = None) -> tuple:
    """`({rel: declencheur}, {rel: faute})`. Lecture PARALLELE + pre-filtre par SOUS-CHAINE.

    Aucun fichier n'est IMPORTE : `declencheur_cliquet.lire` passe par `ast.literal_eval`, donc
    un fichier de test dont l'import PLANTE peut quand meme declarer -- et c'est exactement
    l'etat ou l'on veut le savoir.

    `lues`, si fourni, recoit `rel -> declaration` pour TOUTE declaration effectivement LUE,
    y compris MAL FORMEE (#486-r30). Sans elle, une declaration mal formee sortait en `ko`
    et n'etait plus jamais regardee : sa faute de PERIMETRE restait CACHEE derriere sa faute de
    FORME, et il fallait deux tranches pour trouver les deux. Un parametre de SORTIE plutot
    qu'un 3e element de tuple, pour ne pas casser les appelants qui depaquettent une paire.
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
        if lues is not None and isinstance(d, dict):
            lues[rel] = d
        # `perimetre_derive=True` : le perimetre d'un TEST porte la cascade de harnais et le
        # fichier lui-meme, donc `chemins: ()` y est borne, pas vide (#486-r31).
        fautes = DC.valider(d, perimetre_derive=True)
        if fautes:
            ko[rel] = "declaration MAL FORMEE : %s" % "; ".join(fautes)
            continue
        ok[rel] = d
    return ok, ko


# ============================================================== fermeture d'imports CIBLEE
#: La fermeture vit dans le FOYER depuis #531 : le PERIMETRE EFFECTIF en depend desormais (le
#: foyer y derive la cascade de harnais), et le perimetre est servi aussi bien a ce cliquet qu'a
#: la SELECTION de `probe_457`. En garder une seconde copie ici rouvrirait l'ecart silencieux
#: que #463-r1 a ferme sur le recensement offline : le garde jugerait un autre perimetre que
#: celui que la selection joue.
Fermeture = DC.Fermeture


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


def confronter(decl: dict, verbeux: bool = False, ferm=None) -> tuple:
    """`(rouges, non_mesures, bypass)` -- ce que chaque declaration ne couvre PAS.

    DEUX SOURCES, et elles ne voient pas la meme chose :
      * la FERMETURE D'IMPORTS -- ce que le fichier CHARGE. Exacte, calculee ici ;
      * les TEMOINS de l'empreinte -- ce que le fichier a reellement OUVERT pendant ses tests.
        Elle seule voit un `read_text("data/...")` qu'aucun import ne revele.

    LE BYPASS EST MESURE, PAS CRU SUR PAROLE (#486-r24). Un fichier qui declare
    `hors_confrontation` n'est pas ROUGE sur ses decouverts -- mais on les COMPTE quand meme,
    parce que ce compte est la seule chose qui rende la relecture d'un bypass decidable : un
    bypass qui masque UN chemin nommable (typiquement le probe frere du test) n'est pas de la
    meme nature qu'un bypass qui en masque soixante (un balayage d'arbre). Et un bypass qui
    n'en masque AUCUN est une declaration MORTE, donc un rouge : c'est le seul cran qui empeche
    la cle de devenir l'echappatoire universelle qu'elle remplace.

    `ferm` -- INJECTION, jamais un cache (#941-r2). Par defaut la fermeture est NEUVE, donc rien
    ne change pour le CLI ni pour aucun appelant existant. Un appelant qui confronte plusieurs
    fois dans le MEME process peut en revanche fournir la sienne et ne payer la resolution
    qu'une fois : `test_486r24_bypass_confrontation_offline.py` appelait `confronter` TROIS fois
    (deux mutations sur le meme fichier, puis la population reelle) et re-resolvait a chaque
    fois la fermeture de ce fichier -- 19,1 s + 8,4 s + 42,1 s mesures le 2026-08-11. Un cache
    GLOBAL aurait ete le mauvais outil : il servirait un releve perime a un appelant qui vient
    d'ecrire dans l'arbre, et c'est precisement ce que ce fichier de test fait (`_monte_arbre`).
    Ici, c'est l'appelant qui decide de la fraicheur, parce que lui seul la connait.
    """
    ferm = ferm if ferm is not None else Fermeture(ROOT)
    rouges: list = []
    non_mesures: list = []
    bypass: list = []
    for rel in sorted(decl):
        globs = DC.perimetre(decl[rel], rel)
        decouverts = sorted(m for m in ferm.de(rel) if not DC.couvre(globs, m))
        tem, mesure = temoins_mesures(rel)
        if not mesure:
            non_mesures.append(rel)
        decouverts += sorted(t for t in tem if not DC.couvre(globs, t))
        motif = DC.hors_confrontation(decl[rel])
        if motif is not None:
            bypass.append((rel, motif, decouverts))
            continue
        if decouverts:
            rouges.append((rel, decouverts))
        elif verbeux:
            print("    OK  %s  (%d module(s) de fermeture, %d temoin(s))"
                  % (rel, len(ferm.de(rel)), len(tem)))
    return rouges, non_mesures, bypass


# ============================================================== l'AIDE A L'ECRITURE (#486-r28)
def proposer(rel: str) -> int:
    """Imprime la declaration que ce cliquet EXIGERAIT pour `rel`. Foyer unique du calcul.

    POURQUOI CE MODE EXISTE. Jusqu'ici l'outillage ne savait que JUGER : `--sans-dette`,
    `--ecrire-dette`, `--ecrire-bypass`. Un auteur devait donc deriver A LA MAIN sa fermeture
    d'imports, en soustraire la cascade que le foyer ajoute, et deviner -- alors que la machine
    qui calcule la reponse est exactement celle qui le juge ensuite. Mesure du 2026-08-07 :
    CINQ declarations ont rendu `master` ROUGE en une journee, dont deux MAL FORMEES et trois
    trop etroites sur un foyer partage arrive sous elles. Aucune n'etait une negligence : le
    seul gate qu'un auteur interroge (le hook pytest) ne valide que la PRESENCE (#486-r27).

    ⚠ LE CALCUL N'EST PAS REFAIT ICI, ET C'EST LE POINT. La proposition se derive en soustrayant
    `DC.perimetre` d'une declaration VIDE -- donc la cascade de harnais, les ajouts du foyer, et
    rien d'autre. Une seconde derivation << equivalente >> rouvrirait l'ecart silencieux que
    #531 a ferme : l'aide proposerait alors un perimetre que le juge n'accepte pas.

    ⚠ ET ELLE N'EMET JAMAIS DE GLOB DE RACINE. `scripts/python/*.py` rend la confrontation
    toujours satisfaite tout en MENTANT au selecteur (mesure `case-486-r24` §3bis : il fait
    passer l'axe des probes de 20 a 995 chemins retenus). Une aide qui le proposerait
    industrialiserait le defaut qu'elle est censee prevenir.
    """
    rel = _rel_depuis(rel)
    if rel is None:
        return 2
    if not (ROOT / rel).is_file():
        print("[486r15] introuvable : %s" % rel)
        return 2

    vide = {"chemins": (), "build": False, "toujours": False, "raison": ""}
    deja = DC.perimetre(vide, rel, ROOT)          # la cascade + ce que le foyer ajoute
    ferm = Fermeture(ROOT)
    closure = sorted(ferm.de(rel))
    tem, mesure = temoins_mesures(rel)

    manquants = sorted(set(c for c in closure if not DC.couvre(deja, c))
                       | set(t for t in tem if not DC.couvre(deja, t)))

    print("[486r15] PROPOSITION pour %s" % rel)
    print("   fermeture d'imports          : %d module(s)" % len(closure))
    print("   cascade DERIVEE par le foyer : %d chemin(s) -- NE PAS les declarer (#531)"
          % len(deja))
    if mesure:
        print("   temoins de l'empreinte 457   : %d" % len(tem))
    else:
        print("   temoins de l'empreinte 457   : NON MESURE -- cette proposition ne voit que les")
        print("                                  IMPORTS. Un `read_text(\"data/...\")` qu'aucun")
        print("                                  import ne revele y echappe. Joue le fichier puis")
        print("                                  `probe_457_offline_tests_green.py --measure-missing`,")
        print("                                  et RE-JOUE ce mode.")
    print()

    if not manquants:
        print("   RIEN A DECLARER hors de la cascade : la fermeture de ce fichier y tient")
        print("   entierement. Une declaration a `chemins` VIDE serait donc juste -- mais dis")
        print("   quand meme dans `raison` ce que le fichier prouve.")
    else:
        print("   A DECLARER -- %d chemin(s) que la cascade ne couvre PAS :" % len(manquants))

    lit_build = any(m.startswith("data/symbols") for m in manquants + list(tem)) \
        or any("il2cpp" in m or "build_pin" in m for m in manquants)

    print()
    print("DECLENCHEUR = {")
    print("    \"chemins\": (")
    for m in manquants:
        print("        %r," % m)
    print("    ),")
    print("    \"build\": %s,%s" % (lit_build,
                                   "   # DERIVE : ce fichier lit le binaire ou data/symbols/**"
                                   if lit_build else
                                   "  # <- passe a True s'il lit le binaire ou data/symbols/**"))
    print("    \"toujours\": False,")
    print("    \"raison\": \"<A ECRIRE -- pourquoi CES chemins, et pourquoi pas d'autres>\",")
    print("}")
    print()
    print("[486r15] La `raison` n'est PAS decorative : c'est le seul champ qu'aucune machine ne")
    print("[486r15] peut deriver, donc le seul par lequel un relecteur voit qu'une declaration")
    print("[486r15] juste a ete ecrite pour de MAUVAISES raisons.")
    if manquants:
        sous_engine = sum(1 for m in manquants if m.startswith("scripts/python/engine/"))
        if sous_engine >= 4:
            print("[486r15]")
            print("[486r15] %d de ces chemins sont sous `engine/`. Un GLOB y est acceptable "
                  "-- le critere" % sous_engine)
            print("[486r15] n'est pas << littéral ou joker >>, c'est << ce joker couvre-t-il un "
                  "test ou un")
            print("[486r15] probe TIERS ? >>. `engine/**/*.py` n'en couvre aucun ; "
                  "`scripts/python/*.py`")
            print("[486r15] les couvre tous, et c'est le SEUL qui coute (mesure "
                  "`case-486-r24` 3bis :")
            print("[486r15] il fait passer l'axe des probes de 20 a 995 chemins retenus).")
            print("[486r15] NB : `engine/**/*.py` seul ne couvre PAS `engine/*.py` -- dans ce")
            print("[486r15] matcher, `**/` exige un segment. Les deux formes sont necessaires.")
    return 0


def _rel_depuis(chemin: str):
    """Le chemin relatif au depot, depuis un argument absolu ou relatif. `None` si hors arbre.

    TROIS lectures, dans cet ordre -- et l'ordre compte. On sera appele aussi bien depuis la
    RACINE que depuis `scripts/python/` (c'est de la que se jouent les probes), et un chemin
    deja relatif au DEPOT resolu contre le cwd donnerait `scripts/python/scripts/python/...`
    -- une non-existence qui se lit comme << fichier introuvable >> alors que le fichier est la.
    """
    p = Path(chemin)
    if p.is_absolute():
        try:
            return p.resolve().relative_to(ROOT.resolve()).as_posix()
        except (ValueError, OSError):
            print("[486r15] hors du depot : %s" % chemin)
            return None
    if (ROOT / chemin).is_file():                       # deja relatif au DEPOT
        return Path(chemin).as_posix()
    try:                                                 # relatif au CWD
        return (Path.cwd() / p).resolve().relative_to(ROOT.resolve()).as_posix()
    except (ValueError, OSError):
        print("[486r15] hors du depot : %s" % chemin)
        return None


# ============================================================== la ligne de base des bypass
def lire_bypass_atteste() -> set:
    """Les fichiers DEJA connus pour bypasser. Absente -> ensemble VIDE (critere sec).

    CE N'EST PAS UNE ALLOWLIST DE PERIMETRE (#457-r6) : le perimetre du cliquet reste DERIVE de
    `git ls-files`, et un fichier neuf y entre tout seul. C'est une ATTESTATION, comme la dette
    de declaration -- elle ne dit pas QUI est juge, elle dit ce qui etait deja vrai. Sa fonction
    est de rendre toute CROISSANCE de la population visible dans un diff : poser un bypass
    exige alors deux gestes, dont l'un dans un fichier que personne ne lit par accident."""
    try:
        lignes = BYPASS.read_text(encoding="utf-8").splitlines()
    except OSError:
        return set()
    return {l.strip() for l in lignes if l.strip() and not l.startswith("#")}


def ecrire_bypass(rels) -> None:
    entete = [
        "# #486-r24 -- fichiers de test qui declarent `hors_confrontation` (le BYPASS).",
        "# ARTEFACT GENERE ET VERSIONNE : ne pas fusionner a la main, REGENERER",
        "# (`python scripts/python/probe_486r15_declencheurs_tests.py --ecrire-bypass`).",
        "#",
        "# UN BYPASS DESARME LA CONFRONTATION D'UN FICHIER -- et donc la seule chose qui",
        "# empeche sa declaration de derailler sans bruit. Le contrat en exige la RAISON",
        "# (dans le fichier lui-meme) ; ce fichier-ci en exige la VISIBILITE : un bypass",
        "# non inscrit est ROUGE, donc toute croissance de la population passe par un diff.",
        "#",
        "# CE N'EST PAS UNE DETTE A RESORBER. Un bypass peut etre pleinement legitime -- un",
        "# test qui BALAIE l'arbre depend reellement de tout, et aucune enumeration ne le",
        "# bornera. Ce qui est garde ici, ce n'est pas le zero : c'est qu'on sache toujours",
        "# QUI se derobe, et sur quel motif.",
        "#",
        "# %d fichier(s)." % len(rels),
    ]
    BYPASS.write_text("\n".join(entete + sorted(rels)) + "\n", encoding="utf-8")


def _run(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sans-dette", action="store_true", dest="sans_dette",
                    help="Joue le critere SEC : toute absence de declaration est ROUGE.")
    ap.add_argument("--ecrire-dette", action="store_true", dest="ecrire",
                    help="(Re)pose la ligne de base. Elle ne doit JAMAIS s'elargir.")
    ap.add_argument("--ecrire-bypass", action="store_true", dest="ecrire_bypass",
                    help="(Re)pose la population des `hors_confrontation` attestes.")
    ap.add_argument("--proposer", metavar="FICHIER", default="",
                    help="Imprime la declaration que ce cliquet EXIGERAIT pour ce fichier de "
                         "test. Aide a l'ECRITURE, pas au jugement (#486-r28).")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args(argv)

    # AVANT le balayage : ce mode porte sur UN fichier, il n'a pas besoin du perimetre entier
    # (et il doit repondre meme quand le parc est rouge -- c'est precisement quand on s'en sert).
    if args.proposer:
        return proposer(args.proposer)

    fichiers = fichiers_de_test()
    if not fichiers:
        # Reponse VALIDE de git avec une liste vide = fait sur le depot (perimetre effondre),
        # pas une panne d'outil. C'est un ROUGE, la frontiere a ne pas laisser glisser.
        print("[486r15] FAIL -- le perimetre ne designe AUCUN fichier de test")
        return 1

    lues: dict = {}
    ok, ko = declarations(fichiers, lues)
    dette = set() if args.sans_dette else lire_dette()

    if args.ecrire:
        ecrire_dette(sorted(ko))
        print("[486r15] dette (re)ecrite : %d fichier(s) sans declaration sur %d -> %s"
              % (len(ko), len(fichiers), DETTE))
        return 0

    if args.ecrire_bypass:
        porteurs = sorted(r for r in ok if DC.hors_confrontation(ok[r]) is not None)
        ecrire_bypass(porteurs)
        print("[486r15] bypass (re)ecrit : %d fichier(s) declarent `%s` sur %d -> %s"
              % (len(porteurs), DC.CLE_HORS_CONFRONTATION, len(ok), BYPASS))
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
    rouges, non_mesures, bypass = confronter(ok, args.verbose)
    # ⚠ CE N'EST PAS UNE REMARQUE DE FIN, C'EST UNE RESERVE SUR LE VERDICT (#486-r29). Un
    # fichier sans entree d'empreinte est juge sur UNE source (la fermeture d'imports), qui
    # est STRICTEMENT PLUS ETROITE que l'union. Le PASS qui suit ne vaut donc pas la meme
    # chose pour lui que pour un fichier confronte -- et l'ancienne sortie le comptait
    # pourtant parmi les << confrontee(s) >>.
    reserve = sorted(r for r in non_mesures
                     if DC.hors_confrontation(ok[r]) is None)
    if non_mesures:
        print("[486r15] %d declaration(s) NON CONFRONTEE(S) a l'empreinte (aucune entree mesuree) "
              ": la fermeture d'imports seule a ete verifiee -- %s"
              % (len(non_mesures), ", ".join(x.rsplit("/", 1)[-1] for x in non_mesures[:4])))

    # -- ETAGE 3 : LE BYPASS, COMPTE ET MOTIVE (#486-r24)
    attestes = set() if args.sans_dette else lire_bypass_atteste()
    non_attestes = sorted(rel for rel, _, _ in bypass if rel not in attestes)
    morts = sorted(rel for rel, _, dec in bypass if not dec)
    perimes = sorted(a for a in attestes
                     if a not in {rel for rel, _, _ in bypass} and a in fichiers)
    if bypass:
        print("[486r15] %d declaration(s) HORS CONFRONTATION (bypass declare et motive) sur %d :"
              % (len(bypass), len(ok)))
        for rel, motif, dec in sorted(bypass, key=lambda t: (-len(t[2]), t[0])):
            print("             %-64s masque %3d chemin(s) -- %s"
                  % (rel.rsplit("/", 1)[-1], len(dec), motif[:96]))
    if perimes:
        print("[486r15] %d attestation(s) de bypass PERIMEE(S) (le fichier ne bypasse plus, ou a "
              "disparu) -- regenerer : %s" % (len(perimes), ", ".join(perimes[:4])))

    mauvais = 0
    for rel in hors_dette:
        print("[486r15] ROUGE -- %s : %s" % (rel, ko[rel]))
        # UN ROUGE DOIT DIRE CE QU'IL N'A PAS REGARDE (#486-r30). Une declaration mal formee
        # sortait ici et n'etait plus confrontee : sa faute de PERIMETRE restait CACHEE derriere
        # sa faute de FORME. Mesure du 2026-08-08 sur `test_175e_175r_tile_meta_live.py` :
        # `build`/`toujours` absents masquaient 6 chemins de fermeture non declares, et il a
        # fallu DEUX tranches pour trouver les deux fautes l'une apres l'autre.
        d = lues.get(rel)
        if d is None:
            print("             PERIMETRE NON EXAMINE : la declaration n'a pas pu etre LUE.")
            mauvais += 1
            continue
        try:
            globs = DC.perimetre(d, rel)
            dec = sorted(m for m in Fermeture(ROOT).de(rel) if not DC.couvre(globs, m))
        except Exception as exc:                                          # noqa: BLE001
            print("             PERIMETRE NON EXAMINE : %s" % str(exc)[:90])
            mauvais += 1
            continue
        if DC.hors_confrontation(d) is not None:
            print("             perimetre : HORS CONFRONTATION (bypass declare)")
        elif dec:
            print("             ET SON PERIMETRE EST TROP ETROIT : %d chemin(s) hors perimetre "
                  "-- a corriger DANS LA MEME PASSE, pas a la suivante" % len(dec))
            for x in dec[:6]:
                print("               %s" % x)
        else:
            print("             perimetre : couvert (seule la FORME est en faute)")
        mauvais += 1
    for rel, decouverts in rouges:
        print("[486r15] ROUGE -- %s DECLARE TROP ETROIT : %d chemin(s) lu(s)/importe(s) hors du "
              "perimetre declare" % (rel, len(decouverts)))
        for d in decouverts[:8]:
            print("             %s" % d)
        print("             => soit ELARGIR (nommer ces chemins), soit declarer "
              "`%s: \"<raison>\"` si la fermeture ne peut PAS borner ce fichier."
              % DC.CLE_HORS_CONFRONTATION)
        mauvais += 1
    for rel in morts:
        print("[486r15] ROUGE -- %s declare `%s` mais NE MASQUE RIEN : la confrontation passe "
              "sans lui. Declaration MORTE -- la retirer."
              % (rel, DC.CLE_HORS_CONFRONTATION))
        mauvais += 1
    for rel in non_attestes:
        print("[486r15] ROUGE -- %s bypasse SANS ETRE ATTESTE. Un bypass se pose en DEUX gestes : "
              "la cle dans le fichier, et la ligne dans %s (`--ecrire-bypass`)."
              % (rel, BYPASS.relative_to(ROOT).as_posix()))
        mauvais += 1

    if mauvais:
        print("[486r15] VERDICT: FAIL -- %d fichier(s) en faute" % mauvais)
        return 1

    # ------------------------------------------------------------------ LE VERT SE QUALIFIE
    # UN VERT DOIT DIRE DE QUOI IL EST LE VERT (#486-r29). Le compte des << confrontee(s) >>
    # valait `len(ok) - len(bypass)` : il rangeait parmi les confrontees les declarations
    # SANS entree d'empreinte, qui n'ont ete jugees que sur la fermeture d'imports. Le
    # verdict devient donc TRI-ETAT en TEXTE (le rc reste 0 : ce n'est pas une faute).
    confrontees = len(ok) - len(bypass) - len(reserve)
    if reserve:
        print("[486r15] VERDICT: PASS SOUS RESERVE -- %d declaration(s) dont %d confrontee(s) "
              "aux DEUX sources, %d a UNE SEULE (fermeture d'imports) et %d hors "
              "confrontation ; dette de %d fichier(s)"
              % (len(ok), confrontees, len(reserve), len(bypass), len(ko)))
        print("[486r15] CE VERT NE VAUT QUE POUR UNE SOURCE sur %d fichier(s) : la fermeture "
              "d'imports NE VOIT PAS ce qu'un test OUVRE sans l'importer." % len(reserve))
        for r in reserve[:12]:
            print("             %s" % r)
        if len(reserve) > 12:
            print("             ... et %d autre(s)" % (len(reserve) - 12))
        # L'ORDRE, ecrit la ou il est joue -- pas seulement dans un brief qu'on recopie.
        print("[486r15] ORDRE (#486-r29) : joue `probe_457_offline_tests_green.py "
              "--measure-missing` D'ABORD, PUIS ce cliquet. Grave l'empreinte APRES, et la "
              "confrontation passe de UNE a DEUX sources AU MERGE, pas chez toi -- c'est")
        print("[486r15]   exactement ce qui a rendu `master` rouge au commit 18edd540 : PR "
              "#832 verte chez son auteur, 8 chemins manquants, TOUS apportes par les "
              "temoins, 0 par la fermeture, empreinte arrivee dans la MEME PR.")
        return 0
    print("[486r15] VERDICT: PASS -- %d declaration(s) dont %d confrontee(s) aux DEUX sources "
          "et %d hors confrontation ; dette de %d fichier(s)"
          % (len(ok), confrontees, len(bypass), len(ko)))
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
