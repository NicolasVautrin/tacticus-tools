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

## Le tableau attendu, ENONCE AVANT LA MESURE

Ce que le recensement des `.cctor` mesure, c'est la PRESENCE d'un second ecrivain, PAS le seuil : le
champ a un ecrivain de PLUS, `ComparablePlaybook<T>$$.cctor`, qui y met `Fix64(10)` et qui ecrit en
DERNIER (cf. `engine/playbook/static_threshold_gate.py` et le probe `..._r4_ecart_permissif`). Le
seuil effectif vaut donc **10 pour les douze** -- mesure sur `1150` (avec `.cctor` derive) et sur
`1069` (sans). Les `.cctor` derives restent gardes ici parce que leur presence est le fait qui
explique la lecture erronee « 1 vs 0 » de la tranche precedente.

| classe (`IdunBattle.AI.Playbook[.Loki]`)   | ability            | `.cctor` derive | seuil effectif |
|--------------------------------------------|--------------------|-----------------|----------------|
| `BlightGrenadesPlaybook`                    | 1176 BlightGrenades| OUI (`Fix64(1)`)| `Fix64(10)`    |
| `Loki.FlailSwingPlaybook`                   | 1042 FlailSwing    | OUI (`Fix64(1)`)| `Fix64(10)`    |
| `Loki.MomentShacklePlaybook`                | 1184 MomentShackle | OUI (`Fix64(1)`)| `Fix64(10)`    |
| `Loki.PlasmaCannonPlaybook`                 | 1150 PlasmaCannon  | OUI (`Fix64(1)`)| `Fix64(10)`    |
| `Loki.AncestralFortunePlaybook`             | 1207               | non             | `Fix64(10)`    |
| `Loki.ExcruciatingFrequenciesPlaybook`      | 1197               | non             | `Fix64(10)`    |
| `Loki.PlagueWindPlaybook`                   | 1035               | non             | `Fix64(10)`    |
| `Loki.ScytheOfDustPlaybook`                 | 1074               | non             | `Fix64(10)`    |
| `Loki.ScythingTalonsPlaybook`               | 1065               | non             | `Fix64(10)`    |
| `Loki.SeekerMissileFrequencyLockPlaybook`   | 1069               | non             | `Fix64(10)`    |
| `Loki.StaffOfStarsPlaybook`                 | 1073               | non             | `Fix64(10)`    |
| `Loki.SuperchargePlaybook`                  | 1103               | non             | `Fix64(10)`    |

