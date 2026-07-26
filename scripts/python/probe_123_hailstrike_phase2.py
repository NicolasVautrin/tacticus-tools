"""Probe #123 -- PHASE 2 de Hailstrike (1214, `darkaStormSpeeder`), confront LIVE des DEUX maillons :

  (a) `Hailstrike_ExtraPierceEffect` (effet 1509) : +extraPierceRatio au percage des attaques
      RANGED / OVERWATCH du PORTEUR du buff ;
  (b) `Hailstrike_AttackAbility` (triggered 1507) : quand ce porteur finit une attaque ranged sur un
      ennemi VIVANT, la MACHINE OF WAR attaque la MEME cible (nrOfHits coups du profil de la config).

Les deux se manifestent dans LA MEME action live (l'attaque normale de l'allie buffe) -> une seule
mesure les confronte, avec `dumpRng` avant l'action pour rejouer offline bit-exact.

Le porteur est HORS du seed BC -> `catalog_inject.py` (#92). Hailstrike n'a PAS de `munitionsCost`
(contrairement a DeathOnTheWind) -> castable au tour 1.

Usage :
    python probe_123_hailstrike_phase2.py --phase recon     # etat initial (niveaux, stats, armure)
    python probe_123_hailstrike_phase2.py --phase full      # cast + attaque + replay offline + mutation

ASCII only (console cp1252).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import hexgeo
from rl_collect_batch import _rpc, _resolve_session

PYDIR = Path(__file__).resolve().parent
DATA = PYDIR.parent.parent / "data"
SEED_BC = DATA / "_123_hailstrike_bc.json"
BOARD = "MC1_67"

MOW = "darkaStormSpeeder"
ALLY = "darkaAzrael"          # arme RANGED Plasma (range 2, 1 coup) + arme melee Power (3 coups)
SPARE = "ultraApothecary"     # jamais activee : garde le tour ouvert
FOE = "astraBullgryn"         # armure elevee -> le percage change le degat de facon MESURABLE


def _unwrap(r):
    return r["result"] if isinstance(r, dict) and "result" in r else r


def rpc(sid, method, body=None, timeout=120):
    return _unwrap(_rpc(sid, method, [body] if body is not None else [], timeout=timeout))


def ensure_seed_bc(ammo: int = 5, tanky: bool = False):
    """Seed BC augmente du porteur MoW (#92) + munitions. `tanky` = PV enormes pour l'ennemi SANS
    toucher son armure : `--hp-target` de rl_duel met `FixedArmor = 0` (ce qui rendrait le PERCAGE
    inerte), on ne peut donc pas s'en servir quand on veut PLUSIEURS echantillons de degat perce.
    Extension de HARNAIS (parametre de BATAILLE), pas de mecanique."""
    path = SEED_BC.with_name(SEED_BC.stem + ("_tanky" if tanky else "") + SEED_BC.suffix)
    if path.exists():
        return path
    subprocess.run([sys.executable, "catalog_inject.py", "--units", MOW, "--out", str(path)],
                   cwd=str(PYDIR), check=True)
    bc = json.loads(path.read_text(encoding="utf-8"))
    for _pid, p in ((bc.get("Player") or {}).get("Players") or {}).items():
        if isinstance(p, dict) and p.get("PlayerType") != 2:
            p["MachineOfWarAmmo"] = ammo
    if tanky:
        n = 0
        for u in (bc.get("Units") or {}).values() if isinstance(bc.get("Units"), dict) \
                else (bc.get("Units") or []):
            if isinstance(u, dict) and u.get("VisualId") == FOE:
                u["Health"] = 900000
                u["RemainingHealth"] = 900000
                n += 1
        print(f"[bc] {FOE} : PV portes a 900000 sur {n} template(s) (armure INCHANGEE)")
    path.write_text(json.dumps(bc), encoding="utf-8")
    return path


def build(state_file: str, seed: str = "31337", no_armor: bool = False, tanky: bool = False) -> int:
    bcp = ensure_seed_bc(tanky=tanky)
    # `--hp-target` met `FixedArmor = 0` (rl_duel.py) -> le PERCAGE devient INERTE sur le degat.
    # C'est le levier de DECOMPOSITION PAR ETAGE : sans armure, un buff purement « percage » ne doit
    # RIEN changer ; s'il change quand meme le degat, c'est qu'il agit sur un AUTRE etage.
    extra = ["--hp-target", "900000", "--hp-player", "900000"] if no_armor else []
    p = subprocess.run([sys.executable, "rl_duel.py", "build", "--seed", seed,
                        "--board", BOARD, "--seed-bc", str(bcp),
                        "--p-units", f"{ALLY},{SPARE}", "--a-units", f"{FOE},{FOE}",
                        "--p-mow", MOW, *extra,
                        "--state-file", state_file],
                       cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    st = json.loads(Path(state_file).read_text(encoding="utf-8"))
    rid = st.get("runnerId")
    if rid is None:
        raise RuntimeError((p.stderr or p.stdout or "")[-2000:])
    return int(rid)


def upos(u):
    q = (u or {}).get("pos") or {}
    return (q.get("col"), q.get("row"))


def find(d, vis):
    return next((u for u in (d.get("units") or []) if u.get("visualId") == vis), None)


def find_all(d, vis):
    return [u for u in (d.get("units") or []) if u.get("visualId") == vis]


def mow_of(d):
    return next((m for m in (d.get("mows") or []) if m.get("visualId") == MOW), None)


def dview(sid, rid):
    return rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)


def legal_targets(sid, rid, unit_id, ability_id):
    """`fromHere` UNIQUEMENT (gate de ciblage #115) -- jamais `targets`."""
    at = rpc(sid, "abilityTargets", {"runnerId": rid, "unitId": unit_id,
                                     "abilityType": ability_id}, 120)
    for u in (at.get("units") or []):
        for a in (u.get("abilities") or []):
            if a.get("abilityId") != ability_id:
                continue
            return [t.get("targetId") for t in (a.get("fromHere") or [])
                    if t.get("targetId") is not None]
    return []


def drive(sid, rid, vis, goal_id, want_dist, iters=14):
    """Rapproche `vis` a <= want_dist de l'unite `goal_id` (deplacements legaux uniquement)."""
    for _ in range(iters):
        d = dview(sid, rid)
        u = find(d, vis)
        g = next((x for x in (d.get("units") or []) if x["id"] == goal_id), None)
        if u is None or g is None:
            return d
        if hexgeo.distance(upos(u), upos(g)) <= want_dist:
            return d
        mov = rpc(sid, "aiMovableTiles", {"runnerId": rid, "side": "all"}, 90)
        mu = next((m for m in (mov.get("units") or []) if m.get("unitId") == u["id"]), None)
        tiles = [(t["col"], t["row"]) for t in (mu or {}).get("tiles") or []
                 if t.get("col") is not None]
        if not tiles:
            rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 90)
            continue
        best = min(tiles, key=lambda t: (hexgeo.distance(t, upos(g)), t))
        if hexgeo.distance(best, upos(g)) >= hexgeo.distance(upos(u), upos(g)):
            rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 90)
            continue
        rpc(sid, "applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": u["id"], "to": {"col": best[0], "row": best[1]}}}, 90)
    return dview(sid, rid)


