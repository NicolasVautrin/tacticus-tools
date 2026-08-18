"""`IdunBattleLogic.AI.Utilities.UnitPicker.*` — les utilites du CANAL UNITE, celui qui repond a
« QUI JOUE ENSUITE ». Build `t6dpr4k06g`. Cette tranche (#10022-r3) n'en porte qu'UNE :
`ShortestPathToEnemyUtility` (`UtilityType.UnitWithShortestPathToEnemy` = 72).

POURQUOI CELLE-LA D'ABORD -- et pourquoi le reste ne sert a rien sans elle
--------------------------------------------------------------------------
`IdunBattle.AI.OperationalDeciders.DefaultGroupOperator$$.ctor` alloue **huit** buckets d'utilite
et `IdunBattleLogic.AI.Utilities.UtilityDecider.u003CDecideEnumeratoru003Ed__6u003Cobjectu003E$$MoveNext`
les parcourt DANS L'ORDRE, en s'arretant au premier qui departage. Mesure de l'inventaire
(`docs/rl/case-10022-unitpicker-inventaire.md` section 8) : sur le seul regime confrontable
d'aujourd'hui, les buckets 0 a 5 rendent tous ex-aequo et **c'est le bucket 6, celui-ci, qui
tranche**. Un port de la colonne vertebrale sans lui rendrait systematiquement le premier
candidat -- soit exactement le comportement actuel du port, avec en plus l'illusion d'un etage.

CE QUE LE CANAL UNITE N'EST PAS
--------------------------------
Ce n'est ni le canal TUILE (`utilities/tile.py`, signature `(tile, meta, ctx, wt)`) ni le canal
MOUVEMENT (`utilities/move.py`, `(ctx, pos)`). Le natif a une methode PAR CANAL sur `BaseUtility`
(`EvaluateTileInSteps` / `EvaluateMovementInSteps` / `EvaluateUnitInSteps`) et le picker n'appelle
que la troisieme. `engine/utilities/base.py` documente deja ce parti : chaque sous-systeme fixe sa
propre signature d'appel. D'ou `evaluate_unit(...)` ci-dessous.

⚠ NE PAS CONFONDRE avec `MinDistanceToClosestEnemyUtility` (`utilities/move.py`, type 17), qui
utilise le MEME pathfinder `PathfinderType.IgnoreTerrain` mais ne calcule PAS la meme chose :
  * MinDist  : min sur le **FOOTPRINT COMPLET** d'**UN SEUL** ennemi -- le `ClosestEnemy` FIGE en
    amont par `MovementActionGenerator.u003CFindClosestEnemyu003Ed__8$$MoveNext`, avec ses quatre
    filtres de ciblabilite ;
  * celle-ci : min sur **TOUS** les ennemis rendus par `GetAllEnemyUnitsOfUnit`, **sans aucun
    filtre de ciblabilite**, et sur leur **MAIN TILE** seule -- pas leur empreinte.
Les deux divergent donc des qu'une unite est multi-hex, ou qu'un ennemi est non ciblable
(deep-strike, Environment, taunt). Ne jamais substituer l'une a l'autre.

LE DECOMPILE, LU VERBATIM
--------------------------
`IdunBattleLogic.AI.Utilities.UnitPicker.ShortestPathToEnemyUtility$$EvaluateUnitInSteps` n'alloue
que la machine a etats ; le corps est dans
`IdunBattleLogic.AI.Utilities.UnitPicker.ShortestPathToEnemyUtility.u003CEvaluateUnitInStepsu003Ed__0$$MoveNext`,
remis en C# :

    var dc = new <>c__DisplayClass0_0 { <>4__this = this,
                                        unitTile = unit.GetMainTile(this.state) };
    int? minSteps = null;
    foreach (var target in Enumerable.OrderBy(this.state.GetAllEnemyUnitsOfUnit(unit),
                                              dc.<EvaluateUnitInSteps>b__0)) {
        yield return BaseUtility.<statics+0x30>;                     // pas de travail (-12345)
        var targetTile = target.GetMainTile(this.state);
        if (minSteps.HasValue && minSteps.Value <= <distance>(dc.unitTile, targetTile)) continue;
        var path = this.pathfinders.<slot 4>(1, unit, dc.unitTile, targetTile, null);
        if (path != null) {
            if (minSteps.HasValue && path.Count >= minSteps.Value) continue;
            minSteps = path.Count;
            if (minSteps.Value == 1) break;
        }
    }
    yield return minSteps.HasValue ? Fix64(-minSteps.Value) : BaseUtility.<statics+0x18>;

et le comparateur du tri, qui est un corps A PART et que Ghidra rend AVEC ses arguments
(`IdunBattleLogic.AI.Utilities.UnitPicker.ShortestPathToEnemyUtility.u003Cu003Ec__DisplayClass0_0$$u003CEvaluateUnitInStepsu003Eb__0`) :

    int b__0(IEntity target) =>
        this.<>4__this.query.<slot 0x6c>(this.unitTile, target.GetMainTile(<>4__this.state));

CINQ LECTURES QU'IL FAUT NOMMER, PARCE QU'AUCUNE NE SE DEDUIT DU NOM
--------------------------------------------------------------------
1. **`slot 4` d'`IPathfinders` = `GetPath` a CINQ parametres**, donc la surcharge
   `Pathfinders$$GetPath(pathfinderType, unit, from, to, useTeleporter)` -- LU dans
   `data/symbols/<build>/metadata/interface_slots.tsv` (`IPathfinders 4 GetPath 5`), pas devine.
   Le `1` est un **LITTERAL** au site : `PathfinderType.IgnoreTerrain`, meme pour une unite
   volante. C'est le meme litteral, et le meme pathfinder, que `GetMinDistanceToEnemy` -- d'ou la
   reutilisation de `entities/pathfinding/ignore_terrain_pathfinder`, deja confronte au natif
   (180 distances, 0 ecart).
2. **`slot 0x6c` d'`IBattleQuery` = `GetDistance` a DEUX parametres** (meme table ; `IBattleQuery
   108/109/110` sont trois surcharges homonymes). Le site passe deux `TileEntity`, donc la
   surcharge `(IEntity tileA, IEntity tileB)`, qui delegue au slot 9 d'`IMovementQuery`
   (`IdunBattle.Core.Services.BattleQuery$$GetDistance` -- son corps entier est ce forward).
   C'est la distance **HEX**, pas un chemin.
3. **`path.Count` est un compte de NOEUDS, extremites INCLUSES** (`route+0x18` = `List._size`) :
   `aretes + 1`. Une flood-fill qui compte des ARETES rend UN DE MOINS. Le mirror
   `ignore_terrain_pathfinder.get_path_node_counts*` porte deja cette convention.
4. **Les `yield` intermediaires valent `BaseUtility.<statics+0x30>` = `Fix64(-12345)`**, pas la
   valeur. La valeur est le DERNIER `Current`, apres que `MoveNext()` a rendu `false` -- la state
   machine Roslyn ne remet pas `<>2__current` a zero au `yield break`. Porter la methode NOMMEE
   ferait conclure « elle ne fait rien ».
5. **Aucun chemin vers aucun ennemi -> `BaseUtility.<statics+0x18>`**, la sentinelle HORS COURSE
   (`base.OUT_OF_RUNNING`) -- **pas** le veto ferme `statics+0x20`, et surtout pas `0`. La
   distinction commande le jeu entier : `PreferAbilitiesUtility` rend `statics+0x18` pour TOUTE
   unite dans ce build, donc si `+0x18` eliminait, aucune unite IA ne jouerait jamais.

CE QUE LES DEUX ELAGAGES CHANGENT -- ET CE QU'ILS NE CHANGENT PAS
------------------------------------------------------------------
Le mirror ci-dessous les porte tels quels, mais il faut savoir ce qu'ils valent, sinon on ne sait
pas ce qu'on valide :

  * elagage 1 (`minSteps <= hexDist(unitTile, targetTile)` -> skip) est **ADMISSIBLE** sur un
    graphe ou toute arete relie deux voisins hex : un chemin de `hexDist` aretes compte
    `hexDist + 1` noeuds, donc `path.Count >= hexDist + 1 > minSteps` -- la cible ne pouvait pas
    ameliorer. ⚠ **Un TELEPORTEUR le rendrait FAUX** : `IgnoreTerrainPathfinder$$IsValidPathNode`
    autorise une arete entre deux tuiles de teleportation quelle que soit l'elevation, donc un
    chemin peut y etre plus court que la distance hex. Ce serait alors un elagage errone DU NATIF,
    a mirrorer tel quel -- pas un bug du port. Aucun board de `data/boards/` n'en porte (meme
    constat que `walk_pathfinder` / `ignore_terrain_pathfinder`, qui ne portent pas l'exception).
  * elagage 2 (`path.Count >= minSteps` -> skip) ne fait que ne pas ecraser un meilleur minimum.
  * le `break` a `minSteps == 1` ne peut se produire que si la main tile de l'unite EST celle d'un
    ennemi (un chemin d'un seul noeud), donc jamais en pratique -- mais il est porte.

⇒ Hors teleporteur, **le resultat est exactement `min over ennemis of pathNodeCount(unitTile,
targetMainTile)`**, et l'ORDRE DE VISITE n'y change rien. C'est ce que le cliquet
`probe_10022r3_shortest_path_to_enemy.py` verifie en confrontant le mirror fidele a cet argmin
naif sur les boards reels -- une propriete FALSIFIABLE, pas une reformulation.
"""
from __future__ import annotations

