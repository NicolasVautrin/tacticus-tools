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
from engine.entities.abilities.active_ability import (
    AActiveAbility, active_ability_for, makes_damage_predictions, _PROFILE_BY_INDEX)
from engine import dsl
from engine.entities.abilities.ability_configuration import AbilityConfiguration
from engine.services.damage_calculations import spread_to_min_max
from engine.services.damage_prediction import get_attack_prediction, get_default_attack_hits
from engine.entities import EffectsState
from engine.entities.effects import (
    build_attacker_modifiers_from_effects, build_defender_modifiers_from_effects, hits_bonus_from_effects,
)
from engine.entities.traits import attacker_bonus_hits
from engine.services.damage_modifiers import add_modifier, calculate_elevation_bonus_modifier
from engine import weights as _weights

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / "data" / "duel_state.json"

# Bonus de dégât positionnels/config (BC `Damage`) — RE `CalculateElevationBonusModifier` @181003ea0.
# `ElevationBonus` (=50) = +% si la tuile de l'attaquant surplombe celle de la cible.
_DMG_CFG: dict = json.loads(_weights.DEFAULT_BC.read_text(encoding="utf-8")).get("Damage", {}) \
    if _weights.DEFAULT_BC.exists() else {}
ELEVATION_BONUS_PCT: int = int(_DMG_CFG.get("ElevationBonus", 50))


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
    return pierce, is_ranged, whits, w.get("DamageProfile")   # profil (gate défenseur TerminatorArmour)


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


# ── PRÉDICTEUR OFFLINE RÉUTILISABLE (câblable dans engine_validate.py, remplace l'aiPredict live) ──
#   build_predictor : capture one-shot (combatSnapshot) → tables statiques par runner.
#   step_context    : état COURANT (hp/pos/team/effets) reconstruit à chaque pas depuis un decisionView.
#   predict_normal  : prédiction offline d'UNE attaque normale (att→tgt depuis attack_pos), = aiPredict.

def _faction_of(vis_by_id, uid):
    v = vis_by_id.get(uid)
    return (GC.unit(v) or {}).get("FactionId") if v else None


def _getstuckin_bonus(ctx, a_id, t_id, base_hits, attack_pos, pos_by_id, team_by_id, vis_by_id, units):
    """+floor(base_hits/2) si GetStuckIn. Ancré sur la **position d'attaque** (`ranked`, post-move) —
    elle fixe within range 2 = cheby(attack_pos, cible)≤2 + les comptes d'adjacence à la CIBLE (le caster
    post-move y est compté). MinDistance natif = pathfinding ; cheby = proxy (§17.21)."""
    traits = ctx.trait_objects()
    if not any(type(t).__name__ == "GetStuckInTrait" for t in traits):
        return 0
    tpos = pos_by_id.get(t_id)
    if not attack_pos or not tpos:
        return 0
    u_by_id = {u.get("id"): u for u in units}

    def _adj_pos(uid):
        if uid == a_id:
            return attack_pos
        u2 = u_by_id.get(uid)
        return (u2["pos"]["col"], u2["pos"]["row"]) if (u2 and u2.get("pos")) else None

    adj = [u for u in units if u.get("id") != t_id and _adj_pos(u.get("id"))
           and _cheby(_adj_pos(u.get("id")), tpos) == 1]
    adj_orks = sum(1 for u in adj if _faction_of(vis_by_id, u.get("id")) == "Orks")
    adj_friends = sum(1 for u in adj if u.get("team") == team_by_id.get(a_id))
    gctx = {"attacker_within_range2": _cheby(attack_pos, tpos) <= 2, "base_hits": base_hits,
            "target_adjacent_orks": adj_orks, "target_adjacent_friends": adj_friends}
    return attacker_bonus_hits(traits, gctx)


