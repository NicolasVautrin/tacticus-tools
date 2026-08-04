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

import argparse
import contextlib
import json
import os
import subprocess
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

# ============================================================================ volet LIVE
#
# LE DISCRIMINANT, ENONCE AVANT LA MESURE
# ---------------------------------------
# Le gate recoit `attackHealUtility = CalculateCustomUtility + CalculateUtilityFromPredictions`.
# Sur une cible a PV PLEINS et sans bouclier, l'utilite de degat vaut, au decompile porte
# (`engine/utilities/damage.py::DamageUtility.evaluate`, poids `W_DAMAGE = 80` + `W_REMAINING = 20`) :
#
#     u = 80 * (dmg / (maxHP + 2)) + 20 * (1 - (maxHP + 2 - dmg) / (maxHP + 2))
#       = 100 * dmg / (maxHP + 2)                                     [aucun kill : PV >> degat]
#
# `u` est donc PILOTABLE par les PV de la cible, a degat constant : `u x (maxHP + 2) = 100 x dmg`
# est INVARIANT. Deux bras, un seul axe (les PV) :
#
#   * bras `lo` : PV enormes -> `0 < u < 1`. Le seuil 1 REFUSE, le seuil 0 ACCEPTE.
#   * bras `hi` : PV CALIBRES depuis `u` mesure en `lo` pour viser `u ~ 2`. Les DEUX acceptent.
#
# Ce n'est donc pas un regime degenere : les deux modeles (`> 0` et `> 1`) rendent des verdicts
# OPPOSES dans le bras `lo`, et le meme dans `hi`. L'encadrement obtenu borne le seuil dans
# `(u_lo, u_hi)`, ce qui est bien plus fort que « le seuil est grand ».
#
# NEUTRALISER L'ATTAQUE NORMALE -- sans quoi le bras `lo` aurait DEUX causes indistinguables
# ------------------------------------------------------------------------------------------
# `aiDryRunAllUnits` rend l'action GAGNANTE. Or dans le bras `lo` toutes les utilites tendent vers
# 0 tandis que l'attaque normale garde son `CalculateCustomUtility = Fix64(1)` : elle raflerait
# l'argmax que le gate morde ou non. Le montage la prive donc de tout plan, par la GEOMETRIE :
#
#     distance(caster, cible)  >  Movement + portee de l'arme la plus longue
#     distance(caster, cible) <=  range de l'ability
#
# `Movement` est ramene a 1 par `--unit-stat` (il faut pouvoir approcher), et l'approche s'arrete a
# la distance VOULUE, pas « a portee ». Les deux casters :
#
#   | caster           | ability                       | seuil | armes      | range | distance |
#   |------------------|-------------------------------|-------|------------|-------|----------|
#   | darkaTerminator  | 1150 PlasmaCannon             |   1   | melee (1)  |   3   |    3     |
#   | tauMarksman      | 1069 SeekerMissileFrequencyLock|   0  | melee/R3   |   5   |    5     |
#
# `tauMarksman` est le TEMOIN : meme bras, meme cible, memes PV, seuil 0 -> il doit rester propose
# dans les DEUX bras. Sans lui, « plus rien n'est propose en `lo` » se lirait aussi bien comme un
# effet d'argmax que comme un gate qui mord.

FOE = "adeptRetributor"
BOARD = "MC1_67"
SEED = "4242"
MOVEMENT = 1

#: `(visualId, ability, seuil LU, distance cible a la cible)`
LIVE_CASTERS = (
    ("darkaTerminator", 1150, 1.0, 3),
    ("tauMarksman",     1069, 0.0, 5),
)

#: PV du bras `lo`. Choisi tres au-dessus de `100 x degat` pour garantir `u < 1` quel que soit le
#: rang de normalisation ; la valeur EXACTE de `u` est ensuite MESUREE, pas supposee.
HP_LO = 4_000_000

#: Cible d'utilite du bras `hi`, atteinte par calibrage depuis `u` mesure en `lo`.
U_HI_TARGET = 2.0

MAX_APPROACH_TURNS = 16


class MontageError(RuntimeError):
    """Le montage n'est pas installe -- un bras qui ne mesure pas ce qu'il annonce."""


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


