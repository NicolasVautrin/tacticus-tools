# #512 — `1197 ExcruciatingFrequencies` : le crit se compte sur TOUTES les unités du rayon

`emperNoiseMarine` « Shiron » (Emperor's Children / Chaos, **lineup**, DANS le pool `--list-pool`
au rank 17 — seul porteur). Avant cette tranche l'ability était un **no-op silencieux** : absente
d'`ABILITY_CLASSES`, le cast partait, `ported` valait `False`, et **rien** ne se produisait — ni
dégât, ni effet, ni erreur.

## 1. Ce que le natif fait — `Execute`, PAS `ExecuteAtomic`

`IdunBattleLogic.Entities.Abilities.Active.Loki.ExcruciatingFrequenciesAbility$$ExecuteBehaviour` :

```
tousSurLaLigne = Cache( Units(GetAffectedTiles(), unique: 1, selectionType: 3), 1 )
ennemis        = Cache( Enemies( Caster@DSLSelectors+0x48,
                                 Units(GetAffectedTiles(), unique: 1, selectionType: 3), 3 ), 1 )
montant        = Multiply( Count(tousSurLaLigne),
                           Direct(GetVariableForLevel(0x41 = extraCritChance)) )
crit           = AddStaticStatModifierEffect( targets = Caster@+0x48,
                                              0x56c = TemporaryStatModifier,
                                              0x9   = StatType.CritChance,
                                              amount = montant,
                                              turns  = DSLFormulas+0x20 = Direct(1),
                                              isHidden = 1 )
retrait        = RemoveEffect( Caster@+0x48, Nullable(0x56c) )
attaque        = AttackWithAttackDamage( Caster@+0x48, ennemis,
                                         MinMaxDamage(abilityState, isPrediction: 0),
                                         Nullable(GetDamageProfile()), GetHits(),
                                         AbilityOrEffect(this), <options ZERO>,
                                         selectionType = 2 )

Execute( (crit op_BitwiseAnd attaque) op_BitwiseAnd retrait )
```

et le sous-arbre nommé, **partagé avec la face DÉCISION** :