def build_predictor(sid, rid):
    """Tables STATIQUES du prédicteur offline pour le runner `rid` — capture one-shot (cold) :
    `combatSnapshot` (dégât d'arme + stats + `unitConfig` mult/level) + `decisionView` (visualId).
    C'est la SEULE lecture live du prédicteur (une fois par runner). Renvoie None si combatSnapshot KO."""
    snap = rpc(sid, "combatSnapshot", {"runnerId": rid}, 40)
    if not snap.get("ok"):
        print(f"[predict] combatSnapshot KO: {snap.get('error')}")
        return None
    dv0 = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1}, 60)
    vis_by_id = {u["id"]: u.get("visualId") for u in (dv0.get("units") or [])}
    ctx_by_id, armor_by_id, mult_by_id, ablvl_by_id = {}, {}, {}, {}
    for u in (snap.get("units") or []):
        eid = u["entityId"]
        u["visualId"] = vis_by_id.get(eid)
        armor_by_id[eid] = int((u.get("stats") or {}).get("fixedArmor") or 0)
        uc = u.get("unitConfig") or {}
        if isinstance(uc, dict) and uc.get("abilityVariablesMultiplier") is not None:
            mult_by_id[eid] = int(uc["abilityVariablesMultiplier"])
            if uc.get("passiveAbilityLevel"):
                ablvl_by_id[eid] = int(uc["passiveAbilityLevel"])
        # activeAbilityLevel (indexe minDmg/maxDmg des spéciales) = lu par UnitContext.from_snapshot
        # depuis u["unitConfig"] directement.
        if not (u.get("normalAttack") or {}).get("error"):
            ctx_by_id[eid] = UnitContext.from_snapshot(u, GC.unit(vis_by_id.get(eid) or ""))
    return {"ctx_by_id": ctx_by_id, "armor_by_id": armor_by_id,
            "mult_by_id": mult_by_id, "ablvl_by_id": ablvl_by_id, "vis_by_id": vis_by_id}


def step_context(predictor, dv):
    """État COURANT réutilisable pour tous les `predict_normal` d'un pas (hp/pos/team + effets
    matérialisés seed une seule fois). Reconstruit à chaque pas car l'état mute (walk natif)."""
    units = dv.get("units") or []
    return {
        "units": units,
        "hp_by_id": {u["id"]: u.get("hp") for u in units},
        "pos_by_id": {u["id"]: (u["pos"]["col"], u["pos"]["row"]) for u in units if u.get("pos")},
        "team_by_id": {u["id"]: u.get("team") for u in units},
        "eff_state": EffectsState.seed(
            {u["id"]: (u.get("effects") or []) for u in units},
            predictor["mult_by_id"], predictor["ablvl_by_id"]),
    }


def _add_elevation_and_defender_mods(mods, sctx, tgt_id, is_melee, attack_pos, t_pos,
                                     elev_by_pos, hp_by_id, damage_profile=None):
    """Ajoute au `mods` (accumulateur %-list) l'**ElevationBonus** (attaque en surplomb,
    `CalculateElevationBonusModifier @181003ea0` : +ELEVATION_BONUS_PCT% si tuile d'attaque > tuile cible ;
    gate effet 0x423 non plombé → False = dégradation sûre) + les **modifiers DÉFENSEUR**
    (`CalculateDefenderModifiersForPrediction` : effets de la CIBLE réduisant le dégât reçu, ex.
    Terrifying_ExtraDefense −30% mêlée). PARTAGÉ par `predict_normal` ET `predict_special` : le pipeline
    natif `CalculateDamagePredictionScenario` applique ces modifiers à TOUT dégât d'attaque (normal comme
    spécial), pas seulement l'arme normale — les omettre du chemin spécial gonflait le normal (élévation)
    face au spécial (comparaison inéquitable de l'argmax d'ability)."""
    if elev_by_pos and attack_pos and t_pos:
        a_elev, t_elev = elev_by_pos.get(attack_pos), elev_by_pos.get(t_pos)
        if a_elev is not None and t_elev is not None:
            eb = calculate_elevation_bonus_modifier(a_elev, t_elev, ELEVATION_BONUS_PCT)
            if eb is not None:
                add_modifier(mods, eb)
    tgt_effects = sctx["eff_state"].active_effects(tgt_id, {"hp": hp_by_id.get(tgt_id)})
    def_mods = build_defender_modifiers_from_effects(tgt_effects, is_melee, damage_profile)
    for mult, cap in def_mods.pct_list:
        mods.pct_list.append((mult, cap))


