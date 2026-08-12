#!/usr/bin/env python
"""Probe #971 -- confrontation LIVE des trois faces DECISION de categorie SUMMON.

    1058 `Waaagh`             (`orksWarboss`, HERO)
    1145 `SporeMineLauncher`  (`tyranBiovore`, MACHINE OF WAR)
    1219 `IronkinSteeljack`   (`votanMemnyr`, HERO hors pool -> injection catalogue)

L'ORACLE, ET POURQUOI CELUI-LA
-------------------------------
`ncEvaluate` (#46) invoque la LEAF NATIVE `Evaluate(unit, UnitPosition, tiles)` du playbook --
c'est-a-dire EXACTEMENT `EvaluateNonComparable` sous son wrapper -- **par position**, et decode le
`Bucket` rendu : `util` (Fix64) + `action.targetLow` (l'id d'entite cible) + `action.ability`.
C'est la valeur que le natif ATTRIBUE, pas une preview : `aiPredict` ne repond pas pour un
NonComparable (les quatre `Make*Predictions` ne sont declarees que sur la branche Comparable --
`probe_350r3_noncomparable_oracle.py` etape 0).

La confrontation se fait donc PAR ETAGE, position par position :

    natif   : ncEvaluate.positions[i] = {pos, util, action.targetLow}
    port    : l'utilite de CETTE position, calculee par les helpers du playbook porte

et non pas seulement sur l'argmax global -- un argmax identique par accident masquerait une
formule fausse.

⚠ NON-DEGENERESCENCE : le probe REFUSE de conclure si le regime est vide (aucune position avec
bucket non vide) ou si toutes les positions rendent la MEME utilite (rien n'est departage). Il
sort alors `rc = 2` (NON CONFRONTE), jamais un vert.

Codes de retour : 0 = confronte et vert ; 1 = DESACCORD ; 2 = non confronte (montage/plateforme).

ASCII only (cp1252). Usage (depuis scripts/python) :
    python probe_971_summon_decision_faces.py --ability 1219
    python probe_971_summon_decision_faces.py --ability all --json
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parent.parent
sys.path.insert(0, str(PYDIR))

import hexgeo                                                        # noqa: E402
from rl_collect_batch import _resolve_session, _rpc                  # noqa: E402

#: `visualId` du porteur, roster adverse, et si le porteur exige une injection catalogue.
CAS = {
    1058: {"name": "Waaagh", "carrier": "orksWarboss", "inject": False, "mow": False,
           "p_units": "orksWarboss,orksNob,orksRuntherd,orksBigMek",
           "a_units": "ultraTitus,ultraApothecary,necroWarden"},
    # La MoW est mise du cote ADVERSE : c'est `aiPlayByUnit` qui joue son tour, donc la tuile ou
    # le spore mine apparait EST la decision native observee (cf. `confront_mow`).
    1145: {"name": "SporeMineLauncher", "carrier": "tyranBiovore", "inject": False, "mow": True,
           "p_units": "ultraTitus,ultraApothecary,necroWarden",
           "a_units": "tyranNeurothrope,tyranParasite"},
    # `votanChampion` n'est PAS dans le pool : les allies sont pris DANS le pool
    # (`rl_duel build --list-pool`), seul le PORTEUR est injecte.
    1219: {"name": "IronkinSteeljack", "carrier": "votanMemnyr", "inject": True, "mow": False,
           "p_units": "votanMemnyr,orksNob",
           "a_units": "ultraTitus,ultraApothecary,necroWarden"},
}


def _sid():
    return _resolve_session()


def rpc(sid, method, body, timeout=60):
    r = _rpc(sid, method, [body], timeout=timeout)
    return r.get("result", r) if isinstance(r, dict) else r


def build(cas, seed, board):
    """`rl_duel build`, avec injection catalogue quand le porteur est hors pool."""
    state = ROOT / "logs" / "runners" / f"st-971-{uuid.uuid4().hex[:8]}.json"
    state.parent.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", seed, "--board", board,
           "--state-file", str(state), "--p-units", cas["p_units"],
           "--a-units", cas["a_units"]]
    if cas["mow"]:
        cmd += ["--a-mow", cas["carrier"]]
        # MUNITIONS : sans `MachineOfWarAmmo`, la MoW se deploie mais ne CASTE JAMAIS -- le tour
        # d'IA ne propose alors rien, et un « le natif ne propose pas 1145 » se lirait a tort
        # comme un verdict. Meme levier que `test_storm_speeder_live` / `probe_129`.
        import rl_duel as RD
        bc = RD._load_seed_bc()
        for _pid, pl in ((bc.get("Player") or {}).get("Players") or {}).items():
            if isinstance(pl, dict) and pl.get("PlayerType") != 2:      # Environment exclu
                pl["MachineOfWarAmmo"] = 5
        bcf = ROOT / "logs" / "runners" / f"bc-971-{uuid.uuid4().hex[:8]}.json"
        bcf.parent.mkdir(parents=True, exist_ok=True)
        bcf.write_text(json.dumps(bc), encoding="utf-8")
        cmd += ["--seed-bc", str(bcf)]
    if cas["inject"]:
        # Porteur HORS POOL -> BC augmente EN MEMOIRE (meme recette que
        # `tests/engine/runner/test_ironkin_steeljack_live.py::_build_votan`, case-92 §6).
        import catalog_inject as CI
        import rl_duel as RD
        seed_bc = RD._load_seed_bc()
        bc, _added, _ab, _marker = CI.augment(seed_bc, [cas["carrier"]], rank=17)
        bcf = ROOT / "logs" / "runners" / f"bc-971-{uuid.uuid4().hex[:8]}.json"
        bcf.write_text(json.dumps(bc), encoding="utf-8")
        cmd += ["--seed-bc", str(bcf)]
    p = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state.exists():
        print("BUILD KO:", (p.stderr or p.stdout or "")[-800:])
        return None, state
    return json.loads(state.read_text())["runnerId"], state


def find_caster(sid, rid, cas):
    """Id d'entite du porteur -- unite de `dv.units` ou MoW de `dv.mows` (`casterId`)."""
    dv = rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 180)
    if cas["mow"]:
        m = next((x for x in (dv.get("mows") or [])
                  if x.get("visualId") == cas["carrier"]), None)
        return (m or {}).get("casterId"), dv
    u = next((x for x in (dv.get("units") or [])
              if x.get("visualId") == cas["carrier"] and x.get("alive")), None)
    return (u or {}).get("id"), dv


