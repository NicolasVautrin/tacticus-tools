"""`IdunBattleLogic.Entities.Abilities.Triggered.Loki.HyperCorrosiveAcidAbility` -- ability
**MYTHIQUE** (`TriggeredAbilityType` 0x5af = 1455) des Machines of War `tyranBiovore` (lineup) et
`tyranNpcMowBiovore` (npc). Face RUNNER << POSE de l'effet >>. #1035.

i2 (`/Abilities/HyperCorrosiveAcid_CurrentLevelDescription`) : « Enemies that are damaged by a
friendly **Spore Mine** take +{extraDmgPct}% Damage from attacks by **Mythic** characters for
{nrOfRounds} round. »

## RE -- LE DECOMPILE, LU (`frida/classes.tsv` : parent `IdunBattle.Entities.Abilities.BaseTriggeredAbility`)

La classe DECLARE ses deux methodes (`sources_win` : `CreateTrigger` slot 24, `CreateBehaviour`
slot 26) -- rien n'est herite ici, contrairement a `BlightedLandAbility`.

`...HyperCorrosiveAcidAbility$$CreateTrigger` -- UNE seule branche, quatre conjoints :

    unitId = AbilityConfiguration$$GetStringConstant( config@<this+0x20>,
                                                     0x0 = AbilityConstantType.unitId )
    ab = AreFriends( Owner@<DSLSelectors+0x30>, Actor@<DSLSelectors+0x40>,
                     UnitTeamSelectionType.ByCurrentTeam = 0, anyEntity: false )
         & IsUnitWithVisualId( Actor@<DSLSelectors+0x40>,
                               DSLFormulas$$VisualUnitIdFromUnitId(unitId) )
    cd = AreEnemies( Owner@<DSLSelectors+0x30>, Target@<DSLSelectors+0x60>,
                     UnitTeamSelectionType.ByCurrentTeam = 0 )
         & IsAlive( Target@<DSLSelectors+0x60> )
    return op_BitwiseAnd( op_BitwiseAnd( On(0x0f = EventTriggerType.DamageTaken,
                                            ownerNeedsToBeAlive: 1),
                                         cd ),
                          ab )

⚠ L'ORDRE DE CONSTRUCTION du pseudo-C est `ab` PUIS `cd` PUIS `On`, et la composition finale est
`((On & cd) & ab)`. Une conjonction est commutative, donc l'ordre n'a pas d'observable ; ce qui en a,
c'est l'APPARIEMENT slot <-> conjoint : `AreFriends`/`IsUnitWithVisualId` portent sur l'**ACTEUR**
(`+0x40`, la source du degat), `AreEnemies`/`IsAlive` sur la **CIBLE** (`+0x60`, la victime).
Les intervertir ferait declencher l'ability quand le Biovore lui-meme frappe, au lieu de sa mine.

`...HyperCorrosiveAcidAbility$$CreateBehaviour(abilityState, triggerType)` :

    turns   = DSLFormulas$$TurnsFromRounds( AbilityConfiguration$$GetNumberConstant(
                                                config@<this+0x20>, 0x45 = nrOfRounds ) )
    ajout   = DSLBehaviors$$AddEffect( 0x5a8 = EffectType.HyperCorrosiveAcid_ExtraDamagePct,
                                       BaseTriggeredAbility$$get_AbilityStateReference(this),
                                       source  = Owner@<DSLSelectors+0x30>,
                                       targets = Target@<DSLSelectors+0x60>,
                                       turns )
    refresh = DSLBehaviors$$ChangeEffectTurns( owner      = Target@<DSLSelectors+0x60>,
                                               effectType = 0x5a8,
                                               amount     = turns,
                                               changeType = 1 = ChangeType.Set )
    cond    = DSLTriggers$$HasEffect( Target@<DSLSelectors+0x60>, 0x5a8,
                                      onlyActive = 0, effectTarget = 6 )
    return DSLBehaviors$$If( cond, refresh, ajout )

C'est le MEME behaviour qu'`ElectrochaffBackups` (#1025) au type d'effet pres -- refresh-or-add,
`ChangeType.Set` (une re-explosion REMET la duree a `turns`, elle ne l'accumule PAS ; lu au 5e
argument du call-site `CONCAT44(hi, 1)`), `onlyActive = 0` (une instance INERTE compte comme
« deja presente »).

`nrOfRounds` vaut **"1"** et `unitId` vaut **"tyranSmnSporeMine"** au gameconfig (les `constants`
sont des CHAINES) : LUS, jamais codes en dur.

## LE GATE `IsUnitWithVisualId` -- LE NATIF COMPARE **UNE** CHAINE

`IdunBattle.Entities.Selectors.IsUnitWithVisualIdTrigger$$ShouldTrigger`, corps entier :

    unit  = <selecteur @+0x10>.SelectUnit(entities);      if (unit == null)  return false;
    value = <formule   @+0x18>.Calculate(entities);       if (!HasValue)     return false;
    return System.String.op_Equality( UnitExtensions$$GetVisualUnitId(unit), value.Value );

-> une egalite de CHAINES, pas une appartenance. Le noeud Python `VisualUnitIdFromUnitId`, lui, rend
DEUX formes (`[unitId, gameconfig.unit(unitId).visualId]`) par la REDUCTION OFFLINE deja documentee
dans son propre docstring : le champ `visualId` du port porte l'id de CONFIG pour une unite spawnee
offline et l'id VISUEL pour une unite seedee du live. Composer les deux noeuds tels quels comparait
donc une `str` a une `list` -> **FAUX systematique, sans erreur**. `IsUnitWithVisualId` accepte
desormais les deux formes (cf. son docstring) ; ce module est son PREMIER consommateur executable.

## CE QUI EST PORTE ICI, ET CE QUI NE L'EST PAS

PORTE : le TRIGGER (les quatre conjoints) et le BEHAVIOUR (`If`/`ChangeEffectTurns`/`AddEffect`).
Aucun de ces noeuds ne porte de gate de RARETE -- cette face est integralement confrontable.

NON PORTE : l'EFFET 0x5a8 = 1448 lui-meme (`IdunBattle.Entities.Effects.Loki.
HyperCorrosiveAcid_ExtraDamagePctEffect`), dont le `$$CreateEffectDamageBonusForAttack` est

    EffectBonus$$ForPercentIncrease(
        get_OwnerIsTarget
        & ( AreFriends( Caster@<DSLSelectors+0x48>,
                        EffectSource(Effect@<DSLSelectors+0x38>), 0, false )
            & HasRarity( Caster@<DSLSelectors+0x48>, 5 = Rarity.Mythic )
            & HasTrait( Caster@<DSLSelectors+0x48>, 0x10 = UnitTrait.Hero ) ),
        DSLFormulas$$ConfigVar( 0xa = AbilityVariableType.extraDmgPct,
                                GetAbilityState(effet), effet@+0x60 ) )

`HasRarity(..., 5)` lit `GetBaseUnitComponent(entity)+0x74` et **aucun canal `rarity` n'existe cote
port** -- meme verrou qu'`ElectrochaffBackups` (`#1025-r1`). L'inscrire sans ce gate serait un terme
PERMISSIF (tout attaquant ami du Biovore beneficierait du +extraDmgPct, pas seulement les Mythiques
Hero), pas un port : l'effet reste donc HORS d'`EFFECT_CLASSES`, ce qui rend `BaseEffect` generique
et TOUS ses canaux muets -- degradation RESTRICTIVE et nommee. Residu `#1035-r1`.

⚠ CE VERROU EST DEJA MESURE DE BOUT EN BOUT PAR `docs/rl/case-1024-shield-of-faith-on-my-position.md`
Sec.4 -- ne pas le re-mesurer, le LIRE. Trois faits qu'elle etablit et dont ce port depend :
l'enum EXISTE (`IdunMetaLogic.UserProgress.Model.UnitRarity`, `5 = Mythic`) ; `BC.Units[].Rarity`
ATTEINT bien `BaseUnitComponent.Rarity` (contre-epreuve live `--unit-stat "<vis>:Rarity=4"`, qui
ETEINT le gate) ; et `rl_duel build` pose `targetRarity = 5`, donc **dans un runner standard toute
unite est Mythic et `HasRarity(., Mythic)` est uniformement VRAI** -- un port qui OUBLIERAIT le gate
serait d'accord avec le natif dans tous les bras par defaut. C'est le regime DEGENERE, et c'est
exactement pourquoi le canal de degat de 1448 ne peut pas etre porte << au jugé >>.

APPORT DE CETTE TRANCHE sur ce seul point : la VOIE que `readUnitConfig` peut prendre sans changer
de structure. `case-1024` prescrit de resoudre `BaseUnitComponent.Rarity` par `getFieldOffset` (a
cause du piege `0x74`, qui vaut `AbilityVariablesMultiplierPercentage` dans `UnitConfiguration` et
la RARETE dans `BaseUnitComponent`). Or `readUnitConfig` tient DEJA le pointeur
`UnitConfiguration` : `IdunBattle.Entities.Factories.UnitFactory$$InitBaseComponent` fait
`BaseUnitComponent+0x74 = UnitConfiguration+0x80`, et `UnitConfiguration+0x80` EST le champ
`Rarity` (`sources_win`, ancre par ses deux voisins DEJA portes -- `+0x74
AbilityVariablesMultiplierPercentage` et `+0x78 TertiaryAbilityVariablesMultiplierPercentage`, que
`UnitContext` cite aux memes offsets). Le capteur se reduit donc a UN champ de plus dans le dict
que `readUnitConfig` rend deja, resolu comme ses voisins par
`getFieldOffset(unitConfigurationClass, "Rarity")` -- jamais par recopie de `0x80`. Cela exige une
FENETRE DE REINJECT, que cette tranche n'a pas le droit d'ouvrir. Residu `#1035-r1`.

## DISPATCH -- le vecteur est DEJA emis par le port

`On(0x0f = DamageTaken)` -> `dispatch/attack.damage_taken_triggers` (emis par
`_apply_damage_pipeline` apres la mutation des PV) : `actor` = la SOURCE du degat, `target` = la
VICTIME. Ce sont exactement les deux slots dont ce trigger a besoin, sans rien inventer.

⚠ AUCUNE degradation `IsRangedAttack` ici, contrairement a `ElectrochaffBackups` : ce trigger ne lit
ni `ability_type` ni le profil du coup -- il ne regarde que QUI frappe (l'acteur est-il une Spore
Mine amie ?) et QUI encaisse (un ennemi vivant ?).
"""
from __future__ import annotations

