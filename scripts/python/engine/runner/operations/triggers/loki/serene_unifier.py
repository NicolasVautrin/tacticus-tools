"""`IdunBattleLogic.Entities.Abilities.Triggered.Loki.SereneUnifierAbility` -- le POSEUR du cycle a
trois temps du passif `SereneUnifier` (`TriggeredAbilityType` 0x479 = 1145) de `tauAunShi`.

CE QUI MANQUAIT (#462-r4e-o-r2-r1-r1). Les EFFETS posés étaient déjà portés et consommés
(`SereneUnifierSenseOfStoneEffect` 0x491 = 1169 dans `entities/effects/loki/damage_reduction.py`,
`SereneUnifierStormOfFireEffect` 0x493 = 1171 dans `entities/effects/loki/serene_unifier.py`) ; ce
qui n'existait pas, c'est la ROTATION qui les pose. Conséquence MESURÉE : un rejeu offline
multi-tours gardait indéfiniment l'effet SEEDÉ au chargement (`SereneUnifierSenseOfStone`, round 1)
et ne matérialisait JAMAIS les deux autres -- le natif, lui, passait à
`SereneUnifierStormOfFire` (round 3, `+582 Damage`) au tour suivant. C'est ce qui rendait
`[214, 281, 255, 227, 286]` là où le natif rend `[1044, 886, 70, 0, 0]`.

⚠ CE N'EST PAS « UN COMPTEUR DE ROUND QUE LE PORT N'AVANCE PAS ». Le compteur existe et il est
déjà avancé (`State.turn_counts`, mirror `TurnComponent+0x38`, bumpé par
`IdunBattle.Operations.StartTurnOperation$$Execute` -> `turnflow.StartTurnOperation.execute`). Ce
qui manquait est son CONSOMMATEUR.

================================================================================================
RE (décompilé ghidra, build `rnca9r7q6c`) -- DEUX fonctions natives NOMMÉES
================================================================================================

## 1. `...SereneUnifierAbility$$CreateTrigger`

    On(0x13 = TurnStart_Other = 19, ownerNeedsToBeAlive = 1)
  & <DSLTriggers+0x28 = IsTurnOf(Owner)>
  & get_OwnerIsCaster

MÊME patron que `...LivingMetalRepairAbility$$CreateTrigger` (#203/case-310) et
`...CursedPlagueBellMovementAbility$$CreateTrigger` (case-224) -- donc MÊME vecteur porté,
`turn_start_other_triggers` (`dispatch/turn.py`), émis par `StartTurnOperation.execute`.
`<DSLTriggers+0x28>` est identifié `IsTurnOf(Owner)` par `docs/rl/case-366-r1-turnof-all.md` §2 ;
sa porte est `ev.player_id == OwnerComponent.player`.

⚠ Le vecteur `On(0x13)` n'est PAS celui de `FleshMetalGunsAbility` (`On(0x16 =
TurnStart_Actions)`), qui porte pourtant l'autre cycle `Modulo(..., 3, k)` du port. Les deux
events sont émis par le MÊME `StartTurnOperation$$Execute`, dans la séquence
0x12 -> 0x13 -> 0x14 -> 0x15 -> 0x16, donc l'ordre relatif compte : SereneUnifier pose ses effets
AVANT les triggers `On(0x16)`.

## 2. `...SereneUnifierAbility$$CreateBehaviour(abilityState, triggerType)`

Cibles (le MÊME sélecteur pour les six branches) :

    adj     = DSLSelectors.AdjacentFriends(Self@0x48, unique = 1, unitSelectionType = 3)
    surr    = DSLSelectors.SurroundingFriends(Self@0x48,
                                              range = DSLFormulas.ConfigConst(0x16 = range),
                                              unique = 1, unitSelectionType = 3)
    targets = (adj + Self@0x48)
            + DSLSelectors.UnitsFromFaction(surr op_Subtraction adj,
                                            Enum.ToString(UnitFaction = 9) = "Tau",
                                            unitSelectionType = 3)

`<DSLSelectors+0x48>` = **Caster** (identité établie par `case-305`, `admec.py` : `factory+0x160
Caster` == `DSLSelectors+0x48`) ; pour un triggered, Owner == Caster == Self. Aun'Shi EST dans ses
propres cibles -- c'est le seul cas où source == porteur, donc le seul où la re-dérivation de
magnitude d'un `ConfigVar` est EXACTE (cf. `entities/effects/loki/serene_unifier.py`).

Phase (le MÊME prédicat pour les six branches, seul le reste attendu change) :

    k = DSLFormulas.PlayerTurnsStarted(Self@0x48)   # UnitsPlayerTurnsStartedFormula -> turn_counts
    Modulo(k, Direct(3), Direct(<reste>))           # ModuloAbilityTrigger : (a mod b) == c

Chaîne `AbilityBehaviour.op_Addition` (l'ORDRE est celui du décompilé) :

    Nothing()
    + If( Modulo(k,3,0), AddStaticStatModifierEffect(targets, 0x493 = 1171, stat = 0 ATTACK,
                                                     ConfigVar(8 = extraDmg, abilityState),
                                                     TurnsFromRounds(1), isHidden = 0) )
    + If( Modulo(k,3,1), AddEffect(0x491 = 1169, AbilityStateReference, Self@0x48, targets,
                                   TurnsFromRounds(1)) )
    + If( Modulo(k,3,2), AddStaticStatModifierEffect(targets, 0x492 = 1170, stat = 1 MOVEMENT,
                                                     ConfigConst(0xe = extraMovement),
                                                     TurnsFromRounds(1), isHidden = 0) )
    + If( Modulo(k,3,0), AddEffect(0x49a = 1178 StormOfFire_Visual,  ..., TurnsFromRounds(1)) )
    + If( Modulo(k,3,1), AddEffect(0x498 = 1176 SenseOfStone_Visual, ..., TurnsFromRounds(1)) )
    + If( Modulo(k,3,2), AddEffect(0x499 = 1177 ZephyrsGrace_Visual, ..., TurnsFromRounds(1)) )

**AUCUN `RemoveEffect`** -- contrairement à `FleshMetalGunsAbility`, qui retire ses trois effets
avant de reposer celui du tour. Ici c'est la DURÉE `TurnsFromRounds(1)` qui fait le travail, et
c'est le tick d'`IdunBattle.Operations.EndTurnOperation$$RefreshEffects` qui la consomme.
Corollaire pour le port : un rejeu offline qui n'exécute pas `EndTurnOperation` garde l'effet de la
phase précédente ET no-ope la re-pose (`AddEffectOperation` refuse un effet déjà présent) -- les
deux moitiés du même défaut.

================================================================================================
FORME DU PORT (frontière #149)
================================================================================================
L'artefact natif est un `CreateBehaviour` -> ARBRE DSL, construit de nœuds EXISTANTS. Les prédicats
du `CreateTrigger` (`On` + `IsTurnOf(Owner)` + `OwnerIsCaster`) sont collapsés impérativement dans
`matches`, comme LivingMetal / CursedPlagueBell / FleshmetalGuns.

Les DEUX feuilles natives sont portées par les DEUX voies déjà en place, et le choix est dicté par
l'existence d'une CLASSE D'EFFET portée -- même arbitrage que
`anvil_shield.anvil_shield_frozen_attacker_advantage_tree`, qui décompose lui aussi un
`AddStaticStatModifierEffect` natif en `AddEffect` + part DATA de la classe :

  * 1171 et 1169 ONT leur classe (`SereneUnifierStormOfFireEffect` / `SereneUnifierSenseOfStoneEffect`)
    -> feuille `AddEffect` + `scale_from_source=True` : la magnitude est la part DATA de la classe
    (`ConfigVar(8 = extraDmg)` indexé par le niveau PASSIF du caster x son multiplier de rareté),
    exécutée par `AddEffectOperation._apply_stat_mods`. C'est AUSSI la voie du SEED live, donc pose
    offline et capture live matérialisent la MÊME classe ;
  * 1170 n'a PAS de classe portée -> feuille `AddStaticStatModifierEffect`, qui porte elle-même le
    couple (statType, montant). Le montant est la constante gameconfig `extraMovement`
    (`AbilityConstantType.extraMovement`), lue comme le fait `astramilitarum.py` pour
    `AbilityConstantType.range` -- `ConfigConst` du port a besoin d'un `ctx.config` que le contexte
    d'un triggered de runner ne porte pas.

Les trois `*_Visual` sont posés comme le natif les pose. Aucune classe ne leur est déclarée : ils se
matérialisent en `BaseEffect` nu, INERTE (aucun stat-mod, aucun trigger) -- ce qui est exactement
leur rôle natif (`NoneEffect`, cf. `docs/rl/case-366...` §3.2). Les OMETTRE aurait été une
divergence d'état vis-à-vis du seed live, qui les publie sur le même canal que les trois autres.
"""
from __future__ import annotations

