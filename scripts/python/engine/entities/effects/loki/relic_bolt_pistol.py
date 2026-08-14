"""`RelicBoltPistol` -- la relique `R_Crit_RelicBoltPistol` (Mythic, `items[*].abilityId`), et ses
DEUX effets porteurs, un par NATURE de coup. #910.

i2 : « The relic bearer gains +10% pierce ratio with melee attacks and deals +877 Crit Damage with
ranged attacks. These bonuses are doubled against Chaos or Xenos enemies. »

## IDENTITE -- TROIS enums, et deux collisions d'ordinal sur le chemin

    TriggeredAbilityType  0x5bb = 1467 = RelicBoltPistol                     <- la CONFIG
    EffectType            0x5b1 = 1457 = RelicBoltPistol_ExtraPierce         <- effet MELEE
    EffectType            0x5b2 = 1458 = RelicBoltPistol_ExtraCritDamage     <- effet RANGED

    TriggeredAbilityType  0x5b1 = 1457 = KardiocoreGalvanus                  <- une AUTRE relique
    TriggeredAbilityType  0x5b2 = 1458 = PhoenixGem                          <- une AUTRE relique
    EffectType            0x5bb = 1467 = SelfRepairMechanism                 <- rien a voir

Les trois qualifications sont LUES, jamais deduites de la voie : les deux `EffectType` sont les
litteraux passes a `DSLBehaviors$$AddEffect` (2e argument, type `IdunBattle.Entities.Enum.EffectType`
dans `frida/methods.tsv`), et le `1467` est le litteral du `.ctor` de l'effet, RELU OCTET A OCTET ::

    ba bb 05 00 00                    ; mov  edx, 0x5bb = 1467
    e8 <rel32>                        ; call IdunBattle.Core.AbilityOrEffect$$op_Implicit
                                      ;   surcharge tranchee par son ADRESSE : son corps appelle
                                      ;   `AbilityOrEffect$$set_TriggeredAbility` (les surcharges
                                      ;   sont homonymes, elles ne se distinguent pas au nom)
    41 b0 01                          ; mov  r8b, 1  = hasAutomaticActivation
    e8 <rel32>                        ; call IdunBattle.Entities.Effects.BaseEffect$$.ctor

=> la config lue est celle de la TRIGGERED `RelicBoltPistol`, dont les deux variables sont
`extraPierceRatio` (`[5..10]`) et `extraCritDmg` (`[590..877]`). Ce meme `.ctor` est PARTAGE par les
deux classes d'effet (`RelicBoltPistol_ExtraCritDamageEffect$$.ctor` est absent des tables : IL2CPP
deduplique les corps identiques) -- les deux lisent donc la MEME config.

## POSE -- deux owner-effects PERMANENTS, a l'init de l'ability

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.RelicBoltPistolAbility$$CreateBehaviour`
(mirror ; les deux `AddEffect` sont combines par `IdunBattle.DSL.AbilityBehaviour$$op_BitwiseAnd`) ::

    AddEffect( 0x5b1 = RelicBoltPistol_ExtraPierce,      AbilityStateReference,
               source = Owner@DSLSelectors+0x30, targets = Owner@DSLSelectors+0x30,
               options = <zeroe> )
    &
    AddEffect( 0x5b2 = RelicBoltPistol_ExtraCritDamage,  AbilityStateReference,
               source = Owner@DSLSelectors+0x30, targets = Owner@DSLSelectors+0x30,
               options = <zeroe> )

La surcharge d'`AddEffect` est tranchee par l'ADRESSE de son call (`e8` relu a l'assembleur, cible
`IdunBattleLogic.Entities.DSLBehaviors$$AddEffect` a 6 parametres) : son 6e parametre est
`options: System.Nullable<IdunBattle.Entities.Behaviours.AddEffectBehaviourOptions>`, PAS une duree
-- il n'y a donc AUCUNE duree a poser, les deux effets sont PERMANENTS.

**source == targets == Owner**, et c'est ce qui rend le niveau exact : l'`AbilityState` bake est
celui de la relique SUR SON PORTEUR, c'est-a-dire l'etat TERTIAIRE quand elle est EQUIPEE
(`BC.Units[].TertiaryAbilityLevel`, cf. `case-237`). Le port le relit par le foyer UNIQUE
`runner/operations/triggers/base.py::triggered_ability_state` (#357), le meme que
`AmuletOfTheVoidwyrm_CritDamageReduction`.

Aucun `If(...)` n'enveloppe les deux `AddEffect` (contrairement au corps de BASE
`AOwnerEffectTriggeredAbility$$CreateBehaviour`) : la pose est INCONDITIONNELLE, et aucune des deux
classes ne porte de `CreateActiveCondition` (`ghidra/functions.tsv` ne connait pour elles que
`.ctor`, `CreatePiercingBonusForAttack` et `CreateCritDamageBonus`). Les deux instances sont donc
TOUJOURS actives -- donc TOUJOURS publiees par le canal `decisionView.effects` (ACTIF-ONLY, ground
truth #100), ce qui rend inutile une entree `ABILITY_INIT_OWNER_EFFECTS` (meme arbitrage que
`WireweaveNet` / `StructuralAnalyser` : le seed lirait les passives du KIT gameconfig, ou une
relique EQUIPEE ne figure de toute facon pas).

## LES DEUX CANAUX -- meme corps, a la variable et a la NATURE du coup pres

`IdunBattle.Entities.Effects.Loki.RelicBoltPistol_ExtraPierceEffect$$CreatePiercingBonusForAttack`
et `IdunBattle.Entities.Effects.Loki.RelicBoltPistol_ExtraCritDamageEffect$$CreateCritDamageBonus`
sont le MEME code -- relu des deux cotes, pas suppose ::

    traitOr = HasTrait(Target@DSLSelectors+0x60, 0x3ee = 1006 Xenos)
              | HasTrait(Target@DSLSelectors+0x60, 0x7ea = 2026 Chaos)
    cv      = ConfigVar(<0x3f extraPierceRatio | 0x42 extraCritDmg>, GetAbilityState(effect),
                        config@+0x60)
    amount  = If( traitOr, Multiply(cv, <DSLFormulas+0x28>), cv )
    return    EffectBonus.ForAddition( get_OwnerIsCaster & <IsMeleeAttack | IsRangedAttack>, amount )

Trois lectures qui NE se devinent pas :

1. **`<DSLFormulas+0x28>` = `Direct(2)`**, LU dans `IdunBattleLogic.Entities.DSLFormulas$$.ctor`, qui
   alloue cinq constantes dans l'ordre `+0x18 = Direct(0)`, `+0x20 = Direct(1)`, `+0x28 = Direct(2)`,
   `+0x30 = Direct(100)`, `+0x38 = Direct(-1)`. C'est le « doubled » de l'i2, et il est ici une
   MAGNITUDE (branche d'un `If`), pas un gate : sans le trait, le bonus vaut `cv`, il ne disparait
   PAS. Confondre les deux -- gate au lieu de multiplicateur -- annulerait le bonus contre tout
   Imperial, un ecart PERMISSIF pour le defenseur et SILENCIEUX.
2. **`<DSLSelectors+0x60>` = `Target`**, LU sans passer par aucune citation heritee :
   `IdunBattleLogic.Entities.DSLTriggers$$get_OwnerIsTarget` = `AreEqual(<+0x30>, <+0x60>)` et
   `$$get_OwnerIsCaster` = `AreEqual(<+0x30>, <+0x48>)` -- le membre COMMUN aux deux est `Owner`,
   donc `+0x60` est la CIBLE et `+0x48` le CASTER.
3. **`Xenos`/`Chaos` sont des pseudo-traits de GRANDE-ALLIANCE**, absents de tout `traits`
   gameconfig (mesure : 0 unite sur les trois groupes en porte un). Ils viennent de
   `idun.Idun.Source.Shared.GrandAlliance$$GetTrait` et la couche meta les injecte dans la
   `BattleConfiguration` -- d'ou la lecture par `entity_trait_names` (substrat d'ENTITE, #264) et
   JAMAIS par `gameconfig.unit().traits`, qui rendrait le gate MORT sur toutes les cibles.

Les deux canaux natifs sont DISTINCTS et n'ont rien de symetrique : le premier alimente
`IdunBattle.Core.Services.DamagePrediction$$GetAttackPiercingDamageRatio` (terme additif du ratio de
percage, AVANT le `Min(100, ...)`), le second `$$GetCritDamageBonusFromEffects` puis
`$$CalculateCriticalDamage` (`max(0, GetStat(10) + somme)`). Un coup MELEE ne touche que le premier,
un coup RANGED que le second : l'ability ne double jamais son effet sur un meme coup.
"""
from __future__ import annotations

