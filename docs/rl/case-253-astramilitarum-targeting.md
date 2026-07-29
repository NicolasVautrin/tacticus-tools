# case-253 — masques de ciblage du module `astramilitarum` (1016 / 1028 / 1142 / 1143)

Les quatre abilities du module entraient dans `ABILITY_CLASSES` **sans** `TARGETING_OPTIONS` :
`get_invalid_target_reason` commence par `options = getattr(ability, "TARGETING_OPTIONS", None)` et
rend **0 immédiatement** — aucun gate. Dégradation permissive, ni erreur ni crash, invisible en
self-play. **14 casts illégaux** que `master` acceptait ont été fermés (mesure ci-dessous).

## 1. Ce que dit le décompilé

Les **quatre** sont en **forme 1 « FLAGS DIRECTS »** : la surcharge à 8 arguments de
`IdunBattle.Core.Services.TargetingOptions$$.ctor`, celle qui écrit `+0x28 <- param_5` **sans OR**.
Le littéral **EST** le masque. Ce n'est pas l'overload piégé « PRESET + flags » : le 3e argument reçu
est un `TargetingRange` de 0x18 octets recopié depuis les statiques, qui n'a pas de `+0x28`.

Ce qui les sépare, c'est le **preset de portée** — et ils sont **tous différents**
(`IdunBattle.Core.Services.TargetingRange$$.cctor`, offsets relatifs du bloc de statiques) :

| id | ctor (`TargetingOptions..ctor`) | preset | `AActiveAbility..ctor` arg 3 |
|---|---|---|---|
| 1016 | `(&opts, 0, &preset, 1, 0x4002, 0,0,0)` | `+0x00` | `1` SummonAndAttackTarget |
| 1028 | `(&opts, **1**, &preset, 1, 0x208000, 0,0,0)` | `+0x60` | `2` Others |
| 1142 | `(&opts, 0, &preset, 1, 0x10000040000040, 0,0,0)` | `+0x48` | `2` Others |
| 1143 | `(&opts, 0, &preset, 1, 0x40000422, 0,0,0)` | `+0x48` | `2` Others |

`forceMeleeTarget` = 4e argument = **1 = `RangedBool.False`** pour les quatre.
Les cinq presets de `TargetingRange$$.cctor`, relus à cette occasion (layout `{int onlyAdjacent
@+0x00 ; bool useRangeFromConfig @+0x04 ; bool useWholeBoard @+0x05 ; Nullable<int> overrideRange
@+0x08}`) :

| offset | contenu | nom du port |
|---|---|---|
| `+0x00` | `onlyAdjacent = 3 IfNotRangedCaster` | `RANGE_ADJACENT_IF_MELEE_CASTER` |
| `+0x18` | `useRangeFromConfig = true` | `RANGE_FROM_CONFIG` |
| `+0x30` | `onlyAdjacent = 0 True`, `overrideRange = 1` | `RANGE_ADJACENT` |
| `+0x48` | `useWholeBoard = true` (l'octet `+0x05` du mot `0x100`) | `RANGE_WHOLE_BOARD` |
| `+0x60` | `overrideRange = 0` | `RANGE_SELF` |

### Décomposition bit à bit — somme exacte, aucun bit résiduel

* **1016** `0x4002` = `TargetIsEnemy` (1<<14) | `TargetMatchesDynamicRule` (1<<1).
* **1028** `0x208000` = `CasterHasFreeAdjacentTile` (1<<21) | `CasterIsPossibleTarget` (1<<15).
* **1142** `0x10000040000040` = `CasterHas2TurnsLeft` (1<<52) | `AllowNullCasterTile` (1<<30) |
  `TargetIsTile` (1<<6).
* **1143** `0x40000422` = `AllowNullCasterTile` (1<<30) | `TargetIsFriendly` (1<<10) |
  `TargetHasFreeAdjacentTile` (1<<5) | `TargetMatchesDynamicRule` (1<<1).

Le décompilé et l'i2 concordent mot pour mot : *« Select a target **within 2 hexes** »* (1016, portée
d'arme de Yarrick = 2), *« Summons up to N in **free adjacent hexes** »* (1028,
`CasterHasFreeAdjacentTile`), *« **Marks a hex** on the battlefield »* (1142, `TargetIsTile`),
*« in a hex adjacent to the **targeted friendly unit** »* (1143, `TargetIsFriendly` +
`TargetHasFreeAdjacentTile`).

