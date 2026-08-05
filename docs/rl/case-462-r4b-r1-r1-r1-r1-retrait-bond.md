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
`unit_removed_triggers` sur 1113 est **vacuously vrai** — l'effet vit sur une TUILE, et aucun
effet-trigger de tuile n'atteignait alors son `matches`. Un compteur d'instances avant/après s'y
lisait comme une mesure sans en être une. Le bras B assertionne désormais l'**absence au registre**,
qui rougit ; le rejeu reste joué comme non-régression, et le test le DIT.
⚠⚠ **L'ATTRIBUTION écrite ici — « `collect_effect_triggers` itère `effects.by_unit` » — est FAUSSE,
et `#462-r4b-r1-r1-r1-r1-c-r1` l'a mesurée.** `by_unit` est clée par id d'**ENTITÉ**, tuiles
comprises : le collecteur instancie bien le trigger. C'était le **gate d'owner** de
`evaluate_trigger_operation` qui le jetait, parce que son critère était l'attribut de CLASSE
`owner_is_tile`. Le constat de vacuité reste juste ; sa cause était un étage plus bas.
Corrigé depuis : `case-462-r4b-r1-r1-r1-r1-c-r1-effets-de-tuile.md`.

Non-régression (39 verts) : `test_462_r4b_r1_r1_r1_neuroparasite_pose_live` (7),
`test_366_r1_tunneling_horror_live` (5), `test_haze_of_corruption_transfer_live` (9),
`test_haze_bonded_chain_live` (18).

## 6. NON CONFRONTÉS et résidus nommés

* ~~**(b) `<klass+0x728> get_Range` et (c) `<klass+0x738> get_Adjacent` — NON CONFRONTÉS, non
  portés.**~~ **RÉSOLU par `#462-r4b-r1-r1-r1-r1-b` — voir §8.** L'énoncé « inobservable » était
  vrai du seul montage tenté (déplacer le taunté, ce que `Taunted_BlockMovement` interdit de toute
  façon) ; il tombe dès qu'on **déplace de force** dans le tour du cast.
* **Les 20 dérivées d'`IdunBattle.Entities.Effects.APendingAttackEffect` — RÉSOLUES par
  `#462-r4b-r1-r1-r1-r1-c`.** Voir §7.
* **`Taunted_BlockMovement` (25) et `Taunted_CantUseAbility` (26)** : la classe native qui les sert
  n'est pas établie. `IdunBattle.Entities.Effects.TauntedEffect$$.ctor` ne porte pas d'`EffectType`
  — il vient de la lambda d'`IdunBattle.Core.Services.EffectsDatabase$$InitializeEffects`, non lue.
  Les inscrire par ressemblance de nom serait une hypothèse : `EffectType.Taunted_OnlySpecificTargets`
  est servi par `TauntedEffect`, `EffectType.ValkyrieStrike_Effect` par `ValkyrieStrikeEffect` — la
  correspondance nom↔classe est irrégulière.
* Résidu `#462-r4b-r1-r1-r1-r1-r1` : le littéral `<DSLFormulas+0x20>` vs la sémantique mesurée (§3).

## 7. `#462-r4b-r1-r1-r1-r1-c` — le quatrième virtuel : `IsExecutedIfOwnerDies`

`APendingAttackEffect$$get_RemoveOnBondedEntityDeath` ne rend pas une constante — son corps est
`NOT <klass+0x778>()`. Ce virtuel est **`IsExecutedIfOwnerDies`**, et la sous-famille en tire son
gate (a). Le nom n'est déductible d'**aucune** table : `IsExecutedIfOwnerDies` n'apparaît dans aucun
symbole ghidra, parce que les 20 corps sont des `return 0`/`return 1` **dédupliqués**.

### 7.1 Pourquoi la passe précédente s'est arrêtée — un balayage DÉSALIGNÉ

