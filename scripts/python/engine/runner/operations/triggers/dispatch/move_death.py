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


def pre_move_triggers(state: State, mover_id: int) -> list[dict]:
    """Vecteur `On(PreUnitMove = 0x1f = 31)` — emis par
    `IdunBattle.Operations.MoveUnitOperation$$EvaluatePreMoveTriggers`, dont le corps est aussi
    INLINE dans `IdunBattle.Operations.MoveUnitOperation$$Execute` (d'ou l'absence d'xref CODE vers
    la fonction nommee : c'est le meme code, recopie par l'optimiseur).

    PLACE EXACTE dans le pipeline natif du move, LUE au decompile d'`Execute` : apres les sept gates
    de validation (`IsAllowedToMove`, `UnitIsOnTiles`, `TilesAreWalkable`, `TilesMatchUnitFeetCount`,
    `IsDisallowedEmptyPosition`, `IsPositionReservedForOtherUnit`, `IsPositionReservedForDrafting`) et
    apres `SetReservation`, mais **AVANT** `CalculatePaths`, `MoveUnit` (l'ecriture de la position),
    `AddMoveEvent`, `KillSteppableUnits`, `UpdateCharging`, `SetMovedFlag` et
    `EvaluateAfterMoveTriggers`. Autrement dit : l'unite est ENCORE sur sa tuile de depart quand cet
    evenement part. Le port l'emet donc en TETE de `MoveUnitOperation.execute`.

    `AbilityEntities.ctor(mover, mover, mover, …)` -> **actor = caster = target = le mover** (lu au
    decompile). L'emission est gardee cote natif par l'octet `MoveUnitOptions@+0x12` (nul a tous les
    call-sites du port -> event TOUJOURS emis, meme regime que `SetMovedFlag`).

    Consommateurs portes :
      * `GhostReviveAbility`/`TimeFluxReviveAbility` (#213) : Toth qui bouge laisse un time-ghost sur
        sa tuile de DEBUT DE TOUR ;
      * 1er des cinq retraits de `GhostEffect` : un ghost dont le poseur rebouge disparait.
    No-op si aucun trigger ne matche."""
    ev = TriggerEvent(EventTriggerType.PreUnitMove, mover_id, mover_id, ranged=False, profile=None)
    return evaluate_trigger_operation(state, ev)


def unit_position_changed_1_triggers(state: State, unit_id: int) -> list[dict]:
    """Vecteur `On(UnitPositionChanged_1 = 0x24 = 36)` — PREMIER des trois events qu'emet
    `IdunBattle.Operations.MoveUnitOperation$$EvaluateAfterMoveTriggers`, egalement emis par
    `IdunBattle.Operations.DisplaceUnitOperation$$EventAndAbilitiesAndEffects` (push) et par
    `IdunBattle.Operations.ReviveUnitOperation$$SetRevivePosition` (revive NON in-place, #213).

    Le port l'appelait jusqu'ici en BESPOKE (`light_cover_on_enter`, une tile-ability hors registre).
    Ce foyer ajoute le dispatch GENERIQUE du meme event, pour les EFFET-triggers qui l'ecoutent :
      * 3e des cinq retraits de `GhostEffect` — `On(0x24) & NOT AreEqual(caster, EffectSource) &
        Contains(TargetTiles@0x190, Owner@0x148)` : une AUTRE unite arrive sur la tuile du ghost, le
        ghost disparait (c'est le « the time ghost vanishes if the hex becomes occupied » de l'i2).
    `TargetTiles@0x190` = la tuile d'ARRIVEE : le port la derive de la `PositionComponent` de
    `unit_id`, qui est deja ecrite a ce stade (le natif emet ces events APRES `MoveUnit`).
    No-op si aucun trigger ne matche."""
    ev = TriggerEvent(EventTriggerType.UnitPositionChanged_1, unit_id, unit_id,
                      ranged=False, profile=None)
    return evaluate_trigger_operation(state, ev)


