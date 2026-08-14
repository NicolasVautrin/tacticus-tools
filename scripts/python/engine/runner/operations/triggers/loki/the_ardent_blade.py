"""`TheArdentBlade` -- RELIQUE d'`adeptCelestine` (`TriggeredAbilityType` 0x5bc = 1468).
Tache #1013-r2, face COMBAT. RE : decompile ghidra, build `rnca9r7q6c`. RE detaillee (etage
`DeactivateEffect`, surcharges de `SortTilesByUtilityForSummon`, inventaire des 11 symboles) :
`docs/rl/case-1013r2-the-ardent-blade.md`.

================================================================================================
1. UNE CLE, **DEUX** CLASSES NATIVES
================================================================================================

`...TheArdentBlade_InitAbility` et `...TheArdentBlade_TriggerAbility` -- parent LU dans
`data/symbols/<build>/frida/classes.tsv` : `IdunBattle.Entities.Abilities.BaseTriggeredAbility` pour
les deux. Aucune ne declare de `.ctor`, donc **aucun `TargetingOptions`** : `get_TargetingOptions`
n'est declare que par `AActiveAbility`, et ces deux-la n'en derivent pas. La regle « masque de
ciblage dans le meme commit » vise `ABILITY_CLASSES` (les ACTIVES) et ne s'applique pas ici.

## 1a. `...TheArdentBlade_InitAbility$$CreateBehaviour` -- le JETON

    AddEffect( effectType = 0x5b6 = 1462 EffectType.TheArdentBlade,
               abilityState = BaseTriggeredAbility$$get_AbilityStateReference(this),
               source = Owner@<DSLSelectors+0x30>, targets = Owner@<+0x30>,
               options = &<32 octets a ZERO> )
    op_BitwiseAnd
    ActivateEffect( Owner@<+0x30>, 0x5b6 )

La classe ne surcharge PAS `CreateTrigger` : elle prend le patron
`OnOwnerSpecificAbilityInit(<AbilityType>)` de la famille des owner-effects poses a l'init. Le port
le modelise par `entities/effects/factory.ABILITY_INIT_OWNER_EFFECTS["TheArdentBlade"]`, que
`runner/operations/spawn.py::_seed_ability_owner_effects` lit -- **y compris par la voie TERTIAIRE**
(`ctx.tertiary_ability`, acquise depuis #1005), ce qui est la seule voie d'une relique EQUIPEE.
L'instance materialisee est PERMANENTE et ACTIVE, ce qui est exactement l'etat que le couple natif
`AddEffect` + `ActivateEffect` produit.

⚠ `1462` n'a **AUCUNE classe d'effet native** (inventaire exhaustif des symboles `ArdentBlade` :
11 entrees, aucune sous `Entities.Effects.*`). C'est un JETON pur -- il ne modifie aucune stat, il
n'existe que pour etre relu par le `HasEffect(onlyActive: true)` du trigger ci-dessous et eteint par
le `DeactivateEffect` du behaviour. Rien a inscrire dans `EFFECT_CLASSES`.

## 1b. `...TheArdentBlade_TriggerAbility$$CreateTrigger` (verbatim)

    ( ( ( On(0x36 = UnitDefeated, ownerNeedsToBeAlive: 1)
          & get_OwnerIsActor )
        & IsNormalUnit( Target@<DSLSelectors+0x60> ) )
      & AreEnemies( Owner@<+0x30>, Target@<+0x60>, selectionType = 1 ) )
    & HasEffect( Owner@<+0x30>, 0x5b6, onlyActive = 1, targetType = 6 )

SIX conjonctions effectives : `On(type, ownerNeedsToBeAlive: true)` rend
`<EventTrigger(0x36)> & <trigger « owner vivant »@DSLTriggers+0x20>`, un conjoint IMPLICITE.

TROIS arguments nus, QUALIFIES par le TYPE DECLARE lu dans `data/symbols/<build>/frida/methods.tsv`
(jamais par l'ordinal) :
  * `AreEnemies(unit1, unit2, selectionType : IdunBattle.Entities.Enum.**UnitTeamSelectionType**)`
    -> `1 = ByOriginalTeam`. Non cosmetique : une unite CONVERTIE est jugee sur son equipe d'ORIGINE ;
  * `HasEffect(entity, effectType, onlyActive : Boolean, targetType : **EffectTargetType**)`
    -> `6 = Both` (champ de BITS `2 = Owner | 4 = Target`), surtout PAS un nombre de tours ;
  * `UnitsWithId(entities, unitId, selectionType : **UnitSelectionType**)` (ci-dessous) -> `0 = Any`.

## 1c. `...TheArdentBlade_TriggerAbility$$CreateBehaviour` (verbatim)

    unitId     = GetStringConstant(config, 0 = unitId)              # "adeptSmnGeminaeSuperia"
    geminae    = UnitsWithId( Children(Owner@+0x30), unitId, 0 = Any )
    deadFirst  = First( DeadUnits(geminae), 1, ignoreForcedTargets = 0 )
    tile       = First( SortTilesByUtilityForSummon( CanAddUnit(AdjacentTiles(Owner@+0x30)),
                                                     utilityType = 7, parent = Owner@+0x30 ), 1, 0 )
    hp         = GetVariableForLevel(config, 0x1d = hp, abilityState, null)
    cond       = AmountIsGreaterThanZero(deadFirst) & AmountIsGreaterThanZero(tile)

    resurrect  = Resurrect( targets = deadFirst, targetTiles = tile, hp = Get(hp),
                            healType = 2, abilityType = <Nullable>, options = <octet bas a 0> )
    grp1       = Group( resurrect, groupEntity = Owner@+0x30, groupType = 0x28 )

    rangeF     = Get( GetNumberConstant(config, 0x16 = range) )
    chosen     = PickRandomly( Filter( geminae,
                                       IsAlive(ActiveTarget@+0x68)
                                         & IsInRange(Owner@+0x30, ActiveTarget@+0x68, rangeF) ),
                               1, allowDuplicates = 0, maxDuplicatesAllowed = 0x7fffffff,
                               ignoreForcedTargets = false )
    utilities  = new WeightedUtility[2] { (0x06 = 6  UnitMovement,          weight = null),
                                          (0x42 = 66 TheArdentBlade_Geminae, weight = null) }
    def        = new UtilityDefinition( new UtilityBucket(utilities, minUtilityDifference = null) )
    aiAttack   = PerformAIAttack( unit = chosen, allowOnlyMove = 1, overrideMovement = null,
                                  utilityEntity = null, customUtility = def )
    grp2       = Group( aiAttack, groupEntity = chosen, groupType = 0x20 )

    return If( cond, grp1, grp2 ) op_BitwiseAnd DeactivateEffect( Owner@+0x30, 0x5b6 )

TROIS lectures qui ne se devinent pas :

 1. **`healType = 2 = HealType.Any`** (`IdunBattle.Entities.Enum.HealType` : 0 NonMechanical,
    1 Mechanical, 2 Any). Le noeud Python `Resurrect` a `heal_type = 0` **par DEFAUT** : laisser le
    defaut REFUSERAIT de ressusciter une Geminae classee mecanique -- le port le passe explicitement.
 2. **Le `groupEntity` du 2e `Group` est `chosen`, pas `Owner`** (le 1er, lui, porte bien `Owner`).
    Et c'est le MEME objet de noeud que le `PerformAIAttack` : `GroupBehaviour$$Execute` EVALUE son
    selecteur de groupe AVANT le child, donc le `PickRandomly` est tire DEUX FOIS (#504). Le port
    passe le meme objet et reproduit les deux tirages -- un `Cache` ajoute ici serait une divergence
    de flux PRNG silencieuse.
 3. **`DeactivateEffect` DESACTIVE, il ne RETIRE PAS** (`RemoveEffect` est un slot DISTINCT du
    processeur, jamais emprunte). L'entite-effet SURVIT, seul son flag `IsActive` tombe -- c'est ce
    qui fait du couple `AddEffect`+`ActivateEffect` ... `HasEffect(onlyActive)` ... `DeactivateEffect`
    un **JETON A UN COUP par pose**. Un port qui SUPPRIMERAIT l'instance romprait le cycle en silence.
    Le `& deact` est HORS du `If` : le jeton est consomme dans les DEUX branches.

=> Lisible : la PREMIERE fois qu'`adeptCelestine` abat une unite normale ennemie, soit elle
ressuscite une Geminae morte sur la meilleure tuile libre adjacente, soit -- s'il n'y a pas de morte
ou pas de place -- une Geminae vivante a portee `range` prend un tour d'IA immediat. Puis le jeton
s'eteint : la relique ne se redeclenche plus de la bataille.

================================================================================================
2. CE QUI N'EST PAS PORTE, ET POURQUOI
================================================================================================

  * **`customUtility` du `PerformAIAttack`** -- la `UtilityDefinition` a deux poids
    (`UnitMovement` + `TheArdentBlade_Geminae`). La feuille portee n'expose pas ce parametre et le
    corps unique (`abilities/loki/summon.py::perform_ai_ability_unit_behaviour`) choisit sa cible par
    le moteur d'utilite par DEFAUT. L'utilite 66 vaut `+GetUtilityValue("LikesAdjacentCelestine")`
    (= **30** dans le `BC.Utilities` de la seed) quand la tuile visee est adjacente au PARENT de la
    Geminae (`IdunBattle.AI.Utilities.TheArdentBlade_GeminaeUtility$$EvaluateAttackInSteps`). Face
    DECISION, distincte -> residu **#1013-r3**.
  * `abilityType` (5e argument de `Resurrect`, un `Nullable<AbilityType>`) : aucun observable d'etat
    porte (attribution) -- residu PARTAGE, deja nomme par la feuille.
  * `SortTilesByUtilityForSummon` est mirrore par `SortTilesByUtility(unit_sel = None,
    parent_sel = Owner)` : mirror VALEUR-EQUIVALENT (le natif appelle un selecteur qui rend `null`,
    le port court-circuite l'appel). HYPOTHESE nommee dans `case-1013r2` sec.3.

================================================================================================
3. LES TROIS CONSTANTES, DESORMAIS **LUES** (la fiche les disait non lisibles hors ligne)
================================================================================================

`case-1013r2` sec.5 annoncait « la valeur des trois constantes n'est PAS verifiable hors ligne : la
config d'ability des reliques n'est pas dans `data/seed-bc.json` ». C'est vrai du seed BC, et FAUX du
GAMECONFIG, qui les porte : `constants = {unitId: "adeptSmnGeminaeSuperia", range: "3"}`,
`variables.hp = [2350 .. 3492]` (10 paliers), `variablesAffectedByRarityBonus = null` (donc le
multiplicateur de rarete ne s'applique a AUCUNE des deux). Le `'adeptSmnGeminaeSuperia'` de l'enonce
etait juste -- il est maintenant MESURE, plus « plausible ». Aucune valeur n'est ecrite en dur ici :
le port lit le gameconfig au runtime, comme le natif lit sa `AbilityConfiguration`.
"""
from __future__ import annotations

