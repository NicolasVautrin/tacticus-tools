#!/usr/bin/env python
"""GROUND TRUTH LIVE des DEUX residus AnvilShield (#100) : `ApplyStun` + `FrozenAttackerAdvantage`.

i2 (passif `AnvilShield` de `spaceRockfist` << Arjac >>) :
  « Arjac blocks an additional 728 Damage and when he Blocks he covers the attacker's hex in Ice.
    **If Arjac is below 35% Health, or if his attacker is on a hex covered in Ice, he gains +20%
    Block chance and if he blocks a melee attack, the attacker is Stunned until the end of the
    attacker's next turn.** »

Decompile (build gqfc5mff6c) :
  - `IdunBattle.Entities.Effects.Loki.AnvilShield_BlockChanceBelowHealthCapEffect$$CreateActiveCondition`
      = AmountIsEqualOrGreater( Direct(GetNumberConstant(0x4f = healthPct = 35)),
                                StatAmount(Self@0x148, 5 = HEALTH, 1 = CURRENT_PCT) )
  - `IdunBattleLogic.Entities.Abilities.Triggered.Loki.AnvilShieldAbility_FrozenAttackerAdvantage$$CreateTrigger`
      = On(0x2a = PreUnitAbility) & IsNormalAttack & OwnerIsTarget
        & IsUnitOnTileWithEffect(caster@0x160, 0x11 = Ice)
        & !HasEffect(Self@0x148, 0x4b0, 1, 6) & !HasEffect(Self@0x148, 0x4b1, 1, 6)
  - `...AnvilShieldAbility_ApplyStun$$CreateTrigger`
      = On(0x3c = UnitBlocked) & OwnerIsTarget & IsMeleeAttack & !HasTrait(caster, 0x1b = Steppable)
        & IsUnit(caster) & IsAlive(caster)
        & ( HasEffect(target@0x178, 0x4b0, 1, 6) | HasEffect(target@0x178, 0x4b1, 1, 6) )
  (le 4e argument natif de `IdunBattleLogic.Entities.DSLTriggers$$HasEffect` est ACTIVE-ONLY, pas un
   minLevel : `IdunBattle.Entities.EntityExtensions$$IsOwnerOfEffect` teste `EffectComponent+0x5c` =
   le flag IsActive, mis a 0 par `IdunBattle.Operations.RefreshEffectsOperation$$DeactivateEffect`.)

Deux scenarios (ASCII only) :
  --scenario lowhp  : on descend Arjac sous 35 % PV -> 1200 devient ACTIF (blockChance 0 -> 20),
                      puis les coups MELEE bloques doivent Stun l'attaquant.
  --scenario frozen : Njal (LordOfTempests) GLACE la tuile d'un ennemi adjacent a Arjac ; quand cet
                      ennemi attaque Arjac (PLEINS PV), Arjac doit gagner 1201 (+20 blockChance),
                      puis un coup bloque doit Stun l'attaquant.

Usage : python probe_anvil_shield_residues.py --scenario frozen --build
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hexgeo                                            # noqa: E402
from rl_collect_batch import _resolve_session, _rpc      # noqa: E402

# SORTIE de run -> `logs/` RELATIF au checkout (#314) : un chemin absolu ferait
# ecrire ce probe dans l'arbre principal depuis un worktree d'agent.
STATE = (Path(__file__).resolve().parents[2] / "logs" / "runners"
         / "_probe100_anvil_state.json")
ARJAC, NJAL = "spaceRockfist", "spaceStormcaller"


def _r(sid, m, b, t=180):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def dv(sid, rid, full=False):
    return _r(sid, "decisionView",
              {"runnerId": rid, "maxRank": 0, "allAbilities": bool(full)}, 300)


def find(d, vis):
    return [u for u in (d.get("units") or []) if u.get("visualId") == vis]


def unit(d, uid):
    for u in (d.get("units") or []):
        if u.get("id") == uid:
            return u
    return None


def effs(u):
    return [(e.get("name"), e.get("level"), e.get("remaining"), e.get("source"))
            for e in ((u or {}).get("effects") or [])]


def names(u):
    return [e.get("name") for e in ((u or {}).get("effects") or [])]


def act(sid, rid, action):
    return _r(sid, "applyAction", {"runnerId": rid, "action": action, "captureEvents": False}, 300)


def dist(a, b):
    return hexgeo.distance((a["col"], a["row"]), (b["col"], b["row"]))


def stats_of(sid, rid, uid):
    cs = _r(sid, "combatSnapshot", {"runnerId": rid}, 300)
    for u in (cs.get("units") or []):
        if int(u.get("entityId") or -1) == int(uid):
            return u.get("stats") or {}
    return {}


def tile_effects(sid, rid, pos):
    tm = _r(sid, "tileMeta", {"runnerId": rid}, 300)
    for t in (tm.get("tiles") or []):
        if t.get("col") == pos["col"] and t.get("row") == pos["row"]:
            return [e.get("name") for e in (t.get("effects") or [])]
    return []


def normal_ids(sid, rid):
    """{unitId: abilityType de l'attaque NORMALE} — lu UNE fois (decisionView complet)."""
    d = dv(sid, rid, full=True)
    out = {}
    for u in (d.get("units") or []):
        for ab in (u.get("abilities") or []):
            if ab.get("kind") == "normal":
                out[u["id"]] = ab.get("id")
    return out, d


def build(seed: int, p_units: str, a_units: str, board: str, hp_player=None, block_target=None):
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--board", board,
           "--p-units", p_units, "--a-units", a_units, "--state-file", str(STATE)]
    if hp_player:
        cmd += ["--hp-player", str(hp_player)]
    if block_target:
        cmd += ["--block-target", block_target]
    subprocess.run(cmd, cwd=str(Path(__file__).resolve().parent), check=True)
    return json.loads(STATE.read_text())["runnerId"]


