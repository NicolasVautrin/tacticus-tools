#!/usr/bin/env python
"""probe_226_hammer_foehammer -- CONFRONT LIVE des deux actives du profil POWER du lot #226 :

  * `Foehammer`     (1097, spaceRockfist «Arjac»)      -- 1x Power ranged + Stunned(1162) sur la cible,
                                                          degat = MinMaxDamage + extraDmg x #heros morts.
  * `HammerOfWrath` (1153, bloodIntercessor «Mataneo») -- Infiltrate(1046) self + CHARGE (MoveUnit) +
                                                          2x Power sur la cible + 1x Physical sur les
                                                          ennemis adjacents A LA CIBLE ; degat DOUBLE
                                                          si le caster porte 1332 (HP <= healthPct).

Le probe monte SES PROPRES runners depuis la seed BC (board choisi), en DEPLACANT le camp joueur au
CONTACT du camp adverse (`probe_112_darkangels._contact_placement`) et en patchant les PV PAR VISUAL-ID
(`hp_by_visual`) -- ce que `rl_duel build --hp-target` ne sait pas faire (il applique la MEME valeur a
toutes les a-units), or on veut un heros SACRIFIABLE a cote de cibles pleines.

CAS DISCRIMINANTS :
  foehammer -- meme cible, 0 puis 1 HEROS MORT dans la bataille (le terme `extraDmg x Count(
               UnitsWithTrait(AllDeadOrResurrectedUnits, Hero))`), + une 2e cible d'armure differente.
  hammer    -- Mataneo a PV pleins (pas de doublement) puis a ~33 % PV (effet 1332 ACTIF -> doublement),
               chaque cast portant DEUX volets de nombres differents (2x Power cible / 1x Physical
               adjacents).

Usage (depuis scripts/python, session Frida chaude) :
    python probe_226_hammer_foehammer.py --case recon
    python probe_226_hammer_foehammer.py --case foehammer
    python probe_226_hammer_foehammer.py --case hammer

ASCII only (cp1252). Dispose SES runners (jamais ceux des autres).
"""
from __future__ import annotations

import argparse
import copy
import json

import hexgeo
import probe_112_darkangels as PR
import rl_collect_batch as R

from engine.entities.pathfinding.board import Board
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.snapshot import load_state

FOEHAMMER = 1097
HAMMER_OF_WRATH = 1153
BOARD = "MC1_67"
RANK = 17


# --------------------------------------------------------------------------- build

def build_custom(sid, p_units, a_units, seed, board=BOARD, hp_by_visual=None, cap_wait_s=300):
    """`_build_custom_once` + ATTENTE du cap de runners (MAX_RUNNERS est PARTAGE entre agents : on
    attend qu'un slot se libere au lieu d'echouer, on ne dispose JAMAIS le runner d'un autre)."""
    import time
    deadline = time.time() + max(0, int(cap_wait_s))
    while True:
        try:
            return _build_custom_once(sid, p_units, a_units, seed, board, hp_by_visual)
        except RuntimeError as exc:
            if "cap reached" not in str(exc) or time.time() >= deadline:
                raise
            time.sleep(10)


