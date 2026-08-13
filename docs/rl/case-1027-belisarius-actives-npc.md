# #1027 -- les deux actives npc d'`admecBossBelisarius` : `InvocationOfMachineVengeance` (1172) et `SolarAtomizer` (1174)

Build `rnca9r7q6c`. Les deux etaient en `[--]` au `docs/rl/npc-registry.tsv` (ni face combat ni face
decision). Un SEUL montage sert les deux, parce que 1172 CREE le substrat que 1174 consomme.

## 1. Le nom ment, et le decompile le dit

`SolarAtomizer` **ne frappe pas**. Aucune feuille `AttackWith*` dans
`IdunBattleLogic.Entities.Abilities.Active.SolarAtomizerAbility$$ExecuteBehaviour`, et
`AActiveAbility..ctor(this, &opts, 2)` = `AbilityAttackType.Others`. Les `minDmg`/`maxDmg` du
gameconfig 1174 alimentent la TRIGGERED `1297 SolarAtomizer_PendingAttack`, qui frappe au tour
SUIVANT (hors perimetre). L'i2 concorde : « marks all hexes in a straight line 2 hexes wide. At the
beginning of his next turn, de[als damage] ».

`InvocationOfMachineVengeance` n'est ni un buff simple ni une invocation simple : c'est un SPAWN
**puis** un buff d'equipe, et l'ORDRE est load-bearing (le buff voit les summons).

## 2. Les deux arbres, LUS

### 1172 -- `InvocationOfMachineVengeanceAbility$$ExecuteBehaviour`

```
nb      = Get( GetVariableForLevel(config, 0x4f = nrOfSummons, abilityState, 0) )   # 4 au niv. 50
unitId  = GetStringConstant(config, 0 = unitId)                                     # admecSmnTechpriest
trig    = HasTrait( Units(ActiveTarget@+0x68, unique: 1, sel: 3), 0x1b = Steppable )
extra   = ConditionalAmount( trig, <DSLFormulas+0x20> = Const(1), <+0x18> = Const(0) )
tiles   = First( SortByRow( CanAddUnit(AllTiles@+0x18), sameColumnIsRandom: 1,
                            additionalSorting: extra, ascending: 1 ), nb, 0 )
spawn   = Spawn( Caster@+0x48, tiles, unitId, WithStatsFromConfig(config, abilityState, 0, 0) )
mech    = MechanicalUnits( Friends(Caster@+0x48, AllUnits, sel: 3), sel: 3 )
addEff  = AddEffectOrIncreaseLevel( 0x555 = 1365 MachineVengeance, AbilityStateReference,
                                    source = Owner@+0x30, targets = mech,
                                    amount = Get(GetNumberConstant(0x73 = effectLevel)) = 1, max: 0 )
Execute( spawn op_BitwiseAnd addEff )
```

`SortByRow(ascending: 1)` = row CROISSANTE = « at the bottom of the map » de l'i2. Le critere
SECONDAIRE vaut 1 quand la tuile porte une unite `Steppable`, 0 sinon -> `ThenBy` ascendant = les
tuiles VRAIMENT libres d'abord (`CanAddUnit` accepte les deux).

### 1174 -- `SolarAtomizerAbility$$ExecuteBehaviour`

```
cached  = Cache( EntitiesWithAnyEffect( Friends(Caster@+0x48, AllUnits - Caster@+0x48, sel: 3),
                                        0x555, effectTarget: 6 ), matchAbilityEntities: 1 )
KEY     = Get("AccumulatedEffectLevel")                    # string literal #3759 du build
addPD   = AddPersistentData( AbilityOrEffect(0x496 = 1174), Caster@+0x48, KEY,
                             EffectLevel( EffectFromOwner(cached, 0x555) ) )
rmEff   = RemoveEffect( cached, Nullable<EffectType>(0x555), 0 )
pd      = GetPersistentData( AbilityOrEffect(1174), Caster@+0x48, KEY )
ifGt    = If( AmountIsGreater(pd, <DSLFormulas+0x18> = 0),
              AddEffectOrIncreaseLevel(0x555, AbilityStateReference, Caster, Caster, pd, 0), null )
setPD   = SetPersistentData( AbilityOrEffect(1174), Caster@+0x48, KEY, <DSLFormulas+0x18> = 0 )
mark1   = AddEffect( 0x55b = 1371 SolarAtomizer_PendingAttack,  ..., targets = Caster@+0x48 )
mark2   = AddEffect( 0x55c = 1372 SolarAtomizer_PendingTarget,  ..., targets = GetTargetTiles() )
Execute( ((((addPD & rmEff) & ifGt) & setPD) & mark1) & mark2 )
```

`GetTargetTiles` -- la BANDE DE DEUX LIGNES :

