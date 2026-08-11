# #940 — `KissOfDeath` (1108) : la face COMBAT était un NO-OP SILENCIEUX

Avant cette tranche, `AbilityHandler.ABILITY_CLASSES` ne connaissait pas 1108 : l'IA la choisissait,
l'exécution n'en faisait **rien** — zéro dégât, aucune erreur, invisible en self-play.

## 1. Les faces, recensées

| face | artefact natif | verdict |
|---|---|---|
| COMBAT | `IdunBattleLogic.Entities.Abilities.Active.Loki.KissOfDeathAbility$$ExecuteBehaviour` | **PORTÉE** (ce commit) |
| CIBLAGE | `...KissOfDeathAbility$$.ctor` | **PORTÉE** — masque + `AbilityAttackType` |
| DÉCISION (owner) | `IdunBattle.AI.Playbook.Loki.KissOfDeathPlaybook$$EvaluateNonComparable` + `$$.ctor` | **NON PORTÉE** → résidu `#940-r2` |
| DÉCISION (non-owner) | — | **N'EXISTE PAS** : `metadata/active_playbook_builders.tsv` ne porte 1108 que sous `active` (+0x68) ; les dicts `nonowner` (+0x98) et `specific` (+0xa8) ne le citent pas |
| `CreateTrigger` / `CreateBehaviour` | — | **N'EXISTENT PAS** : `frida/methods.tsv` comme `ghidra/functions.tsv` ne portent que `.ctor` et `ExecuteBehaviour` pour cette classe, et le voisinage du bloc `methodPointers` (entre `KillMaimBurnAbility$$.ctor` et `LashOfTormentAbility$$ExecuteBehaviour`) ne contient rien d'autre |

⚠ **La parenté du playbook se lit dans `classes.tsv`, pas au nom du `.ctor`** : le décompilé du `.ctor`
affiche `ComparablePlaybook<…>::.ctor` (ICF), la table dit `NonComparablePlaybook\`1` — ce que confirme
le nom de la méthode, `EvaluateNonComparable`.

## 2. L'arbre, terme à terme

```
ExecuteAtomic( ((AddEffect & ChainAttackDamage) & FlyUnit) & RemoveEffect,
               GroupType 0x2a = Ability_AtomicGroup )

AddEffect  ( 0x414 = EffectType.Untargetable, AbilityStateReference,
             source = Caster@<DSLSelectors+0x48>, targets = Caster@+0x48,
             options = <Nullable<AddEffectBehaviourOptions> VIDE> )
Chain      ( preselectedTargets = Target@<+0x60>,
             jumpTargetSelector = <lambda, cf. §4>,
             maxTargets = ConfigVar(0x0 maxAdjacentTargets),
             dmgAmount  = Direct(GetVariableForLevel(config, 0xb dmg, abilityState, 0)),
             damageProfileType = GetDamageProfile(),  hits = Direct(GetHits()),
             abilityType = AbilityOrEffect(this),
             extraBehaviour = null, maxTargetsExtra = null,
             damageOptions = <AttackDamageBehaviourOptions ZERO>,
             chainOptions  = { +0x12 = 1 } )                       # coup DIFFÉRÉ d'un cran
FlyUnit    ( Caster@+0x48,
             First( SortTilesByUtility( A.Otherwise(B).Otherwise(C),
                                        Caster@+0x48, 7 = UtilityType.Tile, null ), 1, false ) )
   A = CanAddUnit(AdjacentTiles(Last(UnitsAttackedThisTurn(Caster@+0x48), 1, false)))
           op_Subtraction <DSLSelectors+0x50 = CasterTile>
   B = idem sur AtIndex(<les mêmes>, 1)          C = idem sur Target@+0x60
RemoveEffect( Caster@+0x48, Nullable(0x414), replaceableEffectType = null )
```

i2 : « The Harlequin Player **disappears** and deals {nrOfHits}x {dmg} Direct Damage to an adjacent
enemy, and up to {maxAdjacentTargets} additional enemies adjacent to **a previous** target, then it
**reappears** in a hex adjacent to the **last target hit**. » — les quatre propositions sont les
quatre membres de l'`op_BitwiseAnd`.

## 3. Ce que le natif dit et qu'aucune table ne disait

1. **La colonne `DAMAGE(DirectDamage)` de l'audit est VRAIE ici, mais par coïncidence** : elle dérive
   du `damageProfile` de l'ARME du porteur ; le dégât réel vient d'un `ChainAttackDamage`
   (famille ATTACK → `AttackDamageOperation`), et le profil est LU de la constante de config.
