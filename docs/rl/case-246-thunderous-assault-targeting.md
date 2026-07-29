# Case 246 — `ThunderousAssault` (1043) : la forme de ctor **PRESET + FLAGS**, où le littéral visible ment

`ThunderousAssaultAbility` (1043, porteur `templSwordBrother` « Sword Brother », Black Templars)
entrait dans `ABILITY_CLASSES` **sans** `TARGETING_OPTIONS`. `get_invalid_target_reason` /
`get_invalid_caster_reason` (`engine/runner/abilities/targeting.py`) commencent par
`options = getattr(ability, "TARGETING_OPTIONS", None)` et rendent **0 immédiatement** quand c'est
`None` : aucun gate. Dégradation **permissive** — ni erreur ni crash, invisible en self-play.

## 1. La forme de ctor : **PRESET + FLAGS** (la 2ᵉ des trois)

`IdunBattleLogic.Entities.Abilities.Active.Loki.ThunderousAssaultAbility$$.ctor` recopie d'abord les
**0x40 octets** du champ **statique** de `TargetingOptions` situé à l'offset **`+0x40`** du bloc
`<class>+0xb8`, puis :

```
TargetingOptions..ctor(&opts, &preset, 0x10000000, 0)     # surcharge (dst, preset, flags)
AActiveAbility..ctor(this, &opts, 0, 0)                   # 3e arg = 0 = AbilityAttackType.DirectTargetAttack
```

La surcharge `(dst, preset, flags)` de `IdunBattle.Core.Services.TargetingOptions$$.ctor` recopie le
preset **champ par champ**, à une exception près — `Rules`, qu'elle **combine** :

```c
*(ulonglong *)(param_1 + 0x28) = param_3 | uVar2;         // uVar2 = *(preset + 0x28)
```

⇒ masque **effectif** = `flags | preset.Rules` = `0x10000000 | *(statics+0x68)`. Et
`IdunBattle.Core.Services.TargetingOptions$$.cctor` écrit `*(statics+0x68) = 0x4000`.

**`0x10004000`.** Ni le littéral visible dans le ctor (`0x10000000`), ni le masque du preset
(`0x4000`) ne sont le masque : c'est leur **OU**. Un port qui aurait recopié l'un ou l'autre aurait
été faux dans les deux sens (`TargetIsEnemy` perdu d'un côté, `CasterCanMove` de l'autre).

### Le preset lu en entier (pas seulement son champ `Rules`)

`TargetingOptions$$.cctor`, bloc `statics+0x40` :

