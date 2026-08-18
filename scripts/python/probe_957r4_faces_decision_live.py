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
PRIMUS = "genesPrimus"          # porteur de 1179 (`--list-pool` : present)
#: Les autres unites ne servent QU'A ENCOMBRER le voisinage de la cible pauvre -- aucune n'est un
#: `genesSmnDecoy`/`genesSmnNeophyte`, donc le terme 2 reste NUL des deux cotes et le seul
#: discriminant est bien le terme 1 (celui dont #957 a corrige l'ancre).
ALLIES_1179 = "genesMagus,genesPatriarch,genesKelermorph,genesBiophagus"
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
            "ring": list(sc["ring_units"]), "events": events, "nrOfHits": h1, "nrOfHits2": h2,
            "port_events": _events_du_port(rpc, rid, sc["me"], sc["target"])}


def _events_du_port(rpc, rid, caster, target) -> list:
    """Ce que `engine.playbook.prediction.abilities.make_damage_predictions` -- LE chemin du port,
    celui qui consomme `FragBombAbility.get_aoe_targets` et `_frag_bomb_inputs` -- rend sur ce MEME
    etat. C'est ce qui rend la confrontation MORDANTE cote port : sans lui, on ne compare le natif
    qu'a la geometrie du montage, et une mutation du SET porte passerait inapercue.

    Rend `[]` si le predicteur n'est pas montable -- l'appelant DIT alors qu'il n'a pas mesure.
    """
    from engine.ai import context as _ai_ctx
    from engine.playbook import scene as _scene
    from engine.playbook.prediction.abilities import make_damage_predictions
    from engine.runner import snapshot as _snapshot
    from engine import weights as W
    seam = lambda m, b, t: rpc(m, b, t)                                        # noqa: E731
    pred = _scene.build_predictor(seam, rid)
    if pred is None:
        return []
    dv = rpc("decisionView", _snapshot.decision_view_seed_body(rid, allAbilities=True, maxRank=8),
             180)
    mov = rpc("aiMovableTiles", {"runnerId": rid}, 60) or {}
    mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
    # La MEME couture que `engine_validate.engine_decide` : la face PREDICTION ne voit que la
    # `Scene`, et `ai.context.build` est son unique constructeur live.
    ctx = _ai_ctx.build(seam, rid, dv, mov_by_unit, int(caster), W.load(), pred)
    if getattr(ctx, "scene", None) is None:
        return []
    evs = make_damage_predictions(ctx.scene, int(caster), int(target), ABILITY_1017, "FragBomb")
    out = []
    for e in (evs or []):
        dp = getattr(e, "prediction", None)
        out.append({"target": getattr(e, "target", None),
                    "hits": getattr(dp, "applied_hits", None) if dp is not None else None})
    return out


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
    pev = res.get("port_events") or []
    par_port = {}
    for e in pev:
        if e["target"] is not None:
            par_port.setdefault(int(e["target"]), []).append(e["hits"])
    print("evenements du PORT (%d) : %s" % (len(pev), sorted(par_port.items())))

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
    if not pev:
        print("PORT : NON MESURE (predicteur offline indisponible) -- jamais rabattu sur un accord")
        rc = max(rc, 2)
    elif par_port != par_cible:
        print("ECART PORT/NATIF : port %s != natif %s"
              % (sorted(par_port.items()), sorted(par_cible.items())))
        rc = 1
    else:
        print("PORT : OK -- `make_damage_predictions` rend exactement les memes (cible, coups)")
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

def _nr_of_summons(rpc, rid, uid) -> int:
    """`...CultDemagogueAbility$$GetDecoyAmount` = `GetVariableForLevel(0x4f = nrOfSummons)`, lu par
    le MEME chemin que le port (jamais un litteral ecrit ici)."""
    from engine.entities.effects.magnitude import ability_var
    snap = rpc("combatSnapshot", {"runnerId": rid}, 40) or {}
    niv = 0
    for u in (snap.get("units") or []):
        if int(u.get("entityId", -1)) == int(uid):
            niv = int((u.get("unitConfig") or {}).get("activeAbilityLevel") or 0)
    if niv <= 0:
        return 0                     # NON MESURE -- jamais rabattu sur un niveau suppose
    return int(ability_var("CultDemagogue", "nrOfSummons", niv) or 0)


