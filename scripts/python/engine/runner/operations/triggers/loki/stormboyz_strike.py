"""`IdunBattleLogic.Entities.Abilities.Triggered.Loki.StormboyzStrike_TeleportAbility`
(`TriggeredAbilityType` 0x475 = 1141 `StormboyzStrike`, passif d'`orksNpc6Stormboy` << Stormboy >>)
-- tranche 3/3 du residu `#366-r1-tunnel-family`, 4e et DERNIER appelant de la primitive
`IdunBattleLogic.Entities.DSLBehaviors$$RemoveUnitFromItsTiles`.

i2 : « In its first turn this unit flies into any free hex, instead of starting on its designated
spawn point. There's a 20% chance it misses its designated hex and ends up in a random adjacent hex
instead. This fly-in counts as a movement for <i>Full Throttle</i>. »

⚠ QUALIFIER LES ENUMS -- ce kit est un nid de collisions d'id, et se tromper de table donne un port
faux SANS erreur :
    1141 = `TriggeredAbilityType.StormboyzStrike`   MAIS `ActiveAbilityType.OverwhelmingWrath`
    1140 = `EffectType.StormboyzStrike_TeleportingIn` MAIS `ActiveAbilityType.ExemplarOfHate`
           et `TriggeredAbilityType.PowerUp_Hits`
    1179 = `EffectType.StormboyzStrike_AlreadyUsedTile` MAIS `ActiveAbilityType.CultDemagogue`
           et `TriggeredAbilityType.PsychicStalk`
Les trois homonymes sont DEJA portes ailleurs (`darkangels.py`, `genestealer.py`,
`extra_damage_aura.py`) : ne rien y toucher.

RE (decompile ghidra, build `rnca9r7q6c`)
-----------------------------------------
`...StormboyzStrike_TeleportAbility$$CreateTrigger` :

    <DSLTriggers+0x30>                                          # On(0x21 = AbilityInit)
                                                                #   & <conjonct @DSLTriggers+0x70>
                                                                #   & get_OwnerIsActor
  & AmountIsEqual( UnitTurnsStarted(Owner@DSLSelectors+0x30),
                   <DSLFormulas+0x18> = Direct(0) )             # PREMIER tour de l'unite
  & op_LogicalNot( HasFlag(Owner@DSLSelectors+0x30, 0) )        # UnitFlag.Moved

`<DSLTriggers+0x30>` est bati par `IdunBattleLogic.Entities.DSLTriggers$$InitializeShared` (LU :
`op_BitwiseAnd(op_BitwiseAnd(On(0x21), <+0x70>), get_OwnerIsActor())`) -- le MEME trigger pre-cache
que toute la famille des owner-effects poses a l'init
(`...LifewardsAddEffectAbility$$CreateTrigger`, `...ListenUpMaggotsAbility$$CreateTrigger`).
⚠ `<+0x70>` n'est PAS identifie : c'est une instance d'une classe que le `$$.ctor` de `DSLTriggers`
alloue trois fois (`+0x40`, `+0x70`, et `+0x48 = op_LogicalNot(<la meme>)`), sans accesseur nomme
dans le build. Le port le COLLAPSE, exactement comme il collapse le `df@0x128` homologue de
l'ancienne `DSLFactory` monolithique depuis #95 (`dispatch/ability.py`) : ce n'est pas une lecture
neuve, c'est la convention en place pour tout ce vecteur. `<DSLFormulas+0x18>` est le `Direct(0)`
pre-cache de `IdunBattleLogic.Entities.DSLFormulas$$.ctor` (`+0x18 -> 0`, `+0x20 -> 1`,
`+0x28 -> 2`, `+0x30 -> 100`, `+0x38 -> -1`).

`...StormboyzStrike_TeleportAbility$$CreateBehaviour` :

    RemoveUnitFromItsTiles( Owner@DSLSelectors+0x30, removeTileFromUnit: true )
  & AddEffect( 0x474 = 1140 StormboyzStrike_TeleportingIn,
               AbilityStateReference, targets: Owner@DSLSelectors+0x30,
               turns: Nullable<int>(2) )

L'`AddEffect` passe la surcharge `(effectType, abilityState, targets, turns)` dont le `turns` est un
`Nullable<int>` -- la factory en fait un `Direct(n)` qu'elle range dans les options, donc une duree
DEJA EN TOURS, **non** convertie par `IdunBattle.Core.Services.BattleQuery$$ConvertRoundsToTurns`
(d'ou `duration_turns=2` et pas `duration_rounds=2`, qui vaudrait 4 tours a 2 joueurs). La MEME
surcharge passe litteralement `0` en 5e argument d'`IdunBattle.Entities.Behaviours.AddEffectBehaviour$$.ctor`
(le selecteur SOURCE) -> fallback natif « la source EST la cible » (`source_from_target=True`).

CE QUI N'EST PAS DANS CETTE TRANCHE (residus NOMMES, chacun un artefact natif DISTINCT)
---------------------------------------------------------------------------------------
* `IdunBattleLogic.Abilities.Triggered.Loki.StormboyzStrike_FallbackAbility` -- c'est LUI, et pas
  1141, qui pose `0x49b = 1179 StormboyzStrike_AlreadyUsedTile` (`AddEffect(0x49b, stateRef,
  <la tuile choisie>, turns: Nullable<int>(1))`). Trigger `On(0x28 = UnitFinishedTurn) &
  get_OwnerIsActor & HasEffect(Owner, 0x474, onlyActive: false, 6)` ; arbre
  `MoveUnitBehaviour(Caster, First(SortTilesByUtility(CanAddUnit(<Sel+0x18>), Caster,
  UtilityDefinition(6)))) & AddEffect(0x49b, ...) & PerformAIMovementBehaviour(
  AmountIsEqual(Tiles(Caster), Direct(0)), RemoveEffect(Owner, 0x474) & Kill(Caster, ForDirectKill))`.
  TRANCHE A ELLE SEULE (filet de securite « l'unite finit son tour encore hors plateau »).
* `IdunBattleLogic.Entities.Abilities.Triggered.Loki.StormboyzStrike_MissAbility` -- le « 20 % de
  rater son hex » : `On(0x1f = PreUnitMove) & get_OwnerIsActor & HasEffect(Owner, 0x474, false, 6)`
  -> `Inform{0x79: EntityId(<Sel+0x78>)} & If(Maybe(GetNumberConstant(0x2a = 'chance')),
  OverrideUnitMovementTarget(Owner, PickRandomly(CanAddUnit(AdjacentTiles(<Sel+0x78>)), 1)))
  & RemoveEffect(Caster, 0x474) & TriggerAbility(Caster, 0x46e, ...)`. Autre tranche.
* `IdunBattle.Entities.Effects.Loki.ATeleportingEffect$$CreateHandleTriggerAbilitiesInternal` -- les
  QUATRE triggers PROPRES de l'effet 1140, partages par ses trois soeurs (1035
  `TeleportStrike_TeleportingIn`, 1238 `FearOfTheUnseen_TeleportingIn`, 1573
  `TitanhammerSquad_TeleportingIn`). PORTES depuis #448-r2 (base + 1035) et #448-r2b (1140), dans
  `triggers/loki/teleporting_in.py` ; 1238 et 1573 restent hors registre (#448-r2c/d). Le paragraphe
  ci-dessous est la LECTURE D'ORIGINE, conservee -- sa derniere phrase a ete RECTIFIEE par #448-r2b
  (voir apres) :
      On(0x04 UnitAfterMove)    & OwnerIsActor                & <vslot 0x738> -> RemoveEffect(self)
      On(0x2a PreUnitAbility)   & OwnerIsActor                & <vslot 0x738> -> RemoveEffect(self)
      On(0x28 UnitFinishedTurn) & OwnerIsActor & HasTile(Owner) & <vslot 0x738> -> RemoveEffect(self)
      On(0x1f PreUnitMove)      & OwnerIsActor & <vslot 0x738> & <vslot 0x748>
          -> GetMovingEffectType().HasValue ? AddEffect(<ce type>, ..., Owner, turns: 1) : Nothing()
  `<vslot 0x738>` = `GetAdditionalRemoveTriggers` (seule surcharge nommee du build :
  `FearOfTheUnseen_TeleportingInEffect$$GetAdditionalRemoveTriggers` = `AmountIsEqual(
  EffectRemainingTurns(<Sel+0x38>), Direct(1))`) ; le corps de base est TRIVIAL donc dedupliqe et
  non nommable -- il faudrait le lire au RUNTIME (`resolveMethodPtr` sur le slot) avant de porter la
  famille. Le 4e trigger est en revanche INERTE pour 1140.
  ⚠ RECTIFICATION (#448-r2b, `resolveMethodPtr` + octets) : `StormboyzStrike_TeleportingInEffect`
  SURCHARGE bien `GetMovingEffectType` (le slot est ABSTRAIT dans la base, les QUATRE le
  surchargent) -- c'est son CORPS qui est vide, `xor eax, eax ; ret`, dedupliqe avec
  `Unity.Services.Core.Device.UnityAdsIdentifier$$get_UserId`, donc `Nullable` sans valeur.
  Conclusion observable INCHANGEE (branche `Nothing()`), lecture corrigee. Et l'`EffectType` du
  build contient TROIS `*_Moving` -- 1036, 1241, 1574 -- dont aucun Stormboyz.
* `IdunBattle.Entities.Pathfinding.StormboyzStrikePathfinder$$IsValidTeleportTile` (vslot 11) --
  le pool de teleport que 1140 declenche (`MovementQuery$$GetPathfinderTypeForUnit` -> types 8/9),
  porte en HYPOTHESE `True` dans `entities/pathfinding/teleport_pathfinder.py`. CONFRONTE ici :
  cf. `probe_366_r1_stormboyz_strike.py` volet E2 et `docs/rl/case-366-r1-tunneling-horror-pending-summon.md` §7.

PORTEUR / CONFRONTABILITE : `unit_map.py find --ability StormboyzStrike` -> UNE unite,
`orksNpc6Stormboy` (bucket **npc**, trait `Flying`), voie `passive`. Ni pool ni summoner ->
recours GREFFE du passif sur une unite du pool (`catalog_inject.graft_passive_ability`, cf.
`docs/rl/case-92-catalog-injection.md` §5bis). Legitime ici, condition VERIFIEE : ni le trigger ni
le behaviour ne lisent stat, trait ou arme du caster -- seulement ses TUILES, son compteur de tours
et son flag `Moved`. (Le trait `Flying` du VRAI porteur ne change que la BASE du decorateur de
pathfinder -- `StormboyzStrikeFly` 9 au lieu de `StormboyzStrikeWalk` 8 -- pas cette ability.)

NI `TARGETING_OPTIONS` NI `ABILITY_ATTACK_TYPE` : c'est une TRIGGERED ability
(`IdunBattle.Entities.Abilities.BaseTriggeredAbility`, cf. l'appel a
`BaseTriggeredAbility$$get_AbilityStateReference` dans `CreateBehaviour`), pas une
`AActiveAbility` -- elle n'entre pas dans `ABILITY_CLASSES`, ne traverse jamais
`IdunBattle.Operations.ActiveAbilityOperation` et n'a donc aucun masque de ciblage a poser.

DISPATCH : vecteur `ability_init_triggers` (`On(AbilityInit = 0x21 = 33)`). Cote port, ce vecteur
n'est emis que par la feuille `Spawn` (les summons) -- le roster INITIAL, lui, arrive deja
initialise dans le snapshot (l'unite y est deja hors plateau avec 1140, que `load_state` seede).
Ce port n'est donc PAS un chemin de production pour `orksNpc6Stormboy` (qui n'a aucun summoner) :
il est exerce par ses tests, contre l'etat que le NATIF produit sur le meme montage.
"""
from __future__ import annotations

