#!/usr/bin/env python
"""#486-r12 -- CLIQUET : chaque cliquet de la banque DECLARE son declencheur, et le DECLARE JUSTE.

CE QUE CE CLIQUET EST SEUL A VOIR
----------------------------------
Un cliquet de `scripts/ratchets.ps1` qui (a) ne dit PAS ce qui doit changer pour qu'il change
d'avis, ou (b) le dit TROP ETROIT -- il LIT un fichier que son `DECLENCHEUR` ne couvre pas. La
seconde faute est la dangereuse : elle ne produit ni erreur ni rouge, elle produit un cliquet
QU'ON NE JOUE PAS quand son gisement vient de se rouvrir. Exactement la signature de
`TARGETING_OPTIONS` -- permissive, silencieuse, et alimentee par notre propre cadence.

Aucun autre cliquet ne regarde cet axe. `probe_439` verifie qu'une entree PEUT rendre un code
non nul ; `probe_471` ce que ce non-nul SIGNIFIE ; `probe_457` selectionne des TESTS (jamais des
cliquets) ; `probe_486r2` demande si un probe peut encore DEMARRER. Aucun ne demande ce dont un
verdict DEPEND.

LES DEUX ETAGES, ET POURQUOI LE SECOND NE PEUT PAS ETRE UNE RELECTURE DU SOURCE
--------------------------------------------------------------------------------
  [1] DECLARATION -- perimetre DERIVE de `scripts/ratchets.ps1` (jamais une liste ecrite ici :
      une entree neuve doit entrer d'elle-meme, c'est la lecon de #457-r6 sur les allowlists).
      Chaque script de la banque doit porter un `DECLENCHEUR` bien forme, et peut AFFINER
      entree par entree (`DECLENCHEUR_PAR_ENTREE`, #486-r19). Une cle qui ne designe aucune
      entree de banque de ce script est une declaration MORTE, donc un rouge.
  [2] MESURE -- la declaration est confrontee aux fichiers que le cliquet OUVRE REELLEMENT
      (`declencheur_trace`, meme idee que `probe_457._FilesPerTest`). Croire le source du
      declarant reviendrait a lui demander de s'auto-attester : un `read_text` derriere un
      helper, un `import` qui traine un paquet, une table lue par un module tiers sont
      invisibles a l'oeil et decisifs pour le verdict.

CE QUE #486-r19 A CHANGE, ET POURQUOI CE N'ETAIT PAS COSMETIQUE
---------------------------------------------------------------
L'empreinte est keyee par ENTREE DE BANQUE depuis le premier jour ; la declaration, elle, ne
pouvait porter que sur le FICHIER. L'etage 2 confrontait donc une mesure FINE a une declaration
GROSSIERE. 14 des 25 entrees du groupe C sont dans ce cas (6 etapes de `probe_283`, 8 shards de
`probe_457`), et l'effet est double : la confrontation est DESARMEE (`probe_283:diff` ne lit que
`data/symbols/<build>/frida/enums.tsv` mais etait juge contre l'union des six etapes, donc il ne
pouvait pas rougir), et la declaration est INEXPLOITABLE par une future selection -- un `.ts` de
`frida/` rejouerait 161,8 s d'etapes qui ne le lisent pas.

L'EMPREINTE EST VERSIONNEE, ET UNE ENTREE PERIMEE NE PEUT QUE MANQUER
----------------------------------------------------------------------
`scripts/declencheurs-empreinte.tsv` porte, par entree de banque, DEUX shas pris au moment de la
mesure : le source du cliquet, et la fermeture de ses imports (#486-r36). Si l'un des deux a
bouge depuis, l'entree n'est pas SERVIE -- elle est declaree PERIMEE, donc NON MESUREE. C'est la
regle de `verdict_cache` (#486-r1) : une attestation qui ne peut que manquer ne peut pas mentir.
Le mode `--mesurer` la reconstruit.

⚠ LE SECOND SHA N'EST PAS UN CONFORT (#486-r36). Le premier seul laissait servir une empreinte
qu'un helper partage avait perimee : `declencheur_trace` qui se met a lire un TSV, un
`engine/x.py` qui ajoute un import -- rien de tout cela ne touche le fichier du cliquet, donc
rien ne perimait, et la confrontation jugeait un perimetre PERIME. Le foyer est `cle_fraicheur`,
et il sert AUSSI `--incremental` : le mode rapide remesure exactement ce que l'etage 2 aurait
refuse de servir, donc il ne peut pas changer un verdict.

LE COUT EST MESURE ET VERSIONNE
--------------------------------
`scripts/declencheurs-durees.json` porte la duree de chaque entree, avec son REGIME (`serie` =
cout isole ; `para-N` = duree portant la contention). Sans lui, personne ne pouvait dire ou
passaient les ~20 min de `--mesurer`, et les deux accelerations possibles repondent a des
distributions OPPOSEES : concentree, seul l'incremental paye ; plate, seul le parallelisme paye.

TRI-ETAT (#471) -- une panne d'outil ne rougit pas
---------------------------------------------------
  0  : tout ce qui etait mesurable a ete mesure, rien ne rougit ;
  1  : au moins un cliquet ne declare pas, declare mal, ou LIT hors de son perimetre declare ;
  99 : rien n'a pu etre mesure (banque illisible), ou aucun rouge mais des entrees NON MESUREES.

CE QUE LA MESURE NE VOIT PAS, ET QUI EST DIT PLUTOT QUE TU
-----------------------------------------------------------
Un sous-process NON-python (`git`, `pwsh`) lit hors de notre hook. Le cliquet qui en lance est
marque MESURE INCOMPLETE : sa confrontation garde son sens dans UN sens (ce qui est VU doit etre
couvert), jamais dans l'autre. De meme, un fichier dont seule l'EXISTENCE decide n'est jamais
ouvert. C'est pourquoi un declencheur se prend LARGE : la mesure borne par le BAS.

⚠ ET UNE MESURE PEUT ETRE UN REFUS (#486-r36). Un cliquet qui rend un rc DISANT n'avoir rien
mesure (cf. `RC_SANS_MESURE`) laisse une trace : celle de son refus, quelques lectures que tout
glob couvre. Mesure du 2026-08-10 : les 8 shards `probe_457:s*` etaient dans ce cas -- 8 des 49
entrees se comptaient CONFRONTEES sans rien confronter. Elles tombent desormais en NON MESUREE,
pas en rouge : ce n'est pas un verdict sur leur declaration.

Usage :
    python probe_486r12_declencheurs.py                 # les deux etages
    python probe_486r12_declencheurs.py --mesurer       # (re)mesure TOUTE la banque, puis ecrit
    python probe_486r12_declencheurs.py --mesurer --incremental --jobs 8   # le geste QUOTIDIEN
    python probe_486r12_declencheurs.py --mesurer --only probe_181,probe_313
    python probe_486r12_declencheurs.py --verbose

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import declencheur_cliquet as DC                                       # noqa: E402
import declencheur_trace as DT                                         # noqa: E402
import probe_439_cliquet_peut_rougir as B439                           # noqa: E402
import verdict_cache                                                   # noqa: E402

ROOT = PYDIR.parents[1]
EMPREINTE = ROOT / "scripts" / "declencheurs-empreinte.tsv"
#: `2` depuis #486-r36 : chaque entree porte une seconde ligne `ferm` (sha de la fermeture
#: d'imports). Une empreinte de format 1 se relit sans erreur -- `ferm` y vaut la chaine vide,
#: donc TOUTES ses entrees sont PERIMEES, ce qui est le comportement voulu : on ne sert pas une
#: attestation dont on ne peut pas etablir la fraicheur.
FORMAT = "2"

#: Le COUT de chaque entree, par entree de banque -- versionne (#486-r36).
#:
#: POURQUOI IL FALLAIT L'ECRIRE. Le chrono existait depuis le premier jour (`t0 = time.time()`
#: autour du `subprocess.run`) et n'atterrissait nulle part : la ligne `[mesure]` defile puis
#: disparait. Personne ne pouvait donc dire OU passaient les ~20 min de `--mesurer`, et toute
#: decision d'acceleration (incremental ? parallelisme ?) se prenait a l'intuition -- alors que
#: les deux repondent a des distributions OPPOSEES (concentree => seul l'incremental paye ;
#: plate => seul le parallelisme paye). `scripts/ratchets-457-durations.json` ne couvre PAS ce
#: gisement : il porte des FICHIERS DE TEST, et son intersection avec les ids de banque est VIDE.
#:
#: ⚠ LE REGIME EST ECRIT AVEC LA DUREE, et ce n'est pas decoratif : une entree mesuree sous
#: parallelisme 16 sur une machine a 8 coeurs porte la contention de ses voisines, pas son cout.
#: Comparer deux passes sans lire leur regime ferait conclure a une regression la ou seul le
#: throttle a change. `serie` est le seul regime dont la duree est un COUT ISOLE.
DUREES = ROOT / "scripts" / "declencheurs-durees.json"
FORMAT_DUREES = "1"

#: Ce qui doit changer pour que ce cliquet puisse changer d'avis (#486-r12).
#: Il est SOUMIS A SON PROPRE CRITERE -- exiger des autres une declaration sans en porter une
#: serait indefendable, et c'est le meme principe qui met `probe_439` dans la banque qu'il garde.
DECLENCHEUR = {
    "chemins": ("scripts/ratchets.ps1", "scripts/python/**/*.py",
                "scripts/declencheurs-empreinte.tsv"),
    "build": False,
    "toujours": False,
    "raison": "Trois entrees, toutes dans l'arbre. La BANQUE (son perimetre en est DERIVE, donc "
              "une entree ajoutee ou retiree change son verdict), le SOURCE de chaque script de "
              "la banque (il y lit le `DECLENCHEUR` par AST -- pris a tout `scripts/python/**` "
              "parce que la banque seule dit lesquels), et l'EMPREINTE versionnee qu'il "
              "confronte. Aucune dependance au build ni au jeu : tout ce qu'il juge est du "
              "texte du depot.",
}

#: Budget par cliquet a la mesure. `probe_319` pese ~135 s isole ; 900 s laisse de la marge sous
#: contention sans laisser un cliquet bloque pendre indefiniment.
TIMEOUT = 900


# ============================================================== derivation de la banque
def banque() -> dict:
    """`{id de banque: [argv]}`, DERIVE de `scripts/ratchets.ps1`.

    On reutilise `probe_439.banque_par_texte` -- foyer UNIQUE de cette lecture. La reecrire ici
    creerait une seconde source pour une meme composition, ce que #430 combat sur la banque.
    """
    return B439.banque_par_texte()


def script_de(argv) -> str | None:
    for a in argv:
        if a.endswith(".py"):
            return a
    return None


def par_script(bq: dict) -> dict:
    """`{script.py: [ids]}` -- plusieurs entrees partagent un script (`probe_283:*`, `probe_457:*`).

    Le `DECLENCHEUR` porte sur le SCRIPT et vaut pour l'UNION de ses entrees : c'est le sens
    conservateur, et il reste le REPLI de toute entree qui ne s'affine pas.

    ⚠ MAIS L'UNION SEULE ETAIT UNE ASYMETRIE (#486-r19), et elle desarmait l'etage 2.
    L'EMPREINTE est deja par ENTREE (`declencheurs-empreinte.tsv` est keye sur l'id de banque) :
    on confrontait donc une mesure FINE a une declaration GROSSIERE. `probe_283:diff` ne lit que
    `data/symbols/<build>/frida/enums.tsv` (1,1 s) et etait juge contre l'union des SIX etapes,
    qui couvre tout `.py`/`.ts`/`.js` du depot -- il ne pouvait structurellement pas rougir, et
    surtout il ne DISAIT rien. Sur les 25 entrees du groupe C, 14 partagent un fichier avec des
    perimetres differents (6 pour `probe_283`, 8 pour `probe_457`).
    Un script peut donc affiner, entree par entree, via `DECLENCHEUR_PAR_ENTREE` -- contrat et
    resolution dans `declencheur_cliquet.py`, foyer UNIQUE.
    """
    out: dict = {}
    for ident, argv in bq.items():
        s = script_de(argv)
        if s:
            out.setdefault(s, []).append(ident)
    return out


# ============================================================== empreinte : lecture/ecriture
class Empreinte:
    """`{id: {"sha", "ferm", "lu": [(dossier, ext, n, t_min, t_max)], "proc": [..], "nproc"}}`.

    ⚠ `commit` est INFORMATIF -- aucun verdict n'en depend, contrairement a `probe_457` qui
    invalide son empreinte par l'AGE. Ici la peremption se joue entierement sur le `sha` du
    source de chaque cliquet, ce qui la rend insensible a une reecriture d'historique : apres
    un rebase, le commit note devient orphelin alors que les fichiers, eux, sont identiques.
    Faire dependre un verdict de ce champ transformerait chaque rebase en `NON MESURE`.
    """

    def __init__(self) -> None:
        self.par_id: dict = {}
        self.commit: str = "?"

    # -- lecture -----------------------------------------------------------------------
    #: ⚠ `chemin=None` et JAMAIS `chemin=EMPREINTE` : une valeur par defaut est evaluee A
    #: L'IMPORT, donc elle FIGE le chemin et rend `EMPREINTE` insubstituable -- c'est la
    #: forme A du CLAUDE.md (<< ne mord pas >>), et le test offline l'a attrapee.
    @classmethod
    def charger(cls, chemin=None):
        e = cls()
        p = Path(chemin or EMPREINTE)
        if not p.is_file():
            return e
        for ligne in p.read_text(encoding="utf-8", errors="replace").splitlines():
            if not ligne.strip():
                continue
            if ligne.startswith("#"):
                if ligne.startswith("# commit="):
                    e.commit = ligne.split("=", 1)[1].strip()
                continue
            ch = ligne.split("\t")
            if len(ch) < 3:
                continue
            ident, kind = ch[0], ch[1]
            d = e.par_id.setdefault(ident, {"sha": "", "ferm": "", "inst": "", "lu": [],
                                            "proc": [], "nproc": 0, "rc": 0})
            if kind == "sha":
                d["sha"] = ch[2]
            elif kind == "ferm":
                d["ferm"] = ch[2]
            elif kind == "inst":
                d["inst"] = ch[2]
            elif kind == "rc":
                d["rc"] = int(ch[2] or 0)
            elif kind == "proc":
                d["proc"].append(ch[2])
            elif kind == "nproc":
                d["nproc"] = int(ch[2] or 0)
            elif kind == "lu" and len(ch) >= 7:
                d["lu"].append((ch[2], ch[3], int(ch[4] or 0), ch[5], ch[6]))
        return e

    # -- ecriture ----------------------------------------------------------------------
    def ecrire(self, chemin=None) -> None:      # `None` : cf. `charger` (forme A insubstituable)
        lignes = ["# format=%s  declencheurs-empreinte (#486-r12) -- GENERE, jamais fusionne a "
                  "la main : REGENERER (`--mesurer`) en cas de conflit." % FORMAT,
                  "# commit=%s" % self.commit,
                  "# Une ligne `lu` = un groupe (dossier, extension) reellement OUVERT en lecture,",
                  "# avec son compte et DEUX temoins (le plus petit et le plus grand chemin du",
                  "# groupe). Les temoins sont ce que le cliquet confronte aux globs declares :",
                  "# l'agregation borne la taille du fichier, et c'est une APPROXIMATION assumee",
                  "# -- un glob discriminant sur le NOM de base pourrait couvrir les deux temoins",
                  "# sans couvrir un troisieme fichier du meme groupe."]
        for ident in sorted(self.par_id):
            d = self.par_id[ident]
            lignes.append("%s\tsha\t%s" % (ident, d["sha"]))
            lignes.append("%s\tferm\t%s" % (ident, d.get("ferm") or ""))
            lignes.append("%s\tinst\t%s" % (ident, d.get("inst") or ""))
            lignes.append("%s\trc\t%d" % (ident, d.get("rc") or 0))
            lignes.append("%s\tnproc\t%d" % (ident, d["nproc"]))
            for prog in sorted(set(d["proc"])):
                lignes.append("%s\tproc\t%s" % (ident, prog))
            for grp in sorted(d["lu"]):
                lignes.append("%s\tlu\t%s\t%s\t%d\t%s\t%s" % (ident, grp[0], grp[1], grp[2],
                                                              grp[3], grp[4]))
        Path(chemin or EMPREINTE).write_text("\n".join(lignes) + "\n", encoding="utf-8")


_FICHIERS_DU_DEPOT: dict | None = None


def fichiers_par_groupe() -> dict:
    """`{(dossier, ext): [chemins versionnes]}` -- les CANDIDATS possibles d'un groupe trace.

    `None` n'est jamais rendu : une panne de `git ls-files` leve, elle ne se degrade pas en
    dictionnaire vide. Un zero fabrique ici ferait imprimer « 0 groupe a risque », c'est-a-dire
    exactement le faux vert que l'inventaire ci-dessous existe pour ne pas rendre.
    """
    global _FICHIERS_DU_DEPOT
    if _FICHIERS_DU_DEPOT is not None:
        return _FICHIERS_DU_DEPOT
    out = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z"],
                         capture_output=True, text=True, timeout=120, check=True)
    par: dict = {}
    for rel in out.stdout.split("\0"):
        if not rel:
            continue
        dossier, _, base = rel.rpartition("/")
        ext = ("." + base.rsplit(".", 1)[1]) if "." in base else ""
        par.setdefault((dossier, ext), []).append(rel)
    _FICHIERS_DU_DEPOT = par
    return par


def groupes_a_risque(e, globs) -> list:
    """L'AMPLITUDE MAJOREE du trou d'agregation (#486-r16 (a)), groupe par groupe.

    ---------------------------------------------------------------------------------------
    CE QUE CE COMPTE DIT, ET CE QU'IL NE DIT PAS
    ---------------------------------------------------------------------------------------
    Une ligne `lu` agrege un groupe `(dossier, extension)` en `n` + DEUX temoins (le plus petit
    et le plus grand chemin, lexicographiquement). La confrontation aux globs ne porte donc que
    sur ces deux-la : un glob discriminant sur le NOM DE BASE peut les couvrir tous les deux et
    rater un TROISIEME fichier du meme groupe. C'est une approximation assumee, et elle penche
    du cote du FAUX VERT.

    On ne peut pas la FERMER a cout tenable, et c'est MESURE (2026-08-15) : garder tous les
    chemins couterait **55 555** lignes `lu` au lieu de **1 197**, soit **x46** sur un artefact
    versionne dont le conflit de merge est deja un sujet (#943-r2). Deplacer la confrontation
    DANS la mesure la fermerait sans grossir le fichier, mais ferait dependre le verdict FIGE
    de `declencheur_cliquet.couvre`, qui n'est PAS dans la cle de fraicheur -- on echangerait
    une approximation bornee contre un trou non borne, et il faudrait re-mesurer toute la
    banque (~1 425 s) pour le poser.

    Alors on la MESURE, et on l'IMPRIME. Pour chaque groupe de plus de deux fichiers dont les
    deux temoins PASSENT, on cherche un chemin VERSIONNE strictement entre eux que les globs ne
    couvrent PAS : s'il en existe un, l'agregation POURRAIT masquer une lecture hors perimetre
    sur ce groupe.

    ⚠ C'EST UNE MAJORATION, DONC UN INVENTAIRE ET JAMAIS UN GATE. Le cliquet n'a lu que `n`
    fichiers du groupe ; rien ne dit que le chemin exhibe en fasse partie. Rougir dessus
    accuserait a tort, et un cran qui accuse a tort se fait desarmer -- le remede serait alors
    d'elargir les declencheurs, c'est-a-dire de MASQUER le trou au lieu de le mesurer, ce que
    #486-r16 interdit explicitement.
    """
    par = fichiers_par_groupe()
    risque = []
    for dossier, ext, n, t_min, t_max in e["lu"]:
        if n <= 2 or not t_min or not t_max or t_min == t_max:
            continue
        if any(DC.couvre(globs, t) is None for t in (t_min, t_max)):
            continue                                   # deja rouge : le trou n'y ajoute rien
        rates = [c for c in par.get((dossier, ext), ())
                 if t_min < c < t_max and DC.couvre(globs, c) is None]
        if rates:
            risque.append((dossier, ext, n, len(rates), rates[0]))
    return risque


def grouper(lectures) -> list:
    """`{(dossier, ext): (n, min, max)}` -> liste triee. Cf. l'en-tete du fichier ecrit."""
    seaux: dict = {}
    for rel in lectures:
        dossier, _, base = rel.rpartition("/")
        ext = ("." + base.rsplit(".", 1)[1]) if "." in base else ""
        cle = (dossier, ext)
        n, mn, mx = seaux.get(cle, (0, None, None))
        seaux[cle] = (n + 1, rel if mn is None or rel < mn else mn,
                      rel if mx is None or rel > mx else mx)
    return sorted((d, e, n, mn, mx) for (d, e), (n, mn, mx) in seaux.items())


def sha_source(script: str) -> str:
    """Sha du CONTENU LOGIQUE du cliquet -- `sha_texte`, jamais `sha_fichiers`.

    `sha_fichiers` hache les OCTETS ; `core.autocrlf` vaut `true` ici, donc les memes octets
    versionnes se materialisent en CRLF sous Windows et en LF ailleurs. Une empreinte VERSIONNEE
    hachee sur les octets serait PERIMEE d'une plateforme a l'autre -- 46 entrees `NON MESUREE`
    et un rc=99 permanent, ce qui est la forme la plus surement desarmee d'un garde-fou.
    """
    p = PYDIR / script
    if not p.is_file():
        return ""
    return verdict_cache.sha_texte(p.read_text(encoding="utf-8", errors="replace"))


#: Memoisation de la fermeture d'imports -- une instance PAR RACINE, donc chaque module du depot
#: n'est parse et lu qu'UNE fois quels que soient les cliquets qui l'atteignent.
#: ⚠ MEMOISE PAR RACINE, JAMAIS UNE INSTANCE UNIQUE POSEE A L'IMPORT : `ROOT` est SUBSTITUE par
#: les tests offline (`monkeypatch.setattr(G, "ROOT", tmp_path)`), et une instance figee a
#: l'import lirait l'arbre REEL pendant que le reste du garde lit l'arbre jetable. C'est la
#: forme A du `CLAUDE.md` (<< ne mord pas >>), transposee d'un import a un cache.
_FERM: dict = {}
_SHA_FERM: dict = {}


def _fermeture():
    cle = str(ROOT)
    f = _FERM.get(cle)
    if f is None:
        f = DC.Fermeture(cle)
        _FERM[cle] = f
    return f


def sha_fermeture(script: str) -> str:
    """Sha de TOUT ce que le cliquet importe, transitivement -- pas de son seul fichier.

    ⚠ C'EST LE TROU QUE `sha_source` LAISSAIT OUVERT, ET IL EST EXACTEMENT DU TYPE QUE CE
    CLIQUET EXISTE POUR ATTRAPER. L'empreinte atteste << voici ce que cette entree OUVRE >>. Ce
    qu'elle ouvre depend de son fichier, mais AUSSI de chaque module qu'il tire : un
    `declencheur_trace` qui se met a lire un TSV, un `engine/x.py` qui ajoute un `import
    engine.y`, un helper partage qui change de table -- rien de tout cela ne touche le fichier du
    cliquet. Le `sha` ne bougeait donc pas, l'empreinte restait SERVIE, et la confrontation
    jugeait un perimetre PERIME. Permissif, silencieux, et alimente par notre propre cadence :
    la signature meme de `TARGETING_OPTIONS`.

    LA FERMETURE EST DEJA DERIVEE ICI, on ne l'invente pas : `declencheur_cliquet.Fermeture` la
    calcule pour la cascade de harnais (#531). Elle prend TOUS les imports, y compris ceux
    ECRITS DANS UN CORPS DE FONCTION -- une sous-approximation dans un critere de fraicheur
    serait un faux vert, exactement comme dans un critere de couverture.

    CE QUE CE SHA NE COUVRE PAS, ET QUI EST DIT PLUTOT QUE TU :
      * un fichier de DONNEES dont le CONTENU dirige les lectures (une table qui liste des
        chemins a ouvrir) ; il change sans que ni le source ni la fermeture ne bougent ;
      * un fichier AJOUTE a l'arbre qu'un cliquet BALAYEUR (`probe_283`, `probe_431`) lirait
        alors qu'aucun glob declare ne le couvre.
    Les deux sont des trous de la PEREMPTION, pas de la mesure : `--mesurer` sans
    `--incremental` les dissout, et c'est pourquoi il reste la reference.
    """
    memo = (str(ROOT), script)
    if memo in _SHA_FERM:
        return _SHA_FERM[memo]
    rel = "scripts/python/" + script
    morceaux = []
    if (ROOT / rel).is_file():
        for m in sorted(_fermeture().de(rel)):
            q = ROOT / m
            try:
                morceaux.append(m + "\0" + q.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                morceaux.append(m + "\0<illisible>")
    # Une fermeture VIDE rend la chaine VIDE, jamais `sha_texte("")` : un cliquet qui n'importe
    # rien du depot n'a pas de seconde composante, et lui en fabriquer une ferait mentir la
    # difference entre << pas de dependance >> et << dependance dont le contenu est vide >>.
    _SHA_FERM[memo] = (verdict_cache.sha_texte("\n\0\0\n".join(morceaux)) if morceaux else "")
    return _SHA_FERM[memo]


#: L'INSTRUMENT : les modules dont depend ce que la mesure VOIT (hook `open`, normalisation du
#: `__pycache__`, repertoires exclus, fusion des traces). Ils ne sont importes par AUCUN cliquet,
#: donc aucune fermeture ne les porte -- et pourtant une empreinte prise avec un autre instrument
#: n'est pas comparable.
#:
#: ⚠ MESURE DU 2026-08-10 : ajouter `.pytest_cache` aux exclusions de `declencheur_trace` a
#: change deux groupes de l'empreinte SANS perimer une seule entree (ni le source d'un cliquet ni
#: sa fermeture ne bougeaient), et `--incremental` les aurait servies telles quelles. Un
#: instrument qui change en silence est la meme faute qu'un helper partage qui change en silence
#: -- un cran plus haut.
INSTRUMENT = ("declencheur_trace.py",)


def sha_instrument() -> str:
    parts = []
    for s in INSTRUMENT:
        c = cle_source_et_fermeture(s)
        parts.append("%s\0%s\0%s" % (s, c[0], c[1]))
    return verdict_cache.sha_texte("\n".join(parts))


def cle_source_et_fermeture(script: str) -> tuple:
    """Les DEUX composantes propres a un script. Separee de `cle_fraicheur` pour que
    `sha_instrument` puisse l'appeler sans recursion."""
    return (sha_source(script), sha_fermeture(script))


def cle_fraicheur(script: str) -> tuple:
    """FOYER UNIQUE de << cette empreinte est-elle encore valable ? >>.

    Il sert DEUX lecteurs, et c'est le point : l'etage 2, qui refuse de SERVIR une empreinte
    perimee, et `--incremental`, qui decide laquelle REMESURER. Deriver ces deux decisions du
    meme critere est ce qui rend l'acceleration incapable de changer un verdict -- le mode
    rapide remesure EXACTEMENT ce que l'etage 2 aurait de toute facon refuse de servir. Deux
    criteres ouvriraient l'ecart que #486 combat : un mode rapide qui sert ce que le garde
    aurait rejete est un faux vert.

    TROIS composantes, et chacune ferme un trou MESURE :
      * le SOURCE du cliquet (d'origine) ;
      * sa FERMETURE d'imports -- un helper partage qui change (#486-r36) ;
      * l'INSTRUMENT -- ce que la mesure VOIT (#486-r36, meme tranche).
    """
    c = cle_source_et_fermeture(script)
    return (c[0], c[1], sha_instrument())


#: Le libelle de CHAQUE composante, dans l'ordre du tuple. Rendre la cause plutot qu'un booleen,
#: pour la meme raison que `DC.couvre` rend le glob : un garde qui ne dit pas POURQUOI il refuse
#: se degrade en bruit qu'on finit par ignorer.
CAUSES = ("source du cliquet", "fermeture d'imports", "instrument de mesure")
CHAMPS = ("sha", "ferm", "inst")


def est_perimee(e, cle: tuple) -> bool:
    """`e` = l'entree d'empreinte chargee, `cle` = `cle_fraicheur` du script courant."""
    return cause_de_peremption(e, cle) is not None


def cause_de_peremption(e, cle: tuple):
    """Le LIBELLE de la premiere composante qui ne correspond plus, ou `None`."""
    if e is None:
        return "absente"
    for champ, attendu, libelle in zip(CHAMPS, cle, CAUSES):
        if (e.get(champ) or "") != attendu:
            return libelle
    return None


#: Les rc sous lesquels le cliquet DIT lui-meme n'avoir rien mesure -- meme table que la banque
#: (`scripts/ratchets-verdict.ps1`) : 99 = INDISPONIBLE, 64 = erreur d'USAGE. `-1` est notre
#: propre sentinelle de TIMEOUT.
#:
#: ⚠ CE CRAN EXISTE PARCE QU'UNE MESURE PEUT ETRE UN REFUS, ET LE REFUS AVAIT L'AIR D'UNE MESURE
#: (#486-r36). Mesure du 2026-08-10 : les HUIT shards `probe_457:s*` rendent `rc=99` en ~1,2 s --
#: `probe_457` REFUSE de courir sans `TACTICUS_ALLOW_RATCHETS=1` (garde anti-reflexe posee le
#: 2026-08-06, parce qu'un run complet coute ~1 425 s). Leur empreinte portait donc **5
#: lectures** (son propre source et ses imports immediats), trivialement couvertes par n'importe
#: quel glob : 8 des 49 entrees se declaraient CONFRONTEES en n'ayant rien confronte. Le garde
#: `nproc == 0` ne pouvait pas les voir -- le process a bel et bien tourne et trace : il a trace
#: son refus.
#:
#: LA SORTIE EST DANS L'ENVIRONNEMENT DE L'APPELANT, et c'est deliberement a lui de la prendre :
#: `mesurer` herite de `os.environ`, donc
#:     $env:TACTICUS_ALLOW_RATCHETS=1 ; python probe_486r12_declencheurs.py --mesurer --only probe_457
#: les mesure pour de vrai. On ne pose PAS la variable ici : ce serait decider a la place de
#: l'appelant de jouer ~1 425 s de tests, exactement ce que le refus de `probe_457` empeche.
RC_SANS_MESURE = (64, 99)


def mesure_refusee(e) -> bool:
    """Le run a-t-il DIT n'avoir rien mesure ? Alors sa trace ne vaut pas un perimetre."""
    rc = (e or {}).get("rc") or 0
    return rc in RC_SANS_MESURE or rc < 0


def a_remesurer(ids, bq: dict, emp) -> tuple[list, list]:
    """(a remesurer, servies par l'empreinte) -- LE MEME critere que l'etage 2, pas un second.

    Une entree est SERVIE si et seulement si l'etage 2 accepterait son empreinte : presente,
    fraiche (`est_perimee`), et non VIDE de mesure (`nproc == 0` = un run qui n'a rien trace,
    que l'etage 2 compte deja comme ABSENTE -- le servir ici fabriquerait un vert que le garde
    refuse par ailleurs). Tout le reste est remesure.

    ⚠ C'EST LA SEULE FORME QUI NE PEUT PAS CHANGER UN VERDICT. Un mode rapide qui deciderait par
    un critere a lui -- un age, un diff, une liste -- pourrait servir ce que l'etage 2 aurait
    rejete : le rc passerait de 99 a 0 par le fait d'avoir saute des entrees, ce que le tri-etat
    interdit explicitement.
    """
    servies, reste = [], []
    for i in ids:
        s = script_de(bq[i]) or ""
        e = emp.par_id.get(i)
        if (e is not None and not est_perimee(e, cle_fraicheur(s)) and e.get("nproc")
                and not mesure_refusee(e)):
            servies.append(i)
        else:
            reste.append(i)
    return reste, servies


# ============================================================== mesure
def mesurer(ids: list, bq: dict, verbose: bool, parallelisme: int = 1) -> tuple[Empreinte, dict]:
    """Joue les cliquets demandes sous audit hook. Rend (empreinte, durees par entree).

    LE PARALLELISME N'EST PAS UN PARI (#486-r36). `scripts/ratchets.ps1` joue DEJA cette meme
    banque en parallele -- `-ThrottleLimit 0` vaut `min(nb de cliquets, nb de coeurs)` -- et sa
    documentation en donne la raison : les cliquets sont 100 % OFFLINE (aucun runner, aucun RPC,
    aucune session Frida), donc le plafond de 4 du `CLAUDE.md`, qui borne ce qui MONTE UN RUNNER,
    ne les concerne pas. Ce qui est neuf ici, c'est seulement que la MESURE emprunte la meme voie
    que la banque qu'elle mesure.

    Ce que le parallelisme ne doit PAS perturber, et ne perturbe pas :
      * la TRACE -- chaque entree a son propre dossier (`base / ident`) passe par
        `TACTICUS_DECLENCHEUR_TRACE`, et chaque process y ecrit un fichier a SON pid. Deux
        entrees ne peuvent donc pas melanger leurs lectures ;
      * le `sitecustomize.py` -- ecrit UNE fois, avant le pool, et lu seulement ;
      * la DUREE -- elle porte alors la contention des voisines, ce que le regime ecrit DIT.
        Une distribution ne se derive que d'une passe `serie`.
    """
    e = Empreinte()
    e.commit = _tete()
    durees: dict = {}
    regime = REGIME_ISOLE if parallelisme <= 1 else "para-%d" % parallelisme
    base = Path(tempfile.mkdtemp(prefix="declencheur-mesure-"))
    site = base / "site"
    # UNE seule preparation : `preparer` ecrit le `sitecustomize.py` partage et rend
    # l'environnement. L'appeler par entree depuis N threads ferait N ecritures concurrentes du
    # meme fichier -- inutile, et sous Windows une ecriture peut alors echouer sur un verrou.
    env_base = DT.preparer(base / "_ignore", site, str(ROOT))

    def _une(ident: str) -> tuple:
        argv = bq[ident]
        dossier = base / ident.replace(":", "_")
        env = dict(env_base)
        env[DT.ENV_TRACE] = str(dossier)
        t0 = time.time()
        try:
            r = subprocess.run([sys.executable] + list(argv), cwd=str(PYDIR), env=env,
                               capture_output=True, text=True, timeout=TIMEOUT)
            rc = r.returncode
        except subprocess.TimeoutExpired:
            rc = -1
        return ident, rc, time.time() - t0, DT.fusionner(dossier)

    def _flux():
        """Les resultats AU FIL DE L'EAU. `as_completed` et non `pool.map` : `map` ne rend rien
        avant que TOUT soit fini, donc une passe de plusieurs minutes n'affichait pas une ligne.
        L'ordre de sortie devient celui des completions -- sans consequence, l'empreinte etant
        triee a l'ecriture."""
        if parallelisme <= 1:
            for i in ids:
                yield _une(i)
            return
        with ThreadPoolExecutor(max_workers=parallelisme) as pool:
            for f in as_completed([pool.submit(_une, i) for i in ids]):
                yield f.result()

    try:
        for ident, rc, dt, (lectures, programmes, nproc) in _flux():
            script = script_de(bq[ident])
            cle = cle_fraicheur(script)
            e.par_id[ident] = {"sha": cle[0], "ferm": cle[1], "inst": cle[2], "rc": rc,
                               "lu": grouper(lectures),
                               "proc": sorted(programmes & set(DT.OPAQUES)), "nproc": nproc}
            durees[ident] = {"s": round(dt, 2), "rc": rc, "commit": e.commit[:12]}
            print("  [mesure] %-22s rc=%-4s %5.1f s  %5d lecture(s)  %d process%s"
                  % (ident, rc, dt, len(lectures), nproc,
                     ("  opaques: " + ",".join(DT.opaques(programmes))) if DT.opaques(programmes)
                     else ""))
            if verbose:
                for g in e.par_id[ident]["lu"][:20]:
                    print("            %s/*%s  x%d" % (g[0] or ".", g[1], g[2]))
    finally:
        shutil.rmtree(base, ignore_errors=True)
    return e, durees


# ============================================================== durees : lecture / ecriture
#: Le regime dont la duree est un COUT ISOLE. Les autres portent la contention de leurs voisines.
REGIME_ISOLE = "serie"


def charger_durees(chemin=None) -> dict:
    """`{ident: {regime: {"s": float, "rc": int, "commit": str}}}`, ou `{}`.

    ⚠ KEYE PAR REGIME, ET C'EST UNE FAUTE PAYEE SUR CE PROPRE ARTEFACT (#486-r36). La premiere
    version ecrivait une seule mesure par entree : la passe `para-16` a donc ECRASE la
    distribution `serie` -- c'est-a-dire la SEULE interpretable, et le livrable meme de la
    tranche. Un fichier qui ne garde qu'une valeur par entree ne peut pas porter deux regimes,
    et le regime ecrit a cote ne suffit pas : il DIT quelle mesure on a, pas celle qu'on a
    perdue.

    JAMAIS fatal : une mesure de COUT ne doit pas pouvoir faire echouer un garde de FIDELITE.
    Un fichier illisible rend `{}` -- la passe suivante le reecrira."""
    p = Path(chemin or DUREES)
    if not p.is_file():
        return {}
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return (d.get("durees") or {}) if isinstance(d, dict) else {}


def fusionner_durees(anciennes: dict, neuves: dict, regime: str) -> dict:
    """Pose `neuves` SOUS `regime`, sans toucher aux autres regimes de la meme entree."""
    out = {i: dict(r) for i, r in anciennes.items()}
    for ident, mesure in neuves.items():
        out.setdefault(ident, {})[regime] = mesure
    return out


def ecrire_durees(durees: dict, chemin=None) -> None:
    p = Path(chemin or DUREES)
    ordonne = {i: {r: durees[i][r] for r in sorted(durees[i])} for i in sorted(durees)}
    p.write_text(json.dumps({"format": FORMAT_DUREES, "regime_isole": REGIME_ISOLE,
                             "durees": ordonne}, indent=1, sort_keys=False) + "\n",
                 encoding="utf-8")


def publier_distribution(durees: dict, joues: list, regime: str | None = None) -> None:
    """Total, mediane, les 5 plus lourdes et leur part CUMULEE -- sur les entrees JOUEES.

    ⚠ La part cumulee est ce qui TRANCHE entre les deux accelerations, et c'est pour ca qu'elle
    est imprimee plutot que laissee a deriver : concentree, seul l'incremental paye ; plate, seul
    le parallelisme paye. Un total sans sa forme ne decide rien.

    Le regime par defaut est `serie` -- le seul cout ISOLE. Une distribution derivee d'une passe
    parallele melangerait le cout d'une entree et la contention de ses voisines.
    """
    reg = regime or REGIME_ISOLE
    vus = [(i, durees[i][reg]["s"]) for i in joues
           if i in durees and reg in durees[i]]
    if not vus:
        print("\n  -- DISTRIBUTION : rien en regime `%s` pour cette selection. Jouer "
              "`--mesurer` SANS `--jobs` pour un cout isole. --" % reg)
        return
    total = sum(s for _, s in vus)
    vals = sorted(s for _, s in vus)
    lourdes = sorted(vus, key=lambda t: -t[1])
    manquantes = [i for i in joues if i not in durees or reg not in durees[i]]
    print("\n  -- DISTRIBUTION DU COUT (%d entree(s), regime %s%s) --"
          % (len(vus), reg,
             ", %d SANS mesure dans ce regime" % len(manquantes) if manquantes else ""))
    print("     total %.1f s | mediane %.1f s | min %.1f s | max %.1f s"
          % (total, statistics.median(vals), vals[0], vals[-1]))
    cumul = 0.0
    for rang, (ident, s) in enumerate(lourdes[:5], 1):
        cumul += s
        print("     %d. %-24s %6.1f s  (%4.1f %% ; cumul %4.1f %%)"
              % (rang, ident, s, 100.0 * s / total if total else 0.0,
                 100.0 * cumul / total if total else 0.0))
    print("     les 5 plus lourdes pesent %.1f s sur %.1f s" % (cumul, total))


def _tete() -> str:
    try:
        r = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                           capture_output=True, text=True, timeout=20)
        return r.stdout.strip() if r.returncode == 0 else "?"
    except (OSError, subprocess.SubprocessError):
        return "?"


# ============================================================== etage 1 : la declaration
def etage_declaration(scripts: dict) -> tuple[int, dict, dict]:
    """Rend (nb de rouges, {script: declencheur}, {script: declencheur_par_entree}).

    Un script sans `DECLENCHEUR` est ROUGE ; un `DECLENCHEUR_PAR_ENTREE` mal forme ou portant
    une cle MORTE (aucune entree de banque de ce script) l'est aussi."""
    print("== [1] DECLARATION -- perimetre DERIVE de scripts/ratchets.ps1 ==")
    ok: dict = {}
    fins: dict = {}
    absents, malformes = [], []
    for script in sorted(scripts):
        p = PYDIR / script
        if not p.is_file():
            malformes.append((script, ["source introuvable : %s" % p]))
            continue
        try:
            d = DC.lire(p)
        except DC.DeclencheurAbsent as exc:
            absents.append((script, str(exc)))
            continue
        fautes = DC.valider(d)
        try:
            fin = DC.lire_par_entree(p)
        except DC.DeclencheurAbsent as exc:
            fautes = fautes + [str(exc)]
            fin = {}
        fautes = fautes + DC.valider_par_entree(fin, scripts[script])
        if fautes:
            malformes.append((script, fautes))
            continue
        ok[script] = d
        fins[script] = fin

    total = len(scripts)
    print("  scripts de la banque      : %d" % total)
    print("  avec DECLENCHEUR valide   : %d" % len(ok))
    print("  SANS declaration          : %d" % len(absents))
    print("  declaration MAL FORMEE    : %d" % len(malformes))
    borne = [s for s, d in ok.items() if not d.get("toujours")]
    print("  dont BORNES (toujours=0)  : %d" % len(borne))
    n_fines = sum(len(f) for f in fins.values())
    n_entrees = sum(len(v) for v in scripts.values())
    print("  entrees de banque         : %d, dont %d AFFINEES (DECLENCHEUR_PAR_ENTREE)"
          % (n_entrees, n_fines))

    # INFORMATIF (cf. `declencheur_cliquet.hors_de_l_union`) : le declencheur de FICHIER
    # pretend etre l'union de ses entrees, et il sert de repli a toute entree neuve.
    ecarts = [(s, i, g) for s in sorted(fins)
              for i, g in DC.hors_de_l_union(ok[s], fins[s])]
    if ecarts:
        print("  [info] glob(s) d'une entree HORS de l'union declaree par le fichier : %d"
              % len(ecarts))
        for script, ident, g in ecarts[:6]:
            print("      %-46s %-22s %r" % (script.rsplit("/", 1)[-1], ident, g))

    # INFORMATIF, jamais un rc (cf. `declencheur_cliquet.redondants`) : un glob integralement
    # couvert par un autre de la MEME declaration. Trace d'hesitation sur la semantique de
    # `**/`, pas une faute -- l'union est identique et rougir punirait un declarant prudent.
    redond = [(s, r) for s in sorted(ok) for r in DC.redondants(ok[s])]
    if redond:
        print("  [info] globs REDONDANTS (couverts par un autre de la meme declaration) : %d"
              % len(redond))
        for script, (couvert, couvrant) in redond[:6]:
            print("      %-46s %r  <=  %r" % (script.rsplit("/", 1)[-1], couvert, couvrant))
        if len(redond) > 6:
            print("      ... et %d autre(s)" % (len(redond) - 6))

    ko = 0
    if absents:
        ko += len(absents)
        print("\n  ROUGE -- %d script(s) de la banque sans `DECLENCHEUR` :" % len(absents))
        for script, msg in absents:
            print("      %s" % msg)
        print("      => poser la constante au niveau module (contrat : declencheur_cliquet.py).")
        print("         Le DEFAUT est `toujours: True` avec sa raison -- c'est un RESULTAT,")
        print("         jamais un echec. Un declencheur trop LARGE est sain ; trop ETROIT est")
        print("         un faux vert.")
    if malformes:
        ko += len(malformes)
        print("\n  ROUGE -- %d declaration(s) MAL FORMEE(s) :" % len(malformes))
        for script, fautes in malformes:
            print("      %s" % script)
            for f in fautes:
                print("          %s" % f)
    return ko, ok, fins


# ============================================================== etage 2 : la mesure
def etage_mesure(scripts: dict, decl: dict, fins: dict, emp: Empreinte,
                 verbose: bool) -> tuple[int, int]:
    """Rend (nb de rouges, nb d'entrees NON MESUREES).

    La confrontation est PAR ENTREE des deux cotes depuis #486-r19 : l'empreinte l'etait deja,
    la declaration peut l'etre. Une entree qui ne s'affine pas est jugee contre le declencheur
    du FICHIER, comme avant."""
    print("\n== [2] MESURE -- ce que le cliquet OUVRE vraiment, confronte a ce qu'il DECLARE ==")
    print("  empreinte : %s (commit=%s, %d entree(s))"
          % (EMPREINTE.relative_to(ROOT).as_posix(), emp.commit[:12], len(emp.par_id)))

    ko = non_mesure = 0
    fautes: list = []
    incompletes: list = []
    perimees: list = []
    absentes: list = []
    refusees: list = []
    bypass: list = []
    morts: list = []
    a_risque: list = []
    risque_non_mesure: list = []
    confrontes = 0

    for script in sorted(scripts):
        d = decl.get(script)
        if d is None:
            continue                              # deja rouge a l'etage 1, ne pas compter deux fois
        cle = cle_fraicheur(script)
        fin = fins.get(script) or {}
        for ident in sorted(scripts[script]):
            d_eff = DC.resoudre(d, fin, ident)
            globs = DC.perimetre(d_eff, source_rel=("scripts/python/" + script))
            e = emp.par_id.get(ident)
            if e is None:
                absentes.append(ident)
                non_mesure += 1
                continue
            cause = cause_de_peremption(e, cle)
            if cause is not None:
                perimees.append("%s (%s)" % (ident, cause))
                non_mesure += 1
                continue
            if e["nproc"] == 0:
                # Un run qui n'a trace AUCUN process n'a rien mesure : le compter comme une
                # confrontation reussie serait un vert fabrique.
                absentes.append(ident + " (0 process trace)")
                non_mesure += 1
                continue
            if mesure_refusee(e):
                # Le cliquet a DIT n'avoir rien mesure (cf. `RC_SANS_MESURE`). Sa trace est
                # alors celle de son REFUS -- quelques lectures que n'importe quel glob couvre.
                refusees.append((ident, e.get("rc")))
                non_mesure += 1
                continue
            if e["proc"]:
                incompletes.append((ident, e["proc"]))
            confrontes += 1
            if d_eff.get("toujours"):
                continue                          # rien a confronter : il se rejoue TOUJOURS
            hors = []
            for dossier, ext, n, t_min, t_max in e["lu"]:
                for temoin in {t_min, t_max}:
                    if not temoin:
                        continue
                    if DC.couvre(globs, temoin) is None:
                        hors.append((temoin, n))
                        break
            #: #486-r16 (a) -- l'AMPLITUDE de l'approximation d'agregation, mesuree et publiee.
            #: Ce n'est PAS un gate (c'est une majoration, cf. `groupes_a_risque`) : c'est le
            #: refus de laisser une approximation TACITE. Un compte filtre dit ce qu'il filtre.
            try:
                r = groupes_a_risque(e, globs)
            except (OSError, subprocess.SubprocessError) as ex:         # noqa: BLE001
                risque_non_mesure.append("%s (%s)" % (ident, str(ex)[:60]))
            else:
                if r:
                    a_risque.append((ident, r))
            # LE BYPASS (#486-r24), meme contrat que cote tests. Il DESARME la confrontation de
            # cette entree, jamais l'obligation de declarer -- et il est MESURE : un bypass qui
            # ne masque RIEN est une declaration morte, donc un rouge. Sans ce cran, la cle
            # deviendrait l'echappatoire universelle qu'elle remplace.
            motif = DC.hors_confrontation(d_eff)
            if motif is not None:
                bypass.append((ident, motif, len(hors)))
                if not hors:
                    morts.append((ident, script))
                continue
            if hors:
                fautes.append((ident, script, globs, sorted(set(hors))))

    print("  entrees de banque confrontees : %d" % confrontes)
    print("  NON MESUREES                  : %d (absente %d, perimee %d, mesure REFUSEE %d)"
          % (non_mesure, len(absentes), len(perimees), len(refusees)))
    if refusees:
        print("  MESURE REFUSEE PAR LE CLIQUET LUI-MEME (rc dans %s) : %d -- sa trace est celle "
              "de son REFUS," % (RC_SANS_MESURE, len(refusees)))
        print("  donc trivialement couverte. Ce n'est PAS un verdict sur sa declaration.")
        for ident, rc in refusees:
            print("      %-22s rc=%s" % (ident, rc))
        print("      => si tu veux les mesurer, pose la variable que LE CLIQUET exige, puis")
        print("         `--mesurer --only <id>`. On ne la pose pas d'office : elle engage un")
        print("         cout que seul l'appelant peut arbitrer.")
    if incompletes:
        print("  MESURE INCOMPLETE (sous-process opaque, hors de portee du hook) : %d"
              % len(incompletes))
        for ident, progs in incompletes:
            print("      %-22s lance %s" % (ident, ",".join(progs)))
    if verbose or absentes:
        for a in absentes:
            print("      ABSENTE de l'empreinte : %s" % a)
    if verbose or perimees:
        for p in perimees:
            print("      PERIMEE (ce que le cliquet LIT a pu changer depuis la mesure) : %s" % p)

    # ---------------------------------------------------------------- #486-r16 (a) : INVENTAIRE
    # L'agregation par (dossier, extension) ne confronte que DEUX temoins par groupe. Ce compte
    # dit combien de groupes POURRAIENT masquer une lecture hors perimetre -- une MAJORATION,
    # donc un inventaire, jamais un gate (cf. `groupes_a_risque`). Il est imprime MEME a zero :
    # un compte qu'on ne voit qu'en cas de probleme ne permet pas de constater qu'il a bouge.
    if risque_non_mesure:
        print("  AGREGATION -- amplitude NON MESUREE sur %d entree(s) : %s"
              % (len(risque_non_mesure), "; ".join(risque_non_mesure[:3])))
    print("  AGREGATION (#486-r16) -- groupes ou les DEUX temoins passent alors qu'un chemin")
    print("  VERSIONNE du meme groupe ne passerait pas : %d, sur %d entree(s)"
          % (sum(len(r) for _, r in a_risque), len(a_risque)))
    if a_risque:
        print("      MAJORATION : le cliquet n'a lu que `n` fichiers du groupe, rien ne dit que")
        print("      le chemin exhibe en fasse partie. Ce n'est donc PAS un rouge -- et l'elargir")
        print("      en gate ferait elargir les declencheurs, c'est-a-dire MASQUER le trou.")
        for ident, r in sorted(a_risque)[:8]:
            for dossier, ext, n, nrates, ex in r[:2]:
                print("      %-22s %s/*%s (groupe de %d) -- %d chemin(s) non couverts, ex. %s"
                      % (ident, dossier, ext, n, nrates, ex))

    if bypass:
        print("  HORS CONFRONTATION (bypass declare et motive, #486-r24) : %d" % len(bypass))
        for ident, motif, n in sorted(bypass, key=lambda t: (-t[2], t[0])):
            print("      %-22s masque %3d temoin(s) -- %s" % (ident, n, motif[:88]))
    if morts:
        ko += len(morts)
        print("\n  ROUGE -- %d bypass qui NE MASQUENT RIEN (la confrontation passe sans eux) :"
              % len(morts))
        for ident, script in morts:
            print("      %s (%s) -- declaration MORTE, retirer `%s`."
                  % (ident, script, DC.CLE_HORS_CONFRONTATION))

    if fautes:
        # `+=` et JAMAIS `=` : les bypass MORTS comptent deja dans `ko`, et une affectation
        # seche les effacerait -- un rouge qui en avale un autre est un faux vert partiel.
        ko += len(fautes)
        print("\n  ROUGE -- %d cliquet(s) LISENT hors de leur perimetre DECLARE :" % len(fautes))
        for ident, script, globs, hors in fautes:
            print("      %s (%s)" % (ident, script))
            print("          declare : %s" % ", ".join(globs))
            for temoin, n in hors[:8]:
                print("          LU hors perimetre : %s   (groupe de %d fichier(s))" % (temoin, n))
            if len(hors) > 8:
                print("          ... et %d autre(s) groupe(s)" % (len(hors) - 8))
        print("      => ELARGIR le declencheur (jamais retrecir la mesure). Un declencheur trop")
        print("         ETROIT ne fait pas jouer le cliquet quand son gisement se rouvre.")
    return ko, non_mesure


# ============================================================== main
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--mesurer", action="store_true",
                    help="(re)joue les cliquets sous audit hook et REECRIT l'empreinte")
    ap.add_argument("--only", default="",
                    help="CSV d'ids de banque (prefixe accepte) -- borne la MESURE")
    ap.add_argument("--jobs", type=int, default=1, metavar="N",
                    help="entrees mesurees EN PARALLELE (defaut 1 = serie). Les cliquets sont "
                         "100 pourcent offline (cf. ratchets.ps1 -ThrottleLimit), donc le "
                         "plafond de 4 du CLAUDE.md, qui borne ce qui MONTE UN RUNNER, ne les "
                         "concerne pas. ATTENTION : sous N > 1 les DUREES portent la contention, "
                         "sont ecrites avec leur regime, et une distribution ne se derive que "
                         "d'une passe `serie`.")
    ap.add_argument("--incremental", action="store_true",
                    help="ne (re)mesure que les entrees que l'etage 2 REFUSERAIT de servir : "
                         "absentes, PERIMEES au sens de `cle_fraicheur` (source du cliquet, "
                         "fermeture de ses imports, ou instrument de mesure), ou dont le run "
                         "avait DIT n'avoir rien mesure. Les autres restent attestees par leur "
                         "empreinte -- jamais supposees vertes. Ne dispense PAS d'une passe "
                         "complete : cf. `sha_fermeture` pour les deux trous qu'il laisse.")
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()

    try:
        bq = banque()
    except Exception as exc:                                           # noqa: BLE001
        print("[486r12] INDISPONIBLE -- la banque n'est pas derivable : %s: %s"
              % (type(exc).__name__, exc))
        print("[486r12] rc=99 -- RIEN n'a ete mesure. Ce n'est PAS un verdict sur le depot.")
        return 99

    scripts = par_script(bq)
    print("[486r12] banque : %d entree(s), %d script(s) distinct(s)" % (len(bq), len(scripts)))

    if a.mesurer:
        vise = [m.strip() for m in a.only.split(",") if m.strip()]
        # Meme regle de prefixe que `ratchets.ps1 -Only` : l'id EXACT, ou ses etapes/shards
        # (`probe_283` -> `probe_283:prose`). Jamais un prefixe libre -- `probe_43` prendrait
        # `probe_433`, `probe_437` et `probe_439`, trois cliquets sans rapport.
        ids = sorted(i for i in bq
                     if not vise or any(i == v or i.startswith(v + ":") for v in vise))
        if not ids:
            print("[486r12] rc=99 -- `--only %s` ne selectionne aucune entree." % a.only)
            return 99
        # La SELECTION demandee, avant toute reduction incrementale : la distribution porte sur
        # elle, pas sur ce qui a ete rejoue. Un `--incremental` qui ne publierait que ses 1 ou 2
        # entrees rendrait une << distribution >> qui ne decrit rien.
        selection = list(ids)
        if a.incremental:
            ids, servies = a_remesurer(ids, bq, Empreinte.charger())
            print("[486r12] INCREMENTAL : %d entree(s) SERVIES par l'empreinte (fraiches, et "
                  "toujours CONFRONTEES a l'etage 2), %d a remesurer." % (len(servies), len(ids)))
            if not ids:
                print("[486r12] rien a remesurer -- l'empreinte est a jour pour cette selection.")
        print("[486r12] MESURE de %d entree(s) ..." % len(ids))
        neuf, durees_neuves = mesurer(ids, bq, a.verbose, parallelisme=max(1, a.jobs))
        # Mesure INCREMENTALE : on ne perd jamais ce qu'on n'a pas rejoue.
        ancien = Empreinte.charger()
        ancien.par_id.update(neuf.par_id)
        ancien.commit = neuf.commit
        ancien.ecrire()
        print("[486r12] empreinte ecrite : %s (%d entree(s))"
              % (EMPREINTE.relative_to(ROOT).as_posix(), len(ancien.par_id)))
        regime = REGIME_ISOLE if max(1, a.jobs) <= 1 else "para-%d" % max(1, a.jobs)
        toutes = fusionner_durees(charger_durees(), durees_neuves, regime)
        ecrire_durees(toutes)
        print("[486r12] durees ecrites   : %s (%d entree(s), regime %s)"
              % (DUREES.relative_to(ROOT).as_posix(), len(toutes), regime))
        publier_distribution(toutes, selection)
        if regime != REGIME_ISOLE:
            publier_distribution(toutes, selection, regime)

    ko1, decl, fins = etage_declaration(scripts)
    ko2, non_mesure = etage_mesure(scripts, decl, fins, Empreinte.charger(), a.verbose)

    ko = ko1 + ko2
    print("")
    if ko:
        print("[486r12] ROUGE -- %d faute(s) (%d de declaration, %d de fidelite)."
              % (ko, ko1, ko2))
        return 1
    if non_mesure:
        print("[486r12] INDISPONIBLE -- 0 rouge, mais %d entree(s) NON MESUREE(S)." % non_mesure)
        print("[486r12] rc=99 -- rejouer `--mesurer` (eventuellement `--only <id>`).")
        return 99
    print("[486r12] OK -- %d script(s) declarent, et aucun ne lit hors de son perimetre."
          % len(decl))
    return 0


if __name__ == "__main__":
    sys.exit(main())