def _configurations(coord, walk, plafond, n_encombreurs, k=24):
    """Les `k` meilleures configurations (pivot, cible PAUVRE, cible RICHE, encombreurs), classees
    par ECART PLAFONNE decroissant.

    Le terme 1 natif est `min(|tuiles libres <=2 hex de l'ancre|, nrOfSummons) * 20` : il ne
    departage QUE si les deux valeurs PLAFONNEES different. On maximise donc
    `min(libres(riche), plafond) - min(libres(pauvre), plafond)`, en comptant l'occupation
    PLANIFIEE (pivot + les deux cibles + les encombreurs).

    Les encombreurs sont pris a <=2 hex de la cible PAUVRE et a >2 hex de la RICHE : appauvrir l'une
    ne touche alors pas l'autre. Liste VIDE si aucun ecart n'est atteignable -- l'appelant DIT que le
    regime n'est pas armable, il n'invente pas de verdict.
    """
    import hexgeo
    lst = sorted(walk)
    d = {}
    for a in lst:
        for b in lst:
            d[(a, b)] = hexgeo.distance(coord[a], coord[b])
    prox2 = {t: [o for o in lst if o != t and d[(t, o)] <= 2] for t in lst}

    out = []
    for pivot in lst:
        voisins = prox2[pivot]
        for pauvre in voisins:
            for riche in voisins:
                if riche == pauvre:
                    continue
                cand = [o for o in prox2[pauvre]
                        if o not in (riche, pivot) and d[(riche, o)] > 2]
                enc = cand[:n_encombreurs]
                occ = {pivot, pauvre, riche} | set(enc)
                lp = len([o for o in prox2[pauvre] if o not in occ])
                lr = len([o for o in prox2[riche] if o not in occ])
                ecart = min(lr, plafond) - min(lp, plafond)
                if ecart >= 1:
                    out.append({"pivot": pivot, "pauvre": pauvre, "riche": riche, "enc": enc,
                                "libres_pauvre": lp, "libres_riche": lr, "ecart": ecart})
    out.sort(key=lambda c: (-c["ecart"], len(c["enc"]), c["pivot"], c["pauvre"]))
    return out[:k]


def _pose(rpc, byid, coord, walk, cfg, caster, cible_pauvre, cible_riche, encombreurs, autres):
    """Pose la configuration DEPUIS UN PLATEAU DEGAGE.

    ⚠ Un `move` vers une tuile OCCUPEE echoue EN SILENCE : poser sans degager d'abord fabrique une
    geometrie qu'on croit avoir et qu'on n'a pas (mesure de ce probe -- un << echange >> de deux
    cibles s'est revele un NO-OP integral, et les etiquettes imprimees mentaient). On PARQUE donc
    tout le monde loin d'abord, puis on place.
    """
    import hexgeo
    def move(uid, tid):
        c = byid[tid]
        return rpc("applyAction", {"runnerId": rid_courant[0], "action": {
            "kind": "move", "unitId": int(uid), "to": {"col": c["col"], "row": c["row"]}}}, 40)

    zone = {cfg["pivot"], cfg["pauvre"], cfg["riche"]} | set(cfg["enc"])
    parking = [t for t in sorted(walk)
               if t not in zone
               and min(hexgeo.distance(coord[t], coord[z]) for z in zone) >= 4]
    toutes = [caster, cible_pauvre, cible_riche] + list(encombreurs) + list(autres)
    if len(parking) < len(toutes):
        return "pas assez de tuiles de parking (%d pour %d unites)" % (len(parking), len(toutes))
    for u, t in zip(toutes, parking):
        move(u, t)
    move(caster, cfg["pivot"])
    move(cible_pauvre, cfg["pauvre"])
    move(cible_riche, cfg["riche"])
    for u, t in zip(encombreurs, cfg["enc"]):
        move(u, t)
    return None


rid_courant = [None]              # le `rid` courant, pose par `confronte_cultdemagogue`


