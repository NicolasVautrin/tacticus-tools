"""`IdunBattleLogic.Entities.Abilities.Triggered.Loki.ElectrochaffBackupsAbility` -- ability
**MYTHIQUE** (`TriggeredAbilityType` 0x5ae = 1454) des Machines of War `tauBroadside` << Tson'ji >>
(lineup) et `tauNpcMoWBroadside` (npc). Face RUNNER << POSE de l'effet >>. #1025.

i2 (`/Abilities/ElectrochaffBackups_CurrentLevelDescription`) : « Enemy units that have a
**Markerlight** or have been damaged by a **ranged attack** deal -{dmgReductionPct}% Damage to
**Mythic** characters for {nrOfRounds} round. »

## RE -- LE DECOMPILE, LU (`classes.tsv` : parent `IdunBattle.Entities.Abilities.BaseTriggeredAbility`)

`...ElectrochaffBackupsAbility$$CreateTrigger` -- DEUX branches unies par un `op_BitwiseOr`, qui
partagent un tronc `commun` :

    commun = AreEnemies( Owner@<DSLSelectors+0x30>, Target@<DSLSelectors+0x60>, 0 )
             & IsNormalUnit( Target@<DSLSelectors+0x60> )
    brancheA = On(0x3e = EventTriggerType.EffectAdded, ownerNeedsToBeAlive: 1) & commun
               & TriggeringEffectIs( 0x462 = EffectType.Markerlight )
    brancheB = On(0x0f = EventTriggerType.DamageTaken, ownerNeedsToBeAlive: 1) & commun
               & IsRangedAttack()
    return op_BitwiseOr( brancheA, brancheB )

⚠ L'ORDRE DES CONJOINTS EST CELUI DU DECOMPILE, et il n'est pas anodin a la lecture : le natif
construit `commun` D'ABORD, puis `On(0x3e) & commun`, puis `& TriggeringEffectIs`, puis
`On(0x0f) & commun`, puis `& IsRangedAttack`. Une conjonction est commutative -- ce qui ne l'est
pas, c'est l'appariement branche <-> conjoint propre : `TriggeringEffectIs` appartient a la branche
`EffectAdded`, `IsRangedAttack` a la branche `DamageTaken`. Les intervertir donnerait deux branches
STRUCTURELLEMENT differentes (un Markerlight pose au corps-a-corps ne poserait plus rien).

`...ElectrochaffBackupsAbility$$CreateBehaviour(abilityState, triggerType)` :

    turns   = DSLFormulas$$TurnsFromRounds( AbilityConfiguration$$GetNumberConstant(
                                                config@<this+0x20>, 0x45 = nrOfRounds ) )
    ajout   = DSLBehaviors$$AddEffect( 0x5a6 = EffectType.ElectrochaffBackups_DamageReductionPct,
                                       BaseTriggeredAbility$$get_AbilityStateReference(this),
                                       source  = Owner@<DSLSelectors+0x30>,
                                       targets = Target@<DSLSelectors+0x60>,
                                       turns )
    refresh = DSLBehaviors$$ChangeEffectTurns( owner      = Target@<DSLSelectors+0x60>,
                                               effectType = 0x5a6,
                                               amount     = turns,
                                               changeType = 1 = ChangeType.Set )
    cond    = DSLTriggers$$HasEffect( Target@<DSLSelectors+0x60>, 0x5a6,
                                      onlyActive = 0, effectTarget = 6 )
    return DSLBehaviors$$If( cond, refresh, ajout )

⚠ `changeType = 1` est **`ChangeType.Set`**, pas `Add` : un re-declenchement REMET la duree a
`turns`, il ne l'accumule PAS. Lu au 5e argument du call-site (`CONCAT44(hi, 1)`), et la semantique
vient de `IdunBattle.Core.Services.BattleQuery$$GetAmount` (0 = Add, 1 = Set), deja mirroree par
`ChangeEffectTurnsOperation.get_amount`. C'est le SEUL endroit ou une confusion serait numerique et
silencieuse : avec `Add`, un ennemi tire trois fois dessus finirait a 3 tours au lieu de 1.

⚠ `onlyActive = 0` : le natif ne consulte PAS `EffectComponent.IsActive @+0x5c` -- une instance
1446 INERTE compte quand meme comme « deja presente », donc on refresh au lieu de re-poser. Mirror =
`components.has_effect_of_type` (qui ne filtre que `consumed`), JAMAIS `active_effects`.

`nrOfRounds` vaut **"1"** au gameconfig (une CHAINE, comme toutes les `constants`), d'ou
`duration_rounds = 1` -> `ConvertRoundsToTurns(1)`. Lu, jamais code en dur.

## CE QUI EST PORTE ICI, ET CE QUI NE L'EST PAS

PORTE : le TRIGGER (les deux branches) et le BEHAVIOUR (`If`/`ChangeEffectTurns`/`AddEffect`).
Aucun de ces noeuds ne porte de gate de RARETE -- cette face est donc integralement confrontable.

NON PORTE : l'EFFET 1446 lui-meme (`IdunBattle.Entities.Effects.Loki.
ElectrochaffBackups_DamageReductionPctEffect`), dont le `CreateDamageModifier` est

    EffectBonus$$ForPercentDecrease(
        get_OwnerIsCaster
        & HasRarity( Target@<DSLSelectors+0x60>, 5 = Mythic )
        & AreFriends( Target@<DSLSelectors+0x60>,
                      EffectSource(Effect@<DSLSelectors+0x38>), 0, false ),
        DSLFormulas$$ConfigVar( 0x46 = dmgReductionPct, GetAbilityState(effet), effet@+0x60 ) )

Son premier conjoint utile est `HasRarity(..., 5)`, qui lit `GetBaseUnitComponent(entity)+0x74`
(MESURE : `IdunBattle.Entities.UnitExtensions$$HasRarity` et
`IdunBattle.Entities.Formulas.UnitsWithRaritySelector$$Select` comparent tous deux ce champ au
litteral, il n'existe aucune autre voie). **AUCUN canal `rarity` n'existe cote port** -- ni
`combatSnapshot`, ni `UnitContext`, et le gameconfig porte `BaseRarity = "Common"` pour les DEUX
MoW, donc il ne repond pas a la question. Meme verrou que `ShieldOfFaithNonOwnerPlaybook` et que
les trois faces MOVE de `#477-r37-r1`. Porter le canal de degat sans ce gate serait un terme
PERMISSIF, pas un port -- l'effet reste donc HORS d'`EFFECT_CLASSES`, ce qui rend `BaseEffect`
generique et TOUS ses canaux muets : la degradation est RESTRICTIVE et nommee. Residu `#1025-r1`.

## DISPATCH -- deux vecteurs, tous deux DEJA emis par le port

  * `On(0x3e = EffectAdded)` -> `dispatch/move_death.effect_added_triggers` (emis a la FIN
    d'`AddEffectOperation.execute`, donc APRES materialisation) : `actor` = la SOURCE de l'effet,
    `target` = la cible de la pose, `triggering_effect` = le type pose ;
  * `On(0x0f = DamageTaken)` -> `dispatch/attack.damage_taken_triggers` (emis par
    `_apply_damage_pipeline` apres la mutation des PV) : `actor` = la source du degat,
    `target` = la VICTIME.

⚠ Sur les DEUX vecteurs, `Target@<DSLSelectors+0x60>` est bien `ev.target_id` -- ce n'est pas
l'attaquant. C'est ce qui fait de l'ennemi BLESSE (ou MARQUE) le porteur de l'effet, conformement a
l'i2 (« Enemy units that ... have been damaged »), et non son agresseur.

⚠ **`IsRangedAttack` sur le vecteur `DamageTaken` : degradation NOMMEE.**
`damage_taken_triggers` ne threade PAS `ability_type` (il construit son `TriggerEvent` avec
`ability_type = None`), donc `_is_ranged_attack` retombe sur la branche << attaque normale
concrete >> du slot 3 `IdunBattle.Core.Services.BattleQuery$$IsRangedAttack` = `!AreEntitiesAdjacent`.
Pour une attaque d'ABILITY dont l'`attackRangeType` est `Ranged(2)` mais dont la cible est
ADJACENTE, le natif rend VRAI sans lire la position, la ou le port rend FAUX. Elargir le canal
demande de threader `ability_type` depuis `_apply_damage_pipeline` (foyer partage) : residu
`#1025-r2`, degradation RESTRICTIVE en attendant.
"""
from __future__ import annotations

