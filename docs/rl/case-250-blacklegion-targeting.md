# Case 250 — module `blacklegion` soldé : les cinq masques de ciblage, et les deux MoW du même porteur

Cinq abilities Black Legion entraient dans `ABILITY_CLASSES` **sans** `TARGETING_OPTIONS`.
`get_invalid_target_reason` / `get_invalid_caster_reason`
(`engine/runner/abilities/targeting.py`) commencent par
`options = getattr(ability, "TARGETING_OPTIONS", None)` et rendent **0 immédiatement** quand c'est
`None` : aucun gate. Dégradation **permissive** — ni erreur ni crash, invisible en self-play.

| id | ability | porteur | forme de ctor | `rules` | `TargetingRange` | `forceMeleeTarget` | `AbilityAttackType` |
|---|---|---|---|---|---|---|---|
| 1021 | `Incursion` | `blackPossession` (héros) | **1 — flags directs** | `0x4020` | `RANGE_FROM_CONFIG` (2) | `2` `IfRangedCaster` | `1` SummonAndAttackTarget |
| 1022 | `BringerOfDespair` | `blackTerminator` (héros) | **3 — preset `+0x40`** | `0x4000` | `RANGE_ADJACENT` | `1` `False` | `0` DirectTargetAttack |
| 1036 | `FrenziedFiring` | `blackObliterator` (héros) | **3 — preset `+0x140`** | `0x4002` | `RANGE_FROM_CONFIG` (3) | `0` **`True`** | `0` DirectTargetAttack |
| 1147 | `HadesAutocannons` | `blackForgefiend` (**MoW**) | **1 — flags directs** | `0x46006000` | `RANGE_WHOLE_BOARD` | `1` `False` | `0` DirectTargetAttack |
| 1148 | `DaemonicOrdnance` | `blackForgefiend` (**MoW**) | **1 — flags directs** | `0x46000040` | `RANGE_WHOLE_BOARD` | `1` `False` | `0` DirectTargetAttack |

Les cinq littéraux `AbilityAttackType` (3ᵉ argument de `AActiveAbility..ctor`) étaient **déjà posés
et justes** — y compris `1036`, dont l'antécédent (`d2be96e`, littéral omis à l'entrée au registre)
avait été rattrapé depuis. Aucune divergence à signaler.

## 1. Ce qui a été lu, ctor par ctor

### 1021 `Incursion` — flags directs

```
IdunBattleLogic.Entities.Abilities.Active.Loki.IncursionAbility$$.ctor
    opts = {0}
    TargetingOptions..ctor(&opts, isSelfCasting=0, range=&<TargetingRange statics+0x18>,
                           forceMeleeTarget=2, rules=0x4020, 0, 0, 0)
    AActiveAbility..ctor(this, &opts, 1, 0)
```

| bit | masque | nom (`IdunBattle.Core.Services.TargetingRule`) | porté |
|---|---|---|---|
| 5 | `0x20` | `TargetHasFreeAdjacentTile` | oui |
| 14 | `0x4000` | `TargetIsEnemy` | oui |

Somme exacte, aucun bit résiduel. `TargetHasFreeAdjacentTile` est le pendant DÉCISION exact du
`CanAddUnit(AdjacentTiles(Target()))` de
`IdunBattleLogic.Entities.Abilities.Active.Loki.IncursionAbility$$GetNextSpawnTile` : sans tuile
libre autour de la cible, la chaîne de spawns n'aurait rien à poser.

`TargetingRange$$.cctor`, bloc `statics+0x18` : `onlyAdjacent = 1 (RangedBool.False)`,
`useRangeFromConfig = true`, `useWholeBoard = false`, `overrideRange` nul → `RANGE_FROM_CONFIG`, donc
`AActiveAbility$$SetConfigValuesInTargetingOptions` pose `overrideRange = constants.range` = **2**.

### 1022 `BringerOfDespair` — preset statique copié

Aucun `TargetingOptions..ctor` : recopie des 0x40 octets de `TargetingOptions statics+0x40`, puis
`AActiveAbility..ctor(this, &opts, 0, 0)`. Le preset lu **en entier** dans
`IdunBattle.Core.Services.TargetingOptions$$.cctor` :

