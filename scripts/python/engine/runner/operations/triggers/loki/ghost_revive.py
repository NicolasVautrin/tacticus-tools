"""`GhostRevive` -- le SEUL revive NON-IN-PLACE du binaire (case-66 §8.2 / §8.4, #213 puis #366-r1).

UNE base native (`GhostReviveAbility` + `GhostEffect`), DEUX instanciations, et c'est le SEUL endroit
du sous-systeme revive ou la position change :

| effectType | ability qui pose | `TriggeredAbilityType` | porteur | branche d'`amount` |
|---|---|---|---|---|
| 1186 `TimeFlux_Revive` | `TimeFluxReviveAbility` | 1157 `TimeFlux` | `thousTerminator` (hero, pool) | `Direct(ConfigVar('hp'))` |
| 1284 `EchoesFromTheWarp_Revive` | `EchoesFromTheWarpAbility` | 1219 `EchoesFromTheWarp` | `thousNpc4Terminator` (npc) | `StatAmount(src, Health, Initial)` |

i2 (authoritatif) :
  * `TimeFlux` : « When Toth moves, he leaves a time ghost behind on the hex he moved from. The time
    ghost vanishes if the hex becomes occupied by another unit or if ... »
  * `EchoesFromTheWarp` : « When this unit moves, it leaves a time ghost behind on the hex it moved
    from. The time ghost vanishes if the hex becomes occupied by another unit or if the terrain
    becomes impassable (as with Broken Ice). **The first time this unit dies each battle**, if its
    time ghost is on the battlefield then it revives with **Full Health** at its location. This works
    even if this unit is **Overkilled**. »
⚠ le decompile CORRIGE l'i2 sur un point : la tuile n'est PAS « the hex he moved from », c'est la
tuile ou l'unite se trouvait au **DEBUT DE SON TOUR** (`CurrentTurnStartTile`, `UnitComponent +
0x18c`, ecrit par `IdunBattle.Operations.StartTurnOperation$$Execute`). Les deux coincident tant que
l'unite ne bouge qu'une fois par tour -- ce qui est le cas nominal -- mais c'est bien le champ +0x18c
qui est lu.

IDENTITE DE CLASSE, ETABLIE et non supposee (#366-r1) -- `data/symbols/<build>/frida/classes.tsv` +
lecture du bloc `methodPointers` du PE (technique case-66 §8.3) :
  * `EchoesFromTheWarpAbility` et `TimeFluxReviveAbility` ont TOUTES DEUX pour parent
    `GhostReviveAbility` (lui-meme fils de `BaseTriggeredAbility`) ;
  * chacune ne declare qu'**UNE SEULE methode**, son `.ctor` -- leurs blocs `methodPointers`
    contiennent exactement une entree, encadree par les blocs des classes voisines
    (`ECogSupport_InitAbility` / `EcstaticSlaughterAbility` pour l'une, `TimeFluxAbility` /
    `TimesplinterMantleAbility` pour l'autre). AUCUN override de `CreateTrigger`/`CreateBehaviour` ;
  * les deux ctors appellent le MEME corps de base (que ghidra nomme
    `GenericAddEffectToOwnerAbility..ctor` par ICF -- **ne PAS se fier au nom**, il l'appelait
    `EnvDefenderHealthBuffAbility..ctor` sur le build precedent), avec pour seul argument le
    litteral d'effectType : `0x4a2 = 1186` / `0x504 = 1284` ;
  * `GhostEffect` (parent `BaseEffect`) n'a **AUCUNE sous-classe**, et les DEUX effectTypes sont
    bel et bien construits depuis LA MEME classe : dans
    `IdunBattle.Core.Services.EffectsDatabase$$InitializeEffects`, `0x4a2` et `0x504` mappent sur
    les lambdas `...EffectsDatabase.u003Cu003Ec$$u003CInitializeEffectsu003Eb__14_203` et
    `...b__14_204`, qui allouent depuis **le meme slot `Il2CppClass*` (`DAT_1833ea8f0`, dont ce sont
    les SEULES xrefs) et appellent le meme ctor**. Leurs octets ne different que par le flag d'init
    et par l'immediat passe a `IdunBattle.Core.AbilityOrEffect$$op_Implicit` :
    **`0x485 = 1157 TimeFlux` pour 1186, `0x4c3 = 1219 EchoesFromTheWarp` pour 1284**.
⇒ c'est LA FABRIQUE qui fige le champ `source` que le fork d'amount relira : la bijection
`effectType <-> TriggeredAbilityType poseur` est donc STRUCTURELLE, pas une coincidence de ctors.
Voir le fork ci-dessous pour le discriminant que le NATIF utilise au runtime.

TROIS artefacts natifs DISTINCTS (ne pas les fondre) :

1. `IdunBattleLogic.Entities.Abilities.Triggered.Loki.GhostReviveAbility` -- la POSE du ghost.

       `GhostReviveAbility$$CreateTrigger` =
           <cache factory@0xa0 = OwnerIsActor> & On(0x1f = PreUnitMove, 1) & OwnerIsCaster

       `GhostReviveAbility$$CreateBehaviour` =
           tile = CurrentTurnStartTile(caster@0x160)
           cond = AmountIsEqual(CurrentTurnStartTile(caster@0x160), Direct(0))
                | HasBeenRevivedByAbility(caster@0x160, AbilityOrEffect(this.effectType@0x60))
                | NOT(OwnerIsCaster)
                | TileHasTriggeredAbility(tile, 0x1d = 29 = BrokenIce)
           If( cond, Nothing(),
               AddEffect(this.effectType@0x60, AbilityStateReference,
                         source = caster@0x160, targets = tile, options = null) )

   `AddEffect` est ici la surcharge `(effectType, abilityState, source, targets, options)` (5 args) :
   **source = le porteur, targets = la TUILE**. L'effet est donc PORTE PAR LA TUILE.

2. `IdunBattle.Entities.Effects.Loki.GhostEffect` -- l'effet porte par la tuile.

       `GhostEffect$$CreateTargetTrigger` =
           OnPreDeath(ignoreOverkill = 1) & AreEqual(EffectSource(self@0x150), target@0x178)
       -> **even if Overkilled**, et seul le POSEUR du ghost peut le declencher.

       `GhostEffect$$CreateTargetTriggerBehaviour` =
           src    = EffectSource(Get(effect))
           cond   = NOT(IsAlive(src)) & NOT(HasFlag(src, 6 = Dead))
                    & NOT(HasBeenRevivedByAbility(src, AbilityOrEffect(effectType@0x10)))
           amount = <si effect.source@0x14 vaut 0x485 = 1157 TriggeredAbilityType.TimeFlux>
                    ? Direct(GetVariableForLevel(config@0x60, 0x1d = 'hp', abilityState))
                    : StatAmount(src, Health = 5, StatPart = 3 = Initial)
           If( cond, Revive(src, src, amount, healType = 2,
                            Nullable(AbilityOrEffect(effectType@0x10)),
                            **tiles = Owner@0x148**, priority = 0)
                     + BaseEffect.GetRemoveEffectBehaviour(),
               null )

   ⚠ **LE FORK N'EST PAS UN NOEUD** : il est resolu A LA CONSTRUCTION de l'arbre. Deux
   `Nullable.get_HasValue` en cascade deballent le champ `source` de l'effet
   (`Nullable<AbilityOrEffect>` @+0x14..0x2c), puis `if (source == 0x485)` -> `Direct('hp')`,
   `else` -> `StatAmount`. Le `else` couvre AUSSI le cas `Nullable` VIDE -- sans consommateur : les
   deux `AddEffect` du binaire passent un `AbilityStateReference`.
   **DISCRIMINANT RUNTIME des deux ids** : le natif compare le `TriggeredAbilityType` de l'ability
   QUI A POSE l'effet (1157 vs 1219), pas l'effectType. Les deux etant en bijection (un seul ctor
   par sous-classe : 1157 pose 1186, 1219 pose 1284), le port resout le fork A L'ENREGISTREMENT
   (`EFFECT_TRIGGERS[1186]` vs `EFFECT_TRIGGERS[1284]`) -- aucun test de source au runtime, comme
   le natif qui n'evalue jamais la branche non prise.

   ⚠ **`StatPart = 3` est `Initial`, PAS `Maximum` (= 2)** -- `IdunBattle.Entities.Enum.StatPart` :
   `0=Current,1=CurrentPct,2=Maximum,3=Initial,4=Missing,...`, et
   `IdunBattle.Entities.Components.FillUpStatComponent$$GetStatPart` le confirme au corps
   (`case 3: return *(this+0x10)` = le champ base, vs `case 2: get_CurrentMaximumValue()` = base +
   modification clampee). La fiche case-66 §8.4 ecrivait « max = 3 » : c'etait un mislabel.
   Le meme `Initial` est relu par le clamp
   `IdunBattle.Core.Services.BattleQuery$$GetMaximumReviveHealth` =
   `Min(GetStat(unit, Health, Initial), <cap config slot 0x12>(CurrentMaximum, ...))`, appele par
   `IdunBattle.Entities.Behaviours.ReviveBehaviour$$GetMaxReviveAmount` -> le montant final vaut
   `Min(Health_Initial, Health_Initial, cap)` = **PV pleins**, exactement le « Full Health » de l'i2.

       `GhostEffect$$CreateHandleTriggerAbilitiesInternal` = ArraySet de CINQ retraits
       (`GetRemoveEffectBehaviour` a chaque fois) -- la « condition de disparition » de l'i2 :
         1. On(0x1f = PreUnitMove, 1) & AreEqual(caster@0x160, EffectSource)
         2. On(0x32 = UnitAdded, 1) & NOT AreEqual(caster, EffectSource)
            & Contains(TargetTiles@0x190, Owner@0x148) & NOT HasTrait(caster, 0x1b = Steppable)
         3. On(0x24 = UnitPositionChanged_1, 1) & NOT AreEqual(caster, EffectSource)
            & Contains(TargetTiles@0x190, Owner@0x148)
         4. OnDeath(1) & AreEqual(EffectSource, target@0x178) & NOT IsEffectActive(self@0x150)
         5. On(0x25 = UnitRemoved, 1) & AreEqual(EffectSource, target@0x178)

3. `IdunBattle.Operations.ReviveUnitOperation$$SetRevivePosition` -- le mutateur de position
   (mirror dans `operations/revive.py::_set_revive_position`), garde par
   `if (!revivePosition.HasValue) return;`.

DOCTRINE #149 : les `CreateTrigger` sont COLLAPSES dans `matches()` (idiome de tous les
trigger-ports) ; les `CreateBehaviour`/`CreateTargetTriggerBehaviour` sont de VRAIS arbres DSL
(`If`/`Nothing` + feuilles `AddEffect` / `Revive` / `RemoveEffect`), et la frontiere reste le
`.execute` des feuilles (`AddEffectOperation`, `post_pending_revive` -> `ReviveUnitOperation`).
"""
from __future__ import annotations

