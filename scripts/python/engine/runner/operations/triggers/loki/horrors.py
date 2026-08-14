"""Cluster HORREURS Thousand Sons — la CHAINE `Split` (1156) -> `FlamesOfMutation` (1160).

Regroupees ICI (1 module pour 2 abilities natives, comme `death_nova.py` et `fire.py`) parce que le
natif les enchaine ET les FACTORISE : une Pink Horror qui meurt se scinde en DEUX Blue Horrors, dont
chacune enflamme sa propre tuile en mourant -- et surtout, leurs DEUX `CreateTrigger` sont **UN SEUL
ET MEME CORPS** (fold ICF, cf. plus bas). Porteurs (`docs/rl/summons-registry.tsv`) :
  * `Split`            -- `thousSmnPinkHorror` (S+), `thousSmnPinkHorrorHSE` (S?)
  * `FlamesOfMutation` -- `thousSmnBlueHorror` (S+), `thousSmnBlueHorrorHSE` (S?)
Tous SUMMONS : ils arrivent en bataille par leur summoner, et ils s'OBSERVENT (#291) -- un summon
n'entre jamais dans `decisionView.toActivate`.

--------------------------------------------------------------------------------------------------
ARTEFACTS NATIFS (build `rnca9r7q6c` ; decompile = verite)
--------------------------------------------------------------------------------------------------
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.SplitAbility$$CreateTrigger`
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.SplitAbility$$CreateBehaviour`
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.SplitAbility$$CreateSpawnBehavior`
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.FlamesOfMutationAbility$$CreateBehaviour`
`IdunBattleLogic.Entities.DSLTriggers$$OnPreDeath2` -> `IdunBattleLogic.Entities.DSLTriggers$$OnDeathEvent(2, a, b)`
`IdunBattleLogic.Entities.DSLTriggers$$IsTurnOf` · `IdunBattleLogic.Entities.DSLTriggers$$InitializeShared`
`IdunBattleLogic.Entities.DSLBehaviors$$If` · `$$Spawn` · `$$AddEffect` · `$$PerformAIAttackFromCurrentPosition`
`IdunBattleLogic.Entities.DSLSelectors$$AdjacentTiles` · `$$CanAddUnit` · `$$PickRandomly` · `$$Tiles`
`IdunBattle.Entities.Behaviours.SpawnUnitOptions$$WithStatsFromConfig`
`IdunBattle.Configuration.AbilityConfiguration$$GetStringConstant`

TRIGGER -- **UN SEUL CORPS POUR LES DEUX ABILITIES**, et c'est une DEDUPLICATION ICF, pas une
approximation. `IdunBattleLogic.Entities.Abilities.Triggered.Loki.FlamesOfMutationAbility.CreateTrigger`
est ABSENT de `data/symbols/rnca9r7q6c/frida/methods.tsv` alors que son `CreateBehaviour` y est
(RVA `10359a0`, voisine du `SplitAbility.CreateTrigger` retenu comme proprietaire, `1035a30`) ; et le
`dump.cs` Il2CppDumper leur donne litteralement la MEME RVA (`0xFAF310` sur le build de mai,
`0xFC2220` sur l'autre coupe). C'est le cas d'ecole du garde-fou « l'ABSENCE d'une methode dans les
tables ne prouve RIEN » (CLAUDE.md) : ici l'absence prouve le PARTAGE, pas l'inexistence.

    CreateTrigger() = OnPreDeath2(triggerOnOverkill: false, triggerOnSteppable: false)
                      & get_OwnerIsTarget

et `OnDeathEvent(eventId, a, b)`, relu VERBATIM sur `rnca9r7q6c` (les DEUX gates sont ARMES ici) :

    On(eventId = 2 = PreUnitDeath_2)  &  <YesTrigger @DSLTriggers+0x70>
      & (a == 0 ? NOT TargetIsOverkilled : YES)      # `HasFlagAbilityTrigger(Target@DSLSelectors+0x60,
                                                    #  UnitFlag.Overkilled = 8)` puis `op_LogicalNot`
      & (b == 0 ? NOT HasTrait(Target@+0x60, 0x1b = UnitTrait.Steppable) : YES)

-> `a = 0` EST le « Does not apply if Overkilled » des DEUX textes i2. Contraste avec la famille
DEATH-NOVA (`death_nova.py`), qui passe `a = 1` et part MEME en overkill : recopier son
`_DeathNovaAbility` tel quel aurait ete FAUX sur ce gate-la.

BEHAVIOUR `SplitAbility$$CreateBehaviour(abilityState, triggerType)` :

    If( <DSLTriggers+0x28>,                              # = IsTurnOf(Owner@DSLSelectors+0x30)
        CreateSpawnBehavior(abilityState, autoAttack: true),
        CreateSpawnBehavior(abilityState, autoAttack: false) )

Le champ `DSLTriggers+0x28` est IDENTIFIE, pas devine : `IdunBattleLogic.Entities.DSLTriggers$$
InitializeShared` l'ecrit `new <DAT_1833ab568>(<DSLSelectors+0x30>, matchState, 0)`, et
`IdunBattleLogic.Entities.DSLTriggers$$IsTurnOf(selector)` construit EXACTEMENT la meme classe avec
la meme forme d'arguments -- c'est donc le `IsTurnOf` du slot **Owner** (`+0x30`, l'identite du slot
etant elle-meme LUE par `get_OwnerIsActor` = `AreEqual(+0x30, +0x40)`), memoise une fois pour toutes.
Et c'est mot pour mot l'i2 : « can immediately attack an enemy **if summoned during the Pink
Horror's turn** ».

BEHAVIOUR `SplitAbility$$CreateSpawnBehavior(abilityState, autoAttack)` :

    options = SpawnUnitOptions$$WithStatsFromConfig(config@this+0x20, abilityState, 0, 0)
    if (autoAttack)
        options.<+0x18> = PerformAIAttackFromCurrentPosition(ActiveTarget@<DSLSelectors+0x68>,
                                                             utilityEntity: null, customUtility: null,
                                                             skipAtomicCheck: false)
    origin = Owner@<DSLSelectors+0x30>
    tiles  = PickRandomly( CanAddUnit( AdjacentTiles(origin) ),
                           amount: 2, allowDuplicates: false,
                           maxDuplicatesAllowed: 0x7fffffff, ignoreForcedTargets: false )
    return Spawn( parentSelector: origin, tiles, GetStringConstant(config, 0 = unitId), options )

-> **2** Blue Horrors, sur des tuiles ADJACENTES au mourant ou une unite PEUT etre posee, tirees au
sort. Le `2` est un LITTERAL du decompile (le gameconfig de `Split` ne porte AUCUNE variable de
compte : seulement `summonHp`/`summonDmg` + la constante `unitId`).

BEHAVIOUR `FlamesOfMutationAbility$$CreateBehaviour(abilityState, triggerType)` :

    AddEffect( effectType : 5 = EffectType.Fire,
               abilityState: BaseTriggeredAbility$$get_AbilityStateReference(this),
               source      : <ABSENT -- le ctor recoit 0 en param_4>,
               targets     : Tiles(Owner@<DSLSelectors+0x30>),
               turns       : null )

`DSLSelectors$$Tiles(entities)` alloue un `IdunBattle.Entities.Selectors.UnitsMainTilesSelector` =
la MAIN TILE par entite -> « it sets **its hex** on Fire » (SA tuile, pas son empreinte). La
surcharge d'`AddEffect` employee est celle a QUATRE arguments (hors `this`), dont le ctor
`AddEffectBehaviour..ctor(logger, effectType, abilityState, 0, targets, options)` passe **`0` en
selecteur SOURCE** : c'est le fallback natif « source absente => la source EST la cible », deja
porte et documente sur `BrazierOfHolyFire` (`source_from_target`). `turns = null` -> duree DEFAUT de
l'effet, pas un compte explicite.

--------------------------------------------------------------------------------------------------
CONSTANTES -- LUES EN CONFIG, ZERO HARDCODE
--------------------------------------------------------------------------------------------------
`abilities.Split.constants.unitId` = `thousSmnBlueHorror` ; `abilities.Split.variables.summonHp` /
`summonDmg` (64 paliers, tous deux dans `variablesAffectedByRarityBonus`) -> palier 64 = 1528 / 1310,
soit EXACTEMENT le « Blue Horror's stats: 1528 Health 1310 Damage » de l'i2. Ces sept stats de summon
sont lues par `build_summon_context` sous l'`AbilityState` PASSIF du porteur (2e argument de
`WithStatsFromConfig`), pas sous son canal d'active -- d'ou le `ability_state=` de la feuille.

⚠ `abilities.FlamesOfMutation.constants.chance = "50"` est une constante **NON LUE**, et c'est un
resultat, pas un renoncement. La classe native n'a que QUATRE membres (`dump.cs` :
`get_AllowForDeadOwner` slot 21, `CreateTrigger` slot 24, `CreateBehaviour` slot 26, `.ctor`) ; les
quatre corps ont ete lus : `CreateBehaviour` ci-dessus (aucun `GetNumberConstant`), `CreateTrigger`
= le corps PARTAGE avec Split (qui, lui, n'a pas de `chance` en config -- un gate de chance y serait
absurde), et les deux autres sont triviaux/partages. En amont, `IdunBattle.Entities.Abilities.
BaseTriggeredAbility$$ShouldTrigger` delegue au trigger de `this+0x58` et `$$Execute` execute le
behaviour : **aucun gate de chance generique** n'existe a cet etage. Le texte i2 ne mentionne pas de
chance non plus (« When this unit gets defeated it sets its hex on Fire »). Porter un `Maybe(50)`
ici serait un gate INVENTE -- l'anti-pattern §2.1. RESIDU ouvert pour ce qui reste non elimine :
la constante pourrait etre lue par un consommateur VIEW (`IdunBattle.View.AbilityConfigs.Loki.
FlamesOfMutationVisuals$$ExecuteInternal`), ce qui serait sans effet sur l'etat.
"""
from __future__ import annotations

