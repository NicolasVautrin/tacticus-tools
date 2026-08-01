"""Effets de la faction LEAGUES OF VOTANN (case-220 §6.10, lot #113) — namespace natif
`IdunBattle.Entities.Effects.Loki` / base de donnees `IdunBattle.Core.Services.EffectsDatabase`.

Les TROIS stat-mods de ce lot n'ont **aucune classe d'effet dediee** cote natif : ils sont instancies
directement par des lambdas de `IdunBattle.Core.Services.EffectsDatabase$$InitializeEffects` sur la classe
GENERIQUE `IdunBattle.Entities.Effects.DynamicStatModifierEffect` :

    lambda(): new DynamicStatModifierEffect( AbilityType.op_Implicit(<abilityId>), <varKey>, <isNegative>, <flag> )

et leur magnitude sort du corps GENERIQUE
`IdunBattle.Entities.Effects.DynamicStatModifierEffect$$GetDynamicStatModificationAmount` :

    amount = ConfigVar( <abilityId>, EffectSource(Get(entities)), <varKey> ).Invoke(entities)
    return Nullable( this+0x4a4 /*isNegative*/ ? -amount : amount )

-> **le SIGNE du stat-mod est un champ de l'effet** (`isNegative`, +0x4a4), pas une convention du
call-site. Le `ChangeStat` que pose `IdunBattle.Entities.Effects.AStatModifierEffect$$ApplyModification`
utilise `StatPart` **5 = MODIFICATION** (additif) tant que `this+0x482` (isMultiplier) est faux — c'est le
cas des trois.

Lambdas LUES (build gqfc5mff6c) :
  * `IdunBattle.Core.Services.EffectsDatabase.u003Cu003Ec$$u003CInitializeEffectsu003Eb__14_533`
    -> `DynamicStatModifierEffect(AbilityType(0x4c5=1221 AugmentedAssault), 0x30=48 armorReduction,
        isNegative=1, 1)`  ==> **AugmentedAssault_ReduceArmor (0x605=1541)**, MALUS.
  * `IdunBattle.Core.Services.EffectsDatabase.u003Cu003Ec$$u003CInitializeEffectsu003Eb__14_520`
    -> `DynamicStatModifierEffect(AbilityType(0x4b7=1207 AncestralFortune), 0x41=65 extraCritChance,
        isNegative=0, 0)`  ==> **AncestralFortune_ExtraCritChance (0x5cd=1485)**, BONUS.
  * `IdunBattle.Core.Services.EffectsDatabase.u003Cu003Ec$$u003CInitializeEffectsu003Eb__14_519`
    -> `DynamicStatModifierEffect(AbilityType(0x4b7=1207 AncestralFortune), 0x3e=62 extraBlockChance,
        isNegative=0, 0)`  ==> **AncestralFortune_ExtraBlockChance (0x5ce=1486)**, BONUS.
(Cles `IdunBattle.Configuration.AbilityVariableType` : 48=armorReduction, 62=extraBlockChance,
63=extraPierceRatio, 65=extraCritChance -- dump enums du build.)

Le QUATRIEME effet du lot a, LUI, une classe dediee (canal PERCAGE, pas stat-mod) :
  * `IdunBattle.Entities.Effects.Loki.GravitonRifle_ExtraPierceEffect` (0x5cc=1484).

CINQUIEME (case-366-r1-blockhits-purgeresponse) : `IdunBattle.Entities.Effects.Loki.
PurgeResponseEffect` (0x602 = 1538), porte par `votanSmnSteeljack` / `votanNpc2Steeljack` --
canal `BlockHitsReduction`, cf. `PurgeResponseEffect` en bas de module.
"""
from __future__ import annotations

from collections.abc import Mapping

from ...effect_type import EffectType
from ..base import BaseEffect
from ..magnitude import ability_var

_AUGMENTED_ASSAULT = "AugmentedAssault"       # ActiveAbilityType 0x4c5 = 1221 (votanBeserk / Havyr)
_ANCESTRAL_FORTUNE = "AncestralFortune"       # ActiveAbilityType 0x4b7 = 1207 (votanUthar / Uthar)
_GRAVITON_RIFLE = "GravitonRifle"             # ActiveAbilityType 0x4b6 = 1206 (votanIronmaster / Vynn)


