"""`SentinelDirectivesPlaybook` (0x473 = 1139, `admecDestroyer` << Sy-Gex >>) -- face DECISION, #975.

REACHABILITY, LUE ET NON SUPPOSEE
---------------------------------
`data/symbols/rnca9r7q6c/metadata/active_playbook_builders.tsv` :

    active   1139   IdunBattle.AI.Playbook.SentinelDirectivesPlaybook

UNE seule entree, dict `active` (+0x68). ⚠ Le namespace est `IdunBattle.AI.Playbook` **SANS**
`.Loki` -- contrairement aux quatre autres playbooks de ce lot. Le lire de travers ferait chercher
un symbole qui n'existe pas.

BASE DE HIERARCHIE -- `NonComparablePlaybook<T>`, LUE dans `frida/classes.tsv`
------------------------------------------------------------------------------
    IdunBattle.AI.Playbook.SentinelDirectivesPlaybook  112  IdunBattle.AI.Playbook.NonComparablePlaybook`1

Le `.ctor` decompile s'appelle `ComparablePlaybook<...>$$.ctor(this, 0x473, klass)` : corps trivial
DEDUPLIQUE (piege #487-r1). Le `0x473` est l'ability_id, LU la.

LE CORPS, TERME A TERME
------------------------
`IdunBattle.AI.Playbook.SentinelDirectivesPlaybook$$EvaluateNonComparable` :

    bucket = new Bucket<UnitAction>(0, Nullable(<statics+0x00>))       # cctor : Fix64(1)
    foreach entities in BasePlaybook.GetEligibleTargetsSelectable(caster, casterPosition):
        utility   = Fix64.op_Implicit(1)                              # <-- PLANCHER CONSTANT
        casterPos = entities.get_CasterPosition()
        damage    = ability.Config.GetVariableForLevel(0xc, abilityState, 0)   # var 12 = minDmg
        profile   = ability.Config.GetDamageProfile().Value                    # const damageProfile
        hits      = ability.Config.GetNumberConstant(0x2f)                     # const 47 = nrOfHits
        u         = Playbook<T>.CalculateUtilityFromDamageEvent(
                        entities@+0x08 = caster, entities@+0x10 = target, casterPos,
                        damage, profile, hits)
        utility   = Fix64.op_Addition(utility, u)
        bucket.AddAction(BasePlaybook.GenerateAction(casterPosition, entities@+0x10, utility))
    return bucket

`IdunBattle.AI.Playbook.SentinelDirectivesPlaybook$$.cctor` :

    <statics+0x00> = FixMath.NET.Fix64$$op_Implicit(1)

TROIS POINTS QUI SE LISENT, ET QU'AUCUN VOISIN NE DONNE
--------------------------------------------------------
1. **LE DEGAT EST `minDmg` SEUL, PAS LA MOYENNE.** Le call-site passe
   `GetVariableForLevel(0xc)` -- un accesseur DIRECT de variable, `AbilityVariableType.minDmg`
   (0xc = 12, LU dans le mirror `engine/entities/ability_variable_type.py`). Ce n'est PAS
   `AActiveAbility$$MinMaxDamage` (= `Half(Sum(var 0xc, var 0xd))`) qu'emploient `KillMaimBurn` et
   le chemin generique. Le meme choix natif existe deja pour `HammerOfWrath` (`GetMinDamage`), d'ou
   `base_override=`. Prendre la moyenne surevaluerait l'utilite de ~25 % sur ce kit
   (`minDmg`/`maxDmg` du gameconfig 1139 = 48/60 au rang 1, 3420/4275 au dernier).

   ⚠ QUALIFICATION D'ENUM : `0xc = 12` est `minDmg` **dans `AbilityVariableType`** ; l'ordinal 12
   d'`AbilityConstantType` est `minAdjacentEnemies`, qui n'a rien a voir. Le discriminant est
   l'ACCESSEUR appele au site (`GetVariableForLevel` -> variables ; `GetNumberConstant` ->
   constantes), jamais l'entier. Meme raison pour `0x2f = 47`, qui vaut `nrOfHits` des DEUX cotes
   mais est ici lu par `GetNumberConstant`, donc c'est la CONSTANTE.

2. **L'UTILITE PORTE UN PLANCHER `+1` CONSTANT**, pose AVANT la somme
   (`Fix64.op_Implicit(1)` puis `op_Addition`). Consequence concrete : `MIN_UTILITY` valant 1
   (le meme statique), une cible dont la prediction de degat rend une utilite NULLE passe quand
   meme le gate `Bucket$$AddAction` (`util >= min`). 1139 est donc TOUJOURS proposable des qu'une
   cible est eligible -- le degat ne fait que DEPARTAGER les cibles entre elles.

3. **L'etage de prediction est le MEME que celui de `HammerOfWrath`.**
   `IdunBattle.AI.Playbook.Playbook<T>$$CalculateUtilityFromDamageEvent` (surcharge a 7 params,
   RELUE pour cette tranche) fait litteralement :

       pred = <IDamagePrediction slot 0x28>(battleQuery@this+0x28, caster, target, casterPosition,
                                            Nullable(AbilityOrEffect(this.ability)),
                                            damage, Nullable(profile), hits)
       ev   = new ProbableDamageEvent(target, pred)
       return CalculateUtilityFromDamageEvent(ev, caster, casterPosition, weights)

   -- c'est-a-dire : le scalaire `damage` est l'`initialDamage` du predicteur, `profile` son
   profil et `hits` son nombre de coups. Cote port, ce triplet est exactement
   `base_override` / `profile_override` / `hits_override` de
   `generate_multi_hit_attack_prediction`, puis `calculate_utility_from_damage_event`.

BORNES DE PORT, nommees
------------------------
* AUCUN gate propre : `ShouldEvaluate` n'est PAS surcharge par 1139 (`frida/methods.tsv` ne lui
  declare que `.ctor`, `.cctor` et `EvaluateNonComparable`), donc c'est l'implementation de base
  `BasePlaybook$$ShouldEvaluate` -> `GetUseProbability` = `Fix64(1)` -> True constant. Pas de porte
  aleatoire ici.
* `generate_multi_hit_attack_prediction` rend `None` (config sans `minDmg`/`maxDmg`, base <= 0,
  scene absente) -> la cible est sautee. Le natif, lui, construirait une prediction degeneree ;
  l'ecart est une borne INF et ne concerne que des etats ou le canal ne publie rien.
* Le spread +-20 % de `GetBaseDamageFix64` est applique en aval du scalaire, cote port comme cote
  natif (c'est le meme `IDamagePrediction` slot 0x28) : `base_override` remplace la BASE, pas les
  bornes.
"""
from __future__ import annotations

