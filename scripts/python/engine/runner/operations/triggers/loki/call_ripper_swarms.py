"""#890-r3 -- la PHASE 2 de `CallRipperSwarms` : le SPAWN DIFFERE des Ripper Swarms.

La PHASE 1 (le cast, `abilities/tyranids.py::CallRipperSwarmsAbility`) pose l'effet-BOND
`1094 CallRipperSwarms_PendingSummon` sur QUATRE tuiles et ne spawne RIEN. Sans ce module, la
marque etait posee offline et **rien n'apparaissait jamais**.

i2 : les rippers « emerge from the ground at the beginning of the Hive Tyrant's next turn, unless
their hex is occupied by another unit ».

===================================================================================================
`...CallRipperSwarms_PendingSummonEffect$$CreateHandleTriggerAbilitiesInternal` -- LU AUX OCTETS
===================================================================================================
Deux `DSLFactory.Triggered` sont AJOUTES a l'`ArraySet` herite d'`ABondEffect` -- lequel est VIDE
ici, et c'est MESURE : `probe_462_r4b_r1_r1_r1_r1_bond_removal.py --step declared` rend, sur le
build COURANT, `get_Range = none` / `get_Adjacent = false` /
`get_RemoveOnBondedEntityDeath = false` pour cette classe. Les deux ci-dessous sont donc les SEULS
triggers de l'effet.

    (1)  On(0x15 = TurnStart_DelayedAttacks)  &  IsTurnOf( BondedEntitySelector )
         ->  If( IsCanAddUnit(Owner@<DSLSelectors+0x30>),
                 TriggerAbility( targets = bonded, ability = <GetSpawnAbilityType>,
                                 actor = bonded, caster = bonded,
                                 target = Owner@<DSLSelectors+0x30>,
                                 sel4 = null, groupType = 0,
                                 ignoreUnitHavingAbility = **false** ) )
             op_BitwiseAnd  GetRemoveEffectBehaviour()

    (2)  On(0x1f = PreUnitMove)  &  get_OwnerIsTargetTile
         ->  GetRemoveEffectBehaviour()                       <-- RETRAIT SEUL, AUCUN spawn

⚠ **LE SECOND EST UN RETRAIT SEUL, ET LA VERSION PRECEDENTE DE LA FICHE #890 DISAIT L'INVERSE** --
elle envoyait les DEUX vers `If(IsCanAddUnit, TriggerAbility(...))`. Porter cela ferait apparaitre
un ripper des qu'une unite marche sur la tuile marquee : l'inverse exact du natif ET de l'i2.

⚠ **LE PREMIER RETIRE L'EFFET DANS TOUS LES CAS.** Le `op_BitwiseAnd` porte sur le BEHAVIOUR : le
`If` et le `GetRemoveEffectBehaviour()` sont DEUX termes d'une somme, pas un if/else. La marque
disparait donc au turn-start du bonded meme quand la tuile est occupee -- ce qui est exactement
« unless their hex is occupied » : pas de ripper, et pas de marque non plus.

⚠ **`ignoreUnitHavingAbility` VAUT `false`, LU AUX OCTETS** (`xor r13d, r13d` puis `mov [rsp+0x48],
r13` / `mov [rsp+0x40], r13b` autour du `call ...DSLBehaviors$$TriggerAbility`). Le gate
`GetAbilityState(bonded, <spawnType>)` s'applique donc -- et c'est COHERENT, puisque
`GetSpawnAbilityType` choisit precisement l'ability que le bonded POSSEDE. C'est l'inverse du
call-site `FinalVengeance_UnitEffect`, qui passe `true` (#1002-r1).

===================================================================================================
`$$GetSpawnAbilityType` -- LES TROIS LITTERAUX, RELUS AUX OCTETS
===================================================================================================
Le decompile ne montre pas les constantes (elles passent par
`IdunBattle.Core.AbilityOrEffect$$op_Implicit`). Au desassemblage :

    mov r8d, 0x44d  -> ActorHasTriggeredAbility(bonded, 1101)      mov edx, 0x44d -> Direct(1101)
    mov r8d, 0x44c  -> ActorHasTriggeredAbility(bonded, 1100)      mov edx, 0x44c -> Direct(1100)
                                                                   mov edx, 0x44b -> Direct(1099)

    If( ActorHasTriggeredAbility(bonded, 1101), Direct(1101),
    If( ActorHasTriggeredAbility(bonded, 1100), Direct(1100),
        Direct(1099) ) )

soit **le palier LE PLUS HAUT que le porteur possede reellement**. Les trois paliers correspondent
aux trois actives `1052 / 1054 / 1055` (table `ACTIVE_DERIVED_TRIGGERED_ABILITY_IDS`, relue du
`.cctor` natif), et chacune porte SON `unitId` au gameconfig : Leviathan / Kronos / Gorgon.

COLLAPSE ASSUME : ce `DSLSelectors$$If` a des branches CONSTANTES (`Direct(<litteral>)`), donc il
ne fait que choisir un entier. Le port n'a aucun selecteur d'`AbilityOrEffect` et l'ecrire en
`if/elif/else` ne perd RIEN d'observable -- contrairement a un `If` dont les branches selectionnent
des entites. Le predicat, lui, passe par le FOYER du gate natif
(`abilities/behaviours/lifecycle::_unit_has_triggered_ability`, mirror de
`IdunBattle.Entities.UnitExtensions$$GetAbilityState`), jamais par une lecture de kit recablee.

===================================================================================================
`...CallRipperSwarms_SpawnAbility$$CreateBehaviour` -- MIRROR
===================================================================================================
    options = SpawnUnitOptions.WithStatsFromConfig( config@this+0x20, abilityState, null, null )
    options.<+0x18 : onAppearance> = PerformAIAttack( ActiveTarget@<DSLSelectors+0x68>, 1, null )
    return Spawn( parent  = Caster@<DSLSelectors+0x48>,
                  targets = Target@<DSLSelectors+0x60>,
                  unitId  = AbilityConfiguration.GetStringConstant(config, 0),
                  options )

Le `caster` de l'`AbilityEntities` de l'ability declenchee est le BONDED (le Hive Tyrant) et son
`target` est la TUILE marquee -- c'est ce que `TriggerAbility` ci-dessus lui passe. Le port
reconstruit donc l'`AbilityEntities` a l'identique avant d'executer l'arbre : `Spawn` EXIGE un
caster-UNITE (il lit son `OwnerComponent`/`StatsComponent`), et un caster-tuile le ferait sortir
en no-op SILENCIEUX.

===================================================================================================
ECARTS NOMMES
===================================================================================================
* **Le kit du ripper n'est pas resoluble offline.** `GetStringConstant(0)` rend
  `GuildBoss2Npc1TyranRipperSwarmLeviathan`, qui n'existe NI comme `id` NI comme `visualId` dans le
  gameconfig (mesure : les trois index `lineup`/`npc`/`summons` rendent zero). `build_summon_context`
  degrade alors proprement -- stats de combat correctes (elles viennent des variables `summonHp` /
  `summonDmg` / ... de l'ability, presentes), mais traits VIDES, arme ABSENTE et `Movement = 0`.
  L'unite existe donc et occupe sa tuile, mais son `PerformAIAttack` d'apparition ne trouvera aucune
  arme. Le kit voisin `tyranNpc2RipperSwarm` (memes 5 hits `Physical`, `Movement 3`, traits
  `InstinctiveBehaviour`/`Swarm`/`BattleFatigue`) LUI RESSEMBLE mais n'est pas apparie par une
  lecture -- l'y substituer serait une invention. C'est un ecart de SEEDING, pas de mecanique.
* **`ActorHasTriggeredAbility` sur les paliers 2 et 3.** Le seul porteur confrontable
  (`tyranBossHiveTyrantLeviathan`) ne possede QUE `1099` (`triggered_ability_ids` rend
  `[1095, 1056, 1099]`), donc les deux bras hauts du fork ne sont pas exerces.
"""
from __future__ import annotations

