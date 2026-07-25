# `PerformAIAction` (+ `GetAbilityStatModification`) — débloqueur transverse « faire agir une autre unité »

Build `gqfc5mff6c`. Statut : **PORTÉ ET VALIDÉ LIVE** via son premier consommateur
**SupremeCommander (1028, `astraCreed`)**.

---

## 1. Chaîne native (VAs complètes)

### 1.1 Face COMBAT (l'action s'exécute)

```
DSLFactory.PerformAIAction(selector, asGroup, resetTurnFlags)      @180df8990
  -> PerformAIActionBehaviour..ctor(selector@+0x50, asGroup@+0x58,
                                    resetTurnFlags@+0x59)          @180fcbda0
  -> PerformAIActionBehaviour.Execute(this, entities, processor)   @180fcba10
        units = selector.Select(entities)                          (iface slot 4)
        if (!asGroup) foreach u in units: proc.<slot 0x34>(u, resetTurnFlags)
        else                              proc.<slot 0x35>(units, resetTurnFlags)

Core.Services.OperationProcessor.ComputerAction(Unit, bool)        @180e07330   (slot 0x34)
Core.Services.OperationProcessor.ComputerAction(IEnumerable, bool) @180e07360   (slot 0x35)
  -> IdunBattle.Operations.ComputerActionOperation.Execute(Unit, bool)     @180e641e0
  -> IdunBattle.Operations.ComputerActionOperation.Execute(IReadOnlyList, bool) @180e63d80
        [ saved = UnitFlagsComponent.RemoveTurnFlags(flags, true, true)    @180fad310 ]
          IAiControl.ExecuteFor(unit | group)                              (slots 5 / 6)
        [ ComputerActionOperation.SetUnitTurnsFlags(unit, saved)           @180e645b0 ]

IdunBattle.Core.Services.AiControl.ExecuteFor(Unit)                @180ffbda0
      UNE passe : DefaultPlayerStrategy.CalculateNextActionForUnit @1810b42e0
      (-> <>d__7.MoveNext @1810c0c10 -> GetUnitTactic(u) -> tactic.CalculateNextActionForUnit)
      drainée, puis AiControl.ApplyAiMessages @180ffb3a0.
IdunBattle.Core.Services.AiControl.ExecuteFor(IEnumerable<Unit>)    @180ffbeb0
      BOUCLE while(messages != vide) : DefaultPlayerStrategy.CalculateNextActionForUnitGroup
      @1810b4280 -> DefaultGroupOperator.<...>d__6.MoveNext @1811974c0 :
          u = PickNextUnit(group)                                  @181183d50
              -> AnAiGroupOperator.GetValidUnits                    @1811833e0
                 = HasActionLeft(u) @180ed50e0 && !IsDead(u) && BaseUnitComponent.aiActions@+0x60 < 0x3e9
              -> picker d'utilité (iface slot 1, poids operator+0x30)
          if IsDead(u) -> messages vides -> FIN
          BaseUnitComponent.aiActions@+0x60 += 1
          GetUnitTactic(u).CalculateNextActionForUnit(u)
```

**Le détail qui rend un port « plausible et faux » si on le devine** — `resetTurnFlags` :
`RemoveTurnFlags(flags, true, true)` efface `{Moved(0), Teleported(0xc), ArrivedAtFinalTile(1),
NoActionAvailable(4), ActiveAbilityUsed(2), TurnFinished(3), TurnFinishedForced(0x1b)}` **et rend la
struct des flags qui étaient présents** ; `SetUnitTurnsFlags` les **re-pose un à un** après l'action.
Donc :

1. l'unité agit **même si elle avait déjà fini son tour** — et c'est ce reset qui la rend *valide*
   (`GetValidUnits` teste `HasActionLeft` = `!Has(NoActionAvailable)`) ;
2. **l'action supplémentaire NE CONSOMME PAS le tour de la cible** (état de tour rendu inchangé).

**Quand s'insère l'action** : ni au turn-start ni à la fin du tour — **inline, pendant l'exécution de
l'ability**, entre les nœuds du behaviour. Cascade live du cast SupremeCommander (ordre observé) :
`ActionsAvailable(Creed)=0` → `AtomicGroup{ spawn u92, spawn u94, TurnFinished(u92/u94)=1,
ActionsAvailable(u92/u94)=0 }` → **`Group#11 e=u94` (move) puis `Group#11 e=u92` (move)** →
`TurnFinished(Creed)=1` + `ActiveAbility 1028 CanStillBeUsed=0`. Les deux summons agissent donc
**après avoir été marqués `TurnFinished`** par le spawn, et **avant** la clôture du tour du caster.

