#!/usr/bin/env python
"""Probe EnvFire/ABILITY-route — le DoT de tuile en feu subit-il le cap `Resilient` ?

QUESTION BINAIRE (le discriminant de la migration `execute_direct` -> `AbilityDamageOperation`) :
quand le tick de feu d'une cible RESILIENT depasse ses PV COURANTS, le natif la tue-t-il, ou la
laisse-t-il a 1 PV ?

RE (decompile = verite) :
- `IdunBattleLogic.Entities.Abilities.Active.Loki.EnvFireTileAbility$$CreateBehaviour` appelle
  `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAbilityDamage`, qui construit
  `IdunBattle.Entities.Behaviours.AbilityDamageBehaviour$$.ctor` + `IdunBattle.Entities.Behaviours.AttackBehaviour$$.ctor`
  (`AttackBehaviour$$Execute` : +0x50 = caster resolu en UNE entite = `Tiles(<occupant>)` = la TUILE,
  +0x58 = la liste des cibles = l'occupant) -> famille ABILITY = `IdunBattle.Operations.AbilityDamageOperation`
  -> `IdunBattle.Core.Services.DamagePrediction$$CalculateAbilityDamage`, dont l'etage limites
  (`IdunBattle.Core.Services.DamagePrediction$$ApplyTraitDamageLimitsToDamage` mode 2) contient
  `IdunBattle.Core.Services.DamagePrediction$$ApplyResilientTraitDamageLimit` = cap a `hp - 1`.
- Le port route encore ce DoT par `AttackDamageOperation.execute_direct` (percage/armure SEULS,
  AUCUN etage limites hors member-cap) -> il TUE la cible Resilient.

=> PREDICTIONS OPPOSEES, mesurables :
   natif ability-route : tick sur hp dans (dot/2, dot] -> degat = hp-1, l'unite SURVIT a 1 PV ;
   port execute_direct : degat = dot >= hp                -> l'unite MEURT.
   (borne basse dot/2 : au-dela, `IsOverkill` (seuil overkillDmgPctOfHealth=100) BYPASSE le cap.)

SCENARIO (runner isole, ennemi JAMAIS active) :
- P = adeptRetributor «Vindicta» : arme ranged `hits=4 DamageProfile=Flame Range=2` -> son attaque
  normale POSE le feu sur la tuile de la cible (`OnFireDamageAbility`, profil a trait OnFire).
- A = astraYarrick : traits = {Hero, Resilient} SEULEMENT (aucun trait defensif, aucun heal), et
  `--hp-target` force Health=RemainingHealth=N + Armor=FixedArmor=0 -> dot = 20% de N, EXACT.
- Boucle : attaquer a distance 2 (jamais au contact : l'arme melee est Physical, pas Flame) pour
  poser/re-poser le feu, laisser les ticks descendre les PV, et CESSER d'attaquer des que hp entre
  dans la fenetre discriminante. Le tour ennemi est SAUTE (endturn a sa place) : les seules
  mutations de PV entre deux de mes tours sont les ticks de debut de tour.
ASCII only (cp1252). Usage: python probe_envfire_resilient_cap.py [--seed 90101] [--max-rounds 24]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hexgeo  # noqa: E402
import gameconfig as GC  # noqa: E402
from rl_collect_batch import _resolve_session, _rpc  # noqa: E402
from engine.dsl.base import _round_fix64  # noqa: E402
from engine.services.damage_prediction import apply_pierce_and_modifiers  # noqa: E402
from engine.runner.abilities.base import profile_pierce  # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
STATE = ROOT / "logs" / "runners" / "_envfire_resilient_state.json"
P_UNITS = "adeptRetributor"
A_UNITS = "astraYarrick"          # traits = Hero + Resilient SEULEMENT
BOARD = "MC1_67"
W, H = 7, 9
MV_VIN = 3
HP_TARGET = 500000                # dot = 20% = 100000 ; fenetre discriminante = (50000, 100000]
FIRE_EFFECT_TYPE = 5              # Effect_Type Fire (project_effect_type_attribution)


def _r(sid: int, method: str, body: dict, t: float = 90) -> dict:
    return (_rpc(sid, method, [body], timeout=t).get("result") or {})


def build(seed: int, hp_target: int, a_units: str) -> int:
    STATE.unlink(missing_ok=True)
    STATE.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
         "--state-file", str(STATE), "--board", BOARD,
         "--p-units", P_UNITS, "--a-units", a_units,
         "--hp-target", str(hp_target)],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not STATE.exists():
        print(f"[envfire] build KO: {(proc.stderr or proc.stdout or '')[-600:]}", file=sys.stderr)
        sys.exit(2)
    for ln in (proc.stdout or "").splitlines():
        if "[build]" in ln:
            print("  " + ln)
    return json.loads(STATE.read_text())["runnerId"]


def _alive(dv: dict) -> list:
    return [u for u in (dv.get("units") or []) if u.get("alive")]


def _by_vis(dv: dict, vis: str) -> list:
    return [u for u in _alive(dv) if u.get("visualId") == vis]


def _pos(u: dict) -> tuple:
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row"))


def _endturn(rpc, rid) -> None:
    try:
        rpc("applyAction", {"runnerId": rid, "actions": [{"kind": "endturn"}]}, 60)
    except Exception:
        pass


def _move_to(rpc, rid, uid, cur, cands) -> tuple:
    for t in cands:
        try:
            r = rpc("applyAction", {"runnerId": rid, "actions": [
                {"kind": "move", "unitId": uid, "to": {"col": t[0], "row": t[1]}}]}, 60)
        except Exception:
            continue
        if isinstance(r, dict) and r.get("ok", True) and not r.get("error"):
            return t
    return cur


def _enemy_turn_skip(rpc, rid, my_player: int) -> None:
    """Tour ennemi SAUTE : on endturn a sa place jusqu'a recuperer la main. L'ennemi n'agit donc
    JAMAIS -> les seules mutations de PV entre deux de mes tours sont les ticks de debut de tour."""
    for _ in range(6):
        cp = rpc("decisionView", {"runnerId": rid, "maxRank": 1}, 60).get("currentPlayer")
        if cp == my_player:
            return
        _endturn(rpc, rid)
    print("[envfire] /!\\ la main ne revient pas")


def _fire_on(rpc, rid, pos: tuple) -> tuple:
    """(porte_le_feu, remaining) de la tuile `pos`, lu sur le RPC `tileMeta` (`tiles[].effects`) —
    la MEME source que `_load_tile_effects`. Prouve que le DoT observe vient bien d'une tuile en
    feu (et permet de piloter la re-pose)."""
    tm = rpc("tileMeta", {"runnerId": rid}, 60)
    rows = tm.get("tiles") if isinstance(tm, dict) else tm
    for t in (rows or []):
        if (t.get("col"), t.get("row")) != pos:
            continue
        for e in (t.get("effects") or []):
            if str(e.get("name") or "").lower().startswith("fire"):
                return True, e.get("remaining")
    return False, None


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=90101)
    ap.add_argument("--max-rounds", type=int, default=24)
    ap.add_argument("--hp-target", type=int, default=HP_TARGET)
    ap.add_argument("--observe-ticks", action="store_true",
                    help="ne cherche PAS la fenetre du cap Resilient : pose le feu puis MESURE le "
                         "montant de chaque tick (discriminant TerminatorArmour x0.25, mods defenseur)")
    ap.add_argument("--a-units", default=A_UNITS,
                    help="cible : astraYarrick (Resilient) ou un TEMOIN non-Resilient "
                         "(ex. astraBullgryn) — le temoin doit MOURIR au tick discriminant")
    args = ap.parse_args(argv)
    sid = _resolve_session()
    rid = build(args.seed, args.hp_target, args.a_units)
    rpc = lambda m, b, t=90: _r(sid, m, b, t)   # noqa: E731

    pct = int(GC.global_value("fireDmgPct") or 20)
    pierce = int(profile_pierce(None, "Flame", ranged=False))
    print(f"[envfire] seed={args.seed} runner={rid} fireDmgPct={pct} pierce(Flame)={pierce} "
          f"hp-target={args.hp_target}")

    verdict = "AUCUN-DATAPOINT"
    try:
        dv0 = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        vin_u = (_by_vis(dv0, P_UNITS) or [None])[0]
        tgt_u = (_by_vis(dv0, args.a_units) or [None])[0]
        if vin_u is None or tgt_u is None:
            print(f"[envfire] roster KO (vin={vin_u} tgt={tgt_u})")
            return 2
        vin, tgt = vin_u["id"], tgt_u["id"]
        my_player = dv0.get("currentPlayer")
        vin_norm = None
        for u in (dv0.get("units") or []):
            if u.get("id") == vin:
                for ab in (u.get("abilities") or []):
                    if ab.get("kind") == "normal":
                        vin_norm = ab.get("id") if ab.get("id") is not None else ab.get("abilityId")
        if vin_norm is None:
            print("[envfire] attaque normale de Vindicta introuvable")
            return 2
        print(f"[envfire] vindicta=u{vin} (normale={vin_norm}) cible=u{tgt} me={my_player}")

        hp_max = None
        dot = None
        hp_prev = None
        ticks = []
        for rnd in range(args.max_rounds):
            dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1}, 60)
            tu = next((u for u in (dec.get("units") or []) if u.get("id") == tgt), None)
            vu = next((u for u in _alive(dec) if u.get("id") == vin), None)
            if tu is None or not tu.get("alive"):
                print(f"[envfire] r{rnd}: cible MORTE")
                if hp_prev is not None and dot is not None and dot // 2 < hp_prev <= dot:
                    verdict = "UNCAPPED(mort)"
                    ticks.append({"rnd": rnd, "hp_before": hp_prev, "dot": dot,
                                  "hp_after": 0, "verdict": "UNCAPPED"})
                break
            if vu is None:
                print(f"[envfire] r{rnd}: Vindicta morte -> stop")
                break
            hp = int(tu.get("hp") or 0)
            if hp_max is None:
                snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
                su = next((u for u in (snap.get("units") or [])
                           if u.get("entityId") == tgt), {})
                st, sd = su.get("stats") or {}, su.get("statDelta") or {}
                hp_max = int(st.get("health") or 0) - int(sd.get("health") or 0)
                armor = int(st.get("fixedArmor") or 0)
                base = int(_round_fix64(Fraction(pct * hp_max, 100), 0))
                dot = int(round(apply_pierce_and_modifiers(base, pierce_pct=pierce,
                                                           armor=armor, mods=None)))
                print(f"[envfire] cible: hp_max={hp_max} armure={armor} base={base} dot={dot} "
                      f"fenetre discriminante=({dot // 2}, {dot}]")

            # tick detecte = baisse de PV depuis MON tour precedent (l'ennemi n'a rien fait)
            if hp_prev is not None and hp < hp_prev:
                d = hp_prev - hp
                discr = dot // 2 < hp_prev <= dot
                v = ("CAPPED" if hp == 1 else "UNCAPPED" if d == dot else "AUTRE")
                ticks.append({"rnd": rnd, "hp_before": hp_prev, "dmg": d, "dot": dot,
                              "hp_after": hp, "discriminant": discr, "verdict": v})
                print(f"[envfire] r{rnd}: TICK hp {hp_prev} -> {hp} (d={d}, dot={dot}, "
                      f"dot/4={dot // 4}) {'** DISCRIMINANT **' if discr else '(modele)'} -> {v}")
                if args.observe_ticks:
                    print(f"[envfire] r{rnd}: MONTANT DU TICK = {d} "
                          f"(sans mod defenseur : {dot} ; avec TerminatorArmour x0.25 : {dot // 4})")
                    verdict = (f"TICK={d} dot={dot} quart={dot // 4}")
                    break
                if discr:
                    verdict = f"CAPPED(hp=1)" if hp == 1 else f"AUTRE(hp={hp}, d={d})"
                    break
            elif hp_prev is not None and hp == hp_prev:
                print(f"[envfire] r{rnd}: pas de tick (feu eteint) hp={hp}")

            vp, tp = _pos(vu), _pos(tu)
            dist = hexgeo.distance(vp, tp)
            on_fire, fire_rem = _fire_on(rpc, rid, tp)
            print(f"[envfire] r{rnd}: hp={hp} pos_cible={tp} feu={on_fire} remaining={fire_rem}")
            # `--observe-ticks` : des que la tuile brule, on CESSE d'attaquer et on ne fait que
            # mesurer le MONTANT des ticks (mode « quel est le degat du feu ? » ; le mode par defaut
            # cherche la fenetre du cap Resilient).
            in_window = dot is not None and dot // 2 < hp <= dot
            if args.observe_ticks and on_fire:
                print(f"[envfire] r{rnd}: observe-ticks -> on laisse le tick (hp={hp})")
            elif in_window and on_fire:
                print(f"[envfire] r{rnd}: hp={hp} DANS la fenetre ET tuile EN FEU -> on laisse le tick")
            else:
                # se poser a distance 2 EXACTEMENT (arme Flame Range=2 ; au contact = Physical)
                if dist != 2:
                    occ = {_pos(u) for u in _alive(dec)} - {vp}
                    ring2 = [t for t in hexgeo.ring(tp[0], tp[1], 2)
                             if 0 <= t[0] < W and 0 <= t[1] < H and t not in occ
                             and hexgeo.distance(vp, t) <= MV_VIN]
                    ring2.sort(key=lambda t: hexgeo.distance(vp, t))
                    if ring2:
                        vp = _move_to(rpc, rid, vin, vp, ring2)
                        dist = hexgeo.distance(vp, tp)
                    else:                       # trop loin : se rapprocher
                        goal = [t for t in hexgeo.disk(vp[0], vp[1], MV_VIN)
                                if 0 <= t[0] < W and 0 <= t[1] < H and t not in occ and t != vp]
                        goal.sort(key=lambda t: hexgeo.distance(t, tp))
                        if goal:
                            vp = _move_to(rpc, rid, vin, vp, goal[:6])
                            dist = hexgeo.distance(vp, tp)
                if dist == 2:
                    rr = rpc("applyAction", {"runnerId": rid, "actions": [
                        {"kind": "ability", "casterId": vin, "targetId": tgt,
                         "abilityType": vin_norm}]}, 90)
                    ok = isinstance(rr, dict) and not rr.get("error")
                    hits = {u.get("squadId"): u.get("hp") for u in (rr.get("units") or [])}
                    nh = hits.get(tgt)
                    print(f"[envfire] r{rnd}: ATTAQUE ranged Flame ok={ok} dist={dist} "
                          f"hp {hp} -> {nh}")
                    if nh is not None:
                        hp = int(nh)
                else:
                    print(f"[envfire] r{rnd}: dist={dist} != 2 -> pas d'attaque ce tour")

            hp_prev = hp
            _endturn(rpc, rid)
            _enemy_turn_skip(rpc, rid, my_player)

        print(f"\n[envfire] BILAN ({len(ticks)} ticks) :")
        for t in ticks:
            print(f"  r{t['rnd']} hp {t['hp_before']} -> {t.get('hp_after')} "
                  f"d={t.get('dmg')} dot={t['dot']} discr={t.get('discriminant')} "
                  f"-> {t['verdict']}")
        print(f"[envfire] VERDICT = {verdict}")
        return 0 if verdict.startswith("CAPPED") else (1 if verdict.startswith("UNCAPPED") else 4)
    finally:
        try:
            _r(sid, "disposeRunner", {"runnerId": rid}, 15)
            print(f"[envfire] runner {rid} dispose")
        except Exception as e:
            print(f"[envfire] dispose KO: {e}")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