from typing import Optional

from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.behaviours import If
from .....entities.effect_type import EffectType
from .....entities.selectors.accessors import ActiveTarget, Owner
from .....entities.selectors.tiles import AdjacentTiles, CanAddUnit
from .....entities.selectors.units import Tiles
from .....entities.traits.unit_trait import UnitTrait
from .....entities.triggered_ability_type import TriggeredAbilityType
from .....entities.triggers import IsTurnOf
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.effects import AddEffect
from ....abilities.behaviours.summon import PerformAIAttack, Spawn
from ....state import State
from ..base import TriggeredAbility, TriggerEvent, _unit_trait_names, triggered_ability_state

# --- Identites d'ability (`TriggeredAbilityType` -- PAS `ActiveAbilityType`/`EffectType`) ----------
SPLIT_ABILITY = int(TriggeredAbilityType.Split)                      # 0x484 = 1156
FLAMES_OF_MUTATION_ABILITY = int(TriggeredAbilityType.FlamesOfMutation)   # 0x488 = 1160

#: Cles GAMECONFIG des deux abilities (= le nom du passif dans `units.<id>.passiveAbilities`, qui est
#: aussi la cle du registre `ABILITY_TRIGGERS`). Le nom PLEIN discrimine, l'ordinal non (CLAUDE.md).
SPLIT_KEY = TriggeredAbilityType.Split.name                          # "Split"
FLAMES_OF_MUTATION_KEY = TriggeredAbilityType.FlamesOfMutation.name  # "FlamesOfMutation"

