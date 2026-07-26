# `PerformAIAction` (+ `GetAbilityStatModification`) — débloqueur transverse « faire agir une autre unité »

Build `gqfc5mff6c`. Statut : **PORTÉ ET VALIDÉ LIVE** via son premier consommateur
**SupremeCommander (1028, `astraCreed`)**, faces COMBAT **et** DÉCISION.

La chaîne qui alimente `GetAbilityStatModification` (`SwornProtector` → Kell → `ListenUpMaggots`)
est portée et confrontée live : **§5.1**. La face DÉCISION (`SupremeCommanderPlaybook`) : **§6**.

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

1. **`ListenUpMaggotsEffect` (effet `0x426`) — PORTÉ ET CONFRONTÉ LIVE** (#95-RESTE2, cf. §5.1) : la
   chaîne `SwornProtector` → Kell → `ListenUpMaggots` → `AddUnitActiveAbilityModification` est portée
   de bout en bout, donc `GetAbilityStatModification` n'est plus condamné à rendre 0 offline.
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

## 5.1. Chaîne `SwornProtector` → Kell → `ListenUpMaggots` — PORTÉE ET CONFRONTÉE LIVE (#95-RESTE2)

C'est la SEULE source native d'écriture dans `ActiveAbilityModificationsComponent` (xrefs exhaustives
de `IdunBattle.Operations.AddUnitActiveAbilityModificationOperation$$Execute`), donc le seul chemin
qui rende `IdunBattle.Entities.UnitExtensions$$GetAbilityStatModification` non nul.

### Les trois maillons (RE lue au décompilé, build `gqfc5mff6c`)

| Maillon | Artefact natif | Event | Port |
|---|---|---|---|
| 1. spawn de Kell | `…Loki.SwornProtectorAbility$$CreateTrigger` / `$$CreateBehaviour` (triggered 1050, passif `astraCreed`) | `On(PreUnitAbility=0x2b)` | `runner/operations/triggers/loki/sworn_protector.py::SwornProtectorSummonKellAbility` |
| 2. échange de position | `…Loki.SwornProtector_ProtectAbility$$CreateTrigger` / `$$CreateBehaviour` (triggered 1075, passif `astraSmnKell`) | `On(PreUnitAbility=0x2b)` | `…::SwornProtectorProtectSwitchAbility` |
| 3. pose du buff | `…Loki.ListenUpMaggotsAbility$$CreateTrigger` / `$$CreateBehaviour` (triggered 1063) | `On(AbilityInit=0x21)` | `…/listen_up_maggots.py::ListenUpMaggotsAddEffectAbility` |
| 4. écriture | `…Effects.Loki.ListenUpMaggotsEffect$$ApplyInternal` / `$$RevertInternal` (effet 0x426) | — | `entities/effects/loki/ability_modifications.py` + `runner/operations/ability_modifications.py` |

Détails structurants (tous LUS, pas déduits) :

- Le trigger de `SwornProtector` est un ET de **7** termes, dont `NOT
  HasTriggeredAbilityBeenTriggered(owner, this.Id)` (« **first** targeted », one-shot par bataille),
  `NOT AmountIsEqualOrGreater(UnitsWithId(Children(owner), astraSmnKell, 3), One@0xc0)` (Kell pas déjà
  là) et `AmountIsEqualOrGreater(CanAddUnit(AdjacentTiles(owner)), One@0xc0)` (un hex libre).
  `factory@0xc0` = la constante **1** du `.ctor` du `DSLFactory` (`+0xb8`=0, `+0xc0`=1, `+0xc8`=2,
  `+0xd0`=100, `+0xd8`=-1).
- Le behaviour de `SwornProtector` **déclenche lui-même** `SwornProtector_Protect` sur le summon
  (`If(CanSwitchPosition(owner), TriggerAbility(unitsC, 0x433))`) : le switch a donc lieu AVANT que
  l'attaque déclenchante ne se résolve → **c'est Kell qui encaisse**, dès le premier coup.
- `CanSwitchPosition(u)` = `NOT HasEffect(u, 0x1b = Taunted_OnlySpecificTargets, 0, 6)`.
- Le trigger de `ListenUpMaggots` est `df@0xa8 & HasUnit(Parent(caster@0x160), 3)`, où `df@0xa8` est le
  trigger PRÉ-CACHÉ de `IdunBattleLogic.Entities.DSLFactory$$InitializeShared` =
  `On(0x21 = AbilityInit) & df@0x128 & OwnerIsActor` — la MÊME base que toute la famille des
  owner-effects posés à l'init (`LifewardsAddEffectAbility$$CreateTrigger` = `return df@0xa8`).
- L'effet 0x426 est **porté par Kell** mais son `CreateTargetSelector` est **`Parent(Self@0x148)`** :
  `ApplyInternal` écrit sur **Creed**. `ApplyInternal` fait, dans cet ordre,
  `AddUnitActiveAbilityModification(target, 0x16, GetNumberConstant(0x16)=3)` puis
  `(target, 0x10, GetNumberConstant(0x10)=1)` ; `RevertInternal` = les mêmes appels en `-valeur`.

### Ground truth LIVE — l'ancienne conclusion de ce document est RÉFUTÉE

L'ancienne §5 affirmait « deux probes live, dont une avec Kell vivant, montrent que le natif summon
**2** gardes → modification nulle des deux côtés ». **C'est faux.** Mesure refaite (session 78, board
`MC1_67`, Creed attaqué par un `necroSpyder` — attaquant à faible dégât par coup, choisi pour que Kell
SURVIVE au coup déclencheur) :