def make_normal_attack_predictions(predictor, sctx, att_id, tgt_id, attack_pos, *, meta=False, elev_by_pos=None):
    """Mirror `ALoki_NormalAttackPlaybook.MakeDamagePredictions @181372730` (→ `FindAttackWeapon` +
    `GenerateMultiHitAttackPredictions` + `PredictAttackRaw`) — cible unique (l'attaque normale n'est pas
    AoE). Chaîne fidèle base=Attack × hits + perçage + armure + MODIFIER (effets attaquant + ElevationBonus +
    modifiers DÉFENSEUR §16/§17). Renvoie un `DamagePredictionResult` (ou `(result, meta_dict)` si meta=True),
    None si l'attaquant n'a pas de contexte capturé. `attack_pos` = tuile d'attaque (post-move) : fixe
    mêlée/ranged, distance, GetStuckIn. `elev_by_pos` = `{(col,row): elevation}` (tileMeta) → ElevationBonus.
    NB: nom historique `predict_normal` réaligné (§ règle CLAUDE.md « partir de la fonction native nommée »)."""
    ctx = predictor["ctx_by_id"].get(att_id)
    if ctx is None:
        return None
    hp_by_id, pos_by_id = sctx["hp_by_id"], sctx["pos_by_id"]
    att_effects = sctx["eff_state"].active_effects(att_id, {"hp": hp_by_id.get(att_id)})
    mods = build_attacker_modifiers_from_effects(att_effects)
    eff_hits = hits_bonus_from_effects(att_effects)
    t_pos = pos_by_id.get(tgt_id)
    dist = _cheby(attack_pos, t_pos) if (attack_pos and t_pos) else None
    pierce, _ranged, whits, prof_name = _normal_weapon_pierce(ctx, dist)
    is_melee = not _ranged
    _add_elevation_and_defender_mods(mods, sctx, tgt_id, is_melee, attack_pos, t_pos,
                                     elev_by_pos, hp_by_id, damage_profile=prof_name)
    # PLANCHER 1 coup : les malus de coups (ex. FightingRetreatHitReduction, EffectBonus
    # `ForAdditionWithMinimum(…, min=Direct(1))` @180f495d0) ne descendent JAMAIS sous 1.
    hits_pre = max(1, whits + ctx.extra_hits + eff_hits)
    hits = hits_pre + _getstuckin_bonus(ctx, att_id, tgt_id, hits_pre, attack_pos,
                                        pos_by_id, sctx["team_by_id"], predictor["vis_by_id"],
                                        sctx["units"])
    armor = predictor["armor_by_id"].get(tgt_id, 0)
    res = get_attack_prediction(
        target_current_health=hp_by_id.get(tgt_id, 0), initial_damage=ctx.attack, hits=hits,
        profile_type=0, pierce_pct=pierce, armor=armor, mods=mods)
    if meta:
        return res, {"base": ctx.attack, "pierce": pierce, "armor": armor, "hits": hits,
                     "mods": [round(m, 3) for m, _c in mods.pct_list] or None,
                     "effects": [e.name for e in att_effects] or None}
    return res


_PROFILE_INDEX = {name: idx for idx, name in _PROFILE_BY_INDEX.items()}


def _event_from_dp(dp, hp):
    """Construit le `ProbableDamageEvent` (pred dict) d'une cible depuis un `DamagePredictionResult` +
    ses PV — cap FillUpStat (dégât santé <= PV) inclus. Partagé main/AoE (structure d'event unique)."""
    r = dp.accurate_health_damage
    return {"hpBefore": hp, "shieldBefore": dp.shield,
            "healthDmgMin": min(r.min, hp), "healthDmgMax": min(r.max, hp),
            "appliedHits": dp.applied_hits, "kill": r.max >= hp, "killSure": r.min >= hp}


