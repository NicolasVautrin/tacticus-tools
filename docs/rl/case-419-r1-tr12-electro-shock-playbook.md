# #419-r1 tranche 12 — `ElectroShock` (1303), face ATTACK : PORTÉ + CONFRONTÉ LIVE

Tête des résidus ATTACK de #419-r1 (3 porteurs). Le corps n'avait **pas** été lu.

## 1. L'inventaire du nom — SIX artefacts natifs, un seul porté

Un id ne désigne rien à lui seul, et le nom non plus. Sur `rnca9r7q6c` :

| symbole | ce que c'est |
|---|---|
| `IdunBattle.AI.Playbook.Loki.ElectroShockPlaybook$$CalculateAttackUtilityInStepsInternal` | **CETTE TRANCHE** |
| `…ElectroShockPlaybook$$CalculateMovementUtilityInStepsInternal` | `yield Fix64(0)` constant (§5) |
| `IdunBattle.AI.Playbook.Loki.ElectroShock_NormalAttackPlaybook$$.ctor` | playbook de l'**ACTIVE 1178** |
| `IdunBattleLogic.Entities.Abilities.Triggered.Loki.ElectroShockAbility$$CreateTrigger` | le trigger du passif |
| `IdunBattleLogic.Entities.Abilities.Active.Loki.ElectroShock_NormalAttackAbility$$GetCustomNormalAttackBehaviour` | la face COMBAT (§4) |
| `…ElectroShock_NormalAttackAbility$$PossibleTargets` / `$$GetAttackDamage` | idem |

Homonymie d'id : `EffectType` **1303** = `WrathfulDevotionKilled_Visual`, sans rapport ; il n'existe
**pas** d'`ActiveAbilityType` 1303. L'attaque normale du porteur vit sous `ActiveAbilityType`
**1178** = `ElectroShock_NormalAttack`. Le triggered n'a NI `TARGETING_OPTIONS` NI
`ABILITY_ATTACK_TYPE` (données du registre `ABILITY_CLASSES`, réservé aux ACTIVES).

## 2. Ce que dit le décompilé

Le wrapper monte la SM `d__3` — disposition **lue dans le wrapper**, elle DIFFÈRE de celle de
`FireOfAbsolution` (`d__4` : `+0x20` = case, `+0x28` = playbook) et coïncide avec `Boltstorm` :
`sm@+0x20 = this` (le playbook), `sm@+0x28 = case`, `sm@+0x30 = getUtilityVal`. Le corps est
`…ElectroShockPlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__3$$MoveNext`, **un seul
état de yield** et une **sortie anticipée sans valeur** :

```csharp
var enemies = this.<IBattleQuery @playbook+0x60>
                  .GetAdjacentEnemies(case.Target, case.Caster, ignoreSteppables: false); // slot 0x7f
if (enemies.Count == 0)
    yield break;                            // AUCUN yield -- pas même un 0
yield return Fix64.op_Implicit(GetUtilityValue("ElectroShock_TargetHasAdjacentEnemy"));   // état 1
```

Cinq lectures qui ne se devinent pas :

