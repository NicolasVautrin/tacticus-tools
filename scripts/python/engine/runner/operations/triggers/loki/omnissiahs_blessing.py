"""`OmnissiahsBlessing` (`TriggeredAbilityType` 0x513 = **1299**), passif du `admecSmnTechpriest`
<< Tech-Priest Enginseer >> (SUMMON d'`InvocationOfMachineVengeance`) et du npc
`admecNpc2Techpriest` -- canal **T** (`ABILITY_TRIGGERS`). #1023.

i2 : << Whenever the Tech-Priest Enginseer repairs another unit, it transfers all levels of Machine
Vengeance it has to the repaired unit. >>

================================================================================================
LES DEUX CORPS, LUS VERBATIM SUR `rnca9r7q6c`
================================================================================================

Slots lus : `DSLSelectors+0x30 Owner`, `+0x60 Target` ; `DSLFactory+0x78 Behaviors`,
`+0x80 Formulas`, `+0x88 Triggers`, `+0x90 Selectors`.

## `IdunBattleLogic.Entities.Abilities.Triggered.Loki.OmnissiahsBlessingAbility$$CreateTrigger`

    On( 0x30 = 48 UnitRepaired, ownerNeedsToBeAlive: 1 )
      op_BitwiseAnd  get_OwnerIsCaster
      op_BitwiseAnd  HasEffect( Owner@+0x30, 0x555 = 1365 MachineVengeance,
                                onlyActive = 0, targetType = 6 )
      op_BitwiseAnd  op_LogicalNot( get_OwnerIsTarget )

## `...OmnissiahsBlessingAbility$$CreateBehaviour(abilityState, triggerType)`

    lvl = DSLFormulas.EffectLevel( DSLSelectors.EffectFromOwner(Owner@+0x30, 0x555) )
    b1  = DSLBehaviors.AddEffectOrIncreaseLevel( 0x555, AbilityStateReference,
                                                 source  = Owner@+0x30,
                                                 targets = Target@+0x60,
                                                 level   = lvl, maxLevel = NULL )
    b2  = DSLBehaviors.RemoveEffect( Owner@+0x30, Nullable<EffectType>(0x555),
                                     replaceableEffectType = NULL )
    return AbilityBehaviour.op_BitwiseAnd( b1, b2 )

`AddEffectOrIncreaseLevel(this, effectType, abilityState, source, targets, level, maxLevel)` :
signature LUE (`IdunBattleLogic.Entities.DSLBehaviors$$AddEffectOrIncreaseLevel`, sept parametres),
et non deduite de l'ordre du call-site. `RemoveEffect` est la surcharge a QUATRE arguments
(`this, selector, effectType, replaceableEffectType`) -- l'autre surcharge prend une entite-effet
directe et n'est pas celle-ci ; le `Nullable<EffectType>` est monte juste avant l'appel
(`System.Nullable<...>..ctor(&local, &0x555)`), le `replaceableEffectType` vaut litteralement `0`.

================================================================================================
CINQ LECTURES QUI NE SE DEVINENT PAS
================================================================================================

1. **`EffectLevel` prend un SELECTEUR D'EFFETS et rend une SOMME.**
   `IdunBattle.Entities.Formulas.EffectLevelFormula$$Calculate` part de `0` et **ACCUMULE**
   `EffectComponent+0x68` (`Level`) sur toutes les entites-effet rendues par `<this+0x10>` : ce
   n'est ni un `First` ni un `max`. Le selecteur, lui, est
   `IdunBattle.Entities.Selectors.EffectWithTypeSelector$$Select` =
   `foreach entity in <+0x18>.Select : eff = EntityExtensions.GetOwnedEffect(entity, state, <+0x20>) ;
   if (eff != null) list.Add(eff)` -- donc AU PLUS une instance par unite selectionnee, et ici une
   seule unite (l'Owner). `GetOwnedEffect` ne filtre NI `IsActive` NI le niveau (corps relu : il
   itere l'`EffectsOwnedComponent` et compare `EffectComponent.Type @+0x58`), d'ou le filtre
   `consumed` SEUL cote port.

2. **L'ORDRE DES DEUX BEHAVIOURS EST LOAD-BEARING, et le port a du RENONCER AU COLLAPSE POUR LE
   GARDER.** `op_BitwiseAnd(b1, b2)` = `IdunBattle.DSL.CombinedBehaviour` -- gauche PUIS droite. Le
   transfert lit le niveau AVANT que `RemoveEffect` ne vide la pile de l'Owner ; inverser rendrait
   un transfert de **0**, sans erreur et sans qu'aucun compte global ne bouge -- la pile
   disparaitrait, purement et simplement.
   Le COLLAPSE V habituel d'`EffectLevel(EffectFromOwner(...))` (resoudre le niveau en SCALAIRE
   avant l'arbre, cf. `runner/abilities/custodes.py::talons_used_abilities_level` et
   `triggers/loki/red_rampage.py::_remaining_turns_of_extra_movement`) est ici INTERDIT, et c'est
   MESURE : sous un scalaire, le mutant << ordre inverse >> reste **VERT** -- le niveau etant deja
   fige, l'inversion ne change plus rien. Le port passe donc un NOEUD VALEUR paresseux
   (`MachineVengeanceLevelOfOwner`), evalue par `AddEffectOrIncreaseLevel` au moment ou il
   s'execute -- exactement comme le natif. Le mutant devient alors ROUGE.
   Ce que ce choix coute : le noeud CAPTURE le `state`, faute d'accesseur de NIVEAU d'effet sur le
   `DslContext` (`ctx.has_effect` n'est qu'un booleen).

3. **`maxLevel = NULL` -> AUCUN cap.** Contraste `TerrifyingCrescendoAbility$$CreateBehaviour`, qui
   passe `Direct(GetNumberConstant(0x62 = buffMaxLevel))`. Le plafond de `MachineVengeance` qui
   existe ailleurs (`ArcScourgeAbility$$GetDynamicInvalidCasterReason` refuse le cast au-dela de
   `effectLevel_2` = 9) est un gate de CASTER sur une AUTRE ability : il ne borne pas ce transfert.

4. **`NOT get_OwnerIsTarget` est le << another unit >> de l'i2, et il n'est PAS redondant** avec
   `get_OwnerIsCaster` : `RepairAbility` porte `TargetingRule.CasterIsPossibleTarget` (masque
   `0x8002` lu sur `IdunBattleLogic.Entities.Abilities.Active.RepairAbility$$.ctor`), donc un
   mecanicien PEUT se reparer lui-meme -- et c'est exactement le cas ou les deux gates divergent.
   Sans ce conjoint, une auto-reparation ferait poser puis retirer la pile sur le meme porteur.

5. **`HasEffect(..., onlyActive = 0)`.** Le 4e argument natif est un flag ACTIVE-ONLY (et non un
   `minLevel`, cf. la docstring d'`entities/triggers.py::HasEffect`), et il vaut ici le LITTERAL
   `0` -- comme sur les deux call-sites `MachineVengeance` d'`ArcScourgeAbility`. Le port passe donc
   `active_only=False` : une instance rendue inerte par son `ActiveCondition` compte quand meme.
   `targetType = 6` = `EffectTargetType.Both` (2|4 : owned|incoming), la valeur que le noeud porte
   deja en dur.

================================================================================================
CRITERE DE L'EMETTEUR
================================================================================================
`On(0x30 = 48 UnitRepaired)` est emis par `triggers/dispatch/repair.py::unit_repaired_triggers`
depuis #964-r1 (`processor.<slot 0x51>(caster, caster, target, 0x30, ...)`), avec
`actor_id = le REPARATEUR` et `target_id = la cible reparee`. L'inscription n'est donc PAS un
registered-but-dead. Les deux autres consommateurs portes de ce vecteur (`ECogSupportAbility`,
`VolummsMasterArtificeAbility`) l'attestent.

================================================================================================
CE QUI N'EST PAS PORTE, ET LE RESTE (residu #1023-r1)
================================================================================================
L'EFFET `1365 MachineVengeance` lui-meme n'a AUCUNE classe dans `EFFECT_CLASSES`. Son unique canal
natif est
`IdunBattle.Entities.Effects.Loki.MachineVengeanceEffect$$CreateEffectDamageBonusForAttack` =

    EffectBonus.ForPercentIncrease( get_OwnerIsCaster,
                                    Multiply( Get(GetNumberConstant(config, 7)),
                                              EffectLevel(Effect@DSLSelectors+0x38) ) )

-- un bonus de degat en POURCENTAGE, par niveau, quand le porteur ATTAQUE
(`AbilityConstantType 7 = MachineVengeanceExtraPct`). Ce module transfere donc fidelement le
NIVEAU (observable en propre : presence de l'instance et valeur de son `Level`), mais le port ne
convertit pas encore ce niveau en degat -- exactement comme AVANT cette tranche, ou la pile
d'`ArcScourge` etait deja posee sans canal de degat. L'ecart est donc INCHANGE par ce port ; il est
NOMME ici plutot que masque. Foyer du residu : `engine/entities/effects/factory.py` +
un module d'effet sous `engine/entities/effects/loki/`.
"""
from __future__ import annotations

