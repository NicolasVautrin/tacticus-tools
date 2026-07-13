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
