"""#527 -- MESURE des six rouges de `test_votann_lot1_live.py`, pour les ATTRIBUER.

Ce probe ne teste rien : il MESURE, etage par etage, ce que le montage du fichier de test produit
REELLEMENT, pour dire de chaque rouge s'il accuse le PORT, le MONTAGE, ou une ATTENTE perimee.

Il reutilise les helpers de `probe_113_votann.py` (meme seed BC augmente, meme board, memes
rosters) : le montage mesure ici est bien celui du test, pas un jumeau approximatif.

Etages, dans l'ordre ou ils se conditionnent :

  `stats`    stats de BASE d'un `votanUthar` FRAIS (`combatSnapshot`). Le regime `fortune_gated`
             du test suppose `critChance == 0 and blockChance == 0` ; si la base est > 0, le
             regime qu'il croit exercer N'EXISTE PLUS et ses assertions accusent le MONTAGE.
  `graviton` cast 1206 sur la cible Mechanical, avec les PV MAX de la cible et les events NATIFS
             du cast. `_live_total` du test est un DELTA DE PV : il est PLAFONNE par les PV
             restants, alors qu'un total de degat ne l'est pas. Une cible qui MEURT rend donc
             l'egalite `port == live` fausse par construction, et fait DISPARAITRE les effets
             (d'ou « cible non Stun ([]) »).
  `fortune`  cast 1207, geometrie des DEUX camps + events natifs non filtres. C'est la seule
             facon de dire si le natif a ATTAQUE, et qui, quand `_live_total` vaut 0.

Usage (depuis `scripts/python`, ASCII only) :
    python probe_527_votann_lot1_rouges.py --etage stats
    python probe_527_votann_lot1_rouges.py --etage graviton
    python probe_527_votann_lot1_rouges.py --etage fortune
    python probe_527_votann_lot1_rouges.py --etage tous

Sorties -> `logs/` (gitignore). `data/` ne porte que des ENTREES (#349).
"""
from __future__ import annotations

import argparse
import json

import hexgeo
from rl_collect_batch import _resolve_session

import probe_113_votann as P113
from probe_113_votann import (BESERK, FOE_MECH, FOE_PLAIN, IRONMASTER, LOGS, SPARE, UTHAR,
                              build, drive, find, legal_targets, rpc, snap_stats, upos)

AUGMENTED_ASSAULT, GRAVITON_RIFLE, ANCESTRAL_FORTUNE = 1221, 1206, 1207


def _cast(sid, rid, caster_id, target_id, ability_type):
    return P113._cast(sid, rid, caster_id, target_id, ability_type)


def _dv(sid, rid):
    return rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)


def _by_id(d, uid):
    return next((u for u in (d.get("units") or []) if u["id"] == uid), None)


def _hits_from_events(a0, entity_id):
    """Les coups LIVE tels que le TEST les lit : events `action` sur l'entite cible portant a la
    fois `UnitStats_RemainingHealth` et `Attack_DidCrit`. Rendus BRUTS (aucun filtre en plus)."""
    out = []
    for ev in (a0.get("events") or []):
        if ev.get("kind") != "action" or ev.get("entity") != entity_id:
            continue
        tg = ev.get("tags") or ""
        if "UnitStats_RemainingHealth" not in tg or "Attack_DidCrit" not in tg:
            continue
        try:
            t = json.loads(tg)
        except Exception:
            continue
        out.append({"hp": int(t.get("UnitStats_RemainingHealth")),
                    "crit": bool(int(t.get("Attack_DidCrit") or 0))})
    return out


def _event_digest(a0, limit=60):
    """Digest ASCII des events du cast : (groupe, entite, cles de tags). Sert a voir SI le natif a
    attaque et QUI il a frappe -- un `_live_total` a 0 ne le dit pas."""
    rows = []
    for ev in (a0.get("events") or [])[:limit]:
        tg = ev.get("tags") or ""
        try:
            keys = sorted(json.loads(tg).keys()) if tg else []
        except Exception:
            keys = ["<non-json>"]
        rows.append({"kind": ev.get("kind"), "group": ev.get("group"),
                     "entity": ev.get("entity"), "tags": keys})
    return rows


