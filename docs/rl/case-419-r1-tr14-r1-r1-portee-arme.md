# `#419-r1-tr14-r1-r1` — l'attaque normale est gatée sur la PORTÉE de l'arme

Ouvert par la PR #698 sur un écart d'étage PRÉDICTION : porteur `templNpc1Initiate` (arme `Chain`,
mêlée, 2 coups), depuis une tuile à 2 hex, le natif rend `0..0` en **1** coup et le port
`732..1098` en **2**.

## 1. Ce que la RE a tranché — et une affirmation du port démentie

Le foyer est **`IdunBattle.Core.Services.BattleQuery$$GetAttackWeaponForDefaultNormalAttack(attacker,
attackerTiles, target)`**, la surcharge du slot **`0xaf`** d'`IBattleQuery`. Trois surcharges
existent et **ne font pas la même chose** ; l'appariement slot↔arité est LU sur les délégués du
proxy `RecordedSimulationRequestsBattleQuery` :

| slot | signature | corps |
|---|---|---|
| `0xae` | `(attacker, attackerTiles)` | chaîne de repli **croisé** mêlée↔distance |
| `0xaf` | `(attacker, attackerTiles, **target**)` | `GetAbilityAttackRangeType` + `HasFlag(0x15)` + `AreEntitiesAdjacent` ; **aucun repli** |
| `0xb0` | `(attacker, attackerTiles, **targetTiles**)` | `AreTilesAdjacent` ; mêlée **ou** distance, sans porte de portée |

`services/battle_query.py` écrivait de `0xaf` : « **NON PORTEE, aucun consommateur porte ne
l'emprunte** ». C'est **faux**, et c'est la cause racine. `IdunBattleLogic.Entities.Abilities.Active.
Loki.ALoki_NormalAttackAbility$$FindAttackWeapon(this, entities)` — la surcharge à **deux**
arguments — invoque le slot `0xaf`, et ses appelants (xrefs lues) sont :

* `ALoki_NormalAttackAbility$$PredictAttack` — face **DÉCISION** ;
* `ALoki_NormalAttackAbility$$ExecuteBehaviour` — face **COMBAT** ;
* les huit attaques normales dérivées (`ProperKilly`, `RighteousRepugnance`, `TalonOfHorus`,
  `Boltstorm`, `Fealty`, `FeederTendrils`, `OptimizedGait`).

**Un seul foyer natif, deux faces** — corriger le foyer du port est donc fidèle des deux côtés.

Corps de `0xaf`, LU :

```
rangeType = GetAbilityAttackRangeType(GetNormalAttackType(attacker));   // 0 None 1 Melee 2 Ranged 3 Normal
if (rangeType == Melee)  return FindMeleeWeapon(attacker, attackerTiles, target);
if (rangeType == Normal && !UnitExtensions.HasFlag(attacker, 0x15)      // ForceRangedAttack
                        && AreEntitiesAdjacent(attackerTiles, target))
    return FindMeleeWeapon(attacker, attackerTiles, target);