from typing import Optional

from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.behaviours import If
from .....entities.effect_type import EffectType
from .....entities.selectors.accessors import ActiveTarget, Owner, Target
from .....entities.selectors.units import Tiles
from .....entities.triggered_ability_type import TriggeredAbilityType
from .....entities.triggers import IsCanAddUnit
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.lifecycle import (TRIGGERED_ABILITY_BEHAVIOURS, TriggerAbility,
                                                _unit_has_triggered_ability)
from ....abilities.behaviours.summon import PerformAIAttack, Spawn
from ....components import OwnerComponent
from ....state import State
from ...remove_effects import remove_effect_instance
from ..base import TileEffectTrigger, TriggerEvent

#: L'effet-BOND pose sur les tuiles par la phase 1 (`abilities/tyranids.py`).
CALL_RIPPER_SWARMS_PENDING_SUMMON = int(EffectType.CallRipperSwarms_PendingSummon)      # 0x446

#: Les trois paliers de `$$GetSpawnAbilityType`, du PLUS HAUT au plus bas -- l'ordre est celui du
#: fork natif, et il est load-bearing : le premier que le porteur possede gagne.
SPAWN_ABILITY_PALIERS = (
    int(TriggeredAbilityType.CallRipperSwarms_Spawn3),                                  # 0x44d
    int(TriggeredAbilityType.CallRipperSwarms_Spawn2),                                  # 0x44c
    int(TriggeredAbilityType.CallRipperSwarms_Spawn),                                   # 0x44b
)