def native_nc(sid, rid, uid, aid):
    """`ncEvaluate` : le bucket natif PAR POSITION (util + cible + ability)."""
    return rpc(sid, "ncEvaluate", {"runnerId": rid, "unitId": uid, "abilityType": aid,
                                   "sweep": True}, 180)


def native_dryrun(sid, rid, uid):
    """`aiDryRunAllUnits` : le TOUR D'IA OBSERVE (la decision reelle, pas une preview).

    C'est le SEUL oracle disponible quand le caster est une MACHINE OF WAR : `ncEvaluate` resout
    son unite par `forEachEntity(..., EntityType.Unit, ...)` et une MoW n'y est pas -- il rend
    alors « unit N not found ». Corriger ce point exigerait de LIVRER un hook, donc une fenetre de
    reinject (residu `#971-r3`). `aiDryRunAllUnits`, lui, couvre bien le caster MoW (meme voie que
    `probe_129_thrice_blessed_decision.py`)."""
    dry = rpc(sid, "aiDryRunAllUnits", {"runnerId": rid}, 240)
    print("   dryRun couvre : %s"
          % [(u.get("unitId"), [m.get("abilityType") for m in (u.get("proposed") or [])])
             for u in (dry.get("units") or [])])
    nat = next((u for u in (dry.get("units") or []) if u.get("unitId") == uid), None)
    return [{"cls": m.get("cls"), "ability": m.get("abilityType"), "target": m.get("targetId"),
             "to": m.get("to")} for m in ((nat or {}).get("proposed") or [])]


