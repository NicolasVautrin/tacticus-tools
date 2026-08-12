"""`Skullsmasher` (`TriggeredAbilityType 0x4c1 = 1217`) -- passif de kit de `worldJakhal`
<< Macer >> (World Eaters / Chaos), HERO **DU POOL**.

i2 `Abilities/Skullsmasher_CurrentLevelDescription` :
    << Macer deals +{[extraDmg]} Damage for each {[hpPct]}% of his maximum Health he is currently
    missing. In addition, if Macer has defeated an enemy this battle, all enemies he attacks become
    Stunned. >>

===================================================================================================
RECENSEMENT PAR LE BLOC `methodPointers` (jamais par grep de nom)
===================================================================================================

Le gameconfig ne connait qu'un nom (`passiveAbilities: [Skullsmasher]`) ; le build en derive TROIS
classes d'ability, de bases DIFFERENTES -- lues dans `data/symbols/<build>/frida/classes.tsv`,
jamais dans le nom du `.ctor` :

    IdunBattleLogic...Triggered.Loki.Skullsmasher_DamageEffectAbility  : AOwnerEffectTriggeredAbility
        -> [ GetEffectType, .ctor ]         (bloc `methodPointers` : DEUX entrees, rien d'autre)
    IdunBattleLogic...Triggered.Loki.Skullsmasher_ActivateStunAbility  : BaseTriggeredAbility
        -> [ CreateTrigger, CreateBehaviour, .ctor ]
    IdunBattleLogic...Triggered.Loki.Skullsmasher_TriggerStunAbility   : BaseTriggeredAbility
        -> [ CreateTrigger, CreateBehaviour, .ctor ]

et UNE classe d'effet, dont le bloc `methodPointers` porte SEPT corps (les deux premiers FONDUS
par l'ICF, donc invisibles a tout grep de nom) :

    IdunBattle.Entities.Effects.Loki.Skullsmasher_ExtraDamageEffect (`EffectType 0x4ef = 1263`)
        [ .ctor, CreateActiveCondition, CreateTargetSelector = <0xeb6650>, CreateEffectDamage
          BonusForAttack, GetAttackModifier, GetMissingHealthSteps, GetLocalizationDataInternal ]

⚠ **`CreateTargetSelector` EXISTE et vaut le corps par DEFAUT** -- `<DSLSelectors+0x30>` = `Owner`
(corps `return Selectors@+0x30`, que ghidra etiquette `WhisperingWebEffect$$CreateTargetSelector`).
C'est donc un SELF-effect, **PAS une aura** : le distinguer de l'aura d'`ObsessiveAnnunciation`
(meme lot, meme canal) exige de lire le CORPS, pas la seule presence de la methode.

CE QUI N'EXISTE PAS, et c'est un RESULTAT :
  * `Skullsmasher_DamageEffectAbility` n'a NI `CreateTrigger` NI `CreateBehaviour` propres -> tout
    vient d'`AOwnerEffectTriggeredAbility` (`OnOwnerSpecificAbilityInit(this.AbilityType)` puis
    `AddEffect(GetEffectType(), AbilityState(Owner), source = Owner, targets = Owner)`), donc un
    owner-effect PERMANENT pose a l'INIT -> `ABILITY_INIT_OWNER_EFFECTS`, **jamais**
    `ABILITY_TRIGGERS`. `$$GetEffectType` a pour corps ENTIER `return 0x4ef` : l'appariement
    ability -> effet est LU, pas devine.
  * aucun `SkullsmasherPlaybook` dans le build, et **aucune cle `Skullsmasher*` dans
    `BC.Utilities`** -> face DECISION INEXISTANTE (contraste `ObsessiveAnnunciation`, du meme lot).

===================================================================================================
L'ARBRE DE MAGNITUDE (mirror 1:1, surcharges tranchees par l'ADRESSE de la cible du `call`)
===================================================================================================

    $$GetMissingHealthSteps =
        Divide( Percent( StatAmount(Owner@+0x30, StatType.Health = 5, StatPart.Missing = 4,
                                    modificationEntity = null),
                         StatAmount(Owner@+0x30, StatType.Health = 5, StatPart.Maximum = 2,
                                    modificationEntity = null),
                         RoundingRule.Default = 0 ),
                ConfigConst(AbilityConstantType.hpPct = 0x12),
                RoundingRule.Floor = 2 )

    $$GetAttackModifier =
        Max( <DSLFormulas+0x18> = Direct(0),
             Multiply( GetMissingHealthSteps(), ConfigVar(AbilityVariableType.extraDmg = 8,
                                                          GetAbilityState(this), config@this+0x60) ) )

    $$CreateActiveCondition =
        AmountIsGreaterThanZero( GetMissingHealthSteps() )        # surcharge `IAmountFormula`

    $$CreateEffectDamageBonusForAttack =
        EffectBonus.ForAddition( get_OwnerIsCaster, GetAttackModifier() )

  * `Percent(a, b, rounding)` = `a x 100 / b` -> le POURCENTAGE de PV manquants ; `Divide(pct, hpPct,
    Floor)` -> le NOMBRE DE PALIERS de `hpPct` % franchis. `hpPct` est une **CONSTANTE**
    (`ConfigConst` = `GetNumberConstant`), donc ni indexee par niveau ni scalee par la rarete ;
    `extraDmg` est une VARIABLE, et elle EST dans `variablesAffectedByRarityBonus` (`[8]` au BC).
  * `<DSLFormulas+0x18>` = `Direct(0)` -- le `.ctor` de `DSLFormulas` y ecrit `Direct(0)` (voisins :
    `+0x20 = 1`, `+0x28 = 2`, `+0x30 = 100`, `+0x38 = -1`). Le `Max` est donc un PLANCHER a zero,
    pas un gate.
  * les DEUX surcharges d'`AmountIsGreaterThanZero` existent (`ITargetsSelector` = `0xed5360`,
    `IAmountFormula` = `0xed52d0`) : c'est la SECONDE qui est appelee (`E8 rel32` -> `0x180ed52d0`).
  * les DEUX surcharges de `StatAmount` du meme nom n'existent pas ; celle-ci est
    `(unit, statType, statPart, modificationEntity, selectionType)` -- son 4e argument est NUL
    (aucune source de modification), donc la lecture est la stat TOTALE.

## Ce que la recopie du voisin de forme aurait efface

`Skullsmasher_ExtraDamage` rejoint la fratrie des `CreateEffectDamageBonusForAttack` a UN SEUL
conjoint (`get_OwnerIsCaster`), comme `HeadClaimer_ExtraDamage` (#947) -- ni `IsRangedAttack`
(l'attaque normale de Macer est MELEE), ni `IsNormalAttack` (le bonus vaut aussi pour
`JakhalStimms`). Mais sa MAGNITUDE n'est PAS celle de la fratrie `Multiply(ConfigVar, EffectLevel)` :
elle ne lit AUCUN niveau d'effet -- elle lit les PV du porteur A CHAQUE COUP. Et il porte, LUI, une
`CreateActiveCondition` que ses trois voisins n'ont pas.
"""
from __future__ import annotations

