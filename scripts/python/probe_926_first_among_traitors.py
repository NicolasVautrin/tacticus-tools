#!/usr/bin/env python3
"""#926 -- le passif `FirstAmongTraitors` (`TriggeredAbilityType` 0x428 = 1064) de `blackAbaddon`.

RE complete : en tete d'`engine/entities/effects/loki/first_among_traitors.py` (l'ability, l'effet,
le selecteur et la magnitude) et dans la docstring de
`engine/playbook/friends_in_range.py::FirstAmongTraitorsPlaybook` (la face DECISION owner).
Ce probe MESURE ; les assertions vivent dans `tests/engine/runner/test_926_first_among_traitors_live.py`.

MONTAGE -- il DISCRIMINE les trois gates separement (un accord obtenu sur un seul bras ne
prouverait rien) :

    blackAbaddon      (3,3)  PORTEUR de l'aura                -> attendu : AUCUN bonus (self EXCLU)
    emperNoiseMarine  (3,4)  Chaos,    dist 1                 -> attendu : bonus
    ultraTitus        (2,3)  IMPERIAL, dist 1                 -> attendu : RIEN (gate TRAIT)
    worldKharn        (0,0)  Chaos,    dist 4 > range 2       -> attendu : RIEN (gate DISTANCE)

DEUX ennemis, et c'est LOAD-BEARING : l'attaque normale d'Abaddon declenche son AUTRE passif
`LetTheGalaxyBurn`, qui pose l'effet de TUILE `DespoiledGround` (1476) sur la cible. Son volet
`DespoiledGround_ExtraDamagePct` (1478) n'est PAS porte (residu ANTERIEUR, `case-159` §« volet
DespoiledGround ») -> toute prediction CONTRE la cible frappee diverge de x1.25 a x1.33, pour une
raison qui n'a rien a voir avec ce cas. L'etage 5 mesure donc sur l'ennemi que le porteur N'A PAS
frappe.

ETAGES
  0  registres et litteraux (offline)
  1  la formule, au chiffre, et le POINT DE CAP (offline, contre le gameconfig vivant)
  2  NATIF : qui PORTE l'effet 1063, et ou (live)
  3  PREDICTION : oracle NATIF `decisionView.attackPlans[].evals[].ranked[].dmg{Min,Max}` PAR TUILE
     candidate vs le port -- le gate geometrique se lit TUILE PAR TUILE
  4  DECISION owner : `triggeredMoveTrace` (armement NOMINATIF par runnerId) -> le total natif de
     `TriggeredAbilitiesUtility` par (unite, tuile) vs la feuille portee
  5  LE TERME CROISSANT : Abaddon attaque, `TotalAttacksMade` avance, la prediction NATIVE des
     beneficiaires doit monter -- et le port doit suivre
  6  COMBAT : `damage_model.attacker_modifiers(...).additive` par unite (pas de fork avec la
     prediction), avec la VALEUR EXACTE attendue
  7  MUTANTS : quatre mutations du port DOIVENT faire rougir l'etage 3 ou l'etage 6

ASCII only dans les sorties (console cp1252).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

import hexgeo                                                    # noqa: E402
import rl_collect_batch as L                                     # noqa: E402  (foyer `_rpc`)

BOARD = "MC1_67"
SEED = "777"
CARRIER = "blackAbaddon"          # porteur du passif (HERO du pool -- aucun montage requis)
NEAR_CHAOS = "emperNoiseMarine"   # UnitTrait.Chaos, distance 1, PAS de deep strike
PLAIN = "ultraTitus"              # Imperial -> PAS le trait Chaos, distance 1
FAR_CHAOS = "worldKharn"          # UnitTrait.Chaos, LOIN
FOE_NEAR = "ultraApothecary"      # cible des beneficiaires
FOE_FAR = "necroWarden"           # cible d'Abaddon a l'etage 5 (pour isoler `DespoiledGround`)

PLACES = {CARRIER: (3, 3), NEAR_CHAOS: (3, 4), PLAIN: (2, 3), FAR_CHAOS: (0, 0)}
A_PLACES = {FOE_NEAR: (2, 4), FOE_FAR: (5, 1)}
ABILITY = "FirstAmongTraitors"
EFFECT_NAME = "FirstAmongTraitors_ExtraDmg"
#: Sortie de run sous le `logs/` de la RACINE, jamais `scripts/python/logs/` (#935) : `probe_273`
#: ne reconnait comme SORTIE que les racines de premier niveau (`_OUTPUT_ROOTS = {"logs", "app"}`).
STATE: Path = Path(__file__).resolve().parents[2] / "logs" / "st-926.json"
TOL = 3          # meme tolerance d'arrondi que `test_aura_position_live`


def rpc(method, body=None, timeout=120, tolerate=False):
    try:
        return L._rpc(L._resolve_session(), method, [body if body is not None else {}],
                      timeout=timeout).get("result") or {}
    except Exception as exc:                                     # noqa: BLE001
        if tolerate:
            print("[rpc] %s indisponible (%s)" % (method, exc))
            return {}
        raise


def _duel(args):
    return subprocess.run([sys.executable, "rl_duel.py"] + args, cwd=str(PYDIR),
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", check=False)


def build(state: Path) -> int:
    """Montage : rosters explicites + positions FORCEES (la geometrie de spawn ne decide de rien).

    `--no-ai` : on pilote tout, aucun tour adverse ne vient bouger le porteur sous la mesure."""
    state.parent.mkdir(parents=True, exist_ok=True)
    if state.exists():
        state.unlink()
    args = ["build", "--seed", SEED, "--board", BOARD, "--no-ai", "--state-file", str(state),
            "--p-units", ",".join((CARRIER, NEAR_CHAOS, PLAIN, FAR_CHAOS)),
            "--a-units", ",".join((FOE_NEAR, FOE_FAR))]
    for uid, (c, r) in PLACES.items():
        args += ["--place", "%s:%d,%d" % (uid, c, r)]
    for uid, (c, r) in A_PLACES.items():
        args += ["--a-place", "%s:%d,%d" % (uid, c, r)]
    p = _duel(args)
    if not state.exists():
        raise SystemExit("build KO (MONTAGE, pas une mesure) : "
                         + (p.stderr or p.stdout or "")[-900:])
    return int(json.loads(state.read_text(encoding="utf-8"))["runnerId"])


def ids_by_visual(dec) -> dict:
    return {u.get("visualId"): int(u.get("id")) for u in (dec.get("units") or [])}


# ------------------------------------------------------------------ etage 0 : registres (offline)
def etage0() -> dict:
    from engine.entities.ability_constant_type import AbilityConstantType
    from engine.entities.ability_variable_type import AbilityVariableType
    from engine.entities.effect_type import EffectType
    from engine.entities.effects.factory import ABILITY_INIT_OWNER_EFFECTS, EFFECT_CLASSES
    from engine.entities.traits.unit_trait import UnitTrait
    from engine.entities.triggered_ability_type import TriggeredAbilityType
    from engine.playbook.adjacent_unit_preference import load_playbook
    from engine.playbook.non_owner import load_playbook_non_owner

    out = {
        "init_owner": list(ABILITY_INIT_OWNER_EFFECTS.get(ABILITY) or []),
        "effect_class": (EFFECT_CLASSES.get(EFFECT_NAME).__name__
                         if EFFECT_CLASSES.get(EFFECT_NAME) else None),
        "playbook_owner":
            type(load_playbook(int(TriggeredAbilityType.FirstAmongTraitors))).__name__,
        "playbook_non_owner":
            type(load_playbook_non_owner(int(TriggeredAbilityType.FirstAmongTraitors))).__name__,
        "litteraux": {
            "TriggeredAbilityType.FirstAmongTraitors": int(TriggeredAbilityType.FirstAmongTraitors),
            "EffectType.FirstAmongTraitors_ExtraDmg":
                int(EffectType.FirstAmongTraitors_ExtraDmg),
            "UnitTrait.Chaos": int(UnitTrait.Chaos),
            "AbilityConstantType.range": int(AbilityConstantType.range),
            "AbilityVariableType.extraDmg": int(AbilityVariableType.extraDmg),
            "AbilityVariableType.extraDmg_2": int(AbilityVariableType.extraDmg_2),
            "AbilityVariableType.maxDmg": int(AbilityVariableType.maxDmg),
        },
    }
    print("[0] ABILITY_INIT_OWNER_EFFECTS[%s] = %s" % (ABILITY, out["init_owner"]))
    print("[0] EFFECT_CLASSES[%s]  = %s" % (EFFECT_NAME, out["effect_class"]))
    print("[0] playbook OWNER / NON-OWNER      = %s / %s"
          % (out["playbook_owner"], out["playbook_non_owner"]))
    print("[0] litteraux                       = %s" % json.dumps(out["litteraux"]))
    return out


# --------------------------------------------------------------- etage 1 : la formule (offline)
def etage1(level=50, mult=100) -> dict:
    """`Min(Sum(extraDmg, Multiply(n, extraDmg_2)), maxDmg)` -- et le POINT DE CAP.

    La constante `buffMaxLevel` du gameconfig (= 13) est un temoin INDEPENDANT du cap : le port ne
    la lit pas, mais `extraDmg + buffMaxLevel x extraDmg_2` doit tomber EXACTEMENT sur `maxDmg`."""
    from engine.entities.effects.loki.first_among_traitors import (
        EXTRA_DMG_2_VAR, EXTRA_DMG_VAR, FIRST_AMONG_TRAITORS, MAX_DMG_VAR,
        FirstAmongTraitorsExtraDmgEffect, first_among_traitors_range)
    from engine.entities.effects.magnitude import ability_var

    base = int(ability_var(FIRST_AMONG_TRAITORS, EXTRA_DMG_VAR, level, multiplier_pct=mult) or 0)
    per = int(ability_var(FIRST_AMONG_TRAITORS, EXTRA_DMG_2_VAR, level, multiplier_pct=mult) or 0)
    cap = int(ability_var(FIRST_AMONG_TRAITORS, MAX_DMG_VAR, level, multiplier_pct=mult) or 0)
    buff_max = ability_var(FIRST_AMONG_TRAITORS, "buffMaxLevel", is_constant=True)
    rows, ok = [], True
    for n in (0, 1, 2, 13, 14, 40):
        e = FirstAmongTraitorsExtraDmgEffect(EFFECT_NAME)
        e.ability_level, e.ability_variables_multiplier = level, mult
        got = e._current_damage_bonus(n)
        want = min(base + n * per, cap)
        ok = ok and int(got or 0) == want
        rows.append({"n": n, "port": got, "attendu": want})
        print("[1] n=%-3d port=%-6s attendu=%-6d %s"
              % (n, got, want, "OK" if int(got or 0) == want else "ECART"))
    print("[1] level=%s mult=%s : extraDmg=%d extraDmg_2=%d maxDmg=%d range=%s buffMaxLevel=%s"
          % (level, mult, base, per, cap, first_among_traitors_range(), buff_max))
    if buff_max is not None:
        cap_ok = base + int(buff_max) * per == cap
        ok = ok and cap_ok
        print("[1] temoin INDEPENDANT du cap : extraDmg + buffMaxLevel x extraDmg_2 = %d (maxDmg=%d) %s"
              % (base + int(buff_max) * per, cap, "OK" if cap_ok else "ECART"))
    return {"rows": rows, "base": base, "per": per, "cap": cap, "buff_max": buff_max, "ok": ok}


# ------------------------------------------------------------------ etage 2 : NATIF (live)
def etage2(dec) -> dict:
    """QUI porte l'effet 1063 -- le natif le pose sur le SEUL porteur du passif (owner-effect)."""
    by_vis = ids_by_visual(dec)
    pos = {int(u["id"]): (u["pos"]["col"], u["pos"]["row"])
           for u in (dec.get("units") or []) if u.get("pos")}
    eff = {int(u["id"]): [e.get("name") for e in (u.get("effects") or [])]
           for u in (dec.get("units") or [])}
    rows = {}
    for vis in (CARRIER, NEAR_CHAOS, PLAIN, FAR_CHAOS, FOE_NEAR, FOE_FAR):
        uid = by_vis.get(vis)
        if uid is None:
            raise SystemExit("MONTAGE : %s absent du decisionView" % vis)
        d = (hexgeo.distance(pos[by_vis[CARRIER]], pos[uid])
             if uid in pos and by_vis[CARRIER] in pos else None)
        rows[vis] = {"id": uid, "pos": pos.get(uid), "dist": d,
                     "porte_1063": EFFECT_NAME in (eff.get(uid) or []),
                     "effets": sorted(eff.get(uid) or [])}
        print("[2] %-17s u%-3d pos=%-8s dist=%-5s porte_1063=%-6s effets=%s"
              % (vis, uid, rows[vis]["pos"], d, rows[vis]["porte_1063"], rows[vis]["effets"]))
    return {"rows": rows}


