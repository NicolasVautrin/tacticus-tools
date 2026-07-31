# case-354 — `MartialApotheosis` n'a plus de porteur : le port est fidèle, le TEST est orphelin

**Verdict : ni bug de port, ni bug du rail turn-start.** Le build `rnca9r7q6c` a **retiré
`MartialApotheosis` (PassiveAbilityType 1045) de son unique porteur** `necroOverlord`, remplacée
par `MyWillBeDoneOverlord`. Un port fidèle ne peut pas dispatcher une ability que le gameconfig
n'accorde à personne — `start_turn_triggers` rend `[]`, et **c'est la bonne réponse**.

Mesure : `scripts/python/probe_354_martial_apotheosis_carrier.py` (4 étages).

## 1. L'étage qui décroche est l'ATTRIBUTION, pas le dispatch

La signature l'isolait déjà sans rien mesurer — sur les 5 tests de
`tests/engine/runner/test_martial_apotheosis_live.py`, **les 3 qui rougissent sont exactement les
3 qui passent par `start_turn_triggers`** ; les 2 qui appellent le port directement (`matches`,
`execute_behaviour`) **passent**. L'arbre DSL, le ciblage anneau-1, les params et le pump de
dispatch sont donc tous sains.

`collect_triggered_abilities` (`triggers/dispatch/core.py`) n'instancie une ability-trigger que si
`gameconfig.unit(visualId).passiveAbilities` la nomme. C'est ce test-là qui rend faux.

## 2. Les quatre voies, toutes fermées

| voie | mesure | résultat |
|---|---|---|
| gameconfig (`lineup`/`npc`/`summons` × 4 voies d'attribution) | **les 2 instantanés** présents sur la machine (29/07 et 30/07) | **0 porteur** |
| trait | `StaticBattleRules.Trait$$GetTriggeredAbility` = `TryGetValue` sur le dict bâti par `StaticBattleRules.Trait$$.cctor` — **41 paires**, valeurs de `0x3f2` à `0x5ce` | **`0x415` (1045) ABSENT** (la suite saute de `0x414` à `0x41b`) |
| live-event / tile | `MartialApotheosis` ne porte ni le préfixe `Enhancement*` ni `PowerUp_*` | sans objet |
| live (le jeu qui tourne) | `decisionView` du `necroOverlord` monté en runner | `Loki_NormalAttack` + `ResurrectionOrb` (1009) **seuls** ; le port n'instancie pour lui que `LivingMetalRepairAbility` |

Balayer **les deux** instantanés distingue « le jeu vient de retirer l'ability » d'un artefact de
lecture d'un snapshot périmé (`gameconfig._find_gameconfig` ne retient que le dernier ÉCRIT) : le
kit est identique dans les deux — le changement est antérieur, il est venu **avec le build**.

La config d'ability, elle, **existe toujours** (`attackRangeType: Melee`, `nrOfHits: 2`,
`damageProfile: Energy`), et `MartialApotheosisAbility$$CreateTrigger` **existe toujours** dans le
binaire — et confirme la structure portée : `On(0x16) & <prédicat> & AmountIsGreaterThanZero(
GetPossibleTargets)`. Ability retirée de son porteur ≠ ability supprimée du jeu. **Le port reste
juste ; il est seulement INERTE.** À ne pas supprimer : il redeviendrait vivant si un kit la
reprend.

⚠ Le build a même donné à `MartialApotheosisAbility` **son propre** `CreateTrigger` /
`GetPossibleTargets` (le port les documente comme *hérités* de `DestroyerHiveAbility`, RE
`gqfc5mff6c`). Structure inchangée, provenance différente — sans effet tant que l'ability est
inerte.

## 3. Ce que le rouge NE dit pas

Le test E imprimait `live target=e79 live_dmg=3702` et l'on pouvait lire « le LIVE tire bien, seul
le port est muet ». **Non** : son assertion est `live_dmg > 0`, un critère que **n'importe quelle**
source de dégât satisfait. Rien n'y attribue ces 3702 à `MartialApotheosis` — et l'ability n'est
pas au kit. C'est un critère trop faible pour porter une conclusion.

Le candidat naturel, `MyWillBeDoneOverlord`, n'est d'ailleurs **pas** un turn-start :
`MyWillBeDoneOverlordAbility$$CreateTrigger` = `On(0x12 = TurnStart_EffectActivation) &
AmountIsGreaterThanZero(GetPersistentDataListAsEntities)` **|** `On(0x29 =
UnitFinishedTurnNormally) & OwnerIsActor`.

**Piège d'énum** (deux abilities de noms voisins, deux enums) : `MartialApotheosis` =
Passive/Triggered **1045** ; `MartialInspiration` = Active **1191** (celle de `#316`) ;
`GetEmRuntz` = Active **1045**. Le correctif `_MAKE_DMG_INPUT_OVERRIDES` de #316 ne concerne pas ce
cas.

## 3bis. Contre-épreuve : le rail turn-start est SAIN

`DestroyerHive` est la classe native dont `MartialApotheosisAbility` **hérite** son
`CreateTrigger` — même vecteur `On(0x16)`, même `OwnerIsActor`, même
`AmountIsGreaterThanZero(GetValidTargets)`, même anneau-1, même `PickRandomly(…, 1)` — et son
porteur `deathTyphus`, lui, **existe toujours**. `test_destroyer_hive_live.py` +
`test_living_metal_repair_live.py` (l'autre passif turn-start du même `necroOverlord`) :
**12 passed**. Le patron de trigger et le rail de dispatch sont donc exercés et verts ; ce qui
manque à 1045 est uniquement son porteur.

## 4. Cas ISOLÉ, et c'est mesuré

Étage 4 du probe : sur les **29** entrées de `ABILITY_TRIGGERS`, `MartialApotheosis` est la
**seule** orpheline. La mise à jour n'a pas ouvert de série — un seul port est tombé inerte.

## 5. Ce qui reste ouvert

Le test **reste ROUGE** : il cible une ability sans porteur, aucune correction du port ne peut le
verdir. Le trancher est un arbitrage de périmètre, pas de RE — trois issues possibles (le retirer ;
le convertir en garde d'inertie ; greffer l'ability sur une unité du pool par injection catalogue,
cf. `case-92` §5bis, qui re-validerait le port sans porteur naturel). **Non tranché ici.**

Résidu neuf : **`MyWillBeDoneOverlord` n'est portée sur aucune face** — ni COMBAT
(`MyWillBeDoneOverlordAbility`), ni décision (`MyWillBeDoneOverlordPlaybook`,
`MyWillBeDoneOverlordNonOwnerPlaybook`, déjà nommé par `#271-r4`). C'est le passif **effectif** de
`necroOverlord` + **5 npc** Necron depuis ce build. Backlog `#354-r1`.
