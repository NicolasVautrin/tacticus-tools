# Case 247 — les CINQ masques du module `summon`, et les deux trous generiques qu'ils ont revele

`ScarabHive` (1007), `GetEmRuntz` (1045), `ScarabSummon` (1047), `MasterOfTheTutelaries` (1096) et
`AberrantHypermorph` (1166) entraient dans `ABILITY_CLASSES` **sans** `TARGETING_OPTIONS`.
`get_invalid_target_reason` / `get_invalid_caster_reason`
(`engine/runner/abilities/targeting.py`) commencent par
`options = getattr(ability, "TARGETING_OPTIONS", None)` et rendent **0 immediatement** quand c'est
`None` : aucun gate. Degradation **permissive** — ni erreur ni crash, invisible en self-play.

## 1. Les cinq ctors, lus un par un

| id | forme de ctor | ce qu'il faut lire | masque | `TargetingRange` | `isSelfCasting` | `AbilityAttackType` |
|---|---|---|---|---|---|---|
| 1007 `ScarabHive` | 1 — flags directs | le litteral | `0x4020` | statics `+0x30` = `RANGE_ADJACENT` | 0 | **1** `SummonAndAttackTarget` |
| 1045 `GetEmRuntz` | **3 — preset copie, aucun ctor** | `*(TargetingOptions statics+0x2a8)` | `0x8004` | `<preset>+0x08` <- statics `+0x60` = `RANGE_SELF` | **1** | 2 `Others` |
| 1047 `ScarabSummon` | 1 — flags directs | le litteral | `0x208000` | statics `+0x60` = `RANGE_SELF` | **1** | 2 `Others` |
| 1096 `MasterOfTheTutelaries` | 1 — flags directs | le litteral | `0x1040` | statics `+0x30` = `RANGE_ADJACENT` | 0 | 2 `Others` |
| 1166 `AberrantHypermorph` | 1 — flags directs | le litteral | `0x1040` | statics `+0x30` = `RANGE_ADJACENT` | 0 | 2 `Others` |

`forceMeleeTarget` vaut **1 = `RangedBool.False`** pour les cinq (4e argument du ctor, ou
`<preset>+0x20` pour 1045).

**1007 et 1047 sont dans le MEME fichier, de la MEME forme de ctor, et n'ont rien en commun** :
`0x4020` + `RANGE_ADJACENT` + `isSelfCasting = 0` contre `0x208000` + `RANGE_SELF` +
`isSelfCasting = 1`. C'est le contre-exemple interne du lot : deduire l'un de l'autre aurait produit
deux masques faux. Le seul couple identique est 1096 / 1166 — et il a ete lu deux fois, pas deduit.

Les `TargetingRange` statiques sont ceux qu'ecrit `IdunBattle.Core.Services.TargetingRange$$.cctor`
(relus en entier a cette occasion) : `+0x00` adjacent-si-melee, `+0x18` from-config, `+0x30`
`onlyAdjacent = RangedBool.True` + `overrideRange = Nullable(1)`, `+0x48` whole-board, `+0x60`
`onlyAdjacent = RangedBool.False` + `overrideRange = Nullable(0)`. Ils confirment ligne par ligne la
table du port.

### Le preset de 1045, lu en entier (`TargetingOptions$$.cctor`, bloc `statics+0x280`)

| champ | offset | valeur | signification |
|---|---|---|---|
| `isSelfCasting` | `statics+0x280` | `1` | self-cast |
| `range` | `statics+0x288` | copie de `TargetingRange statics+0x60` | **`RANGE_SELF`** (portee 0) |
| `forceMeleeTarget` | `statics+0x2a0` | `1` = `RangedBool.False` | pas de clamp melee |
| `rules` | `statics+0x2a8` | **`0x8004`** | les deux bits ci-dessous |
| les 2 delegues | `+0x2b0` / `+0x2b8` | `0` | ecrases par `AActiveAbility$$.ctor` |

`+0x280` -> `0x8004`, la ou `+0x140` -> `0x4002` et `+0x1c0` -> `0x6000040` : **troisieme preuve que
les presets ne sont pas interchangeables.**

