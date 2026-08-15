# #955 — `SummaryExecution` (Yarrick) et `Possession` (Archimatos)

Deux passifs de kit, chacun le dernier item manquant de son kit ; les deux porteurs
(`astraYarrick`, `blackPossession`) sont au pool, aucune injection catalogue.

## 1. Recensement — par le bloc `methodPointers`, jamais par grep de nom

Le tableau de pointeurs du PE est lu (`GameAssembly.dll` du build `rnca9r7q6c`), résolu pointeur
par pointeur contre `data/symbols/rnca9r7q6c/ghidra/functions.tsv`, et **segmenté par classe**.
Un corps est **PROPRE** quand il n'est le corps d'aucune autre classe ; les autres sont fondus par
l'ICF et n'apparaissent donc sous **aucun** nom exploitable au grep.

| classe | slots | propres | faces DÉDUPLIQUÉES (invisibles au grep) |
|---|---|---|---|
| `…Abilities.Active.Loki.SummaryExecutionAbility` | 3 | **2** | `.ctor` (= `UnityEngine.Scripting.RequiredByNativeCodeAttribute$$.ctor`, corps vide) |
| `…Abilities.Active.Loki.SummaryExecutionAddBaseEffectAbility` | 3 | **1** | `CreateTrigger` (corps ICF partagé, **58** références), `.ctor` |
| `IdunBattle.Entities.Effects.Loki.SummaryExecutionEffect` | 4 | **3** | `CreateTargetSelector` (= `…SummaryExecution_AlwaysEffectEffect$$CreateTargetSelector`) |
| `IdunBattle.Entities.Effects.Loki.SummaryExecution_AlwaysEffectEffect` | 3 | **3** | — |
| **total `SummaryExecution`** | **13** | **9 (69 %)** | |
| `…Abilities.Active.Loki.PossessionAbility` | 3 | **2** | `.ctor` |
| **total `Possession`** | **3** | **2 (67 %)** | |

