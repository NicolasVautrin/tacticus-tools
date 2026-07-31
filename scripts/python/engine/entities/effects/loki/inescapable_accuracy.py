"""`InescapableAccuracy_extraCritChance` (0x45b = **1115**) — le volet CHANCE DE CRIT du passif
`InescapableAccuracy` (TriggeredAbilityType 0x45b = 1115) d'`eldarMauganRa`. case-366-r1.

## TROIS classes natives, pas une — tranche par le SLOT `Il2CppClass*`, jamais par le nom du ctor

La fiche d'inventaire annoncait « classe propre, ctor fondu avec 1116 ». Le ctor EST fondu (un seul
corps pour les trois ids) mais les CLASSES sont bien TROIS, et c'est le slot qui le dit :
`IdunBattle.Core.Services.EffectsDatabase.u003Cu003Ec$$u003CInitializeEffectsu003Eb__14_141`,
`...b__14_142` et `...b__14_143` allouent chacune depuis un `Il2CppClass*` DIFFERENT, puis appellent
le MEME corps de `$$.ctor` (IL2CPP deduplique les corps bit-identiques -- et ce corps l'est, parce
que les trois classes derivent de `BaseEffect` avec la MEME constante d'ability).

Les trois tables de methodes le confirment : chacune porte `.ctor` + `CreateActiveCondition` +
`CreateTargetSelector` (le corps partage `= <DSLSelectors+0x30>` = Owner) PLUS **une** methode qui lui
est propre --
`...InescapableAccuracy_ExtraCritChanceEffect$$CreateCritChanceBonus` (CETTE classe, 1115),
`...InescapableAccuracy_ExtraCritDamageEffect$$CreateCritDamageBonus` (1116),
`...InescapableAccuracy_OverridHitsEffect$$ActiveCondition` + `$$CreateBlockHitReductionTrigger`
(1117). Ce port ne couvre QUE le chemin de 1115.

## SOURCE DE CONFIG — la TRIGGERED 1115, pas l'EffectType 1115 (homonymie a deux faces)

Le corps de ctor partage :

    mov edx, 0x45b                                        ; 1115
    call IdunBattle.Core.AbilityOrEffect$$op_Implicit      ; surcharge TRIGGERED (tranchee par son
                                                          ;  ADRESSE : c'est celle dont le corps
                                                          ;  appelle `AbilityOrEffect$$set_
                                                          ;  TriggeredAbility`, les quatre
                                                          ;  surcharges portent le meme nom)
    call IdunBattle.Entities.Effects.BaseEffect$$.ctor(this, abilityOrEffect,
                                                      hasAutomaticActivation: 1)

`0x45b` vaut 1115 dans DEUX enums (`EffectType.InescapableAccuracy_extraCritChance` ET
`TriggeredAbilityType.InescapableAccuracy`, dump `enums.tsv`) : c'est le second qui est lu ici, et
c'est aussi la seule lecture COHERENTE -- sinon 1116 et 1117, qui partagent ce corps, liraient la
config de l'effet 1115. => la config est `abilities.InescapableAccuracy`, indexee par le niveau
d'ability **PASSIVE** du porteur.

## POSE — `InescapableAccuracyAbility$$CreateBehaviour` (les trois d'un bloc)

MIRROR du decompile :

    AddEffect(0x45b = 1115, <abilityStateReference>, targets = <DSLSelectors+0x30> = Owner, turns = NULL)
  + AddEffect(0x45c = 1116, <idem>)
  + AddEffect(0x45d = 1117, <idem>)
    (les trois fusionnes par `IdunBattle.DSL.AbilityBehaviour$$op_Addition`)

`turns = NULL` => PERMANENT : ce qui l'eteint est la CONDITION, pas une duree.

## CANAL — `CreateCritChanceBonus`, DEUX noeuds (et pas quatre)

    EffectBonus.ForAddition( get_OwnerIsCaster & IsRangedAttack,
                             ConfigVar(0x41 = extraCritChance, GetAbilityState(effect), config@+0x60) )

C'est le canal ouvert par `1222 WarHowl_ExtraDamage_Unstoppable` (case-366-r1) :
`IdunBattle.Core.Services.DamagePrediction$$GetCritChanceBonusFromEffects` accumule
`addition - subtraction` de chaque `EffectBonus`, et son consommateur unique est
`IdunBattle.Core.Services.DamagePrediction$$RollCritical` = `clamp(GetStat(9) + somme, 0, 100)`.
**N'HERITE RIEN DE SON VOISIN** : la ou WarHowl porte QUATRE noeuds
(`get_OwnerIsCaster & IsMeleeAttack & IsNormalAttack & AmountIsGreaterThanZero(StatAmount(Caster,
CriticalChance))`), celui-ci n'en porte que DEUX -- le gate d'attaque est l'INVERSE
(`IsRangedAttack`, surcharge SANS argument, tranchee par la cible du `call` :
`IdunBattleLogic.Entities.DSLTriggers$$IsRangedAttack` -> `IsRangedAttackAbilityTrigger`), il n'y a
**pas** de `IsNormalAttack` (le bonus vaut donc aussi pour les attaques d'ABILITY) et **pas** de
`AmountIsGreaterThanZero` (cf. le residu `CouldCrit` en fin de docstring).

## ACTIVE-CONDITION — `NOT HasFlag(Owner, UnitFlag.Moved)`

Le corps partage par les trois classes (`...InescapableAccuracy_ExtraCritDamageEffect$$
CreateActiveCondition` -- nom Ghidra du proprietaire arbitraire d'un corps DEDUPLIQUE, present dans
les TROIS tables de methodes) :

    op_LogicalNot( HasFlag( <DSLSelectors+0x30> = Owner, flag = 0 ) )

`IdunBattleLogic.Entities.DSLTriggers$$HasFlag` alloue un
`IdunBattle.Entities.Conditions.HasFlagAbilityTrigger(unit, flag, contains: 1)` dont le
`$$ShouldTrigger` est `IdunBattle.Entities.Components.UnitFlagsComponent$$Has(unit, flag)` ;
`flag = 0` = `UnitFlag.Moved` (cf. `runner/components.py::UnitFlagsComponent.MOVED`, meme foyer que
`unit_has_moved`). => **Maugan Ra qui a bouge ce tour ne beneficie plus du bonus.** Meme predicat
natif que `IdunBattle.Entities.Effects.Loki.CrushingStrikeEffect$$CreateActiveCondition` (#98), et
i2 le dit aussi (`Abilities/InescapableAccuracy_CurrentLevelDescription`).

Le port le rend DEUX fois, comme `ModifiedExoarmour_ExtraDmg` (case-322) rend son
`AmountIsGreaterThanZero(TilesMovedThisTurn)` : par `is_active` (la place NATIVE de la condition,
qui vaut pour tout consommateur d'`active_effects`) et par le gate du canal (`att_ctx["has_moved"]`,
pose au foyer unique `AttackDamageOperation._crit_params`). La redondance est assumee : les deux
lisent le MEME store, `UnitFlagsComponent`.

## MAGNITUDE

`ConfigVar(0x41)` = `gameconfig.ability("InescapableAccuracy").variables["extraCritChance"][level]`
(10 -> 15 sur 65 niveaux ; **15** au niveau normalise 50). `extraCritChance` n'est **PAS** dans
`variablesAffectedByRarityBonus` de cette ability (qui ne contient que `extraCritDmg`) -> aucun
scaling de rarete, et `ability_var` applique cette regle config-driven toute seule. Le residu #382
(« le multiplicateur vient de la SOURCE, le port lit le PORTEUR ») est donc DOUBLEMENT inerte ici :
la variable n'est pas scalee, et l'effet est pose sur son propre porteur (source == porteur).

## HYPOTHESE REFUTEE PAR LA MESURE — il n'y a PAS de residu `could_crit` ici

`IdunBattle.Core.Services.DamageCalculations$$CouldCrit(attacker)` lit bien `GetStat(9)` et
`GetStat(10)` BRUTES (le bonus d'effet n'y entre pas), et l'absence du gate
`AmountIsGreaterThanZero` -- que le voisin `1222` porte, lui -- faisait CRAINDRE que le port crite
la ou le natif ne crite pas, sur un porteur a `GetStat(9) == 0`.

**MESURE LIVE (`--crit 0,700`, `GetStat(9) = 0`) : le natif CRITE.** Le chemin d'execution ne passe
pas par `CouldCrit` (qui n'a que des xrefs DATA, donc n'est invoque que par slot d'interface) mais
par `IdunBattle.Core.Services.DamagePrediction$$RollCritical`, dont le gate est
`clamp(GetStat(9) + GetCritChanceBonusFromEffects, 0, 100) >= 1` -- **bonus INCLUS**. Le port, qui
passe `GetStat(9) + somme` a `could_crit`, rend donc exactement le meme gate. Les deux tirent, et le
coup mesure est bit-exact. Le carre du probe le montre dans les deux sens : sans le canal, le port
retombe a `could_crit(0, 700)` = faux, ne tire RIEN, et le coup cesse d'etre un crit.
"""
from __future__ import annotations

