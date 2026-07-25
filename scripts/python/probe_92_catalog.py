#!/usr/bin/env python
"""probe_92_catalog -- CONFRONT LIVE du debloqueur « porteurs absents du seed BC » (#92 / #54).

Le mecanisme est `catalog_inject.py` (mirror de `Idun.Source.IdunBattle.View.BattleConfigBuilder$$GetUnitConfiguration`,
consomme par `IdunBattle.Core.Services.BattleQuery$$GetUnitConfig`). Ce probe le confronte au jeu, en
distinguant les TROIS etats qui ne se valent pas :

  (1) PRESENT  -- l'id passe `buildNormalizedBC` et apparait dans le pool spawnable ;
  (2) SPAWNE   -- l'unite est VIVANTE sur le plateau (`observeBattle` / `decisionView`) ;
  (3) AGIT     -- une de ses abilities CASTE (`applyAction`) avec un effet OBSERVABLE (spawn, degat,
                  effet pose, hp) mesure par delta d'etat live.

Plus un volet CONTROL qui valide le mecanisme lui-meme : pour une unite DEJA au catalogue, l'entree
SYNTHETISEE remplace l'entree CAPTUREE -> l'unite spawnee doit etre indiscernable (stats recalculees,
traits, abilities, level/multiplicateur). Si le control passe, une entree synthetisee vaut une entree
capturee, et donc l'injection n'introduit pas d'unite « approximative ».

Usage (depuis scripts/python, session Frida chaude) :
    python probe_92_catalog.py --phase control
    python probe_92_catalog.py --phase present
    python probe_92_catalog.py --phase spawn  --units votanMemnyr,votanBeserk,votanIronmaster,votanUthar
    python probe_92_catalog.py --phase act    --units votanMemnyr
    python probe_92_catalog.py --phase actmow --mow thousDaemonPrince --ability 1209
    python probe_92_catalog.py --phase all

ASCII only. Dispose SES runners (jamais ceux des autres).
"""
from __future__ import annotations

import argparse
import copy
import json
import sys

import catalog_inject as CI
import rl_collect_batch as R

BOARD_UNITS = "MC1_67"     # 5v5
BOARD_MOW = "C1_02"        # slot MachineOfWarPosition des deux cotes (cf. test_mow_caster_load_live)
SEED = 4242
RANK = 17
ENEMY = "ultraTitus"

_rids: list[int] = []


def rpc(sid, method, body, timeout=90):
    r = R._rpc(sid, method, [body], timeout=timeout)
    if isinstance(r, dict) and r.get("error"):
        raise RuntimeError(f"{method}: {r['error']}")
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def dispose(sid, rid):
    try:
        R._rpc(sid, "disposeRunner", [{"runnerId": rid}], timeout=20)
    except Exception:
        pass
    if rid in _rids:
        _rids.remove(rid)


def _placement(bc, p_units, near_enemy):
    """Tuiles de deploiement des unites joueur.

    `near_enemy` : on DEPLACE le camp joueur au contact du camp IA (couronne autour du 1er spawn
    twpi=1, tuiles libres) au lieu de subir la geometrie de spawn -- sans quoi les 8-10 hexes qui
    separent les deux coins de MC1_67 rendent toute ability « 0 cible legale » et l'etat (3) est
    intestable."""
    spawns = R._spawn_points_by_twpi(bc)
    if not near_enemy:
        pts = spawns.get(0) or []
        if len(pts) < len(p_units):
            raise RuntimeError(f"{len(pts)} spawns joueur < {len(p_units)} units")
        return [(int(pts[i][0]), int(pts[i][1])) for i in range(len(p_units))]
    import hexgeo
    epts = [tuple(p) for p in (spawns.get(1) or [])]
    if not epts:
        raise RuntimeError("aucun spawn adverse")
    board = bc.get("Board") or {}
    w, h = int(board.get("Width") or 0), int(board.get("Height") or 0)
    # On n'exclut QUE la tuile ou l'IA se deploie en premier : les autres points de spawn adverses
    # sont les seules tuiles ADJACENTES a l'IA (les voisines hors-groupe sont a distance 2), et le
    # groupe adverse en compte 5 pour 1 unite -> le deploiement IA retombe sur une tuile libre.
    taken = {epts[0]}
    cands = [(c, r) for c, r in hexgeo.disk(epts[0][0], epts[0][1], 3)
             if (c, r) not in taken and 0 <= c < w and 0 <= r < h]
    cands.sort(key=lambda p: hexgeo.distance(p, epts[0]))    # les plus proches d'abord
    out = cands[:len(p_units)]
    if len(out) < len(p_units):
        raise RuntimeError("pas assez de tuiles libres au contact de l'IA")
    return out


