"""`MonsterSlayerOfCaliban` -- relique `R_Crit_MonsterSlayerOfCaliban` (`TriggeredAbilityType`
0x5f7 = **1527**), porteur UNIQUE `darkaCompanion` << Forcas >> (Dark Angels, HERO du pool
rank 17). Voie `item`, etat 2 des trois etats d'une relique -> montage ECRIT
`rl_duel build --equip-relic darkaCompanion:MonsterSlayerOfCaliban:<lvl>` (#237). #1009.

i2 `Abilities/MonsterSlayerOfCaliban_CurrentLevelDescription` :
    << Forcas deals +{[extraDmg]} Damage to Big Targets and Vehicles. He also has an added
    {[blockChance]}% chance to Block {[blockDmg]} Damage. >>

===================================================================================================
LES ARTEFACTS NATIFS (decompile ghidra, build `rnca9r7q6c`)
===================================================================================================

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.MonsterSlayerofCalibanAbility` (parent
`IdunBattle.Entities.Abilities.BaseTriggeredAbility`, `frida/classes.tsv`) -- **UNE seule** classe
native pour la cle, contrairement a `DaemonfleshPlate` / `Lakrimae` / `ChaliceOfBaal`.

    $$CreateTrigger  = OnOwnerSpecificAbilityInit( 0x5f7 = 1527 )

    $$CreateBehaviour =
        blockChance = GetVariableForLevel( AbilityVariableType.blockChance = 0x15, abilityState )
        blockDmg    = GetVariableForLevel( AbilityVariableType.blockDmg    = 0x14, abilityState )
        extraBlock  = AddExtraBlockEffectToOwner( EffectType.MonsterSlayerOfCaliban_ExtraBlock
                                                     = 0x604 = 1540,
                                                 blockChance : Direct(blockChance),
                                                 blockDamage : Direct(blockDmg),
                                                 turns       : null )
        extraDmg    = AddEffect( EffectType.MonsterSlayerOfCaliban_ExtraDmg = 0x603 = 1539,
                                 abilityState = AbilityStateReference,
                                 targets      = Owner@<DSLSelectors+0x30>,
                                 turns        : Nullable<int>(null) )
        return op_BitwiseAnd( extraDmg, extraBlock )

⚠ **L'ORDRE D'EXECUTION EST `extraDmg` PUIS `extraBlock`, ET IL EST L'INVERSE DE L'ORDRE DE
CONSTRUCTION.** Le natif CONSTRUIT `AddExtraBlockEffectToOwner` d'abord (registre `pvVar6`), puis
`AddEffect`, et ne les compose qu'au `op_BitwiseAnd(AddEffect, AddExtraBlock)` final -- or
`CombinedBehaviour` execute GAUCHE puis DROITE. Lire l'ordre du pseudo-C au lieu de l'ordre des
arguments du `&` est exactement la faute que `VolummsMasterArtifice` a payee (#1001). Ici les deux
poses sont independantes et idempotentes, donc l'ordre n'a aucun observable -- il est ecrit parce
qu'il est LU, pas parce qu'il mordrait.

⚠ **LA SURCHARGE D'`AddExtraBlockEffectToOwner` EST `(effectType, blockChance, blockDamage,
turns)`** (`frida/methods.tsv`, parametres NOMMES) : le 2e argument construit est
`Direct(GetVariableForLevel(0x15))` = **blockChance**, le 3e `Direct(GetVariableForLevel(0x14))` =
**blockDmg**. Les deux variables sont voisines dans l'enum (`0x14 blockDmg`, `0x15 blockChance`) et
les inverser produirait un block de 10 points de degat avec 1470 % de chance -- silencieux cote
port, puisque les deux champs sont des `int`. L'appariement vient du NOM du parametre, jamais de
l'ordre des `GetVariableForLevel`.

`IdunBattle.Entities.Effects.Loki.MonsterSlayerofCaliban_ExtraDmgEffect` (`EffectType` 1539, parent
`IdunBattle.Entities.Effects.DamageModifierAbilityEffect`, `frida/classes.tsv`) :

    $$CreateDamageModifier =
        EffectBonus.ForAddition(
            get_OwnerIsCaster
          & ( HasTrait( Target@<DSLSelectors+0x60>, UnitTrait.Vehicle   = 0x405 = 1029 )
            | HasTrait( Target@<DSLSelectors+0x60>, UnitTrait.BigTarget = 0x3f9 = 1017 ) ),
            ConfigVar( AbilityVariableType.extraDmg = 8, GetAbilityState(this), config@this+0x60 ) )

  * la face est **attaquant** : `CreateDamageModifier` sort par le forwarder
    `IdunBattle.Entities.Effects.DamageModifierAbilityEffect$$CreateEffectDamageBonusForAttack`
    (recopie nue du `Nullable<EffectBonus>`), donc l'accumulateur natif est `attackModifiers` ;
  * **AUCUN** autre noeud dans la conjonction : ni `IsMeleeAttack`, ni `IsNormalAttack`, ni
    `IsRangedAttack`. Le contraste avec `BeastSlayer_ExtraDmgEffect` -- meme paire de traits cible,
    meme famille -- est ENTIER : celui-la porte `IsMeleeAttack` et un `ForPercentIncrease`,
    celui-ci n'a aucun gate de nature et un `ForAddition`. Recopier le voisin de forme aurait
    eteint le bonus sur les abilities et transforme un flat en pourcentage.

`EffectType` 1540 (`MonsterSlayerOfCaliban_ExtraBlock`) n'a **AUCUNE classe d'effet dediee** dans
le build (`frida/classes.tsv` : la seule `MonsterSlayer*` est l'`_ExtraDmgEffect`) -- c'est le
regime NORMAL d'`AddExtraBlockEffectToOwner`, qui pose un `MultiValueStatEntryEffect` portant deux
entrees `{BLOCK_CHANCE, BLOCK_DAMAGE}` calculees AU MOMENT DE LA POSE. Cote port on suit le patron
deja etabli par `PsychicFortressExtraBlockEffect` / `BeastSlayerExtraBlockEffect` : une classe qui
RELIT la config au niveau de l'`AbilityState` -- valeur identique, puisque les deux `Direct(...)`
natifs sont figes par le meme couple `(level, multiplier)` pour toute la bataille.

===================================================================================================
CANAL DE PORT, ET LE NIVEAU QUI N'EST PAS CELUI DES PASSIFS
===================================================================================================

`CreateTrigger` = `OnOwnerSpecificAbilityInit` -> le canal est
`factory.ABILITY_INIT_OWNER_EFFECTS["MonsterSlayerOfCaliban"]`, **jamais** `ABILITY_TRIGGERS` ni
`RELIC_ABILITY_TRIGGERS` (s'y tromper donnerait un passif qui ne se pose JAMAIS). Le seed
(`runner/operations/spawn.py::_seed_ability_owner_effects`) lit `ctx.tertiary_ability` et passe le
couple TERTIAIRE (`TertiaryAbilityLevel` / `TertiaryAbilityVariablesMultiplierPercentage`), pas
celui des passifs -- rail repare par #1005/#1007. C'est ce qui separe `extraDmg[1] = 490` de
`extraDmg[10] = 728` (clamp du palier passif 50) : +238 par coup, en silence.

1527 est une `TriggeredAbilityType` : elle n'entre NI dans `ABILITY_CLASSES`, NI dans
`TARGETING_OPTIONS`, NI dans `ABILITY_ATTACK_TYPE`.

RESIDUS NOMMES
  * `target_traits` n'est threade que sur le chemin d'attaque NORMALE (`runner/operations/
    damage.py`) -- limite d'INFRA PARTAGEE avec `BeastSlayer` / `MartialKatah` / `CondemnorStake`,
    pas propre a ce port : sur une attaque d'ABILITY le gate de trait est muet et le bonus ne
    s'applique pas. Forcas n'a qu'une active (`CalibaniteGreatsword`, un toggle de posture), donc
    son vecteur observable est bien l'attaque normale.
  * la face PREDICTION du bonus suit le canal commun `create_effect_damage_bonus_for_attack` ; le
    natif n'a pas de `CreateEffectDamageBonusForAttackPrediction` propre a cet effet.
"""
from __future__ import annotations

