"""`GeminaeSuperia` (`TriggeredAbilityType.GeminaeSuperia` = 1048 = 0x418) -- passif de kit de
`adeptCelestine` << Celestine >> (HERO Sisterhood, Legendary). RE : decompile ghidra, build
`rnca9r7q6c` (#963).

i2 : « When attacked, summons a Geminae Superia in a free adjacent hex, and immediately triggers its
passive ability Lifewards. Can do this twice per battle. »

## CE QUI EXISTAIT DEJA (recense AVANT de porter)

Ce passif n'etait PAS absent du depot : il etait porte sur son AUTRE FACE.
  * `engine/playbook/geminae_superia.py` -- `GeminaeSuperiaPlaybook`, face DECISION / MOUVEMENT
    (case-165b), inscrit dans `TRIGGERED_MOVE_PLAYBOOKS` sous `TriggeredAbilityType.GeminaeSuperia`.
    RE-CONFRONTE au decompile pour cette tranche
    (`GeminaeSuperiaPlaybook.u003CCalculateMovementUtilityInStepsInternalu003Ed__3$$MoveNext` et
    `...$$OwnerInAdjacentTile`) : les TROIS termes sont JUSTES. Seule une CITATION etait imprecise
    (`get_CasterTile` la ou le natif appelle
    `IdunBattle.AI.Utilities.UtilityMovementCase$$get_MovementTile`), corrigee dans le meme commit.
  * `engine/entities/triggered_ability_type.py` (1048) et `engine/entities/effect_type.py`
    (`GeminaeSuperia_JustSummonedEffect` = 1061) -- les deux mirrors d'enum.
  * DEUX **lecteurs** de l'effet 1061, tous deux annotes « NO-OP offline tant qu'aucun poseur de
    1061 n'est porte » : `engine/runner/operations/spawn.py` (le `RemoveEffect(1061)` prealable de
    `MasterOfTheTutelaries_SummonAbility`) et `engine/runner/abilities/loki/momentum.py`.
    Ce port est le POSEUR qui manquait : il les arme.

Ce qui manquait, et que ce module apporte : la face COMBAT (aucune entree dans les quatre registres
de trigger).

## L'arbre natif, lu verbatim

`GeminaeSuperiaAbility` a pour base `IdunBattle.Entities.Abilities.BaseTriggeredAbility` -- LUE dans
`data/symbols/<build>/frida/classes.tsv`, PAS deduite du namespace, qui dit `Abilities.**Active**.Loki`
(meme piege que `MedicusMinistorum`). C'est une passiveAbility.

`GeminaeSuperiaAbility$$CreateTrigger` =

    On(0x39 = PreDamageTaken, ownerNeedsToBeAlive = 0)
      & IsFirstDamagingHitInSeries
      & get_OwnerIsTarget
      & AmountIsGreaterThanZero( GetPossibleSpawnTiles() )
      & SummonLimit()

`GeminaeSuperiaAbility$$GetPossibleSpawnTiles` =

    CanAddUnit( AdjacentTiles(Owner@<DSLSelectors+0x30>)
                op_Subtraction
                PendingMovingTile(Owner@<+0x30>) )

`GeminaeSuperiaAbility$$SummonLimit` (methode NOMMEE, inline dans `CreateTrigger`) =

    op_LogicalNot( AmountIsEqualOrGreater(
        UnitsWithId( Children(Owner@<+0x30>),                       // DSLSelectors$$Children(parent)
                     GetStringConstant(config, 0 = unitId),
                     UnitSelectionType.Any = 0 ),
        DSLFormulas.Get(2) ) )                                      // LITTERAL 2

`GeminaeSuperiaAbility$$CreateBehaviour` =

    unitId = GetStringConstant(config, 0 = AbilityConstantType.unitId)   // adeptSmnGeminaeSuperia
    opts   = SpawnUnitOptions.WithStatsFromConfig(config, abilityState, null, null)
    opts.<+0x10> = AddEffect( 0x425 = GeminaeSuperia_JustSummonedEffect,
                              BaseTriggeredAbility$$get_AbilityStateReference(this),
                              targets = Target@<DSLSelectors+0x60>,
                              turns   = null )
    tiles  = PickRandomly( GetPossibleSpawnTiles(), 1, allowDuplicates = 0,
                           maxDuplicatesAllowed = 0x7fffffff, ignoreForcedTargets = false )
    spawnB = Spawn( parentSelector = Owner@<+0x30>, tiles, unitId, opts )
    trigB  = TriggerAbility( entity = Last(Children(Owner@<+0x30>), 1, ignoreForcedTargets = true),
                             triggeredAbilityType = 0x419 = TriggeredAbilityType.Lifewards,
                             actor = Actor@<+0x40>, caster = Caster@<+0x48>, target = Owner@<+0x30>,
                             unitFeetTiles = null,
                             selectionType = UnitSelectionType.OnlyAlive = 1,
                             ignoreUnitHavingAbility = false )
    return spawnB op_BitwiseAnd trigB

QUATRE points tranches AU DECOMPILE, pas au tooltip :

  1. LE CAP COMPTE LES GEMINAE POSEES, MORTES COMPRISES. `UnitsWithId(..., 0)` est
     `UnitSelectionType.Any`, et `DSLSelectors$$Children` ne filtre PAS `alive` (le port en a deja
     la mesure : `ChildrenOf`, #590, « AUCUN filtre alive ici »). Le « twice per battle » de l'i2
     est donc un cap d'USAGES, pas « deux vivantes a la fois » -- tuer la premiere Geminae ne rend
     pas une charge. Ecrire `Alive(...)` ici serait plus PERMISSIF que le natif.
  2. `Get(2)` EST UN LITTERAL, pas une variable de config : la config `GeminaeSuperia` ne porte que
     `unitId` en constante et `summonHp`/`summonDmg`/`summonArmor` en variables. Le 2 est ecrit dans
     l'ability native.
  3. `IsFirstDamagingHitInSeries` N'EST PAS `IsFirstHitInSeries`. Le premier lit
     `AbilityEntities+0x118` (`isFirstDamagingHit`, 29e parametre NOMME du ctor) DIRECTEMENT ; le
     second passe par `get_IsFirstHit` (`+0x108` = `hitIndex == 0`). Les confondre ferait spawner sur
     un coup entierement bloque. Mesure et correction des citations : `entities/triggers.py`.
  4. LE MARQUEUR 1061 VA SUR `Target@+0x60`, donc -- le trigger exigeant `get_OwnerIsTarget` -- sur
     CELESTINE elle-meme, pas sur la Geminae. Et contrairement a son jumeau `SwornProtector` (meme
     champ `opts+0x10`), l'arbre ne le RETIRE PAS : il persiste.

## CRITERE D'EMETTEUR -- LE **NON** DE CETTE TRANCHE

`On(0x39 = PreDamageTaken)` **n'avait AUCUN emetteur cote port** : recensement executable au moment
de l'ouverture (tout `TriggerEvent(EventTriggerType.X, ...)` construit dans `engine/**`) -> **40
types emis, celui-ci absent des 40**. Inscrire ce passif sans rien d'autre l'aurait fait entrer
*registered-but-dead* : aucun test d'appartenance au registre ne l'aurait vu.

Le vecteur a donc ete CREE dans le meme commit -- `pre_damage_taken_triggers`
(`triggers/dispatch/attack.py`), et sa PLACE d'emission LUE AUX OCTETS dans
`IdunBattle.Operations.ApplyDamageOperation$$Execute` : apres le gate `Overkilled`, sous
`0 < DamageAppliedResult$$get_Damage(result)`, et **AVANT** la mutation des PV
(`FillUpStatComponent$$Reduce`). C'est ce qui fait que Celestine est encore a pleine vie quand la
Geminae apparait. Les trois publications de cette operation ont ete relues (`0x39`, `0xf`, `0x10`) --
au passage, la citation « sequence `0x3a` -> `0xf` -> `0x10` » de `operations/damage.py` etait une
COQUILLE (`0x3a` = `PhaseEnd`), corrigee.

## FORME DU PORT (doctrine #149)

L'artefact natif est un `CreateTrigger` + un `CreateBehaviour` : ARBRE DSL. Tout le vocabulaire
existait sauf DEUX primitives, portees ici :
  * `PendingMovingTile` (`entities/selectors/tiles.py`) -- selecteur ;
  * `IsFirstDamagingHitInSeries` (`entities/triggers.py`) -- trigger ;
et un champ d'options (`SpawnUnitOptions+0x10` -> `Spawn(on_spawn_effect=...)`).

RESIDUS NOMMES :
  * `TriggerAbility(Lifewards)` : le registre `TRIGGERED_ABILITY_BEHAVIOURS` ne porte PAS 1049
    (`Lifewards` est le passif du SUMMON, hors du couple de cette tranche). La feuille rend donc
    `dispatched: False` -- le gap est VISIBLE dans les events, jamais muet. Le transfert de degat
    (`LifewardsAbility$$CreateBehaviour` = `AddBondEffect(0x424)` + `AddBondEffect(0x4d8)` +
    `TransferDamage`) reste a porter -> `#963-r3`.
  * `selectionType = OnlyAlive = 1` et `ignoreUnitHavingAbility = false` du `TriggerAbility` : la
    feuille portee n'expose pas ces deux champs (residu PARTAGE par tous ses call-sites).
  * `PendingMovingTile` rend `[]` cote port : le deplacement y est ATOMIQUE, il n'existe aucun etat
    « en cours de mouvement ». La soustraction est donc INERTE -- fidele au regime du port, et ecrite
    quand meme pour que la structure native reste lisible.
"""
from __future__ import annotations

