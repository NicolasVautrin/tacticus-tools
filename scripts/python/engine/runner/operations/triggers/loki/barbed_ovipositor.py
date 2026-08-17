"""`BarbedOvipositor` (passif d'`tyranParasite` << Parasite of Mortrex >>, HERO Tyranids) — canal **T**
(`ABILITY_TRIGGERS`), jusqu'ici GAP-ABSENT dans `docs/rl/passive-ability-coverage.md`.

i2 : « When the Parasite of Mortrex defeats a unit it targeted that is not Mechanical it summons a
Ripper Swarm in the defeated unit's hex. Ripper Swarm stats: 4583 Health 800 Damage 1091 Armour »

================================================================================================
RE (decompile ghidra, build `gqfc5mff6c`) — les DEUX faces du meme artefact natif
================================================================================================
Slots `AbilityEntities` de `IdunBattleLogic.Entities.DSLSelectors$$InitializeShared` :
`0x138 TriggeringAbility · 0x148 Owner · 0x158 Actor · 0x160 Caster · 0x178 Target · 0x180 ActiveTarget`.

## `IdunBattleLogic.Entities.Abilities.Triggered.Loki.BarbedOvipositorAbility$$CreateTrigger`

    On(UnitDeath = 0, 1)
    & OwnerIsActor                                       # le porteur est le TUEUR
    & AreEnemies(owner@0x148, target@0x178)
    & NOT IsObjectOrSteppable(target@0x178)
    & NOT TriggeringAbilityIs(0x438)                     # cf. << gate inerte >> ci-dessous
    & NOT HasTrait(target@0x178, 5 = Mechanical)

`IdunBattleLogic.Entities.DSLTriggers$$IsObjectOrSteppable(x)` = `HasTrait(x, 0x1b = 27 Steppable)
| HasTrait(x, 0xd = 13 Object)` (decompile LU, pas deduit — relu VERBATIM sur `rnca9r7q6c`). Ce
conjoint et son voisin `NOT HasTrait(target, 5)` passent par les NOEUDS DSL partages
(`entities/triggers.py`), plus par une recopie locale du couple de traits : cf. << SUBSTRAT >>.

`TriggeringAbilityIs` est INLINE par ghidra sur ce site : `AreEqual(@0x138, Direct(AbilityOrEffect
(0x438)))` puis `op_LogicalNot` — structure IDENTIQUE a `IdunBattleLogic.Entities.DSLFactory$$
TriggeringAbilityIs` (qui lit le MEME slot `@0x138`). **QUALIFICATION DE L'ENUM** (piege #157/#158) :
le call-site vise l'overload `IdunBattle.Core.AbilityOrEffect$$op_Implicit` qui pose
`set_TriggeredAbility` (call decode a `BarbedOvipositorAbility$$CreateTrigger+0xfc` -> l'un des
QUATRE overloads homonymes ; les trois autres posent `set_ActiveAbility` / `set_Effect`) ->
**`TriggeredAbilityType.ItsGonnaBlow` = 1080**, PAS `ActiveAbilityType.HellfireShells` (1080) ni
`EffectType.BeastSnagga_ExtraDmg` (1080).

## `IdunBattleLogic.Entities.Abilities.Triggered.Loki.BarbedOvipositorAbility$$CreateBehaviour`

    unitId = GetStringConstant(cfg, 0)                       # "tyranSmnRipperSwarm"
    opts   = SpawnUnitOptions.WithStatsFromConfig(cfg, level)   # AUCUN +0x10 (effet), AUCUN +0x18
                                                                # (on-appearance) -> le Ripper N'ATTAQUE PAS
                                                                # a l'apparition (contraste `ItItches`)
    Spawn( owner@0x148,
           PickRandomly(CanAddUnit(Tiles(target@0x178)),        1, 0, 0x7fffffff, false)
             .Otherwise(
           PickRandomly(CanAddUnit(AdjacentTiles(target@0x178)), 1, 0, 0x7fffffff, false)),
           unitId, opts )

AUCUN cap de summons dans cet arbre (et `gameconfig.BarbedOvipositor.variables` n'a pas de
`maxSummons`) : le passif peut poser autant de Rippers qu'il fait de kills qualifiants.

================================================================================================
FORME DU PORT
================================================================================================
* `CreateTrigger` COLLAPSE imperativement dans `matches` (doctrine #149, comme SwornProtector /
  ControlEdict / MasterAnnihilator) ;
* `CreateBehaviour` = un ARBRE DSL au-dessus de l'Operation `_spawn_config_grot` (feuille `Spawn`).

### EQUIVALENCE PROUVEE du tile-selecteur (pas une approximation)
Le port ecrit `PickRandomly(Otherwise(A, B), 1)` la ou le natif ecrit
`Otherwise(PickRandomly(A,1), PickRandomly(B,1))` — les deux consomment le MEME flux RNG :
  * `IdunBattle.DSL.OtherwiseSelector$$Select` (decompile LU) evalue la branche primaire, teste
    `Enumerable.Any(...)`, et n'evalue la branche de repli QUE si elle est vide -> **lazy** ;
  * `IdunBattle.Entities.Selectors.PickRandomAmountSelector$$Select` sort AVANT tout tirage quand
    `candidates.Count < 1` (loi #130, foyer `abilities/loki/splash.py::_pick_randomly_n`).
  => `PickRandomly(X,1)` est vide ssi `X` est vide, et consomme 0 tirage dans ce cas. Les deux
  ecritures rendent donc le meme element ET le meme nombre de tirages (1 si A ou B non vide, 0 si
  les deux sont vides). Le fold `pick_n=1` de la feuille `Spawn` est le seul endroit qui voit
  `state.rng` (meme convention que SupremeCommander/SendInTheNextWave).

### POURQUOI le `Otherwise` existe (et n'est pas mort)
La branche primaire `CanAddUnit(Tiles(dead))` = la tuile du mort. `CanAddUnit` exige `walkable` ET
libre. Le mort ne l'occupe plus (le port : `alive=False` -> `CanAddUnit` l'ignore), donc elle est
libre — MAIS une unite `Flying` (« can traverse impassable hexes ») peut mourir SUR une tuile non
walkable, et la branche de repli (une adjacente libre au hasard) prend alors le relais.

### SUBSTRAT DE TRAITS -- pourquoi la migration vers le foyer n'est PAS cosmetique
Les deux conjoints de TRAIT (`NOT IsObjectOrSteppable(target)`, `NOT HasTrait(target, 5)`) lisaient
`StatsComponent.ctx.traits` BRUT, avec le repli `set()` quand le composant manque. Or le natif lit
`IdunBattle.Entities.Components.BaseUnitComponent$$HasTrait`, et un CADAVRE garde son composant :
le `set()` etait un ARTEFACT du port, pas une lecture. Les noeuds DSL, eux, lisent `_traits` =
`entity_trait_names` (le repli gameconfig #226).

MESURE (build `rnca9r7q6c`, runner live, `probe_..._r3 --step substrat`) :
  * unite VIVANTE au chargement -> `StatsComponent` present, `ctx.traits_measured = True` : les deux
    substrats coincident **bit pour bit** (grande-alliance comprise). La migration est donc
    VALUE-PRESERVING sur le regime NOMINAL -- celui de tous les bras de
    `tests/engine/runner/test_barbed_ovipositor_live.py`.
  * unite MORTE AU CHARGEMENT -> **absente de `combatSnapshot.units`**, donc AUCUN `StatsComponent`
    (mesure : `tyranParasite` mort, `combatSnapshot` = {77, 79, 83}, `decisionView` = {77, 79, 81,
    83}). Substrat BRUT = `[]` -> les DEUX gates AVEUGLES ; substrat foyer =
    `['Flying','Hero','Synapse','Xenos']` -> gates VOYANTS.
Ce second regime est ATTEIGNABLE ici parce que `On(UnitDeath)` peut viser une entite RESSUSCITEE :
`IdunBattle.Operations.ResurrectUnitOperation$$Execute` (port `operations/resurrect.py`) cible
explicitement une unite DEFEATED, et ni lui ni `operations/revive.py` ne pose de `StatsComponent`.
Le port spawnait alors un Ripper sur un mort `Steppable`/`Object`/`Mechanical` que le natif ecarte.

### RESIDUS EXPLICITES
* `NOT TriggeringAbilityIs(TriggeredAbilityType.ItsGonnaBlow = 1080)` : **NON PORTE, INERTE**. Le
  vecteur `unit_death_triggers` (`../dispatch.py`) ne threade pas d'`ability_type` sur `On(0)`, et
  AUCUN poseur d'`ItsGonnaBlow` n'existe cote port (passif de la caisse de munitions npc, i2 « If
  this unit is Overkilled the ammo box explodes » -> GAP-ABSENT npc-only dans
  `docs/rl/passive-ability-coverage.md`). Le gate ne peut donc jamais MORDRE offline : le port
  l'omet plutot que de le simuler avec un champ qui ne porte pas la meme information. A rouvrir le
  jour ou `ItsGonnaBlow` est porte.
* `SpawnUnitOptions.WithStatsFromConfig(cfg, level)` : le `level` du port est
  `ctx.active_ability_level` du porteur (meme convention que ControlEdict/SquigHound, validee live
  bit-exact sur ControlEdict) et non un `passive_ability_level` distinct.
"""
from __future__ import annotations