### Deux pièges écartés

* **1142 porte `constants.range = 2`** — mais son preset ne pose **pas** `useRangeFromConfig`, donc
  `AActiveAbility$$SetConfigValuesInTargetingOptions` ne le recopie pas. Ce `range` est celui du
  barrage de phase 2 (`MalleusRocketLauncher_AttackAbility`), **pas** du ciblage. Même piège écarté
  sur 1028 (`constants.range = 2`, consommé par le `SurroundingFriends` de la behaviour).
* **`AllowNullCasterTile` (bit 30) n'est pas une règle, c'est une PERMISSION.**
  `TargetingQuery$$GetInvalidCasterReason` refuse `broken(0x40000000)` quand `casterTiles` est vide
  et que ni ce bit ni `CasterHasNoTile` (bit 55) ne sont posés. Une MoW n'a aucune position : sans ce
  bit, **aucune** de ses abilities ne serait castable. En faire une règle refuserait tout.

## 2. Deux ports collatéraux, tous deux imposés par une MESURE

### a. La tête de domaine, élargie aux TUILES

C'est le **premier refus** de la cascade, avant toute autre règle. Verbatim de
`TargetingQuery$$GetInvalidTargetReason` (surcharge 7 arguments) :

```
if ((rules & TargetIsTile) == 0) {
    if      (rules & TargetIsMachine) { t = GetMachine(target); if (t == null) broken(TargetIsMachine) }
    else if (rules & TargetIsActor)   { t = GetUnit(target) ?? GetMachine(target);
                                        if (t == null) broken(TargetIsActor) }
    else                              { t = GetUnit(target); if (t == null) broken(TargetIsUnit) }
}
```

`t` (= `pcVar12`) est la **cible résolue** que toute la suite consomme.

`get_target_domain_broken_rule` (branches machine/unité) est arrivée par le lot `tau` pendant que ce
lot tournait ; elle était **délibérément muette sur les TUILES** (« le natif rompt, le port ne rompt
pas »). Ce lot **ferme précisément ce trou**, sur mesure : 1143 casté sur une tuile **VIDE**, le natif
rend `TargetIsUnit` (`0x200000000000`) ; casté sur la tuile d'un **allié**, il rend `0` = **VALIDE**.
Les deux verdicts sont désormais rendus. Ne reste muette que la cible que le port ne résout ni en
unité, ni en machine, ni en tuile.

Sans ce port, la raison de 1143 sur tuile vide venait de la règle dynamique, bien plus bas — refus
juste, **code faux**.

### b. `unit_of_entity` = `UnitExtensions$$GetUnit(entity, state)`

Le natif résout une **tuile en son OCCUPANT**. `_unit_of` du port répond à une autre question
(« la cible EST-elle une unité »), et reste inchangée. **Mesure** : 1143 casté sur la **tuile d'un
allié**, le natif rend `0` = VALIDE. Un port qui répondrait « pas une unité » y poserait un **faux
refus** — c'est exactement ce que faisait la première version de la règle dynamique de 1143, et la
mesure l'a attrapée.

`ForwardSpotterAbility$$GetDynamicInvalidTargetReason` est d'ailleurs porté (3 lignes de décompilé :
`if (IsUnit(target)) return caster == target; return true;`), et il reçoit la cible **déjà résolue**
— le filtre invoque la règle-délégué avec `pcVar12`, pas avec le `target` brut. Le retour est un
`TargetingRule` : le booléen s'y élargit en le littéral `1`, que le natif **réutilise** comme code de
refus (même quirk que la branche `TargetIsTile`).

