#!/usr/bin/env python
"""#956 -- CLIQUET : une passe de tests offline n'ECRIT dans AUCUN fichier VERSIONNE.

LE FAIT QUE CE CLIQUET FERME
-----------------------------
La banque offline (`probe_457_offline_tests_green.py --jobs N`) repartit ses fichiers en SHARDS,
et chaque shard est un processus pytest ou PLUSIEURS fichiers tournent ensemble, en PARALLELE des
autres shards, sur UN SEUL arbre de travail. Si un fichier de test ECRIT dans un fichier
VERSIONNE, deux choses deviennent vraies en meme temps :

  * un autre fichier de test qui LIT ce meme artefact voit un etat qui depend de QUI a tourne
    avant lui -- donc de la COMPOSITION DES SHARDS, c'est-a-dire de `--jobs N` ;
  * la passe laisse l'arbre SALE, et le verdict de la passe SUIVANTE part d'un autre etat.

Un cliquet dont le resultat depend du decoupage n'est pas un cliquet. Et l'axe est INVISIBLE de
tout ce qu'on a : `probe_547` lit le ledger, `probe_486r15` lit les declencheurs, `probe_457
--since` lit le diff. AUCUN ne regarde qui ECRIT.

CE QU'IL NE PRETEND PAS COUVRIR, ET IL FAUT LE LIRE
----------------------------------------------------
  * les ecritures HORS des fichiers versionnes (`logs/`, `__pycache__`, tmp) : deux shards
    peuvent aussi se marcher dessus la (c'est le gisement mesure par #455 sur `scripts/python`).
    Elles sont COMPTEES et RENDUES, mais elles ne font pas rougir -- le critere garde ici est le
    fichier VERSIONNE, celui dont un etat different se propage a tout le monde par `git` ;
  * l'etat EN MEMOIRE partage entre deux fichiers du meme shard (modules importes, caches
    memoises, `monkeypatch` mal defait). Meme axe, autre canal -- il n'est pas mesurable par un
    hook d'audit sur les ecritures. Residu NOMME, cf. `docs/rl/case-956-purete-de-passe.md` ;
  * ce que la passe n'a pas JOUE. Le perimetre par defaut est DERIVE (les fichiers de test qui
    portent au moins un site d'ecriture ou un lancement de processus), et ce filtre est une
    SUR-approximation statique : il ne rate pas d'ecriture, mais il ne prouve rien sur les
    fichiers qu'il ecarte. `--tout` existe, et son prix est dit.

DEUX CANAUX, ET LE SECOND EXISTE PARCE QUE LE PREMIER A UNE FRONTIERE
-----------------------------------------------------------------------
  1. HOOK D'AUDIT (`sys.addaudithook`) -- il voit `open` avec son MODE, plus les evenements
     `os.*` / `shutil.*` qui modifient le disque. Il attribue au FICHIER DE TEST courant, et il
     voit meme une ecriture TRANSITOIRE (ecrire puis restaurer) -- ce qui est le bon critere :
     un shard voisin peut lire PENDANT. Sa frontiere : il ne franchit PAS la frontiere de
     PROCESSUS. Un test qui lance `probe_457 --measure` en sous-processus n'ouvre rien lui-meme.
  2. `git status --porcelain` AUX BORNES DE FICHIER -- il voit le RESULTAT NET, quel que soit le
     processus qui l'a produit. Sa frontiere : il ne voit pas une ecriture restauree avant la
     borne. Les deux canaux sont donc COMPLEMENTAIRES, aucun ne subsume l'autre, et le probe
     RAPPORTE lequel a mordu.

⚠ L'INSTRUMENT NE SE MESURE PAS LUI-MEME. Meme cran que `probe_457._FilesPerTest` (#547-r5) : le
seau GLOBAL se ferme a `pytest_sessionfinish`, et les appels a `git` que ce probe fait lui-meme
sont marques (sinon chaque borne de fichier ferait croire que le test courant a lance un
processus fils).

TRI-ETAT (#471)
---------------
  0  : aucun fichier VERSIONNE ecrit pendant la passe ;
  1  : au moins un ; les fichiers et les chemins sont NOMMES, avec le canal qui a mordu ;
  99 : RIEN n'a pu etre mesure (git muet, perimetre vide, pytest en erreur d'usage).

Usage (depuis `scripts/python`) :

    python probe_956_purete_de_passe.py --lister          # le perimetre derive, sans rien jouer
    python probe_956_purete_de_passe.py                   # les candidats (defaut)
    python probe_956_purete_de_passe.py --fichiers tests/test_x_offline.py
    python probe_956_purete_de_passe.py --tout            # tout le perimetre offline (cher)

ASCII only (console cp1252). 100 % OFFLINE : aucun runner, aucun RPC.
"""
from __future__ import annotations

