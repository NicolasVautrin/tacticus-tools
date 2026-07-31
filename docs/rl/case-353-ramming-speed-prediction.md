# case-353 — `RammingSpeed` (1059) : la prédiction n'est pas `ExplodesAbility$$GetDamage`

Résidu `#350-r2`. #350 avait inscrit `1059` dans `_PREDICTION_DAMAGE_NOT_MINMAX_AVERAGE` avec pour
formule `ExplodesAbility$$GetDamage` = `PercentageOf(StatAmount(Health), …)`. **Lecture partielle** :
prise sur les *xrefs* de ce corps, dont l'une est `RammingSpeedPlaybook$$MakeDamagePredictions`.
Ce corps n'alimente que les **deux derniers** batchs du playbook, et seulement sous condition.

---

## 1. La forme native complète

`IdunBattle.AI.Playbook.Loki.RammingSpeedPlaybook$$MakeDamagePredictions` — quatre batchs :

```
dmg   = AbilityConfiguration$$GetVariableForLevel(config, 0xc = minDmg, abilityState)
hits1 = AbilityConfiguration$$GetNumberConstant(config, 0x2f = nrOfHits)      // 4
hits2 = AbilityConfiguration$$GetNumberConstant(config, 0x32 = nrOfHits_2)    // 2
prof  = AbilityConfiguration$$GetDamageProfile(config)                        // Physical

// 1. la CIBLE
list = GenerateMultiHitAttackPredictions(caster, casterPos, TARGET, <Target@0x60>,
                                         Get(dmg), hits1, prof, null, 0)
// 2. le CASTER (recul du ram)
self = GenerateMultiHitAttackPredictions(caster, casterPos, CASTER, <Caster@0x48>,
                                         Get(dmg), hits2, prof, null, 0)
list.AddRange(self)
if (!self.Any(p => p.Prediction.WillBeKill)) return list;     // <>c$$<MakeDamagePredictions>b__2_0

// 3/4. l'EXPLOSION — seulement si le recul TUE le caster
amount  = <eval>( ExplodesAbility$$GetDamage(dsl) )
tile    = RammingSpeedAbility$$GetTileToMoveTo(ability)
list.AddRange(GenerateAttackPredictions(caster, casterPos, TARGET,
                  Friends(<Caster>, AdjacentUnits(tile, 1, 3), 3), Get(amount), null,
                  Nullable(0xf = DirectDamage), 0))
list.AddRange(GenerateAttackPredictions(caster, casterPos, TARGET,
                  Enemies(<Caster>, AdjacentUnits(tile, 1, 3), 3), Get(amount), null,
                  Nullable(0xf), 0))
```

