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

LE QUATRIEME VIRTUEL, `<klass+0x778>` (residu ferme par #462-r4b-r1-r1-r1-r1-c).
`IdunBattle.Entities.Effects.APendingAttackEffect$$get_RemoveOnBondedEntityDeath` ne rend pas une
constante : son corps est `NOT <klass+0x778>()`. Les 20 derivees d'`APendingAttackEffect` heritent
donc leur gate (a) d'un QUATRIEME virtuel, propre a cette sous-famille. Il est NOMME
`IsExecutedIfOwnerDies` -- mesure, pas deduction, et par DEUX voies concordantes :

  * `--step pending`, voie `class_get_methods` : les 20 derivees le DECLARENT toutes en propre
    (`depth 0`), corps `0x1802b4590` (= `return 1`, VRAI) ou `0x1802b45a0` (= `return 0`, FAUX) ;
  * `--step vtable` : sur une classe dont la vtable EST materialisee, le slot `+0x778` rend le meme
    couple (adresse, nom). Les slots voisins servent de CONTROLE de l'alignement --
    `+0x758 = GetAttackingUnitSelector`, `+0x768 = GetTriggeredAbilityType`, tous deux confirmes
    par `data/symbols/<build>/frida/methods.tsv`, qui les nomme pour les classes dont le corps
    n'est PAS dedupliqué.

⚠ POURQUOI LA PASSE PRECEDENTE A CONCLU << slot NULL, non resolvable >>. Les slots de cette vtable
sont a `0x728 / 0x738 / 0x748 / 0x758 / 0x768 / 0x778` -- alignes sur `...8`, PAS sur `...0`. Le
premier jet de ce pas balayait `0x750..0x790` par pas de 0x10, soit `0x750, 0x760, 0x770, 0x780` :
DECALE DE 8, donc a cote de CHAQUE slot. Il rendait des cases vides, ce qui s'est lu comme << aucune
vtable n'est materialisee >>. Un balayage aligne montre l'inverse : la vtable de
`SeekerMissileFrequencyLockTargetEffect` etait deja materialisee dans la session, et le nom se lisait
sans rien monter. LECON : sur un balayage de slots, l'alignement du `start` fait partie de la mesure
-- une plage vide n'est une absence QUE si l'on a d'abord prouve que la plage tombe sur les slots.

Usage (ASCII only, depuis scripts/python) :
  python probe_462_r4b_r1_r1_r1_r1_bond_removal.py --step vtable
  python probe_462_r4b_r1_r1_r1_r1_bond_removal.py --step declared
  python probe_462_r4b_r1_r1_r1_r1_bond_removal.py --step pending
  python probe_462_r4b_r1_r1_r1_r1_bond_removal.py --step all
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rl_collect_batch import _resolve_session, _rpc                # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]

BOND_BASE = "IdunBattle.Entities.Effects.ABondEffect"
PENDING_BASE = "IdunBattle.Entities.Effects.APendingAttackEffect"

# Les TROIS slots gates, dans l'ordre ou `CreateHandleTriggerAbilitiesInternal` les consulte.
SLOT_RANGE = 0x728          # (b) `Nullable<int>` -- portee au-dela de laquelle le bond tombe
SLOT_ADJACENT = 0x738       # (c) bool -- le bond exige l'ADJACENCE
SLOT_ON_DEATH = 0x748       # (a) bool -- le bond tombe a la mort/au retrait du bonde
SLOTS = (SLOT_RANGE, SLOT_ADJACENT, SLOT_ON_DEATH)

# Les TROIS virtuels que `APendingAttackEffect` AJOUTE aux precedents. Les deux premiers sont
# recoupes par `methods.tsv` (qui les nomme pour les classes au corps non dedupliqué) et servent de
# CONTROLE D'ALIGNEMENT du balayage ; le troisieme est le gate cherche.
SLOT_ATTACKING_SELECTOR = 0x758     # `GetAttackingUnitSelector` : ITargetsSelector
SLOT_TRIGGERED_ABILITY = 0x768      # `GetTriggeredAbilityType` : TriggeredAbilityType
SLOT_EXECUTED_IF_OWNER_DIES = 0x778  # `IsExecutedIfOwnerDies` : bool -- gate (a) de la sous-famille
PENDING_SLOTS = (SLOT_RANGE, SLOT_ADJACENT, SLOT_ON_DEATH,
                 SLOT_ATTACKING_SELECTOR, SLOT_TRIGGERED_ABILITY, SLOT_EXECUTED_IF_OWNER_DIES)


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


def derived_classes(base):
    """Toutes les classes dont la chaine de parents atteint `base` (elle exclue)."""
    parents = _parents()
    out = []
    for name in parents:
        cur, seen = name, 0
        while cur and seen < 12:
            cur = parents.get(cur)
            seen += 1
            if cur == base:
                out.append(name)
                break
    return sorted(out)


def bond_effect_classes():
    return derived_classes(BOND_BASE)


def pending_attack_classes():
    return derived_classes(PENDING_BASE)


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


def step_vtable(sid, with_runner=True, extra=()):
    """⚠ CE PAS EXIGE UN RUNNER VIVANT (mesure du 2026-08-04). Une vtable IL2CPP n'est materialisee
    qu'apres `il2cpp_runtime_class_init`, et c'est
    `IdunBattle.Core.Services.EffectsDatabase$$InitializeEffects` qui INSTANCIE toutes les classes
    d'effet -- au demarrage d'une bataille. Lance sans runner, le pas rend 3 classes materialisees
    sur 36 (les residus d'une session anterieure) et la BASE abstraite pointe sur le stub de
    remplissage paresseux `Unity.Burst.Unsafe$$AsRef` (qui ne retourne pas). Avec un runner vivant,
    tout se resout."""
    rid = None
    if with_runner:
        import probe_112_darkangels as PR
        import probe_462_r4b_r1_r1_defender_additive_carriers as P0
        rid = P0._build(sid, [P0.NEURO_CARRIER], [P0.NEURO_VICTIM])
        print("[runner] %d monte pour MATERIALISER les vtables (InitializeEffects)" % rid)
    try:
        return _step_vtable_inner(sid, extra)
    finally:
        if rid is not None:
            import probe_112_darkangels as PR
            PR.dispose(sid, rid)


def _step_vtable_inner(sid, extra=()):
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
    for full in extra:
        # ⚠ ALIGNEMENT : les slots sont a `...8` (0x728/0x738/.../0x778), pas a `...0`. Un balayage
        # depuis 0x750 tomberait A COTE de chacun et rendrait des cases vides -- ce qui s'etait lu
        # comme << aucune vtable materialisee >>, et a laisse le residu ouvert une passe entiere.
        ns, cls = _split(full)
        res = _r(sid, "resolveVtableSlot", {"ns": ns, "cls": cls,
                                            "start": SLOT_RANGE, "end": 0x788}, 30)
        print("")
        print("SLOTS 0x728..0x788 de %s (les virtuels d'`APendingAttackEffect`)" % full)
        for sl in (res.get("slots") or []):
            print("    %-8s %-14s %s" % (sl.get("off"), sl.get("ghidraVA") or "(vide)",
                                         sl.get("method")))
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


# ------------------------------------------------------------------------------------------------
# --step pending : le QUATRIEME virtuel `<klass+0x778> IsExecutedIfOwnerDies`
#
# LA QUESTION. `IdunBattle.Entities.Effects.APendingAttackEffect$$get_RemoveOnBondedEntityDeath` ne
# rend PAS une constante : son corps est `NOT <klass+0x778>()`. Les 20 derivees d'
# `APendingAttackEffect` heritent donc leur gate (a) d'un virtuel de plus, que `--step declared` ne
# regardait pas (il n'interrogeait que `get_Range` / `get_Adjacent` /
# `get_RemoveOnBondedEntityDeath`, et pour ces classes le troisieme rendait l'entree HERITEE de la
# base -- une adresse de code REEL, pas un corps trivial, donc illisible comme booleen).
#
# LES DEUX VOIES, ET POURQUOI ON JOUE LES DEUX.
#   * `class_get_methods` (colonne DECLARE) ne depend d'AUCUNE initialisation de classe : c'est la
#     seule qui couvre les 20, y compris celles qu'aucune bataille n'a instanciees.
#   * la VTABLE (colonne SLOT) ne repond que pour les classes materialisees, mais elle est la SEULE
#     a etablir le lien slot <-> nom : c'est elle qui NOMME `<klass+0x778>`. Sans elle, la colonne
#     DECLARE serait une valeur sans adresse d'appel.
# Les deux doivent CONCORDER sur toute classe materialisee ; le pas le verifie et le DIT.
#
# CONTROLE D'ALIGNEMENT, joue dans le meme balayage. `+0x758` et `+0x768` doivent rendre
# `GetAttackingUnitSelector` et `GetTriggeredAbilityType` -- deux noms que
# `data/symbols/<build>/frida/methods.tsv` porte independamment. S'ils ne tombent pas, le balayage
# est decale et AUCUNE valeur du pas ne vaut (c'est exactement la faute qui a laisse ce residu
# ouvert : un balayage `0x750..0x790` par pas de 0x10 rate les six slots).
# ------------------------------------------------------------------------------------------------
IS_EXECUTED_IF_OWNER_DIES = "IsExecutedIfOwnerDies"

# Ce que `methods.tsv` nomme independamment pour les deux slots de controle.
ALIGNMENT_CONTROL = {SLOT_ATTACKING_SELECTOR: "GetAttackingUnitSelector",
                     SLOT_TRIGGERED_ABILITY: "GetTriggeredAbilityType",
                     SLOT_EXECUTED_IF_OWNER_DIES: IS_EXECUTED_IF_OWNER_DIES}


def _pending_slot_row(sid, full):
    """`{off: (ghidraVA, nom)}` pour les six slots, balayes ALIGNES sur `...8`."""
    ns, cls = _split(full)
    res = _r(sid, "resolveVtableSlot",
             {"ns": ns, "cls": cls, "start": SLOT_RANGE, "end": SLOT_EXECUTED_IF_OWNER_DIES}, 30)
    if not res.get("ok"):
        return None
    out = {}
    for sl in (res.get("slots") or []):
        try:
            off = int(str(sl.get("off")), 16)
        except (TypeError, ValueError):
            continue
        out[off] = (sl.get("ghidraVA") or None, sl.get("method"))
    return out


def step_pending(sid):
    names = [PENDING_BASE] + pending_attack_classes()
    print("`<klass+0x778>` -- le QUATRIEME virtuel des derivees d'`APendingAttackEffect`")
    print("Corps triviaux resolus par ADRESSE : %s" % TRIVIAL)
    print("")
    hdr = ("%-48s | %-26s | %-26s | %s"
           % ("classe", "DECLARE IsExecutedIfOwnerDies", "SLOT +0x778 (vtable)",
              "=> get_RemoveOnBondedEntityDeath"))
    print(hdr)
    print("-" * len(hdr))
    verdicts, mismatches, misaligned, materialised = {}, [], [], []
    for full in names:
        short = full.rsplit(".", 1)[-1]
        got, err = _declared(sid, full, IS_EXECUTED_IF_OWNER_DIES)
        decl_va, decl = None, "ERR:" + str(err)[:20] if err else "ABSENT"
        if got:
            own = [(d, k, va) for d, k, va in got if d == 0]
            if own:
                decl_va = own[0][2]
                decl = TRIVIAL.get(decl_va) or ("?" + str(decl_va))
        row = _pending_slot_row(sid, full)
        slot_va, slot = None, "(non materialisee)"
        if row:
            slot_va, slot_name = row.get(SLOT_EXECUTED_IF_OWNER_DIES, (None, None))
            # ⚠ Le critere de MATERIALISATION est le `MethodInfo*` (donc le NOM), pas le pointeur de
            # code : une classe non initialisee porte le stub de remplissage paresseux
            # (`Unity.Burst.Unsafe$$AsRef`) a une adresse bien reelle, avec un `MethodInfo*` NUL.
            # Prendre l'adresse pour critere ferait passer la BASE ABSTRAITE -- qui n'est jamais
            # instanciee -- pour une classe lisible, et son slot vide pour un desalignement.
            if slot_name is None:
                slot_va = None
            if slot_va is not None:
                materialised.append(short)
                slot = "%s=%s" % (slot_name, TRIVIAL.get(slot_va) or ("?" + str(slot_va)))
                for off, expect in ALIGNMENT_CONTROL.items():
                    nm = (row.get(off) or (None, None))[1]
                    if nm != expect:
                        misaligned.append((short, hex(off), expect, nm))
                if decl_va is not None and slot_va != decl_va:
                    mismatches.append((short, decl_va, slot_va))
        # `get_RemoveOnBondedEntityDeath` = NOT `IsExecutedIfOwnerDies`.
        if decl in ("true", "false"):
            verdicts[short] = (decl == "false")
            verdict = "TRUE (le bond tombe)" if decl == "false" else "FALSE (le bond SURVIT)"
        else:
            verdict = "NON RESOLU"
        print("%-48s | %-26s | %-26s | %s" % (short, decl, slot, verdict))

    print("")
    print("CONTROLE D'ALIGNEMENT : %d classe(s) materialisee(s) -- %s"
          % (len(materialised), ", ".join(materialised) or "aucune"))
    if misaligned:
        print("  ECHEC : le balayage ne tombe PAS sur les slots attendus -- AUCUNE valeur ne vaut.")
        for short, off, expect, nm in misaligned:
            print("    %-40s %s attendu=%s lu=%s" % (short, off, expect, nm))
        return 2
    if not materialised:
        print("  AUCUNE classe materialisee : le lien slot <-> nom n'est pas etabli par CE run.")
        print("  La colonne DECLARE reste valable (elle ne depend d'aucune initialisation), mais")
        print("  rien ici ne prouve qu'elle repond au slot `+0x778`. NE PAS conclure seul.")
        return 3
    print("  OK : `+0x758`/`+0x768`/`+0x778` rendent bien "
          "`GetAttackingUnitSelector`/`GetTriggeredAbilityType`/`%s`." % IS_EXECUTED_IF_OWNER_DIES)
    if mismatches:
        print("")
        print("DESACCORD declare/vtable : %d -- le pas NE CONCLUT PAS." % len(mismatches))
        for short, dv, sv in mismatches:
            print("    %-40s declare=%s slot=%s" % (short, dv, sv))
        return 2
    print("  Les deux voies CONCORDENT sur chaque classe materialisee.")
    print("")
    armes = sorted(k for k, v in verdicts.items() if v)
    print("get_RemoveOnBondedEntityDeath VRAI (trigger (a) CONSTRUIT) : %d / %d"
          % (len(armes), len(verdicts)))
    print("FAUX (aucun trigger (a)) : %s"
          % ", ".join(sorted(k for k, v in verdicts.items() if not v)))
    return 0


# ------------------------------------------------------------------------------------------------
# --step pendingporteurs : les TROIS effets `APendingAttackEffect` que le port POSE sont-ils
# CONFRONTABLES sur le gate (a) ?
#
# Repondre a << quelle valeur >> ne suffit pas : le trigger (a) se declenche sur la MORT ou le
# RETRAIT du BONDE. Il faut donc etablir QUI est le bonde de chacun, et si cette entite peut mourir.
# Le pas le MESURE plutot que de le supposer, parce que les trois n'ont pas le meme bonde :
#
#   1308 `MalleusRocketLauncher`     -- `AddBondEffect(..., targets=TUILE, bond=owner@0x148)`
#                                       (`MalleusRocketLauncherAbility$$ExecuteBehaviour`)
#   1402 `DevastatingRefrain_Target` -- idem (`DevastatingRefrainAbility$$ExecuteBehaviour`)
#        -> pour les DEUX, l'owner est une MACHINE OF WAR : le bonde est une entite de type
#           `Machine`, pas une `Unit`.
#   1022 `ValkyrieStrike_Effect`     -- `AddBondEffect(..., caster@0x160 en 4e ET 6e position)`
#                                       (`ValkyrieStrikeAbility$$ExecuteBehaviour`), owner = une
#                                       UNITE (`astraSmnVoxcaster`).
#
# CE QUE LE PAS RAPPORTE, sans le deduire : pour chaque porteur, l'entite bondee telle que le RPC
# l'expose (`pos`, `hp`, `alive`), et si elle figure dans les cibles legales d'une attaque. Une
# entite sans tuile n'est frappable par AUCUNE attaque -- c'est ce qui decide si l'ecart de port
# est OBSERVABLE ou seulement sur le papier, et le pas doit le DIRE plutot que le conclure.
# ------------------------------------------------------------------------------------------------
PENDING_POSERS = (
    # (visualId, abilityType, effectType, role du porteur)
    ("astraOrdnanceBattery", 1142, 1308, "mow"),
    ("adeptExorcist", 1188, 1402, "mow"),
)


def step_pendingporteurs(sid, board="C1_02", seed=4242):
    import probe_90b_mow_effects as P90

    rc = 0
    for mow, ability, effect_type, role in PENDING_POSERS:
        state_file = ROOT / "logs" / ("_probe462c-%s-%d.json" % (mow, os.getpid()))
        state_file.parent.mkdir(parents=True, exist_ok=True)
        rid = P90.build(mow, board, str(state_file), seed=seed)
        if rid is None:
            print("[%s] build KO -- NON CONFRONTE (montage), aucun verdict" % mow)
            rc |= 2
            continue
        try:
            dv = _r(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)
            m = next((x for x in (dv.get("mows") or []) if x.get("visualId") == mow), None)
            if m is None:
                print("[%s] absent de decisionView.mows -- NON CONFRONTE" % mow)
                rc |= 2
                continue
            bonded = int(m["casterId"])
            print("[%s] ability=%d effet=%d ; BONDE = l'owner = casterId %d"
                  % (mow, ability, effect_type, bonded))
            print("   entite bondee : pos=%s hp=%s/%s alive=%s (type Machine, pas Unit)"
                  % (m.get("pos"), m.get("hp"), m.get("maxHp"), m.get("alive")))
            # Le bonde figure-t-il parmi les cibles LEGALES d'une attaque, cote adverse ?
            frappable = _is_targetable(sid, rid, dv, bonded)
            print("   cible legale d'une attaque ? %s" % frappable)
            if frappable is False and m.get("pos") is None:
                print("   => le BONDE n'a PAS de tuile et n'est cible d'AUCUNE attaque : sa mort")
                print("      n'est pas atteignable par le jeu. Le trigger (a) est CONSTRUIT cote")
                print("      natif mais INATTEIGNABLE. NON CONFRONTABLE -- ne rien porter serait")
                print("      indistinguable du natif, et le porter serait invalidable.")
            elif frappable:
                print("   => le BONDE est frappable : le bras de mise a mort est jouable.")
                rc |= 3          # 3 = confrontable, mais le bras n'est pas joue par CE pas
        finally:
            _r(sid, "disposeRunner", {"runnerId": rid}, 60)
    return rc


def _is_targetable(sid, rid, dv, entity_id):
    """`entity_id` figure-t-il dans les cibles LEGALES d'une des unites du plateau ?

    Rend `None` si aucune unite n'a pu etre interrogee -- une mesure vide n'est pas un << non >>."""
    interroge = 0
    for u in (dv.get("units") or []):
        if not u.get("alive"):
            continue
        uid = int(u["id"])
        at = _r(sid, "abilityTargets", {"runnerId": rid, "unitId": uid}, 90) or {}
        row = next((x for x in (at.get("units") or []) if x.get("unitId") == uid), None)
        if row is None:
            continue
        interroge += 1
        for a in (row.get("abilities") or []):
            for t in (a.get("targets") or []):
                if t.get("kind") == "unit" and int(t.get("targetId") or -1) == int(entity_id):
                    return True
    return False if interroge else None


# ------------------------------------------------------------------------------------------------
# --step valkyrielive : le SEUL des trois qui soit confrontable, et il l'est dans le SENS RARE
#
# `ValkyrieStrikeEffect` est la seule des trois classes du perimetre dont
# `IsExecutedIfOwnerDies` vaut VRAI, donc la seule dont `get_RemoveOnBondedEntityDeath` vaut FAUX :
# le natif ne construit AUCUN trigger (a) pour elle, et l'effet 1022 doit SURVIVRE a la mort de son
# bonde. C'est aussi la seule dont le bonde est une UNITE (`astraSmnVoxcaster`, le caster) et non une
# MoW -- donc la seule dont la mort soit atteignable.
#
# POURQUOI CE BRAS COMPTE PLUS QU'IL N'EN A L'AIR. Un port qui n'inscrit RIEN passe trivialement un
# bras << l'effet survit >>. Ce bras ne prouve donc pas le port : il prouve le NATIF, et c'est ce qui
# manquait. La valeur `true` de `IsExecutedIfOwnerDies` est lue sur un corps TRIVIAL DEDUPLIQUE
# (`0x1802b4590`, dont le proprietaire ghidra est `UnityEngine.U2D.IK.Solver2D$$DoValidate` -- un nom
# qui ne dit RIEN de l'appelant) ; la confronter au comportement observe est le seul moyen de
# verifier que la table `TRIVIAL` du probe dit vrai, et donc que les 19 AUTRES lignes -- lues par la
# meme table -- ne sont pas une illusion.
#
# CRITERE, ENONCE AVANT LA MESURE :
#   H0 (la lecture est juste, `RemoveOnBondedEntityDeath = FALSE`) -> apres la mort du BONDE, 1022
#      est ENCORE la.
#   H1 (la lecture est fausse) -> 1022 a disparu, et alors la table `TRIVIAL` est a refaire.
# CONTROLE : on releve 1022 AVANT la mise a mort. S'il n'y est pas, le bras ne mesure rien
# (montage), et le pas doit le DIRE plutot que de lire une absence comme une survie ratee -- c'est
# exactement le piege << vacuously vrai >> releve au §5 de la fiche.
# ------------------------------------------------------------------------------------------------
# LE MONTAGE, ET POURQUOI IL N'EST PAS CELUI DE `probe_245`. Mesure du 2026-08-05 avec le montage
# de `probe_245` tel quel (Vox a 5000 PV) : le Vox-caster SURVIT a dix tours de frappes, et pendant
# ce temps l'effet 1022 DISPARAIT TOUT SEUL -- consomme par l'AUTRE trigger de la sous-famille,
# `Triggered( On(0x15) & IsTurnOf(<0x758>()), TriggerAbility(...) & RemoveEffect(Effect) )`, qui est
# la frappe aerienne differee elle-meme. Un bras qui laisse passer un tour ne mesure donc RIEN du
# gate (a) : il mesure le second foyer de retrait. D'ou les deux exigences du montage --
#   * le bonde doit tomber en UNE frappe (PV bas + degat eleve), et
#   * AUCUN `endturn` entre le cast et la mise a mort.
# C'est la difference entre << adapter les rosters a l'objectif >> et << subir la geometrie >>.
VALKYRIE_EFFECT = 1022
VOX_HEALTH_KILLABLE = 60          # le bonde doit tomber en UNE frappe, avant tout changement de tour
ENEMY_DAMAGE = 40000              # idem -- aucun de ces deux champs n'entre dans ce qu'on mesure


def _build_valkyrie_killable(sid):
    """Runner du bras : Vox-caster spawne cote joueur, PV bas, ennemis a fort degat.

    Copie ASSUMEE du `_build` de `probe_245` (meme voie `initAndStart` + catalogue) : ce probe-ci a
    besoin de DEUX patchs de plus (PV du bonde, degat de l'ennemi) que 245 n'a aucune raison de
    porter -- son objet a lui est le masque de ciblage, pas la mise a mort."""
    import copy
    import json
    import catalog_inject as CI
    import probe_245_valkyrie_targeting as P245
    import rl_duel as RD

    state_file = ROOT / "logs" / ("_probe462c-valkyrie-%d.json" % os.getpid())
    state_file.parent.mkdir(parents=True, exist_ok=True)
    bc0, _added, _ab, _m = CI.augment(RD._load_seed_bc(None), [P245.VOXCASTER, P245.ENEMY],
                                      rank=P245.RANK)
    dump = RD._load_board_dump(P245.BOARD)
    template, _pool, _pmow = RD._normalize_and_extract_pool(sid, bc0, P245.RANK, board_dump=dump)
    bc = copy.deepcopy(template)
    vox = next((u for u in bc["Units"] if u.get("Id") == P245.VOXCASTER), None)
    if vox is None:
        raise RuntimeError("%s absent du catalogue BC.Units" % P245.VOXCASTER)
    vox["Health"] = VOX_HEALTH_KILLABLE
    vox["RemainingHealth"] = VOX_HEALTH_KILLABLE
    vox["Traits"] = list(P245.VOX_TRAITS)          # `Summon` retire : il rend l'unite AUTOMATIQUE
    foe = next((u for u in bc["Units"] if u.get("Id") == P245.ENEMY), None)
    if foe is not None:
        foe["Damage"] = ENEMY_DAMAGE
    RD._patch_predefined_units(bc, [P245.ENEMY, P245.ENEMY])
    # ⚠ ON DEPLACE LE BONDE, on ne subit pas la geometrie. Spawne au point JOUEUR habituel, le
    # Vox-caster est hors de portee des deux ennemis, et les rapprocher coute des `endturn` -- que
    # ce bras s'interdit (ils consommeraient l'effet par l'autre trigger). On le spawne donc sur un
    # point du groupe ADVERSE, en gardant `playerId = HUMAN` : il reste NOTRE unite (donc c'est bien
    # SON cast), mais il nait au contact de ses futurs bourreaux. Le dernier point du groupe est
    # choisi parce que les deux `PredefinedUnits` consomment les premiers.
    spawns = RD._spawn_points_by_twpi(bc)
    foe_pts = [pts for twpi, pts in sorted(spawns.items()) if twpi != 0 and pts]
    pts = foe_pts[0] if foe_pts else (spawns.get(0) or [])
    if not pts:
        raise RuntimeError("aucun spawn point exploitable sur %s" % P245.BOARD)
    col, row = pts[-1]
    pu = [{"unitId": P245.VOXCASTER, "playerId": RD.PLAYER_ID_HUMAN,
           "col": int(col), "row": int(row)}]
    resp = _rpc(sid, "initAndStart",
                [{"configJson": json.dumps(bc), "seed": P245.SEED, "playerUnits": pu,
                  "owner": str(state_file.resolve())}], timeout=120)
    rid = ((resp or {}).get("result") or {}).get("runnerId")
    if rid is None:
        raise RuntimeError("initAndStart KO: %s" % json.dumps(resp)[:400])
    state_file.write_text(json.dumps({"runnerId": int(rid)}), encoding="utf-8")
    return int(rid)


def _effects_everywhere(sid, rid, effect_type):
    """Ou l'effet `effect_type` se trouve-t-il : sur des UNITES, sur des TUILES, ou nulle part ?

    Les deux canaux sont lus, parce que `AddBondEffect` itere un selecteur d'ENTITES et que ses
    cibles peuvent etre des tuiles (`MalleusRocketLauncherAbility`) comme des unites. Ne lire que
    `decisionView.units` ferait passer un effet de TUILE pour absent."""
    dv = _r(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)
    tm = _r(sid, "tileMeta", {"runnerId": rid}, 90) or {}
    units = [int(u["id"]) for u in (dv.get("units") or [])
             if any(int(e.get("effectType") or -1) == effect_type for e in (u.get("effects") or []))]
    mows = [int(m["casterId"]) for m in (dv.get("mows") or [])
            if any(int(e.get("effectType") or -1) == effect_type for e in (m.get("effects") or []))]
    tiles = [(t.get("col"), t.get("row")) for t in (tm.get("tiles") or [])
             if any(int(e.get("effectType") or -1) == effect_type for e in (t.get("effects") or []))]
    return {"units": units, "mows": mows, "tiles": tiles,
            "total": len(units) + len(mows) + len(tiles)}


def _kill_no_endturn(sid, rid, victim_id, victim_owner, tries=6):
    """Tue `victim_id` avec les unites adverses, SANS aucun `endturn`.

    Le `endturn` est proscrit ici, et ce n'est pas un detail de confort : il fait passer le tour,
    donc declencher `On(0x15)`, donc consommer l'effet par l'AUTRE trigger de la sous-famille. Un
    bras qui en joue un mesure le mauvais foyer de retrait (mesure du 2026-08-05)."""
    import probe_112_darkangels as PR

    for _ in range(tries):
        d = _r(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)
        v = next((u for u in (d.get("units") or []) if int(u["id"]) == int(victim_id)), None)
        if v is None or not v.get("alive"):
            return True
        fired = False
        for u in (d.get("units") or []):
            if not u.get("alive") or u.get("owner") == victim_owner:
                continue
            aid = next((a.get("id") for a in (u.get("abilities") or [])
                        if a.get("kind") != "passive"), None)
            if aid is None:
                continue
            if int(victim_id) not in PR.legal_from_here(sid, rid, int(u["id"]), aid):
                continue
            PR.act(sid, rid, {"kind": "ability", "casterId": int(u["id"]),
                              "targetId": int(victim_id), "abilityType": aid})
            fired = True
        if not fired:
            break
    d = _r(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)
    v = next((u for u in (d.get("units") or []) if int(u["id"]) == int(victim_id)), None)
    return (v is None) or (not v.get("alive"))


def step_valkyrielive(sid):
    import probe_245_valkyrie_targeting as P245
    import probe_112_darkangels as PR

    rid = _build_valkyrie_killable(sid)
    print("[build] runner=%d board=%s seed=%s (Vox a %d PV, ennemi a %d de degat)"
          % (rid, P245.BOARD, P245.SEED, VOX_HEALTH_KILLABLE, ENEMY_DAMAGE))
    try:
        dv, vox = P245._to_my_turn(sid, rid)
        if vox is None:
            print("[FAIL] voxcaster absent -- montage KO, AUCUN verdict")
            return 2
        cid = int(vox["id"])
        at = _r(sid, "abilityTargets",
                {"runnerId": rid, "unitId": cid, "abilityType": P245.VALKYRIE_STRIKE}, 120) or {}
        row = next((x for x in (at.get("units") or []) if x.get("unitId") == cid), None)
        tgts = ((row.get("abilities") or [{}])[0].get("targets") or []) if row else []
        if not tgts:
            print("[FAIL] aucune cible legale pour ValkyrieStrike -- AUCUN verdict")
            return 2
        pick = next((t for t in tgts if t.get("kind") == "unit"), tgts[0])
        act = {"kind": "ability", "casterId": cid, "abilityType": P245.VALKYRIE_STRIKE}
        if pick.get("kind") == "unit":
            act["targetId"] = pick["targetId"]
        else:
            act["to"] = {"col": pick["tile"]["col"], "row": pick["tile"]["row"]}
        r = _r(sid, "applyAction", {"runnerId": rid, "action": act}, 150) or {}
        a0 = (r.get("actions") or [{}])[0]
        before = _effects_everywhere(sid, rid, VALKYRIE_EFFECT)
        print("[cast] pick=%s ok=%s mut=%s -> effet 1022 : %s"
              % (pick, a0.get("ok"), a0.get("mutated"), before))
        if before["total"] == 0:
            print("[FAIL] 1022 n'est POSE nulle part -- le bras ne mesure RIEN (montage).")
            return 2

        # Mise a mort du BONDE = le caster (`caster@0x160` en 4e ET 6e position du natif).
        # `applyAction` ne verifie pas la propriete du `unitId` (runner.md §4), donc on pilote
        # l'adversaire pour frapper notre propre Vox-caster -- SANS `endturn`, sinon la frappe
        # aerienne differee consomme l'effet et on ne mesure plus le gate (a).
        dead = _kill_no_endturn(sid, rid, cid, vox.get("owner"))
        after = _effects_everywhere(sid, rid, VALKYRIE_EFFECT)
        print("[apres] bonde mort=%s -> effet 1022 : %s" % (dead, after))
        print("")
        if not dead:
            print("VERDICT : NON CONFRONTE -- le Vox-caster n'a pas pu etre tue.")
            return 2
        if after["total"] > 0:
            print("VERDICT H0 : 1022 SURVIT a la mort de son bonde. La lecture")
            print("  `IsExecutedIfOwnerDies = true` -> `get_RemoveOnBondedEntityDeath = FALSE`")
            print("  est CONFIRMEE, et avec elle la table `TRIVIAL` par laquelle les 19 autres")
            print("  lignes sont lues. Le port, qui n'inscrit aucun trigger pour 1022, est")
            print("  CONFORME sur ce point.")
            return 0
        print("VERDICT H1 : 1022 a DISPARU a la mort du bonde -- la lecture du gate est REFUTEE.")
        return 1
    finally:
        PR.dispose(sid, rid)


# ------------------------------------------------------------------------------------------------
# --step gatelive : le gate `NOT AmountIsZero(BondedEntity)` mord-il, OUI ou NON ?
#
# LA QUESTION, ET POURQUOI ELLE PRECEDE TOUT PORTAGE.
# Les trois triggers partagent le conjoint `NOT AmountIsZero(BondedEntityFromEffect(Effect))`.
# `IdunBattleLogic.Entities.DSLTriggers$$AmountIsZero(selector)` construit
# `NOT AmountIsGreaterAbilityTrigger(selector, <DSLFormulas+0x20>)`, et
# `IdunBattle.Entities.Conditions.AmountIsGreaterAbilityTrigger$$ShouldTrigger` rend
# `minAmount < amount`. Or `DSLFormulas+0x20` est `Direct(1)`, PAS `Direct(0)` :
#   * `IdunBattleLogic.Entities.DSLFormulas$$.ctor` ecrit `+0x18 <- Direct(0)`, `+0x20 <- Direct(1)`,
#     `+0x28 <- Direct(2)`, `+0x30 <- Direct(100)`, `+0x38 <- Direct(-1)` ;
#   * `IdunBattleLogic.Entities.DSLTriggers$$AmountIsGreaterThanZero`, lui, lit `+0x18` -- le nom
#     colle donc a `minAmount = 0`, et `AmountIsZero` lit un AUTRE slot ;
#   * `IdunBattle.Entities.Effects.Loki.NeuroparasiteEffect$$GetIncreaseLevelBehaviour` passe
#     exactement `+0x20` comme INCREMENT, et #556 a mesure LIVE niveau 1 -> 2. `+0x20` vaut 1.
# Donc `AmountIsZero(x) == (count(x) <= 1)` -- pas `== 0`. Et `BondedEntityFromEffect` est un
# `TargetSelector` SINGULIER (`IdunBattle.Entities.Selectors.SelectBondedEntityFromEffectSelector$$
# Select` rend `[]` ou `[entite]`), donc `count <= 1` est TOUJOURS vrai et `NOT AmountIsZero`
# TOUJOURS FAUX -- ce qui rendrait les trois triggers structurellement morts.
#
# C'est une lecture, pas un verdict : on la CONFRONTE. Le porteur choisi est `TauntedEffect`
# (`get_Range = Nullable<int>(1)`, `get_RemoveOnBondedEntityDeath = true` -> triggers (a) ET (b)),
# pose par `CrushingClaws` (1105) du HERO `tyranTyrantGuard`, deja monte par
# `probe_436_taunt_targeting.py`. Le bras (b) est le SEUL discriminant propre : aucun autre
# mecanisme du jeu ne retire un taunt sur un DEPLACEMENT.
#
# CRITERE, ENONCE AVANT LA MESURE :
#   H0 (le gate mord)         -> apres avoir eloigne le taunte a d >= 2 du tauntant, l'effet 27
#                                (et ses enfants) DISPARAIT de la vue.
#   H1 (le gate est mort)     -> les effets RESTENT.
# CONTROLE OBLIGATOIRE, dans le meme run : un deplacement qui GARDE d == 1 emet le meme
# `On(0x1d = UnitPositionChanged_2)` mais laisse `IsInRange` vrai. S'il retirait deja l'effet, la
# mesure ne dirait rien du terme de PORTEE -- elle ne mesurerait que « bouger retire le taunt ».
# ------------------------------------------------------------------------------------------------
CRUSHING = 1105                      # `CrushingClaws`, RANGE_ADJACENT, HERO `tyranTyrantGuard`
THIRD_UNIT = "ultraCalgar"           # unite TIERCE du controle -- aucun lien avec le bond
TAUNT_FAMILY = (25, 26, 27, 1237)    # 27 COMPOSITE -> enfants 25 / 26 / 1237


def _taunt_effects(dv, uid):
    out = []
    for u in (dv.get("units") or []):
        if int(u.get("id") or -1) == int(uid):
            for e in (u.get("effects") or []):
                et = e.get("effectType")
                if et is not None and int(et) in TAUNT_FAMILY:
                    out.append(int(et))
    return sorted(out)


def step_gatelive(sid, seed="777", board="MC1_67"):
    import hexgeo
    import probe_247_splash_targeting as P247
    import probe_436_taunt_targeting as P436

    rid, _state = P436._build(sid, seed, board, P436.P_UNITS, P436.A_UNITS_DEFAUT)
    print("[build] runner=%d board=%s seed=%s" % (rid, board, seed))
    try:
        for _ in range(P247.TOURS_DE_CHAUFFE):
            P247._act(sid, rid, {"kind": "endturn"}, 60)
        tauntee = P436._make_adjacent(sid, rid, "tyranTyrantGuard")
        if tauntee is None:
            print("[FAIL] pas de contact -- montage KO, AUCUN verdict")
            return 2
        P247._give_turn_to(sid, rid, "tyranTyrantGuard")
        dv = P247._dv(sid, rid)
        guard = P247._by_vis(dv, "tyranTyrantGuard")
        cid = int(guard["id"])
        r = P247._act(sid, rid, {"kind": "ability", "casterId": cid,
                                 "abilityType": CRUSHING, "targetId": tauntee}, 120)
        mutated = ((r or {}).get("actions") or [{}])[0].get("mutated")
        dv = P247._dv(sid, rid)
        eff0 = _taunt_effects(dv, tauntee)
        d0 = hexgeo.distance(P247._pos(P247._by_vis(dv, "tyranTyrantGuard")),
                             P247._pos(next(u for u in dv["units"] if int(u["id"]) == tauntee)))
        print("[cast] CrushingClaws u%d -> u%d  mutated=%s  effets=%s  d=%d"
              % (cid, tauntee, mutated, eff0, d0))
        if not eff0:
            print("[FAIL] le taunt n'est pas pose -- AUCUN verdict (montage, pas mecanique)")
            return 2

        def _snap(tag):
            d = P247._dv(sid, rid)
            g = P247._by_vis(d, "tyranTyrantGuard")
            t = next((u for u in d["units"] if int(u["id"]) == tauntee), None)
            dist = (hexgeo.distance(P247._pos(g), P247._pos(t))
                    if (g is not None and t is not None) else None)
            ef = _taunt_effects(d, tauntee)
            print("  [%-22s] d=%-4s effets=%s" % (tag, dist, ef))
            return dist, ef

        _snap("post-cast")
        P247._act(sid, rid, {"kind": "endturn"}, 60)
        d_a, ef_a = _snap("apres endturn")
        if not ef_a:
            print("[FAIL] le taunt est deja tombe a l'endturn (duree) -- le bras PORTEE est "
                  "inobservable sur ce montage. AUCUN verdict sur le gate.")
            return 2

        # CONTROLE 1 -- DUREE PURE : un `endturn` de plus, personne ne bouge.
        P247._act(sid, rid, {"kind": "endturn"}, 60)
        d_t2, ef_t2 = _snap("CTRL duree +1 tour")
        if not ef_t2:
            print("[FAIL] duree epuisee sans qu'aucune unite ne bouge -- rien d'attribuable au "
                  "trigger. AUCUN verdict.")
            return 2

        # CONTROLE 2 -- EVENT GLOBAL : un AUTRE ennemi bouge. `On(0x1d)` est publie, mais ni
        # l'`Owner` (le taunte) ni le `BondedEntity` (le tauntant) n'ont change de tuile, donc
        # `IsInRange` reste vrai. Si le taunt tombait ICI, la mesure ne dirait rien du terme de
        # PORTEE : elle ne mesurerait que « un mouvement quelconque retire le taunt ».
        d = P247._dv(sid, rid)
        tu = next(u for u in d["units"] if int(u["id"]) == tauntee)
        other = next((u for u in d["units"]
                      if u.get("alive") and u.get("owner") == tu.get("owner")
                      and int(u["id"]) != tauntee), None)
        if other is not None:
            P247._step_toward(sid, rid, int(other["id"]), P247._pos(tu), 5)
            d_o, ef_o = _snap("CTRL autre unite bouge")
        else:
            d_o, ef_o = None, ef_t2
            print("  [CTRL autre unite bouge] aucun allie du taunte -- controle NON JOUE")

        # CONTROLE 3 -- ACTION DU TAUNTE : il bouge en RESTANT a d == 1. Meme event, `IsInRange`
        # toujours vrai. Ce controle-la separe « le taunte a agi » de « la portee est rompue ».
        before = P247._pos(next(u for u in P247._dv(sid, rid)["units"] if int(u["id"]) == tauntee))
        P247._step_toward(sid, rid, tauntee, P247._pos(P247._by_vis(P247._dv(sid, rid),
                                                                    "tyranTyrantGuard")), 1)
        after = P247._pos(next(u for u in P247._dv(sid, rid)["units"] if int(u["id"]) == tauntee))
        d_c, ef_c = _snap("CTRL taunte bouge d=1")
        print("  (tuile du taunte : %s -> %s, change=%s)" % (before, after, before != after))

        # LE BRAS -- LA PORTEE : eloigner a d >= 2.
        for _ in range(6):
            g = P247._by_vis(P247._dv(sid, rid), "tyranTyrantGuard")
            if g is None:
                break
            if not P247._step_toward(sid, rid, tauntee, P247._pos(g), 4):
                P247._act(sid, rid, {"kind": "endturn"}, 60)
            d_now, _ = _snap("eloignement")
            if d_now is not None and d_now >= 2:
                break
        d_b, ef_b = _snap("APRES eloignement")

        print("")
        print("VENTILATION : cast=%s  endturn=%s  duree+1=%s  autre-bouge=%s  taunte-d1=%s  "
              "d>=2=%s" % (bool(eff0), bool(ef_a), bool(ef_t2), bool(ef_o), bool(ef_c),
                           bool(ef_b)))
        if ef_c and d_b is not None and d_b >= 2 and not ef_b:
            print("VERDICT H0 : le gate MORD, et le terme de PORTEE est ISOLE (d=1 garde, "
                  "d=%d retire)." % d_b)
            return 0
        if ef_c and ef_b:
            print("VERDICT H1 : le gate NE MORD PAS -- taunt encore present a d=%s." % d_b)
            return 0
        if ef_o and not ef_c:
            print("VERDICT PARTIEL : le retrait est declenche par l'ACTION DU TAUNTE, pas par la "
                  "rupture de portee. Le gate `NOT AmountIsZero` MORD donc (quelque chose retire), "
                  "mais le terme `IsInRange` n'est PAS isole par ce montage.")
            return 3
        print("VERDICT INDETERMINE -- voir la ventilation ci-dessus.")
        return 2
    finally:
        _r(sid, "disposeRunner", {"runnerId": rid}, 60)


# ------------------------------------------------------------------------------------------------
# --step killlive : le trigger (a), sur le porteur du cas -- `NeuroparasiteEffect`
#
# POURQUOI CE PORTEUR PLUTOT QUE LE TAUNT. Mesure du 2026-08-04 (`--step gatelive`) : le taunt de
# `CrushingClaws` est pose avec `TurnsFromRounds(1)` et TOMBE au deuxieme `endturn` SANS QUE
# PERSONNE NE BOUGE -- sa duree epuise le montage avant que le terme de PORTEE soit exercable.
# `NeuroparasiteEffect` est l'oppose exact : `AddBondEffect` y passe des options VIDES, donc
# `DefaultAmountOfRounds(0x4c2)` absente, donc effet PERMANENT (`remaining = 0`, atteste par #556).
# Et `--step declared` lui donne `get_RemoveOnBondedEntityDeath = true`, `get_Range = none`,
# `get_Adjacent = false` : le trigger (a) est le SEUL construit sur cette classe, donc tout retrait
# observe lui est attribuable.
#
# CRITERE, ENONCE AVANT LA MESURE. Le parasite est pose sur la victime, `bonded` = le Neurothrope.
# On TUE le Neurothrope (le BONDE, pas le porteur).
#   H0 (le gate mord) -> l'effet 1218 DISPARAIT de la victime.
#   H1 (le gate est mort, cf. la lecture `AmountIsZero == count <= 1` ci-dessus) -> il RESTE.
# CONTROLE : on tue d'abord une unite TIERCE. Le trigger porte `IsEntityWithIdTarget(BondedEntity)`,
# donc une mort qui n'est pas celle du bonde ne doit RIEN retirer. Sans ce controle, un retrait
# observe pourrait n'etre qu'un nettoyage generique declenche par n'importe quelle mort.
# ------------------------------------------------------------------------------------------------
def _kill_via(sid, rid, attacker_id, victim_id, tag):
    """Frappe `victim_id` avec `attacker_id` (la VICTIME parasitee) jusqu'a sa mort. `applyAction`
    ne verifie pas la propriete du `unitId` (runner.md §4), donc on pilote l'unite adverse.
    Rend `(mort ?, parasite encore present sur `attacker_id` ?)`.

    EXPOSE au niveau module -- le test live `test_462_r4b_r1_r1_r1_r1_bond_removal_live.py` le
    rejoue tel quel : la boucle de mise a mort n'est PAS ce qu'on mesure, la dupliquer ferait deux
    montages a maintenir pour une seule mecanique."""
    import probe_112_darkangels as PR
    import probe_462_r4b_r1_r1_defender_additive_carriers as P0
    import probe_462_r4b_r1_r1_r1_neuroparasite_pose as P1

    for _ in range(10):
        d = PR.rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        v = next((u for u in (d.get("units") or []) if int(u["id"]) == int(victim_id)), None)
        if v is None or not v.get("alive"):
            break
        aid = P0._normal_attack_id(d, attacker_id)
        p = PR.positions(d)
        if int(victim_id) not in PR.legal_from_here(sid, rid, attacker_id, aid):
            if int(victim_id) in p:
                P0._move_within(sid, rid, d, attacker_id, p[int(victim_id)], 1, min_dist=1)
            if int(victim_id) not in PR.legal_from_here(sid, rid, attacker_id, aid):
                PR.act(sid, rid, {"kind": "endturn"})
                continue
        PR.act(sid, rid, {"kind": "ability", "casterId": attacker_id, "targetId": int(victim_id),
                          "abilityType": aid})
        PR.act(sid, rid, {"kind": "endturn"})
    d = PR.rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    v = next((u for u in (d.get("units") or []) if int(u["id"]) == int(victim_id)), None)
    dead = (v is None) or (not v.get("alive"))
    pres, lvl = P1._live_parasite(d, attacker_id)
    print("  [%-22s] u%s mort=%s   parasite sur u%s = %s (level %s)"
          % (tag, victim_id, dead, attacker_id, pres, lvl))
    return dead, pres


def step_killlive(sid):
    import probe_112_darkangels as PR
    import probe_462_r4b_r1_r1_defender_additive_carriers as P0
    import probe_462_r4b_r1_r1_r1_neuroparasite_pose as P1

    # UN SEUL ennemi (montage EPROUVE de #556 : `anchor`/`occupied` sont derives du layout adverse,
    # et deux ennemis de MEME `visualId` s'ecrasent dans ce dict -> ancrage faux, mesure du
    # 2026-08-04 : « le Neurothrope ne peut pas frapper la victime en PSYCHIQUE »). L'unite TIERCE
    # du controle est donc dans NOTRE camp -- elle n'a rien a voir avec le bond et c'est justement
    # ce qu'on veut : sa mort ne doit RIEN retirer.
    p_units = [P0.NEURO_CARRIER, THIRD_UNIT]
    a_units = [P0.NEURO_VICTIM]
    layout = P0._enemy_layout(sid, p_units, a_units)
    if P0.NEURO_VICTIM not in layout:
        print("[FAIL] victime absente du layout adverse : %s" % sorted(layout))
        return 2
    # Le Neurothrope doit etre TUABLE (c'est tout l'objet du bras) ; la victime doit survivre et
    # frapper fort. Aucun de ces champs n'entre dans ce qu'on mesure (presence/absence de 1218).
    patch = {P0.NEURO_CARRIER: {"Health": 1000, "RemainingHealth": 1000},
             THIRD_UNIT: {"Health": 1000, "RemainingHealth": 1000},
             P0.NEURO_VICTIM: {"Health": 300000, "RemainingHealth": 300000, "Damage": 400000}}
    rid = P0._build(sid, p_units, a_units, armor=P0.ARMOR_FLAT, unit_patch=patch,
                    anchor=layout[P0.NEURO_VICTIM], occupied=list(layout.values()))
    try:
        dv = PR.rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        bv = PR.units_by_visual(dv)
        if P0.NEURO_CARRIER not in bv or P0.NEURO_VICTIM not in bv:
            print("[FAIL] roster incomplet : %s" % sorted(bv))
            return 2
        neuro = bv[P0.NEURO_CARRIER]["id"]
        tgt = int(bv[P0.NEURO_VICTIM]["id"])
        third = int(bv[THIRD_UNIT]["id"]) if THIRD_UNIT in bv else None
        normal_id = P0._normal_attack_id(dv, neuro)
        pos = PR.positions(dv)
        ok, dv = P0._move_within(sid, rid, dv, neuro, pos[tgt], P0.NEURO_RANGE, min_dist=2)
        if not ok or tgt not in PR.legal_from_here(sid, rid, neuro, normal_id):
            print("[FAIL] geometrie : le Neurothrope ne peut pas frapper la victime en PSYCHIQUE")
            return 2
        r = PR.act(sid, rid, {"kind": "ability", "casterId": neuro, "targetId": tgt,
                              "abilityType": normal_id})
        dv = PR.rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        present, level = P1._live_parasite(dv, tgt)
        print("[pose] attaque psychique u%d -> u%d : ok=%s  parasite=%s level=%s"
              % (neuro, tgt, r.get("ok"), present, level))
        if not present:
            print("[FAIL] parasite NON pose -- montage KO, AUCUN verdict")
            return 2

        def _kill(victim_id, tag):
            return _kill_via(sid, rid, tgt, victim_id, tag)

        if third is None:
            print("  [CTRL mort TIERCE] %s absent du roster -- controle NON JOUE" % THIRD_UNIT)
            dead3, pres3 = False, True
        else:
            dead3, pres3 = _kill(third, "CTRL mort TIERCE")
        deadN, presN = _kill(neuro, "mort du BONDE")

        print("")
        if not deadN:
            print("VERDICT : NON CONFRONTE -- le Neurothrope n'a pas pu etre tue.")
            return 2
        if dead3 and not pres3:
            print("VERDICT INDETERMINE : le parasite est deja tombe a la mort d'une unite TIERCE. "
                  "Le retrait n'est pas attribuable a `IsEntityWithIdTarget(BondedEntity)`.")
            return 2
        if not presN:
            print("VERDICT H0 : le gate MORD. La mort d'une TIERCE laisse le parasite (%s), celle "
                  "du BONDE le retire. Le trigger (a) d'`ABondEffect` est VIVANT." % pres3)
            return 0
        print("VERDICT H1 : le gate NE MORD PAS -- parasite encore present apres la mort du bonde.")
        return 0
    finally:
        PR.dispose(sid, rid)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", default="declared",
                    choices=["vtable", "declared", "pending", "pendingporteurs", "valkyrielive",
                             "gatelive", "killlive", "all"])
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    a = ap.parse_args()
    sid = _resolve_session()
    rc = 0
    if a.step in ("vtable", "all"):
        rc |= step_vtable(sid, extra=("IdunBattle.Entities.Effects.Loki.ValkyrieStrikeEffect",
                                      "IdunBattle.Entities.Effects.OwnerPendingAttackEffect"))
        print("")
    if a.step in ("declared", "all"):
        rc |= step_declared(sid)
        print("")
    if a.step in ("pending", "all"):
        rc |= step_pending(sid)
        print("")
    if a.step in ("pendingporteurs", "all"):
        rc |= step_pendingporteurs(sid)
        print("")
    if a.step in ("valkyrielive", "all"):
        rc |= step_valkyrielive(sid)
        print("")
    if a.step in ("gatelive", "all"):
        rc |= step_gatelive(sid, a.seed, a.board)
        print("")
    if a.step in ("killlive", "all"):
        rc |= step_killlive(sid)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