#: `AddEffect(5, ...)` de `FlamesOfMutationAbility$$CreateBehaviour` -- l'effet de TUILE « en feu ».
FLAMES_OF_MUTATION_FIRE = int(EffectType.Fire)                       # 5

#: `PickRandomly(..., amount: 2, ...)` de `SplitAbility$$CreateSpawnBehavior` -- LITTERAL du
#: decompile (aucune variable de compte en gameconfig), d'ou la constante nommee plutot qu'un `2`
#: pose au milieu de l'arbre.
SPLIT_SPAWN_COUNT = 2

#: `GetStringConstant(config, 0)` -- `AbilityConstantType 0 = unitId` (le defaut de la feuille
#: `Spawn`, ecrit ici pour que le site DISE quelle constante le natif lit).
SPLIT_UNIT_ID_CONSTANT = "unitId"


# --- Arbres DSL (mirror 1:1 des `CreateBehaviour`) ------------------------------------------------
def split_spawn_behavior(ability_state, auto_attack: bool):
    """`IdunBattleLogic.Entities.Abilities.Triggered.Loki.SplitAbility$$CreateSpawnBehavior(
    abilityState, autoAttack)` -- MIRROR 1:1 du decompile (cf. l'en-tete de module pour le pseudo-C).

    `pick_n` est le FOLD du `PickRandomly(tiles, 2)` que le natif ENVELOPPE autour du tile-selecteur
    du `Spawn` : la feuille le resout par le foyer unique `_pick_randomly_n`, seul endroit qui voit
    `state.rng` -- meme convention que `SupremeCommanderAbility`, dont le natif a la MEME forme
    (`Spawn(PickRandomly(CanAddUnit(AdjacentTiles(...)), n), unitId, WithStatsFromConfig)`).

    `on_appearance` = le sous-behaviour `SpawnUnitOptions+0x18`, fire PAR SUMMON par
    `IdunBattle.Entities.Behaviours.SpawnUnitBehaviour$$TriggerSpawnedUnitBehaviours` juste apres la
    pose, et dont l'acteur est `ActiveTarget@<DSLSelectors+0x68>` = le summon fraichement pose. Les
    defauts de `PerformAIAttack` (`allow_move_action=False`, `move_amount=0`) SONT ceux du noeud
    `...FromCurrentPosition` -- c'est le « can immediately attack an enemy [...] **but cannot move
    until their next turn** » de l'i2, et le « cannot move » est deja porte par `#291`
    (`TriggerSpawnedUnitBehaviours` -> `FinishUnitTurn(spawned, isTerminated: true)`, que la feuille
    `Spawn` appelle APRES l'on-appearance).

    Les DEUX branches du `If` allouent chacune leur PROPRE chaine de selecteurs (le natif appelle
    `CreateSpawnBehavior` deux fois, et chaque appel re-alloue `AdjacentTiles`/`CanAddUnit`/
    `PickRandomly`) : on ne PARTAGE donc PAS l'instance entre les branches, contrairement a
    `putrid_explosion_tree` ou le natif reutilise le meme pointeur."""
    tiles = CanAddUnit(AdjacentTiles(Owner()))          # CanAddUnit(AdjacentTiles(Owner@+0x30))
    return Spawn(tiles, SPLIT_KEY,
                 pick_n=SPLIT_SPAWN_COUNT,              # fold `PickRandomly(..., 2, ...)`
                 on_appearance=(PerformAIAttack(ActiveTarget()) if auto_attack else None),
                 unit_id_constant=SPLIT_UNIT_ID_CONSTANT,
                 # 2e argument de `SpawnUnitOptions$$WithStatsFromConfig` : le summon monte SES
                 # abilities (dont `FlamesOfMutation`) sous l'`AbilityState` du PASSIF du summoner.
                 ability_state=ability_state)


