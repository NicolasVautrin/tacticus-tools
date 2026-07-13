"""Générateurs d'action ordonnés — namespace `IdunBattle.AI` (cf. playbook/architecture.md §2.3).

Le tactic natif (`DefaultAiUnitTactic`) itère une LISTE ORDONNÉE de générateurs et prend la PREMIÈRE
action NON-NULLE (`CalculateNextActionForUnit.MoveNext @1810f54e0`). Un `ActiveAbilityActionGenerator`
balaie (tuiles de move × abilities de SON ensemble), fait `LoadPlaybook(ability) -> playbook.Evaluate`
(le playbook énumère ses cibles et les score), merge dans un `Bucket`, `ChooseAction`
(`<GenerateActions>d__7 @18119a3f0` + `@1813fc0d0`).

MÉCANISME CONFIRMÉ (RE ghidra, décompilé = vérité — cf. architecture.md §2.3) : `InitAbilityTypeLists
@1810ed540` range chaque ability par le flag `slot1` de son playbook = **Comparable vs NonComparable** :
  - NonComparable (slot1=FALSE) -> `dict[get_Priority]` : UN générateur par tier de priorité,
    dans l'ordre `[1000, 100, 0, -100, -1000]` (générateurs #1..#5) ;
  - Comparable (slot1=TRUE, **attaque normale INCLUSE** + spéciales d'attaque + soins) -> l'OrderedSet
    `special` = UN générateur fallback (#6), évalué APRÈS tous les tiers NonComparable ;
  - `MovementActionGenerator` (approche pure) EN DERNIER (#7).
`GetDefaultActiveAbilityActionGenerators @1810ed0c0` crée cette liste dans cet ordre exact ; le tactic
prend la 1re action non-nulle. => **toute NonComparable précède toute Comparable** : une NC bat une
attaque de plus forte utilité PAR L'ORDRE DES GÉNÉRATEURS, pas par l'utilité (preuves live seed777 :
step7 FightingRetreat u=2 vs attaque u=102 ; step10 BloodyFury ; step14 summon). Le gate par-playbook
(seuil `Fix64` du cctor : FightingRetreat>=2, AberrantHypermorph>=1, …) décide si la NC « sort » de son
générateur ; sinon on descend au tier suivant, puis au fallback Comparable.

Le SCORING Comparable est dispatché par playbook (`engine.playbook` : NormalAttack/Default/Heal),
chacun déléguant sa prédiction à `engine.playbook.prediction` (modèle objet). Intra-générateur :
argmax d'utilité faisable (`Bucket` `default`), seuil par-playbook comme gate.

NB : sur seed777, les 4 NonComparable présentes (BloodyFury/Vexilla/FightingRetreat/AberrantHypermorph)
sont priorité 0 -> seul le générateur #3 (dict[0]) tire côté NC. #115 (RE gqfc5mff6c) : AUCUN playbook
n'override `get_Priority` (slot-0 de l'interface, dispatch `FUN_180002560(0, interface, playbook)` ;
search_symbols get_Priority/Playbook.*Priority/IsComparable = 0 hit Playbook -> le getter vit UNE fois
sur le parent partagé, jamais surchargé par-leaf) -> les 15 NonComparable portées partagent TOUTES le
tier de base = 0. L'ORDRE inter-tier N'EST DONC JAMAIS exercé (un seul tier peuplé) ; l'ancien
NovaBoost=1000/NovaShield=-1000 venait d'un @1807D66A0 (`mov eax,0x3E8`) stale/mal-attribué qui NE RÉSOUT
PLUS dans ce build -> corrigé à 0. Deux NonComparable d'une même unité se départagent alors par UTILITÉ
(argmax intra-tier `choose_action`), pas par un tier fabriqué.
"""
from __future__ import annotations

import sys
import math

import hexgeo
import gameconfig as gc
from engine import move
from engine import battle_query as bq          # is_adjacent (élévation-gaté) — cibles heal SpiritLeech (#84)
from engine.playbook import noncomparable as playbooks
from engine.playbook import get_playbook_or_default, tile_utility
from engine.playbook.common import NORMAL_ATTACK_PLAYBOOK, HEAL_PLAYBOOK
from engine.playbook.bespoke_heals import BESPOKE_SELFCAST   # #82 : BloodChalice/MomentShackle self-cast
from engine.predict import (repair_utility,            # RepairedAmountUtility (analogue non-custom du soin)
                            predict_heal_effective, heal_amount_config,   # magnitude soin OFFLINE (#79)
                            predict_repair_effective, repair_amount_config,  # magnitude repair OFFLINE (#83)
                            heal_utility)             # HealUtility — terme lifesteal SpiritLeech (#84)
