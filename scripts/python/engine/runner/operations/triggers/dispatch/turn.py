"""Vecteurs d'event de la face TOUR (round-tick des tuiles, debut et fin de tour),
extraits de `triggers/dispatch.py` (scission du module >1000 lignes, tache #169 --
deplacement VERBATIM, zero changement de comportement).

`On(0x12)`/`On(0x14)` (tile-tick), `On(0x16=TurnStart)`, `TurnStart_Other`, `On(0x17=TurnEnd)`."""
from __future__ import annotations

from ....state import State
from ....components import OwnerComponent, UnitComponent, HealthComponent
from .....dsl.event_trigger_type import EventTriggerType
from ..base import TriggerEvent
from ..tiles import dry_bush_fire_spread
from .core import evaluate_trigger_operation
from .....dsl.base import Const
from .....entities.triggers import MaybeTrigger
from ....abilities.behaviours.context import entities_from_state
from ...minimal_health import reset_times_attacked, evaluate_minimal_health
from ...spawn import SpawnUnitOperation


def tile_tick_triggers(state: State) -> list[dict]:
    """Vecteur ROUND-TICK des tile-effects (#128) : `IdunBattle.Operations.StartTurnOperation$$Execute émet la séquence
    0x12/0x13/0x14/... → ici on tire `On(0x12)` (Contaminated re-apply IdunBattle.Entities.Effects.Loki.ContaminatedEffect$$CreateHandleTriggerAbilitiesInternal) puis `On(0x14)` (Fire DoT
    IdunBattleLogic.Entities.Abilities.Active.Loki.EnvFireTileAbility$$CreateTrigger + DryBush spread IdunBattleLogic.Entities.Abilities.Tiles.DryBushFireSpreadAbility$$CreateTrigger). Chaque tile-effect trigger (owner=tuile) matche sur l'occupant
    de SA tuile. Ordre 0x12 puis 0x14, AVANT le turn-start `On(0x16)` (ordre exact = HYPOTHÈSE à valider,
    cf. verdict RE #128). La PROPAGATION DryBush (`dry_bush_fire_spread`) tourne APRÈS le DoT `On(0x14)` : le
    DoT frappe les occupants des tuiles en feu AU DÉBUT du tick, puis la propagation allume les voisines pour
    le tick SUIVANT (snapshot source → pas de cascade même-tick). No-op si aucun tile-effect actif."""
    out: list[dict] = []
    for eid in (EventTriggerType.TurnStart_EffectActivation, EventTriggerType.TurnStart_EnvironmentEffects):
        ev = TriggerEvent(eid, -1, -1, ranged=False, profile=None)
        out += evaluate_trigger_operation(state, ev)
    out += dry_bush_fire_spread(state)    # `DryBushFireSpreadAbility` On(0x14) : feu DryBush -> DryBush adjacent (10%)
    return out


def start_turn_triggers(state: State, player_id: int) -> list[dict]:
    """Vecteur DÉBUT DE TOUR (mirror `IdunBattle.Operations.StartTurnOperation$$Execute émettant l'event `On(0x16)`).
    Construit l'événement turn-start {player=player_id} et lance `evaluate_trigger_operation`. Déclenche
    les auto-tours forcés du player courant (ex. TheBetrayer de worldKharn : move+attaque). `actor`/`target`
    = -1 (pas d'acteur unique ; chaque trigger filtre sur `ev.player_id` == son owner). No-op si aucun
    trigger turn-start ne matche (ou pas de board/rng pour le move+attaque).

    #G6a : au boundary de tour, remet a 0 le compteur d'attaques recues (`HasBeenAttackedAmountThisTurn`) de
    toutes les unites PUIS re-evalue l'ActiveCondition des HP-floors Hypersensory (`IsEnemyTurn(owner) &
    Not(attacked>=1)`) -> Apply (snapshot 50% du HP courant) au tour ENNEMI du porteur, Revert sinon. Avant
    l'emission de l'event (l'etat floor doit etre pose quand les triggers turn-start s'executent)."""
    from ...revive import reset_revive_gates
    reset_times_attacked(state)
    reset_revive_gates(state)          # case-66 : REACTIVE le passif revive (once-per-turn) au turn-start
    evaluate_minimal_health(state, player_id)
    ev = TriggerEvent(EventTriggerType.TurnStart_Actions, -1, -1, ranged=False, profile=None, player_id=player_id)
    return evaluate_trigger_operation(state, ev)


