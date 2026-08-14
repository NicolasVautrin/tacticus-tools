"""Turn flow — EndTurn -> ChangeTurn -> StartTurn (RE fidele, cf. docs/rl/runner-engine.md §2.6).

Operations natives (VA citees) :
  - `IdunBattle.Operations.EndTurnOperation$$Execute  : fin de tour du joueur courant. ORDRE des
    etapes tel qu'il se lit dans le corps (case-n8b) :
      1. per-unite (equipe du joueur finissant) : `turnsFinished@+0x5c += 1` (`_bump_turns_finished`),
        `IdunBattle.Operations.EndTurnOperation$$ResetAbilitiesThatResetOnTurnEnd +
        `IdunBattle.Operations.EndTurnOperation$$DecreaseAbilityCooldowns.
      2. toutes unites : `IdunBattle.Operations.EndTurnOperation$$RemoveOneTurnOnShields + `ActorStatisticsComponent.ResetThisTurn`.
      3. meme `+0x5c += 1` sur la Machine of War du joueur (`PlayerComponent+0x78`).
      4. si `IdunBattle.Entities.Components.TurnComponent$$HasActivePlayer : le vecteur de triggers
        `On(0x17 = TurnEnd)` (`end_turn_summon_triggers`).
      5. `IdunBattle.Operations.EndTurnOperation$$RefreshEffects : tick d'1 tour des effets a duree de TOUTES les unites —
        **APRES le vecteur `On(0x17)`**, jamais avant (le port faisait l'inverse jusqu'a case-n8b).
      * si `advance` (param_2) : enqueue le changement de tour (ChangeTurn) puis StartTurn.
  - `IdunBattle.Operations.ChangeTurnOperation$$Execute  : `current = IdunBattle.Operations.ChangeTurnOperation$$FindNextPlayer ;
      `IdunBattle.Entities.Components.TurnComponent$$SetCurrentPlayer ; si le nouveau joueur est de type 2 (neutre) -> recurse (skip).
      C'est LA que vivent les deux compteurs PAR JOUEUR (`+0x38` demarres, `+0x40` termines) :
      `SetCurrentPlayer` en est l'ecrivain UNIQUE, et `ChangeTurnOperation$$Execute` son SEUL
      appelant. Le port y bumpe les DEUX -- `state.turns_ended` (#287-r11-r1-r1-r1) ET
      `state.turn_counts` (#287-r11-r1-r1-r1-r1), cf. `set_current_player`.
  - `IdunBattle.Operations.StartTurnOperation$$Execute  : resets per-unite (ActorStatistics/UnitFlags) +
      emet la sequence d'events de debut de tour 0x12/0x13/0x14/0x15/0x16 (`On(0x16)` = vecteur
      turn-start porte = `start_turn_triggers`).

PORTE ICI (tranche TF-A) — l'etat OBSERVABLE suivi par le runner (current_player, compteur de tours,
durees d'effet, triggers de debut de tour) :
  * RefreshEffects  -> `EffectsState.on_turn_end` (deja porte : decremente remaining_turns -> expiration
                       + cascade composite), applique a TOUTES les unites a effets, en DERNIER (apres
                       le vecteur `On(0x17)`). Il n'inflige AUCUN degat : le natif y fait
                       `IdunBattle.Entities.Components.EffectComponent$$RemoveOneTurn + events, puis
                       `Core.Services.OperationProcessor$$RefreshEffects ->
                       `IdunBattle.Operations.RefreshEffectsOperation$$Execute (branche de retrait).
  * IdunBattle.Operations.EndTurnOperation$$RemoveOneTurnOnShields -> `ShieldComponent.remove_one_turn` (decay d'1 tour des boucliers
                       a duree de TOUTES les unites ; retire les instances a 0).
  * EndTurn         -> `turnsFinished@+0x5c += 1` PER-UNITE du joueur FINISSANT (`_bump_turns_finished`),
                       AVANT le vecteur `On(0x17)` (gate `OwnerHasFinishedMinTurns` de PileIn).
  * ChangeTurn      -> `find_next_player` : QUATRE etages natifs SEPARES (#462-r4e-o-r2-r1-r1-r1) —
                       l'ORDRE vient de la config (`player_turn_order` = `BC.Player.TurnOrder`, slot
                       `IBattleQuery` 0x18), l'INDEX du courant s'y cherche sans filtre
                       (`find_turn_index`), et le SKIP (`should_player_skip_turn`, slot 0x1a) est
                       evalue DANS la boucle bornee. L'Environment fait partie de l'ordre ; c'est la
                       RECURSION d'`Execute` qui l'ecarte (non portee, cf. `ChangeTurnOperation`).
  * StartTurn       -> `turnsStarted@+0x58 += 1` PER-UNITE du joueur courant (stat 12,
                       `_bump_turns_started`, mig #123) + `start_turn_triggers(player)`.
                       ⚠ IL N'INCREMENTE **PAS** `state.turn_counts` (#287-r11-r1-r1-r1-r1) :
                       `IdunBattle.Operations.StartTurnOperation$$Execute` ne fait que LIRE
                       `GetAmountOfTurnsStartedByCurrentPlayer`. L'unique ecrivain de `+0x38` (et de
                       `+0x40`) est `TurnComponent$$SetCurrentPlayer`, donc ChangeTurn -- les DEUX
                       dicts y sont desormais bumpes, cf. `set_current_player`.

DEFERE (etat NON suivi offline -> TODO, en miroir documente) :
  * `DecreaseAbilityCooldowns` (le runner ne suit pas de compteur de cooldown d'ability offline) ;
  * `ActorStatisticsComponent.ResetThisTurn` : SEUL le volet TUILES est porte (case-322-r1,
    `reset_tiles_moved_this_turn` -> `+0xf0 = 0` partout, `+0xf4 = +0xf0` si `wasOwnTurn`) ; les
    autres roulements de ce reset (0x78/0x7c, 0xe4/0xe8, 0x58/0x5c, 0xa0/0xa4, dict par-entite)
    portent des stats per-tour non suivies offline (attaques recues/portees...) ;
  * `ResetAbilitiesThatResetOnTurnEnd` ; resets per-unite UnitFlags de StartTurn ;
  * `PickNextUnit` (ordre intra-tour = DECISION de l'IA, pas une mutation moteur -> couche playbook).
"""
from __future__ import annotations

from typing import Optional

from ..state import State
from ..components import (OwnerComponent, UnitComponent, ShieldComponent, StatsComponent,
                          UnitFlagsComponent, PositionComponent, reset_tiles_moved_this_turn,
                          is_machine_of_war, ActiveAbilitiesComponent)
from ...entities.stats import StatType
from .triggers.dispatch.turn import (
    delayed_attack_triggers, start_turn_triggers, tile_tick_triggers, turn_start_other_triggers
)
from .triggers.tiles import first_aid_heal
# #270-r4-r2 : les SIX imports de ce fichier qui etaient DIFFERES sont HISSES. Aucun ne brise
# de cycle -- mesure `probe_270r4r2_import_en_premier.py`, depuis 8 ordres d'entree distincts
# (un cycle ne se voit que dans UN sens, un seul ordre ne prouverait rien). Le seul motif qui
# restait etait le COUT (276 -> 341 modules `engine` charges), et ce n'en est pas un : un import
# differe deplace l'echec vers le premier appel et rend l'ordre d'initialisation dependant du
# chemin d'execution. Le cout d'import, lui, se paie une fois.
from ...entities.traits.unit_trait import UnitTrait, has_trait
# #287-r11-r1-r1-r1 -- FORME B (module, pas symbole) : `player_turn_order` DELEGUE a son foyer natif
# (`BattleQuery$$GetPlayerTurnOrder`). Un `from ... import get_player_turn_order` gelerait la liaison
# et NE MORDRAIT PAS sous `monkeypatch.setattr("engine.services.battle_query.get_player_turn_order")`.
# Aucun cycle : `services.battle_query` est deja dans la cascade de ce module (via `abilities.targeting`
# juste en dessous), et il ne remonte vers le runner que par un differe INTERNE a sa fonction.
from ...services import battle_query as _sbq
from ..abilities.targeting import (valid_normal_attack_targets, normal_attack_type_for,
                                   get_invalid_target_reason, get_invalid_caster_reason,
                                   targeting_options_for, UnportedAbilityTargeting)
from ..abilities.handler import ABILITY_CLASSES
from .repair import _is_boss
from ...ai.state_bridge import _move_tiles
import engine.runner.operations.effects as _ops_effects   # FORME B (#547-r2), et ABSOLUE : le
# MODULE, pas le paquet parent (`from . import effects` declarerait une arete vers
# `engine.runner.operations` et c'est ainsi qu'un SCC se referme -- mesure
# `test_270r4r2_cycles_imports_offline`), pas le symbole (un `monkeypatch.setattr(
# "engine.runner.operations.effects.<x>", ...)` doit mordre). `.effects` est deja au preambule
# (ligne suivante), donc l'arete existe : ni cycle, ni cout.
from .effects import revert_stat_mods_of_removed_effects
from .traits import revert_traits_of_removed_effects
from .refresh_effects import RefreshEffectTrigger, refresh_stat_modifier_effects
from .summon_ai import run_ai_control_pass
from .triggers.dispatch.turn import end_turn_summon_triggers
from .triggers.dispatch.turn import unit_finished_turn_triggers
from .triggers.dispatch.move_death import arrived_at_final_tile_triggers
from .triggers.dispatch.turn import unit_finished_turn_normally_triggers


class MarkUnitAsNoActionAvailableOperation:
    """`IdunBattle.Operations.MarkUnitAsNoActionAvailableOperation$$Execute(unit, reverse)` (#287-r1)
    — le FOYER UNIQUE de `UnitFlag.NoActionAvailable` (4). MIRROR du decompile :

        if (unit == null) return
        comp = unit.GetComponent<UnitFlagsComponent>()          # TryGetComponent -> null => return
        if (comp == null) return
        if (!reverse) { if (!comp.Add(UnitFlag.NoActionAvailable)) return }
        else          { if (!comp.Remove(UnitFlag.NoActionAvailable)) return }
        Events.Publish(0xc, entityId(unit),
                       { TagKey.UnitStats_ActionsAvailable (0x6f) : reverse ? 1 : 0 })

    `Add` / `Remove` rendent « la mutation a MORDU » (`UnitFlagsComponent$$Add` = `Contains ?
    false : (Add, true)`) : l'event n'est publie QUE si le flag a reellement change. Le port ne
    suit pas la couche stream (comme le reste des Operations) — la cle est CITEE, pas emise.

    DEUX ENTREES natives, qui different par `reverse` :
      * `Core.Services.OperationProcessor$$MarkUnitAsNoActionAvailable` (slot `IOperationProcessor`
        0x76) -> `reverse = false` : POSE le flag ;
      * `Core.Services.OperationProcessor$$MarkUnitAsActionAvailable`   (slot 0x77)
        -> `reverse = true`  : le RETIRE.
    Le couple est identifie sans ambiguite : `FinishUnitTurnOperation$$Execute` termine par le
    slot 0x76, et la branche `Has(4)` de `VerifyUnitsTurnFinishedOperation$$VerifyUnitTurnEnded`
    (« l'unite a REGAGNE des options ») appelle le 0x77.

    LES CINQ PORTEURS du slot 0x76, recenses par SCAN BINAIRE
    (`scripts/python/probe_287r1_no_action_available.py`, etape 3) :
    `FinishUnitTurnOperation$$Execute` (queue, INCONDITIONNEL — c'est CE site que le port
    mirrore), `ActiveAbilityOperation$$ExecuteInternal` (`if (!skipEndTurn)`, AVANT le corps de
    l'ability), et les trois `VerifyUnitsTurnFinishedOperation$${Execute, VerifyUnitTurnEnded,
    VerifyMachineTurnEnded}`.

    LE RETRAIT (`reverse = true`) A SON APPELANT DEPUIS #287-r1-r1 :
    `VerifyUnitsTurnFinishedOperation.verify_unit_turn_ended` (plus bas dans ce module), branchee
    dans `Runner.apply` a l'ancrage LU — `IdunBattle.Messages.InputMessageProcessor$$RunPhase`
    invoque le slot `IOperationProcessor` 0x21 = `Core.Services.OperationProcessor$$
    VerifyUnitsTurnFinished` (AUCUN argument — c'est ce qui l'identifie parmi ses voisins `0x22` a
    un argument et `0x23` a deux) en phase NON interne. C'est la SEULE voie native de retrait, et
    elle est load-bearing : `RemoveTurnFlags(includeNoAction: 0)` CONSERVE le flag au changement de
    tour, donc sans elle une unite marquee une fois le resterait pour toujours.
    Mesure (`probe_287r1r1_verify_turn_ended.py`) : POSE `live=[0,1,4]`/`port=[0,1,4]`, RETRAIT
    `live=[]`/`port=[]`."""
    __slots__ = ()

    @staticmethod
    def execute(state: State, unit_id: int, reverse: bool = False) -> dict:
        e = state.get_entity(int(unit_id))
        if e is None:
            return {"unit": int(unit_id), "found": False, "changed": False}
        fl = e.get_component(UnitFlagsComponent)
        if fl is None:
            # Mirror STRICT : le natif `TryGetComponent` -> composant absent = retour immediat,
            # il n'en CREE pas. Toute unite native en porte un ; offline, une entite sans
            # `UnitFlagsComponent` est une capture partielle, pas une unite a marquer.
            return {"unit": int(unit_id), "found": False, "changed": False}
        present = fl.has(UnitFlagsComponent.NO_ACTION_AVAILABLE)
        if reverse:
            changed = present
            fl.remove(UnitFlagsComponent.NO_ACTION_AVAILABLE)
        else:
            changed = not present
            fl.add(UnitFlagsComponent.NO_ACTION_AVAILABLE)
        # `changed` = ce que rend `Add`/`Remove` natif, et le gate de l'event de stream
        # (`TagKey.UnitStats_ActionsAvailable` = `reverse ? 1 : 0`). Rendu pour le diagnostic.
        return {"unit": int(unit_id), "found": True, "changed": bool(changed),
                "reverse": bool(reverse)}


