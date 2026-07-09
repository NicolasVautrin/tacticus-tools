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
sont priorité 0 -> seul le générateur #3 (dict[0]) tire côté NC. L'ORDRE inter-tier est exercé par
NovaBoost (tier **1000**) vs NovaShield (tier **-1000**), portées pour tauBossRiptide (roster crafté) :
NovaBoost (util=1) prime sur NovaShield (util>=100) PAR L'ORDRE DES GÉNÉRATEURS (tier 1000 avant -1000),
pas par l'utilité -> preuve que le tier domine l'argmax (cf. noncomparable.py).
"""
from __future__ import annotations

import sys

import hexgeo
import gameconfig as gc
from engine import move
from engine.playbook import noncomparable as playbooks
from engine.playbook import get_playbook_or_default, tile_utility
from engine.playbook.common import NORMAL_ATTACK_PLAYBOOK, HEAL_PLAYBOOK
from engine.predict import repair_utility   # RepairedAmountUtility (repair = analogue non-custom du soin)
from engine.ai.bucket import Action, Bucket


# Abilities REPAIR Comparable (RepairPlaybook @181187c00 / Repair_GalvanicFieldPlaybook @181155b80) —
# identifiees par ID, PAS par `"Repair" in name` (R2 : ce substring captait aussi
# NanoscarabRepairProtocols(1224), NonComparablePlaybook @18114e1f0 -> mauvais routage). ActiveAbilityType :
# SEULS Repair(28) + Repair_GalvanicField(1119) sont Comparable-repair (RepairedAmountUtility instanciee 1x) ;
# 1224 = le seul NonComparable-repair, exclu. (82/84 = IDs inexistants dans l'enum, retires -- validateur.)
_COMPARABLE_REPAIR_IDS: "frozenset[int]" = frozenset({28, 1119})


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
            plan=ctx.plans.get(ctx.uid) or {}, hp_cur_by_id=ctx.hp_cur_by_id,
            elev_by_pos=ctx.elev_by_pos, ability_targets=ctx.ability_targets,
            wt=ctx.wt, is_temporary_by_pos=ctx.is_temporary_by_pos,
            effects_by_pos=ctx.effects_by_pos, obs_units=ctx.obs_units,
            tile_id_by_pos=ctx.tile_id_by_pos, active_levels=ctx.active_ability_levels,
            units=ctx.units, cast_from_tiles=ctx.cast_from_tiles, debug=ctx.debug)
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
                if pair_best is None or u_full > pair_best[0]:
                    pair_best = (u_full, cand["u"], cand["pred"], cand["aoe"], tile, cand["bk"])
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
            for tg in vts:
                tu = unit_by_id.get(tg) or {}
                # gate natif `HasEffect(target, EffectType.TwistedScience_ExtraHp=1355)` sur l'état d'effets
                # STRUCTURÉ (`EffectsState`) — on colle au JEU (HasEffect sur les EffectComponent), PAS à la
                # liste sérialisée `unit["effects"]` de decisionView. Les deux chemins (live/offline) portent
                # cet état via `ctx.scene.eff_state`. Scene absente -> pas d'exclusion (no-op fidèle).
                _eff = getattr(getattr(ctx, "scene", None), "eff_state", None)
                if _eff is not None and _eff.has_effect(tg, effect_type=1355):
                    continue  # cible déjà buffée (TwistedScience_ExtraHp) -> ignorée (inconditionnel)
                ob = hpmax_by_sq.get(tg) or {}
                hp_max = int(ob.get("hpMax") or 0)
                hp_cur = int(ob.get("hp") or 0)
                missing = max(0, hp_max - hp_cur)   # soin effectif SATURÉ = missing
                is_friend = (me is not None and tu.get("team") == me.get("team"))
                faction = _faction(tu.get("visualId"))
                pred = HEAL_PLAYBOOK.score(missing, hp_max, is_friend, is_twisted, faction)
                if ctx.debug:
                    print(f"    [dbg heal u{ctx.uid}->{tg}] vis={tu.get('visualId')} fac={faction} "
                          f"hp={hp_cur}/{hp_max} miss={missing} twisted={is_twisted} pred={pred}",
                          file=sys.stderr)
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
        """Sweep RÉPARATION (tile-swept) via `RepairPlaybook` (Comparable, @181187c00) -> liste
        {target, ability, to, pred, full}. MIROIR de `_heal_candidates` : identification par ID Comparable-
        repair (`_COMPARABLE_REPAIR_IDS` = {28, 1119} = Repair / Repair_GalvanicField ; PAS `"Repair" in
        name` qui captait le NonComparable NanoscarabRepairProtocols(1224)) ; énumération cibles =
        `abilityTargets` ; utilité par cible =
        `repair_utility` (RepairedAmountUtility : `fill_hp/(maxHP+1)×100 + fill_armor/(maxArmor+1)×50`,
        PAS de friendSign — répare ses propres machines) ; gate `ShouldExecute` : pred > 0.

        SIMPLIFICATIONS (1er wiring, notées) : (a) `fill_hp = missing_hp` SATURÉ (repairAmount supposé
        >= manquant, comme `_heal_candidates` avec `missing`) — le repairAmount exact (config d'ability
        via predict_repair_effective) est un raffinement ; (b) terme ARMOR = 0 (armure courante/max non
        exposée dans observeBattle.units → à capturer ; W_armor=50 < W_hp=100, terme secondaire)."""
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
                fill_hp = max(0, hp_max - hp_cur)          # (a) saturation missing ; (b) armor=0
                pred = repair_utility(fill_hp, hp_max, 0, 0, is_boss=False)
                if ctx.debug:
                    print(f"    [dbg repair u{ctx.uid}->{tg}] vis={ob.get('visualId')} "
                          f"hp={hp_cur}/{hp_max} fill={fill_hp} pred={pred}", file=sys.stderr)
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

    def generate(self, ctx) -> dict | None:
        cands: list = []  # {target, ability, to:(c,r)|None, pred, full}
        best = self._best_attack(ctx)
        if best and best[0] > 0:   # best[0] = u (dégât) > 0 -> ShouldExecute
            cands.append({"target": best[2], "ability": best[3], "to": best[4],
                          "pred": best[0], "full": best[1]})   # full = u_full (dégât + Tile7)
        cands += self._heal_candidates(ctx)
        cands += self._repair_candidates(ctx)
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
