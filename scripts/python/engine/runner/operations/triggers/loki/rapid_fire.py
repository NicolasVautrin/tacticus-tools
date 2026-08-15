"""`RapidFire` (#1020-r5) -- passif `TriggeredAbilityType` 0x46f = 1135, Ultramarines.

RE : decompile ghidra, build `t6dpr4k06g`. Les deux arbres sont LUS verbatim.

i2 (`Abilities/RapidFire_CurrentLevelDescription`) : l'unite peut attaquer une SECONDE fois dans le
meme tour, au prix de son deplacement et de ses abilities actives.

===================================================================================================
LES DEUX ARBRES, LUS VERBATIM
===================================================================================================

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.RapidFireAbility$$CreateTrigger` =

      On( 0xe = EventTriggerType.UnitPostAbility, ownerNeedsToBeAlive = 1 )
    & IsNormalAttack()
    & get_OwnerIsActor
    & NOT HasFlag( Caster@<DSLSelectors+0x48>, 0x0 = UnitFlag.Moved )
    & NOT HasEffect( Caster@<+0x48>, 0x471 = 1137, onlyActive: 0, effectTarget: 6 = Both )

`...RapidFireAbility$$CreateBehaviour` =

      ( ResetTurn( Owner@<DSLSelectors+0x30>, resetMovement = 0 )
      & AddEffect( 0x471 = 1137 RapidFire_BlockAbilities,
                   get_AbilityStateReference(this),
                   source  = Owner@<+0x30>,
                   targets = Owner@<+0x30>,
                   turns   = <DSLFormulas+0x20> = Direct(1) ) )
    & AddFlag( Caster@<+0x48>, 0x0 = UnitFlag.Moved )

L'associativite est LUE (les deux `op_BitwiseAnd` sont emis dans cet ordre) et elle n'est pas
neutre : le `ResetTurn` doit precede l'`AddFlag`, sans quoi le drapeau `Moved` qu'on vient de poser
serait le seul etat que le reset ne retire pas -- il ne le retire deja pas, mais l'ordre inverse
rendrait la lecture ambigue pour qui relit.

===================================================================================================
CE QUE LA MECANIQUE FAIT -- et pourquoi elle ne boucle PAS
===================================================================================================

1. l'unite attaque NORMALEMENT sans avoir bouge -> `On(UnitPostAbility)` a la cloture ;
2. `ResetTurn(Owner, resetMovement = 0)` retire {ActiveAbilityUsed, TurnFinished, TurnFinishedForced}
   + {NoActionAvailable} (le `includeNoAction` est le litteral `1` du behaviour) mais **PAS**
   {Moved, Teleported, ArrivedAtFinalTile} : l'unite redevient activable SANS recuperer son
   deplacement. C'est tout le sens du `resetMovement = 0` -- l'exact contraire du `ResetTurn(.., 1)`
   de `FightingRetreat` ;
3. `AddEffect(1137)` pose le blocage d'ability pour UN TOUR : la seconde action ne peut etre qu'une
   ATTAQUE NORMALE (`includeNormalAttack = 0`), pas un actif ;
4. `AddFlag(Caster, Moved)` ferme le deplacement.

**Les DEUX gardes de re-entrance sont dans le trigger, et ils sont redondants a dessein** :
`NOT HasFlag(Moved)` (pose a l'etape 4) et `NOT HasEffect(1137)` (pose a l'etape 3). La seconde
attaque ne peut donc pas en declencher une troisieme.

===================================================================================================
EFFET DE BORD **DAMAGE**, REEL ET INDIRECT
===================================================================================================

L'`AddFlag(Moved)` eteint le conjoint `NOT HasFlag(Owner, 0 = Moved)` de
`IdunBattle.Entities.Effects.Loki.HeavyWeapon_ExtraDmgEffect$$CreateDamageModifier`, et les QUATRE
porteurs de `RapidFire` ont le trait `HeavyWeapon` : la SECONDE attaque perd le bonus. Cette ability
ne traverse aucun noeud producteur de degat (aucun des trois events d'`ApplyDamageOperation$$Execute`)
-- son effet numerique passe entierement par cet extincteur.

===================================================================================================
L'EFFET 1137 : POURQUOI IL N'ENTRE PAS DANS `EFFECT_CLASSES`
===================================================================================================

`IdunBattle.Entities.Effects.BlockActiveAbilityEffect$$.ctor(this, hasAutomaticActivation = 1,
includeNormalAttack = 0, includeMachinePrimaryAbility = 1)` n'ecrit que DEUX booleens (`this+0x480`,
`this+0x481`) apres un `BaseEffect$$.ctor` dont la struct d'options est ZEROEE : la classe ne porte
**aucune** magnitude, aucun `ConfigVar`. Sa face utile est le couple
`$$ApplyInternal`/`$$RevertInternal` -> `UpdateActiveAbilityBlockerOperation$$AddBlocker/RemoveBlocker`,
que le port realise COTE REQUETE dans `engine/battle_query.py::can_use_ability` (registre
`ACTIVE_ABILITY_BLOCKER_EFFECTS`). Materialiser ici une classe d'effet sans magnitude serait une
instance INERTE, exactement le vice ferme par #462-r4b-r1-r1. Ses deux soeurs de famille (26
`Taunted_CantUseAbility`, 1165 `Stunned_CantUseAbility`) sont traitees de meme et ne sont, elles non
plus, dans aucun registre d'`EFFECT_CLASSES`.

Meme raison pour le 2e argument natif `get_AbilityStateReference(this)` : le port ne l'arme pas
(`scale_from_source` non passe), comme `Maugetar_HasNotMoved` dont le call-site a la meme forme --
il n'a rien a mettre a l'echelle. S'il fallait un jour donner une magnitude a cette famille, c'est
CE call-site qu'il faudrait armer, et la ligne ci-dessus est la ou le lecteur doit revenir.

===================================================================================================
LE PORTEUR -- ventilation, et pourquoi la GREFFE est licite
===================================================================================================

`unit_map find --ability RapidFire` rend QUATRE porteurs, aucun `hero` : `ultraNpc3Intercessor`,
`ultraNpc4HeavyIntercessor`, `ultraNpc4HeavyIntercessorSurv` (npc) et `ultraSmnHeavyIntercessor`
(summon). La condition de GREFFE (`case-92` SS5bis) est LUE et non supposee : **ni le trigger ni le
behaviour ne consultent une stat, un trait ou une variable du caster** -- le trigger ne lit que le
vecteur, un drapeau et un effet ; le behaviour ne prend aucun `ConfigVar`. L'ability se greffe donc
sur une unite du pool ; l'hote qui SEPARE est un porteur du trait `HeavyWeapon` (pour que l'effet de
bord DAMAGE soit visible), par exemple `ultraEliminatorSgt`.
"""
from __future__ import annotations