from typing import Optional

from .....dsl.base import Const
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.ability_constant_type import AbilityConstantType
from .....entities.ability_variable_type import AbilityVariableType
from .....entities.behaviours import Group, If, Seq
from .....entities.effect_target_type import EffectTargetType
from .....entities.effect_type import EffectType
from .....entities.effects.magnitude import ability_var
from .....entities.formulas import Count
from .....entities.heal_type import HealType
from .....entities.selectors.accessors import ActiveTarget, Target
from .....entities.selectors.geometry import PickRandomly, UnitsWithId
from .....entities.selectors.tiles import (AdjacentTiles, CanAddUnit, Caster, ChildrenOf,
                                           SortTilesByUtility)
from .....entities.selectors.units import DeadUnits, Filter, First
from .....entities.triggered_ability_type import TriggeredAbilityType
from .....entities.triggers import (AmountIsGreaterThanZero, AreEnemies, HasEffect, IsAlive,
                                    IsInRange, IsNormalUnit, OwnerIsActor, TriggerAnd)
from .....entities.unit_selection_type import UnitSelectionType
from .....entities.unit_team_selection_type import UnitTeamSelectionType
from .....streams.group_type import GroupType
from .....utilities.utility_type import UtilityType
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.effects import DeactivateEffect
from ....abilities.behaviours.lifecycle import Resurrect
from ....abilities.behaviours.summon import PerformAIAttack
from ....state import State
from ..base import TriggeredAbility, TriggerEvent, triggered_ability_state

