"""probe #462-r4b-r1-r1-r1-r1 -- le RETRAIT herite d'`ABondEffect`, ses TROIS gates virtuels.

CE QUI EST LU (decompile ghidra, build `rnca9r7q6c`).
`IdunBattle.Entities.Effects.ABondEffect$$CreateHandleTriggerAbilitiesInternal` ajoute JUSQU'A
trois `Triggered()` de `RemoveEffect`, chacun sous un appel VIRTUEL de la classe d'effet. Slots de
vtable (`klass+off` = methodPtr, `klass+off+8` = `MethodInfo*`) :

    (a) <klass+0x748>() : bool ->
          Triggered( NOT AmountIsZero(BondedEntityFromEffect(Effect@DSLSelectors+0x38))
                     & ( On(2 = PreUnitDeath_2) | On(0x25 = UnitRemoved) )
                     & IsEntityWithIdTarget(BondedEntityFromEffect(...)),
                     RemoveEffect(Effect@0x38) )

    (b) <klass+0x728>() : Nullable<int> ; si HasValue ->
          Triggered( NOT IsInRange(Owner@DSLSelectors+0x30, BondedEntity, Direct(value))
                     & NOT AmountIsZero(BondedEntity) & On(0x1d = UnitPositionChanged_2),
                     RemoveEffect(Effect@0x38) )

    (c) <klass+0x738>() : bool ->
          Triggered( NOT IsAdjacent(Owner@0x30, BondedEntity, 3)
                     & NOT AmountIsZero(BondedEntity) & On(0x1d),
                     RemoveEffect(Effect@0x38) )

POURQUOI UN PROBE RUNTIME. Aucun de ces trois virtuels n'apparait sous `<Effet>$$*` dans
`data/symbols/<build>/frida/methods.tsv` pour la plupart des classes -- et ca ne prouve RIEN : les
corps triviaux (`xor eax,eax ; ret` pour un bool faux, un `Nullable` vide) sont DEDUPLIQUES par
IL2CPP et un corps partage n'a qu'UN SEUL proprietaire dans la table. La seule facon de conclure est
de LIRE LE SLOT sur la classe, au runtime, et de comparer son POINTEUR a celui de la base
`ABondEffect` (patron `probe_433_r4_r2_r1_r1_dynamic_target_gate.py --step gate`, PR #558).

  * `--step vtable` : pour `ABondEffect` et CHAQUE classe qui en derive (transitivement, lue dans
    `data/symbols/<build>/frida/classes.tsv`), l'adresse ghidra et le NOM (`il2cpp_method_get_name`)
    des slots `+0x728` / `+0x738` / `+0x748`. C'est ce pas qui a NOMME les trois virtuels --
    `get_Range`, `get_Adjacent`, `get_RemoveOnBondedEntityDeath` -- et dans cet ordre exact.
    ATTENTION, il ne CONCLUT pas a lui seul : une vtable IL2CPP n'est materialisee qu'apres
    `il2cpp_runtime_class_init`, donc une classe jamais instanciee rend des slots pointant sur le
    stub de remplissage paresseux (`Unity.Burst.Unsafe$$AsRef`, qui ne retourne pas) ou NULL.
    Mesure du 2026-08-04 : 3 classes sur 36 materialisees, et la BASE elle-meme -- abstraite, jamais
    instanciee -- rend le stub pour les trois slots. Comparer a elle serait comparer a du bruit.

  * `--step declared` : la voie qui CONCLUT, et qui ne depend d'aucune initialisation. Elle
    enumere `class_get_methods` NIVEAU PAR NIVEAU de la chaine de parents (`resolveMethodPtr`) :
    une classe qui SURCHARGE declare son propre `MethodInfo`, meme quand IL2CPP a DEDUPLIQUE le
    corps -- le `methodPointer` est partage, l'entree de la classe ne l'est pas. C'est ce qui
    permet de conclure la ou `methods.tsv` (indexee par ADRESSE, donc dedupliquee) est aveugle.
    Les trois corps triviaux sont resolus par leur adresse :
        `0x1802b4590` = `return 1`  -> bool TRUE
        `0x1802b45a0` = `return 0`  -> bool FALSE
        `0x1802b45b0` = `return 0`  -> `Nullable<int>` VIDE (pas de portee)

Usage (ASCII only, depuis scripts/python) :
  python probe_462_r4b_r1_r1_r1_r1_bond_removal.py --step vtable
  python probe_462_r4b_r1_r1_r1_r1_bond_removal.py --step declared
  python probe_462_r4b_r1_r1_r1_r1_bond_removal.py --step all
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rl_collect_batch import _resolve_session, _rpc                # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]

BOND_BASE = "IdunBattle.Entities.Effects.ABondEffect"

# Les TROIS slots gates, dans l'ordre ou `CreateHandleTriggerAbilitiesInternal` les consulte.
SLOT_RANGE = 0x728          # (b) `Nullable<int>` -- portee au-dela de laquelle le bond tombe
SLOT_ADJACENT = 0x738       # (c) bool -- le bond exige l'ADJACENCE
SLOT_ON_DEATH = 0x748       # (a) bool -- le bond tombe a la mort/au retrait du bonde
SLOTS = (SLOT_RANGE, SLOT_ADJACENT, SLOT_ON_DEATH)


def _r(sid, m, b, t=60):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def _parents():
    """`fullName -> parent`, lu dans la table de symboles VERSIONNEE du build."""
    out = {}
    for path in (ROOT / "data" / "symbols").glob("*/frida/classes.tsv"):
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("#!"):
                    continue
                cols = line.rstrip("\n").split("\t")
                if len(cols) >= 3 and cols[0] and "<" not in cols[0]:
                    out[cols[0]] = cols[2]
    return out


def bond_effect_classes():
    """Toutes les classes dont la chaine de parents atteint `ABondEffect` (elle exclue)."""
    parents = _parents()
    out = []
    for name in parents:
        cur, seen = name, 0
        while cur and seen < 12:
            cur = parents.get(cur)
            seen += 1
            if cur == BOND_BASE:
                out.append(name)
                break
    return sorted(out)


def _split(full):
    i = full.rfind(".")
    return (full[:i], full[i + 1:]) if i > 0 else ("", full)


def _slots(sid, full):
    """Rend `{off: (ghidraVA, methodName)}` pour les trois slots gates de `full`.

    Une chaine `ghidraVA` VIDE = slot non materialise (classe jamais initialisee) : c'est un
    « non resolu », JAMAIS un verdict de surcharge -- le confondre ferait passer toute classe non
    initialisee pour un overrider (piege releve par #558)."""
    ns, cls = _split(full)
    got = {}
    for off in SLOTS:
        try:
            res = _r(sid, "resolveVtableSlot", {"ns": ns, "cls": cls, "start": off, "end": off}, 30)
        except Exception as exc:                                   # pragma: no cover - diagnostic
            got[off] = (None, "RPC:" + str(exc)[:40])
            continue
        if not res.get("ok"):
            got[off] = (None, (res.get("error") or "?")[:60])
            continue
        sl = (res.get("slots") or [{}])[0]
        va = sl.get("ghidraVA") or None
        got[off] = (va, sl.get("method"))
    return got


def step_vtable(sid):
    base = _slots(sid, BOND_BASE)
    print("BASE %s" % BOND_BASE)
    for off in SLOTS:
        va, name = base[off]
        print("  +0x%x  %-12s %s" % (off, va or "(non resolu)", name))
    if any(base[off][0] is None for off in SLOTS):
        print("")
        print("ABANDON : la base n'est pas resolue -- aucune comparaison n'a de sens.")
        return 1

    names = bond_effect_classes()
    print("")
    print("classes derivant de %s : %d" % (BOND_BASE.rsplit(".", 1)[1], len(names)))
    print("")
    over = {off: [] for off in SLOTS}
    unresolved = []
    for full in names:
        got = _slots(sid, full)
        if all(got[off][0] is None for off in SLOTS):
            unresolved.append((full, got[SLOTS[0]][1]))
            continue
        for off in SLOTS:
            va, name = got[off]
            if va is not None and va != base[off][0]:
                over[off].append((full, va, name))
    for off in SLOTS:
        print("SURCHARGES de +0x%x : %d / %d" % (off, len(over[off]), len(names)))
        for full, va, name in over[off]:
            print("    %-72s %-12s %s" % (full, va, name))
        print("")
    if unresolved:
        print("NON RESOLUES (aucun des 3 slots lisible) : %d" % len(unresolved))
        for full, err in unresolved:
            print("    %-72s %s" % (full, err))
    return 0


# ------------------------------------------------------------------------------------------------
# --step declared : QUI DECLARE le virtuel, et quelle valeur son corps rend
# ------------------------------------------------------------------------------------------------
GETTERS = {SLOT_RANGE: "get_Range",
           SLOT_ADJACENT: "get_Adjacent",
           SLOT_ON_DEATH: "get_RemoveOnBondedEntityDeath"}

# Corps TRIVIAUX dedupliques par IL2CPP, resolus au decompile ghidra a leur adresse. Les noms
# ghidra qui y sont attaches (`UnityEngine.U2D.IK.Solver2D$$DoValidate`, ...) sont ceux du
# proprietaire ARBITRAIRE du corps partage -- ils ne disent RIEN de l'appelant.
TRIVIAL = {"0x1802b4590": "true",           # `return 1`
           "0x1802b45a0": "false",          # `return 0` (1 octet)
           "0x1802b45b0": "none"}           # `return 0` (8 octets) = `Nullable<int>` VIDE


def _declared(sid, full, method, max_depth=8):
    """Rend `[(depth, klassName, ghidraVA)]` pour CHAQUE niveau qui DECLARE `method`."""
    ns, cls = _split(full)
    try:
        res = _r(sid, "resolveMethodPtr",
                 {"targets": [{"ns": ns, "cls": cls, "method": method}], "maxDepth": max_depth}, 30)
    except Exception as exc:                                       # pragma: no cover - diagnostic
        return None, "RPC:" + str(exc)[:40]
    tgt = (res.get("targets") or [{}])[0]
    if not tgt.get("ok", True) and tgt.get("error"):
        return None, str(tgt["error"])[:60]
    out = []
    for lvl in (tgt.get("levels") or []):
        for m in (lvl.get("methods") or []):
            va = ((m.get("raw") or {}).get("ghidraVA")
                  or (m.get("entry") or {}).get("ghidraVA"))
            out.append((lvl.get("depth"), lvl.get("name") or lvl.get("klass"), va))
    return out, None


def step_declared(sid):
    names = [BOND_BASE] + bond_effect_classes()
    print("QUI DECLARE les trois virtuels gates ? (%d classes, base incluse)" % len(names))
    print("Valeur = corps resolu par ADRESSE : %s" % TRIVIAL)
    print("")
    rows, errs = [], []
    for full in names:
        cells = []
        for off in SLOTS:
            got, err = _declared(sid, full, GETTERS[off])
            if got is None:
                errs.append((full, GETTERS[off], err))
                cells.append(("ERR", None, None))
                continue
            own = [(d, k, va) for d, k, va in got if d == 0]
            inh = [(d, k, va) for d, k, va in got if d != 0]
            src = own or inh
            if not src:
                cells.append(("ABSENT", None, None))
                continue
            d, k, va = src[0]
            cells.append(("OWN" if d == 0 else "herite d%d" % d, va,
                          TRIVIAL.get(va) or ("?" + str(va))))
        rows.append((full, cells))
    hdr = "%-70s | %s" % ("classe", " | ".join("%-26s" % GETTERS[o] for o in SLOTS))
    print(hdr)
    print("-" * len(hdr))
    for full, cells in rows:
        print("%-70s | %s"
              % (full.rsplit(".", 1)[1] if "." in full else full,
                 " | ".join("%-26s" % ("%s=%s" % (c[0], c[2]) if c[1] else c[0]) for c in cells)))
    print("")
    # Le VERDICT par classe : quels triggers de retrait sont CONSTRUITS.
    print("TRIGGERS DE RETRAIT CONSTRUITS (a = mort/retrait du bonde, b = portee, c = adjacence)")
    for full, cells in rows:
        a = cells[2][2] == "true"
        b = cells[0][2] not in ("none", None, "ERR")
        c = cells[1][2] == "true"
        tags = "".join(t for t, on in (("a", a), ("b", b), ("c", c)) if on) or "AUCUN"
        print("    %-70s %s" % (full.rsplit(".", 1)[1] if "." in full else full, tags))
    if errs:
        print("")
        print("ERREURS : %d" % len(errs))
        for full, m, err in errs[:8]:
            print("    %-60s %-30s %s" % (full, m, err))
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", default="declared", choices=["vtable", "declared", "all"])
    a = ap.parse_args()
    sid = _resolve_session()
    rc = 0
    if a.step in ("vtable", "all"):
        rc |= step_vtable(sid)
        print("")
    if a.step in ("declared", "all"):
        rc |= step_declared(sid)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