from typing import Optional

from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.ability_constant_type import AbilityConstantType
from .....entities.behaviours import Seq
from .....entities.effect_type import EffectType
from .....entities.formulas import Count
from .....entities.selectors.geometry import PickLastN, PickRandomly, UnitsWithId
from .....entities.selectors.tiles import (AdjacentTiles, CanAddUnit, Caster, ChildrenOf,
                                           PendingMovingTile)
from .....entities.selectors.units import Sub
from .....entities.triggered_ability_type import TriggeredAbilityType
from .....entities.triggers import AmountIsEqualOrGreater, AmountIsGreaterThanZero, Not, OwnerIsTarget
from .....entities.unit_selection_type import UnitSelectionType
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.effects import AddEffect
from ....abilities.behaviours.lifecycle import TriggerAbility
from ....abilities.behaviours.summon import Spawn
from ....components import StatsComponent
from ....state import State
from ..base import TriggeredAbility, TriggerEvent

ABILITY_ID = "GeminaeSuperia"
SUMMON_UNIT_ID_CONSTANT = AbilityConstantType.unitId          # `GetStringConstant(config, 0)`
JUST_SUMMONED_EFFECT = EffectType.GeminaeSuperia_JustSummonedEffect     # 0x425 = 1061
LIFEWARDS = TriggeredAbilityType.Lifewards                    # 0x419 = 1049
# `DSLFormulas.Get(2)` -- LITTERAL de l'ability native, pas une variable de config (en-tete point 2).
SUMMON_LIMIT = 2
# `UnitsWithId(Children(Owner), unitId, 0)` : `Any` -> les Geminae MORTES comptent (en-tete point 1).
SUMMON_COUNT_SELECTION = UnitSelectionType.Any                # = 0
PICK_MAX_DUPLICATES = 0x7FFFFFFF                              # `maxDuplicatesAllowed` du PickRandomly