class FinishUnitTurnOperation:
    """`IdunBattle.Operations.FinishUnitTurnOperation$$Execute (#139) — clot le tour d'UNE unite :
      * si `forced` : Add(UnitFlag 27 = TURN_FINISHED_FORCED) ;
      * Add(ArrivedAtFinalTile=1) — si nouvellement pose et !forced, le natif publie l'event 0x1c ;
      * Add(TurnFinished=3)       — si nouvellement pose, events 0x29 (+0x2a si !forced) + step Events(0xd) ;
      * reset du cache de mouvement (MovementComponent@+0x18/+0x10) puis, en DERNIERE instruction,
        le slot processor 0x76 = `Core.Services.OperationProcessor$$MarkUnitAsNoActionAvailable`
        -> `UnitFlag.NoActionAvailable` (4). PORTE depuis #287-r1 (la citation « (Verify...) » qui
        etait ici nommait la MAUVAISE fonction : 0x76 pose le flag, il ne verifie rien).
      * **`UnitComponent.ChargedUnitIds` (+0x190) VIDEE** — le decompile termine par un
        `TryGetComponent<UnitComponent>` suivi d'un `List<T>.Clear()` INLINE sur le champ @+0x190
        (`_version++`, `_size = 0`, `Array.Clear(_items, 0, size)`). C'est CE site qui donne au
        predicat `IdunBattle.Core.Services.BattleQuery$$IsCharging` sa portee « CE TOUR » : la liste
        est remplie par les moves de l'activation et remise a zero quand elle se termine.
    OFFLINE on porte la MUTATION (les 3 flags + `NoActionAvailable` + la purge des charges) ;
    events/steps de stream = couche view/process non suivie (documente). Declencheurs natifs :
    `Core.Services.OperationProcessor$$FinishUnitTurn (appele par
    `IdunBattle.Operations.ActiveAbilityOperation$$AddFlagsAfterAbilityExecution quand l'ability TERMINE le tour),
    `FinishUnitTurnMessage`, et `FinishUnitTurnBehaviour` IdunBattle.Entities.Behaviours.FinishUnitTurnBehaviour$$Execute (DSL)."""
    __slots__ = ()

    @staticmethod
    def execute(state: State, unit_id: int, forced: bool = False) -> dict:
        e = state.get_entity(unit_id)
        if e is None:
            return {"unit": int(unit_id), "found": False}
        uc = e.get_component(UnitComponent)
        if uc is not None:
            uc.charged_unit_ids = []          # `List.Clear()` inline sur UnitComponent+0x190
        fl = e.get_component(UnitFlagsComponent)
        if fl is None:
            fl = e.add_component(UnitFlagsComponent())
        if forced:
            fl.add(UnitFlagsComponent.TURN_FINISHED_FORCED)
        newly_arrived = not fl.has(UnitFlagsComponent.ARRIVED_AT_FINAL_TILE)
        fl.add(UnitFlagsComponent.ARRIVED_AT_FINAL_TILE)
        newly_finished = not fl.has(UnitFlagsComponent.TURN_FINISHED)
        fl.add(UnitFlagsComponent.TURN_FINISHED)
        out = {"unit": int(unit_id), "found": True, "forced": bool(forced),
               "newly_arrived": newly_arrived, "newly_finished": newly_finished}
        # `Add(ArrivedAtFinalTile=1)` nouvellement pose ET `!forced` -> le natif PUBLIE `On(0x1c)`.
        # C'est la branche << l'unite n'a PAS bouge >> (si elle avait bouge, `MoveUnitOperation` aurait
        # deja pose le flag ET emis l'event -- vecteur `after_move_triggers`). Le gate par flag est
        # DANS `arrived_at_final_tile_triggers` (idempotent) : on ne l'appelle que sur `not forced`.
        # Consommateurs : `SpiritualLeaderAbility` (passif genesMagus) et `ArcaneShieldAbility` (passif
        # thousSorcerer -- c'est PAR ICI que Thaumachus obtient son bouclier quand il ne bouge pas).
        # No-op si personne n'ecoute.
        if newly_arrived and not forced:
            out["arrived_triggers"] = arrived_at_final_tile_triggers(
                state, int(unit_id), gate_already_consumed=True)
        # `Add(TurnFinished=3)` nouvellement pose -> le natif publie `On(0x28 = UnitFinishedTurn)`
        # PUIS, si `!isTerminated`, `On(0x29 = UnitFinishedTurnNormally)`. Les DEUX gates sont ceux du
        # decompile (#354) ; l'ordre relatif a `On(0x1c)` (au-dessus) est celui du natif.
        # `On(0x28 = UnitFinishedTurn)` est EMIS depuis #448-r2 (consommateur : le 3e trigger
        # d'`ATeleportingEffect` = l'atterrissage deep-strike d'une unite qui clot son tour sans avoir
        # agi) -- et il l'est MEME sur `forced`, seul `On(0x29 = UnitFinishedTurnNormally)` portant le
        # gate `!isTerminated`.
        # Consommateur de `On(0x29 = UnitFinishedTurnNormally)` : `MyWillBeDoneOverlordAttackAbility`
        # (passif `necroOverlord`).
        if newly_finished:
            out["finished_triggers"] = unit_finished_turn_triggers(state, int(unit_id))
        if newly_finished and not forced:
            out["finished_normally_triggers"] = unit_finished_turn_normally_triggers(
                state, int(unit_id))
        # #287-r1 -- DERNIERE instruction du corps natif, INCONDITIONNELLE (aucun gate `forced`,
        # aucun gate `newly_*`) : `<IOperationProcessor slot 0x76>(unit)` =
        # `Core.Services.OperationProcessor$$MarkUnitAsNoActionAvailable`. Elle vient APRES le
        # vidage de `UnitComponent.ChargedUnitIds` -- l'ordre est celui du decompile.
        # Ce que ca ferme, MESURE : `probe_287_facade_combat.py` lisait `[1, 2, 3, 4]` cote natif
        # et `[1, 2, 3]` cote port sur le caster d'un cast. Le flag est ce que lit
        # `IdunBattle.Entities.UnitExtensions$$HasActionLeft` (et donc
        # `AnAiGroupOperator$$GetValidUnits`, deja mirroree par `summon_ai.has_action_left`).
        out["no_action"] = MarkUnitAsNoActionAvailableOperation.execute(state, int(unit_id))
        return out


def add_flags_after_ability_execution(state: State, caster_id: int,
                                      skip_ability_used: bool, skip_end_turn: bool) -> dict:
    """`IdunBattle.Operations.ActiveAbilityOperation$$AddFlagsAfterAbilityExecution (#139) — queue d'`IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal apres TOUTE execution d'ability active (attaque normale incluse : c'est une ability) :
      * `!skip_ability_used` -> UnitFlags.Add(ActiveAbilityUsed=2) ;
      * `!skip_end_turn`     -> `Core.Services.OperationProcessor$$FinishUnitTurn(caster, false)
                                -> `FinishUnitTurnOperation` (flags 1+3).
    Les deux skips viennent de `IdunBattle.Operations.ActiveAbilityOperation$$GetSkipAbilityUsedFlag / `IdunBattle.Operations.ActiveAbilityOperation$$GetSkipEndTurnFlag =
    `options.skip*Flag || !ability.Sets*().Evaluate(entities)` (cf. abilities/base.py)."""
    e = state.get_entity(caster_id)
    if e is None:
        return {"caster": int(caster_id), "found": False}
    out: dict = {"caster": int(caster_id), "found": True,
                 "ability_used_flag": not skip_ability_used, "turn_finished": not skip_end_turn}
    if not skip_ability_used:
        fl = e.get_component(UnitFlagsComponent)
        if fl is None:
            fl = e.add_component(UnitFlagsComponent())
        fl.add(UnitFlagsComponent.ACTIVE_ABILITY_USED)
    if not skip_end_turn:
        out["finish"] = FinishUnitTurnOperation.execute(state, caster_id, forced=False)
    return out


def player_turn_order(state: State) -> list[int]:
    """`IdunBattle.Core.Services.BattleQuery$$GetPlayerTurnOrder` = le slot `IBattleQuery` **0x18**
    (arite **0**, lu dans `data/symbols/<build>/metadata/interface_slots.tsv` -- un NOM designe un
    ENSEMBLE de slots, c'est le couple nom+arite qui l'identifie). Son corps est un pur accesseur de
    CONFIG :

        return this.<+0xa0 : BattleConfiguration>.<+0x30>.<+0x18>      # IList<PlayerId>

    soit, cote BC, **`BC.Player.TurnOrder`** -- que le seed porte a `[11, 12, 13]`, c'est-a-dire les
    ids des trois entrees de `BC.Player.Players` : `player` (PlayerType 0), `enemy_1` (1) et
    **`Environment` (2)**. L'ORDRE DE TOUR CONTIENT DONC L'ENVIRONMENT ; ce n'est pas
    `FindNextPlayer` qui l'ecarte, c'est la RECURSION d'`Execute` (cf. `ChangeTurnOperation`).

    ⚠ STAND-IN NOMME, et sa portee est bornee. Le port ne recoit NI la liste `TurnOrder` NI la table
    `PlayerId -> BEntityId` : `decisionView` ne publie que `units[].owner`, un **BEntityId** de
    joueur. L'ordre est donc RECONSTRUIT par les ids d'entite CROISSANTS des joueurs porteurs
    d'unites. Les deux coincident sur le seed BC (`TurnOrder` trie par `PlayerId`, entites joueur
    creees dans cet ordre -- MESURE du 2026-08-06 : joueurs `3` et `4`, `observeBattle.counts.player`
    = 3), et rien ne le garantit pour une BC dont le `TurnOrder` ne serait pas trie. Residu
    `#462-r4e-o-r2-r1-r1-r1-r1` : le publier demanderait un capteur sur `GetPlayerTurnOrder`.

    ⚠ LE FILTRE `alive` A DISPARU, ET C'EST LE CORRECTIF. `TurnOrder` est une donnee de
    CONFIGURATION : un joueur n'en sort JAMAIS, meme toutes ses unites mortes. L'ancien port le
    retirait de l'ordre, ce qui melangeait deux etages natifs distincts -- l'ORDRE (config) et le
    SKIP (`ShouldPlayerSkipTurn`, evalue DANS la boucle). La difference se voit des que le joueur
    COURANT est celui qui n'a plus d'unite : l'ancien port ne le trouvait plus dans l'ordre et
    repartait de `order[0]`, la ou `FindTurnIndex` -- qui ne consulte AUCUN skip -- le trouve et
    avance depuis SA position.

    ⚠ LE CORPS A DEMENAGE (#287-r11-r1-r1-r1), ET LA RAISON EST UN SECOND LECTEUR.
    `GetPlayerTurnOrder` est une methode de `BattleQuery`, et `BattleQuery$$HasMinimumRemainingTurns`
    l'appelle (`GetAmountOfTurnsEndedByPlayer(GetPlayerTurnOrder()[0])`). Le corps vit donc desormais
    dans `engine.services.battle_query.get_player_turn_order`, son foyer NATIF, et cette fonction-ci
    y DELEGUE : deux stand-ins qui derivent auraient ete un bug silencieux -- l'un dans l'ordre de
    tour, l'autre dans le plafond de rounds."""
    return _sbq.get_player_turn_order(state)


