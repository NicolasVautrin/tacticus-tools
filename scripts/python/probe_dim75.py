"""#75 VALIDATION ADVERSARIALE de `Diminutive` (trait 1032) -- probe parametre.

Confronte, sur un runner ISOLE, le nombre de COUPS predit/applique par le NATIF au nombre
de coups du MOTEUR Python, cible = summon `orksGrot` (porteur Diminutive) vs cible de
CONTROLE (sans Diminutive), pour des attaquants CHOISIS (1 coup / multi-coups / melee /
ranged / ability). Sert a attaquer les points NON couverts par le port :
  - plancher min=1 (attaque a 1 SEUL coup),
  - face PREDICTION (aiPlaybookPredict.appliedHits) et non seulement le combat,
  - attaques d'ABILITY (pas seulement l'attaque normale),
  - CUMUL avec un autre modificateur du meme canal (LightCover tuile DryBush, BigTarget aura,
    MasterAnnihilator +1 coup).

Oracle = le NATIF qui tourne (aucune valeur attendue codee en dur). ASCII only.

CLI :
  python probe_dim75.py map      --sid S --runner R
  python probe_dim75.py move     --sid S --runner R --unit U --to C,R
  python probe_dim75.py endturn  --sid S --runner R
  python probe_dim75.py cast     --sid S --runner R --caster U --ability A [--to C,R] [--target T]
  python probe_dim75.py hits     --sid S --runner R --attackers "u1,u2" --targets "t1,t2" [--abilities "69,..."]
  python probe_dim75.py attack   --sid S --runner R --caster U --target T --ability A
"""
from __future__ import annotations

import argparse
import sys

import rl_collect_batch as R


def _res(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def rpc(sid, method, body=None, timeout=90):
    return _res(R._rpc(sid, method, [body] if body is not None else [], timeout=timeout))


def decision(sid, rid):
    return rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)


def cmd_map(a) -> int:
    dec = decision(a.sid, a.runner)
    obs = rpc(a.sid, "observeBattle", {"runnerId": a.runner}, 40)
    dead = {u.get("id") for u in (obs.get("units") or []) if u.get("isDead")}
    print("currentPlayer=%s stage=%s" % (dec.get("currentPlayer"), dec.get("stage")))
    for u in (dec.get("units") or []):
        eff = [e.get("name") for e in (u.get("effects") or [])]
        abs_ = ["%s:%s(%s)" % (x.get("kind"), x.get("id"), x.get("name"))
                for x in (u.get("abilities") or [])]
        print("u%-4s %-22s team=%s pos=(%s,%s) hp=%s dead=%s\n      ab=%s\n      eff=%s" % (
            u.get("id"), u.get("visualId"), u.get("team"),
            (u.get("pos") or {}).get("col"), (u.get("pos") or {}).get("row"),
            u.get("hp"), u.get("id") in dead, abs_, eff))
    return 0


def cmd_move(a) -> int:
    col, row = [int(x) for x in a.to.split(",")]
    r = rpc(a.sid, "applyAction", {"runnerId": a.runner,
                                   "action": {"kind": "move", "unitId": a.unit,
                                              "to": {"col": col, "row": row}}}, 60)
    print("move u%s -> (%s,%s) ok=%s mutated=%s stage=%s cp=%s err=%s" % (
        a.unit, col, row, r.get("ok"), r.get("mutated"), r.get("stage"),
        r.get("currentPlayer"), r.get("error")))
    return 0


def cmd_endturn(a) -> int:
    r = rpc(a.sid, "applyAction", {"runnerId": a.runner, "action": {"kind": "endturn"}}, 60)
    print("endturn ok=%s stage=%s cp=%s" % (r.get("ok"), r.get("stage"), r.get("currentPlayer")))
    return 0


def cmd_cast(a) -> int:
    act = {"kind": "ability", "casterId": a.caster, "abilityType": a.ability}
    if a.to:
        col, row = [int(x) for x in a.to.split(",")]
        act["to"] = {"col": col, "row": row}
    if a.target is not None:
        act["targetId"] = a.target
    r = rpc(a.sid, "applyAction", {"runnerId": a.runner, "action": act}, 90)
    print("cast ok=%s mutated=%s err=%s" % (r.get("ok"), r.get("mutated"), r.get("error")))
    for ev in (r.get("events") or []):
        print("   ev", {k: v for k, v in ev.items() if k not in ("raw",)})
    return 0


def cmd_attack(a) -> int:
    """Attaque REELLE : compte les coups appliques cote NATIF via les events de degat."""
    before = decision(a.sid, a.runner)
    hp0 = {u["id"]: u.get("hp") for u in (before.get("units") or [])}
    act = {"kind": "ability", "casterId": a.caster, "targetId": a.target,
           "abilityType": a.ability}
    r = rpc(a.sid, "applyAction", {"runnerId": a.runner, "action": act}, 90)
    evs = r.get("events") or []
    dmg = [e for e in evs if str(e.get("type") or e.get("kind") or "").lower().find("damag") >= 0]
    print("attack u%s -> u%s ability=%s ok=%s mutated=%s err=%s" % (
        a.caster, a.target, a.ability, r.get("ok"), r.get("mutated"), r.get("error")))
    print("  events(%d) types=%s" % (len(evs), sorted({str(e.get("type") or e.get("kind"))
                                                       for e in evs})))
    for e in dmg:
        print("   DMG", {k: v for k, v in e.items() if k not in ("raw",)})
    after = decision(a.sid, a.runner)
    for u in (after.get("units") or []):
        if hp0.get(u["id"]) != u.get("hp"):
            print("   HP u%s : %s -> %s (delta %s)" % (u["id"], hp0.get(u["id"]), u.get("hp"),
                                                       (hp0.get(u["id"]) or 0) - (u.get("hp") or 0)))
    return 0


