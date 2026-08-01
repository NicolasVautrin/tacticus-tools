"""`IdunBattle.AI.Playbook.Loki.NeuroparasitePlaybook` -- face ATTACK du triggered `Neuroparasite`
(1183), passif de `tyranNeurothrope` << Neurothrope >> (HERO, AU POOL `rl_duel build --list-pool`)
et de 6 npc : 7 porteurs DISPATCHES, a EGALITE DE TETE de la liste des residus ATTACK de #419.

Feuille `TriggeredAbilitiesUtility(2)` du composite Damage(34), MEME dispatcher que Psyker,
AggressiveOnslaught, SuppressiveFire, Lakrimae et BarbedOvipositor
(`utilities/tile.py::evaluate_attack_in_steps`, vslot 3).

## Le corps natif, remis en C#

`IdunBattle.AI.Playbook.Loki.NeuroparasitePlaybook$$CalculateAttackUtilityInStepsInternal` monte la
SM `d__2` -- et sa STRUCTURE se lit dans le wrapper, pas dans un nom : il ecrit `sm@+0x20 = case`,
`sm@+0x28 = this` (le PLAYBOOK) et `sm@+0x10 = 0` (state). **Le troisieme parametre, le delegue
scorer `getUtilityVal`, n'est PAS stocke** -- il n'y a donc, dans ce playbook, AUCUN appel a
`TriggeredAbilityPlaybook<T>$$GetUtilityValue`, AUCUNE cle de poids, et AUCUN `.cctor`. Le corps est
`NeuroparasitePlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__2$$MoveNext`, DEUX etats de
yield :

    target = case@+0x20                                     // la CIBLE du case
    if (EntityExtensions.HasEffect(target, this.State, (EffectType)0x4c2, onlyActive: null))
        yield return Fix64.op_Implicit(1)                    // etat 2
    else
        yield return Fix64.op_Implicit(0)                    // etat 1

Trois lectures qui ne se devinent pas, et dont AUCUNE ne se generalise depuis un voisin de la liste :

1. **La valeur est le LITTERAL `1`, pas un poids du BC.** `FixMath.NET.Fix64$$op_Implicit` est
   `(long)(int)value << 0x20` -- l'entier `1` promu en Fix64, soit **1.0** exactement. C'est le seul
   playbook ATTACK porte a ce jour dont la sortie ne passe pas par
   `Utilities.Default.TriggeredAbilities` : il n'y a rien a lire dans le gameconfig, et chercher une
   cle « NEUROPARASITE_* » serait chercher ce qui n'existe pas. Le corollaire pratique : ce terme ne
   peut PAS etre neutralise par un poids nul du BC servi (piege #271 sans objet ici), et il vaut 1
   quel que soit le BC.

2. **`0x4c2` = 1218 = `EffectType.Neuroparasite`** -- a QUALIFIER, car `1183` est le
   `TriggeredAbilityType` du MEME nom (l'ability) et `1218` l'`EffectType` (le parasite pose sur la
   victime). Le playbook lit l'EFFET, pas l'ability. L'effet est materialise COTE CIBLE, mesure live
   par #86 (`decisionView.effects[].effectType == 1218` sur la victime ; cf.
   `engine/entities/effects/loki/damage_reduction.py::NeuroparasiteEffect`).

3. **Le predicat porte sur la CIBLE seule** : ni stats, ni traits, ni position du caster, et le case
   n'est lu QU'EN `+0x20`. En particulier **`case.DamagePrediction` (`UtilityAttackCase@+0x28`)
   n'est PAS lu** : contrairement a `BarbedOvipositor` (#438), ce playbook ne consomme pas le canal
   `prediction` -- il l'accepte et l'ignore, comme son corps natif.

`onlyActive` est le litteral `0` au call-site ⇒ `IdunBattle.Entities.EntityExtensions$$HasEffect` =
`IsOwnerOfEffect(e, state, type, 0) || IsTargetOfEffect(e, state, type)` SANS lecture de
`EffectComponent.IsActive @+0x5c` : cote port c'est le foyer PARTAGE
`battle_query.scene_has_effect`, exactement celui de `SuppressiveFire` (meme corps natif, meme
argument nul -- une copie locale serait un fork de port).

## Le sens, verifie sur les DEUX faces de l'ability (le playbook n'est pas l'inverse du trigger)

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.NeuroparasiteAbility$$CreateTrigger` monte
`On(9) & OwnerIsCaster & !HasEffect(target, 0x4c2, ...) & IsUnit(target) &
CurrentAttackDamageProfilesContain(0xd) & !(OwnerIsActor & OwnerIsTarget)`, et
`$$CreateBehaviour` un `DSLBehaviors.AddBondEffect(0x4c2, ...)`. Le `!HasEffect` de ce trigger ne
CONTREDIT pas le `HasEffect` du playbook : il dit seulement que la POSE initiale du parasite ne se
rejoue pas. La ou l'utilite se gagne, c'est
`IdunBattle.Entities.Effects.Loki.NeuroparasiteEffect$$GetIncreaseLevelBehaviour`
(`DSLBehaviors.IncreaseEffectLevel`, plafonne par `$$GetMaximumLevel`), arme par
`$$GetDamageTakenTrigger` (`OwnerIsTarget & CurrentAttackDamageProfilesContain(0xd)`) : re-frapper
une cible DEJA infectee **monte le niveau**, et c'est ce niveau que multiplie l'additif de degat de
`$$CreateEffectDamageMalusForDefense`. Le playbook prefere donc la cible deja parasitee -- 1 point.

## Face MOVE : `yield Fix64(0)` CONSTANT

`NeuroparasitePlaybook.u003CCalculateMovementUtilityInStepsInternalu003Ed__1$$MoveNext` est
DECOMPILE LU : un unique `yield return Fix64.op_Implicit(0)`, rien d'autre. Elle n'entre donc pas au
registre `TRIGGERED_MOVE_PLAYBOOKS`, et son absence EST le comportement natif (meme forme que
`Lakrimae` et `BarbedOvipositor` -- la taille trie, le decompile conclut).
"""
from __future__ import annotations

