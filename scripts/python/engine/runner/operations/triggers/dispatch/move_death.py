"""Vecteurs d'event des faces MOUVEMENT et MORT, extraits de `triggers/dispatch.py`
(scission du module >1000 lignes, tache #169 -- deplacement VERBATIM, zero changement de
comportement).

Mouvement : `On(0x24)`/`On(4)`/`On(0x1d)` (after-move), arrivee sur tuile finale,
deplacement force (`UnitDisplaced`), kills declenches par un move.
Mort : `On(1=PreUnitDeath)`, `PreUnitDeath_2`, `UnitDeath`, `UnitDefeated`, revive,
resurrection, plus `On(PreEffectAdded)`."""
from __future__ import annotations

from typing import Optional

from ....state import State
from ....components import (StatsComponent, UnitComponent, PositionComponent,
                            UnitFlagsComponent)
from .....dsl.event_trigger_type import EventTriggerType
from ..base import TriggerEvent
from .core import evaluate_trigger_operation


def after_move_triggers(state: State, mover_id: int) -> list[dict]:
    """Vecteur after-move (mirror `IdunBattle.Operations.MoveUnitOperation$$EvaluateAfterMoveTriggers → dispatch).
    Le natif émet, dans l'ordre, `On(0x24=UnitPositionChanged_1)`, `On(4=UnitAfterMove)` (overwatch) PUIS
    `On(0x1d=UnitPositionChanged_2)`. On dispatche les trois : `On(0x24)` déclenche la POSE de couverture
    de la tuile d'arrivée (`LightCoverAbility`, tile-ability écoutant cet event — résidu O3, cf.
    `triggers/tiles.py::light_cover_on_enter`) ; `On(0x1d)` déclenche DecoysAndMisdirection (G2 —
    ennemi/allié qui marche sur un decoy allié crushé par `_kill_steppable_units`, G1). No-op si aucun
    trigger ne matche (ou pas de board/rng).

    ORDRE NATIF COMPLET, lu au décompilé d'`IdunBattle.Operations.MoveUnitOperation$$Execute` (les deux
    events ENCADRANTS sont désormais portés, cf. les vecteurs dédiés ci-dessous) :
        AddMoveEvent(s) -> **KillSteppableUnits** (-> `On(0x36=PostUnitKill)` par crushé)
        -> UpdateCharging -> SetMovedFlag -> **Add(UnitFlag.ArrivedAtFinalTile=1)**
        -> EvaluateAfterMoveTriggers (`On(0x24)` / `On(4)` / `On(0x1d)`)
        -> si le flag 1 venait d'être AJOUTÉ : **`On(0x1c=ArrivedAtFinalTile)`**.
    `post_unit_kill_triggers` est donc émis EN TÊTE (le crush précède) et
    `arrived_at_final_tile_triggers` EN QUEUE (l'event 0x1c suit les after-move)."""
    out = post_unit_kill_triggers_for_move(state, mover_id)
    # `On(0x24 = UnitPositionChanged_1)` — PREMIER des trois events d'`EvaluateAfterMoveTriggers`.
    # Consommateur porté : `LightCoverAbility` (tile-ability : la tuile de cover pose l'effet 1013 sur
    # l'unité qui vient d'y arriver). Les tile-abilities ne sont pas dans le registre d'effet-triggers
    # (elles sont portées par le tile-def, pas par un effet) → appel direct, comme `dry_bush_fire_spread`
    # / `first_aid_heal`. No-op hors tuile de cover.
    from ..tiles import light_cover_on_enter
    out += light_cover_on_enter(state, mover_id)
    ev = TriggerEvent(EventTriggerType.UnitAfterMove, mover_id, mover_id, ranged=False, profile=None)
    out += evaluate_trigger_operation(state, ev)
    # G2 : `On(0x1d=UnitPositionChanged_2)` émis APRÈS `On(4)` par le même `EvaluateAfterMoveTriggers` natif.
    ev2 = TriggerEvent(EventTriggerType.UnitPositionChanged_2, mover_id, mover_id, ranged=False, profile=None)
    out += evaluate_trigger_operation(state, ev2)
    return out + arrived_at_final_tile_triggers(state, mover_id)


