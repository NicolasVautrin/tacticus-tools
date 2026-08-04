# #433-r4-r2-r1-r2-r2-r1-r1 — les 32 masques `rules` des abilities du pool hors registre

**Critère binaire** : les 32 abilities ACTIVES du pool spawnable absentes d'`ABILITY_CLASSES`
portent-elles leur masque `TargetingOptions.rules`, et ce masque rend-il le port conforme au natif ?

**Verdict** : **32/32 lus**, trois sources concordantes, **0 divergence**. Le port passe d'une
sur-attribution mesurée à l'**exactitude** sur le montage de walkability (FP 30 → **0**, FN 0), et
la lecture ferme **trois** résidus au lieu des deux annoncés. **Aucune des 32** ne porte le bit 43
`AllowUnwalkableTargetTile`.

---

## 1. Le périmètre, re-dérivé

`rl_duel build --list-pool` (rank 17, **97** unités régulières) × `gameconfig.activeAbilities`,
moins `ABILITY_CLASSES` (**102** entrées) = **32** abilities — exactement l'ensemble que portait
`engine.services.ability_range.TARGETING_RANGE_BY_ABILITY`, et exactement celles pour lesquelles
`targeting_options_for` rendait `None`. Le compte annoncé par la fiche héritée est confirmé par une
dérivation indépendante.

Les 97 unités du pool exposent **97** abilities actives distinctes ; les 32 sont donc **un tiers**
du kit actif confrontable.

## 2. Comment la surcharge a été tranchée — par les XREFS ENTRANTES

Ghidra rend le **même nom décompilé** (`TargetingOptions___ctor`) pour les trois surcharges de
`IdunBattle.Core.Services.TargetingOptions$$.ctor`. Ce qui les sépare est leur **adresse**, donc
l'appartenance d'un ctor d'ability à leur liste d'appelants — jamais le comptage d'arguments à
l'œil (c'est la faute qui a coûté `1029 Drachnyen`, #336).

| surcharge | signature | ce qu'elle écrit en `+0x28` | dans ce lot |
|---|---|---|---|
| A | `.ctor(this, isSelfCasting, range, forceMeleeTarget, rules, dynCaster, dynTarget)` | `rules` — le littéral EST le masque | **14** |
| B | `.ctor(this, template, additionalRules)` | `additionalRules \| template+0x28` | **5** |
| C | `.ctor(this, template)` | `template+0x28`, copie PURE, aucun `\|` | **1** |
| — | aucun ctor : STATIC-COPY des 0x40 octets d'un preset | `<preset>+0x28` du `.cctor` | **12** |

Les xrefs entrantes des trois adresses donnent la ventilation **directement** : la surcharge B liste
`FragstormGrenadeLauncher`, `HolyDuel`, `AttemptedPossession`, `WarHowl`, `VexillaMagnifica` (et
elles seules du lot) ; la surcharge C liste `BloodyFury` (et elle seule) ; la surcharge A les 14
autres. Le reste — 12 — n'apparaît dans aucune, ce qui EST la signature de la static-copy.

⚠ `1064 Loki_SwoopingHawk` n'a pas de corps propre : `SwoopingHawkAbility$$.ctor` fait
`return DiveAttackAbilityBase$$.ctor(this);`, et c'est la BASE qui recopie le preset `+0x40`.

## 3. Les 16 presets, relus dans le `.cctor`

`IdunBattle.Core.Services.TargetingOptions$$.cctor` écrit 16 blocs de 0x40 octets
(`isSelfCasting@+0x00`, `range@+0x08..0x1f`, `forceMeleeTarget@+0x20`, `rules@+0x28`). Ceux que ce
lot consomme :