| Observable | Kell en jeu | Contre-cas sans Kell (même board, même seed, même géométrie) |
|---|---|---|
| `astraSmnKell` présent, `alive` | oui, porteur de `ListenUpMaggotsEffect` | absent |
| gardes spawnés par le cast 1028 | **3** | **2** |
| garde ami à distance **2** rejoué par `PerformAIAction` | oui | oui |
| garde ami à distance **3** rejoué | **oui** | **non** |
| garde ami à distance **4** rejoué | non | — |

⇒ `nrOfSummons` **+1** (additif) et `range` **3** (OVERRIDE) sont tous deux NON NULS et
OBSERVABLES. Les probes antérieures mesuraient un état où Kell mourait du coup qui l'avait fait
apparaître (il prend le coup à cause du switch) — d'où le « 2 gardes » trompeur.

### Résidus de cette tranche (explicites)

- `SwornProtectorAbility$$GetSpawnTile` enveloppe son `CanAddUnit(AdjacentTiles(...))` dans un
  `SortTilesByUtilityForSummon` (moteur d'utilité IA complet, non porté) → la TUILE de spawn de Kell
  offline est la première tuile libre dans l'ordre du voisinage. Même collapse que `ForwardSpotter`.
- Le marqueur `SwornProtector_JustSummonedEffect` (0x4ce) est posé (`SpawnUnitOptions+0x10`) puis
  retiré DANS LE MÊME behaviour et n'est lu par aucun gate porté → non porté (observable nul), plutôt
  que de deviner ce slot d'options (`+0x18` = on-appearance, lui identifié).
- `Inform({0xb4: EntityId(caster)})` et `ResetPreviousPosition(owner)` = notification de vue et champ
  de pathfinding non matérialisé → no-op documentés.
- Le port n'émet `On(PreUnitAbility)` que depuis la voie d'attaque **normale** (`damage_ops.py`) ; le
  natif l'émet aussi pour les attaques d'**ability** → une ability offensive ciblant Creed ne réveille
  pas encore `SwornProtector` côté port (résidu partagé avec AnvilShield).
- `KillUnitOperation$$Execute` fait un `RemoveEffects` COMPLET ; le port n'en porte que la part
  `ability_modifications` (les stat-mods d'un cadavre ne sont lus par personne, un retrait global
  serait un changement transverse hors périmètre).

---

## 6. Face DÉCISION — `SupremeCommanderPlaybook`, PORTÉE **et CONFRONTÉE À L'IA NATIVE** (#119)

`IdunBattle.AI.Playbook.Loki.SupremeCommanderPlaybook` (`NonComparablePlaybook<0x404=1028>`) —
port : `engine/playbook/noncomparable/supreme_commander.py` ; probe :
`probe_119_supreme_commander_decision.py` ; garde : `tests/engine/test_supreme_commander_decision_live.py`.

- `.ctor` = `NonComparablePlaybook(0x404)` ; `.cctor` = `MIN_UTILITY = Fix64.FromInt(1)` = **1.0**.
- `ShouldEvaluate` :
  1. `if (BasePlaybook.EnemyWillBeKilledWithNormalAttack(unit)) return false;`
  2. `units = SelectUniqueUnits(ability.baseSelector@+0x80 + DSLFactory.AllDeadUnits(), ctx)` ;
     `if (!units.Any(u => IsFriendlyKell(u, unit))) return false;`
     — `IsFriendlyKell` = `u.GetComponent<ChildComponent>().ParentId(+0x10) == EntityId(caster)
     && UnitExtensions.IsFriend(u, caster)` = **il existe un enfant (vivant OU mort) du caster**.
     Le composant lu est **`ChildComponent`** (champ `ParentId`, `BEntityId` @+0x10 — offset
     confirmé live par `dumpEntityComponents` sur Kell), **pas** `ParentComponent` (dont le +0x10
     est `ChildrenIds`, une `List`). Les deux composants existent sur TOUTE unité, d'où l'absence
     de branche null côté natif. Le sélecteur amont est « toutes les vivantes » + « toutes les
     mortes » = toutes les unités des DEUX camps : c'est `IsFriend` qui filtre l'équipe ;
  3. `chance = Fix64(1/2) + FillUpStatComponent.RemainingPercentage(unit) / 2`, passée à l'iface
     `this+0x30` slot 4 (tirage) — même slot que `BasePlaybook$$ShouldEvaluate`.
- `EvaluateNonComparable` : bucket `(0, MIN_UTILITY=1)`, `GetEligibleTargetsSelectable(position.MainTile)`,
  utilité **plate `3/2` = 1.5** par cible, `Bucket.AddAction`.

### 6.1 Étage (3) : ce n'est pas une jauge abstraite, c'est le RATIO DE PV DU CASTER

`FillUpStatComponent.RemainingPercentage` = `Max(0, remaining@+0x18 / get_CurrentMaximumValue())`.
`ShouldEvaluate` fait le **même `GetComponent`** que la branche `param_2 == 5` de
`IdunBattle.Entities.UnitExtensions$$GetFillUpStatComponent` (même classe générique, même static de
type) : le stat interrogé est **5 = Health**. Donc `chance = 1/2 + hp/hpMax du caster / 2`, et **à PV
pleins la chance vaut 1** — l'étage (3) y est DÉTERMINISTE.

Mesures LIVE (`aiDryRunAllUnits` = `CalculateNextActionForUnit`, tirages consécutifs sur le même état) :

| PV du caster | chance attendue `1/2 + hp%/2` | cast natif observé |
|---|---|---|
| 100 % | 1.000 | **20/20** (et 20/20 sur un 2ᵉ couple board/seed) |
| 32.4 % | 0.662 | **31/40 = 0.775** |

Le tirage EXISTE (31/40 ≠ 40/40) et sa fréquence à PV réduits est incompatible avec `1/2`
(p ≈ 8·10⁻⁴) comme avec `hp%` (0.324) — cohérente avec la formule lue. **GAP assumé, borné** : le
port rend `True` dès que (1) et (2) passent, donc il SUR-PRÉDIT sous les PV pleins (probabilité
d'abstention native `(1 − hp%)/2`, au pire 1/2 à l'agonie). Même classe de gap que
`BlackRagePlaybook` (`GetUseProbability` = 0.4) : moteur déterministe, RNG d'IA non porté.

### 6.2 Le gate (2) : le lien enfant→parent n'est publié par AUCUN RPC

`ChildComponent.ParentId` n'apparaît ni dans `projectUnitsFull` (decisionView : id/visualId/pos/hp/
owner/team/alive/ctrl/hasAction/ranged/defeatedByMelee/killerId/abilities/effects), ni dans
`observeBattle`, ni dans `combatSnapshot`. Le port lisait `u["parentId"]` — clé **toujours absente**
→ gate (2) constamment `False` → `should_evaluate` constamment `False` → **playbook enregistré mais
mort** sur la face décision. Désaccord MESURÉ avec l'IA native (§6.3, ligne A) : le natif castait,
le port attaquait.