from typing import Optional

from ....state import State
from ....components import UnitComponent, PositionComponent
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.effect_type import EffectType
from .....entities.formulas import StatAmount
from .....entities.stats import StatType, StatPart
from .....entities.triggered_ability_type import TriggeredAbilityType
from .....entities.traits.unit_trait import UnitTrait, has_trait
from .....entities.selectors.accessors import Target
from .....entities.selectors.tiles import Caster
from ....abilities.behaviours.context import entities_from_state
from ..base import TriggeredAbility, TileEffectTrigger, TriggerEvent, _unit_trait_names
from ..revive_effect import Revive, can_be_revived
from ....components import StatsComponent
from ...effects import AddEffectOperation

# --- les DEUX litteraux d'effectType passes au ctor de `GhostReviveAbility` ---------------------
TIME_FLUX_GHOST_EFFECT = int(EffectType.TimeFlux_Revive)              # 0x4a2 = 1186
ECHOES_GHOST_EFFECT = int(EffectType.EchoesFromTheWarp_Revive)        # 0x504 = 1284
# `TriggeredAbilityType` des deux abilities poseuses -- c'est 1157 que le fork d'amount compare.
TIME_FLUX_ABILITY = int(TriggeredAbilityType.TimeFlux)                # 0x485 = 1157
ECHOES_ABILITY = int(TriggeredAbilityType.EchoesFromTheWarp)          # 0x4c3 = 1219

