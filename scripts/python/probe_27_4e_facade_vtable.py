"""probe #27 tranche 4c -- les DEUX vtables dont depend le port de SorcerousFacade (1100).

DEUX questions binaires, toutes deux resolues au SLOT DE VTABLE (jamais par grep, jamais par
elimination) :

1. `IdunBattle.AI.Playbook.Loki.SorcerousFacadePlaybook` override-t-il bien
   `CalculateCustomUtility` (+0x338), `ShouldExecute` (+0x328) et `MakeDamagePredictions` (+0x358) ?
   Les trois corps sont NOMMES dans `methods.tsv`, donc l'override est acquis -- ce que le dump
   verifie ici, c'est l'OFFSET de chaque slot, seule facon de croiser le port avec la RE de
   `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateActionUtility`.

2. **Quelle methode est le slot d'interface `0xa` d'`IBattleQuery`** qu'appelle
   `IdunBattle.AI.Playbook.Loki.SorcerousFacadePlaybook$$ShouldExecute` dans sa branche
   `sel == null` ? La RE l'avait identifiee PAR ELIMINATION (collection de TUILES, 3 arguments,
   3e argument NUL tolere) : `IdunBattle.Core.Services.BattleQuery$$GetCurrentAndMovableTilesOf`.
   Une identification par elimination se recopie ensuite comme un fait -- on la MESURE.

   Conversion slot d'interface -> index de vtable de la classe CONCRETE : `+interfaceOffset`.
   L'`interfaceOffset` d'`IBattleQuery` sur `IdunBattle.Core.Services.BattleQuery` vaut 4, etabli
   par DEUX ancres independantes (#27-4) :
     - `IdunBattle.Entities.Triggers.IsMeleeAttackAbilityTrigger$$ShouldTrigger` appelle le slot
       d'interface 2, et l'index 6 de la vtable est `BattleQuery$$IsMeleeAttack` ;
     - l'index 0x53 est `GetAdjacentTiles`, documente slot 0x4f.
   Le probe REVERIFIE ces deux ancres dans le meme dump, puis lit l'index `0xa + 4 = 0xe`.

Usage : python probe_27_4e_facade_vtable.py [--build rnca9r7q6c]   (ASCII only ; exit 0 = OK)
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
VTABLE_MAX_SLOTS = 220          # BattleQuery porte >0x90 slots ; borne large, le dump s'arrete seul

# Ancres de l'`interfaceOffset` d'IBattleQuery sur BattleQuery (cf. docstring).
IFACE_OFFSET = 4
ANCHORS = {6: "IsMeleeAttack", 0x53: "GetAdjacentTiles"}
# Le slot d'interface lu dans `SorcerousFacadePlaybook$$ShouldExecute`.
FACADE_IFACE_SLOT = 0xA
FACADE_EXPECT = "GetCurrentAndMovableTilesOf"

PLAYBOOK_EXPECT = {0x328: "ShouldExecute", 0x338: "CalculateCustomUtility",
                   0x358: "MakeDamagePredictions"}


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


def dump(sid: int, ns: str, cls: str) -> list:
    end = VTABLE_START + (VTABLE_MAX_SLOTS - 1) * VTABLE_SLOT
    res = rpc(sid, "resolveVtableSlot", [{"ns": ns, "cls": cls,
                                          "start": VTABLE_START, "end": end}])
    if not res or not res.get("ok"):
        raise SystemExit("resolveVtableSlot KO pour %s.%s : %r" % (ns, cls, res))
    out = []
    for s in res["slots"]:
        if not s.get("method") or not s.get("funcRVA"):
            break                                # fin de la vtable PROPRE (borne #218)
        out.append(s)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", default="rnca9r7q6c")
    args = ap.parse_args()
    sid = _session_id()
    tbl = owners(args.build)
    print("session=%d build=%s table=%d entries" % (sid, args.build, len(tbl)))
    fails = []

    # --- 1. la vtable du playbook ------------------------------------------------------------
    slots = dump(sid, "IdunBattle.AI.Playbook.Loki", "SorcerousFacadePlaybook")
    print("\n=== IdunBattle.AI.Playbook.Loki.SorcerousFacadePlaybook (%d slots propres)" % len(slots))
    by_off = {}
    for s in slots:
        off = int(s["off"], 16) if isinstance(s["off"], str) else int(s["off"])
        by_off[off] = s
    for off, name in sorted(PLAYBOOK_EXPECT.items()):
        s = by_off.get(off)
        if s is None:
            fails.append("slot +0x%x absent de la vtable de SorcerousFacadePlaybook" % off)
            continue
        rva = int(s["funcRVA"], 16)
        own = tbl.get(rva, "<unnamed body>")
        mark = "OK " if s["method"] == name else "!! "
        print("  %s+0x%-4x %-28s rva=%08x  %s" % (mark, off, s["method"], rva, own))
        if s["method"] != name:
            fails.append("slot +0x%x = %s, attendu %s" % (off, s["method"], name))
        if name in ("CalculateCustomUtility", "ShouldExecute", "MakeDamagePredictions") \
                and "SorcerousFacadePlaybook" not in own:
            fails.append("slot +0x%x (%s) ne pointe PAS sur un corps de SorcerousFacadePlaybook : %s"
                         % (off, name, own))

    # --- 2. la vtable de BattleQuery : ancres + le slot d'interface 0xa -----------------------
    bq = dump(sid, "IdunBattle.Core.Services", "BattleQuery")
    idx_by_name = {}
    name_by_idx = {}
    for s in bq:
        off = int(s["off"], 16) if isinstance(s["off"], str) else int(s["off"])
        idx = (off - VTABLE_START) // VTABLE_SLOT
        name_by_idx[idx] = s["method"]
        idx_by_name.setdefault(s["method"], idx)
    print("\n=== IdunBattle.Core.Services.BattleQuery (%d slots propres)" % len(bq))
    for idx, want in sorted(ANCHORS.items()):
        got = name_by_idx.get(idx)
        print("  ancre index 0x%-3x -> %-34s (attendu %s)" % (idx, got, want))
        if got != want:
            fails.append("ancre index 0x%x = %r, attendu %r -> l'interfaceOffset %d n'est plus "
                         "valide sur ce build" % (idx, got, want, IFACE_OFFSET))
    target_idx = FACADE_IFACE_SLOT + IFACE_OFFSET
    got = name_by_idx.get(target_idx)
    print("  slot d'interface 0x%x -> index 0x%x -> %s" % (FACADE_IFACE_SLOT, target_idx, got))
    if got != FACADE_EXPECT:
        fails.append("slot d'interface 0x%x = %r, la RE par elimination disait %r"
                     % (FACADE_IFACE_SLOT, got, FACADE_EXPECT))
    # voisinage, pour lecture humaine (et pour voir la soeur `...PositionsFor`)
    print("  voisinage :", ", ".join("0x%x=%s" % (i, name_by_idx.get(i))
                                     for i in range(target_idx - 2, target_idx + 4)
                                     if i in name_by_idx))

    if fails:
        print()
        for f in fails:
            print("FAIL:", f)
        return 1
    print("\nOK: slots playbook +0x328/+0x338/+0x358 confirmes sur des corps SorcerousFacadePlaybook ;"
          " ancres IBattleQuery revalidees ; slot d'interface 0x%x = %s" % (FACADE_IFACE_SLOT, got))
    return 0


if __name__ == "__main__":
    sys.exit(main())