# ---- coeur : coups NATIF (oracle) vs coups MOTEUR ------------------------------------------

def _engine_scene(sid, rid):
    """Scene MOTEUR construite comme predict_samples/predict_sweep (meme chemin de prod)."""
    from engine.playbook import scene as SC
    from engine.playbook.scene import Scene

    def rpc_b(method, body=None, timeout=90):
        return rpc(sid, method, body, timeout)

    predictor = SC.build_predictor(rpc_b, rid)
    dec = decision(sid, rid)
    sctx = SC.step_context(predictor, dec)
    return Scene.from_predictor_sctx(predictor, sctx, None), dec


def _engine_hits(scene, att, tgt, ability_id, ability_name, kind, tile):
    from engine.playbook import prediction
    try:
        if kind == "normal":
            ev = prediction.make_normal_attack_predictions(scene, att, tgt, tile)
            events = [ev] if ev is not None else []
        else:
            events = prediction.make_damage_predictions(scene, att, tgt, ability_id,
                                                        ability_name, attack_pos=tile)
    except Exception as exc:  # noqa: BLE001
        return {"err": "%s: %s" % (type(exc).__name__, exc)}
    main = next((e for e in (events or []) if e.target == tgt), None)
    if main is None:
        return {"err": "no main event"}
    p = main.prediction
    return {"hits": int(p.applied_hits), "min": int(p.accurate_health_damage.min),
            "max": int(p.accurate_health_damage.max)}


def _native_hits(sid, rid, att, tgt, ability_id):
    r = rpc(sid, "aiPlaybookPredict", {"runnerId": rid, "unitId": att, "targetId": tgt,
                                       "abilityType": ability_id}, 60)
    if not r or not r.get("ok"):
        return {"err": (r or {}).get("error", "rpc null")}
    main = next((e for e in (r.get("events") or []) if e.get("targetId") == tgt), None)
    if main is None:
        return {"err": "no main event (count=%s)" % r.get("count")}
    return {"hits": int(main.get("appliedHits") or 0),
            "min": int(main.get("healthDmgMin") or 0), "max": int(main.get("healthDmgMax") or 0)}


def cmd_hits(a) -> int:
    scene, dec = _engine_scene(a.sid, a.runner)
    units = {u["id"]: u for u in (dec.get("units") or [])}
    effs = {u["id"]: [e.get("name") for e in (u.get("effects") or [])]
            for u in (dec.get("units") or [])}
    atts = [int(x) for x in a.attackers.split(",") if x.strip()]
    tgts = [int(x) for x in a.targets.split(",") if x.strip()]
    abils = [int(x) for x in a.abilities.split(",")] if a.abilities else None
    print("%-6s %-6s %-7s %-26s | %-14s | %-14s | %s" % (
        "att", "tgt", "abil", "tgt_effects", "NATIF hits/min/max", "MOTEUR", "verdict"))
    rc = 0
    for att in atts:
        au = units.get(att)
        if au is None:
            print("att u%s ABSENT" % att)
            continue
        tile = ((au.get("pos") or {}).get("col"), (au.get("pos") or {}).get("row"))
        by_id = {int(x.get("id")): x for x in (au.get("abilities") or [])}
        normal_id = next((int(x.get("id")) for x in (au.get("abilities") or [])
                          if x.get("kind") == "normal"), -1)
        ab_list = abils if abils is not None else sorted(by_id)
        for tgt in tgts:
            tnames = effs.get(tgt) or []
            for ab in ab_list:
                nat = _native_hits(a.sid, a.runner, att, tgt, ab)
                abn = (by_id.get(int(ab)) or {}).get("name")
                kind = "normal" if int(ab) == normal_id else "active"
                eng = _engine_hits(scene, att, tgt, ab, abn, kind, tile)
                if "err" in nat or "err" in eng:
                    verdict = "SKIP(%s|%s)" % (nat.get("err", "-"), eng.get("err", "-"))
                elif nat["hits"] == eng["hits"]:
                    verdict = "HITS-OK"
                else:
                    verdict = "HITS-MISMATCH"
                    rc = 1
                print("u%-5s u%-5s %-7s %-26s | %-14s | %-14s | %s" % (
                    att, tgt, ab, ",".join(tnames)[:26],
                    "%s/%s/%s" % (nat.get("hits"), nat.get("min"), nat.get("max")),
                    "%s/%s/%s" % (eng.get("hits"), eng.get("min"), eng.get("max")), verdict))
    return rc


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["map", "move", "endturn", "cast", "hits", "attack"])
    ap.add_argument("--sid", type=int, required=True)
    ap.add_argument("--runner", type=int, required=True)
    ap.add_argument("--unit", type=int)
    ap.add_argument("--caster", type=int)
    ap.add_argument("--target", type=int)
    ap.add_argument("--ability", type=int)
    ap.add_argument("--to", type=str)
    ap.add_argument("--attackers", type=str, default="")
    ap.add_argument("--targets", type=str, default="")
    ap.add_argument("--abilities", type=str, default="")
    a = ap.parse_args()
    return {"map": cmd_map, "move": cmd_move, "endturn": cmd_endturn, "cast": cmd_cast,
            "hits": cmd_hits, "attack": cmd_attack}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