def split_tree(ability_state):
    """`IdunBattleLogic.Entities.Abilities.Triggered.Loki.SplitAbility$$CreateBehaviour` -- MIRROR
    1:1 :

        If( IsTurnOf(Owner@<DSLSelectors+0x30>)   [ = le champ memoise <DSLTriggers+0x28> ],
            CreateSpawnBehavior(abilityState, autoAttack: true),
            CreateSpawnBehavior(abilityState, autoAttack: false) )

    La branche `else` EST posee par le natif (4e argument non nul) : les deux branches spawnent, seul
    l'on-appearance differe."""
    return If(IsTurnOf(Owner()),
              split_spawn_behavior(ability_state, auto_attack=True),
              split_spawn_behavior(ability_state, auto_attack=False))


def flames_of_mutation_tree():
    """`IdunBattleLogic.Entities.Abilities.Triggered.Loki.FlamesOfMutationAbility$$CreateBehaviour`
    -- MIRROR 1:1 :

        AddEffect( 5 = EffectType.Fire, AbilityStateReference, <source 0>,
                   Tiles(Owner@<DSLSelectors+0x30>), turns: null )

    `source_from_target=True` = le `0` que le ctor `AddEffectBehaviour..ctor` recoit en selecteur
    SOURCE (surcharge a 4 arguments) -> chaque TUILE est sa propre source, comme
    `BrazierOfHolyFireAbility`. `duration_rounds=None` = l'argument natif `turns = null` -> duree
    DEFAUT de l'effet (`DefaultAmountOfRounds`), surtout pas un compte invente."""
    return AddEffect(FLAMES_OF_MUTATION_FIRE, EffectType.Fire.name,
                     Tiles(Owner()),                    # UnitsMainTilesSelector(Owner@+0x30)
                     duration_rounds=None,              # `turns = null`
                     source_from_target=True)           # selecteur SOURCE natif = 0


