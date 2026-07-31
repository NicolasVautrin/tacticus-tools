# case-352 — `1098 PlasmaGrenade` et `1048 FragstormGrenadeLauncher` : la base de prédiction

Résidu ouvert par #350 (PR #359). Les deux figuraient dans `_PREDICTION_DAMAGE_NOT_MINMAX_AVERAGE`
avec « corrigé = **non** » : elles retombaient sur le DÉFAUT (troncature d'une moyenne min/max),
faux sur un axe **plus profond que l'arrondi**.

Elles avaient l'air du même patron (« une borne unique »). **Elles ne le sont pas** : leurs deux
playbooks n'appellent même pas la même fonction. Chacune a été relue seule.

## 1. `1098 PlasmaGrenade`

`IdunBattle.AI.Playbook.Loki.PlasmaGrenadePlaybook$$MakeDamagePredictions` — même mold que
`StikkbombPlaybook` (#57e), relu ability par ability :

```
damage  = DSLFormulas$$Get(GetVariableForLevel(config, 0xc = minDmg, state))   // == Direct
hits    = GetNumberConstant(config, 0x2f = nrOfHits)                          // LITTERAL
profile = GetDamageProfile(config)                                            // Nullable NON vide
GenerateMultiHitAttackPredictions(caster, casterPosition, target, <Target>, damage, hits, profile, null, 0)
```

- **BASE = `minDmg` SEUL**, pas `avg(minDmg, maxDmg)`. Live lvl 50 : `minDmg` 388 / `maxDmg` 554 →
  le générique tronquait à 471, soit **+83 par coup**.
- **HITS = `nrOfHits` LITTÉRAL** : le générique passe par `GetDefaultAttackHits`, qui AJOUTE la stat
  `ExtraHits` du caster — ce playbook ne l'ajoute pas.
- PROFIL : générique (Plasma), aucun override.

Porté : `prediction/abilities.py::_plasma_grenade_inputs`.

## 2. `1048 FragstormGrenadeLauncher` — ce n'est PAS « maxDmg seul »

La lecture de #350 était **incomplète**. Le playbook n'appelle **aucun**
`GenerateMultiHitAttackPredictions` : il appelle directement la surcharge « amount » de
`IBattleQuery.GetAttackPrediction` (slot d'interface **0x24** — le générique prend le **0x28** de la
MÊME interface, `Playbook<T>+0x28`) :

```
maxDmg = GetVariableForLevel(config, 0xd = maxDmg, state)
hits   = GetNumberConstant(config, 0x2f = nrOfHits)
result = battleQuery.GetAttackPrediction(caster, target, casterPosition, Nullable(AbilityOrEffect),
                                         amount: hits * maxDmg, GetDamageProfile(config), null, default)
return new[] { new ProbableDamageEvent(target, result, null, null) }.ToList();
```

Deux lectures :

1. **la base est le PRODUIT `nrOfHits × maxDmg`** ;
2. **le nombre de coups est 1, littéral — et c'est la surcharge appelée qui le pose** :
   `IdunBattle.Core.Services.BattleQuery$$GetAttackPrediction` (forme « amount », sans paramètre
   `hits`) transmet `hits: 1` **en dur** à
   `IdunBattle.Core.Services.DamagePredictionQuery$$GetAttackPrediction`
   (forme `(caster, casterPosition, target, ability, initialDamage, hits, damageProfile,
   defenderInitialHealth, previousHitsPrediction)`).

⚠ Les noms de paramètres que ghidra affiche sur ces deux corps sont **décalés d'un cran** (le
retour est une struct de 0xa0 : le param 1 est le **retbuf**, pas `this`). L'ordre réel est
`(caster, target, casterPosition, ability, amount, damageProfileType, defenderInitialHealth,
previousHitsPrediction)` — vérifié en recoupant l'appel du générique, qui passe son `hits` en
DERNIER, après le profil.

Ce n'est donc ni la bonne **grandeur** ni la bonne **structure** : `1 × 13098` contre `6 × 1964`.
Les deux ne coïncident sur aucun axe — et surtout pas l'armure, déduite **une** fois au lieu de six.

Porté : `prediction/abilities.py::_fragstorm_grenade_launcher_inputs`.

## 3. Les DEUX volets secondaires sont MORTS — mesuré, pas supposé

Les deux playbooks portent une boucle secondaire. **Aucune ne produit jamais d'event**, et le port,
qui n'en émet aucun, est donc FIDÈLE. La cause est la même : le contexte `AbilityEntities` que le
playbook fabrique pour évaluer son sélecteur est **incomplet**.

| ability | contexte construit | sélecteur | verdict |
|---|---|---|---|
| 1098 | `AbilityEntities..ctor(entities, caster: 0, actor: 0, target: target, …)` | `…PlasmaGrenadeAbility$$GetOtherTargets` = `Enemies(caster@0x30, AdjacentUnits(Target@0x60,1,3), 1)` | dépend du **caster**, nul → vide |
| 1048 | `FUN_1802abdd0(&local_248, 0, 0x128)` = memset(0) COMPLET | `…FragstormGrenadeLauncherAbility$$GetOtherTargets` = `Damageable(SurroundingEnemies(caster@0x30, ConfigConst(0x16),1,3) − Target@0x60)` | dépend du caster ET de la cible → vide |
| **1051 (témoin)** | même forme que 1098 | `…StikkbombAbility$$GetAdjacentDamageTargets` = `AdjacentUnits(Target, unique, sel)` | ne dépend que de `Target` → **VIVANT** |

**C'est le témoin qui tranche**, et il est indispensable : sans lui, « 1 event » se lirait comme un
montage raté. Sur la **même** géométrie (2 ennemis collés à la cible ET à portée 2 du caster, sur
deux couples board/seed), le natif rend **3 events pour 1051** et **1 event pour 1098 et 1048**.
Pour 1048 le gate `result.WillBeKill` est de plus **franchi** (le natif rend `min == max == PV de la
cible`) : la boucle est bien atteinte, c'est le set qui est vide.

Corollaire d'outillage : `StikkbombPlaybook` a un `make_damage_predictions` (volet porté),
`PlasmaGrenadePlaybook` n'en a pas — et c'est **voulu**, pas un oubli. Son `CalculateCustomUtility`,
lui, reste vivant parce que son set est un appel de **service**
(`battleQuery.GetAdjacentEnemies(target, ownerId, false)`), qui reçoit cible et joueur en arguments.

Quirk lu au passage, sans effet tant que le set de 1048 est vide : dans sa boucle le natif passe
l'unité **itérée** en `caster` et garde `target` en cible, alors que son batch principal y passe le
vrai `caster`. Vérifié à l'assembleur (`r8` reçoit `IEnumerator.get_Current()`, `r9` le home slot du
4ᵉ paramètre, `rsp_entrée − 0x778`). Les arguments sont inversés côté natif.