GHOST_HEAL_TYPE = 2                           # 4e argument du `Revive` -- `IsAffectedByHealType` ne
                                              # filtre NI Heal NI Repair (meme litteral que PhoenixGem).
GHOST_REVIVE_PRIORITY = 0                     # 8e argument (`IsPreferredRevive`)
# `TileHasTriggeredAbility(tile, 0x1d = 29)` -- `TriggeredAbilityType.BrokenIce` (dump d'enums du
# build). Une tuile de glace BRISEE ne peut pas porter de ghost. Aucun board du pool ne porte cette
# tile-ability -> gate INERTE en pratique, porte quand meme (mirror, et il ne coute rien).
BROKEN_ICE_TILE_ABILITY = 29
# `NOT HasTrait(caster, 0x1b)` du retrait n°2 : `UnitTrait.Steppable` -- un decoy / une spore-mine
# posee sur la tuile du ghost ne le dissipe PAS.
GHOST_UNIT_ADDED_EXCLUDED_TRAIT = UnitTrait.Steppable


def _tile_of(state: State, unit_id: int) -> Optional[int]:
    """Id d'entite-tuile (`boardGraph`) ou se tient `unit_id` -- mirror
    `IdunBattle.Entities.EntityExtensions$$GetMainTile(unit).Id`. None sans board / sans position."""
    board = getattr(state, "board", None)
    e = state.get_entity(unit_id)
    pc = e.get_component(PositionComponent) if e is not None else None
    if board is None or pc is None:
        return None
    return board.id_at(pc.col, pc.row)


def _has_been_revived_by_ability(state: State, unit_id: int, source: int) -> bool:
    """`IdunBattleLogic.Entities.DSLTriggers$$HasBeenRevivedByAbility(unit, source)` ->
    `Idun.Source.IdunBattle.Logic.Entities.Triggers.HasBeenRevivedAbilityTrigger$$ShouldTrigger` :
    resout son selecteur, prend l'`ActorStatisticsComponent` de l'entite et rend
    `component@+0xe0 .Contains(source)`. Le set est alimente par
    `IdunBattle.Operations.ReviveUnitOperation$$Execute` (l'`AbilityOrEffect` de la `ReviveData`) et
    n'est JAMAIS remis a zero -> gate « une seule fois par BATAILLE » (le « the first time this unit
    dies **each battle** » de l'i2 d'`EchoesFromTheWarp`). Port : le set
    `UnitComponent.revived_by_abilities` (meme residu structurel que `last_hit_damage_taken_*`)."""
    e = state.get_entity(unit_id)
    uc = e.get_component(UnitComponent) if e is not None else None
    return uc is not None and int(source) in uc.revived_by_abilities


def _tile_has_triggered_ability(state: State, tile_id: Optional[int], ability: int) -> bool:
    """`IdunBattleLogic.Entities.DSLTriggers$$TileHasTriggeredAbility(tile, ability)` ->
    `IdunBattle.Entities.Triggers.TileHasTriggeredAbilityTrigger$$ShouldTrigger` : resout le
    selecteur de tuile (slot 0xc = une entite) puis
    `IdunBattle.Entities.UnitExtensions$$HasTriggeredAbility(tile, abilityType)`.

    Cote port, les tile-abilities sont portees par le `tileDefId` du terrain (cf.
    `triggers/tiles.py`, ou `TilesWithTriggeredAbility(0x39 = DryBushFireSpread)` <=> `tileDefId ==
    'DryBush'`). `BrokenIce` (29) n'a AUCUN tile-def hote dans les boards du pool -> False.
    RESIDU NOMME : la table `TriggeredAbilityType -> tileDefId` n'existe pas cote port (elle vit dans
    les Unity assets de tuile, hors gameconfig) ; ce gate est donc structurellement present mais
    toujours faux. Il ne peut REFUSER un ghost a tort que sur un board a glace brisee."""
    return False


def _effect_source(state: State, tile_id: int, effect_type: int) -> Optional[int]:
    """`EffectSource(self@0x150)` -- l'unite qui a POSE le ghost (`EffectComponent.SourceUnit @+0x10`).
    None si la tuile ne porte plus l'effet."""
    eff = getattr(state, "effects", None)
    if eff is None:
        return None
    for e in (eff.by_unit.get(int(tile_id)) or []):
        if e.effect_type == int(effect_type) and not e.consumed:
            return None if e.source is None else int(e.source)
    return None