# --------------------------------------------------------------------------- etape 4 : LIVE

def _duel(*args) -> tuple:
    p = subprocess.run([sys.executable, "rl_duel.py", *args], cwd=_HERE, capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def _build(state_file: str, argv_tail: list) -> int:
    argv = [sys.executable, "rl_duel.py", "build", "--state-file", state_file, *argv_tail]
    p = subprocess.run(argv, cwd=_HERE, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise MontageError("rl_duel build a echoue (rc=%s) : %s"
                           % (p.returncode, (p.stderr or p.stdout or "")[-800:]))
    with open(state_file, encoding="utf-8") as fh:
        return int(json.load(fh)["runnerId"])


def _dispose(rid) -> None:
    try:
        rpc("disposeRunner", {"runnerId": rid}, 60)
    except Exception:
        pass


def _pos(u):
    p = u.get("pos") or {}
    return None if p.get("col") is None else (p["col"], p["row"])


def _end_turn(sf: str, rid: int) -> None:
    """Termine NOTRE tour, puis attend qu'il nous revienne.

    ⚠ L'ordre est ce qui compte, et l'avoir inverse a coute une mesure : tester
    `currentPlayer == 3` AVANT de finir le tour fait sortir immediatement (c'est deja notre tour),
    donc le tour n'est JAMAIS termine -- les unites qui ont bouge restent sans action et l'approche
    se bloque au deuxieme pas, avec le symptome trompeur « AUCUNE tuile movable »."""
    _duel("act", "endturn", "--state-file", sf, "--no-ai")
    for _ in range(4):
        if rpc("battleStatus", {"runnerId": rid}, 40).get("currentPlayer") == 3:
            return
        _duel("act", "endturn", "--state-file", sf, "--no-ai")


def _movement_reach(mbu: dict, uid: int, here) -> int:
    """Portee de deplacement EFFECTIVE, mesuree sur les tuiles rendues -- le garde qui verifie que
    la mutation `--unit-stat <X>:Movement=1` a MORDU. Une mutation qui ne prend pas laisse le
    montage passer par chance de geometrie, et c'est le vert le plus dangereux."""
    import hexgeo
    tiles = [(t.get("col"), t.get("row")) for t in ((mbu.get(uid) or {}).get("tiles") or ())]
    tiles = [t for t in tiles if t[0] is not None]
    return max((hexgeo.distance(t, here) for t in tiles), default=0)


def _approach(sf: str, rid: int, casters: dict, foe_id: int) -> dict:
    """Amene chaque caster a SA distance cible de l'unique cible, un hex par tour (`Movement = 1`).

    On vise une DISTANCE, pas « a portee » : c'est elle qui prive l'attaque normale de tout plan
    tout en laissant l'ability porter. `--no-ai` : l'adversaire ne bouge jamais, la geometrie est
    PILOTEE, pas subie. Un TOUR BLANC clot l'approche, sinon les unites qui viennent de bouger
    n'ont plus d'action et `aiDryRunAllUnits` rend `FinishUnitTurnMessage`.

    ⚠ Le PREMIER tour est le DEPLOIEMENT : `decisionView` y publie des positions de pre-placement,
    et la premiere « distance » lue n'est pas une distance de board (mesure : 11 pour une unite qui
    se retrouve a 3 apres UN hex). On solde donc un tour a vide avant de mesurer quoi que ce soit."""
    import hexgeo
    want = {vis: d for vis, _ab, _t, d in LIVE_CASTERS}
    _end_turn(sf, rid)                      # solde le DEPLOIEMENT avant toute lecture de distance
    reach = {}
    for _turn in range(MAX_APPROACH_TURNS):
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 300)
        by_id = {u.get("id"): u for u in (dv.get("units") or ())}
        fp = _pos(by_id.get(foe_id) or {})
        cur = {vis: hexgeo.distance(_pos(by_id[uid]), fp) for vis, uid in casters.items()}
        if all(cur[v] == want[v] for v in casters):
            break
        mov = rpc("aiMovableTiles", {"runnerId": rid}, 90)
        mbu = {m.get("unitId"): m for m in (mov.get("units") or ())}
        moved = False
        for vis, uid in casters.items():
            here = _pos(by_id[uid])
            r = _movement_reach(mbu, uid, here)
            if r:
                reach[vis] = max(reach.get(vis, 0), r)
            if cur[vis] == want[vis]:
                continue
            tiles = [(t.get("col"), t.get("row")) for t in ((mbu.get(uid) or {}).get("tiles") or ())]
            tiles = [t for t in tiles if t[0] is not None]
            if not tiles:
                continue
            best = min(tiles, key=lambda t: abs(hexgeo.distance(t, fp) - want[vis]))
            if abs(hexgeo.distance(best, fp) - want[vis]) >= abs(cur[vis] - want[vis]):
                continue                      # aucun progres depuis cette tuile -- ne pas gacher le tour
            rc, _o = _duel("act", "move", "--state-file", sf, "--unit", str(uid),
                           "--to", "%d,%d" % best)
            moved = moved or rc == 0
        if not moved:
            break
        _end_turn(sf, rid)
    _end_turn(sf, rid)                                           # TOUR BLANC
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 300)
    by_id = {u.get("id"): u for u in (dv.get("units") or ())}
    fp = _pos(by_id.get(foe_id) or {})
    return ({vis: hexgeo.distance(_pos(by_id[uid]), fp) for vis, uid in casters.items()}, reach)