# ------------------------------------------------------------------------------------------------ #
# etage `stats` -- le regime « base nulle » de `fortune_gated` existe-t-il encore ?
# ------------------------------------------------------------------------------------------------ #

def etage_stats(sid, args):
    rid = build(args.state, f"{UTHAR},{SPARE}", f"{FOE_MECH},{FOE_PLAIN}")
    print("[stats] runner", rid)
    d = _dv(sid, rid)
    u = find(d, UTHAR)
    su = snap_stats(sid, rid, u["id"])
    st = su.get("stats") or {}
    print("[stats] uthar stats  =", json.dumps(st))
    print("[stats] uthar config =", json.dumps(su.get("unitConfig") or {}))
    print("[stats] REGIME GATED (le test suppose critChance==0 et blockChance==0) : critChance=%s"
          " blockChance=%s -> %s"
          % (st.get("critChance"), st.get("blockChance"),
             "TENU" if not int(st.get("critChance") or 0) and not int(st.get("blockChance") or 0)
             else "PERIME"))
    for vis in (FOE_MECH, FOE_PLAIN):
        f = find(d, vis)
        if f is None:
            continue
        fs = snap_stats(sid, rid, f["id"]).get("stats") or {}
        print("[stats] %-16s hp=%s health=%s fixedArmor=%s armor=%s"
              % (vis, f.get("hp"), fs.get("health"), fs.get("fixedArmor"), fs.get("armor")))
    return rid


# ------------------------------------------------------------------------------------------------ #
# etage `graviton` -- le delta de PV est-il PLAFONNE par la mort de la cible ?
# ------------------------------------------------------------------------------------------------ #

def etage_graviton(sid, args, foe=FOE_MECH):
    rid = build(args.state, f"{IRONMASTER},{SPARE}", f"{FOE_MECH},{FOE_PLAIN}")
    print("[graviton:%s] runner %s" % (foe, rid))
    drive(sid, rid, IRONMASTER, foe, 2)
    d = _dv(sid, rid)
    v, f = find(d, IRONMASTER), find(d, foe)
    print("[graviton:%s] dist =" % foe, hexgeo.distance(upos(v), upos(f)))
    tg = legal_targets(sid, rid, v["id"], GRAVITON_RIFLE)
    if f["id"] not in tg:
        print("[graviton:%s] ABORT : cible hors fromHere %s" % (foe, tg))
        return rid
    fs0 = snap_stats(sid, rid, f["id"]).get("stats") or {}
    print("[graviton:%s] AVANT  hp=%s health=%s fixedArmor=%s effects=%s"
          % (foe, f.get("hp"), fs0.get("health"), fs0.get("fixedArmor"),
             [e.get("name") for e in f.get("effects") or []]))
    a0 = _cast(sid, rid, v["id"], f["id"], GRAVITON_RIFLE)
    print("[graviton:%s] cast =" % foe,
          json.dumps({k: a0.get(k) for k in ("ok", "mutated", "actionConsumed", "error")}))
    hits = _hits_from_events(a0, f["id"])
    print("[graviton:%s] coups NATIFS (RemainingHealth successifs) = %s" % (foe, json.dumps(hits)))
    d2 = _dv(sid, rid)
    f2 = _by_id(d2, f["id"]) or {}
    ob = rpc(sid, "observeBattle", {"runnerId": rid}, 40)
    dead = [u.get("id") for u in (ob.get("units") or []) if u.get("isDead")]
    hp0, hp1 = int(f.get("hp") or 0), int(f2.get("hp") or 0)
    print("[graviton:%s] APRES  hp=%s effects=%s isDead=%s"
          % (foe, f2.get("hp"), [e.get("name") for e in f2.get("effects") or []],
             f["id"] in dead))
    # Le total NATIF, lu des events (somme des baisses successives), N'EST PAS le delta de PV :
    # le dernier coup d'une cible qui MEURT est tronque par les PV restants.
    prev, per_hit = hp0, []
    for h in hits:
        per_hit.append(prev - h["hp"])
        prev = h["hp"]
    print("[graviton:%s] delta de PV (ce que `_live_total` du test mesure) = %d" % (foe, hp0 - hp1))
    print("[graviton:%s] somme des coups events                            = %d"
          % (foe, sum(per_hit)))
    print("[graviton:%s] per-hit events = %s" % (foe, per_hit))
    print("[graviton:%s] MORTE ? %s  (une cible morte perd ses effets -> « non Stun ([]) »)"
          % (foe, "OUI" if f["id"] in dead else "non"))
    return rid