from typing import Optional

from ....state import State
from ....components import UnitComponent
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.effects import RemoveEffect, add_effect_or_increase_level
from .....dsl.base import AAmountFormula, resolve_unit
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.behaviours import Seq
from .....entities.effect_type import EffectType
from .....entities.selectors.accessors import Owner, Target
from .....entities.triggered_ability_type import TriggeredAbilityType
from .....entities.triggers import HasEffect
from ..base import TriggeredAbility, TriggerEvent

#: Cle du registre `ABILITY_TRIGGERS` = le NOM gameconfig de la `passiveAbilities` porteuse.
OMNISSIAHS_BLESSING = "OmnissiahsBlessing"
#: `AbilityOrEffect(0x513)` de cette triggered-ability.
OMNISSIAHS_BLESSING_ID = int(TriggeredAbilityType.OmnissiahsBlessing)     # 0x513 = 1299

#: `On(0x30 = 48 UnitRepaired, ownerNeedsToBeAlive = 1)`.
_ON_UNIT_REPAIRED = int(EventTriggerType.UnitRepaired)                    # 0x30 = 48

#: L'effet TRANSFERE -- le MEME id que la pile qu'`ArcScourgeAbility` empile sur son caster
#: (`runner/abilities/admec.py::AS_MACHINE_VENGEANCE`). L'ordinal 1365 nomme AUSSI
#: `TriggeredAbilityType.MachineVengeance` : c'est le NOM et l'enum qui tranchent, jamais l'entier.
MACHINE_VENGEANCE = int(EffectType.MachineVengeance)                      # 0x555 = 1365
MACHINE_VENGEANCE_NAME = EffectType.MachineVengeance.name

