"""Harnais de validation DEV — modèle ISO-AI `engine/predict.py` vs ORACLE live.

> Le prédicteur est 100% offline : il consomme `combatSnapshot.normalAttack` (dégât de base
> d'arme, capturé one-shot au déploiement) ; l'oracle live (`decisionView`/`aiPredict`) ne sert
> QU'À valider (dev-only). cf. engine/predict.py PARTIE 1.

Procédure (déterministe, l'oracle = moi) : build runner frais → combatSnapshot (capture base
par unité, à froid) → avancer nos unités au contact (`applyAction move`) → pour chaque plan
d'attaque NORMALE à portée, comparer `predict_normal_attack(base, hp_cible)` à l'oracle
`decisionView` (dmgMin/dmgMax). Match attendu pour les cibles SANS réduction (non-predOptimistic).

Usage : python predict_validate.py [--seed 777] [--max-turns 6]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import rl_collect_batch as R
import gameconfig as GC
from engine.entities import UnitContext
from engine.entities.abilities import NormalAttackAbility
from engine.services.damage_calculations import spread_to_min_max
from engine.services.damage_prediction import get_attack_prediction
from engine.entities import EffectsState
from engine.entities.effects import build_attacker_modifiers_from_effects, hits_bonus_from_effects
from engine.entities.traits import attacker_bonus_hits

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / "data" / "duel_state.json"


def _res(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def rpc(sid, method, body=None, timeout=60):
    return _res(R._rpc(sid, method, [body] if body is not None else [], timeout=timeout))


def _cheby(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def _normal_weapon_pierce(ctx, dist=None):
    """Arme de l'attaque normale + son pierceRatio (`ALoki_NormalAttackAbility.FindAttackWeapon`
    @1811aeb80 → DamageProfile@0x10 → `GetAttackPiercingDamageRatio` @181030a20).

    **Sélection mêlée/ranged FIDÈLE (catch user) :** FindAttackWeapon choisit l'arme par
    PORTÉE/atteignabilité de la cible (pas la 1re à hits-tie). Règle portée standard : cible
    **adjacente (dist≤1)** → arme **mêlée** ; sinon (à distance) → arme **ranged** (le tir). Fallback :
    ranged si dispo, sinon mêlée/1re. (Vérifié value-dump u90→u86 dist>1 = Projectile pierce 15, PAS
    Chain 20.) `dist=None` (position d'attaque inconnue) → on suppose le tir si une arme ranged existe.
    pierce = profile.PiercingRatio (gameconfig) + ExtraPierce(26) + ExtraPierce{Melee21|Ranged22}, clamp 0..100."""
    gu = GC.unit(ctx.visual_id or "") or {}
    weapons = gu.get("weapons") or []
    if not weapons:
        return 100, False, 1
    melee = [w for w in weapons if not w.get("Range")]
    ranged = [w for w in weapons if w.get("Range")]
    adjacent = dist is not None and dist <= 1
    if adjacent and melee:
        cand = melee
    elif ranged:
        cand = ranged          # à distance (ou position inconnue) → tir si arme ranged dispo
    else:
        cand = melee or weapons
    # parmi les candidats (même type d'arme), celui dont hits == normal_hits capté, sinon le 1er.
    w = next((x for x in cand if int(x.get("hits") or 0) == ctx.normal_hits), cand[0])
    dp = GC.damage_profile(w.get("DamageProfile")) or {}
    prof_ratio = int(dp.get("PiercingRatio") or 0)
    is_ranged = bool(w.get("Range"))
    dir_pierce = ctx.extra_pierce_ranged if is_ranged else ctx.extra_pierce_melee
    pierce = max(0, min(100, prof_ratio + ctx.extra_pierce + dir_pierce))
    whits = int(w.get("hits") or 1)
    return pierce, is_ranged, whits


def _drive_into_range(sid, rid, my_team, max_turns):
    """Avance nos unités vers l'ennemi le plus proche jusqu'à un plan d'attaque à portée."""
    amine = 3 if my_team == 1 else 4

    def dec():
        return rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 3, "allAbilities": True}, 90)

    def populated(d):
        return [ap for ap in (d.get("attackPlans") or [])
                if any((e.get("ranked") or []) and e["ranked"][0].get("dmgMax") is not None
                       for e in (ap.get("evals") or []))]

    for t in range(max_turns):
        d = dec()
        if d.get("stageName") != "Running":
            print(f"  [drive] stage={d.get('stageName')} — stop"); return d
        if d.get("currentPlayer") != amine:
            rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 30); d = dec()
        # continuer jusqu'à ce que >=3 attaquants soient à portée (couverture multi-unités)
        if len(populated(d)) >= 3:
            print(f"  [drive] {len(populated(d))} attaquants à portée (tour {t})"); return d
        enemies = [(u["id"], (u["pos"]["col"], u["pos"]["row"]))
                   for u in (d.get("units") or [])
                   if u.get("alive") and u.get("team") != my_team and u.get("pos")]
        mov = rpc(sid, "aiMovableTiles", {"runnerId": rid}, 60)
        moved = 0
        for mu in (mov.get("units") or []):
            up = mu.get("pos") or {}
            if up.get("col") is None or not enemies:
                continue
            tiles = [(tt["col"], tt["row"]) for tt in (mu.get("tiles") or [])
                     if tt.get("col") is not None]
            if not tiles:
                continue
            cur = (up["col"], up["row"])
            best = min(tiles, key=lambda c: min(_cheby(c, e[1]) for e in enemies))
            if min(_cheby(best, e[1]) for e in enemies) < min(_cheby(cur, e[1]) for e in enemies):
                rpc(sid, "applyAction", {"runnerId": rid, "action": {
                    "kind": "move", "unitId": mu["unitId"],
                    "to": {"col": best[0], "row": best[1]}}}, 30)
                moved += 1
        rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 30)
        print(f"  [drive] tour {t}: {moved} avancée(s)")
    return dec()


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--max-turns", type=int, default=6)
    a = ap.parse_args(argv)

    sid = R._resolve_session()
    print(f"[validate] session {sid} — build seed {a.seed}")
    subprocess.run([sys.executable, "rl_duel.py", "build", "--seed", str(a.seed)],
                   capture_output=True, text=True, encoding="utf-8", errors="replace")
    st = json.loads(STATE.read_text())
    rid = st["runnerId"]; my_team = st.get("myTeam", 1)

    # 1) capture one-shot (cold) → UnitContext par unité (stats résolues + dégât d'arme capté
    #    + gameconfig-units pour traits/damageType/range). C'est la SEULE lecture live.
    snap = rpc(sid, "combatSnapshot", {"runnerId": rid}, 40)
    if not snap.get("ok"):
        print(f"[validate] combatSnapshot KO: {snap.get('error')}"); return 1
    # entityId -> visualId via decisionView (combatSnapshot ne donne pas le visualId)
    dv0 = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1}, 60)
    vis_by_id = {u["id"]: u.get("visualId") for u in (dv0.get("units") or [])}
    ctx_by_id = {}
    for u in (snap.get("units") or []):
        eid = u["entityId"]
        u["visualId"] = vis_by_id.get(eid)
        ctx = UnitContext.from_snapshot(u, GC.unit(vis_by_id.get(eid) or ""))
        if not (u.get("normalAttack") or {}).get("error"):
            ctx_by_id[eid] = ctx
    print(f"[validate] UnitContext (cold): {len(ctx_by_id)}/{len(snap.get('units') or [])} unités")

    # 2) avancer au contact pour obtenir des plans d'attaque (oracle live).
    dec = _drive_into_range(sid, rid, my_team, a.max_turns)
    hp_by_id = {u["id"]: u.get("hp") for u in (dec.get("units") or [])}
    armor_by_id = {u["entityId"]: int((u.get("stats") or {}).get("fixedArmor") or 0)
                   for u in (snap.get("units") or [])}
    # effets ACTIFS : MATÉRIALISÉS offline (seed one-shot + évolution, §17.13). Ici on seede depuis le
    # decisionView (oracle ; la capture one-shot via combatSnapshot.effects = extension à venir), puis
    # on interroge l'ensemble actif par attaquant (is_active/consumed/expired sur les classes d'effet).
    effects_by_id = {u["id"]: (u.get("effects") or []) for u in (dec.get("units") or [])}
    # AbilityVariablesMultiplierPercentage + niveau d'ability PAR ENTITÉ (§17.24) : capté LIVE via
    # combatSnapshot.units[].unitConfig (BattleQuery.GetUnitConfig → UnitConfiguration). PassiveAbilityLevel
    # indexe les variables[level] d'ability (≠ stack level capté). Fallback BC offline si vieux hook.
    mult_by_id, ablvl_by_id = {}, {}
    for u in (snap.get("units") or []):
        uc = u.get("unitConfig") or {}
        if isinstance(uc, dict) and uc.get("abilityVariablesMultiplier") is not None:
            mult_by_id[u["entityId"]] = int(uc["abilityVariablesMultiplier"])
            if uc.get("passiveAbilityLevel"):
                ablvl_by_id[u["entityId"]] = int(uc["passiveAbilityLevel"])
    if not mult_by_id:            # fallback : hook sans unitConfig → BC par visualId (duel mirror)
        bc = st.get("bc") or {}
        mult_by_vis = {x.get("VisualId"): int(x.get("AbilityVariablesMultiplierPercentage") or 100)
                       for x in (bc.get("Units") or [])}
        ablvl_by_vis = {x.get("VisualId"): int(x.get("PassiveAbilityLevel") or x.get("Level") or 0)
                        for x in (bc.get("Units") or [])}
        mult_by_id = {eid: mult_by_vis.get(vis_by_id.get(eid), 100) for eid in ctx_by_id}
        ablvl_by_id = {eid: ablvl_by_vis.get(vis_by_id.get(eid)) for eid in ctx_by_id}
    eff_state = EffectsState.seed(effects_by_id, mult_by_id, ablvl_by_id)

    # positions/teams/factions (GetStuckIn §17.21 : portée ≤2 + comptes d'adjacence à la CIBLE).
    units = dec.get("units") or []
    pos_by_id = {u["id"]: (u["pos"]["col"], u["pos"]["row"]) for u in units if u.get("pos")}
    team_by_id = {u["id"]: u.get("team") for u in units}
    _u_by_id = {u.get("id"): u for u in units}

    def _faction(uid):
        v = vis_by_id.get(uid)
        return (GC.unit(v) or {}).get("FactionId") if v else None

    def _getstuckin_bonus(att_ctx, a_id, t_id, base_hits, attack_pos):
        """+floor(base_hits/2) si GetStuckIn. La prédiction est ANCRÉE à la **position d'attaque**
        (`ranked[col,row]`, post-move) — c'est elle qui fixe mêlée/ranged ET la distance. within range 2 =
        cheby(attack_pos, cible)≤2 ; comptes d'adjacence (≥2 orks OU ≥4 amis) = unités adjacentes à la CIBLE
        (le caster post-move y est compté s'il devient adjacent). MinDistance natif = pathfinding ; cheby = proxy."""
        traits = att_ctx.trait_objects()
        if not any(type(t).__name__ == "GetStuckInTrait" for t in traits):
            return 0
        tpos = pos_by_id.get(t_id)
        if not attack_pos or not tpos:
            return 0
        # unités adjacentes (cheby 1) à la cible, AVEC le caster repositionné sur attack_pos.
        def _adj_pos(uid):
            return attack_pos if uid == a_id else (
                (u2["pos"]["col"], u2["pos"]["row"]) if (u2 := _u_by_id.get(uid)) and u2.get("pos") else None)
        adj = [u for u in units if u.get("id") != t_id and _adj_pos(u.get("id"))
               and _cheby(_adj_pos(u.get("id")), tpos) == 1]
        adj_orks = sum(1 for u in adj if _faction(u.get("id")) == "Orks")
        adj_friends = sum(1 for u in adj if u.get("team") == team_by_id.get(a_id))
        gctx = {"attacker_within_range2": _cheby(attack_pos, tpos) <= 2, "base_hits": base_hits,
                "target_adjacent_orks": adj_orks, "target_adjacent_friends": adj_friends}
        return attacker_bonus_hits(traits, gctx)

    # 3) CHAÎNE FIDÈLE PAR CIBLE (RE §16, câblage A) : base = stat Attack (StatAmountFormula) →
    #    spread → GetDamageWithPiercing(pierce gameconfig, armure CIBLE) → MODIFIER post-perçage par
    #    bout (DamageModifiers bâti depuis les effets actifs de l'attaquant §17.7). Comparé à l'oracle
    #    par (attaquant, cible) : xmod≈1.00 attendu y compris sur les buffés (u94 RapidAssault +25%).
    rows = []
    for ap in (dec.get("attackPlans") or []):
        a_id = ap.get("unitId")
        ctx = ctx_by_id.get(a_id)
        if not ctx:
            continue
        norm_ids = {ab.get("id") for u in (dec.get("units") or []) if u.get("id") == a_id
                    for ab in (u.get("abilities") or []) if ab.get("kind") == "normal"}
        base = ctx.attack                       # RE : base PAR COUP = stat Attack(0)
        att_effects = eff_state.active_effects(a_id, {"hp": hp_by_id.get(a_id)})  # matérialisés + filtrés actifs
        mods = build_attacker_modifiers_from_effects(att_effects)                 # ×bonus + pénétration §17.8
        eff_hits = hits_bonus_from_effects(att_effects)   # +bonus effets (PowerTrip_FullHealth +1), par-attaquant
        eff_names = [e.name for e in att_effects]
        a_pos = pos_by_id.get(a_id)
        for ev in (ap.get("evals") or []):
            if norm_ids and ev.get("abilityId") not in norm_ids:
                continue
            rk = ev.get("ranked") or []
            if not rk or rk[0].get("dmgMax") is None:
                continue
            r0 = rk[0]; t_id = ev.get("targetId")
            armor = armor_by_id.get(t_id, 0)
            # position d'ATTAQUE = tuile du plan oracle (ranked col,row ; post-move). C'est ELLE qui fixe
            # mêlée/ranged ET la distance (point user : la prédiction est relative à cette position).
            attack_pos = ((r0.get("col"), r0.get("row")) if r0.get("col") is not None else a_pos)
            t_pos = pos_by_id.get(t_id)
            dist = _cheby(attack_pos, t_pos) if (attack_pos and t_pos) else None
            pierce, _ranged, whits = _normal_weapon_pierce(ctx, dist)
            hits_pre_gsi = whits + ctx.extra_hits + eff_hits      # arme + ExtraHits + PowerTrip+1
            # GetStuckIn (§17.21) : +floor(hits/2) ancré sur la position d'attaque (portée ≤2 + adjacence cible).
            hits = hits_pre_gsi + _getstuckin_bonus(ctx, a_id, t_id, hits_pre_gsi, attack_pos)
            pred = get_attack_prediction(
                target_current_health=hp_by_id.get(t_id, 0), initial_damage=base, hits=hits,
                profile_type=0, pierce_pct=pierce, armor=armor,
                mods=mods)                       # MODIFIER post-perçage par bout (§17.7)
            res = pred.accurate_health_damage
            rows.append({
                "att": a_id, "tgt": t_id, "tgtVis": ev.get("targetVis"),
                "base": base, "pierce": pierce, "armor": armor, "hits": hits,
                "oracle": (r0.get("dmgMin"), r0.get("dmgMax")),
                "offline": (res.min, res.max),
                "predOpt": bool(r0.get("predOptimistic")),
                "mods": [round(m, 3) for m, _c in mods.pct_list] or None,
                "effects": eff_names or None,
            })

    if not rows:
        print("[validate] aucun échantillon d'attaque normale capturé."); return 1
    print(f"\n=== {len(rows)} ÉCHANTILLONS (chaîne fidèle base=Attack+pierce+armure+MODIFIER effets §17) ===")
    print(f"{'att':>5} {'cible':>22} {'base':>6} {'prc':>3} {'arm':>5} "
          f"{'oracle[min-max]':>18} {'offline[min-max]':>18} {'h':>2} {'xmod':>5} {'mods':>10} flag")
    n_clean = n_ok = n_chain = 0
    for r in rows:
        om, oM = r["oracle"]; fm, fM = r["offline"]
        clean = not r["predOpt"]
        ok = clean and _cheby((om, oM), (fm, fM)) <= 3          # tolérance arrondi //100 vs Fix64
        omid, fmid = (om + oM) / 2, (fm + fM) / 2
        mod = omid / fmid if fmid else 0
        chain = clean and 0.97 <= mod <= 1.03                    # ×mod≈1 = chaîne (modifier inclus) exacte
        if clean:
            n_clean += 1
            n_ok += int(ok)
            n_chain += int(chain)
        flag = ("OPT" if r["predOpt"] else ("OK" if ok else ("~chain" if chain else "MOD")))
        mod_s = f"{mod:.2f}" if fmid else "-"                    # ×mod = oracle/offline (modifier résiduel)
        mods_s = ",".join(f"{m:g}" for m in (r["mods"] or [])) or "-"   # ×bonus appliqués (effets captés)
        tgt = f"u{r['tgt']}/{r['tgtVis']}"
        print(f"u{r['att']:>4} {tgt:>22} {r['base']:>6} {r['pierce']:>3} {r['armor']:>5} "
              f"{om}-{oM:<12} {fm}-{fM:<12} {r['hits']:>2} {mod_s:>5} {mods_s:>10} {flag}")
    print(f"\nAGREEMENT exact (+/-3) : {n_ok}/{n_clean}  |  CHAINE-OK (xmod~1, modifier inclus) : {n_chain}/{n_clean}")
    print("(xmod = oracle/offline ; ~1.00 = chaîne base*hits+pierce+armure+modifier exacte ; mods = ×bonus effets appliqués)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