| champ | offset | valeur |
|---|---|---|
| `isSelfCasting` | `statics+0x40` | `0` |
| `range` | `statics+0x48` | copie de `TargetingRange statics+0x30` = `RANGE_ADJACENT` |
| `forceMeleeTarget` | `statics+0x60` | `1` = `RangedBool.False` |
| `rules` | `statics+0x68` | **`0x4000`** = `TargetIsEnemy` seul |

`TargetMatchesDynamicRule` (`0x2`) est **absent** : aucune règle dynamique consultée.

### 1036 `FrenziedFiring` — preset statique copié, l'autre preset

Recopie de `TargetingOptions statics+0x140` :

| champ | offset | valeur |
|---|---|---|
| `isSelfCasting` | `statics+0x140` | `0` |
| `range` | `statics+0x148` | copie de `TargetingRange statics+0x18` = `RANGE_FROM_CONFIG` (`constants.range` = 3) |
| `forceMeleeTarget` | `statics+0x160` | **`0` = `RangedBool.True`** |
| `rules` | `statics+0x168` | `0x4002` = `TargetMatchesDynamicRule` \| `TargetIsEnemy` |

Le bit `0x2` est **inerte** : 1036 ne surcharge pas `GetDynamicInvalidTargetReason`, donc le défaut
`0` de `ActiveAbility.get_dynamic_invalid_target_reason` est le mirror exact. Mesuré (§4,
contrefactuel `sansDynamic` : 0 verdict déplacé).

### 1147 / 1148 — deux abilities du MÊME porteur, deux masques sans rapport

```
HadesAutocannonsAbility$$.ctor : TargetingOptions..ctor(&opts, 0, &<TargetingRange statics+0x48>,
                                                        1, 0x46006000, 0, 0, 0)
DaemonicOrdnanceAbility$$.ctor : TargetingOptions..ctor(&opts, 0, &<TargetingRange statics+0x48>,
                                                        1, 0x46000040, 0, 0, 0)
```

| bit | masque | nom | 1147 | 1148 | porté |
|---|---|---|---|---|---|
| 6 | `0x40` | `TargetIsTile` | — | ✔ | oui |
| 13 | `0x2000` | `TargetIsSummon` | ✔ | — | **oui (porté par ce case)** |
| 14 | `0x4000` | `TargetIsEnemy` | ✔ | — | oui |
| 25 | `0x2000000` | `AllowObscuredTargetByElevation` | ✔ | ✔ | désarmement (LoS non portée) |
| 26 | `0x4000000` | `AllowObscuredTargetByWalls` | ✔ | ✔ | idem |
| 30 | `0x40000000` | `AllowNullCasterTile` | ✔ | ✔ | volet caster, non porté |

Sommes exactes (`0x2000+0x4000+0x6000000+0x40000000` et `0x40+0x6000000+0x40000000`), aucun bit
résiduel. `TargetingRange statics+0x48` = `useWholeBoard = true` → **aucun** test de portée : la
constante `HadesAutocannons.constants.range` (2) n'est **pas** la portée de ciblage, elle n'alimente
que le disque `SurroundingUnits` de
`IdunBattleLogic.Entities.Abilities.Active.Loki.HadesAutocannonsAbility$$GetAllTargets`.

1148 ne porte **aucune** règle de camp : le natif accepte une tuile des deux camps. C'est cohérent
avec son `ExecuteBehaviour`, qui embrase la zone puis ne frappe que les ennemis déjà en feu — le
filtre de camp est un filtre d'**exécution**, pas de ciblage.

## 2. Règle nouvellement portée : `TargetIsSummon` (bit 13)

Lu VERBATIM dans `IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason` (surcharge 7
arguments), juste après le bloc portée / ligne de vue :

```c
if (((param_5[5] & 0x2000) != 0) &&
   (cVar6 = IdunBattle_Entities_UnitExtensions__HasTrait(pcVar12, 2, 0), cVar6 == '\0')) {
  lVar8 = 0x2000;   /* TargetIsSummon */
  goto LAB_1810bbd10;
}
```