import argparse
import ast
import os
import subprocess
import sys
import time
from pathlib import Path

_PYDIR = Path(__file__).resolve().parent
if str(_PYDIR) not in sys.path:
    sys.path.insert(0, str(_PYDIR))

import probe_463r1_ecart_empreinte_offline as ECART                      # noqa: E402

#: Ce qui doit changer pour que ce cliquet puisse changer d'avis (#486-r15).
DECLENCHEUR = {
    "chemins": (
        "scripts/python/probe_956_purete_de_passe.py",
        # Le foyer du RECENSEMENT offline : ce probe en derive son perimetre.
        "scripts/python/probe_463r1_ecart_empreinte_offline.py",
        # Le proprietaire du seul prefixe EXEMPTE : `prefixes_neutres` en derive son chemin.
        "scripts/python/verdict_cache.py",
        # Tout fichier de test peut se mettre a ecrire : c'est LE gisement.
        "scripts/python/tests/**/*.py",
    ),
    "build": False,
    "toujours": False,
    "raison": "Il joue des fichiers de TEST et regarde ce qu'ils ecrivent : le perimetre est "
              "derive de `git ls-files`, donc tout fichier de test ajoute, retire ou modifie "
              "peut changer son verdict.",
}

EX_NON_MESURE = 99

#: Les evenements d'audit CPython qui MODIFIENT le disque, et l'INDICE de l'argument qui porte le
#: chemin ecrit. `open` est traite a part (son mode decide). Cette table est deliberement LARGE :
#: un evenement de trop coute un faux positif LISIBLE (le chemin est nomme), un evenement manquant
#: coute un angle mort SILENCIEUX.
EVENEMENTS_ECRITURE = {
    "os.remove": 0, "os.rmdir": 0, "os.mkdir": 0, "os.truncate": 0,
    "os.rename": 1, "os.link": 1, "os.symlink": 1,
    "shutil.copyfile": 1, "shutil.copymode": 1, "shutil.copystat": 1,
    "shutil.copytree": 1, "shutil.move": 1, "shutil.unpack_archive": 1,
    "shutil.rmtree": 0,
}

#: Modes d'`open` qui ecrivent. `+` compte : `r+` ouvre en LECTURE-ECRITURE.
_MODES_ECRIVANTS = frozenset("wax+")


class MontageImpossible(RuntimeError):
    """Ce dont ce probe depend et qui N'EST PAS son gisement (git muet, perimetre vide)."""


def prefixes_neutres() -> tuple:
    """FOYER UNIQUE (#956) : les prefixes VERSIONNES dont l'ecriture ne peut PAS changer un verdict.

    UN SEUL, et ce n'est pas une allowlist de circonstance -- c'est une CLASSE d'artefact dont la
    neutralite est prouvee AILLEURS, par un cliquet executable :

      `scripts/cliquets-cache/` -- le CACHE DE VERDICT PAR FICHIER (#486-r1). Sa cle contient le
      sha256 du CONTENU juge, donc une entree perimee ne peut que MANQUER -- donc faire
      RECALCULER -- jamais mentir. Son charter le dit (<< un cache absent, vide, corrompu ou en
      echec d'ecriture ne peut rendre qu'un verdict IDENTIQUE, plus lentement >>), et
      `tests/test_486_r1_cache_verdict_offline.py` le PROUVE : `verdict_cache.verifier` recalcule
      TOUT en ignorant le cache et confronte entree par entree, y compris une entree FALSIFIEE de
      facon coherente.

    Le prefixe est DERIVE de `verdict_cache.DOSSIER`, jamais recopie : le proprietaire du
    repertoire est seul a savoir ou il vit, et une chaine ecrite ici se perimerait le jour du
    deplacement -- en OUVRANT silencieusement le gisement au lieu de le fermer.

    ⚠ CE QUE L'EXEMPTION NE COUVRE PAS, ET IL FAUT LE LIRE : le TEMPS. Deux passes de decoupages
    differents ne rendront pas les memes DUREES -- l'une trouve le cache chaud, l'autre froid.
    C'est voulu, et c'est une raison de plus pour qu'un chronometre ne prouve rien sur cet axe.

    ⚠ ET CE QU'ELLE N'EST PAS : une porte ouverte. Toute entree AJOUTEE ici doit venir avec le
    cliquet qui PROUVE sa neutralite ; `test_956_purete_de_passe_offline.py` verifie que
    l'exemption designe exactement le foyer du cache, et que la preuve existe.
    """
    try:
        from verdict_cache import DOSSIER, RACINE
        return (DOSSIER.relative_to(RACINE).as_posix() + "/",)
    except Exception:                              # pragma: no cover - foyer deplace ou illisible
        # AUCUNE EXEMPTION PLUTOT QU'UNE DEVINEE : sans le foyer, on ne sait pas ce qui est
        # neutre. Sur-signaler est SUR (un rouge lisible) ; deviner ne l'est pas.
        return ()


