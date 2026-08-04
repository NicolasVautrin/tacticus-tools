"""#419-r1-tr14-r5-r2-r1-r1-r1-r2 -- la famille `ShouldExecute` = `utility > <seuil statique>`.

DOUZE corps natifs, tous de la MEME forme, lue verbatim au decompile :

    // <X>Playbook$$ShouldExecute
    y = *(*(Il2CppClass*<X>Playbook + 0xb8));      // = le PREMIER champ statique de la classe
    return Fix64.op_GreaterThan(attackHealUtility, y);

`+0xb8` = `Il2CppClass.static_fields` ; la double indirection lit donc le champ statique d'offset 0.
Le seuil ne se DEDUIT pas : il s'ecrit dans le `.cctor` de la classe, et QUATRE des douze classes
seulement en declarent un.

## Ce que ce probe MESURE (et pourquoi il existe)

Deux etapes, deux sources INDEPENDANTES, parce que le point qui decide du port -- « cette classe
a-t-elle un `.cctor` ? » -- est exactement celui ou un grep negatif ne prouve RIEN (dedup IL2CPP des
corps triviaux, bases generiques absentes du dump Frida) :

  * **etape 1 (OFFLINE)** : le recensement des `.cctor` dans `data/symbols/<build>/frida/methods.tsv`
    (produit par l'enumeration IL2CPP `class_get_methods`, pas par Ghidra) ;
  * **etape 2 (LIVE)** : `resolveMethodPtr` sur `{.cctor, ShouldExecute}` pour les douze classes --
    l'enumeration `class_get_methods` REFAITE dans le processus, chaine de parents comprise. Le
    TEMOIN de cette etape est `ShouldExecute` : il DOIT apparaitre a `depth 0` sur les douze, sinon
    l'absence de `.cctor` ne mesure que la panne du RPC.

Un `.cctor` absent des DEUX sources ==> le champ statique n'est jamais ecrit ==> il vaut ce que
`Class::Init` y a laisse, c.-a-d. **zero** (`static_fields` est alloue zero-initialise). Le seuil est
alors `Fix64(0)`, et le gate se lit `utility > 0`.

## Le tableau attendu, ENONCE AVANT LA MESURE

| classe (`IdunBattle.AI.Playbook[.Loki]`)   | ability            | `.cctor` | seuil     |
|--------------------------------------------|--------------------|----------|-----------|
| `BlightGrenadesPlaybook`                    | 1176 BlightGrenades| OUI      | `Fix64(1)`|
| `Loki.FlailSwingPlaybook`                   | 1042 FlailSwing    | OUI      | `Fix64(1)`|
| `Loki.MomentShacklePlaybook`                | 1184 MomentShackle | OUI      | `Fix64(1)`|
| `Loki.PlasmaCannonPlaybook`                 | 1150 PlasmaCannon  | OUI      | `Fix64(1)`|
| `Loki.AncestralFortunePlaybook`             | 1207               | non      | `Fix64(0)`|
| `Loki.ExcruciatingFrequenciesPlaybook`      | 1197               | non      | `Fix64(0)`|
| `Loki.PlagueWindPlaybook`                   | 1035               | non      | `Fix64(0)`|
| `Loki.ScytheOfDustPlaybook`                 | 1074               | non      | `Fix64(0)`|
| `Loki.ScythingTalonsPlaybook`               | 1065               | non      | `Fix64(0)`|
| `Loki.SeekerMissileFrequencyLockPlaybook`   | 1069               | non      | `Fix64(0)`|
| `Loki.StaffOfStarsPlaybook`                 | 1073               | non      | `Fix64(0)`|
| `Loki.SuperchargePlaybook`                  | 1103               | non      | `Fix64(0)`|

Les quatre `.cctor` ecrivent tous `Fix64.op_Implicit(1)` a l'offset 0 des statics -- lu un par un,
JAMAIS generalise depuis le premier (`BlightGrenadesPlaybook$$.cctor`). Les douze `ability_id` sont
lus dans le `.ctor` de leur classe (`ComparablePlaybook<T>..ctor(this, <id>, klass)`).

Usage :
    python scripts/python/probe_419r1tr14r5r2r1r1r1r2_static_threshold_gate.py

ASCII only. rc 0 = les deux sources s'accordent avec le tableau ci-dessus.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

HOST = "http://127.0.0.1:8765"
_ROOT = os.path.abspath(os.path.join(_HERE, "..", ".."))

#: `(namespace, classe, ability_id, .cctor attendu, seuil attendu)` -- le namespace est celui que
#: `findClassAnywhere` attend cote Frida (`IdunBattle.AI.Playbook` ou `IdunBattle.AI.Playbook.Loki`).
FAMILY = (
    ("IdunBattle.AI.Playbook",      "BlightGrenadesPlaybook",             1176, True,  1.0),
    ("IdunBattle.AI.Playbook.Loki", "FlailSwingPlaybook",                 1042, True,  1.0),
    ("IdunBattle.AI.Playbook.Loki", "MomentShacklePlaybook",              1184, True,  1.0),
    ("IdunBattle.AI.Playbook.Loki", "PlasmaCannonPlaybook",               1150, True,  1.0),
    ("IdunBattle.AI.Playbook.Loki", "AncestralFortunePlaybook",           1207, False, 0.0),
    ("IdunBattle.AI.Playbook.Loki", "ExcruciatingFrequenciesPlaybook",    1197, False, 0.0),
    ("IdunBattle.AI.Playbook.Loki", "PlagueWindPlaybook",                 1035, False, 0.0),
    ("IdunBattle.AI.Playbook.Loki", "ScytheOfDustPlaybook",               1074, False, 0.0),
    ("IdunBattle.AI.Playbook.Loki", "ScythingTalonsPlaybook",             1065, False, 0.0),
    ("IdunBattle.AI.Playbook.Loki", "SeekerMissileFrequencyLockPlaybook", 1069, False, 0.0),
    ("IdunBattle.AI.Playbook.Loki", "StaffOfStarsPlaybook",               1073, False, 0.0),
    ("IdunBattle.AI.Playbook.Loki", "SuperchargePlaybook",                1103, False, 0.0),
)


# --------------------------------------------------------------------------- transport

def _http(path, payload=None, timeout=120):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(HOST + path, data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _sid():
    return (_http("/api/admin/status").get("session") or {}).get("id")


def rpc(method, body=None, timeout=120):
    r = _http("/api/scripts/%s/rpc" % _sid(),
              {"method": method, "args": [body] if body is not None else [],
               "timeout": timeout * 1000}, timeout=timeout + 60)
    return r.get("result") if isinstance(r, dict) and "result" in r else r


# --------------------------------------------------------------------------- etape 1 : OFFLINE

def _build_hash() -> str:
    p = os.path.join(_ROOT, "data", "symbols", "CURRENT")
    with open(p, encoding="utf-8") as fh:
        return fh.read().strip()


def etape1_methods_tsv() -> dict:
    """Recensement des `.cctor` dans `frida/methods.tsv` -- l'enumeration IL2CPP, pas Ghidra."""
    build = _build_hash()
    path = os.path.join(_ROOT, "data", "symbols", build, "frida", "methods.tsv")
    wanted = {"%s.%s" % (ns, cls) for ns, cls, _, _, _ in FAMILY}
    seen: dict = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("#"):
                continue
            cols = line.rstrip("\n").split("\t")
            if len(cols) < 3:
                continue
            qual, owner = cols[1], cols[2]
            if owner not in wanted:
                continue
            # Le nom de methode est ce qui suit `owner + "."` -- PAS un `rsplit(".", 1)` : le nom
            # qualifie d'un constructeur statique est `<Classe>..cctor` (DEUX points), et le rsplit
            # rendrait `cctor`. Faute deja commise ici : elle faisait diverger cette etape de la
            # mesure live sur les QUATRE classes qui declarent un `.cctor`.
            seen.setdefault(owner, set()).add(qual[len(owner) + 1:])
    print("[etape 1] methods.tsv build=%s" % build)
    bad = 0
    for ns, cls, aid, want_cctor, thr in FAMILY:
        full = "%s.%s" % (ns, cls)
        names = seen.get(full) or set()
        has = ".cctor" in names
        ok_shouldexec = "ShouldExecute" in names
        flag = "OK " if (has == want_cctor and ok_shouldexec) else "BAD"
        if flag == "BAD":
            bad += 1
        print("  %s %-36s id=%-5d cctor=%-5s (attendu %-5s) ShouldExecute=%s"
              % (flag, cls, aid, has, want_cctor, ok_shouldexec))
    return {"bad": bad, "build": build}


