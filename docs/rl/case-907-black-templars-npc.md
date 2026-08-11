# #907 — `1044 IncendiaryShells` PORTÉE, `1053 DevoutPush` RE COMPLÈTE / PORT REFUSÉ

Deux actives Black Templars à porteurs `[NS]` (un npc, un summon). Une est portée et confrontée
live ; l'autre appelle un nœud DSL **absent du port**, donc son port est refusé — sa RE est ici,
entière, et le résidu `#907-r1` la porte.

## 1. Le montage : trois voies, et laquelle chaque ability autorise

| ability | npc | summon | summon INVOCABLE ? | voie retenue |
|---|---|---|---|---|
| `1044 IncendiaryShells` | `templNpc2Neophyte` | `templNeophyte` | **NON** | `--explicit-stats templNpc2Neophyte:45` |
| `1053 DevoutPush` | `templNpc1Initiate` | `templInitiate` | **oui** (`EnvFactionSummons:BlackTemplars` / `:SpaceWolves`, `nrOfSummons = 3`) | — (port refusé) |

**Mesure** (balayage EXHAUSTIF du gameconfig, toutes sections) : `templNeophyte` n'apparaît que dans
sa **propre** entrée `units` — **aucune** ability ne le cite, ni par `unitToSpawn`, ni par `unitId`,
ni par `unitId_2`. La voie « spawner son invocateur » n'existe donc pas pour 1044 : la voie NPC
n'est pas une commodité, c'est la **seule**. `templInitiate`, lui, est bien invoqué (4 occurrences,
deux `EnvFactionSummons`) — mais son ability n'est pas portable pour une autre raison (§3).

`--explicit-stats` monte le porteur avec SES stats (`units.npc[id].stats[]` →
`Health 9796`, `Damage 6555`, `FixedArmor 1942`, `ActiveAbilityLevel 65`,
`AbilityVariablesMultiplierPercentage 200`), SES traits et SES armes. **Aucune greffe.**

## 2. `1044 IncendiaryShells` — PORTÉE

### L'arbre natif, tel que LU

`IdunBattleLogic.Entities.Abilities.Active.Loki.IncendiaryShellsAbility$$ExecuteBehaviour` :

```
hits    = AbilityConfiguration.GetNumberConstant(config@this+0x60, 0x2f = nrOfHits)   -> 3
minDmg  = AbilityConfiguration.GetVariableForLevel(config, 0xc = minDmg, AbilityState, 0)
maxDmg  = AbilityConfiguration.GetVariableForLevel(config, 0xd = maxDmg, AbilityState, 0)
dmg     = DSLFormulas.RandomAmount(minDmg, maxDmg)
profile = AbilityConfiguration.GetDamageProfile(config)     # Nullable<DamageProfileType> -> Flame

[A] atk    = DSLBehaviors.AttackWithAttackDamage(
                 caster = Caster@DSLSelectors+0x48, target = Target@+0x60, amount = dmg,
                 damageProfile = profile, hits = hits            # surcharge `hits:System.Int32`
                 abilityOrEffect = AbilityOrEffect(this+0x10),
                 options = Nullable<AttackDamageBehaviourOptions> VIDE (HasValue = 0),
                 selectionType = 2 = UnitSelectionType.OnlyTargetable)
[B] inform = DSLBehaviors.InformWeapon(damageProfileType = profile, isMelee = 0, useSpecial = 0)

AActiveAbility.ExecuteAtomic(this, [B] op_BitwiseAnd [A], entities,
                             groupType = 0x51 = GroupType.IncendiarySheels_AtomicGroup)
```

`AActiveAbility$$MinMaxDamage(this, abilityState, isPrediction: 0)` construit **exactement**
`RandomAmount(GetVariableForLevel(0xc), GetVariableForLevel(0xd))` — ce que `ExecuteBehaviour`
recopie inline. Le mode « bornes » de la feuille du port est donc le mirror exact.

`IncendiaryShellsAbility$$GetDamageRange` est la surcharge de **prédiction** (face DÉCISION, hors
tranche) et elle DIVERGE : `random: 0` → `Divide(Sum(Get(min), Get(max)), Get(2))` = la moyenne ;
`random: 1` → `RandomAmount(min, max)`. Aucun nœud de l'arbre d'exécution ne l'appelle.