def _build_custom_once(sid, p_units, a_units, seed, board=BOARD, hp_by_visual=None):
    """Runner isole avec rosters CHOISIS + camp joueur au contact + PV patches PAR VISUAL-ID.

    `hp_by_visual` = {visualId: (health, remaining, zero_armor)} -> ecrit `Health`/`RemainingHealth`
    (+ `Armor`/`FixedArmor` = 0 quand on veut un kill deterministe) dans le template `BC.Units` (meme
    canal que `rl_duel --hp-target`, mais PAR UNITE)."""
    seed_bc = R._load_seed_bc()
    board_dump = R._load_board_dump(board)
    template, pool, _mow = R._normalize_and_extract_pool(sid, seed_bc, RANK, board_dump=board_dump)
    miss = [u for u in list(p_units) + list(a_units) if u not in pool]
    if miss:
        raise RuntimeError("hors pool rank %d : %s" % (RANK, miss))
    bc = copy.deepcopy(template)
    R._patch_predefined_units(bc, list(a_units))
    for u in bc.get("Units", []):
        spec = (hp_by_visual or {}).get(u.get("VisualId"))
        if spec is None:
            continue
        health, remaining, zero_armor = spec
        u["Health"] = int(health)
        u["RemainingHealth"] = int(remaining)
        if zero_armor:
            u["Armor"] = 0
            u["FixedArmor"] = 0
    pos = PR._contact_placement(bc, len(p_units))
    player_units = [{"unitId": u, "playerId": R.PLAYER_ID_HUMAN,
                     "col": pos[i][0], "row": pos[i][1]} for i, u in enumerate(p_units)]
    resp = R._rpc(sid, "initAndStart",
                  [{"configJson": json.dumps(bc), "seed": seed, "playerUnits": player_units}],
                  timeout=60)
    rid = (resp.get("result") or {}).get("runnerId")
    if rid is None:
        raise RuntimeError("initAndStart KO: %s" % (resp.get("error") or resp))
    PR._rids.append(rid)
    return rid


# --------------------------------------------------------------------------- helpers live

def tags(e):
    tg = e.get("tags")
    if isinstance(tg, str):
        try:
            return json.loads(tg)
        except Exception:
            return {}
    return tg or {}


def live_hits(events, ability, target_id=None):
    """Coups LIVE d'une ability : (target_id -> [amount,...]) depuis les events `Amount` tagges
    `Active_Ability_Type == ability`."""
    out = {}
    for e in (events or []):
        tg = tags(e)
        if tg.get("Active_Ability_Type") != ability or "Amount" not in tg:
            continue
        t = tg.get("Target_Id")
        if target_id is not None and t != target_id:
            continue
        out.setdefault(t, []).append({"amt": tg.get("Amount"), "crit": tg.get("Attack_DidCrit"),
                                      "blk": tg.get("Attack_DidBlock")})
    return out


def capture(sid, rid):
    dec = PR.rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    ob = PR.rpc(sid, "observeBattle", {"runnerId": rid}, 60)
    snap = PR.rpc(sid, "combatSnapshot", {"runnerId": rid}, 90)
    bg = PR.rpc(sid, "boardGraph", {"runnerId": rid}, 60)
    rng = PR.rpc(sid, "dumpRng", {"runnerId": rid}, 30)
    return dec, ob, snap, bg, rng


def offline_state(dec, ob, snap, bg, rngdump):
    st = load_state(dec, ob, snap, board=Board(bg["tiles"], adjacency="native_sym"))
    r = IntBasedMersenneTwister()
    r.mt = list(rngdump["mt"])
    r.mti = rngdump["mti"]
    st.rng = r
    return st


def move_to(sid, rid, uid, col, row):
    return PR.act(sid, rid, {"kind": "move", "unitId": uid, "col": col, "row": row})


def free_ring(dv, center_uid, radius=1):
    pos = PR.positions(dv)
    occ = set(pos.values())
    c = pos[center_uid]
    return [p for p in hexgeo.ring(c[0], c[1], radius) if p not in occ]


def live_effect_posed(events, name, target_id):
    """L'effet nomme `name` a-t-il ete POSE sur `target_id` pendant CE cast ? Lecture des EVENTS
    (ground truth), pas du `decisionView` d'apres-coup : le natif ouvre un groupe
    `{kind:"group", source:"<NomEffet>", entity:<id d'entite-effet>}` puis emet les actions de cet
    effet sur l'unite affectee. Plus robuste que relire `decisionView.effects` apres le cast (dont la
    fenetre depend du tick de fin de tour)."""
    eids = {e.get("entity") for e in (events or [])
            if e.get("kind") == "group" and e.get("source") == name}
    if not eids:
        return False
    for e in (events or []):
        if e.get("kind") == "group":
            continue
        if e.get("entity") == target_id and tags(e).get("Effect_Id") in eids:
            return True
    return False


def eff_of(dv, uid, etype):
    u = next((x for x in (dv.get("units") or []) if x.get("id") == uid), None)
    return [e for e in ((u or {}).get("effects") or []) if e.get("effectType") == etype]