from collections.abc import Mapping

from ..base import BaseEffect, is_ranged_attack
from ..magnitude import ability_var

_ABILITY_ID = "InescapableAccuracy"   # TriggeredAbilityType 0x45b = 1115 (passif, eldarMauganRa)


class InescapableAccuracyExtraCritChanceEffect(BaseEffect):
    """`InescapableAccuracy_extraCritChance` (0x45b = 1115) — +extraCritChance% de chance de crit sur
    les attaques A DISTANCE du porteur, tant qu'il n'a pas bouge ce tour."""

    def _level(self) -> "int | None":
        """`Level$$ToZeroBasedIndex(GetAbilityState(effect))` : `InescapableAccuracy` est une ability
        PASSIVE (`GC.unit("eldarMauganRa").passiveAbilities`) -> l'index est `ability_level`
        (= `unitConfig.passiveAbilityLevel`, propage par `EffectsState.seed`), repli stack level."""
        return self.ability_level if self.ability_level is not None else self.level

    def is_active(self, unit_state: "Mapping | None" = None) -> bool:
        """`CreateActiveCondition` = `op_LogicalNot(HasFlag(Owner, 0 = UnitFlag.Moved))`.

        `has_moved` ABSENT du `unit_state` = **non mesure** -> on ne ferme pas (degradation fidele,
        meme regime que `ModifiedExoarmour_ExtraDmg` avec `tiles_moved_this_turn`). Cote COMBAT la
        cle EST posee : `UnitEffectStateView` la lit du `UnitFlagsComponent` via `unit_has_moved`,
        le store UNIQUE du fait « a bouge ce tour » (pose par `MoveUnitOperation`, purge par
        `RemoveTurnFlags` du `StartTurnOperation`)."""
        m = (unit_state or {}).get("has_moved")
        return True if m is None else not bool(m)

    def create_effect_crit_chance_bonus_for_attack(self, att_ctx: "Mapping | None" = None) -> "int | None":
        """MIRROR de `IdunBattleLogic.Entities.Abilities.Triggered.Loki.
        InescapableAccuracy_ExtraCritChanceEffect$$CreateCritChanceBonus` :

            EffectBonus.ForAddition( get_OwnerIsCaster & IsRangedAttack,
                                     ConfigVar(0x41 = extraCritChance, GetAbilityState(effect),
                                               config@+0x60) )

        Le retour est un ENTIER (pas un `EffectBonus`) : le canal natif somme des scalaires
        (`GetCritChanceBonusFromEffects` accumule `addition - subtraction` de chaque `EffectBonus`),
        et son consommateur est `clamp(GetStat(9) + somme, 0, 100)` dans `RollCritical`.

        Les cles lues d'`att_ctx` sont chacune UN noeud natif, jamais un besoin d'effet, et une cle
        ABSENTE fait TAIRE son gate (« present != applique ») :
          * `is_ranged`  -> `IsRangedAttack` (tri-etat #106, cf. `is_ranged_attack` : nature non
            PROUVEE distance => aucune contribution) ;
          * `has_moved`  -> l'`ActiveCondition` `NOT HasFlag(Owner, UnitFlag.Moved)`. Ferme des que
            le mouvement est PROUVE ; la cle absente laisse passer, exactement comme
            `CrushingStrikeEffect` (#98), qui porte le MEME predicat natif par le MEME idiome.

        `get_OwnerIsCaster` est rendu par le CANAL (`crit_chance_bonus_from_effects` n'itere que les
        effets de l'ATTAQUANT). AUCUN gate `IsNormalAttack` cote natif -> le bonus vaut aussi pour
        les attaques d'ABILITY a distance ; ne pas en ajouter un par analogie avec 1222."""
        c = att_ctx or {}
        if not is_ranged_attack(c.get("is_ranged")):        # IsRangedAttack
            return None
        if c.get("has_moved"):                              # ActiveCondition NOT HasFlag(Moved)
            return None
        n = ability_var(_ABILITY_ID, "extraCritChance", self._level(),   # ConfigVar 0x41
                        multiplier_pct=self.ability_variables_multiplier)
        return int(n) if n else None
