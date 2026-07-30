"""probe #27-4g -- RE-DERIVE au runtime la correspondance
`slot d'interface IBattleQuery` -> `index de vtable IdunBattle.Core.Services.BattleQuery`.

POURQUOI un probe et pas une fiche : les numeros de slot d'interface ONT BOUGE entre
`gqfc5mff6c` et `rnca9r7q6c` (mesure #27-4, note de fidelite HeavyWarpFlamer : le terme
d'adjacence de DoomSiren est passe de 0x7f a 0x80). Recopier « 0x7d = GetAdjacentEnemies »
d'une fiche ecrite sur l'ancien build peut donner `GetAdjacentUnits` -- c'est-a-dire AMIS
COMPRIS -- et le port serait faux SANS AUCUNE erreur.

Ce que le probe fait :

1. balaye la vtable PROPRE de `IdunBattle.Core.Services.BattleQuery` (bornee : depuis +0x138,
   arret au premier slot non nomme -- cf. #218, un balayage non borne deborde sur
   l'`Il2CppClass` VOISINE et rend des `MethodInfo` parfaitement nommes) ;
2. imprime les index encadrant les surcharges de `GetAdjacentEnemies` / `GetAdjacentUnits` ;
3. verifie l'ANCRE de conversion `+4` par deux points independants documentes :
   l'index 0x53 doit etre `GetAdjacentTiles` (slot d'interface 0x4f) et l'index 6 doit etre
   `IsMeleeAttack` (slot d'interface 2, appele par
   `IdunBattle.Entities.Triggers.IsMeleeAttackAbilityTrigger$$ShouldTrigger`).

Sortie ASCII pure (cp1252).
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request

HOST = "http://127.0.0.1:8765"

VTABLE_START = 0x138
VTABLE_SLOT = 0x10
VTABLE_MAX_SLOTS = 220          # BattleQuery a une vtable LONGUE (>0x84 methodes)

# Ancres de la conversion slot d'interface -> index de vtable (delta attendu = +4).
# Chacune est un call-site NATIF lu au decompile, pas une fiche recopiee.
ANCHORS = [
    (0x02, "IsMeleeAttack",
     "IdunBattle.Entities.Triggers.IsMeleeAttackAbilityTrigger$$ShouldTrigger"),
    (0x4F, "GetAdjacentTiles",
     "documente case-27 (note de fidelite HeavyWarpFlamer)"),
]


def _session_id() -> int:
    with urllib.request.urlopen(HOST + "/api/admin/status", timeout=10) as r:
        st = json.loads(r.read().decode("utf-8"))
    sess = st.get("session") or {}
    if sess.get("status") != "running":
        raise SystemExit("no running frida session: %r" % (sess,))
    return int(sess["id"])


def rpc(sid: int, method: str, args=None, timeout_ms: int = 60000):
    payload = json.dumps({
        "method": method,
        "args": args if args is not None else [],
        "timeout": timeout_ms,
    }).encode("utf-8")
    req = urllib.request.Request(
        "%s/api/scripts/%d/rpc" % (HOST, sid), data=payload,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout_ms / 1000.0 + 15) as r:
        body = json.loads(r.read().decode("utf-8"))
    if body.get("error"):
        raise RuntimeError("rpc %s failed: %s" % (method, body["error"]))
    return body.get("result")


def own_vtable(sid: int, ns: str, cls: str) -> list:
    """Slots de la vtable PROPRE (bornee au premier slot non nomme)."""
    end = VTABLE_START + (VTABLE_MAX_SLOTS - 1) * VTABLE_SLOT
    res = rpc(sid, "resolveVtableSlot",
              [{"ns": ns, "cls": cls, "start": VTABLE_START, "end": end}])
    if not res or not res.get("ok"):
        raise SystemExit("class not found / vtable unreadable: %s.%s" % (ns, cls))
    own = []
    for s in res["slots"]:
        if not s.get("method") or not s.get("funcRVA"):
            break
        own.append(s)
    return own


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ns", default="IdunBattle.Core.Services")
    ap.add_argument("--cls", default="BattleQuery")
    ap.add_argument("--needles", default="GetAdjacentEnemies,GetAdjacentUnits,"
                                         "GetAdjacentTiles,IsMeleeAttack,GetAllEnemiesOf")
    ap.add_argument("--slots", default="",
                    help="slots d'INTERFACE a resoudre, hex separes par des virgules "
                         "(ex. 0x7d,0x7f,0x80)")
    ap.add_argument("--delta", type=int, default=4,
                    help="conversion slot d'interface -> index de vtable")
    args = ap.parse_args()

    sid = _session_id()
    print("session=%d class=%s.%s" % (sid, args.ns, args.cls))

    own = own_vtable(sid, args.ns, args.cls)
    print("vtable PROPRE : %d slots nommes (borne au premier trou)" % len(own))

    by_index = {}
    for s in own:
        idx = (int(s["off"], 16) - VTABLE_START) // VTABLE_SLOT
        by_index[idx] = s

    ok = True
    for slot, expect, why in ANCHORS:
        idx = slot + args.delta
        got = by_index.get(idx, {}).get("method")
        mark = "OK " if got == expect else "MISMATCH"
        if got != expect:
            ok = False
        print("[ancre] slot 0x%02x + %d -> index 0x%02x = %-22s attendu %-22s %s (%s)"
              % (slot, args.delta, idx, got, expect, mark, why))
    print("[ancre] conversion +%d %s" % (args.delta, "CONFIRMEE" if ok else "REFUTEE"))

    needles = [n.strip() for n in args.needles.split(",") if n.strip()]
    print("\n=== indices portant un nom recherche ===")
    for idx in sorted(by_index):
        m = by_index[idx].get("method")
        if any(n == m for n in needles):
            print("  index 0x%02x (slot itf 0x%02x) : %s"
                  % (idx, idx - args.delta, m))

    if args.slots:
        print("\n=== resolution des slots demandes ===")
        for tok in args.slots.split(","):
            tok = tok.strip()
            if not tok:
                continue
            slot = int(tok, 16)
            idx = slot + args.delta
            s = by_index.get(idx)
            print("  slot itf 0x%02x -> index 0x%02x = %s"
                  % (slot, idx, (s or {}).get("method", "<hors vtable propre>")))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