# ------------------------------------------------------------------------------------------------ #
# etage `fortune` -- pourquoi `_live_total` vaut-il 0 alors que le port rend 12880 ?
# ------------------------------------------------------------------------------------------------ #

def etage_fortune(sid, args, extra=None):
    rid = build(args.state, f"{UTHAR},{SPARE}", f"{FOE_MECH},{FOE_PLAIN}", extra=extra)
    print("[fortune] runner %s extra=%s" % (rid, extra))
    drive(sid, rid, UTHAR, FOE_MECH, 1)
    d = _dv(sid, rid)
    u, f, g = find(d, UTHAR), find(d, FOE_MECH), find(d, FOE_PLAIN)
    up = upos(u)
    print("[fortune] positions : uthar=%s %s=%s %s=%s"
          % (up, FOE_MECH, upos(f), FOE_PLAIN, upos(g) if g else None))
    print("[fortune] dist(uthar,%s)=%s dist(uthar,%s)=%s"
          % (FOE_MECH, hexgeo.distance(up, upos(f)),
             FOE_PLAIN, hexgeo.distance(up, upos(g)) if g else None))
    st0 = snap_stats(sid, rid, u["id"]).get("stats") or {}
    print("[fortune] uthar stats =", json.dumps(st0))
    tg = legal_targets(sid, rid, u["id"], ANCESTRAL_FORTUNE)
    print("[fortune] fromHere =", tg, "self =", u["id"])
    tid = u["id"]
    if tid not in tg:
        print("[fortune] ABORT : self hors fromHere")
        return rid
    hp_before = {vis: (find(d, vis) or {}).get("hp") for vis in (FOE_MECH, FOE_PLAIN, SPARE, UTHAR)}
    a0 = _cast(sid, rid, u["id"], tid, ANCESTRAL_FORTUNE)
    print("[fortune] cast =",
          json.dumps({k: a0.get(k) for k in ("ok", "mutated", "actionConsumed", "error")}))
    print("[fortune] events =", json.dumps(_event_digest(a0)))
    d2 = _dv(sid, rid)
    hp_after = {vis: (find(d2, vis) or {}).get("hp") for vis in (FOE_MECH, FOE_PLAIN, SPARE, UTHAR)}
    for vis in (FOE_MECH, FOE_PLAIN, SPARE, UTHAR):
        b, a = hp_before.get(vis), hp_after.get(vis)
        print("[fortune] hp %-16s %s -> %s  delta %s"
              % (vis, b, a, (int(b or 0) - int(a or 0))))
    u2 = _by_id(d2, u["id"]) or {}
    print("[fortune] uthar effects apres =", [e.get("name") for e in u2.get("effects") or []])
    print("[fortune] coups NATIFS sur %s = %s"
          % (FOE_MECH, json.dumps(_hits_from_events(a0, f["id"]))))
    if g is not None:
        print("[fortune] coups NATIFS sur %s = %s"
              % (FOE_PLAIN, json.dumps(_hits_from_events(a0, g["id"]))))
    return rid