def unit_position_changed_2_triggers(state: State, unit_id: int) -> list[dict]:
    """Vecteur `On(UnitPositionChanged_2 = 0x1d = 29)` — TROISIEME et dernier event
    d'`EvaluateAfterMoveTriggers`, emis aussi par `ReviveUnitOperation$$SetRevivePosition`.
    Consommateur porte : `DecoysAndMisdirection_BuffFriends` (G2). Foyer partage avec
    `after_move_triggers` (qui l'emettait deja inline)."""
    ev = TriggerEvent(EventTriggerType.UnitPositionChanged_2, unit_id, unit_id,
                      ranged=False, profile=None)
    return evaluate_trigger_operation(state, ev)


def unit_removed_triggers(state: State, unit_id: int) -> list[dict]:
    """Vecteur `On(UnitRemoved = 0x25 = 37)` — 5e et dernier retrait de `GhostEffect`
    (`On(0x25) & AreEqual(EffectSource, target@0x178)` : le poseur du ghost QUITTE le plateau, le
    ghost part avec lui).

    EMETTEUR (#227) : `IdunBattle.Operations.RemoveUnitOperation$$Execute`, porte dans
    `runner/operations/remove_unit.py` -- c'est le SEUL appelant de production, et les deux sites de
    despawn du port (feuille DSL `RemoveUnit`, eviction `MV71SniperDroneSquadAttackAbility`) passent
    par lui. `AbilityEntities.ctor(entity, entity, entity)` -> actor = caster = target = l'unite
    retiree, ce que reflete l'appel ci-dessous. Le natif publie APRES la pose du flag
    `Removed (0x1a)` et le retrait des tuiles, mais AVANT `RemoveUnitOperation$$RemoveEffects` :
    l'Operation portee respecte cet ordre. No-op si aucun trigger ne matche."""
    ev = TriggerEvent(EventTriggerType.UnitRemoved, unit_id, unit_id, ranged=False, profile=None)
    return evaluate_trigger_operation(state, ev)


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
        AddMoveEvent(s) -> **KillSteppableUnits** (-> `On(0x35=PostUnitKill)` par crushé)
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
    # ... et le dispatch GENERIQUE du meme `On(0x24)` pour les effet-triggers qui l'ecoutent (#213 :
    # retrait n°3 de `GhostEffect` -- une autre unite arrive sur la tuile du ghost).
    out += unit_position_changed_1_triggers(state, mover_id)
    ev = TriggerEvent(EventTriggerType.UnitAfterMove, mover_id, mover_id, ranged=False, profile=None)
    out += evaluate_trigger_operation(state, ev)
    # G2 : `On(0x1d=UnitPositionChanged_2)` émis APRÈS `On(4)` par le même `EvaluateAfterMoveTriggers` natif.
    out += unit_position_changed_2_triggers(state, mover_id)
    return out + arrived_at_final_tile_triggers(state, mover_id)


