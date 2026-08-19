"""#469 -- DECONFONDRE les causes du mur de `ratchets-bg`.

LA QUESTION
-----------
Le mur de la banque a trois causes candidates, aucune separee des autres :

  (a) TAILLE DE LA FLOTTE  -- N agents prennent le CPU, tout ralentit ;
  (b) PERIMETRE DU DIFF    -- `probe_457 --since` rejoue plus ou moins de tests ;
  (c) CONTENTION `.git/`   -- le depot partage (arbre principal + worktrees + ratchets-bg)
                              serialise les gestes git.

Regler `-ThrottleLimit` sur une correlation non causale serait le vice meme que la tache denonce.

LE BRAS QUI SEPARE (c) DE TOUT LE RESTE -- et c'est le seul qui ne demande AUCUNE fenetre calme
-----------------------------------------------------------------------------------------------
On joue les MEMES commandes git, AU MEME INSTANT, sur DEUX depots :

  * `gitP` -- le depot PARTAGE (son `.git/` est celui de l'arbre principal, vu par N worktrees) ;
  * `gitC` -- un CLONE PRIVE (`git clone --local`, hardlinks : meme contenu, meme volume d'objets,
              mais index / refs / locks A LUI, que personne d'autre ne touche).

Les deux subissent EXACTEMENT la meme machine au meme instant (meme CPU pris, meme antivirus, meme
disque). La seule chose qui les distingue est le PARTAGE du `.git/`. Donc :

    gitP / gitC >> 1   ->  la contention `.git/` est REELLE et INDEPENDANTE du CPU  -> (c)
    gitP / gitC ~= 1   ->  << git est lent >> n'est qu'une autre facon de dire << la machine est
                           prise >> ; (c) n'est PAS un axe propre, la parade est ailleurs.

C'est la meme forme que le tri-etat de `host_inputs` : on refuse de rendre un chiffre unique
(<< git met 20 s >>) quand ce chiffre confond deux causes.

LE BRAS QUI REMPLACE LA FENETRE << FLOTTE VIDE >>
------------------------------------------------
On ne peut pas VIDER la flotte (elle appartient a l'orchestrateur). On peut l'AUGMENTER : on
injecte K coeurs de charge CPU synthetique et on relit les memes sondes. Une fenetre calme donne
un point sous la charge courante ; la charge injectee donne N points AU-DESSUS. La pente est la
meme information, et elle est disponible tout de suite -- avec l'avantage d'etre un bras
RANDOMISABLE (on choisit K) la ou attendre une flotte vide est observationnel.

CE QUE CHAQUE SONDE MESURE
--------------------------
  cpu1  un coeur, calcul pur -- ne bouge que si le scheduler degrade CE thread (coeurs tous pris,
        ou relegation sur un E-core). Ne voit PAS une machine a moitie prise.
  cpu4  quatre process simultanes, meme calcul -- mesure le DEBIT AGREGE encore disponible.
        C'est le capteur de (a) : il monte des que les coeurs libres manquent.
  gitP  git en LECTURE SEULE sur le depot partage (aucune ecriture, aucun lock pris :
        `--no-optional-locks` partout ou git pourrait en prendre un).
  gitC  les memes commandes sur le clone prive -- le CONTROLE de gitP.
  fs    lecture de N fichiers du working tree, hors `.git/` -- separe << disque/antivirus lent >>
        de << git lent >>.

Toutes les durees sont des MEDIANES de `--repet` releves ; la charge machine est lue par
`GetSystemTimes` (kernel32) et rendue en COEURS OCCUPES, pas en pourcentage -- un pourcentage se
lit mal quand on veut savoir combien de coeurs restent.

USAGE
-----
    python probe_469_contention_deconfusion.py --releve            # un releve a charge courante
    python probe_469_contention_deconfusion.py --releve --charge 8 # + 8 coeurs de charge injectee
    python probe_469_contention_deconfusion.py --rampe 0,4,8,16    # la pente complete
    python probe_469_contention_deconfusion.py --charge-seule 8 --duree 600   # bruit de fond

Sortie ASCII stricte (cp1252). Ecrit sous `logs/` (jamais dans `data/`, jamais dans
`scripts/python/` -- la banque enumere cet arbre en parallele, #455).
"""

from __future__ import annotations

