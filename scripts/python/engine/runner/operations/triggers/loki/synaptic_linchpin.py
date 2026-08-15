"""`SynapticLinchpin` (passif d'`tyranWingedPrime` << Winged Prime >>, HERO Tyranids) -- canal **T**
(`ABILITY_TRIGGERS`).

i2 (L50) : « Whenever the Winged Prime, or another friendly unit with Synapse, performs a normal
attack against an enemy and that enemy is not defeated, summons a Hormagaunt adjacent to the target,
which immediately attacks the enemy. Cannot have more than 4 Hormagaunts summoned this way at the
same time. Hormagaunt stats: 1680 Health 1232 Damage 336 Armour »

================================================================================================
RE (decompile ghidra, build `rnca9r7q6c`) -- les DEUX faces du meme artefact natif
================================================================================================
Slots de `IdunBattleLogic.Entities.DSLSelectors$$InitializeShared` sur ce build, ETABLIS par
recoupement des getters NOMMES de `DSLTriggers` (chacun construit `AreEqual(<slot>, <slot>)`, donc
chaque paire contraint ses deux membres ; le champ COMMUN a plusieurs getters est identifie) :

    get_OwnerIsActor      -> (+0x30, +0x40)      get_OwnerIsTarget     -> (+0x30, +0x60)
    get_OwnerIsCaster     -> (+0x30, +0x48)      get_OwnerIsCasterTile -> (+0x30, +0x50)
    get_CasterIsTarget    -> (+0x48, +0x60)      get_CasterIsCasterTile-> (+0x48, +0x50)
    get_OwnerIsTargetTile -> (+0x78, +0x30)      get_OwnerTileIsTarget -> (MainTileOfUnits(+0x30), +0x60)

  => `+0x30 Owner` (4 getters) · `+0x40 Actor` · `+0x48 Caster` (3 getters) · `+0x50 CasterTile` ·
     `+0x60 Target` (3 getters) · `+0x68 ActiveTarget` · `+0x78 TargetTile`.
  `+0x68` n'est couvert par aucun getter ; il est etabli par DEUX sources concordantes :
  (a) l'ordre des slots homologues du `DSLFactory` d'un autre build (`0x178 Target · 0x180
  ActiveTarget` -- le champ qui SUIT `Target`), et (b)
  `IdunBattle.Entities.Behaviours.SpawnUnitBehaviour$$TriggerSpawnedUnitBehaviours`, qui recopie
  l'`AbilityEntities` puis ECRIT `unitSpawned` dans le champ `+0x20` de la copie AVANT d'executer
  `options.<+0x18>` -- et `+0x20` est le slot `activeTarget` de
  `IdunBattle.Entities.Abilities.AbilityEntities$$.ctor` (32 arguments ; `[rcx+0x20] <- arg12`).

## `IdunBattleLogic.Entities.Abilities.Triggered.Loki.SynapticLinchpinAbility$$CreateTrigger`

    a = HasTrait(actor@+0x40, UnitTrait.Synapse = 2024)
    b = AreFriends(owner@+0x30, actor@+0x40, UnitTeamSelectionType.ByCurrentTeam = 0, anyEntity: 0)
    c = IsAlive(target@+0x60)
    d = On( EventTriggerType.NormalAttack = 38,
            ownerNeedsToBeAlive: NOT( OwnerIsActor
                                      & TriggeringAbilityIs(TriggeredAbilityType.FinalJustice = 1024) ) )
    return ((d & a) & b) & c                     # ordre des `op_BitwiseAnd` LU au desassemblage

**LE 2e ARGUMENT DE `On` N'EST PAS UNE CONDITION D'EVENEMENT** -- `IdunBattleLogic.Entities.
DSLTriggers$$On(triggerType, ownerNeedsToBeAlive: IAbilityTrigger)`, corps LU :

    left  = new EventTypeTrigger(triggerType)
    right = new Not(ownerNeedsToBeAlive)                  # meme classe que `DSLTriggers$$Not` et que
                                                          # `AbilityTrigger$$op_LogicalNot` (xrefs)
    return left & ( this.<+0x20> | right )

et la surcharge BOOLEENNE tranche l'identite de `<+0x20>` : `On(t, bool b)` rend
`EventTypeTrigger(t) & this.<b ? +0x20 : +0x70>` (`cmove` LU), or `+0x70` est le trigger
TOUJOURS-VRAI que le port nomme deja `YesTrigger`. Donc `<+0x20>` = **OwnerIsAlive**, et

    On(t, X)  ==  Event(t) & ( OwnerIsAlive | !X )

Ici `X = !(OwnerIsActor & TriggeringAbilityIs(FinalJustice))`, donc le gate effectif est

    Event(NormalAttack) & ( OwnerIsAlive | (OwnerIsActor & TriggeringAbilityIs(FinalJustice)) )

soit « le Winged Prime doit etre vivant, SAUF quand c'est LUI qui frappe via `FinalJustice` » --
et `IdunBattleLogic.Entities.Abilities.Active.Loki.FinalJusticeAbility$$CreateTrigger` est
`OnPreDeath(triggerOnOverKill: 1) & OwnerIsTarget`, c'est-a-dire l'attaque POST-MORTEM du trait
`FinalJustice` que `tyranWingedPrime` porte. Le disjunct n'est donc pas decoratif : il fait vivre le
passif pendant la mort de son porteur.

⚠ **QUALIFICATION DE L'ENUM** (piege du voisin de forme) : l'`op_Implicit` du `TriggeringAbilityIs`
perd son immediat dans le pseudo-C. Au DESASSEMBLAGE, `mov edx, 0x400` precede
`call IdunBattle.Core.AbilityOrEffect$$op_Implicit`, et la surcharge visee est celle dont
`frida/methods.tsv` declare le parametre `triggeredAbility:IdunBattle.Entities.Enum.
TriggeredAbilityType` (les trois autres homonymes posent `ActiveAbilityType` / `EffectType` /
`AbilityType`, et leurs quatre RVA sont DISTINCTES -- aucune fusion ICF ici). `1024` est un membre
VALIDE des trois espaces et y nomme trois choses differentes : `TriggeredAbilityType.FinalJustice`,
`ActiveAbilityType.Burrowers_Appear`, `EffectType.Emplacement_RangedEffect`.

## `IdunBattleLogic.Entities.Abilities.Triggered.Loki.SynapticLinchpinAbility$$CreateBehaviour`

    unitId     = GetStringConstant(cfg, AbilityConstantType.unitId = 0)          # "tyranSmnHormagaunt"
    nrSummons  = GetNumberConstant(cfg, AbilityConstantType.nrOfSummons = 16)    # 1
    maxSummons = GetVariableForLevel(cfg, AbilityVariableType.maxSummons = 49, abilityState, null)

    cap  = AmountIsEqualOrGreater( UnitsWithId( Children(owner@+0x30), unitId,
                                                UnitSelectionType.OnlyAliveAndTargetable = 3 ),
                                   Direct(maxSummons) )
    opts = SpawnUnitOptions.WithStatsFromConfig(cfg, abilityState, null, null)
    opts.<+0x18> = UseNormalAttackIfAble( activeTarget@+0x68, target@+0x60,
                                          parentAbility: Nullable(AbilityOrEffect(this.<+0x10>)),
                                          triggerAbilityOrEffect: null, options: default )
    tiles = First( SortTilesByUtilityForSummon( CanAddUnit(AdjacentTiles(target@+0x60)),
                                                UtilityType.Tile = 7, parent: caster@+0x48 ),
                   amount: 1, ignoreForcedTargets: 0 )
    return Repeat( If( NOT cap, Spawn(owner@+0x30, tiles, unitId, opts), null ), Direct(nrSummons) )

`this.<+0x10>` du `parentAbility` : le pseudo-C affiche `CenterSpace.Free.MersenneTwister$$get_Count`
(fold ICF, corps = `return *(int*)(this + 0x10)`) -- c'est le `TriggeredAbilityType` de CETTE ability
(`SynapticLinchpin` = 1192), pas un immediat. Contraste avec le `TriggeringAbilityIs(0x400)` du
trigger, qui EST un immediat et designe une AUTRE ability : c'est exactement le couple que le piege
du voisin confond.

`IdunBattle.Entities.Behaviours.RepeatBehaviour$$Execute` : `times` evalue UNE fois avant la boucle,
`n` iterations du MEME `entities`, **aucun court-circuit** (cf. la docstring du noeud `Repeat`).
Le cap est donc RE-EVALUE a chaque iteration (il est DANS le `If`), et les summons deja poses par
les iterations precedentes le voient -- inerte tant que `nrOfSummons == 1`, mais porte tel quel.

================================================================================================
FORME DU PORT
================================================================================================
* `CreateTrigger` -> `matches`, en EVALUANT les noeuds DSL du foyer `entities/triggers.py` sur
  l'`AbilityEntities` materialise (regime `BarbedOvipositor`), jamais une recopie de predicat ;
* `CreateBehaviour` -> un ARBRE DSL (`synaptic_linchpin_spawn_tree`) au-dessus de la feuille `Spawn`.

### BRANCHE `owner MORT + FinalJustice` -- TRANCHEE, ELLE VIT (#937-r1)
La valeur qui manquait est LUE, et elle ne s'appelait pas comme le depot le croyait. Le gate de
`IdunBattle.Operations.EvaluateTriggerOperation$$CanGetAbilityTrigger` est
`if (!ability.get_AllowForDeadOwner()) { if (IsUnit(owner) && !IsAlive(owner)) return 0; }` --
`ITriggeredAbility` **slot 8**, pas un `IsAtomic` (cf. `dispatch/core.py::_owner_gate_applies`).

`SynapticLinchpinAbility` **SURCHARGE** cette propriete (slot 22 de sa vtable, `flags=0x08c6` : pas
de `NewSlot`, donc un override), ce qu'aucune des deux tables ne montre -- son corps est trivial et
DEDUPLIQUE, donc `SynapticLinchpinAbility$$get_AllowForDeadOwner` est absent de `frida/methods.tsv`
ET de `ghidra/functions.tsv`. La RVA se resout par le TOKEN
(`Il2CppCodeGenModule.methodPointers`) et le corps se lit : **le MEME que
`FinalJusticeAbility$$get_AllowForDeadOwner`**, `b0 01 c3` = `mov al,1 ; ret` = **VRAI**.

Le natif laisse donc bien passer un porteur MORT jusqu'a `ShouldTrigger`, ou le disjunct
`OwnerIsAlive | (OwnerIsActor & TriggeringAbilityIs(FinalJustice))` tranche. `fire_on_death = True`
est le mirror de ce fait, et la branche cesse d'etre inatteignable cote port.

### RESIDUS EXPLICITES
* **`ignoreForcedTargets: 0`** du `First` natif : aucune contrepartie portee (le port n'a pas de
  notion de cible FORCEE cote selecteur). Le noeud `First(source, index=0)` du port est un
  `PickAtIndexSelector` ; il rend le MEME singleton que le `First(source, amount=1)` natif, mais
  cite une autre primitive -- ecart de CITATION, pas de valeur, tant que `amount == 1`.
* **`parentSelector = owner@+0x30`** : la feuille `Spawn` du port prend son parent/owner sur
  `entities.caster`. Pour une TRIGGERED, `Owner == Caster == le porteur` (c'est ce que pose
  `entities_from_state(state, owner_id, ...)`), donc l'ecart est nul ici ; il le resterait a
  documenter si un jour la feuille servait un chemin ou les deux slots divergent.
"""
from __future__ import annotations