### Decompositions bit a bit (exhaustives — aucun bit residuel)

**1007 = `0x4020`** (`0x20 + 0x4000`)

| bit | masque | nom | ce qu'il fait | porte |
|---|---|---|---|---|
| 5 | `0x20` | `TargetHasFreeAdjacentTile` | `GetFreeAdjacentTiles(target).Count == 0` => refus. C'est la precondition MECANIQUE : les 2 `necroSmnSwarm` naissent sur des tuiles libres **adjacentes a la cible** | oui |
| 14 | `0x4000` | `TargetIsEnemy` | `UnitsCanAttackEachOther` — refuse soi-meme et un allie | oui |

**1045 = `0x8004`** (`0x4 + 0x8000`)

| bit | masque | nom | ce qu'il fait | porte |
|---|---|---|---|---|
| 2 | `0x4` | `CasterMatchesDynamicRule` | regle-delegue `options+0x30` = `GetEmRuntzAbility$$GetDynamicInvalidCasterReason` | **oui, #250** (§3) |
| 15 | `0x8000` | `CasterIsPossibleTarget` | **declaratif** : n'apparait ni dans le filtre statique ni dans `GetInvalidCasterReason` ; seul `TargetingOptions$$get_CanTargetCaster` le lit | sans objet |

**1047 = `0x208000`** (`0x8000 + 0x200000`)

| bit | masque | nom | ce qu'il fait | porte |
|---|---|---|---|---|
| 15 | `0x8000` | `CasterIsPossibleTarget` | declaratif (idem) | sans objet |
| 21 | `0x200000` | `CasterHasFreeAdjacentTile` | jumelle EXACTE du bit 5, appliquee au CASTER (`slot 0x51` sur `param_2`), juste apres elle dans la cascade | non — **inatteignable**, §4 |

**1096 et 1166 = `0x1040`** (`0x40 + 0x1000`)

| bit | masque | nom | ce qu'il fait | porte |
|---|---|---|---|---|
| 6 | `0x40` | `TargetIsTile` | domaine TUILE ; tuile non marchable => le natif rend le **litteral 1** (`ValidRequest`), `AllowUnwalkableTargetTile` (bit 43) n'etant pas pose | oui |
| 12 | `0x1000` | `TargetTileIsFree` | `!CanAddUnit(GetMainTile(target), state, 1, 0, 0)` => refus | oui |

`RANGE_ADJACENT` fait prendre au filtre la branche `AreEntitiesAdjacent(casterTiles, target)` :
c'est litteralement le « on a free hex **adjacent to** Abraxas / Biophagus » de l'i2, et **ce n'est
pas `distance hex == 1`** — `MovementUtil$$AreTilesAdjacent` gate aussi l'ELEVATION (`|dElev| < 2`).
Mesure : sur `C3_26`, `tile-adjLIBRE (5,5)` a `d = 1` est refusee `TargetIsInRange` **par le natif
comme par le port**.

## 2. Le premier trou generique : le volet PORTEE etait AVEUGLE aux cibles TUILE

`get_range_broken_rule` resolvait ses deux empreintes avec `components.get_unit_feet`
(= `GetUnitFeetIds`), qui rend `[]` sur une TUILE — d'ou un `return 0` et **aucun gate de portee
pour toute ability tile-target**. Le natif, lui, passe l'ENTITE au slot `0x60` / a `GetDistance`,
qui resolvent par `EntityExtensions$$GetTiles` : pour une tuile, `GetTiles(tile) = [tile]`.

C'est exactement l'avertissement que porte deja la docstring d'`entity_tiles` — il n'avait pas ete
applique a cette fonction. Correctif : `entity_tiles` des deux cotes. Pour une cible UNITE le
resultat est **inchange** (`entity_tiles` commence par `get_unit_feet`).

Mesure avant/apres sur 1096, `MC1_67`/777, meme etat fige : **14 tuiles** (les `d2` et les `LOIN`)
ou le natif rend `TargetIsInRange` et ou le port rendait `0`.

