# Case 248 — `CordClaw` (1122) : même preset que la voisine, masque différent

`CordClawAbility` (1122, porteur `admecRuststalker` « Exitor-Rho », Adeptus Mechanicus) entrait dans
`ABILITY_CLASSES` **sans** `TARGETING_OPTIONS`. `get_invalid_target_reason` /
`get_invalid_caster_reason` (`engine/runner/abilities/targeting.py`) commencent par
`options = getattr(ability, "TARGETING_OPTIONS", None)` et rendent **0 immédiatement** quand c'est
`None` : aucun gate. Dégradation **permissive** — ni erreur ni crash, invisible en self-play.

## 1. La forme de ctor : **PRESET STATIQUE COPIÉ** (la 3ᵉ des trois)

`IdunBattleLogic.Entities.Abilities.Active.Loki.CordClawAbility$$.ctor` **n'appelle aucun**
`IdunBattle.Core.Services.TargetingOptions$$.ctor`. Il recopie les **0x40 octets** du champ
**statique** de `TargetingOptions` situé à l'offset **`+0x40`** du bloc `<class>+0xb8`, puis :

```
AActiveAbility..ctor(this, &opts, 0, 0)
```

Le masque **effectif** est la constante qu'écrit
`IdunBattle.Core.Services.TargetingOptions$$.cctor` à `<preset>+0x28`, soit `*(statics+0x68)` =
**`0x4000`**.

### Le preset lu en entier (pas seulement son champ `Rules`)

`TargetingOptions$$.cctor`, bloc `statics+0x40` :