def find_turn_index(state: State, player: Optional[int]) -> Optional[int]:
    """`IdunBattle.Operations.ChangeTurnOperation$$FindTurnIndex(playerEntityId)`, MIRROR du
    decompile (le corps est aussi INLINE dans `FindNextPlayer`, a l'identique) :

        if (playerEntityId == 0)                      return null
        order  = query.GetPlayerTurnOrder()
        player = state.<slot 0x29 = GetEntity>(playerEntityId)
        pc     = player.GetPlayerComponent()          # throw si absent
        for (i = 0 ; i < order.Count ; i++)
            if (order[i] == pc.<+0x10 : PlayerId>)    return i
        return null                                   # Nullable<int> SANS valeur

    Rend un `Optional[int]` -- le `Nullable<int>` natif -- et **jamais** un `-1` : c'est
    l'APPELANT qui rabat l'absence sur `-1` (cf. `find_next_player`), et les deux ne se confondent
    pas (un `-1` rendu ici entrerait dans un `%` comme un index valide).

    ⚠ AUCUN filtre de skip ici : `FindTurnIndex` cherche la POSITION du joueur courant dans l'ordre
    de configuration, que ce joueur soit jouable ou non."""
    if player is None or int(player) == 0:
        return None
    order = player_turn_order(state)
    for i, pid in enumerate(order):
        if int(pid) == int(player):
            return i
    return None


def should_player_skip_turn(state: State, player: int) -> bool:
    """`IdunBattle.Core.Services.IBattleQuery.ShouldPlayerSkipTurn` = le slot **0x1a** (arite **1**),
    le predicat de SKIP de la boucle de `FindNextPlayer`.

    ⚠ NON PORTE, ET NOMME PLUTOT QUE DEVINE. `IdunBattle.Core.Services.BattleQuery$$ShouldPlayerSkipTurn`
    n'a **aucun corps propre** dans le binaire : il est absent de `ghidra/functions.tsv` (voisins
    immediats en adresse : `BattleQuery$$ShouldIgnoreSpecialMovementInDangerZone` puis
    `BattleQuery$$u003CGetBestWeaponu003Eb__316_0`) **et** de `frida/methods.tsv` -- signature d'un
    corps TRIVIAL dedupplique par IL2CPP. On ne conclut donc RIEN de cette absence (cf. CLAUDE.md,
    << l'absence d'une methode dans les tables ne prouve rien >>) : le predicat reste ILLISIBLE. Seul
    le decorateur `IdunBattle.Core.Services.RecordedSimulationRequestsBattleQuery$$ShouldPlayerSkipTurn`
    est lisible, et il ne fait que RELAYER le slot 0x1a de son `inner`.

    Ce qui est ecrit ici est donc un STAND-IN : << un joueur dont aucune unite n'est vivante ne joue
    pas >>. C'est ce que l'ancien `_active_players` faisait DEJA, mais en amont et en silence ; le
    changement est qu'il est desormais A SA PLACE NATIVE (predicat de la boucle) et DECLARE.
    Direction du residu : si le natif skippait AUSSI pour une autre raison, le port ferait jouer un
    joueur que le natif saute -- jamais l'inverse. Residu `#462-r4e-o-r2-r1-r1-r1-r2` ; point
    d'ancrage a hooker : le slot 0x1a de l'`IBattleQuery` du runner.

    Le second usage natif du meme slot le confirme comme un predicat de JOUABILITE, et montre qu'il
    est DISTINCT du test d'Environment -- `IdunBattle.Entities.Formulas.TurnsUntilUnitOwnerTurnFormula$$GetTurnsUntilUnitOwnerTurn`
    compte les tours intercalaires avec les DEUX gardes cote a cote :

        if (pc.<+0x20 : PlayerType> != 2)  &&  !query.ShouldPlayerSkipTurn(p)   ->  count++
    """
    for e in state.entities.values():
        oc = e.get_component(OwnerComponent)
        if oc is None or oc.player is None or int(oc.player) != int(player):
            continue
        uc = e.get_component(UnitComponent)
        if uc is None or uc.alive:
            return False                   # au moins une unite jouable -> le joueur n'est pas saute
    return True


def find_next_player(state: State) -> Optional[int]:
    """`IdunBattle.Operations.ChangeTurnOperation$$FindNextPlayer(matchEntity)`, MIRROR du
    decompile :

        if (StateExtensions.IsMatchFinished(state))            return null
        turn    = matchEntity.GetComponent<TurnComponent>()
        players = matchEntity.<IMatchEntity>.<+0x10 : List<...>>          # la BORNE de la boucle
        current = turn.get_CurrentPlayerId()                              # BEntityId
        order   = query.GetPlayerTurnOrder()                              # slot 0x18, arite 0
        index   = FindTurnIndex(current)                                  # INLINE, a l'identique
        i = (index.HasValue ? index.Value : -1)
        for (offset = 1 ; offset <= players.Count ; offset++) {
            pid    = order[(i + offset) % order.Count]
            player = StateExtensions.GetPlayer(state, pid)
            if (!query.ShouldPlayerSkipTurn(player))           break      # slot 0x1a, arite 1
        }
        if (offset > players.Count)                            return null
        return player.Id

    QUATRE etages, tous LUS, et c'est leur SEPARATION qui est le correctif -- l'ancien port les
    avait fondus dans un unique << cycle sur les joueurs a unites vivantes, tries >> :

      1. l'ORDRE vient de la CONFIG (`player_turn_order`), pas de qui est vivant ;
      2. l'INDEX du courant se cherche dans cet ordre COMPLET (`find_turn_index`), sans skip ;
      3. l'absence d'index vaut **-1**, donc le premier candidat est `order[0]` ;
      4. le SKIP (`should_player_skip_turn`) est evalue DANS la boucle, candidat par candidat, et
         la boucle est BORNEE : tous skippes -> `None` (le natif ne boucle pas indefiniment).

    ⚠ `IsMatchFinished` n'est PAS porte (le port n'a pas de substrat de condition de victoire) : la
    fonction rend donc un joueur la ou le natif aurait rendu `null` sur un match deja fini. Sans
    consequence sur le runner, dont `Runner.apply` n'appelle plus rien apres la fin de match.

    ⚠ CE QUI A ETE MESURE, ET CE QUI NE L'A PAS ETE (2026-08-06, seed 777 / MC1_67, montage
    `astraBullgryn,tauAunShi` vs `genesPrimus,necroWarden`) : la suite native des `currentPlayer` sur
    14 changements de tour est une ALTERNANCE STRICTE `[3, 4, 3, 4, ...]`, et elle le reste apres la
    mort d'une unite (le decoy `Ambush` reste possede par le SUMMONER, pas par l'Environment). Les
    quatre etages ci-dessus ne se separent donc PAS dans le regime confrontable a deux camps : ils
    n'y sont exerces qu'OFFLINE (>= 3 joueurs, joueur entierement mort, joueur courant hors ordre --
    cf. `tests/engine/runner/test_462r4eor2r1r1r1_cycle_de_tour_offline.py`)."""
    order = player_turn_order(state)
    if not order:
        return None
    n = len(order)
    idx = find_turn_index(state, state.current_player_id)
    i = idx if idx is not None else -1          # `Nullable<int>` sans valeur -> -1 (LU)
    # BORNE native = `players.Count`, le nombre de joueurs du match. Le port ne connait que les
    # joueurs de l'ordre de tour, donc `n` : les deux valent 3 dans toute BC du runner (seed BC :
    # `Players` = 11/12/13, `TurnOrder` = [11, 12, 13]), et `n` est la borne PRUDENTE (elle ne peut
    # que sous-estimer le nombre de tentatives, jamais boucler plus que le natif).
    for offset in range(1, n + 1):
        pid = int(order[(i + offset) % n])
        if not should_player_skip_turn(state, pid):
            return pid
    return None                                 # tous skippes -> le natif rend `null`


def set_current_player(state: State, next_player_id: int) -> None:
    """`IdunBattle.Entities.Components.TurnComponent$$SetCurrentPlayer(nextPlayerId)` -- MIRROR du
    decompile, VERBATIM et dans cet ordre :

        if (get_CurrentPlayerId() == nextPlayerId)            return;          # NO-OP
        if (!started.ContainsKey(nextPlayerId))               started.Add(nextPlayerId, 0);
        if (get_CurrentPlayerId() != 0) {
            if (!ended.ContainsKey(CurrentPlayerId))          ended.Add(CurrentPlayerId, 0);
            ended[CurrentPlayerId] = ended[CurrentPlayerId] + 1;
        }
        prev = get_CurrentPlayerId();
        this.<+0x24 : currentPlayerId>  = nextPlayerId;
        this.<+0x18 : previousPlayerId> = prev;
        started[get_CurrentPlayerId()] = started[get_CurrentPlayerId()] + 1;

    (`started` = `<Dictionary @+0x38>`, `ended` = `<Dictionary @+0x40>` ;
    `get_CurrentPlayerId` = `tempPlayer.HasValue ? tempPlayer.Value : <+0x24>`.)

    ⚠ C'EST L'ECRIVAIN **UNIQUE** DES DEUX DICTIONNAIRES, et c'est ce fait -- pas une formule -- qui
    a debloque le residu `#287-r11-r1-r1-r1`. Verifie sur les **19** methodes de `TurnComponent` :
    `.ctor` les construit VIDES, `Copy` les clone, aucune autre ne les touche (`BlockTurnChange` /
    `UnblockTurnChange` ecrivent `+0x30`, `SetTempChangeToPlayer` / `ResetTempPlayerTurn` `+0x28`,
    `GetNextTurnStage` lit `+0x10/+0x14`). Et il n'a qu'UN SEUL appelant,
    `IdunBattle.Operations.ChangeTurnOperation$$Execute` (xrefs). Corollaire LU, jamais ajuste :
    a tout instant, `ended[p] == started[p] - (p == CurrentPlayerId ? 1 : 0)` -- c'est l'identite que
    `snapshot._load_turns_ended` utilise pour SEEDER, et elle tient meme sous joueur TEMPORAIRE
    (`ended[temp]` et `started[temp]` sont bumpes ensemble).

    ⚠ LES **DEUX** DICTIONNAIRES SONT BUMPES ICI DEPUIS #287-r11-r1-r1-r1-r1, ET C'EST LA FIN DU
    PLACEMENT HERITE. `state.turn_counts` (`+0x38`) vivait dans `StartTurnOperation.execute` --
    placement d'origine, MESURE comme faux : le decompile de
    `IdunBattle.Operations.StartTurnOperation$$Execute` ne fait que LIRE
    `GetAmountOfTurnsStartedByCurrentPlayer` (compare a `1`), il n'ecrit JAMAIS `+0x38`. Les deux
    sites etaient ENCHAINES par `advance_turn` (`ChangeTurn` puis `StartTurn`), donc l'etat
    observable apres la paire etait le meme -- SAUF sur le NO-OP (`cur == next`, seul joueur encore
    jouable), ou le natif ne bumpe RIEN et le port comptait un tour de plus pour lui (direction :
    le port SUR-comptait `turn_counts` dans ce seul regime).

    ⚠ CE QUE LE DEPLACEMENT CHANGE POUR LES APPELANTS DE `StartTurnOperation.execute` SEUL (8 sites,
    tous des probes -- `probe_213_ghost_revive`, `probe_227_remove_unit_operation` x2,
    `probe_366r1_echoes_revive`, `probe_cvc_contagions_lifecycle`, `probe_lot_pose` x3) : leur appel
    ne fait plus avancer `turn_counts`. Mesure du 2026-08-07 : **aucun des cinq fichiers** ne
    mentionne `turn_counts`, `PlayerTurnsStarted`, `turn_defeated`, `SereneUnifier` ni `Ambush` --
    les DEUX seuls consommateurs portes de ce dict. Ils appellent l'operation pour ce qu'elle FAIT
    vraiment (resets per-unite, `turnsStarted@+0x58`, vecteurs turn-start), pas pour le compteur.
    Un appelant qui voudrait VRAIMENT avancer d'un tour joue desormais la PAIRE
    (`set_current_player` ou `ChangeTurnOperation.execute`, puis `StartTurnOperation.execute`) --
    ce qui est aussi ce que fait le natif."""
    cur = state.current_player_id
    if cur is not None and int(cur) == int(next_player_id):
        return                                    # `if (cur == next) return;` -- AUCUN bump
    if cur is not None and int(cur) != 0:         # `if (get_CurrentPlayerId() != 0)`
        state.turns_ended[int(cur)] = int(state.turns_ended.get(int(cur), 0)) + 1
    state.current_player_id = next_player_id      # `this.<+0x24> = nextPlayerId`
    # `started[get_CurrentPlayerId()] = started[get_CurrentPlayerId()] + 1` -- DERNIERE instruction
    # du corps natif, et INCONDITIONNELLE : le gate `!= 0` ne porte QUE sur `ended`. A ce point
    # `get_CurrentPlayerId()` vaut deja `nextPlayerId` (la ligne au-dessus), donc c'est l'ENTRANT
    # qui est bumpe. Le `if (!started.ContainsKey(next)) started.Add(next, 0)` de tete de corps est
    # absorbe par le `.get(..., 0)` : il ne sert, natif, qu'a rendre l'indexeur non levant.
    state.turn_counts[int(next_player_id)] = int(state.turn_counts.get(int(next_player_id), 0)) + 1