# ------------------------------------------------------------------------------------------------ #
# etage `replay` -- DECOMPOSER : le CHOIX DE CIBLE et le DEGAT sont deux etages distincts
# ------------------------------------------------------------------------------------------------ #

def _capture(sid, rid):
    """L'etat-avant tel que le test le capture (`dv`/`ob`/`snap`/`rng`), + le board."""
    from engine.entities.pathfinding.board import Board
    dv0 = _dv(sid, rid)
    ob0 = rpc(sid, "observeBattle", {"runnerId": rid}, 40)
    snap0 = rpc(sid, "combatSnapshot", {"runnerId": rid}, 60)
    rng0 = rpc(sid, "dumpRng", {"runnerId": rid}, 30)
    bg = rpc(sid, "boardGraph", {"runnerId": rid}, 60)
    board_obj = Board(bg["tiles"], adjacency="evenq") if (bg or {}).get("tiles") else None
    return dv0, ob0, snap0, rng0, board_obj


def _load(dv0, ob0, snap0, rng0, board_obj):
    from engine.runner.snapshot import load_state
    from engine.runner.prng import IntBasedMersenneTwister
    st = load_state(dv0, ob0, snap0, board=board_obj)
    if isinstance(rng0, dict) and rng0.get("mt"):
        rng = IntBasedMersenneTwister()
        rng.mt = list(rng0["mt"])
        rng.mti = rng0["mti"]
        st.rng = rng
    return st


