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

INIT live = amorce-si-besoin : `autoBootExtraire` SANS `force` est idempotent
(no-op si déjà chaud ; cycle de nav complet si froid / après reinject — agent frais
⇒ ptr null ⇒ vrai amorce).
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

# --- #455 : un FICHIER qui n'a RIEN confronte est un vert qui ment ------------
#
# Les hooks vivent dans `green_skip_guard` (module a part, PAS ici) pour deux raisons :
# un conftest non-racine ne peut pas declarer `pytest_plugins` (interdit depuis pytest 7),
# et le cliquet `probe_455_all_skipped_file.py` doit pouvoir charger le garde par
# `-p green_skip_guard` sur des fichiers de test SYNTHETIQUES, hors de cette suite.
# Cet import EST le cablage : sans lui, le garde existe et ne garde rien -- le cliquet le
# verifie en deposant un fichier inerte sous `tests/` et en exigeant un rouge SANS `-p`.
# Il DERIVE la liste ci-dessous de `dir(green_skip_guard)` : un hook ajoute au garde et
# oublie ici fait rougir son etape 2.
#
# DEUX criteres, un seul vice. Le fichier 100 % SKIPPE (#455) se lit sur un BILAN ; le
# fichier a 0 TEST COLLECTE (#455-r3) n'emet aucun report et ne se lit que sur la COLLECTE
# -- d'ou `pytest_collectreport`.
#
# DISTINCT du bloc « un SKIP harnais indisponible est un ECHEC » plus bas (#77) : celui-la
# lit la RAISON d'un skip, test par test ; celui-ci lit un BILAN, fichier par fichier. Un
# skip de MONTAGE ne porte aucun marqueur de harnais et passe donc intact le premier.
from green_skip_guard import (                        # noqa: F401,E402  (hooks pytest)
    pytest_collectreport, pytest_deselected, pytest_sessionstart, pytest_sessionfinish,
    pytest_terminal_summary)

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
# Les autres causes d'indisponibilite du harnais (build KO, pas de session, amorce
# KO) sont converties en ECHEC par `pytest_runtest_makereport` plus bas -- y compris
# quand elles viennent d'un test qui construit son runner LUI-MEME sans passer par la
# fabrique `build_runner`.
_CAP_MARKER = "runner cap reached"

# MODE DRAIN cote host (#285) -- meme FORME d'indisponibilite que le cap, autre
# CAUSE. Le cap dit « toutes les places sont prises » ; le drain dit « je n'en
# donne plus, une fenetre de maintenance s'ouvre ». Dans les deux cas la conduite
# correcte est identique : ATTENDRE puis reessayer, et si ca ne se libere pas,
# ECHOUER ROUGE -- jamais rendre un skip vert.
#
# La chaine du message, de bout en bout :
#   frida/host/drain.ts  DRAIN_MARKER          (source de verite)
#     -> throw DrainRefusedError
#     -> router  503 + { error: <message> }
#     -> rl_collect_batch._http  parse le corps de la HTTPError et le REND
#     -> rl_duel.cmd_build  imprime `init_resp["error"]` sur stderr
#     -> ICI  la sous-chaine est retrouvee dans la sortie du subprocess
# Si la constante change d'un cote sans l'autre, l'attente et la conversion en
# rouge sautent SILENCIEUSEMENT (retour au skip vert) -- c'est le seul maillon
# du dispositif qui ne se signale pas tout seul. Garde : `probe_285_drain_gate.py`.
_DRAIN_MARKER = "runner creation paused"

# Marqueurs qui justifient d'ATTENDRE plutot que d'abandonner.
_WAIT_MARKERS = (_CAP_MARKER, _DRAIN_MARKER)
_CAP_WAIT_S = float(os.environ.get("TACTICUS_RUNNER_CAP_WAIT_S", "300"))
_CAP_POLL_S = float(os.environ.get("TACTICUS_RUNNER_CAP_POLL_S", "15"))


