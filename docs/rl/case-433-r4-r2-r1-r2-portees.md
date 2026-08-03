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

* **`#433-r4-r2-r1-r1` — la zone d'une ability `UseWholeBoard` n'est pas dérivable.** `LightOfSanguinius`
  et `LeadingTheCharge` partagent le **même** preset (`TargetingOptions statics+0x240`, donc le même
  `TargetingRange` *et* le même masque `Rules = 0x102004032`) et rendent pourtant des zones
  DIFFÉRENTES (≈5 contre 1) : le discriminant est **en aval** du `TargetingRange` — un des gates
  d'ability, ou le slot `10`, ou un override de `GetPossibleTargetTiles` (les corps triviaux étant
  dédoublonnés, son absence des tables ne prouve rien). Le port ne l'élargit pas → **borne
  INFÉRIEURE**, 0 faux positif mesuré, 18 faux négatifs sur `bloodDante`. Dégradation **permissive**
  (le port attribue `+50` là où le natif n'en donne pas). *Candidat `fable-solver`* : RE de
  `GetPossibleTargetsForOptions` + des gates de `GetAllTilesInAbilityRange`.
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
* **NON COUVERT** — les kits dont la zone dépend d'un `UseWholeBoard` (cf. `-r1-r1`) ; les unités
  MULTI-HEX (cf. `-r1-r3`) ; les abilities actives des unités HORS pool spawnable (npc, summons),
  dont le `TargetingRange` n'est pas dans la table : elles retombent sur la portée d'arme, ce qui
  est le cas natif majoritaire mais pas une garantie.
