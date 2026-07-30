"""Route des abilities Comparable **SANS PREDICTION** — le verrou 2 de `case-27` (#27 tranche 4b).

## Ce que le natif fait, et ce que le port faisait

`IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateActionUtility`
(RE relue sur `rnca9r7q6c`) :

    u = CalculateCustomUtility(vtable +0x338)(caster, casterPosition, target, abilityOrEffect, possibleTargets)
    if (u == <sentinelle A> || u == <sentinelle B>) return null;          // Fix64? vide
    if (u == <sentinelle C>) return Nullable(<sentinelle C>);
    u += CalculateUtilityFromPredictions(caster, casterPosition, target, abilityOrEffect)
    if ( ShouldExecute(vtable +0x328)(caster, casterPosition.MainTile, target, u) ) {
        u += CalculateCasterPositionUtility(vtable +0x348)(caster, casterPosition, abilityOrEffect)
        u += <service #0x37>.slot5( IdunBattle.AI.Utilities.UtilityAttackCase$$Base(
                                        caster, casterPosition, target, abilityOrEffect) )
        u += CalculateUtilityFromTilePrediction(caster, casterPosition, target, ...)
        return Nullable(u)
    }
    return null;

DEUX faits que ce corps etablit, et qui tiennent tout ce module :

1. **Le terme custom est calcule EN PREMIER et entre dans l'argument de `ShouldExecute`** — il n'est
   pas « ajoute apres coup » a une utilite de degat.
2. **`ShouldExecute` par DEFAUT rend `true`.** Ce n'est pas une deduction : le slot de vtable +0x328
   de `ChronometronPlaybook`, `DrachnyenPlaybook`, `DoomSirenPlaybook` et `ForwardObserversPlaybook`
   pointe tous les quatre sur le MEME corps trivial `return 1` (dont l'unique proprietaire nomme dans
   `methods.tsv` est `UnityEngine.U2D.IK.Solver2D$$DoValidate` — dedup IL2CPP). Les
   `<X>Playbook$$ShouldExecute` NOMMES (`IdunBattle.AI.Playbook.Loki.HealingBalms_HealPlaybook$$ShouldExecute`
   = `utility > Fix64(0)`, `IdunBattle.AI.Playbook.Loki.ArmoriumCherubPlaybook$$ShouldExecute`,
   `IdunBattle.AI.Playbook.Loki.SorcerousFacadePlaybook$$ShouldExecute`) sont des OVERRIDES, pas la base.
   Mesure : `probe_27_4b_chronometron_vtable.py`.

=> **Le natif n'exige NULLE PART une prediction de degat pour generer une action.** Ce qui borne
l'ensemble des actions, c'est le CIBLAGE (`IdunBattle.AI.Playbook.BasePlaybook$$GetEligibleTargetsEntities`,
evalue PAR TUILE candidate), pas l'existence d'un `damageProfile`.

Cote port, la seule route Comparable etait `ComparableAbilityGenerator._best_attack`, alimentee par
`state_bridge._plans_for_unit` -> `_is_attack_ability` (= `constants.damageProfile` present ET
non-NonComparable), et `ComparablePlaybook.calculate_action_utility` commence par
`if not events: return None`. Une ability sans `damageProfile` n'avait donc **aucune route offline** :
ni erreur, ni desaccord de degat — l'action n'existait simplement pas cote moteur. C'est le verrou
qui tenait 1226 / 1053 / 1185 / 1212 (et, pour une autre raison — cible ALLIEE —, 1100).

## Ce que ce module ajoute

Une SECONDE route Comparable, strictement ADDITIVE (elle ne touche ni `_best_attack` ni le gate
`if not events`, qui reste le mirror pratique du regime ATTAQUE) :

- `NonAttackComparablePlaybook` — regime « Comparable sans prediction » : `u = custom`, gate
  `should_execute` (defaut `True`, mirror du slot +0x328), `u_full = u + tile_utility(tuile)`.
- `nonattack_candidates(ctx)` — mirror des deux boucles natives :
  `IdunBattle.AI.ActionGenerators.ActiveAbilityActionGenerator.u003CGenerateActionsu003Ed__7$$MoveNext`
  (ability x tuile) et `...ComparablePlaybook...$$EvaluateInternal` (cible, keep-first STRICT).

Le registre `NONATTACK_PLAYBOOKS` est explicite : seule une ability dont le playbook est PORTE entre
par cette route. Aucune ability n'y arrive « par defaut » — la degradation permissive d'une route
generique (toute non-attaque devenue candidate) serait exactement le trou qu'un entrainement irait
exploiter.
"""
from __future__ import annotations

from .base import ComparablePlaybook, tile_utility, register


