"""`VengeanceForTheOmnissiah` (`TriggeredAbilityType` 0x512 = **1298**), passif du
`admecSmnTechpriest` << Tech-Priest Enginseer >> (SUMMON d'`InvocationOfMachineVengeance`) et de son
jumeau npc `admecNpc2Techpriest` -- canal **T** (`ABILITY_TRIGGERS`). #1071.

i2 : << Whenever an adjacent friendly Mechanical is defeated, the Tech-Priest Enginseer gains 1 level
of Machine Vengeance. >>

C'est le POSEUR de la pile que son co-passif `OmnissiahsBlessing` (1299, #1023) TRANSFERE : les deux
vivent sur la MEME unite, et jusqu'ici seul le transfert etait porte -- la pile ne pouvait donc
naitre sur ce porteur que par une ability de Belisarius. Ce module ferme la boucle.

================================================================================================
LES DEUX CORPS, LUS VERBATIM SUR `rnca9r7q6c`
================================================================================================

Slots lus : `DSLSelectors+0x30 Owner`, `+0x60 Target` ; `DSLFactory+0x78 Behaviors`,
`+0x80 Formulas`, `+0x88 Triggers`, `+0x90 Selectors`.

## `IdunBattleLogic.Entities.Abilities.Triggered.Loki.VengeanceForTheOmnissiahAbility$$CreateTrigger`

    On( 0x36 = 54 UnitDefeated, ownerNeedsToBeAlive: 1 )
      op_BitwiseAnd  AreFriends( Owner@+0x30, Target@+0x60,
                                 comparisonType = 0, anyEntity = false )
      op_BitwiseAnd  IsAdjacent( Owner@+0x30, Target@+0x60, selectionType = 2 )
      op_BitwiseAnd  IsMechanical( Target@+0x60, selectionType = 2 )

## `...VengeanceForTheOmnissiahAbility$$CreateBehaviour(abilityState, triggerType)`

    lvl = DSLFormulas.ConfigConst( 0x73 = AbilityConstantType.effectLevel, this+0x20 )
    return DSLBehaviors.AddEffectOrIncreaseLevel( 0x555 = 1365 MachineVengeance,
                                                  AbilityStateReference,
                                                  source  = Owner@+0x30,
                                                  targets = Owner@+0x30,
                                                  level   = lvl, maxLevel = NULL )

⚠ `source` ET `targets` sont **le MEME slot** `+0x30` -- le decompile lit deux fois
`*(<Selectors> + 0x30)`. Ce n'est pas une coquille de transcription : le porteur est a la fois la
source de l'effet et sa cible, contrairement a `OmnissiahsBlessing` qui vise `Target@+0x60`.

================================================================================================
QUATRE LECTURES QUI NE SE DEVINENT PAS
================================================================================================

1. **`ConfigConst` ICI EST UNE NUMBER-CONSTANT, PAS UNE VARIABLE DE NIVEAU -- et c'est LU.**
   La surcharge appelee est `IdunBattleLogic.Entities.DSLFormulas$$ConfigConst(this, constantType,
   config)` (TROIS arguments), qui alloue
   `IdunBattle.Entities.Formulas.ConfigAmount$$.ctor(this, config, constantType)` -- l'unique
   surcharge du ctor a trois parametres. Elle ecrit `config@+0x10` et
   `Nullable<AbilityConstantType>(constantType)@+0x38`, et **ne touche PAS `+0x30`**. Or
   `IdunBattle.Entities.Formulas.ConfigAmount$$Calculate` bifurque exactement la-dessus :

       if (HasValue(this+0x30))  return AbilityConfiguration.GetVariableForLevel(config,
                                            <+0x30>, abilityState.Level, 0);   // PER-NIVEAU
       if (HasValue(this+0x38))  return AbilityConfiguration.GetNumberConstant(config, <+0x38>);
       return 0;

   Le niveau d'ability n'entre donc JAMAIS dans cette lecture. **Consequence de harnais, et c'est
   la raison pour laquelle cet item est confrontable malgre #1049-r1** : le defaut connu
   d'`--explicit-stats` (un `AbilityState` annonce `(niveau 1, mult 100)` que `unitAbilityStates`
   contredit `(65, 200)`) ne peut pas fausser une valeur qui ne depend NI du niveau NI du
   multiplicateur. Le gameconfig confirme la forme : `constants = {effectLevel: 1}`, et
   `variables` est **VIDE**.
   Le noeud `entities/formulas.py::ConfigConst` du port ne convient PAS ici -- il appelle
   `get_variable_for_level`, donc il fait le travail de `ConfigVar` (reserve deja ecrite dans ce
   fichier). On lit la constante au gameconfig, exactement comme
   `triggers/loki/savior_protocols.py::savior_chance`.

2. **`IsMechanical` porte sur la CIBLE (le MORT), jamais sur le porteur** -- `IsMechanical(*(<Selectors>
   + 0x60), 2)`. Le passif ne lit donc AUCUN trait, AUCUNE stat et AUCUNE arme de son propre porteur :
   ses trois conjoints ne consultent que la RELATION (equipe, adjacence) et le trait de la victime.
   C'est ce qui rend le porteur substituable, et c'est verifie et non suppose.
   `DSLTriggers$$IsMechanical` n'alloue AUCUN predicat dedie : il compose
   `AmountIsEqualOrGreater(Count(MechanicalUnits(unit, selectionType)), Direct(1))` -- d'ou le
   mirror `entities/triggers.py::is_mechanical`, et non un `HasTrait(Mechanical)` ecrit a la main
   (`UnitExtensions$$IsMechanical` est une DISJONCTION de trois traits : `Mechanical` 5,
   `LivingMetal` 1000, `Vehicle` 1029).

3. **Le `2` d'`IsAdjacent` et celui d'`IsMechanical` sont des `UnitSelectionType`, pas des rayons.**
   `UnitSelectionType.OnlyTargetable` = `NOT HasFlag(unit, 0x11 = UnitFlag.Untargetable)` --
   le seul filtre que le natif applique ici, et il ne teste PAS `IsAlive`. Le regime est
   litteralement celui de `BattleFatigueAbility$$CreateTrigger` (`IsAdjacent(self@+0x30,
   dying@+0x60, 2)`), l'autre passif du depot qui ecoute une mort ADJACENTE : le mort garde ses
   tuiles, donc l'adjacence se lit sur le cadavre. Un `IsAlive` ajoute ici REFUSERAIT tout, et
   serait l'exact inverse du natif.

4. **`AddEffectOrIncreaseLevel` avec `maxLevel = NULL` -> AUCUN cap.** Le plafond de
   `MachineVengeance` qui existe ailleurs (`ArcScourgeAbility$$GetDynamicInvalidCasterReason`
   refuse le cast au-dela d'`effectLevel_2` = 9) est un gate de CASTER sur une AUTRE ability : il
   ne borne pas cette accumulation. ⚠ `AbilityConstantType.effectLevel` = **115** et
   `effectLevel_2` = **118** : deux constantes distinctes, homonymes proches.

================================================================================================
CRITERE DE L'EMETTEUR
================================================================================================
`On(0x36 = 54 UnitDefeated)` est emis par
`triggers/dispatch/move_death.py::unit_defeated_triggers`, avec `actor_id = le TUEUR` et
`target_id = le MORT`. L'inscription n'est donc PAS un registered-but-dead : le vecteur porte deja
`AmbushSummonAbility`, `CosmicHorror`, `EmpyricAmbush`, `TrophyTaker`, `RedRampage`.

⚠ Les conjoints de ce passif se lisent TOUS sur `Target@+0x60` = le MORT ; `actor_id` (le tueur)
n'entre dans AUCUN d'eux -- il n'y a ni `OwnerIsActor` ni `OwnerIsTarget` dans le `CreateTrigger`.
Le porteur peut donc gagner sa pile sur une mort qu'il n'a pas causee, et meme sur SA PROPRE mort
d'un allie tue par l'ennemi. C'est ce que dit le decompile, pas une extrapolation.
"""
from __future__ import annotations

