"""PROBE #957-r4 -- le splash de `1017 FragBomb` et l'ancre de `1179 CultDemagogue`, CONFRONTES LIVE.

Les deux volets sont PORTES et gardes OFFLINE depuis #957, et AUCUN des deux n'avait ete confronte
au natif : les trois montages de la tranche portaient `darkaAsmodai` / `spaceRockfist` /
`tyranDeathleaper`, jamais `astraBullgryn` (1017) ni `genesPrimus` (1179). Ce probe monte les deux
porteurs -- tous deux dans `rl_duel build --list-pool` -- et va chercher l'ORACLE NATIF de chacun.

Les deux volets n'ont PAS le meme oracle, et c'est la STRUCTURE du playbook natif qui l'impose :

  * `IdunBattle.AI.Playbook.Loki.FragBombPlaybook` surcharge `MakeDamagePredictions` -> l'oracle
    DIRECT est `aiPlaybookPredict`, qui invoque cette methode meme et rend la liste des
    `ProbableDamageEvent` (cible, coups appliques). Le volet SPLASH y est LISIBLE : un evenement
    par unite adjacente a la tuile ciblee, ALLIES COMPRIS (le set natif
    `...FragBombAbility$$GetAdjacentTargets` n'a AUCUN wrapper `Enemies`), a `nrOfHits_2` coups,
    la cible principale restant a `nrOfHits`.
  * `IdunBattle.AI.Playbook.Loki.CultDemagoguePlaybook` surcharge `EvaluateInternal` et n'a AUCUNE
    `MakeDamagePredictions` (le corps generique de `ComparablePlaybook<T>` LEVE) -- ni
    `aiPlaybookPredict` ni `pairUtility` ne rendent donc son utilite. L'oracle est le TOUR D'IA
    OBSERVE (`aiDryRunAllUnits`), c'est-a-dire la CIBLE que le natif choisit ; et le discriminant
    est une geometrie ou l'ancre du terme dominant (CIBLE vs CASTER) fait basculer l'argmax.

REGIME DISCRIMINANT DE 1179, et pourquoi il existe : le terme 1 vaut
`min(|tuiles libres <=2 hex de <ancre>|, nrOfSummons) * 20`. Ancre au CASTER, il est CONSTANT sur
les cibles -- l'argmax retombe alors sur le terme 2 (decoys/neophytes amis autour de la cible), NUL
au premier tour, donc sur la PREMIERE cible enumeree (`Bucket$$AddAction` ne remplace que sur
amelioration STRICTE). Ancre a la CIBLE, c'est ce terme qui departage. Il suffit donc que la
PREMIERE cible eligible ait MOINS de tuiles libres autour d'elle qu'une autre : les deux ancres
designent alors des cibles DIFFERENTES, et le natif tranche.

Usage (depuis scripts/python) :

    python probe_957r4_faces_decision_live.py --bras fragbomb
    python probe_957r4_faces_decision_live.py --bras fragbomb-isole
    python probe_957r4_faces_decision_live.py --bras cultdemagogue

ASCII only. Dispose SES runners, jamais ceux des autres.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import probe_130_placement_sort_rng as P130  # noqa: E402

#: Ce qui doit changer pour que cette confrontation puisse changer d'avis.
DECLENCHEUR = {
    "chemins": ("scripts/python/engine/entities/abilities/active_ability.py",
                "scripts/python/engine/playbook/prediction/abilities.py",
                "scripts/python/engine/playbook/bespoke.py",
                "scripts/python/probe_957r4_faces_decision_live.py",
                "scripts/python/tests/engine/runner/test_957r4_faces_decision_live.py"),
    "build": True,
    "toujours": False,
    "raison": "Il confronte au NATIF le volet SPLASH de la prediction de 1017 (`aiPlaybookPredict`) "
              "et l'ancre du terme dominant de 1179 (tour d'IA observe).",
}

BOARD = "MC1_67"

# ---- 1017 FragBomb ------------------------------------------------------------------------
BULL = "astraBullgryn"          # seul porteur de 1017 dans le seed BC
ALLY_1017 = "astraCreed"        # allie -> exerce le FRIENDLY-FIRE du set nu
ENEMIES_1017 = "necroOverlord,necroWarden,necroDestroyer,necroSpyder"
ABILITY_1017 = 1017

# ---- 1179 CultDemagogue -------------------------------------------------------------------
PRIMUS = "genesPrimus"          # porteur de 1179
ALLY_1179 = "genesAcolyte"
ENEMIES_1179 = "necroOverlord,necroWarden,necroDestroyer,necroSpyder"
ABILITY_1179 = 1179


def _build(state_file, p_units, a_units, extra=(), seed="777"):
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", seed,
           "--state-file", str(state_file), "--board", BOARD,
           "--p-units", p_units, "--a-units", a_units] + list(extra)
    proc = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not Path(state_file).exists():
        print("BUILD KO:", (proc.stderr or proc.stdout or "")[-1200:])
        return None
    return json.loads(Path(state_file).read_text())["runnerId"]


def _consts_1017():
    """`GetNumberConstant(0x2f = nrOfHits)` et `(0x32 = nrOfHits_2)` de la config 1017."""
    import gameconfig as GC
    c = (GC.ability("FragBomb") or {}).get("constants") or {}
    return int(c.get("nrOfHits") or 0), int(c.get("nrOfHits_2") or 0)


# ============================================================================================
#  VOLET 1017 -- le SPLASH de la PREDICTION
# ============================================================================================

def confronte_fragbomb(rpc, rid, isole: bool) -> dict:
    """Pose la geometrie `ring_scenario` puis interroge l'ORACLE `aiPlaybookPredict` sur 1017.

    ⚠ `aiPlaybookPredict` veut le `squadId` d'`observeBattle`, pas son `entityId` (meme piege que
    #957-r3). `decisionView.units[].id` est apparie au `squadId` par le `visualId`, jamais suppose.
    """
    sys.path.insert(0, str(PYDIR / "tests" / "engine" / "runner"))
    from _ringed_cast import ring_scenario  # noqa: E402

    sc = ring_scenario(rpc, rid, BULL, ALLY_1017, rounds=1, place_caster_adjacent=True,
                       isolate_target=isole)
    if sc.get("reason"):
        return {"ok": False, "raison": "montage : %s" % sc["reason"]}

    ob = sc["ob"] or {}
    # `decisionView.id` -> `observeBattle.squadId`. Les deux vues portent le meme identifiant de
    # squad dans nos runners, mais on ne le SUPPOSE pas : on verifie qu'il existe cote observeBattle.
    squads = {int(u["squadId"]) for u in (ob.get("units") or []) if u.get("squadId") is not None}
    for nom, uid in (("caster", sc["me"]), ("cible", sc["target"])):
        if int(uid) not in squads:
            return {"ok": False,
                    "raison": "%s u%s absent des squadId d'observeBattle -- appariement des vues "
                              "a refaire avant de conclure" % (nom, uid)}

    r = rpc("aiPlaybookPredict", {"runnerId": rid, "unitId": int(sc["me"]),
                                  "targetId": int(sc["target"]),
                                  "abilityType": ABILITY_1017}, 90)
    if not isinstance(r, dict) or not r.get("ok"):
        return {"ok": False, "raison": "aiPlaybookPredict KO : %s" % (r if not isinstance(r, dict)
                                                                     else r.get("error"))}
    events = [{"target": ev.get("targetId"), "hits": ev.get("appliedHits")}
              for ev in (r.get("events") or [])]
    h1, h2 = _consts_1017()
    return {"ok": True, "caster": sc["me"], "target": sc["target"], "ally": sc["ally"],
            "ring": list(sc["ring_units"]), "events": events, "nrOfHits": h1, "nrOfHits2": h2}


def _port_fragbomb(res: dict) -> dict:
    """Ce que le PORT annonce pour ce meme montage : le SET (`FragBombAbility._AOE`, via
    `get_aoe_targets`) et les COUPS par batch (`_frag_bomb_inputs`)."""
    import gameconfig as GC
    from engine.entities.abilities.ability_configuration import AbilityConfiguration
    from engine.playbook.prediction.abilities import _frag_bomb_inputs
    cfg = AbilityConfiguration.from_gameconfig("FragBomb", GC.ability("FragBomb"))
    inp = _frag_bomb_inputs(None, None, None, None, cfg)
    return {"hits_principal": inp.get("hits_override"),
            "hits_splash": (inp.get("aoe_overrides") or {}).get("hits_override")}


def verdict_fragbomb(res: dict, isole: bool) -> int:
    if not res.get("ok"):
        print("NON CONFRONTE :", res.get("raison"))
        return 2
    port = _port_fragbomb(res)
    attendu = {int(res["target"])}
    if not isole:
        attendu |= {int(u) for u in res["ring"]}
    obtenu = {int(e["target"]) for e in res["events"] if e["target"] is not None}
    par_cible = {}
    for e in res["events"]:
        par_cible.setdefault(int(e["target"]), []).append(e["hits"])

    print("caster=u%s cible=u%s allie=u%s anneau=%s"
          % (res["caster"], res["target"], res["ally"], res["ring"]))
    print("config 1017 : nrOfHits=%s nrOfHits_2=%s ; port : principal=%s splash=%s"
          % (res["nrOfHits"], res["nrOfHits2"], port["hits_principal"], port["hits_splash"]))
    print("evenements NATIFS (%d) : %s" % (len(res["events"]), sorted(par_cible.items())))

    if not res["events"]:
        print("REGIME NON ARME : aucun evenement predit -- rien a confronter")
        return 2
    rc = 0
    if obtenu != attendu:
        print("ECART SET : natif %s != cible+anneau %s" % (sorted(obtenu), sorted(attendu)))
        rc = 1
    else:
        print("SET : OK -- le natif predit exactement cible + voisinage%s"
              % (" (vide, cible isolee)" if isole else ""))
    for tid, hits in sorted(par_cible.items()):
        att = port["hits_principal"] if tid == int(res["target"]) else port["hits_splash"]
        if set(hits) != {att}:
            print("ECART COUPS u%s : natif %s != port %s" % (tid, hits, att))
            rc = 1
    if rc == 0:
        print("COUPS : OK -- principal=%s, splash=%s, exactement ce que le port surcharge"
              % (port["hits_principal"], port["hits_splash"]))
    if not isole:
        if int(res["ally"]) in obtenu:
            print("FRIENDLY-FIRE : OK -- l'ALLIE u%s est PREDIT par le natif (set nu, sans "
                  "wrapper `Enemies`)" % res["ally"])
        else:
            print("ECART FRIENDLY-FIRE : l'allie u%s n'est PAS predit" % res["ally"])
            rc = 1
        if int(res["caster"]) in obtenu:
            print("ECART : le CASTER u%s est predit (le set natif le SOUSTRAIT)" % res["caster"])
            rc = 1
    print("VERDICT :", "le natif et le port predisent la MEME chose" if rc == 0 else "ECART")
    return rc


# ============================================================================================
#  VOLET 1179 -- l'ANCRE du terme dominant
# ============================================================================================

def _pose_geometrie_1179(rpc, rid):
    """Deux ennemis a <=2 hex du caster dont les VOISINAGES LIBRES different fortement.

    Construction, entierement DERIVEE du `boardGraph` du runner (aucune tuile en dur) :
      * `centre` = une tuile a 6 voisins tous marchables, la plus DEGAGEE du plateau ;
      * la cible OUVERTE y est posee ; la cible ENCOMBREE est posee sur la tuile marchable dont le
        voisinage a <=2 hex compte le MOINS de tuiles marchables (bord de plateau) et que des
        unites viennent encore encombrer.
    Rend `{"reason": ...}` si la geometrie n'est pas atteignable -- jamais un verdict.
    """
    import hexgeo
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        return {"reason": "boardGraph indispo"}
    byid = {t["id"]: t for t in bg["tiles"]}
    coord = {t["id"]: (t["col"], t["row"]) for t in bg["tiles"]}
    walk = {t["id"] for t in bg["tiles"] if t.get("walkable")}

    def libres_autour(tid, r=2):
        c = coord[tid]
        return [o for o in walk if o != tid and hexgeo.distance(coord[o], c) <= r]

    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    units = [u for u in (dv.get("units") or []) if u.get("alive")]
    me = next((u for u in units if u.get("visualId") == PRIMUS), None)
    if me is None:
        return {"reason": "porteur %s absent du build" % PRIMUS}
    ens = [u for u in units if u.get("owner") != me.get("owner")]
    if len(ens) < 3:
        return {"reason": "moins de 3 ennemis vivants"}

    # La tuile la PLUS degagee et la MOINS degagee, mesurees et non supposees.
    cands = sorted(walk, key=lambda t: (-len(libres_autour(t)), t))
    ouverte, encombree = cands[0], cands[-1]
    if len(libres_autour(ouverte)) <= len(libres_autour(encombree)):
        return {"reason": "le plateau n'offre aucun contraste de voisinage libre"}
    # Le caster doit voir les DEUX a <=2 hex : on le pose sur une tuile qui le permet.
    pivots = [t for t in walk
              if t not in (ouverte, encombree)
              and hexgeo.distance(coord[t], coord[ouverte]) <= 2
              and hexgeo.distance(coord[t], coord[encombree]) <= 2]
    if not pivots:
        return {"reason": "aucune tuile ne voit les deux cibles a <=2 hex "
                          "(contraste et proximite incompatibles sur ce plateau)"}
    pivot = pivots[0]

    def move(uid, tid):
        c = byid[tid]
        return rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": uid, "to": {"col": c["col"], "row": c["row"]}}}, 40)

    # ⚠ L'ORDRE de pose fixe l'ordre d'enumeration ; on pose la cible ENCOMBREE en premier pour que
    # le contre-factuel « ancre CASTER » (qui retombe sur la 1re cible au tie) designe bien l'AUTRE
    # cible que l'ancre CIBLE. Si l'ordre reel du selecteur differe, le probe le MESURE plus bas.
    move(ens[0]["id"], encombree)
    move(ens[1]["id"], ouverte)
    move(me["id"], pivot)
    # les autres ennemis loin, pour ne pas ajouter de cible eligible
    loin = [t for t in cands
            if hexgeo.distance(coord[t], coord[pivot]) >= 5]
    for i, u in enumerate(ens[2:]):
        if i < len(loin):
            move(u["id"], loin[i])
    return {"byid": byid, "coord": coord, "walk": walk, "me": me["id"],
            "encombree": ens[0]["id"], "ouverte": ens[1]["id"],
            "libres_encombree": len(libres_autour(encombree)),
            "libres_ouverte": len(libres_autour(ouverte))}


def confronte_cultdemagogue(rpc, rid, sid) -> dict:
    """Confronte l'ancre du terme dominant : port TEL QUEL (ancre CIBLE) vs contre-factuel
    (ancre CASTER), face a la cible que le NATIF choisit."""
    import engine_validate as EV
    from engine import weights as W

    geo = _pose_geometrie_1179(rpc, rid)
    if geo.get("reason"):
        return {"ok": False, "raison": "montage : %s" % geo["reason"]}

    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 32, "allAbilities": True}, 180)
    mov = rpc("aiMovableTiles", {"runnerId": rid}, 60)
    mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
    wt = W.load()
    uid = int(geo["me"])

    # --- l'ORACLE NATIF : l'action que l'IA propose pour CETTE unite sur CET etat
    dry = rpc("aiDryRunAllUnits", {"runnerId": rid}, 180)
    natif = None
    for row in (dry.get("units") or []):
        if int(row.get("unitId", -1)) != uid:
            continue
        for m in ((row.get("action") or {}).get("messages") or []):
            if m.get("cls") == "ActiveAbilityMessage":
                natif = {"ability": m.get("abilityType"), "target": m.get("targetId")}
    # --- le PORT, par le chemin REEL (`DefaultAiUnitTactic` -> `_bespoke_candidates`)
    port_cible = EV.engine_decide(sid, rid, dv, mov_by_unit, uid, wt)

    # --- le CONTRE-FACTUEL : la MEME chaine, ancre ramenee au CASTER (l'etat d'avant #957)
    from engine.playbook import bespoke as BSP
    vrai = BSP.CultDemagoguePlaybook._free_tiles_around

    def ancre_caster(self, ctx, center):
        me = ctx.me or {}
        p = me.get("pos") or {}
        origine = (p.get("col"), p.get("row")) if p.get("col") is not None else None
        return vrai(self, ctx, origine)

    BSP.CultDemagoguePlaybook._free_tiles_around = ancre_caster
    try:
        port_caster = EV.engine_decide(sid, rid, dv, mov_by_unit, uid, wt)
    finally:
        BSP.CultDemagoguePlaybook._free_tiles_around = vrai

    return {"ok": True, "uid": uid, "geo": {k: geo[k] for k in
                                            ("encombree", "ouverte", "libres_encombree",
                                             "libres_ouverte")},
            "natif": natif, "port_cible": port_cible, "port_caster": port_caster}


def verdict_cultdemagogue(res: dict) -> int:
    if not res.get("ok"):
        print("NON CONFRONTE :", res.get("raison"))
        return 2
    g, nat = res["geo"], res["natif"]
    pc, pk = res["port_cible"], res["port_caster"]
    print("caster=u%s" % res["uid"])
    print("cible ENCOMBREE=u%s (%d tuiles libres <=2hex)  cible OUVERTE=u%s (%d)"
          % (g["encombree"], g["libres_encombree"], g["ouverte"], g["libres_ouverte"]))
    print("natif        :", nat)
    print("port  ancre CIBLE  :", {k: pc.get(k) for k in ("kind", "ability", "target")})
    print("port  ancre CASTER :", {k: pk.get(k) for k in ("kind", "ability", "target")})

    if nat is None or int(nat.get("ability") or 0) != ABILITY_1179:
        print("REGIME NON ARME : le natif ne propose pas 1179 pour cette unite (il propose %s) -- "
              "rien a confronter sur l'ancre" % (nat,))
        return 2
    if pc.get("ability") != ABILITY_1179:
        print("ECART DE VOIE : le port ne propose pas 1179 (%s) -- l'ancre n'est pas en cause"
              % ({k: pc.get(k) for k in ("kind", "ability", "target")}))
        return 1
    if pc.get("target") == pk.get("target"):
        print("REGIME DEGENERE : les deux ancres designent la MEME cible (u%s) -- l'accord qui "
              "suivrait ne prouverait RIEN sur l'ancre" % pc.get("target"))
        return 2
    print("REGIME DISCRIMINANT : ancre CIBLE -> u%s ; ancre CASTER -> u%s"
          % (pc.get("target"), pk.get("target")))
    if int(nat["target"]) == int(pc["target"]):
        print("VERDICT : le natif choisit la cible de l'ancre CIBLE -- le fix #957 est CONFIRME live")
        return 0
    if int(nat["target"]) == int(pk["target"]):
        print("VERDICT : le natif choisit la cible de l'ancre CASTER -- le fix #957 est REFUTE")
        return 1
    print("VERDICT : le natif choisit u%s, ni l'une ni l'autre -- etage inconnu" % nat["target"])
    return 1


# ============================================================================================

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bras", choices=("fragbomb", "fragbomb-isole", "cultdemagogue"),
                    default="fragbomb")
    ap.add_argument("--state-file", default=None)
    ap.add_argument("--seed", default="777")
    a = ap.parse_args()

    rpc = P130.Rpc()
    sf = Path(a.state_file) if a.state_file else (
        ROOT / "logs" / "runners" / ("p957r4-%s.json" % uuid.uuid4().hex[:8]))
    sf.parent.mkdir(parents=True, exist_ok=True)

    if a.bras.startswith("fragbomb"):
        p_units, a_units = "%s,%s" % (BULL, ALLY_1017), ENEMIES_1017
        extra = ["--hp-target", "120000", "--hp-player", "120000", "--no-ai"]
    else:
        p_units, a_units = "%s,%s" % (PRIMUS, ALLY_1179), ENEMIES_1179
        extra = ["--hp-target", "120000", "--hp-player", "120000", "--no-ai"]

    rid = _build(sf, p_units, a_units, extra, seed=a.seed)
    if rid is None:
        print("NON CONFRONTE : le build a echoue (ce n'est PAS un verdict sur le port)")
        return 2
    try:
        if a.bras.startswith("fragbomb"):
            res = confronte_fragbomb(rpc, rid, isole=a.bras.endswith("isole"))
            return verdict_fragbomb(res, isole=a.bras.endswith("isole"))
        res = confronte_cultdemagogue(rpc, rid, rpc.sid)
        return verdict_cultdemagogue(res)
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 30)
        Path(sf).unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