class ChangeTurnOperation:
    """`IdunBattle.Operations.ChangeTurnOperation$$Execute()`, MIRROR du decompile :

        next = FindNextPlayer(matchEntity) ; if (next == 0)          return
        prev = turn.get_CurrentPlayerId()
        turn.SetCurrentPlayer(next)                                   # NO-OP si next == prev
        if (state.GetEntity(next).GetPlayerComponent().<+0x20 : PlayerType> == 2) {
            Execute(this)                                             # RECURSION : l'Environment
            turn.<+0x18 : previousPlayerId> = prev                    #   ne joue jamais un tour
        }
        return processor.<IOperationProcessor slot 0x14 = VerifyMatchEnd>()

    ⚠ LA RECURSION ENVIRONMENT N'EST PAS PORTEE, et ce n'est pas un oubli : elle serait
    STRUCTURELLEMENT INERTE. Le port derive son ordre de tour des PROPRIETAIRES D'UNITES
    (`player_turn_order`) ; or l'Environment n'a aucune unite -- le decoy pose par `Ambush` reste
    possede par son SUMMONER (MESURE du 2026-08-06 : `genesSmnDecoy` `owner = 4`, celui de
    `genesPrimus`). Il n'entre donc jamais dans l'ordre du port, et la branche ne pourrait jamais
    fire. La porter demanderait le `PlayerComponent.<+0x20 : PlayerType>`, qu'aucun RPC ne publie :
    residu `#462-r4e-o-r2-r1-r1-r1-r1`, meme capteur que celui de l'ordre de tour.

    ⚠ `SetCurrentPlayer` est un NO-OP quand le joueur ne change pas (`if (cur == next) return`, LU
    dans `IdunBattle.Entities.Components.TurnComponent$$SetCurrentPlayer`) : rendre le joueur
    COURANT n'est pas une anomalie cote natif -- mais ce n'est PAS non plus « un tour de plus pour
    lui », comme cette note l'ecrivait avant #287-r11-r1-r1-r1. Le retour anticipe est AVANT les deux
    bumps : ni `+0x38[next]` ni `+0x40[cur]` ne bougent. Le compte de tours du natif ne progresse
    donc pas dans ce regime, et `set_current_player` le mirroir.

    Renvoie le nouveau joueur (ou None)."""
    __slots__ = ()

    @staticmethod
    def execute(state: State) -> Optional[int]:
        nxt = find_next_player(state)
        if nxt is None:
            return None
        set_current_player(state, nxt)         # mirror IdunBattle.Entities.Components.TurnComponent$$SetCurrentPlayer
        return nxt


def _bump_turns_started(state: State, player: int) -> None:
    """Mirror de la boucle interne de `IdunBattle.Operations.StartTurnOperation$$Execute` : pour CHAQUE unite VIVANTE
    du joueur courant (`PlayerComponent.GetCurrentlyOwnedUnitIds`), `turnsStarted@+0x58 += 1` (compteur
    PER-UNITE, stat 12 = `GetStat(unit, 0xc)` = `IdunBattle.Entities.Formulas.UnitTurnsStartedFormula$$Calculate`). Base des
    hits Executioner (`RoundsStarted`, cf. #122) et de tout consommateur de `GetStat(unit, 0xc)`. DISTINCT
    du compteur GLOBAL `state.turn_counts` (TurnComponent+0x38, `GetAmountOfTurnsStartedByCurrentPlayer`).
    Off-by-one voulu : incr AVANT que les unites agissent -> a leur 1er tour le compteur vaut deja 1 (jamais
    0). No-op sur une unite sans `StatsComponent` (rien a bumper ; ex. capture partielle) — `increment_base`
    seede un compteur a 0 puis +1 si le stat n'etait pas capte."""
    for e in state.entities.values():
        oc = e.get_component(OwnerComponent)
        if oc is None or oc.player != player:
            continue
        uc = e.get_component(UnitComponent)
        if uc is not None and not uc.alive:
            continue
        sc = e.get_component(StatsComponent)
        if sc is None or sc.ctx is None:
            continue
        sc.ctx.stats.increment_base(StatType.TURNS_STARTED, 1)


class StartTurnOperation:
    """`IdunBattle.Operations.StartTurnOperation$$Execute (squelette fidele) : incremente le compteur
    PER-UNITE `turnsStarted@+0x58` de chaque unite du joueur courant (stat 12, `_bump_turns_started`,
    mig #123) puis emet la sequence d'events 0x12..0x16 ; ici on tire le vecteur turn-start `On(0x16)` deja porte
    (`start_turn_triggers` -> ex. TheBetrayer auto-tour). Les resets per-unite natifs (ActorStatistics/
    UnitFlags) ne sont pas suivis offline (cf. en-tete).

    APRES les triggers turn-start : passe AUTOMATIQUE (`run_ai_control_pass`) — joue les unites
    `IdunBattle.Entities.UnitExtensions$$IsAutomatic` (trait `Summon`(2) ou `Object`(13)) de la team
    courante via le playbook complet AVANT que le controleur agisse. Artefact natif = le slot
    `IOperationProcessor` 0x71 = `PlayAutomaticUnits(currentPlayer)` ->
    `IdunBattle.Operations.PlayAutomaticUnitsOperation$$Execute` (et NON
    `IdunGameViews$$QueueComputerActions`, qui est la boucle IA d'un joueur entierement AI-controle —
    citation corrigee par #291). **La PLACE du port est confirmee** : dans le corps natif, l'appel du
    slot 0x71 vient bien APRES les cinq emissions d'events 0x12..0x16. Deux gates natifs (non suivis
    offline, sans impact mesure sur l'arene — cf. `summon_ai.run_ai_control_pass`) :
    `!BattleQuery.NoAutomaticUnitTurns` et `PlayerType in {Human(0), Network(3), HumanAI(4)}`.
    No-op si la team n'a aucun summon (aucune regression turn-flow)."""
    __slots__ = ()

    @staticmethod
    def execute(state: State, player: int) -> list[dict]:
        # ⚠ AUCUN BUMP DE `state.turn_counts` ICI (#287-r11-r1-r1-r1-r1). Le natif LIT
        # `GetAmountOfTurnsStartedByCurrentPlayer` dans ce corps (il le compare a `1`), il ne
        # l'ECRIT pas : l'ecrivain UNIQUE de `TurnComponent+0x38` est
        # `IdunBattle.Entities.Components.TurnComponent$$SetCurrentPlayer`, donc `set_current_player`
        # (plus haut dans ce module), et lui seul respecte le NO-OP `cur == next`.
        _bump_turns_started(state, player)     # #123 : turnsStarted PER-UNITE (stat 12) += 1 (joueur courant)
        # #139 : reset des UnitFlags de tour du joueur ENTRANT — mirror de la boucle de StartTurnOperation.
        # (#101 : c'est le SEUL reset du fait "a bouge ce tour" — le `state.moved_this_turn.clear()` de #60
        # etait un reset GLOBAL, non natif : il effacait aussi la marque des unites du joueur SORTANT.)
        # IdunBattle.Operations.StartTurnOperation$$Execute : pour chaque unite de `PlayerComponent.CurrentlyOwnedUnitIds`,
        # `IdunBattle.Entities.Components.UnitFlagsComponent$$RemoveTurnFlags(includeNoAction=0, newActivation=1) (retire Moved/Teleported/
        # ArrivedAtFinalTile + ActiveAbilityUsed/TurnFinished/27 ; NoActionAvailable est CONSERVE — il n'est
        # leve que par VerifyUnitTurnEnded slot 0x77 quand l'unite regagne des options).
        for e in state.entities.values():
            oc = e.get_component(OwnerComponent)
            if oc is None or oc.player != player:
                continue
            fl = e.get_component(UnitFlagsComponent)
            if fl is not None:
                fl.remove_turn_flags(include_no_action=False, new_activation=True)
            # #202 : reset du dict "degats recus ce tour" — mirror `StartTurnOperation.ResetUnit
            # IdunBattle.Operations.StartTurnOperation$$ResetUnit` -> `IdunBattle.Entities.Components.ActorStatisticsComponent$$ResetReceivedDamageThisTurn`, PAR-UNITE DU JOUEUR ENTRANT
            # uniquement (les cles des unites ADVERSES survivent a leur propre tour — la portee du
            # reset compte pour le seuil >=3 de WeaverOfFate). Consomme par UnitsThatTakenDamageThisTurn.
            uc = e.get_component(UnitComponent)
            if uc is not None and uc.received_damage_this_turn:
                uc.received_damage_this_turn.clear()
            # ROULEMENT du « dernier coup encaisse » — mirror des DEUX instructions qui SUIVENT
            # immediatement `ResetReceivedDamageThisTurn` dans
            # `IdunBattle.Operations.StartTurnOperation$$ResetUnit` :
            #     stats[0x70] = stats[0x6c] ;  stats[0x6c] = 0
            # `@+0x70` est ce que rend `IdunBattle.Entities.Formulas.LastHitDamageTakenLastTurnFormula
            # $$Calculate` -> il vaut donc le degat du DERNIER COUP recu depuis le debut du tour
            # PRECEDENT du proprietaire (typiquement : pendant le tour adverse). Meme portee que le
            # reset du dict ci-dessus : PAR-UNITE DU JOUEUR ENTRANT uniquement.
            # ⚠ ORDRE : ce roulement precede l'emission des 5 events 0x12..0x16 plus bas — c'est ce qui
            # permet a la regen `TimeFlux` (`On(TurnStart_Other=0x13)`) de lire la bonne valeur.
            if uc is not None:
                uc.last_hit_damage_taken_last_turn = int(uc.last_hit_damage_taken_this_turn or 0)
                uc.last_hit_damage_taken_this_turn = 0
            # #366-r1 : `IdunBattle.Entities.Components.ActorStatisticsComponent$$
            # ResetBlocksMadeThisTurn` (`+0x8c = 0`) -- la TROISIEME instruction de la sequence de
            # `IdunBattle.Operations.StartTurnOperation$$ResetUnit`, entre `ResetUnitsAttackedThisTurn`
            # et `ResetReceivedDamageThisTurn`. MEME portee que les deux resets ci-dessus : les unites
            # du joueur ENTRANT. Lecteur unique : le gate `NOT HasBlockedThisTurn(Target)` de
            # `IdunBattleLogic.Entities.Abilities.Triggered.Loki.HarlequinsPanoplyAbility$$CreateTrigger`
            # (« the FIRST time each turn this unit blocks a hit »).
            if uc is not None:
                uc.blocks_made_this_turn = 0
            # #1037 : `*(undefined4 *)(stats + 0xd4) = 0` -- la DERNIERE instruction du bloc
            # `ActorStatisticsComponent` de `IdunBattle.Operations.StartTurnOperation$$ResetUnit`,
            # juste apres le roulement `+0x70 = +0x6c` ci-dessus (elle n'a PAS de methode `Reset*`
            # dediee : le champ est efface INLINE). MEME portee que les resets voisins : les unites
            # du joueur ENTRANT. ⚠ `ActorStatisticsComponent$$ResetThisTurn` ne le touche PAS -- lu
            # au decompile. C'est ce zero qui rouvre la fenetre du gate
            # `AmountIsEqual(TimesHealedThisTurn(Target), Const(1))` de
            # `IdunBattleLogic.Entities.Abilities.Triggered.Loki.WyrdmakersHelmAbility$$CreateTrigger`
            # (« gets healed for the FIRST time this turn »).
            if uc is not None:
                uc.times_healed_this_turn = 0
            # #509 : `IdunBattle.Entities.Components.ActorStatisticsComponent$$
            # ResetUnitsAttackedThisTurn` (`Clear(+0x40)`) -- la PREMIERE instruction de la meme
            # sequence de `IdunBattle.Operations.StartTurnOperation$$ResetUnit` (elle PRECEDE le
            # `ResetBlocksMadeThisTurn` ci-dessus, cf. sa note). MEME portee : les unites du joueur
            # ENTRANT. C'est ce Clear qui rouvre la fenetre du compteur `TotalTurnsWithAttacksMade`
            # (`+0x30`, incremente par `RegisterAttackMade` UNIQUEMENT quand ce set est vide) -->
            # une unite qui attaque a N tours differents a `+0x30 == N`. Lecteur porte :
            # `MartialInspiration_ExtraDamageEffect` (0x580 = 1408).
            if uc is not None and uc.units_attacked_this_turn:
                uc.units_attacked_this_turn.clear()
            # `#462-r4b-r1-r1-r1-r1-b-r1-r1-r3-r1-r3` : `*(undefined2 *)(uc + 0x179) = 0` -- la
            # SECONDE instruction de `IdunBattle.Operations.StartTurnOperation$$ResetUnit` (elle
            # suit immediatement `uc + 0x60 = 0` et PRECEDE tout le bloc `ActorStatisticsComponent`
            # ci-dessus). Ce `short` efface DEUX octets d'un coup : `+0x179` et `+0x17a`. Seul
            # `+0x17a` est porte -- c'est `killed_this_turn`, le substrat du noeud DSL
            # `IdunBattleLogic.Entities.DSLTriggers$$IsKilledThisTurn`.
            # ⚠ LE FILTRE `uc.alive` N'EST PAS UNE PRUDENCE : `ResetUnit` est appele sur
            # `PlayerComponent.CurrentlyOwnedUnitIds`, dont `PlayerComponent$$
            # get_CurrentlyOwnedUnitIds` retire les defaits (meme `RemoveAll(<defait>)` que
            # `current_turn_start_tile` plus bas). Un cadavre ne voit donc JAMAIS son drapeau
            # efface, et c'est ce qui donne au predicat sa vraie semantique : « tuee, et n'a pas
            # redemarre de tour depuis » -- PAS « tuee pendant le tour courant ».
            if uc is not None and uc.alive:
                uc.killed_this_turn = False
            # #213 : `UnitComponent + 0x18c` = la TUILE de debut de tour. Mirror des DEUX lignes qui
            # suivent le bump de `turnsStarted@+0x58` dans la MEME boucle native
            # (`IdunBattle.Operations.StartTurnOperation$$Execute`) :
            #     mainTile = EntityExtensions.GetMainTile(unit) ;
            #     unitComponent[0x18c] = (mainTile != null) ? mainTile.Id : 0 ;
            # Portee identique au reste de la boucle : les unites du joueur ENTRANT seulement. Le
            # filtre `alive` mirroir le `RemoveAll(<defait>)` de
            # `PlayerComponent$$get_CurrentlyOwnedUnitIds` (une unite morte n'est plus dans la liste,
            # donc sa tuile de debut de tour n'est PAS reecrite). Relu par le selecteur
            # `CurrentTurnStartTile` (ghost de `thousTerminator`, cf. `triggers/loki/ghost_revive.py`).
            if uc is not None and uc.alive and state.board is not None:
                pc = e.get_component(PositionComponent)
                uc.current_turn_start_tile = (state.board.id_at(pc.col, pc.row)
                                              if pc is not None else None)
        # #128 tile-effects ROUND-TICK : StartTurn emet la SEQUENCE d'events 0x12->0x13->0x14->0x15->0x16
        # (VERIFIE IdunBattle.Operations.StartTurnOperation$$Execute : 5 emissions FUN_1800280e0(...,0x12/0x13/0x14/0x15/0x16) en fin d'Execute ;
        # l'ancien "0x12/0x14/0x16" etait INCOMPLET). Mapping effets : 0x12 = Contaminated re-apply ; 0x13 =
        # FirstAid heal-on-tile (#130 : On(0x13) & IsTurnOf(units-on-tile)) ; 0x14 = Fire DoT + DryBush spread ;
        # 0x15 = (role a mapper) ; 0x16 = turn-start (start_turn_triggers). Le port tire tile_tick (0x12/0x14) +
        # FirstAid (0x13, PLAYER courant via IsTurnOf) + On(0x16). 0x15 PAS ENCORE branche (role non mappe).
        tile_ticks = tile_tick_triggers(state)
        first_aid = first_aid_heal(state, player)          # #130 : On(0x13) heal-on-tile des unites du player courant
        # #203 : On(0x13=TurnStart_Other) -> LivingMetalRepair (regen % PV des Necron endommages du player).
        # Meme event que FirstAid ; l'ordre 0x13-vs-0x14(tile DoT) herite de l'imperfection existante (tile_ticks
        # lumpe 0x12+0x14) -> residu documente (case-203). L'ordre FirstAid/LivingMetal entre eux est immateriel
        # (les deux soins s'additionnent, capes a maxHP).
        living_metal = turn_start_other_triggers(state, player)
        # `RefreshEffectTrigger.TurnChanged` (= 6, dump d'enums du build) -> `IdunBattle.Operations.
        # RefreshEffectsOperation$$Execute` avec `effectEntity` NUL = TOUS les effets, chacun voyant
        # sa `CreateActiveCondition` reevaluee (`RefreshEffectsOperation$$ShouldBeActive`).
        # PLACE : APRES `_bump_turns_started` ci-dessus, et c'est ce qui compte — les conditions qui
        # LISENT `GetStat(0xc = TurnsStarted)` doivent voir le compteur DEJA incremente. Cas porte :
        # `ContagionsOfNurgle_ArmorReduction1/2`, dont le rayon `GetCurrentRange` monte 1 -> 2 -> 3
        # avec le `TurnsStarted` du PORTEUR d'aura : une unite jusque-la hors du disque y entre au
        # tour ou l'aura grandit, et prend le debuff SANS avoir bouge.
        # Idempotent pour tout autre effet declaratif a stat-mod (`Modify` = replace par-source).
        # ⚠ Le declencheur est PASSE depuis #477-r21-r2 volet A (il n'etait qu'en commentaire) :
        # `RefreshEffectsOperation$$ShouldBeActive` le consomme via
        # `BaseEffect$$ShouldRefreshForTrigger`.
        refresh_stat_modifier_effects(state, refresh_trigger=RefreshEffectTrigger.TurnChanged)
        # #513 : `On(0x15 = TurnStart_DelayedAttacks)`, le QUATRIEME des cinq events -- il etait le
        # SEUL sans consommateur porte (<< role a mapper >> ci-dessus). Son role est lu :
        # `IdunBattle.Entities.Effects.APendingAttackEffect$$CreateHandleTriggerAbilitiesInternal` y
        # monte l'attaque DIFFEREE de toute la famille 2-phases. Il PRECEDE `On(0x16)` -- ordre du
        # decompile, et il compte : le missile frappe AVANT que les trigger-abilities de turn-start
        # ne s'executent.
        delayed = delayed_attack_triggers(state, player)
        out = start_turn_triggers(state, player)
        out = (tile_ticks + first_aid + living_metal + delayed + out
               + run_ai_control_pass(state, player))
        return out