Le §6 disait « slot NULL même runner vivant ». C'était un **artefact de mesure** : le pas balayait
`0x750..0x790` **par pas de 0x10**, alors que les slots sont alignés sur `...8`
(`0x728/0x738/0x748/0x758/0x768/0x778`). Il tombait à côté de **chacun**, et ses cases vides se
lisaient comme une absence de matérialisation. Un balayage aligné montre l'inverse : la vtable de
`SeekerMissileFrequencyLockTargetEffect` était **déjà** matérialisée dans la session, et le nom se
lisait sans rien monter.

⇒ **Sur un balayage de slots, l'alignement du `start` fait partie de la mesure.** Une plage vide
n'est une absence que si l'on a d'abord prouvé que la plage tombe sur les slots. Le pas porte
désormais ce **contrôle d'alignement** : `+0x758` et `+0x768` doivent rendre
`GetAttackingUnitSelector` et `GetTriggeredAbilityType`, que `methods.tsv` nomme indépendamment ;
désalignement ⇒ `rc 2`, aucune valeur rendue.

Second piège, corrigé dans le même pas : le critère de matérialisation est le **`MethodInfo*`**
(donc le nom), **pas** le pointeur de code. Une classe non initialisée porte le stub de remplissage
paresseux à une adresse bien réelle avec un `MethodInfo*` nul — prendre l'adresse pour critère fait
passer la base abstraite pour lisible, et son slot vide pour un désalignement.

### 7.2 La mesure — deux voies concordantes, `--step pending`

`class_get_methods` (ne dépend d'aucune initialisation, couvre les 20) et la **vtable** (ne répond
que pour les classes matérialisées, mais seule à établir le lien slot ↔ nom). Les deux **concordent**
sur chaque classe matérialisée, en adresse **et** en nom.

Les 20 dérivées **déclarent toutes** `IsExecutedIfOwnerDies` en propre : **17 à `false`** (donc
`get_RemoveOnBondedEntityDeath` **VRAI**) et **3 à `true`** — `AnnihilatorBeam_PendingAttackEffect`,
`TargetingProtocols_PendingAttackEffect`, `ValkyrieStrikeEffect`.

`APendingAttackEffect` **surcharge par ailleurs** `get_Range` (`Nullable` vide) et `get_Adjacent`
(`false`) : **ni (b) ni (c) sur aucune des 20**.

### 7.3 L'attribution `EffectType` ↔ classe native, établie par MESURE

La ressemblance de nom ne prouve rien (§6). L'attribution est ici mesurée par **bascule de vtable** :
poser l'effet en bataille initialise sa classe, et **elle seule** passe de non matérialisée à
matérialisée. Les 19 autres restent NULL à chaque pas — c'est le contrôle.

| `EffectType` | ability / porteur | classe native (MESURÉE) | `IsExecutedIfOwnerDies` | `RemoveOnBondedEntityDeath` |
|---|---|---|---|---|
| 1308 `MalleusRocketLauncher` | 1142, `astraOrdnanceBattery` (MoW) | `MalleusRocketLauncherEffect` | **false** | **TRUE** |
| 1402 `DevastatingRefrain_Target` | 1188, `adeptExorcist` (MoW) | `DevastatingRefrainEffect` | **false** | **TRUE** |
| 1022 `ValkyrieStrike_Effect` | 1018, `astraSmnVoxcaster` (summon) | `ValkyrieStrikeEffect` | **true** | **FALSE** |

### 7.4 Verdict sur le port

* **1022 — CONFORME, et CONFRONTÉ.** Le natif ne construit **aucun** trigger (a) ; le port n'en
  inscrit aucun. C'est le seul des trois dont le bondé (le caster) soit une **unité tuable**, donc le
  seul confrontable — et il l'est dans le **sens rare** : `--step valkyrielive` mesure bondé mort,
  **1022 encore présent**. Ce bras vaut aussi **contre-épreuve de la table `TRIVIAL`** du probe, par
  laquelle les 19 autres valeurs sont lues. L'entrée est **dans** `BOND_REMOVAL_GATES` (à `False`),
  pour documenter le non-retrait : le câblage se dérive, donc **aucun trigger inscrit**.