_ON_PRE_DAMAGE_TAKEN = int(EventTriggerType.PreDamageTaken)   # 0x39 = 57


def geminae_possible_spawn_tiles():
    """`GeminaeSuperiaAbility$$GetPossibleSpawnTiles` =
    `CanAddUnit( AdjacentTiles(Owner@<+0x30>) op_Subtraction PendingMovingTile(Owner@<+0x30>) )`.

    Une NOUVELLE instance a chaque appel, EXPRES : le natif appelle cette fabrique depuis
    `CreateTrigger` **et** depuis `CreateBehaviour`.

    `Owner@+0x30` est rendu par `Caster()` (pour une `BaseTriggeredAbility`, owner == caster).
    La soustraction est ecrite telle quelle bien que `PendingMovingTile` rende `[]` cote port
    (cf. le residu en en-tete)."""
    return CanAddUnit(Sub(AdjacentTiles(Caster()), PendingMovingTile(Caster())))


def geminae_summoned_units():
    """Le sous-arbre commun a `SummonLimit` et au terme de meme nom de `CreateTrigger` :

        UnitsWithId( Children(Owner@<+0x30>), GetStringConstant(config, 0), UnitSelectionType.Any = 0 )

    `Children(parent)` est `IdunBattleLogic.Entities.DSLSelectors$$Children` (AVEC argument), donc
    `ChildrenOf` -- **pas** l'accumulateur `Children()` du cast courant (#590 : les confondre rend
    un selecteur toujours vide, sans erreur). C'est ce qui fait que le cap survit d'un cast a
    l'autre."""
    return UnitsWithId(ChildrenOf(Caster()), _summon_unit_id(), int(SUMMON_COUNT_SELECTION))