| natif | contenu |
|---|---|
| `$$GetAffectedTiles` | `SortReverse( TilesBehindInLine(CasterTile@+0x50, TargetTile@+0x78, settings{+0x10 = 1, +0x11 = 1}, Direct(GetNumberConstant(0x17 = nrOfTiles))) )` |
| `$$GetAttackTargets` | `Enemies(Caster@+0x48, Units(GetAffectedTiles()))` — c'est **le second `Cache` ci-dessus**, et c'est aussi le corps de `$$GetDynamicInvalidTargetReason` (`Count > 0 ? 0 : 2`), **déjà porté** avant cette tranche (`_dynamic_rule_excruciating_frequencies`, #287-r11-r1) : il MIGRE seulement de `DYNAMIC_TARGET_RULE_UNPORTED` vers une surcharge de la classe |
| `$$GetUnitsOnTargetTiles` | `Units(GetAffectedTiles())` — le **premier** `Cache`, celui du `Count` |

⚠ **La callée est `AActiveAbility$$Execute(behaviour, entities)` — DEUX arguments.** Pas
`$$ExecuteAtomic(behaviour, entities, groupType)`, qui en prend trois. Le port ne pose donc
**aucun** `AtomicGroup` — contraste avec `DoomSiren` (1199) dans le **même module de faction** et
avec `LeadingTheCharge` (1204), qui emballent tous deux leur arbre dans un
`GroupType.Ability_AtomicGroup`. La forme se LIT à l'arité de la callée, elle ne se déduit pas du
voisinage.

## 2. Le point du cas : DEUX sélecteurs sur la MÊME géométrie

`GetAffectedTiles()` est appelé **deux fois**, et les deux résultats ne subissent pas le même
filtre :

* le **`Count`** du montant lit `Units(GetAffectedTiles())` — **toutes** les unités posées sur le
  rayon, alliées comprises ;
* l'**attaque** lit `Enemies(Units(GetAffectedTiles()))` — les seuls ennemis.

i2 le dit mot pour mot : « +{extraCritChance}% Crit Chance for each **unit** on affected hexes and
deals {nrOfHits}x {minDmg}-{maxDmg} Blast Damage to each **enemy** on affected hexes. »

Réutiliser le sélecteur d'ennemis pour le `Count` rendrait **exactement la même valeur** sur tout
régime sans allié sur le rayon — c'est-à-dire sur la quasi-totalité des batailles. La faute est donc
structurellement invisible d'un critère sur un total, et c'est ce qui a dicté le montage (§4).

## 3. Le masque, et le bit 41

`...ExcruciatingFrequenciesAbility$$.ctor` — forme **FLAGS DIRECTS** (surcharge à 7 arguments), donc
le littéral EST le masque, sans preset à OR-er :

```
TargetingOptions..ctor(&opts, isSelfCasting = 0, range = <TargetingRange statics+0x30>,
                       forceMeleeTarget = 1, rules = 0x20000000042, 0, 0)
AActiveAbility..ctor(this, &opts, 2)          // 3e argument = AbilityAttackType.Others
```

Décomposition **exhaustive** de `0x20000000042` (`0x2 + 0x40 + 0x20000000000`, rien ne reste) :

| bit | valeur | règle | effet |
|---|---|---|---|
| 1 | `0x2` | `TargetMatchesDynamicRule` | → la surcharge `get_dynamic_invalid_target_reason` |
| 6 | `0x40` | `TargetIsTile` | domaine TUILE : la cible EST un hex |
| **41** | `0x20000000000` | `AllowUntargetableTarget` | une tuile n'est jamais « targetable » |

⚠ **Le bit 41 est au-delà de 32.** `rules` est un masque **64 bits** (`options+0x28`) ; le lire ou le
stocker en 32 bits le perdrait **en silence**, et le cast tile-target serait refusé. Le test de la
tranche le garde explicitement.

`range` = `TargetingRange statics+0x30` = `RANGE_ADJACENT` (`onlyAdjacent = True`,
`overrideRange = 1`) : la tuile visée est **ADJACENTE** au caster — c'est la **direction** du rayon,
pas sa portée (celle-ci vaut `nrOfTiles`). `forceMeleeTarget = 1` = `RangedBool.False`.

⚠ **`AbilityAttackType = 2 = Others`, TRANSCRIT.** 1197 EST une attaque (`nrOfHits` coups Blast) et
porterait `DirectTargetAttack` à l'œil ; le littéral du ctor dit `Others`, et c'est lui qui décide de
`AbilityHasAttackType(0|1)` (gate SwornProtector).

## 4. Les deux enums de config sont AMBIGUS sur les DEUX index lus

Le corps lit `GetNumberConstant(config, 0x17)` et `GetVariableForLevel(config, 0x41, …)`. Les deux
ordinaux existent dans **les deux** enums de configuration, et y nomment autre chose :

| ordinal | `AbilityConstantType` | `AbilityVariableType` |
|---|---|---|
| `0x17` = 23 | **`nrOfTiles`** ← lu ici | `extraChance` |
| `0x41` = 65 | `armorReduction` | **`extraCritChance`** ← lu ici |

Confondre les deux aurait lu **deux mauvaises clés du gameconfig sans lever la moindre erreur**.
Le discriminant est l'**ACCESSEUR appelé au site** (type DÉCLARÉ du 1ᵉʳ paramètre, lu dans
`frida/methods.tsv`), jamais l'ordinal. C'est la forme exacte de l'avertissement du CLAUDE.md
(« une confusion d'enums peut être SILENCIEUSE EN ORDINAL »), rencontrée deux fois dans un même
corps de trois lignes.

## 5. Confrontation live — quatre régimes, board `MC1_67`

Géométrie **DÉRIVÉE** (`battle_query.get_tiles_behind`, le foyer partagé), jamais posée à l'œil : sur
un board hex la ligne CUBE n'est pas la ligne « row constante ». Le couple retenu est
`P = (4,5)`, `aim = (4,6)` → rayon `[(4,6), (4,7), (4,8)]`, trois tuiles d'élévation 1 (le gate
`|Δelev| < 2` de `TileUtil$$IsTileValidForList` ne tronque donc rien).

```
emperNoiseMarine (4,5)  le caster              --crit 0,700  (crit de BASE à ZÉRO : la SEULE
necroWarden      (4,6)  ennemi, 1re tuile                     source de crit est le buff de
ultraTitus       (4,7)  ALLIÉ,  2e tuile                      l'ability -> lisible tel quel)
orksNob          (4,8)  ennemi, 3e tuile
tauMarksman      (5,6)  ennemi HORS rayon      (témoin : ne compte pas, n'est pas frappé)
```