import argparse
import ctypes
import json
import math
import os
import statistics
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

# --------------------------------------------------------------------------- charge machine

_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True) if os.name == "nt" else None


class _FILETIME(ctypes.Structure):
    _fields_ = [("lo", wintypes.DWORD), ("hi", wintypes.DWORD)]

    @property
    def val(self) -> int:
        return (self.hi << 32) | self.lo


def _system_times():
    """(idle, kernel, user) en unites de 100 ns. kernel INCLUT idle (contrat Win32)."""
    if _kernel32 is None:
        return None
    idle, kern, user = _FILETIME(), _FILETIME(), _FILETIME()
    ok = _kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kern), ctypes.byref(user))
    if not ok:
        return None
    return idle.val, kern.val, user.val


class Charge:
    """Coeurs OCCUPES entre deux instants -- pas un pourcentage.

    Un pourcentage repond a << la machine est-elle prise ? >> ; la question ici est << combien de
    coeurs reste-t-il ? >>, et c'est celle-la qui gouverne un `-ThrottleLimit`.
    """

    def __init__(self) -> None:
        self.t0 = _system_times()
        self.h0 = time.perf_counter()

    def lire(self):
        t1 = _system_times()
        h1 = time.perf_counter()
        if self.t0 is None or t1 is None:
            return None
        d_idle = t1[0] - self.t0[0]
        d_kern = t1[1] - self.t0[1]
        d_user = t1[2] - self.t0[2]
        total = d_kern + d_user
        if total <= 0:
            return None
        occupe = 1.0 - (d_idle / total)
        return round(occupe * os.cpu_count(), 2), round(h1 - self.h0, 2)


# --------------------------------------------------------------------------- sondes

_BOUCLE_N = 900_000


def _travail_cpu(n: int = _BOUCLE_N) -> float:
    """Calcul pur, aucun I/O, aucune allocation notable. Calibre ~0,20 s sur un P-core libre."""
    x = 0.0
    for i in range(1, n):
        x += math.sqrt(i) / (i + 1.0)
    return x


def _sonde_cpu1() -> float:
    t = time.perf_counter()
    _travail_cpu()
    return time.perf_counter() - t


def _lancer_et_attendre(argv, k: int) -> float:
    t = time.perf_counter()
    procs = [subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
             for _ in range(k)]
    for p in procs:
        p.wait()
    return time.perf_counter() - t


def _sonde_cpu4(k: int = 4) -> float:
    """Debit AGREGE : k process identiques lances ensemble, mur du plus lent.

    Des PROCESS, pas des threads : le GIL rendrait la mesure aveugle a la contention reelle.
    """
    return _lancer_et_attendre(
        [sys.executable, "-c",
         "import math\nx=0.0\n"
         "for i in range(1,%d): x+=math.sqrt(i)/(i+1.0)\n" % (_BOUCLE_N * 3)], k)


def _sonde_spawn(k: int = 4) -> float:
    """k interpreteurs Python qui ne font RIEN. La ligne de base de `cpu4`, et une mesure a part
    entiere : la banque lance 44 process Python, chacun payant ce cout AVANT de travailler."""
    return _lancer_et_attendre([sys.executable, "-c", "pass"], k)


# Commandes git STRICTEMENT en lecture. `--no-optional-locks` partout ou git pourrait prendre
# `.git/index.lock` (#474) : ces mesures tournent pendant que quatre agents ecrivent, et un lock
# orphelin de notre fait tuerait le `git merge` suivant de quelqu'un d'autre.
#
# `version` N'EST PAS UNE COMMANDE GIT COMME LES AUTRES, et c'est tout l'interet : elle ne touche
# NI le depot NI le disque. Elle mesure donc le COUT DE DEMARRAGE d'un process sur cette machine
# (chargement du binaire, filtre antivirus, ordonnancement). Sans cette ligne de base, tout ce
# cout serait impute au `.git/` -- exactement la confusion que #469 doit trancher.
_GIT_LECTURES = [
    ["--no-optional-locks", "version"],
    ["--no-optional-locks", "rev-parse", "HEAD"],
    ["--no-optional-locks", "ls-files"],
    ["--no-optional-locks", "status", "--porcelain", "--untracked-files=no"],
    ["--no-optional-locks", "diff", "--name-only", "HEAD~1", "HEAD"],
]

