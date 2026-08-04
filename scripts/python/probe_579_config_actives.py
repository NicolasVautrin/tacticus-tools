"""#419-r1-tr14-r5-r2-r2-r1 -- le canal PRE-FABRIQUE `UnitConfiguration.ActiveAbilities`.

Le capteur (#466, PR #579) publie sur `unitAbilityStates`, PAR UNITE, `configId` (la cle de
jointure) et `configActives` (`UnitConfiguration.ActiveAbilities`, `config@+0xa0`), plus
`configLayout` au niveau reponse. C'est l'etat AVANT la fabrique -- ce que teste la garde
`FilterNewList` du repli generique de
`IdunBattle.Entities.Factories.UnitFactory$$AddNormalAttackAbility`, alors que le canal
`unitAbilityStates.units[].actives` lit l'`ActiveAbilityComponent`, donc APRES.

CE QUE CE PROBE MESURE -- les sept crans du plan (case-doc SS7.4), en DEUX volets :

  * `--volet index` (crans 1 a 6) : le montage a six unites du SS7.2. Il confronte
    `configActives` (PRE) a `actives` (POST) unite par unite. Le cran qui porte tout est le 5 :
    `actives \\ configActives` doit valoir exactement l'attaque normale que la fabrique vient
    d'ecrire, et `configActives \\ actives` doit etre VIDE. Si les deux listes etaient EGALES,
    le capteur lirait le composant et non la configuration, et la garde resterait tautologique.
  * `--volet summon` (cran 7) : une unite INVOQUEE n'a AUCUNE `UnitConfiguration` dans la BC
    (elle nait d'une operation de spawn, pas de `BC.Units`). Elle doit sortir en
    `configActives: null` -- PAS MESURE -- et JAMAIS en `[]`, qui est la mesure « configuration
    sans actif » (50 des 175 entrees du seed). Confondre les deux ferait appliquer le repli
    generique a une unite dont on n'a rien lu.

MESURE DU 2026-08-04 (session 3, build `rnca9r7q6c`), volet `index` :

  | entite           | PRE (`configActives`) | POST (`actives`) | POST \\ PRE          |
  |------------------|-----------------------|------------------|----------------------|
  | `templAggressor` | `[1048]`              | `[1048, 1128]`   | `1128` (norm. Boltstorm) |
  | `eldarRanger`    | `[1063]`              | `[1063, 69]`     | `69`                 |
  | `orksNob`        | `[1152]`              | `[1152, 69]`     | `69`                 |
  | `tauMarksman`    | `[1069]`              | `[1069, 1076]`   | `1076`               |
  | `necroWarden`    | `[1005]`              | `[1005, 69]`     | `69`                 |
  | `astraBullgryn`  | `[1017]`              | `[1017, 69]`     | `69`                 |

  `configLayout` : `bcResolved=true`, `bcUnits=175`, `bcUnitsWithActives=125`,
  `activeAbilitiesOff=0xa0`, `idOff=0x10`, `baseUnitComponentIdOff=0x10`,
  `elemClass=ActiveAbilityType`, `elemStride=4`, `unreadableActiveLists=0`,
  `configIdCollisions=[]`, `unmatchedEntities=0`.

  Et `normal_attack_already_present` rend `None` **6/6** sur PRE contre non-`None` **6/6** sur
  POST : c'est le chiffre qui dit que le canal PRE n'est PAS tautologique.

Usage :
    python scripts/python/probe_579_config_actives.py --volet all --state-file <ABSOLU>.json

ASCII only.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import hexgeo                                             # noqa: E402
import probe_419r1tr14_heavy_bolt_pistol as P14           # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType     # noqa: E402
from engine.runner.abilities.attack_type import REGULAR_ATTACK_ABILITY_TYPES  # noqa: E402
from engine.services.custom_normal_attack import normal_attack_already_present  # noqa: E402

MontageError = P14.MontageError

BOARD = "MC1_67"
SEED_INDEX = "777"
SEED_SUMMON = "777"

P_UNITS = ("tauMarksman", "necroWarden", "astraBullgryn")
A_UNITS = ("templAggressor", "eldarRanger", "orksNob")

#: PRE attendu par unite -- les colonnes du SS7.2, relues du BC reellement envoye au runner.
EXPECTED_PRE = {
    "templAggressor": [1048], "eldarRanger": [1063], "orksNob": [1152],
    "tauMarksman": [1069], "necroWarden": [1005], "astraBullgryn": [1017],
}
#: L'entree que la fabrique AJOUTE (`POST \ PRE`) -- l'attaque normale, une par unite.
EXPECTED_ADDED = {
    "templAggressor": 1128, "eldarRanger": 69, "orksNob": 69,
    "tauMarksman": 1076, "necroWarden": 69, "astraBullgryn": 69,
}

SUMMONER = "orksRuntherd"
GET_EM_RUNTZ = 1045


def _names(config_actives):
    """`configActives` (liste de `{type,name}`) -> liste de NOMS d'`ActiveAbilityType`.
    `None` en entree (PAS MESURE) ressort `None` : le tri-etat traverse."""
    if config_actives is None:
        return None
    out = []
    for c in config_actives:
        t = c.get("type") if isinstance(c, dict) else c
        try:
            out.append(ActiveAbilityType(int(t)).name)
        except ValueError:
            continue                # id hors enum du mirror -> non ingerable, non devinable
    return out


def _states(rpc, rid):
    return rpc("unitAbilityStates", {"runnerId": rid}, 180)


def _vis_by_id(rpc, rid):
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1}, 200)
    return {u.get("id"): u.get("visualId") for u in (dv.get("units") or ())}


# --------------------------------------------------------------------------- volet INDEX

def run_index(rpc, build, verbose: bool = True) -> dict:
    """Crans 1 a 6 : la disposition resolue, l'index, et PRE contre POST unite par unite."""
    rid = build(SEED_INDEX, ["--board", BOARD, "--p-units", ",".join(P_UNITS),
                             "--a-units", ",".join(A_UNITS)])
    st = _states(rpc, rid)
    vis = _vis_by_id(rpc, rid)
    layout = st.get("configLayout") or {}
    rows = []
    for su in (st.get("units") or ()):
        eid = su.get("entityId")
        v = vis.get(eid)
        if v not in EXPECTED_PRE:
            continue
        post = [int(a.get("type")) for a in (su.get("actives") or ()) if a.get("type") is not None]
        raw = su.get("configActives")
        pre = None if raw is None else [int(c.get("type")) for c in raw]
        added = None if pre is None else sorted(set(post) - set(pre))
        missing = None if pre is None else sorted(set(pre) - set(post))
        rows.append({
            "unit": v, "entityId": eid, "configId": su.get("configId"),
            "pre": pre, "post": post, "added": added, "missing": missing,
            "pre_expected": EXPECTED_PRE[v], "added_expected": [EXPECTED_ADDED[v]],
            # cran 6 : le foyer de la garde, sur les DEUX canaux.
            "foyer_pre": normal_attack_already_present(_names(raw)),
            "foyer_post": normal_attack_already_present(
                [ActiveAbilityType(t).name for t in post
                 if t in set(int(x) for x in ActiveAbilityType.__members__.values())]),
            "post_regulars": [t for t in post if t in REGULAR_ATTACK_ABILITY_TYPES],
            "pre_regulars": None if pre is None
            else [t for t in pre if t in REGULAR_ATTACK_ABILITY_TYPES],
        })
    out = {"rid": rid, "layout": layout, "rows": rows}
    if verbose:
        print("   configLayout : bcResolved=%s bcUnits=%s withActives=%s off=0x%x/0x%x/0x%x "
              "elem=%s stride=%s unreadable=%s collisions=%s unmatched=%s"
              % (layout.get("bcResolved"), layout.get("bcUnits"),
                 layout.get("bcUnitsWithActives"), layout.get("activeAbilitiesOff") or 0,
                 layout.get("idOff") or 0, layout.get("baseUnitComponentIdOff") or 0,
                 layout.get("elemClass"), layout.get("elemStride"),
                 layout.get("unreadableActiveLists"), layout.get("configIdCollisions"),
                 layout.get("unmatchedEntities")))
        for r in rows:
            print("   [%-16s] PRE=%-10s POST=%-14s ajoute=%-8s manquant=%-6s "
                  "foyer(PRE)=%-28s foyer(POST)=%s"
                  % (r["unit"], r["pre"], r["post"], r["added"], r["missing"],
                     r["foyer_pre"], r["foyer_post"]))
    return out


