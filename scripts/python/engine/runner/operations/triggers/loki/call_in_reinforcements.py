"""`CallInReinforcements` -- passif `TriggeredAbilityType` 0x405 = **1029** (#1080).

i2 : « At the end of the Vox-caster's action, a Cadian Guardsman is summoned in a nearby free edge
hex and immediately takes a turn. Cadian Guardsman's stats: 1819 Health 873 Damage 364 Armour »

PORTEURS (gate de confrontabilite, ventiles -- meme forme que case-1052) :
  * `astraNpc3Voxcaster` -- **npc**, `units.npc[].stats[]` present (45 paliers) -> confrontable par
    le CHEMIN DE STATS EXPLICITE (`rl_duel build --explicit-stats astraNpc3Voxcaster:45`, case-92
    Sec.5bis recours 4). Le porteur arrive avec SES stats, SES traits, SES armes ;
  * `astraSmnVoxcaster` -- **summon**, `visualId == astraNpc3Voxcaster` (le jumeau npc ci-dessus).
    Son invocateur existe mais n'est porte par AUCUNE UNITE : un balayage EXHAUSTIF du gameconfig
    (tout `str` de l'arbre, pas seulement `constants.unitId*`) le trouve exactement dans
    `units.abilities.EnvFactionSummons:Armageddon{Astra,BA,BT,SW}.constants.unitId` -- quatre
    abilities d'ENVIRONNEMENT, dont AUCUNE n'est referencee ailleurs dans le gameconfig courant
    (0 occurrence, `liveEvents` compris). C'est le cas 2 de case-92 Sec.5bis, et c'est pourquoi
    l'audit rendait `S?` ; le jumeau NPC le rend confrontable quand meme.

================================================================================================
RE (decompile ghidra, build `rnca9r7q6c`) -- decompile = verite
================================================================================================
La classe vit dans le namespace `...Abilities.Active.Loki`, mais le gameconfig l'attribue par
`passiveAbilities` et son ordinal est une `TriggeredAbilityType` : **le namespace ne tranche pas la
voie**, l'appariement se fait par le NOM (`TriggeredAbilityType.CallInReinforcements` = 1029 ;
`EffectType` et `ActiveAbilityType` n'ont AUCUN membre de ce nom).

## `IdunBattleLogic.Entities.Abilities.Active.Loki.CallInReinforcementsAbility$$CreateTrigger`

    On(0x29 = UnitFinishedTurnNormally, ownerNeedsToBeAlive: true)  &  get_OwnerIsActor

## `...CallInReinforcementsAbility$$CreateBehaviour(abilityState, triggerType)`

    opts       = SpawnUnitOptions.WithStatsFromConfig(config@<this+0x20>, abilityState, null, null)
    opts+0x18  = PerformAIAttack(ActiveTarget@<DSLSelectors+0x68>, allowOnlyMove: 1,
                                 overrideMovement: null, utilityEntity: null, customUtility: null)
    util       = UtilityDefinition( UtilityBucket([ WeightedUtility(0x1b = 27 PowerUp,      null),
                                                    WeightedUtility(0x22 = 34 TileDistance, null) ]) )
    tiles      = EdgeTiles( CanAddUnit(AllTiles@<DSLSelectors+0x18>) )
    tiles      = SortTilesByUtilityForSummon(tiles, util, Owner@<DSLSelectors+0x30>)
    tiles      = First(tiles, amount: 1, ignoreForcedTargets: 0)
    unitId     = AbilityConfiguration.GetStringConstant(config, 0 = unitId)   # astraSmnGuardsman
    return Spawn(Caster@<DSLSelectors+0x48>, tiles, unitId, opts)

`...CallInReinforcementsAbility$$GetPossibleSpawnTiles` = `EdgeTiles(CanAddUnit(AllTiles))`, le
MEME sous-arbre extrait pour la face DECISION -- hors perimetre de cette tranche.

Table des selecteurs partages (`IdunBattleLogic.Entities.DSLSelectors$$InitializeShared`, noms de
CHAMP mesures par #1064) : `+0x18 _allTiles · +0x20 _allAliveUnits · +0x30 Owner · +0x48 Caster ·
+0x68 ActiveTarget`.

⚠ **CE PORT EST LE JUMEAU EXACT DE `ForwardSpotter` (1143), A DEUX ETAGES PRES.** Meme summon
(`astraSmnGuardsman`), meme `WithStatsFromConfig`, meme on-appearance
`PerformAIAttack(ActiveTarget, allowOnlyMove = 1, moveAmount = null)` -- donc le meme « immediately
takes a turn » (le summon S'APPROCHE avant de frapper, #348). Ce qui differe :
  * la CHAINE DE TUILES : `EdgeTiles(CanAddUnit(AllTiles))` (tout le BORD du plateau) au lieu de
    `CanAddUnit(AdjacentTiles(target))` (le voisinage d'une cible choisie) ;
  * la DEFINITION D'UTILITE : un bucket BATI A LA MAIN `[PowerUp(27), TileDistance(34)]` au lieu de
    la surcharge scalaire `UtilityDefinition(7 = Tile)`.
Recopier le voisin de forme aurait donc pose le summon au mauvais endroit, en silence.

⚠ **`TileDistance(34)` EST CE QUI PORTE LE « nearby » DE L'i2.** `EdgeTiles(CanAddUnit(AllTiles))`
rend TOUT le bord libre du plateau ; `PowerUp(27)` vaut 0 partout tant qu'aucun power-up n'occupe
une candidate. Le seul terme discriminant est donc `-distance/10` a la main tile du PARENT
(`Owner@<+0x30>`), c'est-a-dire du Vox-caster : la tuile de bord LIBRE LA PLUS PROCHE gagne. C'est
la branche `else if (c.owner != null) DistanceTo(c, c.owner)` de
`IdunBattle.AI.Utilities.TileDistanceUtility.u003CEvaluateMovementInStepsu003Ed__1$$MoveNext`, que
le port ne portait PAS (elle etait declaree inatteignable, aucun call-site ne l'exercant) : elle est
portee par cette tranche, avec la cle `ctx["parent_pos"]` de `_spawn_leaf_ctx`.

⚠ **`IsEdgeTile` compte la tuile ELLE-MEME.** `IdunBattle.Core.Services.BattleQuery$$IsEdgeTile` =
`GetSurroundingTilesCount(tile, 1, false, false, false, includeCenter: TRUE) <= 5`, litteraux LUS A
L'ASSEMBLEUR (le pseudo-C laisse deux arguments en registres non resolus) => **`voisins <= 4`**, pas
`voisins < 6`. Une tuile a CINQ voisins n'est pas « edge ». Detail : le noeud `EdgeTiles`.

================================================================================================
CE QUE `ABILITY_CLASSES` N'EXIGE PAS
================================================================================================
1029 est une `TriggeredAbilityType`, donc elle n'entre NI dans `ABILITY_CLASSES`, NI dans
`TARGETING_OPTIONS`, NI dans `ABILITY_ATTACK_TYPE` -- ces trois registres sont ceux des abilities
ACTIVES (meme constat que `Pyreblaster`, case-1052).

RESIDUS NOMMES
  * `PowerUp(27)` ne mord que si une candidate porte un occupant power-up. Le port resout
    l'occupant par le foyer `_occupants_by_tile` et lit son kit DECLENCHE
    (`unit_is_power_up`, mirror d'`IdunBattle.Entities.UnitExtensions$$IsPowerUp` sur les 22
    `TriggeredAbilityType` du `.cctor` de `StaticBattleRules.TriggeredAbility`) ; sur un runner
    monte par `rl_duel build` il n'y a AUCUN power-up, donc ce terme est constant a 0 et NON
    CONFRONTE. Le poids BC `PowerUp.summons_dislike_tiles_with_powerups` n'est pas exerce non plus.
  * `ignoreForcedTargets = 0` du `First` : transporte, jamais lu (le port n'a pas de notion de
    cible forcee a cet etage) -- MEME residu que tous les call-sites portes de `First`.
  * Les trois derniers arguments de `PerformAIAttack` (`overrideMovement`, `utilityEntity`,
    `customUtility`, tous `null`) : le port n'en porte que les DEUX premiers champs
    (`+0x70 allowMoveAction`, `+0x78 moveAmount`), comme au call-site `ForwardSpotter`.
"""
from __future__ import annotations

