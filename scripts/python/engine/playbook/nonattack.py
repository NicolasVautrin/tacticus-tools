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

- `NonAttackComparablePlaybook` — regime « Comparable hors `attackPlans` » :
  `u = custom + CalculateUtilityFromPredictions(MakeDamagePredictions(...))`, gate `should_execute`
  (defaut `True`, mirror du slot +0x328), `u_full = u + tile_utility(tuile)`. La base rend une liste
  de predictions VIDE (le cas des abilities sans `damageProfile`, ex. Chronometron) — le terme de
  prediction y est donc nul, exactement comme cote natif ; un membre qui OVERRIDE
  `MakeDamagePredictions` (1100 SorcerousFacade) le voit sommé, comme `CalculateActionUtility` le fait.

  ⚠ La route ne se limite PAS aux abilities « sans `damageProfile` ». Son critere reel est
  « Comparable **invisible de `_best_attack`** » — ce qui couvre aussi une ability a `damageProfile`
  dont le masque de ciblage refuse toute cible ennemie (VETO #217 : `state_bridge._is_attack_ability`
  rend False, l'ability n'entre jamais dans `attackPlans`). C'est par cette porte, et SANS toucher au
  veto, que 1100 SorcerousFacade (cible ALLIEE) devient candidate.

  ⚠⚠ **« ABSENTE de `ctx.plans` » n'est PAS le bon enonce du critere — mesure #289.** C'est vrai du
  cote OFFLINE (`_plans_for_unit` n'enumere que `_attack_abilities`), mais FAUX en LIVE : `ctx.plans`
  y recopie `decisionView.attackPlans`, qui LISTE 1009 ResurrectionOrb (a `rankCount = 0`, et sur des
  ENNEMIS uniquement, alors que la cible que le natif retient est le CASTER). Ce qui reste vrai dans
  les DEUX regimes, et donc ce qu'il faut verifier, c'est que `_best_attack` ne peut pas la rendre :
  `make_damage_predictions` rend `[]` -> `calculate_action_utility` rend `None` -> l'action n'existe
  pas. Garde : `test_resurrection_orb_decision_live.py::test_best_attack_can_never_yield_the_orb`.
- `nonattack_candidates(ctx)` — mirror des deux boucles natives :
  `IdunBattle.AI.ActionGenerators.ActiveAbilityActionGenerator.u003CGenerateActionsu003Ed__7$$MoveNext`
  (ability x tuile) et `...ComparablePlaybook...$$EvaluateInternal` (cible, keep-first STRICT).

Le registre `NONATTACK_PLAYBOOKS` est explicite : seule une ability dont le playbook est PORTE entre
par cette route. Aucune ability n'y arrive « par defaut » — la degradation permissive d'une route
generique (toute non-attaque devenue candidate) serait exactement le trou qu'un entrainement irait
exploiter.
"""
from __future__ import annotations

from .base import NO_ACTION, ComparablePlaybook, tile_utility, register


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

    # `should_execute` (slot de vtable +0x328) vit desormais sur `ComparablePlaybook` (base.py) : les
    # DEUX routes Comparable le consultent, et un corps duplique ici en serait un fork. Le defaut
    # reste `return true` -- la MEME mesure de vtable, cf. l'en-tete du module.

    def should_evaluate(self, ctx, caster_tile, ability_id) -> bool:
        """`IdunBattle.AI.Playbook.BasePlaybook$$ShouldEvaluate(unit, position, possiblePositions)` —
        le slot de vtable **6**, appelé PAR TUILE CANDIDATE (et non une fois par unité).

        Établi sur le corps de
        `IdunBattle.AI.ActionGenerators.ActiveAbilityActionGenerator.u003CGenerateActionsu003Ed__7$$MoveNext` :
        la machine à états ouvre un énumérateur sur les positions (`d__7+0x68`), et à chaque
        `MoveNext` appelle `playbook.<slot 6>(unit, position, d__7+0x30)` avant
        `battleQuery.<slot 0x40>` puis `playbook.Evaluate`. Trois surcharges DISTINCTES de
        `ShouldEvaluate` coexistent — slot 4 `(unit)`, slot 5 `(unit, possiblePositions)`,
        slot 6 `(unit, position, possiblePositions)` — et les deux premières sont appelées UNE fois,
        avant la boucle. Ne pas les confondre : `...InstrumentsOfVengeancePlaybook$$ShouldEvaluate`
        override la surcharge 2-args, `...MartialExemplarPlaybook$$ShouldEvaluate` et
        `...TheLionsWrathPlaybook$$ShouldEvaluate` la 4-args.

        DÉFAUT `True`, et ce n'est PAS le corps de base exact : celui-ci refuse d'abord une position
        posée sur une tuile TEMPORAIRE (`foreach tile in position: if TileExtensions$$IsTemporary
        return false`, sauf si le prédicat de vtable `+0x1d8` l'autorise) puis délègue à la virtuelle
        `+0x1e8`. Aucun membre actuel du registre ne repose sur ce refus, et l'état d'AVANT ce hook
        était « aucun gate du tout » — le défaut permissif ne peut donc rien régresser. Le volet
        `IsTemporary` reste un résidu nommé de `case-27`."""
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

    def targets_tiles(self, ability_id) -> bool:
        """`IdunBattle.Core.Services.TargetingOptions$$get_IsTileTargeting` (= `rules >> 6 & 1`) — le
        SEUL aiguillage tuile du natif, et il est BINAIRE.

        `IdunBattle.Core.Services.TargetingQuery$$GetPossibleTargetsForOptions` le teste UNE fois puis
        appelle `...$$GetTilesInRange` **ou** `...$$GetUnitsInRange` — jamais les deux. Un ensemble de
        cibles natif est donc homogene : tout tuile, ou tout unite/machine. C'est pourquoi
        `eligible_targets` choisit un domaine au lieu de concatener (case-302 §1.1).

        Import LOCAL : `engine.runner.abilities.targeting` tire tout le registre d'abilities, dont
        cette couche n'a pas besoin au chargement."""
        try:
            from ..runner.abilities.targeting import targeting_options_for
            opts = targeting_options_for(ability_id)
        except Exception:
            return False
        return bool(opts is not None and opts.is_tile_targeting)

    def eligible_targets(self, ctx, ability_id) -> list:
        """`IdunBattle.AI.Playbook.BasePlaybook$$GetEligibleTargetsEntities` — l'ensemble des cibles
        que le playbook score. Mirror OFFLINE/LIVE via le seam `ctx.ability_targets` (RPC natif
        `abilityTargets` en live, `state_bridge.ability_targets_offline` sinon), qui rend l'UNION des
        cibles legales sur les tuiles-caster. Le natif, lui, recalcule l'ensemble PAR TUILE
        (`possibleCasterPosition`) : l'union est un SUR-ENSEMBLE, resserre par `is_caster_added`.

        DOMAINE (case-302) : le natif rend une liste d'`IEntity` NON TYPEE — `GetValidTargets` remplit
        `ValidTargets.AllTargets` avec des entites TUILE des que le masque porte `TargetIsTile`, et
        `IdunBattle.AI.Playbook.BasePlaybook$$ShouldEvaluateTarget` (le predicat du `Remove` final) ne
        retire QUE des unites (`IsUnit && CurrentOwnerIsEnvironment`, ou `IsIrrelevantObject`) : une
        entite-tuile n'est **jamais** ecartee. Le filtre `kind == "unit"` d'origine etait donc une
        restriction du PORT, pas du natif — c'est lui qui rendait la route inerte sur 1169 / 1148.

        Le RPC `abilityTargets` n'emet PAS d'`id` sur `kind == "tile"` (contrat mesure :
        `{kind, tile:{col,row}}` seul, `frida/hooks/features/ai-step/rpc-targeting.ts::mapTargets`).
        La resolution passe donc par `ctx.tile_id_by_pos` (RPC `boardGraph`), qui est **le meme id que
        celui attendu par `applyOneAction`** — la cible qu'emet le natif dans son
        `ActiveAbilityMessage`. Une tuile non resolue est OMISE (jamais un id invente)."""
        at = ctx.ability_targets(ctx.uid, ability_id) or {}
        tile_domain = self.targets_tiles(ability_id)
        tid_by_pos = getattr(ctx, "tile_id_by_pos", None) or {}
        out = []
        for u in (at.get("units") or []):
            for a in (u.get("abilities") or []):
                if a.get("abilityId") != ability_id:
                    continue
                for t in (a.get("targets") or []):
                    if tile_domain:
                        if t.get("kind") != "tile":
                            continue
                        tl = t.get("tile") or {}
                        tid = tid_by_pos.get((tl.get("col"), tl.get("row")))
                        if tid is None:
                            continue        # tuile hors boardGraph -> pas d'id emettable
                    elif t.get("kind") == "unit" and t.get("targetId") is not None:
                        tid = int(t["targetId"])
                    else:
                        continue
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
            if not pb.should_evaluate(ctx, T, aid):
                continue                   # slot 6 : ShouldEvaluate(unit, position, positions)
            if not pb.is_caster_added(ctx, T):
                continue                   # GetCasterNotAddedReason != null depuis cette tuile
            for tgt in targets:
                # ORDRE NATIF de `CalculateActionUtility` : custom D'ABORD, puis la somme des
                # predictions, et c'est CETTE somme que `ShouldExecute` recoit en argument.
                u = pb.calculate_custom_utility(ctx, T, tgt, aid)
                if u is NO_ACTION:
                    # Deux des trois sentinelles de `IdunBattle.AI.Utilities.BaseUtility` testees en
                    # tete de `CalculateActionUtility` rendent un `Nullable` VIDE : aucune action pour
                    # ce (tuile, cible). Aucun membre ACTUEL de cette route ne les rend -- le test est
                    # ici pour que les deux routes Comparable traitent le custom a l'IDENTIQUE.
                    continue
                events = pb.make_damage_predictions(ctx, T, tgt, aid)
                if events:                 # liste vide -> terme nul (le cas de tous les membres
                    #                        sans `damageProfile`, ex. Chronometron : no-op exact)
                    u += pb.calculate_utility_from_predictions(ctx, T, tgt, aid, events)[0]
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
