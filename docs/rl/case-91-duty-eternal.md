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
`{0x88: HasFlag(entity, 6)}`, puis `RemoveEffects(entity)`. Côté port, la conséquence
observable est unique et suffisante : **la MoW ne peut plus caster** (ni `DutyEternal`, ni
`MacroPlasmaIncinerator`) pour le reste de la bataille — c'est exactement ce que dit l'i2.

## 7. Ce que le port ne couvre PAS (résidus nommés)

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