def post_unit_kill_triggers(state: State, killer_id: int, killed_id: int) -> list[dict]:
    """Vecteur `On(PostUnitKill = 0x36 = 54)` — **5e et DERNIER** des events de mort émis par
    `IdunBattle.Operations.KillUnitOperation$$Execute` (séquence lue au décompilé et déjà documentée
    par `pre_unit_death_2_triggers` : `On(1)` -> `On(2)` -> `On(0)` -> `On(0x37)` -> `On(0x36)`).
    `actor` = le TUEUR, `target`/`dying` = la victime.

    Consommateur porté : `CosmicHorrorOnMoveAbility` (`On(0x36) & OwnerIsActor & AreFriends &
    HasTrait(target, Decoy)`) — le Patermine qui marche sur un decoy allié le CRUSHE
    (`MoveUnitOperation$$KillSteppableUnits` -> `KillUnitOperation$$Execute` avec
    `KillUnitOperationOptions$$ForSteppable`) et se soigne. No-op si rien ne matche."""
    ev = TriggerEvent(EventTriggerType.PostUnitKill, killer_id, killed_id,
                      ranged=False, profile=None, killer_id=killer_id, dying_id=killed_id)
    return evaluate_trigger_operation(state, ev)


def post_unit_kill_triggers_for_move(state: State, mover_id: int) -> list[dict]:
    """`On(0x36)` pour les STEPPABLES que le move qui vient de s'exécuter a écrasés.

    Le port crushe INLINE dans `movement.py::_kill_steppable_units` par un kill « propre » qui n'émet
    AUCUN event (contrairement au natif, qui passe par `KillUnitOperation$$Execute` et en émet cinq).
    On ré-identifie donc les crushés par CO-LOCALISATION — le même collapse que
    `genestealer.py::_valid_dead_decoys` (déjà porté/validé pour G2) : une unité MORTE, `Steppable`,
    sur la tuile du mover. Les positions étant exclusives, la tuile est libérée au crush puis
    ré-occupée par le mover -> au plus un crushé par move, et un steppable mort d'un tour antérieur
    est sur une AUTRE tuile.

    RÉSIDU assumé : les 4 autres events de la séquence de mort d'un steppable crushé
    (`On(1)`/`On(2)`/`On(0)`/`On(0x37)`) restent NON émis, et `On(0x36)` reste non émis pour les
    morts par DÉGÂT (damage.py) et pour le crush par `ResurrectUnitOperation`/`AddUnitOperation`.
    Aucun consommateur porté ne les lit ; à rouvrir si un port futur en dépend."""
    from .....entities.traits import UnitTrait, has_trait
    board = state.board
    mover = state.get_entity(mover_id)
    if board is None or mover is None:
        return []
    mpc = mover.get_component(PositionComponent)
    if mpc is None:
        return []
    pos = (mpc.col, mpc.row)
    out: list[dict] = []
    for uid, e in sorted(state.entities.items()):
        if uid == mover_id:
            continue
        uc = e.get_component(UnitComponent)
        if uc is None or uc.alive:                        # le crushé est MORT
            continue
        pc = e.get_component(PositionComponent)
        if pc is None or (pc.col, pc.row) != pos:         # ... et co-localisé avec le mover
            continue
        sc = e.get_component(StatsComponent)
        traits = getattr(sc.ctx, "traits", None) if sc is not None else None
        if not has_trait(traits or [], UnitTrait.Steppable):
            continue
        out += post_unit_kill_triggers(state, mover_id, uid)
    return out