def snap_unit(sid, rid, uid):
    s = rpc(sid, "combatSnapshot", {"runnerId": rid}, 120)
    return next((u for u in (s.get("units") or []) if u.get("entityId") == uid), {})


def live_hits(cast):
    """Degats live attribues, par (Target_Id, Active_Ability_Type) -> [(amount, profile), ...]."""
    out: dict = {}
    for act in (cast.get("actions") or []):
        for e in (act.get("events") or []):
            td = e.get("tags")
            if not td:
                continue
            td = json.loads(td) if isinstance(td, str) else td
            if "Amount" not in td:
                continue
            key = (td.get("Target_Id"), td.get("Active_Ability_Type"),
                   td.get("Triggered_Ability_Type"), td.get("Effect_Type"), td.get("Source_Id"))
            out.setdefault(key, []).append((td.get("Amount"), td.get("DamageProfileType")))
    return out


def phase_recon(sid, args):
    rid = build(args.state)
    print(f"[recon] runner {rid}")
    d = dview(sid, rid)
    m = mow_of(d)
    print("[recon] mow =", json.dumps({k: m.get(k) for k in ("casterId", "owner", "visualId")}))
    print("[recon] mow abilities =", json.dumps([{k: a.get(k) for k in ("id", "usable", "cooldown")}
                                                 for a in (m.get("abilities") or [])]))
    ally = find(d, ALLY)
    print("[recon] ally =", ally["id"], upos(ally),
          [{k: a.get(k) for k in ("id", "kind")} for a in (ally.get("abilities") or [])])
    for f in find_all(d, FOE):
        su = snap_unit(sid, rid, f["id"])
        print("[recon] foe", f["id"], upos(f), "hp", f.get("hp"),
              "stats", json.dumps(su.get("stats") or {})[:400])
    su = snap_unit(sid, rid, m["casterId"])
    print("[recon] mow snapshot =", json.dumps(su)[:900])
    print("[recon] mow dv entry =", json.dumps(m)[:900])
    mu = next((u for u in (d.get("units") or []) if u["id"] == m["casterId"]), None)
    print("[recon] mow in units[] =", json.dumps(mu)[:600])
    # OFFLINE : ce que le port voit reellement de la MoW (niveau d'ability actif = l'index du ConfigVar)
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    from engine.runner.components import StatsComponent
    bg = rpc(sid, "boardGraph", {"runnerId": rid}, 90)
    board = Board(bg["tiles"], adjacency="native_sym") if (bg or {}).get("tiles") else None
    st = load_state(d, rpc(sid, "observeBattle", {"runnerId": rid}, 90),
                    rpc(sid, "combatSnapshot", {"runnerId": rid}, 120), board=board)
    for uid in (m["casterId"], ally["id"]):
        e = st.get_entity(uid)
        sc = e.get_component(StatsComponent) if e is not None else None
        c = getattr(sc, "ctx", None) if sc is not None else None
        print(f"[recon] OFFLINE u{uid} visual={getattr(c, 'visual_id', None)} "
              f"activeLvl={getattr(c, 'active_ability_level', None)} "
              f"mult={getattr(c, 'ability_variables_multiplier', None)}")
    sa = snap_unit(sid, rid, ally["id"])
    print("[recon] ally cfg =", json.dumps(sa.get("unitConfig") or {})[:400])
    print("[recon] ally stats =", json.dumps(sa.get("stats") or {})[:400])
    return rid