def playbook_gates(sid, rid, uid, aid):
    """Slots 0 (`get_Priority`) et 4 (`ShouldEvaluate`) INVOQUES sur la vtable du playbook.

    C'est la SEULE voie qui tranche un slot 4 FOLDE par ICF : `frida/methods.tsv` est indexee par
    ADRESSE et ne garde qu'un proprietaire par corps, donc l'absence d'un
    `<Classe>$$ShouldEvaluate` n'y prouve RIEN (cf. CLAUDE.md)."""
    sl = rpc(sid, "pbSlots", {"runnerId": rid, "abilityType": aid, "maxSlots": 7}, 90)
    itf = next((i for i in (sl.get("interfaces") or []) if i.get("slots")), None)
    names = [(x.get("slot"), x.get("name"), x.get("params"))
             for x in ((itf or {}).get("slots") or [])]
    g0 = rpc(sid, "pbGate", {"runnerId": rid, "unitId": uid, "abilityType": aid,
                             "itf": "Playbook", "slot": 0, "args": []}, 60)
    g4 = rpc(sid, "pbGate", {"runnerId": rid, "unitId": uid, "abilityType": aid,
                             "itf": "Playbook", "slot": 4, "args": ["unit"]}, 60)
    return {"playbookClass": sl.get("playbookClass"), "slots": names,
            "slot0": g0, "slot4": g4}


def port_ctx(sid, rid, uid, mow: bool):
    """NCContext bati sur l'etat LIVE.

    Voie NORMALE (`engine.ai.context.build`) pour une UNITE. Pour une MACHINE OF WAR le driver
    offline n'a pas d'entree (`state_bridge._dv_units` exclut les MoW de `decisionView.units`) :
    on monte alors le contexte a la main avec les canaux dont les feuilles ont besoin -- meme
    parti-pris que `probe_129_thrice_blessed_decision.py`, et il est NOMME, pas silencieux."""
    from engine.playbook import noncomparable as PB
    dv = rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    bg = rpc(sid, "boardGraph", {"runnerId": rid}, 90)
    tiles = bg.get("tiles") or []
    walk = {(t["col"], t["row"]): bool(t.get("walkable")) for t in tiles}
    elev = {(t["col"], t["row"]): t.get("elevation") for t in tiles}
    tid = {(t["col"], t["row"]): t.get("id") for t in tiles if t.get("id") is not None}
    neigh = {}
    by_id = {t.get("id"): (t["col"], t["row"]) for t in tiles if t.get("id") is not None}
    for t in tiles:
        ns = [by_id.get(n) for n in (t.get("neighbours") or [])]
        neigh[(t["col"], t["row"])] = [n for n in ns if n is not None]
    if not mow:
        from engine import weights
        from engine.ai import context as _ai_ctx
        from engine.playbook import scene as _scene
        mov = rpc(sid, "aiMovableTiles", {"runnerId": rid}, 90)
        mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
        predictor = _scene.build_predictor(lambda m, b, t: rpc(sid, m, b, t), rid)
        c = _ai_ctx.build(lambda m, b, t: rpc(sid, m, b, t), rid, dv, mov_by_unit, uid,
                          weights.load(), predictor)
        return PB.NCContext(
            uid=c.uid, origin=c.origin, reach_nc=c.reach_nc, epos=c.epos, fpos=c.fpos,
            enemies=c.enemies, neigh_by_pos=c.neigh_by_pos, walkable_by_pos=c.walkable_by_pos,
            plan=c.plans.get(c.uid) or {}, plans=c.plans, hp_cur_by_id=c.hp_cur_by_id,
            elev_by_pos=c.elev_by_pos, ability_targets=c.ability_targets, wt=c.wt,
            is_temporary_by_pos=c.is_temporary_by_pos, effects_by_pos=c.effects_by_pos,
            obs_units=c.obs_units, tile_id_by_pos=c.tile_id_by_pos,
            active_levels=c.active_ability_levels, ability_config=c.heal_config,
            units=c.units, cast_from_tiles=c.cast_from_tiles, scene=c.scene), dv
    mow_e = next((m for m in (dv.get("mows") or []) if m.get("casterId") == uid), None)
    owner = (mow_e or {}).get("owner")
    units = [u for u in (dv.get("units") or []) if u.get("alive")]
    epos = [(u["pos"]["col"], u["pos"]["row"]) for u in units
            if u.get("owner") != owner and u.get("pos")]
    fpos = [(u["pos"]["col"], u["pos"]["row"]) for u in units
            if u.get("owner") == owner and u.get("pos")]
    return PB.NCContext(
        uid=uid, origin=None, reach_nc=[], epos=epos, fpos=fpos, plan={}, hp_cur_by_id={},
        ability_targets=lambda u, a: rpc(sid, "abilityTargets",
                                         {"runnerId": rid, "unitId": u, "abilityType": a}, 120),
        units=units, walkable_by_pos=walk, elev_by_pos=elev, neigh_by_pos=neigh,
        tile_id_by_pos=tid), dv