from typing import Optional

from ....state import State
from ....components import OwnerComponent, UnitComponent
from ....abilities.behaviours import (AddEffect, AddStaticStatModifierEffect,
                                      entities_from_state)
from .....entities.behaviours import op_add, If as IfBehaviour
from .....entities.formulas import PlayerTurnsStarted
from .....entities.selectors import (Caster, AdjacentFriends, SurroundingFriends,
                                     UnitsFromFaction, Sub, Union)
from .....entities.triggers import Modulo
from .....entities.effect_type import EffectType
from .....entities.triggered_ability_type import TriggeredAbilityType
from .....entities.stats import StatType
from .....entities.ability_constant_type import AbilityConstantType
from .....dsl.base import Const
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from ..base import TriggeredAbility, TriggerEvent

_ABILITY_ID = "SereneUnifier"                    # cle gameconfig (passiveAbilities de `tauAunShi`)
_ON_TURN_START_OTHER = int(EventTriggerType.TurnStart_Other)      # `On(0x13 = 19)`
_CYCLE_LEN = 3                                   # `Direct(3)`, le diviseur du `Modulo`
_TAU_FACTION = "Tau"                             # `Enum.ToString(UnitFaction = 9)`
# `AdjacentFriends(Self, unique = 1, unitSelectionType = 3)` : le natif ne passe PAS de rayon a
# cette surcharge -- le port a `radius = Const(1)` en defaut, c'est le meme anneau.
_ADJACENT_RADIUS = 1
# `DSLSelectors$$UnitsFromFaction(..., 3)` / `AdjacentFriends(..., 3)` : `unitSelectionType` = 3 =
# OnlyAliveAndTargetable. Les selecteurs du port filtrent deja les morts -- argument NOMME, pas porte.
_UNIT_SELECTION_TYPE = 3

