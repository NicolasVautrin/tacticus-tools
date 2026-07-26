#!/usr/bin/env python
"""Probe #204 -- validation live de TerrifyingCrescendo_ExtraDmg (effet 1424, passif d'emperNoiseMarine
<<Shiron>>, EmperorsChildren).

Mecanique RE (decompile = verite, gqfc5mff6c) :
  - effet `IdunBattle.Entities.Effects.Loki.TerrifyingCrescendo_ExtraDmgEffect$$CreateEffectDamageBonusForAttack` =
    ForAddition(IsRangedAttack & OwnerIsCaster, GetCurrentExtraDamage()).
  - `IdunBattle.Entities.Effects.Loki.FuelledByFury_ExtraDamageEffect$$GetCurrentExtraDamage` (herite de FuelledByFury) = Multiply(ConfigVar(8=extraDmg),
    EffectLevel) = extraDmg[ablvl passif] x mult x stack_level. extraDmg[L65]=218 (i2), rarity-scale.
  - accumulation `IdunBattleLogic.Entities.Abilities.Triggered.Loki.TerrifyingCrescendoAbility$$CreateTrigger` = (On overkill & OwnerIsActor & TargetIsOverkilled) |
    (On(0x3e) & OwnerIsActor & TriggeringEffectIs(0x429=1065=Pinned/Suppressed)). +1 stack par
    declenchement, cap buffMaxLevel=6. crescendo dispo dans decisionView.effects[].level.

Setup crafte (drive-positions) : Shiron + 2 fillers vs 3x necroWarden HP GONFLE (personne ne meurt ->
accumulation par SUPPRESS uniquement, +1/round via le trait SuppressiveFire = croissance propre 0->6),
MC1_67. Chaque round Shiron tire en RANGED sur un warden (accumule pour le round suivant).

Datapoints :
  A. CAPTURE : effet TerrifyingCrescendo_ExtraDmg de Shiron + niveau de STACK (croissance 0->6).
  B. PREDICTION per-tuile (canal `ranked` natif) : attaque normale de Shiron -- pour CHAQUE tuile candidate
     (RANGED = bonus inclus ; MELEE adjacente = pas de bonus), natif (dmgMin,dmgMax) vs offline
     make_normal_attack_predictions. Attendu : MATCH partout, a TOUS les niveaux de stack (0..6 inclus).
  C. COMBAT ranged : Shiron tire -> cascade UnitDamaged (6 coups). Le total observe doit tomber dans
     [off_min, off_max] de la tuile de tir (bornes qui INCLUENT l'additif) -> preuve que le COMBAT applique
     bien l'additif (pas seulement la prediction). Baseline L0 = sans additif.

ASCII only (cp1252). Usage: python probe_204_crescendo.py [--seed 20204] [--max-rounds 12]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hexgeo  # noqa: E402
from rl_collect_batch import _resolve_session, _rpc  # noqa: E402
from engine.playbook import scene as SC  # noqa: E402
from engine.playbook.scene import Scene  # noqa: E402
from engine.playbook import prediction  # noqa: E402
from engine.entities.effects.magnitude import ability_var  # noqa: E402

PYDIR = Path(__file__).resolve().parent
# Chemin RELATIF au checkout qui execute ce script (via __file__), jamais absolu :
# un agent en worktree doit ecrire dans SON logs/, sinon son etat atterrit dans l'arbre
# principal et lui SURVIT.
STATE = Path(__file__).resolve().parents[2] / "logs" / "runners" / "agent204-crescendo.json"
NOISE_VIS = "emperNoiseMarine"      # Shiron -- porteur de TerrifyingCrescendo
FILL_VIS = "necroWarden"            # fillers cote joueur (neutres)
ENEMY_VIS = "necroWarden"           # cibles HP-gonfle
EFFECT_NAME = "TerrifyingCrescendo_ExtraDmg"
RNG_HITS, RNG_RANGE, RNG_MOVE = 6, 3, 3
W, H = 7, 9                          # bornes MC1_67


def _r(sid: int, method: str, body: dict, t: float = 90) -> dict:
    return (_rpc(sid, method, [body], timeout=t).get("result") or {})


def build(seed: int) -> int:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.unlink(missing_ok=True)
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
         "--state-file", str(STATE), "--board", "MC1_67",
         "--p-units", f"{NOISE_VIS},{FILL_VIS},{FILL_VIS}",
         "--a-units", f"{ENEMY_VIS},{ENEMY_VIS},{ENEMY_VIS}",
         "--hp-target", "400000", "--hp-player", "400000"],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not STATE.exists():
        print(f"[204] build KO: {(proc.stderr or proc.stdout or '')[-400:]}", file=sys.stderr)
        sys.exit(2)
    return json.loads(STATE.read_text())["runnerId"]


def _units_by_vis(dv: dict) -> dict:
    out = {}
    for u in (dv.get("units") or []):
        if u.get("alive"):
            out.setdefault(u.get("visualId"), []).append(u)
    return out


def _pos(u: dict) -> tuple:
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row"))


def _elev(board, pos) -> int:
    if board is None or pos is None:
        return 0
    for t in board.by_id.values():
        if (t["col"], t["row"]) == tuple(pos):
            return int(t.get("elevation") or 0)
    return 0


def _advance_to_my_turn(rpc, rid, uid_want, max_iter=14):
    """Avance jusqu'au tour du PROPRIETAIRE de l'unite `uid_want` puis renvoie une decisionView riche."""
    for _ in range(max_iter):
        dec = rpc("decisionView", {"runnerId": rid}, 150)
        if not isinstance(dec, dict) or not dec.get("ok"):
            return None, None
        u = next((x for x in (dec.get("units") or [])
                  if x.get("id") == uid_want and x.get("alive")), None)
        if u is None:
            return dec, None
        if dec.get("currentPlayer") == u.get("owner"):
            rich = rpc("decisionView", {"runnerId": rid, "maxRank": 99, "allAbilities": True}, 150)
            if isinstance(rich, dict) and rich.get("ok"):
                u2 = next((x for x in (rich.get("units") or [])
                           if x.get("id") == uid_want and x.get("alive")), None)
                return rich, u2
            return None, None
        rpc("aiPlayTurn", {"runnerId": rid}, 200)
        dec2 = rpc("decisionView", {"runnerId": rid}, 150)
        if isinstance(dec2, dict) and dec2.get("ok") \
                and dec2.get("currentPlayer") != u.get("owner"):
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    return None, None


def _crescendo_level(u: dict):
    """Niveau de stack de l'effet TerrifyingCrescendo_ExtraDmg de l'unite (None = effet absent = L0)."""
    for e in (u.get("effects") or []):
        if e.get("name") == EFFECT_NAME:
            return e.get("level"), e.get("remaining")
    return None, None


def _rows_pred(dec, scene, att_id, pos_by_id) -> list:
    """Datapoint B : confrontation per-tuile natif(ranked) vs offline pour l'attaque NORMALE de `att_id`."""
    rows = []
    norm_ids = {ab.get("id") for u in (dec.get("units") or []) if u.get("id") == att_id
                for ab in (u.get("abilities") or []) if ab.get("kind") == "normal"}
    for ap in (dec.get("attackPlans") or []):
        if ap.get("unitId") != att_id:
            continue
        for ev in (ap.get("evals") or []):
            if norm_ids and ev.get("abilityId") not in norm_ids:
                continue
            tgt_id = ev.get("targetId")
            tgt_pos = pos_by_id.get(tgt_id)
            for rk in (ev.get("ranked") or []):
                if rk.get("dmgMax") is None or rk.get("col") is None:
                    continue
                tile = (rk["col"], rk["row"])
                out = prediction.make_normal_attack_predictions(scene, att_id, tgt_id, tile, meta=True)
                if not out:
                    continue
                res = out[0].prediction.accurate_health_damage
                d_tgt = hexgeo.distance(tile, tuple(tgt_pos)) if tgt_pos else None
                rows.append({"tile": tile, "tgt": tgt_id, "d_tgt": d_tgt,
                             "is_ranged": (d_tgt is not None and d_tgt > 1),
                             "oracle": (rk.get("dmgMin"), rk.get("dmgMax")),
                             "offline": (res.min, res.max),
                             "off_meta": out[1],
                             "match": (rk.get("dmgMin"), rk.get("dmgMax")) == (res.min, res.max)})
    return rows