from typing import Optional

from ....state import State
from ....components import StatsComponent, UnitComponent
from ....abilities.behaviours.combat import UseNormalAttackIfAble
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.summon import Spawn
from .....dsl.base import Const
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.behaviours import If, Repeat
from .....entities.effects.magnitude import ability_var
from .....entities.formulas import Count
from .....entities.selectors.accessors import Actor, ActiveTarget, Owner, Target
from .....entities.selectors.geometry import UnitsWithId
from .....entities.selectors.tiles import (AdjacentTiles, CanAddUnit, Caster, ChildrenOf,
                                           SortTilesByUtility)
from .....entities.selectors.units import First
from .....entities.traits.unit_trait import UnitTrait
from .....entities.triggered_ability_type import TriggeredAbilityType
from .....entities.triggers import AmountIsEqualOrGreater, AreFriends, HasTrait, IsAlive, Not
from .....entities.unit_selection_type import UnitSelectionType
from .....utilities.tile import UtilityType
from ..base import TriggeredAbility, TriggerEvent

SYNAPTIC_LINCHPIN_ABILITY = "SynapticLinchpin"

#: `On(EventTriggerType.NormalAttack, ...)` -- 38 (0x26), le vecteur `after_hit_normal_attack`.
_ON_NORMAL_ATTACK = int(EventTriggerType.NormalAttack)

