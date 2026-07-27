"""Fixtures partagées de la suite de tests du moteur Python (`engine/`).

PRINCIPE (validé) : **chaque test se confronte au LIVE** — l'oracle est le moteur
natif en cours d'exécution, jamais un snapshot gelé (un gelé = proxy qui peut
diverger en silence ; la doctrine du projet = le live est la vérité). La suite est
donc un harnais d'AGRÉMENT property-based :

  • INDÉPENDANT de la version du jeu : on lit l'état LIVE (boardGraph, decisionView,
    …), aucune tuile/RVA/valeur hardcodée.
  • INDÉPENDANT du seed : assertions GÉNÉRIQUES sur toutes les unités/tuiles de la
    bataille courante. Le seed ne sert qu'à *bootstrapper* une bataille si aucun
    runner n'existe — il n'entre jamais dans le critère pass/fail.
  • Pas de session → SKIP propre (on confronte le live, ou rien).

INIT live = warmup-if-needed : `warmupGameSingletons` SANS `force` est idempotent
(no-op si déjà chaud ; cycle de nav complet si froid / après reinject — agent frais
⇒ ptr null ⇒ vrai warmup).
"""
from __future__ import annotations

import itertools
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[1]          # scripts/python
ROOT = Path(__file__).resolve().parents[3]           # racine repo
# State-file DEDIE aux tests — jamais le data/duel_state.json par defaut :
# depuis le replace scope de `rl_duel build` (2026-07-03), un build dispose
# le runner enregistre dans SON state-file ; sur le fichier partage par
# defaut, ca disposerait le runner de travail de l'utilisateur.
#
# UNIQUE PAR PROCESSUS *ET* PAR BUILD (2026-07-25) : le nom etait FIXE, donc
# partage par tous les pytest concurrents (plusieurs agents worktree partagent
# le meme `data/`). Le `build` de l'un DISPOSAIT le runner de l'autre : le
# scoped-replace de `rl_duel build` lit l'ancien runnerId dans le state-file et
# le dispose -> faux echecs non reproductibles. Le suffixe PID isole les
# processus ; le compteur ajoute l'isolation INTRA-session (deux runners
# construits par la meme session coexistent au lieu de se remplacer).
#
# Override : `TACTICUS_PYTEST_STATE_PREFIX` (chemin ABSOLU, sans extension) pour
# deporter les state-files ailleurs. `TACTICUS_PYTEST_STATE` (chemin ABSOLU d'un
# .json) est accepte pour compatibilite — son suffixe est retire et le chemin
# sert de prefixe, on ne revient PAS a un fichier unique.
#
# SOUS `logs/`, PAS `data/` (2026-07-27) : `data/` est VERSIONNE depuis f467e64 et ne
# contient que des ENTREES (symbols, boards, seed-bc, i2). Un state-file y est une
# SORTIE, et `git check-ignore` le confirmait non ignore -- une passe interrompue
# laissait `data/_pytest_duel_state-<pid>-<n>.json` dans `git status`, exactement ce
# que le garde-fou « rien de produit par un run ne va dans data/ » doit rendre visible.
_state_env = os.environ.get("TACTICUS_PYTEST_STATE_PREFIX") \
    or os.environ.get("TACTICUS_PYTEST_STATE")
STATE_PREFIX = (Path(_state_env).with_suffix("") if _state_env
                else ROOT / "logs" / "_pytest_duel_state")
STATE_PREFIX.parent.mkdir(parents=True, exist_ok=True)
_state_seq = itertools.count()


def _new_state_path() -> Path:
    """Chemin de state-file neuf, propre a CE processus et a CE build."""
    return Path(f"{STATE_PREFIX}-{os.getpid()}-{next(_state_seq)}.json")