### 1.2 `GetAbilityStatModification`

```
IdunBattle.Entities.UnitExtensions.GetAbilityStatModification(unit, AbilityVarOrConst)  @180ece900
  -> ActiveAbilityModificationsComponent.Get(key)                                       @180f8f570
       Dictionary<AbilityVarOrConst, ModificationConfig> @+0x10 ; TryGetValue ? value : 0
     (écriture : .Add @180f8f2a0 -> ModificationConfig.Add @180fa5170 = value += delta puis
      clamp `if (cap.HasValue && cap < value) value = cap`)
```

- **xrefs EXHAUSTIVES** du getter : **2 call-sites, tous deux dans `SupremeCommanderAbility.
  ExecuteBehaviour @18120df30`** (@18120e09b clé `0x10` = nrOfSummons, @18120e17a clé `0x16` = range).
  Aucun autre appelant dans le build.
- **Écriture** : `OperationProcessor.AddUnitActiveAbilityModification @180e06ec0` ->
  `AddUnitActiveAbilityModificationOperation.Execute @180e522b0`. **Seule source** appelante :
  `ListenUpMaggotsEffect.ApplyInternal @180f56590` / `RevertInternal @180f56740` (le passif de
  `astraSmnKell`, ciblant `Parent(self)` = Creed, `+GetNumberConstant(0x16)=3` et
  `+GetNumberConstant(0x10)=1` ; ability `ListenUpMaggotsAbility` `CreateBehaviour @181221cc0` =
  `AddEffect(0x426, Self)`, `CreateTrigger @181221d20` = `<trigger@0xa8> & HasUnit(Parent(caster), 3)`).

---

## 2. Consommateur validé : SupremeCommander (1028, `astraCreed`)

`SupremeCommanderAbility.ExecuteBehaviour @18120df30` (mirror lu, pas déduit) :

```
unitId   = GetStringConstant(cfg, 0)                          # astraSmnGuardsman
nSummons = GetNumberConstant(cfg, 0x10)                       # nrOfSummons = 2
ids      = GetStringArrayConstant(cfg, 0x3e)                  # affectedUnitIds
modN     = GetAbilityStatModification(caster, VarOrConst(0x10))
range    = GetNumberConstant(cfg, 0x16)                       # range = 2
modR     = GetAbilityStatModification(caster, VarOrConst(0x16))
if (modR != 0) range = modR                                   # OVERRIDE (≠ additif !)
spawnB   = Spawn(caster, PickRandomly(CanAddUnit(AdjacentTiles(caster)), nSummons + modN),
                 unitId, SpawnUnitOptions.WithStatsFromConfig(cfg, level))
aiB      = PerformAIAction(UnitsWithIds(SurroundingFriends(caster, casterTile, range, 1, 3), ids), 1, 1)
AActiveAbility.ExecuteAtomic(this, spawnB, entities, 0x48)
AActiveAbility.Execute(this, aiB, entities)
```

Les **deux** consommations de `GetAbilityStatModification` ont des sémantiques **différentes** :
`nrOfSummons` **additif**, `range` **override si non nul**.

`UnitsWithIds @180e00230` = union sur `ids` de `UnitsWithIdSelector.Select @180f04390`
(= `HasUnitId(u, id) @180ed70c0` = `GetUnitIdWithoutLevel(GetUnitId(u)) == id`).
`affectedUnitIds = "astraSmnGuardsman,astraNpc1Guardsman"` — la liste couvre l'id de config du summon
**et** l'id du NPC pré-placé. `astraSmnGuardsman.visualId` (gameconfig) = `astraNpc1Guardsman`, d'où
le `visualId` rendu par `decisionView` pour les gardes invoqués.

---

## 3. Forme du port

