# Tâche #94 — Consommateurs `PerformAIAction` / SPAWN : Waaagh 1058, SendInTheNextWave 1016, Incursion 1021, Poxwalkers 1040, retrofit CultDemagogue 1179

Build `gqfc5mff6c`. Socle réutilisé : [`case-perform-ai-action.md`](case-perform-ai-action.md)
(`PerformAIAction @180df8990` → `ComputerActionOperation @180e641e0`/`@180e63d80` →
`AiControl.ExecuteFor @180ffbda0`/`@180ffbeb0`). Tranche amont : [`case-220/p0-summon.md`](case-220/p0-summon.md).

Statut : **les 5 items sont PORTÉS et CONFRONTÉS AU LIVE** (`tests/engine/runner/test_summon_consumers_live.py`,
23 tests ; `tests/engine/runner/test_cultdemagogue_migration_live.py`, 6 tests).

---

## 0. Correction de prémisse — qui consomme réellement `PerformAIAction`

Le regroupement de la tâche supposait que 1016 / 1021 / 1040 étaient des consommateurs de
`PerformAIAction`. **Le décompilé le réfute** : leurs `ExecuteBehaviour` n'appellent JAMAIS
`DSLFactory.PerformAIAction`. Ils appartiennent à la famille **SPAWN + sous-behaviour on-appearance**
(`SpawnUnitOptions+0x18`) :

| id | ability | vecteur d'action des summons | nœud natif |
|---|---|---|---|
| 1058 | Waaagh | `PerformAIAction(…, asGroup=1, resetTurnFlags=1)` | `@180df8990` |
| 1179 | CultDemagogue | `PerformAIAction(…, asGroup=0, resetTurnFlags=1)` | `@180df8990` |
| 1016 | SendInTheNextWave | `UseNormalAttackIfAble(ActiveTarget@0x180, Target@0x178)` | `@180e01870` |
| 1021 | Incursion | `UseNormalAttackIfAble(ActiveTarget@0x180, Entity(cible))` | `@180e01870` |
| 1040 | Poxwalkers | `PerformAIAttackFromCurrentPosition(ActiveTarget@0x180)` | `@180df8a10` |

Conséquence : le socle `PerformAIAction` s'applique **tel quel** à 1058 et 1179 ; 1016/1021/1040 ont
demandé d'autres primitives (`ActiveTarget`, `ChainBehaviour`, on-appearance du `Spawn`).

---

## 1. Carte des sélecteurs cachés du `DSLFactory` (posée par `InitializeShared @180df2670`)

```
0x78 AllTiles · 0x80 <toutes les unités> · 0xb8 Direct(0) · 0xc0 Direct(1) · 0xc8 Direct(2)
0xd0 Direct(100) · 0xd8 Direct(-1)
0x148 Owner · 0x150 Effect · 0x158 Actor · 0x160 Caster · 0x168 CasterTile · 0x170 CasterTiles
0x178 Target · 0x180 ActiveTarget · 0x188 PreviousActiveTarget · 0x190 TargetTiles · 0x198 UnitFeetTiles
```
(0xb8…0xd8 lus dans `DSLFactory..ctor @180e020b0` ; 0x148…0x198 dans `InitializeShared @180df2670` ;
noms via `runner-engine.md` §654.)

**`ActiveTarget@0x180`** est le pivot de cette tâche : c'est l'ÉLÉMENT COURANT lié par le behaviour
englobant — le **summon fraîchement posé** dans un sous-behaviour on-appearance, l'**élément d'itération**
dans un `ChainBehaviour`. Porté : `DslContext.active_target` + nœud `selectors.ActiveTarget`.

---

## 2. Waaagh (1058, `orksWarboss`) — `ExecuteBehaviour @18122b010`

**CINQ exécutions top-level successives**, chacune `AActiveAbility.Execute(Group(<b>, caster@0x160, <id>))` :