def _bump_turns_finished(state: State, player: int) -> None:
    """Mirror de la boucle interne d'`IdunBattle.Operations.EndTurnOperation$$Execute` : pour CHAQUE
    unite de `PlayerComponent.GetCurrentlyOwnedUnitIds` du joueur qui FINIT son tour,
    `*(int *)(unitComponent + 0x5c) += 1` (compteur PER-UNITE `turnsFinished`, lu par
    `IdunBattle.Entities.UnitExtensions$$GetTurnsFinished`).

    DISTINCT des deux autres compteurs de tour, et c'est tout l'enjeu :
      * `turnsStarted@+0x58` (stat 12) est bumpe par `StartTurnOperation` -> `_bump_turns_started` ;
      * `state.turn_counts` est le dict PAR JOUEUR `TurnComponent+0x38`.
    Le natif a DEUX sites `+0x5c += 1` dans `EndTurnOperation.Execute` : la boucle sur les unites du
    joueur, puis la Machine of War du joueur (`PlayerComponent+0x78`). Le port materialise la MoW avec
    un `UnitComponent` (cf. `snapshot._load_machines`) -> une seule boucle couvre les deux sites.

    Unites MORTES EXCLUES : `PlayerComponent$$get_CurrentlyOwnedUnitIds` finit par un `RemoveAll` du
    predicat `PlayerComponent$$u003Cget_CurrentlyOwnedUnitIdsu003Eb__17_0` (« id present dans la liste
    des defaits @+0x40 ») -> meme filtre `alive` que `_bump_turns_started`.

    ORDRE : cette boucle est la PREMIERE etape du corps natif. Elle precede donc l'execution des
    trigger-abilities `On(0x17 = TurnEnd)` (l'appel du slot 0x51 avec le litteral `0x17` vient apres)
    -> le porteur voit deja le tour qui s'acheve dans son compteur quand son propre gate s'evalue.
    Corollaire : une unite SPAWNEE par un trigger `On(0x17)` (replique PileIn) n'est PAS bumpee ce
    tour-la, exactement comme dans le natif ou la liste d'ids est COPIEE avant la boucle. Et elle
    precede AUSSI `RefreshEffects`, qui est la DERNIERE etape (case-n8b)."""
    for e in state.entities.values():
        oc = e.get_component(OwnerComponent)
        if oc is None or oc.player != player:
            continue
        uc = e.get_component(UnitComponent)
        if uc is None or not uc.alive:
            continue
        uc.turns_finished = int(uc.turns_finished or 0) + 1