def _source_level_mult(effect: BaseEffect, stats_ctx) -> "tuple[int, int]":
    """(niveau d'ability ACTIVE, multiplier de rarete %) qui indexent le `ConfigVar` de l'effet.

    Mirror de `ConfigVar(<abilityId>, EffectSource(...), <varKey>)` : le natif resout la config contre
    l'`AbilityState` de la **SOURCE** de l'effet (celui qui l'a pose), PAS contre le porteur. Cote port,
    `AddEffectOperation` seede ces deux champs sur l'instance depuis le caster (`scale_from_source`) ->
    on les lit sur l'EFFET en priorite ; le `stats_ctx` (ctx du PORTEUR) n'est le repli que pour les
    effets CAPTES one-shot (self-cast : porteur == source)."""
    lvl = effect.active_ability_level
    if lvl is None:
        lvl = effect.ability_level
    if lvl is None and stats_ctx is not None:
        lvl = getattr(stats_ctx, "active_ability_level", None)
    lvl = int(lvl) if lvl is not None else 0
    mult = effect.ability_variables_multiplier
    if (mult is None or int(mult) == 100) and stats_ctx is not None:
        mult = getattr(stats_ctx, "ability_variables_multiplier", 100)
    return lvl, int(mult or 100)


class AugmentedAssaultReduceArmorEffect(BaseEffect):
    """`AugmentedAssault_ReduceArmor` (0x605 = 1541) — stat-mod **FixedArmor(16) NEGATIF** pose sur la
    **CIBLE** de l'attaque par `IdunBattleLogic.Entities.Abilities.Active.Loki.AugmentedAssaultAbility$$ExecuteBehaviour` :

        AddDynamicStatModifierEffect( factory, targets = target@0x178, source = self@0x148,
                                      effectType = 0x605, stat = 0x10 = 16 FixedArmor,
                                      AbilityStateReference, duree = <aucune> )

    SENS TRANCHE AU DECOMPILE (pas au tooltip) sur DEUX etages independants :
      1. QUI porte l'effet — `IdunBattleLogic.Entities.DSLFactory$$AddDynamicStatModifierEffect` (overload
         a 8 args) construit `AddStatModifierEffectBehaviour(.., source=param_3, targets=param_2, ..)` ;
         `IdunBattle.Entities.Behaviours.AddStatModifierEffectBehaviour$$Execute` ITERE le selecteur
         **+0x60 (= targets)** et pose une instance par element, en attribuant la ValueModification a
         **+0x58 (= source)**. Le call-site passe `param_2 = target@0x178` -> la CIBLE porte le malus, le
         caster n'est que la source. (Le helper jumeau `...$$AddDynamicStatModifierEffectToOwner` passe
         `self@0x148` DANS LES DEUX slots -- c'est lui le self-buff, cf. AncestralFortune ci-dessous.)
      2. LE SIGNE — `isNegative = 1` dans la lambda `...EffectsDatabase...b__14_533`, lu par
         `DynamicStatModifierEffect$$GetDynamicStatModificationAmount` (`return isNegative ? -amount : amount`).

    Magnitude = `armorReduction[activeAbilityLevel du caster]` x multiplier de rarete
    (`armorReduction` EST dans `variablesAffectedByRarityBonus` de la config 1221).

    DUREE : le call-site ne passe AUCUN noeud de duree (slot +0x78 = 0) et
    `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Effect$$DefaultAmountOfRounds`
    ne connait PAS 0x605 (switch lu en entier : 0x4f, 0x429/0x48a, 5/0x11/0x12/0x3a/0x4dc/0x5c4 SEULEMENT)
    -> `AddEffectOperation` retombe sur `lVar14 = 0` = **PERMANENT** (« for the rest of the battle », meme
    forme que le jumeau `ChampionOfTheFeast_ReduceArmor`)."""
    stat_mod_source = None   # cle de source ChangeStat (revert par-source via la feuille `RemoveEffect`)

    def applied_stat_mods(self, stats_ctx) -> "list":
        """DATA du `ChangeStat` (StatPart 5 = MODIFICATION) pose a l'application : FixedArmor -=
        armorReduction[level source] x mult. Execute par `AddEffectOperation._apply_stat_mods`."""
        from ...stats import StatType
        lvl, mult = _source_level_mult(self, stats_ctx)
        amt = ability_var(_AUGMENTED_ASSAULT, "armorReduction", lvl, multiplier_pct=mult)
        if not amt:
            return []
        return [(int(StatType.FIXED_ARMOR), -int(amt))]      # isNegative = 1 -> -amount

    def reverted_stats(self) -> "list":
        """Stats annulees par `RevertModification` (lu par la feuille `RemoveEffect`)."""
        from ...stats import StatType
        return [StatType.FIXED_ARMOR]


