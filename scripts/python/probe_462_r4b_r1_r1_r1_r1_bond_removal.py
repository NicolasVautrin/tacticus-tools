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
    des slots `+0x728` / `+0x738` / `+0x748`. Une adresse EGALE a celle de la base = pas de
    surcharge ; une adresse differente = surcharge, et le nom de methode identifie le virtuel.

Usage (ASCII only, depuis scripts/python) :
  python probe_462_r4b_r1_r1_r1_r1_bond_removal.py --step vtable
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", default="vtable", choices=["vtable"])
    a = ap.parse_args()
    sid = _resolve_session()
    return step_vtable(sid)


if __name__ == "__main__":
    raise SystemExit(main())