def _ghost_effect(state: State, tile_id: int, effect_type: int):
    """L'instance de `GhostEffect` NON CONSOMMEE portee par `tile_id`, ou None.

    ⚠ « non consommee » n'est PAS « active » : ce filtre est celui du COLLECTEUR
    (`collect_effect_triggers` skippe `e.consumed`), pas le gate `EffectComponent.IsActive @+0x5c`.
    La docstring disait « ACTIVE » alors que le code ne lisait pas le flag -- c'est cette confusion
    qui a laisse la resurrection sans gate (#421). Le flag se lit par `_ghost_is_active`."""
    eff = getattr(state, "effects", None)
    if eff is None:
        return None
    for e in (eff.by_unit.get(int(tile_id)) or []):
        if e.effect_type == int(effect_type) and not e.consumed:
            return e
    return None


def _ghost_is_active(state: State, tile_id: int, effect_type: int) -> bool:
    """Le flag `EffectComponent.IsActive @+0x5c` de l'instance de ghost portee par la tuile --
    mirror du gate que `IdunBattle.Operations.EvaluateTriggerOperation$$EvaluateEffectTriggerTargets`
    applique PAR CIBLE, sur le composant RE-FETCH depuis l'entite-effet, AVANT `ShouldTrigger`.

    Meme forme que `RitesOfMorkaiReviveTrigger._instance_is_active` (1502) et
    `ReanimationBeamReviveTrigger` (1547). Aucune instance -> True : degradation PERMISSIVE (on ne
    fabrique pas un refus ; si l'effet etait reellement absent, le collecteur n'aurait instancie
    aucun trigger)."""
    e = _ghost_effect(state, tile_id, effect_type)
    return True if e is None else bool(e.active)


def _remove_ghost(state: State, tile_id: int, effect_type: int) -> bool:
    """`BaseEffect.GetRemoveEffectBehaviour()` -- retire le ghost de la tuile. Le port marque
    l'instance `consumed=True` (MEME mecanique que `RemoveReviveEffect`, cf. `revive_effect.py`) :
    `collect_effect_triggers` skippe les effets consommes -> plus aucun trigger du ghost ne fire."""
    e = _ghost_effect(state, tile_id, effect_type)
    if e is None:
        return False
    e.consumed = True
    return True


def _passive_scaling(state: State, owner_id: int) -> tuple:
    """`(passive_ability_level, ability_variables_multiplier)` du porteur -- `TimeFlux` comme
    `EchoesFromTheWarp` sont des PASSIFS (meme resolution que `time_flux.py::_passive_scaling`)."""
    e = state.get_entity(owner_id)
    sc = e.get_component(StatsComponent) if e is not None else None
    ctx = getattr(sc, "ctx", None)
    if ctx is None:
        return None, 100
    return (getattr(ctx, "passive_ability_level", None),
            int(getattr(ctx, "ability_variables_multiplier", 100) or 100))


# ═══ 1. la POSE du ghost -- `GhostReviveAbility` et ses DEUX sous-classes ════════════════════════

class GhostReviveAbility(TriggeredAbility):
    """`IdunBattleLogic.Entities.Abilities.Triggered.Loki.GhostReviveAbility` -- BASE ABSTRAITE de la
    pose du time-ghost. Le natif la parametre par l'`effectType` passe au ctor ; le port le declare
    en attribut de classe (`GHOST_EFFECT_TYPE`), exactement comme les sous-classes natives ne
    portent QUE ce litteral (aucune n'override `CreateTrigger`/`CreateBehaviour`, verifie au bloc
    `methodPointers` -- cf. l'en-tete du module).

    `CreateTrigger` = `<factory@0xa0 = OwnerIsActor> & On(0x1f = PreUnitMove, 1) & OwnerIsCaster` :
      * `OwnerIsActor` (le MEME cache @0xa0 que `TimeFluxAbility`/`LivingMetalRepairAbility`, ou il
        est PROUVE live par `probe_203`) + `OwnerIsCaster` : sur `On(PreUnitMove)` le natif construit
        `AbilityEntities.ctor(mover, mover, mover)` -> actor == caster == target == le mover, donc
        les deux predicats se reduisent au MEME test : « c'est MOI qui bouge »."""
    event_id = int(EventTriggerType.PreUnitMove)            # On(0x1f = 31)
    GHOST_EFFECT_TYPE: int = 0                              # litteral du ctor (1186 / 1284)
    ABILITY_ID: str = ""                                    # cle gameconfig (scaling du passif)
    EFFECT_NAME: str = ""                                   # nom de l'EffectType pose

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        # `OwnerIsActor & OwnerIsCaster` -- collapse : le mover EST l'acteur ET le caster de l'event.
        if ev.actor_id is None or int(ev.actor_id) != int(self.owner_id):
            return False
        e = state.get_entity(self.owner_id)
        uc = e.get_component(UnitComponent) if e is not None else None
        return uc is not None and uc.alive

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        e = state.get_entity(self.owner_id)
        uc = e.get_component(UnitComponent) if e is not None else None
        if uc is None:
            return None
        # `tile = CurrentTurnStartTile(caster@0x160)` -- `CurrentTurnStartTileSelector$$Select` lit
        # `UnitComponent + 0x18c` et rend `[]` quand il vaut 0.
        tile = uc.current_turn_start_tile
        # --- `cond` (les quatre disjonctions, dans l'ordre du decompile) --------------------------
        # 1. `AmountIsEqual(CurrentTurnStartTile(caster), Direct(0))` : aucune tuile de debut de tour
        #    enregistree (le champ vaut 0) -> pas de ghost.
        no_start_tile = tile is None
        # 2. `HasBeenRevivedByAbility(caster, AbilityOrEffect(effectType@0x60))` : le porteur a DEJA
        #    ete ressuscite par CE ghost dans cette bataille -> il n'en repose plus.
        already = _has_been_revived_by_ability(state, self.owner_id, self.GHOST_EFFECT_TYPE)
        # 3. `NOT(OwnerIsCaster)` : deja tranche par `matches` (event mover==owner) -> toujours faux ici.
        # 4. `TileHasTriggeredAbility(tile, BrokenIce=29)` : pas de ghost sur une glace brisee.
        broken_ice = _tile_has_triggered_ability(state, tile, BROKEN_ICE_TILE_ABILITY)
        if no_start_tile or already or broken_ice:
            return None                                  # branche `Nothing()` du `If`
        # --- branche `AddEffect(effectType, AbilityStateReference, source=caster, targets=tile)` ---
        # `AddEffectOperation` = la feuille imperative (frontiere #149). L'`AbilityStateReference` du
        # natif = l'etat d'ability du PORTEUR (les deux abilities sont des PASSIFS) -> on transmet son
        # `passive_ability_level` + `ability_variables_multiplier`, ce que relira le
        # `GetVariableForLevel(config, 'hp')` du behaviour de l'effet (branche TimeFlux uniquement --
        # la branche `StatAmount` d'EchoesFromTheWarp ne lit AUCUNE variable de config, et le
        # gameconfig d'`EchoesFromTheWarp` porte d'ailleurs `variables: {}`).
        lvl, mult = _passive_scaling(state, self.owner_id)
        eff = AddEffectOperation.execute(state, source=int(self.owner_id), target=int(tile),
                                         effect_type=self.GHOST_EFFECT_TYPE, name=self.EFFECT_NAME,
                                         ability_level=lvl, multiplier_pct=mult)
        if eff is None:
            return None
        return {"ability": self.ABILITY_ID, "owner": int(self.owner_id), "ghost_tile": int(tile),
                "effect_type": self.GHOST_EFFECT_TYPE, "on_event": int(ev.event_id)}