from engine.entities.stats import StatType, StatPart   # Attack INITIALE de la cible (magnitude #85)
from engine.entities.effect_type import EffectType     # #158 : ids d'effet -> enum natif
from engine.entities.effects.magnitude import ability_var   # maxDmg/dmgPct GalvanicField (#85)
from engine.ai.bucket import Action, Bucket


# RepairPlaybook GENERIQUE @181187c00 — identifiee par ID (PAS `"Repair" in name` : R2 ce substring
# captait aussi NanoscarabRepairProtocols(1224), NonComparablePlaybook @18114e1f0 -> mauvais routage).
# Repair(28) SEUL = repair Comparable generique (magnitude hpToRepair, RepairedAmountUtility seule ;
# necroReanimator/ReanimationBeam...). Repair_GalvanicField(1119) = playbook BESPOKE distinct
# (`Repair_GalvanicFieldPlaybook @181155b80` : magnitude % Attack-CIBLE + terme CustomUtility) ->
# route dediee `_repair_galvanic_candidates` (#85), PAS ce set generique. (1224 = NonComparable-repair,
# exclu ; 82/84 = IDs inexistants dans l'enum, retires -- validateur.)
_COMPARABLE_REPAIR_IDS: "frozenset[int]" = frozenset({28})
_GALVANIC_REPAIR_ID = 1119   # Repair_GalvanicField (bespoke Comparable, admecManipulus/Loki) — #85
_SPIRITLEECH_ID = 1104       # SpiritLeech (tyranNeurothrope/Loki) — attaque psychique per-ennemi + lifesteal (#84)
_SPIRITLEECH_HEAL_FACTION = "Tyranids"   # GetHealTargets @18120a1e0 : faction 0xc (self + amis Tyranids adjacents)


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


class ActionGenerator:
    """Base d'un générateur : `generate(ctx) -> action|None`. None = ce générateur n'a produit
    aucune action légale (le tactic passe au suivant)."""

    def generate(self, ctx) -> dict | None:
        raise NotImplementedError


class NonComparableGenerator(ActionGenerator):
    """UN générateur NonComparable de tier `priority` (= `dict[get_Priority]`, `InitAbilityTypeLists
    @1810ed540`). Évalue les abilities NonComparable de l'unité DE CE TIER ; chaque
    `<Playbook>.EvaluateNonComparable` score une heuristique ENTIÈRE (pas de terme Tile7), gate par
    `MIN_UTILITY` (seuil du cctor). `choose_action(priority=…)` = `Bucket.ChooseAction` (argmax STRICT).
    Le tactic instancie 5 de ces générateurs [1000,100,0,-100,-1000], tous AVANT le fallback Comparable
    -> une NC qui « sort » prime sur toute attaque (preuves seed777 : step7 FightingRetreat u=2 vs
    attaque u=102 ; step10 BloodyFury ; step14 summon)."""

    def __init__(self, priority: int = 0):
        self.priority = priority

    def generate(self, ctx) -> dict | None:
        nc_ctx = playbooks.NCContext(
            uid=ctx.uid, origin=ctx.origin, reach_nc=ctx.reach_nc, epos=ctx.epos, fpos=ctx.fpos,
            enemies=ctx.enemies,   # id+pos (meme ordre que epos) -> cible Gauntlets (#117)
            neigh_by_pos=ctx.neigh_by_pos,   # voisins ordre natif -> cible EXACTE Gauntlets (#117)
            walkable_by_pos=ctx.walkable_by_pos,   # gate statique placement CanAddUnit (HammerOfWrath #116)
            plan=ctx.plans.get(ctx.uid) or {}, hp_cur_by_id=ctx.hp_cur_by_id,
            elev_by_pos=ctx.elev_by_pos, ability_targets=ctx.ability_targets,
            wt=ctx.wt, is_temporary_by_pos=ctx.is_temporary_by_pos,
            effects_by_pos=ctx.effects_by_pos, obs_units=ctx.obs_units,
            tile_id_by_pos=ctx.tile_id_by_pos, active_levels=ctx.active_ability_levels,
            units=ctx.units, cast_from_tiles=ctx.cast_from_tiles, scene=ctx.scene, debug=ctx.debug)
        bc = playbooks.choose_action((ctx.me or {}).get("abilities") or [], nc_ctx,
                                     priority=self.priority)
        if bc is None:
            return None
        return {"kind": "ability", "target": bc["target"], "ability": bc["ability"],
                "to": bc["to"], "util": bc["pred"]}


