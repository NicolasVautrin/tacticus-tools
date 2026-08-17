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

SIXIEME et SEPTIEME (#959) : les DEUX passifs d'AURA du roster, `GrimEfficiency` (1490, `votanUthar`)
et `PredictiveGuidance` (1525, `votanMemnyr`) -- cf. les deux blocs en bas de module et
`docs/rl/case-959-grim-efficiency-predictive-guidance.md`.

HUITIEME (#1001) : `BladeOfTheAncestorsBuffEffect` (0x5d1 = 1489), le buff crit EMPILABLE de la
RELIQUE `R_Crit_BladeOfTheAncestors` (`votanUthar`) -- cf. le bloc en bas de module et
`docs/rl/case-1001-reliques-votann.md`.
"""
from __future__ import annotations

from collections.abc import Mapping

from ...effect_type import EffectType
from ..base import BaseEffect
from ..magnitude import ability_var
from ....entities.active_ability_type import ActiveAbilityType   # #270-r1-r1-r3
from ...ability_constant_type import AbilityConstantType         # #959 (`ConfigConst` du selecteur)
from ...triggered_ability_type import TriggeredAbilityType       # #959 (les deux `.ctor` relus)
from ...traits.unit_trait import UnitTrait                       # #959 (`IsMechanical`)
from ...unit_faction import UnitFaction                          # #959 (`HasFaction`)
from ...stats import StatType
# FORME B (#930) : `surrounding_friends` reste patchable au foyer. Import ABSOLU du MODULE et non
# `from .. import aura_selectors` (#943) : la forme `from . import x` declare le PAQUET (elle lit
# son attribut), donc elle refermait le SCC `effects` -> `effects.factory` -> `loki.votann` ->
# `effects` -- MESURE par `test_270r4r2_cycles_imports_offline`, qui rougissait sur ce cycle exact
# et redevient vert avec cette forme. `import <module> as N` ne declare que le module, et reste
# forme B.
import engine.entities.effects.aura_selectors as ASel            # noqa: E402
from ....services.effect_bonus import EffectBonus, for_addition

_BLADE_OF_THE_ANCESTORS = "BladeOfTheAncestors"   # TriggeredAbilityType 0x5d3 = 1491 (relique de votanUthar)
_AUGMENTED_ASSAULT = "AugmentedAssault"       # ActiveAbilityType 0x4c5 = 1221 (votanBeserk / Havyr)
_ANCESTRAL_FORTUNE = "AncestralFortune"       # ActiveAbilityType 0x4b7 = 1207 (votanUthar / Uthar)
_GRAVITON_RIFLE = "GravitonRifle"             # ActiveAbilityType 0x4b6 = 1206 (votanIronmaster / Vynn)
_GRIM_EFFICIENCY = "GrimEfficiency"           # TriggeredAbilityType 0x5d2 = 1490 (votanUthar / Uthar)
_PREDICTIVE_GUIDANCE = "PredictiveGuidance"   # TriggeredAbilityType 0x5f5 = 1525 (votanMemnyr / Ammuk)


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
      1. QUI porte l'effet — `IdunBattleLogic.Entities.DSLBehaviors$$AddDynamicStatModifierEffect` (overload
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
        lvl, mult = _source_level_mult(self, stats_ctx)
        amt = ability_var(_AUGMENTED_ASSAULT, "armorReduction", lvl, multiplier_pct=mult)
        if not amt:
            return []
        return [(int(StatType.FIXED_ARMOR), -int(amt))]      # isNegative = 1 -> -amount

    def reverted_stats(self) -> "list":
        """Stats annulees par `RevertModification` (lu par la feuille `RemoveEffect`)."""
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
        lvl, mult = _source_level_mult(self, stats_ctx)
        amt = ability_var(_ANCESTRAL_FORTUNE, "extraCritChance", lvl, multiplier_pct=mult)
        if not amt:
            return []
        return [(int(StatType.CRIT_CHANCE), int(amt))]

    def reverted_stats(self) -> "list":
        return [StatType.CRIT_CHANCE]


class AncestralFortuneExtraBlockChanceEffect(BaseEffect):
    """`AncestralFortune_ExtraBlockChance` (0x5ce = 1486) — stat-mod **BlockChance(7)** POSITIF, self-buff
    du caster, 1 round. Jumeau exact du precedent :

        AddDynamicStatModifierEffectToOwner( factory, 0x5ce, stat = 7 BlockChance, TurnsFromRounds(1) )

    Magnitude = `extraBlockChance[activeAbilityLevel]` (lambda `...b__14_519` : varKey 0x3e = 62,
    `isNegative = 0`)."""
    stat_mod_source = None

    def applied_stat_mods(self, stats_ctx) -> "list":
        lvl, mult = _source_level_mult(self, stats_ctx)
        amt = ability_var(_ANCESTRAL_FORTUNE, "extraBlockChance", lvl, multiplier_pct=mult)
        if not amt:
            return []
        return [(int(StatType.BLOCK_CHANCE), int(amt))]

    def reverted_stats(self) -> "list":
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
    CURRENT_ABILITY = ActiveAbilityType.GravitonRifle

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


# =================================================================================================
#  #959 -- `GrimEfficiency` (TriggeredAbilityType 0x5d2 = 1490), passif de `votanUthar` << Uthar >>
# =================================================================================================
#
#  `IdunBattleLogic.Entities.Abilities.Triggered.Loki.GrimEfficiencyAbility` (base LUE dans
#  `classes.tsv` : `IdunBattle.Entities.Abilities.BaseTriggeredAbility`). TROIS slots au bloc
#  `methodPointers`, UN SEUL corps propre :
#
#    CreateTrigger    -> corps FONDU par l'ICF avec
#                        `...Triggered.Loki.WayOfTheShortBlade_InitAbility$$CreateTrigger` =
#                        `DSLTriggers.OnOwnerSpecificAbilityInit( this.AbilityType )`
#                        -> canal `ABILITY_INIT_OWNER_EFFECTS`, JAMAIS `ABILITY_TRIGGERS`
#                           (meme corps ICF que `IconOfObstinacy`, cf. `factory.py`).
#    CreateBehaviour  -> corps PROPRE :
#        DSLBehaviors.AddDynamicStatModifierEffectToOwner( effectType = 0x5cf = 1487
#                            GrimEfficiency_ExtraArmor,  statType = 0x10 = 16 FixedArmor,
#                            turns = null, isHidden = false )
#      & DSLBehaviors.AddDynamicStatModifierEffectToOwner( effectType = 0x5d0 = 1488
#                            GrimEfficiency_ExtraPierce, statType = 0x1a = 26 ExtraPierce,
#                            turns = null, isHidden = false )
#    .ctor            -> corps FONDU trivial.
#
#  Le `statType` vient donc du BEHAVIOUR, la MAGNITUDE du `.ctor` de l'effet -- deux etages
#  distincts qu'il ne faut pas confondre (`0x10` n'est PAS un `AbilityVariableType`).
#
#  Les DEUX effets derivent de `IdunBattle.Entities.Effects.DynamicStatModifierEffect` (LU dans
#  `classes.tsv`, taille 1192, base `ADynamicStatModifierEffect`) et leurs `.ctor` sont relus A
#  L'ASSEMBLEUR (le pseudo-C perd le litteral, il part par `edx`) :
#
#    GrimEfficiency_ExtraArmorEffect$$.ctor  : `mov edx,0x5d2` + `mov r8d,0x1b` + `xor r9d,r9d`
#                                              + `mov byte [rsp+0x20],0`
#    GrimEfficiency_ExtraPierceEffect$$.ctor : `mov edx,0x5d2` + `mov r8d,0x3f` + idem
#      => DynamicStatModifierEffect( abilityType  = AbilityType.op_Implicit(0x5d2 = 1490),
#                                    variableType = 0x1b = 27 extraArmor / 0x3f = 63
#                                                   extraPierceRatio,
#                                    isNegative   = false, canBeImmuneTo = false )
#  ⚠ La SURCHARGE d'`op_Implicit` est tranchee par l'ADRESSE REELLE du `call`
#  (`IdunBattle.Core.AbilityType$$op_Implicit(triggeredAbility: TriggeredAbilityType)`), pas par le
#  nom : `AbilityType` en porte DEUX, et `ActiveAbilityType 1490` nomme autre chose.
#
#  MAGNITUDE (corps GENERIQUE `DynamicStatModifierEffect$$GetDynamicStatModificationAmount`) :
#      amount = ConfigVar( <abilityType>, EffectSource(Get(effect)), <variableType> )
#      return isNegative ? -amount : amount
#  -> indexee sur l'`AbilityState` de la **SOURCE** (Uthar), jamais sur le buffe. Meme structure
#  que `LionHelm_ExtraBlockDamage` (`dark_angels_passives.py`).
#
#  SELECTEUR -- `CreateTargetSelector` des DEUX effets est un corps FONDU par l'ICF, PARTAGE avec
#  `IdunBattle.Entities.Effects.Loki.LionHelm_ExtraBlockDamageEffect$$CreateTargetSelector` (slot LU
#  au bloc `methodPointers`, absent de `functions.tsv` -- le faux negatif ICF) :
#      DSLSelectors.SurroundingFriends( unit  = Owner@DSLSelectors+0x30,
#                                       range = AbilityConfiguration.GetNumberConstant(
#                                                   config@+0x60, 0x16 = AbilityConstantType.range ),
#                                       unique = true,
#                                       unitSelectionType = 3 = OnlyAliveAndTargetable )
#  -> le PORTEUR est EXCLU (`SurroundingTiles - Tiles(self)`, aucun `op_Addition Owner`), ce que
#  l'i2 corrobore (<< **Other** friendly units within 2 hexes ... >>). UNE seule patte de port.
#
#  CONDITION ACTIVE -- corps PROPRES et DIFFERENTS, c'est tout le passif :
#    GrimEfficiency_ExtraArmorEffect$$CreateActiveCondition  = DSLTriggers.HasEffect(
#        DSLSelectors.EffectSource(Effect@+0x38), 0x5c7 = 1479
#        PrioritisedEfficiency_HostileAcquisition_Stance, onlyActive = false,
#        targetType = 6 = EffectTargetType.Both )
#    GrimEfficiency_ExtraPierceEffect$$CreateActiveCondition = idem avec 0x5c8 = 1480
#        PrioritisedEfficiency_FortifyTakeover_Stance
#  -> les deux auras PARTITIONNENT les stances du trait `PrioritisedEfficiency` (1059) : jamais
#  actives ensemble. C'est le SEUL discriminant entre les deux classes, avec la variable et le stat.
#
#  ⚠ CE QUE LE PORT NE PRODUIT PAS, ET QUI EST LU ICI : la POSE/BASCULE des marqueurs de stance vit
#  dans `APrioritisedEfficiencyAbility$$GetSet{Offensive,Defensive}StanceBehaviour`, qui depend du
#  substrat PERSISTENT-DATA absent du port (residu #121, cf. `loki/extra_damage.py`). Les stances
#  sont donc SEEDEES depuis l'etat live capte, jamais posees offline -- d'ou `is_active` ci-dessous,
#  qui LIT le marqueur au lieu de le supposer, et `active_condition_ported = True`, qui interdit au
#  flag `active` d'une instance SEEDEE (defaut True) d'ouvrir l'aura de la MAUVAISE stance.


class _GrimEfficiencyAuraStatModEffect(BaseEffect):
    """Socle des DEUX `DynamicStatModifierEffect` de `GrimEfficiency` -- AURA stat-mod PROJETEE sur
    les alliés d'Uthar à <= `range` hexes, le porteur EXCLU (cf. le bloc de RE ci-dessus).

    INTERFACE PORT (duck-typed, consommee par `runner/operations/aura_stat_mods.py`), la MEME que
    `_LionHelmAuraStatModEffect` -- c'est le meme corps ICF de selecteur :
      * `aura_stat_modification_stat()`    -> le `StatType` ecrit chez la cible (du BEHAVIOUR) ;
      * `aura_stat_modification_amount()`  -> `ConfigVar(<variableType>)` indexe sur la SOURCE ;
      * `aura_stat_modification_targets()` -> `SurroundingFriends(Owner, ConfigConst(range))`.

    ⚠ Les DEUX sous-classes ne different QUE par leurs trois constantes de classe : la variable de
    config, le stat ecrit, et le marqueur de stance de la condition active. Rien n'est recopie d'une
    moitie sur l'autre -- les trois sont LUES separement au decompile."""

    #: `AbilityVariableType` du `.ctor` (relu a l'assembleur : `mov r8d, <ord>`).
    _VAR: str = ""
    #: `StatType` passe par `AddDynamicStatModifierEffectToOwner` -- le BEHAVIOUR, pas le `.ctor`.
    _STAT: int = 0
    #: `HasEffect(EffectSource(Effect), <stance>, onlyActive = false, Both)` de `CreateActiveCondition`.
    _STANCE: int = 0

    # Le flag `active` d'une instance SEEDEE vaut True par defaut : sans ce drapeau, l'aura de la
    # stance NON courante s'appliquerait aussi (sur-compte silencieux d'un facteur 2 sur le kit).
    active_condition_ported = True

    # ── `CreateActiveCondition` ─────────────────────────────────────────────────────────────────
    def is_active(self, unit_state: "Mapping | None" = None) -> bool:
        """MIRROR de `HasEffect( EffectSource(Effect@+0x38), <stance>, onlyActive = false,
        targetType = 6 = Both )`.

        `EffectSource` = le poseur de l'effet. Pour ce passif, `AddDynamicStatModifierEffectToOwner`
        met `Owner@DSLSelectors+0x30` en source ET en cibles -> source == porteur == Uthar ; on lit
        donc `self.source` en priorite et `unit_state["owner_id"]` en repli.

        `has_effect_on` est le CALLABLE `(unit_id, effect_type) -> bool` de
        `runner.components.UnitEffectStateView`, mirror EXACT du meme noeud (`onlyActive: null`,
        `effectTargetType: 6`) -- pas un predicat neuf.

        TRI-ETAT : cle absente (`unit_state` non threade, face DECISION) -> True, la degradation
        « present == actif » de tout le parc. Elle est SURE ici parce que le canal live actif-only
        ne publie QUE l'aura de la stance courante : rendre True sur ce qui a ete CAPTE est fidele.
        Le seul regime ou la cle manque ET ou les deux instances coexistent est le SEED offline, et
        c'est justement la que `unit_state_for_effects` la fournit."""
        c = unit_state or {}
        has = c.get("has_effect_on")
        if has is None:
            return True                              # donnee non threadee -> « present == actif »
        src = self.source if self.source is not None else c.get("owner_id")
        if src is None:
            return True
        return bool(has(int(src), int(self._STANCE)))

    # ── interface AURA stat-mod ─────────────────────────────────────────────────────────────────
    def aura_stat_modification_stat(self) -> int:
        """`statType` du `AddDynamicStatModifierEffectToOwner` (0x10 FixedArmor / 0x1a ExtraPierce)."""
        return int(self._STAT)

    def aura_stat_modification_amount(self) -> "int | None":
        """`DynamicStatModifierEffect$$GetDynamicStatModificationAmount` :
        `ConfigVar(1490, EffectSource(Get(effect)), <variableType>)`, `isNegative = false`.

        `ability_level is None` (aucun `AbilityState` capte) -> None : « present != applique »,
        meme regime que `LionHelm` / `FirstAmongTraitors`."""
        if self.ability_level is None:
            return None
        amt = ability_var(_GRIM_EFFICIENCY, self._VAR, self.ability_level,
                          multiplier_pct=self.ability_variables_multiplier)
        return int(amt) if amt else None

    def aura_stat_modification_targets(self, state, owner_id: int) -> list:
        """`SurroundingFriends(Owner@+0x30, GetNumberConstant(0x16 = range), true,
        OnlyAliveAndTargetable)` -- le PORTEUR est exclu par le noeud lui-meme.

        Constante absente -> `GetNumberConstant` LEVE cote natif ; le port se degrade en « aucun
        beneficiaire » plutot que d'inventer un rayon (meme regime que `first_among_traitors_range`)."""
        rng = grim_efficiency_range()
        if rng is None:
            return []
        return list(ASel.surrounding_friends(state, owner_id, int(rng)))


def grim_efficiency_range() -> "int | None":
    """`AbilityConfiguration.GetNumberConstant(config@+0x60, 0x16 = AbilityConstantType.range)` =
    `abilities.GrimEfficiency.constants.range` (= 2). `None` = constante absente."""
    v = ability_var(_GRIM_EFFICIENCY, AbilityConstantType.range.name, is_constant=True)
    return None if v is None else int(v)


class GrimEfficiencyExtraArmorEffect(_GrimEfficiencyAuraStatModEffect):
    """`IdunBattle.Entities.Effects.Loki.GrimEfficiency_ExtraArmorEffect` (EffectType 0x5cf = 1487).

    Stance << Hostile Acquisition >> : +`extraArmor` FixedArmor aux autres alliés à <= 2 hexes.
    i2 : « Hostile Acquisition: Affected units have +437 Armour. »
    Gameconfig vivant : `extraArmor[65] = 437` (et `variablesAffectedByRarityBonus` ne le contient
    PAS -> aucun scaling de rarete, `ability_var` porte deja ce gate)."""

    _VAR = "extraArmor"                                        # AbilityVariableType 0x1b = 27
    _STAT = int(StatType.FIXED_ARMOR)                          # StatType 0x10 = 16
    _STANCE = int(EffectType.PrioritisedEfficiency_HostileAcquisition_Stance)   # 0x5c7 = 1479


class GrimEfficiencyExtraPierceEffect(_GrimEfficiencyAuraStatModEffect):
    """`IdunBattle.Entities.Effects.Loki.GrimEfficiency_ExtraPierceEffect` (EffectType 0x5d0 = 1488).

    Stance << Fortify Takeover >> : +`extraPierceRatio` ExtraPierce aux autres alliés à <= 2 hexes.
    i2 : « Fortify Takeover: Affected units have +20% pierce ratio with all attacks. »
    Gameconfig vivant : `extraPierceRatio[65] = 20`.

    ⚠ `StatType.EXTRA_PIERCE` (26) et NON `EXTRA_PIERCE_MELEE` (21) / `EXTRA_PIERCE_RANGED` (22) :
    le litteral du behaviour est `0x1a`, LU -- l'i2 (« with all attacks ») le corrobore."""

    _VAR = "extraPierceRatio"                                  # AbilityVariableType 0x3f = 63
    _STAT = int(StatType.EXTRA_PIERCE)                         # StatType 0x1a = 26
    _STANCE = int(EffectType.PrioritisedEfficiency_FortifyTakeover_Stance)      # 0x5c8 = 1480


# =================================================================================================
#  #959 -- `PredictiveGuidance` (TriggeredAbilityType 0x5f5 = 1525), passif de `votanMemnyr`
#          << Ammuk >>
# =================================================================================================
#
#  `IdunBattleLogic.Entities.Abilities.Triggered.Loki.PredictiveGuidanceAbility` (base LUE dans
#  `classes.tsv` : `IdunBattle.Entities.Abilities.BaseTriggeredAbility`). TROIS slots, UN corps
#  propre -- et son `CreateTrigger` est le MEME corps ICF que celui de `GrimEfficiency` ci-dessus :
#
#    CreateTrigger    -> `DSLTriggers.OnOwnerSpecificAbilityInit( this.AbilityType )`
#    CreateBehaviour  -> corps PROPRE :
#        DSLBehaviors.AddEffect( 0x5ff = 1535 PredictiveGuidance_Melee,     AbilityStateReference,
#                                source = Owner@+0x30, targets = Owner@+0x30, options = default )
#      & DSLBehaviors.AddEffect( 0x600 = 1536 PredictiveGuidance_Ranged,    ... idem ... )
#      & DSLBehaviors.AddEffect( 0x601 = 1537 PredictiveGuidance_ExtraHits, ... idem ... )
#    .ctor            -> corps FONDU trivial.
#
#  ⚠ `targets = Owner` : les TROIS effets-entites vivent sur AMMUK, PAS sur les ennemis. Leur
#  `CreateTargetSelector` designe les entites AFFECTEES, qui ne portent aucune instance -- exactement
#  le regime mesure pour `FearedInterrogator_Target` (`dark_angels_passives.py`). Le port les
#  modelise donc COTE SOURCE, et re-evalue le selecteur PAR COUP.
#
#  Les TROIS `.ctor` sont un SEUL corps (ICF), relu a l'assembleur :
#    `mov edx,0x5f5` + `mov r8b,1` + `call AbilityOrEffect$$op_Implicit(triggeredAbility)`
#      => BaseEffect( AbilityOrEffect(0x5f5 = 1525), hasAutomaticActivation = true )
#  Leur `CreateActiveCondition` est elle aussi UN corps ICF, partage avec
#  `...WayOfTheShortBlade_AdditionalAttackMarkerEffect$$CreateActiveCondition` = `<DSLTriggers+0x40>`,
#  le trigger CONSTANT VRAI que `DSLTriggers$$.ctor` met en cache (son `op_LogicalNot` occupe
#  `+0x48`) -> TOUJOURS actifs, donc toujours captes : aucun `is_active` a porter ici.
#
#  SELECTEURS -- TROIS corps PROPRES, et ils ne sont PAS identiques :
#    _MeleeEffect$$CreateTargetSelector    = UnitsWithoutFlag( <aura>, 0 = UnitFlag.Moved, 3 )
#    _RangedEffect$$CreateTargetSelector   = UnitsWithFlag(    <aura>, 0 = UnitFlag.Moved, 3 )
#    _ExtraHitsEffect$$CreateTargetSelector = <aura>                       (AUCUN filtre de flag)
#  ou `<aura>` = `_MeleeEffect$$AffectUnitsInRange(dsl, config)`, helper STATIQUE partage :
#      DSLSelectors.SurroundingEnemies( unit = Owner@+0x30,
#                                       range = DSLFormulas.ConfigConst( 0x16 = range, config ),
#                                       unique = true, unitSelectionType = 3 )
#
#  BONUS -- TROIS corps PROPRES, et le troisieme n'a PAS la meme condition que les deux premiers :
#    _MeleeEffect$$CreateEffectDamageBonusForAttack =
#        EffectBonus.ForAddition( get_OwnerIsTarget & IsMeleeAttack & BonusCondition(dsl),
#                                 ConfigVar( 0x08 = extraDmg,   AbilityState, config ) )
#    _RangedEffect$$CreateEffectDamageBonusForAttack =
#        EffectBonus.ForAddition( get_OwnerIsTarget & IsRangedAttack & BonusCondition(dsl),
#                                 ConfigVar( 0x09 = extraDmg_2, AbilityState, config ) )
#    _MeleeEffect$$BonusCondition(dsl)   -- helper STATIQUE, appele par les DEUX ci-dessus :
#        op_LogicalNot( AreEqual( EffectSource(Effect@+0x38), Caster@DSLSelectors+0x48 ) )
#      & ( IsMechanical( Caster@+0x48, selectionType = 0 = Any )
#        | HasFaction(   Caster@+0x48, 0x14 = 20 LeaguesOfVotann, selectionType = 3 ) )
#    _ExtraHitsEffect$$CreateEffectHitsBonusForAttack =
#        EffectBonus.ForAddition( get_OwnerIsTarget
#                               & HasFaction( Caster@+0x48, 0x14 = LeaguesOfVotann, 3 )
#                               & op_LogicalNot( AreEqual( EffectSource, Caster@+0x48 ) ),
#                                 ConfigConst( 0x64 = 100 extraHits, config ) )
#
#  ⚠ QUATRE ECARTS MESURES entre les trois moitiés -- aucune recopie possible :
#    (1) le filtre de flag `Moved` : ABSENT / PRESENT / INVERSE selon l'effet ;
#    (2) `extraDmg` (0x08) contre `extraDmg_2` (0x09) : DEUX cles distinctes du gameconfig, qui se
#        trouvent porter les MEMES valeurs aujourd'hui -- les lire separement est ce qui survivra a
#        un rebalancement ;
#    (3) `ExtraHits` n'a PAS le membre `IsMechanical` : il est reserve aux Leagues of Votann, ce que
#        l'i2 dit explicitement (« Other friendly **Leagues of Votann** units also score ... ») ;
#    (4) `ExtraHits` lit une CONSTANTE (`ConfigConst`), les deux autres une VARIABLE de niveau
#        (`ConfigVar`) -- accesseurs differents, donc sections differentes du gameconfig.
#
#  `get_OwnerIsTarget` dans ces trois corps : le natif boucle « effets actifs du board x CIBLES de
#  l'effet » et ecrit `AbilityEntities+0x18 (Owner) <- la cible de l'effet`
#  (`IdunBattle.Core.Services.EffectsQuery$$GetActiveEffectsWithBonuses`, cf. le bloc #372 de
#  `effects/__init__.py`). Le noeud signifie donc « la cible de l'effet EST la cible du coup » --
#  et c'est le CANAL qui le rend cote port : `create_aura_defense_damage_malus_for_ally` (axe DEGAT)
#  et `create_aura_hits_malus_for_defense` (axe COUPS) sont les deux boucles state-wide ou le
#  porteur est une AUTRE unite que la cible.


def predictive_guidance_range() -> "int | None":
    """`DSLFormulas.ConfigConst( 0x16 = AbilityConstantType.range, config@+0x60 )` =
    `abilities.PredictiveGuidance.constants.range` (= 2). `None` = constante absente -> le port se
    degrade en « aucun ennemi affecte »."""
    v = ability_var(_PREDICTIVE_GUIDANCE, AbilityConstantType.range.name, is_constant=True)
    return None if v is None else int(v)


def _pg_affects_target(c: "Mapping", require_moved: "bool | None") -> bool:
    """`UnitsWith[out]Flag( SurroundingEnemies(Owner, ConfigConst(range), true, 3), Moved, 3 )`
    evalue contre le ctx du coup.

    `require_moved` : `True` = `UnitsWithFlag(Moved)` (RangedEffect), `False` =
    `UnitsWithoutFlag(Moved)` (MeleeEffect), `None` = pas de noeud de flag (ExtraHitsEffect).

    TRI-ETAT sur `tgt_has_moved` : cle absente = flag non threade -> le gate se FERME (degradation
    RESTRICTIVE, jamais un sur-compte). Le noeud de flag n'existe pas pour `None` -> pas de lecture."""
    if c.get("owner_id") is None or c.get("tgt_id") is None:
        return False
    if c.get("owner_id") == c.get("tgt_id"):
        return False                                  # `SurroundingEnemies` : jamais le porteur
    ot, tt = c.get("owner_team"), c.get("tgt_team")
    if ot is None or tt is None or ot == tt:
        return False                                  # `Enemies` = equipe DIFFERENTE du porteur
    op, tp = c.get("owner_pos"), c.get("t_pos")
    if not op or not tp:
        return False
    rng = predictive_guidance_range()
    if rng is None:
        return False
    import hexgeo
    d = hexgeo.distance(tuple(op), tuple(tp))
    if d is None or d > int(rng):                     # `SurroundingTiles(Owner, range)`
        return False
    if require_moved is not None:
        moved = c.get("tgt_has_moved")
        if moved is None or bool(moved) is not bool(require_moved):
            return False                              # `UnitsWith[out]Flag(Moved)`
    return True


def _pg_bonus_condition(c: "Mapping", require_mechanical_or_faction: bool) -> bool:
    """`_MeleeEffect$$BonusCondition(dsl)` (helper STATIQUE, partage Melee/Ranged) et sa variante
    REDUITE d'`ExtraHits` -- les deux conjoints qui portent sur l'ATTAQUANT (`Caster@+0x48`).

    `require_mechanical_or_faction = True`  -> `IsMechanical(Caster, Any) | HasFaction(Caster, LoV, 3)`
    `require_mechanical_or_faction = False` -> `HasFaction(Caster, LoV, 3)` SEUL (ExtraHits).

    Le premier conjoint (`!AreEqual(EffectSource, Caster)`) est commun aux trois corps : la source
    de l'effet est le PORTEUR (Ammuk), donc `owner_id != att_id` -- c'est le « **other** friendly »
    de l'i2. TRI-ETAT : `att_faction` / `att_traits` absents -> le membre se tait (gate FERME)."""
    aid = c.get("att_id")
    if aid is None or c.get("owner_id") is None or aid == c.get("owner_id"):
        return False                                  # `!AreEqual(EffectSource, Caster)`
    votann = c.get("att_faction") == UnitFaction.LeaguesOfVotann.name   # `HasFaction(., 0x14, 3)`
    if not require_mechanical_or_faction:
        return bool(votann)
    mechanical = UnitTrait.Mechanical.name in (c.get("att_traits") or ())  # `IsMechanical(., Any)`
    return bool(mechanical or votann)


class _PredictiveGuidanceDamageEffect(BaseEffect):
    """Socle des DEUX effets de DEGAT de `PredictiveGuidance` -- ils partagent le helper natif
    `_MeleeEffect$$BonusCondition` et l'aura `_MeleeEffect$$AffectUnitsInRange`, et RIEN D'AUTRE.

    CANAL PORT = `create_aura_defense_damage_malus_for_ally` (boucle state-wide « TOUS les effets a
    cible x leurs cibles » de `CalculateDefenderModifiersForPrediction`) : l'effet-entite vit sur
    AMMUK, la CIBLE du coup doit etre dans son selecteur, et le bonus va a l'ATTAQUANT.

    ⚠ `AURA_DEFENSE_MALUS_NATIVE_FACE = "attacker"` : le natif n'implemente PAS le slot 0x1a
    (`CreateEffectDamageMalusForDefense`) mais le slot 0x16 (`CreateEffectDamageBonusForAttack`) --
    sa contribution atterrit donc dans `attackModifiers`, ce qui decide du nombre d'arrondis
    `Fix64.Round` en aval (#437-r1-r1-r1). Meme regime que `DaughterOfTheAbyss_ExtraDamagePct`."""

    AURA_DEFENSE_MALUS_NATIVE_FACE = "attacker"

    #: `ConfigVar(<ord>, AbilityState, config)` du corps -- `extraDmg` (8) / `extraDmg_2` (9).
    _VAR: str = ""
    #: `IsMeleeAttack` (True) / `IsRangedAttack` (False).
    _IS_MELEE: bool = True
    #: `UnitsWithoutFlag(Moved)` (False) / `UnitsWithFlag(Moved)` (True).
    _REQUIRE_MOVED: bool = False

    def create_aura_defense_damage_malus_for_ally(self,
                                                  ctx: "Mapping | None" = None) -> "EffectBonus | None":
        c = ctx or {}
        # `IsMeleeAttack` / `IsRangedAttack` -- tri-etat #106 : `None` = nature non declaree, les
        # DEUX predicats natifs sont faux -> le gate se ferme.
        if c.get("is_melee") is not self._IS_MELEE:
            return None
        if not _pg_affects_target(c, self._REQUIRE_MOVED):     # get_OwnerIsTarget (via le selecteur)
            return None
        if not _pg_bonus_condition(c, True):                   # BonusCondition(dsl)
            return None
        if self.ability_level is None:      # ConfigVar sans AbilityState -> pas de magnitude
            return None
        amt = ability_var(_PREDICTIVE_GUIDANCE, self._VAR, self.ability_level,
                          multiplier_pct=self.ability_variables_multiplier)
        if not amt:
            return None
        # `EffectBonus.ForAddition(., .)` -> canal ADDITIF (post-percage), cote ATTAQUANT.
        return for_addition(True, int(amt))


class PredictiveGuidanceMeleeEffect(_PredictiveGuidanceDamageEffect):
    """`IdunBattle.Entities.Effects.Loki.PredictiveGuidance_MeleeEffect` (EffectType 0x5ff = 1535).

    i2 : « If an affected enemy **did not move** in its last turn, other friendly Leagues of Votann
    or Mechanical units deal +655 Damage with **melee** attacks against it. »
    Gameconfig vivant : `extraDmg[65] = 655` (dans `variablesAffectedByRarityBonus` -> scale par le
    multiplicateur de rarete d'AMMUK, que `ability_var` porte)."""

    _VAR = "extraDmg"                                  # AbilityVariableType 0x08 = 8
    _IS_MELEE = True                                   # IsMeleeAttack
    _REQUIRE_MOVED = False                             # UnitsWithoutFlag(Moved)


class PredictiveGuidanceRangedEffect(_PredictiveGuidanceDamageEffect):
    """`IdunBattle.Entities.Effects.Loki.PredictiveGuidance_RangedEffect` (EffectType 0x600 = 1536).

    i2 : « If an affected enemy **moved** in its last turn, other friendly Leagues of Votann or
    Mechanical units deal +655 Damage with **ranged** attacks against it. »
    Gameconfig vivant : `extraDmg_2[65] = 655` -- MEME valeur qu'`extraDmg` aujourd'hui, CLE
    DIFFERENTE : c'est le litteral `0x09` du corps qui est lu, pas la valeur qui est recopiee."""

    _VAR = "extraDmg_2"                                # AbilityVariableType 0x09 = 9
    _IS_MELEE = False                                  # IsRangedAttack
    _REQUIRE_MOVED = True                              # UnitsWithFlag(Moved)


class PredictiveGuidanceExtraHitsEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.PredictiveGuidance_ExtraHitsEffect` (EffectType 0x601 = 1537).

    i2 : « Other friendly Leagues of Votann units also score an additional hit with all attacks
    against affected enemies. »

    CANAL PORT = `create_aura_hits_malus_for_defense` (l'effet est possede par une AUTRE unite que
    la cible et modifie les coups qu'elle RECOIT) -- avec un `ForAddition` **POSITIF**, ce que le
    canal sait porter : le natif trie ses `HitsBonusForAttack` au SIGNE, pas a la provenance
    (`DamagePrediction$$GetAttackHits`).

    ⚠ TROIS ecarts avec ses deux freres, tous LUS : aucun filtre `UnitFlag.Moved` (l'aura NUE),
    aucun membre `IsMechanical` (Leagues of Votann SEULEMENT), et une CONSTANTE `ConfigConst(0x64 =
    extraHits)` la ou eux lisent une variable de niveau. Gameconfig vivant :
    `constants.extraHits = "1"`."""

    #: `ConfigConst( 0x64 = AbilityConstantType.extraHits, config@+0x60 )`.
    _CONST = AbilityConstantType.extraHits             # 0x64 = 100

    def create_aura_hits_malus_for_defense(self,
                                           ctx: "Mapping | None" = None) -> "EffectBonus | None":
        c = ctx or {}
        if not _pg_affects_target(c, None):            # aura NUE : aucun noeud de flag
            return None
        if not _pg_bonus_condition(c, False):          # HasFaction(LoV) SEUL, pas d'IsMechanical
            return None
        n = ability_var(_PREDICTIVE_GUIDANCE, self._CONST.name, is_constant=True)
        if not n:
            return None
        return for_addition(True, int(n))              # ForAddition POSITIF (+1 coup)


# =================================================================================================
#  #1001 -- `BladeOfTheAncestors` (relique `R_Crit_BladeOfTheAncestors`, `TriggeredAbilityType`
#           0x5d3 = 1491, porteur `votanUthar` << Uthar >>) : le BUFF, cote effet.
# =================================================================================================
#
#  `IdunBattle.Entities.Effects.Loki.BladeOfTheAncestorsBuffEffect` (`EffectType` 0x5d1 = 1489
#  `BladeOfTheAncestors_Effect`). Base LUE dans `frida/classes.tsv` :
#  `IdunBattle.Entities.Effects.BaseEffect` -- ce n'est PAS un `AStatModifierEffect`, la classe
#  construit ses `ChangeStat` ELLE-MEME.
#
#  `...BladeOfTheAncestorsBuffEffect$$.ctor` (litteral relu a l'assembleur -- le pseudo-C le perd,
#  il part par `edx` : `mov edx,0x5d3` juste avant le `call` a
#  `IdunBattle.Core.AbilityOrEffect$$op_Implicit`) :
#      BaseEffect( hasAutomaticActivation = 1, Nullable<...>(0), Nullable(AbilityOrEffect(0x5d3)) )
#  -> la config lue par ses `GetVariableForLevel` est celle de l'ABILITY 1491, jamais celle de
#  l'effet. Corroboration independante : `extraCritDmg` n'existe que dans le gameconfig de
#  `BladeOfTheAncestors` (`AncestralFortune`, l'autre porteur d'`extraCritChance` du roster, n'a que
#  `extraCritChance` + `extraBlockChance`).
#
#  `...BladeOfTheAncestorsBuffEffect$$ApplyModification(target, effect)` -- MIRROR :
#      ChangeStat( Entity(target), Stat(9  = CritChance, 5 = Modification), mode 4,
#                  Direct( GetVariableForLevel(cfg, 0x41 = extraCritChance, GetAbilityState(this)) ),
#                  Entity(effect), 3 = OnlyAliveAndTargetable, 0, 0 )
#      ChangeStat( Entity(target), Stat(10 = CritDamage,  5 = Modification), mode 4,
#                  Get(    GetVariableForLevel(cfg, 0x42 = extraCritDmg,    GetAbilityState(this)) ),
#                  Entity(effect), 3, 0, 0 )
#  (`Direct` au premier, `Get` au second : deux fabriques de constante d'`IdunBattleLogic.Entities.
#  DSLFormulas`, meme signature `(amount: Int32) -> IAmountFormula`. L'asymetrie est LUE, elle n'a
#  aucune consequence de valeur -- les deux enveloppent le meme entier.)
#
#  `...BladeOfTheAncestorsBuffEffect$$RevertInternal(owner, target, effect)` : les MEMES deux
#  `ChangeStat`, avec `Stat(<9|10>, 6 = ResetModification)` et `<DSLFormulas+0x18> = Direct(0)`.
#  -> exactement le couple `applied_stat_mods` / `reverted_stats` du port.
#
#  `...BladeOfTheAncestorsBuffEffect$$UpdateInternal(owner, target, effect)` = `ApplyModification`
#  NU (un increment de plus par re-pose) ; `...$$RefreshValueInternal` = le slot 0x578 puis
#  `ApplyModification` x `BaseEffect$$GetTimesApplied(effect)`. Les deux disent la MEME chose :
#  l'effet EMPILE de facon ADDITIVE, il ne se rafraichit pas. D'ou `stacks_stat_mod_on_add = True`
#  (patron `ActOfFaithBuffEffect` / `RealityUnbound_ExtraMaxDamage`), qui reproduit l'observable
#  par N instances plutot que par le compteur `TimesApplied` -- meme choix, meme raison qu'ActOfFaith.
#
#  ⚠ CE N'EST PAS `ActOfFaith`, ET LA DIFFERENCE EST NUMERIQUE. `ActOfFaithBuffEffect` pose
#  `Ceiling(GetStat(CritDamage, part 3 = Initial) x actOfFaithExtraCritDmgPct%)`, un POURCENTAGE de
#  la crit-dmg de base. Ici les DEUX montants sont des variables de niveau PLATES
#  (`extraCritChance[10] = 10`, `extraCritDmg[10] = 877`), ce que l'i2 dit mot pour mot :
#  << gains +10% Crit Chance and deals +877 Crit Damage >>. Recopier le voisin de forme aurait
#  ecrit un pourcentage la ou le natif lit une constante de config.


def _relic_ability_state(stats_ctx, ability_name: str) -> "tuple":
    """`(level, multiplier)` de l'`AbilityState` sous lequel `ability_name` est MONTEE sur le
    porteur dont on tient le `StatsComponent.ctx`.

    MEME tri que `engine.runner.operations.triggers.base.triggered_ability_state` (mirror de la
    distribution des trois `AbilityState` par `IdunBattle.Entities.Factories.UnitFactory$$Build`),
    mais depuis le CONTEXTE seul : `applied_stat_mods` ne recoit pas le `State`. La duplication est
    assumee et bornee a ces quatre lignes -- hisser le helper ici ferait dependre `entities/` de
    `runner/`, l'arete que le paquet n'a pas.

    POURQUOI LE CTX DU PORTEUR EST LE BON : `BladeOfTheAncestorsAbility$$CreateBehaviour` pose
    `AddEffect(0x5d1, AbilityStateReference, Owner@DSLSelectors+0x30, turns = null)` -- SOURCE et
    CIBLE sont le MEME `Owner`. Le `GetAbilityState(this)` que lit `ApplyModification` est donc
    l'etat d'ability du PORTEUR lui-meme ; lire le ctx de la cible n'est pas une approximation, la
    source et la cible sont la meme unite par construction.

    Sans ce tri, une relique montee au niveau 8 lirait `passive_ability_level` (50 sur tout runner
    normalise), donc le DERNIER palier -- un ecart de magnitude SILENCIEUX."""
    if stats_ctx is None:
        return (None, 100)
    if getattr(stats_ctx, "tertiary_ability", None) == ability_name:
        return (int(getattr(stats_ctx, "tertiary_ability_level", 0) or 0),
                int(getattr(stats_ctx, "tertiary_ability_variables_multiplier", 100) or 100))
    return (getattr(stats_ctx, "passive_ability_level", None),
            int(getattr(stats_ctx, "ability_variables_multiplier", 100) or 100))


class BladeOfTheAncestorsBuffEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.BladeOfTheAncestorsBuffEffect` (`EffectType` 0x5d1 = 1489).

    Buff crit EMPILABLE d'Uthar : `+extraCritChance` `CritChance` et `+extraCritDmg` `CritDamage`
    par pile. Pose par `BladeOfTheAncestorsAbility` (mort ou kill d'un HERO allie), retire -- TOUTES
    piles -- par `BladeOfTheAncestors_RemoveEffectAbility` au crit du porteur. Le RE des cinq corps
    natifs est dans le bloc ci-dessus."""

    #: `AbilityOrEffect(0x5d3)` du `.ctor` : la config lue est celle de l'ABILITY, pas de l'effet.
    ABILITY_ID = _BLADE_OF_THE_ANCESTORS

    #: `AbilityVariableType` 0x41 = 65 / 0x42 = 66 -- les deux `GetVariableForLevel` d'`ApplyModification`.
    EXTRA_CRIT_CHANCE_KEY = "extraCritChance"
    EXTRA_CRIT_DMG_KEY = "extraCritDmg"

    cc_delta: int = 0   # delta crit-chance de CETTE pile (info/report, patron ActOfFaith)
    cd_delta: int = 0   # delta crit-damage de CETTE pile (info/report)
    stat_mod_source = None   # cle de source ChangeStat (revert par-source via la feuille RemoveEffect)
    # `UpdateInternal` = `ApplyModification` nu, `RefreshValueInternal` = `ApplyModification` x
    # `GetTimesApplied` : l'empilement est ADDITIF, pas un refresh. Cf. le bloc de RE.
    stacks_stat_mod_on_add = True

    def applied_stat_mods(self, stats_ctx) -> "list":
        """`...BladeOfTheAncestorsBuffEffect$$ApplyModification` -- les DEUX `ChangeStat`
        (`StatPart` 5 = MODIFICATION, donc ADDITIF), part DATA cote `entities/`. La couche runner
        (`AddEffectOperation._apply_stat_mods`) les EXECUTE via `apply_change_stat`, keyees par une
        source unique par instance -> revert par-source exact.

        `extraCritChance` et `extraCritDmg` sont des VARIABLES DE NIVEAU du gameconfig de l'ability
        1491, indexees par le couple TERTIAIRE quand la relique est equipee (cf.
        `_relic_ability_state`). Aucune des deux n'est dans `variablesAffectedByRarityBonus` -> le
        multiplicateur ne mord pas ; on le passe quand meme, parce que c'est `ability_var` (mirror de
        `GetVariableForLevel`) qui en decide, pas nous.

        Variable illisible / relique non seedee -> montant 0, donc AUCUN stat-mod pose (le port
        refuse d'inventer un palier)."""
        lvl, mult = _relic_ability_state(stats_ctx, self.ABILITY_ID)
        cc = int(ability_var(self.ABILITY_ID, self.EXTRA_CRIT_CHANCE_KEY, lvl,
                             multiplier_pct=mult) or 0)
        cd = int(ability_var(self.ABILITY_ID, self.EXTRA_CRIT_DMG_KEY, lvl,
                             multiplier_pct=mult) or 0)
        out = []
        if cc:
            out.append((int(StatType.CRIT_CHANCE), cc))     # Stat(9, 5) <- Direct(extraCritChance)
        if cd:
            out.append((int(StatType.CRIT_DAMAGE), cd))     # Stat(10, 5) <- Get(extraCritDmg)
        return out

    def reverted_stats(self) -> "list":
        """`...BladeOfTheAncestorsBuffEffect$$RevertInternal` = les MEMES deux stats, `StatPart`
        6 = RESET_MODIFICATION. Lues par la feuille `RemoveEffect` pour `revert_change_stat(...,
        stat_mod_source)` par-source."""
        return [StatType.CRIT_CHANCE, StatType.CRIT_DAMAGE]
