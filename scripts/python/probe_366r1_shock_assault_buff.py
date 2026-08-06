"""case-366-r1 -- MONTAGE LIVE de `ShockAssault_Buff` (0x3e8 = 1000), le buff « +Damage for this
attack » que le PASSIF `ShockAssault` d'`ultraInceptorSgt` pose sur ses Inceptors.

## Le probleme de mesure, et comment ce montage le resout

En regime NATUREL le buff est POSE ET RETIRE dans la MEME resolution -- mesure du 2026-08-01, events
d'un `applyAction ability(69)` du Bellator (le seul ordre lisible du natif) :

    group 21 entity <bellator> source Loki_NormalAttack     # l'attaque du Bellator se cloture
    group 21 entity <bellator> source ShockAssault          # -> On(0xa) & OwnerIsCaster : le passif tire
    group 22 entity <e99>      source ShockAssault_Buff     # POSE de 1000 sur l'Inceptor
    group 12/21 entity <inceptor> source Loki_NormalAttack  # PerformAIAbility : l'Inceptor frappe
    group 22 entity <e99>      source ShockAssault_Buff     # RETRAIT (meme entite-effet)

=> 1000 n'apparait JAMAIS dans un `decisionView`, meme `includeInactive`, et lire l'ATTACK de
l'Inceptor avant/apres ne montre RIEN (997 -> 997). Une mesure prise la ne tranche pas entre « le
port est bon », « l'effet est inerte » et « l'effet n'existe pas » -- le piege
`feedback_absence_of_event_proves_nothing`.

LE LEVIER est dans le `customUtility` de `PerformAIAbility`
(`...ShockAssaultAbility$$u003CCreateBehaviouru003Eb__1_1`) : il rend **null** -- donc aucune action
-- des que `UnitExtensions.IsAlive(<la cible>)` est faux. **Si le Bellator TUE sa cible, l'Inceptor
ne joue pas et GARDE son buff.** On le fabrique avec `--unit-stat <bellator>:Damage=<enorme>` : le
Bellator one-shot sa cible, les Inceptors gardent leurs stats de kit (`WithStatsFromConfig`,
independant du `Damage` du poseur). Un SECOND ennemi garde la bataille ouverte.

## Ce qui est mesure, et par quels canaux INDEPENDANTS

1. **PRESENCE** -- 1000 est dans `decisionView.effects` de l'Inceptor apres le kill.
2. **MAGNITUDE** -- `statModSources(inceptor, attack)` donne le montant que le NATIF a attribue a
   l'entite-effet ; on le confronte a `ability_var("ShockAssault", "extraDmg", <passif du POSEUR>,
   <mult du POSEUR>)` re-derive du gameconfig. Deux sources independantes, aucun scalaire fitte.
3. **STAT** -- l'axe est ATTACK (0) et rien d'autre.
4. **NIVEAU** -- second couple discriminant : le bras `--unit-stat <bellator>:PassiveAbilityLevel=20`
   DISSOCIE le passif de l'actif (que `buildNormalizedBC` met tous deux a 50). Il refute a la fois
   « la magnitude lit l'ACTIF » et « la magnitude est un scalaire ».
5. **ATTRIBUTION offline** -- le `State` charge depuis la capture doit poser la contribution sous une
   cle d'effet retirable, residu opaque 0. Bras de contre-epreuve : le MEME etat rejoue avec
   l'inscription RETIREE du registre.
6. **RETRAIT** -- des DEUX cotes : live, l'Inceptor rejoue au turn-start suivant
   (`PlayAutomaticUnits`) et 1000 doit disparaitre ; offline, `attack_damage_attack_triggers` sur le
   porteur doit le retirer ET sortir sa `ValueModification`.

ASCII only (cp1252). Usage :
    python probe_366r1_shock_assault_buff.py [--seed 4471] [--board MC1_67] [--keep]
    python probe_366r1_shock_assault_buff.py --passive-level 20      # le bras discriminant
Consommateur pytest : `tests/engine/runner/test_shock_assault_buff_live.py`.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

_PYDIR = Path(__file__).resolve().parent
_ROOT = _PYDIR.parent.parent
sys.path.insert(0, str(_PYDIR))

import hexgeo                                                    # noqa: E402
from rl_collect_batch import _rpc, _resolve_session              # noqa: E402

BELLATOR = "ultraInceptorSgt"      # HERO au pool -- porteur du PASSIF ShockAssault (1002)
INCEPTOR = "ultraSmnInceptor"      # le SUMMON buffe (`GetStringConstant(config, 0 = unitId)`)
FOE = "tyranTyrantGuard"           # la cible que le Bellator doit TUER
FOE2 = "orksNob"                   # garde la bataille ouverte apres le kill
BOARD = "MC1_67"
SEED = "4471"
SHOCK_ASSAULT_BUFF = 1000          # 0x3e8
DEATH_FROM_ABOVE = 1003            # l'ACTIVE qui fait apparaitre les Inceptors
NORMAL_ATTACK = 69                 # l'attaque normale concrete d'`ultraInceptorSgt`
BELLATOR_DAMAGE = 500000           # one-shot : c'est ce qui fait SURVIVRE le buff (cible morte)
FOE_HP = 30000                     # les ennemis encaissent les Inceptors sans mourir


def build_args(passive_level: int | None) -> list[str]:
    specs = ["%s:Damage=%d" % (BELLATOR, BELLATOR_DAMAGE)]
    if passive_level is not None:
        specs.append("%s:PassiveAbilityLevel=%d" % (BELLATOR, passive_level))
    argv = ["--p-units", BELLATOR, "--a-units", "%s,%s" % (FOE, FOE2),
            "--board", BOARD, "--hp-target", str(FOE_HP), "--no-ai"]
    for s in specs:
        argv += ["--unit-stat", s]
    return argv


def _unwrap(r):
    return r["result"] if isinstance(r, dict) and "result" in r else r


def _build_subprocess(seed: str, board: str, passive_level: int | None) -> int:
    state = _ROOT / "logs" / ("_probe366r1-%d.json" % os.getpid())
    state.parent.mkdir(parents=True, exist_ok=True)
    state.unlink(missing_ok=True)
    extra = build_args(passive_level)
    extra[extra.index("--board") + 1] = board
    argv = [sys.executable, "rl_duel.py", "build", "--seed", seed,
            "--state-file", str(state), *extra]
    p = subprocess.run(argv, cwd=str(_PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state.exists():
        raise RuntimeError("build runner KO (rl_duel): " + ((p.stderr or p.stdout or "")[-600:]))
    return int(json.loads(state.read_text())["runnerId"])


def _pos(u):
    q = (u or {}).get("pos") or {}
    return (q.get("col"), q.get("row"))


def _find(d, vis):
    return next((u for u in (d.get("units") or []) if u.get("visualId") == vis
                 and u.get("alive") is not False), None)


def _effect(dec, uid, effect_type):
    for u in (dec.get("units") or []):
        if u.get("id") == uid:
            for e in (u.get("effects") or []):
                if e.get("effectType") == effect_type:
                    return True, e
    return False, None


def run(rpc, seed: str = SEED, board: str = BOARD, build_runner=None,
        passive_level: int | None = None, keep: bool = False) -> dict:
    """Monte le montage, mesure LIVE + MOTEUR, rend le dict. Libere le runner sauf `keep`."""
    r = _run(rpc, seed, board, build_runner, passive_level)
    if not keep and r.get("rid") is not None:
        try:
            rpc("disposeRunner", {"runnerId": r["rid"]}, 40)
        except Exception:                                # pragma: no cover (nettoyage best-effort)
            pass
    return r


def _run(rpc, seed: str, board: str, build_runner, passive_level: int | None) -> dict:
    from engine.entities.effects.magnitude import ability_var
    from engine.entities.pathfinding.board import Board
    from engine.entities.stats import StatType, CAPTURED_SOURCE
    from engine.runner.components import StatsComponent
    from engine.runner.operations.triggers.dispatch.attack import attack_damage_attack_triggers
    from engine.runner.snapshot import load_state

    if build_runner is not None:
        extra = build_args(passive_level)
        extra[extra.index("--board") + 1] = board
        rid = build_runner(seed, extra=extra)["rid"]
    else:
        rid = _build_subprocess(seed, board, passive_level)
    out = {"rid": rid, "seed": seed, "board": board, "passive_level": passive_level,
           "ok": False, "why": None}

    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        out["why"] = "boardGraph indispo"
        return out
    brd = Board(bg["tiles"], adjacency="evenq")

    def dec(inactive=True):
        body = {"runnerId": rid, "maxRank": 1, "allAbilities": True}
        if inactive:
            body["includeInactive"] = True
        return rpc("decisionView", body, 120)

    def act(action, t=180):
        return rpc("applyAction", {"runnerId": rid, "action": action}, t)

    def endturn():
        return act({"kind": "endturn"}, 60)

    def _castable(unit_id, ability_id):
        """Cibles castables DEPUIS LA POSITION COURANTE (`fromHere`) -- jamais `targets`, qui est le
        superset APRES deplacement. `DeathFromAbove` porte `TargetHasFreeAdjacentTile` : sur un board
        encombre, une partie des ennemis adjacents N'EST PAS ciblable, et le cast repond alors
        `ok: true, mutated: false` (mesure du 2026-08-01) -- un refus SILENCIEUX."""
        at = rpc("abilityTargets", {"runnerId": rid}, 120)
        for u in (at.get("units") or []):
            if u.get("unitId") != unit_id:
                continue
            for a in (u.get("abilities") or []):
                if a.get("abilityId") == ability_id:
                    return [t.get("targetId") for t in (a.get("fromHere") or [])
                            if t.get("targetId") is not None]
        return []

    # --- 1. amener le Bellator au contact d'un ennemi (mouvements legaux) ------------------------
    d = dec()
    for _ in range(24):
        b = _find(d, BELLATOR)
        foes = [u for u in (d.get("units") or [])
                if u.get("team") != (b or {}).get("team") and u.get("alive") is not False]
        if b is None or not foes:
            out["why"] = "Bellator ou ennemis absents du live"
            return out
        near = min(foes, key=lambda u: hexgeo.distance(_pos(b), _pos(u)))
        if hexgeo.distance(_pos(b), _pos(near)) <= 1:
            break
        mov = rpc("aiMovableTiles", {"runnerId": rid, "side": "all"}, 60)
        mu = next((m for m in (mov.get("units") or []) if m.get("unitId") == b["id"]), None)
        tiles = [(t["col"], t["row"]) for t in (mu or {}).get("tiles") or []
                 if t.get("col") is not None]
        best = min(tiles, key=lambda t: (hexgeo.distance(t, _pos(near)), t)) if tiles else None
        if best is None or hexgeo.distance(best, _pos(near)) >= hexgeo.distance(_pos(b), _pos(near)):
            endturn()
        else:
            act({"kind": "move", "unitId": b["id"], "to": {"col": best[0], "row": best[1]}}, 60)
        d = dec()
    b = _find(d, BELLATOR)
    out["bellator"] = b["id"]

    # --- 2. DeathFromAbove : faire APPARAITRE un Inceptor adjacent -------------------------------
    if not b.get("hasAction"):
        endturn()
        d = dec()
        b = _find(d, BELLATOR)
    cast_targets = _castable(b["id"], DEATH_FROM_ABOVE)
    if not cast_targets:
        out["why"] = "DeathFromAbove n'a aucune cible `fromHere` (TargetHasFreeAdjacentTile)"
        return out
    victim = cast_targets[0]                      # la cible du DFA -- et celle que le Bellator TUERA
    out["victim"] = victim
    dfa = act({"kind": "ability", "casterId": b["id"], "targetId": victim,
               "abilityType": DEATH_FROM_ABOVE})
    out["dfa"] = [{k: a.get(k) for k in ("kind", "ok", "error", "mutated")}
                  for a in (dfa.get("actions") or [])]
    d = dec()
    inc = _find(d, INCEPTOR)
    if inc is None:
        out["why"] = ("aucun Inceptor apparu (DeathFromAbove n'a pas spawn) -- cast=%s"
                      % (out["dfa"],))
        return out
    out["inceptor"] = inc["id"]

    # --- 3. le Bellator TUE sa cible -> `IsAlive(target)` faux -> l'Inceptor NE JOUE PAS ---------
    for _ in range(4):
        d = dec()
        b = _find(d, BELLATOR)
        if b is not None and b.get("hasAction"):
            break
        endturn()
    d = dec()
    b, inc = _find(d, BELLATOR), _find(d, INCEPTOR)
    f = next((u for u in (d.get("units") or []) if u.get("id") == victim
              and u.get("alive") is not False), None)
    if b is None or f is None or inc is None:
        out["why"] = "scene incomplete avant le kill (b=%s victime=%s inc=%s)" % (b, f, inc)
        return out
    out["foe_hp_before"] = f.get("hp")
    out["dist_bellator_inceptor"] = hexgeo.distance(_pos(b), _pos(inc))
    res = act({"kind": "ability", "casterId": b["id"], "targetId": victim,
               "abilityType": NORMAL_ATTACK})
    out["kill_events"] = [(e.get("group"), e.get("entity"), e.get("source"))
                          for e in ((res.get("actions") or [{}])[0].get("events") or [])
                          if e.get("source")]

    # --- 4. CAPTURE : l'effet doit etre LA, sur l'Inceptor ---------------------------------------
    cap_dec = dec()
    present, e = _effect(cap_dec, out["inceptor"], SHOCK_ASSAULT_BUFF)
    out["live_present"] = bool(present)
    out["live_effect"] = e
    if not present:
        out["why"] = ("1000 absent apres le kill -- l'Inceptor a-t-il joue ? "
                      "(events=%s)" % (out["kill_events"],))
        return out
    cap_ob = rpc("observeBattle", {"runnerId": rid}, 40)
    cap_snap = rpc("combatSnapshot", {"runnerId": rid}, 60)

    # MAGNITUDE NATIVE : `statModSources` lit la `ValueModification` par SOURCE (l'entite-EFFET).
    sm = rpc("statModSources", {"runnerId": rid, "unitId": int(out["inceptor"]),
                                "stats": ["attack"]}, 120)
    mods = {}
    for u in (sm.get("units") or []):
        if int(u.get("entityId") or -1) == int(out["inceptor"]):
            mods = (u.get("mods") or {}).get("attack") or {}
    out["live_statmod"] = mods
    out["live_statmod_effect"] = sum(int(s.get("amount") or 0) for s in (mods.get("bySource") or [])
                                     if not s.get("sourceIsUnit"))
    out["live_attack"] = next((int((u.get("stats") or {}).get("attack") or 0)
                               for u in (cap_snap.get("units") or [])
                               if int(u.get("entityId") or -1) == int(out["inceptor"])), None)
    cfg = next(((u.get("unitConfig") or {}) for u in (cap_snap.get("units") or [])
                if int(u.get("entityId") or -1) == int(out["bellator"])), {})
    out["poser_config"] = cfg
    out["expected"] = ability_var("ShockAssault", "extraDmg",
                                  cfg.get("passiveAbilityLevel"),
                                  multiplier_pct=int(cfg.get("abilityVariablesMultiplier") or 100))

    # --- 5. OFFLINE : la MEME capture, inscription PRESENTE puis RETIREE -------------------------
    from engine.entities.effects.factory import EFFECT_CLASSES

    def _offline(declare: bool) -> dict:
        saved = EFFECT_CLASSES.pop("ShockAssault_Buff", None)
        if declare and saved is not None:
            EFFECT_CLASSES["ShockAssault_Buff"] = saved
        try:
            s = load_state(cap_dec, cap_ob, cap_snap, board=brd)
            ent = s.get_entity(out["inceptor"])
            comp = ent.get_component(StatsComponent) if ent is not None else None
            if comp is None or comp.ctx is None:
                return {"why": "StatsComponent absent du State charge"}
            cx = comp.ctx
            ps = dict(cx.stats.components[int(StatType.ATTACK)].modification.per_source)
            keys = [k for k in ps if isinstance(k, tuple)
                    and k[:2] == ("statmod", SHOCK_ASSAULT_BUFF)]
            r = {"attack_on": int(cx.stat(StatType.ATTACK)),
                 "statmod_keys": [str(k) for k in keys],
                 "attributed": sum(ps[k] for k in keys),
                 "opaque_residual": int(ps.get(CAPTURED_SOURCE, 0))}
            # RETRAIT offline : `On(0xa)` avec le PORTEUR en attaquant.
            other = next((u.get("id") for u in (cap_dec.get("units") or [])
                          if u.get("id") not in (out["inceptor"], out["bellator"])
                          and u.get("alive") is not False), out["bellator"])
            attack_damage_attack_triggers(s, out["inceptor"], other,
                                          ranged=False, profile="Bolter")
            r["still_here"] = any(x.effect_type == SHOCK_ASSAULT_BUFF and not x.consumed
                                  for x in s.effects.by_unit.get(out["inceptor"], []))
            r["attack_off"] = int(cx.stat(StatType.ATTACK))
            return r
        finally:
            if saved is not None:
                EFFECT_CLASSES["ShockAssault_Buff"] = saved

    declared = _offline(True)
    if declared.get("why"):
        out["why"] = declared["why"]
        return out
    out["declared"] = declared
    out["undeclared"] = _offline(False)

    # --- 6. RETRAIT LIVE : l'Inceptor rejoue au turn-start suivant (`PlayAutomaticUnits`) --------
    for _ in range(4):
        endturn()
        d2 = dec()
        if not _effect(d2, out["inceptor"], SHOCK_ASSAULT_BUFF)[0]:
            break
    d2 = dec()
    out["live_still_here"] = _effect(d2, out["inceptor"], SHOCK_ASSAULT_BUFF)[0]
    out["live_attack_after"] = next(
        (int((u.get("stats") or {}).get("attack") or 0)
         for u in ((rpc("combatSnapshot", {"runnerId": rid}, 60)).get("units") or [])
         if int(u.get("entityId") or -1) == int(out["inceptor"])), None)
    out["ok"] = True
    return out


def main():
    ap = argparse.ArgumentParser(description="montage live de ShockAssault_Buff (1000)")
    ap.add_argument("--seed", default=SEED)
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--passive-level", type=int, default=None)
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()
    sid = _resolve_session()

    def rpc(method, body=None, timeout=90):
        return _unwrap(_rpc(sid, method, [body] if body is not None else [], timeout=timeout))

    r = run(rpc, a.seed, a.board, passive_level=a.passive_level, keep=a.keep)
    print("[366r1] runner=%s ok=%s why=%s" % (r.get("rid"), r.get("ok"), r.get("why")))
    if r.get("kill_events"):
        print("[366r1] events du kill : %s" % (r["kill_events"],))
    print("[366r1] 1000 present live apres le kill : %s (capte = %s)"
          % (r.get("live_present"), json.dumps(r.get("live_effect") or {})))
    print("[366r1] bellator=u%s inceptor=u%s victime=u%s dist(b,inc)=%s"
          % (r.get("bellator"), r.get("inceptor"), r.get("victim"),
             r.get("dist_bellator_inceptor")))
    print("[366r1] poser config = %s" % (json.dumps(r.get("poser_config") or {}),))
    print("[366r1] MAGNITUDE  natif(statModSources bySource non-unite) = %s | attendu gameconfig = %s"
          % (r.get("live_statmod_effect"), r.get("expected")))
    print("[366r1] statModSources brut = %s" % (json.dumps(r.get("live_statmod") or {}),))
    print("[366r1] ATTACK live avec le buff = %s ; apres retrait live = %s (still_here=%s)"
          % (r.get("live_attack"), r.get("live_attack_after"), r.get("live_still_here")))
    for tag in ("declared", "undeclared"):
        b = r.get(tag) or {}
        print("[366r1] OFFLINE %-10s attack_on=%s attribue=%s residu_opaque=%s "
              "-> apres On(0xa) still=%s attack=%s"
              % (tag, b.get("attack_on"), b.get("attributed"), b.get("opaque_residual"),
                 b.get("still_here"), b.get("attack_off")))
    return 0 if r.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