from typing import Optional

from ....state import State
from ....components import has_effect_of_type
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.effects import AddEffect
from .....entities.selectors.accessors import Actor, Owner, Target
from .....entities.ability_constant_type import AbilityConstantType
from .....entities.effect_type import EffectType
from .....entities.formulas import VisualUnitIdFromUnitId
from .....entities.triggered_ability_type import TriggeredAbilityType
from .....entities.triggers import AreEnemies, AreFriends, IsAlive, IsUnitWithVisualId
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from ..base import TriggeredAbility, TriggerEvent
from ...effects import ChangeEffectTurnsOperation
from ....abilities.base import convert_rounds_to_turns

#: Nom gameconfig de l'ability (cle des `mythicAbilities` de `tyranBiovore`) -- c'est par ce NOM que
#: le registre de dispatch l'indexe, et c'est lui que porte `UnitContext.tertiary_ability` quand
#: `catalog_inject.equip_mythic` l'a ecrite dans `BC.Units[].TertiaryAbility`.
HYPER_CORROSIVE_ACID_ID = "HyperCorrosiveAcid"
#: `TriggeredAbilityType` 0x5af = 1455 -- l'id que porte `BC.Units[].TertiaryAbility`.
HYPER_CORROSIVE_ACID = TriggeredAbilityType.HyperCorrosiveAcid
#: `EffectType` 0x5a8 = 1448 -- l'effet pose sur l'ennemi (`AddEffect` du behaviour).
HYPER_CORROSIVE_ACID_EFFECT = int(EffectType.HyperCorrosiveAcid_ExtraDamagePct)
#: `AbilityConstantType` 0x45 = 69 -- `GetNumberConstant(config, nrOfRounds)`.
CONST_NR_OF_ROUNDS = AbilityConstantType.nrOfRounds
#: `AbilityConstantType` 0x0 -- `GetStringConstant(config, unitId)` = "tyranSmnSporeMine".
CONST_UNIT_ID = AbilityConstantType.unitId
#: `HasEffect(..., effectTarget = 6)` = `2|4` (owned | targeted) -- cote port les deux branches
#: coincident, l'`EffectsState` etant indexee par ENTITE PORTEUSE. Cf. `has_effect_of_type`.
_EFFECT_TARGET_OWNED_OR_TARGETED = 6
#: `ChangeType.Set` (`IdunBattle.Entities.Enum.ChangeType` 1) -- le 5e argument du call-site.
_CHANGE_SET = ChangeEffectTurnsOperation.CHANGE_SET