ABILITY_ID = "TheArdentBlade"
THE_ARDENT_BLADE = int(TriggeredAbilityType.TheArdentBlade)          # 0x5bc = 1468
#: `AddEffect(0x5b6, ...)` / `HasEffect(.., 0x5b6, ..)` / `DeactivateEffect(.., 0x5b6)` --
#: `EffectType`, PAS `TriggeredAbilityType` (ou 1462 nommerait autre chose). Le JETON de la relique.
THE_ARDENT_BLADE_EFFECT = int(EffectType.TheArdentBlade)             # 0x5b6 = 1462
#: `GetStringConstant(config, 0)` -> `adeptSmnGeminaeSuperia` (LU au gameconfig, cf. sec.3).
SUMMON_UNIT_ID_CONSTANT = AbilityConstantType.unitId                 # 0
#: `GetNumberConstant(config, 0x16)` -- `range`, PAS `blockDmg_2` (le MEME ordinal 22 dans
#: `AbilityVariableType`) : la confusion serait SILENCIEUSE en ordinal.
RANGE_CONSTANT = AbilityConstantType.range                           # 0x16 = 22
#: `GetVariableForLevel(config, 0x1d, abilityState, null)` -- `AbilityVariableType`, indexe par le
#: niveau TERTIAIRE (celui de la relique), pas par celui des passifs.
HP_VARIABLE = AbilityVariableType.hp                                 # 0x1d = 29
#: `UnitsWithId(Children(Owner), unitId, 0)` : `Any` -> les Geminae MORTES sont dans le pool (c'est
#: exactement ce que `DeadUnits` va y chercher). Ecrire `OnlyAlive` ici viderait la branche resurrection.
GEMINAE_SELECTION = UnitSelectionType.Any                            # = 0
#: `AreEnemies(Owner, Target, 1)` -- `UnitTeamSelectionType`, pas `UnitSelectionType`.
ENEMY_TEAM_SELECTION = UnitTeamSelectionType.ByOriginalTeam          # = 1
#: `HasEffect(.., onlyActive: 1, targetType: 6)` -- `EffectTargetType.Both` = `Owner | Target`.
HAS_EFFECT_TARGET_TYPE = EffectTargetType.Both                       # = 6
#: `SortTilesByUtilityForSummon(tiles, 7, parent)` -- `IdunBattle.Configuration.UtilityType.Tile`.
SPAWN_TILE_UTILITY = UtilityType.Tile                                # = 7
#: `Resurrect(.., healType = 2, ..)` -- `HealType.Any`, cf. la lecture 1 de l'en-tete.
RESURRECT_HEAL_TYPE = HealType.Any                                   # = 2
#: `options` de `Resurrect` : struct `ResurrectUnitOptions` dont l'octet bas (`takesImmediateTurn`)
#: est mis a ZERO au site d'appel -> la Geminae ressuscitee n'agit PAS immediatement.
RESURRECT_IMMEDIATE_TURN = False
#: Les DEUX `Group` du behaviour -- `IdunBattle.Streams.GroupType`.
GROUP_RESURRECT = GroupType.Ability_Other                            # 0x28 = 40
GROUP_AI_ATTACK = GroupType.Ability_Attack                           # 0x20 = 32
#: `PickRandomly(sel, 1, 0, 0x7fffffff, false)` -- le `maxDuplicatesAllowed` du site.
PICK_MAX_DUPLICATES = 0x7FFFFFFF
#: `PerformAIAttack(unit, allowOnlyMove = 1, overrideMovement = null, ...)` -- la surcharge
#: `DSLBehaviors$$PerformAIAttack` (et NON `...FromCurrentPosition`, dont les deux champs valent
#: `0` / `Direct(0)`) : la Geminae a le droit de S'APPROCHER avant de frapper.
AI_ALLOW_MOVE_ACTION = True
AI_MOVE_AMOUNT = None