from engine.entities.ability_constant_type import AbilityConstantType
from engine.entities.ability_variable_type import AbilityVariableType
from engine.entities.active_ability_type import ActiveAbilityType

from ._base import NCContext, _PlanTargetPlaybook

_ABILITY_NAME = "SentinelDirectives"

#: `GetVariableForLevel(config, 0xc, abilityState, 0)` -- `AbilityVariableType.minDmg` (12).
_VAR_MIN_DMG = AbilityVariableType.minDmg.name
#: `GetNumberConstant(config, 0x2f)` -- `AbilityConstantType.nrOfHits` (47).
_CONST_HITS = AbilityConstantType.nrOfHits.name
#: `AbilityConfiguration$$GetDamageProfile()` = la constante `damageProfile` (ici `Physical`).
_CONST_PROFILE = "damageProfile"


class SentinelDirectivesPlaybook(_PlanTargetPlaybook):
    """`IdunBattle.AI.Playbook.SentinelDirectivesPlaybook$$EvaluateNonComparable` (0x473 = 1139).

    utilite(cible) = `1 + CalculateUtilityFromDamageEvent(minDmg[level], damageProfile, nrOfHits)`
    -- plancher constant plus le score de degat de la cible."""
    ABILITY_ID = int(ActiveAbilityType.SentinelDirectives)   # 0x473 = 1139
    MIN_UTILITY = 1.0     # `...SentinelDirectivesPlaybook$$.cctor` : `Fix64$$op_Implicit(1)`
    PRIORITY = 0          # hors `NATIVE_PRIORITY` (defaut `AbilityPriority.Normal`, sweep #170)
    #: `Fix64.op_Implicit(1)` pose AVANT la somme -- cf. le point 2 de l'en-tete.
    _BASE_UTILITY = 1.0

    def _ability_prediction(self, tile, target, ctx: NCContext):
        """Le `DamagePredictionResult` que `CalculateUtilityFromDamageEvent` score, avec les TROIS
        entrees LUES au call-site : `minDmg` (var 0xc) en base, `damageProfile` en profil,
        `nrOfHits` (const 0x2f) en coups. Foyer UNIQUE, partage par `damage_predictions` (trace de
        construction) et `evaluate_non_comparable` (utilite)."""
        if ctx.scene is None or tile is None or target is None:
            return None
        import gameconfig as GC
        from engine.entities.abilities.ability_configuration import AbilityConfiguration
        from engine.playbook.prediction.abilities import generate_multi_hit_attack_prediction
        from engine.entities.abilities.active_ability import active_ability_for
        ctx0 = ctx.scene.ctx(ctx.uid)
        cfg = AbilityConfiguration.from_gameconfig(_ABILITY_NAME, GC.ability(_ABILITY_NAME))
        if ctx0 is None or cfg is None:
            return None
        ab = active_ability_for(_ABILITY_NAME, self.ABILITY_ID, ctx0, cfg,
                                ability_state=ctx.scene.ability_state(ctx.uid, self.ABILITY_ID))
        minv = cfg.get_variable_for_level(_VAR_MIN_DMG, ab.level, 0, ab.multiplier)
        consts = cfg.constants or {}
        hits = max(1, int(consts.get(_CONST_HITS) or 1))
        return generate_multi_hit_attack_prediction(ctx.scene, ctx.uid, target, self.ABILITY_ID,
                                                    _ABILITY_NAME, attack_pos=tile,
                                                    base_override=minv, hits_override=hits,
                                                    profile_override=consts.get(_CONST_PROFILE))

    def damage_predictions(self, tile, target, ctx: NCContext) -> list:
        """UN SEUL event par cible : le corps natif ne traverse aucun autre
        `ProbableDamageEvent$$.ctor` (pas de gate `WillNormalAttackKill`, contraste `KillMaimBurn`)."""
        dp = self._ability_prediction(tile, target, ctx)
        return [("ability", dp)] if dp is not None else []

    def evaluate_non_comparable(self, tile, target, ctx: NCContext):
        """`Fix64(1) + CalculateUtilityFromDamageEvent(...)` -- le plancher est DANS l'utilite, pas
        seulement dans le gate du bucket (cf. le point 2 de l'en-tete)."""
        dp = self._ability_prediction(tile, target, ctx)
        if dp is None:
            return None
        from engine.playbook.probable_damage_event import (ProbableDamageEvent,
                                                           calculate_utility_from_damage_event)
        ev = ProbableDamageEvent(target=target, prediction=dp)
        u = calculate_utility_from_damage_event(ev, ctx.wt, ctx.scene.hpmax(target))
        return self._BASE_UTILITY + u