| preset | `isSelfCasting` | `range` | `forceMeleeTarget` | `rules` |
|---|---|---|---|---|
| `+0x000` | 0 | `TR statics+0x00` ADJ_IF_MELEE | 2 `IfRangedCaster` | `0x4002` |
| `+0x040` | 0 | `TR statics+0x30` ADJACENT | 1 `False` | `0x4000` |
| `+0x140` | 0 | `TR statics+0x18` FROM_CONFIG | **0 `True`** | `0x4002` |
| `+0x180` | 0 | `TR statics+0x18` FROM_CONFIG | 1 `False` | `0x4002` |
| `+0x240` | 0 | `TR statics+0x48` WHOLE_BOARD | 1 `False` | `0x102004032` |
| `+0x280` | 1 | `TR statics+0x60` SELF | 1 `False` | `0x8004` |

⚠ **`+0x140` et `+0x180` portent le MÊME masque et diffèrent par `forceMeleeTarget`.** Les deux sont
dans ce lot (`1088 HellfyreMissileRack` contre `1027`/`1069`) : recopier le seul masque aurait laissé
le volet PORTÉE faux, sans que rien ne le signale. C'est le piège « même masque, presets différents ».

## 4. Ce qui a été porté

Les 32 entrent dans **`engine/runner/abilities/targeting.py::TARGETING_OPTIONS_UNPORTED`** avec
leurs **quatre** champs — ils sortent tous du même appel de ctor et se posent donc ensemble.

**`TARGETING_RANGE_BY_ABILITY` est SUPPRIMÉE.** Elle portait le volet PORTÉE **seul** des mêmes 32,
pendant que leur masque restait non lu : deux sources pour une même struct native de 0x40 octets,
donc un fork. `targeting_range_of` et `target_tiles_zone_is_empty` passent désormais par
`targeting_options_for`, foyer unique.

## 5. TROIS étages débloqués, pas deux

La fiche annonçait deux résidus fermés (obscurcissement `#433-r4-r2-r1-r2-r1`, walkability
`#433-r4-r2-r1-r2-r2-r1-r1`). Il y en avait un **troisième**, invisible depuis les deux fiches :

1. **Court-circuit AMONT** — `TargetingQuery$$GetPossibleTargetTiles` rend un `OrderedSet` **VIDE**
   quand `TargetIsFriendly && !TargetIsEnemy`, avant même `GetRange`. `target_tiles_zone_is_empty`
   lisait le **seul** `ABILITY_CLASSES` : les 32 y rendaient `False`. **6** d'entre elles portent le
   court-circuit (`1005`, `1038`, `1039`, `1049`, `1061`, `1175`) et ne versaient donc AUCUNE tuile
   côté natif pendant que le port versait leur disque de portée.
2. **Walkability** — le `RemoveAll` de `GetTilesInRange`, gaté par le bit 43. **0 porteur sur 32**,
   donc l'étage mord pour les 32.
3. **Ligne de vue** — les bits `AllowObscuredTargetBy*` décident de ce que
   `GetTilesObscuringTerrain` regarde. **4** porteuses : `1048` et `1177`/`1204` (élévation),
   `1087` (élévation **et** murs, seule du lot à porter les deux).

## 6. La confrontation live — deux montages, un étage chacun

Oracle : `aiMovableTiles {threat: true}` = `AttackQuery$$GetAllTilesInAbilityRange`, le **même**
slot 0xe que `BattleQuery$$IsTileInRangeOfAnyAbility` interroge. Le port y est évalué **en union sur
le même movable set** — sinon on comparerait deux questions différentes. Contre-factuel d'AVANT : la
portée seule, `rules = None` (le substrat exact de la table supprimée), jamais « aucune option ».

| montage | board | natif | port AVANT | port APRÈS |
|---|---|---|---|---|
| `templAncient` / `1061`, kit d'UNE ability friendly-only | `MC1_67` | 5 tuiles, `dmax 2` | 11 (**6 FP**), `dmax 3` | 6 (**1 FP**), `dmax 2` |
| `tauMarksman` / `1069`, portée 5, 34 non marchables / 63 | `C5_19` | 25 tuiles | 55 (**30 FP**) | **25 — 0 FP, 0 FN** |

`unit_threat_reach(templAncient)` : **2 → 1**, et les deux modèles sont donc SÉPARABLES — sans cet
écart, la mesure serait compatible avec les deux et ne prouverait rien.