#: `HasEffect( Owner@+0x30, 0x555, onlyActive = 0, targetType = 6 )` -- noeud DSL du foyer
#: (`entities/triggers.py`), `active_only=False` transcrit du LITTERAL `0` du call-site.
_OWNER_HAS_MACHINE_VENGEANCE = HasEffect(Owner(), MACHINE_VENGEANCE, active_only=False)


def machine_vengeance_level(state: State, unit_id: int) -> int:
    """`DSLFormulas.EffectLevel( DSLSelectors.EffectFromOwner(Owner@+0x30, 0x555) )` -- substrat
    OFFLINE.

    `entities/selectors/geometry.py::EffectFromOwner` rend `[]` hors-ligne (le domaine
    ENTITE-EFFET n'est pas materialise cote port), donc le noeud DSL ne peut pas porter cette
    lecture : elle se resout en amont, en scalaire. C'est le MEME arbitrage, au MEME endroit, que
    `runner/abilities/custodes.py::talons_used_abilities_level` pour
    `EffectLevel(EffectFromOwner(Caster@+0x48, 0x58c))`.

    `EffectLevelFormula$$Calculate` **ACCUMULE** (somme des `EffectComponent+0x68`), et le selecteur
    ne filtre ni `IsActive` ni le niveau -- d'ou `consumed` comme SEUL filtre, exactement comme
    `talons_used_abilities_level_from_effects` et comme le balayage de
    `ArcScourgeAbility$$GetDynamicInvalidCasterReason` (`admec.py`), qui lit la MEME pile.

    Pas de `state.effects` -> 0, ce qui rend le behaviour inerte (transfert de zero niveau) : le
    natif rendrait 0 de meme sur un `EffectsOwnedComponent` vide."""
    eff = getattr(state, "effects", None)
    if eff is None or unit_id is None:
        return 0
    total = 0
    for e in eff.by_unit.get(int(unit_id), []):
        if getattr(e, "consumed", False) or int(getattr(e, "effect_type", -1)) != MACHINE_VENGEANCE:
            continue
        total += int(getattr(e, "level", 0) or 0)
    return total