def etage_replay(sid, args):
    """Deux volets, chacun sur SON runner :

      GRAVITON : le port colle-t-il COUP PAR COUP au natif sur les coups NON TRONQUES ? (le
                 dernier coup d'une cible qui tombe a 0 PV est tronque cote natif, jamais cote port)
      FORTUNE  : le port et le natif choisissent-ils la MEME cible parmi DEUX ennemis adjacents ?
                 et, cible FORCEE a celle du natif, le degat concorde-t-il ?
    """
    from engine.runner.abilities.handler import ABILITY_CLASSES
    from engine.runner.abilities.votann import (ancestral_fortune_tree,
                                                _ancestral_fortune_attack_target)
    from engine.runner.abilities.behaviours.context import entities_from_state
    from engine.dsl.effects import ExecutionContext
    from engine.runner.operations.damage_utility import (_target_utility, damage_utility_weights)
    from engine.entities.effects.magnitude import ability_var
    from engine.dsl.base import _round_fix64
    from fractions import Fraction

    # ---- volet GRAVITON ----
    rid = build(args.state, f"{IRONMASTER},{SPARE}", f"{FOE_MECH},{FOE_PLAIN}")
    print("[replay:graviton] runner", rid)
    drive(sid, rid, IRONMASTER, FOE_MECH, 2)
    dv0, ob0, snap0, rng0, board_obj = _capture(sid, rid)
    v, f = find(dv0, IRONMASTER), find(dv0, FOE_MECH)
    tg = legal_targets(sid, rid, v["id"], GRAVITON_RIFLE)
    if f["id"] in tg:
        a0 = _cast(sid, rid, v["id"], f["id"], GRAVITON_RIFLE)
        hits = _hits_from_events(a0, f["id"])
        prev, live_per = int(f.get("hp") or 0), []
        for h in hits:
            live_per.append(prev - h["hp"])
            prev = h["hp"]
        st = _load(dv0, ob0, snap0, rng0, board_obj)
        res = ABILITY_CLASSES[GRAVITON_RIFLE]().execute_behaviour(st, v["id"], f["id"])
        atk = (res or {}).get("attack") or {}
        print("[replay:graviton] live per-hit = %s (total %d, PV avant %s)"
              % (live_per, sum(live_per), f.get("hp")))
        print("[replay:graviton] port per-hit = %s (total %s)"
              % (atk.get("per_hit"), atk.get("total")))
        print("[replay:graviton] crits live = %s / port = %s"
              % ([h["crit"] for h in hits], atk.get("crits")))
    rpc(sid, "disposeRunner", {"runnerId": rid}, 30)

    # ---- volet FORTUNE ----
    rid = build(args.state, f"{UTHAR},{SPARE}", f"{FOE_MECH},{FOE_PLAIN}")
    print("[replay:fortune] runner", rid)
    drive(sid, rid, UTHAR, FOE_MECH, 1)
    dv0, ob0, snap0, rng0, board_obj = _capture(sid, rid)
    u = find(dv0, UTHAR)
    ids = {vis: (find(dv0, vis) or {}).get("id") for vis in (FOE_MECH, FOE_PLAIN)}
    print("[replay:fortune] ids =", json.dumps(ids), "uthar =", u["id"])
    tg = legal_targets(sid, rid, u["id"], ANCESTRAL_FORTUNE)
    if u["id"] not in tg:
        print("[replay:fortune] ABORT : self hors fromHere", tg)
        rpc(sid, "disposeRunner", {"runnerId": rid}, 30)
        return None
    hp0 = {vis: (find(dv0, vis) or {}).get("hp") for vis in (FOE_MECH, FOE_PLAIN)}
    a0 = _cast(sid, rid, u["id"], u["id"], ANCESTRAL_FORTUNE)
    dv1 = _dv(sid, rid)
    hp1 = {vis: (find(dv1, vis) or {}).get("hp") for vis in (FOE_MECH, FOE_PLAIN)}
    live_tgt = [vis for vis in (FOE_MECH, FOE_PLAIN)
                if int(hp0.get(vis) or 0) != int(hp1.get(vis) or 0)]
    print("[replay:fortune] NATIF a frappe :", live_tgt, "hp", json.dumps(hp0), "->",
          json.dumps(hp1))

    st = _load(dv0, ob0, snap0, rng0, board_obj)
    port_tgt = _ancestral_fortune_attack_target(st, u["id"])
    print("[replay:fortune] PORT choisit :", port_tgt)
    # L'utilite de CHAQUE candidat, avec la MEME plage que le call-site natif
    # (`MinMaxDamage(entities, 1)` = moyenne des bornes, arrondie `RoundFix64Result`).
    from engine.runner.components import StatsComponent
    sc = st.get_entity(u["id"]).get_component(StatsComponent)
    lvl = int(getattr(sc.ctx, "active_ability_level", 0) or 0)
    mult = int(getattr(sc.ctx, "ability_variables_multiplier", 100) or 100)
    bmin = int(ability_var("AncestralFortune", "minDmg", lvl, multiplier_pct=mult) or 0)
    bmax = int(ability_var("AncestralFortune", "maxDmg", lvl, multiplier_pct=mult) or 0)
    avg = _round_fix64(Fraction(bmin + bmax, 2), 0)
    wt = damage_utility_weights()
    for vis, eid in ids.items():
        if eid is None:
            continue
        print("[replay:fortune] utilite(%s=%s) = %s" % (vis, eid,
                                                        _target_utility(st, eid, avg, avg, wt)))
    print("[replay:fortune] bornes ability minDmg=%s maxDmg=%s avg=%s" % (bmin, bmax, avg))

    # Cible FORCEE a celle du natif -> le DEGAT est-il fidele une fois le choix mis de cote ?
    for vis in (FOE_MECH, FOE_PLAIN):
        eid = ids.get(vis)
        if eid is None:
            continue
        st2 = _load(dv0, ob0, snap0, rng0, board_obj)
        ectx = ExecutionContext(state=st2, rng=st2.rng)
        ancestral_fortune_tree(eid).execute(entities_from_state(st2, u["id"], eid), ectx)
        atk = next((p for n, p in ectx.emitted if n == "AttackWithAttackDamage"), {})
        a = atk.get("attack") or {}
        print("[replay:fortune] port FORCE sur %-16s per-hit=%s total=%s crits=%s"
              % (vis, a.get("per_hit"), atk.get("total"), a.get("crits")))
        live_per = []
        b = int(hp0.get(vis) or 0)
        for h in _hits_from_events(a0, eid):
            live_per.append(b - h["hp"])
            b = h["hp"]
        if live_per:
            print("[replay:fortune] live     sur %-16s per-hit=%s total=%s"
                  % (vis, live_per, sum(live_per)))
    return rid