# ------------------------------------------------------------------ LE PERIMETRE, DERIVE

#: Attributs de `pathlib.Path` / noms de fonctions qui ECRIVENT. Sert au filtre STATIQUE qui borne
#: le perimetre par defaut. SUR-APPROXIMATION ASSUMEE et NECESSAIRE : `replace` matche aussi
#: `str.replace`, `run` aussi bien un `git status` qu'un `--measure`. Un candidat de trop coute
#: quelques secondes de test ; un candidat manquant coute l'angle mort que ce probe existe pour
#: fermer.
_ECRITURES_ATTRIBUT = frozenset((
    "write_text", "write_bytes", "unlink", "mkdir", "touch", "rmdir", "replace", "rename",
    "symlink_to", "hardlink_to", "chmod", "writelines", "write"))
_ECRITURES_MODULE = frozenset((
    ("shutil", "copy"), ("shutil", "copy2"), ("shutil", "copyfile"), ("shutil", "copytree"),
    ("shutil", "rmtree"), ("shutil", "move"),
    ("os", "remove"), ("os", "unlink"), ("os", "rmdir"), ("os", "makedirs"), ("os", "mkdir"),
    ("os", "rename"), ("os", "replace"), ("os", "truncate"),
    ("json", "dump"),
    ("subprocess", "run"), ("subprocess", "check_call"), ("subprocess", "Popen"),
    ("subprocess", "check_output")))


def sites_d_ecriture(source: str) -> list:
    """`[(forme, ligne)]` -- les sites d'ecriture ou de lancement de processus d'un source.

    FONCTION PURE (elle prend le TEXTE), pour que sa contre-epreuve n'ait besoin d'aucun fichier.
    """
    try:
        arbre = ast.parse(source)
    except (SyntaxError, ValueError):
        # Illisible : on ne peut RIEN affirmer, donc on le RETIENT (le sens sur).
        return [("ILLISIBLE", 0)]
    out = []
    for n in ast.walk(arbre):
        if not isinstance(n, ast.Call):
            continue
        f = n.func
        if isinstance(f, ast.Attribute):
            if f.attr in _ECRITURES_ATTRIBUT:
                out.append((f.attr, n.lineno))
            elif isinstance(f.value, ast.Name) and (f.value.id, f.attr) in _ECRITURES_MODULE:
                out.append(("%s.%s" % (f.value.id, f.attr), n.lineno))
        elif isinstance(f, ast.Name) and f.id == "open":
            mode = ""
            if len(n.args) > 1 and isinstance(n.args[1], ast.Constant):
                mode = str(n.args[1].value)
            for kw in n.keywords:
                if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
                    mode = str(kw.value.value)
            if set(mode) & _MODES_ECRIVANTS:
                out.append(("open(%s)" % mode, n.lineno))
    return out