def turn_start_other_triggers(state: State, player_id: int) -> list[dict]:
    """Vecteur `On(TurnStart_Other=0x13=19)` — 2e des 5 events emis par `IdunBattle.Operations.StartTurnOperation$$Execute` (sequence 0x12->0x13->0x14->0x15->0x16 ; cf. turnflow.py). Dispatch GENERIQUE du
    registre `TRAIT_TRIGGERS` sur cet event. Consommateur : `LivingMetalRepairAbility` (#203, regen %
    PV des Necron endommages, `OwnerIsActor` via `player_id`). Le meme event 0x13 porte aussi FirstAid
    (tile-effect, reste bespoke dans tiles.py). `actor`/`target` = -1 (chaque trigger filtre sur
    `ev.player_id`). No-op si aucun porteur LivingMetal endommage du player courant."""
    ev = TriggerEvent(EventTriggerType.TurnStart_Other, -1, -1, ranged=False, profile=None, player_id=player_id)
    return evaluate_trigger_operation(state, ev)


def unit_finished_turn_triggers(state: State, unit_id: int) -> list[dict]:
    """Vecteur `On(0x28 = UnitFinishedTurn = 40)` -- le DEUXIEME des trois evenements que
    `IdunBattle.Operations.FinishUnitTurnOperation$$Execute` publie (#354) :

        if (flags.Add(0x01 = ArrivedAtFinalTile) && !isTerminated)  publish On(0x1c)
        if (flags.Add(0x03 = TurnFinished)) {
            publish On(0x28 = UnitFinishedTurn)                <- CE vecteur
            if (!isTerminated) publish On(0x29 = UnitFinishedTurnNormally)
        }

    Son gate est le SEUL « le flag TurnFinished vient d'etre POSE » -- contrairement a `On(0x29 = UnitFinishedTurnNormally)`,
    il est emis MEME sur une terminaison FORCEE (`isTerminated`). Le gate vit chez l'appelant
    (`operations/turnflow.py`), comme pour ses deux voisins. `actor` = `target` = l'unite qui clot.

    Consommateur porte (#448-r2) : le 3e trigger d'`IdunBattle.Entities.Effects.Loki.
    ATeleportingEffect$$CreateHandleTriggerAbilitiesInternal` -- `On(0x28 = UnitFinishedTurn) & OwnerIsActor &
    HasTile(Owner)` -> `RemoveEffect(EffectSelf)`, i.e. l'ATTERRISSAGE d'une unite deep-strike qui
    finit son tour sans avoir ni bouge ni caste. Ce vecteur etait un RESIDU NOMME jusqu'ici (« le
    jour ou une ability l'ecoute, elle s'ajoute ICI, pas dans un fork ») : c'est ce jour-la.

    Le canal `TriggeringAbility` est VIDE sur cet evenement, comme sur `On(0x29 = UnitFinishedTurnNormally)` -- meme site
    d'emission, meme `Nullable<AbilityOrEffect>` a zero."""
    ev = TriggerEvent(EventTriggerType.UnitFinishedTurn, int(unit_id), int(unit_id),
                      ranged=False, profile=None)
    return evaluate_trigger_operation(state, ev)


def unit_finished_turn_normally_triggers(state: State, unit_id: int) -> list[dict]:
    """Vecteur `On(0x29 = UnitFinishedTurnNormally = 41)` — le TROISIEME et dernier evenement que
    `IdunBattle.Operations.FinishUnitTurnOperation$$Execute` publie, dans cet ordre (decompile relu,
    #354) :

        if (flags.Add(0x01 = ArrivedAtFinalTile) && !isTerminated)  publish On(0x1c)
        if (flags.Add(0x03 = TurnFinished)) {
            publish On(0x28 = UnitFinishedTurn)
            if (!isTerminated) publish On(0x29 = UnitFinishedTurnNormally)
        }

    Les DEUX gates sont donc « le flag TurnFinished vient d'etre POSE » et « la terminaison n'est pas
    FORCEE » ; ils vivent chez l'appelant (`operations/turnflow.py::FinishUnitTurnOperation.execute`),
    exactement comme le gate d'`arrived_at_final_tile_triggers`. `actor` = `target` = l'unite qui
    clot (le natif passe `unit` dans les TROIS slots de l'`AbilityEntities`).

    `On(0x28 = UnitFinishedTurn)` a son propre vecteur juste au-dessus (#448-r2) -- il precede
    celui-ci et n'a pas le gate `!isTerminated`.

    Consommateur : `MyWillBeDoneOverlordAttackAbility` (passif `necroOverlord` : un allie adjacent
    attaque quand l'Overlord clot son activation). No-op si personne n'ecoute.

    Le canal `TriggeringAbility` est VIDE sur cet evenement (le natif publie un
    `Nullable<AbilityOrEffect>` a ZERO -- controle fait au desassemblage) : on ne threade donc
    AUCUN `triggering_ability`, et c'est le mirror exact."""
    ev = TriggerEvent(EventTriggerType.UnitFinishedTurnNormally, int(unit_id), int(unit_id),
                      ranged=False, profile=None)
    return evaluate_trigger_operation(state, ev)