from ....services.damage_combat import BlockSource
from ....services.effect_bonus import EffectBonus, for_addition
from ...effect_type import EffectType          # #270-r1-r1-r3 : cles nommees, jamais l'ordinal
from ...traits.unit_trait import UnitTrait
from ..base import BaseEffect, relic_ability_state
from ..magnitude import ability_var

#: Cle gameconfig de l'ability -- la config qu'indexent `ConfigVar` / `GetVariableForLevel`.
ABILITY_ID = "MonsterSlayerOfCaliban"

#: `AbilityVariableType` 8 / 0x14 / 0x15 (`frida/enums.tsv`), resolus par leur NOM. L'ordinal seul
#: ne discrimine pas : 0x14 et 0x15 sont VOISINS et tous deux presents au gameconfig de 1527.
VAR_EXTRA_DMG = "extraDmg"          # AbilityVariableType 8
VAR_BLOCK_DMG = "blockDmg"          # AbilityVariableType 0x14 = 20
VAR_BLOCK_CHANCE = "blockChance"    # AbilityVariableType 0x15 = 21

#: `HasTrait(Target@<DSLSelectors+0x60>, X)` -- les DEUX traits du `op_BitwiseOr`, par leur membre
#: d'enum (`UnitTrait.Vehicle = 1029`, `UnitTrait.BigTarget = 1017`). Le port compare des NOMS de
#: trait (c'est ce que publient `StatsComponent.ctx.traits` cote runner et `Scene.ctx_by_id` cote
#: decision), donc le membre sert a garantir que le nom ecrit est celui du build.
MONSTER_TARGET_TRAITS = frozenset({UnitTrait.Vehicle.name, UnitTrait.BigTarget.name})


