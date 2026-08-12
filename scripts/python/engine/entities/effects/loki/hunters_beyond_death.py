"""`HuntersBeyondDeath` (`TriggeredAbilityType` 1162) -- le passif de `spaceHound` << Tjark >>, ses
TROIS effets. #952

RECENSEMENT PAR LE BLOC `methodPointers`, pas par grep de nom (la table `frida/methods.tsv` ne
publie que les corps PROPRES : 5 lignes sur 14 slots pour cette famille). Les quatre blocs, lus
dans le tableau de pointeurs du PE et resolus un a un :

    IdunBattleLogic.Entities.Abilities.Triggered.Loki.HuntersBeyondDeathAbility   3 slots, 1 propre
        CreateTrigger        DEDUPLIQUE  (corps = `...Active.Loki.SummaryExecutionAddBaseEffectAbility$$CreateTrigger`)
        CreateBehaviour      PROPRE
        .ctor                DEDUPLIQUE  (corps = `UnityEngine.Scripting.RequiredByNativeCodeAttribute$$.ctor`)

    IdunBattle.Entities.Effects.Loki.HuntersBeyondDeath_ExtraDamageEffect         4 slots, 1 propre
        .ctor                DEDUPLIQUE  (partage avec les DEUX autres effets du kit)
        CreateActiveCondition DEDUPLIQUE (corps = `...WisdomOfTheAncients_DamageReductionEffect$$CreateActiveCondition`)
        CreateTargetSelector  DEDUPLIQUE (corps = `...WhisperingWebEffect$$CreateTargetSelector`)
        CreateEffectDamageBonusForAttack  PROPRE

    IdunBattle.Entities.Effects.Loki.HuntersBeyondDeathEffect                     4 slots, 2 propres
        .ctor                 DEDUPLIQUE
        CreateTargetSelector  PROPRE
        CreateActiveCondition DEDUPLIQUE (corps = `...WayOfTheShortBlade_AdditionalAttackMarkerEffect$$CreateActiveCondition`)
        CreateEffectDamageMalusForDefense PROPRE

    IdunBattle.Entities.Effects.Loki.HuntersBeyondDeathPsykerSuppressionEffect    3 slots, 1 propre
        .ctor                 DEDUPLIQUE
        CreateActiveCondition DEDUPLIQUE (meme corps que celui d'`_ExtraDamage`)
        CreateTargetSelector  PROPRE      (deja porte -- `entities/effect_targets.py`, #418-r1)

Les DEUX `CreateActiveCondition` rendent une CONSTANTE VRAIE : `<DSLTriggers+0x70>` pour
`_ExtraDamage` et `PsykerSuppression`, `<DSLTriggers+0x40>` pour `HuntersBeyondDeathEffect`. Ce
sont DEUX instances de la MEME classe (`IdunBattle.Entities.Triggers.YesTrigger`), construites cote
a cote par `IdunBattleLogic.Entities.DSLTriggers$$.ctor` avec le MEME ctor vide -- et la preuve que
cette classe est bien le `YesTrigger` est dans le meme ctor : `<+0x48>` y est
`op_LogicalNot(new <meme classe>())`, or `<DSLTriggers>+0x48` est deja lu comme la constante FAUSSE
(`runner/abilities/base.py`). => les trois effets sont TOUJOURS ACTIFS ; aucun
`active_condition_ported`.

## L'ARBRE DE POSE

`HuntersBeyondDeathAbility$$CreateTrigger` = `<DSLTriggers+0x30>`, le trigger d'INIT partage et mis
en cache par `IdunBattleLogic.Entities.DSLTriggers$$InitializeShared` :
`On(0x21 = EventTriggerType.AbilityInit) & <YesTrigger> & get_OwnerIsActor`. Ce n'est donc PAS un
vecteur de combat -> registre `ABILITY_INIT_OWNER_EFFECTS`, jamais `ABILITY_TRIGGERS` (meme
arbitrage que `EnmityForTheUnworthy`, #948).

`HuntersBeyondDeathAbility$$CreateBehaviour` (MIRROR, feuille par feuille) :

      AddEffect(0x4a6 = 1190 HuntersBeyondDeath,             AbilityStateReference, source = Owner@+0x30, targets = Owner@+0x30, options = default)
    + AddEffect(0x494 = 1172 HuntersBeyondDeath_ExtraDamage, AbilityStateReference, source = Owner@+0x30, targets = Owner@+0x30, options = default)
    + AddEffect(0x4a7 = 1191 HuntersBeyondDeathPsykerSuppression, ...)

-- combines par `IdunBattle.DSL.AbilityBehaviour$$op_Addition` (et non `op_BitwiseAnd`), dans CET
ordre. La surcharge d'`AddEffect` est celle a `Nullable<AddEffectBehaviourOptions>` (0x28 octets mis
a ZERO juste avant l'appel => options par defaut, aucune duree => PERMANENT). Les trois ids sont des
`EffectType` : `TriggeredAbilityType` d'ordinal 1190/1172/1191 nomme `BlisteringAssault` /
`BattleFocus` / `HyperAggression`, sans aucun rapport -- l'enum se QUALIFIE.

## LES DEUX MAGNITUDES, ET LEUR CONFIG

Les deux `ConfigVar` visent la surcharge
`DSLFormulas$$ConfigVar(variableType, abilityState : IAbilityStateSelector, config)` (adresse de la
cible du `call` LUE, pas devinee) : le 1er argument est un `AbilityVariableType`, le 3e la
`AbilityConfiguration` de l'effet lui-meme (`<effet>+0x60`).

  * `_ExtraDamageEffect`  -> `AbilityVariableType.extraDmg` (8)
  * `HuntersBeyondDeathEffect` -> `AbilityVariableType.dmgReduction` (0x12)

Les DEUX sont dans `variablesAffectedByRarityBonus` de la config `HuntersBeyondDeath` (lu au
gameconfig), donc scalees par le multiplicateur de rarete du porteur. Elles portent d'ailleurs le
MEME tableau de valeurs (8..582 sur 65 niveaux) : un test qui ne verifierait QUE le chiffre ne
saurait pas distinguer les deux faces -- d'ou les contre-epreuves par GATE de
`test_952_hunters_beyond_death_offline.py`.

i2 (`Abilities/HuntersBeyondDeath_CurrentLevelDescription`) : << Deals +{extraDmg} Damage against
Psykers, and enemy Psykers within 2 hexes deal -{dmgReduction} Damage. >>

ASCII only (console cp1252).
"""
from __future__ import annotations