Le correctif arme aussi le volet portee des tile-target deja au registre qui portaient un
`TargetingRange` non-whole-board (`astramilitarum`, `darkangels`, `admec`, `votann`, `orks`,
`tyranids`) — dans le sens NATIF, jamais inventif.

## 3. Le second trou generique : pas de point d'extension pour la regle dynamique du CASTER

`GetEmRuntzAbility$$GetDynamicInvalidCasterReason` **existe** et n'etait pas porte. Decompile :

```
ctx = default(SelectorContext); ctx.subject = caster; ctx.casterTiles = casterTiles;
list = this.GetSpawnTileSelector().Select(ctx);
return (list.Count > 0) ? 0 : 2;
```

Le litteral rendu est **2**, que l'enum genere nomme `TargetMatchesDynamicRule` : le natif reutilise
ce code pour la regle dynamique du volet CASTER, et `GetInvalidCasterReason` le re-emballe tel quel
(`GenericBrokenTargetingRule(r)`). L'oracle `abilityReason` le rend litteralement
`TargetMatchesDynamicRule`.

Semantique : « Get 'Em Runtz » **ne peut pas etre caste** s'il n'existe aucune tuile libre adjacente
au Runtherd **et** adjacente a un ennemi vivant non-`Steppable` — aucune place ou poser un grot.

Trois pieces posees, dans l'ordre natif relu en entier :

1. `ActiveAbility.get_dynamic_invalid_caster_reason` (defaut 0) — le pendant exact de
   `get_dynamic_invalid_target_reason`, mirror du virtuel slot `+0x470` ;
2. la clause bit 2 dans `get_invalid_caster_reason`, **apres** `CasterHasNotMoved` et la paire
   tuile-nulle, **avant** les filtres de `FeetCount` (ordre lu sur
   `TargetingQuery$$GetInvalidCasterReason`) ;
3. l'override sur `GetEmRuntzAbility`, qui evalue **le MEME** `get_spawn_tile_selector()` que son
   arbre de behaviour — gate et execution ne peuvent donc pas diverger.

**Sans ce port, 5 lignes sur 5 divergeaient** (`C3_26`/31337) : le natif rend `0x2` et le port `0`.

Le natif propage la raison CASTER dans `targetReason` (l'overload 5 arguments de
`GetInvalidTargetReason` rend `casterReason` tel quel) — d'ou la lecture du port par
`is_invalid_target`, le meme point d'entree, et non `get_invalid_target_reason` seul.

## 4. `CasterHasFreeAdjacentTile` (bit 21) : lu, situe, **non porte** — et pourquoi

Le bit a desormais un porteur (1047), donc la ligne « aucun porteur » de l'inventaire etait fausse.
La regle est dans le filtre statique, jumelle exacte du bit 5 :

```c
if ((rules & 0x200000) != 0) {
    tiles = battleQuery.<slot 0x51>GetFreeAdjacentTiles(caster);   // param_2, pas la cible
    if (tiles.Count == 0) -> broken(0x200000);
}
```

Elle est **INATTEIGNABLE par la cascade pour son seul porteur**, et c'est structurel :

* cible == caster -> `isSelfCasting = 1` fait brancher l'overload 5 arguments sur
  `GetCasterNotAddedReason`, qui n'evalue **jamais** le filtre statique ;
* cible != caster -> `RANGE_SELF` (portee 0) refuse deja `TargetIsInRange`, **qui precede le bit 21**
  dans la cascade.