# --------------------------------------------- etage 3 : PREDICTION natif vs port (par TUILE)
def _scene(rid, dec):
    from engine.playbook import scene as SC
    from engine.playbook.scene import Scene
    predictor = SC.build_predictor(lambda m, b, t: rpc(m, b, t), rid)
    if predictor is None:
        raise SystemExit("combatSnapshot KO (MONTAGE)")
    sctx = SC.step_context(predictor, dec)
    return Scene.from_predictor_sctx(predictor, sctx, None), sctx


def _rows_pred(dec, scene, sctx, only_target=None) -> list:
    """Chaque tuile candidate rankee par le NATIF, avec sa prediction offline en regard."""
    from engine.playbook import prediction
    pos_by_id = sctx["pos_by_id"]
    out = []
    for ap in (dec.get("attackPlans") or []):
        a_id = ap.get("unitId")
        norm_ids = {ab.get("id") for u in (dec.get("units") or []) if u.get("id") == a_id
                    for ab in (u.get("abilities") or []) if ab.get("kind") == "normal"}
        for ev in (ap.get("evals") or []):
            if norm_ids and ev.get("abilityId") not in norm_ids:
                continue
            if only_target is not None and ev.get("targetId") != only_target:
                continue
            for rk in (ev.get("ranked") or []):
                if rk.get("dmgMax") is None or rk.get("predOptimistic"):
                    continue
                tile = ((rk["col"], rk["row"]) if rk.get("col") is not None
                        else pos_by_id.get(a_id))
                ev_off = prediction.make_normal_attack_predictions(
                    scene, a_id, ev.get("targetId"), tile)
                res = ev_off.prediction.accurate_health_damage
                out.append({"att": a_id, "tgt": ev.get("targetId"), "tile": tile,
                            "oracle": (rk.get("dmgMin"), rk.get("dmgMax")),
                            "offline": (res.min, res.max)})
    return out