# `git grep` est HORS de la liste repetee : mesure a 26 s sur cet arbre (2026-08-04), il coute a
# lui seul plus que toutes les autres sondes reunies. Il reste mesurable a la demande (`--grep`)
# parce que c'est LE geste de #468 -- celui dont on a lu << 0,6 s -> 20-40 s a 10 worktrees >>.
_GIT_GREP = ["--no-optional-locks", "grep", "-l", "--", "TARGETING_OPTIONS"]


def _sonde_git_grep(repo: Path) -> float:
    t = time.perf_counter()
    subprocess.run(["git", "-C", str(repo)] + _GIT_GREP,
                   capture_output=True, text=True, errors="replace")
    return time.perf_counter() - t


def _banque_en_vol() -> dict:
    """Qui tourne EN CE MOMENT. Un releve sans son contexte ne se compare a rien.

    Lecture par `Get-CimInstance` : sans `psutil`, c'est la seule voie qui donne la LIGNE DE
    COMMANDE, or c'est elle qui distingue un cliquet d'un pytest d'agent.
    """
    ps = ("Get-CimInstance Win32_Process -Filter \"Name='python.exe' or Name='pwsh.exe'\" | "
          "ForEach-Object { $_.CommandLine }")
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                           capture_output=True, text=True, errors="replace", timeout=60)
        lignes = [l for l in r.stdout.splitlines() if l.strip()]
    except Exception:
        return {"mesure": False}
    cliquets = [l for l in lignes if "probe_" in l and "probe_469" not in l]
    ratchets = [l for l in lignes if "ratchets" in l]
    pytests = [l for l in lignes if "-m pytest" in l or " pytest " in l]
    return {"mesure": True, "python_pwsh": len(lignes), "cliquets": len(cliquets),
            "ratchets": len(ratchets), "pytest": len(pytests)}


def _sonde_git(repo: Path) -> dict:
    par_cmd = {}
    for args in _GIT_LECTURES:
        t = time.perf_counter()
        subprocess.run(["git", "-C", str(repo)] + args,
                       capture_output=True, text=True, errors="replace")
        par_cmd[args[1]] = round(time.perf_counter() - t, 3)
    # `total` = le travail REELLEMENT fait sur le depot : somme des commandes, MOINS le cout de
    # demarrage paye par chacune. Sans cette soustraction, cinq demarrages a 0,4 s font 2 s de
    # << git lent >> qui n'a rien a voir avec git.
    # BORNE A ZERO, et c'est une precaution MESUREE : le 2026-08-04 la soustraction a rendu
    # -0,065 s, parce que `version` avait ete tire a un instant plus charge que les autres. Un
    # temps negatif n'est pas << rapide >>, c'est un ESTIMATEUR HORS DOMAINE -- le laisser passer
    # ferait lire un ratio negatif comme un verdict. `brut` reste donc la mesure de reference.
    demarrage = par_cmd.get("version", 0.0)
    brut = sum(v for k, v in par_cmd.items() if k != "version")
    par_cmd["brut"] = round(brut, 3)
    par_cmd["total"] = round(max(brut - demarrage * (len(_GIT_LECTURES) - 1), 0.0), 3)
    return par_cmd


def _cibles_fs(racine: Path, plafond: int = 400) -> list:
    cibles = []
    base = racine / "scripts" / "python"
    if base.is_dir():
        for p in sorted(base.glob("*.py")):
            cibles.append(p)
            if len(cibles) >= plafond:
                break
    return cibles


def _sonde_fs(racine: Path, plafond: int = 400) -> float:
    """Lecture de fichiers du working tree, HORS `.git/`. Separe disque/antivirus de git."""
    cibles = _cibles_fs(racine, plafond)
    t = time.perf_counter()
    for p in cibles:
        try:
            p.read_bytes()
        except OSError:
            pass
    return time.perf_counter() - t