def _dmg_events(r, tgt_sq=None) -> list:
    import stream_events
    cascade = r.get("cascade") or []
    for a in (r.get("actions") or []):
        cascade = cascade + list(a.get("events") or [])
    an = stream_events.analyze(cascade, [])
    return [d for d in an.get("damage") or []
            if tgt_sq is None or d.get("target") == tgt_sq]


def _apply(rpc, rid, action) -> dict:
    return rpc("applyAction", {"runnerId": rid, "action": action}, 120)


def _move(rpc, rid, unit_id, tile) -> bool:
    r = _apply(rpc, rid, {"kind": "move", "unitId": unit_id,
                          "to": {"col": int(tile[0]), "row": int(tile[1])}})
    a0 = ((r or {}).get("actions") or [{}])[0]
    return bool(a0.get("ok"))


def _attack(rpc, rid, dec, caster_id, tgt_id):
    ability = None
    norm_ids = {ab.get("id") for u in (dec.get("units") or []) if u.get("id") == caster_id
                for ab in (u.get("abilities") or []) if ab.get("kind") == "normal"}
    for p in (dec.get("attackPlans") or []):
        if p.get("unitId") == caster_id:
            for ev in (p.get("evals") or []):
                if ev.get("targetId") == tgt_id and (not norm_ids or ev.get("abilityId") in norm_ids):
                    ability = ev.get("abilityId")
    if ability is None and norm_ids:
        ability = sorted(norm_ids)[0]
    if ability is None:
        return False, []
    r = _apply(rpc, rid, {"kind": "ability", "casterId": caster_id,
                          "targetId": tgt_id, "abilityType": ability})
    a0 = ((r or {}).get("actions") or [{}])[0]
    return bool(a0.get("ok")), _dmg_events(r, tgt_id)