def port_at_position(pb, ctx, pos):
    """Ce que le PORT attribue A CETTE POSITION -- `(utilite, cible)` ou `(None, None)`.

    On restreint le sweep du port a la seule position `pos` (`reach_nc = [pos]`) et on relance
    `generate_candidates` : c'est EXACTEMENT ce que le natif calcule dans un appel
    `EvaluateNonComparable(caster, <cette position>)`, donc c'est le bon grain de comparaison.
    Comparer les seuls ARGMAX GLOBAUX laisserait passer une formule fausse qui se trouve maximiser
    la meme position -- la decomposition par etage est ce qui l'interdit."""
    import dataclasses
    sub = dataclasses.replace(ctx, reach_nc=[pos])
    c = pb.generate_candidates(sub)
    if not c:
        return None, None
    return c[0].get("pred"), c[0].get("target")


def confront(sid, rid, uid, aid, cas, as_json=False):
    from engine.playbook import noncomparable as PB
    gates = playbook_gates(sid, rid, uid, aid)
    nat = native_nc(sid, rid, uid, aid)
    ctx, _dv = port_ctx(sid, rid, uid, cas["mow"])
    pb = PB.PLAYBOOKS[aid]
    cands = pb.generate_candidates(ctx)
    positions = [p for p in (nat.get("positions") or []) if p.get("util") is not None]
    rec = {"ability": aid, "name": cas["name"], "uid": uid, "gates": gates,
           "nativePositions": nat.get("positions"), "portCandidates": cands,
           "playbookClass": gates.get("playbookClass")}
    print("[%d %s] u%s playbook=%s evalName=%s"
          % (aid, cas["name"], uid, gates.get("playbookClass"), nat.get("evalName")))
    print("   slots 0..6 : %s" % (gates.get("slots"),))
    print("   slot0(get_Priority)=%s  slot4(ShouldEvaluate)=%s"
          % (json.dumps(gates.get("slot0"))[:160], json.dumps(gates.get("slot4"))[:160]))
    for p in (nat.get("positions") or []):
        print("   natif pos=%s cur=%s hvt=%s util=%s tgt=%s"
              % (p.get("pos"), p.get("cur"), p.get("hvt"), p.get("util"),
                 (p.get("action") or {}).get("targetLow")))
    print("   PORT should_evaluate=%s candidats=%s"
          % (pb.should_evaluate(ctx), cands))
    if not positions:
        # Repli sur le TOUR D'IA OBSERVE -- seul oracle disponible pour un caster MoW.
        dry = native_dryrun(sid, rid, uid)
        rec["dryRun"] = dry
        casts = [m for m in dry if m.get("ability") == aid]
        print("   ncEvaluate MUET (%s) -> repli oracle TOUR D'IA OBSERVE : %s"
              % (nat.get("error") or "aucune position", dry))
        if not casts:
            print("   NON CONFRONTE : le natif ne propose PAS %d ce tour (une autre action gagne)"
                  % aid)
            rec["verdict"] = "NON_CONFRONTE"
            return rec, 2
        ok = bool(cands) and cands[0].get("target") == casts[0].get("target")
        rec["verdict"] = "OK" if ok else "DESACCORD"
        print("   VERDICT (tour observe) : natif tgt=%s port tgt=%s -> %s"
              % (casts[0].get("target"), (cands[0].get("target") if cands else None),
                 rec["verdict"]))
        if as_json:
            print(json.dumps(rec, default=str))
        return rec, (0 if ok else 1)
    # ETAGE 1 -- l'utilite, POSITION PAR POSITION.
    ecarts = []
    nat_cls: dict = {}          # ptr natif -> [positions]
    port_cls: dict = {}         # cible portee -> [positions]
    for p in positions:
        pos = tuple(p.get("pos"))
        u, tgt = port_at_position(pb, ctx, pos)
        ok_u = (u is not None) and abs(u - p["util"]) < 1e-6
        pos_of_tile = {v: k for k, v in (ctx.tile_id_by_pos or {}).items()}
        print("   ETAGE pos=%s natif=%s port=%s tuile-portee=%s%s  %s"
              % (pos, p.get("util"), u, tgt, pos_of_tile.get(tgt, ""),
                 "OK" if ok_u else "ECART"))
        rec.setdefault("etages", []).append(
            {"pos": list(pos), "natif": p.get("util"), "port": u, "ok": ok_u})
        if not ok_u:
            ecarts.append((pos, p.get("util"), u))
        nat_cls.setdefault((p.get("action") or {}).get("targetLow"), []).append(pos)
        port_cls.setdefault(tgt, []).append(pos)
    # ETAGE 2 -- la CIBLE. `ncEvaluate` rend `action+0x18` en U32 : sur ces playbooks c'est le bas
    # d'un POINTEUR d'entite, pas un `BEntityId` -- il n'est donc PAS comparable a l'id de tuile
    # que le port emet. Ce qui l'est, et qui est un invariant fort : la PARTITION des positions
    # induite par la cible. Deux positions ou le natif retient la MEME entite doivent etre deux
    # positions ou le port retient la MEME tuile, et reciproquement.
    nat_part = sorted(sorted(v) for v in nat_cls.values())
    port_part = sorted(sorted(v) for v in port_cls.values())
    same_part = nat_part == port_part
    print("   PARTITION des positions par cible : natif=%s" % (nat_part,))
    print("                                       port =%s  -> %s"
          % (port_part, "OK" if same_part else "ECART"))
    rec["partition"] = {"natif": nat_part, "port": port_part, "identique": same_part}
    # NON-DEGENERESCENCE : le montage doit DEPARTAGER.
    utils = {round(p["util"], 6) for p in positions}
    rec["utilsDistincts"] = sorted(utils)
    best = None                 # argmax natif = keep-first (position courante en tete, `>` strict)
    for p in positions:
        if best is None or p["util"] > best["util"]:
            best = p
    rec["nativeBest"] = {"pos": best.get("pos"), "util": best.get("util")}
    print("   natif BEST pos=%s util=%s | port to=%s pred=%s"
          % (best.get("pos"), best.get("util"),
             (cands[0].get("to") if cands else None),
             (cands[0].get("pred") if cands else None)))
    degenere = (len(utils) == 1 or len(positions) < 2 or len(nat_cls) < 2)
    if degenere:
        print("   NON CONFRONTE : le montage ne DEPARTAGE pas (%d position(s), %d utilite(s)"
              " distincte(s), %d cible(s) distincte(s))"
              % (len(positions), len(utils), len(nat_cls)))
        rec["verdict"] = "NON_CONFRONTE_DEGENERE"
        rec["degenere"] = True
        return rec, 2
    port_best_pos = (tuple(cands[0]["to"]) if (cands and cands[0].get("to"))
                     else (ctx.origin if cands else None))
    ok_argmax = bool(cands) and (list(port_best_pos or ()) == list(best.get("pos") or ()))
    ok = (not ecarts) and same_part and ok_argmax
    rec["verdict"] = "OK" if ok else "DESACCORD"
    print("   VERDICT : etages=%s partition=%s argmax=%s -> %s"
          % ("OK" if not ecarts else ("ECART %s" % (ecarts,)),
             "OK" if same_part else "ECART", "OK" if ok_argmax else "ECART", rec["verdict"]))
    if as_json:
        print(json.dumps(rec, default=str))
    return rec, (0 if ok else 1)