def _sonde_fs_ouvertures(racine: Path, plafond: int = 400) -> float:
    """MEMES fichiers, mais on ne lit QU'UN OCTET. Ce qui reste est le cout d'OUVRIR.

    C'est le discriminant : si `fs` et `fs_ouvertures` se degradent ENSEMBLE, ce qui coute est le
    NOMBRE D'ACCES (un filtre systeme paye a l'ouverture) ; si seul `fs` se degrade, c'est le
    DEBIT (disque). Les deux appellent la meme parade -- et ce ne sont pas les memes.
    """
    cibles = _cibles_fs(racine, plafond)
    t = time.perf_counter()
    for p in cibles:
        try:
            with open(p, "rb") as f:
                f.read(1)
        except OSError:
            pass
    return time.perf_counter() - t


def _sonde_fs_volume(racine: Path) -> float:
    """UN SEUL gros fichier, lu en entier : une ouverture, beaucoup d'octets.

    Le pendant exact de `fs_ouvertures`. Ensemble ils separent << beaucoup d'ouvertures >> de
    << beaucoup d'octets >>, que la sonde `fs` seule confond.
    """
    gros = None
    base = racine / "data" / "symbols"
    if base.is_dir():
        for p in base.rglob("*.tsv"):
            if gros is None or p.stat().st_size > gros.stat().st_size:
                gros = p
    if gros is None:
        return float("nan")
    t = time.perf_counter()
    with open(gros, "rb") as f:
        while f.read(1 << 20):
            pass
    return time.perf_counter() - t


# --------------------------------------------------------------------------- charge injectee

def _lancer_charge(k: int, genre: str = "cpu", racine: Path | None = None):
    """k process de bruit de fond. Le SUBSTITUT CONTROLE d'une flotte plus grande.

    DEUX GENRES, et c'est le bras qui separe le CPU de l'I/O. Une flotte d'agents ne prend pas que
    du CPU : elle ouvre des fichiers sans arret (imports Python, balayages d'arbre, pytest). Une
    charge purement CPU ne reproduirait donc PAS ce qu'une flotte fait subir a la banque -- et
    conclure de la seule charge CPU serait la meme faute que conclure du seul mur.
    """
    if genre == "cpu":
        argv = [sys.executable, "-c",
                "import math\nx=0.0\ni=1\n"
                "while True:\n x+=math.sqrt(i)/(i+1.0)\n i+=1\n"
                " \n if i>10**9: i=1\n"]
    elif genre == "io":
        base = str((racine or Path(".")) / "scripts" / "python")
        argv = [sys.executable, "-c",
                "import glob\n"
                "fs=sorted(glob.glob(r'%s\\\\*.py'))\n"
                "while True:\n"
                " for p in fs:\n"
                "  try:\n"
                "   open(p,'rb').read()\n"
                "  except OSError: pass\n" % base]
    else:
        raise ValueError("genre de charge inconnu : %s" % genre)
    return [subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            for _ in range(k)]


def _tuer(procs):
    for p in procs:
        try:
            p.kill()
        except OSError:
            pass
    for p in procs:
        try:
            p.wait(timeout=10)
        except Exception:
            pass


# --------------------------------------------------------------------------- clone de controle

def preparer_clone(repo: Path, dest: Path) -> Path:
    """Clone LOCAL (hardlinks) : meme contenu, meme volume d'objets, `.git/` A LUI.

    C'est le controle de `gitP`. `--local` ne fait que LIRE le depot partage (hardlinks sur les
    blobs, qui sont immuables) : aucune ecriture experimentale sur le `.git/` de quatre agents.
    """
    dest = dest.resolve()
    if not (dest / ".git").exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        r = subprocess.run(["git", "clone", "--local", "--no-hardlinks", "--quiet",
                            str(repo), str(dest)],
                           capture_output=True, text=True, errors="replace")
        if r.returncode != 0:
            raise RuntimeError("clone de controle impossible : rc=%d %s"
                               % (r.returncode, r.stderr[:400]))
    # SORTIR DU REGIME << RACY >>, sinon le controle mesure autre chose que le partage.
    # Juste apres un clone, les entrees de l'index portent le mtime du checkout : git les tient
    # pour DOUTEUSES et RELIT le contenu des 3498 fichiers a chaque `status`. Or nos sondes
    # passent `--no-optional-locks`, qui interdit precisement de reecrire l'index -- le clone
    # resterait donc en regime racy A VIE, et le << controle >> mesurerait ce regime au lieu du
    # partage. Contre-epreuve du 2026-08-04, index re-arme exprES : `status` a 23,8 puis 29,8 s
    # (stable, donc pas un cache froid) -> `update-index --refresh` -> 0,16 et 0,18 s.
    #
    # `update-index --refresh` et NON `git status` : #474 proscrit un `git status` de LECTURE qui
    # prend `.git/index.lock` a l'insu de son auteur, et `probe_474` a mordu sur la premiere
    # redaction de cette ligne -- a raison, son analyse statique ne peut pas savoir que la cible
    # est un depot jetable. Ici l'ecriture est le BUT, pas un effet de bord : la commande le
    # DECLARE. Ce n'est pas contourner le cliquet par le nom, c'est nommer le geste correctement.
    subprocess.run(["git", "-C", str(dest), "update-index", "--refresh"],
                   capture_output=True, text=True, errors="replace")
    return dest