| régime | delta | crit posé NATIF | crit posé PORT | cibles | tirages |
|---|---|---|---|---|---|
| **R0 `isolé`** | R1 + caster privé de son passif | **90** | **90** | u81, u83 | 6 = 6 |
| **R1 `mixte`** | l'allié est SUR le rayon | **90** | **90** | u81, u83 | 6 = 6 |
| **R2 `ennemis`** | l'allié est LOIN `(0,3)` | **60** | **60** | u81, u83 | 6 = 6 |
| **R3 `borne`** | caster `(4,8)` → rayon `[(4,7),(4,6),(4,5)]`, un ennemi sur la **4e** tuile `(4,4)` | **60** | **60** | u81, u83 | 6 = 6 |

**Le natif PUBLIE la valeur mesurée**, ce qui rend l'étage déterministe — aucun tirage n'intervient :

```
[Effect_Refresh e=106 «TemporaryStatModifier»]
  ActivateEffect e=77  Effect_Id=106
  ReceiveEffect  e=77  Effect_SourceId=77 Effect_RemainingTurns=1 Effect_Id=106
  ChangeStats    e=77  UnitStats_Modification_Hidden=1
                       UnitStats_CritChance_Modification=90
                       UnitStats_CritChance_Modification_Change=90
```

`90 = 3 unités × extraCritChance(niveau 50) = 30`. Le couple **R1/R2** est le discriminant : mêmes
ennemis, mêmes tuiles, même seed, **seule** la position de l'allié change — et le natif rend `90`
puis `60`. Un port qui compterait les ennemis rendrait `60` aux deux.

Trois lectures que ce montage ferme au passage :

* `RemainingTurns = 1` confirme `turns = DSLFormulas+0x20 = Direct(1)` (déjà en TOURS, surtout pas
  `TurnsFromRounds`) ;
* `Modification_Hidden = 1` confirme le 7ᵉ argument `isHidden = 1` ;
* `LoseEffect e=77 Effect_Id=106` en fin de cascade confirme le `RemoveEffect` final : le buff ne
  survit pas au cast.
* et le **niveau** : `30` par unité, pas `20` (niveau 1) ni `48` (`30 × 160 %`) — `extraCritChance`
  n'est **pas** dans `variablesAffectedByRarityBonus`, donc le multiplicateur de rareté du runner ne
  mord pas. Les deux lectures fautives sont gardées par le test.

**Conséquence observable du compte, au-delà de l'événement** : en R1 la crit chance vaut `90` (+15
de `ThrillSeekers` = 105) et les **deux** coups critent ; en R2 elle vaut `60` (+15 = 75) et **seul
le premier** crite. Le port reproduit la séquence de crits dans les deux régimes.

Contre-épreuves hors-ligne (mêmes captures, une lecture changée à la fois) :

