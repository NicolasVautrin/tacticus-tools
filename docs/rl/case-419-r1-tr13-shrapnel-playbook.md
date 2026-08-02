# #419-r1 tranche 13 — `Shrapnel` (1116), face ATTACK : PORTÉ + CONFRONTÉ LIVE

Tête des résidus ATTACK de #419-r1 (3 porteurs). Le corps n'avait **pas** été lu.

## 1. L'inventaire du nom — TROIS artefacts sous l'id `1116`, et l'antécédent n'en est pas un

Le brief signalait un historique sur `1116` (`case-366-r1-inescapable-accuracy-crit-damage.md`). La
ventilation le range **avant** toute lecture :

| enum qualifié | valeur `1116` | rapport avec cette tranche |
|---|---|---|
| `PassiveAbilityType` / `TriggeredAbilityType` | **`Shrapnel`** | **CETTE TRANCHE** |
| `ActiveAbilityType` | `RadBombardment` | l'active tile-targeting de #217/#241/#254/#302, **portée** (`runner/abilities/admec.py`) |
| `EffectType` | `InescapableAccuracy_extraCritDmg` | l'effet CRIT porté par #414 — **homonyme numérique**, aucun lien |

Les symboles natifs portant le **NOM** `Shrapnel`, exhaustivement (`ghidra/functions.tsv`,
`rnca9r7q6c`) :

| symbole | ce que c'est |
|---|---|
| `IdunBattle.AI.Playbook.Loki.ShrapnelPlaybook$$CalculateAttackUtilityInStepsInternal` | **CETTE TRANCHE** |
| `…ShrapnelPlaybook$$CalculateMovementUtilityInStepsInternal` | `yield Fix64(0)` constant (§7) |
| `…ShrapnelPlaybook$$.ctor` | passe `0x45c` = 1116 à la base `TriggeredAbilityPlaybook<T>` |
| `IdunBattleLogic.Entities.Abilities.Triggered.Loki.ShrapnelAbility$$CreateTrigger` / `$$CreateBehaviour` | la face COMBAT (§4) |
| `IdunBattle.View.AbilityConfigs.Loki.ShrapnelVisuals$$ExecuteInternal` | visuels, hors périmètre |

**Aucun autre enum ne porte le nom `Shrapnel`** : il n'y a donc **pas** de mold d'attaque normale
sous un autre id pour ce passif — à l'inverse de `RighteousRepugnance` (playbook 1107 → mold **1182**)
et d'`ElectroShock` (playbook 1303 → mold **1178**). Corroboré par le code : les 15 occurrences de
`1116` dans `engine/runner/**` et `engine/entities/**` désignent **toutes** l'un des deux homonymes.

Le triggered n'entre pas dans `ABILITY_CLASSES` (réservé aux ACTIVES) : il ne porte donc **ni**
`TARGETING_OPTIONS` **ni** `ABILITY_ATTACK_TYPE`. Le seul registre concerné est
`TRIGGERED_ATTACK_PLAYBOOKS`, posé dans le même commit.

## 2. Ce que dit le décompilé

Le wrapper monte la SM `d__2` — disposition **lue dans le wrapper**, pas par analogie : il écrit
`sm@+0x20 = this` (le PLAYBOOK), `sm@+0x28 = case`, et **ne conserve PAS `getUtilityVal`** (deux
champs, comme `BarbedOvipositor` ; `Boltstorm`/`CosmicHorror`/`ElectroShock` en ont trois). Le corps
est `…ShrapnelPlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__2$$MoveNext`, **un seul
yield** :