def make_damage_predictions(predictor, sctx, caster_id, main_tgt_id, ability_id, ability_name,
                            attack_pos=None, elev_by_pos=None):
    """Mirror de `<Ability>Playbook.MakeDamagePredictions` (ex. `HarvesterOfSoulsPlaybook @1811428b0`) :
    produit la LISTE COMPLÈTE des `ProbableDamageEvent` d'une ability spéciale = cible PRINCIPALE + cibles
    AoE (`GetSurroundingUnits`/`GetOtherTargets` via `ability.get_aoe_targets`, nodes.py). Chaque event
    passe par `predict_special` (= le per-cible de `GenerateMultiHitAttackPredictions @181409da0`).
    Retourne `list[(target_id, event_dict)]` (main en tête), `[]` si non-attaque. La somme de leur
    `damage_composite` = `CalculateUtilityFromPredictions @181407890` (§39). Surrounding dmg =
    minDmg_2/maxDmg_2 (== minDmg/maxDmg pour Harvester → `predict_special` réutilisé tel quel).

    GATE NonComparable : un playbook sans `MakeDamagePredictions` (RadBombardment/BloodyFury/VexillaMagnifica :
    NonComparablePlaybook) n'émet AUCUN ProbableDamageEvent — l'IA le score par une heuristique (compte
    d'ennemis / stat), pas par du dégât. On renvoie `[]` (l'engine ne le scorera pas comme attaque ; il
    fabriquait sinon un dégât depuis `minDmg/maxDmg` gameconfig → sur-évaluation)."""
    if not makes_damage_predictions(ability_name):
        return []                                    # playbook NonComparable → pas de prédiction de dégât
    dp = generate_multi_hit_attack_prediction(predictor, sctx, caster_id, main_tgt_id, ability_id, ability_name,
                         attack_pos=attack_pos, elev_by_pos=elev_by_pos)
    if dp is None:
        return []                                    # non-attaque (summon/buff) → pas d'events
    events = [(main_tgt_id, _event_from_dp(dp, sctx["hp_by_id"].get(main_tgt_id) or 0))]
    ctx0 = predictor["ctx_by_id"].get(caster_id)
    cfg = AbilityConfiguration.from_gameconfig(ability_name, GC.ability(ability_name))
    if ctx0 is None or cfg is None:
        return events
    ab = active_ability_for(ability_name, ability_id, ctx0, cfg)
    units = sctx["units"]
    by_id = {u.get("id"): u for u in units}
    dctx = dsl.DslContext(units=units, caster=by_id.get(caster_id), target=by_id.get(main_tgt_id),
                          config=cfg, ability_level=ctx0.active_ability_level,
                          times_attacked=getattr(ctx0, "times_attacked", 0) or 0,
                          caster_pos=attack_pos, elev_by_pos=elev_by_pos)
    aoe = [t for t in ab.get_aoe_targets(dctx)      # 2ᵉ batch (surrounding/behind/other)
           if t.get("id") is not None and t.get("id") != main_tgt_id]
    # Plafond de cibles secondaires (`GetMaxSecondaryTargets`, ex. PlasmaCannon=2) → le batch
    # secondaire est pondéré `min(1, max/n)` (`FromIntFraction` dans MakeDamagePredictions
    # @181150B10) ; l'event porte `probability`, consommée par le Σ d'utilité (eventMultiplier de
    # `CalculateUtilityFromDamageEvent @1814a9f90`). None (Harvester/BloodyFury) → poids 1.
    maxsec = ab.get_max_secondary_targets()
    prob = (min(1.0, maxsec / len(aoe)) if (maxsec is not None and aoe) else 1.0)
    for t in aoe:
        tid = t.get("id")
        adp = generate_multi_hit_attack_prediction(predictor, sctx, caster_id, tid, ability_id, ability_name,
                              attack_pos=attack_pos, elev_by_pos=elev_by_pos)
        if adp is not None:
            ev = _event_from_dp(adp, sctx["hp_by_id"].get(tid) or 0)
            if prob < 1.0:
                ev["probability"] = prob
            events.append((tid, ev))
    return events


