"""`EuphoricStrikes_ExtraCrit` (0x595 = **1429**) -- la marque que `emperExultant` (« Laviscus »)
pose sur la cible de son ability ACTIVE `EuphoricStrikes` (1198), et qui donne +crit-chance a la
PROCHAINE attaque portee contre elle. #522.

## IDENTITE -- la config lue est l'ability ACTIVE 1198, relue BYTE A BYTE

`IdunBattle.Entities.Effects.Loki.EuphoricStrikes_ExtraCritEffect$$.ctor` (octets du prologue) :

    48 8D 4C 24 40      lea  rcx, [rsp+0x40]                 ; buffer de retour
    BA AE 04 00 00      mov  edx, 0x4ae                      ; 1198
    E8 ..               call IdunBattle.Core.AbilityOrEffect$$op_Implicit
    41 B0 01            mov  r8b, 1                          ; hasAutomaticActivation: 1
    E8 ..               call IdunBattle.Entities.Effects.BaseEffect$$.ctor

`0x4ae = 1198` est `ActiveAbilityType.EuphoricStrikes` ; l'`EffectType`, lui, vaut **1429**. Les deux
ne se confondent donc pas -- meme forme qu'`EmpyricAmbush` (1232 / 1578). => la config est
`abilities.EuphoricStrikes`, et ses variables sont indexees par le niveau de l'ability **ACTIVE** de
la SOURCE (Laviscus), pas par un niveau de passif.

## POSE -- sur la CIBLE, par le CASTER, pour UN tour

`IdunBattleLogic.Entities.Abilities.Active.Loki.EuphoricStrikesAbility$$ExecuteBehaviour` :

    AActiveAbility.Execute(
        AttackWithAttackDamage( Caster@DSLSelectors+0x48, Target@+0x60, MinMaxDamage,
                                GetDamageProfile(), Get(GetHits()), AbilityOrEffect(this+0x10), ... )
      & AddEffect( 0x595 = 1429 EuphoricStrikes_ExtraCrit, AbilityStateReference,
                   source  = Caster@DSLSelectors+0x48,
                   targets = Target@+0x60,
                   turns   = <DSLFormulas+0x20> = Direct(1) ) )

`<DSLFormulas+0x20>` = `Direct(1)` (`IdunBattleLogic.Entities.DSLFormulas$$.ctor` pre-alloue
`+0x18 = Direct(0)`, `+0x20 = Direct(1)`, `+0x28 = Direct(2)`, `+0x30 = Direct(100)`,
`+0x38 = Direct(-1)`) => **UN tour**, PAS un `TurnsFromRounds`. La POSE est portee par
`runner/abilities/emperorschildren.py::EuphoricStrikesAbility` ; ce module-ci porte l'EFFET.

## LE CANAL -- crit-CHANCE seul, et le porteur est le DEFENSEUR

`IdunBattle.Entities.Effects.Loki.EuphoricStrikes_ExtraCritEffect$$CreateCritChanceBonus`, mirror de
l'ordre du decompile :

    EffectBonus.ForAddition(
        get_OwnerIsTarget
          & AmountIsGreaterThanZero( StatAmount( Caster@DSLSelectors+0x48,
                                                 statType = 0x9 = CritChance,
                                                 statPart = 0 = Current,
                                                 modificationEntity = null,
                                                 selectionType = 0 ) ),
        ConfigVar( 0x41 = extraCritChance, GetAbilityState(effect), config@+0x60 ) )

Signature relue : `IdunBattleLogic.Entities.DSLFormulas$$StatAmount(this, unit, statType, statPart,
modificationEntity, selectionType)` -- le `0x9` est donc bien le `statType` et le `0` qui suit le
`statPart`. Resolutions par les mirrors du build, jamais recopiees du decompile :
`IdunBattle.Entities.Enum.StatType` 9 = `CRIT_CHANCE`, `StatPart` 0 = `CURRENT`,
`AbilityVariableType` 0x41 = 65 = `extraCritChance`.

⚠ **UN SEUL canal** : contrairement a `EmpyricAmbush` (1578) et a `InescapableAccuracy` (1115/1116),
cet effet n'a **AUCUN** `CreateCritDamageBonus` -- le build ne porte que `$$CreateCritChanceBonus`,
`$$CreateRemoveEffectTrigger` et `$$.ctor` pour cette classe. Il decide donc SI le coup crite
(`IdunBattle.Core.Services.DamagePrediction$$RollCritical` = `clamp(GetStat(9) + somme, 0, 100)`),
jamais de COMBIEN. L'i2 le dit de meme : « The next attack against this unit has
+{[extraCritChance]}% Crit Chance ».

`get_OwnerIsTarget` (`IdunBattleLogic.Entities.DSLTriggers$$get_OwnerIsTarget` =
`AreEqual(Owner@DSLSelectors+0x30, Target@+0x60)`) : le PORTEUR de l'effet est le DEFENSEUR du coup.
C'est evaluable parce que le canal natif ECRASE `AbilityEntities+0x18` (`Owner`) par le porteur de
l'effet courant a chaque iteration de sa boucle -- le meme fait qui a impose l'elargissement du
balayage a `board_effect_carriers` (#589-r1-r1, cf. `entities/effects/__init__.py`).

`AmountIsGreaterThanZero(StatAmount(Caster, CritChance, Current))` : le SUJET est
`Caster@DSLSelectors+0x48` = **l'ATTAQUANT**, pas le porteur. Le bonus ne s'applique donc qu'a un
attaquant qui peut DEJA critiquer (`GetStat(9) > 0`). Une unite a crit-chance de base nulle ne
gagne rien -- exactement la meme forme de gate que `PathOfCommand` (`UnitsWithStatBiggerThan(
CRIT_CHANCE > 0)`, `entities/effects/loki/crit_aura.py`), ou l'`eldarFarseer` a cc=0 ne recevait
rien alors qu'il etait a portee.

⚠ `variablesAffectedByRarityBonus` d'`EuphoricStrikes` = `["minDmg", "maxDmg"]` : `extraCritChance`
n'y est **PAS**, donc aucun scaling de rarete. `ability_var` applique cette regle config-driven --
c'est pourquoi le multiplier est transmis plutot que teste ici.

## RETRAIT -- `On(9) & OwnerIsTarget | On(0) & Target == EffectSource`

`IdunBattle.Entities.Effects.Loki.EuphoricStrikes_ExtraCritEffect$$CreateRemoveEffectTrigger` :

      On( 9 = EventTriggerType.Attack,    ownerNeedsToBeAlive: true ) & get_OwnerIsTarget
    | On( 0 = EventTriggerType.UnitDeath, ownerNeedsToBeAlive: true )
        & AreEqual( Target@DSLSelectors+0x60, EffectSource(Effect@DSLSelectors+0x38) )

(`IdunBattleLogic.Entities.DSLTriggers$$On(this, triggerType, ownerNeedsToBeAlive)` -- signature
relue, le second litteral est le drapeau, pas un second event.)

C'est ce qui fait de ce +crit une CHARGE A USAGE UNIQUE (« The **next** attack against that enemy
this turn ») et non un buff qui durerait tout le tour. Porte dans
`runner/operations/triggers/loki/euphoric_strikes.py` (`EFFECT_TRIGGERS[1429]`), meme greffe
generique que 1550/1180 : `IdunBattle.Entities.Effects.BaseEffect$$CreateHandleTriggerAbilities`
ajoute `Triggered(CreateRemoveEffectTrigger(), DSLFactory.RemoveEffect(df@0x150))` quand le virtuel
rend un trigger non nul.
"""
from __future__ import annotations