def _confront(rows, cpos, vis_by_id, tag, tol=TOL) -> dict:
    bad, seen = [], {}
    for r in rows:
        d = hexgeo.distance(cpos, r["tile"]) if cpos and r["tile"] else None
        vis = vis_by_id.get(r["att"], "?")
        seen.setdefault(vis, set()).add(d)
        if (abs((r["oracle"][0] or 0) - r["offline"][0]) > tol
                or abs((r["oracle"][1] or 0) - r["offline"][1]) > tol):
            bad.append("%s u%s tuile=%s d(porteur)=%s oracle=%s offline=%s"
                       % (vis, r["att"], r["tile"], d, r["oracle"], r["offline"]))
    print("[%s] %d tuile(s) candidate(s) rankee(s), %d ecart(s) (tolerance %d)"
          % (tag, len(rows), len(bad), tol))
    for vis, ds in sorted(seen.items()):
        print("[%s] %-17s distances porteur des tuiles rankees = %s" % (tag, vis, sorted(ds)))
    for b in bad[:12]:
        print("[%s] ECART %s" % (tag, b))
    return {"rows": rows, "bad": bad, "distances": {k: sorted(v) for k, v in seen.items()}}


def etage3(rid, dec) -> dict:
    scene, sctx = _scene(rid, dec)
    by_vis = ids_by_visual(dec)
    vis_by_id = {v: k for k, v in by_vis.items()}
    cpos = sctx["pos_by_id"].get(by_vis[CARRIER])
    return _confront(_rows_pred(dec, scene, sctx), cpos, vis_by_id, "3")