**La face cachée qui CHANGE le port** : `SummaryExecutionEffect` n'a **pas** de
`CreateTargetSelector` propre — son slot pointe sur le corps de son voisin
`SummaryExecution_AlwaysEffectEffect`. Les DEUX effets ont donc **le même sélecteur d'aura**
(`Friends(Owner, UnitsWithTrait(AllAliveUnits, BattleFatigue))`). Le lire « Owner » (effet SELF,
comme le piège de #952) ou l'omettre aurait rendu `1031` inerte.

**Ce que le tableau du dispatch donnait pour `Possession` était FAUX** : les quatre classes
`AttemptedPossession*` (`_PossessedEffect`, `…Ability`, `…Playbook`) appartiennent à
`ActiveAbilityType.AttemptedPossession = 1101`, l'**active de `thousSorcerer`** (Thaumachus), pas
au passif `TriggeredAbilityType.Possession = 1034` de `blackPossession`. Elles sont **déjà
portées** (`engine/runner/abilities/loki/attempted_possession.py`,
`engine/playbook/noncomparable/attempted_possession.py`,
`engine/entities/effects/loki/possession.py`). `Possession` n'a **ni effet, ni playbook** : son
bloc entier tient en trois slots.

## 2. `SummaryExecution` — les arbres (mirror 1:1)

```
SummaryExecutionAddBaseEffectAbility$$CreateTrigger
    = <DSLTriggers+0x30>                    # trigger d'INIT partagé, cf. #952 :
                                            # On(0x21 = AbilityInit) & <YesTrigger> & get_OwnerIsActor
SummaryExecutionAddBaseEffectAbility$$CreateBehaviour
    AddDynamicStatModifierEffectToOwner( effectType = 0x413 = EffectType.SummaryExecution_BaseEffect,
                                         statType   = 0     = StatType.Attack,
                                         turns      = null (PERMANENT),
                                         isHidden   = false )

SummaryExecution_AlwaysEffectEffect$$CreateTargetSelector
    Friends( Owner@<DSLSelectors+0x30>,
             UnitsWithTrait( AllAliveUnits@<DSLSelectors+0x20>,
                             0x3f7 = UnitTrait.BattleFatigue,
                             3 = UnitSelectionType.OnlyAliveAndTargetable ),
             3 )
SummaryExecution_AlwaysEffectEffect$$GetDynamicStatModificationAmount
    ConfigVar( 0x409 = TriggeredAbilityType.SummaryExecution,
               EffectSource( Get(effect) ),
               8 = AbilityVariableType.extraDmg )

SummaryExecutionAbility$$CreateTrigger
      NOT HasEffect(Owner@+0x30, 0x407 = EffectType.SummaryExecution_Effect,
                    onlyActive = false, targetType = 6)
    & On(0x33 = EventTriggerType.PreUnitFled, ownerNeedsToBeAlive = true)
    & AreFriends(Owner@+0x30, Actor@<DSLSelectors+0x40>, 0, anyEntity = false)
    & TriggeringAbilityIs( 0x401 = TriggeredAbilityType.BattleFatigue )
SummaryExecutionAbility$$CreateBehaviour
      AddDynamicStatModifierEffectToOwner( 0x407 = SummaryExecution_Effect, StatType.Attack,
                                           null, false )
    & Kill( Owner@+0x30, Actor@+0x40, KillUnitBehaviourOptions.ForDirectKill() )

SummaryExecutionEffect$$CreateTargetSelector        = LE MEME CORPS que celui de 1043 (ICF)
SummaryExecutionEffect$$GetDynamicStatModificationAmount
    ConfigVar( SummaryExecution, EffectSource(Get(effect)), 9 = AbilityVariableType.extraDmg_2 )
SummaryExecutionEffect$$ApplyInternal
    AStatModifierEffect.ApplyInternal(owner, target, effect)
    ; BaseEffect.AddSubEffect(effect, target, 0x437 = EffectType.IgnoreBattleFatigue, turns = null)
```

Les deux `.ctor` d'effet appellent
`AStatModifierEffect..ctor(sourceAbility, unitEffectType = null, canBeImmuneTo = false,
keepOnRevive = true, isMultiply = false)` — donc canal **ADDITIF** sur le stat, jamais
multiplicatif.

**L'ANNULATION DE LA FUITE EST DANS `FleeOperation`, PAS DANS LE PASSIF.**
`IdunBattle.Operations.FleeOperation$$Execute` commence par

```
IOperationProcessor.<slot 81 = EvaluateAbilities>( actor = unit, caster = unit, target = unit,
                                                   eventType = 0x33 = PreUnitFled,
                                                   abilityOrEffect = triggeringAbilityOrEffect )
if (UnitExtensions.IsDead(unit)) return;        // <- la fuite est ABANDONNEE
```

C'est le « executed **instead** » de l'i2 : le `Kill` du passif rend l'unité morte, et le natif
sort avant `RecordFlee` / `RemoveUnit` / `UnitFlag 9` / `On(0x34 = UnitFled)`.

## 3. `Possession` — l'arbre (mirror 1:1)

```
PossessionAbility$$CreateTrigger
      ( On(0x35 = EventTriggerType.PostUnitKill, ownerNeedsToBeAlive = true)
        & get_OwnerIsActor )
    & ( AreEnemies(Owner@+0x30, Target@<DSLSelectors+0x60>, 0)
        & NOT IsObjectOrSteppable(Target@+0x60) )
    & NOT TriggeringAbilityIs( 0x438 = TriggeredAbilityType.ItsGonnaBlow )

PossessionAbility$$CreateBehaviour
    unitId  = AbilityConfiguration.GetStringConstant(cfg, 0 = AbilityConstantType.unitId)    # blackSmnBloodletter
    unitId2 = AbilityConfiguration.GetStringConstant(cfg, 4 = AbilityConstantType.unitId_2)  # thousSmnBlueHorror
    optsA   = SpawnUnitOptions.WithStatsFromConfig (cfg, abilityState, null, null)   # -> ordinal 1
    optsB   = SpawnUnitOptions.WithStatsFromConfig2(cfg, abilityState, null, null)   # -> ordinal 2
    hex     = PickRandomly( FreeTilesOrAdjacentFreeTiles( Tiles(Target@+0x60) ),
                            amount = 1, allowDuplicates = false,
                            maxDuplicatesAllowed = 0x7fffffff, ignoreForcedTargets = false )
    cond    = NOT IsDefeatedByMeleeAttack(Target@+0x60, countRevived = true, countResurrected = true)
    return    If( cond,
                  Spawn(Owner@+0x30, hex, unitId2, optsB),     # kill NON-melee -> Blue Horror
                  Spawn(Owner@+0x30, hex, unitId,  optsA) )    # kill MELEE     -> Bloodletter
```

`WithStatsFromConfig` / `WithStatsFromConfig2` sont deux **thunks** vers la même surcharge à
5 arguments, avec `ordinal = 1` / `ordinal = 2` — c'est l'ordinal qui choisit
`summonHp`/`summonDmg` (1) contre `summonHp_2`/`summonDmg_2` (2). La surcharge appelle
`SetStatFromConfig` **sept** fois : `0x29 summonHp -> 5`, `0x2a summonDmg -> 0`,
`0x2b summonArmor -> 0x10`, `0x56 summonBlockChance -> 7`, `0x55 summonBlockDmg -> 8`,
`0x54 summonCritChance -> 9`, `0x57 summonCritDmg -> 10` ; le gameconfig de `Possession` ne
fournit que les deux premières paires.

`IsDefeatedByMeleeAttack(u, r, s)` = `AmountIsGreaterThanZero(UnitsDefeatedByMeleeAttack(u, r, s))`,
et `UnitsDefeatedByMeleeAttackSelector$$IsValidUnit` exige `<composant>+0x178 != 0` (le drapeau
« défait par une attaque de MÊLÉE ») **et** (`HasFlag(9 = Fled)` | `HealthComponent.IsDead` |
`countRevived && HasFlag(0x14)` | `countResurrected && HasFlag(0xe)`).

## 4. Surcharges tranchées par l'ADRESSE RÉELLE de la cible du `call` (`E8 rel32`)

* `DSLFormulas$$ConfigVar` a **cinq** surcharges ; les deux `GetDynamicStatModificationAmount`
  visent `180ea83e0` = `ConfigVar(abilityType, unit, variableType)` — donc le **premier**
  argument `0x409` est un `TriggeredAbilityType`, pas un `AbilityVariableType`, et le
  `8`/`9` final est la variable. Lire `ConfigVar(8, …)` comme dans #952 aurait inversé les deux.
* `DSLBehaviors$$If` a trois surcharges ; celle visée prend `(IAbilityTrigger, ifBehaviour,
  elseBehaviour)`.
* `DSLSelectors$$PickRandomly` a deux surcharges ; celle visée prend `amount : System.Int32`.
* `BaseEffect$$AddSubEffect` a deux surcharges ; celle visée est **sans** `EffectBuilder`
  (`effect, target, effectType, turns`).
* Les deux `AbilityOrEffect$$op_Implicit` des `TriggeringAbilityIs` sont lus **aux octets** :
  `BA 01 04 00 00` (`mov edx, 0x401`) à `SummaryExecutionAbility$$CreateTrigger+0x11c`, et
  `BA 38 04 00 00` (`mov edx, 0x438`) à `PossessionAbility$$CreateTrigger+0x13a` — le décompilé
  ne montre qu'un `local_28` non initialisé.

## 5. Ce que cette tranche a dû AJOUTER EN AMONT

`EventTriggerType.PreUnitFled` (0x33) **n'avait AUCUN émetteur** dans tout `engine/**` : un
balayage ne le trouvait que dans le mirror d'enum et dans un commentaire. Le port de
`FleeOperation$$Execute` (`runner/operations/behaviour.py`) commençait à `RemoveUnit`, alors que
le natif ouvre sur les deux gestes cités au §2. **Sans eux, `SummaryExecutionAbility` n'aurait
jamais pu se poser** — et le « executed instead » de l'i2 n'aurait eu aucun mécanisme, puisque
c'est le `return` sur `IsDead` qui ANNULE la fuite, pas le passif.

Le canal `TriggerEvent.triggering_ability` est seedé par l'**unique appelant porté** de
`FleeOperation.execute` (`BattleFatigueAbility.execute_behaviour`), qui est précisément l'ability
que `TriggeringAbilityIs(0x401)` compare. Sur le vecteur MORT, ce champ-là (`CurrentAbility@+0x60`)
reste vide — mais ce n'est PAS le canal que `TriggeringAbilityIs` lit : c'est `+0x98`, et il y est
renseigné (`state.trigger_ability_type`). Cf. #955-r1 au §7.

Second ajout : la feuille `Spawn` gagne `stat_key_suffix`, mirror de l'`ordinal` de
`WithStatsFromConfig{,2}`. Sans lui, les deux summons de `Possession` auraient pris **les mêmes
stats** — le bon `unitId` avec le mauvais jeu de variables, en silence.

## 6. Validation

**Offline** — `tests/engine/test_955_summary_execution_possession_offline.py`, **15 tests** :
ids et enums cités au site, les deux registres (et le fait que 1031 n'est PAS dans le registre
d'INIT), le sélecteur PARTAGÉ, les deux magnitudes, la structure des trois arbres, le couplage
`ordinal ↔ constante`, et l'étage amont `PreUnitFled` (dont l'ORDRE : l'émission précède le
retrait du plateau).

**Live** — `probe_955_summary_execution_possession.py` + `tests/engine/runner/…_live.py`, board
`MC1_67`, seed `4321`, géométrie **calculée** depuis le `boardGraph` puis **assertionnée** contre
les positions réelles (un bras qui n'obtient pas sa configuration fait ÉCHOUER le test, jamais un
skip).

| volet | régime | natif | port | écart |
|---|---|---|---|---|
| `possession` / `melee` | Archimatos à **d = 1** de sa victime | `blackSmnBloodletter` @(2,3) | idem, **même tuile** | 0 |
| `possession` / `ranged` | Archimatos à **d = 2** | `thousSmnBlueHorror` @(1,3) | idem, **même tuile** | 0 |
| `summary` / aura 1043 | Guardsman (trait `BattleFatigue`) | Attack **+400** | +400 | 0 |
| `summary` / témoin | `tauCrisis`, **sans** le trait | **0** | 0 | 0 |
| `summary` / porteur | Yarrick lui-même (pas le trait) | **0** | 0 | 0 |
| `execution` | l'allié adjacent au Guardsman meurt | Guardsman **TUÉ**, Yarrick `[1031, 1043]` | `temoins_fled = []`, `[1031, 1043]`, immunité posée sur l'autre | 0 |

Les deux bras de `possession` **DISCRIMINENT** (summons différents) : le probe REFUSE de conclure
s'ils rendent le même, parce que c'est exactement ce qu'un port lisant la mauvaise adjacence
produirait. Le volet `summary` a son propre témoin discriminant — l'allié **sans** le trait, qui
ne doit rien recevoir.

**Six mutants, tous mordent, chacun sur son axe :**

| mutant | volet | effet mesuré |
|---|---|---|
| `m_registre` | possession | 0 summon sur les deux bras |
| `m_melee` | possession | les deux summons ÉCHANGÉS (le gate melee/ranged est load-bearing) |
| `m_effet` | summary | la part sous clé d'aura tombe à `0 / 0 / 0` |
| `m_trait` | summary | `400 / 400 / 400` — le témoin et le porteur reçoivent à tort |
| `m_registre` | execution | le Guardsman **FUIT** (`temoins_fled = [106]`), pas de 1031, pas d'immunité |
| `m_vecteur` | execution | idem — c'est la mesure que l'étage `PreUnitFled` est load-bearing |

### Deux observables qui NE DISCRIMINENT PAS, et c'est mesuré

1. **Le TOTAL du stat-mod ne prouve rien.** `load_state` seede la modification depuis
   `combatSnapshot`, donc la part CAPTURÉE est là de toute façon — sous la clé opaque
   `CAPTURED_SOURCE` si rien ne l'attribue. Mesure : les **deux** mutants du volet `summary`
   laissaient le total à **400**. Ce qui mesure le port, c'est la part portée par la **clé
   d'AURA**, que `attribute_aura_stat_modifiers` ne pose que si l'effet déclare l'interface
   `aura_stat_modification_*` ET sélectionne cette unité.
2. **`alive == False` ne sépare pas l'exécution de la fuite.** Une unité ENFUIE est
   `alive = False` côté port aussi (`FleeOperation$$Execute` appelle `RemoveUnit` AVANT de poser
   `UnitFlag 9`, #429-r1-r3-r1-r2), donc les deux mutants du volet `execution` la rendaient
   « morte » comme le nominal. Le discriminant est le **flag `Fled`** et l'effet 1031.

### Trois montages qui ont RATÉ, et ce qu'ils mesurent

* **Deux bras dans la MÊME bataille** : le Bloodletter invoqué au 1ᵉʳ bras est `ai_controlled`
  (trait `Summon`), donc `PlayAutomaticUnits` le fait jouer au turn-start suivant et il achève la
  seconde victime — `applyAction` rend `{"ok": false, "error": "stage Finished (need Running)"}`.
  Un build par bras.
* **Un seul ennemi** : le tuer finit la bataille et le `decisionView` d'après ne publie plus aucun
  summon (les deux bras rendaient `summons: []` alors que le même bras melee, joué avec un second
  ennemi vivant, rend bien `blackSmnBloodletter`). D'où le **figurant** à d ≥ 4.
* **Guardsmen adjacents entre eux** : ils se posent sur des tuiles libres du rayon 2 autour de la
  cible, par tirage — 3 essais sur 3 les ont rendus à d = 2 ou 3. Le trigger de `BattleFatigue`
  exigeant l'adjacence STRICTE, c'est un **allié placé adjacent à la cible** qui fait la victime.

### Ce qui n'est PAS couvert

* Le gate `NOT TriggeringAbilityIs(ItsGonnaBlow)` — **branché sur le bon canal depuis #955-r1**
  (`+0x98`, pas `+0x60`) et gardé par un test à deux bras ; il reste inerte EN JEU faute de poseur
  porté d'`ItsGonnaBlow` (blocage `porteur`, pas `seeding`).
* La face **PRÉDICTION** des deux auras. Elle est **structurellement satisfaite** et c'était déjà
  écrit avant cette tranche : `playbook/prediction/normal_attack.py` calcule
  `attack_base = attack_current − aura_real + aura_cand`, et son commentaire #57a nomme
  explicitement `SummaryExecution_BaseEffect 1043 : +400 flat aux Friends(UnitsWithTrait),
  sélecteur SANS nœud d'adjacence`. Le sélecteur n'ayant AUCUNE géométrie, `aura_real == aura_cand`
  et l'expression se réduit à `attack_current`, qui porte déjà le mod. **Porter
  `create_aura_attack_bonus` pour ces deux effets serait donc un ajout INERTE** — et le +400 mesuré
  au live confirme au chiffre près la valeur que ce commentaire annonçait.
* Le `Maybe(GetFleeChance)` — chance non sourçable offline. Le port FUIT quand éligible ; le probe
  rejoue plusieurs seeds et échoue franchement si aucune fuite ne se déclenche (« non confronté »
  est alors un résultat, pas un vert). Mesure : **1 essai sur 1** a suffi.
* `HasEffect(..., targetType = 6)` : le 4ᵉ argument (`EffectTargetType`) n'a pas de contrepartie
  portée. Sans conséquence ici — l'effet 1031 est posé sur le porteur, donc présent sous n'importe
  quelle lecture.

## 7. Résidus

* **#955-r1 — FERMÉ (2026-08-15). La prémisse était FAUSSE : le canal n'était pas ABSENT, il était
  MAL CHOISI.** La fiche disait « le vecteur MORT ne seede aucune ability déclenchante » et classait
  le blocage en `seeding`. Or `IdunBattleLogic.Entities.DSLTriggers$$TriggeringAbilityIs` prend le
  slot `DSLSelectors+0x90` → `AbilityTypeSelector.TriggeringAbilitySelector$$Select`, qui lit
  `AbilityEntities+0x98` — et `+0x98` **est** renseigné sur ce vecteur : c'est le `killTrigger`
  recopié depuis `KillUnitOptions+0x04` par `IdunBattle.Operations.KillUnitOperation$$Execute`, que
  le port pose sur `state.trigger_ability_type` le temps du drain depuis #301. Le champ VIDE est
  `CurrentAbility@+0x60` (le `memset(.., 0x128)`), et c'est LUI que `possession.py` lisait
  (`ev.triggering_ability`).

  Le gate lit désormais `state.trigger_ability_type`, exactement comme
  `haze_of_corruption._triggering_ability` le fait déjà sur le même vecteur. Garde :
  `test_955_summary_execution_possession_offline.py::test_955r1_le_gate_ItsGonnaBlow_lit_le_canal_0x98_et_MORD`
  (deux bras : `+0x98` refuse, `+0x60` seul ne change rien).

  **Ce qui reste n'est plus un `seeding` mais un `porteur`** : `ItsGonnaBlow` (passif de la caisse
  de munitions npc) n'a aucun poseur porté, donc `+0x98` ne vaudra jamais `1080` aujourd'hui. Fait
  déjà écrit à l'identique dans `barbed_ovipositor.py` et `head_claimer.py`, qui portent le MÊME
  conjoint — pas de résidu de plus pour le redire une quatrième fois.

  **Bonus de la même tranche** : le second résidu de `possession.py`, le marqueur
  `IsDefeatedByMeleeAttack` (`UnitComponent+0x178`), est lui aussi porté (#951-r1) — l'approximation
  positionnelle n'est plus qu'un repli sur `None`.
* ~~**#955-r2**~~ — **FERMÉ EN REFUS : le port était juste sur les quatre.** Détail : **§7bis**.
* ~~**#955-r3**~~ — **FERMÉ.** L'`ApplyInternal` est désormais joué **par cible**, à chaque réveil
  du driver d'aura. Et sa prémisse d'inatteignabilité était fausse : détail **§7ter**.

## 7bis. `#955-r2` — le résidu était FAUX, et faux d'UN BIT

**Ce qu'il annonçait** : « quatre consommateurs, un seul porte `allowSteppable` ; les trois
collapses impératifs sont RESTRICTIFS, le summon se pose une case plus loin ». **Ce que la relecture
mesure** : les trois collapses sont **fidèles**, et leur ajouter la branche serait un écart
**PERMISSIF** — l'inverse exact.

**La cause de l'erreur : le nœud a DEUX surcharges, et le résidu a lu la mauvaise.**

```
DSLSelectors$$FreeTilesOrAdjacentFreeTiles(tiles)                 # 2 args
    isSteppable = <dsl>.<+0x88 = DSLTriggers>.<+0x48>             #   pris dans SON PROPRE corps
DSLSelectors$$FreeTilesOrAdjacentFreeTiles(tiles, isSteppable)    # 3 args
                                                                  #   reçu de l'APPELANT
```

Le résidu a lu le corps de la surcharge **2 args** — d'où son « `isSteppable = <DSLTriggers+0x48>`,
donc `allowSteppable` TOUJOURS VRAI » — puis l'a attribué aux call-sites de la surcharge **3 args**.
Or, **LU aux octets** (`mov r8, [reg+0x40]`, r8 = 3ᵉ argument x64), les trois call-sites portés en
collapse passent **`+0x40`** :

| call-site natif | surcharge | `isSteppable` | `allowSteppable` | port |
|---|---|---|---|---|
| `Ambush_SummonAbility$$GetSummonBehaviour` | 3 args | `+0x40` | **faux** | `genestealer::_free_tile_or_adjacent` |
| `HypersensoryAbilitiesAbility_MoveAndSpawnDecoy$$CreateBehaviour` | 3 args | `+0x40` | **faux** | idem (2ᵉ call-site) |
| `CosmicHorror_OnKillAbility$$CreateBehaviour` | 3 args | `+0x40` | **faux** | `cosmic_horror::_decoy_tile_for_kill` |
| `PossessionAbility$$CreateBehaviour` | 2 args | `+0x48` | **vrai** | `possession_spawn_tree(allow_steppable=True)` |

**Les deux slots sont adjacents, et l'un est la NÉGATION de l'autre** — c'est ce qui rend la
confusion muette. `IdunBattleLogic.Entities.DSLTriggers$$.ctor`, lu :

```
+0x40 = new <trigger sans champ>(0)                      // NU     -> ShouldTrigger toujours VRAI
+0x48 = AbilityTrigger$$op_LogicalNot( new <même type>(0) )  //      -> toujours FAUX
+0x70 = new <même type>(0)                               // déjà nommé `YesTrigger` par le port
```

et `IdunBattle.Entities.Selectors.CanAddUnitTileSelector$$Select` **INVERSE** ce qu'il reçoit :
`allowSteppable = !(<+0x28>.ShouldTrigger(entities, 0x20))`. Donc `+0x40` ⇒ `allowSteppable` **faux**,
`+0x48` ⇒ **vrai**. Le ctor n'appelle `op_LogicalNot` **qu'une fois**, et range son résultat en
`+0x48` (`mov [rdi+0x48], rax` immédiatement après le `call`) — c'est le fait qui donne leur sens
opposé aux deux slots, et l'étage 1 de la garde le re-dérive du PE à chaque passe.

**Ce que ça aurait coûté de « corriger »** : le summon d'Ambush, le decoy de Cosmic Horror et celui
d'Hypersensory se seraient posés **sur un mur, un décor ou un token** — là où le natif refuse.

Garde : `tests/engine/runner/test_955r2_free_tiles_steppable_offline.py` — 3 étages binaires (le
ctor, les trois call-sites, le quatrième qui n'en charge **aucun** r8) + le port des deux côtés,
avec sa contre-épreuve mordante sur le **même** état (`allow_steppable=False` rend `[]`,
`True` rend la tuile du `Steppable`).

## 7ter. `#955-r3` — le 4ᵉ point du driver d'aura, et une inatteignabilité qui n'en était pas une

**La prémisse a été re-mesurée, et elle ne tient PAS.** Le résidu écrivait : « aucun montage porté ne
produit ce régime — le trait est statique dans le gameconfig, et les seuls porteurs sont des summons
créés avec ». C'est le **mauvais axe**. Le sélecteur est
`Friends(Owner, UnitsWithTrait(AllAliveUnits, BattleFatigue))` : ce qui compte n'est pas qu'une unité
**acquière** le trait, c'est qu'une unité qui le **porte déjà** entre dans `AllAliveUnits` **après**
la matérialisation de 1031. Un summon fait exactement cela — et `operations/spawn.py` **réveille
déjà** `refresh_aura_stat_modifiers`. Le stat-mod suivait donc, l'immunité non : régime **atteignable**,
et silencieux (le symptôme n'apparaît qu'au prochain `BattleFatigue`, où l'unité fuit au lieu d'ignorer).

**Ce qui a été ajouté** — un 4ᵉ point à l'interface duck-typée du driver, mirror de l'étage natif qui
manquait :

```
RefreshEffectsOperation$$UpdateEffectTargets
    ApplyEffectsForTargets(targetsToAdd, ...)
        foreach target : effect.<slot 0xe = BaseEffect$$Apply>(owner, target, effectEntity)
                             -> <slot 0x548 = <Effect>$$ApplyInternal>(owner, target, effect)
```

`aura_sub_effects_on_apply() -> tuple[SubEffectSpec, ...]`, déclaré par `SummaryExecutionEffect`
seul, joué par `aura_stat_mods._apply_aura_sub_effects` aux **deux** foyers du driver
(`refresh_aura_stat_modifiers` et `attribute_aura_stat_modifiers`) — donc automatiquement aux
**quatre** sites de câblage existants (`snapshot.load_state`, `movement`, `spawn`, le behaviour du
trigger), sans en toucher un seul.

**Le poseur bespoke du behaviour est RETIRÉ** : il y avait sinon deux foyers pour le même
`ApplyInternal`, dont un qui ne joue qu'une fois. La trace `immunised` du retour est désormais
**dérivée** de l'état.

* **Idempotence** : le port n'a pas la liste `EffectComponent.Targets@+0x48` par instance (le driver
  ré-évalue le sélecteur à chaque réveil), donc l'« entrée » est dérivée de la **présence** du
  sous-effet — le gate « déjà présent » d'`AddEffectOperation`. Trois réveils ⇒ une seule instance.
* **Aucun symétrique au retrait, et c'est LU** : le bloc de `SummaryExecutionEffect` porte `.ctor`,
  `ApplyInternal` et `GetDynamicStatModificationAmount` — **pas** de `RevertInternal`. Une cible qui
  sort du sélecteur garde son immunité côté natif aussi ; elle ne part qu'avec le parent, par
  `RemoveEffectOperation$$RemoveSubEffects`.
* **Résidu nommé** : le lien `parent_type` n'est pas posé (`AddEffectOperation.execute` ne l'expose
  pas). Sans effet observable tant que 1031 est permanent et one-shot par bataille.

Garde : `tests/engine/runner/test_955r3_apply_internal_par_cible_offline.py` — le régime entrant, la
contre-épreuve mordante (hors sélecteur, jamais), l'idempotence sur trois réveils, et le cran qui
interdit de hisser l'interface sur la base commune (1043 est posée au **chargement** : l'y mettre
immuniserait tout le monde dès le premier tour et viderait le passif de son objet).

