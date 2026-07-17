# Chantier archi : behaviours de combat en arbres DSL exécutables (effet-nœuds)

> Cap posé 2026-07-13 (feedback utilisateur : « pourquoi tu n'utilises pas plus le port DSL ? »).
> Racine doctrinale : `.claude/skills/tacticus-re-port/SKILL.md` §2.0 + mémoire
> `feedback_check_own_port_before_re` (« structure offline == structure native », appliqué aux behaviours).

## Problème (pourquoi ce chantier)

Le runner porte les behaviours d'ability **IMPÉRATIVEMENT** (`execute_*` dans `runner/operations/triggers.py`,
`runner/abilities/loki.py`, `runner/operations/spawn.py`) au lieu d'**arbres DSL**. C'est une **divergence
structurelle** : dans le jeu, `<Ability>.CreateBehaviour` **renvoie un arbre DSL d'effet-nœuds**
(`AttackWithAttackDamage & Maybe(SetOnFire) & Foreach(...)`), et l'exécution de l'ability = l'exécution de cet
arbre. Le porter en `execute_*` à la main, **c'est nous qui redécidons la logique** (ciblage, re-trigger,
exclusion de trait) au lieu qu'elle **émerge** des nœuds partagés portant la sémantique native exacte.

C'est la **cause commune** d'une classe de bugs « re-câblé / deviné à la main » :
- **Psyker chain** (#140/#147) : `after_hit_ability_attack` câblé à la main → j'ai deviné le re-trigger du
  splash (chain 51×) alors que le natif fait 1 seul splash. Le comportement aurait dû émerger d'un nœud
  `AttackWithAttackDamage` partagé.
- **UnitTrait dup** (#146) : `UnitsWithoutTrait(0x1b)` re-porté 2× ad-hoc au lieu du sélecteur partagé.
- **weapon-selection fork** (#49) : 1 service natif porté 2× (runner + prédiction) → divergence latente.

## État actuel

- `engine/dsl/` (`nodes.py`, `selectors.py`, `base.py`) = moteur de nœuds **LAZY**, utilisé côté
  **PRÉDICTION / DÉCISION** : `Node.evaluate(ctx)` → **une valeur / une cible** (pur, read-only, régime eager :
  on résout les feuilles puis on combine).
- Runner **combat** = **impératif** (`execute_*` appellent les Operations directement).
- Le runner a **DÉJÀ** l'infra d'exécution : ~80 **Operations** (mutateurs ECS atomiques), l'**Apply pipeline**
  (`IdunRunner.Apply @180e34bf0`, gate→pre→record→post), la **cascade** (LIFO inline + FIFO deferred). Cf.
  `runner-engine.md`.

Donc le blocage n'est **pas** « DSL pas adapté à Python » : c'est que les nœuds de prédiction sont **purs**
(→ valeur) alors que les nœuds de combat sont **à EFFET** (`AttackWithAttackDamage`, `AddEffect`, `CreateShield`,
`SpawnUnit`, `AddBondEffect`, `Inform`, `SetOnFire` **mutent** l'état + cascade). Les **effet-nœuds n'ont
jamais été construits** → le runner a grandi tranche-par-tranche en impératif.

## Direction (quoi)

Étendre le DSL avec des **EFFET-NŒUDS** : à côté de `evaluate(ctx) → valeur`, un `execute(ctx) → mutations +
events`. Les behaviours de combat = les **arbres EXACTS du décompilé**, composés par les combinateurs natifs
(`&` = `op_BitwiseAnd`, `Maybe(chance)`, `Foreach(selector)`). Chaque effet-nœud **ÉMET la/les Operation(s)**
correspondante(s) → l'Apply pipeline + cascade **existants** les appliquent. **Le DSL-effet est une couche
MINCE d'orchestration au-dessus des Operations déjà portées** (on ne réécrit pas les mutateurs, on remplace
l'orchestration impérative `execute_*` par l'arbre natif).

Bénéfices : primitives partagées **par construction** (un sélecteur/mutateur = 1 nœud, N usages) ; chaque
ability **vérifiable nœud-par-nœud** vs le décompilé (VA citées) ; la classe de bugs « re-porté / deviné à la
main » disparaît.

## RE à CLORE avant de bâtir (ne PAS inventer le modèle d'exécution)

1. **Le walker natif** : comment l'arbre de `CreateBehaviour` est EXÉCUTÉ quand l'ability fire ?
   (`ActiveAbilityOperation.ExecuteInternal @180e44ec0` → ? ; rôle de `EvaluateAbilities` ; le virtuel
   `Execute`/`Apply` des effet-nœuds / `TargetsSelector`).
2. **Sémantique des combinateurs** : `&` (séquence stricte ? court-circuit ?), `Maybe` (1 `next_bool`, place
   dans l'ordre RNG), `Foreach` (ordre d'itération des cibles).
3. **Mapping effet-nœud → Operation(s)** : `AttackWithAttackDamage` → `AttackDamageOperation` /
   `AbilityDamageOperation.ExecuteHit` (les DEUX appellent `EvaluateAfterHitTriggers @180e25fc0` — cf. #147 :
   résoudre pourquoi le splash Psyker ne re-trigger PAS malgré ça = la sémantique exacte de l'event after-hit,
   event 8/0x3d vs `On(0x26)`/`On(9)` — le port a peut-être conflé les event-ids). **⇒ le fix #140 ÉMERGE de
   ce port** : le re-trigger (ou non) est porté par la sémantique native du nœud, pas câblé à la main.

## Plan de migration (comment, sans big-bang)

1. **RE** walker + combinateurs + mapping nœud→Operation (ci-dessus).
2. **Base** : effet-nœuds `AttackWithAttackDamage` / `AddEffect` / `SpawnUnit` / `Maybe` / `Foreach` / `&`
   émettant les Operations **existantes** ; un `ExecutionContext` (state + rng + cascade) à côté du contexte
   de prédiction.
3. **1er behaviour leaf** (candidat le plus simple : `GetEmRuntz` = `Foreach(spawn tiles, SpawnUnit)` ; ou
   `FireOfAbsolution` = `AttackWithAttackDamage(splash) & Maybe(SetOnFire)`). **Garder impératif + DSL
   côte-à-côte**, valider **replay-diff bit-exact** (DSL == impératif == live), puis basculer.
4. Migrer les behaviours au fil des slices ; **retirer `execute_*`** quand le DSL est validé. #146
   (`UnitsWithoutTrait`) **tombe par construction** (le sélecteur partagé remplace les checks ad-hoc).

## Critère de succès

Chaque behaviour migré = l'**arbre EXACT du décompilé** (VA citées en commentaire), **replay-diff bit-exact**
vs l'impératif qu'il remplace ET vs live. **Zéro régression**. Migration incrémentale : le runner impératif
reste la référence jusqu'à ce que chaque behaviour DSL soit validé.

## Verdict RE #149 slice-2 (re-expert, PROUVÉ ghidra gqfc5mff6c) — WALKER + combinateurs + arbre GetEmRuntz

### 1. Contrat du walker (partagé, PROUVÉ)
Le behaviour n'est PAS exécuté par `ActiveAbilityOperation.ExecuteInternal @180e44ec0` (celle-ci = orchestrateur
d'ability : validité caster/cible, `GetAbilityEntities`, flags fin de tour). L'`Execute` de chaque `*Behaviour`
est un **virtuel** (`GetEmRuntzAbility.ExecuteBehaviour @1811e2210` n'a que des xrefs DATA = slots method-table).
Contrat lu sur `CombinedBehaviour.Execute @180ffe730`, `ForeachBehaviour.Execute @180fc6210`, etc. :
```
OperationResult Execute(this, AbilityEntities entities /*0x50 octets, by-value*/, IProcessor* proc)
```
- **`entities`** = le CONTEXTE lu par tous les nœuds (caster/owner/actor, target, casterPosition, abilityType,
  level, subject courant) = homologue exact de `DslContext`. Reconstruit par `Foreach` avec `subject`=cible
  courante (`DSLFactory.Entity(factory, target)`).
- **`proc` (`IProcessor*`, classe `DAT_1831d3468`)** = LE COLLECTEUR d'Operations, threadé identiquement à
  travers TOUTE la récursion. Chaque feuille émet son Operation via un slot vtable de `proc` (ex.
  `SpawnUnitBehaviour @180fd3d80` : slot +5). ⇒ **notre `ExecutionContext` = ce `proc`** (state + rng + bus).
- **Retour `OperationResult`** : byte @+0x20 = flag succès/**court-circuit** ; combiné en remontant
  (`OperationResult.Combine`). Les Operations enfilées sont appliquées via `IdunRunner.Apply @180e34bf0`
  (cascade LIFO inline / FIFO deferred, DÉJÀ portée).
- **LAZY vs EFFET = split STRUCTUREL** : `TargetsSelector`/valeurs (`AdjacentTiles`, `Enemies`,
  `LastUnitAttackedBy`, `TotalAttacksMade`) = nœuds `evaluate → valeur/liste` (DSL lazy actuel). Les
  `*Behaviour` (`Spawn`, `Foreach`, `Maybe`, `Combined`, `PerformAIAbility`, `AddBondEffect`) =
  `execute → OperationResult + Operations émises`. Un `Foreach`/`Maybe` **appelle** un selector lazy pour ses
  cibles puis exécute son child à effet.

### 2. Combinateurs (PROUVÉ)
| Combinateur | Factory → classe | Execute (VA) | Sémantique |
|---|---|---|---|
| `&` op_BitwiseAnd | `@180ffaae0` → `CombinedBehaviour` (left@0x50 right@0x58) | `@180ffe730` | séquence gauche→droite, **court-circuit** : exec left, `Combine` ; `if result.byte@+0x20 == 0` → exec right, sinon STOP. 2 effets purs → flag 0 → les deux s'exécutent. |
| `+` op_Addition | `@180ffaa70` → `CombinedBehaviour` (même layout) | (même classe) | identique structurellement à `&`. GetEmRuntz joint `(Spawn & PerformAIAttack)` et `Foreach(Taunt)` via `op_Addition @1811e2210`. |
| `Maybe(chance)` | `DSLFactory.Maybe @180df6470` → `MaybeBehaviour` (ctor `@180fca430`) | `@180fc9dc0` | **UN** `next_bool(chance)` AVANT le child ; child exécuté ssi vrai. Variante Foreach = 1 tirage PAR cible. |
| `Foreach(sel, body)` | `DSLFactory.Foreach @180defcd0` → `ForeachBehaviour` (ctor `@180fc69c0`) | `@180fc6210` | évalue selector@0x58 → IEnumerable, itère dans l'**ordre du sélecteur** (pas de tri) ; par cible reconstruit `entities` (subject=cible) puis bodyFunc → sous-behaviour Execute. |

### 3. Arbre GetEmRuntz (`ExecuteBehaviour @1811e2210`, id 1045 orksRuntherd — PROUVÉ, mirror 1:1)
```
op_Addition (@1811e2210 = CombinedBehaviour séquence)
├─ LEFT : Spawn & PerformAIAttack           (ExecuteAtomic @180fb0930 → AtomicGroup)
│  ├─ Spawn (@180dfbd50)
│  │    tileSelector = Cache(GetSpawnTileSelector)          # DSLFactory.Cache @180deb0d0
│  │    visualId     = AbilityConfiguration.GetStringConstant(cfg@+0x60, 0)
│  │    stats        = SpawnUnitOptions.WithStatsFromConfig(cfg@+0x60)
│  │  → SpawnUnitBehaviour.Execute @180fd3d80
│  └─ PerformAIAttackFromCurrentPosition (@180df8a10) → PerformAIAbilityUnitBehaviour   # on-appearance
└─ RIGHT : Foreach(Children, TauntWithNewChildrenWhoDidDamage)
   ├─ selector = Children(factory@+0x148)                   # DSLFactory.Children @180debed0 = summons de CE cast
   └─ body = TauntWithNewChildrenWhoDidDamage (@1811e27a0), Func<entities,behaviour> :
        If( AmountIsGreaterThanZero(TotalAttacksMade(child))
            & AmountIsEqual(child.abilityLevel, UnitTurnsStarted(child)) & IsAlive(child),
            AddBondEffect(0x1b=27, source=child, target=LastUnitAttackedBy(child), duration=TurnsFromRounds(1)) )

GetSpawnTileSelector (@1811e26b0, lazy) =
   op_BitwiseAnd( CanAddUnit(AdjacentTiles(caster@+0x168)),
                  Unique(AdjacentTiles( UnitsWithoutTrait(Enemies(caster,0x80,3), 0x1b) )) )
```
⚠ `UnitsWithoutTrait(Enemies, 0x1b)` : le port impératif (`spawn.py:487`) le lit comme exclusion du TRAIT
`Steppable`(=0x1b=27, tokens marchables) ; le re-expert a noté 0x1b comme l'effet Bond/Taunt (conflation
possible). **À trancher au build** (le nom `UnitsWithoutTrait` implique un TRAIT ; garder le mapping #146/#158).

### 4. Mapping nœud→Operation (feuilles, PROUVÉ)
| Feuille (VA) | Operation native | Port existant | État |
|---|---|---|---|
| Spawn/SpawnUnitBehaviour `@180fd3d80` | AddUnitOperation (slot +5) + TriggerSpawnedUnitBehaviours | `spawn.py SpawnUnitOperation.execute_getemruntz` / `_spawn_config_grot` | **spawn PORTÉ** |
| PerformAIAttackFromCurrentPosition `@180df8a10` | AttackDamageOperation (chemin dégât normal, event-map #150) | `damage.py AttackDamageOperation` | Operation existe ; **wiring on-appearance no-op** (`spawn.py:455`) |
| AddBondEffect(0x1b=27) `@1811e27a0` | AddEffectOperation (source=child, target=lastAttacked, 1t) | `effects.py AddEffectOperation.execute` | Operation existe ; **wiring Taunt-on-hit no-op** |

### 5. Priorités validator (flaggées re-expert)
1. Ordre RNG du `Maybe` (1 `next_bool` avant child) — valider bit-exact sur une ability à Maybe (FireOfAbsolution).
2. `Foreach(Children)` = summons de CE cast uniquement (`factory@+0x148`), PAS tous les summons du board.
3. Court-circuit `&` : pour 2 effets purs le flag@+0x20 reste 0 (sinon on perd le RIGHT du `op_Addition`).
4. Wiring on-appearance PerformAIAttack + Taunt-if-did-damage (gap no-op actuel) : replay-diff sans re-trigger fantôme (garde-fou #140).

## Verdict RE #199 — DÉCOMPILE `ExecuteBehaviour @1811e2210` (orchestrateur, gqfc5mff6c) : structure EXACTE

Le décompilé de `GetEmRuntzAbility.ExecuteBehaviour @1811e2210` **corrige la structure de la section 3**
(qui groupait `op_Addition((Spawn & PerformAIAttack), Foreach)`). La forme RÉELLE = **DEUX phases
d'exécution séquentielles** (PAS un seul arbre) :

```
ExecuteBehaviour(this, entities, out result) :
  1. ExecuteAtomic(this, Spawn(Cache(GetSpawnTileSelector), visualId=GetStringConstant(cfg,0),
                               stats=WithStatsFromConfig(cfg)), entities, 0x50)   # spawn TOUS les grots
  2. Execute(out result, this,
       op_Addition(
         PerformAIAttackFromCurrentPosition(Cache(GetSpawnTileSelector)),   # les grots (unités SUR les
                                                                            # tuiles de spawn) attaquent
         Foreach(Children = Children(factory+0x148), TauntWithNewChildrenWhoDidDamage) ),
       entities)
```

- **`ExecuteAtomic(Spawn)` d'abord**, puis **`Execute(PerformAIAttack + Foreach(Taunt))`** — l'ordre net =
  **tous les spawns → toutes les attaques → tous les Taunts** (le `Spawn` natif itère son tile-selecteur en
  interne ; PerformAIAttack itère les unités du **même** `Cache(GetSpawnTileSelector)` = les grots spawnés).
  ⚠ L'impératif `loki.GetEmRuntzAbility.execute_behaviour` **interleave** (attaque grot1 → Taunt grot1 →
  attaque grot2 …) ; le DSL suit le NATIF (batché). **Équivalent PROUVÉ bit-exact** (replay-diff offline :
  PV ennemis identiques) car le Taunt ne tire **aucun** RNG.
- **`TauntWithNewChildrenWhoDidDamage @1811e27a0`** (Func<entities,behaviour>, décompilé) pour l'enfant
  courant `child` (= subject du Foreach) :
  ```
  If( AmountIsGreaterThanZero(TotalAttacksMade(child))            # le grot a fait >=1 attaque
      & AmountIsEqual(factory+0xb8, UnitTurnsStarted(child))      # enfant NEUF de ce cast (turnsStarted
      &                                                           #   capturé de l'owner == celui du child)
      & IsAlive(LastUnitAttackedBy(child)),                       # l'ENNEMI FRAPPÉ est vivant
      AddBondEffect(0x1b=27 Taunted, stateRef=AbilityStateReference,
                    source=child, target=LastUnitAttackedBy(child), TurnsFromRounds(1)) )
  ```
  **Le gate `IsAlive` porte sur `LastUnitAttackedBy(child)` (l'ennemi), PAS sur `child`** — ce qui **VALIDE
  l'impératif** (`if target_alive: taunt`). La crainte initiale « native gate child-alive » était une
  mauvaise lecture de la section 3.
- **`Children @180debed0` = `AllAliveMachinesSelector`** (tous les summons vivants réf. `factory+0x148`) ; le
  narrowing « ce cast / neufs » est le prédicat `AmountIsEqual(turnsStarted)`. Port : accumulateur
  `DslContext.children` (mirror `factory+0x148`), alimenté par les feuilles `SpawnUnit`, scopé à CE cast.
- **`PerformAIAbilityUnitBehaviour.Execute @180fcb070`** = machinerie AI (itère les unités du selecteur,
  chacune décide une attaque via ses Func champs @+0x60/0x68/0x78/0x90). Port MINCE = plus-proche-ennemi +
  `AttackDamageOperation.execute` (approx AI **identique à l'impératif** live-validé ; cible AI-exacte =
  raffinement live à venir).

### Port livré (#199) — arbre DSL complet `getemruntz_tree()`
| Nœud natif (VA) | Port (`dsl_behaviours.py` / DSL lazy) | Statut |
|---|---|---|
| `Spawn @180dfbd50` | `Spawn(cache, "GetEmRuntz")` — nœud dédié, itère son tile-selector EN INTERNE (mirror natif, plus de `Foreach(tiles,SpawnUnit)`) | **mirror #199** |
| `Cache(GetSpawnTileSelector) @180deb0d0` | `Cache(...)` MÉMOÏSANT (slot unique), **PARTAGÉ** Spawn/PerformAIAttack | **mirror #199** (fix bug pass-through) |
| `ExecuteAtomic @180fb0930` (AtomicGroup) | `AtomicGroup(Spawn(cache))` — inline (RE #201) | **mirror #199** |
| `op_Addition @180ffaa70` | `op_add(PerformAIAttack(cache), Foreach(Children, Taunt))` | **mirror #199** |
| `PerformAIAttackFromCurrentPosition @180df8a10` | `PerformAIAttack` (EffectNode, per-child nearest + AttackDamageOperation) | **#199** |
| `Children @180debed0` (`AllAliveMachinesSelector`) | `Children` (lit `DslContext.children`, accumulateur factory+0x148) | **#199** |
| `TotalAttacksMade @180dfe090` / `LastUnitAttackedBy @180df5ee0` / `UnitTurnsStarted @180dff280` | accesseurs runtime (lisent le dict enfant annoté par `PerformAIAttack`) | **#199** |
| `op_BitwiseAnd` (AbilityTrigger, ×2) | `predicates.TriggerAnd` | **#199** |
| `AddBondEffect(0x1b) @1811e27a0` | `AddBondEffect` (EffectNode → `AddEffectOperation` Taunted 27) | **#199** |

Validé : replay-diff OFFLINE `getemruntz_tree()` == impératif `GetEmRuntzAbility.execute_behaviour` (State
synthétique board evenq, orksRuntherd + 2 ennemis HIGH-HP) → grots [23,25], PV ennemis identiques
post-attaque, **les 2 ennemis Taunted**. **RESTE (slice-2b final)** : bascule `AbilityHandler` (DSL en place
de l'impératif) + retrait de `execute_getemruntz`/`GetEmRuntzAbility.execute_behaviour` + **replay-diff
LIVE** (confront in-game).

## Confront LIVE #199 (2026-07-16) — l'exécution de l'arbre N'EST PAS synchrone dans `ExecuteBehaviour` (finding OUVERT → tâche #200)

**But** : valider le tracer natif `dsl-trace.ts` (RPC `dslTraceArm`/`dslTraceLastCast`/`dslTraceDisarm`,
gate sur `<ability>.ExecuteBehaviour`) en confrontant l'arbre d'exécution NATIF d'un cast GetEmRuntz réel
au walk OFFLINE (`trace_offline_getemruntz.py`, 52 nœuds E=11/T=10/S=25/V=6).

**Méthode (reproductible)** :
1. warmup, `rl_duel build --seed 20260716 --rank 17 --p-units orksRuntherd,orksNob --a-units astraCreed,astraBullgryn --board C1_01`.
2. `act move --unit 53 --to 1,3` (rapprocher le caster : GetEmRuntz `now:∅` → `now[1]:u53` après déplacement).
3. `dslTraceArm("IdunBattleLogic.Entities.Abilities.Active.Loki","GetEmRuntzAbility",1)` → `hooks:434` (4 familles), gate = `GetEmRuntzAbility.ExecuteBehaviour`.
4. `act ability --caster 53 --ability 1045 --target 53` → cast RÉUSSI (2 grots e71/e74 spawnés, `Loki_NormalAttack`, `SwornProtector` adverse e79, **167 events** de cascade).
5. `dslTraceLastCast` → `capturedTrees:1`.

**Résultat** : l'arbre natif capturé = **1 SEUL nœud** — `IdunBattle.Entities.Selectors.EntitiesSelector`
(kind S, depth 0). **Aucun** E/T/V, aucun autre S. Vs 52 nœuds offline.

**Ce n'est PAS un artefact du tracer** : les 6 nœuds de l'arbre GetEmRuntz (`CombinedBehaviour`,
`ForeachBehaviour`, `MaybeBehaviour`, `PerformAIAbilityUnitBehaviour`, `SpawnUnitBehaviour`,
`AtomicGroupBehaviour`) dérivent TOUS de `IdunBattle.DSL.AbilityBehaviour` (vérifié `il2cpp_classes.tsv`
lignes 11874/11911/11924/11930/11963/12505) = la base E que le tracer énumère → ils SONT dans les 434 hooks.
Leur absence de la capture ⇒ **leur `.Execute` s'exécute HORS de la fenêtre synchrone `enter→leave` de
`ExecuteBehaviour`**. Seule la résolution de cibles (`EntitiesSelector.Select`) tourne en-frame.

**Contradiction avec le « Verdict RE #199 » ci-dessus** (qui décrivait `ExecuteBehaviour` = 2 phases
synchrones `ExecuteAtomic(Spawn)` puis `Execute(op_Addition(...))`). Le live prouve que ces `.Execute`
ne tournent PAS dans le frame d'`ExecuteBehaviour`. Deux sous-hypothèses à trancher (RE, tâche #200) :
- **(b1)** `ExecuteBehaviour` **construit + enfile** l'arbre (appels DSLFactory = ctors de nœuds, PAS les
  virtuels `.Execute`) comme root-Operation ; le **walk réel est différé** dans le pipeline `IdunRunner.Apply`
  (cascade FIFO — les 167 events) → pour tracer l'exécution, il faut gater le **point d'entrée différé**, pas
  `ExecuteBehaviour`.
- **(b2)** le `ExecuteBehaviour` gaté est l'entrée **résolution-de-cibles / preview** (d'où l'unique
  `EntitiesSelector.Select`) et l'exécution passe par une **AUTRE** méthode (`ActiveAbilityOperation.ExecuteInternal
  @180e44ec0` → les `*Behaviour.Execute`) → **on a gaté la mauvaise méthode**.

**Impact** : le walk offline 1-passe synchrone ne reflète pas (encore prouvé) la structure native
d'EXÉCUTION. **Ne PAS retirer l'impératif `execute_getemruntz`** ni basculer GetEmRuntz sur le DSL tant que
#200 n'a pas tranché (b1/b2) et re-confronté avec un gate correct. Le port offline reste valide comme
**modèle de décision** (bit-exact en replay-diff offline) ; c'est la **fidélité du modèle d'EXÉCUTION** vs le
runtime natif qui est rouverte. Artefacts : `scratchpad/native_tree.json` (capture), `scratchpad/trace_offline_getemruntz.py` (walk offline).

### RÉSOLUTION (RE #200, 2026-07-16) — c'est une LIMITE DU TRACER, pas du modèle. Fix = hooker `DSLFactory`

Décompilé ghidra de la chaîne d'exécution (gqfc5mff6c) :
- **`GetEmRuntzAbility.ExecuteBehaviour @1811e2210`** = **CONSTRUIT** l'arbre par une séquence d'appels
  `DSLFactory.X(...)` **directs et synchrones** (`Cache`, `Spawn`, `PerformAIAttackFromCurrentPosition`,
  `Children`, `Foreach`, `AtomicGroup`, `op_Addition` + `GetSpawnTileSelector`→`CanAddUnit`/`AdjacentTiles`/
  `Enemies`/`UnitsWithoutTrait`/`Unique`), puis appelle `AActiveAbility.ExecuteAtomic(Spawn)` +
  `AActiveAbility.Execute(op_Addition)`.
- **`AActiveAbility.Execute @180fb0c40`** → `FUN_1800291d0` = **dispatch d'interface il2cpp SYNCHRONE** (lit
  `klass+0xb0` interfaceOffsets, résout le slot, `(*pcVar1)(out,this,entities)` appelle `behaviour.Execute`
  immédiatement, renvoie `OperationResult`). ⇒ l'op_Addition n'est **pas** différé (réfute b1 pour cette
  branche).
- **`AActiveAbility.ExecuteAtomic @180fb0930`** → `DSLFactory.AtomicGroup(factory,0x50,callback,proc)` =
  construit un AtomicGroup + callback, retourne void ⇒ le **Spawn est planifié/différé** (b1 pour cette branche).
- **`SpawnUnitBehaviour.Execute @180fd3d80`** = vrai corps concret (pas un thunk).

**Cause de la cécité du tracer** : les `*Behaviour.Execute` sont invoqués soit par **dispatch d'interface /
gshared** (`FUN_1800291d0` = slot de vtable d'interface), soit **différés** (AtomicGroup). Or le tracer hooke
`findMethod(k,"Execute")` = **le pointeur concret par-classe**, qui **n'est pas** celui exécuté au runtime
(slot d'interface / corps gshared) — donc les hooks d'exécution ne fire jamais (sauf l'`EntitiesSelector`
appelé par un chemin concret direct). **Ni b1 ni b2 « le modèle offline est faux » : le modèle est bon (le
replay-diff offline validait déjà le comportement), c'est l'INSTRUMENTATION qui est aveugle.**

**Fix = tracer-v2 sur la CONSTRUCTION** (intuition user, validée) : la construction de l'arbre est une
séquence `DSLFactory.X(...)` **directe, synchrone, en-fenêtre** → hooker les `DSLFactory.*` (+ `op_Addition`/
`op_BitwiseAnd`, `ExecuteAtomic`), enregistrer le **ret-ptr + arg-ptrs** de chaque appel, et **reconstruire
l'arbre par matching de pointeurs** (un arg == un ret précédent ⇒ lien parent→enfant). Robuste au dispatch
interface/gshared/deferral. Donne un confront **structurel** exact (le port bâtit-il le même arbre que le
natif ?) — au prix de perdre l'ordre d'EXÉCUTION (acceptable : l'exec-order offline est déjà validé en
replay-diff). ⇒ #200 = écrire ce tracer-v2, rebuild+reinject, re-confronter `getemruntz_tree()`.

### MIRROR STRUCTUREL DU PORT — FAIT (#199, 2026-07-17)

`getemruntz_tree()` réécrit en **mirror 1:1** de l'arbre de construction natif (dérivé du décompilé
`ExecuteBehaviour`, PAS d'une capture frida) : `Seq(AtomicGroup(Spawn(cache)), op_add(PerformAIAttack(cache),
Foreach(Children, Taunt)))`, `cache = Cache(GetSpawnTileSelector)` **partagé** Spawn/Attack. Nouveaux nœuds :
`Spawn` (itère son tile-selector en interne, `dsl_behaviours.py`), `AtomicGroup` (inline, `entities/behaviours.py`),
et `Cache` **corrigé pour MÉMOÏSER** (`entities/selectors.py` — était un pass-through recompute = bug latent
masqué : sans mémoïsation, `PerformAIAttack(cache)` relirait `CanAddUnit` post-spawn et exclurait les tuiles
occupées par les grots → 0 attaque). `PerformAIAttack` rendu **selector-driven** (parcourt les tuiles du Cache
en ordre, mappe chaque tuile→grot). **Validé replay behavioral bit-identique** (état synthétique orksRuntherd +
2 ennemis) : grots sur tuiles `[23,25]`, les 2 grots attaquent (2207/2628 dmg), les 2 ennemis Taunted — MÊME
résultat qu'avant le refactor. **RESTE = la capture FRIDA du natif (#200 tracer-v2 DSLFactory)** pour confronter
LIVE l'arbre natif à ce mirror (le confront actuel est ANALYTIQUE : décompilé natif == arbre porté).

### TRACER-V2 GÉNÉRIQUE + CONFRONT LIVE — FAIT (#200, 2026-07-17)

Tracer-v2 écrit et validé LIVE : `frida/hooks/features/dsl-ctor-trace.ts` (RPC `dslCtorArm`/`dslCtorCasts`/
`dslCtorDisarm`). **GÉNÉRIQUE** (pas focus GetEmRuntz) : hooke TOUTE la classe `DSLFactory` (768 méthodes,
overloads inclus) + les opérateurs des 4 bases DSL + les drivers `AActiveAbility.Execute`/`ExecuteAtomic`,
gaté sur la fenêtre de N'IMPORTE QUEL `<Ability>.ExecuteBehaviour` (230 gates enum, namespace Abilities.*),
chaque cast tagué par la classe réelle lue sur `this`. Reconstruction offline (`scratchpad/reconstruct_dsltree.py`)
par **règle d'arête uniforme** : un arg = enfant SSI il égale le `ret` d'un appel antérieur (gère instance-factory
arg0=factory exclu ET opérateurs statiques 2-nœuds sans cas particulier ; on part des drivers → remonte les
arêtes = arbre STRUCTUREL pur, le bruit d'exec = query-calls non consommés est filtré).

**Confront LIVE réel** (cast GetEmRuntz piloté sur runner isolé, Snotflogga=orksRuntherd vs 2 astra, ennemi
amené adjacent via IA) : 3 casts capturés — `GetEmRuntzAbility` (898 appels) + 2× `Loki_NormalAttackAbility`
(94 chacun, = les grots qui attaquent → **prouve la généricité**, capture d'une AUTRE ability sans config).
Arbre natif GetEmRuntz reconstruit = **exactement** le mirror porté :
- stmt1 `ExecuteAtomic`: `Spawn → Cache → op_BitwiseAnd(CanAddUnit(AdjacentTiles), Unique(AdjacentTiles(UnitsWithoutTrait(Enemies))))`
- stmt2 `Execute`: `op_Addition(PerformAIAttackFromCurrentPosition → Cache[MÊME ret 0x…3240], Foreach(Children))`
- ✅ **Cache = DAG mémoïsé partagé CONFIRMÉ LIVE** : le même `ret` sous Spawn ET PerformAIAttack.
- ✅ **Seq(AtomicGroup, op_add) confirmé** : deux statements (ExecuteAtomic puis Execute).

**DISCREPANCE trouvée → FIXÉE #202** : la branche droite native = `UnitsWithoutTrait(Enemies(AllUnits), Steppable)`
**SANS nœud `Damageable`** ; le port (`selectors.py:515`) insérait un `Damageable(Enemies(...))` spurieux. RE de la
chaîne : `DSLFactory.AllUnits @180de85f0` → **`AllAliveMachinesSelector @180ee0080`** = le primitif DSL `AllUnits`
est la variante **ALIVE** (un `AllUnitsSelector` distinct existe pour le set brut, non utilisé). Le port avait
`AllUnits.select = list(ctx.units)` (tous, morts inclus) → le `Damageable` **compensait** ce non-mirror. FIX
(zéro blast radius, `AllUnits()` construit UNIQUEMENT dans `get_spawn_tile_selector`) : `AllUnits` filtre désormais
alive+hp>0 (mirror `AllAliveMachines`), `Damageable` retiré → structure = native. Validé : replay bit-identique
(grots `[23,25]`) + test discriminant dead-exclusion (mort id exclu de `AllUnits`).

**NUANCE (pas un bug)** : le `Foreach` natif prend un `Func<b__0>` **lazy-per-child** (construit le sous-arbre
taunt à chaque grot) → invisible comme enfant de `Foreach` dans la capture (apparaît en bruit d'exec) ; le port
le construit eager (`getemruntz_taunt_tree()`) = équivalent comportemental, modeling différent.

### #199 CLOS — impératif retiré (2026-07-17)

Le confront live (#200) étant fait, l'impératif `SpawnUnitOperation.execute_getemruntz` (65 lignes, superseded)
a été **RETIRÉ** (+ import mort `UnitTrait, has_trait` de `spawn.py`). `GetEmRuntzAbility.execute_behaviour`
n'exécute plus QUE l'arbre DSL `getemruntz_tree()`. Validé : import OK + replay bit-identique (`[23,25]`,
2207/2628, taunted `[2,3]`). GetEmRuntz = 1er behaviour combat 100% DSL, live-confirmé fidèle.
