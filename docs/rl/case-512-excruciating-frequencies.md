# #512 — `1197 ExcruciatingFrequencies` : le crit se compte sur TOUTES les unités du rayon

> **`#512-r1` est RÉSOLU** (§6) : `SuppressiveFire` écoute désormais son vecteur natif
> `On(PreAttack = 5)`, émis **par cible distincte**, et son gate est le slot 3 `IsRangedAttack`
> COMPLET — dont la branche `Ranged(2)`, qui ne lit **aucune** position. Le dégât est bit-exact dans
> les quatre régimes. Résidu ouvert : `#512-r2` (§8).

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

## 6. Le dégât NOMINAL divergeait — `#512-r1`, la chaîne de déclencheurs du porteur

En régime nominal le port SOUS-TIRAIT, à **séquence, cibles, crits et nombre de tirages
identiques** :

| régime | cible | PORT (avant) | NATIF | écart |
|---|---|---|---|---|
| R1 | u81 | 9575 | 10073 | +498 |
| R1 | u83 | 7101 | 7766 | +665 |
| R3 | u81 | 6383 | 6715 | +332 |
| R3 | u83 | 6226 | 6891 | +665 |

**R0 — le MÊME montage que R1, le caster privé de son seul passif — rendait `9575 / 7101` des DEUX
côtés, bit pour bit, en 6 tirages.** L'écart n'était donc pas dans ce mirror ; il était dans la
chaîne de déclencheurs du porteur :

```
natif : SuppressiveFire (TRAIT du caster) pose `Pinned` (0x429) sur CHAQUE cible du rayon
        -> On(PreEffectAdded = 0x3d) -> TerrifyingCrescendo (passif) monte
           `TerrifyingCrescendo_ExtraDmg` (0x590) d'un niveau
        -> ce niveau ajoute son `extraDmg` au coup EN COURS
port  : `SuppressiveFireAddEffectAbility` n'écoutait que `On(NormalAttack = 38)`, donc RIEN n'était
        posé sur une attaque d'ABILITY -> le crescendo ne montait jamais
```

### 6.1 OÙ LE NATIF ÉMET `PreAttack` — la lecture qui tranche

Le commentaire de `suppressive_fire.py` écartait le vecteur au motif que « le natif suppress la
cible PRIMAIRE seule (PreAttack once) → sur-suppression des victimes de splash ». **C'est faux**, et
la réponse ne se déduit pas d'un observable : elle se LIT.

```
IdunBattle.Entities.Behaviours.AttackBehaviour$$Execute        # le nœud DSL `Attack(...)`
    caster  = Select(entities+0x50) ; targets = Select(entities+0x58)   (OrderBy si Count > 1)
    for tgt in targets:
        if prev is null or prev != tgt: processor.StartAttack  (slot 58)
        <inner behaviour>                                      # AttackDamage / AbilityDamage
        if next is null or next != tgt: processor.FinishAttack (slot 59)
IdunBattle.Operations.StartAttackOperation$$Execute
    -> IOperationProcessor.EvaluateAbilitiesImmediately(EventTriggerType.PreAttack = 5,
                                                        AbilityEntities{actor, target})
```

Les slots sont **LUS** dans `data/symbols/<build>/metadata/ioperationprocessor_slots.tsv`
(58 `StartAttack`/3, 59 `FinishAttack`/3, 80 `EvaluateAbilitiesImmediately`/2), et la lecture du 4ᵉ
argument comme `EventTriggerType` est **recoupée** sur
`IdunBattle.Operations.ADamageOperation$$EvaluateAfterHitTriggers`, qui émet par le même helper
`0x3c = UnitBlocked` puis `8 = AttackHit` — exactement ce que le port en dit déjà.

⇒ **`PreAttack` part une fois par CIBLE DISTINCTE** (l'`OrderBy` préalable groupe les cibles
répétées, donc N coups sur la même cible n'ouvrent qu'une attaque). Trois émetteurs de `StartAttack`
en tout : `AttackBehaviour$$Execute`, `IdunBattle.Entities.Behaviours.StartAttackBehaviour$$Execute`
et la voie MESSAGE `IdunBattle.Messages.InputMessageProcessor.u003Cu003Ec__DisplayClass25_0$$u003CVisitu003Eb__0`.

Ce qui reste vrai de la mise en garde, mais autrement : une feuille
`IdunBattleLogic.Entities.DSLBehaviors$$AttackDamage` **NUE** composée dans le `Attack(...)` d'une
autre attaque (`isOutsideAttack = false`, `#419-r3`) n'ouvre **aucun** `StartAttack` et n'émet donc
rien. **La distinction est STRUCTURELLE — `Attack(...)` contre feuille nue — pas « primaire contre
toutes ».**

⚠ Et `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAbilityDamage` (surcharge racine à 7
arguments) finit elle aussi par `IdunBattle.Entities.Behaviours.AttackBehaviour$$.ctor` : la famille
ABILITY émet donc `PreAttack` **comme** la famille ATTACK. Le port ne l'y émet pas (gate
`is_attack_damage_op`) → résidu `#512-r2`.