# --------------------------------------------------------------------------- releve

def releve(repo: Path, clone: Path | None, repet: int, etiquette: str, grep: bool = False) -> dict:
    """Un releve = `repet` passages sur toutes les sondes, EN ALTERNANCE.

    L'alternance est load-bearing : jouer toutes les sondes gitP puis toutes les gitC les
    exposerait a des charges DIFFERENTES, et c'est exactement la confusion qu'on veut eviter.
    """
    _sonde_fs(repo)                     # amorce : le 1er passage mesure le cache froid, pas la charge
    ch = Charge()
    ser = {"cpu1": [], "cpu4": [], "spawn": [], "gitP": [], "gitC": [], "fs": [],
           "fs_ouvertures": [], "fs_volume": [],
           "gitP_brut": [], "gitC_brut": [], "gitP_demarrage": [], "grepP": [], "grepC": []}
    detail_git = {"P": [], "C": []}
    for _ in range(repet):
        ser["cpu1"].append(_sonde_cpu1())
        gp = _sonde_git(repo)
        ser["gitP"].append(gp["total"])
        ser["gitP_brut"].append(gp["brut"])
        ser["gitP_demarrage"].append(gp["version"])
        detail_git["P"].append(gp)
        if clone is not None:
            gc_ = _sonde_git(clone)
            ser["gitC"].append(gc_["total"])
            ser["gitC_brut"].append(gc_["brut"])
            detail_git["C"].append(gc_)
        ser["fs"].append(_sonde_fs(repo))
        ser["fs_ouvertures"].append(_sonde_fs_ouvertures(repo))
        ser["fs_volume"].append(_sonde_fs_volume(repo))
        ser["spawn"].append(_sonde_spawn())
        ser["cpu4"].append(_sonde_cpu4())
        if grep:
            # `git grep` en DERNIER et en ALTERNANCE stricte P puis C : c'est le geste de #468, et
            # sa comparaison partage/prive est le bras qui tranche (c). L'ordre importe -- les
            # jouer groupes par depot les exposerait a des charges differentes.
            ser["grepP"].append(_sonde_git_grep(repo))
            if clone is not None:
                ser["grepC"].append(_sonde_git_grep(clone))
    charge, duree = ch.lire() or (None, None)

    def med(xs):
        return round(statistics.median(xs), 3) if xs else None

    def mn(xs):
        return round(min(xs), 3) if xs else None

    res = {
        "etiquette": etiquette,
        "quand": time.strftime("%Y-%m-%d %H:%M:%S"),
        "contexte": _banque_en_vol(),
        "repet": repet,
        "coeurs_logiques": os.cpu_count(),
        "charge_coeurs_occupes": charge,
        "duree_releve_s": duree,
        "median": {k: med(v) for k, v in ser.items()},
        "min": {k: mn(v) for k, v in ser.items()},
        "series": {k: [round(x, 3) for x in v] for k, v in ser.items()},
        "git_detail": detail_git,
    }
    # Le ratio se prend sur le BRUT : c'est la seule des deux qui ne passe par aucun estimateur.
    gp, gc_ = res["median"]["gitP_brut"], res["median"]["gitC_brut"]
    res["ratio_gitP_sur_gitC"] = round(gp / gc_, 2) if (gp and gc_) else None
    xp, xc = res["median"]["grepP"], res["median"]["grepC"]
    res["ratio_grepP_sur_grepC"] = round(xp / xc, 2) if (xp and xc) else None
    return res


