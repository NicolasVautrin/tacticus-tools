# #462-r4b-r1-r1-r1-r1 — le RETRAIT hérité d'`ABondEffect`, et le virtuel qui l'arme

#556 a porté la POSE de `Neuroparasite` et sa montée en niveau, et a nommé au §6 un résidu : les
**trois `Triggered()` de `RemoveEffect`** hérités d'`IdunBattle.Entities.Effects.ABondEffect`, dont
les gates sont des **virtuels** que les tables de symboles ne savent pas lire. Un bond qui ne se
retire jamais est un effet qui persiste indûment — dégât ou stat-mod appliqué après sa condition de
fin. Ce cas ferme (a), établit pourquoi (b) et (c) restent NON CONFRONTÉS, et laisse deux résidus
nommés.

## 1. Les trois artefacts (build `rnca9r7q6c`)

`IdunBattle.Entities.Effects.ABondEffect$$CreateHandleTriggerAbilitiesInternal` :

```
(a) <klass+0x748>() : bool ->
      Triggered( NOT AmountIsZero(BondedEntityFromEffect(Effect@DSLSelectors+0x38))
                 & ( On(2 = PreUnitDeath_2) | On(0x25 = UnitRemoved) )
                 & IsEntityWithIdTarget(BondedEntityFromEffect(...)),        RemoveEffect(Effect) )

(b) <klass+0x728>() : Nullable<int> ; si HasValue ->
      Triggered( NOT IsInRange(Owner@DSLSelectors+0x30, BondedEntity, Direct(value))
                 & NOT AmountIsZero(BondedEntity) & On(0x1d = UnitPositionChanged_2),
                                                                             RemoveEffect(Effect) )

(c) <klass+0x738>() : bool ->
      Triggered( NOT IsAdjacent(Owner@0x30, BondedEntity, 3)
                 & NOT AmountIsZero(BondedEntity) & On(0x1d),                RemoveEffect(Effect) )
```

Nœuds lus : `IdunBattleLogic.Entities.DSLTriggers$$IsInRange` construit
`IdunBattle.Entities.Triggers.IsInRangeAbilityTrigger` (`query.GetDistance(s1, s2) <= range`) —
**pas** `IsUnitOnTileEffectTrigger`, vers qui ghidra résout le ctor **dédupliqué** ; c'est la
signature Frida (`selector1, selector2, range: IAmountFormula`) qui tranche.
`IdunBattleLogic.Entities.DSLTriggers$$IsEntityWithIdTarget` construit
`IdunBattle.Entities.Triggers.IsEntityWithIdAbilityTrigger` avec `isOwner = 0` : l'id de l'entité
sélectionnée doit égaler celui de la **cible** de l'event.

## 2. Les trois virtuels sont NOMMÉS — au runtime, parce que les tables ne pouvaient pas

`probe_462_r4b_r1_r1_r1_r1_bond_removal.py --step vtable` lit le slot sur l'instance et rend son
`il2cpp_method_get_name` :

| slot | nom | type |
|---|---|---|
| `+0x728` | `get_Range` | `System.Nullable<System.Int32>` |
| `+0x738` | `get_Adjacent` | `System.Boolean` |
| `+0x748` | `get_RemoveOnBondedEntityDeath` | `System.Boolean` |

⚠ **Ce pas ne conclut pas seul.** Une vtable IL2CPP n'est matérialisée qu'après
`il2cpp_runtime_class_init` : mesure du 2026-08-04, **3 classes sur 36**, et la base `ABondEffect`
— abstraite, jamais instanciée — rend le **stub de remplissage paresseux**
(`Unity.Burst.Unsafe$$AsRef`, qui ne retourne pas) pour les trois slots. La comparer aux dérivées,
qui est le patron de #558, comparerait ici à du bruit. **Monter un runner ne suffit pas non plus** :
33 classes restent à NULL, y compris les 20 `APendingAttackEffect`.