# ------------------------------------------------------------------------------------------------ #
# etage `armure` -- A/B DISCRIMINANT : l'ARMURE de la cible entre-t-elle dans le classement ?
# ------------------------------------------------------------------------------------------------ #
#
# Le port classe par `degat / maxHP` PRE-ARMURE (`operations/damage_utility._target_utility` :
# `armor = 0`, « la plage de degat est la MEME pour toutes les cibles »). Si c'etait vrai, deux
# cibles a maxHP EGAL seraient EX AEQUO et le tie-break trancherait -- donc la MEME victime quelle
# que soit leur armure. On egalise donc les maxHP et on ne fait varier QUE l'armure :
#
#   `haute` : `necroWarden` garde son armure native (la PLUS HAUTE des deux)
#   `basse` : `necroWarden` passe SOUS celle de `bloodMephiston`
#
# Si la victime NATIVE bascule d'un regime a l'autre, l'armure entre dans le classement et le port
# est FAUX. Si elle ne bascule pas, le port est fidele et le rouge vient d'ailleurs.
#
# ⚠ Ce montage a ete crafte APRES avoir constate que la validation anterieure du foyer
# (#419-r6-r1, Doombolt) tournait `FixedArmor = Armor = 0` sur TOUTES ses cibles -- un regime ou
# l'armure ne peut par construction rien discriminer.

ARMURE_REGIMES = {
    # maxHP EGALISES a ceux de `necroWarden` -> sans armure, les deux cibles sont EX AEQUO.
    "haute": ["--unit-stat", "bloodMephiston:Health=8536,RemainingHealth=8536"],
    "basse": ["--unit-stat", "bloodMephiston:Health=8536,RemainingHealth=8536",
              "--unit-stat", "necroWarden:Armor=300,FixedArmor=300"],
    # #527-r1 -- A/B du canal BLOCK, a UNE variable, sur le regime NOMINAL (rien d'autre n'est
    # touche). `aiPredict` montre que seule `bloodMephiston` porte un scenario de block
    # (`blockScenarioCount = 1`, `blockProbability = 30`) et que c'est ELLE que le natif prefere.
    # On lui RETIRE son block : si la victime NATIVE bascule vers `necroWarden`, le canal block est
    # etabli comme facteur du classement ; si elle ne bascule pas, il est ELIMINE a son tour.
    "block_off": ["--unit-stat", "bloodMephiston:BlockChance=0,BlockDamage=0"],
    # CONTRE-BRAS : le block est au contraire donne AUSSI a `necroWarden`. Les deux cibles en
    # portent alors un -- si le classement suit le block, la preference doit se defaire.
    "block_both": ["--unit-stat", "necroWarden:BlockChance=30,BlockDamage=1828"],
    # #527-r1 -- ENCADRER LE SEUIL D'ARMURE, ce qui MESURE le degat `d` que le selecteur emploie.
    # `GetDamageWithPiercing` bascule de la branche PERCAGE (`d x 65 %`) a la branche ARMURE
    # (`d - armure`) quand `armure < d x 35 %`. Les regimes deja joues bornent le seuil de
    # `necroWarden` entre 2008 (il gagne) et 2662 (il perd), donc `d` est entre 5737 et 7606.
    #   * un SEUL coup (`avg = 2044`) donnerait un seuil de 715 -- REFUTE, `necroWarden` gagne
    #     encore a 2008 ;
    #   * les TROIS coups de l'ability (`3 x 2044 = 6132`) donnent 2146.
    # On encadre donc 2146 : a 2100 la branche armure doit gagner pour `necroWarden` (il reste
    # prefere), a 2200 elle doit perdre (la preference bascule sur `bloodMephiston`). Si la bascule
    # tombe entre ces deux points, `d` vaut bien le degat des TROIS coups -- mesure, pas ajustement.
    "seuil_2100": ["--unit-stat", "necroWarden:Armor=2100,FixedArmor=2100"],
    "seuil_2200": ["--unit-stat", "necroWarden:Armor=2200,FixedArmor=2200"],
    # TEMOIN INVERSE : armures EGALISEES, maxHP laisses DIFFERENTS (8536 vs 9537). Le facteur que
    # le port porte DEJA (`degat / maxHP`) est alors le seul qui varie. Il etablit que le port
    # n'est pas faux de bout en bout -- il est AMPUTE de l'etage armure -- et que ce montage sait
    # rendre un ACCORD, donc que les deux bascules ci-dessus ne sont pas un artefact du montage.
    "hp": ["--unit-stat", "necroWarden:Armor=2008,FixedArmor=2008"],
}