2. **`dmgAmount` est un `Direct(...)`, pas un `MinMaxDamage`.** La config 1108 n'a **ni `minDmg` ni
   `maxDmg`** — le mode BORNES de la feuille d'attaque y lirait deux clés absentes, donc **0 dégât en
   silence**. `ChainAttackDamage` ignorait ce 4ᵉ argument de la factory (son unique consommateur,
   `FuryOfTheAncients`, est en bornes) : il le transmet désormais.
3. **`maxTargets` borne les SAUTS, pas le total** — le compteur natif est un delta sur la liste
   présélectionnée. `maxAdjacentTargets = 2` + 1 présélectionnée = **3 unités** frappées au plus.
4. **L'atterrissage se lit APRÈS la chaîne, et c'est tout l'enjeu du port.**
   `UnitsAttackedThisTurn` est l'`ActorStatisticsComponent+0x40` du caster — un `OrderedSet` que
   **chaque maillon vient d'allonger**. `FlyUnit` n'évalue son sélecteur qu'à son `execute`, donc
   après le `chain`. Deux conséquences, toutes deux portées :
   * `unitsAttackedThisTurn` entre dans `_LIVE_KEYS` (`behaviours/context.py`) — figé au seed il
     rendrait la liste d'AVANT le premier coup ;
   * le substrat passe de `set` à **`dict` ordonné** (`components.py`) — un `set` Python itère par
     hash, donc `Last(…)` y désignerait une victime arbitraire, **silencieusement**.
5. **Le masque de ciblage est une RECOPIE de preset statique** (la 2ᵉ forme du piège) : aucun
   `TargetingOptions$$.ctor` n'est appelé, le `.ctor` copie les 0x40 octets de
   `<TargetingOptions statics>+0x40`. Masque effectif = `<preset>+0x28` = `<statics>+0x68` =
   **0x4000 = `TargetIsEnemy`**, seul.
   ⚠ **Et la PORTÉE ne se déduit PAS d'`attackRangeType`** : le même preset recopie le
   `TargetingRange` de `<TargetingRange statics>+0x30` (`onlyAdjacent = RangedBool.True`,
   `overrideRange = 1`) = **`RANGE_ADJACENT`**, pas `RANGE_FROM_CONFIG` (`statics+0x18`) — la config
   1108 n'a d'ailleurs aucune constante `range`. **Mesuré** : avec `RANGE_FROM_CONFIG`, le port
   acceptait les quatre ennemis du montage **plus le caster** là où le natif n'en accepte qu'un.
6. `AActiveAbility$$.ctor(this, &opts, 0)` → `AbilityAttackType = 0 = DirectTargetAttack`, transcrit.

## 4. Le lambda `jumpTargetSelector` n'est dans AUCUNE table — attribution ÉTAYÉE, pas lue

`KissOfDeathAbility` ne porte que deux méthodes dans les deux tables : son `<ExecuteBehaviour>b__N_0`
a été **fondu par l'ICF**. Le corps retenu est celui de
`IdunBattleLogic.Entities.Abilities.Active.Loki.StormOfWrathAbility$$u003CExecuteBehaviouru003Eb__1_0` :

```
lastTargets => Enemies( of = Caster@<DSLSelectors+0x48>,
                        AdjacentUnits(lastTargets, unique = 1, selectionType = 3),
                        selectionType = 3 )
```

Trois arguments concordants : (a) c'est la seule des **cinq** lambdas `-> TargetsSelector` du binaire
dont le corps ne porte **aucun littéral propre ni bloc d'init de metadata-usage** — donc le seul que
l'ICF *peut* fondre avec un homologue d'une autre classe ; (b) sa sémantique est mot pour mot celle de
l'i2 ; (c) les deux classes partagent le pointeur de classe des `chainOptions` et celui du `Func<>`.
**Confirmé en live** : `M2`, adjacent à `M1` seul et jamais à la cible désignée, EST frappé — ce que
seul un saut depuis la liste complète des cibles piquées produit. Résidu `#940-r1` : le trancher
exigerait de lire le `MethodInfo*` du delegate en live.

## 5. Confrontabilité — la voie SUMMON est FERMÉE, et c'est mesuré