| champ | offset | valeur lue | signification |
|---|---|---|---|
| `isSelfCasting` | `<preset>+0x00` = `statics+0x40` | `0` | pas de self-cast |
| `range` (`TargetingRange`) | `<preset>+0x08` = `statics+0x48` | copie de `TargetingRange statics+0x30` | **`RANGE_ADJACENT`** |
| `forceMeleeTarget` (`RangedBool`) | `<preset>+0x20` = `statics+0x60` | `1` = `RangedBool.False` | pas de clamp mêlée (la portée EST déjà l'adjacence) |
| `rules` (`TargetingRule`) | `<preset>+0x28` = `statics+0x68` | **`0x4000`** | un seul bit |
| les 2 règles-délégués | `+0x30` / `+0x38` | `0` | écrasées par `AActiveAbility$$.ctor` |

`TargetingRange$$.cctor`, bloc `statics+0x30` : `onlyAdjacent = 0 (RangedBool.True)`,
`useRangeFromConfig = false`, `useWholeBoard = false`, `overrideRange = Nullable(1)`,
`overrideRangeFunc` nul — c'est le `RANGE_ADJACENT` du port. Cohérent avec la config :
`CordClaw.constants` ne porte **aucune** clé `range` (seulement `damageProfile`, `nrOfHits`,
`nrOfHits_2`) et `attackRangeType` vaut `Melee`.

### Décomposition du masque `0x4000` (exhaustive — aucun bit résiduel)

| bit | masque | nom (`IdunBattle.Core.Services.TargetingRule`) | porté |
|---|---|---|---|
| 14 | `0x4000` | `TargetIsEnemy` | oui (`TargetingQuery$$UnitsCanAttackEachOther`) |

Un seul bit, la somme est exacte. `TargetMatchesDynamicRule` (`0x2`) est **absent** : le natif ne
consulte **aucune** règle dynamique pour cette ability, quel que soit le contenu du slot vtable
`+0x480` — c'est le bit qui arme la consultation, pas la présence d'un délégué.

## 2. Le piège : `ThunderousAssault` (1043) recopie **le même preset**

1043 lit exactement le même champ statique `TargetingOptions statics+0x40`, mais **enchaîne** sur la
surcharge « preset + flags » :

```
TargetingOptions..ctor(&opts, &preset, 0x10000000, 0)     # 1043 seulement
```

Cette surcharge recopie le preset champ par champ **sauf `Rules`**, qu'elle **combine** :
`*(dst+0x28) = flags | *(preset+0x28)` → `0x10000000 | 0x4000` = `0x10004000`. CordClaw, elle, copie
**intégralement** et s'arrête là : son masque est le preset **nu**, **sans `CasterCanMove`**.

**Même source statique, deux masques.** Ce n'est donc pas « quel preset » qui suffit à trancher, mais
**quelle forme de ctor** : une même adresse de preset peut donner deux masques selon qu'un
`TargetingOptions$$.ctor` suit ou non. Conséquence directe, et **vérifiée** en §4 : le volet CASTER
de CordClaw est vide (`casterReason` natif = 0 partout), là où 1043 porte un bit de ce volet — bit
que le port ne modélise pas et qui est resté un résidu documenté dans `case-246`.

## 3. Ce que le masque refuse

Deux volets mordent :

* **`TargetIsEnemy`** — refuse le cast sur un **allié** et sur **soi-même** ;
* **le volet PORTÉE armé par `RANGE_ADJACENT`** — `onlyAdjacent` fait prendre au filtre statique la
  branche `battleQuery.AreEntitiesAdjacent(casterTiles, target)` (et non un `dist <= N`), donc toute
  cible **hors contact** est refusée sur `TargetIsInRange`.

Le cas limite n'est donc pas une portée numérique mais **d=2** : la première distance hors adjacence.

## 4. Validation — `scripts/python/probe_248_cord_claw_targeting.py`

Oracle = le **live** : `abilityReason(casterId, abilityType, targetId)` rend le `TargetingRule`
natif. Le probe rejoue le gate offline sur le **même état figé**, en six versions : `APRÈS`, `AVANT`
(`TARGETING_OPTIONS = None`, c'est-à-dire `master`) et quatre contrefactuels par champ.

Géométrie **conduite**, jamais subie (runner `--no-ai`, les deux camps pilotés) : un ennemi au
contact, un ennemi à **d=2**, un ennemi à d=4, un allié au contact, et le caster.

| board / seed | lignes | accord natif/APRÈS | natif REFUSE alors qu'`AVANT` rendait 0 |
|---|---|---|---|
| `MC1_67` / 777 | 5 | **5/5** | **4** |
| `C4_09` / 31337 | 5 | **5/5** | **4** |

| cible | d | natif | port APRÈS | port AVANT (`master`) |
|---|---|---|---|---|
| ennemi au contact | 1 | `0x0` | `0x0` | `0x0` |
| ennemi | **2** | `0x8000000` `TargetIsInRange` | `0x8000000` | **`0x0`** |
| ennemi | 4 | `0x8000000` `TargetIsInRange` | `0x8000000` | **`0x0`** |
| le caster lui-même | 0 | `0x4000` `TargetIsEnemy` | `0x4000` | **`0x0`** |
| allié au contact | 1 | `0x4000` `TargetIsEnemy` | `0x4000` | **`0x0`** |

**4 casts illégaux sur 5 que `master` acceptait**, dont le cas limite d=2.

### Contrefactuels par champ — ce qui porte, et ce qui ne porte pas

| contrefactuel | lignes en désaccord avec le natif | lecture |
|---|---|---|
| `sansEnemy` (masque privé du bit 14) | **2/5** | faux-accepte le caster et l'allié |
| `sansRange` (`range = None`) | **2/5** | faux-accepte les deux cibles hors contact |
| `rangeDist2` (`custom_range(2)` — même portée numérique, **sans** `onlyAdjacent`) | **1/5** | faux-accepte la cible à **d=2** |
| `forceMeleeTrue` (`forceMeleeTarget` inversé) | **0/5** | **inerte** — attendu, §5 |

`rangeDist2` est le contrefactuel qui compte vraiment ici : `sansRange` prouve seulement qu'*une*
portée est lue, tandis que `rangeDist2` prouve que c'est le **régime `onlyAdjacent`** qui l'est. Sans
lui, un port qui aurait écrit `custom_range(2)` — ou `custom_range(1)`, indistinguable de
l'adjacence sur ce montage plat — passerait pour juste.

**Contre-épreuve du test de garde** (`tests/engine/runner/test_cord_claw_targeting_live.py`) : avec
la colonne `apres` forcée à l'état `master`, le test **échoue** sur son assertion de fond — 4 lignes
de désaccord.

## 5. `forceMeleeTarget` : lu, posé, **inerte** — et c'est dit

`*(statics+0x60)` vaut `1` = `RangedBool.False`, donc `RangedBoolExtensions$$IsTrue` rend `false` et
`GetRange` n'entre jamais dans la branche `Math.Min(1, v)`. Mais **même inversé** (`RangedBool.True`,
contrefactuel `forceMeleeTrue`) le champ ne déplacerait aucun verdict : la portée est **déjà**
l'adjacence, le clamp n'a rien à clamper.

Autrement dit : ce champ est **renseigné parce qu'il a été lu**, pas parce que la mesure le
discrimine. C'est un cas où la validation ne peut pas départager deux valeurs — dit explicitement
plutôt que masqué. Le test l'assertionne dans ce sens (`forceMeleeTrue == apres` sur toutes les
lignes) : si un jour cette assertion tombe, c'est que le **régime de portée** a changé, pas que le
champ était faux.

