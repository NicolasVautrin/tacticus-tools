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

### 3bis. `#175-r1` — PORTÉ (2026-08-15), et le blocage `etage` n'existait pas

Rien ne manquait au niveau ÉTAGE : `IPathfinders.GetPath(IgnoreTerrain, …)` était déjà porté et
confronté. Ce qui manquait était un ÉCRIVAIN — la clé `movetowards_hexdist` n'en avait **aucun**.

Livré : `ignore_terrain_pathfinder.get_path_node_counts_by_pos` (jumeau en domaine POSITION du
moteur `Board`), `_movetowards_target_pos` / `_movetowards_pathdist_by_pos`, la pose de
`meta["movetowards_pathdist"]` dans `apply_tile_attributes` (clé RENOMMÉE avec son producteur), et
le substrat que `_unit_record` jetait : `owned_effects` = `{type, source, active}` **plus**
`parent`, posés dans les TROIS jumeaux de `leaf_ctx`.

Deux points de RE **en plus des six** ci-dessus, lus à l'écriture sur `t6dpr4k06g` :

* la branche EFFET part de `IBattleQuery.<slot 192 = GetActiveEffects>(type, null)` puis
  `FirstOrDefault(allUnits, u.Id == comp.OwnerId)` — et elle **n'exclut PAS `case.Unit`**, alors
  que la branche ABILITY porte explicitement `u.Id != case.Unit.Id` ;
* les deux drapeaux `+0x70` sont des champs **DE SOUS-CLASSE**, et seule la taille d'instance
  l'établit (`frida/classes.tsv` : base 112, BioMinefield 120, MasterOfTheTutelaries 128). Le lire
  comme un champ unique ferait croire les deux drapeaux vrais des deux côtés. La DÉCLARATION
  Il2CppDumper confirme : BioMinefield n'override que `EffectSourceMustBeParent`, MoT que `Friends`
  et `OnlyUnitsWithAny`.

⚠ **La réserve du re-expert est LEVÉE** : `decisionView.units[].effects` publie bien `source`,
ainsi qu'`effectType` et `active` (`frida/hooks/game/effects.ts::EffectInfo`, servi tel quel par
`rpc-decision`). BioMinefield n'est donc PAS dégradé sur la face DÉCISION.

MESURE — écart CHEMIN vs HEX par board (`probe_175r1_movetowards_pathdist.py`) :
`MC1_67` 3/63, `C1_74` 9/61, `C3_59` 12/59, `C4_09` 5/66, `C6_09` 2/57 ; tuiles walkable
INJOIGNABLES depuis la cible (donc terme 0) : 4 sur `C4_09`, 2 sur `C1_74` et `C3_59`, 0 ailleurs.
Une amplitude ne s'estime pas depuis un board : elle varie d'un facteur 6 entre `C6_09` et `C3_59`.

NON COUVERT : l'ARGMAX natif des deux feuilles.

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