def _ordre_des_cibles(rpc, rid, uid):
    """L'ORDRE dans lequel le selecteur natif enumere les cibles eligibles de 1179.

    C'est LUI qui decide l'argmax du contre-factuel << ancre CASTER >> : ce terme y etant CONSTANT
    sur les cibles et le terme 2 nul (aucun decoy/neophyte pose), toutes les utilites sont EGALES, et
    `IdunBattle.AI.BucketSystem.Bucket<...>$$AddAction` ne remplace que sur amelioration STRICTE --
    la PREMIERE enumeree gagne. Cet ordre n'est PAS celui des identifiants (mesure : `[79, 83, 77,
    81]`), donc il se LIT, il ne se suppose pas."""
    at = rpc("abilityTargets", {"runnerId": rid, "unitId": int(uid),
                                "abilityType": ABILITY_1179}, 60) or {}
    for u in (at.get("units") or []):
        for a in (u.get("abilities") or []):
            if a.get("abilityId") != ABILITY_1179:
                continue
            return [int(t["targetId"]) for t in (a.get("targets") or [])
                    if t.get("kind") == "unit" and t.get("targetId") is not None]
    return []


def _action_native(rpc, rid, uid):
    """L'action que l'IA NATIVE propose pour `uid` sur l'etat courant (`aiDryRunAllUnits`).

    ⚠ La ligne porte `proposed` (une liste de messages), PAS `action.messages` -- mesure de ce
    probe : lire la mauvaise clef rend `None` et se lirait comme << le natif ne propose pas 1179 >>,
    c'est-a-dire un REGIME NON ARME qui n'existe pas."""
    dry = rpc("aiDryRunAllUnits", {"runnerId": rid}, 180) or {}
    for row in (dry.get("units") or []):
        if int(row.get("unitId", -1)) != int(uid):
            continue
        for m in (row.get("proposed") or []):
            if m.get("cls") == "ActiveAbilityMessage":
                return {"ability": m.get("abilityType"), "target": m.get("targetId")}
        return {"ability": None, "target": None,
                "autre": [m.get("cls") for m in (row.get("proposed") or [])]}
    return None


def _decisions_du_port(sid, rid, rpc, uid):
    """(port TEL QUEL = ancre CIBLE, contre-factuel = ancre CASTER), par le chemin REEL du moteur."""
    import engine_validate as EV
    from engine import weights as W
    from engine.playbook import bespoke as BSP

    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 32, "allAbilities": True}, 180)
    mov = rpc("aiMovableTiles", {"runnerId": rid}, 60)
    mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
    wt = W.load()
    port_cible = EV.engine_decide(sid, rid, dv, mov_by_unit, int(uid), wt)

    vrai = BSP.CultDemagoguePlaybook._free_tiles_around

    def ancre_caster(self, ctx, center):
        """L'etat d'AVANT #957 : le terme 1 compte les tuiles libres autour du CASTER."""
        me = ctx.me or {}
        p = me.get("pos") or {}
        origine = (p.get("col"), p.get("row")) if p.get("col") is not None else None
        return vrai(self, ctx, origine)

    BSP.CultDemagoguePlaybook._free_tiles_around = ancre_caster
    try:
        port_caster = EV.engine_decide(sid, rid, dv, mov_by_unit, int(uid), wt)
    finally:
        BSP.CultDemagoguePlaybook._free_tiles_around = vrai
    return port_cible, port_caster