def etage_armure(sid, args, regime="haute"):
    from engine.runner.abilities.votann import _ancestral_fortune_attack_target
    rid = build(args.state, f"{UTHAR},{SPARE}", f"{FOE_MECH},{FOE_PLAIN}",
                extra=ARMURE_REGIMES[regime])
    print("[armure:%s] runner %s" % (regime, rid))
    drive(sid, rid, UTHAR, FOE_MECH, 1)
    dv0, ob0, snap0, rng0, board_obj = _capture(sid, rid)
    u = find(dv0, UTHAR)
    ids = {vis: (find(dv0, vis) or {}).get("id") for vis in (FOE_MECH, FOE_PLAIN)}
    for vis, eid in ids.items():
        if eid is None:
            continue
        s = snap_stats(sid, rid, eid).get("stats") or {}
        d = find(dv0, vis) or {}
        print("[armure:%s] %-16s id=%s hp=%s health=%s fixedArmor=%s dist=%s"
              % (regime, vis, eid, d.get("hp"), s.get("health"), s.get("fixedArmor"),
                 hexgeo.distance(upos(u), upos(d))))
    tg = legal_targets(sid, rid, u["id"], ANCESTRAL_FORTUNE)
    if u["id"] not in tg:
        print("[armure:%s] ABORT : self hors fromHere %s" % (regime, tg))
        return rid
    hp0 = {vis: (find(dv0, vis) or {}).get("hp") for vis in (FOE_MECH, FOE_PLAIN)}
    _cast(sid, rid, u["id"], u["id"], ANCESTRAL_FORTUNE)
    dv1 = _dv(sid, rid)
    hp1 = {vis: (find(dv1, vis) or {}).get("hp") for vis in (FOE_MECH, FOE_PLAIN)}
    frappes = [vis for vis in (FOE_MECH, FOE_PLAIN)
               if int(hp0.get(vis) or 0) != int(hp1.get(vis) or 0)]
    st = _load(dv0, ob0, snap0, rng0, board_obj)
    port_tgt = _ancestral_fortune_attack_target(st, u["id"])
    port_vis = next((v for v, e in ids.items() if e == port_tgt), port_tgt)
    print("[armure:%s] NATIF frappe %s | PORT choisit %s" % (regime, frappes, port_vis))
    return rid


# ------------------------------------------------------------------------------------------------ #
# etage `predict` (#527-r1) -- la PREDICTION NATIVE par cible, au lieu de la deduire
# ------------------------------------------------------------------------------------------------ #
#
# Le calcul offline REFUTE l'explication « l'armure passe par le percage » sur le regime NOMINAL :
# `AncestralFortune` a le profil `Plasma`, dont le `PiercingDamageRatio` vaut 65, et
# `StaticBattleRules.Damage$$GetDamageWithPiercing` = `max(0, d - armure, d x pierce%)` rend
# EXACTEMENT la meme valeur (1328.6) pour armure 2662 et 2008 -- le plancher percage domine dans les
# deux cas. L'armure ne mord qu'a 300 (1744.0), ce qui explique le regime `basse` mais PAS le
# nominal. On arrete donc de deduire et on demande au NATIF ce qu'il predit, cible par cible.