Les douze `ability_id` sont lus dans le `.ctor` de leur classe
(`ComparablePlaybook<T>..ctor(this, <id>, klass)`).

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
    ("IdunBattle.AI.Playbook",      "BlightGrenadesPlaybook",             1176, True,  10.0),
    ("IdunBattle.AI.Playbook.Loki", "FlailSwingPlaybook",                 1042, True,  10.0),
    ("IdunBattle.AI.Playbook.Loki", "MomentShacklePlaybook",              1184, True,  10.0),
    ("IdunBattle.AI.Playbook.Loki", "PlasmaCannonPlaybook",               1150, True,  10.0),
    ("IdunBattle.AI.Playbook.Loki", "AncestralFortunePlaybook",           1207, False, 10.0),
    ("IdunBattle.AI.Playbook.Loki", "ExcruciatingFrequenciesPlaybook",    1197, False, 10.0),
    ("IdunBattle.AI.Playbook.Loki", "PlagueWindPlaybook",                 1035, False, 10.0),
    ("IdunBattle.AI.Playbook.Loki", "ScytheOfDustPlaybook",               1074, False, 10.0),
    ("IdunBattle.AI.Playbook.Loki", "ScythingTalonsPlaybook",             1065, False, 10.0),
    ("IdunBattle.AI.Playbook.Loki", "SeekerMissileFrequencyLockPlaybook", 1069, False, 10.0),
    ("IdunBattle.AI.Playbook.Loki", "StaffOfStarsPlaybook",               1073, False, 10.0),
    ("IdunBattle.AI.Playbook.Loki", "SuperchargePlaybook",                1103, False, 10.0),
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
# est INVARIANT. Trois bras, un seul axe (les PV), les deux derniers CALIBRES depuis le `u` mesure
# au premier :
#
#   * bras `lo`  : PV enormes -> `0 < u < 1`   -> SOUS le seuil (10) : natif ET port refusent ;
#   * bras `mid` : `u ~ 5`                     -> SOUS le seuil      : natif ET port refusent ;
#   * bras `hi`  : `u ~ 20`                    -> AU-DESSUS          : natif ET port acceptent.
#
# Le bras `mid` est celui qui a NOMME l'erreur de seuil : avec le seuil `Fix64(1)` de la tranche
# precedente, le port y acceptait quand le natif refusait. L'ENCADREMENT SERRE du seuil (a 3e-5) et
# le TEMOIN a seuil declare OPPOSE vivent dans le probe `..._r4_ecart_permissif`.
#
# DEUX CONCURRENTS A NEUTRALISER -- sans quoi le bras `lo` aurait des causes indistinguables
# ------------------------------------------------------------------------------------------
# `aiDryRunAllUnits` rend l'action GAGNANTE. Or dans le bras `lo` toutes les utilites d'attaque
# tendent vers 0, et DEUX autres generateurs raflent alors l'argmax que le gate morde ou non :
#
#   1. **l'ATTAQUE NORMALE**, qui garde son `CalculateCustomUtility = Fix64(1)` ;
#   2. **le MOUVEMENT** -- et c'est le piege le moins evident : un deplacement CONSOMME
#      l'activation (mesure : apres un `MoveUnitMessage` applique, `aiDryRunAllUnits` rend
#      `FinishUnitTurnMessage`), donc « bouger » et « caster » s'EXCLUENT. Un caster a `u ~ 0.07`
#      preferera toujours se rapprocher.
#
# Les deux tombent avec le meme levier, `--unit-stat <X>:Movement=0` :
#
#   * le generateur de MOUVEMENT n'a plus aucune tuile -> il ne concurrence plus rien ;
#   * le sweep de tuiles du generateur d'ACTION se reduit a l'origine, donc l'attaque normale n'a
#     de plan QUE si la cible est deja a portee d'arme -- une condition purement geometrique.
#
# Et le placement reste libre parce que **le DEPLOIEMENT ignore `Movement`** (mesure : 55 tuiles,
# portee 10, sur une unite a `Movement = 0`). Il suffit donc de :
#
#     portee de l'arme la plus longue  <  distance(caster, cible)  <=  range de l'ability
#
#   | caster           | ability            | seuil effectif | armes     | range | distance |
#   |------------------|--------------------|----------------|-----------|-------|----------|
#   | darkaTerminator  | 1150 PlasmaCannon  |       10       | melee (1) |   3   |    3     |

FOE = "adeptRetributor"
BOARD = "MC1_67"
SEED = "4242"
MOVEMENT = 0

#: `(visualId, ability, seuil LU, distance cible a la cible)`
#:
#: UN SEUL caster, et c'est une CONTRAINTE MESUREE, pas un choix : le placement libre du premier
#: tour vient du trait **Teleport**, pas d'une phase de deploiement. Mesure, meme spawn `(1,0)` et
#: meme `Movement=0` : `darkaTerminator` (Terminator, donc Teleport) rend **58** tuiles atteignables
#: (distances 2 a 11), `tauMarksman` en rend **0**. Un caster sans Teleport reste donc a son spawn,
#: hors de portee de son ability -- il n'est pas montable a `Movement=0`, et avec un `Movement`
#: suffisant pour approcher il choisirait de BOUGER (cf. plus bas). D'ou le temoin par REGIME
#: (trois bras sur le meme caster) plutot que par ability.
LIVE_CASTERS = (
    ("darkaTerminator", 1150, 10.0, 3),
)

#: PV du bras `lo`. Choisi tres au-dessus de `100 x degat` pour garantir `u < 1` quel que soit le
#: rang de normalisation ; la valeur EXACTE de `u` est ensuite MESUREE, pas supposee.
HP_LO = 4_000_000

#: Utilites visees par les deux autres bras, atteintes par calibrage depuis `u` mesure en `lo`
#: (`u x (maxHP + 2)` invariant). `mid` est AU-DESSUS du seuil porte et EN DESSOUS du point ou le
#: natif bascule ; `hi` est au-dessus des deux.
U_MID_TARGET = 5.0
U_HI_TARGET = 20.0



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


