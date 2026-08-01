# case-381-r4 — les collapses IMPÉRATIFS de `MovableTilesInRange` portaient un pathfinding NU

Ferme le résidu `#381-r4` (nommé par `case-381-r1` §5). Résidu neuf qui en sort : `#381-r5` (§4).

## 1. Ce qui était vrai de l'énoncé, et ce qui ne l'était pas

Trois call-sites collapsent le nœud `IdunBattleLogic.Entities.DSLSelectors$$MovableTilesInRange`
en appel direct au pathfinder. Vérifié au décompilé (build `rnca9r7q6c`) : le nœud prend bien
**cinq** arguments (`unitSelector, unitTileSelector, overrideRange, ignoreFlags,
ignoreUnitsOnTiles`), et sa chaîne passe par `BattleQuery$$GetMovableTilesFor` →
`MovementQuery$$GetMovableTilesFor` → `$$FindAnyOrAllMoveableTiles` → `$$AnyOrFillMoveableTiles`,
donc par `GetReachableTiles` — gate d'expansion `BasePathfinder$$NodesInNextLevel` →
`IsValidContinuePathTile` (#131) **et** dispatch `MovementQuery$$GetPathfinderTypeForUnit` compris.

L'énoncé disait « le correctif est le même à recopier ». Deux corrections :

* le correctif n'est pas trois blocs recopiés mais **un FOYER** —
  `engine/services/movement_query.get_movable_tiles_for`, mirror de
  `MovementQuery$$GetMovableTilesFor`, qui rend le STOP-SET comme le natif ;
* `GetPathfinderTypeForUnit` **n'est pas** `IsLikeFlying ? Fly : Walk`. Il a une branche
  MOUVEMENT SPÉCIAL en amont, que personne ne porte — §4.

## 2. Ce que le gate manquant coûtait, site par site (mesuré AVANT le correctif)

`probe_381r4_imperative_collapses.py` — boards réels de `data/boards/`, porteurs réels
(`genesKelermorph` Judh, `custoKyrus` Tyrith, `worldKharn` Kharn ; aucun n'est `Flying`/`Burrow`,
aucun ne porte Mounted/Vehicle/Unstoppable, donc le gate mord sur les trois), portée 2, tous les
couples (caster, cible) à distance 2..4 entre tuiles marchables :

| site | board | pool / sortie différente | dont destination changée |
|---|---|---|---|
| `abilities/genestealer._charge_candidate_tiles` | `C2_26` | **151** pools | **92** HeroicFusillade · **83** VigilanceEternal |
| idem | `EMC2_02` | **232** pools | **143** · **141** |
| `triggers/loki/betrayer._betrayer_stop_tile` | `C2_26` | — | **157** tuiles d'arrêt |
| idem | `EMC2_02` | — | **242** |
| `triggers/genestealer._hypersensory_move_dest` | les deux | — | **0 sur 2960 configurations** |

La tuile en trop est ILLÉGALE côté natif : elle ne pend que d'un Swamp. Le port envoyait donc la
charge là où le jeu ne peut pas aller (ex. `C2_26`, caster (0,1), cible (2,1) : port (2,2), natif
(1,1)).

`PVP_desert_04` porte 10 tuiles block-entering mais **aucune** configuration discriminante : le
probe y rend `rc 1` (« le bras NE DISCRIMINE PAS ») plutôt qu'un vert vide.

## 3. Le troisième site n'est PAS corrigé, et c'est un résultat

`HypersensoryAbilitiesAbility_MoveAndSpawnDecoy$$CreateBehaviour` passe comme `overrideRange` le
champ `DSLFormulas+0x20` — la formule partagée `Direct(1)` que `DSLFormulas$$.ctor` alloue
(`+0x18`=0, `+0x20`=1, `+0x28`=2, `+0x30`=100, `+0x38`=-1). À portée 1 :

    NodesInNextLevel : if (currentTile != startTile && !IsValidContinuePathTile(...)) return [];

la seule tuile qui s'étend au seul niveau parcouru **EST** le start ⇒ le prédicat n'est jamais
consulté. Établi par mesure (2960 configurations, 0 différence) **et** par une sentinelle
committée (`test_..._offline.py` : `can_continue` qui lève, silencieuse à portée 1, appelée à
portée 2). Le dispatch fly y est inerte aussi (aucun des 5 porteurs de `HypersensoryAbilities`
n'est `IsLikeFlying`). Le brancher serait un no-op non mesurable ; la garde verrouille la
**prémisse** (`HYPERSENSORY_MOVE_RANGE == 1`), pas un comportement.

## 4. `#381-r5` — la branche MOUVEMENT SPÉCIAL, découverte en confrontant — **FERMÉ**, `case-381-r5`

`IdunBattle.Core.Services.MovementQuery$$GetPathfinderTypeForUnit(unit, ignoreSpecialMovement)`,
lu verbatim :

```
if (!ignoreSpecialMovement) {
    if (HasEffect(unit, 0x40b)) return IsLikeFlying(unit) ? 7  : 6;
    if (HasEffect(unit, 0x474)) return IsLikeFlying(unit) ? 9  : 8;
    if (HasEffect(unit, 0x4d6)) return IsLikeFlying(unit) ? 11 : 10;
    if (HasEffect(unit, 0x625)) return IsLikeFlying(unit) ? 13 : 12;
}
return IsLikeFlying(unit) ? 3 : 0;
```

Les quatre effets sont les états « je descends du ciel », et les quatre ids résolvent dans l'enum
du port : `1035 TeleportStrike_TeleportingIn`, `1140 StormboyzStrike_TeleportingIn`,
`1238 FearOfTheUnseen_TeleportingIn`, `1573 TitanhammerSquad_TeleportingIn`.

Le port n'a aucun des pathfinders 6..13 et **personne** ne teste ces effets — ni le nœud DSL
(`#381-r1`), ni `ai/state_bridge._move_tiles`, ni le foyer neuf. Mesuré (`C2_26`, seed 38104,
`overrideRange` 2, tout début de bataille) : `tyranDeathleaper` et `bloodIntercessor` portent
`TeleportStrike_TeleportingIn` (`remaining` 2) et le natif leur rend **35 tuiles** — un pool
board-wide, pas un disque de rayon 2 — contre **9** au port. Dégradation RESTRICTIVE, TRANSITOIRE.

**Fermé le 2026-08-01** — `case-381-r5-mouvement-special.md` : dispatch porté entier au foyer
`entities/pathfinding/pathfinders`, les huit types 6..13 sont des décorateurs au pool board-wide,
et les quatre `IsValidTeleportTile` sont distincts. Confronté 35/35, 47/47, 37/37 sur trois boards.
Le datapoint `bloodIntercessor` de `#381-r2` y reçoit son verdict chiffré (artefact ; le résidu
FlyPathfinder qui subsiste vaut **1 tuile**, pas 20).

`services/movement_query.has_special_movement` reste le nommeur de régime pour un mesureur.

## 5. La confrontation

**Le foyer, nu.** `aiMovableTiles` appelle littéralement `MovementQuery$$GetMovableTilesFor` :
l'égalité attendue est EXACTE, unité par unité. `C2_26`, `overrideRange` 2, roster complet du
seed — **5/5 WALK exactes** ; écartées et nommées : pool natif vide (`#381`), volantes
(`#381-r2`), mouvement spécial (`#381-r5`). Le test EXIGE qu'au moins une unité voie son pool
changer par le gate, sinon il échoue.

**L'atterrissage.** Cast réel de `1202 VigilanceEternal` sur une géométrie où le port GATÉ et le
port NON GATÉ désignent deux tuiles différentes : caster (4,1), cible (3,4) — port gaté **(3,3)**,
port d'avant **(4,3)**, **live (3,3)**.

Gardes committées : `tests/engine/runner/test_381r4_imperative_collapses_offline.py` (4 tests,
board synthétique à couloir de Swamp ; les 3 qui portent sur un site corrigé sont vues **ROUGES**
quand on désarme le gate) et `..._live.py` (2, auto-discriminantes).

## 6. Ce qui reste

* **L'occupation par MAIN TILE** dans les trois collapses (`_living_occupants_map`, l'`occupants`
  de betrayer) là où le natif lit `GetTileContent` = l'EMPREINTE. Même écart que
  `ai/state_bridge._move_tiles` ; hors périmètre `#381-r4`, non corrigé.
* **`_betrayer_stop_tile` associe un `entity id`** à la tuile (`occupants[t] = eid`) là où
  `WalkPathfinder$$UnitIsBlockedByEnemyUnit` compare à la TEAM du mover : un **ALLIÉ bloque la
  traversée** alors que le natif le laisse passer. Dégradation RESTRICTIVE — à l'inverse de tous
  les autres résidus du nœud. Le stop-set, lui, est correct. Nommé dans la docstring, non corrigé
  (hors périmètre).
* Les résidus hérités du nœud (`#381`, `#381-r2`, `#381-r3`, `IsTileReserved`/`IsTemporary`,
  `Steppable`, `GetEffectiveDepth`) valent à l'identique pour le foyer.