from .base import BaseUtility, OUT_OF_RUNNING
from .utility_type import UtilityType


class ShortestPathToEnemyUtility(BaseUtility):
    """`IdunBattleLogic.AI.Utilities.UnitPicker.ShortestPathToEnemyUtility`
    (`IdunBattleLogic.AI.Utilities.UnitPicker.ShortestPathToEnemyUtility$$.ctor` est trivial : il
    n'appelle que `BaseUtility..ctor` ; toutes ses dependances arrivent par
    `IdunBattle.AI.Utilities.BaseUtility$$Init`). Bucket **6** des huit de
    `DefaultGroupOperator$$.ctor`, avec `minUtilityDifference = 0` et le flag `+0x18` a FAUX."""

    UTILITY_TYPE = int(UtilityType.UnitWithShortestPathToEnemy)      # 72

    def evaluate_unit(self, unit, *, main_tile_of, enemies_of, hex_distance,
                      path_node_count) -> float:
        """`ShortestPathToEnemyUtility.u003CEvaluateUnitInStepsu003Ed__0$$MoveNext` — mirror 1:1.

        Les quatre dependances sont INJECTEES parce qu'elles le sont aussi cote natif
        (`BaseUtility$$Init` renseigne `state` en `+0x10`, `query` en `+0x20`, `pathfinders` en
        `+0x28`) : cette classe ne connait ni le `State` ni le `Board` du port.

          * `main_tile_of(entity) -> pos | None` = `IdunBattle.Entities.EntityExtensions$$GetMainTile`.
            ⚠ La MAIN TILE, pas l'empreinte : une unite a 3 ou 7 pieds n'entre ici que par une
            seule tuile, aux DEUX bouts (celle de l'unite comme celle de la cible).
          * `enemies_of(entity) -> iterable` = `IdunBattle.Entities.StateExtensions$$GetAllEnemyUnitsOfUnit`,
            dont le corps entier est
            `GetAllEnemyUnitsOfPlayer(state, EntityExtensions.GetCurrentPlayer(unit, state), null)`.
            **AUCUN filtre de ciblabilite** ici, contrairement a `FindClosestEnemy`.
          * `hex_distance(pos_a, pos_b) -> int` = le `slot 0x6c` d'`IBattleQuery`. Sert AU TRI et a
            l'elagage 1, jamais au resultat.
          * `path_node_count(unit, from_pos, to_pos) -> int | None` =
            `IPathfinders.GetPath(PathfinderType.IgnoreTerrain, unit, from, to, null)?.Count`,
            en NOEUDS. `None` = le natif rend `null` (aucun chemin) -> la cible est ignoree, ce
            qui n'est PAS la meme chose que `minSteps` restant nul a la fin.

        Rend `Fix64(-minSteps)` (un NEGATIF : plus l'unite est PRES d'un ennemi, plus son utilite
        est HAUTE) ou la sentinelle `OUT_OF_RUNNING` si aucun ennemi n'est joignable."""
        unit_tile = main_tile_of(unit)
        min_steps: "int | None" = None

        # `Enumerable.OrderBy(...)` — tri STABLE en .NET comme en Python : a distance hex egale,
        # l'ordre reste celui de `GetAllEnemyUnitsOfUnit`. Le comparateur natif est un corps a part
        # (`<>c__DisplayClass0_0.<EvaluateUnitInSteps>b__0`) qui recalcule `GetMainTile(target)`
        # a chaque appel ; ici la cle est evaluee une fois par element, ce qui ne change que le
        # nombre d'appels, pas l'ordre.
        cibles = sorted(enemies_of(unit),
                        key=lambda t: hex_distance(unit_tile, main_tile_of(t)))

        for target in cibles:
            # `yield return BaseUtility.<statics+0x30>` — un pas de TRAVAIL, jamais le resultat.
            # Le port n'a pas de coroutine a decouper : il n'y a rien a rendre ici.
            target_tile = main_tile_of(target)
            if min_steps is not None and min_steps <= hex_distance(unit_tile, target_tile):
                continue                                  # elagage 1 (cf. en-tete du module)
            path = path_node_count(unit, unit_tile, target_tile)
            if path is not None:
                if min_steps is not None and path >= min_steps:
                    continue                              # elagage 2
                min_steps = int(path)
                if min_steps == 1:
                    break
        if min_steps is None:
            return OUT_OF_RUNNING
        return float(-min_steps)
