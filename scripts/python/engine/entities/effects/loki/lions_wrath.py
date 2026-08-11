"""`TheLionsWrath_ExtraCritChance` (0x5f2 = **1522**) -- le buff de crit que `darkaBossLion` (« le
Lion ») pose SUR LUI-MEME au cast de son active `1217 TheLionsWrath`, et qui rend son SECOND coup
critique. #889.

## IDENTITE -- la config lue est l'ability ACTIVE 1217

`IdunBattleLogic.Entities.Abilities.Active.Loki.TheLionsWrathAbility$$ExecuteBehaviour` pose l'effet
par la surcharge a CINQ arguments de `IdunBattleLogic.Entities.DSLBehaviors$$AddEffect(this,
effectType, abilityState, targets, turns)` :

    AddEffect( 0x5f2 = 1522 TheLionsWrath_ExtraCritChance,
               AActiveAbility$$get_AbilityStateReference(this),
               targets = Owner@DSLSelectors+0x30,
               turns   = null )

-> pose sur le CASTER (`Owner`, pas `Target`), duree NON overridee (`DefaultAmountOfRounds`), et
l'`AbilityStateReference` bake l'etat d'ability du poseur : c'est CET etat que relit
`IdunBattle.Entities.Effects.BaseEffect$$GetAbilityState` pour indexer le `ConfigVar` ci-dessous.

## LE CANAL -- crit-CHANCE seul, et le porteur est l'ATTAQUANT

`IdunBattle.Entities.Effects.Loki.TheLionsWrath_ExtraCritChanceEffect$$CreateCritChanceBonus`,
mirror de l'ordre du decompile :

    EffectBonus.ForAddition(
        get_OwnerIsCaster
          & AmountIsEqual( CurrentHitIndex(), <DSLFormulas+0x20> ),
        ConfigVar( 0x3a = chance, GetAbilityState(effect), config@+0x60 ) )

Resolutions par les mirrors du build, jamais recopiees du decompile : `AbilityVariableType`
0x3a = 58 = `chance` (**PAS** `extraCritChance` = 0x41, qui est la variable de `1216
MartialExemplar` -- les deux abilities du meme boss lisent DEUX variables differentes, et l'ordinal
seul ne l'aurait pas dit) ; `<DSLFormulas+0x20>` = `Direct(1)` (`IdunBattleLogic.Entities.
DSLFormulas$$.ctor` pre-alloue `+0x18 = Direct(0)`, `+0x20 = Direct(1)`, `+0x28 = Direct(2)`,
`+0x30 = Direct(100)`, `+0x38 = Direct(-1)`).

⚠ **UN SEUL canal** : le build ne porte que `$$CreateCritChanceBonus` et `$$.ctor` pour cette
classe -- **aucun** `CreateCritDamageBonus`, **aucun** `CreateRemoveEffectTrigger`. L'effet decide
donc SI le coup crite (`IdunBattle.Core.Services.DamagePrediction$$RollCritical` =
`clamp(GetStat(9) + somme, 0, 100)`), jamais de COMBIEN ; et son RETRAIT n'est pas porte par un
trigger d'effet mais **par la phase 2** (`...TheLionsWrath_PendingAttackAbility$$CreateBehaviour`
finit par `RemoveEffect(Owner@+0x30, Nullable(0x5f2))`, HORS du `If` -- cf.
`runner/operations/triggers/loki/lions_wrath_attack.py`).

`get_OwnerIsCaster` = le PORTEUR de l'effet est l'ATTAQUANT du coup (contraste avec
`EuphoricStrikes_ExtraCrit` 1429, qui lit `get_OwnerIsTarget` et vit donc sur le DEFENSEUR).

`chance` du gameconfig 1217 = **100 a tous les niveaux** (65 entrees), et `nrOfHits = 2` : le
second coup de chaque cast est donc CRITIQUE PAR CONSTRUCTION (`clamp(cc + 100, 0, 100) = 100`),
sous reserve du gate `CouldCrit` (`GetStat(9) >= 1 && GetStat(10) > 0`) que `_crit_params` evalue
APRES la somme. `chance` est HORS `variablesAffectedByRarityBonus`
(`["minDmg", "maxDmg", "minDmg_2", "maxDmg_2"]`) -> aucun scaling de rarete ; `ability_var`
applique cette regle config-driven.

⚠ **`AmountIsEqual(CurrentHitIndex(), 1)` EXIGE l'index du coup, que le canal CRIT du port ne
threadait pas.** Le natif le passe (`IdunBattle.Core.Services.DamagePrediction$$
GetCritChanceBonusFromEffects(this, attaquant, defenseur, abilityOrEffect, **hitIndex**)`) ; le
port le pose desormais dans `att_ctx["hit_index"]` au foyer unique
(`runner/operations/damage.py::AttackDamageOperation._crit_params`). LIMITE ECRITE : le port ne
mesure la crit chance qu'a DEUX index (0 et 1+, cf. `_roll_crit(idx)` de `damage_hits.py`), la ou
le natif la relit a CHAQUE coup -- exact pour toute serie de 1 ou 2 coups, donc exact pour ce
porteur ; residu #889-r1 pour les series plus longues.
"""
from __future__ import annotations