class ComparableAbilityGenerator(ActionGenerator):
    """Tier Comparable (attaque normale INCLUSE + spéciales d'attaque + soins). DISPATCHE par playbook :
    `LoadPlaybook(ability)` (NormalAttack pour l'attaque normale, Default/spéciale sinon) puis
    `playbook.calculate_action_utility(ctx, tuile, cible)` (= `EvaluateInternal @181408980` :
    prédiction déléguée à PV + Σ + Tile(7) + gate ShouldExecute). Sweep de position par paire
    (ability,cible) [argmax tile STRICT] -> argmax inter-ability -> pool attaque+soin -> `Bucket.ChooseAction`."""

    def _best_attack(self, ctx):
        """Sweep attaque : renvoie `best = (u, u_full, target, ability, tile)` ou None. Argmax inter-
        ability par clé `(u_full, is_normal)` (tie-break : à utilité TOTALE égale, l'attaque NORMALE
        gagne — `is_normal_attack` du playbook ; step-9 seed777 : 69 et 1067 sure-kill même tuile
        -> natif garde la normale)."""
        plan = ctx.plans.get(ctx.uid) or {}
        best = None       # (u, u_full, tgt, ab, tile)
        best_key = None
        dbg = []
        for ev in (plan.get("evals") or []):
            if not ev.get("rankCount"):
                continue
            ranked = ev.get("ranked") or []
            if not ranked:
                continue
            tgt, ab = ev.get("targetId"), ev.get("abilityId")
            # LoadPlaybook : attaque normale -> NormalAttackPlaybook ; sinon fallback/spéciale.
            pb = NORMAL_ATTACK_PLAYBOOK if ab in ctx.normal_ids else get_playbook_or_default(ab)
            # SWEEP DE POSITION par paire (ability, cible) : chaque cible depuis CHAQUE tuile candidate
            # (`EvaluateInternal` boucle les cibles à position fixe). `ranked[0]` seul est FAUX pour les
            # spéciales (classement dMin/dMax-based, arbitraire) -> balayer TOUTES. Argmax STRICT `>`.
            pair_best = None   # (u_full, u, pred, aoe, tile, bk)
            for rk in ranked:
                tile = (rk.get("col"), rk.get("row"))
                if tile[0] is None:
                    continue
                cand = pb.calculate_action_utility(ctx, tile, tgt, ab)
                if cand is None:
                    continue
                u_full = cand["u_full"]
                u_val = cand["u"]
                if ab == _SPIRITLEECH_ID:
                    # #84 : SpiritLeech (Comparable) SOMME un terme LIFESTEAL (Σ HealUtility sur self + amis
                    # Tyranids adjacents à `tile`) au dégât dans `CalculateActionUtility`. Position-dépendant.
                    ls = self._spiritleech_lifesteal_util(ctx, tile, cand["pred"])
                    u_full += ls
                    u_val += ls
                if pair_best is None or u_full > pair_best[0]:
                    pair_best = (u_full, u_val, cand["pred"], cand["aoe"], tile, cand["bk"])
            if pair_best is None:
                continue
            u_full, u, pred, aoe, tile, bk = pair_best
            key = (u_full, 1 if pb.is_normal_attack else 0)  # util TOTALE, puis normal premier-énuméré
            if ctx.debug:
                p = pred or {}
                dbg.append((ab, tgt, round(u, 1), round(u_full, 1), p.get("killSure"), p.get("kill"),
                            p.get("healthDmgMax"), p.get("hpBefore"), f"aoe{len(aoe)}", tile,
                            ("sh", p.get("shieldDmgMin"), p.get("shieldDmgMax")), ("bk", bk)))
            if best_key is None or key > best_key:
                best = (u, u_full, tgt, ab, tile)
                best_key = key
        if ctx.debug:
            ab_ids = [a.get("id") for a in ((ctx.me or {}).get("abilities") or [])]
            print(f"    [dbg u{ctx.uid}] abilities={ab_ids} attack_cands(ab,tgt,util,kS,k,dmax,hp)={dbg}",
                  file=sys.stderr)
            nat_dbg = [(ev.get("abilityId"), ev.get("targetId"),
                        (ev.get("ranked") or [{}])[0].get("dmgMin"),
                        (ev.get("ranked") or [{}])[0].get("dmgMax"),
                        "OPT" if (ev.get("ranked") or [{}])[0].get("predOptimistic") else "")
                       for ev in (plan.get("evals") or []) if ev.get("rankCount")]
            print(f"    [dbg u{ctx.uid}] NATIVE ranked(ab,tgt,dMin,dMax,opt)={nat_dbg}", file=sys.stderr)
        return best

    def _spiritleech_lifesteal_util(self, ctx, tile_T, cand_pred) -> float:
        """Terme LIFESTEAL de `SpiritLeechPlaybook.MakeHealPredictions @18115d7a0` (Comparable id 1104,
        tyranNeurothrope/Loki) → `GenerateHealPredictions` → Σ `CalculateUtilityFromHealEvent`, SOMMÉ au
        dégât (+ effet Pinned=0, inerte ce build) par `CalculateActionUtility @181406ee0`.

        - lifesteal = `GetHealAmountForPrediction @181209fa0` = `ceil(degat_predit × hpToHealPct/100)`
          (`GetHealAmountFromDamageAmount @18120a160` = `PercentageOf(dmg, ConfigVar 0x4b, roundUp=1)`).
          `hpToHealPct` ∈ [40..60] au niveau ACTIF du caster (PAS rarity-scaled). `degat_predit` = dégât
          santé+bouclier prédit sur la cible d'attaque (avg des bornes BRUTES @0x24/@0x28 + bouclier).
        - cibles = `GetHealTargets @18120a1e0` = SELF ∪ (amis ADJACENTS à `tile_T`, faction Tyranids(0xc)).
        - Σ par cible : eff = `PredictHeal` = min(lifesteal, PV manquants) ; `HealUtility` = eff/(maxHP+1)×100
          (is_friend=True). Position-dépendant (adjacence des alliés à la tuile de cast `tile_T`)."""
        me = ctx.me
        if me is None or not cand_pred:
            return 0.0
        # degat predit (avg des bornes BRUTES health @0x24/@0x28 + bouclier) sur la cible d'attaque
        dmg = ((cand_pred.get("rawHealthDmgMin") or 0) + (cand_pred.get("rawHealthDmgMax") or 0)) / 2.0 \
            + ((cand_pred.get("shieldDmgMin") or 0) + (cand_pred.get("shieldDmgMax") or 0)) / 2.0
        if dmg <= 0:
            return 0.0
        hc = ctx.heal_config(ctx.uid)
        pct = ability_var("SpiritLeech", "hpToHealPct", hc["active"], multiplier_pct=hc["multiplier"]) or 0
        lifesteal = math.ceil(dmg * pct / 100.0)
        if lifesteal <= 0:
            return 0.0
        # cibles de soin : SELF + amis Tyranids ADJACENTS à la tuile de cast (GetHealTargets)
        team = me.get("team")
        heal_ids = {ctx.uid}
        for u in ctx.units:
            if u.get("id") == ctx.uid or u.get("team") != team or not u.get("alive"):
                continue
            if _faction(u.get("visualId")) != _SPIRITLEECH_HEAL_FACTION:
                continue
            p = u.get("pos")
            if p and p.get("col") is not None and bq.is_adjacent(tile_T, (p["col"], p["row"]), ctx.elev_by_pos):
                heal_ids.add(u.get("id"))
        obs_by_sq = {u.get("squadId"): u for u in ctx.obs_units}
        total = 0.0
        for hid in heal_ids:
            ob = obs_by_sq.get(hid) or {}
            hp_max = int(ob.get("hpMax") or 0)
            hp_cur = int(ob.get("hp") or 0)
            if hp_max <= 0:
                continue
            eff = min(lifesteal, max(0, hp_max - hp_cur))   # PredictHeal = min(healAmount, manquant)
            total += heal_utility(eff, hp_max, is_friend=True, is_boss=False)
        if ctx.debug:
            print(f"    [dbg spiritleech u{ctx.uid}@{tile_T}] dmg={dmg:.0f} pct={pct} lifesteal={lifesteal} "
                  f"healTargets={sorted(heal_ids)} lifestealU={total:.3f}", file=sys.stderr)
        return total

    def _heal_candidates(self, ctx) -> list:
        """Sweep soin (tile-swept) via `HealPlaybook` -> liste {target, ability, to, pred, full}.
        Énumération cibles = `abilityTargets` ; gate d'énumération « cible déjà buffée TwistedScience »
        (inconditionnel) ; utilité par cible = `HealPlaybook.score` (CustomUtility + heal_term ; gate
        pred > 0). reach = origine + tuiles de move (self depuis toute tuile, allié depuis adjacent)."""
        me = ctx.me
        heal_abis = [ab for ab in ((me or {}).get("abilities") or [])
                     if "Heal" in (ab.get("name") or "") and ab.get("usable") is not False]
        if not heal_abis:
            return []
        unit_by_id = {u.get("id"): u for u in ctx.units}
        pos_by_id = {u.get("id"): (u["pos"]["col"], u["pos"]["row"])
                     for u in ctx.units if u.get("pos") and u["pos"].get("col") is not None}
        hpmax_by_sq = {u.get("squadId"): u for u in ctx.obs_units}
        reach = ([ctx.origin] if ctx.origin is not None else []) \
            + [(t["col"], t["row"]) for t in ctx.move_tiles]
        HEAL_RANGE = 1  # gameconfig : aucun heal ciblé n'a de `range` -> adjacent
        out = []
        for ab in heal_abis:
            aid = ab.get("id")
            at = ctx.ability_targets(ctx.uid, aid)
            vts = set()
            for u in (at.get("units") or []):
                for a in (u.get("abilities") or []):
                    if a.get("abilityId") == aid:
                        for t in (a.get("targets") or []):
                            if t.get("kind") == "unit" and t.get("targetId") is not None:
                                vts.add(t["targetId"])
            is_twisted = "TwistedScience" in (ab.get("name") or "")
            # Magnitude OFFLINE du soin = `HealAbility.HealAmount @180e345b0` = `ability_var(hpToHeal, level)`
            # (#79 ; depend de l'ability + du niveau du caster, PAS de la cible -> resolu 1x). None -> pas de
            # `hpToHeal` (soin a arme reelle Heal(18) / magnitude speciale TwistedScience) -> saturation.
            _hc = ctx.heal_config(ctx.uid)
            heal_amt = heal_amount_config(ab.get("name"), _hc["active"], _hc["passive"], _hc["multiplier"])
            for tg in vts:
                tu = unit_by_id.get(tg) or {}
                # gate natif `HasEffect(target, EffectType.TwistedScience_ExtraHp=1355)` sur l'état d'effets
                # STRUCTURÉ (`EffectsState`) — on colle au JEU (HasEffect sur les EffectComponent), PAS à la
                # liste sérialisée `unit["effects"]` de decisionView. Les deux chemins (live/offline) portent
                # cet état via `ctx.scene.eff_state`. Scene absente -> pas d'exclusion (no-op fidèle).
                _eff = getattr(getattr(ctx, "scene", None), "eff_state", None)
                if _eff is not None and _eff.has_effect(tg, effect_type=int(EffectType.TwistedScience_ExtraHp)):
                    continue  # cible déjà buffée (TwistedScience_ExtraHp) -> ignorée (inconditionnel)
                ob = hpmax_by_sq.get(tg) or {}
                hp_max = int(ob.get("hpMax") or 0)
                hp_cur = int(ob.get("hp") or 0)
                missing = max(0, hp_max - hp_cur)   # PV manquants = BORNE du soin effectif
                # Soin EFFECTIF = `PredictHeal @181037180` (MaxFillUp @180f9b790) = min(healAmount, missing).
                # heal_amt None (soin non-hpToHeal) -> saturation `missing` (approximation documentee #79,
                # sans regression). Le -50/+50 friendSign + bossMod restent dans HealUtility (score).
                effective = missing if heal_amt is None else predict_heal_effective(heal_amt, hp_cur, hp_max)
                is_friend = (me is not None and tu.get("team") == me.get("team"))
                faction = _faction(tu.get("visualId"))
                pred = HEAL_PLAYBOOK.score(effective, hp_max, is_friend, is_twisted, faction)
                if ctx.debug:
                    print(f"    [dbg heal u{ctx.uid}->{tg}] vis={tu.get('visualId')} fac={faction} "
                          f"hp={hp_cur}/{hp_max} miss={missing} healAmt={heal_amt} eff={effective} "
                          f"twisted={is_twisted} pred={pred}", file=sys.stderr)
                if pred is None:
                    continue  # ShouldExecute : émet le soin SSI pred > 0
                tpos = pos_by_id.get(tg)
                for T in reach:
                    if tg != ctx.uid and (tpos is None or hexgeo.distance(T, tpos) > HEAL_RANGE):
                        continue  # cible hors portée de soin depuis T (self = depuis toute tuile)
                    out.append({"target": tg, "ability": aid,
                                "to": (T if T != ctx.origin else None),
                                "pred": pred, "full": pred + tile_utility(ctx, T)})
        return out

    def _repair_candidates(self, ctx) -> list:
        """Sweep RÉPARATION GÉNÉRIQUE (tile-swept) via `RepairPlaybook` (Comparable, @181187c00) -> liste
        {target, ability, to, pred, full}. MIROIR de `_heal_candidates` : identification par ID Comparable-
        repair (`_COMPARABLE_REPAIR_IDS` = {28} = Repair générique SEUL ; PAS `"Repair" in name` qui
        captait le NonComparable NanoscarabRepairProtocols(1224). Repair_GalvanicField(1119) = playbook
        BESPOKE -> `_repair_galvanic_candidates`, PAS ici) ; énumération cibles =
        `abilityTargets` ; utilité par cible =
        `repair_utility` (RepairedAmountUtility : `fill_hp/(maxHP+1)×100 + fill_armor/(maxArmor+1)×50`,
        PAS de friendSign — répare ses propres machines) ; gate `ShouldExecute` : pred > 0.

        MAGNITUDE (#83) : `RepairAmount @1811c4860` = `hpToRepair[activeLevel]` de la clé CONCRÈTE de
        l'unité (`repair_amount_config` : nom runtime `Repair` GÉNÉRIQUE → clé résolue via gameconfig
        `activeAbilities`, ex. necroReanimator → ReanimationBeam). `PredictRepair @181038280` remplit DEUX
        stats via `MaxFillUp` : Health(5) + Armor(4) → `fill_hp`/`fill_armor` = `min(repairAmount,
        manquant_i)` (`predict_repair_effective`). Armor courante/max = `observeBattle.armor/armorMax`
        (ArmorComponent, #83). `repair_amt` None (unité sans réparation Comparable à `hpToRepair`) →
        saturation `fill = missing` (approximation documentée, sans régression)."""
        me = ctx.me
        repair_abis = [ab for ab in ((me or {}).get("abilities") or [])
                       if ab.get("id") in _COMPARABLE_REPAIR_IDS and ab.get("usable") is not False]
        if not repair_abis:
            return []
        pos_by_id = {u.get("id"): (u["pos"]["col"], u["pos"]["row"])
                     for u in ctx.units if u.get("pos") and u["pos"].get("col") is not None}
        obs_by_sq = {u.get("squadId"): u for u in ctx.obs_units}
        reach = ([ctx.origin] if ctx.origin is not None else []) \
            + [(t["col"], t["row"]) for t in ctx.move_tiles]
        REPAIR_RANGE = 1  # gameconfig : repair ciblé adjacent (pas de `range` propre observé)
        # Magnitude REPAIR OFFLINE = hpToRepair[activeLevel] × rareté (résolu 1x : dépend du caster, pas de
        # la cible). Niveau = ACTIF (réparation native, +0xB8) via heal_config (même source unitConfig).
        _rc = ctx.heal_config(ctx.uid)
        _caster_vid = (obs_by_sq.get(ctx.uid) or {}).get("visualId")
        repair_amt = repair_amount_config(_caster_vid, _rc["active"], _rc["multiplier"])
        out = []
        for ab in repair_abis:
            aid = ab.get("id")
            at = ctx.ability_targets(ctx.uid, aid)
            vts = set()
            for u in (at.get("units") or []):
                for a in (u.get("abilities") or []):
                    if a.get("abilityId") == aid:
                        for t in (a.get("targets") or []):
                            if t.get("kind") == "unit" and t.get("targetId") is not None:
                                vts.add(t["targetId"])
            for tg in vts:
                ob = obs_by_sq.get(tg) or {}
                hp_max = int(ob.get("hpMax") or 0)
                hp_cur = int(ob.get("hp") or 0)
                arm_max = int(ob.get("armorMax") or 0)
                arm_cur = int(ob.get("armor") or 0)
                if repair_amt is None:   # pas de magnitude Comparable -> saturation (approx documentée)
                    fill_hp = max(0, hp_max - hp_cur)
                    fill_armor = max(0, arm_max - arm_cur)
                else:                    # PredictRepair : min(repairAmount, manquant) par stat (Health+Armor)
                    rp = predict_repair_effective(repair_amt, hp_cur, hp_max, arm_cur, arm_max)
                    fill_hp, fill_armor = rp.fill_hp, rp.fill_armor
                pred = repair_utility(fill_hp, hp_max, fill_armor, arm_max, is_boss=False)
                if ctx.debug:
                    print(f"    [dbg repair u{ctx.uid}->{tg}] vis={ob.get('visualId')} "
                          f"hp={hp_cur}/{hp_max} arm={arm_cur}/{arm_max} repairAmt={repair_amt} "
                          f"fillHp={fill_hp} fillArm={fill_armor} pred={pred}", file=sys.stderr)
                if pred <= 0:
                    continue   # ShouldExecute : émet la réparation SSI pred > 0
                tpos = pos_by_id.get(tg)
                for T in reach:
                    if tg != ctx.uid and (tpos is None or hexgeo.distance(T, tpos) > REPAIR_RANGE):
                        continue   # cible hors portée depuis T (self = depuis toute tuile)
                    out.append({"target": tg, "ability": aid,
                                "to": (T if T != ctx.origin else None),
                                "pred": pred, "full": pred + tile_utility(ctx, T)})
        return out

    def _repair_galvanic_candidates(self, ctx) -> list:
        """`Repair_GalvanicFieldPlaybook @181155b80` (ComparablePlaybook<0x45f=1119>, admecManipulus/Loki)
        — réparation Comparable BESPOKE GRANTED par le passif GalvanicField. DISTINCTE du RepairPlaybook
        générique (`_repair_candidates`, id 28, magnitude hpToRepair) : magnitude ET utilité PROPRES (RE
        ghidra gqfc5mff6c). Tile-swept sur les cibles de `abilityTargets` (self + amis Mechanical, vérité
        live — le natif cible target!=caster, mais le self-repair est OBSERVÉ live seed909 step14).

        MAGNITUDE `GetOverrideAttackDamageAmount @181200080` = `PercentageOfAttackCappedAtMax @180df8530`
        = `M = min(round(cible.Attack_INITIALE × dmgPct/100), maxDmg)` — % de l'Attack INITIALE de la
        CIBLE réparée (`StatType=Attack`, `StatPart=Initial` ; le « 100% of *its own* Damage » du tooltip),
        plafonnée à `maxDmg`. `dmgPct`/`maxDmg` = vars du passif GalvanicField au niveau PASSIF du CASTER
        (`maxDmg` seule rarity-scaled). PAS `hpToRepair`.

        UTILITÉ `CalculateActionUtility @181406ee0` (chemin repair) = SOMME de deux termes (lu dans le
        décompilé, ADDITIFS) : (1) `RepairedAmountUtility` générique = `repair_utility(fill_hp, maxHP,
        fill_armor, maxArmor)` avec `fill = min(M, manquant)` sur Health+Armor (`PredictRepair`/`MaxFillUp`,
        cf. #83) ; (2) `CalculateCustomUtility @181155520` bespoke = `M/(cible.maxHP+1) × 50`, GATÉ par
        `HasValidTargets(cible)` (la cible réparée peut attaquer depuis SA position = combat-readiness, même
        prédicat que #77 → 0 sinon). `ShouldExecute` : util totale > 0."""
        me = ctx.me
        gal = next((ab for ab in ((me or {}).get("abilities") or [])
                    if ab.get("id") == _GALVANIC_REPAIR_ID and ab.get("usable") is not False), None)
        if gal is None:
            return []
        scene = ctx.scene
        if scene is None:
            return []   # pas de prédicteur (combatSnapshot KO) -> Attack cible indisponible -> pas de candidat
        pos_by_id = {u.get("id"): (u["pos"]["col"], u["pos"]["row"])
                     for u in ctx.units if u.get("pos") and u["pos"].get("col") is not None}
        obs_by_sq = {u.get("squadId"): u for u in ctx.obs_units}
        reach = ([ctx.origin] if ctx.origin is not None else []) \
            + [(t["col"], t["row"]) for t in ctx.move_tiles]
        REPAIR_RANGE = 1  # réparation ciblée adjacente (pas de `range` propre observé)
        # dmgPct/maxDmg du passif GalvanicField au niveau PASSIF du caster (maxDmg rarity-scaled par mult).
        cfg = ctx.heal_config(ctx.uid)
        maxdmg = ability_var("GalvanicField", "maxDmg", cfg["passive"], multiplier_pct=cfg["multiplier"])
        dmgpct = ability_var("GalvanicField", "dmgPct", cfg["passive"], multiplier_pct=cfg["multiplier"])
        at = ctx.ability_targets(ctx.uid, _GALVANIC_REPAIR_ID)
        vts = set()
        for u in (at.get("units") or []):
            for a in (u.get("abilities") or []):
                if a.get("abilityId") == _GALVANIC_REPAIR_ID:
                    for t in (a.get("targets") or []):
                        if t.get("kind") == "unit" and t.get("targetId") is not None:
                            vts.add(t["targetId"])
        out = []
        for tg in vts:
            tctx = scene.ctx_by_id.get(tg)
            if tctx is None:
                continue   # cible hors combatSnapshot (Attack indisponible) -> pas de candidat bespoke
            ob = obs_by_sq.get(tg) or {}
            hp_max = int(ob.get("hpMax") or 0)
            hp_cur = int(ob.get("hp") or 0)
            arm_max = int(ob.get("armorMax") or 0)
            arm_cur = int(ob.get("armor") or 0)
            # M = min(round(Attack_INITIALE cible × dmgPct/100), maxDmg)
            att = tctx.get_stat(StatType.ATTACK, StatPart.INITIAL)
            raw = int(round(att * (dmgpct or 0) / 100.0))
            M = raw if maxdmg is None else min(raw, maxdmg)
            rp = predict_repair_effective(M, hp_cur, hp_max, arm_cur, arm_max)  # fill = min(M, manquant_i)
            repaired = repair_utility(rp.fill_hp, hp_max, rp.fill_armor, arm_max, is_boss=False)
            custom = (M / (hp_max + 1) * 50.0) if playbooks._has_valid_targets(ctx, tg) else 0.0
            pred = repaired + custom
            if ctx.debug:
                print(f"    [dbg galv u{ctx.uid}->{tg}] vis={ob.get('visualId')} hp={hp_cur}/{hp_max} "
                      f"attInit={att} dmgPct={dmgpct} maxDmg={maxdmg} M={M} fillHp={rp.fill_hp} "
                      f"repaired={repaired:.3f} custom={custom:.3f} pred={pred:.3f}", file=sys.stderr)
            if pred <= 0:
                continue   # ShouldExecute : util totale > 0
            tpos = pos_by_id.get(tg)
            for T in reach:
                if tg != ctx.uid and (tpos is None or hexgeo.distance(T, tpos) > REPAIR_RANGE):
                    continue   # cible hors portée depuis T (self = depuis toute tuile)
                out.append({"target": tg, "ability": _GALVANIC_REPAIR_ID,
                            "to": (T if T != ctx.origin else None),
                            "pred": pred, "full": pred + tile_utility(ctx, T)})
        return out

    def _bespoke_candidates(self, ctx) -> list:
        """Playbooks Comparable BESPOKE self-cast (#82 : BloodChalice/MomentShackle) — chacun a son
        scoring PROPRE (override `EvaluateInternal`, PAS `HEAL_PLAYBOOK.score`). Dispatch par ID d'ability
        présente + `usable` (identification par id, PAS `"Heal" in name` : leur nom n'a pas "Heal")."""
        me_abis = {ab.get("id"): ab for ab in ((ctx.me or {}).get("abilities") or [])}
        out = []
        for aid, pb in BESPOKE_SELFCAST.items():
            ab = me_abis.get(aid)
            if ab is None or ab.get("usable") is False:
                continue
            out += pb.generate_candidates(ctx)
        return out

    def generate(self, ctx) -> dict | None:
        cands: list = []  # {target, ability, to:(c,r)|None, pred, full}
        best = self._best_attack(ctx)
        if best and best[0] > 0:   # best[0] = u (dégât) > 0 -> ShouldExecute
            cands.append({"target": best[2], "ability": best[3], "to": best[4],
                          "pred": best[0], "full": best[1]})   # full = u_full (dégât + Tile7)
        cands += self._heal_candidates(ctx)
        cands += self._repair_candidates(ctx)             # RepairPlaybook générique (id 28)
        cands += self._repair_galvanic_candidates(ctx)    # #85 : Repair_GalvanicField bespoke (id 1119)
        cands += self._bespoke_candidates(ctx)   # #82 : BloodChalice/MomentShackle
        # (Les NonComparable sont traitées par le générateur précédent — cf. InitAbilityTypeLists.)
        if ctx.debug and cands:
            for c in sorted(cands, key=lambda c: -c["full"])[:8]:
                print(f"    [dbg cand u{ctx.uid}] tgt={c.get('target')} ab={c.get('ability')} "
                      f"to={c.get('to')} pred={round(c.get('pred') or 0,3)} "
                      f"tile_term={round((c.get('full') or 0)-(c.get('pred') or 0),3)} "
                      f"full={round(c.get('full') or 0,3)}", file=sys.stderr)
        if not cands:
            return None
        # `Bucket.ChooseAction` : argmax `full` (tie-break id de cible croissant = -target).
        bucket = Bucket()
        for c in cands:
            bucket.add_action(Action(key=(c["full"], -(c.get("target") or 0)),
                                     payload={"kind": "ability", "target": c["target"],
                                              "ability": c["ability"], "to": c["to"],
                                              "util": c["pred"]}))
        return bucket.choose_action()


class MovementActionGenerator(ActionGenerator):
    """Générateur d'approche pure (`MovementActionGenerator`, EN DERNIER dans la liste). Ne fire que
    si aucun tier d'ability n'a produit d'action légale. Scoring `MovementSuggestion` porté
    (`move.best_move_faithful` = MinDist chemin + MaxDist + situationnels). Renvoie TOUJOURS une
    action (fallback terminal du tactic)."""

    def generate(self, ctx) -> dict | None:
        if not ctx.move_tiles or not ctx.enemies:
            return {"kind": "move", "to": None}
        move_to, move_util = move.best_move_faithful(
            ctx.move_tiles, ctx.elev_by_pos, ctx.epos, ctx.wt,
            pathdist_by_pos=ctx.pathdist_by_pos,
            is_temporary_by_pos=ctx.is_temporary_by_pos, effects_by_pos=ctx.effects_by_pos)
        return {"kind": "move", "to": move_to, "util": move_util}