#: `AbilityConfiguration` que lit `CallRipperSwarms_SpawnAbility` (`config@this+0x20`). Un palier
#: TRIGGERED lit la config de l'ACTIVE dont il derive -- appariement LU dans
#: `ACTIVE_DERIVED_TRIGGERED_ABILITY_IDS` (`ActiveAbility$$GetDerivedTriggeredAbilities`,
#: `<statics>+0x30`), pas devine du nom. Chacune porte SON `unitId` (Leviathan/Kronos/Gorgon) et
#: son propre jeu de variables `summon*`.
SPAWN_ABILITY_CONFIG = {
    int(TriggeredAbilityType.CallRipperSwarms_Spawn): "CallRipperSwarms",               # <- 1052
    int(TriggeredAbilityType.CallRipperSwarms_Spawn2): "CallRipperSwarms2",             # <- 1054
    int(TriggeredAbilityType.CallRipperSwarms_Spawn3): "CallRipperSwarms3",             # <- 1055
}


def call_ripper_swarms_spawn_tree(config_name: str):
    """`...CallRipperSwarms_SpawnAbility$$CreateBehaviour` -- MIRROR 1:1, UNE feuille.

    `Target()` = `<DSLSelectors+0x60>` : la TUILE marquee, que `TriggerAbility` a posee en `target`
    de l'`AbilityEntities`. `ActiveTarget()` = `<DSLSelectors+0x68>`, que `Spawn` LIE au summon
    fraichement pose avant de jouer l'on-appearance (mirror de
    `SpawnUnitBehaviour$$TriggerSpawnedUnitBehaviours`).

    `PerformAIAttack(<sel>, True, None)` est le noeud `DSLBehaviors$$PerformAIAttack` (et non son
    cousin `...FromCurrentPosition`) : `allowMoveAction = 1`, `moveAmount = null` -- le ripper
    APPROCHE puis attaque, i2 « immediately takes a turn »."""
    return Spawn(Target(), config_name,
                 on_appearance=PerformAIAttack(ActiveTarget(), True, None))


def spawn_ability_type(state: State, bonded_id: Optional[int]) -> int:
    """`...CallRipperSwarms_PendingSummonEffect$$GetSpawnAbilityType` -- le palier LE PLUS HAUT que
    `bonded_id` possede reellement.

    Le predicat passe par `_unit_has_triggered_ability`, le FOYER du gate natif
    (`UnitExtensions$$GetAbilityState`) -- le MEME que celui que `TriggerAbility` appliquera juste
    apres, puisque `ignoreUnitHavingAbility` vaut `false`. Les faire diverger produirait un
    `notCarrying` silencieux : on choisirait un palier que le gate refuserait ensuite.

    Defaut `1099` quand rien n'est lisible : c'est le bras `else` du fork natif, pas un repli
    invente."""
    if bonded_id is not None:
        for palier in SPAWN_ABILITY_PALIERS[:-1]:            # les deux bras `ActorHasTriggeredAbility`
            if _unit_has_triggered_ability(state, int(bonded_id), palier):
                return palier
    return SPAWN_ABILITY_PALIERS[-1]                          # `Direct(0x44b = 1099)`