def phase_full(sid, args):
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.operations.damage import AttackDamageOperation

    rid = build(args.state)
    print(f"[full] runner {rid}")
    d = dview(sid, rid)
    m = mow_of(d)
    if m is None:
        print("[full] ABORT : MoW non deployee")
        return rid
    cid = m["casterId"]
    ally = find(d, ALLY)
    foes = [u for u in (d.get("units") or []) if u.get("owner") != m.get("owner") and u.get("alive")]
    print("[full] mow", cid, "ally", ally["id"], "foes", [f["id"] for f in foes])

    # (1) rapprocher l'allie a portee RANGED (2) d'un ennemi -- drive-positions, jamais « bloque par
    #     la geometrie de spawn ».
    d = drive(sid, rid, ALLY, foes[0]["id"], 2)
    ally = find(d, ALLY)
    foe = next((u for u in (d.get("units") or []) if u["id"] == foes[0]["id"]), None)
    dist = hexgeo.distance(upos(ally), upos(foe))
    print("[full] dist ally-foe =", dist, upos(ally), upos(foe))
    if dist > 2 or dist < 2:
        print(f"[full] WARN : dist={dist} (2 attendu pour un tir Plasma range 2 non-adjacent)")

    # (2) cast Hailstrike (1214) sur l'ALLIE (cible = un ami)
    fh = legal_targets(sid, rid, cid, 1214)
    print("[full] fromHere(1214) =", fh)
    if ally["id"] not in fh:
        print("[full] ABORT : l'allie n'est pas cible legale de Hailstrike")
        return rid
    cast = rpc(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": cid, "targetId": ally["id"], "abilityType": 1214}}, 150)
    a0 = ((cast or {}).get("actions") or [{}])[0]
    print("[full] cast =", json.dumps({k: a0.get(k) for k in ("ok", "mutated", "error")}))
    d = dview(sid, rid)
    a2 = next((u for u in (d.get("units") or []) if u["id"] == ally["id"]), {})
    print("[full] ally effects =", json.dumps(a2.get("effects") or []))

    # (3) SNAPSHOT + RNG avant l'attaque de l'allie
    bg = rpc(sid, "boardGraph", {"runnerId": rid}, 90)
    board = Board(bg["tiles"], adjacency="native_sym") if (bg or {}).get("tiles") else None
    dv2, ob2 = dview(sid, rid), rpc(sid, "observeBattle", {"runnerId": rid}, 90)
    snap2 = rpc(sid, "combatSnapshot", {"runnerId": rid}, 120)
    rng0 = rpc(sid, "dumpRng", {"runnerId": rid}, 60)
    hp_before = {u["id"]: u.get("hp") for u in (dv2.get("units") or [])}

    # (4) l'ALLIE tire sur l'ennemi (attaque NORMALE, id per-unite lu du decisionView)
    nid = next((a.get("id") for a in (a2.get("abilities") or []) if a.get("kind") == "normal"), None)
    print("[full] normal ability id =", nid)
    atk = rpc(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": ally["id"], "targetId": foe["id"], "abilityType": nid},
        "captureEvents": True}, 150)
    b0 = ((atk or {}).get("actions") or [{}])[0]
    print("[full] attack =", json.dumps({k: b0.get(k) for k in ("ok", "mutated", "error")}))
    lh = live_hits(atk)
    print("[full] LIVE hits (target, activeAbility, triggeredAbility, effectType, source) :")
    for k, v in lh.items():
        print("   ", k, "->", v)
    d3 = dview(sid, rid)
    for u in (d3.get("units") or []):
        if hp_before.get(u["id"]) not in (None, u.get("hp")):
            print(f"[full] hp u{u['id']} {hp_before[u['id']]} -> {u.get('hp')} "
                  f"(delta {hp_before[u['id']] - u.get('hp')})")

    # (5) REPLAY OFFLINE du meme coup (etat + rng identiques)
    st = load_state(dv2, ob2, snap2, board=board)
    if isinstance(rng0, dict) and rng0.get("mt"):
        r = IntBasedMersenneTwister()
        r.mt = list(rng0["mt"])
        r.mti = rng0["mti"]
        st.rng = r
    eff = st.effects.by_unit.get(ally["id"], []) if st.effects is not None else []
    print("[full] OFFLINE effets de l'allie =",
          [(type(e).__name__, e.effect_type, e.source, e.active_ability_level) for e in eff])
    from engine.runner.operations.triggers.dispatch import collect_triggered_abilities
    reg = [type(t).__name__ for t in collect_triggered_abilities(st)]
    print("[full] OFFLINE registre triggers =", sorted(set(reg)))
    res = AttackDamageOperation.execute(st, ally["id"], foe["id"])
    print("[full] OFFLINE attaque allie =", json.dumps({k: res.get(k) for k in
                                                        ("hits", "total", "pierce", "armor")}))
    print("[full] OFFLINE hp apres :")
    from engine.runner.components import HealthComponent
    for uid in sorted(hp_before):
        e = st.get_entity(uid)
        hc = e.get_component(HealthComponent) if e is not None else None
        if hc is not None and hp_before[uid] != hc.hp:
            print(f"    u{uid} {hp_before[uid]} -> {hc.hp} (delta {hp_before[uid] - hc.hp})")
    return rid