def _normal_has_plan(dv, uid: int) -> bool:
    """L'attaque normale de `uid` a-t-elle UN plan (n'importe quelle tuile) ? Doit etre FAUX dans
    le montage : c'est la condition qui empeche l'argmax de masquer le gate."""
    nids = set()
    for u in (dv.get("units") or ()):
        if u.get("id") == uid:
            nids = {a["id"] for a in (u.get("abilities") or ())
                    if a.get("kind") == "normal" and a.get("id") is not None}
    for pl in (dv.get("attackPlans") or ()):
        if pl.get("unitId") != uid:
            continue
        for ev in (pl.get("evals") or ()):
            if ev.get("abilityId") in nids and ev.get("rankCount"):
                return True
    return False


def _ability_castable_here(dv, uid: int, ability: int) -> bool:
    """L'ability est-elle castable DEPUIS la tuile courante ? (sa tuile figure dans les `ranked` de
    son eval). C'est le second garde de montage : sans lui, « le natif ne propose pas » se lirait
    aussi bien comme « le gate mord » que comme « l'ability ne porte pas d'ici »."""
    here = None
    for u in (dv.get("units") or ()):
        if u.get("id") == uid:
            here = _pos(u)
    for pl in (dv.get("attackPlans") or ()):
        if pl.get("unitId") != uid:
            continue
        for ev in (pl.get("evals") or ()):
            if ev.get("abilityId") != ability:
                continue
            if any((rk.get("col"), rk.get("row")) == here for rk in (ev.get("ranked") or ())):
                return True
    return False


def _settle(sf: str, rid: int, casters: dict, max_steps: int = 2) -> None:
    """Laisse le natif se POSER sur la tuile qu'il prefere, DANS LE MEME TOUR, avant de lire son
    verdict d'ability.

    `CalculateNextActionForUnit` rend UNE action a la fois : quand le maximum de `u_action` est sur
    une AUTRE tuile que l'origine, il emet d'abord un `MoveUnitMessage` -- et l'ability, meme
    parfaitement proposable, n'apparait qu'au pas SUIVANT. Mesure : `darkaTerminator` a `u = 2.0`,
    ability `rankCount = 4` dont sa propre tuile, rendait `MoveUnitMessage vers (4,7)`.

    ⚠ AUCUN `endturn` ici, et c'est le point : un deplacement ne consomme PAS l'action d'attaque du
    tour. Solder le tour entre deux pas (ce que faisait la premiere version) rend au caster un
    mouvement neuf a chaque fois -- mesure : les deux casters finissaient a portee de leur ATTAQUE
    NORMALE (`normalPlan` passe de faux a vrai), ce qui detruisait precisement la neutralisation que
    le montage cherche. Sans `endturn`, le mouvement est consomme des le premier pas : le sweep de
    tuiles se reduit a l'origine et la normale ne peut plus revenir."""
    for _ in range(max_steps):
        dry = rpc("aiDryRunAllUnits", {"runnerId": rid}, 300)
        by_uid = {u.get("unitId"): (u.get("proposed") or ()) for u in (dry.get("units") or ())}
        moved = False
        for _vis, uid in casters.items():
            msgs = by_uid.get(uid) or ()
            mv = next((m for m in msgs if m.get("cls") == "MoveUnitMessage"), None)
            to = (mv or {}).get("to") or {}
            if to.get("col") is None:
                continue
            rc, _o = _duel("act", "move", "--state-file", sf, "--unit", str(uid),
                           "--to", "%d,%d" % (to["col"], to["row"]))
            moved = moved or rc == 0
        if not moved:
            return


