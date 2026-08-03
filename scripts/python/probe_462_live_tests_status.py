"""#462 -- INVENTAIRE de l'etat des tests LIVE (`*_live.py`), que RIEN ne regarde aujourd'hui.

CE QU'IL EST SEUL A VOIR
------------------------
`probe_457_offline_tests_green.py` garde le VERT des tests offline, et son perimetre EXCLUT
`*_live.py` -- choix assume et documente (la suite live sature la session Frida partagee). La
boucle de merge, elle, ne rejoue que les tests live de la TRANCHE modifiee. Entre les deux, un
fichier live que personne ne touche n'est JAMAIS regarde : il peut rougir des semaines sans que
rien ne le signale.

MESURE qui l'a revele (PR #533) : `test_env_fire_tile_dot_applies_resilient_cap_live` etait ROUGE
sur `master` depuis `ad5692e7`. Ni la banque ni la boucle ne pouvaient le voir. C'est la meme
famille que #455 (un fichier integralement skippe est INVISIBLE) : ce n'est pas le rouge qui est le
probleme, c'est l'INVISIBILITE.

POURQUOI CE PROBE N'EST PAS DANS LA BANQUE
------------------------------------------
Il ne peut pas y etre, et le refuter coute moins cher que de l'essayer. Le parc live est de
l'ordre de 400 fichiers ; chacun monte au moins un runner. Le plafond DUR est de 4 processus
montant un runner en parallele (le pump est partage avec les autres agents). Un balayage COMPLET
se compte donc en heures -- hors de portee d'une banque dont le mur entier tient en ~300 s.

Un << shard tournant >> (1/N du parc par passage de banque) a ete propose puis REFUTE PAR CALCUL :
a un budget de +60 s de mur par passage, couvrir le parc UNE fois demanderait de l'ordre de la
centaine de passages. Ce n'est pas un garde, c'est une loterie -- un fichier peut rougir pendant
des semaines avant que son tour vienne.

CE QU'IL FAIT DONC
------------------
Il est un INSTRUMENT DE BALAYAGE BORNE, lance A LA MAIN (ou par un travail periodique), et un
LEDGER : il ecrit le dernier statut CONNU par fichier, avec le commit ou il a ete mesure. Ce que le
ledger rend visible n'est pas << tout est vert >> (personne ne peut le promettre) mais
L'ANCIENNETE DE LA DERNIERE MESURE -- l'aveu explicite que 417 fichiers n'ont pas ete regardes
depuis N jours vaut mieux qu'un silence qui se lit comme du vert.

MODES
-----
  --list                 imprime le perimetre et sort (aucun runner monte).
  --collect              collecte SEULE (`--collect-only`) sur tout le perimetre. Ne monte AUCUN
                         runner -- c'est le seul balayage EXHAUSTIF abordable, et il couvre a lui
                         seul la categorie HARNAIS/COLLECTE (import, syntaxe, fixture inconnue).
  --run                  joue un SOUS-ENSEMBLE borne (`--sample`/`--files`/`--since`), `--jobs`
                         processus en parallele (defaut 4, PLAFOND DUR -- cf. `CLAUDE.md`).
  --report               relit le ledger et imprime l'inventaire, sans rien jouer.

VENTILATION (#533) : un rouge n'accuse pas forcement le PORT. Ce probe ne CLASSE pas -- il ne peut
pas : distinguer PORT / MONTAGE / HARNAIS demande de lire le decompile. Il RAPPORTE le symptome
verbatim, et c'est a l'humain (ou a un solveur) de ventiler. Pretendre classer automatiquement
reproduirait exactement la faute de #533, ou le message du `pytest.fail` disait vrai sur le FAIT et
FAUX sur la CAUSE.

ROUGE = `failed`/`error` > 0, OU `passed == 0 and skipped > 0` (#455 : zero assertion evaluee).

PERIMETRE (#434) : `git ls-files` dans CE checkout -- jamais l'arbre d'un autre agent.
ECRITURE (#455) : rien sous `scripts/python/` -- le ledger va sous `logs/`, les XML JUnit dans un
tmpdir systeme.

ASCII only (cp1252).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path

_PYDIR = Path(__file__).resolve().parent

#: Meme repertoire de tests que `probe_457` -- PATHSPEC de repertoire, pas un glob (#457-r5 :
#: `**/` exige un segment intermediaire et masquait les fichiers poses directement dans `tests/`).
TESTS_DIR = "scripts/python/tests"

#: Plafond DUR de processus montant un runner (`CLAUDE.md`) : le pump est PARTAGE avec les autres
#: agents. Depasser degrade tout le monde, y compris l'appelant.
MAX_JOBS = 4


def repo_root() -> Path:
    """Racine du checkout COURANT (worktree compris) -- jamais l'arbre principal (#434)."""
    return _PYDIR.parents[1]