class TimeFluxReviveAbility(GhostReviveAbility):
    """`...TimeFluxReviveAbility$$.ctor` = `GhostReviveAbility..ctor(this, 0x4a2 = 1186)`.

    Rail : `ABILITY_TRIGGERS["TimeFlux"]` (aux cotes de `TimeFluxRegenAbility`) -- le natif derive
    DEUX triggered-abilities du MEME passiveAbility `TimeFlux` de `thousTerminator`, et ce registre
    est precisement le mirror de cette derivation."""
    GHOST_EFFECT_TYPE = TIME_FLUX_GHOST_EFFECT
    ABILITY_ID = "TimeFlux"
    EFFECT_NAME = "TimeFlux_Revive"
    TRIGGERED_ABILITY_ID = TIME_FLUX_ABILITY                # `BaseTriggeredAbility$$Execute` inscrit cet id


class EchoesFromTheWarpAbility(GhostReviveAbility):
    """`...EchoesFromTheWarpAbility$$.ctor` = `GhostReviveAbility..ctor(this, 0x504 = 1284)`.

    Rail : `ABILITY_TRIGGERS["EchoesFromTheWarp"]` -- passiveAbility UNIQUE de
    `thousNpc4Terminator` (« Scarab Occult Terminator », ThousandSons), le SEUL porteur du parc.
    Ce porteur est un **npc** : il n'entre pas dans `--list-pool` et `catalog_inject` ne peut pas
    l'y faire entrer (`IdunMetaLogic.Formulas.StatsFormula$$StatsUsingProgressionIndexFor` leve un
    `KeyNotFoundException` sur un lookup PAR UNITID qui ne couvre que le bucket `lineup`, cf.
    case-66 §8.4). La confrontation live passe donc par la GREFFE de l'ability sur une unite DU POOL
    (`case-92` §5bis) : rien de cette ability ne lit les traits ni l'arme du caster, et la seule
    stat lue (`Health` part `Initial`) est celle du GREFFON -- ce qui en fait un discriminant, pas un
    confond. Probe : `probe_366r1_echoes_revive.py`."""
    GHOST_EFFECT_TYPE = ECHOES_GHOST_EFFECT
    ABILITY_ID = "EchoesFromTheWarp"
    EFFECT_NAME = "EchoesFromTheWarp_Revive"
    TRIGGERED_ABILITY_ID = ECHOES_ABILITY


# ═══ 2. la RESURRECTION -- `GhostEffect$$CreateTargetTrigger(Behaviour)` ═════════════════════════

