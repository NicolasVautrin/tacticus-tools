# #433-r4-r2-r1 + -r2 — le CONTENU des deux branches d'`EarlyWarningOverridePlaybook`

**Verdicts : `-r2` FERMÉ (mirror 1:1, foyer déjà porté) ; `-r1` PORTÉ AU GRAIN ATTEIGNABLE, avec
deux résidus MESURÉS.** Les deux sont traités dans la même tranche parce que les fermer séparément
produit un port dégénéré : `threshold` (branche B) et l'ancienne approximation de la branche A
(« portée d'arme max ») sont **numériquement égales** sur toute unité à une seule arme à distance —
le partage A/B aurait cessé d'être observable *dans le port*, et aucun test d'utilité ne l'aurait vu.

Après la tranche, sur `tauMarksman`, les deux branches valent **5** et **3**. Elles sont séparées.

## 1. La chaîne native, LUE

```
BattleQuery$$IsTileInRangeOfAnyAbility(unit, tile)                      # slot IBattleQuery 0xc5
    if (UnitExtensions.GetFeetCount(unit, state) > 1) return true;      # court-circuit MULTI-TUILES
    main  = EntityExtensions.GetMainTile(unit, state);
    set   = new OrderedSet<Tile>(main == null ? new List<Tile>() : main.ToList());
    tiles = <this.attack @+0x20>.<slot 0xe>(unit, set, true);
    return tiles != null && tiles.Contains(tile);
```

Le service à `BattleQuery+0x20` est le paramètre **`attack`** de
`IdunBattle.Core.Services.BattleQuery$$Initialize(processor, movement, tileQuery, ATTACK, effects,
damagePrediction, …)`. Son slot `0xe` est
`IdunBattle.Core.Services.AttackQuery$$GetAllTilesInAbilityRange(unit, possiblePositions,
includeNormalAttack)` — surcharge à TROIS arguments, `includeNormalAttack` = le littéral `1` du
call-site.

⚠ **L'ensemble de positions est le SINGLETON `{GetMainTile(unit)}` : il n'y a AUCUN mouvement dans
cette question.** La fiche héritée (`case-433-r4-r2` §7) annonçait « mouvement et LoS compris » —
la lecture du slot le RÉFUTE. Ce qui portait à `d = 5` sur `tauMarksman` (arme de portée 3), c'est
son ability `SeekerMissileFrequencyLock`, pas un rayon de déplacement.

En aval, `AttackQuery$$GetAllTilesInAbilityRange(unit, position, ability)` gate chaque ability
(`CanCurrentlyBeUsed`, `IsAbilityBlocked`, `GetInvalidCasterReason`) puis appelle les slots `9`/`10`
de l'`IActiveAbility` ; le slot `9` par défaut est
`AActiveAbility$$GetPossibleTargetTiles` → `TargetingQuery$$GetPossibleTargetTiles` →
`TargetingQuery$$GetRange` + `GetPossibleTargetsForOptions`.

Branche B, verbatim du corps du playbook :

```
w   = <IBattleQuery slot 0xb3>(otherUnit)           # BattleQuery$$FindRangedWeapon(unit)
n   = (w != null) ? *(Nullable<int>*)(w + 0x24) : default(Nullable<int>)
thr = n.HasValue ? n.GetValueOrDefault() : 1
if (thr < d) util += 50
```

## 2. Le substrat de la portée par ability

`TargetingRange` (0x18 o) vit à `TargetingOptions+0x08` ; ses cinq instances STATIQUES sont écrites
par `IdunBattle.Core.Services.TargetingRange$$.cctor`, RE-lues **à l'octet** et identiques aux cinq
que `engine.runner.abilities.targeting` nommait déjà :

| statique | contenu | nom du port |
|---|---|---|
| `+0x00` | `onlyAdjacent = 3` (IfNotRangedCaster) | `RANGE_ADJACENT_IF_MELEE_CASTER` |
| `+0x18` | `useRangeFromConfig = 1` | `RANGE_FROM_CONFIG` |
| `+0x30` | `onlyAdjacent = 0` (True), `overrideRange = 1` | `RANGE_ADJACENT` |
| `+0x48` | `useWholeBoard = 1` | `RANGE_WHOLE_BOARD` |
| `+0x60` | `overrideRange = 0` | `RANGE_SELF` |

Un `<X>Ability$$.ctor` pose son `TargetingRange` de trois façons — les trois sont dans le lot lu :
ctor « flags directs » (`&range` = un statique), **preset** (recopie des 0x40 o d'un statique de
`TargetingOptions`, dont `TargetingRange` occupe `<preset>+0x08`), ou `CustomRange(GetRange)`
(délégué → portée non dérivable).

**Ce qui est entré au port** : `engine/services/ability_range.py`, avec deux sources —
`ABILITY_CLASSES` (registre du runner, **102 entrées, 102 avec un `TargetingRange`**) et
`TARGETING_RANGE_BY_ABILITY` (les **32** abilities actives du pool spawnable qui n'y étaient pas,
lues ctor par ctor). Une garde offline interdit qu'une ability figure dans les deux.

## 3. Ce que la mesure a tranché — et ce qu'elle a invalidé

`probe_433_r4_r2_r1_ability_range.py --step kit` : caster à `d = 8` de l'ennemi (branche A pure),
`Movement = 6`, **sweep de 40 positions, `d = 2..10`**. Le terme s'isole par
`bonus = util + 10·Σ_E d(P,E)` : `0` = en portée, `50` = hors portée.

| kit ennemi | arme | ability | reach NATIF | port | verdict |
|---|---|---|---|---|---|
| `tauMarksman` | 3 | `SeekerMissileFrequencyLock` `RANGE_FROM_CONFIG`, `range = 5` | **5** | 5 | **EXACT 40/40** |
| `astraDreir` | mêlée | `LeadingTheCharge` `RANGE_WHOLE_BOARD` | **1** | 1 | **EXACT 40/40** |
| `custoBladeChampion` | mêlée | `MartialInspiration` `RANGE_ADJACENT` | **1** | 1 | EXACT |
| `bloodDante` | mêlée | `LightOfSanguinius` `RANGE_WHOLE_BOARD` | **≈5** | 1 | **DIVERGE, 18 FN / 0 FP** |

**Un verrou de montage a invalidé une première mesure, et c'est le point de méthode de ce cas.** La
partition n'est attribuable qu'à **UN** ennemi vivant : chacun verse son propre `+50/0` *et* son
propre `−10·d`. `genesMagus` amène **deux summons au spawn** (`genesSmnDecoy`, `genesSmnNeophyte`) —
la partition lue était un mélange de trois kits, et elle affichait « en portée à `d = 7,8`, hors à
`d = 2..6` », un profil géométriquement impossible. Le probe REFUSE désormais ce montage.

## 4. Ce qui est porté, et ce qui ne l'est pas

**Porté** — la structure, étage par étage : le court-circuit multi-tuiles, le singleton de la tuile
courante, l'union `attaque normale ∪ abilities`, et la cascade `GetRange` (override du ctor > config
`constants.range` > portée d'arme, dans **cet** ordre — `SetConfigValuesInTargetingOptions` ne pose
la config que si `OverrideRange` est encore vide), `only_adjacent` ramenant la portée effective à 1.