from typing import Optional

from ....state import State
from ....components import StatsComponent, unit_has_moved
from ....abilities.behaviours import AddEffect, RemoveUnitFromItsTiles, entities_from_state
from .....entities.behaviours import Seq
from .....entities.selectors import Caster
from .....entities.effect_type import EffectType
from .....entities.stats import StatType
from .....entities.triggered_ability_type import TriggeredAbilityType
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from ..base import TriggeredAbility, TriggerEvent

STORMBOYZ_STRIKE_ID = "StormboyzStrike"
STORMBOYZ_TELEPORTING_IN = int(EffectType.StormboyzStrike_TeleportingIn)   # 0x474 = 1140
_ON_ABILITY_INIT = int(EventTriggerType.AbilityInit)                      # 0x21 = 33


def _turns_started(state: State, unit_id: int) -> int:
    """`IdunBattleLogic.Entities.DSLFormulas$$UnitTurnsStarted(Owner)` ->
    `IdunBattle.Entities.Formulas.UnitTurnsStartedFormula$$Calculate` = `GetStat(unit, 0xc)`.
    Canal du port : `StatsComponent.ctx.stat(StatType.TURNS_STARTED)`, le MEME que lisent
    `DeathFromAboveAbility$$GetNumSummons` et `ContagionsOfNurgleRange`. Absent -> 0."""
    e = state.get_entity(int(unit_id))
    sc = e.get_component(StatsComponent) if e is not None else None
    ctx = getattr(sc, "ctx", None) if sc is not None else None
    if ctx is None:
        return 0
    return int(ctx.stat(StatType.TURNS_STARTED) or 0)