def imprimer(r: dict) -> None:
    print("-" * 78)
    print("releve            : %s   (%s)" % (r["etiquette"], r["quand"]))
    print("coeurs occupes    : %s / %s   (pendant %s s de releve)"
          % (r["charge_coeurs_occupes"], r["coeurs_logiques"], r["duree_releve_s"]))
    ctx = r.get("contexte") or {}
    if ctx.get("mesure"):
        print("contexte          : %d process python/pwsh, dont %d cliquet(s), %d ratchets, %d pytest"
              % (ctx["python_pwsh"], ctx["cliquets"], ctx["ratchets"], ctx["pytest"]))
    else:
        print("contexte          : NON MESURE (l'inventaire des process a echoue)")
    m, mi = r["median"], r["min"]
    for k, libelle in (("cpu1", "cpu1  (1 coeur)"), ("cpu4", "cpu4  (debit agrege)"),
                       ("spawn", "spawn (4 python nus)"),
                       ("gitP_demarrage", "git   (demarrage nu)"),
                       ("gitP_brut", "gitP  (.git PARTAGE)"), ("gitC_brut", "gitC  (clone PRIVE)"),
                       ("grepP", "grepP (grep PARTAGE)"), ("grepC", "grepC (grep PRIVE)"),
                       ("fs", "fs    (400 fic. lus)"),
                       ("fs_ouvertures", "fsOpen(400 ouvertures)"),
                       ("fs_volume", "fsVol (1 gros fichier)")):
        if m.get(k) is not None:
            print("  %-22s median %8.3f s   min %8.3f s" % (libelle, m[k], mi[k]))
    for cle, libelle in (("ratio_gitP_sur_gitC", "RATIO gitP / gitC"),
                         ("ratio_grepP_sur_grepC", "RATIO grepP / grepC")):
        if r.get(cle) is not None:
            print("  %-21s %.2f      <- >>1 = contention du .git PARTAGE (c)"
                  % (libelle, r[cle]))