def _stage(logs: str, tag: str, hp: int) -> dict:
    sf = os.path.join(logs, "tr14r5r2r1r1r1r2_%s.json" % tag)
    extra = ["--seed", SEED, "--board", BOARD, "--no-ai",
             "--p-units", ",".join(v for v, _a, _t, _d in LIVE_CASTERS),
             "--a-units", FOE,
             "--unit-stat", ";".join("%s:Movement=%d" % (v, MOVEMENT)
                                     for v, _a, _t, _d in LIVE_CASTERS),
             "--unit-stat", "%s:Health=%d,RemainingHealth=%d" % (FOE, hp, hp)]
    rid = _build(sf, extra)
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 300)
    ids, foe_id = {}, None
    for u in (dv.get("units") or ()):
        if u.get("visualId") == FOE:
            foe_id = u.get("id")
        else:
            ids[u.get("visualId")] = u.get("id")
    missing = [v for v, _a, _t, _d in LIVE_CASTERS if ids.get(v) is None]
    if missing or foe_id is None:
        _dispose(rid)
        raise MontageError("montage NON INSTALLE (%s) : casters absents=%s, cible=%s"
                           % (tag, missing, foe_id))
    dist, reach = _approach(sf, rid, ids, foe_id)
    _settle(sf, rid, ids)
    return {"tag": tag, "rid": rid, "sf": sf, "hp": hp, "ids": ids, "foe": foe_id,
            "dist": dist, "reach": reach}


def _ctx(case: dict, uid: int):
    from engine import weights as W
    from engine.ai import context as _ai_ctx
    from engine.playbook import scene as _scene
    dv = rpc("decisionView", {"runnerId": case["rid"], "allAbilities": True, "maxRank": 32}, 300)
    mov = rpc("aiMovableTiles", {"runnerId": case["rid"]}, 90)
    mbu = {u.get("unitId"): u for u in (mov.get("units") or [])}
    return dv, _ai_ctx.build(rpc, case["rid"], dv, mbu, uid, W.load(),
                             _scene.build_predictor(rpc, case["rid"]))


def _port_u(ctx, ability: int, target: int):
    """`(u_pred, action_existe)` -- `u_pred` est l'ARGUMENT EXACT du gate natif
    (`CalculateCustomUtility + CalculateUtilityFromPredictions`), lu AVANT lui ; `action_existe`
    est ce que `calculate_action_utility` rend apres lui (`None` = le `Nullable` VIDE natif)."""
    from engine.playbook import get_playbook_or_default
    pb = get_playbook_or_default(ability)
    evs = pb.make_damage_predictions(ctx, ctx.origin, target, ability)
    if not evs:
        return None, False
    u, _bk = pb.calculate_utility_from_predictions(ctx, ctx.origin, target, ability, evs)
    u += pb.calculate_custom_utility(ctx, ctx.origin, target, ability)
    return u, pb.calculate_action_utility(ctx, ctx.origin, target, ability) is not None


def _native_proposes(case: dict) -> dict:
    dry = rpc("aiDryRunAllUnits", {"runnerId": case["rid"]}, 300)
    by_uid = {}
    for u in (dry.get("units") or ()):
        by_uid[u.get("unitId")] = [(m.get("cls"), m.get("abilityType")) for m in (u.get("proposed") or ())]
    out = {}
    for vis, ab, _t, _d in LIVE_CASTERS:
        msgs = by_uid.get(case["ids"][vis]) or []
        out[vis] = (any(c == "ActiveAbilityMessage" and a == ab for c, a in msgs), msgs)
    return out