### La catégorie annoncée est juste, et c'est une coïncidence à nommer

`combat-ability-coverage.md` classe 1044 en `DAMAGE(Flame)`. Le porteur ne porte **aucune** arme
Flame (gameconfig : mêlée `Physical` 1 coup, ranged `Projectile` portée 2, 2 coups) : le `Flame`
vient d'`abilities.IncendiaryShells.constants.damageProfile`, que le natif lit par
`GetDamageProfile(config)`. La colonne tombe juste parce que l'audit lit aussi la config d'ability,
pas parce que l'arme le dirait.

### Le bug trouvé : `attackRangeType` ABSENT ⇒ `is_melee=None`, pas `False`

**Les deux `isMelee` de cet arbre ne sont pas le même objet.**

* `InformWeapon(profile, isMelee: 0, useSpecial: 0)` — un **littéral de call-site**, LU au
  décompilé. Il alimente le tag de flux `TagKey.Attack_Weapon_IsMelee`. Il vaut `False`.
* `AttackWithAttackDamage(..., is_melee=…)` — ce paramètre ne mirror **aucun** argument du
  call-site : il mirror `IdunBattle.Core.Services.BattleQuery$$IsMeleeAttack`, que le natif DÉRIVE
  de `GetAbilityAttackRangeType`. Or **la config 1044 n'a pas d'`attackRangeType`** — contraste
  MESURÉ avec ses quatre voisines de patron, toutes `Ranged` : 1048 Fragstorm, 1080 HellfireShells,
  1051 Stikkbomb, 1098 PlasmaGrenade. `rangeType = 0` rend `IsMeleeAttack` **et** `IsRangedAttack`
  FAUX ⇒ nature **non déclarée** ⇒ `is_melee=None` (convention déjà posée par `1168 EntropyCannons`).

Écrire `False` n'est pas un synonyme prudent de `None` : le port lit le tri-état
(`c.get("is_melee") is not False` dans
`BigTargetAdjacentEffect.create_aura_hits_malus_for_defense`), donc un booléen **arme** les gates
`IsRangedAttack` que le natif laisse muets.

**Mesure** — montage `libre`, cible `eldarRanger`, `astraBullgryn` (trait `BigTarget`) adjacent :

| | coups | séquence |
|---|---|---|
| natif | **3** | `[6131, 5852, 6311]` |
| port `is_melee=False` (avant) | **2** | `[6131, 5852]` |
| port `is_melee=None` (après) | **3** | `[6131, 5852, 6311]` |

Étage fautif : `IdunBattle.Entities.Effects.Loki.BigTargetAdjacentEffect$$CreateEffectHitsBonusForAttack`
= `ForAdditionWithMinimum(OwnerIsTarget & IsRangedAttack, Direct(-1), min = Direct(1))`.

### Le masque — forme STATIC-COPY, preset `+0x140`

`…IncendiaryShellsAbility$$.ctor` n'appelle **aucun** `TargetingOptions$$.ctor` : il recopie les
0x40 octets du champ statique `TargetingOptions` statics `+0x140` puis
`AActiveAbility..ctor(this, &opts, 0)`. **LU AU DÉSASSEMBLAGE**, pas au pseudo-C :
`movups xmm0,[rax+0x140]` … `movups xmm1,[rax+0x170]` (quatre paires 16 octets = le preset entier),
précédé de `xor r9d,r9d` / `xor r8d,r8d` — ce dernier EST le littéral d'`AbilityAttackType`.

Preset lu dans `IdunBattle.Core.Services.TargetingOptions$$.cctor` :

```
+0x140 isSelfCasting    = 0
+0x148 range            <- `TargetingRange` statics `+0x18` = RANGE_FROM_CONFIG  -> range = 2
+0x160 forceMeleeTarget = 0 = RangedBool.True          <- ARME le clamp de melee
+0x168 rules            = 0x4002
```

Décomposition EXHAUSTIVE : `0x2 TargetMatchesDynamicRule` (pas de surcharge de
`GetDynamicInvalidTargetReason` → défaut 0, dégradation permissive) + `0x4000 TargetIsEnemy`
(PORTÉ). Somme exacte, aucun bit résiduel.