# --------------------------------------------------------------------------- cas

def case_recon(sid, seed):
    rid = build_custom(sid, ["spaceRockfist", "bloodIntercessor"],
                       ["necroOverlord", "necroWarden", "orksNob", "adeptCanoness"], seed)
    try:
        dv = PR.rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True})
        pos = PR.positions(dv)
        for u in (dv.get("units") or []):
            print("  u%-4s %-22s ctrl=%-5s pos=%s hp=%s eff=%s" % (
                u.get("id"), u.get("visualId"), u.get("ctrl"), pos.get(u["id"]), u.get("hp"),
                PR.eff_names(dv, u["id"])))
        bv = PR.units_by_visual(dv)
        for vid, ab in (("spaceRockfist", FOEHAMMER), ("bloodIntercessor", HAMMER_OF_WRATH)):
            if vid in bv:
                print("  legal fromHere %s(%d): %s" % (
                    vid, ab, PR.legal_from_here(sid, rid, bv[vid]["id"], ab)))
    finally:
        PR.dispose(sid, rid)


def _foehammer_cast(sid, rid, caster, target, label):
    """Capture -> cast LIVE -> replay OFFLINE -> comparaison per-coup + Stunned + #heros morts."""
    from engine.runner.abilities.spacewolves import FoehammerAbility
    dec, ob, snap, bg, rngd = capture(sid, rid)
    st = offline_state(dec, ob, snap, bg, rngd)
    pre_stun = eff_of(dec, target, 1162)
    r = PR.cast(sid, rid, caster, target, FOEHAMMER)
    lh = live_hits(r.get("events"), FOEHAMMER, target).get(target) or []
    dv2 = PR.rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True})
    post_stun = eff_of(dv2, target, 1162)
    res = FoehammerAbility().execute_behaviour(st, caster, target)
    off = ((res or {}).get("main_attack") or {}).get("per_hit") or []
    print("[%s] caster u%s -> u%s | live=%s off=%s | dead_heroes(off)=%s | stun pre=%s post=%s "
          "| ok=%s mutated=%s cur=%s legal=%s" % (
              label, caster, target, [h["amt"] for h in lh], off, (res or {}).get("dead_heroes"),
              len(pre_stun), len(post_stun), r.get("ok"), r.get("mutated"),
              dec.get("currentPlayer"), PR.legal_from_here(sid, rid, caster, FOEHAMMER)))
    return {"live": [int(h["amt"]) for h in lh], "off": [int(x) for x in off],
            "dead_heroes": (res or {}).get("dead_heroes"), "stun_post": len(post_stun),
            "ok_apply": r.get("ok"), "mutated": r.get("mutated")}


def _my_player(dv):
    """`currentPlayer` du camp CONTROLE (`ctrl == True` cote decisionView) -- l'id de joueur du runner
    n'est PAS `PLAYER_ID_HUMAN` (celui-la sert au deploiement, pas au tour)."""
    for u in (dv.get("units") or []):
        if u.get("ctrl"):
            return u.get("owner")
    return dv.get("currentPlayer")


def _next_turn(sid, rid, me, max_steps=8):
    """Passe au TOUR SUIVANT de mon camp SANS faire jouer l'IA : `endturn` clot le tour de l'equipe
    COURANTE (quelle qu'elle soit -- `applyAction` ne verifie pas la propriete), et on boucle jusqu'a
    ce que `decisionView.currentPlayer` redevienne `me`. La geometrie reste FIGEE (aucun move IA).

    ⚠ Le 1er `endturn` est INCONDITIONNEL : appelee alors que c'est DEJA mon tour, une version qui
    rendait la main tout de suite ne faisait PASSER AUCUN tour -- et une unite `TeleportStrike`
    n'atterrissait jamais (l'atterrissage a lieu en FIN de son 1er tour), donc ses passives (dont
    l'owner-effect `HammerOfWrath_ConditionalDamage`) n'etaient jamais initialisees."""
    PR.act(sid, rid, {"kind": "endturn"})
    for _ in range(max_steps):
        dv = PR.rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        if dv.get("currentPlayer") == me:
            return dv
        PR.act(sid, rid, {"kind": "endturn"})
    return PR.rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 120)


