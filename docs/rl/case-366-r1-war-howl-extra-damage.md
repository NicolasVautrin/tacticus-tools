# case-366-r1 — `1222 WarHowl_ExtraDamage_Unstoppable` : TROIS artefacts, TROIS canaux

> Extrait du gisement des 96 (`case-366-gisement-96-effets.md` §3.3, groupe G3).
> Sa fiche d'inventaire annonçait « `CreateEffectDamageBonusForAttack` + `CreateCritChanceBonus` +
> `ApplyInternal`/`RevertInternal` ». Les trois existent ; ils tombent dans **trois canaux
> différents**, et un seul des trois est un canal que le port avait déjà branché.

## 1. Identité — une classe, un `EffectType`

Le slot `Il2CppClass*` `0x1833908e8` n'est partagé par aucun autre des 96 ids de la forme B, et
`IdunBattle.Entities.Effects.Loki.WarHowl_ExtraDamage_UnstoppableEffect$$.ctor` n'a **qu'un seul
appelant** dans tout le binaire : `IdunBattle.Core.Services.EffectsDatabase.u003Cu003Ec$$u003C
InitializeEffectsu003Eb__14_240`. Une fabrique = un enregistrement ⇒ aucun jumeau parmi les 607
(formes A + B). Verdict tranché par le SLOT et par les XREFS, jamais par le nom du ctor.

Le ctor porte une constante : `mov edx, 0x452` → `IdunBattle.Core.AbilityOrEffect$$op_Implicit`
→ `IdunBattle.Entities.Effects.BaseEffect$$.ctor(this, abilityOrEffect, hasAutomaticActivation: 1)`.
La surcharge d'`op_Implicit` est tranchée par son ADRESSE (celle qui prend un `ActiveAbilityType`,
`IdunBattle.Core.AbilityOrEffect.op_Implicit(activeAbility)`), pas à l'œil : les quatre surcharges
portent le même nom. `0x452 = 1106 = ActiveAbilityType.WarHowl` ⇒ **la config lue est celle d'une
ability ACTIVE**, indexée par le niveau d'ability ACTIVE de la SOURCE.

## 2. La POSE — `WarHowlAbility$$ExecuteBehaviour` (face non portée)

```
targets = Caster
        + UnitsWithoutTrait( UnitsWithoutRangedWeapons(
              Friends(Caster, <pool partagé> - Caster, UnitSelectionType.OnlyAliveAndTargetable) ),
              trait = 0x2 = UnitTrait.Summon, UnitSelectionType.OnlyAliveAndTargetable )

AddEffect( 0x4c6 = 1222, CreateSnapshot(<abilityState du cast>),
           source = Caster, targets = <ci-dessus>, turns = Get(1) )
```

`WarHowlAbility$$OtherBuffTargets` est le MÊME sélecteur sans le `+ Caster` (face DÉCISION).
**Ni faction, ni rayon** : tout ami mêlée non-Summon reçoit le buff, Space Wolf ou non.

MESURE live (MC1_67 / 777, `--no-ai`) : le cast pose 1222 sur `spaceBlackmane`, `spaceWulfen` et
`spaceHound` ; **pas** sur `spaceRockfist` ni `spaceStormcaller` (armes à distance). L'effet
remonte `Effect_RemainingTurns: 1` et a disparu des trois porteurs après **un seul** `endturn`.

⚠ Conséquence de montage : **le caster ne peut pas mesurer sa propre face** — le cast consomme son
activation. Le porteur mesuré est donc toujours un ALLIÉ, donc porteur ≠ source (cf. §6).

## 3. Les trois artefacts

### 3.1 DÉGÂT — `CreateEffectDamageBonusForAttack`

```
EffectBonus.ForAddition( get_OwnerIsCaster & IsMeleeAttack & IsNormalAttack,
                         ConfigVar(0x08 = extraDmg, GetAbilityState(effect), config@+0x60) )
```