from typing import Optional

from ....state import State
from ....components import OwnerComponent, UnitComponent
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.summon import Spawn
from .....dsl.base import TargetsSelector
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.selectors.accessors import Target
from .....entities.selectors.geometry import Otherwise
from .....entities.selectors.tiles import AdjacentTiles, CanAddUnit
from .....entities.selectors.units import Tiles
from .....entities.traits.unit_trait import UnitTrait
from .....entities.triggers import HasTrait, is_object_or_steppable
from ..base import TriggeredAbility, TriggerEvent

BARBED_OVIPOSITOR_ABILITY = "BarbedOvipositor"
_ON_UNIT_DEATH = int(EventTriggerType.UnitDeath)             # 0 — 3e event de `KillUnitOperation$$Execute`

# Les DEUX conjoints de TRAIT de `BarbedOvipositorAbility$$CreateTrigger`, portes par les NOEUDS DSL
# du foyer `entities/triggers.py` -- surtout pas une n-ieme recopie du couple de traits (le vice que
# ce residu ferme : `IsObjectOrSteppable` a HUIT call-sites natifs, et deux recopies manuelles
# avaient DIVERGE). Ils lisent tous deux `ctx.has_trait`, donc le MEME substrat
# (`entity_trait_names`, repli gameconfig #226) -- cf. << SUBSTRAT DE TRAITS >> en tete de module.
_IS_OBJECT_OR_STEPPABLE = is_object_or_steppable(Target())   # NOT IsObjectOrSteppable(sel@+0x60)
_HAS_TRAIT_MECHANICAL = HasTrait(Target(), int(UnitTrait.Mechanical))   # NOT HasTrait(sel@+0x60, 5)


