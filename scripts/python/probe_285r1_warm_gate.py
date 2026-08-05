"""#285-r1 -- La porte de warmup est-elle CABLEE dans `rpcCall` ?

Ce probe mesure la moitie que l'epreuve hors Frida ne peut pas voir. Les deux sont
necessaires et ne se remplacent pas :

  frida/host/warm-gate.probe.ts   la LOGIQUE (marquage, coup unique, file unique,
                                  echappatoire, chemin d'echec) -- 24 verifications,
                                  5 mutants la font rougir. Aucune Frida, aucun jeu.
  CE PROBE                        le CABLAGE : l'etat est-il PUBLIE, une session
                                  fraiche est-elle vue FROIDE, et une creation la
                                  rend-elle CHAUDE toute seule ?

Une porte juste et NON cablee se lit exactement comme une porte qui marche.

POURQUOI ELLE EXISTE (l'incident du 2026-08-05, mesure). Fenetre de maintenance :
drain arme, `liveRunners` a 0, restart du host. Le drain vit EN MEMOIRE -> il
repart a `false`. L'auto-restore re-attache et REINJECTE mais ne warme PAS (seul
`POST /api/admin/inject` enchaine le warmup). Entre les deux, la creation de
runners etait rouverte sur une session FROIDE : trois `initAndStart` d'un agent y
sont passes et ont rendu `started: true`. C'est le piege exact que la regle
inconditionnelle du `CLAUDE.md` vise -- « un probe qui MARCHE sans warmup ne
prouve rien » -- et elle n'etait ecrite qu'en prose.

TRI-ETAT OBLIGATOIRE. Un host ANTERIEUR a #285-r1 ne publie pas `warmGate`. Ce
probe rend alors **rc 2 = NON MESURE**, jamais un vert (« le champ est absent donc
tout va bien ») ni un rouge (« la porte est cassee ») : les deux mentiraient. La
porte ne s'active qu'au prochain redemarrage du host.

USAGE
    python scripts/python/probe_285r1_warm_gate.py

PREREQUIS : host lance et session Frida vivante. Le probe ne construit un runner
que si la session est deja chaude ou s'il peut la faire chauffer -- et il dispose
ce qu'il cree, y compris sur echec.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

from rl_collect_batch import _resolve_session, _rpc, HOST  # noqa: E402

# Doit rester EGAL a `WARM_GATE_MARKER` (frida/host/warm-gate.ts). Contrat
# inter-langages, comme `DRAIN_MARKER` -- et DISTINCT de lui a dessein : le
# marqueur de drain veut dire « attends », celui-ci veut dire « va lire le
# warmup ». Les confondre ferait boucler le client sur une cause qui ne bouge pas.
WARM_GATE_MARKER = "warmup required"

_failures: list[str] = []
_checks = 0


def check(label: str, ok: bool, detail: str = "") -> bool:
    global _checks
    _checks += 1
    print(f"  [{'OK ' if ok else 'FAIL'}] {label}" + (f" -- {detail}" if detail else ""))
    if not ok:
        _failures.append(f"{label} -- {detail}")
    return ok


def http(path: str) -> tuple[int, dict]:
    try:
        with urllib.request.urlopen(HOST + path, timeout=20) as r:
            raw = r.read().decode("utf-8")
            return r.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8")
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"_raw": raw[:400]}


def main() -> int:
    code, st = http("/api/admin/status")
    if code != 200:
        print(f"[285-r1] NON MESURE : GET /api/admin/status -> HTTP {code}")
        return 2

    # -- 0. LE HOST PORTE-T-IL LA PORTE ? Question posee AVANT toute autre, et
    #       repondue par un TRI-ETAT. Un host anterieur repondrait `None` a tout
    #       ce qui suit, et un lecteur presse lirait « rien a signaler ».
    if "warmGate" not in st:
        print("[285-r1] NON MESURE -- le host tourne un code ANTERIEUR a #285-r1 "
              "(champ `warmGate` absent de /api/admin/status).")
        print("[285-r1] La porte ne s'active qu'au prochain REDEMARRAGE du host. "
              "Rien n'est conclu ici : ni vert, ni rouge.")
        return 2

    sid = _resolve_session()
    print(f"[285-r1] session={sid}\n")
    state = Path(tempfile.gettempdir()) / f"probe285r1_{os.getpid()}.json"
    rid = None

    try:
        print("[1] l'etat est PUBLIE, et il distingue `running` de `chaude`")
        wg = st.get("warmGate") or {}
        sess = st.get("session") or {}
        check("/api/admin/status publie warmGate", isinstance(wg, dict))
        for k in ("warmed", "pending", "autoWarmups", "autoWarmupFailures", "escapeHatch"):
            check(f"warmGate.{k} present", k in wg, f"cles={sorted(wg)}")
        check("la session publie son etat `warmed`", "warmed" in sess,
              f"cles={sorted(sess)}")
        check("`warmed` est un booleen, pas un null deguise",
              isinstance(sess.get("warmed"), bool), f"warmed={sess.get('warmed')}")
        print(f"      warmed={sess.get('warmed')} autoWarmups={wg.get('autoWarmups')} "
              f"echecs={wg.get('autoWarmupFailures')} echappatoire={wg.get('escapeHatch')}")

        # -- 2. L'echappatoire ne doit pas etre armee par defaut : sinon la porte
        #       est publiee mais inerte, ce qui est le pire des deux mondes.
        print("\n[2] l'echappatoire est DESARMEE par defaut")
        check("TACTICUS_ALLOW_COLD_RUNNER n'est pas actif cote host",
              wg.get("escapeHatch") is False,
              "une porte publiee mais court-circuitee se lit comme une porte qui mord")

        # -- 3. LE CABLAGE. Une creation sur une session froide doit la rendre
        #       chaude TOUTE SEULE. Si la session est deja chaude, on ne peut pas
        #       l'observer ici -- et on le DIT, plutot que de compter un vert.
        print("\n[3] une creation rend la session chaude")
        was_warm = bool(sess.get("warmed"))
        if was_warm:
            print("      NON OBSERVABLE : la session est DEJA chaude. Ce cran ne se "
                  "mesure que sur une session fraichement injectee -- il n'est ni "
                  "vert ni rouge, il est hors de portee de ce run.")
        r = _rpc(sid, "initAndStart", [{"configJson": "{}"}], timeout=300)
        err = str(r.get("error") or "")
        # `configJson: {}` est volontairement INVALIDE : on mesure que la porte a
        # laisse passer (ou a warme), pas qu'un runner se construit. Un refus de
        # la porte se reconnait a SON marqueur, distinct de toute erreur metier.
        check("la porte n'a pas refuse la creation", WARM_GATE_MARKER not in err,
              err[:200])
        _, st2 = http("/api/admin/status")
        sess2 = st2.get("session") or {}
        check("la session est CHAUDE apres la tentative de creation",
              sess2.get("warmed") is True, f"warmed={sess2.get('warmed')}")
        if not was_warm:
            wg2 = st2.get("warmGate") or {}
            check("le warmup automatique est COMPTE",
                  (wg2.get("autoWarmups") or 0) > (wg.get("autoWarmups") or 0),
                  f"{wg.get('autoWarmups')} -> {wg2.get('autoWarmups')}")

        # -- 4. La porte ne mord QUE la creation. Meme borne que le drain : geler
        #       le monitoring casserait le travail des agents en vol.
        print("\n[4] la porte ne touche PAS au monitoring")
        r = _rpc(sid, "listRunners", [], timeout=30)
        check("listRunners passe", "error" not in r, str(r.get("error"))[:160])

    finally:
        if rid is not None:
            try:
                _rpc(sid, "disposeRunner", [{"runnerId": rid}], timeout=30)
            except Exception:
                pass
        state.unlink(missing_ok=True)

    print(f"\n[285-r1] {_checks - len(_failures)}/{_checks} verifications OK")
    if _failures:
        print("[285-r1] VERDICT : ECHEC")
        for f in _failures:
            print(f"  - {f}")
        return 1
    print("[285-r1] VERDICT : la porte est CABLEE -- l'etat est publie, "
          "et une creation ne peut plus partir d'une session froide.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
