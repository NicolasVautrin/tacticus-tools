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
# partage par tous les pytest concurrents. Avec plusieurs agents en parallele,
# le `build` de l'un DISPOSAIT le runner de l'autre (le scoped-replace lit
# l'ancien runnerId dans le state-file et le dispose) -> faux echecs non
# reproductibles. Le suffixe PID isole les processus ; le compteur ajoute
# l'isolation INTRA-session (deux runners construits par la meme session
# coexistent au lieu de se remplacer). `TACTICUS_PYTEST_STATE_PREFIX` permet
# de deporter les state-files ailleurs (chemin ABSOLU, sans extension).
STATE_PREFIX = Path(os.environ.get(
    "TACTICUS_PYTEST_STATE_PREFIX", str(ROOT / "data" / "_pytest_duel_state")))
_state_seq = itertools.count()


def _new_state_path() -> Path:
    """Chemin de state-file neuf, propre a CE processus et a CE build."""
    return Path(f"{STATE_PREFIX}-{os.getpid()}-{next(_state_seq)}.json")


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
    """Fabrique de runners ISOLÉS frais, AUTO-NETTOYÉS en fin de session.

    La coexistence est le DÉFAUT côté hooks (`initAndStart` ne dispose plus
    jamais les runners frères ; cap dur MAX_RUNNERS) — le runner de travail de
    l'utilisateur n'est jamais nuké. Chaque runner créé par les tests est
    libéré via `disposeRunner` au teardown → aucun orphelin, le cap respire.

    Renvoie `build(seed="777", extra=None, board="MC1_67") -> {"rid": int, "my_team": int}`.
    Le seed n'est qu'un générateur de bataille, hors critère (l'invariant testé tient pour
    toute bataille). Un `--board` est OBLIGATOIRE depuis #159 (le seed BC est un skeleton dont
    le board par défaut n'a pas de spawns 5v5) : défaut `MC1_67` (arène), régénéré par
    `dump_boards.py`. `extra` = args `rl_duel build` supplémentaires (ex. 1v1 minimal + `--crit`
    pour la slice crit) ; si `extra` fournit déjà `--board`/`--board-pool`, le défaut est omis."""
    created: list[tuple[int, Path]] = []

    def _build(seed: str = "777", extra: list[str] | None = None,
               board: str = "MC1_67") -> dict:
        extra = list(extra or [])
        board_args = [] if any(x in ("--board", "--board-pool") for x in extra) \
            else ["--board", board]
        state = _new_state_path()
        # Purge AVANT le build : sans ça un build KO passerait inaperçu si un
        # state-file traînait (PID recyclé, run précédent tué) — on relirait un
        # runnerId périmé au lieu de skipper.
        state.unlink(missing_ok=True)
        proc = subprocess.run(
            [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
             "--state-file", str(state), *board_args, *extra],
            cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8",
            errors="replace")
        if not state.exists():
            pytest.skip(f"build runner KO (rl_duel): "
                        f"{(proc.stderr or proc.stdout or '')[-300:]}")
        st = json.loads(state.read_text())
        rid = st["runnerId"]
        created.append((rid, state))
        return {"rid": rid, "my_team": st.get("myTeam", 1)}

    yield _build

    # teardown : dispose tous les runners de test (idempotent ; removed=false si déjà parti)
    # puis retire les state-files — sinon ils s'accumulent dans data/ à chaque run.
    for rid, state in created:
        try:
            host._rpc(live_session, "disposeRunner", [{"runnerId": rid}], timeout=20)
        except Exception:
            pass
        state.unlink(missing_ok=True)


@pytest.fixture(scope="session")
def live_runner(build_runner):
    """runnerId d'une bataille LIVE isolée (auto-disposée). Lecture seule côté
    pathfinding. Seed `PATHFIND_SEED` = simple générateur."""
    return build_runner(os.environ.get("PATHFIND_SEED", "777"))["rid"]