# `ConfigConst(0x16 = range)` -> gameconfig `SereneUnifier.constants.range` (= 2 au build courant).
CONST_RANGE = AbilityConstantType.range                  # GetNumberConstant(0x16)
# `ConfigConst(0xe = extraMovement)` -> `SereneUnifier.constants.extraMovement` (= 1).
CONST_EXTRA_MOVEMENT = AbilityConstantType.extraMovement  # GetNumberConstant(0xe)

# (reste du modulo, effectType, nom capte) des TROIS phases PORTEUSES d'un effet reel.
# L'ORDRE est celui du decompile : k = 0 -> ATTAQUE, k = 1 -> DEFENSE, k = 2 -> MOUVEMENT.
PHASE_STORM_OF_FIRE = 0        # 0x493 = 1171, stat 0 ATTACK, ConfigVar(8 = extraDmg)
PHASE_SENSE_OF_STONE = 1       # 0x491 = 1169, classe bespoke (reduction de degat)
PHASE_ZEPHYRS_GRACE = 2        # 0x492 = 1170, stat 1 MOVEMENT, ConfigConst(0xe = extraMovement)

# Les trois `*_Visual`, dans l'ordre du decompile, apparies a la MEME phase que leur effet reel.
VISUAL_CYCLE = (
    (PHASE_STORM_OF_FIRE, int(EffectType.SereneUnifierStormOfFire_Visual)),    # 0x49a = 1178
    (PHASE_SENSE_OF_STONE, int(EffectType.SereneUnifierSenseOfStone_Visual)),  # 0x498 = 1176
    (PHASE_ZEPHYRS_GRACE, int(EffectType.SereneUnifierZephyrsGrace_Visual)),   # 0x499 = 1177
)

# `TurnsFromRounds(1)` -- le port convertit rounds -> tours dans `_resolve_duration`.
_DURATION_ROUNDS = 1