| Artefact natif | Port | Nature |
|---|---|---|
| `PerformAIActionBehaviour.Execute @180fcba10` | `engine/runner/abilities/behaviours/ai_control.py::PerformAIAction` | **feuille DSL** |
| `ComputerActionOperation.Execute @180e641e0/@180e63d80`, `SetUnitTurnsFlags @180e645b0` | `engine/runner/operations/summon_ai.py::ComputerActionOperation` | **Operation impérative** |
| `AiControl.ExecuteFor @180ffbda0/@180ffbeb0`, `HasActionLeft @180ed50e0` | `summon_ai.py::ai_control_execute_for{,_group}`, `has_action_left` | impératif |
| `UnitFlagsComponent.RemoveTurnFlags @180fad310` | `components.py::UnitFlagsComponent.remove_turn_flags` **rend désormais le set des flags retirés** | composant |
| `ActiveAbilityModificationsComponent` (`Get`/`Add`), `UnitExtensions.GetAbilityStatModification @180ece900` | `components.py::ActiveAbilityModificationsComponent`, `get_ability_stat_modification` | composant + extension |
| `DSLFactory.UnitsWithIds @180e00230` | `entities/selectors.py::UnitsWithIds` | **sélecteur DSL** |
| `PickRandomly(tiles, n) @180df8e70` enveloppant le tile-selector de `Spawn` | `behaviours/summon.py::Spawn(pick_n=…)` (fold, convention existante) | fold |
| `SupremeCommanderAbility.ExecuteBehaviour @18120df30` | `engine/runner/abilities/astramilitarum.py` (2 arbres + classe, registre 1028) | arbres DSL |

**Frontière DSL/impératif respectée** : `PerformAIAction` (nœud) appelle `ComputerActionOperation`
(mutateur) ; aucun ciblage recâblé à la main — le set d'unités **émerge** de
`UnitsWithIds(SurroundingFriends(...))`.

**Deux exécutions top-level** (`ExecuteAtomic` puis `Execute`) → deux arbres exécutés successivement,
avec le `DslContext` **re-matérialisé entre les deux** : l'`AbilityEntities` natif porte une **ref
d'état** (les sélecteurs du 2ᵉ arbre voient les gardes tout juste spawnés) alors que le port fige la
LISTE d'unités à la construction. Sans cette re-matérialisation, `SurroundingFriends` manquerait les
gardes = **no-op silencieux**. (Cas particulier du chantier #5 `DslContext live-state`.)

---

## 4. Validation (adversariale)

Fichier : `scripts/python/tests/engine/runner/test_supreme_commander_live.py` (11 tests, **11 PASS,
0 skip**), runners `--board MC1_67` (seed 777) et `--board C3_01` (seed 31337).

**Effet OBSERVÉ live** (pas « le code est atteint ») : après le cast, **2 gardes apparaissent adjacents
à Creed puis QUITTENT l'anneau de spawn dans la même transaction** (positions finales à distance ≥ 2
du caster) **et attaquent** — l'ennemi perd des PV *pendant le cast* (mesuré : −2163). Ils avaient
pourtant été marqués `TurnFinished=1 / ActionsAvailable=0` par le spawn juste avant.

| Test | Ce qu'il prouve |
|---|---|
| `test_spawn_count_port_matches_live` | port et natif spawnent le même nombre de gardes |
| `test_summon_stats_bit_exact_vs_live` | `WithStatsFromConfig` : `hpMax` live == `summonHp[level] × mult` == port |
| `test_no_ability_stat_modification_live` | modification d'ability **nulle côté natif observé** (voir §5) |
| `test_perform_ai_action_moves_fresh_summons_live` | **discriminant live** : un garde a quitté l'anneau de spawn |
| `test_perform_ai_action_moves_fresh_summons_port` | le port reproduit le discriminant |
| `test_ai_action_reaches_and_attacks` | **conséquence** : l'ennemi perd des PV pendant le cast, live ET port |
| `test_counter_case_without_perform_ai_action` | **contre-cas** : même état, même arbre de spawn, SANS le nœud → tous les gardes restent à distance 1 |
| `test_turn_flags_saved_and_restored` | une cible `TurnFinished`+`ActiveAbilityUsed`+`Moved` agit, et **retrouve ses flags** après |
| `test_ally_outside_affected_ids_not_forced_to_act_{live,port}` | **généralisation** (autre board/roster) : un allié à portée hors `affectedUnitIds` (et ayant déjà agi) n'est PAS rejoué |
| `test_ability_stat_modification_semantics_offline` | les 2 sémantiques : `+1` → 3 gardes (additif), `mod 3` → radius **3** (override, pas 2+3) |

**Mutants** (plugin jetable hors dépôt) — les tests DISCRIMINENT :