def report(sid, rid, tag, hpmax=None):
    d = dv(sid, rid)
    us = find(d, ARJAC)
    if not us:
        print("[%s] Arjac ABSENT" % tag)
        return None, d
    u = us[0]
    s = stats_of(sid, rid, u["id"])
    hp = u.get("hp")
    hm = hpmax or s.get("health") or 1
    print("[%s] Arjac u%s hp=%s/%s (%.1f pct) blockChance=%s blockDamage=%s"
          % (tag, u["id"], hp, hm, 100.0 * float(hp or 0) / float(hm),
             s.get("blockChance"), s.get("blockDamage")))
    print("      effets: %s" % (effs(u),))
    return u, d


def move_toward(sid, rid, d, movers, goal_pos):
    mov = _r(sid, "aiMovableTiles", {"runnerId": rid, "side": "all"}, 240)
    by_uid = {m.get("unitId"): (m.get("tiles") or []) for m in (mov.get("units") or [])}
    taken = {(u["pos"]["col"], u["pos"]["row"]) for u in (d.get("units") or []) if u.get("alive")}
    moved = 0
    for uid in movers:
        tiles = [t for t in by_uid.get(uid, []) if (t["col"], t["row"]) not in taken]
        if not tiles:
            continue
        best = min(tiles, key=lambda t: dist(t, goal_pos))
        if act(sid, rid, {"kind": "move", "unitId": uid,
                          "to": {"col": best["col"], "row": best["row"]}}).get("ok"):
            moved += 1
            taken.add((best["col"], best["row"]))
    return moved


def close_in(sid, rid, maxrounds=16):
    """DRIVE POSITIONS des DEUX camps : a chaque tour on deplace les unites du JOUEUR COURANT vers
    l'autre camp (les tuiles legales ne sont rendues qu'au joueur courant), jusqu'a l'adjacence."""
    for _ in range(maxrounds):
        d = dv(sid, rid)
        arj = (find(d, ARJAC) or [None])[0]
        if arj is None:
            return None, d
        foes = [u for u in (d.get("units") or [])
                if u.get("alive") and u.get("owner") != arj.get("owner") and u.get("visualId")]
        if not foes or any(dist(f["pos"], arj["pos"]) <= 1 for f in foes):
            return arj, d
        if d.get("currentPlayer") == arj.get("owner"):
            mine = [u["id"] for u in (d.get("units") or [])
                    if u.get("alive") and u.get("owner") == arj.get("owner")]
            move_toward(sid, rid, d, mine,
                        min(foes, key=lambda f: dist(f["pos"], arj["pos"]))["pos"])
        else:
            move_toward(sid, rid, d, [f["id"] for f in foes], arj["pos"])
        act(sid, rid, {"kind": "endturn"})
    d = dv(sid, rid)
    return (find(d, ARJAC) or [None])[0], d


def hit(sid, rid, nids, attacker_id, arjac_id, tag=""):
    """Un coup de l'attaquant sur Arjac + relecture des effets des DEUX. Renvoie (ok, arjac, att)."""
    r = act(sid, rid, {"kind": "ability", "casterId": attacker_id,
                       "targetId": arjac_id, "abilityType": nids.get(attacker_id)})
    d = dv(sid, rid)
    a = unit(d, arjac_id)
    f = unit(d, attacker_id)
    print("  %s coup u%s->u%s ok=%s | Arjac hp=%s eff=%s | attaquant eff=%s"
          % (tag, attacker_id, arjac_id, r.get("ok"), (a or {}).get("hp"), names(a), names(f)))
    return bool(r.get("ok")), a, f


