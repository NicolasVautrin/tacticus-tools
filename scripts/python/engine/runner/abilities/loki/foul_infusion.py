"""`FoulInfusion` (1038) -- l'active de `deathPutrifier` << Pestillian >> (Death Guard / Nurgle),
seul porteur LINEUP (les trois autres -- `deathBossPutrifier`, `deathBossPutrifierLHE`,
`deathNpcPutrifier` -- sont npc). Portee #500.

i2 `Abilities/FoulInfusion_CurrentLevelDescription` : le cast BUFFE Pestillian et les allies
**Chaos** de son aura de Contagion, puis Pestillian **attaque** un ennemi adjacent.

================================================================================================
RE (decompile ghidra, build `rnca9r7q6c`) -- decompile = verite, live = confirmation
================================================================================================

## `IdunBattleLogic.Entities.Abilities.Active.Loki.FoulInfusionAbility$$ExecuteBehaviour`

MIRROR 1:1, terme a terme (slots de `IdunBattleLogic.Entities.DSLSelectors` du build `rnca9r7q6c` :
`+0x30 Owner`, `+0x40 Actor`, `+0x48 Caster`, `+0x60 Target`, `+0x68 ActiveTarget/Subject` --
mapping ETABLI par recoupement, cf. l'en-tete de `runner/abilities/deathguard.py`) :

    range   = DSLFormulas.ContagionsOfNurgleRange( Owner@+0x30,
                                                   unitSelectionType = 1, isNextTurn = 0 )
    friends = DSLSelectors.SurroundingFriends( Caster@+0x48, range, unique = 1,
                                               unitSelectionType = 3 )
    chaos   = DSLSelectors.UnitsWithTrait( friends, 0x7ea = 2026 Chaos, 3 )
    targets = TargetsSelector.op_Addition( chaos, Caster@+0x48 )
    buff    = DSLBehaviors.AddEffect( 0x432 = 1074 FoulInfusion_ExtraHits,
                                      GetAbilityStateReference(this),
                                      source  = Caster@+0x48,
                                      targets = targets,
                                      turns   = DSLFormulas.TurnsFromRounds(2) )
    foes    = DSLSelectors.AdjacentEnemies( Caster@+0x48, unique = 1, selectionType = 3 )
    foes    = DSLSelectors.Attackable( foes, 3 )
    pick    = DSLSelectors.PickRandomly( foes, amount = 1, allowDuplicates = 0,
                                         maxDuplicatesAllowed = 0x7fffffff,
                                         ignoreForcedTargets = false )
    atk     = DSLBehaviors.UseNormalAttack( Caster@+0x48, pick,
                                            parentAbility          = Nullable(AbilityOrEffect(...)),
                                            triggerAbilityOrEffect = default,
                                            options                = default )
    AActiveAbility.Execute( this, AbilityBehaviour.op_Addition(buff, atk), entities )

QUATRE lectures que le decompile impose et qu'il ne faut pas << lisser >> :

  * **UN SEUL `Execute`, et AUCUN `ExecuteAtomic`** : le decompile passe l'`op_Addition` DIRECTEMENT
    a `IdunBattle.Entities.Abilities.AActiveAbility$$Execute` (contraste `RevitalizingMalignancy`,
    qui emballe le sien dans un `AtomicGroup`). Le port rend donc un `Seq` nu (`op_add`).
  * **LE BUFF EST POSE AVANT L'ATTAQUE**, et c'est ce qui rend l'ability observable en UN cast :
    `FoulInfusion_ExtraHits` (`entities/effects/loki/hits.py`) ajoute `nrOfHits` = 1 coup `Toxic`
    aux attaques MELEE de son porteur (`IsMeleeAttack & OwnerIsCaster`) -- l'attaque libre de la
    phase 2 en beneficie DEJA. L'arme de `deathPutrifier` n'a pas de `Range` -> MELEE -> le gate
    mord. C'est la SEQUENCE, pas le compte, qui distingue un port juste d'un port faux.
  * **le rayon vient de l'aura, PAS d'une constante d'ability** :
    `ContagionsOfNurgleRange` -> `IdunBattle.Entities.Triggers.AuraEffectRangeFormula$$Calculate`,
    qui exige `HasTrait(unit, IAuraEffect(0x42f).GetTrait() = 0x7eb ContagionsOfNurgle)` puis
    evalue `GetCurrentRange()` = `GetRangeOnOwnerTurn(StatAmount(Owner, 0xc TurnsStarted))` :
    **1** aux tours 1-2, **2** aux tours 3-4, **3** a partir du 5e. Pestillian PORTE le trait
    `ContagionsOfNurgle` (gameconfig `deathPutrifier.traits`) -- sans lui la formule rend 0 et le
    volet << allies >> est vide, ce qui reste un resultat correct du natif.
  * **le caster est ajoute PAR L'ARBRE, pas par le masque** : `SurroundingFriends` retire les
    tuiles du centre (`SurroundingTiles(unit, r) - Tiles(unit)`), donc l'`op_Addition(chaos,
    Caster)` final est le SEUL chemin par lequel Pestillian se buffe lui-meme -- et il se buffe
    **sans passer par le filtre `UnitsWithTrait(Chaos)`**.

## `IdunBattleLogic.Entities.Abilities.Active.Loki.FoulInfusionAbility$$GetDynamicInvalidTargetReason`

    return UnitExtensions.HasTrait(target, 0x7ea) ? 0 : 2;   // 0x7ea = UnitTrait.Chaos
                                                             // 2     = TargetMatchesDynamicRule

Corps porte (et INCHANGE) dans `runner/abilities/targeting.py::_dynamic_rule_foul_infusion` ; cette
classe le SURCHARGE, et l'entree de `DYNAMIC_TARGET_RULE_UNPORTED` sort dans le meme commit --
meme forme que `ExemplarOfTheKauyonAbility` (#488).

## `IdunBattleLogic.Entities.Abilities.Active.Loki.FoulInfusionAbility$$.ctor`

    GetRange..ctor(g, null, <methodinfo>)                       # delegue de portee
    range = TargetingRange.CustomRange(g)                       # surcharge GetRange (delegue)
    TargetingOptions..ctor(&opts, isSelfCasting = 1, &range, forceMeleeTarget = 1,
                           rules = 0x482, null, null)           # surcharge A, FLAGS DIRECTS
    AActiveAbility..ctor(this, &opts, 2)                        # 3e arg = 2 = AbilityAttackType.Others

Le litteral EST le masque (aucun preset, aucune combinaison). Cf. `TARGETING_OPTIONS` ci-dessous.

================================================================================================
RESIDUS EXPLICITES (nommes, jamais lisses)
================================================================================================
 * `unitSelectionType = 3 = OnlyAliveAndTargetable` : le port n'honore que le volet ALIVE
   (`_within` ecarte les cadavres). Le volet TARGETABLE (deep-strike en cours d'atterrissage)
   n'est materialise nulle part cote port -- MEME residu que tous les selecteurs d'occupation
   (cf. `runner/operations/triggers/loki/cursed_plague_bell.py`).
 * `unique = true` (SurroundingFriends ET AdjacentEnemies) : `_within` ne peut pas produire de
   doublon (une unite = une position) -> flag sans effet observable.
 * `unitSelectionType = 1` de `ContagionsOfNurgleRange` : stocke par
   `AuraEffectRangeFormula$$.ctor` a `+0x1c` et LU par AUCUN chemin de `$$Calculate` (cf.
   `entities/formulas.py::AuraEffectRange`) -> non porte, comme chez les autres call-sites.
 * `parentAbility` / `triggerAbilityOrEffect` / `options` de `UseNormalAttack` : les OPTIONS
   `UseActiveAbilityBehaviour+0x68..+0xac` sont INERTES pour une attaque normale (cf. la docstring
   de la feuille `UseActiveAbility`) -- non portees, comme chez `WallOfMirrors`.
 * `AddEffect(..., scale_from_source=True)` : l'`AbilityStateReference` natif, c'est-a-dire
   `BaseEffect$$GetAbilityState(effect)` que lit `FoulInfusion_ExtraHitsEffect$$CreateAdditionalHits`
   pour son `ConfigVar(0xb = dmg)`. Le foyer partage `_source_scaling` prefere
   `passive_ability_level` au `active_ability_level` ; sur un BC normalise les deux valent
   `targetAbilityLevel`, donc l'ecart est nul ICI -- il est nomme, pas suppose.
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from ....dsl.effects import ExecutionContext
from ....entities.active_ability_type import ActiveAbilityType
from ....entities.behaviours import op_add, Seq
from ....entities.effect_type import EffectType
from ....entities.formulas import AuraEffectRange
from ....entities.selectors.accessors import Owner
from ....entities.selectors.geometry import PickRandomly
from ....entities.selectors.tiles import Caster
from ....entities.selectors.units import (AdjacentEnemies, SurroundingFriends, Union,
                                          UnitsWithTrait, UnitsWithoutTrait)
from ....entities.traits.unit_trait import UnitTrait
from ..base import ActiveAbility
from ..behaviours.combat import UseActiveAbility
from ..behaviours.context import entities_from_state
from ..behaviours.effects import AddEffect
from ..targeting import custom_range_func, RANGED_BOOL_FALSE, TargetingOptions
from ..targeting import _dynamic_rule_foul_infusion
from ..targeting_rule import TargetingRule as TR

if TYPE_CHECKING:
    from ...state import State

ABILITY_ID = "FoulInfusion"                                       # la cle gameconfig de l'ability 1038
EXTRA_HITS = int(EffectType.FoulInfusion_ExtraHits)               # 0x432 = 1074
EXTRA_HITS_NAME = EffectType.FoulInfusion_ExtraHits.name
# 3e argument LITTERAL de `DSLFormulas$$ContagionsOfNurgleRange` -> `AuraEffectRangeFormula..ctor`.
# ⚠ QUALIFICATION D'ENUM : `0x42f` vaut 1071 dans DEUX enums (`TriggeredAbilityType.CursedPlagueBell`
# et cet `EffectType`) -- ici c'est l'EffectType, celui que `effectsDatabase.Get` resout en IAuraEffect.
AURA_EFFECT = int(EffectType.ContagionsOfNurgle_ArmorReduction1)  # 0x42f = 1071
CHAOS = int(UnitTrait.Chaos)                                      # 0x7ea = 2026
# `DSLSelectors$$Attackable(entities, selectionType)` = `UnitsWithoutTrait(entities, 0x1b, selectionType)`
# -- le natif N'ALLOUE AUCUN selecteur dedie, il COMPOSE textuellement (lu au decompile).
STEPPABLE = int(UnitTrait.Steppable)                              # 0x1b = 27
BUFF_ROUNDS = 2                                                   # `TurnsFromRounds(2)`
# `PickRandomly(foes, amount, allowDuplicates, maxDuplicatesAllowed, ignoreForcedTargets)` --
# les quatre litteraux du call-site, transcrits tels quels.
PICK_AMOUNT = 1
PICK_MAX_DUPLICATES = 0x7FFFFFFF


def foul_infusion_buff_targets():
    """`op_Addition( UnitsWithTrait( SurroundingFriends(Caster, ContagionsOfNurgleRange(Owner)),
    0x7ea Chaos ), Caster )` -- MIRROR 1:1 du volet CIBLAGE du buff.

    `Owner()` (slot `DSLSelectors+0x30`) et `Caster()` (slot `+0x48`) sont NATIVEMENT distincts et
    le port les cite tels quels ; pour une ability ACTIVE montee par `entities_from_state`,
    `ctx.owner` n'est pas threade et `Owner()` retombe sur le caster -- les deux coincident A
    L'EXECUTION, mais le mirror ne les confond pas (meme note que `WallOfMirrors`)."""
    caster = Caster()
    rng = AuraEffectRange(Owner(), AURA_EFFECT, is_next_turn=False)   # isNextTurn = 0
    friends = SurroundingFriends(caster, rng)     # `SurroundingFriends(Caster, range, unique, 3)`
    return Union(UnitsWithTrait(friends, CHAOS), caster)             # `op_Addition(chaos, Caster)`


