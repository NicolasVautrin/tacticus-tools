"""Turn flow — EndTurn -> ChangeTurn -> StartTurn (RE fidele, cf. docs/rl/runner-engine.md §2.6).

Operations natives (VA citees) :
  - `IdunBattle.Operations.EndTurnOperation$$Execute  : fin de tour du joueur courant.
      * per-unite (equipe du joueur finissant) : `IdunBattle.Operations.EndTurnOperation$$ResetAbilitiesThatResetOnTurnEnd +
        `IdunBattle.Operations.EndTurnOperation$$DecreaseAbilityCooldowns.
      * toutes unites : `IdunBattle.Operations.EndTurnOperation$$RemoveOneTurnOnShields + `ActorStatisticsComponent.ResetThisTurn`.
      * `IdunBattle.Operations.EndTurnOperation$$RefreshEffects : tick d'1 tour des effets a duree de TOUTES les unites.
      * si `advance` (param_2) : enqueue le changement de tour (ChangeTurn) puis StartTurn.
  - `IdunBattle.Operations.ChangeTurnOperation$$Execute  : `current = IdunBattle.Operations.ChangeTurnOperation$$FindNextPlayer ;
      `IdunBattle.Entities.Components.TurnComponent$$SetCurrentPlayer ; si le nouveau joueur est de type 2 (neutre) -> recurse (skip).
  - `IdunBattle.Operations.StartTurnOperation$$Execute  : resets per-unite (ActorStatistics/UnitFlags) +
      emet la sequence d'events de debut de tour 0x12/0x13/0x14/0x15/0x16 (`On(0x16)` = vecteur
      turn-start porte = `start_turn_triggers`).

PORTE ICI (tranche TF-A) — l'etat OBSERVABLE suivi par le runner (current_player, compteur de tours,
durees d'effet, triggers de debut de tour) :
  * RefreshEffects  -> `EffectsState.on_turn_end` (deja porte : decremente remaining_turns -> expiration
                       + cascade composite), applique a TOUTES les unites a effets.
  * IdunBattle.Operations.EndTurnOperation$$RemoveOneTurnOnShields -> `ShieldComponent.remove_one_turn` (decay d'1 tour des boucliers
                       a duree de TOUTES les unites ; retire les instances a 0).
  * ChangeTurn      -> `find_next_player` (prochain joueur cyclique actif).
  * StartTurn       -> incremente `state.turn_counts[player]` (compteur GLOBAL, TurnComponent+0x38) +
                       `turnsStarted@+0x58 += 1` PER-UNITE du joueur courant (stat 12, `_bump_turns_started`,
                       mig #123) + `start_turn_triggers(player)`.

DEFERE (etat NON suivi offline -> TODO, en miroir documente) :
  * `DecreaseAbilityCooldowns` (le runner ne suit pas de compteur de cooldown d'ability offline) ;
  * `ActorStatisticsComponent.ResetThisTurn` (stats per-tour non suivies : attaques recues/portees...) ;
  * `ResetAbilitiesThatResetOnTurnEnd` ; resets per-unite UnitFlags de StartTurn ;
  * `PickNextUnit` (ordre intra-tour = DECISION de l'IA, pas une mutation moteur -> couche playbook).
"""
from __future__ import annotations

from typing import Optional

from ..state import State
from ..components import (OwnerComponent, UnitComponent, ShieldComponent, StatsComponent,
                          UnitFlagsComponent)
from ...entities.stats import StatType
from .triggers import (start_turn_triggers, turn_start_other_triggers, tile_tick_triggers,
                       first_aid_heal)