def _ability_const(key) -> int:
    """`AbilityConfiguration$$GetNumberConstant(config, <key>)` = `SereneUnifier.constants[<nom>]`.

    Lecture gameconfig DIRECTE (meme voie qu'`astramilitarum.py` pour `AbilityConstantType.range`) :
    le noeud `ConfigConst` du port lit `ctx.config`, un `AbilityConfiguration` que le contexte d'un
    triggered de runner ne porte pas. La cle est le NOM du membre d'enum, jamais son ordinal."""
    import gameconfig as GC
    consts = (GC.ability(_ABILITY_ID) or {}).get("constants") or {}
    return int(consts.get(getattr(key, "name", str(key))) or 0)


def serene_unifier_targets():
    """MIRROR 1:1 du sélecteur de cibles de `...SereneUnifierAbility$$CreateBehaviour` (cf. en-tete) :

        (AdjacentFriends(Self) + Self) + UnitsFromFaction(SurroundingFriends(Self, range) - AdjacentFriends(Self), "Tau")

    = self + amis adjacents + amis T'au dans le disque de rayon `range` (centre exclu). Les deux
    `AdjacentFriends` du natif sont le MEME objet (`pvVar2`, reutilise par l'`op_Subtraction`) --
    le port en construit deux instances equivalentes (selecteurs SANS etat)."""
    adj = AdjacentFriends(Caster(), Const(_ADJACENT_RADIUS))
    surr = SurroundingFriends(Caster(), Const(_ability_const(CONST_RANGE)))
    tau = UnitsFromFaction(Sub(surr, AdjacentFriends(Caster(), Const(_ADJACENT_RADIUS))),
                           _TAU_FACTION)
    return Union(Union(adj, Caster()), tau)


def serene_unifier_tree():
    """MIRROR 1:1 de `...SereneUnifierAbility$$CreateBehaviour` : les SIX `If(Modulo(...))` dans
    l'ordre du decompile, chaines par `AbilityBehaviour.op_Addition`.

    `PlayerTurnsStarted(Self)` = `State.turn_counts[<joueur du porteur>]` (`TurnComponent+0x38`),
    **PAS** `UnitTurnsStarted` (`UnitComponent+0x58`, stat 0xc) que lit le cycle de FleshmetalGuns.
    Le compteur est incremente par `StartTurnOperation` AVANT l'emission de `On(0x13)` -> au 1er
    tour d'Aun'Shi il vaut deja 1, donc la phase 1 (`SenseOfStone`) est celle du round 1. C'est ce
    que montre tout seed frais, et ce qui fait de la phase 0 (`StormOfFire`) celle du round 3."""
    targets = serene_unifier_targets()
    k = PlayerTurnsStarted(Caster())
    tree = None

    def _chain(node):
        return node if tree is None else op_add(tree, node)

    # k = 0 -> `AddStaticStatModifierEffect(targets, 0x493, stat 0 ATTACK, ConfigVar(8 = extraDmg),
    #          TurnsFromRounds(1))` -- decompose en `AddEffect` + part DATA de la classe portee.
    tree = _chain(IfBehaviour(
        Modulo(k, Const(_CYCLE_LEN), Const(PHASE_STORM_OF_FIRE)),
        AddEffect(int(EffectType.SereneUnifierStormOfFire),
                  EffectType.SereneUnifierStormOfFire.name, targets,
                  duration_rounds=_DURATION_ROUNDS, scale_from_source=True)))
    # k = 1 -> `AddEffect(0x491, AbilityStateReference, Self, targets, TurnsFromRounds(1))`.
    tree = _chain(IfBehaviour(
        Modulo(k, Const(_CYCLE_LEN), Const(PHASE_SENSE_OF_STONE)),
        AddEffect(int(EffectType.SereneUnifierSenseOfStone),
                  EffectType.SereneUnifierSenseOfStone.name, targets,
                  duration_rounds=_DURATION_ROUNDS, scale_from_source=True)))
    # k = 2 -> `AddStaticStatModifierEffect(targets, 0x492, stat 1 MOVEMENT,
    #          ConfigConst(0xe = extraMovement), TurnsFromRounds(1))` -- aucune classe portee pour
    #          1170, donc la feuille du port, qui porte elle-meme (statType, montant).
    tree = _chain(IfBehaviour(
        Modulo(k, Const(_CYCLE_LEN), Const(PHASE_ZEPHYRS_GRACE)),
        AddStaticStatModifierEffect(targets, int(EffectType.SereneUnifierZephyrsGrace),
                                    int(StatType.MOVEMENT),
                                    Const(_ability_const(CONST_EXTRA_MOVEMENT)),
                                    name=EffectType.SereneUnifierZephyrsGrace.name,
                                    duration_rounds=_DURATION_ROUNDS)))
    # Les trois `*_Visual`, dans l'ordre du decompile (0x49a, 0x498, 0x499) -- `NoneEffect` natifs,
    # `BaseEffect` nus cote port : materialises, INERTES.
    for rest, eff_type in VISUAL_CYCLE:
        tree = _chain(IfBehaviour(
            Modulo(k, Const(_CYCLE_LEN), Const(rest)),
            AddEffect(eff_type, EffectType(eff_type).name, targets,
                      duration_rounds=_DURATION_ROUNDS)))
    return tree


