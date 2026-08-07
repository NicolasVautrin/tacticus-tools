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
`scripts/declencheurs-empreinte.tsv` porte, par entree de banque, le SHA du source du cliquet au
moment de la mesure. Si le source a bouge depuis, l'entree n'est pas SERVIE -- elle est declaree
PERIMEE, donc NON MESUREE. C'est la regle de `verdict_cache` (#486-r1) : une attestation qui ne
peut que manquer ne peut pas mentir. Le mode `--mesurer` la reconstruit.

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

Usage :
    python probe_486r12_declencheurs.py                 # les deux etages
    python probe_486r12_declencheurs.py --mesurer       # (re)mesure TOUTE la banque, puis ecrit
    python probe_486r12_declencheurs.py --mesurer --only probe_181,probe_313
    python probe_486r12_declencheurs.py --verbose

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
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
FORMAT = "1"

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
    """`{id: {"sha": str, "lu": [(dossier, ext, n, t_min, t_max)], "proc": [..], "nproc": int}}`.

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
            d = e.par_id.setdefault(ident, {"sha": "", "lu": [], "proc": [], "nproc": 0})
            if kind == "sha":
                d["sha"] = ch[2]
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
            lignes.append("%s\tnproc\t%d" % (ident, d["nproc"]))
            for prog in sorted(set(d["proc"])):
                lignes.append("%s\tproc\t%s" % (ident, prog))
            for grp in sorted(d["lu"]):
                lignes.append("%s\tlu\t%s\t%s\t%d\t%s\t%s" % (ident, grp[0], grp[1], grp[2],
                                                              grp[3], grp[4]))
        Path(chemin or EMPREINTE).write_text("\n".join(lignes) + "\n", encoding="utf-8")


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


# ============================================================== mesure
def mesurer(ids: list, bq: dict, verbose: bool) -> Empreinte:
    """Joue les cliquets demandes sous audit hook et rend l'empreinte correspondante."""
    e = Empreinte()
    e.commit = _tete()
    base = Path(tempfile.mkdtemp(prefix="declencheur-mesure-"))
    site = base / "site"
    try:
        for ident in ids:
            argv = bq[ident]
            script = script_de(argv)
            dossier = base / ident.replace(":", "_")
            env = DT.preparer(dossier, site, str(ROOT))
            t0 = time.time()
            try:
                r = subprocess.run([sys.executable] + list(argv), cwd=str(PYDIR), env=env,
                                   capture_output=True, text=True, timeout=TIMEOUT)
                rc = r.returncode
            except subprocess.TimeoutExpired:
                rc = -1
            lectures, programmes, nproc = DT.fusionner(dossier)
            e.par_id[ident] = {"sha": sha_source(script), "lu": grouper(lectures),
                               "proc": sorted(programmes & set(DT.OPAQUES)), "nproc": nproc}
            print("  [mesure] %-22s rc=%-4s %5.1f s  %5d lecture(s)  %d process%s"
                  % (ident, rc, time.time() - t0, len(lectures), nproc,
                     ("  opaques: " + ",".join(DT.opaques(programmes))) if DT.opaques(programmes)
                     else ""))
            if verbose:
                for g in e.par_id[ident]["lu"][:20]:
                    print("            %s/*%s  x%d" % (g[0] or ".", g[1], g[2]))
    finally:
        shutil.rmtree(base, ignore_errors=True)
    return e


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
    confrontes = 0

    for script in sorted(scripts):
        d = decl.get(script)
        if d is None:
            continue                              # deja rouge a l'etage 1, ne pas compter deux fois
        sha = sha_source(script)
        fin = fins.get(script) or {}
        for ident in sorted(scripts[script]):
            d_eff = DC.resoudre(d, fin, ident)
            globs = DC.perimetre(d_eff, source_rel=("scripts/python/" + script))
            e = emp.par_id.get(ident)
            if e is None:
                absentes.append(ident)
                non_mesure += 1
                continue
            if e["sha"] != sha:
                perimees.append(ident)
                non_mesure += 1
                continue
            if e["nproc"] == 0:
                # Un run qui n'a trace AUCUN process n'a rien mesure : le compter comme une
                # confrontation reussie serait un vert fabrique.
                absentes.append(ident + " (0 process trace)")
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
            if hors:
                fautes.append((ident, script, globs, sorted(set(hors))))

    print("  entrees de banque confrontees : %d" % confrontes)
    print("  NON MESUREES                  : %d (absente %d, perimee %d)"
          % (non_mesure, len(absentes), len(perimees)))
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
            print("      PERIMEE (le source du cliquet a change depuis la mesure) : %s" % p)

    if fautes:
        ko = len(fautes)
        print("\n  ROUGE -- %d cliquet(s) LISENT hors de leur perimetre DECLARE :" % ko)
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
        print("[486r12] MESURE de %d entree(s) ..." % len(ids))
        neuf = mesurer(ids, bq, a.verbose)
        # Mesure INCREMENTALE : on ne perd jamais ce qu'on n'a pas rejoue.
        ancien = Empreinte.charger()
        ancien.par_id.update(neuf.par_id)
        ancien.commit = neuf.commit
        ancien.ecrire()
        print("[486r12] empreinte ecrite : %s (%d entree(s))"
              % (EMPREINTE.relative_to(ROOT).as_posix(), len(ancien.par_id)))

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