class EndTurnOperation:
    """`IdunBattle.Operations.EndTurnOperation$$Execute (squelette fidele) — cf. en-tete pour le porte/defere.

    ORDRE, lu dans le corps d'`Execute` (case-n8b) — les cinq etapes se suivent dans CET ordre :
      1. boucle sur `PlayerComponent.CurrentlyOwnedUnitIds` du joueur FINISSANT :
         `turnsFinished@+0x5c += 1` (+ `ResetAbilitiesThatResetOnTurnEnd` / `DecreaseAbilityCooldowns`,
         non suivis offline) ;
      2. `IdunBattle.Operations.EndTurnOperation$$RemoveOneTurnOnShields` sur `GetAllUnits`
         (+ `ActorStatisticsComponent.ResetThisTurn` : volet TUILES porte, cf. en-tete) ;
      3. meme `+0x5c += 1` sur la Machine of War du joueur (`PlayerComponent+0x78`) ;
      4. si `IdunBattle.Entities.Components.TurnComponent$$HasActivePlayer` : le vecteur de triggers
         `On(0x17 = TurnEnd)` (slot 0x51 = `Core.Services.OperationProcessor$$EvaluateAbilities`,
         litteral `0x17`) ;
      5. **`IdunBattle.Operations.EndTurnOperation$$RefreshEffects` — APRES le vecteur**, pas avant :
         le `LAB` de l'appel `0x17` tombe en fall-through sur celui de `RefreshEffects`, et la branche
         `HasActivePlayer == 0` saute DIRECTEMENT a `RefreshEffects` en enjambant le vecteur.
    Puis les events de fin et, si `advance` (param_2), la sequence ChangeTurn + StartTurn.

    Le port faisait etape 5 EN PREMIER (tick des effets avant le vecteur). Corrige ici. Consequence
    exacte : **les gates des triggers `On(0x17)` voient l'etat PRE-tick** — un effet a duree qui
    s'eteint a cette fin de tour est encore ACTIF quand ils s'evaluent."""
    __slots__ = ()

    @staticmethod
    def execute(state: State, advance: bool = True) -> dict:
        finishing = state.current_player_id
        # (1) `turnsFinished@+0x5c += 1` PER-UNITE du joueur qui FINIT son tour (compteur natif lu par
        # `IdunBattle.Entities.UnitExtensions$$GetTurnsFinished`). PREMIERE etape du corps natif, donc
        # AVANT le vecteur `On(0x17)` : c'est ce qui donne son sens au gate `OwnerHasFinishedMinTurns`
        # de PileIn (le tour qui s'acheve compte deja).
        _bump_turns_finished(state, finishing)
        # (2) IdunBattle.Operations.EndTurnOperation$$RemoveOneTurnOnShields : décay d'1 tour des boucliers à durée de TOUTES les unités
        # (ShieldComponent.RemoveOneTurn → décrémente remaining, retire les instances à 0).
        # MEME BOUCLE, MEME RANG que le natif : `Execute` itere `StateExtensions$$GetAllUnits` et
        # enchaine, par unite, `RemoveOneTurnOnShields` puis
        # `IdunBattle.Entities.Components.ActorStatisticsComponent$$ResetThisTurn(comp, wasOwnTurn)`.
        # Volet TUILES de ce reset (case-322-r1, `reset_tiles_moved_this_turn`) : `+0xf0 = 0` pour
        # TOUTES les unites -- c'est ce qui donne a `TilesMovedThisTurn` sa portee « CE TOUR » --
        # et `+0xf4 = +0xf0` (TilesMovedLastTurn) pour les seules unites du joueur qui FINIT.
        # `was_own_turn` = mirror du `PlayerComponent.CurrentlyOwnedUnitIds.Contains(unit.Id)` natif.
        shields_ticked: list[tuple] = []
        for uid, e in state.entities.items():
            shc = e.get_component(ShieldComponent)
            if shc is not None and shc.shields:
                ch = shc.remove_one_turn()
                if ch["removed"] or ch["decremented"]:
                    shields_ticked.append((int(uid), ch))
            oc = e.get_component(OwnerComponent)
            reset_tiles_moved_this_turn(state, int(uid),
                                        was_own_turn=(oc is not None and oc.player == finishing))
        # (3) `FinishUnitTurn(unit, isTerminated: false)` PAR UNITE POSSEDEE -- le natif le fait bien
        # ici : `IdunBattle.Operations.EndTurnOperation$$Execute` itere
        # `PlayerComponent.CurrentlyOwnedUnitIds` et appelle le slot 0x23 de `Core.Services.
        # OperationProcessor` avec `(unit, false)`. Que ce slot SOIT `FinishUnitTurn` est PROUVE et non
        # suppose : `IdunBattle.Operations.ActiveAbilityOperation$$AddFlagsAfterAbilityExecution`
        # appelle le MEME slot 0x23 de la MEME classe avec `(caster, false)`, et c'est deja ce que le
        # port nomme `FinishUnitTurn` (cf. `add_flags_after_ability_execution`).
        #
        # C'EST L'OPERATION ENTIERE QUI EST APPELEE, PAS UNE DE SES JAMBES (#462-r4e-o-r2-r1-r1).
        # Le port n'emettait d'ici que `On(0x28 = UnitFinishedTurn)`, en sautant la POSE des flags
        # et les deux autres jambes -- « rayon de souffle hors de la tranche #448-r2 », disait le
        # residu. C'etait une PRUDENCE, pas une fidelite : le natif appelle bien le slot 0x23 avec
        # `isTerminated = false`, donc `IdunBattle.Operations.FinishUnitTurnOperation$$Execute`
        # POSE `Add(0x01 = ArrivedAtFinalTile)` et `Add(0x03 = TurnFinished)`, publie `On(0x1c)`
        # puis `On(0x28)` puis `On(0x29)` sous leurs gates respectifs, vide `ChargedUnitIds` et
        # termine par le slot 0x76 (`MarkUnitAsNoActionAvailable` -> flag 4). Tout cela etait DEJA
        # PORTE dans `FinishUnitTurnOperation.execute` -- seul l'APPEL manquait.
        # MESURE qui l'a montre (montage Ambush MC1_67/777) : les flags de l'unite RESSUSCITEE
        # valaient `[14]` cote port contre `[1, 3, 4, 14]` cote natif, et les trois flags manquants
        # sont EXACTEMENT ceux que cette operation pose.
        # Le gate `Add(TurnFinished)` (« le flag vient d'etre pose ») vit DANS l'operation
        # (`newly_finished`), donc la boucle n'a plus a le pre-filtrer.
        #
        # CE QUE CA REMPLACE : la boucle bespoke `land_deep_strike` d'avant #448-r2, qui faisait
        # atterrir ICI toutes les unites deep-strike du joueur finissant. Le retrait de
        # `TeleportStrike_TeleportingIn` est desormais porte par les TROIS triggers natifs de
        # l'effet (`On(4)`, `On(0x2a = PreUnitAbility)`, `On(0x28 = UnitFinishedTurn)`) -- mesure live : le natif retire l'effet DES LE
        # MOUVEMENT ou DES LE CAST, pas en fin de tour. Ce site-ci ne couvre donc plus que le cas
        # « l'unite n'a rien fait de son tour », qui est exactement ce que le natif couvre ici.
        # ⚠ MORTES EXCLUES : `PlayerComponent$$get_CurrentlyOwnedUnitIds` finit par un `RemoveAll`
        # des defaits -- MEME filtre que `_bump_turns_started` / `_bump_turns_finished`.
        landed: list[dict] = []
        for uid, e in list(state.entities.items()):
            oc = e.get_component(OwnerComponent)
            if oc is None or oc.player != finishing:
                continue
            uc = e.get_component(UnitComponent)
            if uc is not None and not uc.alive:
                continue
            landed.append(FinishUnitTurnOperation.execute(state, int(uid), forced=False))
        # (4) vecteur `On(0x17 = TurnEnd)` — DEUX consommateurs portes (inventaire re-derive du registre
        # par `probe_n8b_turnend_consumers.py`) : le dispatch generique `ABILITY_TRIGGERS`
        # (`RadSaturationAbility`, branche `NOT HasFlag(owner, Moved)`) et le bespoke
        # IdunBattleLogic.Entities.Abilities.Active.Loki.PileInAbility$$CreateBehaviour /
        # IdunBattleLogic.Entities.Abilities.Active.Loki.PileInAbility$$CreateTrigger (grots du joueur
        # FINISSANT a PV pleins -> auto-dedoublement, 75-5%/grot). AVANT le tick d'effets : leurs gates
        # lisent donc l'etat PRE-tick, comme dans le natif. No-op si aucun porteur.
        pilein = end_turn_summon_triggers(state, finishing)
        # (5) IdunBattle.Operations.EndTurnOperation$$RefreshEffects : tick d'1 tour des effets a duree de TOUTES les unites (le natif
        # itere GetAllUnits, pas seulement le joueur finissant). `attacked` non suivi offline -> False
        # (les effets removed-after-attack sont rares et deja consommes one-shot a l'attaque via on_attack).
        # Le natif n'inflige AUCUN degat ici : `RefreshEffects` = `EffectComponent.RemoveOneTurn` + events,
        # puis `Core.Services.OperationProcessor$$RefreshEffects` -> `RefreshEffectsOperation$$Execute`
        # (branche de retrait). Les DoT de tuile passent, eux, par les events 0x12/0x14 de StartTurn.
        # ⚠ `state` EST PASSE, ET C'EST CE QUI REND L'ECHEANCE OBSERVABLE (#936-r1). Sans lui le tick
        # posait `consumed` en direct : aucun des trois vecteurs de
        # `IdunBattle.Operations.RemoveEffectOperation$$Execute` (`On(0x3f = PreEffectRemoved)`,
        # `On(0x40 = EffectRemoved)`, `On(0x3b = UnitBecameTargetable)`) ne sortait sur cette voie,
        # et le NOM de l'effet restait colle a l'`EffectsOwnedComponent` du porteur. Le natif, lui,
        # n'a qu'UN corps de retrait, atteint depuis l'echeance par la `System.Action` differee
        # `RefreshEffectsOperation.<>c__DisplayClass9_0$$<RemoveEffect>b__0` (slot 0x11).
        ticked: list[int] = []
        if state.effects is not None:
            for uid in list(state.effects.by_unit.keys()):
                state.effects.on_turn_end(uid, attacked=False, state=state)
                ticked.append(int(uid))
        # `<Effect>.RevertInternal` -> `IdunBattle.Entities.Effects.AStatModifierEffect$$RevertModification`
        # (ChangeStat part 6) : un effet que le tick vient de faire EXPIRER doit SORTIR sa `ValueModification`
        # du `UnitStats`. Sans ce foyer, seul le retrait EXPLICITE (feuille `RemoveEffect`) revertait — un
        # stat-mod a TIMER (ex. `Thrilled` 1434 de ThrillSeekers, +15 CritChance pour 1 round) restait
        # applique pour toujours. No-op strict pour toute instance sans `stat_mod_source`. Reste COLLE au
        # tick (mirror du `RefreshEffectsOperation` que `RefreshEffects` appelle en sortie de boucle).
        reverted = revert_stat_mods_of_removed_effects(state)
        # MEME `RevertInternal`, AUTRE part : les TRAITS accordes par un effet qui vient d'expirer
        # (`OperationProcessor$$RemoveTrait`, cf. `WarHowl_ExtraDamage_UnstoppableEffect$$
        # RevertInternal`). Foyer separe parce que le gate d'idempotence de l'autre est specifique
        # aux stat-mods (`effect_stat_mod_key` -> `continue` sur None, donc un effet a trait SANS
        # stat-mod n'y arrive jamais). Reste COLLE au tick, comme lui.
        traits_reverted = revert_traits_of_removed_effects(state)
        # Meme rang, TROISIEME axe (#590) : un `AttemptedPossession_Possessed` (1209) que le tick
        # vient de faire EXPIRER doit rendre son porteur a son camp d'origine
        # (`AttemptedPossession_PossessedEffect$$RevertInternal` = `ResetUnitOwner`). Colle au tick
        # pour la meme raison que les deux lignes au-dessus : le natif enfile les TROIS depuis
        # `RefreshEffectsOperation$$RefreshEffect`. No-op strict tant qu'aucune instance expiree ne
        # declare `overrides_unit_owner()`.
        # ⚠ Les TROIS clefs voyagent ENSEMBLE dans le dict de retour (#585 x #590, resolu au
        # rebase) : en garder une seule ETEINDRAIT le canal de l'autre en silence -- son appelant
        # lirait `None` et le lirait comme << rien a reverser >>.
        owners_reverted = _ops_effects.revert_owner_overrides_of_removed_effects(state)
        if not advance:
            return {"ticked": ticked, "shields_ticked": shields_ticked, "landed": landed,
                    "pilein": pilein, "next_player": None, "start": None,
                    "stat_mods_reverted": reverted, "traits_reverted": traits_reverted,
                    "owner_overrides_reverted": owners_reverted}
        nxt = ChangeTurnOperation.execute(state)
        start = StartTurnOperation.execute(state, nxt) if nxt is not None else None
        return {"ticked": ticked, "shields_ticked": shields_ticked, "landed": landed,
                "pilein": pilein, "next_player": nxt, "start": start,
                "stat_mods_reverted": reverted, "traits_reverted": traits_reverted,
                "owner_overrides_reverted": owners_reverted}


# ================================================================================================ #
# `IdunBattle.Operations.VerifyUnitsTurnFinishedOperation` (#287-r1-r1) — la voie qui RE-OUVRE
# l'activation d'une unite. C'est le pendant du foyer de POSE porte par #287-r1 : le natif ne se
# contente pas de poser `UnitFlag.NoActionAvailable`, il le RETIRE des que l'unite regagne des
# options. Sans cette voie le port ne peut que SUR-FERMER, et le flag est COLLANT :
# `UnitFlagsComponent$$RemoveTurnFlags(includeNoAction: 0)` — ce que `StartTurnOperation` appelle —
# le CONSERVE au changement de tour. Une unite marquee une fois le resterait pour toujours.
# ================================================================================================ #


def _can_move(state: State, unit_id: int) -> Optional[bool]:
    """`IdunBattle.Entities.UnitExtensions$$CanMove(unit)` — MIRROR du decompile :

        if (unit == null)                                          return false
        if (EntityExtensions.GetEntityType(unit) != EntityType.Unit) return false
        base = UnitExtensions.GetBaseUnitComponent(unit)
        if (base != null && base.HasTrait(UnitTrait.Stationary)) return false
        if (!unit.TryGetComponent<MovementComponent>(out mc))    return false
        return mc.IsAllowedToMove()

    TRI-ETAT. Les trois premiers etages sont LUS sur le substrat du runner ; le quatrieme ne l'est
    pas, et il est NOMME plutot que devine :

    `IdunBattle.Entities.Components.MovementComponent$$IsAllowedToMove` est
    `this.<+0x50 : Dictionary>.Count == 0` — un registre de BLOQUEURS par source, qu'aucun canal de
    seed du runner n'expose (et dont aucun ecrivain n'est une methode NOMMEE du binaire : les
    ecritures sont inline, donc meme le decompile ne donne pas la liste des poseurs). On ne le
    fabrique PAS depuis les effets `*_BlockMovement` : ce serait une hypothese deguisee en mirror.
    Il est donc rendu comme NON PORTE, et sa direction est dite : le port croit l'unite MOBILE la ou
    le natif la bloquerait -> `has_tiles_to_move_to` sur-estime -> le port RETIRE le flag un peu plus
    souvent que le natif (permissif), jamais il ne le POSE a tort. MEME residu, meme direction, que
    celui deja nomme par `entities/selectors/tiles.MovableTilesInRange` (garde d'entree de
    `FindAnyOrAllMoveableTiles`).

    Rend `False` (certain), `True` (aux trois etages lus), ou `None` si l'entite n'est pas lisible.
    """
    e = state.get_entity(int(unit_id))
    if e is None:
        return False                      # `unit == null` -> false
    uc = e.get_component(UnitComponent)
    if uc is None:
        return None                       # entite sans `UnitComponent` : type d'entite non lisible
    # `GetEntityType(unit) != EntityType.Unit(1)` — une MACHINE OF WAR (`EntityType.Machine` = 6) ne
    # passe JAMAIS ce gate. C'est ce qui rend `HasTilesToMoveTo` faux pour elle cote natif, et c'est
    # aussi pourquoi `VerifyMachineTurnEnded` ne l'appelle pas du tout.
    if is_machine_of_war(e):
        return False
    sc = e.get_component(StatsComponent)
    traits = (getattr(sc.ctx, "traits", None) if (sc is not None and getattr(sc, "ctx", None)
                                                  is not None) else None)
    if traits is not None and has_trait(traits, UnitTrait.Stationary):
        return False                      # `BaseUnitComponent$$HasTrait(unit, UnitTrait.Stationary)`
    return True                           # `MovementComponent$$IsAllowedToMove` NON PORTE (cf. ci-dessus)


