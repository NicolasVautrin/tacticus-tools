"""`ExemplarOfTheMontka` (0x5da = 1498) -- le buff pose par l'ACTIVE `ExemplarOfTheMontka`
(`ActiveAbilityType` 0x4ba = 1210) de `tauFarsight` << Commander Farsight >>.

## SOURCE DE CONFIG -- l'ability ACTIVE 1210, tranchee par l'ADRESSE de la surcharge

`IdunBattle.Entities.Effects.Loki.ExemplarOfTheMontkaEffect$$.ctor`, octets LUS :

    ba ba 04 00 00      mov edx, 0x4ba                          ; 1210
    e8 ...              call IdunBattle.Core.AbilityOrEffect$$op_Implicit
    41 b0 01            mov r8b, 1                              ; hasAutomaticActivation
    e8 ...              call IdunBattle.Entities.Effects.BaseEffect$$.ctor

Les QUATRE surcharges d'`op_Implicit` portent le meme nom ; celle appelee est tranchee par
l'ADRESSE de la cible du `call` -- `IdunBattle.Core.AbilityOrEffect.op_Implicit(activeAbility:
IdunBattle.Entities.Enum.ActiveAbilityType)`. => la config lue est `abilities.ExemplarOfTheMontka`
et le niveau qui indexe ses variables est le niveau d'ability **ACTIVE** de la SOURCE.
⚠ `0x4ba` NOMME AUTRE CHOSE dans les enums voisins -- mesure sur
`data/symbols/rnca9r7q6c/frida/enums.tsv` : `EffectType 1210 = AttemptedPossession_DmgOverride`,
`TriggeredAbilityType 1210 = GunnersKillOnSight_Attack`. L'ordinal seul ne tranche pas, la
SIGNATURE si.

## POSE -- `ExemplarOfTheMontkaAbility$$ExecuteBehaviour` (portee par la meme tranche)

    targets = UnitsWithRangedWeapons(
                  UnitsWithTrait( Friends( of       = Caster@DSLSelectors+0x48,
                                           entities = AllAliveUnits@DSLSelectors+0x20,
                                           selectionType = 3 ),
                                  trait = 0x10 = UnitTrait.Hero,
                                  selectionType = 3 ) )

    AddEffect( 0x5da = 1498,
               abilityState = AActiveAbility$$get_AbilityStateReference,
               source       = Caster@DSLSelectors+0x48,
               targets      = <ci-dessus>,
               turns        = <DSLFormulas+0x20> = la constante 1 )

⚠ **AUCUNE SOUSTRACTION DU CASTER, ET AUCUN `op_Addition` POUR LE RE-AJOUTER** : contrairement au
jumeau de forme `WarHowlAbility$$ExecuteBehaviour` (qui fait `Friends(of=Owner@+0x30,
entities = AllAliveUnits - Owner)` puis `op_Addition(Owner, ...)`), 1210 passe le pool ENTIER et
laisse le caster entrer par le filtre -- `IdunBattle.Entities.UnitExtensions$$IsFriend` n'ecarte
pas l'egalite. Consequence LOAD-BEARING : Farsight ne se buffe que s'il satisfait LUI AUSSI
`UnitsWithTrait(Hero)` et `UnitsWithRangedWeapons` (il porte bien `Hero` et une arme `Plasma`
`Range 2` au kit -- donc oui, mais par le filtre, pas par une exception).

## TROIS ARTEFACTS, TROIS CANAUX -- et la classe n'en porte QUE ces trois

Le bloc `methodPointers` range par classe : entre `ExemplarOfTheKauyon_AdditionalHitsEffectEffect`
et `ExplosiveMaladies_ExtraMeleeAttackEffect`, la classe occupe EXACTEMENT quatre slots contigus
(`ApplyInternal`, `CreateEffectDamageBonusForAttack`, `RevertInternal`, `.ctor`). Pas de
`CreateTargetSelector` (donc AUCUNE aura : l'effet ne vit que sur ses porteurs), pas de
`CreateCritChanceBonus`, pas de `GetRefreshTriggers`.

### 1. TRAIT -- `ApplyInternal` / `RevertInternal`

    ApplyInternal (this, owner, target, effect)
        -> <IOperationProcessor @this+0x68>.<slot 0x26>(target, 0x412, isTemporary: 1)
    RevertInternal(this, owner, target, effect)
        -> <IOperationProcessor @this+0x68>.<slot 0x27>(target, 0x412, isTemporary: 1)

Corps STRICTEMENT identique a celui de `WarHowl_ExtraDamage_UnstoppableEffect` (memes slots, meme
`0x412`, meme `isTemporary`), mais a une ADRESSE DIFFERENTE et avec son propre garde de
`class_init` -- ce sont bien DEUX corps, pas un fold. `0x412 = 1042 = UnitTrait.Unstoppable`
(qualifie : 1042 vaut `EffectType.HailOfLivingAmmunition_ExtraHits` et
`TriggeredAbilityType.HailOfLivingAmmunition` dans d'AUTRES enums).

### 2. DEGAT -- `CreateEffectDamageBonusForAttack`

    EffectBonus.ForAddition(
        get_OwnerIsCaster & IsNormalAttack,
        DSLFormulas.If( DSLTriggers.HasTrait(Target@DSLSelectors+0x60, 0x3f9 = BigTarget),
                        ConfigVar(0x09 = extraDmg_2, GetAbilityState(effect), config@+0x60),
                        ConfigVar(0x08 = extraDmg,   GetAbilityState(effect), config@+0x60) ) )

⚠ **PAS DE `IsMeleeAttack` NI DE `IsRangedAttack`** -- c'est la difference de fond avec WarHowl,
dont le trigger porte `IsMeleeAttack`. Le buff mord sur TOUTE attaque normale du porteur, mêlée
comme distance. L'i2 le dit mot pour mot : « all their normal attacks deal +{extraDmg} Damage ».

⚠ **L'ORDRE DES DEUX BRANCHES EST LU, PAS DEDUIT** : `DSLFormulas$$If(trigger, ifAmount,
elseAmount)` (signature dans `frida/methods.tsv`) recoit `ifAmount = ConfigVar(0x09)` et
`elseAmount = ConfigVar(0x08)` -- le decompile construit `ConfigVar(8)` D'ABORD puis `ConfigVar(9)`,
et c'est le SECOND construit qui part en `ifAmount`. Concorde avec l'i2 (« When attacking a Big
Target, they deal +946 Damage instead », et `extraDmg_2[64] = 946` contre `extraDmg[64] = 437`).

### 3. Rien d'autre

Aucun canal COUPS, aucun canal CRIT, aucune aura.
"""
from __future__ import annotations