# --- File d'attente sur le cap de runners (#77, volet client) -----------------
#
# Cote hooks, `initAndStart` REFUSE SEC quand MAX_RUNNERS est atteint : pas de
# file d'attente, l'erreur remonte telle quelle. Le state-file n'est donc pas
# ecrit -> le fixture rendait un `pytest.skip`. Or plusieurs agents worktree
# partagent la MEME session Frida : le cap se sature en fonctionnement NORMAL, et
# une passe entiere devenait `sssssss` — des `s` qui RESSEMBLENT a des succes
# alors que RIEN n'a ete valide (mesure du 2026-07-25 : 7/7 tests skippes,
# runners 86 + 116-124 tous legitimement occupes par deux agents).
#
# Deux corrections ici, cote CLIENT (aucune reinjection requise) :
#   1. ATTENDRE qu'un slot se libere (les autres agents disposent au fil de l'eau)
#      au lieu d'abandonner au premier refus ;
#   2. si le cap tient jusqu'au bout, ECHOUER FORT (`pytest.fail`) au lieu de
#      skipper : « je n'ai pas pu valider » n'est pas « il n'y avait rien a
#      valider ». Un skip vert sur un cap plein est un faux negatif silencieux.
# Les autres causes d'indisponibilite du harnais (build KO, pas de session, warmup
# KO) sont converties en ECHEC par `pytest_runtest_makereport` plus bas -- y compris
# quand elles viennent d'un test qui construit son runner LUI-MEME sans passer par la
# fabrique `build_runner`.
_CAP_MARKER = "runner cap reached"
_CAP_WAIT_S = float(os.environ.get("TACTICUS_RUNNER_CAP_WAIT_S", "300"))
_CAP_POLL_S = float(os.environ.get("TACTICUS_RUNNER_CAP_POLL_S", "15"))


# --- Liberation des runners AU FIL DE L'EAU (#77) ------------------------------
#
# AVANT : `build_runner` empilait TOUS les runners construits et ne les disposait
# qu'au teardown de SESSION. Une passe de 9 tests gardait donc 9 des 10 slots
# pendant toute sa duree, alors que chaque runner n'est utile que sur une fraction
# de la passe -> un seul agent affamait tous les autres (mesure du 2026-07-25 :
# runners 86 + 116-124, cap 10/10, 7/7 tests d'un autre agent skippes).
#
# MAINTENANT : chaque runner est libere par SON PROPRIETAIRE REEL, des que la
# portee de ce proprietaire se termine.
#
# QUI est le proprietaire : on ne devine pas, on lit DEUX signaux de pytest.
#
#   `pytest_fixture_setup`  encadre la construction d'une fixture -> on empile SA
#                           portee. Le sommet de pile donne directement la duree de
#                           vie du runner qu'elle construit.
#   `pytest_runtest_call`   encadre la phase d'APPEL d'un test -> distingue « le
#                           corps du test a appele la fabrique » du reste.
#
#   pile NON VIDE          -> duree de vie = portee de la fixture au sommet
#   pile vide + phase APPEL-> le CORPS du test        -> fin de CE test
#   pile vide + hors appel -> fixture de SESSION      -> fin de session
#
# POURQUOI CE DERNIER CAS EXISTE (mesure du 2026-07-25, pas une supposition) : le
# hook `pytest_fixture_setup` de CE conftest n'est PAS appele pour les fixtures de
# portee SESSION. Les hooks d'un conftest sont resolus par CHEMIN : une fixture de
# session est construite au niveau du noeud `Session`, dont le chemin est la rootdir
# (`scripts/python`) -- `tests/conftest.py` n'y est pas applicable. Sonde : le hook
# n'a vu que `module:`/`class:`/`function:`, jamais `session:host`,
# `session:live_session`, `session:build_runner`, `session:live_runner`.
# Consequence : `live_runner` etait etiquete « test », donc dispose en fin de
# premier module -> `runner 170 not found` dans le fichier suivant.
#
# POURQUOI PAS UN CONFTEST RACINE : il suffirait a faire porter le hook sur le
# noeud Session, mais couterait deux fichiers de plus (le hook + un module d'etat
# partage) pour une information que la composition ci-dessus donne deja.
#
# ROBUSTE AU CHANGEMENT : si une version de pytest se mettait a appeler le hook
# pour les fixtures de session, la pile serait non vide et on lirait « session » --
# MEME REPONSE. Et toute portee inconnue est rabattue sur SESSION : liberer PLUS
# TARD ne coute qu'un slot, liberer plus TOT casse les tests qui reutilisent.
#
# Etat de MODULE (pas de fixture) : une fixture autouse qui dependrait du ledger
# tirerait `live_session` sur CHAQUE test, y compris les tests offline -- ils
# exigeraient alors une session Frida pour rien.
_LEDGER: list[dict] = []
_DISPOSER = None                      # callable(rid) -> None, pose par build_runner
_FIXTURE_SCOPES: list[str] = []       # pile des portees en cours de construction
_IN_TEST_CALL = False                 # True pendant la phase d'APPEL d'un test
# portee pytest -> etiquette de duree de vie utilisee par le ledger
_SCOPE_OWNER = {"function": "test", "class": "class", "module": "module",
                "package": "session", "session": "session"}