# --------------------------------------------------------------------------- volet SUMMON

def run_summon(rpc, build, verbose: bool = True) -> dict:
    """Cran 7 : une unite INVOQUEE n'a pas de configuration -> `configActives: null`, jamais `[]`."""
    rid = build(SEED_SUMMON, ["--board", BOARD,
                              "--p-units", "%s,tauMarksman" % SUMMONER,
                              "--a-units", "templAggressor,eldarRanger"])

    def _act(action):
        """Les actions passent par le RPC `applyAction` -- PAS par `rl_duel act`, qui exige un
        `--state-file` et rendrait le montage dependant du fichier qu'un appelant lui passe
        (piege deja paye : le volet visait le runner du volet precedent)."""
        return rpc("applyAction", {"runnerId": rid, "action": action}, 120)

    before = _states(rpc, rid)
    ids_before = {su.get("entityId") for su in (before.get("units") or ())}
    unmatched_before = (before.get("configLayout") or {}).get("unmatchedEntities")

    legal = None
    for _ in range(10):
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 4}, 300)
        pos = {u.get("visualId"): ((u.get("pos") or {}).get("col"),
                                   (u.get("pos") or {}).get("row"))
               for u in (dv.get("units") or ())}
        cid = next((u.get("id") for u in (dv.get("units") or ())
                    if u.get("visualId") == SUMMONER), None)
        if cid is None:
            raise MontageError("montage NON INSTALLE : %s absent du board" % SUMMONER)
        at = rpc("abilityTargets", {"runnerId": rid, "casterId": cid}, 120)
        tg = []
        for u in (at.get("units") or ()):
            if u.get("unitId") != cid:
                continue
            for ab in (u.get("abilities") or ()):
                if ab.get("abilityId") == GET_EM_RUNTZ:
                    tg = ab.get("fromHere") or []
        if verbose:
            print("     approche summon : turnsEnded=%s player=%s cibles=%d"
                  % (dv.get("turnsEnded"), dv.get("currentPlayer"), len(tg)))
        if tg:
            legal = (cid, tg[0])
            break
        if pos.get(SUMMONER) is None or pos.get("templAggressor") is None:
            break
        anchor = pos["templAggressor"] if dv.get("currentPlayer") == 3 else pos[SUMMONER]
        mv = rpc("aiMovableTiles", {"runnerId": rid}, 90)
        for mu in (mv.get("units") or ()):
            tiles = [t for t in (mu.get("tiles") or ()) if t.get("col") is not None]
            if not tiles:
                continue
            best = min(tiles, key=lambda t: hexgeo.distance((t["col"], t["row"]), anchor))
            _act({"kind": "move", "unitId": mu.get("unitId"),
                  "to": {"col": best["col"], "row": best["row"]}})
        _act({"kind": "endturn"})
    if legal is None:
        raise MontageError("montage NON INSTALLE : aucune cible legale de %d atteinte"
                           % GET_EM_RUNTZ)
    cid, tgt = legal
    action = {"kind": "ability", "casterId": cid, "abilityType": GET_EM_RUNTZ}
    if tgt.get("kind") == "unit":
        action["targetId"] = tgt.get("targetId")
    else:
        action["to"] = {"col": tgt.get("col"), "row": tgt.get("row")}
    _act(action)

    after = _states(rpc, rid)
    layout = after.get("configLayout") or {}
    newborn = []
    for su in (after.get("units") or ()):
        eid = su.get("entityId")
        if eid in ids_before:
            continue
        newborn.append({"entityId": eid, "configId": su.get("configId"),
                        "configActives": su.get("configActives"),
                        "actives": [a.get("type") for a in (su.get("actives") or ())]})
    out = {"rid": rid, "newborn": newborn,
           "unmatched_before": unmatched_before,
           "unmatched_after": layout.get("unmatchedEntities"),
           "layout": layout}
    if verbose:
        print("   unmatchedEntities : avant=%s apres=%s" % (unmatched_before,
                                                            layout.get("unmatchedEntities")))
        for n in newborn:
            print("   INVOQUE eid=%s configId=%s configActives=%s actives=%s"
                  % (n["entityId"], n["configId"],
                     "null" if n["configActives"] is None else n["configActives"],
                     n["actives"]))
    return out


