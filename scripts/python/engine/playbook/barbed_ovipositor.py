"""`IdunBattle.AI.Playbook.Loki.BarbedOvipositorPlaybook` -- face ATTACK du triggered
`BarbedOvipositor` (1204), passif de `tyranParasite` << Parasite of Mortrex >> (HERO, au pool) et
de 6 npc `tyranBossParasite*` : 7 porteurs DISPATCHES, tete de la liste des residus ATTACK de #419.

Feuille `TriggeredAbilitiesUtility(2)` du composite Damage(34), MEME dispatcher que Psyker,
AggressiveOnslaught, SuppressiveFire et Lakrimae (`utilities/tile.py::evaluate_attack_in_steps`,
vslot 3).

## Le corps natif, remis en C#

`IdunBattle.AI.Playbook.Loki.BarbedOvipositorPlaybook$$CalculateAttackUtilityInStepsInternal` monte
la SM `d__4` (case @+0x20, delegue scorer @+0x28) ; le corps est
`BarbedOvipositorPlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__4$$MoveNext`, QUATRE
etats de yield -- donc quatre sorties, dans CET ordre :

    if (!case.DamagePrediction.HasValue)                      // case@+0x28, champ `hasValue`
        yield return Fix64.op_Implicit(0)                     // etat 1
    else if (!case.DamagePrediction.Value.MightBeKill)
        yield return Fix64.op_Implicit(0)                     // etat 2
    else if (UnitExtensions.HasTrait(case.Target, (UnitTrait)5))   // case@+0x20, 5 = Mechanical
        yield return Fix64.op_Implicit(0)                     // etat 3
    else
        yield return Fix64.op_Implicit(GetUtilityValue(
            case.DamagePrediction.Value.WillBeKill ? "BARBEDOVIPOSITOR_DefinitelyKill"
                                                   : "BARBEDOVIPOSITOR_PossibleKill"))  // etat 4

Quatre lectures qui ne se devinent pas -- et aucune ne se generalise depuis un voisin de la liste :

1. **Le playbook lit la PREDICTION du case, pas seulement la cible.** C'est le premier playbook
   ATTACK porte qui le fait : `Lakrimae`/`SuppressiveFire` ne consultent que la cible. Le champ est
   `UtilityAttackCase@+0x28` = `Nullable<DamagePredictionResult>` (offsets LUS dans
   `IdunBattle.AI.Utilities.UtilityAttackCase$$.ctor` et `$$ForDamagePrediction` : caster@+0x10,
   casterPosition@+0x18, target@+0x20, damagePrediction@+0x28 sur 0xa8 octets, heal@+0xd0,
   repair@+0xdc, effectType@+0xe8, abilityType@+0xf0). D'ou le parametre `prediction` ajoute a la
   signature de la face ATTACK : le natif passe le CASE ENTIER a chaque playbook, le port l'eclate
   en composants, et il en manquait un.

2. **`HasValue == false` rend 0** -- c'est le regime des cases construits par `ForEffect` /
   `ForHealPrediction` / `ForRepairPrediction`, qui ne portent aucune prediction de degat. Le repli
   `prediction is None -> 0.0` du port EST ce chemin natif, pas une degradation defensive.

3. **`UnitTrait` 5 = `Mechanical`**, qualifie des deux cotes : le mirror
   `engine.entities.traits.unit_trait.UnitTrait(5).name` rend `Mechanical`, et
   `IdunBattleLogic.Entities.Abilities.Triggered.Loki.BarbedOvipositorAbility$$CreateTrigger` monte
   la MEME exclusion cote COMBAT (un trigger `(target, 5)` passe a `AbilityTrigger$$op_LogicalNot`).
   Le playbook ne fait donc que refleter le trigger : une cible mecanique ne peut pas etre pondue
   dedans, l'utilite doit etre nulle. Le predicat porte sur la CIBLE, jamais sur le caster.

4. **Les deux poids sont des cles BC DISTINCTES, et le discriminant est `WillBeKill`** (kill
   GARANTI) contre `MightBeKill` (kill POSSIBLE) -- deux accesseurs natifs asymetriques deja
   mirrores dans `engine/services/damage_prediction.py` :
   `IdunBattle.Core.Services.DamagePredictionResult$$get_MightBeKill` = `CurrentHealth <= rawMax`,
   SANS aucun gate ; `$$get_WillBeKill` sort en tete sur `CannotBeGuaranteedKilled@0x89` puis
   compare a `BlockScenarios[0]` (ou `rawMin` si la liste est vide). Valeurs au gameconfig courant
   (`Utilities.Default.TriggeredAbilities`) : `BARBEDOVIPOSITOR_DefinitelyKill` = **50**,
   `BARBEDOVIPOSITOR_PossibleKill` = **25**. Le regime est donc a TROIS niveaux (0 / 25 / 50) --
   il n'est PAS degenere, et c'est ce qui rend la mesure live discriminante.

## Ce que la face COMBAT dit du meme passif (deja portee, #probe_o10)

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.BarbedOvipositorAbility$$CreateBehaviour` fait
naitre un `tyranSmnRipperSwarm` (`Constants.unitId`) sur la tuile liberee par le mort, sinon sur une
tuile adjacente (`DSLSelectors.Tiles -> CanAddUnit -> PickRandomly`, `Otherwise` la meme chaine sur
`AdjacentTiles`). Le trigger exige `AreEnemies` & `!IsObjectOrSteppable` & `OwnerIsActor` & `!(trait
5)`. Port : `engine/runner/operations/triggers/loki/barbed_ovipositor.py`. La face ATTACK est donc
l'estimation IA de CE gain : plus la mort est sure, plus le ver est sur d'eclore.

## Face MOVE : `yield Fix64(0)` CONSTANT

`BarbedOvipositorPlaybook.u003CCalculateMovementUtilityInStepsInternalu003Ed__3$$MoveNext` est
decompile LU : un unique `yield return Fix64.op_Implicit(0)`, rien d'autre. Elle n'entre donc pas au
registre `TRIGGERED_MOVE_PLAYBOOKS`, et son absence EST le comportement natif (meme forme que
`Lakrimae`, cf. #419 -- la taille trie, le decompile conclut).
"""
from __future__ import annotations