```
opts   = SpawnUnitOptions.WithStatsFromConfig(config, level)
spawnB = Spawn(caster@0x160,
               PickRandomly(CanAddUnit(AdjacentTiles(casterTile@0x168)),
                            GetNumberConstant(0x10)=nrOfSummons=2),
               GetStringConstant(0)=orksOrkBoys, opts)            # corps == GetSummonBehaviour @18122c120
buffB  = GetBuffBehaviour(level)                                  # @18122b900
moveB  = MoveUnit(caster@0x160,
                  First(SortTilesByUtility(GetPossibleMovementTiles(target@0x178),
                                           caster@0x160, 0x20), 1),
                  <5 sélecteurs d'options NULS>)
atkB   = GetAttackBehaviour(level)                                # @18122b700
aiB    = PerformAIAction(Friends(caster@0x160,
                                 UnitsWithVisualId(VisualUnitIdFromUnitId(Get(GetStringConstant(0))), 1),
                                 3), asGroup=1, resetTurnFlags=1) # corps == GetTriggerSummonsBehaviour @18122c260

Execute(Group(spawnB,0x22)) ; Execute(Group(buffB,0x25)) ; Execute(Group(moveB,0x23)) ;
Execute(Group(atkB,0x20))   ; Execute(Group(aiB,0x28))
```

- **`GetBuffBehaviour @18122b900`** : sélecteur = `Unique( caster@0x160 + AdjacentFriends(caster,1,3)
  + UnitsFromFaction(Friends(caster, @0x80), 5=Orks, 3) )` → le caster, ses alliés **adjacents** (toute
  faction) et **TOUS** ses alliés de faction **Orks** (board-wide). Trois effets, durée `Direct(1)@0xc0` :
  `AddStaticStatModifierEffect(sel, 1099 Waaagh_ExtraMovement, stat=MOVEMENT(1), Direct(GetNumberConstant(0xe)=extraMovement))`
  `& AddEffect(0x44c=1100 Waaagh_ExtraDamage)` `& AddEffect(0x44d=1101 Waaagh_ExtraHits)`.
- **`GetPossibleMovementTiles @18122c060`** :
  `TilesUnitCanMoveToChargeTarget(caster@0x160, casterTile@0x168, target, UnitMovementRangeWithBonus(caster, 1099, Direct(extraMovement)), canReachOnly=0)`.
  **`UnitMovementRangeWithBonus @180dff050` = `If(HasEffect(caster,1099), StatAmount(caster,MOVEMENT), Sum(StatAmount(caster,MOVEMENT), bonus))`**
  → ANTI-DOUBLE-COMPTE : l'effet 1099 étant déjà posé (Group buff `0x25` s'exécute AVANT Group move
  `0x23`), la portée lit la stat MOVEMENT *déjà bonifiée*. **C'est ce qui rend le port de
  `applied_stat_mods` sur 1099 OBLIGATOIRE** : sans lui, la charge perdrait son +1 hex.
- **`GetAttackBehaviour @18122b700`** :
  `If(IsAdjacent(caster@0x160, target@0x178, 3), UseActiveAbility(caster, target, UnitNormalAttackType(caster))) & KillDeadUnits(Killer(ActiveTarget@0x180), AllUnits())`.
  Le `3` d'`IsAdjacent` ne va PAS au prédicat par-paire (slot iface `0x5f = AreNeighbours`) → seuil
  **dist == 1 STRICT** (même lecture que VigilanceEternal `@18122a580`).
- **`PerformAIAction`** : sélecteur **BOARD-WIDE**. `UnitsWithVisualId @180e00e90` =
  `UnitsWithIdSelector(ctx, factory+0x80, visualId, mode)` — la source est le slot « toutes les unités »,
  **aucun rayon**. À NE PAS confondre avec le `UnitsWithIds(SurroundingFriends(caster, range))` de
  SupremeCommander. Mécaniquement : le Waaagh fait rejouer **TOUS** les Ork Boyz alliés du plateau, pas
  seulement ceux du cast courant.
