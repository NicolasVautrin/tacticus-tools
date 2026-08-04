"""Contre-epreuve de l'instrument `probe_474_git_lock_forensics`.

CE QUI EST GARDE ICI, ET POURQUOI C'EST LE POINT CRITIQUE
----------------------------------------------------------
Tout l'instrument repose sur UN fait : `tenu()` distingue un lock TENU d'un lock PERIME par
OUVERTURE EXCLUSIVE. Si ce test rendait `False` sur un fichier reellement tenu, `--purger`
supprimerait le lock d'un git EN COURS -- c'est-a-dire corromprait le depot exactement de la
facon que #474 interdit. Un instrument qui ne repond que << libre >> serait pire que rien.

Le sens SUSPECT est donc le vert facile : chaque epreuve verifie que sa condition a MORDU
(le handle exclusif est bien pris, le `git status` tient bien son lock) avant de conclure.

DEPOT JETABLE (tmpdir SYSTEME, #455). ASCII strict.
"""

import ctypes
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import probe_474_git_lock_forensics as F                                  # noqa: E402


def _ouvrir_exclusif(chemin: Path):
    """Un handle en partage ZERO -- ce que fait un git qui tient son lockfile."""
    k32 = ctypes.windll.kernel32
    k32.CreateFileW.restype = wintypes.HANDLE
    k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD,
                                wintypes.HANDLE]
    h = k32.CreateFileW(str(chemin), 0x80000000 | 0x40000000, 0, None, 3, 0, None)
    assert h and h != ctypes.c_void_p(-1).value, "le handle exclusif n'a pas ete pris"
    return h


def test_libre_absent_tenu(tmp_path):
    f = tmp_path / "index.lock"
    f.write_bytes(b"")

    assert F.tenu(f)[0] is False, "un fichier que personne ne tient doit etre LIBRE"

    h = _ouvrir_exclusif(f)
    try:
        etat, code = F.tenu(f)
        assert etat is True, "un fichier TENU doit etre vu tenu (sinon --purger detruit)"
        assert code in (5, 32), "code Windows attendu ACCESS_DENIED/SHARING_VIOLATION, eu %d" % code
    finally:
        ctypes.windll.kernel32.CloseHandle(wintypes.HANDLE(h))

    assert F.tenu(f)[0] is False, "handle relache -> LIBRE"

    f.unlink()
    assert F.tenu(f)[0] is None, "absent = PAS MESURE, jamais rabattu sur libre"


def test_purger_epargne_un_lock_tenu(tmp_path, capsys):
    depot = tmp_path / "d"
    (depot / ".git").mkdir(parents=True)
    lock = depot / ".git" / "index.lock"
    lock.write_bytes(b"")

    h = _ouvrir_exclusif(lock)
    try:
        assert F.purger(depot, "index.lock") == 0
        assert lock.exists(), "un lock TENU ne doit JAMAIS etre supprime"
        assert "TENU" in capsys.readouterr().out
    finally:
        ctypes.windll.kernel32.CloseHandle(wintypes.HANDLE(h))

    assert F.purger(depot, "index.lock") == 0
    assert not lock.exists(), "un lock LIBRE doit etre retire"


def test_un_git_en_cours_est_vu_TENU(tmp_path):
    """L'epreuve qui compte : le lock d'une commande REELLE en cours n'est pas << perime >>.

    C'est la contre-epreuve du discriminant sur du vrai git, pas sur un handle fabrique.

    La commande est `git add`, pas `git status`, et ce n'est PAS un contournement du cliquet
    `probe_474` : `add` prend `index.lock` tout aussi reellement (mesure #474 : lock vu 8/8,
    tailles 0 -> 131072 -> ... -> 481886) et il est HORS de son gisement par construction --
    son lock est une ECRITURE VOULUE, a laquelle `--no-optional-locks` ne s'applique pas.
    Ecrire `git status` ici ferait rougir `probe_474` sur son propre test, et l'exempter par
    une allowlist ruinerait un perimetre DERIVE.
    """
    depot = tmp_path / "repo"
    depot.mkdir()

    def g(*a):
        return subprocess.run(["git", *a], cwd=str(depot), capture_output=True,
                              text=True, timeout=180)
    g("init", "-q", "-b", "master")
    g("config", "user.email", "t@t")
    g("config", "user.name", "t")
    for i in range(1500):
        (depot / ("f%04d.txt" % i)).write_text("%d\n" % i, encoding="ascii")
    g("add", "-A")
    g("commit", "-qm", "base")
    (depot / "f0000.txt").write_text("sale\n", encoding="ascii")

    lock = depot / ".git" / "index.lock"
    p = subprocess.Popen(["git", "add", "-A"], cwd=str(depot),
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    vu_tenu = vu_lock = False
    t0 = time.time()
    try:
        while p.poll() is None and time.time() - t0 < 60:
            if lock.exists():
                vu_lock = True
                if F.tenu(lock)[0] is True:
                    vu_tenu = True
                    break
            time.sleep(0.001)
    finally:
        try:
            p.wait(timeout=60)
        except subprocess.TimeoutExpired:      # pragma: no cover
            p.kill()

    if not vu_lock:
        pytest.skip("le lock n'a pas ete apercu : rien a confronter sur cette machine")
    assert vu_tenu, ("un `git add` EN COURS tenait son index.lock et l'instrument l'a "
                     "vu LIBRE -- --purger detruirait un lock vivant")


def test_gitdir_depuis_un_worktree(tmp_path):
    """Depuis un worktree, `.git` est un FICHIER : l'instrument doit remonter au commun."""
    depot = tmp_path / "repo"
    depot.mkdir()

    def g(cwd, *a):
        return subprocess.run(["git", *a], cwd=str(cwd), capture_output=True,
                              text=True, timeout=180)
    g(depot, "init", "-q", "-b", "master")
    g(depot, "config", "user.email", "t@t")
    g(depot, "config", "user.name", "t")
    (depot / "a.txt").write_text("a\n", encoding="ascii")
    g(depot, "add", "-A")
    g(depot, "commit", "-qm", "base")

    wt = tmp_path / "wt"
    r = g(depot, "worktree", "add", "--detach", "-q", str(wt))
    if r.returncode != 0:                       # pragma: no cover
        pytest.skip("git worktree add indisponible : %s" % (r.stderr or "").strip())

    assert (wt / ".git").is_file(), "montage inattendu : .git devrait etre un fichier"
    assert F.gitdir(wt) == depot / ".git"
    assert F.gitdir(depot) == depot / ".git"
    g(depot, "worktree", "remove", "--force", str(wt))
