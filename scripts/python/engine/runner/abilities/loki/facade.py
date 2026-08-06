"""SorcerousFacade (active 1100, `thousTzaangor` « Yazaghor », ThousandSons) — face COMBAT (#287).

La face DECISION (playbook : terme custom, gate `ShouldExecute`, prediction) a ete portee par #27-4e
(`engine/playbook/loki_custom.py::SorcerousFacadePlaybook`) ; ce module porte l'EXECUTION.

ARBRE NATIF — `IdunBattleLogic.Entities.Abilities.Active.Loki.SorcerousFacadeAbility$$
ExecuteBehaviour` (MIRROR du decompile, chaine `AbilityBehaviour.op_Addition` a QUATRE termes) :

    sel = Cache( First( SortByDistance( ValidNormalAttackTargets(Caster@0x48, CasterTile@0x50,
                                                                 range = null,
                                                                 ignoreRule/additionalRule = VIDES),
                                        Caster@0x48 ),
                        1, 0 ),
                 true )
    [1] AddEffect( 0x4b4 = 1204 SorcerousFacade_AdditionalHits,
                   abilityState = AbilityStateReference,
                   source  = Caster@0x48,
                   targets = op_Addition(Caster@0x48, Target@0x60),
                   turns   = TurnsFromRounds(1) )
    [2] UseActiveAbility( caster = Caster@0x48, target = sel,
                          abilityType = UnitNormalAttackType(Caster@0x48), <options> )
    [3] KillDeadUnits( killer = Caster@0x48, targets = sel )
    [4] TriggerAbilityDelayed( entity = Owner@0x30, 0x49c = 1180 SorcerousFacade_Switch,
                               unitSelectionType = 3 )
    AActiveAbility.Execute( (((([1] + [2]) + [3]) + [4]) )

`SorcerousFacadeAbility$$GetTarget` construit EXACTEMENT le meme `sel` (memes appels, memes
arguments) : UN SEUL artefact natif, partage avec la face DECISION (cf. `case-27-custom-utility.md`
§SorcerousFacade). C'est pourquoi `sorcerous_facade_target_selector()` ci-dessous est la source
unique des deux lectures COMBAT (le `UseActiveAbility` et le `KillDeadUnits`).

DEUX RAILS DISTINCTS, et les confondre est LE piege de cette ability :
  * la CIBLE DU CAST (`Target@0x60`) est un **ALLIE Psyker** — masque `TargetIsFriendly` ;
  * `sel` est l'**ENNEMI le plus proche** attaquable a l'attaque normale : c'est LUI qui prend
    l'attaque, et c'est deja ce que la face DECISION predit (#171).

ARBRE NATIF DE LA TRIGGERED — `IdunBattleLogic.Entities.Abilities.Triggered.Loki.
SorcerousFacade_SwitchAbility$$CreateBehaviour` (le [4] ci-dessus la declenche) :

    IfAlive( Caster@0x48,
             op_BitwiseAnd(
                 KillDeadUnits( Killer(Target@0x60), Target@0x60,
                                KillUnitBehaviourOptions.ForClearDeadUnits() ),
                 If( op_BitwiseOr( IsAlive(Target@0x60),
                                   op_BitwiseAnd( NOT IsAlive(Target@0x60),
                                                  IsCanAddUnit(Target@0x60) ) ),
                     SwitchPosition( Caster@0x48, Target@0x60 ) ) ) )

`IfAlive(sel, then, else)` est LITTERALEMENT `If(IsAlive(sel), then, else)` (relu :
`DSLBehaviors$$IfAlive` appelle `DSLTriggers$$IsAlive` puis `DSLBehaviors$$If`) -> pas de noeud
dedie cote port, la composition EST le mirror.
`IsCanAddUnit(sel)` = `AmountIsGreater(CanAddUnit(sel), Direct(0))` (relu :
`DSLTriggers$$IsCanAddUnit`).

i2 : « Target a friendly Psyker ... performs a NORMAL ATTACK against the closest enemy, then
switches positions with the targeted Psyker. »

LA REGLE DYNAMIQUE EST PORTEE, et ce n'etait PAS un raffinement cosmetique :
`...SorcerousFacadeAbility$$GetDynamicInvalidTargetReason` (mirror ci-dessous) refuse le cast des
que le caster n'a AUCUNE cible d'attaque normale -- et la MESURE (`probe_287 --far-foes`) montre le
natif refuser EN SILENCE (`ok=True`, aucune mutation, signature #111) un cast que le port, lui,
executait entierement (effet pose + switch). C'est une divergence PERMISSIVE qui MUTAIT l'etat :
elle est fermee ici.

CE QUE LE PORT NE FAIT PAS (residus NOMMES) :
  * la garde `IsTemporary` des tuiles du switch (le port n'a pas de tuile temporaire).

FERME depuis #287-r1 : `UnitFlag.NoActionAvailable` (4), que le natif pose en queue de cast
(`IdunBattle.Operations.MarkUnitAsNoActionAvailableOperation`). Le residu etait TRANSVERSE au
turn-flow, pas propre a cette ability -- il est ferme au foyer
(`runner/operations/turnflow.py::MarkUnitAsNoActionAvailableOperation`, branchee en queue de
`FinishUnitTurnOperation`), pas ici. L'ecart de flags mesure par `probe_287` (`[1, 2, 3, 4]`
natif contre `[1, 2, 3]` port) tombe a VIDE.
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from ..base import ActiveAbility
from ..behaviours import (AddEffect, KillDeadUnits, SwitchPosition, TriggerAbilityDelayed,
                          UseActiveAbility, entities_from_state,
                          TRIGGERED_ABILITY_DELAYED_BEHAVIOURS)
from ..targeting import RANGE_WHOLE_BOARD, RANGED_BOOL_FALSE, TargetingOptions
from ..targeting_rule import TargetingRule as TR
from ....dsl.base import Const
from ....dsl.effects import ExecutionContext
from ....entities.active_ability_type import ActiveAbilityType
from ....entities.effect_type import EffectType
from ....entities.triggered_ability_type import TriggeredAbilityType
from ....entities.behaviours import If, op_add, op_and
from ....entities.formulas import Count
from ....entities.selectors import (Cache, Caster, CanAddUnit, First, SortByDistance, Target, Tiles,
                                    Union, ValidNormalAttackTargets)
from ....entities.triggers import AmountIsGreater, IsAlive, Not, TriggerAnd, TriggerOr
from ....entities.traits.unit_trait import UnitTrait, has_trait
from ...components import StatsComponent
from ..targeting import valid_normal_attack_targets

if TYPE_CHECKING:
    from ...state import State

FACADE_ID = "SorcerousFacade"
# `AddEffect(0x4b4, ...)` du terme [1] — l'effet est porte par `entities/effects/loki/hits.py`
# (`SorcerousFacadeAdditionalHitsEffect`, canal #179).
SORCEROUS_FACADE_ADDITIONAL_HITS = int(EffectType.SorcerousFacade_AdditionalHits)   # 0x4b4 = 1204
# `TriggerAbilityDelayed(..., 0x49c, 3)` du terme [4].
SORCEROUS_FACADE_SWITCH = int(TriggeredAbilityType.SorcerousFacade_Switch)          # 0x49c = 1180


def sorcerous_facade_target_selector():
    """`sel` — le sous-arbre PARTAGE par `...SorcerousFacadeAbility$$GetTarget` et son
    `$$ExecuteBehaviour` (memes appels, memes arguments : un seul artefact natif) :

        Cache( First( SortByDistance( ValidNormalAttackTargets(Caster, CasterTile), Caster ), 1 ),
               true )

    - `ValidNormalAttackTargets` = les cibles LEGALES de l'attaque NORMALE du caster (cascade de
      ciblage native avec le masque `NORMAL_ATTACK_TARGETING_OPTIONS`, cf. `targeting.py`) ;
    - `SortByDistance(..., Caster)` : la reference est le selecteur **Caster**, donc la distance est
      prise a la position REELLE du caster (meme quirk d'ancrage que Chronometron/SavageEchoes) ;
    - `First(..., 1)` : le minimum ; `OrderBy` LINQ etant STABLE, l'ordre d'enumeration source
      tranche a distance egale (residu nomme : le port enumere dans l'ordre de `state.entities`) ;
    - `Cache(..., true)` : memoise -> les termes [2] et [3] lisent la MEME unite, meme si l'attaque
      a tue la cible entre les deux (le `KillDeadUnits` doit voir le cadavre, pas un ensemble
      recalcule).

    Une NOUVELLE instance par cast (comme tous les arbres du port) : le `Cache` est par-cast."""
    return Cache(First(SortByDistance(ValidNormalAttackTargets(Caster()), Caster())))


def sorcerous_facade_tree():
    """Arbre de `...SorcerousFacadeAbility$$ExecuteBehaviour` — MIRROR 1:1 (cf. l'en-tete du module).

    `AddEffect(source_ref=Caster())` = le 4e argument NATIF de la surcharge 6-args
    (`AddEffect(effectType, abilityState, source, targets, turns)`) ; `scale_from_source=True` parce
    que la magnitude de 1204 vient de `ConfigVar` resolus sur l'`AbilityStateReference` du caster
    (meme regime que FleshmetalGuns/CordClaw).
    `Union(Caster(), Target())` = le `TargetsSelector.op_Addition(Caster@0x48, Target@0x60)` du
    call-site : l'effet se pose sur le caster ET sur l'allie vise.
    `duration_rounds=1` = le `TurnsFromRounds(1)` litteral.

    `UseActiveAbility(Caster(), sel)` = la feuille deja portee, specialisee au dispatch d'ATTAQUE
    NORMALE (`UnitNormalAttackType(Caster)`) -> `AttackDamageOperation.execute`.

    `TriggerAbilityDelayed(Caster(), 1180, 3)` : le selecteur natif est `Owner@0x30`. Le port n'a pas
    de noeud `Owner` -- pour une ability ACTIVE, `Owner == Caster` (`entities_from_state` fait
    d'ailleurs retomber `ctx.owner` sur le caster), donc `Caster()` EST la lecture, pas une
    approximation de commodite."""
    sel = sorcerous_facade_target_selector()
    add_eff = AddEffect(SORCEROUS_FACADE_ADDITIONAL_HITS,
                        EffectType.SorcerousFacade_AdditionalHits.name,
                        Union(Caster(), Target()), duration_rounds=1,
                        scale_from_source=True, source_ref=Caster())
    attack = UseActiveAbility(Caster(), sel)
    kill = KillDeadUnits(Caster(), sel)
    switch = TriggerAbilityDelayed(Caster(), SORCEROUS_FACADE_SWITCH, unit_selection_type=3)
    return op_add(op_add(op_add(add_eff, attack), kill), switch)


def sorcerous_facade_switch_tree():
    """Arbre de `...SorcerousFacade_SwitchAbility$$CreateBehaviour` (triggered 1180) — MIRROR 1:1 :

        IfAlive( Caster,
                 KillDeadUnits(Killer(Target), Target) & If( IsAlive(Target)
                                                             | (NOT IsAlive(Target)
                                                                & IsCanAddUnit(Target)),
                                                             SwitchPosition(Caster, Target) ) )

    - `IfAlive(x, b)` -> `If(IsAlive(x), b)` (identite RELUE, cf. l'en-tete) ;
    - `Killer(Target)` (le TUEUR de la cible) est COLLAPSE en `Target()` : la feuille `KillDeadUnits`
      du port est un mirror STRUCTUREL qui ne re-mute rien (la mort est finalisee inline par
      l'attaque, cf. sa docstring) -- son 1er argument n'est donc jamais lu. Poser un `Killer` ici
      demanderait un noeud sans consommateur ;
    - `IsCanAddUnit(Target)` -> `AmountIsGreater(Count(CanAddUnit(Tiles(Target))), 0)`, le mirror
      exact de `DSLTriggers$$IsCanAddUnit` (relu) ;
    - la disjonction est ecrite TELLE QUELLE (elle se reduit logiquement a
      `IsAlive | IsCanAddUnit`, mais on porte la structure, pas sa simplification)."""
    can_add = AmountIsGreater(Count(CanAddUnit(Tiles(Target()))), Const(0))
    cond = TriggerOr(IsAlive(Target()),
                     TriggerAnd(Not(IsAlive(Target())), can_add))
    body = op_and(KillDeadUnits(Target(), Target()),
                  If(cond, SwitchPosition(Caster(), Target())))
    return If(IsAlive(Caster()), body)


def _run_switch(entities, ectx):
    """Callback du registre `TRIGGERED_ABILITY_DELAYED_BEHAVIOURS` : execute l'arbre de la triggered
    1180 dans le contexte du declencheur. Le natif PLANIFIE ce declenchement (service de triggers
    differes) ; le port l'execute INLINE, en queue d'arbre -- cf. la docstring de
    `TriggerAbilityDelayed` (meme collapse que MasterOfTheTutelaries)."""
    sorcerous_facade_switch_tree().execute(entities, ectx)
    sw = next((p for n, p in ectx.emitted if n == "SwitchPosition"), None)
    return {"ability_type": SORCEROUS_FACADE_SWITCH, "switch": sw}


TRIGGERED_ABILITY_DELAYED_BEHAVIOURS[SORCEROUS_FACADE_SWITCH] = _run_switch


class SorcerousFacadeAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.SorcerousFacadeAbility$$ExecuteBehaviour`
    (id 1100, `thousTzaangor` « Yazaghor »). Cast UNIT-TARGET sur un **ALLIE Psyker** : pose l'effet
    de coups additionnels 1204 sur le caster ET l'allie, porte une attaque NORMALE sur l'ENNEMI le
    plus proche, puis ECHANGE ses positions avec l'allie (triggered differee 1180).

    Retour : {ability, caster, target, effects, attack, switch, dsl}."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.SorcerousFacade)   # 1100
    ABILITY_ID = FACADE_ID

    # GATE DE CIBLE (#115). `IdunBattleLogic.Entities.Abilities.Active.Loki.SorcerousFacadeAbility$$
    # .ctor` prend la surcharge **FLAGS DIRECTS** de `IdunBattle.Core.Services.TargetingOptions$$
    # .ctor` -- ni preset statique recopie, ni surcharge PRESET+flags, donc AUCUN des deux pieges a
    # masque ne s'applique ici :
    #     TargetingOptions..ctor(&opts, isSelfCasting = 0,
    #                            range = <TargetingRange statics+0x48 = UseWholeBoard>,
    #                            forceMeleeTarget = 1 (RangedBool.False),
    #                            rules = 0x402, 0, 0)
    # `0x402` = `TargetIsFriendly | TargetMatchesDynamicRule` :
    #     TargetIsFriendly          -> PORTE (la cible doit etre un ALLIE ; refus sur tout ennemi).
    #     TargetMatchesDynamicRule  -> point d'extension `get_dynamic_invalid_target_reason` ; la
    #                                  regle de 1100 (`HasTrait(target, 0x3ea = Psyker)` + « le
    #                                  caster peut porter son attaque normale depuis les tuiles de
    #                                  cast ») n'est PAS portee -> degradation PERMISSIVE.
    # PORTEE = whole board : `get_range` ne pose AUCUN gate de distance. CONFIRME LIVE (#27-4e) :
    # `abilityTargets(1100)` rend l'allie a distance 6 du caster.
    # ⚠ Ce masque etait dans `TARGETING_OPTIONS_UNPORTED` (pose par #217) ; il MIGRE ici avec la face
    # COMBAT, comme l'exige le contrat de DISJONCTION des deux sources
    # (`tests/engine/runner/test_targeting_options_sources.py`).
    TARGETING_OPTIONS = TargetingOptions(rules=TR.TargetIsFriendly | TR.TargetMatchesDynamicRule,
                                         self_cast=False, range=RANGE_WHOLE_BOARD,
                                         force_melee_target=RANGED_BOOL_FALSE)

    def get_dynamic_invalid_target_reason(self, state: "State", caster_id: int,
                                          target_id: Optional[int]) -> int:
        """`...SorcerousFacadeAbility$$GetDynamicInvalidTargetReason` — MIRROR du decompile, verbatim :

            if (UnitExtensions.HasTrait(target, 0x3ea = Psyker)) {
                if (battleQuery.<slot 0x40>(caster, casterTiles, GetNormalAttackType(caster)))
                    return 0;
            }
            return 2;                       # TargetingRule.TargetMatchesDynamicRule

        DEUX conjonctions, et la seconde est celle qu'on n'aurait pas devinee du texte i2 :
          1. la cible porte le trait **Psyker** (0x3ea = 1002) ;
          2. le caster peut attaquer QUELQUE CHOSE a l'attaque normale depuis ses tuiles de cast --
             le slot 0x40 d'`IBattleQuery` est
             `IdunBattle.Core.Services.BattleQuery$$HasValidTargets(caster, casterTiles, type)`
             -- TROIS arguments, comme le call-site ci-dessus ;
             `IdunBattle.Core.Services.BattleQuery$$CanAttackAnyUnitFromAnyTileWithAnyAbility` est
             au slot 0x38 et ne prend QUE l'unite. La semantique est la meme ici, l'appel etant
             restreint a l'`ActiveAbilityType` de l'attaque normale du caster. Mirror : l'ensemble
             `valid_normal_attack_targets(state, caster)` est NON VIDE -- exactement la source que
             `sel` consomme dans l'arbre (un seul port de la cascade, pas deux).

        MESURE qui l'a rendue obligatoire (`probe_287_facade_combat.py --far-foes`) : les deux
        ennemis hors de portee -> le natif rend `ok=True` et NE MUTE RIEN (refus silencieux, cf.
        case-111), la ou le port sans cette regle posait l'effet 1204 sur deux unites ET echangeait
        les positions. Une degradation « permissive » qui MUTE l'etat n'est pas benigne.

        ⚠ Pas de recursion : `valid_normal_attack_targets` evalue la cascade avec le masque de
        l'ATTAQUE NORMALE (`_NormalAttackTargeting`), jamais avec celui de 1100."""
        if target_id is None:
            return int(TR.TargetMatchesDynamicRule)
        e = state.get_entity(int(target_id))
        sc = e.get_component(StatsComponent) if e is not None else None
        traits = getattr(sc.ctx, "traits", None) if sc is not None else None
        if not has_trait(traits or [], UnitTrait.Psyker):          # HasTrait(target, 0x3ea)
            return int(TR.TargetMatchesDynamicRule)
        if not valid_normal_attack_targets(state, int(caster_id)):  # slot 0x40 d'IBattleQuery
            return int(TR.TargetMatchesDynamicRule)
        return 0

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None or state.get_entity(caster_id) is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        sorcerous_facade_tree().execute(entities_from_state(state, caster_id, target_id), ectx)
        effects = [p for n, p in ectx.emitted if n == "AddEffect"]
        atk = next((p for n, p in ectx.emitted if n == "UseActiveAbility"), None)
        sw = next((p for n, p in ectx.emitted if n == "SwitchPosition"), None)
        return {"ability": self.ABILITY_ID, "caster": caster_id, "target": target_id,
                "effects": effects, "attack": atk, "switch": sw, "dsl": True}