class MonsterSlayerOfCalibanExtraDmgEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.MonsterSlayerofCaliban_ExtraDmgEffect$$CreateDamageModifier`
    (`EffectType` 0x603 = 1539, nom capte `MonsterSlayerOfCaliban_ExtraDmg`) -- owner-effect
    PERMANENT pose a l'init de la relique sur Forcas. Cf. l'en-tete du module pour l'arbre natif.

    ⚠ **LE SYMBOLE NATIF ECRIT `MonsterSlayerof` (o MINUSCULE), LE NOM D'EFFET `MonsterSlayerOf`
    (O MAJUSCULE).** Ce n'est pas une coquille du port : `frida/classes.tsv` porte
    `...Loki.MonsterSlayerofCaliban_ExtraDmgEffect` et `frida/enums.tsv`
    `EffectType.MonsterSlayerOfCaliban_ExtraDmg`. La citation ci-dessus est VERBATIM, et c'est
    elle -- pas le nom -- qui apparie la classe du port a la classe native pour
    `probe_437r1r1r1_effect_face_table.py` (la voie NOM echoue par construction sur ce couple).

    OBSERVABLE : chaque coup de Forcas contre une cible `Vehicle` ou `BigTarget` porte
    `+extraDmg[niveau de relique]` en FLAT (canal additif attaquant)."""

    def create_effect_damage_bonus_for_attack(self, is_ranged: bool | None = None,
                                              has_moved: bool | None = None,
                                              target_traits: "frozenset[str] | None" = None,
                                              is_prediction: bool = False,
                                              is_normal_attack: bool | None = True,
                                              target_armor_reduced: bool | None = None,
                                              att_ctx=None) -> EffectBonus | None:
        """`ForAddition( get_OwnerIsCaster & (HasTrait(Target, Vehicle) | HasTrait(Target,
        BigTarget)), ConfigVar(extraDmg) )` -- MIRROR 1:1.

        `get_OwnerIsCaster` est satisfait STRUCTURELLEMENT sur ce canal : l'agregateur n'itere que
        les effets de l'ATTAQUANT (meme regime que `Skullsmasher` / `CondemnorStake`).

        `target_traits` = les noms de traits de la CIBLE. `None` (contexte sans cible : prediction
        generique, attaque d'ability) -> pas de bonus, jamais un bonus devine (« present !=
        applique », meme degradation que `BeastSlayer`)."""
        if not target_traits or MONSTER_TARGET_TRAITS.isdisjoint(target_traits):
            return None                       # ni Vehicle ni BigTarget -> le `op_BitwiseOr` est FAUX
        # `ConfigVar(extraDmg, GetAbilityState(this), config@this+0x60)` : l'`AbilityState` est le
        # TERTIAIRE du porteur (`level 1..10 / mult 100`), jamais celui de ses passifs
        # (`50 / 180` en runner normalise) -- meme canal et meme justification que `VitarusEffect`
        # (#1005). Cet effet ne vit QUE sur le porteur de la relique, donc la cle est toujours la
        # sur le canal ATTAQUANT ; le repli couvre les appelants historiques ET les captures
        # re-bakees par `snapshot._rebake_tertiary_owner_effects` (#1009), qui posent deja le bon
        # couple sur l'instance.
        r_lvl, r_mult = relic_ability_state(att_ctx, ABILITY_ID)
        lvl = r_lvl if r_lvl is not None else self.ability_level
        if lvl is None:
            return None                       # `ConfigVar` sans `AbilityState` -> inerte
        mult = r_mult if r_mult is not None else self.ability_variables_multiplier
        amount = ability_var(ABILITY_ID, VAR_EXTRA_DMG, lvl, multiplier_pct=mult)
        return for_addition(True, int(amount)) if amount else None


class MonsterSlayerOfCalibanExtraBlockEffect(BaseEffect):
    """`EffectType` 0x604 = 1540 (`MonsterSlayerOfCaliban_ExtraBlock`) -- l'entree
    `GetMultiValueStat(7)` posee par `AddExtraBlockEffectToOwner(1540, Direct(blockChance),
    Direct(blockDmg), turns = null)`, c.-a-d. une source de BLOCK **SUPPLEMENTAIRE** du porteur,
    ABSENTE du scalaire `GetStat(7/8)` -- meme canal que `PsychicFortress_ExtraBlockChance`,
    `BeastSlayer_ExtraBlock` et `Daemon_ExtraBlock`.

    Aucune classe d'effet dediee cote natif (cf. l'en-tete) : les deux valeurs sont figees a la
    pose par le couple `(TertiaryAbilityLevel, multiplier)` de l'`AbilityState`, que le port relit
    ici -- meme valeur, meme niveau."""

    def create_effect_block_source_for_defense(self, defender_fixed_armor: int = 0,
                                               defender_attack: int = 0,
                                               defender_max_health: int = 0):
        """`BlockSource(chance = blockChance[niveau], amount = blockDmg[niveau])`.

        Ni l'un ni l'autre ne depend d'une stat du defenseur (contraste `BeastSlayer`, dont l'amount
        est un `PercentageOf(FixedArmor)`, et `Daemon`, `PercentageOf(Attack)`) : les deux arguments
        natifs sont des `Direct(<valeur de config>)`. Les deux parametres sont donc ignores, et
        c'est un RESULTAT de lecture."""
        lvl = self.ability_level if self.ability_level is not None else self.level
        chance = ability_var(ABILITY_ID, VAR_BLOCK_CHANCE, lvl,
                             multiplier_pct=self.ability_variables_multiplier)
        amount = ability_var(ABILITY_ID, VAR_BLOCK_DMG, lvl,
                             multiplier_pct=self.ability_variables_multiplier)
        if not chance or not amount or int(amount) <= 0:
            return None
        # `block_id` = l'ENTITE-EFFET natif (`BlockChanceInfo.entityId`, cle du `failedBlockIds` de
        # `IdunBattle.Core.Services.DamageCalculations$$CalculateBlockChances`) : offline l'identite
        # stable est l'`effect_type` (cf. `BaseEffect.block_source_id`). Ne PAS prendre la chance :
        # 1540 et un autre ExtraBlock a 10 % se confondraient dans l'exclusion inter-coups.
        return BlockSource(chance=int(chance), amount=int(amount),
                           block_id=self.block_source_id(int(EffectType.MonsterSlayerOfCaliban_ExtraBlock)))