from collections.abc import Mapping

from ..base import BaseEffect
from ..magnitude import ability_var

_ABILITY_ID = "EuphoricStrikes"      # ActiveAbilityType 0x4ae = 1198 (active, emperExultant)


class EuphoricStrikesExtraCritEffect(BaseEffect):
    """`EuphoricStrikes_ExtraCrit` (0x595 = 1429) -- marque posee par `emperExultant` (« Laviscus »)
    sur la cible de son ability active, pour UN tour : la PROCHAINE attaque portee contre l'unite
    marquee gagne +`extraCritChance` de chance de crit, a condition que son attaquant puisse deja
    critiquer (`GetStat(CritChance) > 0`)."""

    def _owner_is_target(self, att_ctx: "Mapping | None" = None) -> bool:
        """`IdunBattleLogic.Entities.DSLTriggers$$get_OwnerIsTarget` = `AreEqual(Owner@+0x30,
        Target@+0x60)` -- « le PORTEUR de cet effet est-il le defenseur du coup ? ».

        `owner_id` est pose PAR PORTEUR par l'agregateur (`crit_chance_bonus_from_effects`), mirror
        de l'ecriture `AbilityEntities+0x18 (Owner) <- le porteur de l'effet` que le canal natif
        fait a chaque iteration. Identite NON PROUVEE (l'une des deux cles absente) => le noeud est
        FAUX, jamais permissif (meme foyer de raisonnement qu'`EmpyricAmbushEffect._owner_is_target`)."""
        c = att_ctx or {}
        oid, tid = c.get("owner_id"), c.get("tgt_id")
        return oid is not None and tid is not None and oid == tid

    def _caster_can_crit(self, att_ctx: "Mapping | None" = None) -> bool:
        """`AmountIsGreaterThanZero( StatAmount(Caster@+0x48, 0x9 = CritChance, 0 = Current,
        null, 0) )` -- l'ATTAQUANT a-t-il une chance de crit STRICTEMENT positive ?

        La cle `caster_crit_chance` est posee par le foyer UNIQUE du canal
        (`runner/operations/damage.py::AttackDamageOperation._crit_params`), qui la lit comme
        `ctx.stat(StatType.CRIT_CHANCE)` -- donc la valeur COURANTE de l'attaquant, la meme que celle
        que le natif lit dans `RollCritical`, et AVANT la somme des bonus d'effets (le natif lit ici
        `GetStat`, pas le total). Tri-etat : cle absente = grandeur NON MESUREE (appelant historique
        ou probe) => le noeud est FAUX, jamais permissif."""
        v = (att_ctx or {}).get("caster_crit_chance")
        return v is not None and int(v) > 0

    def create_effect_crit_chance_bonus_for_attack(self, att_ctx: "Mapping | None" = None) -> "int | None":
        """MIRROR de `IdunBattle.Entities.Effects.Loki.EuphoricStrikes_ExtraCritEffect$$CreateCritChanceBonus` :

            EffectBonus.ForAddition(
                get_OwnerIsTarget & AmountIsGreaterThanZero(StatAmount(Caster, CritChance, Current)),
                ConfigVar(0x41 = extraCritChance, GetAbilityState(effect), config@+0x60) )

        Le retour est un ENTIER (pas un `EffectBonus`) : le canal natif somme des scalaires
        (`GetCritChanceBonusFromEffects` accumule `addition - subtraction`), et son consommateur est
        `clamp(GetStat(9) + somme, 0, 100)` dans `DamagePrediction$$RollCritical`.

        `GetAbilityState(effect)` indexe la config de l'ability **ACTIVE** 1198 : le niveau est
        `active_ability_level`, repli `ability_level` puis stack `level` (l'effet est pose par une
        ACTIVE, cf. la surcharge d'`op_Implicit` relue octet a octet en tete de module).
        `extraCritChance` n'est PAS dans `variablesAffectedByRarityBonus` -> aucun scaling de rarete ;
        `ability_var` applique cette regle config-driven."""
        if not self._owner_is_target(att_ctx):          # get_OwnerIsTarget
            return None
        if not self._caster_can_crit(att_ctx):          # AmountIsGreaterThanZero(StatAmount(...))
            return None
        lvl = self.active_ability_level
        if lvl is None:
            lvl = self.ability_level if self.ability_level is not None else self.level
        n = ability_var(_ABILITY_ID, "extraCritChance", lvl,
                        multiplier_pct=self.ability_variables_multiplier)   # ConfigVar 0x41
        return int(n) if n else None