from collections.abc import Mapping

from ....services.effect_bonus import EffectBonus, for_addition, for_subtraction
from ...ability_variable_type import AbilityVariableType
from ...traits.unit_trait import UnitTrait
from ..base import BaseEffect, min_distance_at_most
from ..magnitude import ability_var

#: Cle gameconfig du PASSIF -- `TriggeredAbilityType.HuntersBeyondDeath` (0x48a = 1162). Les TROIS
#: effets s'y indexent (`ConfigVar(..., config@+0x60)` = la config de l'ability qui les a poses).
_ABILITY_ID = "HuntersBeyondDeath"

#: `HasTrait(<sel>, 0x3ea)` / `UnitsWithTrait(..., 0x3ea, 3)` -- le NOM tel que la capture le publie
#: (`StatsComponent.ctx.traits` cote runner, `Scene.ctx_by_id[...].traits` cote decision).
_TRAIT_PSYKER = UnitTrait.Psyker.name

#: `Direct(2)` du gate de distance, ET le `range` du `CreateTargetSelector` de 1190. Le natif ecrit
#: le litteral DEUX fois, dans deux noeuds independants -- on le nomme une fois.
_RANGE = 2


class HuntersBeyondDeathExtraDamageEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.HuntersBeyondDeath_ExtraDamageEffect`
    (`EffectType.HuntersBeyondDeath_ExtraDamage` = 0x494 = 1172) -- la face ATTAQUANT du passif :
    Tjark inflige `+extraDmg[level]` PLAT a toute cible qui porte le trait `Psyker`.

    `$$CreateEffectDamageBonusForAttack`, MIRROR du decompile :

        EffectBonus.ForAddition(
              get_OwnerIsCaster
            & HasTrait(Target@DSLSelectors+0x60, 0x3ea = UnitTrait.Psyker),
              ConfigVar(8 = extraDmg, GetAbilityState(effet), config@+0x60) )

    ⚠ SON `CreateTargetSelector` EST `<DSLSelectors+0x30>` = **Owner**, corps DEDUPLIQUE avec
    `WhisperingWebEffect$$CreateTargetSelector`. C'est donc un effet SELF, pas une aura : la seule
    voie du port est `create_effect_damage_bonus_for_attack` (l'effet est porte par l'attaquant).
    Le confondre avec son voisin 1190 -- qui, LUI, a un vrai selecteur d'aura -- aurait branche
    cette face sur `create_aura_attack_damage_bonus_for_ally`, ou l'agregateur EXCLUT le porteur :
    le bonus n'aurait JAMAIS ete applique a Tjark, c'est-a-dire jamais.

    AUCUN gate de nature de coup (`IsMeleeAttack` / `IsRangedAttack` absents) ni de profil : le
    bonus vaut sur l'attaque normale MELEE de Tjark comme sur sa relique a distance."""

    def create_effect_damage_bonus_for_attack(self, is_ranged: "bool | None" = None,
                                              has_moved: "bool | None" = None,
                                              target_traits: "frozenset[str] | None" = None,
                                              is_prediction: bool = False,
                                              is_normal_attack: "bool | None" = True,
                                              target_armor_reduced: "bool | None" = None,
                                              att_ctx=None) -> EffectBonus | None:
        # `HasTrait(Target@+0x60, Psyker)` : traits de la CIBLE du coup. Cle absente = non mesure ->
        # gate FERME (jamais permissif), meme convention que `owner_is_caster`.
        if not target_traits or _TRAIT_PSYKER not in target_traits:
            return None
        # `ConfigVar(..., GetAbilityState(effet), ...)` : sans `AbilityState`, le natif n'a pas de
        # niveau a indexer -> aucune contribution.
        if self.ability_level is None:
            return None
        amt = ability_var(_ABILITY_ID, AbilityVariableType.extraDmg.name, self.ability_level,
                          multiplier_pct=self.ability_variables_multiplier)
        # `get_OwnerIsCaster` est rendu PAR LE CANAL : `create_effect_damage_bonus_for_attack` n'est
        # interroge que sur les effets de l'ATTAQUANT (`_attacker_effect_bonuses`), donc
        # `Owner == Caster` par construction -- meme arbitrage que les autres effets SELF de
        # `extra_damage.py`.
        return for_addition(True, int(amt)) if amt else None


class HuntersBeyondDeathEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.HuntersBeyondDeathEffect`
    (`EffectType.HuntersBeyondDeath` = 0x4a6 = 1190) -- la face DEFENSEUR : un Psyker ENNEMI a
    <= 2 hexes de Tjark inflige `dmgReduction[level]` de MOINS aux unites du camp de Tjark.

    i2 (`UnitEffects/HuntersBeyondDeath_Description`) : << Psykers within 2 Hexes of Tjark do
    {dmgReduction} less Damage. >>

    `$$CreateEffectDamageMalusForDefense`, MIRROR du decompile (toutes les surcharges tranchees par
    l'ADRESSE REELLE de la cible du `call`) :

        src = EffectSource(Effect@DSLSelectors+0x38)                       # le POSEUR = Tjark
        EffectBonus.ForSubtraction(
              NOT AreFriends(src, Caster@+0x48, comparisonType = 0, anyEntity = false)
            &     AreFriends(src, Target@+0x60, comparisonType = 0, anyEntity = false)
            &     HasTrait(Caster@+0x48, 0x3ea = UnitTrait.Psyker)
            & NOT AmountIsGreater(MinDistance(src, Caster@+0x48), Direct(2)),
              ConfigVar(0x12 = dmgReduction, GetAbilityState(effet), config@+0x60) )

    `$$CreateTargetSelector` (corps PROPRE) :

        UnitsWithTrait( SurroundingEnemies(unit = Owner@+0x30, unitTile = <+0x50>, range = 2,
                                           unique = 1, unitSelectionType = 3),
                        0x3ea = Psyker, 3 )

    ⚠ CE SELECTEUR N'EST PAS LE GATE, et les confondre serait faux. Il MATERIALISE la liste
    `EffectComponent.Targets` (ce que l'UI affiche, et ce que lit `IsEffectTarget`) ; la condition
    d'application, elle, RE-DERIVE la geometrie par `MinDistance(src, Caster) <= 2`. Les deux ne
    portent pas sur le meme sujet : le selecteur vise les Psykers ennemis, le gate vise l'ATTAQUANT
    du coup courant. Le port ne consomme donc PAS ce selecteur (aucun lecteur d'`IsEffectTarget`
    pour 1190) -- il est ecrit ici, pas inscrit dans `EFFECT_TARGET_SELECTORS` (pas de port
    speculatif).

    ⚠ `NOT AmountIsGreater(d, 2)` est bien `d <= 2` : le corps d'
    `IdunBattle.Entities.Conditions.AmountIsGreaterAbilityTrigger$$ShouldTrigger` finit sur
    `return minAmount < amount` (comparaison STRICTE), et l'adresse appelee (0x...ed53f0) n'est
    aucune des deux surcharges d'`AmountIsEqualOrGreater` -- verifie contre le piege ICF nomme par
    `battle_query.py`.

    ## DEUX FOYERS DISJOINTS, parce que `IsFriend(x, x)` est VRAI

    `AreFriends(src, Target)` est VRAI quand la cible EST Tjark (`IdunBattle.Entities.UnitExtensions
    $$IsFriend` compare deux index de joueur sans ecarter l'egalite) : le malus vaut donc AUSSI
    quand Tjark lui-meme encaisse. Or l'agregateur d'aura defense (`aura_defense_damage_malus_from_
    units`) EXCLUT le porteur (`uid == tgt_id -> continue`) sur ses DEUX call-sites. D'ou le meme
    decoupage que `PsychicStalk_FriendlyChaosExtraDamage` / `DestroyTheWitch_ExtraDamage`, mais sur
    l'axe DEFENSE :

      * `create_effect_damage_malus_for_defense`      -> la patte SELF (Tjark est le defenseur) ;
      * `create_aura_defense_damage_malus_for_ally`   -> ses ALLIES (defenseur != Tjark).

    Ni trou, ni double-compte : les deux boucles ont des univers de porteurs complementaires.

    ## FACE NATIVE

    Le slot est `CreateEffectDamageMalusForDefense` (0x1a) et la fabrique est `ForSubtraction` ->
    `flat_reductions` de l'accumulateur DEFENSEUR, donc les defauts `DEFENSE_MALUS_NATIVE_FACE` /
    `AURA_DEFENSE_MALUS_NATIVE_FACE` (= "defender") conviennent : rien a surcharger."""

    def _amount(self) -> "int | None":
        """`ConfigVar(0x12 = dmgReduction, GetAbilityState(effet), config@+0x60)`."""
        if self.ability_level is None:
            return None
        amt = ability_var(_ABILITY_ID, AbilityVariableType.dmgReduction.name, self.ability_level,
                          multiplier_pct=self.ability_variables_multiplier)
        return int(amt) if amt else None

    @staticmethod
    def _attacker_is_hostile_psyker_in_range(src_team, src_pos, att_team, att_pos,
                                             att_traits) -> bool:
        """Les TROIS conjoints du gate qui portent sur l'ATTAQUANT, foyer partage par les deux
        pattes (SELF et AURA) -- le natif n'a qu'un seul trigger, le port ne doit pas le forker.

            NOT AreFriends(src, Caster) & HasTrait(Caster, Psyker)
                                        & NOT AmountIsGreater(MinDistance(src, Caster), Direct(2))

        Toute donnee manquante FERME le gate (jamais permissif) -- meme convention que
        `owner_is_caster` / `is_at_range`."""
        if src_team is None or att_team is None or src_team == att_team:
            return False                                   # NOT AreFriends(src, Caster)
        if not att_traits or _TRAIT_PSYKER not in att_traits:
            return False                                   # HasTrait(Caster, Psyker)
        return min_distance_at_most(src_pos, att_pos, _RANGE)

    def create_effect_damage_malus_for_defense(self, is_melee: "bool | None" = None,
                                               damage_profile: "str | None" = None,
                                               attacker_ctx: Mapping | None = None
                                               ) -> EffectBonus | None:
        """Patte SELF : le porteur (Tjark) EST le defenseur du coup.

        `AreFriends(src, Target)` est alors VRAI par construction (src == Target == Tjark), et
        `owner_pos` est la position de ce meme porteur -- c'est la cle que ce canal thread pour
        `Owner@DSLSelectors+0x30`, au meme titre qu'`is_turn_of_owner`.

        ⚠ Les trois cles lues ici (`owner_pos`, `att_pos`, `traits`) etaient DEJA threadees par
        `TerrorsLament_DamageReduction` (#950) sous ces MEMES noms -- ce port n'en a ajoute aucune
        sur ce canal. Deux gates geometriques independants qui convergent sur le meme couple : ce
        n'est pas une coincidence, c'est le contexte natif `AbilityEntities` que les deux
        mirroirent."""
        c = attacker_ctx or {}
        if not self._attacker_is_hostile_psyker_in_range(
                c.get("owner_team"), c.get("owner_pos"), c.get("team"), c.get("att_pos"),
                c.get("traits")):
            return None
        amt = self._amount()
        return for_subtraction(True, amt) if amt else None

    def create_aura_defense_damage_malus_for_ally(self, ctx: Mapping | None = None
                                                  ) -> EffectBonus | None:
        """Patte AURA : le defenseur est un ALLIE de Tjark, distinct de lui.

        `AreFriends(src, Target@+0x60)` = `owner_team == tgt_team` (le porteur EST la source :
        `AddEffect(..., source = Owner, targets = Owner)`)."""
        c = ctx or {}
        if c.get("owner_team") is None or c.get("tgt_team") is None \
                or c.get("owner_team") != c.get("tgt_team"):
            return None                                    # AreFriends(src, Target)
        if not self._attacker_is_hostile_psyker_in_range(
                c.get("owner_team"), c.get("owner_pos"), c.get("att_team"), c.get("att_pos"),
                c.get("att_traits")):
            return None
        amt = self._amount()
        return for_subtraction(True, amt) if amt else None


class HuntersBeyondDeathPsykerSuppressionEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.HuntersBeyondDeathPsykerSuppressionEffect`
    (`EffectType.HuntersBeyondDeathPsykerSuppression` = 0x4a7 = 1191).

    i2 : << Their normal ranged attack will not hit an additional unit. >>

    AUCUN canal de DEGAT : le bloc `methodPointers` de la classe ne declare que `.ctor`,
    `CreateActiveCondition` (constante VRAIE) et `CreateTargetSelector`. Sa seule consequence de jeu
    passe par la LISTE DE CIBLES, lue par le gate `IsPsykerAttackSuppressed` du splash Psyker
    (`IdunBattleLogic.Entities.Abilities.Active.Loki.PsykerExtraAttackAbility$$
    IsPsykerAttackSuppressed` = `IsEffectTarget(Caster@+0x48, 0x4a7) | IsEffectTarget(Target@+0x60,
    0x5fd)`), deja porte par `runner/operations/triggers/loki/psyker.py` via la geometrie de
    `entities/effect_targets.py::_surrounding_enemy_psykers_r2` (#418-r1).

    La classe existe donc pour que l'effet soit MATERIALISE par `EffectFactory.create` sous son
    identite, et non en `BaseEffect` anonyme : c'est ce qui rend le passif comptable par le canal
    OWNER-EFFECT de l'audit (`ABILITY_INIT_OWNER_EFFECTS` exige >= 1 effet dans `EFFECT_CLASSES`) et
    ce qui documente, au bon endroit, que ses deux autres faces sont DEDUPLIQUEES et lues.

    ⚠ Ne RIEN surcharger ici est le mirror exact : ajouter un canal de degat inventerait une face
    que le natif ne declare pas."""