def build(sid, bc_units_extra, p_units, a_units=(ENEMY,), p_mow=None, a_mow=None,
          board=BOARD_UNITS, seed_bc=None, near_enemy=False):
    """Runner isole depuis un seed BC AUGMENTE. Rend (runnerId, pool, pool_mow, template)."""
    seed = seed_bc if seed_bc is not None else R._load_seed_bc()
    bc0, added, added_ab, unresolved = CI.augment(seed, bc_units_extra, rank=RANK)
    if added_ab or unresolved:
        print(f"  [inject] units={added} abilities={added_ab} non-derivables={unresolved}")
    board_dump = R._load_board_dump(board)
    template, pool, pool_mow = R._normalize_and_extract_pool(sid, bc0, RANK, board_dump=board_dump)
    bc = copy.deepcopy(template)
    R._patch_predefined_units(bc, list(a_units))
    R._patch_predefined_machines(bc, p_mow, a_mow)
    pos = _placement(bc, p_units, near_enemy)
    player_units = [{"unitId": u, "playerId": R.PLAYER_ID_HUMAN,
                     "col": pos[i][0], "row": pos[i][1]}
                    for i, u in enumerate(p_units)]
    resp = R._rpc(sid, "initAndStart",
                  [{"configJson": json.dumps(bc), "seed": SEED, "playerUnits": player_units}],
                  timeout=60)
    rid = (resp.get("result") or {}).get("runnerId")
    if rid is None:
        raise RuntimeError(f"initAndStart KO: {resp.get('error') or resp}")
    _rids.append(rid)
    return rid, pool, pool_mow, added


def unit_rows(dec, visual_id):
    return [u for u in (dec.get("units") or []) if u.get("visualId") == visual_id]


def profile_live(sid, rid, visual_id) -> dict:
    """Signature LIVE complete d'une unite : stats de combat (`combatSnapshot`), identite +
    multiplicateurs (`unitConfig`), abilities + AbilityState, effets poses au deploiement
    (`decisionView` -- c'est la SONDE des traits : `Ambush` pose Ambush_CanResurrect 1358),
    et hp/armure (`observeBattle`). Tout ce qui vient du CATALOGUE finit ici."""
    dec = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True})
    ob = rpc(sid, "observeBattle", {"runnerId": rid}, 40)
    cs = rpc(sid, "combatSnapshot", {"runnerId": rid}, 60)
    du = next((u for u in (dec.get("units") or []) if u.get("visualId") == visual_id), None)
    ou = next((u for u in (ob.get("units") or []) if u.get("visualId") == visual_id), None)
    cu = next((u for u in (cs.get("units") or [])
               if (u.get("unitConfig") or {}).get("visualId") == visual_id), None)
    if du is None or ou is None or cu is None:
        return {"MISSING": {"decisionView": du is None, "observeBattle": ou is None,
                            "combatSnapshot": cu is None}}
    return {
        "visualId": visual_id,
        "stats": cu.get("stats"),
        "healthMax": cu.get("healthMax"),
        "unitConfig": cu.get("unitConfig"),
        "abilityStates": sorted(json.dumps(a, sort_keys=True)
                                for a in (cu.get("abilityStates") or [])),
        "abilities": sorted(json.dumps(a, sort_keys=True) for a in (du.get("abilities") or [])),
        "effects": sorted(json.dumps({k: v for k, v in e.items() if k != "effectId"},
                                     sort_keys=True) for e in (du.get("effects") or [])),
        "obs": {k: ou.get(k) for k in ("hp", "hpMax", "armor", "col", "row", "teamId")},
    }