from typing import Optional

from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.ability_constant_type import AbilityConstantType
from .....entities.effect_type import EffectType
from .....entities.selectors.accessors import Owner, Target
from .....entities.triggered_ability_type import TriggeredAbilityType
from .....entities.triggers import AreFriends, IsAdjacent, TriggerAnd, is_mechanical
from .....entities.unit_selection_type import UnitSelectionType
from .....entities.unit_team_selection_type import UnitTeamSelectionType
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.effects import add_effect_or_increase_level
from ....components import UnitComponent
from ....state import State
from ..base import TriggeredAbility, TriggerEvent

#: Cle du registre `ABILITY_TRIGGERS` = le NOM gameconfig de la `passiveAbilities` porteuse.
VENGEANCE_FOR_THE_OMNISSIAH = "VengeanceForTheOmnissiah"
#: `AbilityOrEffect(0x512)` de cette triggered-ability.
VENGEANCE_FOR_THE_OMNISSIAH_ID = int(TriggeredAbilityType.VengeanceForTheOmnissiah)   # 0x512 = 1298

#: `On(0x36 = 54 UnitDefeated, ownerNeedsToBeAlive = 1)`.
_ON_UNIT_DEFEATED = int(EventTriggerType.UnitDefeated)                    # 0x36 = 54