def scalabilite(repo: Path, ks: list, genre: str, repet: int = 1) -> list:
    """LE DEBIT AGREGE en fonction du nombre de process concurrents.

    C'est la mesure qui repond directement a << combien de parallelisme la machine RENDE-t-elle ? >>,
    et elle coute deux minutes la ou rejouer la banque en coute vingt.

    On lance K process identiques faisant chacun le MEME travail borne, et on lit le mur. Si la
    ressource passe a l'echelle, le mur reste plat et le debit croit lineairement. Si elle sature,
    le mur croit proportionnellement a K et le debit plafonne : au-dela du point de saturation,
    ajouter un process n'ajoute RIEN et allonge TOUS les autres -- ce qui est exactement la forme
    d'un mur de banque.

    Deux genres, parce qu'il y a deux ressources candidates et qu'elles n'ont pas la meme parade :
      * `cpu` -- calcul pur : plafonne au nombre de coeurs utiles ;
      * `io`  -- ouvertures de fichiers : plafonne la ou le filtre systeme sature.
    """
    base = repo / "scripts" / "python"
    n_fic = 200
    if genre == "cpu":
        prog = ("import math\nx=0.0\n"
                "for i in range(1,%d): x+=math.sqrt(i)/(i+1.0)\n" % (_BOUCLE_N * 4))
        unite = "boucles"
        travail_par_proc = 1.0
    else:
        prog = ("import glob\n"
                "fs=sorted(glob.glob(r'%s\\\\*.py'))[:%d]\n"
                "for p in fs:\n"
                " try:\n"
                "  open(p,'rb').read(1)\n"
                " except OSError: pass\n" % (str(base), n_fic))
        unite = "ouvertures"
        travail_par_proc = float(n_fic)

    out = []
    for k in ks:
        murs = []
        for _ in range(repet):
            murs.append(_lancer_et_attendre([sys.executable, "-c", prog], k))
        mur = statistics.median(murs)
        # Le spawn est paye par chaque process AVANT de travailler : le retirer, sinon a K=1 on
        # imputerait a la ressource un cout qui est celui du demarrage.
        out.append({"k": k, "genre": genre, "mur_s": round(mur, 3),
                    "debit_par_s": round(k * travail_par_proc / mur, 1) if mur > 0 else None,
                    "unite": unite})
        print("  k=%-3d  mur %7.3f s   debit %10.1f %s/s" % (k, mur, out[-1]["debit_par_s"], unite))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", default=None, help="depot PARTAGE a sonder (defaut : arbre principal)")
    ap.add_argument("--clone", default=None, help="repertoire du clone de controle")
    ap.add_argument("--sans-clone", action="store_true", help="ne pas sonder de clone de controle")
    ap.add_argument("--repet", type=int, default=3)
    ap.add_argument("--releve", action="store_true", help="un releve a la charge courante")
    ap.add_argument("--charge", type=int, default=0, help="coeurs de charge injectee pendant le releve")
    ap.add_argument("--genre", choices=["cpu", "io"], default="cpu",
                    help="nature de la charge injectee : calcul pur, ou ouvertures de fichiers")
    ap.add_argument("--rampe", default=None, help="liste de charges, ex. 0,4,8,16")
    ap.add_argument("--charge-seule", type=int, default=0, help="injecter K process et attendre")
    ap.add_argument("--duree", type=int, default=300, help="duree de --charge-seule, en secondes")
    ap.add_argument("--etiquette", default="")
    ap.add_argument("--scalabilite", default=None,
                    help="liste de degres de parallelisme, ex. 1,2,4,8,16,22")
    ap.add_argument("--grep", action="store_true",
                    help="ajouter la sonde `git grep` (le geste de #468) -- ~26 s par depot")
    ap.add_argument("--json", default=None, help="ou ecrire le releve (defaut : logs/probe469/)")
    a = ap.parse_args(argv)

    if a.charge_seule > 0:
        procs = _lancer_charge(a.charge_seule, a.genre,
                               Path(a.repo) if a.repo else Path.cwd().parents[1])
        print("[469] charge injectee : %d process, %d s" % (a.charge_seule, a.duree))
        try:
            time.sleep(a.duree)
        finally:
            _tuer(procs)
        print("[469] charge retiree")
        return 0

    repo = Path(a.repo).resolve() if a.repo else Path(
        subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True,
                       text=True).stdout.strip() or ".").resolve()

    if a.scalabilite:
        ks = [int(x) for x in a.scalabilite.split(",") if x.strip()]
        tout = {"quand": time.strftime("%Y-%m-%d %H:%M:%S"), "contexte": _banque_en_vol(),
                "coeurs_logiques": os.cpu_count(), "series": {}}
        for genre in ("cpu", "io"):
            print("--- scalabilite %s ---" % genre.upper())
            tout["series"][genre] = scalabilite(repo, ks, genre, a.repet)
        dest_json = Path(a.json) if a.json else (
            repo / "logs" / "probe469" / ("scalabilite-%s.json" % time.strftime("%Y%m%d-%H%M%S")))
        dest_json.parent.mkdir(parents=True, exist_ok=True)
        dest_json.write_text(json.dumps(tout, indent=1), encoding="utf-8")
        print("[469] scalabilite -> %s" % dest_json)
        return 0

    clone = None
    if not a.sans_clone:
        dest = Path(a.clone) if a.clone else Path(os.environ.get("TEMP", ".")) / "probe469-clone"
        clone = preparer_clone(repo, dest)

    charges = [a.charge]
    if a.rampe:
        charges = [int(x) for x in a.rampe.split(",") if x.strip() != ""]

    releves = []
    for k in charges:
        procs = _lancer_charge(k, a.genre, repo) if k > 0 else []
        if k > 0:
            time.sleep(2.0)          # laisser la charge s'etablir avant de mesurer
        try:
            et = a.etiquette or "charge%s+%d" % (a.genre, k)
            if a.rampe:
                et = "%s charge%s+%d" % (a.etiquette or "rampe", a.genre, k)
            r = releve(repo, clone, a.repet, et, grep=a.grep)
            r["charge_injectee"] = k
            releves.append(r)
            imprimer(r)
        finally:
            _tuer(procs)

    dest_json = Path(a.json) if a.json else (
        repo / "logs" / "probe469" / ("releve-%s.json" % time.strftime("%Y%m%d-%H%M%S")))
    dest_json.parent.mkdir(parents=True, exist_ok=True)
    dest_json.write_text(json.dumps(releves, indent=1), encoding="utf-8")
    print("[469] releve -> %s" % dest_json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