```
dir    = DirectionTo( AdjacentTiles(Target@+0x60) & Tiles(CasterTiles@+0x58), Target@+0x60 )
others = AdjacentTiles(Target@+0x60) - CasterTiles@+0x58
score  = Count( AdjacentTiles(ActiveTarget@+0x68) & CasterTiles@+0x58 )
second = First( SortByFormula(others, score, ascending: 0), 1, 0 )     # DECROISSANT
opts   = new <LineSettings>() ; *(u16*)(opts+0x10) = 0x101             # checkWalkable=1, updateRef=1
return ( (Target + TilesBehindInLine(Target, dir, opts, null))
       + (second + TilesBehindInLine(second, dir, opts, null)) ) - CasterTiles@+0x58
```

`SortByFormula(..., ascending: 0)` = decroissant -> `second` est le voisin de la cible qui a le PLUS
de tuiles du caster adjacentes, c'est-a-dire la colonne parallele COTE CASTER : c'est ce qui fait la
largeur 2.

## 3. Les trois LECTURES qui ne se devinent pas

1. **Les trois `AbilityOrEffect.op_Implicit` de 1174 portent `0x496 = 1174`** -- lu AUX OCTETS
   (`mov edx, 0x496` avant chacun des trois `call`). La donnee persistante est donc keyee sur CETTE
   ability et ne peut pas collisionner avec le compteur d'`ArcScourge` (`0x495`) sur le meme caster.
2. **Les deux cles de donnee persistante sont des string literals DISTINCTS** : `#3759`
   `"AccumulatedEffectLevel"` (1174) contre `#7679` `"EffectLevel"` (1173). Le slot de cache
   `0x33d9730` n'a QUE `SolarAtomizerAbility$$ExecuteBehaviour` pour xref ; la valeur textuelle vient
   de `data/symbols/rnca9r7q6c/metadata/string_literals.tsv`.
3. **`EffectLevel(effects)` est une SOMME** (`EffectLevelFormula$$Calculate` accumule
   `EffectComponent+0x68` sur tout le selecteur) -- c'est le « Transfers ALL levels » de l'i2.

## 4. Les masques, LUS ability par ability

| ability | isSelfCasting | range | forceMeleeTarget | rules |
|---|---|---|---|---|
| 1172 | **1** | `<TargetingRange statics+0x60>` = `RANGE_SELF` | 1 (`RangedBool.False`) | `0x8000` = `CasterIsPossibleTarget` |
| 1174 | 0 | `CustomRange(2)` (le `2` est dans `edx` avant le `call`) | 1 | `0x1000100042` = `TargetMatchesDynamicRule` \| `TargetIsTile` \| `AllowSteppableUnit` \| `CasterHas3Tiles` |

FORME 1 « flags directs » pour les deux : la surcharge est
`TargetingOptions$$.ctor(this, isSelfCasting, range, forceMeleeTarget, rules,
getDynamicInvalidCasterReason, getDynamicInvalidTargetReason)`, les deux autres `..ctor` etant des
COPIES (`template` seul ; `template + additionalRules`). **Le voisin ne predit rien** : 1172 partage
`isSelfCasting = 1` + `statics+0x60` avec `SupremeCommanderAbility` mais PAS son masque
(`0x208000` la-bas) -- `CasterHasFreeAdjacentTile` n'est pas pose ici, coherent avec un spawn EN BAS
DE CARTE.

`SolarAtomizerAbility$$GetDynamicInvalidTargetReason` -> `IsValidLineStartTile(casterTiles, target)`
= `GetAdjacentTiles(target).FilterInPlace(t => casterTiles.Contains(t)).Any()` : **la tuile visee
doit etre adjacente a une tuile du caster**. Sans cela l'intersection dont derive `dir` serait vide et
la bande degenererait.

## 5. La face DECISION -- deux playbooks NonComparable

Ghidra nomme leurs `.ctor` `ComparablePlaybook<T>$$.ctor` : c'est un corps **gshared DEDUPLIQUE**
(`NovaShieldPlaybook$$.ctor` n'a AUCUN symbole propre, et son playbook est NonComparable et porte
comme tel). Le discriminant LU est l'override d'`EvaluateNonComparable` :
`NonComparablePlaybook<T>$$EvaluateInternal` a pour corps ENTIER `(**(vtable + 0x318))()`.

* **1172** : `u = (casterPosition != GetUnitPosition(caster)) + 1`. Le Bucket ne remplace que sur
  STRICT `>` et la liste `tiles` commence par la position COURANTE -> **Belisarius BOUGE des qu'il le
  peut**, sur la PREMIERE tuile du movable set. C'est l'INVERSE de `NovaBoostPlaybook` (utilite
  constante -> cast en place), alors que les deux sont des self-cast : le voisin de forme ne predit
  pas le verdict. `.cctor` -> `minUtility = 1` ; tier `get_Priority` = **-1000**.