```csharp
if (!IsRegularAttack(case))  yield break;              // AUCUN yield -- pas meme un 0

Fix64 acc = Fix64.op_Implicit(0);
var sel = DSLSelectors.Damageable(
              DSLSelectors.AdjacentUnits(DSLSelectors.Get(case.Target),      // case@+0x20
                                         unique: true, unitSelectionType: 3));
foreach (var u in sel.SelectUniqueUnits(new AbilityEntities(/* memset 0 */), 3)) {
    var pred = this.<IBattleQuery @playbook+0x60>.<slot 0x23>(
                   case.Caster, u, case.CasterPosition.MainTile, case.AbilityType,
                   AbilityConfiguration.GetVariableForLevel(config, 0xc /* minDmg */,
                                                            GetAbilityState(case.Caster), false),
                   (DamageProfileType?)0x12 /* Blast */, false, null);
    var ev = new ProbableDamageEvent(u, pred, null, null);
    int hits = AbilityConfiguration.GetNumberConstant(config, 0x2f /* nrOfHits */);
    for (int i = 0; i < hits; i++)
        acc = Fix64.op_Addition(acc, CalculateUtilityFromDamageEvent(ev, case.Caster,
                                                                     case.CasterPosition));
}
yield return acc;
```

Neuf lectures qui ne se devinent pas — les cinq premières sont **confrontées live** (§5/§6) :

1. **AUCUN poids BC.** `getUtilityVal` n'est pas capturé : il n'y a ni `GetUtilityValue`, ni clé
   `SHRAPNEL_*` à chercher. La sortie est une **utilité de dégât** (composite Damage).
2. **SOMME, pas moyenne.** Aucune division dans le corps. `Psyker` (1013) fait le **même** balayage
   `Damageable(AdjacentUnits(CIBLE))` et **divise par `Count`** (`Fix64.op_Division` de sortie) ;
   `LightImUp` moyenne ses cibles secondaires. Recopier le voisin diviserait.