class GhostEffectRevive(TileEffectTrigger):
    """`GhostEffect$$CreateTargetTrigger` + `$$CreateTargetTriggerBehaviour` -- la RESURRECTION.

    Porteur = la TUILE (`TileEffectTrigger` : `owner_is_tile` fait sauter les gates unit/alive du
    dispatch, `owner_id` est un id de `boardGraph`). C'est le seul revive du binaire dont le
    `DSLFactory.Revive` recoit un `targetsTile` non nul (`Owner@0x148` = cette tuile), donc le seul
    qui ecrit une position dans la `ReviveData`.

    BASE des deux instanciations : `effect_type` (attribut de classe) porte le litteral, et
    `amount_node()` porte le FORK -- resolu ici a l'enregistrement, comme le natif le resout a la
    construction de l'arbre."""
    event_ids = (int(EventTriggerType.PreUnitDeath),)       # OnPreDeath -> OnDeathEvent(1)
    event_id = int(EventTriggerType.PreUnitDeath)
    ABILITY_ID: str = ""

    def amount_node(self, state: State, dying: int):
        """4e argument de `DSLFactory.Revive`. Rend `(amount_node, hp_var_level, mult)` ; le noeud
        prime s'il est non nul. Surcharge par instanciation -- le natif n'evalue JAMAIS la branche
        non prise."""
        raise NotImplementedError

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        # --- gate `EffectComponent.IsActive @+0x5c` (rail TARGETS) -- #421 ------------------------
        # `GhostEffect$$CreateTargetTrigger` place CE trigger sur le rail TARGETS, donc
        # `IdunBattle.Operations.EvaluateTriggerOperation$$EvaluateEffectTriggerTargets` le gate sur
        # le flag ; les CINQ retraits, eux, viennent de `$$CreateHandleTriggerAbilitiesInternal`
        # (rail ArraySet, `...$$EvaluateEffectTriggerEffectAbilities`, AUCUN gate).
        #
        # C'est ce qui rend les deux branches EXCLUSIVES cote natif sur le meme evenement : ghost
        # INACTIF + poseur qui meurt -> seul `GhostRemoveOnSourceDeathInactive` (`NOT IsEffectActive`)
        # mord. Sans ce gate le port faisait LES DEUX -- il ressuscitait ET retirait. Le port
        # modelise deja cet etat (le retrait n°4 lit `not e.active`), donc l'incoherence etait
        # INTERNE, pas theorique. Cf. `docs/rl/case-229-effect-triggers-active-inventory.md`.
        if not _ghost_is_active(state, self.owner_id, self.effect_type):
            return False
        dying = ev.dying_id
        if dying is None or state.get_entity(dying) is None:
            return False
        # `OnPreDeath(ignoreOverkill = 1)` -> AUCUN gate overkill (« even if Overkilled ») : on ne
        # teste DELIBEREMENT PAS `ev.overkill`.
        # `AreEqual(EffectSource(self@0x150), target@0x178)` : seul le POSEUR du ghost le declenche.
        src = _effect_source(state, self.owner_id, self.effect_type)
        if src is None or int(src) != int(dying):
            return False
        # --- `cond` du behaviour (evaluee ici : c'est un `If`, pas un second trigger) -------------
        # `NOT(IsAlive(src))` -- l'unite doit etre morte. Sur le vecteur `On(1)` le port a deja pose
        # `alive=False` (fire-on-death), donc ce gate est satisfait ; il reste porte pour le cas ou
        # ce trigger serait atteint hors sequence de mort.
        e = state.get_entity(dying)
        uc = e.get_component(UnitComponent) if e is not None else None
        if uc is not None and uc.alive:
            return False
        # `NOT(HasFlag(src, 6 = Dead))` -- le flag `UnitFlag.Dead` n'est pose qu'APRES la garde de
        # `KillUnitOperation` (donc jamais a l'instant de l'`On(1)`) : mirror non modelise, gate
        # toujours vrai ici, exactement comme le flag 0xd de `can_be_revived` (case-66 §5).
        # `NOT(HasBeenRevivedByAbility(src, AbilityOrEffect(effectType@0x10)))`
        if _has_been_revived_by_ability(state, dying, self.effect_type):
            return False
        # `DSLFactory.Revive` -> `ReviveBehaviour$$Execute` gate `BattleQuery.CanBeRevived(target,
        # healType)` avant d'ecrire la `ReviveData` : meme mirror que la base `ReviveEffect`.
        entities = entities_from_state(state, self.owner_id, dying)
        tgt = entities.target
        if tgt is None:
            return False
        return can_be_revived(entities, tgt, dying, state, heal_type=GHOST_HEAL_TYPE)

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        dying = ev.dying_id
        entities = entities_from_state(state, self.owner_id, dying)
        ectx = ExecutionContext(state=state, rng=state.rng)
        eff = _ghost_effect(state, self.owner_id, self.effect_type)
        lvl = None if eff is None else (eff.active_ability_level
                                        if eff.active_ability_level is not None else eff.ability_level)
        mult = 100 if eff is None else int(eff.ability_variables_multiplier or 100)
        # `tiles_sel = Caster()` = `Owner@0x148` : dans le contexte d'un effet-trigger le port pose
        # `caster = owner` (collapse documente de `entities_from_state`), et l'owner est ICI la TUILE.
        Revive(Target(), self.ABILITY_ID, "hp", lvl, mult,
               heal_type=GHOST_HEAL_TYPE, source_id=self.effect_type,
               priority=GHOST_REVIVE_PRIORITY, tiles_sel=Caster(),
               amount_node=self.amount_node(state, dying)).execute(entities, ectx)
        # 2e volet de l'`op_Addition` : `BaseEffect.GetRemoveEffectBehaviour()` -- le ghost est
        # consomme par la resurrection qu'il vient de declencher.
        removed = _remove_ghost(state, self.owner_id, self.effect_type)
        revives = [p for n, p in ectx.emitted if n == "Revive" and p.get("revived")]
        return {"ability": self.ABILITY_ID, "ghost_tile": int(self.owner_id), "dying": dying,
                "revives": revives, "ghost_removed": removed}


class TimeFluxGhostEffectRevive(GhostEffectRevive):
    """Instanciation `TimeFlux_Revive` (1186) -- branche `Direct(GetVariableForLevel(config,
    0x1d='hp', abilityState))` du fork (source de l'effet == `0x485 = 1157`).
    Confirmation croisee : `TimeFlux.hp` (2401 @ L65) existe au gameconfig et n'est lue par AUCUN
    autre arbre (`time_flux.py` lit `hpToHeal`/`maxHpToHeal`)."""
    effect_type = TIME_FLUX_GHOST_EFFECT
    ABILITY_ID = "TimeFlux"

    def amount_node(self, state: State, dying: int):
        return None                      # -> la feuille `Revive` calcule `ability_var('TimeFlux','hp')`