# ----------------------------------- etage 4 : DECISION owner (`triggeredMoveTrace`, NOMINATIF)
def etage4(rid) -> dict:
    """La feuille `TriggeredAbilitiesUtility` : total NATIF par (unite, tuile) vs le port.

    L'armement est NOMINATIF (`{runnerId}`) : il ne touche PAS les mesures des autres agents."""
    import probe_443r1a_triggered_move_anchor as P443

    st = rpc("triggeredMoveTraceStatus", {}, 30, tolerate=True)
    if not isinstance(st, dict) or not st:
        print("[4] NON CONFRONTE -- le capteur `triggeredMoveTrace` n'est pas charge dans la "
              "session (il exige une fenetre de reinject). Rien n'en est conclu.")
        return {"status": "no-sensor"}
    rpc("triggeredMoveTraceClear", {"runnerId": rid}, 30, tolerate=True)
    rpc("triggeredMoveTraceOn", {"runnerId": rid}, 60, tolerate=True)
    try:
        rpc("aiDryRunAllUnits", {"runnerId": rid}, 240, tolerate=True)
        dump = rpc("triggeredMoveTraceDump", {"runnerId": rid, "max": 4000}, 60, tolerate=True)
    finally:
        rpc("triggeredMoveTraceOff", {"runnerId": rid}, 30, tolerate=True)
    entries = (dump or {}).get("entries") or []
    owner = [e for e in entries if e.get("utility") == "TriggeredAbilitiesUtility"]
    print("[4] %d event(s) captes, dont %d sur la feuille OWNER" % (len(entries), len(owner)))
    sid = L._resolve_session()
    prows = P443._port_rows(sid, rid, entries, bind=True)
    v = P443.check_value(prows)
    print("[4] verdict valeur [%s] %s" % (v["status"], v["message"]))
    return {"status": v["status"], "message": v["message"], "rows": prows, "entries": entries}


