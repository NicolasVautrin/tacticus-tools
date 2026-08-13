# #996-r1 — `1053 DevoutPush` PORTÉE, `1015 PrecisionShot` PORT REFUSÉ (et pourquoi c'est mesuré)

**Build** : `rnca9r7q6c`. **Source** : `mcp__ghidra__decompile_function` — décompilé = vérité, live
= confirmation. Fiche de reconnaissance amont :
`docs/rl/case-996-six-no-op-silencieuses-reconnaissance.md`. RE antérieure de 1053 :
`docs/rl/case-907-black-templars-npc.md` §3 — dont le **VERROU est PÉRIMÉ**, cf. §1.

## 0. Ce que la tranche établit

| id | verdict |
|---|---|
| `1053 DevoutPush` | **PORTÉE et CONFRONTÉE LIVE** — attaque bit-exacte + tuile d'arrivée en accord, gate 5/5 |
| `1015 PrecisionShot` | **PORT REFUSÉ**, pour une raison MESURÉE (§3) — résidu `#996-r1-r3` |

Trouvés en chemin, dans des foyers PARTAGÉS, tous deux **invisibles sans erreur** :

* `PerformAIMovement` rendait `units = []` pour tout sélecteur unit-domain **NU** (§2.1) ;
* `build_from_state(max_distance = N)` rabattait **tout `N` non nul sur `0`** (§2.2) — donc
  `1144 BioMinefield`, qui passe déjà `Direct(1)`, ne pouvait pas bouger non plus.

## 1. Le verrou de #907 n'existe plus — re-mesure, pas relecture

`case-907` §3 refusait le port de 1053 parce que **quatre pièces manquaient**. Re-mesuré à
`bcd6215c` :

