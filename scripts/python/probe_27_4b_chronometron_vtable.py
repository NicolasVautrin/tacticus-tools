"""probe #27 tranche 4b -- vtable de `IdunBattle.AI.Playbook.Loki.ChronometronPlaybook`.

QUESTION BINAIRE : `ChronometronPlaybook` override-t-il `ShouldExecute` ?

Pourquoi la question, et pourquoi elle ne se lit pas dans la table : le corps par
defaut (`IdunBattle.AI.Playbook.Loki.HealingBalms_HealPlaybook$$ShouldExecute` en
est un exemplaire NOMME) vaut `attackHealUtility > Fix64(0)`, et
`IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateActionUtility`
appelle ce predicat AVANT d'ajouter le terme custom. Une ability SANS prediction
(Chronometron n'a pas de `damageProfile`) arriverait donc a `utility = 0` et
serait REFUSEE -- sauf override. Or un `return true` est un corps trivial
(`mov al,1 ; ret`), donc DEDUPLIQUE par IL2CPP et nomme sur UN SEUL proprietaire :
l'absence de `ChronometronPlaybook$$ShouldExecute` dans `methods.tsv` ne prouve
RIEN (cf. CLAUDE.md, case-170).

Ce qui tranche : le SLOT DE VTABLE sur l'instance, borne (cf. #218), et la
resolution de la RVA du slot contre `methods.tsv` du build COURANT.

Sortie ASCII pure (cp1252).
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

HOST = "http://127.0.0.1:8765"
REPO = Path(__file__).resolve().parents[2]
VTABLE_START = 0x138
VTABLE_SLOT = 0x10
VTABLE_MAX_SLOTS = 96


def _session_id() -> int:
    with urllib.request.urlopen(HOST + "/api/admin/status", timeout=10) as r:
        st = json.loads(r.read().decode("utf-8"))
    sess = st.get("session") or {}
    if sess.get("status") != "running":
        raise SystemExit("no running frida session: %r" % (sess,))
    return int(sess["id"])


def rpc(sid: int, method: str, args=None, timeout_ms: int = 60000):
    payload = json.dumps({"method": method, "args": args or [],
                          "timeout": timeout_ms}).encode("utf-8")
    req = urllib.request.Request("%s/api/scripts/%d/rpc" % (HOST, sid), data=payload,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout_ms / 1000.0 + 15) as r:
        body = json.loads(r.read().decode("utf-8"))
    if body.get("error"):
        raise RuntimeError("rpc %s failed: %s" % (method, body["error"]))
    return body.get("result")


def owners(build: str) -> dict:
    """RVA -> symbole complet (toute la table, pas seulement un motif)."""
    p = REPO / "data" / "symbols" / build / "frida" / "methods.tsv"
    out = {}
    with p.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            f = line.rstrip("\n").split("\t")
            if len(f) < 2:
                continue
            try:
                out[int(f[0], 16)] = f[1]
            except ValueError:
                continue
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", default="rnca9r7q6c")
    ap.add_argument("--ns", default="IdunBattle.AI.Playbook.Loki")
    ap.add_argument("--cls", action="append", default=[])
    args = ap.parse_args()
    classes = args.cls or ["ChronometronPlaybook", "HealingBalms_HealPlaybook",
                           "ArmoriumCherubPlaybook"]

    sid = _session_id()
    tbl = owners(args.build)
    print("session=%d build=%s table=%d entries" % (sid, args.build, len(tbl)))

    end = VTABLE_START + (VTABLE_MAX_SLOTS - 1) * VTABLE_SLOT
    for cls in classes:
        res = rpc(sid, "resolveVtableSlot",
                  [{"ns": args.ns, "cls": cls, "start": VTABLE_START, "end": end}])
        print("\n=== %s.%s ok=%s" % (args.ns, cls, bool(res and res.get("ok"))))
        if not res or not res.get("ok"):
            continue
        for s in res["slots"]:
            if not s.get("method") or not s.get("funcRVA"):
                break  # fin de la vtable PROPRE (borne #218)
            rva = int(s["funcRVA"], 16)
            own = tbl.get(rva, "<unnamed body>")
            print("  +%-6s %-42s rva=%08x  %s" % (s["off"], s["method"], rva, own))
    return 0


if __name__ == "__main__":
    sys.exit(main())