## 3. Le piège d'oracle de 1142 : MUNITIONS, mesuré contrefactuellement

Au premier passage, `abilityReason` rendait `0x1 ValidRequest` sur **les 9 lignes** de 1142, et
`casterReason = 1` — alors que 1143, **portée par la même MoW**, rendait des raisons sensées.

`IdunBattle.Core.Services.AttackQuery$$GetInvalidTargetReason` (surcharge 4 arguments)
court-circuite en `broken(1)` **avant** d'entrer dans la cascade, sur trois termes :

```
aa = ActiveAbilityComponent$$GetOrNull(caster, abilityType)
if (aa == null || !ActiveAbility$$get_CanCurrentlyBeUsed(aa) || aa[+0x44] == 0) -> broken(1)
if (IsDamagedMachine(caster) && !IsMachinePrimaryAbilityType(caster, ability))  -> broken(1)
```

Ici c'est le **2e terme** : 1142 porte `munitionsCost = 1`, le seed BC partagé capture une bataille à
`BC.Player.Players[*].MachineOfWarAmmo = 0` et aucune opération native ne l'incrémente
(`case-mow-ammo-gauge.md`) → `get_CanCurrentlyBeUsed` est faux.

**Contrefactuel** (même runner, même caster, même board, même géométrie ; SEULE la BC change —
`MachineOfWarAmmo = 5` dans un seed BC patché **hors `data/`**) : `casterReason` passe de `1` à `0`
et les 9 lignes passent de `0x1` à des raisons sensées. C'est donc bien les munitions.

> **À ne pas généraliser** : « caster MoW » n'est pas la cause. 1143, même MoW, sans `munitionsCost`,
> n'a **jamais** été court-circuitée. Et `abilityState.usable` ne le voit pas — il vaut
> `CanStillBeUsed@0x28`, pas le composite `CanCurrentlyBeUsed`. Un autre lot a rencontré le même
> `0x1` avec `GetOrNull == null` pour cause : les deux causes existent, seul un contrefactuel les
> sépare. Quand aucune ne se lève, l'oracle **ensembliste** (`abilityTargets`) reste disponible : le
> probe bascule dessus automatiquement (`_ensembliste`).

## 4. Mesure

`probe_253_astramilitarum_targeting.py` — runner `--no-ai`, **les deux camps conduits** (ennemis
placés à d=1 / d=2 / d=3 de Yarrick, Creed ramené à d<=2), seed BC patché à 5 munitions.

**Deux couples board/seed : `C1_02`/777 et `C2_02`/31337. Accord natif/port `28/28` sur chacun.**

| ability | lignes | accord | casts illégaux fermés | seuil encadré |
|---|---|---|---|---|
| 1016 | 5 | 5/5 | 3 | d=2 accepté / **d=3 refusé** `TargetIsInRange` |
| 1028 | 5 | 5/5 | 4 | d=0 accepté (self-cast) / **d=1 refusé** `TargetIsInRange` |
| 1142 | 9 | 9/9 | 1 | — (`useWholeBoard` : aucun test de portée) |
| 1143 | 9 | 9/9 | 6 | — (`useWholeBoard`) |

**Contrefactuels par champ** (désaccords comptés **dans les deux sens**) :

| ability | `rules = 0` | `range = None` | `forceMeleeTarget` inversé |
|---|---|---|---|
| 1016 | 2 faux-ACCEPT | 1 faux-ACCEPT | **1 faux-REFUS** |
| 1028 | **0 — INERTE** | 4 faux-ACCEPT | **0 — INERTE** |
| 1142 | 2 faux-REFUS | **0 — INERTE** | **0 — INERTE** |
| 1143 | 3 faux-ACCEPT | **0 — INERTE** | **0 — INERTE** |

Lecture honnête de ces zéros, plutôt que de les maquiller en validation :