# --------------------------------------------------------------------------- etape 2 : LIVE

def etape2_resolve_method_ptr() -> dict:
    """`resolveMethodPtr` REFAIT l'enumeration `class_get_methods` dans le processus.

    TEMOIN obligatoire : `ShouldExecute` doit apparaitre a `depth 0` pour les douze. Sans lui,
    « aucun `.cctor` » ne mesurerait que la panne du RPC (classe introuvable, nom mal orthographie)."""
    targets = []
    for ns, cls, _, _, _ in FAMILY:
        targets.append({"ns": ns, "cls": cls, "method": ".cctor"})
        targets.append({"ns": ns, "cls": cls, "method": "ShouldExecute"})
    res = rpc("resolveMethodPtr", {"targets": targets, "maxDepth": 6}, 90) or {}
    if not res.get("ok"):
        print("[etape 2] RPC KO: %s" % json.dumps(res)[:400])
        return {"bad": len(FAMILY), "measured": False}
    by_key = {}
    for t in (res.get("targets") or []):
        by_key[(t.get("ns"), t.get("cls"), t.get("method"))] = t
    print("[etape 2] resolveMethodPtr (live, il2cppBase=%s)" % res.get("il2cppBase"))
    bad = 0
    for ns, cls, aid, want_cctor, thr in FAMILY:
        tc = by_key.get((ns, cls, ".cctor")) or {}
        ts = by_key.get((ns, cls, "ShouldExecute")) or {}
        if not tc.get("ok") or not ts.get("ok"):
            print("  BAD %-36s classe introuvable: %s" % (cls, tc.get("error") or ts.get("error")))
            bad += 1
            continue
        lv_c = (tc.get("levels") or [{}])[0]
        lv_s = (ts.get("levels") or [{}])[0]
        has_cctor = bool(lv_c.get("methods"))
        has_should = bool(lv_s.get("methods"))
        ok = (has_cctor == want_cctor) and has_should
        if not ok:
            bad += 1
        print("  %s %-36s depth0=%-46s cctor=%-5s (attendu %-5s) ShouldExecute@d0=%s"
              % ("OK " if ok else "BAD", cls, lv_c.get("name"), has_cctor, want_cctor, has_should))
    return {"bad": bad, "measured": True}