_ON_UNIT_DEFEATED = int(EventTriggerType.UnitDefeated)               # 0x36 = 54


def _summon_unit_id():
    """`IdunBattle.Configuration.AbilityConfiguration$$GetStringConstant(config, 0 = unitId)` =
    `gameconfig.abilities.TheArdentBlade.constants.unitId` = `adeptSmnGeminaeSuperia`.

    MEME lecture que `geminae_superia._summon_unit_id` -- et c'est le MEME summon : la relique
    ressuscite (ou fait agir) les Geminae que le passif de kit `GeminaeSuperia` a posees.
    `None` = cle absente -> le selecteur ne matche rien, les deux branches sont des no-op."""
    import gameconfig as GC
    return ((GC.ability(ABILITY_ID) or {}).get("constants") or {}).get(SUMMON_UNIT_ID_CONSTANT.name)


def ardent_blade_geminae():
    """`UnitsWithId( Children(Owner@+0x30), GetStringConstant(0), UnitSelectionType.Any = 0 )`.

    `Children(parent)` est `IdunBattleLogic.Entities.DSLSelectors$$Children` (AVEC argument), donc
    `ChildrenOf` -- **pas** l'accumulateur `Children()` du cast courant (#590 : les confondre rend un
    selecteur toujours vide, sans erreur). `Any` : le pool contient les Geminae MORTES, ce que la
    branche resurrection exige.

    Une SEULE instance est partagee par les deux branches dans `ardent_blade_behaviour_tree`, comme
    le natif reprend le meme `pvVar2` : l'arbre est donc evalue deux fois, exactement comme lui."""
    return UnitsWithId(ChildrenOf(Caster()), _summon_unit_id(), int(GEMINAE_SELECTION))