from ....services.effect_bonus import EffectBonus, for_addition
from ...traits.unit_trait import UnitTrait          # `0x412 = 1042 = Unstoppable` de `ApplyInternal`
from ..base import BaseEffect
from ..magnitude import ability_var

_ABILITY_ID = "ExemplarOfTheMontka"    # ActiveAbilityType 0x4ba = 1210 (active, tauFarsight)

#: `DSLTriggers$$HasTrait(Target@DSLSelectors+0x60, 0x3f9)` -- le NOM gameconfig du trait, seule
#: forme que `target_traits` transporte. `0x3f9 = 1017 = UnitTrait.BigTarget` (qualifie : 1017 vaut
#: `EffectType.ActOfFaith_Effect`, `ActiveAbilityType.FragBomb` et
#: `TriggeredAbilityType.FireOfAbsolution` dans d'AUTRES enums).
_BIG_TARGET_TRAIT = UnitTrait.BigTarget.name       # 0x3f9 = 1017


class ExemplarOfTheMontkaEffect(BaseEffect):
    """`ExemplarOfTheMontka` (0x5da = 1498) -- `Unstoppable` + un bonus de degat ADDITIF sur les
    attaques normales du porteur, pour UN tour. Cf. l'en-tete du module pour la RE complete.

    NIVEAU / MULTIPLICATEUR -- les deux viennent de l'`AbilityState` BAKE A LA POSE, donc celui de
    la **SOURCE** (`IdunBattle.Entities.Effects.BaseEffect$$GetAbilityState` =
    `IdunBattleLogic.Entities.DSLSelectors$$AbilityStateFromEffect(<noeud EFFET>)`, et le noeud pose
    est `AActiveAbility$$get_AbilityStateReference` = `DSLSelectors$$AbilityState(Caster@+0x48,
    <l'active courante>)`). Le port le transporte par `AddEffect(scale_from_source=True)` ; un effet
    SEEDE (etat charge, pose faite par le natif hors du port) retombe sur le porteur -- residu
    PARTAGE `#382`, pas un choix de cette classe. Il MORD ici : `extraDmg` ET `extraDmg_2` sont
    TOUS DEUX dans `variablesAffectedByRarityBonus` du kit."""

    def _level(self) -> "int | None":
        """`Level$$ToZeroBasedIndex(abilityState)` : la variable est celle d'une ability ACTIVE
        (`AbilityOrEffect.op_Implicit(ActiveAbilityType 0x4ba)` au `.ctor`, surcharge tranchee par
        son adresse). Repli sur le niveau passif puis sur le niveau d'effet, meme idiome que les
        18 autres classes qui lisent une ability ACTIVE (`war_howl.py`, `extra_damage.py`, ...)."""
        if self.active_ability_level is not None:
            return self.active_ability_level
        return self.ability_level if self.ability_level is not None else self.level

    def applied_traits(self) -> "list":
        """MIRROR de `IdunBattle.Entities.Effects.Loki.ExemplarOfTheMontkaEffect$$ApplyInternal` /
        `$$RevertInternal` :

            ApplyInternal (this, owner, target, effect)
                -> <IOperationProcessor @this+0x68>.<slot 0x26>(target, 0x412, isTemporary: 1)
            RevertInternal(this, owner, target, effect)
                -> <IOperationProcessor @this+0x68>.<slot 0x27>(target, 0x412, isTemporary: 1)

        Les deux slots sont resolus par la MEME interface et leur signature `(target, trait,
        isTemporary)` est celle de `IdunBattle.Core.Services.OperationProcessor$$AddTrait` /
        `$$RemoveTrait` -> `IdunBattle.Operations.AddTraitOperation$$Execute` /
        `IdunBattle.Operations.RemoveTraitOperation$$Execute`.

        `is_temporary = True` : cote natif il choisit la collection `BaseUnitComponent+0x48` et
        SUPPRIME la diffusion d'evenement ; cote port les deux collections sont fondues (cf.
        `runner/operations/traits.py`), le drapeau est transporte sans observable distinct.

        CONSOMMATEUR NATIF du trait : `StaticBattleRules.Effect$$NotBlockingMovementOfTraits`
        (Mounted / Vehicle / Unstoppable exemptent des effets de tuile bloquants), lu par
        `IdunBattle.Entities.Pathfinding.WalkPathfinder$$GetTileBlockingReasons` -- porte par
        `services/static_battle_rules.py`. C'est le MEME trait que pose `WarHowl` : le port en
        partage donc l'execution, pas seulement la declaration."""
        return [(UnitTrait.Unstoppable, True)]           # AddTrait(0x412, isTemporary: 1)

    def create_effect_damage_bonus_for_attack(self, is_ranged: "bool | None" = None,
                                              has_moved: "bool | None" = None,
                                              target_traits=None,
                                              is_prediction: bool = False,
                                              is_normal_attack: "bool | None" = True,
                                              target_armor_reduced: "bool | None" = None,
                                              att_ctx=None) -> "EffectBonus | None":
        """MIRROR de `IdunBattle.Entities.Effects.Loki.ExemplarOfTheMontkaEffect$$
        CreateEffectDamageBonusForAttack` :

            EffectBonus.ForAddition(
                get_OwnerIsCaster & IsNormalAttack,
                If( HasTrait(Target@DSLSelectors+0x60, 0x3f9 = BigTarget),
                    ConfigVar(0x09 = extraDmg_2), ConfigVar(0x08 = extraDmg) ) )

        DEUX noeuds de trigger seulement -- `get_OwnerIsCaster`, deja rendu par le canal (il n'est
        interroge que pour les attaques du PORTEUR, cf. `_attacker_effect_bonuses`), et
        `IsNormalAttack`, porte par le parametre du meme nom. **Aucun gate de nature de coup** :
        ne PAS lire `is_ranged` ici serait une omission chez WarHowl, c'est la fidelite ici.

        `target_traits is None` = cible NON MESUREE. Le natif, lui, evalue TOUJOURS son `If` : la
        contribution existe dans les deux branches, seule la MAGNITUDE change. Le port prend donc
        la branche `else` (`extraDmg`), ce qui est la degradation MINIMALE -- ne jamais accorder la
        magnitude MAJOREE sans avoir vu le trait. L'inverse (rendre `None`) supprimerait un bonus
        que le natif accorde toujours."""
        if is_normal_attack is not True:                   # IsNormalAttack
            return None
        big = _BIG_TARGET_TRAIT in (target_traits or ())   # HasTrait(Target@+0x60, 0x3f9)
        key = "extraDmg_2" if big else "extraDmg"          # If(<ci-dessus>, ConfigVar 9, ConfigVar 8)
        n = ability_var(_ABILITY_ID, key, self._level(),
                        multiplier_pct=self.ability_variables_multiplier)
        return for_addition(True, int(n)) if n else None
