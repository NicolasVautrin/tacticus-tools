"""`BaseEffect` — mirror de `IdunBattle.Entities.Effects.BaseEffect` + l'interface effet que les builders
de modifier/prédiction consomment (gqfc5mff6c).

Chaque effet du jeu = **UNE sous-classe** (1:1, le namespace natif = le module Python : `Loki` → loki.py).
Une sous-classe N'OVERRIDE QUE les méthodes qu'elle implémente réellement (lues dans ghidra, VA citée) ;
tout le reste = no-op par défaut (l'effet ne contribue rien / est actif tant que présent). C'est la
réplique fidèle du modèle natif « 1 classe par effet, interface uniforme » (doc §17.3/§17.13).

Méthodes d'interface (chacune = sa jumelle native) :
  • create_effect_damage_bonus_for_attack → `EffectBonus | None`  (CreateEffectDamageBonusForAttack)
  • create_effect_hits_bonus_for_attack   → `EffectBonus | None`  (CreateEffectHitsBonusForAttack)
  • get_armor_penetration                 → `int | None`          (IgnoreArmor, ex. KanOpener ConfigVar 0x40)
  • is_active(unit_state)                  → bool                  (CreateActiveCondition)
  • entity_is_immune_to_effect(traits)     → bool                  (EntityIsImmuneToEffect + get_CanBeImmuneTo)
Cycle de vie (porté depuis les `*Ability.CreateTrigger` de pose/retrait) : `removed_after_attack`,
`one_shot`, `expired`.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from ...services.effect_bonus import EffectBonus
from ..effect_type import EffectType
# FEUILLE PURE (n'importe rien de `engine.*`), et c'est ce qui rend cet import possible AU NIVEAU
# MODULE : l'enum vivait dans `runner/operations/remove_effects.py`, dont la cascade traverse ce
# fichier meme (177 modules charges) -- l'importer de la aurait ferme un cycle. Deplace par #1088,
# voie (1) de la doctrine (supprimer l'arete), pas voie (3) (differer).
from ..kill_unit_step import KillUnitStep
from ..traits.unit_trait import UnitTrait, has_trait

# Sentinelle de durée d'un sous-effet : MÊME nombre de tours que le parent (mirror natif
# `AddSubEffectWithSameTurns`). Distinct de None (= permanent, lié au cycle de vie du parent).
SAME_TURNS = "same"


# ── nature du coup : mirror des DEUX prédicats natifs (#106) ────────────────────────────────────
# `IdunBattle.Core.Services.BattleQuery$$IsMeleeAttack` / `IdunBattle.Core.Services.BattleQuery$$IsRangedAttack`
# (consommés par `IdunBattle.Entities.Triggers.IsMeleeAttackAbilityTrigger$$ShouldTrigger` /
# `IdunBattle.Entities.Triggers.IsRangedAttackAbilityTrigger$$ShouldTrigger`, eux-mêmes les nœuds
# `IdunBattleLogic.Entities.DSLTriggers$$IsMeleeAttack` / `$$IsRangedAttack` des `CreateEffectDamageBonusForAttack`).
# Les DEUX partent de `GetAbilityAttackRangeType(abilityDuCoup)` et rendent un **bool**, jamais un tri-état :
#   • `Nullable<AbilityOrEffect>` VIDE (pas d'ability dans le contexte) → `GetAbilityAttackRangeType` = 0
#     → melee=FALSE **et** ranged=FALSE ;
#   • 0 (None)   → melee=FALSE, ranged=FALSE  (ni l'un ni l'autre — les deux gates se taisent) ;
#   • 1 (Melee)  → melee=TRUE,  ranged=FALSE ;
#   • 2 (Ranged) → melee=FALSE, ranged=TRUE  ;
#   • 3 (Both)   → `HasFlag(unit, 0x15)` ? (melee=FALSE, ranged=TRUE) : `AreUnitsInMelee(attPos, tgtPos)`
#                  (position-based, melee = AreUnitsInMelee, ranged = son complément).
# ⇒ le natif n'a PAS d'état « inconnu », et surtout : quand la nature n'est PAS déterminée, il ne se rabat
# JAMAIS sur mêlée. Côté port, `is_ranged=None` (nature non threadée par la façade appelante) doit donc
# faire TAIRE les DEUX familles de gates, comme l'axe COUPS (`att_ctx["is_melee"] is not True`) et les
# auras (`ctx["is_melee"]`) le font déjà. Le défaut FALSY de `if is_ranged:` faisait l'inverse sur l'axe
# DÉGÂT (contribution mêlée-only appliquée à un coup de nature inconnue) — c'était le fork du cas #106.
def is_melee_attack(is_ranged: "bool | None") -> bool:
    """`BattleQuery$$IsMeleeAttack` : VRAI seulement si la nature du coup est PROUVÉE mêlée."""
    return is_ranged is False


def is_ranged_attack(is_ranged: "bool | None") -> bool:
    """`BattleQuery$$IsRangedAttack` : VRAI seulement si la nature du coup est PROUVÉE distance."""
    return is_ranged is True


def is_not_charging(att_ctx) -> bool:
    """Gate `IsCharging` du canal modifier : le coup est-il PROUVÉ hors-charge (case-r32) ?

    Le prédicat natif est `IdunBattle.Core.Services.BattleQuery$$IsCharging(caster, target)` =
    `AreEntitiesAdjacent(caster,target) && UnitComponent.ChargedUnitIds@+0x190.Contains(target.Id)`.
    Il est évalué UNE fois par coup et threadé dans `att_ctx["is_charging"]` par le contexte
    d'attaque (combat : `runner.damage_model.battle_query_is_charging` ; prédiction : le mirror
    d'`UpdateCharging` sur la tuile CANDIDATE). Foyer UNIQUE du gate — les trois effets qui portent
    ce nœud (`AvalancheOfMuscle_ExtraDamage` 1025, `FeederTendrils_ExtraDamage` 1197,
    `BlackRage_ExtraDamage` 1343) l'appellent, aucun ne re-dérive la condition.

    ⚠ Ce n'est PAS `HasFlag(UnitFlag.Moved)` — les deux prédicats existent nativement et ne se
    recouvrent pas : `UpdateCharging` n'inscrit que les unités devenues **NOUVELLEMENT adjacentes**
    pendant le pas, donc un caster qui bouge vers une cible DÉJÀ adjacente a `Moved` VRAI et
    `IsCharging` FAUX. C'est l'ancien proxy `has_moved`, qui sur-accordait (mesuré +599/coup sur
    `astraBullgryn` L50 mult 180 %, cf. `test_ischarging_extra_damage_live.py`).

    Tri-état, aligné sur `is_melee_attack`/`is_ranged_attack` en INTENTION mais pas en polarité : la
    clé ABSENTE (contexte d'attaque sans cible — prédictions internes type FinalJustice) laisse
    passer, comme le faisait `has_moved=None`. Seul un `False` EXPLICITE ferme le gate."""
    return (att_ctx or {}).get("is_charging") is False


def target_is_on_fire_tile(att_ctx) -> bool:
    """`EntitiesWithAnyEffect( Tiles(Target@DSLSelectors+0x60), EffectType.Fire = 5,
    effectTarget = 6 )` -- « la MAIN TILE de la cible du coup porte-t-elle l'effet `Fire` ? »

    FOYER UNIQUE du predicat cote canal MODIFIER. Il etait ecrit DEUX fois dans
    `loki/extra_damage_aura.py` (`APsychicStalkEffect$$GetTargetIsOnFireTileCondition` et son
    jumeau `1216`) ; l'ecrire une TROISIEME fois pour `VitarusEffect` (dont la condition natif est
    `Any(Tiles(Target@+0x60), HasEffect(<element>, Fire, onlyActive: false, EffectTargetType.Both
    = 6))` -- meme question, autre noeud) aurait fait un fork. `Tiles` =
    `IdunBattle.Entities.Selectors.UnitsMainTilesSelector` -> UNE tuile, pas l'empreinte complete.

    Contexte : `t_pos` (position de la cible) + `tile_effects_by_pos` (`{(col,row): [noms]}`),
    tous deux poses par `runner/damage_model.py::attacker_modifiers` et par la face PREDICTION.
    Canal ABSENT -> False : le natif ne devine pas non plus, et « present != applique »."""
    c = att_ctx or {}
    tfx, tp = c.get("tile_effects_by_pos"), c.get("t_pos")
    if tfx is None or tp is None:
        return False
    return EffectType.Fire.name in set((tfx or {}).get(tuple(tp)) or ())


def relic_ability_state(att_ctx, relic_ability: str):
    """Le couple `(niveau, multiplicateur)` de l'ability TERTIAIRE de l'ATTAQUANT quand c'est bien
    `relic_ability` qui est equipee -- sinon `(None, None)`.

    POURQUOI CE CANAL EXISTE (#1005, MESURE, pas suppose). Un effet de RELIQUE resout son
    `ConfigVar` contre l'`AbilityState` que l'`AddEffect` natif lui a passe, c.-a-d.
    `DSLSelectors$$AbilityState(Owner, <l'ability courante>)` = l'etat **TERTIAIRE**. Or ce couple
    n'est PAS celui des passifs : RPC `unitAbilityStates` sur `bloodMephiston` porteur de
    `Vitarus` -- `TriggeredAbilityComponent` `raw = [1470, .., level = 1, mult = 100, ..,
    hierarchie = 3, ..]`, tandis que ses passifs portent `level = 50, mult = 180`. Cote port,
    `EffectFactory.create` recoit le couple PASSIF de l'unite porteuse (canal de seed
    `decisionView.effects` comme voie offline), donc `Vitarus.extraDmg` serait lu a l'indice
    clampe (`extraDmg[10] = 728`) au lieu d'`extraDmg[1] = 490` : **+238 par coup, en silence**.

    `att_ctx` porte les trois cles depuis `runner/damage_model.py::attacker_modifiers` (canal
    ATTAQUANT, le seul qu'empruntent les deux effets de relique portes). Cles absentes ou relique
    differente -> `(None, None)`, et l'appelant retombe sur ses champs d'effet -- degradation
    NOMMEE, jamais un niveau devine."""
    c = att_ctx or {}
    if not relic_ability or c.get("att_tertiary_ability") != relic_ability:
        return (None, None)
    return (c.get("att_tertiary_level"), c.get("att_tertiary_mult"))


def is_charging_attack(att_ctx) -> bool:
    """Forme POSITIVE du même gate : le coup est-il PROUVÉ en charge (case-ischarging-hits) ?

    Même prédicat, même clé `att_ctx["is_charging"]`, même foyer `battle_query.is_charging` —
    seule la polarité de la dégradation change, et c'est VOULU :

    * `is_not_charging` (ci-dessus) sert des consommateurs qui EXISTAIENT avant le gate
      (`AvalancheOfMuscle`, `FeederTendrils`) ; leur contexte historique n'avait pas la clé et
      laissait passer — le retrofit a conservé cette polarité pour ne rien changer là où le
      contexte n'est pas threadé ;
    * `is_charging_attack` sert les consommateurs NOUVEAUX, où « contexte inconnu » doit rendre
      **aucune contribution** (« présent ≠ appliqué », la dégradation par défaut du port). Sur ce
      canal c'est aussi le plus FIDÈLE : `BattleQuery$$IsCharging` commence par
      `AreEntitiesAdjacent(caster, target)` — sans positions, le natif rend FAUX, jamais VRAI.

    Aligné en polarité sur `is_melee_attack` / `is_ranged_attack` : VRAI seulement si PROUVÉ."""
    return (att_ctx or {}).get("is_charging") is True


def owner_is_caster(att_ctx) -> bool:
    """Noeud DSL `IdunBattleLogic.Entities.DSLTriggers$$get_OwnerIsCaster` = `AreEqual(
    Owner@DSLSelectors+0x30, Caster@DSLSelectors+0x48)` -- foyer UNIQUE du couple de cles
    `att_ctx["owner_id"]` / `att_ctx["att_id"]` sur les canaux CRIT (#589-r1-r1).

    « Le PORTEUR de cet effet est-il l'attaquant du coup ? ». `owner_id` est pose PAR PORTEUR par
    les agregateurs (`crit_chance_bonus_from_effects` / `crit_damage_bonus_from_effects`), mirror
    de l'ecriture `AbilityEntities+0x18 (Owner) <- le porteur de l'effet` que les deux canaux
    natifs font a chaque iteration de leur boucle sur les effets du board.

    Ce noeud etait RENDU par le canal tant que le balayage se limitait aux effets de l'attaquant ;
    il a MIGRE dans les classes qui le portent quand le balayage s'est aligne sur l'univers natif
    (meme geste et meme cause que `1117` lors de `case-366-r1-blockhits-purgeresponse`, sur l'axe
    COUPS). Sans lui, un porteur SPECTATEUR bufferait un tiers.

    Identite NON PROUVEE (l'une des deux cles absente) => FAUX, jamais permissif -- meme idiome que
    `GravitonRifle_ExtraPierceEffect.create_effect_piercing_bonus_for_attack` et que
    `InescapableAccuracyOverrideHitsEffect.block_hits_reduction`."""
    c = att_ctx or {}
    oid, aid = c.get("owner_id"), c.get("att_id")
    return oid is not None and aid is not None and oid == aid


def is_at_range(att_pos, t_pos, expected: int) -> bool:
    """Noeud DSL `IdunBattleLogic.Entities.DSLTriggers$$IsAtRange(sel1, sel2, formule)` -- foyer
    UNIQUE du gate de DISTANCE des effets, partage par les deux faces de
    `SpecialIssueCombiMelta` (1563 / 1564).

    ⚠ C'EST UNE EGALITE, PAS UN `<=`, et ca ne se devine pas. Corps ENTIER de
    `IdunBattle.Entities.Triggers.IsAtRangeAbilityTrigger$$ShouldTrigger` (LU sur `rnca9r7q6c`) :

        attendu = <formule this+0x28>.Calculate(entities)                 # slot 1
        a       = <this+0x18>.Select(entities)                            # slot 10
        b       = <this+0x20>.Select(entities)
        d       = query.<slot 0x6f = GetDistance>(a, b)
        return d == attendu                                               # `(int)uVar15 == iVar13`

    et la formule des call-sites de 1563/1564 n'est PAS un `Get(n)` construit sur place : c'est un
    CHAMP PRE-CONSTRUIT de l'instance `DSLFormulas`, pose par
    `IdunBattleLogic.Entities.DSLFormulas$$.ctor` -- `+0x18 = Const(0)`, `+0x20 = Const(1)`,
    `+0x28 = Const(2)`, `+0x30 = Const(100)`, `+0x38 = Const(-1)`. Lire `+0x20`/`+0x28` comme des
    offsets opaques aurait fait rater les portees 1 et 2.

    La distance est la distance HEXAGONALE (`IdunBattle.Core.Services.MovementQuery$$GetDistance` =
    MIN sur les paires de pieds, `IdunBattle.Utils.Hex.CubeCoordinate$$Distance`, aucun
    pathfinding). Cote port, `hexgeo.distance` sur les MAIN TILES -- meme approximation MULTI-HEX
    que la face DECISION (residu `#419-r1-tr11-r1`, non confronte : aucune MoW au montage).

    POSITION MANQUANTE -> **FAUX**, jamais permissif : un gate de distance inevaluable ne peut pas
    etre suppose vrai (meme convention que `is_charging_attack` / `owner_is_caster`)."""
    if att_pos is None or t_pos is None:
        return False
    import hexgeo
    return hexgeo.distance(tuple(att_pos), tuple(t_pos)) == int(expected)


def min_distance_at_most(a_pos, b_pos, max_distance: int) -> bool:
    """Noeud composite `NOT AmountIsGreater(DSLFormulas$$MinDistance(a, b), Direct(n))` -- foyer
    UNIQUE du gate de PORTEE `<=` des effets (#952). A ne pas confondre avec `is_at_range` juste
    au-dessus, qui mirroire `IsAtRange` et est une EGALITE.

    DEUX lectures, faites et non deduites :

    * `IdunBattleLogic.Entities.DSLFormulas$$MinDistance(a, b)` construit une formule dont le
      `Calculate` passe par `IdunBattle.Core.Services.BattleQuery$$GetMinDistance(tilesA, tilesB)` :
      un MIN de `BattleQuery$$GetDistance` sur le PRODUIT des deux jeux de tuiles -- distance
      HEXAGONALE, aucun pathfinding. Cote port, `hexgeo.distance` sur les MAIN TILES : meme
      approximation multi-hex que `is_at_range` (residu `#419-r1-tr11-r1`).
    * `IdunBattle.Entities.Conditions.AmountIsGreaterAbilityTrigger$$ShouldTrigger` finit
      litteralement sur `return minAmount < amount` -- comparaison STRICTE. Le `op_LogicalNot` du
      call-site donne donc `d <= n`, borne INCLUSE. C'est aussi le garde-fou contre le mislabel ICF
      signale par `battle_query.py` (un `.ctor` nomme `AmountIsGreater...` qui est en realite
      `AmountIsEqualOrGreater`) : ici c'est le CORPS du trigger qui a ete relu, pas son nom.

    POSITION MANQUANTE -> **FAUX**, jamais permissif (meme convention que `is_at_range`).

    ⚠ ECART NOMME avec le natif dans UN seul regime : `GetMinDistance` seede a `int.MaxValue` et
    rend **-1** quand aucune paire de tuiles n'existe (selecteur VIDE), ce qui fait passer
    `NOT (-1 > n)` a VRAI. Ce regime n'a pas de substrat cote port (une unite sans position n'est
    pas placee), et le rendre VRAI ici ouvrirait un gate sur une inconnue -- on ferme."""
    if a_pos is None or b_pos is None:
        return False
    import hexgeo
    return hexgeo.distance(tuple(a_pos), tuple(b_pos)) <= int(max_distance)


def tiles_moved_this_turn(att_ctx) -> "int | None":
    """Nœud DSL `IdunBattleLogic.Entities.DSLFormulas$$TilesMovedThisTurn(Self)` — foyer UNIQUE du
    canal `att_ctx["tiles_moved_this_turn"]` (case-322).

    Le natif est `IdunBattle.Entities.Formulas.TilesMovedThisTurnFormula$$Calculate`, qui rend le
    champ `+0xf0` de l'**`ActorStatisticsComponent`** du porteur (case-322-r1 : le composant est
    celui que `IdunBattle.Operations.StartTurnOperation$$ResetUnit` passe à
    `ActorStatisticsComponent$$ResetAttacksReceivedThisTurn` — la fiche #322 écrivait
    `UnitComponent`, c'était une erreur d'étiquette, sans effet sur le port). Ce champ n'est écrit
    QUE par `IdunBattle.Entities.UnitExtensions$$RecordTilesMoved`, en `+=` (et no-op si le compte
    est `< 1`), et `IdunBattle.Operations.MoveUnitOperation$$Execute` l'alimente sur les DEUX
    branches — y compris la branche SIMULATION (`state.IsSimulating`), où le corps de
    `MoveUnitOperation$$GetNumTilesMovedForSimulation` est inliné :

        num = 0
        if (HasTriggeredAbility(unit, 0x5f9 ModifiedExoarmour) || HasTriggeredAbility(unit, 0x4de))
            CalculatePaths(unit, movementStart, previous, startTile, endTile, options,
                           out path, out connectedPath)
            num = BattleQuery.GetNumTilesMoved(connectedPath)      // = Count - 1
        RecordTilesMoved(unit, num, state)                          // +0xec ET +0xf0  +=  num

    D'où la valeur que voit une PRÉDICTION à une tuile candidate : **le compteur réel du tour PLUS
    le nombre de tuiles du pas simulé** (le `+=`), et 0 pour toute unité qui ne porte NI 0x5f9 NI
    0x4de (le natif ne calcule alors aucun chemin).

    DEUX faces alimentent désormais cette clé, et aucune ne devine :
      * DÉCISION — `playbook/prediction/_shared.py::prediction_tiles_moved_this_turn` (compteur réel
        + tuiles du pas simulé) ;
      * COMBAT (case-322-r1) — `runner/damage_model.py::attacker_modifiers`, qui lit le compteur
        RÉEL de l'ECS (`runner/components.py::unit_tiles_moved_this_turn`), tenu par
        `MoveUnitOperation` à chaque pas joué. La clé y est TOUJOURS posée.

    Tri-état : clé ABSENTE -> `None` = « non threadé », et les consommateurs rendent AUCUNE
    contribution (« présent != appliqué »). Ce n'est PAS `0` : un zéro affirmerait « l'unité n'a pas
    bougé », ce que le contexte ne dit pas. Ne reste `None` que pour les appelants HORS des deux
    faces ci-dessus (prédictions internes sans contexte d'attaque)."""
    v = (att_ctx or {}).get("tiles_moved_this_turn")
    return None if v is None else int(v)


def is_turn_of_owner(att_ctx) -> "bool | None":
    """Noeud DSL `IdunBattleLogic.Entities.DSLTriggers$$IsTurnOf(Owner@0x148)` — foyer UNIQUE du
    canal `att_ctx["is_turn_of_owner"]` (case-366-r1, `1110 FireAndReposition_ReduceDmg`).

    Le natif est `IdunBattle.Entities.Triggers.IsTurnOfUnitTrigger$$ShouldTrigger` : pour chaque
    entite rendue par le selecteur il compare `OwnerComponent.CurrentPlayerEntityId` a
    `TurnComponent.CurrentPlayerId`. Sur le canal DEFENSEUR (`CreateEffectDamageMalusForDefense`),
    `Owner@0x148` est le PORTEUR de l'effet, c'est-a-dire la CIBLE du coup -- donc la question posee
    est « est-ce le tour du joueur qui possede le defenseur ? ».

    C'est mot pour mot `IdunBattle.Entities.UnitExtensions$$IsControlledByCurrentPlayer(unit, state)`
    (meme paire de champs, meme egalite), ce que les DEUX faces LISENT au lieu de le deriver :
      * DECISION -- `decisionView.units[].ctrl`, ou le hook INVOQUE la methode native
        (`projection.ts`, `isCtrlByCurMi`), relaye par `Scene.is_turn_of(uid)` ;
      * COMBAT -- `OwnerComponent.player == State.current_player_id` (mirror
        `StateExtensions.GetCurrentPlayerId`), pose par `damage_model.defender_modifiers`.

    Tri-etat : cle ABSENTE -> `None` = « non threade ». Les consommateurs d'un gate `NOT IsTurnOf`
    n'appliquent alors RIEN (« present != applique ») -- meme polarite que `is_charging_attack`.

    Le port du noeud generique (`entities/triggers.py::IsTurnOf`) agrege par `all(...)` depuis
    #366-r1-turnof (`docs/rl/case-366-r1-turnof-all.md`) -- le natif sort FAUX des qu'UNE entite
    selectionnee n'appartient pas au joueur courant, set vide -> VRAI. Sans effet sur CE foyer :
    `Owner` est un singleton, et les deux agregations coincident sur un set d'un element."""
    v = (att_ctx or {}).get("is_turn_of_owner")
    return None if v is None else bool(v)


@dataclass
class SubEffectSpec:
    """Sous-effet (enfant) qu'un effet COMPOSITE spawne quand il est appliqué (mirror des
    `Add*SubEffect`/`AddEffect` de `<Effect>.ApplyInternal`). `turns` :
      • `SAME_TURNS` → même durée que le parent (`AddSubEffectWithSameTurns`)
      • `0` ou None  → permanent, lié au parent (rem=0 natif ; reverté à l'expiration du parent)
      • `N>0`        → N tours."""
    effect_type: int
    name: str
    turns: "int | str | None" = None
    # L'enfant est-il posé sur l'entité BONDÉE du parent au lieu de son porteur ?
    #
    # `AddSubEffectWithSameTurns(this, effect, <cible>, EffectBuilder(ctx, <lambda>), <type>)` prend
    # la CIBLE en 3e argument, et rien n'oblige que ce soit le porteur du parent :
    # `IdunBattle.Entities.Effects.Loki.HolyDuel_TauntEffect$$ApplyInternal` passe `target` (le
    # porteur) pour son PREMIER sous-effet et `<entités>.GetEntity(ABondEffect.BondedEntityId(this,
    # effect))` pour les TROIS autres — le duel est symétrique, chacun des deux duellistes porte le
    # composite `Taunted` de l'autre.
    #
    # Le BOND de l'enfant bascule AVEC le porteur, jamais séparément : les quatre lambdas du
    # `<>c__DisplayClass9_0` appellent toutes `AddEffectBehaviour$$DefaultBondEffectBuilder`, mais
    # `b__0` (l'enfant posé sur le porteur) lui passe `ctx.<+0x18>` = le bondé du parent, tandis que
    # `b__1`/`b__2`/`b__3` (les enfants posés sur le bondé) lui passent `ctx.<+0x20>.Id` = le
    # porteur du parent. UN seul champ suffit donc à décrire les deux, et il ne peut pas décrire
    # une combinaison que le natif n'écrit pas.
    #
    # `False` (défaut) = le comportement de TOUS les autres composites du port (`TauntedEffect`,
    # `StunnedEffect`) : enfant sur le porteur, bond hérité du parent.
    on_bonded_entity: bool = False


@dataclass
class BaseEffect:
    """Effet matérialisé : identité (seedée depuis la capture one-shot) + état de cycle de vie mutable."""
    # ── #437-r1-r1-r1 : ACCUMULATEUR NATIF de chaque canal de dégât ─────────────────────────────
    # `IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers` applique UN
    # `Fix64.Round` par accumulateur non nul (`attackModifiers`, `defenseModifiers`) : la face d'une
    # contribution est donc OBSERVABLE, et elle vaut ±1 sur la borne.
    #
    # Elle est fixée par le SLOT VIRTUEL par lequel la contribution sort, jamais par le porteur :
    #   * `CreateEffectDamageBonusForAttack` (slot 0x16), ou `CreateDamageModifier` derrière le
    #     forwarder `IdunBattle.Entities.Effects.DamageModifierAbilityEffect$$
    #     CreateEffectDamageBonusForAttack` (lu : recopie nue du `Nullable<EffectBonus>` du slot
    #     virtuel de la sous-classe)                                   -> "attacker" ;
    #   * `CreateEffectDamageMalusForDefense` (slot 0x1a), ou `CreateDamageDefenseModifier` derrière
    #     le forwarder de `ADamageDefenseModifierAbilityEffect`         -> "defender".
    # Les DEUX builders natifs énumèrent le MÊME dictionnaire d'effets de l'état ; le trigger
    # (`OwnerIsTarget` / `OwnerIsActor`) choisit QUELLE unité déclenche, jamais l'accumulateur.
    #
    # Ces cinq attributs disent, POUR CHAQUE CANAL DU PORT, l'accumulateur d'arrivée. Le défaut est
    # celui du canal ; une classe le SURCHARGE quand le natif l'a rangée dans l'autre famille — et
    # cela arrive dans les DEUX SENS (`Terrifying_ExtraDefense` porté par la cible mais versé côté
    # attaquant ; `Stunned_DamageModifier` porté par l'attaquant mais versé côté défenseur).
    # La table complète (59 classes, dérivée des tables de symboles, deux sources concordantes) et
    # sa garde : `scripts/python/probe_437r1r1r1_effect_face_table.py`.
    ATTACK_BONUS_NATIVE_FACE = "attacker"
    DEFENSE_MALUS_NATIVE_FACE = "defender"
    AURA_ATTACK_BONUS_NATIVE_FACE = "attacker"
    AURA_ATTACK_MALUS_NATIVE_FACE = "attacker"
    AURA_DEFENSE_MALUS_NATIVE_FACE = "defender"

    name: str
    effect_type: int | None = None
    level: int | None = None                 # niveau de STACK capté (decisionView.effects[].level) — pour
                                             # les effets à empilement (ex. Contagions) ; ≠ niveau d'ability
    # Niveau de l'ABILITY source sur l'unité (active/passive/tertiary), qui indexe les `variables[level]`
    # d'ability (≠ stack `level`). Ex. PowerTrip.armorIgnored indexé par PassiveAbilityLevel (=50), PAS
    # par le stack level (=1). Seedé depuis l'unité ; None → fallback sur `level`. §17.21.
    ability_level: int | None = None
    # Niveau de l'ability ACTIVE de l'unité (unitConfig.activeAbilityLevel) — pour les stat-mods dont la
    # source est une ability ACTIVE (ex. StandVigil) : indexe `variables[level]` sur l'active, pas la
    # passive. `ability_level` reste le niveau passif (défaut). Un effet choisit le slot pertinent.
    active_ability_level: int | None = None
    remaining_turns: int | None = None      # None = permanent/aura ; sinon décrémenté en fin de tour
    source: int | None = None                # `EffectComponent` SourceUnit @+0x10 (qui a posé l'effet)
    # `EffectComponent` Target @+0x14 — l'unité QUI PORTE l'effet (peuplé à la MATÉRIALISATION,
    # AddEffectOperation/AddNewEffect ; les effets seedés one-shot le laissent None, l'unité porteuse
    # = la clé `EffectsState.by_unit`). Distinct de `source` (qui l'a posé).
    target: int | None = None
    # `EffectComponent` Value @+0x60/+0x64 (flag @+0x5d) — magnitude matérialisée (Nullable<int> natif :
    # None = effet sans valeur portée, la magnitude vient alors de la config d'ability). Peuplé par
    # AddEffectOperation depuis le builder (param_6) quand l'ability source porte une valeur explicite.
    value: int | None = None
    # `EffectComponent` ParentEffect @+0x70 — pour un SOUS-effet (enfant d'un effet composite), le type
    # de l'effet parent qui l'a spawné (ex. Stunned 1162 parent de 1165/1166/1167). None = effet racine.
    # Sert au cycle de vie (les enfants sont reverté quand le parent expire). §matérialisation composite.
    parent_type: int | None = None
    # `EffectComponent` TimesApplied @+0x6c — COMPTEUR D'APPLICATIONS de CETTE instance. Mirror 1:1 :
    #   * `IdunBattle.Entities.Components.EffectComponent$$.ctor` ecrit **1** (`*(int*)(this+0x6c) = 1`,
    #     juste a cote du Level @+0x68 qu'il initialise pareil) -> une instance FRAICHE vaut 1, PAS 0 ;
    #   * `IdunBattle.Operations.AddEffectOperation$$UpdateExistingEffect` fait `+0x6c += 1` quand le
    #     MEME type est RE-pose sur une cible qui le porte deja (branche `IsUpdatable(type)` + match
    #     `EffectComponent.Type @+0x58` + match `ParentEffect @+0x70`).
    # LU par `IdunBattle.Entities.Effects.BaseEffect$$GetTimesApplied` (retourne litteralement `+0x6c`)
    # et par le noeud DSL `IdunBattleLogic.Entities.DSLFactory$$TimesEffectApplied` ->
    # `IdunBattle.Entities.Formulas.TimesEffectAppliedFormula$$Calculate` (somme `+0x6c` sur les entites
    # rendues par le selecteur). Consommateur porte : `Chronometron_ExtraDamageEffect` (magnitude
    # `Multiply(ConfigVar, TimesEffectApplied(Effect@0x150))`).
    # ⚠ N'est PAS expose par les evenements d'effet (seuls `+0x64` et `+0x68` partent dans les payloads
    # 0x15/0x29) -> ABSENT du canal de seed `decisionView.effects` : le defaut natif 1 est aussi la
    # seule valeur seedable.
    times_applied: int = 1
    consumed: bool = False                   # retiré par le cycle de vie (one-shot / fin-de-tour)
    # `EffectComponent` IsActive @+0x5c — l'ETAT ACTIF **PERSISTE** de CETTE instance d'effet, ecrit par
    # `IdunBattle.Operations.RefreshEffectsOperation$$ActivateEffect` (=1) et
    # `IdunBattle.Operations.RefreshEffectsOperation$$DeactivateEffect` (=0), c'est-a-dire par les feuilles
    # DSL `ActivateEffect`/`DeactivateEffect` des `Triggered()` que l'effet enregistre dans son
    # `CreateHandleTriggerAbilitiesInternal`. RELU par
    # `IdunBattle.Operations.EvaluateTriggerOperation$$EvaluateEffectTriggerTargets` AVANT d'evaluer le
    # trigger de CIBLE de l'effet (et re-lu PAR CIBLE dans la boucle : une desactivation en cours de
    # drain stoppe les cibles suivantes), et par `IdunBattle.Entities.EntityExtensions$$IsOwnerOfEffect`
    # quand `activeOnly` est pose.
    # ⚠ A NE PAS CONFONDRE avec la METHODE `is_active(unit_state)` ci-dessous, qui est le mirror de
    # `<Effect>.CreateActiveCondition` (la CONDITION, reevaluee a la lecture). Ici c'est le FLAG.
    # Defaut True, et le SEED peut desormais l'ECRASER : `EffectFactory.create` lit la cle `active`
    # du capte quand la source la publie. Canal `decisionView` par DEFAUT -> les entrees a
    # `IsActive == 0` sont DROPPEES par `readEffectsByUnit` (case-160/case-127 SS 80), donc
    # « present == IsActive » et le defaut True est exact. Canal `decisionView { includeInactive:
    # true }` -> les entrees inertes SONT publiees, `active: false` compris, et c'est cette valeur
    # qui atterrit ici. Meme defaut pour la pose OFFLINE (`AddEffectOperation`), dont le `captured`
    # n'a pas de cle `active` : le natif cree l'entite-effet ACTIVE et delegue l'inertie a
    # `<Effect>.CreateActiveCondition` (la METHODE `is_active` ci-dessous).
    active: bool = True
    # `AbilityVariablesMultiplierPercentage` de l'unité porteuse (BC, défaut 100). Le natif bake le
    # scaling dans la config par-unité ; ici l'effet le porte pour scaler ses variables d'ability
    # affectées (`variablesAffectedByRarityBonus`) via `magnitude.ability_var(multiplier_pct=…)`. §17.21.
    ability_variables_multiplier: int = 100
    # `StatModifierComponent` de l'ENTITE-EFFET, tel que le capteur le publie CHAMP PAR CHAMP sous
    # ses NOMS NATIFS (`frida/hooks/game/effects.ts::readStatModifier`, qui ENUMERE les champs
    # DECLARES de `IdunBattle.Entities.Components.StatModifierComponent` au lieu de deviner un
    # layout) : `{StatType, Amount, ApplyCounter, IsDynamic, IsHidden}`. Ces noms concordent avec
    # `IdunBattle.Entities.Behaviours.AddStatModifierEffectBehaviour$$StatModifierBuilder`, qui
    # ecrit `+0x10 = statType`, `+0x14 = amount`, `+0x1c = isDynamic`, `+0x1d = isHidden`.
    #
    # ⚠ C'EST LA MAGNITUDE QUE LE NATIF LUI-MEME RELIT :
    # `IdunBattle.Entities.Effects.AStatModifierEffect$$GetStatModificationStat` retourne
    # litteralement `+0x10`, et `IdunBattle.Entities.Effects.StaticStatModifierEffect$$
    # GetStatModificationAmount` litteralement `+0x14`. Une classe d'effet qui RE-DERIVE la
    # magnitude de gameconfig fait donc une APPROXIMATION -- exacte quand elle sait retrouver
    # l'`AbilityState` du poseur, FAUSSE sinon. Le cas qui l'a mis en evidence est
    # `ShockAssault_Buff` (1000, case-366-r1) : sa feuille de pose passe `source = null`, donc
    # `captured["source"]` designe le PORTEUR (le summon) et non le poseur -- la re-derivation y
    # rendait `extraDmg[1] = 5` la ou le natif avait ecrit `499` (mesure live 2026-08-01).
    #
    # ⚠ LE `source = null` N'EST PAS UN CHOIX D'ABILITY, C'EST LA FEUILLE (case-366-r1-statmod) :
    # les TROIS surcharges `IdunBattleLogic.Entities.DSLBehaviors$$AddStaticStatModifierEffect`
    # construisent `IdunBattle.Entities.Behaviours.AddStatModifierEffectBehaviour$$.ctor` avec
    # **NULL** en 4e argument (`source`), et `...$$Execute` retombe alors litteralement sur
    # l'ENTITE-CIBLE de l'iteration (`lVar9 = <target>; if (sourceSelectionne != 0) lVar9 =
    # <source>;`). Les DEUX surcharges `...$$AddStaticStatModifierEffectToOwner`, elles, passent
    # `Owner@DSLSelectors+0x30` en source ET en cibles. Le discriminant d'une classe est donc :
    # « sa feuille de pose vise-t-elle AUTRE CHOSE que l'Owner ? » -- si oui, `SourceUnit` designe
    # le porteur et toute magnitude re-derivee d'un `AbilityState` est FAUSSE hors du poseur.
    # ⚠ Ce champ est INERTE tant qu'une classe ne le lit pas (`captured_stat_mod_amount`) : les
    # classes deja validees gardent leur derivation, aucune n'est modifiee par sa seule presence.
    # None = l'entite-effet n'a pas de `StatModifierComponent` (la grande majorite), ou la capture
    # ne publie pas ce canal (pose OFFLINE, capture anterieure au capteur).
    stat_mod: "Mapping | None" = None
    # Empilement : un effet StatModifier qui applique un stat-mod FRAIS à CHAQUE pose (ActOfFaith) le passe
    # à True → `AddEffectOperation` ne no-op PAS sur « déjà présent » et matérialise une NOUVELLE instance
    # (revert par-source). Défaut False = comportement historique (un même-type déjà présent → no-op, mirror
    # du refresh des effets updatable Fire/Pinned/Stunned). §slice-20 (docs/rl/dsl-effect-nodes.md).
    # ⚠ PAS d'annotation de type (`: bool`) : ce serait un FIELD dataclass dont l'`__init__` écraserait
    # l'override de sous-classe (ex. `ActOfFaithBuffEffect.stacks_stat_mod_on_add = True`). Attribut de
    # classe SIMPLE = surchargeable par la MRO (même pattern que `cc_delta`/`stat_mod_source`).
    stacks_stat_mod_on_add = False
    # Le flag capté `active` est-il PÉRIMÉ pour cet effet, parce que le port porte lui-même sa
    # `CreateActiveCondition` ? (case-322). Natif : `EffectComponent.IsActive @+0x5c` n'est PAS un
    # état figé — `IdunBattle.Operations.RefreshEffectsOperation$$RefreshEffect` le RÉÉCRIT à chaque
    # refresh (`RefreshEffectTrigger.Simulation` compris : une prédiction à une tuile candidate
    # passe par `IdunBattle.Operations.SimulateEffectsOperation$$RefreshSimulatedEffects`). Un effet
    # dont la condition dépend de l'ÉTAT SIMULÉ (ex. `ModifiedExoarmour_ExtraDmg` :
    # `AmountIsGreaterThanZero(TilesMovedThisTurn)`) a donc un flag capté qui décrit l'état RÉEL et
    # ne prédit RIEN de l'état simulé — le lire comme un filtre ferme le port à tort.
    # `True` => `EffectsState.active_effects` s'en remet à `is_active(unit_state)` SEUL.
    # ⚠ N'y passer un effet que si sa `CreateActiveCondition` est RÉELLEMENT portée (sinon le défaut
    # `is_active -> True` transformerait un inerte capté en contributeur). Défaut `False` = le flag
    # capté fait foi, comportement historique de TOUTES les autres classes.
    # (Attribut de classe SIMPLE, sans annotation : sinon field dataclass, écrasé par l'`__init__`.)
    active_condition_ported = False
    # TEMOIN d'ENTITE de la pose de cet effet : le nom d'un effet FRERE, pose par la MEME expression
    # `<Ability>.CreateBehaviour` et INCONDITIONNEL, donc toujours publie par le canal ACTIF-ONLY.
    # Sert au seed de la face DECISION (`playbook/scene.py::_seed_condition_gated_owner_effects`) :
    # un effet inactif ne se materialise que si son temoin est LA. Pourquoi un temoin plutot que le
    # kit gameconfig du porteur : le kit dit ce que l'unite POSSEDE EN THEORIE, pas ce que l'ENTITE
    # porte en bataille -- meme piege que #264 (`necroOverlord` a `Resilient` au gameconfig et pas en
    # bataille). MESURE (case-322) : un seed BC prive de `PassiveAbilities` produit une entite SANS
    # aucun des deux effets, alors que `GC.unit(vid).passiveAbilities` continue de les annoncer ; un
    # seed base sur le kit sur-predisait alors de +2806 sur une tuile (contre-bras de #312).
    # None = pas de seed decision (defaut de TOUTES les autres classes).
    seed_witness_effect = None
    # Journal des `AddUnitActiveAbilityModification` REELLEMENT poses par cette instance (liste de
    # `(target, key, delta)`), rempli par `operations/ability_modifications.py::apply_ability_modifications`
    # et NIE par `revert_ability_modifications` (mirror `RevertInternal` = les memes appels en `-delta`).
    # Meme regime d'attribut de classe SIMPLE que `stacks_stat_mod_on_add` (pas d'annotation -> pas de
    # field dataclass). None/[] = l'effet n'a pose aucune modification d'ability.
    applied_ability_modifications = None
    # Journal des `AddTrait` REELLEMENT accordes par cette instance (liste de
    # `(target, trait, is_temporary)`), rempli par `operations/traits.py::apply_traits_of_effect` et
    # NIE par `revert_traits_of_effect` (mirror `RevertInternal` = les memes appels en RETRAIT).
    # Meme regime d'attribut de classe SIMPLE que `applied_ability_modifications` juste au-dessus.
    # ⚠ IL PORTE UN CRAN QUE LA DECLARATION `applied_traits()` NE PORTE PAS : le natif s'arrete des
    # que `coll.Add(trait)` rend `false` (trait DEJA porte), donc un trait de KIT ne doit PAS partir
    # au retrait de l'effet. Le port fusionne les deux collections natives en un seul ensemble de
    # NOMS -> seule cette liste distingue « pose par moi » de « deja la ». MESURE (case-366-r1) :
    # `spaceWulfen` porte `Unstoppable` au kit et recoit 1222 -- sans ce cran, l'expiration du buff
    # lui volerait son trait permanent. None/[] = l'instance n'a accorde aucun trait.
    applied_trait_grants = None
    # CLE de la `ValueModification` que CETTE instance a posee sur le `UnitStats` de sa cible. Cote natif
    # c'est litteralement l'ENTITE-EFFET : `IdunBattle.Entities.Effects.AStatModifierEffect$$ApplyModification`
    # passe `DSLFactory$$Entity(<effectEntity>)` en 6e argument de `IdunBattleLogic.Entities.DSLFactory$$ChangeStat`,
    # et `IdunBattle.Entities.Effects.AStatModifierEffect$$RevertModification` REPASSE LA MEME entite avec
    # `Position(stat, part 6)` -> `IdunBattle.Entities.Components.ValueModification$$ReverseModification`.
    # => UNE seule cle par instance d'effet, quel que soit le chemin qui l'a posee. Renseignee par les
    # chemins de pose OFFLINE (`AddEffectOperation._apply_stat_mods`, feuille `AddStaticStatModifierEffect`) ;
    # laissee None pour un effet SEEDE (la cle est alors DERIVEE — cf. `effect_stat_mod_key`).
    stat_mod_source = None
    # Marqueur d'idempotence du revert (`RevertModification` deja joue pour cette instance). Le revert
    # par-source est structurellement idempotent (`ReverseModification` pop une cle absente = no-op) ; ce
    # drapeau evite surtout de RE-LISTER le meme revert a chaque tick dans les diagnostics.
    stat_mod_reverted = False
    # ETAPE de la sequence de mort a laquelle cet effet est retire du porteur qui vient de mourir --
    # le predicat que `IdunBattle.Operations.RemoveEffectsOperation$$Execute` lit sur l'objet-effet
    # (slot 4 de l'interface `IEffect`, NOMME `get_RemoveOnDeathStep` dans
    # `data/symbols/<build>/metadata/interface_slots.tsv`) et compare par EGALITE a `options.step`.
    # Domaine : `IdunBattle.Operations.KillUnitStep`, les trois valeurs que passe
    # `IdunBattle.Operations.KillUnitOperation$$Execute` a ses trois appels de `$$RemoveEffects`.
    #
    # ⚠ LE DEFAUT ETAIT UNE HYPOTHESE NOMMEE (#389-r2, `PreUnitRemove`), ET ELLE ETAIT FAUSSE.
    # `probe_1088_remove_on_death_step.py` LIT desormais ce getteur constant -- DECLARATION dans le
    # `global-metadata.dat`, VALEUR aux OCTETS dans le bloc `methodPointers` -- sur les 465 classes
    # de la fermeture transitive de `BaseEffect`, avec **0 indeterminee** :
    #   * la base rend `b8 01 00 00 00 c3` = **1** (`AfterUnitRemove`), 66 controles d'alignement ;
    #   * QUATRE classes surchargent (entree versionnee `metadata/remove_on_death_step.tsv`).
    # Ce n'etait donc pas un cas particulier : les 461 classes qui heritent etaient toutes decrites
    # au mauvais step.
    #
    # ⚠ ET L'ECART N'ETAIT PAS INERTE, contrairement a ce que la fiche d'origine affirmait :
    # `KillUnitOperation$$Execute` place `On(UnitDeath)` puis `On(UnitDefeated)` ENTRE le step 1 et
    # le step 2, donc un effet a `AfterDeathTrigger` est encore porte quand ces events partent. Le
    # port, qui retirait tout au step 0, rendait structurellement impossible un trigger qui LIT un
    # effet du mourant -- cause racine de la face SUCCESS inerte de #911-r1.
    # (Attribut de classe SIMPLE, sans annotation : sinon field dataclass, ecrase par l'`__init__`.)
    remove_on_kill_step = KillUnitStep.AfterUnitRemove
    # ENTITE BONDEE de CETTE instance d'effet -- mirror du champ `+0x10` du composant de bond que
    # `IdunBattle.Entities.Behaviours.AddEffectBehaviour$$DefaultBondEffectBuilder` ecrit sur l'entite-effet
    # (`BondEffect(id)` blueprint, puis `<composant>.BondedEntityId = param_3`), et que relit
    # `IdunBattle.Entities.Effects.ABondEffect$$BondedEntityId(effect)` -- la source du noeud
    # `IdunBattleLogic.Entities.DSLFactory$$BondedEntityFromEffect` / `ABondEffect$$BondedEntitySelector`.
    # L'id vient du 5e argument d'`IdunBattleLogic.Entities.DSLFactory$$AddBondEffect` (`bondedEntity`, un
    # SELECTEUR range dans les options), resolu A L'EXECUTION par
    # `IdunBattle.Entities.Behaviours.AddEffectBehaviour$$GetEffectBuilder` (`this+0x70` -> `SelectSingle`
    # -> `EntityId`) : `0`/null => builder d'effet ORDINAIRE, donc AUCUN bond.
    # DISTINCT de `source` (`EffectComponent.SourceUnit @+0x10`, l'EffectSource) et de `target`
    # (`EffectComponent.Target @+0x14`, le porteur) : sur `HazeOfCorruption_DamageTransfer` (1077) les trois
    # sont TROIS unites differentes -- source = la cible initiale, target = le relais, bonded = Maladus.
    # None = effet non-bond, OU capteur muet. Depuis #436-r1 la vue d'effet PUBLIE le bonded
    # (`bondedEntityId` + `bondMeasured`, `frida/hooks/game/effects.ts::readBondLink`), et
    # `EffectFactory.create` le pose sur les effets SEEDES -- il ne reste `None` sur un effet hydrate
    # que si le hook charge est anterieur a ce capteur (`bondMeasured: false`), auquel cas le port
    # garde son comportement d'avant. ⚠ Le capteur exige une fenetre de reinject pour etre CHARGE :
    # tant qu'elle n'a pas eu lieu, tout etat hydrate reste `bonded = None`.
    bonded = None
    # `EffectComponent+0x48` -- les ids d'entite CIBLE materialises SUR L'ENTITE-EFFET, ecrits par
    # `IdunBattle.Entities.Components.EffectComponent$$AddTargetId` depuis
    # `IdunBattle.Operations.RefreshEffectsOperation$$AddTargetsToEffect` (elle-meme enfilee par
    # `...$$UpdateEffectTargets`, qui joue le `CreateTargetSelector` de l'effet). C'est le champ que
    # LIT `IdunBattle.Entities.EntityExtensions$$IsTargetOfEffectOfType` -- donc la SORTIE native de
    # tout `CreateTargetSelector`, la seule qui permette de confronter ces noeuds autrement que sur
    # leurs ENTREES (#366-r1-effect-targets).
    #
    # TRI-ETAT, meme discipline que `bonded` : `None` = **PAS MESURE** (capture anterieure au
    # capteur, ou pose OFFLINE, qui ne materialise pas cette liste) ; `[]` = mesure faite et VIDE ;
    # liste non vide = les cibles. Le capteur EXISTE et est verifie live depuis le 2026-08-01
    # (`frida/hooks/game/effects.ts::readEffectTargetIds`, publie sous
    # `decisionView.units[].effects[].targetIds`, lui-meme tri-etat) -- ce champ-ci est le bout
    # PORT du meme canal, jusqu'ici absent.
    # ⚠ INERTE tant qu'aucun consommateur ne le lit : il est POSE, pas encore CONSOMME. Le port
    # continue de RE-DERIVER les cibles a la lecture (chaque `CreateTargetSelector` est evalue par
    # son consommateur) ; ce champ est la mesure native en regard, pas un remplacant.
    target_ids = None

    def applied_stat_mods(self, stats_ctx) -> "list":
        """`<Effect>.ApplyModification` (part DATA côté `entities/`) — liste des `(StatType, montant)` posés
        via `ChangeStat` quand l'effet est appliqué. La couche runner (`AddEffectOperation._apply_stat_mods`)
        les EXÉCUTE (`apply_change_stat`, keyé par source). Symétrique de `reverted_stats()` (que lit
        `RemoveEffect`). Défaut `[]` = effet sans stat-mod eager (la plupart)."""
        return []

    # ── canal RANGE BONUS du mouvement (#1048) ──────────────────────────────────────────────────────
    def create_range_bonus_for_movement(self, mctx):
        """`<Effect>$$CreateRangeBonusForMovement(owner)` — slot VIRTUEL (`+0x698` de la table de
        l'effet), appelé par `IdunBattle.Entities.Effects.BaseEffect$$RangeBonusForMovement`.
        Défaut `None` = la base rend un `Nullable<EffectRangeBonus>` VIDE, donc aucun bonus.

        Le SEUL implémenteur du build `rnca9r7q6c` est
        `IdunBattle.Entities.Effects.Loki.AdrenalGlandsEffect$$CreateRangeBonusForMovement`
        (`entities/effects/loki/adrenal_glands.py`). `mctx` = `services.range_bonus.
        MovementBonusContext` — le port doit fournir l'état et le plateau que l'effet natif porte
        déjà dans ses champs `+0x50` (`IBattleQuery`) et `+0x58` (l'état)."""
        return None

    def range_bonus_for_movement(self, mctx):
        """`IdunBattle.Entities.Effects.BaseEffect$$RangeBonusForMovement(entities)` — mirror 1:1 :

            var b = this.CreateRangeBonusForMovement(entities.<+0x18 = owner>);   // slot +0x698
            if (!b.HasValue) return null;
            if (b.Value.Trigger != null && !b.Value.Trigger.Check(entities, ...)) return null;
            return new RangeBonus(b.Value.ExtraRange, b.Value.ExtraRangeCondition,
                                  b.Value.ReduceRange);

        Le gate `Trigger` est porté par FIDÉLITÉ : aucun effet du build n'en pose (le seul
        implémenteur rend `Trigger = null`), donc il est INERTE aujourd'hui — mais un port qui
        l'omettrait laisserait passer un bonus conditionnel le jour où il apparaît, en silence."""
        from ...services.range_bonus import RangeBonus       # FEUILLE (aucun import du paquet)
        b = self.create_range_bonus_for_movement(mctx)
        if b is None:
            return None
        trg = getattr(b, "trigger", None)
        if trg is not None and not trg(mctx):
            return None
        return RangeBonus(extra_range=int(getattr(b, "extra_range", 0) or 0),
                          extra_range_condition=getattr(b, "extra_range_condition", None),
                          reduce_range=getattr(b, "reduce_range", None))

    # ── contributions aux modifiers (None = pas de contribution) ────────────────────────────────────
    def create_effect_damage_bonus_for_attack(self, is_ranged: bool | None = None,
                                              has_moved: bool | None = None,
                                              target_traits: "frozenset[str] | None" = None,
                                              is_prediction: bool = False,
                                              is_normal_attack: bool | None = True,
                                              target_armor_reduced: bool | None = None,
                                              att_ctx=None) -> EffectBonus | None:
        """`<Effect>.CreateEffectDamageBonusForAttack` — contribution au scalaire dégât (additif/percent).
        `target_traits` = noms de traits gameconfig de la CIBLE (mirror `HasTrait(target,…)` natif) pour
        les bonus target-conditionnels (ex. BeastSlayer vs BigTarget/Vehicle) ; None = cible inconnue.
        `is_ranged` = nature du coup courant : effets gated `IsRangedAttack` (HeavyWeapon_ExtraDmg,
        RangedSpecialist). `has_moved` = `HasFlag(Self, UnitFlag.Moved)` tel que le vecteur courant le
        voit : effets gated no-move (`!HasFlag(HasMoved=0)`, ex. HeavyWeapon IdunBattle.Entities.Effects.Loki.HeavyWeapon_ExtraDmgEffect$$CreateDamageModifier).
        En COMBAT c'est le flag de l'ECS (`components.unit_has_moved`) ; en PRÉDICTION c'est ce MÊME
        flag OU la tuile candidate ≠ tuile courante — les deux termes de `prediction_has_moved` (#266),
        le second étant le mirror de `SimulateEffectsOperation$$DoActionInSimulatedTile`, qui appelle
        `SetMovedFlag` avant d'évaluer une prédiction depuis une tuile simulée.
        `is_normal_attack` = mirror du nœud DSL `IsNormalAttack` (attaque normale
        vs spéciale — gate de CrushingStrike IdunBattle.Entities.Effects.Loki.CrushingStrikeEffect$$CreateDamageModifier ; True par défaut : les call-sites normale ne le
        passent pas). `target_armor_reduced` = évaluation du gate `HasNegativeModifier(cible, {ARMOR,
        FIXED_ARMOR})` (IdunBattle.Entities.Triggers.HasNegativeModifier$$ShouldTrigger ; la CIBLE porte ≥1 modification per-source <0 sur une stat d'armure =
        « armure réduite ») threadée depuis le site de résolution — pour les bonus gated sur l'état d'armure
        de la cible (ConquerorImperative IdunBattle.Entities.Effects.Loki.ConquerorImperativeEffect$$CreateDamageModifier). None = état inconnu. `att_ctx` (Mapping|None) =
        contexte POSITIONNEL de l'attaque pour les bonus dont la MAGNITUDE dépend de la position du caster
        (mirror du DSL qui lit la UnitPosition hypothétique, ex. LordOfTempests `SurroundingTiles(owner,0,1)`
        IdunBattle.Entities.Effects.Loki.LordOfTempests_ExtraDamageEffect$$GetHexesIncreasingDamage) : {"att_pos": (col,row) tuile candidate, "tile_effects_by_pos": {(col,row):[noms]}}.
        None = contexte inconnu -> ces bonus rendent None (« présent ≠ appliqué », dégradation fidèle).

        QUATRE clés d'`att_ctx` décrivent la CIBLE et l'ATTAQUANT plutôt que la position, arrivées avec
        `PsychicStalk_FriendlyChaosExtraDamage` (#366-r1) — `att_grand_alliance` (nœud
        `HasTrait(Caster@0x48, 0x7ea = Chaos)`), `damage_profile` (`DamageProfileIs([...])`), `t_pos` +
        l'entrée correspondante de `tile_effects_by_pos` (`EntitiesWithAnyEffect(Tiles(Target@0x60),
        Fire)`), et `tgt_team`. Ce sont les MÊMES CLÉS, avec la MÊME sémantique, que le ctx du canal
        AURA (`create_aura_attack_damage_bonus_for_ally`) et que la face PRÉDICTION : le natif n'a
        qu'UN corps (`CreateEffectDamageBonusForAttack`) et qu'UN `AbilityEntities`, la scission
        self/aura est un artefact du port. Clé absente -> gate FERMÉ (dégradation RESTRICTIVE)."""
        return None

    def create_effect_hits_bonus_for_attack(self, is_normal_attack: bool = True,
                                            att_ctx: Mapping | None = None) -> EffectBonus | None:
        """`<Effect>.CreateEffectHitsBonusForAttack` — contribution à l'axe COUPS (Addition/Subtraction).
        `att_ctx` (Mapping|None) = le `board` de `AttackHitsWithModifiersFormula` ({att_id, tgt_id,
        attack_pos, t_pos, …}) ENRICHI de `tile_effects_by_pos` (tileMeta → nœud `HasTileStatusEffect`)
        et `persistent_data` (les clés `PersistentDataComponent` posées sur l'ATTAQUANT → nœud
        `IsPersistentData`), pour les bonus dont le gate porte sur la CIBLE ou sur un flag intra-attaque
        (ex. `IdunBattle.Entities.Effects.Loki.LetTheGalaxyBurnEffect$$CreateAdditionalHits = `OwnerIsCaster &
        (TargetHasTileEffect | IsPersistentData)`). None = contexte inconnu → ces bonus rendent None."""
        return None

    def create_effect_hits_malus_for_defense(self, is_melee: bool | None = None,
                                             damage_profile: str | None = None,
                                             defender_on_cover: bool | None = None,
                                             dist: int | None = None,
                                             is_normal_attack: bool = True,
                                             att_ctx: Mapping | None = None) -> EffectBonus | None:
        """Contribution DÉFENSEUR à l'axe COUPS (l'effet est sur la CIBLE, modifie les coups reçus).
        Natif : même canal `CreateEffectHitsBonusForAttack` mais trigger `OwnerIsTarget` (ex.
        `IdunBattle.Entities.Effects.Loki.LightCoverEffect$$CreateEffectHitsBonusForAttack = `ForAdditionWithMinimum(
        OwnerIsTarget(tuiles égales) & !IsMeleeAttack, -ConfigConst(0x2c hitsReduction), min=Direct(1))` ;
        `ParryEffect` IdunBattle.Entities.Effects.Loki.ParryEffect$$CreateEffectHitsBonusForAttack idem gated `IsMeleeAttack` ; `MasterAnnihilator_AdditionalHitEffect`
        IdunBattle.Entities.Effects.Loki.MasterAnnihilator_AdditionalHitEffect$$CreateAdditionalHits = +nrOfHits gated `!DamageProfileIs(Psychic)`) — le port eager sépare
        attaquant/défenseur, symétrique de `create_effect_damage_malus_for_defense`. `damage_profile` =
        NOM du profil de l'attaque (gate Psychic). `defender_on_cover` = gate compute-time des effets de
        TUILE (LightCover) : True=cible sur sa tuile de cover, False=hors-cover (effet périmé, ne s'applique
        pas), None=inconnu (applique sur présence — cas prédiction, cible immobile). Plancher min=1 chez le
        consommateur. Défaut None.
        `is_normal_attack` = nature du VECTEUR (attaque normale vs attaque d'ABILITY), MEME donnee que
        celle threadee par `create_effect_hits_bonus_for_attack` -- le natif n'a qu'UN canal
        (`CreateEffectHitsBonusForAttack`) et le noeud `IdunBattleLogic.Entities.DSLTriggers$$IsNormalAttack`
        y apparait des DEUX cotes du trigger `OwnerIsTarget`/`OwnerIsCaster`. Porteur cote DEFENSE :
        `IdunBattle.Entities.Effects.Loki.ShroudPsalmEffect$$CreateEffectHitsBonusForAttack`
        (`get_OwnerIsTarget & IsNormalAttack`). Defaut True = attaque normale.

        `att_ctx` = le `board` COMPLET de `IdunBattle.Entities.Formulas.AttackHitsWithModifiersFormula`
        -- LE MEME dict que celui deja passe au canal ATTAQUANT (`create_effect_hits_bonus_for_attack`)
        et au canal AURA, threade ici parce que le natif n'a QU'UN canal et passe le MEME
        `AbilityEntities` a tous les effets de sa boucle : rien n'y borne les noeuds lisibles au
        DEFENSEUR. Premier consommateur : `TerrorsLament_HitReduction`, dont le trigger ne porte NI
        sur la cible NI sur un selecteur mais sur l'ATTAQUANT (`IsAdjacent(Caster, Owner)`,
        `AreEnemies(Owner, Caster)`, `HasTrait(Caster, Immune)`) -- ses cles sont `att_id`,
        `attack_pos`, `team_by_id`, `att_traits`, `t_pos`, `tgt_team`. Absent (appelant historique)
        -> ces gates se taisent, comme toute cle manquante."""
        return None

    def create_aura_hits_malus_for_defense(self, ctx: Mapping | None = None) -> EffectBonus | None:
        """Contribution AURA à l'axe COUPS : l'effet est possédé par une AUTRE unité que la cible et
        projette un malus sur elle selon la géométrie (natif : effet à `CreateTargetSelector` +
        `GetRefreshTriggers`, ex. `BigTargetAdjacentEffect` IdunBattle.Entities.Effects.Loki.BigTargetAdjacentEffect$$CreateEffectHitsBonusForAttack/IdunBattle.Entities.Effects.Loki.BigTargetAdjacentEffect$$CreateTargetSelector = alliés ring-1 du
        porteur, -1 coup ranged min 1). `ctx` = {owner_id/pos/team, tgt_id, t_pos, tgt_team, is_melee}
        fourni par l'agrégateur `aura_hits_malus_for_defense`. Défaut None = pas d'aura."""
        return None

    # #204 avait SUPPRIME `create_aura_hits_bonus_for_attack` : son unique implementeur d'alors,
    # `AstartesBannerExtraHitEffect`, appelle en natif `CreateAdditionalHits` (canal #179) et non
    # `CreateEffectHitsBonusForAttack` -- le hook etait donc MORT, et un hook mort est un piege.
    # #372 le REOUVRE avec l'alimenteur natif qui manquait :
    # `IdunBattle.Entities.Effects.Loki.DefenderOfTheGreaterGood_ExtraHitsEffect$$CreateEffectHitsBonusForAttack`
    # (1183 / 1307), un `EffectBonus.ForAddition` -- donc bien un TERME DE LA FORMULE de coups.
    def create_aura_hits_bonus_for_attack(self, ctx: Mapping | None = None) -> EffectBonus | None:
        """Contribution AURA a l'axe COUPS de l'ATTAQUANT : l'effet est possede par une AUTRE unite
        (le PORTEUR) et projette un bonus de coups sur ses allies selon son `CreateTargetSelector`.

        Natif : `IdunBattle.Core.Services.DamagePrediction$$GetAttackHits` n'itere pas les effets de
        l'attaquant mais TOUS les effets actifs du board
        (`IdunBattle.Core.Services.EffectsQuery$$GetActiveEffectsWithBonuses`), en bouclant effets x
        CIBLES et en ecrivant `AbilityEntities+0x18 (Owner) <- la cible de l'effet` : `get_OwnerIsCaster`
        y signifie donc « la cible de l'effet EST l'attaquant ». Le port rend ce gate par le canal
        (l'agregateur n'interroge que les porteurs != attaquant et evalue le selecteur sur l'attaquant),
        comme les autres auras source-side (#49/#153).

        `ctx` = {owner_id/pos/team, att_id/att_pos/att_team/att_faction, is_melee, damage_profile,
        turns_started_by_id, parent_by_id, rng, aura_peers} fourni par `aura_hits_bonus_for_attack`.
        Defaut None = pas d'aura."""
        return None

    def block_hits_reduction(self, att_ctx: Mapping | None = None) -> bool:
        """`IdunBattle.Entities.Effects.BaseEffect$$BlockHitsReduction` — l'effet ANNULE-t-il les
        REDUCTIONS de coups de cette attaque ? (case-366-r1, canal ouvert par `1117
        InescapableAccuracy_overrideHits`).

        TROISIEME canal de `IdunBattle.Core.Services.DamagePrediction$$GetAttackHits`, distinct des
        deux autres et lu au MEME tour de boucle. Le natif trie les `HitsBonusForAttack` de TOUS les
        effets actifs du board (`IdunBattle.Core.Services.EffectsQuery$$GetActiveEffectsWithBonuses`)
        en DEUX listes selon le SIGNE de leur `addition` -- `< 0` = REDUCTION, `>= 0` = addition --
        puis somme la liste des additions INCONDITIONNELLEMENT et celle des reductions
        **seulement si aucun effet n'a rendu `BlockHitsReduction == true`**. Ce booleen est donc un
        interrupteur global sur l'axe COUPS, pas un terme de la somme : il n'a AUCUNE magnitude.

        Cote natif la valeur rendue est le trigger `CreateBlockHitReductionTrigger` mis en cache a
        `<effect>+0x460` par `IdunBattle.Entities.Effects.BaseEffect$$InitializeBonusCacheIfNeeded` ;
        un effet qui ne le surcharge pas a un cache NUL et rend `false`. D'ou le defaut ici.

        `att_ctx` = le meme `board` que `create_effect_hits_bonus_for_attack` (la formule le passe
        aux DEUX canaux, un seul point d'enrichissement), PLUS la cle `owner_id` que
        `block_hits_reduction_from_effects` pose par PORTEUR -- mirror de l'ecriture native
        `AbilityEntities+0x18 (Owner) <- la cible de l'effet` dans la boucle de `GetAttackHits`.
        Cle ABSENTE = gate qui se tait ; `is_melee is not False` ferme `IsRangedAttack` (tri-etat
        #106, meme idiome que `BigTargetAdjacentEffect`).

        DEUX implementeurs natifs -- les DEUX portes depuis `#366-r1-blockhits-purgeresponse`, et
        leurs triggers n'ont AUCUN noeud en commun :
          * `IdunBattleLogic.Entities.Abilities.Triggered.Loki.InescapableAccuracy_OverridHitsEffect$$
            CreateBlockHitReductionTrigger` = `get_OwnerIsCaster & IsRangedAttack`
            -> `InescapableAccuracyOverrideHitsEffect` (eldarMauganRa) ;
          * `IdunBattle.Entities.Effects.Loki.PurgeResponseEffect$$CreateBlockHitReductionTrigger`
            = `TriggeringAbilityIs(AbilityOrEffect(EffectType 0x3f1 = 1009 Overwatch_AutoAttack))`,
            noeud UNIQUE, SANS `get_OwnerIsCaster` -> `PurgeResponseEffect` (votanSmnSteeljack).
        C'est la seconde qui a impose le balayage BOARD-WIDE de l'agregateur (son porteur peut etre
        n'importe qui, dans n'importe quel camp) et donc la MIGRATION du `get_OwnerIsCaster` de la
        premiere depuis le canal vers sa classe."""
        return False

    def create_aura_attack_bonus(self, ctx: Mapping | None = None) -> "int | None":
        """Contribution AURA à la BASE (stat Attack) : effet stat-mod possédé par un ALLIÉ du porteur qui
        buffe le dégât de base de l'attaquant quand il est à portée (natif : `DynamicStatModifierEffect` à
        `CreateTargetSelector` = `AdjacentUnits(1)→Friends→With/WithoutTrait`, ex. `RitesOfBattleAbility`
        IdunBattleLogic.Entities.Abilities.Active.Loki.RitesOfBattleAbility$$CreateBehaviour). Ajouté PLAT à `GetStat(Attack, INITIAL)`, RÉ-ÉVALUÉ PAR CANDIDAT (adjacence à la tuile
        d'attaque). `ctx` = {owner_id/pos/team/mult/level, att_id/att_pos/att_team/att_grand_alliance, board}
        fourni par l'agrégateur `aura_attack_bonus_from_allies`. Défaut None = pas d'aura."""
        return None

    def create_aura_fixed_armor_bonus_for_defense(self, ctx: Mapping | None = None) -> "int | None":
        """Contribution AURA à la stat **FixedArmor(16)** du DÉFENSEUR : effet stat-mod possédé par un ALLIÉ
        du défenseur qui buffe l'armure de ce dernier quand il est à portée (natif : `DynamicStatModifierEffect`
        à `CreateTargetSelector` = self + `AdjacentFriends(1)` ∩ `UnitsWithTrait(5=Mechanical)`, ex.
        `ProtectorImperative` IdunBattle.Entities.Effects.Loki.ConquerorImperativeEffect$$CreateTargetSelector). Ajouté PLAT à `GetStat(FixedArmor)` du défenseur, RÉ-ÉVALUÉ PAR
        ADJACENCE au site de résolution armure (le natif écrit la ValueModification à TOUTES ses cibles-sélecteur
        → l'armure de l'allié à portée l'inclut). Le porteur (self) est déjà couvert par son stat-mod EAGER
        (`applied_stat_mods`, dans `GetStat`) → l'aura n'ajoute QUE pour un défenseur allié DISTINCT (pas de
        double-compte). `ctx` = {owner_id/pos/team/mult/level, def_id/def_pos/def_team/def_traits} fourni par
        l'agrégateur `aura_fixed_armor_bonus_for_defense`. SYMÉTRIQUE défenseur de `create_aura_attack_bonus`
        (attaquant). Défaut None = pas d'aura."""
        return None

    def create_aura_attack_damage_malus_for_enemy(self, ctx: Mapping | None = None) -> EffectBonus | None:
        """Contribution AURA %-DÉGÂT projetée sur un ENNEMI ATTAQUANT à portée (l'effet est possédé par une
        unité, se projette sur les ENNEMIS environnants qui subissent un malus sur LEUR propre attaque —
        natif : effet à `CreateEffectDamageBonusForAttack(OwnerIsActor & ...)` + `CreateTargetSelector` =
        `SurroundingEnemies(range)`, ex. `ShadowInTheWarp_LessDmg_Effect` IdunBattle.Entities.Effects.Loki.ShadowInTheWarp_LessDmg_Effect$$CreateEffectDamageBonusForAttack/IdunBattle.Entities.Effects.Loki.ShadowInTheWarp_LessDmg_Effect$$CreateTargetSelector = -25%
        Psychic). `ctx` = {owner_id/pos/team, att_id/att_pos/att_team, damage_profile} fourni par
        l'agrégateur `aura_attack_damage_malus_from_enemies`. Défaut None = pas d'aura."""
        return None

    def create_aura_attack_damage_bonus_for_ally(self, ctx: Mapping | None = None) -> EffectBonus | None:
        """Contribution AURA DÉGÂT projetée sur un ALLIÉ ATTAQUANT à portée (l'effet est possédé par une
        unité et BONIFIE le dégât que ses ALLIÉS environnants INFLIGENT — natif : effet à
        `CreateEffectDamageBonusForAttack(OwnerIsCaster & ...)` + `CreateTargetSelector` = `AdjacentFriends
        + UnitsWithTrait(...)`, ex. `BeaconOfRage_FriendlyExtraDamageEffect` IdunBattle.Entities.Effects.Loki.BeaconOfRage_FriendlyExtraDamageEffect$$CreateEffectDamageBonusForAttack : +50% du bonus rage
        FLAT aux attaques MÊLÉE des amis Chaos adjacents d'Azkor, #191 ; `ConquerorImperativeEffect` IdunBattle.Entities.Effects.Loki.ConquerorImperativeEffect$$CreateDamageModifier :
        +extraDmg FLAT aux amis Mechanical adjacents vs cible à armure réduite, #23). `ctx` = {owner_id/pos/team,
        att_id/att_pos/att_team, att_grand_alliance, att_traits, is_melee, target_armor_reduced} fourni par
        l'agrégateur `aura_attack_damage_bonus_from_allies` (les gates lisent le sous-ensemble pertinent :
        BeaconOfRage → att_grand_alliance+is_melee ; Conqueror → att_traits+target_armor_reduced). SYMÉTRIQUE
        ALLIÉ de `create_aura_attack_damage_malus_for_enemy`. Défaut None = pas d'aura.

        La clé `tile_effects_by_pos` (`{(col,row): [noms]}`, la MAIN TILE de la cible) est arrivée avec
        `PsychicStalk_FriendlyChaosExtraDamage` (#366-r1), dont le trigger n'a AUCUN
        `CreateTargetSelector` : toute la sélection vit dans le trigger, et l'un de ses conjoints
        (`EntitiesWithAnyEffect(Tiles(Target@0x60), Fire)`) lit les effets portés par la TUILE. MÊME
        forme et MÊME clé que le canal DÉFENSE (`create_aura_defense_damage_malus_for_ally`) et que
        `LetTheGalaxyBurnEffect`. Absente -> le gate se tait.

        La clé `att_rarity` (`idun.meta.Rarity | None`) est arrivée avec `BlightedLandEffect` (1442,
        #999-r3-r1). Le BÉNÉFICIAIRE de ce canal est l'ATTAQUANT — la boucle native écrit
        `AbilityEntities+0x18 (Owner) <- CHAQUE CIBLE du sélecteur` puis évalue `get_OwnerIsCaster` —
        donc un étage `UnitsWithRarity(…, Mythic)` du `$$CreateTargetSelector` se lit sur `att_id`,
        et NON sur le porteur. Substrat : `BaseUnitComponent.Rarity` (+0x74), foyers de lecture
        `damage_model._unit_rarity` / `prediction._shared._entity_rarity`. TRI-ÉTAT : `None` = NON
        MESURÉ -> le gate se FERME (jamais `Rarity.Common` en repli, qui serait PERMISSIF).
        `tile_effects_by_pos` porte depuis la même tranche la MAIN TILE de l'ATTAQUANT en plus de
        celle de la cible (`UnitsOnTilesWithEffect` lit la tuile de l'élément du sélecteur).

        ⚠ Cet agrégateur EXCLUT le porteur (`att_id == owner_id`). Un effet dont le trigger natif
        accorde AUSSI au porteur — `AreFriends(Owner, Caster)` est VRAI quand `Owner == Caster`,
        `IdunBattle.Entities.UnitExtensions$$IsFriend` n'écartant pas l'égalité — doit donc porter
        EN PLUS sa patte SELF dans `create_effect_damage_bonus_for_attack` (patron `DestroyTheWitch_
        ExtraDamage` / `PsychicStalk_FriendlyChaosExtraDamage`). Les deux foyers sont DISJOINTS :
        ni trou, ni double-compte."""
        return None

    def create_aura_defense_damage_malus_for_ally(self, ctx: Mapping | None = None) -> EffectBonus | None:
        """Contribution AURA %-DÉGÂT projetée sur une CIBLE alliée du porteur à portée (l'effet est possédé
        par une unité et RÉDUIT le dégât que ses ALLIÉS environnants REÇOIVENT — natif : effet EffectWithTarget
        à `CreateEffectDamageMalusForDefense(OwnerIsTarget & DamageProfileIs(...))` + `CreateTargetSelector` =
        `SurroundingFriends(range, exclut self)`, évalué state-wide par `IdunBattle.Core.Services.DamageCalculations$$CalculateDefenderModifiersForPrediction (boucle « TOUS les EffectWithTarget actifs × leurs cibles », cf. case-68) — ex.
        `DaughterOfTheAbyss_FriendlyDmgReductionPctEffect` IdunBattle.Entities.Effects.Loki.DaughterOfTheAbyss_FriendlyDmgReductionPctEffect$$CreateEffectDamageMalusForDefense : -dmgReductionPct% Psychic aux amis
        dans le rayon 2 d'Atlacoya (#184). La même boucle sert aussi les effets qui AUGMENTENT le dégât reçu
        par les ENNEMIS du porteur à portée (ex. `DaughterOfTheAbyss_ExtraDamagePctEffect` IdunBattle.Entities.Effects.Loki.DaughterOfTheAbyss_ExtraDamagePctEffect$$CreateEffectDamageBonusForAttack :
        +extraDmgPct% aux Psykers ennemis, selector IdunBattle.Entities.Effects.Loki.DaughterOfTheAbyss_ExtraDamagePctEffect$$CreateTargetSelector `SurroundingEnemies+UnitsWithTrait(0x3ea)`).
        `ctx` = {owner_id/pos/team, tgt_id, t_pos, tgt_team, tgt_traits, tgt_rarity, damage_profile,
        att_id, att_is_unit, tile_effects_by_pos} fourni par l'agrégateur
        `aura_defense_damage_malus_from_units`. Défaut None = pas d'aura.

        La clé `tgt_rarity` (`idun.meta.Rarity | None`) est arrivée avec
        `ContemptuousDisregard_DamageReductionEffect` (1443, #999-r3-r1). Le BÉNÉFICIAIRE de ce canal
        est la CIBLE du coup — `CalculateDefenderModifiersForPrediction` écrit
        `AbilityEntities+0x18 (Owner) <- CHAQUE CIBLE du sélecteur` et le trigger est
        `get_OwnerIsTarget` — donc un étage `UnitsWithRarity(…, Mythic)` du `$$CreateTargetSelector`
        se lit sur `tgt_id`, et NON sur le porteur. Substrat : `BaseUnitComponent.Rarity` (+0x74).
        TRI-ÉTAT : `None` = NON MESURÉ -> le gate se FERME.

        Les TROIS clés `att_rarity`, `is_normal_attack` et `tgt_adjacent_unit_profiles` sont
        arrivées avec `MoreGitzOverEre_ExtraDamagePct` (1449, #1025-r1). Elles ne portent PAS sur le
        bénéficiaire : le trigger de cet effet est
        `get_OwnerIsTarget & (AreFriends(Caster@+0x48, EffectSource@+0x38) & HasRarity(Caster@+0x48,
        Mythic)) & IsMeleeAttack & IsNormalAttack` — deux de ses conjoints interrogent l'ATTAQUANT,
        et son `$$CreateTargetSelector` interroge le VOISINAGE de la cible. `att_rarity` et
        `is_normal_attack` sont les MÊMES clés (même nom, même résolveur, même tri-état) que celles
        déjà posées sur le canal ATTAQUE et sur l'`att_ctx` du canal défenseur non-aura — pas un
        nommage neuf. `tgt_adjacent_unit_profiles` = tuple de `(uid, team, visual_id, rarity)` pour
        `AdjacentUnits(<la cible>, unique, 3)` (foyers `damage_model._adjacent_unit_profiles` /
        `prediction._shared._adjacent_unit_profiles`, adjacence NATIVE partagée). TRI-ÉTAT partout :
        `None` = NON MESURÉ -> le gate se FERME ; un tuple VIDE est une mesure (« aucun voisin »).

        Les TROIS dernières clés sont arrivées avec `PsychicStalk_ExtraAttackDamage` (#366-r1), dont
        le trigger ne porte NI sur le porteur NI sur un `CreateTargetSelector` : `IsUnit(caster@0x160)`
        lit l'ATTAQUANT (`att_is_unit`, même clé/sémantique que l'`attacker_ctx["is_unit"]` du canal
        défenseur non-aura), et `EntitiesWithAnyEffect(Tiles(Target@0x178), Fire)` lit les effets
        portés par la TUILE de la cible (`tile_effects_by_pos` = `{(col,row): [noms]}`, même forme
        que le canal déjà monté pour `LetTheGalaxyBurnEffect`). Absentes -> le gate se tait."""
        return None

    def create_effect_crit_chance_bonus_for_attack(self, att_ctx: Mapping | None = None) -> int | None:
        """Bonus de CHANCE de crit (%) — couche calc-time SÉPARÉE de `GetStat(9)`, sommée dans
        `IdunBattle.Core.Services.DamagePrediction$$GetCritChanceBonusFromEffects puis ajoutée à GetStat(9) dans
        `RollCritical` (cc = clamp(GetStat(9)+Σbonus, 0, 100)). Distinct des effets StatModification
        sur la crit-chance (eux DANS GetStat) → pas de double-compte. Défaut None = pas de bonus.

        `att_ctx` = CONTEXTE DU COUP. Le canal natif n'est PAS aveugle :
        `GetCritChanceBonusFromEffects(this, attaquant, defenseur, abilityOrEffect, hitIndex)`
        construit LUI-MÊME l'`IdunBattle.Entities.Abilities.AbilityEntities` (caster = owner =
        l'attaquant, target = le défenseur, plus l'`AbilityOrEffect` du coup et l'index de coup)
        avant d'évaluer le trigger de chaque `EffectBonus` par le slot d'interface 0x21 — donc
        `get_OwnerIsCaster`, `IsMeleeAttack`, `IsNormalAttack` et `StatAmount(Caster, …)` y sont
        TOUS évaluables. C'était le port qui perdait le contexte, exactement comme le résidu `N14`
        du canal crit-DÉGÂT (case-ischarging-crit-channel).

        Clés threadées aujourd'hui par l'agrégateur `crit_chance_bonus_from_effects` (foyer unique =
        `runner/operations/damage.py::AttackDamageOperation._crit_params`) :
          • `is_ranged`          → `IsMeleeAttack` / `IsRangedAttack` (tri-état #106 : nature non
            prouvée ⇒ les DEUX gates se taisent, cf. `is_melee_attack`/`is_ranged_attack`) ;
          • `is_normal_attack`   → `IsNormalAttack` ;
          • `caster_crit_chance` → `StatAmount(Caster, 0x9 CriticalChance, StatPart.Current)`, la
            stat COURANTE de l'attaquant (stat-modifications comprises) — nœud du gate
            `AmountIsGreaterThanZero` de `WarHowl_ExtraDamage_Unstoppable` ;
          • `has_moved`          → `HasFlag(Owner, 0 = UnitFlag.Moved)`, le prédicat de la
            `CreateActiveCondition` d'`InescapableAccuracy_extraCritChance` (1115). Même store que
            le gate no-move déjà porté sur l'axe DÉGÂT (`CrushingStrike`) : `UnitFlagsComponent`.
        Clé absente ⇒ le gate correspondant se TAIT (« présent ≠ appliqué »), jamais une valeur
        devinée."""
        return None

    def create_effect_piercing_bonus_for_attack(self, ctx: Mapping | None = None) -> "int | None":
        """`<Effect>.CreatePiercingBonusForAttack` — contribution ADDITIVE au **ratio de perçage** du coup
        courant (`IdunBattle.Entities.Effects.BaseEffect$$PiercingBonusForAttack` : le cache d'`EffectBonus`
        est évalué contre les `entities` du coup, `ForAddition` → +montant / `ForSubtraction` → −montant),
        consommée par `IdunBattle.Core.Services.DamagePrediction$$GetAttackPiercingDamageRatio`
        (`Min(100, Max(base>0, dirPierce + extraPierce + <ces bonus> + basePiercingRatio))`).

        `ctx` = contexte du coup fourni par l'agrégateur `piercing_bonus_from_effects` :
        `{owner_id, att_id, ability_type, target_traits, owner_ctx, is_ranged, is_overwatch,
        unit_ctx_of}` — de quoi évaluer les gates natifs `get_OwnerIsCaster` (owner_id == att_id),
        `CurrentAbilityIs(<abilityOrEffect>)`, `HasTrait(target, …)` et la disjonction
        `IsRangedAttack | IsOverwatchAttack` (Hailstrike_ExtraPierce). `is_ranged` suit la convention
        tri-état #106 (None = nature non threadée ⇒ les DEUX gates se taisent) ; `unit_ctx_of` =
        résolveur `unit_id -> UnitContext` (mirror `GetAbilityState(effect)` quand la SOURCE de l'effet
        n'est pas son porteur). Défaut None = pas de contribution (la quasi-totalité des effets)."""
        return None

    def create_effect_crit_damage_bonus_for_attack(self, att_ctx: Mapping | None = None) -> int | None:
        """`<Effect>.CreateCritDamageBonus` — bonus de DÉGÂT de crit, couche calc-time SÉPARÉE de
        `GetStat(10)`, sommée dans `IdunBattle.Core.Services.DamagePrediction$$GetCritDamageBonusFromEffects`
        puis ajoutée à GetStat(10) dans `IdunBattle.Core.Services.DamagePrediction$$CalculateCriticalDamage`
        (critDmgPct = max(0, GetStat(10)+Σbonus)). Défaut None = pas de bonus.

        `att_ctx` = CONTEXTE DU COUP. Le canal natif n'est PAS aveugle : `CalculateCriticalDamage(this,
        attaquant, cible, …)` passe **les deux entités** à `GetCritDamageBonusFromEffects`, qui construit
        lui-même l'`IdunBattle.Entities.Abilities.AbilityEntities` (caster = owner = l'attaquant, target =
        la cible) avant d'évaluer le trigger de chaque `EffectBonus` par le slot d'interface
        `IdunBattle.Entities.Effects.BaseEffect$$CritDamageBonus`. Les nœuds `get_OwnerIsCaster`,
        `IsCharging(owner, target)`, `HasTrait(target, …)` y sont donc TOUS évaluables — c'était le PORT
        qui perdait le contexte, pas le natif (résidu `N14`, case-ischarging-crit-channel).

        Clés threadées aujourd'hui par l'agrégateur `crit_damage_bonus_from_effects` (foyer unique =
        `runner/operations/damage.py::AttackDamageOperation._crit_params`) :
          • `is_charging` → `IdunBattleLogic.Entities.DSLTriggers$$IsCharging(owner@0x148, target@0x178)`,
            lue par le gate partagé `is_charging_attack(att_ctx)`.
        Clé absente ⇒ le gate correspondant se TAIT (« présent ≠ appliqué »), jamais une valeur devinée."""
        return None

    def create_effect_damage_malus_for_defense(self, is_melee: bool | None = None,
                                                damage_profile: str | None = None,
                                                attacker_ctx: Mapping | None = None) -> EffectBonus | None:
        """`<Effect>.CreateEffectDamageMalusForDefense` — contribution DÉFENSEUR (l'effet est sur la CIBLE,
        MODIFIE le dégât reçu). Symétrique de `create_effect_damage_bonus_for_attack`. `is_melee` = nature
        du coup (certains malus sont gated `IsMeleeAttack`, ex. Terrifying_ExtraDefense) ; `damage_profile`
        = NOM du profil de dégât de l'attaque (certains malus sont gated `DamageProfileIs`, ex.
        TerminatorArmour réduit SAUF Psychic/DirectDamage). `attacker_ctx` = contexte de l'ATTAQUANT (source
        du coup) `{id, ability_level, multiplier}` — pour les malus gated sur l'IDENTITÉ de l'attaquant
        (ex. Neuroparasite : `AreEqual(BondedEntity, damageSource)` = seul LE Neurothrope qui a infecté
        bénéficie du +dégât ; sa magnitude `ConfigVar(source ability state)` s'indexe sur SON niveau/mult).

        CONTENU d'`attacker_ctx` — chaque clé = **UN nœud DSL natif porté sur `caster@0x160`** (l'attaquant
        du coup dans le contexte d'évaluation d'un `DamageBonus`/`DamageMalus`), JAMAIS un besoin d'effet :
          • `id`                → `Entity(caster@0x160)` (identité, gate `AreEqual`) ;
          • `ability_level` / `multiplier` → l'`AbilityState` du caster (indexation `ConfigVar`) ;
          • `is_normal_attack`  → `IsNormalAttack` ;
          • `faction`           → `HasFaction(caster, <FactionId>)` ;
          • `is_unit`           → `IsUnit(caster@0x160)` ;
          • `team`              → l'équipe du caster, membre GAUCHE d'`AreFriends(caster, …)` ;
          • `team_by_id`        → `{unit_id: team}`, requis pour résoudre le membre DROIT d'un
                                  `AreFriends(caster, <autre nœud entité>)` — typiquement
                                  `EffectSource(Effect@0x150)` = `eff.source`, qui n'est PAS l'attaquant ;
          • `traits`            → `HasTrait(caster, …)` (noms gameconfig), dont `IsMechanical(caster)`
                                  = `AmountIsEqualOrGreater(TraitAmount(caster, Mechanical), 1)` ;
          • `rarity`            → `HasRarity(caster@0x160, idun.meta.Rarity.Mythic = 5)`
                                  (`BaseUnitComponent.Rarity` @+0x74), #999-r3-r1. TRI-ÉTAT :
                                  `None` = NON MESURÉ ⇒ le gate se FERME — jamais `Rarity.Common`
                                  en repli, qui accorderait le bonus à toute unité non mesurée.
                                  Consommateur : `HyperCorrosiveAcid_ExtraDamagePct` (1448).
        UNE clé fait exception et porte sur `Owner@0x148` (= le PORTEUR de l'effet, donc la CIBLE du
        coup) et non sur le caster — parce que le nœud natif, lui, porte sur l'Owner :
          • `is_turn_of_owner`  → `IsTurnOf(Owner@0x148)`, lu par le foyer `is_turn_of_owner(ctx)`
                                  ci-dessus (gate de `1110 FireAndReposition_ReduceDmg`).
        Clé absente ⇒ le gate correspondant se TAIT (« présent ≠ appliqué »), jamais une valeur devinée.
        Renvoie un `EffectBonus` (`PercentDecrease` de réduction OU `ForAddition` positif type Neuroparasite,
        gated par une condition d'effet) ou None.

        RE : `IdunBattle.Core.Services.DamageCalculations$$CalculateDefenderModifiersForPrediction itère les effets de la cible et appelle
        cette méthode (interface effet, slot 0x1a) sur chacun → accumule un `DamageModifiers` (%-list).
        La famille `ADamageDefenseModifierAbilityEffect` (CloudOfFlies/ContemptuousDisregard/ForwardObservers/
        HuntersInstincts/… IdunBattle.Entities.Effects.ADamageDefenseModifierAbilityEffect$$CreateEffectDamageMalusForDefense→IdunBattle.Entities.Effects.BaseEffect$$DamageMalusForDefense) = `EffectBonus(PercentDecrease,
        ConfigVar(key))` gated (ex. ContemptuousDisregard IdunBattle.Entities.Effects.Loki.ContemptuousDisregard_DamageReductionEffect$$CreateEffectDamageMalusForDefense : OwnerIsTarget & HasUsedActiveAbilityThisTurn
        → ConfigVar 0x46). Défaut None = effet sans réduction défensive (dégradation fidèle)."""
        return None

    def create_piercing_bonus_for_attack(self, damage_profile: str | None = None,
                                         is_melee: bool | None = None,
                                         attacker_ctx: Mapping | None = None) -> EffectBonus | None:
        """`<Effect>.CreatePiercingBonusForAttack` — slot d'interface DISTINCT de
        `CreateEffectDamageBonusForAttack` : il alimente l'axe PERCAGE (`DamageModifiers` @+0x20), PAS le
        scalaire degat. Mirror : `EffectBonus.ForPiercing(trigger, montant)`
        (`IdunBattle.Entities.Effects.EffectBonus$$ForPiercing`).

        Porte ici pour la variante **OwnerIsTarget** (l'effet vit sur la VICTIME et bonifie le percage de
        QUI l'attaque) : `IdunBattle.Entities.Effects.Loki.Supercharge_ExtraPiercingEffect$$CreatePiercingBonusForAttack`
        = `ForPiercing(DamageProfileIs(GetDamageProfile(config)) & get_OwnerIsTarget,
        ConfigVar(0x3f=extraPierceRatio))`. Agrege par `build_defender_modifiers_from_effects` (boucle des
        effets de la CIBLE) puis fusionne dans le percage effectif par
        `AttackDamageOperation._apply_defender_flat_reductions`.

        `damage_profile` = NOM du profil du coup (gate `DamageProfileIs`) ; `is_melee` = nature du coup
        (gate `IsMeleeAttack`, et branche du `If` de `AllIsDustEffect$$GetPierceStatModifier`).

        `attacker_ctx` (#1052) = le MEME dict que `create_effect_damage_malus_for_defense` recoit --
        les noeuds natifs portes sur `Caster@<DSLSelectors+0x48>` que ce slot doit lire. Trois cles
        y ont ete AJOUTEES pour `AllIsDustEffect`, aux DEUX faces (combat et prediction) :
        `extra_pierce` (`StatAmount(Caster, 0x1a = ExtraPierce, 0x5 = Modification)`),
        `extra_pierce_dir` (`StatAmount(Caster, 0x15|0x16, Modification)`) et
        `effect_pierce_addition` (`CasterEffectPierceAddition`). Cle absente = NON MESURE -> le
        consommateur se tait. Defaut None = pas de bonus de percage."""
        return None

    def block_source_id(self, fallback_chance: int = 0) -> int:
        """`BlockChanceInfo.entityId` (@+0x0) de la source de block que CET effet pose — l'identite
        testee par `Contains(failedBlockIds, entityId)` dans
        `IdunBattle.Core.Services.DamageCalculations$$CalculateBlockChances` et poussee par
        `IdunBattle.Core.Services.BlockDamageInfo$$AddFailedBlockId` (signature Frida :
        `failedBlockIds: System.Collections.Generic.List<IdunBattle.Core.BEntityId>`) apres un jet
        rate. Natif = l'ENTITE-EFFET (la cle du dictionnaire par-entite du `MultiValueStatComponent`),
        exactement comme la cle de `ValueModification` (cf. `effect_stat_mod_key`) ; offline l'entite
        n'existe pas, l'identite stable est le `effect_type` (une seule instance d'un type ExtraBlock
        par porteur : `DaemonAbility$$CreateUpdateEffectBehaviour` fait `RemoveEffect(0x40a)` AVANT
        de re-poser). `fallback_chance` = repli (effet sans `effect_type` seede) ; il vaut l'ancien
        comportement, donc jamais pire. **Ne PAS utiliser la chance comme id** : deux sources de meme
        chance se confondraient dans l'exclusion inter-coups de `_run_hits` (un tirage perdu)."""
        et = getattr(self, "effect_type", None)
        return int(et) if et else int(fallback_chance)

    def create_effect_block_source_for_defense(self, defender_fixed_armor: int = 0,
                                               defender_attack: int = 0,
                                               defender_max_health: int = 0):
        """`<Effect>.CreateAddBlockEffectBehaviour`/`AddExtraBlockEffectToOwner` IdunBattleLogic.Entities.Abilities.Triggered.Loki.BeastSlayerAbility$$CreateAddBlockEffectBehaviour — source de
        BLOCK SUPPLEMENTAIRE possedee par la CIBLE (defenseur), AJOUTEE a la chaine
        `apply_random_block_damage` EN PLUS du block de base (scalaire `GetStat(7/8)`). Renvoie un
        `BlockSource(chance, amount)` ou None (defaut). Ex. BeastSlayer IdunBattleLogic.Entities.Abilities.Triggered.Loki.BeastSlayerAbility$$CreateAddBlockEffectBehaviour :
        chance=`IdunBattleLogic.Entities.Abilities.Triggered.Loki.BeastSlayerAbility$$GetBlockChance`=beastSlayerBlockChance ; amount=`IdunBattleLogic.Entities.Abilities.Triggered.Loki.BeastSlayerAbility$$GetBlockDamage`=
        blockDmgPct% du FixedArmor COURANT du defenseur. Ces entrees sont ABSENTES du scalaire GetStat(7/8)
        (verifie live 2026-07-09 : orksNob blockChance=0 alors que BeastSlayer donne +10%) -> le natif les
        tient dans `GetMultiValueStat(7)` (`IdunBattle.Core.Services.DamageCalculations$$CalculateBlockChances`). `defender_fixed_armor` =
        FixedArmor courant de la CIBLE (pour les sources dont l'amount depend de l'armure). #72.
        `defender_attack` = stat Attack COURANTE de la CIBLE (sources type Daemon_ExtraBlock, #54A).
        `defender_max_health` = `GetStat(cible, Health = 5, StatPart.Maximum = 2)` -- le TROISIEME
        substrat de cette famille, LU dans `IdunBattleLogic.Entities.Abilities.Triggered.Loki.
        BeastSnaggaAbility$$CreateBehaviour` : `PercentageOf(StatAmount(Owner@<DSLSelectors+0x30>,
        statType 0x5, statPart 0x2), Direct(GetNumberConstant(0x36)))` (#1015-r1). Il s'ajoute aux
        deux autres exactement comme `defender_attack` s'est ajoute a `defender_fixed_armor` : le
        natif n'a qu'UN accumulateur (`GetMultiValueStat(7)`), et chaque source y calcule son amount
        depuis la stat de son choix. `0` = non threade -> la source rend `None` plutot qu'un amount
        devine."""
        return None

    def get_armor_penetration(self, is_normal_attack: bool = True) -> int | None:
        """`<Effect>.IgnoreArmor` — pénétration d'armure (axe armure : armor_eff = max(armure − pén, 0)).
        `is_normal_attack` : certaines pénétrations sont gated attaque normale (i2 PowerTrip
        « NORMAL attacks ignore X Armour » — GROUND TRUTH step-13 : DakkaDakkaDakka (spéciale) du même
        porteur ne bénéficie PAS des 499 de pénétration, per-coup natif 404/728 vs 78 = armure pleine)."""
        return None

    def additional_hit_groups(self, ctx: Mapping | None = None) -> "list[dict] | None":
        """`<Effect>.CreateAdditionalHits` (`IdunBattle.Entities.Effects.EffectAdditionalHits$$Create`) — coups ADDITIONNELS
        HETEROGENES a degat/profil PROPRE ajoutes a l'attaque du PORTEUR (trigger natif OwnerIsActor/
        OwnerIsCaster, evalue ; +gate nature d'attaque eventuel via `ctx["is_melee"]`, ex. FoulInfusion
        IsMeleeAttack). Renvoie une liste de groupes `{count, profile, ...}` a materialiser APRES les
        coups d'arme dans la MEME chaine prev-threadee (overkill continu). Defaut None = pas de coups
        additionnels. Ex. `SquigHound_AdditionalHits` = 2 coups [minDmg,maxDmg] profil Physical.

        ## DEUX NOEUDS DE DEGAT, DEUX FACES (#159) -- `min`/`max` ET `amount` COEXISTENT

        Le descripteur natif porte **deux** noeuds distincts, et l'evaluateur
        `IdunBattle.Entities.Effects.BaseEffect$$AdditionalHits(this, entities, useDisplay)` choisit
        (lu verbatim, gqfc5mff6c) :

            if (!d.condition.ShouldTrigger(entities))  return default          # slot 5
            count  = d.countNode != null ? d.countNode.Calculate(entities) : 1 # +0x18, slot 1
            amount = d.minNode.<slot 4>(entities)                              # +0x10 noeud DISPLAY
            min = max = amount
            if (!useDisplay) {                                                 # <- FACE COMBAT
                min = d.amountNode.<slot 2>(entities)                          # +0x08 noeud ROLL
                max = d.amountNode.<slot 3>(entities)
            }
            -> AdditionalHitsInfo{ MinMax = MinMaxDamage(min, max), amount, count, profile, ... }

        et `IdunBattle.Operations.AdditionalHitsFromEffects$$GetAdditionalHitsData` bat l'AttackData
        de chaque groupe par `IdunBattle.Core.HitDamage$$.ctor(min, Nullable(max))` DEPUIS ce
        MinMaxDamage. Qui passe quoi :
          - **COMBAT** -> `IdunBattle.Operations.AttackDamageOperation$$ExecuteAdditionalHitsWithout
            DamageProfileType` appelle `...$$GetAdditionalHitsFromEffectsInternal` avec l'octet
            EXPLICITEMENT MIS A ZERO (`in_stack & 0xffffff00`) => `useDisplay = false` => bornes =
            le noeud **ROLL** ;
          - **PREDICTION** -> `IdunBattle.Entities.Abilities.AActiveAbility$$GetAdditionalHitsFrom
            EffectsForPrediction` => cellule DEGENEREE `(amount, amount)`, que le pipeline de
            prediction etale ensuite (`DamageCalculations$$CalculateDamageSpread`, +-20 %).

        D'ou le CONTRAT du dict rendu ici -- les deux cles ne s'excluent PAS :
          - `min`/`max` = les bornes du noeud **ROLL** -> lues par la face COMBAT
            (`runner/operations/additional_hits.py::execute_additional_hits`) ;
          - `amount`    = la valeur du noeud **DISPLAY** -> lue par la face PREDICTION
            (`playbook/prediction/normal_attack.py`, qui teste `"amount" in g` EN PREMIER).
        Un descripteur dont les deux noeuds sont le MEME (`param_8 = 0` dans
        `EffectAdditionalHits$$Create` -> `minNode` retombe sur `amountNode`, ex. FoulInfusion /
        ExplosiveMaladies) n'a qu'une forme a rendre. Un descripteur a noeuds DISTINCTS
        (FleshmetalGuns : `RandomAmount(a,b)` vs `Average(a,b)` ; CyclicIonBlaster :
        `RandomAmount(min,max)` vs `min` seul) DOIT rendre LES DEUX -- ne rendre que `amount`
        faisait etaler la face COMBAT a +-20 % autour de la moyenne au lieu de tirer dans
        [min, max] (residu #159 (a), mesure live 8/8 contre 0/8 :
        cf. `docs/rl/case-159-rng-canal179-et-maybe-ltgb.md`)."""
        return None

    def create_aura_additional_hits_for_ally(self, ctx: Mapping) -> "dict | None":
        """`<Effect>.CreateAdditionalHits` d'un effet HOSTE SUR UNE AUTRE ENTITE QUE L'ATTAQUANT
        (ex. ExplosiveMaladies IdunBattle.Entities.Effects.Loki.ExplosiveMaladies_ExtraRangedAttackEffect$$CreateAdditionalHits/IdunBattle.Entities.Effects.Loki.ExplosiveMaladies_ExtraMeleeAttackEffect$$CreateAdditionalHits + selecteur IdunBattle.Entities.Effects.Loki.ExplosiveMaladies_ExtraRangedAttackEffect$$CreateTargetSelector `AdjacentFriends(owner, 1)`) — geometrie
        re-evaluee a la TUILE CANDIDATE, modele #49/#153 : rien n'est poste sur le beneficiaire.

        #204 — « for_ally » est un raccourci HISTORIQUE : le natif enumere les descripteurs
        GLOBALEMENT (`IdunBattle.Operations.AdditionalHitsFromEffects$$GetAdditionalHitsFromEffects
        Internal`) et laisse la CONDITION trancher. Ce hook porte donc les DEUX conditions :
          - `get_OwnerIsCaster` (porteur = attaquant : ExplosiveMaladies, InfernalPacts, AstartesBanner) ;
          - `get_OwnerIsTarget` (porteur = CIBLE de l'attaque : MasterAnnihilator_AdditionalHitEffect).

        `ctx` = {att_id, att_pos, att_team, att_faction, att_grand_alliance, att_traits, is_melee,
        owner_id, owner_pos, owner_team, owner_mult, owner_ablvl, owner_grand_alliance, owner_faction,
        tgt_id, t_pos, damage_profile, attack_hit_damage} (owner_* = le porteur ; att_traits = traits
        gameconfig de l'attaquant, gate Daemon d'InfernalPacts #202-B ; `tgt_id` EST le predicat
        `OwnerIsTarget` ; `damage_profile` le noeud `AreEqual(CurrentAttackDamageProfile, .)` ;
        `attack_hit_damage` le noeud `FirstHitInCurrentAttackDamageRange`, absent hors attaque).
        Renvoie UN groupe `{count, amount|min/max, profile}` ou None (gates non satisfaites)."""
        return None

    # ── stat-modification (famille AStatModifierEffect) ─────────────────────────────────────────────
    def get_stat_modification_stat(self) -> "int | None":
        """`IdunBattle.Entities.Effects.AStatModifierEffect$$GetStatModificationStat` — le **StatType** que CET effet
        modifie (natif : `EffectComponent+0x10`). `None` = l'effet n'est pas un StatModifier (défaut).
        Un effet StatModification écrit sa magnitude dans la **modification** du stat (part 5/9),
        attribuée à sa source, appliquée via `ChangeStat` (cf. `UnitStats.change_stat`)."""
        return None

    def get_stat_modification_amount(self) -> "int | None":
        """`IdunBattle.Entities.Effects.StaticStatModifierEffect$$GetStatModificationAmount` (natif : `EffectComponent+0x14`,
        fixe) / `IdunBattle.Entities.Effects.ADynamicStatModifierEffect$$GetStatModificationAmount` (calculé).
        Magnitude (delta additif) ajoutée à la modification du StatType de
        `get_stat_modification_stat`. `None`/0 = aucune (défaut). Un effet StatModification concret
        override les deux (StatType + magnitude, typiquement depuis sa config d'ability)."""
        return None

    def captured_stat_mod_amount(self) -> "int | None":
        """La magnitude que le NATIF a ECRITE dans le `StatModifierComponent` de cette instance
        (`Amount` = `+0x14`), telle que la capture la publie -- c'est-a-dire EXACTEMENT ce que
        `StaticStatModifierEffect$$GetStatModificationAmount` relit.

        A PREFERER a toute re-derivation gameconfig quand elle est disponible : la re-derivation
        suppose qu'on sache retrouver l'`AbilityState` du POSEUR, ce qui est faux pour un buff
        cross-unite dont la feuille de pose passe `source = null` (`ShockAssault_Buff` 1000,
        `SereneUnifierStormOfFire` 1171).
        `None` = canal absent (pose OFFLINE, ou capture sans `statMod`) -> l'appelant retombe sur sa
        derivation, et DOIT dire ce qu'elle vaut dans ce regime.

        ⚠ GATE `IsDynamic` -- c'est le DISPATCH NATIF, pas une prudence : seul
        `IdunBattle.Entities.Effects.StaticStatModifierEffect$$GetStatModificationAmount` relit
        `+0x14` ; `IdunBattle.Entities.Effects.ADynamicStatModifierEffect$$GetStatModificationAmount`
        appelle le slot virtuel `+0x798` (`GetDynamicStatModificationAmount`) et RECALCULE. Pour un
        effet DYNAMIQUE le `+0x14` n'est donc PAS la magnitude : le champ vaut ce que la feuille de
        pose y a mis (les surcharges `AddDynamicStatModifierEffect*` ne passent AUCUN `amount` ->
        `IdunBattle.Entities.Behaviours.AddStatModifierEffectBehaviour$$Execute` ecrit 0). Rendre 0
        serait pire qu'une derivation approchee, d'ou le `None`. MESURE 2026-08-01 : `IsDynamic = 0`
        sur `1171` (les deux porteurs) et `1000`, les deux seuls consommateurs actuels."""
        sm = self.stat_mod
        if not isinstance(sm, Mapping):
            return None
        if sm.get("IsDynamic"):
            return None
        v = sm.get("Amount")
        return int(v) if isinstance(v, (int, float)) else None

    def captured_stat_mod_stat(self) -> "int | None":
        """Le **StatType** que le NATIF a ECRIT dans le `StatModifierComponent` de cette instance
        (`StatType` = `+0x10`) -- litteralement ce que retourne
        `IdunBattle.Entities.Effects.AStatModifierEffect$$GetStatModificationStat`.

        Jumeau EXACT de `captured_stat_mod_amount` sur l'autre champ de la paire native, et SANS son
        gate `IsDynamic` : le stat est relu au MEME endroit par TOUTE la famille (`AStatModifierEffect`
        est le foyer, statique comme dynamique), c'est seulement le MONTANT qui bifurque.
        `None` = canal absent -> l'appelant retombe sur le litteral de sa feuille de pose."""
        sm = self.stat_mod
        if not isinstance(sm, Mapping):
            return None
        v = sm.get("StatType")
        return int(v) if isinstance(v, (int, float)) else None

    def reverted_stats(self) -> "list":
        """StatTypes que `<Effect>.RevertInternal` annule quand l'effet est RETIRÉ (mirror des `ChangeStat`
        posés par `ApplyModification`, reverté par-source via la clé `stat_mod_source`). C'est la part DATA
        (côté `entities/`) que la feuille runner `RemoveEffect` lit pour exécuter le revert (`revert_change_stat`,
        côté `runner/`) — l'interface `get_stat_modification_stat` est SINGULIÈRE et ne couvre pas un effet
        multi-stat (ex. ActOfFaith = crit-chance ET crit-damage), d'où la liste.

        DÉFAUT = le stat de `get_stat_modification_stat()` (mirror EXACT de la paire native
        `IdunBattle.Entities.Effects.AStatModifierEffect$$ApplyModification` /
        `IdunBattle.Entities.Effects.AStatModifierEffect$$RevertModification` : les DEUX construisent leur
        `Position(stat, part)` depuis le MÊME `(**vtable+0x728)` = `GetStatModification()`, seule la `part`
        change — 5/9 à l'apply, 6 au revert). Autrement dit un `AStatModifierEffect` reverte TOUJOURS le stat
        qu'il modifie ; il n'y a pas de famille « modifie mais ne reverte pas » côté natif. `[]` (défaut
        effectif) pour tout effet non-StatModifier."""
        st = self.get_stat_modification_stat()
        return [] if st is None else [int(st)]

    def overridden_stats(self) -> "list":
        """Part DATA d'un `ApplyInternal` qui OVERRIDE des stats du porteur (part 7, `ChangeStat` mode 4)
        aux valeurs **CURRENT du PARENT** du porteur — cas `MV71SniperDroneSquad_InitialDmgEffect
        IdunBattle.Entities.Effects.Loki.MV71SniperDroneSquad_InitialDmgEffect$$ApplyInternal` (4 stats). La couche runner (`AddEffectOperation._apply_stat_overrides`) SNAPSHOTE la
        valeur du parent (= `eff.source`, mirror `GetParentUnit`) et exécute `apply_stat_override`
        (part 7 → SetOverride) ; le retrait exécute `remove_stat_override` (part 8, mirror `IdunBattle.Entities.Effects.Loki.MV71SniperDroneSquad_InitialDmgEffect$$RevertInternal` → ResetStat ×N). Défaut `[]` = pas d'override."""
        return []

    def applied_stat_overrides(self) -> "list":
        """Part DATA d'un `IdunBattle.Entities.Effects.StatOverrideEffect$$ApplyInternal` — les
        `(StatType, valeur, isModifiable)` que CET effet pose en OVERRIDE, et que
        `IdunBattle.Entities.Effects.StatOverrideEffect$$RevertInternal` retire.

        NATIF, lu verbatim :

            ApplyInternal :  ChangeStat(Entity(target), Position(<comp+0x10>, part 7 = OVERRIDE),
                                        mode 4, Direct(<comp+0x14>), Entity(effect),
                                        3, <this+0x480 = isModifiable>, <comp+0x18 = isHidden>)
            RevertInternal : ChangeStat(Entity(target), Position(<comp+0x10>, part 8 = REMOVE),
                                        mode 4, <Formulas+0x18>, Entity(effect), 0, 0, isHidden)

        `<comp>` = le `StatOverrideComponent` de l'ENTITE-EFFET (blueprint
        `IdunBattle.Entities.Blueprints$$StatOverrideEffect`), rempli a la pose par
        `IdunBattle.Entities.Behaviours.AddStatOverrideEffectBehaviour$$StatOverrideBuilder`
        (`+0x10 = statType`, `+0x14 = amount` — le noeud `amount` de la feuille DEJA EVALUE —,
        `+0x18 = isHidden`). `isModifiable` vit sur le DEF (`+0x480`), ecrit par
        `IdunBattle.Entities.Effects.StatOverrideEffect$$.ctor` : il decide si les modifications
        par-source s'ajoutent A l'override (`IdunBattle.Entities.Components.ValueOverride$$
        GetOverrideValueWithModification` = `override + (isModifiable ? modTotal : 0)`).

        DISTINCT d'`overridden_stats()`, qui mirrore
        `IdunBattle.Entities.Effects.Loki.MV71SniperDroneSquad_InitialDmgEffect$$ApplyInternal` :
        la valeur y est LUE SUR LE PARENT a l'application, donc la classe ne declare que des
        StatTypes et la couche runner va chercher la valeur. Ici la valeur EST une donnee de
        l'effet -> le triplet complet.

        ⚠ Le `StatOverrideComponent` n'est PAS publie par la capture (`frida/hooks/game/effects.ts`
        ne lit que le `StatModifierComponent`) : la valeur est RE-DERIVEE de gameconfig, comme
        toute magnitude sans canal `statMod`. Defaut `[]` = l'effet ne pose aucun override."""
        return []

    def ability_modifications(self) -> "list":
        """Part DATA d'un `ApplyInternal` qui ecrit des **modifications de constantes d'ABILITY** sur une
        unite (et NON une stat) — natif `IdunBattle.Operations.OperationProcessor$$AddUnitActiveAbilityModification`
        -> `IdunBattle.Operations.AddUnitActiveAbilityModificationOperation$$Execute` ->
        `IdunBattle.Entities.Components.ActiveAbilityModificationsComponent$$Add(key, delta)`.

        Rend une liste de `(key, delta)` ou `key` = l'index de constante d'ability (`AbilityVarOrConst`,
        ex. `0x10` = nrOfSummons, `0x16` = range) et `delta` = le montant ADDITIF. Le `RevertInternal`
        natif rejoue LES MEMES appels en `-delta` -> la couche runner reverte en niant cette liste (pas
        de table separee). Defaut `[]` = l'effet n'ecrit aucune modification d'ability.

        Unique porteur du build : `IdunBattle.Entities.Effects.Loki.ListenUpMaggotsEffect` (0x426)."""
        return []

    def ability_modifications_target_selector(self):
        """`<Effect>.CreateTargetSelector` — le selecteur des entites sur lesquelles `ApplyInternal`
        ecrit ses `ability_modifications` (natif : `ApplyInternal(this, .., target, ..)` est appele PAR
        CIBLE rendue par ce selecteur). `None` (defaut) = le PORTEUR lui-meme.

        `IdunBattle.Entities.Effects.Loki.ListenUpMaggotsEffect$$CreateTargetSelector` = `Parent(Self@0x148)`
        -> l'effet est PORTE par Kell mais MODIFIE son parent (Creed)."""
        return None

    def writes_forced_attack_targets(self) -> bool:
        """Part DATA d'un `ApplyInternal` qui ÉCRIT la liste de cibles d'attaque FORCÉES du porteur
        (`ForcedAttackTargetsComponent`, cf. `engine/runner/components.py`) — le TAUNT.

        NATIF, `IdunBattle.Entities.Effects.TauntedEffect$$ApplyInternal` (queue de la fonction,
        après les trois `AddSubEffectWithSameTurns`) :

            comp = target.GetComponent<ForcedAttackTargetsComponent>();
            list = new List<int>(); list.Add(ABondEffect.BondedEntityId(this, effect));
            comp.<+0x50> = list;

        et `TauntedEffect$$RevertInternal` : `comp.<+0x50> = new List<int>()`.

        La VALEUR écrite n'est PAS une donnée de la classe : c'est le `BondedEntityId` de
        l'INSTANCE (`BaseEffect.bonded`, écrit à la pose par `AddEffectBehaviour$$
        DefaultBondEffectBuilder`). La classe ne déclare donc que le FAIT d'écrire ; la couche
        runner (`AddEffectOperation._apply_forced_attack_targets`) va chercher le bonded.

        Défaut `False` = l'effet n'écrit aucune cible forcée. Unique porteur porté :
        `TauntedEffect` (27 `Taunted_OnlySpecificTargets`)."""
        return False

    def applied_traits(self) -> "list":
        """Part DATA d'un `ApplyInternal` qui ACCORDE des TRAITS au porteur — le couple
        `OperationProcessor$$AddTrait` / `$$RemoveTrait`, et jamais l'un sans l'autre.

        NATIF, le porteur LU de ce canal est `IdunBattle.Entities.Effects.Loki.
        WarHowl_ExtraDamage_UnstoppableEffect` (0x4c6 = 1222) :

            ApplyInternal (this, owner, target, effect)
                -> <IOperationProcessor @this+0x68>.<slot 0x26>(target, 0x412, isTemporary: 1)
            RevertInternal(this, owner, target, effect)
                -> <IOperationProcessor @this+0x68>.<slot 0x27>(target, 0x412, isTemporary: 1)

        Les deux slots sont resolus par la MEME interface et leur signature
        `(target, trait, isTemporary)` est celle de `IdunBattle.Core.Services.OperationProcessor$$
        AddTrait` / `$$RemoveTrait` -> `IdunBattle.Operations.AddTraitOperation$$Execute` /
        `IdunBattle.Operations.RemoveTraitOperation$$Execute`.

        Rend une liste de `(UnitTrait, is_temporary)`. Le `RevertInternal` natif rejoue LES MEMES
        appels en RETRAIT -> la couche runner reverte en niant cette liste (pas de table separee),
        exactement comme `ability_modifications`. Defaut `[]` = l'effet n'accorde aucun trait.

        ⚠ `is_temporary` n'est PAS decoratif cote natif : il decide de la COLLECTION ecrite
        (`BaseUnitComponent+0x40` permanents / `+0x48` temporaires) et il SUPPRIME la diffusion
        d'evenement (`AddTraitOperation$$Execute` retourne avant la publication quand il vaut 1).
        Cote port, les deux collections sont fondues en un seul ensemble de NOMS
        (`UnitContext.traits`, ce que rend `UnitExtensions$$HasTrait` = la RESULTANTE) : le drapeau
        est donc TRANSPORTE (il documente le call-site lu) mais n'a pas d'observable distinct --
        residu NOMME, pas un oubli."""
        return []

    # ── matérialisation composite ─────────────────────────────────────────────────────────────────
    def overrides_unit_owner(self) -> bool:
        """Part DATA d'un `ApplyInternal` qui BASCULE LE PROPRIÉTAIRE du porteur — l'OWNER-SWAP
        (#590).

        NATIF, `IdunBattle.Entities.Effects.Loki.AttemptedPossession_PossessedEffect$$ApplyInternal`
        — la fonction ENTIÈRE, il n'y a rien d'autre :

            caster = state.<IMatchState slot 41 Get>( ABondEffect.BondedEntityId(this, effect) );
            return processor.<IOperationProcessor slot 127 ChangeUnitOwner>(target, caster);

        et son `$$RevertInternal`, tout aussi court :

            return processor.<IOperationProcessor slot 128 ResetUnitOwner>(target);

        Même forme que `writes_forced_attack_targets` juste au-dessus : la VALEUR n'est pas une
        donnée de la classe (c'est le `BondedEntityId` de l'INSTANCE, `BaseEffect.bonded`), la
        classe ne déclare que le FAIT de swapper. La couche runner
        (`AddEffectOperation._apply_owner_override` / `remove_effect_instance`) va chercher le
        bonded et appelle les deux Operations portées
        (`engine/runner/operations/change_unit_owner.py`).

        Défaut `False`. Unique porteur porté : `1209 AttemptedPossession_Possessed`."""
        return False

    def sub_effects_on_apply(self) -> list[SubEffectSpec]:
        """`<Effect>.ApplyInternal` — sous-effets (enfants) spawnés quand CET effet est appliqué.
        Défaut : aucun (effet simple). Un effet COMPOSITE (ex. Stunned) override pour déclarer ses
        enfants ; `AddEffectOperation` les matérialise après le parent (en propageant le lien parent)."""
        return []

    # ── immunité (gate de POSE) ─────────────────────────────────────────────────────────────────────
    # `IdunBattle.Entities.Effects.BaseEffect$$get_CanBeImmuneTo` — VIRTUEL de `BaseEffect` (slot de
    # vtable `get_CanBeImmuneTo`). Le corps de la BASE est le stub partagé `return 0` ⇒ **False par
    # défaut** : la quasi-totalité des effets ne sont PAS « immunisables ». Attribut de CLASSE simple
    # (pas d'annotation ⇒ pas de field dataclass, surchargeable par la MRO — même régime que
    # `stacks_stat_mod_on_add`).
    #
    # INVENTAIRE : entrée VERSIONNÉE `data/symbols/<build>/metadata/can_be_immune_to.tsv`, dérivée
    # par `probe_175r2_can_be_immune_to.py` sur la FERMETURE TRANSITIVE de `BaseEffect` (464
    # descendants) — DÉCLARATION lue dans le `global-metadata.dat`, VALEUR lue par les OCTETS du
    # corps (`b0 01 c3` / `32 c0 c3`) dans le bloc `methodPointers`, avec contrôle d'alignement.
    # **13** classes à `true`, dont **8 qui déclarent** (`DespoiledGroundEffect`,
    # `BlockTileMovementEffect`, `BlockUnitMovementBondEffect`,
    # `ContagionsOfNurgle_ArmorReduction_Effect`, `ContaminatedEffect`, `PinnedEffect`,
    # `StunnedEffect`, `TauntedEffect`) et 5 qui HÉRITENT de `BlockTileMovementEffect`.
    # ⚠ L'inventaire qui vivait ICI (7 classes, « et RIEN d'autre ») venait de
    # `probe_224_can_be_immune_to.py`, qui comparait la VA du corps à trois LITTÉRAUX d'un build
    # ANTÉRIEUR : sur `rnca9r7q6c` il rendait **0** classe à `true` et classait les **10** classes
    # sondées en « `EntityIsImmuneToEffect` SURCHARGÉ » alors que 9 pointaient sur le corps de
    # `BaseEffect` lui-même. Il est réparé (les corps s'identifient par leurs OCTETS) ; sa liste
    # d'alors omettait `StunnedEffect`/`TauntedEffect`/`BlockUnitMovementBondEffect` et
    # SUR-annonçait `ContagionsOfNurgle_ArmorReduction_Effect`, que la classe Python tenait à
    # `False` dix lignes plus bas (#175-r2).
    # Recoupé par l'i2 du trait `Immune` : « immune to special hexes and hex effects, and cannot
    # have its Armour, hits, Movement or Range reduced ».
    can_be_immune_to = False

    # ── survie au CHANGEMENT DE PROPRIETAIRE (#982-r4) ──────────────────────────────────────────────
    # `IEffect` slot **3** = `get_KeepOnChangeOwner` (nom LU dans
    # `data/symbols/<build>/metadata/interface_slots.tsv`, jamais deduit). Le corps de la BASE est
    # `b0 01 c3` (`mov al,1 ; ret`) ⇒ **True par defaut** : un effet SURVIT au changement de camp.
    # C'est ce que consulte `IdunBattle.Operations.ChangeUnitOwnerOperation$$RemoveEffects`, qui met
    # l'effet dans la liste de SUPPRESSION quand le getter rend **FAUX** (noter le sens du test).
    #
    # INVENTAIRE, derive OFFLINE sur la FERMETURE TRANSITIVE de `BaseEffect` — **465** classes,
    # **0 INCONNU** (`probe_982r4_keep_on_change_owner.py`, qui reutilise la machinerie de
    # `probe_175r2_can_be_immune_to.py` : DECLARATION lue dans le `global-metadata.dat`, VALEUR lue
    # par les OCTETS du corps dans le bloc `methodPointers`). **DEUX** classes declarent, et les deux
    # rendent `32 c0 c3` (`xor al,al ; ret`) : `IdunBattle.Entities.Effects.TauntedEffect` et
    # `IdunBattle.Entities.Effects.Loki.HolyDuel_TauntEffect`. Les 463 autres HERITENT du `true`.
    # ⚠ Une derivation par la VTABLE RUNTIME ne suffit PAS ici : IL2CPP ne remplit la vtable qu'a
    # l'INITIALISATION de la classe, et une session ou aucun taunt n'a ete pose ne mesure que
    # **53** classes sur 465 -- elle rend alors << AUCUN override >>, c'est-a-dire un faux zero.
    keep_on_change_owner = True

    def entity_is_immune_to_effect(self, trait_names: "list | None" = None) -> bool:
        """`IdunBattle.Entities.Effects.BaseEffect$$EntityIsImmuneToEffect` — mirror 1:1 (octets relus) :

            bool EntityIsImmuneToEffect(IEntity entity)
                => UnitExtensions.HasTrait(entity, UnitTrait.Immune /* 0x19 = 25 */) && this.CanBeImmuneTo;

        C'est le point d'extension VIRTUEL que le CONSOMMATEUR
        `IdunBattle.Operations.AddEffectOperation$$Execute` interroge sur l'effet-DEF rendu par
        `EffectsDatabase.Get(effectType)` (interface `IEffect` slot 40 ; MÊME appel que
        `IdunBattle.Core.Services.BattleQuery$$IsUnitImmuneTo`) — vrai ⇒ **la pose est ABANDONNÉE**
        (`return 0`), avant même la création de l'entité-effet.

        `trait_names` = les NOMS de traits gameconfig de la cible (`StatsComponent.ctx.traits`) ; une
        entité SANS composant d'unité (tuile) rend `[]` ⇒ jamais immune — mirror de
        `UnitExtensions.HasTrait` qui passe par `GetBaseUnitComponent` (null ⇒ faux)."""
        return bool(self.can_be_immune_to) and has_trait(trait_names, UnitTrait.Immune)

    # ── cycle de vie ────────────────────────────────────────────────────────────────────────────────
    def is_active(self, unit_state: Mapping | None = None) -> bool:
        """`<Effect>.CreateActiveCondition` — l'effet contribue-t-il dans l'état courant ? (défaut : oui)."""
        return True

    @property
    def removed_after_attack(self) -> bool:
        """Retiré en fin de tour si l'unité a attaqué ce tour (cas RapidAssault)."""
        return False

    @property
    def one_shot(self) -> bool:
        """Consommé dès la 1re attaque de l'unité (effets « 1re attaque » stricts)."""
        return False

    @property
    def expired(self) -> bool:
        return self.remaining_turns is not None and self.remaining_turns <= 0
