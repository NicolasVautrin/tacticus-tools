# #419-r1 tranche 5 — `LightImUp` (1103), face ATTACK : PORTÉ + CONFRONTÉ LIVE

Tête des résidus ATTACK à corps non trivial de #419-r1 (5 porteurs dispatchés : `orksWarboss`
« Gulgortz » HERO au pool + `orksBossWarboss`, `orksBossWarbossLHE`, `orksNpcWarboss`,
`orksNpcWarbossSurv`). Le corps n'avait **jamais** été lu. Inventaire re-dérivé après la tranche
(`probe_419_triggered_playbook_inventory.py --residuals`) : `porte+cable` **9 → 10**,
`non porte+cable` **15 → 14**.

## 0. Gate de confrontabilité

| porteur | catégorie | chemin d'arrivée en bataille |
|---|---|---|
| `orksWarboss` | **HERO** | `rl_duel build --list-pool` au rank 17 — spawné directement |
| `orksBossWarboss`, `orksBossWarbossLHE`, `orksNpcWarboss`, `orksNpcWarbossSurv` | npc | hors-jeu |

Aucune greffe n'est nécessaire : le HERO du pool porte l'ability par son **kit gameconfig**
(`passiveAbilities: ["LightImUp"]`, vérifié live dans l'`AbilitiesComponent`). Les quatre npc ne
sont donc **pas** un obstacle, et il n'y a pas de canal relique/mythique en jeu ici.

**Piège du nom, levé** : `1103` désigne **trois** artefacts —
`TriggeredAbilityType.LightImUp` (ce playbook), `ActiveAbilityType.Supercharge`,
`EffectType.KanOpener_ReduceArmor`. Corollaire outillage : `gameconfig.ability_name(1103)` rend
`"Supercharge"` (l'index est celui d'`ActiveAbilityType`) — toute lecture de config passe donc par
le **nom** `"LightImUp"`.

## 1. Ce que dit le décompilé

`IdunBattle.AI.Playbook.Loki.LightImUpPlaybook$$CalculateAttackUtilityInStepsInternal` monte la SM
`d__2` — disposition **lue dans le wrapper** : `sm@+0x10 = state`, `sm@+0x18 = current`,
`sm@+0x20 = this` (le playbook), `sm@+0x28 = case`. Le délégué `getUtilityVal` n'est **pas capturé**
(comme `Neuroparasite`) : la sortie n'est **aucune** clé de `Utilities.Default.TriggeredAbilities`.
Corps : `LightImUpPlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__2$$MoveNext`, **cinq**
états de yield.

```csharp
if (!IsMeleeAttack(case))         yield Fix64(0);                          // état 1
else if (!IsRegularAttack(case))  yield Fix64(0);                          // état 2
else {
    var st = GetAbilityState(case.Caster);
    int hits   = ability.GetHits();                     // ConfigConst(0x2f = nrOfHits) = 3
    int amount = ability.GetAverageDamage(st).Calculate(new AbilityEntities());
    var profil = ability.GetDamageProfile();            // constants.damageProfile = Projectile
    var pred1  = Query.<slot 0x22>(case.Caster, case.Target, case.CasterPosition);
    if (pred1.WillBeKill)  yield CalculateAttackUtilityForSecondaryTarget(case, hits);   // état 3
    else {
        var pred2 = Query.<slot 0x28>(case.Caster, case.Target, case.CasterPosition,
                                      case.AbilityType, amount, profil, hits);
        pred2.Add(pred1);
        if (!pred2.MightBeKill) yield CalculateAttackUtilityForMainTarget(case, hits);   // état 4
        else yield (Main + Secondary) / Fix64(2);                                        // état 5
    }
}
```

Les deux méthodes **propres** au playbook ont leurs propres symboles :
`$$CalculateAttackUtilityForMainTarget` (une prédiction sur `case.Target` → `CalculateUtility
FromDamageEvent`) et `$$CalculateAttackUtilityForSecondaryTarget` (la **moyenne** des utilités sur
`GetPossibleSecondaryTargets`, `Count == 0` → `Fix64(0)` avant tout calcul de montant).

Le sélecteur, `IdunBattleLogic.Entities.Abilities.Triggered.Loki.LightImUpAbility$$GetPossibleSecondaryTargets` :

```
Damageable( SurroundingEnemies(unit = Caster@DSLSelectors+0x48, unitTile = <+0x50>,
                               range = ConfigConst(0x16) = 3, unique = 1, sel = 3)
            |> Unobscured(Owner@+0x30, _)
            |> _ - Target@+0x60 )
```

Sept lectures qui ne se devinent pas — le détail complet (avec les symboles) vit dans l'en-tête de
`scripts/python/engine/playbook/light_im_up.py`. Les trois qui ont coûté le plus :

1. **La gate 1 est une gate de MÊLÉE, et elle porte sur l'attaque DU CASE.**
   `IBattleQuery` **slot 2** = `IdunBattle.Core.Services.BattleQuery$$IsMeleeAttack` (identifié par
   `IdunBattle.Core.Services.DamagePrediction$$IsMeleeAttack`, qui appelle le même slot sur la même
   klass d'interface) : `AttackRangeType` 0 → faux, 1 `Melee` → vrai, 2 `Ranged` → faux, 3 `Normal`
   → `!HasFlag(caster, 0x15 = ForceRangedAttack) && AreEntitiesAdjacent(casterPos, target)`. Le
   passif, lui, est **`Ranged`** au gameconfig : la gate mêlée et le profil `Projectile` cohabitent
   — c'est une riposte au corps à corps **qui tire**, et les confondre inverse le port.
2. **L'`ability` transmise à la prédiction est `case.AbilityType`, jamais 1103.** Les prédicats DSL
   des effets d'attaquant (`IdunBattle.Entities.Triggers.IsMeleeAttackAbilityTrigger$$ShouldTrigger`
   appelle le **même** slot 2 sur `AbilityEntities.Ability`) s'évaluent donc sur l'attaque NORMALE.
3. **Les trois sorties sont un arbre de KILL**, mise en utilité du « leftover hits » du tooltip :
   normale tue à coup sûr → tous les coups partent ailleurs (secondaire) ; normale + passif ne peut
   même pas tuer → tout reste sur la cible (principal) ; indéterminé → moyenne.

## 2. Face MOVE

`LightImUpPlaybook.u003CCalculateMovementUtilityInStepsInternalu003Ed__1$$MoveNext` rend 0 (déjà
inventorié par #193) → pas d'entrée au registre `TRIGGERED_MOVE_PLAYBOOKS`, et son absence **est** le
comportement natif.

## 3. Le montage, et l'oracle qu'il exploite

Le hook `ncPlaybookPredict` (#369/#375) sait invoquer les **trois** entrées natives séparément
(`via: attackUtilityForMainTarget | attackUtilityForSecondaryTarget | attackUtilityInSteps`,
`abilityKind: "triggered"`). On ne compare donc pas un scalaire agrégé : chaque **étage** est
confronté, ce qui **localise** une divergence. `LightImUp` n'appelant jamais `GetUtilityValue`, la
minoration que le hook signale (`utilityWeightsProvided: false`) ne le concerne pas — les trois
utilités rendues sont fidèles.

Board `MC1_67`, seed `419503`, rank 17. Géométrie **construite** : `orksWarboss` au centre d'une
étoile, trois cibles **adjacentes** à des PV calibrés, une quatrième à 2-3 hex.

⚠ **`--unit-stat` doit poser `RemainingHealth`, pas seulement `Health`** — le natif lit le premier.

Les PV ne sont pas devinés : pour chaque cible le port rend `raw` de l'attaque normale et `raw` du
passif, d'où `état3 ⇔ hp ≤ willBeKill(normale)`, `état4 ⇔ hp > max(normale) + max(passif)`, `état5`
entre les deux. Calibrage mesuré (amount 1940, 3 coups) : `necroWarden` état 3 si `hp ≤ 4696` ;
`ultraTitus` (source de BLOCK → `willBeKill` faux dès `hp > 0`) état 5 tant que `hp ≤ 6268` ;
`admecDestroyer` état 4 dès `hp > 11235`.

**L'état joué est attribué par les seules mesures NATIVES** (`inSteps` comparé à `Main`, `Sec` et
leur moyenne) : l'attestation ne doit rien au port, et une ligne dont l'état n'est pas identifiable
de façon **unique** est un échec, pas un accord.

⚠ **Piège de montage mesuré** : les voies `...ForMainTarget` / `...ForSecondaryTarget` doivent être
interrogées avec `attackAbility: "normalAttack"` **elles aussi**. Le natif ne les appelle jamais
autrement que depuis sa propre SM, dont les gates garantissent un case qui **nomme** une ability. Un
case anonyme fait évaluer faux à tous les prédicats DSL d'attaquant : sur `ultraTitus`,
`healthDmg = [699, 1047]` au lieu de `[1047, 1572]` — un facteur 1.5 de modifiers perdu, donc un
oracle qui répond à une **autre** question.

## 4. Ce que la mesure a corrigé dans le port

### 4a. Le canal du slot 0x28 applique le spread ±20 % — il n'est **pas** « prédéfini »

Le premier jet posait `spread_pct=0`, par analogie avec `psyker.py` / `avalanche_of_muscle.py`. La
capture native le réfute, et **exactement** : sur `ultraTitus` (armure 2312, aucun bouclier),
`amount = 1940`, 3 coups → natif `healthDmg = [1047, 1572]`, soit `[349, 524]` par coup.
`0.8 × 1940 × p = 349` et `1.2 × 1940 × p = 524` avec `p = 0.225` : **les deux bornes tombent**. Un
canal prédéfini (min = max) et un `RandomAmount(minDmg, maxDmg)` (`[1662, 2218] × p × 3 =
[1122, 1497]`) sont l'un et l'autre réfutés par ce même couple.

### 4b. `IsMeleeAttack` se ré-évalue **par cible** dans les modifiers

La gate du corps porte sur `case.Target` ; le prédicat que consomment les effets d'attaquant porte
sur la cible **de la prédiction courante** (`PredictAttackRaw` pose `entities.Target =
request.target`). Une cible secondaire à 2-3 hex n'est donc pas « en mêlée », même si le case l'était.

**La signature qui a nommé la cause** : décalage **constant** de `+0.485523` sur les trois cases dont
l'ensemble secondaire contenait la cible non adjacente, et **zéro** sur celui où cette même unité
était la cible principale. `0.485523 × 3 = 1.456570` = exactement l'écart mesuré sur `...ForMainTarget`
de cette unité (`2.909806` natif contre `4.366376` en régime mêlée forcé, facteur 1.5006).

## 5. Mesures (runner `MC1_67`/`419503`, `orksWarboss` rank 17, `amount = 1940`, `hits = 3`)

**Étage isolé** — trois voies natives × quatre cibles, écart `port − natif` :

| cible | hp | gates natives | état natif | main | sec | inSteps |
|---|---|---|---|---|---|---|
| `necroWarden` | 400 | regular ✓ melee ✓ | **état 3** | 239.502488 / **0** | 15.622534 / **0** | 15.622534 / **0** |
| `ultraTitus` | 3 000 | regular ✓ melee ✓ | **état 5** | 43.637575 / **0** | 80.910838 / **0** | 62.274207 / **0** |
| `admecDestroyer` | 900 000 | regular ✓ melee ✓ | **état 4** | 0.320222 / **0** | 95.349956 / **0** | 0.320222 / **0** |
| `astraBullgryn` (2-3 hex) | 30 000 | regular ✓ melee ✗ | **état 1** | 2.909806 / **0** | 94.486761 / **0** | 0.000000 / **0** |

État 2 exercé à part (`attackAbility = Waaagh 1058`) : natif `isRegularAttack: false`, `0.0` des deux
côtés. `Count == 0` : ensemble vide → `0.0`.

**Étage intégré** — `pairUtility` natif contre le port, et le port **privé** du playbook 1103 :

| cible | natif | port | port muté | manque | terme isolé |
|---|---|---|---|---|---|
| `necroWarden` | 255.125022 | 255.125022 | 239.502488 | **+15.622534** | +15.622534 |
| `ultraTitus` | 212.207584 | 212.207584 | 149.933378 | **+62.274207** | +62.274207 |
| `admecDestroyer` | 0.972442 | 0.972442 | 0.652221 | **+0.320222** | +0.320222 |
| `astraBullgryn` | 1.306580 | 1.306580 | 1.306580 | **+0.000000** | +0.000000 |

Le manque vaut **exactement** le terme mesuré à l'étage isolé, cible par cible : le câblage est
prouvé, pas supposé. **Aucun écart résiduel** sur cette paire (contrairement à #446).

## 6. L'ancrage du disque secondaire, tranché par contre-épreuve

`SurroundingEnemies(unit, unitTile, ...)` — surcharge **six** arguments dont toute la géométrie passe
par `unitTile` (`SurroundingTiles(unitTile, includeCenter: 1, range) - Tiles(unitTile)`). Le playbook
alimente `AbilityEntities.CasterTile` avec `case.CasterPosition.MainTile` — **seul** des dix
playbooks attack portés à le faire. La lecture « le disque suit la tuile d'attaque » n'est pas
déduite du nom du champ : elle est **mesurée**.

Depuis la tuile candidate `(4,3)`, dont le disque de rayon 3 contient `{u79, u81}` là où celui de la
tuile courante contient `{u79, u81, u83}` :

| | valeur |
|---|---|
| natif | `14.647084008902311` |
| port, disque ancré sur la **tuile d'attaque** | `14.64708400285278` (écart 6e-9) |
| port, disque ancré sur la **tuile réelle** | `10.734658006212678` |

Les deux variantes **divergent** — le montage discrimine, et il tranche. `Unobscured`, lui, prend
`Owner@+0x30` (une **entité**) : sa ligne de vue part de la MainTile **réelle**. Les deux ancrages
coexistent dans le même arbre.

## 7. Contre-épreuves de mutation — et le trou que la troisième a trouvé

| mutation | attrapée par |
|---|---|
| A — `spread_pct=0` restauré | DIFF sur les trois faces |
| B — `is_melee` constant `True` | DIFF, **exactement** la signature `+0.485523` |
| C — disque ancré sur la tuile **réelle** | **le probe rendait VERT** — corrigé, voir ci-dessous |
| D — playbook retiré du registre | `MontageError` à l'étage intégré |

**La mutation C est le résultat le plus utile de la tranche.** Ancrer le disque sur la tuile réelle
ne change **rien** aux trois faces mesurées depuis la tuile courante (elles coïncident), et la
contre-épreuve d'ancrage — le seul discriminant — n'entrait pas dans le verdict du probe : elle
rendait `confronted: false` (la mutation supprime jusqu'à la possibilité de trouver une tuile
discriminante) et le probe imprimait `-> OK`. Le probe compte désormais l'ancrage ; la mutation rend
`rc = 1`. La garde pytest, elle, rougissait déjà (`assert a["confronted"]`).

## 8. Résidus NOMMÉS

* **`#419-r1-tr5-r1`** — `UnitFlag.ForceRangedAttack` (21) n'est pas capturé par
  `combatSnapshot.unitFlags` (la Scene n'en stocke que quatre : `PreventOverkill` / `Moved` /
  `Teleported` / `ActiveAbilityUsed`). Le port le lit comme **absent**. Dégradation permissive-en-plus,
  qui ne mord que sur une attaque normale de type `Normal(3)` dont le porteur serait sous
  `ForceRangedAttack` **tout en étant adjacent**. Capteur manquant nommé : ajouter
  `"ForceRangedAttack"` à la liste de `scene._unit_flag_from_snapshot`.
* **`#419-r1-tr5-r2`** — `psyker.py` et `avalanche_of_muscle.py` posent `spread_pct=0` sur le slot
  0x23, qui converge pourtant vers le **même** slot 10 d'`IDamagePredictionQuery` que le 0x28 mesuré
  ici (les deux surcharges `BattleQuery$$GetAttackPrediction` à montant, `…d5d0` et `…d9a0`, y
  mènent ; `GetMultiHitAttackPrediction` passe par la seconde). Les deux lectures ne peuvent pas être
  vraies ensemble. Celle-ci est mesurée **directement** sur les bornes capturées ; celle de `psyker`
  l'est **indirectement** sur une utilité finale (accord à 4e-5, #45-s18). **Aucune des deux n'est
  touchée par cette tranche** — le discriminant reste à trouver. Forme suggérée : capturer
  `ProbableDamageEvent` sur le call-site psyker (`via` dédié ou hook `damage-prediction`) et lire
  `healthDmgMin` vs `healthDmgMax`.
* **`#419-r1-tr5-r3`** — les branches `Melee(1)` / `Ranged(2)` d'`is_melee_attack` ne sont exercées
  par aucun montage, et c'est structurel : `IsRegularAttack` garantit une attaque **normale**, dont
  l'entrée n'existe pas au gameconfig (`ab_name_by_id[69] = "Loki_NormalAttack"`,
  `GC.ability(...) → null`). Le port prend donc toujours la branche `Normal(3)`, qui est **celle que
  le natif prend** pour l'id 69 (mesuré : `astraBullgryn` à 2 hex rend `isMeleeAttack: false`, les
  trois adjacentes `true`). Les deux autres branches sont du mirror de fidélité pour un
  `NormalAttackType` concret typé au gameconfig (ex. `1076 MV71SniperDroneSquadAttack`) : **non
  confrontées**.

## 9. Non couvert

* Le régime **`Unobscured`** du sélecteur secondaire : le montage l'atteste inactif sur les tuiles
  retenues, il ne l'exerce pas (il faudrait un relief bloquant entre le caster et une cible à 2 hex).
* Les **quatre porteurs npc** : hors-jeu, et sans intérêt ici — le HERO du pool exerce le même corps
  avec la même config.
* La **face COMBAT** du passif (`LightImUpAbility$$CreateBehaviour` : `Attack(...) & If(IsDead(...),
  ...)` sur `NumLeftOverHits`) : hors périmètre de cette tranche, qui ne porte que la face DÉCISION.

## 10. Livré

* `scripts/python/engine/playbook/light_im_up.py` — le playbook (les trois faces + le sélecteur).
* `scripts/python/engine/playbook/psyker.py` — entrée `TRIGGERED_ATTACK_PLAYBOOKS[1103]`.
* `scripts/python/probe_419r1tr5_light_im_up.py` — montage, mesure aux deux étages, attestation
  d'état, contre-épreuve d'ancrage.
* `scripts/python/tests/engine/test_419r1tr5_light_im_up_live.py` — 7 gardes live.