## 8. Ce que ce lot mesure sur le CRITÈRE de groupement

Recensement par le bloc `methodPointers` : **13 slots / 9 corps propres (69 %)** pour
`SummaryExecution`, **3 / 2 (67 %)** pour `Possession` — deux proportions **quasi identiques**, et
pourtant les deux items n'ont pas coûté la même chose : `SummaryExecution` a exigé un **étage
amont entier** (le vecteur `PreUnitFled` et son annulation, absents de tout `engine/**`) là où
`Possession` n'a demandé qu'un paramètre à une feuille existante.

⇒ **La proportion de corps propres n'a pas prédit ici**, contrairement à #952. Ce qui a prédit,
c'est une chose que ni les tables ni le bloc ne portent : **l'événement dont le trigger dépend
a-t-il un ÉMETTEUR côté port ?** `Possession` s'abonne à `On(PostUnitKill)`, câblé et consommé
depuis longtemps ; `SummaryExecution` s'abonne à `On(PreUnitFled)`, qui n'existait que dans le
mirror d'enum. Ce test-là se fait en une commande (`git grep <EventTriggerType> -- engine/`) et il
départage le port d'une demi-heure du port d'une demi-journée. La face cachée du bloc, elle
(le `CreateTargetSelector` fondu de 1031), n'a rien coûté **parce qu'elle a été lue** — c'est
l'omettre qui aurait coûté.