def stormboyz_strike_teleport_tree() -> Seq:
    """`...StormboyzStrike_TeleportAbility$$CreateBehaviour`, MIRROR 1:1 de l'`op_BitwiseAnd` :

        RemoveUnitFromItsTiles( Owner, removeTileFromUnit: true )
      & AddEffect( 0x474, AbilityStateReference, targets: Owner, turns: Nullable<int>(2) )

    `Caster()` = le slot `Owner@DSLSelectors+0x30` (pour une triggered ability, `entities.caster`
    EST l'owner -- meme convention que `ListenUpMaggotsAbility`).

    `duration_turns=2` et NON `duration_rounds=2` : la surcharge `turns:Nullable<int>` de
    `IdunBattleLogic.Entities.DSLBehaviors$$AddEffect` construit un `Direct(2)` qu'elle range
    directement dans les options -- `IdunBattle.Operations.AddEffectOperation$$Execute` ne le
    convertit PAS. A deux joueurs, `duration_rounds=2` donnerait 4 tours : le `remaining` LIVE est
    donc un discriminant, pas une coincidence.

    `source_from_target=True` : la factory passe litteralement `0` en selecteur SOURCE
    d'`AddEffectBehaviour$$.ctor` -> « la source EST la cible ». Ici cible == owner == caster, donc
    le resultat coincide avec le defaut historique ; on transcrit la forme NATIVE, pas la
    coincidence (meme lecture que `burrowers_hidden_tree`)."""
    return Seq(RemoveUnitFromItsTiles(Caster(), remove_tile_from_unit=True),
               AddEffect(STORMBOYZ_TELEPORTING_IN,
                         EffectType.StormboyzStrike_TeleportingIn.name, Caster(),
                         duration_rounds=None, duration_turns=2, source_from_target=True))


