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

ROUGE = un `failure` (assertion evaluee, echouee), OU `passed == 0 and skipped > 0` (#455 : zero
assertion evaluee). SETUP = que des `error`, aucun `failure` -- cf. `_verdict`.

VALIDITE D'UN VERDICT (#465)
---------------------------
Le blob repond a << ce CONTENU a-t-il ete mesure ? >>, JAMAIS a << l'a-t-il ete sur CET arbre ? >>.
Or un verdict NON-VERT depend du depot ENTIER, pas du seul fichier de test. Mesure du 2026-08-04 :
les trois ROUGES du ledger etaient PERIMES -- rejoues, ils rendaient 2 passed, 5 passed, et une
cause corrigee entre-temps -- et ils ont failli faire renvoyer trois PR a leurs auteurs.

`verdict_effectif` est le foyer UNIQUE de cette validite, et il est asymetrique par construction :

  * VERT ne PERIME JAMAIS. Un vert perime est CONSERVATEUR (c'est le trou B, #462-r1, ouvert et
    chiffre) ; le perimer rendrait la gate inapplicable et rouvrirait le trou d'origine -- des
    << non mesure >> silencieux sur 419 fichiers.
  * Un NON-VERT mesure AILLEURS que sur cet arbre devient `A RECONFRONTER`. Il reste LISTE et il
    BLOQUE la gate exactement comme avant : la peremption d'un non-vert ne peut pas rendre la gate
    permissive, puisque seul VERT la fait passer. C'est structurel, pas une precaution.

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

#: Ce qui doit changer pour que ce cliquet puisse changer d'avis.
#:
#: Il ne vaut QUE pour l'argv de banque (`--gate origin/master`). Les modes `--collect` et
#: `--run` MONTENT des runners et lisent tout ce que les tests lisent : eux ne sont pas bornables
#: par des chemins, et ce n'est pas ce que la banque joue.
#: L'attestation est keyee sur le BLOB du fichier de test : un fichier live qui ne change pas
#: garde son verdict meme quand `HEAD` avance, donc seuls le fichier live lui-meme et le ledger
#: peuvent faire basculer la gate.
DECLENCHEUR = {
    "chemins": ("scripts/python/tests/*", "scripts/python/tests/**",
                "scripts/ratchets-462-live-attestations.json",
                "scripts/python/probe_462_live_tests_status.py"),
    "build": False,
    "toujours": False,
    "raison": "La gate croise le diff depuis le MERGE-BASE avec `git ls-files "
              "scripts/python/tests` filtre sur `*_live.py`, puis exige pour chacun une "
              "attestation VERTE au ledger versionne -- ces deux entrees, et rien d'autre.",
}

#: Plafond DUR de processus montant un runner (`CLAUDE.md`) : le pump est PARTAGE avec les autres
#: agents. Depasser degrade tout le monde, y compris l'appelant.
MAX_JOBS = 4

#: Verdict d'une entree dont la MESURE ne porte pas sur cet arbre. Ce n'est pas un verdict sur le
#: depot -- c'est l'aveu qu'on n'en a pas. Il BLOQUE la gate au meme titre qu'un ROUGE.
A_RECONFRONTER = "A RECONFRONTER"

#: Distance en COMMITS au-dela de laquelle un verdict NON-VERT mesure sur un ANCETRE cesse d'etre
#: tenu pour un fait sur cet arbre.
#:
#: L'unite est le COMMIT, pas le JOUR, et c'est une mesure qui l'impose : le 2026-08-04, les trois
#: ROUGES geles du ledger avaient 0,4 JOUR d'age. Tout seuil temporel utile (>= 1 j) les laissait
#: passer ; tout seuil qui les aurait captures (< 0,4 j) aurait perime les mesures fraiches. Sur ce
#: depot (~40 commits/jour, 5 agents en vol) le temps est un proxy BRUITE du churn -- le nombre de
#: commits est la mesure directe de ce qui peut avoir change sous un verdict.
#:
#: 20 est un curseur, pas un seuil derive : il tient la boucle de merge (qui ajoute 2 a 3 commits
#: par PR entre la mesure et sa relecture) sans porter un rouge au-dela d'une demi-journee. Se
#: tromper vers le HAUT ne fait que reconduire le statu quo (un rouge affiche comme frais) ; se
#: tromper vers le BAS ne coute RIEN en blocage, seulement un rejeu de plus.
DISTANCE_MAX_COMMITS = 20


def repo_root() -> Path:
    """Racine du checkout COURANT (worktree compris) -- jamais l'arbre principal (#434)."""
    return _PYDIR.parents[1]


