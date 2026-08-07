"""`IdunBattle.AI.Utilities.SwornProtector_AvoidAdjacentEnemiesUtility` (UtilityType **52**) -- la 2e
utilite du bucket de `IdunBattleLogic.Entities.Abilities.Active.Loki.SwornProtectorAbility$$GetSpawnTile`.
#120bis-spawn.

`52` est RE-DERIVE du build courant, pas recopie : `data/symbols/<build>/frida/enums.tsv`,
`IdunBattle.Configuration.UtilityType` -> `52=SwornProtector_AvoidAdjacentEnemies` sur `rnca9r7q6c`.
⚠ La fiche `docs/rl/case-120bis-flailswing-haze-confound.md` cite `WeightedUtility(0x33)` : elle a ete
ecrite sur `gqfc5mff6c`, ou `AttackTile` n'existait pas encore en 8. L'insertion a decale de +1 les 73
membres suivants (meme decalage que celui documente dans `operations/damage_utility.py` pour
`Damage` 34 -> 35), donc `0x33 = 51` y designe aujourd'hui `RoyalGuard_AvoidAdjacentEnemies` --
un HOMONYME quasi parfait, avec le MEME nom de cle BC. Le decompile du build COURANT dit `0x34 = 52`.
C'est exactement le mode de peremption silencieuse que la regle d'enum du `CLAUDE.md` decrit : le port
n'ecrit donc que le MEMBRE, jamais l'ordinal.

CORPS NATIF, remis en C# depuis
`IdunBattle.AI.Utilities.SwornProtector_AvoidAdjacentEnemiesUtility.u003CEvaluateMovementInStepsu003Ed__1$$MoveNext` :

    IEnumerator<Fix64> EvaluateMovementInSteps(UtilityMovementCase case) {
        var subject = DSLSelectors.Entity( case.get_UnitOrParent );       // unit ?? parent
        var tileEnt = DSLSelectors.Entity( case.get_MovementTile );       // la tuile CANDIDATE
        var adj     = DSLSelectors.AdjacentUnits(tileEnt, 1, 3);
        var enemies = DSLSelectors.Enemies(subject, adj, 3);
        int n       = <slot 0x18 de TargetsSelector>(enemies, entities);  // le COUNT
        yield return Fix64.FromInt(n) * GetUtilityValue("AdjacentEnemy"); // UN seul step
    }

Trois points LUS, et le premier est la difference avec son jumeau `RammingSpeed_MostAdjacentEnemies` :

* **le sujet est `get_UnitOrParent`, pas `case.unit`.** `IdunBattle.AI.Utilities.UtilityMovementCase$$
  get_UnitOrParent` = `unit ?? parent`. Sur le SEUL call-site porte (`SortTilesByUtilityForSummon`,
  `case.unit == null`), le sujet est donc le **PARENT** -- Creed. La feuille reste ACTIVE en regime
  spawn, la ou `RammingSpeed_MostAdjacentEnemies` degrade a 0 : recopier sa garde `is_spawning`
  aurait rendu CETTE feuille inerte sur son unique call-site, donc restaure le collapse qu'elle
  vient reparer.
* **l'ancre est la tuile CANDIDATE** (`case.get_MovementTile`), pas la tuile du sujet -- c'est ce qui
  rend la feuille DISCRIMINANTE d'une candidate a l'autre.
* **la cle BC n'est pas devinable** : resolue 100 % offline par
  `python probe_212_bc_key_literals.py --symbol "<le symbole ci-dessus>"` -> `'AdjacentEnemy'`
  (SANS prefixe, contrairement au `'RAMMINGSPEED_AdjacentEnemy'` du jumeau), recroisee avec
  `data/seed-bc.json` `Utilities.Default.SwornProtector_AvoidAdjacentEnemies` = **-20**.
  ⚠ Le probe imprime la premiere sous-table qui porte cette cle, et c'est
  `RoyalGuard_AvoidAdjacentEnemies` (meme cle, meme valeur -20) : c'est le SYMBOLE interroge, pas la
  ligne imprimee, qui designe la sous-table a lire. Les deux existent dans le BC.

Le poids est **NEGATIF** : chaque ennemi adjacent a la tuile candidate la penalise de 20. C'est ce
qui fait que le natif pose Kell du cote OPPOSE a l'attaquant -- la mesure live de
`docs/rl/case-120bis-flailswing-haze-confound.md` (`d(caster, creed) == 2` sur 3/3 montages) est
exactement la consequence de ce signe.

SUBSTRAT OFFLINE : `ctx["enemy_units"]` + `ctx["elev_by_pos"]` + `ctx["neigh_by_pos"]`, tous les
trois publies par `tile._spawn_leaf_ctx` (regime SPAWN) -- avec le camp deja calcule PAR RAPPORT AU
PARENT, ce qui est precisement le `get_UnitOrParent` du natif. Le comptage passe par
`engine.battle_query.count_adjacent`, FOYER UNIQUE d'`IterateAdjacentTiles` cote port (distance hex 1
+ porte d'elevation `|Delta| < 2`), comme le jumeau RammingSpeed.

DEGRADATION : pas de liste d'ennemis (ctx vide, `State` sans entites) -> **0.0**, ce qui redonne
l'ordre SOURCE du selecteur -- c'est-a-dire exactement le comportement d'avant ce port. Aucun
classement invente.

⚠ **L'INSCRIPTION AU REGISTRE EST FAITE ICI, PAS DANS `tile.py`** -- patron `engine/utilities/move.py`,
qui ecrit lui aussi son entree depuis son propre module. Raison de perimetre : `engine/utilities/
tile.py` est le foyer d'une autre tranche en vol au moment de cette livraison, et les deux entrees
voisines (54 `RammingSpeed`, 67 `LeadingTheCharge`) y sont ecrites en dur. Le side-effect est sur
depuis le SEUL consommateur (`runner/operations/triggers/loki/sworn_protector.py` importe ce module
avant d'appeler le tri), mais il gagnerait a rejoindre le litteral de `UTILITY_BY_TYPE` quand ce
foyer sera libre.
"""
from __future__ import annotations