Position native : **première** règle du bloc TRAITS (`TargetIsSummon` → `TargetIsHero` bit 50 →
`TargetIsNotAnObject` bit 33 → `TargetIsHealable` → `TargetIsRepairable`), donc **après** la portée
et **avant** `TargetHasFreeAdjacentTile`. La mesure confirme la place : sur un ennemi non-summon le
natif rend `0x2000` alors que `TargetIsEnemy` (`0x4000`, testé plus tôt) est déjà passé.

1147 est le **seul** porteur du bit dans tout le registre (vérifié par balayage
`ABILITY_CLASSES × TARGETING_OPTIONS`) : le port de la règle est strictement scopé. Sans elle, le
masque de 1147 aurait été posé sans sa règle principale — mesuré : le natif refusait `0x2000` là où
le port rendait `0x0`, sur 4 lignes sur 8.

## 3. Confrontabilité des porteurs

Les cinq sont **dans le pool** (`rl_duel.py build --list-pool`) : `blackPossession`,
`blackTerminator`, `blackObliterator` en héros, `blackForgefiend` parmi les 8 MoW spawnables. Aucune
injection de catalogue nécessaire.

## 4. Validation — `scripts/python/probe_250_blacklegion_targeting.py`

Oracle = le **live** : `abilityReason(casterId, abilityType, targetId)` →
`IdunBattle.Core.Services.AttackQuery$$GetInvalidTargetReason` → la cascade
`TargetingQuery$$GetInvalidTargetReason`. Le probe rejoue le gate offline sur le **même état figé**,
en N versions : `apres`, `avant` (`TARGETING_OPTIONS = None`, l'état de `master`) et un contrefactuel
par champ. Géométrie **conduite** (`--no-ai`, les deux camps pilotés), jamais subie.

### Deux géométries, et elles ne prouvent pas la même chose

`forceMeleeTarget` n'est **lisible** que quand un ennemi est au contact du caster
(`TargetingQuery$$GetRange` n'entre dans `Math.Min(1, v)` que sous
`AttackQuery$$ShouldApplyRangedInMelee`) ; inversement, la valeur numérique de la portée n'est
lisible que quand ce clamp **n'est pas** armé. Les deux couples board/seed portent donc chacun un
discriminant distinct — au lieu de rejouer deux fois la même preuve.

| id | couple | géométrie | lignes | accord natif/`apres` | natif REFUSE alors qu'`avant` rendait 0 |
|---|---|---|---|---|---|
| 1021 | `MC1_67` / 777 | `far` (ennemis à 2, 3, 4) | 5 | **5/5** | **4** |
| 1021 | `C4_09` / 31337 | `near` (ennemis à 1, 2, 4) | 5 | **5/5** | **4** |
| 1022 | `MC1_67` / 777 | `far` (1, 2, 4) | 5 | **5/5** | **4** |
| 1022 | `C4_09` / 31337 | `near` (1, 2, 3) | 5 | **5/5** | **4** |
| 1036 | `MC1_67` / 777 | `far` (2, 3, 5) | 5 | **5/5** | **3** |
| 1036 | `C4_09` / 31337 | `near` (1, 3, 5) | 5 | **5/5** | **4** |
| 1147 | `MC1_67` / 777 | MoW + 3 summons ennemis | 8 | **8/8** | **8** |
| 1148 | `MC1_67` / 777 | MoW + tuiles marchables / non | 7 | **7/7** | **1** |

**Total : 32 casts illégaux que `master` acceptait**, dont plusieurs au seuil exact.

### Les deux seuils qui comptent

`Incursion` porte à 2 **hors contact**, à 1 **au contact** :

| couple | cible | d | natif | port `apres` | port `avant` |
|---|---|---|---|---|---|
| `far` | ennemi | **2** | `0x0` | `0x0` | `0x0` |
| `far` | ennemi | 3 | `0x8000000` `TargetIsInRange` | idem | **`0x0`** |
| `near` (un ennemi à d=1) | ennemi | **2** | `0x8000000` `TargetIsInRange` | idem | **`0x0`** |

La **même distance 2** est légale dans un cas et illégale dans l'autre : c'est le clamp
`RangedBool.IfRangedCaster`, armé parce que `blackPossession` porte une arme à `Range` 2. Idem pour
`FrenziedFiring` entre d=3 (`far`, accepté) et d=3 (`near`, refusé).

### Contrefactuels par champ

| id | contrefactuel | `far` | `near` | lecture |
|---|---|---|---|---|
| 1021 | `sansEnemy` | **2/5** | **2/5** | faux-accepte le caster et l'allié |
| 1021 | `sansRange` | **2/5** | **2/5** | faux-accepte tout ce qui est hors portée |
| 1021 | `rangeAdjacent` | **1/5** | 0/5 | faux-refuse d=2 — mais seulement hors clamp |
| 1021 | `forceMeleeFalse` | 0/5 | **1/5** | faux-accepte d=2 sous clamp — **la seule lecture qui prouve `IfRangedCaster`** |
| 1021 | `sansFreeAdj` | 0/5 | 0/5 | **inerte** — terrain dégagé, aucune cible encerclée |
| 1022 | `sansEnemy` | **2/5** | **2/5** | caster + allié |
| 1022 | `sansRange` | **2/5** | **2/5** | tout le hors-contact |
| 1022 | `rangeDist2` | **1/5** | **1/5** | même portée numérique **sans** `onlyAdjacent` → faux-accepte d=2 : c'est le **régime** qui est verrouillé, pas « une portée » |
| 1022 | `forceMeleeTrue` | 0/5 | 0/5 | **inerte** — la portée EST déjà l'adjacence |
| 1036 | `sansEnemy` | **2/5** | **2/5** | caster + allié |
| 1036 | `sansRange` | **1/5** | **2/5** | hors portée |
| 1036 | `range2` | **1/5** | 0/5 | faux-refuse d=3 hors clamp → verrouille `constants.range` = 3 |
| 1036 | `forceMeleeFalse` | 0/5 | **1/5** | faux-accepte d=3 sous clamp — **c'est exactement ce qu'on obtiendrait en recopiant le preset de 1104 `SpiritLeech`** |
| 1036 | `sansDynamic` | 0/5 | 0/5 | **inerte** — pas de règle dynamique native |
| 1147 | `sansSummon` | **4/8** | — | faux-accepte les 4 non-summons |
| 1147 | `sansEnemy` | **1/8** | — | faux-accepte l'allié |
| 1147 | `sansRange` / `rangeDist1` | 0/8 | — | **inertes**, §6 |
| 1148 | `sansTile` | **1/7** | — | faux-accepte la tuile non marchable |
| 1148 | `allowUnwalkable` | **1/7** | — | l'échappatoire que le masque n'a **pas** |
| 1148 | `sansRange` / `rangeDist1` | 0/7 | — | **inertes**, §6 |

## 5. L'oracle sur un caster MACHINE OF WAR — deux conditions, et un contre-oracle

`AttackQuery$$GetInvalidTargetReason` **court-circuite** avant la cascade et rend le littéral `1`
(`TargetingRule.ValidRequest`) si `ActiveAbilityComponent.GetOrNull(...) == null`, si
`ActiveAbility.get_CanCurrentlyBeUsed` est faux, ou si `*(activeAbility+0x44) == 0`. Un `0x1` ne dit
donc **rien** du masque : il dit que l'oracle n'a pas tourné.

Deux conditions le rendent valide pour un caster MoW, et le probe les tient :

1. **le seed BC est patché** — `Player.Players[].MachineOfWarAmmo` vaut **0** dans `data/seed-bc.json`
   et aucune opération native ne l'incrémente (le stock vit dans
   `IdunBattle.Entities.Components.PlayerComponent+0x6c`, posé une seule fois par
   `IdunBattle.Operations.AddPlayerOperation$$Execute`). Sans munitions,
   `get_CanCurrentlyBeUsed` est faux. `probe_250.seed_bc_with_ammo()` écrit un seed patché **sous
   `logs/`** (jamais dans `data/`, versionné) et le passe à `rl_duel build --seed-bc` ;
