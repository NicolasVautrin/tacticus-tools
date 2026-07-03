#!/usr/bin/env python
"""Harnais de validation du moteur playbook — le PILIER (cf. docs/rl/playbook-engine.md §4).

Marche la trajectoire de l'IA NATIVE (`aiStepDryRun` = sa décision non-appliquée), et à
chaque pas compare la décision du MOTEUR à celle du jeu sur le MÊME état -> **agreement %**.
On compare au grain du « chunk » natif (1 message/pas) : un MoveUnitMessage -> on compare la
destination du 1er move ; un ActiveAbilityMessage -> on compare (cible, ability).

Premier jet : décision moteur = attaque (attackPlans + aiPredict + barème kill/overkill) si une
cible est à portée, sinon move « avance vers l'ennemi le plus proche » (MovementSuggestion). Le
move-scoring est grossier (à raffiner par l'agreement) ; l'attaque s'appuie sur le barème validé.

Usage: python engine_validate.py [--runner N] [--steps K]
Pré-requis: session Frida warmee + un runner construit (rl_duel build).
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rl_collect_batch import _resolve_session, _rpc  # noqa: E402
import hexgeo  # noqa: E402
import gameconfig as gc  # noqa: E402
from engine import weights, move, leaves, playbooks  # noqa: E402
from engine.utility import attack_utility  # noqa: E402
from engine.utilities import damage_composite  # noqa: E402
import predict_validate as PV  # noqa: E402  (prédicteur OFFLINE : remplace l'aiPredict live)


def _r(sid: int, method: str, body: dict, t: float = 90) -> dict:
    return (_rpc(sid, method, [body], timeout=t).get("result") or {})


# Le natif `RangedAdjacentEnemyUtility.ShouldApply` gate sur l'arme/ability RANGED
# (`WeaponProfile.IsRanged`), PAS le flag unité-classe `UnitExtensions.IsRanged` que
# decisionView expose (faux pour les unités HeavyWeapon mêlée-classe : darkaTerminator
# = melee mais PlasmaCannon ranged). On dérive donc « ranged-pour-mouvement » de
# gameconfig (vérité offline) via le visualId : arme Range≥2 OU active attackRangeType==Ranged.
#   def="weapon_or_ability" (défaut) : arme OU ability ranged (capture u96)
#   def="weapon" : arme Range≥2 seulement
_RANGED_DEF = os.environ.get("ENGINE_RANGED_DEF", "weapon_or_ability").lower()
_RANGED_CACHE: dict = {}
_DEBUG = bool(os.environ.get("ENGINE_DEBUG"))

# Modèle de dégât pour l'argmax d'attaque (cible/ability) :
#   "faithful" (DÉFAUT) : composite Damage FIDÈLE `engine.utilities.damage_composite` (DamageDealt 80/20
#                         RE'd ghidra + KillUnit 100/50 + OverkillUnit 40/15, doc §13.7/13.8). Échelle
#                         native réelle (~[0,250]), zéro knob. Nécessite target maxHP (observeBattle 1×/
#                         décision). VALIDÉ à parité du legacy sur seeds 777 (60/80/100) + 2024 (45/65/100).
#   "legacy"            : ancien barème deviné `engine.utility.attack_utility` (kill + chip frac×50),
#                         gardé pour A/B / référence.
_DAMAGE_MODEL = os.environ.get("ENGINE_DAMAGE_MODEL", "faithful").lower()

# Modèle de scoring de MOVE :
#   "unitmovement" (DÉFAUT) : `move.best_move_faithful` = décideur natif RE'd UnitMovement(6) = Tile(7)
#                        [Elevation+situationnels] + MinDist(16) sur **distance de CHEMIN** (RPC
#                        pathDistToEnemies, doc §13.11/13.12). Élévation via tileMeta. VALIDÉ > proxy sur
#                        seeds 777 (65/80) + 2024 (55/75), ability 100 %. RPC pathfinder 1×/unité/décision.
#   "proxy"            : ancien `move.best_move` (MinDist + MaxDistEnemies hex, NON-natif) — gardé pour A/B.
_MOVE_MODEL = os.environ.get("ENGINE_MOVE_MODEL", "unitmovement").lower()

# ATTAQUE-vs-MOVE — argmax sur la devise UNIFIÉE (RE doc §13.6). Le natif ne s'engage dans une
# attaque que si `U(attaque) = U_damage + tile_util(tuile d'attaque)` bat `U(move) = tile_util(meilleure
# tuile de move)` ; sinon il se repositionne (= les 4 misses steps 11/12/17/20 où natif MOVE / moteur
# ATTAQUE). DÉSACTIVÉ par défaut et NON FIDÈLE tant que 2 data manquent (cf. doc §13.7) :
#   1. `attack_utility` n'est pas encore le composite Damage natif FIDÈLE — la feuille DamageDealt
#      (DamageUtility, W_damage=80/W_remaining=20, RE'd doc §13.7) est connue, MAIS l'ASSEMBLAGE du
#      composite (quelles des 13 feuilles + poids/signe par feuille) est dans un tableau statique non
#      extrait (read_bytes=token). Sans lui, mélanger U_damage et tile_util = comparer 2 échelles non
#      calibrées → on NE COMPENSE PAS par un knob (devinette). Gate OFF jusqu'à extraction.
#   2. tile_util fidèle = composite Tile(7) [29 él] (idem non extrait) ; move.py en est un PROXY (55/77).
# Piloté par ENGINE_MOVE_VS_ATTACK ("on" = expérimental, NON validé). Le terme dégât utilisé reste
# `best[0]` (barème actuel) — à remplacer par le composite Damage fidèle une fois les arrays extraits.
_MOVE_VS_ATTACK = os.environ.get("ENGINE_MOVE_VS_ATTACK", "off").lower() == "on"

# SEUIL HEAL (fix bucket-tree §3.2, RE'd DefaultAiUnitTactic / GetDefaultActiveAbilityActionGenerators).
# Le natif decide par-unite en iterant une liste ORDONNEE de generateurs [ability(tiers 1000/100/0/-100/
# -1000)..., MOVEMENT en DERNIER] et prend la 1ere action NON-NULLE ; un generateur d'ability renvoie null
# si aucune ability ne PASSE le seuil de son bucket (FUN_18004cc80 : priority>=MinimumPriority). Donc le
# natif prefere une ability au move SEULEMENT si elle passe son seuil, SINON il MOVE. Sans seuil, le moteur
# soigne trop tot (live: Rotbone heal util ~18 -> natif MOVE, moteur soignait). On gate le heal : pris
# seulement si U_heal >= seuil. Defaut 50 (entre Rotbone ~18 NON et seed-777 TwistedScience ~100 OUI).
# Tiers natifs exacts (preference-order par playbook) = calibration fine future. ENGINE_HEAL_MIN_UTIL.
_HEAL_MIN_UTIL = float(os.environ.get("ENGINE_HEAL_MIN_UTIL", "50"))


_FACTION_CACHE: dict = {}


def _faction(visual_id) -> str | None:
    """FactionId gameconfig d'une unité par visualId (cache). Pour le bonus heal
    `HasFaction(15)` = Genestealers (cf. dump.cs UnitFaction.Genestealers=15)."""
    if not visual_id:
        return None
    if visual_id in _FACTION_CACHE:
        return _FACTION_CACHE[visual_id]
    f = None
    try:
        uid = gc.resolve_unit_id(visual_id)
        u = gc.unit(uid) if uid else None
        f = (u or {}).get("FactionId")
    except Exception:
        f = None
    _FACTION_CACHE[visual_id] = f
    return f


def _is_ranged_unit(visual_id) -> bool:
    """« ranged-pour-mouvement » d'une unité (cf. RangedAdjacentEnemyUtility.ShouldApply),
    dérivé de gameconfig par visualId. Cache par visualId."""
    if not visual_id:
        return False
    if visual_id in _RANGED_CACHE:
        return _RANGED_CACHE[visual_id]
    res = False
    try:
        uid = gc.resolve_unit_id(visual_id)
        u = gc.unit(uid) if uid else None
        if u:
            if any((w.get("Range") or 0) >= 2 for w in (u.get("weapons") or [])):
                res = True
            elif _RANGED_DEF != "weapon":
                for aid in (u.get("activeAbilities") or []):
                    a = gc.ability(aid) or {}
                    if (a.get("attackRangeType") or "").lower() == "ranged":
                        res = True
                        break
    except Exception:
        res = False
    _RANGED_CACHE[visual_id] = res
    return res


def _enemies(units: list, cur_player: int) -> list:
    # ctrl=False => unité adverse ; vivante
    return [u for u in units if not u.get("ctrl") and u.get("alive")
            and u.get("pos")]


def engine_decide(sid: int, rid: int, dv: dict, mov_by_unit: dict, uid: int, wt,
                  predictor: dict | None = None) -> dict:
    """Décision du moteur pour l'unité uid sur l'état dv. Renvoie une forme normalisée :
    {kind:"move", to:(c,r)} ou {kind:"ability", target, ability, to:(c,r)}."""
    units = dv.get("units") or []
    cur = dv.get("currentPlayer")
    plans = {p.get("unitId"): p for p in (dv.get("attackPlans") or [])}
    enemies = _enemies(units, cur)
    epos = [(e["pos"]["col"], e["pos"]["row"]) for e in enemies]
    me = next((u for u in units if u.get("id") == uid), None)
    hp_cur_by_id = {u.get("id"): u.get("hp") for u in units}   # PV courants cible (kill/killSure spéciales)
    ab_name_by_id = {x.get("id"): x.get("name") for x in ((me or {}).get("abilities") or [])}

    # maxHP par cible (combinedMax du composite Damage fidèle) — observeBattle 1×/décision, mode
    # "faithful" seulement. Clé = squadId (= l'id cible des attackPlans, cf. branche heal). Manque -> le
    # scoreur retombe sur hpBefore (cible pleine), dégradation sûre.
    hpmax_by_id: dict = {}
    if _DAMAGE_MODEL == "faithful":
        obs = _r(sid, "observeBattle", {"runnerId": rid}, 40)
        hpmax_by_id = {u.get("squadId"): (u.get("hpMax") or 0) for u in (obs.get("units") or [])}

    # État courant du pas pour le prédicteur OFFLINE (hp/pos/team/effets seed) — reconstruit à chaque
    # décision car l'état mute. `predictor` (tables cold, 1×/runner) fourni par run_agreement.
    sctx = PV.step_context(predictor, dv) if predictor is not None else None
    if sctx is not None:
        # PV max par unité (observeBattle) — consommé par `make_damage_predictions` pour le coût en
        # PV des abilities (`GetHealthToLose`, ex. DakkaDakkaDakka 15% maxHP → event SELF négatif).
        sctx["hpmax_by_id"] = hpmax_by_id

    # Élévation par tuile (Tile(7)) + distance-CHEMIN par tuile (MinDist fidèle, doc §13.12) — mode
    # "unitmovement" seulement. tileMeta 1×/décision ; pathDistToEnemies 1×/unité.
    elev_by_pos: dict = {}
    pathdist_by_pos: dict = {}
    is_temporary_by_pos: dict = {}
    effects_by_pos: dict = {}
    if _MOVE_MODEL == "unitmovement":
        tm = _r(sid, "tileMeta", {"runnerId": rid}, 60)
        elev_by_pos = {(t.get("col"), t.get("row")): t.get("elevation")
                       for t in (tm.get("tiles") or [])}
        is_temporary_by_pos = {(t.get("col"), t.get("row")): bool(t.get("isTemporary"))
                               for t in (tm.get("tiles") or [])}
        # Effets de statut de tuile (tileMeta.effects) -> feuille TileEffects(9). name = clé de
        # poids Default.TileEffects (ex. Thorns_DefenseReduction=-25). Multiplicateur natif = 1.0
        # par défaut (PROUVE : Thorns -25 = poids -25 x mult => mult=1) ; la branche speciale
        # (owner ami/ennemi + effectType==5/Fire) n'est pas encore appliquee (cf. tile.py:tile_effects).
        effects_by_pos = {(t.get("col"), t.get("row")): [e.get("name") for e in (t.get("effects") or [])]
                          for t in (tm.get("tiles") or [])}
        pdr = _r(sid, "pathDistToEnemies", {"runnerId": rid, "unitId": uid}, 90)
        pathdist_by_pos = {(t.get("col"), t.get("row")): t.get("pathDist")
                           for t in (pdr.get("tiles") or [])}

    # Candidat MOVE calculé TÔT (réutilisé par la comparaison attaque-vs-move §13.6 ET la section 2).
    # origin/ranged = au sens natif (gameconfig), pas le flag unité-classe decisionView.ranged.
    origin = (me["pos"]["col"], me["pos"]["row"]) if me and me.get("pos") else None
    ranged = _is_ranged_unit(me.get("visualId")) if me else False
    move_tiles = (mov_by_unit.get(uid) or {}).get("tiles") or []
    move_to, move_util = (None, None)
    if move_tiles and enemies:
        if _MOVE_MODEL == "unitmovement":
            move_to, move_util = move.best_move_faithful(
                move_tiles, elev_by_pos, epos, wt, pathdist_by_pos=pathdist_by_pos,
                is_temporary_by_pos=is_temporary_by_pos, effects_by_pos=effects_by_pos)
        else:
            move_to, move_util = move.best_move(move_tiles, origin, epos, wt, ranged)

    # 1. Attaque : evals atteignables (rankCount>0) -> barème kill/overkill via aiPredict.
    #    allAbilities=True => inclut les abilities spéciales d'attaque (ex. DakkaDakkaDakka 1171),
    #    Comparable, MÊME barème → argmax sûr (n'ajoute que des candidats).
    plan = plans.get(uid) or {}
    # Ids d'attaque NORMALE de l'unité (name « *NormalAttack »). Tie-break : à utilité
    # ÉGALE, le natif préfère l'ability SPÉCIALE à l'attaque normale (bucket d'ability
    # active > bucket normal-attack ; RE bucket-tree §10). Ex. seed777 step21 : 1171
    # DakkaDakkaDakka et 69 normal tuent tous deux u84 (util 50) -> natif prend 1171.
    normal_ids = {a.get("id") for a in ((me or {}).get("abilities") or [])
                  if "NormalAttack" in (a.get("name") or "")}

    # ── 0. ÉTAGE NonComparable (tiers de préférence) — évalué AVANT toute Comparable. RE :
    #    `InitAbilityTypeLists @1810ed540` répartit les abilities par playbook : NonComparable ->
    #    generators de PRIORITÉ [1000,100,0,-100,-1000] ; Comparable (attaque normale INCLUSE,
    #    heals, PlasmaCannon…) -> generator FINAL, évalué APRÈS. `GetDefaultActiveAbilityAction-
    #    Generators @1810ed0c0` = cet ordre exact ; le tactic prend le PREMIER generator non-vide
    #    => une NC qui passe son MIN_UTILITY (cctor, gate `Bucket.AddAction @1813fbcc0` util>=min)
    #    PRIME sur toute attaque/heal quelle que soit leur utilité (preuves seed777 : step7
    #    FightingRetreat u=2 choisi avec attaque ~30 dispo ; step14 summon u>=1 vs attaque 61 ;
    #    step15 RadBombardment u<2 -> tier vide -> attaque normale). Chaque playbook natif = UNE
    #    classe homonyme dans engine/playbooks.py (selector + leaf EvaluateNonComparable + cctor
    #    MIN_UTILITY) ; `choose_action` = le driver générique (mirror Bucket.ChooseAction : argmax
    #    STRICT `>`, tie -> premier énuméré, heuristique BRUTE sans terme Tile7).
    fpos = [(u["pos"]["col"], u["pos"]["row"]) for u in units
            if u.get("ctrl") and u.get("alive") and u.get("pos") and u.get("id") != uid]
    reach_nc = ([origin] if origin is not None else []) \
        + [(t["col"], t["row"]) for t in move_tiles]
    nc_ctx = playbooks.NCContext(
        uid=uid, origin=origin, reach_nc=reach_nc, epos=epos, fpos=fpos,
        plan=plan, hp_cur_by_id=hp_cur_by_id,
        ability_targets=lambda u, a: _r(
            sid, "abilityTargets", {"runnerId": rid, "unitId": u, "abilityType": a}, 40),
        debug=_DEBUG)
    bc = playbooks.choose_action((me or {}).get("abilities") or [], nc_ctx)
    if bc is not None:
        return {"kind": "ability", "target": bc["target"], "ability": bc["ability"],
                "to": bc["to"], "util": bc["pred"]}

    # Terme de tuile Tile(7) — défini ICI (avant l'argmax d'attaque) : le natif score le JOINT
    # (tuile, cible) = `CalculateActionUtility` = utilité-dégât + Tile(7)@tuile ENSEMBLE
    # (EvaluateInternal @181408980 + gate/argmax Bucket sur l'utilité TOTALE). Classer par dégât
    # seul puis ajouter la tuile après faussait les égalités de dégât (step-11 : (82)@(6,3) tile 50
    # vs (78)@(5,5) tile 20, Σ dégât identiques → le tie partait sur 78 ; natif départage par la
    # tuile → 82).
    from engine.utilities.tile import tile_composite
    _elevs0 = [e for e in elev_by_pos.values() if e is not None]
    _emax0, _emin0 = (max(_elevs0), min(_elevs0)) if _elevs0 else (None, None)

    def _tile_term0(pos):
        meta: dict = {}
        e = elev_by_pos.get(pos)
        if e is not None:
            meta = {"elevation": e, "elevation_max": _emax0, "elevation_min": _emin0}
        if pos in is_temporary_by_pos:
            meta["is_temporary"] = is_temporary_by_pos[pos]
        if pos in effects_by_pos:
            meta["effects"] = effects_by_pos[pos]
        return tile_composite(pos, meta, {}, wt)

    best = None  # (util_dégât, target, ability, tile)
    best_key = None  # (util_TOTALE = dégât + tuile, is_special) — tie-break spécial>normal
    dbg = []
    for ev in (plan.get("evals") or []):
        if not ev.get("rankCount"):
            continue
        ranked = ev.get("ranked") or []
        if not ranked:
            continue
        tgt, ab = ev.get("targetId"), ev.get("abilityId")
        # SWEEP DE POSITION par paire (ability, cible) : le natif évalue chaque cible depuis CHAQUE
        # position candidate (générateur balaye les tuiles × `EvaluateInternal @181408980` boucle les
        # cibles à position fixe — cf. trace scorerUtilTrace step-11 : (6,3)/(6,4)/(5,5)… × même cible).
        # `ranked[0]` seul est FAUX pour les spéciales (le classement attackPlans est dMin/dMax-based,
        # 0-0/arbitraire pour un playbook spécial → tuile scorée arbitraire ; step-11 : (1150,82) était
        # évalué depuis une tuile non-élevée alors que le natif gagne depuis (6,3) élevée). Argmax
        # STRICT `>` intra-paire (Bucket.AddAction @1813fbcc0 : tie → premier énuméré).
        pair_best = None   # (u, pred, aoe_events, tile)
        for rk in ranked:
            tile = (rk.get("col"), rk.get("row"))
            if tile[0] is None:
                continue
            if ab in normal_ids and sctx is not None:
                # ATTAQUE NORMALE → prédicteur OFFLINE (`predict_validate.predict_normal`) : reproduit
                # `aiPredict` sans lecture live par-candidat (base=Attack×hits + perçage + armure +
                # MODIFIER effets §16/§17, VALIDÉ 11/11 vs oracle). Prédicteur cold capturé 1×/runner.
                dp = PV.make_normal_attack_predictions(predictor, sctx, uid, tgt, tile,
                                                       elev_by_pos=elev_by_pos)
                if dp is None:
                    continue
                # Event dict via la SOURCE UNIQUE `PV._event_from_dp` (cap FillUpStat + split bouclier
                # AccurateShieldDamage@0x78 inclus — l'ancien dict inline perdait les champs shieldDmg*).
                pred = PV._event_from_dp(dp, dp.current_health)
                _aoe_events = []
            else:
                # ABILITY SPÉCIALE → `MakeDamagePredictions` (mirror `<Ability>Playbook.MakeDamage-
                # Predictions`) : LISTE des events = cible principale + cibles AoE (GetSurroundingUnits/
                # GetOtherTargets). None/vide = NON-attaque (summon/buff/heal) → pas candidat.
                _events = (PV.make_damage_predictions(predictor, sctx, uid, tgt, ab,
                                                      ab_name_by_id.get(ab),
                                                      attack_pos=tile, elev_by_pos=elev_by_pos)
                           if sctx is not None else [])
                if not _events:
                    continue
                pred = _events[0][1]          # cible PRINCIPALE (tie-break kill/killSure + dbg)
                _aoe_events = _events[1:]     # cibles AoE additionnelles (surrounding/behind/other)
            _bk = []
            if _DAMAGE_MODEL == "faithful":
                # `CalculateUtilityFromPredictions @181407890` = Σ damage_composite sur TOUS les events
                # (§39) : principale + AoE, chaque event × sa `probability` (eventMultiplier de
                # `CalculateUtilityFromDamageEvent @1814a9f90` ; ex. PlasmaCannon batch secondaire
                # pondéré min(1, maxSecondary/n)). Mono-cible → Σ = terme principal.
                u = damage_composite(pred, hpmax_by_id.get(tgt), wt)   # composite Damage (§13.7/13.8)
                _bk.append((tgt, round(u, 1)))
                for _atid, _apred in _aoe_events:
                    # Event FRIENDLY (self-damage/coût en PV, `GetHealthToLose`) → utilité NÉGÉE
                    # (DamageUtility @1810e2280 : friendly-fire negated ; step-13 : −15.0 exact).
                    _sign = -1.0 if _apred.get("friendly") else 1.0
                    _ua = _sign * _apred.get("probability", 1.0) * damage_composite(
                        _apred, hpmax_by_id.get(_atid), wt)
                    u += _ua
                    _bk.append((_atid, round(_ua, 1)))
            else:
                u = attack_utility(pred, wt)                           # barème historique
            # ARGMAX JOINT (tuile, cible) : u_total = dégât + Tile(7)@tuile (CalculateActionUtility).
            u_full = u + _tile_term0(tile)
            if pair_best is None or u_full > pair_best[0]:
                pair_best = (u_full, u, pred, _aoe_events, tile, _bk)
        if pair_best is None:
            continue
        u_full, u, pred, _aoe_events, tile, _bk = pair_best
        aoe_dbg = len(_aoe_events)
        # Tie-break FIDÈLE : Bucket.AddAction @1813fbcc0 = argmax STRICT `>` (égalité → PREMIER
        # énuméré gardé) et la liste FINAL commence par l'ATTAQUE NORMALE (InitAbilityTypeLists
        # @1810ed540 : [normal, spéciales…]) → à égalité d'utilité TOTALE, la NORMALE gagne.
        # (GROUND TRUTH step-9 seed777 : 69→94 et 1067→94 tous deux sure-kill même tuile → le
        # natif garde la normale ; l'ancien « spécial > normal » était inversé.)
        key = (u_full, 1 if ab in normal_ids else 0)  # util TOTALE, puis normal premier-énuméré
        if _DEBUG:
            p = pred or {}
            dbg.append((ab, tgt, round(u, 1), round(u_full, 1), p.get("killSure"), p.get("kill"),
                        p.get("healthDmgMax"), p.get("hpBefore"), f"aoe{aoe_dbg}", tile,
                        ("sh", p.get("shieldDmgMin"), p.get("shieldDmgMax")), ("bk", _bk)))
        if best_key is None or key > best_key:
            best = (u, tgt, ab, tile)
            best_key = key
    if _DEBUG:
        ab_ids = [a.get("id") for a in ((me or {}).get("abilities") or [])]
        print(f"    [dbg u{uid}] abilities={ab_ids} attack_cands(ab,tgt,util,kS,k,dmax,hp)={dbg}",
              file=sys.stderr)
        # NATIVE per-target prediction (decisionView.attackPlans ranked) — vérité live pour comparer
        # à la prédiction OFFLINE ci-dessus (isole modifier défenseur / conditionnel manquant).
        nat_dbg = [(ev.get("abilityId"), ev.get("targetId"),
                    (ev.get("ranked") or [{}])[0].get("dmgMin"),
                    (ev.get("ranked") or [{}])[0].get("dmgMax"),
                    "OPT" if (ev.get("ranked") or [{}])[0].get("predOptimistic") else "")
                   for ev in (plan.get("evals") or []) if ev.get("rankCount")]
        print(f"    [dbg u{uid}] NATIVE ranked(ab,tgt,dMin,dMax,opt)={nat_dbg}", file=sys.stderr)
    # ── SCORING UNIFIÉ (refonte §2.3bis) : chaque ability candidate = (tuile atteignable, cible)
    #    scorée `pred_util + tile_util(tuile)` ; gate ShouldExecute = `pred_util > 0` ; argmax
    #    `full_util` toutes abilities confondues. Le MOVE est le FALLBACK (RE premier-non-null :
    #    une ability avec pred>0 prime toujours sur le move pur), PAS un co-argmax. L'action native
    #    est COMPOSÉE (move-vers-la-tuile + ability) — c'est ce balayage de tuiles qui la reproduit.
    from engine.utilities.tile import tile_composite
    # Terme de tuile FIDÈLE = composite Tile(7) (RE `CalculateUtilityFromTilePrediction @181408740`,
    # cf. architecture.md §2.3ter/§2.3quater). REMPLACE `move.move_utility` (profil MovementSuggestion) :
    # le natif N'utilise PAS l'engagement pour le terme de tuile d'une ACTION — `CalculateActionUtility`
    # somme `CalculateUtilityFromPredictions@tuile + Tile(7)@tuile` (+ WireweaveNet=0 + CasterPos=0). Sur
    # carte plate Tile(7)≈0 (feuilles situationnelles gatées sur métadata absente) → discrimine seulement
    # sur élévation / tuiles spéciales. ⚠ ctx par-unité (traits/faction) non plombé → feuilles
    # situationnelles = 0 (dégradation native sûre). ⚠ Pour une ability tile-INDÉPENDANTE (self-heal),
    # tous les termes s'égalisent (pred constant + Tile7≈0) → la tuile est un TIE-BREAK (ordre
    # d'énumération natif @0x68, non-RE'd) : l'argmax retombe sur la 1ʳᵉ tuile de `reach` (déterministe,
    # PAS forcément la tuile native exacte — limitation documentée, pas une erreur de score).
    _elevs = [e for e in elev_by_pos.values() if e is not None]
    _emax, _emin = (max(_elevs), min(_elevs)) if _elevs else (None, None)

    def _tile_term(pos):
        meta: dict = {}
        e = elev_by_pos.get(pos)
        if e is not None:
            meta = {"elevation": e, "elevation_max": _emax, "elevation_min": _emin}
        if pos in is_temporary_by_pos:
            meta["is_temporary"] = is_temporary_by_pos[pos]
        if pos in effects_by_pos:
            meta["effects"] = effects_by_pos[pos]   # feuille TileEffects (ex. Thorns_DefenseReduction=-25)
        return tile_composite(pos, meta, {}, wt)

    cands: list = []  # {target, ability, to:(c,r)|None, pred, full}
    if best and best[0] > 0:
        # ATTAQUE : tuile native = attackPlans.ranked (déjà la tuile move-to-attack choisie).
        cands.append({"target": best[1], "ability": best[2], "to": best[3],
                      "pred": best[0], "full": best[0] + _tile_term(best[3])})

    # 1bis. SOIN (tile-swept) — balaie (tuile atteignable × cible valide) et ajoute au pool unifié.
    #        pred = CustomUtility (per-ability) + heal_term FIDÈLE (HealUtility @1810e16f0 =
    #        (effective/(maxHP+1))*100*friendSign*bossMod ; effective = PredictHeal/MaxFillUp =
    #        min(healAmount, missing), SATURÉ = missing). Gate ShouldExecute @181184b30 : on N'ÉMET le
    #        soin QUE si `pred > 0` (l'ancien seuil `ENGINE_HEAL_MIN_UTIL`=50 était FAUX — le natif
    #        soigne en MOVE+HEAL dès pred>0, cf. architecture.md §2.3bis). La tuile retenue (full_util =
    #        pred + tile_util) reproduit le déplacement de l'action native COMPOSÉE (move+heal).
    unit_by_id = {u.get("id"): u for u in units}
    pos_by_id = {u.get("id"): (u["pos"]["col"], u["pos"]["row"])
                 for u in units if u.get("pos") and u["pos"].get("col") is not None}
    heal_abis = [ab for ab in ((me or {}).get("abilities") or [])
                 if "Heal" in (ab.get("name") or "") and ab.get("usable") is not False]
    if heal_abis:
        from engine.predict import heal_utility
        obs = _r(sid, "observeBattle", {"runnerId": rid}, 40)
        hpmax_by_sq = {u.get("squadId"): u for u in (obs.get("units") or [])}
        # reach = ORIGINE + destinations de MOUVEMENT. RE step-1 seed777 (soin 1167 SANS
        # MoveUnitMessage alors que des tuiles de mouvement existaient) : la liste native des
        # "AllPossibleMovementTiles" balayées par le generator CONTIENT la tuile courante — la
        # nuance §2.3quater ("NullPosition Merge que si aucune tuile") porte sur NullPosition,
        # PAS sur la tuile-origine, qui est une candidate comme les autres. Sélection native =
        # `ComparablePlaybook.EvaluateInternal @181408980` : bucket best remplacé par STRICT `>`
        # (tie -> le PREMIER énuméré gagne ; `FUN_18004cc80` = seuil MinUtility du bucket, init
        # Int32.MinValue -> inopérant ici, PAS un delta). Preuve chiffrée step 1 : (stay@(1,1),88)
        # = 100+Tile7(elev3=30) = 130 == ((0,2),94) = 130 -> égalité stricte, natif garde (stay,88).
        # Origine EN TÊTE de reach (proxy de l'ordre natif : premier max gardé par `max()` sur tie).
        reach = ([origin] if origin is not None else []) + [(t["col"], t["row"]) for t in move_tiles]
        HEAL_RANGE = 1  # soins d'allie cibles = adjacents. Verifie gameconfig: AUCUN heal cible n'a de
        # constant `range` (les abilities heal a range = vol de vie sur attaque -> chemin degat). Pas de soin cible a distance.
        for ab in heal_abis:
            aid = ab.get("id")
            at = _r(sid, "abilityTargets", {"runnerId": rid, "unitId": uid, "abilityType": aid}, 40)
            vts = set()
            for u in (at.get("units") or []):
                for a in (u.get("abilities") or []):
                    if a.get("abilityId") == aid:
                        for t in (a.get("targets") or []):
                            if t.get("kind") == "unit" and t.get("targetId") is not None:
                                vts.add(t["targetId"])
            is_twisted = "TwistedScience" in (ab.get("name") or "")
            for tg in vts:
                tu = unit_by_id.get(tg) or {}
                if any("TwistedScience_ExtraHp" in (e.get("name") or "") for e in (tu.get("effects") or [])):
                    continue  # gate CustomUtility (TwistedScience) : déjà buffé → 0
                ob = hpmax_by_sq.get(tg) or {}
                hp_max = int(ob.get("hpMax") or 0)
                hp_cur = int(ob.get("hp") or 0)
                eff = max(0, hp_max - hp_cur)   # soin effectif SATURÉ = missing
                # cibles abilityTargets d'un SOIN = alliés/self (même équipe que l'unité agissante `me`).
                # ⚠ comparer à me.team (1/2), PAS à currentPlayer (3/4) — sinon is_friend toujours faux.
                is_friend = (me is not None and tu.get("team") == me.get("team"))
                heal_term = heal_utility(eff, hp_max, is_friend=is_friend, is_boss=False)
                custom = (100 + (100 if _faction(tu.get("visualId")) == "Genestealers" else 0)) if is_twisted else 0
                pred = custom + heal_term
                if _DEBUG:
                    print(f"    [dbg heal u{uid}->{tg}] vis={tu.get('visualId')} fac={_faction(tu.get('visualId'))} "
                          f"hp={hp_cur}/{hp_max} miss={eff} custom={custom} heal_term={round(heal_term,2)} pred={round(pred,2)}",
                          file=sys.stderr)
                if pred <= 0:
                    continue  # ShouldExecute : émet le soin SSI pred > 0
                tpos = pos_by_id.get(tg)
                for T in reach:
                    if tg != uid and (tpos is None or hexgeo.distance(T, tpos) > HEAL_RANGE):
                        continue  # cible hors portée de soin depuis T (self = depuis toute tuile)
                    cands.append({"target": tg, "ability": aid,
                                  "to": (T if T != origin else None),
                                  "pred": pred, "full": pred + _tile_term(T)})

    # (Les abilities NonComparable — BloodyFury, Vexilla, FightingRetreat, summon — sont traitées
    #  par l'ÉTAGE 0 ci-dessus, AVANT ce pool Comparable : cf. InitAbilityTypeLists @1810ed540.)

    # ── ARGMAX UNIFIÉ (generator FINAL = abilities Comparable) : meilleure candidate par `full_util` ;
    #    tie-break id de cible croissant (ordre natif). Si une existe, elle PRIME sur le move
    #    (RE premier-non-null). Sinon → move (fallback ci-dessous).
    if _DEBUG and cands:
        for c in sorted(cands, key=lambda c: -c["full"])[:8]:
            print(f"    [dbg cand u{uid}] tgt={c.get('target')} ab={c.get('ability')} to={c.get('to')} "
                  f"pred={round(c.get('pred') or 0,3)} tile_term={round((c.get('full') or 0)-(c.get('pred') or 0),3)} "
                  f"full={round(c.get('full') or 0,3)}", file=sys.stderr)
    if cands:
        bc = max(cands, key=lambda c: (c["full"], -(c.get("target") or 0)))
        return {"kind": "ability", "target": bc["target"], "ability": bc["ability"],
                "to": bc["to"], "util": bc["pred"]}

    # 2. Sinon move : scoring MovementSuggestion porté (engine/move.py) — somme pondérée
    #    MinDistanceToClosestEnemy + MaxDistanceToEnemies (+ RangedAdjacent ; UnitTile off).
    #    Candidat déjà calculé tôt (move_to/move_util) → réutilisé.
    if not move_tiles or not enemies:
        return {"kind": "move", "to": None}
    return {"kind": "move", "to": move_to, "util": move_util}


def native_chunk(action: dict) -> dict:
    """Extrait le chunk COMPLET d'une action native — move ∧ ability, PAS seulement le 1er
    message. Une action native est COMPOSÉE : `[MoveUnitMessage?, ActiveAbilityMessage?,
    FinishUnitTurnMessage?]`. On DOIT comparer les DEUX dimensions (position du move +
    ability castée) : sinon un soin/attaque COMPOSÉ (move+ability) échappe à la métrique
    ability — c'est le bug historique `native_first` (s'arrêtait au 1er message → un move+heal
    ne comptait QUE comme move ; cause de la saga « VERDICT B », cf. doctrine mesure-vérité).
    Renvoie {move:{to}|None, ability:{ability,target}|None, finish:bool, unit}."""
    move = ability = None
    finish = False
    unit = None
    for m in (action.get("messages") or []):
        cls = m.get("cls")
        if cls == "MoveUnitMessage" and move is None:
            to = m.get("to") or {}
            move = {"to": (to.get("col"), to.get("row"))}
            unit = unit if unit is not None else m.get("unitId")
        elif cls == "ActiveAbilityMessage" and ability is None:
            ability = {"ability": m.get("abilityType"), "target": m.get("targetId")}
            unit = unit if unit is not None else m.get("casterId")
        elif cls == "FinishUnitTurnMessage":
            finish = True
            unit = unit if unit is not None else m.get("unitId")
    return {"move": move, "ability": ability, "finish": finish, "unit": unit}


def run_agreement(sid: int, rid: int, steps: int, wt, log=print) -> dict:
    """Marche la trajectoire NATIVE sur `steps` pas (aiStepDryRun → applyAction) et
    compare la décision du MOTEUR à chaque chunk décisionnel (move/ability). SOURCE
    UNIQUE de la comparaison — réutilisée par `main` ET la suite pytest
    (tests/engine/test_playbook_live.py). MUTE l'état du runner (applique les
    actions natives pour avancer) → runner ISOLÉ recommandé.

    Retourne {pos:{n,exact,near}, ability:{n,match}, records:[…]}."""
    # Prédicteur OFFLINE capturé 1×/runner (combatSnapshot cold) — nourrit le scoring d'attaque
    # d'engine_decide SANS aiPredict live. None si combatSnapshot KO (le scoring d'attaque saute alors).
    predictor = PV.build_predictor(sid, rid)
    if predictor is None:
        log("[agreement] combatSnapshot KO — prédicteur offline indisponible (scoring attaque désactivé)")
    n_pos = n_pos_exact = n_pos_near = 0
    n_ab = n_ab_match = 0
    records: list = []
    for step in range(steps):
        dry = _r(sid, "aiStepDryRun", {"runnerId": rid}, 40)
        if not dry.get("ok") or not dry.get("hasNext"):
            log(f"  step {step}: native épuisé / fin de tour ({dry.get('error') or 'no action'})")
            break
        nat = native_chunk(dry.get("action") or {})
        uid = dry.get("activatedUnitId") or nat.get("unit")

        if (nat["move"] or nat["ability"]) and uid is not None:
            # maxRank 32 (défaut 8) : le SWEEP de position par paire (ability,cible) doit voir TOUTES
            # les tuiles d'attaque — le rang natif est arbitraire pour les spéciales (dmg 0-0), la
            # meilleure tuile moteur peut être au-delà du rang 8 (step-11 : (6,3) pour (1150,82)).
            dv = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
            mov = _r(sid, "aiMovableTiles", {"runnerId": rid}, 60)
            # Boucliers = état DYNAMIQUE (accordés en cours de bataille) → refresh par pas comparé
            # (cf. PV.refresh_shields ; le cold de build_predictor rate p.ex. worldTerminator 3989).
            if predictor is not None:
                PV.refresh_shields(predictor, sid, rid)
            mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
            eng = engine_decide(sid, rid, dv, mov_by_unit, uid, wt, predictor)
            eng_to = eng.get("to")
            # Chunk COMPOSÉ → on compare les DEUX dimensions présentes (move ET/OU ability).
            # POSITIONING — SSI le natif a bougé (l'`eng.to` porte la tuile move-to, y compris
            # pour une action composée où eng.kind == "ability").
            if nat["move"]:
                nat_to = nat["move"]["to"]
                n_pos += 1
                d = hexgeo.distance(eng_to, nat_to) if (eng_to and nat_to) else None
                if d is not None:
                    n_pos_exact += int(d == 0)
                    n_pos_near += int(d <= 1)
                    tag = "EXACT" if d == 0 else f"~{d}hex"
                else:
                    tag = "no-dest"
                records.append({"step": step, "uid": uid, "kind": "move",
                                "native": nat_to, "engine": eng_to, "dist": d,
                                "engine_kind": eng["kind"]})
                log(f"  step {step:2} u{uid}: pos native->{nat_to} engine->{eng_to} "
                    f"[{tag}] (eng={eng['kind']})")
            # ABILITY — SSI le natif a casté (in-place OU composé move+ability). C'est ICI que
            # les soins/attaques COMPOSÉS entrent enfin dans la métrique ability (fix §e).
            if nat["ability"]:
                na = nat["ability"]
                # SUMMON : le `targetId` natif = l'id de l'unité SPAWNÉE (artefact post-exécution,
                # inconnaissable a priori) -> comparaison sur l'ability seule (loggé tel quel).
                tgt_ok = (eng.get("target") == na["target"]
                          or leaves.is_summon(na["ability"]))
                same_ab = (eng["kind"] == "ability"
                           and tgt_ok
                           and eng.get("ability") == na["ability"])
                n_ab += 1
                n_ab_match += int(same_ab)
                records.append({"step": step, "uid": uid, "kind": "ability",
                                "native": (na["ability"], na["target"]),
                                "engine": (eng.get("ability"), eng.get("target")),
                                "match": same_ab, "engine_kind": eng["kind"]})
                log(f"  step {step:2} u{uid}: ABIL native(ab={na['ability']},tgt={na['target']}) "
                    f"engine={eng['kind']}(ab={eng.get('ability')},tgt={eng.get('target')}) "
                    f"[{'MATCH' if same_ab else 'MISS'}]")
        else:
            k = "finish" if nat["finish"] else "other"
            log(f"  step {step:2} u{uid}: native={k} (non comparé, on avance)")

        # applique l'action NATIVE (on marche SA trajectoire) pour avancer l'état.
        acts = []
        for m in (dry["action"]["messages"]):
            if m.get("cls") == "MoveUnitMessage":
                acts.append({"kind": "move", "unitId": m["unitId"],
                             "to": {"col": m["to"]["col"], "row": m["to"]["row"]}})
            elif m.get("cls") == "ActiveAbilityMessage":
                acts.append({"kind": "ability", "casterId": m["casterId"],
                             "targetId": m.get("targetId"), "abilityType": m["abilityType"]})
            elif m.get("cls") == "FinishUnitTurnMessage":
                acts.append({"kind": "finish", "unitId": m["unitId"]})
        if acts:
            _r(sid, "applyAction", {"runnerId": rid, "actions": acts}, 40)

    return {"pos": {"n": n_pos, "exact": n_pos_exact, "near": n_pos_near},
            "ability": {"n": n_ab, "match": n_ab_match}, "records": records}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runner", type=int, default=None)
    ap.add_argument("--steps", type=int, default=12)
    a = ap.parse_args(argv)
    sid = _resolve_session()
    rid = a.runner
    if rid is None:
        rl = _rpc(sid, "listRunners", [], timeout=10).get("result") or []
        first = rl[0] if rl else None
        # listRunners renvoie soit des ints, soit des objets {runnerId, started, seed}.
        rid = first.get("runnerId") if isinstance(first, dict) else first
    if rid is None:
        print("[validate] aucun runner — `rl_duel build` d'abord", file=sys.stderr)
        return 2
    wt = weights.load()
    print(f"[validate] session={sid} runner={rid} steps={a.steps}  {wt}")

    # Marche la trajectoire native + compare (SOURCE UNIQUE : run_agreement).
    res = run_agreement(sid, rid, a.steps, wt)
    pos, ab = res["pos"], res["ability"]

    print()
    if pos["n"]:
        print(f"[positioning] {pos['n']} moves : exact={pos['exact']} ({100*pos['exact']//pos['n']}%)  "
              f"<=1hex={pos['near']} ({100*pos['near']//pos['n']}%)")
    if ab["n"]:
        print(f"[ability]     {ab['n']} casts : match={ab['match']} ({100*ab['match']//ab['n']}%)")
    if not pos["n"] and not ab["n"]:
        print("[agreement] aucun chunk décisionnel comparé")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