### 6.2 LE GATE `IsRangedAttack` N'EST PAS POSITIONNEL — deuxième lecture, et elle est décisive

`SuppressiveFireAbility$$CreateTrigger` (re-lu sur `rnca9r7q6c`) conjoint `IsRangedAttack`, qui est
`IdunBattle.Core.Services.BattleQuery$$IsRangedAttack` — le slot **3** d'`IBattleQuery` :

```
if (!ability.HasValue) return false;
switch (GetAbilityAttackRangeType(ability)) {   // 0 None, 1 Melee, 2 Ranged, 3 Normal
  case 0: case 1: return false;
  case 2: return true;                          // INCONDITIONNEL — aucune position lue
  case 3: return HasFlag(caster, 0x15 = UnitFlag.ForceRangedAttack)
                 || !AreEntitiesAdjacent(casterPosition, target);
}
```

L'enum est LU (`IdunBattle.Entities.Enum.AttackRangeType` = `0=None,1=Melee,2=Ranged,3=Normal`) et
le flag aussi (`IdunBattle.Entities.Enum.UnitFlag`, `21=ForceRangedAttack`). Le port n'avait que
`triggers/base._is_ranged_position`, c'est-à-dire **la seule branche `Normal(3)`** — et 1197 est
`attackRangeType = Ranged` (gameconfig **et** `BC.Abilities.ActiveAbilities[…].AttackRangeType = 2`),
avec sa 1ʳᵉ cible ADJACENTE au caster. Le gate positionnel la déclarait mêlée.

⚠ Ce n'est **pas** la négation d'`is_melee_attack` (slot 2) : les deux rendent `false` sur `None(0)`.
D'où deux fonctions natives, et deux mirrors.

### 6.3 LA PLACE de l'émission — troisième volet, et il est portant

Le natif pousse `StartAttack` **avant** d'exécuter le behaviour enfant, donc avant `GetAttackHits`
et avant tout `ExecuteHit` (qui rebâtit les modificateurs à chaque coup). Le port émettait
`pre_attack_triggers` **après** `attacker_modifiers` : le niveau de crescendo monté par la pose
restait invisible du coup en cours. L'émission remonte, sur les **deux** voies. Aucun tirage RNG ne
sépare les deux places, donc l'ordre `state.rng` est inchangé pour tout porteur qui ne pose rien.

### 6.4 Ce que le fix rend, mesuré

| régime | PORT | NATIF | tirages |
|---|---|---|---|
| R0 `isolé` | 9575 / 7101 | 9575 / 7101 | 6 = 6 |
| R1 `mixte` | 10073 / 7766 | 10073 / 7766 | 6 = 6 |
| R2 `ennemis` | 10073 / 6891 | 10073 / 6891 | 6 = 6 |
| R3 `borne` | 6715 / 6891 | 6715 / 6891 | 6 = 6 |

`DEGAT_EXACT` du probe passe à **True dans les quatre régimes** : R0 reste la contre-épreuve
d'ISOLATION (un R0 rouge accuse le mirror, un R1 rouge à R0 vert accuse la chaîne).

⚠ **R0 ne mesurait PAS ce qu'il annonçait, et seul le fix l'a montré.** `probe_512` n'appelait pas
`snapshot.bind_live_rpc`, donc `_auto_ability_states` rendait `no-transport`, tous les canaux
mesurés restaient `None`, et `collect_triggered_abilities` retombait sur le kit GAMECONFIG : le
`--unit-stat <caster>:PassiveAbilities=[]` du régime R0 ne retirait **rien** côté port. R0 passait
donc par **coïncidence** (le port ne posait aucun `Pinned`, donc le crescendo restait à 0 des deux
côtés) ; dès que le vecteur a été câblé, R0 est devenu ROUGE — et c'était le MONTAGE. Le rejeu tourne
désormais sous `live_rpc`. Même gisement que le résidu `#521-r5`.

### 6.5 Généralisation — un AUTRE porteur, une AUTRE ability, la POSE pour observable

`probe_512r1_suppressive_par_cible.py` : `blackObliterator` « Volk » (traits `SuppressiveFire` **et**
`LetTheGalaxyBurn` — les deux seuls consommateurs portés de `On(5)` — et **pas** de
`TerrifyingCrescendo`, donc la pose se lit au lieu de se payer en dégât), castant
`1036 FrenziedFiring` (`Ranged`, famille ATTACK, multi-cible) sur une cible **adjacente**.

| | `Pinned` posé |
|---|---|
| NATIF | `u79` (origine adjacente), `u81`, `u83` |
| PORT | `u79`, `u81`, `u83` |
| `AB1` gate rabattu sur `_is_ranged_position` (l'état d'avant) | `u81` **seul** |
| `AB2` ancien vecteur `On(NormalAttack = 38)` | **∅** |

Les deux contre-épreuves MORDENT : les deux lectures (§6.2 et §6.1) sont donc réellement exercées
par ce montage, et son vert n'est pas vrai par vacuité.