**Non porté, et c'est mesuré** — la ZONE est modélisée par un **disque** de rayon `max(portées)` :
ni la forme, ni le LoS, ni les gates par ability du natif.

## 5. Résidus NOMMÉS

* **`#433-r4-r2-r1-r1` — FERMÉ.** Le discriminant est le slot de vtable `klass+0x478`,
  `GetDynamicInvalidTargetReason`. Détail complet : **§7 ci-dessous**.
* **`#433-r4-r2-r1-r2` — le LoS/élévation retire des tuiles du disque.** Sur le montage à RELIEF de
  `--step couple` (`O` élévation 2, ennemi élévation 4), le natif exclut de la zone **une** tuile à
  `d = 4` que ses voisines de même distance contiennent. Mesure : **1/34** sur relief, **0/40** sur
  le montage plat du même kit → l'écart est porté par le relief, pas par la portée. Le port
  SOUS-estime alors l'utilité de 50. Borné par un test.
* **`#433-r4-r2-r1-r3` — le court-circuit `GetFeetCount(unit) > 1 → true` est inatteignable côté
  DÉCISION.** Aucun canal ne publie le compte de pieds (aucun champ gameconfig ne porte la taille
  d'une unité). Le port passe `feet_count = 1` ; pour une unité MULTI-HEX il rend `False` là où le
  natif rend `True`, donc il attribue le bonus que le natif refuse. *Point d'ancrage à hooker* :
  `IdunBattle.Entities.UnitExtensions$$GetFeetCount`, à publier par unité dans `decisionView`.
* **`UnstoppableMomentumReworked` (1152)** est la seule des 32 dont le ctor ne se trouvait pas par
  le motif `<Name>Ability$$.ctor` en première recherche ; il a été lu (`RANGE_ADJACENT`, `TR+0x30`)
  et est dans la table. Aucun résidu.
* **`#433-r4-r2-r3` (`MIN_UTILITY = 1` CONTESTÉ) reste OUVERT et NON TOUCHÉ.** Cette tranche ne
  l'éclaire pas : elle n'a lu ni le ctor du Bucket ni un `get_MinUtility`. Le constat de `--step
  couple` est inchangé — le natif attribue des utilités négatives à toutes les positions du sweep,
  et le port les rejette.

## 6. Validation

* **OFFLINE** — `tests/engine/test_433_r4_r2_r1_r2_ability_range_offline.py`, **18 passed** : les
  cinq statiques, la cascade et son ORDRE (override > config, prouvé sur un `TargetingRange`
  synthétique portant les deux), `only_adjacent`, les deux régimes indécidables, les trois reach
  mesurés, le court-circuit multi-tuiles, `GetMainTile == null`, le disque, le `threshold` et son
  `?? 1`, la non-duplication des deux sources, et **la garde anti-dégénérescence** (`reach !=
  threshold` sur `tauMarksman`).
  `tests/engine/test_433_r4_r2_adjacency_foyer_offline.py` (tranche précédente) : **15 passed**,
  dont deux RE-ÉTALONNÉS — les deux seuils ayant changé, l'action émise change aussi
  (`30 → 10` sans canal ; `10 → aucune action` avec).
* **LIVE** — `tests/engine/test_433_r4_r2_r1_ability_range_live.py`, **4 passed** : sweep
  discriminant, accord EXACT dans les deux sens sur `tauMarksman`, `reach > threshold`, et le
  résidu `bloodDante` gardé comme **borne inférieure** (0 faux positif, écart non vide — s'il
  disparaissait, c'est que la zone whole-board serait devenue dérivable et le résidu à relire).
  `tests/engine/test_433_r4_r2_adjacency_foyer_live.py` : **7 passed** après ré-étalonnage du
  montage — l'ancien confinait le sweep à `d <= 3`, domaine où les approximations d'alors étaient
  exactes, ce qui retirait justement `3 < d <= 5`, la zone où les deux branches diffèrent.
* **Non-régression** — `test_356_noncomparable_oracle_live.py` (14 passed),
  `test_nc_priority_tiers_offline.py` (5 passed).
* **NON COUVERT** — les unités MULTI-HEX (cf. `-r1-r3`) ; les abilities actives des unités HORS pool
  spawnable (npc, summons), dont le `TargetingRange` n'est pas dans la table : elles retombent sur la
  portée d'arme, ce qui est le cas natif majoritaire mais pas une garantie.
  (`-r1-r1` était listé ici ; il est FERMÉ — §7.)

---

# 7. `#433-r4-r2-r1-r1` — ce qui sépare deux abilities au MÊME preset

**Verdict : FERMÉ.** Le discriminant n'est ni un gate d'ability, ni le slot 10, ni un override de
`GetPossibleTargetTiles` : c'est le slot de vtable **`klass+0x478` = `GetDynamicInvalidTargetReason`**.

## 7.1 La chaîne, LUE

`IdunBattle.Entities.Abilities.AActiveAbility$$.ctor` ne se contente pas de recopier les 0x40 octets
du preset dans `this.<TargetingOptions @+0x70>` — il **ÉCRASE ensuite deux champs** par des délégués
liés à des méthodes **virtuelles** de l'instance :

```
this.TargetingOptions.<+0x30> = new TargetingOptions.DynamicTargetingRule(this,       <klass+0x470>)
this.TargetingOptions.<+0x38> = new TargetingOptions.DynamicTargetingTargetRule(this, <klass+0x480>)
```

`klass+0x470` / `klass+0x480` sont les champs `MethodInfo*` (à `+8` du début de slot) des slots
commençant à `klass+0x468` / `klass+0x478` — la vtable IL2CPP démarrant à `klass+0x138` avec un pas
de `0x10`, ce sont les index **51** et **52**. **Résolus au RUNTIME** (`resolveVtableSlot`) :
`GetDynamicInvalidCasterReason` et `GetDynamicInvalidTargetReason`.

Le champ `+0x38` est exactement celui qu'invoque le **troisième prédicat** de
`IdunBattle.Core.Services.TargetingQuery$$GetPossibleTargetsForOptions` — la lambda
`TargetingQuery.u003Cu003Ec__DisplayClass34_0$$u003CGetPossibleTargetsForOptionsu003Eb__2`, appliquée
en `RemoveAll` quand `Rules & 2` (posé dans `0x102004032`) : **la tuile est RETIRÉE quand le délégué
rend une raison non nulle.** Le gate ne peut donc que RÉTRÉCIR, et le rayon de `GetTilesInRange` en
est une borne SUPÉRIEURE.

**Preuve runtime, pas déduction d'absence** — le corps de base est trivial donc DÉDUPLIQUÉ par
IL2CPP, l'absence d'un symbole ne dirait rien :

| classe | slot `0x478` | verdict |
|---|---|---|
| `AActiveAbility` | `A` | base, rend `0` — ne retire rien |
| `LightOfSanguiniusAbility` | `B ≠ A` | **surcharge** |
| `LeadingTheChargeAbility` | `C ≠ A, C ≠ B` | **surcharge** |
| `MartialInspirationAbility`, `SeekerMissileFrequencyLockAbility` | `A` | pas de gate |

Balayage complet (`probe_433_r4_r2_r1_r1_dynamic_target_gate.py --step gate`) : **19 des 32**
abilities `UseWholeBoard` du port surchargent, **13 non** — leur zone est donc le plateau ENTIER.

⚠ **Calibrage des slots d'interface, re-dérivé au runtime** (#542). `IsTileInRangeOfAnyAbility` est
l'index **201** de la vtable de `BattleQuery` pour le slot `IBattleQuery 0xc5`, et `FindRangedWeapon`
l'index **183** pour `0xb3` → **ifaceOffset = 4**, accordé sur un 3ᵉ point (`GetAllAliveMachines`,
slot `0x97` → index 155). D'où : slot `0x53` = **`GetFreeAdjacentTiles`**, slot `0x6d` =
**`GetDistance`**, slot `0x69` = **`GetAllTiles`**, slot `0xc` = `GetMovableTilesFor`.

## 7.2 Les trois régimes, et leur mesure

`TargetingQuery$$GetRange` court-circuite sur `UseWholeBoard` — il rend
`{ Range = 1, OnlyAdjacent = false, UseWholeBoard = true }` **sans évaluer** `only_adjacent` ni la
portée d'arme — puis `GetTilesInRange` branche dessus EN PREMIER et rend `GetAllTiles()`.

| ability | gate | zone | mesure natif (sweep 40, `d = 2..10`) |
|---|---|---|---|
| `1177 LightOfSanguinius` | `GetFreeAdjacentTiles(...).Any(t => GetDistance(t, casterTiles) <= config.range)` | `config.range + 1` | 100 % à `d ≤ 5`, **4/6 à `d = 6`**, 0 à `d ≥ 7` |
| `1153 HammerOfWrath` | **identique**, `config.range = 5` | idem | profil **identique**, mêmes tuiles |
| `1140 ExemplarOfHate` | AUCUN | tout le plateau | **40/40**, à toute distance |
| `1204 LeadingTheCharge` | `DSLSelectors$$TilesUnitCanMoveToChargeTarget` = `CanAddUnit(AdjacentTiles(target)) & MovableTilesInRangeSelector` | non dérivable (mouvement) | **0/40** |

Le `+1` vient de ce que le test porte sur les **VOISINES** de la cible, pas sur la cible. Un modèle en
`config.range` aurait prédit zéro à `d = 6` : **seule la ventilation PAR DISTANCE sépare les deux** —
une comparaison globale ne l'aurait pas vu.

## 7.3 La porte d'élévation — mesurée, puis tranchée au décompilé

À `d = 6`, le natif accepte **4 tuiles sur 6**. Les deux refusées sont à élévation 2 et n'ont, à
`d ≤ 5`, que des voisines à élévation **4** ; les quatre acceptées ont toutes une voisine proche à
écart `≤ 1`. **Séparation parfaite** — et ce n'est PAS un ajustement sur six points :
`IdunBattle.Core.Services.BattleQuery$$GetFreeAdjacentTiles` = `GetAdjacentTiles(from,
onlyEmptyOrSteppable: 1, onlyWalkableTiles: 1)` filtré en place, dont l'itérateur
`IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext` applique — APRÈS
les gardes de walkability — un gate inconditionnel **`|srcElev - tile.Elevation| < 2`**.

Le foyer porté existait déjà : **`engine.battle_query.is_adjacent`** (#124). Surtout PAS
`are_entities_adjacent`, qui mirrore `MovementUtil$$AreTilesAdjacent` et porte un court-circuit
d'IDENTITÉ (#433-r1) — il compterait la cible comme sa propre voisine.

## 7.4 Ce qui est porté

`ability_range_value` compose désormais **deux étages nommés** :
`tiles_in_range_reach` (= `GetTilesInRange`, borne supérieure) puis `dynamic_target_gate_reach`
(= ce que le prédicat laisse subsister). `is_tile_in_range_of_any_ability` accepte `elev_by_pos` et
décide **par ability, sur la TUILE** ; `early_warning_override` lui passe `ctx.elev_by_pos`, qu'il
possédait déjà. Sans canal, dégradation NOMMÉE sur `config.range + 1` (borne supérieure : 2 faux
positifs sur 40 mesurés, 0 avec le canal).

Le régime `GATE_NOT_DERIVABLE` rend `None` **seulement** quand la base est `WHOLE_BOARD_REACH` :
c'est le seul cas où la borne supérieure est inutilisable (verser le plateau ferait 40 faux positifs
sur `astraDreir` là où `None` en fait 0). Une base bornée survit au gate non dérivable — sans quoi
les **15** abilities non-whole-board qui surchargent disparaîtraient d'un coup de la zone.

## 7.5 Résultat, et ce qui reste

**Six kits, EXACTS 40/40 dans les deux sens** (sweep `d = 2..10`, un seul ennemi vivant) :

| kit | avant | après |
|---|---|---|
| `bloodDante` (`LightOfSanguinius`) | 18 FN / 0 FP | **0 / 0** |
| `bloodIntercessor` (`HammerOfWrath`) | 18 FN / 0 FP | **0 / 0** |
| `darkaAsmodai` (`ExemplarOfHate`) | 40 FN / 0 FP | **0 / 0** |
| `tauMarksman`, `astraDreir`, `custoBladeChampion` | 0 / 0 | **0 / 0** |

Les trois premiers sont **discriminants** : arme de MÊLÉE seule, donc « zone = portée d'arme »
y donnerait 1 — l'accord ne peut pas venir d'une coïncidence de modèles.

**Résidus rouverts par cette tranche, nommés :**

* **`-r1-r1-a` — 11 des 19 gates whole-board restent NON LUS** (`GATE_NOT_READ`), plus ~30 gates
  d'abilities non-whole-board. Le port ne rétrécit pas sur eux : c'est le statu quo, donc une borne
  SUPÉRIEURE sur cet étage — un gate restrictif non lu produirait des faux positifs. Aucun n'est
  mesuré à ce jour ; les lire est un travail de volume, pas d'enquête.
* **`-r1-r1-b` — `onlyEmptyOrSteppable` / `onlyWalkableTiles` ne sont pas modélisés.** Le port ne
  retire pas les voisines OCCUPÉES ni non walkables, faute de canal côté DÉCISION ; l'écart ne peut
  qu'ÉLARGIR. **Point d'ancrage** : publier la walkability et l'occupation par tuile dans le canal
  que `decisionView` fournit déjà pour l'élévation.
* **`-r1-r1-c` — les gates en AMONT** (`CanCurrentlyBeUsed` slot `0x14`, `IsAbilityBlocked` slot
  `0x13`, `AttackQuery$$GetInvalidCasterReason`) peuvent retirer une ability ENTIÈRE (cooldown,
  ammo, caster ayant bougé). Non modélisés — ils n'ont mordu sur aucun des six kits mesurés.