# --------------------------------------------------------------------- CONTROL

def phase_control(sid, carrier="genesBiophagus"):
    """Entree SYNTHETISEE vs entree CAPTUREE pour la MEME unite, meme seed/board/roster."""
    print(f"\n=== CONTROL : entree synthetisee vs capturee ({carrier}) ===")
    seed = R._load_seed_bc()
    patched = copy.deepcopy(seed)
    idx = next(i for i, u in enumerate(patched["Units"]) if u.get("Id") == carrier)
    real_entry = patched["Units"][idx]
    synth_entry = CI.synthesize(carrier, rank=RANK)
    # on GARDE le multiplicateur capture pour isoler la question « le catalogue synthetise
    # decrit-il la meme unite » (le multiplicateur est un choix documente, teste a part).
    synth_entry["AbilityVariablesMultiplierPercentage"] = \
        real_entry["AbilityVariablesMultiplierPercentage"]
    patched["Units"][idx] = synth_entry

    out = {}
    for tag, s in (("capture", seed), ("synth", patched)):
        rid, _pool, _pm, _ = build(sid, [], [carrier, "ultraTitus"], seed_bc=s)
        try:
            out[tag] = profile_live(sid, rid, carrier)
            print(f"  [{tag}] runner={rid} -> {json.dumps(out[tag])}")
        finally:
            dispose(sid, rid)
    same = out.get("capture") == out.get("synth")
    print(f"  VERDICT CONTROL: {'IDENTIQUE' if same else 'DIVERGENT'}")
    if not same:
        a_, b_ = out.get("capture") or {}, out.get("synth") or {}
        for k in sorted(set(a_) | set(b_)):
            if a_.get(k) != b_.get(k):
                print(f"    DIFF {k}: capture={json.dumps(a_.get(k))} synth={json.dumps(b_.get(k))}")
    return same


# --------------------------------------------------------------------- (1) PRESENT

def phase_present(sid):
    """Les 17 unites lineup hors catalogue passent-elles la normalisation native ?"""
    print("\n=== (1) PRESENT : normalisation des porteurs injectes ===")
    seed = R._load_seed_bc()
    miss = CI.missing_from_seed_bc(seed)
    print(f"  {len(miss)} unites lineup hors catalogue: {miss}")
    bc0, added, added_ab, unresolved = CI.augment(seed, miss, rank=RANK)
    print(f"  configs d'ability injectees ({len(added_ab)}): {added_ab}")
    print(f"  traits/configs NON derivables (internes moteur): {unresolved}")
    board_dump = R._load_board_dump(BOARD_UNITS)
    _t, pool, pool_mow = R._normalize_and_extract_pool(sid, bc0, RANK, board_dump=board_dump)
    ok, ko = [], []
    for uid in miss:
        (ok if (uid in pool or uid in pool_mow) else ko).append(
            f"{uid}{'(MoW)' if uid in pool_mow else ''}")
    print(f"  PRESENT au pool : {len(ok)}/{len(miss)} -> {ok}")
    if ko:
        print(f"  ABSENTS du pool : {ko}")
    return ok, ko


# --------------------------------------------------------------------- (2)+(3) unites