Trois nœuds, tous portés. `get_OwnerIsCaster` l'est déjà par le canal (ces effets ne sont
interrogés que sur l'ATTAQUANT), `IsMeleeAttack` par le tri-état `is_ranged` (#106) et
`IsNormalAttack` par le paramètre du même nom. `extraDmg[50] = 886`, **dans**
`variablesAffectedByRarityBonus`.

### 3.2 CHANCE DE CRIT — `CreateCritChanceBonus`

```
EffectBonus.ForAddition(
    get_OwnerIsCaster & IsMeleeAttack & IsNormalAttack
    & AmountIsGreaterThanZero( StatAmount(Caster, 0x9 = CriticalChance,
                                          StatPart.Current, null, UnitSelectionType.Any) ),
    ConfigVar(0x41 = extraCritChance, GetAbilityState(effect), config@+0x60) )
```

**Quatre** nœuds : les trois du canal dégât **plus** un gate `AmountIsGreaterThanZero`, qui est
LOAD-BEARING — sans lui, un porteur à `GetStat(9) == 0` verrait `CouldCrit(0 + 36, GetStat(10))`
passer à VRAI et se mettrait à criter, ce que le natif ne fait jamais
(`IdunBattle.Core.Services.DamageCalculations$$CouldCrit` exige `GetStat(9) > 0`, et le bonus
d'effet n'y entre pas). `extraCritChance[50] = 36`, **hors** `variablesAffectedByRarityBonus`.

L'entité `Caster` est le champ **`+0x48`** de `IdunBattleLogic.Entities.DSLSelectors` — tranché par
recoupement, jamais à l'œil : `HeraldOfTheApocalypse_ExtraDamageEffect$$CreateEffectDamageBonus
ForAttack` = `OwnerIsTarget & IsUnit(<0x48>)` (l'ATTAQUANT) ;
`SagaOfTheWarriorBorn_KillAbility$$CreateTrigger` lit `HasTrait(<0x60>, Hero)` (la CIBLE) ;
`…$$CreateBehaviour` pose `source = <0x30>` (l'Owner).

**Le canal n'existait pas côté port.** `create_effect_crit_chance_bonus_for_attack(self)` ne prenait
AUCUN contexte et `crit_chance_bonus_from_effects(effects)` non plus — alors que le natif
(`IdunBattle.Core.Services.DamagePrediction$$GetCritChanceBonusFromEffects(this, attaquant,
défenseur, abilityOrEffect, hitIndex)`) construit lui-même son `AbilityEntities` avant d'évaluer le
trigger de chaque `EffectBonus` par le slot d'interface 0x21. C'est le symétrique exact du résidu
`N14` du canal crit-DÉGÂT : le contexte existait côté natif, il manquait côté port. Il est désormais
threadé au **même foyer unique** (`runner/operations/damage.py::AttackDamageOperation._crit_params`,
la façade CRIT des trois vecteurs d'attaque), avec trois clés tri-état :
`is_ranged`, `is_normal_attack`, `caster_crit_chance`.

### 3.3 TRAIT — `ApplyInternal` / `RevertInternal`

```
ApplyInternal (this, owner, target, effect)  ->  <IOperationProcessor @this+0x68>.<slot 0x26>(
                                                     target, 0x412, isTemporary: 1)
RevertInternal(this, owner, target, effect)  ->  <IOperationProcessor @this+0x68>.<slot 0x27>(
                                                     target, 0x412, isTemporary: 1)