from collections.abc import Mapping

from ..base import BaseEffect, owner_is_caster
from ..magnitude import ability_var

_ABILITY_ID = "TheLionsWrath"      # ActiveAbilityType 0x4c1 = 1217 (active, darkaBossLion)

#: `<DSLFormulas+0x20>` = `Direct(1)` -- le 2e operande de l'`AmountIsEqual`. Ecrit ici pour que le
#: littéral reste grepable a cote de sa lecture (`DSLFormulas$$.ctor`), pas dilue dans le predicat.
_CRIT_HIT_INDEX = 1


class TheLionsWrathExtraCritChanceEffect(BaseEffect):
    """`TheLionsWrath_ExtraCritChance` (0x5f2 = 1522) -- buff que le Lion pose sur LUI-MEME au cast
    de `1217 TheLionsWrath` : le coup d'index `1` (le SECOND des `nrOfHits = 2`) gagne
    +`chance` (= 100) points de chance de crit."""

    def _is_target_hit_index(self, att_ctx: "Mapping | None" = None) -> bool:
        """`AmountIsEqual( CurrentHitIndex(), <DSLFormulas+0x20> = Direct(1) )`.

        `IdunBattle.Entities.Formulas.CurrentHitIndexFormula$$Calculate` lit le compteur persistant
        de l'attaque en cours (`OngoingAttack+0x30`), le MEME que le port thread deja sous
        `hit_index0` / `next_hit_index`. Tri-etat : cle absente = index NON MESURE (appelant
        historique, probe, vecteur non mis a jour) => FAUX, jamais permissif."""
        v = (att_ctx or {}).get("hit_index")
        return v is not None and int(v) == _CRIT_HIT_INDEX

    def create_effect_crit_chance_bonus_for_attack(self, att_ctx: "Mapping | None" = None) -> "int | None":
        """MIRROR de `IdunBattle.Entities.Effects.Loki.TheLionsWrath_ExtraCritChanceEffect$$
        CreateCritChanceBonus` :

            EffectBonus.ForAddition(
                get_OwnerIsCaster & AmountIsEqual(CurrentHitIndex(), Direct(1)),
                ConfigVar(0x3a = chance, GetAbilityState(effect), config@+0x60) )

        Le retour est un ENTIER (pas un `EffectBonus`) : le canal natif somme des scalaires
        (`GetCritChanceBonusFromEffects` accumule `addition - subtraction`), et son consommateur est
        `clamp(GetStat(9) + somme, 0, 100)` dans `DamagePrediction$$RollCritical`.

        `GetAbilityState(effect)` indexe la config de l'ability **ACTIVE** 1217 : le niveau est
        `active_ability_level`, repli `ability_level` puis stack `level` -- l'effet est pose par une
        ACTIVE, via son `AbilityStateReference`."""
        if not owner_is_caster(att_ctx or {}):          # get_OwnerIsCaster (foyer UNIQUE, `base.py`)
            return None
        if not self._is_target_hit_index(att_ctx):      # AmountIsEqual(CurrentHitIndex(), 1)
            return None
        lvl = self.active_ability_level
        if lvl is None:
            lvl = self.ability_level if self.ability_level is not None else self.level
        n = ability_var(_ABILITY_ID, "chance", lvl,
                        multiplier_pct=self.ability_variables_multiplier)   # ConfigVar 0x3a
        return int(n) if n else None