def candidats(racine=None) -> tuple:
    """`(candidats, perimetre_complet)` -- les fichiers de test qui portent un site d'ecriture."""
    racine = Path(racine) if racine else ECART.ROOT
    perimetre = ECART.recenser(racine)
    if not perimetre:
        raise MontageImpossible("le perimetre offline est VIDE -- `git ls-files %s` ne designe "
                                "aucun fichier de test" % ECART.TESTS_DIR)
    retenus = []
    for rel in perimetre:
        try:
            src = (racine / ECART.PREFIXE_ROOTDIR / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            retenus.append(rel)                    # illisible -> retenu, jamais ecarte en silence
            continue
        if sites_d_ecriture(src):
            retenus.append(rel)
    return retenus, perimetre


# ------------------------------------------------------------------ LE HOOK, ET SES DEUX CANAUX

def _versionnes(racine) -> set:
    """Les chemins SUIVIS par git, en minuscules et separateurs `/` (comparaison Windows)."""
    sortie = ECART._git(["ls-files"], "impossible d'enumerer les fichiers versionnes", racine)
    return {l.strip().lower() for l in sortie.splitlines() if l.strip()}


class EcrituresVersionnees:
    """Plugin pytest : QUI ecrit, OU, et par QUEL canal. Attribution par FICHIER de test.

    Concu pour etre installable tel quel dans une passe de `probe_457` : il n'ecrit rien, ne
    deselectionne rien, et son cout est celui d'un test de type d'evenement par `open`.
    """

    def __init__(self, racine: Path, suivis: set, avec_git: bool = True) -> None:
        self.racine = str(racine).replace("\\", "/").rstrip("/") + "/"
        self._prefixe = self.racine.lower()
        self._n = len(self.racine)
        self.suivis = suivis
        self.neutres = prefixes_neutres()
        self.avec_git = avec_git
        #: `{fichier de test: {chemin relatif}}` -- ecritures VUES DANS CE PROCESSUS.
        self.par_test: dict = {}
        #: idem, mais sur un prefixe dont la NEUTRALITE est prouvee (`prefixes_neutres`).
        #: RAPPORTEES -- une exemption tue ne se relit pas.
        self.par_test_neutre: dict = {}
        #: idem, pour ce qui n'est PAS versionne (rapporte, non bloquant).
        self.hors_versionne: dict = {}
        #: `{fichier de test: {chemin}}` -- deltas NETS vus par `git status` a la borne.
        self.par_test_net: dict = {}
        #: Les fichiers de test qui ont lance un PROCESSUS FILS : le canal 1 ne les couvre pas.
        self.fils: set = set()
        #: Ecritures faites HORS de tout test (collecte, import, conftest).
        self.globales: set = set()
        self.courant = None
        self.clos = False
        self._interne = False          # vrai pendant NOS propres appels a git
        self._etat = self._git_status()
        sys.addaudithook(self._hook)

    # -- canal 2 : le delta NET, tous processus confondus ---------------------------------
    def _git_status(self):
        if not self.avec_git:
            return None
        self._interne = True
        try:
            # `--no-optional-locks` : sans lui, `git status` RAFRAICHIT l'index et prend
            # `index.lock`. Ce probe est fait pour tourner AUSSI dans une passe multi-shard, ou N
            # processus le feraient en meme temps -- la course sur le lock ferait echouer des
            # bornes au hasard, donc rendrait la mesure dependante du parallelisme, exactement le
            # defaut qu'on ferme.
            proc = subprocess.run(["git", "--no-optional-locks", "-C", self.racine,
                                   "status", "--porcelain"],
                                  capture_output=True, text=True, encoding="utf-8",
                                  errors="replace")
        except OSError:
            return None
        finally:
            self._interne = False
        if proc.returncode != 0:
            return None
        return {l[3:].strip().strip('"') for l in (proc.stdout or "").splitlines() if l[3:].strip()}

    def _borne(self):
        """Ferme le fichier courant : ce que `git status` voit de neuf lui est attribue."""
        if self._etat is None or self.courant is None:
            return
        etat = self._git_status()
        if etat is None:
            return
        neufs = {p for p in etat ^ self._etat
                 if p.lower() in self.suivis and not p.startswith(self.neutres)}
        if neufs:
            self.par_test_net.setdefault(self.courant, set()).update(neufs)
        self._etat = etat

    # -- canal 1 : le hook d'audit ---------------------------------------------------------
    def _hook(self, event, args):
        if event == "open":
            mode = args[1] if len(args) > 1 else None
            if not isinstance(mode, str) or not (set(mode) & _MODES_ECRIVANTS):
                return
            chemin = args[0]
        elif event in EVENEMENTS_ECRITURE:
            i = EVENEMENTS_ECRITURE[event]
            chemin = args[i] if len(args) > i else None
        elif event == "subprocess.Popen":
            if self.courant is not None and not self._interne:
                self.fils.add(self.courant)
            return
        else:
            return
        if type(chemin) is not str or len(chemin) <= self._n:
            return
        q = chemin.replace("\\", "/")
        if not q.lower().startswith(self._prefixe):
            return
        rel = q[self._n:]
        if rel.lower() not in self.suivis:
            seau = self.hors_versionne
        elif rel.startswith(self.neutres):
            seau = self.par_test_neutre
        else:
            seau = self.par_test
        if self.courant is None:
            if self.clos or seau is not self.par_test:
                return
            self.globales.add(rel)
        else:
            seau.setdefault(self.courant, set()).add(rel)

    # -- pytest ----------------------------------------------------------------------------
    def pytest_runtest_logstart(self, nodeid, location):               # noqa: D102
        rel = str(nodeid).split("::")[0].replace("\\", "/")
        if rel != self.courant:
            self._borne()
            self.courant = rel

    def pytest_sessionfinish(self, session, exitstatus):               # noqa: D102
        self._borne()
        self.courant = None
        # L'INSTRUMENT NE SE MESURE PAS LUI-MEME (#547-r5) : ce que ce processus ouvre APRES la
        # session est le fait du probe, pas du depot.
        self.clos = True

    # -- verdict ----------------------------------------------------------------------------
    def impurs(self) -> dict:
        """`{fichier de test: {"hook": [...], "net": [...]}}` -- ce qui ecrit du VERSIONNE."""
        out: dict = {}
        for rel, chemins in self.par_test.items():
            out.setdefault(rel, {})["hook"] = sorted(chemins)
        for rel, chemins in self.par_test_net.items():
            out.setdefault(rel, {})["net"] = sorted(chemins)
        return out


# ------------------------------------------------------------------------------- POINT D'ENTREE

def _jouer(fichiers: list, racine: Path, avec_git: bool = True) -> tuple:
    """Joue `fichiers` sous le plugin. Rend `(plugin, rc)`."""
    import pytest

    suivis = _versionnes(racine)
    if not suivis:
        raise MontageImpossible("`git ls-files` n'a rendu AUCUN fichier suivi -- le critere "
                                "<< versionne >> serait VIDE, donc le verdict vacueux")
    plugin = EcrituresVersionnees(racine, suivis, avec_git=avec_git)
    rc = pytest.main(["-q", "-p", "no:cacheprovider", *fichiers], plugins=[plugin])
    return plugin, int(rc)


def _run(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--lister", action="store_true",
                    help="Imprime le perimetre DERIVE et sort, sans rien jouer.")
    ap.add_argument("--tout", action="store_true",
                    help="Joue TOUT le perimetre offline au lieu des seuls candidats. Le prix est "
                         "celui de la banque -- a n'employer que pour re-etablir la mesure.")
    ap.add_argument("--fichiers", nargs="+", default=None,
                    help="Joue exactement ces fichiers (chemins relatifs a scripts/python).")
    ap.add_argument("--sans-git", action="store_true",
                    help="Desarme le canal 2 (`git status` aux bornes). Diagnostic seulement : "
                         "le canal 1 ne voit pas les ecritures des processus FILS.")
    args = ap.parse_args(argv)

    racine = ECART.ROOT
    cands, perimetre = candidats(racine)
    print("[956] perimetre offline : %d fichier(s) ; portant un site d'ecriture ou de "
          "sous-processus : %d" % (len(perimetre), len(cands)))

    if args.fichiers:
        fichiers = [f.replace("\\", "/") for f in args.fichiers]
        inconnus = [f for f in fichiers if f not in set(perimetre)]
        if inconnus:
            print("[956] REFUS D'USAGE : %d chemin(s) hors du perimetre offline : %s"
                  % (len(inconnus), ", ".join(inconnus[:5])))
            return 2
    elif args.tout:
        fichiers = list(perimetre)
    else:
        fichiers = list(cands)

    if args.lister:
        for rel in fichiers:
            print("   ", rel)
        return 0
    if not fichiers:
        print("[956] AUCUN fichier a jouer -- rien n'a ete mesure.")
        print("[956] rc=%d" % EX_NON_MESURE)
        return EX_NON_MESURE

    debut = time.time()
    plugin, rc = _jouer(fichiers, racine, avec_git=not args.sans_git)
    mur = time.time() - debut

    if rc in (2, 3, 4, 5):
        print("[956] pytest rc=%d -- erreur d'USAGE ou interruption : AUCUN verdict." % rc)
        print("[956] rc=%d" % EX_NON_MESURE)
        return EX_NON_MESURE

    impurs = plugin.impurs()
    print("[956] %d fichier(s) joue(s) en %.1f s ; %d ont lance un PROCESSUS FILS ; "
          "%d ecriture(s) hors-versionne (rapportees, non bloquantes)"
          % (len(fichiers), mur, len(plugin.fils),
             sum(len(v) for v in plugin.hors_versionne.values())))
    if plugin.par_test_neutre:
        # L'EXEMPTION EST DITE, JAMAIS TUE. Une exemption silencieuse est indistinguable d'un
        # angle mort, et c'est par la que la classe s'elargirait sans que personne ne le voie.
        print("[956] ecritures sur un prefixe dont la NEUTRALITE est PROUVEE (%s) -- comptees, "
              "non bloquantes :" % ", ".join(prefixes_neutres()))
        for rel, chemins in sorted(plugin.par_test_neutre.items()):
            print("        %-58s %s" % (rel, ", ".join(sorted(chemins)[:2])))
    if plugin.fils:
        # LE TRI-ETAT, DIT. Ces fichiers-la ne sont couverts QUE par le canal 2 : le hook d'audit
        # ne franchit pas la frontiere de processus. Les nommer permet de rejouer exactement
        # ceux-la avec `git status` arme, sans payer la passe entiere.
        print("[956] SOUS-TRAITANTS (axe hook NON mesurable, canal 2 seul) :")
        for rel in sorted(plugin.fils):
            print("        %s" % rel)
    if plugin.globales:
        print("[956] %d ecriture(s) VERSIONNEE(S) HORS DE TOUT TEST (collecte / import / "
              "conftest) : %s" % (len(plugin.globales), ", ".join(sorted(plugin.globales)[:5])))
    if not args.sans_git and plugin._etat is None:
        print("[956] canal 2 (`git status` aux bornes) INDISPONIBLE -- les ecritures faites par "
              "un PROCESSUS FILS ne sont PAS couvertes par cette passe.")

    if not impurs and not plugin.globales:
        print("[956] VERDICT: PASS -- aucun fichier VERSIONNE ecrit par les %d fichier(s) joue(s)."
              % len(fichiers))
        return 0

    print("")
    for rel in sorted(impurs):
        canaux = impurs[rel]
        print("  ECRIT DU VERSIONNE  %s%s" % (rel, "  [lance un fils]" if rel in plugin.fils else ""))
        for canal, chemins in sorted(canaux.items()):
            libelle = ("hook d'audit (ecriture VUE, meme transitoire)" if canal == "hook"
                       else "`git status` a la borne (delta NET, tous processus)")
            print("      %s :" % libelle)
            for c in chemins[:8]:
                print("          %s" % c)
            if len(chemins) > 8:
                print("          ... et %d autre(s)" % (len(chemins) - 8))
    print("")
    print("[956] Un fichier VERSIONNE ecrit pendant une passe rend le verdict de la banque")
    print("[956] DEPENDANT DE LA COMPOSITION DES SHARDS : un autre fichier de test qui le LIT")
    print("[956] voit un etat qui depend de qui a tourne avant lui, et la passe laisse l'arbre")
    print("[956] SALE pour la suivante.")
    print("[956] Deux issues, et ce cliquet n'en choisit AUCUNE :")
    print("[956]   (a) le test ecrit dans un TEMPORAIRE (`tmp_path`) -- verifier alors qu'il MORD")
    print("[956]       encore : la contre-epreuve de #935-r1 s'etait desarmee ainsi ;")
    print("[956]   (b) l'ecriture est le SUJET du test -- la deplacer hors du fichier versionne,")
    print("[956]       ou la faire porter par un depot JETABLE (cf. `test_463r1`, etage 3).")
    print("")
    print("[956] VERDICT: FAIL -- %d fichier(s) de test ecrivent du VERSIONNE." % len(impurs))
    return 1


def main(argv=None) -> int:
    """TROIS issues (#471) : 0 = passe PURE, 1 = au moins une ecriture versionnee, 99 = montage."""
    try:
        return _run(argv)
    # LES DEUX CLASSES, et ce n'est pas un ornement : le perimetre vient du foyer `probe_463r1`,
    # dont le `_git` leve SA propre `MontageImpossible`. Ne rattraper que la notre faisait sortir
    # une panne de git en TRACEBACK, donc `rc=1` -- lu << un test ecrit du versionne >> pour un
    # depot absent. C'est le patron #471 exactement, et il a failli passer.
    except (MontageImpossible, ECART.MontageImpossible) as exc:
        print("[956] MONTAGE EN ECHEC : %s" % exc)
        print("[956] RIEN n'a ete mesure. Ce n'est PAS un verdict sur le depot.")
        print("[956] rc=%d" % EX_NON_MESURE)
        return EX_NON_MESURE


if __name__ == "__main__":
    sys.exit(main())