class MachineVengeanceLevelOfOwner(AAmountFormula):
    """`DSLFormulas.EffectLevel( DSLSelectors.EffectFromOwner(Owner@+0x30, 0x555) )` -- noeud VALEUR
    **PARESSEUX**, evalue par `AddEffectOrIncreaseLevel` au moment ou il s'execute.

    ⚠ C'EST UN ECART DELIBERE AU COLLAPSE V DU DEPOT, et il est MESURE (cf. la lecture 2 de
    l'en-tete) : `custodes.py::talons_used_abilities_level` et
    `red_rampage.py::_remaining_turns_of_extra_movement` resolvent ce meme motif en SCALAIRE avant
    l'arbre, parce que rien, chez eux, ne REECRIT l'effet lu dans le meme arbre. Ici si -- le
    `RemoveEffect` qui suit vide la pile -- donc un scalaire figerait la lecture et rendrait
    l'ORDRE des deux behaviours INOBSERVABLE (mutant << ordre inverse >> VERT).

    Le `state` est capture au constructeur : le `DslContext` n'expose aucun accesseur de NIVEAU
    d'effet (`ctx.has_effect` est un booleen), et `entities/selectors/geometry.py::EffectFromOwner`
    rend `[]` hors-ligne (domaine entite-effet non materialise). Le corps de la lecture reste
    `machine_vengeance_level`, foyer UNIQUE partage avec `execute_behaviour`."""
    __slots__ = ("state", "unit_sel")

    def __init__(self, state: State, unit_sel=None):
        self.state = state
        self.unit_sel = Owner() if unit_sel is None else unit_sel

    def calculate(self, ctx):
        u = resolve_unit(self.unit_sel, ctx)
        uid = u.get("id") if isinstance(u, dict) else None
        return 0 if uid is None else machine_vengeance_level(self.state, int(uid))


def omnissiahs_blessing_transfer_tree(state: State):
    """`AddEffectOrIncreaseLevel( 0x555, AbilityStateReference, source = Owner@+0x30,
    targets = Target@+0x60, level = EffectLevel(EffectFromOwner(Owner, 0x555)), maxLevel = NULL )`.

    FACTORY native (elle alloue `Foreach(targets, If(HasEffect, IncreaseEffectLevel, AddEffect))`)
    -> portee comme un ARBRE via `behaviours/effects.py::add_effect_or_increase_level`, jamais comme
    un helper imperatif qui fusionnerait la pose et l'increment (frontiere #149).

    `max_level=None` = le `maxLevel` NULL natif : `IncreaseEffectLevelOperation$$Execute` ne clampe
    alors rien. `scale_from_source` reste au DEFAUT (`True`) parce que le natif passe bien un
    `abilityState` -- `BaseTriggeredAbility$$get_AbilityStateReference`, c.-a-d. l'etat d'ability
    PASSIF de l'Owner, et `entities.caster` EST l'Owner sur ce chemin (une triggered s'execute sur
    son propre porteur)."""
    return add_effect_or_increase_level(
        MACHINE_VENGEANCE, MACHINE_VENGEANCE_NAME, Target(),
        amount=MachineVengeanceLevelOfOwner(state), max_level=None)


def omnissiahs_blessing_clear_tree():
    """`RemoveEffect( Owner@+0x30, Nullable<EffectType>(0x555), replaceableEffectType = NULL )`.

    Le `replaceableEffectType` NUL est ce que le port exprime en ne le passant pas : la feuille
    `behaviours/effects.py::RemoveEffect` retire TOUTES les instances non consommees du type sur
    chaque cible du selecteur, ce qui est le corps de `RemoveEffectsBehaviour` quand ce second
    parametre est absent."""
    return RemoveEffect(MACHINE_VENGEANCE, Owner())


def omnissiahs_blessing_tree(state: State) -> Seq:
    """`op_BitwiseAnd( AddEffectOrIncreaseLevel(...), RemoveEffect(...) )` -- l'arbre ENTIER, dans
    l'ORDRE natif : on TRANSFERE, PUIS on vide la pile du porteur. Cf. la lecture 2 de l'en-tete --
    c'est ce `Seq` qui porte l'invariant, et le noeud paresseux qui le rend OBSERVABLE."""
    return Seq(omnissiahs_blessing_transfer_tree(state), omnissiahs_blessing_clear_tree())