Un port serait donc du code mort non invalidable -> **residu documente, pas de port speculatif**
(la ligne d'inventaire de `targeting.py` le dit maintenant). Mesure : sur les deux couples, **aucune
ligne** ne rend `0x200000`.

**Residu ouvert** : `GetCasterNotAddedReason` reste non porte (rend 0). Pour 1045 et 1047, dont
`isSelfCasting = 1`, le natif y evalue `GetValidTargets(...).AllTargets.Count == 0` et peut rendre
`0x800 AddCasterIfAtLeastOneTarget` — c'est par CE chemin que le bit 21 pourrait mordre pour 1047
(un scarab totalement encercle). Meme classe de residu que Chronometron (1226), deja documentee : il
faudrait porter `TargetingQuery$$GetValidTargets`, qui enumere tout le plateau.

## 5. Validation — `scripts/python/probe_250_summon_targeting.py`

Oracle = le **live** : `abilityReason(casterId, abilityType, targetId)`. Le port est rejoue
**offline sur le meme etat fige**, en cinq versions : `APRES`, `AVANT` (`TARGETING_OPTIONS = None`,
l'etat de `master`) et trois **contrefactuels par champ** — `sansRules` (`rules = 0`), `sansRange`
(`range = None`), `flipForceMelee` (`RangedBool.False` -> `RangedBool.True`).

Geometrie DRIVEE : caster amene au contact d'un ennemi, allie au contact, ennemis hors contact ;
pour 1047 le porteur SUMMON est amene en bataille en **castant d'abord ScarabHive** ; pour les deux
tile-target, le caster est **deplace** jusqu'a avoir une tuile libre reellement adjacente (sans quoi
aucune ligne ne serait acceptable — mesure sur `C3_26`).

| ability | couple | lignes | accord natif/port | natif REFUSE alors que `master` rendait 0 |
|---|---|---|---|---|
| 1007 | `MC1_67`/777 | 5 | **5/5** | **4** |
| 1007 | `C3_26`/31337 | 5 | **5/5** | **4** |
| 1045 | `MC1_67`/777 | 5 | **5/5** | **4** |
| 1045 | `C3_26`/31337 | 5 | **5/5** | **5** |
| 1047 | `MC1_67`/777 | 7 | **7/7** | **6** |
| 1047 | `C3_26`/31337 | 6 | **6/6** | **5** |
| 1096 | `MC1_67`/777 | 24 | **24/24** | **20** |
| 1096 | `C3_26`/31337 | 24 | **24/24** | **23** |
| 1166 | `MC1_67`/777 | 24 | **24/24** | **20** |
| 1166 | `C3_26`/31337 | 24 | **24/24** | **23** |

Regimes de refus effectivement exerces : `TargetIsEnemy` (1007), `TargetIsInRange` (les cinq),
`TargetTileIsFree` (1096/1166, y compris sur une cible UNITE — §6), `ValidRequest 0x1` sur tuile non
marchable (1096/1166), `TargetMatchesDynamicRule 0x2` cote CASTER (1045).

### Contrefactuels par champ — dont ceux qui NE mordent PAS

| ability | `rules` | `range` | `forceMeleeTarget` (flip) |
|---|---|---|---|
| 1007 | 2 lignes changent | 2 | **0 — inerte** |
| 1045 (`MC1_67`) | **0 — inerte** | 4 | 2 lignes changent |
| 1045 (`C3_26`) | 5 lignes changent | **0** (la regle CASTER refuse avant) | 0 |
| 1047 | **0 — inerte** | 5 a 6 | 2 lignes changent |
| 1096 / 1166 | 6 a 11 | 14 a 15 | **0 — inerte** |

Lecture honnete de ce tableau :

* **`force_melee_target` n'est valide par la mesure que pour 1045 et 1047** (ou le clamp melee
  transformerait la portee 0 en adjacence, donc accepterait des cibles a `d = 1`). Pour 1007, 1096 et
  1166 le flip ne change rien : la portee EST deja l'adjacence. Le champ est pose parce qu'il est
  **lu au decompile**, pas parce qu'il mord partout.
* **`rules` n'est valide par la mesure que pour 1007, 1096, 1166 et (via le bit 2) 1045 sur
  `C3_26`.** Pour 1047, aucun de ses deux bits ne peut mordre offline (§4) : le masque est pose
  parce qu'il est LU, et il est **exact**, mais cette mesure ne le valide pas.
* **`range` est le champ le plus porteur du lot** — il porte a lui seul le refus de toutes les cibles
  hors contact (1007, 1096, 1166) et de toute cible autre que le caster (1045, 1047).

### Le 2e etat de 1045 — celui qui valide le port de la regle CASTER

