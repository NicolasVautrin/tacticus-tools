#!/usr/bin/env python
"""Probe #202-B — validation live d'InfernalPacts (effet-aura 1198, canal #179).

Setup crafte (case-202 §5-B) : Abraxas (thousInfernalMaster, porteur du passif InfernalPacts)
+ Shiron (emperNoiseMarine : Chaos ranged NON-Daemon, 6 coups r3) + Azkor (worldEightbound :
Chaos Daemon melee, 2 coups) vs 3x necroWarden, HP gonfles (personne ne meurt), MC1_67.

Datapoints :
  A. CAPTURE : effets d'Abraxas au decisionView -> nom exact + niveaux du 1198 (cle factory).
  B. PREDICTION per-tuile (canal `ranked` natif = oracle par position candidate) : attaque
     normale de Shiron vs warden — pour CHAQUE tuile candidate, natif (dmgMin,dmgMax) vs
     offline make_normal_attack_predictions. Attendu : match sur les DEUX familles de tuiles
     (adjacentes a Abraxas = bonus inclus ; non-adjacentes = sans bonus). Un match adj-only
     ou nonadj-only localise la face fautive.
  C. COMBAT ranged : Shiron ADJACENT a Abraxas attaque -> cascade UnitDamaged = 6 coups
     d'arme + 1 coup bonus (7 events) ; montants et Effect_Type imprimes. CONTROLE :
     attaque NON-adjacente -> 6 events.
  D. COMBAT melee Daemon : Azkor adjacent a Abraxas ET a un warden -> 2 + 1 = 3 events.

ASCII only (cp1252). Usage: python probe_202b_infernal.py [--seed 20202] [--max-rounds 10]
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

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
STATE = ROOT / "logs" / "runners" / "_202b_infernal_state.json"
ABX_VIS = "thousInfernalMaster"     # porteur de l'aura
# Toth : le Chaos ranged lineup le plus PROPRE (pas de passif auto-empilant — emperNoiseMarine
# ecarte : TerrifyingCrescendo (1424, non porte) stacke a chaque round et pollue tout post-combat).
# Confond residuel controle : son WeaverOfFate ne trippe qu'a >=3 ennemis Psychic-touches/tour —
# on attaque la MEME cible chaque round (1 seul ennemi Psychic'd par le bonus InfernalPacts).
RNG_VIS = "thousTerminator"         # Chaos ranged NON-Daemon (5 coups Flame r2, move 2)
RNG_HITS, RNG_RANGE, RNG_MOVE = 5, 2, 2
DMN_VIS = "worldEightbound"         # Chaos Daemon melee (2 coups)
EFFECT_NAME = "InfernalPacts_AdditionalHits"
W, H = 7, 9                          # bornes MC1_67


def _r(sid: int, method: str, body: dict, t: float = 90) -> dict:
    return (_rpc(sid, method, [body], timeout=t).get("result") or {})


def build(seed: int) -> int:
    STATE.unlink(missing_ok=True)
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
         "--state-file", str(STATE), "--board", "MC1_67",
         "--p-units", f"{ABX_VIS},{RNG_VIS},{DMN_VIS}",
         "--a-units", "necroWarden,necroWarden,necroWarden",
         "--hp-target", "300000", "--hp-player", "300000"],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not STATE.exists():
        print(f"[202b] build KO: {(proc.stderr or proc.stdout or '')[-400:]}", file=sys.stderr)
        sys.exit(2)
    return json.loads(STATE.read_text())["runnerId"]


def _units_by_vis(dv: dict) -> dict:
    return {u.get("visualId"): u for u in (dv.get("units") or []) if u.get("alive")}


def _elev(board, pos) -> int:
    if board is None or pos is None:
        return 0
    for t in board.by_id.values():
        if (t["col"], t["row"]) == tuple(pos):
            return int(t.get("elevation") or 0)
    return 0


def _pos(u: dict) -> tuple:
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row"))


def _advance_to_my_turn(rpc, rid, vis, max_iter=12):
    """Avance au tour du proprietaire de `vis` (copie probe_61bis) puis re-fetch riche."""
    for _ in range(max_iter):
        dec = rpc("decisionView", {"runnerId": rid}, 150)
        if not isinstance(dec, dict) or not dec.get("ok"):
            return None, None
        u = next((x for x in (dec.get("units") or [])
                  if x.get("visualId") == vis and x.get("alive")), None)
        if u is None:
            return dec, None
        if dec.get("currentPlayer") == u.get("owner"):
            rich = rpc("decisionView", {"runnerId": rid, "maxRank": 99,
                                        "allAbilities": True}, 150)
            if isinstance(rich, dict) and rich.get("ok"):
                u2 = next((x for x in (rich.get("units") or [])
                           if x.get("visualId") == vis and x.get("alive")), None)
                return rich, u2
            return None, None
        rpc("aiPlayTurn", {"runnerId": rid}, 180)
        dec2 = rpc("decisionView", {"runnerId": rid}, 150)
        if isinstance(dec2, dict) and dec2.get("ok") \
                and dec2.get("currentPlayer") != u.get("owner"):
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    return None, None


def _rows_pred(dec, scene, att_id, abx_pos, pos_by_id) -> list:
    """Datapoint B : confrontation per-tuile natif(ranked) vs offline pour l'attaque NORMALE
    de `att_id` — TOUTES les cibles evaluees par le plan natif."""
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
                out = prediction.make_normal_attack_predictions(scene, att_id, tgt_id, tile,
                                                                meta=True)
                if not out:
                    continue
                res = out[0].prediction.accurate_health_damage
                adj = hexgeo.distance(tile, tuple(abx_pos)) == 1
                rows.append({"tile": tile, "adj_abx": adj, "tgt": tgt_id,
                             "d_tgt": (hexgeo.distance(tile, tuple(tgt_pos))
                                       if tgt_pos else None),
                             "oracle": (rk.get("dmgMin"), rk.get("dmgMax")),
                             "offline": (res.min, res.max),
                             "match": (rk.get("dmgMin"), rk.get("dmgMax")) == (res.min, res.max)})
    return rows


def _dmg_events(r, tgt_sq=None) -> list:
    """Extrait les UnitDamaged de la cascade d'un applyAction ({target, amount, effect_type})."""
    import stream_events
    cascade = r.get("cascade") or []
    for a in (r.get("actions") or []):
        cascade = cascade + list(a.get("events") or [])
    an = stream_events.analyze(cascade, [])
    out = [d for d in an.get("damage") or []
           if tgt_sq is None or d.get("target") == tgt_sq]
    return out