def arrived_at_final_tile_triggers(state: State, unit_id: int,
                                   gate_already_consumed: bool = False) -> list[dict]:
    """Vecteur `On(ArrivedAtFinalTile = 0x1c = 28)` — « l'unité a terminé son activation ».

    DEUX émetteurs natifs, tous deux lus au décompilé, tous deux gardés par le MÊME flag :
      * `IdunBattle.Operations.MoveUnitOperation$$Execute` : `UnitFlagsComponent.Add(1)` puis, APRÈS
        `EvaluateAfterMoveTriggers`, publie `On(0x1c)` SSI le flag venait d'être ajouté ;
      * `IdunBattle.Operations.FinishUnitTurnOperation$$Execute` : `Add(1)` puis publie `On(0x1c)`
        SSI le flag venait d'être ajouté ET `!forced`.
    => `On(0x1c)` fire AU PLUS UNE FOIS par activation : à la fin du 1er déplacement, ou à la clôture
    du tour si l'unité n'a pas bougé. Le flag est purgé par `RemoveTurnFlags(new_activation=True)` au
    début du tour suivant (`UnitFlagsComponent.remove_turn_flags`), ce qui ré-arme l'event.

    Cette fonction porte le gate : elle POSE `ARRIVED_AT_FINAL_TILE` et n'émet que s'il était absent
    (mirror du `bool` que rend `UnitFlagsComponent.Add`). Appelée (a) en queue d'`after_move_triggers`
    — le port ne posait PAS ce flag au move, cette fonction le pose donc pour lui, ce qui est fidèle
    à l'ordre observable (rien entre les deux ne le lit) ; et (b) par `FinishUnitTurnOperation.execute`,
    qui pose lui-même le flag et a DÉJÀ calculé son `newly_arrived` -> il passe
    `gate_already_consumed=True` pour ne pas re-tester un flag qu'il vient de poser.

    Consommateurs portés : `SpiritualLeaderAbility` (`On(0x1c) & OwnerIsActor`, passif de `genesMagus`)
    et `ArcaneShieldAbility` (`On(0x1c) & OwnerIsActor & OwnerIsCaster`, passif de `thousSorcerer` —
    MIGRÉE sur ce vecteur, résidu N1 : elle était approximée sur `On(4)` et ratait donc le cas « finit
    son tour sans avoir bougé »). No-op si l'unité a déjà le flag (ou n'existe pas)."""
    e = state.get_entity(unit_id)
    if e is None:
        return []
    if not gate_already_consumed:
        fl = e.get_component(UnitFlagsComponent)
        if fl is None:
            fl = e.add_component(UnitFlagsComponent())
        if fl.has(UnitFlagsComponent.ARRIVED_AT_FINAL_TILE):  # `Add` natif a rendu FALSE -> pas d'event
            return []
        fl.add(UnitFlagsComponent.ARRIVED_AT_FINAL_TILE)
    ev = TriggerEvent(EventTriggerType.ArrivedAtFinalTile, unit_id, unit_id,
                      ranged=False, profile=None)
    return evaluate_trigger_operation(state, ev)


def displace_triggers(state: State, pusher_id: int, pushed_id: int) -> list[dict]:
    """Vecteur DÉPLACEMENT FORCÉ (push/pull) — mirror `IdunBattle.Operations.DisplaceUnitOperation$$EventAndAbilitiesAndEffects`. APRÈS le `MoveUnit@0x7e` de la poussée, le natif émet (via `EvaluateTriggerOperation`, msg 0x52)
    la SÉQUENCE d'events `On(0x24=UnitPositionChanged_1)` -> `On(0x23=UnitDisplaced)` -> `On(0x1d=
    UnitPositionChanged_2)`, tous {actor=pusher, target=pushed}. On dispatche `On(0x24)` puis
    `On(UnitDisplaced)` (actor=pusher, target=pushed) : `0x24` pose la couverture de la tuile
    d'ATTERRISSAGE (`LightCoverAbility` — une unité POUSSÉE dans un buisson s'y met à couvert
    exactement comme si elle y avait marché, résidu O3) ; `UnitDisplaced` a pour consommateur
    `RadSaturationAbility` (branche 2 `OwnerIsTarget` -> le Skitarii Vanguard POUSSÉ contamine sa tuile
    d'atterrissage ; le pushed a déjà bougé via `MoveUnitOperation` donc `Tiles(Caster())` = sa tuile
    POST-push). Sibling `On(0x1d)` = NON dispatché ici (flaggé) : DecoysAndMisdirection G2-sur-push =
    concern séparé (non validé). No-op si aucun trigger ne matche. Appelé par
    `DisplaceUnitOperation.execute` (displace.py) après un push réussi."""
    from ..tiles import light_cover_on_enter     # `On(0x24)` — tile-ability, hors registre d'effets
    out = light_cover_on_enter(state, pushed_id)
    ev = TriggerEvent(EventTriggerType.UnitDisplaced, pusher_id, pushed_id, ranged=False, profile=None)
    return out + evaluate_trigger_operation(state, ev)


def after_death_triggers(state: State, dying_id: int, killer_id: Optional[int],
                         overkill: bool = False) -> list[dict]:
    """Vecteur MORT (mirror `IdunBattleLogic.Entities.DSLFactory$$OnDeathEvent → dispatch). Construit l'événement `On(1)`
    {killer=0x158, dying=0x178, overkill} et lance `evaluate_trigger_operation`. Déclenche les accumulations
    ActOfFaith (allié Imperial qui meurt ou tue) + FinalJustice (l'unité mourante riposte, sauf overkill).
    `actor_id`/`target_id` reflètent killer/dying pour le dispatch générique. No-op si aucun trigger ne
    matche."""
    ev = TriggerEvent(EventTriggerType.PreUnitDeath,
                      killer_id if killer_id is not None else dying_id, dying_id,
                      ranged=False, profile=None, killer_id=killer_id, dying_id=dying_id,
                      overkill=overkill)
    return evaluate_trigger_operation(state, ev)


