# Case 247 — `SpiritLeech` (1104) : deux presets qui ne diffèrent que par un champ

`SpiritLeechAbility` (1104, porteur `tyranNeurothrope` « Neurothrope », Tyranids) entrait dans
`ABILITY_CLASSES` **sans** `TARGETING_OPTIONS`. `get_invalid_target_reason` /
`get_invalid_caster_reason` (`engine/runner/abilities/targeting.py`) commencent par
`options = getattr(ability, "TARGETING_OPTIONS", None)` et rendent **0 immédiatement** quand c'est
`None` : aucun gate. Dégradation **permissive** — ni erreur ni crash, invisible en self-play.

## 1. La forme de ctor : **PRESET STATIQUE COPIÉ** (la 3ᵉ des trois)

`IdunBattleLogic.Entities.Abilities.Active.Loki.SpiritLeechAbility$$.ctor` **n'appelle aucun**
`IdunBattle.Core.Services.TargetingOptions$$.ctor`. Il recopie les **0x40 octets** du champ
**statique** de `TargetingOptions` situé à l'offset **`+0x180`** du bloc `<class>+0xb8`, puis :

```
AActiveAbility..ctor(this, &opts, 0, 0)
```

Aucun littéral de masque n'est visible dans le ctor. Le masque **effectif** est la constante
qu'écrit `IdunBattle.Core.Services.TargetingOptions$$.cctor` à `<preset>+0x28`, soit
`*(statics+0x1a8)` = **`0x4002`**.

### Le preset lu en entier (pas seulement son champ `Rules`)

`TargetingOptions$$.cctor`, bloc `statics+0x180` :

| champ | offset | valeur lue | signification |
|---|---|---|---|
| `isSelfCasting` | `<preset>+0x00` = `statics+0x180` | `0` | pas de self-cast |
| `range` (`TargetingRange`) | `<preset>+0x08` = `statics+0x188` | copie de `TargetingRange statics+0x18` | **`useRangeFromConfig`** |
| `forceMeleeTarget` (`RangedBool`) | `<preset>+0x20` = `statics+0x1a0` | **`1`** = `RangedBool.False` | **pas** de clamp mêlée |
| `rules` (`TargetingRule`) | `<preset>+0x28` = `statics+0x1a8` | **`0x4002`** | les deux bits ci-dessous |
| les 2 règles-délégués | `+0x30` / `+0x38` | `0` | écrasées par `AActiveAbility$$.ctor` |

`TargetingRange$$.cctor`, bloc `statics+0x18` : `onlyAdjacent = 1 (RangedBool.False)`,
`useRangeFromConfig = **true**`, `useWholeBoard = false`, `overrideRange` vide, `overrideRangeFunc`
nul — c'est le `RANGE_FROM_CONFIG` du port. `AActiveAbility$$SetConfigValuesInTargetingOptions` y
pose ensuite `OverrideRange = GetNumberConstant(0x16 range)` = `SpiritLeech.constants.range` = **3**.
Les 5 statiques `TargetingRange` ont été relues à cette occasion et **confirment ligne par ligne** la
table du port (`+0x00` adjacent-si-mêlée, `+0x18` from-config, `+0x30` adjacent, `+0x48` whole-board,
`+0x60` self).

### Décomposition du masque `0x4002` (exhaustive — aucun bit résiduel)