Dans l'etat principal le montage GARANTIT une tuile de spawn (sinon aucune cible ne serait
acceptee), donc la regle dynamique n'y mord pas et n'y prouve rien. Le probe fige donc un **second
etat** : Runtherd eloigne jusqu'a n'avoir plus aucune tuile de spawn valide, et confronte le seul
volet caster. `MC1_67`/777 et `C3_26`/31337 : **natif = port** dans les deux etats
(`0x2` quand la regle mord, `0` sinon).

## 6. Ce que le natif refuse et qu'on n'aurait pas devine

Interroger une ability **tile-target** avec une **UNITE** ne rend pas « domaine invalide » : le natif
resout `GetMainTile(target)` et applique la regle. Sur 1096/1166, la cible « caster », « allie au
contact » et « ennemi au contact » rendent toutes **`0x1000 TargetTileIsFree`** — parce que la tuile
de cette unite est occupee **par elle**. Le port ne testait le bit 12 que si `target_id` etait un id
du board ; il resout maintenant `entity_tiles(...)[0]` = `GetMainTileId`, pour les deux natures de
cible. C'etait **3 lignes de desaccord sur 24** au premier passage.

## 7. Compteurs

| | avant | apres |
|---|---|---|
| `ABILITY_CLASSES` | 94 | 94 |
| avec `TARGETING_OPTIONS` | 58 | **63** |
| sans | 36 | **31** |
| dont module `summon` | 5 | **0** |

`ABILITY_ATTACK_TYPE` : les cinq litteraux etaient **deja poses et justes** (1007 = `1`
`SummonAndAttackTarget`, les quatre autres `2` `Others`) — verifie contre le 3e argument de
`AActiveAbility..ctor`, aucun changement.

## 8. Artefacts

* port : `scripts/python/engine/runner/abilities/loki/summon.py` (les cinq `TARGETING_OPTIONS` +
  `GetEmRuntzAbility.get_dynamic_invalid_caster_reason`)
* generique : `scripts/python/engine/runner/abilities/targeting.py` (portee tile-aware,
  `TargetTileIsFree` sur `GetMainTile`, clause `CasterMatchesDynamicRule`),
  `scripts/python/engine/runner/abilities/base.py` (le patron caster)
* probe (MESURE) : `scripts/python/probe_250_summon_targeting.py`
* tests (GARDE) : `scripts/python/tests/engine/runner/test_summon_targeting_live.py`
* cliquet : `scripts/python/tests/engine/runner/test_ability_registry_ratchet.py` (les 5 retirees de
  `SANS_TARGETING_OPTIONS`)

## 9. Ce qui n'est PAS couvert

* ~~**`TargetHasFreeAdjacentTile` (bit 5) de 1007 n'a pas ete exerce**~~ — **EXERCE depuis
  `case-spawn-requires-tile.md`** : `probe_spawn_requires_tile.py` amene le necroSpyder au
  contact d'un ennemi dont la couronne est saturee et le natif rend bien
  `0x20 TargetHasFreeAdjacentTile` (`C3_26`/31337 et `MC1_67`/777, regime « 0 voisine libre »). Ce
  meme montage a leve le fantome de `SpawnUnitOperation` decrit ci-dessous.
* **`GetCasterNotAddedReason`** (§4) : non porte, rend 0. Concerne les deux self-casts du lot.
* **`CasterHasFreeAdjacentTile` (bit 21)** : lu, situe, non porte, inatteignable ici.
* **La ligne de vue** (`GetTilesObscuringTerrain`) reste non portee dans le gate generique — aucune
  des cinq ne pose de bit `AllowObscured*`, donc l'ecart est possible en theorie ; aucune divergence
  observee sur les 2 x 5 etats mesures.
* **Le routage de domaine** (`_ability_kind`) n'a pas ete touche : les deux abilities tile-target du
  lot restent routees comme le backlog le decrit. Poser le masque ne le deplace pas —
  `refuses_all_enemy_targets` est `False` pour les cinq (aucune ne porte `TargetIsFriendly` ni
  `TargetIsCaster`), donc le veto de routage IA est inchange.
