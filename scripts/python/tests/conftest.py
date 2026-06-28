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

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[1]          # scripts/python
ROOT = Path(__file__).resolve().parents[3]           # racine repo
STATE = ROOT / "data" / "duel_state.json"


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

    `rl_duel build --keep` ⇒ COEXISTENCE : ne dispose JAMAIS les runners existants
    (le runner de travail de l'utilisateur n'est jamais nuké). Chaque runner créé
    par les tests est libéré via `disposeRunner` au teardown → aucun orphelin.

    Renvoie `build(seed="777") -> {"rid": int, "my_team": int}`. Le seed n'est qu'un
    générateur de bataille, hors critère (l'invariant testé tient pour toute bataille)."""
    created: list[int] = []

    def _build(seed: str = "777") -> dict:
        proc = subprocess.run(
            [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--keep"],
            cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8",
            errors="replace")
        if not STATE.exists():
            pytest.skip(f"build runner KO (rl_duel): "
                        f"{(proc.stderr or proc.stdout or '')[-300:]}")
        st = json.loads(STATE.read_text())
        rid = st["runnerId"]
        created.append(rid)
        return {"rid": rid, "my_team": st.get("myTeam", 1)}

    yield _build

    # teardown : dispose tous les runners de test (idempotent ; removed=false si déjà parti).
    for rid in created:
        try:
            host._rpc(live_session, "disposeRunner", [{"runnerId": rid}], timeout=20)
        except Exception:
            pass


@pytest.fixture(scope="session")
def live_runner(build_runner):
    """runnerId d'une bataille LIVE isolée (auto-disposée). Lecture seule côté
    pathfinding. Seed `PATHFIND_SEED` = simple générateur."""
    return build_runner(os.environ.get("PATHFIND_SEED", "777"))["rid"]