1. **La sortie est un BOOLÉEN × poids, PAS un produit poids × cardinal.** Le cardinal est calculé
   (`FUN_180002590(0, DAT_183364c10, list)` = le vslot `get_Count`) mais **jamais multiplié** : il ne
   sert qu'au test `== 0`. C'est le piège exact de ce filon — `Boltstorm` (1090, #446),
   `FireOfAbsolution` (1017) et `RighteousRepugnance` (1107, tranche 10) comptent tous des voisins de
   la cible avec **le même helper au même cache** et **tous les trois multiplient**. Une recopie par
   analogie aurait rendu `50 × n` là où le natif rend `50`.
2. **`yield break`, pas `yield 0`.** Sur `Count == 0`, `MoveNext` rend `false` sans écrire `current`.
   Le dispatcher `TriggeredAbilitiesUtility` **somme** les yields, donc c'est observationnellement
   `0.0` ; la distinction est notée parce qu'elle ne serait pas neutre sous un agrégateur qui moyenne.
3. **L'ancre est la CIBLE, le camp est celui du CASTER.** `(case.Target, case.Caster, false)` =
   `UtilityAttackCase@+0x20` puis `@+0x10`, offsets LUS dans
   `IdunBattle.AI.Utilities.UtilityAttackCase$$.ctor` (`+0x10 caster · +0x18 casterPosition ·
   +0x20 target · +0x28 damagePrediction · +0xd0 heal · +0xdc repair · +0xe8 effectType ·
   +0xf0 abilityType`). `case.CasterPosition` n'est jamais lu, la SM ne capture aucune tuile : le
   terme discrimine les **cibles**, jamais les tuiles d'une même cible. `prediction` (#438) non lu.
4. **`ignoreSteppables: false`** (le 6e argument littéral `0`) : les unités `Steppable` comptent.
   Même littéral que `FireOfAbsolution`.
5. **Le poids est `ElectroShock_TargetHasAdjacentEnemy` = 50**, **seule** clé `ELECTRO*` de
   `Utilities.Default.TriggeredAbilities`. Le littéral de chaîne n'est pas lisible au décompilé
   (cache `DAT_` posé au runtime) : identification par le BC servi, **confrontée live**.

### Le slot 0x7f — re-dérivé, pas hérité

Les proxies nommés de `IdunBattle.Core.Services.RecordedSimulationRequestsBattleQuery` relèvent, sur
**ce** build : `DisplayClass151 <GetAdjacentUnits>` → `0x7c` ; `152 <GetAdjacentEnemies>` → `0x7d`
(ref, **int**, bool) ; `153` → `0x7e` (ref, int, bool) ; `154` → **`0x7f`** (ref, **ref**, bool) ;
`155` → `0x80` (ref, ref, bool).

⚠ `docs/rl/case-243-targeting-adjacency.md` (build antérieur) donnait `DisplayClass151..154 =
GetAdjacentEnemies` ; ici le 151 est `GetAdjacentUnits`. Le verdict « `0x7f` = `GetAdjacentEnemies` »
est le même des deux côtés, mais la table a été **re-dérivée** — c'est l'ambiguïté d'ancrage à ±1
slot que signale `case-343` §6.

L'arité tranche la paire `int` (`0x7d`/`0x7e`) de la paire `ref` (`0x7f`/`0x80`). Que le premier
argument soit une **entité** et non une liste de tuiles est établi par le `ctor` du case (point 3) et
recoupé par `ToString`, qui applique le **même** slot d'interface (`9`) à `+0x10` et à `+0x20`.

**La seule différence avec le site de `FireOfAbsolution`** : la variante `ref` de
`IdunBattle.Core.Services.BattleQuery$$GetAdjacentEnemies` commence par
`unit.GetComponent<OwnerComponent>().CurrentPlayerEntityId` avant de rejoindre le **même**
`GetAdjacentUnits` → `GetUnitsOnTiles` → `CountOrGetUnitsOnTiles`. D'où la réutilisation directe de
`fire_of_absolution.count_adjacent_by_camp` (ring-1 avec porte d'élévation, occupants de tuile, la
cible jamais comptée parce qu'elle n'est pas adjacente à elle-même) : **aucune copie locale**.

Le `get_Count` est identifié par **identité de site** : `FireOfAbsolutionPlaybook…d__4$$MoveNext`
appelle `FUN_180002590(0, DAT_183364c10, list)` et en consomme le retour comme **cardinal d'un
produit**. Le même helper au même cache ne peut pas être un `GetEnumerator`.

## 3. L'ability prise à l'envers — pourquoi le terme est PLAT

`ElectroShockAbility$$CreateTrigger` : `On(0xf) & OwnerIsCaster`, où `0xf` =
`IdunBattle.DSL.EventTriggerType.DamageTaken`.

`ElectroShock_NormalAttackAbility$$GetCustomNormalAttackBehaviour` (le même arbre que son
`$$PossibleTargets`) :

```
If( IsMeleeAttack,
    AttackWithAttackDamage(
        Caster@0x48,
        PickRandomly( Damageable( Enemies(Caster@0x48,
                                          AdjacentUnits(Target@0x60, unique: 1, sel: 3), 3) ),
                      count: 1, 0, 0x7fffffff, false ),
        PercentageOf( StatAmount(Owner@0x30, ...), Direct(GetNumberConstant(0x3b)), 0 ),
        GetDamageProfile(), GetHits(), ... ) )
```

**`count: 1`** : l'arc saute sur **une seule** unité, tirée au sort parmi les ennemis adjacents à la
cible. La valeur ne peut donc pas croître avec le nombre de voisins — et le nom de la clé le dit
mot pour mot (`TargetHasAdjacentEnemy`). Deux **écarts NATIFS** entre les deux corps, assumés (ils
sont lus séparément et ne partagent aucun sélecteur) : le playbook n'applique NI le filtre
`Damageable`, NI le gate `IsMeleeAttack`. Un porteur qui tire à distance, ou dont le seul voisin de
cible est non-damageable, marque quand même ses 50 points.

## 4. Le montage — pourquoi une GREFFE, et sur quel hôte

Les 3 porteurs sont 2 npc (`admecNpc3Electropriest`, `admecNpc3ElectropriestSurv`) et le SUMMON
`admecSmnElectropriest`. La gate de confrontabilité a été jouée **dans l'ordre** :

1. `buildNormalizedBC` refuse tout npc → aucun `--p-units`.
2. **SUMMON sans invocateur — vérifié par balayage, pas supposé** (`case-92` §5bis recours 2) :
   l'unique ability qui le déclare (`units.abilities.<X>.constants.unitId == "admecSmnElectropriest"`)
   est **`EnvFactionSummons:AdeptusMechanicus`**, et **aucune** unité du catalogue ne la porte dans
   `activeAbilities`/`passiveAbilities`. C'est un summon d'**environnement** : il n'y a pas de
   summoner à spawner, donc pas de voie « observer le summon » (#291).
3. **Greffe** (`catalog_inject.graft_passive_ability`, recours 3) sur `tauMarksman` — HERO au pool,
   arme distance portée 3, `replace=True`. Elle est **légitime et c'est LU** : le corps ne consulte
   du caster que son **camp**, ni stat, ni trait, ni arme, ni variable d'ability.

**Bras apparié** : deux runners identiques à un passif près (`graft` = `PassiveAbilities=[1303]`,
`base` = le bras greffé **moins** 1303 — surtout pas « les passifs d'origine », `replace=True` les a
déjà retirés ; piège mesuré par la tranche 9). `terme_natif = natif_graft − natif_base`.

Board `MC1_67`, seed `41303`, layout `C=(3,4) T=(0,2) P1=(0,3) P2=(0,1) K1=(0,0) K2=(0,4) K3=(0,6)`.
Roster : `tauMarksman` + `necroWarden` (ami) contre `astraBullgryn` (la cible, **fixe**),
`astraCreed`, `astraDreir` (les deux ennemis mobiles). `T` est à portée 3 de `C` et **non adjacente**
à lui.

## 5. Mesures — quatre crans, cible et caster FIXES

Seul ce qui entoure la cible bouge ; le cardinal est **re-dérivé** des positions live avec
l'adjacence native (`bq.is_adjacent`), et le probe refuse si le cran attendu n'est pas installé.

| cran | ennemis adj. | amis adj. | natif `graft` | natif `base` | **TERME natif** | port | port muté | **TERME port** | attendu |
|---|---|---|---|---|---|---|---|---|---|
| `c0` | 0 | 0 | 10.679466 | 10.679466 | **+0.000000** | 12.044398 | 12.044398 | +0.000000 | 0 |
| `cF` | 0 | **1** | 10.679466 | 10.679466 | **+0.000000** | 12.044398 | 12.044398 | +0.000000 | 0 |
| `c1` | **1** | 0 | 60.679466 | 10.679466 | **+50.000000** | 62.044398 | 12.044398 | +50.000000 | 50 |
| `c2` | **2** | 0 | 60.679466 | 10.679466 | **+50.000000** | 62.044398 | 12.044398 | +50.000000 | 50 |

Deux crans sont **le** résultat de cette tranche :

* **`c2` tranche PLAT contre PRODUIT.** Le cardinal double, le natif ne bouge pas. Un port écrit par
  analogie avec `Boltstorm`/`RighteousRepugnance` rendrait ici `100`.
* **`cF` tranche le CAMP.** Un ami du caster adjacent à la cible ne verse rien : le sélecteur est
  `Enemies(caster)`, pas « voisins ».

## 6. Contre-épreuves — mordantes ET réciproques

Critère = **déplacement du port par rapport au port NON MUTÉ**, jamais l'écart au natif (la paire
porte un résidu constant, §7 — un critère « écart au natif > EPS » serait vrai même pour un mutant
inerte ; piège de #441 et #446). Chaque mutant est joué **à chaque cran** :

| mutant | `c0` | `cF` | `c1` | `c2` |
|---|---|---|---|---|
| `product` (× cardinal) | — | — | — | **+50** |
| `any_neighbour` (amis inclus) | — | **+50** | — | — |
| `no_gate` (terme inconditionnel) | **+50** | **+50** | — | — |
| `friends` (compte les amis) | — | **+50** | **−50** | **−50** |

Les quatre mordent, **et aucun ne mord partout** : la réciproque tient, chaque cran est nécessaire,
et aucune ligne n'est triviale.

**La garde a elle-même été éprouvée par trois mutants du PORT** (le fichier livré, muté sur disque,
patch vérifié — un remplacement inerte lève) : `product` → **5 rouges sur 7**, `any_neighbour` → 4,
`no_gate` → 4. Puis restauration et re-jeu : **7 passed**.

⚠ Le premier essai de cette contre-épreuve a rendu **7 passed sur du code NON MUTÉ** : le motif
n'avait pas matché parce que PowerShell interprète le backtick du script Python inline comme un
échappement. Le script de mutation lève désormais sur motif introuvable — et c'est exactement pour
cela qu'un vert de contre-épreuve doit toujours être suspecté.

## 7. Résidus NOMMÉS

* **`#419-r1-tr12-r1` — FERMÉ** (`docs/rl/case-419-r1-tr14-r5-dispatch-attaque-normale.md`).
  Le port était **au-dessus** du natif de `+1.364932`, invariant aux quatre crans. Ce n'était pas le
  composite de dégât : c'était le DISPATCH de l'attaque normale, résolu depuis le KIT gameconfig là
  où `IdunBattle.Entities.Factories.UnitFactory$$GetCustomNormalAttackTypeFromPassive` lit
  `UnitConfiguration.PassiveAbilities` — que le `replace=True` du montage venait justement de vider.
  Re-mesuré après le fix : **0.000000 aux quatre crans**. Même cause que `#419-r1-tr13-r1` et
  `#419-r1-tr14-r5`, fermés en même temps.
* **`#419-r1-tr12-r2` — le DÉBLOQUEUR est LIVRÉ ; le montage reste à jouer.**
  `buildNormalizedBC` a désormais un chemin de stats explicite npc/summon (`explicitStats`), mirror
  de `IdunMetaLogic.UserProgress.UnitProgression$$GetNpcStats` / `$$GetSummonStats` — confronté au
  témoin que **le jeu** a écrit (4 npc du seed BC, 56 champs, **0 divergence**) et à une mesure live
  antérieure (#202c). Le verrou est reproduit LIVE côté désarmé
  (`skipped.reason = 'v2 patch: system error'`, hp = 0). Le porteur confrontable est le **NPC**
  `admecNpc3Electropriest` : même kit que le summon (mêmes passifs, même arme 3 hits `Particle`,
  même `Movement` 3), et lui a une table de stats — alors que les 65 entrées summon du catalogue
  portent `Health = 0`, écrit par le jeu. **Reste** : la fenêtre de reinject (le champ vit dans
  `frida/hooks/**`), puis rejouer les quatre crans de §5 sur `admecNpc3Electropriest:33`.
  Détail : `docs/rl/case-419-r1-tr12-r2-stats-npc-summon.md`.
* **`#419-r1-tr12-r3` — la face COMBAT n'est pas portée.**
  `ElectroShock_NormalAttackAbility$$GetCustomNormalAttackBehaviour` (`If(IsMeleeAttack,
  AttackWithAttackDamage(…, PickRandomly(…, 1, …), PercentageOf(StatAmount, Direct(0x3b))))`) n'a
  aucun mirror dans `engine/runner` : une attaque normale de l'`Electropriest` ne fait **pas** sauter
  l'arc côté exécution. Même forme que `#419-r1-tr9-r4-r3` et `#419-r1-tr10-r3`. La face DÉCISION
  livrée ne dit rien de l'exécution.
* **`#419-r1-tr12-r4` — `ignoreSteppables: false` n'est pas exercé.** Aucune unité `Steppable` n'est
  au montage ; le littéral est lu au décompilé, pas confronté. Le port ne pose aucun filtre, ce qui
  est le comportement du littéral `false` — mais un montage avec un leurre traversable adjacent à la
  cible le prouverait.
* **`#419-r1-tr10-r2` (PARTAGÉ, déjà ouvert) — les unités MULTI-TUILES.** `count_adjacent_by_camp`
  ne connaît que la MainTile (`scene.pos`) alors qu'`AdjacentTiles` itère
  `EntityExtensions.IterateTiles`. Ce port hérite du résidu, il ne l'aggrave pas.

## 8. Face MOVE : `yield Fix64(0)` CONSTANT — ce n'est PAS un résidu

`…ElectroShockPlaybook.u003CCalculateMovementUtilityInStepsInternalu003Ed__2$$MoveNext` n'a qu'un
état, et cet état est `Fix64.op_Implicit(0)` ; aucun champ de la SM n'est lu. Elle n'entre donc pas
dans `TRIGGERED_MOVE_PLAYBOOKS`, et **son absence EST le comportement natif** (même forme que
`Lakrimae`, `BarbedOvipositor`, `Neuroparasite`, `Boltstorm`, `FireOfAbsolution`).

## 9. Livré

* `scripts/python/engine/playbook/electro_shock.py` — le playbook.
* `scripts/python/engine/playbook/psyker.py` — entrée `TRIGGERED_ATTACK_PLAYBOOKS[1303]`.
* `scripts/python/probe_419r1tr12_electro_shock.py` — bras apparié, 4 crans, 4 contre-épreuves.
* `scripts/python/tests/engine/test_419r1tr12_electro_shock_live.py` — 7 gardes.