## 6. Donnée jumelle — `AbilityAttackType`

`ABILITY_ATTACK_TYPE[1122]` = `DirectTargetAttack` (**0**) était **déjà posé et juste** : c'est bien
le 3ᵉ argument de `AActiveAbility..ctor(this, &opts, 0, 0)`.
`probe_120_pre_unit_ability_fork.py` étape 0 : « littéral de ctor manquant : aucun ».

## 7. Confrontabilité du porteur

`admecRuststalker` est un **héros de lineup présent dans `rl_duel.py build --list-pool`** (rank 17).
Aucune injection de catalogue nécessaire : `--p-units admecRuststalker,admecMarshall` le déploie, et
`abilityState.usable` est vrai après 6 `endturn` — condition vérifiée par le probe avant toute
mesure, sans quoi `AttackQuery$$GetInvalidTargetReason` court-circuiterait sur `CanCurrentlyBeUsed`
et rendrait `0x1` pour la mauvaise raison.

## 8. Artefacts

* port : `scripts/python/engine/runner/abilities/loki/strike.py` (`CordClawAbility`)
* probe (MESURE) : `scripts/python/probe_248_cord_claw_targeting.py`
* test (GARDE) : `scripts/python/tests/engine/runner/test_cord_claw_targeting_live.py`
* cliquet : `scripts/python/tests/engine/runner/test_ability_registry_ratchet.py` (1122 retiré de
  `SANS_TARGETING_OPTIONS`)

## 9. Ce qui n'est PAS couvert

- **La ligne de vue** (`GetTilesObscuringTerrain`) reste non portée, et ce masque ne pose aucun bit
  `AllowObscured*`. Sans conséquence pratique ici — l'adjacence rend l'obstruction improbable — mais
  ce n'est pas *prouvé* inerte, seulement non exercé.
- **`forceMeleeTarget`** n'est pas discriminé par la mesure (§5) : sa valeur est lue au décompilé,
  pas confirmée par un verdict.
- **La face COMBAT de 1122** (attaque 4 coups + pose de l'effet 1250 `CordClaw_AdditionHits` sur le
  caster) est hors périmètre ; elle a ses propres tests
  (`test_cord_claw_live.py`, `test_additional_hits_roll_order_live.py`), rejoués verts.

## 10. La leçon transférable, complétée

`case-246` concluait « trois abilities du même fichier, trois masques sans rapport ». 1122 ajoute le
cas symétrique et plus insidieux : **deux abilities du même fichier qui lisent le MÊME preset et
n'ont pas le même masque**.

| ability | forme | ce qu'il faut lire | masque |
|---|---|---|---|
| 1014 `ArmoriumCherub` | 3 — preset copié | `*(statics+0x168)` | `0x4002` |
| 1018 `ValkyrieStrike` | 3 — preset copié | `*(statics+0x1e8)` | `0x6000040` |
| 1043 `ThunderousAssault` | 2 — preset **+ flags** | `flags \| *(statics+0x68)` | `0x10004000` |
| **1104 `SpiritLeech`** | 3 — preset copié | `*(statics+0x1a8)` | `0x4002` |
| **1122 `CordClaw`** | 3 — preset copié | `*(statics+0x68)` | `0x4000` |

Deux pièges symétriques, tous deux présents dans ce seul module :

* **même masque, presets différents** (1014 et 1104 valent `0x4002`) — et pourtant les presets
  divergent sur `forceMeleeTarget`, ce qui change le régime de portée. Lire `Rules` seul ne suffit
  pas : **les 0x40 octets entiers** comptent.
* **même preset, masques différents** (1043 et 1122 lisent `statics+0x40`) — parce que la **forme du
  ctor** diffère.

La seule méthode qui tient reste : décompiler le ctor de **cette** ability, identifier **quelle
surcharge** est appelée (ou si aucune ne l'est), puis lire le preset **entier** dans le `cctor`.