def ledger_path() -> Path:
    """Dernier statut CONNU par fichier. Sous `logs/`, JAMAIS sous `scripts/python/` (#455)."""
    return repo_root() / "logs" / "ratchets" / "462-live-status.json"


def _is_test_file(name: str) -> bool:
    return name.endswith(".py") and (name.startswith("test_") or name.endswith("_test.py"))


def live_files() -> list[str]:
    """Les fichiers de test `*_live.py`, relatifs a `scripts/python`. Tri stable."""
    out = subprocess.run(["git", "ls-files", TESTS_DIR], capture_output=True, text=True,
                         cwd=str(repo_root()), check=True)
    prefix = "scripts/python/"
    rels = []
    for line in out.stdout.splitlines():
        rel = line.strip()
        if not rel.startswith(prefix) or not rel.endswith("_live.py"):
            continue
        if not _is_test_file(rel.rsplit("/", 1)[-1]):
            continue
        rels.append(rel[len(prefix):])
    return sorted(rels)


def _head() -> str:
    r = subprocess.run(["git", "-C", str(repo_root()), "rev-parse", "HEAD"],
                       capture_output=True, text=True)
    return (r.stdout or "").strip()


def _last_touch(rels: list[str]) -> dict:
    """Date (epoch) du dernier commit ayant touche chaque fichier. Sert au tri par RISQUE.

    Un fichier dont la tranche n'a pas bouge depuis longtemps n'a pas ete rejoue depuis longtemps :
    c'est exactement le gisement ou un rouge peut dormir. Ce n'est PAS une preuve de rot -- juste un
    ordre de visite qui met les candidats les plus probables en tete d'un balayage BORNE."""
    ages = {}
    for rel in rels:
        r = subprocess.run(["git", "-C", str(repo_root()), "log", "-1", "--format=%ct", "--",
                            "scripts/python/" + rel], capture_output=True, text=True)
        txt = (r.stdout or "").strip()
        ages[rel] = int(txt) if txt.isdigit() else 0
    return ages


# --------------------------------------------------------------------------------------------
# Execution bornee
# --------------------------------------------------------------------------------------------

def _parse_junit(xml_path: Path) -> dict:
    """{chemin relatif -> {passed, failed, error, skipped, time, messages}} depuis un JUnit XML.

    On lit l'attribut `file` du `testcase` (pytest le pose), pas `classname` : sous
    `--import-mode=importlib` le classname est un chemin pointe dont la retro-conversion est
    ambigue des qu'un repertoire contient un point."""
    res: dict = {}
    if not xml_path.exists():
        return res
    try:
        tree = ET.parse(str(xml_path))
    except ET.ParseError:
        return res
    for case in tree.getroot().iter("testcase"):
        rel = (case.get("file") or "").replace("\\", "/")
        if not rel:
            continue
        e = res.setdefault(rel, {"passed": 0, "failed": 0, "error": 0, "skipped": 0,
                                 "time": 0.0, "messages": []})
        e["time"] += float(case.get("time") or 0.0)
        kind = None
        for child in case:
            if child.tag in ("failure", "error", "skipped"):
                kind = {"failure": "failed", "error": "error", "skipped": "skipped"}[child.tag]
                if kind in ("failed", "error") and len(e["messages"]) < 3:
                    msg = (child.get("message") or "").strip().replace("\n", " ")
                    e["messages"].append("%s::%s -- %s" % (rel.rsplit("/", 1)[-1],
                                                           case.get("name") or "?", msg[:300]))
                break
        e[kind or "passed"] += 1
    return res