from typing import Optional

from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.behaviours import op_and
from .....entities.effect_type import EffectType
from .....entities.selectors.accessors import Owner
from .....entities.selectors.tiles import Caster
from .....entities.triggered_ability_type import TriggeredAbilityType
from .....entities.unit_flag import UnitFlag
from ....abilities.attack_type import is_normal_attack
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.effects import AddEffect
from ....abilities.behaviours.flags import AddFlag
from ....abilities.behaviours.turnflow import ResetTurn
from ....components import UnitFlagsComponent, has_effect_of_type
from ....state import State
from ..base import TriggeredAbility, TriggerEvent

#: CLE du registre `ABILITY_TRIGGERS` = le nom gameconfig du passif, pris au MEMBRE de l'enum et non
#: recopie en chaine : un renumerotage du build ferait rougir `probe_313` au lieu de laisser une cle
#: morte muette (meme geste que `WAY_OF_THE_SHORT_BLADE_KEY`).
RAPID_FIRE_KEY = TriggeredAbilityType.RapidFire.name                    # "RapidFire"
ABILITY_ID = RAPID_FIRE_KEY
RAPID_FIRE = int(TriggeredAbilityType.RapidFire)                        # 0x46f = 1135
#: `AddEffect(0x471, ...)` / `NOT HasEffect(Caster, 0x471, 0, 6)` -- un `EffectType`, PAS le
#: `TriggeredAbilityType` ci-dessus : les deux ordinaux sont voisins et designent deux enums.
RAPID_FIRE_BLOCK_ABILITIES = int(EffectType.RapidFire_BlockAbilities)   # 0x471 = 1137
#: `NOT HasFlag(Caster@<+0x48>, 0x0)` / `AddFlag(Caster@<+0x48>, 0x0)`.
MOVED = int(UnitFlag.Moved)                                             # 0x0 = 0

