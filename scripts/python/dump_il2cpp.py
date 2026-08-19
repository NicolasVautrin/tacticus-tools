#!/usr/bin/env python3
"""Regenere `data/il2cpp_full.json` depuis le jeu EN COURS, via le one-shot Frida.

C'est la SOURCE de toute la chaine de symboles :
    jeu lance + injection Frida
      scripts/frida/dump-il2cpp-full.js           parcourt le runtime IL2CPP
        -> data/il2cpp_full.json
      preprocess_il2cpp_dump.py                   -> data/il2cpp_{methods,classes,enums}.tsv
      GhidraApplyIl2CppSymbols.java               -> noms appliques dans Ghidra

Le one-shot tourne dans SA propre session (`stop_previous=False` : il ne tue pas la session
principale) et emet le dump en UN message `{t:"il2cpp_full", methods, classes, enums}` capture
dans le log jsonl de la session. On le desenveloppe et on l'ecrit au format attendu par
`preprocess_il2cpp_dump.py` (cles `methods`/`classes`/`enums` a la racine).

NB : ne demande PAS de amorce — le one-shot lit les metadonnees IL2CPP, peuplees au demarrage
du process, pas les singletons de jeu que l'amorcette amorce.

Usage :
    python scripts/python/dump_il2cpp.py --pid <pid>     # pid du Tacticus vise
    python scripts/python/dump_il2cpp.py                 # auto : pid de la session courante
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HOST = "http://127.0.0.1:8765"
ONESHOT = REPO / "scripts" / "frida" / "dump-il2cpp-full.js"
# Ce script est le SEUL consommateur legitime des run-logs : il recupere son dump de
# ~40 Mo dans le journal jsonl de sa session one-shot. Depuis que les run-logs sont
# OPT-IN (le host n'en ecrit plus par defaut), il doit donc demander le sien
# EXPLICITEMENT via `log_dir` dans la requete -- cf. le POST plus bas.
LOG_DIR = REPO / "logs" / "sessions"
OUT = REPO / "logs" / "il2cpp_full.json"


def _post(path: str, body: dict, timeout: int = 120) -> dict:
    req = urllib.request.Request(HOST + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _get(path: str, timeout: int = 30) -> dict:
    with urllib.request.urlopen(HOST + path, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def current_pid() -> int | None:
    try:
        sess = (_get("/api/admin/status") or {}).get("session")
        return int(sess["pid"]) if sess and sess.get("pid") else None
    except Exception:
        return None


def wait_for_payload(run_id: int, timeout_s: int = 600) -> dict | None:
    """Attend le message `il2cpp_full` dans le log jsonl de la session one-shot."""
    deadline = time.time() + timeout_s
    log_path = None
    while time.time() < deadline:
        if log_path is None:
            hits = sorted(LOG_DIR.glob("run-%d_*.jsonl" % run_id))
            if hits:
                log_path = hits[-1]
                print("log : %s" % log_path.name, flush=True)
        if log_path and log_path.exists():
            with log_path.open(encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    if '"il2cpp_full"' not in line:
                        continue
                    try:
                        env = json.loads(line)
                    except json.JSONDecodeError:
                        continue          # ligne encore en cours d'ecriture
                    payload = (env.get("payload") or {}).get("payload") or env.get("payload") or {}
                    if isinstance(payload, dict) and payload.get("t") == "il2cpp_full":
                        return payload
            size = log_path.stat().st_size
            print("  ... %d Mo ecrits" % (size // 1048576), flush=True)
        time.sleep(3)
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pid", type=int, help="pid Tacticus (defaut : celui de la session courante)")
    ap.add_argument("--timeout", type=int, default=600)
    args = ap.parse_args()

    pid = args.pid or current_pid()
    if not pid:
        print("REFUS : aucun pid. Injecter d'abord (POST /api/admin/inject) ou passer --pid.")
        return 2
    if not ONESHOT.is_file():
        print("REFUS : one-shot introuvable : %s" % ONESHOT)
        return 2

    source = ONESHOT.read_text(encoding="utf-8")
    print("one-shot : %s (%d Ko) -> pid %d" % (ONESHOT.name, len(source) // 1024, pid))

    res = _post("/api/scripts/run", {
        "mode": "attach", "pid": pid, "source": source,
        "stop_previous": False,          # NE PAS tuer la session principale
        "log_dir": str(LOG_DIR),         # OBLIGATOIRE : sans lui le host n'ecrit plus
                                         # de run-log, et wait_for_payload ne trouve rien
    })
    run_id = res.get("run_session_id")
    print("session one-shot : %s (status=%s)" % (run_id, res.get("status")))
    if run_id is None:
        print("REFUS : pas de run_session_id -> %r" % res)
        return 1

    payload = wait_for_payload(int(run_id), args.timeout)
    try:
        _post("/api/scripts/%d/stop" % int(run_id), {}, timeout=30)
    except Exception:
        pass

    if payload is None:
        print("ECHEC : aucun message il2cpp_full recu en %ds." % args.timeout)
        return 1

    doc = {k: payload[k] for k in ("methods", "classes", "enums") if k in payload}
    missing = [k for k in ("methods", "classes", "enums") if k not in doc]
    if missing:
        print("ECHEC : cles absentes du dump : %s" % ", ".join(missing))
        return 1

    OUT.write_text(json.dumps(doc), encoding="utf-8")
    print("OK  %s  (%d methodes, %d classes, %d enums, %.1f Mo)"
          % (OUT.relative_to(REPO), len(doc["methods"]), len(doc["classes"]),
             len(doc["enums"]), OUT.stat().st_size / 1048576))
    print("Suite : python scripts/python/preprocess_il2cpp_dump.py   (pose l'estampille)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