# --------------------------------------------------------------------------- CLI

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True, help="chemin ABSOLU (prefixe des state-files)")
    ap.add_argument("--volet", default="all", choices=("all", "index", "summon"))
    args = ap.parse_args()

    from rl_collect_batch import _resolve_session, _rpc
    sid = _resolve_session()

    def rpc(method, body=None, timeout=120):
        r = _rpc(sid, method, [body] if body is not None else [], timeout=timeout)
        return r["result"] if isinstance(r, dict) and "result" in r else r

    logs = os.path.dirname(os.path.abspath(args.state_file))
    os.makedirs(logs, exist_ok=True)
    stem = os.path.splitext(os.path.basename(args.state_file))[0]
    seq, rids = {"n": 0}, []
    sf = {"path": args.state_file}

    def build(seed, extra):
        seq["n"] += 1
        sf["path"] = os.path.join(logs, "%s_%d.json" % (stem, seq["n"]))
        rid = P14._build(sf["path"], ["--seed", str(seed), *extra])
        rids.append(rid)
        return rid

    print("session", sid)
    rc = 0
    try:
        if args.volet in ("all", "index"):
            print("== volet INDEX (crans 1-6) ==")
            out = run_index(rpc, build)
            bad = [r["unit"] for r in out["rows"]
                   if r["pre"] != r["pre_expected"] or r["added"] != r["added_expected"]
                   or r["missing"]]
            print("   -> %d/%d unites conformes" % (len(out["rows"]) - len(bad),
                                                    len(out["rows"])))
            rc |= 1 if (bad or len(out["rows"]) != 6) else 0
            taut = [r["unit"] for r in out["rows"]
                    if r["foyer_pre"] is not None or r["foyer_post"] is None]
            print("   -> foyer : PRE=None et POST!=None attendu partout ; ecarts : %s"
                  % (taut or "aucun"))
            rc |= 1 if taut else 0
        if args.volet in ("all", "summon"):
            print("== volet SUMMON (cran 7) ==")
            try:
                out = run_summon(rpc, build)
            except MontageError as e:
                print("   MONTAGE : %s" % e)
                return rc | 2
            if not out["newborn"]:
                print("   MONTAGE : aucun invoque apparu")
                return rc | 2
            wrong = [n["entityId"] for n in out["newborn"] if n["configActives"] is not None]
            print("   -> invoques a `configActives` non nul : %s" % (wrong or "aucun"))
            rc |= 1 if wrong else 0
            if not (out["unmatched_after"] or 0) > (out["unmatched_before"] or 0):
                print("   -> unmatchedEntities n'a PAS augmente : la jointure ne signale pas "
                      "les invoques")
                rc |= 1
    finally:
        for rid in rids:
            try:
                rpc("disposeRunner", {"runnerId": rid}, 60)
            except Exception:
                pass
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
