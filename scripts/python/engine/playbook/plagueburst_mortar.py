"""`PlagueburstMortarPlaybook` (1169) — PREMIER membre de la route de decision a cibles TUILE.

## L'artefact natif, lu en entier

`IdunBattle.AI.Playbook.PlagueburstMortarPlaybook$$CalculateCustomUtility(caster, casterPosition,
target, abilityState, possibleTargets)` :

    sel = PlagueburstMortarAbility.GetAdjacentEnemies();          // arbre DSL
    ent = AbilityEntities(owner: caster, caster: caster, target: target);
    n   = TargetsSelector.Count(sel, ent);                        // slot 2
    return Fix64(n) * Playbook<T>.GetUtilityValue("PlagueburstMortar_AdjacentEnemy");

Trois lectures que le decompile impose, et que le port respecte :

1. **`casterPosition` n'entre PAS dans l'`AbilityEntities`.** Le terme custom est donc INDEPENDANT
   de la tuile depuis laquelle le caster tire — seule la tuile VISEE le fait varier. (Ce qui reste
   position-dependant, c'est le terme `Tile(7)` ajoute par `CalculateActionUtility` en aval.)
2. `IdunBattleLogic.Entities.Abilities.Active.PlagueburstMortarAbility$$GetAdjacentEnemies` =
   `Enemies(caster@0x160, Units(AdjacentTiles(target@0x178), unique: 1), 3)` — le terme `adj` de
   `plagueburst_damage_targets` (face COMBAT, portee par #90) **sans** son
   `Filter(GetIsValidAdjacentEnemyTrigger)`. Un seul artefact : le port appelle donc
   `engine.runner.abilities.deathguard.plagueburst_adjacent_enemies`, il ne le recable pas.
3. `target@0x178` est une entite **TUILE** (masque `...PlagueburstMortarAbility$$.ctor` = `0x40000042`,
   bit 6 `TargetIsTile`), d'ou `FixedTileIds([target])` comme vehicule de collapse — exactement ce que
   fait deja la face COMBAT (`deathguard.execute_plagueburst_mortar` : `target_sel =
   FixedTileIds([tile_id])`).

## Pourquoi la route NON-ATTAQUE et pas `_best_attack`

1169 a un `damageProfile`, donc `state_bridge._is_attack_ability` la laisse entrer dans les
`attackPlans` — mais avec `rankCount = 0` sur toute cible UNITE (mesure #27-4g), parce que la
structure d'affichage par-unite ne range pas une ability qui cible une tuile. `_best_attack` consomme
`ranked` : il ne peut structurellement rien en faire. Le critere reel de la route non-attaque est
« Comparable **invisible de `_best_attack`** » (cf. l'en-tete de `nonattack.py`), et 1169 y repond.

## Ce qui EST porte ici, et ce qui ne l'est PAS

`IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateActionUtility`
somme `custom + CalculateUtilityFromPredictions(MakeDamagePredictions(...))`. Cette tranche porte le
**custom** (mirror 1:1 ci-dessus). Le terme de PREDICTION reste a `0` :

`IdunBattle.AI.Playbook.PlagueburstMortarPlaybook$$MakeDamagePredictions` =
`GenerateMultiHitAttackPredictions(caster, casterPosition, target,
mainTarget = PlagueburstMortarAbility$$GetMainDamageTarget, GetDamage(abilityState), GetHits(),
Nullable(GetDamageProfile()))`, et `GetMainDamageTarget` = `Filter(Enemies(caster, target@0x178, 3),
GetIsValidAdjacentEnemyTrigger)`. Ce predicat (aura `ContagionsOfNurgle_ArmorReduction1` du camp du
caster **OU** modificateur d'armure NEGATIF sur le sujet) est FAUX partout sur un board frais — le
selecteur rend alors l'ensemble VIDE et la somme des predictions vaut reellement 0, donc le port est
**exact dans ce regime**, qui est celui de l'oracle live.

⚠ **RESIDU NOMME, tranche 2** : des qu'un ennemi satisfait le predicat, le natif ajoute un terme de
degat que ce port ne calcule pas → il SOUS-ESTIME l'utilite de 1169. Le predicat lui-meme est deja
porte (`deathguard.plagueburst_is_valid_adjacent_enemy_trigger`, ses DEUX branches depuis case-224) ;
ce qui manque est son evaluation dans le contexte de DECISION (`ctx.scene`) et le branchement sur
`prediction.make_damage_predictions`. Garde de non-regression silencieuse :
`tests/engine/test_plagueburst_mortar_decision_live.py::test_prediction_term_is_zero_only_when_the_native_predicate_is_false`.
"""
from __future__ import annotations

from ..entities.active_ability_type import ActiveAbilityType
from ..entities.formulas import Count
from ..entities.selectors.accessors import FixedTileIds
from ..runner.abilities.deathguard import plagueburst_adjacent_enemies
from .nonattack import NonAttackComparablePlaybook, register_nonattack
from .tile_targets import dsl_context_for_tile_target


class PlagueburstMortarPlaybook(NonAttackComparablePlaybook):
    """`IdunBattle.AI.Playbook.PlagueburstMortarPlaybook` — cf. l'en-tete du module."""

    __slots__ = ()
    ability_id = int(ActiveAbilityType.PlagueburstMortar)          # 0x491 = 1169
    W_ADJACENT_ENEMY = "PlagueburstMortar_AdjacentEnemy"           # 10 (BC.Utilities, build courant)

    def calculate_custom_utility(self, ctx, caster_tile, target, ability_id) -> float:
        """`PlagueburstMortarPlaybook$$CalculateCustomUtility` — mirror 1:1.

        `caster_tile` est ignore PARCE QUE LE NATIF L'IGNORE : son `AbilityEntities` ne porte que
        `owner`/`caster`/`target`, jamais `casterPosition`.

        Contexte DSL indisponible (Scene ou board absents) -> `0.0` : aucune utilite INVENTEE. La
        degradation est conservatrice — l'action reste generee par la route avec `u = 0`, elle perd
        seulement sa preference — et elle est visible (`probe_302 --stage`)."""
        dctx = dsl_context_for_tile_target(ctx)
        if dctx is None or target is None:
            return 0.0
        n = Count(plagueburst_adjacent_enemies(FixedTileIds([int(target)]))).evaluate(dctx)
        return float(n) * ctx.wt.sub("ActiveAbilities", self.W_ADJACENT_ENEMY)


register_nonattack(PlagueburstMortarPlaybook())