def phase_spawn_and_act(sid, units, do_act=True):
    """(2) spawn + (3) cast pour des porteurs REGULIERS (heros).

    UN runner PAR porteur quand on caste : un cast qui faute cote natif laisse le runner dans un
    etat ou les porteurs suivants n'ont plus de cible legale -> verdicts croises et faux negatifs.
    """
    if do_act:
        out = {}
        for uid in units:
            out.update(phase_spawn_and_act(sid, [uid], do_act=None))
        return out
    do_act = do_act is None
    print(f"\n=== (2)/(3) SPAWN{' + CAST' if do_act else ''} : {units} ===")
    rid, pool, _pm, added = build(sid, units, list(units), near_enemy=do_act)
    verdicts = {}
    try:
        dec = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True})
        ob = rpc(sid, "observeBattle", {"runnerId": rid}, 40)
        alive = {u.get("visualId") for u in (ob.get("units") or []) if not u.get("isDead")}
        for uid in units:
            rows = unit_rows(dec, uid)
            spawned = uid in alive and bool(rows)
            verdicts[uid] = {"spawned": spawned, "acted": False, "detail": ""}
            if not spawned:
                print(f"  [{uid}] SPAWN KO (alive={uid in alive}, decisionView rows={len(rows)})")
                continue
            u = rows[0]
            print(f"  [{uid}] SPAWNE id={u.get('id')} hp={u.get('hp')} pos={u.get('pos')} "
                  f"abilities={[(a.get('id'), a.get('kind'), a.get('level'), a.get('multiplier')) for a in (u.get('abilities') or [])]} "
                  f"effects={[(e.get('effectType'), e.get('name')) for e in (u.get('effects') or [])]}")
            if not do_act:
                continue
            res = _try_cast(sid, rid, u)
            verdicts[uid].update(res)
    finally:
        dispose(sid, rid)
    return verdicts


def _state_footprint(sid, rid):
    """Empreinte live : unites vivantes + hp + effets par entite."""
    dec = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True})
    ob = rpc(sid, "observeBattle", {"runnerId": rid}, 40)
    units = {u.get("squadId"): (u.get("visualId"), u.get("hp"), bool(u.get("isDead")))
             for u in (ob.get("units") or [])}
    effs = {}
    rows = [(u.get("id"), u) for u in (dec.get("units") or [])]
    rows += [(m.get("casterId"), m) for m in (dec.get("mows") or [])]
    for key, u in rows:
        if key is None:
            continue
        e = {int(x["effectType"]): x.get("remaining") for x in (u.get("effects") or [])
             if x.get("effectType") is not None}
        if e:
            effs[int(key)] = e
    return {"units": units, "effects": effs}


def _fp_delta(before, after):
    new_units = {k: v for k, v in after["units"].items() if k not in before["units"]}
    hp_delta = {k: (before["units"][k][1], v[1]) for k, v in after["units"].items()
                if k in before["units"] and before["units"][k][1] != v[1]}
    death = {k: v[0] for k, v in after["units"].items()
             if k in before["units"] and v[2] and not before["units"][k][2]}
    new_eff = {}
    for k, e in after["effects"].items():
        add = {t: r for t, r in e.items() if t not in (before["effects"].get(k) or {})}
        if add:
            new_eff[k] = add
    return {"newUnits": {k: v[0] for k, v in new_units.items()},
            "hpDelta": hp_delta, "deaths": death, "newEffects": new_eff}


def _pick_target(tgts, caster_pos):
    """Cible parmi les LEGALES. Pour une ability TILE-target, `abilityTargets` rend l'ensemble
    castable du board (25 tuiles) alors que le behaviour de SUMMON exige une tuile ADJACENTE au
    caster : prendre `tgts[0]` donne un cast `ok:true` / `mutated:false` / `spawned:0` -- un
    FAUX NEGATIF qui se lit « le summon ne marche pas en headless ». On privilegie donc la tuile
    adjacente au caster."""
    units = [t for t in tgts if t.get("kind") == "unit"]
    if units:
        return units[0]
    tiles = [t for t in tgts if t.get("kind") == "tile"]
    if tiles and caster_pos:
        import hexgeo
        cp = (caster_pos.get("col"), caster_pos.get("row"))
        adj = [t for t in tiles
               if hexgeo.distance((t["tile"]["col"], t["tile"]["row"]), cp) == 1]
        if adj:
            return adj[0]
    return tgts[0]