class AncestralFortuneExtraCritChanceEffect(BaseEffect):
    """`AncestralFortune_ExtraCritChance` (0x5cd = 1485) — stat-mod **CritChance(9)** POSITIF, self-buff du
    caster, 1 round. Pose par
    `IdunBattleLogic.Entities.Abilities.Active.Loki.AncestralFortuneAbility$$ExecuteBehaviour` :

        AddDynamicStatModifierEffectToOwner( factory, 0x5cd, stat = 9 CritChance, TurnsFromRounds(1) )

    (le helper `...$$AddDynamicStatModifierEffectToOwner` met `self@0x148` en source ET en cible -> le
    porteur EST le caster). Magnitude = `extraCritChance[activeAbilityLevel]` (`isNegative = 0`).
    NON rarity-scale : `variablesAffectedByRarityBonus` de 1207 = [minDmg, maxDmg] SEULEMENT --
    `ability_var` applique le multiplier uniquement aux variables listees, donc l'appel avec
    `multiplier_pct` reste correct par construction."""
    stat_mod_source = None

    def applied_stat_mods(self, stats_ctx) -> "list":
        from ...stats import StatType
        lvl, mult = _source_level_mult(self, stats_ctx)
        amt = ability_var(_ANCESTRAL_FORTUNE, "extraCritChance", lvl, multiplier_pct=mult)
        if not amt:
            return []
        return [(int(StatType.CRIT_CHANCE), int(amt))]

    def reverted_stats(self) -> "list":
        from ...stats import StatType
        return [StatType.CRIT_CHANCE]


class AncestralFortuneExtraBlockChanceEffect(BaseEffect):
    """`AncestralFortune_ExtraBlockChance` (0x5ce = 1486) — stat-mod **BlockChance(7)** POSITIF, self-buff
    du caster, 1 round. Jumeau exact du precedent :

        AddDynamicStatModifierEffectToOwner( factory, 0x5ce, stat = 7 BlockChance, TurnsFromRounds(1) )

    Magnitude = `extraBlockChance[activeAbilityLevel]` (lambda `...b__14_519` : varKey 0x3e = 62,
    `isNegative = 0`)."""
    stat_mod_source = None

    def applied_stat_mods(self, stats_ctx) -> "list":
        from ...stats import StatType
        lvl, mult = _source_level_mult(self, stats_ctx)
        amt = ability_var(_ANCESTRAL_FORTUNE, "extraBlockChance", lvl, multiplier_pct=mult)
        if not amt:
            return []
        return [(int(StatType.BLOCK_CHANCE), int(amt))]

    def reverted_stats(self) -> "list":
        from ...stats import StatType
        return [StatType.BLOCK_CHANCE]