from collections.abc import Mapping

from ..base import BaseEffect
from ..magnitude import ability_var
from ...traits.unit_trait import UnitTrait, has_any_trait
from .. import ctx_keys as _ctx_keys      # #1042-r5 : foyer UNIQUE des chaines de cle de ctx

#: `TriggeredAbilityType` 0x5bb = 1467 -- la CONFIG lue par les DEUX effets (`.ctor` partage).
_ABILITY_ID = "RelicBoltPistol"
#: `AbilityVariableType` 0x3f = 63 -- la variable du canal PERCAGE.
_VAR_PIERCE = "extraPierceRatio"
#: `AbilityVariableType` 0x42 = 66 -- la variable du canal CRIT-DEGAT.
_VAR_CRIT_DMG = "extraCritDmg"
#: `<DSLFormulas+0x28>` = `Direct(2)`, LU dans `IdunBattleLogic.Entities.DSLFormulas$$.ctor`.
_DOUBLE = 2
#: `HasTrait(Target@+0x60, 0x3ee) | HasTrait(Target@+0x60, 0x7ea)` -- pseudo-traits de GRANDE-ALLIANCE.
_QUALIFYING_TRAITS = (UnitTrait.Xenos, UnitTrait.Chaos)
#: callable `(owner_id, ability_name) -> (level, multiplier)` -- mirror de `GetAbilityState(effect)`,
#: pose par `_crit_board` (canal CRIT) et `ability_pierce_effect_bonus` (canal PERCAGE).
CTX_ABILITY_STATE_OF = _ctx_keys.CTX_TERTIARY_ABILITY_STATE_OF