@contextlib.contextmanager
def gate_cut():
    """COUPE le gate porte -- `should_execute` rend `True` quoi qu'il arrive, c.-a-d. STRICTEMENT
    le port d'avant cette tranche. On mute la METHODE, jamais le code livre."""
    from engine.playbook.base import ComparablePlaybook
    from engine.playbook import static_threshold_gate as G
    saved = G.StaticUtilityThresholdPlaybook.should_execute
    G.StaticUtilityThresholdPlaybook.should_execute = ComparablePlaybook.should_execute
    try:
        yield
    finally:
        G.StaticUtilityThresholdPlaybook.should_execute = saved


def _measure(case: dict) -> list:
    import hexgeo
    nat = _native_proposes(case)
    rows = []
    for vis, ab, thr, want_d in LIVE_CASTERS:
        dv, ctx = _ctx(case, case["ids"][vis])
        by_id = {u.get("id"): u for u in (dv.get("units") or ())}
        # DISTANCE re-mesuree ICI, pas celle de la fin de l'approche : `_settle` a pu deplacer le
        # caster d'un hex de plus, et c'est la geometrie AU MOMENT DE LA LECTURE qui compte.
        case["dist"][vis] = hexgeo.distance(_pos(by_id[case["ids"][vis]]),
                                            _pos(by_id.get(case["foe"]) or {}))
        u, port = _port_u(ctx, ab, case["foe"])
        with gate_cut():
            _u2, cut = _port_u(ctx, ab, case["foe"])
        rows.append({
            "arm": case["tag"], "caster": vis, "ability": ab, "threshold": thr,
            "hp": case["hp"], "dist": case["dist"].get(vis), "want_dist": want_d,
            "reach": case["reach"].get(vis),
            "normal_plan": _normal_has_plan(dv, case["ids"][vis]),
            "castable_here": _ability_castable_here(dv, case["ids"][vis], ab),
            "u": u, "native": nat[vis][0], "port": port, "port_gate_cut": cut,
            "msgs": nat[vis][1],
        })
    return rows