class GravitonRifleExtraPierceEffect(BaseEffect):
    """`GravitonRifle_ExtraPierce` (0x5cc = 1484) — OWNER-effect de Vynn (votanIronmaster), ajoute a la
    CREATION de l'unite par le dict natif `GetEffectToBeAddedToOwnerForAbility` (`ActiveAbility` +0x50,
    qui ne contient que `{PlasmaCannon -> PlasmaCannon_Visual, GravitonRifle -> GravitonRifle_ExtraPierce}`).

    `IdunBattle.Entities.Effects.Loki.GravitonRifle_ExtraPierceEffect$$.ctor` =
    `BaseEffect(AbilityOrEffect(0x4b6 = 1206 GravitonRifle), 1)` -> la config lue est celle de l'ability
    1206, au niveau de SON porteur.

    `IdunBattle.Entities.Effects.Loki.GravitonRifle_ExtraPierceEffect$$CreatePiercingBonusForAttack`
    (MIRROR 1:1 du decompile) :

        traitOr = HasTrait(target@0x178, 0x40f = 1039 TerminatorArmour)
                | HasTrait(target@0x178, 0x3f5 = 1013 MkXGravis)
                | HasTrait(target@0x178, 5    = Mechanical)
        gate    = ( get_OwnerIsCaster & CurrentAbilityIs(AbilityOrEffect(0x4b6 = 1206)) ) & traitOr
        return Nullable( EffectBonus.ForAddition( gate,
                             ConfigVar(0x3f = 63 extraPierceRatio, GetAbilityState(this), this+0x60) ) )

    Le montant est **additif au ratio de percage de l'attaque**, consomme par
    `IdunBattle.Core.Services.DamagePrediction$$GetAttackPiercingDamageRatio` :
    `Min(100, Max(base>0, dirPierce + extraPierce + bonusEffets... + basePiercingRatio))`.

    TROIS gates cumulatifs -> l'effet est INERTE hors du cast de GravitonRifle par son porteur contre une
    cible qualifiante ; c'est un canal PERCAGE, pas un stat-mod (aucun `applied_stat_mods`)."""

    #: `HasTrait(target, ...)` du gate — noms gameconfig des `IdunBattle.Entities.Enum.UnitTrait`
    #: 1039 / 1013 / 5 (dump enums du build gqfc5mff6c).
    QUALIFYING_TRAITS = frozenset({"TerminatorArmour", "MkXGravis", "Mechanical"})

    #: `CurrentAbilityIs(AbilityOrEffect(0x4b6))` — ActiveAbilityType de GravitonRifle.
    CURRENT_ABILITY = 1206

    def create_effect_piercing_bonus_for_attack(self, ctx=None) -> "int | None":
        """`CreatePiercingBonusForAttack` — bonus ADDITIF au ratio de percage du coup courant, ou None si
        un gate tombe. `ctx` (fourni par `piercing_bonus_from_effects`) :
        `{owner_id, att_id, ability_type, target_traits}` — `owner_id == att_id` mirror
        `get_OwnerIsCaster`, `ability_type` mirror `CurrentAbilityIs`, `target_traits` mirror les trois
        `HasTrait(target, ...)`. `target_traits is None` (cible inconnue) -> None (« present != applique »)."""
        c = ctx or {}
        oid, aid = c.get("owner_id"), c.get("att_id")
        if oid is None or aid is None or oid != aid:          # get_OwnerIsCaster
            return None
        if c.get("ability_type") != self.CURRENT_ABILITY:     # CurrentAbilityIs(1206)
            return None
        tt = c.get("target_traits")
        if not tt or not (self.QUALIFYING_TRAITS & set(tt)):  # HasTrait(target, 1039|1013|5)
            return None
        lvl, mult = _source_level_mult(self, c.get("owner_ctx"))
        amt = ability_var(_GRAVITON_RIFLE, "extraPierceRatio", lvl, multiplier_pct=mult)
        return int(amt) if amt else None