#: Les quatre conjoints de `$$CreateTrigger`, un noeud DSL chacun (le `On(0x0f)` est COLLAPSE en
#: `event_id`, cf. doctrine #149). `AreFriends`/`AreEnemies` prennent leur `selection_type` par
#: defaut = `UnitTeamSelectionType.ByCurrentTeam`, ce que passent les deux call-sites natifs (`0`).
_OWNER_ACTOR_FRIENDS = AreFriends(Owner(), Actor())          # AreFriends(Owner@+0x30, Actor@+0x40)
_OWNER_TARGET_ENEMIES = AreEnemies(Owner(), Target())        # AreEnemies(Owner@+0x30, Target@+0x60)
_TARGET_IS_ALIVE = IsAlive(Target())                         # IsAlive(Target@+0x60)


def hyper_corrosive_rounds() -> int:
    """`AbilityConfiguration$$GetNumberConstant(config@<this+0x20>, 0x45 = nrOfRounds)` -- LU au
    gameconfig, jamais en dur. Les `constants` du gameconfig sont des CHAINES (`"1"`), d'ou le
    `int(...)`. Absent -> 0, ce qui rend `TurnsFromRounds(0)` et donc une pose de duree nulle : le
    natif ferait pareil (`GetNumberConstant` sur une cle absente rend 0)."""
    import gameconfig as GC                                    # noqa: PLC0415
    consts = (GC.ability(HYPER_CORROSIVE_ACID_ID) or {}).get("constants") or {}
    return int(consts.get(CONST_NR_OF_ROUNDS.name) or 0)