class NonAttackComparablePlaybook(ComparablePlaybook):
    """Playbook Comparable dont l'ability ne produit AUCUNE prediction (pas de `damageProfile`).

    `CalculateUtilityFromPredictions` vaut alors 0 : l'utilite d'action se reduit a
    `CalculateCustomUtility + <termes positionnels>`. Les termes positionnels portes sont les memes
    que ceux de la route d'attaque (`tile_utility`, le composite `UtilityAttackCase.Base` reduit a sa
    feuille Tile(7)) — c'est ce qui rend les deux routes COMPARABLES dans le meme `Bucket`.
    `CalculateCasterPositionUtility` (vtable +0x348) et `CalculateUtilityFromTilePrediction` restent
    hors port : leurs corps de BASE sont partages et non nommes, et aucun membre actuel du registre ne
    les override (residu nomme dans `case-27`)."""

    __slots__ = ()

    def make_damage_predictions(self, ctx, caster_tile, target, ability_id):
        """Aucune prediction de degat : l'ability n'a pas de `damageProfile`
        (`IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$MakeDamagePredictions`
        de base rend une liste VIDE quand le profil est absent)."""
        return []

    def should_execute(self, ctx, caster_tile, target, ability_id, utility) -> bool:
        """`ComparablePlaybook<T>.ShouldExecute` — slot de vtable **+0x328**. Corps par DEFAUT =
        `return true` (corps trivial dedupliqué, cf. l'en-tete du module). Un playbook qui override
        (`...HealingBalms_HealPlaybook$$ShouldExecute` = `utility > 0`) redefinit cette methode."""
        return True

    def is_caster_added(self, ctx, caster_tile) -> bool:
        """Mirror de `IdunBattle.Core.Services.TargetingQuery$$GetCasterNotAddedReason == null` pour le
        regime SELF-CAST : quand `TargetingOptions.isSelfCasting` est vrai, le natif appelle
        `GetValidTargets(caster, casterTile, options, true, true)` et, si l'ensemble est VIDE, rend
        `TargetingRuleExtensions.GenericBrokenTargetingRule(0x800)` — le caster n'est alors PAS ajoute
        aux cibles, donc `GetEligibleTargetsEntities` est vide et AUCUNE action n'est generee depuis
        cette tuile.

        Defaut : `True` (aucun refus invente — meme convention permissive que
        `engine.runner.abilities.targeting`). Un playbook self-cast dont le masque porte un predicat de
        portee l'override."""
        return True

    def eligible_targets(self, ctx, ability_id) -> list:
        """`IdunBattle.AI.Playbook.BasePlaybook$$GetEligibleTargetsEntities` — l'ensemble des cibles
        que le playbook score. Mirror OFFLINE/LIVE via le seam `ctx.ability_targets` (RPC natif
        `abilityTargets` en live, `state_bridge.ability_targets_offline` sinon), qui rend l'UNION des
        cibles legales sur les tuiles-caster. Le natif, lui, recalcule l'ensemble PAR TUILE
        (`possibleCasterPosition`) : l'union est un SUR-ENSEMBLE, resserre par `is_caster_added`."""
        at = ctx.ability_targets(ctx.uid, ability_id) or {}
        out = []
        for u in (at.get("units") or []):
            for a in (u.get("abilities") or []):
                if a.get("abilityId") != ability_id:
                    continue
                for t in (a.get("targets") or []):
                    if t.get("kind") == "unit" and t.get("targetId") is not None:
                        tid = int(t["targetId"])
                        if tid not in out:
                            out.append(tid)
        return out


# Registre EXPLICITE : ability_id -> playbook non-attaque. Alimente par `register_nonattack`.
NONATTACK_PLAYBOOKS: dict[int, NonAttackComparablePlaybook] = {}


def register_nonattack(pb: NonAttackComparablePlaybook) -> NonAttackComparablePlaybook:
    """Enregistre le playbook DANS LES DEUX registres : `base.REGISTRY` (dispatch par ability_id, pour
    que `get_playbook_or_default` rende le bon playbook partout) et `NONATTACK_PLAYBOOKS` (la route)."""
    register(pb)
    NONATTACK_PLAYBOOKS[pb.ability_id] = pb
    return pb


def nonattack_candidates(ctx) -> list:
    """Candidats de la route non-attaque — mirror des deux boucles natives.

    `IdunBattle.AI.ActionGenerators.ActiveAbilityActionGenerator.u003CGenerateActionsu003Ed__7$$MoveNext`
    balaie (abilities de l'unite) x (tuiles candidates) et merge chaque `playbook.Evaluate` dans un
    `Bucket` ; `...ComparablePlaybook...$$EvaluateInternal` balaie les cibles a POSITION FIXE et garde
    le premier maximum STRICT (`Fix64.op_GreaterThan`). L'ordre des tuiles est `ctx.reach_nc`
    (= `action_tiles`, ORIGINE EN TETE) — le meme que celui de `_best_attack`, donc le tie-break
    keep-first du `Bucket` final est preserve.

    Renvoie AU PLUS UN candidat par ability (le maximum keep-first sur (tuile, cible)), au format
    consomme par `ComparableAbilityGenerator.generate` : `{target, ability, to, pred, full}`.
    `pred` = utilite HORS terme positionnel (`u`), `full` = `u_action` = ce que le `Bucket` compare."""
    me_abis = {ab.get("id"): ab for ab in ((ctx.me or {}).get("abilities") or [])}
    out: list = []
    for aid, pb in NONATTACK_PLAYBOOKS.items():
        ab = me_abis.get(aid)
        if ab is None or ab.get("usable") is False:
            continue
        targets = pb.eligible_targets(ctx, aid)
        if not targets:
            continue                       # GetEligibleTargetsEntities vide -> aucune action
        best = None                        # (full, u, tile, target)
        for T in (ctx.reach_nc or []):
            if not pb.is_caster_added(ctx, T):
                continue                   # GetCasterNotAddedReason != null depuis cette tuile
            for tgt in targets:
                u = pb.calculate_custom_utility(ctx, T, tgt, aid)
                if not pb.should_execute(ctx, T, tgt, aid, u):
                    continue               # CalculateActionUtility rend un Nullable VIDE
                full = u + tile_utility(ctx, T)
                if best is None or full > best[0]:      # keep-first STRICT
                    best = (full, u, T, tgt)
        if best is None:
            continue
        full, u, T, tgt = best
        out.append({"target": tgt, "ability": aid,
                    "to": (T if T != ctx.origin else None), "pred": u, "full": full})
    return out