**Rayon RE-MESURÉ** (le « 49 » d'avant était périmé) : **52** porteurs du trait, dont **8 lineup**.
Sept d'entre eux portent une active à `attackRangeType` explicite — six en `Ranged`
(`astarCyrus`/`StrikeFromTheShadows`, `astraOrdnance`/`BasiliskBarrage`,
`blackObliterator`/`FrenziedFiring`, `emperNoiseMarine`/`ExcruciatingFrequencies`,
`templAggressor`/`FragstormGrenadeLauncher`, `thousTerminator`/`HellfyreMissileRack`) et une en
`Normal` (`tauDarkstrider`/`FightingRetreat`, qui reste donc positionnelle).

## 7. Ce que la tranche livre

* `engine/runner/abilities/emperorschildren.py` — `ExcruciatingFrequenciesAbility` (masque,
  `AbilityAttackType`, surcharge de la règle dynamique **par délégation** au foyer, arbre DSL) ;
* `engine/runner/abilities/targeting.py` — `excruciating_frequencies_affected_tiles`, **le** foyer
  de `GetAffectedTiles`, désormais partagé par les deux faces ; l'entrée de 1197 **sort** des deux
  tables `*_UNPORTED` (contrat de disjonction) ;
* `engine/runner/abilities/behaviours/context.py` — `entities_with_tile_target`, la forme
  PARTAGEABLE de la parade « le rôle `target` ne matérialise pas une entité-TUILE » que
  `#287-r8` et `#287-r11-r1` écrivaient chacune de leur côté. ⚠ **Cette fonction n'existe plus** :
  `#287-r12` a élargi `entities_from_state` lui-même après avoir mesuré le rayon de souffle
  (**2** abilities, pas 5), et 1197 passe désormais par le foyer — c'est le même contexte, au même
  endroit, sans la forme spécialisée ;
* `probe_512_excruciating_frequencies.py` — 4 régimes live + 4 contre-épreuves ;
* `tests/engine/runner/test_512_excruciating_frequencies_offline.py` — 17 assertions, `DECLENCHEUR`
  large, `build: True` (les ordinaux figés sont lus dans le binaire).

Puis `#512-r1` (§6) :

* `engine/services/battle_query.py` — `attack_range_type` (l'étage `GetAbilityAttackRangeType`,
  séparé chez le natif et consulté par les slots 2 ET 3) et `is_ranged_attack` (le slot 3) ;
* `engine/runner/operations/triggers/base.py` — `_is_ranged_attack`, le slot 3 COMPLET dans le
  domaine du runner (la branche `Normal(3)` reste sur `_is_ranged_position`) ;
* `engine/runner/operations/triggers/loki/suppressive_fire.py` — `event_id = PreAttack(5)` ;
* `engine/runner/operations/damage_ops/{normal,ability}.py` — `pre_attack_triggers` REMONTÉ avant
  `attacker_modifiers` ;
* `engine/runner/abilities/emperorschildren.py` — `ability_type` threadé sur la feuille de 1197
  (7ᵉ argument natif `AbilityOrEffect(this)`) ;
* `probe_512r1_suppressive_par_cible.py` — la généralisation du §6.5.

**Reste hors de cette tranche** : le résidu `#512-r2` (§6.1 — la famille ABILITY émet `PreAttack`
nativement, le port ne l'y émet pas), et la face DÉCISION (le playbook
`ExcruciatingFrequenciesPlaybook`, porté depuis #56-t3b, qui **n'est pas touché** — il consomme le
même `get_tiles_behind` en domaine POSITION).

## 8. Résidus

* **`#512-r2` — la famille de factory ABILITY n'émet pas `PreAttack` côté port.**
  `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAbilityDamage` (surcharge racine à 7 arguments)
  finit par `IdunBattle.Entities.Behaviours.AttackBehaviour$$.ctor(caster, target,
  <AbilityDamageBehaviour>, abilityOrEffect)` — LU au décompilé — donc par `StartAttack`, donc par
  `On(5)`. Le port gate l'émission sur `is_attack_damage_op` (`damage_ops/ability.py`), ce qui
  l'éteint pour toute feuille `native_factory="ability"` — dont `1088 HellfyreMissileRack` et
  `1026 BasiliskBarrage`, **deux abilities de porteurs du trait**. Élargir réveille aussi
  `LetTheGalaxyBurnArmAbility`, dont le `Maybe(chance)` **consomme un tirage** : à confronter live
  (un porteur des deux traits, `blackObliterator`, existe et est dans le pool) avant de le faire.
* **Une feuille qui ne thread pas son `ability_type` fait retomber le gate sur `Normal(3)`.**
  `_is_ranged_attack` lit l'`AbilityOrEffect` de l'événement ; une feuille d'attaque qui laisse
  `ability_type=None` (cas mesuré : `ChainLeftOverHitsAttackDamage` de
  `1048 FragstormGrenadeLauncher`) redevient positionnelle — donc sous-suppresse une cible adjacente.
  Ce n'est pas une dégradation NOUVELLE (c'était l'état de tout le monde avant), mais c'est
  désormais une dégradation SILENCIEUSE et localisée. Les six abilities `Ranged` de porteurs lineup
  ont été vérifiées une par une : cinq threadent, `FragstormGrenadeLauncher` non.