def _try_cast(sid, rid, caster_row, ability=None):
    """Caste la 1re ability castable du porteur ; rend {acted, detail}."""
    cid = caster_row.get("id") if caster_row.get("casterId") is None else caster_row["casterId"]
    # decisionView.units[].abilities[] porte `id` ; decisionView.mows[] peut porter `abilityType`.
    # On tente les ACTIVES d'abord (la signature du porteur), l'attaque normale ensuite.
    rows = sorted((a for a in (caster_row.get("abilities") or [])),
                  key=lambda a: 0 if a.get("kind") == "active" else 1)
    abilities = [a.get("id") if a.get("id") is not None else a.get("abilityType") for a in rows]
    abilities = [a for a in abilities if a is not None]
    if ability is not None:
        abilities = [ability]
    fired = None
    for ab in abilities:
        try:
            at = rpc(sid, "abilityTargets",
                     {"runnerId": rid, "unitId": cid, "abilityType": ab}, 90) or {}
        except Exception as exc:
            print(f"    ability {ab}: abilityTargets KO ({exc})")
            continue
        row = next((u for u in (at.get("units") or []) if u.get("unitId") == cid), None)
        tgts = ((row.get("abilities") or [{}])[0].get("targets") or []) if row else []
        if not tgts:
            print(f"    ability {ab}: 0 cible legale")
            continue
        t = _pick_target(tgts, caster_row.get("pos"))
        action = {"kind": "ability", "casterId": cid, "abilityType": ab}
        if t.get("kind") == "unit":
            action["targetId"] = t["targetId"]
        else:
            action["to"] = {"col": t["tile"]["col"], "row": t["tile"]["row"]}
        before = _state_footprint(sid, rid)
        try:
            res = rpc(sid, "applyAction", {"runnerId": rid, "action": action}, 90) or {}
        except Exception as exc:
            print(f"    ability {ab}: applyAction KO ({exc})")
            continue
        after = _state_footprint(sid, rid)
        d = _fp_delta(before, after)
        act0 = (res.get("actions") or [{}])[0]
        observable = bool(d["newUnits"] or d["hpDelta"] or d["deaths"] or d["newEffects"])
        print(f"    ability {ab}: CAST ok={act0.get('ok', True)} err={act0.get('error')} "
              f"cibles={len(tgts)} tgt={json.dumps(t)[:120]} delta={json.dumps(d)}")
        if observable and fired is None:
            fired = {"acted": True, "detail": f"ability={ab} delta={json.dumps(d)}"}
    return fired or {"acted": False, "detail": "aucune ability castee avec effet observable"}


# --------------------------------------------------------------------- (2)+(3) voie POST-START

def phase_late(sid, units, ability=None):
    """(2)/(3) par la voie POST-START (`applyAddUnit` apres StartMatch).

    OUTIL DE DIAGNOSTIC : le natif a deux chemins d'ajout distincts
    (`IdunBattle.Operations.AddUnitOperation$$AddHeroDuringRunningMatch` n'est emprunte que match
    demarre). Monter le porteur par cette voie separe une faute de DEPLOIEMENT d'une faute de
    CAST. C'est ce qui a localise la vraie cause des « system error » : un passif dont la config
    d'ability manque faute a la CREATION (deploiement pre-start), pas au cast -- une fois la
    config injectee (cf. `catalog_inject.augment`), les deux voies passent.
    """
    print(f"\n=== (2)/(3) POST-START (applyAddUnit apres StartMatch) : {units} ===")
    seed = R._load_seed_bc()
    bc0, _added, _ab, _unres = CI.augment(seed, units, rank=RANK)
    board_dump = R._load_board_dump(BOARD_UNITS)
    template, pool, _pm = R._normalize_and_extract_pool(sid, bc0, RANK, board_dump=board_dump)
    bc = copy.deepcopy(template)
    R._patch_predefined_units(bc, [ENEMY])
    R._patch_predefined_machines(bc, None, None)
    pts = R._spawn_points_by_twpi(bc).get(0) or []
    resp = R._rpc(sid, "initAndStart",
                  [{"configJson": json.dumps(bc), "seed": SEED, "playerUnits": []}], timeout=60)
    rid = (resp.get("result") or {}).get("runnerId")
    if rid is None:
        raise RuntimeError(f"initAndStart KO: {resp.get('error') or resp}")
    _rids.append(rid)
    verdicts = {}
    try:
        for i, uid in enumerate(units):
            r = R._rpc(sid, "applyAddUnit",
                       [{"runnerId": rid, "unitId": uid, "playerId": R.PLAYER_ID_HUMAN,
                         "col": int(pts[i][0]), "row": int(pts[i][1])}], timeout=60)
            ok = bool((r.get("result") or {}).get("ok"))
            verdicts[uid] = {"spawned": ok, "acted": False, "detail": ""}
            print(f"  [{uid}] applyAddUnit ok={ok} err={r.get('error')}")
        dec = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True})
        for uid in units:
            rows = unit_rows(dec, uid)
            if not rows:
                print(f"  [{uid}] absent de decisionView")
                verdicts[uid]["spawned"] = False
                continue
            u = rows[0]
            print(f"  [{uid}] VIVANT id={u.get('id')} hp={u.get('hp')} hasAction={u.get('hasAction')} "
                  f"abilities={[(a.get('id'), a.get('kind'), a.get('level'), a.get('multiplier')) for a in (u.get('abilities') or [])]} "
                  f"effects={[(e.get('effectType'), e.get('name')) for e in (u.get('effects') or [])]}")
            verdicts[uid].update(_try_cast(sid, rid, u, ability))
    finally:
        dispose(sid, rid)
    return verdicts


