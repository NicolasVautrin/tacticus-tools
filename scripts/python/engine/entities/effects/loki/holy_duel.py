"""`HolyDuel` (`ActiveAbilityType` 0x41a = 1050, `templChampion` << Brother Jaeger >>) -- les TROIS
effets de la famille : le composite de duel 1091 et ses deux modificateurs de degat 1092/1093.

i2 (`abilities.HolyDuel`) : << Brother Jaeger Taunts an adjacent enemy unit and immediately performs
a normal attack against it. Brother Jaeger deals +582 Damage and takes -364 Damage from the target
while it's Taunted by him. Brother Jaeger is also Taunted by the target and the taunt does not
expire with rounds passed. >>

================================================================================================
1. LA SOURCE DE CONFIG DES TROIS CLASSES -- lue a l'ASSEMBLEUR
================================================================================================
Le decompilateur masque l'immediat ; les trois `.ctor` portent la MEME sequence :

    ba 1a 04 00 00      mov  edx, 0x41a                  ; 1050
    e8 ..               call IdunBattle.Core.AbilityOrEffect$$op_Implicit

et le `call` vise la surcharge dont `frida/methods.tsv` donne la signature
`op_Implicit(activeAbility: IdunBattle.Entities.Enum.ActiveAbilityType)` (tranchee par l'ADRESSE
CIBLE du `call`, identique pour les trois -- pas par le nom, que les quatre surcharges partagent).
=> `1050` est un `ActiveAbilityType`, donc la config lue est `abilities.HolyDuel` et le niveau qui
indexe ses variables est le niveau d'ability **ACTIVE** de la SOURCE (le champion).
⚠ QUALIFICATION D'ENUM : aux memes ids, `EffectType 1050 = MartialKatah_DmgReduction` et
`TriggeredAbilityType 1050 = ChaosMutation`. Trois enums, un nombre.

Les surcharges de `BaseEffect$$.ctor` visees (signatures `methods.tsv`) :

    HolyDuel_TauntEffect        ..ctor(hasAutomaticActivation: true,
                                       unitEffectType: Nullable<UnitEffectType>(1 = Negative),
                                       sourceAbility: Nullable<AbilityOrEffect>(1050))
    HolyDuel_ExtraDmgEffect     ..ctor(hasAutomaticActivation: true, unitEffectType: null,
                                       sourceAbility: Nullable<AbilityOrEffect>(1050))
    HolyDuel_DmgReductionEffect ..ctor(idem 1092)

================================================================================================
2. `HolyDuel_TauntEffect$$ApplyInternal(owner, target, effect)` -- MIRROR du DECOMPILE
================================================================================================
    ctx = new <>c__DisplayClass9_0()
    ctx.<+0x20> = target                                        # le PORTEUR de 1091 = l'ennemi
    ctx.<+0x10> = (ABondEffect) effect                          # l'entite-effet courante
    ctx.<+0x18> = ABondEffect.BondedEntityId(this, effect)      # = le CHAMPION (cf. la pose)
    bonded      = <entites>.GetEntity(ctx.<+0x18>)

    AddSubEffectWithSameTurns(this, effect, target, EffectBuilder(ctx, b__0), 0x1b   = 27)
    AddSubEffectWithSameTurns(this, effect, bonded, EffectBuilder(ctx, b__1), 0x1b   = 27)
    AddSubEffectWithSameTurns(this, effect, bonded, EffectBuilder(ctx, b__2), 0x444  = 1092)
    AddSubEffectWithSameTurns(this, effect, bonded, EffectBuilder(ctx, b__3), 0x445  = 1093)

et les quatre lambdas sont TOUTES `AddEffectBehaviour$$DefaultBondEffectBuilder(id, <ctx.+0x10 ->
+0x18..+0x38 = l'AbilityStateReference du PARENT>, <bondedEntityId>)`, avec :

    b__0  -> bondedEntityId = ctx.<+0x18>        # l'enfant pose sur l'ennemi   bonde au CHAMPION
    b__1..b__3 -> bondedEntityId = ctx.<+0x20>.Id  # les enfants poses sur le champion bondes a l'ENNEMI

=> LE DUEL EST SYMETRIQUE, et c'est le natif qui le dit : les deux unites recoivent le composite
`Taunted_OnlySpecificTargets` (27), chacune bondee a l'AUTRE. La seule chose qui bascule d'un
enfant a l'autre est le COUPLE (porteur, bonded), toujours ensemble -- d'ou le champ unique
`SubEffectSpec.on_bonded_entity` (cf. `entities/effects/base.py`).

L'`AbilityStateReference` du PARENT descend dans les quatre enfants (c'est le contexte PARTAGE
`ctx.<+0x10>`, pas un recablage) : c'est lui que relit `BaseEffect$$GetAbilityState` quand les
`ConfigVar` de 1092/1093 s'indexent. Cote port : `AddEffectOperation._spawn_sub_effects` propage
`ability_level`/`active_ability_level`/`multiplier_pct` du parent.

================================================================================================
3. LA FIN DU DUEL -- le trigger (c) `get_Adjacent` d'`ABondEffect`
================================================================================================
`HolyDuel_TauntEffect` est la SEULE classe de la famille `ABondEffect` a armer
`<klass+0x738> get_Adjacent` (mesure `probe_462_r4b_r1_r1_r1_r1_bond_removal.py --step declared`).
Le natif construit alors

    Triggered( NOT IsAdjacent(Owner@0x30, BondedEntityFromEffect(Effect@0x38), 3)
               & NOT AmountIsZero(BondedEntity) & On(0x1d = UnitPositionChanged_2),
               RemoveEffect(Effect@0x38) )

C'est ce qui rend l'i2 exact -- << the taunt does not expire with rounds passed >> : 1091 n'a
AUCUNE duree par defaut, il tombe quand les deux duellistes cessent d'etre adjacents (ou a la mort
du bonde, gate (a)). Port : `runner/operations/triggers/bond_removal.py`.
"""
from __future__ import annotations

