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

## Les DEUX termes de `CalculateActionUtility` sont portes

`IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateActionUtility`
somme `custom + CalculateUtilityFromPredictions(MakeDamagePredictions(...))`.

- **custom** — `CalculateCustomUtility` ci-dessus (tranche 1 de `case-302`).
- **prediction** — `MakeDamagePredictions` (tranche 2), cf. la docstring de la methode. Le
  `targetsSelector` natif est `PlagueburstMortarAbility$$GetMainDamageTarget` =
  `Filter(Enemies(caster, target@0x178, 3), GetIsValidAdjacentEnemyTrigger)` : **l'occupant de la
  tuile VISEE**, filtre par le predicat (aura `ContagionsOfNurgle_ArmorReduction1` du camp du caster
  **OU** modificateur d'armure NEGATIF). `GetAdjacentDamageTargets` n'y entre PAS — les voisins ne
  comptent QUE par le terme custom.

Le predicat est FAUX partout sur un board frais, d'ou le `0` mesure par la tranche 1 ; il devient
VRAI des qu'un porteur du trait `ContagionsOfNurgle` du camp du caster arrive a portee d'aura de
l'occupant (ou qu'un modificateur d'armure negatif le frappe). MESURE (`probe_302_2` `--stage`) :
`pairUtility(caster, <tuile occupee>, 1169)` passe de `0` a `1.178` par le seul deplacement du
caster au contact — c'est le regime que la tranche 1 nommait « le port SOUS-ESTIME ».
"""
from __future__ import annotations

from ..entities.active_ability_type import ActiveAbilityType
from ..entities.formulas import Count
from ..entities.selectors.accessors import FixedTileIds
from ..runner.abilities.deathguard import (PLAGUEBURST_MORTAR_ID, plagueburst_adjacent_enemies,
                                           plagueburst_main_damage_target)
from . import prediction
from .nonattack import NonAttackComparablePlaybook, register_nonattack
from .probable_damage_event import ProbableDamageEvent
from .tile_targets import dsl_context_for_tile_target


class PlagueburstMortarPlaybook(NonAttackComparablePlaybook):
    """`IdunBattle.AI.Playbook.PlagueburstMortarPlaybook` — cf. l'en-tete du module."""

    __slots__ = ()
    ability_id = int(ActiveAbilityType.PlagueburstMortar)          # 0x491 = 1169
    ability_name = PLAGUEBURST_MORTAR_ID                           # cle gameconfig
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

    def make_damage_predictions(self, ctx, caster_tile, target, ability_id):
        """`PlagueburstMortarPlaybook$$MakeDamagePredictions` — mirror 1:1 :

            GenerateMultiHitAttackPredictions(
                caster, casterPosition, target,
                targetsSelector = PlagueburstMortarAbility$$GetMainDamageTarget,
                damage  = VigilanceEternalAbility$$GetDamage  (corps DEDUPLIQUE de
                          `IdunBattle.Entities.Abilities.AActiveAbility$$MinMaxDamage(avg)`),
                hits    = AActiveAbility$$GetHits (= `GetNumberConstant(0x2f = nrOfHits)`),
                profile = Nullable(AActiveAbility$$GetDamageProfile) (= le `damageProfile` config),
                weightSelector = null  -> `probability2 = Fix64(1)`)

        et `...ComparablePlaybook...$$GenerateMultiHitAttackPredictions` boucle
        `Select(targetsSelector, abilityEntities)` en emettant UN `ProbableDamageEvent` par entite
        selectionnee, tous avec le MEME (damage, hits, profile). Le port fait donc exactement cela :
        un `generate_multi_hit_attack_prediction` (le per-cible de cette meme fonction) par element
        du selecteur.

        TROIS lectures que le decompile impose, et qu'il faut lire pour ne pas se tromper de forme :

        1. **La PREDICTION ne couvre QUE `GetMainDamageTarget`** — l'occupant de la tuile VISEE.
           `GetAdjacentDamageTargets` (les ennemis des tuiles adjacentes), lui, n'entre QUE dans
           `ExecuteBehaviour`. La face DECISION voit donc les voisins par le seul terme CUSTOM
           (`GetAdjacentEnemies` x poids) et l'occupant par le seul terme PREDICTION : deux
           ensembles DISJOINTS de roles, pas un doublon a dedoublonner.
        2. **Aucun override d'entree.** `damage`/`hits`/`profile` sont les corps GENERIQUES
           (`MinMaxDamage(avg)`, `nrOfHits`, `damageProfile`) — donc pas d'entree dans
           `_MAKE_DMG_INPUT_OVERRIDES` ni dans `_PLAYBOOK_PROFILE_OVERRIDE` (contraste avec 1147 /
           1148, dont le playbook passe `param_8 = null`). Le chemin generique par cible est
           EXACTEMENT le bon.
        3. **Aucun batch secondaire, aucun event SELF** : un seul appel a
           `GenerateMultiHitAttackPredictions`, `GetHealthToLose` absent du corps.

        `caster_tile` EST utilise ici (contrairement au custom) : le natif passe `casterPosition` a
        `GenerateMultiHitAttackPredictions`, qui la place dans l'`AbilityEntities` ET la forwarde a
        `PredictAttack` — d'ou `attack_pos = caster_tile`, qui porte les modificateurs positionnels
        et le gate `HasMoved`.

        Contexte DSL indisponible -> `[]` : le terme de prediction est alors NUL, jamais invente."""
        dctx = dsl_context_for_tile_target(ctx)
        if dctx is None or target is None:
            return []
        events = []
        for u in (plagueburst_main_damage_target(FixedTileIds([int(target)])).select(dctx) or []):
            tid = u.get("id") if isinstance(u, dict) else None
            if tid is None:
                continue
            dp = prediction.generate_multi_hit_attack_prediction(
                ctx.scene, ctx.uid, int(tid), int(ability_id), self.ability_name,
                attack_pos=caster_tile)
            if dp is not None:
                events.append(ProbableDamageEvent(target=int(tid), prediction=dp))
        return events


register_nonattack(PlagueburstMortarPlaybook())