from ..entities.traits.unit_trait import UnitTrait, entity_trait_ids
from ..entities.triggered_ability_type import TriggeredAbilityType

# `UnitExtensions.HasTrait(case.Target, (UnitTrait)5)` -- 5 = Mechanical (enum QUALIFIE, cf. en-tete).
_MECHANICAL = int(UnitTrait.Mechanical)
# Les deux litteraux de chaine du corps natif, lus dans `Utilities.Default.TriggeredAbilities`.
_KEY_DEFINITELY = "BARBEDOVIPOSITOR_DefinitelyKill"      # branche `WillBeKill` (kill GARANTI)
_KEY_POSSIBLE = "BARBEDOVIPOSITOR_PossibleKill"          # branche par defaut


class BarbedOvipositorPlaybook:
    """`BarbedOvipositorPlaybook` (`IdunBattle.AI.Playbook.Loki`, triggered 1204). Seule la face
    ATTACK a un corps ; la face MOVE est un `yield 0` constant au natif (cf. en-tete)."""

    ability_id: int = int(TriggeredAbilityType.BarbedOvipositor)      # 1204

    def calculate_attack_utility_in_steps(self, ctx, attacker_uid: int, ability_id: int,
                                          case_tgt_id: int, attack_tile, prediction=None) -> float:
        """Mirror de `<CalculateAttackUtilityInStepsInternal>d__4$$MoveNext` (cf. en-tete), dans
        l'ORDRE natif : prediction absente -> 0 ; pas de kill possible -> 0 ; cible `Mechanical`
        -> 0 ; sinon le poids `DefinitelyKill` si le kill est GARANTI, `PossibleKill` sinon.

        `prediction` = `case.DamagePrediction` (`Nullable<DamagePredictionResult>`) : `None` mirror
        `HasValue == false`. Le substrat de traits est le foyer d'ENTITE `entity_trait_ids` (#225)
        -- kit gameconfig seede dans `UnitContext.traits` PLUS les traits accordes en bataille par
        le leaf DSL `AddTrait` : le natif interroge l'entite ECS, pas le kit statique."""
        if prediction is None:                       # `!case.DamagePrediction.HasValue` -> etat 1
            return 0.0
        if not prediction.might_be_kill():           # `get_MightBeKill` == false -> etat 2
            return 0.0
        sc = getattr(ctx, "scene", None)
        if sc is None:
            return 0.0
        tgt_ctx = sc.ctx(int(case_tgt_id)) if hasattr(sc, "ctx") else None
        vis = (getattr(sc, "vis_by_id", None) or {}).get(int(case_tgt_id))
        if _MECHANICAL in entity_trait_ids(tgt_ctx, vis):   # `HasTrait(target, 5)` -> etat 3
            return 0.0
        key = _KEY_DEFINITELY if prediction.will_be_kill() else _KEY_POSSIBLE
        return float(ctx.wt.triggered(key))          # `GetUtilityValue(<cle>)` -> etat 4
