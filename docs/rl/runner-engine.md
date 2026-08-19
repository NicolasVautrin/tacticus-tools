# Runner engine — port Python fidèle du moteur de bataille natif

> **But** : reproduire en Python le **runner de bataille** de Tacticus (application
> des actions → mutation d'état → cascade d'events/triggers/effets), à côté du
> moteur de prédiction/playbook déjà porté. Fidèle (decompile = vérité, structure
> 1:1, VA citées) ET modifiable (changer une règle au bon endroit, comme le jeu).
>
> **Méthodologie** (cf. [[feedback_tests_confront_live]] + CLAUDE.md) : RE ghidra
> d'abord, **validation par agrément vs LIVE** brique par brique (replay-diff :
> rejouer la même séquence de messages sur le runner live ET le runner Python,
> diff de l'état après chaque pas). Aucun snapshot gelé, indépendant version/seed.

Build de référence : **gqfc5mff6c**. Toutes les VA ci-dessous en sont issues.

---

## 1. Architecture native (confirmée)

### 1.1 `IdunRunner` — pipeline `Apply`

`IdunBattle.Runner.IdunRunner$$Apply` **@180e34bf0**. Layout objet :

| offset | champ |
|---|---|
| `+0x20` | `state` (l'état ECS de la bataille) |
| `+0x80` | `preHandlers` : `List<IMessageHandler>` |
| `+0x88` | `postHandlers` : `List<IMessageHandler>` |
| `+0xb8` | `recorder` (journalise le message — base du Replay) |

```
Apply(this, msg):
  currentPlayer = StateExtensions.GetCurrentPlayerId(state@0x20)
  if ShouldBlockMessage(this, msg, currentPlayer):  return        # @ IdunRunner$$ShouldBlockMessage
  if ShouldRejectMessage(this, msg):                return        # @ IdunRunner$$ShouldRejectMessage
  for h in preHandlers@0x80:   h.<ifaceSlot>(msg, state, currentPlayer)   # PRE
  record(msg)  @0xb8                                                       # FUN_180003bd0
  for h in postHandlers@0x88:  h.<ifaceSlot>(msg, state, currentPlayer)   # POST
```

Le dispatch handler = recherche du slot de méthode d'interface dans la vtable
(tokens `DAT_1831ccf30` pour pre, `DAT_1831cd068` pour post). **Gate → PRE →
record → POST.** Un message bloqué/rejeté = no-op (rien n'est journalisé).

### 1.2 Messages = pattern Visiteur

`IdunBattle.Messages.*Message` = **data + `Accept(visitor)`**. Le handler est un
visiteur ; `Accept` route vers son `Visit(<typeMessage>)`, qui lance des Operations.

Exemples : `MoveUnitMessage` (`get_To` @180ebef20), `CheatMoveUnitMessage`,
`RemoveUnitMessage`, `ActiveAbilityMessage`, `FinishUnitTurnMessage`,
`EndTurnMessage`, `CheatRunAIMessage`. (Catalogue complet = `*Message$$Accept`.)

### 1.3 Operations = mutateurs atomiques de l'ECS (~80)

`IdunBattle.Operations.*Operation$$Execute` — chaque `Execute` mute des composants.
Catalogue groupé (VA = `$$Execute`) :

- **Mouvement** : `MoveUnitOperation` @180e79ff0, `SetUnitPositionOperation`
  @180e94ec0, `DisplaceUnitOperation` @180e685a0, `RemoveUnitFromTilesOperation`
  @180e8a620, `OverrideMovementTargetOperation` @180e7fae0.
- **Dégât** : `DealDamageOperation` @180e65d20, `ApplyDamageOperation` @180e5a540,
  `AttackDamageOperation` @180e60c70, `AbilityDamageOperation` @180e2adc0,
  `DirectDamageOperation` @180e677f0, `MachineDamageOperation` @180e78770,
  `ExecuteAdditionalHitsWithDamageProfileTypeOperation` @180e70600,
  `DiscardHitOperation` @180e67da0.
- **Attaque (flow)** : `StartAttackOperation` @180ea2380, `FinishAttackOperation`
  @180e71310, `AttackTileOperation` @180e61810.
- **Soin / vie** : `HealUnitOperation` @180e733d0, `RepairUnitOperation` @180e8b820,
  `ResurrectUnitOperation` @180e8e4c0, `KillUnitOperation` @180e76470,
  `RemoveUnitOperation` @180e8add0, `CreateShieldOperation` @180e64cd0.
- **Effets** : `AddEffectOperation` @180e48940, `RemoveEffectOperation` @180e870d0,
  `ChangeEffectTurnsOperation` @180e61c80, `RefreshEffectsOperation` @180e83f60,
  `ActivateEffectOperation` @180e446b0, `DeactivateEffectOperation` @180e65bd0,
  `IncreaseEffectLevelOperation` @180e73cb0, `DecreaseEffectLevelOperation` @180e66720.
- **Abilities / traits / stats** : `AddActiveAbilityOperation` @180e47e40,
  `AddTriggeredAbilityOperation` @180e51cb0, `TriggerTriggeredAbilityOperation`
  @180eac630, `ChangeAbilityCooldownOperation` @180e61960, `AddTraitOperation`
  @180e51830, `AddOrRemoveMultiStatOperation` @180e4d200, `AddUnitBonusOperation`
  @180e52520.
- **Triggers (cascade)** : `EvaluateTriggerOperation` @180e6fac0 (.Execute différé)
  / @180e6fd60 (variante) ; `ExecuteImmediately` @180e6ec90 (inline) ;
  `ExecuteInternal` @180e6ef40 (dispatch listeners triés).
- **Tour / phases** : `EndTurnOperation` @180e6b3c0, `ChangeTurnOperation` @180e62370,
  `EndPhaseOperation` @180e6a0f0, `ContinueTurnPhaseOperation` @180e64890,
  `PickUnitOperation` @180e80ce0, `FinishUnitTurnOperation` @180e72140,
  `FinishAllCurrentPlayerUnitTurnsOperation` @180e70e30,
  `PlayAutomaticUnitsOperation` @180e81120, `RunComputerActionsOperation` @180e93e80.
- **Spawn / setup** : `AddUnitOperation` @180e534f0, `SpawnUnitsOfTurnOperation`
  @180e9fd50, `AddPlayerOperation` @180e4d840, `InitializeMatchOperation` @180e76060,
  `InitializeActorAbilitiesOperation` @180e74660.
- **Divers** : `AtomicGroupOperation` @180e5e200 (groupe atomique), `InformOperation`
  @180e745f0, `InvalidateCachesOperation` @180e76240, `FinishMatchOperation` @180e71a80.

### 1.4 ECS — entités & composants

Entités accédées dans `Apply` via la table de composants : `entity+0xb0` = tableau
de composants `{typeToken, slotIndex}` (paires de 0x10), `entity+0x12e` = nombre de
composants, `entity+0x138` = base des slots. Ajout : `Entity$$AddComponent`
**@181006990**. Composants connus : `UnitFootComponent` (UnitId@0x10, TileId@0x14 ;
position id @+0xa8..0xb4 écrite par MoveUnitOperation), `UnitFlagsComponent`
(`Add` flag), `TriggeredAbilityComponent`, `EffectComponent`/`EffectsOwnedComponent`,
`ActiveAbilityComponent` (NormalAttackType@0x28). **TODO** : RE précis de la struct
Entity + table des composants (layout exact) avant de figer le modèle ECS Python.

### 1.5 Cascade = pile LIFO (inline) + file FIFO (différé)

- **Immédiat** : `EvaluateTriggerOperation.ExecuteImmediately` @180e6ec90 → inline,
  profondeur d'abord (call-stack = LIFO).
- **Différé** : `EvaluateTriggerOperation.Execute` @180e6fac0 → enfile un `BattleEvent`
  sur le bus `Events` (`get_Events` @180ffa4a0), traité plus tard (FIFO).
- Résultat = **arbre** de groupes, **déjà capturé** par `apply-stack.ts`
  (`StreamDispatcher.Action/StartGroup/FinishGroup`) → tables `stream_group`
  (parent/depth/ordinal) + `stream_event`. `FinishGroup()` paramless = discipline
  de pile. Phases différées « système » taggées par GroupType :
  `System_ProcessDeaths`(5), `System_ProcessRemovals`(6), `System_StartTurn`(9),
  `SpawnUnitsOfTurn`(24)/`Wave`(25) — exécutées en post-handlers.

### 1.5bis Le PUMP DSL — `proc = OperationProcessor` (RE #200/#149, re-expert 2026-07-17, VAs prouvées)

Précise le mécanisme exact sous 1.5 (issu du confront live #199 : le tracer d'exécution ne voyait rien
car l'exécution passe par dispatch d'interface, pas par les méthodes concrètes `*Behaviour.Execute`).

- **`proc`** (threadé dans toute la récursion des behaviours, dernier arg de `*Behaviour.Execute`) =
  une instance de **`Core.Services.OperationProcessor`** = un **SAC d'Operations pré-allouées** (1 par
  champ : `+0x70`=AddUnitOp, `+0x2a0`=AdditionalHitsOp, `+0x388`=AtomicGroupOp…). Obtenu via
  `AOperation.get_Events` @180ffa4a0 dans `ActiveAbilityOperation.ExecuteInternal` @180e44ec0.
- **Une feuille émet une Operation par appel de slot d'interface SYNCHRONE** (résolu par les helpers de
  dispatch génériques `FUN_1801e40c0` = slot dans `klass+0xb0`/`+0x138`, puis `FUN_1800291d0`/`180002560`/
  `180003bd0` = invoke). Ex. `SpawnUnitBehaviour.Execute` @180fd3d80 → `proc.slot+5` = **`OperationProcessor.AddUnit`
  @180e06f30** → **`AddUnitOperation.Execute()` INLINE**. **Aucune Operation n'est enfilée** : chaque
  méthode du proc = « configure l'Operation pré-allouée + `.Execute()` tout de suite ».
  ⇒ **Operations = LIFO inline, PAS de file** (la récursion des behaviours = la pile). **Le port fait DÉJÀ
  ça** (appels directs aux Operations) → fidèle par construction ; NE PAS ajouter de file d'Operations.
- **AtomicGroup N'EST PAS différé** : `AActiveAbility.ExecuteAtomic` @180fb0930 → `DSLFactory.AtomicGroup`
  @180de9490 = `proc.slot+0x7c` = **`OperationProcessor.CreateAtomicGroup` @180e073f0** →
  **`AtomicGroupOperation.Execute` @180e5e200 INLINE** : ouvre le groupe (`state.BeginAtomic` slot+0x14),
  **invoque le callback** `AtomicGroupBehaviour.<Execute>b__0` @180fd9390 = exécute le behaviour interne
  (le Spawn) **ici, synchrone** → les `AddUnit` sont émis maintenant ; ferme ; mini-drain FIFO local au
  groupe (`state` dequeue slot+10). ⇒ **ordre GetEmRuntz PROUVÉ : `ExecuteAtomic(Spawn)` inline (grots
  matérialisés) PUIS `Execute(op_Addition(PerformAIAttack, Foreach))`** — les grots existent avant que
  `PerformAIAttack` itère `Cache(GetSpawnTileSelector)`. Le port `Seq(spawn, Seq(attack, taunt))` respecte
  cet ordre.
- **Le SEUL vrai différé du moteur = plan Messages/Events FIFO** : les Operations poussent des Messages
  dans des files du state (`Queue` de *pending triggered abilities*, collection de *damage events*), drainées
  en FIFO par **`InputMessageProcessor.RunPhase` @180ebaa80** → `ProcessDamageEvents` @180eba4f0 +
  `ProcessPendingTriggeredAbilities` @180eba680 (copie Queue→List, **`Queue.Clear`**, puis PAR ITEM FIFO
  relance `RunPhase`). C'est ce plan que le port **collapse en appels directs** (`Runner.apply` non
  ré-entrant) → **gap de fidélité pour l'ORDRE des chaînes de triggers / cascades de dégât** (cf. #140/#147 ;
  neutre pour GetEmRuntz). Voir tâche dédiée.
- **Points OUVERTS** (re-expert) : (1) `proc` des behaviours == `InputMessageProcessor+0x18` ? (même
  interface, très probable, non tracé bout-à-bout) ; (2) sémantique fine des slots de state
  `DAT_1831cbde8` (BeginAtomic/dequeue/pending/damage) lue par usage ; (3) lien `RunPhase` ← `IdunRunner.Apply`
  @180e34bf0 non re-tracé.

### 1.6 Triggers (observateur réactif, indexé par event, trié)