def generate_multi_hit_attack_prediction(predictor, sctx, uid, tgt, ability_id, ability_name,
                                         attack_pos=None, elev_by_pos=None):
    """Per-cible de `ComparablePlaybook.GenerateMultiHitAttackPredictions @181409da0` (appelée par
    `MakeDamagePredictions`) : produit le `ProbableDamageEvent`/`DamagePredictionResult` d'UNE cible avec
    le `(damage, hits, profile, pierce)` PROPRE de l'ability (gameconfig, indexé par niveau via
    `AActiveAbility`), PAS l'arme normale, puis `PredictAttackRaw` (`get_attack_prediction`). Le natif
    itère le SQUAD cible (Blast) — ici mono-membre. **None si non-attaque** (pas de `minDmg/maxDmg` ->
    summon/buff/heal -> pas un candidat d'attaque). NB: nom historique `predict_special` réaligné (§ règle
    CLAUDE.md « partir de la fonction native nommée »)."""
    ctx = predictor["ctx_by_id"].get(uid)
    if ctx is None:
        return None
    cfg = AbilityConfiguration.from_gameconfig(ability_name, GC.ability(ability_name))
    if cfg is None or not (cfg.has_variable("minDmg") or cfg.has_variable("maxDmg")):
        return None                                  # non-attaque -> pas de candidat d'attaque
    ab = active_ability_for(ability_name, ability_id, ctx, cfg)
    base = ab.get_damage()                           # avg(minDmg,maxDmg) au niveau (GetDamage)
    if base <= 0:
        return None
    a = GC.ability(ability_name) or {}
    # §5 : scaling par-unité `AbilityVariablesMultiplierPercentage` sur les variables listées dans
    # `variablesAffectedByUnitRarityMultiplier` (ici minDmg/maxDmg si présentes) — mult capté LIVE
    # (combatSnapshot.unitConfig, ex. 180). L'attaque normale l'a déjà cuit dans le stat Attack ;
    # les SPÉCIALES lisent la variable brute → on applique le mult ici.
    affected = set(a.get("variablesAffectedByRarityBonus") or [])
    mult = predictor["mult_by_id"].get(uid, 100)
    if mult and mult != 100 and ({"minDmg", "maxDmg"} & affected):
        base = (base * mult) // 100
    is_melee = (a.get("attackRangeType") or "").lower() == "melee"
    # Coups = formule PROPRE de l'ability (`ability.GetHits`, cf. active_ability.py) : les abilities
    # portées (HarvesterOfSouls flag/extraHit, BloodyFury snowball, …) surchargent ; les autres gardent
    # le défaut générique `GetDefaultAttackHits(nrOfHits + ExtraHits)` — comportement historique préservé.
    # Bonus/malus de coups des EFFETS de l'attaquant (chaîne partagée `GetHitsWithBonuses` — même
    # couche que l'attaque normale, ex. FightingRetreatHitReduction -1) + PLANCHER 1
    # (`ForAdditionWithMinimum(…, min=Direct(1))` @180f495d0).
    att_effects_h = sctx["eff_state"].active_effects(uid, {"hp": sctx["hp_by_id"].get(uid)})
    hits = max(1, ab.get_special_hits(is_melee)
               + hits_bonus_from_effects(att_effects_h, is_normal_attack=False))
    profile_name = ab.get_damage_profile()
    profile_idx = _PROFILE_INDEX.get(profile_name, 0)
    dp = GC.damage_profile(profile_name) or {}
    dir_pierce = ctx.extra_pierce_melee if is_melee else ctx.extra_pierce_ranged
    pierce = max(0, min(100, int(dp.get("PiercingRatio") or 0) + ctx.extra_pierce + dir_pierce))
    hp_by_id = sctx["hp_by_id"]
    att_effects = sctx["eff_state"].active_effects(uid, {"hp": hp_by_id.get(uid)})
    mods = build_attacker_modifiers_from_effects(att_effects)
    # PARITÉ predict_normal : ElevationBonus (surplomb) + modifiers DÉFENSEUR — le pipeline natif
    # `CalculateDamagePredictionScenario` les applique à TOUT dégât d'attaque (normal ET spécial).
    t_pos = sctx["pos_by_id"].get(tgt)
    _add_elevation_and_defender_mods(mods, sctx, tgt, is_melee, attack_pos, t_pos,
                                     elev_by_pos, hp_by_id, damage_profile=profile_name)
    return get_attack_prediction(
        target_current_health=hp_by_id.get(tgt, 0), initial_damage=base, hits=hits,
        profile_type=profile_idx, pierce_pct=pierce, armor=predictor["armor_by_id"].get(tgt, 0),
        mods=mods)


