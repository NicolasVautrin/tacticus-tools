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
   - **evasion** : branche ALTERNATIVE au block (gate flag) : `ApplyRandomEvasion`
     @1810004f0 — `evasionChance = GetStat(cible, 0xf)` ; si `>0`, `NextBool` → succès = `dmg 0`.
4. `EvaluateAfterHitTriggers` (cascade — tranche TRIGGERS).

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
`calculate_damage_operation(raw, shield, armor_pool, armor_pct, block_sources, evasion_…, rng)`
(split bouclier→armure-pool%→block XOR evasion), wiré dans `AttackDamageOperation.execute`
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

---

## 3. Validation (replay-diff vs live)

- **Source de vérité** = runner live. Pour une séquence de messages, on applique la
  même chose au live (`applyAction`) et au runner Python, et on diff l'état après
  chaque pas (positions, HP, effets, cooldowns, morts, tour courant).
- **Snapshot d'état live** : `observeBattle` (units hp/stage/squadId) + `decisionView`
  (positions/effets) + `combatSnapshot` (stats). **TODO probable** : un RPC de dump
  ECS complet (toutes entités + composants) pour un diff haute-fidélité.
- Intégré au moule pytest existant (`tests/engine/`, [[feedback_tests_confront_live]]) :
  build runner isolé `--keep` auto-disposé, warmup-if-needed, skip si pas de session.

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