from .base import BaseUtility
from .tile import UTILITY_BY_TYPE
from .utility_type import UtilityType
from ..battle_query import count_adjacent, neigh_map


class SwornProtector_AvoidAdjacentEnemiesUtility(BaseUtility):
    """`#ennemis de (case.unit ?? case.parent) adjacents a la tuile candidate` x
    `Utilities.Default.SwornProtector_AvoidAdjacentEnemies.AdjacentEnemy` (= -20)."""
    UTILITY_TYPE = int(UtilityType.SwornProtector_AvoidAdjacentEnemies)   # 52 sur `rnca9r7q6c`

    def evaluate(self, tile, meta, ctx, wt) -> float:
        if tile is None:
            return 0.0
        c = ctx or {}
        # PAS de garde `is_spawning` (contraste `RammingSpeed_MostAdjacentEnemies`) : le natif lit
        # `get_UnitOrParent`, donc le PARENT quand `case.unit` est nul. `_spawn_leaf_ctx` campe
        # justement `enemy_units` par rapport au parent -> la liste est deja la bonne.
        enemies = c.get("enemy_units") or ()
        if not enemies:
            return 0.0
        positions = [e["pos"] for e in enemies if isinstance(e, dict) and e.get("pos")]
        # lazy : utilities <- battle_query <- hexgeo. Le voisinage NATIF accompagne l'elevation
        # (les DEUX etages d'`IterateAdjacentTiles`) ; `neigh_map` lit le canal quelle que soit la
        # forme du contexte.
        n = count_adjacent((tile[0], tile[1]), positions, c.get("elev_by_pos"), neigh_map(c))
        return n * wt.sub("SwornProtector_AvoidAdjacentEnemies", "AdjacentEnemy")


SWORN_PROTECTOR_AVOID_ADJACENT_ENEMIES = SwornProtector_AvoidAdjacentEnemiesUtility()

# Mirror de `IdunBattle.Core.Services.UtilitiesDatabase$$GetUtility` : FEUILLE, pas composite --
# `UtilitiesDatabase$$InitializeUtilities` ne compose que les types qui ont une entree dans son
# `Dictionary<UtilityType, UtilityType[]>`, et 52 n'en a pas, donc `GetUtility` rend directement
# l'instance de la classe (meme critere que 54 et 67).
UTILITY_BY_TYPE[int(UtilityType.SwornProtector_AvoidAdjacentEnemies)] = (
    SWORN_PROTECTOR_AVOID_ADJACENT_ENEMIES)
