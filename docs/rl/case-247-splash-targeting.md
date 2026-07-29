# Case 247 — les masques de ciblage du module `splash` : six abilities, **trois formes de ctor**

Les six abilities de `engine/runner/abilities/loki/splash.py` entraient dans `ABILITY_CLASSES`
**sans** `TARGETING_OPTIONS`. `get_invalid_target_reason` / `get_invalid_caster_reason`
(`engine/runner/abilities/targeting.py`) commencent par
`options = getattr(ability, "TARGETING_OPTIONS", None)` et rendent **0 immédiatement** quand c'est
`None` : aucun gate. Dégradation **permissive** — ni erreur ni crash, invisible en self-play.

Le cas a été instruit **module entier**, ce qui en fait le contre-exemple le plus net à
« généraliser depuis la voisine » : six abilities du **même fichier**, relevant de **trois formes de
ctor** et de **trois presets** distincts, dont deux presets qui ne diffèrent que par **un champ**.

## 1. Table de lecture — une ligne par ability, aucune déduite

| id | ability | forme de ctor | `rules` effectif | `range` | `forceMeleeTarget` | `AbilityAttackType` |
|---|---|---|---|---|---|---|
| 1000 | `GauntletsOfUltramar` | **FACTORY NOMMÉE** | `0x4000` | `CustomRange(2)` | `RangedBool.False` | **2** `Others` |
| 1051 | `Stikkbomb` | PRESET+FLAGS `+0x140` \| `0x2000000` | `0x2004002` | `RANGE_FROM_CONFIG` (2) | `RangedBool.True` | 0 `DirectTargetAttack` |
| 1065 | `ScythingTalons` | PRESET COPIÉ `+0x40` | `0x4000` | `RANGE_ADJACENT` | `RangedBool.False` | 0 |
| 1078 | `Fragstorm` | PRESET+FLAGS **`+0x180`** \| `0x2000000` | `0x2004002` | `RANGE_FROM_CONFIG` (2) | **`RangedBool.False`** | 0 |
| 1098 | `PlasmaGrenade` | PRESET+FLAGS `+0x140` \| `0x2000000` | `0x2004002` | `RANGE_FROM_CONFIG` (2) | `RangedBool.True` | 0 |
| 1105 | `CrushingClaws` | PRESET COPIÉ `+0x40` | `0x4000` | `RANGE_ADJACENT` | `RangedBool.False` | 0 |

Tous les `AbilityAttackType` étaient **déjà posés et sont confirmés** au 3ᵉ argument de
`IdunBattle.Entities.Abilities.AActiveAbility$$.ctor` : `(..., 2, 0)` pour 1000, `(..., 0, 0)` pour
les cinq autres. Aucun changement requis, aucune divergence.

### 1000 — une **quatrième** forme : la factory nommée

`IdunBattleLogic.Entities.Abilities.Active.Loki.GauntletsOfUltramarAbility$$.ctor` n'écrit aucun
champ et ne copie aucun preset. Il appelle une **factory statique** :

```
TargetingOptions..SelfCastIfEnemyInCustomRangeOptions(&opts, 2)   # range = 2
AActiveAbility..ctor(this, &opts, 2, 0)                           # 2 = AbilityAttackType.Others
```

`IdunBattle.Core.Services.TargetingOptions$$SelfCastIfEnemyInCustomRangeOptions(int range)` écrit,
champ par champ (décompilé lu directement, pas déduit du nom) :

| champ | offset | valeur |
|---|---|---|
| `isSelfCasting` | `+0x00` | **`1`** |
| `range` (`TargetingRange` inline) | `+0x08` | `onlyAdjacent = 1` (`RangedBool.False`), `useRangeFromConfig = false`, `useWholeBoard = false`, `overrideRange = Nullable(2)`, `overrideRangeFunc = null` — soit exactement `TargetingRange$$CustomRange(2)` |
| `forceMeleeTarget` | `+0x20` | `1` = `RangedBool.False` |
| `rules` | `+0x28` | **`0x4000`** |
| les 2 règles-délégués | `+0x30` / `+0x38` | `0` (écrasées par `AActiveAbility$$.ctor`) |