```

`FUN_1800103b0` est un **dispatch d'interface** (offset d'interface à `klass+0xb0`, slot ajouté, saut
dans la vtable à `klass+0x138`) ; la signature `(target, trait, isTemporary)` est celle de
`Core.Services.OperationProcessor$$AddTrait` / `$$RemoveTrait` →
`IdunBattle.Operations.AddTraitOperation$$Execute` / `RemoveTraitOperation$$Execute`.
`0x412 = 1042 = UnitTrait.Unstoppable` — **qualifié** : 1042 vaut aussi
`ActiveAbilityType.FlailSwing` et `EffectType.HailOfLivingAmmunition_ExtraHits`.
`isTemporary: 1` ⇒ collection `BaseUnitComponent+0x48`, et **aucun événement diffusé**
(`AddTraitOperation$$Execute` retourne avant la publication quand `isTemporary`).

MESURE live (`combatSnapshot.units[].traits`, l'invoke de `UnitExtensions$$HasTrait` par valeur
d'enum) : `u81` passe de `[16, 26, 1014, 1043, 1061]` à `[16, 26, 1014, **1042**, 1043, 1061]` au
cast ; idem `u85` ; `u83` (`spaceWulfen`) porte déjà 1042 au kit → inchangé.

⇒ **la LECTURE des deux sens est déjà acquise** : le substrat d'entité (`entity_trait_names`, seedé
par `snapshot._load_unit_traits`) reflète l'ajout ET le retrait, et c'est ce même substrat que
consomme le seul consommateur natif du trait, l'exemption de mouvement
`services/static_battle_rules.py::_MOVEMENT_EXEMPT_TRAIT_IDS` (mirror
`StaticBattleRules.Effect$$NotBlockingMovementOfTraits` : Mounted/Vehicle/Unstoppable pour les
effets de tuile 0/5/17 — cf. `case-205-unstoppable.md`, dont le §2 « aucun consommateur » est
désormais **périmé** : `entities/pathfinding/tile_blocking.py` + `walk_pathfinder.py` portent
l'exemption). Ce qui manque est la **POSE offline**, et elle n'a aucun poseur tant que l'ability
1106 n'est pas portée (résidu §6).

## 4. Le criterion, et le carré qui le tranche

> « Le port applique-t-il — **et retire-t-il** — la contribution de 1222 comme le natif ? », mesuré
> là où l'effet MORD.

`probe_366_r1_war_howl_extra_damage.py`, **deux bras × deux régimes de crit**, live == offline
bit-exact dans les quatre cases (MC1_67 / seed 777, porteur `spaceWulfen`) :

| | 1222 PRÉSENT (cast) | 1222 ABSENT (témoin) |
|---|---|---|
| **`--crit 0,700`** | `[5127, 4801, 5049]` | `[3532, 3206, 3454]` |
| **`--crit 40,700`** | `[5994, 5892, 5171]` | `[4399, 4297, 2788]` |

La ligne `0,700` isole la face DÉGÂT : delta **+1595 = round(886 × 1.80)** sur les trois coups, et
`CouldCrit` reste faux des deux côtés (donc **aucun** tirage de crit) — c'est la case qui prouve le
gate `AmountIsGreaterThanZero`. La ligne `40,700` ouvre le gate : le natif roule à 40 + 36 = 76.

**Le retrait (« et retire-t-il ») est mesuré par construction** : `turns = Get(1)`, l'effet est posé
puis rendu au tour suivant par le natif, et le bras TÉMOIN — même roster, même géométrie, même
attaquant, sans cast — est exactement l'état « après retrait ». Les deux modèles y coïncident : le
port n'a rien laissé collé. Le mode d'échec typique de cette forme (un buff qui colle à vie, cf.
`1171`) est structurellement hors d'atteinte ici, parce que le port ne POSE pas 1222 : il le lit du
seed, et le seed suit le natif.

Généralisation, tous bit-exacts :
* `C1_25` / seed **31337** — board à **élévation**, donc l'additif traverse aussi l'étage %-list :
  delta **+2393 = round(1595 × 1.5)** par coup, les 4 cases vertes ;
* porteur `spaceHound` (4 coups d'arme au lieu de 3) — MC1_67 / 777, delta +1595 sur les 4 coups.

## 5. Vue ROUGE par mutation adversariale — **trois**, verbatim

**R1 — inscription retirée d'`EFFECT_CLASSES`** (`--crits NOCRIT`) :

```
[WARHOWL/NOCRIT/ALIGNED] LIVE    n=3 [5127, 4801, 5049]
[WARHOWL/NOCRIT/ALIGNED] OFFLINE n=3 [3532, 3206, 3454]
[WARHOWL/NOCRIT/ALIGNED] DELTA   [1595, 1595, 1595]
[WARHOWL/NOCRIT/ALIGNED] VERDICT per_hit DIVERGE (attendu : OK)
```

**R2 — gate `AmountIsGreaterThanZero` désarmé** (`--crits NOCRIT`, donc `GetStat(9) == 0`) :

```
[WARHOWL/NOCRIT/ALIGNED] LIVE    n=3 [5127, 4801, 5049]
[WARHOWL/NOCRIT/ALIGNED] OFFLINE n=3 [5994, 5892, 4383]
[WARHOWL/NOCRIT/ALIGNED] DELTA   [-867, -1091, 666]
[WARHOWL/NOCRIT/ALIGNED] VERDICT per_hit DIVERGE (attendu : OK)
```

Le port se met à criter (cc = 0 + 36) là où le natif ne tire même pas.

**R3 — magnitude `extraCritChance` retirée** (`--crits CRIT`, `GetStat(9) = 40`) :

```
[WARHOWL/CRIT/ALIGNED] LIVE    n=3 [5994, 5892, 5171]
[WARHOWL/CRIT/ALIGNED] OFFLINE n=3 [5994, 5892, 4383]
[WARHOWL/CRIT/ALIGNED] DELTA   [0, 0, 788]
[WARHOWL/CRIT/ALIGNED] VERDICT per_hit DIVERGE (attendu : OK)
```

Deux coups déjà bit-exacts : la divergence est localisée au **3ᵉ**, celui qui crite à 76 % et pas à
40 % — mêmes tirages, crits différents. Sous R1, le cliquet
`tests/engine/runner/test_war_howl_extra_damage_live.py` rend **4 failed / 3 passed** : tombent le
test structurel de registre, les deux bras DÉGÂT (deux boards) et le bras CRIT ; restent verts le
TÉMOIN, la comparaison live-vs-live (qui atteste que le natif SÉPARE les deux bras) et le test
tri-état offline (qui instancie la classe directement, donc ne dépend pas du registre).

## 6. Résidus NOMMÉS et MESURÉS

### 6.1 `#366-r1-src` (#382) — le multiplicateur vient de la SOURCE, le port lit le PORTEUR