def confronte_cultdemagogue(rpc, rid, sid) -> dict:
    """Cherche un montage ou les DEUX ancres designent des cibles DIFFERENTES, puis demande au natif.

    Le regime discriminant exige DEUX choses simultanement, et la seconde ne se decide pas depuis le
    plateau : (a) un ECART de tuiles libres entre les deux cibles, sous le plafond `nrOfSummons` ;
    (b) que la cible PAUVRE soit la PREMIERE enumeree -- sans quoi l'ancre CASTER, qui retombe sur la
    premiere au tie, designe la MEME cible que l'ancre CIBLE et l'accord ne prouve rien. On pose donc
    les configurations par ecart decroissant jusqu'a en trouver une qui satisfait (b).
    """
    rid_courant[0] = rid
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        return {"ok": False, "raison": "boardGraph indispo"}
    byid = {t["id"]: t for t in bg["tiles"]}
    coord = {t["id"]: (t["col"], t["row"]) for t in bg["tiles"]}
    walk = {t["id"] for t in bg["tiles"] if t.get("walkable")}

    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    units = [u for u in (dv.get("units") or []) if u.get("alive")]
    me = next((u for u in units if u.get("visualId") == PRIMUS), None)
    if me is None:
        return {"ok": False, "raison": "porteur %s absent du build" % PRIMUS}
    ens = [u["id"] for u in units if u.get("owner") != me.get("owner")]
    amis = [u["id"] for u in units if u.get("owner") == me.get("owner") and u["id"] != me["id"]]
    if len(ens) < 2:
        return {"ok": False, "raison": "moins de 2 ennemis vivants"}

    plafond = _nr_of_summons(rpc, rid, me["id"])
    if plafond <= 0:
        return {"ok": False, "raison": "nrOfSummons NON MESURE (niveau d'ability illisible)"}
    # ⚠ Les encombreurs sont des ALLIES : un ennemi encombreur deviendrait lui-meme une cible
    # eligible et entrerait dans l'argmax, ce qui brouillerait le discriminant.
    cfgs = _configurations(coord, walk, plafond, len(amis))
    if not cfgs:
        return {"ok": False,
                "raison": "aucune configuration ne separe les deux termes 1 sous le plafond "
                          "nrOfSummons=%d avec %d encombreurs" % (plafond, len(amis))}

    essais = []
    for cfg in cfgs:
        for pauvre, riche in ((ens[0], ens[1]), (ens[1], ens[0])):
            autres = [e for e in ens if e not in (pauvre, riche)]
            err = _pose(rpc, byid, coord, walk, cfg, me["id"], pauvre, riche, amis, autres)
            if err:
                essais.append({"cfg": cfg["pivot"], "erreur": err})
                continue
            ordre = _ordre_des_cibles(rpc, rid, me["id"])
            essais.append({"pivot": cfg["pivot"], "ecart": cfg["ecart"], "ordre": ordre,
                           "pauvre": pauvre, "riche": riche})
            if not ordre or riche not in ordre:
                continue
            if ordre[0] != pauvre:
                continue
            port_cible, port_caster = _decisions_du_port(sid, rid, rpc, me["id"])
            if port_cible.get("target") == port_caster.get("target"):
                continue                      # pas encore discriminant : on continue de chercher
            natif = _action_native(rpc, rid, me["id"])
            return {"ok": True, "uid": me["id"], "plafond": plafond,
                    "geo": {"pauvre": pauvre, "riche": riche,
                            "libres_pauvre": cfg["libres_pauvre"],
                            "libres_riche": cfg["libres_riche"],
                            "ecart": cfg["ecart"], "encombreurs": len(cfg["enc"]),
                            "ordre": ordre},
                    "natif": natif, "port_cible": port_cible, "port_caster": port_caster,
                    "essais": len(essais)}
    return {"ok": False,
            "raison": "aucun des %d montages joues n'arme le regime (il faut a la fois un ecart de "
                      "tuiles libres ET que la cible PAUVRE soit enumeree la premiere). Derniers "
                      "essais : %s" % (len(essais), essais[-3:])}


def verdict_cultdemagogue(res: dict) -> int:
    if not res.get("ok"):
        print("NON CONFRONTE :", res.get("raison"))
        return 2
    g, nat = res["geo"], res["natif"]
    pc, pk = res["port_cible"], res["port_caster"]
    print("caster=u%s  nrOfSummons(plafond)=%d  encombreurs=%d  montages joues=%d"
          % (res["uid"], res["plafond"], g["encombreurs"], res["essais"]))
    print("cible PAUVRE=u%s (%d tuiles libres <=2hex)  cible RICHE=u%s (%d)  ecart plafonne=%d"
          % (g["pauvre"], g["libres_pauvre"], g["riche"], g["libres_riche"], g["ecart"]))
    print("ordre d'enumeration natif :", g["ordre"], "(la PAUVRE est premiere)")
    print("natif        :", nat)
    print("port  ancre CIBLE  :", {k: pc.get(k) for k in ("kind", "ability", "target")})
    print("port  ancre CASTER :", {k: pk.get(k) for k in ("kind", "ability", "target")})

    if nat is None or int(nat.get("ability") or 0) != ABILITY_1179:
        print("REGIME NON ARME : le natif ne propose pas 1179 pour cette unite (%s) -- rien a "
              "confronter sur l'ancre" % (nat,))
        return 2
    if pc.get("ability") != ABILITY_1179:
        print("ECART DE VOIE : le port ne propose pas 1179 (%s) -- l'ancre n'est pas en cause"
              % ({k: pc.get(k) for k in ("kind", "ability", "target")}))
        return 1
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
        p_units, a_units = "%s,%s" % (PRIMUS, ALLIES_1179), ENEMIES_1179
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