PILEIN_MIN_OWNER_TURNS = 2      # `OwnerHasFinishedMinTurns(2)` — gate du trigger PileIn IdunBattleLogic.Entities.Abilities.Active.Loki.PileInAbility$$CreateTrigger


def end_turn_summon_triggers(state: State, player_id: int) -> list[dict]:
    """Vecteur FIN DE TOUR (`On(0x17=TurnEnd=23)`). Deux volets :

    1. DISPATCH GENERIQUE `On(TurnEnd)` (registre `ABILITY_TRIGGERS`) — ability-triggers TurnEnd. Consommateur :
       `RadSaturationAbility` (branche 3 : le Skitarii Vanguard qui n'a PAS bouge ce tour contamine sa tuile en
       fin de tour ; gate `not unit_has_moved(state, owner)` = `NOT HasFlag(owner, UnitFlag.Moved)`).
       `player_id` scope l'`OwnerIsActor`.
    2. Passif d'auto-dédoublement `PileInAbility` (BESPOKE : trigger IdunBattleLogic.Entities.Abilities.Active.Loki.PileInAbility$$CreateTrigger `On(0x17)` &
       `OwnerHasFinishedMinTurns(2)` & `IsUnitWithStatAmount(Health Cur==Max)` ; behaviour IdunBattleLogic.Entities.Abilities.Active.Loki.PileInAbility$$CreateBehaviour) — chaque
       grot (passif `PileIn`) du `player_id`, a PV PLEINS et ayant lui-meme fini >=2 tours, s'auto-dédouble
       avec proba `chance − chance_2 × (#grots amis)` = 75 − 5×n. Double = `execute_pilein_replica`.
       Snapshot AVANT la boucle (« acts on its NEXT turn »).

       GATE `OwnerHasFinishedMinTurns(2)` — PER-UNITE, et sur `turnsFinished`. Chaine native :
       `IdunBattleLogic.Entities.DSLFactory$$OwnerHasFinishedMinTurns(2)` construit un
       `IdunBattle.Entities.Triggers.UnitHasFinishedMinTurnsAbilityTrigger` (selecteur = `factory+0x148`
       = Self/Owner, amount = 2 @+0x18, unitSelectionType = 3 @+0x28) dont le
       `UnitHasFinishedMinTurnsAbilityTrigger$$ShouldTrigger` fait
       `IdunBattle.Entities.UnitExtensions$$GetTurnsFinished(selecteur.Select(entities)) >= amount` —
       donc le compteur de l'UNITE-PORTEUR (`UnitComponent + 0x5c`), jamais celui du JOUEUR.
       Le port lisait `state.turn_counts[player]` (`TurnComponent + 0x38`, granularite JOUEUR) : deux
       erreurs a la fois, l'une PERMISSIVE (un grot ne d'un `GetEmRuntz` au tour 5 passait le gate des
       sa 1re fin de tour, alors que le natif lui demande d'en finir DEUX), l'autre BLOQUANTE (un runner
       monte depuis un snapshot a `turn_counts == {}` -> gate faux pour TOUT LE MONDE, PileIn mort).
       Le compteur juste vit maintenant sur `UnitComponent.turns_finished` (bumpe par
       `turnflow._bump_turns_finished`, mirror d'`EndTurnOperation.Execute`).

       GATE `Maybe(chance)` (O4a) — le behaviour natif se termine par
           `If( Maybe(Difference(Direct(chance), Multiply(Count(Friends(UnitsWithSameVisualId(Self))),
                                                          Direct(chance_2)))),
                Spawn(Self@0x148, <tuile>, summonId, options),
                Nothing() )`
       ou `Maybe` a UN argument -> `IdunBattle.Entities.Triggers.MaybeTrigger$$ShouldTrigger` (le PREDICAT,
       pas le noeud EFFET homonyme). CONSEQUENCE RNG, et c'est tout l'enjeu : le selecteur de tuile
       `First(SortByFormula(Randomize(CanAddUnit(AdjacentTiles(Self))), ...), 1)` est un argument du
       `Spawn`, donc de la branche THEN du `If` -> `IdunBattle.Entities.Behaviours.IfBehaviour$$Execute`
       ne l'evalue QUE si le `Maybe` a reussi. Le compte natif par grot candidat est donc
       **1 `next_bool(chance)`, PUIS `len(pool)` tirages du `Randomize` SEULEMENT en cas de succes** —
       la ou le port DETERMINISTE d'avant ne tirait PAS le `Maybe` et payait le `Randomize` a tous les
       coups. Le cap naturel `chance <= 0` (n >= 15 grots) est conserve : `next_bool(<=0)` est toujours
       faux, mais le natif le tire quand meme (le `Maybe` est evalue avant tout test de chance) -> on
       laisse le tirage se faire et c'est son verdict qui tranche.

    (PileIn reste BESPOKE — pas dans `ABILITY_TRIGGERS` -> pas de double-fire par le dispatch generique.
     RESIDU ASSUME : seul le gate `Maybe` est un noeud DSL ; le reste du behaviour (Count/Difference/
     Multiply, le selecteur de tuile) demeure impératif dans `spawn.py`.)"""
    import gameconfig as GC
    # 1. dispatch generique On(TurnEnd) : RadSaturation (fin de tour si pas bouge) + tout futur ability-trigger TurnEnd.
    ev = TriggerEvent(EventTriggerType.TurnEnd, -1, -1, ranged=False, profile=None, player_id=player_id)
    out: list[dict] = evaluate_trigger_operation(state, ev)
    # 2. PileIn (bespoke). Le gate `OwnerHasFinishedMinTurns(2)` est PER-PORTEUR (cf. docstring) ->
    # il vit dans la boucle de selection des candidats, pas en sortie anticipee du vecteur.
    consts = (GC.ability("PileIn") or {}).get("constants") or {}
    chance0 = int(consts.get("chance") or 75)
    chance_2 = int(consts.get("chance_2") or 5)
    # snapshot des grots-PileIn vivants du player, à PV PLEINS (avant tout spawn de ce tour).
    candidates: list[tuple] = []
    for eid, e in state.entities.items():
        uc = e.get_component(UnitComponent)
        oc = e.get_component(OwnerComponent)
        hc = e.get_component(HealthComponent)
        if uc is None or oc is None or hc is None or not uc.alive:
            continue
        if oc.player != int(player_id):
            continue
        if "PileIn" not in ((GC.unit(uc.visual_id) or {}).get("passiveAbilities") or []):
            continue
        # `OwnerHasFinishedMinTurns(2)` -> `GetTurnsFinished(owner) >= 2` (`UnitComponent + 0x5c`).
        if int(uc.turns_finished or 0) < PILEIN_MIN_OWNER_TURNS:
            continue
        if hc.hp < hc.hp_max:                  # `IsUnitWithStatAmount(Health Cur==Max)` = PV PLEINS
            continue
        candidates.append((eid, uc.visual_id, oc.team))
    # NB : `out` porte deja les resultats du dispatch generique On(TurnEnd) (volet 1) — on APPEND PileIn dessus.
    for (gid, vid, team) in candidates:
        # `UnitsWithSameVisualId(self) & Friends(3)` -> Count = grots amis (même visualId) hors self.
        n = sum(1 for e2 in state.entities.values()
                if e2.id != gid
                and (u2 := e2.get_component(UnitComponent)) is not None and u2.alive and u2.visual_id == vid
                and (o2 := e2.get_component(OwnerComponent)) is not None and o2.team == team)
        chance = chance0 - chance_2 * n        # `Difference(75, Multiply(count, 5))`
        # `If( Maybe(chance), Spawn(...), Nothing() )` — le PREDICAT `MaybeTrigger` (1 `next_bool`),
        # evalue AVANT le selecteur de tuile du `Spawn` (qui, lui, consomme `len(pool)` tirages via
        # `Randomize`). Echec -> branche `Nothing()` : ni spawn, ni tirage de placement.
        ents = entities_from_state(state, gid, gid)          # AbilityEntities du trigger (Self@0x148)
        if not MaybeTrigger(state.rng, Const(int(chance))).should_trigger(ents):
            continue
        spawned = SpawnUnitOperation.execute_pilein_replica(state, gid)
        if spawned:
            out.append({"grot": gid, "spawned": spawned, "chance": chance, "n_grots": n})
    return out