| Mutation | Tests tués |
|---|---|
| `PerformAIAction.execute` → no-op | `..._moves_fresh_summons_port`, `test_ai_action_reaches_and_attacks` |
| `UnitsWithIds.select` → passe-tout | `test_ally_outside_affected_ids_not_forced_to_act_port` (l'allié entre dans `ai_units`) |
| `SetUnitTurnsFlags` → no-op | `test_turn_flags_saved_and_restored` |

**Zéro-régression** (tests ciblés rejoués) : `test_turnflow_live`, `test_turnflow_endturn_flags`,
`test_summon_not_activated_live`, `test_summon_ability_ports_live`, `test_summon_spawn_live`,
`test_cultdemagogue_migration_live`, `test_thebetrayer_take_turn_migration_live` → **tous verts**.
`test_skitarii_turn_live::test_skitarii_played_by_generic_ai_pass` échoue — **échec PRÉ-EXISTANT** :
reproduit à l'identique (`BFS 3->3`) sur le commit de base `9cf5e40` avec le patch *stashé*.

---

## 5. Résidus / limites (explicites)

1. **`ListenUpMaggotsEffect` (effet `0x426`) non porté** → offline le
   `ActiveAbilityModificationsComponent` reste vide et `GetAbilityStatModification` rend 0. **Ce n'est
   pas une dégradation silencieuse** : deux probes live (dont une avec **Kell VIVANT en jeu au moment
   du cast**) montrent que le natif summon **2** gardes, donc modification nulle côté natif aussi →
   *agreement*. Le chemin non-nul est exercé **offline** en injectant la modification (sémantiques
   additive/override vérifiées). Porter `ListenUpMaggots` exige la chaîne `SwornProtector` → spawn de
   Kell → triggered ability → `AddEffect(0x426)`.
2. **Ordre intra-groupe** : natif = argmax d'utilité du picker (`PickNextUnit @181183d50`, iface
   slot 1) ; port = **ordre du sélecteur**. Live observé sur SupremeCommander : les deux gardes
   agissent dans l'ORDRE INVERSE de leur spawn → divergence d'ordre possible (sans incidence quand les
   unités du groupe sont interchangeables, cas des gardes clones).
3. **Compteur `BaseUnitComponent.aiActions@+0x60`** : mirroré *localement* (dict de la boucle) avec le
   cap natif `< 0x3e9`, pas persisté sur l'entité.
4. **Fin de la passe AI d'une unité** : le natif la clôt via les messages de la tactique ; le port pose
   explicitement `NoActionAvailable(4)` après chaque passe (= ce que lit `HasActionLeft`, et ce que
   montre le live `UnitStats_ActionsAvailable=0` par unité juste après son action).
5. **`UnitsWithIds` compare `visualId`** (le port n'a pas d'id de config par-unité) : exact pour
   SupremeCommander dont `affectedUnitIds` liste les DEUX formes. Un futur consommateur ne listant
   qu'une forme exigerait un id de config dans le `State`.
6. **`PickRandomly` RNG-exact** : gap connu #215 (ordre/coût du tirage non calé) → les TUILES de spawn
   choisies offline peuvent différer du live. Aucune assertion du test n'en dépend.

---

## 6. Face DÉCISION — RE faite, port **volontairement non fait** (reachability non prouvable offline)

`IdunBattle.AI.Playbook.Loki.SupremeCommanderPlaybook` (`NonComparablePlaybook<0x404=1028>`,
`.ctor @181162c50`) :

- `ShouldEvaluate @181162890` :
  1. `if (BasePlaybook.EnemyWillBeKilledWithNormalAttack(unit)) return false;`
  2. `units = SelectUniqueUnits(ability.baseSelector@+0x80 + DSLFactory.AllDeadUnits(), ctx)` ;
     `if (!units.Any(u => IsFriendlyKell(u, unit))) return false;`
     — `IsFriendlyKell @181162720` = `u.<ParentComponent>+0x10 == EntityId(caster) && IsFriend(u, caster)`
     = **il existe un enfant (vivant OU mort) du caster**, c.-à-d. Kell (`SwornProtector`) ;
  3. seuil = `1/2 + FillUpStatComponent.RemainingPercentage(unit) / 2`, passé à l'iface `this+0x30`
     slot 4 (chance).
- `EvaluateNonComparable @181162410` : bucket `MIN_UTILITY` du cctor, `GetEligibleTargetsSelectable`,
  utilité **plate `3/2`** par cible, `Bucket.AddAction`.

**Décision** : ne PAS porter. Le gate (2) exige un enfant du caster ; offline la seule source d'enfant
avant le premier cast est `SwornProtector` (spawn de Kell) — **non porté**. Un port produirait un
playbook qui rend systématiquement `False` : du **code enregistré-mais-mort**, exactement ce que la
doctrine interdit d'introduire. À porter **avec** `SwornProtector`/Kell (voir backlog).

---