def _summon_unit_id():
    """`IdunBattle.Configuration.AbilityConfiguration$$GetStringConstant(config, 0 = unitId)` =
    `gameconfig.abilities.GeminaeSuperia.constants.unitId` = `adeptSmnGeminaeSuperia`.

    MEME lecture que `GeminaeSuperiaPlaybook.summon_unit_ids` (face DECISION), volontairement : les
    deux faces resolvent la MEME constante native. `None` = cle absente -> le selecteur ne matche
    rien (le gate `SummonLimit` passe alors, mais le `Spawn` est de toute facon un no-op :
    `Spawn.execute` sort quand `GetStringConstant` rend None)."""
    import gameconfig as GC
    return ((GC.ability(ABILITY_ID) or {}).get("constants") or {}).get(SUMMON_UNIT_ID_CONSTANT.name)


def geminae_summon_limit_tree():
    """`GeminaeSuperiaAbility$$SummonLimit` =
    `op_LogicalNot( AmountIsEqualOrGreater(<geminae_summoned_units>, Get(2)) )`.

    Methode NOMMEE du natif, mirroree telle quelle : c'est le cap « twice per battle »."""
    return Not(AmountIsEqualOrGreater(Count(geminae_summoned_units()), SUMMON_LIMIT))


def geminae_trigger_tree():
    """`GeminaeSuperiaAbility$$CreateTrigger`, moins le volet `On(0x39)` que porte le DISPATCH et
    moins `IsFirstDamagingHitInSeries` (lu sur l'EVENEMENT, cf. `matches`) :

        get_OwnerIsTarget
          & AmountIsGreaterThanZero( GetPossibleSpawnTiles() )
          & SummonLimit()

    ⚠ `ownerNeedsToBeAlive` vaut **0** ici (2e argument d'`On`), contrairement a la plupart des
    passifs -- le gate « owner vivant » du dispatch reste neanmoins celui du port
    (`CanGetAbilityTrigger`), residu PARTAGE, sans effet observable : sur `PreDamageTaken` la
    victime est encore vivante par construction (l'event precede la mutation de PV).

    ZERO tirage PRNG : aucun `PickRandomly` dans ce sous-arbre (celui du behaviour, lui, en
    consomme un)."""
    from .....entities.triggers import TriggerAnd
    return TriggerAnd(TriggerAnd(OwnerIsTarget(),
                                 AmountIsGreaterThanZero(Count(geminae_possible_spawn_tiles()))),
                      geminae_summon_limit_tree())


def _ability_state_of(state: State, owner_id: int):
    """Le 2e argument de `SpawnUnitOptions$$WithStatsFromConfig(config, abilityState, null, null)` :
    le couple `(niveau, multiplicateur)` sous lequel la Geminae monte ses stats ET ses propres
    passives. `GeminaeSuperia` est un PASSIF -> slot `passive_ability_level`, JAMAIS `active`."""
    e = state.get_entity(owner_id)
    sc = e.get_component(StatsComponent) if e is not None else None
    ctx = getattr(sc, "ctx", None) if sc is not None else None
    if ctx is None:
        return None
    return (getattr(ctx, "passive_ability_level", None),
            int(getattr(ctx, "ability_variables_multiplier", 100) or 100))


