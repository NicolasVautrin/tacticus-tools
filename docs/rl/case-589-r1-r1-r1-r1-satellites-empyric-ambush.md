# case-589-r1-r1-r1-r1 — les deux satellites d'`EmpyricAmbush` : **1555 porté**, **1580 mort**

`#589-r1-r1-r1-r1`. `case-589-r1-r1-r1` avait porté la POSE de l'actif **1232** et inventorié ces deux
satellites sans les porter. Verdicts **différents**, et c'est le point du dossier.

## 1. La question binaire, et sa réponse mesurée

> « Quand `eldarLhykhis` ACHÈVE un ennemi d'une attaque NORMALE au CONTACT, le natif re-arme-t-il son
> actif 1232 — et le port rend-il le MÊME verdict, à partir du même état et du même flux PRNG ? »

**Oui, sur 2 boards, et les deux gates du natif discriminent des deux côtés.** L'observable est
`usable`/`cooldown` de l'actif du TUEUR (`decisionView.units[].abilities` natif ;
`ActiveAbilitiesComponent` port) — exactement les deux champs qu'écrit
`IdunBattle.Operations.ResetActiveAbilityOperation$$Execute`.

| bras | board / seed | natif | port | `NOPORT` mord |
|---|---|---|---|---|
| `MELEE` (kill au contact) | `MC1_67` / 777 | `usable: True` | `True` | oui (`False`) |
| `MELEE` | `C1_74` / 31337 | `usable: True` | `True` | oui (`False`) |
| `RANGED` (kill à distance 2) | `MC1_67` / 777 | `usable: **False**` | `False` | s.o. |
| `RANGED` | `C1_74` / 31337 | `usable: **False**` | `False` | s.o. |
| `PAR-ABILITY` (kill par le cast de 1232) | `MC1_67` / 777 | `usable: **False**` | prédicat `matches = False` | s.o. |