def build_samples(sid, rid, my_team, max_turns=6):
    """Capture les échantillons d'agrément prédiction (chaîne fidèle) pour le
    runner `rid` DÉJÀ construit : `build_predictor` (cold) → drive au contact,
    puis une row par plan d'attaque NORMALE à portée comparant l'offline
    `predict_normal` à l'oracle live `decisionView`. Réutilisé par le harnais
    (`main`) ET la suite pytest (tests/engine/test_predict_live.py). Retourne
    `list[dict]` (vide si combatSnapshot KO ou aucun échantillon)."""
    predictor = build_predictor(sid, rid)      # 1) capture one-shot (cold) — SEULE lecture live statique
    if predictor is None:
        return []
    print(f"[validate] UnitContext (cold): {len(predictor['ctx_by_id'])} unités")

    dec = _drive_into_range(sid, rid, my_team, max_turns)   # 2) avancer au contact (oracle live)
    sctx = step_context(predictor, dec)                     # état courant (hp/pos/team/effets seed)
    pos_by_id = sctx["pos_by_id"]

    # 3) une row par (attaquant, cible) d'attaque NORMALE à portée : offline `predict_normal` vs oracle
    #    `decisionView` (dmgMin/dmgMax). xmod≈1.00 attendu y compris sur les buffés (u94 RapidAssault +25%).
    rows = []
    for ap in (dec.get("attackPlans") or []):
        a_id = ap.get("unitId")
        if a_id not in predictor["ctx_by_id"]:
            continue
        norm_ids = {ab.get("id") for u in (dec.get("units") or []) if u.get("id") == a_id
                    for ab in (u.get("abilities") or []) if ab.get("kind") == "normal"}
        for ev in (ap.get("evals") or []):
            if norm_ids and ev.get("abilityId") not in norm_ids:
                continue
            rk = ev.get("ranked") or []
            if not rk or rk[0].get("dmgMax") is None:
                continue
            r0 = rk[0]; t_id = ev.get("targetId")
            # position d'ATTAQUE = tuile du plan oracle (ranked col,row ; post-move) — fixe mêlée/ranged +
            # distance. Fallback = position courante de l'attaquant.
            attack_pos = ((r0.get("col"), r0.get("row")) if r0.get("col") is not None
                          else pos_by_id.get(a_id))
            pred, meta = make_normal_attack_predictions(predictor, sctx, a_id, t_id, attack_pos, meta=True)
            res = pred.accurate_health_damage
            rows.append({
                "att": a_id, "tgt": t_id, "tgtVis": ev.get("targetVis"),
                "base": meta["base"], "pierce": meta["pierce"], "armor": meta["armor"],
                "hits": meta["hits"],
                "oracle": (r0.get("dmgMin"), r0.get("dmgMax")),
                "offline": (res.min, res.max),
                "predOpt": bool(r0.get("predOptimistic")),
                "mods": meta["mods"], "effects": meta["effects"],
            })
    return rows


def sample_is_clean(r):
    """Échantillon EXPLOITABLE pour l'agrément : prédiction non-optimiste (les
    `predOptimistic` ignorent une réduction de trigger côté moteur, cf. TF04)."""
    return not r["predOpt"]


def sample_is_ok(r, tol=3):
    """Agrément exact (tolérance arrondi //100 vs Fix64) sur un échantillon clean."""
    om, oM = r["oracle"]; fm, fM = r["offline"]
    return sample_is_clean(r) and _cheby((om, oM), (fm, fM)) <= tol


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
    rows = build_samples(sid, rid, my_team, a.max_turns)

    if not rows:
        print("[validate] aucun échantillon d'attaque normale capturé."); return 1
    print(f"\n=== {len(rows)} ÉCHANTILLONS (chaîne fidèle base=Attack+pierce+armure+MODIFIER effets §17) ===")
    print(f"{'att':>5} {'cible':>22} {'base':>6} {'prc':>3} {'arm':>5} "
          f"{'oracle[min-max]':>18} {'offline[min-max]':>18} {'h':>2} {'xmod':>5} {'mods':>10} flag")
    n_clean = n_ok = n_chain = 0
    for r in rows:
        om, oM = r["oracle"]; fm, fM = r["offline"]
        clean = sample_is_clean(r)
        ok = sample_is_ok(r)                                    # tolérance arrondi //100 vs Fix64
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