`list_xrefs` sur cette factory : **un seul appelant natif**, ce ctor. Les trois autres porteurs du
même profil (`ResurrectionOrb` 1009, `AncestralFortune` 1207, `Chronometron` 1226) l'ont reçue
**inlinée** par IL2CPP — c'est pourquoi `necrons.py` la décrit comme « construction inline » pour
1226. Ici elle est lisible telle quelle, ce qui rend le masque de 1000 le mieux établi du lot.

### La surcharge PRESET+FLAGS, relue à la source

`IdunBattle.Core.Services.TargetingOptions$$.ctor(dst, preset, flags)` recopie le preset champ par
champ, à **une** exception :

```c
*(ulonglong *)(param_1 + 0x28) = param_3 | uVar2;      // uVar2 = *(preset + 0x28)
```

⇒ masque effectif = `flags | preset.Rules`. Ni le littéral visible dans le ctor (`0x2000000`), ni le
masque du preset (`0x4002`) : **leur OU**.

### Les presets, lus dans `TargetingOptions$$.cctor`

| preset | `isSelfCasting` | `range` | `forceMeleeTarget` | `rules` | consommé par |
|---|---|---|---|---|---|
| `+0x40` | `0` | `TargetingRange +0x30` = `RANGE_ADJACENT` | `1` `RangedBool.False` | `0x4000` | **1065**, **1105**, et 1043 (via PRESET+FLAGS, case-246) |
| `+0x140` | `0` | `TargetingRange +0x18` = `RANGE_FROM_CONFIG` | **`0`** `RangedBool.True` | `0x4002` | **1051**, **1098**, et 1014 (case-1014) |
| `+0x180` | `0` | `TargetingRange +0x18` = `RANGE_FROM_CONFIG` | **`1`** `RangedBool.False` | `0x4002` | **1078** |

Les cinq `TargetingRange` statiques ont été relus à l'occasion et **confirment ligne par ligne** la
table du port (`+0x00` adjacent-si-mêlée, `+0x18` from-config, `+0x30` adjacent, `+0x48`
whole-board, `+0x60` self).

### Décompositions, exhaustives (aucun bit résiduel)

`0x4000` (1000, 1065, 1105) — bit 14 `TargetIsEnemy` seul. `0x4000 = 0x4000`.

`0x2004002` (1051, 1078, 1098) :

| bit | masque | nom (`IdunBattle.Core.Services.TargetingRule`) | port |
|---|---|---|---|
| 1 | `0x2` | `TargetMatchesDynamicRule` | point d'extension ; aucune de ces trois ne surcharge `get_dynamic_invalid_target_reason` ⇒ défaut `0` (**permissif**) |
| 14 | `0x4000` | `TargetIsEnemy` | **porté** (`UnitsCanAttackEachOther`) |
| 25 | `0x2000000` | `AllowObscuredTargetByElevation` | **désarme** une règle de ligne de vue elle-même non portée ⇒ sans effet, dans le bon sens |

`0x2 + 0x4000 + 0x2000000 = 0x2004002` : somme exacte.

## 2. Le piège du lot : `+0x140` vs `+0x180`

Les deux blocs de `TargetingOptions$$.cctor` sont **identiques sauf `<preset>+0x20`** :
`RangedBool.True` pour `+0x140`, `RangedBool.False` pour `+0x180`. Recopier le masque de la voisine
aurait donc donné le **bon `rules`** (`0x2004002` des deux côtés) et le **mauvais volet portée** —
la forme d'erreur la plus difficile à voir, parce que le chiffre qu'on vérifie d'abord tombe juste.

Ce que ce champ décide, dans `IdunBattle.Core.Services.TargetingQuery$$GetRange` :

```
if (RangedBoolExtensions.IsTrue(options.ForceMeleeTarget, caster)
    && attackQuery.ShouldApplyRangedInMelee(caster, casterTiles, true))
    { v = Math.Min(1, v); onlyAdjacent = true; }
```

