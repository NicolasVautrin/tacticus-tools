#!/usr/bin/env python
"""Probe #884 -- le canal DISPLAY `Average` des QUATRE descripteurs `EffectAdditionalHits`
qui publiaient `min`/`max` SANS `amount`.

## L'artefact natif, LU (build rnca9r7q6c)

`IdunBattle.Entities.Effects.BaseEffect$$GetMinMaxDamage(this, isPrediction, minVar, maxVar)` :

    minNode = DSLFormulas.ConfigVar(minVar, AbilityStateFromEffect(...), config)
    maxNode = DSLFormulas.ConfigVar(maxVar, AbilityStateFromEffect(...), config)
    isPrediction == 0 -> DSLFormulas.RandomAmount(minNode, maxNode)     # noeud ROLL
    isPrediction != 0 -> DSLFormulas.Average(minNode, maxNode)          # noeud DISPLAY

`GetMinMaxDamage(this, p)` (2-arg) = `GetMinMaxDamage(this, p, 0xc = minDmg, 0xd = maxDmg)` ;
`GetMinMaxDamage2(this, p)` = `GetMinMaxDamage(this, p, 0x36 = minDmg_2, 0x37 = maxDmg_2)`.

`IdunBattle.Entities.Effects.EffectAdditionalHits$$Create(out, trigger, roll, type, profile,
hits, forceOverkill, display)` pose `out+0x08 = roll` puis `out+0x10 = display if display else
roll` ; `IdunBattle.Entities.Effects.BaseEffect$$AdditionalHits(this, entities, useDisplay)` lit
`min = max = <+0x10>.Calculate()` quand `useDisplay`, sinon `<+0x08>.CalculateMin()` /
`.CalculateMax()`. `DSLFormulas$$Average(a, b)` = `DivideAmount(SumAmount(a, b), Direct(2),
rule = null)` -> `IdunBattle.Entities.Formulas.DivideAmount$$Calculate` ->
`IdunBattle.DSL.AAmountFormula$$RoundFix64Result(., 0)` = `FixMath.NET Fix64.Round`
demi-vers-le-PAIR -- donc un ENTIER, jamais un `.5`.

## Les QUATRE descripteurs et leur porteur

  * `SquigHound_AdditionalHitsEffect`      (1292) -- `orksRuntherd`      , ability 1082
  * `CordClaw_AdditionalHitsEffect`        (1250) -- `admecRuststalker`  , ability 1122
  * `SorcerousFacade_AdditionalHitsEffect` (1204) -- `thousTzaangor`     , ability 1100
  * `FearOfTheUnseen_ExtraDamageEffect`    (1239) -- `tyranDeathleaper`  , ability 1115

Les quatre abilities POSEUSES sont au registre `ABILITY_CLASSES` et les quatre porteurs sont dans
`rl_duel build --list-pool` : confrontables sans injection catalogue.

## Ce que ce probe MESURE

Oracle = canal `ranked` natif (`decisionView.attackPlans[].evals[].ranked[]` : `dmgMin`/`dmgMax`
par tuile candidate), confronte a `playbook.prediction.make_normal_attack_predictions`. Une seule
CAPTURE live, puis un REPLAY offline par VARIANTE de modele du noeud DISPLAY :

  * `port`       -- `Fix64.Round((min + max) / 2)` demi-vers-le-pair (le port livre) ;
  * `predefined` -- l'ANCIEN modele : pas d'`amount`, la prediction lit `[min, max]` ;
  * `float`      -- `(min + max) / 2` SANS arrondi (le mutant que le montage #419-r1-tr11-r5 ne
                    pouvait PAS separer : sa somme etait PAIRE) ;
  * `floor`      -- `Fix64.Floor` au lieu de `Fix64.Round`.

Le regime servi (rank 17 -> `AbilityVariablesMultiplierPercentage` 180, ability_level 50) donne des
sommes IMPAIRES sur `SorcerousFacade` [997, 1996], `FearOfTheUnseen` [1197, 1496] et `SquigHound`
[2394, 3589] : `float` y publie un `.5` que `port` n'a pas. Et `floor` diverge de `port` des que la
partie entiere de la moyenne est IMPAIRE (`SquigHound` : 2991 contre 2992).

ASCII only. Usage :
    python probe_884_average_display.py [--seed 88401] [--state-file <abs>] [--keep]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hexgeo                                                  # noqa: E402
from rl_collect_batch import _resolve_session, _rpc            # noqa: E402
from engine.dsl.base import _round_fix64                       # noqa: E402
from engine.entities.effects.magnitude import ability_var      # noqa: E402
from engine.playbook import scene as SC                        # noqa: E402
from engine.playbook import prediction                         # noqa: E402
from engine.playbook.scene import Scene                        # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
BOARD = "MC1_67"

#: (visualId du porteur, ability POSEUSE, nom d'effet publie par le decisionView, cle min, cle max,
#: cle gameconfig de l'ability qui porte les variables)
CARRIERS = [
    ("thousTzaangor",    1100, "SorcerousFacade_AdditionalHits", "minDmg",   "maxDmg",   "SorcerousFacade"),
    ("tyranDeathleaper", 1115, "FearOfTheUnseen_ExtraDamage",    "minDmg",   "maxDmg",   "FearOfTheUnseen"),
    ("orksRuntherd",     1082, "SquigHound_AdditionalHits",      "minDmg",   "maxDmg",   "SquigHound"),
    ("admecRuststalker", 1122, "CordClaw_AdditionHits",          "minDmg_2", "maxDmg_2", "CordClaw"),
]
P_UNITS = ",".join(c[0] for c in CARRIERS) + ",thousSorcerer"   # + l'allie Psyker de 1100
A_UNITS = "necroWarden,necroWarden,necroWarden"

VARIANTS = ("port", "predefined", "float", "floor")


# ---------------------------------------------------------------- modeles du noeud DISPLAY

def display_value(mn: int, mx: int, variant: str):
    """La valeur du noeud DISPLAY selon la VARIANTE de modele. `None` = pas de cle `amount`."""
    if variant == "predefined":
        return None
    if variant == "float":
        return (int(mn) + int(mx)) / 2
    if variant == "floor":
        return _round_fix64(Fraction(int(mn) + int(mx), 2), 2)      # RoundFix64Result mode 2
    return _round_fix64(Fraction(int(mn) + int(mx), 2), 0)          # mode 0 = Fix64.Round


def patch_variant(variant: str):
    """Reecrit `additional_hit_groups` des QUATRE classes d'effet pour la variante demandee.
    Rend un callable de restauration."""
    from engine.entities.effects import loki
    from engine.entities.effects.loki import hits as H

    targets = [H.SorcerousFacadeAdditionalHitsEffect, H.FearOfTheUnseenExtraDamageEffect,
               H.SquigHoundAdditionalHitsEffect, H.CordClawAdditionalHitsEffect]
    saved = [(cls, cls.additional_hit_groups) for cls in targets]

    def make(orig):
        def wrapper(self, ctx=None):
            grps = orig(self, ctx)
            if not grps:
                return grps
            out = []
            for g in grps:
                g = dict(g)
                v = display_value(g["min"], g["max"], variant)
                if v is None:
                    g.pop("amount", None)
                else:
                    g["amount"] = v
                out.append(g)
            return out
        return wrapper

    for cls, orig in saved:
        cls.additional_hit_groups = make(orig)

    def restore():
        for cls, orig in saved:
            cls.additional_hit_groups = orig
    _ = loki                                    # garde l'import explicite (pas de faux "unused")
    return restore


# ---------------------------------------------------------------- montage

def build(seed: int, state_file: Path) -> int:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.unlink(missing_ok=True)
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
         "--state-file", str(state_file), "--board", BOARD,
         "--p-units", P_UNITS, "--a-units", A_UNITS,
         "--hp-target", "400000", "--hp-player", "400000"],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not state_file.exists():
        print("[884] build KO: %s" % ((proc.stderr or proc.stdout or "")[-500:]), file=sys.stderr)
        sys.exit(2)
    return json.loads(state_file.read_text())["runnerId"]


def _pos(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row"))


def _by_vis(dec):
    return {u.get("visualId"): u for u in (dec.get("units") or []) if u.get("alive")}


def _rich(rpc, rid):
    return rpc("decisionView", {"runnerId": rid, "maxRank": 99, "allAbilities": True}, 150)


def _advance_to_my_turn(rpc, rid, owner, max_iter=10):
    for _ in range(max_iter):
        dec = rpc("decisionView", {"runnerId": rid}, 150)
        if not isinstance(dec, dict) or not dec.get("ok"):
            return None
        if dec.get("currentPlayer") == owner:
            return _rich(rpc, rid)
        rpc("aiPlayTurn", {"runnerId": rid}, 240)
        dec2 = rpc("decisionView", {"runnerId": rid}, 150)
        if isinstance(dec2, dict) and dec2.get("ok") and dec2.get("currentPlayer") != owner:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    return None


def _end_round(rpc, rid, owner) -> None:
    for _ in range(4):
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
        dec = rpc("decisionView", {"runnerId": rid}, 90)
        if isinstance(dec, dict) and dec.get("ok") and dec.get("currentPlayer") != owner:
            rpc("aiPlayTurn", {"runnerId": rid}, 300)
            return


def _effect_names(dec, uid):
    for u in (dec.get("units") or []):
        if u.get("id") == uid:
            return [e.get("name") for e in (u.get("effects") or [])]
    return []


def _cast(rpc, rid, dec, caster_id, ability_id):
    """Caste `ability_id` depuis `caster_id` sur la 1re cible que le NATIF declare valide."""
    tg = rpc("abilityTargets", {"runnerId": rid, "unitId": caster_id,
                                "abilityType": ability_id}, 90)
    tids = [t.get("unitId") for t in ((tg or {}).get("targets") or []) if t.get("unitId")]
    if not tids:
        # abilities self-only : le natif ne rend aucune cible -> caster sur soi
        tids = [caster_id]
    for tid in tids:
        r = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "unitId": caster_id, "abilityType": ability_id,
            "targetId": tid}}, 150)
        if isinstance(r, dict) and r.get("ok"):
            return tid
    return None


# ---------------------------------------------------------------- mesure

def capture_rows(rpc, rid, dec, att_id):
    """Les lignes NATIVES (`ranked`) de l'attaque NORMALE de `att_id` : tuile, cible, dmgMin/dmgMax.
    Une seule capture -- le replay offline par variante se fait ensuite sur ces memes lignes."""
    rows = []
    norm_ids = {ab.get("id") for u in (dec.get("units") or []) if u.get("id") == att_id
                for ab in (u.get("abilities") or []) if ab.get("kind") == "normal"}
    for ap in (dec.get("attackPlans") or []):
        if ap.get("unitId") != att_id:
            continue
        for ev in (ap.get("evals") or []):
            if norm_ids and ev.get("abilityId") not in norm_ids:
                continue
            for rk in (ev.get("ranked") or []):
                if rk.get("dmgMax") is None or rk.get("col") is None:
                    continue
                rows.append({"tile": (rk["col"], rk["row"]), "tgt": ev.get("targetId"),
                             "nat": (rk.get("dmgMin"), rk.get("dmgMax"))})
    return rows


def replay_offline(rpc, rid, dec, att_id, rows, variant):
    """Recalcule l'offline sur les MEMES lignes, sous la variante donnee."""
    restore = patch_variant(variant)
    try:
        predictor = SC.build_predictor(rpc, rid)
        if predictor is None:
            return None
        sctx = SC.step_context(predictor, dec)
        scene = Scene.from_predictor_sctx(predictor, sctx, None)
        out = []
        for r in rows:
            res = prediction.make_normal_attack_predictions(scene, att_id, r["tgt"], r["tile"],
                                                            meta=True)
            if not res:
                out.append(None)
                continue
            acc = res[0].prediction.accurate_health_damage
            out.append((acc.min, acc.max))
        return out
    finally:
        restore()


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=88401)
    ap.add_argument("--state-file", default=str(ROOT / "logs" / "runners" / "_884avg_state.json"))
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--runner", type=int, default=None)
    args = ap.parse_args(argv)

    sid = _resolve_session()
    rpc = lambda m, b, t=90: (_rpc(sid, m, [b], timeout=t).get("result") or {})   # noqa: E731

    # 0. le REGIME SERVI, offline : bornes, somme, ratio -- c'est ce qui dit si le montage
    #    discrimine AVANT toute mesure live.
    print("[884] regime offline (ability_level 50, multiplier 180 = rank 17)")
    for _vis, _ab, _fx, kmin, kmax, cfg in CARRIERS:
        mn = ability_var(cfg, kmin, 50, multiplier_pct=180)
        mx = ability_var(cfg, kmax, 50, multiplier_pct=180)
        if mn is None or mx is None:
            print("  %-20s BORNES ABSENTES au gameconfig" % cfg)
            continue
        s = int(mn) + int(mx)
        vals = {v: display_value(mn, mx, v) for v in VARIANTS}
        print("  %-20s [%5d,%5d] somme=%6d %s ratio=%.4f  port=%s float=%s floor=%s"
              % (cfg, mn, mx, s, "IMPAIRE" if s % 2 else "paire", float(mx) / float(mn),
                 vals["port"], vals["float"], vals["floor"]))

    rid = args.runner if args.runner is not None else build(args.seed, Path(args.state_file))
    print("[884] seed=%d runner=%s board=%s" % (args.seed, rid, BOARD))
    verdicts = []
    try:
        dec = _rich(rpc, rid)
        if not (isinstance(dec, dict) and dec.get("ok")):
            print("[884] decisionView KO", file=sys.stderr)
            return 2
        byvis = _by_vis(dec)
        owner = (byvis.get(CARRIERS[0][0]) or {}).get("owner")
        dec = _advance_to_my_turn(rpc, rid, owner) or dec
        byvis = _by_vis(dec)

        # 1. TEMOIN -- avant tout cast, aucun des 4 effets n'est pose : natif == offline.
        print("[884] --- TEMOIN (aucun effet pose) ---")
        for vis, _ab, fx, *_ in CARRIERS:
            u = byvis.get(vis)
            if u is None:
                print("  %-20s ABSENT du montage" % vis)
                continue
            rows = capture_rows(rpc, rid, dec, u["id"])
            if not rows:
                print("  %-20s aucune ligne `ranked` (pas de plan d'attaque ce tour)" % vis)
                continue
            off = replay_offline(rpc, rid, dec, u["id"], rows, "port")
            ok = sum(1 for r, o in zip(rows, off or []) if o == r["nat"])
            print("  %-20s %d/%d lignes en accord (effets: %s)"
                  % (vis, ok, len(rows), _effect_names(dec, u["id"])))

        # 2. CAST des 4 abilities poseuses
        print("[884] --- CAST des abilities poseuses ---")
        for vis, ab, fx, *_ in CARRIERS:
            u = _by_vis(_rich(rpc, rid)).get(vis)
            if u is None:
                continue
            tid = _cast(rpc, rid, dec, u["id"], ab)
            print("  %-20s cast %d -> cible %s" % (vis, ab, tid))

        # 3. round complet puis MESURE
        _end_round(rpc, rid, owner)
        dec = _advance_to_my_turn(rpc, rid, owner)
        if dec is None:
            print("[884] impossible de revenir a mon tour", file=sys.stderr)
            return 2
        byvis = _by_vis(dec)

        print("[884] --- MESURE (effets poses) ---")
        for vis, _ab, fx, *_ in CARRIERS:
            u = byvis.get(vis)
            if u is None:
                print("  %-20s ABSENT (mort ?)" % vis)
                verdicts.append((vis, "ABSENT", None))
                continue
            names = _effect_names(dec, u["id"])
            if fx not in names:
                print("  %-20s effet %s NON POSE (effets: %s) -- NON CONFRONTE" % (vis, fx, names))
                verdicts.append((vis, "EFFET ABSENT", names))
                continue
            rows = capture_rows(rpc, rid, dec, u["id"])
            if not rows:
                print("  %-20s effet POSE mais aucune ligne `ranked` -- NON CONFRONTE" % vis)
                verdicts.append((vis, "PAS DE PLAN", names))
                continue
            res = {}
            for v in VARIANTS:
                off = replay_offline(rpc, rid, dec, u["id"], rows, v)
                if off is None:
                    continue
                ok = sum(1 for r, o in zip(rows, off) if o == r["nat"])
                worst = max((max(abs((o or (0, 0))[0] - r["nat"][0]),
                                 abs((o or (0, 0))[1] - r["nat"][1]))
                             for r, o in zip(rows, off)), default=None)
                res[v] = (ok, len(rows), worst, tuple(off))
            print("  %-20s effet POSE, %d lignes" % (vis, len(rows)))
            for v in VARIANTS:
                if v in res:
                    ok, n, worst, _ = res[v]
                    print("      %-11s %2d/%2d en accord, |ecart| max %s" % (v, ok, n, worst))
            distinct = {v: res[v][3] for v in res}
            same_as_port = [v for v in res if v != "port" and distinct[v] == distinct.get("port")]
            print("      variantes NON separees par ce montage : %s"
                  % (same_as_port if same_as_port else "aucune -- les 4 modeles divergent"))
            verdicts.append((vis, res, same_as_port))
    finally:
        if not args.keep and args.runner is None:
            subprocess.run([sys.executable, "rl_duel.py", "dispose", "--runner", str(rid)],
                           cwd=str(PYDIR), stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, check=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
