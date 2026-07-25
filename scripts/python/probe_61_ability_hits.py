"""#61 -- CANAL DE COUPS des attaques d'ABILITY : oracle NATIF (combat + prediction) vs MOTEUR.

Le cas #61 pose que `execute_ability_attack` recoit un `hits` FIXE et ne traverse pas la formule
de coups partagee. Ce probe MESURE, sur un runner isole, les DEUX faces separement (elles n'ont
PAS le meme verdict natif, cf. docs/rl/case-61-ability-hits-channel.md) :

  - `combat`     : caste REELLEMENT l'ability et compte les evenements de degat portant
                   `Active_Ability_Type == <ability>` et `Target_Id == <cible>` (= 1 event par COUP
                   applique, meme compteur que `tests/engine/runner/test_flail_swing_live.py`).
                   C'est l'oracle du nombre de coups de `AttackDamageOperation.Execute` ->
                   `IdunBattle.Operations.AttackDamageOperation$$GetAttackHits` (slot d'interface 0xb5).
  - `predict`    : `aiPlaybookPredict(...).appliedHits` = l'oracle du chemin DECISION
                   (`IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$GenerateMultiHitAttackPredictions`).
  - `offline`    : rejoue la MEME ability offline (Runner + `state.rng` cale via `dumpRng`) et
                   rend le nb de coups du port -- comparable coup a coup.

Le discriminant du canal = une cible porteuse d'un REDUCTEUR DE COUPS (`Parry_ReduceHits` -1 melee,
`Camouflage_HitReduction` -1/-2 ranged, `Diminutive_HitReduction` -1) confrontee a une cible TEMOIN
sans reducteur : si le canal est traverse, le natif rend `base-1` sur la porteuse et `base` sur le
temoin ; sinon `base` partout.

Aucune valeur attendue codee en dur : l'oracle est le natif qui tourne. ASCII only.

CLI (depuis scripts/python ; le runner doit exister -- cf. runner.md) :
  python probe_61_ability_hits.py combat  --sid S --runner R --caster U --ability A --target T
  python probe_61_ability_hits.py predict --sid S --runner R --caster U --ability A --targets "t1,t2"
  python probe_61_ability_hits.py offline --sid S --runner R --caster U --ability A --target T
  python probe_61_ability_hits.py both    --sid S --runner R --caster U --ability A --target T
"""
from __future__ import annotations

import argparse
import json
import sys

import rl_collect_batch as R


def _res(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def rpc(sid, method, body=None, timeout=120):
    return _res(R._rpc(sid, method, [body] if body is not None else [], timeout=timeout))


def decision(sid, rid):
    return rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)


def _effects(dv, uid):
    u = next((x for x in (dv.get("units") or []) if x.get("id") == uid), None)
    return [e.get("name") for e in ((u or {}).get("effects") or [])]


def _wait_castable(sid, rid, cid, ability, tid, max_turns=12):
    """Avance les tours jusqu'a ce que le cast `cid -> tid` soit LEGAL sans bouger (`fromHere`)."""
    for _ in range(max_turns):
        at = rpc(sid, "abilityTargets", {"runnerId": rid, "unitId": cid,
                                         "abilityType": ability}, 120)
        for u in (at.get("units") or []):
            ab = next((a for a in (u.get("abilities") or [])
                       if a.get("abilityId") == ability), None)
            if ab is None:
                continue
            if tid in [x.get("targetId") for x in (ab.get("fromHere") or [])]:
                return True
        rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    return False


def _cast_and_count(sid, rid, cid, tid, ability):
    """Caste l'ability et rend la liste des degats PAR COUP appliques a `tid` (1 entree = 1 coup)."""
    res = rpc(sid, "applyAction",
              {"runnerId": rid,
               "action": {"kind": "ability", "casterId": cid, "targetId": tid,
                          "abilityType": ability},
               "captureEvents": True}, 120)
    per = []
    for act in (res.get("actions") or []):
        for e in (act.get("events") or []):
            td = e.get("tags")
            if not td:
                continue
            td = json.loads(td) if isinstance(td, str) else td
            if "Amount" in td and td.get("Target_Id") == tid \
                    and td.get("Active_Ability_Type") == ability:
                per.append(td.get("Amount"))
    return per, res


def cmd_combat(a) -> int:
    """Oracle COMBAT : nb de coups REELLEMENT appliques par le natif."""
    if not _wait_castable(a.sid, a.runner, a.caster, a.ability, a.target):
        print("cast u%s -> u%s ab=%s : JAMAIS legal (fromHere)" % (a.caster, a.target, a.ability))
        return 2
    dv = decision(a.sid, a.runner)
    per, res = _cast_and_count(a.sid, a.runner, a.caster, a.target, a.ability)
    print("COMBAT u%-4s -> u%-4s ab=%-5s ok=%-5s HITS=%d per=%s"
          % (a.caster, a.target, a.ability, res.get("ok"), len(per), per))
    print("   tgt_effects=%s" % ",".join(_effects(dv, a.target)))
    print("   att_effects=%s" % ",".join(_effects(dv, a.caster)))
    return 0


