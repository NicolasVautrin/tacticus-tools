"""`MartialExemplar_ExtraCritChance` (0x5f0 = **1520**) -- le buff de crit que `darkaBossLion`
(« le Lion ») pose SUR LUI-MEME au cast de son active `1216 MartialExemplar`, et qui ne mord que
sur les SUMMONS. #889-r5.

## IDENTITE -- la config lue est l'ability ACTIVE 1216

`IdunBattleLogic.Entities.Abilities.Active.Loki.MartialExemplarAbility$$ExecuteBehaviour` pose
l'effet par la surcharge a CINQ arguments de `IdunBattleLogic.Entities.DSLBehaviors$$AddEffect` :

    AddEffect( 0x5f0 = 1520 MartialExemplar_ExtraCritChance,
               AActiveAbility$$get_AbilityStateReference(this),
               targets = Owner@DSLSelectors+0x30,
               turns   = <DSLFormulas+0x20> = Direct(1) )

-> pose sur le CASTER (`Owner`, pas `Target`), duree **1 TOUR** (le 5e argument est le champ
pre-alloue `Direct(1)` du `DSLFormulas$$.ctor`, PAS `null` -- c'est la difference avec
`1217 TheLionsWrath`, qui passe bien `null` au meme rang), et l'`AbilityStateReference` bake l'etat
d'ability du poseur : c'est CET etat que relit `IdunBattle.Entities.Effects.BaseEffect$$
GetAbilityState` pour indexer le `ConfigVar` ci-dessous.

⚠ **L'ORDINAL 1520 EST PARTAGE, ET IL DESIGNE DEUX CHOSES.** `EffectType(1520)` est CET effet ;
`TriggeredAbilityType(1520)` est `TheLionsWrath_PendingAttack`, la phase 2 de l'AUTRE active du
MEME boss. Les deux vivent dans le meme fichier de kit et se lisent au meme ordinal : seul le NOM
tranche. C'est l'`AddEffect` (dont le 2e argument est un `EffectType`) qui fixe l'enum ici.

## LE CANAL -- crit-CHANCE seul, et le predicat porte sur le DEFENSEUR

`IdunBattle.Entities.Effects.Loki.MartialExemplar_ExtraCritChanceEffect$$CreateCritChanceBonus`,
mirror de l'ordre du decompile (lu integralement) :

    EffectBonus.ForAddition(
        get_OwnerIsCaster
          & HasTrait( Target@DSLSelectors+0x60, 0x2 ),
        ConfigVar( 0x41 = extraCritChance, GetAbilityState(effect), config@+0x60 ) )

Resolutions par les mirrors du build, jamais recopiees du decompile : `AbilityVariableType`
0x41 = 65 = `extraCritChance` (**PAS** `chance` = 0x3a, la variable de `1217 TheLionsWrath` -- les
DEUX actives du meme boss lisent DEUX variables voisines, et l'ordinal seul ne l'aurait pas dit) ;
`UnitTrait` 0x2 = 2 = `Summon`.

⚠ **LE PREDICAT LIT LE TRAIT DE LA CIBLE, pas du porteur** -- c'est le SEUL noeud crit du depot
dans ce cas, et c'est ce qui a exige d'ajouter `tgt_traits` au substrat du canal
(`runner/operations/damage.py::_crit_board`, pendant exact d'`att_traits`, meme source
`entity_trait_names`). Tri-etat : cle absente = trait NON MESURE => FAUX, jamais permissif.

`get_OwnerIsCaster` = le PORTEUR de l'effet est l'ATTAQUANT du coup (le Lion se buffe lui-meme).

`extraCritChance` du gameconfig 1216 = **10 a tous les niveaux** (65 entrees), et `nrOfHits = 6` :
le cast gagne donc +10 points de chance de crit **sur chaque coup porte a un SUMMON**, et RIEN
contre une unite ordinaire. `extraCritChance` est HORS `variablesAffectedByRarityBonus`
(`["minDmg", "maxDmg", "minDmg_2", "maxDmg_2"]`) -> aucun scaling de rarete ; `ability_var`
applique cette regle config-driven.

⚠ **UN SEUL canal** : le build ne porte que `$$CreateCritChanceBonus` et `$$.ctor` pour cette
classe -- **aucun** `CreateCritDamageBonus`, **aucun** `CreateRemoveEffectTrigger`. L'effet decide
donc SI le coup crite (`IdunBattle.Core.Services.DamagePrediction$$RollCritical` =
`clamp(GetStat(9) + somme, 0, 100)`), jamais de COMBIEN ; et son retrait est porte par la DUREE
(1 tour), pas par un trigger.
"""
from __future__ import annotations

