"""Turn flow — EndTurn -> ChangeTurn -> StartTurn (RE fidele, cf. docs/rl/runner-engine.md §2.6).

Operations natives (VA citees) :
  - `EndTurnOperation.Execute`     @180e6b3c0  : fin de tour du joueur courant.
      * per-unite (equipe du joueur finissant) : `ResetAbilitiesThatResetOnTurnEnd` @180e6cb90 +
        `DecreaseAbilityCooldowns` @180e6b0c0.
      * toutes unites : `RemoveOneTurnOnShields` @180e6c4e0 + `ActorStatisticsComponent.ResetThisTurn`.
      * `RefreshEffects` @180e6bf70 : tick d'1 tour des effets a duree de TOUTES les unites.
      * si `advance` (param_2) : enqueue le changement de tour (ChangeTurn) puis StartTurn.
  - `ChangeTurnOperation.Execute`  @180e62370  : `current = FindNextPlayer` @180e62570 ;
      `SetCurrentPlayer` @180f74af0 ; si le nouveau joueur est de type 2 (neutre) -> recurse (skip).
  - `StartTurnOperation.Execute`   @180ea3fb0  : resets per-unite (ActorStatistics/UnitFlags) +
      emet la sequence d'events de debut de tour 0x12/0x13/0x14/0x15/0x16 (`On(0x16)` = vecteur
      turn-start porte = `start_turn_triggers`).

PORTE ICI (tranche TF-A) — l'etat OBSERVABLE suivi par le runner (current_player, compteur de tours,
durees d'effet, triggers de debut de tour) :
  * RefreshEffects  -> `EffectsState.on_turn_end` (deja porte : decremente remaining_turns -> expiration
                       + cascade composite), applique a TOUTES les unites a effets.
  * RemoveOneTurnOnShields @180e6c4e0 -> `ShieldComponent.remove_one_turn` (decay d'1 tour des boucliers
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
from ..components import OwnerComponent, UnitComponent, ShieldComponent, StatsComponent
from ...entities.stats import StatType
from .triggers import start_turn_triggers


def _active_players(state: State) -> list[int]:
    """Joueurs (`OwnerComponent.player`) ayant >=1 unite VIVANTE = membres actifs de la file de tour.
    Mirror NET du test `FindNextPlayer` `turnQueue.Contains(player)` @180e62570 : l'Environment/neutre
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
    """`ChangeTurnOperation.FindNextPlayer` @180e62570 : prochain joueur CYCLIQUE (apres le courant) dans
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
    """`ChangeTurnOperation.Execute` @180e62370 : `current_player = FindNextPlayer`. Le natif recurse si
    le nouveau joueur est de type 2 (neutre/Environment) pour le SKIP ; ici l'Environment est deja exclu
    de `_active_players` (aucune unite) -> pas de recursion. Renvoie le nouveau joueur (ou None)."""
    __slots__ = ()

    @staticmethod
    def execute(state: State) -> Optional[int]:
        nxt = find_next_player(state)
        if nxt is None:
            return None
        state.current_player_id = nxt          # mirror SetCurrentPlayer @180f74af0
        return nxt


def _bump_turns_started(state: State, player: int) -> None:
    """Mirror de la boucle interne de `StartTurnOperation.Execute @180ea3fb0` : pour CHAQUE unite VIVANTE
    du joueur courant (`PlayerComponent.GetCurrentlyOwnedUnitIds`), `turnsStarted@+0x58 += 1` (compteur
    PER-UNITE, stat 12 = `GetStat(unit, 0xc)` = `UnitTurnsStartedFormula.Calculate @180f2d6c0`). Base des
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
    """`StartTurnOperation.Execute` @180ea3fb0 (squelette fidele) : incremente le compteur de tours du
    joueur (compteur GLOBAL `TurnComponent.turnsStarted`, dict @+0x38) ET le compteur PER-UNITE
    `turnsStarted@+0x58` de chaque unite du joueur courant (stat 12, `_bump_turns_started`, mig #123) puis
    emet la sequence d'events 0x12..0x16 ; ici on tire le vecteur turn-start `On(0x16)` deja porte
    (`start_turn_triggers` -> ex. TheBetrayer auto-tour). Les resets per-unite natifs (ActorStatistics/
    UnitFlags) ne sont pas suivis offline (cf. en-tete).

    APRES les triggers turn-start : passe AI-control (`run_ai_control_pass`) — joue les summons
    (`ai_controlled`) de la team courante via le playbook complet AVANT que le controleur agisse. Mirror de
    `IdunGameViews.QueueComputerActions @1804d90d0` (cf. summon_ai / docs/rl/runner-engine.md #65). No-op si
    la team n'a aucun summon (aucune regression turn-flow)."""
    __slots__ = ()

    @staticmethod
    def execute(state: State, player: int) -> list[dict]:
        state.turn_counts[player] = state.turn_counts.get(player, 0) + 1
        _bump_turns_started(state, player)     # #123 : turnsStarted PER-UNITE (stat 12) += 1 (joueur courant)
        # #60 has_moved : nouveau tour d'equipe -> reset des flags "a bouge ce tour" (mirror RemoveTurnFlags
        # natif). Chaque unite qui bouge ce tour re-marquera son id via MoveUnitOperation.
        state.moved_this_turn.clear()
        out = start_turn_triggers(state, player)
        from .summon_ai import run_ai_control_pass         # lazy : evite le cycle turnflow<->summon_ai
        out = out + run_ai_control_pass(state, player)
        return out


class EndTurnOperation:
    """`EndTurnOperation.Execute` @180e6b3c0 (squelette fidele) — cf. en-tete pour le porte/defere.
    Ordre : RefreshEffects (tick effets toutes unites) puis, si `advance`, ChangeTurn + StartTurn."""
    __slots__ = ()

    @staticmethod
    def execute(state: State, advance: bool = True) -> dict:
        # RefreshEffects @180e6bf70 : tick d'1 tour des effets a duree de TOUTES les unites (le natif
        # itere GetAllUnits, pas seulement le joueur finissant). `attacked` non suivi offline -> False
        # (les effets removed-after-attack sont rares et deja consommes one-shot a l'attaque via on_attack).
        ticked: list[int] = []
        if state.effects is not None:
            for uid in list(state.effects.by_unit.keys()):
                state.effects.on_turn_end(uid, attacked=False)
                ticked.append(int(uid))
        # RemoveOneTurnOnShields @180e6c4e0 : décay d'1 tour des boucliers à durée de TOUTES les unités
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
        # PILEIN @181223990/@181223c50 : passif fin-de-tour des grots du joueur FINISSANT à PV pleins ->
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
    """Visiteur de `EndTurnMessage` (mirror du handler natif lancant `EndTurnOperation`). `last` = dernier
    resultat (diagnostic/test)."""
    __slots__ = ("state", "last")

    def __init__(self, state: State):
        self.state = state
        self.last: Optional[dict] = None

    def visit_EndTurnMessage(self, msg) -> None:
        self.last = EndTurnOperation.execute(self.state, advance=getattr(msg, "advance", True))