def post_unit_kill_triggers(state: State, killer_id: int, killed_id: int) -> list[dict]:
    """Vecteur `On(PostUnitKill = 0x35 = 53)` — **5e et DERNIER** des events de mort émis par
    `IdunBattle.Operations.KillUnitOperation$$Execute` (séquence lue au décompilé et déjà documentée
    par `pre_unit_death_2_triggers` : `On(1)` -> `On(2)` -> `On(0)` -> `On(0x36)` -> `On(0x35)`).
    `actor` = le TUEUR, `target`/`dying` = la victime.

    Consommateur porté : `CosmicHorrorOnMoveAbility` (`On(0x35) & OwnerIsActor & AreFriends &
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
    # dispatch GENERIQUE du meme `On(0x24)` (retrait n°3 de `GhostEffect`, #213) : une unite POUSSEE
    # sur la tuile d'un ghost le fait disparaitre exactement comme si elle y avait marche.
    out += unit_position_changed_1_triggers(state, pushed_id)
    ev = TriggerEvent(EventTriggerType.UnitDisplaced, pusher_id, pushed_id, ranged=False, profile=None)
    return out + evaluate_trigger_operation(state, ev)


def after_death_triggers(state: State, dying_id: int, killer_id: Optional[int],
                         overkill: bool = False) -> list[dict]:
    """Vecteur MORT (mirror `IdunBattleLogic.Entities.DSLFactory$$OnDeathEvent → dispatch). Construit l'événement `On(1)`
    {killer=0x158, dying=0x178, overkill} et lance `evaluate_trigger_operation`. Déclenche les accumulations
    ActOfFaith (allié Imperial qui meurt ou tue) + FinalJustice (l'unité mourante riposte, sauf overkill).
    `actor_id`/`target_id` reflètent killer/dying pour le dispatch générique. No-op si aucun trigger ne
    matche.

    CANAUX D'ABILITY SUR CE VECTEUR (#301) — vaut pour les CINQ events de
    `IdunBattle.Operations.KillUnitOperation$$Execute` (`On(1)`, `On(2)`, `On(0)`, `On(54)`, `On(53)`),
    qui partagent le MEME `AbilityEntities`, bati une fois et publie tel quel :
      * `CurrentAbility` (`+0x60`, `state.triggering_ability`) = **VIDE** — le memset de 0x128 n'est
        suivi d'AUCUNE reecriture de ce champ. Tout `CurrentAbilityIs` y est faux.
      * `TriggeringAbility` (`+0x98`, `state.trigger_ability_type`) = le `killTrigger` de la file
        (`KillUnitOptions+0x04`). C'est LUI que doit lire un `TriggeringAbilityIs` /
        `TriggeringEffectIs` / `TriggeringAbilityIsNone` de ce vecteur.
    Les deux sont poses par `operations/damage.py::_verify_deaths` pour la duree du drain."""
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
    `UnitDefeated(54)`. Emis par `KillUnitOperation$$IdunBattle.Operations.KillUnitOperation$$Execute` ENTRE les deux : ordre
    d'instruction LU au decompile `On(1)` (ret IdunBattle.Operations.KillUnitOperation$$Execute+0x7dc) -> `On(2)` (ret IdunBattle.Operations.KillUnitOperation$$Execute+0x97a) ->
    `On(0)` (IdunBattle.Operations.KillUnitOperation$$Execute+0xdf9) -> `On(0x36=54 UnitDefeated)` (IdunBattle.Operations.KillUnitOperation$$Execute+0xeac) -> `On(0x35=53 PostUnitKill)` (IdunBattle.Operations.KillUnitOperation$$Execute+0x102c).
    (Litteraux d'event RE-DERIVES en #301 : les cinq call-sites passent 1, 2, 0, 0x36 puis 0x35 --
    l'ancienne redaction ecrivait `0x37`/`0x36`, hex faux pour les memes valeurs decimales.)
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
    (sequence verifiee au decompile : `(...,1)` PreUnitDeath -> `...,2` PreUnitDeath_2 ->
    `...,0` **UnitDeath** -> `...,0x36` UnitDefeated -> `...,0x35` PostUnitKill). Le port emettait deja
    `On(1)` (`after_death_triggers`) et `On(0x36)` (`unit_defeated_triggers`) mais PAS `On(0)` — d'ou ce
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


def _effect_vector_triggers(state: State, event_id: int, actor_id: Optional[int],
                            target_id: Optional[int], effect_type: int, *,
                            removing: bool) -> list[dict]:
    """FOYER UNIQUE des vecteurs d'EFFET (pose / retrait) et de leurs DEUX canaux d'ability (#306).

    Les deux Operations natives batissent un `AbilityEntities` NEUF par `memset(0, 0x128)` -- l'ambiant
    de l'appelant (une triggered-ability en cours, p. ex.) n'y survit PAS -- puis remplissent, et
    ELLES NE REMPLISSENT PAS LES MEMES CHAMPS. C'est toute l'asymetrie, re-derivee au decompile du
    build `rnca9r7q6c` :

      `IdunBattle.Operations.AddEffectOperation$$Execute`
          memset(0x128) puis `IdunBattle.Entities.Abilities.AbilityEntities$$.ctor(
              caster: source, actor: source, target: owner, owner: owner, ...,
              currentAbilityOrEffect: Nullable(AbilityOrEffect(effectType)),   -> +0x60
              parentAbilityOrEffect:  Nullable VIDE,                           -> +0x7c
              triggerAbilityOrEffect: Nullable(AbilityOrEffect(effectType)))   -> +0x98
          Les DEUX Nullable sortent de DEUX appels distincts a `IdunBattle.Core.AbilityOrEffect$$
          op_Implicit` sur le MEME argument (`mov edx, edi` deux fois, `edi` = le parametre
          `effectType`) -> **meme valeur dans les deux champs**.
          Events publies avec CETTE struct : `On(0x3d=61 PreEffectAdded)`, `On(0x3e=62 EffectAdded)`,
          `On(0x46=70 UnitBecameUntargetable)`.

      `IdunBattle.Operations.RemoveEffectOperation$$Execute`
          memset(0x128) puis **AUCUN ctor** -- quatre ecritures directes seulement :
              +0x10 (`target`) = +0x18 (`owner`) = Entity(effectComponent.OwnerId @+0x14)
              +0x60..+0x7c (`currentAbilityOrEffect`) =
                  Nullable(AbilityOrEffect(effectComponent.Type @+0x58))
          CONTROLE NEGATIF (fait a l'assembleur, pas deduit) : entre le memset et la copie publiee,
          aucune ecriture ne touche +0x00 (`actor`), +0x08 (`caster`), +0x7c (`parent`) ni **+0x98**
          (`triggering`) -- ils restent a ZERO.
          Events publies : `On(0x3f=63 PreEffectRemoved)`, `On(0x40=64 EffectRemoved)`,
          `On(0x3b=59 UnitBecameTargetable)`.

    Les deux lecteurs sont des copies plates a offset FIXE, ce qui identifie les champs sans deduction :
        `IdunBattleLogic.Entities.AbilityTypeSelector.CurrentAbilitySelector$$Select`    lit +0x60/+0x68/+0x70/+0x78
        `IdunBattleLogic.Entities.AbilityTypeSelector.TriggeringAbilitySelector$$Select` lit +0x98/+0xa0/+0xa8/+0xb0
    et cote DSL, `IdunBattleLogic.Entities.DSLTriggers$$CurrentAbilityIs` prend le slot
    `DSLSelectors+0x88` tandis que `$$TriggeringAbilityIs` / `$$TriggeringEffectIs` /
    `$$TriggeringAbilityIsNone` prennent TOUS LES TROIS `DSLSelectors+0x90`.

    ==> CONSEQUENCE, et c'est l'objet de ce foyer :
        * sur la POSE, les deux canaux portent la MEME valeur -> `CurrentAbilityIs(effet)` ET
          `TriggeringEffectIs(effet)` sont VRAIS, indiscernables ;
        * sur le RETRAIT, `TriggeringEffectIs` / `TriggeringAbilityIs` sont **TOUJOURS FAUX** (le
          Nullable +0x98 est vide) et `TriggeringAbilityIsNone` est VRAI ; c'est **`CurrentAbilityIs`
          qui porte l'effet retire**.

    Mapping port (cf. `TriggerEvent` / `State`) :
        +0x60 `CurrentAbility`    -> `ev.triggering_ability` ET l'ambiant `state.triggering_ability`
        +0x98 `TriggeringAbility` -> `ev.triggering_effect`  ET l'ambiant `state.trigger_ability_type`
    Les DEUX niveaux sont poses : le payload parce que c'est ce que lisent les gates cables sur `ev`,
    l'AMBIANT parce que le memset natif ECRASE ce qu'une triggered englobante y avait mis (sans quoi
    un `CurrentAbilityIs(<la triggered englobante>)` serait VRAI cote port et FAUX cote natif). Les
    deux sont restaures en sortie : le natif jette son `AbilityEntities` avec l'operation, le port n'a
    que des canaux globaux (meme geste que `_verify_deaths` pour le vecteur mort, #301)."""
    et = int(effect_type)
    ev = TriggerEvent(int(event_id),
                      actor_id if actor_id is not None else -1,
                      target_id if target_id is not None else -1,
                      ranged=False, profile=None,
                      triggering_ability=et,                        # +0x60, les DEUX sens
                      triggering_effect=(None if removing else et))  # +0x98, POSE seulement
    # Acces DIRECT (pas `getattr(..., None)`) : les deux slots sont declares dans `State.__slots__`.
    # Un objet qui ne les a pas n'est pas un `State` -> ca doit LEVER, pas degrader en `None` (meme
    # raison qu'en `_publish_unit_triggered_ability` : un canal absent lu comme « vide » est le mode
    # de panne silencieuse que ce cas documente).
    prev_current = state.triggering_ability
    prev_trigger = state.trigger_ability_type
    state.triggering_ability = et
    state.trigger_ability_type = (None if removing else et)
    try:
        return evaluate_trigger_operation(state, ev)
    finally:
        state.triggering_ability = prev_current
        state.trigger_ability_type = prev_trigger


def pre_effect_added_triggers(state: State, source_id: Optional[int], target_id: Optional[int],
                              effect_type: int) -> list[dict]:
    """Vecteur `On(PreEffectAdded=0x3d=61)` — emis par `IdunBattle.Operations.AddEffectOperation$$Execute` **TOUT EN
    HAUT** (`FUN_180026490(0x50, ..., 0x3e)` juste apres la construction de l'`AbilityEntities`, AVANT le
    gate cible-nulle, AVANT le gate << deja present >> et AVANT le gate d'immunite `HasFlag(target,6)`).
    => l'evenement fire meme quand l'effet n'est finalement PAS applique (semantique << would have >>).

    `AbilityEntities.ctor(source, source, target)` -> **actor = la SOURCE** de l'effet ; `target` = la
    cible ; `triggering_effect` = le type pose (lu par `TriggeringEffectIs`). Consommateur : branche 2 de
    `IdunBattleLogic.Entities.Abilities.Triggered.Loki.TerrifyingCrescendoAbility$$CreateTrigger`. No-op si rien ne matche.

    Les DEUX canaux d'ability sont poses par `_effect_vector_triggers` (#306) : la POSE ecrit `+0x60`
    ET `+0x98` avec le MEME `AbilityOrEffect(effectType)`."""
    return _effect_vector_triggers(state, int(EventTriggerType.PreEffectAdded),
                                   source_id, target_id, effect_type, removing=False)


def pre_effect_removed_triggers(state: State, target_id: Optional[int],
                                effect_type: int) -> list[dict]:
    """Vecteur `On(PreEffectRemoved=0x3f=63)` — premier des trois events de
    `IdunBattle.Operations.RemoveEffectOperation$$Execute`, publie APRES les deux gates d'idempotence
    (`EffectComponent+0x5f` deja retire, `+0x5e` retrait en cours) et AVANT toute revocation.

    `actor`/`caster` (+0x00/+0x08) sont VIDES cote natif -- le memset n'est suivi d'aucune ecriture --
    donc le port ne threade PAS de source : seul le PORTEUR est connu (`target` = `owner` = +0x10/+0x18).
    C'est `CurrentAbilityIs` qui porte l'effet retire ; tout `TriggeringEffectIs` y est faux (#306).

    AUCUN consommateur porte n'ecoute encore `On(63)` : l'emission est le MIRROR, et c'est elle qui
    rend le canal OBSERVABLE donc la loi d'asymetrie VALIDABLE (meme arbitrage que `On(0xd)` en #294).
    No-op si rien ne matche."""
    return _effect_vector_triggers(state, int(EventTriggerType.PreEffectRemoved),
                                   None, target_id, effect_type, removing=True)


def effect_removed_triggers(state: State, target_id: Optional[int],
                            effect_type: int) -> list[dict]:
    """Vecteur `On(EffectRemoved=0x40=64)` — deuxieme event de
    `IdunBattle.Operations.RemoveEffectOperation$$Execute`, publie APRES `RemoveSubEffects`, la
    desactivation (`RefreshEffectsOperation$$DeactivateEffect` -> revert des modifications) et la pose
    de `EffectComponent+0x5c = 0` / `+0x5f = 1`.

    MEME `AbilityEntities` que `On(63)` : la struct est batie UNE fois puis publiee telle quelle
    (le port la reconstruit a l'identique via `_effect_vector_triggers`). Memes canaux, meme asymetrie.
    No-op si rien ne matche."""
    return _effect_vector_triggers(state, int(EventTriggerType.EffectRemoved),
                                   None, target_id, effect_type, removing=True)


def unit_defeated_triggers(state: State, dying_id: int, killer_id: Optional[int] = None) -> list[dict]:
    """Vecteur `On(UnitDefeated=54=0x36)` (G3) — event NATIF DISTINCT de `PreUnitDeath(1)` : le natif
    `Ambush_SummonAbility` IdunBattleLogic.Entities.Abilities.Triggered.Loki.Ambush_SummonAbility$$CreateTrigger ecoute `On(0x36) & OwnerIsTarget & Not(HasFlag 0xe)`, PAS On(1). Emis
    par le pipeline de mort APRES `after_death_triggers(On 1)` (l'unite est deja alive=False -> l'ability
    fire-on-death voit sa mort). Declenche la pose du decoy Ambush (mort -> decoy) + l'enregistrement de
    `turn_defeated`. No-op si aucun porteur Ambush ne meurt."""
    ev = TriggerEvent(EventTriggerType.UnitDefeated,
                      killer_id if killer_id is not None else dying_id, dying_id,
                      ranged=False, profile=None, killer_id=killer_id, dying_id=dying_id)
    return evaluate_trigger_operation(state, ev)


def unit_revived_triggers(state: State, revived_id: int, current_ability=None) -> list[dict]:
    """Vecteur `On(UnitRevived = 45 = 0x2e)` (case-89 volet B3) — emis par `ReviveUnitOperation.Execute`
    @IdunBattle.Operations.ReviveUnitOperation$$Execute+0xac1 (`FUN_180026490(0x4d, DAT_1831d3468, events, 0x2e)`), APRES la mutation PV/flags/position
    et **AVANT** la purge de la `ReviveData` (@IdunBattle.Operations.ReviveUnitOperation$$Execute+0xda7+). DISTINCT d'`On(UnitResurrected=46=0x2f)`
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
    """Vecteur `On(UnitResurrected=46=0x2f)` (G3) — emis par `ResurrectUnitOperation` IdunBattle.Operations.ResurrectUnitOperation$$Execute apres une
    resurrection Ambush (`actor` = l'unite ressuscitee, co-localisee avec le decoy qu'elle vient de crusher).
    Alimente `DecoysAndMisdirection_BuffFriends` (G2, `(On(0x2f)|On(0x1d)) & AreFriends` -> +582 + nouveau
    decoy si GS Cult) et la re-arme HeroicFusillade (G5, `On(0x2f) & OwnerIsTarget`). No-op si aucun
    consommateur ne matche. Le decoy crushe (steppable, alive=False, meme tuile) satisfait `GetValidDeadDecoys`
    de BuffFriends (co-localisation dead-decoy/stepper)."""
    ev = TriggerEvent(EventTriggerType.UnitResurrected, resurrected_id, resurrected_id,
                      ranged=False, profile=None)
    return evaluate_trigger_operation(state, ev)