def _apply(rpc, rid, action) -> dict:
    return rpc("applyAction", {"runnerId": rid, "action": action}, 120)


def _move(rpc, rid, unit_id, tile) -> bool:
    r = _apply(rpc, rid, {"kind": "move", "unitId": unit_id,
                          "to": {"col": int(tile[0]), "row": int(tile[1])}})
    a0 = ((r or {}).get("actions") or [{}])[0]
    return bool(a0.get("ok"))


def _attack(rpc, rid, dec, caster_id, tgt_id):
    """Attaque NORMALE caster->tgt (abilityId auto-resolu depuis le plan). -> (ok, events)."""
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


def _advance_unit(rpc, rid, dec, u, enemies, toward=None) -> None:
    """Avance greedy `u` d'au plus 3 hexes vers `toward` (ou l'ennemi le plus proche)."""
    upos = _pos(u)
    goal = tuple(toward) if toward is not None \
        else min((_pos(e) for e in enemies), key=lambda p: hexgeo.distance(upos, p))
    free = _free_tiles(dec)
    cands = [t for t in hexgeo.disk(upos[0], upos[1], 3)
             if t in free and t != tuple(upos)]
    cands.sort(key=lambda t: hexgeo.distance(t, goal))
    for t in cands[:6]:
        if _move(rpc, rid, u["id"], t):
            u["pos"] = {"col": t[0], "row": t[1]}
            return