def has_tiles_to_move_to(state: State, unit_id: int) -> Optional[bool]:
    """`IdunBattle.Operations.VerifyUnitsTurnFinishedOperation$$HasTilesToMoveTo(unit)` = le slot
    `IMovementQuery` **3**, appele `(unit, ignoreUnitFlags: false, options: <memset 0>)` et dont le
    retour est teste comme un BOOLEEN — soit
    `IdunBattle.Core.Services.MovementQuery$$HasAnyMovablePositionsFor`, dont c'est exactement la
    signature :

        HasAnyMovablePositionsFor(unit, ignoreUnitFlags, options) :
            unitFlags = unit.GetComponent<UnitFlagsComponent>()
            unitTiles = EntityExtensions.GetTiles(unit, state)
            return FindAnyOrAllMoveableTiles(unit, unitTiles, ignoreUnitFlags, options,
                                             unitFlags, movableTilesFor: null)

    Le `null` final selectionne le mode **ANY** d'`AnyOrFillMoveableTiles` : le natif y rend `true`
    des que le premier `GetReachableTiles` FILTRE par `IsMovableTile` est non vide. C'est donc, terme
    a terme, `GetMovableTilesFor(...).Count > 0` — le meme stop-set, le meme filtre d'occupation.

    Garde d'entree de `FindAnyOrAllMoveableTiles`, LUE :

        if ((unitFlags.Has(UnitFlag.Moved) && !ignoreUnitFlags) || !UnitExtensions.CanMove(unit))
            return false

    `ignoreUnitFlags` vaut **0** ici (litteral du call-site) : le flag `Moved` MORD. Contrairement au
    noeud DSL `MovableTilesInRange` — qui laissait ce gate inerte faute de substrat — le runner PORTE
    `UnitFlagsComponent`, donc le gate est ici REEL : une unite qui a deja bouge n'a plus de tuile ou
    aller, et c'est precisement ce qui fait poser le flag apres un deplacement.

    Le pathfinding lui-meme n'est PAS re-ecrit : il delegue a `engine.ai.state_bridge._move_tiles`,
    le mirror d'`aiMovableTiles` (= litteralement `MovementQuery$$GetMovableTilesFor`) deja confronte
    live, qui appelle le FOYER `engine.services.movement_query.get_movable_tiles_for`. Aucun second
    calcul de tuiles atteignables n'est introduit par cette tranche.

    Rend `None` quand un ingredient manque (pas de board, pas de position, `CanMove` illisible)."""
    e = state.get_entity(int(unit_id))
    if e is None:
        return None
    fl = e.get_component(UnitFlagsComponent)
    if fl is None:
        return None                        # `unitFlags == null` -> le natif LEVE ; offline = non mesure
    if fl.has(UnitFlagsComponent.MOVED):
        return False                       # `Has(UnitFlag.Moved) && ignoreUnitFlags == 0`
    cm = _can_move(state, int(unit_id))
    if cm is not True:
        return False if cm is False else None
    if state.board is None:
        return None                        # aucun substrat de pathfinding -> NON MESURE
    pc = e.get_component(PositionComponent)
    oc = e.get_component(OwnerComponent)
    uc = e.get_component(UnitComponent)
    if pc is None:
        return None
    tiles = _move_tiles(state, int(unit_id), (uc.visual_id if uc is not None else "") or "",
                        (oc.team if oc is not None else None), (pc.col, pc.row))
    return len(tiles) > 0


def has_action_available(state: State, unit_id: int,
                         movable_is_empty: Optional[bool] = None) -> Optional[bool]:
    """`IdunBattle.Operations.VerifyUnitsTurnFinishedOperation$$HasActionAvailable(unit)` :

        movable = <IMovementQuery slot 0>(unit, ignoreUnitFlags: false, options: <memset 0>)
                = `IdunBattle.Core.Services.MovementQuery$$GetMovableTilesFor`
        movable.Add(EntityExtensions.GetMainTile(unit, state))       // la tuile COURANTE
        return <IDamagePredictionQuery slot 1>(unit, movable)
             = `IdunBattle.Core.Services.DamagePredictionQuery$$CanAttackAnyUnitFromTilesWithAnyAbility`
             -> `IdunBattle.Core.Services.AttackQuery$$CanAttackAnyUnitFromAnyTileWithAnyAbility` :

                  flags = unit.GetComponent<UnitFlagsComponent>()
                  if (flags.TurnEnded())                          return false
                  if (flags.Has(UnitFlag.ActiveAbilityUsed))      return false
                  if (UnitExtensions.IsBoss(unit))                return true
                  positions = EntityExtensions.GetUnitPositionsAtTiles(unit, tiles, state)
                  foreach (ActiveAbility a in unit.GetComponent<ActiveAbilityComponent>().<+0x20>)
                      if (   a.CanCurrentlyBeUsed
                          && !UnitExtensions.IsAbilityBlocked(unit, a.AbilityName)
                          && AttackQuery.HasValidTargets(unit, positions, a.AbilityName))
                          return true
                  return false

    TRI-ETAT, et la ligne de partage est NETTE : ce corps est porte sur ses verdicts **certains**,
    et rend `None` la ou il faudrait `AttackQuery$$HasValidTargets` — la cascade de ciblage complete
    (`GetValidTargets` -> `TargetingQuery$$GetPossibleTargetsForOptions` -> `GetUnitsInRange`), dont
    le port ne dispose pas hors du canal RPC `abilityTargets`. Rendre `False` par defaut ferait
    POSER le flag sur une unite qui peut encore frapper : c'est exactement la SUR-FERMETURE que cette
    tranche existe pour reduire.

    Verdicts rendus, tous LUS sur le substrat du runner :
      * `TurnEnded()` -> `False` (inatteignable depuis `verify_unit_turn_ended`, qui coupe avant —
        ecrit parce que le natif l'ecrit, et parce que les DEUX autres appelants natifs de ce corps
        n'ont pas cette coupe) ;
      * `Has(UnitFlag.ActiveAbilityUsed)` -> `False` : c'est le gate PUR-FLAG qui donne au port sa
        seule voie de POSE certaine (une unite qui a use son active et ne peut plus bouger) ;
      * `IsBoss` -> le FOYER unique du port (`operations/repair._is_boss`, non porte, rend `False`)
        -> on ne prend jamais le raccourci `true` ; direction : le port peut manquer un `True`,
        jamais en fabriquer un ;
      * `ActiveAbilitiesComponent` present et **aucune** entree `CanCurrentlyBeUsed` -> `False`
        certain (la boucle native ne peut alors rien rendre) ;
      * composant ABSENT (le canal `allAbilities` n'a pas ete demande au seed) -> `None`, jamais
        « aucune ability » ;
      * au moins une entree utilisable -> `None` (il faudrait `HasValidTargets`).

    `UnitExtensions$$IsAbilityBlocked` (`ActiveAbilityComponent.NormalAttackIsBlocked` /
    `ActiveAbilitiesAreBlocked` / `MachinePrimaryAbilityIsBlocked`) n'a pas de substrat : il ne peut
    que RESTREINDRE, donc l'ignorer ne peut que rendre un `True` de plus — jamais un `False` a tort.

    LA POSITION D'EVALUATION EST LA TUILE COURANTE, ET C'EST EXACT — pas une approximation.
    `HasValidTargets` est evalue sur `GetMovableTilesFor(unit) + GetMainTile(unit)`, et le port ne
    sait juger une cible que depuis la position REELLE du caster (cf. `valid_normal_attack_targets`).
    Or les DEUX predicats de `VerifyUnitTurnEnded` partagent le MEME `GetMovableTilesFor` : quand
    `HasTilesToMoveTo` est faux — le seul regime ou `_can_act` consulte cette fonction, le OU natif
    court-circuitant sinon — ce set est VIDE (meme garde d'entree `FindAnyOrAllMoveableTiles`, meme
    stop-set), et la liste native se reduit a la seule `GetMainTile`. Le garde ci-dessous rend le
    raisonnement EXECUTABLE plutot que verbal : si le set n'est pas vide, un `False` ne serait pas
    certain (le natif jugerait depuis d'autres tuiles) -> `None`."""
    e = state.get_entity(int(unit_id))
    if e is None:
        return None
    fl = e.get_component(UnitFlagsComponent)
    if fl is None:
        return None
    if fl.turn_ended():
        return False                       # `UnitFlagsComponent$$TurnEnded()` -> false
    if fl.has(UnitFlagsComponent.ACTIVE_ABILITY_USED):
        return False                       # `Has(UnitFlag.ActiveAbilityUsed)` -> false
    if _is_boss(state, int(unit_id)):
        return True                        # `UnitExtensions$$IsBoss(unit)` -> true (foyer : rend False)
    comp = e.get_component(ActiveAbilitiesComponent)
    if comp is None:
        return None                        # canal `allAbilities` non demande -> NON MESURE
    # Le garde de POSITION (cf. docstring) : un `False` n'est certain que si le natif n'avait, lui
    # aussi, que la tuile courante a juger. `movable_is_empty` est passe par `_can_act`, qui vient
    # d'evaluer `has_tiles_to_move_to` -- ne PAS le recalculer (ce serait un 2e pathfinding).
    if movable_is_empty is None:
        movable_is_empty = (has_tiles_to_move_to(state, int(unit_id)) is False)
    undetermined = not movable_is_empty
    # L'ATTAQUE NORMALE d'abord : le natif l'a dans sa `KeyedCollection` (c'est
    # `UnitFactory$$AddNormalAttackAbility` qui l'y pousse), le composant du port l'en EXCLUT (il
    # n'y a pas d'objet `ActiveAbility` derriere) -> il faut la rajouter, sans quoi la boucle
    # ignorerait l'action la plus courante du jeu. `CanCurrentlyBeUsed` : elle n'a ni charge, ni
    # cooldown, ni munitions -> jamais gatee (meme convention que `battle_query.can_use_ability`).
    if normal_attack_type_for(state, int(unit_id)) is None:
        undetermined = True                # type d'attaque normale non resolu -> pas de verdict
    elif valid_normal_attack_targets(state, int(unit_id)):
        return True
    for ab in comp.abilities:
        if not ab.can_currently_be_used():
            continue                       # `!a.CanCurrentlyBeUsed` -> ability sautee
        r = _has_valid_targets(state, int(unit_id), ab.ability_type)
        if r is True:
            return True                    # la boucle native rend `true` a la PREMIERE qui passe
        if r is None:
            undetermined = True
    return None if undetermined else False


def _has_valid_targets(state: State, unit_id: int, ability_type: int) -> Optional[bool]:
    """`IdunBattle.Core.Services.AttackQuery$$HasValidTargets(attacker, attackerPosition,
    activeAbilityType)` — la surcharge par POSITION, celle que la surcharge par liste de tuiles
    appelle en boucle :

        if (activeAbilityType == 0)                                  return false
        ab = attacker.GetComponent<ActiveAbilityComponent>().GetOrNull(activeAbilityType)
        if (ab == null || !ab.CanCurrentlyBeUsed)                    return false
        options = <ITargetingOptionsProvider slot 0>(activeAbilityType)
        return <ITargetingQuery>.<...>(attacker, attackerPosition, <predicat sur options>)

    DEUX ETAGES, et le port n'en portait qu'UN (#287-r4). `TargetingQuery$$GetValidTargets` ouvre par
    le volet CASTER et rend `ValidTargets.Empty` s'il est rompu, AVANT toute enumeration ; ce n'est
    qu'ensuite qu'elle filtre chaque cible par la surcharge 7 arguments. Detail au site.

    Le predicat terminal est la MEME cascade que `TargetingQuery$$GetValidTargets` : la surcharge
    **7 arguments** de `GetInvalidTargetReason`, la CASCADE SEULE (ni aiguillage self-cast, ni volet
    caster -- mais la regle DYNAMIQUE, elle, y est bien : cf. le commentaire au site ci-dessous et
    #287-r4). C'est exactement ce que le port nomme `apply_self_cast_switch=False`, et c'est
    pour cela qu'on n'appelle PAS `is_invalid_target` (qui, lui, ajoute le volet caster de la
    surcharge 5 arguments — il refuserait des cibles que `GetValidTargets` garde, donc SUR-FERMERAIT).

    `None` = masque non RE-lu (`targeting_options_for` rend `None`) : sans ses `TargetingOptions`
    la cascade ne pose AUCUN gate et rendrait `True` pour n'importe quelle entite — un `True`
    fabrique. On le refuse explicitement.

    ORDRE d'enumeration = `state.entities` (meme residu nomme que `valid_normal_attack_targets`) ;
    il n'a aucune incidence sur un predicat d'EXISTENCE."""
    opts = targeting_options_for(int(ability_type))
    if opts is None:
        return None
    # UNE INSTANCE, jamais la CLASSE (#287-r4). Le natif charge ici un OBJET --
    # `attacker.GetComponent<ActiveAbilityComponent>().GetOrNull(activeAbilityType)` -- et la
    # cascade qu'il appelle ensuite (surcharge 7 arguments de
    # `IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason`) INVOQUE le delegue dynamique
    # de cet objet sous le bit `TargetMatchesDynamicRule` :
    #     if ((options.Rules & 2) != 0) {
    #         d = options.<+0x38>;            // pose par `AActiveAbility$$.ctor`, slot vtable +0x480
    #         if (d == null) <NullReferenceException>;
    #         rule = d.Invoke(caster, casterTiles, target, targetTiles);
    #         if (rule != 0) return GenericBrokenTargetingRule(rule);
    #     }
    # « filtre STATIQUE pur » ne qualifie donc que l'ABSENCE de l'aiguillage self-cast et du volet
    # caster (tous deux dans les surcharges 5 arguments, en AMONT) -- la regle DYNAMIQUE, elle, est
    # bien dans la 7 arguments. Passer la classe rendait la methode NON LIEE : `state` se liait a
    # `self` et il manquait un argument (`TypeError`, 47 des 65 ids qui posent le bit).
    klass = ABILITY_CLASSES.get(int(ability_type))
    if klass is not None and getattr(klass, "TARGETING_OPTIONS", None) is not None:
        ability = klass()                      # meme construction que `abilities/handler.py`
    else:
        # Masque LU mais behaviour non portee (`TARGETING_OPTIONS_UNPORTED`) : porteur MINIMAL qui
        # transporte le masque ET les deux regles-delegues, dont la non-evaluabilite est NOMMEE dans
        # la classe -- meme procede que `_NormalAttackTargeting`.
        ability = UnportedAbilityTargeting(int(ability_type), opts,
                                           ability_id=getattr(klass, "ABILITY_ID", None))
    # LE VOLET CASTER, EN TETE (#287-r4). `TargetingQuery$$GetValidTargets` -- la fonction dont
    # cette boucle est le mirror -- COMMENCE par lui, et sort AVANT toute enumeration :
    #     reason = GetInvalidCasterReason(caster, casterTiles, options);
    #     if (reason.IsInvalid())  return ValidTargets.Empty;      // aucune cible, pas « toutes »
    #     range = GetRange(...); foreach (t in GetPossibleTargetsForOptions(...)) { <la 7 args> }
    # Les QUATRE surcharges de `GetValidTargets` convergent vers ce corps, donc le volet caster est
    # dans le chemin quel que soit l'overload emprunte. Ce n'est PAS en contradiction avec le
    # `apply_self_cast_switch=False` ci-dessous : la 7 arguments, elle, n'a pas le volet -- c'est son
    # APPELANTE qui le porte. Les deux etages sont distincts et tous deux necessaires.
    # MESURE qui l'a impose (C1_02 / seed 28704, `orksWarboss` apres un pas) : le natif rend
    # `casterReason = CasterHasNotMoved` et pose `UnitFlag.NoActionAvailable` ; sans cet etage le
    # port trouvait `Waaagh` castable et NE posait PAS le flag -- l'unite restait jouable a tort.
    # `False` et non `None` : un caster refuse est une MESURE (l'ensemble natif est vide), pas une
    # indetermination.
    if get_invalid_caster_reason(state, int(unit_id), ability):
        return False
    for tid in list(state.entities.keys()):
        if get_invalid_target_reason(state, int(unit_id), int(tid), ability,
                                     apply_self_cast_switch=False) == 0:
            return True
    return False