#: `ResetTurn(Owner@<+0x30>, resetMovement = 0)` -- le SECOND argument de la factory, LU a `0`.
#: Il commande le `newActivation` de `UnitFlagsComponent$$RemoveTurnFlags` : a `0`, ni `Moved`, ni
#: `Teleported`, ni `ArrivedAtFinalTile` ne sont retires.
_RESET_MOVEMENT = False
#: `turns = <DSLFormulas+0x20>` = `Direct(1)` -- une duree DEJA EN TOURS, jamais un `TurnsFromRounds`.
_TURNS = 1


def rapid_fire_tree():
    """`...RapidFireAbility$$CreateBehaviour` -- MIRROR 1:1, associativite comprise.

    `Owner@<DSLSelectors+0x30>` et `Caster@<+0x48>` designent ici la MEME unite (le trigger porte
    `get_OwnerIsActor`, et le vecteur `UnitPostAbility` pose `actor == caster`), mais les deux
    selecteurs restent ecrits tels que le natif les passe -- recopier l'un a la place de l'autre
    ferait perdre l'information le jour ou un vecteur les separerait."""
    return op_and(
        op_and(ResetTurn(Owner(), new_activation=_RESET_MOVEMENT),
               AddEffect(RAPID_FIRE_BLOCK_ABILITIES, EffectType.RapidFire_BlockAbilities.name,
                         Owner(), duration_rounds=None, duration_turns=_TURNS)),
        AddFlag(Caster(), MOVED))


class RapidFireAbility(TriggeredAbility):
    """`IdunBattleLogic.Entities.Abilities.Triggered.Loki.RapidFireAbility`.

    OBSERVABLE : une unite qui attaque normalement SANS avoir bouge recupere une action -- mais
    seulement pour une seconde ATTAQUE NORMALE, et sans pouvoir se deplacer."""
    event_id = int(EventTriggerType.UnitPostAbility)                    # `On(0xe, alive = 1)`
    TRIGGERED_ABILITY_ID = RAPID_FIRE                                   # 0x46f = 1135

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        # `get_OwnerIsActor` : `unit_post_ability_triggers` construit l'event avec
        # `actor = caster = caster_id`, donc l'acteur EST le caster sur ce vecteur.
        if ev.actor_id is None or int(ev.actor_id) != int(self.owner_id):
            return False
        # `IsNormalAttack()` -- la surcharge SANS argument, qui delegue a la surcharge a deux
        # arguments en lui passant l'ability COURANTE (`<DSLSelectors+0x90>+0x88`). Cote port
        # c'est `ev.ability_type`, que les deux emetteurs du vecteur threadent.
        if not is_normal_attack(ev.ability_type):
            return False
        # `NOT HasFlag(Caster@<+0x48>, 0x0 = Moved)`. Tri-etat : composant de drapeaux ABSENT ->
        # NON MESURE -> on REFUSE. Degradation RESTRICTIVE et nommee : rouvrir un tour sur une
        # geometrie de drapeaux inconnue serait permissif, et c'est le sens de faute interdit.
        ent = state.get_entity(int(self.owner_id))
        fl = ent.get_component(UnitFlagsComponent) if ent is not None else None
        if fl is None or fl.has(MOVED):
            return False
        # `NOT HasEffect(Caster@<+0x48>, 0x471, onlyActive: 0, effectTarget: 6 = Both)` -- le second
        # garde de re-entrance. `has_effect_of_type` est le mirror EXACT de ce noeud (onlyActive 0).
        return not has_effect_of_type(state, int(self.owner_id), RAPID_FIRE_BLOCK_ABILITIES)

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        entities = entities_from_state(state, self.owner_id, self.owner_id)
        ectx = ExecutionContext(state=state, rng=state.rng)
        rapid_fire_tree().execute(entities, ectx)
        emitted: dict = {}
        for name, payload in ectx.emitted:
            emitted.setdefault(name, []).append(payload)
        resets = emitted.get("ResetTurn", ())
        return {"passive": ABILITY_ID, "owner": int(self.owner_id),
                "reset_flags": sorted({int(f) for p in resets for f in (p.get("removed") or ())}),
                "effect": RAPID_FIRE_BLOCK_ABILITIES,
                "blocked": bool(any(p.get("placed") for p in emitted.get("AddEffect", ()))),
                "moved_flag_added": bool(any(p.get("added") for p in emitted.get("AddFlag", ())))}