def _free_tiles(dec) -> set:
    occ = {tuple(_pos(u)) for u in (dec.get("units") or []) if u.get("alive")}
    return {(c, r) for c in range(W) for r in range(H)} - occ


def _end_round(rpc, rid, my_owner) -> None:
    for _ in range(4):
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
        dec = rpc("decisionView", {"runnerId": rid}, 90)
        if isinstance(dec, dict) and dec.get("ok") and dec.get("currentPlayer") != my_owner:
            rpc("aiPlayTurn", {"runnerId": rid}, 240)
            return


def _advance_toward(rpc, rid, dec, u, enemies, mv=RNG_MOVE) -> bool:
    """Drive-positions : avance greedy `u` d'au plus `mv` hexes vers l'ennemi le plus proche."""
    upos = _pos(u)
    goal = min((_pos(e) for e in enemies), key=lambda p: hexgeo.distance(upos, p))
    free = _free_tiles(dec)
    cands = [t for t in hexgeo.disk(upos[0], upos[1], mv) if t in free and t != tuple(upos)]
    cands.sort(key=lambda t: hexgeo.distance(t, goal))
    for t in cands[:8]:
        if _move(rpc, rid, u["id"], t):
            u["pos"] = {"col": t[0], "row": t[1]}
            return True
    return False


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=20204)
    ap.add_argument("--max-rounds", type=int, default=12)
    args = ap.parse_args(argv)
    sid = _resolve_session()
    rid = build(args.seed)
    rpc = lambda m, b, t=90: _r(sid, m, b, t)   # noqa: E731
    print(f"[204] seed={args.seed} runner={rid}")
    board = SC.build_board(rpc, rid)

    # noise_id = l'entite de Shiron (resolu au 1er tour)
    noise_id = None
    levels_seen = {}                 # L -> {"B": (match, total), "combat": [(off_min, off_max, obs_total)]}
    b_total, b_match = 0, 0
    combat_by_level = {}
    ref_amt = {}                     # L -> additif offline scaled attendu (extraDmg x mult x L, par coup)
    try:
        for rnd in range(args.max_rounds):
            # resolution de l'entite Shiron
            dec0 = rpc("decisionView", {"runnerId": rid}, 150)
            if not isinstance(dec0, dict) or not dec0.get("ok"):
                print(f"[204] round {rnd}: dec KO -> stop")
                break
            if noise_id is None:
                nu = next((u for u in (dec0.get("units") or [])
                           if u.get("visualId") == NOISE_VIS and u.get("alive")), None)
                if nu is None:
                    print("[204] Shiron introuvable -> stop")
                    break
                noise_id = nu.get("id")

            dec, noise = _advance_to_my_turn(rpc, rid, noise_id)
            if noise is None:
                print(f"[204] round {rnd}: tour de Shiron introuvable -> stop")
                break
            enemies = [u for u in (dec.get("units") or [])
                       if u.get("alive") and u.get("owner") != noise.get("owner")]
            if not enemies:
                break
            npos = _pos(noise)
            L, rem = _crescendo_level(noise)
            Lnum = int(L) if L is not None else 0
            print(f"[204] round {rnd}: Shiron={npos} crescendo_level={L} (=%d) rem=%s" % (Lnum, rem))

            # A/ref : additif offline scaled attendu par coup (extraDmg[ablvl] x mult x L)
            predictor = SC.build_predictor(rpc, rid)
            scene = None
            if predictor is not None:
                sctx = SC.step_context(predictor, dec)
                scene = Scene.from_predictor_sctx(predictor, sctx, None)
                mult = scene.mult_by_id.get(noise_id)
                ablvl = scene.ablvl_by_id.get(noise_id)
                per = ability_var("TerrifyingCrescendo", "extraDmg", ablvl,
                                  multiplier_pct=mult) if ablvl else None
                ref_amt[Lnum] = (per * Lnum) if per else 0
                print(f"  [ref] ablvl={ablvl} mult={mult} extraDmg[ablvl]={per}"
                      f" -> additif/coup L{Lnum} = {ref_amt[Lnum]}")

            # B : prediction per-tuile natif vs offline (AVANT de tirer ce round)
            if scene is not None:
                pos_by_id = {u.get("id"): _pos(u) for u in (dec.get("units") or []) if u.get("alive")}
                rows = _rows_pred(dec, scene, noise_id, pos_by_id)
                mt = sum(int(x["match"]) for x in rows)
                b_total += len(rows)
                b_match += mt
                levels_seen.setdefault(Lnum, [0, 0])
                levels_seen[Lnum][0] += mt
                levels_seen[Lnum][1] += len(rows)
                mism = [x for x in rows if not x["match"]]
                print(f"  [B L{Lnum}] {mt}/{len(rows)} match"
                      f" (ranged={sum(1 for x in rows if x['is_ranged'])},"
                      f" melee={sum(1 for x in rows if not x['is_ranged'])})")
                for x in mism[:4]:
                    print(f"    [MISMATCH] tile={x['tile']} d_tgt={x['d_tgt']}"
                          f" ranged={x['is_ranged']} nat={x['oracle']} off={x['offline']}")

            # C : combat -- Shiron tire en RANGED (tuile plate, dist 2-3 d'un warden), observe la cascade,
            #     accumule +1 pour le round suivant
            free = _free_tiles(dec)
            cands = [t for t in free
                     if hexgeo.distance(t, npos) <= RNG_MOVE
                     and any(2 <= hexgeo.distance(t, _pos(u)) <= RNG_RANGE for u in enemies)]
            cands.sort(key=lambda t: _elev(board, t) != 0)   # tuile PLATE d'abord (pas de x1.5 elevation)
            fired = False
            if cands:
                t = cands[0]
                tgt = min((u for u in enemies if 2 <= hexgeo.distance(t, _pos(u)) <= RNG_RANGE),
                          key=lambda u: hexgeo.distance(t, _pos(u)))
                # off prediction (min,max) de CETTE tuile pour comparer au combat observe
                off_rng = None
                if scene is not None:
                    o = prediction.make_normal_attack_predictions(scene, noise_id, tgt["id"], t)
                    if o:
                        r = o.prediction.accurate_health_damage
                        off_rng = (r.min, r.max)
                if _move(rpc, rid, noise_id, t):
                    ok, evs = _attack(rpc, rid, dec, noise_id, tgt["id"])
                    if ok and evs:
                        fired = True
                        amounts = [d.get("amount") for d in evs]
                        obs_total = sum(a or 0 for a in amounts)
                        crits = [bool(d.get("crit")) for d in evs]
                        in_rng = (off_rng is not None and off_rng[0] <= obs_total <= off_rng[1])
                        combat_by_level.setdefault(Lnum, []).append((off_rng, obs_total, in_rng))
                        print(f"  [C L{Lnum}] tile={t} elev={_elev(board, t)} tgt={tgt['id']}"
                              f" coups={len(evs)} obs_total={obs_total} off_rng={off_rng}"
                              f" in_range={in_rng} crits={sum(crits)}")

            # pas de tir possible ce round -> avance Shiron vers le front (drive-positions)
            if not fired:
                if _advance_toward(rpc, rid, dec, noise, enemies):
                    print(f"  [adv] Shiron -> {_pos(noise)} (rapprochement, pas de tir ce round)")

            _end_round(rpc, rid, noise.get("owner"))
            # arret : on a vu la croissance jusqu'au cap (>=2 niveaux >0 + cap 6 atteint)
            if Lnum >= 6:
                break

        print("\n[204] ===== SYNTHESE =====")
        print(f"  B prediction global : {b_match}/{b_total} match")
        for L in sorted(levels_seen):
            m, tot = levels_seen[L]
            print(f"    L{L}: {m}/{tot} match ; additif/coup attendu={ref_amt.get(L)}")
        print("  C combat (total observe dans la plage offline predite, additif inclus) :")
        c_ok, c_tot = 0, 0
        for L in sorted(combat_by_level):
            for off_rng, obs, inr in combat_by_level[L]:
                c_tot += 1
                c_ok += int(bool(inr))
            outs = combat_by_level[L]
            print(f"    L{L}: {[ (o[0], o[1], o[2]) for o in outs ]}")
        b_ok = (b_total > 0 and b_match == b_total)
        saw_growth = len([L for L in levels_seen if L > 0]) >= 2
        print(f"  VERDICT prediction: {'PASS' if b_ok else 'FAIL'}"
              f" (B {b_match}/{b_total}) ; combat_in_range {c_ok}/{c_tot} ;"
              f" stack_growth_seen={sorted(levels_seen)} {'OK' if saw_growth else 'INSUFFISANT'}")
        return 0 if b_ok else 1
    finally:
        _rpc(sid, "disposeRunner", {"runnerId": rid}, timeout=20)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