2. **le `casterId` est celui de `decisionView.mows[].casterId`**, la clé que pose
   `snapshot._load_machines` — **pas** `observeBattle.mows[].id`, qui est un id d'entité natif
   distinct. Avec le mauvais id, l'oracle ne résout pas le caster et rend `casterReason` /
   `targetReason` **nuls** (mesuré : 0/4, tout à `None`), ce qui se lit à tort comme « oracle muet ».

Ces deux conditions réunies, l'oracle **tourne** : sur 1147 il rend `0x2000` / `0x4000` / `0x0` selon
la ligne, et le **contre-oracle ensembliste** `abilityTargets.fromHere`
(`AttackQuery$$GetValidTargets`, chemin natif distinct) donne **exactement le même ensemble**
`[128, 134, 140]` que `abilityReason == 0` — et que le port. Les deux oracles natifs sont d'accord.

**Limite du contre-oracle, mesurée** : sur 1148 (tile-targeting), `abilityTargets.fromHere` est
**vide** alors que `abilityReason` accepte six cibles. Cause : `fromHere` construit une
`UnitPosition` depuis `GetTiles(caster)`, et une MoW **n'a aucune tuile**. C'est le contre-oracle qui
est aveugle ici, pas `abilityReason`. Ne pas inverser la conclusion.