# --------------------------------------------------------------------------- etape 3 : le PORT

def etape3_port_matches() -> dict:
    """Le port declare-t-il le meme seuil que ce qui est LU ? (mirror 1:1, aucun scalaire fitte)."""
    from engine.playbook import REGISTRY
    from engine.playbook import static_threshold_gate as G
    bad = 0
    print("[etape 3] engine.playbook.static_threshold_gate")
    for ns, cls, aid, want_cctor, thr in FAMILY:
        pb = REGISTRY.get(aid)
        registered = isinstance(pb, G.StaticUtilityThresholdPlaybook)
        got = getattr(pb, "utility_threshold", None) if registered else None
        expect_reg = aid not in G.NOT_REGISTERED
        ok = (registered == expect_reg) and (not registered or got == thr)
        if not ok:
            bad += 1
        print("  %s id=%-5d %-36s registre=%-5s (attendu %-5s) seuil=%s (attendu %s)"
              % ("OK " if ok else "BAD", aid, cls, registered, expect_reg, got, thr))
    return {"bad": bad}


def main() -> int:
    r1 = etape1_methods_tsv()
    print("")
    r2 = etape2_resolve_method_ptr()
    print("")
    r3 = etape3_port_matches()
    total = r1["bad"] + r2["bad"] + r3["bad"]
    print("")
    print("VERDICT: %s (etape1=%d BAD, etape2=%d BAD, etape3=%d BAD)"
          % ("PASS" if total == 0 else "FAIL", r1["bad"], r2["bad"], r3["bad"]))
    return 0 if total == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
