# Cas #91 — `DutyEternal` (1158) : de quoi l'ability a-t-elle RÉELLEMENT besoin ?

**Question binaire** : une fois admis que le substrat multi-hex (R30) est porté, que manque-t-il
encore pour porter `DutyEternal` ?

**Réponse : UN MANQUE PRÉCIS, nommé et porté ici.** Le substrat R30 pose la *représentation*
(`UnitComponent.feet`, occupance par pied, géométrie, `ThreeUnitSpawnTileShapeSelector`) ; il ne
pose **aucun producteur** — rien, dans le port, ne savait *créer* une unité à N pieds. Trois
morceaux manquaient, tous lus au décompilé :

1. **le flag `SpawnUnitOptions+0x60`** — le bit qui fait basculer `SpawnUnitBehaviour$$Execute`
   de « une unité PAR tuile » à « **UNE** unité sur **toutes** les tuiles » ;
2. **le nœud DSL `ThreeTileUnitSpawnShape`** — le sélecteur porté en R30 existait comme
   *fonction* (`engine/services/spawn_tile_shape.py`), pas comme nœud d'arbre ;
3. **`RemoveMachine`** — la moitié « la MoW quitte la partie » de l'ability, qui n'a rien à voir
   avec le multi-hex.

## 1. Confrontabilité