**Trois sources concordantes**, dont une LIVE et indépendante de ghidra :
`docs/rl/case-302-4/tile-target-population.json` ligne 1044 → `state=measured`, `form=static-copy`,
`preset=320` (= 0x140), `rules=16386` (= 0x4002).

`AbilityAttackType` = **0 `DirectTargetAttack`** (3ᵉ argument, `xor r8d, r8d`).

## 3. `1053 DevoutPush` — RE COMPLÈTE, PORT REFUSÉ

### L'arbre natif, tel que LU

`IdunBattleLogic.Entities.Abilities.Active.Loki.DevoutPushAbility$$ExecuteBehaviour` :

```
[A] atk  = DSLBehaviors.UseActiveAbility(
               caster            = Caster@DSLSelectors+0x48,
               target            = Target@+0x60,
               activeAbilityType = DSLSelectors.UnitNormalAttackType(Caster@+0x48),
               parentAbility     = Nullable(AbilityOrEffect(this+0x10)),   # HasValue = 1
               triggerAbilityOrEffect = null,  options = ZEROES)
[B] kill = DSLBehaviors.Kill(
               killer  = Caster@+0x48,
               targets = DSLSelectors.DeadUnits(DSLSelectors.Tiles(Target@+0x60)),
               options = 0)
[C] move = DSLBehaviors.PerformAIMovement(
               unit           = Caster@+0x48,
               range          = DSLFormulas.Direct(1),
               overrideUtility = this+0xf0)          # construit au `.ctor`, cf. ci-dessous

AActiveAbility.Execute(entities, this, ([A] op_Addition [B]) op_Addition [C])
```

i2 mot à mot : « Executes a normal melee attack on a single target, then gets to move 1 additional
hex. » — appariement : [A] = l'attaque normale, [C] = le +1 hex. [B] n'apparaît pas dans l'i2 : c'est
la matérialisation de la mort si l'attaque a tué (`Kill` sur les `DeadUnits` des tuiles de la cible).