⚠ La tranche précédente avait validé le **mécanisme** de walkability sur une ability **greffée**
(`1161`). Ici c'est une ability **du pool**, avec le masque que ce lot a lu : la mesure porte sur ce
que le jeu joue réellement.

## 7. Le résidu, ÉTABLI par lecture — et ce n'est pas un écart de masque

Le faux positif unique du montage `friendly` est **la tuile du set d'entrée elle-même**.
`GetTilesInRange` branche sur `range.OnlyAdjacent` vers `<IBattleQuery slot 0x51>` =
`GetAdjacentTiles(casterTiles, …)`, qui rend les **ADJACENTES** — elles excluent `casterTiles`. Le
port modélise la zone par un **rayon** et teste `d <= 1`, donc il inclut `d = 0` : chaque tuile du
set d'entrée est un faux positif, et aucune autre (le test live le BORNE à cet ensemble).

Invisible dans les montages précédents : dès que le movable set compte au moins deux tuiles à
distance ≤ portée, chacune est couverte depuis une autre. Il n'apparaît qu'en régime **singleton +
portée d'arme 1**. Résidu **`#433-r4-r2-r1-r2-r2-r1-r1-r1`**.

⚠ Le même décompilé montre que le bit 43 gouverne **aussi** le paramètre `onlyWalkable` des deux
branches génératrices (`GetAdjacentTiles` et le slot `0x67`), pas seulement le `RemoveAll` — trois
lectures du même bit, cohérentes.

## 8. Ce qui n'est PAS couvert

* **Les 4 bits d'obscurcissement ne sont pas confrontés SÉPARÉMENT.** Le mécanisme l'a été par
  `#433-r4-r2-r1-r2` ; ici seule leur propagation aux 4 porteuses est acquise par construction.
  Aucune mesure ne sépare `1087` (deux bits) de `1048` (un seul).
* **Le résidu §7** — 1 tuile sur 63 dans le régime singleton, sens PERMISSIF.
* **Les 10 abilities actives HORS pool** que le seed BC expose et qui n'ont toujours pas de masque
  (`1010`, `1015`, `1044`, `1053`, `1080`, `1091`, `1108`, `1144`, `1185`, `1186`) — hors périmètre
  de ce lot, inventaire dans le rapport. `1186 WallOfMirrors` est le sujet d'une autre tranche.
* **Le rayon de souffle sur la face DÉCISION est mesuré, pas confronté** : `_ability_kind` /
  `_refuses_all_enemy_targets` (`state_bridge`) sont **inchangés** sur les 32 (les chemins
  gameconfig donnaient déjà le bon `kind`) ; `nonattack.targets_tiles` passe à `True` pour **5**
  (`1057`, `1087`, `1121`, `1152`, `1197`), ce qui est la lecture native (`rules >> 6 & 1`) mais
  n'est pas confronté par un agreement dans cette tranche.

## 9. Validation

* **OFFLINE** — `test_433_r4_r2_r1_r2_ability_range_offline.py` : **24 passed**, dont quatre gardes
  neuves (présence des 32 masques + disjonction + portée préservée ; le de-fork, à périmètre
  **dérivé du seed BC versionné** ; bit 43 à zéro ; les 6 du court-circuit). Voisins :
  `line_of_sight_offline`, `friend_gates_offline`, `walkability_offline`,
  `runner/test_targeting_options_sources.py` — **77 passed** au total.
* **LIVE** — `test_433_r4_r2_r1_r2_r2_r1_r1_pool_masks_live.py` : **6 passed**. Voisins rejoués :
  `walkability_live` **8**, `line_of_sight_live` **7**, `friend_gates_live` **8**.
* **Cliquets** — `probe_181` (102/102 masques du registre), `probe_120` étape 0 (littéral
  `AbilityAttackType` : aucun manquant), `probe_217` (« routée ENNEMI alors que le masque le
  REFUSE » : **0**).