@pytest.hookimpl(wrapper=True)
def pytest_fixture_setup(fixturedef, request):
    """Encadre la construction d'une fixture -> on connait SA portee.
    N'est PAS appele pour les fixtures de portee session (cf. bloc ci-dessus)."""
    _FIXTURE_SCOPES.append(getattr(fixturedef, "scope", "session"))
    try:
        return (yield)
    finally:
        _FIXTURE_SCOPES.pop()


@pytest.hookimpl(wrapper=True)
def pytest_runtest_call(item):
    """Marque la phase d'APPEL : pile vide ICI = c'est le corps du test."""
    global _IN_TEST_CALL
    _IN_TEST_CALL = True
    try:
        return (yield)
    finally:
        _IN_TEST_CALL = False


# --- Un SKIP « harnais indisponible » est un ECHEC, pas un succes (#77) --------
#
# La suite entiere est un harnais d'AGREMENT LIVE : un test qui n'a pas pu joindre
# le jeu n'a rien confronte. Le rendre en `s` le fait lire comme un succes -- c'est
# le faux negatif le plus couteux du projet (mesure du 2026-07-25 : 7/7 `s` lus
# comme du vert ; et lors du crash de ce soir, TOUTE passe lancee pendant la fenetre
# morte serait ressortie `sssss`).
#
# La fabrique `build_runner` echoue deja franchement sur le cap. Mais 13 fichiers de
# test construisent leur runner EUX-MEMES (`subprocess.run(rl_duel build)`) et
# retombent sur un `pytest.skip("build runner KO")` local : ils contournent la file
# d'attente ET l'echec franc. Plutot que d'editer 13 fichiers -- et de laisser le
# 14e recopier le motif demain -- on ferme la classe entiere ICI, au moment du
# RAPPORT : quelle que soit la ligne qui a leve le skip, si sa raison dit que le
# harnais etait indisponible, le resultat devient ROUGE.
#
# Echappatoire explicite : `TACTICUS_ALLOW_GREEN_SKIP=1` (usage attendu : inspecter
# la collecte sans jeu lance). Elle doit rester un geste CONSCIENT, jamais un defaut.
_HARNESS_DOWN_MARKERS = (
    "build runner KO",
    _CAP_MARKER,
    "pas de session Frida active",
    "warmup KO",
)


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item, call):
    """Convertit un skip « harnais indisponible » en echec (cf. bloc ci-dessus)."""
    report = yield
    if not report.skipped or os.environ.get("TACTICUS_ALLOW_GREEN_SKIP") == "1":
        return report
    lr = report.longrepr
    # skip -> longrepr = (fichier, ligne, "Skipped: <raison>") ; sinon on stringifie
    reason = str(lr[2]) if isinstance(lr, tuple) and len(lr) == 3 else str(lr)
    if any(m in reason for m in _HARNESS_DOWN_MARKERS):
        report.outcome = "failed"
        report.longrepr = (
            "HARNAIS INDISPONIBLE -- ce test n'a RIEN confronte au live.\n"
            "Converti en ECHEC : un `s` se lirait comme un succes alors qu'aucune\n"
            "assertion n'a ete evaluee (cf. conftest, bloc « un SKIP harnais »).\n"
            f"\nRaison d'origine : {reason}\n"
            "\nA verifier, dans cet ordre : le jeu tourne ? une session Frida vivante\n"
            "(`/api/admin/status`, champ `.session` SINGULIER) ? le cap de runners\n"
            "(MAX_RUNNERS) est-il sature par des runners a disposer ?\n"
            "Inspection sans jeu : TACTICUS_ALLOW_GREEN_SKIP=1.")
    return report