Le lien est donc reconstruit offline par `_kit_spawn_visual_ids`
(`engine/playbook/noncomparable/_base.py`) : **toute constante d'une ability du kit du caster dont la
valeur nomme une unité connue de gameconfig désigne une unité que ce kit fait apparaître**. Le scan
des 669 unités rend un vocabulaire étroit et exclusivement spawn-related — `unitId`(48),
`unitToSpawn`(5), `unitId_2`(5), `summonId`(3), `heroId`(3), `unitIds`(2), `affectedUnitIds`(1). Pour
Creed : `{astraSmnKell, astraSmnGuardsman, astraNpc1Guardsman}` — `affectedUnitIds` apporte le
visualId **live** du garde (`astraNpc1Guardsman`), dont l'id de config (`astraSmnGuardsman`) diffère.
Un enfant = une unité de ce set, **de la même équipe** (`IsFriend`), vivante ou morte.

**Domaine d'exactitude** : le couple (visualId de summon, équipe) identifie le parent tant qu'une
équipe ne porte pas DEUX summoners du même summon. **Résidu pour lever l'approximation** : publier
`ChildComponent.ParentId` dans `projectUnitsFull` — le port consommerait alors directement la clé
`parentId` (elle existe déjà côté offline, `engine/entities/selectors.py::Parent`). Non fait ici :
un changement de hook exige une réinjection Frida, impossible sans casser les sessions concurrentes.

