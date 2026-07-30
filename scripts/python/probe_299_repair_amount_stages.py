"""probe_299 -- DECOMPOSITION PAR ETAGE du montant de reparation (`RepairAbility$$RepairAmount`).

POURQUOI. La validation de #299 sur un 3e porteur (`necroSpyder`, le seul dont l'arme a 5 coups)
a rendu `live 6032 != offline 6025`. Un ecart de +7 sur ~6000 se « corrige » trivialement par un
facteur fitte -- et c'est exactement ce que la doctrine interdit. Ce probe MESURE chaque etage de la
formule pour trouver le PREMIER ou natif != port :

    RepairAmount = Multiply( StatAmount(Caster, ATTACK, Current),
                             Max( WeaponHighestHits(Caster), Get(1) ) )
    puis PredictRepair : (int)( Fix64(flatBonus + amount) * multiplier )   [RepairModifier]
    puis MaxFillUp     : Min(amount, CurrentMaximumValue - current)

Etages mesures, cote a cote :
  E1  ATTACK    : `combatSnapshot` (live) vs `UnitContext.stat(ATTACK)` (port)
  E2  HITS      : armes du kit gameconfig (max des `hits`) vs `UnitContext.normal_weapon_hits`
  E3  PRODUIT   : E1 x max(E2,1)
  E4  RENDU     : le delta HP REEL du cast live, et le montant rendu par le port

Usage:
    python probe_299_repair_amount_stages.py [--repairer necroSpyder]

ASCII only (console cp1252).
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "tests", "engine", "runner"))

import _repair_stage as S                                        # noqa: E402
from engine.entities.pathfinding.board import Board              # noqa: E402
from engine.entities.stats import StatPart, StatType             # noqa: E402
from engine.runner.abilities.repair import repair_amount         # noqa: E402
from engine.runner.components import HealthComponent, StatsComponent   # noqa: E402
from engine.runner.snapshot import load_state                    # noqa: E402


def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def _by_vis(state, vis):
    for uid, e in state.entities.items():
        sc = e.get_component(StatsComponent)
        if sc is not None and getattr(sc.ctx, "visual_id", None) == vis:
            return uid
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repairer", default="necroSpyder")
    ap.add_argument("--repairee", default=None,
                    help="cible MECANIQUE ; en choisir une a GROS hp_max pour que le manque depasse "
                         "le montant, sinon `MaxFillUp` sature et masque le montant brut")
    ap.add_argument("--hp-player", type=int, default=None, dest="hp_player",
                    help="`--hp-player N` (Health ET RemainingHealth = N) ; combine a --damaged, "
                         "il donne un hp_max ENORME et un manque enorme -> aucune saturation")
    ap.add_argument("--damaged", type=int, default=1,
                    help="RemainingHealth pose sur la cible ; 1 = manque MAXIMAL, pour que "
                         "`MaxFillUp` NE SATURE PAS et laisse voir le montant BRUT")
    args = ap.parse_args()

    import rl_collect_batch as R          # meme voie host que le conftest (import PARESSEUX)
    sid = R._resolve_session()

    def rpc(method, body=None, timeout=90):
        return _unwrap(R._rpc(sid, method, [body] if body is not None else [], timeout=timeout))

    S.REPAIRER_VIS = args.repairer
    if args.repairee:
        S.REPAIREE_VIS = args.repairee
    stage = S.build_stage(rpc, hp_player=args.hp_player, advance=0,
                          damaged_repairee=args.damaged)
    rid = stage["rid"]
    print("runner=%d repairer=%s" % (rid, args.repairer))

    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    board = Board(bg["tiles"], adjacency="native_sym") if bg and bg.get("tiles") else None
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
    state = load_state(dv, ob, snap, board=board)
    cid = _by_vis(state, args.repairer)
    tid = _by_vis(state, S.REPAIREE_VIS)
    if cid is None or tid is None:
        print("roster incomplet offline: cid=%s tid=%s" % (cid, tid))
        return 1

    sc = state.get_entity(cid).get_component(StatsComponent)
    ctx = sc.ctx

    # --- E1 ATTACK -------------------------------------------------------------------------------
    live_stats = {}
    for u in (snap or {}).get("units") or []:
        if u.get("visualId") == args.repairer:
            live_stats = u
            break
    print("\n[E1 ATTACK]")
    print("  port ctx.stat(ATTACK, CURRENT) = %s" % ctx.stat(StatType.ATTACK))
    print("  port ctx.attack                = %s" % getattr(ctx, "attack", None))
    for part in (StatPart.CURRENT, StatPart.INITIAL, StatPart.MODIFICATION):
        try:
            print("  port get_stat(ATTACK, %-12s) = %s"
                  % (part.name, ctx.stats.get_stat(int(StatType.ATTACK), int(part))))
        except Exception as e:
            print("  port get_stat(ATTACK, %-12s) = <%s>" % (part.name, e))
    keys = [k for k in live_stats if "ttack" in str(k) or "amage" in str(k)]
    print("  live combatSnapshot cles attack/damage : %s"
          % {k: live_stats.get(k) for k in keys})

    # --- E2 HITS ---------------------------------------------------------------------------------
    import gameconfig as GC
    kit = GC.unit(args.repairer) or {}
    hits_all = [w.get("hits") for w in (kit.get("weapons") or [])]
    print("\n[E2 HITS]")
    print("  gameconfig weapons hits = %s (max = %s)"
          % (hits_all, max([h for h in hits_all if h] or [1])))
    print("  port ctx.normal_weapon_hits = %s" % getattr(ctx, "normal_weapon_hits", None))

    # --- E3 PRODUIT ------------------------------------------------------------------------------
    port_amount = repair_amount(state, cid)
    print("\n[E3 PRODUIT] port repair_amount = %d" % port_amount)

    # --- E4 RENDU LIVE ---------------------------------------------------------------------------
    U = {u["squadId"]: u for u in (ob.get("units") or [])}
    sq_c = next((sq for sq, u in U.items() if u.get("visualId") == args.repairer), None)
    sq_t = next((sq for sq, u in U.items() if u.get("visualId") == S.REPAIREE_VIS), None)
    hc = state.get_entity(tid).get_component(HealthComponent)
    print("\n[E4 RENDU] cible hp=%s max=%s manque=%s"
          % (hc.hp, hc.hp_max, int(hc.hp_max) - int(hc.hp)))
    if sq_c is not None and sq_t is not None:
        pre = U[sq_t]["hp"]
        aid = (stage.get("repair_ability") or {}).get("abilityId")
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": sq_c, "targetId": sq_t, "abilityType": aid}}, 60)
        ob2 = rpc("observeBattle", {"runnerId": rid}, 40)
        post = {u["squadId"]: u["hp"] for u in (ob2.get("units") or [])}
        live = post.get(sq_t, pre) - pre
        print("  ability=%s  live_delta=%d  port=%d  ECART=%d"
              % (aid, live, port_amount, live - port_amount))
        atk = ctx.stat(StatType.ATTACK)
        hits = max(1, int(getattr(ctx, "normal_weapon_hits", 1) or 1))
        if hits:
            print("  live/hits = %.4f  (port ATTACK = %s)" % (live / float(hits), atk))
        print("  live - port = %d ; (live - port)/hits = %.4f" % (live - port_amount,
                                                                 (live - port_amount) / float(hits)))
    rpc("disposeRunner", {"runnerId": rid}, 40)
    return 0


if __name__ == "__main__":
    sys.exit(main())