| champ | offset | valeur lue | signification |
|---|---|---|---|
| `isSelfCasting` | `<preset>+0x00` = `statics+0x40` | `0` | pas de self-cast |
| `range` (`TargetingRange`) | `<preset>+0x08` = `statics+0x48` | copie de `TargetingRange statics+0x30` | **`RANGE_ADJACENT`** |
| `forceMeleeTarget` (`RangedBool`) | `<preset>+0x20` = `statics+0x60` | `1` = **`RangedBool.False`** | pas de clamp mêlée (la portée EST déjà l'adjacence) |
| `rules` (`TargetingRule`) | `<preset>+0x28` = `statics+0x68` | `0x4000` | **OR-é** avec `0x10000000` par le ctor |
| les 2 règles-délégués | `+0x30` / `+0x38` | `0` | écrasées par `AActiveAbility$$.ctor` |

`TargetingRange$$.cctor`, bloc `statics+0x30` : `onlyAdjacent = 0` (`RangedBool.True`),
`useRangeFromConfig = false`, `useWholeBoard = false`, `overrideRange = Nullable(1)`,
`overrideRangeFunc` nul — c'est le `RANGE_ADJACENT` du port.

### Décomposition du masque `0x10004000` (exhaustive — aucun bit résiduel)

| bit | masque | nom (`IdunBattle.Core.Services.TargetingRule`) | volet | porté |
|---|---|---|---|---|
| 14 | `0x4000` | `TargetIsEnemy` | CIBLE (`UnitsCanAttackEachOther`) | **oui** |
| 28 | `0x10000000` | `CasterCanMove` | **CASTER** | non (§3) |

`0x4000 + 0x10000000 = 0x10004000` : la somme est exacte, il ne reste aucun bit non nommé.

## 2. Ce que le masque refuse, mesuré

Deux volets mordent, et il faut les deux pour que la charge soit gatée comme le natif la gate :

* **`TargetIsEnemy`** — refuse la charge sur un **allié** et sur **soi-même** ;
* **le volet PORTÉE armé par `RANGE_ADJACENT`** — `onlyAdjacent` fait prendre au filtre statique la
  branche `battleQuery.AreEntitiesAdjacent(casterTiles, target)` (et non un `dist <= N`), donc toute
  cible **hors contact** est refusée sur `TargetIsInRange`.

Contre-intuitif au premier regard pour une « charge » : ThunderousAssault **ne se déclenche que sur
une cible déjà au contact**. C'est cohérent avec son arbre de behaviour — le `PushUnit` pousse la
cible d'**un** hex et le `MoveUnit(caster, Cache(TargetTile()))` fait avancer le caster d'**un** hex
dans la tuile libérée. Ce n'est pas une charge à distance ; le déplacement est un pas.

Mesure live (`probe_246_thunderous_targeting.py`, oracle = `abilityReason`), sur deux couples
(board, seed) — `MC1_67`/777 et `C4_09`/31337, **accord 5/5 sur les deux** :

| cible | d | natif | port APRÈS | port AVANT (`master`) |
|---|---|---|---|---|
| ennemi au contact | 1 | `0x0` | `0x0` | `0x0` |
| ennemi | 2 | `0x8000000` `TargetIsInRange` | `0x8000000` | **`0x0`** |
| ennemi | 4 | `0x8000000` `TargetIsInRange` | `0x8000000` | **`0x0`** |
| le caster lui-même | 0 | `0x4000` `TargetIsEnemy` | `0x4000` | **`0x0`** |
| allié au contact | 1 | `0x4000` `TargetIsEnemy` | `0x4000` | **`0x0`** |

**4 casts illégaux sur 5 que `master` acceptait**, dont le cas limite `d = 2` (le seuil de
l'adjacence). Contrefactuels : privé de `TargetIsEnemy` le masque faux-accepte les deux lignes
« amies » ; privé de son `TargetingRange` il faux-accepte les deux lignes « hors contact » — chaque
volet porte réellement son refus, aucun n'est décoratif.

## 3. `CasterCanMove` (bit 28) : lu, situé, **non porté** — et pourquoi c'est le bon choix

Ce bit n'est **pas** une règle du filtre de cible : il vit dans
`IdunBattle.Core.Services.TargetingQuery$$GetInvalidCasterReason`, juste après la clause
`CasterHasNotMoved` :

```c
if (((options.Rules & 0x10000000) != 0) && !UnitExtensions.CanMove(caster))
    return GenericBrokenTargetingRule(0x10000000);
```

`IdunBattle.Entities.UnitExtensions$$CanMove` a **deux** volets :

1. `BaseUnitComponent.HasTrait(0x418)` — `UnitTrait.Stationary` (1048 ; à **qualifier** : `1048`
   vaut `FragstormGrenadeLauncher` en `ActiveAbilityType`, `Infiltrate` en `EffectType`,
   `GeminaeSuperia` en `TriggeredAbilityType` — c'est bien `UnitTrait` ici, l'appelé étant
   `BaseUnitComponent$$HasTrait`). Cette source **est** lue par le port
   (`engine/services/movement_query.py`, `get_movable_positions_for`) ;
2. `MovementComponent$$IsAllowedToMove` = `movementBlockers.Count == 0`, sur un dictionnaire à
   `MovementComponent+0x50` que le port **ne modélise pas** (son seul poseur du build est
   `IdunBattle.Entities.Effects.Loki.InstinctiveBehaviourBlockMovementEffect`).

Porter le seul volet `Stationary` serait un **demi-mirror invalidable** : aucun porteur de 1043 ne
peut recevoir ce trait — son unique poseur est `DutyEternalAbility` →
`AddTrait(ActiveTarget, 0x418)` sur le dreadnought invoqué, qui ne porte pas ThunderousAssault. Pas
de porteur ⇒ pas de confrontation ⇒ **résidu documenté, pas de port spéculatif**.

Le non-port est **vérifié inerte, pas supposé** : le probe et le test exigent `casterReason` natif
**= 0 sur toutes les lignes**, ce qui établit que la règle ne mord pas sur ce porteur et ne peut donc
pas créer de désaccord. Mesure complémentaire : **aucune autre ability du registre ne porte le bit
28**, donc le non-port n'a aucune portée au-delà de 1043.

**Résidu ouvert** : si un jour une ability portant le bit 28 devient confrontable avec un caster
`Stationary` ou porteur d'un `movementBlocker`, il faudra porter `CanMove` — et pour son 2ᵉ volet,
modéliser `MovementComponent.movementBlockers`.

## 4. Donnée jumelle

`ABILITY_ATTACK_TYPE[1043]` = `DirectTargetAttack` (**0**) était **déjà posé et juste** : c'est bien
le 3ᵉ argument de `AActiveAbility..ctor(this, &opts, 0, 0)`. `probe_120_pre_unit_ability_fork.py`
étape 0 : « littéral de ctor manquant : aucun », 94 abilities.

## 5. Compteurs

| | avant | après |
|---|---|---|
| `ABILITY_CLASSES` | 94 | 94 |
| avec `TARGETING_OPTIONS` | 57 | **58** |
| sans | 37 | **36** |
| dont module `strike` | 3 | **2** (restent 1104 `SpiritLeech`, 1122 `CordClaw`) |

## 6. Artefacts

* port : `scripts/python/engine/runner/abilities/loki/strike.py` (`ThunderousAssaultAbility`)
* probe (MESURE) : `scripts/python/probe_246_thunderous_targeting.py`
* test (GARDE) : `scripts/python/tests/engine/runner/test_thunderous_assault_targeting_live.py`
* cliquet : `scripts/python/tests/engine/runner/test_ability_registry_ratchet.py` (1043 retiré de
  `SANS_TARGETING_OPTIONS`)

## 7. La leçon transférable

Les trois formes de ctor ne se distinguent **pas** au nom de l'ability ni à sa mécanique, et le
module `loki/strike.py` les porte **toutes les trois** :

| ability | forme | ce qu'il faut lire | masque |
|---|---|---|---|
| 1014 `ArmoriumCherub` | 3 — preset copié, aucun ctor | `*(statics+0x168)` | `0x4002` |
| 1018 `ValkyrieStrike` | 3 — preset copié, aucun ctor | `*(statics+0x1e8)` | `0x6000040` |
| **1043 `ThunderousAssault`** | **2 — preset + flags** | `flags \| *(statics+0x68)` | `0x10004000` |

Trois abilities du **même fichier**, trois masques sans rapport, et pour la troisième le littéral
visible dans le ctor n'est **pas** le masque. La seule méthode qui tient : **décompiler le ctor de
CETTE ability**, identifier **quelle surcharge** de `TargetingOptions$$.ctor` est appelée (ou si
aucune ne l'est), puis lire le preset **dans le `cctor`**. Jamais généraliser depuis la voisine.
