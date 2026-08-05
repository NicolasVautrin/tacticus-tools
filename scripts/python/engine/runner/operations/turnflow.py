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
  * ChangeTurn      -> `find_next_player` (prochain joueur cyclique actif).
  * StartTurn       -> incremente `state.turn_counts[player]` (compteur GLOBAL, TurnComponent+0x38) +
                       `turnsStarted@+0x58 += 1` PER-UNITE du joueur courant (stat 12, `_bump_turns_started`,
                       mig #123) + `start_turn_triggers(player)`.

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
                          UnitFlagsComponent, PositionComponent, reset_tiles_moved_this_turn)
from ...entities.stats import StatType
from .triggers import (start_turn_triggers, turn_start_other_triggers, tile_tick_triggers,
                       first_aid_heal)


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

    LE RETRAIT (`reverse = true`) EST PORTE MAIS N'A AUCUN APPELANT dans le moteur offline, et
    c'est un ETAT, pas un oubli. Son unique declencheur natif est `VerifyUnitTurnEnded`, et son
    POINT D'ANCRAGE EST LU : `IdunBattle.Messages.InputMessageProcessor$$RunPhase` invoque le slot
    `IOperationProcessor` 0x21 = `Core.Services.OperationProcessor$$VerifyUnitsTurnFinished`
    (AUCUN argument — c'est ce qui l'identifie parmi ses voisins `0x22` a un argument et `0x23` a
    deux) **deux fois** apres chaque message, en phase NON interne. Ce qui bloque le port n'est
    donc pas l'ancrage mais le CORPS : `VerifyUnitTurnEnded` appelle `HasTilesToMoveTo` =
    `MovementQuery$$GetMovableTilesFor`, que le moteur offline ne CALCULE pas (il le RECOIT du RPC
    `aiMovableTiles`). Consequence MESUREE (`probe_287r1_flags_transverse.py`, bras
    `apres_deplacement`) : apres un simple deplacement, le natif pose le flag 4 et le port non —
    ecart RESTRICTIF (le port ne pose que par `FinishUnitTurn`, donc son jeu de flags est un
    SOUS-ENSEMBLE de celui du natif, jamais permissif) et borne a ce seul flag.
    Residu `#287-r1-r1`."""
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
            from .triggers import arrived_at_final_tile_triggers
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
            from .triggers import unit_finished_turn_triggers
            out["finished_triggers"] = unit_finished_turn_triggers(state, int(unit_id))
        if newly_finished and not forced:
            from .triggers import unit_finished_turn_normally_triggers
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


def _active_players(state: State) -> list[int]:
    """Joueurs (`OwnerComponent.player`) ayant >=1 unite VIVANTE = membres actifs de la file de tour.
    Mirror NET du test `FindNextPlayer` `turnQueue.Contains(player)` IdunBattle.Operations.ChangeTurnOperation$$FindNextPlayer : l'Environment/neutre
    (sans unite) et les equipes eliminees (toutes mortes) en sont naturellement exclus. Ordre = ids
    croissants (le natif utilise un tableau d'ordre des joueurs ; equivalent pour 2 equipes = le cas du
    runner ; >2 joueurs = raffinement a valider)."""
    players: set[int] = set()
    for e in state.entities.values():
        oc = e.get_component(OwnerComponent)
        uc = e.get_component(UnitComponent)
        if oc is None or oc.player is None:
            continue
        if uc is not None and not uc.alive:
            continue
        players.add(int(oc.player))
    return sorted(players)


def find_next_player(state: State) -> Optional[int]:
    """`IdunBattle.Operations.ChangeTurnOperation$$FindNextPlayer : prochain joueur CYCLIQUE (apres le courant) dans
    l'ordre des joueurs, present dans la file de tour active (ici = a >=1 unite vivante). Renvoie None si
    aucun (match fini / plus de joueur actif). 1 seul joueur actif -> lui-meme (le natif boucle aussi)."""
    order = _active_players(state)
    if not order:
        return None
    cur = state.current_player_id
    if cur not in order:
        return order[0]
    n = len(order)
    i = order.index(cur)
    return order[(i + 1) % n]      # cyclique : prochain joueur actif (n==1 -> lui-meme)


class ChangeTurnOperation:
    """`IdunBattle.Operations.ChangeTurnOperation$$Execute : `current_player = FindNextPlayer`. Le natif recurse si
    le nouveau joueur est de type 2 (neutre/Environment) pour le SKIP ; ici l'Environment est deja exclu
    de `_active_players` (aucune unite) -> pas de recursion. Renvoie le nouveau joueur (ou None)."""
    __slots__ = ()

    @staticmethod
    def execute(state: State) -> Optional[int]:
        nxt = find_next_player(state)
        if nxt is None:
            return None
        state.current_player_id = nxt          # mirror IdunBattle.Entities.Components.TurnComponent$$SetCurrentPlayer
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
    """`IdunBattle.Operations.StartTurnOperation$$Execute (squelette fidele) : incremente le compteur de tours du
    joueur (compteur GLOBAL `TurnComponent.turnsStarted`, dict @+0x38) ET le compteur PER-UNITE
    `turnsStarted@+0x58` de chaque unite du joueur courant (stat 12, `_bump_turns_started`, mig #123) puis
    emet la sequence d'events 0x12..0x16 ; ici on tire le vecteur turn-start `On(0x16)` deja porte
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
        state.turn_counts[player] = state.turn_counts.get(player, 0) + 1
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
        from .refresh_effects import refresh_stat_modifier_effects
        refresh_stat_modifier_effects(state)
        out = start_turn_triggers(state, player)
        from .summon_ai import run_ai_control_pass         # lazy : evite le cycle turnflow<->summon_ai
        out = tile_ticks + first_aid + living_metal + out + run_ai_control_pass(state, player)
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
        # PORTEE PARTIELLE, et c'est DIT : le port n'emet d'ici que la jambe `On(0x28 =
        # UnitFinishedTurn)` de cet appel, sous son gate natif (« le flag TurnFinished vient d'etre
        # POSE »). Les deux autres jambes (`On(0x1c = ArrivedAtFinalTile)` et `On(0x29 =
        # UnitFinishedTurnNormally)`) restent NON EMISES depuis ce site : les cabler ferait firer
        # `SpiritualLeaderAbility`/`ArcaneShieldAbility`/`MyWillBeDoneOverlordAttackAbility` pour
        # toute unite n'ayant PAS agi du tour -- un rayon de souffle hors de la tranche #448-r2.
        # RESIDU NOMME. (Le flag lui-meme n'est pas pose non plus : meme raison.)
        #
        # CE QUE CA REMPLACE : la boucle bespoke `land_deep_strike` d'avant #448-r2, qui faisait
        # atterrir ICI toutes les unites deep-strike du joueur finissant. Le retrait de
        # `TeleportStrike_TeleportingIn` est desormais porte par les TROIS triggers natifs de
        # l'effet (`On(4)`, `On(0x2a = PreUnitAbility)`, `On(0x28 = UnitFinishedTurn)`) -- mesure live : le natif retire l'effet DES LE
        # MOUVEMENT ou DES LE CAST, pas en fin de tour. Ce site-ci ne couvre donc plus que le cas
        # « l'unite n'a rien fait de son tour », qui est exactement ce que le natif couvre ici.
        from .triggers import unit_finished_turn_triggers
        landed: list[dict] = []
        for uid, e in state.entities.items():
            oc = e.get_component(OwnerComponent)
            if oc is None or oc.player != finishing:
                continue
            fl = e.get_component(UnitFlagsComponent)
            if fl is not None and fl.has(UnitFlagsComponent.TURN_FINISHED):
                continue                       # `flags.Add(TurnFinished)` rend FAUX -> aucune publication
            landed += unit_finished_turn_triggers(state, int(uid))
        # (4) vecteur `On(0x17 = TurnEnd)` — DEUX consommateurs portes (inventaire re-derive du registre
        # par `probe_n8b_turnend_consumers.py`) : le dispatch generique `ABILITY_TRIGGERS`
        # (`RadSaturationAbility`, branche `NOT HasFlag(owner, Moved)`) et le bespoke
        # IdunBattleLogic.Entities.Abilities.Active.Loki.PileInAbility$$CreateBehaviour /
        # IdunBattleLogic.Entities.Abilities.Active.Loki.PileInAbility$$CreateTrigger (grots du joueur
        # FINISSANT a PV pleins -> auto-dedoublement, 75-5%/grot). AVANT le tick d'effets : leurs gates
        # lisent donc l'etat PRE-tick, comme dans le natif. No-op si aucun porteur.
        from .triggers import end_turn_summon_triggers
        pilein = end_turn_summon_triggers(state, finishing)
        # (5) IdunBattle.Operations.EndTurnOperation$$RefreshEffects : tick d'1 tour des effets a duree de TOUTES les unites (le natif
        # itere GetAllUnits, pas seulement le joueur finissant). `attacked` non suivi offline -> False
        # (les effets removed-after-attack sont rares et deja consommes one-shot a l'attaque via on_attack).
        # Le natif n'inflige AUCUN degat ici : `RefreshEffects` = `EffectComponent.RemoveOneTurn` + events,
        # puis `Core.Services.OperationProcessor$$RefreshEffects` -> `RefreshEffectsOperation$$Execute`
        # (branche de retrait). Les DoT de tuile passent, eux, par les events 0x12/0x14 de StartTurn.
        ticked: list[int] = []
        if state.effects is not None:
            for uid in list(state.effects.by_unit.keys()):
                state.effects.on_turn_end(uid, attacked=False)
                ticked.append(int(uid))
        # `<Effect>.RevertInternal` -> `IdunBattle.Entities.Effects.AStatModifierEffect$$RevertModification`
        # (ChangeStat part 6) : un effet que le tick vient de faire EXPIRER doit SORTIR sa `ValueModification`
        # du `UnitStats`. Sans ce foyer, seul le retrait EXPLICITE (feuille `RemoveEffect`) revertait — un
        # stat-mod a TIMER (ex. `Thrilled` 1434 de ThrillSeekers, +15 CritChance pour 1 round) restait
        # applique pour toujours. No-op strict pour toute instance sans `stat_mod_source`. Reste COLLE au
        # tick (mirror du `RefreshEffectsOperation` que `RefreshEffects` appelle en sortie de boucle).
        from .effects import revert_stat_mods_of_removed_effects
        reverted = revert_stat_mods_of_removed_effects(state)
        if not advance:
            return {"ticked": ticked, "shields_ticked": shields_ticked, "landed": landed,
                    "pilein": pilein, "next_player": None, "start": None,
                    "stat_mods_reverted": reverted}
        nxt = ChangeTurnOperation.execute(state)
        start = StartTurnOperation.execute(state, nxt) if nxt is not None else None
        return {"ticked": ticked, "shields_ticked": shields_ticked, "landed": landed,
                "pilein": pilein, "next_player": nxt, "start": start,
                "stat_mods_reverted": reverted}


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