class OmnissiahsBlessingAbility(TriggeredAbility):
    """`OmnissiahsBlessingAbility` (triggered 1299) -- a chaque REPARATION dont le Tech-Priest est le
    CASTER et dont il n'est PAS la cible, et pour autant qu'il porte lui-meme `MachineVengeance` :
    la cible reparee recoit `+<niveau du porteur>` niveaux de `MachineVengeance` (pose si absent,
    increment sinon, SANS cap), puis le porteur PERD toute sa pile. Arbre natif des deux faces :
    en-tete du module."""

    event_id = _ON_UNIT_REPAIRED
    TRIGGERED_ABILITY_ID = OMNISSIAHS_BLESSING_ID

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        """`On(0x30, ownerNeedsToBeAlive: 1) & get_OwnerIsCaster & HasEffect(Owner, 0x555, 0, 6)
        & NOT get_OwnerIsTarget` -- les quatre conjoints, dans l'ordre du decompile.

        `get_OwnerIsCaster` se lit sur `ev.actor_id` : le natif passe le REPARATEUR dans les DEUX
        premiers slots du `processor.<slot 0x51>` (owner ET actor), ce que
        `dispatch/repair.py::unit_repaired_triggers` transcrit.

        `NOT get_OwnerIsTarget` = `NOT AreEqual(Owner@+0x30, Target@+0x60)`. Un `ev.target_id` NUL
        rendrait `AreEqual` faux, donc le conjoint VRAI cote natif -- le behaviour retirerait alors
        la pile sans rien transferer. Le vecteur `unit_repaired_triggers` passe toujours un
        `int(target_id)`, donc ce regime n'est pas atteignable ; on ne pose PAS de gate qui n'existe
        pas au natif, et l'entite cible absente est traitee dans `execute_behaviour`."""
        if ev.actor_id is None or int(ev.actor_id) != int(self.owner_id):
            return False                                  # get_OwnerIsCaster
        if ev.target_id is not None and int(ev.target_id) == int(self.owner_id):
            return False                                  # NOT get_OwnerIsTarget
        owner = state.get_entity(self.owner_id)
        if owner is None:
            return False
        uc = owner.get_component(UnitComponent)
        if uc is not None and not uc.alive:               # `On(..., ownerNeedsToBeAlive = 1)`
            return False
        entities = entities_from_state(state, int(self.owner_id), ev.target_id)
        return bool(_OWNER_HAS_MACHINE_VENGEANCE.should_trigger(entities))

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        """`op_BitwiseAnd( AddEffectOrIncreaseLevel(0x555, ..., Target@+0x60, lvl, NULL),
        RemoveEffect(Owner@+0x30, Nullable(0x555)) )`.

        Le NIVEAU n'est PAS pre-resolu : il est porte par le noeud paresseux
        `MachineVengeanceLevelOfOwner`, que `AddEffectOrIncreaseLevel` evalue au moment ou il
        s'execute -- donc AVANT le `RemoveEffect` qui suit dans le `Seq`, exactement comme le natif.
        Le `level` rendu dans le payload est une LECTURE de journal (avant l'arbre), pas l'entree du
        calcul."""
        if state.effects is None:
            return None
        level = machine_vengeance_level(state, int(self.owner_id))
        entities = entities_from_state(state, int(self.owner_id), ev.target_id)
        ectx = ExecutionContext(state=state, rng=state.rng)
        omnissiahs_blessing_tree(state).execute(entities, ectx)
        transferred = [p for n, p in ectx.emitted if n in ("AddEffect", "IncreaseEffectLevel")
                       and int(p.get("effect_type", -1)) == MACHINE_VENGEANCE]
        removed = sum(int(p.get("removed", 0) or 0) for n, p in ectx.emitted
                      if n == "RemoveEffect" and int(p.get("effect_type", -1)) == MACHINE_VENGEANCE)
        return {"passive": OMNISSIAHS_BLESSING, "unit": int(self.owner_id),
                "target": (None if ev.target_id is None else int(ev.target_id)),
                "level": level,
                "target_level": (transferred[-1].get("level") if transferred else None),
                "removed": removed, "dsl": True}