class EchoesFromTheWarpGhostEffectRevive(GhostEffectRevive):
    """Instanciation `EchoesFromTheWarp_Revive` (1284) -- branche `StatAmount(src, Health = 5,
    StatPart = 3 = Initial)` du fork (source de l'effet != `0x485`).

    C'est le « revives with **Full Health** » de l'i2 : le montant ne lit AUCUNE variable de config
    (le gameconfig d'`EchoesFromTheWarp` a `variables: {}`), seulement la PV INITIALE du revenant.

    `src` = `EffectSource(Get(effect))`. Le port le collapse en `Target()` : le
    `CreateTargetTrigger` a deja impose `AreEqual(EffectSource(self@0x150), target@0x178)`, donc les
    deux designent la MEME entite -- meme collapse que la cible du `Revive` juste au-dessus.

    RESIDU NOMME (fidelite du montant) : le port n'a PAS de champ `hp_initial`
    (`HealthComponent` = `hp`/`hp_max`), donc `FillUpStatComponent.get_stat_part` rend le MEME
    `maximum` pour les parts 2 (`Maximum`) et 3 (`Initial`). Les deux ne divergent cote natif que
    si une modification de MAX-PV est active (`FillUpStatComponent$$ModifyMax`/`MaxReduce`, ou une
    stat-modification de `Health`) : `Maximum = base + modification clampee`, `Initial = base`.
    Aucun effet modifiant le max-PV n'est porte a ce jour."""
    effect_type = ECHOES_GHOST_EFFECT
    ABILITY_ID = "EchoesFromTheWarp"

    def amount_node(self, state: State, dying: int):
        return StatAmount(Target(), int(StatType.HEALTH), int(StatPart.INITIAL))


# ═══ 3. les CINQ retraits -- `GhostEffect$$CreateHandleTriggerAbilitiesInternal` ═════════════════

class _GhostRemoval(TileEffectTrigger):
    """Base des CINQ `Triggered(<cond>, GetRemoveEffectBehaviour())` de
    `GhostEffect$$CreateHandleTriggerAbilitiesInternal`. Behaviour commun : retirer le ghost."""
    ABILITY_ID: str = ""

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        raise NotImplementedError

    def _source(self, state: State) -> Optional[int]:
        return _effect_source(state, self.owner_id, self.effect_type)

    def _actor_is_on_my_tile(self, state: State, unit_id) -> bool:
        """`Contains(TargetTiles@0x190, Owner@0x148)` -- les tuiles-cible de l'evenement contiennent
        la tuile porteuse du ghost. Sur `On(0x24)`/`On(0x32 = UnitAdded)` ces tuiles sont celles ou l'unite vient
        d'arriver / d'apparaitre : le port les derive de sa `PositionComponent` (deja ecrite quand le
        natif emet ces events)."""
        if unit_id is None:
            return False
        return _tile_of(state, int(unit_id)) == int(self.owner_id)

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        if not _remove_ghost(state, self.owner_id, self.effect_type):
            return None
        return {"ability": self.ABILITY_ID, "ghost_tile": int(self.owner_id),
                "ghost_removed": True, "on_event": int(ev.event_id)}


class GhostRemoveOnSourceMoves(_GhostRemoval):
    """Retrait n°1 : `On(0x1f = PreUnitMove, 1) & AreEqual(caster@0x160, EffectSource)` -- le poseur
    du ghost REBOUGE, l'ancien ghost part.

    ⚠ ORDRE avec la POSE (`GhostReviveAbility`, meme event) : `evaluate_trigger_operation` MATERIALISE
    le registre une fois en tete de dispatch (mirror du snapshot + `Queue.Clear` natif) -> le ghost
    POSE pendant ce dispatch n'y figure pas et ne peut donc pas s'auto-retirer, quel que soit l'ordre
    des deux entrees. Le cas de bord subsistant est le double-move DANS LE MEME TOUR sur la MEME tuile
    de debut de tour : `AddEffectOperation` no-ope (effet deja present) puis ce retrait le supprime.
    Residu documente -- une unite ne bouge qu'une fois par tour (flag `UnitFlag.Moved`)."""
    event_ids = (int(EventTriggerType.PreUnitMove),)
    event_id = int(EventTriggerType.PreUnitMove)

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        src = self._source(state)
        return src is not None and ev.actor_id is not None and int(ev.actor_id) == int(src)


class GhostRemoveOnUnitAdded(_GhostRemoval):
    """Retrait n°2 : `On(0x32 = UnitAdded, 1) & NOT AreEqual(caster, EffectSource)
    & Contains(TargetTiles@0x190, Owner@0x148) & NOT HasTrait(caster, 0x1b = Steppable)` -- une AUTRE
    unite (non-Steppable) APPARAIT sur la tuile du ghost."""
    event_ids = (int(EventTriggerType.UnitAdded),)
    event_id = int(EventTriggerType.UnitAdded)

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        actor = ev.actor_id
        src = self._source(state)
        if actor is None or (src is not None and int(actor) == int(src)):
            return False                                   # `NOT AreEqual(caster, EffectSource)`
        if not self._actor_is_on_my_tile(state, actor):
            return False
        # `NOT HasTrait(caster, Steppable)` : un decoy / une spore-mine ne dissipe pas le ghost.
        return not has_trait(_unit_trait_names(state, int(actor)), GHOST_UNIT_ADDED_EXCLUDED_TRAIT)


class GhostRemoveOnUnitEnters(_GhostRemoval):
    """Retrait n°3 : `On(0x24 = UnitPositionChanged_1, 1) & NOT AreEqual(caster, EffectSource)
    & Contains(TargetTiles@0x190, Owner@0x148)` -- une AUTRE unite ARRIVE sur la tuile du ghost.
    C'est le « the time ghost vanishes if the hex becomes occupied by another unit » de l'i2.
    Noter l'ABSENCE du gate `Steppable` ici (contraste avec le retrait n°2) : lu au decompile."""
    event_ids = (int(EventTriggerType.UnitPositionChanged_1),)
    event_id = int(EventTriggerType.UnitPositionChanged_1)

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        actor = ev.actor_id
        src = self._source(state)
        if actor is None or (src is not None and int(actor) == int(src)):
            return False
        return self._actor_is_on_my_tile(state, actor)