return FindRangedWeapon(attacker, attackerTiles, target, distance);     // AUCUN repli croisé
```

`FindRangedWeapon` (surcharge à 5 arguments) filtre `(int)distance <= weapon.Range.Value +
rangeStatBonus` puis appelle `SelectBestDamageWeapon` (target non nul) ou `SelectMaxRangeWeapon` —
**les deux commencent par `if (weapons.Count == 0) return null`**. `FindMeleeWeapon` est le
symétrique, filtre `IsMelee`, même sortie nulle sur ensemble vide.

Ce que les deux consommateurs font du `null` :

* `PredictAttack` : `weapon = FindAttackWeapon(entities); if (weapon != null && TryGet<DamageProfile>
  (...)) { … } else { <slot 0x26>(…, amount: 0, hits: 1, widgets VIDES) }`. Le `1` en position
  `hits` est un **littéral** (visible aussi dans `BattleQuery$$GetAttackPrediction`) — d'où `0..0`
  en 1 coup.
* `ExecuteBehaviour` tient tout entier dans le gate :
  `weapon = FindAttackWeapon(entities); if (weapon == null) return;` — ni `ExecuteInformWeapon`, ni
  `ExecuteNormalAttack`, ni `ExecuteTriggerAbilities`.

**La mesure héritée est donc expliquée par la RE, et le port avait tort.**

## 2. Ce qui a été porté

1. **`services/battle_query.py`** — `get_attack_weapon_for_default_normal_attack` devient le mirror
   1:1 de `0xaf` : branche mêlée sur `is_adjacent` seul, branche distance filtrée par `dist <=
   Range`, **`None` si l'ensemble retenu est vide**. Le repli croisé (`in_range or melee or ranged`,
   `melee or weapons`) disparaît. Le tri mêlée/distance passe de `bool(w["Range"])` à
   `weapon_is_melee` (`get_IsMelee` : `Range is None || Range < 2`), le prédicat que le natif lit.
2. **`playbook/prediction/normal_attack.py`** — la **voie SANS ARME** : `make_normal_attack_
   predictions` résout l'arme en tête (mirror du `weapon = FindAttackWeapon(...)` natif) et, si elle
   est nulle, rend `ProbableDamageEvent(prediction=DamagePredictionResult(applied_hits=1))`.
3. **`runner/operations/damage_ops/normal.py`** — le **no-op combat** (`if _w is None: return None`),
   posé APRÈS `On(0x2a = PreUnitAbility)`, le gate acteur-mort et la re-résolution de cible : ces
   trois-là vivent dans `ActiveAbilityOperation$$ExecuteInternal`, donc en amont d'`ExecuteBehaviour`.
4. **`runner/damage_model.py` + le même site** — `is_adjacent` **découplé** de `dist`, et la
   distance devient **RÉELLE**.

### Le second défaut, que seule la face COMBAT pouvait montrer

Le runner calculait `dist = 1 if adjacent else 2` — une distance **binaire**. La porte
`dist <= Range` ne pouvait donc **jamais** mordre au-delà de 2 : une unité tirait à 3 hex avec une
arme de portée 2. Mesuré live (`adeptCanoness` sur `MC1_67`, cible à 3 hex, `--combat`) :

| | dégât | tirages RNG |
|---|---|---|
| natif | **0** | **0** |
| port (fix du seul foyer) | 1311 | 2 |
| port (après découplage) | **0** | **0** |

Le natif lit bien **deux canaux distincts** — `AreEntitiesAdjacent` pour la branche, et une distance
rendue par le service de mouvement pour la porte. Les rabattre l'un sur l'autre rendait la porte
inopérante.

## 3. Mesures offline (683 unités du catalogue)

`probe_419r1tr14r1r1_weapon_range_gate.py` :

| mesure | valeur |
|---|---|
| armes `Range == 1` (où les deux tris divergent) | **0** — le changement de tri est value-preserving |
| ventilation `get_IsMelee` | 81 sans arme / 271 mêlée seule / **0 distance seule** / 331 mixtes |
| cas `ARME → VIDE` (dist 1..8) | **3776** sur 5464, 602 unités |
| cas où la distance RÉELLE change le choix (combat) | **1879**, 331 unités — **tous** `ARME → VIDE`, **0** changement d'arme |

Le régime « adjacent + aucune arme de mêlée » est **VIDE** sur ce catalogue (0 unité `ranged_only`) :
la branche mêlée ne change donc rien en pratique, et c'est dit plutôt que compté comme une victoire.
L'étape 6 du probe confronte sa propre simulation au **code livré** (0 écart) — une mesure qui aurait
divergé du port mesurerait une hypothèse.

## 4. Généralisation — un porteur MIXTE, trois issues, un boundary

Le résidu s'est ouvert sur un porteur **mêlée seule**, où la porte se réduit à « adjacent ou rien ».
`probe_419r1tr14r1r1_range_gate_generalisation.py` le confronte sur `adeptCanoness` (HERO du pool,
`Chain` mêlée 3 coups + `Bolter` portée 2, 2 coups), unités **déplacées** pour forcer la
configuration :

| distance | branche native | natif | port |
|---|---|---|---|
| 1 | `FindMeleeWeapon` → `Chain` | `1446..2169`, **3** coups | identique |
| 2 | `FindRangedWeapon` → `Bolter` (**boundary `<=`**) | `964..1446`, **2** coups | identique |
| 3 | `FindRangedWeapon` → **vide** → `null` | `0..0`, **1** coup | identique |

Les trois issues **diffèrent** par les bornes ET par le nombre de coups : aucun accord n'y est
dégénéré. Le cran du milieu garde le **sens de l'inégalité** — avec `dist < Range`, il tomberait à
`0..0`.

Face COMBAT sur le même porteur : au contact, `1910` dégâts / 3 tirages **des deux côtés** (le gate
est inerte) ; hors portée, `0` / `0` des deux côtés.

## 5. Les contre-épreuves, vues ROUGES

Deux mutations adversariales du mécanisme livré, chacune sur la garde live :

* **M1** — repli croisé restauré dans le foyer :
  `cran far : etage PREDICTION natif 0..0 (1 coups) contre port 732..1098 (2)`
* **M2** — voie SANS ARME désarmée (foyer corrigé seul) :
  `cran far : etage PREDICTION natif 0..0 (1 coups) contre port 1831..2747 (1)`

M2 est la preuve chiffrée que les **deux** crans sont nécessaires : corriger la seule sélection
d'arme donne `1831..2747` (perçage 100, 1 coup) — **pire** que l'état d'avant (`732..1098`).

Sur la garde de généralisation, M1 mord **de façon ciblée** : seul `accord d=3` tombe, `d=1` et
`d=2` restent verts —
`cran d=3 (tuile (1, 0)) : natif 0..0 (1 coups) contre port 1446..2169 (3)`.

## 6. Ce qui n'est PAS couvert

* **`rangeStatBonus` reste omis (= 0)** dans la porte. Le natif somme
  `weapon.Range + StatComponent.get_CurrentValue(<stat de portée>)` ; ce stat vaut 0 sur toutes les
  unités connues (sweep `case-184` §gaps#2). À réintroduire dès qu'une unité à stat de portée
  positif apparaît.
* **`SelectBestDamageWeapon` n'est pas porté.** Quand plusieurs armes sont éligibles, le natif
  simule la prédiction de dégât de chacune et garde la meilleure ; le port garde `_find_by_hits`
  (l'arme dont `hits` égale celui capté, sinon la première). Résidu antérieur, inchangé — et **0**
  cas du catalogue ne le distingue de la distance réelle (mesure §3 : 0 changement d'arme).
* **`GetAbilityAttackRangeType` et `HasFlag(attacker, 0x15)` ne sont pas consultés** par ce port de
  la sélection : il entre par `is_adjacent`, que l'appelant calcule. Les branches `Melee(1)` (mêlée
  **inconditionnelle**, même hors adjacence) et `ForceRangedAttack` sont donc non exercées.
  `services/battle_query.py::is_melee_attack` les porte, mais pour un **autre** consommateur.
* **La distance du port est `hexgeo.distance`**, pas le service de mouvement natif (slot 10). Elle
  concorde sur les boards mesurés (accord exact aux distances 1, 2, 3), jamais démontrée égale.
* **Le régime combat hors portée n'est pas atteignable par un cast LÉGAL** : la cascade de ciblage
  le refuse en amont (`TargetIsInRange`, `onlyAdjacent = IfNotRangedCaster`). Il est atteint ici par
  un `applyAction` direct — comme le fait `test_dead_attacker_noop_live.py` pour le gate acteur-mort.

## 7. Artefacts

| rôle | chemin |
|---|---|
| foyer corrigé | `scripts/python/engine/services/battle_query.py` |
| voie sans arme (décision) | `scripts/python/engine/playbook/prediction/normal_attack.py` |
| no-op + distance réelle (combat) | `scripts/python/engine/runner/operations/damage_ops/normal.py` |
| découplage `is_adjacent`/`dist` | `scripts/python/engine/runner/damage_model.py` |
| probe OFFLINE (rayon de souffle) | `scripts/python/probe_419r1tr14r1r1_weapon_range_gate.py` |
| probe LIVE (généralisation + combat) | `scripts/python/probe_419r1tr14r1r1_range_gate_generalisation.py` |
| garde neuve | `scripts/python/tests/engine/test_419r1tr14r1r1_range_gate_generalisation_live.py` |
| garde retournée en accord | `scripts/python/tests/engine/test_419r1tr14r1_heavy_bolt_pistol_real_carriers_live.py` |
| tranche mère | `docs/rl/case-419-r1-tr14-r1-porteurs-reels.md` §5 |