`NOPORT` = l'entrée `"EmpyricAmbush"` retirée d'`ACTIVE_ABILITY_TRIGGERS` (la vue d'AVANT ce port).
Sans elle, « ça concorde » ne vaudrait rien. Les bras `RANGED` et `PAR-ABILITY` sont les seuls qui
exercent respectivement `IsMeleeAttack` et `IsNormalAttack` : sans eux, un port qui re-armerait sur
TOUT kill concorderait quand même sur le bras positif.

## 2. `1555 EmpyricAmbush_Reset` — l'arbre natif

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.EmpyricAmbush_ResetAbility$$CreateTrigger` :

    On(0x36 = UnitDefeated, 1)
  & get_OwnerIsActor                                         # AreEqual(Owner@+0x30, Actor@+0x40)
  & AreEnemies(Owner@DSLSelectors+0x30, Target@DSLSelectors+0x60, 0 = ByCurrentTeam)
  & IsNormalAttack(<DSLSelectors+0x90>)
  & IsMeleeAttack(<DSLSelectors+0x90>)

`<DSLSelectors+0x90>` = **`TriggeringAbility`** (`AbilityEntities+0x98`), le slot de
`$$TriggeringAbilityIs`/`$$TriggeringEffectIs`/`$$TriggeringAbilityIsNone` (case-292 §1.1) — **pas**
`<+0x88>` (`CurrentAbility`), qui est le défaut des surcharges à UN argument. Les deux nœuds lisent
donc l'ability du **coup létal**.

**Le behaviour est DÉDUPLIQUÉ**, et c'est ce qui a failli le faire manquer :
`EmpyricAmbush_ResetAbility$$CreateBehaviour` **n'existe pas** dans `functions.tsv` — son corps y est
attribué à `...TacticalPrecision_ResetAbility$$CreateBehaviour` (corps identique, aucun littéral
distinctif). Retrouvé par la **table de pointeurs de méthodes** des deux classes (groupes de 3 :
`.ctor` partagé, `CreateTrigger`, `CreateBehaviour`). `BaseTriggeredAbility$$CreateBehaviour` n'est
qu'un forward vers le slot de vtable `+0x2f8` : une classe SANS override récurserait à l'infini,
donc l'override existe forcément. C'est le faux négatif que le `CLAUDE.md` décrit textuellement.

    CreateBehaviour = ResetActiveAbility( Owner@DSLSelectors+0x30, allowUseless: 1 )

Le littéral `1` (là où `InspiredToGreatnessAbility$$ExecuteBehaviour` passe `0`) fait sauter le gate
de tour de `BattleQuery$$EntityCanHaveActiveAbilityReset` — nécessaire ici, Lhykhis vient d'agir.

**REGISTRE** : `StaticBattleRules.ActiveAbility$$.cctor` → dict `statics+0x30`,
**`0x4d0 (1232) -> ToList(0x613 = 1555)`** (un seul élément). Même chemin que `Hailstrike`
(1214 → 1507) : posséder l'ACTIVE fait porter la triggered dès l'init, sans cast préalable. Le même
cctor de `StaticBattleRules.TriggeredAbility` ajoute `dict[0x613] = 0x4d0` à
`GetActiveAbilityUsedForConfig` — sans conséquence, le behaviour ne lit aucune variable.

## 3. `IsMeleeAttack` — quatre branches, et le port les mirroir toutes

`DSLTriggers$$IsMeleeAttack(this, sel)` alloue un `IsMeleeAttackAbilityTrigger(state, query, logger,
sel, 0, 0, 0)` — **même `.ctor` que son frère `IsRangedAttackAbilityTrigger`** (corps dédupliqué) ;
les deux classes ne diffèrent QUE par le slot d'`IBattleQuery` invoqué en fin de `ShouldTrigger`
(2 = melee / 3 = ranged). Le corps de `IdunBattle.Core.Services.BattleQuery$$IsMeleeAttack` :

    if (!ability.HasValue)                        return false
    switch (GetAbilityAttackRangeType(ability)) :          # AttackRangeType (enums.tsv)
        0 None   -> false
        1 Melee  -> true
        2 Ranged -> false
        3 Normal -> !HasFlag(caster, 0x15 = ForceRangedAttack) && AreEntitiesAdjacent(casterPos, target)
        _        -> throw NotImplementedException

`AttackRangeType` = `0=None, 1=Melee, 2=Ranged, 3=Normal` et `UnitFlag 21 = ForceRangedAttack`, tous
deux lus dans `enums.tsv` — jamais devinés.

## 4. Le CANAL du `killTrigger` : `death_source`, pas `trigger_ability_type`

Le natif compare `AbilityEntities+0x98`, que `KillUnitOperation$$Execute` recopie depuis
`KillUnitOptions+0x04` — le `killTrigger` que `RecordKillOperation$$Execute` passe à
`MatchState$$AddDeath` (coalesce des deux `Nullable<AbilityOrEffect>` du `KillUnitContext`, lu au
décompile).

Le port a **deux** canaux candidats, et **un seul est renseigné sur une attaque normale** :

* `state.trigger_ability_type` (#301) — alimenté par `_add_death` depuis `state.triggering_ability`,
  donc **VIDE** dès que la mort ne vient pas du behaviour d'une triggered. Sur une attaque normale il
  vaut `None`, et le gate ne pourrait **jamais** passer ;
* `UnitComponent.death_source[2]` — le `Nullable<AbilityOrEffect>` de la `DamageSource`
  (`UnitComponent+0x108`), écrit par `_record_death_reason` (mirror de
  `KillUnitOperation$$RecordDeathReason`) **AVANT** `On(PreUnitDeath)`, donc lisible pendant tout le
  vecteur mort. Sa valeur est celle de `_damage_source_ability` (mirror `GetDamageSourceAbility`) :
  `0x3f5 = 1013` sur la voie normale, `1232` sur un kill d'ability (mesuré par le bras
  `PAR-ABILITY`).

C'est le **second** qui est lu : les deux natifs dérivent de la MÊME `DamageSource` du coup létal, et
c'est le seul des deux canaux portés qui soit renseigné sur le régime que cette ability vise.
`None` → gate FAUX, jamais permissif.

## 5. `1580 EmpyricAmbush_AnyMove` — **DEAD CODE**, non porté, et pourquoi

**Verdict : registered-but-dead sur le build `rnca9r7q6c`.** Trois faits mesurés, indépendants :

1. **Aucun chemin d'attribution.** Les trois registres natifs qui montent une triggered sur une unité
   (`StaticBattleRules.ActiveAbility$$GetDerivedTriggeredAbilities`,
   `...TriggeredAbility$$GetDerivedTriggeredAbilities`, `...Trait$$GetTriggeredAbility`) sont tous
   **indexés par `TriggeredAbilityType`** — or `EmpyricAmbush_AnyMove` **n'a pas de valeur d'enum** :
   `TriggeredAbilityType` compte 476 entrées, `1553` est le **seul trou** de la plage dense
   1545..1558, et le littéral `0x611` n'apparaît **nulle part** dans les cctors de
   `StaticBattleRules.ActiveAbility` / `...TriggeredAbility` (1 seule occurrence dans tout le
   binaire, dans `EnvStrategicBuff*`, un AUTRE enum). L'entrée de 1232 dans le dict des dérivées est
   un `ToList` à **un** élément — 1555, et rien d'autre.
2. **Aucun consommateur.** `0x62c` (= 1580) a **5** occurrences littérales dans tout le binaire ;
   une seule est du code de jeu : `EmpyricAmbush_AnyMoveAbility$$CreateBehaviour`, celle qui POSE
   l'effet. Aucun `StaticBattleRules.Effect$$.cctor` ne le range dans un HashSet (invisible,
   cumulatif, …), aucune lecture ailleurs.
3. **Structurellement inobservable même s'il tournait.** L'ability pose 1580 sur `On(PreUnitMove)` et
   `EmpyricAmbush_AnyMoveEffect$$CreateRemoveEffectTrigger` (`On(UnitAfterMove) & OwnerIsActor`) le
   retire : l'effet ne vit qu'entre le début et la fin d'un déplacement. Son seul lecteur est la VUE
   (`IdunBattle.View.AbilityConfigs.Loki.EmpyricAmbush_AnyMoveEffectVisuals$$ActivateEffectInternal` /
   `$$DeactivateEffectInternal`) — un marqueur de VFX.

L'arbre, relu quand même (il n'est pas porté, il est **cité**) :

    CreateTrigger   = On(0x1f = PreUnitMove, 1) & get_OwnerIsActor
    CreateBehaviour = AddEffect(0x62c = 1580, AbilityStateReference,
                                targets = Owner@DSLSelectors+0x30, turns = 0)
    (retrait)       = On(0x4 = UnitAfterMove, 1) & get_OwnerIsActor

⇒ **pas de port spéculatif** : aucun porteur ne peut l'instancier, donc aucun runner ne peut le
confronter (doctrine « porteur spawnable obligatoire »). Si un build futur rouvre le slot d'enum,
l'arbre ci-dessus est prêt à porter.

## 6. Gate de confrontabilité

`eldarLhykhis` — **HERO**, seul porteur de l'actif 1232 donc de la triggered dérivée 1555. **HORS
CATALOGUE** du seed BC (`catalog_inject --missing` la liste, `--list-pool` ne la rend pas) → injectée
par `catalog_inject.write_augmented_seed_bc` + `build --seed-bc`, exactement comme #589-r1-r1-r1.
`1580` n'a **aucun** porteur (§5).

## 7. Reproduction

    python probe_589r1r1r1r1_empyric_ambush_reset_live.py                        # bras MELEE
    python probe_589r1r1r1r1_empyric_ambush_reset_live.py --ranged                # bras IsMeleeAttack
    python probe_589r1r1r1r1_empyric_ambush_reset_live.py --par-ability --hp-target 500
    python probe_589r1r1r1r1_empyric_ambush_reset_live.py --board C1_74 --seed 31337
    python -m pytest tests/engine/runner/test_589r1r1r1r1_empyric_ambush_reset_live.py   # 5 passed

Le montage consomme l'actif par un **vrai cast** de 1232 au tour 1 (ennemis `--hp-target 900000`
pour que les 8 coups d'ability ne tuent personne), puis tue au tour 2 par l'attaque normale
(`--unit-stat "eldarLhykhis:Damage=400000"`). Le probe **REFUSE** (rc 2) si l'actif est encore
utilisable juste avant le kill : un régime non atteint n'est pas un accord.

## 8. Ce qui n'est PAS couvert

* **L'observable `usable` du bras `PAR-ABILITY` est SATURÉE côté port** : le port ne modélise pas la
  consommation de l'actif au cast offline (`ActiveAbilitiesComponent` est SEEDÉ depuis le
  `decisionView` d'avant, donc `usable=True`), et un gate `EntityCanHaveActiveAbilityReset` faux rend
  le re-armement no-op quoi qu'il arrive. `IsNormalAttack` y est donc confronté au niveau du
  **prédicat** (`matches()` sur le même état post-cast, `killTrigger = 1232` lu), pas de l'état. Le
  bras natif, lui, est une vraie mesure.
* **`get_OwnerIsActor` n'a pas de bras dédié** : aucun montage ne fait tuer par une AUTRE unité que
  Lhykhis pendant que son actif est consommé. Le nœud est porté et lu (`ev.killer_id != owner_id`),
  non exercé.
* **`AreEntitiesAdjacent` est évalué au moment du DRAIN de la mort**, pas du coup. Les deux coïncident
  tant que le tueur n'a pas bougé entre les deux — aucun chemin porté ne le fait (le drain est non
  réentrant et suit immédiatement l'application du dégât). Non exercé pour autant.
* **`GetAbilityAttackRangeType`** : le natif le lit dans la base d'abilities (`abilitiesDb[type].<slot
  0xf>`) ; l'oracle porté est le gameconfig, et les attaques normales n'ont **pas** d'entrée
  gameconfig (`Loki_NormalAttack`, `PrecisionShot_Attack` → `None`) → repli sur `AttackRangeType.Normal`,
  la seule valeur compatible avec une unité qui porte à la fois une arme de mêlée et une arme à
  distance. Le gate `IsNormalAttack` étant CONJOINT sur le même sélecteur, la valeur évaluée est
  toujours une attaque régulière.
* **La face DÉCISION du playbook** (`IdunBattle.AI.Playbook.Loki.EmpyricAmbush_ResetPlaybook`,
  `TriggeredAbilityPlaybook<EmpyricAmbush_ResetAbility>`) n'est pas touchée : ce port est la face
  COMBAT.