def scenario_frozen(sid, rid, cycles):
    nids, d = normal_ids(sid, rid)
    arj = (find(d, ARJAC) or [None])[0]
    njal = (find(d, NJAL) or [None])[0]
    if arj is None or njal is None:
        print("[error] Arjac/Njal absents"); return 2
    act(sid, rid, {"kind": "finish", "unitId": arj["id"]})       # sortir du Deep Strike
    act(sid, rid, {"kind": "endturn"})
    report(sid, rid, "T0 PLEINS PV")

    arj, d = close_in(sid, rid)
    if arj is None:
        print("[error] close_in a echoue"); return 2

    stunned_seen, frozen_seen = 0, 0
    for c in range(cycles):
        d = dv(sid, rid)
        arj = (find(d, ARJAC) or [None])[0]
        njal = (find(d, NJAL) or [None])[0]
        if arj is None or not arj.get("alive"):
            print("[stop] Arjac mort"); break
        foes = [u for u in (d.get("units") or [])
                if u.get("alive") and u.get("owner") != arj.get("owner") and u.get("visualId")]
        adj = [f for f in foes if dist(f["pos"], arj["pos"]) <= 1]
        if not adj:
            if d.get("currentPlayer") != arj.get("owner"):
                move_toward(sid, rid, d, [f["id"] for f in foes], arj["pos"])
            act(sid, rid, {"kind": "endturn"})
            continue
        tgt = adj[0]
        if d.get("currentPlayer") == arj.get("owner"):
            # MON tour : Njal glace la tuile de l'attaquant (passif LordOfTempests sur son attaque).
            if njal is not None and njal.get("alive"):
                if dist(njal["pos"], tgt["pos"]) > 2:
                    move_toward(sid, rid, d, [njal["id"]], tgt["pos"])
                    d = dv(sid, rid)
                    njal = unit(d, njal["id"])
                if njal and dist(njal["pos"], tgt["pos"]) <= 2:
                    act(sid, rid, {"kind": "ability", "casterId": njal["id"],
                                   "targetId": tgt["id"], "abilityType": nids.get(njal["id"])})
                    d2 = dv(sid, rid)
                    t2 = unit(d2, tgt["id"])
                    if t2:
                        print("  [ice] tuile de u%s %s -> %s"
                              % (tgt["id"], t2["pos"], tile_effects(sid, rid, t2["pos"])))
            act(sid, rid, {"kind": "endturn"})
            continue
        # TOUR ENNEMI : l'attaquant (sur tuile glacee) frappe Arjac.
        ok, a, f = hit(sid, rid, nids, tgt["id"], arj["id"], tag="c%d" % c)
        if any(str(n).startswith("AnvilShield_Frozen") for n in names(a)):
            frozen_seen += 1
            print("  [1201] FrozenAttackerAdvantage sur Arjac : %s | blockChance=%s"
                  % (effs(a), stats_of(sid, rid, arj["id"]).get("blockChance")))
        if any(str(n).startswith("Stunned") for n in names(f)):
            stunned_seen += 1
            print("  [STUN] attaquant u%s : %s" % (tgt["id"], effs(f)))
        act(sid, rid, {"kind": "endturn"})
    report(sid, rid, "FIN")
    print("[info] cycles=%d frozen(1201)=%d stuns=%d" % (cycles, frozen_seen, stunned_seen))
    return 0


def scenario_lowhp(sid, rid, cycles):
    nids, d = normal_ids(sid, rid)
    arj = (find(d, ARJAC) or [None])[0]
    if arj is None:
        print("[error] Arjac absent"); return 2
    hpmax = float(stats_of(sid, rid, arj["id"]).get("health") or 1)
    act(sid, rid, {"kind": "finish", "unitId": arj["id"]})
    act(sid, rid, {"kind": "endturn"})
    report(sid, rid, "T0 PLEINS PV", hpmax)

    arj, d = close_in(sid, rid)
    if arj is None:
        print("[error] close_in a echoue"); return 2

    crossed, stuns, hits = False, 0, 0
    for _c in range(cycles):
        d = dv(sid, rid)
        arj = (find(d, ARJAC) or [None])[0]
        if arj is None or not arj.get("alive"):
            print("[stop] Arjac mort"); break
        pct = 100.0 * float(arj.get("hp") or 0) / hpmax
        if pct <= 35.0 and not crossed:
            crossed = True
            print("[cross] Arjac sous 35 pct (%.1f)" % pct)
            report(sid, rid, "SOUS 35 PCT", hpmax)
        if d.get("currentPlayer") == arj.get("owner"):
            act(sid, rid, {"kind": "endturn"}); continue
        foes = [u for u in (d.get("units") or [])
                if u.get("alive") and u.get("owner") != arj.get("owner") and u.get("visualId")]
        adj = [f for f in foes if dist(f["pos"], arj["pos"]) <= 1]
        if not adj:
            move_toward(sid, rid, d, [f["id"] for f in foes], arj["pos"])
            d = dv(sid, rid)
            arj = (find(d, ARJAC) or [None])[0]
            adj = [f for f in (d.get("units") or [])
                   if f.get("alive") and f.get("owner") != arj.get("owner") and f.get("visualId")
                   and dist(f["pos"], arj["pos"]) <= 1]
        for f in adj:
            if not f.get("hasAction"):
                continue
            ok, a, ff = hit(sid, rid, nids, f["id"], arj["id"], tag="h%d" % hits)
            hits += 1
            if any(str(n).startswith("Stunned") for n in names(ff)):
                stuns += 1
                print("  [STUN] attaquant u%s : %s (Arjac %s)" % (f["id"], effs(ff), effs(a)))
            if a is None or not a.get("alive"):
                break
        act(sid, rid, {"kind": "endturn"})
    report(sid, rid, "FIN", hpmax)
    print("[info] coups=%d stuns=%d" % (hits, stuns))
    return 0


