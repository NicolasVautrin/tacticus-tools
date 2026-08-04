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
        ns, cls = _split(full)
        res = _r(sid, "resolveVtableSlot", {"ns": ns, "cls": cls, "start": 0x750, "end": 0x790}, 30)
        print("")
        print("SLOTS 0x750..0x790 de %s (les virtuels d'`APendingAttackEffect`)" % full)
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
        for _ in range(P247.WARMUP_ENDTURNS):
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
                    choices=["vtable", "declared", "gatelive", "killlive", "all"])
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
    if a.step in ("gatelive", "all"):
        rc |= step_gatelive(sid, a.seed, a.board)
        print("")
    if a.step in ("killlive", "all"):
        rc |= step_killlive(sid)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