def _wait_reason(out: str) -> str | None:
    """Marqueur d'indisponibilite TEMPORAIRE present dans `out`, sinon None."""
    return next((m for m in _WAIT_MARKERS if m in out), None)


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
    _DRAIN_MARKER,
    "pas de session Frida active",
    "amorce KO",
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
        # #363 : le cache du seed TERTIAIRE est indexe par label de runner (`build#<rid>`). Un rid
        # est RECYCLE par un build ulterieur -> sans cette purge, le prochain runner du meme id
        # heriterait des reliques du precedent, en silence.
        try:
            from engine.runner.snapshot import clear_ability_states_cache
            clear_ability_states_cache("build#%d" % int(e["rid"]))
        except Exception:
            pass                                      # engine non importable (collecte a vide)
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
    """Session Frida résolue + amorce-si-besoin (doctrine : amorce avant tout RPC).
    Skip si pas de session ou amorce KO — toute la suite se confronte au live.

    #363 — LIE AUSSI LE TRANSPORT RPC AMBIANT (`snapshot.bind_live_rpc`) pour la durée de la
    session pytest. C'est ce qui rend le seed de l'ability TERTIAIRE (l'item RELIQUE ÉQUIPÉ, #357)
    ACTIF PAR DÉFAUT dans TOUTE la suite live : `load_state(dv, ob, snap)` va chercher
    `unitAbilityStates` elle-même, sans qu'aucun des ~620 call-sites ait à le demander. Le binding
    est ici, et pas sur la fixture `rpc`, parce que TOUT test live tire `live_session` (directement
    ou via `rpc`/`build_runner`) alors que treize fichiers font leurs RPC eux-mêmes.

    Coût mesuré AVANT branchement (`probe_363_ability_states_channel.py --volet cost`, build
    `rnca9r7q6c`) : un seul RPC de 33 ms par bataille (cache par runner), contre 312 à 1347 ms pour
    la capture que le test fait déjà. Un test qui veut l'état d'AVANT #357 passe
    `ability_states=False` explicitement — `None` ne veut plus dire « rien ».

    `TACTICUS_NO_AMBIENT_RPC=1` débranche l'ambiant : c'est la MUTATION qui fait rougir
    `test_363_ability_states_default_live.py` (une garde qu'on ne sait pas faire échouer ne garde
    rien). Usage attendu : vérifier cette garde, jamais un mode de travail."""
    try:
        sid = host._resolve_session()
    except Exception as e:                            # pas de host / pas de session
        pytest.skip(f"pas de session Frida active (lance Tacticus + inject): {e}")
    w = _unwrap(host._rpc(sid, "autoBootExtraire", [{}], timeout=180))
    if not (isinstance(w, dict) and w.get("ok")):
        pytest.skip(f"amorce KO (jeu indisponible): {str(w)[:200]}")

    def _ambient(method: str, body=None, timeout: float = 60):
        return _unwrap(host._rpc(sid, method, [body] if body is not None else [], timeout=timeout))

    from engine.runner.snapshot import bind_live_rpc, clear_ability_states_cache, unbind_live_rpc
    if os.environ.get("TACTICUS_NO_AMBIENT_RPC") != "1":
        bind_live_rpc(_ambient)
    try:
        yield sid
    finally:
        unbind_live_rpc()
        clear_ability_states_cache()