* **1174** : `u = 1 + |bande| + 20 x |ennemis de la bande|` -- l'increment est HORS du `if` (deux
  sites distincts au decompile), donc une tuile vide vaut 1 et une tuile ennemie 21, jamais 20. La
  bande est RE-EVALUEE par cible candidate, avec le MEME arbre que la face combat (import depuis
  `runner.abilities.admec` : une seconde transcription divergerait en silence). `.cctor` ->
  `minUtility = 1` ; tier = **100**. `ShouldEvaluate` = `IBattleQuery` slot `0x1b` =
  `HasMinimumRemainingTurns(unit, 2)` -- le degat ne tombe qu'au tour suivant, marquer sans 2 tours
  restants ne sert a rien.

## 6. Ce qui a ete CONFRONTE en live, et ce qui ne l'a pas ete

Fixture nommee : `probe_1027_belisarius_actives.py::monter` (board `MC1_67`, seed 777,
`--explicit-stats admecBossBelisarius:4`, allies `admecDominus`/`admecDestroyer`).

⚠ **Le refus de montage documente n'existe plus** : la memoire
`reference_boss_montable_par_explicit_stats` annonce `admecBossBelisarius` comme le SEUL boss dont
`--explicit-stats` leve (`TriggeredAbilityType.ShroudPsalm inconnu du build courant`). RE-MESURE le
2026-08-13 sur `rnca9r7q6c` : le montage PASSE (`hp=34277 dmg=3430 fixedArmor=2286`), le boss entre
en bataille sous l'id remappe `GuildBoss10Boss1AdmecBelisarius`, et ses TROIS actives sont `[pret]`.

* **1172 -- CONFRONTE.** Le cast emet **4 summons `admecNpc2Techpriest`** (= `nrOfSummons[50]` = 4)
  puis `MachineVengeance` `Effect_CurrentLevel=1 Effect_SourceId=81` sur **u81 (le caster), u83, u85
  ET les quatre summons**. La pose sur les summons est la preuve OBSERVABLE que le buff est evalue
  APRES le spawn, dans le meme arbre -- ce que l'`op_BitwiseAnd` du port reproduit (la feuille
  `Spawn` pousse ses enfants dans `entities.units`).
* **1174 -- NON CONFRONTE, et la raison est NATIVE.** Sur `MC1_67`, `abilityTargets` du natif rend
  `targetCount = 0` et `fromHereCount = 0` pour 1174 sur les SEPT unites amies, alors que
  `usable = true`. Ce n'est pas un angle mort du port : c'est le natif qui ne publie AUCUNE cible.
  Piste la plus probable, LUE au masque : le bit `CasterHas3Tiles` (1 << 36) -- Belisarius porte le
  trait `BigTarget` mais n'occupe pas 3 hexes hors de sa CARTE DEDIEE (`BoardId` + SPS du
  gameconfig). Residu `#1027-r6`.

## 7. Le bug que la garde a trouve dans son propre port

`SortByRow.additional_sorting` a d'abord ete ecrit en triant par ROW puis par la formule. Deux `sort`
stables realisent `OrderBy(A).ThenBy(B)` en triant **B d'abord, A ensuite** : l'ordre inverse rend la
FORMULE prioritaire sur la row. L'etage 6 de
`tests/engine/runner/test_1027_belisarius_actives_offline.py` l'a fait tomber (`[2, 3, 1]` au lieu de
`[2, 1, 3]`) avant tout live.

## 8. Residus ouverts

| n | quoi |
|---|---|
| `#1027-r1` | `SortByRow(sameColumnIsRandom: 1)` : le 3e `ThenBy(pseudoRng)` n'est pas tire (pas de substrat cle-par-element). Le port rend *un* des ordres du natif, pas un ordre invente. |
| `#1027-r2` | 1172 : `GetEligibleTargetsSelectable` n'est pas modelise PAR POSITION (self-cast portee 0 -> position-independant). |
| `#1027-r3` | `SolarAtomizerPlaybook$$GetUseProbability` : `BaseUnitComponent+0x5c` non identifie ; la branche 0.5 est une porte aleatoire non modelisee. |
| `#1027-r4` | `dsl_context_for_tile_target` ne repositionne pas le caster ; or `GetTargetTiles` lit `CasterTiles`. |
| `#1027-r5` | `HasMinimumRemainingTurns` sur la face DECISION : le plafond de rounds n'a pas de canal -> bras permissif. |
| `#1027-r6` | 1174 non confrontee : monter Belisarius sur sa CARTE DEDIEE pour que `CasterHas3Tiles` soit satisfait. |
| -- | `EntitiesWithAnyEffect` porte n'expose pas `effectTarget` (le natif passe `6` = owned\|incoming) ; `add_effect_or_increase_level` n'expose pas `source` (Owner == Caster sur une active). |