- Waaagh **n'utilise PAS** `GetAbilityStatModification` (xrefs exhaustives : 2 sites, tous SupremeCommander).

**Port** : `engine/runner/abilities/orks.py` (`waaagh_spawn_tree` / `waaagh_buffed_units_selector` /
`waaagh_buff_tree` / `waaagh_move_range` / `waaagh_charge_tile` / `waaagh_move_tree` /
`waaagh_attack_tree` / `waaagh_ai_tree` / `WaaaghAbility`) + effets `WaaaghExtraMovementEffect`
(stat-mod EAGER, template `BlackRage_ExtraMove` validé live) / `WaaaghExtraDamageEffect` /
`WaaaghExtraHitsEffect` (marqueurs) dans `entities/effects/loki/status.py` + registre `factory.py`.

**Validé live** (board MC1_67, seed 31337, `orksWarboss` vs `necroWarden`+`necroDestroyer`) :
count de spawn port == live == `nrOfSummons`=2 ; PV du summon bit-exact `summonHp[level]×mult` ; les
3 effets posés sur le caster live **et** port ; `move_range` == MOVEMENT post-buff (anti-double-compte) ;
`ai_units` ⊇ les Ork Boyz spawnés ; **discriminant** : un Ork Boy a quitté l'anneau de spawn live ET port ;
**contre-cas** : le même arbre privé de `PerformAIAction` les laisse tous à distance 1.
**Généralisation** (board `C3_01`, roster `orksWarboss + orksNob`) : l'allié Ork est **BUFFÉ**
(`UnitsFromFaction(Orks)`) mais **PAS** poussé à agir (`UnitsWithVisualId(orksOrkBoys)`) — les deux
sélecteurs, distincts, sont discriminés.

---

## 3. SendInTheNextWave (1016, `astraYarrick`) — `ExecuteBehaviour @181206490`

```
unitId = GetStringConstant(0)=astraSmnGuardsman
opts   = SpawnUnitOptions.WithStatsFromConfig(config, level)
opts.+0x18 = UseNormalAttackIfAble(ActiveTarget@0x180, Target@0x178)     # @180e01870
Execute( Spawn(caster@0x160, GetSpawnTilesSelector(level), unitId, opts) )
```
- **`GetNumSummons @181206a70`** =
  `Min( Sum(Direct(GetNumberConstant(0x10)=nrOfSummons), Count(Attackable(Friends(owner@0x148, AllDeadOrResurrectedUnits())))), Direct(GetVariableForLevel(0x31)=maxSummons[level]) )`
  → « la vague suivante grossit avec les pertes », plafonnée.
- **`GetSpawnTilesSelector @181206cc0`** =
  `PickRandomly(preferred, Min(n, Count(preferred))) + PickRandomly(possible, n - k)` où
  `possible = CanAddUnit(SurroundingTiles(target@0x178, 0, r))` et
  `preferred = AttackTilesForTarget(possible, target)`, `r = GetSpawnedUnitRange @181206ed0`
  (service `ability+0x20` vslot 0xaa sur l'unitId ; = 2, la portée d'arme de `astraSmnGuardsman`).
- **`GetDynamicInvalidTargetReason @181206740`** : la cible n'est valide que s'il existe ≥ 1 tuile de
  spawn dans ce rayon (reason 2 sinon).

**Port** : `engine/runner/abilities/astramilitarum.py`
(`send_in_the_next_wave_num_summons` / `send_in_the_next_wave_spawn_tiles` / `send_in_the_next_wave_tree`
/ `SendInTheNextWaveAbility`).
**Résidus documentés** : (a) `SITNW_SPAWNED_UNIT_RANGE = 2` en constante (le service de config d'unités
n'est pas exposé offline) ; (b) `AttackTilesForTarget` = identité offline (aucun modèle de cover / ligne
de vue) ; (c) `Attackable` = identité sur des cadavres.
**Validé live** : count port == live == 2 ; tous les Cadians dans le rayon 2 de la cible (live et port) ;
on-appearance → la cible encaisse pendant le cast, live et port.
**Généralisation** : la formule de count DYNAMIQUE est exercée en injectant N cadavres alliés dans l'état
runner — `count == min(2+N, maxSummons)` sur toute la plage, plafond compris.

