"""Probe #BL-1020r -- la MAGNITUDE et le RETRAIT de l'effet `1027 HeraldOfTheApocalypse`.

L'effet etait POSE (live-confirme des deux cotes par case-bl-1029-1020) mais INERTE cote port :
aucune classe ne l'implementait, donc `EffectFactory` rendait un `BaseEffect` nu.

    `HeraldOfTheApocalypse_ExtraDamageEffect$$CreateEffectDamageBonusForAttack` =
        ForAddition( get_OwnerIsTarget & IsUnit(caster@DSLSelectors+0x48),
                     ConfigVar(8 = extraDmg, GetAbilityState(effet), config@+0x60) )
    `...$$CreateRemoveEffectTrigger` =
        On(9 = Attack, alive) & get_OwnerIsTarget & IsUnit(caster)

i2 : << Affected enemies receive +<extraDmg> Damage from the next attack made by a unit against
them. >>

MONTAGE (deux etages, un seul runner) :
  [A] Haarken caste 1020 sur une cible adjacente -> l'effet 1027 est pose sur elle (et sur
      l'ennemi derriere, s'il y en a un) ;
  [B] Abaddon attaque cette MEME cible a l'attaque normale -> le PREMIER coup doit porter
      `+extraDmg` en plus, puis 1027 doit DISPARAITRE de la cible.

CRITERE, et il est en DEUX temps parce qu'un seul ne separe rien :
  * la MAGNITUDE : le total offline du 1er coup doit egaler celui du live (accord bit-exact) ;
  * le RETRAIT : `1027` present sur la cible AVANT [B], absent APRES, des DEUX cotes. Sans ce
    second temps, un port qui donnerait le bonus a TOUS les coups passerait le premier critere.

ASCII only (cp1252). Usage: python probe_bl_1020r_herald_extra_damage.py [--seed 777] [--board MC1_67]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hexgeo  # noqa: E402
from rl_collect_batch import _resolve_session, _rpc  # noqa: E402
from engine.runner.snapshot import load_state  # noqa: E402
from engine.runner.runner import Runner  # noqa: E402
from engine.runner.messages import ActiveAbilityMessage, AttackUnitMessage  # noqa: E402
from engine.runner.components import HealthComponent, PositionComponent  # noqa: E402
from engine.entities.pathfinding.board import Board  # noqa: E402
from engine.entities.effect_type import EffectType  # noqa: E402
from engine.runner.prng import IntBasedMersenneTwister  # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
STATE = ROOT / "logs" / "runners" / "_bl_1020r_herald_extra.json"
ABADDON, HAARKEN = "blackAbaddon", "blackHaarken"
ENEMIES = "necroWarden,necroDestroyer,necroOverlord"
HERALD = 1020
HERALD_EFFECT = int(EffectType.HeraldOfTheApocalypse)          # 0x403 = 1027


def _r(sid, m, b, t=90):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def _seed_rng(s):
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"])
    rng.mti = s["mti"]
    return rng


def build(seed, board):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.unlink(missing_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
            "--state-file", str(STATE), "--board", board,
            "--p-units", f"{ABADDON},{HAARKEN}", "--a-units", ENEMIES,
            "--hp-target", "500000"]
    proc = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not STATE.exists():
        print(f"[h] build KO: {(proc.stderr or proc.stdout or '')[-600:]}")
        sys.exit(2)
    return json.loads(STATE.read_text())["runnerId"]


def _pos(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row"))


def _dv(rpc, rid):
    return rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)


def _units(dec):
    return [u for u in (dec.get("units") or []) if u.get("alive")]


def _by_vis(dec, vis):
    return next((u for u in _units(dec) if u.get("visualId") == vis), None)


def _act(rpc, rid, action, t=180):
    return rpc("applyAction", {"runnerId": rid, "action": action}, t) or {}


def _has_1027(dec, uid):
    u = next((x for x in (dec.get("units") or []) if x.get("id") == uid), None)
    return any(e.get("effectType") == HERALD_EFFECT and not e.get("removed")
               for e in ((u or {}).get("effects") or []))


def _off_has_1027(state, uid):
    fx = getattr(state, "effects", None)
    if fx is None:
        return False
    return any((not e.consumed) and e.effect_type == HERALD_EFFECT
               for e in fx.by_unit.get(int(uid), []))


def _tags(ev):
    try:
        return json.loads(ev.get("tags") or "{}")
    except Exception:
        return {}


def _amounts(r, uid):
    out = []
    for a in (r or {}).get("actions") or []:
        for ev in (a.get("events") or []):
            t = _tags(ev)
            if t.get("Target_Id") == uid and "Amount" in t:
                out.append(int(t["Amount"]))
    for ev in (r or {}).get("cascade") or []:
        t = _tags(ev)
        if t.get("Target_Id") == uid and "Amount" in t:
            out.append(int(t["Amount"]))
    return out


def _place_adjacent(rpc, rid, mover, anchor_pos, board, occupied):
    ring = [board.coord(t) for t in board.neighbours(board.id_at(*anchor_pos))]
    dest = next((n for n in ring if n not in occupied), None)
    if dest is None:
        return False
    _act(rpc, rid, {"kind": "move", "unitId": mover, "to": {"col": dest[0], "row": dest[1]}})
    return True


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--board", default="MC1_67")
    a = ap.parse_args(argv if argv is not None else sys.argv[1:])

    sid = _resolve_session()

    def rpc(m, b, t=90):
        return _r(sid, m, b, t)

    rid = build(a.seed, a.board)
    print(f"[h] runner={rid} seed={a.seed} board={a.board}")
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            print("[h] boardGraph KO")
            return 2
        board = Board(bg["tiles"], adjacency="native_sym")

        dec = _dv(rpc, rid)
        haar, abad = _by_vis(dec, HAARKEN), _by_vis(dec, ABADDON)
        if haar is None or abad is None:
            print("[h] roster incomplet")
            return 2
        # cible = un ennemi, amene au contact de Haarken (1020 exige une cible ADJACENTE :
        # preset `TargetingRange statics+0x30`, `onlyAdjacent = True`).
        foe = next((u for u in _units(dec) if u.get("owner") != haar.get("owner")), None)
        if foe is None:
            print("[h] aucun ennemi")
            return 2
        occ = {_pos(u) for u in _units(dec)}
        if hexgeo.distance(_pos(foe), _pos(haar)) != 1:
            _place_adjacent(rpc, rid, foe["id"], _pos(haar), board, occ)
        dec = _dv(rpc, rid)
        haar, abad = _by_vis(dec, HAARKEN), _by_vis(dec, ABADDON)
        foe = next((u for u in _units(dec) if u.get("id") == foe["id"]), None)
        if foe is None or hexgeo.distance(_pos(foe), _pos(haar)) != 1:
            print(f"[h] cible pas au contact de Haarken -- montage non joue")
            return 2

        # --- [A] LIVE : Haarken caste 1020 -> pose de 1027 -----------------------------------
        _act(rpc, rid, {"kind": "ability", "casterId": haar["id"], "targetId": foe["id"],
                        "abilityType": HERALD}, 240)
        dec = _dv(rpc, rid)
        if not _has_1027(dec, foe["id"]):
            print("[h] 1027 ABSENT de la cible apres le cast -- l'etage [A] n'a rien pose")
            return 2
        print(f"[h] [A] 1027 pose sur la cible {foe['id']} (live)")

        # --- [B] Abaddon au contact de la cible, puis attaque normale -------------------------
        dec = _dv(rpc, rid)
        abad = _by_vis(dec, ABADDON)
        occ = {_pos(u) for u in _units(dec)}
        if hexgeo.distance(_pos(abad), _pos(foe)) != 1:
            _place_adjacent(rpc, rid, abad["id"], _pos(foe), board, occ)
        dec = _dv(rpc, rid)
        abad = _by_vis(dec, ABADDON)
        tgt = next((u for u in _units(dec) if u.get("id") == foe["id"]), None)
        if tgt is None or hexgeo.distance(_pos(abad), _pos(tgt)) != 1:
            print("[h] Abaddon pas au contact -- etage [B] non joue")
            return 2
        na = next((ab for ab in (abad.get("abilities") or []) if ab.get("kind") == "normal"), None)
        if na is None:
            print("[h] Abaddon sans attaque normale au dv")
            return 2

        ob = rpc("observeBattle", {"runnerId": rid}, 60)
        snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
        s0 = rpc("dumpRng", {"runnerId": rid}, 30)
        state = load_state(dec, ob, snap, board=board)
        if s0 and s0.get("mt"):
            state.rng = _seed_rng(s0)
        off_before = _off_has_1027(state, tgt["id"])
        hc = state.get_entity(tgt["id"]).get_component(HealthComponent)
        hp0_off = int(hc.hp)
        runner1 = Runner(state).install_default_handlers(20)
        runner1.apply(AttackUnitMessage(attacker_id=abad["id"], target_id=tgt["id"]))
        off_total = hp0_off - int(hc.hp)
        off_hits = list((runner1.damage_handler.last or {}).get("per_hit") or [])
        off_after = _off_has_1027(state, tgt["id"])

        # CONTRE-EPREUVE INTERNE : le MEME etat rejoue avec la classe d'effet 1027 NEUTRALISEE.
        # Sans elle, un accord ne separe pas << le port applique le bon bonus >> de << le port
        # n'applique rien et le natif non plus >>. On mute la classe, pas les donnees.
        import engine.entities.effects.loki.damage_reduction as DR
        state2 = load_state(dec, ob, snap, board=board)
        if s0 and s0.get("mt"):
            state2.rng = _seed_rng(s0)
        hc2 = state2.get_entity(tgt["id"]).get_component(HealthComponent)
        hp0_off2 = int(hc2.hp)
        _orig = DR.HeraldOfTheApocalypseExtraDamageEffect.create_effect_damage_malus_for_defense
        DR.HeraldOfTheApocalypseExtraDamageEffect.create_effect_damage_malus_for_defense = (
            lambda self, is_melee=None, damage_profile=None, attacker_ctx=None: None)
        try:
            Runner(state2).install_default_handlers(20).apply(
                AttackUnitMessage(attacker_id=abad["id"], target_id=tgt["id"]))
        finally:
            DR.HeraldOfTheApocalypseExtraDamageEffect.create_effect_damage_malus_for_defense = _orig
        off_total_sans = hp0_off2 - int(hc2.hp)

        r = _act(rpc, rid, {"kind": "ability", "casterId": abad["id"], "targetId": tgt["id"],
                            "abilityType": int(na["id"])}, 240)
        dec2 = _dv(rpc, rid)
        live_hits_all = _amounts(r, tgt["id"])
        # L'AGREGAT COMPARE EST LA SEQUENCE DES COUPS D'ARME, coup par coup -- ni le delta de PV
        # (qui capte des canaux sans `Target_Id`), ni la somme de TOUS les tags `Amount` (le flux
        # live en porte un dernier, d'un ordre de grandeur superieur, qui n'est pas un coup).
        # On compare donc les `len(off_hits)` PREMIERS coups live aux coups offline.
        n = len(off_hits)
        live_hits = live_hits_all[:n] if n else []
        live_total = sum(live_hits)
        live_after = _has_1027(dec2, tgt["id"])
        print(f"[h] [B] MAGNITUDE  offline={off_total}  live={live_total}  "
              f"| coups off={off_hits} live={live_hits} (flux complet={live_hits_all})")
        print(f"[h] [B] CONTRE-EPR offline SANS la classe 1027 = {off_total_sans} "
              f"(ecart = {off_total - off_total_sans})")
        print(f"[h] [B] RETRAIT    1027 avant off={off_before} | apres off={off_after} "
              f"live={live_after}")

        ok_mag = bool(off_hits) and off_hits == live_hits
        ok_disc = off_total_sans != off_total     # la classe MORD -- sinon l'accord ne prouve rien
        ok_rm = (off_before is True) and (off_after is False) and (live_after is False)
        if not ok_disc:
            print("[h]   LA CLASSE 1027 NE MORD PAS -- accord SANS VALEUR")
        if not ok_mag:
            print("[h]   DESACCORD de MAGNITUDE")
        if not ok_rm:
            print("[h]   DESACCORD de RETRAIT")
        print("[h] " + ("PROBE OK" if (ok_mag and ok_rm and ok_disc) else "PROBE KO"))
        return 0 if (ok_mag and ok_rm and ok_disc) else 1
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 60)


if __name__ == "__main__":
    raise SystemExit(main())