# ------------------------------------------------- etage 5 : le TERME CROISSANT (natif vs port)
def _normal_attack_id(dec, uid) -> "int | None":
    for u in (dec.get("units") or []):
        if int(u.get("id")) != int(uid):
            continue
        for ab in (u.get("abilities") or []):
            if ab.get("kind") == "normal":
                return ab.get("id")
    return None


def _pred_for(dec, att_id, tgt_id) -> "tuple | None":
    for ap in (dec.get("attackPlans") or []):
        if ap.get("unitId") != att_id:
            continue
        for ev in (ap.get("evals") or []):
            if ev.get("targetId") != tgt_id:
                continue
            for rk in (ev.get("ranked") or []):
                if rk.get("dmgMax") is not None and not rk.get("predOptimistic"):
                    return (rk.get("dmgMin"), rk.get("dmgMax"), (rk.get("col"), rk.get("row")))
    return None


def _actor_stats(rid) -> dict:
    a = rpc("actorStats", {"runnerId": rid}, 40, tolerate=True) or {}
    return {u["entityId"]: int(u.get("totalAttacksMade") or 0) for u in (a.get("units") or [])}


def etage5(rid, dec_avant) -> dict:
    """Abaddon ATTAQUE l'ennemi PROCHE -> `ActorStatisticsComponent+0x20` avance -> la prediction
    NATIVE des beneficiaires CONTRE L'AUTRE ennemi doit monter, et le port suivre.

    C'est le SEUL terme du cas qui ne se lit ni dans la config ni dans la geometrie : il exige un
    compteur d'ETAT, que #926 porte cote COMBAT (`components.unit_total_attacks_made`).

    ⚠ On mesure sur `FOE_FAR`, PAS sur la cible frappee : l'attaque normale d'Abaddon declenche
    `LetTheGalaxyBurn`, qui pose l'effet de tuile `DespoiledGround` (1476) sous la cible. Son volet
    `DespoiledGround_ExtraDamagePct` (1478) n'est PAS porte (residu ANTERIEUR, `case-159`), donc
    toute prediction CONTRE elle diverge de x1.25 a x1.33 pour une cause etrangere a ce cas --
    mesure du 2026-08-11, ecarts exactement proportionnels (4/3 et 5/4)."""
    by_vis = ids_by_visual(dec_avant)
    ab, ben = by_vis[CARRIER], by_vis[NEAR_CHAOS]
    foe_far, foe_near = by_vis[FOE_FAR], by_vis[FOE_NEAR]
    before = _pred_for(dec_avant, ben, foe_far)
    n_before = _actor_stats(rid)
    atk = _normal_attack_id(dec_avant, ab)
    if atk is None or before is None:
        print("[5] MONTAGE KO -- attaque normale d'Abaddon (%s) ou prediction du beneficiaire (%s) "
              "introuvable" % (atk, before))
        return {"ok": None, "montage": "KO"}
    p = _duel(["act", "ability", "--caster", str(ab), "--ability", str(int(atk)),
               "--target", str(foe_near), "--state-file", str(STATE)])
    dec_apres = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 180)
    n_after = _actor_stats(rid)
    d_n = n_after.get(ab, 0) - n_before.get(ab, 0)
    if d_n <= 0:
        print("[5] MONTAGE KO -- TotalAttacksMade d'Abaddon n'a pas bouge (%s -> %s). verbatim : %s"
              % (n_before.get(ab), n_after.get(ab),
                 (p.stdout or p.stderr or "")[:1200].replace("\n", " | ")))
        return {"ok": None, "montage": "KO", "dec_apres": dec_apres}
    after = _pred_for(dec_apres, ben, foe_far)
    print("[5] TotalAttacksMade(Abaddon) %s -> %s (delta %d)"
          % (n_before.get(ab), n_after.get(ab), d_n))
    print("[5] prediction NATIVE de %s contre %s (non despoiled) : avant=%s apres=%s"
          % (NEAR_CHAOS, FOE_FAR, before, after))
    monte = (after is not None and before is not None
             and (after[0] or 0) > (before[0] or 0) and (after[1] or 0) > (before[1] or 0))
    print("[5] le NATIF monte-t-il ? %s  (temoin que le terme croissant MORD cote jeu)" % monte)
    scene, sctx = _scene(rid, dec_apres)
    vis_by_id = {v: k for k, v in by_vis.items()}
    cpos = sctx["pos_by_id"].get(ab)
    conf = _confront(_rows_pred(dec_apres, scene, sctx, only_target=foe_far),
                     cpos, vis_by_id, "5")
    return {"ok": (not conf["bad"]) and monte, "avant": before, "apres": after, "delta_n": d_n,
            "monte": monte, "bad": conf["bad"], "dec_apres": dec_apres}


