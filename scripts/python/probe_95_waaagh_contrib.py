"""Probe #95 -- selecteur de buff Waaagh + contributions 1100 (+extraDmg) / 1101 (+extraHit).

Canaux natifs mesures :
  `IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$GetBuffBehaviour`
      selecteur = Unique( caster@0x160 + AdjacentFriends(caster,1,3)
                          + UnitsFromFaction(Friends(caster, allUnits@0x80, 3), 5=Orks, 3) )
  `IdunBattle.Entities.Effects.Loki.Waaagh_ExtraDamageEffect$$CreateEffectDamageBonusForAttack`
      = ForAddition(IsNormalAttack & IsMeleeAttack & OwnerIsCaster, ConfigVar(8=extraDmg, AbilityState))
  `IdunBattle.Entities.Effects.Loki.Waaagh_ExtraHitsEffect$$CreateEffectHitsBonusForAttack`
      = ForAddition(MEME condition, ConfigConst(0x2b=extraHit))

ROSTER (4 unites de MON camp, chacune un role) :
  * CASTER  `orksWarboss` : caste Waaagh depuis son spawn (on lui AMENE sa cible).
  * ALLY    `orksNob`     : ORK amene AU CONTACT d'un ennemi LOIN du Warboss -> unite de MESURE
    (preview NATIVE `aiPredict` avant/apres) ET discriminant « Ork non adjacent, tres loin ».
  * MID     `orksRuntherd`: ORK pousse a distance INTERMEDIAIRE (>=3) du Warboss -> discriminant
    « Ork non adjacent, proche » (separe « selecteur board-wide » de « anneau adjacent seul »).
  * SPARE   (non-Ork)     : JAMAIS activee. Elle garde le tour OUVERT apres le cast : sinon le cast
    epuise le camp -> bascule de tour -> TICK -> les 3 buffs (`Direct(1)` = 1 TOUR) ont DEJA expire
    quand on les lit (mesure 1 du probe : « eff [] » sur TOUTES les unites, caster compris).

Sans les DEUX theatres separes, la charge du Warboss + les Ork Boyz du `PerformAIAction` arrivent au
contact de la cible du Nob : elle MEURT (preview nulle) et `GetStuckIn.GetBonusHitChance` bascule a
100 % (2 Orks adjacents a la cible) -> le +1 coup serait noye. Le probe imprime les INVARIANTS.

ASCII only. Ne reinjecte JAMAIS (amorce-si-besoin seulement).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import hexgeo
import rl_collect_batch as R

PYDIR = Path(__file__).resolve().parent
# SORTIE de run -> `logs/` RELATIF au checkout (#314) : un chemin absolu ferait
# ecrire ce probe dans l'arbre principal depuis un worktree d'agent.
STATE = PYDIR.parents[1] / "logs" / "runners" / "_probe95_waaagh_state.json"

CASTER = "orksWarboss"       # porteur de Waaagh (1058)
ALLY = "orksNob"             # ORK de MESURE (melee), amene au contact, TRES loin du Warboss
MID = "orksRuntherd"         # ORK discriminant a distance intermediaire du Warboss
SPARE = "spaceHound"         # non-Ork jamais activee : garde le tour ouvert
# Cible du Nob (theatre A, loin) : SANS trait `Overwatch` (sinon elle TUE le Nob a l'approche ->
# `decisionView` GARDE les cadavres, la mesure porterait sur un CORPS : jamais buffe -- `AllAliveUnits`
# -- et preview figee ; d'ou le controle `dead` ci-dessous) et SANS effet de reduction de degat
# (`tyranTyrantGuard` porte `GuardianOrganism_DamageReduction` = soustraction CAPEE recalculee sur le
# degat courant -> elle POLLUE le delta par-coup). `necroWarden` : aucun effet, aucun Overwatch.
FOE_ALLY = "necroWarden"
FOE_CASTER = "tyranTyrantGuard"   # cible du Waaagh (theatre B, ramenee sur le Warboss ; tanky)


def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def _upos(u):
    q = (u or {}).get("pos") or {}
    return (q.get("col"), q.get("row"))


def main(seed="31337", board="MC1_67", mid_dist="3", rank=None):
    mid_dist = int(mid_dist)
    sid = R._resolve_session()
    print("[probe95] session", sid)
    w = _unwrap(R._rpc(sid, "autoBootExtraire", [{}], timeout=180))
    print("[probe95] amorce ok=", (w or {}).get("ok"))
    STATE.unlink(missing_ok=True)
    p = subprocess.run([sys.executable, "rl_duel.py", "build", "--seed", str(seed),
                        "--state-file", str(STATE), "--board", board,
                        "--p-units", f"{CASTER},{ALLY},{MID},{SPARE}",
                        "--a-units", f"{FOE_CASTER},{FOE_ALLY}"]
                       + (["--rank", str(rank)] if rank else []),
                       cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    if not STATE.exists():
        print("[probe95] build KO:", (p.stderr or p.stdout or "")[-500:])
        return
    rid = json.loads(STATE.read_text())["runnerId"]
    print("[probe95] runner", rid)

    def rpc(m, b, t=90):
        return _unwrap(R._rpc(sid, m, [b], timeout=t))

    def dv():
        return rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True})

    def find(d, vis):
        return next((u for u in (d.get("units") or []) if u.get("visualId") == vis), None)

    def endturn():
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)

    def movable(uid):
        mov = rpc("aiMovableTiles", {"runnerId": rid, "side": "all"}, 60)
        mu = next((m for m in (mov.get("units") or []) if m.get("unitId") == uid), None)
        return [(t["col"], t["row"]) for t in (mu or {}).get("tiles") or []
                if t.get("col") is not None]

    def drive(vis, goal_fn, want_dist, stop_fn=None, iters=14, label=""):
        """Rapproche `vis` de `goal_fn(d)` jusqu'a `want_dist` ; s'arrete si `stop_fn(d)` est vrai."""
        for _ in range(iters):
            d = dv()
            u = find(d, vis)
            if u is None:
                print(f"[probe95] {label}: {vis} absent"); return None
            if stop_fn is not None and stop_fn(d):
                return d
            goal = goal_fn(d)
            dist = hexgeo.distance(_upos(u), goal)
            if dist <= want_dist:
                return d
            tiles = [t for t in movable(u["id"]) if hexgeo.distance(t, goal) >= want_dist]
            best = min(tiles, key=lambda t: (hexgeo.distance(t, goal), t)) if tiles else None
            if best is None or hexgeo.distance(best, goal) >= dist:
                endturn()
                continue
            rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": u["id"], "to": {"col": best[0], "row": best[1]}}}, 60)
            print(f"[probe95] {label}: {vis} {_upos(u)} -> {best} "
                  f"(dist {dist} -> {hexgeo.distance(best, goal)})")
        return dv()

    def legal_targets(uid, ability):
        at = rpc("abilityTargets", {"runnerId": rid}, 90)
        out = []
        for u in (at.get("units") or []):
            if u.get("unitId") != uid:
                continue
            for a in (u.get("abilities") or []):
                if a.get("abilityId") == int(ability):
                    out += [t["targetId"] for t in (a.get("targets") or [])
                            if t.get("targetId") is not None]
        return out

    def adjacents(d, tid):
        t = next((u for u in (d.get("units") or []) if u["id"] == tid), None)
        if t is None:
            return None
        tp = _upos(t)
        return sorted((u["id"], u.get("visualId")) for u in (d.get("units") or [])
                      if u["id"] != tid and _upos(u)[0] is not None
                      and hexgeo.distance(_upos(u), tp) == 1)

    try:
        d = dv()
        wb_spawn = _upos(find(d, CASTER))
        print("[probe95] spawns:", {v: _upos(find(d, v)) for v in
                                    (CASTER, ALLY, MID, SPARE, FOE_CASTER, FOE_ALLY)})

        # theatre B : la cible du Waaagh vient AU Warboss (qui ne bouge pas de son spawn)
        drive(FOE_CASTER, lambda _d: wb_spawn, 2, iters=14, label="B")
        # theatre A : le Nob au contact de sa cible (restee a son spawn)
        drive(ALLY, lambda dd: _upos(find(dd, FOE_ALLY)), 1, iters=16, label="A")
        # discriminant MID : Ork pousse a >= mid_dist du Warboss (mais pas au bout du plateau)
        drive(MID, lambda dd: _upos(find(dd, FOE_ALLY)), 1,
              stop_fn=lambda dd: hexgeo.distance(_upos(find(dd, MID)), wb_spawn) >= mid_dist,
              iters=8, label="MID")

        d = dv()
        a, f = find(d, ALLY), find(d, FOE_ALLY)
        c, m = find(d, CASTER), find(d, MID)
        print("[probe95] geometrie: " + " | ".join(
            f"{v}{_upos(find(d, v))}" for v in (CASTER, ALLY, MID, SPARE, FOE_CASTER, FOE_ALLY)))
        print(f"[probe95] d(nob,foeA)={hexgeo.distance(_upos(a), _upos(f))} "
              f"d(warboss,nob)={hexgeo.distance(_upos(c), _upos(a))} "
              f"d(warboss,mid)={hexgeo.distance(_upos(c), _upos(m))} "
              f"d(warboss,foeA)={hexgeo.distance(_upos(c), _upos(f))}")
        if hexgeo.distance(_upos(a), _upos(f)) != 1:
            print("[probe95] ECHEC : Nob pas au contact -> mesure melee impossible"); return

        wb_target = None
        for _ in range(6):
            d = dv()
            c = find(d, CASTER)
            if d.get("currentPlayer") != c.get("owner"):
                endturn(); continue
            tg = legal_targets(c["id"], 1058)
            print("[probe95] targets1058 =", tg)
            if tg:
                e = find(d, FOE_CASTER)
                wb_target = e["id"] if (e and e["id"] in tg) else tg[0]
                break
            endturn()
        if wb_target is None:
            print("[probe95] ECHEC : Waaagh jamais castable"); return

        # ---------------- BASELINE ----------------
        d0 = dv()
        a0, f0 = find(d0, ALLY), find(d0, FOE_ALLY)
        obs0 = {u.get("squadId"): u for u in (rpc("observeBattle", {"runnerId": rid}, 40)
                                             .get("units") or [])}
        for lbl, u in (("nob", a0), ("foeA", f0)):
            if (obs0.get(u["id"]) or {}).get("isDead"):
                print(f"[probe95] ECHEC : {lbl} est un CADAVRE (decisionView garde les morts) -> "
                      f"mesure invalide")
                return
        pre = rpc("aiPredict", {"runnerId": rid, "unitId": a0["id"], "targetId": f0["id"]}, 90)
        adj0 = adjacents(d0, f0["id"])
        print("[probe95] PRE  currentPlayer", d0.get("currentPlayer"), "toActivate", d0.get("toActivate"))
        print("[probe95] PRE  nob", _upos(a0), "eff", [x.get("name") for x in (a0.get("effects") or [])])
        print("[probe95] PRE  foe", _upos(f0), "hp", f0.get("hp"), "adj", adj0)
        print("[probe95] PRE  aiPredict", json.dumps(pre.get("pred")), "tile", pre.get("tile"))

        # ---------------- CAST ----------------
        c = find(d0, CASTER)
        wb_pos_before = _upos(c)
        act = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": c["id"], "targetId": wb_target,
            "abilityType": 1058}}, 150)
        a0act = ((act or {}).get("actions") or [{}])[0]
        print("[probe95] cast mutated =", a0act.get("mutated"), "err", a0act.get("error"))
        if not a0act.get("mutated"):
            print("[probe95] ECHEC : cast non mute"); return

        # ---------------- POST ----------------
        d1 = dv()
        a1 = next((u for u in (d1.get("units") or []) if u["id"] == a0["id"]), None)
        f1 = next((u for u in (d1.get("units") or []) if u["id"] == f0["id"]), None)
        print("[probe95] POST currentPlayer", d1.get("currentPlayer"), "toActivate", d1.get("toActivate"))
        print(f"[probe95] POST warboss {wb_pos_before} -> {_upos(find(d1, CASTER))}")
        obs = rpc("observeBattle", {"runnerId": rid}, 40)
        obs_by_id = {u.get("squadId"): u for u in (obs.get("units") or [])}
        print("[probe95] POST effets / distance au Warboss AVANT cast :")
        for u in (d1.get("units") or []):
            dd = (hexgeo.distance(_upos(u), wb_pos_before) if _upos(u)[0] is not None else None)
            o = obs_by_id.get(u["id"]) or {}
            print("    id=%-4s %-16s pos=%-8s dWB=%-4s own=%s team=%s pid=%s dead=%s %s" % (
                u["id"], u.get("visualId"), _upos(u), dd, u.get("owner"),
                o.get("teamId"), o.get("playerId"), o.get("isDead"),
                [(x.get("name"), x.get("remaining")) for x in (u.get("effects") or [])]))
        if a1 is None or f1 is None:
            print("[probe95] ECHEC : nob/cible disparus (bataille finie ?)"); return
        post = rpc("aiPredict", {"runnerId": rid, "unitId": a0["id"], "targetId": f0["id"]}, 90)
        adj1 = adjacents(d1, f0["id"])
        print("[probe95] POST aiPredict", json.dumps(post.get("pred")), "tile", post.get("tile"))

        ok = True
        for label, x, y in (("nob_pos", _upos(a0), _upos(a1)),
                            ("foe_pos", _upos(f0), _upos(f1)),
                            ("foe_hp", f0.get("hp"), f1.get("hp")),
                            ("foe_adj", adj0, adj1),
                            ("pred_tile", pre.get("tile"), post.get("tile"))):
            if x != y:
                ok = False
                print(f"[probe95] INVARIANT ROMPU {label}: {x} -> {y}")
        print("[probe95] invariants", "OK" if ok else "KO (mesure a interpreter avec prudence)")
        p0, p1 = pre.get("pred") or {}, post.get("pred") or {}
        h0, h1 = p0.get("appliedHits"), p1.get("appliedHits")
        print(f"[probe95] hits {h0} -> {h1}")
        for k in ("healthDmgMin", "healthDmgMax", "totalDmgMin", "totalDmgMax"):
            print(f"[probe95] {k} {p0.get(k)} -> {p1.get(k)}")
        if h0 and h1:
            print("[probe95] par-coup min %.2f -> %.2f | max %.2f -> %.2f" % (
                p0.get("healthDmgMin") / h0, p1.get("healthDmgMin") / h1,
                p0.get("healthDmgMax") / h0, p1.get("healthDmgMax") / h1))
        # AbilityState BAKE sur l'EFFET (`EffectComponent.AbilityState @0x18`) = CE que
        # `IdunBattle.Entities.Effects.BaseEffect$$GetAbilityState` rend aux noeuds `ConfigVar`.
        for et in (1100, 1101, 1099):
            eas = rpc("effectAbilityStates", {"runnerId": rid, "effectType": et}, 60)
            print(f"[probe95] effectAbilityStates({et}):", json.dumps(eas)[:900])
        # `ConfigVar(8=extraDmg, GetAbilityState(effet))` -> AbilityState PER-ABILITY du POSEUR
        # (canal distinct du global unitConfig, cf. rpc-snapshot.ts `abilityStates`).
        snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
        from engine.entities.effects.magnitude import ability_var
        by_eid = {u.get("entityId"): u for u in (snap.get("units") or [])}
        for lbl, uid in (("warboss", find(d1, CASTER)["id"]), ("nob", a0["id"])):
            u = by_eid.get(uid) or {}
            uc = u.get("unitConfig") or {}
            print(f"[probe95] {lbl} unitConfig:", json.dumps(uc))
            for st in (u.get("abilityStates") or []):
                if st.get("name") in ("Waaagh", None) or st.get("id") == 1058:
                    print(f"[probe95] {lbl} abilityState {st.get('id')}/{st.get('name')}"
                          f" kind={st.get('kind')} level={st.get('level')} mult={st.get('multiplier')}"
                          f" -> extraDmg=" +
                          str(ability_var("Waaagh", "extraDmg", st.get("level"),
                                          multiplier_pct=int(st.get("multiplier") or 100))))
            lv = uc.get("activeAbilityLevel")
            mt = int(uc.get("abilityVariablesMultiplier") or 100)
            print(f"[probe95] {lbl} (canal unitConfig L{lv} x{mt}%) -> extraDmg="
                  + str(ability_var("Waaagh", "extraDmg", lv, multiplier_pct=mt)))
        print("[probe95] extraHit (constante) =", ability_var("Waaagh", "extraHit", is_constant=True))
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 30)
        STATE.unlink(missing_ok=True)
        print("[probe95] disposed", rid)


if __name__ == "__main__":
    main(*(sys.argv[1:]))
