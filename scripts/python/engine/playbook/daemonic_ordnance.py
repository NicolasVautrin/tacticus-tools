"""`DaemonicOrdnancePlaybook` (1148) — SECOND membre de la route de decision a cibles TUILE.

## L'artefact natif, lu en entier

`IdunBattle.AI.Playbook.Loki.DaemonicOrdnancePlaybook$$CalculateCustomUtility(caster, casterPosition,
target, abilityState, possibleTargets)` :

    sel = DaemonicOrdnanceAbility.GetTargetAreaTiles();               // arbre DSL (zone de tir)
    ent = AbilityEntities(owner: caster, caster: null, target: target);
    x   = Fix64(0);
    foreach (tileEntity in TargetsSelector.<slot 10>(sel, ent)) {     // Select, pas Count
        unit = UnitExtensions.GetUnit(tileEntity, state);             // occupant de la tuile
        if (unit != null && UnitExtensions.IsEnemy(unit, caster, state))
            x = Fix64.op_Addition(x, Fix64(0xa));                     // <-- CONSTANTE EN DUR
    }
    return x;

Quatre lectures que le decompile impose, et que le port respecte :

1. **`10` est une CONSTANTE DU BINAIRE, pas un poids de `BattleConfiguration`.** Le corps appelle
   `FixMath_NET_Fix64__op_Implicit(0xa)` et JAMAIS
   `IdunBattle.AI.Playbook.Playbooku003C__Il2CppFullySharedGenericTypeu003E$$GetUtilityValue` —
   contraste NET avec 1169, dont le meme terme passe par `GetUtilityValue(
   "PlagueburstMortar_AdjacentEnemy")`. Ne PAS aller chercher une cle dans `BC.Utilities` : il n'y en
   a pas, et en inventer une rendrait le terme dependant d'une table qui ne le pilote pas.
2. **La boucle est IMPERATIVE, seul l'ENSEMBLE est un arbre DSL.** Le natif n'appelle ni un selecteur
   `Enemies(...)` ni un `Count` : il ITERE les entites-tuiles et resout l'occupant de chacune. Le port
   mirrore cette forme (arbre DSL pour la zone, boucle pour le comptage) au lieu de recabler
   `Count(Enemies(Units(zone)))` — qui DEDOUBLONNERAIT par unite, la ou le natif compte PAR TUILE.
3. **`casterPosition` n'entre PAS dans l'`AbilityEntities`** (meme lecture que 1169) : le terme custom
   est INDEPENDANT de la tuile depuis laquelle le caster tire. Ce qui reste position-dependant, c'est
   le terme `Tile(7)` ajoute en aval par `CalculateActionUtility`.
4. **Le slot `caster` de l'`AbilityEntities` est NUL ici** (`ctor(entities, caster, 0, target, ...)`,
   la ou 1169 passe `ctor(entities, caster, caster, target, ...)`). Sans consequence : l'arbre
   `GetTargetAreaTiles` ne lit que `target@0x178` et l'etat de tour ; le `caster` du test d'ennemi est
   l'ARGUMENT de la fonction, pas un slot de l'`AbilityEntities`.

`IdunBattleLogic.Entities.Abilities.Active.Loki.DaemonicOrdnanceAbility$$GetTargetAreaTiles` :

    dir = If( IsPositionMachineForCurrentPlayer(2), Direct(1), Direct(4) )
    return TilesOnSameElevation( target@0x178, TilesInTriangleShape(target@0x178, dir), maxDiff = 1 )

C'est le MEME artefact que la face COMBAT (portee par #90) : le port appelle donc
`engine.runner.abilities.blacklegion.daemonic_ordnance_target_area_tiles`, il ne le recable pas.
`target@0x178` est une entite TUILE (masque `...DaemonicOrdnanceAbility$$.ctor` = `0x46000040`, bit 6
`TargetIsTile`), d'ou `FixedTileIds([target])` comme vehicule de collapse — exactement comme la face
COMBAT (`blacklegion.DaemonicOrdnanceAbility.execute_behaviour`).

⚠ `If(IsPositionMachineForCurrentPlayer(2), 1, 4)` fait dependre la GEOMETRIE de la zone du cote du
plateau ou la MoW du joueur COURANT est deployee. Ce predicat n'avait aucun canal cote DECISION avant
cette tranche : il rendait False d'office, donc `dir = 4` TOUJOURS, et la zone etait la mauvaise des
que le joueur courant avait sa MoW en `Bottom`. Le canal est desormais
`decisionView.mows[].owner/.slot` -> `AiDecisionContext.mow_slot_by_player` ->
`tile_targets.dsl_context_for_tile_target`.

## Pourquoi la route NON-ATTAQUE et pas `_best_attack`

Meme raison que 1169 : 1148 a un `damageProfile` (Plasma), donc `state_bridge._is_attack_ability` la
laisse entrer dans les `attackPlans` — mais la structure d'affichage par-unite ne range pas une ability
qui cible une TUILE, si bien que `_best_attack` (qui consomme `ranked`) ne peut structurellement rien en
faire. Le critere reel de la route non-attaque est « Comparable **invisible de `_best_attack`** »
(cf. l'en-tete de `nonattack.py`), et 1148 y repond.

## Ce qui EST porte ici, et ce qui ne l'est PAS

`ComparablePlaybook<T>.CalculateActionUtility` somme `custom + CalculateUtilityFromPredictions(
MakeDamagePredictions(...))`. Cette tranche porte le **custom** (mirror 1:1 ci-dessus). Le terme de
PREDICTION reste a `0`, et — contrairement a 1169 — c'est ici une propriete STRUCTURELLE de l'ability,
pas un regime :

`IdunBattle.AI.Playbook.Loki.DaemonicOrdnancePlaybook$$MakeDamagePredictions` boucle
`GenerateMultiHitAttackPredictions` sur `GetEntitiesFromSelector(
DaemonicOrdnanceAbility$$GetAllDamageableTargets, ...)`, et `GetAllDamageableTargets` =
`Enemies(caster@0x160, Units(Filter(GetTargetAreaTiles(), HasEffect(Tiles(Subject@0x180), 5 = Fire)),
1), 3)` : **les ennemis debout sur une tuile DEJA EN FEU**. Or c'est ce meme cast qui POSE le feu, en
DERNIER etage de son behaviour (`ExecuteBehaviour` [5] `AddEffect(Fire -> zone)`). Sur une zone qui ne
brule pas encore, le selecteur rend l'ensemble VIDE et la somme des predictions vaut REELLEMENT 0 —
le port est donc EXACT partout ou la zone visee ne porte pas deja `Fire` (5), ce qui inclut tout
premier cast et tout board frais.

⚠ **RESIDU NOMME (meme tranche 2 que 1169)** : des qu'un ennemi se tient sur une tuile en feu de la
zone visee, le natif ajoute un terme de degat que ce port ne calcule pas -> il SOUS-ESTIME l'utilite
de 1148. Le montage discriminant est explicite : caster 1148 une premiere fois pour allumer la zone,
puis re-scorer un tir sur cette meme zone avec un ennemi encore dessus (c'est exactement le protocole
de `docs/rl/case-172-mow-abilities-conditional.md`). Garde de non-regression silencieuse :
`tests/engine/test_daemonic_ordnance_decision_live.py::test_prediction_term_is_zero_because_the_area_is_not_burning`.
"""
from __future__ import annotations