Ce qui conclut est `--step declared` : il énumère `class_get_methods` **niveau par niveau** de la
chaîne de parents (`resolveMethodPtr`). Une classe qui surcharge déclare son propre `MethodInfo`
**même quand IL2CPP a dédupliqué le corps** — le `methodPointer` est partagé, l'entrée de la classe
ne l'est pas. C'est exactement ce que `frida/methods.tsv`, indexée par ADRESSE, ne peut pas montrer.

Corps triviaux, résolus par leur adresse (les noms ghidra qui y pendent —
`UnityEngine.U2D.IK.Solver2D$$DoValidate`, `Stash.Native.StashNative$$get_IsPurchaseProcessing`,
`Unity.Services.Core.Device.UnityAdsIdentifier$$get_UserId` — sont ceux du propriétaire
**arbitraire** du corps partagé) : `return 1` = TRUE, `return 0` (1 octet) = FALSE, `return 0`
(8 octets) = `Nullable<int>` VIDE.

**37 classes balayées.** (b) n'est armé que par `TauntedEffect`,
`Taunted_RefreshUnitTurnFinishedEffect`, `BlockUnitMovementBondEffect` et
`MindControl_TaunterEffect` — les quatre à `Nullable<int>(1)`. (c) ne l'est que par
`HolyDuel_TauntEffect`. `HazeOfCorruption_DamageTransferEffect` porte les deux en CHAMPS
(`this+0x480` / `this+0x488`) que son ctor n'écrit pas ⇒ vide et faux.

## 3. Le gate `NOT AmountIsZero(BondedEntity)` MORD — et le littéral dit le contraire

`IdunBattleLogic.Entities.DSLTriggers$$AmountIsZero(selector)` construit
`NOT AmountIsGreaterAbilityTrigger(selector, <DSLFormulas+0x20>)`, et
`IdunBattle.Entities.Conditions.AmountIsGreaterAbilityTrigger$$ShouldTrigger` rend
`minAmount < amount`. Or `<DSLFormulas+0x20>` vaut **1** :

* `IdunBattleLogic.Entities.DSLFormulas$$.ctor` écrit `+0x18 <- Direct(0)`, `+0x20 <- Direct(1)`,
  `+0x28 <- Direct(2)`, `+0x30 <- Direct(100)`, `+0x38 <- Direct(-1)` ;
* `IdunBattleLogic.Entities.DSLTriggers$$AmountIsGreaterThanZero` lit `+0x18` — son nom colle donc
  à `minAmount = 0`, et `AmountIsZero` lit bien un AUTRE slot ;
* `IdunBattle.Entities.Effects.Loki.NeuroparasiteEffect$$GetIncreaseLevelBehaviour` passe
  exactement `+0x20` en 2e argument d'`IdunBattleLogic.Entities.DSLBehaviors$$IncreaseEffectLevel`
  (signature Frida : `effect, amount, max`), et #556 a **mesuré live** niveau 1 → 2.

Et `IdunBattle.Entities.Selectors.SelectBondedEntityFromEffectSelector$$Select` rend **au plus un**
élément : il prend `Enumerable.First` du sélecteur d'effet, lit le `BondedEntityId`, résout
l'entité, et passe par `IdunBattleLogic.Extensions.TExtensions$$ToList<T>` — dont le corps fait **un
seul** `List<T>.Add`, sans boucle. Sinon liste vide.

Littéralement, `AmountIsZero(x) == (count(x) <= 1)` serait donc toujours vrai sur ce sélecteur, et
les trois triggers structurellement morts.

**La mesure réfute cette lecture** (`--step killlive`, runner `MC1_67`, Neurothrope patché à 1000 PV,
victime à 400000 de dégât) :

| événement | parasite 1218 sur la victime |
|---|---|
| mort d'une unité **TIERCE** (`ultraCalgar`, notre camp) | **présent**, level 1 |
| mort du **BONDÉ** (le Neurothrope) | **absent** |