def pending_death_added_triggers(state: State, dying_id: int,
                                 killer_id: Optional[int]) -> list[dict]:
    """Vecteur `On(PendingDeathAdded = 3)` — emis par
    `IdunBattle.Operations.RecordKillOperation$$Execute` (appele par
    `Core.Services.OperationProcessor$$RecordKill`), la toute PREMIERE etape de la mort : celle qui
    ENREGISTRE le kill, avant meme que la mort ne soit drainee.

    Sequence LUE dans `RecordKillOperation$$Execute` :
        gate `UnitFlagsComponent.Has(dying, 6)` -> return (deja retire)
        -> compteurs de kills du joueur (`PlayerComponent+0x90`, `+0x94` si le kill est de type 2)
        -> `UnitFlagsComponent.Add(dying, 0xf)`            (marque « mort en attente »)
        -> `MatchState.AddDeath(killer, dying, ...)`       (ENQUEUE, slot 1 de l'interface MatchState)
        -> **publie `On(3)`** {a = killer, b = killer, c = dying}

    La file remplie par `AddDeath` n'est drainee que plus tard, par
    `IdunBattle.Messages.InputMessageProcessor$$VerifyDeaths` (`RunPhase(0xc)` -> `KillUnit` ->
    `IdunBattle.Operations.KillUnitOperation$$Execute`, qui emet `On(1)`) : **`On(3)` precede donc
    STRICTEMENT `On(1)`** pour une meme mort. Le port respecte cet ordre en appelant ce vecteur en tete
    de `damage.py::_fire_death_if_killed`.

    Le triplet d'entites du publieur (3 arguments avant l'`eventType`, meme forme que
    `IdunBattle.Operations.MoveUnitOperation$$EvaluateArrivedAtFinalTileTrigger`) est ici
    `(killer, killer, dying)` -> le **TUEUR** est l'acteur ET le caster, la VICTIME est la cible.
    C'est ce qui permet a `FuelledByFury_ReviveAbility` de tester `AreEqual(caster@0x160, self@0x148)`
    = « c'est MOI qui viens de tuer ».

    `triggering_ability` = `state.triggering_ability`, le champ que
    `IdunBattle.Entities.Abilities.BaseTriggeredAbility$$Execute` a pose si le coup fatal a ete porte
    DANS le behaviour d'une triggered-ability (cf. `dispatch/core.py`). C'est ce que lit
    `TriggeringAbilityIs`. No-op si aucun trigger ne matche.

    RESIDU NOMME : le port ne modelise ni le flag `0xf` pose ici, ni les compteurs de kills du
    `PlayerComponent` -- aucun consommateur porte ne les lit."""
    ev = TriggerEvent(EventTriggerType.PendingDeathAdded,
                      killer_id if killer_id is not None else dying_id, dying_id,
                      ranged=False, profile=None, killer_id=killer_id, dying_id=dying_id,
                      triggering_ability=getattr(state, "triggering_ability", None))
    return evaluate_trigger_operation(state, ev)