def ledger_path() -> Path:
    """Dernier statut CONNU par fichier, avec le BLOB du fichier au moment de la mesure.

    VERSIONNE, et l'asymetrie avec les poids de `probe_457` est le point. Des poids perimes ne
    coutent que du mur ; un statut qu'on ne voit pas est exactement le vice qu'on repare. Sous
    `logs/` (gitignore), le ledger MOURRAIT avec le worktree : chaque agent repartirait de
    << aucune mesure >>, et l'anciennete -- la seule chose que ce dispositif rend visible --
    serait invisible.

    Sous `scripts/`, PAS `scripts/python/` : la banque enumere cet arbre en parallele (#455), et
    `probe_440` R3 rougit sur toute ecriture qui y apparait. C'est le meme emplacement que
    `ratchets-457-footprints.json`, pour la meme raison."""
    return repo_root() / "scripts" / "ratchets-462-live-attestations.json"


def _blobs(rels: list[str]) -> dict:
    """{rel -> hash git du CONTENU de l'arbre de travail}. UN SEUL `git hash-object`.

    Le blob, pas le commit : c'est ce qui rend une attestation INVALIDE des que le fichier de test
    change, et VALIDE quand il ne change pas -- meme si le HEAD a avance. Keyer sur le commit
    invaliderait TOUT a chaque commit, donc rendrait la gate inapplicable."""
    if not rels:
        return {}
    racine = repo_root()
    r = subprocess.run(["git", "-C", str(racine), "hash-object", "--stdin-paths"],
                       input="\n".join("scripts/python/" + rel for rel in rels) + "\n",
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    lignes = [l.strip() for l in (r.stdout or "").splitlines() if l.strip()]
    if len(lignes) != len(rels):
        return {}                     # desaccord de cardinalite : on ne PRETEND pas savoir
    return dict(zip(rels, lignes))


def _live_in_diff(ref: str) -> tuple:
    """(fichiers live touches par MOI depuis `ref`, raison).

    Le diff part du MERGE-BASE, pas de `ref` lui-meme -- semantique `...`, celle de GitHub pour une
    PR. La difference n'est pas cosmetique : `git diff origin/master` compare `origin/master` a mon
    arbre de travail, donc il inclut EN SENS INVERSE tout ce que les autres agents ont pousse
    depuis mon point de branchement. Sur ce depot (~40 commits/jour, 5 agents en vol), la gate
    exigerait alors d'attester des fichiers live que je n'ai jamais touches -- un rouge qui n'accuse
    personne, et le plus sur moyen de la faire desarmer.

    L'arbre de TRAVAIL est inclus (pas de `HEAD` en second terme) : un agent qui n'a pas encore
    commite doit voir sa propre modification, sinon la gate ne mordrait qu'apres le commit."""
    racine = repo_root()
    mb = subprocess.run(["git", "-C", str(racine), "merge-base", ref, "HEAD"],
                        capture_output=True, text=True, encoding="utf-8", errors="replace")
    base = (mb.stdout or "").strip()
    if mb.returncode != 0 or not base:
        # Ni merge-base ni ref lisible -> on ne PRETEND pas savoir. C'est un refus, pas un vert.
        verif = subprocess.run(["git", "-C", str(racine), "rev-parse", "--verify", ref + "^{commit}"],
                               capture_output=True, text=True)
        if verif.returncode != 0:
            return None, "ref `%s` inconnue de git" % ref
        base = ref                       # histoires sans ancetre commun : on prend `ref` tel quel
    r = subprocess.run(["git", "-C", str(racine), "diff", "--name-only", base],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        return None, "diff depuis `%s` impossible" % base[:12]
    prefix = "scripts/python/"
    live = set(live_files())
    vus = {l.strip()[len(prefix):] for l in (r.stdout or "").splitlines()
           if l.strip().startswith(prefix)}
    return sorted(vus & live), ("%d fichier(s) live touche(s) depuis le merge-base %s (avec %s)"
                                % (len(vus & live), base[:8], ref))


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


def _git(*args) -> tuple:
    r = subprocess.run(["git", "-C", str(repo_root()), *args], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout or "").strip()


def etat_commit(sha: str, head: str) -> tuple:
    """(etat, distance) du commit d'une mesure vis-a-vis de CET arbre. 4 etats, tous mesures.

    `HEAD`     -- mesure sur cet arbre exactement. Le verdict est un FAIT sur ce depot.
    `ancetre`  -- mesure sur un point de MON histoire, `distance` commits en arriere.
    `HORS`     -- le commit existe mais n'est PAS un ancetre : branche d'agent, tete de travail
                  abandonnee, commit d'avant un rebase. Le verdict ne porte sur AUCUN point de ma
                  ligne. C'est l'etat des trois rouges geles du 2026-08-04.
    `INCONNU`  -- pas de commit stocke, ou objet absent du depot (worktree disparu et objets gc).

    Mesure du 2026-08-04 sur les 254 entrees du ledger : 0 au HEAD, 17 ancetres, 237 HORS. Le
    regime NOMINAL est donc `HORS` -- une attestation est ecrite par un agent AVANT son rebase,
    donc son sha meurt au rebase. C'est precisement pourquoi cet etat ne doit jamais toucher les
    VERTS : il invaliderait 234 attestations vertes sur 251 et rouvrirait le trou de #462.

    Cout : un appel git par sha DISTINCT et NON-VERT (3 sur 254 au 2026-08-04). La forme naive --
    un appel par entree -- est ce qui avait deja coute 350 s a `_last_touch`."""
    if not sha or not head:
        return "INCONNU", -1
    if sha == head:
        return "HEAD", 0
    if _git("cat-file", "-e", sha + "^{commit}")[0] != 0:
        return "INCONNU", -1
    if _git("merge-base", "--is-ancestor", sha, head)[0] != 0:
        return "HORS", -1
    rc, out = _git("rev-list", "--count", sha + ".." + head)
    return "ancetre", (int(out) if rc == 0 and out.isdigit() else -1)


def verdict_effectif(entree: dict, head: str, cache: dict = None) -> tuple:
    """(verdict effectif, raison) -- LE foyer UNIQUE de la validite d'une entree du ledger.

    Les trois lecteurs (`--gate`, `--report`, `--stale`) passent par ici. Un garde-fou dont le
    verdict DERIVE entre ses lecteurs ne vaut rien -- c'est la lecon deja payee sur `host_inputs`.

    ASYMETRIE, et elle est le tout du dispositif :

      * VERT est rendu TEL QUEL, sans aucune condition sur le commit. Un vert perime est
        CONSERVATEUR -- c'est le trou B (#462-r1), ouvert, chiffre, et assume. Le perimer
        invaliderait 234 attestations sur 251 (mesure du 2026-08-04, cf. `etat_commit`) et
        redonnerait les << non mesure >> silencieux que #462 existe pour fermer.
      * Un NON-VERT n'est un fait sur CE depot que s'il a ete mesure sur cet arbre, ou assez pres.
        Sinon : `A RECONFRONTER`. Il reste liste, il reste bloquant -- seul le RECIT change.

    La peremption ne peut pas desserrer la gate : `_do_gate` ne laisse passer QUE `VERT`, et VERT
    ne passe jamais par une branche de peremption. Ce n'est pas une precaution, c'est la forme du
    code -- et `test_465_ledger_validite_offline.py` le balaie exhaustivement."""
    v = entree.get("verdict") or "?"
    if v == "VERT":
        return "VERT", ""
    sha = entree.get("_commit") or ""
    if cache is None:
        cache = {}
    if sha not in cache:
        cache[sha] = etat_commit(sha, head)
    etat, dist = cache[sha]
    if etat == "HEAD":
        return v, "mesure sur CET arbre"
    if etat == "INCONNU":
        return A_RECONFRONTER, ("mesure au commit %s, INCONNU de ce depot (branche d'agent "
                                "disparue) -- ce verdict ne porte sur aucun arbre lisible ici"
                                % (sha[:8] or "(aucun)"))
    if etat == "HORS":
        return A_RECONFRONTER, ("mesure au commit %s, HORS de l'histoire de ce checkout -- ce "
                                "verdict ne porte sur aucun point de ma ligne" % sha[:8])
    if dist < 0 or dist > DISTANCE_MAX_COMMITS:
        return A_RECONFRONTER, ("mesure %s commits en arriere (seuil %d) -- l'arbre a avance sous "
                                "ce verdict" % (dist if dist >= 0 else "?", DISTANCE_MAX_COMMITS))
    return v, "mesure %d commit(s) en arriere" % dist


def _last_touch(rels: list[str]) -> dict:
    """Date (epoch) du dernier commit ayant touche chaque fichier. Sert au tri par RISQUE.

    Un fichier dont la tranche n'a pas bouge depuis longtemps n'a pas ete rejoue depuis longtemps :
    c'est exactement le gisement ou un rouge peut dormir. Ce n'est PAS une preuve de rot -- juste un
    ordre de visite qui met les candidats les plus probables en tete d'un balayage BORNE.

    UN SEUL `git log`, pas un par fichier. Mesure du 2026-08-03 : la forme naive (417 sous-processus
    `git log -1`) coutait 350 s -- soit DEUX FOIS le mur du balayage qu'elle sert a ordonner."""
    prefix = "scripts/python/"
    voulus = set(rels)
    ages: dict = {}
    r = subprocess.run(["git", "-C", str(repo_root()), "log", "--format=@%ct", "--name-only",
                        "--", TESTS_DIR],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    horodatage = 0
    for line in (r.stdout or "").splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("@"):
            horodatage = int(line[1:]) if line[1:].isdigit() else 0
            continue
        # `git log` descend du plus RECENT au plus ancien -> la premiere occurrence est la bonne.
        if line.startswith(prefix):
            rel = line[len(prefix):]
            if rel in voulus and rel not in ages:
                ages[rel] = horodatage
    for rel in rels:
        ages.setdefault(rel, 0)          # jamais vu dans l'historique du repertoire
    return ages


# --------------------------------------------------------------------------------------------
# Execution bornee
# --------------------------------------------------------------------------------------------

def _classname_index(rels: list[str]) -> dict:
    """{classname pointe -> chemin relatif}. Le JUnit de pytest N'EMET PAS d'attribut `file`.

    Mesure du 2026-08-03 sur `junit_family=xunit2` (le defaut) : un `testcase` ne porte que
    `classname` et `name`. `classname` est le module pointe (`tests.engine.runner.test_x`), donc on
    reconstruit la correspondance DEPUIS le perimetre connu -- jamais l'inverse (rabattre un
    classname sur un chemin serait ambigu des qu'un repertoire contient un point)."""
    idx = {}
    for rel in rels:
        idx[rel[:-3].replace("/", ".")] = rel
    return idx


def _parse_junit(xml_path: Path, index: dict) -> dict:
    """{chemin relatif -> {passed, failed, error, skipped, xfailed, xpassed, time, messages}}.

    `xfail` compte comme JOUE, pas comme skip -- c'est la semantique de `green_skip_guard` (#455 :
    << l'assertion a bien ete evaluee, son echec etait attendu >>). Dans le XML un xfail sort en
    `<skipped type="pytest.xfail">` : sans cette distinction, un fichier entierement xfail serait
    rapporte ROUGE a tort."""
    res: dict = {}
    if not xml_path.exists():
        return res
    try:
        tree = ET.parse(str(xml_path))
    except ET.ParseError:
        return res
    for case in tree.getroot().iter("testcase"):
        rel = index.get(case.get("classname") or "")
        if not rel:
            continue
        e = res.setdefault(rel, {"passed": 0, "failed": 0, "error": 0, "skipped": 0,
                                 "xfailed": 0, "xpassed": 0, "time": 0.0, "messages": []})
        e["time"] += float(case.get("time") or 0.0)
        kind = None
        for child in case:
            if child.tag == "skipped":
                kind = "xfailed" if (child.get("type") or "") == "pytest.xfail" else "skipped"
            elif child.tag in ("failure", "error"):
                kind = "failed" if child.tag == "failure" else "error"
            else:
                continue
            if kind in ("failed", "error") and len(e["messages"]) < 3:
                msg = (child.get("message") or "").strip().replace("\n", " ")
                e["messages"].append("%s::%s -- %s" % (rel.rsplit("/", 1)[-1],
                                                       case.get("name") or "?", msg[:300]))
            break
        e[kind or "passed"] += 1
    return res


def _verdict(counts: dict) -> str:
    """ROUGE / SETUP / VERT / VIDE, aligne sur `green_skip_guard.fichiers_inertes` (#455).

    ROUGE si une ASSERTION a echoue (`<failure>`), ou si `passed == 0 and skipped > 0` SANS aucun
    xfail/xpass (zero assertion evaluee). VIDE = aucun test du tout : ce n'est pas un succes, c'est
    un perimetre qui s'effondre.

    SETUP (#465) = QUE des `<error>`, aucun `<failure>` : l'echec est survenu AVANT toute assertion
    (collecte, fixture, import). Meme convention que le `rc=99` de la banque -- et meme prudence :

      * SETUP dit OU l'echec est survenu, PAS A QUI il est imputable. Une fixture peut casser parce
        que le depot a regresse. Le probe ne CLASSE pas (#533) -- il situe.
      * SETUP est aussi BLOQUANT qu'un ROUGE (`_do_gate` ne laisse passer que VERT) et pese autant
        dans le code de sortie. Le distinguer sert la LECTURE, jamais l'indulgence.

    Ce qui l'a motive, mesure : `test_fabricator_claw_cap_live.py`, 10 `error` de setup sur un
    `ImportError` cite depuis le worktree d'un agent DISPARU -- lu au rapport comme un rouge du
    depot, alors que la cause etait fermee depuis (#462-r4c). Un `f=0 e=10` se lit d'un coup d'oeil
    quand le verdict le dit ; noye dans << ROUGE >>, il ne se lit pas.

    L'ordre compte : `failed` d'abord. Un fichier qui porte les DEUX a bien vu une assertion
    echouer -- c'est un verdict sur le depot, et il prime."""
    if counts.get("failed", 0):
        return "ROUGE"
    if counts.get("error", 0):
        return "SETUP"
    joues = counts.get("passed", 0) + counts.get("xfailed", 0) + counts.get("xpassed", 0)
    if joues == 0:
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
    index = _classname_index(files)
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
        vus = _parse_junit(r["xml"], index)
        for rel in r["files"]:
            c = vus.get(rel)
            if c is None:
                # Pas de report : le worker est mort avant d'y arriver (timeout, crash). NE PAS
                # le compter vert -- c'est exactement le mode de defaillance silencieux a eviter.
                par_fichier[rel] = {"verdict": "NON JOUE", "passed": 0, "failed": 0, "error": 0,
                                    "skipped": 0, "xfailed": 0, "xpassed": 0, "time": 0.0,
                                    "messages": [],
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
    """Fusionne dans le ledger : chaque entree porte le BLOB, le commit et l'horodatage de SA mesure.

    FUSION, jamais ecrasement : une passe ne mesure qu'une tranche, et ecraser perdrait le statut
    des fichiers non joues -- donc rendrait le ledger MUET sur eux, ce qui se lirait comme
    << jamais mesure >> alors qu'ils l'ont ete."""
    path = ledger_path()
    old = {}
    if path.exists():
        try:
            old = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            old = {}
    fichiers = dict(old.get("fichiers", {}))
    blobs = _blobs(sorted(nouveau))
    maintenant = int(time.time())
    for rel, c in nouveau.items():
        fichiers[rel] = {"verdict": c.get("verdict"), "passed": c.get("passed", 0),
                         "failed": c.get("failed", 0), "error": c.get("error", 0),
                         "skipped": c.get("skipped", 0), "xfailed": c.get("xfailed", 0),
                         "sec": round(float(c.get("time", c.get("sec", 0.0)) or 0.0), 1),
                         # Le SYMPTOME VERBATIM, garde tel quel. C'est la seule chose qu'un lecteur
                         # du ledger peut VENTILER (#533 : le probe ne classe pas PORT/MONTAGE/
                         # HARNAIS -- il ne peut pas ; il doit donc rendre ce qu'il a vu).
                         "messages": list(c.get("messages", []))[:3],
                         "_blob": blobs.get(rel), "_commit": commit, "_at": maintenant,
                         # TRACE, jamais critere (#465). La racine dit d'ou la mesure a ete prise,
                         # ce qui rend lisible << mesure dans le worktree d'un agent >>. Elle ne
                         # peut PAS servir a invalider : mesure du 2026-08-04, 237 des 254 entrees
                         # viennent d'un worktree d'agent DISPARU -- c'est le regime NOMINAL. Le
                         # critere qui discrimine est le COMMIT (cf. `etat_commit`), pas la racine.
                         "_root": str(repo_root()).replace("\\", "/")}
    doc = {"_ecrit_le": maintenant, "fichiers": fichiers}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return doc


def _unmeasured(perimetre: list) -> list:
    """Les fichiers du perimetre SANS mesure valide a leur blob courant.

    Trois cas y entrent, et ils sont le MEME etat -- NON MESURE :
      * absent du ledger (jamais joue) ;
      * present mais mesure sur un AUTRE blob (le fichier a change depuis) ;
      * present avec le verdict `NON JOUE` (une passe l'a vise mais n'a produit aucun report --
        worker tue, timeout, fenetre de maintenance ouverte en cours de tranche).

    Le troisieme est le plus traitre : une passe INTERROMPUE laisse des fichiers qu'on croit
    couverts. Un resultat partiel ne vaut rien, et le compter comme une mesure serait exactement
    la demi-couverture que ce dossier existe pour rendre visible."""
    path = ledger_path()
    fichiers = {}
    if path.exists():
        try:
            fichiers = json.loads(path.read_text(encoding="utf-8")).get("fichiers", {})
        except (OSError, ValueError):
            fichiers = {}
    blobs = _blobs(perimetre)
    out = []
    for rel in perimetre:
        e = fichiers.get(rel)
        if (e is None or e.get("verdict") == "NON JOUE"
                or not blobs.get(rel) or e.get("_blob") != blobs.get(rel)):
            out.append(rel)
    return out


def _do_gate(ref: str) -> int:
    """OFFLINE. Tout fichier live TOUCHE par le diff doit porter une attestation VERTE a SON blob.

    CE QUE CETTE GATE FERME, ET CE QU'ELLE NE FERME PAS -- la distinction est tout l'interet.

      * Elle FERME le trou mesure de #533 : `test_env_fire_tile_migration_live.py` a ete introduit
        ROUGE par `ad5692e7` et l'est reste 8 jours. Le fichier etait DANS LE DIFF de son propre
        commit (398 lignes modifiees). Une gate sur les fichiers live du diff l'aurait vu par
        CONSTRUCTION -- et son cout est nul : mesure du 2026-08-03 sur 1706 commits non-merge,
        1158 (68 %) ne touchent AUCUN fichier live, la mediane est 0 et le q3 est 1.

      * Elle NE FERME PAS le rot d'un fichier que PERSONNE ne touche (le cas
        `test_nightshroud_combat_live.py` : valide bit-exact le 2026-07-12, jamais retouche
        substantiellement depuis, ROUGE au balayage du 2026-08-03). Fermer celui-la demanderait la
        CLOTURE du graphe d'imports, dont le cout mesure est prohibitif sur sa queue : mediane 2
        fichiers, mais q3 64 et 320/1706 commits (19 %) au-dela de 100 fichiers, soit plus d'une
        demi-heure de live PAR PR. C'est le balayage periodique qui couvre ce cas, pas une gate.

    Le blob, pas le commit : l'attestation reste valide tant que le FICHIER DE TEST ne change pas.
    C'est ce qui la rend applicable -- et c'est aussi, exactement, sa limite ci-dessus."""
    cibles, raison = _live_in_diff(ref)
    if cibles is None:
        print("[462] gate : %s -- RIEN verifie, ce n'est pas un verdict" % raison)
        return 2
    print("[462] gate --since %s : %s" % (ref, raison))
    if not cibles:
        print("[462] VERDICT: PASS -- aucun fichier live touche, rien a attester")
        return 0
    fichiers = entrees_du_ledger()
    blobs = _blobs(cibles)
    head, cache = _head(), {}
    manquants = []
    for rel in cibles:
        e = fichiers.get(rel)
        blob = blobs.get(rel)
        if e is None:
            manquants.append((rel, "AUCUNE attestation"))
        elif not blob or e.get("_blob") != blob:
            manquants.append((rel, "attestation PERIMEE (le fichier a change depuis la mesure)"))
        else:
            # #465 : SEUL `VERT` passe, et `verdict_effectif` ne rend jamais `VERT` pour une entree
            # qui ne l'etait pas -- la peremption ne peut donc que DEPLACER un refus, jamais en
            # lever un. Ce qu'elle change est le RECIT : << rejoue-le >> plutot que << c'est
            # casse >>, ce qui evite de renvoyer une PR pour un verdict mesure sur un autre arbre.
            eff, pourquoi = verdict_effectif(e, head, cache)
            if eff == A_RECONFRONTER:
                manquants.append((rel, "attestation NON VERTE (%s) et %s : %s"
                                  % (e.get("verdict"), A_RECONFRONTER, pourquoi)))
            elif eff != "VERT":
                manquants.append((rel, "attestation %s -- reproduite sur cet arbre (%s)"
                                  % (eff, pourquoi)))
    for rel, pourquoi in manquants:
        print("  MANQUANT %s -- %s" % (rel, pourquoi))
    if manquants:
        print("[462] VERDICT: FAIL -- %d/%d fichier(s) live du diff sans attestation VERTE."
              % (len(manquants), len(cibles)))
        print("[462] Pour attester : python probe_462_live_tests_status.py --run --since %s" % ref)
        return 1
    print("[462] VERDICT: PASS -- les %d fichier(s) live du diff portent une attestation VERTE "
          "a leur blob courant" % len(cibles))
    return 0


def _print_inventaire(par_fichier: dict, perimetre: list[str], raisons: dict = None) -> int:
    """Imprime l'inventaire et rend le nombre d'entrees NON VERTES.

    LE CODE DE SORTIE NE BOUGE PAS (#465). `A RECONFRONTER` et `SETUP` sont des RE-ETIQUETAGES de
    ce qui comptait deja comme ROUGE : l'ensemble compte est identique a la ligne pres. Le defaut
    mesure le 2026-08-04 etait un defaut de LECTURE -- << j'ai failli lire ces 3 rouges comme des
    regressions de la soiree >> -- pas de code de sortie. Ne pas y toucher supprime tout risque de
    permissivite, y compris ceux qu'on n'aurait pas prevus."""
    raisons = raisons or {}

    def _sel(v):
        return sorted(r for r, c in par_fichier.items() if c.get("verdict") == v)

    rouges, setups, vides = _sel("ROUGE"), _sel("SETUP"), _sel("VIDE")
    nonjoues, areconf = _sel("NON JOUE"), _sel(A_RECONFRONTER)
    verts = [r for r, c in par_fichier.items() if c.get("verdict") == "VERT"]
    # Un verdict que ce probe ne connait pas (entree tronquee, format d'une version anterieure,
    # valeur future) ne doit PAS s'evaporer : la selection par etiquette l'ignorait, donc il ne
    # figurait ni au rapport ni au code de sortie -- il se lisait comme un vert. Meme vice que
    # #455-r3, une porte plus loin. Trouve par le test exhaustif de #465, pas a l'oeil.
    connus = set(rouges) | set(setups) | set(vides) | set(nonjoues) | set(areconf) | set(verts)
    autres = sorted(r for r in par_fichier if r not in connus)
    joues = len(par_fichier)
    ecartes = len(perimetre) - joues

    def _ligne(etiquette, rel, note=""):
        c = par_fichier[rel]
        # `time` est la cle du parse JUnit, `sec` celle du ledger : ce rapport sert les DEUX
        # sources (une passe qui vient de tourner, et une relecture par `--report`).
        print("  %-7s %s  (p=%d f=%d e=%d s=%d xf=%d, %.0f s)%s"
              % (etiquette, rel, c.get("passed", 0), c.get("failed", 0), c.get("error", 0),
                 c.get("skipped", 0), c.get("xfailed", 0),
                 float(c.get("time", c.get("sec", 0.0)) or 0.0), note))
        for m in c.get("messages", [])[:2]:
            print("         | %s" % m)
        if not c.get("failed", 0) and not c.get("error", 0) and c.get("skipped", 0):
            print("         | FICHIER INTEGRALEMENT SKIPPE -- zero assertion evaluee (#455)")

    print("")
    print("[462] INVENTAIRE -- perimetre %d, JOUES %d, ECARTES %d (non balayes dans cette passe)"
          % (len(perimetre), joues, ecartes))
    print("[462]   VERT %d | ROUGE %d | SETUP %d | VIDE %d | NON JOUE %d | %s %d | AUTRE %d"
          % (len(verts), len(rouges), len(setups), len(vides), len(nonjoues),
             A_RECONFRONTER, len(areconf), len(autres)))
    for rel in rouges:
        _ligne("ROUGE", rel)
    for rel in setups:
        _ligne("SETUP", rel)
        print("         | ECHEC HORS ASSERTION (collecte/fixture/import). Cela dit OU, pas A QUI "
              "(#533) -- bloquant au meme titre qu'un ROUGE.")
    if areconf:
        # LA reparation de #465. Ces entrees ne sont PAS des verdicts sur ce depot : les lire
        # comme des regressions a failli couter le renvoi de trois PR a leurs auteurs.
        print("[462] --- %s : mesures AILLEURS que sur cet arbre. Ce ne sont pas des verdicts "
              "sur ce depot ; ils comptent, mais ils accusent le LEDGER, pas le code." % A_RECONFRONTER)
        for rel in areconf:
            _ligne("RECONF", rel, "  <- %s" % raisons.get(rel, "mesure hors de cet arbre"))
        print("[462] --- pour trancher : python probe_462_live_tests_status.py --run --stale")
    for rel in vides:
        # #455-r3 : un fichier dont les tests ont DISPARU n'emet aucun bilan, donc il se lit comme
        # un succes. Il COMPTE dans le verdict -- le lister sans le compter serait exactement la
        # forme d'invisibilite que ce dossier repare.
        print("  VIDE   %s  (0 test collecte -- zero assertion evaluee, cf. #455-r3)" % rel)
    for rel in nonjoues:
        print("  NONJOUE %s  (%s)" % (rel, par_fichier[rel].get("raison", "?")))
    for rel in autres:
        print("  AUTRE  %s  (verdict inconnu de ce probe : %r -- entree tronquee ou format d'une "
              "autre version)" % (rel, par_fichier[rel].get("verdict")))
    # Formule INVARIANTE plutot que somme de categories : le code de sortie est le nombre
    # d'entrees dont le verdict n'est pas VERT. Une categorie oubliee ne peut donc plus rendre une
    # entree invisible -- c'est exactement ce qui vient d'arriver avec les verdicts inconnus.
    return sum(1 for c in par_fichier.values() if c.get("verdict") != "VERT")


def entrees_du_ledger() -> dict:
    path = ledger_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("fichiers", {})
    except (OSError, ValueError):
        return {}


def _relire(fichiers: dict, perimetre: list) -> tuple:
    """({rel -> entree au verdict EFFECTIF}, {rel -> raison}). Le seul point de relecture du ledger.

    `verdict_effectif` n'est appele QUE sur les non-VERTS (il rend VERT sans toucher a git), donc
    le cout git est proportionnel aux rouges, pas aux 254 entrees."""
    head, cache, vus, raisons = _head(), {}, {}, {}
    for rel in perimetre:
        e = fichiers.get(rel)
        if e is None:
            continue
        eff, pourquoi = verdict_effectif(e, head, cache)
        vus[rel] = dict(e, verdict=eff)
        if pourquoi:
            raisons[rel] = pourquoi
    return vus, raisons


def _do_report(perimetre: list[str], ref: str = None) -> int:
    path = ledger_path()
    if not path.exists():
        print("[462] aucun ledger (%s) -- l'etat des %d fichiers live est INCONNU, pas vert"
              % (path, len(perimetre)))
        return 1
    if ref:
        # #465 : `--report --since` etait AVALE en silence (le mode `--report` sortait avant de
        # regarder `--since`), donc une lecture qu'on croyait bornee au diff rendait TOUT le
        # ledger. C'est ce qui a fait lire trois rouges anciens comme << les rouges de la soiree >>.
        cibles, raison = _live_in_diff(ref)
        if cibles is None:
            print("[462] --report --since : %s -- RIEN lu, ce n'est pas un verdict" % raison)
            return 2
        print("[462] --report --since %s : %s" % (ref, raison))
        perimetre = cibles
    fichiers = entrees_du_ledger()
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
    vus, raisons = _relire(fichiers, perimetre)
    return _print_inventaire(vus, perimetre, raisons)


def _stale(perimetre: list) -> list:
    """Les fichiers dont le ledger porte un verdict EFFECTIF non VERT -- la voie de sortie de #465.

    Distincte de `_unmeasured`, et les deux notions ne doivent pas fusionner : `_unmeasured` = << on
    n'a AUCUNE mesure >> (absent, autre blob, `NON JOUE`), `_stale` = << on a une mesure, elle
    accuse quelque chose, et il faut savoir si c'est encore vrai ICI >>. Sans ce mode, `A
    RECONFRONTER` nommerait le probleme sans donner la sortie -- un rouge resterait gele par une
    autre porte."""
    fichiers = entrees_du_ledger()
    vus, _ = _relire(fichiers, perimetre)
    return sorted(r for r, c in vus.items() if c.get("verdict") != "VERT")


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
    ap.add_argument("--gate", metavar="REF", default=None,
                    help="OFFLINE : tout fichier live touche par le diff REF..arbre de travail "
                         "doit porter une attestation VERTE a son blob courant")
    ap.add_argument("--since", metavar="REF", default=None,
                    help="avec --run : joue les fichiers live TOUCHES par le diff REF..arbre "
                         "de travail (c'est le perimetre que --gate exige d'attester)")
    ap.add_argument("--files", nargs="*", default=None,
                    help="chemins relatifs a scripts/python a jouer (sinon --sample)")
    ap.add_argument("--sample", type=int, default=0,
                    help="nombre de fichiers a jouer, pris dans l'ordre de RISQUE (les plus "
                         "anciennement touches d'abord)")
    ap.add_argument("--stale", action="store_true",
                    help="avec --run : rejoue les fichiers dont le ledger porte un verdict "
                         "EFFECTIF non VERT (ROUGE/SETUP/VIDE/NON JOUE/" + A_RECONFRONTER + "). "
                         "C'est la voie de sortie d'un rouge mesure sur un AUTRE arbre : sans "
                         "elle, il resterait gele par une autre porte. Bornable par --sample.")
    ap.add_argument("--unmeasured", action="store_true",
                    help="avec --run --sample N : ne prend QUE les fichiers absents du ledger ou "
                         "dont le blob a change. C'est la reprise correcte d'un balayage borne "
                         "(ou interrompu) -- un fichier NON MESURE n'est ni rouge ni vert, et le "
                         "re-jouer est la seule facon de le sortir de cet etat.")
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
    if args.gate:
        return _do_gate(args.gate)
    if args.report:
        return _do_report(perimetre, args.since)
    if args.collect:
        return _do_collect(perimetre)
    if not args.run:
        print("[462] %d fichier(s) `*_live.py` dans le perimetre. Choisir un mode : "
              "--list / --collect / --run / --report" % len(perimetre))
        return 0

    if args.jobs > MAX_JOBS:
        print("[462] --jobs %d REFUSE : le plafond est %d (pump partage)" % (args.jobs, MAX_JOBS))
        return 2
    if args.since:
        cibles, raison = _live_in_diff(args.since)
        if cibles is None:
            print("[462] --since : %s -- RIEN joue" % raison)
            return 2
        print("[462] --since %s : %s" % (args.since, raison))
        if not cibles:
            print("[462] aucun fichier live touche -- rien a jouer, VERDICT: PASS")
            return 0
    elif args.files:
        cibles = [f.replace("\\", "/") for f in args.files]
        inconnus = [f for f in cibles if f not in perimetre]
        if inconnus:
            print("[462] hors perimetre : %s" % ", ".join(inconnus[:5]))
            return 2
    elif args.stale:
        cibles = _stale(perimetre)
        print("[462] --stale : %d/%d fichier(s) au verdict EFFECTIF non VERT dans le ledger"
              % (len(cibles), len(perimetre)))
        if not cibles:
            print("[462] rien a reconfronter -- VERDICT: PASS")
            return 0
        if args.sample > 0:
            cibles = cibles[args.offset:args.offset + args.sample]
            print("[462] borne a %d fichier(s) (offset %d)" % (len(cibles), args.offset))
    elif args.sample > 0:
        candidats = perimetre
        if args.unmeasured:
            candidats = _unmeasured(perimetre)
            print("[462] --unmeasured : %d/%d fichier(s) SANS mesure valide (absents du ledger, "
                  "ou mesures sur un AUTRE blob)" % (len(candidats), len(perimetre)))
        ages = _last_touch(candidats)
        ordre = sorted(candidats, key=lambda r: (ages.get(r, 0), r))
        cibles = ordre[args.offset:args.offset + args.sample]
        print("[462] echantillon par RISQUE (dernier commit le plus ANCIEN d'abord) : "
              "%d fichier(s), offset %d ; %d ECARTES de cette passe"
              % (len(cibles), args.offset, len(perimetre) - len(cibles)))
    else:
        print("[462] --run exige --since REF, --files, --stale ou --sample N (un balayage COMPLET "
              "du parc live se compte en heures et sature la session partagee)")
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