3. **`nrOfHits` multiplie l'UTILITÉ, pas les dégâts.** Le slot 0x23 écrit le littéral `1` comme
   nombre de coups (`IdunBattle.Core.Services.BattleQuery$$GetAttackPrediction`, lecture #449) ;
   c'est la boucle `for (i < 0x2f)` du playbook qui répète `CalculateUtilityFromDamageEvent` sur le
   **MÊME** event. `hits × U(1 coup) ≠ U(hits coups)` : le composite sature.
4. **Le montant est `minDmg` SEUL** (`GetVariableForLevel(0xc, …, fallbackToDefault: false)`), là où
   la face COMBAT tire `RandomAmount(minDmg, maxDmg)`. Un **seul** appel dans le corps.
5. **AUCUN filtre de camp, et le signe s'INVERSE sur un ami.** L'arbre est
   `Damageable(AdjacentUnits(Get(Target)))` — ni `Enemies`, ni `Friends`. Les trois feuilles
   dominantes du composite multiplient par `Fix64(-1)` sur `IsFriend(case.Caster, case.Target)` —
   **décompilé lu pour les trois** (`DamageUtility`, `KillUnitUtility`, `OverkillUnitUtility`
   `…u003CEvaluateAttackInStepsu003Ed__2$$MoveNext`). C'est le champ `friendly` de
   `ProbableDamageEvent`, dont ce module est le **premier consommateur** du dépôt.
6. **La cible principale n'est jamais comptée** : `DSLSelectors$$AdjacentUnits` =
   `Units(AdjacentTiles(origin), unique, sel) op_Subtraction origin` — le retrait est **dans** le
   sélecteur.
7. **Pas de cap à `nrOfProjectiles`** (§4).
8. **`Damageable` = `UnitsWithoutTrait(0x40e)`**, et `0x40e` = 1038 = `UnitTrait.Invincible` — enum à
   qualifier (à id égal : `TriggeredAbilityType` 1038 = `HatefulAssault`, `ActiveAbilityType` 1038 =
   `FoulInfusion`, `EffectType` 1038 = `CloudOfFlies_DamageReduction`). Le « vivant » vient d'ailleurs :
   `AdjacentTiles` résout des **occupants de tuile**.
9. **Le profil est le littéral `Blast`** (`Nullable<DamageProfileType>(0x12)`, `PiercingRatio` 15),
   pas l'arme du caster — **même littéral** que la face COMBAT. Le corps ne consulte donc du caster
   **ni arme, ni stat, ni trait** : seulement son identité, sa position, et le niveau de son propre
   passif 1116.

### La géométrie, re-dérivée et non héritée

`AdjacentTiles(origin)` → `IdunBattle.Entities.Selectors.AdjacentTilesSelector$$Select`, qui appelle
le slot `0x50` d'`IBattleQuery` avec les **quatre littéraux** `(entity, 0, 1, 1)` =
`IterateAdjacentTiles(from, onlyEmptyOrSteppable: false, onlyWalkableTiles: true,
allowTemporary: true)`, puis exclut les tuiles de l'origine. C'est le **même**
`IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext` que
`fire_of_absolution.count_adjacent_by_camp` et `boltstorm.count_all_targets` — donc la porte
d'élévation inconditionnelle `|Δelev| < 2` s'applique, et le foyer du port est `battle_query.
is_adjacent`, jamais `hexgeo.distance == 1`. Lecture **indépendante** de celle de `boltstorm`
(qui l'affirmait sans citer le sélecteur), et elle la confirme.

### Les deux sorties nulles ne sont pas la même

`!IsRegularAttack` → `yield break` (aucun step) ; boucle vide → `yield acc` avec `acc == Fix64(0)`
(un step à 0). Le dispatcher **somme**, donc les deux valent `0.0` observationnellement — la
distinction est notée parce qu'elle ne serait pas neutre sous un agrégateur qui moyenne (acquis
de #514/#518).

## 3. Le montage — pourquoi une GREFFE, et sur quel hôte

Les 3 porteurs sont 2 npc (`astraNpc4Mortar`, `astraNpc4MortarSurv`) et le SUMMON `astraSmnMortar`.
La gate de confrontabilité a été jouée **dans l'ordre** :

1. `buildNormalizedBC` refuse tout npc → aucun `--p-units`.
2. **SUMMON sans invocateur — vérifié par balayage, pas supposé** (`case-92` §5bis recours 2) :
   l'unique ability qui le déclare (`constants.unitId == "astraSmnMortar"`) est
   **`EnvFactionSummons:AstraMilitarum`**, et **aucune** unité du catalogue ne la porte dans
   `activeAbilities`/`passiveAbilities`. C'est un summon d'**environnement** : il n'y a pas de
   summoner à spawner, donc pas de voie « observer le summon » (#291). Même configuration
   qu'`admecSmnElectropriest` (tranche 12).
3. **Greffe** (`catalog_inject.write_grafted_seed_bc`, recours 3) sur `tauMarksman` — HERO au pool,
   arme distance portée 3, `replace=True`. Elle est **légitime et c'est LU** (lecture 9) : le corps
   ne consulte du caster ni arme, ni stat, ni trait — le profil est un littéral.

**Bras apparié** : deux runners identiques à un passif près (`graft` = `PassiveAbilities=[1116]`,
`base` = le bras greffé **moins** 1116 — surtout pas « les passifs d'origine », `replace=True` les a
déjà retirés ; piège mesuré par la tranche 9). `terme_natif = natif_graft − natif_base`.

Board `MC1_67`, seed `41116`, `Health = RemainingHealth = 10000` pour tout le monde (personne ne meurt,
et le composite `DamageDealt` reste dans sa zone **linéaire** — c'est ce qui rend `hits1` et `mean`
visibles). Layout mesuré : `C=(3,4) T=(0,2) P1=(0,3) P2=(0,1) K1=(0,0) K2=(0,4) K3=(0,6)`.
Roster : `tauMarksman` + `necroWarden` (ami) contre `astraBullgryn` (la cible, **fixe**),
`astraCreed`, `astraDreir`. `T` est à portée 3 de `C` et **non adjacente** à lui — sans cette
contrainte, `C` (qui est son propre ami) serait un voisin AMI permanent et `cF` cesserait de
discriminer.

Le probe **refuse** (`MontageError`) si l'attaque normale de l'hôte n'est pas dans
`REGULAR_ATTACK_ABILITY_TYPES` : la gate du corps natif couperait alors le terme à tous les crans, et
un accord `0 == 0` ne prouverait rien. Mesuré : elle y est.

## 4. L'ability prise à l'envers — trois écarts NATIFS assumés

`ShrapnelAbility$$CreateTrigger` : `On(0x26, true) & OwnerIsCaster & IsRangedAttack`.

`ShrapnelAbility$$CreateBehaviour` :

```
minDmg = GetVariableForLevel(config, 0xc, abilityState, false)
maxDmg = GetVariableForLevel(config, 0xd, abilityState, false)
AttackWithAttackDamage(
    Owner@0x30,
    Cache(PickRandomly(AdjacentTiles(Target@0x60),
                       GetNumberConstant(0x1f) = nrOfProjectiles, 0, 0x7fffffff, false), true),
    DSLFormulas.RandomAmount(minDmg, maxDmg),
    (DamageProfileType?)0x12 = Blast,
    GetNumberConstant(0x2f) = nrOfHits, ... )
```

Gameconfig `Shrapnel` : `nrOfHits = 2`, `nrOfProjectiles = 3`, `attackRangeType = Ranged`,
`variablesAffectedByRarityBonus = [minDmg, maxDmg]`.

Trois écarts **natifs** entre les deux corps, lus séparément (ils ne partagent aucun sélecteur) :

* le playbook prend **toutes** les unités adjacentes damageables ; le behaviour n'en frappe que
  `nrOfProjectiles` **tuiles tirées au sort** ;
* le playbook prédit `minDmg` **seul** ; le behaviour tire `RandomAmount(minDmg, maxDmg)` ;
* le playbook applique `nrOfHits` à l'**utilité** ; le behaviour l'applique aux **coups**.

Même forme d'écart que la tranche 12 (où le playbook ignorait le `Damageable` et le gate
`IsMeleeAttack` de sa face combat). On mirrore chaque corps sur **son** décompilé.

## 5. Mesures — quatre crans, cible et caster FIXES

Seul ce qui entoure la cible bouge ; les cardinaux sont **re-dérivés** des positions live avec
l'adjacence native (`bq.is_adjacent`), et le probe refuse si le cran attendu n'est pas installé.

| cran | ennemis adj. | amis adj. | natif `graft` | natif `base` | **TERME natif** | port | port muté | **TERME port** | écart |
|---|---|---|---|---|---|---|---|---|---|
| `c0` | 0 | 0 | 42.711458 | 42.711458 | **+0.000000** | 48.170366 | 48.170366 | +0.000000 | 0 |
| `c1` | **1** | 0 | 45.890822 | 42.711458 | **+3.179364** | 51.349730 | 48.170366 | +3.179364 | −1,2e−8 |
| `c2` | **2** | 0 | 49.070186 | 42.711458 | **+6.358728** | 54.529094 | 48.170366 | +6.358728 | −2,4e−8 |
| `cF` | 0 | **1** | 39.532094 | 42.711458 | **−3.179364** | 44.991002 | 48.170366 | −3.179364 | +1,2e−8 |

Le terme n'est pas un poids plat mais une **utilité de dégât complète** : l'accord à **1e−8** est
donc bien plus contraignant que sur les tranches à poids BC (où il suffisait de retrouver un entier).

Deux crans sont **le** résultat de cette tranche :

* **`c2` tranche SOMME contre MOYENNE.** Le terme **double** avec le cardinal. Un port écrit par
  analogie avec `Psyker` — qui balaie le **même** arbre — rendrait ici `3.179364` au lieu de
  `6.358728`.
* **`cF` tranche le CAMP *et* le SIGNE.** Un ami du caster adjacent à la cible ne verse pas `0`
  (ce que rendrait un `Enemies(…)`) ni `+3.179364` (ce que rendrait un comptage sans négation) :
  il verse **`−3.179364`**. C'est la seule tranche de ce filon où le playbook peut rendre une utilité
  négative pour une raison qui n'est pas un poids BC négatif.

## 6. Contre-épreuves — mordantes ET réciproques

Critère = **déplacement du port par rapport au port NON MUTÉ**, jamais l'écart au natif (la paire
porte un résidu constant, §8 — un critère « écart au natif > EPS » serait vrai même pour un mutant
inerte ; piège de #441 et #446). Chaque mutant est joué **à chaque cran** :

| mutant | `c0` | `c1` | `c2` | `cF` |
|---|---|---|---|---|
| `mean` (÷ |cibles|) | — | — | **−3.179364** | — |
| `enemies_only` (filtre le camp) | — | — | — | **+3.179364** |
| `hits1` (pas de × `nrOfHits`) | — | **−1.589682** | **−3.179364** | **+1.589682** |
| `avg_minmax` (moyenne min/max) | — | **+0.799840** | **+1.599680** | **−0.799840** |
| `no_friendly_neg` (`friendly=False`) | — | — | — | **+6.358728** |
| `include_target` (compte la cible) | **+3.179364** | +3.179364 | +3.179364 | +3.179364 |

Les six mordent. Cinq ont une réciproque stricte (au moins un cran inerte) ; `include_target` mord
partout **par construction** (la cible principale est là à tous les crans), et ce qu'on lui demande
est de mordre en **`c0`** — le seul cran où tous les autres sont inertes, donc le seul qui prouve que
le `op_Subtraction(origin)` du sélecteur est porté. La garde l'exempte **nommément**.

Deux lectures se lisent dans les chiffres : `hits1` déplace exactement de **la moitié** du terme
(donc `nrOfHits = 2` multiplie bien l'utilité), et `no_friendly_neg` déplace de **deux fois** le terme
de `cF` (passage de `−3.179364` à `+3.179364` : c'est bien un changement de **signe**, pas une
annulation).

**La garde a elle-même été éprouvée par quatre mutants du PORT** (le fichier livré, muté sur disque,
patch **vérifié** — le script de mutation lève sur motif introuvable, sans quoi un vert ne prouverait
rien) :

| mutant du port livré | tests rouges / 7 |
|---|---|
| `mean` | **3** |
| `hits1` | **2** |
| `no_friendly_neg` | **3** |
| `enemies_only` | **4** |

Puis restauration (`git checkout --`) et re-jeu : **7 passed**.

## 7. Face MOVE : `yield Fix64(0)` CONSTANT — ce n'est PAS un résidu

`…ShrapnelPlaybook.u003CCalculateMovementUtilityInStepsInternalu003Ed__1$$MoveNext` a été **lu** : un
unique état, `Fix64.op_Implicit(0)`, aucun champ de la SM consulté. Elle n'entre donc pas dans
`TRIGGERED_MOVE_PLAYBOOKS`, et **son absence EST le comportement natif** (même forme que `Lakrimae`,
`BarbedOvipositor`, `Neuroparasite`, `Boltstorm`, `FireOfAbsolution`, `CosmicHorror`, `ElectroShock`).

## 8. Résidus NOMMÉS

* **`#419-r1-tr13-r1` — l'écart constant de la paire.** Le port est **au-dessus** du natif de
  `+5.458908`, **invariant aux quatre crans** (c'est ce que la garde asserte, à la place d'une
  égalité en niveau qui rougirait pour une cause étrangère). Il ne varie pas avec le terme : il vient
  du composite de DÉGÂT sur le couple (`tauMarksman`, `astraBullgryn`), non instruit ici. Même forme
  que le résidu de #446 et de la tranche 12.
* **`#419-r1-tr13-r2` — les porteurs RÉELS ne sont pas confrontés.** La greffe ne couvre ni les
  stats, ni les traits, ni l'arme du summon/npc. Elle est légitime pour ce terme (le corps ne lit du
  caster que son identité, sa position et le niveau de son passif), mais le `Mortar` lui-même n'a
  jamais été en bataille. Débloqueur nommé, déjà porté par `case-92` §5bis : donner à
  `buildNormalizedBC` un chemin de stats explicite pour summons/npc. **Partagé** avec
  `#419-r1-tr12-r2`.
* **`#419-r1-tr13-r3` — la face COMBAT n'est pas portée.** `ShrapnelAbility$$CreateBehaviour`
  (`AttackWithAttackDamage(Owner, Cache(PickRandomly(AdjacentTiles(Target), nrOfProjectiles)),
  RandomAmount(minDmg, maxDmg), Blast, nrOfHits)`) n'a **aucun** mirror dans `engine/runner` — les 15
  occurrences de `1116` y désignent toutes `ActiveAbilityType.RadBombardment`. Une attaque à distance
  du `Mortar` ne fait donc **pas** partir la grenaille côté exécution. Même forme que
  `#419-r1-tr9-r4-r3`, `#419-r1-tr10-r3` et `#419-r1-tr12-r3`. La face DÉCISION livrée ne dit rien de
  l'exécution.
* **`#419-r1-tr13-r4` — `is_ranged=True` n'est pas EXERCÉ.** Le corps du playbook ne calcule pas ce
  booléen (il n'appelle ni `IsMeleeAttack` ni `FindRangedWeapon`) : c'est la requête native qui le
  dérive. Le port l'écrit `True`, étayé par **deux** sources concordantes (le trigger
  `& IsRangedAttack` et `attackRangeType: Ranged` au gameconfig) — mais aucun modifier
  ranged-conditionnel n'est présent au montage, donc la valeur n'est **pas** discriminée par la
  mesure. Un montage avec un effet gaté `IsRangedAttack` sur l'hôte le trancherait.
* **`#419-r1-tr13-r5` — le filtre `Invincible` n'est pas exercé.** Aucune unité du montage ne porte
  `UnitTrait.Invincible` (0x40e). Le littéral est lu au décompilé (`DSLSelectors$$Damageable` →
  `UnitsWithoutTrait(…, 0x40e, 3)`), pas confronté.
* **`#419-r1-tr13-r6` — les deux branches alternatives de `KillUnitUtility`.** Son corps ne négate
  pas toujours sur `IsFriend` : si `UnitExtensions.HasFriendlyFire(caster)` il négate sur `IsEnemy`
  (**inverse**), et un slot `0x93` d'`IBattleQuery` peut négater seul. Le port (`ProbableDamageEvent.
  friendly` → signe appliqué au composite entier) ne distingue pas ces branches. Elles sont
  inatteignables dans le régime confronté ; les distinguer relève du composite, pas de cette tranche.
* **`#419-r1-tr10-r2` (PARTAGÉ, déjà ouvert) — les unités MULTI-TUILES.** `splash_targets` ne connaît
  que la MainTile (`scene.pos`) alors qu'`AdjacentTiles` itère `EntityExtensions.IterateTiles`. Ce
  port hérite du résidu, il ne l'aggrave pas.

## 9. Livré

* `scripts/python/engine/playbook/shrapnel.py` — le playbook.
* `scripts/python/engine/playbook/psyker.py` — entrée `TRIGGERED_ATTACK_PLAYBOOKS[1116]`.
* `scripts/python/probe_419r1tr13_shrapnel.py` — bras apparié, 4 crans, 6 contre-épreuves.
* `scripts/python/tests/engine/test_419r1tr13_shrapnel_live.py` — 7 gardes.

Après cette tranche, `probe_419_triggered_playbook_inventory.py --residuals` rend **17** playbooks
ATTACK portés+câblés et **6** résidus à porteur dispatché réel (`HeavyBoltPistol` 1083,
`Pyreblaster` 1098, `Wraithcannon` 1220, `Fealty` 1512, `PrehensilePincerTail` 1095,
`SwornProtector_Protect` 1075), plus `TalonOfHorus` 1484 à **0** porteur. ⚠ Chiffres à **re-dériver**,
jamais à citer.