# Les TROIS conjoints hors-`On` de `SynapticLinchpinAbility$$CreateTrigger`, batis une fois au
# niveau module (regime `barbed_ovipositor`) et EVALUES sur l'`AbilityEntities` materialise par
# `matches` -- surtout pas une recopie imperative des predicats, dont le substrat de traits
# divergerait de celui des noeuds (`entity_trait_names`, repli gameconfig #226).
_ACTOR_HAS_SYNAPSE = HasTrait(Actor(), int(UnitTrait.Synapse))          # a
_OWNER_ACTOR_FRIENDS = AreFriends(Owner(), Actor())                     # b
_TARGET_IS_ALIVE = IsAlive(Target())                                    # c


def synaptic_linchpin_spawn_tree(max_summons: int, nr_of_summons: int,
                                 ability_state: tuple | None = None) -> Repeat:
    """Arbre de `SynapticLinchpinAbility$$CreateBehaviour` (cf. l'en-tete du module pour le verbatim
    natif) :

        Repeat( If( NOT AmountIsEqualOrGreater(
                          UnitsWithId(Children(owner@+0x30), unitId, OnlyAliveAndTargetable),
                          Direct(maxSummons) ),
                    Spawn(owner@+0x30, First(SortTilesByUtilityForSummon(
                              CanAddUnit(AdjacentTiles(target@+0x60)), UtilityType.Tile,
                              parent: caster@+0x48), 1),
                          unitId, opts) ),
                Direct(nrOfSummons) )

    `max_summons` = `GetVariableForLevel(maxSummons)` -- il depend du NIVEAU du passif, donc il
    entre par argument (l'arbre est rebati par declenchement, comme tous les arbres du port).
    `ability_state` = le 2e argument de `SpawnUnitOptions$$WithStatsFromConfig`, sous lequel le
    Hormagaunt monte SES propres abilities et lit ses stats `summonHp`/`summonDmg`/`summonArmor`.

    `SortTilesByUtilityForSummon(tiles, utilityType, parent)` est la surcharge SANS `unit` de
    `SortTilesByUtility` (le `dc.unit` natif y est nul) -- le noeud porte l'exprime par
    `unit_sel=None`, et son `parent_sel` est le `caster@+0x48` LU au call-site, pas le owner."""
    unit_id = _summon_unit_id()
    # `UnitsWithId(Children(owner), unitId, 3)` : les enfants du PORTEUR (`DSLSelectors$$Children
    # (parent)` = `ChildrenOf`, PAS l'accumulateur `Children` du cast courant) qui sont des
    # Hormagaunts VIVANTS ET CIBLABLES. Le mode `3` est load-bearing ici : `ChildrenOf` ne filtre
    # rien, donc sans lui un Hormagaunt mort tiendrait un slot du cap.
    live_summons = UnitsWithId(ChildrenOf(Owner()), unit_id,
                               int(UnitSelectionType.OnlyAliveAndTargetable))
    cap_reached = AmountIsEqualOrGreater(Count(live_summons), Const(int(max_summons)))
    spawn = Spawn(
        # `First(SortTilesByUtilityForSummon(CanAddUnit(AdjacentTiles(target@+0x60)), 7, caster), 1)`
        First(SortTilesByUtility(CanAddUnit(AdjacentTiles(Target())),
                                 unit_sel=None,
                                 utility_type=int(UtilityType.Tile),
                                 parent_sel=Caster())),
        SYNAPTIC_LINCHPIN_ABILITY,
        # `opts.<+0x18>` = le sous-behaviour ON-APPEARANCE, fire PAR SUMMON par
        # `SpawnUnitBehaviour$$TriggerSpawnedUnitBehaviours` avec `activeTarget = unitSpawned` :
        # le Hormagaunt frais frappe la cible de l'attaque declenchante (i2 « which immediately
        # attacks the enemy »).
        on_appearance=UseNormalAttackIfAble(ActiveTarget(), Target()),
        ability_state=ability_state)
    return Repeat(If(Not(cap_reached), spawn), Const(int(nr_of_summons)))