from ..entities.active_ability_type import ActiveAbilityType
from ..entities.selectors.accessors import FixedTileIds
from ..runner.abilities.blacklegion import daemonic_ordnance_target_area_tiles
from .nonattack import NonAttackComparablePlaybook, register_nonattack
from .tile_targets import dsl_context_for_tile_target, unit_on_tile


class DaemonicOrdnancePlaybook(NonAttackComparablePlaybook):
    """`IdunBattle.AI.Playbook.Loki.DaemonicOrdnancePlaybook` — cf. l'en-tete du module."""

    __slots__ = ()
    ability_id = int(ActiveAbilityType.DaemonicOrdnance)           # 0x47c = 1148
    # `FixMath_NET_Fix64__op_Implicit(0xa)` litteral du corps natif — AUCUN `GetUtilityValue`, donc
    # AUCUNE cle `BC.Utilities` (contraste avec `PlagueburstMortar_AdjacentEnemy` de 1169).
    ENEMY_IN_AREA = 10.0

    def calculate_custom_utility(self, ctx, caster_tile, target, ability_id) -> float:
        """`DaemonicOrdnancePlaybook$$CalculateCustomUtility` — mirror 1:1.

        `caster_tile` est ignore PARCE QUE LE NATIF L'IGNORE : son `AbilityEntities` ne porte que
        `owner`/`target`, jamais `casterPosition`.

        Contexte DSL indisponible (Scene ou board absents) -> `0.0` : aucune utilite INVENTEE. La
        degradation est conservatrice — l'action reste generee par la route avec `u = 0`, elle perd
        seulement sa preference — et elle est visible (`probe_302_3 --stage`)."""
        dctx = dsl_context_for_tile_target(ctx)
        if dctx is None or target is None:
            return 0.0
        caster_team = (dctx.caster or {}).get("team")
        area = daemonic_ordnance_target_area_tiles(FixedTileIds([int(target)])).select(dctx)
        total = 0.0
        for tile in (area or []):
            # `UnitExtensions.GetUnit(tileEntity, state)` puis `UnitExtensions.IsEnemy(unit, caster,
            # state)` — ce dernier compare `GetCurrentPlayer(x).Team.Index` des deux cotes, ce que le
            # substrat de decision expose en `unit["team"]` (meme convention que le noeud `Enemies`).
            # PAS de dedoublonnage : le natif accumule PAR TUILE (la zone, elle, est deja un HashSet
            # de 3 tuiles au plus, `BattleQuery$$GetTilesInTriangleShape`).
            u = unit_on_tile(dctx, tile)
            if u is not None and u.get("team") != caster_team:
                total += self.ENEMY_IN_AREA
        return total


register_nonattack(DaemonicOrdnancePlaybook())