#: L'effet POSE/INCREMENTE. Le MEME id que la pile qu'`OmnissiahsBlessing` (1299) transfere et
#: qu'`ArcScourge` empile (`runner/abilities/admec.py::AS_MACHINE_VENGEANCE`). L'ordinal 1365 nomme
#: AUSSI `TriggeredAbilityType.MachineVengeance` : c'est le NOM et l'enum qui tranchent, jamais
#: l'entier.
MACHINE_VENGEANCE = int(EffectType.MachineVengeance)                      # 0x555 = 1365
MACHINE_VENGEANCE_NAME = EffectType.MachineVengeance.name

#: 3e argument d'`IsAdjacent` et 2e d'`IsMechanical` : un `UnitSelectionType`, PAS un rayon.
#: `OnlyTargetable` = `NOT HasFlag(unit, 0x11 = Untargetable)` -- aucun test `IsAlive` (lecture 3).
_SELECTION = int(UnitSelectionType.OnlyTargetable)                        # 2
#: `comparisonType = 0` du call-site `AreFriends` = `UnitTeamSelectionType.ByCurrentTeam`.
_TEAM_SELECTION = int(UnitTeamSelectionType.ByCurrentTeam)                # 0
#: `ConfigConst(0x73, config)` -> `AbilityConfiguration$$GetNumberConstant` (lecture 1).
EFFECT_LEVEL_CONSTANT = AbilityConstantType.effectLevel                   # 0x73 = 115


def vengeance_effect_level() -> int:
    """`DSLFormulas$$ConfigConst(0x73 = AbilityConstantType.effectLevel, this+0x20)` =
    `gameconfig.abilities.VengeanceForTheOmnissiah.constants.effectLevel`.

    Lue AU GAMECONFIG, pas par le noeud `entities/formulas.py::ConfigConst` : ce noeud-la appelle
    `get_variable_for_level`, donc il mirroire `ConfigVar`, pas `ConfigConst`. La surcharge native
    reellement appelee ici est celle qui ne renseigne QUE le slot `constantType@+0x38`, et
    `ConfigAmount$$Calculate` y prend la branche `GetNumberConstant` -- HORS niveau (lecture 1 de
    l'en-tete). MEME arbitrage, au MEME endroit, que
    `triggers/loki/savior_protocols.py::savior_chance`.

    Constante absente ou illisible -> 0, ce qui rend le behaviour inerte (increment de zero) : le
    natif, lui, LEVE sur cle absente -- divergence deja assumee par le depot pour toute lecture de
    config (cf. la reserve de `entities/formulas.py::ConfigConst`)."""
    import gameconfig as GC                # lazy : `engine/**` ne depend pas du chargeur gameconfig
    v = ((GC.ability(VENGEANCE_FOR_THE_OMNISSIAH) or {}).get("constants") or {}).get(
        EFFECT_LEVEL_CONSTANT.name)
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def vengeance_trigger_tree():
    """`VengeanceForTheOmnissiahAbility$$CreateTrigger`, moins le seul volet `On(0x36)` que porte le
    DISPATCH -- les TROIS conjoints restants, dans l'ORDRE du decompile :

        AreFriends( Owner@+0x30, Target@+0x60, comparisonType = 0, anyEntity = false )
          op_BitwiseAnd  IsAdjacent( Owner@+0x30, Target@+0x60, 2 )
          op_BitwiseAnd  IsMechanical( Target@+0x60, 2 )

    Les trois sont des noeuds DSL deja portes 1:1 -- on ne recable a la main NI la comparaison
    d'equipe (`AreFriends` resout chaque operande a UNE entite et rend faux sur un operande nul),
    NI l'adjacence (`IsAdjacent` porte le quantificateur UNIVERSEL, les empreintes completes, la
    porte d'elevation et le filtre `selectionType` sur LES DEUX selecteurs), NI le predicat
    mecanique (`is_mechanical` est la composition `Count(MechanicalUnits(.)) >= 1`, dont la
    disjonction de trois traits vit dans `selectors/units.py`)."""
    t = TriggerAnd(AreFriends(Owner(), Target(), _TEAM_SELECTION),
                   IsAdjacent(Owner(), Target(), _SELECTION))
    return TriggerAnd(t, is_mechanical(Target(), _SELECTION))