Le batch 2 a son **pendant COMBAT** : `RammingSpeedAbility$$ExecuteBehaviour` construit
`AttackWithAttackDamage(Owner@0x30, Owner@0x30, RandomAmount(minDmg 0xc, maxDmg 0xd), prof,
nrOfHits_2)` — caster == cible — sommé à l'attaque de la cible, plus `MoveUnit(GetTileToMoveTo)`
sous `If(NOT IsAdjacent(caster, target))` et `AddEffect(0x44a = 1098 RammingSpeed_ExtraExplode)`.
Prédiction et combat divergent sur UN point, natif et assumé : `Get(minDmg)` en prédiction contre
`RandomAmount(minDmg, maxDmg)` en exécution — même écart que Stikkbomb (#57e/#173).

## 2. Le fork du `ConditionalAmount`, lu des deux côtés

`ExplodesAbility$$GetDamage` (partagée avec la nova de mort du trait `Explodes`, déjà portée côté
COMBAT dans `runner/operations/triggers/loki/death_nova.py`) :

```
PercentageOf( StatAmount(Owner, Health = 5, part = 2 -> MAX),        // PV MAX, pas courants
              Sum( ConfigConst(0x3fd = 1021 Explodes,  key 0xf) ,    // explodesDmg = 25
                   ConditionalAmount( HasEffect(Owner, 0x44a = 1098 RammingSpeed_ExtraExplode, 1, 6),
                                      ConfigConst(0x423 = 1059 RammingSpeed, key 0xf),  // extraDmgPct = 50
                                      Get(0) ) ) )
```

| élément | valeur lue |
|---|---|
| condition | `HasEffect(Owner, EffectType 1098 `RammingSpeed_ExtraExplode`, 1, 6)` |
| branche VRAIE | `ConfigConst(ActiveAbilityType 1059, `extraDmgPct`)` = **50** |
| branche FAUSSE | `Get(0)` = **0** |
| base | `StatAmount(Owner, Health, part 2)` = **PV MAX** (`StatPart.Max`), pas les PV courants |

⚠ Le playbook évalue ce corps **sans jamais tester le trait `Explodes` du caster** : quand le recul
tuerait le caster, l'IA prédit la nova, que le caster explose réellement ou non. Quirk natif.

## 3. Gate de confrontabilité — verdict

**Aucune unité du gameconfig ne porte `RammingSpeed`.** Le balayage de tout le JSON ne la cite que
**4 fois** : `units.abilities.RammingSpeed` (sa définition), `units.abilityPowerModifiers.RammingSpeed`,
et deux fois sous `aiUtilities.Default.RammingSpeed_MostAdjacentEnemies`. Ni active, ni passive, ni
trait, ni relique, ni mythic, ni item, ni summon. Verrouillé par
`test_353_ramming_speed_prediction_offline.py::test_ramming_speed_has_no_carrier_anywhere_in_gameconfig`.

Corollaire, et c'est le verdict de la branche VRAIE du fork : l'effet `1098` n'est posé que par
`RammingSpeedAbility$$ExecuteBehaviour`. **Sans porteur de 1059, `HasEffect(1098)` est faux pour
toujours en bataille régulière** — la branche vraie est morte côté jeu, des DEUX faces (prédiction et
combat). C'est ce que le résidu de `death_nova.py` disait déjà de la face COMBAT ; #353 l'établit par
un balayage exhaustif, et l'étend à la prédiction.

Recours utilisé : **GREFFE** (`case-92` §5bis) — `ActiveAbilities = [1059]` sur `orksKillaKan` (pool
rank 17) dans une COPIE du seed BC, **plus** l'injection de la config d'ability dans `BC.Abilities`.
Ce second étage est obligatoire et n'était pas acquis : `_load_seed_bc` ne re-synthétise QUE les
configs déjà référencées par le catalogue — mesuré, `RammingSpeed` est **absente** des 131 entrées
(la ligne de `case-92` §5bis « même une ability que personne ne porte y figure » est donc fausse pour
une ability sans aucun porteur ; sans injection, `GetVariableForLevel` lève → « system error »).

`aiPlaybookPredict` charge le playbook **par ability** (`PlaybookDatabase.LoadPlaybook(1059)`) : le
RPC confirme `playbookClass = RammingSpeedPlaybook`, et l'`AbilityState` vient du **capteur** (le
niveau piloté par `--unit-stat` prend).

## 4. Ce qui est porté, et la mesure

| batch | port | site |
|---|---|---|
| 1 CIBLE | base `minDmg`, hits `nrOfHits` LITTÉRAL | `_ramming_speed_inputs` (`_MAKE_DMG_INPUT_OVERRIDES`) |
| 2 CASTER | mêmes base/profil, hits `nrOfHits_2`, `friendly=True` | `_ramming_speed_self_events` (nouveau registre `_MAKE_DMG_EXTRA_EVENTS`) |
| 3/4 EXPLOSION | **résidu nommé** (§5) | — |

`friendly=True` n'est pas une convention de port : `DamageUtility.<EvaluateAttackInSteps>d__2$$MoveNext`
finit par `if (IsFriend(caster, actor)) u = u * -1` (branche `HasFriendlyFire` → `IsEnemy` sinon). Le
caster est son propre ami.

**Confrontation live** (`probe_353_ramming_speed_prediction.py`, oracle `aiPlaybookPredict`,
signature = `(cible, healthDmgMin, healthDmgMax, appliedHits)` triée) :