| pièce | état #907 | état mesuré |
|---|---|---|
| `DSLBehaviors$$PerformAIMovement` → `PerformAIMovementBehaviour` | ABSENTE | **portée** (`behaviours/ai_control.py`, arrivée avec #939) |
| `OperationProcessor$$ComputerMovementAction` → `ComputerActionOperation$$ExecuteMovementFor` | ABSENTE | **portée** (`runner/operations/summon_ai.py::ComputerMovementActionOperation`) |
| `UtilityType.DevoutPush_AdjacentRangedEnemies` (53) | ABSENTE | **portée par CETTE tranche** (`engine/utilities/devout_push.py`) |
| la `UtilityDefinition` à un bucket du `.ctor` | ABSENTE | **portée** (tuple `DEVOUT_PUSH_MOVE_UTILITY`) |

`DSLSelectors$$DeadUnits` et `$$Tiles` sont eux aussi portés (`entities/selectors/units.py`) —
`case-996` les annonçait manquants. **Une fiche de blocage se re-mesure avant d'être crue.**

## 2. `1053 DevoutPush` — l'arbre, et les deux étages qu'il a réveillés

`IdunBattleLogic.Entities.Abilities.Active.Loki.DevoutPushAbility$$ExecuteBehaviour`, RELU pour
cette tranche :

```
[A] atk  = DSLBehaviors.UseActiveAbility(
               caster = Caster@DSLSelectors+0x48, target = Target@+0x60,
               activeAbilityType = DSLSelectors.UnitNormalAttackType(Caster@+0x48),
               parentAbility = Nullable(AbilityOrEffect(this+0x10)), trigger/options ZÉROÉS)
[B] kill = DSLBehaviors.Kill(Caster@+0x48, DSLSelectors.DeadUnits(DSLSelectors.Tiles(Target@+0x60)), 0)
[C] move = DSLBehaviors.PerformAIMovement(Caster@+0x48, DSLFormulas.Direct(1), this+0xf0)

AActiveAbility.Execute( entities, this, ([A] op_Addition [B]) op_Addition [C] )
```

⚠ **La SURCHARGE d'`UseActiveAbility` se tranche aux XREFS ENTRANTES**, jamais au pseudo-C : les
deux ont sept paramètres et le même nom affiché. `DevoutPushAbility$$ExecuteBehaviour` appelle
celle qui prend un **sélecteur** ; `PrecisionShotAbility$$ExecuteBehaviour` appelle celle qui prend
un `ActiveAbilityType` **entier** et l'emballe dans un `DirectAbilitySelector`.

⚠ **`DeadUnits(Tiles(Target))` prend `UnitSelectionType.Any` (0) aux DEUX étages**, lu aux slots
d'interface (`metadata/interface_slots.tsv`) : `UnitsMainTilesSelector$$Select` appelle le slot **3**
`SelectAllUnits` avec `selectionType = 0`, `DeadUnitsSelector$$Select` le slot **4**
`SelectUniqueUnits` avec `selectionType = 0`. Un `3` recopié par symétrie du reste du module aurait
**vidé** la source — la cible qu'on vient de tuer n'est plus vivante.

**`this+0xf0`** (`.ctor`, lu au désassemblage) : `new UtilityBucket[1]` ;
`UtilityBucket..ctor(bucket, 0x35, <struct ZÉRO>)` — `0x35` = 53 =
`UtilityType.DevoutPush_AdjacentRangedEnemies` ; `this+0xf0 = new UtilityDefinition(buckets)` ; puis
`AActiveAbility..ctor(this, &<preset +0x40>, 0)`.

### La feuille 53, remise en C# depuis son `MoveNext`

```csharp
IEnumerator<Fix64> EvaluateMovementInSteps(UtilityMovementCase c) {
    if (c.unit != null && GetMainTile(c.unit) == c.UnitPosition.get_MainTile()) {
        yield return Fix64.op_Implicit(-10);      // LITTÉRAL de code, PAS une clé BC
        yield break;
    }
    enemies = Enemies(Get(c.unit), AdjacentUnits(Get(c.UnitPosition.MainTile), unique:1, 3), 3);
    int v = 0;
    foreach (u in enemies.SelectAllUnits(<AbilityEntities ZÉRO>, 3))
        v += HasRangedWeapon(u, null) ? weights["DEVOUTPUSH_AdjacentRangedEnemy"]     // 50
                                      : weights["DEVOUTPUSH_AdjacentMeleeEnemy"];    // 30
    yield return Fix64.op_Implicit(v);
}
```

Les deux clés BC sont résolues **100 % offline** (`probe_212_bc_key_literals.py --symbol …`) et
recroisées avec `data/seed-bc.json`. **Contraste mesuré avec les deux voisines** : `52 SwornProtector`
prend `get_UnitOrParent` pour sujet (pas `case.unit` nu) ; `54 RammingSpeed` compte **en bloc**, un
seul poids. Recopier l'une ou l'autre aurait donné un score faux.

### 2.1 `PerformAIMovement` rendait `units = []`, sans erreur

`execute` faisait `self.selector.evaluate(entities) or []` puis filtrait `isinstance(u, dict)`. Un
accesseur unit-domain comme `Caster()` rend un **dict nu** (`ctx.caster`) : l'itérer rend ses
**clés** — des chaînes — que le filtre jetait. Le natif, lui, appelle `this.unit.Select(...)`, dont
le type de RETOUR est une liste quel que soit le sélecteur. Invisible tant que l'unique call-site
porté (`1144 BioMinefield`) passait `EntitiesWithoutEffects(...)`. Réparé par `_units_of`, le
normaliseur déjà utilisé par `Kill`, `UseActiveAbility` et les feuilles d'effet.

### 2.2 `build_from_state(max_distance = N)` rabattait tout `N` non nul sur `0`

VERBATIM (`IdunBattle.Core.Services.MovementQuery$$FindAnyOrAllMoveableTiles`) :

```
range = options.overrideRange.HasValue ? options.overrideRange.Value
                                       : StatComponent.get_CurrentValue(<stat Movement>);
```

L'override est une **profondeur de flood-fill**, pas un interrupteur. Chaîne relue en entier :
`ABaseAiUnitTactic$$GenerateActionTiles` → `BattleQuery$$GetCurrentAndMovablePositionsFor` (qui
remplit `MovementOptions.overrideRange` à `options+0x04`) → `MovementQuery$$GetMovablePositionsFor`
→ `$$GetMovableTilesFor` → `$$FindAnyOrAllMoveableTiles`. Le site portait la prémisse écrite
« seules `None` et `0` ont un call-site natif » — **fausse au moment même où elle a été écrite**.

### 2.3 Confrontation LIVE

Montage : `probe_996r1_devout_push.py`, board `MC1_67`, seed 999, porteur NPC **réel**
`templNpc1Initiate:45` (`--explicit-stats`, aucune greffe). Caster **DRIVÉ** en `(3,4)` — son spawn
`(1,0)` est un coin à trois voisins dont un occupé, géométrie qu'aucun montage ne rend
discriminante. Ennemis placés pour que le spectre d'utilité soit non dégénéré.

Spectre mesuré (`probe_996r1_move_diag.py`) sur les 6 candidates :
`(4,4) = 50` (ennemi RANGED adjacent) · `(2,3)/(2,4)/(4,3) = 30` (MÊLÉE) · `(3,5) = 0` ·
`(3,4)` courante `= -10`. **Argmax = (4,4).**

| | attaque normale | position |
|---|---|---|
| natif | `[5508, 5720]` | `(3,4) -> (4,4)` |
| port AVANT §2.1/§2.2 | `[5508, 5720]` | `(3,4) -> (3,4)` — **ne bouge pas** |
| port APRÈS | `[5508, 5720]` | `(3,4) -> (4,4)` — **accord** |

**GATE — 5/5** contre l'oracle natif `abilityReason.targetReason.hex`
(`TargetingQuery$$GetInvalidTargetReason`) : alliés `0x4000 TargetIsEnemy`, ennemi adjacent `0x0`,
ennemis à `d = 2` `0x8000000 TargetIsInRange`.

**Mutants** — 7 sur 8 MORDENT sur la tuile d'arrivée : `override_utility=None`, nœud [C] retiré
(l'arbre que #907 refusait), utilité 54 RammingSpeed, `range=0`, poids INVERSÉS, clé RANGED absente.
Le seul AVEUGLE est **nommé** : retirer la clé MÊLÉE laisse `(4,4)` à 50 face à des 0, donc le même
argmax. Contrefactuels du masque : `rules` sans `TargetIsEnemy` écarte 2 lignes,
`rules | TargetIsFriendly` en écarte 3 ; `range` et `force_melee_target` sont **AVEUGLES sur cette
géométrie** (caster mêlée-seul, donc aucun clamp `RangedBool` à armer).

### 2.4 Ce qui n'est PAS couvert par ce port

Le natif émet **deux `UnitDamaged` de plus**, tous deux **hors de l'arbre de 1053**. Ventilés par
leurs tags (jamais par un total agrégé) :

* `Passive_Ability_Type = 1083 HeavyBoltPistol` — 2182 sur la cible. C'est exactement **#478-r3**,
  déjà ouvert : le coup de pistolet n'est inséré que sur la voie MESSAGE
  (`DamageHandler.visit_AttackUnitMessage`), pas sur les portes qui appellent
  `AttackDamageOperation.execute` directement — dont `UseActiveAbility`. Ce port en fournit le
  **premier datapoint chiffré**.
* `Effect_Type = 1009 Overwatch_AutoAttack` — 2323 sur le caster. Le port l'émet bien (`after_move`,
  **1872**) : l'écart de MONTANT est **cohérent** avec le décalage de flux `state.rng` qu'introduit
  le tirage manquant du premier — **cohérent, PAS ÉTABLI**.

Non couvert aussi : le porteur SUMMON `templInitiate` (invoqué par
`EnvFactionSummons:BlackTemplars` / `:SpaceWolves`) — la confrontation passe par le NPC ; et le
`Kill` [B], **inerte** côté port pour deux raisons indépendantes (§ docstring de
`devout_push_dead_units_on_target_tiles`), dont un trou du mirror `DeadUnits` → résidu
**`#996-r1-r1`**.

## 3. `1015 PrecisionShot` — PORT REFUSÉ, et la raison est MESURÉE

### L'arbre, tel que lu

```
AActiveAbility.Execute(
   DSLBehaviors.UseActiveAbility( caster = Caster@DSLSelectors+0x48,
                                  target = Caster@+0x48,           # <- le CASTER, pas la cible
                                  activeAbilityType = 0x3f4 = 1012 PrecisionShot_Aim,
                                  parentAbility = Nullable(AbilityOrEffect(this+0x10)),
                                  <opts ZÉRO>, <opts ZÉRO> ) )
```

C'est **tout** le cast — il ne frappe pas. La surcharge appelée est celle à `ActiveAbilityType`
entier, qui construit `AbilityTypeSelector.DirectAbilitySelector(AbilityOrEffect(1012))`.

### La règle dynamique de caster, et son inverse chez les deux sœurs

Le retour de `GetDynamicInvalidCasterReason` est un **`IdunBattle.Core.Services.TargetingRule`**
(type de retour lu dans `frida/methods.tsv`) — un bit de règle rompue, pas un booléen. Les trois
corps, lus **aux octets** (le pseudo-C d'un `cmovne`/`sbb` se prête à l'erreur de sens) :

| ability | corps | verdict |
|---|---|---|
| `1015 PrecisionShot` | `cmovne` : `HasEffect(caster, 1015 PrecisionShot_Aim) ? 0 : 2` | valide **seulement en visée** |
| `1012 PrecisionShot_Aim` | `neg/sbb/and 2` : `HasEffect(...) ? 2 : 0` | valide **seulement hors visée** |
| `1013 PrecisionShot_Attack` | `cmovne` : `HasEffect(...) ? 0 : 4` | valide **seulement en visée** |

`0x2` = `TargetMatchesDynamicRule`, `0x4` = `CasterMatchesDynamicRule`.

### Ce que la bataille monte réellement — MESURE, et personne ne l'avait faite

`probe_996r1_precision_shot.py` (board `MC1_67`, seed 999, `necroNpc3Deathmark:45` via
`--explicit-stats`) alors que le gameconfig ne déclare que `activeAbilities: ["PrecisionShot"]` :

```
KIT ACTIF monté par la bataille : [69 Loki_NormalAttack, 1015 PrecisionShot,
                                   1012 PrecisionShot_Aim, 1013 PrecisionShot_Attack]

abilityReason 1015 -> casterReason 0x2      applyAction 1015 -> actionConsumed = False
abilityReason 1012 -> casterReason 0x0      applyAction 1012 -> actionConsumed = True
abilityReason 1013 -> casterReason 0x4      applyAction 1013 -> actionConsumed = False
```

⇒ Les trois abilities du triptyque sont **montées**, et **1015 est REFUSÉE** tant que le caster n'a
pas visé. Le cast utile est `1012`, puis `1013` au tour suivant. `1015` n'est donc pas la « phase 1 »
qu'on lit dans son nom : c'est une entrée dont le seul chemin d'exécution passe par un état que
`1012` seul produit.

### Pourquoi le port est REFUSÉ

Porter `1015` seule livrerait **un no-op déplacé d'un cran**, ce que `#996-r1` annonçait et que la
mesure ci-dessus confirme : son unique nœud dispatche `1012`, et

| pièce manquante | état |
|---|---|
| `UseActiveAbility` avec un `activeAbilityType` **NON-NORMAL** | **ABSENTE** — la feuille appelle `AttackDamageOperation.execute` inconditionnellement (docstring : « NON porté / flaggé »). Lui donner 1012 lui ferait **inventer une attaque normale** : pire qu'un no-op |
| `1012 PrecisionShot_Aim` (`AddEffect(1015, abilityStateRef, Owner@+0x30, Nullable(3) TOURS) & SetActiveAbilityUsed(Owner@+0x30, 1015)`) | **ABSENTE** d'`ABILITY_CLASSES` |
| `DSLBehaviors$$SetActiveAbilityUsed` → `SetActiveAbilityUsedBehaviour$$Execute` (`foreach u in units.SelectUniqueUnits(entities, 3) : processor.<slot 0x74>(u, activeAbilityType)`) | **ABSENTE** |
| l'effet `1015 PrecisionShot_Aim` (`$$BlockMovement` → sous-effet `0x3f8 = 1016 PrecisionShot_BlockMovement` ; `$$CreateHandleTriggerAbilitiesInternal` = trois `Triggered(<cond>, RemoveEffect)`) | **ABSENTE** |
| `1013 PrecisionShot_Attack` (`AttackWithAttackDamage(DmgDamage, GetDamageProfile(cfg), hits = GetNumberConstant(0x2f), selectionType 2)` dans un `AtomicGroup(0x40)`) | **ABSENTE** |

Le seul morceau livrable isolément serait la **règle dynamique de caster** — elle ferme un trou
PERMISSIF réel (aujourd'hui le port rend `0` là où le natif rend `0x2`, donc il ACCEPTE un cast que
le natif REFUSE). Mais elle ne se pose que **sur la classe d'ability**, donc son inscription à
`ABILITY_CLASSES` arme aussi `execute_behaviour` — c'est-à-dire précisément le dispatch qu'on vient
de refuser. Le couple est indivisible.

⇒ **Résidu `#996-r1-r3`**, avec les cinq pièces ci-dessus et la mesure de reachability qui les
justifie. Le probe est **livré** (`probe_996r1_precision_shot.py`) : la prochaine tranche part de la
mesure, pas d'un décompilé à relire.

## 4. Ce que cette fiche ne tranche PAS

* la face DÉCISION de 1053 : `DevoutPushPlaybook` ne déclare que son `.ctor`
  (`ALoki_NormalAttackPlaybook<T>..ctor(this, 0x41d)`), donc **rien de propre à porter** — attesté
  `RIEN_A_PORTER` au ledger #951-r2, trois sources indépendantes. Mais 1053 est la **SEULE** des 18
  dérivées dont le paramètre de type n'est pas une `*_NormalAttackAbility` : le corps de la BASE
  (`MakeDamagePredictions` = un `ProbableDamageEvent` bâti sur le slot `0x22` d'`IBattleQuery`) lui
  est load-bearing d'une façon qu'il n'est pour aucune autre → résidu **`#996-r1-r2`**, à côté de
  `#1021-r1` qui porte déjà `CalculateCustomUtility` / `ShouldExecute` de la même base ;
* le montant de l'overwatch (§2.4) ;
* les mécaniques 1012/1013/1016 (§3) ;
* deux **rouges PRÉ-EXISTANTS** rencontrés dans le rayon de souffle, vérifiés à `bcd6215c` dans un
  worktree FRAIS et absents des listes de rouges connus :
  `test_448_r2b_stormboyz_teleporting_in_offline.py::test_the_just_summoned_family_stays_out_because_nothing_POSES_it`
  et `test_498r4_face_decision_is_displaceable_offline.py::test_le_recenseur_ne_credite_pas_une_condition_seulement_CITEE`.