Le retrait n'est attribuable à aucun autre chemin :
`IdunBattle.Operations.RemoveEffectsOperation$$Execute` — la voie de
`IdunBattle.Operations.KillUnitOperation$$RemoveEffects` et de l'étape 14 de
`IdunBattle.Operations.RemoveUnitOperation$$Execute` — lit la liste d'effets sur le composant
d'effets de **l'unité qui meurt**, c'est-à-dire ceux qu'elle **porte**. Le parasite est porté par la
victime, qui survit. **Il n'existe aucun nettoyage natif « par SOURCE ».** Et le bras TIERCE ferme
la dernière échappatoire : ce n'est pas « n'importe quelle mort » qui retire.

⇒ Le port mirrore la sémantique **mesurée** : `NOT AmountIsZero(BondedEntity)` = « l'entité bondée
est encore résoluble dans l'état ». **Résidu `#462-r4b-r1-r1-r1-r1-r1`** : la réconciliation exacte
avec le littéral n'est pas tranchée. Elle ne change rien à ce qui est porté — sur les deux vecteurs
`On(2)` et `On(0x25)` le bondé est encore dans l'état (l'event part **avant** la consommation des
effets, cf. `remove_unit.py` étape 13), donc les deux lectures coïncident sur tout le confrontable.

## 4. Ce qui est porté

`scripts/python/engine/runner/operations/triggers/bond_removal.py` — **une seule** classe
`BondRemoveOnBondedEntityDeath` pour tous les `effect_type`, comme le natif (c'est la BASE qui
construit ce `Triggered()` pour toutes ses dérivées). `event_ids = (2, 37)` mirrore l'`op_BitwiseOr`
des deux `On()`. Frontière #149 : `CreateTrigger` collapse dans `matches`, le behaviour est l'arbre
`bond_removal_tree()` → feuille `RemoveEffect` → `remove_effect_instance`.

Le câblage de `EFFECT_TRIGGERS` se **dérive** de la table (`bond_removal_registry_entries`), il ne
s'écrit pas à la main : une entrée à `False` reste **documentée** dans la table sans inscrire de
trigger — côté natif le `Triggered()` n'entre pas dans l'`ArraySet`.

| `EffectType` | classe native | (a) | (b) | (c) |
|---|---|---|---|---|
| 1218 `Neuroparasite` | `NeuroparasiteEffect` | **True** | — | false |
| 1113 `TunnelingHorror_PendingSummon` | `TunnelingHorror_PendingSummonEffect` | **False** | — | false |
| 1077 `HazeOfCorruption_DamageTransfer` | `HazeOfCorruption_DamageTransferEffect` | **True** | — | false |

Le `False` de 1113 n'est pas une valeur inerte : le cast 1011 **retire son propre caster** du
plateau (`RemoveUnitFromItsTiles(Caster, true)`) et ce caster **est** le `bondedEntity`, donc
`On(0x25)` part sur le bondé dans le geste même qui pose le marqueur. Si le trigger était construit,
le kit s'auto-détruirait.

## 5. Validation — deux porteurs, deux valeurs OPPOSÉES du même virtuel