## 4. Gate de confrontabilité — ventilée, par item

| ability | porteurs | chemin en bataille |
|---|---|---|
| 1048 | `templAggressor` [lineup] + 4 npc (`templBossAggressor*`) | **au pool** (`rl_duel build --list-pool`) → build standard |
| 1098 | `eldarSmnGuardian` [SUMMON **sans invocateur** : aucune ability du gameconfig ne le déclare] + `eldarNpc1Guardian` [npc] | catalogue injecté + trait `Summon` retiré (case-245), qui rend l'unité contrôlable |

## 5. Mesure LIVE

`probe_352_grenade_prediction_base.py`. Oracle `aiPlaybookPredict` (invocation directe de
`<X>Playbook$$MakeDamagePredictions`) contre `prediction.abilities.make_damage_predictions`, sur le
même état live. Deux versions du port à chaque montage : `apres` = le code livré ; `avant` = le même
code **l'entrée du registre retirée** (le chemin générique d'avant #352). Un montage où les deux
coïncident fait ÉCHOUER le verdict au lieu de le verdir (discipline #344).

`(healthDmgMin, healthDmgMax, appliedHits)` de l'event de la cible principale, board **MC1_67** /
seed 777, caster en (3,4) :

| montage | natif | port `apres` | port `avant` | events natif |
|---|---|---|---|---|
| 1048 `templAggressor` → `necroWarden` | `(8536, 8536, 1)` | `(8536, 8536, 1)` ✓ | `(1938, 7344, 6)` ✗ | 1 (attendu 1) |
| 1048, **cible à 400 000 PV** (survit) | `(12354, 19534, 1)` | `(12354, 19534, 1)` ✓ | `(1938, 7344, 6)` ✗ | 1 |
| 1098 `eldarSmnGuardian` lvl 50 | `(402, 606, 2)` | `(402, 606, 2)` ✓ | `(490, 734, 2)` ✗ | 1 |
| **1051 témoin** lvl 50 | `(278, 418, 2)` | `(278, 418, 2)` ✓ | `(300, 448, 2)` ✗ | **3** (attendu 3) |

Le bras « cible qui survit » est le plus discriminant : sans lui les deux bornes sont clampées aux PV
(`min == max`) et l'on ne vérifie qu'un plancher. Avec, le spread ±20 % et l'armure traversent —
`21542 − 19534 = 2008` = exactement l'armure de la cible, déduite **une** fois.
Il passe par `--unit-stat Health/RemainingHealth` et **non** `--hp-target`, qui mettrait l'armure à 0.

**Généralisation** : rejoué sur un second couple **(C1_74, seed 999, centre (3,3))** — 3/3 montages
verts, valeurs différentes (terrain/élévation), même verdict.

## 6. Ce qui n'est PAS couvert

- **`ExtraHits` > 0** : l'override `hits_override` de 1098/1051 ne diverge du générique que si le
  caster porte cette stat (les Orks en gagnent par `Waaagh`). Aucun montage ne l'a exercée : la
  branche est portée sur lecture du décompilé, comme pour `_stikkbomb_inputs` avant elle.
- **Volet secondaire de 1048 avec un set NON vide** : impossible par construction (le contexte est un
  memset(0)) — donc l'inversion caster/cible relevée au §3 reste **non confrontée live**, et le
  restera tant que le natif ne changera pas.
- **`1059 RammingSpeed`** reste le dernier « corrigé = non » de la table
  (`ExplodesAbility$$GetDamage` = `PercentageOf(StatAmount(Health), …)`, aucun min/max) — hors
  périmètre de ce cas.
- La face **COMBAT** des deux abilities n'est pas touchée (ce cas ne concerne que la prédiction de
  DÉCISION) ; `1048` n'a toujours pas de classe d'ability dans `ABILITY_CLASSES` (`kit-coverage`
  la marque NO-OP DAMAGE).

## 7. Gardes

| garde | ce qu'elle verrouille |
|---|---|
| `tests/engine/test_350_prediction_average_forms_offline.py` (5, rejouées) | la colonne « corrigé » de `_PREDICTION_DAMAGE_NOT_MINMAX_AVERAGE` doit refléter EXACTEMENT `_MAKE_DMG_INPUT_OVERRIDES` — les deux lignes passent à `True` dans le même commit que leurs handlers |
| `probe_352_grenade_prediction_base.py` | le confront live des deux bases, le bras `avant` obligatoirement discriminant, la géométrie réellement armée, et le **compte d'events attendu** (1/1/3) |
| `tests/engine/test_plasma_grenade_decision_live.py` (8, rejouées) | la face DÉCISION de 1098 (veto de somme nulle) survit au changement de base |