def etage_predict(sid, args, regime=None):
    """`aiPredict` NATIF sur les DEUX cibles adjacentes, dans le regime demande (defaut : nominal).

    ⚠ `aiPredict` est Attack-based (`GetAllPredictions`) : ce n'est PAS le noeud de degat que
    `SortUnitsByDamageUtilitySelector` branche sur son slot +0x40 (`MinMaxDamage(entities, 1)`).
    Il repond donc a UNE question, et une seule : le degat que le natif predit contre une cible
    DEPEND-IL de son armure ? C'est le discriminant qui manque -- le reste (quel noeud de degat,
    quelle normalisation) ne se lit pas ici."""
    extra = ARMURE_REGIMES[regime] if regime else None
    rid = build(args.state, f"{UTHAR},{SPARE}", f"{FOE_MECH},{FOE_PLAIN}", extra=extra)
    print("[predict:%s] runner %s" % (regime or "nominal", rid))
    drive(sid, rid, UTHAR, FOE_MECH, 1)
    d = _dv(sid, rid)
    u = find(d, UTHAR)
    for vis in (FOE_MECH, FOE_PLAIN):
        f = find(d, vis)
        if f is None:
            continue
        s = snap_stats(sid, rid, f["id"]).get("stats") or {}
        pr = rpc(sid, "aiPredict", {"runnerId": rid, "unitId": u["id"], "targetId": f["id"],
                                    "fresh": True}, 90)
        print("[predict:%s] %-16s hp=%s health=%s fixedArmor=%s numberOfMembers=%s dist=%s"
              % (regime or "nominal", vis, f.get("hp"), s.get("health"), s.get("fixedArmor"),
                 s.get("numberOfMembers"), hexgeo.distance(upos(u), upos(f))))
        print("[predict:%s]   aiPredict = %s" % (regime or "nominal", json.dumps(pr)[:700]))
        print("[predict:%s]   traits    = %s" % (regime or "nominal", (f.get("traits") or [])))
    return rid


ETAGES = {"stats": etage_stats, "graviton": etage_graviton, "fortune": etage_fortune,
          "replay": etage_replay, "armure": etage_armure, "predict": etage_predict}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--etage", required=True, choices=sorted(ETAGES) + ["tous"])
    ap.add_argument("--regime", default="haute", choices=sorted(ARMURE_REGIMES) + ["nominal"],
                    help="etage `armure` : quel bras de l'A/B jouer")
    ap.add_argument("--state", default=str(LOGS / "_527_probe_state.json"))
    ap.add_argument("--crit", default=None, help="'CC,CD' passe a rl_duel --crit")
    ap.add_argument("--block", default=None, help="'BC,BD' passe a rl_duel --block-player")
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()
    sid = _resolve_session()
    noms = sorted(ETAGES) if args.etage == "tous" else [args.etage]
    for nom in noms:
        kw = {}
        if nom == "fortune":
            extra = []
            if args.crit:
                extra += ["--crit", args.crit]
            if args.block:
                extra += ["--block-player", args.block]
            kw["extra"] = extra or None
        if nom == "armure":
            kw["regime"] = args.regime
        if nom == "predict":
            kw["regime"] = args.regime if args.regime in ARMURE_REGIMES else None
        rid = ETAGES[nom](sid, args, **kw)
        if rid is not None and not args.keep:
            rpc(sid, "disposeRunner", {"runnerId": rid}, 30)
            print("[527] runner %s dispose" % rid)


if __name__ == "__main__":
    main()