def foul_infusion_attack_target():
    """`PickRandomly( Attackable( AdjacentEnemies(Caster, unique, 3) ), 1, false, int.MaxValue,
    false )` -- MIRROR 1:1 du volet CIBLAGE de l'attaque libre.

    Le tirage consomme le PRNG de bataille (`ctx.pick_randomly` -> foyer unique
    `abilities/loki/splash._pick_randomly_n`) MEME quand le pool tient dans `amount` : c'est la loi
    #130/#215, et court-circuiter desaligne tout le flux RNG de l'attaque qui suit."""
    foes = AdjacentEnemies(Caster())                     # radius 1 = `AdjacentTiles`
    return PickRandomly(UnitsWithoutTrait(foes, STEPPABLE), amount=PICK_AMOUNT,
                        allow_duplicates=False, max_duplicates=PICK_MAX_DUPLICATES,
                        ignore_forced_targets=False)


def foul_infusion_tree() -> Seq:
    """`AActiveAbility.Execute( AddEffect(...) + UseNormalAttack(...) )` -- MIRROR 1:1.

    `op_add` = `IdunBattle.DSL.AbilityBehaviour$$op_Addition` (`CombinedBehaviour`), passe DIRECTEMENT
    a `Execute` : aucun `AtomicGroup` dans ce decompile."""
    return op_add(
        # `source` = `Caster@+0x48` : c'est le defaut de la feuille (`AbilityStateReference` = caster),
        # donc pas de `source_ref` explicite. `duration_rounds` = `TurnsFromRounds(2)` (ROUNDS, pas
        # tours -> la feuille appelle `ConvertRoundsToTurns`).
        AddEffect(EXTRA_HITS, EXTRA_HITS_NAME, foul_infusion_buff_targets(),
                  duration_rounds=BUFF_ROUNDS, scale_from_source=True),
        # `UseNormalAttack(caster, target, ...)` -> `UseActiveAbilityBehaviour` dont l'`activeAbilityType`
        # est `UnitNormalAttackType(caster)` : la feuille `UseActiveAbility` delegue a l'attaque NORMALE
        # du sujet (`AttackDamageOperation.execute`).
        UseActiveAbility(Caster(), foul_infusion_attack_target()))


class FoulInfusionAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.FoulInfusionAbility$$ExecuteBehaviour`
    (id 1038, `deathPutrifier` << Pestillian >> -- Death Guard). Arbre DSL `foul_infusion_tree()`
    (MIRROR 1:1 du decompile, cf. l'en-tete de module) :

        Execute( AddEffect( 1074 FoulInfusion_ExtraHits, AbilityStateReference, source = Caster,
                            targets = UnitsWithTrait(SurroundingFriends(Caster,
                                          ContagionsOfNurgleRange(Owner)), Chaos) + Caster,
                            turns = TurnsFromRounds(2) )
                 + UseNormalAttack( Caster, PickRandomly(Attackable(AdjacentEnemies(Caster)), 1) ) )

    SELF-CAST (`isSelfCasting = 1` ; `FoulInfusionPlaybook$$EvaluateNonComparable` ne rend eligible
    que SOI) : l'arbre ne lit JAMAIS `Target()`, donc `target_id` est indifferent.

    Deux phases dans UN seul cast, et dans CET ordre : (1) le buff `FoulInfusion_ExtraHits` sur
    Pestillian + les allies Chaos de son aura Contagion ; (2) une attaque NORMALE libre sur un
    ennemi adjacent tire au sort. L'attaque de la phase 2 beneficie DEJA du buff de la phase 1
    (l'effet est pose avant) -- l'arme de `deathPutrifier` est melee, donc le gate `IsMeleeAttack`
    de `FoulInfusion_ExtraHitsEffect$$CreateAdditionalHits` mord.

    Termine le tour (1038 hors des frozensets de `base.py` -> flags par defaut).

    Retour : {ability, caster, target, posed, attacks, dsl}."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.FoulInfusion)            # 1038
    ABILITY_ID = ABILITY_ID

    # `...FoulInfusionAbility$$.ctor` -- forme **FLAGS DIRECTS** (surcharge A, 7 arguments) :
    #     range = TargetingRange.CustomRange(<GetRange delegue>)      # surcharge GetRange
    #     TargetingOptions..ctor(&opts, isSelfCasting = 1, &range, forceMeleeTarget = 1,
    #                            rules = 0x482, null, null)
    #     AActiveAbility..ctor(this, &opts, 2)        # 3e arg = 2 = AbilityAttackType.Others
    # Le litteral EST le masque (ni preset copie, ni surcharge PRESET+FLAGS).
    #
    # Decomposition de 0x482 -- EXHAUSTIVE, aucun bit residuel (0x2 + 0x80 + 0x400 = 0x482) :
    #   bit  1  0x2    TargetMatchesDynamicRule   -> delegue `GetDynamicInvalidTargetReason`, PORTE
    #                                                ci-dessous (la cible doit porter `Chaos`).
    #   bit  7  0x80   AddCaster                  -> le caster est AJOUTE a l'ensemble des cibles.
    #   bit 10  0x400  TargetIsFriendly           -> refuse tout ENNEMI.
    #
    # `range` = `CustomRange(GetRange)` = la surcharge DELEGUE (3 call-sites dans le binaire) ->
    # `custom_range_func()` : `onlyAdjacent = RangedBool.False`, `overrideRange` VIDE, et le delegue
    # n'est pas resolu -> AUCUN gate de DISTANCE (borne inferieure assumee, jamais un elargissement).
    # `forceMeleeTarget = 1` = `RANGED_BOOL_FALSE` (l'enum natif est INVERSE : True=0, False=1).
    # `isSelfCasting = 1` -> l'aiguillage SELF-CAST de `TargetingQuery$$GetInvalidTargetReason`.
    #
    # Ce masque etait dans `TARGETING_OPTIONS_UNPORTED` ; il MIGRE ici avec la face COMBAT --
    # contrat de disjonction du module `targeting.py` (garde : `test_targeting_options_sources.py`).
    TARGETING_OPTIONS = TargetingOptions(
        rules=TR.TargetMatchesDynamicRule | TR.AddCaster | TR.TargetIsFriendly,
        self_cast=True, range=custom_range_func(), force_melee_target=RANGED_BOOL_FALSE)

    def get_dynamic_invalid_target_reason(self, state: "State", caster_id: int, target_id) -> int:
        """Le delegue `options+0x38` (slot vtable `+0x480`) =
        `...FoulInfusionAbility$$GetDynamicInvalidTargetReason`. Le CORPS vit dans
        `targeting.py::_dynamic_rule_foul_infusion` (mirror complet, y compris la lecture du
        pseudo-trait d'ALLIANCE `Chaos` dans le substrat d'entite et non dans le kit gameconfig) :
        il y a ete ecrit quand la face COMBAT n'etait pas portee, et il y RESTE -- un seul foyer,
        deux appelants successifs. Son entree de `DYNAMIC_TARGET_RULE_UNPORTED` est retiree par le
        MEME commit que cette classe (les deux tables `*_UNPORTED` sont disjointes
        d'`ABILITY_CLASSES`)."""
        return _dynamic_rule_foul_infusion(state, caster_id, target_id)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, caster_id, target_id)
        foul_infusion_tree().execute(entities, ectx)
        return {"ability": ABILITY_ID, "caster": caster_id, "target": target_id,
                "posed": [p for n, p in ectx.emitted if n == "AddEffect"],
                "attacks": [p for n, p in ectx.emitted if n == "UseActiveAbility"],
                "dsl": True}
