"""Instrument #474 -- qui tient quoi, au moment ou un lock git est la.

POURQUOI IL EXISTE
------------------
La cause de #474 est etablie (un process git TUE pendant qu'il tient `.git/index.lock` laisse
un residu de 0 octet, libre) et la fenetre est fermee a la source par `--no-optional-locks`
(cliquet `probe_474_optional_locks`). Restent les kills qu'aucun code du depot ne gouverne --
une commande interrompue a la main, un shell de fond coupe. Cet instrument est ce qui
ATTRIBUERA la prochaine occurrence au lieu de la faire re-deviner.

Il repond a trois questions, et une seule est un jugement :
  * QUELS locks existent (nom, taille, age) -- sous `.git/` ET sous `.git/worktrees/*/` ;
  * lesquels sont TENUS -- par OUVERTURE EXCLUSIVE, **jamais par l'age** ;
  * QUI tourne -- les process `git` vivants avec leur ligne de commande.

LE DISCRIMINANT, ET CE QU'IL INTERDIT
--------------------------------------
**Libre => perime. Tenu => attendre.** Un lock de 0 octet n'est PAS la preuve d'un residu :
`git status` tient le sien a 0 octet pendant ~toute sa duree (mesure #474), donc un lock de
0 octet est le cas NORMAL d'une commande en cours. Seule l'ouverture exclusive tranche, et
c'est pourquoi `--purger` la refait juste avant chaque suppression.

`--purger` est un geste EXPLICITE. Rien ici ne s'arme tout seul : purger un `index.lock`
parce qu'une commande a echoue corromprait le depot le jour ou un git tourne vraiment.

ASCII strict. Lecture seule sauf `--purger` ; le journal de `--veille` va dans `logs/`
(gitignore), jamais dans `data/`.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import subprocess
import sys
import time
from ctypes import wintypes
from datetime import datetime
from pathlib import Path

_GENERIC_READ = 0x80000000
_GENERIC_WRITE = 0x40000000
_OPEN_EXISTING = 3
_INVALIDE = ctypes.c_void_p(-1).value


def tenu(chemin: Path) -> tuple[bool | None, int]:
    """`(tenu, code)` -- ouverture EXCLUSIVE (`dwShareMode = 0`), le seul test valable.

    `open()`/`os.open()` de Python passent par `_SH_DENYNO` : ils REUSSISSENT sur un fichier
    qu'un autre process tient, donc ils ne repondent pas a la question. `None` = pas mesure
    (le fichier a disparu entre-temps) -- jamais rabattu sur `False` (#467 : un capteur muet
    ne fabrique pas de reponse).
    """
    k32 = ctypes.windll.kernel32
    k32.CreateFileW.restype = wintypes.HANDLE
    k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD,
                                wintypes.HANDLE]
    h = k32.CreateFileW(str(chemin), _GENERIC_READ | _GENERIC_WRITE, 0, None,
                        _OPEN_EXISTING, 0, None)
    if h == _INVALIDE or not h:
        code = ctypes.GetLastError()
        if code == 2:                     # ERROR_FILE_NOT_FOUND : disparu, rien a dire
            return (None, code)
        return (True, code)               # 32 = SHARING_VIOLATION, 5 = ACCESS_DENIED
    k32.CloseHandle(wintypes.HANDLE(h))
    return (False, 0)


def gitdir(repo: Path) -> Path | None:
    """Le repertoire `.git` COMMUN. Depuis un worktree, `.git` est un FICHIER."""
    p = repo / ".git"
    if p.is_dir():
        return p
    if p.is_file():
        for ligne in p.read_text(encoding="utf-8", errors="replace").splitlines():
            if ligne.startswith("gitdir:"):
                gd = Path(ligne.split(":", 1)[1].strip())
                # `.git/worktrees/<n>` -> le commun est deux crans au-dessus
                return gd.parent.parent if gd.parent.name == "worktrees" else gd
    return None


def locks(gd: Path) -> list[dict]:
    """Tous les `*.lock` sous le `.git` commun, y compris ceux des worktrees."""
    out = []
    for p in sorted(gd.rglob("*.lock")):
        try:
            st = p.stat()
        except OSError:
            continue
        t, code = tenu(p)
        out.append({
            "chemin": str(p.relative_to(gd)),
            "octets": st.st_size,
            "age_s": round(time.time() - st.st_mtime, 1),
            "tenu": t,
            "code_win": code,
        })
    return out


def process_git() -> list[dict] | None:
    """Les `git.exe` vivants + leur ligne de commande. `None` = PAS mesure (#467-r6)."""
    ps = ("Get-CimInstance Win32_Process -Filter \"Name='git.exe'\" | "
          "Select-Object ProcessId,ParentProcessId,CommandLine | ConvertTo-Json -Compress")
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                           capture_output=True, text=True, timeout=25)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    brut = (r.stdout or "").strip()
    if not brut:
        return []                          # mesure faite, aucun process : un VRAI zero
    try:
        d = json.loads(brut)
    except ValueError:
        return None
    return d if isinstance(d, list) else [d]