* **1308 et 1402 — le trigger (a) est CONSTRUIT côté natif, et NON CONFRONTABLE.** Leur
  `bondedEntity` est l'`owner` du cast, c'est-à-dire une **Machine of War**. Mesure
  (`--step pendingporteurs`) : entité de type `Machine`, `pos = None`, `hp = None`, absente de
  `decisionView.units`, cible légale d'**aucune** attaque. **Sa mort n'est pas atteignable.**
  Une raison structurelle s'y ajoute, suffisante à elle seule : leurs call-sites ne passent pas
  `bonded_ref`, donc `BaseEffect.bonded` reste `None` et `matches` rendrait `False`. Les inscrire
  produirait du code **doublement inerte**, invalidable — ce que la doctrine proscrit. Ils restent
  **hors table**, par mesure et non par prudence.
  ⚠ **Une TROISIÈME raison était invoquée ici — « ces effets vivent sur des TUILES alors que
  `collect_effect_triggers` itère `effects.by_unit` » — et elle est LEVÉE** (`#462-r4b-r1-r1-r1-r1-c-r1`).
  Le collecteur voyait déjà les tuiles ; c'était le gate d'owner du dispatch, corrigé depuis. Le
  verdict NON CONFRONTABLE ne change pas : il tenait déjà sur chacune des deux autres raisons.

⚠ **Ces trois effets ne sont pas sans retrait, et l'autre foyer MORD.**
`APendingAttackEffect$$CreateHandleTriggerAbilitiesInternal` ajoute
`Triggered( On(0x15) & IsTurnOf(<0x758>()), TriggerAbility(...) & RemoveEffect(Effect) )` — la
frappe différée, qui s'auto-consomme. Mesuré : **un seul `endturn` après le cast fait disparaître
1022 de sa tuile sans qu'aucun bondé ne soit mort.** C'est ce qui a d'abord fait échouer le bras, et
c'est ce qui rend le gate (a) doublement sans conséquence pour cette sous-famille. Le bras s'interdit
donc tout `endturn`, et **déplace le bondé** (spawné sur un point du groupe adverse, `playerId`
inchangé) plutôt que de subir la géométrie.

### 7.5 Gardes et résidu

`assert_pending_gate_consistency()` tient `remove_on_bonded_entity_death == NOT
is_executed_if_owner_dies` — les deux champs sont redondants **exprès**, et c'est la redondance qui
les garde. Contre-épreuve jouée : le garde mord. Tests offline **6 → 9 verts** ; non-régression
**12 verts** (`bond_removal_live` 4, `neuroparasite_pose_live` 7, `valkyrie_strike_migration_live` 1).

