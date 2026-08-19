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
* **`#433-r4-r2-r1-r2` — FERMÉ (2026-08-04).** Le LoS/élévation retirait des tuiles du disque : le
  natif excluait **une** tuile à `d = 4` que ses voisines de même distance contenaient (1/34 sur
  relief, 0/40 sur le montage plat du même kit). L'étage est le **2ᵉ prédicat** de
  `GetPossibleTargetsForOptions`, et il n'est gaté par AUCUN bit — les `AllowObscuredTargetBy*`
  décident de ce qu'il REGARDE, pas s'il tourne. Détail, géométrie (ni `ConnectivityComponent` ni
  `boardGraph.neighbours` : des lignes de COORDONNÉES) et mesures :
  **`docs/rl/case-433-r4-r2-r1-r2-ligne-de-vue.md`**.
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
abilities `UseWholeBoard` du port surchargent, **13 non**.

⚠ « Ne surcharge pas » n'implique pas « zone = plateau entier » : deux étages **en amont** peuvent
la vider ou la trouer, et `-r1-r1-a` les a lus — le court-circuit `TargetIsFriendly` de
`GetPossibleTargetTiles` (qui vide la zone de `1187` et `1214`, pourtant sans gate) et
l'obscurcissement du 2ᵉ prédicat.

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

* **`-r1-r1-a` — FERMÉ (2026-08-04).** Le compte était **9**, pas 11 : les deux gates dérivables
  ci-dessus étaient comptés deux fois. **Aucun des neuf n'est un rayon**, et leur lecture a fait
  apparaître deux autres étages — le court-circuit `TargetIsFriendly` sans `TargetIsEnemy` de
  `GetPossibleTargetTiles` (zone VIDE, exacte) et le régime « valide sur tuile libre ».
  Détail, mesures et résidus : **`docs/rl/case-433-r4-r2-r1-r1-a-gates-whole-board.md`**.
  `GATE_NOT_READ` ne subsiste que sur des abilities **non-whole-board**, dont la borne reste bornée.
* **`-r1-r1-b` — `onlyEmptyOrSteppable` / `onlyWalkableTiles` ne sont pas modélisés.** Le port ne
  retire pas les voisines OCCUPÉES ni non walkables, faute de canal côté DÉCISION ; l'écart ne peut
  qu'ÉLARGIR. **Point d'ancrage** : publier la walkability et l'occupation par tuile dans le canal
  que `decisionView` fournit déjà pour l'élévation.
* **`-r1-r1-c` — les gates en AMONT. FERMÉ (2026-08-04), §8 ci-dessous.** Les deux slots y étaient
  **mal nommés** : ce sont `AActiveAbility$$CanStillBeUsed` (0x14) et `AActiveAbility$$IsDisabled`
  (0x13). Ils n'avaient mordu sur aucun des six kits parce qu'aucun montage ne les armait — un
  montage qui les arme fait tomber la zone de `darkaTerminator` de **3 à 1** et celle de
  `tauMarksman` de **5 à 3**.

---

# 8. `#433-r4-r2-r1-r1-c` — les TROIS gates CASTER, en amont de la zone

**Verdict : FERMÉ.** Les trois gates sont portés. Deux résidus nommés en sortent (§8.5).

## 8.1 La chaîne, LUE — et les deux noms que la fiche donnait FAUX

`IdunBattle.Core.Services.AttackQuery$$GetAllTilesInAbilityRange`, surcharge à **quatre** arguments
`(unit, position, ability)` — l'étage PAR ABILITY, sous lequel passe chaque entrée de
l'`ActiveAbilityComponent` :

```
impl = <this.abilities @+0x18>.<slot 0>(ability.<AbilityName @+0x44>)
if (!impl.<IActiveAbility slot 0x14>(unit, ability.<AmountOfTimesAlreadyUsed @+0x10>)) -> VIDE
if ( impl.<IActiveAbility slot 0x13>(unit))                                            -> VIDE
if (AttackQuery.GetInvalidCasterReason(unit, position, ability.AbilityName).IsInvalid()) -> VIDE
tiles = impl.<slot 9>(unit, position.MainTile) U impl.<slot 10>(unit, position.MainTile, tiles9)
```

L'appelant est `AttackQuery.u003Cu003Ec__DisplayClass39_1$$u003CGetAllTilesInAbilityRangeu003Eb__0`,
qui **énumère l'`ActiveAbilityComponent` ENTIER** ; `includeNormalAttack` ne fait que LEVER le
filtre `!IsRegularAttack`. **L'attaque normale n'est donc pas un cas à part : elle passe par les
mêmes trois gates.**

**Les deux slots, re-dérivés.** `IdunBattle.Operations.AddMachineOperation$$InitializeAbilitiesStatus`
s'en sert pour INITIALISER deux champs de `IdunBattle.Entities.Components.ActiveAbility`, et ces
champs portent leur nom dans les métadonnées IL2CPP (résolus PAR NOM par
`frida/hooks/features/ai-step/internals.ts`) :

```
comp.<CanStillBeUsed @+0x28> = impl.<slot 0x14>(unit, comp.<AmountOfTimesAlreadyUsed @+0x10>)
comp.<IsDisabled    @+0x35> = impl.<slot 0x13>(unit)
```