def _owner_is_caster(ctx: "Mapping | None") -> bool:
    """`IdunBattleLogic.Entities.DSLTriggers$$get_OwnerIsCaster` = `AreEqual(Owner@DSLSelectors+0x30,
    Caster@DSLSelectors+0x48)`.

    Les deux agregateurs posent `owner_id` PAR PORTEUR (mirror de l'ecriture `AbilityEntities+0x18`)
    et `att_id` pour l'attaquant du coup. Identite NON PROUVEE (une des deux cles absente) => noeud
    FAUX, jamais permissif."""
    c = ctx or {}
    oid, aid = c.get("owner_id"), c.get("att_id")
    return oid is not None and aid is not None and oid == aid


def _ability_state(effect: BaseEffect, ctx: "Mapping | None") -> tuple:
    """`IdunBattle.Entities.Effects.BaseEffect$$GetAbilityState` -> `(level, multiplier)` de
    l'`AbilityState` bake a la pose.

    `RelicBoltPistolAbility$$CreateBehaviour` bake `AbilityStateReference` et pose l'effet SUR
    l'Owner : source == porteur, donc le couple se relit sur le porteur (`owner_id`). C'est l'etat
    TERTIAIRE quand la relique est EQUIPEE, l'etat PASSIF quand elle est cablee au kit d'un npc --
    exactement l'arbitrage du foyer UNIQUE `triggered_ability_state` (#357).

    Callable absent (contexte sans `state` : probe, test offline) -> repli sur les niveaux que
    l'instance porte deja, comme toutes les autres classes d'effet. Sans ce discriminant, une relique
    de niveau 3 lirait le niveau des PASSIFS du porteur (50 en runner normalise) donc le dernier
    palier -- un ecart SILENCIEUX de magnitude (877 au lieu de 654)."""
    c = ctx or {}
    fn, oid = c.get(CTX_ABILITY_STATE_OF), c.get("owner_id")
    if fn is not None and oid is not None:
        lvl, mult = fn(oid, _ABILITY_ID)
        if lvl is not None:
            return int(lvl), int(mult if mult is not None else 100)
    lvl = effect.ability_level if effect.ability_level is not None else effect.level
    return lvl, int(effect.ability_variables_multiplier or 100)


def _amount(effect: BaseEffect, var_key: str, target_traits, ctx: "Mapping | None") -> "int | None":
    """`If( HasTrait(Target, Xenos) | HasTrait(Target, Chaos),
            Multiply(ConfigVar(<var>), <DSLFormulas+0x28> = Direct(2)),
            ConfigVar(<var>) )` -- la MAGNITUDE commune aux deux canaux.

    Les deux corps natifs sont IDENTIQUES a l'`AbilityVariableType` pres (`0x3f` vs `0x42`), d'ou un
    seul corps ici -- meme arbitrage qu'`EmpyricAmbushEffect._bonus`.

    TRI-ETAT sur `target_traits` : `None` = cible NON MESUREE. Le noeud `If` natif, lui, tranche
    toujours (une entite a ou n'a pas le trait) ; offline, choisir une branche serait inventer. On
    prend alors la branche NON DOUBLEE -- c'est la borne BASSE, celle qui ne peut pas sur-estimer le
    bonus, et le call-site le declare."""
    lvl, mult = _ability_state(effect, ctx)                      # GetAbilityState(effect)
    cv = ability_var(_ABILITY_ID, var_key, lvl, multiplier_pct=mult)     # ConfigVar(<var>)
    if not cv:
        return None
    if target_traits is not None and has_any_trait(target_traits, _QUALIFYING_TRAITS):
        return int(cv) * _DOUBLE                                 # Multiply(cv, Direct(2))
    return int(cv)


