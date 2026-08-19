# Chantier archi : behaviours de combat en arbres DSL exécutables (effet-nœuds)

> Cap posé 2026-07-13 (feedback utilisateur : « pourquoi tu n'utilises pas plus le port DSL ? »).
> Racine doctrinale : `.claude/skills/tacticus-re-port/SKILL.md` §2.0 + mémoire
> `feedback_check_own_port_before_re` (« structure offline == structure native », appliqué aux behaviours).
>
> **Ce fichier CLASSE le vocabulaire (DSL vs impératif). Il ne dit pas QUI l'emploie.**
> Le graphe d'usage — quelles abilities composent une primitive, et réciproquement — vit dans
> `dsl-cartography-phase1.md` (méthode + contrat) et `dsl-usage-map.md` (données générées).
> C'est là que se lit le **classement des primitives par levier**, qui chiffre l'intuition
> « porter les PRIMITIVES, pas les abilities ».

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

## Classification : ce qui DOIT être DSL vs ce qui RESTE impératif (roadmap durable)

> Posée 2026-07-17 (checkpoint user : « est-ce qu'on est capable de classifier ce qui peut être impératif et
> ce qui ne peut pas l'être ? »). **Réponse : oui — le natif dessine lui-même la frontière.** Section de
> RÉFÉRENCE (pas un log de slice) : à consulter AVANT de migrer tout behaviour/trigger, pour ne pas forcer un
> arbre là où le natif est impératif, ni laisser impératif ce que le natif exprime en arbre.

### Le critère : « quel est l'ARTEFACT NATIF ? »

Le combat natif a deux mondes nettement séparés :

| Monde | Artefact natif | Nature | Port |
|---|---|---|---|
| **Déclaratif** | `CreateBehaviour`/`ExecuteBehaviour` (effets, kind **E**), `CreateTrigger` (prédicats, **T**), sélecteurs (**S**), formules (**V**) | un **arbre de nœuds `DSLFactory`** | **DOIT être un arbre DSL** |
| **Impératif** | les ~80 `Operation.Execute` (mutateurs ECS), les `Effect.ApplyModification`/`ReverseModification`, le pathfinding, le scheduler de tour, le PRNG, l'Apply pipeline | du **code C# impératif** mutant l'ECS | **RESTE impératif** (mirror fidèle) |

**La frontière = le `.Execute` d'une feuille DSL.** Tout ce qu'un `CreateBehaviour` **compose** (structure de
l'arbre + sélecteurs/formules/prédicats qu'il référence) est déclaratif → DSL. Tout ce qu'une feuille
**appelle** (l'Operation) est impératif → reste une Operation. Une feuille (`AttackWithAbilityDamage`,
`AddEffect`, `SetOnFire`, `MoveUnit`…) est un nœud MINCE **des deux côtés à la fois** : on mirror le nœud,
l'Operation en-dessous reste impérative.

Donc « peut-il rester impératif ? » se répond mécaniquement :
- natif = `CreateBehaviour`/`CreateTrigger` (renvoie un arbre) → **non, c'est du DSL** ;
- natif = `Operation.Execute` / `ApplyModification` / routine moteur → **oui, ça reste impératif**.

### Le piège : un helper qui FUSIONNE ce que le natif SÉPARE

`_apply_act_of_faith_stack` fait *à la fois* le behaviour (`AddEffect(0x3f9)`) *et* le `ApplyModification` de
l'effet (stat-mod crit `@180f302f0`). Le split fidèle : behaviour = feuille `AddEffect` DSL ; stat-mod =
`ApplyModification` de l'effet (impératif, dans `entities/effects/`). Migrer sans faire ce split = wrapper un
mélange non-natif. **Règle : avant de wrapper un helper en DSL, vérifier qu'il ne contient pas déjà
l'Operation/`ApplyModification` qui devrait vivre EN DESSOUS de la feuille.**

### Classification concrète — behaviours de trigger/passif `runner/operations/triggers/loki.py`

**Kind E (`CreateBehaviour`) → DOIVENT devenir DSL :**

| Behaviour | Natif | Arbre (mirror cible) | Bloqué sur | Groupe |
|---|---|---|---|---|
| ~~FireOfAbsolution~~ | `@18121f380` | `Inform & splash & Maybe(ignite)` | — (slice-14 ✅) | ✅ |
| ~~OnFireDamage~~ | `@1811c3a60` | `AddEffect(Fire, Tiles(target))` | — (slice-15 ✅ : feuille `AddEffect` **généralisée tile-domain** (itère le sélecteur, `(col,row)`→tile id) + fix `Tiles`=`_units_of`) | ✅ |
| ~~TheBetrayer_AddEffect~~ | `@1811a4a00` | `AddEffect(0x4f3, Self@0x148)` | — (slice-17 ✅ : `AddEffect(Caster())` ; durée **1 tour** RE-confirmée @180e48940 (`Duration@+0x68 = local_588[0] = 1` si override ET `DefaultAmountOfRounds(0x4f3)` null), re-accordée à chaque kill — l'ancien `BaseEffect` PERMANENT était un **bug latent** que le mirror corrige) | ✅ |
| ~~ActOfFaith reset~~ | `@181219eb0` | `RemoveEffect(0x3f9, Self@0x148)` | — (slice-16 ✅ : feuille `RemoveEffect` NEUVE (runner) + `reverted_stats()` DATA de l'effet ; gshared `param_3==0x20`=`RemoveEffect(0x3f9)` retenu, `!=0x20`=`TriggerAbilityDelayed(0x3fa)` écarté) | ✅ |
| ~~ActOfFaith accumulate~~ | `@181219a70` | `op_add(AddEffect(0x3f9, Self@0x148), If(<killer Imperial allié + normal-attack RighteousRepugnance_NormalAttack=1182 + kill mêlée>, Maybe(chance, AddEffect(0x3f9))))` | — (slice-20 ✅ : **split** feuille/effet respecté — feuille `AddEffect(Caster())` déclenche `ActOfFaithBuffEffect.ApplyModification @180f302f0` (DATA `applied_stat_mods` côté effet = 2 ChangeStat crit ; symétrique de `reverted_stats()`), exécutée par `AddEffectOperation._apply_stat_mods` (impératif, `apply_change_stat` par-source) ; stacking via flag effet `stacks_stat_mod_on_add` (skip du gate « déjà-présent », 0 régression Fire/Pinned/Stunned). **2e stack conditionnel PORTÉ + live-validé** (Morvenn Vahl) : nœuds NEUFS `UnitNormalAttackType @180dff150` (type concret via kit gameconfig), `ConfigVarForEntity` (mirror `ConfigVar(RighteousRepugnance=1107, killer, chance=0x3a=58) @180decac0` = `ability_var("RighteousRepugnance","chance", passive_ability_level killer)`, 40-60%), `HasGrandAlliance` (mirror `HasTrait(26=Imperial)` via faction), `AreFriends`, sélecteur `Actor()`, `DslContext.get_ability_level`. **RE Q3 (IsUpdatable @18155afe0)** : ActOfFaith 1017 updatable par fallback (`!=0x472`) MAIS stacke (source-matching `UpdateExistingEffect`, non porté) → observable additif reproduit via N instances (flaggé). **RE Q4** : `ApplyModification` PAS dans `AddNewEffect` (pure ECS) mais pipeline `ApplyInternal→vtable 0x728`) | ✅ |
| ~~EnvFireTile DoT~~ | `@18121e040` | `Foreach(UnitsWithoutTraits([Steppable,Immune]) & Units(EntitiesWithAnyEffect(Fire)), AttackWithAbilityDamage(Tiles, PercentageOf(StatAmount(Health,Max),fireDmgPct), Direct(3), source=Fire))` | — (slice-19 ✅ : feuille DIRECT `AttackWithAbilityDamage` NEUVE (factory `@180de9c90` ≠ `AttackWithAttackDamage @180de9fb0`) → `AttackDamageOperation.execute_direct` (perçage/armure seuls, PAS de crit/block/spread/after-hit) + `PercentageOf(fireDmgPct, StatAmount(Target(),Health,**Max**))`. **RENOMMAGE natif** (« coller au natif ») : l'ancienne classe Python `AttackWithAbilityDamage` (crit/block) → `AttackWithAttackDamage` (65 occ / 4 fichiers), la NEUVE = la vraie DIRECT. `Foreach`/sélecteur restent impératifs (dispatch tuile + `_is_immune_to_fire`, DSL-ification = #216). Bit-exact vs impératif validé (replay-diff, toutes unités)) | ✅ |
| ~~Psyker Smite~~ | `@1812241b0` | `AttackWithAttackDamage(Target(), PercentageOf(StatAmount(Self@0x148,Attack), Direct(psykerExtraDmg)), Psychic, hits=1)` | — (slice-18 ✅ : PRIMITIF damage-node introduit — feuille `AttackWithAbilityDamage` param `amount`/`hits` (mode formule → `execute_normal_like(base, spread=0)`) + wiring `entities_from_state.get_stat` (StatAmount lit la vraie stat via StatsComponent) + helper partagé `profile_pierce`. Sélecteur `PickRandomly(Damageable(Enemies(AdjacentUnits)))` reste impératif → collapse `Target()`, DSL-ification = #216) | ✅ |
| TheBetrayer_TakeTurn | `@1811a4f70` | `If(Amount>0(target), Inform & If(NOT IsAdjacent, MoveUnit(chosenTile)) & If(IsAdjacent, GetDamageBehaviour(target)))` — `target=Cache(GetAttackTarget)`, `chosenTile=First(SortByFormula(SortTilesByUtility(AdjacentTiles(target)&movable .Otherwise movable), MinPathLength, asc))`. **GetDamageBehaviour** `@18119c1e0` = `AttackWithAttackDamage(Self, target, MinMaxDamage, profile 0x19, GetHits)` = feuille DÉJÀ portée (PAS `UseActiveAbility`). `MoveUnit` ✅ (slice-21b, généralise dest_tile_sel). RESTE : sélecteurs AI/pathfinding LOURDS (S) `GetAttackTarget @1811a53a0`, `MovableTilesInRange`, `SortTilesByUtility`, `MinPathLength`, `Otherwise`, `IsAdjacent`, `Inform`, `Direct`, `GetVariableForLevel(0x53)` | **3** |
| ~~FinalJustice~~ | `@18121ed00` | `Inform & If(Count(validTargets)>0 & NOT TargetIsOverkilled, UseActiveAbility(Self, SortUnitsByDamageUtility(ValidNormalAttackTargets), UnitNormalAttackType))` | — (**slice-22 ✅** : feuille NEUVE `UseActiveAbility` (`@180e015e0` → `UseActiveAbilityBehaviour.Execute @180fd9930` : itère targets → dispatch récursif de l'ability sur chaque cible ; specialisée au dispatch attaque-normale = `AttackDamageOperation.execute`, == le corps impératif validé → bit-exact). AI-target `SortUnitsByDamageUtility` (S lourd) **collapsé** en `Target()` (reste impératif `_finaljustice_target`, doctrine slice-18/19). Gate `Count>0 & NOT overkill` + `Inform` déjà dans `matches()`. `_finaljustice_attack` migré en arbre) | ✅ |
| ~~ArcaneShield~~ | `@180e16b40` | `CreateShield(Cache(First(SortByFormula(Randomize(UnitsWithoutTrait(SurroundingFriends(self,range),0x1b)) .Otherwise self, Sum(dist,faction,chaos,not-self)))), ConfigVar(0x27=shieldHp), self.Id, TurnsFromRounds(1))` | — (**slice-23 ✅** : feuille NEUVE `CreateShield` (`@180ded000` → `CreateShieldBehaviour.Execute @180fc2650` : par cible → `ShieldComponent.add_or_update_shield`, == corps impératif → bit-exact). AI-target LOURD (S : SurroundingFriends→UnitsWithoutTrait→Randomize→SortByFormula→First) **collapsé** en `Target()` (`_arcaneshield_target`) ; montant `ConfigVar(0x27=shieldHp)` (formule V) calculé impérativement (`ability_var`) → scalaire. `_arcaneshield_grant` migré ; test NEUF `test_arcaneshield_live` (allié in-range + fallback soi)) | ✅ |

> ⚠ Les VA proviennent des docstrings du port (RE antérieure citée). FireOfAbsolution (slice-14),
> OnFireDamage + TheBetrayer_AddEffect + ActOfFaith accumulate/reset (slice-15 RE) sont décompilés frais. Les
> arbres du **Groupe 3** sont ESQUISSÉS d'après ces docstrings → leur structure EXACTE est à **re-confirmer au
> décompile au moment de migrer** (ne pas les figer). La CLASSIFICATION (ce sont des `CreateBehaviour` trees
> gated sur des feuilles lourdes) est, elle, solide.

> **Map des slots factory `AbilityEntities` (RE slice-15, PROUVÉ décompile)** : `+0x148` = **Self/Owner**
> (prouvé par ActOfFaith accumulate `AreFriends(killer@0x158, +0x148)` == `_friendly_imperial(killer)`) ;
> `+0x158` = **killer/actor** ; `+0x160` = **caster** ; `+0x178` = **target**. Un `AddEffect(effet, +0x148)`
> = effet sur soi → feuille `AddEffect(…, Caster())` (Owner==Caster pour un triggered). `+0x148` sert AUSSI
> d'accumulateur d'enfants spawnés (`Children`/`Spawn`) selon le behaviour — même slot, rôle contextuel.
>
> **`DefaultAmountOfRounds` @181559ff0 (switch 1:1)** : `0x4f`→3 ; `0x429`/`0x48a`→1 ; `5`/`0x11`/`0x12`/
> `0x3a`/`0x4dc`/`0x5c4`→2 ; **tout le reste → null** (durée alors = override, sinon fallback **1** dans
> `AddEffectOperation`). ⇒ `0x4f3` (TheBetrayer) et `0x3f9` (ActOfFaith) = **null → fallback 1** via
> l'Operation. Table portée `_DEFAULT_ROUNDS` (operations/effects.py) confirmée exacte.
>
> **Fallback durée confirmé @180e48940 (slice-17)** : dans `AddEffectOperation.Execute`, `EffectComponent.
> Duration @+0x68 = local_588[0]`, et `local_588[0] = 1` quand l'override Nullable (param_6) n'a pas de valeur.
> ⇒ un `AddEffect(effet, …, override=null)` sur un effet à `DefaultAmountOfRounds` null pose une durée = **1
> tour** (PAS permanent, PAS 0). C'est ce que le port `AddEffectOperation` fait déjà — un behaviour migré vers
> la feuille `AddEffect` hérite donc de cette durée native (ex. TheBetrayer rage 1 tour, re-accordée par kill).

**RESTENT impératifs (natif ≠ arbre de behaviour) — NE PAS forcer en DSL :**
- **Operations** appelées par les feuilles : `AttackDamageOperation`, `AddEffectOperation`,
  `apply_change_stat`/`revert_change_stat`, `MoveUnitOperation`, `HealUnitOperation`, `_fire_death_if_killed`…
  → mutateurs ECS, mirror impératif fidèle. Une feuille DSL les APPELLE.
- **Méthodes d'effet** : `ActOfFaithBuffEffect.ApplyModification/ReverseModification` (stat-mod crit) —
  impératif natif, vit dans `entities/effects/`. Déclenché par la feuille `AddEffect`/`RemoveEffect`.
- **Routines moteur** : pathfinding, scheduler de tour, PRNG, pipeline Apply (gate/pre/record/post), pump FIFO.

**Axes SÉPARÉS (DSL-ifiables mais HORS des slices E de #149)** :
- **(T) `matches()` = `CreateTrigger`** : le natif EST un arbre prédicat (`OwnerIsActor & IsRangedAttack &
  DamageProfileIs & NOT(...)`). DSL-ifiable en famille **T**, mais c'est un CHANTIER distinct (#149 cible E).
- **(S) sélecteurs AI-target** (`_betrayer_target`/`_finaljustice_target`/`_arcaneshield_target`/
  `_adjacent_damageable_enemies`) = kind **S** natif → devraient être des sélecteurs DSL (#216 en couvre 2 ;
  les AI-target sont des sélecteurs lourds).

### Ordre de bataille (tranches E restantes, par tractabilité)

- **Groupe 1 — ✅ TERMINÉ** : ~~OnFireDamage~~ (slice-15 : `AddEffect` généralisée tile-domain
  `Tiles(Target())`) · ~~ActOfFaith reset~~ (slice-16 : feuille `RemoveEffect` neuve + `reverted_stats()` DATA
  côté effet, frontière déclaratif/impératif respectée) · ~~TheBetrayer_AddEffect~~ (slice-17 :
  `AddEffect(Caster())`, durée rage 1 tour RE-confirmée @180e48940 — l'ancien permanent était un bug latent).
  Les 3 feuilles concernées (`AddEffect` tile+unit, `RemoveEffect`) sont désormais des primitives réutilisables.
- **Groupe 2 — ✅ TERMINÉ** : ~~Psyker Smite~~ (slice-18 ✅ : PRIMITIF damage-node livré — cf. ci-dessous) ·
  ~~EnvFireTile DoT~~ (slice-19 ✅ : feuille DIRECT `AttackWithAbilityDamage` NEUVE + `execute_direct` + renommage
  natif — cf. ci-dessous) · ~~ActOfFaith accumulate~~ (slice-20 ✅ : feuille `AddEffect` déclenche
  `ApplyModification` de l'effet (split feuille/effet respecté) + flag `stacks_stat_mod_on_add` ; **2e stack
  conditionnel RighteousRepugnance PORTÉ + live-validé** — nœuds neufs `UnitNormalAttackType`/`ConfigVarForEntity`/
  `HasGrandAlliance`/`AreFriends`/`Actor()`/`get_ability_level` ; cf. la ligne de classification ci-dessus).

  > **PRIMITIF damage-node (slice-18, RE `@1812241b0` décompile frais)** — 3 pièces réutilisables par
  > EnvFireTile/ActOfFaith :
  > 1. **`entities_from_state` wire `get_stat`** : `StatAmount(sel, statType, variant)` lit la VRAIE stat de
  >    l'unité (id → entité → `StatsComponent.ctx.stats.get_stat(statType, part)`) — sans quoi il dégradait
  >    vers Health (hp). `variant` natif = `StatPart` (0=Current, 2=Maximum, 3=Initial). C'était LA pièce
  >    structurelle manquante (le ctx sélecteur = ctx formule, comme l'`AbilityEntities` natif unique).
  > 2. **feuille `AttackWithAbilityDamage` param `amount`/`hits`** : quand le natif passe un dégât-node
  >    `Direct(amountFormula)` (au lieu de bornes `MinMaxDamage`), la feuille calcule `base = amount.evaluate`
  >    (Fix64) et route via `execute_normal_like(base, pierce, hits, spread_pct=0)` — montant mono-valeur =
  >    AUCUNE variance d'arme. `StatAmount.calculate` normalise son sélecteur via `_units_of` (un ref-unité
  >    seule `Caster()`/`Self@0x148` → `[dict]` = set de 1 ; même piège que `Tiles`/`Sub`).
  > 3. **helper partagé `profile_pierce(ctx, profile, ranged)`** (extrait de `ability_attack_params`) : le
  >    perçage `clamp(0,100, PiercingRatio + ExtraPierce + ExtraPierce{Melee|Ranged})` commun aux deux modes.
  >
  > **DEUX factories natives distinctes** (à ne pas confondre) : `DSLFactory.AttackWithAttackDamage @180de9fb0`
  > (Psyker/ThunderousAssault — chemin attaque-damage reduce/crit/block) vs `DSLFactory.AttackWithAbilityDamage
  > @180de9c90` (EnvFireTile — `Direct(3)` = dégât DIRECT sans crit/block). EnvFireTile (slice-19 ✅) route par un
  > chemin DIRECT — feuille NEUVE `AttackWithAbilityDamage` → `AttackDamageOperation.execute_direct` (bare
  > `apply_pierce_and_modifiers`, pas de crit/block/spread/after-hit), PAS `execute_normal_like`.
  >
  > ⚠ **RENOMMAGE natif (slice-19, « coller au natif »)** : l'ancienne classe Python `AttackWithAbilityDamage`
  > mirrorait en réalité `AttackWithAttackDamage @180de9fb0` (crit/block) → RENOMMÉE partout (65 occ / 4 fichiers).
  > La classe `AttackWithAbilityDamage` désigne DÉSORMAIS la vraie factory DIRECT `@180de9c90`. **Les notes de
  > slices 3–13 ci-dessous emploient l'ANCIEN nom `AttackWithAbilityDamage` pour la feuille crit/block → lire
  > `AttackWithAttackDamage`.**
  > **ActOfFaith accumulate (slice-20)** = plus riche que `AddEffect(0x3f9)` seul : le décompile `@181219a70`
  > est `op_Addition(AddEffect(0x3f9, Self@0x148), If(<HasTrait(killer,Imperial) & AreFriends & AreEqual(
  > UnitNormalAttackType(killer),0x49e) & IsMeleeAttack>, Maybe(AddEffect(0x3f9), ConfigVar(0x453))))` — un
  > 2e stack CONDITIONNEL (kill mêlée par un allié Imperial d'un normal-attack précis), + le split stat-mod →
  > `ActOfFaithBuffEffect.ApplyModification` (impératif, effet).
- **Tranche DÉPLACEMENT — ✅ (slice-21a PUSH + slice-21b CHARGE/KillDeadUnits)** : les 3 feuilles de la
  sous-séquence déplacement de `ThunderousAssault.ExecuteBehaviour @1812158b0` sont portées et câblées dans
  `thunderous_assault_tree` (arbre `((((attaque & stun) & push) & kill-dead) & move-caster)` = mirror exact du
  décompile) :
  - **`PushUnit`** (slice-21a — `DSLFactory.PushUnit @180df9540` → `DisplaceUnitBehaviour(type=1)`) →
    `DisplaceUnitOperation(type=1=FindTileToPush @180e695e0)` (`engine/runner/operations/displace.py`) : pousse
    la cible d'1 hex à l'opposé du pousseur le long de la ligne hex (mirror `GetTilesBehind @18106a150`,
    géométrie evenq **parity-safe** via les tables `EVENQ` validées — PAS de conversion cube brute), délègue à
    `MoveUnitOperation` (== natif : DisplaceUnit émet MoveUnit@0x7e). Garde `IsDisplaceable` (mort / `BigTarget`
    =1017 / `Immovable`=17 → no-op). Câblé dans `thunderous_assault_tree` + `crushing_claws_splash_tree`.
  - **`MoveUnit`** (slice-21b — `DSLFactory.MoveUnit @180df6ae0` → `MoveUnitBehaviour.Execute @180fca4f0`) →
    `MoveUnitOperation` : le CASTER CHARGE dans la tuile LIBÉRÉE par le push. Dest = `TargetTile()` = tuile
    **PRE-push** de la cible : le `DslContext` étant un **SNAPSHOT pré-cast** (`entities_from_state` construit
    une fois), `_pos(ctx.target)` reste la tuile d'origine même après le push → collapse GRATUIT du
    `Cache(First(Nearest(Tiles(target),casterPos)))` natif (single-tile target). Garde `CanAddUnit` repliée en
    **LIVE** dans la feuille (mirror `CanAddUnitTileSelector.Select @180ee4230` → `CanAddUnitFromAbility` sur
    contenu de tuile live — le nœud `CanAddUnit` du port est snapshot-based, faux post-push) : le caster ne suit
    QUE si le push a libéré la tuile (garde `local_308==0`). Les 5 sélecteurs d'OPTIONS (+0x70..+0x90) sont nuls
    ici (défauts) → cascade after-move flag-driven (overwatch-charge/steppable) NON déclenchée (flaggé, comme le push).
  - **`KillDeadUnits`** (slice-21b — `DSLFactory.KillDeadUnits @180df5c60` = `Kill(subject, DownedUnits(units)
    @180dee790, options) @180df5cb0` → `KillUnitBehaviour.Execute @180fc8b10`) : le natif finalise les DOWNED
    (flag 0xf) en DIFFÉRÉ. Chez nous la mort est finalisée **INLINE** dans l'attaque (`damage.py:152`
    `alive=False` + on-death) et les morts sont hors-occupation → mirror STRUCTUREL **no-op** (re-kill =
    double-fire on-death) ; journalise les downed LIVE. `MoveUnit` trouve la tuile libre via l'occupation live
    (morts exclus) même si l'attaque a tué la cible → ordre natif respecté sans mutation redondante.
  - **DÉTERMINISTE** (push/kill/move sans rng → ne décalent pas l'ordre RNG des dégâts). Validé : e2e offline
    déterministe (cible poussée sur tuile géométrique **ET** caster chargé dans la tuile libérée,
    `test_thunderous_assault_push_live.py`) + 0 régression (stun BigTarget no-op + CrushingClaws inchangé).
  - **RESTE (raffinements ≥ slice-21c, flaggés)** : distance MULTI-hex (`maxCount` = config global runtime, à
    confirmer live 1-vs-2 — porté à 1 hex `_PUSH_MAX_DIST=1`), steppable-crush, knockback-DAMAGE
    (`ApplyKnockbackTo @180e67fc0`, peut tuer → death-triggers), fall-damage d'élévation, cascade after-move
    flag-driven du move (overwatch-charge).
- **Groupe 3 — ✅ TERMINÉ** : ~~FinalJustice~~ (**slice-22 ✅** : feuille NEUVE `UseActiveAbility` = dispatch
  récursif d'ability, spécialisée attaque-normale — cf. ci-dessous) · ~~ArcaneShield~~ (**slice-23 ✅** : feuille
  NEUVE `CreateShield` — cf. ci-dessous) · ~~TheBetrayer_TakeTurn~~ (**slice-24 ✅** : les DEUX feuilles E routées
  par le DSL, sélecteurs S collapsés — cf. ci-dessous). ⇒ **TOUTES les abilities #149 sont migrées ; toutes les
  feuilles E sont portées.** Le SEUL reste (hors #149) = replier la composition STRUCTURELLE de TheBetrayer_TakeTurn
  (`If`/`&`/`Not` + prédicats `IsAdjacent`/`AmountIsGreaterThanZero` en NŒUDS live) en un ARBRE DSL unique — exige
  que la couche prédicat DSL lise l'état LIVE post-move (le `DslContext` est un snapshot figé) : **axe SÉPARÉ**
  (S-family / playbook-transverse), à décider comme chantier propre.

  > **PRIMITIF `UseActiveAbility` (slice-22, RE `@180fd9930` décompile frais)** — dispatch RÉCURSIF d'ability :
  > `UseActiveAbilityBehaviour.Execute` itère le sélecteur de cibles (+0x58) et pour chaque cible ré-émet une
  > Operation « use-ability » de l'`ability_type` (+0x60) via le collecteur `proc` (fixant `subject`=cible
  > courante). **Seul usage porté (FinalJustice) = `UnitNormalAttackType`** ⇒ la feuille SPÉCIALISE le dispatch
  > à l'attaque normale (`AttackDamageOperation.execute`, resolveur ECS déjà bit-exact) = le corps impératif
  > `_finaljustice_attack` validé. Dispatch d'une ability NON-normale (aucun usage Groupe 3) = flaggé (re-entrer
  > le pipeline via `visit_ActiveAbilityMessage`). Le sélecteur AI `SortUnitsByDamageUtility(ValidNormalAttack
  > Targets)` reste IMPÉRATIF (`_finaljustice_target`) **collapsé en `Target()`** (== ThunderousAssault, doctrine
  > slice-18/19). ⚠ **Correction du sketch** (l'avertissement ⚠ « re-confirmer au décompile » l'avait prédit) :
  > **TheBetrayer_TakeTurn n'utilise PAS `UseActiveAbility`** mais `GetDamageBehaviour` (= `AttackWithAttackDamage`).
  > `UseActiveAbility` est propre à FinalJustice.
  > **Fix connexe (slice-22)** : le split `triggers.py` → package `triggers/` avait laissé 4 helpers privés
  > (`_adjacent_enemies` base.py ; `_finaljustice_target`/`_normal_attack_health_range`/`_damage_utility_weights`
  > loki.py) NON re-exportés dans `__init__.py` → `test_finaljustice_live` rouge (avant même le behaviour).
  > Re-export complété (cohérent avec les autres helpers privés déjà exposés). 0 régression (5 tests verts).

  > **PRIMITIF `CreateShield` (slice-23, RE `@180fc2650` décompile frais)** — feuille de bouclier :
  > `CreateShieldBehaviour.Execute` itère le sélecteur de cibles (+0x50), évalue le montant-formule (+0x58) et
  > pour chaque cible émet une Operation « create-shield » (montant + durée + options) → chez nous
  > `ShieldComponent.add_or_update_shield(amount, source, remaining)` (cumule same-source/same-durée). Seul usage
  > (ArcaneShield) : `CreateShield(<AI-target>, ConfigVar(0x27=shieldHp), self.Id, TurnsFromRounds(1))`. Le
  > sélecteur AI-target (S lourd : `SurroundingFriends → UnitsWithoutTrait(0x1b) → Randomize → SortByFormula(
  > faction+distance+not-self) → First → Cache`) reste IMPÉRATIF (`_arcaneshield_target`) **collapsé en `Target()`**,
  > et le montant `ConfigVar(0x27)` (formule V) calculé impérativement (`ability_var`) → SCALAIRE (même double
  > collapse S+V que FinalJustice, doctrine slice-18/19). `_arcaneshield_grant` migré ; bit-exact par construction
  > (même `add_or_update_shield`). Test NEUF `test_arcaneshield_live` (allié in-range → bouclier sur l'allié ;
  > allié mort → fallback soi). 0 régression (3 tests verts).

  > **TheBetrayer_TakeTurn migré (slice-24, RE `@1811a4f70` décompile frais)** — arbre natif RE-confirmé :
  > `If( AmountIsGreaterThanZero(target), Inform(0xbf) & If(NOT IsAdjacent(caster,target,3), MoveUnit(caster,
  > bestTile, options=NULL)) & If(IsAdjacent(caster,target,3), GetDamageBehaviour(target)) )`, avec
  > `target = Cache(GetAttackTarget(AdjacentTiles(MovableTilesInRange(caster,range))))` et `bestTile =
  > First(SortByFormula(SortTilesByUtility((AdjacentTiles(target) & movable).Otherwise(movable)),
  > MinPathLength))`. **Les DEUX feuilles E routent désormais par le DSL** (== ThunderousAssault) : move =
  > `MoveUnit(Caster(), FixedTiles([bestTile]))` ; attaque = `AttackWithAttackDamage(Target(), "TheBetrayer",
  > "Eviscerate", melee)` (bit-exact : mêmes `ability_attack_params` + `execute_ability_attack`). **Trouvaille
  > fidélité** : le nœud `MoveUnit` a ses OPTIONS ENTIÈREMENT NULLES (`local_a8..local_78 = 0` @1811a4f70) —
  > exactement comme ThunderousAssault → feuille `MoveUnit` plaine fidèle. Les sélecteurs/prédicats S restent
  > IMPÉRATIFS, COLLAPSÉS (doctrine slice-18/19) : `GetAttackTarget` → `_betrayer_target` fourni comme
  > `Target()` ; la chaîne tuile `First(SortByFormula(SortTilesByUtility(...), MinPathLength))` → `_betrayer_stop_tile`
  > injecté via le VÉHICULE DE COLLAPSE tile-domain NEUF `FixedTiles` (analogue de `Target()` pour une tuile
  > pré-résolue) ; `IsAdjacent` (dist-1) = `_is_adjacent_units` relu AVANT/APRÈS le move = la re-éval LIVE
  > native (le move mute la position → l'attaque re-teste). `Inform(0xbf)` = notif AI/UI = NO-OP observable
  > (feuille `Inform`) non modélisée. **Refactor** : `_betrayer_move` (fusion tuile+move+after-move) scindé en
  > `_betrayer_stop_tile` (COLLAPSE S pur) + move-via-feuille ; l'import mort `AttackDamageOperation` (loki.py)
  > retiré (plus aucun call-site après slices 22/24) ; re-export `_betrayer_take_turn`/`_betrayer_target`/
  > `_betrayer_stop_tile`/`_is_adjacent_units`. **Fidélité after-move (task #4 RÉSOLU, RE @180e79770)** : l'`Emit`
  > `after_move_triggers` (overwatch sur le move forcé) est FIDÈLE, PAS un over-trigger — `EvaluateAfterMoveTriggers
  > @180e79770` émet `On(4)` gaté par `if (param_6 != 0) return`, `param_6` = options[4] du `MoveUnit` = flag
  > SUPPRESS (défaut 0 = overwatch ACTIF) ; options NULLES (Kharn == ThunderousAssault) => `On(4)` émis. Émission
  > UNIQUE (feuille `MoveUnit` -> `MoveUnitOperation.execute` position-seule). Détail → `dsl-live-context-substrate.md`. Test NEUF
  > `test_thebetrayer_take_turn_migration_live` (move+attaque via feuilles ; adjacent no-move) ; guard fort =
  > `test_thebetrayer_turnstart_live` (replay-diff LIVE : cible/tuile-move/attaque == natif). 0 régression (5 verts).
  > **S-chantier (Voie A) IMPLÉMENTÉ (2026-07-18)** : composition repliée en UN arbre DSL unifié (`Seq`/`If`/
  > `Not` + `IsAdjacent`/`Inform`) sur UN contexte `entities_from_state` dont les unités sont des `LiveUnit`
  > (pos/hp/alive re-lus du `state` par éval → re-éval live du MÊME nœud `IsAdjacent` à travers le move).
  > Plus aucun `_is_adjacent_units` impératif. Substrat natif RE prouvé (4×) + détail d'implémentation →
  > **`docs/rl/dsl-live-context-substrate.md`** (l'`AbilityEntities` tient une RÉF `+0x40`, position re-dérivée
  > live ; `&` = `CombinedBehaviour.Execute @180ffe730` court-circuit ; `+0x48` = `caster_pos`, sweep AI figé).
  > Sélecteurs S lourds (cible/tuile) restent COLLAPSÉS ; `after_move` overwatch FIDÈLE (task #4 RÉSOLU, RE @180e79770). RESTE =
  > généraliser le live-by-ref à la surface T/S (cas-par-cas). Validé 4/4 (A1 LiveUnit) + 4/4 (A2 arbre).

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
| `PerformAIAttackFromCurrentPosition @180df8a10` | `PerformAIAttack` (EffectNode : résout le DOMAINE — tuiles ou unités — puis **délègue** au corps UNIQUE `loki/summon.py::perform_ai_attack_from_current_position` : cible `_nearest_enemy`, gate `_in_attack_range` = `TargetingQuery$$GetRange` clamp `ForcedInMelee` inclus, `AttackDamageOperation.execute`, **dispatch after-hit inconditionnel**) | **#199** ; de-fork 2026-07-26 (`case-217` §5) |
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
1. amorce, `rl_duel build --seed 20260716 --rank 17 --p-units orksRuntherd,orksNob --a-units astraCreed,astraBullgryn --board C1_01`.
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

## Slice-3 (#203, 2026-07-17) — 2e behaviour DSL : ThunderousAssault + effet-nœuds ATTAQUE/EFFET

**2e behaviour combat migré en arbre DSL** (après GetEmRuntz), et surtout **2 effet-nœuds workhorses** portés
(débloquent des familles entières) :

- **`AttackWithAbilityDamage`** (`DSLFactory.AttackWithAttackDamage @180de9fb0` → `AttackDamageBehaviour`+
  `AttackBehaviour.Execute`) : wrapper MINCE au-dessus de l'Operation DÉJÀ bit-exact
  `AttackDamageOperation.execute_ability_attack`. Débloque **toute la famille attaque d'ability** (refcount
  natif 113+). `(base_min,base_max,pierce,hits)` via `ability_attack_params(ability_id, profile)` = MÊME
  source que l'impératif.
- **`AddEffect`** (`DSLFactory.AddEffect @180de6d20` → `AddEffectBehaviour.Execute`) : wrapper au-dessus de
  `AddEffectOperation.execute`, `source`=caster (AbilityStateReference), `target`=sélecteur, durée
  `TurnsFromRounds`. Débloque **tous les applicateurs d'effet** (refcount natif 403, #6 top-missing du
  catalogue). ≠ `AddBondEffect` (qui LIE deux unités).
- **`Target()`** (`entities/selectors.py`) : sélecteur d'unité-cible (lit `ctx.target` = `factory+0x178`),
  frère de `Subject()`. `entities_from_state(state, caster, target_id)` bind désormais `ctx.target`.

**RE — `ThunderousAssaultAbility.ExecuteBehaviour @1812158b0`** (id 1043, DÉCOMPILE gqfc5mff6c) :
```
ExecuteAtomic(
    AttackWithAttackDamage(caster@0x160, Units(Cache(First(Nearest(Tiles(target@0x178), casterPos)))),
                           MinMaxDamage, GetDamageProfile=Power, hits=GetNumberConstant(0x2f))
  & AddEffect(0x48a=Stunned=1162, AbilityStateReference, target@0x178, TurnsFromRounds(1))
  & PushUnit(caster, target) & KillDeadUnits(ForClearDeadUnitsBlockReviveOverkill) & MoveUnit(caster, CanAddUnit) )
```
Le ciblage `Units(Cache(First(Nearest(Tiles(target), casterPos))))` COLLAPSE en `ctx.target` pour une ability
mono-cible mêlée (== la cible du message, que l'IA a choisie = l'impératif live-validé).

**Port** — `thunderous_assault_tree()` (**`loki.py`**, cf. « structure générique vs spécifique » ci-dessous) :
```
AtomicGroup( op_and( AttackWithAbilityDamage(Target(), "ThunderousAssault", "Power", melee),
                     AddEffect(STUNNED, "Stunned", Target(), 1) ) )
```
push/kill/move = **tranche DÉPLACEMENT différée** (no-op, exactement comme l'impératif). `op_and`
(`CombinedBehaviour`) : effets PURS → pas de court-circuit → l'attaque ne coupe pas le stun (qui s'applique
inconditionnellement après, même si l'attaque tue — live-validé). **Bit-exact BY CONSTRUCTION** : mêmes
Operations, même ordre, mêmes args, même `state.rng`.

**Validé** : import OK + **2 tests live PASS** (`test_damage_ability_live.py` = dégât d'ability bit-exact vs
live ; `test_effect_stun_live.py` = pose Stunned 1162 rem=1 + enfants). L'impératif `ThunderousAssault.
execute_behaviour` (attaque+stun à la main) a été **REMPLACÉ** par l'exécution de l'arbre. `AttackWithAbility
Damage`/`AddEffect` sont désormais réutilisables pour migrer les autres attaques d'ability (ArmoriumCherub,
SpiritLeech, CrushingClaws, splashes…).

**Résidu** : confront STRUCTUREL live optionnel (tracer-v2 DSLFactory #200 sur un cast ThunderousAssault) —
non bloquant ici, le décompilé de `ExecuteBehaviour` étant sans ambiguïté (séquence directe de `DSLFactory.X`)
et le comportement live bit-exact. La tranche DÉPLACEMENT (`PushUnit`/`KillDeadUnits`/`MoveUnit`) reste à porter
(commune à plusieurs abilities).

### RÈGLE DE PLACEMENT — générique (nœud) vs spécifique (arbre) = STRUCTURE NATIVE

Correction structurelle (feedback user pendant slice-3) : NE PAS mélanger, dans un même fichier, les **nœuds
GÉNÉRIQUES réutilisables** et les **arbres d'ability SPÉCIFIQUES**. Le natif les sépare en namespaces distincts
→ le port doit refléter cette organisation (« structure offline == structure native ») :

Namespace natif RÉEL (table de symboles vérifiée) → **4 emplacements distincts** :

| Native | Rôle | Port |
|---|---|---|
| `IdunBattle.Entities.Behaviours.*` (`CombinedBehaviour`, `ForeachBehaviour`, `MaybeBehaviour`, `IfBehaviour`, `AtomicGroupBehaviour`) | COMBINATEURS purs (runner-agnostiques) | `engine/entities/behaviours.py` |
| `IdunBattle.Entities.Behaviours.*` (`SpawnUnitBehaviour` @180fd5ab0, `AttackBehaviour` @180fba0e0 / `AttackDamageBehaviour` @180fbb6e0, `AddEffectBehaviour` @180f947e0, `AddBondEffectBehaviour`, `PerformAIAbilityUnitBehaviour` @180fcb940) | FEUILLES à effet, GÉNÉRIQUES mais **runner-couplées** (émettent une Operation) | `engine/runner/abilities/behaviours.py` |
| `IdunBattle.Entities.Selectors.*` (`AllAliveMachinesSelector`=`Children`, `LastUnitAttackedBySelector`) / `Entities.Formulas.*` (`TotalAttacksMadeFormula`, `UnitTurnsStartedFormula`) | SÉLECTEURS / FORMULES (accesseurs runtime) | `engine/entities/selectors.py` + `engine/entities/formulas.py` |
| `IdunBattle.Entities.Abilities.Active.Loki.<Ability>.ExecuteBehaviour` | ARBRE **SPÉCIFIQUE** à une ability (compose les nœuds ci-dessus) | `engine/runner/abilities/loki.py` (avec sa classe d'ability) |

Slice-3 a d'abord (à tort) mis dans `dsl_behaviours.py` à la fois les feuilles génériques, les accesseurs
(`Children`/`TotalAttacksMade`…) ET l'arbre spécifique `thunderous_assault_tree`. **Mirror complet appliqué** :
- les arbres (`thunderous_assault_tree`/`getemruntz_tree`/`getemruntz_taunt_tree`) → `loki.py` ;
- les accesseurs `Children`/`LastUnitAttackedBy` → `entities/selectors.py`, `TotalAttacksMade`/
  `UnitTurnsStarted` → `entities/formulas.py` (leur vrai namespace `Entities.Selectors`/`Formulas`) ;
- le fichier renommé `dsl_behaviours.py` → **`behaviours.py`** (il ne contient plus QUE des
  `Entities.Behaviours` feuilles, MÊME namespace natif que `entities/behaviours.py`, split par layering) ;
- helper `resolve_unit` partagé → `dsl/base.py`.
Toute future migration d'ability suit cette organisation.

## Slice-4 (#204, 2026-07-17) — 3e behaviour DSL : CrushingClaws (splash Foreach + sélecteur)

**RE — `CrushingClawsAbility.ExecuteBehaviour @1811cd5e0`** (id 1105, tyranTyrantGuard, DÉCOMPILE gqfc5mff6c)
+ lambda `<ExecuteBehaviour>b__0 @1811e3c60` (corps du `Foreach`). Arbre natif EXACT (`op_Addition` = `+`) :

```
splash = UnitsWithoutTrait( AdjacentEnemies(caster,r1) & (AdjacentFriends(target,r1) − {target}), 0xd=Object )
ExecuteAtomic(
    ((  AddBondEffect(0x1b Taunted, caster, target, TurnsFromRounds(1))          # taunt cible
      + AddEffect(0x429 Pinned, target, <défaut>) )                              # « Suppressed » cible
      + AttackWithAttackDamage(caster, target, MinMaxDamage, Piercing, 0x2f=2) ) # attaque principale
    + Foreach(splash, s => PushUnit(caster,s)                                     # [DÉPLACEMENT différé]
                        + If(IsAlive s) AddEffect(0x429 Pinned, s, <défaut>)
                        + If(IsAlive s) AttackWithAttackDamage(caster, s, MinMaxDamage2, Physical, 0x32=1)) )
```

**Décompile décisif — `DSLFactory.AdjacentEnemies/AdjacentFriends(ctx, center, mode, flag)`** (@180de80c0/@180de81d0)
= `{Enemies|Friends}(referent=**center**, Units(AdjacentTiles(center)) − center)` : le référent d'amitié est le
**centre lui-même** (pas le caster). `AdjacentFriends(target)` = **alliés de la cible** ⇒ = ennemis du caster
(2 équipes). Port = convention ÉTABLIE Harvester (`active_ability.py`) : « ennemis-du-caster autour de `<tile>` »
= `AdjacentEnemies(<tile>Tile())` (référent caster + centre géométrique `<tile>`). Splash porté =
`And(AdjacentEnemies(CasterTile()), AdjacentEnemies(TargetTile()))` — chaque centre s'auto-exclut (`_within`
d>0). `UnitsWithoutTrait(Object=13=0xd)` : **0xd MAPPÉ** `UnitTrait.Object` (#158) → l'exclusion scénerie est
PORTÉE (l'ancien impératif la SKIPPAIT « enum inconnu » → le DSL est PLUS fidèle, dégrade en no-op sans le trait).

Arbre porté `crushing_claws_tree()` (`loki.py`) = mirror 1:1 (ordre natif **taunt, pin, main, foreach**). Nœuds
réutilisés (slice-3/#199) + 2 EXTENSIONS mineures de feuilles génériques :
- `AttackWithAbilityDamage` : + clés config `min_key`/`max_key`/`hits_key` (défaut `minDmg`/`maxDmg`/`nrOfHits` =
  `MinMaxDamage`/`0x2f` ; splash passe `minDmg_2`/`maxDmg_2`/`nrOfHits_2` = `MinMaxDamage2`/`0x32`).
- `AddEffect` : `duration_rounds=None` → duree DÉFAUT (`DefaultAmountOfRounds`), mirror de l'arg natif `0` d'`AddEffect`
  sans `TurnsFromRounds` (Pinned CrushingClaws) vs explicite (Stunned ThunderousAssault = `TurnsFromRounds(1)`).

L'impératif `CrushingClawsAbility.execute_behaviour` (avec `_adjacent_to_both`, encore utilisé par ScythingTalons)
est REMPLACÉ par l'exécution de l'arbre. **Bit-exact BY CONSTRUCTION** : mêmes Operations/args/`state.rng` ; l'ordre
natif (effets AVANT le main) est équivalent au main-first de l'impératif — les effets pin/taunt actifs pendant le main
ne modifient PAS le dégât (PROUVÉ A/B, cf. #205).

**Validation** (`test_damage_crushingclaws_live.py`, session 26) : dégât ARBRE == appel main-only DIRECT (fidélité
migration bit-exact vs baseline) + Taunted(27 composite)+Pinned(1065) posés **off == live**. En 1v1 le splash
`And(...)` est vide (seul ennemi = la cible, auto-exclue) → per-coup principal propre.

**#205 (GAP PRÉ-EXISTANT, hors migration)** : le per-coup principal vs LIVE diverge légèrement (ex. off=[1589,1469]
vs live=[1590,1490] ; base=[1496,1996], pierce=80, armor=1909, 2× Piercing). PROUVÉ indépendant de la migration par
**A/B** (`cc_ab_probe` : main-only-direct == arbre → l'ancien impératif aurait échoué à l'identique, jamais bit-exact-
testé avant). Gap = pipeline dégât Piercing/armure haute (arrondi plage réduite ?), pas le DSL. Non asserté exact.

**Résidu** : confront LIVE dédié du SPLASH (géométrie 3-unités : un ennemi adjacent caster+cible) — bit-exact BY
CONSTRUCTION (mêmes nœuds + sélecteur pattern-Harvester validé), différé. Tranche DÉPLACEMENT (`PushUnit`/`KillDeadUnits`/
`MoveUnit`) toujours à porter (commune ThunderousAssault/CrushingClaws/…).


## Slice-5 (#206, 2026-07-17) — 4e behaviour DSL : SpiritLeech (attaque conditionnelle + lifesteal Heal)

**RE — `SpiritLeechAbility.ExecuteBehaviour @181209900`** (id 1104, tyranNeurothrope, DÉCOMPILE gqfc5mff6c). Arbre
natif EXACT (`op_Addition` = `+`, `Execute` — PAS `ExecuteAtomic`) :

```
Execute( ((  AttackWithAbilityDamage(self, target, GetAttackDamage, Psychic, nrOfHits=0x2f=1)   # attaque
           + SetCache(PercentageOf(LastAttackDamageMade, ConfigVar 0x4b hpToHealPct)) )          # montant heal (cache)
           + AddEffect(0x429 Pinned, target, <défaut>) )                                          # « Suppressed » cible
           + Heal(self, GetHealTargets, cachedHealAmount) )                                        # lifesteal
```

- **`GetAttackDamage @181209dd0`** (COMBAT, param_3=0) = `ConditionalAmount( NOT HasEffect(target, Pinned 0x429),
  MinMaxDamage, MinMaxDamage + extraDmg(ConfigVar 8) )` → si la cible est DÉJÀ Pinned/« Suppressed » ⇒ +`extraDmg`
  à plat sur les 2 bornes (avant le tirage). `extraDmg` ∈ `variablesAffectedByRarityBonus` → multiplier = celui du
  caster. Profil Psychic, ranged (range 3). L'état Pinned lu = AVANT le Pin de ce cast (l'attaque précède l'AddEffect).
- **`GetHealTargets @18120a1e0`** = `op_Addition( Self, UnitsFromFaction(Friends(self, AdjacentUnits(self,1)),
  0xc=Tyranids) )` = le caster (Self, SANS gate faction) UNION les alliés VIVANTS Tyranids adjacents (hex 1).
- **`GetHealAmountForExecution @181209f00`** = `PercentageOf(LastAttackDamageMade, ConfigVar 0x4b hpToHealPct, mode=1)`
  (`LastAttackDamageMade` = total dégât-santé de la dernière attaque ; `mode=1` = **Ceiling**, node canonique
  `entities/formulas.py`). `hpToHealPct` HORS `variablesAffectedByRarityBonus` → valeur brute (multiplier 100).

Arbre porté `spirit_leech_tree()` (`loki.py`) = mirror 1:1 = `op_add(op_add(Attack, Pin), Heal)`. Nouveaux nœuds :
- **Feuille `Heal`** (`runner/abilities/behaviours.py`, runner-couplée) → `HealUnitOperation.execute` (mutation PV, cap
  `hp_max`, gate `Cursed`) ; `amount_fn(entities, ectx)` = mirror `GetHealAmountForExecution` (lit le total de la dernière
  `AttackWithAbilityDamage` dans `ectx.emitted`). Source = `ctx.caster`. Émet `Heal` (amount + heals).
- **Sélecteurs `Union` (`op_Addition`) + `UnitsFromFaction`** (`entities/selectors.py`) : `spirit_leech_heal_targets()` =
  `Union(Caster(), UnitsFromFaction(Alive(AdjacentFriends(CasterTile())), "Tyranids"))`. `AdjacentFriends` (référent
  caster) = `Friends(self, AdjacentUnits(self,1))` (self exclu `_within` d>0) ; `Alive` mirror le filtre `Units`
  (=sur tuile, vivant). Faction résolue via un callback ctx `faction_of` (nouveau champ `DslContext`, même pattern que
  `has_trait`/`get_stat`, fourni par `entities_from_state` via `_faction(visualId)` = `FactionId` gameconfig).
- **`AttackWithAbilityDamage` + `damage_override`** : callable `(state, caster, target, bmin, bmax) → (bmin, bmax)`
  mirror d'un `AActiveAbility.GetAttackDamage` SURCHARGÉ (le natif passe la node de dégât calculée à l'attaque).
  Défaut None = dégât générique `MinMaxDamage` (rétro-compat totale : ThunderousAssault/CrushingClaws inchangés).
  SpiritLeech passe `spirit_leech_get_attack_damage` (bonus Suppressed).

**`SetCache`/`Cache` FOLD** : le nœud `SetCache` (mémoïse le montant de heal avant le Pin) est plumbing PUR sans effet
observable dans l'exécuteur eager (même réduction que `Cache`/#201/#202) — l'ordre A→Pin→Heal rend la MÊME valeur (le
Pin n'affecte pas le dégât déjà infligé ; le heal cible Self+alliés, pas la cible). L'impératif `_adjacent_tyranid_allies`
est SUPPRIMÉ (remplacé par le sélecteur DSL `spirit_leech_heal_targets()`).

**Round-mode heal CORRIGÉ au décompile** : `PercentageOf` natif passe `mode=1` = **Ceiling** (`_round_fix64`) ; l'ancien
impératif tronquait (`int()` = floor → gap +0/+1 HP, ex. 1555.8 → ceil 1556 vs trunc 1555). `spirit_leech_heal_amount`
utilise désormais `_round_fix64(Fraction(total×pct,100), 1)` = mirror exact de `GetHealAmountForExecution` (node canonique
`entities/formulas.py PercentageOf`). Le dégât étant bit-exact vs live, seul le round-mode changeait ; corrigé + assert du
test aligné (Ceiling). Le reste de l'arbre est bit-exact BY CONSTRUCTION vs l'impératif.

**Validation** (`test_spirit_leech_combat_live.py`, session 26) : dégât per-coup **off == live** (COMBAT config-based) +
Pinned(0x429) posé + `heal_amount == ceil(dmg×hpToHealPct/100)` + le CASTER (Self) est cible du heal (`op_Addition(Self,…)`).
Régression : `test_damage_crushingclaws_live` + `test_damage_ability_live` (ThunderousAssault) re-PASS (le `damage_override`
défaut None laisse le chemin générique intact).


## Slice-6 (#208, 2026-07-17) — 5e behaviour DSL : PlasmaGrenade (splash MULTI-cible, feuille `multi=True`)

**RE — `PlasmaGrenadeAbility.ExecuteBehaviour @1811f99e0`** (id 1098, eldarSmnGuardian, DÉCOMPILE gqfc5mff6c). Arbre
natif EXACT (`op_Addition` = `+`, plain `Execute` — PAS `ExecuteAtomic`) :

```
Execute( AttackWithAbilityDamage(caster, target,                            RandomAmount(minDmg=var0xc,maxDmg=var0xd), Plasma, nrOfHits=0x2f)     # [MAIN]
       + AttackWithAbilityDamage(caster, Enemies(caster, AdjacentUnits(target,1)), RandomAmount(MÊME),                       Plasma, nrOfHits_2=0x32) )  # [SPLASH]
```

Point CLÉ : le **SPLASH est UN SEUL `AttackWithAbilityDamage` dont la cible est un SÉLECTEUR MULTI-unités**
(`Enemies(caster, AdjacentUnits(target,1))`), **PAS un `Foreach`** (≠ CrushingClaws, dont le splash a une logique
per-unité push/pin/gate ⇒ Foreach). Le `RandomAmount(minDmg/maxDmg)` (node) est PARTAGÉ main/splash ; seule la constante
de coups diffère (`nrOfHits`=0x2f vs `nrOfHits_2`=0x32). Profil Plasma, ranged (range 2).

**`AttackBehaviour.Execute @180fb91a0`** (RE) : quand `targets` résout N unités, il **résout la liste**, l'`OrderBy`
(lambda `<Execute>b__5_0 @180fd9150` = clé scalaire par-unité, vtable +0x158 = ordre de lecture) + `ToList` (si >1), puis
**attaque CHAQUE cible dans l'ordre**. Même pattern d'itération-interne que `Spawn`/`PerformAIAttack`.

Porté :
- **Feuille `AttackWithAbilityDamage` + mode `multi=True`** (`runner/abilities/behaviours.py`) : `evaluate` → liste, tri
  par `id` (= ordre de lecture natif == l'ordre `sorted` de l'impératif `_splash_ability_behaviour` → bit-exact), 1 attaque
  + 1 `emit` par cible. `multi=False` (défaut) = chemin mono-cible `resolve_unit` INCHANGÉ (ThunderousAssault/CrushingClaws/
  SpiritLeech) → zéro régression.
- **Arbre `plasma_grenade_tree()`** (`loki.py`) = `op_add(main, splash)` : `main` = `AttackWithAbilityDamage(Target(),
  Plasma)` ; `splash` = `AttackWithAbilityDamage(Alive(AdjacentEnemies(TargetTile())), Plasma, hits_key="nrOfHits_2",
  multi=True)`. Sélecteur splash = `Alive(AdjacentEnemies(TargetTile()))` = ennemis-du-caster VIVANTS adjacents à la CIBLE
  (`AdjacentEnemies(<tuile>)` = convention Harvester/CrushingClaws, **`_within`/hexgeo** ⇒ board-indépendant, PAS le piège
  #148 boardGraph occupé ; `Alive` compense l'inclusion des cadavres offline, mirror du `Units(AdjacentTiles)`=debout=vivant
  natif, cf. `AllUnits`=alive #202). L'impératif `_splash_ability_behaviour`/`_adjacent_enemies_of` RESTE (partagé par
  Stikkbomb/Fragstorm/ScythingTalons NON migrés).

⚠ **Stikkbomb (1051) ≠ ride gratuit** : son splash natif est `AdjacentUnits(target,1,3)` **sans** wrapper `Enemies`
(≠ PlasmaGrenade qui a l'`Enemies(self, …)` explicite) → sémantique du param-3 team à RE d'abord (l'impératif assume
`_adjacent_enemies_of` pour les deux, hypothèse à vérifier). Slice séparée.

**Caster SUMMON-only** : `eldarSmnGuardian` n'est PAS dans le pool runner (comme votanIronmaster/GravitonRifle) → pas de
cast live direct. **Validation = REPLAY-DIFF sur état LIVE** (`test_plasma_grenade_splash_live.py`, session 26) : l'arbre DSL
(via `PlasmaGrenadeAbility.execute_behaviour`) reproduit BIT-EXACT l'ancien impératif `_splash_ability_behaviour` —
**même set splash** (DSL hexgeo == impératif board `native_sym` sur board plat), **main per-coup** (`[562,570]==[562,570]`) +
**splash per-coup par cible** (`79:[638]`, `81:[544]` identiques), sous le MÊME `state.rng` seedé. Le sélecteur
`AdjacentEnemies` est par ailleurs CONFRONTÉ LIVE en slice-4 (CrushingClaws). Régression : `test_spirit_leech_combat_live`
+ `test_damage_crushingclaws_live` re-PASS (chemin mono-cible `multi=False` inchangé).

## Slice-7 (#209, 2026-07-17) — 6e behaviour DSL : ArmoriumCherub (nœud `EvaluateAbilities` = passif inline)

**RE — `ArmoriumCherubAbility.ExecuteBehaviour @1811b4000`** (id 1014, adeptRetributor «Vindicta», DÉCOMPILE gqfc5mff6c).
Arbre natif EXACT (`op_BitwiseAnd` = `&`, `ExecuteAtomic`) :

```
ExecuteAtomic( AttackWithAttackDamage(caster, target, MinMaxDamage(minDmg 0xc/maxDmg 0xd), Flame, nrOfHits=GetNumberConstant(0x2f)=4)   # [MAIN] 4x Flame ranged
             & EvaluateAbilities(0x4b=AttackInAtomicGroup) )                                                                             # [PASSIF] -> FireOfAbsolution
```

Deux découvertes structurelles :

1. **`AttackWithAttackDamage` (DSLFactory @180dea350) vs `AttackWithAbilityDamage`** : les deux construisent un
   `AttackBehaviour` au-dessus d'un node de dégât. Pour ArmoriumCherub le node = **`MinMaxDamage(target,0)` @180fb2dc0 =
   `RandomAmount(minDmg[0xc],maxDmg[0xd])`** — EXACTEMENT le dégât générique que calcule déjà ma feuille
   `AttackWithAbilityDamage` (via `ability_attack_params`) → **réutilisée telle quelle** (single-target, `multi=False`,
   bit-exact). La branche `MinMaxDamage(target,1)` = `Half(Sum(Direct(min),Direct(max)))` = l'**avg de PRÉDICTION** (#171),
   hors combat.

2. **`EvaluateAbilities(0x4b)` = nœud DSL générique** (`EvaluateAbilitiesBehaviour.Execute @180fc48a0`, ctor @180fc4e10
   champ +0x50 = `EventTriggerType`) : **ÉVALUE les abilities DÉCLENCHÉES du caster pour un `EventTriggerType`**, INLINE
   dans le tree. `0x4b` = **`EventTriggerType.AttackInAtomicGroup`** (75) — l'attaque d'ability ATOMIQUE du caster ;
   ≠ NormalAttack qui passe `EvaluateAbilities(0x26)` (event distinct, xrefs : `ALoki_NormalAttackAbility.ExecuteTriggerAbilities`
   passe 0x26, ArmouredMight/TheQuickening après-move). Pour ArmoriumCherub ce nœud résout le passif **FireOfAbsolution**
   (`FireOfAbsolutionAbility.CreateBehaviour @18121f380` = `Inform(0xb3,target) & AttackWithAttackDamage(caster,
   AdjacentUnits(target,0,3)−caster−target, Direct(var0xb), Flame, nrOfHits) & Maybe(30%=const 0x2a, AdjacentTiles(target))`
   = splash 3x Flame sur les ennemis adjacents à la cible + 30% ignite/hex).

Porté :
- **Feuille `EvaluateAbilities`** (`runner/abilities/behaviours.py`) : `execute` délègue à `evaluate_abilities_for_event`
  (couche dispatch), émet `'EvaluateAbilities'` (liste des résultats des passifs). `event`=`EventTriggerType`, `ranged`
  fourni par l'ability (ArmoriumCherub range-2 → `ranged=True`, == le littéral de l'ancien impératif).
- **Dispatch `evaluate_abilities_for_event`** (`operations/triggers/dispatch.py`) = mirror `EvaluateAbilitiesBehaviour.Execute` :
  `AttackInAtomicGroup` → `_fire_of_absolution_after_attack` (SEUL passif de ce chemin porté ; les autres after-hit de
  l'attaque PRIMAIRE fire déjà DANS l'Operation d'attaque via `after_hit_ability_attack` → **pas de double-fire**).
  Extensible : un futur passif keyé sur cet event s'ajoute ici.
- **Arbre `armorium_cherub_tree()`** (`loki.py`) = `AtomicGroup( op_and( AttackWithAbilityDamage(Target(),"ArmoriumCherub",
  "Flame",ranged), EvaluateAbilities(AttackInAtomicGroup, ranged=True) ) )`. `op_and`=`CombinedBehaviour` PUR (les deux
  volets s'exécutent) ; `AtomicGroup`=inline (#201). Ordre = attaque PUIS passif (== l'ancien impératif, même `state.rng`).

⚠ **FireOfAbsolution a son PROPRE `CreateBehaviour` tree @18121f380** (splash `Direct(var0xb)` + `Maybe` ignite) : sa
migration DSL propre (le passif reste porté impérativement `_fire_of_absolution_after_attack`) = **slice séparée**. Note :
son splash utilise `AdjacentUnits(target,0,3)` — le même **param-3 team** flaggé pour Stikkbomb (à RE avant migration).

**Validation = REPLAY-DIFF sur état LIVE** (`test_armorium_cherub_migration_live.py`, session 26). Caster =
`adeptRetributor` (**BUILDABLE**, porte FireOfAbsolution + ArmoriumCherub → splash RÉELLEMENT exercé, `assert imp_splash`).
L'arbre DSL (via `ArmoriumCherubAbility.execute_behaviour`) reproduit BIT-EXACT l'ANCIEN corps impératif (main via
`execute_ability_attack` + passif via `_fire_of_absolution_after_attack`) sur DEUX états indépendants seedés
identiquement : **main per-coup**, **set + per-coup de splash**, **tuiles ignitées** (même conso RNG `Maybe`) tous égaux.
Régression : `test_plasma_grenade_splash_live` (multi) + `test_damage_crushingclaws_live` (mono-cible) re-PASS.

**Restant loki.py impératif** (post slice-7) : ScarabHive/ScarabSummon (Spawn), ValkyrieStrike (dédié), Stikkbomb (RE
param-3 `AdjacentUnits` d'abord), Fragstorm, ScythingTalons, GravitonRifle ; + tranche transverse DÉPLACEMENT
(`PushUnit`/`KillDeadUnits`/`MoveUnit`).


## Slice-8 (#210, 2026-07-17) — 7e behaviour DSL : ScythingTalons (splash MULTI-cible `_adjacent_to_both`)

**RE — `ScythingTalonsAbility.ExecuteBehaviour @1812059f0`** (id 1065, tyranSmnWarrior, DÉCOMPILE gqfc5mff6c).
Arbre natif EXACT (`op_BitwiseAnd` = `&`, `ExecuteAtomic`) :

```
splash = Unique( Enemies(caster, AdjacentUnits(casterTile,1,3) & AdjacentUnits(targetTile,1,3), 3) )
ExecuteAtomic( AttackWithAttackDamage(caster, target, MinMaxDamage, Bio, condHits1=GetNumberConstant(0x2f)=3)   # [MAIN]
             & AttackWithAttackDamage(caster, splash,  MinMaxDamage, Bio, condHits2=GetNumberConstant(0x32)=2) )  # [SPLASH]
```

Structure = **hybride PlasmaGrenade × CrushingClaws** :

1. **Splash = UN SEUL `AttackWithAttackDamage` avec un SÉLECTEUR MULTI-cible** (PAS un `Foreach` → ≠ CrushingClaws) →
   porté via le mode **`multi=True`** de la feuille `AttackWithAbilityDamage` (résout la liste + `OrderBy` par id =
   ordre de lecture natif), EXACTEMENT comme PlasmaGrenade (slice-6). Plage `MinMaxDamage(minDmg/maxDmg)` **PARTAGÉE**
   main/splash ; seule la constante de coups diffère (`nrOfHits` 0x2f=3 vs `nrOfHits_2` 0x32=2).
2. **Sélecteur splash = `_adjacent_to_both`** (comme CrushingClaws, slice-4) : `Unique(Enemies(caster, AdjUnits(casterTile,1)
   ∩ AdjUnits(targetTile,1), 3))` = ennemis du caster adjacents aux DEUX tuiles. Porté
   `Alive(And(AdjacentEnemies(CasterTile()), AdjacentEnemies(TargetTile())))` : `Enemies(A ∩ B) == Enemies(A) ∩ Enemies(B)`
   (Enemies DISTRIBUE sur l'intersection) et `Unique` est un no-op (`And` dedup déjà par id) ; `Alive` compense
   l'inclusion des cadavres offline (mirror : le natif `AdjacentUnits` n'a que les unités DEBOUT = vivantes, #202/#148).

**`ExecuteAtomic(behaviour, constants, 0x57)` = `DSLFactory.AtomicGroup(dsl, 0x57, callback)`** (`ExecuteAtomic @180fb0930`
décompilé : construit un état de coroutine + `AtomicGroup`, PAS d'auto-fire de triggered-abilities). Le `0x57` est l'**id
du groupe atomique**, inerte offline (`AtomicGroup` = inline #201). ⚠ **ScythingTalons n'a AUCUN nœud `EvaluateAbilities`**
(≠ ArmoriumCherub #209 dont le passif venait d'un nœud EXPLICITE) → rien à évaluer, migration fidèle sans triggered-abilities.

Porté :
- **Arbre `scything_talons_tree()`** (`loki.py`) = `AtomicGroup( op_and( AttackWithAbilityDamage(Target(),"ScythingTalons",
  "Bio",melee), AttackWithAbilityDamage(Alive(And(AdjacentEnemies(CasterTile()),AdjacentEnemies(TargetTile()))),
  "ScythingTalons","Bio",melee, hits_key="nrOfHits_2", multi=True) ) )`. Aucune nouvelle feuille/sélecteur (100 % réuse
  slice-4/6). `op_BitwiseAnd` = `CombinedBehaviour` PUR ; ordre main PUIS splash (== l'impératif, même `state.rng`).
- `ScythingTalonsAbility.execute_behaviour` DÉLÈGUE à l'arbre + split main/splash par target (== PlasmaGrenade). Les helpers
  `_splash_ability_behaviour`/`_adjacent_to_both` restent partagés par Stikkbomb/Fragstorm (non migrés).

⚠ **GAP HITS CONDITIONNELS (tâche #211, HORS migration)** : les coups natifs = `ConditionalAmount(HasTrait(target,
UnitTrait.Summon=2), nrOfHits×2, nrOfHits)` → **DOUBLENT si la CIBLE est un SUMMON** (main 3→6, splash 2→4 ; UnitTrait
value 2 = `Summon`, confirmé). Coups de BASE portés ici (== l'impératif, jamais de sur-compte). Le doublement =
behaviour-changing : nœud `ConditionalAmount` (n'existe PAS dans engine ; `HasTrait` trigger existe), feuille
hits-formule, validation live vs cible summon → tranche séparée.

**Validation = REPLAY-DIFF sur état LIVE** (`test_scything_talons_migration_live.py`, session 26). Caster
`tyranTyrantGuard` (player MELEE buildable) **DRIVÉ dans le cluster ennemi** (maximise le nb d'ennemis adjacents) pour
exercer un splash `_adjacent_to_both` **NON VIDE** — **PREMIER confront LIVE non-vide** de ce sélecteur (empty en 1v1
slice-4). L'arbre DSL reproduit BIT-EXACT l'ancien impératif `_splash_ability_behaviour`+`_adjacent_to_both` sur DEUX
états indépendants seedés identiquement : **même set splash**, **main per-coup**, **splash per-coup** égaux (mesuré :
caster=85 target=77 → main 3× `[965,1280,827]`, splash victime 81 2× `[835,745]`, DSL == imp). Régression :
`test_plasma_grenade_splash_live` (multi) + `test_damage_crushingclaws_live` (mono-cible) re-PASS.

**Restant loki.py impératif** (post slice-8) : ScarabHive/ScarabSummon (Spawn), ValkyrieStrike (dédié), Stikkbomb (RE
param-3 `AdjacentUnits` d'abord), Fragstorm, GravitonRifle (votanIronmaster non-spawnable → non validable live) ; +
tranche transverse DÉPLACEMENT (`PushUnit`/`KillDeadUnits`/`MoveUnit`).


## Slice-9 (#212, 2026-07-17) — 8e behaviour DSL : ValkyrieStrike (nœud unique `AddBondEffect` différé)

**RE — `ValkyrieStrikeAbility.ExecuteBehaviour @181229e40`** (id 1018, astraSmnVoxcaster, DÉCOMPILE gqfc5mff6c).
Arbre natif EXACT (plain `Execute`, **PAS** `ExecuteAtomic`) = **UN SEUL nœud** :

```
Execute( AddBondEffect(0x3fe=1022 ValkyrieStrike_Effect, AbilityStateReference,
                       caster@0x160, target@0x178, caster@0x160, dureeNode=ZERO, 0) )
```

**AUCUNE attaque immédiate au cast.** Le Blast (`constants.damageProfile=Blast, nrOfHits=1`) est le **PAYLOAD de
l'airstrike DIFFÉRÉ** porté par l'effet 1022 (frappe aérienne au tour suivant), **hors** `ExecuteBehaviour`.

Point RE clé = **l'arg7 (durée) = struct 32 octets ZÉRO-initialisé** passé par pointeur (`&local_178`), PAS un
`TurnsFromRounds(n)` (≠ CrushingClaws Taunt / GetEmRuntz qui passent `TurnsFromRounds(1)`). C'est la variante
**durée-défaut** : la durée effective vient de `DefaultAmountOfRounds(1022)`. Mirroré par `duration_rounds=None`
côté port — même sémantique que l'arg natif `0` d'`AddEffect` (Pinned de CrushingClaws).

Porté :
- **Arbre `valkyrie_strike_tree()`** (`loki.py`) = `AddBondEffect(VALKYRIE_STRIKE, "ValkyrieStrike_Effect", Caster(),
  Target(), None)`. `AddBondEffect` (== le natif, LIE source=caster ↔ target : le caster capture la direction du bond,
  args 0x160 en 4e ET 6e position) pose l'effet sur la cible, source=caster ; `None` → `DefaultAmountOfRounds`.
  L'`AbilityStateReference` (arg3) est FOLD dans source=caster (== les ports existants). **Aucun `AtomicGroup`** (natif
  = `Execute`).
- **Carve-out feuille `AddBondEffect`** (`behaviours.py`) : gagne le handling `duration_rounds=None` →
  `duration_override=None` = durée DEFAUT (mirror EXACT de la feuille `AddEffect`, cf. arg7 natif ZÉRO). **`None`-
  conditionnel** → CrushingClaws/GetEmRuntz (`duration=1`) **inchangés** (`turns_from_rounds(1)`=1). 1-liner
  décompile-backed (carve-out règle #149).
- `ValkyrieStrikeAbility.execute_behaviour` DÉLÈGUE à l'arbre (lit l'émission `AddBondEffect` pour le diag). Le PORT
  DÉDIÉ reste une **correction de sur-tir** (1018 a `constants.damageProfile` → `_is_attack_ability`=True → le chemin
  générique tirerait un Blast IMMÉDIAT à tort ; l'enregistrer `ported=True` l'EXCLUT du générique).

Déterministe (**aucun rng consommé**) → **bit-exact BY CONSTRUCTION** vs l'ancien impératif
(`AddEffectOperation.execute(source=caster, target, 1022, SANS duration_override)`).

**Validation = REPLAY-DIFF sur état LIVE** (`test_valkyrie_strike_migration_live.py`, session 26). Carrier natif
(astraSmnVoxcaster) SUMMON-only ; l'effet 1022 est **GLOBAL** (config par type, pas kit-dérivé) → replay-diff
**CASTER-AGNOSTIQUE** : couple cross-team vivant quelconque (cible sans 1022 pré-existant), l'arbre DSL (via la classe
d'ability) reproduit BIT-EXACT l'ancien impératif sur DEUX états indépendants — **même effet 1022 (+ sous-effets
composites), même source, même remaining, même parent**. Vérifie AUSSI le carve-out `None`→défaut (l'arbre passe
`duration_rounds=None`). Régression : `test_damage_crushingclaws_live` (Taunt `AddBondEffect` `duration=1`) re-PASS.

**GravitonRifle (1206, votanIronmaster) — SUPPRIMÉ** (décision user, post slice-9). Le carrier votanIronmaster
n'est **pas** dans le pool du runner (non-spawnable) → GravitonRifle ne peut fire dans **aucun** runner → le port
impératif n'était **jamais confrontable au live** (l'imperatif lui-même invérifiable, indépendamment d'une migration
DSL). Un port qu'on ne peut pas valider contre l'oracle vivant = code spéculatif : **retiré** (`GravitonRifleAbility`
+ sa registration `ABILITY_CLASSES` + exports). Les mirrors d'enum (`ActiveAbilityType.GravitonRifle=1206`,
`GravitonRifle_ExtraPierce=1484`, `enum_maps`) **restent** (les enums mirrorent TOUTES les valeurs natives, indépendam-
ment du portage — convention #158). *Le tree natif (`Execute(op_Addition(AttackWithAttackDamage(target, MinMaxDamage,
Physical, GetHits=3), AddEffect(0x48a Stunned, TurnsFromRounds(nrOfRounds=1))))` @1811e31a0 reste documenté ici pour
mémoire ; il se re-porterait trivialement — même pattern que ThunderousAssault, feuilles existantes — SI un jour
votanIronmaster devient jouable.*

**Restant loki.py impératif** (post slice-9) : ScarabHive/ScarabSummon (Spawn — gros slice : chaîne de sélecteurs
`AdjacentTiles(target)→CanAddUnit→SortByDistance(caster)→First(N)→Cache` + `SpawnUnitOptions.WithStatsFromConfig` +
on-appearance `UseNormalAttackIfAble` + `AddEffect(0x4a3 OverrideDamageProfile)`), Stikkbomb (**BLOQUÉ** : RE team-filter
`AdjacentUnits(target,1,3)` — mur gshared, live confront requis, tâche #213), Fragstorm (splash + `PickRandomly` RNG gap) ;
+ tranche transverse DÉPLACEMENT (`PushUnit`/`KillDeadUnits`/`MoveUnit`).

## Slice-10 (#149, 2026-07-17) — 9e behaviour DSL : ScarabHive (nœud unique `Spawn` + on-appearance embarqué)

**RE — `ScarabHiveAbility.ExecuteBehaviour @181204cb0`** (id 1007, necroSpyder, DÉCOMPILE gqfc5mff6c).
Un noeud `Spawn` **UNIQUE** en plain `Execute` (PAS `ExecuteAtomic`) :

```
Execute( Spawn(caster@0x160, tileSel, unitId=necroSmnSwarm=GetStringConstant(config,0),
               SpawnUnitOptions.WithStatsFromConfig(config)          // team+player caster, stats ability_var
                 .effect       = AddEffect(0x4a3=ScarabHive_OverrideDamageProfile=1187, AbilityState(Parent,this), target@0x178)  // +0x10
                 .onAppearance = UseNormalAttackIfAble(target@0x178)) )                                                            // +0x18
```

- **Le count-2, le placement et `WithStatsFromConfig` vivent DANS `SpawnUnitBehaviour.Execute @180fd3d80`**
  (`GetUnitToSpawn`/`GetTileIds`/`GetStatsToOverride`/`GetAddUnitOptions`), **HORS des DSL-sélecteurs** : le
  tile-sélecteur natif `Cache(First(SortByDistance(CanAddUnit(AdjacentTiles(target)), caster), i))` finit par
  `First`=`PickAtIndexSelector.Select @180ef02e0` = **UN seul élément** (`list[index]`) — le count vient des
  **options**, pas du sélecteur. `TriggerSpawnedUnitBehaviours` fire ensuite les 2 sous-behaviours (effet +
  on-appearance) **par summon**.

**Port** :
- **Feuille `SpawnSummon`** (`runner/abilities/behaviours.py`) = mirror du nœud `Spawn` natif (WithStatsFromConfig
  + effet + on-appearance embarqués). Elle **délègue le SPAWN à l'Operation VALIDÉE LIVE-BIT-EXACT**
  `SpawnUnitOperation.execute` (2× necroSmnSwarm team/player du caster, stats `ability_var`, tuiles libres
  adjacentes à la cible — cf. `test_summon_spawn_live`) **plutôt que de re-dériver la sélection de tuile via des
  DSL-sélecteurs** : le count-2 n'est pas exprimable par `First`=PickAtIndex sans RE de `GetTileIds`/`GetUnitToSpawn`,
  et sans gain (l'outcome est déjà validé). ON-APPEARANCE = `_summon_on_appearance_attack(summon, target,
  unitDamageProfile)` (mirror `UseNormalAttackIfAble`, profil Piercing override immédiat).
- **Arbre `scarab_hive_tree()`** (`loki.py`) = `SpawnSummon("ScarabHive", 2, Target())`. `ScarabHiveAbility.
  execute_behaviour` DÉLÈGUE à l'arbre (diag `spawned`/`attacks` reconstruit des émissions `SpawnUnit`/
  `SummonOnAppearance`, + `dsl:True`). L'impératif (spawn + boucle on-appearance câblés à la main) est **REMPLACÉ**.

**GAP flaggé (tâche #214)** : l'effet **PERSISTANT** `0x4a3` (OverrideDamageProfile pour les attaques des TOURS
SUIVANTS du summon) **n'est ni matérialisé ni lu** par le pipeline d'attaque (aucun reader offline). L'attaque
IMMÉDIATE porte déjà le bon profil (Piercing via `prof`), mais les attaques subséquentes utiliseraient l'arme
Energy → confront live requis (le summon garde-t-il l'effet ? ses coups d'après restent-ils Piercing ?) avant de
matérialiser (ne pas ajouter d'état inerte tant que le reader n'est pas câblé).

**Validation** : `test_scarab_hive_migration_live` (appel direct de la classe → `dsl:True` + 2 spawns owner-du-caster
adjacents + on-appearance ampute la cible, `sum(attacks)==PV perdus`) ; `test_summon_trigger_live` (wiring
`ActiveAbilityMessage(1007)` → arbre) + `test_summon_spawn_live` (Operation spawn) re-PASS.

**Restant loki.py impératif** (post slice-10) : ScarabSummon (auto-dédoublement — `CopyOwner` + `PickRandomly` +
cap-duplication non porté), Stikkbomb (**BLOQUÉ** : RE team-filter `AdjacentUnits(target,1,3)` — mur gshared, live
confront requis, tâche #213), Fragstorm (splash + `PickRandomly` RNG gap) ; + tranche transverse DÉPLACEMENT
(`PushUnit`/`KillDeadUnits`/`MoveUnit`).


## Slice-11 (#149, 2026-07-17) — 10e behaviour DSL : ScarabSummon (nœud unique `Spawn` clone-du-parent + on-appearance)

**RE — `ScarabSummonAbility.ExecuteBehaviour @181205290`** (id 1047, necroSmnSwarm — auto-DÉDOUBLEMENT, DÉCOMPILE
gqfc5mff6c). Un noeud `Spawn` **UNIQUE** en plain `Execute` (PAS `ExecuteAtomic`), **DISTINCT** du nœud ScarabHive :

```
Execute( Spawn(self@0x160,
               PickRandomly(CanAddUnit(AdjacentTiles(self@0x160)), 1, ..., 0x7fffffff),   // 1 tuile libre adjacente à SOI
               unitId=necroSmnSwarm=GetStringConstant(config,0),
               SpawnUnitOptions.CopyOwner(caster)                    // clone owner+stats du PARENT (PAS WithStatsFromConfig)
                 .onAppearance = PerformAIAttack(1)) )               // +0x18 — le double attaque immédiatement (PAS de +0x10 effet)
```

- Contrairement à ScarabHive, **PAS de sous-behaviour `+0x10` AddEffect** (ScarabSummon n'a pas l'effet persistant
  `0x4a3`) : un seul sous-behaviour embarqué, l'on-appearance `PerformAIAttack(1)`. Le count-1, le placement et
  `CopyOwner @180fd5ba0` (clone owner+stats du parent) vivent **DANS `SpawnUnitBehaviour.Execute @180fd3d80`**, HORS
  des DSL-sélecteurs (même carve-out que slice-10).

**Port** :
- **Feuille `SpawnReplica`** (`runner/abilities/behaviours.py`) = mirror du nœud `Spawn` natif (CopyOwner +
  on-appearance embarqués). Elle **délègue le SPAWN à l'Operation VALIDÉE** `SpawnUnitOperation.execute_self_replica`
  (`CopyOwner` = clone owner+stats du parent, count-1, tuiles libres adjacentes au caster — cf. `test_summon_spawn_live`)
  puis l'ON-APPEARANCE `PerformAIAttack(1)` = chaque double attaque l'**ennemi le plus proche** (`_nearest_enemy` +
  `AttackDamageOperation.execute`, approx du choix AI natif). Roll gated sur `state.rng` (no-op gracieux si non calé,
  mirror de l'impératif). Émet `SpawnUnit`/`ReplicaOnAppearance`.
- **Arbre `scarab_summon_tree()`** (`loki.py`) = `SpawnReplica("ScarabSummon", 1)`. `ScarabSummonAbility.
  execute_behaviour` DÉLÈGUE à l'arbre (diag `spawned`/`attacks` reconstruit des émissions `SpawnUnit`/
  `ReplicaOnAppearance`, + `dsl:True`, `replica:True` conservé). L'impératif (spawn + boucle on-appearance câblés à la
  main) est **REMPLACÉ** ; `SUMMON_ABILITY`/`COUNT` retirés de la classe (l'arbre les porte), import module-level
  `SpawnUnitOperation` retiré de `loki.py` (plus de runtime use là).

**GAP (inchangé)** : le cap de duplication (`UnitDuplicationLimitSelector`/`LimitUnitDuplications`) n'est pas porté →
récurrence non bornée offline.

**Validation** : `test_scarab_summon_migration_live` (NEW : swarm matérialisé via ScarabHive, puis `ScarabSummonAbility.
execute_behaviour` sur le swarm → `dsl:True`+`replica:True`, 1 clone `necroSmnSwarm` owner-du-parent adjacent au
swarm-parent, on-appearance frappe un ennemi, `delta HP == total` après restauration PV pour éviter l'overkill) ;
`test_scarab_hive_migration_live` (`SpawnSummon` intact) + `test_summon_spawn_live` (Operation) + `test_summon_trigger_live`
(wiring) re-PASS.

**Restant loki.py impératif** (post slice-11) : Stikkbomb (**BLOQUÉ** : RE team-filter `AdjacentUnits(target,1,3)` — mur
gshared, live confront requis, tâche #213), Fragstorm (splash + `PickRandomly` RNG gap) ; + tranche transverse
DÉPLACEMENT (`PushUnit`/`KillDeadUnits`/`MoveUnit`).


## Slice-12 (#149, 2026-07-17) — 11e behaviour DSL : Stikkbomb (splash MULTI FRIENDLY-FIRE) + fix fidélité #213

**RE — `StikkbombAbility.ExecuteBehaviour @18120c180`** (id 1051, Ork Boy — `orksNpc2OrkBoy` NPC / `orksOrkBoys`
summon, DÉCOMPILE gqfc5mff6c). `Execute(AtomicGroup(op_Addition(main, splash)))` (plain `Execute`, PAS `ExecuteAtomic`
— contraste ScythingTalons) :

```
main   = AttackWithAttackDamage(caster, target,                 RandomAmount(var0xc,var0xd), Blast, nrOfHits=0x2f=2)
splash = AttackWithAttackDamage(caster, AdjacentUnits(target,1,3), RandomAmount(MÊME),        Blast, nrOfHits_2=0x32=1)
```

**#213 RÉSOLU (décompile-conclusif — construction, PAS Execute-hooking : même leçon que #200).** Le splash passe
`AdjacentUnits(target,1,3)` **BRUT**, SANS wrapper de filtre d'équipe → **FRIENDLY-FIRE** (toutes les unités adjacentes
à la cible, alliés du caster INCLUS). Preuve par comparaison **3-way** des sélecteurs splash + décompile des primitives :

| Ability | sélecteur splash (décompile) | filtre équipe | i2 |
|---|---|---|---|
| **Stikkbomb** | `AdjacentUnits(target,1,3)` **brut** | **AUCUN → friendly-fire** | « **units** in hexes adjacent » |
| PlasmaGrenade | `Enemies(caster, AdjacentUnits(target,1,3))` | enemies-only (`UnitsByTeamSelector`) | « **enemy units** in adjacent hexes » |
| Fragstorm | `AdjacentTiles(target) − Tiles(Friends(caster,…))`, PickRandomly | exclut amis du caster | « excluding hexes with **friendly units** » |
| ScythingTalons | `Enemies(caster, AdjacentUnits(cTile)∩AdjacentUnits(tTile))` | enemies-only | « any **enemy units** adjacent » |

`AdjacentUnits @180de8320` = `Units(AdjacentTiles(target),1,3) − target` ; `Units @180e013e0` = `UnitsOnTilesSelector`
(le `1`/`3` = flags du ctor, **PAS** un masque d'équipe) ; `Enemies @180deedd0` = `UnitsByTeamSelector` (le filtre
d'équipe). Le différentiel (Plasma wrappe, Fragstorm soustrait, Stikkbomb brut) PROUVE que la couche d'attaque ne
re-filtre pas les amis → Stikkbomb friendly-fire. **Corroboration i2** : Stikkbomb dit « units » là où les 3 autres
disent « enemy units »/« friendly units ». L'ancien port (`_adjacent_enemies_of` = enemies-only) était donc **ERRONÉ**.

**Port** :
- **Sélecteur `AdjacentUnits`** (`entities/selectors.py`) = mirror `DSLFactory.AdjacentUnits` = `AdjacentEnemies` **SANS
  le filtre team** (`_within(units, targetTile, radius)`, aucun filtre d'équipe → inclut alliés + caster).
- **Arbre `stikkbomb_tree()`** (`loki.py`) = `AtomicGroup(op_add(main, splash))` : main `AttackWithAbilityDamage(Target())`
  + splash `AttackWithAbilityDamage(Alive(AdjacentUnits(TargetTile())), multi=True, hits_key="nrOfHits_2")`. Plage
  RandomAmount PARTAGÉE main/splash, profil Blast, ranged. `StikkbombAbility.execute_behaviour` DÉLÈGUE à l'arbre (diag
  `main_attack`/`splash` reconstruit des émissions `AttackWithAbilityDamage`, + `dsl:True`) — l'impératif
  (`_splash_ability_behaviour`+`_adjacent_enemies_of` enemies-only) est **REMPLACÉ ET CORRIGÉ** en friendly-fire.
  `_adjacent_enemies_of`/`_splash_ability_behaviour` restent partagés par Fragstorm (non migré).

**Validation** : `test_stikkbomb_migration_friendly_fire` (NEW : caster PROXY buildable — le carrier Ork Boy réel étant
NPC/summon non-buildable, et la friendly-fire étant une propriété du SÉLECTEUR de l'ability, pas du kit du caster —
DRIVE un allié-du-caster + un ennemi adjacents à la cible → le splash touche LES DEUX = exactement les unités à dist
hex 1 (AUCUN filtre team), l'allié INCLUS + amputé ; `dsl:True`, main 2 coups, splash 1 coup). `test_plasma_grenade_
splash_live` (Plasma enemies-only intact) + `test_scything_talons_migration_live` (intact) re-PASS.

**Restant loki.py impératif** (post slice-12) : Fragstorm (splash `AdjacentTiles − Tiles(Friends)` + `PickRandomly`-4 —
gap d'ordre/coût RNG du pick) ; + tranche transverse DÉPLACEMENT (`PushUnit`/`KillDeadUnits`/`MoveUnit`).