| bras | board / armure cible | niveau (minDmg, maxDmg, avg) | natif = port LIVRÉ | port AVANT |
|---|---|---|---|---|
| lvl8 | MC1_67 / 0 | 8 (65, 80, 72) | `[(cible,312,468,4), (caster,2,2,2)]` | `[(cible,348,516,4)]` ✗ |
| lvl2 | MC1_67 / 0 | 2 (31, 38, 34) | `[(cible,152,224,4), (caster,2,2,2)]` | `[(cible,164,248,4)]` ✗ |
| lvl30 | **C1_03** / 0 | 30 (345, 425, 385) | `[(cible,1104,1656,4), (caster,6,8,2)]` | `[(cible,1232,1848,4)]` ✗ |
| lvl45 | MC1_67 / **2312** | 45 (906, 1115, 1010) | `[(cible,44,64,4), (caster,14,22,2)]` | `[(cible,48,72,4)]` ✗ |

Les quatre bras **discriminent** sur les deux axes du correctif : la base (`minDmg` ≠ `avg`) et le
**nombre d'events** (le port n'émettait pas le 2ᵉ). Le bras armure 2312 vérifie que le correctif tient
quand le plancher écrase le dégât — régime où un écart de base est souvent absorbé (piège #339 §4).

## 5. Résidu nommé — les batchs 3/4 (EXPLOSION)

Deux verrous, l'un de port, l'autre de mesure.

**(a) Port.** `RammingSpeedAbility$$GetTileToMoveTo` =
`First(SortTilesByUtility( CanAddUnit(AdjacentTiles(target)) & MovableTilesInRange(caster, casterTile,
Direct(GetNumberConstant(0x16 = range)), false), caster, UtilityBucket([WeightedUtility(7 = Tile),
WeightedUtility(0x36 = 54 RammingSpeed_MostAdjacentEnemies)]), null ), 1)`.
Le port a l'intersection (`selectors/tiles.py::tiles_unit_can_move_to_charge_target`, mirror exact) et
l'utilité `7` (`UTILITY_BY_TYPE`), mais **pas** l'utilité `54` ni un bucket à DEUX `WeightedUtility`.
`IdunBattle.AI.Utilities.RammingSpeed_MostAdjacentEnemies.<EvaluateMovementInSteps>d__1$$MoveNext` =
`Σ GetUtilityValue(RAMMINGSPEED_AdjacentEnemy)` sur les entités rendues par la query slot `0x7f`
(tuile, équipe) — poids présent dans `gameconfig.aiUtilities.Default`.

**(b) Mesure — la gate n'a ouvert sur AUCUN montage.** Cinq montages joués
(`hp_player` 9037 / 60 / 1, avec et sans `--block-player 0,0`, caster adjacent puis à distance 2 d'une
cible à 6 voisins dont 3 libres) : le natif rend **2 events**, jamais 4. Or le RPC expose
`willKillDmg = 156` contre `hpBefore = 60` puis `1`. Les deux champs que `get_WillBeKill` lit
réellement ne sont **pas exposés** :

```
get_WillBeKill(this):
    if (this+0x89 /* CannotBeGuaranteedKilled */) return false;
    v = (BlockScenarios@0x38 == null || Count < 1) ? *(int*)(this+0x1c) : BlockScenarios[0]+0x0c;
    return CurrentHealth <= v;
```

`willKillDmg` du RPC = `DefaultScenario.Damage.HealthDamage.Min` (`+0x1c`) — c'est-à-dire **la seule
branche `else`**. Le balayage du décompilé montre que `+0x89` n'est écrit que par
`DamagePrediction$$PredictNormalAttack` (unique site), ce qui *devrait* le laisser à 0 sur une
prédiction d'ability ; et le port calcule `block_raw_min = None` pour ce caster (BlockChance = 0). La
cause reste donc **non tranchée**, et c'est le seul point du cas qui l'est.

> **Point d'ancrage à hooker** (pas de reinject dans cette fenêtre) : exposer, dans
> `frida/hooks/game/damage-prediction.ts`, `CannotBeGuaranteedKilled` (`+0x89`) et le premier élément
> de `BlockScenarios` (`+0x38`, `Probability@0x00` / `HealthDamage.Min@0x0c`). Ces deux champs sont
> déjà DOCUMENTÉS dans la table du fichier ; il ne manque que la lecture. Sans eux, tout verdict sur
> une gate `WillBeKill` se prend en aveugle — et pas seulement pour 1059.

## 5bis. `GetTileToMoveTo` — porté (#353-r1, volet a)

Le volet (a) du §5 est FERMÉ. Trois lectures ont corrigé l'énoncé hérité, et deux d'entre elles
changent la tuile rendue.

**Le décompilé, relu.** `RammingSpeedAbility$$GetTileToMoveTo` n'appelle **pas**
`DSLSelectors$$TilesUnitCanMoveToChargeTarget` : il assemble les deux mêmes nœuds à la main.

```
First( SortTilesByUtility(
           MovableTilesInRange(caster@0x48, casterTile@0x50,
                               Direct(GetNumberConstant(0x16 = range)), 0, 0)
           op_BitwiseAnd  CanAddUnit(AdjacentTiles(target@0x60)),
           caster@0x48,
           UtilityDefinition( UtilityBucket([ WeightedUtility(7 = Tile, null),
                                              WeightedUtility(0x36 = 54, null) ], null) ),
           null),
       1 )
```

1. **L'ordre des opérandes est INVERSE** de celui du helper (§5 l'écrivait dans l'ordre du helper) :
   `MovableTilesInRange` est à GAUCHE. `TargetsSelector$$op_BitwiseAnd(left, right)` garde l'ordre de
   GAUCHE, et l'`OrderBy` de `SortTilesByUtilitySelector$$Select` est STABLE ⇒ **à utilité égale, les
   deux ordres désignent des tuiles différentes**. Mesuré (montage `_ramming_speed_charge_montage`,
   board plat, 2ᵉ ennemi en (2,3)) : ordre natif → `(2,2)`, ordre du helper → `(3,4)`.
2. **La composition du bucket est une SOMME PONDÉRÉE, poids 1 chacun** — lu, pas supposé.
   `WeightedUtility$$.ctor` pose `Weight = weight ?? Fix64.FromInt(1)` et les deux termes sont
   construits avec un `Nullable<Fix64>` VIDE ; `UtilityBucket$$.ctor` pose
   `MinUtilityDifference = m ?? 0` (non lu par ce chemin — il sert à `UtilityDecider$$Decide`) ;
   `UtilityDecider.<CalculateUtilityInSteps>d__9<T>` fait `total += r * wu.Weight` par terme.
   ⚠ **Quatre SENTINELLES** (statiques de `BaseUtility`, `+0x10/+0x18/+0x20/+0x28`) court-circuitent
   la boucle et deviennent le total. Aucune utilité portée n'en rend une → **non modélisées**, résidu
   nommé dans `engine/utilities/decider.py`.
3. **`54` est re-dérivé du build**, pas recopié : `enums.tsv` de `rnca9r7q6c` donne
   `54=RammingSpeed_MostAdjacentEnemies` (le port passe par le MEMBRE `UtilityType.*`, jamais par le
   littéral — #252/#283 ont renuméroté quatre enums).
4. **La clé BC de la feuille était INDEVINABLE au préfixe** :
   `probe_212_bc_key_literals.py --symbol "IdunBattle.AI.Utilities.RammingSpeed_MostAdjacentEnemies.u003CEvaluateMovementInStepsu003Ed__1$$MoveNext"`
   → `'RAMMINGSPEED_AdjacentEnemy'` (majuscules collées), recroisé avec `seed-bc` :
   `Utilities.Default.RammingSpeed_MostAdjacentEnemies` = **20**. C'est une DONNÉE.
5. **La query est bien `GetAdjacentEnemies`, pas `GetAdjacentUnits`** — tranché par l'ARITÉ, pas par
   un numéro de slot recopié (ils ont bougé entre builds, cf. `case-27`) : l'appel a TROIS arguments
   (`from`, `unit`, `ignoreSteppables`) là où `BattleQuery$$GetAdjacentUnits` en a QUATRE
   (`tiles, friendsOf, enemiesOf, ignoreSteppables`). Le 2ᵉ argument est le POINTEUR `case.unit`
   (`case+0x10`) ⇒ la surcharge `(IEntity from, IEntity unit, bool)`. L'ancre est la tuile
   **CANDIDATE** (`case.position.MainTile`), ce qui rend le terme discriminant d'une tuile à l'autre.
   Conséquence de géométrie : toute candidate touche la cible (elle sort de
   `CanAddUnit(AdjacentTiles(Target))`), donc vaut au minimum `1 × 20`.

**Ce que ça change, chiffré** (montage plat, 2ᵉ ennemi en (4,3), pool
`[(2,2), (2,3), (3,2), (3,4), (4,2)]`) : `u54 = [20, 20, 20, 40, 40]`, `Tile(7) = 0` partout.
Bucket → `(3,4)` ; `Tile(7)` seul (ce que le port savait exprimer) → `(2,2)`, la 1ʳᵉ du pool.

**Livré** : `engine/utilities/decider.py` (les 3 mirrors + `calculate_utility`),
`engine/utilities/ramming_speed.py` (la feuille 54), `UTILITY_BY_TYPE[54]` + `utilities_database()`,
`sort_tiles_by_utility(..., utility_definition=)`, et
`engine/runner/abilities/orks.py::ramming_speed_tile_to_move_to` (+ son sélecteur).
1059 **n'entre pas** dans `ABILITY_CLASSES` : seule `GetTileToMoveTo` est portée.

**Non confronté LIVE** — la plateforme était hors service pendant la tranche (host `127.0.0.1:8765`
éteint, aucune session Frida ; un agent n'injecte pas). Le probe est écrit et prêt :
`probe_353r1_ramming_speed_charge_tile.py`. Il n'utilise **aucun capteur neuf** — la face COMBAT
expose la tuile directement (`ExecuteBehaviour` = `If(!IsAdjacent(caster, target, 3), MoveUnit(caster,
GetTileToMoveTo()))`), donc **la position d'arrivée du caster après un cast natif de 1059 EST la
réponse**. Deux conditions de montage, lues au décompilé : caster NON adjacent à la cible (sinon le
`If` court-circuite) et caster n'ayant pas bougé ce tour (sinon
`GetDynamicInvalidTargetReason` rend `0x10` — d'où le `endturn` après le drive).

## 6. Gardes

| garde | ce qu'elle verrouille |
|---|---|
| `tests/engine/test_353_ramming_speed_prediction_offline.py` (6) | le registre + la ligne de table rectifiée ; base = `minDmg` sur 4 niveaux avec écart NON NUL ; coups = littéral même avec `ExtraHits`/`ExtraHitsMelee` (l'axe que le live n'exerce pas) ; câblage du 2ᵉ batch (ordre, cible = caster, `nrOfHits_2`, `friendly`) ; dégradation `[]` sans config ; **0 porteur de 1059 dans tout le gameconfig** |
| `tests/engine/test_353_ramming_speed_prediction_live.py` (4) | greffe appliquée + config injectée + `playbookClass` + `AbilityState` du capteur ; port == natif event pour event ; le natif émet bien l'event SELF à `nrOfHits_2` coups et le port d'AVANT n'en émettait qu'un ; chaque bras DISCRIMINE |
| `tests/engine/runner/test_353r1_ramming_speed_charge_tile_offline.py` (10) | **#353-r1 volet (a)**, 100 % offline sur le montage nommé `_ramming_speed_charge_montage.py` : 54 au registre (par MEMBRE d'enum) ; feuille = `#ennemis adjacents × poids BC` (poids RELU, pas figé) ; muette sans sujet ; bucket = 2 termes de poids 1, `minDiff` 0, UN seul `Buckets[0]` ; **le 2ᵉ terme change la tuile** ; poids 0 ≡ amputation (la composition est bien une somme pondérée) ; type inconnu → LÈVE (jamais 0 silencieux) ; opérandes `MovableTilesInRange` À GAUCHE ; **l'ordre change la tuile à égalité** ; intersection vide → `None` |

**Ce qui n'est PAS couvert** : les batchs 3/4 (§5 (b) — gate `WillBeKill`, hors périmètre #353-r1) ;
la confrontation LIVE de `GetTileToMoveTo` (probe écrit, plateforme éteinte) ; le régime où `Tile(7)`
n'est PAS constant (le montage est plat EXPRÈS, pour que le terme qui tranche soit nommable) ;
l'ORDRE natif de `MovableTilesInRange` (le port rend les ids croissants, le natif l'ordre de visite du
BFS — inobservable tant que ce nœud était à DROITE de toutes les intersections portées, il devient ici
l'ordre source et ne départage que des utilités STRICTEMENT égales) ; l'axe COUPS en live (le greffon
a 0 `ExtraHits` — couvert offline seulement) ; le `multiplier` per-ability (les 4 bras sont à 100).