from collections.abc import Mapping

from ....services.effect_bonus import EffectBonus, for_addition
from ...effect_type import EffectType   # #270-r1-r1-r3
from ..base import BaseEffect
from ..magnitude import ability_var

#: cle gameconfig de l'ability -- la config que `ConfigVar` / `ConfigConst` indexent
#: (`TriggeredAbilityType.Skullsmasher = 1217`).
ABILITY_ID = "Skullsmasher"
#: `AbilityVariableType 8` et `AbilityConstantType 0x12 = 18` (`frida/enums.tsv`, resolus par leur
#: NOM -- l'ordinal 0x12 nomme `dmgReduction` dans l'AUTRE enum, `AbilityVariableType`).
VAR_EXTRA_DMG = "extraDmg"
CONST_HP_PCT = "hpPct"

#: `EffectType 0x4f0 = 1264` -- le MARQUEUR << Macer a deja tue >>, pose sur le porteur par
#: `Skullsmasher_ActivateStunAbility` et LU par le `CreateTrigger` de `Skullsmasher_TriggerStunAbility`.
#: ⚠ `TriggeredAbilityType` 1264 nomme `VisionsOfHeresy` -- une ability qui EXISTE, donc une
#: confusion d'enum ne leverait pas : elle lirait une autre config.
SKULLSMASHER_STUN_MARKER = EffectType.Skullsmasher_StunEffect

#: Cle d'`att_ctx` portant `StatAmount(Owner, Health, {Missing, Maximum})` -- un COUPLE
#: `(hp_courant, hp_max)`, tri-etat `(None, None)` = NON MESURE. Meme substrat (`HealthComponent`)
#: que `unit_health_of` du canal CRIT et que les cles `hp`/`max_hp` du `unit_state`, pour que deux
#: axes qui lisent la MEME grandeur ne puissent pas diverger.
CTX_OWNER_HEALTH = "owner_health"


def _missing_health_steps(health: "tuple | None") -> "int | None":
    """`...Skullsmasher_ExtraDamageEffect$$GetMissingHealthSteps` -- mirror 1:1 :

        Divide( Percent( StatAmount(Owner, Health, Missing), StatAmount(Owner, Health, Maximum),
                         RoundingRule.Default ),
                ConfigConst(hpPct), RoundingRule.Floor )

    `health` = `(courant, maximum)`. Tri-etat : `None` (couple absent, `maximum` nul ou `hpPct`
    illisible) = **NON MESURE** -> l'appelant se tait, jamais un 0 rabattu (qui eteindrait le
    bonus en silence au lieu de le declarer non mesurable).

    ARRONDIS. `Percent` est `RoundingRule.Default` et `Divide` est `RoundingRule.Floor` : le port
    calcule le pourcentage en ENTIER (division euclidienne du produit par le maximum, ce que rend
    `Fix64` sur des grandeurs entieres) puis PLANCHE le quotient par `hpPct`. Les deux etages sont
    SEPARES, donc falsifiables l'un sans l'autre."""
    if not health:
        return None
    cur, mx = health
    if cur is None or mx is None or int(mx) <= 0:
        return None
    step = ability_var(ABILITY_ID, CONST_HP_PCT, is_constant=True)     # ConfigConst(hpPct)
    if not step or int(step) <= 0:
        return None
    missing = max(0, int(mx) - int(cur))                # StatAmount(Owner, Health, Missing)
    pct = (missing * 100) // int(mx)                    # Percent(missing, maximum, Default)
    return pct // int(step)                             # Divide(pct, hpPct, Floor)


class SkullsmasherExtraDamageEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.Skullsmasher_ExtraDamageEffect` (`EffectType 0x4ef = 1263`,
    nom capte `Skullsmasher_ExtraDamage`) -- owner-effect PERMANENT de `worldJakhal`, pose a l'init
    par `Skullsmasher_DamageEffectAbility` (`AOwnerEffectTriggeredAbility`, `GetEffectType` =
    `return 0x4ef`). Cf. l'en-tete du module pour les arbres natifs et le recensement.

    ⚠ Les DEUX faces (condition d'activite et magnitude) partagent le MEME etage
    `GetMissingHealthSteps` -- c'est litteralement le meme corps natif, appele deux fois. Le port le
    factorise dans `_missing_health_steps` pour la MEME raison : les deux ne peuvent pas diverger."""

    #: `$$CreateActiveCondition` EXISTE (corps PROPRE, pas un corps fondu) -> le port evalue le gate
    #: lui-meme au lieu de se fier au flag `IsActive` capte. Contraste `HeadClaimer` (#947), dont
    #: aucun des deux effets n'en declare.
    active_condition_ported = True

    def is_active(self, unit_state: "Mapping | None" = None) -> bool:
        """`$$CreateActiveCondition` = `AmountIsGreaterThanZero( GetMissingHealthSteps() )`
        (surcharge `IAmountFormula` = `0xed52d0`, tranchee par l'ADRESSE de la cible du `call`).

        `AmountIsGreaterThanZeroAbilityTrigger$$ShouldTrigger` compare `> 0` : a PV PLEINS le nombre
        de paliers vaut 0, donc l'effet est INACTIF -- et le premier palier n'est franchi qu'a
        `hpPct` % de PV manquants. Substrat = `hp` / `max_hp` du `unit_state` (le MEME que la
        magnitude, via `CTX_OWNER_HEALTH` cote coup) ; `unit_state` muet -> on retombe sur le regime
        commun (`BaseEffect.is_active`), c.-a-d. le flag capte, jamais un gate invente."""
        us = unit_state or {}
        hp, mx = us.get("hp"), us.get("max_hp")
        if hp is None or mx is None:
            return super().is_active(unit_state)
        steps = _missing_health_steps((hp, mx))
        return bool(steps and steps > 0)

    def create_effect_damage_bonus_for_attack(self, is_ranged: bool | None = None,
                                              has_moved: bool | None = None,
                                              target_traits: "frozenset[str] | None" = None,
                                              is_prediction: bool = False,
                                              is_normal_attack: bool | None = True,
                                              target_armor_reduced: bool | None = None,
                                              att_ctx=None) -> EffectBonus | None:
        """`ForAddition( get_OwnerIsCaster, Max(Direct(0), Multiply(GetMissingHealthSteps(),
        ConfigVar(extraDmg))) )`.

        `get_OwnerIsCaster` est satisfait STRUCTURELLEMENT sur ce canal : l'agregateur n'itere que
        les effets de l'ATTAQUANT. AUCUN autre noeud dans la conjonction -> aucun re-gate
        `is_ranged` / `is_normal_attack` (l'attaque normale de Macer est MELEE, et `JakhalStimms`
        est une ability : les deux beneficient du bonus).

        `att_ctx[CTX_OWNER_HEALTH]` = `(hp, hp_max)` du PORTEUR, qui EST l'attaquant sur ce canal.
        Cle absente / non mesuree -> `None` (« present != applique »), jamais un bonus devine."""
        steps = _missing_health_steps((att_ctx or {}).get(CTX_OWNER_HEALTH))
        if steps is None:
            return None
        if self.ability_level is None:                  # ConfigVar sans AbilityState -> inerte
            return None
        per = ability_var(ABILITY_ID, VAR_EXTRA_DMG, self.ability_level,
                          multiplier_pct=self.ability_variables_multiplier)
        if not per:
            return None
        # `Max(Direct(0), Multiply(steps, per))` : les deux facteurs sont >= 0 ici, le plancher est
        # donc inerte -- il est ecrit parce que le natif l'ecrit, et parce qu'un `extraDmg` negatif
        # au gameconfig le rendrait mordant.
        amount = max(0, int(steps) * int(per))
        return for_addition(True, amount) if amount else None