---

## 4. Incursion (1021, `blackPossession`) — `ExecuteBehaviour @1811e9fe0`

```
opts.+0x18 = UseNormalAttackIfAble(ActiveTarget@0x180, Entity(<cible résolue>))
spawnB = Spawn(caster@0x160, ActiveTarget@0x180, GetStringConstant(0)=blackSmnBloodletter, opts)
Execute( ChainBehaviour(Null(), Func(GetNextSpawnTile), Direct(GetNumberConstant(0x3c)=maxSummons=6),
                        spawnB, UnitTimelines.TypeToTimeline()) )
```
- **`GetNextSpawnTile @1811ea520`** (reconstruit à CHAQUE itération, `Func<>` natif) =
  `PickRandomly(CanAddUnit(AdjacentTiles(target@0x178)), ConditionalAmount(cond, 1@0xc0, 0@0xb8))`
  avec `cond = (IsAlive(caster) & IsAlive(target)) & IsInRange(caster, target, Direct(GetNumberConstant(0x16)=range=2))`
  — c'est EXACTEMENT `GetContinueTrigger @1811ea420`. La chaîne s'arrête dès que le sélecteur est vide.
- **Conséquence mécanique** : les Bloodletters attaquant à l'apparition, une cible qui MEURT en cours de
  chaîne rend `IsAlive(target)` faux → arrêt avant `maxSummons`.
- **Piège de targeting** (mesuré live) : `abilityTargets` accepte une cible à dist 5 alors que l'exécution
  exige `dist <= range = 2` → un cast « légal » à dist 5 produit **0 summon** (natif ET port).

**Port** : `engine/runner/abilities/blacklegion.py` (`incursion_next_spawn_tile` / `incursion_tree` /
`IncursionAbility`) + combinateur `entities/behaviours.py::ChainBehaviour`.
**Validé live** : count port == live ; tous les Bloodletters adjacents à la cible ; borne `maxSummons`
respectée ; on-appearance → dégâts sur la cible live et port. **Contre-cas offline (×2)** : cible déjà
morte → 0 itération ; caster téléporté hors portée → 0 itération.

---

## 5. Poxwalkers (1040, `deathBlightbringer`) — `ExecuteBehaviour @181208b80`

```
range  = ContagionsOfNurgle_ArmorReduction_Effect.CalculateRange(owner)   # @180f39940
tiles  = CanAddUnit(SurroundingTiles(owner@0x148, 0, range))
cnt    = <tiles>.Count(entities)                                          # EAGER (vslot +0x2b8)
amount = Divide(RandomAmount(cnt*var0x3a, cnt*var0x3b), Get(100), mode=1=Ceiling)
opts.+0x18 = PerformAIAttackFromCurrentPosition(ActiveTarget@0x180)
Execute( Spawn(owner@0x148, PickRandomly(tiles, amount), GetStringConstant(0)=deathPoxwalker, opts) )
```
- **`CalculateRange @180f39940`** = `s = GetStat(unit, 0xc=TurnsStarted, Current) ; s>2 ? (s>4 ? 3 : 2) : 1`.
- **`var0x3a` = `chance`, `var0x3b` = `chance_2`** (POURCENTAGES par tuile libre) ;
  **`RandomAmount.Calculate @180f22160` = `rng.<slot 2>(min, max + 1)` → borne haute INCLUSE**.
- SELF-CAST (`SpawnPoxwalkersPlaybook @18115c6f0` : la seule cible éligible est SOI) → `owner@0x148` ≡ caster.