def scenario_selfice(sid, rid, cycles):
    """DISCRIMINANT DETERMINISTE (block CRAFTE a 100 % via `--block-target 100,500` sur Arjac cote
    a-units) — la MEME attaque, repetee, bascule sur la SEULE variable « attaquant sur glace » :

      coup #1 : l'attaquant n'est PAS sur une tuile glacee -> Arjac BLOQUE (100 %) -> `ApplyIce` glace
                la tuile de l'attaquant, mais `ApplyStun` NE fire PAS (Arjac est a pleins PV : 1200
                INACTIF, et 1201 pas encore pose)  == CONTROLE NEGATIF ;
      coup #2 : l'attaquant est desormais SUR la glace -> `On(0x2a = PreUnitAbility)` pose 1201 -> le gate d'`ApplyStun`
                est vrai -> l'attaquant est **Stunned**.
    """
    nids, d = normal_ids(sid, rid)
    arj = (find(d, ARJAC) or [None])[0]
    if arj is None:
        print("[error] Arjac absent"); return 2
    print("[T0] Arjac u%s blockChance=%s" % (arj["id"], stats_of(sid, rid, arj["id"]).get("blockChance")))
    arj, d = close_in(sid, rid)
    if arj is None:
        print("[error] close_in a echoue"); return 2
    for c in range(cycles):
        d = dv(sid, rid)
        arj = (find(d, ARJAC) or [None])[0]
        if arj is None or not arj.get("alive"):
            print("[stop] Arjac mort"); break
        mine = [u for u in (d.get("units") or [])
                if u.get("alive") and u.get("owner") != arj.get("owner") and u.get("visualId")
                and dist(u["pos"], arj["pos"]) <= 1]
        if d.get("currentPlayer") != (mine[0]["owner"] if mine else None) or not mine:
            act(sid, rid, {"kind": "endturn"}); continue
        f = mine[0]
        on_ice = "Ice" in tile_effects(sid, rid, f["pos"])
        ok, a, f2 = hit(sid, rid, nids, f["id"], arj["id"], tag="c%d" % c)
        stun = [n for n in names(f2) if str(n).startswith("Stunned")]
        print("     attaquant-sur-glace(AVANT le coup)=%s -> stun=%s | tuile apres=%s | arjac=%s"
              % (on_ice, bool(stun), tile_effects(sid, rid, f["pos"]),
                 [e for e in effs(a) if str(e[0]).startswith("Stunned") or "Anvil" in str(e[0])]))
        if stun:
            print("     [STUN] %s" % [e for e in effs(f2) if str(e[0]).startswith("Stunned")])
        act(sid, rid, {"kind": "endturn"})
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", choices=["frozen", "lowhp", "selfice"], default="frozen")
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--seed", type=int, default=4100)
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--cycles", type=int, default=24)
    ap.add_argument("--hp-player", type=int, default=None)
    args = ap.parse_args()

    sid = _resolve_session()
    if args.build:
        if args.scenario == "selfice":
            # Arjac cote A (pour `--block-target`), attaquants MELEE cote P (tanky = ils survivent).
            rid = build(args.seed, "templSwordBrother,templAggressor", "spaceRockfist",
                        args.board, None, "100,500")
        else:
            rid = build(args.seed, "spaceRockfist,spaceStormcaller",
                        "orksNob,spaceWulfen,spaceHound", args.board, args.hp_player)
    else:
        rid = json.loads(STATE.read_text())["runnerId"]
    print("[live] session=%s runner=%s scenario=%s" % (sid, rid, args.scenario))
    return {"frozen": scenario_frozen, "lowhp": scenario_lowhp,
            "selfice": scenario_selfice}[args.scenario](sid, rid, args.cycles)


if __name__ == "__main__":
    sys.exit(main())