def _deploy(sf: str, rid: int, casters: dict, foe_id: int) -> tuple:
    """Place chaque caster a SA distance cible, PENDANT LE DEPLOIEMENT, puis solde le tour.

    Deux faits mesures fondent ce montage, et ils sont contre-intuitifs tous les deux :

    * **le DEPLOIEMENT ignore `Movement`** -- `aiMovableTiles` rend au premier tour, pour l'unite en
      cours de placement, TOUTE la zone de deploiement (mesure : 55 tuiles, portee 10, sur une unite
      a `Movement = 0`). C'est ce qui permet de choisir la geometrie exactement, sans approche ;
    * **une fois deployee a `Movement = 0`, l'unite est FIGEE** -- le generateur de MOUVEMENT n'a
      plus aucune tuile, donc il ne peut plus concurrencer le generateur d'ACTION.

    Ce second point est ce qui rend le bras `lo` observable. Un deplacement CONSOMME l'activation
    (mesure : apres un `MoveUnitMessage` applique, `aiDryRunAllUnits` rend `FinishUnitTurnMessage`),
    et dans un regime ou toutes les utilites d'attaque tendent vers 0, le MOVE gagne l'argmax
    quoi qu'il arrive -- l'ability n'apparaitrait jamais, gate ou pas. `Movement = 0` supprime
    l'alternative : il ne reste que « caster » ou « finir son tour ».

    Le placement est SEQUENTIEL (une seule unite a la main a la fois), d'ou la boucle."""
    import hexgeo
    want = {vis: d for vis, _ab, _t, d in LIVE_CASTERS}
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 300)
    fp = _pos({u.get("id"): u for u in (dv.get("units") or ())}.get(foe_id) or {})
    reach, placed = {}, set()
    for _ in range(len(casters) * 3 + 2):
        mov = rpc("aiMovableTiles", {"runnerId": rid}, 90)
        mbu = {m.get("unitId"): m for m in (mov.get("units") or ())}
        did = False
        for vis, uid in casters.items():
            if vis in placed:
                continue
            tiles = [(t.get("col"), t.get("row")) for t in ((mbu.get(uid) or {}).get("tiles") or ())]
            tiles = [t for t in tiles if t[0] is not None]
            if not tiles:
                continue
            reach[vis] = max(reach.get(vis, 0), max(hexgeo.distance(t, fp) for t in tiles))
            best = min(tiles, key=lambda t: abs(hexgeo.distance(t, fp) - want[vis]))
            rc, _o = _duel("act", "move", "--state-file", sf, "--unit", str(uid),
                           "--to", "%d,%d" % best)
            if rc == 0:
                placed.add(vis)
                did = True
                break                              # placement SEQUENTIEL : une unite a la fois
        if not did:
            break
    _end_turn(sf, rid)                             # solde le deploiement -> actions intactes
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 300)
    by_id = {u.get("id"): u for u in (dv.get("units") or ())}
    fp = _pos(by_id.get(foe_id) or {})
    mov = rpc("aiMovableTiles", {"runnerId": rid}, 90)
    mbu = {m.get("unitId"): m for m in (mov.get("units") or ())}
    # `frozen` = le garde de la mutation `Movement=0` : APRES deploiement, plus AUCUNE tuile.
    frozen = {vis: _movement_reach(mbu, uid, _pos(by_id[uid])) == 0 for vis, uid in casters.items()}
    return ({vis: hexgeo.distance(_pos(by_id[uid]), fp) for vis, uid in casters.items()},
            reach, frozen)


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
    dist, reach, frozen = _deploy(sf, rid, ids, foe_id)
    return {"tag": tag, "rid": rid, "sf": sf, "hp": hp, "ids": ids, "foe": foe_id,
            "dist": dist, "reach": reach, "frozen": frozen}


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
            "reach": case["reach"].get(vis), "frozen": case["frozen"].get(vis),
            "normal_plan": _normal_has_plan(dv, case["ids"][vis]),
            "castable_here": _ability_castable_here(dv, case["ids"][vis], ab),
            "u": u, "native": nat[vis][0], "port": port, "port_gate_cut": cut,
            "msgs": nat[vis][1],
        })
    return rows