def _can_act(state: State, unit_id: int) -> Optional[bool]:
    """`HasTilesToMoveTo(unit) || HasActionAvailable(unit)` — le OU **court-circuite** du natif, dans
    son ORDRE (les deux branches de `VerifyUnitTurnEnded` evaluent `HasTilesToMoveTo` en premier).

    Propagation tri-etat, sans jamais fabriquer un verdict :
      * l'un des deux `True`   -> `True`  (le OU est tranche) ;
      * les deux `False`       -> `False` ;
      * sinon                  -> `None`  (indetermine : on s'abstiendra)."""
    a = has_tiles_to_move_to(state, unit_id)
    if a is True:
        return True                        # court-circuit : `HasActionAvailable` n'est pas evalue
    b = has_action_available(state, unit_id, movable_is_empty=(a is False))
    if b is True:
        return True
    if a is False and b is False:
        return False
    return None


class VerifyUnitsTurnFinishedOperation:
    """`IdunBattle.Operations.VerifyUnitsTurnFinishedOperation` (#287-r1-r1) — l'arbitre du flag
    `UnitFlag.NoActionAvailable` : il le POSE quand l'unite n'a plus d'options, et le RETIRE quand
    elle en regagne. C'est la SEULE voie native de retrait.

    `$$VerifyUnitTurnEnded(unit)`, MIRROR du decompile :

        if (unit == null) throw
        flags = unit.GetComponent<UnitFlagsComponent>()      # throw si absent
        if (flags.TurnEnded())                    return     # tour deja fini -> rien
        if (unit.TryGetComponent<HealthComponent>(out hp) && hp.IsDead())  return   # morte -> rien
        if (!flags.Has(UnitFlag.NoActionAvailable)) {
            if (HasTilesToMoveTo(unit))           return
            if (HasActionAvailable(unit))         return
            <IOperationProcessor slot 0x76>(unit)            # = MarkUnitAsNoActionAvailable (POSE)
        } else {
            if (!HasTilesToMoveTo(unit) && !HasActionAvailable(unit))  return
            <IOperationProcessor slot 0x77>(unit)            # = MarkUnitAsActionAvailable (RETRAIT)
        }

    Le couple de slots est celui deja etabli par #287-r1 (`0x76` pose / `0x77` retire) ; les deux
    passent par le FOYER UNIQUE `MarkUnitAsNoActionAvailableOperation`, `reverse` faisant la
    difference. Aucune ecriture directe du flag n'est ajoutee par cette tranche.

    ABSTENTION quand `_can_act` rend `None` : ni pose ni retrait. Le verdict native est alors
    INDETERMINE cote port (il dependrait de `AttackQuery$$HasValidTargets`), et une abstention
    conserve exactement le comportement anterieur a la tranche — alors qu'un defaut, dans un sens ou
    dans l'autre, fabriquerait une mutation que rien n'a mesuree. Le compte des abstentions est
    RENDU (`undetermined`), pour que l'amplitude du residu soit lisible et non devinee."""
    __slots__ = ()

    @staticmethod
    def verify_unit_turn_ended(state: State, unit_id: int) -> dict:
        e = state.get_entity(int(unit_id))
        if e is None:
            return {"unit": int(unit_id), "found": False, "action": None}
        fl = e.get_component(UnitFlagsComponent)
        if fl is None:
            # Le natif LEVE (composant absent = etat impossible). Offline, une entite sans
            # `UnitFlagsComponent` est une capture partielle -> on s'abstient, comme
            # `MarkUnitAsNoActionAvailableOperation`.
            return {"unit": int(unit_id), "found": False, "action": None}
        if fl.turn_ended():
            return {"unit": int(unit_id), "found": True, "action": None, "reason": "turn_ended"}
        uc = e.get_component(UnitComponent)
        if uc is not None and not uc.alive:
            # `TryGetComponent<HealthComponent>(out hp) && hp.IsDead()` -> retour immediat.
            return {"unit": int(unit_id), "found": True, "action": None, "reason": "dead"}
        has = fl.has(UnitFlagsComponent.NO_ACTION_AVAILABLE)
        can = _can_act(state, int(unit_id))
        out = {"unit": int(unit_id), "found": True, "has_flag": bool(has), "can_act": can}
        if can is None:
            out["action"] = None
            out["reason"] = "undetermined"
            return out
        if not has:
            if can:
                out["action"] = None
                return out
            out["action"] = "mark"                 # slot 0x76 : POSE
            out["mark"] = MarkUnitAsNoActionAvailableOperation.execute(state, int(unit_id))
            return out
        if not can:
            out["action"] = None
            return out
        out["action"] = "unmark"                   # slot 0x77 : RETRAIT
        out["mark"] = MarkUnitAsNoActionAvailableOperation.execute(state, int(unit_id),
                                                                   reverse=True)
        return out

    @staticmethod
    def execute(state: State) -> dict:
        """`IdunBattle.Operations.VerifyUnitsTurnFinishedOperation$$Execute()` :

            turn = state.GetComponent<TurnComponent>()
            if (turn.<+0x24> != 1) return                      # la bataille n'est pas EN COURS
            player = state.<0x29>(turn.CurrentPlayerId).GetComponent<PlayerComponent>()
            foreach (id in player.CurrentlyOwnedUnitIds)
                unit = state.<0x29>(id) ; if (unit != null) VerifyUnitTurnEnded(unit)
            machine = state.<0x29>(player.<+0x78>)             # la MACHINE OF WAR du joueur
            <le corps de VerifyMachineTurnEnded, INLINE>

        Le port balaye les entites du joueur courant (`OwnerComponent.player`) — c'est le mirror de
        `PlayerComponent$$get_CurrentlyOwnedUnitIds`, deja utilise par `_bump_turns_started` /
        `_bump_turns_finished`, y compris son `RemoveAll(<defait>)` (filtre `alive`).

        LA MACHINE OF WAR EST ECARTEE, et c'est un mirror, pas un oubli : le natif ne lui applique
        PAS `VerifyUnitTurnEnded` mais `$$VerifyMachineTurnEnded`, dont le corps est DIFFERENT — il
        ne teste ni `HasTilesToMoveTo` ni `HasActionAvailable`, mais le slot
        `IDamagePredictionQuery` **2** = `MachineCanAttackAnyUnitWithAnyAbility(machine)`, dont le
        port n'a pas plus le verdict que de `HasValidTargets`. Lui appliquer la voie UNITE poserait
        un flag sur un predicat qui n'est pas le sien. Les MoW sont donc COMPTEES a part
        (`machines_skipped`) — un compte, pas un silence.

        `turn.<+0x24> != 1` (la bataille doit etre en cours) n'a pas de substrat offline : un `State`
        de runner est par construction une bataille en cours."""
        cur = state.current_player_id
        results: list[dict] = []
        marked = unmarked = undetermined = machines = 0
        for uid, e in list(state.entities.items()):
            oc = e.get_component(OwnerComponent)
            if oc is None or oc.player != cur:
                continue
            uc = e.get_component(UnitComponent)
            if uc is None or not uc.alive:
                continue                    # `CurrentlyOwnedUnitIds` : `RemoveAll(<defait>)`
            if is_machine_of_war(e):
                machines += 1
                continue                    # -> `VerifyMachineTurnEnded`, corps distinct (cf. supra)
            r = VerifyUnitsTurnFinishedOperation.verify_unit_turn_ended(state, int(uid))
            if r.get("action") == "mark":
                marked += 1
            elif r.get("action") == "unmark":
                unmarked += 1
            elif r.get("reason") == "undetermined":
                undetermined += 1
            results.append(r)
        return {"player": cur, "units": results, "marked": marked, "unmarked": unmarked,
                "undetermined": undetermined, "machines_skipped": machines}


def verify_units_turn_finished(state: State) -> dict:
    """`Core.Services.OperationProcessor$$VerifyUnitsTurnFinished()` — le slot `IOperationProcessor`
    **0x21** (celui qui ne prend AUCUN argument, ce qui l'identifie parmi `0x22` a un argument et
    `0x23` a deux). Son corps natif est un pur delegue :
    `this.<+600>.Execute()` -> `VerifyUnitsTurnFinishedOperation$$Execute`.

    ANCRAGE : `IdunBattle.Messages.InputMessageProcessor$$RunPhase` l'invoque **deux fois** dans sa
    branche `isInternalPhase == false`, dans cet ordre LU :

        processor.<0x8e> ; processor.<0x94> ; if (!isManualTurnEnd) VerifyDrafting
        processor.<0x21>()                       <- 1er
        processor.<0x20>(0, isManualTurnEnd)
        ProcessPendingTriggeredAbilities ; VerifyDeaths ; ProcessDamageEvents ; VerifyDrafting
        processor.<0x21>()                       <- 2e

    Le port n'en pose qu'UN (`Runner.apply`), et c'est le meme choix — pour la meme raison — que
    celui deja fait pour le DRAIN #2 des triggered-abilities (cf.
    `operations/triggers/dispatch/pending.py`) : AUCUN des gestes que le natif intercale entre les
    deux appels n'est joue a cet endroit cote port, donc le second appel operereait sur un etat
    strictement identique. L'operation etant idempotente (elle met le flag en COHERENCE avec un
    predicat, elle ne l'accumule pas), le second appel serait un no-op integral — au prix d'un second
    pathfinding par unite. RESIDU NOMME."""
    return VerifyUnitsTurnFinishedOperation.execute(state)


class TurnFlowHandler:
    """Visiteur de `EndTurnMessage` + `FinishUnitTurnMessage` (mirror des handlers natifs lancant
    `EndTurnOperation` / `FinishUnitTurnOperation`). `last` = dernier resultat (diagnostic/test)."""
    __slots__ = ("state", "last")

    def __init__(self, state: State):
        self.state = state
        self.last: Optional[dict] = None

    def visit_EndTurnMessage(self, msg) -> None:
        self.last = EndTurnOperation.execute(self.state, advance=getattr(msg, "advance", True))

    def visit_FinishUnitTurnMessage(self, msg) -> None:
        # #139 : mirror `FinishUnitTurnMessage` -> `Core.Services.OperationProcessor$$FinishUnitTurn.
        uid = getattr(msg, "unit_id", None)
        if uid is None:
            self.last = {"finish_unit_turn": None, "error": "unit_id manquant"}
            return
        self.last = FinishUnitTurnOperation.execute(self.state, int(uid), forced=False)