class GhostRemoveOnSourceDeathInactive(_GhostRemoval):
    """Retrait n°4 : `OnDeath(1) & AreEqual(EffectSource, target@0x178)
    & NOT IsEffectActive(self@0x150)` -- le poseur meurt ALORS QUE l'effet est INACTIF.

    `IdunBattleLogic.Entities.DSLTriggers$$IsEffectActive` lit le champ `Active` de l'`EffectComponent`
    (@+0x5c), que `ActivateEffectBehaviour` bascule. Le port materialise cet etat par
    `BaseEffect.active` ; un ghost fraichement pose est ACTIF -> ce retrait ne fire pas, et c'est
    `GhostEffectRevive` (le MEME event `On(1)`) qui prend la main. Le retrait n°4 est donc le
    complement exact de la resurrection : « le poseur meurt mais le ghost ne peut pas agir ».

    NB : `OnDeath(1)` = `OnDeathEvent(eventType = 0 = UnitDeath, ignoreOverkill = 1)`, un event
    NATIF DISTINCT du `OnPreDeath(1)` de la resurrection -- d'ou le vecteur `unit_death_triggers`."""
    event_ids = (int(EventTriggerType.UnitDeath),)
    event_id = int(EventTriggerType.UnitDeath)

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        dying = ev.dying_id
        src = self._source(state)
        if dying is None or src is None or int(src) != int(dying):
            return False
        eff = _ghost_effect(state, self.owner_id, self.effect_type)
        return eff is not None and not bool(getattr(eff, "active", True))   # `NOT IsEffectActive`


class GhostRemoveOnSourceRemoved(_GhostRemoval):
    """Retrait n°5 : `On(0x25 = UnitRemoved, 1) & AreEqual(EffectSource, target@0x178)` -- le poseur
    QUITTE le plateau.

    EMETTEUR (#227) : `IdunBattle.Operations.RemoveUnitOperation$$Execute`, portee dans
    `runner/operations/remove_unit.py`, publie `On(0x25)` avec `(a = b = c = l'unite retiree)` --
    APRES la pose du flag `Removed (0x1a)` et le retrait des tuiles, mais AVANT la consommation des
    effets portes. C'est cet ordre qui rend ce retrait-ci observable : le ghost est porte par la
    TUILE (source = le poseur), donc `RemoveEffects(poseur)` ne le toucherait pas.

    ATTEIGNABILITE, mesuree : aucune des cinq abilities natives qui appellent
    `IdunBattleLogic.Entities.DSLBehaviors$$RemoveUnit` ne retire le poseur d'un ghost -- MV71 retire
    un drone, `AggressiveOnslaught_Unsummon` les `Children(Owner)`, `HunterOfSouls` son PROPRE
    porteur, `NoHidingFromTheWatchers` n'a que des porteurs npc/summon, `PriorityReclamation` aucun
    porteur au gameconfig. Ce trigger reste donc INERTE en bataille reelle ; il est exerce par la
    garde en appelant l'Operation directement (ce que `HunterOfSouls` fait sur son porteur)."""
    event_ids = (int(EventTriggerType.UnitRemoved),)
    event_id = int(EventTriggerType.UnitRemoved)

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        src = self._source(state)
        return (src is not None and ev.target_id is not None
                and int(ev.target_id) == int(src))


# --- les DIX classes concretes de retrait (5 par instanciation de `GhostEffect`) -----------------
# Le natif n'a QU'UNE classe `GhostEffect` : ces sous-classes ne portent que l'`effectType` sous
# lequel `EFFECT_TRIGGERS` les enregistre (le port indexe les triggers d'effet PAR effectType).

class TimeFluxGhostRemoveOnSourceMoves(GhostRemoveOnSourceMoves):
    effect_type = TIME_FLUX_GHOST_EFFECT
    ABILITY_ID = "TimeFlux"


class TimeFluxGhostRemoveOnUnitAdded(GhostRemoveOnUnitAdded):
    effect_type = TIME_FLUX_GHOST_EFFECT
    ABILITY_ID = "TimeFlux"


class TimeFluxGhostRemoveOnUnitEnters(GhostRemoveOnUnitEnters):
    effect_type = TIME_FLUX_GHOST_EFFECT
    ABILITY_ID = "TimeFlux"


class TimeFluxGhostRemoveOnSourceDeathInactive(GhostRemoveOnSourceDeathInactive):
    effect_type = TIME_FLUX_GHOST_EFFECT
    ABILITY_ID = "TimeFlux"


class TimeFluxGhostRemoveOnSourceRemoved(GhostRemoveOnSourceRemoved):
    effect_type = TIME_FLUX_GHOST_EFFECT
    ABILITY_ID = "TimeFlux"


class EchoesGhostRemoveOnSourceMoves(GhostRemoveOnSourceMoves):
    effect_type = ECHOES_GHOST_EFFECT
    ABILITY_ID = "EchoesFromTheWarp"


class EchoesGhostRemoveOnUnitAdded(GhostRemoveOnUnitAdded):
    effect_type = ECHOES_GHOST_EFFECT
    ABILITY_ID = "EchoesFromTheWarp"


class EchoesGhostRemoveOnUnitEnters(GhostRemoveOnUnitEnters):
    effect_type = ECHOES_GHOST_EFFECT
    ABILITY_ID = "EchoesFromTheWarp"


class EchoesGhostRemoveOnSourceDeathInactive(GhostRemoveOnSourceDeathInactive):
    effect_type = ECHOES_GHOST_EFFECT
    ABILITY_ID = "EchoesFromTheWarp"


class EchoesGhostRemoveOnSourceRemoved(GhostRemoveOnSourceRemoved):
    effect_type = ECHOES_GHOST_EFFECT
    ABILITY_ID = "EchoesFromTheWarp"