# --------------------------------------------------------------------- (2)+(3) MoW

def phase_mow(sid, mow_id, ability=None):
    """(2) deploiement + (3) cast pour une MACHINE OF WAR injectee au catalogue."""
    print(f"\n=== (2)/(3) MoW : {mow_id} ===")
    rid, pool, pool_mow, added = build(
        sid, [mow_id], ["necroDestroyer", "necroWarden"],
        a_units=("necroDestroyer", "necroWarden"), p_mow=mow_id, board=BOARD_MOW)
    verdict = {"present": mow_id in pool_mow, "spawned": False, "acted": False, "detail": ""}
    try:
        print(f"  pool MoW = {pool_mow}")
        dec = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True})
        m = next((x for x in (dec.get("mows") or []) if x.get("visualId") == mow_id), None)
        if m is None:
            print(f"  [{mow_id}] NON DEPLOYEE (absente de decisionView.mows) "
                  f"mows={[x.get('visualId') for x in (dec.get('mows') or [])]}")
            return verdict
        verdict["spawned"] = True
        print(f"  [{mow_id}] DEPLOYEE casterId={m.get('casterId')} team={m.get('team')} "
              f"abilities={[(a.get('abilityType'), a.get('level'), a.get('multiplier')) for a in (m.get('abilities') or [])]}")
        res = _try_cast(sid, rid, m, ability)
        verdict.update(res)
    finally:
        dispose(sid, rid)
    return verdict


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", default="all",
                    choices=["all", "control", "present", "spawn", "act", "late", "actmow"])
    ap.add_argument("--units", default="votanMemnyr,votanBeserk,votanIronmaster,votanUthar")
    ap.add_argument("--mow", default="thousDaemonPrince")
    ap.add_argument("--ability", type=int, default=None)
    ap.add_argument("--carrier", default="genesBiophagus")
    a = ap.parse_args(argv)
    sid = R._resolve_session()
    print(f"[probe92] session={sid}")
    units = [x.strip() for x in a.units.split(",") if x.strip()]
    try:
        if a.phase in ("all", "control"):
            phase_control(sid, a.carrier)
        if a.phase in ("all", "present"):
            phase_present(sid)
        if a.phase in ("all", "spawn"):
            phase_spawn_and_act(sid, units, do_act=False)
        if a.phase in ("all", "act"):
            phase_spawn_and_act(sid, units, do_act=True)
        if a.phase == "late":
            phase_late(sid, units, a.ability)
        if a.phase in ("all", "actmow"):
            phase_mow(sid, a.mow, a.ability)
    finally:
        for rid in list(_rids):
            dispose(sid, rid)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