def _summon_unit_id() -> str | None:
    """`GetStringConstant(cfg, AbilityConstantType.unitId = 0)` = `tyranSmnHormagaunt`."""
    import gameconfig as GC
    return ((GC.ability(SYNAPTIC_LINCHPIN_ABILITY) or {}).get("constants") or {}).get("unitId")


def _nr_of_summons() -> int:
    """`GetNumberConstant(cfg, AbilityConstantType.nrOfSummons = 16)` -- le nombre d'iterations du
    `Repeat`. Constante de config (pas une variable per-niveau) ; absente -> 0 iteration, ce que
    rend aussi `RepeatBehaviour$$Execute` sur un `times <= 0`."""
    import gameconfig as GC
    raw = ((GC.ability(SYNAPTIC_LINCHPIN_ABILITY) or {}).get("constants") or {}).get("nrOfSummons")
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


class SynapticLinchpinAbility(TriggeredAbility):
    """`SynapticLinchpinAbility` (triggered 1192, passif d'`tyranWingedPrime`) -- a chaque attaque
    NORMALE d'une unite AMIE portant `Synapse` (le Winged Prime compris) contre un ennemi qui
    SURVIT, un Hormagaunt apparait sur la meilleure tuile libre adjacente a la cible et l'attaque
    immediatement, tant que le nombre de Hormagaunts vivants issus de ce passif reste sous
    `maxSummons[level]`. Arbre natif des deux faces : en-tete du module."""
    event_id = _ON_NORMAL_ATTACK
    TRIGGERED_ABILITY_ID = int(TriggeredAbilityType.SynapticLinchpin)      # 1192
    # `SynapticLinchpinAbility$$get_AllowForDeadOwner` (`ITriggeredAbility` slot 8, surcharge au
    # slot 22 de la vtable) rend **VRAI** -- corps `b0 01 c3`, PARTAGE avec
    # `FinalJusticeAbility$$get_AllowForDeadOwner` (cf. l'en-tete du module, #937-r1). Sans lui,
    # `dispatch/core.py` ecartait le porteur MORT AVANT `matches`, et le disjunct
    # `OwnerIsActor & TriggeringAbilityIs(FinalJustice)` de `_owner_alive_or_final_justice` ne
    # pouvait jamais mordre.
    fire_on_death = True

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        if ev.actor_id is None or ev.target_id is None:
            return False
        # L'`AbilityEntities` que le natif tient pour tout `CreateTrigger` : `owner`/`caster` = le
        # porteur, `actor` = l'ATTAQUANT de l'evenement, `target` = sa cible.
        entities = entities_from_state(state, self.owner_id, ev.target_id, ev.actor_id)
        if not self._owner_alive_or_final_justice(state, ev):        # gate du `On` (cf. en-tete)
            return False
        if not _ACTOR_HAS_SYNAPSE.should_trigger(entities):          # HasTrait(actor, Synapse)
            return False
        if not _OWNER_ACTOR_FRIENDS.should_trigger(entities):        # AreFriends(owner, actor)
            return False
        # `IsAlive(target@+0x60)` = « l'ennemi n'est PAS defait » (i2). Le vecteur `On(0x26)` est
        # emis APRES la resolution des degats, donc une cible tuee par le coup y est deja `alive
        # = False`.
        return bool(_TARGET_IS_ALIVE.should_trigger(entities))

    def _owner_alive_or_final_justice(self, state: State, ev: TriggerEvent) -> bool:
        """`OwnerIsAlive | (OwnerIsActor & TriggeringAbilityIs(FinalJustice))` -- le gate effectif du
        `On(NormalAttack, ownerNeedsToBeAlive: NOT(...))`, cf. l'en-tete du module.

        ⚠ **IL MORD DEPUIS #937-r1** : `fire_on_death = True` (mirror de
        `get_AllowForDeadOwner`, LU vrai sur cette classe) laisse le porteur MORT franchir le gate
        de `dispatch/core.py`, donc la branche gauche n'est plus toujours vraie quand `matches` est
        appele. Le regime discriminant est le seul que le natif autorise : le porteur est mort ET
        c'est LUI l'acteur ET le coup vient de l'attaque post-mortem du trait `FinalJustice`
        (`ev.triggering_ability == 1024`, canal `AbilityEntities+0x60` que
        `IdunBattle.Entities.Abilities.BaseTriggeredAbility$$Execute` pose AVANT le behaviour, donc
        herite par l'attaque qu'il engendre). Un allie Synapse qui frappe pendant que le Prime est
        mort ne passe PAS (`OwnerIsActor` faux)."""
        e = state.get_entity(self.owner_id)
        uc = None if e is None else e.get_component(UnitComponent)
        if uc is None or bool(uc.alive):                  # `OwnerIsAlive`
            return True
        # `OwnerIsActor & TriggeringAbilityIs(TriggeredAbilityType.FinalJustice = 1024)`
        return (ev.actor_id == self.owner_id
                and ev.triggering_ability == int(TriggeredAbilityType.FinalJustice))

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        level, mult = self._ability_state(state)
        max_summons = ability_var(SYNAPTIC_LINCHPIN_ABILITY, "maxSummons", level,
                                  multiplier_pct=mult)
        if max_summons is None:
            return None                                   # config illisible -> no-op fidele
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, self.owner_id, ev.target_id, ev.actor_id)
        synaptic_linchpin_spawn_tree(int(max_summons), _nr_of_summons(),
                                     ability_state=(level, mult)).execute(entities, ectx)
        spawned = [p["unit"] for n, p in ectx.emitted if n == "SpawnUnit"]
        if not spawned:
            return None                                   # cap atteint / aucune tuile -> no-op
        attacks = [p for n, p in ectx.emitted if n == "UseNormalAttackIfAble"]
        return {"ability": SYNAPTIC_LINCHPIN_ABILITY, "unit": self.owner_id,
                "actor": ev.actor_id, "target": ev.target_id,
                "spawned": spawned, "attacks": attacks}

    def _ability_state(self, state: State) -> tuple:
        """L'`AbilityState` que `CreateBehaviour` recoit en argument, c'est-a-dire celui du PASSIF du
        porteur : c'est lui qui indexe `maxSummons` ET qui part dans
        `SpawnUnitOptions$$WithStatsFromConfig`. `passive_ability_level` absent -> repli sur
        `active_ability_level` (les deux valent `targetAbilityLevel` apres `buildNormalizedBC`)."""
        e = state.get_entity(self.owner_id)
        sc = e.get_component(StatsComponent) if e is not None else None
        ctx = getattr(sc, "ctx", None)
        level = getattr(ctx, "passive_ability_level", None)
        if level is None:
            level = getattr(ctx, "active_ability_level", None)
        mult = int(getattr(ctx, "ability_variables_multiplier", 100) or 100)
        return level, mult