def _verdict(counts: dict) -> str:
    """ROUGE / VERT / VIDE. `passed == 0 and skipped > 0` est ROUGE (#455)."""
    if counts.get("failed", 0) or counts.get("error", 0):
        return "ROUGE"
    if counts.get("passed", 0) == 0:
        return "ROUGE" if counts.get("skipped", 0) else "VIDE"
    return "VERT"


def _batches(files: list[str], jobs: int) -> list[list[str]]:
    """Round-robin : chaque worker recoit un echantillon reparti, pas un bloc contigu.

    Contigu grouperait les fichiers d'un meme repertoire (donc de couts correles) dans le meme
    worker ; le round-robin les etale, ce qui equilibre sans avoir besoin de poids mesures."""
    out: list[list[str]] = [[] for _ in range(jobs)]
    for i, rel in enumerate(files):
        out[i % jobs].append(rel)
    return [b for b in out if b]


def _run_batch(idx: int, files: list[str], xml_dir: Path, timeout_s: float) -> dict:
    """Un worker pytest. Rend {rc, timed_out, xml, elapsed}."""
    xml = xml_dir / ("junit-%d.xml" % idx)
    cmd = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
           "--junitxml=%s" % xml, *files]
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    started = time.time()
    timed_out = False
    try:
        p = subprocess.run(cmd, cwd=str(_PYDIR), env=env, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout_s)
        rc = p.returncode
        tail = (p.stdout or "")[-4000:]
    except subprocess.TimeoutExpired:
        timed_out = True
        rc = -1
        tail = "TIMEOUT apres %.0f s" % timeout_s
    return {"idx": idx, "rc": rc, "timed_out": timed_out, "xml": xml,
            "elapsed": time.time() - started, "tail": tail, "files": files}


def _do_run(files: list[str], jobs: int, timeout_s: float, out_dir: Path) -> dict:
    """Joue `files` sur `jobs` workers paralleles. Rend l'inventaire par fichier."""
    from concurrent.futures import ThreadPoolExecutor

    batches = _batches(files, jobs)
    print("[462] %d fichier(s) a jouer, %d worker(s), timeout %.0f s/worker"
          % (len(files), len(batches), timeout_s))
    started = time.time()
    with ThreadPoolExecutor(max_workers=len(batches)) as pool:
        futures = [pool.submit(_run_batch, i, b, out_dir, timeout_s)
                   for i, b in enumerate(batches)]
        results = [f.result() for f in futures]
    mur = time.time() - started

    par_fichier: dict = {}
    for r in results:
        vus = _parse_junit(r["xml"])
        for rel in r["files"]:
            # Le nodeid pytest est relatif au rootdir (`scripts/python`), et l'attribut `file`
            # du JUnit XML l'est aussi -- meme forme que `rel`.
            c = vus.get(rel)
            if c is None:
                # Pas de report : le worker est mort avant d'y arriver (timeout, crash). NE PAS
                # le compter vert -- c'est exactement le mode de defaillance silencieux a eviter.
                par_fichier[rel] = {"verdict": "NON JOUE", "passed": 0, "failed": 0, "error": 0,
                                    "skipped": 0, "time": 0.0, "messages": [],
                                    "raison": ("worker %d timeout" % r["idx"]) if r["timed_out"]
                                              else ("worker %d rc=%d, aucun report"
                                                    % (r["idx"], r["rc"]))}
            else:
                par_fichier[rel] = dict(c, verdict=_verdict(c))
    print("[462] mur %.1f s ; workers : %s"
          % (mur, ", ".join("#%d %.0f s%s" % (r["idx"], r["elapsed"],
                                              " TIMEOUT" if r["timed_out"] else "")
                            for r in results)))
    return par_fichier


