"""Effets de `1164 MindControl` (`genesMagus` << Magus >>, Genestealer Cults) -- #552.

TROIS effets natifs, tous poses par
`IdunBattleLogic.Entities.Abilities.Active.Loki.MindControlAbility$$ExecuteBehaviour` :

  * **1349 `MindControl_OutoingDamageReduction`** (sur la CIBLE) -- elle inflige `-dmgReduction`
    PLAT. Trigger `get_OwnerIsCaster` -> canal PORT `create_effect_damage_bonus_for_attack`.
  * **1350 `MindControl_IncomingDamageBonus`** (sur la CIBLE) -- elle subit `+extraDmgPct %`.
    Trigger `get_OwnerIsTarget` -> canal PORT `create_effect_damage_malus_for_defense`, mais
    face NATIVE **attaquant** (cf. `DEFENSE_MALUS_NATIVE_FACE` ci-dessous).
  * **1367 `MindControl_Taunter`** (sur l'ALLIE du caster qui taunte) -- MARQUEUR de bond, aucune
    contribution de degat.

⚠ **L'APPARIEMENT id <-> classe est INVERSE de l'ordre des ctors dans le binaire**, et il se lit
dans l'enum `EffectType` (mirror `entities/effect_type.py`), jamais dans l'ordre des symboles :
`MindControl_OutoingDamageReduction = 1349` (0x545) et `MindControl_IncomingDamageBonus = 1350`
(0x546), alors que `...IncomingDamageBonusEffect$$.ctor` precede
`...OutoingDamageReductionEffect$$.ctor` en adresse. (Le nom natif porte bien la faute de frappe
<< Outoing >> ; on le recopie VERBATIM.)

⚠ Les DEUX debuffs derivent DIRECTEMENT de `IdunBattle.Entities.Effects.BaseEffect` (`classes.tsv`)
et declarent `CreateEffectDamageBonusForAttack` en propre (`methods.tsv`) -- donc le slot 0x16,
celui qu'invoque `IdunBattle.Core.Services.DamageCalculations$$CalculateAttackerModifiersFor
Prediction`. Leur face NATIVE est `attacker` pour les DEUX, quel que soit leur trigger
(meme lecture que `ExemplarOfHate_TargetEffect` et `MarkerlightEffect`, cf. #437-r1-r1-r1).

⚠ AUCUN des trois n'arme `get_CanBeImmuneTo` (`data/symbols/<build>/metadata/can_be_immune_to.tsv`
ne liste, de cette famille, que `IdunBattle.Entities.Effects.TauntedEffect`) : les deux debuffs
s'appliquent AUSSI a une cible `Immune`. Le gate `Immune` de l'arbre ne couvre QUE le taunt.
"""
from __future__ import annotations

from collections.abc import Mapping

from ....services.effect_bonus import EffectBonus, for_addition, for_percent_increase
from ..base import BaseEffect
from ..magnitude import ability_var
# `ConfigVar(0xa, ...)` / `ConfigVar(0x12, ...)` -- l'accesseur natif est `ConfigVar(this,
# variableType, abilityState, config)` (le 2e parametre est DECLARE `variableType` dans
# `frida/methods.tsv`), donc un `AbilityVariableType`, PAS un `AbilityConstantType` : `10` y nomme
# `extraDmgPct` et `18` `dmgReduction`, et le gameconfig de `MindControl` porte ces deux cles sous
# `variables` (jamais sous `constants`). L'`AbilityConstantType` homonyme vaut 15 / 114 -- les
# confondre lirait la mauvaise cle SANS lever.
from ...ability_variable_type import AbilityVariableType
# `HasEffect(..., 0x1b, ...)` : `0x1b = 27 = EffectType.Taunted_OnlySpecificTargets` -- le membre
# NOMME, jamais l'ordinal du decompile (CLAUDE.md, << un ENTIER qui DESIGNE quelque chose passe par
# un ENUM >>).
from ...effect_type import EffectType

#: La cle gameconfig de l'ability 1164 (les deux `ConfigVar` s'indexent dessus).
MIND_CONTROL_ID = "MindControl"


class MindControlOutgoingDamageReductionEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.MindControl_OutoingDamageReductionEffect` (EffectType
    **0x545 = 1349**), pose sur la CIBLE du cast pour `TurnsFromRounds(2)`.

    MIRROR 1:1 de `IdunBattle.Entities.Effects.Loki.MindControl_OutoingDamageReductionEffect$$
    CreateEffectDamageBonusForAttack`, terme a terme :

        montant = Negative( ConfigVar( 0x12 = dmgReduction,
                                       GetAbilityState(effet), config@effet+0x60 ) )
        return EffectBonus.ForAddition( DSLTriggers.get_OwnerIsCaster, montant )

    => `-dmgReduction` PLAT (additif, PAS un pourcentage) sur TOUT degat que le PORTEUR inflige.
    **AUCUN autre gate** : ni `IsMeleeAttack`, ni `IsRangedAttack`, ni `IsNormalAttack` -- le
    decompile ne compose qu'`ForAddition(get_OwnerIsCaster, ...)`. Jumeau exact de
    `FightingRetreat_DamageReductionEffect` (1157), a ceci pres que celui-la ecrit son oppose par
    `Multiply(ConfigVar, MinusOne)` la ou celui-ci passe par `DSLFormulas$$Negative`.

    i2 (verbatim) : << ... that enemy unit deals -582 Damage, takes +20% Damage ... >> -- `582` est
    `dmgReduction[L65]`, jamais code en dur ici.

    MAGNITUDE : `ConfigVar` s'indexe sur l'`AbilityState` de la SOURCE (le Magus), que l'`AddEffect`
    de l'arbre bake par `scale_from_source=True` -> `active_ability_level` +
    `ability_variables_multiplier` de l'unite qui a caste. `dmgReduction` EST dans
    `variablesAffectedByRarityBonus` de 1164, donc le multiplicateur MORD."""

    def create_effect_damage_bonus_for_attack(self, is_ranged: bool | None = None,
                                              has_moved: bool | None = None,
                                              target_traits: "frozenset[str] | None" = None,
                                              is_prediction: bool = False,
                                              is_normal_attack: bool | None = True,
                                              target_armor_reduced: bool | None = None,
                                              att_ctx=None) -> EffectBonus | None:
        lvl = (self.active_ability_level if self.active_ability_level is not None
               else self.ability_level)                    # `MindControl` = ability ACTIVE du poseur
        v = ability_var(MIND_CONTROL_ID, AbilityVariableType.dmgReduction.name, lvl,
                        multiplier_pct=self.ability_variables_multiplier)
        # `Negative(...)` -> montant NEGATIF ; `owner_is_caster=True` = `get_OwnerIsCaster` (le
        # porteur est l'ATTAQUANT du coup courant).
        return for_addition(True, -int(v)) if v else None


class MindControlIncomingDamageBonusEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.MindControl_IncomingDamageBonusEffect` (EffectType
    **0x546 = 1350**), pose sur la CIBLE du cast pour `TurnsFromRounds(2)`.

    MIRROR 1:1 de `IdunBattle.Entities.Effects.Loki.MindControl_IncomingDamageBonusEffect$$
    CreateEffectDamageBonusForAttack`, terme a terme :

        montant = ConfigVar( 0xa = extraDmgPct, GetAbilityState(effet), config@effet+0x60 )
        return EffectBonus.ForPercentIncrease( DSLTriggers.get_OwnerIsTarget, montant )

    => `+extraDmgPct %` sur TOUT degat que le PORTEUR **RECOIT**. **AUCUN autre gate** (contraste
    `MarkerlightEffect`, qui ajoute `IsRangedAttack & HasFaction`) : le decompile ne compose
    qu'`ForPercentIncrease(get_OwnerIsTarget, ...)` -- donc melee ET ranged, normale ET ability.

    i2 (verbatim) : << ... takes +20% Damage ... >> -- `20` est `extraDmgPct[L65]`, lu en gameconfig.

    ⚠ `extraDmgPct` n'est PAS dans `variablesAffectedByRarityBonus` de 1164 (seul `dmgReduction`
    y est) : le multiplicateur est passe quand meme, parce que c'est la CONFIG qui decide s'il
    mord, jamais le site d'appel."""

    def create_effect_damage_malus_for_defense(self, is_melee: bool | None = None,
                                               damage_profile: str | None = None,
                                               attacker_ctx: Mapping | None = None) -> EffectBonus | None:
        lvl = (self.active_ability_level if self.active_ability_level is not None
               else self.ability_level)
        v = ability_var(MIND_CONTROL_ID, AbilityVariableType.extraDmgPct.name, lvl,
                        multiplier_pct=self.ability_variables_multiplier)
        # `owner_is_caster=False` = `get_OwnerIsTarget` (le porteur est le DEFENSEUR du coup).
        return for_percent_increase(False, int(v)) if v else None

    # #437-r1-r1-r1 -- FACE NATIVE. La classe derive DIRECTEMENT de
    # `IdunBattle.Entities.Effects.BaseEffect` (`classes.tsv`) et declare
    # `CreateEffectDamageBonusForAttack` en propre (`methods.tsv`), c'est-a-dire le slot 0x16 :
    # seul `CalculateAttackerModifiersForPrediction` l'invoque, donc le natif verse ce `+X %` dans
    # `attackModifiers` MALGRE le trigger `get_OwnerIsTarget`. Le canal du port est celui du
    # DEFENSEUR (c'est la seule liste qui balaie les effets de la cible) -> derogation explicite,
    # exactement comme `MarkerlightEffect` et `Terrifying_ExtraDefense`. CONSEQUENCE ARITHMETIQUE
    # REELLE (canal POURCENT) : le `+20 %` compose SANS `Round` intermediaire avec les autres
    # pourcentages de la face attaquante.
    DEFENSE_MALUS_NATIVE_FACE = "attacker"