def hyper_corrosive_unit_id():
    """`AbilityConfiguration$$GetStringConstant(config@<this+0x20>, 0x0 = unitId)` =
    `"tyranSmnSporeMine"` -- LU au gameconfig. Absent -> `None`, et le gate rend alors FAUX
    (le natif ferait pareil : `Calculate` sans valeur -> `HasValue == false` -> `return false`)."""
    import gameconfig as GC                                    # noqa: PLC0415
    consts = (GC.ability(HYPER_CORROSIVE_ACID_ID) or {}).get("constants") or {}
    return consts.get(CONST_UNIT_ID.name)


def hyper_corrosive_actor_is_spore_mine() -> IsUnitWithVisualId:
    """`IsUnitWithVisualId( Actor@<DSLSelectors+0x40>, VisualUnitIdFromUnitId(GetStringConstant(
    unitId)) )` -- MIRROR 1:1 de la composition native, les deux noeuds tels quels.

    Construit a CHAQUE appel (et non une constante de module) parce que la constante gameconfig est
    lue paresseusement : figer le noeud au chargement du module lirait le gameconfig a l'import."""
    return IsUnitWithVisualId(Actor(), VisualUnitIdFromUnitId(hyper_corrosive_unit_id()))


def hyper_corrosive_add_effect_tree(rounds: int) -> AddEffect:
    """Branche `else` de `$$CreateBehaviour` (MIRROR 1:1) :

        AddEffect( 0x5a8, get_AbilityStateReference(this),
                   source = Owner@<DSLSelectors+0x30>, targets = Target@<DSLSelectors+0x60>,
                   turns  = TurnsFromRounds(GetNumberConstant(nrOfRounds)) )

    `Target()` (unit-domain) resout la cible de l'evenement ; `source_ref = Owner()` CITE le 3e
    argument natif -- sur une triggered-ability `Owner == Caster`, donc identique au defaut du port,
    mais le slot cite est celui que le natif cite."""
    return AddEffect(HYPER_CORROSIVE_ACID_EFFECT, "HyperCorrosiveAcid_ExtraDamagePct",
                     Target(), duration_rounds=rounds, source_ref=Owner())