Deux porteurs, aucun au pool. `eldarSmnHarlequin` est un **summon** dont le summoner n'est pas une
unité : l'unique ability du gameconfig dont `constants.unitId` vaut `eldarSmnHarlequin` est
**`EnvFactionSummons:Aeldari`**, que `unit_map find --ability` ne rattache à **aucune** unité du
catalogue (spawner d'ENVIRONNEMENT, posé par le board). « Spawner son summoner » est donc impossible
depuis `rl_duel build`.

La voie retenue est le **recours 4** de `case-92 §5bis` : `eldarNpc3Harlequin`, le porteur **npc**,
monté par `--explicit-stats eldarNpc3Harlequin:40` (`GetNpcStats` → `units.npc[id].stats[]`). C'est le
**mirror**, pas la greffe — l'unité arrive avec ses stats, ses traits, son arme et son ability 1108.
Mesuré : `hp=8264 dmg=2728 fixedArmor=1122`, `abilityState` = (level 59, mult 200).

## 6. Validation

`probe_940_kiss_of_death_live.py` — six étages, montage `MC1_67` avec la géométrie **calculée**
(`H(3,3) · T(3,4) · M1(3,5) · M2(2,5) · W(1,6)`), chaque adjacence assertionnée avant de mesurer :

| étage | verdict |
|---|---|
| ciblage | natif `fromHere = [T]` ; port accepte `[T]`, refuse `M1/M2/W/H` |
| cibles de la chaîne | port == natif == `{T, M1, M2}` ; `W` **non** frappé (la borne mord) |
| atterrissage | port == natif == **(2,4)**, adjacente à `M2` (la dernière victime) |
| effet 1044 | le caster reçoit un effet dont il est la source, **puis** le perd, même cascade |
| dégât | `DirectDamage`, `Active_Ability_Type = 1108`, et **T:1715 M1:3840 M2:3840 bit-exact** des deux côtés (rng calé par `dumpRng`) |
| mutants | **5/5 MORDENT** |

⚠ **Sans calage du rng, le pipeline de dégât est INERTE** (`if state.rng is None: return None`) — et
pour CE port la dégradation est traîtresse : pas de dégât ⇒ pas de `register_attack_made` ⇒
`UnitsAttackedThisTurn` vide ⇒ atterrissage sur le 3ᵉ repli. Première mesure : port (2,3) — voisine de
la **cible** — contre natif (2,4) — voisine de la **dernière victime**, avec les trois mutants
d'atterrissage **inertes**. Un banc de mutants qui ne mord pas est le symptôme, pas le verdict.

⚠ Et le premier rouge du gate de ciblage accusait le **port** : la cause était l'ordre des arguments
dans le probe (`get_invalid_target_reason(state, caster, target, ability)`). Inversés, `TARGETING_OPTIONS`
est lu sur un entier → `None` → retour 0 → **tout passe** : exactement la dégradation permissive que
la règle du masque décrit.

Gardes : `tests/engine/runner/test_940_kiss_of_death_offline.py` (17 tests — registre, ordinaux,
substrat ordonné, les quatre régimes de `PickLastN`, la clé LIVE, la forme de l'arbre ; contre-épreuve
**5/5 mutations du code font rougir**) et `tests/engine/runner/test_940_kiss_of_death_live.py`
(4 tests, un seul runner).

## 7. Résidus

* **`#940-r1`** — le `jumpTargetSelector` est **attribué** par l'ICF (§4), pas lu sous le nom de cette
  classe. Le trancher exige de lire le `MethodInfo*` du delegate en live.
* **`#940-r2`** — face **DÉCISION** non portée : `KissOfDeathPlaybook$$EvaluateNonComparable`
  (`NonComparablePlaybook<KissOfDeathAbility>`, ability id `0x454`) construit un `Bucket` de seuil
  `Fix64(2)` puis, pour chaque cible de `GetEligibleTargetsEntities(caster, casterPosition.MainTile)`,
  appelle `BasePlaybook$$GenerateAction` avec une utilité lue par trois appels d'interface non résolus.
* **Non porté, nommé** : `APickSelector$$AddForcedTargetsAndUpdateCandidates` (cibles forcées) —
  `PickLastN` porte `ignore_forced_targets` comme champ **transcrit** mais sans effet, exactement comme
  `PickFirstN`. Le seul call-site porté passe `0`.
* **Hypothèse assumée** : `OrderedSet$$Add` ne **remonte pas** un doublon en fin d'ordre (le port suit
  `dict[k] = v`). Inerte pour 1108 — `allow_repeat_targets = False` interdit de re-frapper une cible
  dans le même cast.
