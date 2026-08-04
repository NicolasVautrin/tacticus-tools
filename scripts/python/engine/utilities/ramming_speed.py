"""`IdunBattle.AI.Utilities.RammingSpeed_MostAdjacentEnemies` (UtilityType **54**) — la 2e utilite du
bucket de `IdunBattleLogic.Entities.Abilities.Active.Loki.RammingSpeedAbility$$GetTileToMoveTo`.

`54` est RE-DERIVE du build courant, pas recopie : `data/symbols/<build>/frida/enums.tsv`,
`IdunBattle.Configuration.UtilityType` -> `54=RammingSpeed_MostAdjacentEnemies` sur `rnca9r7q6c`.
(#252/#283 ont renumerote quatre enums d'un build a l'autre ; le port n'appelle donc JAMAIS le
litteral, il passe par le MEMBRE `UtilityType.RammingSpeed_MostAdjacentEnemies`.)

CORPS NATIF, remis en C# depuis
`IdunBattle.AI.Utilities.RammingSpeed_MostAdjacentEnemies.u003CEvaluateMovementInStepsu003Ed__1$$MoveNext` :

    IEnumerator<Fix64> EvaluateMovementInSteps(UtilityMovementCase case) {
        Fix64 u = Fix64.FromInt(0);
        var tile = case.position.MainTile;                            // case+0x18 -> get_MainTile
        foreach (var _ in this.battleQuery.<slot itf 0x7f>(tile, case.unit, ignoreSteppables: false))
            u += GetUtilityValue("RAMMINGSPEED_AdjacentEnemy");       // literal RESOLU, cf. plus bas
        yield return u;                                               // UN seul step
    }

Trois points LUS, dont deux qu'un nom seul aurait fait deviner de travers :

* **la cle BC n'est pas devinable** : le litteral IL2CPP vit dans `global-metadata.dat`, Ghidra n'en
  montre qu'un slot. Resolu 100 % offline par
  `python probe_212_bc_key_literals.py --symbol "<le symbole ci-dessus>"` ->
  `'RAMMINGSPEED_AdjacentEnemy'` (majuscules collees), recroise avec `data/seed-bc.json`
  `Utilities.Default.RammingSpeed_MostAdjacentEnemies` = **20**. C'est une DONNEE de BC
  (`engine.weights`), jamais une constante de code.
* **le comptage porte sur les ENNEMIS, pas sur les unites** : l'appel a TROIS arguments
  (`from`, `unit`, `ignoreSteppables`), ce qui exclut d'emblee
  `IdunBattle.Core.Services.BattleQuery$$GetAdjacentUnits` (qui en a QUATRE :
  `tiles, friendsOf, enemiesOf, ignoreSteppables`). Le 2e argument est le POINTEUR `case.unit`
  (case+0x10), donc la surcharge `GetAdjacentEnemies(IEntity from, IEntity unit, bool)` -- celle qui
  resout le camp par `OwnerComponent.get_CurrentPlayerEntityId(unit)` puis
  `IterateAdjacentTiles(from)` + `GetUnitsOnTiles`. (Ne PAS recopier un numero de slot d'une fiche
  ecrite sur un autre build : ils ont bouge entre `gqfc5mff6c` et `rnca9r7q6c`, cf. case-27.)
* **l'ancre est la tuile CANDIDATE**, pas la tuile reelle du caster : `from` = `case.position.MainTile`,
  c'est-a-dire la tuile balayee par `SortTilesByUtility`. C'est ce qui rend cette feuille
  DISCRIMINANTE (elle varie d'une candidate a l'autre), la ou un ancrage sur le caster en aurait
  fait un terme constant.

La CIBLE de la charge compte elle aussi : toute candidate est adjacente a la cible (elle sort de
`CanAddUnit(AdjacentTiles(Target))`), donc chaque candidate vaut au minimum 1 x 20. Ce n'est pas un
biais du port, c'est la geometrie du call-site.

SUBSTRAT OFFLINE : `ctx["enemy_units"]` (dicts `{pos, ...}`, camp resolu par l'appelant relativement
a `case.unit`) et `ctx["elev_by_pos"]` -- exactement ce que produisent `runner_tile_leaf_ctx` et
`tile_leaf_ctx`. Le comptage passe par `engine.battle_query.count_adjacent`, le FOYER UNIQUE de
`IterateAdjacentTiles` cote port (distance hex 1 + porte d'elevation `|Delta| < 2` inconditionnelle).

DEGRADATION : pas de sujet (`case.unit == null`) ou pas de liste d'ennemis -> **0.0**. Le natif, lui,
LEVE dans ce regime (`GetAdjacentEnemies` deref `unit`), et aucun call-site porte ne l'y amene : les
deux consommateurs de cette feuille passent le caster. Rendre 0 est la degradation sure, pas un
comportement natif mirroré.
"""
from __future__ import annotations

from .base import BaseUtility
from .utility_type import UtilityType


class RammingSpeed_MostAdjacentEnemies(BaseUtility):
    """`IdunBattle.AI.Utilities.RammingSpeed_MostAdjacentEnemies` (le natif n'a PAS le suffixe
    `Utility` sur cette classe-la) : `#ennemis de case.unit adjacents a la tuile candidate` x
    `Utilities.Default.RammingSpeed_MostAdjacentEnemies.RAMMINGSPEED_AdjacentEnemy`."""
    UTILITY_TYPE = int(UtilityType.RammingSpeed_MostAdjacentEnemies)  # 54 sur `rnca9r7q6c`

    def evaluate(self, tile, meta, ctx, wt) -> float:
        if tile is None:
            return 0.0
        c = ctx or {}
        if c.get("is_spawning") or c.get("uid") is None:
            return 0.0                       # `case.unit == null` -> aucun camp a resoudre
        enemies = c.get("enemy_units") or ()
        if not enemies:
            return 0.0
        # lazy : utilities <- battle_query <- hexgeo. #433-r4-r1-r4-r2-r1 : le voisinage NATIF
        # accompagne l'elevation (les DEUX etages d'`IterateAdjacentTiles`) ; `neigh_map` lit le
        # canal quelle que soit la forme du contexte (ici un dict).
        from ..battle_query import count_adjacent, neigh_map
        positions = [e["pos"] for e in enemies if isinstance(e, dict) and e.get("pos")]
        n = count_adjacent((tile[0], tile[1]), positions, c.get("elev_by_pos"), neigh_map(c))
        return n * wt.sub("RammingSpeed_MostAdjacentEnemies", "RAMMINGSPEED_AdjacentEnemy")


RAMMING_SPEED_MOST_ADJACENT_ENEMIES = RammingSpeed_MostAdjacentEnemies()