class FinishUnitTurnOperation:
    """`IdunBattle.Operations.FinishUnitTurnOperation$$Execute (#139) — clot le tour d'UNE unite :
      * si `forced` : Add(UnitFlag 27 = TURN_FINISHED_FORCED) ;
      * Add(ArrivedAtFinalTile=1) — si nouvellement pose et !forced, le natif publie l'event 0x1c ;
      * Add(TurnFinished=3)       — si nouvellement pose, events 0x29 (+0x2a si !forced) + step Events(0xd) ;
      * reset du cache de mouvement (MovementComponent@+0x18/+0x10) + slot processor 0x76 (Verify...).
    OFFLINE on porte la MUTATION (les 3 flags) ; events/steps de stream + verify = couche view/process non
    suivie (documente). Declencheurs natifs : `Core.Services.OperationProcessor$$FinishUnitTurn (appele par
    `IdunBattle.Operations.ActiveAbilityOperation$$AddFlagsAfterAbilityExecution quand l'ability TERMINE le tour),
    `FinishUnitTurnMessage`, et `FinishUnitTurnBehaviour` IdunBattle.Entities.Behaviours.FinishUnitTurnBehaviour$$Execute (DSL)."""
    __slots__ = ()

    @staticmethod
    def execute(state: State, unit_id: int, forced: bool = False) -> dict:
        e = state.get_entity(unit_id)
        if e is None:
            return {"unit": int(unit_id), "found": False}
        fl = e.get_component(UnitFlagsComponent)
        if fl is None:
            fl = e.add_component(UnitFlagsComponent())
        if forced:
            fl.add(UnitFlagsComponent.TURN_FINISHED_FORCED)
        newly_arrived = not fl.has(UnitFlagsComponent.ARRIVED_AT_FINAL_TILE)
        fl.add(UnitFlagsComponent.ARRIVED_AT_FINAL_TILE)
        newly_finished = not fl.has(UnitFlagsComponent.TURN_FINISHED)
        fl.add(UnitFlagsComponent.TURN_FINISHED)
        return {"unit": int(unit_id), "found": True, "forced": bool(forced),
                "newly_arrived": newly_arrived, "newly_finished": newly_finished}


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

    APRES les triggers turn-start : passe AI-control (`run_ai_control_pass`) — joue les summons
    (`ai_controlled`) de la team courante via le playbook complet AVANT que le controleur agisse. Mirror de
    `IdunBattle.View.Game.IdunGameViews$$QueueComputerActions` (cf. summon_ai / docs/rl/runner-engine.md #65). No-op si
    la team n'a aucun summon (aucune regression turn-flow)."""
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
        # #128 tile-effects ROUND-TICK : StartTurn emet la SEQUENCE d'events 0x12->0x13->0x14->0x15->0x16
        # (VERIFIE IdunBattle.Operations.StartTurnOperation$$Execute : 5 emissions FUN_180026490(...,0x12/0x13/0x14/0x15/0x16) en fin d'Execute ;
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
        out = start_turn_triggers(state, player)
        from .summon_ai import run_ai_control_pass         # lazy : evite le cycle turnflow<->summon_ai
        out = tile_ticks + first_aid + living_metal + out + run_ai_control_pass(state, player)
        return out


class EndTurnOperation:
    """`IdunBattle.Operations.EndTurnOperation$$Execute (squelette fidele) — cf. en-tete pour le porte/defere.
    Ordre : RefreshEffects (tick effets toutes unites) puis, si `advance`, ChangeTurn + StartTurn."""
    __slots__ = ()

    @staticmethod
    def execute(state: State, advance: bool = True) -> dict:
        # IdunBattle.Operations.EndTurnOperation$$RefreshEffects : tick d'1 tour des effets a duree de TOUTES les unites (le natif
        # itere GetAllUnits, pas seulement le joueur finissant). `attacked` non suivi offline -> False
        # (les effets removed-after-attack sont rares et deja consommes one-shot a l'attaque via on_attack).
        ticked: list[int] = []
        if state.effects is not None:
            for uid in list(state.effects.by_unit.keys()):
                state.effects.on_turn_end(uid, attacked=False)
                ticked.append(int(uid))
        # IdunBattle.Operations.EndTurnOperation$$RemoveOneTurnOnShields : décay d'1 tour des boucliers à durée de TOUTES les unités
        # (ShieldComponent.RemoveOneTurn → décrémente remaining, retire les instances à 0).
        shields_ticked: list[tuple] = []
        for uid, e in state.entities.items():
            shc = e.get_component(ShieldComponent)
            if shc is not None and shc.shields:
                ch = shc.remove_one_turn()
                if ch["removed"] or ch["decremented"]:
                    shields_ticked.append((int(uid), ch))
        # DEEP-STRIKE LANDING : les unites TeleportStrike du joueur FINISSANT atterrissent a la fin de leur
        # 1er tour (ground truth live ds_landing : discret, PAS un tick de duree) -> retire TeleportingIn +
        # init des passives deferrees (aura PathOfCommand). Mirror natif : landing = InitializeActorAbilities.
        from .spawn import land_deep_strike
        finishing = state.current_player_id
        landed: list[dict] = []
        for uid, e in state.entities.items():
            oc = e.get_component(OwnerComponent)
            if oc is not None and oc.player == finishing:
                r = land_deep_strike(state, uid)
                if r is not None:
                    landed.append(r)
        # PILEIN IdunBattleLogic.Entities.Abilities.Active.Loki.PileInAbility$$CreateBehaviour/IdunBattleLogic.Entities.Abilities.Active.Loki.PileInAbility$$CreateTrigger : passif fin-de-tour des grots du joueur FINISSANT à PV pleins ->
        # auto-dédoublement (WithStatsFromConfig(PileIn), 75-5%/grot). Après le tick d'effets (un DoT qui
        # entame les PV du grot le disqualifie du gate PV-pleins). No-op si aucun grot PileIn.
        from .triggers import end_turn_summon_triggers
        pilein = end_turn_summon_triggers(state, finishing)
        if not advance:
            return {"ticked": ticked, "shields_ticked": shields_ticked, "landed": landed,
                    "pilein": pilein, "next_player": None, "start": None}
        nxt = ChangeTurnOperation.execute(state)
        start = StartTurnOperation.execute(state, nxt) if nxt is not None else None
        return {"ticked": ticked, "shields_ticked": shields_ticked, "landed": landed,
                "pilein": pilein, "next_player": nxt, "start": start}


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