from typing import Optional

from ....state import State
from ....components import OwnerComponent, StatsComponent, has_effect_of_type
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.effects import AddEffect
from .....entities.selectors.accessors import Target
from .....entities.ability_constant_type import AbilityConstantType
from .....entities.effect_type import EffectType
from .....entities.traits.unit_trait import entity_trait_names, is_normal_unit
from .....entities.triggered_ability_type import TriggeredAbilityType
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from ..base import TriggeredAbility, TriggerEvent, _is_ranged_attack
from ...effects import ChangeEffectTurnsOperation
from ....abilities.base import convert_rounds_to_turns

#: Nom gameconfig de l'ability (cle des `mythicAbilities` de `tauBroadside`) -- c'est par ce NOM
#: que le registre de dispatch l'indexe, et c'est lui que porte `UnitContext.tertiary_ability`
#: quand `catalog_inject.equip_mythic` l'a ecrite dans `BC.Units[].TertiaryAbility`.
ELECTROCHAFF_BACKUPS_ID = "ElectrochaffBackups"
#: `TriggeredAbilityType` 0x5ae = 1454 -- l'id que porte `BC.Units[].TertiaryAbility`.
ELECTROCHAFF_BACKUPS = TriggeredAbilityType.ElectrochaffBackups
#: `EffectType` 0x5a6 = 1446 -- l'effet pose sur l'ennemi (`AddEffect` du behaviour).
ELECTROCHAFF_EFFECT = int(EffectType.ElectrochaffBackups_DamageReductionPct)
#: `EffectType` 0x462 = 1122 -- le `TriggeringEffectIs` de la branche A.
MARKERLIGHT = int(EffectType.Markerlight)
#: `AbilityConstantType` 0x45 = 69 -- `GetNumberConstant(config, nrOfRounds)`.
CONST_NR_OF_ROUNDS = AbilityConstantType.nrOfRounds
#: `HasEffect(..., effectTarget = 6)` = `2|4` (owned | targeted) -- cote port les deux branches
#: coincident, l'`EffectsState` etant indexee par ENTITE PORTEUSE. Cf. `has_effect_of_type`.
_EFFECT_TARGET_OWNED_OR_TARGETED = 6
#: `ChangeType.Set` (`IdunBattle.Entities.Enum.ChangeType` 1) -- le 5e argument du call-site.
_CHANGE_SET = ChangeEffectTurnsOperation.CHANGE_SET