class RelicBoltPistolExtraPierceEffect(BaseEffect):
    """`RelicBoltPistol_ExtraPierce` (0x5b1 = 1457) -- owner-effect PERMANENT de la relique
    `RelicBoltPistol` : les attaques **MELEE** de son porteur gagnent `+extraPierceRatio` points de
    ratio de percage, DOUBLES si la cible est Chaos ou Xenos.

    Canal PERCAGE (`BaseEffect$$PiercingBonusForAttack`), agrege par
    `entities/effects/__init__.py::piercing_bonus_from_effects` puis additionne par
    `IdunBattle.Core.Services.DamagePrediction$$GetAttackPiercingDamageRatio` DANS la meme somme que
    `PiercingRatio` du profil et les stats `ExtraPierce*`, AVANT le `Min(100, ...)`."""

    def create_effect_piercing_bonus_for_attack(self, ctx: "Mapping | None" = None) -> "int | None":
        """MIRROR de `IdunBattle.Entities.Effects.Loki.RelicBoltPistol_ExtraPierceEffect$$
        CreatePiercingBonusForAttack` :

            EffectBonus.ForAddition( get_OwnerIsCaster & IsMeleeAttack,
                                     If( HasTrait(Target@+0x60, Xenos) | HasTrait(Target@+0x60, Chaos),
                                         Multiply(ConfigVar(0x3f = extraPierceRatio),
                                                  <DSLFormulas+0x28> = Direct(2)),
                                         ConfigVar(0x3f = extraPierceRatio) ) )

        Les etages sont SEPARES et chacun peut se taire independamment (aucun scalaire fitte) :
          1. `get_OwnerIsCaster` -- le porteur est-il l'attaquant du coup ?
          2. `IsMeleeAttack`     -- `ctx["is_ranged"]`, tri-etat #106 : `None` = nature non threadee
             par le vecteur appelant => le gate se TAIT (jamais permissif) ;
          3. `HasTrait(Target)`  -- branche du `If`, PAS un gate : sans le trait le bonus vaut `cv` ;
          4. `GetAbilityState`   -- niveau/multiplicateur TERTIAIRE de la relique sur le porteur ;
          5. `ConfigVar` puis `Multiply` -- la magnitude.

        `ctx["target_traits"]` doit venir du substrat d'ENTITE (`entity_trait_names`) : `Xenos` et
        `Chaos` ne sont dans AUCUN `traits` gameconfig (cf. l'en-tete de module)."""
        c = ctx or {}
        if not _owner_is_caster(c):                              # 1
            return None
        if c.get("is_ranged") is not False:                      # 2  IsMeleeAttack (tri-etat #106)
            return None
        return _amount(self, _VAR_PIERCE, c.get("target_traits"), c)     # 3-5


class RelicBoltPistolExtraCritDamageEffect(BaseEffect):
    """`RelicBoltPistol_ExtraCritDamage` (0x5b2 = 1458) -- owner-effect PERMANENT de la relique
    `RelicBoltPistol` : les attaques **RANGED** de son porteur gagnent `+extraCritDmg` de degat
    critique, DOUBLES si la cible est Chaos ou Xenos.

    Canal crit-DEGAT (`BaseEffect$$CritDamageBonus`), agrege par
    `entities/effects/__init__.py::crit_damage_bonus_from_effects` puis ajoute a `GetStat(10)` par
    `IdunBattle.Core.Services.DamagePrediction$$CalculateCriticalDamage` (`max(0, GetStat(10) +
    somme)`). Contrairement a `AmuletOfTheVoidwyrm_CritDamageReduction` (`ForSubtraction`), c'est un
    `ForAddition` : le retour est POSITIF."""

    def create_effect_crit_damage_bonus_for_attack(self, att_ctx: "Mapping | None" = None) -> "int | None":
        """MIRROR de `IdunBattle.Entities.Effects.Loki.RelicBoltPistol_ExtraCritDamageEffect$$
        CreateCritDamageBonus` :

            EffectBonus.ForAddition( get_OwnerIsCaster & IsRangedAttack,
                                     If( HasTrait(Target@+0x60, Xenos) | HasTrait(Target@+0x60, Chaos),
                                         Multiply(ConfigVar(0x42 = extraCritDmg),
                                                  <DSLFormulas+0x28> = Direct(2)),
                                         ConfigVar(0x42 = extraCritDmg) ) )

        Memes cinq etages que son frere PERCAGE, a deux cles de contexte pres : le canal CRIT nomme
        les traits de la cible `tgt_traits` (et non `target_traits`) et les tire deja du substrat
        d'ENTITE (`_crit_board`, #889-r5) ; sa nature de coup est la meme cle tri-etat `is_ranged`."""
        c = att_ctx or {}
        if not _owner_is_caster(c):                              # get_OwnerIsCaster
            return None
        if c.get("is_ranged") is not True:                       # IsRangedAttack (tri-etat #106)
            return None
        return _amount(self, _VAR_CRIT_DMG, c.get("tgt_traits"), c)