# --------------------------------------------------------- etage 6 : COMBAT (canal `additive`)
def _load_state(rid, dec):
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
    tm = rpc("tileMeta", {"runnerId": rid}, 90)
    bg = rpc("boardGraph", {"runnerId": rid}, 90)
    ast = rpc("actorStats", {"runnerId": rid}, 40, tolerate=True)
    return load_state(dec, ob, snap, board=Board(bg["tiles"], adjacency="native_sym"), tiles=tm,
                      actor_stats=ast or None)


def attendu_bonus(rid, dec, level, mult) -> int:
    """La valeur EXACTE attendue, FIGEE **avant** toute mutation (etage 7).

    Un `attendu` recalcule par la fonction MUTEE se deplacerait avec elle : c'est exactement
    comme cela qu'un mutant de magnitude passe pour vert."""
    from engine.entities.effects.loki.first_among_traitors import FirstAmongTraitorsExtraDmgEffect
    from engine.runner.components import unit_total_attacks_made
    st = _load_state(rid, dec)
    n = unit_total_attacks_made(st, ids_by_visual(dec)[CARRIER])
    e = FirstAmongTraitorsExtraDmgEffect(EFFECT_NAME)
    e.ability_level, e.ability_variables_multiplier = level, mult
    return int(e._current_damage_bonus(n) or 0)


def etage6(rid, dec, level, mult, bonus=None) -> dict:
    """Canal COMBAT : `attacker_modifiers(...).additive` doit porter la MEME valeur que la
    prediction -- et 0 sur les trois unites que le selecteur natif ecarte.

    `bonus` = la valeur attendue, passee par l'appelant (FIGEE hors mutation)."""
    from engine.runner.components import unit_total_attacks_made
    from engine.runner.damage_model import attacker_modifiers

    st = _load_state(rid, dec)
    by_vis = ids_by_visual(dec)
    n = unit_total_attacks_made(st, by_vis[CARRIER])
    if bonus is None:
        bonus = attendu_bonus(rid, dec, level, mult)
    attendu = {CARRIER: 0, NEAR_CHAOS: bonus, PLAIN: 0, FAR_CHAOS: 0}
    print("[6] port : TotalAttacksMade(Abaddon) seede = %d -> bonus attendu = %d" % (n, bonus))
    rows, ok = {}, True
    for vis in (CARRIER, NEAR_CHAOS, PLAIN, FAR_CHAOS):
        uid = by_vis[vis]
        base, _act = attacker_modifiers(st, uid, None, is_ranged=None,
                                        target_id=by_vis[FOE_NEAR])
        # Le DELTA impute a CETTE aura : on refait le calcul en retirant la classe du registre.
        import engine.entities.effects.factory as F
        saved = F.EFFECT_CLASSES.pop(EFFECT_NAME, None)
        try:
            st2 = _load_state(rid, dec)
            sans, _a2 = attacker_modifiers(st2, uid, None, is_ranged=None,
                                           target_id=by_vis[FOE_NEAR])
        finally:
            if saved is not None:
                F.EFFECT_CLASSES[EFFECT_NAME] = saved
        delta = round(float(base.additive) - float(sans.additive))
        rows[vis] = {"id": uid, "additive": float(base.additive), "delta_1063": delta,
                     "attendu": attendu[vis]}
        same = delta == attendu[vis]
        ok = ok and same
        print("[6] %-17s u%-3d additive=%-9.1f delta impute a 1063 = %-6d attendu=%-6d %s"
              % (vis, uid, base.additive, delta, attendu[vis], "OK" if same else "ECART"))
    return {"ok": ok, "rows": rows, "bonus": bonus, "n": n}