| variante | R1 | R3 |
|---|---|---|
| REF | crit 90, cibles `[81, 83]` | crit 60, cibles `[81, 83]` |
| AB1 `Count(Enemies)` au lieu de `Count(Units)` | crit **60** | *inerte* (pas d'allié sur le rayon) |
| AB2 aucun buff de crit | crit **None** | crit **None** |
| AB3 attaque TOUTES les unités | cibles **`[79, 81, 83]`** | *inerte* |
| AB4 borne `nrOfTiles` désarmée | *inerte* (le rayon finit au bord du plateau) | crit **90**, cibles **`[81, 83, 85]`** |

Aucune variante n'est inerte dans **tous** les régimes — et le probe **imprime** celles qui le sont
dans le régime courant, pour qu'un vert ne se lise jamais comme une mesure qui n'a pas eu lieu.

## 6. Le dégât NOMINAL diverge — l'écart est ATTRIBUÉ, résidu `#512-r1`

En régime nominal le port SOUS-TIRE, à **séquence, cibles, crits et nombre de tirages identiques** :

| régime | cible | PORT | NATIF | écart |
|---|---|---|---|---|
| R1 | u81 | 9575 | 10073 | +498 |
| R1 | u83 | 7101 | 7766 | +665 |
| R3 | u81 | 6383 | 6715 | +332 |
| R3 | u83 | 6226 | 6891 | +665 |

**R0 — le MÊME montage que R1, le caster privé de son seul passif — rend `9575 / 7101` des DEUX
côtés, bit pour bit, en 6 tirages.** L'écart n'est donc pas dans ce mirror ; il est dans la chaîne
de déclencheurs du porteur :

```
natif : SuppressiveFire (TRAIT du caster) pose `Pinned` (0x429) sur CHAQUE cible du rayon
        -> On(PreEffectAdded = 0x3d) -> TerrifyingCrescendo (passif) monte
           `TerrifyingCrescendo_ExtraDmg` (0x590) d'un niveau
        -> ce niveau ajoute son `extraDmg` au coup EN COURS
           (niveau 1 sur le 1er coup, niveau 2 sur le 2e -- visible dans la cascade native)
port  : `SuppressiveFireAddEffectAbility` n'écoute que `On(NormalAttack = 38)`, donc RIEN n'est
        posé sur une attaque d'ABILITY -> le crescendo ne monte jamais
```

C'est un résidu **déjà nommé** dans `runner/operations/triggers/loki/suppressive_fire.py` : « Un
carrier qui suppress via une ATTAQUE-ABILITY ranged ne serait pas couvert […] **Aucun scénario de
validation ne l'exige.** » #512 **est** ce scénario, et c'est la première fois qu'il est exercé.

⚠ **La mesure RÉFUTE l'argument qui y justifiait l'abstention.** Ce commentaire écarte le vecteur
`Attack(9)` au motif que « le natif suppress la cible PRIMAIRE seule (PreAttack once) → sur-
suppression des victimes de splash ». Sur une attaque d'ability **multi-cible**, la cascade native
pose `Pinned` sur **chacune** des cibles (`u81` puis `u83`, chacun dans son propre bloc
`[Ability_Power e=77 «SuppressiveFire»]`) — parce que `AttackBehaviour$$Execute` pousse un
`OngoingAttack`, donc un `On(PreAttack)`, **par cible**. Ce qui reste à trancher n'est donc pas
« primaire ou toutes », mais **où le natif émet `PreAttack`** — et la réponse sépare une attaque
multi-cible (une par cible) d'un splash composé dans le `Attack(...)` d'une autre attaque
(`isOutsideAttack = false`, aucun nouveau `PreAttack`, cf. `#419-r3`).

Corriger le vecteur touche les **49** porteurs du trait (dont 8 lineup) et exige la RE des points
d'émission de `PreAttack` : hors périmètre de cette tranche. Résidu `#512-r1`.

## 7. Ce que la tranche livre

* `engine/runner/abilities/emperorschildren.py` — `ExcruciatingFrequenciesAbility` (masque,
  `AbilityAttackType`, surcharge de la règle dynamique **par délégation** au foyer, arbre DSL) ;
* `engine/runner/abilities/targeting.py` — `excruciating_frequencies_affected_tiles`, **le** foyer
  de `GetAffectedTiles`, désormais partagé par les deux faces ; l'entrée de 1197 **sort** des deux
  tables `*_UNPORTED` (contrat de disjonction) ;
* `engine/runner/abilities/behaviours/context.py` — `entities_with_tile_target`, la forme
  PARTAGEABLE de la parade « le rôle `target` ne matérialise pas une entité-TUILE » que
  `#287-r8` et `#287-r11-r1` écrivaient chacune de leur côté (résidu `#287-r12` inchangé :
  `entities_from_state` n'est PAS élargi, les 5 abilities tile-target qui lisent un `Target()` nul
  ne bougent pas) ;
* `probe_512_excruciating_frequencies.py` — 4 régimes live + 4 contre-épreuves ;
* `tests/engine/runner/test_512_excruciating_frequencies_offline.py` — 17 assertions, `DECLENCHEUR`
  large, `build: True` (les ordinaux figés sont lus dans le binaire).

**Reste hors de cette tranche** : le résidu `#512-r1` ci-dessus, et la face DÉCISION (le playbook
`ExcruciatingFrequenciesPlaybook`, porté depuis #56-t3b, qui **n'est pas touché** — il consomme le
même `get_tiles_behind` en domaine POSITION).