⇒ `Stikkbomb` et `PlasmaGrenade`, avec un ennemi non-`Steppable` au contact du caster, **retombent
à la portée 1** ; `Fragstorm`, dans le même état, **garde sa portée 2**. Trois abilities de splash
ranged (range 2, profil Blast/Plasma) au comportement de portée différent, et rien dans le kit ne
l'annonce.

## 3. Mesure live — items 1000 et 1105

Oracle = `abilityReason(casterId, abilityType, targetId)`, qui appelle
`IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason`. Le probe
(`scripts/python/probe_247_splash_targeting.py`) rejoue le gate offline sur le **même état figé**,
en cinq versions (six pour 1000) : `APRÈS`, `AVANT` (`TARGETING_OPTIONS = None`, l'état de `master`),
`sansRules`, `sansRange`, `fmtFlip`, `sansSelf`.

La géométrie est **fabriquée**, pas subie : `_drive_spectrum` place un ennemi à **chaque** distance
de `(1, 2, 3, 5)` de l'ancre — ce sont les deux seuils du lot (`d=1` vs `d=2` pour l'adjacence,
`d=2` vs `d=3` pour la portée 2) — puis `_bring_to_contact` amène le second caster au contact.

**Deux couples (board, seed), `PASS` sur les deux :**

| couple | 1000 accord | 1000 gains | 1105 accord | 1105 gains |
|---|---|---|---|---|
| `MC1_67` / 777 | **6/6** | 3 | **6/6** | 5 |
| `C4_09` / 31337 | **6/6** | 3 | **6/6** | 5 |

« gains » = lignes où le natif **REFUSE** alors que `master` (masque `None`) rendait `0` — des casts
illégaux que le moteur acceptait.

Détail `MC1_67`/777 (identique en structure sur `C4_09`/31337) :

| ability | cible | d | natif | port APRÈS | port AVANT |
|---|---|---|---|---|---|
| 1000 | ennemi | 1 | `0x0` | `0x0` | `0x0` |
| 1000 | ennemi | **2** | `0x0` | `0x0` | `0x0` |
| 1000 | ennemi | **3** | `0x8000000` `TargetIsInRange` | idem | **`0x0`** |
| 1000 | ennemi | 5 | `0x8000000` | idem | **`0x0`** |
| 1000 | **le caster** | 0 | `0x0` | `0x0` | `0x0` |
| 1000 | allié | 1 | `0x4000` `TargetIsEnemy` | idem | **`0x0`** |
| 1105 | ennemi | **1** | `0x0` | `0x0` | `0x0` |
| 1105 | ennemi | **2**+ | `0x8000000` `TargetIsInRange` | idem | **`0x0`** |
| 1105 | allié | 1 | `0x4000` | idem | **`0x0`** |
| 1105 | **le caster** | 0 | `0x4000` | `0x4000` | **`0x0`** |

Les deux seuils tombent exactement où le décompilé les place : **1000 accepte `d=2` et refuse
`d=3`** (`overrideRange = 2`, comparaison `hexDistance <= 2`), **1105 accepte `d=1` et refuse
`d=2`** (`onlyAdjacent` ⇒ branche `AreEntitiesAdjacent`, pas une distance).