def electrochaff_rounds() -> int:
    """`AbilityConfiguration$$GetNumberConstant(config@<this+0x20>, 0x45 = nrOfRounds)` -- LU au
    gameconfig, jamais en dur. Les `constants` du gameconfig sont des CHAINES (`"1"`), d'ou le
    `int(...)`. Absent -> 0, ce qui rend `TurnsFromRounds(0)` et donc une pose de duree nulle : le
    natif ferait pareil (`GetNumberConstant` sur une cle absente rend 0)."""
    import gameconfig as GC                                    # noqa: PLC0415
    consts = (GC.ability(ELECTROCHAFF_BACKUPS_ID) or {}).get("constants") or {}
    return int(consts.get(CONST_NR_OF_ROUNDS.name) or 0)


def electrochaff_add_effect_tree(rounds: int):
    """Branche `else` de `$$CreateBehaviour` (MIRROR 1:1) :

        AddEffect( 0x5a6, get_AbilityStateReference(this),
                   source = Owner@<DSLSelectors+0x30>, targets = Target@<DSLSelectors+0x60>,
                   turns  = TurnsFromRounds(GetNumberConstant(nrOfRounds)) )

    `Target()` (unit-domain) resout la cible de l'evenement ; la SOURCE est le porteur (defaut du
    port : `entities.caster`, que `entities_from_state(state, owner_id, target_id)` fixe au
    porteur -- une ability triggered a `Owner == Caster`)."""
    return AddEffect(ELECTROCHAFF_EFFECT, "ElectrochaffBackups_DamageReductionPct",
                     Target(), duration_rounds=rounds)