⇒ slot `0x14` = **`AActiveAbility$$CanStillBeUsed(caster, amountOfTimesAlreadyUsed)`** (2 paramètres,
et le 2ᵉ est bien `comp+0x10` — `ResetActiveAbilityOperation$$Execute` écrit d'ailleurs
`comp+0x10 = 0` et `comp+0x28 = 1` ENSEMBLE) ; slot `0x13` = **`AActiveAbility$$IsDisabled(caster)`**
(1 paramètre). Les deux noms de la fiche héritée existent mais ne sont **ni l'un ni l'autre** un slot
de cette interface : `ActiveAbility$$get_CanCurrentlyBeUsed` est une **propriété du composant**, lue
plus bas (marche d) ; `UnitExtensions$$IsAbilityBlocked` est une **autre fonction** (elle lit
`ActiveAbilityComponent.NormalAttackIsBlocked` / `ActiveAbilitiesAreBlocked` /
`MachinePrimaryAbilityIsBlocked`).

⚠ Et ce n'est **pas** une déduction d'absence : ses **six** appelants sont ÉNUMÉRÉS
(`list_xrefs`) — `ActiveAbilityOperation$$ExecuteInternal`,
`UpdateActiveAbilityBlockerOperation$$SendUpdateAction`,
`AttackQuery$$CanAttackAnyUnitFromAnyTileWithAnyAbility`,
`AttackQuery$$MachineCanAttackAnyUnitWithAnyAbility`,
`AActionGenerator$$CanAbilityBeUsed` et
`RandomAbilityActionGenerator.u003CGenerateActionsu003Ed__5$$MoveNext`. Ni
`GetAllTilesInAbilityRange` ni `AttackQuery$$GetInvalidCasterReason` n'y figurent. C'est un gate
FRÈRE (celui des générateurs d'action de l'IA), pas celui-ci — et le foyer qui le porte existe
déjà : `engine.battle_query.can_use_ability`.

## 8.2 L'ORDRE, et le rang de ce qui était déjà porté

`AttackQuery$$GetInvalidCasterReason(unit, attackerPosition, activeAbilityType)` est lui-même une
cascade ordonnée :

| # | condition | raison |
|---|---|---|
| a | `unit == null` | `broken(1)` |
| b | `IsMultiTileUnit(unit, state) && !HasTrait(unit, 0x418 Stationary)` | `broken(1)` |
| c | `ActiveAbilityComponent` absent, ou `GetOrNull(type) == null` | `broken(1)` |
| d | `!aa.CanCurrentlyBeUsed` | `broken(1)` |
| e | `aa.AbilityName == 0` | `broken(1)` |
| f | `IsAlreadyUsedThisTurn(type, aa)` | `broken(1 << 54)` |
| g | sinon → `AActiveAbility$$GetInvalidCasterReason` → **`TargetingQuery$$GetInvalidCasterReason`** | |

**La marche (g) est ce qui était DÉJÀ porté** (`engine.runner.abilities.targeting.
get_invalid_caster_reason`, face RUNNER) : tout ce cas est donc **en amont** de lui.
`ActiveAbilityOperation$$IsInvalidTarget` (porté, face COMBAT) est un **autre pipeline** — celui de
l'exécution d'un cast, pas celui de la zone.
`IBrokenTargetingRuleExtensions$$IsInvalid(rule)` = `rule.<slot 0>() != 0` : « invalide » vaut
exactement « raison non nulle ».

## 8.3 Ventilation — dérivable, non dérivable, inatteignable

Le canal `decisionView.units[].abilities[]` (`allAbilities: true`) publie, **pour toute unité des
deux camps**, les cinq champs que `readAbilityState` lit PAR NOM : `usable` ← `CanStillBeUsed@0x28`,
`disabled` ← `IsDisabled@0x35`, `cooldown` ← `RemainingCooldownTurns@0x2c`, `ammoCost` ←
`AmmoCost@0x38`, `hasAmmo` ← `HasEnoughAmmo@0x40`.

| gate | verdict |
|---|---|
| 1 — slot `0x14` | **PORTÉ** par le champ `usable` (la valeur que la méthode a écrite) |
| 2 — slot `0x13` | **PORTÉ SANS AUCUN CANAL** : `StaticBattleRules.ActiveAbility$$IsDisabled` = `IsRegularAttack(type) ? false : (nrOfTargets < 1, sinon nrOfHits < 1)` — du kit gameconfig pur |
| 3d | **PORTÉ**, par délégation au foyer déjà posé `engine.battle_query.can_currently_be_used` |
| 3b | **INATTEIGNABLE par cette voie** : `IsTileInRangeOfAnyAbility` court-circuite sur `GetFeetCount > 1`, qui est le prédicat d'`IsMultiTileUnit` — une unité multi-tuiles n'atteint jamais ce gate |
| 3c | hors périmètre : c'est la LISTE des abilities, substrat inchangé |
| 3f `IsAlreadyUsedThisTurn` | **NON DÉRIVABLE, borne EXPLICITE, sens PERMISSIF.** Il lit `ActiveAbility.<Nullable<int> @+0x20>` contre `TurnComponent.GetAmountOfTurnsEnded(null)` ; aucun canal ne publie ce champ. **Point d'ancrage** : l'ajouter à `readAbilityState`, à côté des cinq déjà lus (exige une fenêtre de reinject) |
| 3g | face RUNNER seulement (consomme un `State`) |

**Le gate 2 est porté et son gisement est VIDE**, et c'est une mesure : sur les **175** abilities
actives distinctes du gameconfig, **0** sont disabled (3 portent `nrOfTargets`, 110 `nrOfHits`,
toutes `>= 1`). Chiffres re-dérivables : `probe_433_r4_r2_r1_r1_c_caster_gates.py --step inventaire`.

**Non mesuré ≠ faux.** Canal absent → les gates 1 et 3 rendent `None` et l'appelant ne gate pas :
statu quo, borne SUPÉRIEURE. Le gate 2, lui, répond toujours.