class StormboyzStrikeTeleportAbility(TriggeredAbility):
    """`StormboyzStrike_TeleportAbility` (1141) : a l'init de ses abilities, si c'est bien son
    PREMIER tour et qu'elle n'a pas bouge, l'unite QUITTE le plateau et prend
    `StormboyzStrike_TeleportingIn` (1140) pour 2 tours -- l'etat qui detourne son pathfinder vers
    `StormboyzStrikePathfinder` (`MovementQuery$$GetPathfinderTypeForUnit`, types 8/9) et lui donne
    un pool de destination BOARD-WIDE au lieu de son disque de mouvement."""
    event_id = _ON_ABILITY_INIT
    TRIGGERED_ABILITY_ID = int(TriggeredAbilityType.StormboyzStrike)      # 0x475 = 1141

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        if ev.actor_id != self.owner_id:                 # get_OwnerIsActor (<DSLTriggers+0x30>)
            return False
        if _turns_started(state, self.owner_id) != 0:    # AmountIsEqual(UnitTurnsStarted, Direct(0))
            return False
        return not unit_has_moved(state, self.owner_id)  # op_LogicalNot(HasFlag(Owner, Moved=0))

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        if state.effects is None:
            return None                                   # pas d'EffectsState -> pose impossible
        ectx = ExecutionContext(state=state, rng=state.rng)
        stormboyz_strike_teleport_tree().execute(entities_from_state(state, self.owner_id), ectx)
        freed = [p.get("tiles") for n, p in ectx.emitted if n == "RemoveUnitFromItsTiles"]
        placed = any(p.get("placed") for n, p in ectx.emitted if n == "AddEffect")
        return {"ability": STORMBOYZ_STRIKE_ID, "unit": self.owner_id,
                "tilesFreed": (freed[0] if freed else []), "placed": bool(placed)}