def etat(repo: Path) -> dict:
    gd = gitdir(repo)
    if gd is None:
        return {"erreur": "pas un depot git : %s" % repo}
    d: dict = {"quand": datetime.now().isoformat(timespec="seconds"),
               "repo": str(repo), "gitdir": str(gd), "locks": locks(gd),
               "process_git": process_git()}
    for nom in ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REBASE_HEAD", "BISECT_LOG", "gc.pid"):
        f = gd / nom
        if f.exists():
            d.setdefault("marqueurs", {})[nom] = f.read_text(
                encoding="utf-8", errors="replace").strip()[:80]
    pid_gc = (d.get("marqueurs", {}) or {}).get("gc.pid", "").split()
    if pid_gc and pid_gc[0].isdigit():
        d["gc_pid_vivant"] = _pid_vivant(int(pid_gc[0]))
    return d


def _pid_vivant(pid: int) -> bool | None:
    k32 = ctypes.windll.kernel32
    h = k32.OpenProcess(0x1000, False, pid)          # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return False if ctypes.GetLastError() == 87 else None    # 87 = param invalide = mort
    k32.CloseHandle(wintypes.HANDLE(h))
    return True


def imprimer(d: dict) -> None:
    if "erreur" in d:
        print("[474] %s" % d["erreur"])
        return
    print("[474] %s  gitdir=%s" % (d["quand"], d["gitdir"]))
    ls = d["locks"]
    if not ls:
        print("  locks : AUCUN")
    for l in ls:
        if l["tenu"] is None:
            verdict = "PAS MESURE (disparu)"
        elif l["tenu"]:
            verdict = "TENU -> ATTENDRE (code win %d)" % l["code_win"]
        else:
            verdict = "LIBRE -> PERIME"
        print("  lock %-52s %7d o  age %8.1f s  %s"
              % (l["chemin"], l["octets"], l["age_s"], verdict))
    pg = d["process_git"]
    if pg is None:
        print("  process git : PAS MESURE (powershell muet)")
    elif not pg:
        print("  process git : aucun")
    else:
        for p in pg:
            print("  git pid=%-7s ppid=%-7s %s"
                  % (p.get("ProcessId"), p.get("ParentProcessId"),
                     (p.get("CommandLine") or "")[:110]))
    for k, v in (d.get("marqueurs") or {}).items():
        sfx = ""
        if k == "gc.pid" and "gc_pid_vivant" in d:
            sfx = "  (PID vivant : %s)" % d["gc_pid_vivant"]
        print("  marqueur %-16s %s%s" % (k, v, sfx))