**Résidu `#462-r4b-r1-r1-r1-r1-c-r1` — RÉSOLU (2026-08-05),
`case-462-r4b-r1-r1-r1-r1-c-r1-effets-de-tuile.md`.** Le trou existait, mais **pas où on l'accusait** :
`collect_effect_triggers` VOIT les effets de tuile (`by_unit` est clée par id d'ENTITÉ) ; c'était le
**gate d'owner** de `evaluate_trigger_operation` qui les jetait, son critère étant l'attribut de
CLASSE `owner_is_tile` là où la nature du porteur est une propriété de l'INSTANCE. Côté natif, le
seul discriminant est `IdunBattle.Entities.EntityExtensions$$IsUnit` — et sur la face EFFET il n'y a
**aucun** gate du tout (`CanGetEffectTrigger` s'ouvre sur un corps dédupliqué `return 1`). Le port
mirrore désormais `IsUnit` par la négative. **Le trou est LATENT et ça se mesure** : aucun
`effect_type` porté par une tuile n'est servi par une classe nue (mesuré live et sur le registre),
ce qui est exactement ce qui l'a masqué trois fois. Résidu ouvert en aval :
**`#462-r4b-r1-r1-r1-r1-c-r3`** (les deux gates d'owner que le port garde encore sur la face EFFET,
et que le natif n'a pas).

**Non couvert, et nommé** : les **17 autres dérivées** à `RemoveOnBondedEntityDeath = TRUE`. Leur
valeur est mesurée, mais leurs abilities ne sont pas portées dans `engine/` — donc ni porteur
recensé, ni confrontation. Ce n'est pas un trou du port : c'est du kit non porté.

## 8. `#462-r4b-r1-r1-r1-r1-b` — (b) `get_Range` porté, (c) `get_Adjacent` mesuré

### 8.1 Ce qui a débloqué la confrontation : ne consommer AUCUN tour

Le §6 concluait « inobservable » sur un montage unique — déplacer le taunté. Deux verrous s'y
opposent, et le second n'avait pas été nommé : la durée `TurnsFromRounds(1)` du taunt tombe au
deuxième `endturn`, **et** le composite pose `Taunted_BlockMovement` (25) sur sa cible — le taunté
**ne peut pas marcher**. Le mouvement volontaire est donc structurellement fermé.

Le montage qui tranche n'attend aucun tour et ne fait marcher personne : une **seconde unité du
même camp** caste `MortisRound` (1004, `ultraEliminatorSgt`), dont l'arbre porte
`PushUnit(Caster(), Target())`. Le déplacement **forcé** apporte les deux ingrédients du trigger
d'un coup — `IdunBattle.Operations.DisplaceUnitOperation$$EventAndAbilitiesAndEffects` publie
`On(0x24)` → `On(0x23)` → **`On(0x1d)`** puis `RefreshEffects(7)`, et la distance change.

**Le discriminant est la GÉOMÉTRIE, pas un paramètre.** Le push envoie le taunté en `V - e` (à
l'opposé du pousseur), donc `dist(V - e, T) = |e + t|` où `T = V + t` est le taunteur :

| pousseur | `|e + t|` | attendu |
|---|---|---|
| à **1 cran** de `t` (adjacent au taunteur) | **2** | hors portée (`get_Range = 1`) |
| à **2 crans** | **1** | encore à portée — **le CONTRÔLE** |

Les deux bras jouent le même cast, le même push, la même attaque : une tuile de différence.
Le placement des DEUX camps est explicite (`--a-place` : l'unité quitte `BC.PredefinedUnits` pour
les `playerUnits` d'`initAndStart` avec `playerId = PLAYER_ID_AI`) — le spawn natif de `MC1_67`
posait la victime sur une tuile de bord à **deux** voisins jouables, où aucune des deux
configurations n'existe.

### 8.2 La mesure — (b), les deux faces

`probe_462_r4b_r1_r1_r1_r1_b_bond_range.py --step rangelive` (board `MC1_67`, `tyranTyrantGuard` +
`ultraEliminatorSgt` vs `blackPossession` à 400 000 PV, **aucun `endturn`**) :

| bras | dist | NATIF | PORT (avant) | PORT (après) |
|---|---|---|---|---|
| ELOIGNE | 1 → **2** | `[25,26,27,1237]` → **`[]`** | inchangé | **`[]`** |
| PROCHE | 1 → **1** | inchangé | inchangé | inchangé |

Le port était donc **faux dans un sens permissif** : un taunt poussé hors de portée survivait, et
avec lui `ForcedAttackTargets`, `Taunted_BlockMovement` et `Taunted_CantUseAbility` — une unité
contrainte à vie, sans erreur ni crash.

**C'est le PARENT qui tombe** : les trois sous-effets partent avec lui. Si seul
`Taunted_RefreshUnitTurnFinishedEffect` (1237) avait porté le trigger, 27 serait resté. La mesure
**attribue** donc `EffectType 27` à une classe qui arme (b), et parmi les quatre c'est
`TauntedEffect` — la seule dont `ApplyInternal` pose ces trois sous-effets **et** la liste de
cibles forcées (#436).

⚠ **La bascule de vtable (§7.3) est inutilisable ici** : les six classes de la famille étaient
**déjà matérialisées** avant tout cast (session partagée, runners d'autres agents). Le pas
`--step attrib` existe et le **dit** au lieu de rendre un verdict vide.

### 8.3 Trois défauts trouvés, tous MESURÉS — le trigger seul n'aurait rien fait

1. **Le trigger (b) n'existait pas** → `BondRemoveOnRangeExceeded` (`On(0x1d)`,
   `distance(owner, bonded) > range`).
2. **`displace_triggers` n'émettait PAS `On(0x1d)`** — le port le flaggait « concern séparé, non
   validé ». Sans lui, le trigger ne se réveille jamais sur un push. Contre-épreuve C2 : **2 rouges**.
3. **`remove_effect_instance` ne retirait pas les SOUS-EFFETS.** `RemoveEffectOperation$$Execute`
   appelle `$$RemoveSubEffects` (copie de `EffectComponent.SubEffects@+0x78`, `RemoveEffect`
   récursif sur chacun), et le port n'avait cette cascade que dans `EffectsState.on_turn_end`
   (expiration par TIMER). Tout retrait **anticipé** laissait les enfants derrière lui — mesuré :
   le trigger retirait le 27 et `[25, 26, 1237]` restaient. C'est un défaut **antérieur** à ce
   résidu, révélé par lui.
4. Corollaire de (3) : sur un état **hydraté**, `parent_type` n'était écrit par personne — les deux
   consommateurs du lien devenaient muets. `snapshot._load_effect_parent_links` le **reconstruit**
   depuis la même part DATA que la pose (`sub_effects_on_apply()`), l'attribution étant unique
   puisqu'`AddEffectOperation` garantit au plus une instance non consommée d'un type par unité.

### 8.4 (c) `get_Adjacent` — mesuré au NATIF, rien à porter

`IdunBattleLogic.Entities.Abilities.Active.Loki.HolyDuelAbility$$ExecuteBehaviour` (1050) :

```
Execute( AddBondEffect(0x443 = 1091 HolyDuel_Taunt, AbilityStateReference,
                       source = Caster@0x48, targets = Target@0x60,
                       bondedEntity = Caster@0x48, options VIDES)
         & UseActiveAbility(caster, target, UnitNormalAttackType(caster), ...) )
```

Le porteur `templChampion` **est au pool** (rank 17) — la gate de confrontabilité passe, malgré les
5 npc `templBossChampion*` qui l'accompagnent. Même montage, `--step holyduel` :

| bras | dist | 1091 |
|---|---|---|
| ELOIGNE | 1 → 2 | présent → **absent** |
| PROCHE | 1 → 1 | présent → présent |

Options **vides** ⇒ le bond est **permanent** (`remaining = 0`) : aucune durée ne peut expliquer la
disparition, contrairement au taunt de `CrushingClaws`. La mesure est donc plus propre que celle
de (b).

`IdunBattleLogic.Entities.DSLTriggers$$IsAdjacent` construit
`IdunBattle.Entities.Triggers.IsAdjacentAbilityTrigger`, dont le ctor est
`(selector1, selector2, selectionType, query)` — **le `0x3` du call-site est le `selectionType`
passé aux deux `Select`, PAS un rayon** ; `$$ShouldTrigger` teste `query.IsAdjacent(a, b)` sur
toutes les paires, et rend `false` si l'un des ensembles est vide.

**PORT : rien à porter, et le test le DIT.** L'ability 1050 n'est pas dans `ABILITY_CLASSES`, donc
1091 n'est **jamais posé** offline : un trigger (c) serait vacuement vrai (le piège du §5). 1091
n'entre donc PAS dans `BOND_REMOVAL_GATES` — la table ne contient que des effets que le port pose.
`test_c_le_port_ne_pose_pas_1091_donc_ne_porte_aucun_trigger_c` **rougira** le jour où 1050 sera
portée, et c'est ce jour-là qu'il faudra écrire `BondRemoveOnAdjacencyLost`.

### 8.5 (a) sur l'effet 27 — l'effet de BORD, confronté lui aussi

`TauntedEffect$$get_RemoveOnBondedEntityDeath` vaut **`true`**. Faire entrer 27 dans la table
inscrit donc AUSSI (a), et livrer un câblage non confronté n'est pas acceptable. Vecteur :
le friendly-fire de `FragBomb` (1017, `astraBullgryn`, **tile-target**), dont le splash
`AdjacentUnits(Target) - Caster` inclut les **alliés**. Les deux bras ne diffèrent que par les PV
du taunteur (`--step deathlive`) :

| taunteur | NATIF | PORT (`On(2)` rejoué) |
|---|---|---|
| 1 PV → **mort** | `[25,26,27,1237]` → **`[]`** | mort du BONDÉ → **`[]`** |
| 400 000 PV → vivant | inchangé | mort d'une TIERCE → inchangé |

### 8.6 Validation

`test_462_r4b_r1_r1_r1_r1_b_bond_range_live.py` : **8 verts** (les trois bras, contrôles inclus).
`test_462_r4b_r1_r1_r1_r1_bond_removal_offline.py` : **9 → 16 verts**.

Contre-épreuves, toutes MORDANTES, arbre restauré :

| mutation | rouges |
|---|---|
| C2 — `On(0x1d)` retiré de `displace_triggers` | **2** |
| C3 — `range = 2` au lieu de 1 | **5** (dont 2 comportementaux) |
| C4 — `_remove_sub_effects` neutralisé | **5** |
| C5 — `_load_effect_parent_links` neutralisé | **4** |

Non-régression : **49 verts** offline (`436r1_bond_channel`, `366_r1_tunneling_horror_*`,
`462_r4b_r1_r1_r1_neuroparasite_pose`), **12 verts** sur le vecteur push
(`thunderous_assault_push`, `mortis_round`, `rad_saturation`, `decoys_misdirection_migration`).

### 8.7 Non couverts, nommés

* **`BlockUnitMovementBondEffect` et `MindControl_TaunterEffect`** arment (b) à `Nullable<int>(1)`,
  mais leurs `EffectType` ne sont **pas établis** et le port ne pose aucun de ces effets. Rien à
  porter ; la valeur est mesurée, elle attend son porteur.
* **`Taunted_RefreshUnitTurnFinishedEffect`** (1237) arme (b) en propre. Le port pose bien 1237,
  mais comme **sous-effet** — sans `bondedEntity` (le natif non plus : `AddSubEffectWithSameTurns`
  ne passe pas de bond). Son `Triggered()` est donc construit côté natif et sans effet : le
  sélecteur de bond rend une liste vide. Non porté, non confronté.
* **Résidu `#462-r4b-r1-r1-r1-r1-b-r1`** : `IdunBattle.Entities.Triggers.IsAdjacentAbilityTrigger`
  prend un `selectionType` en 3ᵉ argument, **pas un rayon** — or `triggers/loki/narthecium.py` et
  `tainted_narthecium.py` portent `IsAdjacent(self, target, 2)` comme `distance <= 2`
  (`ADJACENCY_RANGE = 2`). Les deux nœuds sont peut-être distincts (un FILTRE `DSLFactory` vs ce
  TRIGGER) et la question n'a **pas** été tranchée : elle est hors du périmètre de ce résidu, et
  aucune mesure n'a été faite dessus ici. Si le 3ᵉ argument y est aussi un `selectionType`, les
  deux revives natifs exigent l'**adjacence stricte** et le port est permissif d'un hex.
