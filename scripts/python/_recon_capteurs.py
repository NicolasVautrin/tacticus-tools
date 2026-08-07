"""Recon JETABLE (tranche capteurs) -- lit des champs de composants par `dumpEntityComponents`.

Ce fichier est un OUTIL DE MESURE de la tranche, pas un livrable : il sert a etablir les
noms/offsets de champ que les capteurs doivent resoudre au runtime.

    python _recon_capteurs.py --state-file <abs> --entity <id> [--cls UnitComponent]
    python _recon_capteurs.py --state-file <abs> --entities            # liste les entites
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from rl_collect_batch import _rpc  # noqa: E402


def _ids(state_file: Path):
    st = json.loads(state_file.read_text(encoding="utf-8"))
    sess = st.get("session") or {}
    sid = sess.get("sessionId", sess.get("id"))
    return int(sid), int(st["runnerId"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True)
    ap.add_argument("--entity", type=int)
    ap.add_argument("--cls", default=None)
    ap.add_argument("--entities", action="store_true")
    ap.add_argument("--rpc", default=None, help="RPC brut a jouer (JSON body via --body)")
    ap.add_argument("--body", default="{}")
    a = ap.parse_args()
    sid, rid = _ids(Path(a.state_file))

    if a.rpc:
        body = json.loads(a.body)
        body.setdefault("runnerId", rid)
        res = _rpc(sid, a.rpc, [body], timeout=300).get("result")
        print(json.dumps(res, indent=1)[:12000])
        return 0

    if a.entities:
        for eid in range(1, 120):
            res = _rpc(sid, "dumpEntityComponents",
                       [{"runnerId": rid, "entityId": eid, "withFields": False}],
                       timeout=300).get("result") or {}
            if not res.get("ok"):
                continue
            cls = [c.get("cls") for c in (res.get("components") or [])]
            print("id=%-4s type=%s  %s" % (eid, res.get("type"), ",".join(cls)[:180]))
        return 0

    res = _rpc(sid, "dumpEntityComponents",
               [{"runnerId": rid, "entityId": a.entity, "withFields": True}],
               timeout=300).get("result") or {}
    if not res.get("ok"):
        print("KO: %s" % res.get("error"))
        return 1
    print("entity %s type=%s" % (res.get("id"), res.get("type")))
    for c in (res.get("components") or []):
        if a.cls and a.cls.lower() not in str(c.get("cls", "")).lower():
            continue
        print("== %s.%s" % (c.get("ns"), c.get("cls")))
        for f in (c.get("fields") or []):
            print("   +0x%-4x %-46s %s" % (f.get("offset", -1), f.get("name"), f.get("type")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
