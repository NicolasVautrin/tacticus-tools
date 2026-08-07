# case-175-r — le `BLOCAGE: capteur` couvrait quatre sujets de natures différentes

Build `rnca9r7q6c`. Garde : `scripts/python/tests/engine/test_175e_175r_tile_meta_live.py`.

La ligne `#175-r` disait « metadata par-tuile qu'aucun RPC ne remonte ». Confrontée au code
courant, elle couvrait **quatre** sujets, et **deux** ne demandaient aucun capteur.

## 1. `ability_friend_counts` — DÉRIVABLE, porté ici

Feuilles `KustomForceField(21)`, `DefenderOfTheGreaterGood(22)`, `SaviorProtocols(23)`. La clé
n'était posée que par `engine/runner/abilities/loki/mv71.py`, sur SON chemin ; ni
`apply_tile_attributes` (donc ni `engine.move` ni `playbook.base.tile_utility`) ni
`sort_tiles_by_utility` ne la posaient ⇒ les trois feuilles étaient **structurellement à 0**, hors
régime spawn compris.

Corps PARTAGÉ `IdunBattle.AI.Utilities.ATriggeredAbilityUtility.u003CEvaluateMovementInStepsu003Ed__3$$MoveNext` :

```c
if (!this.AppliesTo(case)) yield Fix64.Zero;
else yield Fix64.FromInt(Count(this.GetUnitsWithUtilityForMove(case))) * this.GetUtilityPerUnit();
```

Sélecteur commun `ATriggeredAbilityUtility$$GetFriendsAdjacentToMovementTile` :

```
Friends(Entity(case.unit), AdjacentUnits(Entity(case.MovementTile), 1, 3), 3) - Entity(case.unit)
```

— les AMIS du mover ADJACENTS à la tuile candidate, **self exclu** (`op_Subtraction`), puis
`UnitsWithTriggeredAbility(<utility+0x60>)`. `AdjacentUnits` passe par `IterateAdjacentTiles`, donc
porte d'élévation `|Δ| < 2` ⇒ `battle_query.is_adjacent`.

⚠ **UNE feuille s'écarte, et il faut le lire** —
`IdunBattle.AI.Utilities.DefenderOfTheGreaterGoodUtility$$GetUnitsWithUtilityForMove` REMPLACE ce
sélecteur par `SurroundingFriends(Entity(case.unit), Entity(case.MovementTile), 2, 1, 3)` quand
`HasFaction(case.unit, 9 = Tau)`. Deux écarts, tous deux load-bearing : **disque hex r=2** (donc
plus de porte d'élévation) **et aucune soustraction de `case.unit`** — un mover Tau porteur de 1155
se compte lui-même. Mesuré : ring-1 → **1**, disque → **3**, disque + porteur → **4**.

Les gates propres restent dans les `evaluate` (`HasRangedWeapon` pour 22 ;
`SaviorProtocolsUtility$$CanBeProtector` = `HasFaction(Tau) && !HasTriggeredAbility(1120)` pour 23) :
côté natif ils vivent dans le même `GetUnitsWithUtilityForMove`, qui rend `None()` — soit un compte
nul, soit exactement ce que rend un `evaluate` qui court-circuite.

**Porteur confrontable** : `tauShadowsun` porte 1155 et **est au pool** (les 6 autres porteurs sont
npc/summon ; les 6 porteurs de 1120 et les 0 de 1102 ne le sont pas).

## 2. `sort_tiles_by_utility` ne posait AUCUN attribut de tuile — corrigé ici

C'était le **troisième** constructeur de `meta` du composite `Tile(7)`, et le seul à n'appeler pas
`apply_tile_attributes`. Sur ce chemin — le sélecteur DSL
`IdunBattle.Entities.Selectors.SortTilesByUtilitySelector`, donc tous les call-sites de charge ET
le sweep de tuile de spawn d'un summon — les feuilles gatées sur un attribut de tuile rendaient 0
quoi que porte le `leaf_ctx`. Le natif, lui, évalue la MÊME `ComposedUtility` avec le MÊME
`UtilityMovementCase` sur les trois chemins.

## 3. `movetowards_hexdist` — le classement « dérivable OFFLINE des positions » est RÉFUTÉ

`case-175` §4 le rangeait comme « dérivable offline des positions, pas besoin de RPC ». Le
décompilé dit autre chose, sur **deux** étages :

```c
// IdunBattle.AI.Utilities.MoveTowardsUnitUtility$$GetMinDistanceToTarget
foreach (tile in EntityExtensions.IterateTiles(target, State)) {
    p = MovementQuery.<slot 4>(1, unit, unitTile, tile, 0);
    if (p != null && p.<+0x18> < min) min = p.<+0x18>;
}
return min;                                       // Nullable<int>
```

— une distance de **CHEMIN** (le service de MOUVEMENT, murs et occupants compris), pas
`hexgeo.distance`. Le nom `movetowards_hexdist` du port porte donc l'erreur dans son identifiant.

Et la CIBLE ne se dérive pas non plus d'une position : `<EvaluateMovementInSteps>d__15` la cherche
en balayant `Query.<slot 0x89 = GetAllAliveUnits>(null)` puis en testant `HasActiveAbility` /
`HasTriggeredAbility` / `GetOwnedEffect` selon que le virtuel `UnitIdentifierAbilityOrEffect()`
porte une ABILITY ou un EFFET, et retient la première AMIE ou ENNEMIE selon un troisième virtuel.

⇒ Blocage réel : **`etage`**, pas `capteur`. Résidu **`#175-r1`**.

## 4. Ce qui reste vraiment `capteur`

* **`door`** (`SummonDislikeDoorOpening(29)`, `HeroLikeDoorOpening(30)`) : `roomTileType` (0/1/2)
  est déjà projeté par `projectMatchState` mais absent de `tileMeta` ; manquent l'état
  ouvert/fermé et `BC.Board.Doors` (présent dans 15 des 779 dumps de board).
* **`occupant_is_powerup`** (`PowerUp(26)`) : canal d'occupance + prédicat power-up.

Reste inchangé : `CapturePoint(24)` est câblé mais **jamais vrai** (seed BC `RuleSet: null` /
`GameMode: Campaign`, 0 tuile territoire) — régime absent, pas trou. Et
`attract_mechanicals_neighbor` était déjà fermé par #477-r31.

## 5. Témoin NON NUL

| mesure | avant | après |
|---|---:|---:|
| `apply_tile_attributes(...)["ability_friend_counts"]` | **absente** | `{1155: 1}` |
| feuille 22, mover Tau, 3 amis dans le disque r=2 | **0** | **75** (= 3 × 25) |
| compte 1155, mover Tau **porteur** | — | **4** (self ré-injecté) |
| `sort_tiles_by_utility` → clés de `meta` | 4 | + celles d'`apply_tile_attributes` |

Contre-épreuve par MUTATION : 6/6 rougissent (dont « `_ability_friend_counts` rend `{}` » = l'état
exact d'avant-fix, et « `is_surrounding` désarmé » = la branche Tau non portée).

**NON COUVERT** : la confrontation du SCORE natif par feuille (hooks `scorer-damage-trace` aux RVA
`gqfc5mff6c`, reinject interdit) et l'ARGMAX live d'un mover Tau autour de `tauShadowsun` — montage
identifié (protocole `case-271` §5), non joué ici.