class PurgeResponseEffect(BaseEffect):
    """`PurgeResponse` (0x602 = 1538) — owner-effect du passif homonyme de l'**Ironkin Steeljack**
    (`votanSmnSteeljack`, summon de `votanMemnyr` via `IronkinSteeljack` 1219 ; et son jumeau npc
    `votanNpc2Steeljack`). SECOND et DERNIER implementeur natif de `BlockHitsReduction`.

    `IdunBattle.Entities.Effects.Loki.PurgeResponseEffect$$.ctor` =
    `BaseEffect(AbilityOrEffect(TriggeredAbilityType 0x5f6 = 1526 PurgeResponse),
    hasAutomaticActivation = 1)` -- la surcharge d'`op_Implicit` appelee est celle qui ecrit le slot
    `TriggeredAbility` (`AbilityOrEffect$$set_TriggeredAbility`), pas `set_Effect`.

    `IdunBattle.Entities.Effects.Loki.PurgeResponseEffect$$CreateBlockHitReductionTrigger`
    (MIRROR 1:1 du decompile, lu a l'assembleur -- UN SEUL appel a `DSLTriggers`, aucun
    `IdunBattle.DSL.AbilityTrigger$$op_BitwiseAnd`) :

        TriggeringAbilityIs( AbilityOrEffect( EffectType 0x3f1 = 1009 Overwatch_AutoAttack ) )

    La surcharge d'`op_Implicit` est ici celle qui ecrit le slot **Effect**
    (`AbilityOrEffect$$set_Effect`) : c'est un `EffectType`, pas un `ActiveAbilityType` (1009 =
    `ResurrectionOrb`) ni un `TriggeredAbilityType` (1009 = `WhipcoilBody`) ni un `UnitTrait`
    (1009 = `Resilient`). Le noeud lit `AbilityEntities+0x98` (`triggerAbilityOrEffect`, via
    `IdunBattleLogic.Entities.AbilityTypeSelector.TriggeringAbilitySelector$$Select`), que
    `IdunBattle.Core.Services.DamagePrediction$$GetAttackHits` remplit depuis le contexte d'attaque.

    ⚠ **AUCUN `get_OwnerIsCaster`, aucun autre conjoint** -- et c'est LE fait porteur de cette
    tranche. Le trigger ne lit RIEN du porteur : ni son identite, ni ses stats, ni ses traits, ni
    sa position. Tant qu'UNE instance ACTIVE de cet effet existe sur le board -- dans n'importe
    quel camp -- TOUTE attaque dont l'AbilityOrEffet declencheur est `Overwatch_AutoAttack` ignore
    les reductions de coups, y compris celle d'un attaquant qui n'a rien a voir avec le porteur.
    C'est PLUS LARGE que la description i2 (« While Overwatching, the Ironkin Steeljack's attacks
    ignore hit reductions ») : le decompile est la verite, la description ne l'est pas. C'est aussi
    ce qui exige le balayage BOARD-WIDE de `block_hits_reduction_from_effects`.

    Le canal est le seul artefact de cette classe : trigger NU (pas d'`EffectBonus`), donc AUCUNE
    variable de config, AUCUNE magnitude -- le seul observable est la CARDINALITE de la salve.

    L'AUTRE moitie du passif -- `IdunBattleLogic.Entities.Abilities.Triggered.Loki.
    PurgeResponse_ActiveOverwatchAbility` (`CreateTrigger` = `On(0x17) & <DSLTriggers+0x28> &
    AmountIsGreaterThanZero(Count(HeroUnits(UnitsFromFaction(AdjacentFriends(Owner, incl. self, 3),
    0x14))))`, `CreateBehaviour` = `ActivateEffect(Owner, 0x3f1)`) -- est HORS de cette tranche :
    elle ARME l'overwatch du Steeljack, elle ne touche pas au canal des coups."""

    #: `TriggeringAbilityIs(<AbilityOrEffect>)` -- le littéral 0x3f1 du `CreateBlockHitReductionTrigger`,
    #: qualifie EFFECT (surcharge `op_Implicit(EffectType)` -> `set_Effect`).
    TRIGGERING_EFFECT_TYPE = int(EffectType.Overwatch_AutoAttack)      # 0x3f1 = 1009

    def block_hits_reduction(self, att_ctx: "Mapping | None" = None) -> bool:
        """MIRROR de `PurgeResponseEffect$$CreateBlockHitReductionTrigger` : un noeud, un seul.

        `att_ctx["trigger_ability_type"]` = `AbilityEntities+0x98` (`triggerAbilityOrEffect`), pose
        par `runner/damage_model.py::build_hits_board` depuis le `triggering_ability` que
        `AttackDamageOperation.execute` recoit -- et dont l'UNIQUE producteur cote port est le
        vecteur OVERWATCH (`triggers/effect_triggers.py`, `OVERWATCH_AUTO_ATTACK`). Cle ABSENTE =
        pas de declencheur = `TriggeringAbilityIs` FAUX (c'est aussi ce que rend le natif quand le
        `Nullable` du slot est vide : cf. `TriggeringAbilityIsNoneTrigger`).

        ⚠ Le port COLLAPSE les trois `Nullable` de l'`AbilityOrEffect` natif (ActiveAbility /
        TriggeredAbility / Effect) en UN entier -- comme le fait deja le canal DEGAT
        (`att_ctx['trigger_ability_type']` de `attacker_modifiers`, #47). Tant que le seul
        producteur de cette cle sur l'axe COUPS est l'overwatch (EffectType 1009), la comparaison
        est exacte ; un futur producteur qui y poserait un `ActiveAbilityType 1009`
        (`ResurrectionOrb`) ou un `TriggeredAbilityType 1009` (`WhipcoilBody`) exigerait de
        materialiser le SLOT. Verrouille par `test_purge_response_gates_offline`."""
        c = att_ctx or {}
        ta = c.get("trigger_ability_type")
        return ta is not None and int(ta) == self.TRIGGERING_EFFECT_TYPE