# ------------------------------------------------------------------------- etage 7 : MUTANTS
def etage7(rid, dec, level, mult, bonus) -> dict:
    """Quatre mutations du PORT. Chacune DOIT faire rougir l'etage 6 (valeurs EXACTES).

    `bonus` est FIGE AVANT les mutations : sans cela, le mutant de magnitude deplace l'attendu
    avec lui et passe pour vert -- mesure du 2026-08-11, ce probe s'y est fait prendre.

    Un mutant vert dit que le temoin est aveugle -- c'est ce qu'on refuse."""
    import engine.entities.effects.loki.first_among_traitors as M
    from engine.services.effect_bonus import EffectBonus

    K = M.FirstAmongTraitorsExtraDmgEffect
    orig_bonus = K.create_aura_attack_damage_bonus_for_ally
    orig_range = M.first_among_traitors_range
    orig_cur = K._current_damage_bonus
    out = {}

    def _run(nom):
        try:
            r = etage6(rid, dec, level, mult, bonus=bonus)
        except Exception as exc:                                 # noqa: BLE001
            r = {"ok": False, "err": str(exc)}
        out[nom] = bool(r.get("ok"))
        print("[7] mutant %-28s -> etage6 %s  (%s)"
              % (nom, "VERT" if r.get("ok") else "ROUGE",
                 "AVEUGLE, a corriger" if r.get("ok") else "le temoin MORD"))

    # (a) gate de TRAIT retire -> `ultraTitus` (Imperial) toucherait le bonus
    def sans_trait(self, ctx=None):
        c = dict(ctx or {})
        c["att_traits"] = tuple(c.get("att_traits") or ()) + ("Chaos",)
        return orig_bonus(self, c)
    K.create_aura_attack_damage_bonus_for_ally = sans_trait
    _run("gate TRAIT retire")
    K.create_aura_attack_damage_bonus_for_ally = orig_bonus

    # (b) rayon elargi -> `worldKharn` (dist 4) toucherait le bonus
    M.first_among_traitors_range = lambda: 99
    _run("rayon 2 -> 99")
    M.first_among_traitors_range = orig_range

    # (c) le `op_Addition Owner` que le natif n'a PAS : on DECLARE la patte SELF. Elle ne peut pas
    # se simuler depuis le canal aura -- l'agregateur EXCLUT le porteur de ses propres carriers
    # (`uid == att_id: continue`), donc le seul chemin par lequel le porteur toucherait le bonus est
    # `create_effect_damage_bonus_for_attack`. Un mutant qui n'ajoutait pas cette methode restait
    # VERT sans rien prouver (mesure du 2026-08-11).
    def patte_self(self, is_ranged=None, has_moved=None, target_traits=None, is_prediction=False,
                   is_normal_attack=None, target_armor_reduced=None, att_ctx=None):
        v = orig_cur(self, (att_ctx or {}).get("total_attacks_made_owner"))
        if v is None:                       # pas de compteur threade sur ce canal -> n = 0
            v = orig_cur(self, 0)
        return EffectBonus("Addition", int(v), True) if v else None
    K.create_effect_damage_bonus_for_attack = patte_self
    _run("patte SELF ajoutee")
    del K.create_effect_damage_bonus_for_attack

    # (d) magnitude : +1 sur le montant -- l'attendu, lui, est FIGE
    def plus_un(self, total_attacks_made=None):
        v = orig_cur(self, total_attacks_made)
        return None if v is None else int(v) + 1
    K._current_damage_bonus = plus_un
    _run("magnitude +1")
    K._current_damage_bonus = orig_cur

    aveugles = [k for k, v in out.items() if v]
    print("[7] mutants VERTS (temoin aveugle) : %s" % (aveugles or "aucun"))
    return {"ok": not aveugles, "mutants": out}