def geminae_behaviour_tree(ability_state):
    """`GeminaeSuperiaAbility$$CreateBehaviour` = `Spawn(...) op_BitwiseAnd TriggerAbility(...)`.

    `op_BitwiseAnd` alloue la MEME `CombinedBehaviour` que `op_Addition` -> noeud `Seq`. L'ORDRE est
    load-bearing : le `Last(Children(Owner), 1)` du second terme doit voir la Geminae que le premier
    vient de poser (la feuille `Spawn` pousse chaque enfant dans `entities.units` ET
    `entities.children`, mirror de la ref d'etat native).

    `opts.<+0x10>` = le marqueur 1061, pose sur `Target@+0x60` -- donc sur CELESTINE (le trigger
    exige `get_OwnerIsTarget`), et JAMAIS retire par cet arbre (en-tete point 4)."""
    marker = AddEffect(int(JUST_SUMMONED_EFFECT), JUST_SUMMONED_EFFECT.name, Caster(),
                       duration_rounds=None, duration_turns=None)     # `turns = null` du natif
    spawn = Spawn(geminae_possible_spawn_tiles(), ABILITY_ID, pick_n=1,
                  unit_id_constant=SUMMON_UNIT_ID_CONSTANT.name,
                  ability_state=ability_state,
                  on_spawn_effect=marker)                             # `SpawnUnitOptions+0x10`
    # `Last(Children(Owner@+0x30), 1, ignoreForcedTargets = true)` = la DERNIERE Geminae posee.
    last_summon = PickLastN(ChildrenOf(Caster()), 1, ignore_forced_targets=True)
    return Seq(spawn, TriggerAbility(last_summon, int(LIFEWARDS)))


class GeminaeSuperiaAbility(TriggeredAbility):
    """`GeminaeSuperiaAbility` (`TriggeredAbilityType` 0x418 = 1048, passif `adeptCelestine`)
    -- cf. l'en-tete du module pour la chaine native, le recensement de l'existant et les residus.

    `On(0x39 = PreDamageTaken) & IsFirstDamagingHitInSeries & OwnerIsTarget
     & AmountIsGreaterThanZero(GetPossibleSpawnTiles()) & SummonLimit()`
    -> `Spawn(<1 hex libre adjacent>, adeptSmnGeminaeSuperia, stats du passif, marqueur 1061 sur
       Celestine) & TriggerAbility(<la Geminae posee>, Lifewards)`."""
    event_id = _ON_PRE_DAMAGE_TAKEN
    TRIGGERED_ABILITY_ID = int(TriggeredAbilityType.GeminaeSuperia)      # 0x418 = 1048

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        """`CreateTrigger` moins le volet `On(0x39)` du dispatch.

        `IsFirstDamagingHitInSeries` est lu sur l'EVENEMENT (`ev.is_first_damaging_hit`), comme
        `ThrillSeekersFullHealthTargetAbility` lit `ev.is_first_hit` pour `IsFirstHitInSeries` : le
        canal natif est le champ `AbilityEntities+0x118`, que seul l'emetteur renseigne.
        `None` = `Nullable` vide -> `false` (mirror de
        `IsFirstDamagingHitInSeriesTrigger$$ShouldTrigger`)."""
        if not ev.is_first_damaging_hit:
            return False
        entities = entities_from_state(state, self.owner_id, ev.target_id, actor_id=ev.actor_id)
        return bool(geminae_trigger_tree().evaluate(entities))

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, self.owner_id, ev.target_id, actor_id=ev.actor_id)
        geminae_behaviour_tree(_ability_state_of(state, self.owner_id)).execute(entities, ectx)
        spawned = [p.get("unit") for (n, p) in ectx.emitted if n == "SpawnUnit"]
        trig = next((p for (n, p) in ectx.emitted if n == "TriggerAbility"), None)
        return {"passive": ABILITY_ID, "owner": int(self.owner_id),
                "spawned": spawned,
                "lifewards_targets": (trig.get("targets") if trig else None),
                "lifewards_dispatched": (trig.get("dispatched") if trig else None),
                "dsl": True}