**Ce cas le MESURE, il ne le corrige pas** (mécanisme partagé par les 135 entrées
d'`EFFECT_CLASSES`, tranche à part entière). La lecture au décompilé est décisive :
`IdunBattle.Configuration.AbilityConfiguration$$TryGetVariableArrayForLevel` — foyer UNIQUE des
quatre accesseurs de variable — lit **les deux** grandeurs sur son argument `abilityState` :

* l'index, par `Idun.Shared.Level$$ToZeroBasedIndex(abilityState)` (champ `+0x0`), clampé à la
  longueur du tableau ;
* et, **pour toute variable listée dans `variablesAffectedByRarityBonus` (`config+0x28`)**, le
  facteur `Fix64(abilityState+0x4) / 100`, avec `Round(AwayFromZero)`.

Or l'`abilityState` d'un effet est `IdunBattle.Entities.Effects.BaseEffect$$GetAbilityState` =
`IdunBattleLogic.Entities.DSLSelectors$$AbilityStateFromEffect(<nœud EFFET>)`, c.-à-d. celui **baké
à la pose** — donc celui de la SOURCE. `EffectsState.seed` du port, lui, est clé PAR PORTEUR.

`extraDmg` **est** dans `variablesAffectedByRarityBonus`, et les multiplicateurs diffèrent
(MESURE live, seed 777 / MC1_67 / rank 17 : `spaceBlackmane` = **200**, `spaceWulfen` et
`spaceHound` = **180**). L'écart est donc RÉEL et non nul, contrairement à `1224` où seul
`extraCritDmg` était scalé :

```
[WARHOWL/NOCRIT/SRCMULT] attaquant u83 cc=0 mult_porteur=180 | source u81 mult_source=200
[WARHOWL/NOCRIT/SRCMULT] LIVE    n=3 [5304, 4978, 5226]
[WARHOWL/NOCRIT/SRCMULT] OFFLINE n=3 [5127, 4801, 5049]
[WARHOWL/NOCRIT/SRCMULT] DELTA   [177, 177, 177]
```

**+177 par coup = 886 × 2.00 − round(886 × 1.80) = 1772 − 1595.** Repro :
`probe_366_r1_war_howl_extra_damage.py --arms WARHOWL --crits NOCRIT --mult SRCMULT
--expect-diverge`. Le bras de référence l'annule en imposant le même
`AbilityVariablesMultiplierPercentage` aux deux (`--unit-stat`), et une garde d'exécution REFUSE de
mesurer si le patch n'a pas pris. L'axe CRIT en est exempt (`extraCritChance` n'est pas scalé).

### 6.2 Le NIVEAU d'ability ACTIVE n'est pas propagé au seed

`EffectsState.seed` ne propage que `ability_variables_multiplier` et `ability_level`
(= `unitConfig.passiveAbilityLevel`) : `active_ability_level` vaut **None sur tout effet SEEDÉ**.
Les 18 autres classes qui lisent une ability ACTIVE emploient déjà le repli
`active_ability_level if not None else ability_level`, et ce port fait pareil. Sous
`buildNormalizedBC` les deux valent 50 ⇒ écart numériquement nul, non observable dans nos harnais.
Même famille que §6.1, même tranche à ouvrir.

### 6.3 La POSE (`AddEffect` + `ApplyInternal`/`RevertInternal`) n'est pas portée

Un moteur 100 % offline ne posera jamais 1222 de lui-même : ni l'ability `WarHowl` (1106, backlog
`[1106 WarHowl | spaceBlackmane]`) ni les faces `AddTrait`/`RemoveTrait` de l'effet ne sont portées.
Ce cas ferme la **LECTURE** (quand le natif l'a posé, le port en compte la contribution) et pas la
pose. **À câbler dans la tâche 1106**, dans le même commit que l'ability : le couple
`AddTrait(Unstoppable, isTemporary)` / `RemoveTrait` — c'est-à-dire exactement une paire, jamais
l'une sans l'autre.

### 6.4 Face PRÉDICTION du canal crit-chance

`services/damage_prediction.py` n'appelle `crit_chance_bonus_from_effects` nulle part
(`could_crit(ctx.crit_chance, …)` seul) : le +extraCritChance n'entre pas dans la prédiction de
dégât. Gap PRÉEXISTANT du canal, pas de ce port — aucun effet ne l'alimentait avant.

## 7. Ce qui n'est PAS couvert

* **Le sélecteur de pose** (`UnitsWithoutRangedWeapons`, `UnitsWithoutTrait(Summon)`) est LU au
  décompilé et RECOUPÉ live (5 unités, 3 buffées), mais pas porté — il appartient à la tâche 1106.
* **Le porteur == source** (Ragnar lui-même) n'est pas mesuré : son activation part au cast. Le
  chemin de code est le même à un seed près ; ce qui n'est pas mesuré, c'est cette coïncidence.
* **Le canal `create_effect_crit_chance_bonus_for_attack` ne balaie que les effets de l'ATTAQUANT**
  alors que le natif énumère les entités porteuses d'effets de tout l'état (même limite que
  `crit_damage_bonus_from_effects`). Sans conséquence pour 1222, dont le trigger commence par
  `get_OwnerIsCaster`.
* **Le vecteur OVERWATCH** n'est pas exercé : il passe par `damage_ops/normal.py` avec
  `_ranged = True`, donc les deux gates `IsMeleeAttack` se ferment — conforme au natif, non mesuré.