def _merge_ledger(nouveau: dict, commit: str) -> dict:
    """Fusionne dans le ledger : chaque entree porte le commit et l'horodatage de SA mesure."""
    path = ledger_path()
    old = {}
    if path.exists():
        try:
            old = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            old = {}
    fichiers = dict(old.get("fichiers", {}))
    maintenant = int(time.time())
    for rel, c in nouveau.items():
        fichiers[rel] = dict(c, _commit=commit, _at=maintenant)
    doc = {"_ecrit_le": maintenant, "fichiers": fichiers}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return doc


def _print_inventaire(par_fichier: dict, perimetre: list[str]) -> int:
    rouges = sorted(r for r, c in par_fichier.items() if c.get("verdict") == "ROUGE")
    vides = sorted(r for r, c in par_fichier.items() if c.get("verdict") == "VIDE")
    nonjoues = sorted(r for r, c in par_fichier.items() if c.get("verdict") == "NON JOUE")
    verts = [r for r, c in par_fichier.items() if c.get("verdict") == "VERT"]
    joues = len(par_fichier)
    ecartes = len(perimetre) - joues
    print("")
    print("[462] INVENTAIRE -- perimetre %d, JOUES %d, ECARTES %d (non balayes dans cette passe)"
          % (len(perimetre), joues, ecartes))
    print("[462]   VERT %d | ROUGE %d | VIDE %d | NON JOUE %d"
          % (len(verts), len(rouges), len(vides), len(nonjoues)))
    for rel in rouges:
        c = par_fichier[rel]
        print("  ROUGE  %s  (p=%d f=%d e=%d s=%d, %.0f s)"
              % (rel, c.get("passed", 0), c.get("failed", 0), c.get("error", 0),
                 c.get("skipped", 0), c.get("time", 0.0)))
        for m in c.get("messages", [])[:2]:
            print("         | %s" % m)
        if c.get("passed", 0) == 0 and c.get("skipped", 0) and not c.get("failed", 0):
            print("         | FICHIER INTEGRALEMENT SKIPPE -- zero assertion evaluee (#455)")
    for rel in vides:
        print("  VIDE   %s  (aucun test collecte)" % rel)
    for rel in nonjoues:
        print("  NONJOUE %s  (%s)" % (rel, par_fichier[rel].get("raison", "?")))
    return len(rouges) + len(nonjoues)