## 7. Ce qu'il reste à faire pour les AUTRES consommateurs (au-dessus de ce socle)

> **MISE À JOUR — tâche #94 ([case-94-summon-consumers.md](case-94-summon-consumers.md))** : **Waaagh
> (1058)** et **CultDemagogue (1179, retrofit)** sont PORTÉS + validés live au-dessus de ce socle.
> **SendInTheNextWave (1016), Incursion (1021) et Poxwalkers (1040) ne sont PAS des consommateurs de
> `PerformAIAction`** (décompilé : aucun appel à `@180df8990`) — ils utilisent le sous-behaviour
> **on-appearance** du `Spawn` (`SpawnUnitOptions+0x18`), respectivement `UseNormalAttackIfAble
> @180e01870` (1016, 1021) et `PerformAIAttackFromCurrentPosition @180df8a10` (1040). Ils sont portés +
> validés live par la même tâche, mais via d'autres primitives. La liste ci-dessous est conservée telle
> qu'elle a été écrite ; les corrections sont dans la case-doc #94.

Le socle fournit : le nœud `PerformAIAction(selector, asGroup, resetTurnFlags)`, l'Operation
`ComputerActionOperation`, `AiControl.ExecuteFor{,_group}`, `UnitsWithIds`, `Spawn(pick_n=…)`,
`get_ability_stat_modification`. Reste, par consommateur :

- **Waaagh (1058, `orksWarboss`, `ExecuteBehaviour @18122b010`)** — appelle `PerformAIAction` **deux
  fois**. Site 2 déjà lu : `WaaaghAbility.GetTriggerSummonsBehaviour @18122c260` =
  ```
  unitId = GetStringConstant(cfg, 0)
  sel    = Friends(caster@0x160, UnitsWithVisualId(VisualUnitIdFromUnitId(Get(unitId)), 1))
  PerformAIAction(sel, asGroup=1, resetTurnFlags=1)          # @18122c310
  ```
  → **mêmes booléens que SupremeCommander** ; le socle s'applique tel quel. **Manquent** :
  `DSLFactory.UnitsWithVisualId`, `DSLFactory.VisualUnitIdFromUnitId` et `DSLFactory.Get` (nœud
  valeur-string de config) — sélecteur **board-wide** (aucun rayon), à ne pas confondre avec
  `UnitsWithIds`. Site 1 (@18122b306, dans `ExecuteBehaviour`) : reste à RE, ainsi que le corps
  (buffs/summons). **N'utilise PAS** `GetAbilityStatModification` (xrefs exhaustives : 2 sites, tous
  deux SupremeCommander). Porteur `orksWarboss` : vérifier le gate pool (`rl_duel build --list-pool`).
- **SendInTheNextWave (1016)** — face DÉCISION **déjà portée**
  (`playbook/noncomparable/send_in_the_next_wave.py`). Reste la face COMBAT : constantes
  `nrOfSummons=2 / unitId=astraSmnGuardsman` (mêmes clés que SupremeCommander) → le couple
  `Spawn(pick_n=…)` + éventuel `PerformAIAction` se réutilise tel quel ; RE de son `ExecuteBehaviour`
  requise (sélecteur de tuiles et présence/absence du nœud AI).
- **Incursion (1021)**, **Poxwalkers (1040)** — face DÉCISION déjà portée
  (`playbook/noncomparable/{incursion,poxwalkers}.py`). Face COMBAT à RE : mêmes briques.
- **CultDemagogue (1179)** — **déjà porté**, mais avec une feuille bespoke `PerformAINeophyteTurn`
  (`abilities/genestealer.py`) qui **fusionne** le sélecteur et l'action AI, et **n'implémente pas** le
  cycle sauvegarde/restauration des flags (`PerformAIAction(sel, 0, 1)` natif @1811cdc30 : `asGroup=0`,
  `resetTurnFlags=1`). → **retrofit** : remplacer par
  `PerformAIAction(UnitsWithIds(SurroundingFriends(TargetTile(), range), unitId_2), as_group=False,
  reset_turn_flags=True)`. Non fait ici (hors périmètre : le cas ne demandait qu'UN consommateur).
- **BlackRage_ActivationAbility (`CreateBehaviour @180e19ef0`)** et
  **ReanimationBeam (`GetSummonsTakeActionBehaviour @1811ff510`)**, **AdaptiveStrategy** — mêmes
  briques ; le résidu « act-again » documenté dans `effects/loki/status.py:447` et
  `abilities/loki/strike.py:548` est désormais **débloqué**.