from collections.abc import Mapping

from ..base import BaseEffect, has_trait, owner_is_caster
from ..magnitude import ability_var
from ...traits.unit_trait import UnitTrait

_ABILITY_ID = "MartialExemplar"    # ActiveAbilityType 0x4c0 = 1216 (active, darkaBossLion)


class MartialExemplarExtraCritChanceEffect(BaseEffect):
    """`MartialExemplar_ExtraCritChance` (0x5f0 = 1520) -- buff que le Lion pose sur LUI-MEME au
    cast de `1216 MartialExemplar` : chaque coup porte a une cible portant le trait
    `UnitTrait.Summon` gagne +`extraCritChance` (= 10) points de chance de crit."""

    def _target_is_summon(self, att_ctx: "Mapping | None" = None) -> bool:
        """`HasTrait( Target@DSLSelectors+0x60, 0x2 = UnitTrait.Summon )`.

        Substrat = `att_ctx["tgt_traits"]`, le pendant d'`att_traits` pose par le foyer unique
        `AttackDamageOperation._crit_board` (traits d'ENTITE, pas le kit gameconfig -- #264).
        Tri-etat : cle absente ou `None` = trait NON MESURE => FAUX, jamais permissif (meme
        discipline qu'`owner_is_caster`, dont l'identite non prouvee rend FAUX)."""
        tt = (att_ctx or {}).get("tgt_traits")
        return tt is not None and has_trait(tt, UnitTrait.Summon)

    def create_effect_crit_chance_bonus_for_attack(self, att_ctx: "Mapping | None" = None) -> "int | None":
        """MIRROR de `IdunBattle.Entities.Effects.Loki.MartialExemplar_ExtraCritChanceEffect$$
        CreateCritChanceBonus` :

            EffectBonus.ForAddition(
                get_OwnerIsCaster & HasTrait(Target@+0x60, 0x2 = UnitTrait.Summon),
                ConfigVar(0x41 = extraCritChance, GetAbilityState(effect), config@+0x60) )

        Le retour est un ENTIER (pas un `EffectBonus`) : le canal natif somme des scalaires
        (`GetCritChanceBonusFromEffects` accumule `addition - subtraction`), et son consommateur est
        `clamp(GetStat(9) + somme, 0, 100)` dans `DamagePrediction$$RollCritical`.

        `GetAbilityState(effect)` indexe la config de l'ability **ACTIVE** 1216 : le niveau est
        `active_ability_level`, repli `ability_level` puis stack `level` -- l'effet est pose par une
        ACTIVE, via son `AbilityStateReference`."""
        if not owner_is_caster(att_ctx or {}):          # get_OwnerIsCaster (foyer UNIQUE, `base.py`)
            return None
        if not self._target_is_summon(att_ctx):         # HasTrait(Target@+0x60, Summon)
            return None
        lvl = self.active_ability_level
        if lvl is None:
            lvl = self.ability_level if self.ability_level is not None else self.level
        n = ability_var(_ABILITY_ID, "extraCritChance", lvl,
                        multiplier_pct=self.ability_variables_multiplier)   # ConfigVar 0x41
        return int(n) if n else None