class SereneUnifierRotationAbility(TriggeredAbility):
    """`SereneUnifierAbility` (`$$CreateTrigger` = `On(0x13 = TurnStart_Other) & IsTurnOf(Owner) &
    get_OwnerIsCaster` ; `$$CreateBehaviour` = les six `If(Modulo(PlayerTurnsStarted(Self), 3, k))`)
    -- au DEBUT DU TOUR d'Aun'Shi (`tauAunShi`), pose sur lui-meme, ses amis adjacents et les amis
    T'au a <= `range` l'effet de la phase courante du cycle a trois temps.

    Les effets poses sont deja portes : 1169 (`damage_reduction.py`), 1171 (`serene_unifier.py`) ;
    1170 passe par la feuille generique. Les trois `*_Visual` sont inertes."""
    event_id = _ON_TURN_START_OTHER
    # `BaseTriggeredAbility$$Execute` ecrit `AbilityOrEffect(this.Id)` avant le behaviour -> c'est ce
    # que lit `TriggeringAbilityIs`. Id = `TriggeredAbilityType.SereneUnifier` (0x479 = 1145).
    TRIGGERED_ABILITY_ID = int(TriggeredAbilityType.SereneUnifier)     # 0x479 = 1145

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        """`<DSLTriggers+0x28 = IsTurnOf(Owner)>` & `get_OwnerIsCaster` -- le tour qui demarre est
        celui du proprietaire. `On(0x13, ownerNeedsToBeAlive = 1)` : le porteur doit etre VIVANT
        (`<DSLTriggers+0x20>` = `OwnerIsAliveAbilityTrigger`, cf. case-224 §volet ATTAQUE)."""
        e = state.get_entity(self.owner_id)
        if e is None:
            return False
        uc = e.get_component(UnitComponent)
        if uc is not None and not uc.alive:            # `On(..., ownerNeedsToBeAlive = 1)`
            return False
        oc = e.get_component(OwnerComponent)
        return oc is not None and ev.player_id is not None and oc.player == int(ev.player_id)

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        if state.effects is None:
            return None                                # pas d'EffectsState -> pose impossible
        ectx = ExecutionContext(state=state, rng=state.rng)
        # `entities_from_state(state, owner)` : Owner == Caster == Self pour un triggered (le natif
        # lit les trois dans le meme slot `<DSLSelectors+0x48>`). Pas de cible d'evenement.
        serene_unifier_tree().execute(entities_from_state(state, self.owner_id, None), ectx)
        placed = [(p.get("effect_type"), p.get("target"))
                  for n, p in ectx.emitted if n == "AddEffect" and p.get("placed")]
        stat_mods = [(p.get("effect_type"), p.get("unit"))
                     for n, p in ectx.emitted if n == "AddStaticStatModifierEffect"]
        if not placed and not stat_mods:
            return None
        return {"ability": _ABILITY_ID, "unit": int(self.owner_id),
                "player_turns_started": state.turn_counts.get(int(ev.player_id), 0),
                "placed": placed, "stat_mods": stat_mods}