@pytest.fixture(scope="session")
def rpc(host, live_session):
    """`rpc("decisionView", {"runnerId": rid})` → résultat déballé.

    #363 — ce transport est AUSSI LIÉ COMME AMBIANT (`snapshot.bind_live_rpc`) le temps de la
    session pytest. C'est ce qui rend le seed de l'ability TERTIAIRE (l'item RELIQUE ÉQUIPÉ, #357)
    ACTIF PAR DÉFAUT dans TOUTE la suite live : `load_state(dv, ob, snap)` va alors chercher
    `unitAbilityStates` elle-même, sans qu'aucun des ~620 call-sites ait à le demander. Coût mesuré
    avant branchement (`probe_363_ability_states_cost.py`) : 33 ms par bataille — un seul RPC, mis
    en cache par runner — contre 312 à 1347 ms pour la capture que le test fait déjà.

    Un test qui veut l'état d'AVANT #357 (contre-épreuve « sans rail ») passe `ability_states=False`
    explicitement ; `None` ne veut plus dire « rien »."""
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
        # Indisponibilite TEMPORAIRE (cap sature, ou host en DRAIN) : on ATTEND
        # puis on reessaie, plutot que d'abandonner. Un cap se libere quand les
        # autres agents disposent au fil de l'eau ; un drain se leve quand la
        # fenetre de maintenance se referme. cf. bloc « file d'attente » en tete.
        waited = 0.0
        while (not state.exists()) and _wait_reason(out) and waited < _CAP_WAIT_S:
            time.sleep(_CAP_POLL_S)
            waited += _CAP_POLL_S
            out = _attempt()
        if not state.exists():
            reason = _wait_reason(out)
            if reason == _DRAIN_MARKER:
                pytest.fail(
                    f"host toujours en DRAIN apres {waited:.0f}s d'attente -- "
                    f"AUCUNE validation n'a eu lieu (ce n'est PAS un skip vert). "
                    f"La creation de runner est suspendue le temps d'une fenetre "
                    f"de maintenance ; les runners en place restent pilotables. "
                    f"Attendre la levee (GET /api/admin/drain) ou relever "
                    f"TACTICUS_RUNNER_CAP_WAIT_S. Detail: {out[-300:]}",
                    pytrace=False)
            if reason == _CAP_MARKER:
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


@pytest.fixture(scope="module")
def arcaneshield_stage(build_runner, rpc):
    """MONTAGE `ArcaneShield` (Thaumachus) : roster MIXTE + positions DRIVEES — cf.
    `tests/engine/runner/_arcane_shield_stage.py` pour le detail du roster et les scores attendus.

    Owner `thousSorcerer` + trois amis choisis pour SEPARER les trois termes non-distance du score de
    tri natif (`Sum(3*distance, faction, chaos, owner)`) : un ThousandSons (meme faction), un autre
    Chaos, un non-Chaos. `stage.load()` rend un `State` neuf par scenario, `stage.place(state, {role:
    distance})` impose la geometrie voulue.

    Portee MODULE : le runner est monte une fois par fichier de test qui s'en sert, les scenarios se
    partagent les memes captures live (un montage = une bataille, pas une par assertion)."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "engine", "runner"))
    from _arcane_shield_stage import build_stage        # noqa: E402
    return build_stage(build_runner, rpc)


@pytest.fixture(scope="module")
def repair_stage(build_runner, rpc):
    """MONTAGE `Repair` (#298) : un repareur trait `Mechanic` + un ami MECANIQUE BLESSE —
    cf. `tests/engine/runner/_repair_stage.py` pour le roster et le detail des quatre etages
    natifs qu'il permet de separer.

    `advance=0` (aucun tour IA joue) + `damaged_repairee` (`--unit-stat
    <cible>:RemainingHealth=…`) : la seule variable entre ce montage et son controle est la
    SANTE de la cible. `--hp-player` ne convient PAS — il ecrit `Health` ET `RemainingHealth`,
    donc l'unite reste a 100 % et `AttackQuery$$IsDamagedUnit` reste faux.

    Portee MODULE : un runner par fichier de test qui s'en sert."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "engine", "runner"))
    from _repair_stage import build_stage             # noqa: E402
    return build_stage(rpc, build_runner=build_runner,
                       hp_player=None, advance=0, damaged_repairee=2000)


@pytest.fixture(scope="session")
def live_runner(build_runner):
    """runnerId d'une bataille LIVE isolée (auto-disposée). Lecture seule côté
    pathfinding. Seed `PATHFIND_SEED` = simple générateur.

    SEULE fixture de ce conftest partagée entre PLUSIEURS modules : la libérer en fin
    de module la tuerait sous les fichiers suivants. Aucun `keep=True` n'est nécessaire —
    sa portée `session` est LUE sur la fixture elle-même (cf. `pytest_fixture_setup`)."""
    return build_runner(os.environ.get("PATHFIND_SEED", "777"))["rid"]
