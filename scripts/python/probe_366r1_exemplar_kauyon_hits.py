"""#366-r1 G3 -- `1181 ExemplarOfTheKauyon_AdditionalHits` : MESURE du canal.

RE (decompile `rnca9r7q6c`, decompile = verite) --
`IdunBattle.Entities.Effects.Loki.ExemplarOfTheKauyon_AdditionalHitsEffectEffect$$CreateAdditionalHits`
-> `IdunBattle.Entities.Effects.EffectAdditionalHits$$Create` (canal #179, groupe a degat PROPRE),
et NON `CreateEffectHitsBonusForAttack` (canal des coups d'ARME, celui de `1183` -- meme porteur).

    amount  = ConfigVar( 0xb = dmg, GetAbilityState(effet), config@0x60 )
    hits    = Get( GetNumberConstant( 0x2f = nrOfHits ) )          # = 2
    profile = GetDamageProfile( config ).Value                      # = Blast
    trigger = get_OwnerIsCaster                                     # SEUL conjoint
    Create( &out, trigger, amount, 1, profile, hits, forceOverkill = false, param_8 = 0 )

Seul site de pose : `...ExemplarOfTheKauyonAbility$$ExecuteBehaviour` =
`Teleport(Caster, TargetTile) & If(trigger, AddEffect(0x49d) & PerformAIAttackFromCurrentPosition &
RemoveEffect(0x49d)) & Spawn(tauSmnDroneCommandLink)` -- l'effet ne vit QUE le temps de l'attaque
declenchee par le cast.

DEUX BRAS, sur DEUX runners (le port ne sait PAS rejouer 1087, qui est encore un NO-OP combat) :

  * BRAS A  -- `tauShadowsun` CASTE 1087 sur une tuile T : le natif la teleporte en T, pose 1181,
               joue son attaque normale, retire 1181. On compte les evenements de degat.
  * BRAS B  -- MEME geometrie, mais Shadowsun est POSEE en T et joue une attaque normale NUE
               (aucun 1181). C'est le CONTROLE : `nA - nB` doit valoir `nrOfHits = 2`.

Puis le PORT est confronte sur le snapshot du BRAS B (positions DEJA celles d'apres teleport, donc
aucune chirurgie de position offline) :

  * sans l'effet  -> doit rendre les coups d'ARME de B ;
  * avec l'effet  -> doit rendre B + 2 coups Blast, et la valeur de ces 2 coups doit egaler celle
    des 2 coups surnumeraires de A. Elle est DETERMINISTE des deux cotes : `param_8 = 0` rend la
    cellule DEGENEREE (`min == max`), et `IdunBattle.Core.HitDamage$$GetDamage` rend sans tirage
    quand `*param_1 == param_1[1]`.

Usage :
    python probe_366r1_exemplar_kauyon_hits.py [--board MC1_67] [--seed 777] [--keep]

ASCII only (console cp1252).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import urllib.request

import hexgeo

HOST = "http://127.0.0.1:8765"
PYDIR = os.path.dirname(os.path.abspath(__file__))

CARRIER = "tauShadowsun"          # HERO du pool -- porteur de l'active 1087
ALLY = "tauCrisis"                # l'allie dont le ring-1 fournit les tuiles de destination legales
ENEMY = "orksNob"                 # surchargeable (`--enemy`) : change l'armure, donc la VALEUR du coup
EXEMPLAR_OF_THE_KAUYON = 1087     # `ActiveAbilityType.ExemplarOfTheKauyon` (enum_maps.py)
EFFECT_NAME = "ExemplarOfTheKauyon_AdditionalHits"
EFFECT_TYPE = 1181                # `EffectType.ExemplarOfTheKauyon_AdditionalHits` (0x49d)


# ------------------------------------------------------------------ transport

def _sid():
    with urllib.request.urlopen(HOST + "/api/admin/status", timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))["session"]["id"]


def _rpc(sid, method, body=None, timeout=90):
    payload = json.dumps({"method": method,
                          "args": [body] if body is not None else []}).encode("utf-8")
    req = urllib.request.Request("%s/api/scripts/%s/rpc" % (HOST, sid), data=payload,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        out = json.loads(r.read().decode("utf-8"))
    return out.get("result") if isinstance(out, dict) and "result" in out else out


def build_extra(enemy: str = ENEMY) -> list:
    """Arguments `rl_duel build` du montage -- FOYER UNIQUE (#419-r6).

    Le probe et `test_exemplar_of_the_kauyon_hits_live.py` construisaient la MEME liste, chacun de
    son cote. La duplication n'est pas cosmetique : neutraliser ici laissait le test intact, et la
    mutation ne mordait pas -- constate a la mesure, pas a la relecture.

    Confonds NEUTRALISES : ce montage compare des coups au chiffre pres (`A - B` doit valoir
    exactement `nrOfHits`, et les 2 coups surnumeraires doivent etre EGAUX entre eux -- cellule
    degeneree `min == max`, donc AUCUN tirage). Un crit est un facteur qui s'applique APRES : il ne
    teste rien ici et deplace tout. Les QUATRE faces, car `--crit`/`--block-player` n'epinglent que
    les p-units et `--crit-target`/`--block-target` que les a-units.
    """
    return ["--p-units", "%s,%s" % (CARRIER, ALLY), "--a-units", enemy,
            "--hp-target", "300000", "--hp-player", "300000", "--no-ai",
            "--crit", "0,0", "--crit-target", "0,0",
            "--block-target", "0,0", "--block-player", "0,0"]


def build(seed, board, state_file):
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--board", board,
            "--state-file", state_file, *build_extra()]
    p = subprocess.run(argv, cwd=PYDIR, capture_output=True, text=True)
    if p.returncode != 0:
        print("[build] rc=%s\n%s\n%s" % (p.returncode, p.stdout[-1500:], p.stderr[-1500:]))
        return None
    with open(state_file, "r", encoding="utf-8") as f:
        return int(json.load(f)["runnerId"])


# ------------------------------------------------------------------ lecture / pilotage

def dview(sid, rid):
    return _rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)


def alive(dv):
    return [u for u in (dv.get("units") or []) if u.get("alive")]


def upos(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row")) if p.get("col") is not None else None


def place(sid, rid, uid, coord):
    _rpc(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": int(uid),
        "to": {"col": int(coord[0]), "row": int(coord[1])}}}, 60)
    u = next((x for x in alive(dview(sid, rid)) if x.get("id") == uid), None)
    return u is not None and upos(u) == (int(coord[0]), int(coord[1]))


def endturn(sid, rid):
    _rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)


def reach_my_turn(sid, rid, my_player, force_cycle=True, max_end=12):
    dv = dview(sid, rid)
    if force_cycle and dv.get("currentPlayer") == my_player:
        endturn(sid, rid)
        dv = dview(sid, rid)
    for _ in range(max_end):
        if dv.get("currentPlayer") == my_player:
            return dv
        endturn(sid, rid)
        dv = dview(sid, rid)
    return dv if dv.get("currentPlayer") == my_player else None


def normal_attack_type(dv, uid):
    for u in (dv.get("units") or []):
        if u.get("id") == uid:
            for a in (u.get("abilities") or []):
                if a.get("kind") == "normal":
                    return a.get("id")
    return None


def hits_from(res, attacker, target):
    """Amounts des evenements de degat `attacker -> target` de l'action, dans l'ordre emis."""
    a0 = (res.get("actions") or [{}])[0] if isinstance(res, dict) else {}
    out = []
    for e in (a0.get("events") or []):
        td = e.get("tags")
        if not td:
            continue
        td = json.loads(td) if isinstance(td, str) else td
        if ("Amount" in td and td.get("Attacker_Id") == attacker
                and td.get("Target_Id") == target):
            out.append({"amount": int(td["Amount"]),
                        "profile": td.get("DamageProfile_Type") or td.get("DamageProfile"),
                        "effect": td.get("Effect_Type"), "raw": td})
    return out, bool(a0.get("ok"))


# ------------------------------------------------------------------ geometrie du montage

def free_coords(board):
    return [board.coord(t) for t in sorted(board.by_id) if board.walkable(t)]


def arrange(sid, rid, board, enemy_visual=None, verbose=True):
    """Ancre l'ennemi sur une tuile a 6 voisins, pose l'ALLIE a d=2 de lui (son ring-1 fournit donc
    des destinations legales a d=1..3 de l'ennemi), et EXILE Shadowsun a d>=4 pour que le teleport
    soit reel. Rend `{carrier, ally, target, anchor, ally_pos, my_player}` ou None."""
    dv = dview(sid, rid)
    by_v = {u.get("visualId"): u for u in alive(dv)}
    car, ally = by_v.get(CARRIER), by_v.get(ALLY)
    enemy = by_v.get(enemy_visual if enemy_visual is not None else ENEMY)
    if car is None or ally is None or enemy is None:
        print("[arrange] ABORT unites absentes: %s" % sorted(by_v))
        return None
    my_player = car.get("owner")
    coords = free_coords(board)
    anchors = [c for c in coords
               if len([n for n in coords if hexgeo.distance(c, n) == 1]) == 6]
    for anc in anchors:
        apos = next((c for c in coords
                     if hexgeo.distance(c, anc) == 2
                     and len([n for n in coords if hexgeo.distance(c, n) == 1]) >= 5), None)
        if apos is None:
            continue
        cpos = next((c for c in coords
                     if hexgeo.distance(c, anc) >= 4 and hexgeo.distance(c, apos) >= 3), None)
        if cpos is None:
            continue
        if not (place(sid, rid, enemy["id"], anc) and place(sid, rid, ally["id"], apos)
                and place(sid, rid, car["id"], cpos)):
            continue
        if verbose:
            print("[arrange] enemy=%s ally=%s shadowsun=%s" % (anc, apos, cpos))
        return {"carrier": car["id"], "ally": ally["id"], "target": enemy["id"],
                "anchor": anc, "ally_pos": apos, "carrier_pos": cpos, "my_player": my_player}
    print("[arrange] ABORT aucune geometrie")
    return None


def legal_destinations(sid, rid, caster_id):
    """Tuiles legales du cast, LUES DU NATIF (`abilityTargets`) -- jamais re-derivees."""
    t = _rpc(sid, "abilityTargets",
             {"runnerId": rid, "unitId": caster_id, "abilityType": EXEMPLAR_OF_THE_KAUYON}, 150)
    out = []
    for u in (t.get("units") or []):
        for ab in (u.get("abilities") or []):
            if int(ab.get("abilityId") or -1) == EXEMPLAR_OF_THE_KAUYON:
                out += [c.get("tile") for c in (ab.get("fromHere") or [])
                        if isinstance(c, dict) and c.get("tile")]
    return [(int(c["col"]), int(c["row"])) for c in out]


# ------------------------------------------------------------------ les deux bras

def arm_cast(sid, rid, board, enemy_visual=None, verbose=True):
    """BRAS A -- le cast natif. Rend `{dst, hits, plan}` ou None."""
    plan = arrange(sid, rid, board, enemy_visual, verbose)
    if plan is None:
        return None
    if reach_my_turn(sid, rid, plan["my_player"]) is None:
        print("[A] ABORT tour non atteint")
        return None
    dests = legal_destinations(sid, rid, plan["carrier"])
    # La destination doit mettre l'ennemi A PORTEE de tir : on prend la PLUS PROCHE de lui parmi
    # les tuiles legales (elles sont toutes sur le ring-1 d'un allie, cf. i2).
    dests = sorted((d for d in dests if d != plan["anchor"]),
                   key=lambda d: hexgeo.distance(d, plan["anchor"]))
    if not dests:
        print("[A] ABORT aucune destination legale")
        return None
    dst = dests[0]
    if verbose:
        print("[A] dst=%s d(enemy)=%d (%d candidates)"
              % (dst, hexgeo.distance(dst, plan["anchor"]), len(dests)))
    res = _rpc(sid, "applyAction", {"runnerId": rid, "actions": [
        {"kind": "ability", "casterId": plan["carrier"],
         "to": {"col": dst[0], "row": dst[1]}, "abilityType": EXEMPLAR_OF_THE_KAUYON}]}, 180)
    hits, ok = hits_from(res, plan["carrier"], plan["target"])
    dv = dview(sid, rid)
    pos = {u["id"]: upos(u) for u in alive(dv)}
    return {"dst": dst, "hits": hits, "ok": ok, "plan": plan,
            "carrier_after": pos.get(plan["carrier"]),
            "summon": [u.get("visualId") for u in alive(dv)
                       if u.get("visualId") not in (CARRIER, ALLY, ENEMY)]}


def arm_control(sid, rid, board, dst, enemy_visual=None, verbose=True):
    """BRAS B -- MEME geometrie, Shadowsun POSEE en `dst`, attaque normale NUE.
    Rend `{hits, snapshot, plan, ability_type}` ou None."""
    plan = arrange(sid, rid, board, enemy_visual, verbose)
    if plan is None:
        return None
    if not place(sid, rid, plan["carrier"], dst):
        print("[B] ABORT pose en %s impossible" % (dst,))
        return None
    if reach_my_turn(sid, rid, plan["my_player"]) is None:
        print("[B] ABORT tour non atteint")
        return None
    dv = dview(sid, rid)
    pos = {u["id"]: upos(u) for u in alive(dv)}
    if pos.get(plan["carrier"]) != dst or pos.get(plan["target"]) != plan["anchor"]:
        print("[B] ABORT geometrie perdue apres cycle : %s" % pos)
        return None
    at = normal_attack_type(dv, plan["carrier"])
    if at is None:
        print("[B] ABORT pas d'attaque normale")
        return None
    snap = {"dv": dv,
            "ob": _rpc(sid, "observeBattle", {"runnerId": rid}, 60),
            "snap": _rpc(sid, "combatSnapshot", {"runnerId": rid}, 90),
            "rng": _rpc(sid, "dumpRng", {"runnerId": rid}, 40)}
    res = _rpc(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": plan["carrier"], "targetId": plan["target"],
        "abilityType": int(at)}}, 120)
    hits, ok = hits_from(res, plan["carrier"], plan["target"])
    return {"hits": hits, "ok": ok, "plan": plan, "snapshot": snap, "ability_type": at}


# ------------------------------------------------------------------ rejeu offline

def replay_offline(rec, board, with_effect):
    """Rejoue l'attaque normale du BRAS B, avec ou sans l'effet 1181 POSE sur Shadowsun
    (mirror de l'`AddEffect(0x49d, ..., Caster, Caster)` du natif).

    Rend `{weapon, extra, effects}`."""
    from engine.entities.effects import EffectFactory
    from engine.runner.messages import AttackUnitMessage
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.runner import Runner
    from engine.runner.snapshot import load_state
    s = rec["snapshot"]
    st = load_state(s["dv"], s["ob"], s["snap"], board=board)
    dump = s["rng"]
    if isinstance(dump, dict) and dump.get("mt"):
        rng = IntBasedMersenneTwister()
        rng.mt = list(dump["mt"])
        rng.mti = dump["mti"]
        st.rng = rng
    cid, tid = rec["plan"]["carrier"], rec["plan"]["target"]
    groups, mult, lvl = None, None, None
    if with_effect:
        from engine.runner.components import StatsComponent
        ent = st.get_entity(cid)
        sc = ent.get_component(StatsComponent) if ent is not None else None
        ctx = getattr(sc, "ctx", None)
        mult = int(getattr(ctx, "ability_variables_multiplier", 100) or 100)
        lvl = getattr(ctx, "active_ability_level", None) or 50
        eff = EffectFactory.create(
            {"name": EFFECT_NAME, "effectType": EFFECT_TYPE, "level": lvl, "source": cid},
            ability_variables_multiplier=mult, ability_level=lvl)
        groups = eff.additional_hit_groups()
        st.effects.add_effect(cid, eff)
    runner = Runner(st).install_default_handlers(20)
    runner.apply(AttackUnitMessage(attacker_id=cid, target_id=tid))
    last = runner.damage_handler.last or {}
    return {"weapon": list(last.get("per_hit") or []),
            "extra": list(((last.get("additional_hits") or {}).get("per_hit")) or []),
            "groups": groups, "mult": mult, "ability_level": lvl}


# ------------------------------------------------------------------ main

def main():
    global ENEMY
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--seed", default="777")
    ap.add_argument("--enemy", default=ENEMY)
    ap.add_argument("--mutant", action="store_true",
                    help="rejoue aussi le port AVEC l'inscription 1181 RETIREE du registre "
                         "(vue ROUGE : le port doit alors perdre les 2 coups)")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()
    ENEMY = a.enemy
    sid = _sid()
    print("[probe-1181] session=%s board=%s seed=%s" % (sid, a.board, a.seed))
    from engine.entities.pathfinding.board import Board
    tmp = tempfile.gettempdir()
    fa = os.path.join(tmp, "p1181_a_%s_%s.json" % (a.board, os.getpid()))
    fb = os.path.join(tmp, "p1181_b_%s_%s.json" % (a.board, os.getpid()))
    ra = rb = None
    try:
        ra = build(a.seed, a.board, fa)
        if ra is None:
            return 2
        bg = _rpc(sid, "boardGraph", {"runnerId": ra}, 90)
        board = Board(bg["tiles"], adjacency="native_sym")
        A = arm_cast(sid, ra, board, a.enemy)
        if A is None:
            return 3
        print("[A] ok=%s hits=%s" % (A["ok"], [h["amount"] for h in A["hits"]]))
        print("[A] profils=%s" % [h["profile"] for h in A["hits"]])
        print("[A] effect_types=%s" % [h["effect"] for h in A["hits"]])
        print("[A] carrier_after=%s (dst=%s) summons=%s"
              % (A["carrier_after"], A["dst"], A["summon"]))
        rb = build(a.seed, a.board, fb)
        if rb is None:
            return 4
        B = arm_control(sid, rb, board, A["dst"], a.enemy)
        if B is None:
            return 5
        print("[B] ok=%s hits=%s" % (B["ok"], [h["amount"] for h in B["hits"]]))
        print("[B] profils=%s" % [h["profile"] for h in B["hits"]])
        off0 = replay_offline(B, board, with_effect=False)
        off1 = replay_offline(B, board, with_effect=True)
        print("[OFF sans 1181] weapon=%s extra=%s" % (off0["weapon"], off0["extra"]))
        print("[OFF avec 1181] weapon=%s extra=%s" % (off1["weapon"], off1["extra"]))
        print("[OFF avec 1181] groupe=%s (ability_level=%s mult=%s)"
              % (off1["groups"], off1["ability_level"], off1["mult"]))
        print("[DELTA] nA=%d nB=%d nA-nB=%d (attendu nrOfHits=2)"
              % (len(A["hits"]), len(B["hits"]), len(A["hits"]) - len(B["hits"])))
        if a.mutant:
            # MUTANT (e) -- le port d'AVANT, reconstitue par RETRAIT de l'inscription : l'effet
            # retombe sur `BaseEffect`, dont `additional_hit_groups` rend None.
            from engine.entities.effects.factory import EFFECT_CLASSES
            saved = EFFECT_CLASSES.pop(EFFECT_NAME, None)
            try:
                mut = replay_offline(B, board, with_effect=True)
            finally:
                if saved is not None:
                    EFFECT_CLASSES[EFFECT_NAME] = saved
            print("[MUTANT sans inscription] weapon=%s extra=%s -> n=%d (live A n=%d, delta=%d)"
                  % (mut["weapon"], mut["extra"],
                     len(mut["weapon"]) + len(mut["extra"]), len(A["hits"]),
                     len(mut["weapon"]) + len(mut["extra"]) - len(A["hits"])))
        return 0
    finally:
        for rid in (ra, rb):
            if rid is not None and not a.keep:
                try:
                    _rpc(sid, "disposeRunner", {"runnerId": rid}, 30)
                except Exception:
                    pass
        for f in (fa, fb):
            try:
                os.unlink(f)
            except OSError:
                pass


if __name__ == "__main__":
    sys.exit(main())
