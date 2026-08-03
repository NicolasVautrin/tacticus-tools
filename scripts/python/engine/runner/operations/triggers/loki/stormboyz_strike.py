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

LES DEUX AUTRES CLASSES DU MEME `TriggeredAbilityType` (#448-r1, PORTEES ICI DEPUIS)
-------------------------------------------------------------------------------------
`TriggeredAbilityType` ne contient qu'UN `StormboyzStrike` (1141), et le builder
`AbilitiesDatabase.u003Cu003Ec$$u003CInitializeTriggeredAbilitiesu003Eb__28_134` en construit
**TROIS** instances (contre UNE pour `FullThrottle`/`b__28_137`) : le passif monte donc les trois
d'un coup, et le registre les inscrit toutes les trois sous la meme cle.

* `...StormboyzStrike_FallbackAbility` -- le filet « fin de tour encore hors plateau ». C'est LUI,
  et pas 1141, qui pose `0x49b = 1179 StormboyzStrike_AlreadyUsedTile`. Cf.
  `StormboyzStrikeFallbackAbility` plus bas.
* `...StormboyzStrike_MissAbility` -- les 20 % de rater son hex. Cf. `StormboyzStrikeMissAbility`.

⚠ **RECTIFICATION de la lecture d'origine (#448-r1)** : le 3e terme du Fallback n'est PAS un
`PerformAIMovementBehaviour`. La classe allouee est `IdunBattle.Entities.Behaviours.IfBehaviour` --
c'est la MEME que celle qu'alloue `IdunBattleLogic.Entities.DSLBehaviors$$If` (identite tranchee par
XREFS sur le cache de classe, pas a l'oeil), et `IfBehaviour$$Execute` lit exactement les trois
champs que le ctor pose (`+0x50` condition -> `ShouldTrigger`, `+0x58` branche VRAIE, `+0x60`
branche FAUSSE, resultat VIDE si elle est nulle). Le `$$.ctor` nomme
`IdunBattle.Entities.Behaviours.PerformAIMovementBehaviour$$.ctor` dans les tables est un corps
DEDUPLIQUE (trois champs `+0x50/+0x58/+0x60`, et ses noms de parametres `unit, range,
overrideUtility` ne collent a AUCUN des arguments passes ici) ; le VRAI
`PerformAIMovementBehaviour$$Execute`, lui, lit CINQ champs (`+0x50` selecteur d'unites, `+0x58`
formule, `+0x68`, `+0x70` delegue, et ECRIT `+0x60`) -- il n'a rien a voir avec ce call-site.
⇒ **`PerformAIMovementBehaviour` n'est PAS une piece manquante de ce kit.** Le nœud est un `If`,
deja porte.

CE QUI N'EST PAS DANS CETTE TRANCHE (residus NOMMES, chacun un artefact natif DISTINCT)
---------------------------------------------------------------------------------------
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
from ....components import StatsComponent, PositionComponent, unit_has_moved
from ....abilities.behaviours import (AddEffect, Kill, MoveUnit, OverrideUnitMovementTarget,
                                      RemoveEffect, RemoveUnitFromItsTiles, TriggerAbility,
                                      entities_from_state)
from .....entities.behaviours import Seq, If, Inform
from .....entities.formulas import Count
from .....entities.selectors import (AdjacentTiles, AllTiles, CanAddUnit, Caster, FixedTile,
                                     PickFirstN, PickRandomly, SortTilesByUtility, Tiles)
from .....entities.triggers import AmountIsEqual, MaybeTrigger
from .....entities.effect_type import EffectType
from .....entities.stats import StatType
from .....entities.triggered_ability_type import TriggeredAbilityType
from .....dsl.base import Const
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....utilities.utility_type import UtilityType
from ..base import TriggeredAbility, TriggerEvent

STORMBOYZ_STRIKE_ID = "StormboyzStrike"
STORMBOYZ_TELEPORTING_IN = int(EffectType.StormboyzStrike_TeleportingIn)   # 0x474 = 1140
STORMBOYZ_ALREADY_USED_TILE = int(EffectType.StormboyzStrike_AlreadyUsedTile)   # 0x49b = 1179
_ON_ABILITY_INIT = int(EventTriggerType.AbilityInit)                      # 0x21 = 33
_ON_UNIT_FINISHED_TURN = int(EventTriggerType.UnitFinishedTurn)           # 0x28 = 40
_ON_PRE_UNIT_MOVE = int(EventTriggerType.PreUnitMove)                     # 0x1f = 31
_FULL_THROTTLE = int(TriggeredAbilityType.FullThrottle)                   # 0x46e = 1134


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


def _has_teleporting_in(state: State, unit_id: int) -> bool:
    """`HasEffect(Owner@DSLSelectors+0x30, 0x474, onlyActive: FALSE, targetType: 6)` -- le gate
    commun aux DEUX triggers ci-dessous, lu VERBATIM dans les deux `CreateTrigger`.

    `onlyActive = 0` : la 4e position du `DSLTriggers$$HasEffect` natif, un flag ACTIVE-ONLY (#100)
    -- ici a ZERO, donc un `1140` pose-mais-INACTIF compte AUSSI. `targetType = 6` = les DEUX
    branches d'`EntityExtensions$$HasOneOfEffects` (owned | incoming). Le port lit la liste
    possedee sans filtre `is_active`, ce qui EST le `onlyActive = 0` ; le gate `consumed` reste
    (un effet consomme n'est plus dans `ActiveEffectIds` cote natif non plus)."""
    eff = getattr(state, "effects", None)
    if eff is None or unit_id is None:
        return False
    return any((not e.consumed) and e.effect_type == STORMBOYZ_TELEPORTING_IN
               for e in eff.by_unit.get(int(unit_id), []))


def stormboyz_strike_fallback_tree() -> Seq:
    """`IdunBattleLogic.Abilities.Triggered.Loki.StormboyzStrike_FallbackAbility$$CreateBehaviour`,
    MIRROR 1:1 de l'ARBRE (ordre des `op_BitwiseAnd` relu au decompile) :

        ( MoveUnitBehaviour( Caster@Sel+0x48, <sel>, <options 0x40 octets a ZERO> )
        & AddEffect( 0x49b = 1179, AbilityStateReference, targets: <sel>,
                     turns: Nullable<int>(1) ) )
        & If( AmountIsEqual( Tiles(Caster@Sel+0x48), <DSLFormulas+0x18> = Direct(0) ),
              RemoveEffect( Owner@Sel+0x30, Nullable(0x474) ) & Kill( Caster, Caster, ForDirectKill ),
              null )

    ou `<sel>` = `First( SortTilesByUtility( CanAddUnit(<DSLSelectors+0x18>), Caster@Sel+0x48,
                                             UtilityDefinition(6), null ),
                         Direct(1) )`.

    LE MEME OBJET-NOEUD `<sel>` EST PARTAGE par le `MoveUnitBehaviour` et l'`AddEffect` (`local_78`
    dans le decompile) -- d'ou la variable unique ci-dessous, et surtout d'ou le QUIRK #425 : `&` les
    execute EN SEQUENCE, donc a la RE-EVALUATION le caster occupe deja la meilleure tuile,
    `CanAddUnit` l'EXCLUT, et `First` rend la SUIVANTE du classement. **La tuile marquee 1179 n'est
    PAS la tuile d'atterrissage** (mesure live : atterrissage (1,3), marque (0,3)). C'est
    precisement pour preserver ce quirk que `SortTilesByUtility` est un vrai NOEUD ici et pas un
    collapse imperatif.

    DEUX SLOTS LUS, PAS DEVINES :
      * `<DSLSelectors+0x18>` = `IdunBattle.Entities.Selectors.AllTilesSelector` --
        `IdunBattleLogic.Entities.DSLSelectors$$InitializeShared` l'y ecrit NOMMEMENT (seul slot dont
        le ctor n'est pas mislabelle). Le pool est le PLATEAU ENTIER, pas un voisinage.
      * `UtilityDefinition(6)` = `UtilityType.UnitMovement` -- tranche par XREF ENTRANTE :
        `$$CreateBehaviour` appelle la surcharge `UtilityDefinition..ctor(this, utilityType)`, la
        meme que `DSLSelectors$$SortTilesByUtility` emploie pour envelopper son argument `int` (les
        deux autres surcharges, `(bucket)` et `(utility)`, ont des appelants disjoints). C'est LE
        score de mouvement de l'IA, et `TileEffects(10)` en est une feuille -- voila par ou le
        marqueur 1179 (poids `-100`, le plus negatif des 20) mord sur les Stormboyz SUIVANTS.

    `First(source, Direct(1))` = **`PickFirstN(source, 1)`**, pas un index : le parametre natif
    s'appelle `amount`, la surcharge `int` de `DSLSelectors$$First` construit `Direct(amount)` et
    delegue a la surcharge objet, qui alloue un `IdunBattle.Entities.Selectors.PickFirstNSelector`
    (`Select` = « les `amount` premiers »). `PickAtIndexSelector` est une classe DISTINCTE, d'une
    autre factory.

    `turns: Nullable<int>(1)` = une duree DEJA EN TOURS (surcharge `turns` de
    `DSLBehaviors$$AddEffect` -> `Direct(n)` range tel quel), **pas** un `TurnsFromRounds` -> UN seul
    tour. La MEME surcharge passe `0` en selecteur SOURCE -> `source_from_target=True` (mesure #425 :
    l'entite 1179 a bien `SourceUnitId == OwnerId == la tuile marquee`).

    `AmountIsEqual(<selecteur>, <formule>)` = la surcharge `(selector, amount)` de
    `DSLTriggers$$AmountIsEqual` (les trois surcharges allouent la MEME classe
    `AmountIsEqualAbilityTrigger` ; seul le type du 1er argument les separe) -> cote port
    `Count(Tiles(...))`. Le gate est donc **« le caster n'est sur AUCUNE tuile »**, c'est-a-dire
    « le move n'a rien trouve » : le Stormboy qui ne peut nulle part se poser PERD son 1140 et MEURT.

    `Caster()` = le slot `Owner@DSLSelectors+0x30` comme `Caster@Sel+0x48` : pour une triggered
    ability les deux coincident (meme convention que `stormboyz_strike_teleport_tree` ci-dessus).
    Le natif utilise pourtant les DEUX slots dans le meme arbre -- transcrit sans les distinguer,
    exactement comme le port le fait deja partout ailleurs sur ce vecteur."""
    sel = PickFirstN(SortTilesByUtility(CanAddUnit(AllTiles()), Caster(),
                                        int(UtilityType.UnitMovement)), Const(1))
    return Seq(Seq(MoveUnit(Caster(), sel),
                   AddEffect(STORMBOYZ_ALREADY_USED_TILE,
                             EffectType.StormboyzStrike_AlreadyUsedTile.name, sel,
                             duration_rounds=None, duration_turns=1, source_from_target=True)),
               If(AmountIsEqual(Count(Tiles(Caster())), Const(0)),
                  Seq(RemoveEffect(STORMBOYZ_TELEPORTING_IN, Caster()),
                      Kill(Caster(), Caster())),
                  None))


class StormboyzStrikeFallbackAbility(TriggeredAbility):
    """`IdunBattleLogic.Abilities.Triggered.Loki.StormboyzStrike_FallbackAbility` (1141) -- le FILET
    de securite du kit : « l'unite finit son tour ENCORE hors plateau ».

        $$CreateTrigger = On(0x28 = UnitFinishedTurn) & get_OwnerIsActor
                        & HasEffect( Owner@Sel+0x30, 0x474, onlyActive: false, targetType: 6 )

    Le vecteur `On(0x28)` est EMIS par le port depuis #448-r2 (`dispatch/turn.py::
    unit_finished_turn_triggers`, appele par `operations/turnflow.py` sous son gate natif « le flag
    TurnFinished vient d'etre POSE » -- et MEME sur une terminaison forcee, contrairement a
    `On(0x29)`). C'etait la 1re des quatre « pieces manquantes » de la fiche #448-r1 : elle est
    fermee depuis, la fiche etait perimee sur ce point.

    L'arbre : cf. `stormboyz_strike_fallback_tree`. Trois observables distincts, et il faut les
    TROIS pour que le port soit fidele : l'unite ATTERRIT, la tuile suivante est MARQUEE 1179 (poids
    de mouvement `-100` pour les Stormboyz suivants du meme tour), et si aucune tuile n'etait libre
    elle MEURT en perdant son 1140.

    NI `TARGETING_OPTIONS` NI `ABILITY_ATTACK_TYPE` : c'est une `BaseTriggeredAbility` (cf. l'appel a
    `BaseTriggeredAbility$$get_AbilityStateReference` dans `$$CreateBehaviour`), elle n'entre pas
    dans `ABILITY_CLASSES` et ne traverse jamais `IdunBattle.Operations.ActiveAbilityOperation`."""
    event_id = _ON_UNIT_FINISHED_TURN
    TRIGGERED_ABILITY_ID = int(TriggeredAbilityType.StormboyzStrike)      # 0x475 = 1141

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        if ev.actor_id != self.owner_id:                  # get_OwnerIsActor
            return False
        return _has_teleporting_in(state, self.owner_id)  # HasEffect(Owner, 0x474, false, 6)

    def execute_behaviour(self, state: State, ev: TriggerEvent):
        ectx = ExecutionContext(state=state, rng=state.rng)
        stormboyz_strike_fallback_tree().execute(entities_from_state(state, self.owner_id), ectx)
        moved = [p for n, p in ectx.emitted if n == "MoveUnit"]
        marked = [p.get("target") for n, p in ectx.emitted if n == "AddEffect" and p.get("placed")]
        killed = [i for n, p in ectx.emitted if n == "Kill" for i in (p.get("killed") or [])]
        e = state.get_entity(self.owner_id)
        pc = e.get_component(PositionComponent) if e is not None else None
        return {"ability": STORMBOYZ_STRIKE_ID, "class": "Fallback", "unit": self.owner_id,
                "landed": ((pc.col, pc.row) if pc is not None else None),
                "moved": bool(moved and moved[-1].get("moved")),
                "markedTiles": marked, "killed": killed}


def stormboyz_strike_miss_tree(dest, chance: int, rng) -> Seq:
    """`IdunBattleLogic.Entities.Abilities.Triggered.Loki.StormboyzStrike_MissAbility$$
    CreateBehaviour`, MIRROR 1:1 (ordre des `op_BitwiseAnd` relu -- l'arbre est
    `((Inform & If) & RemoveEffect) & TriggerAbility`) :

        Inform( { 0x79 : EntityId(<Sel+0x78>) } )
      & If( Maybe( GetNumberConstant(0x2a = 'chance') ),
            OverrideUnitMovementTarget( Owner@Sel+0x30,
                PickRandomly( CanAddUnit( AdjacentTiles(<Sel+0x78>) ),
                              1, null, 0x7fffffff, false ) ),
            null )
      & RemoveEffect( Caster@Sel+0x48, Nullable(0x474), null )
      & TriggerAbility( Caster@Sel+0x48, 0x46e = 1134 FullThrottle, Caster, Caster, null, null, 3, false )

    `<Sel+0x78>` = les tuiles de DESTINATION du mouvement en cours. Cote port c'est
    `TriggerEvent.dest_tile`, que `MoveUnitOperation.execute` -- seul emetteur du vecteur
    `On(0x1f = PreUnitMove)` -- threade deja (meme canal que `HatefulAssaultAbility`, ou le natif met
    la MEME liste `position` en `casterTiles` ET en `targetTiles`). Materialise ici par `FixedTile`,
    comme les autres call-sites qui consomment une tuile calculee hors arbre.

    `0x46e` = **`TriggeredAbilityType.FullThrottle` (1134)** -- mot pour mot le « This fly-in counts
    as a movement for *Full Throttle* » de l'i2, et le porteur natif porte bien les deux passifs
    (`orksNpc6Stormboy.passiveAbilities = ['StormboyzStrike', 'FullThrottle']`). Le noeud
    `TriggerAbility` **COURT-CIRCUITE le `CreateTrigger`** de l'ability declenchee : lu au decompile
    d'`IdunBattle.Operations.TriggerTriggeredAbilityOperation$$TriggerAbility`, qui va directement au
    slot `Execute` de l'ability (avec `triggerType = 0x20 = Custom`) sans jamais evaluer son
    `ShouldTrigger`. Le gate `AmountIsEqualOrGreater(MovementSteps(), Direct(movement = 3))` du
    passif FullThrottle n'est donc PAS exerce ici -- et c'est coherent : le fly-in est board-wide.

    `Inform{0x79: ...}` est un canal de VUE (`StormboyzStrikeVisuals$$GetFinalTile` lit
    `GetStepMessage(0x25)` puis, a defaut, `GetInfoMessage(0)`, et en extrait la cle `0x79`). Le
    runner n'a pas de bus de vue -> le noeud `Inform` porte est un NO-OP structurel, sa charge utile
    est DROPPEE (comportement en place depuis FireOfAbsolution). MIRROR STRUCTUREL, pas une
    mutation.

    `Maybe(chance)` = le PREDICAT `MaybeTrigger` (surcharge a UN argument, `NextBool(chance)`), pas
    le noeud EFFET homonyme -- il consomme UN tirage du PRNG de bataille, a CHAQUE mouvement du
    porteur sous 1140. `chance` = `StormboyzStrike.constants.chance` = **20**.

    `RemoveEffect(Caster, 0x474)` est HORS du `If` : le 1140 tombe que le hex ait ete rate ou non --
    le vol n'a lieu qu'une fois. Et le `TriggerAbility` l'est aussi : FullThrottle est declenche
    dans les DEUX cas.

    `rng` est passe au CONSTRUCTEUR du `MaybeTrigger`, comme le natif : le PRNG y est un CHAMP de
    l'instance (`+0x18`, pose par la factory depuis `DSLFactory+0x18`), pas une entree du contexte."""
    return Seq(Seq(Seq(Inform(0x79),
                       If(MaybeTrigger(rng, Const(int(chance))),
                          OverrideUnitMovementTarget(
                              Caster(),
                              PickRandomly(CanAddUnit(AdjacentTiles(FixedTile(dest))), 1)),
                          None)),
                   RemoveEffect(STORMBOYZ_TELEPORTING_IN, Caster())),
               TriggerAbility(Caster(), _FULL_THROTTLE))


class StormboyzStrikeMissAbility(TriggeredAbility):
    """`IdunBattleLogic.Entities.Abilities.Triggered.Loki.StormboyzStrike_MissAbility` (1141) -- les
    20 % de rater son hex.

        $$CreateTrigger = On(0x1f = PreUnitMove) & get_OwnerIsActor
                        & HasEffect( Owner@Sel+0x30, 0x474, onlyActive: false, targetType: 6 )

    MEME trigger que le Fallback a l'evenement pres. Il fire sur le mouvement d'ATTERRISSAGE du
    Stormboy -- que ce mouvement vienne du joueur/de l'IA, ou du `MoveUnitBehaviour` du Fallback
    lui-meme (qui passe des options a ZERO, donc SANS `skipPreMoveTriggers`).

    Son arbre (cf. `stormboyz_strike_miss_tree`) DEVIE la destination via
    `OverrideUnitMovementTarget` -> `OverrideMovementTargetOperation` -> le canal
    `UnitComponent.movement_target_override`, que `MoveUnitOperation.execute` relit APRES le vecteur,
    consomme, et qui la fait RELANCER le mouvement vers la nouvelle tuile sans re-emettre les
    pre-move triggers. C'est la chaine complete : le port n'a aucune deviation « recablee ».

    NI `TARGETING_OPTIONS` NI `ABILITY_ATTACK_TYPE` (meme lecture que le Fallback)."""
    event_id = _ON_PRE_UNIT_MOVE
    TRIGGERED_ABILITY_ID = int(TriggeredAbilityType.StormboyzStrike)      # 0x475 = 1141

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        if ev.actor_id != self.owner_id:                  # get_OwnerIsActor
            return False
        return _has_teleporting_in(state, self.owner_id)  # HasEffect(Owner, 0x474, false, 6)

    def execute_behaviour(self, state: State, ev: TriggerEvent):
        import gameconfig as GC
        dest = getattr(ev, "dest_tile", None)
        if dest is None:
            # `<Sel+0x78>` VIDE : le vecteur ne porte pas de destination. Le natif resoudrait un
            # selecteur vide -> `AdjacentTiles([])` vide -> le gate `Count > 0` d'
            # `OverrideUnitMovementTargetBehaviour$$Execute` est FAUX -> pas de deviation. Les trois
            # AUTRES termes de l'arbre s'executent quand meme -- on les joue donc, avec un
            # `FixedTile` vide, plutot que de sortir en no-op (ce qui taierait le retrait de 1140 et
            # le TriggerAbility).
            dest = None
        chance = int((GC.ability(STORMBOYZ_STRIKE_ID) or {}).get("constants", {}).get("chance") or 0)
        ectx = ExecutionContext(state=state, rng=state.rng)
        tree = stormboyz_strike_miss_tree(dest, chance, state.rng)
        tree.execute(entities_from_state(state, self.owner_id), ectx)
        ovr = [p for n, p in ectx.emitted if n == "OverrideUnitMovementTarget"]
        return {"ability": STORMBOYZ_STRIKE_ID, "class": "Miss", "unit": self.owner_id,
                "dest": (tuple(dest) if dest is not None else None),
                "missed": bool(ovr and ovr[-1].get("applied")),
                "deviatedTo": (ovr[-1].get("target") if ovr else None),
                "triggered": [p.get("ability_type") for n, p in ectx.emitted
                              if n == "TriggerAbility"]}