def _snapshot(sid, rid):
    from engine.entities.pathfinding.board import Board
    bg = rpc(sid, "boardGraph", {"runnerId": rid}, 90)
    board = Board(bg["tiles"], adjacency="native_sym") if (bg or {}).get("tiles") else None
    return (dview(sid, rid), rpc(sid, "observeBattle", {"runnerId": rid}, 90),
            rpc(sid, "combatSnapshot", {"runnerId": rid}, 120),
            rpc(sid, "dumpRng", {"runnerId": rid}, 60), board)


def _offline_state(dv, ob, snap, rng0, board):
    from engine.runner.snapshot import load_state
    from engine.runner.prng import IntBasedMersenneTwister
    st = load_state(dv, ob, snap, board=board)
    if isinstance(rng0, dict) and rng0.get("mt"):
        r = IntBasedMersenneTwister()
        r.mt = list(rng0["mt"])
        r.mti = rng0["mti"]
        st.rng = r
    return st


def _hp_map(dv):
    return {u["id"]: u.get("hp") for u in (dv.get("units") or [])}


def _offline_hp(st, ids):
    from engine.runner.components import HealthComponent
    out = {}
    for uid in ids:
        e = st.get_entity(uid)
        hc = e.get_component(HealthComponent) if e is not None else None
        if hc is not None:
            out[uid] = hc.hp
    return out