def vengeance_behaviour_tree(level: int):
    """`AddEffectOrIncreaseLevel( 0x555, AbilityStateReference, source = Owner@+0x30,
    targets = Owner@+0x30, level = ConfigConst(effectLevel), maxLevel = NULL )`.

    FACTORY native (elle alloue `Foreach(targets, If(HasEffect, IncreaseEffectLevel, AddEffect))`)
    -> portee comme un ARBRE via `behaviours/effects.py::add_effect_or_increase_level`, jamais comme
    un helper imperatif qui fusionnerait la pose et l'increment (frontiere #149).

    `Owner()` et non `Target()` : le natif relit DEUX FOIS le slot `+0x30` (cf. l'en-tete). Le
    niveau est un SCALAIRE et non un noeud paresseux -- contrairement a `omnissiahs_blessing.py`,
    rien dans cet arbre ne reecrit ce qu'il lit, donc le collapse V habituel du depot s'applique
    sans rendre quoi que ce soit inobservable.

    `max_level=None` = le `maxLevel` NULL natif : `IncreaseEffectLevelOperation$$Execute` ne clampe
    alors rien (lecture 4). `scale_from_source` reste au DEFAUT parce que le natif passe bien un
    `abilityState` -- `BaseTriggeredAbility$$get_AbilityStateReference`, c.-a-d. l'etat d'ability
    PASSIF de l'Owner, et `entities.caster` EST l'Owner sur ce chemin."""
    return add_effect_or_increase_level(MACHINE_VENGEANCE, MACHINE_VENGEANCE_NAME, Owner(),
                                        amount=int(level), max_level=None)


class VengeanceForTheOmnissiahAbility(TriggeredAbility):
    """`VengeanceForTheOmnissiahAbility` (triggered 1298) -- a chaque mort d'une unite ALLIEE,
    ADJACENTE et MECANIQUE, le porteur gagne `effectLevel` niveau(x) de `MachineVengeance` (pose si
    absent, increment sinon, SANS cap). Arbre natif des deux faces : en-tete du module."""

    event_id = _ON_UNIT_DEFEATED
    TRIGGERED_ABILITY_ID = VENGEANCE_FOR_THE_OMNISSIAH_ID

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        """`On(0x36, ownerNeedsToBeAlive: 1) & AreFriends(Owner, Target, 0, false)
        & IsAdjacent(Owner, Target, 2) & IsMechanical(Target, 2)`.

        Le seul conjoint COLLAPSE est `ownerNeedsToBeAlive = 1` (le 2e argument litteral d'`On`),
        que le dispatch n'exprime pas : il se lit sur `UnitComponent.alive` du porteur, exactement
        comme `omnissiahs_blessing.py` et `sanguinary_priest.py`. Les trois autres restent des
        noeuds DSL evalues par `vengeance_trigger_tree`.

        ⚠ AUCUN gate sur `ev.actor_id` : le `CreateTrigger` natif ne porte NI `OwnerIsActor` NI
        `OwnerIsTarget`. En ajouter un serait inventer un refus que le natif n'a pas -- le porteur
        gagne sa pile quel que soit le TUEUR. `ev.target_id` nul -> les selecteurs rendent une
        liste vide, `AreFriends` rend faux sur operande nul et `IsAdjacent` rend faux sur liste
        vide : le refus vient des noeuds, pas d'une garde ecrite ici."""
        owner = state.get_entity(self.owner_id)
        if owner is None:
            return False
        uc = owner.get_component(UnitComponent)
        if uc is not None and not uc.alive:               # `On(..., ownerNeedsToBeAlive = 1)`
            return False
        entities = entities_from_state(state, int(self.owner_id), ev.target_id,
                                       actor_id=ev.actor_id)
        return bool(vengeance_trigger_tree().evaluate(entities))

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        """`AddEffectOrIncreaseLevel(0x555, AbilityStateReference, Owner@+0x30, Owner@+0x30,
        ConfigConst(0x73 = effectLevel), NULL)` -- l'arbre ENTIER, sur le PORTEUR."""
        level = vengeance_effect_level()
        entities = entities_from_state(state, int(self.owner_id), ev.target_id,
                                       actor_id=ev.actor_id)
        ectx = ExecutionContext(state=state, rng=state.rng)
        vengeance_behaviour_tree(level).execute(entities, ectx)
        gained = [p for n, p in ectx.emitted if n in ("AddEffect", "IncreaseEffectLevel")
                  and int(p.get("effect_type", -1)) == MACHINE_VENGEANCE]
        return {"passive": VENGEANCE_FOR_THE_OMNISSIAH, "unit": int(self.owner_id),
                "defeated": (None if ev.target_id is None else int(ev.target_id)),
                "level": level,
                "owner_level": (gained[-1].get("level") if gained else None),
                "dsl": True}
