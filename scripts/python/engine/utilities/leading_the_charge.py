"""`IdunBattle.AI.Utilities.LeadingTheCharge_ChargeTileUtility` (UtilityType **67**) -- le 2e terme du
bucket de `IdunBattleLogic.Entities.Abilities.Active.Loki.LeadingTheChargeAbility$$GetMoveTile`.

`67` est RE-DERIVE du build courant, pas recopie : `data/symbols/<build>/frida/enums.tsv`,
`IdunBattle.Configuration.UtilityType` -> `67=LeadingTheCharge_ChargeTile` sur `rnca9r7q6c`. Le port
n'ecrit donc JAMAIS le litteral, il passe par le MEMBRE `UtilityType.LeadingTheCharge_ChargeTile`.

CORPS NATIF, remis en C# depuis
`IdunBattle.AI.Utilities.LeadingTheCharge_ChargeTileUtility.u003CEvaluateMovementInStepsu003Ed__1$$MoveNext` :

    IEnumerator<Fix64> EvaluateMovementInSteps(UtilityMovementCase case) {
        Fix64 u = Fix64.FromInt(0);
        var tile  = case.position.MainTile;                       // case+0x18 -> get_MainTile
        var free  = this.battleQuery.<slot itf 0x52>(tile);       // GetFreeAdjacentTiles(from)
        if (free.Count > 0)
            u += Fix64.FromInt(free.Count) * GetUtilityValue("PreferAdjacentFreeTiles");
        yield return u;                                           // UN seul step
    }

Trois points LUS, dont deux qu'un nom seul aurait fait deviner de travers :

* **le slot n'est PAS devine** : `0x52` = 82, LU dans
  `data/symbols/<build>/metadata/interface_slots.tsv` -> `IBattleQuery 82 GetFreeAdjacentTiles 1`
  (arite 1, ce qui exclut les surcharges LISTE de `GetAdjacentTiles`, d'arite 4). Le mirror deja
  porte de ce natif est `runner/abilities/targeting.get_free_adjacent_tiles` ; ici l'ancre est une
  TUILE (pas une entite), donc le compte passe par `battle_query.adjacent_addable_count`, le meme
  foyer `GetAdjacentTiles + porte d'elevation |Delta| < 2 + CanAddUnit` que
  `HammerOfWrathPlaybook` (#116) et `GeminaeSuperiaPlaybook` (case-165b).
* **la cle BC n'est pas devinable** : elle est RECOUPEE avec `data/seed-bc.json` ->
  `Utilities.Default.LeadingTheCharge_ChargeTile` = `{"PreferAdjacentFreeTiles": 5}`. C'est une
  DONNEE de BC (`engine.weights`), jamais une constante de code -- le port lit `wt.sub(...)`.
* **l'ancre est la tuile CANDIDATE**, pas la tuile reelle du caster : `from` = `case.position.MainTile`,
  c'est-a-dire la tuile balayee par `SortTilesByUtility`. C'est ce qui rend cette feuille
  DISCRIMINANTE (elle varie d'une candidate a l'autre), la ou un ancrage sur le caster en aurait
  fait un terme constant.

SENS DE JEU (i2 1204) : « summons up to 4 Death Riders in free adjacent hexes » -- Dreir charge de
preference sur la tuile qui laisse le PLUS de place libre autour de lui, parce que c'est la que ses
Death Riders se poseront. La feuille EST ce biais, et elle vaut jusqu'a 6 x 5 = 30 points, donc elle
DOMINE largement le second terme du bucket (`MovementSuggestion` = `[Tile(7), TileDistance(34)]`,
dont le `TileDistance` plafonne a |0.2|). Le classement des tuiles de charge de Dreir est donc, en
pratique, un classement par nombre de voisins libres -- `Tile(7)` (elevation, effets de hex) ne
departageant qu'a egalite de ce compte.

SUBSTRAT OFFLINE : `ctx["neigh_by_pos"]`, `ctx["walkable_by_pos"]`, `ctx["elev_by_pos"]` et les
positions occupees (`friend_units` / `enemy_units` / `self_pos`) -- exactement ce que produisent
`runner_tile_leaf_ctx` et `tile_leaf_ctx`.

⚠ **`self_pos` est COMPTE OCCUPE, et c'est le natif** : `TileContentComponent$$IsEmpty` rend FAUX sur
la tuile ou le caster se tient encore pendant tout le sweep (`GetMoveTile` est evalue AVANT le
`MoveUnit`). Contrairement a `GeminaeSuperiaPlaybook`, ce corps natif ne RE-CREDITE PAS cet hex
(pas d'`OwnerInAdjacentTile` ici) -- ne pas ajouter la compensation par analogie.

DEGRADATION : `walkable_by_pos` absent -> `can_add_unit` degrade en permissif (borne SUPERIEURE),
meme degradation nommee que partout ailleurs ; `neigh_by_pos` absent -> repli `hexgeo.neighbors`
(ordre non natif, compte identique).
"""
from __future__ import annotations

from .base import BaseUtility
from .utility_type import UtilityType
from ..battle_query import adjacent_addable_count


def _occupied_positions(ctx: dict) -> set:
    """Positions que `CanAddUnit` voit OCCUPEES : toutes les unites vivantes POSEES, **self INCLUS**
    (cf. la note `self_pos` de l'en-tete). Jumeau du helper homonyme de
    `engine/playbook/geminae_superia.py` -- meme mirror de
    `IdunBattle.Entities.Components.TileContentComponent$$IsEmpty`."""
    c = ctx or {}
    occ = {tuple(u["pos"]) for u in (c.get("friend_units") or ()) if u.get("pos")}
    occ |= {tuple(u["pos"]) for u in (c.get("enemy_units") or ()) if u.get("pos")}
    sp = c.get("self_pos")
    if sp:
        occ.add(tuple(sp))
    return occ


class LeadingTheCharge_ChargeTile(BaseUtility):
    """`IdunBattle.AI.Utilities.LeadingTheCharge_ChargeTileUtility` :
    `#tuiles LIBRES adjacentes a la tuile candidate` x
    `Utilities.Default.LeadingTheCharge_ChargeTile.PreferAdjacentFreeTiles`."""
    UTILITY_TYPE = int(UtilityType.LeadingTheCharge_ChargeTile)   # 67 sur `rnca9r7q6c`

    #: `GetUtilityValue(this, "PreferAdjacentFreeTiles")` -- cle de `Utilities.Default.
    #: LeadingTheCharge_ChargeTile` du BC (= 5 sur `data/seed-bc.json`).
    FREE_HEX_KEY = "PreferAdjacentFreeTiles"

    def evaluate(self, tile, meta, ctx, wt) -> float:
        if tile is None:
            return 0.0
        c = ctx or {}
        n = adjacent_addable_count((tile[0], tile[1]), c.get("neigh_by_pos"),
                                   c.get("walkable_by_pos"), _occupied_positions(c),
                                   c.get("elev_by_pos"))
        if n <= 0:                       # `if (free.Count > 0)` du natif -- inerte (0 x w = 0),
            return 0.0                   # transcrit pour rester lisible face au decompile.
        return float(n) * float(wt.sub("LeadingTheCharge_ChargeTile", self.FREE_HEX_KEY))


LEADING_THE_CHARGE_CHARGE_TILE = LeadingTheCharge_ChargeTile()