| porteur | catégorie | chemin en bataille |
|---|---|---|
| `ultraDreadnought` (Galatian) | **MACHINE OF WAR** | présence DIRECTE dans `rl_duel build --list-pool` — `8 MoW spawnables : [... 'ultraDreadnought']` |
| `ultraSmnDreadnought` | summon (produit PAR l'ability) | arrive par le cast |

`DutyEternal` n'a **qu'un** porteur ; il est spawnable. **CONFRONTABLE.**
Leviers de mise en scène : `munitionsCost = 3` et `initialCooldownTurns = 2` (constantes de
l'ability), déjà documentés en R30 §2.

## 2. Le kit (gameconfig + i2, jamais une capture live)

```
ultraDreadnought «Galatian» [lineup] traits=[MachineOfWar] activeAbilities=[DutyEternal, MacroPlasmaIncinerator]
                            mythicAbilities=[WisdomOfTheAncients]
  [active 1158] DutyEternal {"unitId":"ultraSmnDreadnought","initialCooldownTurns":"2","munitionsCost":"3"}
    « Summons Galatian as a stationary unit in a 3 hex area on the battlefield. After using this
      ability, Galatian can no longer be used as a Machine of War for the rest of the battle. »
ultraSmnDreadnought [summons] traits=[Summon, BigTarget, Overwatch, Vehicle, Mechanical]
                              passiveAbilities=[AncientFury]  activeAbilities=[]
```

Le texte i2 porte les **deux** volets que le décompilé confirme : « stationary » (le trait `0x418`
posé à l'apparition, pas une propriété de la config du summon) et « can no longer be used as a
Machine of War » (`RemoveMachine`).

## 3. Le décompilé — `IdunBattleLogic.Entities.Abilities.Active.Loki.DutyEternalAbility$$ExecuteBehaviour`

Structure lue (mirror 1:1) :

```
opts = SpawnUnitOptions.WithStatsFromConfig(config 1158, <levelInfo de param_2>)
onAppearance = AddTrait(ActiveTarget@0x180, 0x418)                      // 1048 = Immobile
if (caster.GetComponent<TriggeredAbilityComponent>().<coll @+0x18>.Count > 0) {
    a = First(coll)
    onAppearance &= AddTriggeredAbility(ActiveTarget@0x180, a.Id, {a@0x20, a@0x28})
}
opts.<+0x18> = onAppearance          // sous-behaviour on-appearance (TriggerSpawnedUnitBehaviours)
opts.<+0x50> = UnitExtensions.GetQuestUnitId(caster)
opts.<+0x60> = 1                     // <-- LE flag multi-pieds (cf. §4)
Execute( RemoveMachine(caster@0x160) & Spawn(caster@0x160,
                                             ThreeTileUnitSpawnShape(Target@0x178),
                                             GetStringConstant(config, 0),
                                             opts) )
```

`...DutyEternalAbility$$.ctor` :

```
TargetingOptions..ctor(&opts, 0, &<TargetingRange statics>+0x48, 1, 0x20000040000042, 0, 0, 0)
AActiveAbility..ctor(this, &opts, 2, 0)
```

* forme **FLAGS DIRECTS** (pas un preset recopié) — le littéral EST le masque effectif ;
* `&<TargetingRange statics>+0x48` = **le même preset de portée que `SporeMineLauncherAbility$$.ctor`**
  (décompiles comparés, même classe statique, même offset) = `RANGE_WHOLE_BOARD` ;
* `forceMeleeTarget = 1` = `RangedBool.False` ;
* `rules = 0x20000040000042` = `TargetMatchesDynamicRule` (bit 1) | `TargetIsTile` (bit 6)
  | `AllowNullCasterTile` (bit 30) | `CasterIsMachine` (bit 53) ;
* 3ᵉ argument d'`AActiveAbility..ctor` = **2 = `AbilityAttackType.Others`**.

`...DutyEternalAbility$$GetDynamicInvalidTargetReason` : construit
`ThreeTileUnitSpawnShape(Target@0x178)`, l'évalue sur un `AbilityEntities` fabriqué, et rend
**2 (invalide)** si le sélecteur rend `null` **ou** une liste vide, **0** sinon. C'est exactement
le pendant du bit `TargetMatchesDynamicRule` : *la tuile visée est légale ssi l'aire triangulaire
de 3 tuiles existe autour d'elle*.

## 4. Le manque n°1 — `SpawnUnitOptions+0x60`, le producteur d'empreinte

`IdunBattle.Entities.Behaviours.SpawnUnitBehaviour$$Execute` a **deux** branches, et c'est le
champ `+0x60` des options qui tranche :

| `options+0x60` | branche | effet |
|---|---|---|
| `0` (défaut) | boucle `foreach tile in tiles` : chaque tuile est convertie en liste d'**UN** élément (`ToList` du singleton) puis passée à `AddUnit(unitConfig, [tile], player, 2, options)` | **N unités mono-pied** |
| `≠ 0` | `GetTileIds(tiles)` — **toutes** les tuiles dans UNE liste — puis **UN SEUL** `AddUnit(unitConfig, allTiles, player, 2, options)` | **UNE unité à N pieds** |

`IdunBattle.Entities.Behaviours.SpawnUnitBehaviour$$GetTileIds` est littéralement
« itère la collection de tuiles et rend la liste de leurs ids » — la liste que
`IdunBattle.Operations.AddUnitOperation$$Execute` consomme ensuite par `ClearFeet` +
un `AddFoot` **par tuile**, dans l'ordre (R30 §1).

**C'est le seul endroit du binaire où une unité multi-pied est produite**, et c'est ce que le
port n'avait pas : `Spawn` (feuille DSL) spawnait toujours une unité par tuile, et
`_spawn_config_grot` posait un `PositionComponent` unique. Les deux sont désormais paramétrés
(`Spawn(..., spawn_as_single_unit=True)` / `_spawn_config_grot(..., tiles=[...])` →
`set_unit_feet`).

## 5. Le manque n°2 — le nœud DSL `ThreeTileUnitSpawnShape`

R30 a porté `ThreeUnitSpawnTileShapeSelector` comme **fonctions pures**
(`get_area` / `correct_area` / `correct_relationship_in_area`). Le natif, lui, est un
**sélecteur** placé dans l'arbre (`DSLFactory$$ThreeTileUnitSpawnShape(inner)` →
`ThreeUnitSpawnTileShapeSelector$$Select(ctx)` = `inner.Select(ctx)` puis `GetArea(tile)`).
Le port ajoute donc le nœud `ThreeTileUnitSpawnShape` (`engine/entities/selectors.py`), qui
enveloppe un sélecteur de TUILE et rend l'empreinte — l'ability ne recâble rien à la main.

## 6. Le manque n°3 — `RemoveMachine`

`IdunBattleLogic.Entities.DSLFactory$$RemoveMachine(factory, sel)` construit un
`IdunBattle.Entities.Behaviours.RemoveMachineBehaviour`, dont l'`Execute` résout son sélecteur
(`+0x50` = `caster@0x160`) et appelle l'opération `RemoveMachine(entity, removeEffects=1, …)`.

`IdunBattle.Operations.RemoveMachineOperation$$Execute` (gate `EntityExtensions$$IsMachine`) :
`RemoveMachineFromPlatform`, remise à zéro d'un champ de la plateforme, **event `0x2e`** portant
`{0x88: HasFlag(entity, 6)}`, puis `RemoveEffects(entity)`. **Elle ne détruit pas l'entité et ne
touche NI `ActiveAbilityComponent` NI les PV** : elle DÉTACHE la machine de sa plateforme.

### Ce que le décompilé ne dit pas — et qu'il a fallu MESURER

Le décompilé donne la mutation ; il ne dit pas ce que le détachement rend **observable**. Deux
hypothèses plausibles s'affrontaient, et l'une d'elles a été **réfutée** (`probe_91_duty_eternal.py`,
avec runner de CONTRÔLE) :

| canal | après `RemoveMachine` | verdict |
|---|---|---|
| `decisionView.mows` | la MoW est **toujours là**, ses DEUX abilities à `usable: true, hasAmmo: true, cooldown: null` | **ne dit rien du retrait** — cohérent : le projecteur lit `ActiveAbilityComponent`, que l'opération ne touche pas |
| `observeBattle.units` | la machine est absente | non concluant (une MoW hors plateau n'y est jamais) |
| `applyAction` → `mutated` | `False` **des deux côtés** | **piège** : 1159 est un poseur d'effets de tuile, il ne change ni position ni PV *même quand il passe* |
| `applyAction` → **`actionConsumed`** | **`False`** après retrait, **`True`** sur le runner de CONTRÔLE (même fenêtre cooldown/tour ouverte, 1158 jamais casté) | **LE discriminant** |

Conséquence directe sur le port : **éteindre `CanStillBeUsed` / poser `alive = False` sur la MoW
aurait fabriqué un état natif FAUX** (c'était la première version, réfutée par la mesure). Le port
pose donc le seul état que l'opération pose (`MachineComponent.removed` + `RemoveEffects`), et le
REFUS vit là où le natif le rend observable : en tête d'opération d'ability
(`AbilityHandler.visit_ActiveAbilityMessage`, gate `machine_removed` — même rang et même forme que
le gate acteur-mort #70 : aucune behaviour, aucun flag de tour, aucun vecteur d'événement).

### `abilityReason` est AVEUGLE à la règle dynamique ici

Même méthode, même surprise, sur la face DÉCISION : `abilityReason({casterId: <MoW>,
abilityType: 1158, targetId: <tile id>})` rend **`reasons: []` pour les 63 tuiles du board**,
y compris celles que le natif refuse. Ce n'est donc **pas** un oracle utilisable pour cette règle.

L'oracle est le **cast lui-même** : sur une tuile sans aire valide, `applyAction` rend
`ok: true, mutated: false, spawned: 0, actionConsumed: false` — le refus silencieux de
`ActiveAbilityOperation` (case-111) ; sur l'ancre choisie, `mutated: true, spawned: 3`.
Le port refuse **exactement** les tuiles à aire vide (23 sur 63 dans la mesure MC1_67), avec le
code littéral `2` = `TargetingRule.TargetMatchesDynamicRule`.

`test_ability_reason_is_blind_to_the_dynamic_rule_here` verrouille ce constat : **s'il échoue un
jour, c'est une bonne nouvelle** (le canal s'est mis à rendre la raison, et la confrontation
tuile-par-tuile — plus fine que le cast — redevient possible).

## 7. Validation

**20 tests live** dans `scripts/python/tests/engine/runner/test_multihex_dutyeternal_live.py`
(les 7 de R30 — inchangés et toujours verts — plus 13 neufs), **18 tests offline** dans
`test_multihex_substrate.py`, et le probe de mesure `scripts/python/probe_91_duty_eternal.py`.

**Vues rouges confirmées** — chaque mutation fait tomber exactement le(s) test(s) censé(s) la voir :

| mutation | tests qui tombent | chiffre |
|---|---|---|
| `spawn_as_single_unit=False` | `..._spawns_one_unit_on_the_whole_footprint`, `..._matches_native_footprint` | port `[(1,2)]` vs natif `[(1,2), (2,1), (2,2)]` |
| `AddTrait(Stationary)` → un autre trait | `..._grants_the_stationary_trait` | traits du summon sans `Stationary` |
| règle dynamique → `return 0` | `..._refuses_exactly_when_no_area_exists`, `..._reason_is_blind...` | `(0,0)` sans aire : port rend 0 au lieu de 2 |
| `RemoveMachine` retiré de l'arbre | `..._removes_the_machine`, `..._gate_refuses_any_cast...` | `machine_removed` absent |
| `CanAddUnit` ignore les pieds | `..._every_foot_blocks_the_dsl_can_add_unit_selector` | pied `(2,1)` (tuile 31) vu LIBRE |
| `ThreeTileUnitSpawnShape` ignore les pieds | `..._footprint_blocks_a_second_three_tile_shape` | aire `[(2,1),(2,2),(3,2)]` acceptée sur l'empreinte |

**Généralisation craftée** (ce que l'empreinte change EN AVAL du cast, hors de DutyEternal
elle-même) : une fois Galatian posé, ni le nœud DSL `CanAddUnit` — consommé par TOUS les spawns
(GetEmRuntz, SupremeCommander, ScarabSummon…) — ni le producteur `ThreeTileUnitSpawnShape` ne
doivent accepter une seule des trois tuiles. Les deux mutations ci-dessus montrent que c'est bien
`feet` (et non `pos`) qui les en empêche.

**Non-régression re-jouée** : `test_summon_spawn_live` + `test_mow_caster_load_live` +
`test_mow_effect_posers_live` (16), `test_summon_ability_ports_live` +
`test_mow_targeting_predicate_live` (9), `test_multihex_substrate` (18). Tous verts.

## 8. Ce que le port ne couvre PAS (résidus nommés)

* **`AddTriggeredAbility` conditionnel** — le bloc est porté (structure lue), mais sa branche
  n'est **atteignable que si le caster porte au moins une triggered ability**. Le seul candidat
  du kit est la **mythic** `WisdomOfTheAncients` (« Friendly Mythic characters take -20% Damage
  if they are adjacent to Galatian… »), qu'un `ultraDreadnought` de rang courant n'a pas.
  Le port lit donc la liste des triggered du caster et ne transfère rien quand elle est vide —
  **même dégradation que le natif**, mais la branche « non vide » reste **non confrontée live**.
* **`options+0x50 = GetQuestUnitId(caster)`** — champ de quête, sans consommateur de combat porté.
* **`HasPowerup` dans `CorrectArea`** — résidu R30 §6.1, inchangé (le port est plus permissif sur
  un plateau à power-ups).
* **L'event `0x2e` de `RemoveMachineOperation`** et son tag `0x88` ne sont pas matérialisés : le
  port n'a pas de bus d'events de plateforme MoW.
* **Le CONTRÔLE POSITIF du refus de cast** (MoW *non* retirée → `actionConsumed = True`) vit dans
  le **probe**, pas dans le test : le rejouer dans le test coûterait un second runner par passe.
  C'est lui qui établit la causalité ; le test ne garde que le verdict.
* **`AetherStride` (1208, `thousDaemonPrince`)** — l'autre consommateur de
  `ThreeTileUnitSpawnShape` — profite désormais de tout le substrat *et* du producteur, mais son
  porteur est hors seed BC (voie `catalog_inject`) : **non exercé**, donc non porté ici.

## 9. Ce que ce cas ferme, au-delà de l'ability

* **R30 §6.3** (`HasTrait(0x418)` non reproduit dans `movement_query.get_movable_positions_for`) :
  **FERMÉ**. Le gate n'était pas porté faute de porteur du trait dans l'état du port — or
  `AddTrait(ActiveTarget, 0x418)` en crée un. Le gate est désormais en tête de fonction, mirror du
  natif, lisant les traits à la source unique (`StatsComponent.ctx.traits`).
* **L'occupance par pied dans les nœuds DSL** : `CanAddUnit` raisonnait sur `pos`, pas sur
  l'empreinte. Inerte tant qu'aucune unité multi-hex n'existait dans l'état du port — donc un
  faux-négatif qui se serait réveillé silencieusement au premier `DutyEternal`.
* **`_unit_dict` expose `feet`** (mirror `EntityExtensions$$GetTiles`, toujours une liste, jamais
  `None`) : c'est la porte d'entrée des sélecteurs DSL sur l'empreinte, qui n'existait pas.