def case_foehammer(sid, seed, board=BOARD):
    """TROIS casts sur le MEME runner -- A (0 heros mort) et C (1 heros mort) sur la MEME cible :
    ils isolent le terme `extraDmg x Count(UnitsWithTrait(AllDeadOrResurrectedUnits, Hero))` ; le cast
    B tue le heros SACRIFIABLE (100 PV, armure 0) et sert de generateur de cadavre."""
    P = ["spaceRockfist"]
    A = ["necroOverlord", "necroWarden", "orksNob", "adeptCanoness"]
    rid = build_custom(sid, P, A, seed, board=board, hp_by_visual={"orksNob": (100, 100, True)})
    try:
        dv = PR.rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True})
        me = _my_player(dv)
        bv = PR.units_by_visual(dv)
        arjac = bv["spaceRockfist"]["id"]
        sacr = bv["orksNob"]["id"]
        pos = PR.positions(dv)
        print("[foehammer] arjac u%s @%s | sacrifiable u%s @%s" % (
            arjac, pos.get(arjac), sacr, pos.get(sacr)))
        for u in (dv.get("units") or []):
            print("   u%-4s %-18s ctrl=%-5s pos=%s hp=%s" % (u["id"], u.get("visualId"),
                                                             u.get("ctrl"), pos.get(u["id"]),
                                                             u.get("hp")))
        legal = PR.legal_from_here(sid, rid, arjac, FOEHAMMER)
        print("  legal fromHere:", legal)
        cands = [t for t in legal if t != sacr]
        if not cands or sacr not in legal:
            print("  ABANDON: cibles legales insuffisantes (%s)" % legal)
            return None
        t1 = cands[0]
        a = _foehammer_cast(sid, rid, arjac, t1, "A 0-dead")           # 0 heros mort
        _next_turn(sid, rid, me)
        b = _foehammer_cast(sid, rid, arjac, sacr, "B kill-sacr")      # tue le sacrifiable
        ob = PR.rpc(sid, "observeBattle", {"runnerId": rid}, 60)
        dead = [u["squadId"] for u in (ob.get("units") or []) if u.get("isDead")]
        print("  morts apres B : %s" % dead)
        _next_turn(sid, rid, me)
        c = _foehammer_cast(sid, rid, arjac, t1, "C 1-dead")           # 1 heros mort, MEME cible
        print("  VERDICT A live=%s off=%s dead=%s | C live=%s off=%s dead=%s" % (
            a["live"], a["off"], a["dead_heroes"], c["live"], c["off"], c["dead_heroes"]))
        return a, b, c
    finally:
        PR.dispose(sid, rid)


def _hammer_cast(sid, rid, caster, target, label):
    from engine.runner.abilities.bloodangels import HammerOfWrathAbility
    dec, ob, snap, bg, rngd = capture(sid, rid)
    st = offline_state(dec, ob, snap, bg, rngd)
    pos = PR.positions(dec)
    adj = [u["id"] for u in (dec.get("units") or [])
           if u["id"] not in (caster, target) and u.get("alive", True)
           and pos.get(u["id"]) and hexgeo.distance(pos[target], pos[u["id"]]) == 1]
    r = PR.cast(sid, rid, caster, target, HAMMER_OF_WRATH)
    lh = live_hits(r.get("events"), HAMMER_OF_WRATH)
    dv2 = PR.rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True})
    res = HammerOfWrathAbility().execute_behaviour(st, caster, target)
    off_main = ((res or {}).get("main_attack") or {}).get("per_hit") or []
    off_splash = {s["target"]: (s["attack"] or {}).get("per_hit") for s in (res or {}).get("splash") or []}
    print("[%s] caster u%s -> u%s | adj=%s" % (label, caster, target, adj))
    print("   LIVE   hits=%s" % ({k: [h["amt"] for h in v] for k, v in lh.items()},))
    print("   OFF    main=%s splash=%s moved_to=%s dest=%s doubled=%s" % (
        off_main, off_splash, (res or {}).get("moved_to"), (res or {}).get("dest"),
        (res or {}).get("doubled")))
    print("   LIVE   caster pos=%s | infiltrate=%s" % (
        PR.positions(dv2).get(caster), len(eff_of(dv2, caster, 1046))))
    return {"live": {k: [int(h["amt"]) for h in v] for k, v in lh.items()},
            "off_main": [int(x) for x in off_main],
            "off_splash": {k: [int(x) for x in (v or [])] for k, v in off_splash.items()},
            "moved_to": (res or {}).get("moved_to"), "dest": (res or {}).get("dest"),
            "doubled": (res or {}).get("doubled"),
            "live_pos": PR.positions(dv2).get(caster), "adj": adj,
            "ok": r.get("ok"), "mutated": r.get("mutated")}