class MindControlTaunterEffect(BaseEffect):
    """`Idun.Source.IdunBattle.Logic.Entities.Effects.Loki.MindControl_TaunterEffect` (EffectType
    **0x557 = 1367**) -- le MARQUEUR pose sur l'ALLIE du caster qui recupere le taunt, bonde a la
    cible mind-controlee. Il n'a QUE deux corps propres dans `methods.tsv` (`get_Range`,
    `CreateActiveCondition`) : **aucune contribution de degat, de coups, de percage ou de stat**.

    `...MindControl_TaunterEffect$$get_Range` = `System.Nullable<int>(1)` -- LU (`Nullable..ctor(
    &ret, 1)`), et deja mesure par #462-r4b-r1-r1-r1-r1-b, qui le classait << valeur mesuree, en
    attente de son porteur >>. CETTE tranche est ce porteur.

    `...MindControl_TaunterEffect$$CreateActiveCondition` (MIRROR du decompile) :

        bonded = BondedEntityFromEffect( Effect@DSLSelectors+0x38 )
        eff    = EffectFromOwner( bonded, 0x1b = 27 Taunted_OnlySpecificTargets )
        return   HasEffect( bonded, 0x1b, null, selectionType: 6 )
               & AreEqual( BondedEntityFromEffect(eff), Owner@DSLSelectors+0x30 )

    autrement dit : << la cible bondee porte ENCORE son taunt, ET ce taunt pointe vers MOI >>.
    C'est le miroir exact du bond pose par l'arbre (`AddBondEffect(27, targets=Target,
    bondedEntity=cache)` d'un cote, `AddBondEffect(1367, targets=cache, bondedEntity=Target)` de
    l'autre).

    ⚠ POURQUOI CETTE CONDITION-LA EST EVALUABLE, ALORS QUE CELLE DE `1369` NE L'EST PAS (#576-r1).
    Le contexte d'une `CreateActiveCondition` est l'`AbilityEntities` que
    `IdunBattle.Operations.RefreshEffectsOperation$$ShouldBeActive` `memset` a ZERO avant d'ecrire
    QUATRE champs : `<+0x08>` = owner, `<+0x18>` = owner, `<+0x50>` = activePlayer,
    `<+0x58>` = effectEntity. Or les selecteurs employes ICI lisent tous un champ RENSEIGNE --
    `IdunBattle.Entities.Selectors.EffectSelector$$Select` -> `ctx+0x58`,
    `IdunBattle.Entities.Selectors.OwnerSelector$$Select` -> `ctx+0x18` -- la ou
    `...TargetSelector$$Select` lit `ctx+0x10`, qui reste nul. Les deux conjoints sont donc de
    vraies lectures d'etat, pas des constantes.

    PORTEE ICI (`#552-r1`, tranche du 2026-08-10) -- les trois briques natives sont exposees par
    `runner/components.py::unit_state_for_effects`, le foyer UNIQUE du contexte (#208) :
    `owner_id` (= `Owner@+0x30`), le callable `has_effect_on` (= `HasEffect(sel, type,
    onlyActive: null, 6)`) et le callable `owned_effect_bonded_entity`
    (= `BondedEntityFromEffect(EffectFromOwner(sel, type))`). `Effect@+0x38` n'a PAS besoin d'etre
    threade : le selecteur designe l'entite-effet COURANTE, donc `BondedEntityFromEffect` de cette
    entite-la est exactement `self.bonded`, que l'instance porte deja.

    CONSEQUENCE, inchangee : `1367` ne CONTRIBUE a rien (ses deux seuls corps propres sont
    `get_Range` et `CreateActiveCondition`), donc l'ecart etait -- et l'apport est -- confine a la
    LISTE d'effets publiee et aux gates `HasEffect(1367)`."""

    # La `CreateActiveCondition` est REELLEMENT portee -> le flag capte ne fait plus foi pour
    # cette classe (`case-322`) : `EffectsState.active_effects` s'en remet a `is_active` seul.
    active_condition_ported = True

    def is_active(self, unit_state: Mapping | None = None) -> bool:
        """MIRROR terme a terme de `...MindControl_TaunterEffect$$CreateActiveCondition` (cf. la
        docstring de classe) :

            bonded = BondedEntityFromEffect( Effect@DSLSelectors+0x38 )   # == `self.bonded`
            return   HasEffect( bonded, 27 Taunted_OnlySpecificTargets, onlyActive: null, 6 )
                   & AreEqual( BondedEntityFromEffect(EffectFromOwner(bonded, 27)),
                               Owner@DSLSelectors+0x30 )

        DEGRADATIONS, toutes dans le sens << on ne masque pas a tort >> (VRAI), et chacune nommee :
          * `unit_state` absent ou prive de l'une des trois cles (face DECISION, `Scene`, appelant
            qui n'a pas de `EffectsState`) -> VRAI, comme toutes les autres conditions portees ;
          * `self.bonded is None` -> VRAI. Ce n'est PAS le verdict natif (`BondedEntityFromEffect`
            rendrait la liste vide, donc `SelectUnit` null, donc `HasEffect` faux) : c'est le
            refus de trancher sur une instance dont le canal de bond n'a pas ete seede. Le canal
            EXISTE (`decisionView` publie `bondedId`, et `AddEffectOperation` l'ecrit a la pose
            offline), mais une capture anterieure a ce champ rendrait `None` sur une instance
            parfaitement liee -- et fermer l'effet dans ce cas serait un faux negatif SILENCIEUX.
        """
        if not unit_state:
            return True
        bonded = self.bonded
        if bonded is None:
            return True                     # bond non seede -> on ne tranche pas (cf. docstring)
        has_effect_on = unit_state.get("has_effect_on")
        bonded_of = unit_state.get("owned_effect_bonded_entity")
        owner = unit_state.get("owner_id")
        if has_effect_on is None or bonded_of is None or owner is None:
            return True                     # contexte non threade -> degradation VRAIE
        taunt = int(EffectType.Taunted_OnlySpecificTargets)
        if not has_effect_on(int(bonded), taunt):          # 1er conjoint : HasEffect(bonded, 27)
            return False
        back = bonded_of(int(bonded), taunt)               # 2d conjoint : AreEqual(..., Owner)
        return back is not None and int(back) == int(owner)