from engine import battle_query as bq

from ..entities.effect_type import EffectType
from ..entities.triggered_ability_type import TriggeredAbilityType

# `HasEffect(target, this.State, (EffectType)0x4c2, onlyActive: null)` -- 0x4c2 = 1218, l'EFFET
# `Neuroparasite` pose sur la victime (a NE PAS confondre avec le `TriggeredAbilityType` 1183 du
# meme nom, qui est l'ability du Neurothrope).
_NEUROPARASITE = int(EffectType.Neuroparasite)                 # 1218 = 0x4c2
# `Fix64.op_Implicit(1)` = `(long)1 << 0x20` = 1.0. LITTERAL du corps natif, PAS une cle de poids :
# ce playbook n'a ni delegue scorer capture, ni `.cctor`, ni entree `Utilities.Default.
# TriggeredAbilities` (cf. en-tete, point 1).
_INFECTED_VALUE = 1.0


class NeuroparasitePlaybook:
    """`NeuroparasitePlaybook` (`IdunBattle.AI.Playbook.Loki`, triggered 1183 -- l'id passe par
    `$$.ctor` a la base `TriggeredAbilityPlaybook<T>` est bien `0x49f`). Seule la face ATTACK a un
    corps ; la face MOVE est un `yield 0` constant au natif (cf. en-tete)."""

    ability_id: int = int(TriggeredAbilityType.Neuroparasite)   # 1183

    def calculate_attack_utility_in_steps(self, ctx, attacker_uid: int, ability_id: int,
                                          case_tgt_id: int, attack_tile, prediction=None) -> float:
        """Mirror de `<CalculateAttackUtilityInStepsInternal>d__2$$MoveNext` (cf. en-tete) : 1 si la
        CIBLE du case porte deja l'effet `Neuroparasite` (1218), 0 sinon.

        `prediction` est accepte et IGNORE : le corps natif ne lit que `case@+0x20` (la cible), pas
        `case.DamagePrediction` (`UtilityAttackCase@+0x28`). Substrat absent (`ctx.scene` None,
        contexte offline) -> 0.0 : le natif, lui, deref sans garde (`FUN_1801f51f0` sur case ou
        playbook nul), il n'a donc pas de repli a mirrorer -- c'est la degradation du port quand la
        table d'effets n'existe pas, et elle est PERMISSIVE-EN-MOINS (jamais un 1 invente)."""
        sc = getattr(ctx, "scene", None)
        if sc is None:
            return 0.0
        return _INFECTED_VALUE if bq.scene_has_effect(sc, case_tgt_id, _NEUROPARASITE) else 0.0
