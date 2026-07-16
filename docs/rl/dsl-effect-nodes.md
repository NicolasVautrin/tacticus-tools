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
| `Spawn @180dfbd50` | `Foreach(get_spawn_tile_selector(), SpawnUnit)` | slice-2b pas 2 (committé) |
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