def _one_attack(sid, rid, tag, attacker, target, nid, mutate=False, sweep=None):
    """LIVE = une attaque normale ; OFFLINE = la MEME depuis le snapshot + rng identiques."""
    from engine.runner.operations.damage import AttackDamageOperation
    dv, ob, snap, rng0, board = _snapshot(sid, rid)
    hp0 = _hp_map(dv)
    atk = rpc(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": attacker, "targetId": target, "abilityType": nid},
        "captureEvents": True}, 150)
    b0 = ((atk or {}).get("actions") or [{}])[0]
    lh = live_hits(atk)
    dv3 = dview(sid, rid)
    hp1 = _hp_map(dv3)
    live_delta = {u: hp0[u] - hp1[u] for u in hp0 if hp1.get(u) is not None and hp0[u] != hp1[u]}
    print(f"[{tag}] LIVE ok={b0.get('ok')} mutated={b0.get('mutated')} err={b0.get('error')}")
    for k, v in lh.items():
        print(f"[{tag}] LIVE hit key(target,active,triggered,effect,source)={k} -> {v}")
    print(f"[{tag}] LIVE hp delta = {live_delta}")
    for act in (atk.get("actions") or []):
        for e in (act.get("events") or []):
            td = e.get("tags")
            td = json.loads(td) if isinstance(td, str) else td
            if td and "Amount" in td:
                print(f"[{tag}] LIVE RAW TAGS = {json.dumps(td)}")

    # CHEMIN DE PRODUCTION offline = `Runner.apply(AttackUnitMessage)` (le handler
    # `visit_AttackUnitMessage`), PAS `AttackDamageOperation.execute` seul : c'est le HANDLER qui emet le
    # vecteur after-hit `On(9)` dont depend le trigger 1507 (un appel direct a l'Operation le SAUTE).
    from engine.runner.runner import Runner
    from engine.runner.messages import AttackUnitMessage
    st = _offline_state(dv, ob, snap, rng0, board)
    if mutate:
        # MUTATION-TEST : on NEUTRALISE le bonus de percage Hailstrike (et LUI SEUL) pour prouver
        # qu'il est PORTANT (si le port sans lui donnait le meme resultat, l'assertion serait aveugle).
        from engine.entities.effects.loki.darkangels import HailstrikeExtraPierceEffect
        for e in (st.effects.by_unit.get(attacker) or []):
            if isinstance(e, HailstrikeExtraPierceEffect):
                e.create_effect_piercing_bonus_for_attack = lambda ctx=None: None
    rr = Runner(st).install_default_handlers(20)
    rr.apply(AttackUnitMessage(attacker_id=attacker, target_id=target))
    res = rr.damage_handler.last or {}
    res = dict(res, after_hit=rr.damage_handler.after_hit)
    off_hp = _offline_hp(st, list(hp0))
    off_delta = {u: hp0[u] - off_hp[u] for u in hp0 if off_hp.get(u) is not None and hp0[u] != off_hp[u]}
    print(f"[{tag}] OFFLINE{'(MUTE)' if mutate else ''} attack = "
          f"{json.dumps({k: res.get(k) for k in ('hits', 'total', 'pierce', 'armor', 'base')})}")
    print(f"[{tag}] OFFLINE{'(MUTE)' if mutate else ''} hp delta = {off_delta}")
    print(f"[{tag}] VERDICT delta live == offline ? {live_delta == off_delta}")
    print(f"[{tag}] OFFLINE bornes reduites = [{res.get('clean_min')}, {res.get('clean_max')}] "
          f"effets_actifs={res.get('effects')}")
    print(f"[{tag}] OFFLINE after_hit = {json.dumps(res.get('after_hit'), default=str)[:700]}")
    if sweep:
        # DIAGNOSTIC PAR ETAGE (jamais un fit) : (1) sweep du BONUS de percage, (2) sweep du NOMBRE de
        # tirages RNG BRULES avant le coup. Le 1er localise un etage "valeur", le 2e un etage
        # "consommation RNG" -- les deux sont des localisateurs, ils ne DECIDENT de rien.
        # --- DIAG maillon (b) : le trigger 1507 est-il collecte, et son `matches` passe-t-il ? -----
        from engine.runner.operations.triggers.dispatch import collect_triggered_abilities
        from engine.runner.operations.triggers.base import TriggerEvent
        from engine.dsl.event_trigger_type import EventTriggerType
        from engine.runner.components import OwnerComponent, UnitComponent, StatsComponent
        st3 = _offline_state(dv, ob, snap, rng0, board)
        for uid in (attacker, target):
            e3 = st3.get_entity(uid)
            print(f"[{tag}] DIAG u{uid} comps = "
                  f"owner={getattr(e3.get_component(OwnerComponent), 'team', None) if e3 else None} "
                  f"alive={getattr(e3.get_component(UnitComponent), 'alive', None) if e3 else None}")
        for t in collect_triggered_abilities(st3):
            if type(t).__name__ != "HailstrikeAttackAbility":
                continue
            e3 = st3.get_entity(t.owner_id)
            oc3 = e3.get_component(OwnerComponent) if e3 else None
            uc3 = e3.get_component(UnitComponent) if e3 else None
            sc3 = e3.get_component(StatsComponent) if e3 else None
            ev3 = TriggerEvent(int(EventTriggerType.Attack), attacker, target,
                               ranged=True, profile="Plasma")
            print(f"[{tag}] DIAG trigger owner={t.owner_id} team={getattr(oc3, 'team', None)} "
                  f"alive={getattr(uc3, 'alive', None)} lvl="
                  f"{getattr(getattr(sc3, 'ctx', None), 'active_ability_level', None)} "
                  f"matches={t.matches(st3, ev3)}")
        from engine.entities.effects.loki.darkangels import HailstrikeExtraPierceEffect
        live_amt0 = next((v[0][0] for k, v in lh.items()
                          if k[0] == target and k[1] is not None), None)
        hits2 = []
        for delta in sweep:
            for burn2 in range(0, 25):
                st2 = _offline_state(dv, ob, snap, rng0, board)
                for _ in range(burn2):
                    st2.rng.genrand_int32()
                for e in (st2.effects.by_unit.get(attacker) or []):
                    if isinstance(e, HailstrikeExtraPierceEffect):
                        e.create_effect_piercing_bonus_for_attack = (
                            lambda ctx=None, _d=delta: (_d or None))
                r2 = AttackDamageOperation.execute(st2, attacker, target) or {}
                if r2.get("total") == live_amt0:
                    hits2.append((delta, burn2, r2.get("pierce")))
                if burn2 == 0 and delta % 5 == 0:
                    print(f"[{tag}] SWEEP bonus=+{delta:>3} -> pierce={r2.get('pierce')} "
                          f"bornes=[{r2.get('clean_min')},{r2.get('clean_max')}] total={r2.get('total')}")
        print(f"[{tag}] SWEEP (bonus, burn, pierce) reproduisant LIVE {live_amt0} = {hits2}")
        st2 = _offline_state(dv, ob, snap, rng0, board)
        raws = [st2.rng.genrand_int32() >> 1 for _ in range(4)]
        print(f"[{tag}] RAW (genrand>>1) = {raws}")
        # `next_internal(lo, hi)` non-puissance-de-2 = `lo + (raw % (hi-lo))` : on RESOUD le ratio de
        # percage LIVE a partir du 1er raw et des bornes BRUTES (clean/p), sans rien fitter d'autre.
        lo0 = res.get("clean_min") / max(1, res.get("pierce")) * 100.0
        hi0 = res.get("clean_max") / max(1, res.get("pierce")) * 100.0
        live_amt = next((v[0][0] for k, v in lh.items()
                         if k[0] == target and k[1] is not None), None)
        if live_amt is not None:
            sol = []
            for p in range(1, 101):
                lo, hi = int(lo0 * p / 100.0), int(hi0 * p / 100.0)
                if hi <= lo:
                    continue
                if lo + (raws[0] % (hi - lo)) == live_amt:
                    sol.append(p)
            print(f"[{tag}] SOLVE percage LIVE (raw[0], bornes brutes ~[{lo0:.0f},{hi0:.0f}]) "
                  f"amt={live_amt} -> p in {sol}")
        for burn in range(0, 5):
            st2 = _offline_state(dv, ob, snap, rng0, board)
            for _ in range(burn):
                st2.rng.genrand_int32()
            r2 = AttackDamageOperation.execute(st2, attacker, target)
            print(f"[{tag}] SWEEP burn={burn} -> pierce={r2.get('pierce')} total={r2.get('total')}")
    return live_delta, off_delta