def ardent_blade_dead_geminae(geminae):
    """`First( DeadUnits(geminae), amount = 1, ignoreForcedTargets = 0 )` -- la Geminae a ressusciter.

    `First(sel)` (index 0) mirrore `First(sel, 1, 0)` : la surcharge native prend les `amount`
    PREMIERS elements de la liste dans SON ordre, et pour `amount == 1` c'est l'element 0."""
    return First(DeadUnits(geminae))


def ardent_blade_spawn_tile():
    """`First( SortTilesByUtilityForSummon( CanAddUnit(AdjacentTiles(Owner@+0x30)), 7, Owner@+0x30 ),
    1, 0 )` -- la tuile d'atterrissage de la ressuscitee.

    ⚠ **AUCUN `PendingMovingTile` ici**, contrairement au `GetPossibleSpawnTiles` de
    `GeminaeSuperiaAbility` : les deux arbres se ressemblent et ne sont pas les memes."""
    return First(SortTilesByUtility(CanAddUnit(AdjacentTiles(Caster())),
                                    unit_sel=None, utility_type=int(SPAWN_TILE_UTILITY),
                                    parent_sel=Caster()))


def ardent_blade_reachable_geminae(geminae, rng_value: int):
    """`PickRandomly( Filter( geminae, IsAlive(It@+0x68) & IsInRange(Owner@+0x30, It@+0x68,
    Get(range)) ), 1, 0, 0x7fffffff, false )`.

    `It@<DSLSelectors+0x68>` = `ActiveTarget`, le slot que `FromTriggerSelector$$Select` ecrase a
    chaque element -- c'est le sujet du `Filter`. Le port lie les DEUX noms du meme slot
    (`subject` ET `active_target`), donc `ActiveTarget()` resout bien l'element courant.

    ⚠ Le `Filter` porte sur l'ensemble **COMPLET** des Geminae (`UnitsWithId`, morts compris), pas
    sur le sous-ensemble mort -- c'est l'`IsAlive` du predicat qui trie, et lui seul.

    `rng_value` = `Get(GetNumberConstant(config, 0x16 = range))`, resolu par l'appelant (le natif le
    resout lui aussi AVANT de batir l'arbre : `GetNumberConstant` puis `DSLFormulas$$Get`)."""
    return PickRandomly(Filter(geminae,
                               TriggerAnd(IsAlive(ActiveTarget()),
                                          IsInRange(Caster(), ActiveTarget(),
                                                    Const(int(rng_value))))),
                        1, False, PICK_MAX_DUPLICATES, False)


def ardent_blade_behaviour_tree(hp_amount: int, range_value: int):
    """`...TheArdentBlade_TriggerAbility$$CreateBehaviour` -- MIRROR 1:1 (cf. sec.1c de l'en-tete) :

        If( AmountIsGreaterThanZero(deadFirst) & AmountIsGreaterThanZero(tile),
            Group(Resurrect(...), Owner, 0x28),
            Group(PerformAIAttack(chosen, 1, null, null, def), chosen, 0x20) )
        op_BitwiseAnd
        DeactivateEffect( Owner@+0x30, 0x5b6 )

    ⚠ `chosen` est le MEME objet de noeud pour le `PerformAIAttack` et pour le `groupEntity` du
    `Group` : `GroupBehaviour$$Execute` evalue son selecteur AVANT le child, donc le `PickRandomly`
    consomme DEUX tirages et peut designer deux Geminae DIFFERENTES (celle du groupe de presentation
    et celle qui frappe). C'est le quirk natif mesure par #504 -- le mirrorer, pas le « corriger ».

    ⚠ Le `DeactivateEffect` est HORS du `If` (`op_BitwiseAnd` a la racine) : le jeton tombe meme
    quand la branche prise n'a rien fait (aucune Geminae vivante a portee, par exemple)."""
    geminae = ardent_blade_geminae()          # le MEME sous-arbre pour les deux branches (natif)
    dead_first = ardent_blade_dead_geminae(geminae)
    tile = ardent_blade_spawn_tile()
    cond = TriggerAnd(AmountIsGreaterThanZero(Count(dead_first)),
                      AmountIsGreaterThanZero(Count(tile)))
    resurrect = Group(Resurrect(dead_first, tile, int(hp_amount),
                                heal_type=int(RESURRECT_HEAL_TYPE),
                                immediate_turn=RESURRECT_IMMEDIATE_TURN),
                      int(GROUP_RESURRECT), Caster())
    chosen = ardent_blade_reachable_geminae(geminae, range_value)
    ai_attack = Group(PerformAIAttack(chosen, AI_ALLOW_MOVE_ACTION, AI_MOVE_AMOUNT),
                      int(GROUP_AI_ATTACK), chosen)
    return Seq(If(cond, resurrect, ai_attack),
               DeactivateEffect(Caster(), THE_ARDENT_BLADE_EFFECT))