from typing import Optional

from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.selectors.accessors import ActiveTarget, Owner
from .....entities.selectors.geometry import EdgeTiles
from .....entities.selectors.tiles import AllTiles, CanAddUnit, SortTilesByUtility
from .....entities.selectors.units import First
from .....entities.triggered_ability_type import TriggeredAbilityType
from .....utilities.decider import UtilityBucket, UtilityDefinition, WeightedUtility
from .....utilities.utility_type import UtilityType
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.summon import PerformAIAttack, Spawn
from ....components import UnitComponent
from ....state import State
from ..base import TriggeredAbility, TriggerEvent

#: Cle du registre `ABILITY_TRIGGERS` = le NOM gameconfig du passif (`units.<kind>.<id>.
#: passiveAbilities`), DERIVE du mirror d'enum -- jamais un litteral (meme convention que
#: `PYREBLASTER_KEY` de `loki/pyreblaster.py`).
CALL_IN_REINFORCEMENTS_KEY = TriggeredAbilityType.CallInReinforcements.name   # "CallInReinforcements"
ABILITY_ID = CALL_IN_REINFORCEMENTS_KEY

#: `UtilityDefinition( UtilityBucket([ WeightedUtility(0x1b, null), WeightedUtility(0x22, null) ]) )`
#: -- la definition BATIE A LA MAIN par `...CallInReinforcementsAbility$$CreateBehaviour` (allocation
#: d'un `WeightedUtility[2]`, UN `IdunBattleLogic.AI.Utilities.UtilityBucket$$.ctor`, puis UN
#: `IdunBattleLogic.AI.Utilities.UtilityDefinition$$.ctor`). Surtout PAS la surcharge scalaire
#: `UtilityDefinition(utilityType)`, qui ne peut pas exprimer deux termes. `Nullable<Fix64>` VIDE aux
#: deux -> poids 1 chacun.
CALL_IN_REINFORCEMENTS_SPAWN_TILE_UTILITY = UtilityDefinition(UtilityBucket([
    WeightedUtility(utility_type=int(UtilityType.PowerUp)),          # 0x1b = 27
    WeightedUtility(utility_type=int(UtilityType.TileDistance)),     # 0x22 = 34
]))