### 6.3 Confrontation à l'IA native — états CRAFTÉS, oracle = un tour d'IA

Oracle : `CalculateNextActionForUnit` (RPC `aiDryRunAllUnits`, read-only, `mutated=false` vérifié) +
un tour **réellement joué** (`playTurn`) sur le cas nominal. **Jamais** `aiPredict`/`GetAllPredictions`
(preview du seul vecteur Attack). Géométrie pilotée ; rendez-vous DÉRIVÉ du `boardGraph` (une tuile à
6 voisins jouables) et non codé en dur — `SwornProtectorAbility$$GetSpawnTile` exige un voisin LIBRE
de la cible, sans quoi Kell ne spawne pas et le scénario est silencieusement vide.

| état | gates natifs visés | natif | port |
|---|---|---|---|
| A — Kell allié, PV pleins, ennemis increvables | (1)F (2)V (3)=1 | **caste 1028 sur lui-même** | idem, même cible |
| A2 — idem sur board `C3_01` / seed 777 | idem | **caste 1028** | idem |
| B — Creed jamais attaqué (aucun enfant) | (2) FAUX | attaque (69) | idem, même cible |
| C — DEUX Creed, **un seul Kell, camp adverse** | (2) selon l'équipe | mon Creed **se déplace**, le leur **caste 1028** | idem pour les deux, même destination |
| D — Kell allié mais ennemi sure-kill | (1) VRAI | attaque (69), même tuile | idem |

**C est le point discriminant** : dans le MÊME état, deux Creed et un seul Kell — une règle naïve
« il existe un Kell sur le plateau » répondrait pareil pour les deux ; le natif non. Contre-épreuve
faite : en restaurant le corps pré-#119 (`u["parentId"]`), A et C-adverse **désaccordent**.

**Non couvert** : l'étage (3) sous les PV pleins (gap assumé ci-dessus, mesuré mais non porté) ; le
cas « deux summoners du même summon dans une équipe » (hors domaine d'exactitude du §6.2) ; le
second cast d'affilée (cooldown de l'ability, jamais atteint dans ces états).

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