class TheArdentBladeTriggerAbility(TriggeredAbility):
    """`...TheArdentBlade_TriggerAbility` (2e des DEUX classes de la cle 0x5bc ; la 1re, l'`InitAbility`,
    vit dans `ABILITY_INIT_OWNER_EFFECTS`).

    `On(0x36 = UnitDefeated, alive) & get_OwnerIsActor & IsNormalUnit(Target) &
     AreEnemies(Owner, Target, ByOriginalTeam) & HasEffect(Owner, 1462, onlyActive: true, Both)`
    -> `If(<une Geminae morte ET une tuile libre>, Resurrect(...), PerformAIAttack(<une Geminae
       vivante a portee>)) & DeactivateEffect(Owner, 1462)`.

    Lisible : la PREMIERE unite normale ennemie qu'`adeptCelestine` abat lui rend une Geminae -- ou,
    a defaut, offre un tour a une Geminae vivante. Une seule fois par pose du jeton."""
    event_id = _ON_UNIT_DEFEATED
    TRIGGERED_ABILITY_ID = THE_ARDENT_BLADE

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        """Le `CreateTrigger` moins le volet `On(0x36)` + « owner vivant », deja porte par le
        dispatch. Les QUATRE conjoints restants sont des noeuds DSL (doctrine #149), dans l'ordre
        d'imbrication du decompile."""
        entities = entities_from_state(state, self.owner_id, ev.target_id, actor_id=ev.actor_id)
        # `Target@<DSLSelectors+0x60>` : une NOUVELLE instance par site, comme le natif relit le
        # meme champ a chaque conjoint.
        tree = TriggerAnd(
            TriggerAnd(
                TriggerAnd(OwnerIsActor(), IsNormalUnit(Target())),
                AreEnemies(Caster(), Target(), int(ENEMY_TEAM_SELECTION))),
            HasEffect(Caster(), THE_ARDENT_BLADE_EFFECT, active_only=True))
        return bool(tree.evaluate(entities))

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        # `GetVariableForLevel(config, 0x1d = hp, abilityState, null)` et `GetNumberConstant(config,
        # 0x16 = range)`. Le couple `(niveau, multiplicateur)` est celui de l'`AbilityState`
        # **TERTIAIRE** : lire celui des passifs clamperait `hp` au dernier palier (3492) dans tout
        # runner normalise, SILENCIEUSEMENT.
        lvl, mult = triggered_ability_state(state, int(self.owner_id), ABILITY_ID)
        hp = int(ability_var(ABILITY_ID, HP_VARIABLE.name, lvl, multiplier_pct=mult) or 0)
        rng_v = int(ability_var(ABILITY_ID, RANGE_CONSTANT.name, is_constant=True) or 0)
        entities = entities_from_state(state, self.owner_id, ev.target_id, actor_id=ev.actor_id)
        ectx = ExecutionContext(state=state, rng=state.rng)
        ardent_blade_behaviour_tree(hp, rng_v).execute(entities, ectx)
        res = next((p for (n, p) in ectx.emitted if n == "Resurrect"), None)
        att = next((p for (n, p) in ectx.emitted if n == "PerformAIAttack"), None)
        deact = next((p for (n, p) in ectx.emitted if n == "DeactivateEffect"), None)
        return {"passive": ABILITY_ID, "owner": int(self.owner_id),
                "victim": (int(ev.target_id) if ev.target_id is not None else None),
                "hp": hp, "range": rng_v, "ability_state": (lvl, mult),
                "resurrections": (res.get("resurrections") if res else None),
                "attacks": (att.get("attacks") if att else None),
                "token_deactivated": (deact.get("deactivated") if deact else None),
                "dsl": True}