def _call_ripper_swarms_spawn(state, owner_id, entities=None, ectx_appelant=None) -> Optional[dict]:
    """Entree de `TRIGGERED_ABILITY_BEHAVIOURS` pour les TROIS paliers.

    `owner_id` = l'unite DECLENCHEE, c.-a-d. le BONDED (`TriggerAbility(targets = bonded, ...)`).
    La TUILE arrive par l'`AbilityEntities` du declencheur, ou le trigger d'effet l'a posee en
    CASTER (patron invariable des `TileEffectTrigger` du port : `entities_from_state(state,
    <tile_id>, ...)`).

    L'`AbilityEntities` est RECONSTRUIT ici -- caster = le bonded, target = la tuile -- parce que
    c'est ce que le natif passe a l'ability declenchee (`TriggerAbilityBehaviour$$Execute` resout
    ses quatre selecteurs et les lui transmet). Le port de `TriggerAbility` ne les reconstruit pas :
    il relaie l'`AbilityEntities` du DECLENCHEUR (contrat documente au registre). Sans cette
    reconstruction, `Spawn` verrait une TUILE en caster et sortirait en no-op SILENCIEUX."""
    tuile = None if entities is None else (entities.caster or {}).get("id")
    if tuile is None or owner_id is None:
        return None
    aid = spawn_ability_type(state, int(owner_id))
    config_name = SPAWN_ABILITY_CONFIG.get(int(aid))
    if config_name is None:
        return None
    ent = entities_from_state(state, int(owner_id), int(tuile))
    ectx = ectx_appelant if ectx_appelant is not None else ExecutionContext(state=state,
                                                                            rng=state.rng)
    call_ripper_swarms_spawn_tree(config_name).execute(ent, ectx)
    spawns = [p for n, p in ectx.emitted if n == "SpawnUnit"]
    return {"ability": config_name, "triggered": int(aid), "summoner": int(owner_id),
            "tile": int(tuile), "spawned": [p.get("unit") for p in spawns]}


for _palier in SPAWN_ABILITY_PALIERS:
    TRIGGERED_ABILITY_BEHAVIOURS[_palier] = _call_ripper_swarms_spawn


class _CallRipperSwarmsPendingSummon(TileEffectTrigger):
    """Base des DEUX `Triggered()` de `$$CreateHandleTriggerAbilitiesInternal`. `owner_id` = l'id
    d'entite-TUILE (le marqueur est pose sur des tuiles, pas sur des unites)."""
    effect_type = CALL_RIPPER_SWARMS_PENDING_SUMMON

    def _instance(self, state: State):
        """L'instance 1094 portee par ma tuile. `EffectsState.by_unit` est clé par l'entite
        PORTEUSE -- unite ou tuile indifferemment."""
        eff = getattr(state, "effects", None)
        if eff is None:
            return None
        for e in eff.by_unit.get(int(self.owner_id), []):
            if not e.consumed and int(getattr(e, "effect_type", -1)) == self.effect_type:
                return e
        return None

    def _bonded(self, state: State) -> Optional[int]:
        """`ABondEffect$$BondedEntitySelector(this)` -- l'entite BONDEE, c.-a-d. le summoner.

        TRI-ETAT : `BaseEffect.bonded` vaut `None` quand le canal de capture n'a pas publie le
        `BondedEntityId` (limite connue du canal `tileMeta`, cf. `TunnelingHorrorPendingSummonEffect`).
        On retombe alors sur `source` -- `EffectComponent.SourceUnit @+0x10` -- et c'est EXACT pour
        cet effet precis : `AddBondEffect(0x446, ..., source = Caster@+0x48, ...,
        bondedEntity = Caster@+0x48, ...)` passe le MEME selecteur aux deux slots (LU au
        decompile de `CallRipperSwarmsAbility$$ExecuteBehaviour`). Ce repli n'est donc pas une
        approximation : c'est une egalite etablie AU SITE DE POSE, et elle ne vaut que la."""
        inst = self._instance(state)
        if inst is None:
            return None
        b = getattr(inst, "bonded", None)
        if b is not None:
            return int(b)
        s = getattr(inst, "source", None)
        return None if s is None else int(s)

    def _consume(self, state: State) -> bool:
        """`BaseEffect$$GetRemoveEffectBehaviour(this)`. Foyer PARTAGE `remove_effect_instance`,
        jamais un `consumed = True` recable a la main : le retrait doit emettre ses deux events
        `On(0x3f = PreEffectRemoved)` / `On(0x40 = EffectRemoved)` et de-enregistrer le nom."""
        inst = self._instance(state)
        if inst is None:
            return False
        return bool(remove_effect_instance(state, int(self.owner_id), inst))