**Port** : `engine/runner/abilities/deathguard.py` (`contagions_of_nurgle_range` /
`poxwalkers_spawn_tiles` / `poxwalkers_count` / `spawn_poxwalkers_tree` / `SpawnPoxwalkersAbility`).
**Validé live** : rayon == bande `TurnsStarted` ; count port ET live dans la bande config
`[ceil(n·chance/100), ceil(n·chance_2/100)]` (on confronte la BANDE, pas un scalaire : l'ordre RNG du
tirage n'est pas calé bit-à-bit — gap déjà connu de `_pick_randomly_n`) ; tous les Poxwalkers dans le
rayon ; un `PerformAIAttack` fire PAR summon.
**Généralisation** : les TROIS bandes de `CalculateRange` exercées en pilotant la stat `TurnsStarted`.

---

## 6. Retrofit CultDemagogue (1179, `genesPrimus`) — `ExecuteBehaviour @1811cdc30`

Arbre natif (association du décompilé) :
```
op_Addition( op_Addition( Group(SpawnDecoys, Null, 100), Group(SpawnNeophytesOnDecoys, Null, 0x65) ),
             PerformAIAction( UnitsWithId( SurroundingEnemies(target@0x178, GetNumberConstant(0x44)=range, 1, 3),
                                           GetStringConstant(4)=unitId_2, 3 ),
                              asGroup=0, resetTurnFlags=1 ) )
```
Le port portait le 3e étage comme une feuille **bespoke** `PerformAINeophyteTurn` qui (a) FUSIONNAIT
sélecteur et action et (b) appelait `decide_and_apply` **à nu** — donc **sans le cycle de flags de tour**.
Retrofit : feuille DSL `PerformAIAction` au-dessus, `ComputerActionOperation` (impératif) en dessous.

**`SurroundingEnemies` a DEUX formes natives** (lues au décompilé) — piège majeur du retrofit :
- 6 args (`@180dfc300`/`@180dfc3d0`) : `SurroundingEnemies(ref, center, radius, …)` → référence et centre
  SÉPARÉS (le call-site standard passe le caster) ;
- **4 args (`@180dfc570`/`@180dfc4a0`)** : `SurroundingEnemies(X, radius, …)` où le MÊME `X` sert de centre
  ET de référence (`Enemies(param_2 = X, units)`). C'est la forme de CultDemagogue :
  « unités entourant la CIBLE et **ennemies DE LA CIBLE** » = les **alliés du caster** (les Neophytes).

Le nœud porté a donc gagné un paramètre `reference` (défaut `None` → `ctx.caster`, comportement
historique inchangé pour HeroicFusillade/Stormcaller/…).

---

## 7. Le piège du NO-OP SILENCIEUX (et sa parade)

Le natif passe **le MÊME `entities`** (une REF d'état LIVE) à toutes les exécutions ; les sélecteurs d'un
étage aval VOIENT les unités posées par un étage amont. Le `DslContext` du port **fige** sa liste `units`
à la construction (`entities_from_state`). Deux parades, désormais **cumulées** :

1. **Re-matérialisation entre exécutions top-level** — pour les abilities à PLUSIEURS `Execute`
   (SupremeCommander : 2 ; **Waaagh : 5**). Sans elle, l'étage `PerformAIAction` ne verrait aucun summon.
2. **Poussée dans `entities.units`** par les feuilles de spawn (`behaviours/summon.py::Spawn`,
   `genestealer.py::SpawnDecoys`/`SpawnNeophytesOnDecoys`) — INDISPENSABLE pour les abilities à **UNE
   SEULE** exécution top-level, cas de **CultDemagogue** (un unique `Execute` sur un `op_Addition` à
   3 termes) : sans elle, le sélecteur du 3e étage rendrait un ensemble VIDE → no-op silencieux.
   Les enfants sont des `LiveUnit` (pos/hp/alive relus du state) — mirror de la réf d'état native.

**Prouvé par test** (`test_cultdemagogue_migration_live.py`) : `ai_units` non vide et ⊆ `neophytes`
(anti-no-op), cycle de flags sauvegardé/restauré, et **contre-cas** — avec une liste d'unités tronquée
des Neophytes, le sélecteur rend `[]` et `PerformAIAction` est un no-op.

---

## 8. Primitives DSL ajoutées

| nœud porté | natif | fichier |
|---|---|---|
| `ActiveTarget` (+ `DslContext.active_target`) | slot `factory+0x180` (`InitializeShared @180df2670`) | `entities/selectors.py`, `dsl/base.py` |
| `SurroundingTiles(center, radius, include_center)` | `@180dfca70` | `entities/selectors.py` |
| `UnitsWithVisualId(visualId, mode)` | `@180e00e90` (source = `factory+0x80`, **board-wide**) | `entities/selectors.py` |
| `UnitsWithId(source, id, mode)` | `@180e00170` (volet mono-id d'`UnitsWithIds`) | `entities/selectors.py` |
| `SurroundingEnemies(..., reference=)` | surcharge 4-args `@180dfc570` | `entities/selectors.py` |
| `FixedTileIds` | véhicule de collapse ID-domain (jumeau de `FixedTiles`, position-domain) | `entities/selectors.py` |
| `VisualUnitIdFromUnitId(unitId)` | `@180e01d70` | `entities/formulas.py` |
| `ChainBehaviour(next_selector, times, body, init)` | `@180deb910` | `entities/behaviours.py` |
| `Spawn(..., on_appearance=)` | `SpawnUnitOptions+0x18` (fire par `TriggerSpawnedUnitBehaviours`) | `runner/abilities/behaviours/summon.py` |
| `PerformAIAttack` — domaine UNITE en plus du domaine TUILE | `@180df8a10` (un seul port, pas de fork) | `runner/abilities/behaviours/summon.py` |

**`VisualUnitIdFromUnitId` — réduction offline documentée** : le champ `visualId` du dict d'unité porte
l'id de **CONFIG** pour les unités spawnées par le moteur (`orksOrkBoys`) et l'id **VISUEL** pour les
unités seedées depuis le live (`orksNpc2OrkBoy`) ; le nœud rend donc les **DEUX** formes — exactement ce
que fait naturellement la constante `affectedUnitIds` de SupremeCommander.

---

## 9. Résidus ouverts

- **Waaagh 1100 / 1101** : marqueurs posés (présents, durée 1 round) — les contributions `+extraDmg[level]`
  (canal `CreateEffectDamageBonusForAttack`) et `+extraHit` (canal coups additionnels #179) ne sont PAS
  branchées. Même classe de résidu que `BlackRage_ExtraDamage`.
- **`SortTilesByUtility`** (Waaagh move) collapsé en « tuile la plus proche du caster » — même proxy que
  tous les gap-closers déjà portés (HeroicFusillade / VigilanceEternal / SkyStrike).
- **`GetSpawnedUnitRange`** (1016) en constante `2` : le service de config d'unités (`ability+0x20`,
  vslot 0xaa) n'est pas exposé offline.
- **`AttackTilesForTarget`** (1016) = identité offline (aucun modèle de cover / ligne de vue) ; quand
  `|possible| < n`, l'union native produit des doublons de tuiles que le port élimine (HYPOTHÈSE : le
  natif re-teste la tuile dans `SpawnUnitBehaviour`).
- **Ordre/coût RNG** des `PickRandomly` / `RandomAmount` non calé bit-à-bit (gap pré-existant de
  `_pick_randomly_n`) → le count Poxwalkers est confronté en BANDE, pas en scalaire.
- **`Killer(...)`** (Waaagh `GetAttackBehaviour`) non porté : le `KillDeadUnits` du port n'exploite pas
  `subject_sel` (la mort est finalisée inline).