**LA CATÉGORIE ANNONCÉE EST FAUSSE SUR LES DEUX AXES.** `combat-ability-coverage.md` classe 1053 en
`EFFECT/BUFF` : l'arbre ne pose **aucun** effet et n'applique **aucun** buff. Il FRAPPE (par
l'attaque NORMALE de l'unité, dont le profil vient de l'ARME — `Chain`, 2 coups) puis DÉPLACE.
La config 1053 n'a **ni** `variables`, **ni** `constants`, **ni** `attackRangeType` : c'est la
config la plus vide du lot (`{id, upgrades, variables}` seuls).

### `this+0xf0` — la `UtilityDefinition` construite au ctor

`…DevoutPushAbility$$.ctor` (LU au désassemblage) :

```
new UtilityBucket[1]
UtilityBucket..ctor(bucket, utilityType = 0x35, minUtilityDifference = <struct ZÉRO>)
                                  # 0x35 = 53 = UtilityType.DevoutPush_AdjacentRangedEnemies
buckets[0] = bucket
this+0xf0 = new UtilityDefinition(buckets)
puis AActiveAbility..ctor(this, &<preset +0x40>, 0)      # `xor r8d,r8d` -> DirectTargetAttack
```

### Le masque — forme STATIC-COPY, preset `+0x40`

```
+0x40 isSelfCasting    = 0
+0x48 range            <- `TargetingRange` statics `+0x30` = RANGE_ADJACENT
+0x60 forceMeleeTarget = 1 = RangedBool.False
+0x68 rules            = 0x4000 = TargetIsEnemy SEUL
```

Confirmé LIVE : `tile-target-population.json` → `preset=64`, `rules=16384`, `form=static-copy`.
`AbilityAttackType` = **0 `DirectTargetAttack`** (`xor r8d, r8d`).
Le masque **reste** dans `TARGETING_OPTIONS_UNPORTED` (la face COMBAT n'est pas portée) — le contrat
de disjonction est donc respecté en l'état.

### `IdunBattle.AI.Utilities.DevoutPush_AdjacentRangedEnemies` (UtilityType 53)

Remis en C# depuis
`…DevoutPush_AdjacentRangedEnemies.u003CEvaluateMovementInStepsu003Ed__2$$MoveNext` :

```csharp
IEnumerator<Fix64> EvaluateMovementInSteps(UtilityMovementCase c) {
    if (c.unit != null
        && EntityExtensions.GetMainTile(c.unit, this.<+0x10>) == c.UnitPosition.get_MainTile()) {
        yield return Fix64.FromInt(-10);       // rester SUR PLACE est penalise de 10 (litteral)
        yield break;                           // un seul pas dans cette branche
    }
    var subject = DSLSelectors.Get(sel, c.unit);
    var tileEnt = DSLSelectors.Get(sel, c.UnitPosition.get_MainTile());   // la tuile CANDIDATE
    var adj     = DSLSelectors.AdjacentUnits(tileEnt, unique: 1, 3);
    var enemies = DSLSelectors.Enemies(subject, adj, 3);
    int v = 0;
    foreach (u in enemies.SelectAllUnits(<AbilityEntities ZÉRO>, 3))
        v += UnitExtensions.HasRangedWeapon(u, false)
             ? weights["DEVOUTPUSH_AdjacentRangedEnemy"]     // +50
             : weights["DEVOUTPUSH_AdjacentMeleeEnemy"];     // +30
    yield return Fix64.FromInt(v);
}
```

Les deux clés BC sont résolues **100 % offline** (`probe_212_bc_key_literals.py --symbol <le symbole
ci-dessus>`) et recroisées avec `data/seed-bc.json` :
`Utilities.Default.DevoutPush_AdjacentRangedEnemies = {"DEVOUTPUSH_AdjacentRangedEnemy": 50,
"DEVOUTPUSH_AdjacentMeleeEnemy": 30}`. **Poids POSITIFS** : l'utilité PRÉFÈRE les tuiles adjacentes
à des ennemis, deux fois plus fort pour un porteur d'arme à distance — c'est le « push » du nom.

### Pourquoi le port est REFUSÉ

Sur les cinq nœuds de l'arbre, **quatre sont portés** (`UseActiveAbility`, `UnitNormalAttackType`,
`Kill`, `DeadUnits`, `Tiles`). Le cinquième, `PerformAIMovement`, ne l'est pas — et sa chaîne non
plus :

| pièce | état |
|---|---|
| `DSLBehaviors$$PerformAIMovement(unit, range, overrideUtility)` → `PerformAIMovementBehaviour` | **ABSENTE** |
| `Core.Services.OperationProcessor$$ComputerMovementAction(unit, overrideRange:Nullable<int>, overrideTileUtility)` → `ComputerActionOperation$$ExecuteMovementFor` → slot d'interface `AiControl` | **ABSENTE** (le port a la voie TOUR COMPLET — `ComputerActionOperation.execute` — pas la voie MOUVEMENT SEUL) |
| `UtilityType.DevoutPush_AdjacentRangedEnemies` (53) | **ABSENTE** (52 `SwornProtector_AvoidAdjacentEnemies` et 54 `RammingSpeed_MostAdjacentEnemies` le sont) |
| la `UtilityDefinition` à un bucket du `.ctor` | **ABSENTE** |

⚠ **`PerformAIMovementBehaviour$$.ctor` est un corps DÉDUPLIQUÉ** — `stormboyz_strike.py` le
documente déjà : ses trois champs `+0x50/+0x58/+0x60` et ses noms de paramètres sont partagés avec
`IfBehaviour$$.ctor`. Le mapping ci-dessous vient donc du **corps d'`Execute`**, pas du ctor :

```
+0x50 unit (ITargetsSelector)       -> Select(entities, selectionType 3)
+0x58 range (IAmountFormula)        -> Calculate(entities) -> int
+0x60 overrideUtility               -> passé tel quel à ComputerMovementAction
+0x68 utilitySelector               -> SelectFirst(entities)   \ ÉCRIVENT +0x60 quand tous deux
+0x70 utilityFactory (délégué)      -> délégué(+0x68)          / non nuls -- NULS chez 1053
foreach (u in +0x50) processor.ComputerMovementAction(u, Nullable(range), this+0x60)
```

Porter seulement [A] et [B] donnerait l'attaque normale sans le +1 hex : un port à moitié fidèle
qui ne casse aucun test et dégrade en **silence**. Refusé. En l'état, 1053 est hors
`ABILITY_CLASSES` — son cast est un no-op complet, ce qui est **visible** (aucune attaque non plus).

## 4. Ce que les témoins discriminent, et ce qu'ils ne discriminent pas

`probe_907_incendiary_shells.py` (volets `spawn` / `gate` / `degat`), garde
`tests/engine/runner/test_907_incendiary_shells_live.py`.

**GATE — 10/10 lignes d'accord natif/port**, sur deux géométries, contre l'oracle `abilityReason`
(`TargetingQuery$$GetInvalidTargetReason`) :

| géométrie | cible | d | natif | port |
|---|---|---|---|---|
| libre | caster + allié | 0, 1 | `0x4000 TargetIsEnemy` | idem |
| libre | ennemi | 2 | `0x0` **ACCEPTÉ** | idem |
| libre | ennemis | 3, 4 | `0x8000000 TargetIsInRange` | idem |
| mêlée | ennemi au contact | 1 | `0x0` | idem |
| mêlée | **le même ennemi qu'en libre** | 2 | `0x8000000` **BASCULE** | idem |

La dernière ligne est le clamp de `TargetingQuery$$GetRange` (`v = min(1, v) ; onlyAdjacent = true`),
armé par `forceMeleeTarget = RangedBool.True`.

**Contrefactuels du masque** — chacun doit changer au moins une ligne :

| champ basculé | libre | mêlée |
|---|---|---|
| `force_melee_target` → `RangedBool.False` | AVEUGLE (attendu : pas de clamp à armer) | **1 ligne** |
| `range` → `RANGE_ADJACENT` | **1 ligne** | AVEUGLE (attendu : déjà rabattu à 1) |
| `rules` sans `TargetIsEnemy` | **2 lignes** | **2 lignes** |
| `TARGETING_OPTIONS = None` | **4 lignes** | **4 lignes** |

Les deux AVEUGLE sont **structurels** : les deux champs de portée s'excluent par géométrie, et
c'est précisément pourquoi il en faut deux.

**DÉGÂT — accord bit-exact sur DEUX régimes d'armure**, séquence coup par coup :

| régime | natif = port |
|---|---|
| `armure = 0` | `[6131, 5852, 6311]` |
| `armure = 3000` | `[1631, 1463, 1811]` |

Mutants de l'arbre, rejoués sur un `State` rechargé du **même** instantané :

| mutant | armure 0 | armure 3000 |
|---|---|---|
| `hits = 2` | MORD | MORD |
| `native_factory = "ability"` (1 tirage/coup) | MORD | MORD |
| `is_melee = False` (nature déclarée RANGED) | **MORD** — c'est lui qui a trouvé le bug | MORD |
| `profile = Physical` | **AVEUGLE** (perçage inerte à armure 0) | MORD |
| `is_melee = True` (nature déclarée MÊLÉE) | **AVEUGLE** | **AVEUGLE** |

Le premier AVEUGLE est **levé** par le régime armure — c'est pour ça qu'il y en a deux. Le second
ne l'est pas : `True` désarme l'aura `BigTargetAdjacent` (qui exige `is_melee is False`) et n'arme
rien d'autre dans ce montage — aucun porteur de `Parry` (aucune unité du gameconfig ne porte ce
trait), aucun `ExtraHitsMelee` sur le caster. `True` et `None` **coïncident** ici. Nommé, pas tu.

## 5. Ce qui n'est PAS couvert

* la face **DÉCISION** de 1044 (`IncendiaryShellsPlaybook$$MakeDamagePredictions` +
  `IncendiaryShellsAbility$$GetDamageRange`, qui rend la MOYENNE et non un tirage) — hors tranche ;
* `selectionType = OnlyTargetable` (2) de l'attaque de 1044 : la feuille du port collapse le
  sélecteur mono-cible sur `ctx.target`. Sans effet observable (la cible du message est vivante par
  construction), mais **écart nommé** ;
* le trait de profil `Flame.Traits = ["OnFire"]` (pose de feu on-hit) : porté ailleurs
  (`OnFireDamageAbility`, `entities/damage_trait.py`), **non confronté par cette tranche** ;
* le porteur SUMMON `templNeophyte` : aucun invocateur, donc **jamais** confrontable en bataille ;
* tout `1053 DevoutPush` — cf. `#907-r1`.
