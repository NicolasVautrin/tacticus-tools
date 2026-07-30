#!/usr/bin/env python
"""probe_321_runner_registry_drift.py -- QUI compte les runners, et QUI gate ?

LA QUESTION BINAIRE : `GET /api/runners` publie-t-il des runners VIVANTS, et est-ce
CE compteur que `MAX_RUNNERS` gate ?

REPONSE, derivee du code (pas du chiffre) :
  * `MAX_RUNNERS` (= 50) vit dans `frida/hooks/game/runner-registry.ts` et n'est
    compare qu'a `listRunners()` du MEME module, aux deux seuls points de creation
    -- `initAndStart` (`frida/hooks/features/launch.ts`) et `buildPatchedRunner`
    (`frida/hooks/features/battle-config.ts`). Le gate est donc COTE HOOKS.
  * `GET /api/runners` publie le CACHE du host (`frida/host/battle-store.ts`,
    map `runners`), qui ne gate rien. C'est un cache de PRESENTATION pour le
    panneau du front et pour `/api/runners/:id/latest-state`.

Ce probe MESURE l'ecart entre les deux, et le NOMME. Il ne cree ni ne dispose
aucun runner : lecture pure, sans effet de bord sur les agents en vol.

MESURE D'ORIGINE (2026-07-31, avant correctif) : host=318 / hooks=0, runnerIds
1..318 SANS AUCUN TROU et tous sans `configId` -- donc aucune entree n'avait
jamais ete retiree, et toutes venaient de l'auto-inference `battle_event`. Cause :
la comptabilite host etait ASYMETRIQUE (creation inferee, mort jamais cablee sur
le chemin RPC `disposeRunner` qu'empruntent tous les agents). Corrige dans
`rpcCall` (host/sessions.ts) + filet `host/runner-reconcile.ts`.

APRES le correctif, l'ecart attendu est ~0 (a la tolerance d'une course de
quelques centaines de ms pres). `--max-drift N` fait echouer au-dela de N, ce qui
en fait un cliquet utilisable apres la fenetre de restart du host.

TRI-ETAT ASSUME : le compte HOOKS peut etre `None` (pas de session, RPC KO). Un
`None` n'est PAS un zero -- sans mesure cote autorite, aucun verdict de derive
n'est rendu. C'est la meme discipline que `host_inputs.py` (#273) et que la jauge
de drain (#285).

Usage :
  python probe_321_runner_registry_drift.py
  python probe_321_runner_registry_drift.py --max-drift 0 --json logs/probe321.json
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parents[2]          # racine du CHECKOUT
HOST = "http://127.0.0.1:8765"

# Ce que le probe AFFIRME du code, et qu'il re-verifie a chaque run (etape 0).
# Un port qui deplacerait le gate sans mettre a jour ces ancres doit rougir.
_GATE_ANCHORS = [
    ("frida/hooks/game/runner-registry.ts", "export const MAX_RUNNERS"),
    ("frida/hooks/features/launch.ts", "active.length >= MAX_RUNNERS"),
    ("frida/hooks/features/battle-config.ts", "active.length >= MAX_RUNNERS"),
]


def _get(path: str, timeout: int = 20):
    req = urllib.request.Request(HOST + path, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _post(path: str, body: dict, timeout: int = 20):
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(HOST + path, data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def read_gate() -> dict:
    """Etape 0 -- le GATE, relu dans les sources, jamais suppose."""
    out = {"maxRunners": None, "anchors": [], "ok": True}
    for rel, needle in _GATE_ANCHORS:
        p = ROOT / rel
        found = False
        if p.exists():
            for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
                if needle in line:
                    found = True
                    if "export const MAX_RUNNERS" in line:
                        digits = "".join(c for c in line.split("=")[-1] if c.isdigit())
                        out["maxRunners"] = int(digits) if digits else None
                    break
        out["anchors"].append({"file": rel, "needle": needle, "found": found})
        if not found:
            out["ok"] = False
    return out


def read_hooks_count() -> tuple[int | None, str | None]:
    """AUTORITE : le registre des hooks, via la RPC `listRunners`.

    Passe par `GET /api/admin/drain`, qui interroge deja les hooks avec le
    tri-etat qui va bien -- inutile de rouvrir un second chemin de mesure."""
    try:
        d = _get("/api/admin/drain")
    except Exception as e:                                   # noqa: BLE001
        return None, f"GET /api/admin/drain KO: {e}"
    n = d.get("liveRunners")
    if n is None:
        return None, str(d.get("liveRunnersError") or "liveRunners non mesure")
    return int(n), None


def read_host_registry() -> tuple[list | None, str | None]:
    try:
        return _get("/api/runners"), None
    except Exception as e:                                   # noqa: BLE001
        return None, f"GET /api/runners KO: {e}"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-drift", type=int, default=None,
                    help="echoue si (host - hooks) depasse N. Omis = mesure seule.")
    ap.add_argument("--sync", action="store_true",
                    help="declenche POST /api/runners/sync (reconciliation MANUELLE) "
                         "puis re-mesure. Sans effet sur les runners VIVANTS.")
    ap.add_argument("--json", default=None,
                    help="ecrit le rapport (chemin RELATIF au checkout ; logs/ conseille)")
    a = ap.parse_args(argv)

    gate = read_gate()
    print("[0] GATE relu dans les sources")
    print("    MAX_RUNNERS =", gate["maxRunners"], "(frida/hooks/game/runner-registry.ts)")
    for an in gate["anchors"]:
        print("    %-46s %-32s %s" % (an["file"], an["needle"],
                                      "OK" if an["found"] else "INTROUVABLE"))
    if not gate["ok"]:
        print("    /!\\ une ancre a bouge : le gate n'est peut-etre plus la ou ce probe le dit")

    hooks, herr = read_hooks_count()
    host, oerr = read_host_registry()
    host_n = None if host is None else len(host)

    print("[1] COMPTEURS")
    print("    hooks  (AUTORITE, RPC listRunners) =",
          "NON MESURE (%s)" % herr if hooks is None else hooks)
    print("    host   (CACHE, GET /api/runners)   =",
          "NON MESURE (%s)" % oerr if host_n is None else host_n)

    if host:
        no_cfg = sum(1 for r in host if not r.get("configId"))
        ids = sorted(r["runnerId"] for r in host if isinstance(r.get("runnerId"), int))
        gaps = 0
        if ids:
            gaps = (ids[-1] - ids[0] + 1) - len(ids)
        sess = sorted({r.get("sessionId") for r in host})
        print("    detail host : sans configId=%d/%d  ids=%d..%d  trous=%d  sessions=%s"
              % (no_cfg, len(host), ids[0], ids[-1], gaps, sess))
        print("      (aucun trou + aucun configId = registre JAMAIS purge, "
              "toutes entrees auto-inferees depuis battle_event)")

    if a.sync:
        try:
            s = _post("/api/runners/sync", {})
            print("[2] sync MANUEL : kept=%d removed=%d"
                  % (len(s.get("kept") or []), len(s.get("removed") or [])))
        except Exception as e:                               # noqa: BLE001
            print("[2] sync KO:", e)
        hooks, herr = read_hooks_count()
        host, oerr = read_host_registry()
        host_n = None if host is None else len(host)
        print("    apres sync : hooks=%s host=%s" % (hooks, host_n))

    drift = None
    if hooks is not None and host_n is not None:
        drift = host_n - hooks
        print("[3] DERIVE host-hooks =", drift)
    else:
        print("[3] DERIVE : NON CALCULABLE (un des deux cotes non mesure) -- "
              "ce n'est PAS un zero.")

    print("[4] VERDICT")
    print("    Le compteur qui GATE la creation est celui des HOOKS. "
          "GET /api/runners ne gate rien.")
    if drift is not None and drift > 0:
        print("    Le cache host retient %d entree(s) de runners MORTS : "
              "purge non cablee sur un chemin de mort (cf. #321)." % drift)

    report = {"gate": gate, "hooksCount": hooks, "hooksError": herr,
              "hostCount": host_n, "hostError": oerr, "drift": drift}
    if a.json:
        p = Path(a.json)
        if p.is_absolute():
            print("[!] --json doit etre RELATIF au checkout (cliquet #314) :", a.json)
            return 2
        p = ROOT / p
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print("    rapport ->", a.json)

    if a.max_drift is not None:
        if drift is None:
            print("[FAIL] --max-drift exige une mesure des DEUX cotes ; "
                  "au moins un est absent.")
            return 1
        if drift > a.max_drift:
            print("[FAIL] derive=%d > max-drift=%d" % (drift, a.max_drift))
            return 1
        print("[OK] derive=%d <= max-drift=%d" % (drift, a.max_drift))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