# ------------------------------------- etage 8 : le volet « Targetable » du `unitSelectionType`
def etage8_deep_strike(state: Path) -> dict:
    """QUESTION BINAIRE : le natif accorde-t-il le bonus a un ami Chaos NON CIBLABLE ?

    Le selecteur porte `unitSelectionType = 3 = OnlyAliveAndTargetable` sur SES DEUX noeuds. Le
    volet « Targetable » est REEL sur un autre canal du binaire -- mesure live de `LionHelm`
    (`effects/loki/dark_angels_passives.py`) : `darkaTerminator` en `TeleportStrike_TeleportingIn`
    ne recoit AUCUN de ses deux stat-mods. Recopier ce verdict ICI serait un « voisin de forme ».

    Montage : `blackTerminator` (Chaos + `TeleportStrike`) prend la place du beneficiaire, a
    distance 1. Il arrive en bataille avec l'effet 1035 (`UntargetableEffect`), donc le regime est
    exerce par construction -- l'etage 2 le VERIFIE au lieu de l'esperer.

    Second runner : il MUTE le roster, donc il ne peut pas partager celui des autres etages."""
    global NEAR_CHAOS, PLACES, STATE
    sauve = (NEAR_CHAOS, PLACES, STATE)
    NEAR_CHAOS, STATE = "blackTerminator", state
    PLACES = {CARRIER: (3, 3), "blackTerminator": (3, 4), PLAIN: (2, 3), FAR_CHAOS: (0, 0)}
    try:
        rid = build(state)
        dec = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 180)
        r2 = etage2(dec)
        exerce = "TeleportStrike_TeleportingIn" in (r2["rows"][NEAR_CHAOS]["effets"] or ())
        scene, _sc = _scene(rid, dec)
        by_vis = ids_by_visual(dec)
        mult = scene.mult(by_vis[CARRIER]) or 100
        lvl = scene.ablvl_by_id.get(by_vis[CARRIER]) or 50
        bonus = attendu_bonus(rid, dec, lvl, mult)
        e6 = etage6(rid, dec, lvl, mult, bonus=bonus)
        e3 = etage3(rid, dec)
        donne = int(e6["rows"][NEAR_CHAOS]["delta_1063"])
        print("[8] regime EXERCE (l'unite porte bien 1035) : %s" % exerce)
        print("[8] le PORT accorde %d au non-ciblable ; ecarts avec l'oracle NATIF : %d"
              % (donne, len(e3["bad"])))
        print("[8] => le natif %s le bonus a un ami Chaos NON CIBLABLE"
              % ("ACCORDE" if (donne and not e3["bad"]) else "REFUSE (ou ecart)"))
        return {"exerce": exerce, "donne": donne, "bad": e3["bad"], "bonus": bonus,
                "ok": bool(exerce and donne == bonus and not e3["bad"])}
    finally:
        _duel(["dispose", "--state-file", str(state)])
        NEAR_CHAOS, PLACES, STATE = sauve


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", default=None,
                    help="chemin ABSOLU et UNIQUE du state-file du runner")
    ap.add_argument("--offline-only", action="store_true")
    ap.add_argument("--keep", action="store_true", help="ne pas disposer le runner")
    ap.add_argument("--no-mutants", action="store_true")
    a = ap.parse_args()

    global STATE
    if a.state_file:
        STATE = Path(a.state_file)

    etage0()
    e1 = etage1()
    if a.offline_only:
        return 0 if e1["ok"] else 1

    rid = build(STATE)
    print("[montage] runner=%d board=%s seed=%s places=%s / %s"
          % (rid, BOARD, SEED, PLACES, A_PLACES))
    try:
        dec = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 180)
        etage2(dec)
        e3 = etage3(rid, dec)
        scene, _sc = _scene(rid, dec)
        by_vis = ids_by_visual(dec)
        mult = scene.mult(by_vis[CARRIER]) or 100
        lvl = scene.ablvl_by_id.get(by_vis[CARRIER]) or 50
        print("[montage] %s : ability_level=%s multiplier=%s" % (CARRIER, lvl, mult))
        etage1(level=lvl, mult=mult)
        e4 = etage4(rid)
        bonus = attendu_bonus(rid, dec, lvl, mult)      # FIGE avant toute mutation (etage 7)
        e6 = etage6(rid, dec, lvl, mult, bonus=bonus)
        e7 = {"ok": None} if a.no_mutants else etage7(rid, dec, lvl, mult, bonus)
        e5 = etage5(rid, dec)
        _duel(["dispose", "--state-file", str(STATE)])
        e8 = etage8_deep_strike(STATE.with_name(STATE.stem + "-ds.json"))
        ok = ((not e3["bad"]) and (e4.get("status") in (None, "ok", "no-sensor"))
              and e6.get("ok") and (e5.get("ok") is not False) and (e7.get("ok") is not False)
              and e8.get("ok"))
        print("[verdict] etage3=%s etage4=%s etage5=%s etage6=%s etage7=%s etage8=%s -> %s"
              % (not e3["bad"], e4.get("status"), e5.get("ok"), e6.get("ok"), e7.get("ok"),
                 e8.get("ok"), "ACCORD" if ok else "ECART"))
        return 0 if ok else 1
    finally:
        if not a.keep:
            _duel(["dispose", "--state-file", str(STATE)])


if __name__ == "__main__":
    raise SystemExit(main())