def etape4_live(logs: str, verbose: bool = True) -> dict:
    """Les trois bras (le meme caster, trois regimes d'utilite), et les quatre criteres."""
    bad, rows = 0, []
    case = _stage(logs, "lo", HP_LO)
    try:
        rows += _measure(case)
    finally:
        _dispose(case["rid"])
    # CALIBRAGE : `u x (maxHP + 2)` est invariant a degat constant -> les deux autres bras se
    # derivent du `u` MESURE en `lo`, sans supposer le degat.
    ref = rows[0] if rows else None
    if not ref or not ref["u"] or ref["u"] <= 0:
        print("[etape 4] CALIBRAGE IMPOSSIBLE : u=%s dans le bras lo" % (ref or {}).get("u"))
        return {"bad": 1, "rows": rows}
    for tag, target in (("mid", U_MID_TARGET), ("hi", U_HI_TARGET)):
        hp = max(1, int(round((HP_LO + 2) * ref["u"] / target)) - 2)
        case = _stage(logs, tag, hp)
        try:
            rows += _measure(case)
        finally:
            _dispose(case["rid"])

    if verbose:
        print("[etape 4] live -- board %s seed %s, Movement=%d, cible %s" % (BOARD, SEED, MOVEMENT, FOE))
        for r in rows:
            print("  [%-2s] %-16s ab=%-5d seuil=%.1f hp=%-9d dist=%-2s frozen=%-5s normalPlan=%-5s "
                  "castHere=%-5s u=%-10s natif=%-5s port=%-5s"
                  % (r["arm"], r["caster"], r["ability"], r["threshold"], r["hp"], r["dist"],
                     r["frozen"], r["normal_plan"], r["castable_here"],
                     "None" if r["u"] is None else round(r["u"], 4), r["native"], r["port"]))
        print("  -- contre-epreuve gate-coupe (= le port d'avant cette tranche) --")
        for r in rows:
            print("     [%-2s] %-16s -> port=%-5s %s"
                  % (r["arm"], r["caster"], r["port_gate_cut"],
                     "MORD" if r["port_gate_cut"] != r["port"] else "inerte"))

    want_u = {"lo": (0.0, 1.0), "mid": (2.0, 10.0), "hi": (15.0, 1e9)}
    for r in rows:
        # MONTAGE, QUATRE conditions -- sans elles la ligne ne mesure pas ce qu'elle annonce :
        #   `frozen`          `--unit-stat <X>:Movement=0` a MORDU : APRES placement, plus aucune
        #                     tuile. Un vert obtenu sur une mutation qui ne prend pas ne prouve rien ;
        #   `dist == voulu`   la geometrie visee est bien celle atteinte ;
        #   `not normal_plan` l'attaque normale n'a AUCUN plan, donc son custom `Fix64(1)` ne peut
        #                     pas rafler l'argmax ;
        #   `castable_here`   l'ability, elle, EST castable depuis la tuile courante.
        if (not r["frozen"]) or r["dist"] != r["want_dist"] or r["normal_plan"] \
                or not r["castable_here"]:
            print("  BAD MONTAGE [%s] %s : frozen=%s dist=%s (voulu %s) normalPlan=%s castHere=%s"
                  % (r["arm"], r["caster"], r["frozen"], r["dist"], r["want_dist"],
                     r["normal_plan"], r["castable_here"]))
            bad += 1
            continue
        # REGIME : chaque bras doit tomber dans SA fenetre d'utilite, sinon il ne discrimine rien.
        lo_b, hi_b = want_u[r["arm"]]
        if r["u"] is None or not (lo_b < r["u"] <= hi_b):
            print("  BAD REGIME [%s] %s : u=%s hors (%s, %s]" % (r["arm"], r["caster"], r["u"],
                                                                 lo_b, hi_b))
            bad += 1
            continue
        # CRITERE A -- ACCORD PLEIN. Depuis que le seuil porte est le seuil EFFECTIF (`Fix64(10)`,
        # cf. `-r4`), les deux canaux doivent s'accorder DANS LES DEUX SENS sur les trois bras.
        # Avant, seul le sens « le port ne refuse jamais ce que le natif choisit » etait exigible :
        # le port acceptait a `u = 5` la ou le natif refusait, et cet ecart PERMISSIF etait la
        # signature du seuil faux.
        if r["native"] != r["port"]:
            print("  VIOLE A [%s] %s : natif=%s port=%s a u=%.4f"
                  % (r["arm"], r["caster"], r["native"], r["port"], r["u"]))
            bad += 1
        # CRITERE B : le gate MORD cote port partout SOUS le seuil, et nulle part au-dessus.
        if (r["u"] > r["threshold"]) != bool(r["port"]):
            print("  VIOLE B [%s] %s : u=%.4f vs seuil %.1f -> port=%s"
                  % (r["arm"], r["caster"], r["u"], r["threshold"], r["port"]))
            bad += 1
        # CRITERE C : quand l'utilite est FRANCHE, le natif propose bel et bien cette ability --
        # c'est le temoin qui exclut « elle n'est de toute facon jamais proposee », et donc ce qui
        # donne un sens au refus du bras `lo`.
        if r["arm"] == "hi" and not r["native"]:
            print("  VIOLE C [hi] %s : natif REFUSE a u=%.4f -- le temoin ne tient pas"
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