def phase_ab_noarmor(sid, args):
    return phase_ab(sid, args, no_armor=True)


def phase_ab(sid, args, no_armor: bool = False):
    """A/B dans UN SEUL runner : meme allie, meme arme, deux ennemis IDENTIQUES (armure 3513).
    A = attaque SANS buff (controle du port de base) ; B = attaque AVEC le buff Hailstrike."""
    rid = build(args.state, no_armor=no_armor)
    print(f"[ab] runner {rid}")
    d = dview(sid, rid)
    m = mow_of(d)
    cid = m["casterId"]
    ally = find(d, ALLY)
    foes = [u for u in (d.get("units") or []) if u.get("owner") != m.get("owner") and u.get("alive")]
    d = drive(sid, rid, ALLY, foes[0]["id"], 2)
    ally = find(d, ALLY)
    pos = {u["id"]: upos(u) for u in (d.get("units") or [])}
    print("[ab] ally", ally["id"], pos.get(ally["id"]),
          "foes", {f["id"]: (pos.get(f["id"]), hexgeo.distance(pos[ally["id"]], pos[f["id"]]))
                   for f in foes})
    nid = next((a.get("id") for a in (ally.get("abilities") or []) if a.get("kind") == "normal"), None)
    fa, fb = foes[0]["id"], foes[1]["id"]
    if hexgeo.distance(pos[ally["id"]], pos[fb]) != 2:
        print("[ab] WARN : 2e ennemi hors portee 2 -> A et B sur la MEME cible (2 tours)")
        fb = fa

    # --- A : CONTROLE (aucun buff) -------------------------------------------------------------
    print("[ab] --- A : attaque SANS buff Hailstrike ---")
    _one_attack(sid, rid, "A", ally["id"], fa, nid, sweep=[0])

    # rendre la main a mon camp
    for _ in range(4):
        dd = dview(sid, rid)
        if dd.get("currentPlayer") == m.get("owner") and \
                next((u for u in (dd.get("units") or []) if u["id"] == ally["id"]), {}).get("hasAction"):
            break
        rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 90)

    # --- B : TRAITEMENT (buff Hailstrike pose par la MoW) --------------------------------------
    print("[ab] --- B : cast Hailstrike puis attaque ---")
    fh = legal_targets(sid, rid, cid, 1214)
    print("[ab] fromHere(1214) =", fh)
    if ally["id"] not in fh:
        print("[ab] ABORT : allie non cible legale de Hailstrike")
        return rid
    st_before = snap_unit(sid, rid, ally["id"])
    rpc(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": cid, "targetId": ally["id"], "abilityType": 1214}}, 150)
    st_after = snap_unit(sid, rid, ally["id"])
    sb, sa = (st_before.get("stats") or {}), (st_after.get("stats") or {})
    diff = {k: (sb.get(k), sa.get(k)) for k in set(sb) | set(sa) if sb.get(k) != sa.get(k)}
    print("[ab] STAT DIFF allie (cast Hailstrike) =", json.dumps(diff))
    print("[ab] statDelta apres =", json.dumps(st_after.get("statDelta") or {}))
    dd = dview(sid, rid)
    a2 = next((u for u in (dd.get("units") or []) if u["id"] == ally["id"]), {})
    print("[ab] ally effects =", [e.get("name") for e in (a2.get("effects") or [])])
    print("[ab] ally hasAction =", a2.get("hasAction"))
    _one_attack(sid, rid, "B", ally["id"], fb, nid, sweep=[0, 15])
    return rid


def phase_samples(sid, args):
    """IDENTIFICATION du bonus de percage par N echantillons INDEPENDANTS (jamais un fit sur 1 point) :
    a chaque tour, la MoW (re)pose Hailstrike sur l'allie, l'allie tire sur un ennemi a ARMURE INTACTE
    (3513) et PV enormes, et on cherche QUEL bonus de percage reproduit EXACTEMENT le degat live.
    Si le MEME bonus ressort sur tous les tirs, il est IDENTIFIE (N contraintes independantes)."""
    from engine.runner.runner import Runner
    from engine.runner.messages import AttackUnitMessage
    from engine.entities.effects.loki.darkangels import HailstrikeExtraPierceEffect
    rid = build(args.state, tanky=True)
    print(f"[samples] runner {rid}")
    d = dview(sid, rid)
    m = mow_of(d)
    cid = m["casterId"]
    ally = find(d, ALLY)
    foes = [u for u in (d.get("units") or []) if u.get("owner") != m.get("owner") and u.get("alive")]
    d = drive(sid, rid, ALLY, foes[0]["id"], 2)
    ally = find(d, ALLY)
    nid = next((a.get("id") for a in (ally.get("abilities") or []) if a.get("kind") == "normal"), None)
    pos = {u["id"]: upos(u) for u in (d.get("units") or [])}
    tgts = [f["id"] for f in foes if hexgeo.distance(pos[ally["id"]], pos[f["id"]]) == 2]
    print("[samples] ally", ally["id"], pos[ally["id"]], "cibles a portee 2 :", tgts)
    if not tgts:
        print("[samples] ABORT : aucune cible a portee 2")
        return rid
    ident = []
    for n in range(int(args.n)):
        dd = dview(sid, rid)
        au = next((u for u in (dd.get("units") or []) if u["id"] == ally["id"]), {})
        if not au.get("hasAction") or dd.get("currentPlayer") != m.get("owner"):
            rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 90)
            dd = dview(sid, rid)
            au = next((u for u in (dd.get("units") or []) if u["id"] == ally["id"]), {})
            if not au.get("hasAction"):
                print(f"[samples] stop au tir {n} : l'allie n'a plus d'action")
                break
        if not any((e.get("name") or "") == "Hailstrike" for e in (au.get("effects") or [])):
            fh = legal_targets(sid, rid, cid, 1214)
            if ally["id"] in fh:
                rpc(sid, "applyAction", {"runnerId": rid, "action": {
                    "kind": "ability", "casterId": cid, "targetId": ally["id"],
                    "abilityType": 1214}}, 150)
            else:
                print(f"[samples] tir {n} : Hailstrike non castable (fromHere={fh})")
        tgt = tgts[n % len(tgts)]
        dv, ob, snap, rng0, board = _snapshot(sid, rid)
        atk = rpc(sid, "applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": ally["id"], "targetId": tgt, "abilityType": nid},
            "captureEvents": True}, 150)
        amt, prof = None, None
        for act in (atk.get("actions") or []):
            for e in (act.get("events") or []):
                td = e.get("tags")
                td = json.loads(td) if isinstance(td, str) else td
                if td and td.get("Attacker_Id") == ally["id"] and "Amount" in td:
                    amt, prof = td["Amount"], td.get("DamageProfileType")
        if amt is None:
            print(f"[samples] tir {n} : aucun degat live (skip) ok={((atk.get('actions') or [{}])[0]).get('ok')}")
            rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 90)
            continue
        st0 = _offline_state(dv, ob, snap, rng0, board)
        rr0 = Runner(st0).install_default_handlers(20)
        rr0.apply(AttackUnitMessage(attacker_id=ally["id"], target_id=tgt))
        r0 = rr0.damage_handler.last or {}
        print(f"[samples] tir {n} LIVE={amt} prof={prof} | OFFLINE(port)={r0.get('total')} "
              f"pierce={r0.get('pierce')} bornes=[{r0.get('clean_min')},{r0.get('clean_max')}] "
              f"hits={r0.get('hits')} ranged={r0.get('ranged')} profil={r0.get('profile')} "
              f"armure={r0.get('armor')} base={r0.get('base')}")
        # MODELE DE TIRAGE : `next_internal(lo, hi)` = `lo + (raw % (hi-lo))` avec raw = genrand>>1.
        # On VERIFIE d'abord que le modele reproduit l'OFFLINE (sinon toute deduction serait fausse),
        # puis on cherche quel ratio de percage p reproduirait le LIVE avec le MEME raw.
        stR = _offline_state(dv, ob, snap, rng0, board)
        raw0 = stR.rng.genrand_int32() >> 1
        b_lo = round(r0.get("clean_min") * 100.0 / max(1, r0.get("pierce")))
        b_hi = round(r0.get("clean_max") * 100.0 / max(1, r0.get("pierce")))

        def _model(p):
            lo, hi = int(b_lo * p / 100), int(b_hi * p / 100)
            return (lo + raw0 % (hi - lo)) if hi > lo else None
        ok_model = _model(r0.get("pierce")) == r0.get("total")
        cand = [p for p in range(1, 101) if _model(p) == amt]
        print(f"[samples] tir {n} MODELE(raw={raw0}, base=[{b_lo},{b_hi}]) valide_offline={ok_model} "
              f"-> p reproduisant LIVE {amt} = {cand}")
        sols = []
        for delta in range(0, 41):
            st2 = _offline_state(dv, ob, snap, rng0, board)
            for e in (st2.effects.by_unit.get(ally["id"]) or []):
                if isinstance(e, HailstrikeExtraPierceEffect):
                    e.create_effect_piercing_bonus_for_attack = (
                        lambda ctx=None, _d=delta: (_d or None))
            rr = Runner(st2).install_default_handlers(20)
            rr.apply(AttackUnitMessage(attacker_id=ally["id"], target_id=tgt))
            r2 = rr.damage_handler.last or {}
            if r2.get("total") == amt:
                sols.append((delta, r2.get("pierce")))
        print(f"[samples] tir {n} cible {tgt} LIVE={amt} -> bonus reproduisant = {sols}")
        ident.append(set(d0 for d0, _p in sols))
        rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 90)
    if ident:
        inter = set.intersection(*ident) if len(ident) > 1 else ident[0]
        print(f"[samples] INTERSECTION des bonus compatibles sur {len(ident)} tirs = {sorted(inter)}")
    return rid


PHASES = {"recon": phase_recon, "full": phase_full, "ab": phase_ab,
          "ab_noarmor": phase_ab_noarmor, "samples": phase_samples}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", required=True, choices=sorted(PHASES))
    ap.add_argument("--state", default=str(LOGS / "runners" / "probe123-hailstrike.json"))
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--n", type=int, default=8)
    args = ap.parse_args()
    Path(args.state).parent.mkdir(parents=True, exist_ok=True)
    sid = _resolve_session()
    rid = None
    try:
        rid = PHASES[args.phase](sid, args)
    finally:
        if rid is not None and not args.keep:
            try:
                rpc(sid, "disposeRunner", {"runnerId": rid}, 60)
                print(f"[cleanup] runner {rid} dispose")
            except Exception as ex:
                print("[cleanup] KO", ex)


if __name__ == "__main__":
    main()