def call_in_reinforcements_spawn_tiles():
    """La chaine de tuiles de `...CallInReinforcementsAbility$$CreateBehaviour`, noeud par noeud :

        First( SortTilesByUtilityForSummon( EdgeTiles( CanAddUnit(AllTiles@<DSLSelectors+0x18>) ),
                                            <definition BATIE A LA MAIN>,
                                            Owner@<DSLSelectors+0x30> ),
               1 )

    `SortTilesByUtilityForSummon(tiles, definition, parent)` =
    `SortTilesByUtility(tiles, AllAliveMachinesSelector<provider NUL>, definition, parent)` : le
    `dc.unit` natif vaut donc **null** et le `dc.parent` vaut l'owner -- la signature EXACTE du
    regime SPAWN de case-205, exprimee ici par `unit_sel=None` + `parent_sel=Owner()`.

    `AllTiles` est bien le selecteur PARTAGE `<+0x18>` (`IdunBattle.Entities.Selectors.
    AllTilesSelector`, le SEUL des 14 que ghidra nomme dans `$$InitializeShared`), donc le balayage
    porte sur TOUT le plateau, pas sur un voisinage."""
    tiles = EdgeTiles(CanAddUnit(AllTiles()))
    return First(SortTilesByUtility(
        tiles, unit_sel=None, parent_sel=Owner(),
        utility_definition=CALL_IN_REINFORCEMENTS_SPAWN_TILE_UTILITY))


def call_in_reinforcements_tree() -> Spawn:
    """`Spawn(Caster@<+0x48>, <les tuiles>, GetStringConstant(0) = astraSmnGuardsman, opts)` avec
    `opts+0x18 = PerformAIAttack(ActiveTarget@<+0x68>, allowOnlyMove: 1, ...)`.

    `allow_move_action=True` + `move_amount=None` = les champs `+0x70`/`+0x78` du noeud
    `IdunBattleLogic.Entities.DSLBehaviors$$PerformAIAttack` (a opposer au
    `...FromCurrentPosition`, qui vaut `0`/`Direct(0)`) : le Guardsman fraichement pose joue un TOUR
    COMPLET -- il s'APPROCHE puis frappe. C'est le « immediately takes a turn » de l'i2, et c'est le
    MEME couple de litteraux que `ForwardSpotterAbility$$ExecuteBehaviour`, qui invoque le meme
    summon."""
    return Spawn(call_in_reinforcements_spawn_tiles(), ABILITY_ID,
                 on_appearance=PerformAIAttack(ActiveTarget(), allow_move_action=True,
                                               move_amount=None))


class CallInReinforcementsAbility(TriggeredAbility):
    """`...CallInReinforcementsAbility$$CreateTrigger` + `$$CreateBehaviour` -- cf. l'en-tete.

    OBSERVABLE : quand le Vox-caster CLOT son activation normalement, un `astraSmnGuardsman`
    apparait sur la tuile de bord LIBRE la plus proche de lui et joue immediatement son tour."""
    event_id = int(EventTriggerType.UnitFinishedTurnNormally)   # `On(0x29, ownerNeedsToBeAlive: 1)`

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        # `get_OwnerIsActor` -- l'unite qui vient de finir son tour EST le porteur.
        if ev.actor_id is None or int(ev.actor_id) != int(self.owner_id):
            return False
        # `ownerNeedsToBeAlive: true` du `On(...)`. Le gate generique
        # (`dispatch/core.evaluate_trigger_operation` -> `CanGetAbilityTrigger`) le porte deja ;
        # celui-ci le rend explicite sur un etat SEEDE mi-tour, ou le vecteur peut arriver sans que
        # le dispatch ait revalide la vivacite.
        ow = state.get_entity(self.owner_id)
        uc = ow.get_component(UnitComponent) if ow is not None else None
        return uc is None or bool(uc.alive)

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        entities = entities_from_state(state, int(self.owner_id), actor_id=int(self.owner_id))
        ectx = ExecutionContext(state=state, rng=state.rng)
        call_in_reinforcements_tree().execute(entities, ectx)
        spawned = [p for n, p in ectx.emitted if n == "SpawnUnit"]
        acted = [p for n, p in ectx.emitted if n == "PerformAIAttack"]
        if not spawned:
            return None
        return {"passive": ABILITY_ID, "owner": int(self.owner_id),
                "spawned": [p.get("unit") for p in spawned],
                "tiles": [p.get("tile") for p in spawned],
                "ai_actions": len(acted), "dsl": True}