def _end_round(rpc, rid, my_owner) -> None:
    """Fin de MON tour + tour ENNEMI complet — mirror garde-fou cmd_aiturn (H19 : le endturn
    ne flippe pas toujours -> re-endturn jusqu'au flip AVANT aiPlayTurn, sinon l'IA jouerait
    MA team)."""
    for _ in range(4):
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
        dec = rpc("decisionView", {"runnerId": rid}, 90)
        if isinstance(dec, dict) and dec.get("ok") and dec.get("currentPlayer") != my_owner:
            rpc("aiPlayTurn", {"runnerId": rid}, 240)
            return


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=20202)
    ap.add_argument("--max-rounds", type=int, default=10)
    args = ap.parse_args(argv)
    sid = _resolve_session()
    rid = build(args.seed)
    rpc = lambda m, b, t=90: _r(sid, m, b, t)   # noqa: E731
    print(f"[202b] seed={args.seed} runner={rid}")
    board = SC.build_board(rpc, rid)

    done = {"A": False, "C_adj": None, "C_ctrl": None, "D_adj": None, "B_adj": 0,
            "B_adj_match": 0, "B_non": 0, "B_non_match": 0, "combat_started": False,
            "bonus_draws": []}
    try:
        for rnd in range(args.max_rounds):
            dec, abx = _advance_to_my_turn(rpc, rid, ABX_VIS)
            if abx is None:
                print(f"[202b] round {rnd}: Abraxas introuvable / dec KO -> stop")
                break
            byvis = _units_by_vis(dec)
            noise, azkor = byvis.get(RNG_VIS), byvis.get(DMN_VIS)
            enemies = [u for u in (dec.get("units") or [])
                       if u.get("alive") and u.get("owner") != abx.get("owner")]
            if not enemies:
                break
            apos = _pos(abx)
            _npos = _pos(noise) if noise is not None else None
            _zpos = _pos(azkor) if azkor is not None else None
            _dmin = min(hexgeo.distance(_npos, _pos(u)) for u in enemies) \
                if (_npos and enemies) else None
            _nplans = sum(1 for p in (dec.get("attackPlans") or [])
                          if noise is not None and p.get("unitId") == noise["id"])
            print(f"[202b] round {rnd}: abx={apos} noise={_npos} azkor={_zpos}"
                  f" d(noise,enemy)={_dmin} plans_noise={_nplans}")

            # A. capture des effets d'Abraxas (cle factory + niveaux)
            if not done["A"]:
                effs = [(e.get("name"), e.get("effectType"), e.get("level"),
                         e.get("remaining")) for e in (abx.get("effects") or [])]
                print(f"[202b] A effets Abraxas: {effs}")
                names = [e[0] for e in effs]
                print(f"[202b] A verdict: {EFFECT_NAME} "
                      f"{'PRESENT' if EFFECT_NAME in names else 'ABSENT (nom a reconcilier!)'}")
                done["A"] = True

            # effets courants de Shiron (diagnostic pollution post-combat, ex. Thrilled)
            if noise is not None and done["combat_started"]:
                print(f"  [fx noise] {[(e.get('name'), e.get('level')) for e in (noise.get('effects') or [])]}")

            # B. prediction per-tuile — UNIQUEMENT avant tout combat (le combat pose des
            # effets non-portes, ex. ThrillSeekers, qui polluent la confrontation)
            if noise is not None and not done["combat_started"]:
                pos_by_id = {u.get("id"): _pos(u) for u in (dec.get("units") or [])
                             if u.get("alive")}
                predictor = SC.build_predictor(rpc, rid)
                if predictor is not None:
                    sctx = SC.step_context(predictor, dec)
                    scene = Scene.from_predictor_sctx(predictor, sctx, None)
                    rows = _rows_pred(dec, scene, noise["id"], apos, pos_by_id)
                    # + rows du DAEMON melee (Azkor) : la branche Daemon de la face prediction
                    if azkor is not None:
                        rows += _rows_pred(dec, scene, azkor["id"], apos, pos_by_id)
                    for x in rows:
                        fam = "ADJ" if x["adj_abx"] else "non"
                        done[f"B_{'adj' if x['adj_abx'] else 'non'}"] += 1
                        done[f"B_{'adj' if x['adj_abx'] else 'non'}_match"] += int(x["match"])
                        print(f"  [B {fam}] tile={x['tile']} elev={_elev(board, x['tile'])}"
                              f" tgt={x['tgt']} d_tgt={x['d_tgt']}"
                              f" nat={x['oracle']} off={x['offline']}"
                              f" {'MATCH' if x['match'] else 'MISMATCH'}")
                    # oracle per-tuile natif (healthDmg + appliedHits) sur les tuiles ADJ :
                    # appliedHits dit si le natif COMPTE le coup bonus dans les hits affiches
                    for x in [r for r in rows if r["adj_abx"]][:2]:
                        nid = next((ab.get("id") for u in (dec.get("units") or [])
                                    if u.get("id") == noise["id"]
                                    for ab in (u.get("abilities") or [])
                                    if ab.get("kind") == "normal"), None)
                        if nid is None:
                            break
                        pb = rpc("aiPlaybookPredict",
                                 {"runnerId": rid, "unitId": noise["id"], "targetId": x["tgt"],
                                  "abilityType": nid, "col": int(x["tile"][0]),
                                  "row": int(x["tile"][1])}, 60)
                        if isinstance(pb, dict) and pb.get("ok"):
                            for e in (pb.get("events") or []):
                                print(f"  [pb ADJ] tile={x['tile']} tgt_ev={e.get('targetId')}"
                                      f" nat=({e.get('healthDmgMin')},{e.get('healthDmgMax')})"
                                      f" hits={e.get('appliedHits')}")

            acted = False

            # reference : bornes InfernalPacts scaled telles que NOTRE scene les materialise
            if noise is not None and done["C_adj"] is None:
                try:
                    from engine.entities.effects.magnitude import ability_var
                    predictor2 = SC.build_predictor(rpc, rid)
                    sctx2 = SC.step_context(predictor2, dec)
                    scene2 = Scene.from_predictor_sctx(predictor2, sctx2, None)
                    for e in scene2.effects(abx["id"]) or []:
                        if getattr(e, "name", None) == EFFECT_NAME:
                            lvl = e.ability_level if e.ability_level is not None else e.level
                            mult = e.ability_variables_multiplier
                            mn = ability_var("InfernalPacts", "minDmg", lvl, multiplier_pct=mult)
                            mx = ability_var("InfernalPacts", "maxDmg", lvl, multiplier_pct=mult)
                            print(f"  [ref] effet scene: ablvl={lvl} mult={mult}"
                                  f" -> scaled(min,max)=({mn},{mx}) avg={(mn + mx) / 2 if mn and mx else None}")
                except Exception as ex:
                    print(f"  [ref] KO: {ex}")

            # C. combat ranged : adjacent (1er = comptage), controle non-adjacent, puis
            # re-echantillonnage adjacent chaque round (distribution du tirage bonus)
            if noise is not None:
                npos = _pos(noise)
                free = _free_tiles(dec)
                want_adj = done["C_adj"] is None or done["C_ctrl"] is not None
                cands = [t for t in free
                         if (hexgeo.distance(t, apos) == 1 if want_adj
                             else hexgeo.distance(t, apos) >= 2)
                         and hexgeo.distance(t, npos) <= RNG_MOVE
                         and any(1 <= hexgeo.distance(t, _pos(u)) <= RNG_RANGE
                                 for u in enemies)]
                cands.sort(key=lambda t: _elev(board, t) != 0)   # tuile PLATE d'abord (pas de x1.5)
                if cands:
                    t = cands[0]
                    tgt = min(enemies, key=lambda u: hexgeo.distance(t, _pos(u)))
                    if _move(rpc, rid, noise["id"], t):
                        ok, evs = _attack(rpc, rid, dec, noise["id"], tgt["id"])
                        if ok and evs:
                            done["combat_started"] = True
                            acted = True
                            amounts = [d.get("amount") for d in evs]
                            if want_adj:
                                tag = "C ADJ" if done["C_adj"] is None else "C adj+"
                                print(f"  [{tag}] tile={t} elev={_elev(board, t)} tgt={tgt['id']}"
                                      f" coups={len(evs)} ({RNG_HITS}+1 attendus)"
                                      f" amounts={amounts}"
                                      f" crits={[bool(d.get('crit')) for d in evs]}")
                                if done["C_adj"] is None:
                                    done["C_adj"] = len(evs)
                                if (len(evs) == RNG_HITS + 1
                                        and not any(d.get("crit") for d in evs)
                                        and _elev(board, t) == 0):
                                    done["bonus_draws"].append(amounts[-1])
                            else:
                                print(f"  [C ctl] tile={t} elev={_elev(board, t)} (d_abx>=2)"
                                      f" tgt={tgt['id']} coups={len(evs)}"
                                      f" amounts={amounts} ({RNG_HITS} attendus)")
                                done["C_ctrl"] = len(evs)

            # D. combat melee Daemon : Azkor adjacent a Abraxas ET a un warden
            if azkor is not None and done["D_adj"] is None:
                zpos = _pos(azkor)
                free = _free_tiles(dec)
                cands = [t for t in free
                         if hexgeo.distance(t, apos) == 1
                         and hexgeo.distance(t, zpos) <= 3
                         and any(hexgeo.distance(t, _pos(u)) == 1 for u in enemies)]
                if cands:
                    t = cands[0]
                    tgt = next(u for u in enemies if hexgeo.distance(t, _pos(u)) == 1)
                    if _move(rpc, rid, azkor["id"], t):
                        ok, evs = _attack(rpc, rid, dec, azkor["id"], tgt["id"])
                        if ok:
                            done["combat_started"] = True
                            acted = True
                            print(f"  [D ADJ melee Daemon] tile={t} tgt={tgt['id']}"
                                  f" coups={len(evs)} (2 arme + 1 bonus attendus = 3)")
                            for d in evs:
                                print(f"      amount={d.get('amount')} crit={d.get('crit')}"
                                      f" effect_type={d.get('effect_type')}")
                            done["D_adj"] = len(evs)

            # aucune action de datapoint ce round -> toute la bande avance vers le front
            # (drive-positions : on CREE la configuration au lieu d'attendre la geometrie)
            if not acted:
                _advance_unit(rpc, rid, dec, abx, enemies)
                if noise is not None:
                    _advance_unit(rpc, rid, dec, noise, enemies, toward=_pos(abx))
                if azkor is not None:
                    _advance_unit(rpc, rid, dec, azkor, enemies, toward=_pos(abx))

            _end_round(rpc, rid, abx.get("owner"))
            if (done["C_adj"] is not None and done["C_ctrl"] is not None
                    and done["D_adj"] is not None and len(done["bonus_draws"]) >= 5):
                break

        print("\n[202b] ===== SYNTHESE =====")
        print(f"  B prediction : ADJ {done['B_adj_match']}/{done['B_adj']} match ;"
              f" non-adj {done['B_non_match']}/{done['B_non']} match")
        print(f"  C combat ranged ADJ : {done['C_adj']} coups (attendu {RNG_HITS + 1})")
        print(f"  C controle non-adj  : {done['C_ctrl']} coups (attendu {RNG_HITS})")
        print(f"  D combat melee Daemon ADJ : {done['D_adj']} coups (attendu 3)")
        bd = done["bonus_draws"]
        if bd:
            print(f"  tirages bonus (no-crit, n={len(bd)}) : min={min(bd)} max={max(bd)} {bd}")
        ok = (done["B_adj"] > 0 and done["B_adj_match"] == done["B_adj"]
              and done["B_non_match"] == done["B_non"]
              and done["C_adj"] == RNG_HITS + 1 and done["C_ctrl"] == RNG_HITS)
        print(f"  VERDICT: {'PASS' if ok else 'A ANALYSER'}"
              f" (D={'PASS' if done['D_adj'] == 3 else done['D_adj']})")
        return 0
    finally:
        _rpc(sid, "disposeRunner", {"runnerId": rid}, timeout=20)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