| bit | masque | nom (`IdunBattle.Core.Services.TargetingRule`) | porté |
|---|---|---|---|
| 1 | `0x2` | `TargetMatchesDynamicRule` | oui (point d'extension), mais **inerte** — §3 |
| 14 | `0x4000` | `TargetIsEnemy` | oui (`TargetingQuery$$UnitsCanAttackEachOther`) |

`0x2 + 0x4000 = 0x4002` : la somme est exacte, il ne reste aucun bit non nommé.

## 2. La voisine ment — et c'est **un seul champ** qui la trahit

`ArmoriumCherub` (1014) est dans le **même fichier**, de la **même forme** de ctor, avec le **même
masque `0x4002`** et le **même `RANGE_FROM_CONFIG`**. Son preset est `+0x140`, et la seule
différence avec `+0x180` est :

| | `statics+0x140` (1014) | `statics+0x180` (1104) |
|---|---|---|
| `forceMeleeTarget` | `*(statics+0x160)` = **0** = `RangedBool.True` | `*(statics+0x1a0)` = **1** = `RangedBool.False` |

Ce champ n'est pas décoratif : `TargetingQuery$$GetRange` lit
`RangedBoolExtensions.IsTrue(options.ForceMeleeTarget, caster) && attackQuery.ShouldApplyRangedInMelee(...)`
et, si c'est vrai, fait `v = Math.Min(1, v); onlyAdjacent = true`. Autrement dit : **Vindicta clampe
à 1 dès qu'un ennemi est à son contact ; le Neurothrope garde ses 3 hexes.** Copier le préset du
voisin — geste naturel devant deux abilities « du même patron » — aurait produit un gate qui refuse
des drains parfaitement légaux dès qu'une mêlée s'engage.

C'est **mesuré**, pas argumenté : le contrefactuel `forceMeleeTrue` du probe rejoue exactement le
preset de 1014 et **faux-refuse** la cible à d=3 que le natif accepte (§4).

## 3. `TargetMatchesDynamicRule` (bit 1) : posé, lu, **inerte** — et vérifié tel

Le filtre statique n'invoque la règle-délégué `options+0x38` (slot vtable `+0x480`) que sous ce bit.
La classe native ne fournit **aucun** corps `SpiritLeechAbility$$GetDynamicInvalidTargetReason` : ses
seuls corps sont `$$.ctor`, `$$ExecuteBehaviour`, `$$GetAttackDamage`, `$$GetHealTargets`,
`$$GetHealAmountForExecution`, `$$GetHealAmountForPrediction`, `$$GetHealAmountFromDamageAmount` et
`$$GetSuppressCondition`. Le slot retombe donc sur le défaut `AActiveAbility` (= 0), et côté port sur
`ActiveAbility.get_dynamic_invalid_target_reason` (défaut 0 également).

L'argument par absence de symbole ne suffirait pas seul (les corps triviaux sont dédupliqués), donc
le probe **le mesure** : le contrefactuel `sansDynamic` (masque privé du bit 1) ne déplace **aucun**
verdict sur les deux montages, alors que l'oracle natif, lui, consulte bel et bien le délégué. Si un
refus dynamique existait, il apparaîtrait comme un désaccord natif/port — il n'y en a aucun.

## 4. Validation — `scripts/python/probe_247_spirit_leech_targeting.py`

Oracle = le **live** : `abilityReason(casterId, abilityType, targetId)` rend le `TargetingRule`
natif. Le probe rejoue le gate offline sur le **même état figé**, en six versions : `APRÈS`
(l'ability du registre), `AVANT` (`TARGETING_OPTIONS = None`, c'est-à-dire `master`), et quatre
contrefactuels par champ.

Géométrie **conduite**, jamais subie (runner `--no-ai`, les deux camps pilotés) : un ennemi au
**contact** — indispensable, sans lui `ShouldApplyRangedInMelee` est faux et le contrefactuel
`forceMeleeTrue` serait un no-op qui ne prouverait rien —, un ennemi au **seuil** d=3, un ennemi à
**d=4**, un allié à portée, et le caster.

| board / seed | lignes | accord natif/APRÈS | natif REFUSE alors qu'`AVANT` rendait 0 |
|---|---|---|---|
| `MC1_67` / 777 | 5 | **5/5** | **3** |
| `C4_09` / 31337 | 5 | **5/5** | **3** |

Table `C4_09`/31337 (identique en structure sur `MC1_67`/777, où l'ennemi lointain tombait à d=5) :

| cible | d | natif | port APRÈS | port AVANT (`master`) |
|---|---|---|---|---|
| ennemi au contact | 1 | `0x0` | `0x0` | `0x0` |
| ennemi au **seuil** | 3 | `0x0` | `0x0` | `0x0` |
| ennemi | 4 | `0x8000000` `TargetIsInRange` | `0x8000000` | **`0x0`** |
| le caster lui-même | 0 | `0x4000` `TargetIsEnemy` | `0x4000` | **`0x0`** |
| allié | 1 | `0x4000` `TargetIsEnemy` | `0x4000` | **`0x0`** |

**3 casts illégaux sur 5 que `master` acceptait**, et le seuil de portée est **encadré des deux
côtés** (d=3 accepté / d=4 refusé) : une portée fausse de ±1 ne passerait pas.

### Contrefactuels par champ — ce qui porte, et ce qui ne porte pas

| contrefactuel | lignes en désaccord avec le natif | lecture |
|---|---|---|
| `sansEnemy` (masque privé du bit 14) | **2/5** | faux-accepte le caster et l'allié |
| `sansRange` (`range = None`) | **1/5** | faux-accepte l'ennemi hors portée |
| `forceMeleeTrue` (le champ du preset **voisin** 1014) | **1/5** | **faux-refuse** l'ennemi à d=3 |
| `sansDynamic` (masque privé du bit 1) | **0/5** | bit **inerte** — attendu, et c'est un résultat |

Le seul champ dont la neutralisation ne change rien est `TargetMatchesDynamicRule`, et §3 dit
pourquoi. Les trois autres sont chacun **porteurs d'un refus** que le natif prononce.

**Contre-épreuve du test de garde** (`tests/engine/runner/test_spirit_leech_targeting_live.py`) :
avec la colonne `apres` forcée à l'état `master`, le test **échoue** sur son assertion de fond —
3 lignes de désaccord (`0x8000000`, `0x4000`, `0x4000` contre `0x0`).

## 5. Donnée jumelle — `AbilityAttackType`

`ABILITY_ATTACK_TYPE[1104]` = `DirectTargetAttack` (**0**) était **déjà posé et juste** : c'est bien
le 3ᵉ argument de `AActiveAbility..ctor(this, &opts, 0, 0)` (`AActiveAbility$$.ctor` l'écrit en
`*(undefined4 *)(param_1 + 0xd) = param_3`). `probe_120_pre_unit_ability_fork.py` étape 0 :
« littéral de ctor manquant : aucun », 94 abilities.

## 6. Confrontabilité du porteur

`tyranNeurothrope` est un **héros de lineup présent dans `rl_duel.py build --list-pool`** (rank 17,
97 unités régulières). Aucune injection de catalogue n'a été nécessaire : `--p-units
tyranNeurothrope,tyranTyrantGuard` le déploie directement, et son `abilityState.usable` est vrai
après 6 `endturn` (purge de `initialCooldownTurns`) — condition sans laquelle
`AttackQuery$$GetInvalidTargetReason` court-circuiterait sur `CanCurrentlyBeUsed` et rendrait `0x1`
pour la mauvaise raison. Le probe le vérifie avant de mesurer quoi que ce soit.

## 7. Compteurs

| | avant | après |
|---|---|---|
| `ABILITY_CLASSES` | 94 | 94 |
| avec `TARGETING_OPTIONS` | 58 | **60** (avec 1122, cf. case-248) |
| sans | 36 | **34** |
| dont module `strike` | 2 | **0** — le module est **soldé** |

## 8. Artefacts

* port : `scripts/python/engine/runner/abilities/loki/strike.py` (`SpiritLeechAbility`)
* probe (MESURE) : `scripts/python/probe_247_spirit_leech_targeting.py`
* test (GARDE) : `scripts/python/tests/engine/runner/test_spirit_leech_targeting_live.py`
* cliquet : `scripts/python/tests/engine/runner/test_ability_registry_ratchet.py` (1104 retiré de
  `SANS_TARGETING_OPTIONS`)

## 9. Ce qui n'est PAS couvert

- **La ligne de vue** (`GetTilesObscuringTerrain`) reste non portée dans le gate générique, et ce
  masque ne pose aucun bit `AllowObscured*` : une cible **obscurcie** que le natif refuserait serait
  acceptée offline. Aucune des lignes mesurées ne l'exerce (les deux montages ont vue dégagée), donc
  c'est un résidu **ouvert**, pas un résidu observé.
- **`TargetIsSummon` / `TargetIsHero` / `TargetIsNotAnObject`** ne sont pas dans ce masque : rien à
  porter ici, mais rien n'a été vérifié non plus sur des cibles de ces natures.
- **Le régime `forceMeleeTarget = RangedBool.True`** n'est exercé que par le *contrefactuel* — la
  branche `ShouldApplyRangedInMelee` du port est donc confrontée au natif **indirectement** (par le
  fait que le natif ne clampe pas), pas par un porteur qui la déclenche vraiment. Le cas dédié reste
  1014 (`case-1014` / `case-241`).
- **La face COMBAT de 1104** (dégât conditionnel `GetAttackDamage`, lifesteal, pose de `Pinned`) est
  hors périmètre : ce cas ne traite que le gate de **ciblage** du cast.
