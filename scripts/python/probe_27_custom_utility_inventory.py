"""probe #27 -- inventaire EXHAUSTIF des overrides CalculateCustomUtility.

Etape 0 (bloquante) de la tranche #27-3 : re-derive l'inventaire DEPUIS LE
BINAIRE, sans se fier a une fiche, et SANS se fier a l'absence d'un symbole
dans les tables (IL2CPP DEDUPLIQUE les corps triviaux -- un corps partage par
N classes n'a qu'UN SEUL proprietaire dans methods.tsv, cf. #170 get_Priority).

Methode (deux sources independantes) :

1. SOURCE A -- table de symboles offline (data/symbols/<build>/frida/methods.tsv).
   Donne les proprietaires NOMMES de chaque corps.
2. SOURCE B -- balayage RUNTIME du SLOT DE VTABLE : pour CHAQUE classe dont le
   nom contient "Playbook" (findClassesNamed), on lit le pointeur de fonction
   du slot `CalculateCustomUtility` (resolveVtableSlot). Une classe qui
   n'override pas pointe sur le corps de la base ; une classe qui override
   avec un corps DEDUPLIQUE pointe sur le corps d'une AUTRE classe -- c'est
   exactement le faux negatif que la table ne peut pas montrer.

Sortie ASCII pure (cp1252).
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path

HOST = "http://127.0.0.1:8765"
GHIDRA_IMAGE_BASE = 0x180000000
REPO = Path(__file__).resolve().parents[2]


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
    if "error" in body and body["error"]:
        raise RuntimeError("rpc %s failed: %s" % (method, body["error"]))
    return body.get("result")


# ---------------------------------------------------------------- source A
def table_owners(build: str) -> dict:
    """RVA -> nom complet, pour tous les corps CalculateCustomUtility nommes."""
    p = REPO / "data" / "symbols" / build / "frida" / "methods.tsv"
    out = {}
    with p.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if "CalculateCustomUtility" not in line:
                continue
            fields = line.rstrip("\n").split("\t")
            if len(fields) < 2:
                continue
            name = fields[1]
            if not name.endswith("CalculateCustomUtility"):
                continue  # ecarte les lambdas <>c.<CalculateCustomUtility>b__*
            out[int(fields[0], 16)] = name
    return out


# ---------------------------------------------------------------- source B
VTABLE_START = 0x138  # offset canonique du 1er VirtualInvokeData dans Il2CppClass
VTABLE_SLOT = 0x10    # sizeof(VirtualInvokeData) = { methodPtr, MethodInfo* }
VTABLE_MAX_SLOTS = 96


def sweep_vtable(sid: int, classes: list) -> list:
    """Balaye la vtable PROPRE de chaque classe et retient le slot nomme
    CalculateCustomUtility, OU QU'IL SOIT DEDANS. L'offset n'est pas fige (les
    hierarchies Comparable / NonComparable / Triggered n'ont pas la meme
    disposition), mais le balayage est BORNE.

    ⚠ Le bornage est un CORRECTIF (#218), pas un detail. `resolveVtableSlot` lit
    `klass+off` en aveugle : il n'a pas acces a `vtable_count`. Un balayage large
    (l'ancien 0x108..0x808) deborde sur l'`Il2CppClass` SUIVANTE -- elles sont
    contigues -- et rend des MethodInfo parfaitement nommes appartenant a une
    AUTRE classe. C'est ce qui avait fait conclure, en tranche 3, que
    `AmuletOfTheVoidwyrmPlaybook` overridait `CalculateCustomUtility` en
    partageant le corps de `PlasmaGrenadePlaybook` : le "slot +0x548" etait le
    slot +0x338 de PlasmaGrenadePlaybook, dont la classe suit a +0x210 en
    memoire. Voir `docs/rl/case-218-amulet-voidwyrm-custom-utility.md`.

    Borne appliquee : premier bloc CONTIGU de slots nommes depuis +0x138. Une
    classe jamais instanciee a une vtable NULLE -- statut `vtable-uninit`, un
    INDETERMINE explicite (a trancher par la chaine d'heritage), plus jamais un
    debordement silencieux.
    """
    rows = []
    end = VTABLE_START + (VTABLE_MAX_SLOTS - 1) * VTABLE_SLOT
    for ns, cls in classes:
        try:
            res = rpc(sid, "resolveVtableSlot",
                      [{"ns": ns, "cls": cls,
                        "start": VTABLE_START, "end": end}])
        except Exception as exc:  # noqa: BLE001
            rows.append((ns, cls, None, None, "ERR %s" % exc))
            continue
        if not res or not res.get("ok"):
            rows.append((ns, cls, None, None, "no-class"))
            continue
        own = []
        for s in res["slots"]:
            if not s.get("method") or not s.get("funcRVA"):
                break  # fin de la vtable PROPRE -- au-dela = classe voisine
            own.append(s)
        if not own:
            rows.append((ns, cls, None, None, "vtable-uninit"))
            continue
        hits = [s for s in own if s.get("method") == "CalculateCustomUtility"]
        if not hits:
            rows.append((ns, cls, None, None, "no-slot"))
            continue
        slot = hits[0]
        rva = slot.get("funcRVA")
        rows.append((ns, cls, int(rva, 16) if rva else None,
                     slot.get("off"), "ok"))
    return rows


def find_slot(sid: int, ns: str, cls: str) -> int:
    """Localise le slot de vtable de CalculateCustomUtility sur une classe.

    Meme borne que `sweep_vtable` (cf. #218) : la vtable commence a +0x138 et
    s'arrete au premier slot non nomme. Au-dela on lit la classe VOISINE.
    """
    rows = sweep_vtable(sid, [(ns, cls)])
    _ns, _cls, _rva, off, status = rows[0]
    if status != "ok":
        raise SystemExit("no CalculateCustomUtility slot on %s.%s (status=%s)"
                         % (ns, cls, status))
    return int(off, 16)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", default="gqfc5mff6c")
    ap.add_argument("--anchor-ns", default="IdunBattle.AI.Playbook.Loki")
    ap.add_argument("--anchor-cls", default="DrachnyenPlaybook")
    ap.add_argument("--needle", default="Playbook")
    args = ap.parse_args()

    sid = _session_id()
    print("session=%d build=%s" % (sid, args.build))

    owners = table_owners(args.build)
    print("[A] table methods.tsv : %d corps nommes CalculateCustomUtility"
          % len(owners))

    slot = find_slot(sid, args.anchor_ns, args.anchor_cls)
    print("[B] slot de vtable CalculateCustomUtility = +0x%x (ancre %s)"
          % (slot, args.anchor_cls))

    found = rpc(sid, "findClassesNamed", [args.needle])
    classes = sorted({(r["ns"], r["cls"]) for r in found["results"]})
    print("[B] classes *%s* vues au runtime : %d" % (args.needle, len(classes)))

    rows = sweep_vtable(sid, classes)
    by_rva = defaultdict(list)
    offs = defaultdict(int)
    bad = []
    for ns, cls, rva, off, status in rows:
        if rva is None:
            bad.append((ns, cls, status))
            continue
        by_rva[rva].append("%s.%s" % (ns, cls))
        offs[off] += 1
    print("[B] offsets de slot rencontres : %s"
          % ", ".join("%s x%d" % (k, v) for k, v in sorted(offs.items())))
    print("[B] classes PORTANT le slot : %d / %d"
          % (sum(offs.values()), len(classes)))

    print("\n=== CORPS DISTINCTS (par RVA de fonction), %d ===" % len(by_rva))
    for rva in sorted(by_rva):
        owner = owners.get(rva, "<NON NOMME dans methods.tsv>")
        print("RVA 0x%-8x VA 0x%x  owner=%s"
              % (rva, GHIDRA_IMAGE_BASE + rva, owner))
        for u in sorted(by_rva[rva]):
            print("      user: %s" % u)

    print("\n=== CORPS PARTAGES (dedup / heritage), %d ===" %
          sum(1 for v in by_rva.values() if len(v) > 1))
    for rva, users in sorted(by_rva.items()):
        if len(users) > 1:
            print("  0x%x  owner=%s  users=%d"
                  % (rva, owners.get(rva, "?"), len(users)))

    unnamed = [r for r in by_rva if r not in owners]
    print("\n=== CORPS SANS PROPRIETAIRE NOMME (invisible dans methods.tsv),"
          " %d ===" % len(unnamed))
    for rva in sorted(unnamed):
        print("  0x%x users=%s" % (rva, ", ".join(sorted(by_rva[rva]))))

    orphan_table = [rva for rva in owners if rva not in by_rva]
    print("\n=== CORPS NOMMES JAMAIS ATTEINTS par le balayage, %d ===" %
          len(orphan_table))
    for rva in sorted(orphan_table):
        print("  0x%x %s" % (rva, owners[rva]))

    if bad:
        byst = defaultdict(int)
        for _ns, _cls, st in bad:
            byst[st] += 1
        print("\n=== CLASSES SANS SLOT CalculateCustomUtility (%d) ===" % len(bad))
        for st, n in sorted(byst.items()):
            print("  status=%s : %d" % (st, n))
    return 0


if __name__ == "__main__":
    sys.exit(main())