**Anti-fork.** `get_CanCurrentlyBeUsed` avait DÉJÀ un mirror côté DÉCISION
(`engine.battle_query.can_currently_be_used`, posé par le lot MoW-ammo). Le module de gates le
**délègue** et n'y ajoute que le tri-état ; un test garde la délégation (pas l'égalité des valeurs —
deux corps identiques aujourd'hui divergeraient demain).

## 8.4 La mesure — DEUX bras, DEUX kits, DEUX gates différents

Le discriminant est énoncé **avant** : il faut un bras où l'ability est réellement bloquée **et** un
témoin où elle ne l'est pas — sans le second, un port qui refuse tout passerait aussi.

| kit | arme | ability | gate armé par | natif bloqué → témoin | port |
|---|---|---|---|---|---|
| `darkaTerminator` | mêlée 1 | `PlasmaCannon` (1150), zone 3 | `constants.initialCooldownTurns = 1` → marche **d** (`RemainingCooldownTurns`) | **1 → 3** | 1 → 3 |
| `tauMarksman` | distance 3 | `SeekerMissileFrequencyLock` (1069), zone 5 | un CAST → **slot 0x14** (`cooldown` reste `null`) | **5 → 3** | 5 → 3 |

Même runner, même tuile ennemie, même sweep (38 positions) ; seul l'état de l'ability change.
Les trois ports imaginables se séparent sur **chaque** kit : correct `1→3` / `5→3` ; « ne gate
jamais » `3→3` / `5→5` ; « gate tout » `1→1` / `3→3`. Et le régime n'est **pas dégénéré** — « zone =
portée d'arme » est faux sur les deux témoins (3 ≠ 1 et 5 ≠ 3).

Sur `darkaTerminator`, le bras bloqué passe de **12 faux positifs sur 38 à 0 / 0, EXACT**.
Le second kit est ce qui interdit d'attribuer l'accord à un seul mécanisme : le premier est gaté par
le **cooldown** (`usable` reste `true`), le second par **`CanStillBeUsed`** (`cooldown` reste `null`).

**CONTRE-ÉPREUVE, jouée dans le test sur la mesure déjà prise** : on rejoue le bras bloqué avec le
port PRIVÉ de son canal — le port d'AVANT cette tranche — et on exige qu'il sur-couvre. Sans elle,
« mon gate marche » ne se distingue pas de « le montage ne gate rien ».

## 8.5 Ce qui est porté, et ce qui reste