Confronter sur UN porteur ne prouve rien : un port qui retirerait tous les bonds — ou aucun —
passerait la moitié des lignes. `test_462_r4b_r1_r1_r1_r1_bond_removal_live.py` (4 verts) prend donc
les deux sens : **A** `Neuroparasite` (virtuel VRAI, effet PERMANENT donc rien d'autre ne peut le
faire disparaître) tombe à la mort du bondé et **pas** à celle d'une tierce, natif ET port, sur les
deux vecteurs ; **B** `TunnelingHorror_PendingSummon` (virtuel FAUX) survit au retrait de son bondé.
`test_462_r4b_r1_r1_r1_r1_bond_removal_offline.py` : 6 verts (table, câblage dérivé, les deux `On()`,
arbre inspecté comme OBJET — jamais par le texte du source, leçon #556 §3).

Contre-épreuves, toutes MORDANTES, arbre restauré :

| mutation | rouges |
|---|---|
| C1 — `Neuroparasite` `a=True -> False` | **2** (les deux vecteurs, côté port) |
| C2b — câbler TOUS les bonds (virtuel FAUX ignoré) | **1** (bras B) |
| C3 — conjoint `IsEntityWithIdTarget` retiré | **1** (le bras « mort TIERCE ») |

⚠ **C2b a d'abord été VERT**, et c'est ce qui a corrigé le test : le rejeu de
`unit_removed_triggers` sur 1113 est **vacuously vrai** — l'effet vit sur une TUILE et
`collect_effect_triggers` itère `effects.by_unit`. Un compteur d'instances avant/après s'y lisait
comme une mesure sans en être une. Le bras B assertionne désormais l'**absence au registre**, qui
rougit ; le rejeu reste joué comme non-régression, et le test le DIT.

Non-régression (39 verts) : `test_462_r4b_r1_r1_r1_neuroparasite_pose_live` (7),
`test_366_r1_tunneling_horror_live` (5), `test_haze_of_corruption_transfer_live` (9),
`test_haze_bonded_chain_live` (18).

## 6. NON CONFRONTÉS et résidus nommés

* **(b) `<klass+0x728> get_Range` et (c) `<klass+0x738> get_Adjacent` — NON CONFRONTÉS, non portés.**
  Le seul porteur que le port pose et qui les arme est la famille `Taunted`, et `--step gatelive`
  établit qu'elle est **inobservable** : le taunt de `CrushingClaws` (1105) est posé avec
  `TurnsFromRounds(1)` et tombe au **deuxième `endturn` sans que personne ne bouge**. Le premier jet
  du bras, qui déplaçait le taunté, mesurait en réalité la fin de son propre tour. Porter (b)/(c)
  serait du code que rien ne peut invalider.
* **Les 20 dérivées d'`IdunBattle.Entities.Effects.APendingAttackEffect` — NON RÉSOLUES**, dont
  `MalleusRocketLauncherEffect` (1308), `ValkyrieStrikeEffect` (1022) et `DevastatingRefrainEffect`
  (1402), tous trois POSÉS par le port. Elles héritent toutes de
  `APendingAttackEffect$$get_RemoveOnBondedEntityDeath`, dont le corps est `NOT <klass+0x778>()` :
  un **quatrième** virtuel, dont aucune vtable n'est matérialisée (slot NULL même runner vivant) et
  dont le nom n'est déductible d'aucune table. Elles ne sont pas sans retrait pour autant :
  `APendingAttackEffect$$CreateHandleTriggerAbilitiesInternal` ajoute son propre
  `Triggered( On(0x15) & IsTurnOf(<0x758>()), TriggerAbility(...) & RemoveEffect(Effect) )`.
  Pour trancher : matérialiser la vtable d'une dérivée en posant l'effet en bataille, puis
  `--step vtable --extra`.
* **`Taunted_BlockMovement` (25) et `Taunted_CantUseAbility` (26)** : la classe native qui les sert
  n'est pas établie. `IdunBattle.Entities.Effects.TauntedEffect$$.ctor` ne porte pas d'`EffectType`
  — il vient de la lambda d'`IdunBattle.Core.Services.EffectsDatabase$$InitializeEffects`, non lue.
  Les inscrire par ressemblance de nom serait une hypothèse : `EffectType.Taunted_OnlySpecificTargets`
  est servi par `TauntedEffect`, `EffectType.ValkyrieStrike_Effect` par `ValkyrieStrikeEffect` — la
  correspondance nom↔classe est irrégulière.
* Résidu `#462-r4b-r1-r1-r1-r1-r1` : le littéral `<DSLFormulas+0x20>` vs la sémantique mesurée (§3).