class UnitMainTileIds(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLSelectors$$Tiles(units)` -> `IdunBattle.Entities.Selectors.
    UnitsMainTilesSelector$$Select`, **DOMAINE ID**.

    Jumeau id-domain du noeud `Tiles` d'`entities/selectors/units.py`, qui rend des POSITIONS
    `(col, row)` : `CanAddUnit` et la feuille `Spawn` consomment des **ids** de tuile (comme
    `AdjacentTiles`/`SurroundingTiles`). Meme dualite deja assumee par le couple
    `FixedTiles` (positions, pour `MoveUnit`) / `FixedTileIds` (ids, pour `Spawn`). Delegue au
    noeud `Tiles` porte puis convertit via `board.id_at`. board absent -> []."""
    def __init__(self, units: TargetsSelector):
        self.units = units

    def select(self, ctx):
        board = getattr(ctx, "board", None)
        if board is None:
            return []
        out: list = []
        for pos in Tiles(self.units).select(ctx):
            tid = board.id_at(pos[0], pos[1])
            if tid is not None:
                out.append(tid)
        return out


def barbed_ovipositor_spawn_tree() -> Spawn:
    """Arbre de `IdunBattleLogic.Entities.Abilities.Triggered.Loki.BarbedOvipositorAbility$$
    CreateBehaviour` :

        Spawn( owner@0x148,
               PickRandomly(CanAddUnit(Tiles(target@0x178)), 1)
                 .Otherwise(PickRandomly(CanAddUnit(AdjacentTiles(target@0x178)), 1)),
               GetStringConstant(cfg, 0) = "tyranSmnRipperSwarm",
               SpawnUnitOptions.WithStatsFromConfig(cfg, level) )

    Le double `PickRandomly` est FOLDE en `pick_n=1` sur la feuille `Spawn` — equivalence RNG
    PROUVEE (cf. en-tete du module). AUCUN `on_appearance` : le natif ne pose ni `+0x10` (effet)
    ni `+0x18` (on-appearance) sur les options."""
    return Spawn(Otherwise(CanAddUnit(UnitMainTileIds(Target())),      # la tuile du MORT
                           CanAddUnit(AdjacentTiles(Target()))),       # repli : une adjacente libre
                 BARBED_OVIPOSITOR_ABILITY, pick_n=1)


class BarbedOvipositorSummonAbility(TriggeredAbility):
    """`BarbedOvipositorAbility` — quand le Parasite of Mortrex TUE une unite ennemie qui n'est ni
    un objet/steppable ni Mechanical, un Ripper Swarm apparait sur l'hex du mort (a defaut sur une
    tuile libre adjacente). Cf. l'en-tete du module pour l'arbre natif des deux faces."""
    event_id = _ON_UNIT_DEATH

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        # `get_OwnerIsActor` : le porteur est l'ACTEUR de l'evenement de mort = le TUEUR
        # (`unit_death_triggers` construit l'event avec `actor = killer`, `target = dying`).
        if ev.actor_id != self.owner_id:
            return False
        dying = ev.dying_id if ev.dying_id is not None else ev.target_id
        if dying is None or dying == self.owner_id:
            return False
        owner = state.get_entity(self.owner_id)
        victim = state.get_entity(dying)
        if owner is None or victim is None:
            return False
        # `AreEnemies(owner@0x148, target@0x178)`
        ooc = owner.get_component(OwnerComponent)
        voc = victim.get_component(OwnerComponent)
        if ooc is None or voc is None or ooc.team == voc.team:
            return False
        # GARDE DE PORT (pas un conjoint natif) : la victime doit etre une entite-UNITE de l'ECS.
        # INERTE en pratique (les six sites qui creent une entite posent TOUS un `UnitComponent`).
        # Elle etait AUPARAVANT presentee comme une part d'`IsObjectOrSteppable` (« entite sans
        # UnitComponent = objet ») : c'est FAUX, le natif ne teste que des TRAITS.
        vuc = victim.get_component(UnitComponent)
        if vuc is None:
            return False
        # `NOT IsObjectOrSteppable(target@0x178)` puis `NOT HasTrait(target@0x178, 5 = Mechanical)` :
        # DEUX noeuds DSL du MEME arbre, sur le MEME selecteur `sel@+0x60`. Le `matches` est
        # imperatif, donc on materialise ici l'`AbilityEntities` que le natif tient pour tout
        # `CreateTrigger` -- `entities_from_state(state, owner, dying)` pose `Target()` sur la
        # victime. Leur substrat de traits devient `entity_trait_names` (cf. en-tete) : un CADAVRE
        # charge sans `StatsComponent` rendait `set()` en lecture BRUTE, et les deux gates etaient
        # alors AVEUGLES.
        entities = entities_from_state(state, self.owner_id, dying)
        if _IS_OBJECT_OR_STEPPABLE.should_trigger(entities):
            return False
        if _HAS_TRAIT_MECHANICAL.should_trigger(entities):
            return False
        # `NOT TriggeringAbilityIs(TriggeredAbilityType.ItsGonnaBlow = 1080)` : gate INERTE offline
        # (aucun poseur porte, et `On(0)` ne threade pas d'ability) -> cf. residus de l'en-tete.
        return True

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        dying = ev.dying_id if ev.dying_id is not None else ev.target_id
        ectx = ExecutionContext(state=state, rng=state.rng)
        # `target@0x178` = l'unite MOURANTE ; `caster`/`owner` = le porteur (triggered : Owner==Caster).
        barbed_ovipositor_spawn_tree().execute(
            entities_from_state(state, self.owner_id, dying), ectx)
        spawned = [p["unit"] for n, p in ectx.emitted if n == "SpawnUnit"]
        if not spawned:
            return None                                   # aucune tuile posable -> no-op fidele
        return {"ability": BARBED_OVIPOSITOR_ABILITY, "unit": self.owner_id,
                "victim": dying, "spawned": spawned}