`BaseTriggeredAbility` (~573 types = enum `passive_ability_type`) : `CreateTrigger`
(condition DSL `On(event) & conds`) + `Execute` (comportement) + `AbilityStateReference`
@180fbcbe0 (cooldown/once). Stockés par entité (`TriggeredAbilityComponent`, via
`AddTriggeredAbilityOperation.Execute` @180e51cb0 → TryAdd). Enregistrés **triés**
dans `AbilityAndEffectCache` (event_type → listeners ; `AddSorted` @18128ab10 /
`AddAbilityOrEffect` @180e27880). Dispatch : `ExecuteInternal` @180e6ef40 (itère les
listeners triés). Éval : `EvaluateAbilityOrEffectTrigger` @180e6d250 (type-check
effet/ability, condition, immédiat/différé via param_5, fire → cascade). Les effets
portent aussi des triggers.

### 1.7 RNG — MT19937 (PORTÉ + validé)

`IdunBattle.Utils.PRNG.MersenneTwister`/`IntBasedMersenneTwister` = MT19937 **standard
confirmé bit-pour-bit** au décompilé. Porté : `engine/runner/prng.py`.
- `init_genrand` @180e3a750 (mult `0x6c078965`) ; `genrand_int32` @180e3a3e0
  (twist UPPER/LOWER, M=397, MATRIX_A `0x9908b0df`, tempering std ; seed défaut 5489) ;
  `genrand_real2` @180e3a6b0 = `(g>>2)/2^30` (jeu en Fix64 ; port en float — pour le
  bit-exact entier préférer les Next).
- `IntBasedMersenneTwister.NextInternal(lo,hi)` @180e39be0 [lo,hi) & `Next(bound)`
  @180e394e0 [0,bound) : range puissance-de-2 → `((range*(g>>1))>>31)+lo` ; sinon
  rejet façon Java nextInt. Compteur d'appels @+0x14, mti @+0x28, mt[] @+0x20.
- **Validé** `tests/engine/runner/test_prng.py` (5/5) : vecteur canonique mt19937ar
  + **MT19937 stdlib Python** (réf indépendante, 200 tirages) + seed défaut 5489 +
  bornes Next. Wrappé `DisallowablePseudoRNG` (gate) côté natif ; combat via `IPseudoRNG`.
- **RPC `dumpRng`** (BUILT, `rpc-view.ts`) : lit l'état MT natif. RE
  `IdunRunner.Initialize` → le RNG de combat (IntBasedMersenneTwister) est sur le
  **runner @0x38** (passé à DSLFactory.ctor → DisallowablePseudoRNG@+0x18→inner@+0x10).
  Retourne `{mt:[624], mti, callCount}` (garde-fou len==624). Test
  `tests/engine/runner/test_rng_dump_live.py` : dump AVANT → coup consommant du RNG →
  dump APRÈS → le MT Python avance de l'état-avant et **retrouve exactement** l'état-après
  (bit-exact vs binaire live). ✅ **VALIDÉ LIVE 2/2** (session 36) : le port MT reproduit
  la consommation RNG du binaire bit-pour-bit. Suite totale 20 passed + 1 xfail (1b).
- ⏳ Bridge overwatch bit-exact : dumpRng avant le move → sync MT Python → rejouer la
  cascade overwatch (attaque normale du watcher via engine/predict, tirage exact) →
  Δhp Python == 1174 live (xfail 1b → xpass).

### 1.8 Chemin de dégât de COMBAT (RE'd — ≠ prédiction)

**Le combat réel n'est PAS `GetAttackPrediction`.** Les deux passent par le MÊME
service (`IDamagePrediction`, token `DAT_183287ef8`) mais par des **méthodes
différentes** :

| slot iface `IDamagePrediction` | méthode | usage |
|---|---|---|
| **#5** | `GetAttackPrediction` | **PRÉDICTION** (IA, midpoint, 0 RNG) |
| **#0xc (12)** | `CalculateDamageOperation` | **COMBAT RÉEL** (split `Damage{health,armor,shield}`) |