* **1028, `rules = 0` inerte** : son masque ne porte aucune règle du filtre CIBLE effectivement
  atteinte — `CasterIsPossibleTarget` est un flag **déclaratif** (jamais une règle de refus), et
  `CasterHasFreeAdjacentTile` est court-circuité (cf. §5). Ce qui gate 1028, c'est **la portée**, et
  `range = None` le montre : 4 faux-accepts.
* **1142 / 1143, `range` et `forceMeleeTarget` inertes** : `useWholeBoard` fait **sauter tout le
  bloc portée** du filtre statique — il n'y a rien à clamper. Les deux champs sont posés parce qu'ils
  se lisent dans la même ligne de ctor, pas parce qu'ils décident ici.
* **1016, `forceMeleeTarget` inversé = 1 faux-REFUS** : le seul contrefactuel qui produit un
  faux-**refus**. Passé à `RangedBool.True`, le clamp `ShouldApplyRangedInMelee` mord (Yarrick a un
  ennemi au contact), la portée tombe à 1 et la cible à d=2 est refusée à tort. C'est la preuve que
  la valeur **lue** (`RangedBool.False`) est bien celle qui compte.
* **1142, `rules = 0` = 2 faux-REFUS** : retirer `TargetIsTile` fait basculer l'ability en domaine
  UNITÉ, et les tuiles vides tombent alors sur le préambule `TargetIsUnit`. Le bit de domaine est
  donc bien ce qui distingue un cast tile-target.

## 5. Résidus nommés, non fermés

* **`CasterHasFreeAdjacentTile` (bit 21)** — règle du filtre statique CIBLE (slot 0x51 d'`IBattleQuery`
  sur le **caster**, juste après le même slot sur la cible pour le bit 5, avant `TargetTileIsFree`).
  Son unique porteur du registre est **1028**, qui pose aussi `isSelfCasting = 1` : casté sur
  lui-même, le natif part sur `GetCasterNotAddedReason` et la cascade CIBLE n'est jamais atteinte ;
  casté ailleurs, sa portée **nulle** refuse en amont. La règle est **inerte pour le seul porteur
  connu** — la porter serait du code non confrontable. Elle est signalée dans l'inventaire de
  `targeting.py`.
* **`CasterHas2TurnsLeft` (bit 52, porteur 1142)** — règle CASTER, gated par le slot `0x1a`
  d'`IBattleQuery` sur `(caster, 2)`, non résolu. Non portée → permissif.
* **`SendInTheNextWaveAbility$$GetDynamicInvalidTargetReason` (1016)** — non portée. Elle exige qu'il
  RESTE au moins une tuile de spawn autour de la cible : slot **0x66** d'`IBattleQuery` appelé avec
  `(target, GetSpawnedUnitRange(), 1, 1, 0, 1)`, puis `broken(2)` si le compte est < 1. Le slot 0x66
  n'a pas été résolu (aucune lambda du décorateur `RecordedSimulationRequestsBattleQuery` ne le
  donne). Le défaut d'`ActiveAbility` rend 0 — permissif, jamais un refus inventé.
* **Branches `TargetIsMachine` / `TargetIsActor` du préambule** — non portées (aucun porteur au
  registre), signalées dans l'inventaire.

## 6. Ce qui n'est PAS couvert

* Le volet CASTER n'est exercé que sur son verdict **0** : aucun des quatre masques ne porte
  `CasterHasNotMoved`, la seule règle caster portée.
* `abilityTargets` n'a servi que de **repli** — il n'a pas eu à être utilisé, l'oracle par code ayant
  tourné pour les quatre une fois les munitions patchées. Le chemin est écrit et testé
  structurellement, pas exercé.
* Les tuiles **réservées** (`Position+0x2c`) ne sont captées par aucun RPC : `tile_can_add_unit`
  reste permissif là-dessus (limitation pré-existante, pas un résidu neuf de ce lot).