La ligne **« cible = le caster »** oppose les deux abilities du même module : 1000 l'accepte
(`isSelfCasting` aiguille vers `GetCasterNotAddedReason`, qui n'évalue jamais la cascade), 1105 la
refuse sur `TargetIsEnemy`. C'est la démonstration directe que le byte `options+0x00` n'est pas
décoratif.

### Contrefactuels, champ par champ

Comptés comme **lignes divergentes dans les deux sens** — neutraliser un champ peut faux-**accepter**
(le refus disparaît) comme faux-**refuser** (armer un clamp que le natif ne pose pas). Ne compter que
les faux-accepts aurait déclaré « non validé » deux champs pourtant démontrés porteurs.

| champ neutralisé | 1000 (`MC1_67`) | 1105 (`MC1_67`) | ce que ça prouve |
|---|---|---|---|
| `rules = 0` | 1/6 | 2/6 | `TargetIsEnemy` porte le refus des cibles amies |
| `range = None` | 2/6 | 3/6 | le volet portée porte les refus `TargetIsInRange` |
| `force_melee_target` basculé | **1/6** | **0/6** | pour 1000 : bascule `RangedBool.True` ⇒ clamp de mêlée ⇒ la ligne `d=2` passe de `0x0` à `0x8000000`, un **faux refus**. Pour 1105 : `RANGE_ADJACENT` clampe déjà à 1, le champ ne peut rien changer |
| `self_cast = False` (1000) | **1/6** | — | la ligne « cible = le caster » passe de `0x0` à `0x4000`, faux refus |

**Explicitement non validé par la mesure** : `force_melee_target` de **1105** (et, par identité de
preset, de **1065**). Sa neutralisation ne change **rien** sur l'état mesuré, et c'est structurel :
`RANGE_ADJACENT` pose déjà `onlyAdjacent`, donc le clamp de mêlée est un no-op. Le champ est **lu au
décompilé**, pas mesuré — et il ne peut pas créer d'écart tant que la portée reste l'adjacence.

**Volet CASTER** : `casterReason` natif = `0` sur toutes les lignes des deux abilities, et le port
rend `0` — aucun des deux masques ne pose `CasterHasNotMoved`, donc rien à porter et rien qui puisse
diverger.

## 4. Confrontabilité des porteurs — ventilée

| id | porteurs | chemin de spawn |
|---|---|---|
| 1000 | `ultraCalgar` **lineup** (+ 3 npc) | **au pool** (`--list-pool`) ✔ mesuré |
| 1105 | `tyranTyrantGuard` **lineup** (+ 5 npc) | **au pool** ✔ mesuré |
| 1065 | `tyranSmnWarrior` **summon**, 4 npc | summoner `tyranWingedPrime` (au pool) caste `AlphaWarrior` (**1112**) — spawn obtenu, porteur non résolu (§5) |
| 1051 | `orksOrkBoys` **summon**, 1 npc | summoner `orksWarboss` (au pool) caste `Waaagh` (1058) — spawn non obtenu (§5) |
| 1078 | `templSmnAggressor` **summon**, 1 npc | **aucun summoner d'unité** : le seul poseur est le PowerUp `PowerUp_SummonSpawn_templSmnAggressor` |
| 1098 | `eldarSmnGuardian` **summon**, 1 npc | **aucun summoner au gameconfig** (même situation que `astraSmnVoxcaster`, case-245) |

⚠ **Qualifier les abilities, pas se fier au nom.** `templAggressor` (le héros Aggressor, au pool)
**ne porte pas** `Fragstorm` (1078) mais `FragstormGrenadeLauncher` (**1048**) — deux
`ActiveAbilityType` distincts. Un recensement par sous-chaîne du nom l'avait classé porteur de 1078 ;
c'est l'oracle live qui a tranché (`abilityState.usable = false`, donc court-circuit `ValidRequest`),
avant que le gameconfig ne le confirme par `activeAbilities`.

## 5. Ce qui n'est PAS couvert

- **1051 / 1078 / 1098 : RÉSOLU depuis, par case-243.** Les trois sont désormais confrontées live
  (14/14 chacune, seuil encadré des deux côtés **et** clamp de mêlée exercé) et gardées par
  `test_splash_range_clamp_live.py`. La voie qui a débloqué le lot est celle qui est décrite
  ci-dessous comme « non tentée » : catalogue injecté **+ retrait du trait `Summon`**, qui est ce qui
  désarmait `CanStillBeUsed`. Voir `docs/rl/case-243-splash-range-clamp.md`.
- **1065 : masque POSÉ sur RE, validation live NON obtenue.** La lecture est exhaustive et mécanique,
  et **1065 est validé par identité de source** : son preset est `+0x40`, **le même bloc mémoire** que
  1105, dont l'accord natif/port est mesuré 6/6 sur deux couples. Le seul écart possible serait une
  erreur de lecture du ctor, or les deux ctors sont textuellement identiques hors le `this`. Il reste
  le seul item du module sans mesure — la voie de case-243 s'y applique telle quelle.
- **Blocages rencontrés dans CETTE tranche, et ce qu'ils valaient réellement** :
  - `Waaagh` (1058) rend **0 cible légale** (`abilityTargets.fromHere`) tant que les ennemis sont
    hors de `constants.range = 3` ; une fois le spectre monté il en rend toujours 0 sur les deux
    positions essayées — sa règle dynamique (`WaaaghAbility$$GetDynamicInvalidTargetReason`) n'a pas
    été instruite ici. Blocage **contourné** par case-243 : on n'invoque plus, on spawne le summon
    directement depuis le catalogue.
  - `AlphaWarrior` (1112) **invoque bien** (`spawned=1` puis `2`), et les unités apparues sont
    `tyranNpc4Warrior` + `tyranNpc1Hormagaunt` dans l'équipe du summoner — donc le `visualId` du
    spawn **n'est pas** l'id gameconfig du summon. Aucune unité ne rendait `abilityState.usable`
    pour 1065 : c'était bien **le résidu de case-245** (le trait `Summon` désarme `CanStillBeUsed`),
    confirmé par case-243, qui le lève en retirant ce trait de l'entrée de catalogue.
- **La ligne de vue** (`GetTilesObscuringTerrain`) reste non portée. Sans conséquence *dans ce sens*
  pour 1051/1078/1098 : leur bit `AllowObscuredTargetByElevation` **désarme** justement une partie de
  cette règle côté natif.
- **La règle dynamique** (`TargetMatchesDynamicRule`, bit 1) des trois abilities `0x2004002` : le
  port rend `0` (défaut permissif). Si l'une d'elles surcharge réellement
  `GetDynamicInvalidTargetReason` — invérifiable par absence dans les tables de symboles, qui
  dédupliquent les corps triviaux — le port accepterait des cibles que le natif refuse. C'est la
  seule dégradation connue de ces trois masques, et elle va du côté permissif.
- **Le volet CASTER** au-delà de `CasterHasNotMoved` : aucun des six masques ne pose de bit caster,
  donc rien de neuf ici.

## 6. Compteurs

| | avant | après |
|---|---|---|
| `ABILITY_CLASSES` | 94 | 94 |
| avec `TARGETING_OPTIONS` | 58 | **64** |
| sans | 36 | **30** |
| dont module `splash` | 6 | **0** |

## 7. Artefacts

- port : `scripts/python/engine/runner/abilities/loki/splash.py` (les six classes)
- probe (MESURE) : `scripts/python/probe_247_splash_targeting.py` (`--group heroes|summons`) pour
  1000/1105 ; `scripts/python/probe_243_splash_range_clamp.py` pour 1051/1078/1098 (case-243)
- test (GARDE) : `scripts/python/tests/engine/runner/test_splash_targeting_live.py` (1000/1105) et
  `scripts/python/tests/engine/runner/test_splash_range_clamp_live.py` (1051/1078/1098)
- cliquet : `scripts/python/tests/engine/runner/test_ability_registry_ratchet.py`
  (les six retirées de `SANS_TARGETING_OPTIONS`, chacune avec sa forme et son calcul)

## 8. La leçon transférable

Le module `splash` porte **trois** des quatre formes de ctor connues, plus la quatrième (factory
nommée) découverte ici. La seule méthode qui tienne reste : **décompiler le ctor de CETTE
ability**, identifier **quelle surcharge** de `TargetingOptions$$.ctor` est appelée — ou si c'est une
**factory**, ou si **aucun appel** n'a lieu — puis lire le preset **dans le `cctor`**, champ par
champ et pas seulement `Rules`.

Et le corollaire, que ce lot rend chiffrable : sur six abilities d'un même fichier, **deux paires
partagent leur preset** (1065/1105 et 1051/1098) et **une le brise d'un seul champ** (1078). Une
généralisation « le module `splash` vaut X » aurait été fausse pour 1000 (masque et forme
différents), fausse pour 1078 (volet portée), et juste par accident partout ailleurs.