def _release_runners(owners: set[str]) -> None:
    """Dispose (idempotent) les runners du ledger dont l'owner est dans `owners`."""
    kept = []
    for e in _LEDGER:
        if e["owner"] not in owners:
            kept.append(e)
            continue
        if _DISPOSER is not None:
            try:
                _DISPOSER(e["rid"])
            except Exception:
                pass                                  # deja parti / session morte
        e["state"].unlink(missing_ok=True)
    _LEDGER[:] = kept


@pytest.fixture(autouse=True)
def _release_test_owned_runners():
    """Fin de CHAQUE test : rend les runners que le test a construits lui-meme."""
    yield
    _release_runners({"test"})


@pytest.fixture(scope="class", autouse=True)
def _release_class_owned_runners():
    """Fin de CHAQUE classe : rend les runners de ses fixtures de classe."""
    yield
    _release_runners({"class"})


@pytest.fixture(scope="module", autouse=True)
def _release_module_owned_runners():
    """Fin de CHAQUE module : rend les runners de ses fixtures de module."""
    yield
    _release_runners({"module"})


def _unwrap(r):
    """Déballe l'enveloppe {result: …} des RPC host."""
    return r.get("result") if isinstance(r, dict) and "result" in r else r


@pytest.fixture(scope="session")
def host():
    """Import PARESSEUX de rl_collect_batch (tire psycopg3, etc.)."""
    import rl_collect_batch as R
    return R


@pytest.fixture(scope="session")
def live_session(host):
    """Session Frida résolue + warmup-if-needed (doctrine : warmup avant tout RPC).
    Skip si pas de session ou warmup KO — toute la suite se confronte au live."""
    try:
        sid = host._resolve_session()
    except Exception as e:                            # pas de host / pas de session
        pytest.skip(f"pas de session Frida active (lance Tacticus + inject): {e}")
    w = _unwrap(host._rpc(sid, "warmupGameSingletons", [{}], timeout=180))
    if not (isinstance(w, dict) and w.get("ok")):
        pytest.skip(f"warmup KO (jeu indisponible): {str(w)[:200]}")
    return sid


@pytest.fixture(scope="session")
def rpc(host, live_session):
    """`rpc("decisionView", {"runnerId": rid})` → résultat déballé."""
    sid = live_session

    def _call(method: str, body=None, timeout: float = 60):
        return _unwrap(host._rpc(sid, method, [body] if body is not None else [],
                                 timeout=timeout))
    return _call


