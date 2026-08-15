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

L'ECART MESURE, ET OU IL VIT -- residu `#975-r3`
-------------------------------------------------
Confrontation LIVE (`probe_975_kit_decision_faces.py`, banc `MC1_67`/777, cinq porteurs
co-injectes) : le port rend le MEME argmax de POSITION et la MEME cible que l'oracle `ncEvaluate`,
et le MEME ordre de preference entre positions --

    pos   (1,5)   (1,6)   (0,4)   (0,5)   autres
    natif 54.50   45.59   41.76   34.56   28.17
    port  38.99   32.67   32.11   24.83   21.74

-- mais pas la meme VALEUR. La decomposition par etage (`probe_975_diag1139{,b,c,d}.py`) place
l'ecart EN AMONT de cette feuille, dans la PREDICTION DE DEGAT, et l'etablit par DEUX voies
natives independantes :

  * `ncPlaybookPredict --via evaluate` capture les `ProbableDamageEvent` que le playbook NATIF
    construit : a `(1,6)`, **min 2933 / max 4230, hits 1** -- **IDENTIQUES POUR LES TROIS CIBLES**,
    dont les armures different (2662 / 2510 / ...). Le port, lui, rend 1670/3798 pour l'une et
    1184/2886 pour l'autre : ses bornes DEPENDENT de la cible.
  * le PLAN natif (`computeAttackPlans`, voie qui n'emprunte AUCUN playbook) publie pour les memes
    couples `dmgMin/dmgMax` = **5984/8436**, **8976/10542**, **7480/8536** la ou le port rend
    1184/2886, 2004/4557, 1480/3608 -- un facteur ~3 a ~5.

Un balayage de `base_override` montre qu'AUCUNE valeur ne reconcilie : la valeur qui reproduit
l'utilite native (**4933**) n'est ni `minDmg` (4254), ni `maxDmg` (5318), ni leur moyenne (4786),
et le RAPPORT max/min differe structurellement (1.44 natif contre 2.05-2.27 port). Ce n'est donc
pas un choix de variable, c'est la CHAINE de prediction. `1139` n'est d'ailleurs dans AUCUN des
registres `_PREDICTION_MINMAX_*` d'`entities/abilities/active_ability.py` : sa prediction n'avait
jamais ete confrontee. Le porteur `admecDestroyer` porte `HeavyWeapon_ExtraDmg` et
`HeavyGravCannon` -- deux modificateurs de degat que le port applique PARTIELLEMENT.

CONSEQUENCE, ecrite sans la maquiller : l'argmax est conforme quand l'ecart est monotone sur les
cibles (montage A -- meme position, meme cible, y compris le kill-sure), et il PEUT DIVERGER quand
il ne l'est pas (montage B -- natif `(1,6)`, port `(1,5)`). La face DECISION est donc portee et
sa STRUCTURE est verifiee terme a terme ; sa VALEUR reste celle que lui donne l'etage amont.

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
# FORME B, differes CLASSES GRATUITS depuis le degraissage du baril `engine.playbook`
# (#485-r1-r4). `generate_multi_hit_attack_prediction` est SUBSTITUE par cinq patcheurs.
from engine.entities.abilities import ability_configuration as _abcfg
from engine.entities.abilities import active_ability as _actab
from engine.playbook.prediction import abilities as _pred_ab
from engine.playbook import probable_damage_event as _pde

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
        ctx0 = ctx.scene.ctx(ctx.uid)
        cfg = _abcfg.AbilityConfiguration.from_gameconfig(_ABILITY_NAME, GC.ability(_ABILITY_NAME))
        if ctx0 is None or cfg is None:
            return None
        ab = _actab.active_ability_for(_ABILITY_NAME, self.ABILITY_ID, ctx0, cfg,
                                       ability_state=ctx.scene.ability_state(ctx.uid,
                                                                             self.ABILITY_ID))
        minv = cfg.get_variable_for_level(_VAR_MIN_DMG, ab.level, 0, ab.multiplier)
        consts = cfg.constants or {}
        hits = max(1, int(consts.get(_CONST_HITS) or 1))
        return _pred_ab.generate_multi_hit_attack_prediction(
            ctx.scene, ctx.uid, target, self.ABILITY_ID, _ABILITY_NAME, attack_pos=tile,
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
        ev = _pde.ProbableDamageEvent(target=target, prediction=dp)
        u = _pde.calculate_utility_from_damage_event(ev, ctx.wt, ctx.scene.hpmax(target))
        return self._BASE_UTILITY + u