def pre_unit_death_2_triggers(state: State, dying_id: int, killer_id: Optional[int],
                              overkill: bool = False) -> list[dict]:
    """Vecteur `On(PreUnitDeath_2 = 2)` — event NATIF DISTINCT de `PreUnitDeath(1)` et de
    `UnitDefeated(55)`. Emis par `KillUnitOperation$$IdunBattle.Operations.KillUnitOperation$$Execute` ENTRE les deux : ordre
    d'instruction LU au decompile `On(1)` (ret IdunBattle.Operations.KillUnitOperation$$Execute+0x7dc) -> `On(2)` (ret IdunBattle.Operations.KillUnitOperation$$Execute+0x97a) ->
    `On(0)` (IdunBattle.Operations.KillUnitOperation$$Execute+0xdf9) -> `On(0x37=55)` (IdunBattle.Operations.KillUnitOperation$$Execute+0xeac) -> `On(0x36=54)` (IdunBattle.Operations.KillUnitOperation$$Execute+0x102c).
    (`ApplyDamageOperation$$IdunBattle.Operations.ApplyDamageOperation$$Execute` n'emet AUCUN des trois ; `InputMessageProcessor$$
    IdunBattle.Messages.InputMessageProcessor$$VerifyDeaths` non plus — il ne fait qu'appeler `OperationProcessor$$Core.Services.OperationProcessor$$KillUnit.)

    Consommateurs portes : la famille DEATH-NOVA (`IdunBattleLogic.Entities.DSLFactory$$OnPreDeath2` ->
    `IdunBattleLogic.Entities.DSLFactory$$OnDeathEvent(2, a, b)) — `ExplodesAbility` (trait Explodes) et `PutridExplosion_Ability`
    (trait PutridExplosion). Les DEUX passent `a=1` -> AUCUN gate `NOT HasFlag(dying, Overkilled=8)` :
    la nova part MEME EN OVERKILL (le flag `overkill` est thread pour fidelite du payload, aucun
    consommateur de CE vecteur ne le lit aujourd'hui). L'unite est deja `alive=False` au dispatch
    (fire-on-death). No-op si aucun porteur ne meurt."""
    ev = TriggerEvent(EventTriggerType.PreUnitDeath_2,
                      killer_id if killer_id is not None else dying_id, dying_id,
                      ranged=False, profile=None, killer_id=killer_id, dying_id=dying_id,
                      overkill=overkill)
    return evaluate_trigger_operation(state, ev)


def unit_death_triggers(state: State, dying_id: int, killer_id: Optional[int] = None,
                        overkill: bool = False) -> list[dict]:
    """Vecteur `On(UnitDeath=0)` — 3e des events de mort emis par `IdunBattle.Operations.KillUnitOperation$$Execute`
    (sequence verifiee au decompile : `FUN_180026490(...,1)` PreUnitDeath -> `...,2` PreUnitDeath_2 ->
    `...,0` **UnitDeath** -> `...,0x37` UnitDefeated -> `...,0x36` PostUnitKill). Le port emettait deja
    `On(1)` (`after_death_triggers`) et `On(0x37)` (`unit_defeated_triggers`) mais PAS `On(0)` — d'ou ce
    vecteur, insere a sa place EXACTE (entre les deux).

    Consommateur : branche 1 de `IdunBattleLogic.Entities.Abilities.Triggered.Loki.TerrifyingCrescendoAbility$$CreateTrigger`
    (`On(0) & OwnerIsActor & TargetIsOverkilled` -> +1 stack). `actor` = le TUEUR (OwnerIsActor),
    `target`/`dying` = la victime, `overkill` = `TargetIsOverkilled`. No-op si rien ne matche.
    (Le `IdunBattle.Entities.Effects.Loki.MasterAnnihilator_AdditionalHitEffect$$CreateRemoveEffectTrigger` ecoute aussi `On(0)`
    — retrait du marqueur a la mort de SA source — mais c'est un EFFET-trigger non enregistre, cf.
    loki/master_annihilator.py.)"""
    ev = TriggerEvent(EventTriggerType.UnitDeath,
                      killer_id if killer_id is not None else dying_id, dying_id,
                      ranged=False, profile=None, killer_id=killer_id, dying_id=dying_id,
                      overkill=overkill)
    return evaluate_trigger_operation(state, ev)


def pre_effect_added_triggers(state: State, source_id: Optional[int], target_id: Optional[int],
                              effect_type: int) -> list[dict]:
    """Vecteur `On(PreEffectAdded=0x3e=62)` — emis par `IdunBattle.Operations.AddEffectOperation$$Execute` **TOUT EN
    HAUT** (`FUN_180026490(0x50, ..., 0x3e)` juste apres la construction de l'`AbilityEntities`, AVANT le
    gate cible-nulle, AVANT le gate << deja present >> et AVANT le gate d'immunite `HasFlag(target,6)`).
    => l'evenement fire meme quand l'effet n'est finalement PAS applique (semantique << would have >>).

    `AbilityEntities.ctor(source, source, target)` -> **actor = la SOURCE** de l'effet ; `target` = la
    cible ; `triggering_effect` = le type pose (lu par `TriggeringEffectIs`). Consommateur : branche 2 de
    `IdunBattleLogic.Entities.Abilities.Triggered.Loki.TerrifyingCrescendoAbility$$CreateTrigger`. No-op si rien ne matche."""
    ev = TriggerEvent(EventTriggerType.PreEffectAdded,
                      source_id if source_id is not None else -1,
                      target_id if target_id is not None else -1,
                      ranged=False, profile=None, triggering_effect=int(effect_type))
    return evaluate_trigger_operation(state, ev)