class HyperCorrosiveAcidAbility(TriggeredAbility):
    """`HyperCorrosiveAcidAbility` (mythique 0x5af = 1455 de `tyranBiovore`).

    OBSERVABLE : chaque fois qu'une **Spore Mine** amie inflige du degat a un ennemi VIVANT, cet
    ennemi porte (ou voit rafraichir a `nrOfRounds`) l'effet 1448."""
    event_id = int(EventTriggerType.DamageTaken)               # On(0x0f = 15, ownerNeedsToBeAlive: 1)
    TRIGGERED_ABILITY_ID = int(TriggeredAbilityType.HyperCorrosiveAcid)   # 0x5af = 1455

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        """Les quatre conjoints de `$$CreateTrigger`, evalues sur l'`AbilityEntities` de l'evenement
        (`owner`/`caster` = le porteur, `actor` = la source du degat, `target` = la victime)."""
        if ev.actor_id is None or ev.target_id is None:
            return False
        entities = entities_from_state(state, self.owner_id, ev.target_id, ev.actor_id)
        # `AreEnemies(Owner@+0x30, Target@+0x60, 0)` puis `IsAlive(Target@+0x60)` : la victime est un
        # ennemi du porteur, et elle SURVIT au coup (le vecteur `On(0x0f)` est emis APRES la mutation
        # des PV, donc une cible tuee y est deja `alive = False`).
        if not _OWNER_TARGET_ENEMIES.should_trigger(entities):
            return False
        if not _TARGET_IS_ALIVE.should_trigger(entities):
            return False
        # `AreFriends(Owner@+0x30, Actor@+0x40, 0, false)` : la source du degat est un ALLIE du
        # porteur (la Spore Mine est un summon du Biovore, donc sur l'equipe du summoner).
        if not _OWNER_ACTOR_FRIENDS.should_trigger(entities):
            return False
        # `IsUnitWithVisualId(Actor@+0x40, VisualUnitIdFromUnitId(GetStringConstant(unitId)))` :
        # c'est bien une SPORE MINE qui frappe, pas le Biovore ni un autre allie.
        return bool(hyper_corrosive_actor_is_spore_mine().should_trigger(entities))

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        """`$$CreateBehaviour` (MIRROR 1:1) :
        `If( HasEffect(Target, 0x5a8, onlyActive: 0, effectTarget: 6),
             ChangeEffectTurns(Target, 0x5a8, turns, ChangeType.Set),
             AddEffect(0x5a8, ..., Target, turns) )`."""
        if state.effects is None or ev.target_id is None:
            return None                                        # pas d'EffectsState -> pose impossible
        if state.get_entity(ev.target_id) is None:
            return None
        rounds = hyper_corrosive_rounds()
        # `HasEffect(Target, 0x5a8, onlyActive = 0, effectTarget = 6)` -- le mirror EXACT de ces
        # quatre arguments (cf. la docstring de `has_effect_of_type`).
        if has_effect_of_type(state, int(ev.target_id), HYPER_CORROSIVE_ACID_EFFECT):
            # `ChangeEffectTurns( EffectFromOwner(Target, 0x5a8), turns, ChangeType.Set )`. Le
            # `TurnsFromRounds` du natif est deja applique a l'`amount` : la duree passee a
            # l'operation est en TOURS, comme `AddEffect(duration_rounds=...)` la convertit de son
            # cote. `EffectFromOwner` rend UNE instance -> la premiere non consommee de ce type.
            turns = convert_rounds_to_turns(state, rounds)
            inst = next((e for e in state.effects.by_unit.get(int(ev.target_id), [])
                         if not e.consumed and e.effect_type == HYPER_CORROSIVE_ACID_EFFECT), None)
            new_turns = ChangeEffectTurnsOperation.execute(state, inst, turns, _CHANGE_SET)
            return {"ability": HYPER_CORROSIVE_ACID_ID, "owner": int(self.owner_id),
                    "affected": int(ev.target_id), "refreshed": new_turns is not None,
                    "turns": new_turns, "placed": False, "on_event": int(ev.event_id)}
        ectx = ExecutionContext(state=state, rng=state.rng)
        hyper_corrosive_add_effect_tree(rounds).execute(
            entities_from_state(state, self.owner_id, ev.target_id), ectx)
        placed = any(p.get("placed") for n, p in ectx.emitted if n == "AddEffect")
        return {"ability": HYPER_CORROSIVE_ACID_ID, "owner": int(self.owner_id),
                "affected": int(ev.target_id), "refreshed": False,
                "placed": bool(placed), "rounds": rounds, "on_event": int(ev.event_id)}
