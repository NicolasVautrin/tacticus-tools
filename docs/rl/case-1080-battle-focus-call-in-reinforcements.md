# case-1080 — `BattleFocus` et `CallInReinforcements` : deux `GAP-MENTION` dont le porteur `S?` était un JUMEAU NPC

Deux passives de `passive-ability-coverage.md`, toutes deux `S?=1 N=1`. L'audit rendait `S?` parce
que son graphe de summon ne balaie que les abilities **des unités** ; la moitié du travail était de
trancher le porteur. Les deux tombent dans la ventilation de `case-1052`, mais **par deux cas
différents**.

## 1. Les porteurs, ventilés

| passif | ordinal(s) | summon | npc jumeau (`visualId`) | invocateur du summon | chemin retenu |
|---|---|---|---|---|---|
| `BattleFocus` | ability `TriggeredAbilityType` **1172** + effet `EffectType` **1199** | `eldarSmnGuardian` | `eldarNpc1Guardian` | **AUCUN** — balayage EXHAUSTIF du gameconfig (toute chaîne de l'arbre, pas seulement `constants.unitId*`) : **0 occurrence** hors de sa propre définition | **npc**, `--explicit-stats eldarNpc1Guardian:45` |
| `CallInReinforcements` | `TriggeredAbilityType` **1029** | `astraSmnVoxcaster` | `astraNpc3Voxcaster` | `EnvFactionSummons:Armageddon{Astra,BA,BT,SW}` (`constants.unitId`) — quatre abilities d'**ENVIRONNEMENT**, portées par aucune unité, et **elles-mêmes référencées nulle part** dans le gameconfig courant (`liveEvents` compris) | **npc**, `--explicit-stats astraNpc3Voxcaster:45` |

Les deux npc portent leur table `units.npc[].stats[]` (45 paliers) ⇒ **confrontables** par le chemin
de stats explicite (case-92 §5bis recours 4), avec LEURS stats, LEURS traits, LEURS armes.

⚠ **Le palier 45 n'est pas ici une condition d'observabilité** (aucun plancher de perçage en jeu,
contrairement à `AllIsDust`), mais il rend le Vox-caster **survivable** : au palier 3 il a 28 PV,
meurt au premier coup et ne clôt jamais son activation — le vecteur `On(0x29)` ne part pas.

## 2. Ce qui existait DÉJÀ au registre — mesuré PAR EXÉCUTION

Les sept registres interrogés dans un process frais, avant tout port :
`TRAIT_TRIGGERS`, `ABILITY_TRIGGERS`, `ACTIVE_ABILITY_TRIGGERS`, `PASSIVE_HELPER_ABILITY_TRIGGERS`,
`RELIC_ABILITY_TRIGGERS`, `CUSTOM_TRIGGERED_ABILITIES`, `EFFECT_TRIGGERS`, plus `EFFECT_CLASSES`,
`ABILITY_INIT_OWNER_EFFECTS`, `ABILITY_OWNER_EFFECTS`, `ABILITY_CLASSES`,
`CUSTOM_NORMAL_ATTACK_BY_PASSIVE` et `TRIGGERED_ABILITY_BEHAVIOURS`.

**Résultat : RIEN. Zéro entrée, dans zéro registre, pour les deux noms.** Le `GAP-MENTION` était
exact — les deux noms n'existaient que comme membres du mirror `TriggeredAbilityType`.

## 3. RE — `CallInReinforcements` (1029)

Namespace `...Abilities.**Active**.Loki`, mais attribution par `passiveAbilities` et ordinal
`TriggeredAbilityType` : **le namespace ne tranche pas la voie**, le NOM le fait.

```
$$CreateTrigger  = On(0x29 = UnitFinishedTurnNormally, ownerNeedsToBeAlive: true) & get_OwnerIsActor

$$CreateBehaviour :
  opts      = SpawnUnitOptions.WithStatsFromConfig(config, abilityState, null, null)
  opts+0x18 = PerformAIAttack(ActiveTarget@<Sel+0x68>, allowOnlyMove: 1, null, null, null)
  util      = UtilityDefinition( UtilityBucket([ WeightedUtility(0x1b = 27 PowerUp,      null),
                                                 WeightedUtility(0x22 = 34 TileDistance, null) ]) )
  tiles     = First( SortTilesByUtilityForSummon( EdgeTiles(CanAddUnit(AllTiles@<Sel+0x18>)),
                                                  util, Owner@<Sel+0x30> ), 1, 0 )
  return Spawn(Caster@<Sel+0x48>, tiles, GetStringConstant(0) = astraSmnGuardsman, opts)
```

⚠ **JUMEAU EXACT DE `ForwardSpotter` (1143) À DEUX ÉTAGES PRÈS** — même summon, même
`WithStatsFromConfig`, même on-appearance `PerformAIAttack(ActiveTarget, allowOnlyMove = 1,
moveAmount = null)`. Ce qui diffère : la **chaîne de tuiles** (tout le BORD au lieu du voisinage
d'une cible) et la **définition d'utilité** (bucket BÂTI À LA MAIN au lieu de la surcharge scalaire
`UtilityDefinition(7 = Tile)`). Recopier le voisin de forme aurait posé le summon ailleurs, en
silence.

⚠ **`TileDistance(34)` EST ce qui porte le « nearby » de l'i2.** `EdgeTiles(CanAddUnit(AllTiles))`
rend TOUT le bord libre ; `PowerUp(27)` vaut 0 partout sans power-up. Le seul terme discriminant est
`-distance/10` à la main tile du **PARENT** — la branche `else if (c.owner != null) DistanceTo(c,
c.owner)` de `IdunBattle.AI.Utilities.TileDistanceUtility.u003CEvaluateMovementInStepsu003Ed__1$$MoveNext`,
que le port **déclarait inatteignable** (« ses six occurrences passent toutes
`UtilityDefinition(7 = Tile)` », `engine/utilities/tile.py`). Ce call-site l'exerce : elle est
portée, avec la clé `ctx["parent_pos"]` de `_spawn_leaf_ctx` — clé NEUVE et DISTINCTE de `self_pos`
(la fabriquer sous le nom du SUJET ferait mordre les gates que le natif laisse tomber en régime
spawn). C'est aussi ce qui a fait entrer `PowerUp(27)` et `TileDistance(34)` dans `UTILITY_BY_TYPE` :
sans elles, `UtilityDecider.CalculateUtility` **LÈVE**.

⚠ **`IsEdgeTile` compte la tuile ELLE-MÊME, et le pseudo-C ne le montre pas.**
`IdunBattle.Core.Services.BattleQuery$$IsEdgeTile` =
`GetSurroundingTilesCount(tile, 1, false, false, false, includeCenter) <= 5`. Ghidra laisse deux
arguments en registres non résolus et affiche `< 6` ; le décodage du prologue tranche —
`r8d = 1` (distance), `r9d = 0`, `[rsp+0x20] = 0`, `[rsp+0x28] = 0`, **`[rsp+0x30] = 1`**
(`includeCenter`), puis `cmp eax, 5 ; setle`. Donc **`voisins <= 4`**, pas `voisins < 6` : une tuile
à CINQ voisins n'est **pas** une tuile de bord. Lire `< 6` aurait élargi la sélection de tout le
liseré interne du plateau.

## 4. RE — `BattleFocus` (1172 / 1199)

Trois temps, et **aucun** n'est un `CreateTrigger` de l'ability.

**(a) POSE.** `BattleFocusAbility : AOwnerEffectTriggeredAbility` →
`CreateTrigger = OnOwnerSpecificAbilityInit(1172)` et
`CreateBehaviour = If(<slot 0x368>, AddEffect(GetEffectType() = 0x4af, AbilityState(Owner@<Sel+0x30>),
source = Owner, targets = Owner, turns = ZÉROÉES))`. `$$GetEffectType` = `return 0x4af;` (corps
trivial, LU). **CONFIRMÉ LIVE** : `decisionView` rend `u81 [eldarNpc1Guardian] : BattleFocus` dès le
déploiement, sans aucun cast.

**(b) DÉTECTION.** `BattleFocusEffect$$CreateTargetTrigger` =
```
  NOT IsMoving(Owner@<Sel+0x30>)  &  CanMove(Owner@<Sel+0x30>)
& ( On(0xb = UnitAbility, ownerNeedsToBeAlive: 1)
    & AbilityHasAttackType(CurrentAbility@<Sel+0x88>, AbilityAttackType.DirectTargetAttack = 0)
    & ( get_OwnerIsTarget | get_OwnerIsCaster ) )
```
⚠ `AbilityHasAttackType(..., 0)` **SEUL**, pas la disjonction `0 | 1` de `SwornProtector` — le
`SummonAndAttackTarget` est EXCLU. La disjonction `OwnerIsTarget | OwnerIsCaster` **est** le
« after attacking OR being attacked » de l'i2, en UN vecteur : `On(0xb)` est publié
INCONDITIONNELLEMENT par `ActiveAbilityOperation$$ExecuteInternal`, donc il couvre l'attaque normale
comme un cast (#928).

**(c) DÉPLACEMENT.** `$$CreateTargetTriggerBehaviour` =
`TriggerAbilityDelayed(Owner@<Sel+0x30>, 0x494 = 1172, UnitSelectionType 3)` ; puis
`BattleFocusAbility$$CreateBehaviour` bifurque sur `triggerType == 0x20 = Custom` vers
`$$CreateMoveBehaviour` :
```
  base  = CanAddUnit( AdjacentTiles(Owner@<Sel+0x30>) )
  tiles = TilesWithoutPowerUps(base).Otherwise(base)
  avoid = NonSteppableOrObjectUnits( Enemies(Owner, _allAliveUnits@<Sel+0x20>, 3), 3 )
  tiles = SafestTiles(tiles, Owner@<Sel+0x30>, avoid)
  tiles = PickRandomly(tiles, 1, 0, 0x7fffffff, 0)
  return IfAlive( Owner, MoveUnit(Owner, tiles, <options ZÉROÉES>), null )
```
**L'EFFET NE DÉPLACE RIEN** : il ENFILE, et c'est le SECOND passage qui bouge le porteur. Câbler le
`MoveUnit` sur `On(0xb)` donnerait le bon observable et le **mauvais ORDRE** (déplacement au milieu
de la résolution de l'attaque).

⚠ **`SafestTileSelector$$Select` a un critère LEXICOGRAPHIQUE à deux étages** : maximiser d'abord la
distance au plus proche des `unitsToAvoid`, puis, à égalité, **minimiser `cur.Count`** — un compteur
alimenté par `AddRange(eTiles)`, donc en **TUILES**, pas en unités (une unité multi-hex y pèse autant
de fois qu'elle a de pieds). `bestMin` part de **`0`**, pas de `int.MinValue` : une tuile dont un
ennemi occupe le voisinage immédiat (distance 0) ne peut jamais gagner. Le retour est un **ENSEMBLE**
d'ex æquo, que `PickRandomly(..., 1)` réduit.

⚠ **`TilesWithoutPowerUps` : la garde est `unit == null` OU `!IsPowerUp`, dans cet ordre** — la
branche `null` est prise AVANT tout appel à `IsPowerUp`, donc le nœud n'exige PAS que la tuile soit
libre. C'est ce qui le rend composable avec le `.Otherwise(base)`, où `base` est déjà un
`CanAddUnit(...)` : sans ce point, l'`Otherwise` serait toujours inerte.
`IdunBattle.Entities.UnitExtensions$$IsPowerUp` = « l'unité porte au moins une des **22**
`TriggeredAbilityType` du `HashSet` que le `.cctor` de
`idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.TriggeredAbility` écrit dans
`<statics+0x70>` » — les 22 sont LUES une à une dans ce `.cctor`, jamais dérivées du préfixe du nom.

⚠ **Le dict d'unité du DSL NE PORTE PAS de clé `triggered_abilities`.** La première écriture de
`unit_is_power_up` lisait `unit["triggered_abilities"]` : le prédicat était **INERTE en silence**, et
un filtre inerte est indiscernable d'un filtre correct sur un plateau sans power-up. C'est la GARDE
offline (mutant M5) qui l'a montré, pas le live. Il passe désormais par `ctx.has_triggered_ability`,
foyer unique du kit déclenché d'une entité.

## 5. Confrontation LIVE — `probe_1080_battle_focus_call_in_reinforcements.py`

`CallInReinforcements`, `astraNpc3Voxcaster:45`, `MC1_67`, mutation = l'entrée quitte
`ABILITY_TRIGGERS`. **La tuile de SPAWN se lit dans les ÉVÉNEMENTS**, pas dans le `decisionView`
d'après : le on-appearance fait jouer un TOUR COMPLET au summon, qui s'éloigne (mesuré : 3 pas).

| position du Vox | tuile de spawn LIVE | port AVEC | port SANS |
|---|---|---|---|
| (1,0) — spawn points | tuile 12 = **(0,0)** | **(0,0)** | aucun spawn |
| (5,5) — `--place` | tuile 70 = **(6,4)** | **(6,4)** | aucun spawn |

`BattleFocus`, `eldarNpc1Guardian:45` placé en (3,4), mutation = l'arbre de déplacement n'est pas
joué :

| géométrie | position après, LIVE | port AVEC | port SANS |
|---|---|---|---|
| ennemis en (3,6)/(4,6) | **(3,3)** — il fuit vers le haut | **(3,3)** | (3,4) |
| ennemis en (3,2)/(4,2) | **(3,5)** — il fuit vers le bas | **(3,5)** | (3,4) |

**Témoin NON dégénéré dans les 4 bras** : le régime `sans` rend un résultat DIFFÉRENT à chaque fois,
et la réponse `avec` n'est pas constante d'une géométrie à l'autre.

## 6. Garde offline et matrice de mutants

`tests/engine/test_1080_battle_focus_call_in_reinforcements_offline.py` — **18 tests, aucun runner**.
Sept mutations, **7 ROUGES** :

| mutant | effet | verdict |
|---|---|---|
| M1 | seuil d'`EdgeTiles` `<= 5` → `<= 6` | ROUGE |
| M2 | branche de repli PARENT de `TileDistanceUtility` retirée | ROUGE |
| M3 | étage 1 de `SafestTiles` inversé | ROUGE |
| M4 | étage 2 de `SafestTiles` supprimé | ROUGE |
| M5 | garde de `TilesWithoutPowerUps` inversée | ROUGE |
| M6 | `EFFECT_TRIGGERS` sans `BattleFocus` | ROUGE |
| M7 | le bucket de `CallInReinforcements` perd `TileDistance` | ROUGE |

⚠ **M4 est resté VERT à la première passe**, et la cause est instructive : dans l'ordre de source
`[bonne, mauvaise]`, la bonne candidate entre la PREMIÈRE et l'étage 2 n'a rien à trancher. Le test
joue désormais **les DEUX ordres** — l'étage 2 doit ÉVINCER une candidate déjà retenue.

## 7. Résidus

* **`#1080-r1`** — `NOT IsMoving(Owner)` n'est pas porté. `IsMovingTrigger$$ShouldTrigger` lit un
  flag booléen du composant de mouvement (`<composant>+0xa8+<offset>`) qu'aucun canal du runner ne
  publie. Le port collapse à VRAI : correct **sur ce vecteur** (côté port le déplacement est
  ATOMIQUE, donc le flag natif serait faux quand `On(0xb)` part), FAUX sur un vecteur qui partirait
  pendant une animation de déplacement. Dégradation PERMISSIVE, nommée.
* **`CanMove(Owner)` ne tient que 3 de ses 4 étages** — `MovementComponent$$IsAllowedToMove` n'est
  publié par aucun canal. Résidu **PRÉ-EXISTANT** du nœud `entities/triggers.py::CanMove`, hérité tel
  quel (le trait `Stationary` = 0x418, lui, est porté).
* **`PowerUp(27)` NON CONFRONTÉ** — sur un runner monté par `rl_duel build` il n'y a aucun power-up,
  donc ce terme du bucket est constant à 0. Le prédicat est gardé OFFLINE (M5), pas live.
* `unitSelectionType`, `ignoreForcedTargets`, `maxDuplicatesAllowed`, les `MoveUnitBehaviourOptions`
  zéroées et les trois derniers arguments de `PerformAIAttack` : transportés, jamais lus — MÊMES
  résidus que tous les call-sites déjà portés.