def unit_defeated_triggers(state: State, dying_id: int, killer_id: Optional[int] = None) -> list[dict]:
    """Vecteur `On(UnitDefeated=55=0x37)` (G3) — event NATIF DISTINCT de `PreUnitDeath(1)` : le natif
    `Ambush_SummonAbility` IdunBattleLogic.Entities.Abilities.Triggered.Loki.Ambush_SummonAbility$$CreateTrigger ecoute `On(0x37) & OwnerIsTarget & Not(HasFlag 0xe)`, PAS On(1). Emis
    par le pipeline de mort APRES `after_death_triggers(On 1)` (l'unite est deja alive=False -> l'ability
    fire-on-death voit sa mort). Declenche la pose du decoy Ambush (mort -> decoy) + l'enregistrement de
    `turn_defeated`. No-op si aucun porteur Ambush ne meurt."""
    ev = TriggerEvent(EventTriggerType.UnitDefeated,
                      killer_id if killer_id is not None else dying_id, dying_id,
                      ranged=False, profile=None, killer_id=killer_id, dying_id=dying_id)
    return evaluate_trigger_operation(state, ev)


def unit_revived_triggers(state: State, revived_id: int, current_ability=None) -> list[dict]:
    """Vecteur `On(UnitRevived = 46 = 0x2e)` (case-89 volet B3) — emis par `ReviveUnitOperation.Execute`
    @IdunBattle.Operations.ReviveUnitOperation$$Execute+0xac1 (`FUN_180026490(0x4d, DAT_1831d3468, events, 0x2e)`), APRES la mutation PV/flags/position
    et **AVANT** la purge de la `ReviveData` (@IdunBattle.Operations.ReviveUnitOperation$$Execute+0xda7+). DISTINCT d'`On(UnitResurrected=47=0x2f)`
    (`ResurrectUnitOperation`, ambush).

    `current_ability` = le `sourceId` (`AbilityOrEffect`) porte par la `ReviveData` — c'est ce que lit le
    noeud `CurrentAbilityIs` des consommateurs. Consommateurs portes :
      * `PhoenixGem_CanReviveEffect` IdunBattle.Entities.Effects.Loki.PhoenixGem_CanReviveEffect$$CreateHandleTriggerAbilitiesInternal : `On(0x2e) & OwnerIsTarget & CurrentAbilityIs(0x5b2=1458
        TriggeredAbilityType.PhoenixGem)` -> `RemoveEffect(marqueur 1451)` = « the FIRST TIME each battle » ;
      * (non porte, cf. residu A2) `FuelledByFury_CanReviveEffect` IdunBattle.Entities.Effects.Loki.FuelledByFury_CanReviveEffect$$CreateHandleTriggerAbilitiesInternal : meme forme avec
        `CurrentAbilityIs(0x4e3=1251)` -> `DeactivateEffect` (« first time each TURN »).
    Le bras `On(UnitRevived)` du trait Swarm est, lui, re-evalue IMPERATIVEMENT par l'Operation (helper
    `on_group_unit_hp_changed`) — residu structurel deja documente (#60). No-op si rien ne matche."""
    ev = TriggerEvent(EventTriggerType.UnitRevived, revived_id, revived_id,
                      ranged=False, profile=None, ability_type=current_ability)
    return evaluate_trigger_operation(state, ev)


def unit_resurrected_triggers(state: State, resurrected_id: int) -> list[dict]:
    """Vecteur `On(UnitResurrected=47=0x2f)` (G3) — emis par `ResurrectUnitOperation` IdunBattle.Operations.ResurrectUnitOperation$$Execute apres une
    resurrection Ambush (`actor` = l'unite ressuscitee, co-localisee avec le decoy qu'elle vient de crusher).
    Alimente `DecoysAndMisdirection_BuffFriends` (G2, `(On(0x2f)|On(0x1d)) & AreFriends` -> +582 + nouveau
    decoy si GS Cult) et la re-arme HeroicFusillade (G5, `On(0x2f) & OwnerIsTarget`). No-op si aucun
    consommateur ne matche. Le decoy crushe (steppable, alive=False, meme tuile) satisfait `GetValidDeadDecoys`
    de BuffFriends (co-localisation dead-decoy/stepper)."""
    ev = TriggerEvent(EventTriggerType.UnitResurrected, resurrected_id, resurrected_id,
                      ranged=False, profile=None)
    return evaluate_trigger_operation(state, ev)