class CallRipperSwarmsSpawnOnBondedTurnStart(_CallRipperSwarmsPendingSummon):
    """Triggered n°1 : `On(0x15 = TurnStart_DelayedAttacks) & IsTurnOf(BondedEntitySelector)`.

    OBSERVABLE : au debut du tour du Hive Tyrant, un Ripper Swarm emerge sur chaque tuile marquee
    QUI EST ENCORE LIBRE, et la marque disparait -- libre ou non."""
    event_ids = (int(EventTriggerType.TurnStart_DelayedAttacks),)                       # 0x15
    event_id = int(EventTriggerType.TurnStart_DelayedAttacks)

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        # `IsTurnOf(bonded)` : le tour qui DEBUTE est celui du camp du bonded. Le port lit
        # `ev.player_id` (le joueur dont le tour commence) et le compare au proprietaire du bonded,
        # comme `HealingBalmsDelayedHeal` et `ArmourOfShriekingSoulsDrainOnTurnStart`.
        bonded = self._bonded(state)
        if bonded is None or ev.player_id is None:
            return False
        e = state.get_entity(int(bonded))
        oc = e.get_component(OwnerComponent) if e is not None else None
        if oc is None or oc.player is None:
            return False
        return int(oc.player) == int(ev.player_id)

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        bonded = self._bonded(state)
        # `entities_from_state(state, <tile_id>, <unit_id>)` -- le patron INVARIABLE des
        # `TileEffectTrigger` du port : la tuile en CASTER (donc `Owner()` y retombe, via le repli
        # `ctx.owner or ctx.caster`), l'unite concernee en TARGET. Ici la cible est le BONDED, ce
        # qui donne a `TriggerAbility(Target(), ...)` exactement le selecteur natif
        # `BondedEntitySelector` -- meme collapse que `ghost_revive` fait de `EffectSource`.
        entities = entities_from_state(state, int(self.owner_id),
                                       None if bonded is None else int(bonded))
        ectx = ExecutionContext(state=state, rng=state.rng)
        aid = spawn_ability_type(state, bonded)
        # `IsCanAddUnit(Owner@<DSLSelectors+0x30>)` : le natif passe l'ENTITE-tuile directement, et
        # son `CanAddUnit` la consomme en enchainant `GetMainTile(element)` puis `get_Id` (la meme
        # paire d'appels que documente `Spawn`). Cote port, `CanAddUnit` attend des IDS et `Owner()`
        # rend un DICT : sans normalisation, la boucle itere les CLES du dict et lève `KeyError:
        # 'id'` (mesure du premier jet). `Tiles(<sel>, as_ids=True)` EST le mirror de cette paire --
        # DOMAINE MIXTE, donc identite sur un id de tuile -- ce n'est pas un noeud ajoute a l'arbre.
        If(IsCanAddUnit(Tiles(Owner(), as_ids=True)),
           TriggerAbility(Target(), aid)).execute(entities, ectx)
        trig = next((p for (n, p) in ectx.emitted if n == "TriggerAbility"), None)
        # SECOND terme de l'`op_BitwiseAnd` : le retrait, INCONDITIONNEL. Il ne depend pas du `If`
        # -- c'est ce qui realise le « unless their hex is occupied » sans laisser la marque.
        removed = self._consume(state)
        return {"effect": EffectType.CallRipperSwarms_PendingSummon.name,
                "tile": int(self.owner_id), "bonded": bonded, "ability": int(aid),
                "dispatched": None if trig is None else bool(trig.get("dispatched")),
                "notCarrying": [] if trig is None else list(trig.get("notCarrying") or ()),
                "results": [] if trig is None else list(trig.get("results") or ()),
                "removed": removed}


class CallRipperSwarmsRemoveOnUnitMovesIn(_CallRipperSwarmsPendingSummon):
    """Triggered n°2 : `On(0x1f = PreUnitMove) & get_OwnerIsTargetTile` -> `GetRemoveEffectBehaviour()`.

    RETRAIT SEUL -- AUCUN spawn. Une unite qui se DEPLACE sur une tuile marquee efface la marque :
    le ripper n'y emergera pas. C'est le « unless their hex is occupied by another unit » de l'i2,
    pris en amont du turn-start.

    `get_OwnerIsTargetTile` = « la tuile PORTEUSE est la tuile-cible de l'evenement ». Sur
    `On(0x1f)` le port dispose de `ev.dest_tile` -- la DESTINATION `(col, row)`, threadee par le
    seul `MoveUnitOperation.execute`. C'est le seul vecteur qui la porte, et c'est precisement
    celui-ci. `dest_tile is None` -> le trigger se TAIT (pas de retrait) : confondre « non mesure »
    avec « les tuiles sont egales » effacerait des marques au hasard."""
    event_ids = (int(EventTriggerType.PreUnitMove),)                                    # 0x1f
    event_id = int(EventTriggerType.PreUnitMove)

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        dest = getattr(ev, "dest_tile", None)
        if dest is None:
            return False
        co = self._tile_coord(state)
        if co is None:
            return False
        return (int(dest[0]), int(dest[1])) == (int(co[0]), int(co[1]))

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        if not self._consume(state):
            return None
        return {"effect": EffectType.CallRipperSwarms_PendingSummon.name,
                "tile": int(self.owner_id), "mover": ev.actor_id, "removed": True}