def cmd_predict(a) -> int:
    """Oracle PREDICTION (`aiPlaybookPredict.appliedHits`) pour plusieurs cibles."""
    dv = decision(a.sid, a.runner)
    for tid in [int(x) for x in a.targets.split(",") if x.strip()]:
        r = rpc(a.sid, "aiPlaybookPredict", {"runnerId": a.runner, "unitId": a.caster,
                                             "targetId": tid, "abilityType": a.ability}, 90)
        ev = next((e for e in ((r or {}).get("events") or []) if e.get("targetId") == tid), None)
        print("PREDICT u%-4s -> u%-4s ab=%-5s hits=%s min=%s max=%s | tgt_effects=%s"
              % (a.caster, tid, a.ability,
                 (ev or {}).get("appliedHits"), (ev or {}).get("healthDmgMin"),
                 (ev or {}).get("healthDmgMax"), ",".join(_effects(dv, tid))))
    return 0


def _offline_cast(sid, rid, cid, tid, ability):
    """Rejoue l'ability OFFLINE depuis l'etat live courant, `state.rng` cale via `dumpRng`.
    Rend `(hits, per_hit)` ou `(None, raison)`."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.abilities.handler import ABILITY_CLASSES

    cls = ABILITY_CLASSES.get(int(ability))
    if cls is None:
        return None, "AUCUNE classe portee (ABILITY_CLASSES)"
    bg = rpc(sid, "boardGraph", {"runnerId": rid}, 60)
    board = Board(bg["tiles"], adjacency="native_sym") if isinstance(bg, dict) and bg.get("tiles") \
        else None
    dv = decision(sid, rid)
    ob = rpc(sid, "observeBattle", {"runnerId": rid}, 60)
    snap = rpc(sid, "combatSnapshot", {"runnerId": rid}, 90)
    st = load_state(dv, ob, snap, board=board)
    s0 = rpc(sid, "dumpRng", {"runnerId": rid}, 30)          # DERNIER RPC avant le cast live
    rng = IntBasedMersenneTwister()
    if isinstance(s0, dict) and s0.get("mt"):
        rng.mt = list(s0["mt"]); rng.mti = s0["mti"]
    else:
        rng.init_genrand(61001)
    st.rng = rng
    res = cls().execute_behaviour(st, cid, tid)
    atk = (res or {}).get("attack") or {}
    return atk.get("hits"), atk.get("per_hit")


def cmd_offline(a) -> int:
    """Nb de coups du MOTEUR pour la MEME ability (Runner offline, rng cale)."""
    hits, per = _offline_cast(a.sid, a.runner, a.caster, a.ability and a.target, a.ability)
    print("OFFLINE u%-4s -> u%-4s ab=%-5s HITS=%s per=%s"
          % (a.caster, a.target, a.ability, hits, per))
    return 0


def cmd_both(a) -> int:
    """REPLAY-DIFF : offline (rng cale) PUIS cast live, dans le MEME etat -> comparaison bit-exact
    du nb de coups ET du degat par coup. C'est le verdict du canal (case-61)."""
    if not _wait_castable(a.sid, a.runner, a.caster, a.ability, a.target):
        print("cast u%s -> u%s ab=%s : JAMAIS legal (fromHere)" % (a.caster, a.target, a.ability))
        return 2
    dv = decision(a.sid, a.runner)
    off_hits, off_per = _offline_cast(a.sid, a.runner, a.caster, a.target, a.ability)
    live_per, res = _cast_and_count(a.sid, a.runner, a.caster, a.target, a.ability)
    same_n = (off_hits == len(live_per))
    same_ph = (list(off_per or []) == list(live_per))
    print("BOTH u%-4s -> u%-4s ab=%-5s ok=%s" % (a.caster, a.target, a.ability, res.get("ok")))
    print("   NATIF  hits=%d per=%s" % (len(live_per), live_per))
    print("   MOTEUR hits=%s per=%s" % (off_hits, off_per))
    print("   verdict: HITS %s | PER-HIT %s"
          % ("OK" if same_n else "MISMATCH", "BIT-EXACT" if same_ph else "DIFF"))
    print("   tgt_effects=%s" % ",".join(_effects(dv, a.target)))
    return 0 if same_n else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["combat", "predict", "offline", "both"])
    ap.add_argument("--sid", type=int, required=True)
    ap.add_argument("--runner", type=int, required=True)
    ap.add_argument("--caster", type=int, required=True)
    ap.add_argument("--ability", type=int, required=True)
    ap.add_argument("--target", type=int)
    ap.add_argument("--targets", type=str, default="")
    a = ap.parse_args()
    return {"combat": cmd_combat, "predict": cmd_predict, "offline": cmd_offline,
            "both": cmd_both}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