class _ElectrochaffBackupsBase(TriggeredAbility):
    """Tronc COMMUN des deux branches du `op_BitwiseOr` de `$$CreateTrigger` : le meme
    `AreEnemies(Owner, Target) & IsNormalUnit(Target)` et le MEME `$$CreateBehaviour` (le natif
    n'en a qu'UN -- c'est le trigger qui est disjonctif, pas le behaviour)."""

    def _common(self, state: State, ev: TriggerEvent) -> bool:
        """`AreEnemies(Owner@+0x30, Target@+0x60, 0) & IsNormalUnit(Target@+0x60)`."""
        if ev.target_id is None:
            return False
        owner, tgt = state.get_entity(self.owner_id), state.get_entity(ev.target_id)
        if owner is None or tgt is None:
            return False
        oc, tc = owner.get_component(OwnerComponent), tgt.get_component(OwnerComponent)
        if oc is None or tc is None or oc.team == tc.team:     # AreEnemies(Owner, Target)
            return False
        # `IsNormalUnit(Target)` = `IdunBattle.Entities.UnitExtensions$$IsNormalUnit` =
        # `!HasTrait(0xd = Object) && !HasTrait(0x1b = Steppable)` -- FOYER PARTAGE
        # (`entities.traits.unit_trait.is_normal_unit`), jamais un predicat re-ecrit ici. Le
        # substrat de traits est celui d'`entity_trait_names` (kit + accordes en bataille +
        # grande-alliance), le MEME que lit `BaseUnitComponent$$HasTrait`.
        tsc = tgt.get_component(StatsComponent)
        return is_normal_unit(entity_trait_names(getattr(tsc, "ctx", None)))

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        """`$$CreateBehaviour` (MIRROR 1:1) :
        `If( HasEffect(Target, 0x5a6, onlyActive: 0, effectTarget: 6),
             ChangeEffectTurns(Target, 0x5a6, turns, ChangeType.Set),
             AddEffect(0x5a6, ..., Target, turns) )`."""
        if state.effects is None or ev.target_id is None:
            return None                                        # pas d'EffectsState -> pose impossible
        if state.get_entity(ev.target_id) is None:
            return None
        rounds = electrochaff_rounds()
        # `HasEffect(Target, 0x5a6, onlyActive = 0, effectTarget = 6)` -- le mirror EXACT de ces
        # quatre arguments (cf. la docstring de `has_effect_of_type`).
        if has_effect_of_type(state, int(ev.target_id), ELECTROCHAFF_EFFECT):
            # `ChangeEffectTurns( EffectFromOwner(Target, 0x5a6), turns, ChangeType.Set )`. Le
            # `TurnsFromRounds` du natif est deja applique a l'`amount` : la duree passee a
            # l'operation est en TOURS, comme `AddEffect(duration_rounds=...)` la convertit de son
            # cote. `EffectFromOwner` rend UNE instance -> la premiere non consommee de ce type.
            turns = convert_rounds_to_turns(state, rounds)
            inst = next((e for e in state.effects.by_unit.get(int(ev.target_id), [])
                         if not e.consumed and e.effect_type == ELECTROCHAFF_EFFECT), None)
            new_turns = ChangeEffectTurnsOperation.execute(state, inst, turns, _CHANGE_SET)
            return {"ability": ELECTROCHAFF_BACKUPS_ID, "owner": int(self.owner_id),
                    "affected": int(ev.target_id), "refreshed": new_turns is not None,
                    "turns": new_turns, "placed": False, "on_event": int(ev.event_id)}
        ectx = ExecutionContext(state=state, rng=state.rng)
        electrochaff_add_effect_tree(rounds).execute(
            entities_from_state(state, self.owner_id, ev.target_id), ectx)
        placed = any(p.get("placed") for n, p in ectx.emitted if n == "AddEffect")
        return {"ability": ELECTROCHAFF_BACKUPS_ID, "owner": int(self.owner_id),
                "affected": int(ev.target_id), "refreshed": False,
                "placed": bool(placed), "rounds": rounds, "on_event": int(ev.event_id)}


class ElectrochaffBackupsOnMarkerlightAbility(_ElectrochaffBackupsBase):
    """Branche A : `On(0x3e = EffectAdded) & AreEnemies(Owner, Target) & IsNormalUnit(Target)
    & TriggeringEffectIs(0x462 = EffectType.Markerlight)`.

    Un ennemi vient de recevoir un **Markerlight** -> il porte l'Electrochaff. Le vecteur
    `effect_added_triggers` publie `triggering_effect = <le type pose>` et `target = la cible de la
    pose` : les deux canaux dont ce trigger a besoin, sans rien inventer."""
    event_id = int(EventTriggerType.EffectAdded)               # On(0x3e = 62)

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        # `TriggeringEffectIs(AbilityOrEffect(Markerlight))` -- le canal `triggering_effect`, mirror
        # d'`AbilityEntities+0x98` que `TriggeringEffectIs` compare. NON threade -> FAUX (on ne
        # fabrique pas un effet declencheur), meme convention que les autres consommateurs.
        if ev.triggering_effect is None or int(ev.triggering_effect) != MARKERLIGHT:
            return False
        return self._common(state, ev)


class ElectrochaffBackupsOnRangedDamageAbility(_ElectrochaffBackupsBase):
    """Branche B : `On(0x0f = DamageTaken) & AreEnemies(Owner, Target) & IsNormalUnit(Target)
    & IsRangedAttack()`.

    Un ennemi vient d'encaisser du degat d'une attaque a DISTANCE -> il porte l'Electrochaff.
    ⚠ AUCUN `get_OwnerIsActor` : le tireur n'a PAS a etre le Broadside (ni meme son allie) -- lu au
    decompile, le tronc commun ne contraint que le couple (Owner, Target)."""
    event_id = int(EventTriggerType.DamageTaken)               # On(0x0f = 15)

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        if not self._common(state, ev):
            return False
        # `IsRangedAttack()` = mirror du slot 3 `IdunBattle.Core.Services.BattleQuery$$
        # IsRangedAttack`. Cf. la degradation NOMMEE en en-tete (`ability_type` non threade sur ce
        # vecteur -> branche << attaque normale concrete >> = `!AreEntitiesAdjacent`).
        return _is_ranged_attack(state, ev.ability_type, ev.actor_id, ev.target_id)