## 6. Ce que la portée ne peut PAS prouver sur une MoW — et c'est dit

Pour 1147 et 1148, les deux contrefactuels de portée (`sansRange`, `rangeDist1`) sont **inertes**,
pour **deux raisons indépendantes** qui se recouvrent :

* `RANGE_WHOLE_BOARD` (`useWholeBoard = true`) fait court-circuiter `TargetingQuery$$GetRange` ;
* le caster MoW n'a **aucune** `PositionComponent` → `_tile_of` rend `None` → `get_range` rend `None`
  quelle que soit la valeur du champ.

Le champ `range` de ces deux masques est donc **renseigné parce qu'il a été lu**, pas parce que la
mesure le discrimine. Dit explicitement plutôt que masqué. Même statut pour `forceMeleeTarget` sur
1022 (§4) : lu, posé, inerte — la portée y est déjà l'adjacence.

## 7. Comment la géométrie summon a été montée (1147)

`TargetIsSummon` n'a de cible acceptable que si un **summon ennemi** existe. Le montage l'AMÈNE : le
`blackPossession` **adverse** caste `Incursion` (1021) sur une unité de mon camp, et ses
`blackSmnBloodletter` apparaissent **dans son camp** (`project_summon_team_model`) — donc des summons
ennemis pour la MoW. Trois sont apparus, tous acceptés par le natif **et** par le port.

C'est un montage auto-référent utile : l'ability 1021 de ce même lot sert d'instrument pour valider
1147.

## 8. Artefacts

* port : `scripts/python/engine/runner/abilities/blacklegion.py` (les 5 `TARGETING_OPTIONS`)
* règle `TargetIsSummon` : `scripts/python/engine/runner/abilities/targeting.py`
* probe (MESURE) : `scripts/python/probe_250_blacklegion_targeting.py`
* test (GARDE) : `scripts/python/tests/engine/runner/test_blacklegion_targeting_live.py`
* cliquet : `scripts/python/tests/engine/runner/test_ability_registry_ratchet.py`
  (1021/1022/1036/1147/1148 retirés de `SANS_TARGETING_OPTIONS` ; 94 au registre, **76** avec masque,
  **18** sans)

## 9. Ce qui n'est PAS couvert

* **La ligne de vue** (`TargetingQuery$$GetTilesObscuringTerrain`) reste non portée. 1147 et 1148
  posent `AllowObscuredTarget`, donc pour elles la règle est de toute façon **désarmée nativement** —
  les deux seuls masques de ce lot où le non-port est sans conséquence *prouvable*. Pour 1021 / 1022 /
  1036, la règle n'est pas exercée par ces montages (terrain dégagé), pas prouvée inerte.
* **Le volet CASTER** : `casterReason` natif vaut `0` sur toutes les lignes des cinq abilities, donc
  aucune des règles caster non portées ne mord ici. `AllowNullCasterTile` (bit 30) n'est pas modélisé
  — il ne peut qu'**autoriser**, jamais refuser.
* **`TargetHasFreeAdjacentTile` (1021)** est porté mais **inerte sur ces deux montages** : aucune
  cible n'était encerclée. Un montage qui enferme une cible reste à faire.
* **La face COMBAT** des cinq abilities est hors périmètre (elle a ses propres tests).
* **1148 sur un board riche en tuiles non marchables** : `MC1_67` n'en a fourni qu'**une**. La règle
  est encadrée des deux côtés (2 marchables acceptées / 1 non marchable refusée), mais sur un seul
  échantillon négatif.
