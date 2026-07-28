"""Probe #88 (residu A1) -- preuve LIVE end-to-end du volet REVIVE de `FuelledByFury` (`ultraTitus`).

i2 : << The first time each turn **he defeats an enemy with an attack triggered by Final Vengeance**
he is immediately revived with a maximum of {hp} Health. >>

CHAINE NATIVE (RE) :
  Titus meurt -> `IdunBattle.Operations.KillUnitOperation$$Execute` emet `On(1 = PreUnitDeath)`
  -> `IdunBattleLogic.Entities.Abilities.Active.Loki.FinalJusticeAbility` (trait `FinalJustice`,
     `TriggeredAbilityType` 0x400 = 1024) porte UNE attaque normale sur la meilleure cible adjacente
  -> si cette attaque TUE, `IdunBattle.Operations.RecordKillOperation$$Execute` publie
     `On(3 = PendingDeathAdded)` {caster = Titus (le TUEUR), target = la victime}, en portant
     l'`AbilityEntities.TriggeringAbility` = 1024 (pose par
     `IdunBattle.Entities.Abilities.BaseTriggeredAbility$$Execute` avant le behaviour)
  -> `IdunBattleLogic.Entities.Abilities.Triggered.Loki.FuelledByFury_ReviveAbility$$CreateTrigger`
     matche (`HasEffect(self, 1324 ACTIF) & AreEqual(caster, self) & TriggeringAbilityIs(1024)`)
     et son behaviour POSE une `ReviveData` sur `UnitComponent+0xa8` de Titus
  -> de retour dans le `KillUnitOperation` de TITUS, la garde `if (!pendingRevive.HasValue)`
     ECHOUE -> **la mort de Titus est ANNULEE** et `ReviveUnitOperation` l'applique.

DISCRIMINANT LIVE (deux regimes, MEME geometrie, MEME coup fatal -- seule change la PV des ennemis) :
  * regime KILL   : les ennemis sont assez fragiles pour que la riposte les TUE
                    -> Titus est **VIVANT** apres le coup fatal, a `hp = min(reviveHP, maxPV)`
                       (valeur ABSOLUE) et **sur sa propre tuile** ;
  * regime NO-KILL: les ennemis survivent a la riposte
                    -> Titus est **MORT**.
La paire discrimine la chaine ENTIERE : sans le vecteur `On(3)`, sans le threading du
`TriggeringAbility`, ou sans le marqueur 1324, le regime KILL rendrait << mort >> comme l'autre.

Le probe confronte ensuite le PORT au live sur le MEME etat (`load_state` du runner, positions REELLES),
en rejouant la mort de Titus par le vrai chokepoint `AttackDamageOperation._fire_death_if_killed`.

Usage : python probe_88_fuelled_by_fury_revive.py   (ASCII only)
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

from rl_collect_batch import _resolve_session, _rpc  # noqa: E402
import hexgeo  # noqa: E402

ROOT = PYDIR.parents[1]
STATE = str(ROOT / "logs" / "_probe88_fbf_state.json")
HERO = "ultraTitus"
FOE_KILLER = "astraBullgryn"     # melee, gros degat de charge MESURABLE -> tue Titus
FOE_VICTIM = "orksNob"           # 2e ennemi melee : cible potentielle de la riposte
BOARD = "MC1_67"


def rpc(sid, m, args, t=90):
    return (_rpc(sid, m, [args], timeout=t).get("result") or {})


def build(hp_player: int, hp_target: int):
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", "31337", "--rank", "17",
           "--p-units", HERO, "--a-units", "%s,%s" % (FOE_KILLER, FOE_VICTIM),
           "--hp-player", str(hp_player), "--hp-target", str(hp_target),
           "--board", BOARD, "--state-file", STATE]
    p = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True)
    if p.returncode != 0:
        sys.stdout.write(p.stdout[-1500:])
        sys.stdout.write(p.stderr[-2000:])
        raise SystemExit("build KO")
    return json.loads(Path(STATE).read_text(encoding="utf-8"))["runnerId"]


def view(sid, rid):
    dv = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)
    ob = rpc(sid, "observeBattle", {"runnerId": rid}, 60)
    # BASE = `observeBattle` : c'est la SEULE vue qui garde les unites MORTES (`isDead`) meme quand la
    # bataille est finie et que `decisionView` ne rend plus rien (regime NO-KILL : Titus est la seule
    # unite du joueur, sa mort termine le match).
    out = {}
    for o in (ob.get("units") or []):
        out[o.get("visualId")] = {"id": o.get("id"), "col": o.get("col"), "row": o.get("row"),
                                  "hp": o.get("hp"), "hpMax": o.get("hpMax"),
                                  "isDead": o.get("isDead"), "effects": []}
    for u in (dv.get("units") or []):                    # enrichissement (id/pos/effets frais)
        vid = u.get("visualId")
        p = u.get("pos") or {}
        cur = out.setdefault(vid, {})
        cur["id"] = u.get("id", cur.get("id"))
        if p.get("col") is not None:
            cur["col"], cur["row"] = p.get("col"), p.get("row")
        cur.setdefault("hp", u.get("hp"))
        cur["effects"] = [e.get("name") for e in (u.get("effects") or [])]
    return dv, out


def act(sid, rid, action, t=90):
    return rpc(sid, "applyAction", {"runnerId": rid, "action": action}, t)


def movable(sid, rid, uid):
    r = rpc(sid, "aiMovableTiles", {"runnerId": rid, "unitId": uid}, 90)
    for u in (r.get("units") or []):
        if u.get("unitId") == uid:
            return [(t.get("col"), t.get("row")) for t in (u.get("tiles") or [])]
    return [(t.get("col"), t.get("row")) for t in (r.get("unionTiles") or [])]


def step_towards(sid, rid, uid, goal):
    tiles = movable(sid, rid, uid)
    if not tiles:
        return None
    tiles.sort(key=lambda t: hexgeo.distance(t, goal))
    act(sid, rid, {"kind": "move", "unitId": uid, "to": {"col": tiles[0][0], "row": tiles[0][1]}})
    return tiles[0]


def normal_attack_id(dv, caster_id, target_id):
    for p in (dv.get("attackPlans") or []):
        if p.get("unitId") == caster_id:
            for ev in (p.get("evals") or []):
                if ev.get("targetId") == target_id:
                    return ev.get("abilityId")
    return None


def setup(sid, hp_player, hp_target):
    """Monte un runner et DRIVE la geometrie : les DEUX ennemis au contact de Titus (le tueur pour
    porter le coup fatal, l'autre pour offrir une cible a la riposte FinalJustice)."""
    rid = build(hp_player, hp_target)
    dv, uu = view(sid, rid)
    for k in (HERO, FOE_KILLER, FOE_VICTIM):
        if k not in uu:
            rpc(sid, "disposeRunner", {"runnerId": rid}, 60)
            raise SystemExit("MISSING %s" % k)
    hid = uu[HERO]["id"]
    for _ in range(12):
        dv, uu = view(sid, rid)
        hpos = (uu[HERO]["col"], uu[HERO]["row"])
        d1 = hexgeo.distance((uu[FOE_KILLER]["col"], uu[FOE_KILLER]["row"]), hpos)
        d2 = hexgeo.distance((uu[FOE_VICTIM]["col"], uu[FOE_VICTIM]["row"]), hpos)
        if d1 <= 1 and d2 <= 1:
            break
        # tour du joueur : Titus avance vers les ennemis (les rapproche mutuellement)
        step_towards(sid, rid, hid, (uu[FOE_KILLER]["col"], uu[FOE_KILLER]["row"]))
        act(sid, rid, {"kind": "endturn"})
        # tour adverse : on pilote les DEUX ennemis vers Titus
        dv, uu = view(sid, rid)
        hpos = (uu[HERO]["col"], uu[HERO]["row"])
        for foe in (FOE_KILLER, FOE_VICTIM):
            step_towards(sid, rid, uu[foe]["id"], hpos)
        act(sid, rid, {"kind": "endturn"})
    dv, uu = view(sid, rid)
    return rid, dv, uu


def regime(sid, hp_player, hp_target, label):
    """Monte la geometrie, porte le coup FATAL sur Titus, rend son etat observe."""
    rid, dv, uu = setup(sid, hp_player, hp_target)
    try:
        hpos = (uu[HERO]["col"], uu[HERO]["row"])
        d1 = hexgeo.distance((uu[FOE_KILLER]["col"], uu[FOE_KILLER]["row"]), hpos)
        d2 = hexgeo.distance((uu[FOE_VICTIM]["col"], uu[FOE_VICTIM]["row"]), hpos)
        print("  [%s] hp_player=%d hp_target=%d  d(killer)=%d d(victim)=%d" % (
            label, hp_player, hp_target, d1, d2))
        if d1 > 1:
            print("  [%s] geometrie KO (tueur pas au contact)" % label)
            return None
        nid = normal_attack_id(dv, uu[FOE_KILLER]["id"], uu[HERO]["id"])
        if nid is None:
            print("  [%s] pas de plan killer->Titus" % label)
            return None
        hp0 = int(uu[HERO]["hp"])
        foes0 = {f: (uu[f]["hp"], uu[f]["isDead"]) for f in (FOE_KILLER, FOE_VICTIM)}
        act(sid, rid, {"kind": "ability", "casterId": uu[FOE_KILLER]["id"],
                       "targetId": uu[HERO]["id"], "abilityType": nid})
        _, uu2 = view(sid, rid)
        h = uu2[HERO]
        foes1 = {f: (uu2[f]["hp"], uu2[f]["isDead"]) for f in (FOE_KILLER, FOE_VICTIM)}
        killed = [f for f in foes1 if foes1[f][1] and not foes0[f][1]]
        res = {"hp0": hp0, "hp1": h["hp"], "isDead": h.get("isDead"),
               "pos0": hpos, "pos1": (h["col"], h["row"]),
               "effects": h.get("effects"), "foes_killed_by_retaliation": killed,
               "hp_max": h.get("hpMax")}
        print("  [%s] Titus hp %s -> %s  isDead=%s  pos %s -> %s  | riposte a tue: %s" % (
            label, hp0, h["hp"], h.get("isDead"), hpos, res["pos1"], killed or "(rien)"))
        return res
    finally:
        rpc(sid, "disposeRunner", {"runnerId": rid}, 60)
        print("  [%s] runner %s dispose" % (label, rid))


def calibrate(sid):
    """Degat du coup de charge du tueur sur Titus (PV enormes -> pas de mort) ET degat de l'attaque
    normale de Titus (pour dimensionner la PV des ennemis des deux regimes)."""
    rid, dv, uu = setup(sid, 90000, 90000)
    try:
        # Le pilotage de geometrie a CONSOMME l'action de Titus -> on cloture des tours jusqu'a ce qu'il
        # en ait une (les plans d'attaque n'existent que pour une unite qui peut encore agir).
        for _ in range(4):
            hero = next((u for u in (dv.get("units") or []) if u.get("visualId") == HERO), {})
            if hero.get("hasAction"):
                break
            act(sid, rid, {"kind": "endturn"})
            dv, uu = view(sid, rid)
        # (1) attaque normale de TITUS sur un ennemi -- proxy EXACT de la riposte FinalJustice
        #     (`UseActiveAbility(Self, best, UnitNormalAttackType)`). On mesure d'abord, tant que
        #     c'est le tour du joueur et que Titus a son action.
        dmg_by_hero = None
        tid = uu[FOE_VICTIM]["id"]
        tnid = normal_attack_id(dv, uu[HERO]["id"], tid)
        if tnid is None:                       # victime hors plan -> essaie l'autre ennemi
            tid = uu[FOE_KILLER]["id"]
            tnid = normal_attack_id(dv, uu[HERO]["id"], tid)
        if tnid is not None:
            f0 = int(uu[FOE_VICTIM]["hp"] if tid == uu[FOE_VICTIM]["id"] else uu[FOE_KILLER]["hp"])
            act(sid, rid, {"kind": "ability", "casterId": uu[HERO]["id"], "targetId": tid,
                           "abilityType": tnid})
            _, uuX = view(sid, rid)
            f1 = int(uuX[FOE_VICTIM]["hp"] if tid == uu[FOE_VICTIM]["id"] else uuX[FOE_KILLER]["hp"])
            dmg_by_hero = f0 - f1
        # (2) coup du tueur sur Titus
        dv2, uu2 = view(sid, rid)
        nid = normal_attack_id(dv2, uu2[FOE_KILLER]["id"], uu2[HERO]["id"])
        dmg_on_hero = None
        if nid is not None:
            hp0 = int(uu2[HERO]["hp"])
            act(sid, rid, {"kind": "ability", "casterId": uu2[FOE_KILLER]["id"],
                           "targetId": uu2[HERO]["id"], "abilityType": nid})
            _, uu3 = view(sid, rid)
            dmg_on_hero = hp0 - int(uu3[HERO]["hp"])
        return dmg_on_hero, dmg_by_hero
    finally:
        rpc(sid, "disposeRunner", {"runnerId": rid}, 60)


def offline_confront(hp_player, hp_target, expect_alive, label):
    """Rejoue la MEME mort dans le PORT, sur un etat monte a l'identique (positions REELLES pilotees,
    stats/traits/effets captes live), par le VRAI chokepoint `_fire_death_if_killed`."""
    from engine.runner.operations.damage import AttackDamageOperation
    from engine.runner.components import UnitComponent, HealthComponent, StatsComponent
    from engine.runner.snapshot import load_state
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.entities.pathfinding.board import Board
    sid = _resolve_session()
    rid, dv, uu = setup(sid, hp_player, hp_target)
    try:
        snap = rpc(sid, "combatSnapshot", {"runnerId": rid}, 90)
        ob = rpc(sid, "observeBattle", {"runnerId": rid}, 60)
        bg = rpc(sid, "boardGraph", {"runnerId": rid}, 60)
        board = Board(bg["tiles"], adjacency="evenq") if (bg or {}).get("tiles") else None
        st = load_state(dv, ob, snap, board=board)
        st.rng = IntBasedMersenneTwister(12345)
        hid = uu[HERO]["id"]
        e = st.get_entity(hid)
        hc = e.get_component(HealthComponent)
        hp_before = int(hc.hp)
        hc.hp = 0
        out = AttackDamageOperation._fire_death_if_killed(
            st, hid, uu[FOE_KILLER]["id"], hp_before, 0, e, damage=hp_before)
        uc = e.get_component(UnitComponent)
        alive = bool(uc.alive)
        print("  [offline %s] alive=%s hp=%s  attendu alive=%s" % (
            label, alive, hc.hp, expect_alive))
        for r in (out or []):
            if "kill_cancelled_by_revive" in r or r.get("ability") == "FuelledByFury":
                print("     %s" % json.dumps(r, default=str)[:220])
        _ = StatsComponent
        return alive == expect_alive, alive, hc.hp
    finally:
        rpc(sid, "disposeRunner", {"runnerId": rid}, 60)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline-only", action="store_true")
    a = ap.parse_args()
    sid = _resolve_session()
    print("[probe88] FuelledByFury (ultraTitus) -- volet REVIVE, preuve LIVE end-to-end")

    dmg_on_hero, dmg_by_hero = calibrate(sid)
    print("[probe88] calibrage: degat killer->Titus = %s ; degat Titus->ennemi = %s"
          % (dmg_on_hero, dmg_by_hero))
    if not dmg_on_hero or not dmg_by_hero:
        print("[probe88] calibrage KO")
        return 4

    # PV de Titus : LETALE mais PAS overkill (FinalJustice porte `NOT TargetIsOverkilled`).
    hp_player = int(dmg_on_hero * 0.85)
    hp_kill = max(1, int(dmg_by_hero * 0.50))      # riposte LETALE  -> revive attendu
    hp_nokill = int(dmg_by_hero * 3.0)             # riposte NON letale -> pas de revive
    print("[probe88] regimes: hp_player=%d (2xPV=%d > dmg=%d -> non-overkill)"
          % (hp_player, 2 * hp_player, dmg_on_hero))

    res = {}
    if not a.offline_only:
        print("[probe88] REGIME KILL   (ennemis a %d PV, riposte letale)" % hp_kill)
        res["kill"] = regime(sid, hp_player, hp_kill, "KILL")
        print("[probe88] REGIME NO-KILL (ennemis a %d PV, riposte non letale)" % hp_nokill)
        res["nokill"] = regime(sid, hp_player, hp_nokill, "NOKILL")

    print("[probe88] confrontation OFFLINE du port sur les MEMES etats")
    ok_a, alive_a, hp_a = offline_confront(hp_player, hp_kill, True, "KILL")
    ok_b, alive_b, hp_b = offline_confront(hp_player, hp_nokill, False, "NOKILL")

    ok = ok_a and ok_b
    print("[probe88] ---- SYNTHESE ----")
    if not a.offline_only:
        rk, rn = res.get("kill"), res.get("nokill")
        if rk is None or rn is None:
            print("  LIVE incomplet")
            ok = False
        else:
            print("  LIVE   KILL   : Titus isDead=%s hp=%s pos %s->%s (riposte a tue %s)"
                  % (rk["isDead"], rk["hp1"], rk["pos0"], rk["pos1"],
                     rk["foes_killed_by_retaliation"]))
            print("  LIVE   NOKILL : Titus isDead=%s hp=%s (riposte a tue %s)"
                  % (rn["isDead"], rn["hp1"], rn["foes_killed_by_retaliation"]))
            if rk["isDead"] or not rk["foes_killed_by_retaliation"]:
                print("  KO LIVE : le regime KILL n'a pas produit revive-apres-kill")
                ok = False
            if not rn["isDead"]:
                print("  KO LIVE : le regime NO-KILL laisse Titus vivant (pas de discriminant)")
                ok = False
            if rk["pos0"] != rk["pos1"]:
                print("  KO LIVE : position CHANGEE -> le revive doit etre EN PLACE")
                ok = False
            if not rk["isDead"] and rn["isDead"]:
                print("  PORT vs LIVE : alive KILL port=%s live=%s | NOKILL port=%s live=%s"
                      % (alive_a, not rk["isDead"], alive_b, not rn["isDead"]))
                if alive_a != (not rk["isDead"]) or alive_b != (not rn["isDead"]):
                    print("  KO : desaccord port/live")
                    ok = False
                elif rk["hp1"] is not None and hp_a is not None and int(rk["hp1"]) != int(hp_a):
                    print("  KO : hp de revive port=%s live=%s" % (hp_a, rk["hp1"]))
                    ok = False
    print("  OFFLINE KILL   : alive=%s hp=%s (attendu alive=True)" % (alive_a, hp_a))
    print("  OFFLINE NOKILL : alive=%s hp=%s (attendu alive=False)" % (alive_b, hp_b))
    print("[probe88] VERDICT: %s" % ("OK" if ok else "KO"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