def etape4_live(logs: str, verbose: bool = True) -> dict:
    """Les deux bras, le calibrage du second depuis le premier, et les trois criteres."""
    bad, rows = 0, []
    case = _stage(logs, "lo", HP_LO)
    try:
        rows += _measure(case)
    finally:
        _dispose(case["rid"])
    # CALIBRAGE : `u x (maxHP + 2)` est invariant a degat constant. On vise `U_HI_TARGET` sur le
    # caster GATE-E (seuil 1) ; le temoin (seuil 0) n'a besoin que de `u > 0`, vrai des deux cotes.
    ref = next((r for r in rows if r["threshold"] == 1.0), None)
    if not ref or not ref["u"] or ref["u"] <= 0:
        print("[etape 4] CALIBRAGE IMPOSSIBLE : u=%s dans le bras lo" % (ref or {}).get("u"))
        return {"bad": 1, "rows": rows}
    hp_hi = max(1, int(round((HP_LO + 2) * ref["u"] / U_HI_TARGET)) - 2)
    case = _stage(logs, "hi", hp_hi)
    try:
        rows += _measure(case)
    finally:
        _dispose(case["rid"])

    if verbose:
        print("[etape 4] live -- board %s seed %s, Movement=%d, cible %s" % (BOARD, SEED, MOVEMENT, FOE))
        for r in rows:
            print("  [%-2s] %-16s ab=%-5d seuil=%.1f hp=%-9d dist=%-2s reach=%-2s normalPlan=%-5s "
                  "castHere=%-5s u=%-10s natif=%-5s port=%-5s"
                  % (r["arm"], r["caster"], r["ability"], r["threshold"], r["hp"], r["dist"],
                     r["reach"], r["normal_plan"], r["castable_here"],
                     "None" if r["u"] is None else round(r["u"], 4), r["native"], r["port"]))
        print("  -- contre-epreuve gate-coupe (= le port d'avant cette tranche) --")
        for r in rows:
            print("     [%-2s] %-16s -> port=%-5s %s"
                  % (r["arm"], r["caster"], r["port_gate_cut"],
                     "MORD" if r["port_gate_cut"] != r["port"] else "inerte"))

    for r in rows:
        # MONTAGE, TROIS conditions -- sans elles la ligne ne mesure pas ce qu'elle annonce :
        #   `reach == MOVEMENT`     la mutation `--unit-stat <X>:Movement=1` a MORDU (un vert
        #                           obtenu sur une mutation qui ne prend pas est le plus dangereux) ;
        #   `not normal_plan`       l'attaque normale n'a AUCUN plan, donc son custom `Fix64(1)`
        #                           ne peut pas rafler l'argmax et masquer le gate ;
        #   `castable_here`         l'ability, elle, EST castable depuis la tuile courante -- sinon
        #                           « le natif ne propose pas » ne dirait rien du gate.
        if r["reach"] != MOVEMENT or r["normal_plan"] or not r["castable_here"]:
            print("  BAD MONTAGE [%s] %s : reach=%s (voulu %d) normalPlan=%s castHere=%s dist=%s"
                  % (r["arm"], r["caster"], r["reach"], MOVEMENT, r["normal_plan"],
                     r["castable_here"], r["dist"]))
            bad += 1
            continue
        # CRITERE A (necessite, symetrique) : le port ne refuse JAMAIS ce que le natif CHOISIT.
        if r["native"] and not r["port"]:
            print("  VIOLE A [%s] %s : natif PROPOSE, port REFUSE" % (r["arm"], r["caster"]))
            bad += 1
        # CRITERE B : dans le bras `lo`, le seuil 1 doit etre REFUSE par le natif et le seuil 0
        # ACCEPTE -- c'est le discriminant qui separe les deux seuils.
        if r["arm"] == "lo":
            if r["u"] is None or not (0.0 < r["u"] < 1.0):
                print("  BAD REGIME [lo] %s : u=%s hors (0,1)" % (r["caster"], r["u"]))
                bad += 1
            elif r["native"] == (r["threshold"] == 1.0):
                print("  VIOLE B [lo] %s : natif=%s pour seuil %.1f"
                      % (r["caster"], r["native"], r["threshold"]))
                bad += 1
        # CRITERE C : dans le bras `hi`, les DEUX seuils acceptent -- le temoin temporel du MEME
        # caster, qui exclut « cette ability n'est jamais proposee ».
        if r["arm"] == "hi":
            if r["u"] is None or r["u"] <= 1.0:
                print("  BAD REGIME [hi] %s : u=%s <= 1" % (r["caster"], r["u"]))
                bad += 1
            elif not r["native"]:
                print("  VIOLE C [hi] %s : natif REFUSE alors que u=%.4f > 1"
                      % (r["caster"], r["u"]))
                bad += 1
        # CRITERE D : la contre-epreuve doit MORDRE exactement la ou le gate refuse, et seulement la.
        if (r["port_gate_cut"] != r["port"]) != (not r["port"]):
            print("  VIOLE D [%s] %s : gate_cut=%s port=%s" % (r["arm"], r["caster"],
                                                               r["port_gate_cut"], r["port"]))
            bad += 1
    return {"bad": bad, "rows": rows}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="joue aussi l'etape 4 (monte deux runners)")
    ap.add_argument("--state-file", default=None, help="prefixe ABSOLU des state-files (avec --live)")
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args()

    r1 = etape1_methods_tsv()
    print("")
    r2 = etape2_resolve_method_ptr()
    print("")
    r3 = etape3_port_matches()
    r4 = {"bad": 0, "rows": []}
    if args.live:
        if not args.state_file:
            print("--live exige --state-file (chemin ABSOLU)")
            return 2
        logs = os.path.dirname(os.path.abspath(args.state_file))
        os.makedirs(logs, exist_ok=True)
        print("")
        r4 = etape4_live(logs)
    total = r1["bad"] + r2["bad"] + r3["bad"] + r4["bad"]
    print("")
    print("VERDICT: %s (etape1=%d BAD, etape2=%d BAD, etape3=%d BAD, etape4=%d BAD)"
          % ("PASS" if total == 0 else "FAIL", r1["bad"], r2["bad"], r3["bad"], r4["bad"]))
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump({"etape1": r1, "etape2": r2, "etape3": r3, "etape4": r4}, fh, indent=1)
    return 0 if total == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