# --- Ability-triggers -----------------------------------------------------------------------------
class _HorrorOnDeathAbility(TriggeredAbility):
    """Base PARTAGEE des deux Horreurs, et le partage est celui du NATIF : leurs deux
    `CreateTrigger` sont **le meme corps** (fold ICF, cf. l'en-tete de module). L'arbre :

        On(PreUnitDeath_2 = 2) & NOT TargetIsOverkilled
                               & NOT HasTrait(Target, Steppable)
                               & OwnerIsTarget

    `fire_on_death` : l'owner EST le mourant, deja `alive=False` au dispatch -> bypass du gate
    « owner vivant » de `CanGetAbilityTrigger`. Le vecteur `pre_unit_death_2_triggers` PRECEDE tout
    retrait de l'unite du plateau (LU dans `IdunBattle.Operations.KillUnitOperation$$Execute`, et
    mirrore tel quel par `damage.py`), donc l'owner a encore sa position : c'est ce qui rend
    `AdjacentTiles(Owner())` non vide."""
    event_id = EventTriggerType.PreUnitDeath_2
    fire_on_death = True

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        if ev.dying_id != self.owner_id:            # get_OwnerIsTarget (owner = le mourant @+0x60)
            return False
        # `a = 0` -> `NOT TargetIsOverkilled` = `NOT HasFlag(Target, UnitFlag.Overkilled = 8)`.
        # C'est le « Does not apply if Overkilled » de l'i2, et l'ECART avec la famille death-nova,
        # qui passe `a = 1` et n'a donc AUCUN gate ici.
        if ev.overkill:
            return False
        # `b = 0` -> `NOT HasTrait(Target, 0x1b = Steppable)`. INERTE pour les quatre porteurs
        # actuels (aucune Horreur n'est Steppable) -- mirrore quand meme, comme `PutridExplosion`.
        if UnitTrait.Steppable.name in _unit_trait_names(state, self.owner_id):
            return False
        return True


class SplitAbility(_HorrorOnDeathAbility):
    """`SplitAbility` (`TriggeredAbilityType.Split` = 1156) -- passif de `thousSmnPinkHorror` et
    `thousSmnPinkHorrorHSE`.

    Trigger = le corps partage (cf. `_HorrorOnDeathAbility`). Behaviour = `split_tree` : DEUX Blue
    Horrors sur des tuiles adjacentes libres tirees au sort, qui attaquent immediatement SI c'est le
    tour de la Pink Horror (`IsTurnOf(Owner)`)."""
    TRIGGERED_ABILITY_ID = SPLIT_ABILITY

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        # `abilityState` = le 1er parametre de `CreateBehaviour`, relaye a `WithStatsFromConfig` :
        # l'etat d'ability sous lequel le PASSIF `Split` est monte sur le porteur (hierarchie 2).
        ability_state = triggered_ability_state(state, self.owner_id, SPLIT_KEY)
        entities = entities_from_state(state, self.owner_id, self.owner_id,
                                       actor_id=ev.killer_id)   # owner = caster = target = le mourant
        ectx = ExecutionContext(state=state, rng=state.rng)
        split_tree(ability_state).execute(entities, ectx)
        spawned = [p["unit"] for n, p in ectx.emitted if n == "SpawnUnit"]
        attacks = [a for n, p in ectx.emitted if n == "PerformAIAttack" for a in (p.get("attacks") or [])]
        if not spawned:
            return None                              # aucune tuile posable adjacente -> no-op
        return {"ability": SPLIT_KEY, "owner": int(self.owner_id), "spawned": spawned,
                "attacks": attacks, "on_event": ev.event_id}


class FlamesOfMutationAbility(_HorrorOnDeathAbility):
    """`FlamesOfMutationAbility` (`TriggeredAbilityType.FlamesOfMutation` = 1160) -- passif de
    `thousSmnBlueHorror` et `thousSmnBlueHorrorHSE`.

    Trigger = le MEME corps que `Split` (fold ICF -- cf. l'en-tete de module ; c'est ce qui rend le
    gate overkill des deux Horreurs strictement identique). Behaviour = `flames_of_mutation_tree` :
    `EffectType.Fire` sur la MAIN TILE du mourant, duree par defaut de l'effet."""
    TRIGGERED_ABILITY_ID = FLAMES_OF_MUTATION_ABILITY

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        entities = entities_from_state(state, self.owner_id, self.owner_id,
                                       actor_id=ev.killer_id)
        ectx = ExecutionContext(state=state, rng=state.rng)
        flames_of_mutation_tree().execute(entities, ectx)
        placed = [{"target": p.get("target"), "placed": p.get("placed")}
                  for n, p in ectx.emitted if n == "AddEffect"]
        if not placed:
            return None                              # pas de tuile resolue -> no-op
        return {"ability": FLAMES_OF_MUTATION_KEY, "owner": int(self.owner_id),
                "effect": FLAMES_OF_MUTATION_FIRE, "tiles": placed, "on_event": ev.event_id}