def veille(repo: Path, secs: float, pas: float, persist: float) -> int:
    """Attrape l'occurrence SUIVANTE : un lock LIBRE (ouverture exclusive) qui PERSISTE.

    `persist` borne le faux positif : `git status` tient son lock a 0 octet pendant ~toute sa
    duree, et l'ouverture exclusive peut y reussir entre deux acces. Un residu, lui, reste.
    """
    gd = gitdir(repo)
    if gd is None:
        print("[474] pas un depot git : %s" % repo)
        return 2
    jour = repo / "logs" / "474-git-lock"
    vus: dict[str, float] = {}
    fin = time.time() + secs
    trouves = 0
    print("[474] veille %.0f s sur %s (pas %.2f s, persistance %.1f s)" % (secs, gd, pas, persist))
    while time.time() < fin:
        maintenant = time.time()
        courants = {l["chemin"]: l for l in locks(gd)}
        for cle in list(vus):
            if cle not in courants:
                del vus[cle]
        for cle, l in courants.items():
            if l["tenu"] is not False:          # tenu, ou pas mesure -> on n'accuse pas
                vus.pop(cle, None)
                continue
            depuis = vus.setdefault(cle, maintenant)
            if maintenant - depuis < persist:
                continue
            d = etat(repo)
            d["declencheur"] = cle
            d["libre_depuis_s"] = round(maintenant - depuis, 1)
            print("[474] OCCURRENCE -- `%s` LIBRE depuis %.1f s" % (cle, maintenant - depuis))
            imprimer(d)
            jour.mkdir(parents=True, exist_ok=True)
            f = jour / ("%s-%s.json" % (datetime.now().strftime("%Y%m%d-%H%M%S"),
                                        cle.replace("/", "_").replace("\\", "_")))
            f.write_text(json.dumps(d, indent=2), encoding="utf-8")
            print("[474] capture -> %s" % f)
            trouves += 1
            vus[cle] = maintenant + 1e9         # ne pas re-declencher sur le meme
        time.sleep(pas)
    print("[474] veille terminee -- %d occurrence(s)" % trouves)
    return 0


def purger(repo: Path, motif: str) -> int:
    """Supprime les locks dont l'ouverture EXCLUSIVE reussit. Geste explicite, jamais arme."""
    gd = gitdir(repo)
    if gd is None:
        print("[474] pas un depot git : %s" % repo)
        return 2
    n = 0
    for l in locks(gd):
        if motif not in l["chemin"]:
            continue
        p = gd / l["chemin"]
        t, code = tenu(p)                       # RE-teste juste avant : l'etat a pu changer
        if t is None:
            print("  %-52s disparu entre-temps" % l["chemin"])
            continue
        if t:
            print("  %-52s TENU (code win %d) -- on n'y touche pas" % (l["chemin"], code))
            continue
        try:
            p.unlink()
            print("  %-52s LIBRE -> supprime (%d o, age %.1f s)"
                  % (l["chemin"], l["octets"], l["age_s"]))
            n += 1
        except OSError as exc:
            print("  %-52s suppression refusee : %s" % (l["chemin"], exc))
    print("[474] %d lock(s) perime(s) retire(s)" % n)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", default=str(Path(__file__).resolve().parent.parent.parent))
    ap.add_argument("--veille", action="store_true", help="attendre l'occurrence suivante")
    ap.add_argument("--secs", type=float, default=600.0)
    ap.add_argument("--pas", type=float, default=0.25)
    ap.add_argument("--persistance", type=float, default=3.0)
    ap.add_argument("--purger", metavar="MOTIF", nargs="?", const="index.lock",
                    help="supprimer les locks LIBRES dont le chemin contient MOTIF")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    repo = Path(a.repo).resolve()
    if a.veille:
        return veille(repo, a.secs, a.pas, a.persistance)
    if a.purger:
        return purger(repo, a.purger)
    d = etat(repo)
    if a.json:
        print(json.dumps(d, indent=2))
    else:
        imprimer(d)
    return 0


if __name__ == "__main__":
    sys.exit(main())