**Porté** : `engine/services/ability_caster_gates.py` (les trois gates, dans l'ordre natif, chacun
nommé par son symbole) ; `engine/services/ability_range.py` les consomme dans `unit_threat_reach` et
`is_tile_in_range_of_any_ability` (paramètres `ability_state` / `normal_attack_id`, cache
court-circuité dès qu'un état est fourni) ; `EarlyWarningOverridePlaybook.enemies_of` alimente le
canal depuis la ligne `decisionView` de chaque ennemi.

**Validation** — offline `tests/engine/test_433_r4_r2_r1_r1_c_caster_gates_offline.py` : **27
passed** (ordre des trois gates, ordre des deux constantes d'`IsDisabled`, tri-état, anti-fork,
non-contamination du cache, attaque normale, gisement vide). Live
`test_433_r4_r2_r1_r1_c_caster_gates_live.py` : **13 passed** (les 2 bras × 2 kits, la propriété
« un gate ne peut que RETIRER », l'anti-dégénérescence et la contre-épreuve).
Non-régression rejouée après rebase : `test_433_r4_r2_r1_r2_ability_range_offline`,
`test_433_r4_r2_r1_r1_dynamic_target_gate_offline`, `test_433_r4_r2_adjacency_foyer_offline`,
`test_nc_priority_tiers_offline` (**79 offline** au total), et **40 live**
(`test_433_r4_r2_r1_ability_range_live` 6, `test_433_r4_r2_adjacency_foyer_live` 7,
`test_356_noncomparable_oracle_live` 14, + les 13 de la tranche).

**Résidus NOMMÉS :**

* **`-r1-r1-c-r1` — `IsAlreadyUsedThisTurn` non dérivable.** Marche (f) de
  `AttackQuery$$GetInvalidCasterReason`, sens PERMISSIF (le port garde une ability que le natif
  retirerait le tour de son usage). **Point d'ancrage** : publier
  `components.ActiveAbility.<Nullable<int> @+0x20>` dans `readAbilityState` — capteur à écrire,
  fenêtre de reinject requise.
* **`-r1-r1-c-r2` — le canal n'est peuplé que si l'appelant demande `allAbilities: true`.** Sans
  lui, `unitAbilityTypes` n'émet que l'attaque NORMALE (sans état) : les gates 1 et 3 deviennent
  « non mesurés » et la zone repasse à la borne supérieure — silencieusement. Les consommateurs de
  production qui le demandent déjà : `engine_validate.py`, `probe_433_*`. À recenser et à rendre
  uniforme.
* **Les faux positifs RÉSIDUELS des deux témoins** (≤ 2 par bras) ne sont **pas** de ce cas : ni
  `PlasmaCannonAbility` ni `SeekerMissileFrequencyLockAbility` ne surchargent `klass+0x478`
  (égalité du pointeur de slot avec `AActiveAbility`, lue au runtime) — c'est `-r1-r1-r2`
  (2ᵉ prédicat de `GetPossibleTargetsForOptions`, tuiles obscurcies). Le test garde qu'ils ne
  s'aggravent pas **et** que le bras bloqué n'en crée aucun nouveau.

## 9. `#433-r4-r2-r1-r1-c-r1` — le capteur `IsAlreadyUsedThisTurn`, écrit (#466), NON CONFRONTÉ

Le résidu était bloqué sur un **capteur**, pas sur une question ouverte. Il est écrit.
**Aucune ligne de §9.3 n'est une mesure du capteur** : rien n'a tiré, faute de fenêtre de reinject.
§9.1 et §9.2 sont, elles, des lectures — décompilé et métadonnées IL2CPP du build vivant.

### 9.1 Le corps natif, relu — et la marche dont le SENS était donné à l'envers

`IdunBattle.Core.Services.AttackQuery$$IsAlreadyUsedThisTurn(this, activeAbilityType, activeAbility)`,
lu verbatim sur `rnca9r7q6c` :

```csharp
if (this.<+0x10> != 0)                                              return false;   // court-circuit
if (StaticBattleRules.ActiveAbility.IsRegularAbilityType(activeAbilityType)) return false;
if (activeAbility == null)                                          throw;
if (!activeAbility.<Nullable<int> @+0x20>.HasValue)                 return false;
turnsEnded = TurnComponent.GetAmountOfTurnsEnded(
                 StateExtensions.GetMatchTurn(this.<+0x20>), 0);
return hasValue && (value == turnsEnded);
```

⚠ **Le sens de la 2ᵉ marche** : le corps est gardé par `if ((char)IsRegularAbilityType(...) == '\0')`,
donc le natif rend `false` **quand le type EST une attaque régulière** — une attaque normale n'est
jamais « déjà utilisée ce tour ». La fiche héritée l'énonçait dans l'autre sens ; c'est lu, pas
déduit du nom, et ça compte pour le consommateur (le gate ne doit jamais retirer l'attaque normale).

### 9.2 Le NOM du champ `@+0x20` — mesuré, parce qu'il n'était pas dérivable

Aucun symbole ne l'expose (`$$ToString` ne le touche pas, `$$Copy` est un `MemberwiseClone`), et
`data/symbols/<build>/frida/classes.tsv` ne porte **aucun** offset de champ. Il a donc été lu au
RUNTIME, par le RPC `classFields("IdunBattle.Entities.Components", "ActiveAbility")` :

| offset | nom | type |
|---|---|---|
| `0x10` | `AmountOfTimesUsed` | `Int32` |
| `0x14` | `TotalUsageCount` | `Int32` |
| `0x18` | **`LastTurnUsed`** | `Nullable<int>` |
| `0x20` | **`UnresetedLastTurnUsed`** | `Nullable<int>` |
| `0x28` | `CanStillBeUsed` | `Boolean` |
| `0x2c` | `RemainingCooldownTurns` | `Nullable<int>` |

⇒ le champ que lit la marche (f) est **`UnresetedLastTurnUsed`**. ⚠ Son voisin `LastTurnUsed`
@`0x18` est un AUTRE `Nullable<int>` du même composant : choisir entre les deux « au nom » aurait
été un coup de dé. **Les deux sont donc publiés**, pour que la fenêtre CONFRONTE lequel bouge quand
une ability est castée, au lieu de me croire sur parole.

La disposition `{ int value @+0 ; bool hasValue @+4 }` est LUE deux fois : les champs voisins
l'encadrent (`RemainingCooldownTurns` @`0x2c` suivi d'`IsInitialCooldown` @`0x34` = 8 octets), et le
décompilé copie les 8 octets de `+0x20` d'un bloc puis compare la moitié BASSE au compteur.

**Et le compteur n'était pas publiable non plus.** `decisionView.turn` est
`TurnComponent$$GetAmountOfTurnsStartedByCurrentPlayer` — relu : `dict<+0x38>[currentPlayerId]`.
`GetAmountOfTurnsEnded` lit `Sum(dict<+0x40>.Values)`. **Deux dictionnaires, deux agrégations** :
`turn` ne peut donc pas servir de substitut, et publier le champ sans le compteur aurait laissé la
question indécidable côté moteur. C'est une lecture, pas une précaution de style.

### 9.3 Ce qui est livré

* `frida/hooks/features/ai-step/internals.ts` — `readAbilityState` publie
  `unresetedLastTurnUsed` / `unresetedLastTurnUsedHasValue` **et** `lastTurnUsed` /
  `lastTurnUsedHasValue`, en **TRI-ÉTAT** : `…HasValue === null` = **PAS MESURÉ** (offset non
  résolu ou lecture en faute), `false` = mesuré et vide, `true` = mesuré avec valeur. La valeur est
  **BRUTE** (le tour), jamais un booléen pré-calculé : la comparaison au compteur appartient au
  moteur, qui doit pouvoir la refaire à l'identique du natif — y compris la marche
  `IsRegularAbilityType`, qui n'est pas dans ce champ.
* Même fichier — `readTurnsEnded(state)` : trouve le `TurnComponent` comme le fait
  `StateExtensions$$GetMatchTurn` (premier porteur du composant, sans présupposer l'entité `Match`)
  puis **invoque la méthode nommée** `TurnComponent$$GetAmountOfTurnsEnded`. `null` = pas mesuré,
  jamais `0` (qui est un tour légitime, et le confondre ferait répondre « utilisée ce tour » à
  toute ability dont le Nullable vaut `0`).
* `decisionView` — `turnsEnded`, plus `abilityStateLayout` / `turnsEndedLayout` (ce que le capteur a
  RÉSOLU, avec les littéraux du décompilé à côté pour diagnostic). `unitAbilityStates` porte les
  mêmes `turnsEnded` / `turnsEndedLayout` : le canal qui porte l'état d'ability doit porter
  l'échelle à laquelle il se compare.
* **Résolution par NOM sans repli littéral** (contraste voulu avec `fieldOffsetOr`) : un nom absent
  au prochain build rend « pas mesuré », jamais la lecture d'un offset devenu celui d'un autre champ.
* **Aucun gate n'est branché.** `ability_caster_gates` reste à trois marches ; ajouter la marche (f)
  change un résultat observable (elle est RESTRICTIVE : elle retire une ability), donc c'est
  spéculatif tant que la mesure n'a pas eu lieu.

# 10. `#433-r4-r2-r1-r2-r2-r1-r1-r1-r4` — le QUATRIÈME gate CASTER, et le préfixe qui manquait

## 10.1 Ce que c'est

La marche **(g)** d'`AttackQuery$$GetInvalidCasterReason` (§8.1) n'est pas une clause de plus :
c'est un appel à **`IdunBattle.Core.Services.TargetingQuery$$GetInvalidCasterReason`**, qui porte à
elle seule **onze** règles. Chaîne relue à l'octet :

    AttackQuery$$GetInvalidCasterReason(unit, position, type)      [marche g]
      -> <processor @+0x30>( () => impl.<IActiveAbility slot 8>(unit, position.MainTile) )
      -> AActiveAbility$$GetInvalidCasterReason(caster, casterTile)
           caster == null -> GenericBrokenTargetingRule(1)
           SetConfigValuesInTargetingOptions(this, &this.<TargetingOptions @+0x70>)   // n'écrit
                                                          // que `+0x10` (range), JAMAIS `rules`
           -> TargetingQuery$$GetInvalidCasterReason(caster, casterTile, options)  // surcharge TUILE
      -> surcharge TUILE : `casterTiles = TExtensions.ToList(casterTile)` — un SINGLETON
      -> surcharge LISTE : la cascade des onze règles.

Les deux voies de retour (`il2cpp_value_box` direct et `TargetingRuleExtensions$$
GenericBrokenTargetingRule`) boxent **le même type** : aucune ne transforme le code.

Le port est `engine/services/ability_caster_gates.py` (section GATE 4) —
`invalid_caster_reason` / `CasterSubstrate` / `dynamic_caster_reason`, composés par
`caster_gate_reason` **au 4ᵉ rang**, après les trois gates de §8.

## 10.2 Le bug : `CasterHasNotMoved` était porté SANS son préfixe

Le décompilé garde la clause 1 derrière `<IBattleQuery slot 0x35>(caster)`, que le port déclarait
« non résolu » et portait comme **toujours vrai**. Le slot **est** résoluble : le seul autre site du
binaire qui invoque ce couple (slot, classe d'interface) est la lambda
`IdunBattle.Core.Services.RecordedSimulationRequestsBattleQuery.u003Cu003Ec__DisplayClass86_0$$
u003CIsTurnOfUnitu003Eb__0` — son **nom** donne la méthode.

    battleQuery.IsTurnOfUnit(caster)
      = GetOriginalOwnerEntity(GetUnit(caster)).Id == GetMatchTurn(state).CurrentPlayerId

Préfixe faux ⇒ le port refusait **11 paires sur 42** que le natif accepte (unité ayant bougé mais
dont ce n'est pas le tour). Écart **RESTRICTIF**, et le pire possible ici : le consommateur côté
DÉCISION (`is_tile_in_range_of_any_ability`) évalue la menace des unités **ENNEMIES**, c'est-à-dire
exactement celles dont ce n'est pas le tour. `CasterSubstrate.is_turn_of_unit` (tri-état) le porte.

⚠ **Ne pas le confondre avec `decisionView.units[].ctrl`** (`UnitExtensions$$
IsControlledByCurrentPlayer`), qui lit `OwnerComponent.CurrentPlayerEntityId` : `IsTurnOfUnit` lit
le propriétaire d'**ORIGINE**. Les deux divergent sous contrôle mental.

## 10.3 Les deux canaux — ils EXISTENT, contrairement à ce que le module affirmait

* `has_moved` — `UnitExtensions$$DidMove` = `GetComponent<UnitFlagsComponent>(unit).Has(UnitFlag.Moved)`
  après un `Type == Unit` ; `UnitFlag.Moved` = **0** (`enums.tsv`, re-confronté au runtime par
  `combatSnapshot.unitFlagTypes`). Publié par **`combatSnapshot.units[].unitFlags`**.
* `is_turn_of_unit` — `observeBattle.units[].playerId` (= `OwnerComponent.PlayerEntityId`,
  l'ORIGINE) == `observeBattle.currentPlayer` (= `TurnComponent._currentPlayerId`, celui-là même
  que le natif compare).

Le probe les nourrit ; `is_tile_in_range_of_any_ability` **non** (résidu §10.6).

## 10.4 Le gisement, re-dérivé des 148 masques

`AllowNullCasterTile` 18 · `CasterHasNotMoved` 13 · `CasterMatchesDynamicRule` 12 ·
`CasterHas2TurnsLeft` 3 · `CasterCanMove` 2 · `CasterHas1Tiles` 1 · `CasterIsMachine` 1 ·
`CasterHasCompletedOneTurn` / `CasterHasNoTile` / `CasterHas3Tiles` / `CasterHas7Tiles` **0**
(mirrors STRUCTURELS — écrits parce que le natif les a, gisement vide = résultat).

Règle-déléguée (`options+0x30`, bit `CasterMatchesDynamicRule`), 12 porteurs :
**1** dérivable (`1045 GetEmRuntz` → `GetSpawnTileSelector`, littéral **2**), **6** lues et non
dérivables hors état de bataille (1008, 1015, 1023, 1040, 1102, 1207), **5** dont la surcharge n'est
pas établie (1077, 1106, 1184, 1215, 1216 — l'absence du symbole ne prouve rien, IL2CPP déduplique).

## 10.5 La mesure (2026-08-05, build `rnca9r7q6c`)

`probe_433_r4_r2_r1_r2_r2_r1_r1_r1_r4_caster_reason.py`, trois volets :

| volet | montage | résultat |
|---|---|---|
| `live` | `MC1_67`, seed 777, `orksRuntherd` + 3 `necroWarden` vs 2, caster APPROCHÉ pas à pas | **13 tours comparables, MORD=8 PASSE=5** ; étage natif == port **13/13** ; zone exacte (fp imputables 0, fn 0) ; gate efficace sur 2 tours (retire (2,0) puis (1,0), **tous deux faux positifs**) ; résidu 5 tuiles, **toutes** attribuées au terme d'attaque normale (`fp == fp_normale`) |
| `cascade` | 10 unités choisies pour couvrir les règles à gisement non nul, 2 passes/tour (posé / bougé) | **60 paires, 60 EXACT, 0 refus inventé** — contre **49/60 + 11 refus inventés** avant le correctif du préfixe |
| `moved` | `bloodDante` / `1177`, avant/après déplacement | natif `CasterHasNotMoved`, port `CasterHasNotMoved`, et **sans le bit du masque le port ACCEPTE** (contre-épreuve) |

⚠ **Le régime PASSE n'est atteignable qu'en DÉPLAÇANT le caster** : `endturn` seul ne fait pas
avancer l'adversaire (les deux `necroWarden` restent à (6,7)/(6,8) sur 10 tours) et le Runtherd
spawne à `d = 10`, alors que le gate ne s'ouvre qu'à `d <= 2`. Bouger est licite : le masque `0x8004`
de `1045` ne porte pas `CasterHasNotMoved`.

Gardes : `tests/engine/test_433_r4_r2_r1_r2_r2_r1_r1_r1_r4_caster_reason_offline.py` (31 crans —
ORDRE de la cascade sur masques craftés, préfixe en tri-état, sélecteur de spawn ; **rougit 3/31**
quand on retire le préfixe, contre-épreuve jouée) et `..._live.py` (9 crans, les volets `cascade` +
`moved`).

⚠ **L'ORDRE n'est observable dans AUCUN montage live** : sur les 148 masques, aucune ability n'arme
deux règles CASTER à la fois. Il est donc gardé sur des masques **craftés** — c'est une propriété du
CODE, pas du catalogue.

## 10.6 Résidus

* **`#433-r4-r2-r1-r2-r2-r1-r1-r1-r4-r1`** — `has_moved` / `is_turn_of_unit` ne sont pas branchés
  dans `is_tile_in_range_of_any_ability`, donc la règle `CasterHasNotMoved` (13 porteurs) reste
  INERTE par le chemin ZONE. Les deux canaux existent (§10.3) mais vivent côté RUNNER
  (`combatSnapshot`) / dans `observeBattle`, et `NCContext` — l'appelant de production, dans
  `engine/playbook/noncomparable/early_warning_override.py` — ne les transporte pas. **Point
  d'ancrage** : les ajouter à `NCContext` puis les passer en paramètres de
  `is_tile_in_range_of_any_ability`, comme `team_by_pos` / `walkable_by_pos` l'ont été.
* **`#433-r4-r2-r1-r2-r2-r1-r1-r1-r4-r2`** — huit des onze règles ne sont confrontées par AUCUN
  montage. Quatre ont **0 porteur** (mirrors structurels) ; `CasterCanMove` (2) lit
  `UnitExtensions$$CanMove`, `CasterHas2TurnsLeft` (3) le slot `IBattleQuery 0x1b` et
  `CasterIsMachine` (1) est porté par une MoW (donc inerte chez son seul porteur) — aucun canal
  DÉCISION ne publie les trois premiers, et le volet `cascade` ne balaie que des UNITÉS (les MoW
  vivent dans `observeBattle.mows`). `AllowNullCasterTile` (18) exigerait un caster sans tuile.
* Les **6+5 régimes** de la règle-déléguée (§10.4) restent non portés : le port ne refuse pas —
  écart PERMISSIF nommé, jamais restrictif.

### 9.4 PLAN DE MESURE — ce que la fenêtre doit jouer, et ce que chaque résultat tranche

Prérequis : reinject + `autoBootExtraire({force:true})`. Montage = celui de §8.4, bras
`tauMarksman`, **le seul qui casse une ability par un CAST** (et non par un cooldown initial) :

```
python rl_duel.py build --seed 777 --board MC1_67 \
  --p-units "tauMarksman,necroWarden" --a-units "templAggressor,eldarRanger" \
  --state-file <ABSOLU unique>
# T0 : decisionView { runnerId, allAbilities: true }
# puis act ability --caster <tauMarksman> --target <ennemi> --ability 1069
# T1 : decisionView (MEME tour) ; act endturn x2 ; T2 : decisionView (tour suivant)
```

| # | mesure | résultat attendu | ce qu'un ÉCART trancherait |
|---|---|---|---|
| 1 | `abilityStateLayout.classResolved` + `unresetedLastTurnUsed` / `lastTurnUsed` | `true`, `0x20` et `0x18` — égaux aux `decompiled*` publiés à côté | un `-1` ⇒ le nom n'existe plus : le capteur rend « pas mesuré » (c'est voulu), et il faut re-lire la disposition avant tout. Un offset ≠ ⇒ la disposition a bougé : **rien des crans 3-7 n'est interprétable** |
| 2 | `turnsEndedLayout` + `decisionView.turnsEnded` à T0 | `methodResolved: true`, `turnsEnded` **entier**, et `paramClass` publié tel quel | `turnsEnded: null` ⇒ méthode non résolue ou aucun porteur du composant : capteur inopérant sur cette moitié, et le résidu reste ENTIER. Si `paramClass` n'est pas un `Int32`, le noter — l'argument est passé sur 8 octets à zéro, ce qui couvre aussi un `Nullable<int>` |
| 3 | `turnsEnded` vs `turn` sur la même réponse | **différents** au moins une fois dans la partie | toujours égaux ⇒ le montage ne les sépare pas (partie trop courte) : allonger, ne pas conclure que les deux compteurs coïncident — le décompilé dit le contraire (§9.2) |
| 4 | à **T0**, l'ability `1069` : `unresetedLastTurnUsedHasValue` | `false` (jamais utilisée) | `null` ⇒ cf. cran 1. `true` avec une valeur ⇒ l'état est hérité d'un montage précédent : repartir d'un runner neuf |
| 5 | **à T1 (même tour, après le cast)** : `unresetedLastTurnUsedHasValue == true` **et** `unresetedLastTurnUsed == turnsEnded` | **oui / oui** | c'est LE cran : il prouve que le champ porte bien « le tour où l'ability a été utilisée » et que l'échelle est celle de `turnsEnded`. Si `hasValue` reste `false`, le cast n'écrit pas ce champ ⇒ **c'est `LastTurnUsed` qu'il faut lire**, et le cran 6 le dit. Si `hasValue` est vrai mais la valeur ≠ `turnsEnded`, les deux ne sont pas dans la même échelle ⇒ ne PAS brancher le gate, re-ventiler |
| 6 | à T1, `lastTurnUsed*` — le voisin | bouge **aussi** (les deux sont écrits au cast) | seul `lastTurnUsed` bouge ⇒ le décompilé et la disposition se contredisent sur `+0x20` : **relire `IsAlreadyUsedThisTurn`** avant de porter quoi que ce soit. C'est exactement pourquoi les deux sont publiés |
| 7 | à **T2** (tour suivant) : `unresetedLastTurnUsed` inchangé pendant que `turnsEnded` a augmenté ⇒ `value != turnsEnded` | oui — l'ability redevient utilisable | si `unresetedLastTurnUsed` est REMIS à vide au changement de tour, le nom « Unreseted » est démenti : c'est alors `LastTurnUsed` qui est le champ non réinitialisé, et le rôle des deux est inversé. Trancher ici, pas après |

**Après la fenêtre, et seulement après** : ajouter la marche (f) à
`engine/services/ability_caster_gates.py` — **dans l'ordre natif** (après `CanCurrentlyBeUsed`,
avant la délégation à `TargetingQuery`), avec la garde `IsRegularAbilityType` et le tri-état
(`unresetedLastTurnUsedHasValue is None` ou `turnsEnded is None` ⇒ **ne pas gater**, borne
supérieure d'aujourd'hui). Puis rejouer
`test_433_r4_r2_r1_r1_c_caster_gates_live.py` et `test_433_r4_r2_r1_ability_range_live.py` : la
zone d'une ability castée CE tour doit rétrécir, et **aucune** zone d'attaque normale ne doit
bouger (c'est la contre-épreuve de la marche `IsRegularAbilityType`).

⚠ **Ce qui restera NON COUVERT même après la fenêtre** : le court-circuit `this.<+0x10>` de
`AttackQuery` (un champ du SERVICE, pas de l'ability — aucun canal ne le publie, et le port le
suppose faux), et `-r1-r1-c-r2` (le canal d'état n'existe que sous `allAbilities: true`), qui reste
entier et rend ce gate-ci silencieusement muet chez tout consommateur qui ne demande pas le drapeau.

### 9.5 LA FENÊTRE A TIRÉ (2026-08-04) — le capteur est MAL POSÉ, et le plan ne pouvait pas le voir

Le capteur a été confronté sur la session 3 (build `rnca9r7q6c`). **Crans 1 à 4 : conformes.
Cran 5 : ÉCART, et il accuse le capteur.**

| # | attendu | obtenu | verdict |
|---|---|---|---|
| 1 | `classResolved: true`, `unresetedLastTurnUsed = 0x20`, `lastTurnUsed = 0x18`, égaux aux `decompiled*` | **exactement ça** (`32` / `24`) | OK — et c'est le point : les offsets de CHAMP sont justes, le cran 1 est donc **structurellement aveugle** au défaut |
| 2 | `methodResolved: true`, `turnsEnded` entier, `paramClass` publié | `true`, `0`, **`Int32`** | OK |
| 3 | `turnsEnded` ≠ `turn` au moins une fois | `turn` = 3/4/3 pendant que `turnsEnded` = 0/3/4/6/… | OK, **et le motif n'est pas celui annoncé** : `turn` suit `currentPlayer`. `projectMatch` pose `turn: status.currentTurnPlayer` (= `TurnComponent._currentPlayerId`), pas `GetAmountOfTurnsStartedByCurrentPlayer` — §9.2 se trompait de fonction. La conclusion (« `turn` ne peut pas servir de substitut ») tient *a fortiori*. |
| 4 | à T0, `unresetedLastTurnUsedHasValue = false` | `false` (et `lastTurnUsed` idem) | OK |
| 5 | à T1, `hasValue = true` **et** `value == turnsEnded` | `hasValue = true`, `value = 1`, **`turnsEnded = 6`** | **ÉCART** |
| 6 | `lastTurnUsed` bouge aussi | il bouge, à la MÊME valeur (`1`) | conforme — et le décompilé dit pourquoi (cf. ci-dessous) |
| 7 | à T2, `unresetedLastTurnUsed` inchangé pendant que `turnsEnded` monte | inchangé (`1`) à `turnsEnded` 7 puis 9 | conforme en FORME, sans valeur puisque le cran 5 est faux |

**Le discriminant, énoncé avant la mesure** : un seul cast ne peut pas trancher, parce que sous la
disposition fausse ce qui sort en `value` est le bit `hasValue`, c'est-à-dire toujours `1` — et `1`
est un tour parfaitement plausible. Il faut **DEUX casts à deux compteurs distincts**, dans la même
bataille :

| cast | unité | ability | `turnsEnded` au cast | `unresetedLastTurnUsed` publié |
|---|---|---|---|---|
| 1 | `tauMarksman` | `1069` | **6** | **1** |
| 2 | `templAggressor` | `1048` | **19** | **1** |

Les deux écrivains sont lus verbatim et écrivent la MÊME expression dans les DEUX champs :
`IdunBattle.Operations.SetActiveAbilityUsedOperation$$Execute` et
`IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal` posent
`Nullable(TurnComponent.GetAmountOfTurnsEnded(StateExtensions.GetMatchTurn(state), 0))` dans
`LastTurnUsed@+0x18` **et** `UnresetedLastTurnUsed@+0x20` (ce qui explique le cran 6 : ils bougent
ensemble, à la même valeur, par construction). Et
`IdunBattle.Entities.Components.TurnComponent$$GetAmountOfTurnsEnded` =
`Sum(this.<Dictionary @+0x40>.Values) + turnsToAdd` est **monotone**. Deux casts séparés par des
tours terminés ne peuvent donc PAS avoir stocké la même valeur. ⇒ le champ publié n'est pas le tour.

**Cause : la disposition interne du `Nullable<T>`.** `readAbilityState` lisait
`{ int value @+0 ; bool hasValue @+4 }`. `System.Nullable`1` déclare `hasValue` PUIS `value`
(`classFields("System", "Nullable`1")`), et le décompilé le confirme deux fois :
`IdunBattle.Core.Services.AttackQuery$$IsAlreadyUsedThisTurn` prend l'octet `HasValue` sur
`fields[0]` et l'int comparé au compteur sur `fields[0] + 0x20` (= `fields[1]`), et
`IdunBattle.Entities.Components.ActiveAbility$$get_IsInCooldown` prend le sien sur `fields[0]`
aussi. Neuf autres sites du dépôt documentaient déjà `hasValue @+0` ; ce foyer-ci était **le seul à
l'inverse**, et `frida/hooks/features/effect-bonus-trace.ts` **nommait la contradiction sans la
trancher**.

**Rayon de souffle, dans le MÊME foyer** — `cooldown` (`RemainingCooldownTurns`) et `ammoCost` y
étaient lus à la même convention inverse, depuis toujours :

* le NOMBRE était faux — `cooldown` valait `1` pour tout cooldown non nul (c'est le bit `hasValue`
  qui sortait), donc `engine/runner/operations/ability_reset.py` (`remaining_cooldown > 1`, mirror
  d'`EntityCanHaveActiveAbilityReset`) ne pouvait **jamais** être vrai ;
* la PRÉSENCE, elle, coïncidait par accident : `value & 0xff != 0` équivaut à
  `HasValue && Value > 0` (= `get_IsInCooldown`) tant que la valeur tient sur un octet non nul.
  C'est ce qui explique qu'aucun test ne l'ait vu — et pourquoi le témoin de §8.4
  (`initialCooldownTurns = 1`) est **dégénéré** sur cet axe : `1` est justement la valeur où les
  deux dispositions coïncident.

Le `HasValue` du `Nullable<AbilityState>` (`OverrideAbilityState`, `+0xc` codé en dur) relevait de
la même supposition, symétrique.

**Livré** : `readNullableInt` résout désormais la disposition **par réflexion** (champ → type →
classe `Nullable`1` → offsets `hasValue`/`value`, moins le `0x10` de l'offset boxé) — le patron que
`frida/hooks/game/match-state.ts` applique déjà à `UnitComponent.DeathReason`. Non résolue ⇒
« PAS MESURÉ », jamais une lecture à une convention devinée. La disposition résolue est publiée
dans `abilityStateLayout.nullableLayout`. Cliquet offline :
`scripts/python/tests/test_579r1_nullable_layout_offline.py` (4 crans ; **rougit 4/4** sur la
version d'avant, contre-épreuve jouée). Probe de confrontation :
`scripts/python/probe_579_nullable_layout.py` (rc `0` fidèle / `1` infidèle / `2` non tranché,
avec refus explicite des deux régimes dégénérés : même compteur aux deux casts, ou compteur nul).

⚠ **Le correctif vit dans `frida/hooks`, donc il exige une NOUVELLE fenêtre de reinject.** Ce qui
est prouvé aujourd'hui : le bundle recompile (`frida-compile`, rc=0) et le cliquet offline tient.
Rien de plus. **La marche (f) n'est donc TOUJOURS PAS branchée** — son entrée n'est pas fiable, et
la brancher sur une valeur fausse serait pire que l'absence (elle est RESTRICTIVE).

**Ce que la fenêtre suivante doit jouer** : `probe_579_nullable_layout.py`, et exiger `rc=0`
(`value == turnsEnded` aux DEUX casts, à deux compteurs distincts et non nuls). Alors seulement
ajouter la marche (f) selon §9.4. À rejouer **aussi**, parce que le correctif les change :
`test_433_r4_r2_r1_r1_c_caster_gates_live.py` (le gate `cooldown` lit désormais la vraie valeur —
un `Nullable(0)` sort en `0` là où il sortait `null`, ce que `can_currently_be_used` traite
correctement via `cd >= 1`) et les tests de reset d'ability.