def _do_report(perimetre: list[str]) -> int:
    path = ledger_path()
    if not path.exists():
        print("[462] aucun ledger (%s) -- l'etat des %d fichiers live est INCONNU, pas vert"
              % (path, len(perimetre)))
        return 1
    doc = json.loads(path.read_text(encoding="utf-8"))
    fichiers = doc.get("fichiers", {})
    maintenant = int(time.time())
    jamais = [r for r in perimetre if r not in fichiers]
    print("[462] ledger %s" % path)
    print("[462] %d/%d fichier(s) du perimetre ont un statut connu ; %d JAMAIS mesure(s)"
          % (len(perimetre) - len(jamais), len(perimetre), len(jamais)))
    ages = sorted(((maintenant - int(c.get("_at", 0))) / 86400.0, r)
                  for r, c in fichiers.items() if r in perimetre)
    if ages:
        print("[462] anciennete de la mesure : min %.1f j, max %.1f j, mediane %.1f j"
              % (ages[0][0], ages[-1][0], ages[len(ages) // 2][0]))
    return _print_inventaire({r: c for r, c in fichiers.items() if r in perimetre}, perimetre)


def _do_collect(perimetre: list[str]) -> int:
    """Collecte SEULE sur tout le perimetre. Aucun runner monte -- balayage EXHAUSTIF abordable."""
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    started = time.time()
    p = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q",
                        "-p", "no:cacheprovider", *perimetre],
                       cwd=str(_PYDIR), env=env, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    elapsed = time.time() - started
    lignes = (p.stdout or "").splitlines()
    erreurs = [l for l in lignes if l.startswith("ERROR ") or " ERROR " in l]
    print("[462] --collect : %d fichier(s), rc=%d en %.1f s" % (len(perimetre), p.returncode,
                                                                elapsed))
    print("[462]   %s" % (lignes[-1] if lignes else "(aucune sortie)"))
    if p.returncode != 0 or erreurs:
        print("[462] VERDICT: FAIL -- la COLLECTE echoue (import/syntaxe/fixture inconnue) :")
        for l in erreurs[:20]:
            print("    %s" % l)
        return 1
    print("[462] VERDICT: PASS -- les %d fichiers live COLLECTENT ; cela ne dit RIEN de leur "
          "verdict a l'execution" % len(perimetre))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--list", action="store_true", help="imprime le perimetre et sort")
    ap.add_argument("--collect", action="store_true",
                    help="collecte SEULE sur tout le perimetre (aucun runner monte)")
    ap.add_argument("--run", action="store_true", help="joue un sous-ensemble BORNE")
    ap.add_argument("--report", action="store_true", help="relit le ledger, ne joue rien")
    ap.add_argument("--files", nargs="*", default=None,
                    help="chemins relatifs a scripts/python a jouer (sinon --sample)")
    ap.add_argument("--sample", type=int, default=0,
                    help="nombre de fichiers a jouer, pris dans l'ordre de RISQUE (les plus "
                         "anciennement touches d'abord)")
    ap.add_argument("--offset", type=int, default=0,
                    help="decalage dans l'ordre de risque (pour enchainer des tranches)")
    ap.add_argument("--jobs", type=int, default=MAX_JOBS,
                    help="processus paralleles (PLAFOND DUR %d)" % MAX_JOBS)
    ap.add_argument("--timeout", type=float, default=3600.0, help="timeout par worker (s)")
    ap.add_argument("--no-ledger", action="store_true", help="n'ecrit pas le ledger")
    args = ap.parse_args(argv)

    perimetre = live_files()

    if args.list:
        print("[462] %d fichier(s) `*_live.py`" % len(perimetre))
        for rel in perimetre:
            print("   ", rel)
        return 0
    if args.report:
        return _do_report(perimetre)
    if args.collect:
        return _do_collect(perimetre)
    if not args.run:
        print("[462] %d fichier(s) `*_live.py` dans le perimetre. Choisir un mode : "
              "--list / --collect / --run / --report" % len(perimetre))
        return 0

    if args.jobs > MAX_JOBS:
        print("[462] --jobs %d REFUSE : le plafond est %d (pump partage)" % (args.jobs, MAX_JOBS))
        return 2
    if args.files:
        cibles = [f.replace("\\", "/") for f in args.files]
        inconnus = [f for f in cibles if f not in perimetre]
        if inconnus:
            print("[462] hors perimetre : %s" % ", ".join(inconnus[:5]))
            return 2
    elif args.sample > 0:
        ages = _last_touch(perimetre)
        ordre = sorted(perimetre, key=lambda r: (ages.get(r, 0), r))
        cibles = ordre[args.offset:args.offset + args.sample]
        print("[462] echantillon par RISQUE (dernier commit le plus ANCIEN d'abord) : "
              "%d fichier(s), offset %d ; %d ECARTES de cette passe"
              % (len(cibles), args.offset, len(perimetre) - len(cibles)))
    else:
        print("[462] --run exige --files ou --sample N (un balayage COMPLET du parc live se "
              "compte en heures et sature la session partagee)")
        return 2

    with tempfile.TemporaryDirectory() as td:      # tmpdir SYSTEME, jamais scripts/python (#455)
        par_fichier = _do_run(cibles, min(args.jobs, len(cibles)), args.timeout, Path(td))
    if not args.no_ledger:
        _merge_ledger(par_fichier, _head())
        print("[462] ledger mis a jour : %s" % ledger_path())
    rc = _print_inventaire(par_fichier, cibles)
    print("[462] %s" % ("VERDICT: FAIL -- %d fichier(s) ROUGE/NON JOUE" % rc if rc
                        else "VERDICT: PASS -- tous les fichiers JOUES sont verts"))
    return 1 if rc else 0


if __name__ == "__main__":
    sys.exit(main())