@pytest.fixture(scope="session")
def build_runner(host, live_session):
    """Fabrique de runners ISOLÉS frais, libérés PAR LEUR PROPRIÉTAIRE RÉEL.

    La coexistence est le DÉFAUT côté hooks (`initAndStart` ne dispose plus
    jamais les runners frères ; cap dur MAX_RUNNERS) — le runner de travail de
    l'utilisateur n'est jamais nuké. Chaque runner créé par les tests est
    libéré via `disposeRunner` au teardown → aucun orphelin, le cap respire.

    Renvoie `build(seed="777", extra=None, board="MC1_67") -> {"rid": int, "my_team": int}`.
    Le seed n'est qu'un générateur de bataille, hors critère (l'invariant testé tient pour
    toute bataille). Un `--board` est OBLIGATOIRE depuis #159 (le seed BC est un skeleton dont
    le board par défaut n'a pas de spawns 5v5) : défaut `MC1_67` (arène), régénéré par
    `dump_boards.py`. `extra` = args `rl_duel build` supplémentaires (ex. 1v1 minimal + `--crit`
    pour la slice crit) ; si `extra` fournit déjà `--board`/`--board-pool`, le défaut est omis.

    CAP SATURÉ (#77) : le build ATTEND qu'un slot se libère (`TACTICUS_RUNNER_CAP_WAIT_S`,
    défaut 300 s) et ÉCHOUE FORT s'il ne l'obtient pas — jamais un skip vert.

    LIBÉRATION (#77) : la durée de vie du runner est celle de la FIXTURE qui l'a
    construit (portée lue sur `fixturedef.scope`) ; construit par le corps d'un test,
    il meurt avec ce test. `keep=True` = dérogation explicite « garde-le jusqu'à la fin
    de session ». cf. le bloc « Libération des runners AU FIL DE L'EAU » en tête."""
    global _DISPOSER
    _DISPOSER = lambda rid: host._rpc(                       # noqa: E731
        live_session, "disposeRunner", [{"runnerId": rid}], timeout=20)

    def _build(seed: str = "777", extra: list[str] | None = None,
               board: str = "MC1_67", keep: bool = False) -> dict:
        extra = list(extra or [])
        board_args = [] if any(x in ("--board", "--board-pool") for x in extra) \
            else ["--board", board]
        state = _new_state_path()
        argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
                "--state-file", str(state), *board_args, *extra]

        def _attempt() -> str:
            # Purge AVANT le build : sans ça un build KO passerait inaperçu si un
            # state-file traînait (PID recyclé, run précédent tué) — on relirait
            # un runnerId périmé au lieu de skipper.
            state.unlink(missing_ok=True)
            p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True,
                               text=True, encoding="utf-8", errors="replace")
            return (p.stderr or p.stdout or "")

        out = _attempt()
        # Cap sature : on ATTEND un slot (les autres agents disposent au fil de
        # l'eau) plutot que d'abandonner. cf. bloc « file d'attente » en tete.
        waited = 0.0
        while (not state.exists()) and _CAP_MARKER in out and waited < _CAP_WAIT_S:
            time.sleep(_CAP_POLL_S)
            waited += _CAP_POLL_S
            out = _attempt()
        if not state.exists():
            if _CAP_MARKER in out:
                pytest.fail(
                    f"cap de runners toujours sature apres {waited:.0f}s d'attente "
                    f"-- AUCUNE validation n'a eu lieu (ce n'est PAS un skip vert). "
                    f"Libere des slots (disposeRunner) ou releve "
                    f"TACTICUS_RUNNER_CAP_WAIT_S. Detail: {out[-300:]}",
                    pytrace=False)
            pytest.skip(f"build runner KO (rl_duel): {out[-300:]}")
        st = json.loads(state.read_text())
        rid = st["runnerId"]
        # Propriétaire (cf. bloc en tête) : portée de la fixture en construction ;
        # à défaut, la phase tranche — corps du test, ou fixture de session (le
        # seul cas où le hook de fixture ne passe pas ici).
        if keep:
            owner = "session"
        elif _FIXTURE_SCOPES:
            owner = _SCOPE_OWNER.get(_FIXTURE_SCOPES[-1], "session")
        else:
            owner = "test" if _IN_TEST_CALL else "session"
        _LEDGER.append({"rid": rid, "state": state, "owner": owner})
        return {"rid": rid, "my_team": st.get("myTeam", 1)}

    yield _build

    # Filet de fin de session : tout ce qui reste (les `session`, et les rescapés
    # d'une interruption avant le teardown de leur portée). Idempotent.
    _release_runners({"test", "class", "module", "session"})


@pytest.fixture(scope="session")
def live_runner(build_runner):
    """runnerId d'une bataille LIVE isolée (auto-disposée). Lecture seule côté
    pathfinding. Seed `PATHFIND_SEED` = simple générateur.

    SEULE fixture de ce conftest partagée entre PLUSIEURS modules : la libérer en fin
    de module la tuerait sous les fichiers suivants. Aucun `keep=True` n'est nécessaire —
    sa portée `session` est LUE sur la fixture elle-même (cf. `pytest_fixture_setup`)."""
    return build_runner(os.environ.get("PATHFIND_SEED", "777"))["rid"]