from collections.abc import Mapping

from ....services.effect_bonus import EffectBonus, for_addition
from ..base import BaseEffect, SubEffectSpec, SAME_TURNS
from ..magnitude import ability_var
from ...effect_type import EffectType
from ...ability_variable_type import AbilityVariableType

# `ConfigVar(<cle>, GetAbilityState(effect), <config@effet+0x60>)` des deux modificateurs.
_VAR_EXTRA_DMG = AbilityVariableType.extraDmg               # 8    -- 1092
_VAR_DMG_REDUCTION = AbilityVariableType.dmgReduction       # 0x12 -- 1093
HOLY_DUEL_ABILITY_ID = "HolyDuel"          # cle gameconfig (les deux variables y sont rarity-scaled)


def _duel_level(eff: BaseEffect):
    """Le niveau qui indexe `variables[level]` de `abilities.HolyDuel`.

    `ConfigVar(..., GetAbilityState(effect))` lit l'`AbilityStateReference` BAKEE dans l'entite-effet,
    c'est-a-dire celle du CHAMPION qui a caste -- et `HolyDuel` est une ability **ACTIVE** (§1), donc
    `active_ability_level`. Repli sur `ability_level` (le slot PASSIF) quand l'actif n'a pas ete
    propage : meme cascade que `LightOfSanguinius_DamageReductionEffect`, l'autre effet du port dont
    la source est une active."""
    return eff.active_ability_level if eff.active_ability_level is not None else eff.ability_level


class HolyDuelTauntEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.HolyDuel_TauntEffect` -- `EffectType` 0x443 = **1091**
    `HolyDuel_Taunt`, effet COMPOSITE et BOND pose par
    `IdunBattleLogic.Entities.Abilities.Active.Loki.HolyDuelAbility$$ExecuteBehaviour` sur l'ENNEMI
    vise, `bondedEntity` = le CHAMPION.

    Ses quatre sous-effets (cf. §2 de l'en-tete de module), tous `AddSubEffectWithSameTurns` donc
    MEME duree que le parent :

      * `Taunted_OnlySpecificTargets` (27) sur le PORTEUR (l'ennemi), bonde au champion ;
      * `Taunted_OnlySpecificTargets` (27) sur le CHAMPION, bonde a l'ennemi ;
      * `HolyDuel_ExtraDmg` (0x444 = 1092) sur le CHAMPION, bonde a l'ennemi ;
      * `HolyDuel_DmgReduction` (0x445 = 1093) sur le CHAMPION, bonde a l'ennemi.

    Chacun des deux `27` est lui-meme un composite (`TauntedEffect$$ApplyInternal` -> 25/26/1237 +
    l'ecriture de `ForcedAttackTargetsComponent`) : c'est CE canal, et lui seul, qui rend le duel
    opposable au ciblage (#436).

    ⚠ AUCUNE surcharge de `get_CanBeImmuneTo` n'est LUE pour cette classe (`methods.tsv` ne lui
    declare que `.ctor` et `ApplyInternal`, et le corps d'un getteur constant est DEDUPLIQUE par
    IL2CPP -- l'absence ne prouve rien). On laisse donc le defaut de `BaseEffect` : le gate
    d'immunite est porte par le composite `27` lui-meme, qui le SURCHARGE a `true` (#175-r2), donc
    une unite `Immune` refuse de toute facon les deux `Taunted` et leurs enfants."""

    # #982-r4 -- `IEffect` slot 3 `get_KeepOnChangeOwner` -> `32 c0 c3` (`xor al,al ; ret`) = FAUX.
    # Ici la DECLARATION est LUE dans le `global-metadata.dat` (et la valeur dans les octets du
    # corps), pas deduite d'une absence : `methods.tsv` est indexee par ADRESSE et IL2CPP DEDUPLIQUE
    # les corps triviaux -- c'est exactement le faux negatif que la note ci-dessus decrit pour
    # `get_CanBeImmuneTo`. Cette classe est l'une des DEUX SEULES du build (sur 465) a surcharger.
    keep_on_change_owner = False

    def sub_effects_on_apply(self) -> list[SubEffectSpec]:
        return [
            # b__0 : sur le PORTEUR (l'ennemi), bonde a `ctx.<+0x18>` = le champion.
            SubEffectSpec(int(EffectType.Taunted_OnlySpecificTargets),          # 0x1b
                          EffectType.Taunted_OnlySpecificTargets.name, turns=SAME_TURNS),
            # b__1 : sur l'entite BONDEE (le champion), bonde a `ctx.<+0x20>.Id` = l'ennemi.
            SubEffectSpec(int(EffectType.Taunted_OnlySpecificTargets),          # 0x1b
                          EffectType.Taunted_OnlySpecificTargets.name, turns=SAME_TURNS,
                          on_bonded_entity=True),
            # b__2
            SubEffectSpec(int(EffectType.HolyDuel_ExtraDmg),                    # 0x444
                          EffectType.HolyDuel_ExtraDmg.name, turns=SAME_TURNS,
                          on_bonded_entity=True),
            # b__3
            SubEffectSpec(int(EffectType.HolyDuel_DmgReduction),                # 0x445
                          EffectType.HolyDuel_DmgReduction.name, turns=SAME_TURNS,
                          on_bonded_entity=True),
        ]


class HolyDuelExtraDmgEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.HolyDuel_ExtraDmgEffect` -- `EffectType` 0x444 = **1092**
    `HolyDuel_ExtraDmg`, porte par le CHAMPION, bonde a son duelliste.

    `...$$CreateEffectDamageBonusForAttack` (MIRROR du decompile, build `rnca9r7q6c`) :

        v       = ConfigVar( 8 = extraDmg, GetAbilityState(effet), <config@effet+0x60> )
        trigger = DSLTriggers.get_OwnerIsActor
                  op_BitwiseAnd
                  DSLTriggers.AreEqual( Target@DSLSelectors+0x60,
                                        BondedEntityFromEffect(Effect@DSLSelectors+0x38) )
        return EffectBonus.ForAddition( trigger, v )

    => `+extraDmg` PLAT (additif) sur les attaques du PORTEUR **contre son duelliste et lui seul**.
    AUCUN autre gate : ni melee/ranged, ni profil, ni `IsNormalAttack` -- il mord sur tout vecteur.

    FACE : le slot implemente est `CreateEffectDamageBonusForAttack` et le trigger est `OwnerIsActor`
    -> canal ATTAQUANT du port, `owner_is_caster=True`, `ATTACK_BONUS_NATIVE_FACE` par defaut
    ("attacker").

    `AreEqual` = `IdunBattleLogic.Entities.DSLTriggers$$AreEqual` sur deux selecteurs d'entite ; le
    port le lit comme l'egalite d'ids -- `att_ctx["tgt_id"]` (la cible du coup) contre `self.bonded`
    (le champ `+0x10` du composant de bond, ecrit par `DefaultBondEffectBuilder`). Une des deux
    inconnues -> `None` (degradation RESTRICTIVE : present != applique)."""

    def create_effect_damage_bonus_for_attack(self, is_ranged: bool | None = None,
                                              has_moved: bool | None = None,
                                              target_traits: "frozenset[str] | None" = None,
                                              is_prediction: bool = False,
                                              is_normal_attack: bool | None = True,
                                              target_armor_reduced: bool | None = None,
                                              att_ctx=None) -> EffectBonus | None:
        bonded = self.bonded
        tgt = (att_ctx or {}).get("tgt_id")
        if bonded is None or tgt is None or int(tgt) != int(bonded):
            return None                     # `AreEqual(Target@0x60, BondedEntityFromEffect(Effect))`
        v = ability_var(HOLY_DUEL_ABILITY_ID, _VAR_EXTRA_DMG.name, _duel_level(self),
                        multiplier_pct=self.ability_variables_multiplier)   # ConfigVar(8)
        return for_addition(True, int(v)) if v else None                    # OwnerIsActor


class HolyDuelDmgReductionEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.HolyDuel_DmgReductionEffect` -- `EffectType` 0x445 = **1093**
    `HolyDuel_DmgReduction`, porte par le CHAMPION, bonde a son duelliste.

    `...$$CreateEffectDamageBonusForAttack` (MIRROR du decompile, build `rnca9r7q6c`) :

        v       = ConfigVar( 0x12 = dmgReduction, GetAbilityState(effet), <config@effet+0x60> )
        trigger = DSLTriggers.get_OwnerIsTarget
                  op_BitwiseAnd
                  DSLTriggers.AreEqual( Actor@DSLSelectors+0x40,
                                        BondedEntityFromEffect(Effect@DSLSelectors+0x38) )
        return EffectBonus.ForAddition( trigger, Multiply(v, <DSLFormulas+0x38>) )

    `<DSLFormulas+0x38>` = `Direct(-1)` (`DSLFormulas$$.ctor` ecrit `+0x18 <- Direct(0)`,
    `+0x20 <- Direct(1)`, `+0x28 <- Direct(2)`, `+0x30 <- Direct(100)`, `+0x38 <- Direct(-1)`).
    => `-dmgReduction` PLAT sur le degat que le porteur RECOIT **de son duelliste et de lui seul**.
    MEME forme que `FightingRetreat_DamageReductionEffect` (`Multiply(ConfigVar(0x12), MinusOne)`),
    au trigger pres.

    FACE. Le slot implemente s'appelle `...ForAttack` mais son trigger est `OwnerIsTarget` : l'effet
    vit sur le DEFENSEUR et modifie le degat qu'il RECOIT -> canal PORT
    `create_effect_damage_malus_for_defense` (meme mold qu'`ExemplarOfHate_TargetEffect` /
    `Chronometron_ExtraDamageEffect` / `NeuroparasiteEffect`). L'ACCUMULATEUR natif, lui, reste
    `attackModifiers` -- c'est `CalculateAttackerModifiersForPrediction` qui invoque le slot 0x16 --
    d'ou `DEFENSE_MALUS_NATIVE_FACE = "attacker"` (#437-r1-r1-r1).

    `Actor@DSLSelectors+0x40` = l'ATTAQUANT du coup ; le port le lit dans `attacker_ctx["id"]`
    (threade par `damage_model.defender_modifiers` et par la face PREDICTION). Une des deux
    inconnues -> `None`."""

    # Le slot NATIF est `CreateEffectDamageBonusForAttack` (0x16), invoque par
    # `CalculateAttackerModifiersForPrediction` : la contribution atterrit dans `attackModifiers`
    # MALGRE le trigger `OwnerIsTarget`. Meme lecture que `MarkerlightEffect` / `ExemplarOfHate_
    # TargetEffect` / `Chronometron_ExtraDamageEffect`.
    DEFENSE_MALUS_NATIVE_FACE = "attacker"

    def create_effect_damage_malus_for_defense(self, is_melee: bool | None = None,
                                               damage_profile: str | None = None,
                                               attacker_ctx: Mapping | None = None
                                               ) -> EffectBonus | None:
        bonded = self.bonded
        att = (attacker_ctx or {}).get("id")
        if bonded is None or att is None or int(att) != int(bonded):
            return None                     # `AreEqual(Actor@0x40, BondedEntityFromEffect(Effect))`
        v = ability_var(HOLY_DUEL_ABILITY_ID, _VAR_DMG_REDUCTION.name, _duel_level(self),
                        multiplier_pct=self.ability_variables_multiplier)   # ConfigVar(0x12)
        # `Multiply(v, <DSLFormulas+0x38> = Direct(-1))` : additif NEGATIF cote defenseur.
        return for_addition(False, -int(v)) if v else None                  # OwnerIsTarget