def case_hammer(sid, seed, hp_frac=None, label="A full-hp", board=BOARD):
    """Mataneo charge une cible entouree -> 2x Power sur la cible + 1x Physical sur ses adjacents.
    `hp_frac` = fraction de PV de depart de Mataneo (None = plein ; 0.33 -> effet 1332 ACTIF ->
    doublement)."""
    P = ["bloodIntercessor"]
    A = ["necroOverlord", "necroWarden", "necroWarden", "necroWarden"]
    hp = None
    if hp_frac is not None:
        # `Health` (max) inchange, `RemainingHealth` abaisse -> le ratio courant/max tombe sous healthPct.
        hp = {"bloodIntercessor": (9035, int(9035 * hp_frac), False)}
    rid = build_custom(sid, P, A, seed, board=board, hp_by_visual=hp)
    try:
        # Mataneo demarre en Deep Strike (TeleportStrike) : les passives (dont l'owner-effect 1332)
        # ne sont initialisees qu'a L'ATTERRISSAGE, en fin de son 1er tour. On passe donc un tour.
        dv = PR.rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True})
        _next_turn(sid, rid, _my_player(dv))
        dv = PR.rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True})
        bv = PR.units_by_visual(dv)
        mat = bv["bloodIntercessor"]["id"]
        pos = PR.positions(dv)
        print("[hammer %s] mataneo u%s @%s hp=%s eff=%s" % (
            label, mat, pos.get(mat), bv["bloodIntercessor"].get("hp"), PR.eff_names(dv, mat)))
        for u in (dv.get("units") or []):
            print("   u%-4s %-18s ctrl=%-5s pos=%s hp=%s" % (u["id"], u.get("visualId"),
                                                             u.get("ctrl"), pos.get(u["id"]),
                                                             u.get("hp")))
        legal = PR.legal_from_here(sid, rid, mat, HAMMER_OF_WRATH)
        print("  legal fromHere:", legal)
        if not legal:
            print("  ABANDON: aucune cible legale")
            return None
        # cible = celle qui a le PLUS d'ennemis adjacents (exercer le volet splash)
        def n_adj(t):
            return sum(1 for u in (dv.get("units") or [])
                       if u["id"] != t and not u.get("ctrl") and pos.get(u["id"])
                       and hexgeo.distance(pos[t], pos[u["id"]]) == 1)
        tgt = max(legal, key=n_adj)
        return _hammer_cast(sid, rid, mat, tgt, "hammer %s" % label)
    finally:
        PR.dispose(sid, rid)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="recon")
    ap.add_argument("--seed", type=int, default=226226)
    ap.add_argument("--board", default=BOARD,
                    help="board de la bataille (GENERALISATION : la tuile de charge et le volet "
                         "splash dependent de la GEOMETRIE -- rejouer sur >= 2 couples board/seed)")
    a = ap.parse_args()
    sid = R._resolve_session()
    try:
        if a.case == "recon":
            case_recon(sid, a.seed)
        elif a.case == "foehammer":
            case_foehammer(sid, a.seed, board=a.board)
        elif a.case == "hammer":
            case_hammer(sid, a.seed, None, "A full-hp", board=a.board)
            case_hammer(sid, a.seed, 0.33, "B 33pct", board=a.board)
    finally:
        for rid in list(PR._rids):
            PR.dispose(sid, rid)


if __name__ == "__main__":
    main()