def confront_mow(sid, rid, uid, aid, cas, as_json=False):
    """Confrontation d'un caster MACHINE OF WAR -- oracle = le TOUR D'IA REELLEMENT JOUE.

    POURQUOI PAS `ncEvaluate` NI `aiDryRunAllUnits` : les deux resolvent leur unite parmi les
    `EntityType.Unit`, et une MoW n'en est pas une. MESURE : `ncEvaluate` rend « unit 83 not
    found », et `aiDryRunAllUnits` ne couvre que les DEUX unites de l'equipe (84, 86), jamais le
    caster MoW 83. Ce n'est pas un trou de montage : c'est une limite des deux capteurs, et la
    lever exige de LIVRER un hook -> fenetre de reinject, residu `#971-r3`.

    L'oracle retenu est donc le plus fort de tous : `aiPlayByUnit` joue le tour, et la TUILE OU LE
    SPORE MINE APPARAIT **EST** la cible que le natif a choisie. On la lit dans `observeBattle`
    (delta avant/apres), pas dans une preview."""
    from engine.playbook import noncomparable as PB
    summon_id = (__import__("gameconfig").ability(cas["name"]) or {}) \
        .get("constants", {}).get("unitId")
    ctx, dv = port_ctx(sid, rid, uid, True)
    mow_e = next((m for m in (dv.get("mows") or []) if m.get("casterId") == uid), None)
    print("   MoW=%s owner=%s pos=%s abilities=%s currentPlayer=%s"
          % ((mow_e or {}).get("visualId"), (mow_e or {}).get("owner"),
             (mow_e or {}).get("pos"),
             [(a.get("id"), a.get("usable"), a.get("hasAmmo"), a.get("cooldown"))
              for a in ((mow_e or {}).get("abilities") or [])],
             dv.get("currentPlayer")))
    pb = PB.PLAYBOOKS[aid]
    cands = pb.generate_candidates(ctx)
    pos_of_tile = {v: k for k, v in (ctx.tile_id_by_pos or {}).items()}
    port_tile = pos_of_tile.get(cands[0]["target"]) if cands else None
    print("   PORT candidats=%s -> tuile %s" % (cands, port_tile))
    ob0 = rpc(sid, "observeBattle", {"runnerId": rid}, 90)
    before = {u.get("entityId") or u.get("squadId") for u in (ob0.get("units") or [])}
    r = rpc(sid, "aiPlayByUnit", {"runnerId": rid, "maxTurns": 1, "maxActivations": 9999,
                                  "maxPump": 400, "captureEvents": False}, 300)
    print("   aiPlayByUnit ok=%s turns=%s stop=%s"
          % (r.get("ok"), r.get("turnsPlayed"), r.get("stopReason")))
    ob1 = rpc(sid, "observeBattle", {"runnerId": rid}, 90)
    news = [u for u in (ob1.get("units") or [])
            if (u.get("entityId") or u.get("squadId")) not in before
            and u.get("visualId") == summon_id]
    rec = {"ability": aid, "name": cas["name"], "uid": uid, "portCandidates": cands,
           "portTile": list(port_tile) if port_tile else None,
           "summonId": summon_id,
           "spawned": [{"visualId": u.get("visualId"), "pos": [u.get("col"), u.get("row")]}
                       for u in news]}
    print("   natif : %s spawn(s) de %s -> %s"
          % (len(news), summon_id, [(u.get("col"), u.get("row")) for u in news]))
    if not news:
        print("   NON CONFRONTE : le natif n'a pas caste %d ce tour (aucun %s apparu)"
              % (aid, summon_id))
        rec["verdict"] = "NON_CONFRONTE"
        if as_json:
            print(json.dumps(rec, default=str))
        return rec, 2
    nat_tile = (news[0].get("col"), news[0].get("row"))
    ok = (port_tile is not None) and tuple(port_tile) == nat_tile
    rec["verdict"] = "OK" if ok else "DESACCORD"
    print("   VERDICT (tour JOUE) : natif tuile=%s port tuile=%s -> %s"
          % (nat_tile, port_tile, rec["verdict"]))
    if as_json:
        print(json.dumps(rec, default=str))
    return rec, (0 if ok else 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ability", default="1219")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--seed", default="4242")
    ap.add_argument("--endturns", type=int, default=0)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()

    ids = [1058, 1145, 1219] if args.ability == "all" else [int(args.ability)]
    sid = _sid()
    rc = 0
    for aid in ids:
        cas = CAS[aid]
        rid, _state = build(cas, args.seed, args.board)
        if rid is None:
            print("[%d %s] NON CONFRONTE : build KO" % (aid, cas["name"]))
            rc = max(rc, 2)
            continue
        print("runner=%d ability=%d board=%s seed=%s" % (rid, aid, args.board, args.seed))
        try:
            for _ in range(args.endturns):
                rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            uid, _dv = find_caster(sid, rid, cas)
            if uid is None:
                print("[%d %s] NON CONFRONTE : porteur %s absent du deploiement"
                      % (aid, cas["name"], cas["carrier"]))
                rc = max(rc, 2)
                continue
            if cas["mow"]:
                _rec, r = confront_mow(sid, rid, uid, aid, cas, as_json=args.json)
            else:
                _rec, r = confront(sid, rid, uid, aid, cas, as_json=args.json)
            rc = max(rc, r)
        finally:
            if not args.keep:
                rpc(sid, "disposeRunner", {"runnerId": rid}, 60)
    return rc


if __name__ == "__main__":
    sys.exit(main())