Preuve : `DealDamageOperation.Execute` @180e65d20 résout `get_DamagePrediction`
@180ffa360 puis appelle **slot #0xc** `(retbuf[0xa0], service, attacker, target,
&hitInfo)`. Confirmé par le décorateur `CachedDamagePrediction.CalculateDamageOperation`
@180e2ef10 qui délègue au même slot #0xc avec la même signature. Impl réelle =
**`DamagePrediction.CalculateDamageOperation` @18102dc30**.

**Base commune prédiction↔combat = `DamageCalculations`** (interface `IDamageCalculations`,
token `DAT_183287db8`). `CalculateDamageOperation` y délègue le split (armure/bouclier)
et les rolls crit/block/evasion. C'est la factorisation que l'utilisateur soupçonnait.

#### Orchestration par coup — `AttackDamageOperation.ExecuteHit` @180e5eff0 (inline monstre)

Ordre **RNG** d'un coup (chaque roll = `IPseudoRNG.NextBool(chance)` = slot #5 =
`next_internal(1,100) <= chance`, cf. §1.7) :

1. **spread** : `HitDamage.GetDamage` @181007bf0 — 1 tirage si `min≠max` (déjà porté, palier 1).
2. **crit** : `CouldCrit` (gate, 0 RNG) → `DamagePrediction.RollCritical` @1810387a0 :
   `critChance = clamp(GetStat(attaquant,9) + GetCritChanceBonusFromEffects, 0, 100)` ;
   **1 tirage `NextBool(critChance)` seulement si `critChance ≥ 1`** (sinon 0 RNG, pas de crit).
3. **DealDamageOperation → CalculateDamageOperation** (le split) qui fait :
   - **bouclier** : `CalculateDamageBlockedByShield` @181002850 = `min(dmg, shield)` (0 RNG).
   - **armure** : `CalculateDamageBlockedByArmor` @181002650 =
     `min(dmg, (int)Ceiling(dmg_Fix64 × armorPct/100))` (0 RNG ; `armorPct` caché Nullable).
   - **block** : `ApplyRandomBlockDamage` @181000390 — itère les sources de block triées
     (`CalculateBlockChances` @181002350 depuis `MultiValueStat(7)` → liste `{chance,
     amount=GetBlockDamageForBlockChance}`), `NextBool(chance)` par source ; **1ère réussite**
     → `ApplyBlockDamage` = `max(0, dmg − amount)` et stop ; chaque **échec consomme 1 tirage**
     + enregistre un failed-block-id. ⇒ **0..N tirages** (la « chaîne » décrite par l'user).
   - **evasion** : étage qui **PRÉCÈDE** le block (#407-r1 — ce n'est PAS une branche alternative,
     il n'existe aucun drapeau XOR) : `IdunBattle.Core.Services.DamageCalculations$$
     ApplyRandomEvasion` — `evasionChance = GetStat(cible, 0xf)` ; si `>0`, `NextBool` → succès =
     `dmg 0` **et le block est sauté**. Sinon on descend à la chaîne de block. `evasionChance` vaut
     **toujours 0** en jeu (0 porteur sur 5 voies) ⇒ 0 tirage : `case-407-r1-evasion-order.md`.
4. `EvaluateAfterHitTriggers` (cascade — tranche TRIGGERS).

> ⚠ **PRÉCISION #131 — d'où viennent les CELLULES min/max du coup.** Le point 1 ci-dessus n'est le
> tirage de VALEUR que pour les vecteurs dont le `HitDamage` d'entrée est NON dégénéré (ability
> bounds-mode). Pour l'**attaque NORMALE** le `HitDamage` est dégénéré (`Min == Max`) → 0 tirage ;
> `IdunBattle.Operations.AttackDamageOperation$$ExecuteHit` appelle ensuite le **slot 4**
> `IdunBattle.Core.Services.DamagePrediction$$PredictAttack` (un CACHE dont le seul corps de calcul
> est `IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw`) pour obtenir les cellules min/max
> RÉDUITES, puis le **slot 8** `IdunBattle.Core.Services.DamagePrediction$$RandomlyResolveMinMaxDamage`
> = `IdunBattle.Utils.PRNG.IntBasedMersenneTwister$$NextInternal(min, max + 1)` — **c'est CE tirage
> qui est la valeur du coup**. Conséquence structurelle : le COMBAT de l'attaque normale et la
> PRÉDICTION IA appellent LA MÊME fonction native (`PredictAttackRaw` et
> `IdunBattle.Core.Services.DamagePrediction$$CalculateAbilityDamage` sont les DEUX SEULS appelants de
> `IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers`), donc la MÊME
> matérialisation des bornes : `FixMath.NET.Fix64$$Round(·, AwayFromZero)` (dernier étage
> `IdunBattle.Core.Services.DamageCalculations$$CalculateBaseDamageWithModifiers`), PAS `op_Explicit`.
> Détail + mesure live per-coup : `case-131-normal-attack-bounds-materialization`.

**Crit (déterministe, post-roll)** : `CalculateCriticalDamage` @18102da90 :
`critDmgPct = max(0, GetStat(attaquant,10) + GetCritDamageBonusFromEffects)` →
`ApplyCritDamage` @181000210 = `base + critBonus` (additif ; trait `0x1c` = exécution :
renvoie `shield+health+armor` plein).

**Modifiers (class/affinity/élévation/ranged-in-melee/trench) = 0 RNG** (cf. memo) :
`CalculateAttackerModifiersForPrediction` @181000590, `CalculateElevationBonusModifier`
@181003ea0, `ShouldApplyRangedInMelee` @181005810, `CalculateRangedInMeleeReduction`
@181004700. RNG = UNIQUEMENT spread + crit + block-chain + evasion.

**Stats clés (`UnitExtensions.GetStat`)** : 4=?, 5=armure, 9=critChance, 10=critDamage%,
0xf(15)=evasion, 7=MultiValueStat block. **À confirmer live** (replay-diff vs events).

> ✅ **CONFIRMÉ LIVE (2026-06-29, replay-diff MT)** : le modèle RNG multi-coups SANS
> crit/block = **exactement `hits` genrand = 1 tirage spread par coup, en séquence**.
> Probe `probe_multihit_rng_order.py` (dumpRng avant/après) : u90→u86 (4 coups) = 4
> genrand, **MT offline == MT live après bit-exact** ; u94→u82 (3 coups) = 3 genrand,
> MT match. ⇒ les ROLLS sont bit-identiques ; l'erreur de dégât multi-coups résiduelle
> (u90→u86 off 3370 vs live 6292) est **100% déterministe post-tirage** (base/modifiers
> PowerTrip_IgnoreArmor, armure % combat, réductions trigger cible Parry/TerminatorArmour),
> **PAS le RNG**. `AttackDamageOperation.execute` (boucle `hits` × `next_internal`) reproduit
> déjà la conso RNG du natif.
>
> ⚠ **HYPOTHÈSE encore ouverte** : l'INTERLEAVING crit/block (ordre des tirages quand un
> crit/block/evasion FIRE — pas encore observé live : ces cas avaient critChance 0) +
> l'ordre exact du split `Damage{shield,armor,health}` dans `CalculateDamageOperation`
> (slots #0–#4/#0xc de `DAT_183287db8`) restent lus au mieux du décompilé register-renamé.
> À confirmer quand un crit/block réel apparaît (events `UnitDamaged` step 4 :
> `Amount`/`DidCrit`/`DidBlock`/`DidEvade`/`RemainingArmor`/`Shields_RemainingAmount`).

#### Split combat porté + finding empirique (2026-06-29, probe_split_events.py)

**Port** : `engine/services/damage_combat.py` ajoute `Damage{health,armor,shield,did_*}` +
`calculate_damage_operation(raw, shield, armor_pool, armor_pct, block_sources, evasion_chance, rng)`
(split bouclier→armure-pool%→**esquive PUIS block**, #407-r1), wiré dans `AttackDamageOperation.execute`
(le raw post-modifier/FixedArmor de chaque coup y passe ; pools déplétés entre coups).

**Finding décisif (events live `UnitDamaged` step 4, rolls bit-exact alignés)** : sur TOUTES
les cibles des batailles testées, **`RemainingArmor=0`, `Shields_RemainingAmount=0`, aucun
crit/block/evade**. Conséquences :
- La **`FixedArmor` (stat) est soustraite PLAT en amont** (`ExecuteHit`/`gdwp`), confirmé :
  u88→u80 roll 6829 − FixedArmor 1707 = Amount **5122** (exact). Le split `CalculateDamageOperation`
  ne gère que les **pools déplétables** (`ArmorComponent`/`RemainingArmor` en %, `ShieldComponent`)
  + crit/block/evasion — tous **0/absents** ici ⇒ le split se réduit à `health = raw` (chemin
  validé single-hit, **branches pool/shield/crit/block NON exercées**).
- Le **vrai blocage de l'agrément multi-coups n'est PAS le split** mais (1) les **modifiers de
  dégât attaquant** (RapidAssault/PsychicStalk : Amount > roll−armor ; PowerTrip) et (2) les
  **réductions trigger CIBLE** (Parry/… : Amount ≪ roll, non-constant = `predOptimistic`). =
  chaîne modifier §16/§17 + système de TRIGGERS, pas le split bouclier/armure/crit/block.
- ⇒ **PROCHAINE PRIORITÉ validée par les données** : (a) caler les modifiers attaquant de combat
  (réutilise le port prédiction §17) ; (b) réductions trigger cible (tranche TRIGGERS). Le split
  reste un scaffold fidèle, validable seulement quand une cible avec bouclier/pool/block/esquive
  apparaît.

#### Modifiers attaquant combat — diagnostic (2026-06-29, probe_attacker_mods.py)

Classification par coup `offline_raw = apply_pierce_and_modifiers(roll, pierce, FixedArmor, mods)`
vs live `Amount` (rolls bit-exact), 6 seeds / 27 coups : **REDUC_CIBLE 10 · MANQUE_BONUS 9 ·
CRIT/BLOCK/EVADE 5 · MATCH 2 · OVERKILL 1**.

**Conclusion** : la chaîne modifier ATTAQUANT du combat (effets via `build_attacker_modifiers_from_effects`
+ réduction perçage/FixedArmor partagée) est **déjà largement fidèle** (MATCH + RapidAssault à ~1%
près = résidu Fix64/armure, pas un modifier manquant). Les écarts attaquant restants sont **NICHE /
CONDITIONNELS** et **non isolables** (chaque combat live cumule plusieurs effets + réductions cible) :
- `PsychicStalk_FriendlyChaosExtraDamage` = `ForAddition(ConfigVar 8)` **+294 exact** (u96→u80), MAIS
  gated `AreFriends & HasTrait(0x7ea) & TargetOnFireTile & ValidDamageProfile` (@180f66f50).
- `RangedSpecialist`/`StructuralAnalyserDmgBoost` = bonus de **perçage** conditionnel (anti-armure/
  anti-machine) — off sur-réduit (off 21 vs live 309).
- `PowerTrip`/`Parry` : deltas **non-constants** (±) = confondus par une réduction cible simultanée.

**⇒ Pas de fix attaquant commun à fort impact.** Le vrai blocage d'agrément = **réductions côté CIBLE**
(REDUC_CIBLE dominant : Parry/Terrifying_ExtraDefense/BigTarget defense = `CreateEffectDamageMalusForDefense`
+ triggers `predOptimistic`). Recommandé : pivoter sur la **tranche réductions défenseur/TRIGGERS**.
Les modifiers attaquant niche (PsychicStalk fire-tile, StructuralAnalyser vs-machine) = long-tail à porter
au fil du roster, validables seulement par cas isolé (pas de cible mono-effet dans les seeds testés).

#### Réductions DÉFENSEUR — infrastructure symétrique portée (2026-06-29)

RE : `CalculateDefenderModifiersForPrediction` @181002c30 = **miroir de l'attaquant** — itère les effets de
la CIBLE, appelle `CreateEffectDamageMalusForDefense` (interface effet slot 0x1a) sur chacun → accumule un
`DamageModifiers` (%-list de réduction). La famille `ADamageDefenseModifierAbilityEffect` @180f08e60
(→ `BaseEffect.DamageMalusForDefense` @180f10120) = `EffectBonus(PercentDecrease, ConfigVar(key))` gated
(ex. ContemptuousDisregard @180f3a5b0 : `OwnerIsTarget & HasUsedActiveAbilityThisTurn` → ConfigVar 0x46) —
**même pattern que les bonus attaquant**. (Le natif a aussi 2 additifs @+0x20/@+0x28 via slots 0x19/0x1b,
non portés tant qu'aucun effet ne les fournit.)

**Port (symétrique, non commité)** : `BaseEffect.create_effect_damage_malus_for_defense()` (défaut None) +
`build_defender_modifiers_from_effects` (effects/__init__) + `build_defender_modifiers` (damage_modifiers) +
`defender_modifiers()` (damage_model) ; wiré dans `AttackDamageOperation.execute` (réduction appliquée par
coup APRÈS les modifiers attaquant, AVANT le split : `raw = apply_all_modifiers(raw, def_mods)`). **Vide →
no-op** (single-hit reste bit-exact). **Aucune sous-classe défensive encore implémentée** (les effets des
seeds testés — Parry/Terrifying — utilisent des axes STAT/COUPS/TRIGGER, hors cette famille) ⇒ infrastructure
prête mais **non exercée** (comme l'attaquant : magnitudes/conditions portées au fil du roster, validées par
cas isolé). Les réductions `predOptimistic` (Parry, TerminatorArmour) restent la **tranche TRIGGERS**.

#### Cluster runner↔prédiction — divergences fermées (verdict RE re-expert + validator, 2026-07-07)

Le port avait **forké** le calcul de dégât en 2 chemins (prédiction playbook / combat runner) qui doivent
mirrorer le natif à l'identique. Verdict RE (agent re-expert, décompilé) sur 5 divergences, portées sur
`master` (commits `61a36a0`, `01ae5ec`, `6989aaa`). **Fait clé** : le natif a **UN SEUL** builder de
modifiers attaquant `CalculateAttackerModifiersForPrediction @181000590` (pas de variante « ForCombat » —
le suffixe « ForPrediction » est un **misnomer**) ; combat `DamagePrediction.CalculateAbilityDamage
@18102cb50` et prédiction `PredictAttackRaw @181032fb0` appellent **tous deux** `CalculateBaseDamageWith
AllModifiers @18102d3f0`. Donc les feuilles positionnelles sont partagées BY CONSTRUCTION.

- **#62a — nb de coups = FORMULE partagée**. Le compte n'est PAS une méthode unique : c'est
  `IdunBattle.Entities.Formulas.AttackHitsWithModifiersFormula.Calculate @180f0bf50` (la FORMULE, nœud DSL)
  que les **façades** `GetAttackHits` (slot iface 0xb5) délèguent, une par contexte :
  `AttackDamageOperation.GetAttackHits @180e613d0` (COMBAT), `DamagePrediction.GetAttackHits @18102f240`
  (PRÉDICTION), `BattleQuery.GetAttackHits @18105d8d0`. Composition = base (`weapon + ExtraHits(0x11) +
  Σ effets` via `AdditionalHitsFromEffects.GetAdditionalHitsFromEffects @180e59e50`, clamps Min/Max type
  LightCover) + **GetStuckIn** = behaviour SÉPARÉ `AddBonusHitsToCurrentHitGroupBehaviour.Execute @180f93410`
  (ajout au hit-group pendant l'exec) + malus/aura de coups (effets). Le COMBAT manquait GetStuckIn + malus
  défenseur/aura → divergeait. **Port** : `services/attack_hits_formula.py::attack_hits_with_modifiers`
  (= la Formule, partagée) ; les 2 call-sites (combat `AttackDamageOperation.execute`, prédiction
  `make_normal_attack_predictions`) SONT les façades. **GetStuckIn = gate `include_bonus_hit_behaviours`**
  (verdict validateur, BITE 2) : la prédiction le folde (déterministe, `=True` — la chance ne pilote que le
  roll d'exec, pas la prédiction IA), le COMBAT ne le folde PAS (`=False`) car le natif le roll via
  `Maybe(GetBonusHitChance @180f83460)` (30 %/100 %) dans le behaviour `AddBonusHitsToCurrentHitGroupBehaviour
  @180f93410` À L'EXÉCUTION. Folder inconditionnellement sur-comptait en combat (prouvé live : orksNob 1v1
  chance=30 → natif **3** coups, port **4**). Malus défenseur/aura (LightCover/Parry/BigTarget) NON chance-gaté
  → partagé sans réserve. **TODO #62c** : porter le behaviour combat (roll RNG à la bonne position → bit-exact).

- **#58 — ÉLÉVATION appliquée EN COMBAT** (feuille positionnelle du builder partagé). `CalculateElevation
  BonusModifier @181003ea0` (+50 % surplomb, ELEVATION_BONUS_PCT) est inline dans le builder, calculée depuis
  les positions (pas des effets). **Port** : `damage_model.apply_elevation_bonus` ajoute au `mods` de
  l'attaquant depuis `state.board` + positions réelles ; constante rapatriée dans `damage_modifiers.py`
  (= port de `DamageCalculations`, config `Init @181005790`), plus de module inventé `positional_mods`.
  ⚠ **RÉSIDU** : le call-site COMBAT natif du builder positionnel n'a PAS pu être épinglé **statiquement**
  (dispatch gshared) → confirmation LIVE requise (attaquant en surplomb → dégât réel ×1.5). ranged-in-melee
  /trench en combat = même famille, PAS encore portés (follow-up).

- **#60 — HAS_MOVED (gate no-move HeavyWeapon) lu en COMBAT**. `HeavyWeapon_ExtraDmgEffect.CreateDamage
  Modifier @180f4f030` = `ForPercentIncrease(OwnerIsCaster & IsRangedAttack & NOT HasFlag(execCtx.flags@0x148,
  3) …)` — le « n'a pas bougé ce tour » est un **flag d'état de tour** (contexte d'exécution d'ability),
  PAS une comparaison de position (i2 : « when this unit has not moved this turn »). Le port passait
  has_moved=None → bonus TOUJOURS appliqué (FAUX). **Port (état FINAL, #101)** : le flag natif
  `UnitFlag.Moved=0` du `UnitFlagsComponent` — posé par `set_moved_flag` (mirror
  `IdunBattle.Entities.UnitExtensions$$SetMovedFlag`, appelé par `MoveUnitOperation`), purgé par
  `remove_turn_flags(new_activation=True)` du `StartTurnOperation` (PAR JOUEUR ENTRANT), lu par le
  **lecteur unique** `components.unit_has_moved` (`attacker_modifiers`, `HarvesterOfSouls$$GetHits`,
  `RadSaturation` fin-de-tour). Le set `state.moved_this_turn` de #60 était une 2ᵉ représentation
  parallèle du même flag → supprimé (cf. `case-101-moved-flag` : +25% fantôme sur tout état rechargé).
  Bypass overwatch (flags 0/0xc) = le bonus SURVIT en tir d'overwatch (déjà couvert : l'overwatch garde le bonus).

- **#62b — CRIT en prédiction normale = PAS de changement (déjà fidèle)**. `DamagePredictionResult` porte
  `AccurateHealthDamage@0x58` (range NON-crit) + un **booléen** `MightCrit@0xB1` (+ `ForceOverkill@0xB2`) —
  **aucun champ de dégât crit séparé**. La prédiction NE pondère PAS le crit (elle expose un flag) ; le
  COMBAT tire le crit réel (`RollCritical`/`CalculateCriticalDamage`, cf. ci-dessus). Divergence **VOULUE**.
  `might_crit` n'est consommé nulle part dans le scoring IA → poser/ne pas poser = no-op. Port déjà correct.

- **#59-suite — gates DÉFENSEUR sur chemins ABILITY**. `execute_ability_attack` / `execute_normal_like`
  threadent `is_melee` + `damage_profile` → `build_defender_modifiers_from_effects` (gates
  Terrifying_ExtraDefense = IsMeleeAttack ; TerminatorArmour = exclut Psychic/DirectDamage). Étend le fix
  attaque-normale (`1f9097f`) aux abilities.

**Convention de structure (clarifiée dans les en-têtes)** : `DamageCalculations` (grosse classe service)
est **ÉCLATÉE PAR CONCERN** dans le port (PAS « 1 classe = 1 module ») — tranche MODIFIER →
`services/damage_modifiers.py`, tranche COMBAT (crit/block/evasion) → `services/damage_combat.py`, builders
qui itèrent les EFFETS (`CalculateAttackerModifiersForPrediction`/`…Defender…`) →
`entities/effects/__init__.py`. Chaque en-tête cite sa tranche + VA. `DamagePrediction` → `damage_prediction.py`,
`BattleQuery` → `battle_query.py`, la Formule des coups → `attack_hits_formula.py`.

**Validation** : no-régression 5 passed / 1 red **pré-existant** (`u90→u86`, gap base/modifier famille #49,
indépendant de ce cluster). **Live-bites — VERDICT validateur adversarial (session 25, oracle=natif, discriminateur
bit-exact same-`dumpRng`)** : **3 MORDENT** — (#58) élévation ×1.5 réelle en combat CONFIRMÉE (porteur clean
`astraPrimarisPsy`, surplomb 4278==4278, plat 3336==3336, bornes ×1.5 exact ; le call-site combat non-résoluble
statiquement était le résidu, tranché live) ; (#60) HeavyWeapon annulé après move CONFIRMÉ (moved 5274==5274) ;
(#59) gates défenseur ability CONFIRMÉS (splash Psychic vs TerminatorArmour 1506==1506, non réduit). **1 SUR-AJUSTÉ**
— (#62a) GetStuckIn en combat : le fold inconditionnel sur-comptait (orksNob chance=30 → natif 3 vs port 4) →
**découplé** (`include_bonus_hit_behaviours`, cf. #62a ci-dessus : prédiction folde, combat omet ; behaviour combat
= TODO #62c). **ExtraHitsMelee (StatType 0x17=23) — TRANCHÉ + corrigé** : stat réel (map hook
`extraHitsMelee:23`, capturé combatSnapshot), dans la formule native `GetDefaultAttackHits @181032520`
(`base + ExtraHits(0x11) + (mêlée ? ExtraHitsMelee(0x17))`). Le port l'utilisait déjà côté ABILITY
(`get_default_attack_hits`, `active_ability`) mais la Formule d'attaque normale `attack_hits_with_modifiers`
ré-inlinait `weapon + ExtraHits` **sans** lui → les 2 chemins normaux (préd+combat, Formule partagée) le
rataient en mêlée. **Fix** : la Formule appelle désormais `get_default_attack_hits(weapon, extra_hits,
extra_hits_melee, is_melee)` (homonyme validé). **Inerte** sur les unités testées (`extra_hits_melee=0` →
agreement vert inchangé) ; bite plein-roster non scannable offline (gameconfig hors-live = 3 unités,
unit_map n'indexe que les hits d'arme) → à confirmer sur un porteur live.

### 1.9 SUMMONS — joués par l'IA via behaviours FORCÉS, hors PickNextUnit (RE + live, 2026-06-29)

Une unité **invoquée par ability** (trait `Summon` — `necroSmnSwarm`, `necroSmnDestroyer`, … vs `Hero`
pour les unités normales) **n'est jamais activée par la boucle de PLAYBOOK** (`PickNextUnit`). Mais l'IA
**la joue quand même** (move + attaque) via des **behaviours DSL FORCÉS** déclenchés hors PickNextUnit.
(Correction d'un finding initial erroné « on-appearance only » : ce n'est vrai que pour le scarab.)

- **Exclusion playbook** : `AnAiGroupOperator.GetValidUnits` @1811833e0 ne retient comme *activable* que
  `HasActionLeft && !IsDead && *(int*)(BaseUnitComponent+0x60) < 0x3e9 (1001)`. Les unités `+0x60 >= 1001`
  (= **summons & objects**) sont exclues de `PickNextUnit` et collectées à part (branche `StackDict.New +
  FUN_18000a970(...,0x17,...)`). `+0x60` = int copié par `BaseUnitComponent.Copy` @180f96110 ; identité
  exacte = raffinement, **discriminant offline fidèle = trait `Summon`** (gameconfig).
- **Jeu effectif = behaviour forcé** `DSLFactory.PerformAIAction` @180df8990 / `PerformAIAttack` @180df8b60
  → `PerformAIActionBehaviour.Execute` @180fcba10 : sélectionne les entités-summon (champ +0x50) et
  **exécute la décision IA move+attaque** de chacune (2 bools = move? attack?) dans la file de messages.
  Le summon **utilise donc bien un playbook** (move+attaque), juste invoqué par un trigger forcé.
- **QUAND le trigger forcé tire = par-ability** :
  - **À l'apparition seulement** : necron `ScarabSummonAbility.ExecuteBehaviour` @181205290 range un
    `PerformAIAttack` dans `SpawnUnitOptions+0x18` (1 fois au spawn) ; **aucun trigger récurrent** → le
    scarab agit 1×, puis persiste inerte. Live (teams adaptées, ennemis gelés) : 0 action sur 3 tours,
    ennemis à PV pleins.
  - **Chaque début de tour** : Tyranid `CallRipperSwarms_PendingSummonEffect` = effet **bondé au summoner**
    avec `GetTurnStartBehaviourTrigger` @180f37e70 (`IsTurnOf(owner)`) → `PerformAIAction` chaque tour.
- **Test** : `tests/engine/runner/test_summon_not_activated_live.py` prouve UNIQUEMENT l'exclusion de
  `PickNextUnit` (`aiStepDryRun` = enumerator `CalculateNextActionForPlayer`, groupe normal seul) — PAS
  l'absence d'action (qui passe par les behaviours forcés).
- **Implication runner offline** (« playbook des summons ») : (1) spawn ✅, (2) **behaviour on-appearance**
  ✅ (scarab), (3) **TODO : behaviours forcés récurrents** = effet `*_PendingSummonEffect` bondé +
  trigger turn-start → invoquer le playbook move+attaque du summon (`PerformAIAction`), (4) exclure les
  trait-`Summon` de la (future) boucle `PickNextUnit` offline (gate GetValidUnits, cf. §2.6).

---

## 2. Plan de tranches verticales (validées vs live, dans l'ordre)

Chaque tranche = RE ghidra → port 1:1 → test d'agrément vs live (replay-diff).

0. **Foundation + état initial** (tâche #23) — modèle ECS (Entity/Component), pipeline
   `Apply` (gate→pre→record→post), `Operation` base + registre, bus d'events +
   discipline de cascade, **loader BC→état initial** (`Initialize` @180e35400 →
   spawn `PredefinedUnits` en entités : position/HP/owner/abilities/traits), harnais
   **replay-diff**. *Première validation* : état initial Python == live (observeBattle/
   decisionView) juste après build. ← AUCUNE logique d'operation requise, juste l'ECS.
1. **MOVE** (tâche #24) — `MoveUnitMessage` → `MoveUnitOperation` @180e79ff0
   (validation + `CalculatePaths` + écriture `UnitFootComponent` + `AddMoveEvent`/pas +
   `KillSteppableUnits` + `EvaluateAfterMoveTriggers`). Valide position **et** cascade
   after-move (overwatch). Réutilise `engine/entities/pathfinding`.
2. **DAMAGE** — `ActiveAbilityMessage` (attaque normale) → `StartAttack`/`AttackDamage`/
   `ApplyDamage` → mutation HP. Chaîne RE'd : `AttackDamageOperation.Execute` @180e60c70
   → `GetAttackHits` (nb coups) → `ExecuteHits` @180e607b0 (boucle) → `ExecuteHit`
   @180e5eff0 (PAR COUP : roll crit `CritDamageInfo` + `HitDamage.GetDamage` + roll
   block + `EvaluateAfterHitTriggers`). **Tirage de dégât = `HitDamage.GetDamage`
   @181007bf0** : `min==max`→min (0 RNG) ; mode prédiction→`(min+max)/2` ; sinon
   **`rng.Next(min,max+1)`** = `engine/runner/prng.next_internal(min,max+1)` (1 tirage/coup).
   Spread per-coup via `engine/predict`. Bit-exact = porter l'ORDRE RNG d'ExecuteHit
   (crit→dégât→block) + réductions cible (ex. TerminatorArmour).
   - **PALIER 1 (mono-coup) ✅ validé bit-exact LIVE** (`operations/damage.py` :
     `HitDamage.get_damage` + `AttackDamageOperation` squelette ; test
     `tests/engine/runner/test_damage_roll_live.py` 2/2). RE confirmé : `GetDamage`
     est le **1er** conso RNG d'`ExecuteHit` (crit/block APRÈS) → `roll = raw_min +
     next_internal(0, R)` (R = plage BRUTE pré-armure via `aiPredict`, data-driven),
     puis `get_damage_with_piercing` → dégât live (preuve : seed 31337 u96→u82 roll
     2984 == live 2984, Δ=0). L'OFFSET `next_internal(lo,hi)−lo` ne dépend que du range.
   - **Init STATS + EFFETS structurés ✅** : `StatsComponent` (stat Attack résolue +
     arme via combatSnapshot) + `State.effects` (`EffectsState` matérialisé depuis
     decisionView), `load_state(decision, observe, snapshot)`. `damage_model.py`
     (select_weapon_pierce / resolve_one_hit / attacker_modifiers) + `AttackDamageOperation.execute`
     (tire chaque coup sur stat Attack±spread avec `state.rng`, réduit, mute PV) +
     `AttackUnitMessage`/`DamageHandler` + `state.rng`. **Base de combat = stat Attack**
     confirmée (discriminateur dumpRng ; ≠ weapon-base d'`aiPredict`).
   - **Validation = REPLAY-DIFF (pas d'oracle aiPredict)** : même attaque sur runner LIVE
     ET offline → mêmes PV. `tests/engine/runner/test_runner_attack_live.py` (2/2) : coup
     mono propre → offline (stats+effets ECS + MT calé via `dumpRng`) == live bit-exact,
     effets inclus (seed 777 u88→u80 = 5122 avec 5 effets actifs + armure/perçage).
   - **Paliers suivants** : crit (`CritDamageInfo`, composant 0xb, ordre RNG après dégât)
     + block (composant 10) → débloque multi-coups bit-exact (désync RNG inter-coups) ;
     réductions cible ; `EvaluateAfterHitTriggers`.
3. **DEATH/REMOVAL** — `KillUnitOperation`/`RemoveUnitOperation` + phases différées
   `System_ProcessDeaths`/`ProcessRemovals`.
4. **EFFECTS** — `AddEffectOperation`/`RemoveEffect`/`ChangeEffectTurns` (stacking,
   durée via `StaticBattleRules.Effect.DefaultAmountOfRounds`, id `PlayerIdGenerator`).
5. **TRIGGERS** — `TriggeredAbilityComponent` + `AbilityAndEffectCache` +
   `EvaluateTriggerOperation` (cascade réactive : overwatch, FinalJustice, …).
6. **TURN FLOW** — `EndTurn`/`ChangeTurn`/`StartTurn`/`PickUnit`/`SpawnUnitsOfTurn`. `PickNextUnit`
   filtre via `AnAiGroupOperator.GetValidUnits` @1811833e0 : alive + action-left + **non-summon/object**
   (`BaseUnitComponent+0x60 < 1001` ; offline = skip trait-`Summon`, cf. §1.9).

   **TF-A PORTÉ + validé live** (`engine/runner/operations/turnflow.py`, `EndTurnMessage`) — l'état
   OBSERVABLE de la transition de tour :
   - `IdunBattle.Operations.EndTurnOperation$$Execute` → 5 étapes dans CET ordre (cf.
     `case-n8b-endturn-order.md`) : (1) `turnsFinished@+0x5c += 1` par unité du joueur finissant,
     (2) `IdunBattle.Operations.EndTurnOperation$$RemoveOneTurnOnShields`, (3) même bump sur la MoW,
     (4) vecteur `On(0x17 = TurnEnd)` (gaté par
     `IdunBattle.Entities.Components.TurnComponent$$HasActivePlayer`), (5) **et SEULEMENT ALORS**
     `IdunBattle.Operations.EndTurnOperation$$RefreshEffects` : tick d'1 tour des effets à durée de
     **toutes** les unités (= `EffectsState.on_turn_end`, déjà porté). Le tick est le DERNIER acte,
     jamais le premier — les gates des triggers `On(0x17)` voient donc l'état PRÉ-tick ;
   - `ChangeTurnOperation.Execute` @180e62370 / `FindNextPlayer` @180e62570 → `find_next_player` :
     prochain joueur cyclique actif (Environment/neutre & équipes éliminées exclus = sans unité vivante ;
     ordre = ids croissants, exact pour 2 équipes) ; `current_player` flip ;
   - `StartTurnOperation.Execute` @180ea3fb0 (squelette) : incrémente `state.turn_counts[player]`
     (`TurnComponent.turnsStarted` @+0x38) + émet la séquence 0x12..0x16 → vecteur `On(0x16)` =
     `start_turn_triggers` (déjà porté, ex. TheBetrayer). Validé : `test_turnflow_live.py` (flip exact
     vs live + tick effets) ; smoke offline (flip A↔B, expiration, mono-joueur).

   **TF-A déféré** (état non suivi offline) : `DecreaseAbilityCooldowns` @180e6b0c0 (pas de compteur de
   cooldown offline), `ActorStatisticsComponent.ResetThisTurn` (stats per-tour),
   `ResetAbilitiesThatResetOnTurnEnd` @180e6cb90,
   et **`PickNextUnit`** (ordre intra-tour = décision IA → couche playbook, pas une mutation moteur).

   **TF-B PORTÉ (#139) — flags de tour per-unité + « does not end turn »** (validé live, cas discriminant
   Vindicta/cherub — cf. `docs/rl/solving-playbook.md` #139) :
   - **Flags** (`UnitFlagsComponent`, enum `UnitFlag`) : Moved=0, ArrivedAtFinalTile=1,
     ActiveAbilityUsed=2, TurnFinished=3, NoActionAvailable=4, Fled=9, Teleported=12, forced=27 (0x1b).
     Lecture `TurnEnded` @180fad510 = Contains(3) ; consommé par `VerifyUnitsTurnFinishedOperation.
     VerifyUnitTurnEnded` @180eded20 (auto-endturn quand toutes les unités sont finies ; flag 4 ré-ouvert
     slot 0x77 si l'unité regagne des options) et `AttackQuery.CanAttackAnyUnitFromAnyTileWithAnyAbility`
     @181054ccc. `MovementQuery.GetMovableTilesFor(unit, ignoreUnitFlags=false, …)` les honore aussi.
   - **Pose** : queue d'`ActiveAbilityOperation.ExecuteInternal` @180e44ec0 →
     `GetSkipEndTurnFlag` @180e47120 / `GetSkipAbilityUsedFlag` @180e46f60 (=
     `options.skip*Flag(+0x49/+0x4b) || !ability.Sets*().Evaluate(entities)`, slots iface 0x17/0x18) →
     `AddFlagsAfterAbilityExecution` @180e447f0 (flag 2 + `OperationProcessor.FinishUnitTurn` @180e081c0
     → `FinishUnitTurnOperation.Execute` @180e72140 : flags 1+3, +27 si forced). L'attaque normale EST
     une ActiveAbility (base True/True) → mêmes flags.
   - **Source du verdict** : virtuals `AActiveAbility.SetsEndTurnFlags` @180fb3150 /
     `SetsActiveAbilityUsedFlag` (défaut = `DSLFactory.True`@+0xf8) retournant un `IAbilityTrigger` ;
     overrides constants foldés IL2CPP (`_dsl.No`@+0x118 / `_dsl.False`@+0x100, fold-winners
     @1811b3d40/@1811b3d20) + 1 conditionnel lu (`FightingRetreatAbility.SetsActiveAbilityUsedFlag`
     @1811de7e0 = `Direct(!ennemi adjacent)`). **Famille « does not end turn » (14 abilities)** : 1014
     ArmoriumCherub (Vindicta) · 1063 FireAndReposition (Calandis) · 1081 FightingRetreat (Darkstrider,
     conditionnel) · 1106 WarHowl (Ragnar) · 1118 DoctrinaImperatives (Tan Gi'da) · 1121 ItItches
     (Parasite) · 1127 ArmouredMight_Move · 1131 JakhalStimms (Macer) · 1139 SentinelDirectives (Sy-Gex) ·
     1173 ArcScourge (Cawl) · 1189 CalibaniteGreatsword (Forcas) · 1198 EuphoricStrikes (Laviscus) ·
     1202 VigilanceEternal (Tyrith) · 1210 ExemplarOfTheMontka (Farsight) ; + 1077 EarlyWarningOverride
     (Re'vas) override AbilityUsed SEULEMENT. Tables = `engine/runner/abilities/base.py`.
   - **Reset** : `StartTurnOperation.Execute` @180ea3fb0 → `RemoveTurnFlags` @180fad310 `(0,1)` par unité
     du joueur entrant (retire 0/1/2/3/12/27 ; **conserve** NoActionAvailable=4).
   - **Port** : `turnflow.py` (`FinishUnitTurnOperation`, `add_flags_after_ability_execution`, reset
     StartTurn, `visit_FinishUnitTurnMessage`) + `abilities/handler.py` (queue de flags pour TOUTE ability,
     portée ou non) + `damage.py` (attaque normale). Bookkeeping OBSERVABLE, pas encore ENFORCÉ (aucun gate
     `should_block`/PickNext offline ne le lit — raffinement : brancher la future boucle PickNextUnit
     et `VerifyUnitsTurnFinished` dessus). Tests : `test_turnflow_endturn_flags.py` (offline pur).

   **TF-C PORTÉ (#120bis) — RE-RÉSOLUTION DE CIBLE après `On(0x2b = PreUnitAbility)`** (validé live,
   `SwornProtector`/Kell) :
   - **Où** : `IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal`, JUSTE après l'émission du
     vecteur et le gate caster-mort, AVANT l'exécution de la behaviour :
     `if (IsUnit(target) && Count(entities@+0x38) > 0) { replaced = UnitExtensions.GetUnit(First(...));
     if (replaced != target) return ExecuteForReplacedTarget(caster, replaced, abilityType, options); }`.
   - **Le point de bascule** : `entities@+0x38` = `EntityExtensions.GetTiles(finalTarget)` est **figé par
     `ActiveAbilityOperation$$GetAbilityEntities` AVANT le vecteur** (struct `AbilityEntities` de 0x130 :
     +0x10 target, +0x30 `GetMainTile(target)`, +0x38 `GetTiles(target)`, +0x48 casterTiles), tandis que
     `GetUnit` est résolu APRÈS. Si la cascade de triggers a fait entrer une AUTRE unité sur la tuile
     visée, c'est ELLE que l'ability frappe.
   - **`IdunBattle.Operations.ActiveAbilityOperation$$ExecuteForReplacedTarget`** rebâtit les
     `AbilityEntities` sur la nouvelle cible, RECALCULE `GetSkipEndTurnFlag`/`GetSkipAbilityUsedFlag`
     (consommés seulement par sa branche cible-morte `IsDeadUnitAndNotAllowedByAbility`, qui appelle
     `AddFlagsAfterAbilityExecution` et sort), écrit `options@+0x8 = Nullable(2)` (champ **relu par
     personne** dans la chaîne — marqueur de step/vue) puis **RE-ENTRE dans
     `ActiveAbilityOperation$$Execute`** : gates re-joués, NOUVEAU `On(0x2b)`, behaviour, flags de tour.
     L'appelant `return`e aussitôt ⇒ les flags ne sont posés **qu'une fois**, par la ré-entrée.
   - **Port** : foyer unique `engine/runner/operations/active_ability.py` (`get_tiles`, `get_unit`,
     `resolve_replaced_target`, `execute_for_replaced_target`), appelé par **les DEUX portes
     d'opération** — `operations/damage_ops.py::execute` (attaque normale : elle EST une active ability)
     et `abilities/handler.py::visit_ActiveAbilityMessage` (cast). Le câbler sur une seule aurait rouvert
     le fork que #120 venait de fermer. `AttackDamageOperation.execute` publie désormais `target` = la
     cible RÉELLEMENT frappée, que `DamageHandler` relit pour le vecteur after-hit.
   - **Garde du `Count(targetTiles) > 0`** : `get_tiles` d'une unité MORTE rend `[]` (mirror du board
     natif, d'où un mort est retiré) ⇒ aucune re-résolution sur un cast visant un cadavre — c'est ce qui
     protège `ReviveEffect`/`ReviveUnitOperation` (#66).
   - Tests : `probe_120bis_execute_for_replaced_target.py` (8 scénarios : 2 voies avec switch, 2 voies
     sans switch via `CanSwitchPosition` faux, cible sans SwornProtector, ability `Others`, cible morte,
     structure de la ré-entrée) + `test_pre_unit_ability_fork_live.py` (oracle live voie CAST, incl. un
     cast MONO-CIBLE sur un autre board/seed) + `test_sworn_protector_kell_live.py` (oracle live voie
     NORMALE).

   ### 6bis. BOUCLIERS (`ShieldComponent`) — modèle + absorption + décay (RE, port offline-validé)

   Modèle natif (`ShieldComponent` @180fa8770) = liste d'instances (+0x10) + compteur d'id (+0x18) ;
   chaque **`ShieldInstance`** = {`id`@+0x10, source `AbilityOrEffect`@+0x14, `amount`@+0x30,
   `remaining` Nullable<int>@+0x3c (**None = permanent**)}. `GetTotalShield` @180fa7f30 = Σ `amount`.
   Accordés par abilities/effets (`CreateShield` DSL : `APowerUpAbility.AddShield` @180e13cb0 = %·stat,
   durée `TurnsFromRounds`) — ex. ArcaneShield (Thaumachus), NovaShield (Riptide), WrathfulDevotion
   (Wrask), Shield power-ups (env). i2 : « A Shield absorbs all damage until destroyed and has no
   Armour ».

   **Absorption** (`CalculateDamageOperation` @18102dc30, COMBAT) : ordre **shield → block → armure-pool
   → santé**. Le shield absorbe `min(shield, dégât)` du coup **déjà réduit par l'armure fixe** (le
   « no Armour » = le POOL bouclier n'a pas d'armure, PAS un bypass de l'armure fixe de l'unité ; la
   réduction armure-fixe reste appliquée dans `ExecuteHit` AVANT). ⇒ le split du runner
   (`calculate_damage_operation` shield-first sur le roll réduit) **matche déjà** — il suffit de peupler
   le total. Porté : `AttackDamageOperation` peuple `shield` (3 chemins execute/ability/normal_like) +
   `ShieldComponent.deplete` après le coup.

   **Décay** (`RemoveOneTurnOnShields` @180e6c4e0 → `ShieldComponent.RemoveOneTurn` @180fa8080) : à chaque
   `EndTurn`, chaque instance À DURÉE perd 1 tour ; à 0 → retirée (les permanentes sont sautées). Porté
   dans `EndTurnOperation` (`turnflow.py`), à côté du tick d'effets.

   **Capture** : `shields` par unité ajouté à `combatSnapshot` (`rpc-view.ts`, lecture `ShieldComponent` :
   instances {id@+0x10, amount@+0x30, remaining Nullable@+0x3c}) ; `load_state` monte le `ShieldComponent`.
   ⚠ `remainingRaw=[s32@0x3c, s32@0x40]` émis en plus (layout `Nullable<int>` non tranché : ArcaneShield
   donne toujours remaining=1 → raw=[1,1] ambigu ; à confirmer avec un bouclier >1 round, sans rebuild).

   **VALIDÉ LIVE end-to-end** (probe `thousSorcerer`/ArcaneShield self-shield) : (A) capture d'un bouclier
   réel (amount=5483) ; (B) seed offline total == capté ; (C) absorption sur données réelles (ennemi →
   unité : shield_dmg=2008 absorbé, santé 0, bouclier 5483→3475 — shield-first) ; (D) **décay confronté
   live** : après 1 `endturn`, bouclier expiré OFFLINE **et** LIVE (présence + total MATCH). + smoke
   offline (deplete/expiry/multi-coups).

   **GRANTING (CreateShield) — ArcaneShield porté + validé live** : `ShieldComponent.add_or_update_shield`
   = `AddOrUpdateShield` @180fa7290 (stack même source+durée, sinon nouvelle instance id auto). `Arcane
   ShieldAbility` (`triggers.py`, @180e16f60/@180e16b40) : amount = `shieldHp[passive_level] × mult%`
   (var rareté), durée 1 round, cible = ami le plus proche dans range 2 (préf ThousandSons > Chaos >
   autres > soi) ; **vecteur APPROXIMÉ** sur after-move quand mover==owner (natif `On(0x1c)` = activation
   terminée, le cas « fin de tour sans move » non couvert). `ctx.passive_ability_level` ajouté (indexe les
   vars passives). **Validé live** : grant OFFLINE (after_move → target=soi, amount=5483, durée 1) ==
   bouclier LIVE (5483) — amount bit-exact. Déféré : NovaShield (active, Riptide) / WrathfulDevotion
   (mort, Wrask) ; vecteur 0x1c propre (cas fin-de-tour) ; ciblage multi-amis (validé solo) ; confirmation
   layout `Nullable` (bouclier >1 round).

---

## 3. Validation (replay-diff vs live)

- **Source de vérité** = runner live. Pour une séquence de messages, on applique la
  même chose au live (`applyAction`) et au runner Python, et on diff l'état après
  chaque pas (positions, HP, effets, cooldowns, morts, tour courant).
- **Snapshot d'état live** : `observeBattle` (units hp/stage/squadId) + `decisionView`
  (positions/effets) + `combatSnapshot` (stats). **TODO probable** : un RPC de dump
  ECS complet (toutes entités + composants) pour un diff haute-fidélité.
- Intégré au moule pytest existant (`tests/engine/`, [[feedback_tests_confront_live]]) :
  build runner isolé auto-disposé (coexistence par défaut), amorce-if-needed, skip si pas de session.

---

## 4. État courant

- ✅ RE confirmé : pipeline `Apply`, vocabulaire Operations (~80), composants ECS
  (`*Component` catalogués), pattern Visiteur messages, structure de `MoveUnitOperation`,
  modèle de cascade, triggers.
- ✅ **Tranche 0 (tâche #23) FAITE + validée live (3/3)** : modèle ECS
  (`engine/runner/state.py` + `components.py` : UnitComponent/OwnerComponent/
  PositionComponent/HealthComponent/EffectsOwnedComponent, noms 1:1 natif), pipeline
  `Apply` (`runner.py`), bus de cascade (`events.py`), loader **état initial depuis
  snapshot live** + forme canonique + diff (`snapshot.py`). Harnais
  `tests/engine/runner/test_runner_state_live.py` : state == live (cross-check 2
  chemins exact). ⚠ id d'unité = `squadId`==`decisionView.id` (≠ `entityId` ECS).
- 🔶 **Tranche 1 (tâche #24, MOVE) — incrément 1a FAIT + validé live** :
  `MoveUnitOperation` (POSITION) @180e79ff0 + `MovementHandler` (visiteur) +
  `Runner.install_default_handlers`. Harnais replay-diff
  `tests/engine/runner/test_runner_move_live.py` (rejoue le MÊME move sur live ET
  Python) : position du mover EXACTE + zéro changement structurel parasite. Le
  **mécanisme move→overwatch est RE'd + confirmé live** : `EvaluateAfterMoveTriggers`
  @180e79770 → `Overwatch_AutoAttackEffect` (`GetAttackBehaviour` @180f5d3e0 /
  `GetAutoAttackDamage` @180f5d5b0) ; `AddMoveEvent` @180e78d20 émet UnitMoved(step 3)
  + tuiles chemin (clés 0x79 unit, 0x7a-0x7f pas). **Vérité-terrain** (`_probe_overwatch.py`,
  seed 777) : Maugan Ra (u78) tire **1174** sur le mover u96 (11044→9870), son effet
  `Overwatch_AutoAttack` consommé.
- ⏳ **Incrément 1b** (xfail documenté) : porter la cascade OVERWATCH (dispatch trigger
  after-move + auto-attaque + dégât via engine/predict + réduction TerminatorArmour
  côté cible). Valider Δhp Python == 1174 live. = tranches DAMAGE+EFFECTS+TRIGGERS
  amorcées par ce cas.
- Paquet : `scripts/python/engine/runner/`. Port BC→Initialize (indépendance totale)
  différé (l'état initial est chargé depuis le live = ground-truth-first).

## Summon turn-start auto-play (#65) — CONFIRMÉ live + mécanisme RE'd (build gqfc5mff6c)

**Vérité-terrain (live) :** les summons jouent SEULS au début du tour de leur team. Scénario :
`rl_duel build --p-units astraYarrick,astraCreed --a-units custoVexilusPraetor,custoTrajann` (seed 555) ;
driver Yarrick adjacent à un ennemi ; `applyAction {kind:ability, casterId:82, targetId:78, abilityType:1016}`
(SendInTheNextWave cible un ENNEMI, spawn 2× `astraNpc1Guardsman` team-du-caster adjacents à la cible,
attaque on-appearance −620). Puis endturn team1 → endturn team2 **passif** (garder les Cadiens vivants) →
**au turn-start de team1, AVANT que le contrôleur agisse, les Cadiens ont bougé SEULS** (repositionnés).

**Mécanisme (RE, ce N'EST PAS un triggered ability) :**
- Le **trigger-trace** (hook `BaseTriggeredAbility.ShouldTrigger`) ne capture pour les Cadiens que des
  `PreUnitMove` (réactions à LEUR move) + des env-effects — **AUCUN trigger turn-start summon**.
- `StartTurnOperation.Execute @180ea3fb0` NE joue PAS les summons (reset `ActorStatistics`
  attacks/blocks/damage-this-turn + itère `CurrentlyOwnedUnitIds` + `RemoveTurnFlags` + émet events
  `0x12..0x16` + drafting `BlockDrafting`/`EnableDrafting`).
- L'auto-play = **passe AI-control du runner APRÈS StartTurn** : `IdunGameViews.IsPlayerAiControlled
  @1804d7b10` + les summons ont leur **propre playbook** dans `IdunBattle.AI.Playbook` (ex.
  `ScarabSummonPlaybook @181159380`). Les summons sont des **unités AI-contrôlées** jouées par l'IA
  au turn-start de leur team, AVANT que le joueur contrôle le reste.
- **On-appearance selector = `ActiveTarget`** (`PerformAIAttack(param_2 = DSLFactory+0x180)`,
  `PerformAIAbilityUnitBehaviour.Execute @180fcb070` = routine IA mono-unité cible→move→attaque).
  Carte des `TargetsSelector` cachés du `DSLFactory` (dump.cs, réutilisable) : `0x148 Owner · 0x150 Effect
  · 0x158 Actor · 0x160 Caster · 0x168 CasterTile · 0x170 CasterTiles · 0x178 Target · 0x180 ActiveTarget
  · 0x188 PreviousActiveTarget · 0x190 TargetTiles · 0x198 UnitFeetTiles`.

**PORT #65 (net) :** le `StartTurnOperation` offline doit, APRÈS `start_turn_triggers`, lancer une **passe
AI-control sur les unités AI-contrôlées de la team courante** (= les summons) — chaque summon → décision
playbook → move+attaque → apply — AVANT de rendre la main au contrôleur.

⚠⚠ **DOUBLE CORRECTION — la « CORRECTION post-RE (2026-07-06) » qui tenait ici était elle-même FAUSSE
sur ses DEUX points.** Elle affirmait (a) que l'identification d'un summon n'est pas le trait
`Summon`, mais un flag runtime lu par `IsPlayerAiControlled`, et (b) que le caller est
`IdunGameViews$$QueueComputerActions`. Le décompilé dit le contraire, et la mesure aussi :

- **(a) c'est bien le TRAIT.** `IdunBattle.Entities.UnitExtensions$$IsAutomatic(unit)` =
  `BaseUnitComponent.HasTrait(unit, 2 = Summon) || BaseUnitComponent.HasTrait(unit, 13 = Object)` —
  deux `GetBaseUnitComponent` + `HasTrait`, rien d'autre. Établi par **#250**
  (`tests/engine/runner/test_summon_automatic_live.py`, qui MESURE le renversement : avec le trait le
  porteur n'est jamais `ctrl`/`hasAction` et bouge quand même ; sans le trait il est `ctrl` et ne
  bouge pas) et re-confirmé par **#291**.
- **(b) le caller est `IdunBattle.Operations.PlayAutomaticUnitsOperation$$Execute`**, atteint depuis
  `IdunBattle.Operations.StartTurnOperation$$Execute` par le slot `IOperationProcessor` 0x71 =
  `PlayAutomaticUnits(currentPlayer)`, APRÈS les cinq émissions d'events 0x12..0x16, sous les gates
  `!IdunBattle.Core.Services.BattleQuery$$get_NoAutomaticUnitTurns` et `PlayerComponent.PlayerType ∈
  {Human(0), Network(3), HumanAI(4)}`. `IdunGameViews$$QueueComputerActions` est **autre chose** : la
  boucle IA lancée quand le joueur COURANT est entièrement AI-contrôlé
  (`IdunGameViews$$IsPlayerAiControlled`) — elle ne joue pas « les summons d'une team humaine ».
  Corps de `PlayAutomaticUnitsOperation` (verbatim) :
  `foreach u in CurrentlyOwnedUnitIds(player) if IsAlive(u) && !HasFlag(u, 3 = TurnFinished) &&
  IsAutomatic(u)` → `for i in 0..4: if HasActionLeft(u) ComputerAction(u, forced: false)` →
  `FinishUnitTurn(u, isTerminated: false)`.

Ce qui reste VRAI du paragraphe d'origine : la routine de décision est
`IdunBattle.Entities.Behaviours.PerformAIAbilityUnitBehaviour$$Execute` (énumère les cibles du
sélecteur `+0x50` → per-cible un candidat move `+0x60` + attaque `+0x78`, msgs 0x37/0x38 →
utility-argmax downstream) ⇒ c'est bien le **PLAYBOOK COMPLET**, pas une routine « plus proche
ennemi ». Détail complet et mesure : `docs/rl/case-291-summon-activation.md`.

**Décision utilisateur (2026-07-06) : porter le PLAYBOOK COMPLET** (pas la réduction target→move→attaque).
Chemin natif exact = au turn-start, invoquer la décision playbook du summon (`DefaultAiUnitTactic.
calculate_next_action` déjà porté dans `engine/ai/`). Sous-chantier = **bridge `State → AiDecisionContext`** :
le décideur `calculate_next_action(ctx)` ne consomme QUE un `AiDecisionContext` ; aujourd'hui `context.build`
le remplit via RPC live (decisionView/observeBattle/tileMeta/pathDistToEnemies/aiMovableTiles/combatSnapshot).
Il faut un `build_from_state(state, uid) -> AiDecisionContext` qui dérive TOUS les champs du runner `State`
(sans RPC) — les 2 champs durs = `plans` (attackPlans générés offline) et `scene`/`predictor` (prédicteur
offline depuis le `UnitContext`/`StatsComponent` du State au lieu de `combatSnapshot`).

**FAIT (slice 1, offline-smoke OK) :**
- `UnitComponent.ai_controlled` (flag runtime, mirror `IsPlayerAiControlled`) + `SpawnUnitOperation` le pose
  sur chaque summon spawné.
- `Scene.from_state(state)` (`engine/playbook/scene.py`) : Scene de prédiction 100% depuis les composants
  (`StatsComponent.ctx` == UnitContext ; `State.effects` == EffectsState ; `State.board` = élévation). Le
  spine ne lit QUE `ctx.scene` (jamais `predictor`/`sctx`, morts).
- `build_from_state(state, uid) -> AiDecisionContext` (`engine/ai/state_bridge.py`) : bridge offline complet.
  Champs durs : `plans` = énumération offline (par ability d'attaque × ennemi → SET de tuiles-caster légales,
  portée = max Range d'arme ; ordre indifférent car argmax strict) ; `ability_targets` = no-op (SLICE 2 :
  seuls heal/repair/summon/Nova l'utilisent). Normal attack = id synthétique 17 (le concret per-unité est un
  état runtime non-gameconfig, INUTILE : prédiction lit l'arme du ctx, apply = AttackUnitMessage sans id).
  Gaps no-op documentés : `is_temporary_by_pos`/`effects_by_pos` = {} ; `pathdist_by_pos` = BFS multi-source
  approx (fallback hex dans best_move).
- `run_ai_control_pass(state, player)` (`engine/runner/operations/summon_ai.py`) : collecte les unités
  `ai_controlled` vivantes du player, décision playbook (`DefaultAiUnitTactic.calculate_next_action`) → apply
  (move via `MoveUnitOperation`+after-move ; attaque normale via `AttackDamageOperation`+after-hit — mirror
  exact de `visit_AttackUnitMessage`). Ordre = id (PickNextUnit = raffinement).
- Wiré dans `StartTurnOperation.execute` APRÈS `start_turn_triggers`. No-op si la team n'a aucun summon
  (aucune régression turn-flow).

## Cap phase-triggers + vecteur after-hit COMPLET pour abilities (#138 + #140) — build gqfc5mff6c

**#138 (reset ActOfFaith au crit d'ability/splash) :** `EvaluateAfterHitTriggers @180e25fc0` est porté par
`ADamageOperation` → PARTAGÉ par l'attaque normale ET les attaques d'ability (dispatch `WasCrit`, branche
`param_6 != 0` → event `0x3d`). Le port ne câblait `evaluate_trigger_operation` que pour l'attaque normale
(`after_hit_normal_attack`) ; `execute_ability_attack`/`execute_normal_like` appellent désormais
`after_hit_ability_attack` → le reset ActOfFaith fire au crit d'une ability (ArmoriumCherub) ou d'un coup
de splash (AoE FireOfAbsolution). Validé : `test_act_of_faith_ability_reset_live` (accumulate-from-0 → crit
ability → crit revient à la base). Committé `d2d0d48`.

**#140 (cap phase-triggers + vecteur COMPLET) :** RE du cap natif :
- `EvaluateTriggerOperation.EvaluateAbilityTrigger @180e6d650` GATE chaque ability-trigger à
  `GetTimesTriggeredThisPhase(key) < 0x33` (=51), `MarkAsTriggered` au fire.
- `TriggeredAbilityComponent @180faba40` = KeyedCollection par ability-type : `has_triggered@+0x2c`,
  `total@+0x30`, `times_this_phase@+0x34`. Peuplé au build (`TryAdd`, chaque ability via `UnitFactory.Add*`).
- `ResetPhase @180fab1e0` (zéro `+0x34`) via `EndPhaseOperation.ResetEntityPhase @180e6a210` = fin
  d'ACTIVATION (`OperationProcessor.EndPhase`, séparé de `FinishUnitTurnOperation`).
- **Psyker Smite CHAINE par design** : `PsykerExtraAttackAbility.CreateTrigger @181224420` = `On(0x26) &
  OwnerIsActor & IsRangedAttack & DamageProfileIs(Psychic) & NOT(actor 0x4a7=1191 OR target 0x5fd=1533)`,
  et `CreateBehaviour @1812241b0` (un `AttackWithAttackDamage` psychique) N'AJOUTE AUCUNE suppression → le
  splash (attaque psychique ranged) re-déclenche Smite sur un ennemi adjacent ; le SEUL bornage est le cap 51.
  (1191/1533 = suppressions EXTERNES, ex. HuntersBeyondDeath, pas auto-posées.)

- **`IsRangedAttack` est POSITION-based** (`DSLFactory.IsRangedAttack @180df4d90` → `IsRangedAttackAbilityTrigger`
  @180fa36c0 calcule caster+cible positions via `IsRangedPosition @180df4f60`) : une attaque est RANGED ssi le
  caster N'EST PAS adjacent à la cible — **PAS le type d'arme/profil**. Un splash psychique sur un ennemi
  ADJACENT au caster est MÊLÉE → **ne re-déclenche PAS Smite**. Le chain Psyker n'existe donc que si le caster
  reste à distance RANGED de chaque splash-target.

Port offline (mirror) : `TriggeredAbilityComponent` (`components.py`) attaché à chaque unité
(`snapshot.load_state`) ; gate `<0x33` + `mark_as_triggered` sur les `TriggeredAbility` dans
`evaluate_trigger_operation` (clé = type de trigger) ; `State.reset_trigger_phases()` mappé sur chaque
ACTION top-level (`Runner.apply`). `after_hit_ability_attack` calcule `ranged` **POSITION-based**
(`_is_ranged_position` = caster non-adjacent à la cible, mirror `IsRangedAttack`) — le Smite ne re-déclenche
que si position-ranged. VALIDÉ : cap semantics (`test_triggered_ability_component`, 6/6) ; non-régression
5 tests live bit-exact (psyker_splash / damage_ability / act_of_faith ×3) ; terminaison OK.

⚠ **CHAIN NON CONFIRMÉ LIVE (#145) — limitation tooling** : impossible de produire un confront LIVE du chain
multi-splash. Chaque géométrie contrôlée (2 ennemis tanky mutuellement adjacents, psyker à evenq-d=2) est
CONTAMINÉE par l'écart **evenq vs adjacence native `boardGraph`** : le JEU fait l'attaque primaire en MÊLÉE
(0 splash), alors que le port (evenq-d=2) la fait RANGED → splash + chain 51×. La divergence observée est
l'écart d'adjacence sur la PRIMAIRE (pré-existant, cf. test_psyker_splash), pas la logique de chain. Le chain
reste **RE-fondé** (IsRangedAttack position-based + pas de suppression + cap 51) + **replay-diff-gardé** (une
sur-splash serait attrapée) mais **pas live-confirmé**. Risque résiduel = un mismatch d'adjacence en
replay-diff réel pourrait faire chainer le port là où le natif ne chaine pas (auto-corrigé par replay-diff).
Bug corrigé en cours de route : `ranged` était hardcodé `(is_melee is False)` (always-ranged → over-chain
51× partout) → remplacé par le calcul position-based.
- **Smoke offline (board ligne, Cadien summon col 0 + ennemi col 5) : le Cadien MOVE (0,0)->(3,0) pour mettre
  son Las à portée (dist 2) puis ATTAQUE (2 coups, ranged) — décision full-playbook cohérente.**

### CORRECTION #147 — le splash Psyker NE CHAINE PAS (le « chain by design » de #140 était FAUX)

**Verdict RE #150 (agent, PROUVÉ ghidra gqfc5mff6c) — EVENT-MAPPING (la source du bug #140) :** l'ancien port
CONFLATAIT deux events NATIFS DISTINCTS sous une seule constante `0x26` (commentaire faux « message 8 ») :

- **`On(0x26)` = NormalAttack.** `DSLFactory.OnNormalAttackOrSmite @180df7c70` = `On(0x26) OR (On(9)=ability-attack
  AND HasUsedActiveAbility(Smite 0x3f5))`. L'event `0x26` est émis **UNE fois par ATTAQUE NORMALE** (per-attack),
  sur le chemin attaque-normale **UNIQUEMENT** — jamais par une attaque d'ability/splash.
- **After-hit = `On(8)` (+`On(0x3d)` si crit).** `ADamageOperation.EvaluateAfterHitTriggers @180e25fc0` dispatche
  `FUN_180026490(...,8,...)` après CHAQUE coup (always) et `...,0x3d,...` si crit (`param_6!=0`). **Jamais `0x26`.**
  Partagé par l'attaque normale ET l'ability (porté par `ADamageOperation`).
- **Le splash** emprunte `AbilityDamageOperation.ExecuteHit @180e29d50` → émet `{6, 8, 0x3d}` — **jamais `0x26`**
  (le primary normal `AttackDamageOperation.ExecuteHit @180e5eff0` émet `{6,7,8,0x3d}` + le `0x26` émis plus haut).

⇒ **Le splash ne re-satisfait JAMAIS la souscription `On(0x26)` du Psyker → PAS de chain. STRUCTUREL** (le splash
n'emprunte pas l'émetteur NormalAttack), pas un flag anti-réentrance. Conforme au live (1 seul splash — l'agent
Fable l'a prouvé, `probe145_chain_v3`). Le « chain by design » de #140 (ci-dessus) était un **artefact de la
conflation** : le port faisait re-fire Psyker via le vecteur `after_hit_ability_attack` du splash.

**FIX (`triggers.py`) :** constantes séparées `TRIGGER_NORMAL_ATTACK=0x26` / `TRIGGER_AFTER_HIT=8` /
`TRIGGER_AFTER_CRIT=0x3d`. **Psyker** écoute `NORMAL_ATTACK(0x26)` → `after_hit_normal_attack` dispatche 0x26
(Psyker, per-attaque) **ET** 8 (after-hit) ; **`after_hit_ability_attack` ne dispatche QUE 8** → Psyker n'y matche
plus. **Reset ActOfFaith** reste sur `AFTER_HIT(8)` (gate `is_crit`) → fire toujours au crit des deux chemins
(comportement #138 préservé). Le cap 51 (`TriggeredAbilityComponent`) devient un **garde-fou générique** (jamais
atteint par Psyker). VALIDÉ : (a) structurel (0x26 != 8 → skip) ; (b) 6 gardes live (psyker_splash 1/1,
act_of_faith reset 2/2, damage_ability+crit 3/3) ; (c) **probe offline chain-prone** (4 ennemis en ligne, Psyker
ranged) = **1 splash** (était 51). ⚠ **Follow-up fidélité** : le natif reset = `On(9)`=ability-attack, or le
mapping sur `On(8)` fire AUSSI au crit d'attaque NORMALE (pré-existant, non régressé) — à re-vérifier vs live.

**VALIDÉ LIVE (bridge-equivalence, seed 777) :** `calculate_next_action(build_from_state(state,uid))` ==
`engine_decide(...)` (RPC-fed) sur un runner live — MÊME moteur, entrée reconstruite du State ⇒ tout écart =
infidélité du bridge. Résultat sur les unités de la team courante : **SLICE-1 (move) 3/3 EXACT** (u88/u90/u94,
dont u94 `templChampion` mr=4 ⇒ preuve que le bridge lit le STAT movement live, pas gameconfig=3). Exclus
(hors #65, attendus) : u96 `darkaTerminator` = **Teleport/non-Walk** (le flood Walk ne peut PAS le reproduire —
limitation partagée avec le port pathfinding ; les summons sont Walk) ; u92 `genesBiophagus` = **caster
d'ability spéciale** (SLICE 2 — les `plans` offline n'énumèrent que l'attaque normale).

**FIX clé (trouvé par le bridge-equivalence) :** `_move_range` lit d'abord le STAT `MOVEMENT` (effet-inclusif)
puis fallback gameconfig `Movement` (le summon offline n'a pas de combatSnapshot ⇒ base = bonne portée). Avant
le fix, gameconfig `Movement`=3 fixe donnait un `move_tiles` sous-ensemble strict du natif (u94 devait avoir 4).

**Yarrick END-TO-END live (tenté) — CONFONDU, pas un pass/fail propre :** build Yarrick vs Custodes, drive
Yarrick à portée, cast `SendInTheNextWave` -> 2 `astraNpc1Guardsman` spawnés adjacents à l'ennemi. Constats :
(1) `aiStepDryRun` active l'ENNEMI (u78), PAS un Cadien ⇒ **le summon NE surface PAS dans l'aiStep** (il joue
via la coroutine View `QueueComputerActions`, confirmant la RE) ; (2) l'état capturé post-cast est en FLUX
(les Cadiens ont déjà agi ON-APPEARANCE, le tour bascule vers team2) ⇒ `engine_decide` (RPC-fed) rend `stay`
et l'offline rend un kite-Las, mais les DEUX portent sur une unité déjà-agie ce tour = **baseline non
interprétable**. Le clean « action turn-start summon natif vs offline » exigerait l'état PRÉ-turn-start, que
l'API live n'expose pas proprement (le natif joue le summon automatiquement au flip). ⇒ **abandonné comme
métrique** ; la fidélité de décision reste couverte par le bridge-equivalence (3/3 Walk) + le smoke.

**Vérif offline complémentaire (summon adjacent à un ennemi) :** un Cadien (arme Las range 2, 2 coups + Physical
mêlée 1 coup) à côté d'un ennemi **kite en dist 2 pour tirer au Las (2 coups)** au lieu de rester en mêlée
(1 coup) — comportement RANGÉ correct (maximise les coups + évite la riposte mêlée), PAS un bug. (L'attente
« attaque sur place » était fausse pour une unité rangée.)

## SLICE 2 (abilities actives) — IMPLÉMENTÉ offline (RE re-expert : chaîne native `GetAllValidTargetsFrom
AllPossibleMovementTiles @18111e890` / `GetEligibleTargetsSelectable @18111f0d0` / `TargetingQuery.GetRange
@1810bd670`)

**FAIT (`engine/ai/state_bridge.py`) :**
- `ability_targets_offline(state, uid, ability_id)` : énumérateur de ciblage offline (branché dans le seam
  `_rpc` de `build_from_state` → `ctx.ability_targets`). Rend l'UNION des cibles légales sur les tuiles-caster
  (origine + move). Classif gameconfig : ATTACK ⇔ `constants.damageProfile` ET non-NonComparable ; kind =
  enemy (`damageProfile`) / ally (`Heal*`/id∈{18,1167,1212}) / machine (`Repair*`/id∈{28,1119}) / tile
  (`unitId` sans `damageProfile` → summon, ring-1 libre) / self (résiduel) ; portée = `constants.range` sinon
  `attackRangeType` sinon portée arme.
- `_plans_for_unit` étendu aux abilities d'ATTAQUE actives (via `_attack_abilities` : normale 17 + chaque
  active à `damageProfile` non-NC, portée propre `_ability_reach`). Le spine `_best_attack` sweepe déjà tous
  les evals → aucun changement consommateur.
- Vérifié offline : SendInTheNextWave/ScarabHive/Aberrant→tile, Heal→ally, NovaBoost→self ; énumération tile
  (34 tuiles ring-1 libres) + heal (self) OK ; smoke normal-attack inchangé (33 dmg).

**(c) APPLY des abilities actives — ATTAQUE FAIT** (`summon_ai._apply_active_ability`) : ordre (1) port DÉDIÉ
via `AbilityHandler` (`ABILITY_CLASSES`) ; sinon (2) attaque active SANS port dédié → chemin GÉNÉRIQUE
`execute_ability_attack` (mirror `AttackWithAttackDamage`, config via `ability_attack_params`) ; sinon (3) no-op.
Vérifié offline : GauntletsOfUltramar(1000, non porté)→dmg 97 ; CrushingClaws(1105)→handler ; MightOfHeroes(1001,
non-attaque)→noop ; smoke normal inchangé.

**(c') PORTS DÉDIÉS de summon abilities — FAIT** (`engine/runner/abilities/loki.py` + `handler.py`, spec RE
`docs/rl/summon-abilities-port-spec.md`). `ABILITY_CLASSES` (9) = ThunderousAssault 1043 / GravitonRifle 1206 /
ScarabHive 1007 / CrushingClaws 1105 **+ (nouveaux)** :
- **ValkyrieStrike 1018** @181229e40 (astraSmnVoxcaster) — **CORRECTION SUR-TIR** : ExecuteBehaviour natif = SEUL
  `AddBondEffect(1022 ValkyrieStrike_Effect)`, AUCUNE attaque immédiate (le Blast est le payload de l'airstrike
  DIFFÉRÉ). 1018 a `constants.damageProfile` (`_is_attack_ability=True`) → le générique TIRAIT à tort un Blast
  immédiat ; le port dédié (handler `ported=True`) EXCLUT 1018 du générique → ne pose QUE l'effet 1022. (Fire
  différé du 1022 = tranche pending-effect, TODO.)
- **B1 splash** (1 attaque main sur target + 1 volet splash PARTAGEANT `minDmg/maxDmg`, seul `nrOfHits_2` diffère —
  helper `_splash_ability_behaviour`) : **PlasmaGrenade 1098** (Plasma, splash `_adjacent_enemies_of`, 2/1) ·
  **Stikkbomb 1051** (Blast, idem, 2/1) · **Fragstorm 1078** (Blast, splash pick-random ≤4 `_pick_randomly_n`,
  4/2) · **ScythingTalons 1065** (Bio melee, splash `_adjacent_to_both`, 3/2). Avant : le générique ne tirait
  QUE l'attaque main mono-cible (splash raté). Vérifié offline : registry 9 abilities, imports OK, les 5
  `_is_attack_ability=True` (prouve le sur-tir/perte-de-splash générique corrigés).
  - **VALIDÉ LIVE** (build gqfc5mff6c, board+units RÉELS, `tests/engine/runner/test_summon_ability_ports_live.py`
    NON commité, via le chemin réel `_apply_active_ability`) : **ValkyrieStrike 1018** → `routed=handler`, HP cible
    7029→7029 (ZÉRO dégât immédiat), effet `ValkyrieStrike_Effect` 1022 posé ; **PlasmaGrenade 1098** →
    `routed=handler`, `hits_main=2`/`hits_splash=1`, SET splash == voisins boardGraph NATIF ∩ ennemis (exact
    `[80,82]`). Couvre priorités validator 1 (counts/partage plage), 2 (sur-tir ValkyrieStrike), 4 (helper
    géométrie `_adjacent_enemies_of` vs adjacence native). **Stikkbomb 1051** = MÊME chemin/helpers (couvert par
    construction). NON validés live (GAPS déjà flaggés) : pick-random Fragstorm, doublement trait-2 ScythingTalons.
  - **GAPS inline flaggés** : doublement hits ScythingTalons `ConditionalAmount(HasTrait(target, trait enum 2))`
    (3→6/2→4) NON porté (trait enum 2 non mappé offline, famille 0xd) → hits de BASE (jamais de sur-compte) ;
    coût/ordre RNG du pick Fragstorm non calibré (désync possible `state.rng` si >4 candidats).

**RESTE SLICE 2 :** (c'') B2 (attaque-normale + move : DevoutPush 1053, WallOfMirrors 1186 — le move différé
tranche déplacement) ; B3 effet-seul/self (ForwardObservers 1185, Burrowers 1023, TunnelingHorror 1011 =
`AddEffect` non porté → `BaseEffect` no-op) ; GAPS non-portables offline (PrecisionShot 1015 aim→shoot,
KissOfDeath 1108 chain+blink, SlashingDive 1091 dive-ligne). (d) **validation live** (validator worktree, cf.
spec « Ce que le validator doit attaquer d'abord » : partage plage splash, sur-tir ValkyrieStrike, doublement
trait-2, helper géométrie, pick Fragstorm).

**GAPS documentés (RE §5) :** kind résiduel = self par défaut (faux pour un buff ally/tile type MightOfHeroes) ;
`+GetStat(0x18)` ranged-bonus + clamp effet 0x529 ignorés (portée arme seule) ; portée heal/repair codée 1 ;
`CanAddUnit` trench/hazard non filtré ; 37 abilities d'attaque sans `range`/`attackRangeType` → fallback arme.

**TRAITS DES SUMMONS SPAWNÉS — CORRIGÉ (RE + seed au spawn, 2026-07-07) :** avant, `SpawnUnitOperation.execute`
ajoutait au summon 5 composants mais **ne le seedait NI dans `state.effects` NI dans `state.traits`** → l'APPLY
d'attaque (`attacker_modifiers`/`defender_modifiers` → `build_*_modifiers_from_effects(state.effects.active_effects)`)
ne voyait AUCUN effet du summon → ses traits de dégât étaient MANQUÉS.

**Mécanisme natif RE'd (décompilé, VAs citées)** : à la création d'unité, `InitializeActorAbilitiesOperation.Execute`
@180e74660 fait 2 boucles — (a) par ABILITY → `StaticBattleRules.ActiveAbility.GetEffectToBeAddedToOwnerForAbility`
@1815551f0 (dict `ActiveAbility` static +0x50) ; (b) par TRAIT → `StaticBattleRules.Trait.GetEffectToBeAddedToOwnerForTrait`
@18157e800 (dict `Trait..cctor` @18157f650 static **+0x30**) — et `AddEffect(owner)` pour chaque owner-effect
retourné. La dict TRAIT a **4 entrées LUES** (ids natifs) : `HeavyWeapon(0x3e9)→HeavyWeapon_ExtraDmg(0x3f0)` ·
`MartialKatah(0x41f)→{MartialKatah_DmgBonus(0x56b),DmgReduction(0x56a)}` · `RangedSpecialist(0x424)→RangedSpecialist(0x5eb)`
· `trait 0x41e→Clone(0x53d)`. Nom↔id TRIANGULÉS (trait gameconfig `units.traits` ↔ effet capté live ↔ dict :
custoVexilusPraetor `MartialKatah`→effets MK captés ; tauDarkstrider `RangedSpecialist`→effet capté).

**Port** : `entities/effects/factory.py::get_effect_to_be_added_to_owner_for_trait` (homonyme + `TRAIT_OWNER_EFFECTS`)
+ `spawn.py::_seed_trait_owner_effects` (mirror la boucle TRAITS) appelé dans `SpawnUnitOperation.execute` → matérialise
les owner-effects PERMANENTS (rem=None) dans `EffectsState` (comme les unités initiales seedées depuis capture),
gate `has_effect` idempotent. **VALIDÉ LIVE** (`tests/engine/runner/test_summon_trait_effects_live.py`, NON commité) :
tauSmnStealthSuit → `RangedSpecialist` seedé, +% appliqué RANGED-only (melee gate OK) ; necroSmnDeathmark →
`HeavyWeapon_ExtraDmg` seedé ; contrôle necroSmnSwarm → aucun (pas de faux seed).

**BigTarget (chemin trait→ability dérivée) — CORRIGÉ (RE re-expert, 2026-07-07).** ⚠ Correction d'une erreur
de lecture : `BigTarget_AdjacentEffect` ne vient NI de la dict trait +0x30 NI de la dict ability +0x50 (celle-ci
= `GetEffectToBeAddedToOwnerForAbility`, static `ActiveAbility` +0x50, seulement 2 entrées `PlasmaCannon→
PlasmaCannon_Visual` / `GravitonRifle→GravitonRifle_ExtraPierce`, aucun summon concerné). Le mécanisme RÉEL est
DISTINCT : `AddTraitOperation.AddDerivedAbilities @180e513c0` dérive du trait `BigTarget` (0x3f9=1017) l'ability
`BigTarget` (0x406=1030) via la dict Trait **+0x0** (`GetTriggeredAbility @18157ed10`), puis
`BigTargetAbility.CreateBehaviour @18121a910` fait `AddEffect(0x402 BigTarget_AdjacentEffect)` à l'init de
l'ability (aura -1 hit ranged aux alliés ring-1). Port : `factory.TRAIT_DERIVED_ABILITIES` (mirror Trait+0x0) +
`ABILITY_INIT_OWNER_EFFECTS` (mirror `<Ability>.CreateBehaviour` AddEffect) + `spawn._seed_derived_ability_owner_effects`.
**VALIDÉ LIVE** (`test_summon_trait_effects_live.py`) : tyranSmnWarrior → `BigTarget_AdjacentEffect` seedé, classe
`BigTargetAdjacentEffect` (pas un no-op). (Le J'ai-lu-le-mauvais-dict = piège de frontière d'enum : 1026 =
`BigTarget_AdjacentEffect` en EFFECT_TYPE MAIS aussi un TriggeredAbilityType dans la dict `GetDerivedTriggeredAbilities`
+0x30.)

**Autres traits summon — RE FAIT (2026-07-07), rien à seeder de contributif :**
- **BattleFatigue** (eldarSmnGuardian/orksOrkBoys/astraSmnVoxcaster/tyranSmnRipperSwarm) : `BattleFatigueAbility.CreateBehaviour`
  @18121a0d0 = arbre `Flee`/`If`/`Repeat`/`ModuloAbilityTrigger` (aucun `AddEffect` dans les callees) → **PAS
  d'owner-effect** (déjà porté = death-trigger + Flee flag 9). Rien à seeder.
- **InstinctiveBehaviour** (tyranSmnSporeMine/tyranSmnRipperSwarm) : `InstinctiveBehaviour_UpdateTargetAbility` —
  **DROPPÉ** (décision utilisateur antérieure). Rien à seeder.
- **ShadowInTheWarp** (tyranSmnWarrior) — **PORTÉ (aura, 2026-07-07)** : `ShadowInTheWarp_AddEffectAbility`
  (`_AddEffectAbility`, base `CreateBehaviour` pose `constants.effectType`) → `ShadowInTheWarp_LessDmg_Effect`
  (1053=0x41d). `CreateEffectDamageBonusForAttack @180f6b420` = `ForPercentIncrease(OwnerIsActor &
  DamageProfileIs(Psychic), ConfigConst 0x3b)` ; `CreateTargetSelector @180f6b5f0` = `SurroundingEnemies(range=
  ConfigConst 0x16) & UnitsWithTrait(0x3ea) & UnitsNotFromFaction(0xc)`. **= AURA -25% dégât PSYCHIQUE aux
  ennemis psykers environnants (portée 2)**. Magnitude+portée LUES du **trait** (`shadowInTheWarpDmgModifier=-25`,
  `shadowInTheWarpRange=2`). Port : classe `ShadowInTheWarpLessDmgEffect` (loki.py) + canal aura
  `create_aura_attack_damage_malus_for_enemy` + agrégateur `aura_attack_damage_malus_from_enemies` (effects/__init__)
  wiré dans `prediction.py` (ajouté aux mods de l'ATTAQUANT, comme BigTarget/RitesOfBattle) + `EFFECT_CLASSES` +
  tables `TRAIT_DERIVED_ABILITIES`/`ABILITY_INIT_OWNER_EFFECTS`. Validé OFFLINE (logique aura : -25% ssi
  Psychic+ennemi+portée, None sinon ; seed chain). ⚠ Filtre `UnitsWithTrait(0x3ea)` (psyker) SUR-APPROXIMÉ au seul
  gate Psychic (trait non mappé offline). Live seeding re-confirm = identique au chemin BigTarget (déjà validé live).
- **Synapse** (tyranSmnWarrior) : `Synapse_AddEffectAbility` → `SynapseEffect` (1052=0x41c). ⚠ `SynapseEffect`
  n'a **AUCUNE** méthode de modifier dégât/hits (que `CreateTargetSelector`/`GetMaxRange`/`GetRefreshTriggers`) :
  c'est un effet **COMPORTEMENTAL** (grant synapse aux Tyranids ring-2 pour suppression d'Instinctive Behaviour —
  `SurroundingUnits(2) & Friends & (trait 0x3f7 | InstinctiveBehaviour 0x7e5 | ...)`), PAS une aura de combat.
  **NON porté dans le chemin dégât** (le porter comme modifier serait inventer une contribution inexistante ;
  InstinctiveBehaviour est de toute façon droppé).

**RESTE (flaggé)** : (1) trait `0x3ea` (psyker) à mapper pour affiner le sélecteur ShadowInTheWarp ; (2)
owner-effects posés par les abilities PROPRES du summon (non dérivées) à leur init — même mécanisme
`CreateBehaviour`, non balayé (aucun cas contributif connu sur le roster summon actuel) ; (3)
`MartialKatah_DmgBonus/DmgReduction` = effets non dans `EFFECT_CLASSES` → `BaseEffect` no-op ; (4) ScythingTalons
doublement trait-2 (défenseur) toujours non porté.

**GAP granted-abilities — CORRIGÉ (passive-derived, `state_bridge._granted_abilities`) :** `_abilities_of` ne
lisait que les `activeAbilities` GAMECONFIG → il RATAIT les abilities GRANTED par un passive au runtime. Cas
concret : `genesBiophagus` (`activeAbilities=['AberrantHypermorph']` seul) CASTE en natif `Heal_TwistedScience
(1167)` sur un allié — accordé par le passive TwistedScience, absent de `activeAbilities` → l'offline décidait
un MOVE (bridge-equivalence special 0/1). **Fix DÉRIVÉ DU PASSIVE (aucune table)** : le natif nomme la classe
accordée `<Passive>_HealAbility` = membre d'enum `Heal_<Passive>` (`TwistedScience_HealAbility$ExecuteBehaviour
@181217ad0` = `Heal_TwistedScience` 1167) → `_granted_abilities(vid)` scanne `passiveAbilities` et résout
`Heal_<passive>` via l'enum ACTIVE_ABILITY_TYPE (mergé après weapons(17)+activeAbilities dans `_abilities_of`).
Vérifié : `genesBiophagus` → `((17,NormalAttack),(1166,AberrantHypermorph),(1167,Heal_TwistedScience))` ;
Biophagus décide désormais le heal 1167 (reste un écart de CIBLE self-vs-allié = raffinement sélection heal).
Bridge-equivalence SLICE 1 (move) reste 3/3.

**Gap SLICE 1 restant :** un summon présent DÈS la capture (snapshot.py) n'est pas marqué `ai_controlled`
(seuls les spawns en cours de run le sont) — raffinement.
